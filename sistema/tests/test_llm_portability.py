"""Validação das medições portáveis sem carregar o modelo de linguagem."""

import contextlib
import io
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from execucao import run_llm


class LlmMachineMetricsTest(unittest.TestCase):
    def test_rss_converts_linux_kib_and_macos_bytes(self):
        fake_resource = types.SimpleNamespace(
            RUSAGE_SELF=0,
            getrusage=lambda _: types.SimpleNamespace(ru_maxrss=1024 ** 2),
        )
        with patch.object(run_llm, "resource", fake_resource):
            with patch.object(run_llm.sys, "platform", "linux"):
                self.assertEqual(run_llm._rss_gb(), 1.0)
            with patch.object(run_llm.sys, "platform", "darwin"):
                self.assertEqual(run_llm._rss_gb(), 1 / 1024)

    def test_rss_windows_uses_peak_working_set(self):
        with patch.object(run_llm.sys, "platform", "win32"), patch.object(
            run_llm, "_windows_peak_rss_bytes", return_value=2 * 1024 ** 3
        ):
            self.assertEqual(run_llm._rss_gb(), 2.0)
            self.assertEqual(run_llm._format_rss(), "2,00 GiB")

    def test_failed_rss_query_is_reported_as_unavailable(self):
        with patch.object(run_llm.sys, "platform", "win32"), patch.object(
            run_llm, "_windows_peak_rss_bytes", side_effect=OSError("falha")
        ):
            self.assertIsNone(run_llm._rss_gb())
            self.assertEqual(run_llm._format_rss(), "indisponível")

    def test_machine_records_windows_memory(self):
        with patch.object(run_llm.sys, "platform", "win32"), patch.object(
            run_llm, "_windows_physical_memory_bytes", return_value=123456
        ):
            self.assertIn("Memória física (bytes): 123456", run_llm._machine())


class LlmOutputTest(unittest.TestCase):
    def test_existing_output_is_not_modified_or_model_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "resultado.md"
            output.write_text("anterior", encoding="utf-8")
            with patch("sistema.core.dataset.load_gsm8k") as load, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    run_llm.main(["--saida", str(output)])
            self.assertEqual(result.exception.code, 2)
            load.assert_not_called()
            self.assertEqual(output.read_text(encoding="utf-8"), "anterior")

    def test_output_path_and_explicit_overwrite_with_mocked_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "novo" / "resultado.md"
            tasks = [{"question": "1+1?", "answer": 2}]
            with patch("sistema.core.dataset.load_gsm8k", return_value=tasks), patch(
                "sistema.node.inference.ModelBackend", return_value=types.SimpleNamespace(device="cpu")
            ), patch.object(run_llm, "_generate", return_value=(2, "2", 1.0)), patch.object(
                run_llm, "N_ACCURACY", 1
            ), patch.object(run_llm, "N_QUESTIONS", 1), patch.object(
                run_llm, "N_SAMPLES", 1
            ), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_llm.main(["--saida", str(output)]), 0)
                self.assertIn("Acertos: 1/1", output.read_text(encoding="utf-8"))
                output.write_text("antigo", encoding="utf-8")
                self.assertEqual(run_llm.main(["--saida", str(output), "--sobrescrever"]), 0)
            self.assertIn("Acertos: 1/1", output.read_text(encoding="utf-8"))
            self.assertIn("--sobrescrever", output.read_text(encoding="utf-8"))

    def test_failure_returns_nonzero_and_creates_diagnostic_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "falha.md"
            with patch("sistema.core.dataset.load_gsm8k", side_effect=RuntimeError("sem dados")), contextlib.redirect_stdout(io.StringIO()):
                result = run_llm.main(["--saida", str(output)])
            self.assertEqual(result, 1)
            self.assertIn("sem dados", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
