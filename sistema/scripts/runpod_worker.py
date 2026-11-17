"""Runs the real dynamic protocol with one resident Qwen process per node."""
from __future__ import annotations

import argparse
import csv
from contextlib import ExitStack
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import time
from urllib.request import urlopen

import yaml

from .gen_compose import build_configuration, parse_args
from .runner_containers import _verify_per_node, _write

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "infra/runpod/cenarios-completos.json"
URLS = {f"node-{index}": f"http://127.0.0.1:{18100 + index}" for index in range(50)}


def load_manifest():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    c = manifest["configuration"]
    if (c["nodes"], c["gpu_count"], c["models_per_gpu"], c["inference_layout"]) != (50, 2, 25, "per_node"):
        raise ValueError("A campanha exige 50 nós em duas GPUs.")
    if hashlib.sha256((ROOT / c["task_bank"]).read_bytes()).hexdigest() != c["task_bank_sha256"]:
        raise ValueError("O banco de tarefas diverge do manifesto.")
    entries = manifest["scenarios"]
    combinations = set(itertools.product((0.2, 0.4, 0.6, 0.8), (0.1, 0.2), ("exact", "graded"), range(5)))
    if (len(entries) != 80 or len({e["id"] for e in entries}) != 80 or
            {(e["fracao_maliciosos"], e["audit_p"], e["nota"], e["semente"])
             for e in entries} != combinations or
            not all(re.fullmatch(r"[a-z0-9-]+", e["id"]) and
                    (e["nodes"], e["rounds"], e["expected_generations"]) == (50, 50, 2500)
                    for e in entries)):
        raise ValueError("O manifesto deve listar 80 cenários distintos de 50 rodadas.")
    return manifest


def scenario_configuration(c, entry, work, snapshot):
    values = {
        "nodes": c["nodes"], "rounds": entry["rounds"], "num-tasks": entry["rounds"],
        "seed": entry["semente"], "malicious": entry["fracao_maliciosos"], "degree": c["degree"],
        "dataset": "task_bank", "task-bank": ROOT / c["task_bank"], "mode": "real",
        "inference-mode": "model", "model": c["model"], "model-run-id": entry["id"],
        "model-snapshot": snapshot, "model-revision": c["model_revision"],
        "gpu-count": c["gpu_count"], "models-per-gpu": c["models_per_gpu"],
        "topology": c["topology"], "signal": c["signal"], "consensus-mode": c["consensus_mode"],
        "consensus-center": c["consensus_center"], "mechanism": c["mechanism"], "defense": c["defense"],
        "validation-score": entry["nota"], "malicious-strategy": c["malicious_strategy"],
        "honest-rounds": entry["honest_rounds"], "audit-mode": c["audit_mode"],
        "audit-p": entry["audit_p"], "collusion-value": c["collusion_value"],
        "noise-mode": c["noise_mode"], "noise-distance": c["noise_distance"],
        "timeout-s": 600, "output-dir": work, "experiment-id": entry["id"],
    }
    services, config = build_configuration(parse_args([
        part for key, value in values.items() for part in (f"--{key}", str(value))
    ]))
    processes = {}
    for node in config["nodes"]:
        node_id = node["id"]
        node["url"] = URLS[node_id]
        service = services[node_id]
        env = dict(service["environment"], NODE_URLS=json.dumps(URLS),
                   MODEL_NAME=str(snapshot), MODEL_CACHE_DIR=str(work / "node-models" / node_id),
                   MODEL_MAX_NEW_TOKENS=str(c["max_new_tokens"]),
                   MODEL_TEMPERATURE=str(c["temperature"]), MODEL_TOP_P=str(c["top_p"]))
        gpu = int(service["deploy"]["resources"]["reservations"]["devices"][0]["device_ids"][0])
        processes[node_id] = (gpu, env)
    return processes, config


def publish_archive(storage, prefix, directory):
    archive = directory.with_suffix(".tar.gz")
    try:
        with tarfile.open(archive, "w:gz", compresslevel=3) as output:
            output.add(directory, arcname=directory.name)
        return storage.upload(prefix, archive)
    finally:
        archive.unlink(missing_ok=True)


