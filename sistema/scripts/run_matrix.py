"""Executor da matriz de experimentos para validação do mecanismo de reputação.

Roda a combinação completa de parâmetros definida no plano:

    Nós × Maliciosos × Sementes × Mecanismos × Variante de conluio

Por padrão:
    nós        : 7, 10, 15, 20
    maliciosos : 0%, 25%, 50%
    sementes   : 0 … 9  (10 repetições)
    mecanismos : ema, ema_asymmetric, beta
    conluio    : não (padrão) + sim (apenas para malicious > 0)
    teste      : uma rodada de teste a cada 10 rodadas (10, 20, 30, 40, 50)

A fração 0,65 entra na grade para o cenário de cerca de 65% de nós maliciosos.
Os resultados desta rodada ficam em ``sistema/results/matrix_testes_fixos/``
e não substituem execuções anteriores.
Tempo estimado em simulação local: ~2–4 min no total.

Uso::

    # Execução completa
    python -m sistema.scripts.run_matrix

    # Apenas EMA com 7 e 10 nós, 5 sementes, sem conluio
    python -m sistema.scripts.run_matrix \\
        --nodes 7 10 --mechanisms ema --seeds 5 --no-collusion

    # Ver progresso sem executar
    python -m sistema.scripts.run_matrix --dry-run

Saída::

    sistema/results/matrix_testes_fixos/<experiment_id>/
        per_node.csv
        rounds.csv
        reputation_history.csv
        summary.json
        manifest.json
    sistema/results/matrix_testes_fixos/matrix_index.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from typing import Optional

# Adiciona o root ao path para permitir execução direta.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sistema.core.reputation import MECHANISMS
from sistema.core.schedule import DEFAULT_TEST_EVERY, test_rounds_1based
from sistema.simulate import run_simulation
from sistema.core.validation.runtime import add_validation_arguments

_BASE_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "results", "matrix_validacao_dataset")
_INDEX_FILE = os.path.join(_BASE_OUTPUT, "matrix_index.csv")

INDEX_FIELDS = [
    "validation_enabled", "validation_questions", "validation_rounds", "validation_accuracy",
    "dataset", "dataset_limit", "min_confidence",
    "experiment_id",
    "nodes",
    "malicious_frac",
    "malicious_pct",
    "seed",
    "mechanism",
    "collusion",
    "collusion_value",
    "rounds",
    "alpha",
    "honest_accuracy",
    "test_every",
    "test_rounds",
    "n_malicious",
    "malicious_pct_actual",
    "consensus_accuracy_weighted",
    "consensus_accuracy_majority",
    "consensus_accuracy_weighted_on_tests",
    "consensus_accuracy_majority_on_tests",
    "final_rep_honest",
    "final_rep_malicious",
    "final_rep_unstable",
    "mean_rep_honest",
    "mean_rep_malicious",
    "output_dir",
    "elapsed_s",
]


# ---------------------------------------------------------------------------
# Construção da grade de experimentos
# ---------------------------------------------------------------------------

def build_grid(
    nodes_list: list[int],
    malicious_list: list[float],
    num_seeds: int,
    mechanisms: list[str],
    with_collusion: bool,
    rounds: int,
    alpha: float,
    honest_accuracy: float,
    collusion_value: int,
    test_every: int,
) -> list[dict]:
    """Retorna a lista de configurações a executar."""
    grid = []
    for n_nodes in nodes_list:
        for mal_frac in malicious_list:
            for seed in range(num_seeds):
                for mech in mechanisms:
                    # Variante sem conluio (sempre).
                    grid.append(dict(
                        nodes=n_nodes,
                        malicious_frac=mal_frac,
                        seed=seed,
                        mechanism=mech,
                        collusion=False,
                        collusion_value_arg=None,
                        rounds=rounds,
                        alpha=alpha,
                        honest_accuracy=honest_accuracy,
                        test_every=test_every,
                    ))
                    # Variante com conluio (apenas quando há maliciosos).
                    if with_collusion and mal_frac > 0:
                        grid.append(dict(
                            nodes=n_nodes,
                            malicious_frac=mal_frac,
                            seed=seed,
                            mechanism=mech,
                            collusion=True,
                            collusion_value_arg=collusion_value,
                            rounds=rounds,
                            alpha=alpha,
                            honest_accuracy=honest_accuracy,
                            test_every=test_every,
                        ))
    return grid


def _experiment_id(cfg: dict) -> str:
    import hashlib
    signature = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]
    mal_pct = int(round(cfg["malicious_frac"] * 100))
    collusion_tag = f"_col{cfg['collusion_value_arg']}" if cfg["collusion"] else ""
    return (
        f"mat_n{cfg['nodes']}_m{mal_pct:02d}"
        f"_s{cfg['seed']:02d}_{cfg['mechanism']}{collusion_tag}"
        f"_t{int(cfg.get('test_every', DEFAULT_TEST_EVERY)):02d}"
        f"_vd_{signature}"
    )


# ---------------------------------------------------------------------------
# Execução de um experimento
# ---------------------------------------------------------------------------

def _run_one(cfg: dict, base_output: str, dry_run: bool) -> Optional[dict]:
    exp_id = _experiment_id(cfg)
    output_dir = os.path.join(base_output, exp_id)

    if dry_run:
        print(f"  [DRY] {exp_id}")
        return None

    if os.path.exists(output_dir):
        print(f"  [SKIP] {exp_id} (já existe)")
        # Tentar recuperar summary do experimento existente.
        summary_path = os.path.join(output_dir, "summary.json")
        if os.path.exists(summary_path):
            with open(summary_path, encoding="utf-8") as fh:
                payload = json.load(fh)
            return {**cfg, "exp_id": exp_id, "output_dir": output_dir,
                    "summary": payload.get("summary", {}), "elapsed_s": 0.0}
        return None

    # Construir namespace compatível com simulate.parse_args().
    import argparse
    args = argparse.Namespace(
        nodes=cfg["nodes"],
        malicious=cfg["malicious_frac"],
        unstable=0.0,
        rounds=cfg["rounds"],
        alpha=cfg["alpha"],
        seed=cfg["seed"],
        honest_accuracy=cfg["honest_accuracy"],
        collusion_value=cfg["collusion_value_arg"],
        unstable_p_drop=0.3,
        unstable_p_correct=0.5,
        mechanism=cfg["mechanism"],
        alpha_down=None,
        initial_reputation=0.5,
        output=base_output,
        experiment_id=exp_id,
        overwrite=False,
        test_every=cfg.get("test_every", DEFAULT_TEST_EVERY),
        row_sync=False,
        quiet=True,
        validation_enabled=cfg.get("validation_enabled", True),
        validation_questions=cfg.get("validation_questions", 2),
        dataset=cfg.get("dataset", "sample"),
        dataset_limit=cfg.get("dataset_limit"),
        min_confidence=cfg.get("min_confidence", 0.55),
    )

    t0 = time.perf_counter()
    try:
        summary = run_simulation(args)
    except Exception as exc:
        print(f"  [ERR] {exp_id}: {exc}")
        return None
    elapsed = round(time.perf_counter() - t0, 2)

    return {
        "exp_id": exp_id,
        "output_dir": output_dir,
        "summary": summary,
        "elapsed_s": elapsed,
        **cfg,
    }


# ---------------------------------------------------------------------------
# Índice
# ---------------------------------------------------------------------------

def _index_row(result: dict) -> dict:
    cfg = result
    summ = result.get("summary", {})
    final_rep = summ.get("final_reputation_by_profile", {})
    mean_rep = summ.get("mean_reputation_by_profile_across_rounds", {})
    nodes = int(cfg.get("nodes", 0) or 0)
    mal_frac = float(cfg.get("malicious_frac", 0) or 0)
    n_malicious = int(round(mal_frac * nodes)) if nodes else 0
    mal_pct_actual = round(100.0 * n_malicious / nodes, 2) if nodes else 0
    mal_pct = int(round(mal_frac * 100))
    test_rounds = summ.get("test_rounds") or test_rounds_1based(
        int(cfg.get("rounds", 0) or 0),
        int(cfg.get("test_every", DEFAULT_TEST_EVERY)),
    )
    return {
        "experiment_id": result.get("exp_id", ""),
        "validation_enabled": int(cfg.get("validation_enabled", True)),
        "validation_questions": cfg.get("validation_questions", 2),
        "validation_rounds": "|".join(map(str, summ.get("validation_rounds", []))),
        "validation_accuracy": summ.get("validation_accuracy"),
        "dataset": cfg.get("dataset", "sample"),
        "dataset_limit": cfg.get("dataset_limit"),
        "min_confidence": cfg.get("min_confidence", 0.55),
        "nodes": cfg.get("nodes", ""),
        "malicious_frac": cfg.get("malicious_frac", ""),
        "malicious_pct": mal_pct,
        "n_malicious": n_malicious,
        "malicious_pct_actual": mal_pct_actual,
        "seed": cfg.get("seed", ""),
        "mechanism": cfg.get("mechanism", ""),
        "collusion": int(cfg.get("collusion", False)),
        "collusion_value": cfg.get("collusion_value_arg", ""),
        "rounds": cfg.get("rounds", ""),
        "alpha": cfg.get("alpha", ""),
        "honest_accuracy": cfg.get("honest_accuracy", ""),
        "test_every": cfg.get("test_every", DEFAULT_TEST_EVERY),
        "test_rounds": "|".join(str(r) for r in test_rounds),
        "consensus_accuracy_weighted": summ.get("consensus_accuracy_weighted", ""),
        "consensus_accuracy_majority": summ.get("consensus_accuracy_majority", ""),
        "consensus_accuracy_weighted_on_tests": summ.get("consensus_accuracy_weighted_on_tests", ""),
        "consensus_accuracy_majority_on_tests": summ.get("consensus_accuracy_majority_on_tests", ""),
        "final_rep_honest": final_rep.get("honest", ""),
        "final_rep_malicious": final_rep.get("malicious", ""),
        "final_rep_unstable": final_rep.get("unstable", ""),
        "mean_rep_honest": mean_rep.get("honest", ""),
        "mean_rep_malicious": mean_rep.get("malicious", ""),
        "output_dir": result.get("output_dir", ""),
        "elapsed_s": result.get("elapsed_s", ""),
    }


def _write_index(rows: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa a matriz de experimentos de reputação.",
    )
    add_validation_arguments(parser)
    parser.add_argument(
        "--nodes", type=int, nargs="+", default=[7, 10, 15, 20],
        help="Tamanhos de rede a testar.",
    )
    parser.add_argument(
        "--malicious", type=float, nargs="+", default=[0.0, 0.25, 0.5, 0.65],
        help="Frações nominais de nós maliciosos. 0.65 cobre o cenário de cerca de 65%%.",
    )
    parser.add_argument(
        "--seeds", type=int, default=10,
        help="Número de sementes (0..N-1) por célula.",
    )
    parser.add_argument(
        "--mechanisms", choices=MECHANISMS, nargs="+", default=list(MECHANISMS),
        help="Mecanismos de reputação a comparar.",
    )
    parser.add_argument(
        "--rounds", type=int, default=50,
        help="Rodadas por experimento.",
    )
    parser.add_argument(
        "--test-every", type=int, default=DEFAULT_TEST_EVERY, dest="test_every",
        help="Uma rodada de teste a cada N rodadas (igual em todos os experimentos).",
    )
    parser.add_argument(
        "--alpha", type=float, default=0.3,
        help="Taxa de aprendizado (EMA).",
    )
    parser.add_argument(
        "--honest-accuracy", type=float, default=0.9, dest="honest_accuracy",
        help="Probabilidade de acerto dos nós honestos.",
    )
    parser.add_argument(
        "--collusion-value", type=int, default=999, dest="collusion_value",
        help="Valor usado no conluio (variante com conluio).",
    )
    parser.add_argument(
        "--no-collusion", action="store_true", dest="no_collusion",
        help="Omite a variante de conluio.",
    )
    parser.add_argument(
        "--output", default=_BASE_OUTPUT,
        help="Diretório base para os resultados.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Lista os experimentos sem executar.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    os.makedirs(args.output, exist_ok=True)

    grid = build_grid(
        nodes_list=args.nodes,
        malicious_list=args.malicious,
        num_seeds=args.seeds,
        mechanisms=args.mechanisms,
        with_collusion=not args.no_collusion,
        rounds=args.rounds,
        alpha=args.alpha,
        honest_accuracy=args.honest_accuracy,
        collusion_value=args.collusion_value,
        test_every=args.test_every,
    )

    for cfg in grid:
        cfg.update(validation_enabled=args.validation_enabled,
                   validation_questions=args.validation_questions,
                   dataset=args.dataset, dataset_limit=args.dataset_limit,
                   min_confidence=args.min_confidence)
    total = len(grid)
    print(f"Matriz: {total} experimentos a executar.")
    if args.dry_run:
        for cfg in grid:
            print(f"  {_experiment_id(cfg)}")
        return

    index_rows: list[dict] = []
    t_start = time.perf_counter()

    for i, cfg in enumerate(grid, 1):
        exp_id = _experiment_id(cfg)
        print(f"[{i:>4}/{total}] {exp_id} ...", end=" ", flush=True)
        result = _run_one(cfg, args.output, dry_run=False)
        if result is not None:
            row = _index_row(result)
            index_rows.append(row)
            elapsed = result.get("elapsed_s", 0.0)
            acc_w = result.get("summary", {}).get("consensus_accuracy_weighted_on_tests", "?")
            print(f"OK {elapsed:.1f}s  acc_testes={acc_w}")
        else:
            print("✗")

    # Persiste o índice da matriz.
    index_path = os.path.join(args.output, "matrix_index.csv")
    _write_index(index_rows, index_path)

    total_time = round(time.perf_counter() - t_start, 1)
    print(f"\nConcluído: {len(index_rows)}/{total} experimentos em {total_time}s.")
    print(f"Índice salvo em: {index_path}")


if __name__ == "__main__":
    main()
