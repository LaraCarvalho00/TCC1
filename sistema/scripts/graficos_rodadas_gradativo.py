"""Acurácia por rodada com a fração de maliciosos subindo de 15 em 15 pontos.

Roda a simulação com 20 nós e 0, 15, 30, 45, 60, 75 e 80% de maliciosos,
com e sem conluio, nos dois orquestradores:

* fixo: orquestrador central, gabarito em toda rodada (como em ``teste_fixo``);
* dinâmico: líder eleito, grafo 4-regular, sinal híbrido, líder malicioso que
  forja e todas as defesas.

Com 20 nós todos os percentuais são exatos (3, 6, 9, 12, 15 e 16 maliciosos).
O cenário de 0% não tem variante de conluio e entra nas duas figuras.

Escreve em ``sistema/resultados/rodadas_gradativas/``:

* ``por_rodada/<orquestrador>_m<pct>_<com|sem>.csv``: médias entre repetições;
* ``acuracia_teste.csv`` e ``tabela.md``: acurácia nas rodadas 10, 20, 30, 40, 50;
* ``graficos.tex``: figuras em pgfplots do consenso ponderado e da maioria simples
  (carregar ``teste_fixo/figuras/estilo_figuras.tex``);
* ``figuras/*.png``: prévias das mesmas figuras e painéis 2×2 (acurácia ponderada,
  maioria simples e reputação dos maliciosos).

Uso::

    python -m sistema.scripts.graficos_rodadas_gradativo [--seeds 10] [--workers 4]
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sistema.simulate import parse_args, run_simulation  # noqa: E402

PERCENTS = (0, 15, 30, 45, 60, 75, 80)
NODES = 20
ROUNDS = 50
TEST_ROUNDS = (10, 20, 30, 40, 50)
COLLUSION_VALUE = 999

ORCHESTRATORS = {
    "fixo": ["--orchestration", "fixed", "--signal", "truth"],
    "dinamico": [
        "--orchestration", "dynamic", "--signal", "hybrid", "--topology", "kregular", "--degree", "4",
        "--leader-attack", "forge", "--defense", "all",
    ],
}
ORCH_LABELS = {
    "fixo": "orquestrador fixo (gabarito em toda rodada)",
    "dinamico": "orquestrador dinâmico (líder eleito, sinal híbrido, líder que forja, todas as defesas)",
}

# Do azul (nenhum malicioso) ao vermelho-escuro (80%).
COLORS = {
    0: (31, 119, 180), 15: (44, 160, 44), 30: (188, 189, 34), 45: (230, 120, 20),
    60: (214, 39, 40), 75: (148, 103, 189), 80: (90, 20, 20),
}
MARKS = {0: "*", 15: "triangle*", 30: "pentagon*", 45: "square*", 60: "star", 75: "diamond*", 80: "x"}
LINES = {0: "solid", 15: "solid", 30: "solid", 45: "dashed", 60: "dotted", 75: "dashdotted", 80: "densely dashed"}

_HERE = os.path.dirname(__file__)
_RUNS = os.path.join(_HERE, "..", "results", "rodadas_gradativas")
_OUT = os.path.join(_HERE, "..", "resultados", "rodadas_gradativas")


def _scenarios(seeds: int) -> list[tuple[str, int, bool, int]]:
    jobs = []
    for orch in ORCHESTRATORS:
        for pct in PERCENTS:
            for collusion in ((False,) if pct == 0 else (False, True)):
                jobs += [(orch, pct, collusion, seed) for seed in range(seeds)]
    return jobs


def _name(orch: str, pct: int, collusion: bool) -> str:
    return f"{orch}_m{pct:02d}_{'com' if collusion else 'sem'}"


def _run(job: tuple[str, int, bool, int]) -> tuple[tuple[str, int, bool], int, list[dict], list[dict]]:
    orch, pct, collusion, seed = job
    out = os.path.join(_RUNS, f"{_name(orch, pct, collusion)}_r{seed}")
    argv = [
        "--nodes", str(NODES), "--malicious", str(pct / 100), "--rounds", str(ROUNDS), "--seed", str(seed),
        "--mechanism", "ema", "--output", out, "--overwrite", "--quiet", "--no-row-sync",
        *ORCHESTRATORS[orch],
    ]
    if collusion:
        argv += ["--collusion-value", str(COLLUSION_VALUE)]
    run_simulation(parse_args(argv))
    with open(os.path.join(out, "rounds.csv"), encoding="utf-8", newline="") as fh:
        rounds = list(csv.DictReader(fh))
    with open(os.path.join(out, "per_node.csv"), encoding="utf-8", newline="") as fh:
        per_node = list(csv.DictReader(fh))
    return (orch, pct, collusion), seed, rounds, per_node


def _mean(values: list[float]):
    return statistics.fmean(values) if values else None


def _aggregate(results) -> dict[tuple, list[dict]]:
    acc_w: dict[tuple, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    acc_m: dict[tuple, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    rep: dict[tuple, dict[tuple, list]] = defaultdict(lambda: defaultdict(list))
    for key, _seed, rounds, per_node in results:
        by_round: dict[tuple, list[float]] = defaultdict(list)
        for row in per_node:
            if row.get("reputation_after", "") != "":
                by_round[(int(row["round_index"]) + 1, row["profile"])].append(float(row["reputation_after"]))
        for row in rounds:
            r = int(row["round_index"]) + 1
            acc_w[key][r].append(float(row["consensus_correct"]))
            acc_m[key][r].append(float(row["majority_correct"]))
            for profile in ("honest", "malicious"):
                if by_round.get((r, profile)):
                    rep[key][(r, profile)].append(_mean(by_round[(r, profile)]))
    table = {}
    for key in acc_w:
        table[key] = [
            {
                "rodada": r,
                "rodada_teste": r if r in TEST_ROUNDS else "",
                "acuracia_ponderada": _mean(acc_w[key][r]),
                "acuracia_maioria": _mean(acc_m[key][r]),
                "reputacao_honesta": _mean(rep[key].get((r, "honest"), [])),
                "reputacao_maliciosa": _mean(rep[key].get((r, "malicious"), [])),
            }
            for r in sorted(acc_w[key])
        ]
    return table


def _fmt(value) -> str:
    return "" if value is None else f"{value:.4f}"


def _write_csvs(table: dict, seeds: int) -> list[dict]:
    por_dir = os.path.join(_OUT, "por_rodada")
    os.makedirs(por_dir, exist_ok=True)
    fields = ["orquestrador", "nos", "maliciosos_pct", "conluio", "repeticoes", "rodada", "rodada_teste",
              "acuracia_ponderada", "acuracia_maioria", "reputacao_honesta", "reputacao_maliciosa"]
    summary = []
    for (orch, pct, collusion), rows in sorted(table.items()):
        meta = {"orquestrador": orch, "nos": NODES, "maliciosos_pct": pct, "conluio": int(collusion), "repeticoes": seeds}
        with open(os.path.join(por_dir, f"{_name(orch, pct, collusion)}.csv"), "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({**meta, **{k: _fmt(v) if isinstance(v, float) else v for k, v in row.items()}})
        tests = [row for row in rows if row["rodada"] in TEST_ROUNDS]
        summary.append({
            **meta,
            "acuracia_ponderada_teste": _mean([row["acuracia_ponderada"] for row in tests]),
            "acuracia_maioria_teste": _mean([row["acuracia_maioria"] for row in tests]),
            "acuracia_ponderada_todas": _mean([row["acuracia_ponderada"] for row in rows]),
            "reputacao_honesta_final": rows[-1]["reputacao_honesta"],
            "reputacao_maliciosa_final": rows[-1]["reputacao_maliciosa"],
        })
    with open(os.path.join(_OUT, "acuracia_teste.csv"), "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows({k: _fmt(v) if isinstance(v, float) else v for k, v in s.items()} for s in summary)
    return summary


def _figures() -> list[tuple[str, str, bool]]:
    return [(orch, f"{orch}_{'com' if c else 'sem'}_conluio", c) for orch in ORCHESTRATORS for c in (False, True)]


def _series(pct: int, collusion: bool) -> bool:
    return pct == 0 or collusion


FIELDS = {
    "acuracia_ponderada": ("Acurácia do consenso ponderado", "ponderado", "Acurácia"),
    "acuracia_maioria": ("Acurácia da maioria simples", "maioria", "Acurácia"),
    "reputacao_honesta": ("Reputação média dos nós honestos", "rep_honestos", "Reputação"),
    "reputacao_maliciosa": ("Reputação média dos nós maliciosos", "rep_maliciosos", "Reputação"),
}

DYNAMIC_MALICIOUS_NOTE = (
    "No dinâmico, cada nó é medido na própria cópia da cadeia: acima de 50%, depois da divisão, "
    "a curva dos maliciosos é a cadeia do conluio, que os honestos não seguem."
)


def _write_tex() -> None:
    lines = [
        "% Acurácia e reputação (honestos e maliciosos) por rodada, 20 nós, EMA, de 0% a 80% de maliciosos.",
        "% Carregue antes: pgfplots e sistema/resultados/teste_fixo/figuras/estilo_figuras.tex.",
        "% Os caminhos das tabelas são relativos a sistema/resultados/rodadas_gradativas/.",
        "",
    ]
    for pct, (r, g, b) in COLORS.items():
        lines.append(f"\\definecolor{{gradativo{pct}}}{{RGB}}{{{r},{g},{b}}}")
    lines.append("\\pgfplotsset{")
    for pct in PERCENTS:
        lines.append(
            f"  gradativo {pct}/.style={{color=gradativo{pct}, {LINES[pct]}, mark={MARKS[pct]}, "
            f"mark options={{solid, fill=gradativo{pct}, opacity=1}}}},"
        )
    lines.append("}")
    for field, (title, short, ylabel) in FIELDS.items():
        for orch, _fig, collusion in _figures():
            side = "com conluio (todos os maliciosos respondem 999)" if collusion else "sem conluio (cada malicioso erra com um valor qualquer)"
            lines += [
                "", "\\begin{figure}[htbp]", "\\centering", "\\begin{tikzpicture}",
                f"\\begin{{axis}}[tcc linha, width=\\figw, height=\\figh, ylabel={{{ylabel}}}, legend columns=4]",
                "  \\linhasDeTeste",
            ]
            for pct in PERCENTS:
                if field == "reputacao_maliciosa" and pct == 0:
                    continue
                c = collusion and pct > 0
                lines += [
                    f"  \\addplot[gradativo {pct}] table[x=rodada, y={field}, col sep=comma]",
                    f"    {{por_rodada/{_name(orch, pct, c)}.csv}};",
                    f"  \\addlegendentry{{{pct}\\%}}",
                ]
            lines += [
                "  \\legendaRodadaDeTeste", "\\end{axis}", "\\end{tikzpicture}",
                f"\\caption{{{title} por rodada, {side}, 20 nós, EMA, {ORCH_LABELS[orch]}. "
                "Média entre as repetições. A curva de 0\\% é o cenário sem maliciosos."
                + (" " + DYNAMIC_MALICIOUS_NOTE.replace("%", "\\%") if field == "reputacao_maliciosa" and orch == "dinamico" else "")
                + "}",
                f"\\label{{fig:gradativo-{short}-{orch}-{'com' if collusion else 'sem'}}}", "\\end{figure}",
            ]
    with open(os.path.join(_OUT, "graficos.tex"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _plot(ax, table: dict, orch: str, collusion: bool, field: str = "acuracia_ponderada") -> None:
    for x in TEST_ROUNDS:
        ax.axvline(x, color="#828282", linestyle="--", linewidth=0.8)
    styles = {"solid": "-", "dashed": "--", "dotted": ":", "dashdotted": "-.", "densely dashed": (0, (3, 1))}
    for pct in PERCENTS:
        rows = table[(orch, pct, collusion and pct > 0)]
        xs = [row["rodada"] for row in rows]
        ys = [row[field] for row in rows]
        color = tuple(v / 255 for v in COLORS[pct])
        ax.plot(xs, ys, color=color, linestyle=styles[LINES[pct]], linewidth=1.6, alpha=0.75,
                marker="o", markevery=list(range(9, len(xs), 10)), markersize=5, label=f"{pct}%")
    ax.set_xlim(0, 51)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xticks([0, 10, 20, 30, 40, 50])
    ax.set_xlabel("Rodada")
    ax.grid(alpha=0.2)


def _write_pngs(table: dict) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig_dir = os.path.join(_OUT, "figuras")
    shutil.rmtree(fig_dir, ignore_errors=True)
    os.makedirs(fig_dir)
    titles = {"fixo": "Orquestrador fixo", "dinamico": "Orquestrador dinâmico"}
    for field, (title, short, _ylabel) in FIELDS.items():
        for orch, name, collusion in _figures():
            fig, ax = plt.subplots(figsize=(9, 4.6))
            _plot(ax, table, orch, collusion, field)
            ax.set_ylabel(title)
            ax.set_title(f"{titles[orch]}, {'com' if collusion else 'sem'} conluio (20 nós, média de repetições)")
            ax.legend(title="Maliciosos", ncol=4, fontsize=8, loc="center right")
            fig.tight_layout()
            fig.savefig(os.path.join(fig_dir, f"{short}_{name}.png"), dpi=130)
            plt.close(fig)
    panels = (
        ("acuracia_ponderada", "Acurácia do consenso ponderado", "painel_acuracia_ponderada", ""),
        ("acuracia_maioria", "Acurácia da maioria simples", "painel_acuracia_maioria", ""),
        ("reputacao_honesta", "Reputação média dos honestos", "painel_reputacao_honesta", ""),
        ("reputacao_maliciosa", "Reputação média dos maliciosos", "painel_reputacao_maliciosa", DYNAMIC_MALICIOUS_NOTE),
    )
    _honest_vs_malicious(plt, table, titles, fig_dir)
    for field, label, name, note in panels:
        fig, axes = plt.subplots(2, 2, figsize=(13, 8.4), sharex=True, sharey=True)
        for i, orch in enumerate(ORCHESTRATORS):
            for j, collusion in enumerate((False, True)):
                ax = axes[i][j]
                _plot(ax, table, orch, collusion, field)
                ax.set_title(f"{titles[orch]}, {'com' if collusion else 'sem'} conluio")
                if j == 0:
                    ax.set_ylabel(label)
        handles, labels = axes[0][0].get_legend_handles_labels()
        fig.legend(handles, labels, title="Maliciosos", ncol=7, loc="lower center", fontsize=9)
        if note:
            fig.text(0.5, 0.005, note, ha="center", fontsize=8.5, style="italic")
        fig.tight_layout(rect=(0, 0.08, 1, 1))
        fig.savefig(os.path.join(fig_dir, f"{name}.png"), dpi=120)
        plt.close(fig)


def _honest_vs_malicious(plt, table: dict, titles: dict, fig_dir: str) -> None:
    """Um quadro por percentual: reputação dos honestos, dos maliciosos e acurácia ponderada."""
    curves = (
        ("reputacao_honesta", "Reputação dos honestos", "#1f77b4", "-", 2.0),
        ("reputacao_maliciosa", "Reputação dos maliciosos", "#c81e1e", "--", 2.0),
        ("acuracia_ponderada", "Acurácia do consenso ponderado", "#555555", ":", 1.3),
    )
    combos = [(orch, collusion) for orch in ORCHESTRATORS for collusion in (False, True)]

    def draw(ax, orch, collusion, pct):
        rows = table[(orch, pct, collusion and pct > 0)]
        xs = [row["rodada"] for row in rows]
        for x in TEST_ROUNDS:
            ax.axvline(x, color="#bbbbbb", linestyle="--", linewidth=0.6)
        for field, label, color, style, width in curves:
            ys = [row[field] for row in rows]
            if any(y is not None for y in ys):
                ax.plot(xs, ys, color=color, linestyle=style, linewidth=width, label=label)
        ax.set_xlim(0, 51)
        ax.set_ylim(-0.05, 1.05)
        ax.set_xticks([0, 10, 20, 30, 40, 50])
        ax.grid(alpha=0.2)

    def finish(fig, axes_with_legend, note, path):
        handles, labels = axes_with_legend.get_legend_handles_labels()
        fig.legend(handles, labels, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 0.025), fontsize=10)
        if note:
            fig.text(0.5, 0.004, note, ha="center", fontsize=9, style="italic")
        fig.tight_layout(rect=(0, 0.08, 1, 1))
        fig.savefig(path, dpi=110)
        plt.close(fig)

    for orch, collusion in combos:
        fig, axes = plt.subplots(2, 4, figsize=(16, 7.4), sharex=True, sharey=True)
        for k, pct in enumerate(PERCENTS):
            ax = axes[k // 4][k % 4]
            draw(ax, orch, collusion, pct)
            ax.set_title(f"{pct}% maliciosos ({round(pct * NODES / 100)} de {NODES})", fontsize=10)
        axes[1][3].axis("off")
        for ax in axes[1]:
            ax.set_xlabel("Rodada")
        fig.suptitle(f"{titles[orch]}, {'com' if collusion else 'sem'} conluio: honestos × maliciosos", fontsize=13)
        note = DYNAMIC_MALICIOUS_NOTE if orch == "dinamico" else ""
        side = "com" if collusion else "sem"
        finish(fig, axes[0][1], note, os.path.join(fig_dir, f"honestos_vs_maliciosos_{orch}_{side}_conluio.png"))

    fig, axes = plt.subplots(len(combos), len(PERCENTS), figsize=(22, 12), sharex=True, sharey=True)
    for i, (orch, collusion) in enumerate(combos):
        for j, pct in enumerate(PERCENTS):
            ax = axes[i][j]
            draw(ax, orch, collusion, pct)
            if i == 0:
                ax.set_title(f"{pct}% maliciosos", fontsize=11)
            if j == 0:
                ax.set_ylabel(f"{titles[orch].replace('Orquestrador ', '')}\n{'com' if collusion else 'sem'} conluio", fontsize=11)
            if i == len(combos) - 1:
                ax.set_xlabel("Rodada")
    finish(fig, axes[-1][1], DYNAMIC_MALICIOUS_NOTE, os.path.join(fig_dir, "painel_honestos_vs_maliciosos.png"))


def _write_table(summary: list[dict]) -> None:
    cell = {(s["orquestrador"], s["maliciosos_pct"], s["conluio"]): s for s in summary}

    def get(orch, pct, collusion, field):
        s = cell.get((orch, pct, int(collusion and pct > 0)))
        return "—" if s is None or s[field] is None else f"{s[field]:.3f}"

    lines = [
        "# Acurácia nas rodadas de teste (10, 20, 30, 40, 50), 20 nós, EMA",
        "",
        "## Consenso ponderado nas rodadas de teste",
        "",
        "| Maliciosos | Fixo sem conluio | Fixo com conluio | Dinâmico sem conluio | Dinâmico com conluio |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for pct in PERCENTS:
        lines.append(
            f"| {pct}% | {get('fixo', pct, False, 'acuracia_ponderada_teste')} | {get('fixo', pct, True, 'acuracia_ponderada_teste')} | "
            f"{get('dinamico', pct, False, 'acuracia_ponderada_teste')} | {get('dinamico', pct, True, 'acuracia_ponderada_teste')} |"
        )
    lines += [
        "",
        "## Maioria simples nas rodadas de teste",
        "",
        "| Maliciosos | Fixo sem conluio | Fixo com conluio | Dinâmico sem conluio | Dinâmico com conluio |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for pct in PERCENTS:
        lines.append(
            f"| {pct}% | {get('fixo', pct, False, 'acuracia_maioria_teste')} | {get('fixo', pct, True, 'acuracia_maioria_teste')} | "
            f"{get('dinamico', pct, False, 'acuracia_maioria_teste')} | {get('dinamico', pct, True, 'acuracia_maioria_teste')} |"
        )
    lines += [
        "",
        "## Consenso ponderado em todas as 50 rodadas",
        "",
        "| Maliciosos | Fixo sem conluio | Fixo com conluio | Dinâmico sem conluio | Dinâmico com conluio |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for pct in PERCENTS:
        lines.append(
            f"| {pct}% | {get('fixo', pct, False, 'acuracia_ponderada_todas')} | {get('fixo', pct, True, 'acuracia_ponderada_todas')} | "
            f"{get('dinamico', pct, False, 'acuracia_ponderada_todas')} | {get('dinamico', pct, True, 'acuracia_ponderada_todas')} |"
        )
    lines += [
        "",
        "## Reputação média dos honestos na rodada 50",
        "",
        "| Maliciosos | Fixo sem conluio | Fixo com conluio | Dinâmico sem conluio | Dinâmico com conluio |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for pct in PERCENTS:
        lines.append(
            f"| {pct}% | {get('fixo', pct, False, 'reputacao_honesta_final')} | {get('fixo', pct, True, 'reputacao_honesta_final')} | "
            f"{get('dinamico', pct, False, 'reputacao_honesta_final')} | {get('dinamico', pct, True, 'reputacao_honesta_final')} |"
        )
    lines += [
        "",
        "## Reputação média dos maliciosos na rodada 50",
        "",
        "| Maliciosos | Fixo sem conluio | Fixo com conluio | Dinâmico sem conluio | Dinâmico com conluio |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for pct in PERCENTS[1:]:
        lines.append(
            f"| {pct}% | {get('fixo', pct, False, 'reputacao_maliciosa_final')} | {get('fixo', pct, True, 'reputacao_maliciosa_final')} | "
            f"{get('dinamico', pct, False, 'reputacao_maliciosa_final')} | {get('dinamico', pct, True, 'reputacao_maliciosa_final')} |"
        )
    with open(os.path.join(_OUT, "tabela.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=10, help="Repetições por cenário.")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    args = parser.parse_args()

    jobs = _scenarios(args.seeds)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(_run, jobs))
    shutil.rmtree(_RUNS, ignore_errors=True)

    os.makedirs(_OUT, exist_ok=True)
    table = _aggregate(results)
    summary = _write_csvs(table, args.seeds)
    _write_tex()
    _write_pngs(table)
    _write_table(summary)
    print(f"{len(jobs)} execuções. Saída em {os.path.abspath(_OUT)}")


if __name__ == "__main__":
    main()
