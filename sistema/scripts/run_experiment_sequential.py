"""Grade experimental em sequência: uma configuração termina e a próxima começa.

N = 5..50, percentuais 0/5/20/35/50/65/80%, 50 rodadas, 30 sementes por célula.

    python -m sistema.scripts.run_experiment_sequential
    python -m sistema.scripts.run_experiment_sequential --repeticoes 30
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone

from ..core.experiment_spec import (
    COLLUSION_VALUE,
    CONFIGS,
    CONFIG_TITULOS,
    INTERPRETACAO_SPLIT,
    LEVELS_PROGRESSAO,
    NETWORK_SIZES,
    derive_seed,
    iter_cells_by_config,
)
from .run_harness import run_jobs, write_ambiente, _cpu_model, _lib_versions, _ram_gb

_DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "results", "harness_progressao")


def planned_jobs_for_config(configuracao: str, repeticoes: int = 1) -> list[tuple[int, str, str, int, int]]:
    jobs = []
    for n, nivel, cfg in iter_cells_by_config(
        NETWORK_SIZES, LEVELS_PROGRESSAO, (configuracao,)
    ):
        for indice in range(repeticoes):
            seed = derive_seed(n, nivel, cfg, indice)
            jobs.append((n, nivel, cfg, indice, seed))
    return jobs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grade sequencial (4 configs, 50 rodadas, 1 semente).")
    parser.add_argument("--rodadas", type=int, default=50)
    parser.add_argument("--repeticoes", type=int, default=30)
    parser.add_argument("--limiar-reputacao", type=float, default=0.5)
    parser.add_argument("--interpretacao", choices=("split", "extra"), default=INTERPRETACAO_SPLIT)
    parser.add_argument("--p-falha", type=float, default=0.3)
    parser.add_argument("--alpha", type=float, default=0.25)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--output", default=_DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    out_dir = os.path.abspath(args.output)
    os.makedirs(out_dir, exist_ok=True)
    ambiente_path = os.path.join(out_dir, "ambiente.json")
    started = datetime.now(timezone.utc)
    wall0 = time.perf_counter()
    n_cells = len(NETWORK_SIZES) * len(LEVELS_PROGRESSAO) * len(CONFIGS) * args.repeticoes
    ambiente = {
        "cpu_modelo": _cpu_model(),
        "nucleos": os.cpu_count(),
        "ram_gb": _ram_gb(),
        "inicio_utc": started.isoformat(),
        "fim_utc": None,
        "tempo_total_s": None,
        "bibliotecas": _lib_versions(),
        "parametros": {
            "rodadas": args.rodadas,
            "repeticoes": args.repeticoes,
            "niveis": list(LEVELS_PROGRESSAO),
            "tamanhos": list(NETWORK_SIZES),
            "configuracoes": list(CONFIGS),
            "execucoes_planejadas": n_cells,
            "limiar_reputacao": args.limiar_reputacao,
            "interpretacao_instaveis": args.interpretacao,
            "p_falha": args.p_falha,
            "conluio": f"valor fixo {COLLUSION_VALUE}",
            "alpha": args.alpha,
            "min_confidence": args.min_confidence,
            "ordem": "config -> N -> percentual",
        },
        "configuracoes_concluidas": [],
    }
    write_ambiente(ambiente_path, ambiente)

    common = dict(
        out_dir=out_dir,
        rounds=args.rodadas,
        limiar=args.limiar_reputacao,
        interpretacao=args.interpretacao,
        p_falha=args.p_falha,
        alpha=args.alpha,
        min_confidence=args.min_confidence,
    )

    print(f"Saída: {out_dir}")
    print(f"Planejado: {n_cells} execuções ({args.rodadas} rodadas, {args.repeticoes} semente(s) por célula).")

    for index, configuracao in enumerate(CONFIGS, start=1):
        titulo = CONFIG_TITULOS[configuracao]
        print(f"\n=== Iniciando config {index}/4: {titulo} ===")
        jobs = planned_jobs_for_config(configuracao, args.repeticoes)
        run_jobs(jobs, label=titulo, **common)
        ambiente["configuracoes_concluidas"].append(
            {
                "index": index,
                "configuracao": configuracao,
                "titulo": titulo,
                "fim_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        write_ambiente(ambiente_path, ambiente)
        print(f"=== Config {index}/4 concluída: {titulo} ===")

    ambiente["fim_utc"] = datetime.now(timezone.utc).isoformat()
    ambiente["tempo_total_s"] = round(time.perf_counter() - wall0, 2)
    write_ambiente(ambiente_path, ambiente)
    print(f"\nGrade sequencial concluída em {ambiente['tempo_total_s']}s.")
    print(f"CSV: {os.path.join(out_dir, 'resultados.csv')}")


if __name__ == "__main__":
    main()
