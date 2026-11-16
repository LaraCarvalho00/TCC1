import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sistema.node.inference_pool import InferencePool


class FakeConnection:
    calls = []
    fail_on = None

    def __init__(self):
        self.msg = {"ready": True}
        self.closed = False

    def send(self, job):
        if job is None:
            return
        self.calls.append(job["seed"])
        if job["seed"] == self.fail_on:
            self.msg = {"error": "falha simulada"}
        else:
            self.msg = {"seed": job["seed"], "answer": job["seed"], "text": "saída", "latency_ms": 10}

    def recv(self):
        return self.msg

    def poll(self, _timeout):
        return True

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self): self.joined = False
    def start(self): pass
    def join(self, _timeout): self.joined = True
    def is_alive(self): return False


class FakeContext:
    def __init__(self, fail_on_load=None):
        self.connections, self.processes = [], []
        self.fail_on_load = fail_on_load

    def Pipe(self):
        parent, child = FakeConnection(), FakeConnection()
        self.connections.append(parent)
        if len(self.connections) == self.fail_on_load:
            parent.msg = {"error": "falha ao carregar"}
        return parent, child

    def Process(self, **kwargs):
        process = FakeProcess()
        self.processes.append(process)
        return process


class PoolTests(unittest.TestCase):
    def setUp(self):
        FakeConnection.calls = []
        FakeConnection.fail_on = None
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "cache.sqlite")
        self.context = patch("sistema.node.inference_pool.mp.get_context", return_value=FakeContext())
        self.wait = patch("sistema.node.inference_pool.wait", side_effect=lambda connections, timeout: [connections[0]])
        self.context.start()
        self.wait.start()

    def tearDown(self):
        self.wait.stop()
        self.context.stop()
        self.tmp.cleanup()

    def pool(self, config=None, workers=2):
        return InferencePool("test", "test", "revision", 256, workers, self.path, config or {"scenario": 1})

    def test_resume_preserves_completed_response_after_failure(self):
        FakeConnection.fail_on = 2
        pool = self.pool()
        with self.assertRaises(RuntimeError):
            pool.batch_sample([("pergunta", 1), ("pergunta", 2)], 0.7, 0.95)
        pool.close()
        FakeConnection.calls = []
        FakeConnection.fail_on = None
        pool = self.pool()
        values = pool.batch_sample([("pergunta", 1), ("pergunta", 2)], 0.7, 0.95)
        pool.close()
        self.assertEqual(values, [(1, "saída", 10), (2, "saída", 10)])
        self.assertEqual(FakeConnection.calls, [2])

    def test_configuration_mismatch_is_rejected(self):
        pool = self.pool()
        pool.close()
        with self.assertRaisesRegex(ValueError, "outra configuração"):
            self.pool({"scenario": 2})

    def test_question_mismatch_is_rejected(self):
        pool = self.pool()
        pool.batch_sample([("original", 1)], 0.7, 0.95)
        with self.assertRaisesRegex(ValueError, "outra questão"):
            pool.batch_sample([("diferente", 1)], 0.7, 0.95)
        pool.close()

    def test_worker_counts_one_through_five_return_all_fifty_new_generations_in_order(self):
        for workers in range(1, 6):
            with self.subTest(workers=workers):
                path = str(Path(self.tmp.name) / f"workers-{workers}.sqlite")
                context = FakeContext()
                active_counts = []
                def ready(connections, timeout):
                    active_counts.append(len(connections))
                    return [connections[-1]]
                with patch("sistema.node.inference_pool.mp.get_context", return_value=context), \
                     patch("sistema.node.inference_pool.wait", side_effect=ready):
                    pool = InferencePool("test", "test", "revision", 256, workers, path, {"scenario": 1})
                    try:
                        jobs = [("pergunta", seed) for seed in range(50)]
                        values = pool.batch_sample(jobs, .7, .95)
                        self.assertEqual(values, [(seed, "saída", 10) for seed in range(50)])
                        self.assertEqual(max(active_counts), workers)
                        self.assertEqual(len(context.processes), workers)
                        self.assertEqual(pool.workers, workers)
                        metadata = json.loads(pool.db.execute("SELECT config FROM meta WHERE id=1").fetchone()[0])
                        self.assertEqual(metadata["workers"], workers)
                        self.assertEqual(pool.db.execute("SELECT COUNT(*) FROM generations").fetchone()[0], 50)
                    finally:
                        pool.close()
                    self.assertTrue(all(process.joined for process in context.processes))
                    self.assertTrue(all(connection.closed for connection in context.connections))

    def test_invalid_workers_are_rejected_before_creating_cache_or_processes(self):
        for workers in (0, 6, -1, True, False, 2.5, "2", None):
            with self.subTest(workers=workers), \
                 patch("sistema.node.inference_pool.mp.get_context") as context:
                with self.assertRaises(ValueError):
                    self.pool(workers=workers)
                context.assert_not_called()
                self.assertFalse(Path(self.path).exists())

    def test_cache_cannot_be_reused_with_another_worker_count(self):
        pool = self.pool(workers=5)
        pool.close()
        with self.assertRaisesRegex(ValueError, "outra configuração"):
            self.pool(workers=2)

    def test_explicit_cache_worker_count_must_match_actual_workers(self):
        for configured in (2, True):
            with self.subTest(configured=configured), self.assertRaises(ValueError):
                self.pool({"scenario": 1, "workers": configured}, workers=5)
        self.assertFalse(Path(self.path).exists())

    def test_failed_fourth_load_cleans_every_already_started_worker_and_pipe(self):
        context = FakeContext(fail_on_load=4)
        with patch("sistema.node.inference_pool.mp.get_context", return_value=context):
            with self.assertRaisesRegex(RuntimeError, "falha ao carregar"):
                self.pool(workers=5)
        self.assertEqual(len(context.processes), 4)
        self.assertTrue(all(process.joined for process in context.processes))
        self.assertTrue(all(connection.closed for connection in context.connections))
        # Opening and deleting later is possible because the failed pool closed SQLite.
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM generations").fetchone()[0], 0)

    def test_cleanup_kills_every_worker_that_ignores_termination(self):
        class StubbornProcess(FakeProcess):
            def __init__(self, fail_join=False):
                self.alive, self.fail_join = True, fail_join
            def join(self, _timeout):
                if self.fail_join:
                    self.fail_join = False
                    raise OSError("join failed")
            def is_alive(self): return self.alive
            def terminate(self): pass
            def kill(self): self.alive = False
        pool = self.pool(workers=5)
        processes = [StubbornProcess(fail_join=index == 0) for index in range(5)]
        pool.processes = processes
        pool.close()
        self.assertTrue(all(not process.is_alive() for process in processes))
        self.assertIsNone(pool.db)
        self.assertTrue(pool.cleanup_errors)
        pool.close()  # Cleanup remains safe when requested again.
