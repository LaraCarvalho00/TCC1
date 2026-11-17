"""Executa uma grade de contêineres com deadline e cache exclusivo por cenário."""
from __future__ import annotations

import argparse
import csv
from contextlib import closing
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

from sistema.experimentos.grade_llm import scenarios
from sistema.scripts.gen_compose import generate, parse_args

ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _freeze_source(destination: Path) -> Path:
    """Keep the host gateway on the same source for an entire long experiment."""
    frozen = destination / "codigo"
    if not frozen.exists():
        pending = destination / "codigo.tmp"
        for source in (ROOT / "sistema").rglob("*.py"):
            if "tests" in source.parts or "results" in source.parts or "__pycache__" in source.parts:
                continue
            target = pending / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        task_target = pending / "sistema/dados/banco_smol.json"
        task_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "sistema/dados/banco_smol.json", task_target)
        pending.replace(frozen)
    return frozen


def _fingerprint(node_image: str, orchestrator_image: str) -> dict:
    source = hashlib.sha256()
    base = ROOT / "sistema"
    paths = sorted(path for path in base.rglob("*.py") if "tests" not in path.parts and "results" not in path.parts)
    for path in paths:
        source.update(path.relative_to(ROOT).as_posix().encode("utf-8") + b"\0")
        source.update(path.read_bytes())
    task_digest = hashlib.sha256((base / "dados" / "banco_smol.json").read_bytes()).hexdigest()
    images = {}
    for name in (node_image, orchestrator_image):
        result = subprocess.run(["docker", "image", "inspect", name, "--format", "{{.Id}}"],
                                capture_output=True, text=True, check=True, timeout=10)
        image_id = result.stdout.strip()
        if not image_id.startswith("sha256:"):
            raise RuntimeError(f"Não foi possível verificar a imagem {name!r}.")
        images[name] = image_id
    return {"codigo_sha256": source.hexdigest(), "tarefas_sha256": task_digest, "imagens": images}


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _health(port: int, run_id: str, process, until: float, workers: int | None = None) -> None:
    while time.monotonic() < until:
        if process.poll() is not None:
            raise RuntimeError("Gateway encerrou antes de ficar pronto; consulte o log.")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                health = json.load(response)
                if health.get("run_id") == run_id and (workers is None or health.get("model_instances") == workers):
                    return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise TimeoutError("Tempo limite ao iniciar gateway.")


def _shutdown(port: int, token: str, process, until: float) -> None:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/shutdown", method="POST",
                                     headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=5):
            pass
    except OSError:
        pass
    remaining = max(0.0, until - time.monotonic())
    try:
        process.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            if os.name == "nt":
                # The five CUDA workers must not outlive a stuck gateway.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=15, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                process.terminate()
        process.wait(timeout=10)


