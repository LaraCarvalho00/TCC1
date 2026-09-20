"""Harness da grade experimental: envolve a simulação existente.

Uso:
    python -m sistema.scripts.run_harness --piloto
    python -m sistema.scripts.run_harness --repeticoes 30
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional

from ..core import behavior
from ..core.experiment_spec import (
    COLLUSION_VALUE,
    CONFIGS,
    INTERPRETACAO_SPLIT,
    LEVELS,
    NETWORK_SIZES,
    P_NOMINAL,
    assign_profiles,
    derive_seed,
    iter_cells,
    n_problematicos,
    split_instaveis,
    uses_collusion,
)
from ..simulate import execute_simulation

_DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "results", "harness")
REPUTATION_NS = {10, 30, 50}

RESULT_FIELDS = [
    "N",
    "nivel",
    "p_nominal",
    "p_efetivo",
    "n_maliciosos",
    "n_instaveis",
    "n_honestos",
    "configuracao",
    "interpretacao_instaveis",
    "seed",
    "rodadas",
    "limiar_reputacao",
    "acuracia",
    "acuracia_normalizada",
    "precisao_reputacao",
    "recall_reputacao",
    "tempo_execucao_s",
    "acuracia_maioria",
    "latencia_media_ms",
    "p_falha",
]

REP_FIELDS = [
    "N",
    "nivel",
    "configuracao",
    "seed",
    "rodada",
    "grupo",
    "reputacao_media",
    "reputacao_desvio",
]

PILOTO_SIZES = (5, 25, 50)
PILOTO_LEVELS = ("p0", "p40", "p80")
PILOTO_CONFIGS = ("sem_conluio",)
PILOTO_REPS = 3


def _fmt(value: Optional[float], digits: int = 4) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def _cell_key(n: int, nivel: str, configuracao: str, seed: int) -> tuple:
    return (int(n), str(nivel), str(configuracao), int(seed))


def load_done(path: str) -> set[tuple]:
    done: set[tuple] = set()
    if not os.path.isfile(path):
        return done
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            done.add(_cell_key(row["N"], row["nivel"], row["configuracao"], row["seed"]))
    return done


def append_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    exists = os.path.isfile(path) and os.path.getsize(path) > 0
    with open(path, "a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def read_rows(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def refresh_normalized(path: str) -> None:
    rows = read_rows(path)
    if not rows:
        return
    refs: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        if row["nivel"] != "p0":
            continue
        acc = float(row["acuracia"])
        refs.setdefault((row["N"], row["configuracao"]), []).append(acc)
    means = {key: statistics.mean(values) for key, values in refs.items()}
    for row in rows:
        ref = means.get((row["N"], row["configuracao"]))
        if ref is None or ref == 0:
            row["acuracia_normalizada"] = ""
        else:
            row["acuracia_normalizada"] = _fmt(float(row["acuracia"]) / ref)
    write_rows(path, RESULT_FIELDS, rows)


def reputation_metrics(
    profiles: dict[str, str],
    reputations: dict[str, float],
    threshold: float,
) -> tuple[Optional[float], Optional[float]]:
    mal = [node for node, profile in profiles.items() if profile == behavior.MALICIOUS]
    hon = [node for node, profile in profiles.items() if profile == behavior.HONEST]
    tp = sum(1 for node in mal if reputations[node] < threshold)
    fp = sum(1 for node in hon if reputations[node] < threshold)
    fn = sum(1 for node in mal if reputations[node] >= threshold)
    precisao = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if mal else None
    return precisao, recall


def reputation_rows_for_run(
    n: int,
    nivel: str,
    configuracao: str,
    seed: int,
    profiles: dict[str, str],
    history: dict[str, list[float]],
    rounds: int,
) -> list[dict]:
    groups = {
        "honestos": [node for node, profile in profiles.items() if profile == behavior.HONEST],
        "maliciosos": [node for node, profile in profiles.items() if profile == behavior.MALICIOUS],
        "instaveis": [node for node, profile in profiles.items() if profile == behavior.UNSTABLE],
    }
    rows = []
    for round_index in range(rounds):
        for grupo, nodes in groups.items():
            if not nodes:
                continue
            values = [history[node][round_index + 1] for node in nodes]
            desvio = statistics.stdev(values) if len(values) > 1 else 0.0
            rows.append(
                {
                    "N": n,
                    "nivel": nivel,
                    "configuracao": configuracao,
                    "seed": seed,
                    "rodada": round_index,
                    "grupo": grupo,
                    "reputacao_media": _fmt(statistics.mean(values)),
                    "reputacao_desvio": _fmt(desvio),
                }
            )
    return rows


def _cpu_model() -> str:
    ident = platform.processor() or ""
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            ident = winreg.QueryValueEx(key, "ProcessorNameString")[0]
            winreg.CloseKey(key)
        except OSError:
            pass
    return ident.strip() or platform.machine()


def _ram_gb() -> Optional[float]:
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return round(stat.ullTotalPhys / (1024**3), 2)
    except (AttributeError, OSError, ValueError):
        pass
    return None


def _lib_versions() -> dict[str, str]:
    versions = {}
    for name in ("numpy", "matplotlib", "yaml", "httpx"):
        try:
            module = __import__(name)
            versions[name] = getattr(module, "__version__", "unknown")
        except ImportError:
            versions[name] = "nao instalado"
    return versions


def write_ambiente(path: str, payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def run_cell(
    n: int,
    nivel: str,
    configuracao: str,
    seed: int,
    *,
    rounds: int,
    limiar: float,
    interpretacao: str,
    p_falha: float,
    alpha: float,
    min_confidence: float,
) -> tuple[dict, list[dict]]:
    n_problema = n_problematicos(n, nivel)
    n_mal, n_unst = split_instaveis(n_problema, configuracao, interpretacao, n=n)
    profiles = assign_profiles(n, n_mal, n_unst, seed)
    n_hon = sum(1 for profile in profiles.values() if profile == behavior.HONEST)
    collusion = COLLUSION_VALUE if uses_collusion(configuracao) else None

    started = time.perf_counter()
    summary = execute_simulation(
        profiles=profiles,
        rounds=rounds,
        seed=seed,
        alpha=alpha,
        min_confidence=min_confidence,
        collusion_value=collusion,
        unstable_p_drop=p_falha,
        persist=False,
    )
    elapsed = time.perf_counter() - started
    reputations = summary["final_reputation_by_node"]
    precisao, recall = reputation_metrics(profiles, reputations, limiar)
    p_nominal = P_NOMINAL[nivel]
    row = {
        "N": n,
        "nivel": nivel,
        "p_nominal": "" if p_nominal is None else _fmt(p_nominal, 2),
        "p_efetivo": _fmt(n_mal / n),
        "n_maliciosos": n_mal,
        "n_instaveis": n_unst,
        "n_honestos": n_hon,
        "configuracao": configuracao,
        "interpretacao_instaveis": interpretacao,
        "seed": seed,
        "rodadas": rounds,
        "limiar_reputacao": _fmt(limiar, 2),
        "acuracia": _fmt(summary["consensus_accuracy_weighted"]),
        "acuracia_normalizada": "",
        "precisao_reputacao": _fmt(precisao),
        "recall_reputacao": _fmt(recall),
        "tempo_execucao_s": _fmt(elapsed, 6),
        "acuracia_maioria": _fmt(summary["consensus_accuracy_majority"]),
        "latencia_media_ms": summary["mean_latency_ms"],
        "p_falha": _fmt(p_falha, 2),
    }
    rep_rows = []
    if n in REPUTATION_NS:
        rep_rows = reputation_rows_for_run(
            n,
            nivel,
            configuracao,
            seed,
            profiles,
            summary["reputation_history"],
            rounds,
        )
    return row, rep_rows


def planned_jobs(
    sizes,
    levels,
    configs,
    repeticoes: int,
) -> list[tuple[int, str, str, int, int]]:
    jobs = []
    for n, nivel, configuracao in iter_cells(sizes, levels, configs):
        for indice in range(repeticoes):
            seed = derive_seed(n, nivel, configuracao, indice)
            jobs.append((n, nivel, configuracao, indice, seed))
    return jobs


def run_jobs(
    jobs: list[tuple[int, str, str, int, int]],
    *,
    out_dir: str,
    rounds: int,
    limiar: float,
    interpretacao: str,
    p_falha: float,
    alpha: float,
    min_confidence: float,
    label: str,
) -> list[float]:
    results_path = os.path.join(out_dir, "resultados.csv")
    rep_path = os.path.join(out_dir, "reputacao_por_rodada.csv")
    done = load_done(results_path)
    times: list[float] = []
    pending = [job for job in jobs if _cell_key(job[0], job[1], job[2], job[4]) not in done]
    total = len(pending)
    print(f"{label}: {total} execuções pendentes de {len(jobs)} planejadas.")
    for index, (n, nivel, configuracao, _indice, seed) in enumerate(pending, start=1):
        row, rep_rows = run_cell(
            n,
            nivel,
            configuracao,
            seed,
            rounds=rounds,
            limiar=limiar,
            interpretacao=interpretacao,
            p_falha=p_falha,
            alpha=alpha,
            min_confidence=min_confidence,
        )
        append_csv(results_path, RESULT_FIELDS, [row])
        if rep_rows:
            append_csv(rep_path, REP_FIELDS, rep_rows)
        elapsed = float(row["tempo_execucao_s"])
        times.append(elapsed)
        if index == 1 or index % 25 == 0 or index == total:
            print(
                f"  [{index}/{total}] N={n} {nivel} {configuracao} seed={seed} "
                f"t={elapsed:.4f}s acc={row['acuracia']}"
            )
    refresh_normalized(results_path)
    return times


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grade experimental do TCC (harness).")
    parser.add_argument("--repeticoes", type=int, default=30)
    parser.add_argument("--rodadas", type=int, default=30)
    parser.add_argument("--limiar-reputacao", type=float, default=0.5)
    parser.add_argument("--interpretacao", choices=("split", "extra"), default=INTERPRETACAO_SPLIT)
    parser.add_argument("--p-falha", type=float, default=0.3)
    parser.add_argument("--alpha", type=float, default=0.25)
    parser.add_argument("--min-confidence", type=float, default=0.55)
    parser.add_argument("--output", default=_DEFAULT_OUT)
    parser.add_argument("--piloto", action="store_true", help="Só a grade mínima de calibração.")
    parser.add_argument(
        "--completar",
        action="store_true",
        help="Roda a grade completa (depois do piloto, se ambos).",
    )
    parser.add_argument(
        "--max-horas",
        type=float,
        default=3.0,
        help="Se a estimativa de 30 sementes passar disso, cai para 10.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    out_dir = os.path.abspath(args.output)
    os.makedirs(out_dir, exist_ok=True)
    ambiente_path = os.path.join(out_dir, "ambiente.json")
    started = datetime.now(timezone.utc)
    wall0 = time.perf_counter()
    ambiente = {
        "cpu_modelo": _cpu_model(),
        "nucleos": os.cpu_count(),
        "ram_gb": _ram_gb(),
        "sistema_operacional": f"{platform.system()} {platform.release()} ({platform.version()})",
        "runtime": platform.python_version(),
        "implementacao": platform.python_implementation(),
        "bibliotecas": _lib_versions(),
        "inicio_utc": started.isoformat(),
        "fim_utc": None,
        "tempo_total_s": None,
        "parametros": {
            "rodadas": args.rodadas,
            "repeticoes_solicitadas": args.repeticoes,
            "limiar_reputacao": args.limiar_reputacao,
            "interpretacao_instaveis": args.interpretacao,
            "p_falha": args.p_falha,
            "desempate_split": "sobra_para_malicioso",
            "orquestrador": "node-0 sempre honesto, conta em N, fora do sorteio",
            "conluio": f"valor fixo {COLLUSION_VALUE} (mesmo mecanismo já existente)",
            "alpha": args.alpha,
            "min_confidence": args.min_confidence,
        },
        "piloto": None,
        "estimativas": None,
        "repeticoes_efetivas": None,
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

    piloto_jobs = planned_jobs(PILOTO_SIZES, PILOTO_LEVELS, PILOTO_CONFIGS, PILOTO_REPS)
    piloto_times = run_jobs(piloto_jobs, label="Piloto", **common)
    n_piloto = len(PILOTO_SIZES) * len(PILOTO_LEVELS) * len(PILOTO_CONFIGS) * PILOTO_REPS
    mean_t = statistics.mean(piloto_times) if piloto_times else 0.0
    # 240 células; o piloto já cobriu 9 células × 3 sementes da config sem_conluio
    est_30 = mean_t * 240 * 30
    est_10 = mean_t * 240 * 10
    ambiente["piloto"] = {
        "execucoes": n_piloto,
        "tempos_s": [round(t, 6) for t in piloto_times],
        "tempo_medio_s": round(mean_t, 6),
        "tempo_min_s": round(min(piloto_times), 6) if piloto_times else None,
        "tempo_max_s": round(max(piloto_times), 6) if piloto_times else None,
    }
    ambiente["estimativas"] = {
        "grade_240x30_s": round(est_30, 1),
        "grade_240x30_h": round(est_30 / 3600, 3),
        "grade_240x10_s": round(est_10, 1),
        "grade_240x10_h": round(est_10 / 3600, 3),
        "nota": "Estimativa pelo tempo médio do piloto (inclui células já feitas).",
    }
    write_ambiente(ambiente_path, ambiente)
    print("\n=== Piloto ===")
    print(f"Tempo médio por execução: {mean_t:.4f}s  (min={min(piloto_times):.4f}s max={max(piloto_times):.4f}s)")
    print(f"Estimativa 240×30: {est_30/3600:.2f} h  ({est_30:.0f}s)")
    print(f"Estimativa 240×10: {est_10/3600:.2f} h  ({est_10:.0f}s)")

    if args.piloto and not args.completar:
        ambiente["repeticoes_efetivas"] = PILOTO_REPS
        ambiente["fim_utc"] = datetime.now(timezone.utc).isoformat()
        ambiente["tempo_total_s"] = round(time.perf_counter() - wall0, 2)
        write_ambiente(ambiente_path, ambiente)
        print("Piloto concluído (--piloto sem --completar).")
        return

    repeticoes = args.repeticoes
    if est_30 / 3600 > args.max_horas and args.repeticoes > 10:
        print(
            f"\nEstimativa de {est_30/3600:.2f} h para 30 sementes > {args.max_horas} h. "
            "Caindo para 10 sementes."
        )
        repeticoes = 10
    ambiente["repeticoes_efetivas"] = repeticoes
    write_ambiente(ambiente_path, ambiente)

    full_jobs = planned_jobs(NETWORK_SIZES, LEVELS, CONFIGS, repeticoes)
    run_jobs(full_jobs, label=f"Grade completa ({repeticoes} sementes)", **common)

    ambiente["fim_utc"] = datetime.now(timezone.utc).isoformat()
    ambiente["tempo_total_s"] = round(time.perf_counter() - wall0, 2)
    write_ambiente(ambiente_path, ambiente)
    print(f"\nConcluído em {ambiente['tempo_total_s']}s. Saída: {out_dir}")


if __name__ == "__main__":
    main()
