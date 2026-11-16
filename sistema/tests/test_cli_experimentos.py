"""A entrada principal encaminha as opções às séries do artigo."""
import contextlib
import io
import unittest
from unittest.mock import patch

from sistema.interfaces import cli


class CliExperimentosTest(unittest.TestCase):
    def test_encaminha_argumentos_e_codigo_de_saida(self):
        with patch("sistema.interfaces.cli.artigo_cli.main", return_value=7) as runner:
            code = cli.main(["experimentos", "ruido", "--workers", "4"])
        self.assertEqual(code, 7)
        runner.assert_called_once_with(["ruido", "--workers", "4"])

    def test_planejar_todas_mostra_apenas_series_principais(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(["experimentos", "todas", "--planejar"])
        self.assertEqual(code, 0)
        self.assertIn("Total: 3670", output.getvalue())
        self.assertNotIn("contraste", output.getvalue())

    def test_grupo_desconhecido_e_rejeitado(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["desconhecido", "todas"])


if __name__ == "__main__":
    unittest.main()
