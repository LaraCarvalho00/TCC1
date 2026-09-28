"""Calendário fixo das rodadas de teste.

A avaliação deixa de depender de uma rodada sorteada. Em todos os experimentos
vale a mesma regra: uma rodada de teste a cada ``test_every`` rodadas.

A numeração exposta nos resultados e nos gráficos é 1-based (rodadas 10, 20,
30, …). O índice interno do laço continua 0-based.
"""
from __future__ import annotations

DEFAULT_TEST_EVERY = 10


def is_test_round(round_index: int, test_every: int = DEFAULT_TEST_EVERY) -> bool:
    """Indica se a rodada 0-based ``round_index`` é uma rodada de teste."""
    if test_every < 1:
        raise ValueError("test_every deve ser um inteiro >= 1.")
    return (round_index + 1) % test_every == 0


def test_rounds_1based(num_rounds: int, test_every: int = DEFAULT_TEST_EVERY) -> list[int]:
    """Lista as rodadas de teste em numeração 1-based."""
    if num_rounds < 0:
        raise ValueError("num_rounds deve ser >= 0.")
    return [index + 1 for index in range(num_rounds) if is_test_round(index, test_every)]
