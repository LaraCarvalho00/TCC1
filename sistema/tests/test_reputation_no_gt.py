"""Garante que a reputação não usa gabarito e que instáveis são penalizados."""

from __future__ import annotations

import unittest

from sistema.core.pipeline import run_round
from sistema.core.metrics import MetricsLogger
from sistema.core.reputation import ReputationTracker
from sistema.core.schemas import NodeResponse


class ReputationNoGroundTruthTests(unittest.TestCase):
    def test_colluders_are_not_punished_by_the_answer_key(self) -> None:
        """Se o conluio vence o consenso, o gabarito não pode rebaixar os maliciosos."""
        tracker = ReputationTracker(["h0", "h1", "m0", "m1", "m2"], alpha=1.0, min_confidence=0.5)
        logger = MetricsLogger(self._tmp())
        responses = [
            NodeResponse("h0", "t", 10, 100, "honest"),
            NodeResponse("h1", "t", 10, 100, "honest"),
            NodeResponse("m0", "t", 999, 100, "malicious"),
            NodeResponse("m1", "t", 999, 100, "malicious"),
            NodeResponse("m2", "t", 999, 100, "malicious"),
        ]
        run_round(
            round_index=0,
            task_id="t",
            expected=10,
            responses=responses,
            tracker=tracker,
            logger=logger,
        )
        self.assertGreater(tracker.get("m0"), tracker.get("h0"))
        self.assertEqual(logger.per_node_rows[0]["correct"], 1)  # honesto acertou o GT
        self.assertEqual(logger.per_node_rows[2]["correct"], 0)  # malicioso errou o GT
        self.assertEqual(logger.per_node_rows[2]["reputation_score"], 1.0)

    def test_timeout_penalizes_unstable_without_using_expected(self) -> None:
        tracker = ReputationTracker(["h0", "h1", "u0"], alpha=1.0, min_confidence=0.5)
        logger = MetricsLogger(self._tmp())
        responses = [
            NodeResponse("h0", "t", 7, 100, "honest"),
            NodeResponse("h1", "t", 7, 100, "honest"),
            NodeResponse("u0", "t", None, 4000, "unstable"),
        ]
        run_round(
            round_index=0,
            task_id="t",
            expected=7,
            responses=responses,
            tracker=tracker,
            logger=logger,
        )
        self.assertEqual(tracker.get("u0"), 0.0)
        self.assertEqual(tracker.get("h0"), 1.0)

    def test_tie_does_not_update_reputation(self) -> None:
        tracker = ReputationTracker(["a", "b"], alpha=1.0, min_confidence=0.55, initial=0.5)
        logger = MetricsLogger(self._tmp())
        responses = [
            NodeResponse("a", "t", 1, 100, "honest"),
            NodeResponse("b", "t", 2, 100, "malicious"),
        ]
        run_round(
            round_index=0,
            task_id="t",
            expected=1,
            responses=responses,
            tracker=tracker,
            logger=logger,
        )
        self.assertEqual(tracker.get("a"), 0.5)
        self.assertEqual(tracker.get("b"), 0.5)

    def _tmp(self) -> str:
        import tempfile

        return tempfile.mkdtemp(prefix="tcc-rep-")


if __name__ == "__main__":
    unittest.main()
