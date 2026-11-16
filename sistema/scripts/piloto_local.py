"""Mede duas LLMs NF4 próprias, com HTTP local e saídas exclusivas por nó.

É um piloto de inferência: não executa consenso, contêineres ou a grade de
50 modelos residentes. Nenhum gabarito é enviado aos serviços dos nós.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
import csv
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import sqlite3
import statistics
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
MODEL = "HuggingFaceTB/SmolLM3-3B"


def save(path, value):
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def memory():
    if os.name != "nt":
        return {}
    class Status(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (key, ctypes.c_ulonglong) for key in ("total", "free", "page_total", "page_free", "virtual_total", "virtual_free", "extended")]
    state = Status()
    state.length = ctypes.sizeof(state)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
        raise OSError("GlobalMemoryStatusEx failed")
    return {"ram_total_mib": state.total // 1024**2, "ram_free_mib": state.free // 1024**2,
            "page_free_mib": state.page_free // 1024**2}


def gpu():
    fields = "timestamp,memory.used,memory.total,temperature.gpu,utilization.gpu,power.draw,clocks.sm,clocks_event_reasons.sw_thermal_slowdown"
    result = subprocess.run(["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, check=True, timeout=10,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    values = [item.strip() for item in result.stdout.strip().splitlines()[0].split(",")]
    names = ("timestamp_gpu", "gpu_used_mib", "gpu_total_mib", "temperature_c", "gpu_util_pct", "power_w", "clock_mhz", "thermal_slowdown")
    return dict(zip(names, values))


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(url, body=None, timeout=240):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def infer(node, task, index):
    started = time.perf_counter()
    result = request(node["url"] + "/infer", {"task_id": task["id"], "question": task["question"], "round_index": index})
    if result.get("node_id") != node["node_id"] or result.get("task_id") != task["id"]:
        raise ValueError("Identidade de resposta divergente")
    return {"round_index": index, "node_id": node["node_id"], "task_id": task["id"],
            "client_wall_s": time.perf_counter() - started, "model_s": result["latency_ms"] / 1000,
            "answer": result.get("answer"), "correct": int(result.get("answer") == task["answer"]),
            "first_pair": int(index == 0)}


def aggregate(rows, pairs, total_s, load_s):
    if not rows or not pairs:
        raise ValueError("Nenhuma geração medida")
    wall = sum(item["wall_s"] for item in pairs)
    equivalents = wall / len(rows)
    return {"generations": len(rows), "questions": len(pairs), "generation_wall_s": wall,
            "end_to_end_s": total_s, "load_s": load_s,
            "wall_seconds_per_generation": equivalents, "generations_per_hour": len(rows) * 3600 / wall,
            "median_model_s": statistics.median(row["model_s"] for row in rows),
            "accuracy_descriptive": sum(row["correct"] for row in rows) / len(rows),
            "projection_same_local_gpu_40000_h": equivalents * 40000 / 3600,
            "projection_eight_gpus_equal_local_throughput_40000_h": equivalents * 40000 / 3600 / 8,
            "projection_caveat": "Divisão idealizada, sem medição da A6000, sete modelos/GPU, 50 nós, rede Docker ou 800 cargas. Não comprova conclusão dentro de R$ 500."}


def verify(directory, nodes, rounds):
    verified = []
    for node in nodes:
        with closing(sqlite3.connect(f"file:{(directory / node['node_id'] / 'inferencias.sqlite').as_posix()}?mode=ro", uri=True)) as db:
            generations = db.execute("SELECT round_index,node_id FROM generations").fetchall()
            submitted = db.execute("SELECT round_index FROM responses").fetchall()
        expected = {(i, node["node_id"]) for i in range(rounds)}
        if len(generations) != rounds or set(generations) != expected or sorted(item[0] for item in submitted) != list(range(rounds)):
            raise RuntimeError(f"Gerações ou respostas incompletas: {node['node_id']}")
        verified.append({"node_id": node["node_id"], "generations": rounds, "responses": rounds})
    return verified


def run(output, *, rounds=50, deadline_seconds=3600):
    output = output.resolve()
    allowed = (ROOT / "resultados" / "llm").resolve()
    if not output.is_relative_to(allowed) or not 1 <= rounds <= 50:
        raise ValueError("Use uma pasta nova dentro de resultados/llm e até 50 questões")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    deadline = time.monotonic() + deadline_seconds
    task_path = ROOT / "sistema" / "dados" / "banco_smol.json"
    tasks = json.loads(task_path.read_text(encoding="utf-8"))["tarefas"][:rounds]
    if len(tasks) != rounds:
        raise ValueError("Questões insuficientes")
    from huggingface_hub import snapshot_download
    snapshot = snapshot_download(MODEL, local_files_only=True)
    revision = Path(snapshot).name
    manifest_path = output / "manifesto.json"
    manifest = {"status": "em_andamento", "start_utc": datetime.now(timezone.utc).isoformat(),
                "kind": "piloto_local_http_modelos_proprios", "model": MODEL, "revision": revision,
                "nodes": 2, "questions": rounds, "planned_generations": 2 * rounds,
                "quantization": "nf4", "max_new_tokens": 256, "temperature": .7, "top_p": .95, "seed": 0,
                "task_sha256": hashlib.sha256(task_path.read_bytes()).hexdigest(),
                "environment": {name: importlib.metadata.version(name) for name in ("torch", "transformers", "bitsandbytes", "fastapi", "uvicorn")},
                "memory_before": memory(), "gpu_before": gpu(), "loads": [], "pairs": [],
                "limitations": "Dois nós HTTP localhost em processos Windows; sem Docker, consenso ou 50 modelos simultâneos. Os serviços já ativos na máquina permanecem concorrendo por recursos.",
                "code_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (Path(__file__), ROOT / "sistema/node/app.py", ROOT / "sistema/node/dedicated_inference.py", ROOT / "sistema/node/inference.py")}}
    save(manifest_path, manifest)
    stop = threading.Event()
    def monitor():
        fields = ("elapsed_s", "timestamp_gpu", "gpu_used_mib", "gpu_total_mib", "temperature_c", "gpu_util_pct", "power_w", "clock_mhz", "thermal_slowdown", "ram_total_mib", "ram_free_mib", "page_free_mib")
        with (output / "telemetria.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            while not stop.is_set():
                try:
                    writer.writerow({"elapsed_s": time.perf_counter() - started, **gpu(), **memory()})
                    stream.flush()
                except Exception as exc:
                    print("TELEMETRIA", str(exc), flush=True)
                stop.wait(5)
    monitoring = threading.Thread(target=monitor, daemon=True)
    monitoring.start()
    nodes, processes, logs, rows = [], [], [], []
    try:
        for index in range(2):
            identifier = f"node-{index}"
            local_port = port()
            log = (output / f"{identifier}.log").open("w", encoding="utf-8")
            logs.append(log)
            env = dict(os.environ, NODE_ID=identifier, PROFILE="honest", INFERENCE_MODE="model",
                       MODEL_NAME=snapshot, MODEL_QUANTIZATION="nf4", MODEL_DEVICE="cuda",
                       MODEL_RUN_ID=output.name, MODEL_REVISION=revision, MODEL_CACHE_DIR=str(output / identifier),
                       MODEL_MAX_NEW_TOKENS="256", MODEL_TEMPERATURE="0.7", MODEL_TOP_P="0.95",
                       EXPERIMENT_SEED="0", PEERS="", NEIGHBORS="", COLLUDERS="", CUDA_VISIBLE_DEVICES="0",
                       OMP_NUM_THREADS="1", TOKENIZERS_PARALLELISM="false", HF_HUB_OFFLINE="1",
                       TRANSFORMERS_OFFLINE="1", PYTHONUNBUFFERED="1")
            load_started = time.perf_counter()
            child = subprocess.Popen([sys.executable, "-m", "uvicorn", "sistema.node.app:app", "--host", "127.0.0.1",
                                      "--port", str(local_port), "--workers", "1"], cwd=ROOT, env=env,
                                     stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            processes.append(child)
            node = {"node_id": identifier, "url": f"http://127.0.0.1:{local_port}", "pid": child.pid}
            nodes.append(node)
            until = min(deadline, time.monotonic() + 300)
            while time.monotonic() < until:
                if child.poll() is not None:
                    raise RuntimeError(f"{identifier} encerrou; consulte seu log")
                try:
                    health = request(node["url"] + "/health", timeout=2)
                    if health.get("model_loaded") is True and health.get("model_instances") == 1:
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(.5)
            else:
                raise TimeoutError(f"Modelo de {identifier} não ficou pronto")
            manifest["loads"].append({**node, "load_s": time.perf_counter() - load_started,
                                      "memory": memory(), "gpu": gpu()})
            save(manifest_path, manifest)
            print("MODELO_PRONTO", identifier, round(manifest["loads"][-1]["load_s"], 2), "s", flush=True)
        fields = ("round_index", "node_id", "task_id", "client_wall_s", "model_s", "answer", "correct", "first_pair")
        with (output / "geracoes.csv").open("w", encoding="utf-8", newline="") as stream, ThreadPoolExecutor(max_workers=2) as executor:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for index, task in enumerate(tasks):
                if time.monotonic() >= deadline - 240:
                    raise TimeoutError("Prazo do piloto esgotado")
                pair_start = time.perf_counter()
                futures = [executor.submit(infer, node, task, index) for node in nodes]
                pair = []
                for future in as_completed(futures):
                    row = future.result()
                    rows.append(row)
                    pair.append(row)
                    writer.writerow(row)
                    stream.flush()
                manifest["pairs"].append({"round_index": index, "task_id": task["id"], "wall_s": time.perf_counter() - pair_start,
                                           "generations": pair})
                save(manifest_path, manifest)
                print(f"QUESTAO {index+1}/{rounds} TEMPO_PAR {manifest['pairs'][-1]['wall_s']:.2f}s GERACOES {len(rows)}/{2*rounds}", flush=True)
        manifest["verified_caches"] = verify(output, nodes, rounds)
        manifest["summary"] = aggregate(rows, manifest["pairs"], time.perf_counter() - started,
                                         sum(item["load_s"] for item in manifest["loads"]))
        manifest["status"] = "concluido"
    except BaseException as exc:
        manifest.update(status="falhou", error=f"{type(exc).__name__}: {exc}")
        print("FALHA", manifest["error"], flush=True)
    finally:
        for child in processes:
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)
        for log in logs:
            log.close()
        stop.set()
        monitoring.join(timeout=15)
        try:
            manifest["gpu_after"] = gpu()
            manifest["memory_after"] = memory()
        except Exception as exc:
            # Uma falha de telemetria depois de liberar os modelos não deve
            # apagar o resultado ou deixar o manifesto em andamento.
            manifest["telemetry_cleanup_warning"] = f"{type(exc).__name__}: {exc}"
        manifest["elapsed_including_cleanup_s"] = time.perf_counter() - started
        manifest["end_utc"] = datetime.now(timezone.utc).isoformat()
        save(manifest_path, manifest)
    print("RESULTADO", manifest["status"], str(output), flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--questoes", type=int, default=50)
    args = parser.parse_args()
    return 0 if run(args.saida, rounds=args.questoes)["status"] == "concluido" else 1


if __name__ == "__main__":
    raise SystemExit(main())
