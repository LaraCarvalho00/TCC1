"""Agrega a matriz reexecutada em CSVs por cenário.

Não altera o experimento. Lê ``rounds.csv`` e ``per_node.csv`` de cada
execução e grava a média entre as sementes.

Uso::

    python -m sistema.scripts.exportar_cenarios sistema/results/matriz_reexecucao
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_DEFAULT_MATRIX = os.path.join(
    os.path.dirname(__file__), "..", "results", "matriz_reexecucao"
)
_DEFAULT_OUT = os.path.join(
    os.path.dirname(__file__), "..", "resultados", "teste_fixo"
)

RODADA_FIELDS = [
    "nos",
    "maliciosos_pct",
    "maliciosos_reais",
    "n_maliciosos",
    "conluio",
    "mecanismo",
    "n_sementes",
    "intervalo_teste",
    "rodada",
    "rodada_teste",
    "acuracia_ponderada",
    "acuracia_maioria",
    "reputacao_honesta",
    "reputacao_maliciosa",
]

TESTE_FIELDS = [
    "nos",
    "maliciosos_pct",
    "maliciosos_reais",
    "n_maliciosos",
    "conluio",
    "mecanismo",
    "n_sementes",
    "intervalo_teste",
    "rodadas_teste",
    "acuracia_ponderada_teste",
    "acuracia_maioria_teste",
]

SEMENTE_FIELDS = [
    "nos",
    "maliciosos_pct",
    "maliciosos_reais",
    "n_maliciosos",
    "conluio",
    "mecanismo",
    "semente",
    "intervalo_teste",
    "rodada_teste",
]


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.4f}"


def _read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: str, fields: list[str], rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _scenario_name(nodes: str, mal_pct: str, collusion: str, mechanism: str) -> str:
    lado = "com" if str(collusion) == "1" else "sem"
    return f"n{nodes}_m{int(float(mal_pct)):02d}_{lado}_{mechanism}"


def _meta(sample: dict, n_seeds: int) -> dict:
    return {
        "nos": sample["nodes"],
        "maliciosos_pct": sample["malicious_pct"],
        "maliciosos_reais": sample["malicious_pct_actual"],
        "n_maliciosos": sample["n_malicious"],
        "conluio": sample["collusion"],
        "mecanismo": sample["mechanism"],
        "n_sementes": n_seeds,
        "intervalo_teste": sample["test_every"],
    }


def export(matrix_dir: str, out_dir: str) -> None:
    index = _read_csv(os.path.join(matrix_dir, "matrix_index.csv"))
    if not index:
        raise SystemExit(f"Índice vazio: {matrix_dir}")

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in index:
        key = (row["nodes"], row["malicious_pct"], row["collusion"], row["mechanism"])
        groups[key].append(row)

    por_dir = os.path.join(out_dir, "por_rodada")
    teste_dir = os.path.join(out_dir, "acuracia_teste")
    os.makedirs(por_dir, exist_ok=True)
    os.makedirs(teste_dir, exist_ok=True)

    seed_rows: list[dict] = []
    teste_rows: list[dict] = []
    round_rows_by_name: dict[str, list[dict]] = {}
    intervalos = set()
    calendarios = set()

    for key in sorted(groups, key=lambda item: (int(item[0]), float(item[1]), int(item[2]), item[3])):
        runs = sorted(groups[key], key=lambda row: int(row["seed"]))
        name = _scenario_name(*key)
        meta = _meta(runs[0], len(runs))
        intervalos.add(str(runs[0]["test_every"]))

        acc_w: dict[int, list[float]] = defaultdict(list)
        acc_m: dict[int, list[float]] = defaultdict(list)
        rep_h: dict[int, list[float]] = defaultdict(list)
        rep_mal: dict[int, list[float]] = defaultdict(list)
        test_rounds_seen: set[int] = set()

        for run in runs:
            folder = run["output_dir"]
            rounds = _read_csv(os.path.join(folder, "rounds.csv"))
            nodes = _read_csv(os.path.join(folder, "per_node.csv"))
            honest: dict[int, list[float]] = defaultdict(list)
            malicious: dict[int, list[float]] = defaultdict(list)
            for record in nodes:
                bruto = record.get("reputation_after", "")
                if bruto == "":
                    continue
                rodada = int(record["round_index"]) + 1
                value = float(bruto)
                if record["profile"] == "honest":
                    honest[rodada].append(value)
                elif record["profile"] == "malicious":
                    malicious[rodada].append(value)
            seed_tests: list[int] = []
            for record in rounds:
                rodada = int(record["round_index"]) + 1
                acc_w[rodada].append(float(record["consensus_correct"]))
                acc_m[rodada].append(float(record["majority_correct"]))
                if honest[rodada]:
                    rep_h[rodada].append(_mean(honest[rodada]))
                if malicious[rodada]:
                    rep_mal[rodada].append(_mean(malicious[rodada]))
                if str(record.get("is_test", "0")) == "1":
                    marcada = int(record["test_round"])
                    seed_tests.append(marcada)
                    test_rounds_seen.add(marcada)
            for rodada in seed_tests:
                seed_rows.append({
                    "nos": meta["nos"],
                    "maliciosos_pct": meta["maliciosos_pct"],
                    "maliciosos_reais": meta["maliciosos_reais"],
                    "n_maliciosos": meta["n_maliciosos"],
                    "conluio": meta["conluio"],
                    "mecanismo": meta["mecanismo"],
                    "semente": run["seed"],
                    "intervalo_teste": meta["intervalo_teste"],
                    "rodada_teste": rodada,
                })

        rodadas = sorted(acc_w)
        calendario = tuple(sorted(test_rounds_seen))
        calendarios.add(calendario)
        linhas = []
        for rodada in rodadas:
            linhas.append({
                **meta,
                "rodada": rodada,
                "rodada_teste": rodada if rodada in test_rounds_seen else "",
                "acuracia_ponderada": _fmt(_mean(acc_w[rodada])),
                "acuracia_maioria": _fmt(_mean(acc_m[rodada])),
                "reputacao_honesta": _fmt(_mean(rep_h[rodada])),
                "reputacao_maliciosa": _fmt(_mean(rep_mal[rodada])),
            })
        _write_csv(os.path.join(por_dir, f"{name}.csv"), RODADA_FIELDS, linhas)
        round_rows_by_name[name] = linhas

        testes_deste = [rodada for rodada in rodadas if rodada in test_rounds_seen]
        peso = [acc_w[rodada] for rodada in testes_deste]
        maioria = [acc_m[rodada] for rodada in testes_deste]
        plano = [valor for grupo in peso for valor in grupo]
        base = [valor for grupo in maioria for valor in grupo]
        teste_rows.append({
            **meta,
            "rodadas_teste": "|".join(str(rodada) for rodada in testes_deste),
            "acuracia_ponderada_teste": _fmt(_mean(plano)),
            "acuracia_maioria_teste": _fmt(_mean(base)),
        })
        _write_csv(
            os.path.join(teste_dir, f"{name}.csv"),
            TESTE_FIELDS,
            [teste_rows[-1]],
        )

    _write_csv(
        os.path.join(out_dir, "rodadas_teste_por_semente.csv"),
        SEMENTE_FIELDS,
        seed_rows,
    )
    _write_csv(os.path.join(out_dir, "acuracia_teste.csv"), TESTE_FIELDS, teste_rows)
    _write_analise(out_dir, teste_rows, round_rows_by_name)

    esperado = (10, 20, 30, 40, 50)
    if intervalos != {"10"} or calendarios != {esperado}:
        raise SystemExit(
            f"Calendário inesperado: intervalos={sorted(intervalos)} calendarios={calendarios}"
        )
    intervalo = int(next(iter(intervalos)))
    calendario = list(next(iter(calendarios)))
    manifesto = {
        "intervalo_teste": intervalo,
        "rodadas_teste": calendario,
        "n_cenarios": len(teste_rows),
        "n_execucoes": len(index),
        "cenarios": [
            _scenario_name(row["nos"], row["maliciosos_pct"], row["conluio"], row["mecanismo"])
            for row in teste_rows
        ],
    }
    with open(os.path.join(out_dir, "rodadas_teste.json"), "w", encoding="utf-8") as handle:
        json.dump(manifesto, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"Cenários: {len(teste_rows)}")
    print(f"Intervalo único: {intervalo}. Rodadas de teste: {calendario}")
    print(f"Pasta: {out_dir}")


def _write_analise(out_dir: str, teste_rows: list[dict], por_rodada: dict[str, list[dict]]) -> None:
    analise = os.path.join(out_dir, "analise")
    os.makedirs(analise, exist_ok=True)

    lado: dict[tuple, dict] = {}
    for row in teste_rows:
        chave = (row["nos"], row["maliciosos_pct"], row["mecanismo"])
        lado.setdefault(chave, {})
        lado[chave]["com" if str(row["conluio"]) == "1" else "sem"] = row

    comparacao = []
    for chave in sorted(lado, key=lambda item: (int(item[0]), int(item[1]), item[2])):
        nos, pct, mecanismo = chave
        sem = lado[chave].get("sem", {})
        com = lado[chave].get("com", {})
        comparacao.append({
            "nos": nos,
            "maliciosos_pct": pct,
            "maliciosos_reais": (sem or com).get("maliciosos_reais", ""),
            "mecanismo": mecanismo,
            "ponderado_sem_conluio": sem.get("acuracia_ponderada_teste", ""),
            "maioria_sem_conluio": sem.get("acuracia_maioria_teste", ""),
            "ponderado_com_conluio": com.get("acuracia_ponderada_teste", ""),
            "maioria_com_conluio": com.get("acuracia_maioria_teste", ""),
        })
    _write_csv(
        os.path.join(analise, "acuracia_teste_todos_cenarios.csv"),
        [
            "nos",
            "maliciosos_pct",
            "maliciosos_reais",
            "mecanismo",
            "ponderado_sem_conluio",
            "maioria_sem_conluio",
            "ponderado_com_conluio",
            "maioria_com_conluio",
        ],
        comparacao,
    )

    checkpoints = []
    for name, linhas in sorted(por_rodada.items()):
        for linha in linhas:
            if int(linha["rodada"]) not in (10, 20, 30, 40, 50):
                continue
            checkpoints.append({
                "cenario": name,
                "nos": linha["nos"],
                "maliciosos_pct": linha["maliciosos_pct"],
                "maliciosos_reais": linha["maliciosos_reais"],
                "conluio": linha["conluio"],
                "mecanismo": linha["mecanismo"],
                "rodada": linha["rodada"],
                "rodada_teste": linha["rodada_teste"],
                "acuracia_ponderada": linha["acuracia_ponderada"],
                "acuracia_maioria": linha["acuracia_maioria"],
                "reputacao_honesta": linha["reputacao_honesta"],
                "reputacao_maliciosa": linha["reputacao_maliciosa"],
            })
    _write_csv(
        os.path.join(analise, "rodadas_10_20_30_40_50.csv"),
        [
            "cenario",
            "nos",
            "maliciosos_pct",
            "maliciosos_reais",
            "conluio",
            "mecanismo",
            "rodada",
            "rodada_teste",
            "acuracia_ponderada",
            "acuracia_maioria",
            "reputacao_honesta",
            "reputacao_maliciosa",
        ],
        checkpoints,
    )

    sessenta = []
    for row in teste_rows:
        if str(row["maliciosos_pct"]) != "65" or str(row["conluio"]) != "1":
            continue
        nome = _scenario_name(row["nos"], row["maliciosos_pct"], row["conluio"], row["mecanismo"])
        por_teste = {
            int(linha["rodada"]): linha
            for linha in por_rodada[nome]
            if int(linha["rodada"]) in (10, 20, 30, 40, 50)
        }
        registro = {
            "nos": row["nos"],
            "maliciosos_reais": row["maliciosos_reais"],
            "n_maliciosos": row["n_maliciosos"],
            "mecanismo": row["mecanismo"],
            "acuracia_ponderada_teste": row["acuracia_ponderada_teste"],
            "acuracia_maioria_teste": row["acuracia_maioria_teste"],
        }
        for rodada in (10, 20, 30, 40, 50):
            registro[f"ponderado_r{rodada}"] = por_teste[rodada]["acuracia_ponderada"]
            registro[f"maioria_r{rodada}"] = por_teste[rodada]["acuracia_maioria"]
        sessenta.append(registro)
    campos = [
        "nos",
        "maliciosos_reais",
        "n_maliciosos",
        "mecanismo",
        "acuracia_ponderada_teste",
        "acuracia_maioria_teste",
    ]
    for rodada in (10, 20, 30, 40, 50):
        campos.extend([f"ponderado_r{rodada}", f"maioria_r{rodada}"])
    _write_csv(os.path.join(analise, "cenario_65_conluio.csv"), campos, sessenta)


if __name__ == "__main__":
    matriz = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_MATRIX
    destino = sys.argv[2] if len(sys.argv) > 2 else _DEFAULT_OUT
    export(matriz, destino)
