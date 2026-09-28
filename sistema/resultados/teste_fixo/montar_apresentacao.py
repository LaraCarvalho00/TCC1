"""Gera o PDF de apresentação a partir dos CSVs de teste_fixo."""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from fpdf import FPDF

BASE = Path(__file__).resolve().parent
POR = BASE / "por_rodada"
ANALISE = BASE / "analise"
FIG = BASE / "_apresentacao"
PDF_PATH = BASE / "resultados_apresentacao.pdf"

AZUL = (31 / 255, 119 / 255, 180 / 255)
VERDE = (44 / 255, 160 / 255, 44 / 255)
LARANJA = (230 / 255, 120 / 255, 20 / 255)
VERMELHO = (200 / 255, 30 / 255, 30 / 255)
CINZA = (40 / 255, 40 / 255, 40 / 255)
ROXO = (106 / 255, 90 / 255, 205 / 255)
MARROM = (140 / 255, 86 / 255, 75 / 255)
TEAL = (0 / 255, 128 / 255, 128 / 255)
LINHA = (130 / 255, 130 / 255, 130 / 255)

MECANISMO = {
    "ema": "EMA",
    "ema_asymmetric": "EMA assimétrica",
    "beta": "Beta",
}


def ler(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def serie(path: Path, coluna: str) -> tuple[list[int], list[float]]:
    linhas = sorted(ler(path), key=lambda row: int(row["rodada"]))
    return (
        [int(row["rodada"]) for row in linhas],
        [float(row[coluna]) for row in linhas],
    )


def br(valor: str) -> str:
    if valor is None or str(valor).strip() == "":
        return "—"
    return f"{float(valor):.3f}".replace(".", ",")


def preparar_eixo(ax, ylabel: str) -> None:
    ax.set_xlim(-2, 54)
    ax.set_ylim(-0.16, 1.20)
    ax.set_xlabel("Rodada", fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_xticks([0, 10, 20, 30, 40, 50])
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.tick_params(labelsize=11)
    ax.grid(True, color="0.88", zorder=0)
    for rodada in (10, 20, 30, 40, 50):
        ax.axvline(rodada, color=LINHA, linestyle="--", linewidth=1.05, zorder=1)
    ax.plot([], [], color=LINHA, linestyle="--", linewidth=1.2, label="Rodada de teste")
    for spine in ax.spines.values():
        spine.set_linewidth(0.6)


def curva(ax, x, y, cor, estilo, marcador, rotulo) -> None:
    ax.plot(x, y, color=cor, linestyle=estilo, linewidth=1.9, alpha=0.6, zorder=2)
    marcas_x = [valor for valor in x if valor in (10, 20, 30, 40, 50)]
    marcas_y = [y[x.index(valor)] for valor in marcas_x]
    ax.scatter(
        marcas_x,
        marcas_y,
        color=cor,
        marker=marcador,
        s=50,
        zorder=3,
        clip_on=False,
        label=rotulo,
    )


def salvar(fig, nome: str) -> Path:
    ax = fig.axes[0]
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.20),
        ncol=3,
        frameon=False,
        fontsize=11,
    )
    fig.tight_layout()
    destino = FIG / nome
    fig.savefig(destino, dpi=160, bbox_inches="tight", pad_inches=0.28)
    plt.close(fig)
    return destino


