"""Executor da matriz de experimentos para validação do mecanismo de reputação.

Roda a combinação completa de parâmetros definida no plano:

    Nós × Maliciosos × Repetições × Mecanismos × Variante de conluio

Por padrão:
    nós        : 7, 10, 15, 20
    maliciosos : 0%, 25%, 50%
    repetições : 0 … 9  (10 repetições, parâmetro ``seed``)
    mecanismos : ema, ema_asymmetric, beta
    conluio    : não (padrão) + sim (apenas para malicious > 0)
    teste      : uma rodada de teste a cada 10 rodadas (10, 20, 30, 40, 50)

A fração 0,65 entra na grade para o cenário de cerca de 65% de nós maliciosos.
Os resultados desta rodada ficam em ``sistema/results/matrix_testes_fixos/``
e não substituem execuções anteriores.
Tempo estimado em simulação local: ~2–4 min no total.

Plano ``dynamic`` (orquestrador eleito a cada rodada), salvo em
``sistema/results/matrix_orquestrador_dinamico/``, com seis blocos:

* ``main``      : grafo 4-regular, sinal híbrido, todas as defesas, cada ataque
                  do líder; nós 7, 10, 20; maliciosos 0, 25, 50 e 65% em conluio.
* ``consensus`` : mesmo recorte com sinal de consenso puro (sem juiz).
* ``auditor``   : auditor malicioso que veta rodadas honestas (``false_reject``),
                  25% e 50%, sem defesas e com todas.
* ``ablation``  : 50% e 65% em 20 nós e 0,65 nominal em 7 nós (71%), cada preset
                  de defesa, ataques ``forge`` e ``censor``.
* ``scale``     : 25% maliciosos, 7 a 120 nós, estrela vs 4-regular.
* ``reference`` : orquestrador fixo com gabarito nas mesmas células.

Uso::

    # Execução completa
    python -m sistema.scripts.run_matrix

    # Apenas EMA com 7 e 10 nós, 5 repetições, sem conluio
    python -m sistema.scripts.run_matrix \\
        --nodes 7 10 --mechanisms ema --seeds 5 --no-collusion

    # Rodada de testes do orquestrador eleito
    python -m sistema.scripts.run_matrix --plan dynamic --seeds 5

    # Ver progresso sem executar
    python -m sistema.scripts.run_matrix --dry-run

Saída::

    sistema/results/matrix_testes_fixos/<experiment_id>/
        per_node.csv
        rounds.csv
        reputation_history.csv
        leadership.csv          (só com orquestrador eleito)
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

from sistema.core.behavior import LEADER_ATTACKS
from sistema.core.defenses import preset_names
from sistema.core.reputation import MECHANISMS
from sistema.core.schedule import DEFAULT_TEST_EVERY, test_rounds_1based
from sistema.simulate import run_simulation

_RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
_BASE_OUTPUT = os.path.join(_RESULTS, "matrix_testes_fixos")
_DYNAMIC_OUTPUT = os.path.join(_RESULTS, "matrix_orquestrador_dinamico")
_INDEX_FILE = os.path.join(_BASE_OUTPUT, "matrix_index.csv")

# Valores que mantêm o experimento idêntico à matriz original.
_CLASSIC = dict(
    orchestration="fixed", signal="truth", topology="star", degree=4,
    leader_attack="none", auditor_attack="none", defense="none", block="classic",
)

INDEX_FIELDS = [
    "experiment_id",
    "block",
    "nodes",
    "malicious_frac",
    "malicious_pct",
    "seed",
    "mechanism",
    "collusion",
    "collusion_value",
    "orchestration",
    "signal",
    "topology",
    "degree",
    "leader_attack",
    "auditor_attack",
    "defense",
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
    "recovery_round",
    "final_rep_honest",
    "final_rep_malicious",
    "final_rep_unstable",
    "mean_rep_honest",
    "mean_rep_malicious",
    # Orquestrador eleito (vazio no modo fixo).
    "leader_malicious_rounds",
    "leader_malicious_rounds_after_calibration",
    "max_consecutive_same_leader",
    "n_distinct_leaders",
    "bootstrap_rounds",
    "accepted_rounds",
    "voided_rounds",
    "forged_accepted",
    "censored_accepted",
    "mandates_ended_by_audit",
    "auditor_false_reject_penalties",
    "chain_split_rounds",
    "n_chains_final",
    "honest_replicas_divergent_final",
    "oracle_rounds",
    "oracle_blocked_rounds",
    "malicious_power_mass_final",
    "mean_hops",
    "max_hops",
    "graph_max_degree",
    "graph_diameter",
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
    **variant,
) -> list[dict]:
    """Retorna a lista de configurações a executar.

    ``variant`` fixa orquestração, sinal, topologia, ataques e defesa para toda
    a grade (padrão: orquestrador fixo de hoje).
    """
    extra = {**_CLASSIC, **variant}
    grid = []
    for n_nodes in nodes_list:
        for mal_frac in malicious_list:
            for seed in range(num_seeds):
                for mech in mechanisms:
                    common = dict(
                        nodes=n_nodes,
                        malicious_frac=mal_frac,
                        seed=seed,
                        mechanism=mech,
                        rounds=rounds,
                        alpha=alpha,
                        honest_accuracy=honest_accuracy,
                        test_every=test_every,
                        **extra,
                    )
                    # Variante sem conluio (sempre, salvo quando o bloco só quer conluio).
                    if not extra.get("collusion_only") or mal_frac == 0:
                        grid.append(dict(common, collusion=False, collusion_value_arg=None))
                    # Variante com conluio (apenas quando há maliciosos).
                    if with_collusion and mal_frac > 0:
                        grid.append(dict(common, collusion=True, collusion_value_arg=collusion_value))
    return grid


def build_dynamic_plan(
    num_seeds: int,
    rounds: int,
    alpha: float,
    honest_accuracy: float,
    collusion_value: int,
    test_every: int,
) -> list[dict]:
    """Rodada de testes do orquestrador eleito (blocos descritos no módulo)."""
    common = dict(
        num_seeds=num_seeds, rounds=rounds, alpha=alpha, honest_accuracy=honest_accuracy,
        collusion_value=collusion_value, test_every=test_every, with_collusion=True,
    )
    mechs = ["beta", "ema_asymmetric"]
    dyn = dict(orchestration="dynamic", topology="kregular", collusion_only=True)
    plan: list[dict] = []

    for attack in LEADER_ATTACKS:
        plan += build_grid([7, 10, 20], [0.0, 0.25, 0.5, 0.65], mechanisms=mechs, **common,
                           **dyn, signal="hybrid", defense="all", leader_attack=attack, block="main")
    plan += build_grid([7, 10, 20], [0.0, 0.25, 0.5, 0.65], mechanisms=mechs, **common,
                       **dyn, signal="consensus", defense="all", block="consensus")
    plan += build_grid([7, 10, 20], [0.0, 0.25, 0.5, 0.65], mechanisms=mechs, **common,
                       collusion_only=True, block="reference")

    for defense in ("none", "all"):
        plan += build_grid([7, 10, 20], [0.25, 0.5], mechanisms=mechs, **common, **dyn,
                           signal="hybrid", defense=defense, auditor_attack="false_reject", block="auditor")

    ablation_cells = [(20, 0.5), (20, 0.65), (7, 0.65)]
    for n_nodes, mal_frac in ablation_cells:
        for defense in preset_names():
            for attack in ("forge", "censor"):
                plan += [cfg for cfg in build_grid(
                    [n_nodes], [mal_frac], mechanisms=mechs, **common, **dyn,
                    signal="hybrid", defense=defense, leader_attack=attack, block="ablation",
                ) if cfg["collusion"]]

    for topology in ("star", "kregular"):
        plan += build_grid([7, 10, 20, 60, 120], [0.25], mechanisms=["ema_asymmetric"],
                           **{**common, "num_seeds": min(num_seeds, 3), "with_collusion": False},
                           orchestration="dynamic", topology=topology, signal="hybrid",
                           defense="all", block="scale")

    # Remove duplicatas (a mesma célula pode aparecer em dois blocos).
    unique: dict[str, dict] = {}
    for cfg in plan:
        unique.setdefault(_experiment_id(cfg), cfg)
    return list(unique.values())


def _experiment_id(cfg: dict) -> str:
    mal_pct = int(round(cfg["malicious_frac"] * 100))
    collusion_tag = f"_col{cfg['collusion_value_arg']}" if cfg["collusion"] else ""
    base = (
        f"n{cfg['nodes']}_m{mal_pct:02d}"
        f"_s{cfg['seed']:02d}_{cfg['mechanism']}{collusion_tag}"
    )
    test_tag = f"_t{int(cfg.get('test_every', DEFAULT_TEST_EVERY)):02d}"
    if cfg.get("orchestration", "fixed") == "fixed" and cfg.get("signal", "truth") == "truth":
        return f"mat_{base}{test_tag}"
    return (
        f"dyn_{base}_{cfg.get('orchestration')}_{cfg.get('signal')}_{cfg.get('topology')}"
        f"_la-{cfg.get('leader_attack')}_aa-{cfg.get('auditor_attack')}_d-{cfg.get('defense')}{test_tag}"
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
        orchestration=cfg.get("orchestration", "fixed"),
        signal=cfg.get("signal", "truth"),
        topology=cfg.get("topology", "star"),
        degree=cfg.get("degree", 4),
        leader_attack=cfg.get("leader_attack", "none"),
        auditor_attack=cfg.get("auditor_attack", "none"),
        defense=cfg.get("defense", "none"),
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
    dyn = summ.get("dynamic", {})
    nodes = int(cfg.get("nodes", 0) or 0)
    mal_frac = float(cfg.get("malicious_frac", 0) or 0)
    n_malicious = int(round(mal_frac * nodes)) if nodes else 0
    mal_pct_actual = round(100.0 * n_malicious / nodes, 2) if nodes else 0
    mal_pct = int(round(mal_frac * 100))
    test_rounds = summ.get("test_rounds") or test_rounds_1based(
        int(cfg.get("rounds", 0) or 0),
        int(cfg.get("test_every", DEFAULT_TEST_EVERY)),
    )
    row = {
        "experiment_id": result.get("exp_id", ""),
        "block": cfg.get("block", "classic"),
        "nodes": cfg.get("nodes", ""),
        "malicious_frac": cfg.get("malicious_frac", ""),
        "malicious_pct": mal_pct,
        "n_malicious": n_malicious,
        "malicious_pct_actual": mal_pct_actual,
        "seed": cfg.get("seed", ""),
        "mechanism": cfg.get("mechanism", ""),
        "collusion": int(cfg.get("collusion", False)),
        "collusion_value": cfg.get("collusion_value_arg", ""),
        "orchestration": cfg.get("orchestration", "fixed"),
        "signal": cfg.get("signal", "truth"),
        "topology": cfg.get("topology", "star"),
        "degree": cfg.get("degree", 4),
        "leader_attack": cfg.get("leader_attack", "none"),
        "auditor_attack": cfg.get("auditor_attack", "none"),
        "defense": cfg.get("defense", "none"),
        "rounds": cfg.get("rounds", ""),
        "alpha": cfg.get("alpha", ""),
        "honest_accuracy": cfg.get("honest_accuracy", ""),
        "test_every": cfg.get("test_every", DEFAULT_TEST_EVERY),
        "test_rounds": "|".join(str(r) for r in test_rounds),
        "consensus_accuracy_weighted": summ.get("consensus_accuracy_weighted", ""),
        "consensus_accuracy_majority": summ.get("consensus_accuracy_majority", ""),
        "consensus_accuracy_weighted_on_tests": summ.get("consensus_accuracy_weighted_on_tests", ""),
        "consensus_accuracy_majority_on_tests": summ.get("consensus_accuracy_majority_on_tests", ""),
        "recovery_round": "" if summ.get("recovery_round") is None else summ.get("recovery_round"),
        "final_rep_honest": final_rep.get("honest", ""),
        "final_rep_malicious": final_rep.get("malicious", ""),
        "final_rep_unstable": final_rep.get("unstable", ""),
        "mean_rep_honest": mean_rep.get("honest", ""),
        "mean_rep_malicious": mean_rep.get("malicious", ""),
        "output_dir": result.get("output_dir", ""),
        "elapsed_s": result.get("elapsed_s", ""),
    }
    for key in INDEX_FIELDS:
        if key in dyn:
            row[key] = dyn[key]
    if dyn:
        row["n_distinct_leaders"] = len(dyn.get("leadership_distribution", {}))
    return row


def _write_index(rows: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=INDEX_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa a matriz de experimentos de reputação.",
    )
    parser.add_argument(
        "--plan", choices=["classic", "dynamic"], default="classic",
        help="classic = matriz original; dynamic = rodada de testes do orquestrador eleito.",
    )
    parser.add_argument(
        "--nodes", type=int, nargs="+", default=[7, 10, 15, 20],
        help="Tamanhos de rede a testar.",
    )
    parser.add_argument(
        "--malicious", type=float, nargs="+", default=[0.0, 0.25, 0.5, 0.65],
        help="Frações nominais de nós maliciosos. 0.65 cobre o cenário de cerca de 65%.",
    )
    parser.add_argument(
        "--seeds", type=int, default=10,
        help="Número de repetições (seed 0..N-1) por célula.",
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
        "--output", default=None,
        help="Diretório base para os resultados (padrão depende do --plan).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Lista os experimentos sem executar.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    output = args.output or (_DYNAMIC_OUTPUT if args.plan == "dynamic" else _BASE_OUTPUT)
    os.makedirs(output, exist_ok=True)

    if args.plan == "dynamic":
        grid = build_dynamic_plan(
            num_seeds=args.seeds,
            rounds=args.rounds,
            alpha=args.alpha,
            honest_accuracy=args.honest_accuracy,
            collusion_value=args.collusion_value,
            test_every=args.test_every,
        )
    else:
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
        result = _run_one(cfg, output, dry_run=False)
        if result is not None:
            row = _index_row(result)
            index_rows.append(row)
            elapsed = result.get("elapsed_s", 0.0)
            acc_w = result.get("summary", {}).get("consensus_accuracy_weighted_on_tests", "?")
            print(f"OK {elapsed:.1f}s  acc_testes={acc_w}")
        else:
            print("✗")

    # Persiste o índice da matriz.
    index_path = os.path.join(output, "matrix_index.csv")
    _write_index(index_rows, index_path)

    total_time = round(time.perf_counter() - t_start, 1)
    print(f"\nConcluído: {len(index_rows)}/{total} experimentos em {total_time}s.")
    print(f"Índice salvo em: {index_path}")


if __name__ == "__main__":
    main()
