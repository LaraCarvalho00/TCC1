"""Verifica as séries complementares contra parâmetros e evidência histórica."""
import tempfile
import unittest
from pathlib import Path

from sistema.experimentos.complementares import (
    carregar_banco, executar, trabalhos_contraste, trabalhos_instabilidade,
    trabalhos_sensibilidade, main,
)


class ComplementaresTest(unittest.TestCase):
    def test_dimensoes_e_parametros_das_series(self):
        sensitivity, availability, contrast = trabalhos_sensibilidade(), trabalhos_instabilidade(), trabalhos_contraste()
        self.assertEqual((len(sensitivity), len(availability), len(contrast)), (120, 30, 10))
        self.assertEqual({x["fracao"] for x in sensitivity}, {0.5, 0.65, 0.8})
        self.assertEqual({x["instaveis"] for x in availability}, {0.1, 0.2})
        self.assertEqual({x["estrategia"] for x in contrast}, {"on_off", "knows_schedule"})
        self.assertEqual({x["mecanismo"] for x in sensitivity}, {"ema", "ema_asymmetric", "beta"})

    def test_contraste_semente_zero_com_banco_historico(self):
        bank = Path(__file__).resolve().parents[1] / "dados" / "banco_smol.json"
        tasks, answers = carregar_banco(bank)
        job = next(j for j in trabalhos_contraste() if j["estrategia"] == "on_off" and j["semente"] == 0)
        result = executar(job, tasks, answers)
        self.assertEqual(result["com_reputacao_sem_gabarito"], 0.8333)
        self.assertEqual(result["sem_reputacao_sem_gabarito"], 0.3095)

    def test_pasta_existente_nao_e_sobrescrita(self):
        bank = Path(__file__).resolve().parents[1] / "dados" / "banco_smol.json"
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "saida"
            destination.mkdir()
            file = destination / "arquivo.txt"
            file.write_text("preservado", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                main(["contraste", "--banco", str(bank), "--saida", str(destination)])
            self.assertEqual(file.read_text(encoding="utf-8"), "preservado")


if __name__ == "__main__":
    unittest.main()
