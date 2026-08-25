"""Gera ``docker-compose`` e config para um cenário com N nós.

Permite escalar o experimento (ex.: 5, 10 ou 20 nós) e variar a proporção de
nós maliciosos/instáveis sem editar os arquivos à mão.

Exemplo:
    python -m sistema.scripts.gen_compose --nodes 10 --malicious 0.25 \\
        --compose-out docker-compose.generated.yml \\
        --config-out sistema/config/experiment.generated.yaml
"""

from __future__ import annotations

import argparse

import yaml

from ..core import behavior
from ..simulate import build_profiles


def generate(args: argparse.Namespace) -> None:
    profiles = build_profiles(args.nodes, args.malicious, args.unstable)

    services: dict[str, dict] = {}
    nodes_config: list[dict] = []
    for index, (node_id, profile) in enumerate(profiles.items()):
        environment = {
            "NODE_ID": node_id,
            "PROFILE": profile,
            "INFERENCE_MODE": args.inference_mode,
            "SEED": str(args.seed + index),
        }
        if profile == behavior.MALICIOUS and args.collusion_value is not None:
            environment["MALICIOUS_VALUE"] = str(args.collusion_value)
        if args.inference_mode == "model":
            environment["MODEL_NAME"] = args.model

        services[node_id] = {
            "build": {"context": ".", "dockerfile": "sistema/node/Dockerfile"},
            "environment": environment,
        }
        nodes_config.append({"id": node_id, "url": f"http://{node_id}:8000", "profile": profile})

    services["orchestrator"] = {
        "build": {"context": ".", "dockerfile": "sistema/orchestrator/Dockerfile"},
        "depends_on": list(profiles.keys()),
        "volumes": ["./sistema/results:/app/sistema/results"],
        "command": ["python", "-m", "sistema.orchestrator.run", "--config", args.config_out],
    }

    with open(args.compose_out, "w", encoding="utf-8") as handle:
        yaml.safe_dump({"services": services}, handle, sort_keys=False, allow_unicode=True)

    config = {
        "mode": args.mode,
        "dataset": args.dataset,
        "num_tasks": args.num_tasks,
        "split": "test",
        "rounds": args.rounds,
        "alpha": args.alpha,
        "timeout_s": args.timeout_s,
        "output_dir": args.output_dir,
        "nodes": nodes_config,
    }
    with open(args.config_out, "w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False, allow_unicode=True)

    counts: dict[str, int] = {}
    for profile in profiles.values():
        counts[profile] = counts.get(profile, 0) + 1
    print(f"Gerado: {args.compose_out} e {args.config_out}")
    print(f"Nós ({args.nodes}): {counts}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gerador de docker-compose para N nós.")
    parser.add_argument("--nodes", type=int, default=4)
    parser.add_argument("--malicious", type=float, default=0.25, help="Fração de nós maliciosos (0-1).")
    parser.add_argument("--unstable", type=float, default=0.0, help="Fração de nós instáveis (0-1).")
    parser.add_argument("--seed", type=int, default=10)
    parser.add_argument("--collusion-value", type=int, default=None)
    parser.add_argument("--inference-mode", choices=["mock", "model"], default="mock")
    parser.add_argument("--model", default="HuggingFaceTB/SmolLM3-3B")
    parser.add_argument("--mode", choices=["simulation", "real"], default="simulation")
    parser.add_argument("--dataset", choices=["sample", "gsm8k"], default="sample")
    parser.add_argument("--num-tasks", type=int, default=10)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--alpha", type=float, default=0.3)
    parser.add_argument("--timeout-s", type=float, default=10.0)
    parser.add_argument("--output-dir", default="sistema/results/experimento")
    parser.add_argument("--compose-out", default="docker-compose.generated.yml")
    parser.add_argument("--config-out", default="sistema/config/experiment.generated.yaml")
    return parser.parse_args(argv)


if __name__ == "__main__":
    generate(parse_args())
