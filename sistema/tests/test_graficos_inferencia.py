"""Cobertura dos denominadores e da validação do progresso de inferência."""
from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
import unittest


def _records():
    greedy = [{"id_questao": f"q{q}", "questao": q, "modo": "gulosa", "amostra": None,
               "previsto": q if q % 2 else None, "esperado": q, "correto": bool(q % 2),
               "duracao_segundos": 2.0} for q in range(1, 51)]
    sample = [{"id_questao": f"q{q}", "questao": q, "modo": "amostragem", "amostra": s,
               "previsto": q if s <= 3 else None, "esperado": q, "correto": s <= 3,
               "duracao_segundos": 3.0} for q in range(1, 11) for s in range(1, 6)]
    return greedy + sample


@unittest.skipUnless(find_spec("matplotlib"), "requer matplotlib")
class GraficosInferenciaTest(unittest.TestCase):
    def _write(self, path, rows):
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    def test_execucao_completa_e_denominadores(self):
        from sistema.experimentos.graficos_inferencia import carregar_progresso, gerar
        with tempfile.TemporaryDirectory() as tmp:
            path, out = Path(tmp) / "progresso.jsonl", Path(tmp) / "graficos"
            self._write(path, _records())
            g, s = carregar_progresso(path)
            self.assertEqual((len(g), len(s)), (50, 50))
            manifest = gerar(path, out)
            self.assertEqual((manifest["acertos_gulosos"], manifest["acertos_amostragem"]), (25, 30))
            self.assertEqual((manifest["questoes_gulosas"], manifest["questoes_amostragem"], manifest["amostras_por_questao"]), (50, 10, 5))
            self.assertEqual(len(list(out.glob("*.png"))), 3)
            self.assertIn("não são 50 questões independentes", (out / "LEGENDA_E_METODOLOGIA.md").read_text(encoding="utf-8"))
            with self.assertRaises(FileExistsError):
                gerar(path, out)

    def test_incompleto_duplicado_e_inconsistente_sao_rejeitados(self):
        from sistema.experimentos.graficos_inferencia import carregar_progresso
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "progresso.jsonl"
            records = _records()
            for rows, expected in ((records[:-1], "incompleto"), (records + [records[0]], "duplicado")):
                self._write(path, rows)
                with self.assertRaisesRegex(ValueError, expected):
                    carregar_progresso(path)
            altered = _records(); altered[0]["correto"] = False
            self._write(path, altered)
            with self.assertRaisesRegex(ValueError, "Indicador de acerto"):
                carregar_progresso(path)
            altered = _records(); altered[-1]["id_questao"] = "outra"
            self._write(path, altered)
            with self.assertRaisesRegex(ValueError, "incompatível"):
                carregar_progresso(path)

    def test_sem_duracoes_nao_inventa_tempos(self):
        from sistema.experimentos.graficos_inferencia import gerar
        with tempfile.TemporaryDirectory() as tmp:
            path, out = Path(tmp) / "progresso.jsonl", Path(tmp) / "graficos"
            records = _records()
            for record in records:
                record.pop("duracao_segundos")
            self._write(path, records)
            manifest = gerar(path, out)
            self.assertFalse(manifest["duracoes_completas"])
            self.assertEqual(len(list(out.glob("*.png"))), 2)


if __name__ == "__main__":
    unittest.main()
