"""Testa controle da grade sem iniciar contêineres nem baixar o modelo."""
from pathlib import Path
from contextlib import closing
import json
import sqlite3
import subprocess
import tempfile
import unittest
from unittest import mock

from sistema.scripts import runner_containers as runner


class RunnerTest(unittest.TestCase):
    def test_shutdown_timeout_cleans_the_gateway_process_tree_on_windows(self):
        process = mock.Mock(pid=12345)
        process.wait.side_effect = [subprocess.TimeoutExpired("gateway", 1), None]
        process.poll.return_value = None
        with mock.patch.object(runner.os, "name", "nt"), \
             mock.patch.object(runner.urllib.request, "urlopen", side_effect=OSError), \
             mock.patch.object(runner.subprocess, "run") as cleanup:
            runner._shutdown(1234, "secret", process, runner.time.monotonic())
        self.assertEqual(cleanup.call_args.args[0], ["taskkill", "/PID", "12345", "/T", "/F"])
        process.terminate.assert_not_called()
        self.assertEqual(process.wait.call_count, 2)

    def test_shared_worker_count_is_validated_before_docker_or_output(self):
        for workers in (0, 6, True, 1.5):
            with self.subTest(workers=workers), mock.patch.object(runner, "_fingerprint") as fingerprint:
                with self.assertRaisesRegex(ValueError, "1 a 5"):
                    runner.run(Path("unused"), inference_workers=workers)
                fingerprint.assert_not_called()

    def test_cli_passes_five_workers_and_pinned_model(self):
        with mock.patch.object(runner, "run", return_value={"status": "concluido"}) as run:
            status = runner.main(["--saida", "example", "--nos", "50", "--rodadas", "50",
                                  "--modelo", "Qwen/Qwen3-0.6B", "--inference-workers", "5",
                                  "--model-snapshot", "snapshot", "--model-revision", "revision",
                                  "--prazo-estendido", "--limite-segundos", "604800", "--codigo-da-imagem"])
        self.assertEqual(status, 0)
        self.assertEqual(run.call_args.kwargs["inference_workers"], 5)
        self.assertEqual(run.call_args.kwargs["nodes"], 50)
        self.assertEqual(run.call_args.kwargs["rounds"], 50)
        self.assertEqual(run.call_args.kwargs["model_snapshot"], "snapshot")
        self.assertEqual(run.call_args.kwargs["model_revision"], "revision")
        self.assertTrue(run.call_args.kwargs["extended_deadline"])
        self.assertFalse(run.call_args.kwargs["mount_code"])

    def test_source_snapshot_preserves_host_code_and_tasks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for directory in ("sistema/node", "sistema/dados", "sistema/tests", "sistema/results"):
                (root / directory).mkdir(parents=True, exist_ok=True)
            code = root / "sistema/node/inference.py"
            code.write_text("original", encoding="utf-8")
            (root / "sistema/dados/banco_smol.json").write_text("{\"tarefas\":[]}", encoding="utf-8")
            (root / "sistema/tests/test_example.py").write_text("test")
            (root / "sistema/results/output.py").write_text("output")
            with mock.patch.object(runner, "ROOT", root):
                frozen = runner._freeze_source(root / "grade")
                code.write_text("changed", encoding="utf-8")
                self.assertEqual((frozen / "sistema/node/inference.py").read_text(), "original")
                self.assertEqual((frozen / "sistema/dados/banco_smol.json").read_text(), "{\"tarefas\":[]}")
                self.assertFalse((frozen / "sistema/tests").exists())
                self.assertFalse((frozen / "sistema/results").exists())
                self.assertEqual(runner._freeze_source(root / "grade"), frozen)
                self.assertEqual((frozen / "sistema/node/inference.py").read_text(), "original")

    def test_five_workers_are_launched_and_recorded_with_local_snapshot(self):
        output_root = runner.ROOT / "sistema" / "results"
        output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output_root) as temp:
            root = Path(temp)
            out, snapshot = root / "grade", root / "revision"
            snapshot.mkdir()
            saved = {}

            def generate(args):
                saved["attempt"] = runner.ROOT / args.output_dir
                Path(args.compose_out).write_text("services: {}", encoding="utf-8")
                (runner.ROOT / args.config_out).write_text("{}", encoding="utf-8")

            def command(args, **kwargs):
                if "up" in args:
                    (saved["attempt"] / "summary.json").write_text("{}", encoding="utf-8")
                return subprocess.CompletedProcess(args, 0, "", "")

            with mock.patch.object(runner, "generate", side_effect=generate), \
                 mock.patch.object(runner, "_fingerprint", return_value={"codigo": "teste"}), \
                 mock.patch.object(runner.subprocess, "run", side_effect=command), \
                 mock.patch.object(runner.subprocess, "Popen") as process, \
                 mock.patch.object(runner, "_health") as health, mock.patch.object(runner, "_shutdown"), \
                 mock.patch.object(runner, "_verify_completed"):
                result = runner.run(out, seconds=180, cleanup_margin=30, fractions=(0.2,),
                                    probabilities=(0.1,), scores=("exact",), nodes=50, rounds=50,
                                    inference_workers=5, model="Qwen/Qwen3-0.6B",
                                    model_snapshot=snapshot, model_revision="revision")
            config = result["configuracao"]
            self.assertEqual(config["inference_layout"], "shared")
            self.assertEqual(config["instancias_modelo"], 5)
            self.assertEqual(config["inference_workers"], 5)
            self.assertEqual(config["model_revision"], "revision")
            self.assertEqual(result["chamadas_previstas"], 2500)
            argv = process.call_args.args[0]
            self.assertEqual(argv[argv.index("--workers") + 1], "5")
            self.assertEqual(argv[argv.index("--model-snapshot") + 1], str(snapshot.resolve()))
            self.assertEqual(argv[argv.index("--model-revision") + 1], "revision")
            self.assertEqual(health.call_args.kwargs["workers"], 5)
            with mock.patch.object(runner, "_fingerprint", return_value={"codigo": "teste"}):
                with self.assertRaisesRegex(ValueError, "configuração difere"):
                    runner.run(out, seconds=180, cleanup_margin=30, fractions=(0.2,),
                               probabilities=(0.1,), scores=("exact",), nodes=50, rounds=50,
                               inference_workers=4, model="Qwen/Qwen3-0.6B", model_snapshot=snapshot,
                               model_revision="revision", resume=True)

    def test_resume_rejects_changed_fingerprint(self):
        output_root = runner.ROOT / "sistema" / "results"
        output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output_root) as temp:
            out = Path(temp) / "grade"
            out.mkdir()
            config = {"nos": 20, "rodadas": 10, "rodadas_iniciais_honestas": 5, "sementes": [0], "fracoes": [0.2],
                      "probabilidades": [0.2], "notas": ["exact"], "quantizacao": "nf4",
                      "tempo_maximo_s": 180, "ruido": "relative", "distancia": 0.2,
                      "conluio": True, "node_image": "tcc-node:latest", "orchestrator_image": "tcc-orch:latest",
                      "fingerprint": {"codigo": "antigo"}}
            (out / "manifesto_grade.json").write_text(json.dumps({"configuracao": config}))
            with mock.patch.object(runner, "_fingerprint", return_value={"codigo": "modificado"}):
                with self.assertRaisesRegex(ValueError, "configuração difere"):
                    runner.run(out, seconds=180, cleanup_margin=30, fractions=(0.2,),
                               probabilities=(0.2,), scores=("exact",), nodes=20, rounds=10, resume=True)

    def test_verify_requires_each_node_and_round(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "summary.json").write_text(json.dumps({"config": {"ledgers_valid": True}, "summary": {"rounds": 1}}))
            (root / "rounds.csv").write_text("round_index,num_nodes\n0,2\n")
            (root / "per_node.csv").write_text("round_index,node_id\n0,node-0\n0,node-1\n")
            db = root / "cache.sqlite"
            with closing(sqlite3.connect(db)) as conn:
                conn.execute("CREATE TABLE gateway_requests (round_index INTEGER, node_id TEXT)")
                conn.execute("CREATE TABLE generations (seed INTEGER)")
                conn.executemany("INSERT INTO gateway_requests VALUES (?,?)", [(0, "node-0"), (0, "node-1")])
                conn.executemany("INSERT INTO generations VALUES (?)", [(0,), (1,)])
                conn.commit()
            runner._verify_completed(root, db, 2, 1)
            (root / "per_node.csv").write_text("round_index,node_id\n0,node-0\n0,node-0\n")
            with self.assertRaisesRegex(RuntimeError, "duplicadas"):
                runner._verify_completed(root, db, 2, 1)

    def test_completed_scenario_and_scoped_cleanup(self):
        output_root = runner.ROOT / "sistema" / "results"
        output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output_root) as temp:
            out = Path(temp) / "grade"
            saved = {}

            def generate(args):
                saved["attempt"] = runner.ROOT / args.output_dir
                Path(args.compose_out).write_text("services: {}", encoding="utf-8")
                (runner.ROOT / args.config_out).write_text("{}", encoding="utf-8")

            def command(args, **kwargs):
                if args[:3] == ["docker", "ps", "-aq"]:
                    return subprocess.CompletedProcess(args, 0, "", "")
                if "up" in args:
                    (saved["attempt"] / "summary.json").write_text("{}", encoding="utf-8")
                return subprocess.CompletedProcess(args, 0, "", "")

            with mock.patch.object(runner, "generate", side_effect=generate), \
                 mock.patch.object(runner, "_fingerprint", return_value={"codigo": "teste"}), \
                 mock.patch.object(runner.subprocess, "run", side_effect=command) as calls, \
                 mock.patch.object(runner.subprocess, "Popen"), \
                 mock.patch.object(runner, "_health"), mock.patch.object(runner, "_shutdown"), \
                 mock.patch.object(runner, "_verify_completed"):
                data = runner.run(out, seconds=180, cleanup_margin=30, fractions=(0.2,),
                                  probabilities=(0.2,), scores=("exact",), nodes=20, rounds=10)
            self.assertEqual(data["status"], "concluido")
            self.assertEqual(data["chamadas_previstas"], 200)
            self.assertEqual(data["cenarios"][0]["status"], "concluido")
            on_disk = json.loads((out / "manifesto_grade.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk["status"], "concluido")
            downs = [c.args[0] for c in calls.call_args_list if "down" in c.args[0]]
            self.assertEqual(len(downs), 1)
            self.assertIn(data["cenarios"][0]["tentativas"][0]["projeto_docker"], downs[0])

    def test_six_round_configuration_is_propagated_and_recorded(self):
        output_root = runner.ROOT / "sistema" / "results"
        output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output_root) as temp:
            out = Path(temp) / "grade"
            saved = {}

            def generate(args):
                saved["args"] = args
                saved["attempt"] = runner.ROOT / args.output_dir
                Path(args.compose_out).write_text("services: {}", encoding="utf-8")
                (runner.ROOT / args.config_out).write_text("{}", encoding="utf-8")

            def command(args, **kwargs):
                if "up" in args:
                    (saved["attempt"] / "summary.json").write_text("{}", encoding="utf-8")
                return subprocess.CompletedProcess(args, 0, "", "")

            with mock.patch.object(runner, "generate", side_effect=generate), \
                 mock.patch.object(runner, "_fingerprint", return_value={"codigo": "teste"}), \
                 mock.patch.object(runner.subprocess, "run", side_effect=command), \
                 mock.patch.object(runner.subprocess, "Popen"), \
                 mock.patch.object(runner, "_health"), mock.patch.object(runner, "_shutdown"), \
                 mock.patch.object(runner, "_verify_completed"):
                data = runner.run(out, seconds=180, cleanup_margin=30, fractions=(0.2,),
                                  probabilities=(0.2,), scores=("exact",), nodes=20,
                                  rounds=6, honest_rounds=1, seed=10)
                self.assertEqual(data["status"], "concluido")
                self.assertEqual(data["chamadas_previstas"], 120)
                self.assertEqual(data["configuracao"]["rodadas_iniciais_honestas"], 1)
                self.assertEqual(data["configuracao"]["sementes"], [10])
                self.assertEqual(data["cenarios"][0]["semente"], 10)
                self.assertEqual(saved["args"].honest_rounds, 1)
                self.assertEqual(saved["args"].seed, 10)
                self.assertEqual(saved["args"].rounds, 6)
                self.assertEqual(saved["args"].num_tasks, 6)
                with self.assertRaisesRegex(ValueError, "configuração difere"):
                    runner.run(out, seconds=180, cleanup_margin=30, fractions=(0.2,),
                               probabilities=(0.2,), scores=("exact",), nodes=20,
                               rounds=6, honest_rounds=2, seed=10, resume=True)

    def test_honest_rounds_must_leave_rounds_for_attacks(self):
        with self.assertRaisesRegex(ValueError, "menores que o total"):
            runner.run(Path("unused"), rounds=6, honest_rounds=6)

    def test_cli_passes_rounds_honest_rounds_and_seed(self):
        with mock.patch.object(runner, "run", return_value={"status": "concluido"}) as run:
            status = runner.main(["--saida", "example", "--rodadas", "6", "--rodadas-honestas", "1", "--semente", "10"])
        self.assertEqual(status, 0)
        self.assertEqual(run.call_args.kwargs["rounds"], 6)
        self.assertEqual(run.call_args.kwargs["honest_rounds"], 1)
        self.assertEqual(run.call_args.kwargs["seed"], 10)

    def test_timeout_leaves_partial_status(self):
        output_root = runner.ROOT / "sistema" / "results"
        output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output_root) as temp:
            out = Path(temp) / "grade"
            def generate(args):
                Path(args.compose_out).write_text("services: {}", encoding="utf-8")
                (runner.ROOT / args.config_out).write_text("{}", encoding="utf-8")
            def command(args, **kwargs):
                if "up" in args:
                    raise subprocess.TimeoutExpired(args, 1)
                return subprocess.CompletedProcess(args, 0, "", "")
            with mock.patch.object(runner, "generate", side_effect=generate), \
                 mock.patch.object(runner, "_fingerprint", return_value={"codigo": "teste"}), \
                 mock.patch.object(runner.subprocess, "run", side_effect=command), \
                 mock.patch.object(runner.subprocess, "Popen"), \
                 mock.patch.object(runner, "_health"), mock.patch.object(runner, "_shutdown"):
                data = runner.run(out, seconds=180, cleanup_margin=30, fractions=(0.2,),
                                  probabilities=(0.2,), scores=("exact",), nodes=20, rounds=10)
            self.assertEqual(data["status"], "tempo_esgotado")
            self.assertEqual(data["cenarios"][0]["status"], "interrompido")

    def test_docker_cleanup_timeout_still_shuts_down_gateway(self):
        output_root = runner.ROOT / "sistema" / "results"
        output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output_root) as temp:
            out = Path(temp) / "grade"
            def generate(args):
                Path(args.compose_out).write_text("services: {}", encoding="utf-8")
                (runner.ROOT / args.config_out).write_text("{}", encoding="utf-8")
            def command(args, **kwargs):
                if "down" in args:
                    raise subprocess.TimeoutExpired(args, 1)
                return subprocess.CompletedProcess(args, 1 if "up" in args else 0, "", "")
            with mock.patch.object(runner, "generate", side_effect=generate), \
                 mock.patch.object(runner, "_fingerprint", return_value={"codigo": "teste"}), \
                 mock.patch.object(runner.subprocess, "run", side_effect=command), \
                 mock.patch.object(runner.subprocess, "Popen"), \
                 mock.patch.object(runner, "_health"), mock.patch.object(runner, "_shutdown") as shutdown:
                data = runner.run(out, seconds=180, cleanup_margin=30, fractions=(0.2,),
                                  probabilities=(0.2,), scores=("exact",), nodes=20, rounds=10)
            shutdown.assert_called_once()
            self.assertEqual(data["status"], "falhou")
            self.assertIn("erro_encerramento_docker", data["cenarios"][0]["tentativas"][0])
            self.assertEqual(json.loads((out / "manifesto_grade.json").read_text())["status"], "falhou")


if __name__ == "__main__":
    unittest.main()
