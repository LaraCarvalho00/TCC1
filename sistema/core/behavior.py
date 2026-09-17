"""Simulação de comportamento dos nós por perfil.

Usada apenas em modo de simulação (validação do pipeline sem executar o modelo).
Os três perfis previstos no trabalho:

* ``honest``: responde correto na maior parte das vezes.
* ``malicious``: responde incorreto de forma deliberada; opcionalmente em conluio
  (todos os maliciosos apontam o mesmo valor errado para tentar enviesar o voto).
* ``unstable``: tratamento explícito — com probabilidade ``unstable_p_drop``
  não responde (voto ausente e reputação penalizada); quando responde, erra
  com alta chance e latência irregular.

``expected`` existe só para fabricar o perfil na simulação. No processo real
os nós não recebem gabarito, e o orquestrador **não** usa gabarito na reputação.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from .answer import Answer

HONEST = "honest"
MALICIOUS = "malicious"
UNSTABLE = "unstable"
PROFILES = (HONEST, MALICIOUS, UNSTABLE)


@dataclass
class BehaviorConfig:
    honest_p_correct: float = 0.9
    honest_latency_ms: tuple[int, int] = (100, 600)
    malicious_latency_ms: tuple[int, int] = (100, 600)
    malicious_collusion_value: Optional[int] = None
    unstable_p_drop: float = 0.3
    unstable_p_correct: float = 0.5
    unstable_latency_ms: tuple[int, int] = (200, 4000)


def simulate_answer(
    profile: str,
    expected: Optional[Answer],
    config: BehaviorConfig,
    rng: random.Random,
) -> tuple[Optional[Answer], int]:
    """Retorna ``(resposta, latencia_ms)`` para o perfil informado."""
    if profile == HONEST:
        latency = rng.randint(*config.honest_latency_ms)
        if rng.random() < config.honest_p_correct:
            return expected, latency
        return _wrong(expected, rng), latency

    if profile == MALICIOUS:
        latency = rng.randint(*config.malicious_latency_ms)
        if config.malicious_collusion_value is not None:
            return config.malicious_collusion_value, latency
        return _wrong(expected, rng), latency

    if profile == UNSTABLE:
        latency = rng.randint(*config.unstable_latency_ms)
        if rng.random() < config.unstable_p_drop:
            return None, latency
        if rng.random() < config.unstable_p_correct:
            return expected, latency
        return _wrong(expected, rng), latency

    raise ValueError(f"Perfil desconhecido: {profile!r}")


def _wrong(expected: Optional[Answer], rng: random.Random) -> Answer:
    """Gera um valor incorreto plausível (próximo ao esperado, quando houver)."""
    if expected is None:
        return rng.randint(0, 100)
    delta = 0
    while delta == 0:
        delta = rng.randint(-5, 5)
    base = int(expected) if isinstance(expected, float) and expected.is_integer() else expected
    return base + delta
