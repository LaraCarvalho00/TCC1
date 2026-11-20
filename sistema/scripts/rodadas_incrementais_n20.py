"""História incremental em 20 nós e 50 rodadas.

As 20 configurações são as etapas 4–7 (1–3 saem da 4, medoide sem peso):

* 7 jobs na etapa 4 (0% + 20/40/80% com e sem conluio)
* 7 na etapa 5 (auditoria aleatória p=0,2)
* 3 na etapa 6 (conluio, nota graduada)
* 3 na etapa 7 (conluio, 20% instáveis)

``--sementes 1`` → 20 execuções (texto).
``--sementes 5`` → 100 execuções (figura 20×5).

``--fonte banco`` não usa GPU. ``--fonte vivo`` gera uma resposta por nó e rodada
(Smol: até 2 cópias NF4; Qwen3-8B: 1 cópia). Não rode vivo na mesma GPU do
gerador do banco 8B.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sistema.experimentos.cenarios_incrementais import TAREFAS_PADRAO, executar, trabalhos

RECORTE = {1: "n20", 5: "n20s5"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sementes", type=int, choices=(1, 5), default=1)
    parser.add_argument("--fonte", choices=("banco", "vivo"), default="banco")
    parser.add_argument("--llm", choices=("smol", "qwen3-8b"), default="smol")
    parser.add_argument("--tarefas", type=Path, default=TAREFAS_PADRAO)
    parser.add_argument("--saida", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--planejar", action="store_true")
    args = parser.parse_args(argv)
    recorte = RECORTE[args.sementes]
    jobs, spec = trabalhos(recorte)
    unicas = spec["nos"] * spec["rodadas"] * len(spec["sementes"])
    print(
        f"{len(jobs)} execuções; {spec['nos']} nós; {spec['rodadas']} rodadas; "
        f"{args.sementes} semente(s); fonte {args.fonte}; llm {args.llm}"
        + (f"; até {unicas} gerações" if args.fonte == "vivo" else "; banco 50×20"),
        flush=True,
    )
    if args.planejar:
        for job in jobs:
            print(job["id"])
        return 0
    if args.saida is None:
        raise ValueError("Informe --saida")
    workers = 1 if args.fonte == "vivo" and args.llm == "qwen3-8b" else args.workers
    if args.fonte == "vivo" and args.llm == "smol":
        workers = min(args.workers, 2)
    executar(
        args.saida, recorte=recorte, llm=args.llm, tarefas=args.tarefas,
        workers=workers, fonte=args.fonte,
    )
    print(f"Resultado: {args.saida.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, FileExistsError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        raise SystemExit(1)