def _verify_metrics(attempt: Path, nodes: int, rounds: int) -> set[tuple[int, str]]:
    summary = json.loads((attempt / "summary.json").read_text(encoding="utf-8"))
    if summary.get("config", {}).get("ledgers_valid") is not True:
        raise RuntimeError("Cadeias ausentes ou inválidas.")
    if int(summary.get("summary", {}).get("rounds", -1)) != rounds:
        raise RuntimeError("Quantidade incorreta de rodadas no resumo.")
    with (attempt / "rounds.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != rounds or {int(row["round_index"]) for row in rows} != set(range(rounds)):
        raise RuntimeError("CSV de rodadas incompleto ou com índices duplicados.")
    if any(int(row["num_nodes"]) != nodes for row in rows):
        raise RuntimeError("Número de nós divergente no CSV de rodadas.")
    with (attempt / "per_node.csv").open(encoding="utf-8", newline="") as stream:
        node_rows = list(csv.DictReader(stream))
    expected = {(index, f"node-{node}") for index in range(rounds) for node in range(nodes)}
    observed = [(int(row["round_index"]), row["node_id"]) for row in node_rows]
    if len(observed) != len(expected) or set(observed) != expected:
        raise RuntimeError("CSV por nó incompleto ou com linhas duplicadas.")
    return expected


def _verify_completed(attempt: Path, cache: Path, nodes: int, rounds: int) -> None:
    expected = _verify_metrics(attempt, nodes, rounds)
    with closing(sqlite3.connect(f"file:{cache.as_posix()}?mode=ro", uri=True)) as db:
        requests = db.execute("SELECT round_index, node_id FROM gateway_requests").fetchall()
        generated = db.execute("SELECT COUNT(*) FROM generations").fetchone()[0]
    if len(requests) != len(expected) or set(requests) != expected or generated != len(expected):
        raise RuntimeError("Inferências concluídas não correspondem aos nós e rodadas esperados.")


def _verify_per_node(attempt: Path, cache_root: Path, nodes: int, rounds: int, run_id: str,
                     model_revision: str | None = None, *, model_path: str = "/models") -> None:
    """Every participant, including attackers, must have its own generations."""
    _verify_metrics(attempt, nodes, rounds)
    with (attempt / "rounds.csv").open(encoding="utf-8", newline="") as stream:
        tasks = {int(row["round_index"]): row["task_id"] for row in csv.DictReader(stream)}
    with (attempt / "per_node.csv").open(encoding="utf-8", newline="") as stream:
        submitted = {(int(row["round_index"]), row["node_id"]): row for row in csv.DictReader(stream)}
    expected_rounds = set(range(rounds))
    for index in range(nodes):
        node_id = f"node-{index}"
        cache = cache_root / node_id / "inferencias.sqlite"
        with closing(sqlite3.connect(f"file:{cache.as_posix()}?mode=ro", uri=True)) as db:
            rows = db.execute("SELECT round_index, node_id, task_id FROM generations").fetchall()
            responses = db.execute("SELECT round_index, answer FROM responses").fetchall()
            meta = db.execute("SELECT config FROM meta WHERE id=1").fetchone()
        identity = json.loads(meta[0]) if meta else {}
        if (identity.get("node_id") != node_id or identity.get("run_id") != run_id or
                identity.get("quantization") != "nf4" or identity.get("model") != model_path or
                identity.get("device") != "cuda" or
                (model_revision is not None and identity.get("revision") != model_revision)):
            raise RuntimeError(f"Cache de {node_id} pertence a outra execução ou nó.")
        if len(rows) != rounds or {row[0] for row in rows} != expected_rounds or any(row[1] != node_id for row in rows):
            raise RuntimeError(f"Inferências próprias de {node_id} não correspondem às rodadas esperadas.")
        if any(task_id != tasks[round_index] or task_id != submitted[(round_index, node_id)]["task_id"]
               for round_index, _node_id, task_id in rows):
            raise RuntimeError(f"Tarefas de {node_id} divergem das métricas da rodada.")
        if len(responses) != rounds or {row[0] for row in responses} != expected_rounds:
            raise RuntimeError(f"Respostas enviadas de {node_id} estão incompletas ou duplicadas.")
        for round_index, answer in responses:
            metric = submitted[(round_index, node_id)]["answer"]
            metric_answer = json.loads(metric) if metric != "" else None
            if json.loads(answer) != metric_answer:
                raise RuntimeError(f"Resposta enviada de {node_id} diverge do CSV na rodada {round_index}.")


def _start_per_node(compose_cmd: list[str], nodes: int, gpu_count: int, deadline: float, log) -> None:
    """One load per GPU at a time prevents simultaneous load peaks."""
    health_script = ("import json,urllib.request; "
                     "print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2))))")
    for first in range(0, nodes, gpu_count):
        batch = [f"node-{index}" for index in range(first, min(first + gpu_count, nodes))]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(compose_cmd, 0)
        subprocess.run(compose_cmd + ["up", "-d", "--no-deps", *batch], check=True,
                       stdout=log, stderr=subprocess.STDOUT, timeout=min(remaining, 120))
        until = min(deadline, time.monotonic() + 600)
        for node_id in batch:
            while time.monotonic() < until:
                remaining = until - time.monotonic()
                result = subprocess.run(compose_cmd + ["exec", "-T", node_id, "python", "-c", health_script],
                                        capture_output=True, text=True, timeout=min(10, max(.01, remaining)))
                if result.returncode == 0:
                    try:
                        health = json.loads(result.stdout)
                    except ValueError:
                        health = {}
                    if health.get("model_loaded") is True and health.get("node_id") == node_id and health.get("model_instances") == 1:
                        break
                time.sleep(min(1, max(0, until - time.monotonic())))
            else:
                raise subprocess.TimeoutExpired(f"Modelo próprio de {node_id} não ficou pronto", 600)


def run(destination: Path, *, seconds: float = 21600, resume: bool = False,
        fractions=(0.2, 0.4, 0.6, 0.8), probabilities=(0.1, 0.2),
        scores=("exact", "graded"), seed: int = 0, nodes: int = 20, rounds: int = 10,
        honest_rounds: int = 5, seed_selection: str = "não informado",
        cleanup_margin: float = 120, node_image="tcc-node:latest", orchestrator_image="tcc-orch:latest",
        model: str = "HuggingFaceTB/SmolLM3-3B", custom_counts: tuple[int, int] | None = None,
        extended_deadline: bool = False, protocol_timeout: float = 600,
        inference_layout: str = "shared", gpu_count: int = 1, models_per_gpu: int = 8,
        model_snapshot: str | Path | None = None, per_node_image: str = "tcc-node-model:latest",
        model_revision: str | None = None, inference_workers: int = 2, mount_code: bool = True) -> dict:
    started = time.monotonic()
    maximum = 7 * 24 * 3600 if extended_deadline else 21600
    if not 0 < seconds <= maximum or not 0 < cleanup_margin < seconds:
        raise ValueError("O limite excede o máximo permitido ou é menor que a margem de encerramento.")
    if nodes < 6 or nodes > 200 or not 1 <= rounds <= 50 or protocol_timeout <= 0:
        raise ValueError("Use de 6 a 200 nós, de 1 a 50 rodadas e timeout positivo.")
    if not 0 <= honest_rounds < rounds:
        raise ValueError("Rodadas honestas devem ser não negativas e menores que o total de rodadas.")
    if inference_layout not in ("shared", "per_node"):
        raise ValueError("inference_layout deve ser shared ou per_node.")
    if isinstance(inference_workers, bool) or not isinstance(inference_workers, int) or not 1 <= inference_workers <= 5:
        raise ValueError("Use de 1 a 5 instâncias de inferência compartilhada.")
    if model_snapshot is not None:
        model_snapshot = str(Path(model_snapshot).resolve())
        if not Path(model_snapshot).is_dir():
            raise ValueError("O snapshot local do modelo não existe.")
    if inference_layout == "per_node":
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in (gpu_count, models_per_gpu)):
            raise ValueError("A quantidade de GPUs e modelos por GPU deve ser positiva.")
        if nodes > gpu_count * models_per_gpu:
            raise ValueError("A quantidade de nós excede os slots de modelos próprios nas GPUs.")
        if model_snapshot is None or not Path(model_snapshot).is_dir():
            raise ValueError("Informe --model-snapshot com um snapshot local existente.")
        model_snapshot = str(Path(model_snapshot).resolve())
        node_image = per_node_image
    destination = destination.resolve()
    allowed = (ROOT / "sistema" / "results").resolve()
    if not destination.is_relative_to(allowed) or destination == allowed:
        raise ValueError("A saída deve ser uma subpasta nova de sistema/results.")
    manifest_path = destination / "manifesto_grade.json"
    # A grade científica continua restrita às quatro proporções. O modo
    # personalizado usa contagens explícitas, sem arredondar o perfil dos nós.
    if custom_counts is None:
        jobs = scenarios([seed], list(scores), tuple(fractions), tuple(probabilities), nodes=nodes, rounds=rounds)
        if any(abs(round(nodes * fraction) - nodes * fraction) > 1e-9 for fraction in fractions):
            raise ValueError("Cada proporção deve corresponder a uma quantidade inteira de nós.")
    else:
        honest, malicious = custom_counts
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in custom_counts) or honest + malicious != nodes:
            raise ValueError("As contagens devem ser positivas e somar o total de nós.")
        jobs = scenarios([seed], list(scores), (0.2,), tuple(probabilities), nodes=nodes, rounds=rounds)
        fractions = (malicious / nodes,)
        for entry in jobs:
            entry["fracao_maliciosos"] = fractions[0]
            entry["id"] = entry["id"].replace("m20-", f"h{honest}-m{malicious}-")
    config = {"nos": nodes, "rodadas": rounds, "rodadas_iniciais_honestas": honest_rounds,
              "criterio_semente": seed_selection,
              "sementes": [seed], "fracoes": list(fractions),
              "probabilidades": list(probabilities), "notas": list(scores), "quantizacao": "nf4",
              "tempo_maximo_s": seconds, "ruido": "relative", "distancia": 0.2, "conluio": True,
              "node_image": node_image, "orchestrator_image": orchestrator_image,
              "fingerprint": _fingerprint(node_image, orchestrator_image)}
    if model != "HuggingFaceTB/SmolLM3-3B" or extended_deadline or custom_counts is not None:
        config.update(modelo=model, contagens_personalizadas=list(custom_counts) if custom_counts else None,
                      timeout_protocolo_s=protocol_timeout)
    if inference_layout == "per_node":
        config.update(inference_layout="per_node", gpu_count=gpu_count, models_per_gpu=models_per_gpu,
                      model_snapshot=model_snapshot, model_revision=model_revision, modelo=model, instancias_modelo=nodes)
    elif inference_workers != 2 or model_snapshot is not None or model_revision is not None:
        config.update(inference_layout="shared", instancias_modelo=inference_workers,
                      inference_workers=inference_workers, model_snapshot=model_snapshot,
                      model_revision=model_revision, modelo=model)
    if not mount_code:
        config.update(codigo_na_imagem=True, codigo_host_congelado=True)
    if resume:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["configuracao"] != config:
            raise ValueError("A configuração difere da grade existente.")
    else:
        destination.mkdir(parents=True, exist_ok=False)
        manifest = {"configuracao": config, "inicio_utc": _now(), "status": "em_andamento",
                    "total_cenarios": len(jobs), "chamadas_previstas": len(jobs) * nodes * rounds,
                    "cenarios": jobs,
                    "observacao": ("Cada nó possui uma instância NF4 própria no contêiner; "
                                   "resultados parciais identificados por status." if inference_layout == "per_node" else
                                   f"Nós em contêineres, {inference_workers} instâncias NF4 compartilhadas no host; "
                                   "cada nó gera uma resposta nova por rodada e cenário. Resultados parciais identificados por status.")}
    manifest["status"] = "em_andamento"
    _write(manifest_path, manifest)
    gateway_cwd = ROOT if mount_code else _freeze_source(destination)
    pinned_images = config["fingerprint"].get("imagens", {}) if not mount_code else {}
    runtime_node_image = pinned_images.get(node_image, node_image)
    runtime_orchestrator_image = pinned_images.get(orchestrator_image, orchestrator_image)
    deadline = started + seconds
    for entry in manifest["cenarios"]:
        if entry["status"] == "concluido":
            continue
        if time.monotonic() >= deadline - cleanup_margin:
            manifest["status"] = "tempo_esgotado"
            break
        scenario = destination / "cenarios" / entry["id"]
        scenario.mkdir(parents=True, exist_ok=True)
        attempt_id = f"tentativa-{len(entry['tentativas']) + 1:04d}"
        attempt = scenario / attempt_id
        attempt.mkdir(exist_ok=False)
        project = "tcc-" + uuid.uuid4().hex[:12]
        check = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"],
                               capture_output=True, text=True, check=True, timeout=min(10, max(0.01, deadline - time.monotonic() - cleanup_margin)))
        if check.stdout.strip():
            raise RuntimeError("Nome de projeto Docker já está em uso.")
        port, token = (_port(), secrets.token_urlsafe(32)) if inference_layout == "shared" else (None, None)
        compose_file = attempt / "docker-compose.yml"
        config_file = attempt / "config.yaml"
        rel_config = config_file.relative_to(ROOT).as_posix()
        rel_attempt = attempt.relative_to(ROOT).as_posix()
        argv = ["--nodes", str(nodes), "--rounds", str(rounds), "--num-tasks", str(rounds),
                "--degree", "4", "--malicious", str(entry["fracao_maliciosos"]), "--seed", str(seed),
                "--dataset", "task_bank", "--mode", "real", "--inference-mode", "gateway", "--gateway-run-id", entry["id"],
                "--gateway-url", f"http://host.docker.internal:{port}", "--signal", "consensus",
                "--consensus-mode", "distance", "--consensus-center", "medoid", "--mechanism", "ema_slow_up",
                "--validation-score", entry["nota"], "--malicious-strategy", "knows_schedule", "--honest-rounds", str(honest_rounds),
                "--audit-mode", "random", "--audit-p", str(entry["audit_p"]), "--collusion-value", "999",
                "--noise-mode", "relative", "--noise-distance", "0.2", "--timeout-s", str(protocol_timeout),
                "--node-image", runtime_node_image, "--orchestrator-image", runtime_orchestrator_image,
                "--output-dir", rel_attempt, "--compose-out", str(compose_file), "--config-out", str(config_file)]
        if mount_code:
            argv.append("--mount-code")
        cache_root = scenario / "node-models"
        if inference_layout == "per_node":
            argv[argv.index("--inference-mode") + 1] = "model"
            for shared_option in ("--gateway-run-id", "--gateway-url"):
                position = argv.index(shared_option)
                del argv[position:position + 2]
            argv.extend(["--model-quantization", "nf4", "--model-device", "cuda", "--model-run-id", entry["id"],
                         "--model-cache-root", cache_root.relative_to(ROOT).as_posix(),
                         "--model-snapshot", model_snapshot, "--gpu-count", str(gpu_count),
                         "--models-per-gpu", str(models_per_gpu)])
            if model_revision:
                argv.extend(["--model-revision", model_revision])
        args = parse_args(argv)
        # O caminho da configuração deve ser legível dentro do contêiner Linux.
        args.config_out = rel_config
        generate(args)
        record = {"id": attempt_id, "status": "em_andamento", "inicio_utc": _now(), "projeto_docker": project}
        entry["tentativas"].append(record)
        entry["status"] = "em_andamento"
        _write(manifest_path, manifest)
        env = dict(os.environ, INFERENCE_GATEWAY_CONTROL_TOKEN=token) if token else None
        gateway_cmd = None
        if inference_layout == "shared":
            gateway_cmd = [sys.executable, "-m", "sistema.node.inference_gateway", "--tasks", "sistema/dados/banco_smol.json",
                           "--model", model,
                           "--run-id", entry["id"], "--cache", str(scenario / "inferencias.sqlite"),
                           "--host", "0.0.0.0", "--port", str(port)]
            if inference_workers != 2:
                gateway_cmd.extend(["--workers", str(inference_workers)])
            if model_snapshot is not None:
                gateway_cmd.extend(["--model-snapshot", model_snapshot])
            if model_revision is not None:
                gateway_cmd.extend(["--model-revision", model_revision])
        compose_cmd = ["docker", "compose", "--project-directory", str(ROOT), "-f", str(compose_file), "-p", project]
        process = None
        try:
            with (attempt / "compose.log").open("w", encoding="utf-8") as compose_log:
                if inference_layout == "shared":
                    with (attempt / "gateway.log").open("w", encoding="utf-8") as gateway_log:
                        process = subprocess.Popen(gateway_cmd, cwd=gateway_cwd, env=env, stdout=gateway_log, stderr=subprocess.STDOUT,
                                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        _health(port, entry["id"], process, min(deadline - cleanup_margin, time.monotonic() + 900),
                                workers=inference_workers if inference_workers != 2 else None)
                else:
                    _start_per_node(compose_cmd, nodes, gpu_count, deadline - cleanup_margin, compose_log)
                limit = max(0.01, deadline - cleanup_margin - time.monotonic())
                print(f"Iniciando {entry['id']} ({nodes} nós, {rounds} rodadas)", flush=True)
                execution = ["up", "--abort-on-container-exit", "--exit-code-from", "orchestrator"]
                if inference_layout == "per_node":
                    execution.extend(["--no-deps", "orchestrator"])
                result = subprocess.run(compose_cmd + execution,
                                        cwd=ROOT, stdout=compose_log, stderr=subprocess.STDOUT, timeout=limit)
                record["codigo_saida"] = result.returncode
                summary = attempt / "summary.json"
                if result.returncode != 0 or not summary.is_file():
                    raise RuntimeError("Contêineres não concluíram; consulte compose.log.")
                if inference_layout == "per_node":
                    _verify_per_node(attempt, cache_root, nodes, rounds, entry["id"], model_revision)
                else:
                    _verify_completed(attempt, scenario / "inferencias.sqlite", nodes, rounds)
                record["status"] = entry["status"] = "concluido"
        except subprocess.TimeoutExpired:
            record["status"] = entry["status"] = "interrompido"
            manifest["status"] = "tempo_esgotado"
        except BaseException as exc:
            record["status"] = entry["status"] = "falhou"
            record["erro"] = f"{type(exc).__name__}: {exc}"
            manifest["status"] = "falhou"
        finally:
            if inference_layout == "per_node":
                try:
                    with (attempt / "nodes.log").open("w", encoding="utf-8") as log:
                        subprocess.run(compose_cmd + ["logs", "--no-color"], cwd=ROOT, stdout=log,
                                       stderr=subprocess.STDOUT, check=False, timeout=15)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    record["erro_coleta_logs"] = f"{type(exc).__name__}: {exc}"
            try:
                remaining = max(0.01, deadline - time.monotonic() - 70)
                stopped = subprocess.run(compose_cmd + ["down"], cwd=ROOT, capture_output=True,
                                         timeout=min(45, remaining), check=False)
                if stopped.returncode != 0:
                    raise RuntimeError(f"compose down retornou {stopped.returncode}")
            except (subprocess.TimeoutExpired, OSError, RuntimeError) as exc:
                record["erro_encerramento_docker"] = f"{type(exc).__name__}: {exc}"
                manifest["status"] = "falhou"
            finally:
                try:
                    if process is not None:
                        _shutdown(port, token, process, min(time.monotonic() + 60, deadline - 5))
                except (OSError, subprocess.TimeoutExpired) as exc:
                    record["erro_encerramento_gateway"] = f"{type(exc).__name__}: {exc}"
                    manifest["status"] = "falhou"
                record["fim_utc"] = _now()
                _write(manifest_path, manifest)
        if manifest["status"] in ("tempo_esgotado", "falhou"):
            break
    else:
        manifest["status"] = "concluido"
    manifest["fim_utc"] = _now()
    _write(manifest_path, manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Grade de contêineres com inferência NF4 e prazo máximo")
    parser.add_argument("--saida", required=True)
    parser.add_argument("--retomar", action="store_true")
    parser.add_argument("--limite-segundos", type=float, default=21600)
    parser.add_argument("--prazo-estendido", action="store_true", help="Permite prazo explícito de até sete dias para a nuvem.")
    parser.add_argument("--nos", type=int, default=20)
    parser.add_argument("--honestos", type=int)
    parser.add_argument("--maliciosos", type=int)
    parser.add_argument("--modelo", default="HuggingFaceTB/SmolLM3-3B")
    parser.add_argument("--inference-layout", choices=("shared", "per_node"), default="shared")
    parser.add_argument("--inference-workers", type=int, default=2, help="Instâncias NF4 compartilhadas no host (1 a 5).")
    parser.add_argument("--codigo-da-imagem", action="store_true", help="Usa código fixo nas imagens e cópia congelada no gateway.")
    parser.add_argument("--gpu-count", type=int, default=1)
    parser.add_argument("--models-per-gpu", type=int, default=8)
    parser.add_argument("--model-snapshot")
    parser.add_argument("--model-revision")
    parser.add_argument("--per-node-image", default="tcc-node-model:latest")
    parser.add_argument("--timeout-protocolo", type=float, default=600)
    parser.add_argument("--rodadas", type=int, default=10, help="Quantidade de rodadas por cenário.")
    parser.add_argument("--rodadas-honestas", type=int, default=5,
                        help="Rodadas iniciais em que os maliciosos imitam os honestos.")
    parser.add_argument("--semente", type=int, default=0, help="Semente usada nos sorteios do cenário.")
    parser.add_argument("--criterio-semente", default="não informado", help="Descrição de como a semente foi escolhida.")
    args = parser.parse_args(argv)
    if (args.honestos is None) != (args.maliciosos is None):
        parser.error("Informe as duas contagens: --honestos e --maliciosos.")
    result = run(Path(args.saida), seconds=args.limite_segundos, resume=args.retomar,
                 rounds=args.rodadas, honest_rounds=args.rodadas_honestas, seed=args.semente,
                 seed_selection=args.criterio_semente, nodes=args.nos, model=args.modelo,
                 extended_deadline=args.prazo_estendido, protocol_timeout=args.timeout_protocolo,
                 inference_layout=args.inference_layout, gpu_count=args.gpu_count, models_per_gpu=args.models_per_gpu,
                 inference_workers=args.inference_workers,
                 mount_code=not args.codigo_da_imagem,
                 model_snapshot=args.model_snapshot, per_node_image=args.per_node_image,
                 model_revision=args.model_revision,
                 custom_counts=(args.honestos, args.maliciosos) if args.honestos is not None else None)
    print("Status:", result["status"])
    return 0 if result["status"] == "concluido" else 1


if __name__ == "__main__":
    raise SystemExit(main())
