"""Registro de métricas do experimento em CSV e JSON.

O gabarito (``expected`` / ``correct``) entra **só** nestes arquivos, para a
avaliação científica. A coluna ``reputation_score`` é o sinal que de fato
alimentou a reputação (acordo com o consenso ou 0 em ausência de resposta).
"""

from __future__ import annotations

import csv
import json
import os
import statistics
from typing import Optional

from .schemas import RoundResult

PER_NODE_FIELDS = [
    "round_index",
    "task_id",
    "node_id",
    "profile",
    "answer",
    "expected",
    "correct",
    "agreed",
    "reputation_score",
    "latency_ms",
    "reputation_before",
    "reputation_after",
]

ROUND_FIELDS = [
    "round_index",
    "task_id",
    "expected",
    "consensus_weighted",
    "consensus_correct",
    "consensus_majority",
    "majority_correct",
    "consensus_confidence",
    "num_responses",
    "num_nodes",
    "mean_latency_ms",
]


class MetricsLogger:
    def __init__(self, output_dir: Optional[str] = None) -> None:
        self.output_dir = output_dir
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        self.per_node_rows: list[dict] = []
        self.round_rows: list[dict] = []
        self.validation_rows: list[dict] = []

    def record_node(
        self,
        round_index: int,
        task_id: str,
        node_id: str,
        profile: str,
        answer,
        expected,
        correct: bool,
        agreed: Optional[bool],
        reputation_score: Optional[float],
        latency_ms: int,
        reputation_before: float,
        reputation_after: float,
    ) -> None:
        self.per_node_rows.append(
            {
                "round_index": round_index,
                "task_id": task_id,
                "node_id": node_id,
                "profile": profile,
                "answer": answer,
                "expected": expected,
                "correct": int(correct),
                "agreed": "" if agreed is None else int(agreed),
                "reputation_score": "" if reputation_score is None else round(reputation_score, 4),
                "latency_ms": latency_ms,
                "reputation_before": round(reputation_before, 4),
                "reputation_after": round(reputation_after, 4),
            }
        )

    def record_validation(
        self,
        *,
        round_id: str,
        duration_s: float,
        questions_total: int,
        correct_total: int,
        incorrect_total: int,
        timeout_total: int,
        node_stats: Optional[dict] = None,
        reputations: Optional[dict[str, float]] = None,
    ) -> None:
        self.validation_rows.append(
            {
                "validation_round_id": round_id,
                "validation_round_duration": duration_s,
                "validation_questions_total": questions_total,
                "validation_correct_total": correct_total,
                "validation_incorrect_total": incorrect_total,
                "validation_timeout_total": timeout_total,
                "node_accuracy": (node_stats or {}),
                "node_reputation": (reputations or {}),
            }
        )

    def record_round(self, result: RoundResult, num_nodes: int) -> None:
        latencies = [r.latency_ms for r in result.responses if r.answer is not None]
        mean_latency = round(statistics.mean(latencies), 1) if latencies else 0.0
        self.round_rows.append(
            {
                "round_index": result.round_index,
                "task_id": result.task_id,
                "expected": result.expected,
                "consensus_weighted": result.consensus_weighted,
                "consensus_correct": int(result.consensus_correct),
                "consensus_majority": result.consensus_majority,
                "majority_correct": int(result.majority_correct),
                "consensus_confidence": result.consensus_confidence,
                "num_responses": len(latencies),
                "num_nodes": num_nodes,
                "mean_latency_ms": mean_latency,
            }
        )

    def summary(self, final_reputations: dict[str, float], profiles: dict[str, str]) -> dict:
        rounds = len(self.round_rows)
        consensus_correct = sum(r["consensus_correct"] for r in self.round_rows)
        majority_correct = sum(r["majority_correct"] for r in self.round_rows)
        latencies = [r["latency_ms"] for r in self.per_node_rows if r["answer"] is not None]

        by_profile: dict[str, list[float]] = {}
        for node_id, reputation in final_reputations.items():
            by_profile.setdefault(profiles.get(node_id, "unknown"), []).append(reputation)
        mean_rep_by_profile = {
            profile: round(statistics.mean(values), 4)
            for profile, values in by_profile.items()
        }

        return {
            "rounds": rounds,
            "consensus_accuracy_weighted": _ratio(consensus_correct, rounds),
            "consensus_accuracy_majority": _ratio(majority_correct, rounds),
            "mean_latency_ms": round(statistics.mean(latencies), 1) if latencies else 0.0,
            "final_reputation_by_profile": mean_rep_by_profile,
            "final_reputation_by_node": {k: round(v, 4) for k, v in final_reputations.items()},
            "reputation_uses_ground_truth": False,
            "validation": self._validation_summary(),
        }

    def _validation_summary(self) -> dict:
        if not self.validation_rows:
            return {}
        return {
            "rounds": len(self.validation_rows),
            "validation_round_duration": [row["validation_round_duration"] for row in self.validation_rows],
            "validation_questions_total": sum(row["validation_questions_total"] for row in self.validation_rows),
            "validation_correct_total": sum(row["validation_correct_total"] for row in self.validation_rows),
            "validation_incorrect_total": sum(row["validation_incorrect_total"] for row in self.validation_rows),
            "validation_timeout_total": sum(row["validation_timeout_total"] for row in self.validation_rows),
            "node_accuracy": self.validation_rows[-1]["node_accuracy"],
            "node_reputation": self.validation_rows[-1]["node_reputation"],
        }

    def flush(
        self,
        config: dict,
        final_reputations: dict[str, float],
        profiles: dict[str, str],
    ) -> dict:
        if self.output_dir:
            _write_csv(os.path.join(self.output_dir, "per_node.csv"), PER_NODE_FIELDS, self.per_node_rows)
            _write_csv(os.path.join(self.output_dir, "rounds.csv"), ROUND_FIELDS, self.round_rows)
        summary = self.summary(final_reputations, profiles)
        if self.output_dir:
            payload = {"config": config, "summary": summary}
            with open(os.path.join(self.output_dir, "summary.json"), "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
            if self.validation_rows:
                with open(os.path.join(self.output_dir, "validation_metrics.json"), "w", encoding="utf-8") as handle:
                    json.dump(self.validation_rows, handle, indent=2, ensure_ascii=False)
        return summary


def _ratio(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


def _write_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
