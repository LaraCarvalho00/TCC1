"""Figuras por percentual de maliciosos, N=50, 50 rodadas.

Usa o CSV da grade sequencial (30 sementes). Não executa LLM.

    python -m sistema.scripts.plot_n50_cenarios
"""

from __future__ import annotations

import argparse
import csv
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .plot_results import (
    CONFIG_TITULO,
    CONFIGS,
    NIVEIS_ROTULO,
    _f,
    _save,
    plot_reputation_groups,
)

_DEFAULT_IN = os.path.join(os.path.dirname(__file__), "..", "results", "harness_progressao")

CENARIOS = (
    (1, "p0", "0%"),
    (2, "p5", "5%"),
    (3, "p20", "20%"),
    (4, "p35", "35%"),
    (5, "p50", "50%"),
    (6, "p65", "65%"),
    (7, "p80", "80%"),
)


def load_n50(path: str, nivel: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as handle:
        return [
            row
            for row in csv.DictReader(handle)
            if int(row["N"]) == 50 and row["nivel"] == nivel
        ]


def _mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return mean, var**0.5


def figura_acuracia_barras(rows: list[dict], out_dir: str, titulo: str) -> None:
    by_cfg: dict[str, list[float]] = defaultdict(list)
    by_cfg_maj: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_cfg[row["configuracao"]].append(_f(row, "acuracia"))
        by_cfg_maj[row["configuracao"]].append(_f(row, "acuracia_maioria"))
    labels = [CONFIG_TITULO[c] for c in CONFIGS if c in by_cfg]
    xs = list(range(len(labels)))
    means = [_mean_std(by_cfg[c])[0] for c in CONFIGS if c in by_cfg]
    stds = [_mean_std(by_cfg[c])[1] for c in CONFIGS if c in by_cfg]
    means_m = [_mean_std(by_cfg_maj[c])[0] for c in CONFIGS if c in by_cfg]
    stds_m = [_mean_std(by_cfg_maj[c])[1] for c in CONFIGS if c in by_cfg]

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    width = 0.36
    ax.bar([x - width / 2 for x in xs], means, width, yerr=stds, capsize=3, label="Consenso ponderado", color="#2c7bb6")
    ax.bar([x + width / 2 for x in xs], means_m, width, yerr=stds_m, capsize=3, label="Maioria simples", color="#abd9e9")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylim(0.0, 1.05)
    ax.set_ylabel("Acurácia (média ± desvio, 30 sementes)")
    ax.set_title(titulo)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.5, alpha=0.7)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    _save(fig, out_dir, "acuracia_4configs")


def figura_boxplot(rows: list[dict], out_dir: str, titulo: str) -> None:
    data = []
    labels = []
    for config in CONFIGS:
        values = [_f(row, "acuracia") for row in rows if row["configuracao"] == config]
        if not values:
            continue
        data.append(values)
        labels.append(CONFIG_TITULO[config])
    if not data:
        return
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.boxplot(data, showmeans=True)
    ax.set_xticks(list(range(1, len(labels) + 1)))
    ax.set_xticklabels(labels)
    ax.set_ylim(0.0, 1.05)
    ax.set_ylabel("Acurácia por semente")
    ax.set_title(titulo)
    ax.tick_params(axis="x", labelsize=7)
    ax.grid(True, axis="y", linestyle=":", linewidth=0.5, alpha=0.7)
    fig.tight_layout()
    _save(fig, out_dir, "boxplot_sementes")


