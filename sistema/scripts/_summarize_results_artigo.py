"""Gera tabelas LaTeX a partir do CSV da grade sequencial."""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from statistics import mean, stdev

CSV = os.path.join(os.path.dirname(__file__), "..", "results", "harness_progressao", "resultados.csv")

CONFIGS = (
    "sem_conluio",
    "com_conluio",
    "sem_conluio_instavel",
    "com_conluio_instavel",
)
LEVELS = ("p0", "p5", "p20", "p35", "p50", "p65", "p80")
LEVEL_LABEL = {
    "p0": "0\\%",
    "p5": "5\\%",
    "p20": "20\\%",
    "p35": "35\\%",
    "p50": "50\\%",
    "p65": "65\\%",
    "p80": "80\\%",
}
CFG_LABEL = {
    "sem_conluio": "Sem conluio",
    "com_conluio": "Com conluio",
    "sem_conluio_instavel": "Sem conluio + inst.",
    "com_conluio_instavel": "Com conluio + inst.",
}


def load():
    with open(CSV, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def buckets(rows, n=None):
    data = defaultdict(lambda: {"w": [], "m": []})
    for row in rows:
        if n is not None and int(row["N"]) != n:
            continue
        key = (int(row["N"]), row["nivel"], row["configuracao"])
        data[key]["w"].append(float(row["acuracia"]))
        data[key]["m"].append(float(row["acuracia_maioria"]))
    return data


def fmt(values):
    if not values:
        return "---"
    mu = 100 * mean(values)
    sd = 100 * (stdev(values) if len(values) > 1 else 0.0)
    return f"{mu:.1f}$\\pm${sd:.1f}"


def main():
    rows = load()
    print("total", len(rows), "seeds", len({r["seed"] for r in rows}))
    data50 = buckets(rows, n=50)
    print("% --- N=50 compact table ---")
    print("\\begin{tabular}{|l|c|c|c|c|}")
    print("\\hline")
    print("\\textbf{Nível} & \\textbf{Sem conluio} & \\textbf{Com conluio} & \\textbf{Sem + inst.} & \\textbf{Com + inst.} \\\\")
    print("\\hline")
    for nivel in LEVELS:
        cells = [LEVEL_LABEL[nivel]]
        for cfg in CONFIGS:
            cells.append(fmt(data50[(50, nivel, cfg)]["w"]))
        print(" & ".join(cells) + " \\\\")
    print("\\hline")
    print("\\end{tabular}")
    print()
    print("% majority N=50")
    print("\\begin{tabular}{|l|c|c|c|c|}")
    print("\\hline")
    print("\\textbf{Nível} & \\textbf{Sem conluio} & \\textbf{Com conluio} & \\textbf{Sem + inst.} & \\textbf{Com + inst.} \\\\")
    print("\\hline")
    for nivel in LEVELS:
        cells = [LEVEL_LABEL[nivel]]
        for cfg in CONFIGS:
            cells.append(fmt(data50[(50, nivel, cfg)]["m"]))
        print(" & ".join(cells) + " \\\\")
    print("\\hline")
    print("\\end{tabular}")
    print()
    # p0 vs p80 across N for sem_conluio and com_conluio
    allb = buckets(rows)
    print("% p0 vs p80 sem_conluio / com_conluio weighted")
    for n in (5, 10, 20, 30, 50):
        line = [str(n)]
        for nivel in ("p0", "p80"):
            for cfg in ("sem_conluio", "com_conluio"):
                line.append(fmt(allb[(n, nivel, cfg)]["w"]))
        print("N=" + " ".join(line))
    # counts per cell
    print("cell 50 p0 sem", len(data50[(50, "p0", "sem_conluio")]["w"]))
    print("n_mal p50", {r["n_maliciosos"] for r in rows if int(r["N"])==50 and r["nivel"]=="p50" and r["configuracao"]=="sem_conluio"})
    print("n_mal p80", {r["n_maliciosos"] for r in rows if int(r["N"])==50 and r["nivel"]=="p80" and r["configuracao"]=="sem_conluio"})
    print("n_mal p5", {r["n_maliciosos"] for r in rows if int(r["N"])==50 and r["nivel"]=="p5" and r["configuracao"]=="sem_conluio"})


if __name__ == "__main__":
    main()
