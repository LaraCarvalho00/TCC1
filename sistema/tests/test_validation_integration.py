"""Contratos metodológicos e integração do calendário com CSVs e HTTP."""
import asyncio
import csv
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from sistema.core import dataset
from sistema.core.engine import process_round
from sistema.core.metrics import MetricsLogger
from sistema.core.reputation import MECHANISMS, ReputationTracker
from sistema.core.schemas import NodeResponse
from sistema.core.validation.runtime import ValidationPlan
from sistema.simulate import parse_args, run_simulation


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class ValidationIntegrationTests(unittest.TestCase):
    def run_sim(self, path, *options):
        args = parse_args(["--nodes", "5", "--rounds", "50", "--malicious", "0.4",
                           "--honest-accuracy", "1", "--collusion-value", "999",
                           "--output", str(path), "--no-row-sync", *options])
        args.quiet = True
        return run_simulation(args)

    def test_calendar_persistence_and_weights_next_round_all_mechanisms(self):
        with tempfile.TemporaryDirectory() as tmp:
            for mechanism in MECHANISMS:
                with self.subTest(mechanism=mechanism):
                    folder = Path(tmp) / mechanism
                    summary = self.run_sim(folder, "--mechanism", mechanism)
                    self.assertEqual(summary["validation_rounds"], [10, 20, 30, 40, 50])
                    self.assertEqual(summary["test_rounds"], [10, 20, 30, 40, 50])
                    self.assertEqual(summary["validation_accuracy"], 0.6)
                    results = read_csv(folder / "validation_results.csv")
                    self.assertEqual(len(results), 5 * 2 * 5)
                    history = read_csv(folder / "reputation_history.csv")
                    self.assertEqual(len(history), 5 * 51)
                    normal = read_csv(folder / "per_node.csv")
                    config = json.loads((folder / "summary.json").read_text(encoding="utf-8"))["config"]
                    self.assertFalse(set(config["normal_question_ids"]) & set(config["validation_question_ids"]))
                    self.assertFalse(config["normal_reputation_uses_ground_truth"])
                    for node in summary["final_reputation_by_node"]:
                        checkpoints = {int(r["checkpoint"]): float(r["reputation"])
                                       for r in history if r["node_id"] == node}
                        next_weight = next(float(r["weight_used"]) for r in normal
                                           if r["node_id"] == node and int(r["round_index"]) == 10)
                        self.assertEqual(next_weight, checkpoints[10])
                        self.assertAlmostEqual(checkpoints[50], summary["final_reputation_by_node"][node], places=4)

    def test_normal_updates_independent_of_ground_truth(self):
        for mechanism in MECHANISMS:
            snapshots = []
            for expected in (10, 999, None):
                with tempfile.TemporaryDirectory() as tmp:
                    tracker = ReputationTracker(["a", "b", "c"], mechanism=mechanism)
                    with MetricsLogger(tmp, overwrite=True, row_sync=False) as logger:
                        process_round(round_index=0, task_id="q", expected=expected,
                                      responses=[NodeResponse(n, "q", a, 1, "honest")
                                                 for n, a in [("a", 10), ("b", 10), ("c", 999)]],
                                      tracker=tracker, logger=logger)
                    snapshots.append(tracker.weights())
            self.assertEqual(snapshots[0], snapshots[1])
            self.assertEqual(snapshots[1], snapshots[2])
            self.assertGreater(snapshots[0]["a"], snapshots[0]["c"])

    def test_tied_consensus_holds_even_with_low_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = ReputationTracker(["a", "b"], min_confidence=0)
            with MetricsLogger(tmp, overwrite=True, row_sync=False) as logger:
                process_round(round_index=0, task_id="q", expected=1,
                              responses=[NodeResponse("a", "q", 1, 1, "honest"),
                                         NodeResponse("b", "q", 2, 1, "honest")],
                              tracker=tracker, logger=logger)
            self.assertEqual(tracker.weights(), {"a": 0.5, "b": 0.5})

    def test_reproducible_validation_and_disabled_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_sim(root / "a", "--seed", "12")
            self.run_sim(root / "b", "--seed", "12")
            disabled = self.run_sim(root / "off", "--seed", "12", "--no-validation")
            self.assertEqual(disabled["validation_rounds"], [])
            self.assertIsNone(disabled["validation_accuracy"])
            for filename in ("per_node.csv", "reputation_history.csv"):
                a = read_csv(root / "a" / filename)
                b = read_csv(root / "b" / filename)
                for r in a + b:
                    r.pop("experiment_id", None)
                self.assertEqual(a, b)
            # Selection and validation use separate RNGs, so normal responses match
            # even when the validation control is disabled.
            a = read_csv(root / "a" / "per_node.csv")
            off = read_csv(root / "off" / "per_node.csv")
            self.assertEqual([(r["task_id"], r["answer"]) for r in a],
                             [(r["task_id"], r["answer"]) for r in off])

    def test_custom_interval_and_no_completed_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summ = self.run_sim(root / "custom", "--rounds", "16", "--test-every", "7")
            self.assertEqual(summ["validation_rounds"], [7, 14])
            summ = self.run_sim(root / "short", "--rounds", "9")
            self.assertEqual(summ["validation_rounds"], [])

    def test_invalid_dataset_configuration_fails_early(self):
        rows = dataset.load_sample()
        for count in (0, -1, 10):
            with self.assertRaises(ValueError):
                ValidationPlan.prepare(rows, count=count)
        with self.assertRaises(ValueError):
            ValidationPlan.prepare([rows[0], rows[0]])

    def test_existing_validation_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "run"
            self.run_sim(folder)
            before = (folder / "rounds.csv").read_bytes()
            with self.assertRaises(FileExistsError):
                self.run_sim(folder, "--overwrite")
            self.assertEqual(before, (folder / "rounds.csv").read_bytes())


