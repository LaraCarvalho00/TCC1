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
gabarito. Nos pedidos HTTP os nós recebem apenas identificador e pergunta.
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
from .core.schedule import DEFAULT_TEST_EVERY, is_test_round, test_rounds_1based
from .core.schemas import NodeResponse
from .core.validation.runtime import ValidationPlan, ValidationRuntime, add_validation_arguments, load_tasks
from .core.validation.models import NodeSpec
from .core.validation.transport import SimulatedProfileClient

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
    if num_nodes < 1 or not 0 <= malicious_frac <= 1 or not 0 <= unstable_frac <= 1:
        raise ValueError("Nós deve ser positivo e frações devem estar em [0, 1].")
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

    source = getattr(args, "dataset", "sample")
    tasks = load_tasks(source, getattr(args, "dataset_limit", None))
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
        min_confidence=getattr(args, "min_confidence", 0.55),
    )

    # Experiment ID e diretório de saída.
    experiment_id = getattr(args, "experiment_id", None)
    overwrite = getattr(args, "overwrite", True)
    output_dir = args.output
    if experiment_id:
        output_dir = os.path.join(output_dir, experiment_id)

    test_every = int(getattr(args, "test_every", DEFAULT_TEST_EVERY))
    planned_tests = test_rounds_1based(args.rounds, test_every)
    plan = ValidationPlan.prepare(
        tasks, enabled=getattr(args, "validation_enabled", True),
        count=getattr(args, "validation_questions", 2), seed=args.seed,
        test_every=test_every, source=f"{source}:test",
    )
    tasks = plan.tasks
    logger = MetricsLogger(
        output_dir,
        experiment_id=experiment_id,
        overwrite=overwrite,
        row_sync=bool(getattr(args, "row_sync", True)),
    )

    validation = ValidationRuntime(
        plan, tracker, logger,
        [NodeSpec(node_id=n, profile=profiles[n]) for n in node_ids],
        SimulatedProfileClient(profiles,
                               {q.question_id: q.expected_answer for q in plan.dataset.questions},
                               random.Random(f"{args.seed}:validation-responses"), bcfg),
    )

    # Laço de rodadas.  Se interrompido, os CSVs incrementais (per_node.csv,
    # rounds.csv, reputation_history.csv) já contêm todas as rodadas concluídas.
    # A rodada de teste é fixa: uma a cada `test_every` rodadas (10, 20, 30, …).
    try:
        for round_index in range(args.rounds):
            task = tasks[round_index % len(tasks)]
            expected = normalize(task["answer"])
            this_is_test = is_test_round(round_index, test_every)

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
                is_test=this_is_test,
            )
            validation.after_round(round_index)
            logger.finish_round(round_index, tracker, profiles)
    except BaseException:
        logger.close()
        raise

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
        "test_every": test_every,
        "test_rounds": planned_tests,
        "min_confidence": tracker.min_confidence,
        **plan.metadata(),
    }
    summary = logger.flush(run_config, tracker, profiles, seed=args.seed)
    if not getattr(args, "quiet", False):
        _print_summary(summary, profiles, logger.output_dir)
    return summary


# ---------------------------------------------------------------------------
# Helpers de saída
# ---------------------------------------------------------------------------

def _print_summary(summary: dict, profiles: dict[str, str], output_dir: str) -> None:
    print(f"\n=== Resumo da simulação [{summary['experiment_id']}] ===")
    print(f"Rodadas: {summary['rounds']}")
    print(f"Rodadas de teste: {summary.get('test_rounds', [])}")
    print(f"Acurácia do consenso ponderado (todas as rodadas): {summary['consensus_accuracy_weighted']:.2%}")
    print(f"Acurácia do consenso por maioria (todas as rodadas): {summary['consensus_accuracy_majority']:.2%}")
    print(f"Acurácia do consenso ponderado (só testes): {summary.get('consensus_accuracy_weighted_on_tests', 0):.2%}")
    print(f"Acurácia do consenso por maioria (só testes): {summary.get('consensus_accuracy_majority_on_tests', 0):.2%}")
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
    add_validation_arguments(parser)
    parser.add_argument("--nodes", type=int, default=4, help="Número de nós.")
    parser.add_argument("--malicious", type=float, default=0.25, help="Fração de nós maliciosos.")
    parser.add_argument("--unstable", type=float, default=0.0, help="Fração de nós instáveis.")
    parser.add_argument("--rounds", type=int, default=10, help="Número de rodadas.")
    parser.add_argument(
        "--test-every", type=int, default=DEFAULT_TEST_EVERY, dest="test_every",
        help="Uma rodada de teste a cada N rodadas (padrão: 10 → rodadas 10, 20, 30, …).",
    )
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
    parser.add_argument(
        "--no-row-sync", action="store_false", dest="row_sync", default=True,
        help="Não sincroniza cada linha de CSV em disco (mais rápido em lote).",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    run_simulation(parse_args())
