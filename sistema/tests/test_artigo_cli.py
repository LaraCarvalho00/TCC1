"""Testes da coordenação das séries de experimentos do artigo."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sistema.interfaces import artigo_cli


class ArtigoCliTests(unittest.TestCase):
    def test_todas_planeja_apenas_3670_principais(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = artigo_cli.main(["todas", "--planejar"])
        self.assertEqual(code, 0)
        self.assertIn("Total: 3670", out.getvalue())
        self.assertNotIn("contraste", out.getvalue())

    def test_todas_encadeia_etapas_e_registra_manifesto(self):
        with tempfile.TemporaryDirectory() as tmp:
            bank = Path(tmp) / "banco.json"
            bank.write_text("{}", encoding="utf-8")
            with patch("sistema.interfaces.artigo_cli.subprocess.run") as run:
                run.return_value.returncode = 0
                output, ok = artigo_cli.executar("todas", Path(tmp) / "saida", bank, 4, True)
            self.assertTrue(ok)
            self.assertEqual(run.call_count, 4)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertTrue(commands[0][2].endswith(".ruido"))
            self.assertTrue(commands[1][2].endswith(".centros"))
            self.assertEqual(commands[2][3], "sensibilidade")
            self.assertEqual(commands[3][3], "instabilidade")
            self.assertTrue(all("--workers" in cmd and "4" in cmd for cmd in commands))
            self.assertTrue(all("--guardar-brutos" in cmd for cmd in commands[:2]))
            self.assertTrue(all("--guardar-brutos" not in cmd for cmd in commands[2:]))
            manifest = json.loads((output / "manifesto_execucao.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "concluido")
            self.assertEqual(manifest["total_previsto"], 3670)
            self.assertEqual([e["status"] for e in manifest["etapas"]], ["concluido"] * 4)

    def test_falha_interrompe_etapas_e_preserva_registro(self):
        with tempfile.TemporaryDirectory() as tmp:
            bank = Path(tmp) / "banco.json"
            bank.write_text("{}", encoding="utf-8")
            with patch("sistema.interfaces.artigo_cli.subprocess.run") as run:
                run.return_value.returncode = 7
                output, ok = artigo_cli.executar("todas", Path(tmp) / "saida", bank)
            self.assertFalse(ok)
            self.assertEqual(run.call_count, 1)
            manifest = json.loads((output / "manifesto_execucao.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "falhou")
            self.assertEqual(manifest["etapas"][0]["codigo_saida"], 7)
            self.assertTrue(all(item["status"] == "pendente" for item in manifest["etapas"][1:]))

    def test_contraste_e_saida_independente(self):
        with tempfile.TemporaryDirectory() as tmp:
            bank = Path(tmp) / "banco.json"
            bank.write_text("{}", encoding="utf-8")
            with patch("sistema.interfaces.artigo_cli.subprocess.run") as run:
                run.return_value.returncode = 0
                first, ok = artigo_cli.executar("contraste", Path(tmp) / "saida", bank)
                second, again = artigo_cli.executar("contraste", Path(tmp) / "saida", bank)
            self.assertTrue(ok and again)
            self.assertNotEqual(first, second)
            self.assertEqual(json.loads((first / "manifesto_execucao.json").read_text())["total_previsto"], 10)
            self.assertEqual(run.call_args_list[0].args[0][3], "contraste")

    def test_invalid_workers_or_missing_bank_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "saida"
            with self.assertRaises(ValueError):
                artigo_cli.executar("ruido", target, Path(tmp) / "ausente", 0)
            with self.assertRaises(FileNotFoundError):
                artigo_cli.executar("ruido", target, Path(tmp) / "ausente", 1)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
