"""Gráficos e tabelas da rodada de testes do orquestrador dinâmico.

Lê ``sistema/results/matrix_orquestrador_dinamico/matrix_index.csv`` (gerado por
``run_matrix --plan dynamic``) e escreve em
``sistema/resultados/orquestrador_dinamico/``:

* ``graficos.tex``: figuras em pgfplots, com as mesmas cores das figuras das
  rodadas de teste fixas;
* ``coordenadas.csv``: os pontos de cada figura, para conferência;
* ``tabelas.md``: as médias por cenário usadas em ``analise.md``;
* ``matrix_index.csv``: cópia do índice.

Todas as médias são entre repetições (e entre os mecanismos beta e EMA
assimétrica, quando o recorte não separa por mecanismo).

Uso::

    python -m sistema.scripts.export_graficos_dinamico
"""
from __future__ import annotations

import csv
import os
import shutil
import statistics
import sys
from collections import defaultdict
from typing import Callable, Iterable, Optional

from ..core.defenses import preset as defense_preset

_HERE = os.path.dirname(__file__)
_DEFAULT_MATRIX = os.path.join(_HERE, "..", "results", "matrix_orquestrador_dinamico")
_DEFAULT_OUT = os.path.join(_HERE, "..", "resultados", "orquestrador_dinamico")

_PREAMBLE = r"""% Gráficos do orquestrador dinâmico (líder eleito a cada rodada).
% Pacotes no preâmbulo do documento:
%   \usepackage{pgfplots}
%   \pgfplotsset{compat=1.18}
%
% Mesmas cores das figuras das rodadas de teste fixas. A série adversa
% (mais maliciosos, sem defesa) é sempre vermelha pontilhada com estrela.

\pgfplotsset{
  compat=1.18,
  orquestrador/.style={
    font=\small,
    tick label style={font=\footnotesize},
    label style={font=\small},
    legend style={font=\footnotesize, fill=white, fill opacity=0.9, text opacity=1, draw=black!30},
    line width=0.9pt,
    grid=major,
    major grid style={black!8}
  }
}
\definecolor{serieZero}{RGB}{31,119,180}
\definecolor{serieVinte}{RGB}{44,160,44}
\definecolor{serieCinquenta}{RGB}{230,120,20}
\definecolor{serieSessenta}{RGB}{200,30,30}
\definecolor{serieMaioria}{RGB}{40,40,40}
"""

_SERIES = [
    ("serieZero", "o", "solid"),
    ("serieVinte", "triangle*", "solid"),
    ("serieCinquenta", "square*", "dashed"),
    ("serieSessenta", "star", "dotted"),
    ("serieMaioria", "diamond*", "dashdotted"),
    ("black!45", "x", "loosely dashed"),
]

_PRESET_LABELS = {
    "none": "nenhuma",
    "calibration": "só calibração",
    "oracle_bypass": "só gabarito fora do quórum",
    "split_alpha": "só taxas separadas",
    "split_scores": "só dois scores",
    "refuse_forged": "só recusa (divisão)",
    "all": "todas",
    "all_minus_calibration": "todas menos calibração",
    "all_minus_oracle_bypass": "todas menos gabarito fora",
    "all_minus_split_alpha": "todas menos taxas",
    "all_minus_split_scores": "todas menos dois scores",
    "all_minus_refuse_forged": "todas menos recusa",
}


# ---------------------------------------------------------------------------
# Leitura e agregação
# ---------------------------------------------------------------------------

