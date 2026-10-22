"""Experimentos da A4 com respostas reais do SmolLM3-3B (banco de amostras).

Lê o banco gerado por ``gerar_banco_llm.py`` e roda, sobre as mesmas
questões, duas fontes de resposta para os nós honestos:

* ``llm``    : cada nó honesto sorteia, a cada rodada, uma das amostras que o
               modelo gerou para a pergunta;
* ``perfil`` : controle com o perfil simulado de antes (acerta o gabarito com
               probabilidade 0,9).

Configurações (todas com 50 nós, 50 rodadas, 5 repetições):

* orquestrador fixo, com gabarito nas rodadas 10, 20, 30, 40 e 50;
* orquestrador dinâmico, com gabarito, calibração sem líder de ``--calibracao``
  rodadas e todas as defesas;
* orquestrador dinâmico, sem gabarito.

Cada uma com e sem conluio (999; no dinâmico, o líder malicioso forja quando há
conluio), nas frações 0, 5, 20, 25, 35, 50, 65 e 80% de nós maliciosos.

Para cada execução são registradas a acurácia do consenso ponderado (com
reputação) e a da maioria simples (sem reputação) **sobre o mesmo conjunto de
respostas**: no dinâmico, a maioria é contada só entre os nós da cópia de
referência, a mesma onde o consenso ponderado é medido.

Uso (na raiz do repositório)::

    python -m sistema.scripts.rodar_com_banco --banco sistema/resultados/banco_llm/banco_smol.json \\
        --saida sistema/resultados/banco_llm/experimentos
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import statistics

import sistema.simulate as sim
from sistema.core.answer import normalize
from sistema.core.consensus import majority_consensus
from sistema.scripts.run_a3_n50 import _args

FRACOES = (0.0, 0.05, 0.20, 0.25, 0.35, 0.50, 0.65, 0.80)
SEMENTES = range(5)
CONFIGS = {
    "fixo_com_gabarito": dict(orchestration="fixed", signal="hybrid", defense="none", topology="star"),
    "dinamico_com_gabarito": dict(orchestration="dynamic", signal="hybrid", defense="all", topology="kregular"),
    "dinamico_sem_gabarito": dict(orchestration="dynamic", signal="consensus", defense="all", topology="kregular"),
}

# Captura, rodada a rodada, a maioria simples entre os nós da cópia de referência.
_CAPTURA: list[dict] = []
_original = sim._dynamic_round


def _dynamic_round_com_captura(network, logger, round_index, task_id, expected, responses, profiles,
                               mechanism, initial, is_test):
    _original(network, logger, round_index, task_id, expected, responses, profiles, mechanism, initial, is_test)
    ref = set(network.reference_group().members)
    pares = [(r.node_id, r.answer) for r in responses if r.node_id in ref]
    _CAPTURA.append(dict(is_test=is_test, expected=expected, maioria_ref=majority_consensus(pares).answer,
                         n_ref=len(ref), n_rede=len(responses)))


sim._dynamic_round = _dynamic_round_com_captura


def carregar_banco(path: str) -> tuple[list[dict], dict]:
    with open(path, encoding="utf-8") as h:
        banco = json.load(h)
    tarefas = [{"id": t["id"], "question": t["question"], "answer": t["answer"]} for t in banco["tarefas"]]
    respostas = {t["id"]: [normalize(a["resposta"]) for a in t["amostras"]] for t in banco["tarefas"]}
    return tarefas, respostas


def _taxa(itens: list[dict], chave: str) -> float:
    testes = [i for i in itens if i["is_test"]]
    return sum(1 for i in testes if i[chave] is not None and i[chave] == i["expected"]) / max(len(testes), 1)


def executar(cfg_nome: str, fonte: str, conluio: bool, frac: float, seed: int, tarefas, banco, out: str,
             calibracao: int, mecanismo: str) -> dict:
    cfg = CONFIGS[cfg_nome]
    dinamico = cfg["orchestration"] == "dynamic"
    exp_id = f"{fonte}/{cfg_nome}/c{int(conluio)}/m{int(round(frac * 100)):02d}/s{seed}"
    args = _args(
        exp_id, malicious=frac, seed=seed, mechanism=mecanismo, output=out,
        leader_attack="forge" if (dinamico and conluio and frac > 0) else "none",
        calibration_rounds=calibracao if cfg_nome == "dinamico_com_gabarito" else None, **cfg,
    )
    args.collusion_value = 999 if (conluio and frac > 0) else None
    args.leaderless_calibration = cfg_nome == "dinamico_com_gabarito"
    args.tasks = tarefas
    if fonte == "llm":
        args.answer_bank = banco
    _CAPTURA.clear()
    s = sim.run_simulation(args)
    d = s.get("dynamic", {}) or {}
    maioria = _taxa(_CAPTURA, "maioria_ref") if dinamico else s["consensus_accuracy_majority_on_tests"]
    return dict(
        fonte=fonte, config=cfg_nome, conluio=int(conluio), fracao=frac, n_maliciosos=round(frac * 50),
        repeticao=seed, com_reputacao_teste=s["consensus_accuracy_weighted_on_tests"],
        sem_reputacao_teste=maioria, maioria_rede_inteira_teste=s["consensus_accuracy_majority_on_tests"],
        com_reputacao_todas=s["consensus_accuracy_weighted"],
        lider_malicioso=d.get("leader_malicious_rounds", ""), forjas_aceitas=d.get("forged_accepted", ""),
        anulacoes=d.get("voided_rounds", ""), cadeias_no_fim=d.get("n_chains_final", ""),
        rodadas_com_copia_parcial=sum(1 for c in _CAPTURA if c["n_ref"] < c["n_rede"]) if dinamico else 0,
    )


def resumir(linhas: list[dict]) -> list[dict]:
    chave = ("fonte", "config", "conluio", "fracao", "n_maliciosos")
    grupos: dict = {}
    for l in linhas:
        grupos.setdefault(tuple(l[c] for c in chave), []).append(l)
    out = []
    for k, g in grupos.items():
        d = dict(zip(chave, k))
        for m in ("com_reputacao_teste", "sem_reputacao_teste", "maioria_rede_inteira_teste", "com_reputacao_todas"):
            v = [float(x[m]) for x in g]
            d[m + "_media"] = round(statistics.mean(v), 4)
            d[m + "_dp"] = round(statistics.stdev(v), 4) if len(v) > 1 else 0.0
        for m in ("lider_malicioso", "forjas_aceitas", "anulacoes", "rodadas_com_copia_parcial"):
            v = [float(x[m]) for x in g if x[m] != ""]
            d[m + "_media"] = round(statistics.mean(v), 2) if v else ""
        cad = [x["cadeias_no_fim"] for x in g if x["cadeias_no_fim"] != ""]
        d["cadeias_max"] = max(cad) if cad else ""
        out.append(d)
    return out


def figuras(resumo: list[dict], out: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fr = [int(f * 100) for f in FRACOES]
    for cfg in CONFIGS:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
        fig.patch.set_facecolor("white")
        for ax, fonte, titulo in zip(axes, ("llm", "perfil"), ("Respostas do SmolLM3-3B", "Perfil simulado (controle)")):
            estilos = [
                (1, "com_reputacao_teste_media", "#E8590C", "-", "o", "Com conluio, com reputação"),
                (1, "sem_reputacao_teste_media", "#E8590C", "--", "s", "Com conluio, sem reputação"),
                (0, "com_reputacao_teste_media", "#1C4E80", "-", "o", "Sem conluio, com reputação"),
                (0, "sem_reputacao_teste_media", "#1C4E80", "--", "s", "Sem conluio, sem reputação"),
            ]
            for i, (c, k, cor, ls, mk, rot) in enumerate(estilos):
                y = [100 * next(r[k] for r in resumo if r["fonte"] == fonte and r["config"] == cfg
                                and r["conluio"] == c and r["fracao"] == f) for f in FRACOES]
                ax.plot([x + (-1.2, -0.4, 0.4, 1.2)[i] for x in fr], y, color=cor, ls=ls, marker=mk, lw=2, ms=5, label=rot)
            ax.set_title(titulo, fontsize=11)
            ax.set_xticks(fr)
            ax.set_xticklabels([f"{x}%" for x in fr], fontsize=8)
            ax.set_xlabel("Nós maliciosos (de 50)")
            ax.set_ylim(-5, 105)
            ax.grid(alpha=.3)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
        axes[0].set_ylabel("Acurácia nas rodadas de teste (%)")
        axes[1].legend(fontsize=8, frameon=False, loc="lower left")
        fig.suptitle(cfg.replace("_", " ").capitalize(), fontsize=12)
        fig.tight_layout()
        fig.savefig(os.path.join(out, f"{cfg}.png"), dpi=160, facecolor="white")
        plt.close(fig)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Experimentos com o banco de respostas do modelo.")
    p.add_argument("--banco", required=True)
    p.add_argument("--saida", default=os.path.join("sistema", "resultados", "banco_llm", "experimentos"))
    p.add_argument("--calibracao", type=int, default=3)
    p.add_argument("--mecanismo", default="ema", choices=("ema", "ema_asymmetric", "beta"))
    a = p.parse_args(argv)
    tarefas, banco = carregar_banco(a.banco)
    os.makedirs(a.saida, exist_ok=True)
    linhas = []
    for fonte, cfg, conluio, frac in itertools.product(("llm", "perfil"), CONFIGS, (False, True), FRACOES):
        for seed in SEMENTES:
            linhas.append(executar(cfg, fonte, conluio, frac, seed, tarefas, banco,
                                   os.path.join(a.saida, "brutos"), a.calibracao, a.mecanismo))
    with open(os.path.join(a.saida, "execucoes.csv"), "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    resumo = resumir(linhas)
    with open(os.path.join(a.saida, "resumo.csv"), "w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(resumo[0]))
        w.writeheader()
        w.writerows(resumo)
    figuras(resumo, a.saida)
    print(f"{len(linhas)} execuções, {len(tarefas)} questões -> {a.saida}")


if __name__ == "__main__":
    main()
