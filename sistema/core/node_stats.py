"""Acumuladores de acerto/erro por nó.

Fonte de verdade: eventos persistidos de validação (CORRECT/INCORRECT).
Este objeto é um cache derivado para consulta rápida e para snapshot no
histórico de reputação. Timeout/erro/inválido não incrementam ``evaluated``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import EvaluationOutcome


@dataclass
class NodeAccuracy:
    total_evaluated: int = 0
    total_correct: int = 0
    total_incorrect: int = 0
    total_timeouts: int = 0
    total_errors: int = 0

    @property
    def accuracy(self) -> float:
        if self.total_evaluated == 0:
            return 0.0
        return self.total_correct / self.total_evaluated

    def apply_outcome(self, outcome: str) -> None:
        if outcome == EvaluationOutcome.CORRECT:
            self.total_evaluated += 1
            self.total_correct += 1
            return
        if outcome == EvaluationOutcome.INCORRECT:
            self.total_evaluated += 1
            self.total_incorrect += 1
            return
        if outcome == EvaluationOutcome.TIMEOUT:
            self.total_timeouts += 1
            return
        if outcome in {EvaluationOutcome.ERROR, EvaluationOutcome.INVALID_RESPONSE}:
            self.total_errors += 1


@dataclass
class NodeStats:
    """Cache por nó. Reconstruível a partir de ``validation_results``."""

    by_node: dict[str, NodeAccuracy] = field(default_factory=dict)

    def for_node(self, node_id: str) -> NodeAccuracy:
        if node_id not in self.by_node:
            self.by_node[node_id] = NodeAccuracy()
        return self.by_node[node_id]

    def apply(self, node_id: str, outcome: str) -> NodeAccuracy:
        stats = self.for_node(node_id)
        stats.apply_outcome(outcome)
        return stats

    def rebuild_from_results(self, results) -> None:
        """Reconstrói o cache a partir dos resultados persistidos (fonte de verdade)."""
        self.by_node.clear()
        for item in results:
            self.apply(item.node_id, item.outcome)
