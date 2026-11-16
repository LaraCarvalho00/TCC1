"""Mede modelos NF4 próprios por processo, aumentando a ocupação de uma GPU.

Usa os nós HTTP reais, sem consenso ou Docker. Cada etapa gera respostas novas
em todos os nós residentes. Reservas de memória limitam a busca; o Windows
ainda pode paginar. O resultado é um limite operacional observado.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time

from . import piloto_local as local

ROOT = local.ROOT
MODEL = "Qwen/Qwen3-0.6B"


def snapshot(model, output):
    from huggingface_hub import HfApi, snapshot_download
    info = HfApi().model_info(model)
    path = snapshot_download(model, revision=info.sha, allow_patterns=[
        "*.json", "*.safetensors", "*.txt", "*.model", "*.jinja", "README.md"])
    value = {"model": model, "revision": info.sha, "snapshot": str(Path(path).resolve()),
             "download_complete_utc": datetime.now(timezone.utc).isoformat()}
    local.save(output / "modelo.json", value)
    print("MODELO_DISPONIVEL", json.dumps(value), flush=True)
    return value


def telemetry():
    data = {**local.gpu(), **local.memory()}
    data["gpu_used_mib"] = float(data["gpu_used_mib"])
    data["gpu_total_mib"] = float(data["gpu_total_mib"])
    return data


def admission(sample, additional_gpu_mib, gpu_reserve_mib, ram_reserve_mib, additional_ram_mib=0):
    free_gpu = sample["gpu_total_mib"] - sample["gpu_used_mib"]
    if free_gpu < additional_gpu_mib + gpu_reserve_mib:
        return "reserva_vram", {"free_gpu_mib": free_gpu, "next_gpu_estimate_mib": additional_gpu_mib}
    if sample.get("ram_free_mib", ram_reserve_mib) < ram_reserve_mib + additional_ram_mib:
        return "reserva_ram", {"ram_free_mib": sample.get("ram_free_mib"), "next_ram_estimate_mib": additional_ram_mib}
    if sample.get("page_free_mib", 4096) < 2048:
        return "reserva_memoria_comprometida", {"page_free_mib": sample.get("page_free_mib")}
    return None, {}


def stage_summary(rows, batches):
    if not rows or not batches:
        raise ValueError("Etapa sem gerações completas")
    wall = sum(batch["wall_s"] for batch in batches)
    return {"generations": len(rows), "questions_per_node": len(batches),
            "generation_wall_s": wall, "wall_seconds_per_generation": wall / len(rows),
            "generations_per_hour": len(rows) * 3600 / wall,
            "median_request_s": statistics.median(row["client_wall_s"] for row in rows),
            "max_request_s": max(row["client_wall_s"] for row in rows),
            "parsed_answers": sum(row["answer"] is not None for row in rows),
            "correct_answers": sum(row["correct"] for row in rows),
            "accuracy_descriptive": sum(row["correct"] for row in rows) / len(rows)}


def runtime_files(output, nodes):
    return {node["node_id"]: json.loads((output / node["node_id"] / "model-runtime.json").read_text(encoding="utf-8"))
            for node in nodes}


def verify_rounds(output, nodes, expected):
    from contextlib import closing
    import sqlite3
    report = []
    for node in nodes:
        with closing(sqlite3.connect(f"file:{(output / node['node_id'] / 'inferencias.sqlite').as_posix()}?mode=ro", uri=True)) as db:
            actual = db.execute("SELECT round_index,node_id FROM generations ORDER BY round_index").fetchall()
            submitted = db.execute("SELECT round_index FROM responses ORDER BY round_index").fetchall()
        rounds = expected[node["node_id"]]
        if actual != [(index, node["node_id"]) for index in rounds] or submitted != [(index,) for index in rounds]:
            raise RuntimeError(f"Cache incompleto ou identidade divergente: {node['node_id']}")
        report.append({"node_id": node["node_id"], "generations": len(actual), "responses": len(submitted)})
    return report


def terminate(child):
    if child.poll() is None:
        child.terminate()
    try:
        child.wait(timeout=15)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=10)


def run(args):
    output = args.saida.resolve()
    if not output.is_relative_to((ROOT / "resultados/llm").resolve()):
        raise ValueError("A saída deve ficar dentro de resultados/llm")
    if args.executar_cache:
        model = json.loads((output / "modelo.json").read_text(encoding="utf-8"))
        if (output / "manifesto.json").exists():
            raise FileExistsError("O piloto já foi iniciado nesta pasta; use uma saída nova")
    else:
        output.mkdir(parents=True, exist_ok=False)
        model = snapshot(args.modelo, output)
    if args.somente_download:
        return {"status": "download_concluido", **model}
    task_path = ROOT / "sistema/dados/banco_smol.json"
    all_tasks = json.loads(task_path.read_text(encoding="utf-8"))["tarefas"]
    # Questões com textos/tempos diferentes no piloto anterior; sem gabarito enviado.
    tasks = [all_tasks[index] for index in (0, 2, 8)][:args.questoes]
    started = time.perf_counter()
    deadline = time.monotonic() + args.prazo
    manifest_path = output / "manifesto.json"
    manifest = {"status": "em_andamento", "start_utc": datetime.now(timezone.utc).isoformat(),
                "kind": "capacidade_local_http_modelos_proprios", **model,
                "gpu": "CUDA_VISIBLE_DEVICES=0", "quantization": "nf4", "thinking": False,
                "max_new_tokens": 256, "temperature": .7, "top_p": .95, "seed": 0,
                "max_nodes_requested": args.max_nos, "questions_per_stage": len(tasks),
                "gpu_reserve_mib": args.reserva_gpu, "ram_reserve_mib": args.reserva_ram,
                "task_sha256": hashlib.sha256(task_path.read_bytes()).hexdigest(),
                "environment": {name: importlib.metadata.version(name) for name in
                                ("torch", "transformers", "bitsandbytes", "fastapi", "uvicorn")},
                "baseline": telemetry(), "loads": [], "stages": [],
                "max_loaded_nodes": 0, "max_validated_nodes": 0,
                "limitations": "Processos HTTP Windows, sem Docker ou consenso. Limite observado nesta sessão e nestas questões; busca com reservas de memória. Amostragem global pode perder picos. Picos PyTorch por processo não são picos globais simultâneos.",
                "code_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (Path(__file__), Path(local.__file__), ROOT / "sistema/node/app.py",
                                             ROOT / "sistema/node/dedicated_inference.py", ROOT / "sistema/node/inference.py")}}
    local.save(manifest_path, manifest)
    print("BASELINE", json.dumps(manifest["baseline"]), flush=True)
    stop = threading.Event()
    samples, sample_lock = [], threading.Lock()
    phase = {"stage": 0, "phase": "baseline"}
    def monitor():
        fields = ("elapsed_s", "stage", "phase", "timestamp_gpu", "gpu_used_mib", "gpu_total_mib",
                  "temperature_c", "gpu_util_pct", "power_w", "clock_mhz", "thermal_slowdown",
                  "ram_total_mib", "ram_free_mib", "page_free_mib")
        with (output / "telemetria.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            while not stop.is_set():
                try:
                    sample = {"elapsed_s": time.perf_counter() - started, **phase, **telemetry()}
                    with sample_lock:
                        samples.append(sample)
                    writer.writerow(sample)
                    stream.flush()
                except Exception as exc:
                    print("TELEMETRIA_FALHOU", str(exc), flush=True)
                stop.wait(1)
    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    nodes, processes, logs, expected, rows = [], [], [], {}, []
    next_gpu_mib, next_ram_mib = 1536, 384
    fields = ("stage", "round_index", "node_id", "task_id", "client_wall_s", "model_s", "answer", "correct", "first_pair")
    try:
        with (output / "geracoes.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for count in range(1, args.max_nos + 1):
                if time.monotonic() > deadline - 300:
                    manifest["stop_reason"] = "prazo"
                    break
                before = telemetry()
                reason, details = admission(before, next_gpu_mib, args.reserva_gpu, args.reserva_ram, next_ram_mib)
                if reason:
                    manifest.update(stop_reason=reason, stop_details=details, next_stage_not_attempted=count)
                    print("LIMITE_PREVENTIVO", count, reason, json.dumps(details), flush=True)
                    break
                phase.update(stage=count, phase="loading")
                identifier = f"node-{count-1}"
                node = {"node_id": identifier, "url": f"http://127.0.0.1:{local.port()}"}
                log = (output / f"{identifier}.log").open("w", encoding="utf-8")
                logs.append(log)
                env = dict(os.environ, NODE_ID=identifier, PROFILE="honest", INFERENCE_MODE="model",
                           MODEL_NAME=model["snapshot"], MODEL_QUANTIZATION="nf4", MODEL_DEVICE="cuda",
                           MODEL_RUN_ID=output.name, MODEL_REVISION=model["revision"], MODEL_CACHE_DIR=str(output / identifier),
                           MODEL_MAX_NEW_TOKENS="256", MODEL_TEMPERATURE="0.7", MODEL_TOP_P="0.95",
                           EXPERIMENT_SEED="0", PEERS="", NEIGHBORS="", COLLUDERS="", CUDA_VISIBLE_DEVICES="0",
                           OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", TOKENIZERS_PARALLELISM="false",
                           HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONUNBUFFERED="1")
                load_started = time.perf_counter()
                child = subprocess.Popen([sys.executable, "-m", "uvicorn", "sistema.node.app:app", "--host", "127.0.0.1",
                                          "--port", node["url"].rsplit(":", 1)[1], "--workers", "1"], cwd=ROOT,
                                         env=env, stdout=log, stderr=subprocess.STDOUT,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                processes.append(child)
                node["pid"] = child.pid
                nodes.append(node)
                expected[identifier] = []
                until = min(deadline, time.monotonic() + 300)
                while time.monotonic() < until:
                    if child.poll() is not None:
                        raise RuntimeError(f"{identifier} encerrou ao carregar: consulte seu log")
                    try:
                        health = local.request(node["url"] + "/health", timeout=2)
                        if health.get("model_loaded") is True and health.get("model_instances") == 1:
                            break
                    except (OSError, ValueError):
                        pass
                    time.sleep(.5)
                else:
                    raise TimeoutError(f"Carga de {identifier} excedeu prazo")
                after = telemetry()
                manifest["max_loaded_nodes"] = count
                manifest["loads"].append({**node, "load_s": time.perf_counter() - load_started,
                                          "before": before, "after": after})
                local.save(manifest_path, manifest)
                print("MODELO_PRONTO", identifier, "VRAM_MIB", after["gpu_used_mib"], "RAM_LIVRE_MIB", after.get("ram_free_mib"), flush=True)
                phase.update(phase="generation")
                stage_rows, batches = [], []
                with ThreadPoolExecutor(max_workers=count) as executor:
                    for task_index, task in enumerate(tasks):
                        if time.monotonic() > deadline - 240:
                            raise TimeoutError("Prazo do piloto durante geração")
                        round_index = (count - 1) * len(tasks) + task_index
                        batch_started = time.perf_counter()
                        batch_rows = []
                        futures = [executor.submit(local.infer, current, task, round_index) for current in nodes]
                        for future in as_completed(futures):
                            row = {"stage": count, **future.result()}
                            rows.append(row)
                            stage_rows.append(row)
                            batch_rows.append(row)
                            expected[row["node_id"]].append(round_index)
                            writer.writerow(row)
                            stream.flush()
                        batches.append({"round_index": round_index, "task_id": task["id"],
                                        "wall_s": time.perf_counter() - batch_started, "generations": batch_rows})
                        print("LOTE", count, task_index + 1, "TEMPO_S", round(batches[-1]["wall_s"], 3), flush=True)
                verified = verify_rounds(output, nodes, expected)
                ending = telemetry()
                with sample_lock:
                    measured = [sample for sample in samples if sample["stage"] == count]
                used = [sample["gpu_used_mib"] for sample in measured] + [after["gpu_used_mib"], ending["gpu_used_mib"]]
                free_ram = [sample["ram_free_mib"] for sample in measured if "ram_free_mib" in sample]
                stage = {"nodes": count, "status": "validated", "batches": batches,
                         "summary": stage_summary(stage_rows, batches), "verified_caches": verified,
                         "gpu_peak_sampled_mib": max(used), "end": ending,
                         "ram_min_free_mib": min(free_ram) if free_ram else None,
                         "runtime_per_node": runtime_files(output, nodes)}
                stage["reserves_preserved"] = (
                    ending["gpu_total_mib"] - max(used) >= args.reserva_gpu
                    and (not free_ram or min(free_ram) >= args.reserva_ram))
                manifest["stages"].append(stage)
                manifest["max_validated_nodes"] = count
                if stage["reserves_preserved"]:
                    manifest["max_validated_nodes_with_reserves"] = count
                next_gpu_mib = max(1024, after["gpu_used_mib"] - before["gpu_used_mib"]) + 256
                next_ram_mib = max(384, before.get("ram_free_mib", 0) - ending.get("ram_free_mib", 0)) + 128
                local.save(manifest_path, manifest)
                print("ETAPA_VALIDADA", count, "PICO_VRAM_MIB", max(used), "GERACOES", len(stage_rows),
                      "GERACOES_H", round(stage["summary"]["generations_per_hour"], 2), flush=True)
                reason, details = admission(ending, 0, args.reserva_gpu, args.reserva_ram)
                if reason:
                    manifest.update(stop_reason=reason, stop_details=details, next_stage_not_attempted=count + 1)
                    break
            else:
                manifest["stop_reason"] = "max_nos_solicitado"
        manifest["verified_caches_final"] = verify_rounds(output, nodes, expected)
        manifest["status"] = "concluido" if manifest["max_validated_nodes"] else "sem_etapa_validada"
    except BaseException as exc:
        manifest.update(status="interrompido", error=f"{type(exc).__name__}: {exc}", stop_reason="erro")
        print("FALHA", manifest["error"], flush=True)
    finally:
        phase.update(phase="cleanup")
        cleanup_errors = []
        for child in processes:
            try:
                terminate(child)
            except Exception as exc:
                cleanup_errors.append({"pid": child.pid, "error": f"{type(exc).__name__}: {exc}"})
        for log in logs:
            log.close()
        stop.set()
        monitor_thread.join(timeout=15)
        manifest["child_pids"] = [child.pid for child in processes]
        manifest["children_stopped"] = all(child.poll() is not None for child in processes)
        if cleanup_errors:
            manifest["cleanup_errors"] = cleanup_errors
        try:
            manifest["after_cleanup"] = telemetry()
        except Exception as exc:
            manifest["cleanup_telemetry_error"] = str(exc)
        manifest["elapsed_s"] = time.perf_counter() - started
        manifest["end_utc"] = datetime.now(timezone.utc).isoformat()
        local.save(manifest_path, manifest)
    print("RESULTADO", manifest["status"], "NOS_VALIDADOS", manifest["max_validated_nodes"], str(output), flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--modelo", default=MODEL)
    parser.add_argument("--max-nos", type=int, default=8)
    parser.add_argument("--questoes", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--reserva-gpu", type=int, default=768, help="Reserva operacional de VRAM, em MiB")
    parser.add_argument("--reserva-ram", type=int, default=768, help="Reserva física mínima, em MiB")
    parser.add_argument("--prazo", type=int, default=3600)
    parser.add_argument("--somente-download", action="store_true")
    parser.add_argument("--executar-cache", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.max_nos <= 16 or min(args.reserva_gpu, args.reserva_ram) < 512 or args.prazo < 600:
        parser.error("Use 1–16 nós, reservas de pelo menos 512 MiB e prazo de pelo menos 600 s")
    return 0 if run(args)["status"] in ("concluido", "download_concluido") else 1


if __name__ == "__main__":
    raise SystemExit(main())
