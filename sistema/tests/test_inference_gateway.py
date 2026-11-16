import json
import io
import sqlite3
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sistema.node import inference_gateway as gateway
from sistema.node.inference_gateway import Dispatcher, RequestError, handler_for


class FakePool:
    def __init__(self, path, workers=2):
        self.workers = workers
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS generations (seed INTEGER PRIMARY KEY, answer INTEGER)")
        self.calls = []
        self.batch_sizes = []

    def batch_sample(self, jobs, temperature, top_p):
        self.batch_sizes.append(len(jobs))
        result = []
        for question, seed in jobs:
            row = self.db.execute("SELECT answer FROM generations WHERE seed=?", (seed,)).fetchone()
            if row is None:
                self.calls.append(seed)
                self.db.execute("INSERT INTO generations VALUES (?,?)", (seed, 18))
                self.db.commit()
            result.append((18, "#### 18", 10))
        return result

    def close(self):
        self.db.close()


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "cache.sqlite")
        self.instances = []
        def factory():
            p = FakePool(self.db)
            self.instances.append(p)
            return p
        self.factory = factory
        self.dispatcher = Dispatcher(factory, "run-1", {"t1": "Pergunta?"}, 0.7, 0.95)
        self.value = {"run_id": "run-1", "node_id": "node-1", "round_index": 0,
                      "task_id": "t1", "question": "Pergunta?", "profile": "honest", "seed": 10}

    def tearDown(self):
        self.dispatcher.close()
        self.temp.cleanup()

    def test_duplicate_is_idempotent_and_recovers_after_restart(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.dispatcher.submit, self.value) for _ in range(2)]
            self.assertEqual([f.result()["answer"] for f in futures], [18, 18])
        self.assertEqual(self.instances[0].calls, [10])
        self.dispatcher.close()
        self.dispatcher = Dispatcher(self.factory, "run-1", {"t1": "Pergunta?"}, 0.7, 0.95)
        self.assertEqual(self.dispatcher.submit(self.value)["answer"], 18)
        self.assertEqual(self.instances[1].calls, [])

    def test_rejects_conflicting_node_and_seed(self):
        self.dispatcher.submit(self.value)
        with self.assertRaises(RequestError):
            self.dispatcher.submit(dict(self.value, seed=11))
        with self.assertRaises(RequestError):
            self.dispatcher.submit(dict(self.value, node_id="node-2"))
        with self.assertRaises(RequestError):
            self.dispatcher.submit(dict(self.value, run_id="other"))

    def test_http_inference(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.dispatcher))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/health") as response:
                self.assertEqual(json.load(response), {"status": "ready", "run_id": "run-1",
                                                       "workers": 2, "model_instances": 2})
            url = f"http://127.0.0.1:{server.server_port}/inference"
            request = Request(url, json.dumps(self.value).encode("utf-8"), {"Content-Type": "application/json"})
            with urlopen(request) as response:
                self.assertEqual(json.load(response)["answer"], 18)
            request = Request(url, json.dumps(dict(self.value, question="Diferente")).encode("utf-8"))
            with self.assertRaises(HTTPError) as err:
                urlopen(request)
            self.assertEqual(err.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_five_workers_dispatch_fifty_node_requests_without_sharing_generations(self):
        instances = []
        def factory():
            pool = FakePool(str(Path(self.temp.name) / "five.sqlite"), workers=5)
            instances.append(pool)
            return pool
        dispatcher = Dispatcher(factory, "run-1", {"t1": "Pergunta?"}, .7, .95, workers=5)
        try:
            self.assertEqual(dispatcher.model_instances, 5)
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(dispatcher))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/health") as response:
                    health = json.load(response)
                self.assertEqual(health["workers"], 5)
                self.assertEqual(health["model_instances"], 5)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
            barrier = threading.Barrier(51)
            def send(index):
                barrier.wait(timeout=10)
                return dispatcher.submit(dict(self.value, node_id=f"node-{index}", seed=100 + index))
            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = [executor.submit(send, index) for index in range(50)]
                barrier.wait(timeout=10)
                self.assertEqual([future.result(timeout=10)["answer"] for future in futures], [18] * 50)
            self.assertEqual(sorted(instances[0].calls), list(range(100, 150)))
            self.assertEqual(max(instances[0].batch_sizes), 5)
            self.assertEqual(sum(instances[0].batch_sizes), 50)
            dispatcher.submit(dict(self.value, node_id="node-0", seed=100))
            self.assertEqual(len(instances[0].calls), 50)
            with closing(sqlite3.connect(Path(self.temp.name) / "five.sqlite")) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM gateway_requests").fetchone()[0], 50)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM generations").fetchone()[0], 50)
        finally:
            dispatcher.close()
        self.assertEqual(dispatcher.model_instances, 0)
        self.assertFalse(dispatcher.thread.is_alive())

    def test_invalid_worker_counts_are_rejected_before_starting_dispatcher(self):
        factory = mock.Mock()
        for workers in (0, 6, True, False):
            with self.subTest(workers=workers), self.assertRaises(ValueError):
                Dispatcher(factory, "run", {}, .7, .95, workers=workers)
        factory.assert_not_called()

    def test_worker_failure_stops_pool_and_rejects_queued_and_future_requests(self):
        closed = threading.Event()
        class FailingPool(FakePool):
            def batch_sample(self, *_args):
                raise RuntimeError("worker failed")
            def close(self):
                super().close()
                closed.set()
        dispatcher = Dispatcher(lambda: FailingPool(str(Path(self.temp.name) / "failed.sqlite"), workers=5),
                                "run-1", {"t1": "Pergunta?"}, .7, .95, workers=5)
        try:
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(dispatcher.submit,
                           dict(self.value, node_id=f"node-{index}", seed=100 + index)) for index in range(10)]
                for future in futures:
                    with self.assertRaises(RuntimeError):
                        future.result(timeout=5)
            dispatcher.thread.join(timeout=3)
            self.assertFalse(dispatcher.thread.is_alive())
            self.assertTrue(closed.is_set())
            self.assertEqual(dispatcher.model_instances, 0)
            with self.assertRaises(RuntimeError):
                dispatcher.submit(dict(self.value, seed=999))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(dispatcher))
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                with self.assertRaises(HTTPError) as error:
                    urlopen(f"http://127.0.0.1:{server.server_port}/health")
                self.assertEqual(error.exception.code, 503)
                self.assertEqual(json.load(error.exception)["status"], "error")
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
        finally:
            dispatcher.close()

    def test_shutdown_requires_token(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.dispatcher, "secret"))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/shutdown"
            with self.assertRaises(HTTPError) as err:
                urlopen(Request(url, b""))
            self.assertEqual(err.exception.code, 403)
            request = Request(url, b"", {"Authorization": "Bearer secret"})
            with urlopen(request) as response:
                self.assertEqual(json.load(response)["status"], "stopping")
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
        finally:
            if thread.is_alive():
                server.shutdown()
            server.server_close()
            thread.join()


