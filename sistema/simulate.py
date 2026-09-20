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


def execute_simulation(
    *,
    profiles: dict[str, str],
    rounds: int,
    seed: int,
    alpha: float = 0.25,
    min_confidence: float = 0.55,
    honest_accuracy: float = 0.9,
    collusion_value: int | None = None,
    unstable_p_drop: float = 0.3,
    unstable_p_correct: float = 0.5,
    output: str | None = None,
    persist: bool = True,
) -> dict:
    """Executa o pipeline existente (consenso + reputação) com perfis já definidos."""
    rng = random.Random(seed)
    node_ids = list(profiles)

    tasks = dataset.load_sample()
    if not tasks:
        raise RuntimeError("Amostra de dataset vazia.")

    config = behavior.BehaviorConfig(
        honest_p_correct=honest_accuracy,
        malicious_collusion_value=collusion_value,
        unstable_p_drop=unstable_p_drop,
        unstable_p_correct=unstable_p_correct,
    )
    tracker = ReputationTracker(
        node_ids,
        alpha=alpha,
        min_confidence=min_confidence,
    )
    logger = MetricsLogger(output if persist else None)

    for round_index in range(rounds):
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
        "nodes": len(profiles),
        "rounds": rounds,
        "alpha": alpha,
        "min_confidence": min_confidence,
        "seed": seed,
        "honest_accuracy": honest_accuracy,
        "collusion_value": collusion_value,
        "unstable_p_drop": unstable_p_drop,
        "unstable_p_correct": unstable_p_correct,
        "profiles": profiles,
        "reputation_uses_ground_truth": False,
        "eval_dataset": "gsm8k_sample_offline (nao usado para treinar o modelo)",
    }
    summary = logger.flush(run_config, tracker.weights(), profiles)
    summary["reputation_history"] = {node_id: list(values) for node_id, values in tracker.history.items()}
    summary["profiles"] = profiles
    return summary


def run_simulation(args: argparse.Namespace) -> dict:
    profiles = getattr(args, "profiles", None) or build_profiles(
        args.nodes, args.malicious, args.unstable
    )
    summary = execute_simulation(
        profiles=profiles,
        rounds=args.rounds,
        seed=args.seed,
        alpha=args.alpha,
        min_confidence=args.min_confidence,
        honest_accuracy=args.honest_accuracy,
        collusion_value=args.collusion_value,
        unstable_p_drop=args.unstable_p_drop,
        unstable_p_correct=args.unstable_p_correct,
        output=args.output,
        persist=True,
    )
    printable = {k: v for k, v in summary.items() if k not in {"reputation_history", "profiles"}}
    _print_summary(printable, args.output)
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
