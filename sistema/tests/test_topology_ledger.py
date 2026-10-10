import dataclasses
import unittest

from sistema.core.ledger import GENESIS_HASH, Ledger, RoundRecord, canonical_hash
from sistema.core.topology import build_graph, diameter, distances, max_degree, spanning_tree


def _ids(n):
    return [f"node-{i}" for i in range(n)]


class TopologyTest(unittest.TestCase):
    def test_kregular_is_regular_and_connected(self):
        for n in (7, 10, 20, 120):
            graph = build_graph(_ids(n), "kregular", degree=4, seed=3)
            degrees = {len(v) for v in graph.values()}
            self.assertEqual(degrees, {4}, n)
            self.assertGreater(diameter(graph), 0, n)
            for node, neighbors in graph.items():
                for other in neighbors:
                    self.assertIn(node, graph[other])

    def test_odd_degree_with_odd_nodes_rounds_up(self):
        graph = build_graph(_ids(7), "kregular", degree=3, seed=1)
        self.assertEqual({len(v) for v in graph.values()}, {4})

    def test_same_seed_same_graph(self):
        a = build_graph(_ids(20), "kregular", degree=4, seed=9)
        b = build_graph(_ids(20), "kregular", degree=4, seed=9)
        c = build_graph(_ids(20), "kregular", degree=4, seed=10)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_star_is_complete(self):
        graph = build_graph(_ids(5), "star")
        self.assertEqual(max_degree(graph), 4)
        self.assertEqual(diameter(graph), 1)

    def test_distances_and_tree_respect_allowed(self):
        graph = {"a": ["b"], "b": ["a", "c"], "c": ["b"]}
        self.assertEqual(distances(graph, "a"), {"a": 0, "b": 1, "c": 2})
        self.assertEqual(distances(graph, "a", allowed={"a", "c"}), {"a": 0})
        self.assertEqual(spanning_tree(graph, "a"), {"a": None, "b": "a", "c": "b"})

    def test_degree_bounded_as_network_grows(self):
        for n in (20, 120):
            graph = build_graph(_ids(n), "kregular", degree=4, seed=0)
            self.assertEqual(max_degree(graph), 4)


class LedgerTest(unittest.TestCase):
    def _record(self, prev=GENESIS_HASH, consensus=26):
        return RoundRecord(
            kind="round", round_index=0, prev_hash=prev, leader="node-1",
            responses=(("node-0", 26), ("node-1", 26)), consensus=consensus,
            state_after={"consensus": {"reputation": {"node-0": 0.65, "node-1": 0.65}}},
        ).sealed()

    def test_hash_is_deterministic(self):
        self.assertEqual(self._record().hash, self._record().hash)
        self.assertEqual(canonical_hash({"a": 1.0, "b": [2, 3]}), canonical_hash({"b": (2, 3), "a": 1}))

    def test_append_requires_link_and_valid_hash(self):
        ledger = Ledger()
        first = ledger.append(self._record())
        with self.assertRaises(ValueError):
            ledger.append(self._record())  # prev_hash aponta para a origem
        second = self._record(prev=first.hash, consensus=8)
        tampered = dataclasses.replace(second, consensus=999)  # conteúdo muda, hash antigo
        with self.assertRaises(ValueError):
            ledger.append(tampered)
        ledger.append(second)
        self.assertTrue(ledger.verify_chain())

    def test_rewriting_history_breaks_chain(self):
        ledger = Ledger()
        first = ledger.append(self._record())
        ledger.append(self._record(prev=first.hash, consensus=8))
        ledger.records[0] = self._record(consensus=999)
        self.assertFalse(ledger.verify_chain())

    def test_json_roundtrip_keeps_hash(self):
        ledger = Ledger()
        first = ledger.append(self._record())
        ledger.append(self._record(prev=first.hash, consensus=8))
        restored = Ledger.from_json(ledger.to_json())
        self.assertEqual(restored.head, ledger.head)
        self.assertTrue(restored.verify_chain())


if __name__ == "__main__":
    unittest.main()
