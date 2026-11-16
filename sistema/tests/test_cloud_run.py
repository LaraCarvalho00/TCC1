"""Contrato do worker sem credenciais, Docker ou GPU."""
from pathlib import Path
from contextlib import closing
import json
import subprocess
import tempfile
import unittest
from unittest import mock

from sistema.scripts import cloud_run as cloud
from sistema.scripts import runner_containers as runner


def config(**changes):
    values = {"run_id": "gha-123-1", "results_bucket": "experimentos-testes",
              "results_prefix": "runs/gha-123-1", "aws_region": "us-east-1",
              "model_snapshot": str(Path("/models/smol").resolve()), "model_revision": "abc123"}
    values.update(changes)
    return cloud.validate(values)


class CloudContractTest(unittest.TestCase):
    def test_matrix_has_forty_thousand_fresh_generations(self):
        cfg = config()
        with tempfile.TemporaryDirectory() as temp:
            publisher = cloud.Publisher(cfg, Path(temp))
            with mock.patch.object(publisher, "aws"):
                status = publisher.status("running", Path(temp) / "not-started")
            self.assertEqual(status["total_scenarios"], 16)
            self.assertEqual(status["planned_generations"], 40000)
            self.assertFalse(status["upload_complete"])
        args = cloud.command(cfg, Path("output"), 10000)
        self.assertIn("--prazo-estendido", args)
        self.assertEqual(args[args.index("--nos") + 1], "50")
        self.assertEqual(args[args.index("--timeout-protocolo") + 1], "3600")
        self.assertEqual(args[args.index("--inference-layout") + 1], "per_node")
        self.assertEqual(args[args.index("--gpu-count") + 1], "8")
        self.assertNotIn("gateway", args)

    def test_custom_containers_receive_explicit_counts(self):
        cfg = config(mode="custom", honest_nodes=37, malicious_nodes=13)
        args = cloud.command(cfg, Path("output"), 10000)
        self.assertEqual(args[args.index("--honestos") + 1], "37")
        self.assertEqual(args[args.index("--maliciosos") + 1], "13")

    def test_rejects_inconsistent_or_unbounded_payloads(self):
        invalid = ({"results_prefix": "other/run"}, {"run_id": "../escape"}, {"max_hours": 169},
                   {"workers": 50}, {"nodes": 51}, {"nodes": True},
                   {"mode": "custom", "honest_nodes": 37, "malicious_nodes": 12},
                   {"honest_rounds": 50}, {"model": "/local/path"})
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                config(**change)

    def test_terminal_marker_is_published_after_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            runtime = path / "runtime"
            runtime.mkdir()
            output = path / "output"
            output.mkdir()
            (output / "rounds.csv").write_text("round\n0\n")
            publisher = cloud.Publisher(config(), runtime)
            with mock.patch.object(publisher, "aws") as aws:
                status = publisher.finish(output, "completed")
            commands = [call.args for call in aws.call_args_list]
            self.assertTrue(commands[-2][3].endswith("/results.tar.gz"))
            self.assertTrue(commands[-1][3].endswith("/status.json"))
            self.assertTrue(status["upload_complete"])

    def test_upload_failure_never_publishes_completed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            publisher = cloud.Publisher(config(), root)
            with mock.patch.object(publisher, "snapshot"), \
                 mock.patch.object(publisher, "aws", side_effect=RuntimeError("offline")), \
                 mock.patch.object(publisher, "status") as status:
                with self.assertRaisesRegex(RuntimeError, "offline"):
                    publisher.finish(root / "no-results", "completed")
            status.assert_not_called()

    def test_checkpoints_skip_unchanged_databases(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output, runtime = root / "output", root / "runtime"
            cache = output / "cenarios" / "c1" / "inferencias.sqlite"
            cache.parent.mkdir(parents=True)
            runtime.mkdir()
            with closing(sqlite3.connect(cache)) as connection:
                connection.execute("CREATE TABLE generations (value INTEGER)")
                connection.commit()
            publisher = cloud.Publisher(config(), runtime)
            with mock.patch.object(publisher, "aws") as aws:
                publisher.snapshot(output)
                publisher.snapshot(output)
                checkpoint_calls = [call for call in aws.call_args_list
                                    if any("/checkpoints/c1/" in str(value) for value in call.args)]
                self.assertEqual(len(checkpoint_calls), 1)
                with closing(sqlite3.connect(cache)) as connection:
                    connection.execute("INSERT INTO generations VALUES (1)")
                    connection.commit()
                publisher.snapshot(output)
                checkpoint_calls = [call for call in aws.call_args_list
                                    if any("/checkpoints/c1/" in str(value) for value in call.args)]
                self.assertEqual(len(checkpoint_calls), 2)

    def test_bootstrap_failure_uploads_logs_and_shuts_down(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with mock.patch.object(cloud, "ROOT", root), \
                 mock.patch.object(cloud.Publisher, "finish") as finish, \
                 mock.patch.object(cloud.subprocess, "run") as commands:
                result = cloud.run(config(), runtime=root / "runtime", bootstrap_error="pip failed")
            self.assertEqual(result, 1)
            self.assertEqual(finish.call_args.args[1], "failed")
            self.assertIn("pip failed", finish.call_args.kwargs["error"])
            commands.assert_called_once_with(["shutdown", "-h", "now"], check=False, timeout=30)

    def test_runner_extended_deadline_and_custom_scenario_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / "sistema" / "results").mkdir(parents=True)
            saved = {}

            def generate(args):
                saved["args"] = args
                saved["attempt"] = root / args.output_dir
                Path(args.compose_out).write_text("services: {}")
                (root / args.config_out).write_text("{}")

            def execute(args, **kwargs):
                if "up" in args:
                    (saved["attempt"] / "summary.json").write_text("{}")
                return subprocess.CompletedProcess(args, 0, "", "")

            with mock.patch.object(runner, "ROOT", root), \
                 mock.patch.object(runner, "_fingerprint", return_value={}), \
                 mock.patch.object(runner, "generate", side_effect=generate), \
                 mock.patch.object(runner.subprocess, "run", side_effect=execute), \
                 mock.patch.object(runner.subprocess, "Popen"), \
                 mock.patch.object(runner, "_health"), mock.patch.object(runner, "_shutdown"), \
                 mock.patch.object(runner, "_verify_completed"):
                data = runner.run(root / "sistema" / "results" / "test", seconds=86400,
                                  extended_deadline=True, custom_counts=(37, 13), nodes=50, rounds=50,
                                  protocol_timeout=3600)
            self.assertEqual(data["status"], "concluido")
            self.assertEqual(data["chamadas_previstas"], 10000)
            self.assertEqual(len(data["cenarios"]), 4)
            self.assertEqual(saved["args"].malicious, .26)
            self.assertTrue(all("h37-m13" in item["id"] for item in data["cenarios"]))
            self.assertEqual(data["configuracao"]["contagens_personalizadas"], [37, 13])


if __name__ == "__main__":
    unittest.main()
