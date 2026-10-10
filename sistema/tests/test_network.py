import argparse
import json
import os
import tempfile
import unittest

from sistema.core import behavior
from sistema.core.network import SimulatedNetwork
from sistema.core.protocol import ProtocolConfig
from sistema.core.topology import build_graph
from sistema.simulate import run_simulation

_GOLDEN = os.path.join(os.path.dirname(__file__), "data", "golden_fixed.json")


def _args(**overrides):
    base = dict(
        nodes=20, malicious=0.65, unstable=0.0, rounds=50, alpha=0.3, seed=3, honest_accuracy=0.9,
        collusion_value=999, unstable_p_drop=0.3, unstable_p_correct=0.5, mechanism="ema", alpha_down=None,
        initial_reputation=0.5, experiment_id=None, overwrite=True, test_every=10, row_sync=False, quiet=True,
        orchestration="dynamic", signal="hybrid", topology="kregular", degree=4, leader_attack="none",
        auditor_attack="none", defense="none",
    )
    base.update(overrides)
    base["output"] = tempfile.mkdtemp()
    return argparse.Namespace(**base)


def _run(**overrides):
    return run_simulation(_args(**overrides))


class FixedRegressionTest(unittest.TestCase):
    """O orquestrador fixo reproduz os números de antes do orquestrador eleito."""

    def test_fixed_mode_matches_golden(self):
        with open(_GOLDEN, encoding="utf-8") as fh:
            golden = json.load(fh)
        for case in golden:
            scenario = case["scenario"]
            summary = _run(orchestration="fixed", signal="truth", seed=7, topology="star", **scenario)
            for key, value in case["summary"].items():
                self.assertEqual(summary[key], value, f"{scenario} {key}")
            self.assertNotIn("dynamic", summary)


class DynamicNetworkTest(unittest.TestCase):
    def test_rotation_never_repeats_leader(self):
        summary = _run(malicious=0.25, collusion_value=None, defense="all")
        self.assertEqual(summary["dynamic"]["max_consecutive_same_leader"], 1)
        self.assertEqual(summary["dynamic"]["leader_malicious_rounds_after_calibration"], 0)

    def test_forgery_never_accepted_with_honest_majority(self):
        summary = _run(malicious=0.25, leader_attack="forge", defense="calibration")
        self.assertEqual(summary["dynamic"]["forged_accepted"], 0)
        self.assertEqual(summary["dynamic"]["replicas_divergent_final"], 0)

    def test_censorship_does_not_reach_quorum_with_honest_majority(self):
        summary = _run(malicious=0.25, leader_attack="censor", defense="calibration")
        self.assertEqual(summary["dynamic"]["censored_accepted"], 0)

    def test_false_reject_auditor_does_not_void_honest_round(self):
        ids = [f"node-{i}" for i in range(5)]
        profiles = {n: "honest" for n in ids} | {"node-3": "malicious"}
        net = SimulatedNetwork(
            ids, profiles, build_graph(ids, "star"), ProtocolConfig(),
            behavior.AttackConfig(auditor_attack="false_reject"),
        )
        state = net.groups[0].state
        for node, rep in zip(ids, (0.6, 0.5, 0.9, 0.8, 0.4)):
            state.consensus.reputation[node] = rep
        answers = {n: 26 for n in ids}
        (outcome,) = net.run_round(1, "t", 26, answers)
        self.assertEqual((outcome.leader, outcome.auditor), ("node-2", "node-3"))
        self.assertFalse(outcome.votes["node-3"].ok)
        self.assertTrue(outcome.decision.accepted)
        self.assertEqual(outcome.decision.penalties, [("node-3", "false_reject")])
        self.assertLess(state.power.get("node-3"), 0.8)

    def test_oracle_without_bypass_is_blocked_by_majority_collusion(self):
        blocked = _run(defense="calibration")["dynamic"]
        applied = _run(defense="oracle_bypass")["dynamic"]
        self.assertGreater(blocked["oracle_blocked_rounds"], 0)
        self.assertEqual(applied["oracle_blocked_rounds"], 0)

    def test_collusion_without_leadership_when_scores_split(self):
        summary = _run(defense="all", leader_attack="forge")
        self.assertEqual(summary["dynamic"]["leader_malicious_rounds_after_calibration"], 0)
        self.assertEqual(summary["consensus_accuracy_weighted_on_tests"], 1.0)

    def test_refuse_forged_splits_the_chain(self):
        refused = _run(defense="refuse_forged", leader_attack="forge")["dynamic"]
        followed = _run(defense="none", leader_attack="forge")["dynamic"]
        self.assertGreater(refused["chain_split_rounds"], 0)
        self.assertEqual(refused["honest_replicas_divergent_final"], 0)
        self.assertEqual(followed["chain_split_rounds"], 0)

    def test_pure_consensus_signal_loses_to_majority_collusion(self):
        summary = _run(signal="consensus", defense="all")
        self.assertEqual(summary["consensus_accuracy_weighted_on_tests"], 0.0)

    def test_replicas_agree_without_attacks(self):
        summary = _run(malicious=0.0, collusion_value=None, defense="all")
        self.assertEqual(summary["dynamic"]["replicas_divergent_final"], 0)
        self.assertEqual(summary["dynamic"]["graph_max_degree"], 4)


if __name__ == "__main__":
    unittest.main()
