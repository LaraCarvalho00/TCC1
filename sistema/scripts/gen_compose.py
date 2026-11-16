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

Cada nó recebe ``PEERS`` (todos os membros),
``NEIGHBORS`` (vizinhos no grafo gerado com a mesma repetição ``--seed`` da
simulação) e os parâmetros do protocolo; o orquestrador passa a ser só o
coordenador do experimento.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path, PurePosixPath

import yaml

from ..core import behavior
from ..core.defenses import preset, preset_names, with_overrides
from ..core.reputation import MECHANISMS
from ..core.schedule import DEFAULT_TEST_EVERY
from ..core.topology import KINDS, build_graph, node_sort_key
from ..simulate import ORCHESTRATIONS, build_profiles


def _dynamic_environment(
    args: argparse.Namespace,
    node_id: str,
    profile: str,
    peers: list[str],
    graph: dict,
    malicious: list[str],
) -> dict[str, str]:
    """Variáveis do orquestrador dinâmico: membros, vizinhos e protocolo."""
    environment = {
        "PEERS": ",".join(peers),
        "NEIGHBORS": ",".join(sorted(graph[node_id], key=node_sort_key)),
        "TOPOLOGY": args.topology,
        "DEGREE": str(args.degree),
        "GRAPH_SEED": str(args.seed),
        "SIGNAL": args.signal,
        "MECHANISM": args.mechanism,
        "ALPHA": str(args.alpha),
        "INITIAL_REPUTATION": str(args.initial_reputation),
        "TEST_EVERY": str(args.test_every),
        "DEFENSE": args.defense,
        "LEADER_ATTACK": args.leader_attack,
        "AUDITOR_ATTACK": args.auditor_attack,
        "EXPERIMENT_SEED": str(args.seed),
        "ROUNDS": str(args.rounds),
        "PROTOCOL_TIMEOUT_S": str(args.timeout_s),
        "CONSENSUS_MODE": args.consensus_mode,
        "CONSENSUS_CENTER": args.consensus_center,
        "VALIDATION_SCORE": args.validation_score,
        "MALICIOUS_STRATEGY": args.malicious_strategy,
        "HONEST_ROUNDS": str(args.honest_rounds),
        "AUDIT_MODE": args.audit_mode,
        "AUDIT_P": str(args.audit_p),
        "ALPHA_UP": str(args.alpha_up),
        "NOISE_MODE": args.noise_mode,
        "NOISE_DISTANCE": str(args.noise_distance),
    }
    if args.alpha_down is not None:
        environment["ALPHA_DOWN"] = str(args.alpha_down)
    for field in ("calibration_rounds", "consensus_alpha", "oracle_alpha"):
        value = getattr(args, field, None)
        if value is not None:
            environment[field.upper()] = str(value)
    if profile == behavior.MALICIOUS:
        environment["COLLUDERS"] = ",".join(malicious)
    return environment


