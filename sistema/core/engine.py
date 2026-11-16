"""Métricas de dispersão das respostas dos nós."""
from __future__ import annotations

import statistics
from typing import Optional

from .answer import normalize
from .schemas import NodeResponse


def answer_dispersion(responses: list[NodeResponse]) -> dict:
    """Ausências, valores distintos, desvio padrão, mediana e MAD das respostas."""
    numeric_answers: list[float] = []
    n_absent = 0
    for r in responses:
        if r.answer is None:
            n_absent += 1
        else:
            try:
                numeric_answers.append(float(r.answer))
            except (TypeError, ValueError):
                pass

    n_distinct = len(set(normalize(r.answer) for r in responses if r.answer is not None))
    std_answers: Optional[float] = None
    median_answers: Optional[float] = None
    mad_answers: Optional[float] = None
    if len(numeric_answers) >= 2:
        std_answers = statistics.stdev(numeric_answers)
    if numeric_answers:
        median_answers = statistics.median(numeric_answers)
        deviations = [abs(v - median_answers) for v in numeric_answers]
        mad_answers = statistics.median(deviations)
    return {
        "n_distinct_answers": n_distinct,
        "n_absent": n_absent,
        "std_answers": std_answers,
        "median_answers": median_answers,
        "mad_answers": mad_answers,
    }
