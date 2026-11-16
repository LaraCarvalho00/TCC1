"""Integrity checks for the local timing pilot without model, GPU or HTTP."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from sistema.scripts import piloto_local as pilot


class PilotIntegrityTest(unittest.TestCase):
    def test_aggregate_uses_concurrent_wall_not_sum_of_model_latencies(self):
        rows = [{"model_s": value, "correct": int(index < 2)}
                for index, value in enumerate((2, 3, 4, 5))]
        pairs = [{"wall_s": 3}, {"wall_s": 5}]
        result = pilot.aggregate(rows, pairs, total_s=15, load_s=6)
        self.assertEqual(result["generations"], 4)
        self.assertEqual(result["generation_wall_s"], 8)
        self.assertEqual(result["wall_seconds_per_generation"], 2)
        self.assertEqual(result["end_to_end_s"], 15)
        self.assertEqual(result["load_s"], 6)
        self.assertEqual(result["median_model_s"], 3.5)
        self.assertEqual(result["accuracy_descriptive"], .5)
        self.assertAlmostEqual(result["projection_same_local_gpu_40000_h"], 80000 / 3600)
        self.assertAlmostEqual(result["projection_eight_gpus_equal_local_throughput_40000_h"], 10000 / 3600)

    def test_aggregate_rejects_an_empty_or_unstarted_pilot(self):
        for rows, pairs in (([], []), ([{"model_s": 1}], [])):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                pilot.aggregate(rows, pairs, total_s=1, load_s=0)

    def fixture(self, root):
        nodes = [{"node_id": "node-0"}, {"node_id": "node-1"}]
        for node in nodes:
            directory = root / node["node_id"]
            directory.mkdir()
            with closing(sqlite3.connect(directory / "inferencias.sqlite")) as db:
                db.execute("CREATE TABLE generations (round_index INTEGER, node_id TEXT)")
                db.execute("CREATE TABLE responses (round_index INTEGER)")
                db.executemany("INSERT INTO generations VALUES (?,?)", [(index, node["node_id"]) for index in range(3)])
                db.executemany("INSERT INTO responses VALUES (?)", [(index,) for index in range(3)])
                db.commit()
        return nodes

    def test_verify_requires_every_generation_and_submission_from_each_node(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nodes = self.fixture(root)
            result = pilot.verify(root, nodes, 3)
            self.assertEqual(result, [{"node_id": item["node_id"], "generations": 3, "responses": 3} for item in nodes])
            with closing(sqlite3.connect(root / "node-1" / "inferencias.sqlite")) as db:
                db.execute("DELETE FROM responses WHERE round_index=2")
                db.commit()
            with self.assertRaisesRegex(RuntimeError, "node-1"):
                pilot.verify(root, nodes, 3)

    def test_verify_rejects_duplicated_rounds_or_wrong_node_identity(self):
        for sql in ("UPDATE generations SET round_index=0 WHERE round_index=1",
                    "UPDATE generations SET node_id='node-0' WHERE round_index=1"):
            with self.subTest(sql=sql), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                nodes = self.fixture(root)
                with closing(sqlite3.connect(root / "node-1" / "inferencias.sqlite")) as db:
                    db.execute(sql)
                    db.commit()
                with self.assertRaisesRegex(RuntimeError, "node-1"):
                    pilot.verify(root, nodes, 3)

    def test_existing_output_is_rejected_before_model_or_gpu_access(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            output = root / "resultados" / "llm" / "old-run"
            output.mkdir(parents=True)
            sentinel = output / "manifesto.json"
            sentinel.write_text(json.dumps({"status": "concluido"}), encoding="utf-8")
            with mock.patch.object(pilot, "ROOT", root), mock.patch.object(pilot, "gpu") as gpu:
                with self.assertRaises(FileExistsError):
                    pilot.run(output)
            gpu.assert_not_called()
            self.assertEqual(json.loads(sentinel.read_text(encoding="utf-8")), {"status": "concluido"})

    def test_infer_checks_response_identity_and_does_not_send_answer_key(self):
        node = {"node_id": "node-1", "url": "http://127.0.0.1:12345"}
        task = {"id": "q0", "question": "1+1?", "answer": 2}
        with mock.patch.object(pilot, "request", return_value={"node_id": "node-1", "task_id": "q0", "latency_ms": 123, "answer": 2}) as request:
            row = pilot.infer(node, task, 4)
        self.assertEqual(row["model_s"], .123)
        self.assertEqual(row["correct"], 1)
        self.assertEqual(request.call_args.args[1], {"task_id": "q0", "question": "1+1?", "round_index": 4})
        with mock.patch.object(pilot, "request", return_value={"node_id": "node-0", "task_id": "q0"}):
            with self.assertRaisesRegex(ValueError, "Identidade"):
                pilot.infer(node, task, 4)


if __name__ == "__main__":
    unittest.main()
