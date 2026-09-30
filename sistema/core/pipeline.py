"""Uma rodada do experimento: consenso → reputação observável → métricas.

Ordem fixa (erro metodológico antigo era inverter 2 e 3):

1. Agregar respostas com as reputações **já conhecidas** (rodada anterior).
2. Atualizar reputação só com acordo ao consenso / ausência de resposta.
3. Comparar o consenso com o gabarito **apenas** para avaliação.
"""

from __future__ import annotations

from typing import Optional

from .answer import Answer
from .consensus import majority_consensus, weighted_consensus
from .enums import EvaluationOutcome, RoundKind, UpdateReason
from .metrics import MetricsLogger
from .node_stats import NodeStats
from .reputation import ReputationTracker
from .reputation_history import ReputationEvent, ReputationHistoryStore
from .schemas import NodeResponse, RoundResult


def run_round(
    *,
    round_index: int,
    task_id: str,
    expected: Optional[Answer],
    responses: list[NodeResponse],
    tracker: ReputationTracker,
    logger: MetricsLogger,
    history: Optional[ReputationHistoryStore] = None,
    stats: Optional[NodeStats] = None,
) -> RoundResult:
    pairs = [(r.node_id, r.answer) for r in responses]
    weights = tracker.weights()
    consensus_weighted, _ = weighted_consensus(pairs, weights)
    consensus_majority, _ = majority_consensus(pairs)
    reference, confidence = tracker.peer_reference(pairs)

    result = RoundResult(
        round_index=round_index,
        task_id=task_id,
        expected=expected,
        consensus_weighted=consensus_weighted,
        consensus_majority=consensus_majority,
        responses=responses,
        consensus_confidence=round(confidence, 4),
    )

    for response in responses:
        gt_correct = response.answer is not None and expected is not None and response.answer == expected
        score = tracker.signal(response.answer, reference, confidence)
        reputation_before = tracker.get(response.node_id)
        if score is None:
            reputation_after = tracker.hold(response.node_id)
            agreed = None
            outcome = EvaluationOutcome.HELD
        elif response.answer is None:
            reputation_after = tracker.update(response.node_id, score)
            agreed = False
            outcome = EvaluationOutcome.TIMEOUT
        else:
            reputation_after = tracker.update(response.node_id, score)
            agreed = bool(score)
            outcome = EvaluationOutcome.HELD

        if history is not None:
            snapshot = stats.for_node(response.node_id) if stats is not None else None
            history.append(
                ReputationEvent.capture(
                    node_id=response.node_id,
                    round_id=str(round_index),
                    round_kind=RoundKind.NORMAL_TASK,
                    reputation_before=reputation_before,
                    reputation_after=reputation_after,
                    stats=snapshot,
                    update_reason=UpdateReason.NORMAL_TASK,
                    evaluation_outcome=outcome,
                )
            )

        logger.record_node(
            round_index=round_index,
            task_id=task_id,
            node_id=response.node_id,
            profile=response.profile,
            answer=response.answer,
            expected=expected,
            correct=gt_correct,
            agreed=agreed,
            reputation_score=score,
            latency_ms=response.latency_ms,
            reputation_before=reputation_before,
            reputation_after=reputation_after,
        )

    logger.record_round(result, num_nodes=len(responses))
    return result
