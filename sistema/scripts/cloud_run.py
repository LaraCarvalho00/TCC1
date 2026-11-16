"""Executa e publica uma grade efêmera; encerra o host após preservar resultados.

Este módulo só depende da biblioteca padrão. O runner e a LLM executam em um
subprocesso, permitindo publicar progresso mesmo enquanto a GPU está ocupada.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tarfile
import time

from sistema.aplicacao.capacidade_nuvem import DEFAULT_INSTANCE, plan_capacity

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path("/opt/distributed-ai/runtime")
FINAL_MARGIN = 900


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate(config: dict) -> dict:
    """Valida inclusive quando chamado diretamente, fora do GitHub Actions."""
    config = dict(config)
    for name, default in (("nodes", 50), ("rounds", 50), ("seed", 0), ("honest_rounds", 5),
                          ("max_hours", 72), ("honest_nodes", 40), ("malicious_nodes", 10)):
        value = config.get(name, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} deve ser inteiro.")
        config[name] = value
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", str(config.get("run_id", ""))):
        raise ValueError("run_id inválido.")
    if config.get("mode", "matrix") not in ("matrix", "custom"):
        raise ValueError("mode deve ser matrix ou custom.")
    config.setdefault("mode", "matrix")
    if not 6 <= config["nodes"] <= 200 or not 1 <= config["rounds"] <= 50:
        raise ValueError("Use de 6 a 200 nós e de 1 a 50 rodadas.")
    if config["mode"] == "matrix" and config["nodes"] % 5:
        raise ValueError("A grade requer total de nós múltiplo de cinco.")
    if config["mode"] == "custom" and (min(config["honest_nodes"], config["malicious_nodes"]) < 1 or
                                       config["honest_nodes"] + config["malicious_nodes"] != config["nodes"]):
        raise ValueError("As contagens honestas e maliciosas devem ser positivas e somar nodes.")
    if not 0 <= config["honest_rounds"] < config["rounds"] or config["seed"] < 0:
        raise ValueError("Semente ou rodadas iniciais inválidas.")
    if not 1 <= config["max_hours"] <= 168:
        raise ValueError("Use prazo entre 1 e 168 horas.")
    if config.get("inference_layout", "per_node") != "per_node" or "workers" in config:
        raise ValueError("O worker AWS exige uma LLM dedicada por nó, sem pool de workers.")
    capacity = plan_capacity(config["nodes"], config.get("instance_type", DEFAULT_INSTANCE))
    if any(key in config and config[key] != value for key, value in capacity.items()):
        raise ValueError("Configuração de capacidade difere do perfil escolhido.")
    config.update(capacity)
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", str(config.get("results_bucket", ""))):
        raise ValueError("results_bucket inválido.")
    if config.get("results_prefix") != "runs/" + config["run_id"]:
        raise ValueError("results_prefix deve ser runs/<run_id>.")
    if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-[0-9]", str(config.get("aws_region", ""))):
        raise ValueError("aws_region inválida.")
    model = config.setdefault("model", "HuggingFaceTB/SmolLM3-3B")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", model):
        raise ValueError("model deve ser um identificador público do Hugging Face.")
    deadline = config.get("deadline_epoch")
    if deadline is not None and (isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or deadline <= 0):
        raise ValueError("deadline_epoch inválido.")
    return config


def command(config: dict, output: Path, seconds: float) -> list[str]:
    snapshot = config.get("model_snapshot")
    if not snapshot or not Path(snapshot).is_absolute():
        raise ValueError("Informe o snapshot local absoluto para cada nó montar seu próprio modelo.")
    args = [sys.executable, "-m", "sistema.scripts.runner_containers", "--saida", str(output),
            "--inference-layout", "per_node", "--gpu-count", str(config["gpu_count"]),
            "--models-per-gpu", str(config["models_per_gpu"]), "--model-snapshot", str(snapshot),
            "--model-revision", config.get("model_revision", "unrecorded"),
            "--per-node-image", "tcc-node-model:latest",
            "--nos", str(config["nodes"]), "--rodadas", str(config["rounds"]),
            "--rodadas-honestas", str(config["honest_rounds"]), "--semente", str(config["seed"]),
            "--criterio-semente", "Semente informada antes da execução pelo workflow; sem seleção por resultado.",
            "--modelo", config["model"], "--limite-segundos", str(seconds), "--prazo-estendido",
            "--timeout-protocolo", "3600"]
    if config["mode"] == "custom":
        args.extend(["--honestos", str(config["honest_nodes"]), "--maliciosos", str(config["malicious_nodes"])])
    return args


class Publisher:
    def __init__(self, config: dict, runtime: Path):
        self.config, self.runtime = config, runtime
        self.base = f"s3://{config['results_bucket']}/{config['results_prefix']}"
        self.checkpoints = {}

    def aws(self, *args: str) -> None:
        for attempt in range(3):
            try:
                subprocess.run(["aws", "--region", self.config["aws_region"], *args],
                               env=dict(os.environ, AWS_PAGER=""), check=True, timeout=180)
                return
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def status(self, state: str, output: Path, **extra) -> dict:
        total = 16 if self.config["mode"] == "matrix" else 4
        status = {"run_id": self.config["run_id"], "state": state, "updated_at": stamp(),
                  "total_scenarios": total, "completed_scenarios": 0,
                  "planned_generations": total * self.config["nodes"] * self.config["rounds"],
                  "upload_complete": False, "inference_layout": "per_node",
                  "model_instances": self.config["nodes"], "gpu_count": self.config["gpu_count"]}
        manifest = output / "manifesto_grade.json"
        if manifest.is_file():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            status["completed_scenarios"] = sum(item["status"] == "concluido" for item in data["cenarios"])
            status["experiment_status"] = data["status"]
        status.update(extra)
        path = self.runtime / "status.json"
        path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.aws("s3", "cp", str(path), self.base + "/status.json", "--only-show-errors")
        return status

    def snapshot(self, output: Path, *, final: bool = False) -> None:
        if output.is_dir():
            args = ["s3", "sync", str(output), self.base + "/results", "--only-show-errors"]
            if not final:
                args.extend(["--exclude", "*.sqlite*"])
            self.aws(*args)
        if not final and output.is_dir():
            # Copiar SQLite/WAL diretamente durante escrita pode gerar um cache
            # inconsistente. O backup online fornece um checkpoint coerente.
            caches = list(output.glob("cenarios/*/inferencias.sqlite"))
            caches.extend(output.glob("cenarios/*/node-models/*/inferencias.sqlite"))
            for cache in caches:
                # Cenários concluídos ficam imutáveis. Evita enviar cópias
                # idênticas a cada minuto, especialmente em bucket versionado.
                fingerprints = []
                for source_path in (cache, Path(str(cache) + "-wal")):
                    if source_path.is_file():
                        info = source_path.stat()
                        fingerprints.append((info.st_size, info.st_mtime_ns))
                    else:
                        fingerprints.append(None)
                fingerprint = tuple(fingerprints)
                if self.checkpoints.get(str(cache)) == fingerprint:
                    continue
                relative = cache.relative_to(output / "cenarios")
                target = self.runtime / "checkpoints" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with closing(sqlite3.connect(f"file:{cache.as_posix()}?mode=ro", uri=True, timeout=5)) as source:
                    with closing(sqlite3.connect(target)) as destination:
                        source.backup(destination, pages=256, sleep=.01)
                self.aws("s3", "cp", str(target), self.base + "/checkpoints/" + relative.as_posix(),
                         "--only-show-errors")
                self.checkpoints[str(cache)] = fingerprint
        for log in (Path("/var/log/distributed-ai-bootstrap.log"), Path("/var/log/cloud-init-output.log"),
                    Path("/opt/distributed-ai/bootstrap.log")):
            if log.is_file():
                shutil.copy2(log, self.runtime / log.name)
        self.aws("s3", "sync", str(self.runtime), self.base + "/runtime", "--exclude", "*.tar.gz",
                 "--exclude", "status.json", "--exclude", "checkpoints/*", "--only-show-errors")

    def finish(self, output: Path, state: str, **extra) -> dict:
        self.snapshot(output, final=True)
        archive = self.runtime / "results.tar.gz"
        with tarfile.open(archive, "w:gz", dereference=False) as tar:
            if output.is_dir():
                tar.add(output, arcname="results", recursive=True)
            for path in self.runtime.iterdir():
                if path.is_file() and path != archive and path.name != "status.json":
                    tar.add(path, arcname="runtime/" + path.name)
        self.aws("s3", "cp", str(archive), self.base + "/results.tar.gz", "--only-show-errors")
        # O marcador terminal é o último objeto enviado. Quem limpa a infra
        # só pode interpretá-lo como sucesso após estes uploads retornarem zero.
        return self.status(state, output, artifact_uri=self.base + "/results.tar.gz", upload_complete=True, **extra)


def stop_process(process) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=10)


def cleanup_projects(output: Path) -> None:
    manifest = output / "manifesto_grade.json"
    if not manifest.is_file():
        return
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for entry in data["cenarios"]:
        for attempt in entry["tentativas"]:
            if attempt["status"] == "concluido":
                continue
            compose = output / "cenarios" / entry["id"] / attempt["id"] / "docker-compose.yml"
            subprocess.run(["docker", "compose", "--project-directory", str(ROOT), "-f", str(compose),
                            "-p", attempt["projeto_docker"], "down"], check=False, timeout=60)


def run(config: dict, *, runtime: Path = RUNTIME, bootstrap_error: str | None = None,
        shutdown: bool = True) -> int:
    config = validate(config)
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "run.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output = ROOT / "sistema" / "results" / ("cloud-" + config["run_id"])
    publisher = Publisher(config, runtime)
    process, state, error = None, "failed", None
    try:
        if bootstrap_error:
            raise RuntimeError(bootstrap_error)
        publisher.status("initializing", output)
        deadline = min(float(config.get("deadline_epoch", time.time() + config["max_hours"] * 3600)),
                       time.time() + config["max_hours"] * 3600)
        seconds = deadline - time.time() - FINAL_MARGIN
        if seconds <= 180:
            raise TimeoutError("Prazo restante insuficiente para executar e publicar resultados.")
        with (runtime / "runner.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command(config, output, seconds), cwd=ROOT, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=(os.name == "posix"))
            while process.poll() is None:
                if time.time() >= deadline - FINAL_MARGIN:
                    raise TimeoutError("Prazo de execução esgotado; preservando resultados parciais.")
                try:
                    publisher.snapshot(output)
                    publisher.status("running", output)
                except Exception as exc:
                    print(f"Snapshot temporariamente indisponível: {exc}", file=sys.stderr, flush=True)
                try:
                    process.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    pass
        manifest = json.loads((output / "manifesto_grade.json").read_text(encoding="utf-8"))
        state = {"concluido": "completed", "tempo_esgotado": "timed_out"}.get(manifest["status"], "failed")
        if process.returncode != 0 and state == "completed":
            state = "failed"
        if state != "completed":
            error = f"Runner terminou com status {manifest['status']}, saída {process.returncode}."
    except BaseException as exc:
        state = "timed_out" if isinstance(exc, TimeoutError) else "failed"
        error = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            stop_process(process)
            cleanup_projects(output)
        except BaseException as exc:
            state, error = "failed", f"Falha ao encerrar processos: {type(exc).__name__}: {exc}"
        try:
            manifest_path = output / "manifesto_grade.json"
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if any(item["status"] == "concluido" for item in manifest["cenarios"]):
                    for module, folder in (("graficos_cenarios_llm", "graficos-acuracia"),
                                           ("graficos_reputacao_llm", "graficos-reputacao")):
                        try:
                            subprocess.run([sys.executable, "-m", "sistema.experimentos." + module,
                                            "--grade", str(output), "--saida", str(output / folder)],
                                           cwd=ROOT, check=True, timeout=180)
                        except (OSError, subprocess.SubprocessError) as exc:
                            state, error = "failed", f"Falha ao gerar gráficos: {type(exc).__name__}: {exc}"
            publisher.finish(output, state, **({"error": error} if error else {}))
        except BaseException as exc:
            print(f"Falha na publicação final: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            # Upload parcial não se torna sucesso, mesmo que a execução tenha
            # terminado. O marcador permite diagnóstico pelo reconciliador.
            state = "failed"
            try:
                publisher.status("failed", output, upload_complete=False,
                                 error=f"Falha na publicação: {type(exc).__name__}: {exc}")
            except BaseException:
                pass
        finally:
            if shutdown:
                subprocess.run(["shutdown", "-h", "now"], check=False, timeout=30)
    return 0 if state == "completed" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Worker efêmero de experimentos com publicação no S3")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--bootstrap-error")
    args = parser.parse_args(argv)
    # systemd pode pedir encerramento antes do deadline; preserve as saídas
    # já produzidas pelo mesmo caminho usado pelo timeout do experimento.
    def terminate(_signum, _frame):
        raise TimeoutError("Encerramento solicitado pelo sistema operacional.")
    signal.signal(signal.SIGTERM, terminate)
    return run(json.loads(args.config.read_text(encoding="utf-8")), bootstrap_error=args.bootstrap_error)


if __name__ == "__main__":
    raise SystemExit(main())
