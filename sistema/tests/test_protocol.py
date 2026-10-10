import unittest

from sistema.core.defenses import DefenseConfig, preset, preset_names
from sistema.core.election import elect_leader, is_available, pick_auditor
from sistema.core.ledger import Ledger
from sistema.core.protocol import (
    NetworkState,
    ProtocolConfig,
    Vote,
    apply_record,
    decide,
    objective_check,
    oracle_record,
    outcome_records,
    propose_record,
    replay,
    tally_quorum,
    verify_record,
)
from sistema.core.topology import build_graph

IDS = [f"node-{i}" for i in range(5)]
COLLUDERS = {"node-0", "node-1"}
ANSWERS = {"node-0": 999, "node-1": 999, "node-2": 26, "node-3": 26, "node-4": 26}


def _state(signal="hybrid", **defense):
    return NetworkState(IDS, ProtocolConfig(signal=signal, defense=DefenseConfig(**defense)))


def _propose(state, attack=None, leader="node-0", ledger=None):
    return propose_record(
        state, round_index=0, task_id="t0", leader=leader, auditor="node-3",
        responses=dict(ANSWERS), prev_hash=(ledger.head if ledger else Ledger().head),
        attack=attack, colluders=COLLUDERS,
    )


class VerificationTest(unittest.TestCase):
    def test_honest_proposal_is_confirmed_by_everyone(self):
        state = _state()
        record = _propose(state, leader="node-2")
        self.assertEqual(record.consensus, 26)
        for node in IDS:
            vote = verify_record(state, record, node_id=node, own_answer=ANSWERS[node], prev_hash=Ledger().head)
            self.assertTrue(vote.ok, vote)

    def test_censorship_is_detected_by_the_censored_node(self):
        state = _state()
        record = _propose(state, attack="censor")
        self.assertEqual(objective_check(state, record), "")  # coerente com o que listou
        self.assertEqual(record.consensus, 999)
        vote = verify_record(state, record, node_id="node-2", own_answer=26, prev_hash=Ledger().head)
        self.assertEqual((vote.ok, vote.reason), (False, "censored"))

    def test_forged_state_is_detected_by_anyone(self):
        state = _state()
        record = _propose(state, attack="forge")
        self.assertEqual(objective_check(state, record), "forged")

    def test_false_consensus_is_detected_by_anyone(self):
        state = _state()
        record = _propose(state, attack="false_consensus")
        self.assertEqual(record.consensus, 999)
        self.assertEqual(objective_check(state, record), "false_consensus")

    def test_wrong_chain_is_refused(self):
        state = _state()
        record = _propose(state)
        vote = verify_record(state, record, node_id="node-2", own_answer=26, prev_hash="f" * 64)
        self.assertEqual(vote.reason, "chain")

    def test_forge_on_beta_mechanism(self):
        state = NetworkState(IDS, ProtocolConfig(mechanism="beta"))
        record = _propose(state, attack="forge")
        self.assertEqual(objective_check(state, record), "forged")
        self.assertGreater(record.state_after["consensus"]["reputation"]["node-0"], 0.9)


class QuorumTest(unittest.TestCase):
    def test_mass_must_exceed_half(self):
        weights = {"a": 0.5, "b": 0.5}
        self.assertFalse(tally_quorum({"a": True, "b": False}, weights)[2])  # empate não passa
        self.assertTrue(tally_quorum({"a": True, "b": False}, {"a": 0.9, "b": 0.1})[2])
        self.assertFalse(tally_quorum({"a": True}, {"a": 0.0})[2])

    def test_many_low_reputation_nodes_do_not_reach_quorum(self):
        weights = {f"s{i}": 0.01 for i in range(50)} | {"h1": 0.9, "h2": 0.9}
        votes = {f"s{i}": True for i in range(50)} | {"h1": False, "h2": False}
        self.assertFalse(tally_quorum(votes, weights)[2])

    def test_forged_void_punishes_leader_and_confirmers(self):
        state = _state()
        record = _propose(state, attack="forge")
        votes = {n: Vote(n, n in COLLUDERS, "" if n in COLLUDERS else "forged") for n in IDS}
        decision = decide(state, record, votes, objective_check(state, record))
        self.assertFalse(decision.accepted)
        self.assertEqual(dict(decision.penalties), {"node-0": "forged", "node-1": "confirmed_invalid"})

    def test_false_reject_auditor_is_punished(self):
        state = _state()
        record = _propose(state, leader="node-2")
        votes = {n: Vote(n, n != "node-3", "forged" if n == "node-3" else "") for n in IDS}
        decision = decide(state, record, votes, "")
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.penalties, [("node-3", "false_reject")])
        records = outcome_records(record, decision)
        self.assertEqual([r.kind for r in records], ["round", "penalty"])

    def test_refusing_node_records_void_against_attackers(self):
        state = _state()
        record = _propose(state, attack="forge")
        votes = {n: Vote(n, n in COLLUDERS or n == "node-4", "") for n in IDS}
        decision = decide(state, record, votes, "forged")
        self.assertTrue(decision.accepted)
        (void,) = outcome_records(record, decision, refuse=True)
        self.assertEqual(void.kind, "void")
        self.assertIn(("node-0", "forged"), void.penalties)


