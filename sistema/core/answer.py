"""Extração e normalização da resposta numérica final de um texto.

Segue a convenção do GSM8K, em que a resposta final aparece após ``####``.
Quando o marcador não existe (ex.: saída livre do modelo), usa-se o último
número presente no texto.
"""

from __future__ import annotations

import re
import math
from typing import Optional, Union

Answer = Union[int, float]


def is_numeric_answer(value) -> bool:
    """Resposta GSM8K válida: número finito, excluindo booleanos."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and (not isinstance(value, float) or math.isfinite(value)))

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def extract_final_answer(text: str) -> Optional[Answer]:
    """Retorna o número final do texto, ou ``None`` se não houver nenhum."""
    if text is None:
        return None
    cleaned = text.replace(",", "").replace("$", "")

    candidates = _NUMBER.findall(cleaned)
    if not candidates:
        return None

    chosen = candidates[-1]
    if "####" in cleaned:
        after_marker = cleaned.split("####")[-1]
        after_numbers = _NUMBER.findall(after_marker)
        if after_numbers:
            chosen = after_numbers[0]

    return _to_number(chosen)


def normalize(value: Optional[Answer]) -> Optional[Answer]:
    """Normaliza para ``int`` quando o valor for inteiro, preservando ``None``."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _to_number(raw: str) -> Answer:
    number = float(raw)
    return int(number) if number.is_integer() else number
