"""Registro de métricas do experimento em CSV e JSON.

Gera dois CSVs (um por nó/rodada e um resumo por rodada) e um JSON com a
configuração e os indicadores finais, cobrindo as variáveis dependentes do
Documento de Visão: acurácia agregada, taxa de consenso correto, tempo médio
e estabilidade da reputação.
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
    "num_responses",
    "num_nodes",
    "mean_latency_ms",
]


class MetricsLogger:
    def __init__(self, output_dir: str) -> None:
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.per_node_rows: list[dict] = []
        self.round_rows: list[dict] = []

    def record_node(
        self,
        round_index: int,
        task_id: str,
        node_id: str,
        profile: str,
        answer,
        expected,
        correct: bool,
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
                "latency_ms": latency_ms,
                "reputation_before": round(reputation_before, 4),
                "reputation_after": round(reputation_after, 4),
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
        }

    def flush(
        self,
        config: dict,
        final_reputations: dict[str, float],
        profiles: dict[str, str],
    ) -> dict:
        _write_csv(os.path.join(self.output_dir, "per_node.csv"), PER_NODE_FIELDS, self.per_node_rows)
        _write_csv(os.path.join(self.output_dir, "rounds.csv"), ROUND_FIELDS, self.round_rows)
        summary = self.summary(final_reputations, profiles)
        payload = {"config": config, "summary": summary}
        with open(os.path.join(self.output_dir, "summary.json"), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        return summary


def _ratio(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


def _write_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
