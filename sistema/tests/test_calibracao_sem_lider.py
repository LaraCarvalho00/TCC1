"""Calibração sem líder (opção ``leaderless_calibration``)."""
import csv
import os
import unittest

from sistema.core import behavior
from sistema.core.defenses import DefenseConfig, preset
from sistema.core.network import SimulatedNetwork
from sistema.core.protocol import ProtocolConfig, leaderless_calibration_round, replay
from sistema.core.topology import build_graph
from sistema.tests.test_network import _args
from sistema.simulate import run_simulation

IDS = [f"node-{i}" for i in range(10)]
PROFILES = {nid: (behavior.MALICIOUS if i < 8 else behavior.HONEST) for i, nid in enumerate(IDS)}


def _config(leaderless=True, signal="hybrid"):
    defense = DefenseConfig(**{**preset("all").to_dict(), "leaderless_calibration": leaderless})
    return ProtocolConfig(signal=signal, defense=defense)


def _network(config):
    graph = build_graph(IDS, "kregular", 4, 0)
    return SimulatedNetwork(IDS, PROFILES, graph, config, behavior.AttackConfig(leader_attack="forge"))


def _answers(expected=26):
    return {nid: (999 if PROFILES[nid] == behavior.MALICIOUS else expected) for nid in IDS}


class LeaderlessCalibrationTest(unittest.TestCase):
    def test_helper_only_in_calibration_rounds_with_ground_truth(self):
        cfg = _config()
        self.assertTrue(all(leaderless_calibration_round(r, cfg) for r in range(3)))
        self.assertFalse(leaderless_calibration_round(3, cfg))
        self.assertFalse(leaderless_calibration_round(0, _config(signal="consensus")))
        self.assertFalse(leaderless_calibration_round(0, _config(leaderless=False)))

    def test_calibration_rounds_have_no_leader_vote_or_fork(self):
        net = _network(_config())
        for r in range(3):
            outcomes = net.run_round(r, f"t{r}", 26, _answers())
            self.assertEqual(len(outcomes), 1)
            out = outcomes[0]
            self.assertIsNone(out.leader)
            self.assertIsNone(out.decision)
            self.assertEqual(out.votes, {})
            self.assertEqual(out.record.kind, "calibration")
        self.assertEqual(len(net.groups), 1)

    def test_reputation_follows_ground_truth_with_oracle_alpha(self):
        net = _network(_config())
        for r in range(3):
            net.run_round(r, f"t{r}", 26, _answers())
            state = net.groups[0].state
            self.assertAlmostEqual(state.consensus.get("node-0"), 0.5 * 0.2 ** (r + 1))
            self.assertAlmostEqual(state.power.get("node-0"), 0.5 * 0.2 ** (r + 1))
            self.assertAlmostEqual(state.consensus.get("node-9"), 1 - 0.5 * 0.2 ** (r + 1))

    def test_ledger_replay_reproduces_state(self):
        cfg = _config()
        net = _network(cfg)
        for r in range(6):
            net.run_round(r, f"t{r}", 26, _answers())
        group = net.groups[0]
        replayed = replay(group.ledger.records, IDS, cfg)
        self.assertEqual(replayed.snapshot(), group.state.snapshot())
        self.assertTrue(group.ledger.verify_chain())

    def test_option_off_keeps_old_behaviour(self):
        net = _network(_config(leaderless=False))
        out = net.run_round(0, "t0", 26, _answers())[0]
        self.assertIsNotNone(out.leader)
        self.assertNotEqual(out.record.kind, "calibration")

    def test_full_run_with_majority_colluding(self):
        args = _args(
            nodes=20, malicious=0.8, leader_attack="forge", defense="all", leaderless_calibration=True,
        )
        summary = run_simulation(args)
        dyn = summary["dynamic"]
        self.assertEqual(dyn["leaderless_calibration_rounds"], 3)
        self.assertEqual(dyn["leader_malicious_rounds"], 0)
        self.assertEqual(dyn["forged_accepted"], 0)
        self.assertEqual(dyn["n_chains_final"], 1)
        with open(os.path.join(args.output, "leadership.csv"), encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual([r["outcome"] for r in rows[:3]], ["calibration"] * 3)
        self.assertEqual({r["leader"] for r in rows[:3]}, {""})


if __name__ == "__main__":
    unittest.main()