def figuras() -> dict[str, Path]:
    FIG.mkdir(exist_ok=True)
    saida = {}

    def novo(ylabel: str):
        fig, ax = plt.subplots(figsize=(8.4, 5.15))
        preparar_eixo(ax, ylabel)
        return fig, ax

    fig, ax = novo("Acurácia")
    pares = [
        ("n20_m00_sem_ema.csv", AZUL, "-", "o", "0%"),
        ("n20_m25_com_ema.csv", VERDE, "-", "^", "25%"),
        ("n20_m50_com_ema.csv", LARANJA, "--", "s", "50%"),
        ("n20_m65_com_ema.csv", VERMELHO, ":", "*", "65%"),
    ]
    for arquivo, cor, estilo, marcador, rotulo in pares:
        x, y = serie(POR / arquivo, "acuracia_ponderada")
        curva(ax, x, y, cor, estilo, marcador, rotulo)
    saida["com"] = salvar(fig, "com_conluio.png")

    fig, ax = novo("Acurácia")
    pares = [
        ("n20_m00_sem_ema.csv", AZUL, "-", "o", "0%"),
        ("n20_m25_sem_ema.csv", VERDE, "-", "^", "25%"),
        ("n20_m50_sem_ema.csv", LARANJA, "--", "s", "50%"),
        ("n20_m65_sem_ema.csv", VERMELHO, ":", "*", "65%"),
    ]
    for arquivo, cor, estilo, marcador, rotulo in pares:
        x, y = serie(POR / arquivo, "acuracia_ponderada")
        curva(ax, x, y, cor, estilo, marcador, rotulo)
    saida["sem"] = salvar(fig, "sem_conluio.png")

    fig, ax = novo("Acurácia")
    x, y = serie(POR / "n20_m65_com_ema.csv", "acuracia_ponderada")
    curva(ax, x, y, VERMELHO, ":", "*", "Ponderado")
    x, y = serie(POR / "n20_m65_com_ema.csv", "acuracia_maioria")
    curva(ax, x, y, CINZA, "-", "D", "Maioria simples")
    saida["cmp"] = salvar(fig, "ponderado_vs_maioria.png")

    fig, ax = novo("Reputação média")
    x, y = serie(POR / "n20_m65_com_ema.csv", "reputacao_honesta")
    curva(ax, x, y, ROXO, "-", "p", "Honestos")
    x, y = serie(POR / "n20_m65_com_ema.csv", "reputacao_maliciosa")
    curva(ax, x, y, VERMELHO, ":", "*", "Maliciosos")
    saida["rep"] = salvar(fig, "reputacao.png")

    fig, ax = novo("Acurácia")
    x, y = serie(POR / "n20_m65_com_ema.csv", "acuracia_ponderada")
    curva(ax, x, y, VERMELHO, ":", "*", "EMA")
    x, y = serie(POR / "n20_m65_com_ema_asymmetric.csv", "acuracia_ponderada")
    curva(ax, x, y, MARROM, "--", "P", "EMA assimétrica")
    x, y = serie(POR / "n20_m65_com_beta.csv", "acuracia_ponderada")
    curva(ax, x, y, TEAL, "-.", "X", "Beta")
    saida["mec"] = salvar(fig, "mecanismos.png")
    return saida


