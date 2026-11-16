"""Valida entrada local e progresso incremental sem executar o modelo real."""
import contextlib
import io
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from execucao import run_llm


class LlmProgressTest(unittest.TestCase):
    def _bank(self, directory):
        path = Path(directory) / "banco.json"
        path.write_text(json.dumps({"tarefas": [
            {"id": "t1", "question": "Questão privada 1", "answer": 2, "amostras": [{"resposta": 900}]},
            {"id": "t2", "question": "Questão privada 2", "answer": 3, "amostras": [{"resposta": 901}]},
        ]}), encoding="utf-8")
        return path

    def test_uses_bank_questions_but_regenerates_every_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            bank = self._bank(directory)
            output = Path(directory) / "relatorio.md"
            progress = Path(directory) / "progresso.jsonl"
            generated = [(2, "texto secreto", 0.1), (4, "texto secreto", 0.2),
                         (2, "texto secreto", 0.3), (7, "texto secreto", 0.4)]
            with patch.object(run_llm, "N_ACCURACY", 2), patch.object(run_llm, "N_QUESTIONS", 1), \
                 patch.object(run_llm, "N_SAMPLES", 2), patch("sistema.core.dataset.load_gsm8k") as load, \
                 patch("sistema.node.inference.ModelBackend", return_value=types.SimpleNamespace(device="cpu")), \
                 patch.object(run_llm, "_generate", side_effect=generated) as generate, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_llm.main(["--saida", str(output), "--banco-tarefas", str(bank), "--progresso", str(progress)]), 0)
            load.assert_not_called()
            self.assertEqual(generate.call_count, 4)
            rows = [json.loads(line) for line in progress.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([r["previsto"] for r in rows], [2, 4, 2, 7])
            self.assertEqual([r["modo"] for r in rows], ["gulosa", "gulosa", "amostragem", "amostragem"])
            self.assertEqual([r["amostra"] for r in rows], [None, None, 1, 2])
            self.assertEqual([r["correto"] for r in rows], [True, False, True, False])
            self.assertEqual([r["id_questao"] for r in rows], ["t1", "t2", "t1", "t1"])
            self.assertNotIn("privada", progress.read_text(encoding="utf-8"))
            self.assertNotIn("texto secreto", progress.read_text(encoding="utf-8"))
            report = output.read_text(encoding="utf-8")
            self.assertIn("As respostas pré-geradas do banco não foram reutilizadas", report)
            self.assertIn("SHA-256", report)
            self.assertIn("--banco-tarefas", report)
            self.assertIn(str(bank), report)
            self.assertIn("--progresso", report)
            self.assertIn(str(progress), report)
            self.assertIn("| 1 | 2 |", report)
            self.assertNotIn("| 0 | 2 |", report)
            self.assertEqual([call.kwargs['seed'] for call in generate.call_args_list], [None, None, 0, 1])

    def test_progress_survives_generation_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            bank, output, progress = self._bank(directory), Path(directory) / "out.md", Path(directory) / "p.jsonl"
            with patch.object(run_llm, "N_ACCURACY", 2), patch("sistema.node.inference.ModelBackend", return_value=types.SimpleNamespace(device="cpu")), \
                 patch.object(run_llm, "_generate", side_effect=[(2, "", 0.1), RuntimeError("falha simulada")]), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_llm.main(["--saida", str(output), "--banco-tarefas", str(bank), "--progresso", str(progress)]), 1)
            rows = [json.loads(line) for line in progress.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id_questao"], "t1")
            self.assertIn("falha simulada", output.read_text(encoding="utf-8"))

    def test_invalid_bank_or_overlapping_paths_fail_before_model(self):
        with tempfile.TemporaryDirectory() as directory:
            bank = self._bank(directory)
            with patch.object(run_llm, "N_ACCURACY", 3), patch("sistema.node.inference.ModelBackend") as model, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    run_llm.main(["--saida", str(Path(directory) / "out"), "--banco-tarefas", str(bank)])
                with self.assertRaises(SystemExit):
                    run_llm.main(["--saida", str(bank), "--banco-tarefas", str(bank), "--sobrescrever"])
            model.assert_not_called()
            self.assertIn("tarefas", json.loads(bank.read_text(encoding="utf-8")))

    def test_existing_progress_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            bank, progress = self._bank(directory), Path(directory) / "p.jsonl"
            progress.write_text("dados originais", encoding="utf-8")
            with patch.object(run_llm, "N_ACCURACY", 2), patch("sistema.node.inference.ModelBackend") as model, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    run_llm.main(["--saida", str(Path(directory) / "out"), "--banco-tarefas", str(bank), "--progresso", str(progress), "--sobrescrever"])
            model.assert_not_called()
            self.assertEqual(progress.read_text(encoding="utf-8"), "dados originais")


if __name__ == "__main__":
    unittest.main()
