"""Distância entre respostas e consenso pelo medoide.

O modo padrão do protocolo continua sendo a igualdade exata. Estas funções só
entram quando ``consensus_mode`` é ``"distance"``.
"""
from __future__ import annotations

from typing import Optional, Sequence

from .answer import Answer, normalize
from .consensus import ConsensusResult


def relative_distance(a: Optional[Answer], b: Optional[Answer]) -> float:
    """Distância relativa em ``[0, 1]``.

    ``|a − b| / (|a| + |b|)``. Zero quando os dois valores são iguais, inclusive
    zero. Um quando qualquer lado não respondeu.
    """
    if a is None or b is None:
        return 1.0
    if a == b:
        return 0.0
    left, right = float(a), float(b)
    return abs(left - right) / (abs(left) + abs(right))


DISTANCES = {"relative": relative_distance}


def medoid(
    answers: Sequence[Optional[Answer]],
    weights: Optional[Sequence[float]] = None,
    distance=relative_distance,
) -> ConsensusResult:
    """Resposta que minimiza a distância ponderada até todas as respostas.

    ``None`` não é candidato, mas entra na soma: a distância até uma resposta
    ausente é 1. Sem pesos, cada resposta pesa 1. Empate fica com o menor
    valor numérico, a mesma regra de :mod:`sistema.core.consensus`.

    O placar guarda o custo de cada candidato (menor é melhor). ``margin`` é a
    folga para o segundo colocado.
    """
    if weights is not None and len(weights) != len(answers):
        raise ValueError("weights e answers precisam ter o mesmo tamanho.")
    rows = []
    for index, raw in enumerate(answers):
        weight = 1.0 if weights is None else float(weights[index])
        rows.append((normalize(raw), weight))

    candidates: list[Answer] = []
    seen: set[Answer] = set()
    for answer, _weight in rows:
        if answer is None or answer in seen:
            continue
        seen.add(answer)
        candidates.append(answer)
    if not candidates:
        return ConsensusResult(answer=None)

    costs: dict[Answer, float] = {}
    for candidate in candidates:
        costs[candidate] = sum(weight * distance(candidate, value) for value, weight in rows)

    def _key(item: tuple[Answer, float]) -> tuple:
        answer, cost = item
        try:
            numeric = float(answer)
        except (TypeError, ValueError):
            numeric = float("inf")
        return (cost, numeric)

    winner, winner_cost = min(costs.items(), key=_key)
    ordered = sorted(costs.values())
    second = ordered[1] if len(ordered) > 1 else winner_cost
    tied = len(ordered) > 1 and winner_cost == ordered[1]
    return ConsensusResult(
        answer=winner,
        scores=costs,
        is_tie=tied,
        margin=round(second - winner_cost, 6),
        winner_score=round(winner_cost, 6),
    )


def weighted_medoid(responses: Sequence[tuple[str, Optional[Answer]]], reputations: dict[str, float]) -> ConsensusResult:
    """Medoide ponderado pela reputação. Reputação negativa pesa zero."""
    answers = [answer for _node, answer in responses]
    weights = [max(0.0, reputations.get(node, 0.0)) for node, _answer in responses]
    return medoid(answers, weights)


def plain_medoid(responses: Sequence[tuple[str, Optional[Answer]]]) -> ConsensusResult:
    """Medoide sem peso: a linha de base no lugar da maioria simples."""
    return medoid([answer for _node, answer in responses])
