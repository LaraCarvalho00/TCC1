"""Gera blocos PGFPlots a partir dos CSVs (figuras embutidas no .tex)."""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from statistics import mean, stdev

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CSV = os.path.join(ROOT, "sistema", "results", "harness_progressao", "resultados.csv")
REP = os.path.join(ROOT, "sistema", "results", "harness_progressao", "reputacao_por_rodada.csv")
OUT = os.path.join(ROOT, "sistema", "scripts", "_figuras_pgfplots.tex")

CONFIGS = (
    "sem_conluio",
    "com_conluio",
    "sem_conluio_instavel",
    "com_conluio_instavel",
)
TITULO = {
    "sem_conluio": "Sem conluio",
    "com_conluio": "Com conluio",
    "sem_conluio_instavel": "Sem + inst.",
    "com_conluio_instavel": "Com + inst.",
}
LEVELS = ("p0", "p5", "p20", "p35", "p50", "p65", "p80")
LEVEL_X = {"p0": 0, "p5": 5, "p20": 20, "p35": 35, "p50": 50, "p65": 65, "p80": 80}
LEVEL_LAB = {
    "p0": "0\\%",
    "p5": "5\\%",
    "p20": "20\\%",
    "p35": "35\\%",
    "p50": "50\\%",
    "p65": "65\\%",
    "p80": "80\\%",
}
SIZES = (5, 10, 15, 20, 25, 30, 35, 40, 45, 50)
GRUPO_STYLE = {
    "honestos": "solid, mark=o, color=blue!70!black",
    "maliciosos": "dashed, mark=square, color=red!70!black",
    "instaveis": "dotted, mark=triangle, color=orange!80!black",
}
GRUPO_LAB = {"honestos": "Honestos", "maliciosos": "Maliciosos", "instaveis": "Instáveis"}


def stats(values):
    if not values:
        return 0.0, 0.0
    mu = mean(values)
    sd = stdev(values) if len(values) > 1 else 0.0
    return mu, sd


def coords(xs, ys):
    return " ".join(f"({x},{y:.4f})" for x, y in zip(xs, ys))