class GatewayConfigurationTests(unittest.TestCase):
    def test_manual_snapshot_uses_existing_revision_without_hub_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary) / ("a" * 40)
            snapshot.mkdir()
            download = mock.Mock(side_effect=AssertionError("Hub must not be called"))
            with mock.patch.dict(sys.modules, {"huggingface_hub": SimpleNamespace(snapshot_download=download)}):
                self.assertEqual(gateway.resolve_model_snapshot("Qwen/Qwen3-0.6B", str(snapshot), snapshot.name),
                                 (str(snapshot.resolve()), snapshot.name))
                with self.assertRaisesRegex(ValueError, "revisão"):
                    gateway.resolve_model_snapshot("model", str(snapshot), "b" * 40)
                with self.assertRaisesRegex(ValueError, "não existe"):
                    gateway.resolve_model_snapshot("model", str(snapshot / "missing"))
            download.assert_not_called()

    def test_hub_fallback_is_local_only_and_accepts_a_revision(self):
        download = mock.Mock(return_value="cache/snapshots/revision")
        with mock.patch.dict(sys.modules, {"huggingface_hub": SimpleNamespace(snapshot_download=download)}):
            self.assertEqual(gateway.resolve_model_snapshot("model", revision="revision"),
                             ("cache/snapshots/revision", "revision"))
        download.assert_called_once_with("model", local_files_only=True, revision="revision")

    def test_cli_rejects_invalid_workers_before_reading_tasks_or_loading_model(self):
        for workers in ("0", "6", "true"):
            with self.subTest(workers=workers), \
                 mock.patch.object(gateway, "resolve_model_snapshot") as snapshot, \
                 mock.patch.object(gateway.Path, "read_bytes") as read, \
                 mock.patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as error:
                    gateway.main(["--tasks", "missing", "--run-id", "test", "--cache", "missing",
                                  "--workers", workers])
                self.assertEqual(error.exception.code, 2)
                snapshot.assert_not_called()
                read.assert_not_called()

    def test_cli_propagates_worker_count_and_keeps_two_as_default(self):
        for explicit_workers in (None, 5):
            with self.subTest(workers=explicit_workers), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                tasks = directory / "tasks.json"
                tasks.write_text(json.dumps({"tarefas": [{"id": "t1", "question": "Pergunta?"}]}), encoding="utf-8")
                snapshot = directory / ("a" * 40)
                snapshot.mkdir()
                argv = ["--model", "Qwen/Qwen3-0.6B", "--model-snapshot", str(snapshot),
                        "--model-revision", snapshot.name, "--tasks", str(tasks),
                        "--run-id", "run", "--cache", str(directory / "cache.sqlite")]
                if explicit_workers:
                    argv.extend(["--workers", str(explicit_workers)])
                def make_dispatcher(factory, *_args, **_kwargs):
                    factory()
                    return mock.Mock()
                with mock.patch.object(gateway, "InferencePool") as pool, \
                     mock.patch.object(gateway, "Dispatcher", side_effect=make_dispatcher) as dispatcher, \
                     mock.patch.object(gateway, "ThreadingHTTPServer") as server, \
                     mock.patch.object(gateway, "version", return_value="test"):
                    gateway.main(argv)
                workers = explicit_workers or 2
                self.assertEqual(pool.call_args.args[4], workers)
                self.assertEqual(pool.call_args.args[6]["workers"], workers)
                self.assertEqual(pool.call_args.args[2], snapshot.name)
                self.assertEqual(dispatcher.call_args.kwargs["workers"], workers)
                server.return_value.server_close.assert_called_once()

    def test_server_bind_failure_still_closes_the_started_dispatcher(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            tasks = directory / "tasks.json"
            tasks.write_text(json.dumps({"tarefas": [{"id": "t1", "question": "Pergunta?"}]}), encoding="utf-8")
            snapshot = directory / ("a" * 40)
            snapshot.mkdir()
            argv = ["--tasks", str(tasks), "--run-id", "run", "--cache", str(directory / "cache.sqlite"),
                    "--model-snapshot", str(snapshot), "--workers", "5"]
            with mock.patch.object(gateway, "Dispatcher") as dispatcher, \
                 mock.patch.object(gateway, "ThreadingHTTPServer", side_effect=OSError("port occupied")), \
                 mock.patch.object(gateway, "version", return_value="test"):
                with self.assertRaisesRegex(OSError, "port occupied"):
                    gateway.main(argv)
            dispatcher.return_value.close.assert_called_once()

if __name__ == "__main__":
    unittest.main()
