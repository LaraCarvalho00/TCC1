"""Comparação da gênese, da auditoria e do malicioso que conhece o calendário.

1.400 execuções dinâmicas com o banco do SmolLM3-3B. Não gera figuras e não
interpreta os números.

Uso (na raiz do repositório)::

    python -m sistema.scripts.rodar_comparacao_genese
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import time

from sistema.core.answer import normalize
from sistema.scripts.run_a3_n50 import _args
from sistema.simulate import run_simulation

BANCO = "sistema/resultados/banco_llm/banco_smol.json"
SAIDA = os.path.join("sistema", "resultados", "orientacao_22out")
BRUTOS = os.path.join(SAIDA, "brutos")
FRACOES = (0.0, 0.05, 0.20, 0.25, 0.35, 0.50, 0.65, 0.80)
SEMENTES = range(5)

CONFIGS = {
    "sem_genese": dict(
        signal="consensus", calibration_rounds=0, mechanism="ema",
        audit_mode="fixed", audit_p=0.1, leaderless=False,
    ),
    "com_genese": dict(
        signal="hybrid", calibration_rounds=3, mechanism="ema",
        audit_mode="fixed", audit_p=0.1, leaderless=True,
    ),
    "auditoria_p10": dict(
        signal="consensus", calibration_rounds=0, mechanism="ema_slow_up",
        audit_mode="random", audit_p=0.1, leaderless=False,
    ),
    "auditoria_p20": dict(
        signal="consensus", calibration_rounds=0, mechanism="ema_slow_up",
        audit_mode="random", audit_p=0.2, leaderless=False,
    ),
    "auditoria_p20_ema": dict(
        signal="consensus", calibration_rounds=0, mechanism="ema",
        audit_mode="random", audit_p=0.2, leaderless=False,
    ),
}

CAMPOS = (
    "bloco", "config", "estrategia", "conluio", "fracao", "fracao_instavel",
    "n_maliciosos", "instaveis_honestos", "instaveis_maliciosos", "semente",
    "com_reputacao_teste", "sem_reputacao_teste",
    "com_reputacao_sem_gabarito", "sem_reputacao_sem_gabarito",
    "com_reputacao_todas", "rodadas_auditadas",
    "cadeias_no_fim", "forjas_aceitas", "anulacoes",
    "lider_malicioso", "auditor_malicioso", "vetos_auditor_malicioso",
    "media_pct_honest_exact", "reputacao_final_honestos", "reputacao_final_maliciosos",
)
CHAVES = ("bloco", "config", "estrategia", "conluio", "fracao", "fracao_instavel")
MEDIDAS = tuple(campo for campo in CAMPOS if campo not in CHAVES and campo != "semente")


def carregar_banco(path: str) -> tuple[list[dict], dict]:
    with open(path, encoding="utf-8") as handle:
        banco = json.load(handle)
    tarefas = [{"id": t["id"], "question": t["question"], "answer": t["answer"]} for t in banco["tarefas"]]
    respostas = {t["id"]: [normalize(a["resposta"]) for a in t["amostras"]] for t in banco["tarefas"]}
    return tarefas, respostas


def trabalhos() -> list[dict]:
    """As 1.400 células, na ordem bloco, config, estratégia, conluio, fração, semente."""
    saida = []
    for config in CONFIGS:
        for estrategia in ("on_off", "knows_schedule"):
            for conluio in (False, True):
                for fracao in FRACOES:
                    for semente in SEMENTES:
                        saida.append(dict(
                            bloco="respostas", config=config, estrategia=estrategia,
                            conluio=conluio, fracao=fracao, fracao_instavel=0.0, semente=semente,
                            leader_attack="none", auditor_attack="none",
                        ))
    for config in CONFIGS:
        for fracao in FRACOES:
            for semente in SEMENTES:
                saida.append(dict(
                    bloco="forja", config=config, estrategia="knows_schedule",
                    conluio=True, fracao=fracao, fracao_instavel=0.0, semente=semente,
                    leader_attack="forge", auditor_attack="false_reject",
                ))
    for config in CONFIGS:
        for instavel in (0.1, 0.2):
            for fracao in FRACOES:
                for semente in SEMENTES:
                    saida.append(dict(
                        bloco="instaveis", config=config, estrategia="knows_schedule",
                        conluio=True, fracao=fracao, fracao_instavel=instavel, semente=semente,
                        leader_attack="none", auditor_attack="none",
                    ))
    return saida


def _blank(value):
    return "" if value is None else value


def executar(job: dict, tarefas, banco, brutos: str = BRUTOS) -> tuple[dict, str]:
    config = CONFIGS[job["config"]]
    mal = int(round(job["fracao"] * 100))
    inst = int(round(job["fracao_instavel"] * 100))
    exp_id = (
        f"{job['bloco']}/{job['config']}/{job['estrategia']}/c{int(job['conluio'])}"
        f"/m{mal:02d}/u{inst:02d}/s{job['semente']}"
    )
    args = _args(
        exp_id,
        malicious=job["fracao"],
        unstable=job["fracao_instavel"],
        seed=job["semente"],
        output=brutos,
        nodes=50,
        rounds=50,
        orchestration="dynamic",
        topology="kregular",
        degree=4,
        defense="all",
        signal=config["signal"],
        calibration_rounds=config["calibration_rounds"],
        mechanism=config["mechanism"],
        consensus_mode="distance",
        malicious_answer="noise",
        malicious_strategy=job["estrategia"],
        honest_rounds=5,
        leader_attack=job["leader_attack"],
        auditor_attack=job["auditor_attack"],
        audit_mode=config["audit_mode"],
        audit_p=config["audit_p"],
        unstable_mode="attribute" if job["fracao_instavel"] else "profile",
        quiet=True,
        row_sync=False,
        overwrite=True,
    )
    args.tasks = tarefas
    args.answer_bank = banco
    args.collusion_value = 999 if job["conluio"] else None
    args.leaderless_calibration = config["leaderless"]
    resumo = run_simulation(args)
    dinamico = resumo.get("dynamic") or {}
    finais = resumo.get("final_reputation_by_profile") or {}
    linha = {
        "bloco": job["bloco"],
        "config": job["config"],
        "estrategia": job["estrategia"],
        "conluio": int(job["conluio"]),
        "fracao": job["fracao"],
        "fracao_instavel": job["fracao_instavel"],
        "n_maliciosos": round(job["fracao"] * 50),
        "instaveis_honestos": resumo.get("unstable_honest", 0),
        "instaveis_maliciosos": resumo.get("unstable_malicious", 0),
        "semente": job["semente"],
        "com_reputacao_teste": resumo["consensus_accuracy_weighted_on_tests"],
        "sem_reputacao_teste": resumo["consensus_accuracy_majority_on_tests"],
        "com_reputacao_sem_gabarito": resumo["consensus_accuracy_weighted_no_oracle"],
        "sem_reputacao_sem_gabarito": resumo["consensus_accuracy_majority_no_oracle"],
        "com_reputacao_todas": resumo["consensus_accuracy_weighted"],
        "rodadas_auditadas": resumo.get("n_audited", ""),
        "cadeias_no_fim": _blank(dinamico.get("n_chains_final", "")),
        "forjas_aceitas": _blank(dinamico.get("forged_accepted", "")),
        "anulacoes": _blank(dinamico.get("voided_rounds", "")),
        "lider_malicioso": _blank(dinamico.get("leader_malicious_rounds", "")),
        "auditor_malicioso": _blank(dinamico.get("auditor_malicious_rounds", "")),
        "vetos_auditor_malicioso": _blank(dinamico.get("auditor_malicious_vetoes", "")),
        "media_pct_honest_exact": _blank(resumo.get("mean_pct_honest_exact")),
        "reputacao_final_honestos": _blank(finais.get("honest")),
        "reputacao_final_maliciosos": _blank(finais.get("malicious")),
    }
    return linha, os.path.join(brutos, exp_id)


def acumular_reputacao(pasta: str, chave: tuple, acumulado: dict) -> None:
    grupos: dict[tuple[int, str], list[float]] = {}
    with open(os.path.join(pasta, "reputation_history.csv"), newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["profile"] not in ("honest", "malicious"):
                continue
            grupos.setdefault((int(row["checkpoint"]), row["profile"]), []).append(float(row["reputation"]))
    slot = acumulado.setdefault(chave, {})
    for (checkpoint, profile), values in grupos.items():
        slot.setdefault(checkpoint, {}).setdefault(profile, []).append(statistics.mean(values))


def resumir(linhas: list[dict]) -> list[dict]:
    grupos: dict[tuple, list[dict]] = {}
    for linha in linhas:
        grupos.setdefault(tuple(linha[chave] for chave in CHAVES), []).append(linha)
    saida = []
    for chave, grupo in grupos.items():
        linha = dict(zip(CHAVES, chave))
        for medida in MEDIDAS:
            numeros = []
            for item in grupo:
                valor = item[medida]
                if valor == "" or valor is None:
                    continue
                numeros.append(float(valor))
            if not numeros:
                linha[medida + "_media"] = ""
                linha[medida + "_dp"] = ""
                continue
            linha[medida + "_media"] = round(statistics.mean(numeros), 6)
            linha[medida + "_dp"] = round(statistics.stdev(numeros), 6) if len(numeros) > 1 else 0.0
        saida.append(linha)
    return saida


def gravar_reputacao(acumulado: dict, path: str) -> None:
    campos = (
        "bloco", "config", "estrategia", "conluio", "fracao", "fracao_instavel", "rodada",
        "reputacao_media_honestos", "reputacao_media_maliciosos",
    )
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=campos)
        writer.writeheader()
        for chave in sorted(acumulado):
            bloco, config, estrategia, conluio, fracao, instavel = chave
            for rodada in range(51):
                perfis = acumulado[chave].get(rodada, {})
                honestos = perfis.get("honest", [])
                maliciosos = perfis.get("malicious", [])
                writer.writerow({
                    "bloco": bloco,
                    "config": config,
                    "estrategia": estrategia,
                    "conluio": conluio,
                    "fracao": fracao,
                    "fracao_instavel": instavel,
                    "rodada": rodada,
                    "reputacao_media_honestos": round(statistics.mean(honestos), 6) if honestos else "",
                    "reputacao_media_maliciosos": round(statistics.mean(maliciosos), 6) if maliciosos else "",
                })


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Comparação da gênese, da auditoria e do calendário.")
    parser.add_argument("--saida", default=SAIDA, help="Pasta dos CSVs. O padrão é a pasta já usada.")
    opcoes = parser.parse_args(argv)
    saida = opcoes.saida
    brutos = os.path.join(saida, "brutos")
    jobs = trabalhos()
    if len(jobs) != 1400:
        raise SystemExit(f"grade com {len(jobs)} execuções; o pedido é 1.400.")
    tarefas, banco = carregar_banco(BANCO)
    os.makedirs(brutos, exist_ok=True)
    os.makedirs(saida, exist_ok=True)
    caminho = os.path.join(saida, "execucoes.csv")
    acumulado: dict = {}
    linhas = []
    inicio = time.perf_counter()
    with open(caminho, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CAMPOS)
        writer.writeheader()
        for indice, job in enumerate(jobs, start=1):
            linha, pasta = executar(job, tarefas, banco, brutos)
            writer.writerow(linha)
            handle.flush()
            linhas.append(linha)
            acumular_reputacao(pasta, tuple(linha[chave] for chave in CHAVES), acumulado)
            if indice == 1 or indice % 25 == 0 or indice == len(jobs):
                decorrido = time.perf_counter() - inicio
                print(f"{indice}/{len(jobs)} {decorrido:.0f}s {pasta}", flush=True)
    resumo = resumir(linhas)
    with open(os.path.join(saida, "resumo.csv"), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(resumo[0]))
        writer.writeheader()
        writer.writerows(resumo)
    gravar_reputacao(acumulado, os.path.join(saida, "reputacao_por_rodada.csv"))
    total = time.perf_counter() - inicio
    print(f"{len(linhas)} execuções em {total:.1f}s -> {saida}", flush=True)


if __name__ == "__main__":
    main()
