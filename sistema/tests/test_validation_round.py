"""Casos obrigatórios da Validation Round."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from sistema.core.enums import EvaluationOutcome, UpdateReason
from sistema.core.metrics import MetricsLogger
from sistema.core.node_stats import NodeStats
from sistema.core.reputation import ReputationTracker
from sistema.core.reputation_history import ReputationHistoryStore
from sistema.core.validation.dataset import ValidationQuestion
from sistema.core.validation.models import NodeSpec
from sistema.core.validation.service import ValidationRoundService
from sistema.core.validation.store import ValidationStore
from sistema.core.validation.transport import FORBIDDEN_PAYLOAD_KEYS, ScriptedNodeClient


def _question(qid: str = "q1", expected: int = 10) -> ValidationQuestion:
    return ValidationQuestion(
        question_id=qid,
        prompt="Quanto é 2+8?",
        expected_answer=expected,
        dataset_version="fixture",
    )


def _service(responders, node_ids=None, alpha=1.0, **kwargs):
    node_ids = node_ids or ["n1"]
    client = ScriptedNodeClient(responders)
    tracker = ReputationTracker(node_ids, alpha=alpha, min_confidence=0.5)
    stats = NodeStats()
    history = ReputationHistoryStore()
    store = ValidationStore()
    metrics = MetricsLogger()
    service = ValidationRoundService(
        tracker=tracker,
        client=client,
        store=store,
        history=history,
        stats=stats,
        metrics=metrics,
    )
    nodes = [NodeSpec(node_id=node_id) for node_id in node_ids]
    return service, client, tracker, stats, history, store, nodes


class ValidationRoundTests(unittest.TestCase):
    def test_case1_correct_increments_only_correct(self) -> None:
        service, client, tracker, stats, history, store, nodes = _service({"n1": 10})
        service.start(
            round_number=1,
            nodes=nodes,
            questions=[_question()],
            seed=1,
            dataset_version="fixture",
            round_id="r1",
        )
        acc = stats.for_node("n1")
        self.assertEqual(acc.total_correct, 1)
        self.assertEqual(acc.total_incorrect, 0)
        self.assertEqual(acc.total_evaluated, 1)
        result = store.find_result("r1", "n1", "q1")
        self.assertIsNotNone(result)
        self.assertTrue(result.is_correct)
        self.assertEqual(result.outcome, EvaluationOutcome.CORRECT)
        self.assertEqual(len(history.for_node("n1")), 1)
        self.assertGreater(tracker.get("n1"), 0.5)
        self.assertEqual(history.for_node("n1")[0].update_reason, UpdateReason.VALIDATION_ROUND)

    def test_case2_incorrect_increments_only_incorrect(self) -> None:
        service, _, tracker, stats, history, store, nodes = _service({"n1": 99})
        initial = tracker.get("n1")
        service.start(
            round_number=1,
            nodes=nodes,
            questions=[_question()],
            seed=1,
            dataset_version="fixture",
            round_id="r1",
        )
        acc = stats.for_node("n1")
        self.assertEqual(acc.total_correct, 0)
        self.assertEqual(acc.total_incorrect, 1)
        self.assertEqual(store.find_result("r1", "n1", "q1").outcome, EvaluationOutcome.INCORRECT)
        self.assertEqual(len(history.for_node("n1")), 1)
        self.assertLess(tracker.get("n1"), initial)

    def test_case3_independent_histories(self) -> None:
        responders = {
            "n1": 10,
            "n2": 10,
            "n3": 0,
        }
        service, _, tracker, stats, history, store, nodes = _service(
            responders, node_ids=["n1", "n2", "n3"]
        )
        service.start(
            round_number=1,
            nodes=nodes,
            questions=[_question()],
            seed=1,
            dataset_version="fixture",
            round_id="r1",
        )
        self.assertEqual(stats.for_node("n1").total_correct, 1)
        self.assertEqual(stats.for_node("n2").total_correct, 1)
        self.assertEqual(stats.for_node("n3").total_incorrect, 1)
        self.assertEqual(len(history.for_node("n1")), 1)
        self.assertEqual(len(history.for_node("n2")), 1)
        self.assertEqual(len(history.for_node("n3")), 1)
        self.assertGreater(tracker.get("n1"), tracker.get("n3"))

    def test_case4_consecutive_rounds_keep_all_events(self) -> None:
        service, _, _, stats, history, _, nodes = _service({"n1": 10})
        for index in range(1, 4):
            service.start(
                round_number=index,
                nodes=nodes,
                questions=[_question(qid=f"q{index}")],
                seed=1,
                dataset_version="fixture",
                round_id=f"r{index}",
            )
        events = history.for_node("n1")
        self.assertEqual(len(events), 3)
        self.assertEqual(stats.for_node("n1").total_correct, 3)
        self.assertEqual([event.round_id for event in events], ["r1", "r2", "r3"])

    def test_case5_retry_does_not_double_count(self) -> None:
        service, _, tracker, stats, history, store, nodes = _service({"n1": 10})
        kwargs = dict(
            round_number=1,
            nodes=nodes,
            questions=[_question()],
            seed=1,
            dataset_version="fixture",
            round_id="r1",
        )
        service.start(**kwargs)
        reputation = tracker.get("n1")
        service.start(**kwargs)
        self.assertEqual(stats.for_node("n1").total_correct, 1)
        self.assertEqual(stats.for_node("n1").total_evaluated, 1)
        self.assertEqual(len(store.results), 1)
        self.assertEqual(len(history.for_node("n1")), 1)
        self.assertEqual(tracker.get("n1"), reputation)

    def test_case6_timeout_is_not_incorrect(self) -> None:
        service, _, tracker, stats, history, store, nodes = _service(
            {"n1": (None, EvaluationOutcome.TIMEOUT)}
        )
        initial = tracker.get("n1")
        service.start(
            round_number=1,
            nodes=nodes,
            questions=[_question()],
            seed=1,
            dataset_version="fixture",
            round_id="r1",
        )
        acc = stats.for_node("n1")
        self.assertEqual(acc.total_incorrect, 0)
        self.assertEqual(acc.total_correct, 0)
        self.assertEqual(acc.total_evaluated, 0)
        self.assertEqual(store.find_result("r1", "n1", "q1").outcome, EvaluationOutcome.TIMEOUT)
        self.assertIsNone(store.find_result("r1", "n1", "q1").is_correct)
        self.assertEqual(tracker.get("n1"), initial)
        self.assertEqual(history.for_node("n1")[0].evaluation_outcome, EvaluationOutcome.TIMEOUT)

    def test_case7_validation_does_not_call_consensus(self) -> None:
        service, _, _, _, _, _, nodes = _service({"n1": 10})
        with patch("sistema.core.consensus.weighted_consensus") as weighted:
            with patch("sistema.core.consensus.majority_consensus") as majority:
                service.start(
                    round_number=1,
                    nodes=nodes,
                    questions=[_question()],
                    seed=1,
                    dataset_version="fixture",
                    round_id="r1",
                )
        weighted.assert_not_called()
        majority.assert_not_called()

    def test_stats_rebuild_from_persisted_results(self) -> None:
        service, _, _, stats, _, store, nodes = _service({"n1": 10})
        service.start(
            round_number=1,
            nodes=nodes,
            questions=[_question()],
            seed=1,
            dataset_version="fixture",
            round_id="r1",
        )
        rebuilt = NodeStats()
        rebuilt.rebuild_from_results(store.results)
        self.assertEqual(rebuilt.for_node("n1").total_correct, stats.for_node("n1").total_correct)
        self.assertEqual(rebuilt.for_node("n1").accuracy, 1.0)

    def test_case8_payload_has_no_ground_truth(self) -> None:
        service, client, _, _, _, _, nodes = _service({"n1": 10})
        service.start(
            round_number=1,
            nodes=nodes,
            questions=[_question()],
            seed=1,
            dataset_version="fixture",
            round_id="r1",
        )
        self.assertTrue(client.payloads)
        for payload in client.payloads:
            self.assertEqual(set(payload), {"task_id", "question"})
            for key in FORBIDDEN_PAYLOAD_KEYS:
                self.assertNotIn(key, payload)
            self.assertNotIn("expectedAnswer", payload)


if __name__ == "__main__":
    unittest.main()
