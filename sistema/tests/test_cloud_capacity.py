"""Admissão de 50 modelos residentes antes de criar infraestrutura paga."""
import unittest

from sistema.aplicacao.capacidade_nuvem import plan_capacity, validate_devices


class CapacityTest(unittest.TestCase):
    def test_50_independent_models_map_to_eight_gpus(self):
        plan = plan_capacity(50)
        self.assertEqual(plan["gpu_count"], 8)
        self.assertEqual(plan["model_instances"], 50)
        self.assertEqual(plan["models_per_gpu"], 7)
        self.assertEqual(plan["required_gpu_memory_gib"], 34)

    def test_refuses_undersized_hosts_and_custom_oversubscription(self):
        for nodes, host in ((50, "g6e.12xlarge"), (50, "g6e.4xlarge"), (73, "g6e.48xlarge"), (50, "g6.4xlarge")):
            with self.subTest(nodes=nodes, host=host), self.assertRaises(ValueError):
                plan_capacity(nodes, host)

    def test_small_pilot_can_use_one_gpu(self):
        self.assertEqual(plan_capacity(8, "g6e.4xlarge")["required_gpu_memory_gib"], 38)

    def test_gpu_capacity_is_per_device_not_aggregate(self):
        config = {**plan_capacity(50), "nodes": 50}
        devices = [{"free_mib": 44 * 1024, "total_mib": 44 * 1024}] * 8
        self.assertEqual(validate_devices(config, devices)["models"], 50)
        with self.assertRaisesRegex(ValueError, "GPU 3"):
            validate_devices(config, devices[:3] + [{"free_mib": 30 * 1024}] + devices[4:])
        with self.assertRaisesRegex(ValueError, "Esperadas 8 GPUs"):
            validate_devices(config, devices[:4])
