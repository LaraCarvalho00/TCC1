"""Eleição do líder (orquestrador da rodada) e do auditor.

Regras:

* **Elegível** é o nó disponível: nas últimas ``window`` rodadas registradas na
  cadeia, ficou ausente no máximo ``max_absences`` vezes. A disponibilidade sai
  da cadeia, não de um aviso do próprio nó.
* **Largada**: enquanto os scores de poder dos elegíveis não se separam (maior
  menos menor abaixo de ``margin``), o papel gira em rodízio pela lista fixa de
  membros. Ninguém escolhe o líder pelo menor ``node_id``. Em um grupo só de
  nós com scores parecidos, o rodízio continua e distribui a liderança.
* **Depois da largada**: lidera o maior score elegível, excluindo quem liderou a
  rodada anterior. Empate fica com o menor ``node_id``.
* **Score de eleição**: limite inferior conservador da reputação. Em ``beta``,
  ``s / (s + f + caution)``; em EMA, a própria reputação.
* **Auditor**: maior score elegível a pelo menos 2 saltos do líder no grafo
  (na estrela, onde todos são vizinhos, é o segundo score).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional

from .topology import Graph, distances, node_sort_key

if TYPE_CHECKING:
    from .protocol import NetworkState
    from .reputation import ReputationTracker


def is_available(state: "NetworkState", node_id: str, window: int, max_absences: int) -> bool:
    recent = state.presence.get(node_id, [])[-window:]
    return recent.count(False) <= max_absences


def eligible(
    state: "NetworkState",
    members: Iterable[str],
    window: int = 5,
    max_absences: int = 1,
) -> list[str]:
    return sorted(
        (m for m in members if is_available(state, m, window, max_absences)),
        key=node_sort_key,
    )


def election_score(tracker: "ReputationTracker", node_id: str, caution: float = 2.0) -> float:
    if tracker.mechanism == "beta":
        successes, failures = tracker.counts(node_id)
        return successes / (successes + failures + caution)
    return tracker.get(node_id)


def is_bootstrap(
    state: "NetworkState",
    members: Iterable[str],
    margin: float = 0.05,
    caution: float = 2.0,
) -> bool:
    scores = [election_score(state.power, m, caution) for m in members]
    if len(scores) < 2:
        return False
    return max(scores) - min(scores) < margin


def _ranked(state: "NetworkState", candidates: Iterable[str], caution: float) -> list[str]:
    return sorted(
        candidates,
        key=lambda n: (-election_score(state.power, n, caution), node_sort_key(n)),
    )


def elect_leader(
    state: "NetworkState",
    members: Iterable[str],
    *,
    window: int = 5,
    max_absences: int = 1,
    margin: float = 0.05,
    caution: float = 2.0,
) -> tuple[Optional[str], bool]:
    """Retorna ``(líder, em_largada)`` para os membros desta cópia da cadeia."""
    ordered = sorted(members, key=node_sort_key)
    if not ordered:
        return None, False
    pool = eligible(state, ordered, window, max_absences) or ordered
    candidates = [n for n in pool if n != state.last_leader] or pool

    bootstrap = is_bootstrap(state, pool, margin, caution)
    if bootstrap:
        allowed = set(candidates)
        start = state.rotation % len(ordered)
        for offset in range(len(ordered)):
            node = ordered[(start + offset) % len(ordered)]
            if node in allowed:
                return node, True
    return _ranked(state, candidates, caution)[0], False


def pick_auditor(
    state: "NetworkState",
    members: Iterable[str],
    leader: Optional[str],
    graph: Graph,
    *,
    window: int = 5,
    max_absences: int = 1,
    caution: float = 2.0,
) -> Optional[str]:
    ordered = sorted(members, key=node_sort_key)
    others = [m for m in ordered if m != leader]
    if leader is None or not others:
        return None
    dist = distances(graph, leader, allowed=set(ordered))
    pool = [m for m in eligible(state, others, window, max_absences)]
    far = [m for m in pool if dist.get(m, len(ordered) + 1) >= 2]
    return _ranked(state, far or pool or others, caution)[0]
