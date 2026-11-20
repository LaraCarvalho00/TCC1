"""Figuras da história incremental. Não substitui os gráficos do artigo."""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BLUE = "#24629f"
ORANGE = "#d26a22"
GREEN = "#187952"
GRAY = "#666b73"
BLACK = "#202632"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _save(fig, directory: Path, name: str) -> None:
    for ext in ("png", "pdf"):
        fig.savefig(directory / f"{name}.{ext}", dpi=220, facecolor="white")
    plt.close(fig)


def _pick(rows, **filters):
    found = [row for row in rows if all(str(row[key]) == str(value) for key, value in filters.items())]
    if len(found) != 1:
        raise ValueError(f"Esperava uma linha para {filters}; achei {len(found)}")
    return found[0]


def _xy(etapas, spec, etapa, conluio, fracoes, audit_p=None):
    xs, ys, err = [], [], []
    for fracao in fracoes:
        filters = {"etapa": etapa, "conluio": conluio, "fracao": fracao}
        if audit_p is not None:
            filters["audit_p"] = audit_p
        row = _pick(etapas, **filters)
        xs.append(int(round(fracao * spec["nos"])))
        ys.append(float(row["acuracia_media"]))
        err.append(float(row["acuracia_dp"]))
    return xs, ys, err


def _style(ax):
    ax.set_ylim(0, 100)
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlabel("Nós maliciosos na rede")
    ax.set_ylabel("Acurácia média (%)")


def _caption(fonte: str, spec: dict) -> str:
    rotulo = spec.get("rotulo_banco") or "banco (20 amostras/questão, sem nova inferência)"
    modelo = spec.get("modelo_nome") or ""
    origem = rotulo if fonte == "banco" else f"inferência ao vivo · {modelo}".strip(" ·")
    return (
        f"{spec['nos']} nós · {spec['rodadas']} rodadas · {len(spec['sementes'])} semente(s) · {origem}. "
        "Barras: desvio-padrão amostral. Sem gênese. Nas etapas 1–4 o malicioso coopera nas rodadas 10, 20, 30, 40 e 50."
    )


