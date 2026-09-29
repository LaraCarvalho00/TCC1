"""Estruturas de dados trocadas entre orquestrador e nós."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

# A resposta de uma tarefa GSM8K é numérica (int quando inteira, float caso contrário).
Answer = Union[int, float]


@dataclass
class Task:
    """Tarefa distribuída aos nós.

    ``expected`` é metadado interno do avaliador/simulador. Não faz parte
    do payload HTTP enviado aos nós.
    """

    id: str
    question: str
    expected: Optional[Answer] = None


@dataclass
class NodeResponse:
    """Resposta de um nó a uma tarefa."""

    node_id: str
    task_id: str
    answer: Optional[Answer]
    latency_ms: int
    profile: str = "unknown"


@dataclass
class RoundResult:
    """Resultado consolidado de uma rodada (uma tarefa)."""

    round_index: int
    task_id: str
    expected: Optional[Answer]
    consensus_weighted: Optional[Answer]
    consensus_majority: Optional[Answer]
    responses: list[NodeResponse] = field(default_factory=list)

    @property
    def consensus_correct(self) -> bool:
        return self.expected is not None and self.consensus_weighted == self.expected

    @property
    def majority_correct(self) -> bool:
        return self.expected is not None and self.consensus_majority == self.expected
