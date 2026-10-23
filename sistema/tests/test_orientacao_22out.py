"""Testes da orientação de 22/10. O padrão do protocolo não entra aqui."""
import csv
import os
import random
import unittest

from sistema.core.behavior import corrupt_with_noise
from sistema.core.defenses import DefenseConfig
from sistema.core.distance import medoid, relative_distance
from sistema.core.protocol import NetworkState, ProtocolConfig, apply_record, oracle_record
from sistema.core.reputation import ReputationTracker
from sistema.simulate import run_simulation
from sistema.tests.test_network import _args


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


class NoiseAnswerTest(unittest.TestCase):
    def test_every_draw_is_far_from_the_base(self):
        rng = random.Random(0)
        for _ in range(10_000):
            base = rng.choice([0, 1, 18, 20, 999, -7])
            corrupted = corrupt_with_noise(base, rng)
            self.assertGreaterEqual(abs(corrupted), 1000)
            self.assertGreater(relative_distance(corrupted, base), 0.99)

    def _answers(self, collusion):
        args = _args(
            nodes=10, malicious=0.5, rounds=2, seed=7,
            collusion_value=collusion, malicious_answer="noise", orchestration="fixed",
        )
        run_simulation(args)
        with open(os.path.join(args.output, "per_node.csv"), newline="") as handle:
            return [row for row in csv.DictReader(handle) if row["profile"] == "malicious"]

    def test_collusion_sends_one_value(self):
        by_round: dict[str, set[str]] = {}
        for row in self._answers(999):
            by_round.setdefault(row["round_index"], set()).add(row["answer"])
            self.assertGreaterEqual(abs(float(row["answer"])), 1000)
        self.assertTrue(by_round)
        self.assertTrue(all(len(values) == 1 for values in by_round.values()))

    def test_without_collusion_the_values_differ(self):
        rows = self._answers(None)
        first = [row["answer"] for row in rows if row["round_index"] == "0"]
        self.assertGreater(len(set(first)), 1)


class UnstableAttributeTest(unittest.TestCase):
    def test_twenty_percent_marks_ten_nodes(self):
        summary = run_simulation(_args(
            nodes=50, malicious=0.0, unstable=0.2, unstable_mode="attribute",
            rounds=1, orchestration="fixed", signal="truth", seed=3,
        ))
        self.assertEqual(summary["unstable_honest"] + summary["unstable_malicious"], 10)
        self.assertEqual(summary["unstable_malicious"], 0)

    def test_high_malicious_fraction_is_accepted(self):
        summary = run_simulation(_args(
            nodes=50, malicious=0.8, unstable=0.2, unstable_mode="attribute",
            rounds=1, orchestration="fixed", signal="truth", seed=3,
        ))
        self.assertEqual(summary["unstable_honest"] + summary["unstable_malicious"], 10)

    def test_honest_unstable_answers_honestly(self):
        args = _args(
            nodes=50, malicious=0.0, unstable=0.2, unstable_mode="attribute",
            rounds=1, orchestration="fixed", signal="truth", seed=3,
            honest_accuracy=1.0, unstable_p_drop=0.0,
        )
        run_simulation(args)
        with open(os.path.join(args.output, "rounds.csv"), newline="") as handle:
            expected = next(csv.DictReader(handle))["expected"]
        with open(os.path.join(args.output, "per_node.csv"), newline="") as handle:
            answers = {row["answer"] for row in csv.DictReader(handle)}
        self.assertEqual(answers, {expected})


class StrategicMaliciousTest(unittest.TestCase):
    def test_on_off_waits_until_round_g(self):
        args = _args(
            nodes=20, malicious=0.5, rounds=6, seed=1, orchestration="dynamic",
            collusion_value=999, leader_attack="forge", malicious_strategy="on_off",
            honest_rounds=5, defense="none",
        )
        run_simulation(args)
        with open(os.path.join(args.output, "per_node.csv"), newline="") as handle:
            rows = [row for row in csv.DictReader(handle) if row["profile"] == "malicious"]
        early = [row for row in rows if int(row["round_index"]) < 5]
        late = [row for row in rows if int(row["round_index"]) == 5]
        self.assertTrue(early and late)
        self.assertTrue(all(row["answer"] != "999" for row in early))
        self.assertTrue(all(row["answer"] == "999" for row in late))
        with open(os.path.join(args.output, "leadership.csv"), newline="") as handle:
            lead = list(csv.DictReader(handle))
        forged_early = [
            row for row in lead
            if int(row["round_index"]) < 5 and row["leader_profile"] == "malicious" and row["attack"] == "forge"
        ]
        forged_late = [
            row for row in lead
            if int(row["round_index"]) == 5 and row["leader_profile"] == "malicious" and row["attack"] == "forge"
        ]
        self.assertEqual(forged_early, [])
        self.assertTrue(forged_late)


class AuditAndSlowUpTest(unittest.TestCase):
    def test_random_audit_rate_and_test_rounds(self):
        from sistema.core.protocol import plan_audits
        from sistema.core.schedule import is_test_round

        totals = []
        for seed in range(1000):
            chosen = plan_audits(seed, 50, 10, 0.1)
            self.assertTrue(all(not is_test_round(index, 10) for index in chosen))
            totals.append(len(chosen))
        mean = sum(totals) / len(totals)
        self.assertGreater(mean, 4)
        self.assertLess(mean, 5)

    def test_slow_up_rises_slowly_and_falls_fast(self):
        risen = ReputationTracker(["n"], mechanism="ema_slow_up", initial=0.5)
        risen.update("n", 1.0, ground_truth=True)
        self.assertAlmostEqual(risen.get("n"), 0.55)
        fallen = ReputationTracker(["n"], mechanism="ema_slow_up", initial=0.5)
        fallen.update("n", 0.0, ground_truth=True)
        self.assertAlmostEqual(fallen.get("n"), 0.1)


class RequestedMeasuresTest(unittest.TestCase):
    def test_honest_fraction_and_audit_column(self):
        args = _args(
            nodes=10, malicious=0.0, rounds=1, orchestration="fixed", signal="truth",
            honest_accuracy=1.0, seed=1,
        )
        summary = run_simulation(args)
        self.assertAlmostEqual(summary["mean_pct_honest_exact"], 1.0)
        with open(os.path.join(args.output, "rounds.csv"), newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(float(row["pct_honest_exact"]), 1.0)
        self.assertEqual(float(row["pct_honest_responded"]), 1.0)
        self.assertEqual(row["audited"], "1")

    def test_dynamic_summary_counts_malicious_auditors(self):
        args = _args(
            nodes=10, malicious=0.5, rounds=6, seed=1, orchestration="dynamic",
            auditor_attack="false_reject", defense="none",
        )
        summary = run_simulation(args)
        with open(os.path.join(args.output, "leadership.csv"), newline="") as handle:
            ref = [row for row in csv.DictReader(handle) if row["is_reference"] == "1" and row["outcome"] != "calibration"]
        malicious = sum(1 for row in ref if row["auditor_profile"] == "malicious")
        vetoes = sum(1 for row in ref if row["auditor_profile"] == "malicious" and row["auditor_vote"] == "0")
        self.assertEqual(summary["dynamic"]["auditor_malicious_rounds"], malicious)
        self.assertEqual(summary["dynamic"]["auditor_malicious_vetoes"], vetoes)
        self.assertGreater(malicious, 0)
