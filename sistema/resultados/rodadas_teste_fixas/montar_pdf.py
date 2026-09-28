"""Gera o PDF do documento de resultados com as figuras de linha.

Usado quando não há compilador LaTeX na máquina. As coordenadas, as cores,
os marcadores e as linhas verticais são os mesmos de graficos.tex.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from fpdf import FPDF

HERE = Path(__file__).resolve().parent
CSV = HERE / "coordenadas.csv"
OUT = HERE / "documento_resultados.pdf"
IMG = HERE / "_figuras"
FONT = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_B = Path(r"C:\Windows\Fonts\arialbd.ttf")

COLORS = {
    "0%": "#1f77b4",
    "25%": "#2ca02c",
    "50%": "#e67814",
    "65%": "#c81e1e",
    "ponderado": "#1f77b4",
    "maioria": "#282828",
    "honesto": "#1f77b4",
    "malicioso": "#c81e1e",
    "ema": "#1f77b4",
    "ema_asymmetric": "#e67814",
    "beta": "#2ca02c",
}
MARKERS = {
    "0%": "o",
    "25%": "^",
    "50%": "s",
    "65%": "*",
    "ponderado": "o",
    "maioria": "s",
    "honesto": "o",
    "malicioso": "*",
    "ema": "o",
    "ema_asymmetric": "s",
    "beta": "^",
}
LINES = {
    "0%": "-",
    "25%": "-",
    "50%": "--",
    "65%": ":",
    "ponderado": "-",
    "maioria": "--",
    "honesto": "-",
    "malicioso": ":",
    "ema": "-",
    "ema_asymmetric": "--",
    "beta": "-",
}
LABELS = {
    "0%": "0%",
    "25%": "25%",
    "50%": "50%",
    "65%": "65%",
    "ponderado": "Ponderado (reputação)",
    "maioria": "Maioria",
    "honesto": "Honesto",
    "malicioso": "Malicioso",
    "ema": "EMA",
    "ema_asymmetric": "EMA assimétrica",
    "beta": "Beta",
}

FIGURES = [
    (
        "acuracia_conluio",
        ["0%", "25%", "50%", "65%"],
        "Acurácia do consenso ponderado com conluio",
        "Acurácia",
        (8.6, 4.6),
        10,
    ),
    (
        "acuracia_sem_conluio",
        ["0%", "25%", "50%", "65%"],
        "Acurácia do consenso ponderado sem conluio",
        "Acurácia",
        (7.4, 4.0),
        10,
    ),
    (
        "ponderado_vs_maioria_65",
        ["ponderado", "maioria"],
        "Ponderado e maioria, 65% em conluio",
        "Acurácia",
        (8.0, 4.3),
        10,
    ),
    (
        "reputacao_65",
        ["honesto", "malicioso"],
        "Reputação, 65% em conluio",
        "Reputação",
        (8.2, 4.5),
        11,
    ),
    (
        "mecanismos_65",
        ["ema", "ema_asymmetric", "beta"],
        "Acurácia por mecanismo, 65% em conluio",
        "Acurácia",
        (8.0, 4.3),
        10,
    ),
]


def load() -> dict:
    groups = defaultdict(lambda: defaultdict(list))
    with CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            groups[row["figura"]][row["serie"]].append(
                (int(float(row["rodada"])), float(row["valor"]))
            )
    for fig in groups.values():
        for pts in fig.values():
            pts.sort()
    return groups


def draw(groups: dict) -> list[Path]:
    IMG.mkdir(exist_ok=True)
    paths = []
    for name, series, title, ylabel, size, phase in FIGURES:
        fig, ax = plt.subplots(figsize=size)
        for x in (10, 20, 30, 40, 50):
            ax.axvline(x, color="#666666", linestyle="--", linewidth=0.8, alpha=0.7, zorder=0)
        handles = []
        for serie in series:
            pts = groups[name][serie]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax.plot(
                xs,
                ys,
                color=COLORS[serie],
                linestyle=LINES[serie],
                linewidth=1.6,
                alpha=0.45,
                zorder=2,
                clip_on=False,
            )
            marks = [(x, y) for x, y in pts if x > 0 and x % 10 == 0]
            if phase == 11:
                marks = [(x, y) for x, y in pts if x % 10 == 0]
            ax.scatter(
                [m[0] for m in marks],
                [m[1] for m in marks],
                color=COLORS[serie],
                marker=MARKERS[serie],
                s=42,
                zorder=3,
                clip_on=False,
            )
            handles.append(
                Line2D(
                    [0],
                    [0],
                    color=COLORS[serie],
                    linestyle=LINES[serie],
                    marker=MARKERS[serie],
                    markersize=7,
                    label=LABELS[serie],
                )
            )
        handles.append(
            Line2D([0], [0], color="#666666", linestyle="--", linewidth=0.8, label="Rodada de teste")
        )
        ax.set_xlim(-2, 54)
        ax.set_ylim(-0.12, 1.14)
        ax.set_xticks([0, 10, 20, 30, 40, 50])
        ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1])
        ax.set_xlabel("Rodada", fontsize=11)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_title(title, fontsize=12)
        ax.tick_params(labelsize=9)
        ax.grid(True, color="#000000", alpha=0.08)
        ax.legend(
            handles=handles,
            fontsize=8,
            loc="upper left",
            bbox_to_anchor=(1.02, 1.0),
            borderaxespad=0,
            framealpha=0.95,
        )
        fig.tight_layout()
        path = IMG / f"{name}.png"
        fig.savefig(path, dpi=160, bbox_inches="tight", pad_inches=0.25)
        plt.close(fig)
        paths.append(path)
    return paths


def paragraph(pdf: FPDF, text: str, size: int = 11, bold: bool = False) -> None:
    pdf.set_font("Arial", "B" if bold else "", size)
    pdf.multi_cell(0, 6.2, text)
    pdf.ln(1.5)


def build(images: list[Path]) -> None:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_font("Arial", "", str(FONT))
    pdf.add_font("Arial", "B", str(FONT_B))
    pdf.add_page()
    paragraph(pdf, "Resultados com rodadas de teste fixas", 16, True)
    pdf.ln(1)
    paragraph(
        pdf,
        "Allan Mateus Arruda De Souza e Lara Andrade Carvalho",
        11,
    )
    pdf.ln(2)
    paragraph(
        pdf,
        "Em todos os experimentos há um teste a cada 10 rodadas: 10, 20, 30, 40 e 50. "
        "A acurácia de teste é a média só nessas rodadas. Os valores abaixo são média de "
        "10 sementes, mecanismo EMA, topologia em estrela. A rede de referência tem 20 nós, "
        "em que 65% corresponde a 13 nós maliciosos. As figuras são gráficos de linha. "
        "As linhas são semitransparentes, cada série tem cor e marcador, e as linhas "
        "verticais marcam as rodadas de teste. A série de 65% e a reputação maliciosa "
        "são a linha vermelha pontilhada com estrela.",
    )

    paragraph(pdf, "1. A comparação que mostra o método", 13, True)
    paragraph(
        pdf,
        "Com 65% de nós maliciosos em conluio, a maioria simples fica em 0,000 nos cinco "
        "testes. O consenso ponderado pela reputação fica em 1,000 nesses mesmos testes. "
        "Treze nós votam o mesmo valor errado e sete votam a resposta certa. A maioria "
        "acompanha o bloco malicioso do início ao fim. O ponderado erra enquanto as "
        "reputações ainda são próximas e acerta depois que a reputação dos maliciosos cai.",
    )
    paragraph(
        pdf,
        "Sem conluio, a acurácia fica em 1,000 em 0%, 25%, 50% e 65%, tanto no ponderado "
        "quanto na maioria. Cada malicioso erra com um valor diferente. Os honestos, com "
        "probabilidade 0,9 de acerto, concentram o voto na resposta certa. Por isso a "
        "acurácia parecia igual entre os cenários: sem um bloco único de votos errados, "
        "os dois consensos escolhem a mesma resposta, e a fração de maliciosos não separa as curvas.",
    )
    paragraph(
        pdf,
        "A diferença aparece quando os maliciosos votam juntos. Em 20 nós, com conluio e EMA: "
        "25% maliciosos, ponderado 1,000 e maioria 1,000; 50%, ponderado 1,000 e maioria 0,340; "
        "65%, ponderado 1,000 e maioria 0,000. Abaixo de 50% os honestos ainda são maioria. "
        "Em 50% a maioria já cai. Em 65% ela zera, e o ponderado permanece em 1,000.",
    )

    paragraph(pdf, "2. O que as linhas verticais mostram", 13, True)
    paragraph(
        pdf,
        "As linhas verticais marcam as rodadas 10, 20, 30, 40 e 50 em todos os gráficos. "
        "No cenário de 65% com conluio, a acurácia do consenso ponderado é 0,000 na rodada 1, "
        "0,000 na rodada 2 e 0,900 na rodada 3. Da rodada 4 em diante ela fica em 1,000. "
        "A mudança de regime acontece antes da primeira linha vertical.",
    )
    paragraph(
        pdf,
        "Nas rodadas 20 a 30 a média é 1,000. Na rodada 40 também é 1,000. Os testes 20, 30 "
        "e 40 caem no patamar já recuperado. Não há um segundo regime de acurácia nesse trecho. "
        "Nos cinco testes a acurácia ponderada é 1,000. A maioria permanece em 0,000, porque "
        "13 votos iguais vencem 7.",
    )
    paragraph(
        pdf,
        "O que ainda se move entre as rodadas 20 e 40 é a reputação, e pouco. A reputação "
        "média dos maliciosos está em 0,014 na rodada 10, em 0,000 na rodada 20 e em 0,000 "
        "na rodada 40. A dos honestos vai de 0,882 na rodada 20 a 0,909 na rodada 40.",
    )

    paragraph(pdf, "3. O limite perto de 65%", 13, True)
    paragraph(
        pdf,
        "Com 13 maliciosos em 20 (65%) votando em conluio, o método segue correto nos testes "
        "mesmo com os maliciosos em maioria numérica: acurácia ponderada 1,000 e acurácia da "
        "maioria 0,000.",
    )
    paragraph(
        pdf,
        "O limite aparece um pouco acima disso. Em 7 nós, a fração nominal 0,65 vira "
        "5 maliciosos em 7, ou seja, 71%. Nesse caso a acurácia ponderada nos testes cai "
        "para 0,880, e a da maioria continua em 0,000. Cerca de 65% ainda é um bom desempenho. "
        "Perto de 70%, em rede pequena, a margem começa a faltar.",
    )

    captions = [
        "Figura 1. Acurácia do consenso ponderado por rodada, com conluio, 20 nós e EMA. A curva de 0% é o cenário sem nós maliciosos. A linha vermelha pontilhada com estrela é 65%.",
        "Figura 2. Acurácia do consenso ponderado por rodada, sem conluio. As curvas ficam sobrepostas. A transparência deixa essa coincidência visível.",
        "Figura 3. Consenso ponderado e maioria, com 65% de nós maliciosos em conluio (13 de 20).",
        "Figura 4. Reputação média dos nós honestos e maliciosos. A linha vermelha pontilhada é o perfil malicioso.",
        "Figura 5. Acurácia do consenso ponderado por mecanismo, com 65% de nós maliciosos em conluio.",
    ]
    for path, caption in zip(images, captions):
        pdf.add_page()
        paragraph(pdf, caption, 11, True)
        pdf.image(str(path), x=12, w=186)

    pdf.output(str(OUT))


if __name__ == "__main__":
    build(draw(load()))
    print(OUT)
