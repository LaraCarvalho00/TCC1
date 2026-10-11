"""Protocolo do artigo, 50 rodadas, subindo o número de nós.

Começa em 50 nós, com cinco sementes. Se cada execução cabe no tempo,
sobe para 100, 200 e 400 nós, com uma semente. O sinal é o do artigo:
no fixo o gabarito só entra nas rodadas 10, 20, 30, 40 e 50; no dinâmico
as defesas ficam ligadas. Não é o gabarito em toda rodada.

Uso::

    python -m sistema.scripts.run_escala_artigo
"""
from __future__ import annotations

import csv
import os
import time
from collections import defaultdict

from sistema.scripts.run_a3_n50 import _args
from sistema.simulate import run_simulation

ROUNDS = 50
FRACTIONS = (0.0, 0.05, 0.20, 0.35, 0.50, 0.65, 0.80)
# (nós, sementes). O próximo tamanho só começa se a execução anterior coube.
LADDER = ((50, 5), (100, 1), (200, 1), (400, 1))
MAX_RUN_S = 90

_BASE = os.path.join(
    os.path.dirname(__file__), "..", "resultados", "fora_do_artigo", "escala_outros_tamanhos",
)
_RUNS = os.path.join(_BASE, "runs")

SERIES = {
    50: ("#1f77b4", "o", "-"),
    100: ("#ff7f0e", "^", "-"),
    200: ("#2ca02c", "*", "--"),
    400: ("#d62728", "D", ":"),
}


def _exp_id(nodes: int, label: str, pct: int, seed: int) -> str:
    return f"n{nodes}_r50_{label}_m{pct:02d}_s{seed:02d}"


def _cells(nodes: int, seeds: int) -> list[dict]:
    cells = []
    for frac in FRACTIONS:
        pct = int(round(frac * 100))
        attack = "forge" if frac > 0 else "none"
        for seed in range(seeds):
            cells.append(dict(
                label="fixo_hibrido", frac=frac, pct=pct, seed=seed, nodes=nodes,
                orchestration="fixed", signal="hybrid", defense="none",
                topology="star", leader_attack="none",
            ))
            cells.append(dict(
                label="dinamico_hibrido", frac=frac, pct=pct, seed=seed, nodes=nodes,
                orchestration="dynamic", signal="hybrid", defense="all",
                topology="kregular", leader_attack=attack,
            ))
            if frac in (0.50, 0.65):
                cells.append(dict(
                    label="dinamico_so_consenso", frac=frac, pct=pct, seed=seed, nodes=nodes,
                    orchestration="dynamic", signal="consensus", defense="all",
                    topology="kregular", leader_attack=attack,
                ))
    return cells


def _check(folder: str, nodes: int) -> tuple[int, int, int]:
    with open(os.path.join(folder, "rounds.csv"), encoding="utf-8", newline="") as handle:
        rounds = list(csv.DictReader(handle))
    with open(os.path.join(folder, "per_node.csv"), encoding="utf-8", newline="") as handle:
        per_node = list(csv.DictReader(handle))
    num_nodes = sorted({int(row["num_nodes"]) for row in rounds})
    node_ids = {row["node_id"] for row in per_node}
    round_ids = {int(row["round_index"]) for row in rounds}
    malicious = {
        row["node_id"] for row in per_node
        if row["round_index"] == "0" and row["profile"] == "malicious"
    }
    if num_nodes != [nodes] or len(node_ids) != nodes or round_ids != set(range(ROUNDS)):
        raise SystemExit(
            f"{folder} saiu de {nodes} nós e {ROUNDS} rodadas: "
            f"num_nodes={num_nodes} ids={len(node_ids)} rodadas={len(round_ids)}"
        )
    return len(node_ids), len(rounds), len(malicious)


