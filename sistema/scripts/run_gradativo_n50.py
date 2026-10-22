"""Rodadas gradativas em 50 nós e 50 rodadas.

O script antigo ``graficos_rodadas_gradativo.py`` está fixo em 20 nós.
Este roda um cenário por vez, confere no CSV quantos nós e quantas rodadas
entraram, e só então junta as curvas.

Frações: 0%, 5%, 20%, 35%, 50%, 65% e 80%.
Com maliciosos, todos votam 999.
Fixo: gabarito em toda rodada. Dinâmico: sinal híbrido, grafo 4-regular,
líder que forja e defesas ligadas. Cinco sementes.

Uso::

    python -m sistema.scripts.run_gradativo_n50
    python -m sistema.scripts.run_gradativo_n50 --only-first
"""
from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict

from sistema.simulate import parse_args, run_simulation

NODES = 50
ROUNDS = 50
SEEDS = (0, 1, 2, 3, 4)
PERCENTS = (0, 5, 20, 35, 50, 65, 80)
TEST_ROUNDS = (10, 20, 30, 40, 50)

_BASE = os.path.join(
    os.path.dirname(__file__), "..", "resultados", "fora_do_artigo", "protocolo_gabarito_toda_rodada",
)
_RUNS = os.path.join(_BASE, "runs")

ORCHESTRATORS = {
    "fixo": ["--orchestration", "fixed", "--signal", "truth"],
    "dinamico": [
        "--orchestration", "dynamic", "--signal", "hybrid", "--topology", "kregular",
        "--degree", "4", "--leader-attack", "forge", "--defense", "all",
    ],
}

SERIES = {
    0: ("#1f77b4", "o", "-"),
    5: ("#2ca02c", "s", "-"),
    20: ("#ff7f0e", "^", "-"),
    35: ("#9467bd", "D", "--"),
    50: ("#d62728", "*", "-"),
    65: ("#8c564b", "P", "--"),
    80: ("#111111", "X", ":"),
}


def _jobs(only_first: bool) -> list[tuple[str, int, int]]:
    jobs = [(orch, pct, seed) for pct in PERCENTS for orch in ORCHESTRATORS for seed in SEEDS]
    return jobs[:1] if only_first else jobs


def _exp_id(orch: str, pct: int, seed: int) -> str:
    return f"n50_r50_{orch}_m{pct:02d}_s{seed:02d}"


def _check(exp_id: str) -> dict:
    folder = os.path.join(_RUNS, exp_id)
    with open(os.path.join(folder, "rounds.csv"), encoding="utf-8", newline="") as handle:
        rounds = list(csv.DictReader(handle))
    with open(os.path.join(folder, "per_node.csv"), encoding="utf-8", newline="") as handle:
        per_node = list(csv.DictReader(handle))
    num_nodes = sorted({row["num_nodes"] for row in rounds})
    node_ids = sorted({row["node_id"] for row in per_node}, key=lambda name: int(name.split("-")[1]))
    round_ids = sorted({int(row["round_index"]) for row in rounds})
    first = [row for row in per_node if row["round_index"] == "0"]
    malicious = sorted(row["node_id"] for row in first if row["profile"] == "malicious")
    if num_nodes != ["50"] or len(node_ids) != 50 or node_ids[0] != "node-0" or node_ids[-1] != "node-49":
        raise SystemExit(f"{exp_id} não tem 50 nós: num_nodes={num_nodes} ids={len(node_ids)}")
    if len(rounds) != 50 or round_ids != list(range(50)):
        raise SystemExit(f"{exp_id} não tem 50 rodadas: {len(rounds)} índices {round_ids[:3]}...{round_ids[-3:]}")
    return {
        "experiment_id": exp_id,
        "nos_no_csv": num_nodes[0],
        "nos_distintos": len(node_ids),
        "primeiro_no": node_ids[0],
        "ultimo_no": node_ids[-1],
        "rodadas": len(rounds),
        "maliciosos": len(malicious),
    }


