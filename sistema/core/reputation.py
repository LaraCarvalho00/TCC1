"""Mecanismo dinâmico de reputação **sem ground-truth**.

Cada nó possui reputação em ``[0, 1]``, inicial ``0.5``, atualizada por EMA:

    r <- (1 - alpha) * r + alpha * s

O sinal ``s`` **não** compara a resposta com o gabarito. Ele vem só do que a
rede observa na rodada:

* ``s = 0`` se o nó não respondeu (timeout, queda, recusa) — tratamento do
  perfil instável;
* ``s = 1`` se a resposta coincide com o consenso ponderado da rodada
  (calculado com as reputações **anteriores**);
* ``s = 0`` se diverge desse consenso, desde que o consenso tenha confiança
  mínima (fração de peso no vencedor);
* se não há consenso confiável, a reputação **não muda** (evita gravar um
  empate ou um conluio ainda sem maioria).

O gabarito fica restrito às métricas de avaliação, depois do consenso.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .answer import Answer
from .consensus import weighted_consensus


class ReputationTracker:
    def __init__(
        self,
        node_ids: Iterable[str],
        alpha: float = 0.25,
        initial: float = 0.5,
        min_confidence: float = 0.55,
    ) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha deve estar em (0, 1].")
        if not 0.0 <= initial <= 1.0:
            raise ValueError("initial deve estar em [0, 1].")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence deve estar em [0, 1].")
        self.alpha = alpha
        self.initial = initial
        self.min_confidence = min_confidence
        self.reputation: dict[str, float] = {node_id: initial for node_id in node_ids}
        self.history: dict[str, list[float]] = {
            node_id: [initial] for node_id in self.reputation
        }

    def update(self, node_id: str, score: float) -> float:
        """Aplica EMA com ``score`` em ``[0, 1]`` e devolve a nova reputação."""
        if not 0.0 <= score <= 1.0:
            raise ValueError("score deve estar em [0, 1].")
        current = self.reputation.get(node_id, self.initial)
        updated = (1.0 - self.alpha) * current + self.alpha * score
        self.reputation[node_id] = updated
        self.history.setdefault(node_id, [self.initial]).append(updated)
        return updated

    def hold(self, node_id: str) -> float:
        """Mantém a reputação (sem sinal confiável nesta rodada)."""
        current = self.reputation.get(node_id, self.initial)
        self.history.setdefault(node_id, [self.initial]).append(current)
        return current

    def weights(self) -> dict[str, float]:
        return dict(self.reputation)

    def get(self, node_id: str) -> float:
        return self.reputation.get(node_id, self.initial)

    def peer_reference(
        self,
        pairs: list[tuple[str, Optional[Answer]]],
    ) -> tuple[Optional[Answer], float]:
        """Consenso ponderado atual e fração de peso no vencedor (confiança)."""
        answer, scores = weighted_consensus(pairs, self.weights())
        total = sum(scores.values())
        if answer is None or total <= 0:
            return None, 0.0
        return answer, scores[answer] / total

    def signal(
        self,
        answer: Optional[Answer],
        reference: Optional[Answer],
        confidence: float,
    ) -> Optional[float]:
        """Sinal observável. ``None`` significa 'não atualizar'.

        Ground-truth não entra aqui.
        """
        if answer is None:
            return 0.0
        if reference is None or confidence < self.min_confidence:
            return None
        return 1.0 if answer == reference else 0.0
