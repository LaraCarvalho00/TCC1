"""Compara os cenários do orquestrador dinâmico em containers com a simulação.

Para cada cenário de ``validate_docker_dynamic.ps1`` lê o ``summary.json`` dos
containers e roda a simulação local com os mesmos parâmetros, na mesma
repetição (``--seed 7``) e em mais quatro repetições (8 a 11). Os sorteios de
resposta não são os mesmos (cada container tem o próprio gerador), então a
comparação é de comportamento: quem lidera, o que é anulado, se a cadeia se
divide e a acurácia nas rodadas de teste. A tabela vai para
``sistema/resultados/orquestrador_dinamico/docker_vs_simulacao.md``.

Uso::

    python -m sistema.scripts.compare_docker_dynamic
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import tempfile

from ..simulate import parse_args, run_simulation

BASE = os.path.join("sistema", "results", "docker_orquestrador_dinamico")
OUT = os.path.join("sistema", "resultados", "orquestrador_dinamico")
REPETITIONS = (7, 8, 9, 10, 11)

SCENARIOS = {
    "n4_star_m25_forge": dict(nodes=4, malicious=0.25, topology="star", degree=3, attack="forge", defense="all"),
    "n4_kregular_m25_forge": dict(nodes=4, malicious=0.25, topology="kregular", degree=2, attack="forge", defense="all"),
    "n10_kregular_m25_censor": dict(nodes=10, malicious=0.25, topology="kregular", degree=4, attack="censor", defense="all"),
    "n20_kregular_m65_forge": dict(nodes=20, malicious=0.65, topology="kregular", degree=4, attack="forge", defense="all"),
    "n20_kregular_m65_forge_none": dict(nodes=20, malicious=0.65, topology="kregular", degree=4, attack="forge", defense="none"),
}

FIELDS = (
    "consensus_accuracy_weighted",
    "consensus_accuracy_weighted_on_tests",
    "rep_honest",
    "rep_malicious",
    "leader_malicious_rounds",
    "accepted_rounds",
    "voided_rounds",
    "forged_accepted",
    "censored_accepted",
    "chain_split_rounds",
    "n_chains_final",
    "malicious_power_mass_final",
    "mean_hops",
    "max_consecutive_same_leader",
)


def _flatten(summary: dict) -> dict:
    dyn = summary.get("dynamic", {})
    reps = summary.get("final_reputation_by_profile", {})
    row = {
        "consensus_accuracy_weighted": summary.get("consensus_accuracy_weighted"),
        "consensus_accuracy_weighted_on_tests": summary.get("consensus_accuracy_weighted_on_tests"),
        "rep_honest": reps.get("honest"),
        "rep_malicious": reps.get("malicious"),
    }
    for key in FIELDS[4:]:
        row[key] = dyn.get(key)
    return row


def _simulate(params: dict, seed: int) -> dict:
    argv = [
        "--nodes", str(params["nodes"]), "--malicious", str(params["malicious"]), "--rounds", "30",
        "--seed", str(seed), "--collusion-value", "999", "--mechanism", "beta",
        "--orchestration", "dynamic", "--signal", "hybrid", "--topology", params["topology"],
        "--degree", str(params["degree"]), "--defense", params["defense"], "--leader-attack", params["attack"],
        "--output", tempfile.mkdtemp(), "--overwrite", "--quiet", "--no-row-sync",
    ]
    return _flatten(run_simulation(parse_args(argv)))


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def main() -> None:
    rows = []
    lines = [
        "# Containers × simulação (orquestrador dinâmico, 30 rodadas)",
        "",
        "Docker = uma execução em containers (repetição 7). Sim r7 = simulação na mesma repetição. "
        "Sim média = média das repetições 7 a 11.",
        "",
        "Acurácia, liderança, anulações, forjas e massa maliciosa são medidas na cópia da cadeia "
        "seguida pela maioria dos honestos. A reputação final de cada nó é a da cópia que ele mesmo "
        "segue: depois de uma divisão, o conluio se dá nota alta na própria cadeia. "
        "Saltos nos containers seguem a ordem de chegada das mensagens, por isso podem passar "
        "um pouco da menor distância usada na simulação.",
        "",
    ]
    for scenario, params in SCENARIOS.items():
        path = os.path.join(BASE, scenario, "summary.json")
        if not os.path.exists(path):
            print(f"[faltando] {path}")
            continue
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        docker = _flatten(payload["summary"])
        sims = [_simulate(params, seed) for seed in REPETITIONS]
        mean = {
            k: (statistics.fmean([s[k] for s in sims if s[k] is not None]) if any(s[k] is not None for s in sims) else None)
            for k in FIELDS
        }
        lines += [
            f"## {scenario}",
            "",
            f"Cadeias válidas em todos os nós: {'sim' if payload['config'].get('ledgers_valid') else 'não'}.",
            "",
            "| métrica | Docker | Sim r7 | Sim média |",
            "|---|---|---|---|",
        ]
        for key in FIELDS:
            lines.append(f"| {key} | {_fmt(docker[key])} | {_fmt(sims[0][key])} | {_fmt(mean[key])} |")
            rows.append({"scenario": scenario, "metric": key, "docker": docker[key], "sim_r7": sims[0][key], "sim_mean": mean[key]})
        lines.append("")

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "docker_vs_simulacao.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(OUT, "docker_vs_simulacao.csv"), "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["scenario", "metric", "docker", "sim_r7", "sim_mean"])
        writer.writeheader()
        writer.writerows(rows)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
