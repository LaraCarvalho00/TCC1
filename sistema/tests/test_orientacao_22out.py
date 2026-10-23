"""Testes da orientação de 22/10. O padrão do protocolo não entra aqui."""
import unittest

from sistema.core.distance import medoid, relative_distance


class DistanceTest(unittest.TestCase):
    def test_relative_distance_exact_values(self):
        self.assertEqual(relative_distance(18, 18), 0)
        self.assertEqual(relative_distance(20, 18), 2 / 38)
        self.assertEqual(relative_distance(999, 18), 981 / 1017)
        self.assertEqual(relative_distance(0, 0), 0)
        self.assertEqual(relative_distance(None, 5), 1)

    def test_medoid_exact_values(self):
        self.assertEqual(medoid([18, 18, 20, 999]).answer, 18)
        self.assertEqual(medoid([1, 2]).answer, 1)
        self.assertEqual(medoid([18, 999, 999], weights=[1, 0.01, 0.01]).answer, 18)
