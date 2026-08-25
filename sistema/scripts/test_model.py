"""Testa um modelo de linguagem no GSM8K (tarefa definida na reunião).

Carrega o modelo (ex.: SmolLM3-3B), resolve N problemas do GSM8K e reporta a
acurácia. Requer as dependências de ``requirements-model.txt``.

Exemplo:
    python -m sistema.scripts.test_model --model HuggingFaceTB/SmolLM3-3B \\
        --dataset gsm8k --num-samples 20
"""

from __future__ import annotations

import argparse
import time

from ..core import dataset
from ..core.answer import normalize
from ..node.inference import ModelBackend


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if args.dataset == "gsm8k":
        tasks = dataset.load_gsm8k(split=args.split, limit=args.num_samples)
    else:
        tasks = dataset.load_sample(limit=args.num_samples)

    print(f"Carregando modelo: {args.model} ...")
    backend = ModelBackend(args.model, max_new_tokens=args.max_new_tokens)
    print(f"Dispositivo: {backend.device}\n")

    correct = 0
    total = len(tasks)
    started = time.perf_counter()
    for index, task in enumerate(tasks, start=1):
        predicted = backend.solve(task["question"])
        expected = normalize(task["answer"])
        is_correct = predicted is not None and normalize(predicted) == expected
        correct += int(is_correct)
        status = "OK " if is_correct else "ERR"
        print(f"[{status}] {index}/{total} | esperado={expected} | previsto={predicted}")

    elapsed = time.perf_counter() - started
    accuracy = correct / total if total else 0.0
    print(f"\nAcurácia: {accuracy:.2%} ({correct}/{total})")
    print(f"Tempo total: {elapsed:.1f}s | média por tarefa: {elapsed / total:.1f}s" if total else "")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Teste de modelo LLM no GSM8K.")
    parser.add_argument("--model", default="HuggingFaceTB/SmolLM3-3B")
    parser.add_argument("--dataset", choices=["gsm8k", "sample"], default="gsm8k")
    parser.add_argument("--split", default="test")
    parser.add_argument("--num-samples", type=int, default=20)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
