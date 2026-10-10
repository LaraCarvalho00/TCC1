"""Simulação de comportamento dos nós por perfil.

Usada apenas em modo de simulação (validação do pipeline sem executar o modelo).
Os três perfis previstos no trabalho:

* ``honest``: responde correto na maior parte das vezes.
* ``malicious``: responde incorreto de forma deliberada; opcionalmente em conluio
  (todos os maliciosos apontam o mesmo valor errado para tentar enviesar o voto).
* ``unstable``: alta variância — pode atrasar, falhar (timeout) ou errar.

Nenhum destes recebe o ground truth no processo real; a dependência de
``expected`` aqui existe só para reproduzir o comportamento em simulação.

Com o orquestrador eleito, o nó malicioso também pode atacar quando ocupa um
papel na rodada:

* líder ``censor``          : tira do registro as respostas de quem não é do conluio.
* líder ``forge``           : infla a reputação do conluio no estado proposto.
* líder ``false_consensus`` : publica o valor do conluio como consenso.
* auditor ``false_reject``  : veta uma proposta honesta alegando forja.

Fora desses papéis, o malicioso confirma tudo o que um líder do conluio propõe,
vota como um nó honesto nas propostas honestas e, quando a correção pelo
gabarito passa por votação, vota contra ela. Se a correção é aplicada sem
votação, ele a aceita: recusar só o tiraria da rede.
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

LEADER_ATTACKS = ("none", "censor", "forge", "false_consensus")
AUDITOR_ATTACKS = ("none", "false_reject")


@dataclass(frozen=True)
class AttackConfig:
    leader_attack: str = "none"
    auditor_attack: str = "none"

    def __post_init__(self) -> None:
        if self.leader_attack not in LEADER_ATTACKS:
            raise ValueError(f"leader_attack deve ser um de {LEADER_ATTACKS!r}.")
        if self.auditor_attack not in AUDITOR_ATTACKS:
            raise ValueError(f"auditor_attack deve ser um de {AUDITOR_ATTACKS!r}.")


def leader_attack(profile: str, config: AttackConfig) -> Optional[str]:
    """Ataque aplicado pelo líder desta rodada (``None`` = proposta honesta)."""
    if profile != MALICIOUS or config.leader_attack == "none":
        return None
    return config.leader_attack


def malicious_vote(
    *,
    leader_is_colluder: bool,
    is_auditor: bool,
    honest_ok: bool,
    honest_reason: str,
    config: AttackConfig,
) -> tuple[bool, str]:
    """Voto ``(confirma, motivo)`` de um nó malicioso sobre uma proposta."""
    if leader_is_colluder:
        return True, ""
    if is_auditor and config.auditor_attack == "false_reject":
        return False, "forged"
    return honest_ok, honest_reason


def malicious_oracle_vote() -> bool:
    """O conluio vota contra a correção pelo gabarito quando ela é votada."""
    return False


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
