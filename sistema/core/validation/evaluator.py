"""Compara a resposta do nó com o gabarito. Nunca envia o gabarito ao nó."""

from __future__ import annotations

from typing import Optional

from ..answer import Answer, normalize
from ..enums import EvaluationOutcome
from .transport import NodeReply


class ValidationEvaluator:
    def evaluate(self, reply: NodeReply, expected: Answer) -> str:
        if reply.outcome_hint == EvaluationOutcome.TIMEOUT:
            return EvaluationOutcome.TIMEOUT
        if reply.outcome_hint == EvaluationOutcome.ERROR:
            return EvaluationOutcome.ERROR
        if reply.outcome_hint == EvaluationOutcome.INVALID_RESPONSE:
            return EvaluationOutcome.INVALID_RESPONSE
        if reply.answer is None:
            return EvaluationOutcome.INVALID_RESPONSE
        expected_n = normalize(expected)
        answer_n = normalize(reply.answer)
        if answer_n is None:
            return EvaluationOutcome.INVALID_RESPONSE
        if expected_n is None:
            return EvaluationOutcome.ERROR
        return EvaluationOutcome.CORRECT if answer_n == expected_n else EvaluationOutcome.INCORRECT

    def is_correct(self, outcome: str) -> Optional[bool]:
        if outcome == EvaluationOutcome.CORRECT:
            return True
        if outcome == EvaluationOutcome.INCORRECT:
            return False
        return None