def figura_reputacao(rep_path: str, nivel: str, out_dir: str, titulo: str) -> None:
    if not os.path.isfile(rep_path):
        return
    with open(rep_path, encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if int(row["N"]) == 50 and row["nivel"] == nivel]
    if not rows:
        return
    buckets: dict[tuple, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        buckets[(row["configuracao"], row["grupo"])][int(row["rodada"])].append(_f(row, "reputacao_media"))

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4), sharex=True, sharey=True)
    for ax, config in zip(axes.ravel(), CONFIGS):
        plot_reputation_groups(ax, buckets, config)
        ax.set_ylim(0.0, 1.02)
        ax.tick_params(labelsize=7)
        ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.7)
        ax.text(0.03, 0.04, CONFIG_TITULO[config], transform=ax.transAxes, fontsize=8, va="bottom")
    axes[1, 0].set_xlabel("Rodada")
    axes[1, 1].set_xlabel("Rodada")
    axes[0, 0].set_ylabel("Reputação média")
    axes[1, 0].set_ylabel("Reputação média")
    handles, labels = [], []
    for ax in axes.ravel():
        h, lab = ax.get_legend_handles_labels()
        for handle, name in zip(h, lab):
            if name not in labels:
                handles.append(handle)
                labels.append(name)
    fig.legend(handles, labels, loc="upper center", ncol=3, fontsize=8, frameon=False, bbox_to_anchor=(0.5, 1.02))
    fig.suptitle(titulo, fontsize=9, y=1.04)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    _save(fig, out_dir, "reputacao_por_rodada")


def figura_panorama(all_rows: list[dict], out_dir: str) -> None:
    niveis = [item[1] for item in CENARIOS]
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    cmap = plt.get_cmap("tab10")
    for i, config in enumerate(CONFIGS):
        xs, ys, ss = [], [], []
        for _idx, nivel, rotulo in CENARIOS:
            values = [
                _f(row, "acuracia")
                for row in all_rows
                if row["nivel"] == nivel and row["configuracao"] == config
            ]
            if not values:
                continue
            mean, std = _mean_std(values)
            xs.append(rotulo)
            ys.append(mean)
            ss.append(std)
        if not xs:
            continue
        positions = list(range(len(xs)))
        ax.errorbar(
            positions,
            ys,
            yerr=ss,
            marker="o",
            capsize=3,
            linewidth=1.2,
            color=cmap(i),
            label=CONFIG_TITULO[config],
        )
    ax.set_xticks(list(range(len(niveis))))
    ax.set_xticklabels([c[2] for c in CENARIOS])
    ax.set_ylim(0.0, 1.05)
    ax.set_xlabel("Percentual nominal de nós maliciosos")
    ax.set_ylabel("Acurácia ponderada (N=50, 50 rodadas)")
    ax.set_title("Panorama: N=50, sete cenários de incidência")
    ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.7)
    ax.legend(frameon=False, fontsize=7)
    fig.tight_layout()
    _save(fig, out_dir, "panorama_7_cenarios")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Figuras N=50 por percentual de maliciosos.")
    parser.add_argument("--entrada", default=_DEFAULT_IN)
    parser.add_argument("--saida", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    entrada = os.path.abspath(args.entrada)
    saida = os.path.abspath(args.saida or os.path.join(entrada, "figuras", "n50_50rodadas"))
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8,
            "axes.unicode_minus": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    csv_path = os.path.join(entrada, "resultados.csv")
    rep_path = os.path.join(entrada, "reputacao_por_rodada.csv")
    with open(csv_path, encoding="utf-8", newline="") as handle:
        all_n50 = [row for row in csv.DictReader(handle) if int(row["N"]) == 50]
    figura_panorama(all_n50, saida)
    for index, nivel, rotulo in CENARIOS:
        rows = [row for row in all_n50 if row["nivel"] == nivel]
        pasta = os.path.join(saida, f"cenario_{index}_{rotulo.replace('%', 'pct')}")
        titulo = f"Cenário {index}: {rotulo} maliciosos  |  N=50, 50 rodadas"
        if not rows:
            print(f"Sem dados para {titulo}")
            continue
        os.makedirs(pasta, exist_ok=True)
        figura_acuracia_barras(rows, pasta, titulo)
        figura_boxplot(rows, pasta, titulo)
        figura_reputacao(rep_path, nivel, pasta, titulo)
        n_mal = rows[0]["n_maliciosos"]
        print(f"Cenário {index} ({rotulo}): {len(rows)} linhas, n_maliciosos={n_mal} -> {pasta}")
    print(f"Figuras em {saida}")


if __name__ == "__main__":
    main()