def generate(args: argparse.Namespace) -> None:
    if args.orchestration != "dynamic":
        raise ValueError("Somente a orquestração dinâmica é suportada.")
    dedicated = args.inference_mode == "model" and bool(getattr(args, "model_run_id", ""))
    if dedicated:
        if args.model_quantization != "nf4" or args.model_device != "cuda":
            raise ValueError("O modelo dedicado requer NF4 e CUDA.")
        if args.gpu_count < 1 or args.models_per_gpu < 1 or math.ceil(args.nodes / args.gpu_count) > args.models_per_gpu:
            raise ValueError("Quantidade de modelos por GPU excede a capacidade configurada.")
        if not args.model_snapshot or not Path(args.model_snapshot).is_dir():
            raise ValueError("Informe um snapshot local do modelo em --model-snapshot.")
        cache_root = PurePosixPath(args.model_cache_root)
        if cache_root.is_absolute() or ".." in cache_root.parts or cache_root.parts[:2] != ("sistema", "results"):
            raise ValueError("O cache dedicado deve estar dentro de sistema/results.")
    with_overrides(preset(args.defense), calibration_rounds=getattr(args, "calibration_rounds", None),
                   consensus_alpha=getattr(args, "consensus_alpha", None),
                   oracle_alpha=getattr(args, "oracle_alpha", None))
    profiles = build_profiles(args.nodes, args.malicious, args.unstable)
    peers = sorted(profiles, key=node_sort_key)
    graph = build_graph(peers, args.topology, degree=args.degree, seed=args.seed)
    malicious = [n for n in peers if profiles[n] == behavior.MALICIOUS]

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
            if dedicated:
                environment.update({
                    "MODEL_NAME": "/models", "MODEL_QUANTIZATION": args.model_quantization,
                    "MODEL_DEVICE": args.model_device, "MODEL_RUN_ID": args.model_run_id,
                    "MODEL_REVISION": args.model_revision or Path(args.model_snapshot).name,
                    "MODEL_CACHE_DIR": f"/app/{cache_root.as_posix()}/{node_id}",
                    "MODEL_MAX_NEW_TOKENS": "256", "MODEL_TEMPERATURE": "0.7", "MODEL_TOP_P": "0.95",
                    "NVIDIA_DRIVER_CAPABILITIES": "compute,utility", "WEB_CONCURRENCY": "1",
                    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                })
        if args.inference_mode == "gateway":
            environment["GATEWAY_URL"] = args.gateway_url
            environment["GATEWAY_RUN_ID"] = args.gateway_run_id
        if args.max_sleep_ms is not None:
            environment["MAX_SLEEP_MS"] = str(args.max_sleep_ms)
        environment.update(_dynamic_environment(args, node_id, profile, peers, graph, malicious))

        node_service: dict = {"environment": environment}
        if args.inference_mode == "gateway":
            # Docker Engine Linux não define esse nome automaticamente.
            node_service["extra_hosts"] = ["host.docker.internal:host-gateway"]
        if args.node_image:
            node_service["image"] = args.node_image
        else:
            dockerfile = "sistema/node/Dockerfile.model" if dedicated else "sistema/node/Dockerfile"
            node_service["build"] = {"context": ".", "dockerfile": dockerfile}
        if args.mount_code:
            node_service["volumes"] = ["./sistema:/app/sistema"]
        if dedicated:
            node_service.setdefault("volumes", ["./sistema/results:/app/sistema/results"])
            node_service["volumes"].append({"type": "bind", "source": str(Path(args.model_snapshot).resolve()),
                                             "target": "/models", "read_only": True})
            node_service["deploy"] = {"resources": {"reservations": {"devices": [
                {"driver": "nvidia", "device_ids": [str(index % args.gpu_count)], "capabilities": ["gpu"]}]}}}
            node_service["command"] = ["uvicorn", "sistema.node.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
        services[node_id] = node_service
        nodes_config.append({"id": node_id, "url": f"http://{node_id}:8000", "profile": profile})

    orchestrator_service: dict = {
        "depends_on": list(profiles.keys()),
        "volumes": [
            "./sistema/results:/app/sistema/results",
            "./sistema/config:/app/sistema/config",
        ],
        "command": ["python", "-m", "sistema.orchestrator.run", "--config", args.config_out],
    }
    if args.mount_code:
        orchestrator_service["volumes"] = ["./sistema:/app/sistema"]
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
        "inference_mode": args.inference_mode,
        "task_bank": args.task_bank,
        "num_tasks": args.num_tasks,
        "split": "test",
        "rounds": args.rounds,
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
        "test_every": args.test_every,
        "consensus_mode": args.consensus_mode,
        "consensus_center": args.consensus_center,
        "validation_score": args.validation_score,
        "malicious_strategy": args.malicious_strategy,
        "honest_rounds": args.honest_rounds,
        "audit_mode": args.audit_mode,
        "audit_p": args.audit_p,
        "alpha_up": args.alpha_up,
        "nodes": nodes_config,
    }
    if args.alpha_down is not None:
        config["alpha_down"] = args.alpha_down
    for field in ("calibration_rounds", "consensus_alpha", "oracle_alpha"):
        value = getattr(args, field, None)
        if value is not None:
            config[field] = value
    if args.experiment_id:
        config["experiment_id"] = args.experiment_id
    config.update({
            "orchestration": "dynamic",
            "signal": args.signal,
            "topology": args.topology,
            "degree": args.degree,
            "defense": args.defense,
            "leader_attack": args.leader_attack,
            "auditor_attack": args.auditor_attack,
    })

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
    parser.add_argument("--inference-mode", choices=["mock", "model", "gateway"], default="mock")
    parser.add_argument("--gateway-url", default="http://host.docker.internal:8765")
    parser.add_argument("--gateway-run-id", default="")
    parser.add_argument("--noise-mode", choices=("relative", "multiplicative"), default="relative")
    parser.add_argument("--noise-distance", type=float, default=0.2)
    parser.add_argument("--model", default="HuggingFaceTB/SmolLM3-3B")
    parser.add_argument("--model-quantization", choices=("nf4",), default="nf4")
    parser.add_argument("--model-device", choices=("cuda",), default="cuda")
    parser.add_argument("--model-run-id", default="")
    parser.add_argument("--model-cache-root", default="sistema/results/model-cache")
    parser.add_argument("--model-snapshot", default="")
    parser.add_argument("--model-revision", default=None)
    parser.add_argument("--gpu-count", type=int, default=1)
    parser.add_argument("--models-per-gpu", type=int, default=1)
    parser.add_argument("--mode", choices=["simulation", "real"], default="simulation")
    # Dataset
    parser.add_argument("--dataset", choices=["sample", "gsm8k", "task_bank"], default="sample")
    parser.add_argument("--task-bank", default="sistema/dados/banco_smol.json")
    parser.add_argument("--num-tasks", type=int, default=10, dest="num_tasks")
    parser.add_argument("--rounds", type=int, default=20)
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
    parser.add_argument(
        "--mount-code", action="store_true", dest="mount_code",
        help="Monta ./sistema nos containers (usa o código atual sem rebuild).",
    )
    parser.add_argument("--max-sleep-ms", type=int, default=None, dest="max_sleep_ms",
                        help="Teto da latência simulada em cada nó.")
    parser.add_argument("--test-every", type=int, default=DEFAULT_TEST_EVERY, dest="test_every")
    # Orquestrador dinâmico
    parser.add_argument("--orchestration", choices=ORCHESTRATIONS, default="dynamic")
    parser.add_argument("--signal", choices=("truth", "consensus", "hybrid"), default="hybrid")
    parser.add_argument("--consensus-mode", choices=("exact", "distance"), default="exact")
    parser.add_argument("--consensus-center", choices=("medoid", "median", "mean"), default="medoid")
    parser.add_argument("--validation-score", choices=("exact", "graded"), default="graded")
    parser.add_argument("--malicious-strategy", choices=("always", "on_off", "knows_schedule"), default="always")
    parser.add_argument("--honest-rounds", type=int, default=5)
    parser.add_argument("--audit-mode", choices=("fixed", "random"), default="fixed")
    parser.add_argument("--audit-p", type=float, default=0.1)
    parser.add_argument("--alpha-up", type=float, default=0.1)
    parser.add_argument("--topology", choices=KINDS, default="kregular")
    parser.add_argument("--degree", type=int, default=4)
    parser.add_argument("--defense", choices=preset_names(), default="all")
    parser.add_argument("--calibration-rounds", type=int, default=None, dest="calibration_rounds")
    parser.add_argument("--consensus-alpha", type=float, default=None, dest="consensus_alpha")
    parser.add_argument("--oracle-alpha", type=float, default=None, dest="oracle_alpha")
    parser.add_argument("--leader-attack", choices=behavior.LEADER_ATTACKS, default="none", dest="leader_attack")
    parser.add_argument("--auditor-attack", choices=behavior.AUDITOR_ATTACKS, default="none", dest="auditor_attack")
    parser.add_argument("--experiment-id", default=None, dest="experiment_id")
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
