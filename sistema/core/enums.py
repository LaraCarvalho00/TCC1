"""Constantes de domínio (mesmo padrão de ``behavior.HONEST``).

Evita strings mágicas em histórico, validação e métricas.
"""

from __future__ import annotations


class UpdateReason:
    NORMAL_TASK = "NORMAL_TASK"
    VALIDATION_ROUND = "VALIDATION_ROUND"
    INCONSISTENCY = "INCONSISTENCY"


class RoundKind:
    NORMAL_TASK = "NORMAL_TASK"
    VALIDATION_ROUND = "VALIDATION_ROUND"


class ValidationStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EvaluationOutcome:
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    HELD = "HELD"
