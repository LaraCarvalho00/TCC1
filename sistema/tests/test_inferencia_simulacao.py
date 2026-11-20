"""Integração da inferência por nó e rodada, sem carregar modelos externos."""
import json
from pathlib import Path
import tempfile
import unittest

from sistema.simulate import parse_args, run_simulation


class FakeModel:
    model_name = "teste"
    max_new_tokens = 20

    def __init__(self):
        self.calls = []

    def sample(self, question, *, temperature, top_p, seed):
        self.calls.append((question, temperature, top_p, seed))
        return len(self.calls) + 10, "texto de teste"


class LiveSimulationTests(unittest.TestCase):
    def args(self, directory):
        args = parse_args([
            "--nodes", "4", "--rounds", "2", "--malicious", "0.5", "--seed", "7",
            "--output", directory, "--experiment-id", "teste", "--quiet",
            "--malicious-answer", "noise", "--noise-mode", "relative", "--noise-distance", "0.2",
            "--collusion-value", "999", "--audit-mode", "random", "--audit-p", "0.2",
            "--signal", "consensus", "--consensus-mode", "distance",
        ])
        args.live_model_backend = FakeModel()
        args.tasks = [{"id": "a", "question": "Quanto?", "answer": 11}]
        return args

    def test_one_fresh_call_per_node_and_round_with_shared_attack(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory)
            run_simulation(args)
            self.assertEqual(len(args.live_model_backend.calls), 8)
            rows = [json.loads(line) for line in (Path(directory) / "teste" / "inferencias.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 8)
            self.assertEqual(len({row["semente"] for row in rows}), 8)
            self.assertTrue(all(row["texto_gerado"] == "texto de teste" for row in rows))
            for round_number in (1, 2):
                group = [row for row in rows if row["rodada"] == round_number]
                attackers = [row for row in group if row["perfil"] == "malicious"]
                honest = [row for row in group if row["perfil"] == "honest"]
                self.assertEqual(len(attackers), 2)
                self.assertEqual(attackers[0]["resposta_enviada"], attackers[1]["resposta_enviada"])
                self.assertEqual({row["no_base_ruido_compartilhado"] for row in attackers}, {attackers[0]["no"]})
                self.assertTrue(all(row["resposta_modelo"] == row["resposta_enviada"] for row in honest))
            manifest = json.loads((Path(directory) / "teste" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["config"]["inferencia"]["chamadas"], 8)
            live_manifest = json.loads((Path(directory) / "teste" / "inferencia_manifesto.json").read_text(encoding="utf-8"))
            self.assertEqual(live_manifest["status"], "concluido")

    def test_live_rejects_precomputed_responses(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory)
            args.answer_bank = {"a": [1]}
            with self.assertRaisesRegex(ValueError, "banco de respostas"):
                run_simulation(args)
            self.assertFalse(args.live_model_backend.calls)

    def test_malicious_node_mimics_honest_in_initial_rounds(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory)
            args.malicious_strategy = "knows_schedule"
            args.honest_rounds = 1
            run_simulation(args)
            rows = [json.loads(line) for line in (Path(directory) / "teste" / "inferencias.jsonl").read_text(encoding="utf-8").splitlines()]
            first = [row for row in rows if row["rodada"] == 1 and row["perfil"] == "malicious"]
            second = [row for row in rows if row["rodada"] == 2 and row["perfil"] == "malicious"]
            self.assertTrue(all(row["resposta_modelo"] == row["resposta_enviada"] for row in first))
            self.assertTrue(all(row["origem_resposta"] == "ruido_compartilhado" for row in second))

    def test_live_unstable_attribute_can_drop_after_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory)
            args.unstable = 0.5
            args.unstable_mode = "attribute"
            args.unstable_p_drop = 1.0
            run_simulation(args)
            rows = [json.loads(line) for line in (Path(directory) / "teste" / "inferencias.jsonl").read_text(encoding="utf-8").splitlines()]
            dropped = [row for row in rows if row["origem_resposta"] == "instavel"]
            self.assertEqual(len(args.live_model_backend.calls), 8)
            self.assertEqual(len(dropped), 4)
            self.assertTrue(all(row["resposta_enviada"] is None for row in dropped))

    def test_partial_progress_is_kept_on_model_error(self):
        class Failing(FakeModel):
            def sample(self, *args, **kwargs):
                if len(self.calls) == 1:
                    raise RuntimeError("falha da inferência")
                return super().sample(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            args = self.args(directory)
            args.live_model_backend = Failing()
            with self.assertRaisesRegex(RuntimeError, "falha"):
                run_simulation(args)
            path = Path(directory) / "teste" / "inferencias.jsonl"
            self.assertEqual(len(path.read_text(encoding="utf8").splitlines()), 1)
            live_manifest = json.loads((path.parent / "inferencia_manifesto.json").read_text(encoding="utf8"))
            self.assertEqual(live_manifest["status"], "falhou")
            self.assertFalse(live_manifest["retomada_automatica"])


if __name__ == "__main__":
    unittest.main()
