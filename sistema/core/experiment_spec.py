"""Especificação da grade experimental (contagens, sementes, configurações).

Não altera consenso nem reputação: só define *quem* entra em cada célula.
O orquestrador é o ``node-0``, sempre honesto, e conta em N. Nós problemáticos
são sorteados apenas entre os N−1 restantes.
"""

from __future__ import annotations

import hashlib
import random
from typing import Iterable

from . import behavior

NETWORK_SIZES = (5, 10, 15, 20, 25, 30, 35, 40, 45, 50)
LEVELS = ("p0", "n1", "p20", "p40", "p60", "p80")
LEVELS_PROGRESSAO = ("p0", "p5", "p20", "p35", "p50", "p65", "p80")
CONFIGS = (
    "sem_conluio",
    "com_conluio",
    "sem_conluio_instavel",
    "com_conluio_instavel",
)
CONFIG_TITULOS = {
    "sem_conluio": "1. Maliciosos sem conluio",
    "com_conluio": "2. Maliciosos com conluio",
    "sem_conluio_instavel": "3. Maliciosos sem conluio + instáveis (50-50)",
    "com_conluio_instavel": "4. Maliciosos com conluio + instáveis (50-50)",
}
INTERPRETACAO_SPLIT = "split"
INTERPRETACAO_EXTRA = "extra"
COLLUSION_VALUE = 999
ORCHESTRATOR_ID = "node-0"

# Percentuais nominais; n1 não é percentual.
P_NOMINAL = {
    "p0": 0.0,
    "n1": None,
    "p5": 0.05,
    "p20": 0.2,
    "p35": 0.35,
    "p40": 0.4,
    "p50": 0.5,
    "p60": 0.6,
    "p65": 0.65,
    "p80": 0.8,
}


def n_problematicos(n: int, nivel: str) -> int:
    """Quantidade-alvo de nós problemáticos (incidência sobre N, inteiro exato)."""
    if n not in NETWORK_SIZES:
        raise ValueError(f"N={n} fora da grade {NETWORK_SIZES}.")
    if nivel == "p0":
        return 0
    if nivel == "n1":
        return 1
    if nivel.startswith("p") and nivel[1:].isdigit():
        return n * int(nivel[1:]) // 100
    raise ValueError(f"Nível desconhecido: {nivel!r}")


def split_instaveis(
    n_problema: int,
    configuracao: str,
    interpretacao: str = INTERPRETACAO_SPLIT,
    n: int | None = None,
) -> tuple[int, int]:
    """Devolve ``(n_maliciosos, n_instaveis)``.

    ``split`` (padrão): os nós problemáticos se dividem meio a meio.
    Desempate ímpar: a sobra vai para malicioso (ex.: 3 → 2 maliciosos + 1 instável).

    ``extra``: a quantidade cheia de maliciosos *mais* o mesmo número de instáveis.
    Se não couber em N−1, corta instáveis primeiro e, se preciso, maliciosos.
    """
    if configuracao not in CONFIGS:
        raise ValueError(f"Configuração desconhecida: {configuracao!r}")
    quer_instavel = configuracao.endswith("_instavel")
    quer_conluio = configuracao.startswith("com_conluio")
    _ = quer_conluio  # o conluio não muda contagens, só o valor da resposta

    if not quer_instavel:
        return n_problema, 0

    if interpretacao == INTERPRETACAO_EXTRA:
        n_mal, n_unst = n_problema, n_problema
    elif interpretacao == INTERPRETACAO_SPLIT:
        n_mal = (n_problema + 1) // 2
        n_unst = n_problema // 2
    else:
        raise ValueError(f"Interpretação desconhecida: {interpretacao!r}")

    if n is not None:
        cap = n - 1
        if n_mal + n_unst > cap:
            n_unst = max(0, cap - n_mal)
        if n_mal + n_unst > cap:
            n_mal = cap
            n_unst = 0
    return n_mal, n_unst


def derive_seed(n: int, nivel: str, configuracao: str, indice: int) -> int:
    """Semente determinística derivada da célula e do índice da repetição."""
    material = f"{n}|{nivel}|{configuracao}|{indice}".encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return int.from_bytes(digest[:8], "big") % (2**31 - 1)


