"""Mecanismo dinâmico de pontuação de reputação.

Suporta três mecanismos selecionáveis por configuração:

* ``ema``            : média móvel exponencial (EMA) simétrica — padrão original.
* ``ema_asymmetric`` : EMA com alpha distinto para subida e descida (ataca H2).
* ``beta``           : reputação bayesiana Beta(s,f) — Jøsang & Ismail (2002).

Fórmula EMA original:
    r <- (1 - alpha) * r + alpha * s
    s = 1 (acerto) | s = 0 (erro/ausente)

Decomposição explícita (válida para EMA):
    acerto : reward     = alpha * (1 - r)
    erro   : punishment = alpha * r
    delta  = reward - punishment

Cada chamada a :meth:`update` retorna um :class:`ReputationUpdate` com a
decomposição completa, eliminando a necessidade de recalcular esses valores
nos chamadores e garantindo rastreabilidade rodada a rodada.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

MECHANISMS = ("ema", "ema_asymmetric", "beta")


@dataclass
class ReputationUpdate:
    """Registro estruturado de uma atualização de reputação em uma rodada.

    Todos os campos numéricos são arredondados a 6 casas decimais para
    eliminar ruído de ponto flutuante nos CSVs sem perder precisão relevante.
    """

    node_id: str
    score_before: float
    score_after: float
    delta: float         # score_after - score_before
    reward: float        # max(0, delta)  — ganho de reputação
    punishment: float    # max(0, -delta) — perda de reputação
    alpha_used: float    # taxa efetivamente aplicada nesta rodada
    s: Optional[float]   # None = sem sinal confiável
    mechanism: str       # "ema" | "ema_asymmetric" | "beta"


class ReputationTracker:
    """Mantém e atualiza a reputação de um conjunto de nós.

    Parameters
    ----------
    node_ids : Iterable[str]
        Identificadores dos nós. A ordem define a inicialização do histórico.
    alpha : float
        Taxa de aprendizado da EMA (0 < alpha <= 1).
    initial : float
        Reputação inicial de todos os nós (padrão = 0.5).
    mechanism : str
        Algoritmo: ``"ema"``, ``"ema_asymmetric"`` ou ``"beta"``.
    alpha_down : float, optional
        Taxa de decaimento para ``ema_asymmetric``.
        Se omitido, defaults para ``alpha / 2`` (descida mais lenta que subida).
    """

    def __init__(
        self,
        node_ids: Iterable[str],
        alpha: float = 0.3,
        initial: float = 0.5,
        mechanism: str = "ema",
        alpha_down: Optional[float] = None,
        min_confidence: float = 0.55,
    ) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha deve estar em (0, 1].")
        if not 0.0 <= initial <= 1.0:
            raise ValueError("initial deve estar em [0, 1].")
        if mechanism not in MECHANISMS:
            raise ValueError(f"mechanism deve ser um de {MECHANISMS!r}.")
        if not 0 <= min_confidence <= 1:
            raise ValueError("min_confidence deve estar em [0, 1].")
        if alpha_down is not None and not 0 < alpha_down <= 1:
            raise ValueError("alpha_down deve estar em (0, 1].")
        self.min_confidence = min_confidence

        self.alpha = alpha
        self.alpha_down: float = alpha_down if alpha_down is not None else alpha / 2.0
        self.initial = initial
        self.mechanism = mechanism

        ids = list(node_ids)
        self.reputation: dict[str, float] = {nid: initial for nid in ids}
        self.history: dict[str, list[float]] = {nid: [initial] for nid in ids}

        # Para o mecanismo beta: contagens explícitas de acertos/erros.
        # Prior Beta(1, 1) corresponde a reputação inicial = 0.5.
        self._successes: dict[str, float] = {nid: 1.0 for nid in ids}
        self._failures: dict[str, float] = {nid: 1.0 for nid in ids}

    # ------------------------------------------------------------------
    def update(self, node_id: str, correct: bool) -> ReputationUpdate:
        """Atualiza a reputação do nó e retorna o registro estruturado.

        A fórmula e os pesos utilizados são registrados no objeto retornado,
        permitindo auditoria completa de cada mudança de score.
        """
        s = 1.0 if correct else 0.0
        before = self.reputation.get(node_id, self.initial)

        if self.mechanism == "ema":
            alpha_used = self.alpha
            after = (1.0 - self.alpha) * before + self.alpha * s

        elif self.mechanism == "ema_asymmetric":
            # Subida usa alpha completo; descida usa alpha_down (mais lenta).
            alpha_used = self.alpha if correct else self.alpha_down
            after = (1.0 - alpha_used) * before + alpha_used * s

        else:  # beta — distribuição Beta com prior uniforme Beta(1,1)
            if correct:
                self._successes[node_id] = self._successes.get(node_id, 1.0) + 1.0
            else:
                self._failures[node_id] = self._failures.get(node_id, 1.0) + 1.0
            s_cnt = self._successes.get(node_id, 1.0)
            f_cnt = self._failures.get(node_id, 1.0)
            after = s_cnt / (s_cnt + f_cnt)
            # alpha_used como taxa efetiva: fração do gap coberta neste update.
            gap = abs(s - before)
            alpha_used = abs(after - before) / max(gap, 1e-9)

        self.reputation[node_id] = after
        self.history.setdefault(node_id, [self.initial]).append(after)

        delta = after - before
        return ReputationUpdate(
            node_id=node_id,
            score_before=round(before, 6),
            score_after=round(after, 6),
            delta=round(delta, 6),
            reward=round(max(0.0, delta), 6),
            punishment=round(max(0.0, -delta), 6),
            alpha_used=round(alpha_used, 6),
            s=s,
            mechanism=self.mechanism,
        )

    # ------------------------------------------------------------------
    def weights(self) -> dict[str, float]:
        """Retorna uma cópia das reputações atuais (usadas como pesos no consenso)."""
        return dict(self.reputation)

    def hold(self, node_id: str) -> ReputationUpdate:
        """Registra ausência de sinal sem alterar EMA nem contagens Beta."""
        current = self.get(node_id)
        self.history.setdefault(node_id, [self.initial]).append(current)
        return ReputationUpdate(node_id, current, current, 0.0, 0.0, 0.0,
                                0.0, None, self.mechanism)

    def signal(self, answer, reference, confidence: float) -> Optional[bool]:
        """Sinal operacional baseado somente nas respostas observadas."""
        if answer is None:
            return False
        if reference is None or confidence < self.min_confidence:
            return None
        return answer == reference

    def get(self, node_id: str) -> float:
        """Retorna a reputação atual do nó (ou o valor inicial se não registrado)."""
        return self.reputation.get(node_id, self.initial)
