"""Integrity checks for the capacity benchmark without GPU, models or HTTP."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from sistema.scripts import piloto_capacidade as pilot


class CapacityPilotIntegrityTest(unittest.TestCase):
    def sample(self, **changes):
        return {"gpu_total_mib": 8192, "gpu_used_mib": 2048,
                "ram_free_mib": 4096, "page_free_mib": 8192, **changes}

    def test_admission_preserves_gpu_reserve_after_the_next_model_load(self):
        # The existing reserve is intact, but the next model would consume it.
        reason, details = pilot.admission(
            self.sample(gpu_used_mib=6250), 1536, 768, 768, 384)
        self.assertEqual(reason, "reserva_vram")
        self.assertEqual(details["free_gpu_mib"], 1942)
        self.assertEqual(details["next_gpu_estimate_mib"], 1536)

    def test_admission_preserves_ram_reserve_after_the_next_process_load(self):
        reason, details = pilot.admission(
            self.sample(ram_free_mib=1000), 1536, 768, 768, 384)
        self.assertEqual(reason, "reserva_ram")
        self.assertEqual(details["next_ram_estimate_mib"], 384)
        self.assertEqual(details["ram_free_mib"], 1000)

    def test_admission_accepts_the_exact_combined_reserve_boundary(self):
        self.assertEqual(pilot.admission(
            self.sample(gpu_used_mib=8192 - 1536 - 768,
                        ram_free_mib=768 + 384),
            1536, 768, 768, 384), (None, {}))

    def test_admission_rejects_low_available_committed_memory(self):
        reason, details = pilot.admission(
            self.sample(page_free_mib=2047), 1536, 768, 768, 384)
        self.assertEqual(reason, "reserva_memoria_comprometida")
        self.assertEqual(details["page_free_mib"], 2047)

    def test_summary_counts_generations_using_concurrent_batch_wall_time(self):
        rows = [{"client_wall_s": seconds, "answer": answer, "correct": correct}
                for seconds, answer, correct in
                ((2, 1, 1), (3, 2, 0), (4, None, 0), (5, 3, 1))]
        summary = pilot.stage_summary(rows, [{"wall_s": 3}, {"wall_s": 5}])
        self.assertEqual(summary["generations"], 4)
        self.assertEqual(summary["questions_per_node"], 2)
        self.assertEqual(summary["generation_wall_s"], 8)
        self.assertEqual(summary["wall_seconds_per_generation"], 2)
        self.assertEqual(summary["generations_per_hour"], 1800)
        self.assertEqual(summary["median_request_s"], 3.5)
        self.assertEqual(summary["max_request_s"], 5)
        self.assertEqual(summary["parsed_answers"], 3)
        self.assertEqual(summary["correct_answers"], 2)
        self.assertEqual(summary["accuracy_descriptive"], .5)

    def test_summary_rejects_an_unstarted_or_empty_stage(self):
        for rows, batches in (([], []), ([{}], []), ([], [{"wall_s": 1}])):
            with self.subTest(rows=rows, batches=batches), self.assertRaises(ValueError):
                pilot.stage_summary(rows, batches)

    def fixture(self, root):
        # Node 1 joins later and must not be required to own node 0's old rounds.
        expected = {"node-0": [0, 1, 2, 3], "node-1": [2, 3]}
        nodes = [{"node_id": identifier} for identifier in expected]
        for identifier, rounds in expected.items():
            directory = root / identifier
            directory.mkdir()
            with closing(sqlite3.connect(directory / "inferencias.sqlite")) as db:
                db.execute("CREATE TABLE generations (round_index INTEGER, node_id TEXT)")
                db.execute("CREATE TABLE responses (round_index INTEGER)")
                db.executemany("INSERT INTO generations VALUES (?,?)",
                               [(index, identifier) for index in rounds])
                db.executemany("INSERT INTO responses VALUES (?)", [(index,) for index in rounds])
                db.commit()
        return nodes, expected

    def test_verify_supports_distinct_round_histories_for_later_joining_nodes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nodes, expected = self.fixture(root)
            self.assertEqual(pilot.verify_rounds(root, nodes, expected), [
                {"node_id": "node-0", "generations": 4, "responses": 4},
                {"node_id": "node-1", "generations": 2, "responses": 2},
            ])

    def test_verify_rejects_duplicate_missing_extra_or_wrong_identity_rows(self):
        changes = (
            "UPDATE generations SET round_index=2 WHERE round_index=3",
            "UPDATE generations SET node_id='node-0' WHERE round_index=3",
            "DELETE FROM generations WHERE round_index=3",
            "DELETE FROM responses WHERE round_index=3",
            "INSERT INTO generations VALUES (4,'node-1')",
            "INSERT INTO responses VALUES (4)",
        )
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                nodes, expected = self.fixture(root)
                with closing(sqlite3.connect(root / "node-1/inferencias.sqlite")) as db:
                    db.execute(change)
                    db.commit()
                with self.assertRaisesRegex(RuntimeError, "node-1"):
                    pilot.verify_rounds(root, nodes, expected)

    def test_existing_output_is_preserved_before_download_or_gpu_access(self):
        for cached in (False, True):
            with self.subTest(cached=cached), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                output = root / "resultados/llm/existing"
                output.mkdir(parents=True)
                original = json.dumps({"status": "concluido", "max_validated_nodes": 4})
                sentinel = output / "manifesto.json"
                sentinel.write_text(original, encoding="utf-8")
                (output / "modelo.json").write_text("{}", encoding="utf-8")
                args = SimpleNamespace(saida=output, executar_cache=cached)
                with mock.patch.object(pilot, "ROOT", root), \
                     mock.patch.object(pilot, "snapshot") as snapshot, \
                     mock.patch.object(pilot, "telemetry") as telemetry:
                    with self.assertRaises(FileExistsError):
                        pilot.run(args)
                snapshot.assert_not_called()
                telemetry.assert_not_called()
                self.assertEqual(sentinel.read_text(encoding="utf-8"), original)

    def test_output_outside_results_is_rejected_before_download_or_gpu_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output = root / "unrelated"
            with mock.patch.object(pilot, "ROOT", root), \
                 mock.patch.object(pilot, "snapshot") as snapshot, \
                 mock.patch.object(pilot, "telemetry") as telemetry:
                with self.assertRaises(ValueError):
                    pilot.run(SimpleNamespace(saida=output))
            snapshot.assert_not_called()
            telemetry.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
