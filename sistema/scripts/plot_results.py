"""Gera as figuras da seção de Resultados a partir dos CSVs do harness.

    python -m sistema.scripts.plot_results
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

_DEFAULT_IN = os.path.join(os.path.dirname(__file__), "..", "results", "harness")

NIVEIS_ORDEM = ("p0", "n1", "p20", "p40", "p60", "p80")
NIVEIS_ROTULO = {
    "p0": "0% (p0)",
    "n1": "1 nó (n1)",
    "p20": "20% (p20)",
    "p40": "40% (p40)",
    "p60": "60% (p60)",
    "p80": "80% (p80)",
}
CONFIGS = (
    "sem_conluio",
    "com_conluio",
    "sem_conluio_instavel",
    "com_conluio_instavel",
)
CONFIG_TITULO = {
    "sem_conluio": "Sem conluio",
    "com_conluio": "Com conluio",
    "sem_conluio_instavel": "Sem conluio + instáveis",
    "com_conluio_instavel": "Com conluio + instáveis",
}
GRUPO_ROTULO = {
    "honestos": "Honestos",
    "maliciosos": "Maliciosos",
    "instaveis": "Instáveis",
}
GRUPO_COR = {
    "honestos": "#2c7bb6",
    "maliciosos": "#d7191c",
    "instaveis": "#fdae61",
}


def _f(row: dict, key: str) -> float:
    return float(row[key])


def load_resultados(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def agg_accuracy(rows: list[dict]) -> dict:
    buckets: dict[tuple, list[float]] = defaultdict(list)
    extras: dict[tuple, dict] = {}
    for row in rows:
        key = (int(row["N"]), row["nivel"], row["configuracao"])
        buckets[key].append(_f(row, "acuracia"))
        extras[key] = {
            "n_maliciosos": int(row["n_maliciosos"]),
            "p_efetivo": _f(row, "p_efetivo"),
        }
    out = {}
    for key, values in buckets.items():
        mean = sum(values) / len(values)
        if len(values) > 1:
            var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
            std = var**0.5
        else:
            std = 0.0
        out[key] = {"mean": mean, "std": std, **extras[key]}
    return out


def _save(fig, out_dir: str, stem: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    fig.savefig(os.path.join(out_dir, f"{stem}.pdf"), bbox_inches="tight")
    fig.savefig(os.path.join(out_dir, f"{stem}.svg"), bbox_inches="tight")
    fig.savefig(os.path.join(out_dir, f"{stem}.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)


def figura1(stats: dict, out_dir: str) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4), sharex=True, sharey=True)
    y_vals = [item["mean"] for item in stats.values()]
    y_std = [item["std"] for item in stats.values()]
    ymin = max(0.0, min(m - s for m, s in zip(y_vals, y_std)) - 0.05)
    ymax = min(1.02, max(m + s for m, s in zip(y_vals, y_std)) + 0.05)
    cmap = plt.get_cmap("tab10")
    for ax, config in zip(axes.ravel(), CONFIGS):
        for i, nivel in enumerate(NIVEIS_ORDEM):
            xs, ys, ss = [], [], []
            for n in sorted({key[0] for key in stats if key[2] == config}):
                item = stats.get((n, nivel, config))
                if item is None:
                    continue
                xs.append(n)
                ys.append(item["mean"])
                ss.append(item["std"])
            if not xs:
                continue
            color = cmap(i)
            ax.plot(xs, ys, marker="o", markersize=3, linewidth=1.1, color=color, label=NIVEIS_ROTULO[nivel])
            lo = [y - s for y, s in zip(ys, ss)]
            hi = [y + s for y, s in zip(ys, ss)]
            ax.fill_between(xs, lo, hi, color=color, alpha=0.18, linewidth=0)
        ax.set_ylim(ymin, ymax)
        ax.set_xticks([5, 10, 15, 20, 25, 30, 35, 40, 45, 50])
        ax.tick_params(labelsize=7)
        ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.7)
        ax.text(0.03, 0.04, CONFIG_TITULO[config], transform=ax.transAxes, fontsize=8, va="bottom")
    axes[1, 0].set_xlabel("N (nós, orquestrador incluído)", fontsize=8)
    axes[1, 1].set_xlabel("N (nós, orquestrador incluído)", fontsize=8)
    axes[0, 0].set_ylabel("Acurácia do consenso ponderado", fontsize=8)
    axes[1, 0].set_ylabel("Acurácia do consenso ponderado", fontsize=8)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, fontsize=7, frameon=False, bbox_to_anchor=(0.5, 1.02))
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save(fig, out_dir, "figura1_acuracia_vs_N")


def figura2(stats: dict, out_dir: str, modo: str) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4), sharey=True)
    y_vals = [item["mean"] for item in stats.values()]
    ymin = max(0.0, min(y_vals) - 0.08)
    ymax = min(1.02, max(y_vals) + 0.05)
    cmap = plt.get_cmap("viridis")
    sizes = sorted({key[0] for key in stats})
    for ax, config in zip(axes.ravel(), CONFIGS):
        for i, n in enumerate(sizes):
            points = []
            for nivel in NIVEIS_ORDEM:
                item = stats.get((n, nivel, config))
                if item is None:
                    continue
                x = item["n_maliciosos"] if modo == "absoluto" else 100 * item["p_efetivo"]
                points.append((x, item["mean"], item["std"]))
            points.sort()
            if not points:
                continue
            xs, ys, ss = zip(*points)
            color = cmap(i / max(1, len(sizes) - 1))
            ax.plot(xs, ys, marker="o", markersize=2.5, linewidth=0.9, color=color, label=f"N={n}")
            ax.fill_between(xs, [y - s for y, s in zip(ys, ss)], [y + s for y, s in zip(ys, ss)], color=color, alpha=0.12, linewidth=0)
        ax.set_ylim(ymin, ymax)
        ax.tick_params(labelsize=7)
        ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.7)
        ax.text(0.03, 0.04, CONFIG_TITULO[config], transform=ax.transAxes, fontsize=8, va="bottom")
        if modo == "absoluto":
            ax.set_xlabel("Nós maliciosos (quantidade)", fontsize=8)
        else:
            ax.set_xlabel("Nós maliciosos (% de N)", fontsize=8)
    axes[0, 0].set_ylabel("Acurácia do consenso ponderado", fontsize=8)
    axes[1, 0].set_ylabel("Acurácia do consenso ponderado", fontsize=8)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=5, fontsize=6.5, frameon=False, bbox_to_anchor=(0.5, 1.03))
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    stem = "figura2_acuracia_vs_maliciosos_absoluto" if modo == "absoluto" else "figura2_acuracia_vs_maliciosos_percentual"
    _save(fig, out_dir, stem)


def figura3(rep_path: str, out_dir: str, n: int = 30, nivel: str = "p40") -> None:
    if not os.path.isfile(rep_path):
        print(f"Sem {rep_path}; figura 3 omitida.")
        return
    with open(rep_path, encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if int(row["N"]) == n and row["nivel"] == nivel]
    if not rows:
        print("Figura 3: nenhuma linha para N=30 / p40.")
        return
    buckets: dict[tuple, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        key = (row["configuracao"], row["grupo"])
        buckets[key][int(row["rodada"])].append(_f(row, "reputacao_media"))

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4), sharex=True, sharey=True)
    for ax, config in zip(axes.ravel(), CONFIGS):
        for grupo in ("honestos", "maliciosos", "instaveis"):
            series = buckets.get((config, grupo))
            if not series:
                continue
            xs = sorted(series)
            means = [sum(series[x]) / len(series[x]) for x in xs]
            stds = []
            for x in xs:
                values = series[x]
                mean = sum(values) / len(values)
                if len(values) > 1:
                    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
                    stds.append(var**0.5)
                else:
                    stds.append(0.0)
            ax.plot(xs, means, color=GRUPO_COR[grupo], linewidth=1.2, label=GRUPO_ROTULO[grupo])
            ax.fill_between(
                xs,
                [m - s for m, s in zip(means, stds)],
                [m + s for m, s in zip(means, stds)],
                color=GRUPO_COR[grupo],
                alpha=0.2,
                linewidth=0,
            )
        ax.set_ylim(0.0, 1.02)
        ax.tick_params(labelsize=7)
        ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.7)
        ax.text(0.03, 0.04, CONFIG_TITULO[config], transform=ax.transAxes, fontsize=8, va="bottom")
    axes[1, 0].set_xlabel("Rodada", fontsize=8)
    axes[1, 1].set_xlabel("Rodada", fontsize=8)
    axes[0, 0].set_ylabel("Reputação média do grupo", fontsize=8)
    axes[1, 0].set_ylabel("Reputação média do grupo", fontsize=8)
    handles, labels = axes[1, 1].get_legend_handles_labels()
    if not handles:
        handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, fontsize=8, frameon=False, bbox_to_anchor=(0.5, 1.02))
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save(fig, out_dir, f"figura3_reputacao_N{n}_{nivel}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Figuras a partir dos CSVs do harness.")
    parser.add_argument("--entrada", default=_DEFAULT_IN)
    parser.add_argument("--saida", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    entrada = os.path.abspath(args.entrada)
    saida = os.path.abspath(args.saida or os.path.join(entrada, "figuras"))
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8,
            "axes.unicode_minus": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    stats = agg_accuracy(load_resultados(os.path.join(entrada, "resultados.csv")))
    figura1(stats, saida)
    figura2(stats, saida, "absoluto")
    figura2(stats, saida, "percentual")
    figura3(os.path.join(entrada, "reputacao_por_rodada.csv"), saida)
    print(f"Figuras em {saida}")


if __name__ == "__main__":
    main()
