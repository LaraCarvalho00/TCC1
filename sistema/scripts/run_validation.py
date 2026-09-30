"""CLI da Validation Round (isolada do consenso).

    python -m sistema.scripts.run_validation --nodes 5 --malicious 0.4 --rounds 3
"""

from __future__ import annotations

import argparse
import logging
import os
import random

from ..core import behavior
from ..core.metrics import MetricsLogger
from ..core.node_stats import NodeStats
from ..core.reputation import ReputationTracker
from ..core.reputation_history import ReputationHistoryStore
from ..core.validation.dataset import ValidationDataset
from ..core.validation.models import NodeSpec
from ..core.validation.selector import QuestionSelector
from ..core.validation.service import ValidationRoundService
from ..core.validation.store import ValidationStore
from ..core.validation.transport import SimulatedProfileClient
from ..simulate import build_profiles

_DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "results", "validation")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rodadas de validação (sem consenso).")
    parser.add_argument("--nodes", type=int, default=5)
    parser.add_argument("--malicious", type=float, default=0.4)
    parser.add_argument("--unstable", type=float, default=0.0)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--questions", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--alpha", type=float, default=0.25)
    parser.add_argument("--collusion-value", type=int, default=None)
    parser.add_argument("--output", default=_DEFAULT_OUT)
    parser.add_argument("--dataset-limit", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    out_dir = os.path.abspath(args.output)
    os.makedirs(out_dir, exist_ok=True)

    profiles = build_profiles(args.nodes, args.malicious, args.unstable)
    dataset = ValidationDataset.from_sample(limit=args.dataset_limit)
    rng = random.Random(args.seed)
    selector = QuestionSelector(dataset, rng)
    questions = selector.select(args.questions)

    expected_by_q = {item.question_id: item.expected_answer for item in dataset.questions}
    client = SimulatedProfileClient(
        profiles,
        expected_by_q,
        rng,
        behavior.BehaviorConfig(malicious_collusion_value=args.collusion_value),
    )
    tracker = ReputationTracker(list(profiles), alpha=args.alpha)
    stats = NodeStats()
    history = ReputationHistoryStore(os.path.join(out_dir, "reputation_history.csv"))
    store = ValidationStore(out_dir)
    metrics = MetricsLogger(out_dir)
    service = ValidationRoundService(
        tracker=tracker,
        client=client,
        store=store,
        history=history,
        stats=stats,
        metrics=metrics,
    )
    nodes = [NodeSpec(node_id=node_id, profile=profile) for node_id, profile in profiles.items()]

    for index in range(args.rounds):
        service.start(
            round_number=index + 1,
            nodes=nodes,
            questions=questions,
            seed=args.seed,
            dataset_version=dataset.version,
        )

    summary = metrics.flush(
        {
            "profiles": profiles,
            "rounds": args.rounds,
            "questions": args.questions,
            "seed": args.seed,
            "dataset_version": dataset.version,
            "validation_uses_ground_truth": True,
            "consensus_involved": False,
        },
        tracker.weights(),
        profiles,
    )
    print(f"Validação concluída. Saída: {out_dir}")
    for node_id, acc in sorted(stats.by_node.items()):
        print(
            f"  {node_id} ({profiles[node_id]}): "
            f"acertos={acc.total_correct} erros={acc.total_incorrect} "
            f"reputação={tracker.get(node_id):.3f}"
        )
    return summary


if __name__ == "__main__":
    main()
