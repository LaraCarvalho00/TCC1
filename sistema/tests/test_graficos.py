"""Valida seleção inequívoca dos dados e contagem efetiva de nós."""
from importlib.util import find_spec
import hashlib
import json
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(find_spec("matplotlib") and find_spec("numpy"), "requer dependências de análise")
class GraficosTest(unittest.TestCase):
    def test_percentuais_efetivos_preservam_arredondamento(self):
        from sistema.experimentos.gerar_graficos import EFFECTIVE
        self.assertEqual(EFFECTIVE, (0, 4, 20, 24, 36, 50, 64, 80))

    def test_filtro_de_cenario_rejeita_dados_ambiguos(self):
        from sistema.experimentos.gerar_graficos import _result
        row = {"config": "auditoria_p20", "conluio": "1", "fracao": "0.5", "ruido": "sutil_0.2", "nota_gabarito": "exact"}
        self.assertIs(_result([row], "auditoria_p20", 1, 0.5), row)
        with self.assertRaisesRegex(ValueError, "encontrados 2"):
            _result([row, dict(row)], "auditoria_p20", 1, 0.5)

    def test_aceita_lotes_separados_e_combinado_e_confere_banco(self):
        from sistema.experimentos.gerar_graficos import _validate_manifests
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            banco = root / "banco.json"
            banco.write_text("{}", encoding="utf-8")
            digest = hashlib.sha256(banco.read_bytes()).hexdigest()

            def lot(name, count):
                directory = root / name
                directory.mkdir()
                key = "experimento" if name in ("ruido", "centros") else "serie"
                (directory / "manifesto.json").write_text(json.dumps({
                    key: name, "status": "concluido", "concluidas": count, "banco_sha256": digest,
                }), encoding="utf-8")
                return directory

            r, c = lot("ruido", 2560), lot("centros", 960)
            s, i, t = lot("sensibilidade", 120), lot("instabilidade", 30), lot("todas", 160)
            self.assertEqual(_validate_manifests(r, c, banco, sensibilidade=s, instabilidade=i),
                             [s / "resumo.csv", i / "resumo.csv"])
            self.assertEqual(_validate_manifests(r, c, banco, complementares=t), [t / "resumo.csv"])
            with self.assertRaisesRegex(ValueError, "sem misturá-los"):
                _validate_manifests(r, c, banco, complementares=t, sensibilidade=s)
            with self.assertRaisesRegex(ValueError, "ambas"):
                _validate_manifests(r, c, banco, sensibilidade=s)
            banco.write_text('{"outro": true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "não corresponde"):
                _validate_manifests(r, c, banco, sensibilidade=s, instabilidade=i)

    def test_rejeita_lote_incompleto_ou_com_tipo_incorreto(self):
        from sistema.experimentos.gerar_graficos import _completed
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            manifest = {"serie": "sensibilidade", "status": "concluido", "concluidas": 119}
            (path / "manifesto.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "120"):
                _completed(path, 120, "sensibilidade")
            manifest["concluidas"] = 120
            (path / "manifesto.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "instabilidade"):
                _completed(path, 120, "instabilidade")


if __name__ == "__main__":
    unittest.main()