class StateTest(unittest.TestCase):
    def test_replay_rebuilds_the_same_state(self):
        state = _state(split_scores=True)
        ledger = Ledger()
        for round_index in range(4):
            record = propose_record(
                state, round_index=round_index, task_id="t", leader="node-2", auditor="node-3",
                responses=dict(ANSWERS), prev_hash=ledger.head,
            )
            ledger.append(record)
            apply_record(state, record)
            oracle = oracle_record(
                prev_hash=ledger.head, round_index=round_index, task_id="t", expected=26, graded=dict(ANSWERS),
            )
            ledger.append(oracle)
            apply_record(state, oracle)
        rebuilt = replay(ledger.records, IDS, state.config)
        self.assertEqual(rebuilt.state_hash(), state.state_hash())

    def test_split_scores_power_only_moves_with_oracle(self):
        state = _state(split_scores=True)
        record = _propose(state, leader="node-2")
        apply_record(state, record)
        self.assertEqual(state.power.get("node-0"), 0.5)
        self.assertLess(state.consensus.get("node-0"), 0.5)
        apply_record(state, oracle_record(prev_hash=record.hash, round_index=0, task_id="t0", expected=26, graded=ANSWERS))
        self.assertLess(state.power.get("node-0"), 0.5)
        self.assertGreater(state.power.get("node-2"), 0.5)

    def test_split_alpha_rates(self):
        state = _state(split_alpha=True, consensus_alpha=0.05, oracle_alpha=0.8)
        record = _propose(state, leader="node-2")
        apply_record(state, record)
        self.assertAlmostEqual(state.consensus.get("node-0"), 0.5 * 0.95)
        apply_record(state, oracle_record(prev_hash=record.hash, round_index=0, task_id="t0", expected=26, graded=ANSWERS))
        self.assertAlmostEqual(state.consensus.get("node-0"), 0.5 * 0.95 * 0.2)


class ElectionTest(unittest.TestCase):
    def test_bootstrap_rotates_and_never_repeats(self):
        state = _state()
        leaders = []
        for _ in range(len(IDS) + 2):
            leader, bootstrap = elect_leader(state, IDS)
            self.assertTrue(bootstrap)
            leaders.append(leader)
            state.last_leader = leader
            state.rotation += 1
        self.assertEqual(leaders[: len(IDS)], IDS)
        self.assertTrue(all(a != b for a, b in zip(leaders, leaders[1:])))

    def test_highest_score_leads_but_not_twice_in_a_row(self):
        state = _state()
        for node, rep in zip(IDS, (0.1, 0.2, 0.9, 0.8, 0.7)):
            state.consensus.reputation[node] = rep
        leader, bootstrap = elect_leader(state, IDS)
        self.assertEqual((leader, bootstrap), ("node-2", False))
        state.last_leader = "node-2"
        self.assertEqual(elect_leader(state, IDS)[0], "node-3")

    def test_unavailable_node_is_not_eligible(self):
        state = _state()
        for node, rep in zip(IDS, (0.1, 0.2, 0.9, 0.8, 0.7)):
            state.consensus.reputation[node] = rep
        state.presence["node-2"] = [False, False, True]
        self.assertFalse(is_available(state, "node-2", window=5, max_absences=1))
        self.assertEqual(elect_leader(state, IDS)[0], "node-3")

    def test_auditor_is_far_from_leader(self):
        ids = [f"node-{i}" for i in range(20)]
        state = NetworkState(ids, ProtocolConfig())
        graph = build_graph(ids, "kregular", degree=4, seed=1)
        auditor = pick_auditor(state, ids, "node-0", graph)
        self.assertNotIn(auditor, graph["node-0"])
        self.assertNotEqual(auditor, "node-0")
        star = build_graph(IDS, "star")
        self.assertEqual(pick_auditor(_with_reps(IDS, (0.9, 0.2, 0.3, 0.8, 0.7)), IDS, "node-0", star), "node-3")


def _with_reps(ids, reps):
    state = NetworkState(ids, ProtocolConfig())
    for node, rep in zip(ids, reps):
        state.consensus.reputation[node] = rep
    return state


class DefenseTest(unittest.TestCase):
    def test_presets(self):
        self.assertEqual(preset("none").active(), [])
        self.assertEqual(len(preset("all").active()), 5)
        self.assertNotIn("split_scores", preset("all_minus_split_scores").active())
        self.assertEqual(preset("calibration").calibration_rounds, 3)
        self.assertEqual(len(preset_names()), 12)


if __name__ == "__main__":
    unittest.main()
