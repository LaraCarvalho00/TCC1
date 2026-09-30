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

from ..core.experiment_spec import LEVELS, LEVELS_PROGRESSAO

_DEFAULT_IN = os.path.join(os.path.dirname(__file__), "..", "results", "harness")

NIVEIS_ROTULO = {
    "p0": "0%",
    "n1": "1 nó",
    "p5": "5%",
    "p20": "20%",
    "p35": "35%",
    "p40": "40%",
    "p50": "50%",
    "p60": "60%",
    "p65": "65%",
    "p80": "80%",
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
GRUPO_ESTILO = {
    "honestos": {"linestyle": "-", "marker": "o", "markevery": 8, "zorder": 3, "linewidth": 1.8},
    "maliciosos": {"linestyle": "--", "marker": "s", "markevery": 8, "zorder": 4, "linewidth": 1.6},
    "instaveis": {"linestyle": ":", "marker": "^", "markevery": 8, "zorder": 2, "linewidth": 1.5},
}


def _f(row: dict, key: str) -> float:
    return float(row[key])


def niveis_presentes(stats: dict) -> tuple[str, ...]:
    found = {key[1] for key in stats}
    preferred = LEVELS_PROGRESSAO if "p5" in found or "p35" in found else LEVELS
    ordered = [nivel for nivel in preferred if nivel in found]
    extra = sorted(found - set(ordered))
    return tuple(ordered + extra)


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


def series_mean_std(series: dict[int, list[float]]) -> tuple[list[int], list[float], list[float]]:
    xs = sorted(series)
    means, stds = [], []
    for x in xs:
        values = series[x]
        mean = sum(values) / len(values)
        means.append(mean)
        if len(values) > 1:
            var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
            stds.append(var**0.5)
        else:
            stds.append(0.0)
    return xs, means, stds


def plot_reputation_groups(ax, buckets: dict, config: str) -> None:
    """Desenha grupos com traços distintos; anota empate honesto/malicioso."""
    drawn: dict[str, list[float]] = {}
    for grupo in ("instaveis", "honestos", "maliciosos"):
        series = buckets.get((config, grupo))
        if not series:
            continue
        xs, means, stds = series_mean_std(series)
        estilo = GRUPO_ESTILO[grupo]
        ax.fill_between(
            xs,
            [m - s for m, s in zip(means, stds)],
            [m + s for m, s in zip(means, stds)],
            color=GRUPO_COR[grupo],
            alpha=0.16,
            linewidth=0,
            zorder=estilo["zorder"] - 1,
        )
        ax.plot(
            xs,
            means,
            color=GRUPO_COR[grupo],
            label=GRUPO_ROTULO[grupo],
            **estilo,
            markersize=4,
        )
        drawn[grupo] = means

    hon, mal = drawn.get("honestos"), drawn.get("maliciosos")
    if hon and mal and len(hon) == len(mal):
        gap = max(abs(a - b) for a, b in zip(hon, mal))
        if gap < 0.03:
            ax.text(
                0.97,
                0.50,
                "Empate: consenso sem confiança\n(reputação não atualiza)",
                transform=ax.transAxes,
                fontsize=6.5,
                ha="right",
                va="center",
                color="#333333",
                bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "#bbbbbb", "alpha": 0.92},
                zorder=5,
            )


def figura1(stats: dict, out_dir: str) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4), sharex=True, sharey=True)
    y_vals = [item["mean"] for item in stats.values()]
    y_std = [item["std"] for item in stats.values()]
    ymin = max(0.0, min(m - s for m, s in zip(y_vals, y_std)) - 0.05)
    ymax = min(1.02, max(m + s for m, s in zip(y_vals, y_std)) + 0.05)
    cmap = plt.get_cmap("tab10")
    niveis = niveis_presentes(stats)
    for ax, config in zip(axes.ravel(), CONFIGS):
        for i, nivel in enumerate(niveis):
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
            ax.plot(xs, ys, marker="o", markersize=3, linewidth=1.1, color=color, label=NIVEIS_ROTULO.get(nivel, nivel))
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
    niveis = niveis_presentes(stats)
    for ax, config in zip(axes.ravel(), CONFIGS):
        for i, n in enumerate(sizes):
            points = []
            for nivel in niveis:
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


