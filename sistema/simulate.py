"""Simulação local do sistema, em processo único e sem dependências externas.

Reproduz o fluxo completo do Documento de Visão (distribuição de tarefas,
coleta de respostas, consenso, atualização de reputação e registro de métricas)
sem Docker e sem executar o modelo.  Serve para validar rapidamente o mecanismo
de reputação e o consenso — a "versão mínima funcionando" combinada na reunião.

O laço de rodada é implementado em :mod:`sistema.core.engine` e compartilhado
com o orquestrador Docker, garantindo que os dois caminhos de execução sejam
estritamente comparáveis (mesma lógica de consenso, atualização e logging).

Uso::

    python -m sistema.simulate --nodes 4 --malicious 0.25 --rounds 50

Observação: em simulação, o comportamento dos perfis é fabricado a partir do
gabarito.  No processo real (containers), os nós não recebem o gabarito.
"""
from __future__ import annotations

import argparse
import os
import random

from .core import behavior, dataset
from .core.answer import normalize
from .core.engine import process_round
from .core.metrics import MetricsLogger
from .core.reputation import MECHANISMS, ReputationTracker
from .core.schemas import NodeResponse

_DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "results", "simulacao")


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------

def build_profiles(
    num_nodes: int,
    malicious_frac: float,
    unstable_frac: float = 0.0,
) -> dict[str, str]:
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
    """Executa a simulação e retorna o resumo gerado pelo MetricsLogger."""
    rng = random.Random(args.seed)
    profiles = build_profiles(args.nodes, args.malicious, args.unstable)
    node_ids = list(profiles)

    tasks = dataset.load_sample()
    if not tasks:
        raise RuntimeError("Amostra de dataset vazia.")

    bcfg = behavior.BehaviorConfig(
        honest_p_correct=args.honest_accuracy,
        malicious_collusion_value=args.collusion_value,
        unstable_p_drop=getattr(args, "unstable_p_drop", 0.3),
        unstable_p_correct=getattr(args, "unstable_p_correct", 0.5),
    )

    # Mecanismo e parâmetros de reputação.
    mechanism = getattr(args, "mechanism", "ema")
    alpha_down = getattr(args, "alpha_down", None)
    initial = getattr(args, "initial_reputation", 0.5)
    tracker = ReputationTracker(
        node_ids,
        alpha=args.alpha,
        initial=initial,
        mechanism=mechanism,
        alpha_down=alpha_down,
    )

    # Experiment ID e diretório de saída.
    experiment_id = getattr(args, "experiment_id", None)
    overwrite = getattr(args, "overwrite", True)
    output_dir = args.output
    if experiment_id:
        output_dir = os.path.join(output_dir, experiment_id)

    logger = MetricsLogger(output_dir, experiment_id=experiment_id, overwrite=overwrite)

    # Laço de rodadas.
    for round_index in range(args.rounds):
        task = tasks[round_index % len(tasks)]
        expected = normalize(task["answer"])

        responses: list[NodeResponse] = []
        for node_id in node_ids:
            answer, latency = behavior.simulate_answer(profiles[node_id], expected, bcfg, rng)
            responses.append(
                NodeResponse(
                    node_id=node_id,
                    task_id=task["id"],
                    answer=normalize(answer),
                    latency_ms=latency,
                    profile=profiles[node_id],
                )
            )

        process_round(
            round_index=round_index,
            task_id=task["id"],
            expected=expected,
            responses=responses,
            tracker=tracker,
            logger=logger,
        )

    # Configuração que vai para o manifest / summary.
    run_config = {
        "source": "simulate",
        "nodes": args.nodes,
        "malicious_frac": args.malicious,
        "unstable_frac": args.unstable,
        "rounds": args.rounds,
        "alpha": args.alpha,
        "seed": args.seed,
        "honest_accuracy": args.honest_accuracy,
        "collusion_value": args.collusion_value,
        "mechanism": mechanism,
        "alpha_down": alpha_down,
        "initial_reputation": initial,
        "profiles": profiles,
    }
    summary = logger.flush(run_config, tracker, profiles, seed=args.seed)
    _print_summary(summary, profiles, logger.output_dir)
    return summary


# ---------------------------------------------------------------------------
# Helpers de saída
# ---------------------------------------------------------------------------

def _print_summary(summary: dict, profiles: dict[str, str], output_dir: str) -> None:
    print(f"\n=== Resumo da simulação [{summary['experiment_id']}] ===")
    print(f"Rodadas: {summary['rounds']}")
    print(f"Acurácia do consenso ponderado (reputação): {summary['consensus_accuracy_weighted']:.2%}")
    print(f"Acurácia do consenso por maioria (base):     {summary['consensus_accuracy_majority']:.2%}")
    print(f"Tempo médio de resposta: {summary['mean_latency_ms']:.0f} ms")
    print("\nReputação final média por perfil:")
    for profile, value in sorted(summary["final_reputation_by_profile"].items()):
        print(f"  {profile:<10} {value:.3f}")
    print(f"\nMétricas salvas em: {output_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulação local da rede de reputação.")
    parser.add_argument("--nodes", type=int, default=4, help="Número de nós.")
    parser.add_argument("--malicious", type=float, default=0.25, help="Fração de nós maliciosos.")
    parser.add_argument("--unstable", type=float, default=0.0, help="Fração de nós instáveis.")
    parser.add_argument("--rounds", type=int, default=10, help="Número de rodadas.")
    parser.add_argument("--alpha", type=float, default=0.3, help="Taxa de aprendizado (EMA).")
    parser.add_argument("--seed", type=int, default=42, help="Semente para reprodutibilidade.")
    parser.add_argument(
        "--honest-accuracy", type=float, default=0.9,
        help="Probabilidade de acerto de um nó honesto.",
    )
    parser.add_argument(
        "--collusion-value", type=int, default=None,
        help="Valor de conluio (todos os maliciosos respondem este valor).",
    )
    parser.add_argument(
        "--unstable-p-drop", type=float, default=0.3, dest="unstable_p_drop",
        help="Probabilidade de o nó instável descartar a resposta.",
    )
    parser.add_argument(
        "--unstable-p-correct", type=float, default=0.5, dest="unstable_p_correct",
        help="Probabilidade de acerto de um nó instável quando responde.",
    )
    parser.add_argument(
        "--mechanism", choices=MECHANISMS, default="ema",
        help="Mecanismo de reputação.",
    )
    parser.add_argument(
        "--alpha-down", type=float, default=None, dest="alpha_down",
        help="Alpha de descida para ema_asymmetric (padrão = alpha/2).",
    )
    parser.add_argument(
        "--initial-reputation", type=float, default=0.5, dest="initial_reputation",
        help="Reputação inicial de todos os nós.",
    )
    parser.add_argument("--output", default=_DEFAULT_OUTPUT, help="Diretório base de saída.")
    parser.add_argument(
        "--experiment-id", default=None, dest="experiment_id",
        help="Identificador único do experimento (auto-gerado se omitido).",
    )
    parser.add_argument(
        "--overwrite", action="store_true", default=False,
        help="Sobrescrever diretório de saída se já existir.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    run_simulation(parse_args())
