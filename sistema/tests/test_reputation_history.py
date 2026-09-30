"""Histórico append-only e consulta por rodada."""

from __future__ import annotations

import os
import tempfile
import unittest

from sistema.core.enums import EvaluationOutcome, RoundKind, UpdateReason
from sistema.core.node_stats import NodeStats
from sistema.core.pipeline import run_round
from sistema.core.metrics import MetricsLogger
from sistema.core.reputation import ReputationTracker
from sistema.core.reputation_history import ReputationEvent, ReputationHistoryStore
from sistema.core.schemas import NodeResponse


class ReputationHistoryTests(unittest.TestCase):
    def test_append_only_and_query_by_round(self) -> None:
        store = ReputationHistoryStore()
        stats = NodeStats()
        store.append(
            ReputationEvent.capture(
                node_id="n1",
                round_id="1",
                reputation_before=0.5,
                reputation_after=0.6,
                stats=stats.for_node("n1"),
            )
        )
        store.append(
            ReputationEvent.capture(
                node_id="n1",
                round_id="2",
                reputation_before=0.6,
                reputation_after=0.7,
                stats=stats.for_node("n1"),
            )
        )
        self.assertEqual(len(store.for_node("n1")), 2)
        self.assertEqual(store.reputation_at("n1", "1"), 0.6)
        self.assertEqual(store.reputation_at("n1", "2"), 0.7)
        self.assertIsNone(store.reputation_at("n2", "1"))

    def test_csv_does_not_overwrite_previous_events(self) -> None:
        directory = tempfile.mkdtemp(prefix="tcc-hist-")
        path = os.path.join(directory, "reputation_history.csv")
        store = ReputationHistoryStore(path)
        store.append(
            ReputationEvent.capture(
                node_id="n1",
                round_id="1",
                reputation_before=0.5,
                reputation_after=0.55,
            )
        )
        again = ReputationHistoryStore(path)
        again.append(
            ReputationEvent.capture(
                node_id="n1",
                round_id="2",
                reputation_before=0.55,
                reputation_after=0.6,
            )
        )
        self.assertEqual(len(again.events), 2)

    def test_run_round_records_normal_task_without_changing_ema(self) -> None:
        tracker = ReputationTracker(["h0", "h1"], alpha=1.0, min_confidence=0.5)
        logger = MetricsLogger()
        history = ReputationHistoryStore()
        run_round(
            round_index=0,
            task_id="t",
            expected=10,
            responses=[
                NodeResponse("h0", "t", 10, 100, "honest"),
                NodeResponse("h1", "t", 10, 100, "honest"),
            ],
            tracker=tracker,
            logger=logger,
            history=history,
        )
        self.assertEqual(tracker.get("h0"), 1.0)
        self.assertEqual(history.for_node("h0")[0].update_reason, UpdateReason.NORMAL_TASK)
        self.assertEqual(history.for_node("h0")[0].round_kind, RoundKind.NORMAL_TASK)
        self.assertEqual(history.for_node("h0")[0].evaluation_outcome, EvaluationOutcome.HELD)

    def test_accuracy_zero_when_nothing_evaluated(self) -> None:
        stats = NodeStats()
        self.assertEqual(stats.for_node("n1").accuracy, 0.0)


if __name__ == "__main__":
    unittest.main()
