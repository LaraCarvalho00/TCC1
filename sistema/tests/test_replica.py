import random
import unittest

from sistema.core import behavior
from sistema.core.defenses import preset
from sistema.core.network import SimulatedNetwork
from sistema.core.protocol import ProtocolConfig, Vote, oracle_record, oracle_round
from sistema.core.replica import Replica
from sistema.core.topology import build_graph, distances


def _answers(rng, node_ids, profiles, expected):
    out = {}
    for n in node_ids:
        if profiles[n] == behavior.MALICIOUS:
            out[n] = 999
        else:
            out[n] = expected if rng.random() < 0.9 else expected + 1
    return out


def _replica_round(replicas, profiles, graph, attacks, cfg, round_index, answers, expected):
    """Mesmo fluxo do nó em container: a mensagem percorre o grafo e só os membros da cadeia tratam."""
    groups = {}
    for n in sorted(replicas):
        groups.setdefault(replicas[n].head, []).append(n)
    malicious = {n for n, p in profiles.items() if p == behavior.MALICIOUS}
    for head, members in groups.items():
        leader, auditor, _ = replicas[members[0]].elect()
        reached = [m for m in members if m in distances(graph, leader)]
        record = replicas[leader].propose(
            round_index=round_index, task_id=f"t{round_index}", leader=leader, auditor=auditor,
            responses={m: answers[m] for m in reached},
            attack=behavior.leader_attack(profiles[leader], attacks), colluders=malicious,
        )
        votes = {}
        for m in reached:
            vote = replicas[m].vote(record, answers[m])
            if m in malicious:
                ok, reason = behavior.malicious_vote(
                    leader_is_colluder=leader in malicious, is_auditor=m == auditor,
                    honest_ok=vote.ok, honest_reason=vote.reason, config=attacks,
                )
                vote = Vote(m, ok, reason)
            votes[m] = vote
        for m in reached:
            replicas[m].commit(record, votes)
    if oracle_round(round_index, cfg):
        groups = {}
        for n in sorted(replicas):
            groups.setdefault(replicas[n].head, []).append(n)
        for head, members in groups.items():
            rec = oracle_record(
                prev_hash=head, round_index=round_index, task_id=f"t{round_index}",
                expected=expected, graded={m: answers[m] for m in members},
            )
            votes = {m: m not in malicious for m in members}
            for m in members:
                replicas[m].oracle(rec, votes)


class ReplicaParityTest(unittest.TestCase):
    """As cópias por nó chegam às mesmas cadeias que a simulação em grupo."""

    def _check(self, malicious_count, leader_attack, defense, rounds=30, seed=5):
        node_ids = [f"node-{i}" for i in range(1, 11)]
        profiles = {n: (behavior.MALICIOUS if i <= malicious_count else behavior.HONEST) for i, n in enumerate(node_ids, 1)}
        cfg = ProtocolConfig(signal="hybrid", mechanism="beta", defense=preset(defense))
        attacks = behavior.AttackConfig(leader_attack=leader_attack)
        graph = build_graph(node_ids, "kregular", degree=4, seed=seed)
        network = SimulatedNetwork(node_ids, profiles, graph, cfg, attacks)
        replicas = {n: Replica(n, node_ids, cfg, graph) for n in node_ids}
        rng = random.Random(seed)
        for r in range(rounds):
            answers = _answers(rng, node_ids, profiles, expected=42)
            network.run_round(r, f"t{r}", 42, answers)
            _replica_round(replicas, profiles, graph, attacks, cfg, r, answers, 42)
            self.assertEqual({n: replicas[n].head for n in node_ids}, network.heads(), f"rodada {r}")
        for n in node_ids:
            self.assertTrue(replicas[n].ledger.verify_chain())
            self.assertEqual(replicas[n].state.consensus.weights(), network.group_of(n).state.consensus.weights())

    def test_parity_honest_majority_forge(self):
        self._check(3, "forge", "all")

    def test_parity_collusion_majority_without_defense(self):
        self._check(7, "forge", "none")

    def test_parity_collusion_majority_with_fork(self):
        self._check(7, "forge", "all")

    def test_parity_censor(self):
        self._check(6, "censor", "refuse_forged")


if __name__ == "__main__":
    unittest.main()
