"""Agregação de respostas por consenso.

São calculadas duas formas de consenso a cada rodada para permitir comparação:

* ``weighted_consensus`` : voto ponderado pela reputação de cada nó (proposta).
* ``majority_consensus`` : voto por maioria simples (linha de base).

Respostas ausentes (``None``) são ignoradas na agregação.

Desempate
---------
Em caso de empate de pontuação/contagem, a regra é: escolher o **menor valor
numérico** entre os empatados.  Essa regra é determinística e independente da
ordem de inserção dos votos no dicionário interno — ao contrário do ``max()``
sobre dicionários, cujo comportamento em empate depende da ordem de iteração
(favorecia o bloco malicioso, que tem índices menores e era inserido primeiro).

Retorno estruturado
-------------------
Ambas as funções retornam um :class:`ConsensusResult` que inclui o placar
completo de votos/pesos, o flag ``is_tie`` e a margem de vitória — dados que
antes eram descartados com ``_`` nos chamadores.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from .answer import Answer, normalize


@dataclass
class ConsensusResult:
    """Resultado estruturado de uma função de consenso.

    Attributes
    ----------
    answer : Optional[Answer]
        Resposta vencedora; ``None`` se não houve respostas.
    scores : dict
        Placar completo: ``{valor: pontuação_ou_contagem}``.
    is_tie : bool
        ``True`` se dois ou mais valores empataram na pontuação máxima.
    margin : float
        Diferença entre o vencedor e o segundo colocado (0 se há apenas 1 valor).
    winner_score : float
        Pontuação / contagem da resposta vencedora.
    """

    answer: Optional[Answer]
    scores: dict = field(default_factory=dict)
    is_tie: bool = False
    margin: float = 0.0
    winner_score: float = 0.0


def _tiebreak_key(item: tuple) -> tuple:
    """Chave de ordenação para desempate: maior score, depois menor valor numérico."""
    answer_val, score = item
    try:
        numeric = float(answer_val)
    except (TypeError, ValueError):
        numeric = float("inf")
    # Negamos numeric para que valores menores ganhem o max() em caso de empate.
    return (score, -numeric)


def weighted_consensus(
    responses: Sequence[tuple[str, Optional[Answer]]],
    reputations: dict[str, float],
) -> ConsensusResult:
    """Consenso ponderado pela reputação dos nós.

    Parameters
    ----------
    responses : Sequence[tuple[str, Optional[Answer]]]
        Pares ``(node_id, answer)`` de todos os nós consultados.
    reputations : dict[str, float]
        Mapa ``node_id → reputação`` usado como peso.

    Returns
    -------
    ConsensusResult
        Resultado completo incluindo placar, is_tie e margem.
    """
    scores: dict[Answer, float] = {}
    for node_id, answer in responses:
        answer = normalize(answer)
        if answer is None:
            continue
        scores[answer] = scores.get(answer, 0.0) + max(0.0, reputations.get(node_id, 0.0))

    if not scores:
        return ConsensusResult(answer=None)

    best_item = max(scores.items(), key=_tiebreak_key)
    winner_score = best_item[1]
    sorted_vals = sorted(scores.values(), reverse=True)
    second_score = sorted_vals[1] if len(sorted_vals) > 1 else 0.0
    is_tie = len(sorted_vals) > 1 and winner_score == sorted_vals[1]

    return ConsensusResult(
        answer=best_item[0],
        scores=scores,
        is_tie=is_tie,
        margin=round(winner_score - second_score, 6),
        winner_score=round(winner_score, 6),
    )


def majority_consensus(
    responses: Sequence[tuple[str, Optional[Answer]]],
) -> ConsensusResult:
    """Consenso por maioria simples (um voto por nó).

    Parameters
    ----------
    responses : Sequence[tuple[str, Optional[Answer]]]
        Pares ``(node_id, answer)`` de todos os nós consultados.

    Returns
    -------
    ConsensusResult
        Resultado completo incluindo contagem, is_tie e margem.
    """
    counts: dict[Answer, int] = {}
    for _node_id, answer in responses:
        answer = normalize(answer)
        if answer is None:
            continue
        counts[answer] = counts.get(answer, 0) + 1

    if not counts:
        return ConsensusResult(answer=None)

    best_item = max(counts.items(), key=_tiebreak_key)
    winner_count = float(best_item[1])
    sorted_vals = sorted(counts.values(), reverse=True)
    second_count = float(sorted_vals[1]) if len(sorted_vals) > 1 else 0.0
    is_tie = len(sorted_vals) > 1 and winner_count == sorted_vals[1]

    return ConsensusResult(
        answer=best_item[0],
        scores={k: float(v) for k, v in counts.items()},
        is_tie=is_tie,
        margin=round(winner_count - second_count, 6),
        winner_score=winner_count,
    )
