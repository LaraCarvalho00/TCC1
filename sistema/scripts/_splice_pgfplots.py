"""Substitui \\includegraphics por PGFPlots em artigo.md e copia para artigo.tex."""

from __future__ import annotations

import os
import re
import shutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ART = os.path.join(ROOT, "artigo.md")
TEX = os.path.join(ROOT, "artigo.tex")
FIGS = os.path.join(ROOT, "sistema", "scripts", "_figuras_pgfplots.tex")

PREAMBLE_OLD = r"""\usepackage{amsmath}
\usepackage{tikz}
\usetikzlibrary{arrows.meta,positioning,shapes.geometric}"""

PREAMBLE_NEW = r"""\usepackage{amsmath}
\usepackage{tikz}
\usepackage{pgfplots}
\usepgfplotslibrary{groupplots}
\pgfplotsset{compat=1.17}
\usetikzlibrary{arrows.meta,positioning,shapes.geometric}"""

RAST_OLD = (
    "As figuras da Seção~\\ref{sec:resultados} são cópias estáveis em "
    "\\texttt{figuras/artigo/}."
)
RAST_NEW = (
    "As figuras da Seção~\\ref{sec:resultados} são geradas no próprio arquivo "
    "com \\texttt{pgfplots}, a partir das médias do CSV, para o Overleaf "
    "compilar sem arquivos de imagem externos."
)


def main():
    with open(ART, encoding="utf-8") as handle:
        text = handle.read()
    with open(FIGS, encoding="utf-8") as handle:
        figs = handle.read().strip() + "\n"

    if PREAMBLE_OLD not in text:
        raise SystemExit("preamble block not found")
    text = text.replace(PREAMBLE_OLD, PREAMBLE_NEW, 1)
    text = text.replace(RAST_OLD, RAST_NEW, 1)

    pattern = re.compile(
        r"\\begin\{figure\}\[H\]\s*\\centering\s*\\includegraphics\[width=[^]]+\]\{figuras/artigo/[^}]+\}\s*"
        r"\\caption\{[^}]+\}\s*\\label\{fig:[^}]+\}\s*\\end\{figure\}",
        re.DOTALL,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 5:
        raise SystemExit(f"expected 5 includegraphics figures, found {len(matches)}")

    # Replace the whole span (first to last figure) with generated figs,
    # preserving text between figures. Split generated figs similarly.
    gen_figs = re.findall(
        r"\\begin\{figure\}\[H\].*?\\end\{figure\}",
        figs,
        flags=re.DOTALL,
    )
    if len(gen_figs) != 5:
        raise SystemExit(f"generated {len(gen_figs)} figures")

    pieces = []
    last = 0
    for match, replacement in zip(matches, gen_figs):
        pieces.append(text[last:match.start()])
        pieces.append(replacement)
        last = match.end()
    pieces.append(text[last:])
    text = "".join(pieces)

    if "includegraphics" in text:
        raise SystemExit("includegraphics still present")

    with open(ART, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    shutil.copyfile(ART, TEX)
    print("updated", ART, "and", TEX, "bytes", len(text.encode("utf-8")))


if __name__ == "__main__":
    main()
