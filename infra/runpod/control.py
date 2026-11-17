"""Launch and reconcile Runpod campaigns from short GitHub Actions jobs."""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from sistema.scripts.runpod_storage import PREFIX, RunStorage

HERE = Path(__file__).resolve().parent
TF = ["terraform", f"-chdir={HERE / 'run'}"]
API = "https://api.runpod.io/v2"
STOPPED = {"EXITED", "STOPPED", "TERMINATED"}
ID_PATTERN = r"gh-[0-9]+-[0-9]+"
MAX_STARTUP_SECONDS = 20 * 60
STOP_GRACE_SECONDS = 5 * 60


def api(path, method="GET", body=None):
    request = Request(API + path, method=method, data=None if body is None else json.dumps(body).encode(),
                      headers={"Authorization": "Bearer " + os.environ["RUNPOD_API_KEY"],
                               "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            result = response.read()
    except HTTPError as error:
        if error.code == 404 and path.startswith("/pods/"):
            return None
        raise RuntimeError(f"Runpod respondeu HTTP {error.code} em {method} {path}.") from None
    return json.loads(result) if result else None


def pod_path(pod_id):
    return f"/pods/{quote(pod_id, safe='')}"


def matching_pod(record):
    if record.get("pod_id"):
        pod = api(pod_path(record["pod_id"]))
        if pod and pod.get("name") != record["pod_name"]:
            raise RuntimeError("O nome do Pod divergente impede a reconciliação.")
        return pod
    # Creation may succeed remotely just before Terraform persists its state.
    matches = [pod for pod in api("/pods") if pod.get("name") == record["pod_name"]]
    if len(matches) > 1:
        raise RuntimeError("Mais de um Pod tem o nome reservado desta execução.")
    return matches[0] if matches else None


def set_pod_state(pod, *, terminate=False):
    path = pod_path(pod["id"])
    if terminate:
        api(path, "DELETE")
    elif pod.get("status") not in STOPPED:
        api(path + "/action", "POST", {"action": "stop"})
    for _ in range(8):
        current = api(path)
        if current is None or current.get("status") == "TERMINATED":
            return "terminated"
        if not terminate and current.get("status") in STOPPED:
            return "stopped"
        time.sleep(3)
    raise RuntimeError("O Runpod ainda não confirmou a ação. A próxima reconciliação verificará novamente.")


def report(message):
    print(message, flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(message + "\n\n")


def preflight():
    required = ("RUNPOD_API_KEY", "TCC_S3_ENDPOINT", "TCC_S3_BUCKET", "TCC_S3_ACCESS_KEY",
                "TCC_S3_SECRET_KEY", "TCC_STATE_BUCKET", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                "TCC_REGISTRY_ID")
    absent = [key for key in required if not os.environ.get(key)]
    if absent:
        raise ValueError("Configure as variáveis/Secrets do ambiente runpod: " + ", ".join(absent))
    endpoint = urlparse(os.environ["TCC_S3_ENDPOINT"])
    if endpoint.scheme != "https" or not endpoint.hostname or not endpoint.hostname.endswith(".r2.cloudflarestorage.com"):
        raise ValueError("Use o endpoint HTTPS de S3 do R2, sem caminho.")
    if endpoint.path not in ("", "/") or endpoint.username or endpoint.query or endpoint.fragment:
        raise ValueError("Use somente o endpoint da conta R2.")
    if os.environ["TCC_S3_BUCKET"] == os.environ["TCC_STATE_BUCKET"]:
        raise ValueError("Use buckets privados distintos para resultados e estado Terraform.")
    storage = RunStorage()
    storage.client.list_objects_v2(Bucket=storage.bucket, Prefix=PREFIX, MaxKeys=1)
    api("/pods")
    report("Acesso ao Runpod e ao bucket de resultados verificado.")


def terraform_init(run_id):
    # An override keeps the regular local plan and mock tests independent of R2.
    configuration = {"terraform": {"backend": {"s3": {
        "bucket": os.environ["TCC_STATE_BUCKET"], "key": f"runpod/{run_id}/terraform.tfstate",
        "region": "auto", "endpoints": {"s3": os.environ["TCC_S3_ENDPOINT"]},
        "skip_credentials_validation": True, "skip_metadata_api_check": True,
        "skip_region_validation": True, "skip_requesting_account_id": True,
        "skip_s3_checksum": True, "use_path_style": True, "use_lockfile": True,
    }}}}
    override = HERE / "run" / "backend_override.tf.json"
    override.write_text(json.dumps(configuration), encoding="utf-8")
    subprocess.run(TF + ["init", "-input=false", "-no-color", "-reconfigure", "-lockfile=readonly",
                         "-plugin-dir=" + os.environ["TCC_PROVIDER_MIRROR"]], check=True, timeout=60)


def controlled_runs(storage):
    for key in storage.keys("controls/"):
        if key.endswith(".json"):
            record = storage.get_json(key)
            if record is not None:
                yield key, record


def launch(storage, args):
    if not re.fullmatch(ID_PATTERN, args.run_id):
        raise ValueError("ID de execução inválido.")
    if not re.fullmatch(r"ghcr\.io/[a-z0-9_.\-/]+@sha256:[0-9a-f]{64}", args.image):
        raise ValueError("Informe o digest da imagem publicada no GHCR.")
    if (not 1 <= args.max_hours <= 168 or not args.max_hourly.is_finite() or
            not Decimal("1.38") <= args.max_hourly <= Decimal("3.00")):
        raise ValueError("Use prazo de 1–168 horas e preço máximo entre US$ 1,38/h e US$ 3,00/h.")
    if any(record["state"] in {"launching", "running", "stop_requested"} for _, record in controlled_runs(storage)):
        raise RuntimeError("Já existe uma execução ativa neste bucket.")
    now = int(time.time())
    key = f"controls/{args.run_id}.json"
    record = {"run_id": args.run_id, "pod_name": "tcc-qwen-" + args.run_id, "state": "launching",
              "deadline": now + args.max_hours * 3600, "started": now,
              "max_hourly": str(args.max_hourly), "commit": os.environ["GITHUB_SHA"]}
    terraform_init(args.run_id)
    variables = dict(os.environ, TF_VAR_run_id=args.run_id, TF_VAR_image=args.image,
                     TF_VAR_registry_id=os.environ["TCC_REGISTRY_ID"],
                     TF_VAR_campaign=json.dumps({"deadline": record["deadline"], "bucket": storage.bucket,
                                                 "endpoint": os.environ["TCC_S3_ENDPOINT"]}))
    plan = Path(os.environ["RUNNER_TEMP"]) / "runpod.tfplan"
    subprocess.run(TF + ["plan", "-input=false", "-no-color", "-out=" + str(plan)],
                   env=variables, check=True, timeout=120)
    storage.put_json(key, record, IfNoneMatch="*")
    try:
        subprocess.run(TF + ["apply", "-input=false", "-no-color", str(plan)],
                       env=variables, check=True, timeout=360)
        pod_id = json.loads(subprocess.check_output(TF + ["output", "-json", "pod_id"], timeout=30))
        record.update(pod_id=pod_id, state="running")
        storage.put_json(key, record)
        report(f"Execução `{args.run_id}` iniciada no Pod `{pod_id}`. "
               f"Prazo de {args.max_hours} h. Progresso em `{PREFIX}runs/{args.run_id}/status.json`.")
        reconcile(storage, key, record)
    except Exception:
        record["stop_requested"] = int(time.time()) - STOP_GRACE_SECONDS
        record["state"] = "stop_requested"
        storage.put_json(key, record)
        reconcile(storage, key, record)
        raise


def uploaded_campaign(storage, prefix, status):
    if (not status or status.get("state") != "completed" or status.get("upload_complete") is not True or
            status.get("completed") != 80):
        return False
    index = storage.get_json(prefix + "index.json")
    manifest = storage.get_json(prefix + "manifest.json")
    if not index or not manifest or len(manifest.get("scenarios", [])) != 80:
        return False
    expected = {PREFIX + prefix + f"scenarios/{entry['id']}.tar.gz" for entry in manifest["scenarios"]}
    artifacts = index.get("artifacts", [])
    return (len(expected) == len(artifacts) == 80 and
            {entry["key"] for entry in artifacts} == expected and
            {PREFIX + name for name in storage.keys(prefix + "scenarios/")} == expected)


def reconcile(storage, key, record):
    run_id = record["run_id"]
    prefix = f"runs/{run_id}/"
    now = int(time.time())
    pod = matching_pod(record)
    status = storage.get_json(prefix + "status.json")
    if pod is None:
        if record.get("pod_id") or now >= record["started"] + MAX_STARTUP_SECONDS:
            record["state"] = "terminated"
    else:
        record["pod_id"] = pod["id"]
        rate = Decimal(str(pod.get("cost") or 0))
        last_progress = status.get("updated", record["started"]) if status else record["started"]
        expired = now >= record["deadline"] or now >= last_progress + MAX_STARTUP_SECONDS
        startup_expired = now >= record["started"] + MAX_STARTUP_SECONDS
        if uploaded_campaign(storage, prefix, status):
            record["state"] = set_pod_state(pod, terminate=True)
        elif pod.get("status") in STOPPED:
            record["state"] = "stopped"
        elif (expired or rate > Decimal(record["max_hourly"]) or pod.get("status") == "ERROR" or
              (record.get("stop_requested") and now >= record["stop_requested"] + STOP_GRACE_SECONDS) or
              (status and status["state"] in {"failed", "interrupted"}) or
              (startup_expired and (record["state"] == "launching" or
               (status and status["state"] == "waiting" and not storage.get_json(prefix + "start.json"))))):
            record["state"] = set_pod_state(pod)
        elif record["state"] == "running" and pod.get("status") == "RUNNING" and rate > 0:
            gpu = pod.get("gpu") or {}
            if (gpu.get("id"), gpu.get("count")) != ("NVIDIA RTX A6000", 2):
                record["state"] = set_pod_state(pod)
            elif not storage.get_json(prefix + "start.json"):
                storage.put_json(prefix + "start.json", {"pod_id": pod["id"], "hourly_rate": str(rate)})
    storage.put_json(key, record)
    progress = ""
    if status:
        progress = f" {status['completed']}/{status['total']} cenários."
        if status.get("scenario"):
            progress += f" Cenário `{status['scenario']}`, rodada {status.get('rounds_completed', 0)}."
        if status.get("seconds_per_round_observed") is not None:
            progress += f" Aproximadamente {status['seconds_per_round_observed']} s por rodada neste cenário."
    report(f"`{run_id}` · `{record['state']}` · Pod `{record.get('pod_id', 'pendente')}`.{progress}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("preflight", "launch", "status", "stop", "reconcile"))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--image", default="")
    parser.add_argument("--max-hours", type=int, default=48)
    parser.add_argument("--max-hourly", type=Decimal, default=Decimal("1.42"))
    args = parser.parse_args()
    if args.operation == "preflight":
        preflight()
        return
    storage = RunStorage()
    if args.operation == "launch":
        launch(storage, args)
        return
    if args.operation == "reconcile":
        for key, record in controlled_runs(storage):
            if record["state"] in {"launching", "running", "stop_requested"}:
                reconcile(storage, key, record)
        return
    if not re.fullmatch(ID_PATTERN, args.run_id):
        parser.error("Informe o ID gh-... da execução.")
    key = f"controls/{args.run_id}.json"
    record = storage.get_json(key)
    if record is None:
        parser.error("Execução não encontrada.")
    if args.operation == "stop" and record["state"] in {"launching", "running", "stop_requested"}:
        prefix = f"runs/{args.run_id}/"
        storage.put_json(prefix + "stop.json", {"requested": int(time.time())})
        record["stop_requested"] = record.get("stop_requested", int(time.time()))
        record["state"] = "stop_requested"
        storage.put_json(key, record)
    if args.operation == "status" or record["state"] in {"stopped", "terminated"}:
        status = storage.get_json(f"runs/{args.run_id}/status.json")
        report(f"`{args.run_id}` · `{record['state']}` · Pod `{record.get('pod_id', 'pendente')}`. "
               + (f"{status['completed']}/{status['total']} cenários. "
                  f"Cenário `{status.get('scenario')}`, rodada {status.get('rounds_completed', 0)}."
                  if status else "Aguardando o primeiro registro do Pod."))
    else:
        reconcile(storage, key, record)


if __name__ == "__main__":
    main()
