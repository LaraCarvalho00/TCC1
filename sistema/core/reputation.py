"""Mecanismo dinâmico de pontuação de reputação.

Cada nó possui uma reputação em ``[0, 1]`` atualizada a cada rodada por uma
média móvel exponencial (EMA):

    r <- (1 - alpha) * r + alpha * s

onde ``s = 1`` para resposta correta e ``s = 0`` para incorreta ou ausente.
O parâmetro ``alpha`` controla a velocidade de adaptação (quanto maior, mais
peso à rodada atual). Timeouts contam como resposta incorreta.
"""

from __future__ import annotations

from typing import Iterable


class ReputationTracker:
    def __init__(
        self,
        node_ids: Iterable[str],
        alpha: float = 0.3,
        initial: float = 0.5,
    ) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha deve estar em (0, 1].")
        if not 0.0 <= initial <= 1.0:
            raise ValueError("initial deve estar em [0, 1].")
        self.alpha = alpha
        self.initial = initial
        self.reputation: dict[str, float] = {node_id: initial for node_id in node_ids}
        self.history: dict[str, list[float]] = {
            node_id: [initial] for node_id in self.reputation
        }

    def update(self, node_id: str, correct: bool) -> float:
        """Atualiza e retorna a nova reputação do nó."""
        score = 1.0 if correct else 0.0
        current = self.reputation.get(node_id, self.initial)
        updated = (1.0 - self.alpha) * current + self.alpha * score
        self.reputation[node_id] = updated
        self.history.setdefault(node_id, [self.initial]).append(updated)
        return updated

    def weights(self) -> dict[str, float]:
        """Retorna uma cópia das reputações atuais (usadas como pesos)."""
        return dict(self.reputation)

    def get(self, node_id: str) -> float:
        return self.reputation.get(node_id, self.initial)
