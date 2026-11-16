"""Valida os denominadores e a exclusão de cenários não concluídos."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

from sistema.experimentos.graficos_cenarios_llm import gerar, ler_grade


class GraficosCenariosTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.grade = self.base / "grade"
        self.grade.mkdir()
        self.manifest = {
            "configuracao": {"nos": 20, "rodadas": 3, "sementes": [0]},
            "cenarios": [
                {"id": "c1", "fracao_maliciosos": 0.2, "audit_p": 0.1,
                 "nota": "graded", "semente": 0, "status": "concluido",
                 "tentativas": [{"id": "t1", "status": "concluido"}]},
                {"id": "c2", "fracao_maliciosos": 0.4, "audit_p": 0.1,
                 "nota": "graded", "semente": 0, "status": "em_andamento", "tentativas": []},
            ],
        }
        self.save_manifest()
        self.result = self.grade / "cenarios" / "c1" / "t1"
        self.result.mkdir(parents=True)
        (self.result / "summary.json").write_text(json.dumps({"summary": {"rounds": 3}}), encoding="utf-8")
        self.write_rows([
            {"round_index": 0, "num_nodes": 20, "audited": 0, "calibration": 0, "consensus_correct": 1},
            {"round_index": 1, "num_nodes": 20, "audited": 1, "calibration": 0, "consensus_correct": 0},
            {"round_index": 2, "num_nodes": 20, "audited": 0, "calibration": 0, "consensus_correct": 0},
        ])

    def tearDown(self):
        self.temp.cleanup()

    def save_manifest(self):
        (self.grade / "manifesto_grade.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def write_rows(self, rows):
        with (self.result / "rounds.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def test_exclui_auditoria_e_cenario_incompleto(self):
        _, scenarios, rows, _ = ler_grade(self.grade)
        self.assertEqual(len(scenarios), 2)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["acertos"], rows[0]["rodadas_avaliadas"], rows[0]["acuracia"]), (1, 2, 0.5))
        out = self.base / "figuras"
        gerar(self.grade, out)
        self.assertTrue((out / "acuracia_cenarios.png").is_file())
        self.assertTrue((out / "acuracia_cenarios.pdf").is_file())
        self.assertTrue((out / "acuracia_com_ataque.png").is_file())
        self.assertTrue((out / "acuracia_com_ataque.pdf").is_file())
        self.assertIsNone(rows[0]["acuracia_com_ataque"])
        self.assertIn("1 estavam concluídos", (out / "LEGENDA_E_METODOLOGIA.md").read_text(encoding="utf-8"))

    def test_rejeita_rodadas_incompletas(self):
        self.write_rows([{"round_index": 0, "num_nodes": 20, "audited": 0,
                          "calibration": 0, "consensus_correct": 1}])
        with self.assertRaisesRegex(ValueError, "rodadas inconsistentes"):
            ler_grade(self.grade)

    def test_sem_rodadas_elegiveis_nao_e_zero(self):
        self.write_rows([
            {"round_index": i, "num_nodes": 20, "audited": 1, "calibration": 0, "consensus_correct": 0}
            for i in range(3)
        ])
        _, _, rows, _ = ler_grade(self.grade)
        self.assertEqual(rows[0]["rodadas_avaliadas"], 0)
        self.assertIsNone(rows[0]["acuracia"])

    def test_ataque_exclui_imitacao_e_auditoria(self):
        self.manifest["configuracao"]["rodadas"] = 10
        self.save_manifest()
        (self.result / "summary.json").write_text(json.dumps({
            "summary": {"rounds": 10},
            "config": {"malicious_strategy": "knows_schedule", "audit_mode": "random", "honest_rounds": 5},
        }), encoding="utf-8")
        self.write_rows([
            {"round_index": i, "num_nodes": 20, "audited": int(i in (5, 7, 8)),
             "calibration": 0, "consensus_correct": int(i != 9)}
            for i in range(10)
        ])
        _, _, rows, _ = ler_grade(self.grade)
        self.assertEqual((rows[0]["acertos"], rows[0]["rodadas_avaliadas"]), (6, 7))
        self.assertEqual((rows[0]["acertos_com_ataque"], rows[0]["rodadas_com_ataque_avaliadas"],
                          rows[0]["acuracia_com_ataque"]), (1, 2, 0.5))

    def test_sem_ataque_nao_e_zero(self):
        _, _, rows, _ = ler_grade(self.grade)
        self.assertEqual(rows[0]["rodadas_com_ataque_avaliadas"], 0)
        self.assertIsNone(rows[0]["acuracia_com_ataque"])

    def test_seis_rodadas_usa_uma_rodada_inicial_e_denominador_observado(self):
        self.manifest["configuracao"].update({"rodadas": 6, "rodadas_iniciais_honestas": 1})
        self.manifest["cenarios"][0]["audit_p"] = 0.2
        self.save_manifest()
        (self.result / "summary.json").write_text(json.dumps({
            "summary": {"rounds": 6},
            "config": {"malicious_strategy": "knows_schedule", "audit_mode": "random", "honest_rounds": 1},
        }), encoding="utf-8")
        self.write_rows([
            {"round_index": i, "num_nodes": 20, "audited": int(i in (1, 4)),
             "calibration": 0, "consensus_correct": int(i in (0, 2, 5))}
            for i in range(6)
        ])
        _, _, rows, _ = ler_grade(self.grade)
        self.assertEqual((rows[0]["acertos_com_ataque"], rows[0]["rodadas_com_ataque_avaliadas"]), (2, 3))
        out = self.base / "seis_rodadas"
        gerar(self.grade, out)
        caption = (out / "LEGENDA_E_METODOLOGIA.md").read_text(encoding="utf-8")
        self.assertIn("20 nós, 6 rodadas", caption)
        self.assertIn("1 rodada(s) inicial(is)", caption)
        self.assertIn("p=0,2: 3 rodada(s) elegível(is)", caption)
        self.assertNotIn("dez rodadas", caption)
        self.assertNotIn("cinco rodadas", caption)

    def test_rejeita_rodadas_iniciais_divergentes(self):
        self.manifest["configuracao"]["rodadas_iniciais_honestas"] = 1
        self.save_manifest()
        (self.result / "summary.json").write_text(json.dumps({
            "summary": {"rounds": 3}, "config": {"honest_rounds": 2},
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Rodadas iniciais inconsistentes"):
            ler_grade(self.grade)


if __name__ == "__main__":
    unittest.main()
