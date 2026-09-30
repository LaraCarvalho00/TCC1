"""Tabela de validação: nós problemáticos por (N, nível), sem arredondamento."""

from __future__ import annotations

import unittest

from sistema.core.experiment_spec import (
    CONFIGS,
    EXPECTED_MALICIOUS_TABLE,
    EXPECTED_PROGRESSAO_TABLE,
    LEVELS,
    LEVELS_PROGRESSAO,
    NETWORK_SIZES,
    assign_profiles,
    iter_cells_by_config,
    n_problematicos,
    split_instaveis,
)
from sistema.core import behavior


class ExperimentGridTests(unittest.TestCase):
    def test_malicious_table_exact(self) -> None:
        for n, row in EXPECTED_MALICIOUS_TABLE.items():
            for nivel, expected in row.items():
                self.assertEqual(n_problematicos(n, nivel), expected, (n, nivel))

    def test_all_sizes_and_levels_covered(self) -> None:
        self.assertEqual(tuple(EXPECTED_MALICIOUS_TABLE), NETWORK_SIZES)
        for row in EXPECTED_MALICIOUS_TABLE.values():
            self.assertEqual(tuple(row), LEVELS)

    def test_split_odd_goes_to_malicious(self) -> None:
        # p60 em N=5 → 3 problemáticos → 2 maliciosos + 1 instável
        self.assertEqual(split_instaveis(3, "sem_conluio_instavel", "split"), (2, 1))
        # p40 em N=10 → 4 → 2 + 2
        self.assertEqual(split_instaveis(4, "com_conluio_instavel", "split"), (2, 2))

    def test_without_unstable_keeps_full_malicious_count(self) -> None:
        self.assertEqual(split_instaveis(8, "sem_conluio", "split"), (8, 0))
        self.assertEqual(split_instaveis(8, "com_conluio", "extra"), (8, 0))

    def test_orchestrator_never_malicious_or_unstable(self) -> None:
        profiles = assign_profiles(5, n_maliciosos=4, n_instaveis=0, rng_seed=1)
        self.assertEqual(profiles["node-0"], behavior.HONEST)
        self.assertEqual(sum(1 for p in profiles.values() if p == behavior.MALICIOUS), 4)

    def test_cell_count(self) -> None:
        self.assertEqual(len(NETWORK_SIZES) * len(LEVELS) * len(CONFIGS), 240)

    def test_progressao_table_exact(self) -> None:
        self.assertEqual(tuple(EXPECTED_PROGRESSAO_TABLE), NETWORK_SIZES)
        for n, row in EXPECTED_PROGRESSAO_TABLE.items():
            self.assertEqual(tuple(row), LEVELS_PROGRESSAO)
            for nivel, expected in row.items():
                self.assertEqual(n_problematicos(n, nivel), expected, (n, nivel))

    def test_progressao_cell_count(self) -> None:
        self.assertEqual(len(NETWORK_SIZES) * len(LEVELS_PROGRESSAO) * len(CONFIGS), 280)

    def test_iter_cells_by_config_starts_with_sem_conluio(self) -> None:
        cells = list(iter_cells_by_config())
        self.assertEqual(cells[0], (5, "p0", "sem_conluio"))
        self.assertEqual(cells[1], (5, "p5", "sem_conluio"))
        first_of_second = len(NETWORK_SIZES) * len(LEVELS_PROGRESSAO)
        self.assertEqual(cells[first_of_second][2], "com_conluio")
        self.assertEqual(cells[first_of_second], (5, "p0", "com_conluio"))
        configs_in_order = []
        for _n, _nivel, cfg in cells:
            if cfg not in configs_in_order:
                configs_in_order.append(cfg)
        self.assertEqual(configs_in_order, list(CONFIGS))
        self.assertEqual(len(cells), 280)


if __name__ == "__main__":
    unittest.main()
