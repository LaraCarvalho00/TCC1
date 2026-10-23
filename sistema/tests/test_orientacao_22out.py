"""Testes da orientação de 22/10. O padrão do protocolo não entra aqui."""
import unittest

from sistema.core.defenses import DefenseConfig
from sistema.core.distance import medoid, relative_distance
from sistema.core.protocol import NetworkState, ProtocolConfig, apply_record, oracle_record
from sistema.core.reputation import ReputationTracker


class DistanceTest(unittest.TestCase):
    def test_relative_distance_exact_values(self):
        self.assertEqual(relative_distance(18, 18), 0)
        self.assertEqual(relative_distance(20, 18), 2 / 38)
        self.assertEqual(relative_distance(999, 18), 981 / 1017)
        self.assertEqual(relative_distance(0, 0), 0)
        self.assertEqual(relative_distance(None, 5), 1)

    def test_medoid_exact_values(self):
        self.assertEqual(medoid([18, 18, 20, 999]).answer, 18)
        self.assertEqual(medoid([1, 2]).answer, 1)
        self.assertEqual(medoid([18, 999, 999], weights=[1, 0.01, 0.01]).answer, 18)


class DistanceConsensusTest(unittest.TestCase):
    def test_oracle_round_uses_continuous_signal(self):
        config = ProtocolConfig(
            consensus_mode="distance",
            defense=DefenseConfig(split_alpha=True, oracle_alpha=0.8),
        )
        state = NetworkState(["n0", "n1", "n2"], config)
        record = oracle_record(
            prev_hash="0" * 64, round_index=0, task_id="t", expected=18,
            graded={"n0": 18, "n1": 20, "n2": 999},
        )
        apply_record(state, record)
        self.assertAlmostEqual(state.consensus.get("n0"), 0.1 + 0.8 * 1)
        self.assertAlmostEqual(state.consensus.get("n1"), 0.1 + 0.8 * (1 - 2 / 38))
        self.assertAlmostEqual(state.consensus.get("n2"), 0.1 + 0.8 * (1 - 981 / 1017))

    def test_exact_mode_keeps_binary_signal(self):
        tracker = ReputationTracker(["ok", "bad"], alpha=0.8, initial=0.5)
        tracker.update("ok", True, alpha=0.8)
        tracker.update("bad", False, alpha=0.8)
        self.assertAlmostEqual(tracker.get("ok"), 0.9)
        self.assertAlmostEqual(tracker.get("bad"), 0.1)
