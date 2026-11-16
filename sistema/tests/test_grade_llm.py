from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sistema.experimentos.grade_llm import execute, scenarios


class GradeLlmTests(unittest.TestCase):
    def test_grade_tem_proporcoes_exatas_e_total(self):
        jobs = scenarios([0], ["exact", "graded"])
        self.assertEqual(len(jobs), 16)
        self.assertEqual({x["fracao_maliciosos"] for x in jobs}, {0.2, 0.4, 0.6, 0.8})
        self.assertEqual({x["audit_p"] for x in jobs}, {0.1, 0.2})
        self.assertEqual(len({x["id"] for x in jobs}), 16)

    def test_selecao_de_um_cenario(self):
        jobs = scenarios([0], ["graded"], (0.4,), (0.2,), 20, 50)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], "n20-r50-m40-p20-graded-s0")
        with self.assertRaises(ValueError):
            scenarios([0], ["graded"], (0.35,), (0.2,))

    def test_retoma_sem_sobrescrever_e_cache_separado_por_cenario(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            task_file = base / "tarefas.json"
            task_file.write_text('{"tarefas": []}', encoding="utf-8")
            calls = []

            def fake_run(cmd, **kwargs):
                calls.append(cmd)
                # Segunda tentativa da primeira execução falha para exercitar retomada.
                if len(calls) == 2:
                    return subprocess.CompletedProcess(cmd, 1)
                output = Path(cmd[cmd.index("--output") + 1]) / cmd[cmd.index("--experiment-id") + 1]
                output.mkdir(parents=True)
                (output / "inferencia_manifesto.json").write_text('{"status": "concluido"}', encoding="utf-8")
                (output / "summary.json").write_text('{}', encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0)

            with patch("sistema.experimentos.grade_llm.subprocess.run", side_effect=fake_run):
                destination = base / "grade"
                manifest_path, ok = execute(destination, task_file, [0], ["exact"])
                self.assertFalse(ok)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["cenarios"][0]["status"], "concluido")
                self.assertEqual(manifest["cenarios"][1]["status"], "falhou")
                manifest_path, ok = execute(destination, task_file, [0], ["exact"], resume=True)
                self.assertTrue(ok)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(len(calls), 9)  # 8 cenários e a tentativa que falhou
            self.assertEqual(len(manifest["cenarios"][0]["tentativas"]), 1)
            self.assertEqual(len(manifest["cenarios"][1]["tentativas"]), 2)
            previous, retried = calls[1], calls[2]
            for option in ("--inference-run-id", "--inference-cache"):
                self.assertEqual(previous[previous.index(option) + 1], retried[retried.index(option) + 1])
            self.assertNotEqual(previous[previous.index("--experiment-id") + 1], retried[retried.index("--experiment-id") + 1])
            self.assertNotEqual(calls[0][calls[0].index("--inference-cache") + 1], previous[previous.index("--inference-cache") + 1])
            task_file.write_text('{"tarefas": [1]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "configuração"):
                execute(destination, task_file, [0], ["exact"], resume=True)

    def test_nao_declara_sucesso_sem_resultados_concluidos(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            task_file = base / "tarefas.json"
            task_file.write_text("{}", encoding="utf-8")
            with patch("sistema.experimentos.grade_llm.subprocess.run", return_value=subprocess.CompletedProcess([], 0)):
                manifest_path, ok = execute(base / "grade", task_file, [0], ["exact"])
            self.assertFalse(ok)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["cenarios"][0]["status"], "falhou")

    def test_vinte_nos_cinquenta_rodadas_e_validacao_da_retomada(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            task_file = base / "tarefas.json"
            task_file.write_text("{}", encoding="utf-8")
            with patch("sistema.experimentos.grade_llm.subprocess.run", return_value=subprocess.CompletedProcess([], 1)) as run:
                manifest_path, ok = execute(base / "grade", task_file, [0], ["exact"],
                                            fractions=(0.4,), probabilities=(0.2,), nodes=20, rounds=50)
            self.assertFalse(ok)
            cmd = run.call_args.args[0]
            self.assertEqual(cmd[cmd.index("--nodes") + 1], "20")
            self.assertEqual(cmd[cmd.index("--rounds") + 1], "50")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["chamadas_previstas"], 1000)
            with self.assertRaisesRegex(ValueError, "configuração"):
                execute(base / "grade", task_file, [0], ["exact"], resume=True,
                        fractions=(0.4,), probabilities=(0.2,), nodes=20, rounds=1)


if __name__ == "__main__":
    unittest.main()
