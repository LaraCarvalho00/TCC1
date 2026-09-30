"""Orquestrador central (fixo) da rede distribuída.

Responsável por, a cada rodada: distribuir a tarefa a todos os nós de forma
assíncrona (coleta concorrente via ``httpx``), agregar as respostas por consenso
(ponderado por reputação e por maioria simples), avaliar contra o gabarito,
atualizar a reputação dinâmica e registrar as métricas.

O laço de rodada é implementado em :mod:`sistema.core.engine` e compartilhado
com a simulação local, garantindo que os dois caminhos de execução sejam
estritamente comparáveis (mesma lógica de consenso, atualização e logging).

Topologia: estrela (o orquestrador possui um canal para cada nó).

Uso::

    python -m sistema.orchestrator.run --config sistema/config/experiment.yaml
"""
from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any, Optional

import httpx
import yaml

from ..core import dataset as dataset_module
from ..core.answer import normalize
from ..core.engine import process_round
from ..core.metrics import MetricsLogger
from ..core.reputation import MECHANISMS, ReputationTracker
from ..core.schedule import DEFAULT_TEST_EVERY, is_test_round, test_rounds_1based
from ..core.schemas import NodeResponse
from ..core.validation.runtime import ValidationPlan, ValidationRuntime, load_tasks as load_validation_tasks
from ..core.validation.models import NodeSpec
from ..core.validation.transport import HttpNodeClient

_DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), "..", "config", "experiment.yaml")


# ---------------------------------------------------------------------------
# Config e dataset
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_tasks(config: dict) -> list[dict]:
    source = config.get("dataset", "sample")
    limit = config.get("num_tasks")
    return load_validation_tasks(source, limit, config.get("dataset_split", config.get("split", "train")))


# ---------------------------------------------------------------------------
# Coleta de respostas via HTTP
# ---------------------------------------------------------------------------