def load_rows():
    with open(CSV, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def acc_bucket(rows):
    data = defaultdict(lambda: {"w": [], "m": []})
    for row in rows:
        key = (int(row["N"]), row["nivel"], row["configuracao"])
        data[key]["w"].append(float(row["acuracia"]))
        data[key]["m"].append(float(row["acuracia_maioria"]))
    return data


def fig_acuracia_n(data):
    lines = [
        r"\begin{figure}[H]",
        r"\centering",
        r"\begin{tikzpicture}",
        r"\begin{groupplot}[",
        r"  group style={group size=2 by 2, horizontal sep=1.4cm, vertical sep=1.5cm,",
        r"    xlabels at=edge bottom, ylabels at=edge left},",
        r"  width=0.46\textwidth, height=4.2cm,",
        r"  ymin=0, ymax=1.05, xmin=5, xmax=50,",
        r"  xtick={5,20,35,50},",
        r"  ylabel={Acurácia ponderada},",
        r"  xlabel={$N$ (nós)},",
        r"  grid=major, grid style={dotted,gray!40},",
        r"  legend style={font=\tiny, draw=none, fill=none, legend columns=4,",
        r"    at={(0.5,1.18)}, anchor=south, /tikz/every even column/.append style={column sep=4pt}},",
        r"  mark size=1.1pt, line width=0.7pt]",
    ]
    for i, cfg in enumerate(CONFIGS):
        lines.append(r"\nextgroupplot[title={\small " + TITULO[cfg] + "}]")
        for nivel in LEVELS:
            xs, ys = [], []
            for n in SIZES:
                mu, _ = stats(data[(n, nivel, cfg)]["w"])
                xs.append(n)
                ys.append(mu)
            extra = ", forget plot" if i else ""
            lines.append(
                rf"  \addplot+[mark=*{extra}] coordinates {{{coords(xs, ys)}}};"
            )
            if i == 0:
                lines.append(rf"  \addlegendentry{{{LEVEL_LAB[nivel]}}}")
    lines += [
        r"\end{groupplot}",
        r"\end{tikzpicture}",
        r"\caption{Acurácia do consenso ponderado em função de $N$ (média de 30 sementes).}",
        r"\label{fig:acuracia-n}",
        r"\end{figure}",
        "",
    ]
    return "\n".join(lines)


def fig_panorama(data):
    lines = [
        r"\begin{figure}[H]",
        r"\centering",
        r"\begin{tikzpicture}",
        r"\begin{axis}[",
        r"  width=0.92\textwidth, height=5.2cm,",
        r"  ymin=0, ymax=1.05, xmin=0, xmax=80,",
        r"  xtick={0,5,20,35,50,65,80},",
        r"  xlabel={Percentual nominal de nós problemáticos (\%)},",
        r"  ylabel={Acurácia ponderada},",
        r"  grid=major, grid style={dotted,gray!40},",
        r"  legend style={font=\footnotesize, draw=none, fill=none, legend columns=2,",
        r"    at={(0.02,0.22)}, anchor=west},",
        r"  mark size=2pt, line width=0.9pt, error bars/y dir=both,",
        r"  error bars/y explicit, error bars/error bar style={line width=0.5pt}]",
    ]
    for cfg in CONFIGS:
        xs, ys, ss = [], [], []
        for nivel in LEVELS:
            mu, sd = stats(data[(50, nivel, cfg)]["w"])
            xs.append(LEVEL_X[nivel])
            ys.append(mu)
            ss.append(sd)
        pts = " ".join(f"({x},{y:.4f}) +- (0,{s:.4f})" for x, y, s in zip(xs, ys, ss))
        lines.append(rf"  \addplot+[mark=*] coordinates {{{pts}}};")
        lines.append(rf"  \addlegendentry{{{TITULO[cfg]}}}")
    lines += [
        r"\end{axis}",
        r"\end{tikzpicture}",
        r"\caption{Acurácia ponderada em $N=50$ nos sete percentuais nominais (média $\pm$ desvio, 30 sementes).}",
        r"\label{fig:n50-panorama}",
        r"\end{figure}",
        "",
    ]
    return "\n".join(lines)


def fig_reputacao():
    buckets = defaultdict(lambda: defaultdict(list))
    with open(REP, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["N"]) != 50 or row["nivel"] != "p50":
                continue
            key = (row["configuracao"], row["grupo"])
            buckets[key][int(row["rodada"])].append(float(row["reputacao_media"]))
    lines = [
        r"\begin{figure}[H]",
        r"\centering",
        r"\begin{tikzpicture}",
        r"\begin{groupplot}[",
        r"  group style={group size=2 by 2, horizontal sep=1.3cm, vertical sep=1.4cm,",
        r"    xlabels at=edge bottom, ylabels at=edge left},",
        r"  width=0.46\textwidth, height=4.0cm,",
        r"  ymin=0, ymax=1.05, xmin=0, xmax=50,",
        r"  ylabel={Reputação média}, xlabel={Rodada},",
        r"  grid=major, grid style={dotted,gray!40},",
        r"  legend style={font=\tiny, draw=none, fill=none, legend columns=3,",
        r"    at={(0.5,1.16)}, anchor=south},",
        r"  mark size=1.0pt, line width=0.8pt]",
    ]
    for i, cfg in enumerate(CONFIGS):
        lines.append(r"\nextgroupplot[title={\small " + TITULO[cfg] + "}]")
        for grupo in ("honestos", "maliciosos", "instaveis"):
            series = buckets.get((cfg, grupo))
            if not series:
                continue
            xs = sorted(series)
            ys = [mean(series[x]) for x in xs]
            # reduz pontos para o Overleaf: uma a cada 2 rodadas + última
            xs_s = xs[::2] + ([xs[-1]] if xs[-1] not in xs[::2] else [])
            ys_s = [mean(series[x]) for x in xs_s]
            extra = ", forget plot" if i else ""
            style = GRUPO_STYLE[grupo]
            lines.append(
                rf"  \addplot[{style}{extra}] coordinates {{{coords(xs_s, ys_s)}}};"
            )
            if i == 0:
                lines.append(rf"  \addlegendentry{{{GRUPO_LAB[grupo]}}}")
        if cfg == "com_conluio":
            lines.append(
                r"  \node[font=\tiny, align=center, fill=white, fill opacity=0.85, inner sep=1pt]"
                r"    at (axis cs:38,0.52) {Empate / hold};"
            )
    lines += [
        r"\end{groupplot}",
        r"\end{tikzpicture}",
        r"\caption{Reputação média por perfil em $N=50$ e 50\% de nós problemáticos.}",
        r"\label{fig:n50-p50-rep}",
        r"\end{figure}",
        "",
    ]
    return "\n".join(lines)


def fig_p80_barras(data):
    lines = [
        r"\begin{figure}[H]",
        r"\centering",
        r"\begin{tikzpicture}",
        r"\begin{axis}[",
        r"  ybar, bar width=9pt,",
        r"  width=0.95\textwidth, height=5.0cm,",
        r"  ymin=0, ymax=1.15,",
        r"  ylabel={Acurácia},",
        r"  symbolic x coords={Sem conluio, Com conluio, Sem + inst., Com + inst.},",
        r"  xtick=data, x tick label style={font=\small},",
        r"  enlarge x limits=0.18,",
        r"  grid=major, grid style={dotted,gray!40},",
        r"  legend style={font=\footnotesize, draw=none, fill=none, at={(0.5,0.98)},",
        r"    anchor=north, legend columns=2},",
        r"  nodes near coords, nodes near coords style={font=\tiny, /pgf/number format/fixed,",
        r"    /pgf/number format/precision=2}]",
    ]
    pond = []
    maj = []
    for cfg, lab in zip(CONFIGS, ("Sem conluio", "Com conluio", "Sem + inst.", "Com + inst.")):
        mu_w, _ = stats(data[(50, "p80", cfg)]["w"])
        mu_m, _ = stats(data[(50, "p80", cfg)]["m"])
        pond.append(f"({{{lab}}},{mu_w:.4f})")
        maj.append(f"({{{lab}}},{mu_m:.4f})")
    lines.append(r"  \addplot coordinates {" + " ".join(pond) + r"};")
    lines.append(r"  \addlegendentry{Ponderado}")
    lines.append(r"  \addplot coordinates {" + " ".join(maj) + r"};")
    lines.append(r"  \addlegendentry{Maioria}")
    lines += [
        r"\end{axis}",
        r"\end{tikzpicture}",
        r"\caption{Acurácia ponderada e por maioria em $N=50$ e 80\% nominal, nas quatro configurações (30 sementes).}",
        r"\label{fig:n50-p80}",
        r"\end{figure}",
        "",
    ]
    return "\n".join(lines)


def fig_conluio(data):
    lines = [
        r"\begin{figure}[H]",
        r"\centering",
        r"\begin{tikzpicture}",
        r"\begin{axis}[",
        r"  width=0.92\textwidth, height=5.2cm,",
        r"  ymin=0, ymax=1.05, xmin=5, xmax=50,",
        r"  xtick={5,10,15,20,25,30,35,40,45,50},",
        r"  xlabel={$N$ (nós, orquestrador incluído)},",
        r"  ylabel={Acurácia ponderada},",
        r"  grid=major, grid style={dotted,gray!40},",
        r"  legend style={font=\footnotesize, draw=none, fill=none, legend columns=4,",
        r"    at={(0.5,1.05)}, anchor=south},",
        r"  mark size=1.4pt, line width=0.8pt]",
    ]
    for nivel in LEVELS:
        xs, ys = [], []
        for n in SIZES:
            mu, _ = stats(data[(n, nivel, "com_conluio")]["w"])
            xs.append(n)
            ys.append(mu)
        lines.append(rf"  \addplot+[mark=*] coordinates {{{coords(xs, ys)}}};")
        lines.append(rf"  \addlegendentry{{{LEVEL_LAB[nivel]}}}")
    lines += [
        r"\end{axis}",
        r"\end{tikzpicture}",
        r"\caption{Acurácia ponderada versus $N$ na configuração com conluio (sem instáveis).}",
        r"\label{fig:acuracia-conluio}",
        r"\end{figure}",
        "",
    ]
    return "\n".join(lines)


def main():
    rows = load_rows()
    data = acc_bucket(rows)
    body = "\n".join(
        [
            fig_acuracia_n(data),
            fig_panorama(data),
            fig_reputacao(),
            fig_p80_barras(data),
            fig_conluio(data),
        ]
    )
    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write(body)
    print("wrote", OUT, "chars", len(body))


if __name__ == "__main__":
    main()
