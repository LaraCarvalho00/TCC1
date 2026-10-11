"""Grade do A3: 50 nós, sinal híbrido, rodadas de validação fixas.

Não repete a matriz do Allan (7, 10, 20, 60 e 120). Mede três colunas:

* fixo + híbrido, sem as defesas do protocolo dinâmico: o gabarito entra só
  nas rodadas de teste (10, 20, 30, 40 e 50);
* dinâmico + híbrido + todas as defesas, líder que forja, grafo 4-regular;
* dinâmico só com consenso, nas frações 50% e 65%, para mostrar o papel da
  Rodada de Validação.

Uso::

    python -m sistema.scripts.run_a3_n50
"""
from __future__ import annotations

import argparse
import csv
import os
import time

from sistema.simulate import run_simulation

_BASE = os.path.join(os.path.dirname(__file__), "..", "resultados", "a3_n50")
_FRACTIONS = (0.0, 0.25, 0.5, 0.65)
_SEEDS = range(5)


def _args(exp_id: str, **overrides) -> argparse.Namespace:
    values = dict(
        nodes=50,
        malicious=0.0,
        unstable=0.0,
        rounds=50,
        alpha=0.3,
        seed=0,
        honest_accuracy=0.9,
        collusion_value=None,
        unstable_p_drop=0.3,
        unstable_p_correct=0.5,
        mechanism="ema",
        alpha_down=None,
        initial_reputation=0.5,
        output=_BASE,
        experiment_id=exp_id,
        overwrite=True,
        test_every=10,
        row_sync=False,
        quiet=True,
        orchestration="fixed",
        signal="hybrid",
        topology="star",
        degree=4,
        leader_attack="none",
        auditor_attack="none",
        defense="none",
        calibration_rounds=None,
        consensus_alpha=None,
        oracle_alpha=None,
        split_alpha=False,
        oracle_bypasses_quorum=False,
        split_scores=False,
        refuse_forged=False,
    )
    values.update(overrides)
    if values["malicious"] > 0 and values["collusion_value"] is None:
        values["collusion_value"] = 999
    return argparse.Namespace(**values)


def _cells() -> list[dict]:
    cells = []
    for frac in _FRACTIONS:
        for seed in _SEEDS:
            mal = int(round(frac * 100))
            cells.append(dict(
                label="fixo_hibrido",
                exp_id=f"a3_n50_fixo_hibrido_m{mal:02d}_s{seed:02d}",
                malicious=frac, seed=seed,
                orchestration="fixed", signal="hybrid", defense="none",
                topology="star", leader_attack="none",
            ))
            attack = "forge" if frac > 0 else "none"
            cells.append(dict(
                label="dinamico_hibrido",
                exp_id=f"a3_n50_dinamico_hibrido_m{mal:02d}_s{seed:02d}",
                malicious=frac, seed=seed,
                orchestration="dynamic", signal="hybrid", defense="all",
                topology="kregular", leader_attack=attack,
            ))
            if frac in (0.5, 0.65):
                cells.append(dict(
                    label="dinamico_so_consenso",
                    exp_id=f"a3_n50_dinamico_consenso_m{mal:02d}_s{seed:02d}",
                    malicious=frac, seed=seed,
                    orchestration="dynamic", signal="consensus", defense="all",
                    topology="kregular", leader_attack=attack,
                ))
    return cells


def _row(cell: dict, summary: dict, elapsed: float) -> dict:
    final = summary.get("final_reputation_by_profile", {})
    return {
        "experiment_id": cell["exp_id"],
        "label": cell["label"],
        "nodes": 50,
        "malicious_frac": cell["malicious"],
        "seed": cell["seed"],
        "orchestration": cell["orchestration"],
        "signal": cell["signal"],
        "defense": cell["defense"],
        "topology": cell["topology"],
        "leader_attack": cell["leader_attack"],
        "mechanism": "ema",
        "alpha": 0.3,
        "consensus_accuracy_weighted": summary.get("consensus_accuracy_weighted", ""),
        "consensus_accuracy_majority": summary.get("consensus_accuracy_majority", ""),
        "consensus_accuracy_weighted_on_tests": summary.get("consensus_accuracy_weighted_on_tests", ""),
        "consensus_accuracy_majority_on_tests": summary.get("consensus_accuracy_majority_on_tests", ""),
        "final_rep_honest": final.get("honest", ""),
        "final_rep_malicious": final.get("malicious", ""),
        "elapsed_s": round(elapsed, 2),
    }


def main() -> None:
    os.makedirs(_BASE, exist_ok=True)
    cells = _cells()
    rows = []
    started = time.perf_counter()
    for index, cell in enumerate(cells, start=1):
        args = _args(cell["exp_id"], **{k: cell[k] for k in (
            "malicious", "seed", "orchestration", "signal", "defense", "topology", "leader_attack",
        )})
        t0 = time.perf_counter()
        summary = run_simulation(args)
        elapsed = time.perf_counter() - t0
        rows.append(_row(cell, summary, elapsed))
        print(
            f"[{index:>2}/{len(cells)}] {cell['label']} m={cell['malicious']:.2f} s={cell['seed']} "
            f"teste={summary.get('consensus_accuracy_weighted_on_tests', 0):.3f} "
            f"({elapsed:.1f}s)",
            flush=True,
        )
    index_path = os.path.join(_BASE, "indice.csv")
    with open(index_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} execuções em {time.perf_counter() - started:.0f}s")
    print(f"Índice: {index_path}")


if __name__ == "__main__":
    main()