def assign_profiles(
    n: int,
    n_maliciosos: int,
    n_instaveis: int,
    rng_seed: int,
) -> dict[str, str]:
    """Orquestrador honesto; sorteia os demais com a semente da execução."""
    if n_maliciosos + n_instaveis > n - 1:
        raise ValueError("Maliciosos + instáveis excedem os N−1 nós sorteáveis.")
    node_ids = [f"node-{i}" for i in range(n)]
    workers = [node_id for node_id in node_ids if node_id != ORCHESTRATOR_ID]
    rng = random.Random(rng_seed)
    rng.shuffle(workers)
    profiles = {ORCHESTRATOR_ID: behavior.HONEST}
    for node_id in node_ids:
        if node_id == ORCHESTRATOR_ID:
            continue
        profiles[node_id] = behavior.HONEST
    for node_id in workers[:n_maliciosos]:
        profiles[node_id] = behavior.MALICIOUS
    for node_id in workers[n_maliciosos : n_maliciosos + n_instaveis]:
        profiles[node_id] = behavior.UNSTABLE
    return profiles


def uses_collusion(configuracao: str) -> bool:
    return configuracao.startswith("com_conluio")


def iter_cells(
    sizes: Iterable[int] = NETWORK_SIZES,
    levels: Iterable[str] = LEVELS,
    configs: Iterable[str] = CONFIGS,
):
    for n in sizes:
        for nivel in levels:
            for configuracao in configs:
                yield n, nivel, configuracao


def iter_cells_by_config(
    sizes: Iterable[int] = NETWORK_SIZES,
    levels: Iterable[str] = LEVELS_PROGRESSAO,
    configs: Iterable[str] = CONFIGS,
):
    """Uma config de cada vez; dentro dela, N crescente e depois o percentual."""
    for configuracao in configs:
        for n in sizes:
            for nivel in levels:
                yield n, nivel, configuracao


EXPECTED_MALICIOUS_TABLE = {
    5: {"p0": 0, "n1": 1, "p20": 1, "p40": 2, "p60": 3, "p80": 4},
    10: {"p0": 0, "n1": 1, "p20": 2, "p40": 4, "p60": 6, "p80": 8},
    15: {"p0": 0, "n1": 1, "p20": 3, "p40": 6, "p60": 9, "p80": 12},
    20: {"p0": 0, "n1": 1, "p20": 4, "p40": 8, "p60": 12, "p80": 16},
    25: {"p0": 0, "n1": 1, "p20": 5, "p40": 10, "p60": 15, "p80": 20},
    30: {"p0": 0, "n1": 1, "p20": 6, "p40": 12, "p60": 18, "p80": 24},
    35: {"p0": 0, "n1": 1, "p20": 7, "p40": 14, "p60": 21, "p80": 28},
    40: {"p0": 0, "n1": 1, "p20": 8, "p40": 16, "p60": 24, "p80": 32},
    45: {"p0": 0, "n1": 1, "p20": 9, "p40": 18, "p60": 27, "p80": 36},
    50: {"p0": 0, "n1": 1, "p20": 10, "p40": 20, "p60": 30, "p80": 40},
}

EXPECTED_PROGRESSAO_TABLE = {
    5: {"p0": 0, "p5": 0, "p20": 1, "p35": 1, "p50": 2, "p65": 3, "p80": 4},
    10: {"p0": 0, "p5": 0, "p20": 2, "p35": 3, "p50": 5, "p65": 6, "p80": 8},
    15: {"p0": 0, "p5": 0, "p20": 3, "p35": 5, "p50": 7, "p65": 9, "p80": 12},
    20: {"p0": 0, "p5": 1, "p20": 4, "p35": 7, "p50": 10, "p65": 13, "p80": 16},
    25: {"p0": 0, "p5": 1, "p20": 5, "p35": 8, "p50": 12, "p65": 16, "p80": 20},
    30: {"p0": 0, "p5": 1, "p20": 6, "p35": 10, "p50": 15, "p65": 19, "p80": 24},
    35: {"p0": 0, "p5": 1, "p20": 7, "p35": 12, "p50": 17, "p65": 22, "p80": 28},
    40: {"p0": 0, "p5": 2, "p20": 8, "p35": 14, "p50": 20, "p65": 26, "p80": 32},
    45: {"p0": 0, "p5": 2, "p20": 9, "p35": 15, "p50": 22, "p65": 29, "p80": 36},
    50: {"p0": 0, "p5": 2, "p20": 10, "p35": 17, "p50": 25, "p65": 32, "p80": 40},
}
