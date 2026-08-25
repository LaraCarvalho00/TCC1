"""Simulação local do sistema, em processo único e sem dependências externas.

Reproduz o fluxo completo do Documento de Visão (distribuição de tarefas,
coleta de respostas, consenso, atualização de reputação e registro de métricas)
sem Docker e sem executar o modelo. Serve para validar rapidamente o mecanismo
de reputação e o consenso — a "versão mínima funcionando" combinada na reunião.

Uso:
    python -m sistema.simulate --nodes 4 --malicious 0.25 --rounds 10

Observação: em simulação o comportamento dos perfis é fabricado a partir do
gabarito. No processo real (versão em containers) os nós não recebem o gabarito.
"""

from __future__ import annotations

import argparse
import os
import random

from .core import behavior, dataset
from .core.answer import normalize
from .core.consensus import majority_consensus, weighted_consensus
from .core.metrics import MetricsLogger
from .core.reputation import ReputationTracker
from .core.schemas import NodeResponse, RoundResult

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
    )
    tracker = ReputationTracker(node_ids, alpha=args.alpha)
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

        pairs = [(r.node_id, r.answer) for r in responses]
        consensus_w, _ = weighted_consensus(pairs, tracker.weights())
        consensus_m, _ = majority_consensus(pairs)

        result = RoundResult(
            round_index=round_index,
            task_id=task["id"],
            expected=expected,
            consensus_weighted=consensus_w,
            consensus_majority=consensus_m,
            responses=responses,
        )

        for response in responses:
            correct = response.answer is not None and response.answer == expected
            reputation_before = tracker.get(response.node_id)
            reputation_after = tracker.update(response.node_id, correct)
            logger.record_node(
                round_index=round_index,
                task_id=task["id"],
                node_id=response.node_id,
                profile=response.profile,
                answer=response.answer,
                expected=expected,
                correct=correct,
                latency_ms=response.latency_ms,
                reputation_before=reputation_before,
                reputation_after=reputation_after,
            )

        logger.record_round(result, num_nodes=len(node_ids))

    run_config = {
        "nodes": args.nodes,
        "malicious_frac": args.malicious,
        "unstable_frac": args.unstable,
        "rounds": args.rounds,
        "alpha": args.alpha,
        "seed": args.seed,
        "honest_accuracy": args.honest_accuracy,
        "collusion_value": args.collusion_value,
        "profiles": profiles,
    }
    summary = logger.flush(run_config, tracker.weights(), profiles)
    _print_summary(summary, profiles, args.output)
    return summary


def _print_summary(summary: dict, profiles: dict[str, str], output_dir: str) -> None:
    print("\n=== Resumo da simulação ===")
    print(f"Rodadas: {summary['rounds']}")
    print(f"Acurácia do consenso ponderado (reputação): {summary['consensus_accuracy_weighted']:.2%}")
    print(f"Acurácia do consenso por maioria (base):     {summary['consensus_accuracy_majority']:.2%}")
    print(f"Tempo médio de resposta: {summary['mean_latency_ms']:.0f} ms")
    print("\nReputação final média por perfil:")
    for profile, value in sorted(summary["final_reputation_by_profile"].items()):
        print(f"  {profile:<10} {value:.3f}")
    print(f"\nMétricas salvas em: {output_dir}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulação local da rede de reputação.")
    parser.add_argument("--nodes", type=int, default=4, help="Número de nós (padrão: 4).")
    parser.add_argument("--malicious", type=float, default=0.25, help="Fração de nós maliciosos (0-1).")
    parser.add_argument("--unstable", type=float, default=0.0, help="Fração de nós instáveis (0-1).")
    parser.add_argument("--rounds", type=int, default=10, help="Número de rodadas/tarefas.")
    parser.add_argument("--alpha", type=float, default=0.3, help="Taxa de aprendizado da reputação (EMA).")
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
    parser.add_argument("--output", default=_DEFAULT_OUTPUT, help="Diretório de saída das métricas.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    run_simulation(parse_args())
