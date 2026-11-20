"""Contagem e CLI da história incremental, sem GPU."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sistema.experimentos import cenarios_incrementais as incremental


class CenariosIncrementaisTest(unittest.TestCase):
    def test_recorte_tcc_tem_vinte_execucoes(self):
        jobs, spec = incremental.trabalhos("tcc")
        self.assertEqual(spec["nos"], 10)
        self.assertEqual(spec["rodadas"], 20)
        self.assertEqual(spec["sementes"], (0,))
        self.assertEqual(len(jobs), 20)
        self.assertEqual({job["etapa"] for job in jobs}, {4, 5, 6, 7})
        self.assertEqual(sum(1 for job in jobs if job["etapa"] == 4), 7)
        self.assertEqual(sum(1 for job in jobs if job["etapa"] == 5), 7)
        self.assertEqual(sum(1 for job in jobs if job["etapa"] == 6), 3)
        self.assertEqual(sum(1 for job in jobs if job["etapa"] == 7), 3)
        self.assertTrue(all(job["audit_p"] == 0.2 for job in jobs if job["etapa"] == 5))

    def test_recorte_n20_tem_vinte_execucoes_em_vinte_por_cinquenta(self):
        jobs, spec = incremental.trabalhos("n20")
        self.assertEqual(spec["nos"], 20)
        self.assertEqual(spec["rodadas"], 50)
        self.assertEqual(spec["sementes"], (0,))
        self.assertEqual(len(jobs), 20)
        self.assertEqual({job["etapa"] for job in jobs}, {4, 5, 6, 7})

    def test_recorte_n20s5_tem_cem_execucoes(self):
        jobs, spec = incremental.trabalhos("n20s5")
        self.assertEqual(spec["nos"], 20)
        self.assertEqual(spec["rodadas"], 50)
        self.assertEqual(spec["sementes"], (0, 1, 2, 3, 4))
        self.assertEqual(len(jobs), 100)
        self.assertEqual(len({job["id"] for job in jobs}), 100)

    def test_recorte_isabela_tem_cento_e_setenta_e_cinco(self):
        jobs, spec = incremental.trabalhos("isabela")
        self.assertEqual(spec["nos"], 50)
        self.assertEqual(spec["rodadas"], 50)
        self.assertEqual(len(jobs), 175)
        self.assertEqual(len({job["id"] for job in jobs}), 175)

    def test_planejar_nao_cria_pasta(self):
        with tempfile.TemporaryDirectory() as temp:
            saida = Path(temp) / "nao-criar"
            code = incremental.main(["--planejar", "--recorte", "tcc", "--saida", str(saida)])
            self.assertEqual(code, 0)
            self.assertFalse(saida.exists())

    def test_isabela_sem_confirmacao_e_recusado(self):
        with tempfile.TemporaryDirectory() as temp:
            saida = Path(temp) / "grande"
            code = incremental.main(["--recorte", "isabela", "--fonte", "vivo", "--saida", str(saida), "--llm", "smol"])
            self.assertEqual(code, 1)
            self.assertFalse(saida.exists())

    def test_pasta_concluida_nao_e_sobrescrita(self):
        with tempfile.TemporaryDirectory() as temp:
            saida = Path(temp) / "done"
            saida.mkdir()
            (saida / "manifesto.json").write_text(
                json.dumps({"status": "concluido", "recorte": "tcc", "jobs": []}), encoding="utf-8"
            )
            with self.assertRaises(FileExistsError):
                incremental.executar(saida, recorte="tcc", llm="smol",
                                     tarefas=incremental.TAREFAS_PADRAO, workers=1)

    def test_banco_smol_tem_cinquenta_por_vinte(self):
        tasks, answers, digest, bruto = incremental.carregar_banco(incremental.TAREFAS_PADRAO)
        self.assertEqual(len(tasks), 50)
        self.assertEqual(len(digest), 64)
        self.assertEqual(bruto["total"], 1000)
        self.assertEqual({len(values) for values in answers.values()}, {20})

    def test_etapas_derivam_medoide_sem_peso(self):
        rows = [
            {"etapa": 4, "conluio": 0, "fracao": 0.0, "sem_reputacao_sem_gabarito": 0.5,
             "com_reputacao_sem_gabarito": 0.6, "audit_p": 0.1},
            {"etapa": 4, "conluio": 0, "fracao": 0.2, "sem_reputacao_sem_gabarito": 0.2,
             "com_reputacao_sem_gabarito": 0.4, "audit_p": 0.1},
            {"etapa": 4, "conluio": 1, "fracao": 0.2, "sem_reputacao_sem_gabarito": 0.1,
             "com_reputacao_sem_gabarito": 0.3, "audit_p": 0.1},
            {"etapa": 5, "conluio": 1, "fracao": 0.2, "sem_reputacao_sem_gabarito": 0.1,
             "com_reputacao_sem_gabarito": 0.7, "audit_p": 0.2},
        ]
        tabela = incremental.resumir_etapas(rows)
        base = next(item for item in tabela if item["etapa"] == 1)
        self.assertEqual(base["acuracia_media"], 50.0)
        sem_rep = next(item for item in tabela if item["etapa"] == 2 and item["fracao"] == 0.2)
        self.assertEqual(sem_rep["acuracia_media"], 20.0)
        audit = next(item for item in tabela if item["etapa"] == 5)
        self.assertEqual(audit["acuracia_media"], 70.0)
