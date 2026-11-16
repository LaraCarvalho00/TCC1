"""Gráficos de uma avaliação nova de inferência a partir do progresso JSONL.

Só aceita uma avaliação completa: 50 questões no modo guloso e cinco amostras
para cada uma das dez primeiras. Não lê nem compara o banco histórico.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sistema.core.answer import normalize


def carregar_progresso(path: Path) -> tuple[list[dict], list[dict]]:
    """Valida a cobertura, a identidade das questões e as respostas registradas."""
    records = []
    with path.open(encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            if not line.strip():
                raise ValueError(f"Linha {number} vazia")
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Linha {number} não é JSON válido") from exc
            if not isinstance(entry, dict):
                raise ValueError(f"Linha {number} deve conter um objeto")
            records.append(entry)
    greedy, samples = {}, {}
    for entry in records:
        if not {"questao", "id_questao", "modo", "amostra", "previsto", "esperado", "correto"}.issubset(entry):
            raise ValueError("Registro sem campos obrigatórios")
        question = entry.get("questao")
        mode = entry.get("modo")
        sample = entry.get("amostra")
        if type(question) is not int or not 1 <= question <= 50:
            raise ValueError("Número de questão inválido")
        if mode == "gulosa" and sample is None:
            target, key = greedy, question
        elif mode == "amostragem" and question <= 10 and type(sample) is int and 1 <= sample <= 5:
            target, key = samples, (question, sample)
        else:
            raise ValueError("Modo, questão ou número de amostra inválido")
        if key in target:
            raise ValueError(f"Registro duplicado: {mode} {key}")
        if not isinstance(entry.get("id_questao"), str) or not entry["id_questao"]:
            raise ValueError("Identificador da questão ausente")
        expected, predicted = entry.get("esperado"), entry.get("previsto")
        if type(expected) not in (int, float) or not math.isfinite(expected):
            raise ValueError("Gabarito inválido")
        if predicted is not None and (type(predicted) not in (int, float) or not math.isfinite(predicted)):
            raise ValueError("Resposta prevista inválida")
        correct = predicted is not None and normalize(predicted) == normalize(expected)
        if type(entry.get("correto")) is not bool or entry["correto"] != correct:
            raise ValueError("Indicador de acerto incompatível com a resposta e o gabarito")
        elapsed = entry.get("duracao_segundos")
        if elapsed is not None and (type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0):
            raise ValueError("Duração inválida")
        target[key] = entry
    if set(greedy) != set(range(1, 51)) or set(samples) != {(q, s) for q in range(1, 11) for s in range(1, 6)}:
        raise ValueError("Progresso incompleto: são necessárias 50 respostas gulosas e 5 amostras para cada uma das 10 primeiras questões")
    if len({entry["id_questao"] for entry in greedy.values()}) != 50:
        raise ValueError("As 50 questões devem ter identificadores distintos")
    for (question, _), entry in samples.items():
        original = greedy[question]
        if entry["id_questao"] != original["id_questao"] or normalize(entry["esperado"]) != normalize(original["esperado"]):
            raise ValueError(f"Amostra incompatível com a questão {question} do modo guloso")
    return [greedy[i] for i in range(1, 51)], [samples[q, s] for q in range(1, 11) for s in range(1, 6)]


def _salvar(fig, directory: Path, name: str) -> None:
    fig.savefig(directory / f"{name}.png", dpi=200, facecolor="white")
    fig.savefig(directory / f"{name}.pdf", facecolor="white")
    plt.close(fig)


def gerar(progresso: Path, saida: Path) -> dict:
    greedy, samples = carregar_progresso(progresso)
    # Verifica a entrada antes de criar saída, que nunca substitui outra execução.
    saida.mkdir(parents=True, exist_ok=False)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(12, 4.9))
    values = [int(row["correto"]) for row in greedy]
    count = sum(values)
    for value, color, label in ((1, "#23734b", "Correta"), (0, "#bd4f44", "Incorreta ou ausente")):
        indices = [index for index, result in enumerate(values, 1) if result == value]
        ax.scatter(indices, [value] * len(indices), color=color, s=35, label=label)
    ax.set_ylim(-0.25, 1.25); ax.set_yticks([0, 1], ["Incorreta ou ausente", "Correta"])
    ax.set_xticks([1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50]); ax.set_xlabel("Questão")
    fig.suptitle(f"Avaliação gulosa: {count}/50 corretas ({count * 2}%)", x=0.20, y=0.98, ha="left", fontsize=15, weight="bold")
    fig.text(0.20, 0.89, "Uma resposta por questão; 50 questões, comparação exata com o gabarito.", color="#575f6a")
    ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", alpha=0.2)
    fig.subplots_adjust(left=0.20, right=0.97, top=0.77, bottom=0.16)
    _salvar(fig, saida, "01_acertos_gulosos")

    fig, ax = plt.subplots(figsize=(10.5, 5))
    by_question = [sum(row["correto"] for row in samples if row["questao"] == q) for q in range(1, 11)]
    sample_hits = sum(by_question)
    ax.bar(range(1, 11), by_question, color="#27639c", width=0.7, label="Respostas corretas")
    for q, hits in enumerate(by_question, 1):
        ax.text(q, hits + 0.07, f"{hits}/5", ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, 6); ax.set_yticks(range(6)); ax.set_xticks(range(1, 11))
    ax.set_xlabel("Questão (primeiras 10)"); ax.set_ylabel("Respostas corretas entre 5")
    fig.suptitle(f"Amostragem: {sample_hits}/50 respostas corretas ({sample_hits * 2}%)", x=0.10, y=0.98, ha="left", fontsize=15, weight="bold")
    fig.text(0.10, 0.89, "Cinco respostas para cada uma das 10 questões; não são 50 questões independentes.", color="#575f6a")
    ax.spines[["top", "right"]].set_visible(False); ax.set_axisbelow(True); ax.grid(axis="y", alpha=0.2)
    fig.subplots_adjust(left=0.10, right=0.97, top=0.77, bottom=0.15)
    _salvar(fig, saida, "02_amostras_por_questao")

    durations = [row.get("duracao_segundos") for row in greedy + samples]
    have_durations = all(value is not None for value in durations)
    if have_durations:
        fig, ax = plt.subplots(figsize=(9.4, 5.2))
        groups = ([row["duracao_segundos"] for row in greedy], [row["duracao_segundos"] for row in samples])
        for position, (values_, color, label) in enumerate(zip(groups, ("#27639c", "#d57524"), ("Gulosa", "Amostragem")), 1):
            # Pequeno deslocamento determinístico apenas para evitar sobreposição visual.
            jitter = [position + ((index % 9) - 4) * 0.015 for index in range(len(values_))]
            ax.scatter(jitter, values_, color=color, alpha=0.55, s=19, label=f"{label}: {len(values_)} chamadas")
            ax.plot([position - 0.19, position + 0.19], [statistics.mean(values_)] * 2, color="#252b35", linewidth=2)
        ax.set_xticks([1, 2], ["Gulosa\n50 questões", "Amostragem\n5 respostas × 10 questões"])
        ax.set_ylabel("Duração por chamada (segundos)")
        fig.suptitle("Tempo das chamadas de inferência", x=0.13, y=0.98, ha="left", fontsize=15, weight="bold")
        fig.text(0.13, 0.89, "Pontos: chamadas registradas; traço preto: média. As condições têm questões e modos distintos.", color="#575f6a", fontsize=9)
        ax.set_axisbelow(True); ax.grid(axis="y", alpha=0.2); ax.spines[["top", "right"]].set_visible(False)
        fig.subplots_adjust(left=0.13, right=0.97, top=0.77, bottom=0.17)
        _salvar(fig, saida, "03_tempos_por_chamada")

    explanation = [
        "# Avaliação nova de inferência", "",
        "Os dados destas figuras vêm exclusivamente do JSONL de progresso indicado no manifesto. Eles não usam o banco histórico de respostas pré-geradas.", "",
        f"1. **Geração gulosa:** {count} acertos em 50 questões, uma resposta por questão. Comparação exata da resposta numérica extraída com o gabarito; respostas ausentes contam como erro.",
        f"2. **Amostragem:** {sample_hits} acertos em 50 respostas, sendo cinco respostas para cada uma das dez primeiras questões. As respostas da mesma questão não são 50 questões independentes. O gráfico mostra acertos por questão.",
    ]
    if have_durations:
        explanation.append("3. **Tempos:** uma observação por chamada concluída, em segundos; traços horizontais indicam a média de cada grupo. A amostragem tem cinco chamadas por questão e os grupos usam modos e conjuntos de questões diferentes. Os tempos não incluem carga do modelo nem constituem uma comparação controlada de desempenho.")
    else:
        explanation.append("Tempos não foram apresentados porque não havia duração registrada para todas as chamadas.")
    explanation += ["", "Nenhuma barra representa intervalo de confiança ou teste de significância."]
    (saida / "LEGENDA_E_METODOLOGIA.md").write_text("\n".join(explanation) + "\n", encoding="utf-8")
    manifest = {
        "fonte": str(progresso.resolve()), "sha256_fonte": hashlib.sha256(progresso.read_bytes()).hexdigest(),
        "questoes_gulosas": 50, "acertos_gulosos": count,
        "questoes_amostragem": 10, "amostras_por_questao": 5, "acertos_amostragem": sample_hits,
        "duracoes_completas": have_durations,
        "observacao": "Dados da execução nova; não reutilizam respostas do banco histórico.",
    }
    (saida / "manifesto.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gera figuras a partir de um progresso completo de inferência")
    parser.add_argument("--progresso", required=True, type=Path)
    parser.add_argument("--saida", required=True, type=Path, help="Pasta nova para figuras")
    args = parser.parse_args(argv)
    try:
        result = gerar(args.progresso, args.saida)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Não foi possível gerar os gráficos: {exc}", file=sys.stderr)
        return 1
    print(f"Gráficos gerados em {args.saida.resolve()}: {result['acertos_gulosos']}/50 gulosas; {result['acertos_amostragem']}/50 amostras")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
