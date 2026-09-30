"""Cenário experimental: 5 nós (3 honestos, 2 maliciosos) em validação."""

from __future__ import annotations

import random
import unittest

from sistema.core import behavior
from sistema.core.node_stats import NodeStats
from sistema.core.reputation import ReputationTracker
from sistema.core.reputation_history import ReputationHistoryStore
from sistema.core.validation.dataset import ValidationDataset
from sistema.core.validation.models import NodeSpec
from sistema.core.validation.selector import QuestionSelector
from sistema.core.validation.service import ValidationRoundService
from sistema.core.validation.store import ValidationStore
from sistema.core.validation.transport import SimulatedProfileClient


class ValidationScenarioFiveNodesTests(unittest.TestCase):
    def test_query_accuracy_and_reputation_series(self) -> None:
        profiles = {
            "N1": behavior.HONEST,
            "N2": behavior.HONEST,
            "N3": behavior.HONEST,
            "N4": behavior.MALICIOUS,
            "N5": behavior.MALICIOUS,
        }
        dataset = ValidationDataset.from_sample(limit=6)
        rng = random.Random(7)
        questions = QuestionSelector(dataset, rng).select(2)
        expected = {item.question_id: item.expected_answer for item in dataset.questions}
        client = SimulatedProfileClient(
            profiles,
            expected,
            rng,
            behavior.BehaviorConfig(honest_p_correct=1.0, malicious_collusion_value=999),
        )
        tracker = ReputationTracker(list(profiles), alpha=1.0)
        stats = NodeStats()
        history = ReputationHistoryStore()
        store = ValidationStore()
        service = ValidationRoundService(
            tracker=tracker,
            client=client,
            store=store,
            history=history,
            stats=stats,
        )
        nodes = [NodeSpec(node_id=node_id, profile=profile) for node_id, profile in profiles.items()]

        round_ids = []
        for index in range(1, 4):
            round_ = service.start(
                round_number=index,
                nodes=nodes,
                questions=questions,
                seed=7,
                dataset_version=dataset.version,
                round_id=f"vr{index}",
            )
            round_ids.append(round_.id)

        for node_id in profiles:
            acc = stats.for_node(node_id)
            series = history.series(node_id)
            self.assertGreaterEqual(acc.total_evaluated, 0)
            self.assertEqual(len(series), 3 * len(questions))
            print(
                f"{node_id}: acertos={acc.total_correct} erros={acc.total_incorrect} "
                f"reputação={tracker.get(node_id):.3f}"
            )
            for round_id in round_ids:
                value = history.reputation_at(node_id, round_id)
                self.assertIsNotNone(value)
                print(f"  {round_id} -> {value:.3f}")

        for honest in ("N1", "N2", "N3"):
            self.assertEqual(stats.for_node(honest).total_incorrect, 0)
            self.assertEqual(stats.for_node(honest).total_correct, 3 * len(questions))
        for malicious in ("N4", "N5"):
            self.assertEqual(stats.for_node(malicious).total_correct, 0)
            self.assertEqual(stats.for_node(malicious).total_incorrect, 3 * len(questions))
            self.assertLess(tracker.get(malicious), tracker.get("N1"))


if __name__ == "__main__":
    unittest.main()
