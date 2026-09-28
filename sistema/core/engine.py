"""Motor de rodada compartilhado entre simulação local e execução em containers.

Extrai toda a lógica pós-coleta de respostas — consenso, avaliação, atualização
de reputação e registro de métricas — de ``simulate.py`` e ``orchestrator/run.py``
para um ponto único.  Isso garante que os dois caminhos de execução utilizem
exatamente o mesmo código e as mesmas estruturas de aleatoriedade (a diferença
entre eles é apenas a *origem* das respostas: comportamento local vs HTTP).

Uso
---
::

    from sistema.core.engine import process_round

    result = process_round(
        round_index=0,
        task_id="sample-0",
        expected=26,
        responses=[...],      # list[NodeResponse]
        tracker=tracker,      # ReputationTracker
        logger=logger,        # MetricsLogger
    )
"""
from __future__ import annotations

import statistics
from typing import Optional

from .answer import Answer, normalize
from .consensus import majority_consensus, weighted_consensus
from .metrics import MetricsLogger
from .reputation import ReputationTracker
from .schemas import NodeResponse, RoundResult


def process_round(
    *,
    round_index: int,
    task_id: str,
    expected: Optional[Answer],
    responses: list[NodeResponse],
    tracker: ReputationTracker,
    logger: MetricsLogger,
    is_test: bool = False,
) -> RoundResult:
    """Processa uma rodada completa após a coleta de respostas.

    Executa em sequência:
    1. Snapshot dos pesos (reputações antes da atualização).
    2. Consenso ponderado e por maioria, com desempate neutro.
    3. Construção do :class:`RoundResult`.
    4. Cálculo das métricas de dispersão das respostas.
    5. Atualização de reputação e log por nó.
    6. Log da rodada.

    Parameters
    ----------
    round_index : int
        Índice zero-based da rodada.
    task_id : str
        Identificador da tarefa GSM8K.
    expected : Optional[Answer]
        Resposta correta (gabarito), ou ``None`` em modo real.
    responses : list[NodeResponse]
        Lista de respostas coletadas de todos os nós nesta rodada.
    tracker : ReputationTracker
        Gerenciador de reputação; atualizado in-place.
    logger : MetricsLogger
        Registrador de métricas; linhas acumuladas in-place.
    is_test : bool
        ``True`` quando esta rodada é uma rodada de teste fixa
        (uma a cada ``test_every`` rodadas). A reputação continua
        sendo atualizada; o flag só marca o ponto de avaliação.

    Returns
    -------
    RoundResult
        Resultado consolidado da rodada (consenso + avaliação).
    """
    # 1. Snapshot dos pesos ANTES da atualização desta rodada.
    weights_before = tracker.weights()

    # 2. Consenso.
    pairs = [(r.node_id, r.answer) for r in responses]
    cons_w = weighted_consensus(pairs, weights_before)
    cons_m = majority_consensus(pairs)

    # 3. RoundResult.
    result = RoundResult(
        round_index=round_index,
        task_id=task_id,
        expected=expected,
        consensus_weighted=cons_w.answer,
        consensus_majority=cons_m.answer,
        responses=list(responses),
    )

    # 4. Métricas de dispersão das respostas desta rodada.
    numeric_answers: list[float] = []
    n_absent = 0
    for r in responses:
        if r.answer is None:
            n_absent += 1
        else:
            try:
                numeric_answers.append(float(r.answer))
            except (TypeError, ValueError):
                pass

    n_distinct = len(set(normalize(r.answer) for r in responses if r.answer is not None))
    std_answers: Optional[float] = None
    median_answers: Optional[float] = None
    mad_answers: Optional[float] = None
    if len(numeric_answers) >= 2:
        std_answers = statistics.stdev(numeric_answers)
    if numeric_answers:
        median_answers = statistics.median(numeric_answers)
        deviations = [abs(v - median_answers) for v in numeric_answers]
        mad_answers = statistics.median(deviations)

    # 5. Atualização de reputação + log por nó.
    for response in responses:
        correct = response.answer is not None and response.answer == expected
        weight_used = weights_before.get(response.node_id, tracker.initial)
        rep_update = tracker.update(response.node_id, correct)

        # Erros absoluto e relativo (observacionais, não usados no score).
        abs_error: Optional[float] = None
        rel_error: Optional[float] = None
        answered = response.answer is not None
        if answered and expected is not None and not correct:
            try:
                abs_error = abs(float(response.answer) - float(expected))
                if float(expected) != 0.0:
                    rel_error = abs_error / abs(float(expected))
            except (TypeError, ValueError):
                pass

        logger.record_node(
            round_index=round_index,
            task_id=task_id,
            node_id=response.node_id,
            profile=response.profile,
            answered=answered,
            answer=response.answer,
            expected=expected,
            correct=correct,
            abs_error=abs_error,
            rel_error=rel_error,
            latency_ms=response.latency_ms,
            score_initial=tracker.initial,
            rep_update=rep_update,
            weight_used=weight_used,
            consensus_weighted_result=cons_w.answer,
            consensus_majority_result=cons_m.answer,
            consensus_weighted_correct=result.consensus_correct,
            consensus_majority_correct=result.majority_correct,
            is_tie_weighted=cons_w.is_tie,
            is_tie_majority=cons_m.is_tie,
            is_test=is_test,
        )

    # 6. Log da rodada.
    logger.record_round(
        result,
        num_nodes=len(responses),
        n_distinct_answers=n_distinct,
        n_absent=n_absent,
        std_answers=std_answers,
        median_answers=median_answers,
        mad_answers=mad_answers,
        consensus_margin_weighted=cons_w.margin,
        consensus_margin_majority=cons_m.margin,
        is_tie_weighted=cons_w.is_tie,
        is_tie_majority=cons_m.is_tie,
        is_test=is_test,
    )

    return result
