"""SmolLM3-3B em redes maiores que a do artigo.

Cada rodada usa uma pergunta nova do GSM8K. O modelo responde uma vez por
pergunta; os nós honestos reutilizam essa resposta. Maliciosos votam 999.

Uso::

    .venv/bin/python -m sistema.scripts.run_com_smol_escala
"""
from __future__ import annotations

import csv
import json
import os
import time

from sistema.core.answer import normalize
from sistema.core.dataset import load_gsm8k
from sistema.node.inference import ModelBackend
from sistema.scripts.run_a3_n50 import _args
from sistema.simulate import run_simulation

ROUNDS = 100
QUESTIONS = 100
SIZES = (100, 200)
FRACTIONS = (0.0, 0.25, 0.5, 0.65)
MODEL = "HuggingFaceTB/SmolLM3-3B"
_BASE = os.path.join(
    os.path.dirname(__file__), "..", "resultados", "fora_do_artigo", "smol_escala",
)


def _solve(tasks: list[dict]) -> dict:
    print(f"Carregando {MODEL} ...", flush=True)
    started = time.perf_counter()
    backend = ModelBackend(MODEL, max_new_tokens=256)
    print(f"Dispositivo: {backend.device} ({time.perf_counter() - started:.1f}s)", flush=True)
    answers: dict = {}
    rows = []
    correct = 0
    for index, task in enumerate(tasks, start=1):
        t0 = time.perf_counter()
        predicted = normalize(backend.solve(task["question"]))
        elapsed = time.perf_counter() - t0
        expected = normalize(task["answer"])
        ok = predicted is not None and predicted == expected
        correct += int(ok)
        answers[task["id"]] = predicted
        rows.append({
            "id": task["id"],
            "esperado": expected,
            "previsto": predicted,
            "acerto": int(ok),
            "segundos": round(elapsed, 2),
        })
        print(
            f"[{'OK' if ok else 'ERR'}] {index}/{len(tasks)} esperado={expected} "
            f"previsto={predicted} ({elapsed:.1f}s) acerto={correct}/{index}",
            flush=True,
        )
    os.makedirs(_BASE, exist_ok=True)
    path = os.path.join(_BASE, "respostas_smol.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"acerto": correct, "total": len(rows), "itens": rows}, handle, ensure_ascii=False, indent=2)
    print(f"Smol no GSM8K: {correct}/{len(rows)}. Arquivo: {path}", flush=True)
    return answers


def _run_network(tasks: list[dict], model_answers: dict) -> None:
    runs = os.path.join(_BASE, "runs")
    os.makedirs(runs, exist_ok=True)
    proof = os.path.join(_BASE, "rede.csv")
    fields = [
        "experiment_id", "label", "nodes", "rounds", "malicious_pct", "malicious_nodes",
        "seed", "test_weighted", "wall_s",
    ]
    with open(proof, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for nodes in SIZES:
            for frac in FRACTIONS:
                pct = int(round(frac * 100))
                attack = "forge" if frac > 0 else "none"
                n_mal = round(frac * nodes)
                cells = [
                    ("fixo_hibrido", "fixed", "hybrid", "none", "star", "none"),
                    ("dinamico_hibrido", "dynamic", "hybrid", "all", "kregular", attack),
                ]
                if frac in (0.5, 0.65):
                    cells.append(("dinamico_so_consenso", "dynamic", "consensus", "all", "kregular", attack))
                for label, orch, signal, defense, topology, leader in cells:
                    exp_id = f"smol_n{nodes}_r{ROUNDS}_{label}_m{pct:02d}_s00"
                    args = _args(
                        exp_id,
                        nodes=nodes,
                        rounds=ROUNDS,
                        malicious=frac,
                        seed=0,
                        orchestration=orch,
                        signal=signal,
                        defense=defense,
                        topology=topology,
                        leader_attack=leader,
                        output=runs,
                    )
                    args.tasks = tasks
                    args.model_answers = model_answers
                    started = time.perf_counter()
                    summary = run_simulation(args)
                    elapsed = time.perf_counter() - started
                    row = {
                        "experiment_id": exp_id,
                        "label": label,
                        "nodes": nodes,
                        "rounds": ROUNDS,
                        "malicious_pct": pct,
                        "malicious_nodes": n_mal,
                        "seed": 0,
                        "test_weighted": summary.get("consensus_accuracy_weighted_on_tests", ""),
                        "wall_s": round(elapsed, 2),
                    }
                    writer.writerow(row)
                    handle.flush()
                    print(
                        f"n={nodes} {label} {pct}% ({n_mal} maliciosos): "
                        f"teste={float(row['test_weighted']):.3f} parede={row['wall_s']:.2f}s",
                        flush=True,
                    )


def main() -> None:
    print(f"Baixando {QUESTIONS} perguntas do GSM8K ...", flush=True)
    tasks = load_gsm8k(split="test", limit=QUESTIONS)
    if len(tasks) < ROUNDS:
        raise SystemExit(f"GSM8K devolveu {len(tasks)} perguntas para {ROUNDS} rodadas.")
    _run_network(tasks[:ROUNDS], _solve(tasks[:ROUNDS]))


if __name__ == "__main__":
    main()
