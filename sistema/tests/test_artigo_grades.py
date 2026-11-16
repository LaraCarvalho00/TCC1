"""Regressão das grades do artigo e de suas saídas isoladas."""
import hashlib
import csv
import json
from pathlib import Path
import tempfile
import unittest

from sistema.experimentos import centros, ruido
from sistema.experimentos.execucao import BANCO_PADRAO, executar_grade


class GradesArtigoTest(unittest.TestCase):
    def test_matrizes_e_banco_correspondem_ao_artigo(self):
        self.assertEqual(len(ruido.trabalhos()), 2560)
        self.assertEqual(len(centros.trabalhos()), 960)
        tasks, bank = ruido.carregar_banco(str(BANCO_PADRAO))
        self.assertEqual(len(tasks), 50)
        self.assertEqual(sum(len(samples) for samples in bank.values()), 1000)
        self.assertEqual(hashlib.sha256(BANCO_PADRAO.read_bytes()).hexdigest(),
                         'a376d3cfc75c844270456d831a3f63f1c7766fbf250ae1e0ddade4d8f8cb2afb')

    def test_referencia_ultimas_condicoes(self):
        tasks, bank = ruido.carregar_banco(str(BANCO_PADRAO))
        with tempfile.TemporaryDirectory() as temp:
            row, _ = ruido.executar(ruido.trabalhos()[-1], tasks, bank, temp)
            self.assertEqual((row['com_reputacao_sem_gabarito'], row['sem_reputacao_sem_gabarito'], row['cadeias_no_fim']),
                             (0.35, 0.125, 1))
        with tempfile.TemporaryDirectory() as temp:
            row, _ = centros.executar(centros.trabalhos()[-1], tasks, bank, temp)
            self.assertEqual((row['com_reputacao_sem_gabarito'], row['sem_reputacao_sem_gabarito'], row['cadeias_no_fim']),
                             (0.025, 0.05, 1))

    def test_execucoes_tem_pastas_unicas_e_manifestos(self):
        job = ruido.trabalhos()[-1]
        with tempfile.TemporaryDirectory() as temp:
            first = executar_grade('ruido', ruido, temp, BANCO_PADRAO, [job])
            second = executar_grade('ruido', ruido, temp, BANCO_PADRAO, [job])
            self.assertNotEqual(first, second)
            for directory in (first, second):
                manifest = json.loads((directory / 'manifesto.json').read_text(encoding='utf8'))
                self.assertEqual((manifest['status'], manifest['concluidas']), ('concluido', 1))
                self.assertEqual(manifest['tarefas'], 50)
                self.assertTrue((directory / 'execucoes.csv').is_file())
                self.assertTrue((directory / 'resumo.csv').is_file())
                self.assertTrue((directory / 'reputacao_por_rodada.csv').is_file())
                self.assertFalse((directory / 'brutos').exists())

    def test_multiplos_processos_preservam_ordem_e_opcao_de_brutos(self):
        jobs = ruido.trabalhos()[-2:]
        with tempfile.TemporaryDirectory() as temp:
            serial = executar_grade('ruido', ruido, temp, BANCO_PADRAO, jobs, workers=1)
            paralelo = executar_grade('ruido', ruido, temp, BANCO_PADRAO, jobs, workers=2, guardar_brutos=True)
            def rows(path):
                with (path / 'execucoes.csv').open(encoding='utf8', newline='') as handle:
                    return list(csv.DictReader(handle))
            self.assertEqual(rows(serial), rows(paralelo))
            self.assertFalse((serial / 'brutos').exists())
            self.assertEqual(len(list((paralelo / 'brutos').rglob('summary.json'))), 2)


if __name__ == '__main__':
    unittest.main()
