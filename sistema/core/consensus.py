"""Agregação de respostas por consenso.

São calculadas duas formas de consenso a cada rodada para permitir comparação:

* ``weighted_consensus``: voto ponderado pela reputação de cada nó (proposta do
  trabalho — nós mais confiáveis pesam mais).
* ``majority_consensus``: voto por maioria simples (linha de base sem reputação).

Respostas ausentes (``None``, por timeout ou falha) são ignoradas na agregação.
"""

from __future__ import annotations

from typing import Optional, Sequence

from .answer import Answer, normalize


def weighted_consensus(
    responses: Sequence[tuple[str, Optional[Answer]]],
    reputations: dict[str, float],
) -> tuple[Optional[Answer], dict[Answer, float]]:
    """Retorna a resposta com maior soma de reputação e o placar por resposta."""
    scores: dict[Answer, float] = {}
    for node_id, answer in responses:
        answer = normalize(answer)
        if answer is None:
            continue
        scores[answer] = scores.get(answer, 0.0) + max(0.0, reputations.get(node_id, 0.0))

    if not scores:
        return None, {}
    best = max(scores.items(), key=lambda item: item[1])
    return best[0], scores


def majority_consensus(
    responses: Sequence[tuple[str, Optional[Answer]]],
) -> tuple[Optional[Answer], dict[Answer, int]]:
    """Retorna a resposta mais frequente e a contagem por resposta."""
    counts: dict[Answer, int] = {}
    for _node_id, answer in responses:
        answer = normalize(answer)
        if answer is None:
            continue
        counts[answer] = counts.get(answer, 0) + 1

    if not counts:
        return None, {}
    best = max(counts.items(), key=lambda item: item[1])
    return best[0], counts
