"""Persistência append-only de rounds e resultados, com idempotência."""

from __future__ import annotations

import csv
import json
import os
import time
from typing import Optional

from .models import ValidationResult, ValidationRound

RESULT_FIELDS = [
    "id",
    "validation_round_id",
    "node_id",
    "question_id",
    "node_answer",
    "expected_answer",
    "outcome",
    "is_correct",
    "reputation_before",
    "reputation_after",
    "timestamp",
    "previously_correct",
    "inconsistency_detected",
    "penalty_applied",
]


class ValidationStore:
    def __init__(self, output_dir: Optional[str] = None) -> None:
        self.output_dir = output_dir
        self.rounds: dict[str, ValidationRound] = {}
        self.results: list[ValidationResult] = []
        self._keys: set[tuple[str, str, str]] = set()
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            self._load()

    def save_round(self, round_: ValidationRound) -> None:
        self.rounds[round_.id] = round_
        if self.output_dir:
            self._rewrite_rounds()

    def get_round(self, round_id: str) -> Optional[ValidationRound]:
        return self.rounds.get(round_id)

    def result_key(self, round_id: str, node_id: str, question_id: str) -> tuple[str, str, str]:
        return (round_id, node_id, question_id)

    def find_result(self, round_id: str, node_id: str, question_id: str) -> Optional[ValidationResult]:
        key = self.result_key(round_id, node_id, question_id)
        if key not in self._keys:
            return None
        for item in self.results:
            if (
                item.validation_round_id == round_id
                and item.node_id == node_id
                and item.question_id == question_id
            ):
                return item
        return None

    def add_result(self, result: ValidationResult) -> tuple[ValidationResult, bool]:
        """Devolve ``(result, created)``. Retry devolve o existente (created=False)."""
        existing = self.find_result(result.validation_round_id, result.node_id, result.question_id)
        if existing is not None:
            return existing, False
        self.results.append(result)
        self._keys.add(self.result_key(result.validation_round_id, result.node_id, result.question_id))
        if self.output_dir:
            self._append_result(result)
        return result, True

    def results_for_node(self, node_id: str) -> list[ValidationResult]:
        return [item for item in self.results if item.node_id == node_id]

    def results_for_round(self, round_id: str) -> list[ValidationResult]:
        return [item for item in self.results if item.validation_round_id == round_id]

    def _rounds_path(self) -> str:
        return os.path.join(self.output_dir, "validation_rounds.jsonl")

    def _results_path(self) -> str:
        return os.path.join(self.output_dir, "validation_results.csv")

    def _rewrite_rounds(self) -> None:
        path = self._rounds_path()
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            for round_ in self.rounds.values():
                handle.write(json.dumps(round_.__dict__, ensure_ascii=False) + "\n")
        # Windows may briefly lock the destination while scanners read it.
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if os.name != "nt" or attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))

    def _append_result(self, result: ValidationResult) -> None:
        path = self._results_path()
        exists = os.path.isfile(path) and os.path.getsize(path) > 0
        with open(path, "a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
            if not exists:
                writer.writeheader()
            writer.writerow(
                {
                    "id": result.id,
                    "validation_round_id": result.validation_round_id,
                    "node_id": result.node_id,
                    "question_id": result.question_id,
                    "node_answer": result.node_answer,
                    "expected_answer": result.expected_answer,
                    "outcome": result.outcome,
                    "is_correct": "" if result.is_correct is None else int(result.is_correct),
                    "reputation_before": round(result.reputation_before, 6),
                    "reputation_after": round(result.reputation_after, 6),
                    "timestamp": result.timestamp,
                    "previously_correct": ""
                    if result.previously_correct is None
                    else int(result.previously_correct),
                    "inconsistency_detected": int(result.inconsistency_detected),
                    "penalty_applied": int(result.penalty_applied),
                }
            )

    def _load(self) -> None:
        rounds_path = self._rounds_path()
        if os.path.isfile(rounds_path):
            with open(rounds_path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    payload = json.loads(line)
                    round_ = ValidationRound(**payload)
                    self.rounds[round_.id] = round_
        results_path = self._results_path()
        if os.path.isfile(results_path) and os.path.getsize(results_path) > 0:
            with open(results_path, encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    is_correct = row.get("is_correct", "")
                    previously = row.get("previously_correct", "")
                    result = ValidationResult(
                        id=row["id"],
                        validation_round_id=row["validation_round_id"],
                        node_id=row["node_id"],
                        question_id=row["question_id"],
                        node_answer=_parse_answer(row.get("node_answer")),
                        expected_answer=_parse_answer(row.get("expected_answer")),
                        outcome=row["outcome"],
                        is_correct=None if is_correct == "" else bool(int(is_correct)),
                        reputation_before=float(row["reputation_before"]),
                        reputation_after=float(row["reputation_after"]),
                        timestamp=row["timestamp"],
                        previously_correct=None if previously == "" else bool(int(previously)),
                        inconsistency_detected=bool(int(row.get("inconsistency_detected") or 0)),
                        penalty_applied=bool(int(row.get("penalty_applied") or 0)),
                    )
                    self.results.append(result)
                    self._keys.add(
                        self.result_key(result.validation_round_id, result.node_id, result.question_id)
                    )


def _parse_answer(raw):
    if raw is None or raw == "":
        return None
    try:
        number = float(raw)
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return None