class Doc(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("Arial", size=9)
        self.cell(0, 8, str(self.page_no()), align="C")


def paragrafo(pdf: Doc, texto: str) -> None:
    pdf.set_font("Arial", size=11)
    pdf.multi_cell(0, 6, texto)
    pdf.ln(2)


def titulo(pdf: Doc, texto: str) -> None:
    pdf.set_font("Arial", "B", 14)
    pdf.multi_cell(0, 7, texto)
    pdf.ln(2)


def legenda(pdf: Doc, texto: str) -> None:
    pdf.set_font("Arial", "I", 10)
    pdf.multi_cell(0, 5, texto)
    pdf.ln(3)


def tabela(pdf: Doc, cabecalho: list[str], linhas: list[list[str]], larguras: list[float]) -> None:
    pdf.set_font("Arial", "B", 8)
    pdf.set_fill_color(235, 235, 235)
    for texto, largura in zip(cabecalho, larguras):
        pdf.cell(largura, 6.2, texto, border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_font("Arial", size=8)
    for i, linha in enumerate(linhas):
        if pdf.get_y() > 272:
            pdf.add_page()
            pdf.set_font("Arial", "B", 8)
            pdf.set_fill_color(235, 235, 235)
            for texto, largura in zip(cabecalho, larguras):
                pdf.cell(largura, 6.2, texto, border=1, align="C", fill=True)
            pdf.ln()
            pdf.set_font("Arial", size=8)
        if i % 2 == 1:
            pdf.set_fill_color(248, 248, 248)
            preenchido = True
        else:
            preenchido = False
        for texto, largura in zip(linha, larguras):
            pdf.cell(largura, 5.6, texto, border=1, align="C", fill=preenchido)
        pdf.ln()
    pdf.ln(3)


def imagem(pdf: Doc, caminho: Path, legenda_texto: str) -> None:
    pdf.add_page()
    titulo_curto = legenda_texto.split(".")[0]
    pdf.set_font("Arial", "B", 13)
    pdf.multi_cell(0, 7, titulo_curto)
    pdf.ln(2)
    pdf.image(str(caminho), x=12, w=186)
    pdf.ln(2)
    legenda(pdf, legenda_texto)


def montar() -> None:
    imgs = figuras()
    todos = ler(ANALISE / "acuracia_teste_todos_cenarios.csv")
    sessenta = ler(ANALISE / "cenario_65_conluio.csv")
    marcos = [
        row
        for row in ler(ANALISE / "rodadas_10_20_30_40_50.csv")
        if row["cenario"] == "n20_m65_com_ema"
    ]

    pdf = Doc(format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_font("Arial", "", r"C:\Windows\Fonts\arial.ttf")
    pdf.add_font("Arial", "B", r"C:\Windows\Fonts\arialbd.ttf")
    pdf.add_font("Arial", "I", r"C:\Windows\Fonts\ariali.ttf")
    pdf.add_page()

    pdf.set_font("Arial", "B", 16)
    pdf.multi_cell(0, 8, "Resultados com rodadas de teste fixas")
    pdf.ln(3)
    paragrafo(
        pdf,
        "Em todos os experimentos há um teste a cada 10 rodadas: 10, 20, 30, 40 e 50. "
        "A acurácia de teste é a média só nessas rodadas. Os valores são média de 10 sementes. "
        "A rede de referência tem 20 nós e usa o mecanismo EMA. Nessa rede, 65% corresponde a 13 nós maliciosos. "
        "O cenário de 0% não tem variante de conluio, porque não há nós maliciosos.",
    )

    titulo(pdf, "1. A acurácia entre os cenários")
    paragrafo(
        pdf,
        "Sem conluio, a acurácia fica em 1,000 em 0%, 25%, 50% e 65%, tanto no consenso ponderado "
        "quanto na maioria simples. Cada malicioso erra com um valor diferente. Os honestos, com "
        "probabilidade 0,9 de acerto, concentram o voto na resposta certa. Por isso a acurácia parecia "
        "igual entre os cenários: sem um bloco único de votos errados, os dois consensos escolhem a "
        "mesma resposta.",
    )
    paragrafo(
        pdf,
        "A diferença aparece quando os maliciosos votam juntos. Em 20 nós, com conluio e EMA, "
        "25% mantém os dois consensos em 1,000. Em 50% o ponderado continua em 1,000 e a maioria cai "
        "para 0,340. Em 65% o ponderado permanece em 1,000 e a maioria fica em 0,000.",
    )

    ema20 = [row for row in todos if row["nos"] == "20" and row["mecanismo"] == "ema"]
    tabela(
        pdf,
        ["Maliciosos", "Real", "Ponderado sem", "Maioria sem", "Ponderado com", "Maioria com"],
        [
            [
                f"{row['maliciosos_pct']}%",
                f"{br(row['maliciosos_reais'])}%",
                br(row["ponderado_sem_conluio"]),
                br(row["maioria_sem_conluio"]),
                br(row["ponderado_com_conluio"]),
                br(row["maioria_com_conluio"]),
            ]
            for row in ema20
        ],
        [28, 24, 32, 32, 32, 32],
    )
    legenda(pdf, "Tabela 1. Acurácia de teste, 20 nós, EMA. Média das rodadas 10, 20, 30, 40 e 50, entre 10 sementes.")

    titulo(pdf, "2. Rodadas 20 a 30 e rodada 40")
    paragrafo(
        pdf,
        "No cenário de 65% com conluio e 20 nós, a acurácia do consenso ponderado é 0,000 nas rodadas 1 e 2 "
        "e 0,900 na rodada 3. Da rodada 4 em diante ela fica em 1,000. A mudança acontece antes da primeira "
        "rodada de teste.",
    )
    paragrafo(
        pdf,
        "Nas rodadas 20, 30 e 40 a acurácia ponderada é 1,000. Não há um segundo regime de acurácia nesse trecho. "
        "A maioria permanece em 0,000, porque 13 votos iguais vencem 7. O que ainda se move é a reputação: "
        "a dos maliciosos está em 0,014 na rodada 10 e em 0,000 a partir da rodada 20. A dos honestos vai de "
        "0,882 na rodada 20 a 0,909 na rodada 40.",
    )
    tabela(
        pdf,
        ["Rodada", "Ponderado", "Maioria", "Reputação honesta", "Reputação maliciosa"],
        [
            [
                row["rodada"],
                br(row["acuracia_ponderada"]),
                br(row["acuracia_maioria"]),
                br(row["reputacao_honesta"]),
                br(row["reputacao_maliciosa"]),
            ]
            for row in marcos
        ],
        [28, 32, 32, 44, 44],
    )
    legenda(pdf, "Tabela 2. Valores exatamente nas rodadas de teste. 20 nós, 65% em conluio, EMA.")

    titulo(pdf, "3. Cerca de 65% de nós maliciosos")
    paragrafo(
        pdf,
        "Com 13 maliciosos em 20 votando em conluio, o consenso ponderado acerta os cinco testes e a maioria "
        "simples não acerta nenhum. O mesmo ocorre em 15 nós (10/15, 66,67%) e em 10 nós (6/10, 60%). "
        "O limite aparece em 7 nós: a fração nominal 0,65 vira 5 maliciosos em 7, ou 71,43%. Nesse caso a "
        "acurácia ponderada nos testes cai para 0,880, e a da maioria continua em 0,000. Cerca de 65% ainda "
        "é um bom desempenho. Perto de 70%, em rede pequena, a margem começa a faltar.",
    )
    tabela(
        pdf,
        ["Nós", "Real", "Mecanismo", "Ponderado", "Maioria"],
        [
            [
                row["nos"],
                f"{br(row['maliciosos_reais'])}%",
                MECANISMO[row["mecanismo"]],
                br(row["acuracia_ponderada_teste"]),
                br(row["acuracia_maioria_teste"]),
            ]
            for row in sessenta
        ],
        [22, 28, 48, 38, 38],
    )
    legenda(pdf, "Tabela 3. Fração nominal de 65% com conluio. Acurácia de teste, ponderado e maioria.")

    imagem(
        pdf,
        imgs["com"],
        "Figura 1. Acurácia do consenso ponderado por rodada, com conluio, 20 nós, EMA. "
        "A curva de 0% é o cenário sem maliciosos. A série de 65% é a linha vermelha pontilhada com estrela.",
    )
    imagem(
        pdf,
        imgs["sem"],
        "Figura 2. Acurácia do consenso ponderado por rodada, sem conluio, 20 nós, EMA. "
        "As quatro frações permanecem em 1,000.",
    )
    imagem(
        pdf,
        imgs["cmp"],
        "Figura 3. Consenso ponderado e maioria simples, 65% de nós maliciosos em conluio, 20 nós, EMA.",
    )
    imagem(
        pdf,
        imgs["rep"],
        "Figura 4. Reputação média dos honestos e dos maliciosos, 65% em conluio, 20 nós, EMA. "
        "A reputação dos maliciosos é a linha vermelha pontilhada com estrela.",
    )
    imagem(
        pdf,
        imgs["mec"],
        "Figura 5. Acurácia do consenso ponderado por mecanismo, 65% em conluio, 20 nós. "
        "EMA, EMA assimétrica e Beta chegam a 1,000 antes da rodada 10 e permanecem nesse valor nos testes.",
    )

    pdf.add_page()
    titulo(pdf, "Anexo. Acurácia de teste de todos os cenários")
    paragrafo(
        pdf,
        "Cada linha é a média entre 10 sementes, só nas rodadas 10, 20, 30, 40 e 50. "
        "A coluna Real é a fração obtida depois de arredondar o número de nós maliciosos.",
    )
    tabela(
        pdf,
        ["Nós", "%", "Real", "Mecanismo", "Pond. sem", "Mai. sem", "Pond. com", "Mai. com"],
        [
            [
                row["nos"],
                row["maliciosos_pct"],
                br(row["maliciosos_reais"]),
                MECANISMO[row["mecanismo"]],
                br(row["ponderado_sem_conluio"]),
                br(row["maioria_sem_conluio"]),
                br(row["ponderado_com_conluio"]),
                br(row["maioria_com_conluio"]),
            ]
            for row in todos
        ],
        [16, 14, 18, 36, 24, 24, 24, 24],
    )

    pdf.output(str(PDF_PATH))
    print(PDF_PATH)


if __name__ == "__main__":
    montar()
