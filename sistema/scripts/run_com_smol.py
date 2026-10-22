"""Roda o protocolo do artigo com as respostas do SmolLM3-3B.

O modelo é carregado uma vez e responde cada pergunta da amostra offline.
A decodificação é gulosa, então a resposta de uma pergunta não muda entre nós:
todo nó honesto usa essa resposta. O malicioso, quando há conluio, continua
votando 999. A rede é a do artigo: 50 nós, 50 rodadas, gabarito só na validação.

Uso::

    python3.12 -m sistema.scripts.run_com_smol
"""
from __future__ import annotations

import csv
import json
import os
import time

from sistema.core.answer import normalize
from sistema.core.dataset import load_sample
from sistema.node.inference import ModelBackend
from sistema.scripts.run_a3_n50 import _args
from sistema.simulate import run_simulation

NODES = 50
ROUNDS = 50
FRACTIONS = (0.0, 0.25, 0.5, 0.65)
MODEL = "HuggingFaceTB/SmolLM3-3B"
_BASE = os.path.join(
    os.path.dirname(__file__), "..", "resultados", "fora_do_artigo", "smol_n50",
)


def _solve() -> dict[str, int | None]:
    tasks = load_sample()
    print(f"Carregando {MODEL} ...", flush=True)
    started = time.perf_counter()
    backend = ModelBackend(MODEL, max_new_tokens=256)
    print(f"Dispositivo: {backend.device} ({time.perf_counter() - started:.1f}s)", flush=True)
    answers: dict[str, int | None] = {}
    rows = []
    for index, task in enumerate(tasks, start=1):
        t0 = time.perf_counter()
        predicted = normalize(backend.solve(task["question"]))
        elapsed = time.perf_counter() - t0
        expected = normalize(task["answer"])
        ok = predicted is not None and predicted == expected
        answers[task["id"]] = predicted
        rows.append({
            "id": task["id"],
            "esperado": expected,
            "previsto": predicted,
            "acerto": int(ok),
            "segundos": round(elapsed, 2),
        })
        print(
            f"[{'OK' if ok else 'ERR'}] {index}/{len(tasks)} {task['id']} "
            f"esperado={expected} previsto={predicted} ({elapsed:.1f}s)",
            flush=True,
        )
    os.makedirs(_BASE, exist_ok=True)
    path = os.path.join(_BASE, "respostas_smol.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)
    correct = sum(row["acerto"] for row in rows)
    print(f"Smol na amostra: {correct}/{len(rows)}. Arquivo: {path}", flush=True)
    return answers


def _run_network(model_answers: dict) -> None:
    runs = os.path.join(_BASE, "runs")
    os.makedirs(runs, exist_ok=True)
    proof = os.path.join(_BASE, "rede.csv")
    fields = [
        "experiment_id", "label", "nodes", "rounds", "malicious_pct", "seed",
        "test_weighted", "wall_s",
    ]
    with open(proof, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for frac in FRACTIONS:
            pct = int(round(frac * 100))
            attack = "forge" if frac > 0 else "none"
            cells = [
                ("fixo_hibrido", "fixed", "hybrid", "none", "star", "none"),
                ("dinamico_hibrido", "dynamic", "hybrid", "all", "kregular", attack),
            ]
            if frac in (0.5, 0.65):
                cells.append(("dinamico_so_consenso", "dynamic", "consensus", "all", "kregular", attack))
            for label, orch, signal, defense, topology, leader in cells:
                exp_id = f"smol_n50_{label}_m{pct:02d}_s00"
                args = _args(
                    exp_id,
                    nodes=NODES,
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
                args.model_answers = model_answers
                started = time.perf_counter()
                summary = run_simulation(args)
                elapsed = time.perf_counter() - started
                row = {
                    "experiment_id": exp_id,
                    "label": label,
                    "nodes": NODES,
                    "rounds": ROUNDS,
                    "malicious_pct": pct,
                    "seed": 0,
                    "test_weighted": summary.get("consensus_accuracy_weighted_on_tests", ""),
                    "wall_s": round(elapsed, 2),
                }
                writer.writerow(row)
                handle.flush()
                print(
                    f"{label} {pct}%: teste={float(row['test_weighted']):.3f} "
                    f"parede={row['wall_s']:.2f}s",
                    flush=True,
                )


def main() -> None:
    _run_network(_solve())


if __name__ == "__main__":
    main()
