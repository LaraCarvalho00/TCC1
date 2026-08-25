"""Orquestrador central (fixo) da rede distribuída.

Responsável por, a cada rodada: distribuir a tarefa a todos os nós de forma
assíncrona (coleta concorrente via ``httpx``), agregar as respostas por consenso
(ponderado por reputação e por maioria simples), avaliar contra o gabarito,
atualizar a reputação dinâmica e registrar as métricas.

Topologia: estrela (o orquestrador possui um canal para cada nó), correspondendo
à decisão de começar com um orquestrador fixo em uma rede bem conectada.

Uso:
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
from ..core.consensus import majority_consensus, weighted_consensus
from ..core.metrics import MetricsLogger
from ..core.reputation import ReputationTracker
from ..core.schemas import NodeResponse, RoundResult

_DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), "..", "config", "experiment.yaml")


def load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_tasks(config: dict) -> list[dict]:
    source = config.get("dataset", "sample")
    limit = config.get("num_tasks")
    if source == "gsm8k":
        return dataset_module.load_gsm8k(split=config.get("split", "test"), limit=limit)
    return dataset_module.load_sample(limit=limit)


async def query_node(
    client: httpx.AsyncClient,
    node: dict,
    task: dict,
    mode: str,
    timeout: float,
) -> NodeResponse:
    """Consulta um nó; falhas e timeouts resultam em resposta ``None``."""
    payload: dict[str, Any] = {"task_id": task["id"], "question": task["question"]}
    if mode == "simulation":
        payload["expected"] = task["answer"]

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
    except (httpx.HTTPError, ValueError):
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


async def run_experiment(config: dict) -> dict:
    nodes: list[dict] = config["nodes"]
    node_ids = [node["id"] for node in nodes]
    profiles = {node["id"]: node.get("profile", "unknown") for node in nodes}

    tasks = load_tasks(config)
    if not tasks:
        raise RuntimeError("Nenhuma tarefa carregada.")

    rounds = config.get("rounds") or len(tasks)
    mode = config.get("mode", "simulation")
    timeout = float(config.get("timeout_s", 10))
    output_dir = config.get("output_dir", os.path.join("sistema", "results", "experimento"))

    tracker = ReputationTracker(node_ids, alpha=float(config.get("alpha", 0.3)))
    logger = MetricsLogger(output_dir)

    async with httpx.AsyncClient() as client:
        await wait_for_nodes(client, nodes)

        for round_index in range(rounds):
            task = tasks[round_index % len(tasks)]
            expected = normalize(task["answer"])

            responses: list[NodeResponse] = await asyncio.gather(
                *(query_node(client, node, task, mode, timeout) for node in nodes)
            )

            pairs = [(r.node_id, r.answer) for r in responses]
            consensus_weighted, _ = weighted_consensus(pairs, tracker.weights())
            consensus_majority, _ = majority_consensus(pairs)

            result = RoundResult(
                round_index=round_index,
                task_id=task["id"],
                expected=expected,
                consensus_weighted=consensus_weighted,
                consensus_majority=consensus_majority,
                responses=list(responses),
            )

            for response in responses:
                correct = response.answer is not None and response.answer == expected
                reputation_before = tracker.get(response.node_id)
                reputation_after = tracker.update(response.node_id, correct)
                logger.record_node(
                    round_index=round_index,
                    task_id=task["id"],
                    node_id=response.node_id,
                    profile=profiles[response.node_id],
                    answer=response.answer,
                    expected=expected,
                    correct=correct,
                    latency_ms=response.latency_ms,
                    reputation_before=reputation_before,
                    reputation_after=reputation_after,
                )

            logger.record_round(result, num_nodes=len(node_ids))
            _print_round(result)

    summary = logger.flush(config, tracker.weights(), profiles)
    _print_summary(summary, output_dir)
    return summary


def _print_round(result: RoundResult) -> None:
    status = "OK " if result.consensus_correct else "ERR"
    print(
        f"[{status}] rodada {result.round_index:>3} | tarefa {result.task_id} | "
        f"esperado={result.expected} | ponderado={result.consensus_weighted} | "
        f"maioria={result.consensus_majority}"
    )


def _print_summary(summary: dict, output_dir: str) -> None:
    print("\n=== Resumo do experimento ===")
    print(f"Rodadas: {summary['rounds']}")
    print(f"Acurácia do consenso ponderado (reputação): {summary['consensus_accuracy_weighted']:.2%}")
    print(f"Acurácia do consenso por maioria (base):     {summary['consensus_accuracy_majority']:.2%}")
    print(f"Tempo médio de resposta: {summary['mean_latency_ms']:.0f} ms")
    print("\nReputação final média por perfil:")
    for profile, value in sorted(summary["final_reputation_by_profile"].items()):
        print(f"  {profile:<10} {value:.3f}")
    print(f"\nMétricas salvas em: {output_dir}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Orquestrador da rede de reputação.")
    parser.add_argument("--config", default=_DEFAULT_CONFIG, help="Caminho do arquivo de configuração YAML.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = load_config(args.config)
    asyncio.run(run_experiment(config))


if __name__ == "__main__":
    main()
