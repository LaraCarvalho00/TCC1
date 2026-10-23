"""Teste curto das quatro configurações da comparação da gênese.

Não interpreta os números. Roda 2 sementes, frações 0%, 50% e 80%, com o
banco do SmolLM3-3B, e grava a tabela em ``entrega_impl/teste_curto/``.

Uso (na raiz do repositório)::

    python -m sistema.scripts.rodar_orientacao
"""
from __future__ import annotations

import csv
import os

from sistema.scripts.rodar_com_banco import carregar_banco
from sistema.scripts.run_a3_n50 import _args
from sistema.simulate import run_simulation

BANCO = "sistema/resultados/banco_llm/banco_smol.json"
SAIDA = "entrega_impl/teste_curto"
FRACOES = (0.0, 0.5, 0.8)
SEMENTES = (0, 1)

# O que as quatro têm em comum. O conluio é o valor 999, que no modo ruído
# só marca o grupo: o número enviado é o ruído compartilhado.
COMUM = dict(
    nodes=50,
    rounds=50,
    orchestration="dynamic",
    topology="kregular",
    defense="all",
    consensus_mode="distance",
    malicious_answer="noise",
    malicious_strategy="on_off",
    honest_rounds=5,
    leader_attack="forge",
    auditor_attack="false_reject",
    collusion_value=999,
    quiet=True,
    row_sync=False,
    overwrite=True,
)

CONFIGS = {
    "sem_genese": dict(signal="consensus", calibration_rounds=0, mechanism="ema", audit_mode="fixed"),
    "com_genese": dict(
        signal="hybrid", calibration_rounds=3, mechanism="ema", audit_mode="fixed",
        leaderless_calibration=True,
    ),
    "auditoria_sorteada_p10": dict(
        signal="consensus", calibration_rounds=0, mechanism="ema_slow_up",
        audit_mode="random", audit_p=0.1,
    ),
    "auditoria_sorteada_p20": dict(
        signal="consensus", calibration_rounds=0, mechanism="ema_slow_up",
        audit_mode="random", audit_p=0.2,
    ),
}

CAMPOS = (
    "config", "fracao", "semente", "com_reputacao_teste", "sem_reputacao_teste",
    "com_reputacao_todas", "n_audited", "audited_rounds", "mean_pct_honest_exact",
    "auditor_malicioso", "vetos_auditor_malicioso",
)


def main() -> None:
    tarefas, banco = carregar_banco(BANCO)
    os.makedirs(SAIDA, exist_ok=True)
    linhas = []
    for nome, ajustes in CONFIGS.items():
        for fracao in FRACOES:
            for semente in SEMENTES:
                exp_id = f"{nome}/m{int(round(fracao * 100)):02d}/s{semente}"
                args = _args(exp_id, malicious=fracao, seed=semente, output=SAIDA, **COMUM, **ajustes)
                args.tasks = tarefas
                args.answer_bank = banco
                args.leaderless_calibration = bool(ajustes.get("leaderless_calibration", False))
                resumo = run_simulation(args)
                dinamico = resumo.get("dynamic", {})
                linhas.append({
                    "config": nome,
                    "fracao": fracao,
                    "semente": semente,
                    "com_reputacao_teste": resumo["consensus_accuracy_weighted_on_tests"],
                    "sem_reputacao_teste": resumo["consensus_accuracy_majority_on_tests"],
                    "com_reputacao_todas": resumo["consensus_accuracy_weighted"],
                    "n_audited": resumo.get("n_audited", ""),
                    "audited_rounds": " ".join(str(r) for r in resumo.get("audited_rounds", [])),
                    "mean_pct_honest_exact": resumo.get("mean_pct_honest_exact", ""),
                    "auditor_malicioso": dinamico.get("auditor_malicious_rounds", ""),
                    "vetos_auditor_malicioso": dinamico.get("auditor_malicious_vetoes", ""),
                })
                print(exp_id, linhas[-1]["com_reputacao_teste"], linhas[-1]["n_audited"])
    destino = os.path.join(SAIDA, "execucoes.csv")
    with open(destino, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CAMPOS)
        writer.writeheader()
        writer.writerows(linhas)
    print(f"{len(linhas)} execuções -> {destino}")


if __name__ == "__main__":
    main()
