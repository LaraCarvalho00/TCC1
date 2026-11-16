"""Valida a transmissão dos parâmetros experimentos ao coordenador e às réplicas."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sistema.core.defenses import preset, with_overrides

HAS_DOCKER_DEPS = all(importlib.util.find_spec(name) for name in ("yaml", "httpx", "fastapi"))
ROOT = Path(__file__).resolve().parents[2]


class DefenseOverridesTest(unittest.TestCase):
    def test_zero_calibration_and_different_alphas(self):
        config = with_overrides(preset("all"), calibration_rounds="0", consensus_alpha="0.30", oracle_alpha="0.95")
        self.assertEqual((config.calibration_rounds, config.consensus_alpha, config.oracle_alpha), (0, 0.3, 0.95))
        self.assertTrue(config.split_alpha)
        self.assertTrue(config.refuse_forged)

    def test_invalid_values_are_rejected(self):
        for args in ({"calibration_rounds": -1}, {"calibration_rounds": "1.5"},
                     {"consensus_alpha": float("nan")}, {"oracle_alpha": 1.1}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                with_overrides(preset("all"), **args)


@unittest.skipUnless(HAS_DOCKER_DEPS, "Requer dependências opcionais dos serviços Docker")
class DockerParametersTest(unittest.TestCase):
    def test_gateway_retries_transient_connection_with_same_identity(self):
        import asyncio
        from unittest.mock import AsyncMock, patch
        import httpx
        from sistema.node import app

        class Response:
            def raise_for_status(self): pass
            def json(self): return {"answer": 18, "latency_ms": 10}

        client = AsyncMock()
        client.post.side_effect = [httpx.ConnectError("temporário"), Response()]
        request = app.InferRequest(task_id="t", question="q", round_index=3)
        with patch.dict(os.environ, {"GATEWAY_URL": "http://gateway", "GATEWAY_RUN_ID": "r"}), \
             patch.object(app, "_http", return_value=client), \
             patch.object(app, "PROFILE", "honest"), \
             patch.object(app.asyncio, "sleep", new=AsyncMock()) as sleep:
            answer = asyncio.run(app._gateway_inference(request))
        self.assertEqual(answer, (18, 10))
        self.assertEqual(client.post.call_count, 2)
        self.assertEqual(client.post.call_args_list[0], client.post.call_args_list[1])
        self.assertEqual(sleep.await_count, 1)

    def test_gateway_connection_retries_are_bounded(self):
        import asyncio
        from unittest.mock import AsyncMock, patch
        import httpx
        from sistema.node import app

        client = AsyncMock()
        client.post.side_effect = httpx.ConnectError("indisponível")
        request = app.InferRequest(task_id="t", question="q", round_index=3)
        with patch.dict(os.environ, {"GATEWAY_URL": "http://gateway", "GATEWAY_RUN_ID": "r"}), \
             patch.object(app, "_http", return_value=client), \
             patch.object(app, "PROFILE", "honest"), \
             patch.object(app.asyncio, "sleep", new=AsyncMock()):
            with self.assertRaises(httpx.ConnectError):
                asyncio.run(app._gateway_inference(request))
        self.assertEqual(client.post.call_count, 8)

    def test_failed_audit_is_not_counted_as_applied(self):
        import asyncio
        from unittest.mock import AsyncMock, patch
        from sistema.orchestrator.run import _judge
        from sistema.core.protocol import ProtocolConfig
        cfg = ProtocolConfig()
        states = {"node-0": {"head": "genesis"}}
        with patch("sistema.orchestrator.run._post", new=AsyncMock(return_value={"status": "stale"})):
            with self.assertRaisesRegex(RuntimeError, "Conferência não aplicada"):
                asyncio.run(_judge(None, {"node-0": "http://node-0"}, states,
                                   {"node-0": {"answer": 1}}, [], 0, "task", 1, cfg, 1,
                                   require_applied=True))

    def test_gateway_colluders_apply_same_noise_to_same_base(self):
        code = '''
import asyncio, json
import sistema.node.app as app
class Response:
    def __init__(self, value): self.value = value
    def raise_for_status(self): pass
    def json(self): return {"answer": self.value, "latency_ms": 10}
class Client:
    async def post(self, url, json):
        return Response({"node-0": 18, "node-1": 100}[json["node_id"]])
app._http = lambda: Client()
r = asyncio.run(app._gateway_inference(app.InferRequest(task_id="t", question="q", round_index=8)))
print(json.dumps(r))
'''
        results = []
        for node_id in ("node-0", "node-1"):
            env = dict(os.environ, NODE_ID=node_id, PROFILE="malicious", INFERENCE_MODE="gateway",
                       GATEWAY_URL="http://gateway", GATEWAY_RUN_ID="t", COLLUDERS="node-0,node-1",
                       EXPERIMENT_SEED="0", MALICIOUS_STRATEGY="always", NOISE_MODE="relative",
                       NOISE_DISTANCE="0.2")
            out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, text=True,
                                 capture_output=True, timeout=30)
            self.assertEqual(out.returncode, 0, out.stderr)
            results.append(json.loads(out.stdout)[0])
        self.assertEqual(results[0], results[1])
        self.assertNotEqual(results[0], 18)

    def test_gateway_protocol_matches_coordinator(self):
        import yaml
        from sistema.scripts.gen_compose import generate, parse_args
        from sistema.orchestrator.run import _protocol_config
        from sistema.simulate import _inference_seed
        with tempfile.TemporaryDirectory() as temp:
            compose = Path(temp) / "docker-compose.yml"
            config = Path(temp) / "experiment.yaml"
            args = parse_args(["--nodes", "4", "--degree", "2", "--seed", "42", "--rounds", "10",
                               "--inference-mode", "gateway", "--gateway-run-id", "teste",
                               "--consensus-mode", "distance", "--validation-score", "exact",
                               "--malicious-strategy", "knows_schedule", "--audit-mode", "random",
                               "--audit-p", "0.2", "--compose-out", str(compose), "--config-out", str(config)])
            generate(args)
            services = yaml.safe_load(compose.read_text(encoding="utf-8"))["services"]
            cfg = _protocol_config(yaml.safe_load(config.read_text(encoding="utf-8")))
            for node_id in ("node-0", "node-1", "node-2", "node-3"):
                env = dict(os.environ, **services[node_id]["environment"])
                code = ("import json; from sistema.node.app import _protocol, _gateway_seed; "
                        "print(json.dumps({'audit':sorted(_protocol.audited_rounds),"
                        "'mode':_protocol.consensus_mode,'score':_protocol.validation_score,"
                        "'strategy':_protocol.malicious_strategy,'seed':_gateway_seed(3,"
                        "'" + node_id + "')}))")
                result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                got = json.loads(result.stdout)
                self.assertEqual(got["audit"], sorted(cfg.audited_rounds))
                self.assertEqual((got["mode"], got["score"], got["strategy"]), ("distance", "exact", "knows_schedule"))
                self.assertEqual(got["seed"], _inference_seed(42, 3, node_id))

    def test_generated_values_reach_coordinator_and_every_node(self):
        import yaml
        from sistema.scripts.gen_compose import generate, parse_args
        from sistema.orchestrator.run import _protocol_config

        with tempfile.TemporaryDirectory() as temp:
            compose = Path(temp) / "docker-compose.yml"
            config = Path(temp) / "experiment.yaml"
            args = parse_args(["--nodes", "4", "--degree", "2", "--calibration-rounds", "0",
                               "--consensus-alpha", "0.3", "--oracle-alpha", "0.95",
                               "--compose-out", str(compose), "--config-out", str(config)])
            generate(args)
            services = yaml.safe_load(compose.read_text(encoding="utf-8"))["services"]
            definition = yaml.safe_load(config.read_text(encoding="utf-8"))
            expected = _protocol_config(definition).defense.to_dict()
            self.assertEqual((expected["calibration_rounds"], expected["consensus_alpha"], expected["oracle_alpha"]), (0, 0.3, 0.95))
            for name in ("node-0", "node-1", "node-2", "node-3"):
                env = dict(os.environ, **services[name]["environment"])
                command = [sys.executable, "-c", "import json;from sistema.node.app import _protocol;print(json.dumps(_protocol.defense.to_dict()))"]
                result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), expected)

    def test_generator_rejects_invalid_values_before_writing_files(self):
        from sistema.scripts.gen_compose import generate, parse_args
        with tempfile.TemporaryDirectory() as temp:
            compose = Path(temp) / "docker-compose.yml"
            config = Path(temp) / "experiment.yaml"
            args = parse_args(["--nodes", "4", "--degree", "2", "--oracle-alpha", "1.1",
                               "--compose-out", str(compose), "--config-out", str(config)])
            with self.assertRaises(ValueError):
                generate(args)
            self.assertFalse(compose.exists())
            self.assertFalse(config.exists())
