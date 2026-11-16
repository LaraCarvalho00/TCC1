"""Validação do banco GSM8K e dos caches SQLite da grade Qwen (sem inferência)."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sistema.aplicacao.validacao_dataset_qwen import (
    EXPECTED_MODEL,
    DEFAULT_GRADE,
    load_task_bank,
    stored_matches_parser,
    validate_qwen_grade,
    validate_scenario_sqlite,
    validate_task_bank,
)
from sistema.core.answer import extract_final_answer


class TaskBankValidationTest(unittest.TestCase):
    def test_banco_smol_structure(self):
        bank = Path(__file__).resolve().parents[1] / "dados" / "banco_smol.json"
        self.assertTrue(bank.is_file(), "banco_smol.json ausente no repositório")
        report = validate_task_bank(bank)
        self.assertTrue(report.ok, [f"{i.code}: {i.message}" for i in report.issues])
        self.assertGreaterEqual(report.metrics["tasks"], 50)

    def test_parser_matches_production_rules(self):
        self.assertEqual(extract_final_answer("step #### 42"), 42)
        self.assertEqual(extract_final_answer("only 9 and 10"), 10)
        self.assertTrue(stored_matches_parser("#### 18\n", 18))
        self.assertFalse(stored_matches_parser("#### 18\n", 19))


class SyntheticSqliteValidationTest(unittest.TestCase):
    def _seed_db(self, path: Path) -> None:
        config = {
            "model": EXPECTED_MODEL,
            "tasks_sha256": "deadbeef",
            "temperature": 0.7,
            "top_p": 0.95,
            "workers": 5,
        }
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE meta (id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL)")
        db.execute(
            "CREATE TABLE generations (seed INTEGER PRIMARY KEY, question_hash TEXT NOT NULL, "
            "answer TEXT NOT NULL, text TEXT NOT NULL, latency_ms INTEGER NOT NULL)"
        )
        db.execute(
            "CREATE TABLE gateway_requests (round_index INTEGER NOT NULL, node_id TEXT NOT NULL, "
            "task_id TEXT NOT NULL, profile TEXT NOT NULL, seed INTEGER NOT NULL UNIQUE, "
            "question_hash TEXT NOT NULL, PRIMARY KEY (round_index, node_id))"
        )
        db.execute("INSERT INTO meta VALUES (1, ?)", (json.dumps(config),))
        db.commit()
        db.close()

    def test_detects_parser_drift(self):
        bank = Path(__file__).resolve().parents[1] / "dados" / "banco_smol.json"
        by_id, hashes, digest = load_task_bank(bank)
        tid = next(iter(by_id))
        qh = hashes[tid]

        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as handle:
            db_path = Path(handle.name)
        try:
            self._seed_db(db_path)
            db = sqlite3.connect(db_path)
            try:
                db.execute(
                    "INSERT INTO gateway_requests VALUES (0, 'node-0', ?, 'honest', 1, ?)",
                    (tid, qh),
                )
                db.execute(
                    "INSERT INTO generations VALUES (1, ?, ?, ?, 10)",
                    (qh, json.dumps(999), "Reasoning #### 18 but stored wrong"),
                )
                db.commit()
            finally:
                db.close()

            report = validate_scenario_sqlite(
                db_path, by_id=by_id, hashes=hashes, expected_requests=1, bank_sha256=digest
            )
            self.assertFalse(report.ok)
            codes = {i.code for i in report.issues}
            self.assertIn("parser_drift", codes)
        finally:
            db_path.unlink(missing_ok=True)


@unittest.skipUnless(
    (Path(__file__).resolve().parents[2] / DEFAULT_GRADE).is_dir(),
    "grade Qwen local não presente nesta máquina",
)
class LiveQwenGradeValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2] / DEFAULT_GRADE
        cls.report = validate_qwen_grade(cls.root)

    def test_grade_integrity_no_errors(self):
        errors = [i for i in self.report.issues if i.level == "error"]
        self.assertEqual(errors, [], [f"{e.code}: {e.message}" for e in errors])

    def test_complete_scenarios_have_2500_joined_rows(self):
        for sc in self.report.metrics.get("scenarios_validated") or []:
            if sc.get("manifest_status") == "concluido":
                self.assertEqual(sc.get("gateway_requests"), 2500)
                self.assertEqual(sc.get("joined"), 2500)
                self.assertEqual(sc.get("parser_mismatch"), 0)

    def test_exact_scenario_accuracy_snapshot(self):
        exact = next(
            (s for s in self.report.metrics["scenarios_validated"] if s["scenario_id"].endswith("exact-s0")),
            None,
        )
        self.assertIsNotNone(exact)
        self.assertEqual(exact["raw_correct"], 914)
        self.assertAlmostEqual(exact["raw_accuracy"], 0.3656, places=4)