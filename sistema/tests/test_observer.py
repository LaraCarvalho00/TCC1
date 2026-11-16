"""Regressão da observação explícita das rodadas."""
import tempfile
import unittest
from unittest.mock import patch

from sistema import simulate


class RoundObserverTests(unittest.TestCase):
    def test_observer_preserves_simulation_and_has_round_snapshots(self):
        for fraction in (0.5, 0.8):
            with self.subTest(fracao=fraction), tempfile.TemporaryDirectory() as tmp:
                args = simulate.parse_args([
                    "--nodes", "50", "--malicious", str(fraction), "--rounds", "50",
                    "--test-every", "10", "--seed", "0", "--collusion-value", "999",
                    "--defense", "all", "--topology", "kregular", "--degree", "4",
                    "--leader-attack", "forge", "--signal", "consensus",
                    "--output", tmp, "--experiment-id", "observacao",
                    "--overwrite", "--quiet", "--no-row-sync",
                ])
                baseline = simulate.run_simulation(args)
                events = []
                observed = simulate.run_simulation(args, round_observer=lambda **e: events.append(e))
                for key in ("consensus_accuracy_weighted", "consensus_accuracy_weighted_on_tests", "final_reputation_by_profile"):
                    self.assertEqual(baseline[key], observed[key])
                self.assertEqual(len(events), 50)
                self.assertEqual([e["round_index"] for e in events], list(range(50)))
                self.assertEqual(sum(e["is_test"] for e in events), 5)
                self.assertEqual(len(events[0]["before"]), 50)
                self.assertEqual(len(events[0]["after"]), 50)
                if fraction == 0.8:
                    self.assertLess(len(events[-1]["ref_after"]), 50)

    def test_executor_does_not_replace_simulation_functions(self):
        original_dynamic = simulate._dynamic_round
        with tempfile.TemporaryDirectory() as tmp:
            args = simulate.parse_args([
                "--nodes", "4", "--rounds", "10", "--seed", "0",
                "--topology", "kregular", "--degree", "2", "--output", tmp,
                "--experiment-id", "observacao", "--overwrite", "--quiet", "--no-row-sync",
            ])
            events = []
            with patch.object(simulate, "_dynamic_round", wraps=original_dynamic) as dynamic:
                simulate.run_simulation(args, round_observer=lambda **event: events.append(event))
                self.assertEqual(dynamic.call_count, 10)
                self.assertEqual(len(events), 10)
        self.assertIs(simulate._dynamic_round, original_dynamic)


if __name__ == "__main__":
    unittest.main()
