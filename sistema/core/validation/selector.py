"""Seleção determinística de perguntas (seed injetável)."""

from __future__ import annotations

import random

from .dataset import ValidationDataset, ValidationQuestion


class QuestionSelector:
    def __init__(self, dataset: ValidationDataset, rng: random.Random) -> None:
        self.dataset = dataset
        self.rng = rng

    def select(self, count: int) -> list[ValidationQuestion]:
        if count <= 0:
            raise ValueError("count deve ser positivo.")
        pool = list(self.dataset.questions)
        if not pool:
            raise ValueError("Dataset de validação vazio.")
        if count > len(pool):
            raise ValueError("Quantidade solicitada excede o dataset reservado.")
        if count == len(pool):
            chosen = list(pool)
            self.rng.shuffle(chosen)
            return chosen
        return self.rng.sample(pool, count)
