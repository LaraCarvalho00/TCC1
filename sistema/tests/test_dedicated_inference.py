"""Resident models remain private to each participant without requiring CUDA."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from sistema.node.dedicated_inference import DedicatedModel


class FakeModel:
    def __init__(self):
        self.calls = []

    def sample(self, question, **kwargs):
        self.calls.append((question, kwargs))
        return 100, "#### 100"


class DedicatedInferenceTest(unittest.TestCase):
    def create(self, cache, **changes):
        values = dict(node_id="node-1", run_id="scenario-1", model_name="/models", cache_dir=cache,
                      factory=FakeModel)
        values.update(changes)
        return DedicatedModel(**values)

    def test_concurrent_retries_load_one_instance_and_generate_once(self):
        with tempfile.TemporaryDirectory() as temp:
            loads = []
            def factory():
                loads.append(True)
                return FakeModel()
            backend = self.create(temp, factory=factory)
            with ThreadPoolExecutor(max_workers=8) as workers:
                results = list(workers.map(lambda _: backend.generate(round_index=0, task_id="t0", question="q?", seed=12), range(8)))
            self.assertEqual(len(loads), 1)
            self.assertTrue(backend.loaded)
            self.assertEqual(len(backend.model.calls), 1)
            self.assertTrue(all(item["answer"] == 100 for item in results))
            backend.record_response(0, 150, "node-0")
            backend.record_response(0, 150, "node-0")
            with self.assertRaisesRegex(ValueError, "conflicting"):
                backend.record_response(0, 99, "node-0")

    def test_restart_recovers_own_cache_and_rejects_changed_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            self.create(temp).generate(round_index=0, task_id="t", question="q", seed=2)
            resumed = self.create(temp)
            self.assertEqual(resumed.generate(round_index=0, task_id="t", question="q", seed=2)["answer"], 100)
            self.assertFalse(resumed.loaded)  # HTTP startup loads eagerly; cache reads never generate.
            with self.assertRaisesRegex(ValueError, "another node"):
                self.create(temp, node_id="node-2")
            with self.assertRaisesRegex(ValueError, "another node"):
                self.create(temp, run_id="scenario-2")
            with self.assertRaisesRegex(ValueError, "conflicting"):
                resumed.generate(round_index=0, task_id="t", question="changed", seed=2)

    def test_nodes_have_separate_model_objects_and_responses(self):
        with tempfile.TemporaryDirectory() as temp:
            left = self.create(Path(temp) / "node-0", node_id="node-0")
            right = self.create(Path(temp) / "node-1", node_id="node-1")
            left.generate(round_index=0, task_id="t", question="q", seed=1)
            right.generate(round_index=0, task_id="t", question="q", seed=2)
            self.assertIsNot(left.model, right.model)
            self.assertNotEqual(left.path, right.path)
            self.assertEqual(len(left.model.calls), 1)
            self.assertEqual(len(right.model.calls), 1)

    def test_compose_assigns_fifty_separate_models_to_eight_gpus(self):
        import yaml
        from sistema.scripts.gen_compose import generate, parse_args
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            snapshot = root / "snapshot-revision"
            snapshot.mkdir()
            output, config = root / "compose.yml", root / "config.yml"
            args = parse_args(["--nodes", "50", "--malicious", ".8", "--rounds", "50",
                               "--inference-mode", "model", "--model-run-id", "scenario-1",
                               "--model-cache-root", "sistema/results/scenario-1/node-models",
                               "--model-snapshot", str(snapshot), "--gpu-count", "8", "--models-per-gpu", "8",
                               "--compose-out", str(output), "--config-out", str(config)])
            generate(args)
            services = yaml.safe_load(output.read_text(encoding="utf-8"))["services"]
            self.assertEqual(len(services), 51)
            cache_dirs = set()
            for index in range(50):
                node = services[f"node-{index}"]
                env = node["environment"]
                self.assertEqual(env["INFERENCE_MODE"], "model")
                self.assertEqual(env["MODEL_QUANTIZATION"], "nf4")
                self.assertEqual(env["MODEL_NAME"], "/models")
                self.assertEqual(node["command"][-2:], ["--workers", "1"])
                device = node["deploy"]["resources"]["reservations"]["devices"][0]
                self.assertEqual(device["device_ids"], [str(index % 8)])
                self.assertEqual(node["volumes"][-1]["read_only"], True)
                self.assertNotIn("GATEWAY_URL", env)
                cache_dirs.add(env["MODEL_CACHE_DIR"])
            self.assertEqual(len(cache_dirs), 50)
            self.assertNotIn("deploy", services["orchestrator"])
            args.models_per_gpu = 6
            with self.assertRaisesRegex(ValueError, "capacidade"):
                generate(args)


HAS_NODE_DEPS = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx"))


@unittest.skipUnless(HAS_NODE_DEPS, "Requires optional node HTTP dependencies")
class DedicatedNodeTest(unittest.TestCase):
    def test_startup_eagerly_loads_one_private_instance(self):
        from sistema.node import app
        with tempfile.TemporaryDirectory() as temp:
            backend = DedicatedModel(node_id="node-1", run_id="s1", model_name="/models", cache_dir=temp,
                                     factory=FakeModel)
            async def start():
                async with app.app.router.lifespan_context(app.app):
                    return await app.health()
            with mock.patch.dict(os.environ, {"MODEL_RUN_ID": "s1", "MODEL_QUANTIZATION": "nf4"}), \
                 mock.patch.object(app, "INFERENCE_MODE", "model"), \
                 mock.patch.object(app, "_get_dedicated_backend", return_value=backend), \
                 mock.patch.object(app, "_dedicated_backend", backend):
                status = asyncio.run(start())
            self.assertTrue(status["model_loaded"])
            self.assertEqual(status["model_instances"], 1)

    def test_malicious_node_calls_own_model_before_shared_attack(self):
        from sistema.node import app
        from sistema.core.protocol import ProtocolConfig
        from sistema.core.behavior import corrupt_relative
        import random
        backend = mock.Mock()
        backend.generate.return_value = {"answer": 100, "text": "#### 100", "latency_ms": 5}
        response = mock.Mock()
        response.json.return_value = {"answer": 18, "node_id": "node-0", "run_id": "s1"}
        client = mock.Mock()
        client.post = mock.AsyncMock(return_value=response)
        request = app.InferRequest(task_id="t", question="q", round_index=8)
        with mock.patch.dict(os.environ, {"MODEL_RUN_ID": "s1", "EXPERIMENT_SEED": "0", "NOISE_MODE": "relative"}), \
             mock.patch.object(app, "_get_dedicated_backend", return_value=backend), \
             mock.patch.object(app, "NODE_ID", "node-1"), mock.patch.object(app, "PROFILE", "malicious"), \
             mock.patch.object(app, "COLLUDERS", {"node-0", "node-1"}), \
             mock.patch.object(app, "_protocol", ProtocolConfig(malicious_strategy="always")), \
             mock.patch.object(app, "_http", return_value=client):
            result = asyncio.run(app._dedicated_inference(request))
        backend.generate.assert_called_once()
        self.assertEqual(result, (corrupt_relative(18, random.Random("0:8:noise"), .2), 5))
        backend.record_response.assert_called_once_with(8, result[0], "node-0")
        self.assertEqual(client.post.call_args.args[0], "http://node-0:8000/model_answer")

    def test_honest_node_consults_only_own_model(self):
        from sistema.node import app
        backend = mock.Mock()
        backend.generate.return_value = {"answer": 100, "text": "#### 100", "latency_ms": 5}
        client = mock.Mock()
        client.post = mock.AsyncMock()
        with mock.patch.object(app, "_get_dedicated_backend", return_value=backend), \
             mock.patch.object(app, "PROFILE", "honest"), mock.patch.object(app, "_http", return_value=client):
            result = asyncio.run(app._dedicated_inference(app.InferRequest(task_id="t", question="q", round_index=2)))
        self.assertEqual(result, (100, 5))
        client.post.assert_not_called()
        backend.generate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
