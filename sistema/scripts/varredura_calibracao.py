"""Varredura das rodadas de calibração sem líder e dos α (correção A4).

Orquestrador dinâmico com gabarito, todas as defesas, calibração sem líder,
conluio no valor 999 e líder malicioso que forja. 50 nós, 50 rodadas,
5 repetições.

* k = 0..5 rodadas de calibração (k = 0 é o protocolo sem calibração);
* α do gabarito em {0,5; 0,8; 0,95};
* α do consenso em {0,05; 0,3};
* frações de nós maliciosos 0, 5, 20, 25, 35, 50, 65 e 80%.

Uso (na raiz do repositório)::

    python -m sistema.scripts.varredura_calibracao <pasta_de_saida>
"""
from __future__ import annotations

import csv
import itertools
import os
import statistics
import sys

from sistema.scripts.run_a3_n50 import _args
from sistema.simulate import run_simulation

FRACOES = (0.0, 0.05, 0.20, 0.25, 0.35, 0.50, 0.65, 0.80)
SEMENTES = range(5)


def main(out: str) -> None:
    os.makedirs(out, exist_ok=True)
    linhas = []
    for k, a_gab, a_cons, frac in itertools.product(range(6), (0.5, 0.8, 0.95), (0.05, 0.3), FRACOES):
        for seed in SEMENTES:
            args = _args(
                f"k{k}_g{a_gab}_c{a_cons}_m{int(round(frac * 100))}_s{seed}",
                malicious=frac, seed=seed, orchestration="dynamic", signal="hybrid", defense="all",
                topology="kregular", leader_attack="forge" if frac > 0 else "none",
                calibration_rounds=k, oracle_alpha=a_gab, consensus_alpha=a_cons,
                output=os.path.join(out, "brutos"),
            )
            args.leaderless_calibration = True
            s = run_simulation(args)
            d = s["dynamic"]
            linhas.append(dict(
                k=k, alfa_gabarito=a_gab, alfa_consenso=a_cons, fracao=frac, n_maliciosos=round(frac * 50),
                repeticao=seed, acc_teste=s["consensus_accuracy_weighted_on_tests"],
                acc_teste_maioria=s["consensus_accuracy_majority_on_tests"], acc_todas=s["consensus_accuracy_weighted"],
                lider_malicioso=d["leader_malicious_rounds"], forjas_aceitas=d["forged_accepted"],
                anulacoes=d["voided_rounds"], cadeias_no_fim=d["n_chains_final"],
            ))
    with open(os.path.join(out, "execucoes.csv"), "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    chave = ("k", "alfa_gabarito", "alfa_consenso", "fracao", "n_maliciosos")
    grupos: dict = {}
    for l in linhas:
        grupos.setdefault(tuple(l[c] for c in chave), []).append(l)
    resumo = []
    for kk, g in grupos.items():
        d = dict(zip(chave, kk))
        for m in ("acc_teste", "acc_teste_maioria", "acc_todas"):
            v = [float(x[m]) for x in g]
            d[m + "_media"] = round(statistics.mean(v), 4)
            d[m + "_dp"] = round(statistics.stdev(v), 4)
        for m in ("lider_malicioso", "forjas_aceitas", "anulacoes"):
            d[m + "_media"] = round(statistics.mean(x[m] for x in g), 2)
        d["cadeias_max"] = max(x["cadeias_no_fim"] for x in g)
        resumo.append(d)
    with open(os.path.join(out, "resumo.csv"), "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(resumo[0]))
        w.writeheader()
        w.writerows(resumo)
    print(f"{len(linhas)} execuções -> {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "resultados/varredura_calibracao")