class HttpIntegrationTests(unittest.TestCase):
    def test_transport_failure_classification(self):
        import httpx
        from sistema.core.validation.transport import HttpNodeClient
        from sistema.core.validation.models import NodeSpec
        from sistema.core.enums import EvaluationOutcome
        node = NodeSpec("n", url="http://n")
        client = HttpNodeClient()
        with patch("httpx.post", side_effect=httpx.ReadTimeout("timeout")):
            reply = client.ask(node, "q", "question")
            self.assertEqual(reply.outcome_hint, EvaluationOutcome.TIMEOUT)
        for data in ([], {"answer": None}, {"answer": "invalid"}):
            response = httpx.Response(200, json=data, request=httpx.Request("POST", "http://n/infer"))
            with patch("httpx.post", return_value=response):
                reply = client.ask(node, "q", "question")
                self.assertIsNone(reply.answer)

    def test_http_orchestrator_uses_prompt_only_for_both_flows(self):
        import httpx
        from sistema.orchestrator import run
        from sistema.core.validation import transport
        rows = {r["id"]: r for r in dataset.load_sample()}
        seen = []

        def handler(request):
            if request.method == "GET":
                return httpx.Response(200, json={"status": "ok"})
            payload = json.loads(request.content)
            seen.append(payload)
            self.assertEqual(set(payload), {"task_id", "question"})
            return httpx.Response(200, json={"answer": rows[payload["task_id"]]["answer"], "latency_ms": 1})

        async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with httpx.Client(transport=httpx.MockTransport(handler)) as sync_client:
            with tempfile.TemporaryDirectory() as tmp:
                config = {"nodes": [{"id": "n1", "url": "http://n1", "profile": "honest"}],
                          "rounds": 11, "output_dir": tmp, "dataset": "sample", "mode": "real"}
                with patch.object(run.httpx, "AsyncClient", return_value=async_client), \
                     patch.object(transport, "HttpNodeClient", wraps=transport.HttpNodeClient), \
                     patch("httpx.post", side_effect=sync_client.post):
                    summary = asyncio.run(run.run_experiment(config))
                self.assertEqual(summary["validation_rounds"], [10])
                self.assertEqual(len(seen), 11 + 2)

    def test_worker_rejects_answer_fields_and_mock_uses_local_fixture(self):
        from pydantic import ValidationError
        from sistema.node import app
        row = dataset.load_sample()[0]
        for key in ("expected", "answer", "expected_answer"):
            with self.assertRaises(ValidationError):
                app.InferRequest(task_id=row["id"], question=row["question"], **{key: row["answer"]})
        req = app.InferRequest(task_id=row["id"], question=row["question"])
        with patch.object(app, "INFERENCE_MODE", "mock"), \
             patch.object(app, "_sleep_ms", new=AsyncMock()):
            answer, latency = asyncio.run(app._run_inference(req))
        self.assertIsNotNone(answer)


class ExportTests(unittest.TestCase):
    def test_exports_final_checkpoint_and_actual_calendar(self):
        from sistema.scripts.run_matrix import _run_one, _index_row, _write_index
        from sistema.scripts.export_validacao import export
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = dict(nodes=20, malicious_frac=0.65, seed=1, mechanism="ema",
                       collusion=True, collusion_value_arg=999, rounds=16, alpha=0.3,
                       honest_accuracy=1.0, test_every=7, validation_enabled=True,
                       validation_questions=2, dataset="sample", dataset_limit=None,
                       min_confidence=0.55)
            run = _run_one(cfg, str(root / "matrix"), False)
            self.assertIsNotNone(run)
            _write_index([_index_row(run)], str(root / "matrix" / "matrix_index.csv"))
            export(str(root / "matrix"), str(root / "export"))
            output = root / "export"
            style = (output / "figuras" / "estilo_figuras.tex").read_text(encoding="utf-8")
            self.assertIn(r"\pgfplotsinvokeforeach{7,14}", style)
            self.assertIn("xmax=19", style)
            source = read_csv(Path(run["output_dir"]) / "reputation_history.csv")
            expected = [float(r["reputation"]) for r in source
                        if r["checkpoint"] == "7" and r["profile"] == "honest"]
            exported = read_csv(output / "por_rodada" / "n20_m65_com_ema.csv")
            self.assertAlmostEqual(float(exported[6]["reputacao_honesta"]), sum(expected) / len(expected), places=4)
            self.assertEqual([r["rodada_teste"] for r in exported if r["rodada_teste"]], ["7", "14"])
            self.assertEqual(len(read_csv(output / "validacao_por_execucao.csv")), 2)
            with self.assertRaises(FileExistsError):
                export(str(root / "matrix"), str(root / "export"))


if __name__ == "__main__":
    unittest.main()
