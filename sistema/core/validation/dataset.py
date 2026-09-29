"""Adapter do dataset GSM8K para o formato da Validation Round.

Reutiliza ``sistema.core.dataset``: o nó nunca recebe este objeto completo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .. import dataset as dataset_module
from ..answer import Answer, normalize, is_numeric_answer


@dataclass(frozen=True)
class ValidationQuestion:
    question_id: str
    prompt: str
    expected_answer: Answer
    dataset_version: str


class ValidationDataset:
    """Porta: lista de perguntas com gabarito só no avaliador."""

    def __init__(self, questions: list[ValidationQuestion], version: str) -> None:
        self.questions = list(questions)
        self.version = version

    def __len__(self) -> int:
        return len(self.questions)

    @classmethod
    def from_sample(cls, limit: Optional[int] = None) -> "ValidationDataset":
        rows = dataset_module.load_sample(limit=limit)
        return cls._from_rows(rows, version=f"gsm8k_sample:{limit or 'all'}")

    @classmethod
    def from_gsm8k(cls, split: str = "test", limit: Optional[int] = None) -> "ValidationDataset":
        if split == "train":
            raise ValueError("Validação usa o split de teste. Não avaliar no train do GSM8K.")
        rows = dataset_module.load_gsm8k(split=split, limit=limit)
        return cls._from_rows(rows, version=f"gsm8k-{split}:{limit or 'all'}")

    @classmethod
    def from_rows(cls, rows: list[dict], version: str = "custom") -> "ValidationDataset":
        return cls._from_rows(rows, version=version)

    @classmethod
    def _from_rows(cls, rows: list[dict], version: str) -> "ValidationDataset":
        questions = []
        for row in rows:
            expected = normalize(row.get("answer") if "answer" in row else row.get("expectedAnswer"))
            if not is_numeric_answer(expected):
                raise ValueError("Pergunta sem resposta numérica válida.")
            raw_id = row.get("id") or row.get("questionId")
            question_id = str(raw_id) if raw_id is not None else ""
            prompt = row.get("question") or row.get("prompt")
            if not question_id or not prompt:
                raise ValueError("Pergunta sem ID ou enunciado.")
            questions.append(
                ValidationQuestion(
                    question_id=question_id,
                    prompt=str(prompt),
                    expected_answer=expected,
                    dataset_version=version,
                )
            )
        if len({q.question_id for q in questions}) != len(questions):
            raise ValueError("IDs de perguntas duplicados.")
        return cls(questions, version=version)