def _run_cell(cell: dict) -> dict:
    exp_id = _exp_id(cell["nodes"], cell["label"], cell["pct"], cell["seed"])
    args = _args(
        exp_id,
        nodes=cell["nodes"],
        rounds=ROUNDS,
        malicious=cell["frac"],
        seed=cell["seed"],
        orchestration=cell["orchestration"],
        signal=cell["signal"],
        defense=cell["defense"],
        topology=cell["topology"],
        leader_attack=cell["leader_attack"],
        output=_RUNS,
    )
    started = time.perf_counter()
    summary = run_simulation(args)
    elapsed = time.perf_counter() - started
    n_nodes, n_rounds, n_mal = _check(os.path.join(_RUNS, exp_id), cell["nodes"])
    return {
        "experiment_id": exp_id,
        "label": cell["label"],
        "nodes": n_nodes,
        "rounds": n_rounds,
        "malicious_pct": cell["pct"],
        "malicious_nodes": n_mal,
        "seed": cell["seed"],
        "test_weighted": summary.get("consensus_accuracy_weighted_on_tests", ""),
        "wall_s": round(elapsed, 2),
    }


def _plot(rows: list[dict]) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    grouped: dict[tuple[str, int, int], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(row["label"], int(row["nodes"]), int(row["malicious_pct"]))].append(float(row["test_weighted"]))

    labels = (
        ("fixo_hibrido", "Fixo, validação a cada 10 rodadas"),
        ("dinamico_hibrido", "Dinâmico, híbrido"),
        ("dinamico_so_consenso", "Dinâmico, sem gabarito"),
    )
    fig, axes = plt.subplots(1, 3, figsize=(12.4, 4.4), sharey=True)
    fracs = [int(round(frac * 100)) for frac in FRACTIONS]
    for ax, (label, title) in zip(axes, labels):
        for nodes, (color, marker, linestyle) in SERIES.items():
            xs, ys = [], []
            for pct in fracs:
                sample = grouped.get((label, nodes, pct))
                if not sample:
                    continue
                xs.append(pct)
                ys.append(sum(sample) / len(sample))
            if xs:
                ax.plot(xs, ys, color=color, marker=marker, linestyle=linestyle, linewidth=1.5, label=f"{nodes} nós")
        ax.set_title(title)
        ax.set_xlabel("Maliciosos (%)")
        ax.set_xticks(fracs)
        ax.set_ylim(-0.05, 1.08)
        ax.grid(True, linestyle=":", color="#d5d5d5")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[0].set_ylabel("Acurácia nas rodadas de teste")
    handles, labels_legend = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels_legend, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.08))
    fig.suptitle("Protocolo do artigo · 50 rodadas · nós conferidos no CSV de cada execução", fontsize=12)
    fig.tight_layout()
    fig_dir = os.path.join(_BASE, "figuras")
    os.makedirs(fig_dir, exist_ok=True)
    path = os.path.join(fig_dir, "acuracia_teste_por_tamanho.png")
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def main() -> None:
    os.makedirs(_RUNS, exist_ok=True)
    rows: list[dict] = []
    proof = os.path.join(_BASE, "comprovacao.csv")
    fields = [
        "experiment_id", "label", "nodes", "rounds", "malicious_pct", "malicious_nodes",
        "seed", "test_weighted", "wall_s",
    ]
    with open(proof, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        stop = False
        for nodes, seeds in LADDER:
            if stop:
                print(f"Não subi para {nodes} nós: a execução anterior passou de {MAX_RUN_S}s.", flush=True)
                break
            cells = _cells(nodes, seeds)
            print(f"\n== {nodes} nós, {ROUNDS} rodadas, {seeds} semente(s), {len(cells)} execuções ==", flush=True)
            for index, cell in enumerate(cells, start=1):
                row = _run_cell(cell)
                rows.append(row)
                writer.writerow(row)
                handle.flush()
                print(
                    f"[{index:>2}/{len(cells)}] {cell['label']} {cell['pct']}% s={cell['seed']}: "
                    f"{row['nodes']} nós, {row['rounds']} rodadas, {row['malicious_nodes']} maliciosos, "
                    f"teste={float(row['test_weighted']):.3f}, parede={row['wall_s']:.2f}s",
                    flush=True,
                )
                if row["wall_s"] > MAX_RUN_S:
                    stop = True
    path = _plot(rows)
    print(f"\nGráfico: {path}", flush=True)


if __name__ == "__main__":
    main()
