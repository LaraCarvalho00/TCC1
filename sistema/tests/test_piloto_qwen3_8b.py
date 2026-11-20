"""Testes do piloto Qwen3-8B compartilhado, sem GPU."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sistema.scripts import piloto_qwen3_8b as pilot


class Qwen38bPilotTest(unittest.TestCase):
    def test_model_ready_requires_expected_shard_sizes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            self.assertFalse(pilot.model_ready(path))
            for name, size in list(pilot.WEIGHT_FILES.items())[:-1]:
                (path / name).write_bytes(b"\0" * min(size, 8))
            self.assertFalse(pilot.model_ready(path))

    def test_gateway_seed_matches_node_app_formula(self):
        import hashlib
        encoded = b"0:4:node-1"
        expected = int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big") & ((1 << 63) - 1)
        self.assertEqual(pilot.gateway_seed(0, 4, "node-1"), expected)
        self.assertNotEqual(pilot.gateway_seed(0, 4, "node-0"), expected)

    def test_existing_output_is_rejected_before_download(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            output = root / "resultados" / "llm" / "old-run"
            output.mkdir(parents=True)
            sentinel = output / "manifesto.json"
            sentinel.write_text(json.dumps({"status": "concluido"}), encoding="utf-8")
            with mock.patch.object(pilot, "ROOT", root), mock.patch.object(pilot, "gpu") as gpu, mock.patch.object(pilot, "ensure_model") as download:
                with self.assertRaises(FileExistsError):
                    pilot.run(output)
            gpu.assert_not_called()
            download.assert_not_called()
            self.assertEqual(json.loads(sentinel.read_text(encoding="utf-8")), {"status": "concluido"})
