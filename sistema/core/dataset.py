"""Carregamento das tarefas (GSM8K) usadas nos experimentos.

Duas fontes:

* ``load_sample``: amostra offline embutida no repositório (não requer download),
  para validar o pipeline rapidamente.
* ``load_gsm8k``: baixa o dataset GSM8K via biblioteca ``datasets`` da Hugging
  Face (requer instalação e acesso à internet).
"""

from __future__ import annotations

import json
import os
from typing import Optional

from .answer import extract_final_answer

_SAMPLE_PATH = os.path.join(os.path.dirname(__file__), "data", "gsm8k_sample.json")


def load_sample(limit: Optional[int] = None) -> list[dict]:
    """Carrega a amostra offline embutida."""
    with open(_SAMPLE_PATH, encoding="utf-8") as handle:
        data = json.load(handle)
    return data[:limit] if limit else data


def load_gsm8k(split: str = "test", limit: Optional[int] = None) -> list[dict]:
    """Carrega o GSM8K oficial via Hugging Face ``datasets``.

    Retorna uma lista de dicionários ``{"id", "question", "answer"}`` em que
    ``answer`` já é o valor numérico final extraído do campo de resolução.
    """
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover - depende de instalação opcional
        raise ImportError(
            "A biblioteca 'datasets' é necessária para carregar o GSM8K. "
            "Instale com: pip install -r sistema/requirements-model.txt"
        ) from exc

    dataset = load_dataset("openai/gsm8k", "main", split=split)
    tasks: list[dict] = []
    for index, row in enumerate(dataset):
        if limit is not None and index >= limit:
            break
        tasks.append(
            {
                "id": f"gsm8k-{split}-{index}",
                "question": row["question"],
                "answer": extract_final_answer(row["answer"]),
            }
        )
    return tasks
