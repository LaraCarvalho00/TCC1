"""Roda os três cenários combinados na orientação, em rede pequena.

(i) honestos vs maliciosos (com conluio)
(ii) honestos vs instáveis
(iii) honestos vs maliciosos vs instáveis (ainda com maioria honesta)

Uso:
    python -m sistema.scripts.run_scenarios
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from types import SimpleNamespace

from ..simulate import run_simulation

_ROOT = os.path.join(os.path.dirname(__file__), "..", "results", "cenarios")

# 6 nós: estresse baixo o bastante para o hardware da equipe e para sobrar
# maioria honesta mesmo no cenário misto.
SCENARIOS = (
    {
        "name": "honest_vs_malicious",
        "nodes": 6,
        "malicious": 2 / 6,
        "unstable": 0.0,
        "collusion_value": 999,
    },
    {
        "name": "honest_vs_unstable",
        "nodes": 6,
        "malicious": 0.0,
        "unstable": 2 / 6,
        "collusion_value": None,
    },
    {
        "name": "honest_vs_malicious_vs_unstable",
        "nodes": 6,
        "malicious": 2 / 6,
        "unstable": 1 / 6,
        "collusion_value": 999,
    },
    {
        "name": "collusion_50pct",
        "nodes": 6,
        "malicious": 0.5,
        "unstable": 0.0,
        "collusion_value": 999,
    },
)


def _args_for(scenario: dict, rounds: int, seed: int, alpha: float, min_confidence: float) -> SimpleNamespace:
    return SimpleNamespace(
        nodes=scenario["nodes"],
        malicious=scenario["malicious"],
        unstable=scenario["unstable"],
        rounds=rounds,
        alpha=alpha,
        min_confidence=min_confidence,
        seed=seed,
        honest_accuracy=0.9,
        collusion_value=scenario["collusion_value"],
        unstable_p_drop=0.3,
        unstable_p_correct=0.5,
        output=os.path.join(_ROOT, scenario["name"]),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Três cenários da reunião de orientação.")
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--alpha", type=float, default=0.25)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    args = parser.parse_args(argv)

    rows = []
    for scenario in SCENARIOS:
        print(f"\n######## {scenario['name']} ########")
        summary = run_simulation(
            _args_for(scenario, args.rounds, args.seed, args.alpha, args.min_confidence)
        )
        row = {
            "scenario": scenario["name"],
            "nodes": scenario["nodes"],
            "malicious_frac": round(scenario["malicious"], 4),
            "unstable_frac": round(scenario["unstable"], 4),
            "collusion": scenario["collusion_value"] is not None,
            "weighted_acc": summary["consensus_accuracy_weighted"],
            "majority_acc": summary["consensus_accuracy_majority"],
        }
        for profile, value in summary["final_reputation_by_profile"].items():
            row[f"rep_{profile}"] = value
        rows.append(row)

    os.makedirs(_ROOT, exist_ok=True)
    consolidado = os.path.join(_ROOT, "consolidado.csv")
    fieldnames = sorted({key for row in rows for key in row})
    with open(consolidado, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with open(os.path.join(_ROOT, "consolidado.json"), "w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2, ensure_ascii=False)
    print(f"\nConsolidado: {consolidado}")


if __name__ == "__main__":
    main()