def _read(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _num(value) -> Optional[float]:
    if value in ("", None):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _mean(rows: Iterable[dict], field: str) -> Optional[float]:
    values = [v for v in (_num(r.get(field)) for r in rows) if v is not None]
    return statistics.fmean(values) if values else None


def _share(rows: list[dict], predicate: Callable[[dict], bool]) -> Optional[float]:
    return sum(1 for r in rows if predicate(r)) / len(rows) if rows else None


def _select(index: list[dict], **filters) -> list[dict]:
    rows = index
    for key, expected in filters.items():
        allowed = {str(e) for e in expected} if isinstance(expected, (list, tuple, set)) else {str(expected)}
        rows = [r for r in rows if str(r.get(key)) in allowed]
    return rows


def _pct(row: dict) -> float:
    return float(row["malicious_pct_actual"])


def _fmt(value: Optional[float], digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _ablation_rows(index: list[dict]) -> list[dict]:
    """Bloco da ablação mais o preset ``all``, que foi gravado no bloco ``main``."""
    cells = {("20", "0.5"), ("20", "0.65"), ("7", "0.65")}
    extra = [
        r for r in _select(index, block="main", defense="all", leader_attack=("forge", "censor"))
        if (r["nodes"], r["malicious_frac"]) in cells
    ]
    return _select(index, block="ablation") + extra


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------

class _Figures:
    def __init__(self) -> None:
        self.tex: list[str] = []
        self.coords: list[dict] = []

    def line(self, name, caption, label, xlabel, ylabel, series, *, xtick=None, ymax=None, xmode=None, extra=""):
        body = []
        for i, (legend, pairs, *style_index) in enumerate(series):
            color, mark, style = _SERIES[(style_index[0] if style_index else i) % len(_SERIES)]
            pairs = [(x, y) for x, y in pairs if y is not None]
            for x, y in pairs:
                self.coords.append({"figura": name, "serie": legend, "x": x, "y": f"{y:.3f}"})
            coordinates = " ".join(f"({x:g},{y:.3f})" for x, y in pairs)
            body.append(
                f"\\addplot[{color}, {style}, mark={mark}, opacity=0.6, mark size=2.4pt, "
                f"mark options={{solid, opacity=1}}] coordinates {{{coordinates}}};\n"
                f"\\addlegendentry{{{legend}}}"
            )
        options = [
            "orquestrador", "width=0.9\\textwidth", "height=6.4cm",
            f"xlabel={{{xlabel}}}", f"ylabel={{{ylabel}}}", "ymin=0",
            "legend pos=outer north east",
        ]
        if ymax is not None:
            options.append(f"ymax={ymax}")
        if xtick:
            options.append("xtick={" + ",".join(f"{x:g}" for x in xtick) + "}")
        if xmode:
            options.append(f"xmode={xmode}")
        self._figure(options, "\n".join(body) + extra, caption, label)

    def bars(self, name, caption, label, ylabel, categories, series, *, horizontal=False, ymax=None):
        body = []
        cats = [c for c, _ in categories]
        for i, (legend, values) in enumerate(series):
            color, _, _ = _SERIES[i % len(_SERIES)]
            points = []
            for cat in cats:
                v = values.get(cat)
                if v is None:
                    continue
                self.coords.append({"figura": name, "serie": legend, "x": cat, "y": f"{v:.3f}"})
                points.append(f"({v:.3f},{cat})" if horizontal else f"({cat},{v:.3f})")
            body.append(
                f"\\addplot[fill={color}!70, draw={color}] coordinates {{{' '.join(points)}}};\n"
                f"\\addlegendentry{{{legend}}}"
            )
        coords_key = "symbolic y coords" if horizontal else "symbolic x coords"
        tick_key = "ytick" if horizontal else "xtick"
        ticklabels = ",".join("{" + text + "}" for _, text in categories)
        options = [
            "orquestrador",
            "xbar" if horizontal else "ybar",
            f"{coords_key}={{{','.join(cats)}}}",
            f"{tick_key}=data",
            f"{'yticklabels' if horizontal else 'xticklabels'}={{{ticklabels}}}",
            "width=0.9\\textwidth",
            f"height={'11cm' if horizontal else '6.4cm'}",
            ("xlabel" if horizontal else "ylabel") + f"={{{ylabel}}}",
            ("xmin=0" if horizontal else "ymin=0"),
            "bar width=" + ("4pt" if horizontal else "9pt"),
            "legend pos=outer north east",
            "enlarge " + ("y" if horizontal else "x") + " limits=0.06",
        ]
        if ymax is not None:
            options.append(("xmax" if horizontal else "ymax") + f"={ymax}")
        self._figure(options, "\n".join(body), caption, label)

    def _figure(self, options, body, caption, label):
        opts = ",\n      ".join(options)
        self.tex.append(
            "\n\\begin{figure}[htbp]\n  \\centering\n  \\begin{tikzpicture}\n"
            f"    \\begin{{axis}}[\n      {opts}\n    ]\n{body}\n    \\end{{axis}}\n"
            f"  \\end{{tikzpicture}}\n  \\caption{{{caption}}}\n  \\label{{{label}}}\n\\end{{figure}}\n"
        )


# ---------------------------------------------------------------------------
# Exportação
# ---------------------------------------------------------------------------

def export(matrix_dir: str, out_dir: str) -> None:
    index_path = os.path.join(matrix_dir, "matrix_index.csv")
    index = _read(index_path)
    if not index:
        raise SystemExit(f"Índice vazio: {index_path}")
    os.makedirs(out_dir, exist_ok=True)
    fig = _Figures()
    tables: list[str] = ["# Tabelas do orquestrador dinâmico (geradas)", ""]

    main = _select(index, block="main")
    fractions = sorted({_pct(r) for r in _select(main, nodes=20)})

    # 1. Liderança maliciosa depois da calibração, por N.
    def led_curve(rows: list[dict]) -> list:
        pts = []
        for pct in sorted({_pct(r) for r in rows}):
            cell = [r for r in rows if _pct(r) == pct]
            led = _mean(cell, "leader_malicious_rounds_after_calibration")
            span = float(cell[0]["rounds"]) - defense_preset(cell[0]["defense"]).calibration_rounds
            pts.append((pct, led / span if led is not None else None))
        return pts

    series = [(f"{n} nós, todas as defesas", led_curve(_select(main, nodes=n, leader_attack="forge"))) for n in (7, 10, 20)]
    series.append(("20 nós, sem defesas", led_curve(_select(_ablation_rows(index), nodes=20, defense="none", leader_attack="forge")), 3))
    series.append(("20 nós, só consenso (rodízio)", led_curve(_select(index, block="consensus", nodes=20)), 4))
    series.append(("fração de maliciosos", [(p, p / 100.0) for p in (0, 25, 50, 65, 71.43)], 5))
    fig.line(
        "lideranca_maliciosa", "Fração das rodadas, depois da calibração, em que o líder eleito é malicioso. "
        "Grafo 4-regular, líder que forja, sinal híbrido (exceto a série de consenso puro, em que o poder de voto "
        "não se separa e a eleição vira rodízio). Média entre repetições e mecanismos. "
        "A linha de referência é a fração de nós maliciosos na rede.",
        "fig:dinamico-lideranca", "Nós maliciosos (\\%)", "Rodadas com líder malicioso", series, ymax=1,
        xtick=[0, 25, 50, 65, 71.43],
    )

    # 2. Rodadas anuladas por ataque do líder (20 nós).
    attacks = [("none", "sem ataque"), ("forge", "forja"), ("censor", "censura")]
    series = []
    for pct in fractions:
        values = {}
        for attack, _ in attacks:
            cell = [r for r in _select(main, nodes=20, leader_attack=attack) if _pct(r) == pct]
            values[attack] = _mean(cell, "voided_rounds")
        series.append((f"{pct:g}\\%", values))
    fig.bars(
        "anuladas_por_ataque", "Rodadas anuladas (de 50) por tipo de ataque do líder, 20 nós, todas as defesas. "
        "Média entre repetições e mecanismos. A forja ou a censura só derruba a rodada do líder malicioso.",
        "fig:dinamico-anuladas", "Rodadas anuladas", attacks, series,
    )

    # 3. Massa de reputação maliciosa no fim, 20 nós.
    def mass_curve(rows: list[dict]) -> list:
        return [(pct, _mean([r for r in rows if _pct(r) == pct], "malicious_power_mass_final"))
                for pct in sorted({_pct(r) for r in rows})]
    ablation = _ablation_rows(index)
    series = [
        ("híbrido, todas as defesas", mass_curve(_select(main, nodes=20, leader_attack="forge"))),
        ("só consenso, todas as defesas", mass_curve(_select(index, block="consensus", nodes=20))),
        ("híbrido, sem defesas", mass_curve(_select(ablation, nodes=20, defense="none", leader_attack="forge")), 3),
        ("fração de maliciosos", [(p, p / 100.0) for p in (0, 25, 50, 65)], 5),
    ]
    fig.line(
        "massa_maliciosa", "Massa de reputação dos maliciosos ao fim de 50 rodadas, na cópia da cadeia seguida "
        "pela maioria dos honestos, 20 nós, líder que forja. Acima de 0,5 o conluio fecha o quórum sozinho.",
        "fig:dinamico-massa", "Nós maliciosos (\\%)", "Massa maliciosa", series, ymax=1, xtick=[0, 25, 50, 65],
    )

    # 4. Saltos de difusão por N.
    scale = _select(index, block="scale")
    sizes = sorted({int(r["nodes"]) for r in scale})
    series = []
    for topology, label, styles in (("star", "completo", (0, 5)), ("kregular", "4-regular", (1, 4))):
        rows = _select(scale, topology=topology)
        series.append((f"saltos médios, {label}", [(n, _mean(_select(rows, nodes=n), "mean_hops")) for n in sizes], styles[0]))
        series.append((f"diâmetro, {label}", [(n, _mean(_select(rows, nodes=n), "graph_diameter")) for n in sizes], styles[1]))
    fig.line(
        "saltos_por_n", "Saltos da difusão da tarefa (do líder ao nó mais distante) por tamanho da rede, "
        "25\\% de maliciosos sem conluio. No grafo completo cada nó mantém N-1 conexões; no 4-regular, 4.",
        "fig:dinamico-saltos", "Nós (escala log)", "Saltos", series, xmode="log", xtick=sizes,
    )

    # 5. Ablação: acurácia nas rodadas de teste por preset.
    presets = list(_PRESET_LABELS)
    cats = [(p.replace("_", ""), _PRESET_LABELS[p]) for p in reversed(presets)]
    series = []
    for n, frac, label in ((20, "0.5", "20 nós, 50\\%"), (20, "0.65", "20 nós, 65\\%"), (7, "0.65", "7 nós, 71\\%")):
        values = {}
        for p in presets:
            cell = _select(ablation, nodes=n, malicious_frac=frac, defense=p, leader_attack="forge")
            values[p.replace("_", "")] = _mean(cell, "consensus_accuracy_weighted_on_tests")
        series.append((label, values))
    fig.bars(
        "ablacao", "Ablação das defesas contra conluio: acurácia do consenso ponderado nas rodadas de teste, "
        "líder que forja. Média entre repetições e mecanismos.",
        "fig:dinamico-ablacao", "Acurácia nas rodadas de teste", cats, series, horizontal=True, ymax=1,
    )

    with open(os.path.join(out_dir, "graficos.tex"), "w", encoding="utf-8") as fh:
        fh.write(_PREAMBLE + "".join(fig.tex))
    with open(os.path.join(out_dir, "coordenadas.csv"), "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["figura", "serie", "x", "y"])
        writer.writeheader()
        writer.writerows(fig.coords)

    _png_previews(fig.coords, os.path.join(out_dir, "figuras"))
    tables += _tables(index)
    with open(os.path.join(out_dir, "tabelas.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(tables) + "\n")
    shutil.copyfile(index_path, os.path.join(out_dir, "matrix_index.csv"))
    print(f"Gráficos e tabelas em {out_dir}")


def _png_previews(coords: list[dict], out_dir: str) -> None:
    """Prévia em PNG de cada figura (mesmas coordenadas do TeX), se houver matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    os.makedirs(out_dir, exist_ok=True)
    by_figure: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for c in coords:
        by_figure[c["figura"]][c["serie"].replace("\\%", "%")].append((c["x"], float(c["y"])))
    for name, series in by_figure.items():
        fig, ax = plt.subplots(figsize=(8, 4.2))
        numeric = all(isinstance(x, (int, float)) for pts in series.values() for x, _ in pts)
        if numeric:
            for legend, pts in series.items():
                ax.plot([x for x, _ in pts], [y for _, y in pts], marker="o", label=legend, alpha=0.8)
            if name == "saltos_por_n":
                ax.set_xscale("log")
        else:
            cats = list(dict.fromkeys(x for pts in series.values() for x, _ in pts))
            width = 0.8 / max(1, len(series))
            for i, (legend, pts) in enumerate(series.items()):
                values = dict(pts)
                positions = [j + i * width for j in range(len(cats))]
                if name == "ablacao":
                    ax.barh(positions, [values.get(c, 0) for c in cats], height=width, label=legend)
                else:
                    ax.bar(positions, [values.get(c, 0) for c in cats], width=width, label=legend)
            ticks = [j + width * (len(series) - 1) / 2 for j in range(len(cats))]
            if name == "ablacao":
                ax.set_yticks(ticks, cats, fontsize=7)
            else:
                ax.set_xticks(ticks, cats)
        ax.set_title(name.replace("_", " "))
        ax.grid(alpha=0.2)
        ax.legend(fontsize=7, loc="best")
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, f"{name}.png"), dpi=110)
        plt.close(fig)


def _tables(index: list[dict]) -> list[str]:
    lines: list[str] = []
    main = _select(index, block="main")
    reference = _select(index, block="reference")
    consensus = _select(index, block="consensus")

    def by_cell(rows):
        cells = defaultdict(list)
        for r in rows:
            cells[(int(r["nodes"]), _pct(r))].append(r)
        return cells

    lines += [
        "## Principal: fixo × dinâmico (líder que forja, todas as defesas)",
        "",
        "| Nós | Maliciosos | Fixo: acurácia testes | Fixo: recuperação | Dinâmico: acurácia testes | Dinâmico: todas | "
        "Dinâmico: recuperação | Líder malicioso pós-calibração | Forjas aceitas | Anuladas | Divisões | Massa maliciosa | Consenso puro: acurácia testes |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    ref_cells = by_cell(reference)
    cons_cells = by_cell(consensus)
    for (n, pct), rows in sorted(by_cell(_select(main, leader_attack="forge")).items()):
        ref = ref_cells.get((n, pct), [])
        cons = cons_cells.get((n, pct), [])
        lines.append(
            f"| {n} | {pct:g}% | {_fmt(_mean(ref, 'consensus_accuracy_weighted_on_tests'))} | "
            f"{_fmt(_mean(ref, 'recovery_round'), 1)} | {_fmt(_mean(rows, 'consensus_accuracy_weighted_on_tests'))} | "
            f"{_fmt(_mean(rows, 'consensus_accuracy_weighted'))} | {_fmt(_mean(rows, 'recovery_round'), 1)} | "
            f"{_fmt(_mean(rows, 'leader_malicious_rounds_after_calibration'), 2)} | {_fmt(_mean(rows, 'forged_accepted'), 2)} | "
            f"{_fmt(_mean(rows, 'voided_rounds'), 2)} | {_fmt(_mean(rows, 'chain_split_rounds'), 2)} | "
            f"{_fmt(_mean(rows, 'malicious_power_mass_final'))} | {_fmt(_mean(cons, 'consensus_accuracy_weighted_on_tests'))} |"
        )

    lines += [
        "",
        "## Rotação e ataques do líder (todas as defesas)",
        "",
        "| Ataque | Nós | Maliciosos | Maior sequência do mesmo líder | Líderes distintos | Rodadas de largada | "
        "Mandatos encerrados pela auditoria | Censuras aceitas | Forjas aceitas | Réplicas honestas divergentes |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for attack in ("none", "forge", "censor"):
        for (n, pct), rows in sorted(by_cell(_select(main, leader_attack=attack)).items()):
            lines.append(
                f"| {attack} | {n} | {pct:g}% | {_fmt(_mean(rows, 'max_consecutive_same_leader'), 2)} | "
                f"{_fmt(_mean(rows, 'n_distinct_leaders'), 1)} | {_fmt(_mean(rows, 'bootstrap_rounds'), 1)} | "
                f"{_fmt(_mean(rows, 'mandates_ended_by_audit'), 2)} | {_fmt(_mean(rows, 'censored_accepted'), 2)} | "
                f"{_fmt(_mean(rows, 'forged_accepted'), 2)} | {_fmt(_mean(rows, 'honest_replicas_divergent_final'), 2)} |"
            )

    auditor = _select(index, block="auditor")
    if auditor:
        lines += [
            "",
            "## Auditor que veta rodadas honestas (false_reject)",
            "",
            "| Defesa | Nós | Maliciosos | Rodadas anuladas | Penalidades por veto falso | Divisões | Acurácia testes | Reputação final maliciosos |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for defense in ("none", "all"):
            for (n, pct), rows in sorted(by_cell(_select(auditor, defense=defense)).items()):
                lines.append(
                    f"| {defense} | {n} | {pct:g}% | {_fmt(_mean(rows, 'voided_rounds'), 2)} | "
                    f"{_fmt(_mean(rows, 'auditor_false_reject_penalties'), 2)} | {_fmt(_mean(rows, 'chain_split_rounds'), 2)} | "
                    f"{_fmt(_mean(rows, 'consensus_accuracy_weighted_on_tests'))} | {_fmt(_mean(rows, 'final_rep_malicious'))} |"
                )

    ablation = _ablation_rows(index)
    lines += [
        "",
        "## Ablação das defesas (acurácia ponderada nas rodadas de teste)",
        "",
        "| Preset | Ataque | 20 nós, 50% | 20 nós, 65% | 7 nós, 71% | Massa maliciosa 20/65% | Líder malicioso pós-calibração 20/65% | Divisões 20/65% |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for attack in ("forge", "censor"):
        for preset in _PRESET_LABELS:
            cells = [
                _select(ablation, nodes=n, malicious_frac=f, defense=preset, leader_attack=attack)
                for n, f in ((20, "0.5"), (20, "0.65"), (7, "0.65"))
            ]
            lines.append(
                f"| {preset} | {attack} | " + " | ".join(_fmt(_mean(c, "consensus_accuracy_weighted_on_tests")) for c in cells)
                + f" | {_fmt(_mean(cells[1], 'malicious_power_mass_final'))}"
                + f" | {_fmt(_mean(cells[1], 'leader_malicious_rounds_after_calibration'), 2)}"
                + f" | {_fmt(_mean(cells[1], 'chain_split_rounds'), 2)} |"
            )

    scale = _select(index, block="scale")
    lines += [
        "",
        "## Escala (25% maliciosos, sem conluio)",
        "",
        "| Topologia | Nós | Grau máximo | Diâmetro | Saltos médios | Saltos máximos | Acurácia testes |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for topology in ("star", "kregular"):
        for n in sorted({int(r["nodes"]) for r in scale}):
            rows = _select(scale, topology=topology, nodes=n)
            lines.append(
                f"| {topology} | {n} | {_fmt(_mean(rows, 'graph_max_degree'), 0)} | {_fmt(_mean(rows, 'graph_diameter'), 0)} | "
                f"{_fmt(_mean(rows, 'mean_hops'), 2)} | {_fmt(_mean(rows, 'max_hops'), 1)} | "
                f"{_fmt(_mean(rows, 'consensus_accuracy_weighted_on_tests'))} |"
            )

    lines += [
        "",
        "## Sinal: híbrido × consenso puro (líder sem ataque e com forja, todas as defesas)",
        "",
        "| Nós | Maliciosos | Híbrido: acurácia testes | Híbrido: massa maliciosa | Consenso: acurácia testes | "
        "Consenso: massa maliciosa | Consenso: líder malicioso pós-calibração | Consenso: divisões |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    hybrid_cells = by_cell(_select(main, leader_attack="none"))
    for (n, pct), rows in sorted(by_cell(consensus).items()):
        hyb = hybrid_cells.get((n, pct), [])
        lines.append(
            f"| {n} | {pct:g}% | {_fmt(_mean(hyb, 'consensus_accuracy_weighted_on_tests'))} | "
            f"{_fmt(_mean(hyb, 'malicious_power_mass_final'))} | {_fmt(_mean(rows, 'consensus_accuracy_weighted_on_tests'))} | "
            f"{_fmt(_mean(rows, 'malicious_power_mass_final'))} | {_fmt(_mean(rows, 'leader_malicious_rounds_after_calibration'), 2)} | "
            f"{_fmt(_mean(rows, 'chain_split_rounds'), 2)} |"
        )

    lines += [
        "",
        "## Mecanismo (principal, forja, todas as defesas, acurácia nas rodadas de teste)",
        "",
        "| Nós | Maliciosos | beta | ema_asymmetric |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for (n, pct), rows in sorted(by_cell(_select(main, leader_attack="forge")).items()):
        lines.append(
            f"| {n} | {pct:g}% | {_fmt(_mean(_select(rows, mechanism='beta'), 'consensus_accuracy_weighted_on_tests'))} | "
            f"{_fmt(_mean(_select(rows, mechanism='ema_asymmetric'), 'consensus_accuracy_weighted_on_tests'))} |"
        )
    return lines


if __name__ == "__main__":
    matrix = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_MATRIX
    out = sys.argv[2] if len(sys.argv) > 2 else _DEFAULT_OUT
    export(matrix, out)
