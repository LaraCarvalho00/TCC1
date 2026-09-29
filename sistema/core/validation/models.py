"""Entidades persistidas da rodada de validação."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..answer import Answer
from ..enums import ValidationStatus


@dataclass
class ValidationRound:
    id: str
    round_number: int
    status: str = ValidationStatus.PENDING
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    dataset_version: str = ""
    total_questions: int = 0
    total_nodes: int = 0
    seed: int = 0
    duration_s: float = 0.0
    correct_total: int = 0
    incorrect_total: int = 0
    timeout_total: int = 0
    error_total: int = 0


@dataclass
class ValidationResult:
    id: str
    validation_round_id: str
    node_id: str
    question_id: str
    node_answer: Optional[Answer]
    expected_answer: Answer
    outcome: str
    is_correct: Optional[bool]
    reputation_before: float
    reputation_after: float
    timestamp: str
    previously_correct: Optional[bool] = None
    inconsistency_detected: bool = False
    penalty_applied: bool = False


@dataclass
class NodeSpec:
    node_id: str
    profile: str = "unknown"
    url: Optional[str] = None
