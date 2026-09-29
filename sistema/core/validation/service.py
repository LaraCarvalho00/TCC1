"""Orquestra uma Validation Round sem passar pelo consenso."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..enums import EvaluationOutcome, RoundKind, UpdateReason, ValidationStatus
from ..metrics import MetricsLogger
from ..node_stats import NodeStats
from ..reputation import ReputationTracker
from ..reputation_history import ReputationEvent, ReputationHistoryStore
from .dataset import ValidationQuestion
from .evaluator import ValidationEvaluator
from .models import NodeSpec, ValidationResult, ValidationRound
from .store import ValidationStore
from .transport import NodeClient, NodeReply

logger = logging.getLogger("sistema.validation")


class ValidationRoundService:
    def __init__(
        self,
        *,
        tracker: ReputationTracker,
        client: NodeClient,
        store: ValidationStore,
        history: ReputationHistoryStore,
        stats: NodeStats,
        evaluator: Optional[ValidationEvaluator] = None,
        metrics: Optional[MetricsLogger] = None,
    ) -> None:
        self.tracker = tracker
        self.client = client
        self.store = store
        self.history = history
        self.stats = stats
        self.evaluator = evaluator or ValidationEvaluator()
        self.metrics = metrics

    def start(
        self,
        *,
        round_number: int,
        nodes: list[NodeSpec],
        questions: list[ValidationQuestion],
        seed: int,
        dataset_version: str,
        round_id: Optional[str] = None,
    ) -> ValidationRound:
        if not nodes or not questions:
            raise ValueError("Validação exige nós e perguntas.")
        if len({n.node_id for n in nodes}) != len(nodes):
            raise ValueError("IDs de nós duplicados.")
        if len({q.question_id for q in questions}) != len(questions):
            raise ValueError("IDs de perguntas duplicados.")
        round_ = ValidationRound(
            id=round_id or str(uuid.uuid4()),
            round_number=round_number,
            status=ValidationStatus.PENDING,
            dataset_version=dataset_version,
            total_questions=len(questions),
            total_nodes=len(nodes),
            seed=seed,
        )
        self.store.save_round(round_)
        started = time.perf_counter()
        round_.started_at = datetime.now(timezone.utc).isoformat()
        round_.status = ValidationStatus.RUNNING
        self.store.save_round(round_)
        _log(
            "validation_round_started",
            round_id=round_.id,
            round_number=round_number,
            questions=len(questions),
            nodes=len(nodes),
        )

        try:
            for question in questions:
                for node in nodes:
                    self._process_pair(round_, node, question)
            round_.status = ValidationStatus.COMPLETED
            _log("validation_round_completed", round_id=round_.id, round_number=round_number)
        except Exception:
            round_.status = ValidationStatus.FAILED
            _log("validation_round_failed", round_id=round_.id, round_number=round_number)
            logger.exception("validation_round_failed")
            raise
        finally:
            round_.finished_at = datetime.now(timezone.utc).isoformat()
            round_.duration_s = round(time.perf_counter() - started, 6)
            self._refresh_totals(round_)
            self.store.save_round(round_)
            if self.metrics is not None:
                self.metrics.record_validation(round_, self.stats)
        return round_

    def _process_pair(self, round_: ValidationRound, node: NodeSpec, question: ValidationQuestion) -> None:
        existing = self.store.find_result(round_.id, node.node_id, question.question_id)
        if existing is not None:
            return

        _log(
            "validation_question_sent",
            round_id=round_.id,
            node_id=node.node_id,
            question_id=question.question_id,
        )
        try:
            reply = self.client.ask(node, question.question_id, question.prompt)
        except Exception:
            logger.exception("node_error")
            reply = NodeReply(
                node_id=node.node_id,
                question_id=question.question_id,
                answer=None,
                outcome_hint=EvaluationOutcome.ERROR,
                payload_sent={"task_id": question.question_id, "question": question.prompt},
            )
        _assert_no_ground_truth(reply.payload_sent)
        _log(
            "validation_result_received",
            round_id=round_.id,
            node_id=node.node_id,
            question_id=question.question_id,
            outcome_hint=reply.outcome_hint,
        )

        try:
            outcome = self.evaluator.evaluate(reply, question.expected_answer)
        except Exception:
            outcome = EvaluationOutcome.ERROR
            logger.exception("evaluator_failed")

        is_correct = self.evaluator.is_correct(outcome)
        _log(
            "validation_result_evaluated",
            round_id=round_.id,
            node_id=node.node_id,
            question_id=question.question_id,
            outcome=outcome,
        )

        reputation_before = self.tracker.get(node.node_id)
        created_stats = False
        if outcome == EvaluationOutcome.CORRECT:
            update = self.tracker.update(node.node_id, True)
            self.stats.apply(node.node_id, outcome)
            created_stats = True
        elif outcome == EvaluationOutcome.INCORRECT:
            update = self.tracker.update(node.node_id, False)
            self.stats.apply(node.node_id, outcome)
            created_stats = True
        else:
            update = self.tracker.hold(node.node_id)

        reputation_after = self.tracker.get(node.node_id)

        snapshot = self.stats.for_node(node.node_id)
        self.history.append(
            ReputationEvent.capture(
                node_id=node.node_id,
                round_id=round_.id,
                round_kind=RoundKind.VALIDATION_ROUND,
                reputation_before=reputation_before,
                reputation_after=reputation_after,
                stats=snapshot,
                update_reason=UpdateReason.VALIDATION_ROUND,
                evaluation_outcome=outcome,
            )
        )
        _log(
            "reputation_updated",
            round_id=round_.id,
            node_id=node.node_id,
            reason=UpdateReason.VALIDATION_ROUND,
            outcome=outcome,
            counted=created_stats,
        )

        result = ValidationResult(
            id=str(uuid.uuid4()),
            validation_round_id=round_.id,
            node_id=node.node_id,
            question_id=question.question_id,
            node_answer=reply.answer,
            expected_answer=question.expected_answer,
            outcome=outcome,
            is_correct=is_correct,
            reputation_before=reputation_before,
            reputation_after=reputation_after,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.store.add_result(result)
        if self.metrics is not None:
            self.metrics.record_validation_update(round_, node, question, outcome, update)

    def _refresh_totals(self, round_: ValidationRound) -> None:
        items = [
            item for item in self.store.results if item.validation_round_id == round_.id
        ]
        round_.correct_total = sum(1 for item in items if item.outcome == EvaluationOutcome.CORRECT)
        round_.incorrect_total = sum(1 for item in items if item.outcome == EvaluationOutcome.INCORRECT)
        round_.timeout_total = sum(1 for item in items if item.outcome == EvaluationOutcome.TIMEOUT)
        round_.error_total = sum(
            1
            for item in items
            if item.outcome in {EvaluationOutcome.ERROR, EvaluationOutcome.INVALID_RESPONSE}
        )


def _assert_no_ground_truth(payload: dict) -> None:
    lowered = {str(key).lower() for key in payload}
    forbidden = {"expected", "expectedanswer", "expected_answer", "answer"}
    leaked = forbidden.intersection(lowered)
    if leaked:
        raise ValueError(f"Payload de validação contém gabarito: {sorted(leaked)}")


def _log(event: str, **fields) -> None:
    extras = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("%s %s", event, extras)
