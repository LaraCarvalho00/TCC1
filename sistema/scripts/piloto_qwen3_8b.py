"""Piloto 50 questões × 2 nós lógicos com **uma** cópia NF4 de Qwen3-8B.

Nesta RTX 4060 Laptop (8 GiB) não cabem duas réplicas de 8B. Os nós
``node-0`` e ``node-1`` compartilham o mesmo processo, em série, com as
mesmas 50 primeiras tarefas GSM8K, temperatura 0,7, top-p 0,95, 256 tokens
e a semente ``0:rodada:node_id`` do piloto Smol. Sem consenso, Docker ou gabarito no prompt.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

from sistema.scripts.piloto_local import gpu, memory, save

ROOT = Path(__file__).resolve().parents[2]
MODEL = "Qwen/Qwen3-8B"
LOCAL_MODEL = ROOT / ".cache" / "Qwen3-8B"
NODES = ("node-0", "node-1")
WEIGHT_FILES = {
    "model-00001-of-00005.safetensors": 3996250744,
    "model-00002-of-00005.safetensors": 3993160032,
    "model-00003-of-00005.safetensors": 3959604768,
    "model-00004-of-00005.safetensors": 3187841392,
    "model-00005-of-00005.safetensors": 1244659840,
    "tokenizer.json": 11422654,
}


def model_ready(path: Path) -> bool:
    return all((path / name).is_file() and (path / name).stat().st_size == size for name, size in WEIGHT_FILES.items())


def ensure_model() -> Path:
    if model_ready(LOCAL_MODEL):
        return LOCAL_MODEL
    from huggingface_hub import snapshot_download
    snapshot_download(MODEL, local_dir=str(LOCAL_MODEL), local_dir_use_symlinks=False)
    if not model_ready(LOCAL_MODEL):
        raise FileNotFoundError(f"Pesos incompletos em {LOCAL_MODEL}")
    return LOCAL_MODEL


def gateway_seed(experiment_seed: int, round_index: int, node_id: str) -> int:
    encoded = f"{int(experiment_seed)}:{round_index}:{node_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big") & ((1 << 63) - 1)


def run(output, *, rounds=50, deadline_seconds=14400):
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
    snapshot = ensure_model()
    revision = snapshot.name
    manifest_path = output / "manifesto.json"
    env = {}
    for name in ("torch", "transformers", "bitsandbytes"):
        try:
            env[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            env[name] = None
    manifest = {
        "status": "em_andamento",
        "start_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "piloto_local_qwen3_8b_compartilhado",
        "model": MODEL,
        "revision": revision,
        "nodes": 2,
        "logical_nodes": list(NODES),
        "resident_models": 1,
        "questions": rounds,
        "planned_generations": 2 * rounds,
        "quantization": "nf4",
        "max_new_tokens": 256,
        "temperature": 0.7,
        "top_p": 0.95,
        "seed": 0,
        "thinking": False,
        "task_sha256": hashlib.sha256(task_path.read_bytes()).hexdigest(),
        "environment": env,
        "memory_before": memory(),
        "gpu_before": gpu(),
        "pairs": [],
        "limitations": (
            "Uma LLM NF4 residente; dois nós lógicos em série no mesmo processo. "
            "Não equivale a 20 modelos, nem ao piloto Smol de duas cópias simultâneas. "
            "Sem consenso. Comparação com Smol 79/100 é descritiva."
        ),
        "code_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__), ROOT / "sistema/node/inference.py")
        },
    }
    save(manifest_path, manifest)
    rows = []
    try:
        from sistema.node.inference import ModelBackend
        load_started = time.perf_counter()
        backend = ModelBackend(str(snapshot), device="cuda", max_new_tokens=256, quantization="nf4")
        manifest["load_s"] = time.perf_counter() - load_started
        manifest["gpu_after_load"] = gpu()
        save(manifest_path, manifest)
        print("MODELO_PRONTO", round(manifest["load_s"], 2), "s", flush=True)
        fields = ("round_index", "node_id", "task_id", "seed", "model_s", "answer", "correct", "has_hash_marker")
        with (output / "geracoes.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            jsonl = (output / "geracoes.jsonl").open("w", encoding="utf-8")
            try:
                for index, task in enumerate(tasks):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Prazo do piloto esgotado")
                    pair_start = time.perf_counter()
                    pair = []
                    for node_id in NODES:
                        seed = gateway_seed(0, index, node_id)
                        gen_start = time.perf_counter()
                        answer, text = backend.sample(
                            task["question"], temperature=0.7, top_p=0.95, seed=seed
                        )
                        row = {
                            "round_index": index,
                            "node_id": node_id,
                            "task_id": task["id"],
                            "seed": seed,
                            "model_s": time.perf_counter() - gen_start,
                            "answer": answer,
                            "correct": int(answer == task["answer"]),
                            "has_hash_marker": int("####" in (text or "")),
                        }
                        rows.append(row)
                        pair.append(row)
                        writer.writerow(row)
                        stream.flush()
                        jsonl.write(json.dumps({"text": text, **row}, ensure_ascii=False) + "\n")
                        jsonl.flush()
                    manifest["pairs"].append({
                        "round_index": index,
                        "task_id": task["id"],
                        "wall_s": time.perf_counter() - pair_start,
                        "generations": pair,
                    })
                    save(manifest_path, manifest)
                    done = len(rows)
                    print(
                        f"QUESTAO {index+1}/{rounds} TEMPO_PAR {manifest['pairs'][-1]['wall_s']:.2f}s "
                        f"GERACOES {done}/{2*rounds} ACERTOS {sum(r['correct'] for r in rows)}/{done}",
                        flush=True,
                    )
            finally:
                jsonl.close()
        n = len(rows)
        manifest["summary"] = {
            "generations": n,
            "questions": rounds,
            "correct": sum(r["correct"] for r in rows),
            "accuracy_descriptive": sum(r["correct"] for r in rows) / n if n else None,
            "without_hash_marker": sum(1 - r["has_hash_marker"] for r in rows),
            "load_s": manifest["load_s"],
            "generation_wall_s": time.perf_counter() - started - manifest["load_s"],
            "median_model_s": sorted(r["model_s"] for r in rows)[n // 2] if n else None,
            "smol_piloto_reference_correct": 79,
            "smol_piloto_reference_n": 100,
            "beats_smol_piloto": (
                (sum(r["correct"] for r in rows) / n) > 0.79 if n == 100 else None
            ),
        }
        manifest["status"] = "concluido"
    except BaseException as exc:
        manifest.update(status="falhou", error=f"{type(exc).__name__}: {exc}")
        print("FALHA", manifest["error"], flush=True)
    finally:
        try:
            manifest["gpu_after"] = gpu()
            manifest["memory_after"] = memory()
        except Exception as exc:
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