async def query_node(
    client: httpx.AsyncClient,
    node: dict,
    task: dict,
    mode: str,
    timeout: float,
) -> NodeResponse:
    """Consulta um nó; falhas e timeouts resultam em resposta ``None``."""
    payload: dict[str, Any] = {"task_id": task["id"], "question": task["question"]}

    profile = node.get("profile", "unknown")
    try:
        response = await client.post(f"{node['url']}/infer", json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return NodeResponse(
            node_id=node["id"],
            task_id=task["id"],
            answer=normalize(data.get("answer")),
            latency_ms=int(data.get("latency_ms", 0)),
            profile=profile,
        )
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return NodeResponse(
            node_id=node["id"],
            task_id=task["id"],
            answer=None,
            latency_ms=int(timeout * 1000),
            profile=profile,
        )


async def wait_for_nodes(
    client: httpx.AsyncClient,
    nodes: list[dict],
    retries: int = 30,
    delay: float = 1.0,
) -> None:
    """Aguarda todos os nós responderem em ``/health`` antes de iniciar."""
    for node in nodes:
        for _ in range(retries):
            try:
                response = await client.get(f"{node['url']}/health", timeout=2.0)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# Laço principal
# ---------------------------------------------------------------------------

async def run_experiment(config: dict) -> dict:
    nodes: list[dict] = config["nodes"]
    node_ids = [node["id"] for node in nodes]
    profiles = {node["id"]: node.get("profile", "unknown") for node in nodes}

    tasks = load_tasks(config)
    if not tasks:
        raise RuntimeError("Nenhuma tarefa carregada.")

    rounds = config.get("rounds") or len(tasks)
    test_every = int(config.get("test_every", DEFAULT_TEST_EVERY))
    planned_tests = test_rounds_1based(rounds, test_every)
    mode = config.get("mode", "simulation")
    if mode not in {"simulation", "real"}:
        raise ValueError("mode deve ser simulation ou real.")
    if mode == "simulation" and config.get("dataset", "sample") != "sample":
        raise ValueError("HTTP mock usa sample; para GSM8K use mode=real e nós com modelo.")
    plan = ValidationPlan.prepare(
        tasks, enabled=config.get("validation_enabled", True),
        count=config.get("validation_questions", 2),
        pool_size=config.get("validation_pool_size", 5), seed=int(config.get("seed", 42)),
        test_every=test_every, source=(
            f"{config.get('dataset', 'sample')}:"
            f"{config.get('dataset_split', config.get('split', 'train')) if config.get('dataset', 'sample') == 'gsm8k' else 'bundled'}"
        ),
        audit_failures_to_lock=config.get("audit_failures_to_lock", 2),
        audit_weight_cap=config.get("audit_weight_cap", 0.10),
        recovery_cap=config.get("recovery_cap", 0.05),
        audit_timeout_policy=config.get("audit_timeout_policy", "penalize"),
        audit_timeout_strikes=config.get("audit_timeout_strikes", 3),
    )
    tasks = plan.tasks
    timeout = float(config.get("timeout_s", 10))
    output_dir = config.get("output_dir", os.path.join("sistema", "results", "experimento"))

    mechanism = config.get("reputation_mechanism", "ema")
    if mechanism not in MECHANISMS:
        raise ValueError(f"reputation_mechanism deve ser um de {MECHANISMS!r}.")
    alpha_down = config.get("alpha_down", None)
    initial = float(config.get("initial_reputation", 0.5))

    tracker = ReputationTracker(
        node_ids,
        alpha=float(config.get("alpha", 0.3)),
        initial=initial,
        mechanism=mechanism,
        alpha_down=alpha_down,
        min_confidence=float(config.get("min_confidence", 0.55)),
    )

    experiment_id = config.get("experiment_id", None)
    # Em Docker o diretório de volume pode já existir; usamos overwrite=True.
    logger = MetricsLogger(output_dir, experiment_id=experiment_id, overwrite=True)
    validation = ValidationRuntime(
        plan, tracker, logger,
        [NodeSpec(node_id=n["id"], profile=n.get("profile", "unknown"), url=n["url"]) for n in nodes],
        HttpNodeClient(timeout_s=timeout),
    )

    try:
        async with httpx.AsyncClient() as client:
            await wait_for_nodes(client, nodes)

            for round_index in range(rounds):
                task = tasks[round_index % len(tasks)]
                expected = normalize(task["answer"])
                this_is_test = is_test_round(round_index, test_every)

                responses: list[NodeResponse] = await asyncio.gather(
                    *(query_node(client, node, task, mode, timeout) for node in nodes)
                )

                result = process_round(
                    round_index=round_index,
                    task_id=task["id"],
                    expected=expected,
                    responses=list(responses),
                    tracker=tracker,
                    logger=logger,
                    is_test=this_is_test,
                )
                _print_round(result, is_test=this_is_test)
                await asyncio.to_thread(validation.after_round, round_index)
                logger.finish_round(round_index, tracker, profiles)
    except BaseException:
        # CSVs incrementais já têm todas as rodadas concluídas; fecha os streams.
        logger.close()
        raise

    config = {**config, "test_every": test_every, "test_rounds": planned_tests,
              "min_confidence": tracker.min_confidence, **plan.metadata()}
    summary = logger.flush(
        config,
        tracker,
        profiles,
        seed=config.get("seed"),
    )
    _print_summary(summary, output_dir)
    return summary


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _print_round(result, is_test: bool = False) -> None:
    status = "OK " if result.consensus_correct else "ERR"
    test_tag = " | TESTE" if is_test else ""
    print(
        f"[{status}] rodada {result.round_index + 1:>3} | tarefa {result.task_id} | "
        f"esperado={result.expected} | ponderado={result.consensus_weighted} | "
        f"maioria={result.consensus_majority}{test_tag}"
    )


def _print_summary(summary: dict, output_dir: str) -> None:
    print(f"\n=== Resumo do experimento [{summary['experiment_id']}] ===")
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
    parser = argparse.ArgumentParser(description="Orquestrador da rede de reputação.")
    parser.add_argument("--config", default=_DEFAULT_CONFIG, help="Arquivo YAML de configuração.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = load_config(args.config)
    asyncio.run(run_experiment(config))


if __name__ == "__main__":
    main()
