"""Model-owning nodes must fail closed on missing answers and failed audits."""
import asyncio
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HAS_DEPS = all(importlib.util.find_spec(name) for name in ("httpx", "yaml"))


@unittest.skipUnless(HAS_DEPS, "Requires orchestrator HTTP dependencies")
class DedicatedOrchestratorTest(unittest.TestCase):
    def config(self, output, mode):
        return {"nodes": [{"id": f"node-{i}", "url": f"http://node-{i}", "profile": "honest"} for i in range(6)],
                "inference_mode": mode, "mode": "real", "rounds": 2, "seed": 0,
                "output_dir": output, "signal": "consensus", "audit_mode": "random", "audit_p": 1,
                "honest_rounds": 0}

    def test_missing_node_states_abort_both_real_layouts(self):
        from sistema.orchestrator import run
        for mode in ("model", "gateway"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp, \
                 mock.patch.object(run, "wait_for_nodes", new=mock.AsyncMock()), \
                 mock.patch.object(run, "load_tasks", return_value=[{"id": "t", "question": "q", "answer": 1}]), \
                 mock.patch.object(run, "_get", new=mock.AsyncMock(return_value=None)):
                with self.assertRaisesRegex(RuntimeError, "estado de todos os nós"):
                    asyncio.run(run.run_dynamic_experiment(self.config(temp, mode)))

    def test_missing_node_response_aborts_dedicated_round(self):
        from sistema.orchestrator import run
        async def get(_client, url, *_args, **_kwargs):
            if url.endswith("/state"):
                return {"head": "genesis", "consensus": {}, "chain_length": 0}
            return {"received": False}
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.object(run, "wait_for_nodes", new=mock.AsyncMock()), \
             mock.patch.object(run, "load_tasks", return_value=[{"id": "t", "question": "q", "answer": 1}]), \
             mock.patch.object(run, "_get", new=mock.AsyncMock(side_effect=get)), \
             mock.patch.object(run, "_lead_group", new=mock.AsyncMock(return_value=None)):
            with self.assertRaisesRegex(RuntimeError, "Rodada incompleta"):
                asyncio.run(run.run_dynamic_experiment(self.config(temp, "model")))

    def test_dedicated_round_requires_applied_audit_for_every_node(self):
        from sistema.orchestrator import run
        async def get(_client, url, *_args, **_kwargs):
            if url.endswith("/state"):
                return {"head": "genesis", "consensus": {}, "chain_length": 0}
            return {"received": True, "answer": 1, "latency_ms": 1}
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.object(run, "wait_for_nodes", new=mock.AsyncMock()), \
             mock.patch.object(run, "load_tasks", return_value=[{"id": "t", "question": "q", "answer": 1}]), \
             mock.patch.object(run, "_get", new=mock.AsyncMock(side_effect=get)), \
             mock.patch.object(run, "_lead_group", new=mock.AsyncMock(return_value=mock.Mock(refusers=[]))), \
             mock.patch.object(run, "_judge", new=mock.AsyncMock(side_effect=RuntimeError("audit not applied"))) as judge:
            with self.assertRaisesRegex(RuntimeError, "audit not applied"):
                asyncio.run(run.run_dynamic_experiment(self.config(temp, "model")))
        self.assertIs(judge.call_args.kwargs["require_applied"], True)
