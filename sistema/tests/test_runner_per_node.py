"""Each dedicated node must load and generate before a scenario is completed."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from sistema.scripts import runner_containers as runner


class DedicatedRunnerTest(unittest.TestCase):
    def completed_fixture(self, root):
        (root / "summary.json").write_text(json.dumps({"config": {"ledgers_valid": True}, "summary": {"rounds": 2}}))
        (root / "rounds.csv").write_text("round_index,num_nodes,task_id\n0,2,t0\n1,2,t1\n")
        (root / "per_node.csv").write_text("round_index,node_id,task_id,answer\n0,node-0,t0,100\n0,node-1,t0,150.0\n1,node-0,t1,\n1,node-1,t1,200\n")
        for node in range(2):
            path = root / f"node-{node}"
            path.mkdir()
            with closing(sqlite3.connect(path / "inferencias.sqlite")) as db:
                db.execute("CREATE TABLE meta (id INTEGER PRIMARY KEY, config TEXT)")
                identity = {"node_id": f"node-{node}", "run_id": "scenario", "quantization": "nf4",
                            "model": "/models", "device": "cuda", "revision": "expected-revision"}
                db.execute("INSERT INTO meta VALUES (1, ?)", (json.dumps(identity),))
                db.execute("CREATE TABLE generations (round_index INTEGER, node_id TEXT, task_id TEXT)")
                db.executemany("INSERT INTO generations VALUES (?,?,?)", [(i, f"node-{node}", f"t{i}") for i in range(2)])
                db.execute("CREATE TABLE responses (round_index INTEGER, answer TEXT)")
                answers = [100, None] if node == 0 else [150, 200]
                db.executemany("INSERT INTO responses VALUES (?,?)", [(i, json.dumps(answer)) for i, answer in enumerate(answers)])
                db.commit()

    def test_loads_one_node_per_gpu_then_waits_before_next_batch(self):
        seen = []

        def execute(args, **kwargs):
            seen.append(args)
            if "exec" in args:
                node = args[args.index("-T") + 1]
                return subprocess.CompletedProcess(args, 0, json.dumps({"model_loaded": True, "model_instances": 1, "node_id": node}), "")
            return subprocess.CompletedProcess(args, 0, "", "")

        with mock.patch.object(runner.subprocess, "run", side_effect=execute):
            runner._start_per_node(["docker", "compose"], 6, 2, runner.time.monotonic() + 30, mock.Mock())
        batches = [args[args.index("--no-deps") + 1:] for args in seen if "up" in args]
        self.assertEqual(batches, [["node-0", "node-1"], ["node-2", "node-3"], ["node-4", "node-5"]])
        self.assertEqual(["up" if "up" in args else "health" for args in seen],
                         ["up", "health", "health", "up", "health", "health", "up", "health", "health"])

    def test_rejects_insufficient_slots_before_provisioning(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(runner, "_fingerprint") as fingerprint:
            with self.assertRaisesRegex(ValueError, "excede os slots"):
                runner.run(Path(temp) / "grade", inference_layout="per_node", nodes=50,
                           gpu_count=1, models_per_gpu=8, model_snapshot=temp)
        fingerprint.assert_not_called()

    def test_requires_own_generation_cache_for_every_node(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.completed_fixture(root)
            runner._verify_per_node(root, root, 2, 2, "scenario", "expected-revision")
            with closing(sqlite3.connect(root / "node-1" / "inferencias.sqlite")) as db:
                db.execute("DELETE FROM generations WHERE round_index=1")
                db.commit()
            with self.assertRaisesRegex(RuntimeError, "node-1"):
                runner._verify_per_node(root, root, 2, 2, "scenario")

    def test_rejects_model_revision_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.completed_fixture(root)
            with self.assertRaisesRegex(RuntimeError, "Cache de node-0"):
                runner._verify_per_node(root, root, 2, 2, "scenario", "wrong-revision")

    def test_rejects_missing_or_duplicate_submitted_responses(self):
        for sql in ("DELETE FROM responses WHERE round_index=1",
                    "INSERT INTO responses VALUES (0, '100')"):
            with self.subTest(sql=sql), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.completed_fixture(root)
                with closing(sqlite3.connect(root / "node-0" / "inferencias.sqlite")) as db:
                    db.execute(sql)
                    db.commit()
                with self.assertRaisesRegex(RuntimeError, "Respostas enviadas de node-0"):
                    runner._verify_per_node(root, root, 2, 2, "scenario")

    def test_rejects_response_or_task_disagreement_with_metrics(self):
        for sql, error in (("UPDATE responses SET answer='101' WHERE round_index=0", "Resposta enviada"),
                           ("UPDATE generations SET task_id='another' WHERE round_index=0", "Tarefas")):
            with self.subTest(sql=sql), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                self.completed_fixture(root)
                with closing(sqlite3.connect(root / "node-0" / "inferencias.sqlite")) as db:
                    db.execute(sql)
                    db.commit()
                with self.assertRaisesRegex(RuntimeError, error):
                    runner._verify_per_node(root, root, 2, 2, "scenario")

    def test_dedicated_run_never_starts_gateway_and_readies_nodes_before_orchestrator(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / "sistema" / "results").mkdir(parents=True)
            snapshot = root / "snapshot"
            snapshot.mkdir()
            saved, operations = {}, []

            def parse(args):
                # The generator's real options are tested separately. This test
                # isolates lifecycle ordering from YAML generation.
                saved["argv"] = args
                return SimpleNamespace(output_dir=args[args.index("--output-dir") + 1],
                                       config_out=args[args.index("--config-out") + 1],
                                       compose_out=args[args.index("--compose-out") + 1])

            def generate(args):
                saved["attempt"] = root / args.output_dir
                Path(args.compose_out).write_text("services: {}")
                (root / args.config_out).write_text("{}")

            def command(args, **kwargs):
                if "up" in args:
                    operations.append("orchestrator")
                    (saved["attempt"] / "summary.json").write_text("{}")
                return subprocess.CompletedProcess(args, 0, "", "")

            with mock.patch.object(runner, "ROOT", root), \
                 mock.patch.object(runner, "parse_args", side_effect=parse), \
                 mock.patch.object(runner, "generate", side_effect=generate), \
                 mock.patch.object(runner, "_fingerprint", return_value={}), \
                 mock.patch.object(runner, "_start_per_node", side_effect=lambda *a: operations.append("ready")) as startup, \
                 mock.patch.object(runner, "_verify_per_node") as verify, \
                 mock.patch.object(runner.subprocess, "run", side_effect=command) as commands, \
                 mock.patch.object(runner.subprocess, "Popen") as gateway:
                result = runner.run(root / "sistema" / "results" / "dedicated", seconds=180, cleanup_margin=30,
                                    nodes=10, rounds=6, honest_rounds=1, fractions=(.2,), probabilities=(.1,),
                                    scores=("exact",), inference_layout="per_node", gpu_count=2,
                                    models_per_gpu=8, model_snapshot=snapshot)
            self.assertEqual(result["status"], "concluido")
            self.assertEqual(operations, ["ready", "orchestrator"])
            gateway.assert_not_called()
            startup.assert_called_once()
            verify.assert_called_once()
            self.assertEqual(result["configuracao"]["instancias_modelo"], 10)
            self.assertEqual(saved["argv"][saved["argv"].index("--inference-mode") + 1], "model")
            self.assertEqual(saved["argv"][saved["argv"].index("--mode") + 1], "real")
            self.assertNotIn("--gateway-url", saved["argv"])
            up = next(call.args[0] for call in commands.call_args_list if "up" in call.args[0])
            self.assertEqual(up[-2:], ["--no-deps", "orchestrator"])
            self.assertTrue(any("down" in call.args[0] for call in commands.call_args_list))

    def test_dedicated_start_failure_preserves_partial_and_cleans_nodes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / "sistema" / "results").mkdir(parents=True)
            def parse(args):
                return SimpleNamespace(output_dir=args[args.index("--output-dir") + 1],
                                       config_out=args[args.index("--config-out") + 1],
                                       compose_out=args[args.index("--compose-out") + 1])
            def generate(args):
                Path(args.compose_out).write_text("services: {}")
                (root / args.config_out).write_text("{}")
            with mock.patch.object(runner, "ROOT", root), \
                 mock.patch.object(runner, "parse_args", side_effect=parse), \
                 mock.patch.object(runner, "generate", side_effect=generate), \
                 mock.patch.object(runner, "_fingerprint", return_value={}), \
                 mock.patch.object(runner, "_start_per_node", side_effect=RuntimeError("CUDA OOM")), \
                 mock.patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as commands:
                result = runner.run(root / "sistema" / "results" / "failed", seconds=180, cleanup_margin=30,
                                    nodes=10, rounds=6, honest_rounds=1, fractions=(.2,), probabilities=(.1,),
                                    scores=("exact",), inference_layout="per_node", gpu_count=2, model_snapshot=root)
            self.assertEqual(result["status"], "falhou")
            self.assertIn("CUDA OOM", result["cenarios"][0]["tentativas"][0]["erro"])
            self.assertTrue(any("down" in call.args[0] for call in commands.call_args_list))


if __name__ == "__main__":
    unittest.main()
