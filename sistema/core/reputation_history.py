"""Histórico append-only de atualizações de reputação.

Não sobrescreve eventos anteriores. Persistência em CSV alinhada ao restante
do simulador (sem banco relacional).
"""

from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from .enums import EvaluationOutcome, RoundKind, UpdateReason
from .node_stats import NodeAccuracy


HISTORY_FIELDS = [
    "node_id",
    "round_id",
    "round_kind",
    "reputation_before",
    "reputation_after",
    "total_correct",
    "total_incorrect",
    "total_evaluated",
    "accuracy",
    "update_reason",
    "evaluation_outcome",
    "timestamp",
]


@dataclass
class ReputationEvent:
    node_id: str
    round_id: str
    round_kind: str
    reputation_before: float
    reputation_after: float
    total_correct: int
    total_incorrect: int
    total_evaluated: int
    accuracy: float
    update_reason: str
    evaluation_outcome: str
    timestamp: str

    @classmethod
    def capture(
        cls,
        *,
        node_id: str,
        round_id: str,
        round_kind: str = RoundKind.NORMAL_TASK,
        reputation_before: float,
        reputation_after: float,
        stats: Optional[NodeAccuracy] = None,
        update_reason: str = UpdateReason.NORMAL_TASK,
        evaluation_outcome: str = EvaluationOutcome.HELD,
        timestamp: Optional[str] = None,
    ) -> "ReputationEvent":
        snapshot = stats or NodeAccuracy()
        return cls(
            node_id=node_id,
            round_id=str(round_id),
            round_kind=round_kind,
            reputation_before=reputation_before,
            reputation_after=reputation_after,
            total_correct=snapshot.total_correct,
            total_incorrect=snapshot.total_incorrect,
            total_evaluated=snapshot.total_evaluated,
            accuracy=snapshot.accuracy,
            update_reason=update_reason,
            evaluation_outcome=evaluation_outcome,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        )


class ReputationHistoryStore:
    """Append-only em memória, com flush opcional para CSV."""

    def __init__(self, output_path: Optional[str] = None) -> None:
        self.output_path = output_path
        self.events: list[ReputationEvent] = []
        if output_path and os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            self._load(output_path)

    def append(self, event: ReputationEvent) -> ReputationEvent:
        self.events.append(event)
        if self.output_path:
            self._append_csv(event)
        return event

    def for_node(self, node_id: str) -> list[ReputationEvent]:
        return [event for event in self.events if event.node_id == node_id]

    def reputation_at(self, node_id: str, round_id: str) -> Optional[float]:
        """Última reputação do nó após a rodada ``round_id`` (nessa rodada)."""
        matching = [
            event for event in self.events if event.node_id == node_id and event.round_id == str(round_id)
        ]
        if not matching:
            return None
        return matching[-1].reputation_after

    def series(self, node_id: str) -> list[tuple[str, float]]:
        return [(event.round_id, event.reputation_after) for event in self.for_node(node_id)]

    def _append_csv(self, event: ReputationEvent) -> None:
        directory = os.path.dirname(self.output_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        exists = os.path.isfile(self.output_path) and os.path.getsize(self.output_path) > 0
        with open(self.output_path, "a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HISTORY_FIELDS)
            if not exists:
                writer.writeheader()
            writer.writerow(_row(event))

    def _load(self, path: str) -> None:
        with open(path, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                self.events.append(
                    ReputationEvent(
                        node_id=row["node_id"],
                        round_id=row["round_id"],
                        round_kind=row["round_kind"],
                        reputation_before=float(row["reputation_before"]),
                        reputation_after=float(row["reputation_after"]),
                        total_correct=int(row["total_correct"]),
                        total_incorrect=int(row["total_incorrect"]),
                        total_evaluated=int(row["total_evaluated"]),
                        accuracy=float(row["accuracy"]),
                        update_reason=row["update_reason"],
                        evaluation_outcome=row["evaluation_outcome"],
                        timestamp=row["timestamp"],
                    )
                )


def _row(event: ReputationEvent) -> dict:
    payload = asdict(event)
    payload["reputation_before"] = round(event.reputation_before, 6)
    payload["reputation_after"] = round(event.reputation_after, 6)
    payload["accuracy"] = round(event.accuracy, 6)
    return payload