def figura_cenario_vs_N(stats: dict, out_dir: str, config: str) -> None:
    niveis = niveis_presentes(stats)
    subset = {key: item for key, item in stats.items() if key[2] == config}
    if not subset:
        return
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    cmap = plt.get_cmap("tab10")
    for i, nivel in enumerate(niveis):
        xs, ys, ss = [], [], []
        for n in sorted({key[0] for key in subset}):
            item = subset.get((n, nivel, config))
            if item is None:
                continue
            xs.append(n)
            ys.append(item["mean"])
            ss.append(item["std"])
        if not xs:
            continue
        color = cmap(i)
        ax.plot(xs, ys, marker="o", markersize=4, linewidth=1.3, color=color, label=NIVEIS_ROTULO.get(nivel, nivel))
        ax.fill_between(xs, [y - s for y, s in zip(ys, ss)], [y + s for y, s in zip(ys, ss)], color=color, alpha=0.18, linewidth=0)
    ax.set_ylim(0.0, 1.02)
    ax.set_xticks([5, 10, 15, 20, 25, 30, 35, 40, 45, 50])
    ax.set_xlabel("N (nós, orquestrador incluído)")
    ax.set_ylabel("Acurácia do consenso ponderado")
    ax.set_title(CONFIG_TITULO[config])
    ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.7)
    ax.legend(ncol=4, fontsize=7, frameon=False, loc="lower left")
    fig.tight_layout()
    _save(fig, out_dir, f"{config}_acuracia_vs_N")


def figura_cenario_vs_percentual(stats: dict, out_dir: str, config: str) -> None:
    niveis = niveis_presentes(stats)
    subset = {key: item for key, item in stats.items() if key[2] == config}
    if not subset:
        return
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    cmap = plt.get_cmap("viridis")
    sizes = sorted({key[0] for key in subset})
    for i, n in enumerate(sizes):
        points = []
        for nivel in niveis:
            item = subset.get((n, nivel, config))
            if item is None:
                continue
            points.append((100 * item["p_efetivo"], item["mean"], item["std"]))
        points.sort()
        if not points:
            continue
        xs, ys, ss = zip(*points)
        color = cmap(i / max(1, len(sizes) - 1))
        ax.plot(xs, ys, marker="o", markersize=3, linewidth=1.0, color=color, label=f"N={n}")
        ax.fill_between(xs, [y - s for y, s in zip(ys, ss)], [y + s for y, s in zip(ys, ss)], color=color, alpha=0.12, linewidth=0)
    ax.set_ylim(0.0, 1.02)
    ax.set_xlabel("Nós maliciosos (% efetivo de N)")
    ax.set_ylabel("Acurácia do consenso ponderado")
    ax.set_title(CONFIG_TITULO[config])
    ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.7)
    ax.legend(ncol=5, fontsize=6.5, frameon=False, loc="lower left")
    fig.tight_layout()
    _save(fig, out_dir, f"{config}_acuracia_vs_percentual")


def figura3(rep_path: str, out_dir: str, n: int = 30, nivel: str | None = None) -> None:
    if not os.path.isfile(rep_path):
        print(f"Sem {rep_path}; figura 3 omitida.")
        return
    with open(rep_path, encoding="utf-8", newline="") as handle:
        all_rows = list(csv.DictReader(handle))
    if nivel is None:
        available = {row["nivel"] for row in all_rows if int(row["N"]) == n}
        for candidate in ("p50", "p40", "p35", "p20"):
            if candidate in available:
                nivel = candidate
                break
        if nivel is None and available:
            nivel = sorted(available)[0]
    rows = [row for row in all_rows if int(row["N"]) == n and row["nivel"] == nivel]
    if not rows:
        print(f"Figura 3: nenhuma linha para N={n} / {nivel}.")
        return
    buckets: dict[tuple, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        key = (row["configuracao"], row["grupo"])
        buckets[key][int(row["rodada"])].append(_f(row, "reputacao_media"))

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4), sharex=True, sharey=True)
    for ax, config in zip(axes.ravel(), CONFIGS):
        plot_reputation_groups(ax, buckets, config)
        ax.set_ylim(0.0, 1.02)
        ax.tick_params(labelsize=7)
        ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.7)
        ax.text(0.03, 0.04, CONFIG_TITULO[config], transform=ax.transAxes, fontsize=8, va="bottom")
    axes[1, 0].set_xlabel("Rodada", fontsize=8)
    axes[1, 1].set_xlabel("Rodada", fontsize=8)
    axes[0, 0].set_ylabel("Reputação média do grupo", fontsize=8)
    axes[1, 0].set_ylabel("Reputação média do grupo", fontsize=8)
    handles, labels = [], []
    for ax in axes.ravel():
        h, lab = ax.get_legend_handles_labels()
        for handle, name in zip(h, lab):
            if name not in labels:
                handles.append(handle)
                labels.append(name)
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
    for config in CONFIGS:
        pasta = os.path.join(saida, config)
        figura_cenario_vs_N(stats, pasta, config)
        figura_cenario_vs_percentual(stats, pasta, config)
    print(f"Figuras em {saida}")


if __name__ == "__main__":
    main()
