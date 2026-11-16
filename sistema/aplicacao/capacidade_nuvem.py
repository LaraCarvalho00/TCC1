"""Planejamento conservador de VRAM para uma cópia NF4 por nó.

O orçamento é uma condição de admissão, não um benchmark: o bootstrap ainda
confere a memória real das GPUs e o runner exige cada modelo carregado.
"""
from __future__ import annotations

import math

PROFILES = {
    "g6e.4xlarge": {"gpu_count": 1, "gpu_memory_gib": 44, "host_memory_gib": 128},
    "g6e.12xlarge": {"gpu_count": 4, "gpu_memory_gib": 44, "host_memory_gib": 384},
    "g6e.48xlarge": {"gpu_count": 8, "gpu_memory_gib": 44, "host_memory_gib": 1536},
}
DEFAULT_INSTANCE = "g6e.48xlarge"
MODEL_MEMORY_GIB = 4
GPU_RESERVE_GIB = 6


def plan_capacity(nodes: int, instance_type: str = DEFAULT_INSTANCE) -> dict:
    if isinstance(nodes, bool) or not isinstance(nodes, int) or nodes < 1:
        raise ValueError("Quantidade de nós inválida.")
    if instance_type not in PROFILES:
        raise ValueError("Escolha um perfil G6e com suporte a uma LLM NF4 por nó.")
    profile = PROFILES[instance_type]
    copies = math.ceil(nodes / profile["gpu_count"])
    required = copies * MODEL_MEMORY_GIB + GPU_RESERVE_GIB
    if required > profile["gpu_memory_gib"]:
        maximum = int((profile["gpu_memory_gib"] - GPU_RESERVE_GIB) // MODEL_MEMORY_GIB) * profile["gpu_count"]
        raise ValueError(f"{instance_type} não atende ao orçamento de VRAM de {nodes} modelos residentes: "
                         f"{copies} cópias/GPU exigem {required} GiB por GPU. "
                         f"Limite de planejamento deste perfil: {maximum} nós; escolha outro perfil.")
    return {**profile, "instance_type": instance_type, "inference_layout": "per_node",
            "model_instances": nodes, "models_per_gpu": copies,
            "model_memory_gib": MODEL_MEMORY_GIB, "gpu_reserve_gib": GPU_RESERVE_GIB,
            "required_gpu_memory_gib": required}


def validate_devices(config: dict, devices: list[dict]) -> dict:
    """Conferência do host antes de iniciar qualquer modelo residente."""
    expected = int(config["gpu_count"])
    if len(devices) != expected:
        raise ValueError(f"Esperadas {expected} GPUs; foram encontradas {len(devices)}.")
    needed_mib = int(config["required_gpu_memory_gib"] * 1024)
    for index, device in enumerate(devices):
        if int(device["free_mib"]) < needed_mib:
            raise ValueError(f"GPU {index} sem VRAM livre para os modelos residentes: "
                             f"{device['free_mib']} MiB livres, exigidos {needed_mib} MiB pelo planejamento.")
    return {"layout": "per_node", "models": config["nodes"], "devices": devices,
            "required_mib_per_gpu": needed_mib}
