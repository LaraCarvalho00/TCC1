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
import math
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
        self._effective: dict[str, float] = dict(self.reputation)
        self.audit_locked: dict[str, bool] = {nid: False for nid in ids}
        self.audit_failures: dict[str, int] = {nid: 0 for nid in ids}
        self.audit_successes: dict[str, int] = {nid: 0 for nid in ids}
        self.audit_failure_streak: dict[str, int] = {nid: 0 for nid in ids}
        self.audit_success_streak: dict[str, int] = {nid: 0 for nid in ids}
        self.audit_last_outcome: dict[str, str] = {nid: "" for nid in ids}
        self.audit_failures_to_lock = 2
        self.audit_weight_cap = 0.10
        self.recovery_cap = 0.05

    def configure_audit(self, *, failures_to_lock: int, weight_cap: float,
                        recovery_cap: float) -> None:
        if (isinstance(failures_to_lock, bool) or not isinstance(failures_to_lock, int)
                or failures_to_lock < 1):
            raise ValueError("audit_failures_to_lock deve ser inteiro positivo.")
        if (isinstance(weight_cap, bool) or not isinstance(weight_cap, (int, float))
                or not math.isfinite(weight_cap) or not 0.0 <= weight_cap <= 1.0):
            raise ValueError("audit_weight_cap deve estar em [0, 1].")
        if (isinstance(recovery_cap, bool) or not isinstance(recovery_cap, (int, float))
                or not math.isfinite(recovery_cap) or not 0.0 <= recovery_cap <= 1.0):
            raise ValueError("recovery_cap deve estar em [0, 1].")
        self.audit_failures_to_lock = failures_to_lock
        self.audit_weight_cap = weight_cap
        self.recovery_cap = recovery_cap

    def consensus_weights(self) -> dict[str, float]:
        """Peso efetivo aplicado ao consenso, distinto do score operacional."""
        return {node: min(self._effective.get(node, score), self.audit_weight_cap)
                if self.audit_locked.get(node, False) else score
                for node, score in self.reputation.items()}

    def apply_audit_round(self, outcomes, expected_questions: int, expected_nodes: int | None = None) -> None:
        """Atualiza a trava por bloco concluído; falha parcial não libera nem cria strike."""
        node_count = expected_nodes if expected_nodes is not None else len({r.node_id for r in outcomes})
        if len(outcomes) != expected_questions * node_count:
            raise ValueError("Bloco de auditoria incompleto não pode alterar as travas.")
        by_node: dict[str, list[str]] = {}
        for item in outcomes:
            by_node.setdefault(item.node_id, []).append(item.outcome)
        from .enums import EvaluationOutcome
        if len(by_node) != node_count or any(len(items) != expected_questions for items in by_node.values()):
            raise ValueError("Bloco de auditoria não cobre todos os nós e perguntas.")
        for node_id, result_list in by_node.items():
            incorrect = result_list.count(EvaluationOutcome.INCORRECT)
            for outcome in result_list:
                if outcome == EvaluationOutcome.INCORRECT:
                    self.audit_failures[node_id] = self.audit_failures.get(node_id, 0) + 1
                    self.audit_failure_streak[node_id] = self.audit_failure_streak.get(node_id, 0) + 1
                    self.audit_success_streak[node_id] = 0
                elif outcome == EvaluationOutcome.CORRECT:
                    self.audit_successes[node_id] = self.audit_successes.get(node_id, 0) + 1
                    self.audit_success_streak[node_id] = self.audit_success_streak.get(node_id, 0) + 1
                    self.audit_failure_streak[node_id] = 0
                else:
                    self.audit_failure_streak[node_id] = 0
                    self.audit_success_streak[node_id] = 0
                self.audit_last_outcome[node_id] = outcome
            if incorrect >= self.audit_failures_to_lock:
                self.audit_locked[node_id] = True
                self._effective[node_id] = min(self.reputation[node_id], self.audit_weight_cap)
            elif (self.audit_locked.get(node_id, False)
                  and self.audit_last_outcome.get(node_id) == EvaluationOutcome.CORRECT
                  and self.audit_failure_streak.get(node_id, 0) < self.audit_failures_to_lock):
                self.audit_locked[node_id] = False
                self._effective[node_id] = self.reputation[node_id]

    def _update_effective(self, node_id: str, after: float, source: str) -> None:
        if not self.audit_locked.get(node_id, False) or source == "audit":
            self._effective[node_id] = after
            return
        before = self._effective.get(node_id, self.reputation[node_id])
        self._effective[node_id] = min(after, self.audit_weight_cap,
                                       before + self.recovery_cap if after > before else after)

    # ------------------------------------------------------------------
    def update(self, node_id: str, correct: bool, *, source: str = "operational") -> ReputationUpdate:
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
        self._update_effective(node_id, after, source)
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

    def hold(self, node_id: str, *, source: str = "operational") -> ReputationUpdate:
        """Registra ausência de sinal sem alterar EMA nem contagens Beta."""
        current = self.get(node_id)
        self.history.setdefault(node_id, [self.initial]).append(current)
        self._effective.setdefault(node_id, current)
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
