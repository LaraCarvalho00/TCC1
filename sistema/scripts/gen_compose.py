"""Gera ``docker-compose`` e config para um cenário com N nós.

Permite escalar o experimento (ex.: 5, 10 ou 20 nós) e variar a proporção de
nós maliciosos/instáveis sem editar os arquivos à mão.  Todos os parâmetros de
comportamento (acurácia dos honestos, instabilidade, conluio) e de reputação
(alpha, mecanismo, reputação inicial) são propagados como variáveis de ambiente
para os containers, garantindo que Docker e simulação local sejam comparáveis.

Exemplo::

    python -m sistema.scripts.gen_compose --nodes 10 --malicious 0.25 \\
        --honest-accuracy 0.9 --mechanism ema_asymmetric \\
        --compose-out docker-compose.generated.yml \\
        --config-out sistema/config/experiment.generated.yaml
"""
from __future__ import annotations

import argparse

import yaml

from ..core import behavior
from ..core.reputation import MECHANISMS
from ..core.schedule import DEFAULT_TEST_EVERY
from ..simulate import build_profiles


def generate(args: argparse.Namespace) -> None:
    profiles = build_profiles(args.nodes, args.malicious, args.unstable)

    services: dict[str, dict] = {}
    nodes_config: list[dict] = []

    for index, (node_id, profile) in enumerate(profiles.items()):
        # Semente por nó derivada deterministicamente da semente do experimento.
        node_seed = args.seed + index

        environment: dict[str, str] = {
            "NODE_ID": node_id,
            "PROFILE": profile,
            "INFERENCE_MODE": args.inference_mode,
            "SEED": str(node_seed),
            # Parâmetros de comportamento (propagados para todos os perfis).
            "HONEST_P_CORRECT": str(args.honest_accuracy),
            "UNSTABLE_P_DROP": str(args.unstable_p_drop),
            "UNSTABLE_P_CORRECT": str(args.unstable_p_correct),
        }

        if profile == behavior.MALICIOUS and args.collusion_value is not None:
            environment["MALICIOUS_VALUE"] = str(args.collusion_value)

        if args.inference_mode == "model":
            environment["MODEL_NAME"] = args.model

        node_service: dict = {"environment": environment}
        if args.node_image:
            node_service["image"] = args.node_image
        else:
            node_service["build"] = {"context": ".", "dockerfile": "sistema/node/Dockerfile"}
        services[node_id] = node_service
        nodes_config.append({"id": node_id, "url": f"http://{node_id}:8000", "profile": profile})

    orchestrator_service: dict = {
        "depends_on": list(profiles.keys()),
        "volumes": ["./sistema/results:/app/sistema/results"],
        "command": ["python", "-m", "sistema.orchestrator.run", "--config", args.config_out],
    }
    if args.orchestrator_image:
        orchestrator_service["image"] = args.orchestrator_image
    else:
        orchestrator_service["build"] = {"context": ".", "dockerfile": "sistema/orchestrator/Dockerfile"}
    services["orchestrator"] = orchestrator_service

    with open(args.compose_out, "w", encoding="utf-8") as handle:
        yaml.safe_dump({"services": services}, handle, sort_keys=False, allow_unicode=True)

    # Configuração do orquestrador — inclui todos os novos campos.
    config = {
        "mode": args.mode,
        "dataset": args.dataset,
        "num_tasks": args.num_tasks,
        "split": "test",
        "rounds": args.rounds,
        "test_every": args.test_every,
        "validation_enabled": args.validation_enabled,
        "validation_questions": args.validation_questions,
        "min_confidence": args.min_confidence,
        "alpha": args.alpha,
        "timeout_s": args.timeout_s,
        "output_dir": args.output_dir,
        "seed": args.seed,
        # Mecanismo de reputação.
        "reputation_mechanism": args.mechanism,
        "initial_reputation": args.initial_reputation,
        # Comportamento dos nós.
        "honest_p_correct": args.honest_accuracy,
        "unstable_p_drop": args.unstable_p_drop,
        "unstable_p_correct": args.unstable_p_correct,
        "collusion_value": args.collusion_value,
        "nodes": nodes_config,
    }
    if args.alpha_down is not None:
        config["alpha_down"] = args.alpha_down

    with open(args.config_out, "w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False, allow_unicode=True)

    counts: dict[str, int] = {}
    for profile in profiles.values():
        counts[profile] = counts.get(profile, 0) + 1
    print(f"Gerado: {args.compose_out} e {args.config_out}")
    print(f"Nós ({args.nodes}): {counts}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gerador de docker-compose para N nós.")
    # Topologia
    parser.add_argument("--nodes", type=int, default=4)
    parser.add_argument("--malicious", type=float, default=0.25, help="Fração maliciosos.")
    parser.add_argument("--unstable", type=float, default=0.0, help="Fração instáveis.")
    parser.add_argument("--seed", type=int, default=10)
    parser.add_argument("--collusion-value", type=int, default=None, dest="collusion_value")
    # Inferência
    parser.add_argument("--inference-mode", choices=["mock", "model"], default="mock")
    parser.add_argument("--model", default="HuggingFaceTB/SmolLM3-3B")
    parser.add_argument("--mode", choices=["simulation", "real"], default="simulation")
    # Dataset
    parser.add_argument("--dataset", choices=["sample", "gsm8k"], default="sample")
    parser.add_argument("--num-tasks", type=int, default=10, dest="num_tasks")
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--test-every", type=int, default=DEFAULT_TEST_EVERY)
    parser.add_argument("--validation-questions", type=int, default=2)
    parser.add_argument("--no-validation", dest="validation_enabled", action="store_false", default=True)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    # Reputação
    parser.add_argument("--alpha", type=float, default=0.3)
    parser.add_argument(
        "--mechanism", choices=MECHANISMS, default="ema",
        help="Mecanismo de reputação.",
    )
    parser.add_argument(
        "--alpha-down", type=float, default=None, dest="alpha_down",
        help="Alpha de descida (ema_asymmetric).",
    )
    parser.add_argument(
        "--initial-reputation", type=float, default=0.5, dest="initial_reputation",
    )
    # Comportamento
    parser.add_argument("--honest-accuracy", type=float, default=0.9, dest="honest_accuracy")
    parser.add_argument("--unstable-p-drop", type=float, default=0.3, dest="unstable_p_drop")
    parser.add_argument("--unstable-p-correct", type=float, default=0.5, dest="unstable_p_correct")
    parser.add_argument(
        "--node-image",
        default=None,
        dest="node_image",
        help="Imagem Docker pré-construída para os nós (evita N builds paralelos).",
    )
    parser.add_argument(
        "--orchestrator-image",
        default=None,
        dest="orchestrator_image",
        help="Imagem Docker pré-construída para o orquestrador.",
    )
    # Output
    parser.add_argument("--timeout-s", type=float, default=10.0, dest="timeout_s")
    parser.add_argument("--output-dir", default="sistema/results/experimento", dest="output_dir")
    parser.add_argument("--compose-out", default="docker-compose.generated.yml", dest="compose_out")
    parser.add_argument(
        "--config-out",
        default="sistema/config/experiment.generated.yaml",
        dest="config_out",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    generate(parse_args())
