"""Simulação local do sistema, em processo único e sem dependências externas.

Reproduz distribuição, coleta, consenso, reputação observável e métricas
sem Docker e sem o modelo. O gabarito só fabrica o comportamento dos perfis
e avalia o consenso; **não** entra no cálculo da reputação.

Uso:
    python -m sistema.simulate --nodes 6 --malicious 0.33 --rounds 30
    python -m sistema.scripts.run_scenarios
"""

from __future__ import annotations

import argparse
import os
import random

from .core import behavior, dataset
from .core.answer import normalize
from .core.metrics import MetricsLogger
from .core.pipeline import run_round
from .core.reputation import ReputationTracker
from .core.schemas import NodeResponse

_DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "results", "simulacao")


def build_profiles(num_nodes: int, malicious_frac: float, unstable_frac: float) -> dict[str, str]:
    """Distribui perfis entre os nós a partir das frações informadas."""
    num_malicious = round(malicious_frac * num_nodes)
    num_unstable = round(unstable_frac * num_nodes)
    if num_malicious + num_unstable > num_nodes:
        raise ValueError("Soma de nós maliciosos e instáveis excede o total de nós.")

    profiles: dict[str, str] = {}
    for index in range(num_nodes):
        node_id = f"node-{index}"
        if index < num_malicious:
            profiles[node_id] = behavior.MALICIOUS
        elif index < num_malicious + num_unstable:
            profiles[node_id] = behavior.UNSTABLE
        else:
            profiles[node_id] = behavior.HONEST
    return profiles


def run_simulation(args: argparse.Namespace) -> dict:
    rng = random.Random(args.seed)
    profiles = build_profiles(args.nodes, args.malicious, args.unstable)
    node_ids = list(profiles)

    tasks = dataset.load_sample()
    if not tasks:
        raise RuntimeError("Amostra de dataset vazia.")

    config = behavior.BehaviorConfig(
        honest_p_correct=args.honest_accuracy,
        malicious_collusion_value=args.collusion_value,
        unstable_p_drop=args.unstable_p_drop,
        unstable_p_correct=args.unstable_p_correct,
    )
    tracker = ReputationTracker(
        node_ids,
        alpha=args.alpha,
        min_confidence=args.min_confidence,
    )
    logger = MetricsLogger(args.output)

    for round_index in range(args.rounds):
        task = tasks[round_index % len(tasks)]
        expected = normalize(task["answer"])

        responses: list[NodeResponse] = []
        for node_id in node_ids:
            answer, latency = behavior.simulate_answer(profiles[node_id], expected, config, rng)
            responses.append(
                NodeResponse(
                    node_id=node_id,
                    task_id=task["id"],
                    answer=normalize(answer),
                    latency_ms=latency,
                    profile=profiles[node_id],
                )
            )

        run_round(
            round_index=round_index,
            task_id=task["id"],
            expected=expected,
            responses=responses,
            tracker=tracker,
            logger=logger,
        )

    run_config = {
        "nodes": args.nodes,
        "malicious_frac": args.malicious,
        "unstable_frac": args.unstable,
        "rounds": args.rounds,
        "alpha": args.alpha,
        "min_confidence": args.min_confidence,
        "seed": args.seed,
        "honest_accuracy": args.honest_accuracy,
        "collusion_value": args.collusion_value,
        "unstable_p_drop": args.unstable_p_drop,
        "unstable_p_correct": args.unstable_p_correct,
        "profiles": profiles,
        "reputation_uses_ground_truth": False,
        "eval_dataset": "gsm8k_sample_offline (nao usado para treinar o modelo)",
    }
    summary = logger.flush(run_config, tracker.weights(), profiles)
    _print_summary(summary, args.output)
    return summary


def _print_summary(summary: dict, output_dir: str) -> None:
    print("\n=== Resumo da simulação ===")
    print(f"Rodadas: {summary['rounds']}")
    print(f"Acurácia do consenso ponderado (reputação): {summary['consensus_accuracy_weighted']:.2%}")
    print(f"Acurácia do consenso por maioria (base):     {summary['consensus_accuracy_majority']:.2%}")
    print(f"Tempo médio de resposta: {summary['mean_latency_ms']:.0f} ms")
    print("Reputação usa ground-truth: não")
    print("\nReputação final média por perfil:")
    for profile, value in sorted(summary["final_reputation_by_profile"].items()):
        print(f"  {profile:<10} {value:.3f}")
    print(f"\nMétricas salvas em: {output_dir}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulação local da rede de reputação.")
    parser.add_argument("--nodes", type=int, default=6, help="Número de nós (padrão: 6, rede pequena).")
    parser.add_argument("--malicious", type=float, default=0.0, help="Fração de nós maliciosos (0-1).")
    parser.add_argument("--unstable", type=float, default=0.0, help="Fração de nós instáveis (0-1).")
    parser.add_argument("--rounds", type=int, default=30, help="Número de rodadas/tarefas.")
    parser.add_argument("--alpha", type=float, default=0.25, help="Taxa de aprendizado da reputação (EMA).")
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.55,
        help="Fração mínima de peso no consenso para atualizar reputação.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Semente para reprodutibilidade.")
    parser.add_argument(
        "--honest-accuracy",
        type=float,
        default=0.9,
        help="Probabilidade de acerto de um nó honesto (padrão: 0.9).",
    )
    parser.add_argument(
        "--collusion-value",
        type=int,
        default=None,
        help="Se definido, todos os maliciosos respondem este valor (conluio).",
    )
    parser.add_argument(
        "--unstable-p-drop",
        type=float,
        default=0.3,
        help="Probabilidade de o nó instável não responder.",
    )
    parser.add_argument(
        "--unstable-p-correct",
        type=float,
        default=0.5,
        help="Probabilidade de acerto do nó instável quando responde.",
    )
    parser.add_argument("--output", default=_DEFAULT_OUTPUT, help="Diretório de saída das métricas.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    run_simulation(parse_args())
