"""Figuras do artigo: 50 nós, cinco repetições.

Lê ``sistema/resultados/artigo_n50`` e grava os PNG em ``figuras/`` dessa pasta.
As cópias usadas no texto ficam em ``artigo/figuras``.
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

_ARTIGO = os.path.join(os.path.dirname(__file__), "..", "resultados", "artigo_n50")
_OUT = os.path.join(_ARTIGO, "figuras")
_PASTA = {
    "fixo_hibrido": "fixo_com_gabarito",
    "dinamico_hibrido": "dinamico_com_gabarito",
    "dinamico_so_consenso": "dinamico_sem_gabarito",
}

# Mesma gramática visual da grade que a orientadora já viu:
# círculo, triângulo e estrela, cada um com cor e tipo de linha próprios.
SERIES = (
    ("fixo_hibrido", "#1f77b4", "o", "-", "Fixo, com gabarito"),
    ("dinamico_hibrido", "#ff7f0e", "^", "-", "Dinâmico, com gabarito"),
    ("dinamico_so_consenso", "#2ca02c", "*", "--", "Dinâmico, sem gabarito"),
)
HONESTO = "#1f77b4"
MALICIOSO = "#ff7f0e"


def _tests(ax) -> None:
    """Linhas T1–T5 nas rodadas 10, 20, 30, 40 e 50."""
    for index, round_number in enumerate((10, 20, 30, 40, 50), start=1):
        ax.axvline(round_number, color="#9a9a9a", linestyle=":", linewidth=0.8, zorder=0)
        ax.text(
            round_number,
            1.02,
            f"T{index}",
            ha="center",
            va="bottom",
            fontsize=10,
            color="#444444",
            clip_on=False,
        )


def _style_ax(ax) -> None:
    ax.set_axisbelow(True)
    ax.grid(True, linestyle=":", color="#d5d5d5", zorder=0)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _index() -> list[dict]:
    with open(os.path.join(_ARTIGO, "indice.csv"), encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _run_file(label: str, pct: int, seed: int, name: str) -> str:
    return os.path.join(_ARTIGO, _PASTA[label], f"m{pct:02d}", f"s{seed:02d}", name)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def fig_acuracia(rows: list[dict]) -> None:
    fracs = [0.0, 0.25, 0.5, 0.65]
    grouped: dict[tuple[str, float], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(row["label"], float(row["malicious_frac"]))].append(
            float(row["consensus_accuracy_weighted_on_tests"])
        )

    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    offsets = (-1.6, 0.0, 1.6)
    for (label, color, marker, linestyle, legend), offset in zip(SERIES, offsets):
        xs, ys = [], []
        for frac in fracs:
            sample = grouped.get((label, frac))
            if not sample:
                continue
            xs.append(frac * 100 + offset)
            ys.append(_mean(sample))
        ax.plot(
            xs,
            ys,
            color=color,
            marker=marker,
            linestyle=linestyle,
            linewidth=1.6,
            markersize=9 if marker == "*" else 7,
            label=legend,
        )
        for x_pos, height in zip(xs, ys):
            ax.text(
                x_pos,
                height + 0.06,
                "0" if height == 0 else "1",
                ha="center",
                va="bottom",
                fontsize=8,
                color=color,
            )

    ax.set_xticks([0, 25, 50, 65])
    ax.set_xticklabels(["0%", "25%", "50%", "65%"])
    ax.set_xlim(-8, 73)
    ax.set_ylim(-0.08, 1.22)
    ax.set_ylabel("Acurácia nas rodadas de teste")
    ax.set_xlabel("Fração de nós maliciosos")
    ax.set_title("50 nós · 50 rodadas · 5 sementes · testes T1–T5")
    _style_ax(ax)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3)
    fig.tight_layout()
    fig.savefig(
        os.path.join(_OUT, "fig01_acuracia_teste_n50.png"),
        dpi=160,
        bbox_inches="tight",
    )
    plt.close(fig)


def _acerto_por_rodada(frac: float) -> dict[str, list[float]]:
    pct = int(round(frac * 100))
    return {
        label: _means_from_rounds([
            _run_file(label, pct, seed, "rounds.csv") for seed in range(5)
        ])
        for label, *_rest in SERIES
    }


def _means_from_rounds(paths: list[str]) -> list[float]:
    by_round: dict[int, list[int]] = defaultdict(list)
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for record in csv.DictReader(fh):
                by_round[int(record["round_index"])].append(int(record["consensus_correct"]))
    return [_mean(by_round[i]) for i in range(50)]


def fig_trajetoria() -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 4.4), sharey=True)
    plt.rcParams.update({
        "axes.labelsize": 13,
        "axes.titlesize": 13,
        "xtick.labelsize": 12,
        "ytick.labelsize": 12,
        "legend.fontsize": 12,
    })
    rounds = list(range(1, 51))
    marks = ((0, 10), (4, 10), (7, 10))
    titles = {0.5: "(a) 50% de maliciosos", 0.65: "(b) 65% de maliciosos", 0.8: "(c) 80% de maliciosos"}
    for ax, frac in zip(axes, (0.5, 0.65, 0.8)):
        series_by_label = _acerto_por_rodada(frac)
        for (label, color, marker, linestyle, legend), markevery in zip(SERIES, marks):
            series = series_by_label[label]
            ax.plot(
                rounds,
                series,
                color=color,
                marker=marker,
                linestyle=linestyle,
                linewidth=1.6,
                markersize=8 if marker == "*" else 6,
                markevery=markevery,
                label=legend,
            )
        _tests(ax)
        _style_ax(ax)
        ax.set_title(titles[frac])
        ax.set_xlabel("Rodada")
        ax.set_xlim(0, 50)
        ax.set_ylim(-0.08, 1.18)
    axes[0].set_ylabel("Acerto do consenso ponderado")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.22)
    fig.legend(handles, labels, frameon=False, loc="lower center", ncol=3, bbox_to_anchor=(0.5, 0.02))
    fig.savefig(os.path.join(_OUT, "acerto_por_rodada_50_65_80.png"), dpi=160, bbox_inches="tight")
    plt.close(fig)


def _rep_from_paths(pattern: str) -> dict[str, list[float]]:
    """Média das cinco sementes. Cada nó entra com a reputação da própria cópia."""
    bucket: dict[tuple[str, int], list[float]] = defaultdict(list)
    for seed in range(5):
        per_checkpoint: dict[tuple[str, int], list[float]] = defaultdict(list)
        with open(pattern.format(seed=seed), encoding="utf-8") as fh:
            for record in csv.DictReader(fh):
                per_checkpoint[(record["profile"], int(record["checkpoint"]))].append(
                    float(record["reputation"])
                )
        for (profile, checkpoint), values in per_checkpoint.items():
            bucket[(profile, checkpoint)].append(_mean(values))
    return {
        profile: [_mean(bucket[(profile, k)]) for k in range(51)]
        for profile in ("honest", "malicious")
    }


def _rep_pattern(label: str, pct: int) -> str:
    return os.path.join(
        _ARTIGO, _PASTA[label], f"m{pct:02d}", "s{seed:02d}", "reputation_history.csv",
    )


def _reputacao_dinamico() -> dict[str, dict[str, dict[str, list[float]]]]:
    """50% tem uma cadeia. Em 80% a média do malicioso é a outra cópia."""
    return {
        "50": {
            "com_gabarito": _rep_from_paths(_rep_pattern("dinamico_hibrido", 50)),
            "sem_gabarito": _rep_from_paths(_rep_pattern("dinamico_so_consenso", 50)),
        },
        "80": {
            "com_gabarito": _rep_from_paths(_rep_pattern("dinamico_hibrido", 80)),
            "sem_gabarito": _rep_from_paths(_rep_pattern("dinamico_so_consenso", 80)),
        },
    }


def fig_reputacao() -> dict[str, dict[str, dict[str, list[float]]]]:
    curves = _reputacao_dinamico()
    plt.rcParams.update({
        "axes.labelsize": 13,
        "axes.titlesize": 13,
        "xtick.labelsize": 12,
        "ytick.labelsize": 12,
        "legend.fontsize": 12,
    })
    fig, axes = plt.subplots(2, 2, figsize=(9.2, 7.2), sharey=True)
    rounds = list(range(0, 51))
    panels = (
        ("50", "com_gabarito", "(a) 50%, com gabarito"),
        ("50", "sem_gabarito", "(b) 50%, sem gabarito"),
        ("80", "com_gabarito", "(c) 80%, com gabarito"),
        ("80", "sem_gabarito", "(d) 80%, sem gabarito"),
    )
    for ax, (frac, key, title) in zip(axes.ravel(), panels):
        ax.plot(
            rounds,
            curves[frac][key]["honest"],
            color=HONESTO,
            marker="o",
            linestyle="-",
            linewidth=1.6,
            markersize=5,
            markevery=5,
            label="Honestos",
        )
        ax.plot(
            rounds,
            curves[frac][key]["malicious"],
            color=MALICIOSO,
            marker="^",
            linestyle="-",
            linewidth=1.6,
            markersize=6,
            markevery=5,
            label="Maliciosos",
        )
        _tests(ax)
        _style_ax(ax)
        ax.set_title(title)
        ax.set_xlabel("Rodada")
        ax.set_xlim(0, 50)
        ax.set_ylim(-0.02, 1.18)
    axes[0, 0].set_ylabel("Peso médio do voto")
    axes[1, 0].set_ylabel("Peso médio do voto")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout()
    fig.savefig(os.path.join(_OUT, "reputacao_dinamico_50_e_80.png"), dpi=160, bbox_inches="tight")
    plt.close(fig)
    return curves


def main() -> None:
    os.makedirs(_OUT, exist_ok=True)
    rows = _index()
    fig_acuracia(rows)
    fig_trajetoria()
    curves = fig_reputacao()
    for frac in ("50", "80"):
        for key in ("com_gabarito", "sem_gabarito"):
            hon = curves[frac][key]["honest"]
            mal = curves[frac][key]["malicious"]
            print(
                frac, key,
                " ".join(f"r{k} H={hon[k]:.3f} M={mal[k]:.3f}" for k in (1, 3, 50)),
            )


if __name__ == "__main__":
    main()
