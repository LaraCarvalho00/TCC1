"""Experimentos complementares do artigo: sensibilidade, instabilidade e contraste.

As duas primeiras séries têm 120 e 30 execuções. O contraste auxiliar, fora
das 3.670 execuções principais, tem 10. O banco é previamente gerado e contém
50 tarefas e 20 respostas do modelo por tarefa; não executamos a LLM aqui.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import traceback
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sistema.aplicacao.configuracao import argumentos_simulacao
from sistema.core.answer import normalize
from sistema.simulate import run_simulation

FRACOES = (0.5, 0.65, 0.8)
SEMENTES = range(5)


def trabalhos_sensibilidade() -> list[dict]:
    # A subida lenta de referência já integra a matriz de 2.560 execuções.
    variacoes = [("ema", c, g) for c in (0.05, 0.30) for g in (0.5, 0.8, 0.95)]
    variacoes += [("ema_asymmetric", 0.05, 0.8), ("beta", 0.05, 0.8)]
    return [dict(serie="sensibilidade", mecanismo=m, alpha_consenso=c, alpha_gabarito=g,
                 fracao=frac, instaveis=0.0, semente=seed)
            for (m, c, g), frac, seed in itertools.product(variacoes, FRACOES, SEMENTES)]


def trabalhos_instabilidade() -> list[dict]:
    return [dict(serie="instabilidade", mecanismo="ema_slow_up", alpha_consenso=0.05,
                 alpha_gabarito=0.8, fracao=frac, instaveis=instavel, semente=seed)
            for instavel, frac, seed in itertools.product((0.1, 0.2), FRACOES, SEMENTES)]


def trabalhos_contraste() -> list[dict]:
    return [dict(serie="contraste", mecanismo="ema", alpha_consenso=0.05,
                 alpha_gabarito=0.8, fracao=0.5, instaveis=0.0, semente=seed,
                 estrategia=estrategia)
            for estrategia, seed in itertools.product(("on_off", "knows_schedule"), SEMENTES)]


def carregar_banco(path: str | Path) -> tuple[list[dict], dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tasks = data["tarefas"]
    if len(tasks) != 50 or any(len(item["amostras"]) != 20 for item in tasks):
        raise ValueError("O artigo requer 50 tarefas e 20 amostras por tarefa")
    if len({item["id"] for item in tasks}) != len(tasks):
        raise ValueError("O banco contém identificadores de tarefa repetidos")
    questions = [{"id": x["id"], "question": x["question"], "answer": x["answer"]} for x in tasks]
    answers = {x["id"]: [normalize(y["resposta"]) for y in x["amostras"]] for x in tasks}
    return questions, answers


def executar(job: dict, tarefas: list[dict], banco: dict) -> dict:
    """Uma combinação, com diretório temporário e métricas por execução."""
    contraste = job["serie"] == "contraste"
    with tempfile.TemporaryDirectory(prefix="experimento_complementar_") as temp:
        args = argumentos_simulacao(
            "run", nodes=50, rounds=50, malicious=job["fracao"], unstable=job["instaveis"],
            seed=job["semente"], output=temp, experiment_id="run", orchestration="dynamic",
            topology="kregular", degree=4, defense="all", signal="hybrid" if contraste else "consensus",
            calibration_rounds=3 if contraste else 0, mechanism=job["mecanismo"],
            consensus_alpha=job["alpha_consenso"], oracle_alpha=job["alpha_gabarito"],
            consensus_mode="distance", malicious_answer="noise",
            malicious_strategy=job.get("estrategia", "knows_schedule"), honest_rounds=5,
            leader_attack="none", auditor_attack="none", audit_mode="fixed" if contraste else "random",
            audit_p=0.2, unstable_mode="attribute" if job["instaveis"] else "profile",
            quiet=True, row_sync=False, overwrite=True,
        )
        args.tasks = tarefas
        args.answer_bank = banco
        args.collusion_value = 999
        args.leaderless_calibration = contraste
        args.noise_mode = "multiplicative" if contraste else "relative"
        args.noise_distance = 0.2
        args.validation_score = "graded" if contraste else "exact"
        args.consensus_center = "medoid"
        result = run_simulation(args)
    dynamic = result.get("dynamic") or {}
    return {
        **job, "n_maliciosos": round(job["fracao"] * 50),
        "com_reputacao_sem_gabarito": result["consensus_accuracy_weighted_no_oracle"],
        "sem_reputacao_sem_gabarito": result["consensus_accuracy_majority_no_oracle"],
        "com_reputacao_teste": result["consensus_accuracy_weighted_on_tests"],
        "com_reputacao_todas": result["consensus_accuracy_weighted"],
        "instaveis_honestos": result.get("unstable_honest", 0),
        "instaveis_maliciosos": result.get("unstable_malicious", 0),
        "rodadas_auditadas": result.get("n_audited", ""),
        "cadeias_no_fim": dynamic.get("n_chains_final", ""),
    }


def resumo(rows: list[dict]) -> list[dict]:
    keys = ("serie", "mecanismo", "alpha_consenso", "alpha_gabarito", "fracao", "instaveis", "estrategia")
    groups: dict[tuple, list[float]] = {}
    for row in rows:
        key = tuple(row.get(name, "") for name in keys)
        groups.setdefault(key, []).append(float(row["com_reputacao_sem_gabarito"]))
    return [dict(zip(keys, key), repeticoes=len(values),
                 acuracia_media=statistics.mean(values),
                 acuracia_dp=statistics.stdev(values) if len(values) > 1 else 0.0)
            for key, values in groups.items()]


def _escrever_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


_TAREFAS = None
_BANCO = None


def _iniciar_trabalhador(tarefas: list[dict], banco: dict) -> None:
    global _TAREFAS, _BANCO
    _TAREFAS, _BANCO = tarefas, banco


def _executar_trabalho(job: dict) -> dict:
    return executar(job, _TAREFAS, _BANCO)


def _git(*arguments: str) -> str | None:
    try:
        return subprocess.check_output(["git", *arguments], cwd=Path(__file__).resolve().parents[2],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _hashes_fontes() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    paths = list((root / "sistema" / "core").rglob("*.py"))
    paths.extend((root / "sistema" / "simulate.py", root / "sistema" / "aplicacao" / "configuracao.py", Path(__file__)))
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Séries complementares do artigo (dinâmico).")
    parser.add_argument("serie", choices=("sensibilidade", "instabilidade", "contraste", "todas"))
    parser.add_argument("--banco", required=True)
    parser.add_argument("--saida", required=True, help="Nova pasta de resultados")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers deve ser pelo menos 1")
    tasks, bank = carregar_banco(args.banco)
    plans = {"sensibilidade": trabalhos_sensibilidade, "instabilidade": trabalhos_instabilidade,
             "contraste": trabalhos_contraste}
    jobs = [job for name, builder in plans.items() if args.serie in (name, "todas") for job in builder()]
    output = Path(args.saida)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "serie": args.serie, "status": "em_andamento", "commit": _git("rev-parse", "HEAD"),
        "alteracoes_locais": _git("status", "--porcelain"), "sha256_fontes": _hashes_fontes(),
        "inicio_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
        "plataforma": platform.platform(), "workers": args.workers,
        "banco": str(Path(args.banco).resolve()),
        "banco_sha256": hashlib.sha256(Path(args.banco).read_bytes()).hexdigest(),
        "jobs": jobs, "concluidas": 0,
        "observacao": "Simulação local com respostas pré-geradas; não executa uma LLM por rodada.",
    }
    manifest_path = output / "manifesto.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    rows = []
    try:
        with (output / "progresso.jsonl").open("x", encoding="utf-8") as progress:
            with ProcessPoolExecutor(max_workers=args.workers, initializer=_iniciar_trabalhador,
                                     initargs=(tasks, bank)) as pool:
                for i, result in enumerate(pool.map(_executar_trabalho, jobs, chunksize=1), 1):
                    rows.append(result)
                    progress.write(json.dumps(result, ensure_ascii=False) + "\n")
                    progress.flush()
                    manifest["concluidas"] = i
                    print(f"{i}/{len(jobs)} {result['serie']}", flush=True)
        _escrever_csv(output / "execucoes.csv", rows)
        _escrever_csv(output / "resumo.csv", resumo(rows))
        manifest["status"] = "concluido"
    except BaseException:
        manifest["status"] = "falhou"
        manifest["erro"] = traceback.format_exc()
        raise
    finally:
        manifest["fim_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
