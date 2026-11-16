"""Legibilidade da figura científica no cenário de cinquenta rodadas."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from sistema.experimentos.graficos_reputacao_llm import gerar


class ReputationChartTest(unittest.TestCase):
    def test_fifty_rounds_use_readable_axis_and_preserve_all_checkpoints(self):
        try:
            from matplotlib.axes import Axes
        except ImportError:
            self.skipTest("Matplotlib é uma dependência opcional de análise.")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            grade = root / "grade"
            folder = grade / "cenarios" / "c1" / "t1"
            folder.mkdir(parents=True)
            (grade / "manifesto_grade.json").write_text(json.dumps({
                "configuracao": {"nos": 50, "rodadas": 50, "sementes": [0]},
                "cenarios": [{"id": "c1", "fracao_maliciosos": .2, "audit_p": .1,
                              "nota": "exact", "semente": 0, "status": "concluido",
                              "tentativas": [{"id": "t1", "status": "concluido"}]}]}))
            (folder / "summary.json").write_text(json.dumps({"summary": {"rounds": 50}}))
            with (folder / "rounds.csv").open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["round_index", "num_nodes", "audited", "calibration", "consensus_correct"])
                writer.writerows((index, 50, int(index % 10 == 0), 0, 1) for index in range(50))
            with (folder / "reputation_history.csv").open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["checkpoint", "node_id", "profile", "reputation"])
                writer.writerows((checkpoint, f"node-{node}", "malicious" if node < 10 else "honest", .5)
                                 for checkpoint in range(51) for node in range(50))
            original = Axes.set_xticks
            with mock.patch.object(Axes, "set_xticks", autospec=True, side_effect=original) as ticks:
                gerar(grade, root / "figures")
            expected = list(range(0, 51, 5))
            self.assertTrue(any(call.args[1] == expected for call in ticks.call_args_list))
            self.assertTrue((root / "figures" / "reputacao_20pct.png").is_file())
            self.assertTrue((root / "figures" / "reputacao_20pct.pdf").is_file())
            with (root / "figures" / "reputacao_por_rodada.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 102)
            self.assertEqual({int(row["checkpoint"]) for row in rows}, set(range(51)))


if __name__ == "__main__":
    unittest.main()
