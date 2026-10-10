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
    s: float             # sinal: 1.0 (acerto) ou 0.0 (erro/ausente)
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
    ) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha deve estar em (0, 1].")
        if not 0.0 <= initial <= 1.0:
            raise ValueError("initial deve estar em [0, 1].")
        if mechanism not in MECHANISMS:
            raise ValueError(f"mechanism deve ser um de {MECHANISMS!r}.")

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
    def update(self, node_id: str, correct: bool, alpha: Optional[float] = None) -> ReputationUpdate:
        """Atualiza a reputação do nó e retorna o registro estruturado.

        A fórmula e os pesos utilizados são registrados no objeto retornado,
        permitindo auditoria completa de cada mudança de score.

        ``alpha`` substitui a taxa só nesta chamada (sinal de consenso, gabarito
        ou punição). Em ``ema_asymmetric`` a descida mantém a proporção
        ``alpha_down / alpha``; em ``beta`` a contagem cresce ``alpha / self.alpha``
        em vez de 1. Sem ``alpha``, o comportamento é o original.
        """
        s = 1.0 if correct else 0.0
        before = self.reputation.get(node_id, self.initial)
        rate = self.alpha if alpha is None else alpha

        if self.mechanism == "ema":
            alpha_used = rate
            after = (1.0 - rate) * before + rate * s

        elif self.mechanism == "ema_asymmetric":
            # Subida usa alpha completo; descida usa alpha_down (mais lenta).
            down = self.alpha_down if alpha is None else rate * self.alpha_down / self.alpha
            alpha_used = rate if correct else down
            after = (1.0 - alpha_used) * before + alpha_used * s

        else:  # beta — distribuição Beta com prior uniforme Beta(1,1)
            weight = 1.0 if alpha is None else rate / self.alpha
            if correct:
                self._successes[node_id] = self._successes.get(node_id, 1.0) + weight
            else:
                self._failures[node_id] = self._failures.get(node_id, 1.0) + weight
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

    def get(self, node_id: str) -> float:
        """Retorna a reputação atual do nó (ou o valor inicial se não registrado)."""
        return self.reputation.get(node_id, self.initial)

    def counts(self, node_id: str) -> tuple[float, float]:
        """Contagens ``(acertos, erros)`` do mecanismo ``beta`` (prior incluído)."""
        return self._successes.get(node_id, 1.0), self._failures.get(node_id, 1.0)

    # ------------------------------------------------------------------
    def clone(self) -> "ReputationTracker":
        """Cópia independente, para recalcular uma rodada sem efeito colateral."""
        twin = ReputationTracker(
            list(self.reputation),
            alpha=self.alpha,
            initial=self.initial,
            mechanism=self.mechanism,
            alpha_down=self.alpha_down,
        )
        twin.restore(self.snapshot())
        twin.history = {nid: list(values) for nid, values in self.history.items()}
        return twin

    def snapshot(self) -> dict:
        """Estado mínimo que reproduz a reputação (entra no hash do registro)."""
        state = {"reputation": {nid: round(value, 12) for nid, value in sorted(self.reputation.items())}}
        if self.mechanism == "beta":
            state["successes"] = {nid: round(v, 12) for nid, v in sorted(self._successes.items())}
            state["failures"] = {nid: round(v, 12) for nid, v in sorted(self._failures.items())}
        return state

    def restore(self, state: dict) -> None:
        """Adota um estado produzido por :meth:`snapshot`."""
        for nid, value in state["reputation"].items():
            self.reputation[nid] = float(value)
            self.history.setdefault(nid, [self.initial])
        if self.mechanism == "beta":
            self._successes.update({nid: float(v) for nid, v in state.get("successes", {}).items()})
            self._failures.update({nid: float(v) for nid, v in state.get("failures", {}).items()})