def _run(orch: str, pct: int, seed: int) -> dict:
    exp_id = _exp_id(orch, pct, seed)
    argv = [
        "--nodes", str(NODES),
        "--malicious", str(pct / 100),
        "--rounds", str(ROUNDS),
        "--seed", str(seed),
        "--mechanism", "ema",
        "--alpha", "0.3",
        "--output", _RUNS,
        "--experiment-id", exp_id,
        "--overwrite",
        "--quiet",
        "--no-row-sync",
        *ORCHESTRATORS[orch],
    ]
    if pct > 0:
        argv += ["--collusion-value", "999"]
    else:
        argv = ["none" if item == "forge" else item for item in argv]
    run_simulation(parse_args(argv))
    checked = _check(exp_id)
    checked.update({"orquestrador": orch, "maliciosos_pct": pct, "semente": seed})
    return checked


def _curves() -> dict[tuple[str, int], list[float]]:
    buckets: dict[tuple[str, int], dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    for pct in PERCENTS:
        for orch in ORCHESTRATORS:
            for seed in SEEDS:
                path = os.path.join(_RUNS, _exp_id(orch, pct, seed), "rounds.csv")
                if not os.path.exists(path):
                    continue
                with open(path, encoding="utf-8", newline="") as handle:
                    for row in csv.DictReader(handle):
                        buckets[(orch, pct)][int(row["round_index"])].append(int(row["consensus_correct"]))
    means = {}
    for key, by_round in buckets.items():
        means[key] = [sum(by_round[i]) / len(by_round[i]) for i in range(50)]
    return means


def _plot(means: dict[tuple[str, int], list[float]]) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = os.path.join(_BASE, "figuras")
    os.makedirs(fig_dir, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.8), sharey=True)
    rounds = list(range(1, 51))
    titles = {"fixo": "Fixo, gabarito em toda rodada", "dinamico": "Dinâmico, híbrido"}
    for ax, orch in zip(axes, ORCHESTRATORS):
        for pct in PERCENTS:
            if (orch, pct) not in means:
                continue
            color, marker, linestyle = SERIES[pct]
            n_mal = round(pct / 100 * NODES)
            ax.plot(
                rounds,
                means[(orch, pct)],
                color=color,
                marker=marker,
                linestyle=linestyle,
                linewidth=1.5,
                markersize=6,
                markevery=(PERCENTS.index(pct), 10),
                label=f"{pct}% ({n_mal} nós)",
            )
        for test in TEST_ROUNDS:
            ax.axvline(test, color="#b0b0b0", linestyle=":", linewidth=0.8)
        ax.set_xlim(0, 50)
        ax.set_ylim(-0.05, 1.08)
        ax.set_xticks([0, 10, 20, 30, 40, 50])
        ax.set_xlabel("Rodada")
        ax.set_title(titles[orch])
        ax.grid(True, linestyle=":", color="#d5d5d5")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[0].set_ylabel("Acerto do consenso ponderado")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.08))
    fig.suptitle("50 nós conferidos no CSV · 50 rodadas · 5 sementes · conluio no valor 999", fontsize=12)
    fig.tight_layout()
    path = os.path.join(fig_dir, "acuracia_por_rodada_n50.png")
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-first", action="store_true")
    parser.add_argument("--plot-only", action="store_true")
    args = parser.parse_args()
    os.makedirs(_RUNS, exist_ok=True)

    if not args.plot_only:
        jobs = _jobs(args.only_first)
        proof_path = os.path.join(_BASE, "comprovacao_nos.csv")
        with open(proof_path, "w", newline="", encoding="utf-8") as handle:
            fields = [
                "experiment_id", "orquestrador", "maliciosos_pct", "semente",
                "nos_no_csv", "nos_distintos", "primeiro_no", "ultimo_no", "rodadas", "maliciosos",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for index, (orch, pct, seed) in enumerate(jobs, start=1):
                checked = _run(orch, pct, seed)
                writer.writerow(checked)
                handle.flush()
                print(
                    f"[{index}/{len(jobs)}] {orch} {pct}% semente {seed}: "
                    f"{checked['nos_distintos']} nós ({checked['primeiro_no']}…{checked['ultimo_no']}), "
                    f"{checked['rodadas']} rodadas, {checked['maliciosos']} maliciosos",
                    flush=True,
                )
        if args.only_first:
            return

    path = _plot(_curves())
    print(f"Gráfico: {path}", flush=True)


if __name__ == "__main__":
    main()