def gerar(saida: Path, spec: dict, fonte: str = "banco") -> Path:
    etapas = _rows(saida / "etapas.csv")
    reputacao = _rows(saida / "reputacao_por_rodada.csv")
    output = saida / "graficos"
    output.mkdir(parents=True, exist_ok=True)
    fracoes = [f for f in spec["fracoes"] if f > 0]
    ps = list(spec["ps"])
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    rodape = _caption(fonte, spec)

    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    fig.suptitle("Etapa 1 · Caso base", fontsize=16, weight="bold", x=0.08, y=0.98, ha="left")
    fig.text(0.08, 0.91, "0% maliciosos · medoide sem pesos · sem auditoria", fontsize=10, color=GRAY, ha="left")
    base = _pick(etapas, etapa=1, conluio=0, fracao=0.0)
    ax.bar([0], [float(base["acuracia_media"])], color=BLUE, width=0.45,
           yerr=[float(base["acuracia_dp"])], capsize=4)
    ax.set_xticks([0], ["0 maliciosos"])
    _style(ax)
    ax.set_xlabel("")
    fig.text(0.08, 0.03, rodape, fontsize=8, color=GRAY, wrap=True)
    fig.subplots_adjust(left=0.14, right=0.96, top=0.82, bottom=0.18)
    _save(fig, output, "01_etapa1_caso_base")

    fig, ax = plt.subplots(figsize=(10.4, 5.8))
    fig.suptitle("Etapa 2 · Entram os maliciosos", fontsize=16, weight="bold", x=0.08, y=0.98, ha="left")
    fig.text(0.08, 0.91, "Sem conluio · sem reputação ponderada (medoide sem pesos)", fontsize=10, color=GRAY, ha="left")
    xs, ys, err = _xy(etapas, spec, 2, 0, fracoes)
    ax.errorbar(xs, ys, yerr=err, color=BLACK, marker="x", linestyle="--", capsize=4, linewidth=2, label="Sem reputação")
    _style(ax)
    ax.legend(frameon=False)
    fig.text(0.08, 0.03, rodape, fontsize=8, color=GRAY)
    fig.subplots_adjust(left=0.1, right=0.97, top=0.82, bottom=0.18)
    _save(fig, output, "02_etapa2_maliciosos")

    fig, ax = plt.subplots(figsize=(10.4, 5.8))
    fig.suptitle("Etapa 3 · Entra o conluio", fontsize=16, weight="bold", x=0.08, y=0.98, ha="left")
    fig.text(0.08, 0.91, "Mesmas respostas da etapa 4 · medoide sem pesos", fontsize=10, color=GRAY, ha="left")
    xs, ys, err = _xy(etapas, spec, 2, 0, fracoes)
    ax.errorbar(xs, ys, yerr=err, color=GRAY, marker="x", linestyle="--", capsize=4, linewidth=2, label="Sem conluio")
    xs, ys, err = _xy(etapas, spec, 3, 1, fracoes)
    ax.errorbar(xs, ys, yerr=err, color=ORANGE, marker="o", capsize=4, linewidth=2, label="Com conluio")
    _style(ax)
    ax.legend(frameon=False)
    fig.text(0.08, 0.03, rodape, fontsize=8, color=GRAY)
    fig.subplots_adjust(left=0.1, right=0.97, top=0.82, bottom=0.18)
    _save(fig, output, "03_etapa3_conluio")

    fig, axes = plt.subplots(1, 2, figsize=(12, 6.2), sharey=True)
    fig.suptitle("Etapa 4 · Reputação por consenso", fontsize=16, weight="bold", x=0.08, y=0.98, ha="left")
    fig.text(0.08, 0.91, "Sem auditoria · EMA simétrica αc=0,05 αv=0,95", fontsize=10, color=GRAY, ha="left")
    for ax, collusion, title, etapa_sem in zip(axes, (0, 1), ("Sem conluio", "Com conluio"), (2, 3)):
        xs, ys, err = _xy(etapas, spec, etapa_sem, collusion, fracoes)
        ax.errorbar(xs, ys, yerr=err, color=BLACK, marker="x", linestyle="--", capsize=3, linewidth=1.8, label="Sem reputação")
        xs, ys, err = _xy(etapas, spec, 4, collusion, fracoes)
        ax.errorbar(xs, ys, yerr=err, color=BLUE, marker="o", capsize=3, linewidth=2, label="Com reputação")
        ax.set_title(title, loc="left", fontsize=12, weight="bold")
        _style(ax)
        if collusion:
            ax.set_ylabel("")
    axes[0].legend(frameon=False)
    fig.text(0.08, 0.03, rodape, fontsize=8, color=GRAY)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.82, bottom=0.18, wspace=0.12)
    _save(fig, output, "04_etapa4_reputacao")

    fig, axes = plt.subplots(1, 2, figsize=(12, 6.4), sharey=True)
    fig.suptitle("Etapa 5 · Auditoria por sorteio", fontsize=16, weight="bold", x=0.08, y=0.98, ha="left")
    fig.text(0.08, 0.91, "Nota exata · reputação ponderada nas rodadas sem gabarito", fontsize=10, color=GRAY, ha="left")
    estilos = {0.1: (BLUE, "^", "p = 0,1"), 0.2: (GREEN, "D", "p = 0,2")}
    for ax, collusion, title in zip(axes, (0, 1), ("Sem conluio", "Com conluio")):
        xs, ys, err = _xy(etapas, spec, 4, collusion, fracoes)
        ax.errorbar(xs, ys, yerr=err, color=GRAY, marker="o", linestyle="--", capsize=3, linewidth=1.6, label="Sem auditoria")
        for p in ps:
            xs, ys, err = _xy(etapas, spec, 5, collusion, fracoes, audit_p=p)
            color, marker, label = estilos[p]
            ax.errorbar(xs, ys, yerr=err, color=color, marker=marker, capsize=3, linewidth=2, label=label)
        ax.set_title(title, loc="left", fontsize=12, weight="bold")
        _style(ax)
        if collusion:
            ax.set_ylabel("")
    axes[0].legend(frameon=False)
    fig.text(0.08, 0.03, rodape, fontsize=8, color=GRAY)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.82, bottom=0.18, wspace=0.12)
    _save(fig, output, "05_etapa5_auditoria")

    fig, ax = plt.subplots(figsize=(10.4, 5.8))
    fig.suptitle("Etapa 6 · Nota graduada × exata", fontsize=16, weight="bold", x=0.08, y=0.98, ha="left")
    fig.text(0.08, 0.91, "Conluio · sorteio p = 0,2", fontsize=10, color=GRAY, ha="left")
    xs, ys, err = _xy(etapas, spec, 5, 1, fracoes, audit_p=0.2)
    ax.errorbar(xs, ys, yerr=err, color=BLUE, marker="o", capsize=4, linewidth=2, label="Nota exata")
    xs, ys, err = _xy(etapas, spec, 6, 1, fracoes, audit_p=0.2)
    ax.errorbar(xs, ys, yerr=err, color=ORANGE, marker="s", capsize=4, linewidth=2, label="Nota graduada")
    _style(ax)
    ax.legend(frameon=False)
    fig.text(0.08, 0.03, rodape, fontsize=8, color=GRAY)
    fig.subplots_adjust(left=0.1, right=0.97, top=0.82, bottom=0.18)
    _save(fig, output, "06_etapa6_nota")

    fig, ax = plt.subplots(figsize=(10.4, 5.8))
    fig.suptitle("Etapa 7 · Nós instáveis", fontsize=16, weight="bold", x=0.08, y=0.98, ha="left")
    fig.text(0.08, 0.91, "Conluio · p = 0,2 · nota exata · 20% instáveis (attribute)", fontsize=10, color=GRAY, ha="left")
    xs, ys, err = _xy(etapas, spec, 5, 1, fracoes, audit_p=0.2)
    ax.errorbar(xs, ys, yerr=err, color=BLUE, marker="o", capsize=4, linewidth=2, label="0% instáveis")
    xs, ys, err = _xy(etapas, spec, 7, 1, fracoes, audit_p=0.2)
    ax.errorbar(xs, ys, yerr=err, color=ORANGE, marker="s", capsize=4, linewidth=2, label="20% instáveis")
    _style(ax)
    ax.legend(frameon=False)
    fig.text(0.08, 0.03, rodape, fontsize=8, color=GRAY)
    fig.subplots_adjust(left=0.1, right=0.97, top=0.82, bottom=0.18)
    _save(fig, output, "07_etapa7_instaveis")

    fig, axes = plt.subplots(1, 2, figsize=(12, 6.4), sharey=True)
    fig.suptitle("Síntese · evolução das defesas", fontsize=16, weight="bold", x=0.08, y=0.98, ha="left")
    fig.text(0.08, 0.91, "Uma mudança por etapa; p = 0,2 na auditoria", fontsize=10, color=GRAY, ha="left")
    for ax, collusion, title, etapa_sem in zip(axes, (0, 1), ("Sem conluio", "Com conluio"), (2, 3)):
        for etapa, label, color, marker, style in (
            (etapa_sem, "Sem reputação", BLACK, "x", "--"),
            (4, "Reputação", GRAY, "o", "-"),
            (5, "Auditoria p = 0,2", GREEN, "D", "-"),
        ):
            xs, ys, err = _xy(etapas, spec, etapa, collusion, fracoes, audit_p=0.2 if etapa == 5 else None)
            ax.errorbar(xs, ys, yerr=err, color=color, marker=marker, linestyle=style, capsize=3, linewidth=2, label=label)
        ax.set_title(title, loc="left", fontsize=12, weight="bold")
        _style(ax)
        if collusion:
            ax.set_ylabel("")
    axes[0].legend(frameon=False)
    fig.text(0.08, 0.03, rodape, fontsize=8, color=GRAY)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.82, bottom=0.18, wspace=0.12)
    _save(fig, output, "08_sintese_evolucao")

    fig, axes = plt.subplots(1, 2, figsize=(12, 6.2), sharey=True)
    fig.suptitle("Reputação por rodada · etapa 5", fontsize=16, weight="bold", x=0.08, y=0.98, ha="left")
    fig.text(0.08, 0.91, "Conluio · p = 0,2 · nota exata", fontsize=10, color=GRAY, ha="left")
    alvos = [fracoes[min(len(fracoes) - 1, 1)], fracoes[-1]]
    for ax, fracao in zip(axes, alvos):
        selected = [row for row in reputacao if row["etapa"] == "5" and row["conluio"] == "1"
                    and abs(float(row["fracao"]) - fracao) < 1e-9 and row["nota"] == "exact"
                    and abs(float(row["fracao_instavel"])) < 1e-9]
        selected = sorted(selected, key=lambda row: int(row["rodada"]))
        ax.plot([int(row["rodada"]) for row in selected],
                [float(row["reputacao_media_honestos"]) for row in selected],
                color=BLUE, linewidth=2, label="Honestos")
        ax.plot([int(row["rodada"]) for row in selected],
                [float(row["reputacao_media_maliciosos"]) for row in selected],
                color=ORANGE, linewidth=2, label="Maliciosos")
        ax.set_title(f"{int(round(fracao * spec['nos']))} maliciosos", loc="left", fontsize=12, weight="bold")
        ax.set_xlabel("Rodadas concluídas")
        ax.set_ylim(0, 1)
        ax.grid(axis="y", alpha=0.22)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Reputação média")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, 0.04))
    fig.text(0.08, 0.02, rodape, fontsize=8, color=GRAY)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.82, bottom=0.2, wspace=0.12)
    _save(fig, output, "09_reputacao_etapa5")

    (output / "LEGENDA.md").write_text(
        f"""# Gráficos incrementais ({fonte})

{_caption(fonte, spec)}

01. Etapa 1 — caso base (0% maliciosos, sem reputação).
02. Etapa 2 — maliciosos sem conluio, medoide sem pesos.
03. Etapa 3 — o mesmo com conluio.
04. Etapa 4 — reputação por consenso, com e sem conluio.
05. Etapa 5 — auditoria por sorteio (p do recorte).
06. Etapa 6 — nota graduada versus exata, conluio, p = 0,2.
07. Etapa 7 — 20% de nós instáveis.
08. Síntese da evolução das defesas.
09. Reputação honesto/malicioso na etapa 5.

Não substitui as 3.670 execuções nem as figuras do artigo.
""",
        encoding="utf-8",
    )
    return output