def gpu_memory():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return [{"index": int(i), "used_mib": int(used), "total_mib": int(total), "util_percent": int(util)}
                for i, used, total, util in csv.reader(result.stdout.splitlines())]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def stop_processes(processes):
    for process in processes:
        if process.poll() is None:
            process.terminate()
    until = time.monotonic() + 8
    for process in processes:
        try:
            process.wait(timeout=max(0, until - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def execute_scenario(work, entry, configuration, snapshot, devices, check, progress):
    specifications, config = scenario_configuration(configuration, entry, work, snapshot)
    config_path = work / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    # The bucket credential is only for the supervisor.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("TCC_S3_") and key != "RUNPOD_API_KEY"}
    children = []
    ready = {}
    with ExitStack() as stack:
        try:
            ordered = list(specifications)
            for start in range(0, len(ordered), len(devices)):
                batch = ordered[start:start + len(devices)]
                for node_id in batch:
                    gpu, node_env = specifications[node_id]
                    log = stack.enter_context((work / f"{node_id}.log").open("wb"))
                    process = subprocess.Popen(
                        [sys.executable, "-m", "uvicorn", "sistema.node.app:app",
                         "--host", "127.0.0.1", "--port", URLS[node_id].rsplit(":", 1)[1],
                         "--workers", "1", "--no-access-log"],
                        cwd=ROOT, env=dict(env, **node_env, CUDA_VISIBLE_DEVICES=devices[gpu]),
                        stdout=log, stderr=subprocess.STDOUT)
                    children.append(process)
                    ready[node_id] = process
                for node_id in batch:
                    until = time.monotonic() + 300
                    while time.monotonic() < until:
                        check()
                        if any(process.poll() is not None for process in children):
                            raise RuntimeError("Um nó encerrou durante a carga; consulte os logs do cenário.")
                        try:
                            with urlopen(URLS[node_id] + "/health", timeout=2) as response:
                                health = json.load(response)
                            if (health.get("node_id"), health.get("model_instances"),
                                    health.get("quantization")) == (node_id, 1, "nf4"):
                                break
                        except (OSError, ValueError):
                            pass
                        time.sleep(0.5)
                    else:
                        raise TimeoutError(f"{node_id} não carregou o Qwen NF4 em cinco minutos.")
                progress("loading", nodes_ready=len(ready))
            log = stack.enter_context((work / "orchestrator.log").open("wb"))
            coordinator = subprocess.Popen(
                [sys.executable, "-m", "sistema.orchestrator.run", "--config", str(config_path)],
                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            children.append(coordinator)
            round_started = time.monotonic()
            while coordinator.poll() is None:
                check()
                if any(process.poll() is not None for process in ready.values()):
                    raise RuntimeError("Um nó encerrou antes da conclusão do cenário.")
                rounds = work / "rounds.csv"
                count = 0
                if rounds.exists():
                    with rounds.open(encoding="utf-8", newline="") as stream:
                        count = sum(row.get("round_index", "").isdigit() for row in csv.DictReader(stream))
                fields = {"rounds_completed": count}
                if count:
                    fields["seconds_per_round_observed"] = round((time.monotonic() - round_started) / count, 2)
                progress("running", **fields)
                time.sleep(2)
            if coordinator.returncode:
                raise RuntimeError("O orquestrador encerrou com erro; consulte orchestrator.log.")
        finally:
            stop_processes(children)
    _verify_per_node(work, work / "node-models", configuration["nodes"], entry["rounds"], entry["id"],
                     configuration["model_revision"], model_path=str(snapshot))


def campaign(manifest):
    from huggingface_hub import snapshot_download
    from .runpod_storage import RunStorage

    run = os.environ["TCC_RUN_ID"]
    deadline = int(os.environ["TCC_DEADLINE"])
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", run):
        raise ValueError("ID de execução inválido.")
    workspace = Path("/workspace")
    if not workspace.is_mount():
        raise RuntimeError("O volume persistente não está montado em /workspace.")
    storage = RunStorage()
    prefix = f"runs/{run}/"
    work = workspace / "runs" / run
    work.mkdir(parents=True, exist_ok=False)
    c = manifest["configuration"]
    completed = []
    current = None
    signalled = False
    last_check = last_update = 0.0

    def set_stop(_number, _frame):
        nonlocal signalled
        signalled = True

    signal.signal(signal.SIGTERM, set_stop)
    signal.signal(signal.SIGINT, set_stop)

    def check():
        nonlocal last_check
        if signalled or time.time() >= deadline - 240:
            raise InterruptedError("Execução interrompida ou prazo de exportação atingido.")
        if time.monotonic() - last_check >= 15:
            last_check = time.monotonic()
            if storage.get_json(prefix + "stop.json"):
                raise InterruptedError("Encerramento solicitado no GitHub.")

    def progress(state, *, force=False, **fields):
        nonlocal last_update
        if force or time.monotonic() - last_update >= 60:
            data = {"run_id": run, "state": state, "updated": int(time.time()), "gpu": gpu_memory(),
                    "total": len(manifest["scenarios"]), "completed": len(completed),
                    "scenario": current.name if current else None, **fields}
            _write(work / "status.json", data)
            storage.put_json(prefix + "status.json", data)
            last_update = time.monotonic()

    try:
        progress("waiting", force=True)
        while not (permission := storage.get_json(prefix + "start.json")):
            check()
            progress("waiting")
            time.sleep(5)
        if permission["pod_id"] != os.environ.get("RUNPOD_POD_ID"):
            raise RuntimeError("A autorização da campanha pertence a outro Pod.")
        progress("starting", force=True)
        check()
        import torch
        if not torch.cuda.is_available() or torch.cuda.device_count() != c["gpu_count"]:
            raise RuntimeError("O experimento requer exatamente duas GPUs CUDA disponíveis.")
        devices = os.environ.get("CUDA_VISIBLE_DEVICES", "0,1").split(",")
        if len(devices) != c["gpu_count"] or len(set(devices)) != c["gpu_count"]:
            raise RuntimeError("O mapeamento CUDA não corresponde às duas GPUs reservadas.")
        _write(work / "runtime.json", {"torch": torch.__version__, "cuda": torch.version.cuda,
                                      "gpu": [torch.cuda.get_device_name(i) for i in range(2)],
                                      "code_revision": os.environ.get("TCC_CODE_REVISION", "")})
        storage.put_json(prefix + "manifest.json", manifest)
        storage.upload(prefix + "runtime.json", work / "runtime.json")
        snapshot = Path(snapshot_download(c["model"], revision=c["model_revision"],
                                          allow_patterns=["*.safetensors", "*.json", "*.txt", "*.jinja"]))
        for entry in manifest["scenarios"]:
            check()
            current = work / "scenarios" / entry["id"]
            current.mkdir(parents=True, exist_ok=False)
            progress("loading", force=True)
            execute_scenario(current, entry, c, snapshot, devices, check, progress)
            completed.append(publish_archive(storage, prefix + f"scenarios/{entry['id']}.tar.gz", current))
            current = None
            storage.put_json(prefix + "index.json", {"run_id": run, "artifacts": completed})
            progress("checkpointed", force=True)
        progress("completed", force=True, upload_complete=True)
    except Exception as error:
        # On failure, keep the live volume until the controller stops the Pod.
        partial = None
        if current is not None:
            try:
                partial = publish_archive(storage, prefix + f"partial/{current.name}.tar.gz", current)
            except Exception:
                print("O cenário parcial ficou apenas no volume do Pod.", flush=True)
        progress("interrupted" if isinstance(error, InterruptedError) else "failed", force=True,
                 error_type=type(error).__name__, partial=partial, upload_complete=False)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-config", action="store_true",
                        help="Valida os 80 cenários e o mapeamento sem carregar modelos.")
    args = parser.parse_args()
    manifest = load_manifest()
    if args.check_config:
        with TemporaryDirectory() as directory:
            for entry in manifest["scenarios"]:
                processes, config = scenario_configuration(manifest["configuration"], entry,
                                                             Path(directory), Path(directory))
                if (len(processes) != 50 or
                        [sum(gpu == index for gpu, _ in processes.values()) for index in range(2)] != [25, 25] or
                        len({node["url"] for node in config["nodes"]}) != 50):
                    raise ValueError("Mapeamento inválido dos 50 nós.")
        print("80 cenários, 50 nós, duas GPUs, 25 modelos por GPU.")
    else:
        campaign(manifest)


if __name__ == "__main__":
    main()
