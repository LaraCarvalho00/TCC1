"""Dados da correção A4. Não altera os experimentos já existentes.

Chama ``sistema.simulate.run_simulation`` (o mesmo caminho de
``sistema.scripts.run_a3_n50``) e, em cada rodada, recalcula maioria simples
e consenso ponderado sobre o mesmo conjunto de respostas.

Uso, na raiz do repositório::

    .venv/bin/python entrega_a4/run_a4.py smoke
    .venv/bin/python entrega_a4/run_a4.py etapa2
    .venv/bin/python entrega_a4/run_a4.py etapa3
    .venv/bin/python entrega_a4/run_a4.py etapa4
    .venv/bin/python entrega_a4/run_a4.py figuras
    .venv/bin/python entrega_a4/run_a4.py all
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "entrega_a4")
FIG = os.path.join(OUT, "figuras")
PY = os.path.join(ROOT, ".venv", "bin", "python")
CMD_PREFIX = f'cd "{ROOT}" && "{PY}" entrega_a4/run_a4.py'

FRACTIONS_A3 = (0, 25, 50, 65, 80)
FRACTIONS_ALL = (0, 5, 20, 25, 35, 50, 65, 80)
SEEDS = (0, 1, 2, 3, 4)
MECHANISMS = ("ema", "ema_asymmetric", "beta")
ALPHAS_FIXO = (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
ORACLE_ALPHAS = (0.5, 0.8, 0.95)
CONSENSUS_ALPHAS = (0.05, 0.3)
CALIBRATION_KS = (0, 1, 2, 3, 4, 5)

TOL = 0.005

# Preenchido pelo processo trabalhador. Cada processo do Pool tem o seu.
_rounds: list[dict] = []
_installed = False
_orig_process = None
_orig_dynamic = None


def _install() -> None:
    global _installed, _orig_process, _orig_dynamic
    if _installed:
        return
    import sistema.simulate as sim

    _orig_process = sim.process_round
    _orig_dynamic = sim._dynamic_round

    def process_round(**kwargs):
        tracker = kwargs["tracker"]
        responses = kwargs["responses"]
        before = tracker.weights()
        result = _orig_process(**kwargs)
        after = tracker.weights()
        profiles = {r.node_id: r.profile for r in responses}
        ids = [r.node_id for r in responses]
        _append_round(
            round_index=kwargs["round_index"],
            is_test=bool(kwargs["is_test"]),
            expected=kwargs["expected"],
            responses=responses,
            profiles=profiles,
            before=before,
            after=after,
            power_before=before,
            power_after=after,
            ref_before=ids,
            ref_after=ids,
            protocol_w_ok=int(result.consensus_correct),
            protocol_m_ok=int(result.majority_correct),
        )
        return result

    def dynamic_round(network, logger, round_index, task_id, expected, responses, profiles, mechanism, initial, is_test):
        before = {n: network.group_of(n).state.consensus.get(n) for n in profiles}
        power_before = {n: network.group_of(n).state.power.get(n) for n in profiles}
        ref_before = list(network.reference_group().members)
        _orig_dynamic(
            network, logger, round_index, task_id, expected, responses, profiles, mechanism, initial, is_test,
        )
        after = {n: network.group_of(n).state.consensus.get(n) for n in profiles}
        power_after = {n: network.group_of(n).state.power.get(n) for n in profiles}
        ref_after = list(network.reference_group().members)
        last = logger.round_rows[-1]
        if int(last["round_index"]) != int(round_index):
            raise RuntimeError("a última linha de rounds.csv não é a rodada que acabou de terminar")
        _append_round(
            round_index=round_index,
            is_test=bool(is_test),
            expected=expected,
            responses=responses,
            profiles=profiles,
            before=before,
            after=after,
            power_before=power_before,
            power_after=power_after,
            ref_before=ref_before,
            ref_after=ref_after,
            protocol_w_ok=int(last["consensus_correct"]),
            protocol_m_ok=int(last["majority_correct"]),
        )

    sim.process_round = process_round
    sim._dynamic_round = dynamic_round
    _installed = True


def _sum_mean(mapping: dict, profiles: dict, profile: str) -> tuple[float | None, float | None]:
    vals = [mapping[n] for n, p in profiles.items() if p == profile and n in mapping]
    if not vals:
        return None, None
    return float(sum(vals)), float(sum(vals) / len(vals))


def _hit(answer, expected) -> int:
    return int(expected is not None and answer == expected)


def _append_round(
    *,
    round_index,
    is_test,
    expected,
    responses,
    profiles,
    before,
    after,
    power_before,
    power_after,
    ref_before,
    ref_after,
    protocol_w_ok,
    protocol_m_ok,
) -> None:
    from sistema.core.consensus import majority_consensus, weighted_consensus

    def agg(pairs):
        if not pairs:
            return 0, 0
        weighted = weighted_consensus(pairs, before)
        majority = majority_consensus(pairs)
        return _hit(weighted.answer, expected), _hit(majority.answer, expected)

    pairs_all = [(r.node_id, r.answer) for r in responses]
    after_ids = set(ref_after)
    before_ids = set(ref_before)
    w_all, m_all = agg(pairs_all)
    w_ref, m_ref = agg([p for p in pairs_all if p[0] in after_ids])
    w_vote, m_vote = agg([p for p in pairs_all if p[0] in before_ids])
    sum_hon_b, _ = _sum_mean(before, profiles, "honest")
    sum_mal_b, _ = _sum_mean(before, profiles, "malicious")
    _, mean_hon_a = _sum_mean(after, profiles, "honest")
    _, mean_mal_a = _sum_mean(after, profiles, "malicious")
    _, pow_hon_a = _sum_mean(power_after, profiles, "honest")
    _, pow_mal_a = _sum_mean(power_after, profiles, "malicious")
    _rounds.append({
        "round": int(round_index) + 1,
        "is_test": int(is_test),
        "n_nodes": len(responses),
        "n_ref_before": len(ref_before),
        "n_ref_after": len(ref_after),
        "protocol_w_ok": int(protocol_w_ok),
        "protocol_m_ok": int(protocol_m_ok),
        "w_all_ok": w_all,
        "m_all_ok": m_all,
        "w_ref_ok": w_ref,
        "m_ref_ok": m_ref,
        "w_vote_ok": w_vote,
        "m_vote_ok": m_vote,
        "sum_hon_before": sum_hon_b,
        "sum_mal_before": sum_mal_b,
        "rep_hon_after": mean_hon_a,
        "rep_mal_after": mean_mal_a,
        "power_hon_after": pow_hon_a,
        "power_mal_after": pow_mal_a,
    })


def _rate(series: list[dict], key: str, tests: bool) -> float | None:
    rows = [r for r in series if r["is_test"]] if tests else series
    if not rows:
        return None
    return sum(r[key] for r in rows) / len(rows)


def _at(series: list[dict], round_1based: int, key: str):
    for row in series:
        if row["round"] == round_1based:
            return row[key]
    return None


def _mean_between(series: list[dict], start: int, end: int, key: str):
    vals = [r[key] for r in series if start <= r["round"] <= end and r[key] is not None]
    if not vals:
        return None
    return float(sum(vals) / len(vals))


def _max_between(series: list[dict], start: int, end: int, key: str):
    vals = [r[key] for r in series if start <= r["round"] <= end and r[key] is not None]
    if not vals:
        return None
    return float(max(vals))


def _mean_of_rounds(series: list[dict], rounds: tuple[int, ...], key: str):
    vals = [_at(series, rnd, key) for rnd in rounds]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return float(sum(vals) / len(vals))


def _max_of_rounds(series: list[dict], rounds: tuple[int, ...], key: str):
    vals = [_at(series, rnd, key) for rnd in rounds]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return float(max(vals))


def _blank_dyn(summary: dict, key: str):
    if "dynamic" not in summary:
        return None
    return summary["dynamic"].get(key)


def _check(series: list[dict], summary: dict) -> str:
    problems = []
    if len(series) != int(summary["rounds"]):
        problems.append(f"série {len(series)} rodadas, resumo {summary['rounds']}")
        return "; ".join(problems)
    pairs = (
        ("teste ponderado protocolo", round(_rate(series, "protocol_w_ok", True), 4), summary["consensus_accuracy_weighted_on_tests"]),
        ("teste maioria protocolo", round(_rate(series, "protocol_m_ok", True), 4), summary["consensus_accuracy_majority_on_tests"]),
        ("todas ponderado protocolo", round(_rate(series, "protocol_w_ok", False), 4), summary["consensus_accuracy_weighted"]),
        ("todas maioria protocolo", round(_rate(series, "protocol_m_ok", False), 4), summary["consensus_accuracy_majority"]),
    )
    for name, got, exp in pairs:
        if abs(float(got) - float(exp)) > 1e-9:
            problems.append(f"{name}: série {got} resumo {exp}")
    return "; ".join(problems)


def build_args(job: dict, output_dir: str):
    from sistema.scripts.run_a3_n50 import _args

    args = _args(
        "run",
        output=output_dir,
        experiment_id="run",
        nodes=job["nodes"],
        rounds=job["rounds"],
        malicious=job["malicious_pct"] / 100.0,
        seed=job["seed"],
        orchestration=job["orchestration"],
        signal=job["signal"],
        defense=job["defense"],
        topology=job["topology"],
        leader_attack=job["leader_attack"],
        mechanism=job["mechanism"],
        alpha=job["alpha"],
        collusion_value=999 if job["collusion"] else 0,
        quiet=True,
        overwrite=True,
        row_sync=False,
    )
    if not job["collusion"]:
        args.collusion_value = None
    if job.get("calibration_rounds") is not None:
        args.calibration_rounds = int(job["calibration_rounds"])
    if job.get("consensus_alpha") is not None:
        args.consensus_alpha = float(job["consensus_alpha"])
    if job.get("oracle_alpha") is not None:
        args.oracle_alpha = float(job["oracle_alpha"])
    return args


def execute(job: dict) -> dict:
    """Uma execução. Roda no processo do Pool."""
    t0 = time.perf_counter()
    try:
        _install()
        _rounds.clear()
        from sistema.simulate import build_profiles, defense_from_args, run_simulation

        tmp = tempfile.mkdtemp(prefix="a4_")
        try:
            args = build_args(job, tmp)
            summary = run_simulation(args)
            defense = defense_from_args(args)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        series = list(_rounds)
        profiles = build_profiles(job["nodes"], job["malicious_pct"] / 100.0, 0.0)
        n_mal = sum(1 for p in profiles.values() if p == "malicious")
        final = summary.get("final_reputation_by_profile") or {}
        detail = _check(series, summary)
        split = bool(defense.split_alpha)
        row = {
            "etapa": job["etapa"],
            "label": job["label"],
            "orchestration": job["orchestration"],
            "signal": job["signal"],
            "defense": job["defense"],
            "topology": job["topology"],
            "degree": 4,
            "mechanism": job["mechanism"],
            "alpha": job["alpha"],
            "consensus_alpha_efetivo": defense.consensus_alpha if split else args.alpha,
            "oracle_alpha_efetivo": defense.oracle_alpha if split else args.alpha,
            "split_alpha": int(split),
            "split_scores": int(defense.split_scores),
            "calibration_rounds": int(defense.calibration_rounds),
            "collusion": int(job["collusion"]),
            "leader_attack": job["leader_attack"],
            "nodes": job["nodes"],
            "rounds": job["rounds"],
            "malicious_pct": job["malicious_pct"],
            "n_malicious": n_mal,
            "seed": job["seed"],
            "test_protocol_weighted": summary["consensus_accuracy_weighted_on_tests"],
            "test_protocol_majority": summary["consensus_accuracy_majority_on_tests"],
            "all_protocol_weighted": summary["consensus_accuracy_weighted"],
            "all_protocol_majority": summary["consensus_accuracy_majority"],
            "all_protocol_majority_exata": _rate(series, "protocol_m_ok", False),
            "test_weighted_referencia": _rate(series, "w_ref_ok", True),
            "test_majority_referencia": _rate(series, "m_ref_ok", True),
            "test_weighted_rede": _rate(series, "w_all_ok", True),
            "test_majority_rede": _rate(series, "m_all_ok", True),
            "test_weighted_votantes": _rate(series, "w_vote_ok", True),
            "test_majority_votantes": _rate(series, "m_vote_ok", True),
            "all_weighted_referencia": _rate(series, "w_ref_ok", False),
            "all_majority_referencia": _rate(series, "m_ref_ok", False),
            "all_weighted_rede": _rate(series, "w_all_ok", False),
            "all_majority_rede": _rate(series, "m_all_ok", False),
            "leader_malicious_rounds": _blank_dyn(summary, "leader_malicious_rounds"),
            "leader_malicious_after_calibration": _blank_dyn(summary, "leader_malicious_rounds_after_calibration"),
            "forged_accepted": _blank_dyn(summary, "forged_accepted"),
            "voided_rounds": _blank_dyn(summary, "voided_rounds"),
            "chain_split_rounds": _blank_dyn(summary, "chain_split_rounds"),
            "n_chains_final": _blank_dyn(summary, "n_chains_final"),
            "final_rep_honest": final.get("honest"),
            "final_rep_malicious": final.get("malicious"),
            "final_power_honest": _at(series, job["rounds"], "power_hon_after"),
            "final_power_malicious": _at(series, job["rounds"], "power_mal_after"),
            "rep_mal_r1": _at(series, 1, "rep_mal_after"),
            "rep_mal_r2": _at(series, 2, "rep_mal_after"),
            "rep_mal_r3": _at(series, 3, "rep_mal_after"),
            "rep_hon_r1": _at(series, 1, "rep_hon_after"),
            "rep_hon_r3": _at(series, 3, "rep_hon_after"),
            "rep_hon_r50": _at(series, 50, "rep_hon_after"),
            "rep_mal_r50": _at(series, 50, "rep_mal_after"),
            "power_mal_r1": _at(series, 1, "power_mal_after"),
            "power_mal_r50": _at(series, 50, "power_mal_after"),
            "sum_mal_r4": _at(series, 4, "sum_mal_before"),
            "sum_hon_r4": _at(series, 4, "sum_hon_before"),
            "rep_mal_r10": _at(series, 10, "rep_mal_after"),
            "rep_mal_mean_r20_50": _mean_between(series, 20, 50, "rep_mal_after"),
            "rep_mal_mean_pos_teste_20_50": _mean_of_rounds(series, (20, 30, 40, 50), "rep_mal_after"),
            "rep_mal_peak_pre_validacao": _max_between(series, 1, 9, "rep_mal_after"),
            "rep_mal_peak_antes_testes_seguintes": _max_of_rounds(series, (19, 29, 39, 49), "rep_mal_after"),
            "rounds_referencia_parcial": sum(1 for r in series if r["n_ref_after"] < r["n_nodes"]),
            "check_ok": int(not detail),
            "check_detail": detail,
            "elapsed_s": round(time.perf_counter() - t0, 3),
        }
        if job.get("keep_series"):
            row["series"] = series
        return row
    except Exception:
        return {"error": traceback.format_exc(), "job": job}


def _base_job(**overrides) -> dict:
    job = {
        "etapa": "",
        "label": "",
        "orchestration": "fixed",
        "signal": "hybrid",
        "defense": "none",
        "topology": "star",
        "leader_attack": "none",
        "mechanism": "ema",
        "alpha": 0.3,
        "consensus_alpha": None,
        "oracle_alpha": None,
        "calibration_rounds": None,
        "collusion": 1,
        "nodes": 50,
        "rounds": 50,
        "malicious_pct": 0,
        "seed": 0,
        "keep_series": 0,
    }
    job.update(overrides)
    job["collusion"] = int(job["collusion"])
    return job


def _attack(orchestration: str, collusion: int, pct: int) -> str:
    if orchestration == "dynamic" and collusion and pct > 0:
        return "forge"
    return "none"


def _orch(label: str) -> dict:
    if label == "fixo_com_gabarito":
        return {"orchestration": "fixed", "signal": "hybrid", "defense": "none", "topology": "star"}
    if label == "dinamico_com_gabarito":
        return {"orchestration": "dynamic", "signal": "hybrid", "defense": "all", "topology": "kregular"}
    if label == "dinamico_sem_gabarito":
        return {"orchestration": "dynamic", "signal": "consensus", "defense": "all", "topology": "kregular"}
    raise KeyError(label)


LABELS = ("fixo_com_gabarito", "dinamico_com_gabarito", "dinamico_sem_gabarito")


def jobs_etapa2() -> list[dict]:
    jobs = []
    for label in LABELS:
        for pct in FRACTIONS_A3:
            for seed in SEEDS:
                spec = _orch(label)
                jobs.append(_base_job(
                    etapa="2", label=label, malicious_pct=pct, seed=seed, collusion=1,
                    leader_attack=_attack(spec["orchestration"], 1, pct),
                    keep_series=1, **spec,
                ))
    return jobs


def jobs_etapa3() -> list[dict]:
    jobs = []
    for label in LABELS:
        spec = _orch(label)
        for mechanism in MECHANISMS:
            for collusion in (0, 1):
                for pct in FRACTIONS_ALL:
                    for seed in SEEDS:
                        jobs.append(_base_job(
                            etapa="3", label=label, mechanism=mechanism, collusion=collusion,
                            malicious_pct=pct, seed=seed,
                            leader_attack=_attack(spec["orchestration"], collusion, pct),
                            **spec,
                        ))
    return jobs


def jobs_etapa4() -> list[dict]:
    jobs = []
    spec = _orch("dinamico_com_gabarito")
    for k in CALIBRATION_KS:
        for oracle_alpha in ORACLE_ALPHAS:
            for consensus_alpha in CONSENSUS_ALPHAS:
                for pct in FRACTIONS_ALL:
                    for seed in SEEDS:
                        jobs.append(_base_job(
                            etapa="4", label="dinamico_varredura", collusion=1,
                            malicious_pct=pct, seed=seed,
                            calibration_rounds=k,
                            oracle_alpha=oracle_alpha,
                            consensus_alpha=consensus_alpha,
                            leader_attack=_attack("dynamic", 1, pct),
                            **spec,
                        ))
    spec_f = _orch("fixo_com_gabarito")
    for alpha in ALPHAS_FIXO:
        for collusion in (0, 1):
            for pct in FRACTIONS_ALL:
                for seed in SEEDS:
                    jobs.append(_base_job(
                        etapa="4", label="fixo_varredura", collusion=collusion,
                        malicious_pct=pct, seed=seed, alpha=alpha,
                        leader_attack="none", **spec_f,
                    ))
    return jobs


def jobs_smoke() -> list[dict]:
    out = []
    for label, pct in (
        ("fixo_com_gabarito", 50),
        ("dinamico_com_gabarito", 50),
        ("dinamico_sem_gabarito", 50),
        ("dinamico_com_gabarito", 80),
        ("dinamico_sem_gabarito", 80),
    ):
        spec = _orch(label)
        out.append(_base_job(
            etapa="smoke", label=label, malicious_pct=pct, seed=0, collusion=1,
            leader_attack=_attack(spec["orchestration"], 1, pct), **spec,
        ))
    return out


EXEC_FIELDS = [
    "etapa", "label", "orchestration", "signal", "defense", "topology", "degree",
    "mechanism", "alpha", "consensus_alpha_efetivo", "oracle_alpha_efetivo",
    "split_alpha", "split_scores", "calibration_rounds", "collusion", "leader_attack",
    "nodes", "rounds", "malicious_pct", "n_malicious", "seed",
    "test_protocol_weighted", "test_protocol_majority",
    "all_protocol_weighted", "all_protocol_majority", "all_protocol_majority_exata",
    "test_weighted_referencia", "test_majority_referencia",
    "test_weighted_rede", "test_majority_rede",
    "test_weighted_votantes", "test_majority_votantes",
    "all_weighted_referencia", "all_majority_referencia",
    "all_weighted_rede", "all_majority_rede",
    "leader_malicious_rounds", "leader_malicious_after_calibration",
    "forged_accepted", "voided_rounds", "chain_split_rounds", "n_chains_final",
    "final_rep_honest", "final_rep_malicious",
    "final_power_honest", "final_power_malicious",
    "rep_mal_r1", "rep_mal_r2", "rep_mal_r3",
    "rep_hon_r1", "rep_hon_r3", "rep_hon_r50", "rep_mal_r50",
    "power_mal_r1", "power_mal_r50",
    "sum_mal_r4", "sum_hon_r4",
    "rep_mal_r10", "rep_mal_mean_r20_50", "rep_mal_mean_pos_teste_20_50",
    "rep_mal_peak_pre_validacao", "rep_mal_peak_antes_testes_seguintes",
    "rounds_referencia_parcial", "check_ok", "check_detail", "elapsed_s",
]

GROUP_KEYS = [
    "label", "orchestration", "signal", "defense", "topology", "mechanism",
    "alpha", "consensus_alpha_efetivo", "oracle_alpha_efetivo", "split_alpha",
    "split_scores", "calibration_rounds", "collusion", "leader_attack",
    "nodes", "rounds", "malicious_pct", "n_malicious",
]

MEASURES = [
    "test_protocol_weighted", "test_protocol_majority",
    "all_protocol_weighted", "all_protocol_majority", "all_protocol_majority_exata",
    "test_weighted_referencia", "test_majority_referencia",
    "test_weighted_rede", "test_majority_rede",
    "test_weighted_votantes", "test_majority_votantes",
    "all_weighted_referencia", "all_majority_referencia",
    "all_weighted_rede", "all_majority_rede",
    "leader_malicious_rounds", "leader_malicious_after_calibration",
    "forged_accepted", "voided_rounds", "chain_split_rounds", "n_chains_final",
    "final_rep_honest", "final_rep_malicious",
    "final_power_honest", "final_power_malicious",
    "rep_mal_r1", "rep_mal_r2", "rep_mal_r3",
    "rep_hon_r1", "rep_hon_r3", "rep_hon_r50", "rep_mal_r50",
    "power_mal_r1", "power_mal_r50",
    "sum_mal_r4", "sum_hon_r4",
    "rep_mal_r10", "rep_mal_mean_r20_50", "rep_mal_mean_pos_teste_20_50",
    "rep_mal_peak_pre_validacao", "rep_mal_peak_antes_testes_seguintes",
    "rounds_referencia_parcial", "elapsed_s",
]


def _num(value):
    if value is None or value == "":
        return None
    return float(value)


def mean_std(values) -> tuple[float | None, float | None, int]:
    nums = [float(v) for v in values if v is not None and v != ""]
    if not nums:
        return None, None, 0
    if len(nums) == 1:
        return nums[0], 0.0, 1
    return float(statistics.mean(nums)), float(statistics.stdev(nums)), len(nums)


def summarize(rows: list[dict]) -> list[dict]:
    buckets: dict[tuple, list] = defaultdict(list)
    for row in rows:
        buckets[tuple(row.get(k) for k in GROUP_KEYS)].append(row)
    out = []
    for key, group in buckets.items():
        item = {k: group[0].get(k) for k in GROUP_KEYS}
        item["n_reps"] = len(group)
        item["seeds"] = " ".join(str(r["seed"]) for r in sorted(group, key=lambda r: int(r["seed"])))
        for measure in MEASURES:
            mean, std, n = mean_std([r.get(measure) for r in group])
            item[f"{measure}_mean"] = mean
            item[f"{measure}_std"] = std
            item[f"{measure}_n"] = n
        out.append(item)
    out.sort(key=lambda r: tuple(str(r.get(k)) for k in GROUP_KEYS))
    return out


def _csv_value(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.10g}"
    return value


def write_csv(path: str, rows: list[dict], fields: list[str] | None = None) -> None:
    if not rows:
        raise RuntimeError(f"sem linhas para {path}")
    fields = fields or list(rows[0].keys())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _csv_value(row.get(k)) for k in fields})


def read_csv(path: str) -> list[dict]:
    int_fields = {
        "seed", "collusion", "malicious_pct", "n_malicious", "nodes", "rounds",
        "calibration_rounds", "split_alpha", "split_scores", "degree", "check_ok",
        "n_reps",
    }
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for key, value in list(row.items()):
            if value == "":
                row[key] = None
                continue
            if key in int_fields or key.endswith("_n"):
                row[key] = int(float(value))
            else:
                try:
                    row[key] = float(value) if any(c in value for c in ".eE") or key not in (
                        "etapa", "label", "orchestration", "signal", "defense", "topology",
                        "mechanism", "leader_attack", "seeds", "check_detail",
                    ) else value
                except ValueError:
                    pass
    return rows


def run_jobs(jobs: list[dict], workers: int) -> tuple[list[dict], list[dict]]:
    import multiprocessing as mp

    results: list[dict] = []
    errors: list[dict] = []
    started = time.perf_counter()
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=workers) as pool:
        for index, item in enumerate(pool.imap_unordered(execute, jobs, chunksize=1), start=1):
            if item.get("error"):
                errors.append(item)
                print(f"ERRO {index}/{len(jobs)} {item['job'].get('label')} pct={item['job'].get('malicious_pct')}", flush=True)
            else:
                results.append(item)
            if index == 1 or index % 25 == 0 or index == len(jobs):
                elapsed = time.perf_counter() - started
                rate = index / elapsed if elapsed else 0
                eta = (len(jobs) - index) / rate if rate else 0
                print(f"{index}/{len(jobs)}  {rate:.2f} exec/s  faltam {eta:.0f}s", flush=True)
    return results, errors


def append_errors(errors: list[dict], etapa: str) -> None:
    path = os.path.join(OUT, "ERROS.md")
    previous = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            previous = handle.read()
    if "Nenhum erro registrado." in previous and errors:
        previous = ""
    block = [f"## Etapa {etapa}", ""]
    if not errors:
        block.append("Nenhum erro nesta etapa.")
    else:
        for item in errors:
            job = item.get("job", {})
            block.append(f"### {job.get('label')} pct={job.get('malicious_pct')} seed={job.get('seed')} mechanism={job.get('mechanism')}")
            block.append("")
            block.append("```")
            block.append(item.get("error", "").rstrip())
            block.append("```")
            block.append("")
    text = (previous.rstrip() + "\n\n" if previous.strip() else "") + "\n".join(block) + "\n"
    if not previous.strip() and not errors:
        text = "Nenhum erro registrado.\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "desconhecido"


def fmt(value, nd: int = 4) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    text = f"{float(value):.{nd}f}"
    return text.replace(".", ",")


def pm(mean, std, nd: int = 4) -> str:
    if mean is None:
        return "—"
    return f"{fmt(mean, nd)} ± {fmt(std or 0, nd)}"


def close(got, expected, tol: float = TOL) -> bool:
    if got is None:
        return False
    return abs(float(got) - float(expected)) <= tol + 1e-12


def _sel(rows, **kw):
    out = []
    for row in rows:
        ok = True
        for key, value in kw.items():
            got = row.get(key)
            if isinstance(value, float):
                if got is None or abs(float(got) - value) > 1e-9:
                    ok = False
                    break
            elif got != value:
                ok = False
                break
        if ok:
            out.append(row)
    return out


def _m(rows, key):
    return mean_std([r.get(key) for r in rows])


def malicious_table(rows: list[dict]) -> str:
    seen = {}
    for row in rows:
        seen[int(row["malicious_pct"])] = int(row["n_malicious"])
    lines = ["| Fração | Nós maliciosos (`round(fração × 50)`, `sistema/simulate.py:58`) |", "| --- | --- |"]
    for pct in sorted(seen):
        lines.append(f"| {pct}% | {seen[pct]} |")
    return "\n".join(lines)


def write_etapa2_md(rows: list[dict]) -> None:
    """Tabela pedida, preenchida com a média das 5 sementes."""

    def part(label, pct, key):
        return _m(_sel(rows, label=label, malicious_pct=pct), key)

    claims = []

    def add(afirmacao, artigo, obtido, confere):
        claims.append((afirmacao, artigo, obtido, "sim" if confere else "não"))

    bits = []
    ok = True
    for pct in (0, 25):
        mean, std, _ = part("fixo_com_gabarito", pct, "test_protocol_weighted")
        bits.append(f"{pct}%: {pm(mean, std)}")
        ok = ok and close(mean, 1)
    add("Acurácia de teste, fixo com gabarito, 0% e 25%", "1", "; ".join(bits), ok)

    bits, ok = [], True
    for pct in (50, 65, 80):
        mean, std, _ = part("fixo_com_gabarito", pct, "test_protocol_weighted")
        bits.append(f"{pct}%: {pm(mean, std)}")
        ok = ok and close(mean, 0)
    add("Acurácia de teste, fixo com gabarito, 50%, 65% e 80%", "0", "; ".join(bits), ok)

    bits, ok = [], True
    for pct in FRACTIONS_A3:
        mean, std, _ = part("dinamico_com_gabarito", pct, "test_protocol_weighted")
        bits.append(f"{pct}%: {pm(mean, std)}")
        ok = ok and close(mean, 1)
    add("Acurácia de teste, dinâmico com gabarito, todas as frações", "1", "; ".join(bits), ok)

    bits, ok = [], True
    for pct in (50, 65, 80):
        mean, std, _ = part("dinamico_sem_gabarito", pct, "test_protocol_weighted")
        bits.append(f"{pct}%: {pm(mean, std)}")
        ok = ok and close(mean, 1)
    add("Acurácia de teste, dinâmico sem gabarito, 50%, 65% e 80%", "1", "; ".join(bits), ok)

    bits, ok = [], True
    for pct in FRACTIONS_A3:
        leader, _, _ = part("dinamico_com_gabarito", pct, "leader_malicious_rounds")
        forged, _, _ = part("dinamico_com_gabarito", pct, "forged_accepted")
        voided, _, _ = part("dinamico_com_gabarito", pct, "voided_rounds")
        splits, _, _ = part("dinamico_com_gabarito", pct, "chain_split_rounds")
        bits.append(
            f"{pct}%: líder {fmt(leader, 2)}, forjas {fmt(forged, 2)}, anulações {fmt(voided, 2)}, divisões {fmt(splits, 2)}"
        )
        ok = ok and close(leader, 0) and close(forged, 0) and close(voided, 0) and close(splits, 0)
    add(
        "Dinâmico com gabarito: rodadas com líder malicioso, forjas aceitas, anulações e divisões (todas as frações)",
        "0, 0, 0, 0",
        "; ".join(bits),
        ok,
    )

    bits, ok = [], True
    for pct in FRACTIONS_A3:
        chains, std, _ = part("dinamico_com_gabarito", pct, "n_chains_final")
        bits.append(f"{pct}%: {pm(chains, std, 2)}")
        ok = ok and close(chains, 1)
    add("Dinâmico com gabarito: número de cadeias no fim", "1", "; ".join(bits), ok)

    # Malicioso após 1, 2 e 3. O artigo não fixa a fração; compara-se cada fração com maliciosos.
    bits, ok = [], True
    for pct in (25, 50, 65, 80):
        m1, _, _ = part("dinamico_com_gabarito", pct, "rep_mal_r1")
        m2, _, _ = part("dinamico_com_gabarito", pct, "rep_mal_r2")
        m3, _, _ = part("dinamico_com_gabarito", pct, "rep_mal_r3")
        bits.append(f"{pct}%: {fmt(m1)} / {fmt(m2)} / {fmt(m3)}")
        ok = ok and close(m1, 0.1) and close(m2, 0.02) and close(m3, 0.004)
    add("Malicioso após as rodadas 1, 2 e 3 (dinâmico com gabarito)", "0,1 / 0,02 / 0,004", "; ".join(bits), ok)

    bits, ok = [], True
    for pct, exp in ((50, 0.1), (65, 0.13), (80, 0.16)):
        mean, std, _ = part("dinamico_com_gabarito", pct, "sum_mal_r4")
        bits.append(f"{pct}%: {pm(mean, std)}")
        ok = ok and close(mean, exp)
    add("Soma do peso do conluio na rodada 4, em 50%, 65% e 80%", "0,1 / 0,13 / 0,16", "; ".join(bits), ok)

    bits, ok = [], True
    for pct, exp in ((50, 21.8), (65, 16.5), (80, 9.3)):
        mean, std, _ = part("dinamico_com_gabarito", pct, "sum_hon_r4")
        bits.append(f"{pct}%: {pm(mean, std)}")
        ok = ok and close(mean, exp)
    add("Soma do peso dos honestos na rodada 4, em 50%, 65% e 80%", "21,8 / 16,5 / 9,3", "; ".join(bits), ok)

    h, hs, _ = part("dinamico_com_gabarito", 50, "rep_hon_r1")
    m, ms, _ = part("dinamico_com_gabarito", 50, "rep_mal_r1")
    add("50% com gabarito: honesto e malicioso após a rodada 1", "0,804 / 0,100", f"{pm(h, hs)} / {pm(m, ms)}", close(h, 0.804) and close(m, 0.100))

    h, hs, _ = part("dinamico_com_gabarito", 50, "rep_hon_r3")
    m, ms, _ = part("dinamico_com_gabarito", 50, "rep_mal_r3")
    add("50% com gabarito: honesto e malicioso após a rodada 3", "0,872 / 0,004", f"{pm(h, hs)} / {pm(m, ms)}", close(h, 0.872) and close(m, 0.004))

    m, ms, _ = part("dinamico_sem_gabarito", 50, "rep_mal_r1")
    h, hs, _ = part("dinamico_sem_gabarito", 50, "rep_hon_r1")
    add("50% sem gabarito: malicioso e honesto após a punição da rodada 1", "0,250 / 0,500", f"{pm(m, ms)} / {pm(h, hs)}", close(m, 0.250) and close(h, 0.500))

    h, hs, _ = part("dinamico_sem_gabarito", 50, "rep_hon_r50")
    m, ms, _ = part("dinamico_sem_gabarito", 50, "rep_mal_r50")
    add("50% sem gabarito: médias na rodada 50 (honesto / malicioso)", "0,867 / 0,020", f"{pm(h, hs)} / {pm(m, ms)}", close(h, 0.867) and close(m, 0.020))

    p, ps, _ = part("dinamico_sem_gabarito", 50, "power_mal_r50")
    add("50% sem gabarito: reputação de eleição do malicioso", "0,25", pm(p, ps), close(p, 0.25))

    h1, _, _ = part("dinamico_com_gabarito", 80, "rep_hon_r1")
    h3, _, _ = part("dinamico_com_gabarito", 80, "rep_hon_r3")
    h50, _, _ = part("dinamico_com_gabarito", 80, "rep_hon_r50")
    m50, _, _ = part("dinamico_com_gabarito", 80, "rep_mal_r50")
    add(
        "80% com gabarito: honesto após rodadas 1 e 3; médias na rodada 50",
        "0,756 / 0,929; 0,980 / 0,000",
        f"{fmt(h1)} / {fmt(h3)}; {fmt(h50)} / {fmt(m50)}",
        close(h1, 0.756) and close(h3, 0.929) and close(h50, 0.980) and close(m50, 0.000),
    )

    h, hs, _ = part("dinamico_sem_gabarito", 80, "rep_hon_r50")
    m, ms, _ = part("dinamico_sem_gabarito", 80, "rep_mal_r50")
    add("80% sem gabarito: médias na rodada 50 (honesto / malicioso)", "0,881 / 1", f"{pm(h, hs)} / {pm(m, ms)}", close(h, 0.881) and close(m, 1))

    bits, ok = [], True
    for pct in (65, 80):
        splits, ss, _ = part("dinamico_sem_gabarito", pct, "chain_split_rounds")
        chains, cs, _ = part("dinamico_sem_gabarito", pct, "n_chains_final")
        bits.append(f"{pct}%: divisões {pm(splits, ss, 2)}, cadeias {pm(chains, cs, 2)}")
        ok = ok and close(splits, 1) and close(chains, 2)
    add("65% e 80% sem gabarito: divisões e cadeias no fim", "1 divisão, 2 cadeias", "; ".join(bits), ok)

    bits = []
    ok_literal = True
    ok_pos_teste = True
    for pct in (50, 65, 80):
        r10, _, _ = part("fixo_com_gabarito", pct, "rep_mal_r10")
        todas, _, _ = part("fixo_com_gabarito", pct, "rep_mal_mean_r20_50")
        pos, _, _ = part("fixo_com_gabarito", pct, "rep_mal_mean_pos_teste_20_50")
        pico1, _, _ = part("fixo_com_gabarito", pct, "rep_mal_peak_pre_validacao")
        pico2, _, _ = part("fixo_com_gabarito", pct, "rep_mal_peak_antes_testes_seguintes")
        bits.append(
            f"{pct}%: após rodada 10 {fmt(r10)}; média das rodadas 20 a 50 {fmt(todas)}; "
            f"média só nas rodadas 20, 30, 40 e 50 {fmt(pos)}; "
            f"pico nas rodadas 1 a 9 {fmt(pico1)}; pico nas rodadas 19, 29, 39 e 49 {fmt(pico2)}"
        )
        ok_literal = ok_literal and close(r10, 0.686) and close(todas, 0.691) and close(pico1, 0.987)
        ok_pos_teste = ok_pos_teste and close(r10, 0.686) and close(pos, 0.691) and close(pico2, 0.987)
    add(
        "Fixo: reputação média do malicioso na rodada 10 / rodadas 20–50 / pico antes da validação",
        "0,686 / 0,691 / 0,987",
        "; ".join(bits) + ". Fração não indicada no pedido; valores em 50%, 65% e 80%. "
        "Confere na leitura literal (média de todas as rodadas 20–50 e pico das rodadas 1–9): "
        + ("sim" if ok_literal else "não")
        + ". Confere se 0,691 for o valor depois das validações 20/30/40/50 e 0,987 for o pico nas rodadas 19/29/39/49: "
        + ("sim" if ok_pos_teste else "não") + ".",
        ok_literal,
    )

    subset = _sel(rows, label="fixo_com_gabarito", malicious_pct=50)
    vals = [float(r["all_protocol_majority_exata"]) for r in subset]
    mean, std, _ = mean_std(vals)
    mn, mx = (min(vals), max(vals)) if vals else (None, None)
    raw = ", ".join(fmt(v, 2) for v in sorted(vals))
    add(
        "Fixo, 50%: acurácia da maioria em todas as rodadas (média; mínimo–máximo)",
        "0,072; 0,04–0,10",
        f"média {pm(mean, std)}; mín {fmt(mn, 2)}; máx {fmt(mx, 2)}; sementes [{raw}]",
        close(mean, 0.072) and close(mn, 0.04) and close(mx, 0.10),
    )

    # Nota: líder malicioso depois da calibração, para não esconder a métrica do código.
    note_bits = []
    for pct in FRACTIONS_A3:
        leader, std, _ = part("dinamico_com_gabarito", pct, "leader_malicious_after_calibration")
        note_bits.append(f"{pct}%: {pm(leader, std, 2)}")

    checks = sum(int(r["check_ok"]) for r in rows)
    lines = [
        "# Etapa 2 — reprodução dos números do artigo A3",
        "",
        f"Commit em que os números foram gerados: `{git_sha()}`.",
        "",
        "Comando:",
        "",
        "```",
        f"{CMD_PREFIX} etapa2",
        "```",
        "",
        "Configuração, a mesma de `sistema/scripts/run_a3_n50.py:30-98`, com duas extensões pedidas para a A4: a fração 80% e o dinâmico sem gabarito nas cinco frações (o script do A3 só roda sem gabarito em 50% e 65%, e não roda 80%).",
        "",
        "- 50 nós, 50 rodadas, sementes 0 a 4, `test_every=10` (rodadas de teste 10, 20, 30, 40 e 50).",
        "- Conluio: `collusion_value=999` quando a fração é positiva (`run_a3_n50.py:66-67`).",
        "- Honesto acerta com probabilidade 0,9 (`run_a3_n50.py:37`).",
        "- Fixo com gabarito: `orchestration=fixed`, `signal=hybrid`, `defense=none`, `alpha=0,3`, topologia estrela.",
        "- Dinâmico com gabarito: `orchestration=dynamic`, `signal=hybrid`, `defense=all` (calibração de 3 rodadas, α de consenso 0,05, α de gabarito 0,8), grafo 4-regular, líder `forge` se a fração é positiva.",
        "- Dinâmico sem gabarito: igual ao dinâmico, com `signal=consensus`. Nesse sinal o código não aplica gabarito em rodada alguma (`sistema/core/protocol.py:144-150`).",
        "- Acurácia de teste do protocolo: `consensus_accuracy_weighted_on_tests` (`sistema/core/metrics.py:391`).",
        "- Desvio-padrão: amostral, divisor n−1, das 5 sementes. Tolerância do «confere»: ±0,005 sobre a média.",
        "",
        malicious_table(rows),
        "",
        f"Conferência interna série×resumo: {checks}/{len(rows)} execuções com `check_ok=1`.",
        "",
        "## Tabela pedida",
        "",
        "| Afirmação do artigo A3 | Valor no artigo | Valor obtido (média ± desvio) | Confere? |",
        "| --- | --- | --- | --- |",
    ]
    for afirmacao, artigo, obtido, confere in claims:
        lines.append(f"| {afirmacao} | {artigo} | {obtido} | {confere} |")
    lines += [
        "",
        "O código também conta o líder malicioso só a partir da rodada de índice `calibration_rounds` (`sistema/core/metrics.py:565-567`). Dinâmico com gabarito, essa conta por fração: " + "; ".join(note_bits) + ".",
        "",
        "## Onde a acurácia do dinâmico é medida",
        "",
        "A acurácia de teste do protocolo, no dinâmico, não é um novo consenso calculado no fim. É o valor que a cópia de referência gravou.",
        "",
        "1. A cópia de referência é o grupo com mais nós não maliciosos; empate no tamanho fica com o grupo de `gid` menor (`sistema/core/network.py:105-110`).",
        "2. `run_simulation` passa para o registro os membros desse grupo **depois** da rodada (`sistema/simulate.py:286`).",
        "3. O consenso ponderado da rodada é a resposta adotada por um nó não malicioso dessa cópia. Se a rodada foi anulada ou o nó recusou o registro, essa resposta é `None` e a rodada conta como erro (`sistema/core/network.py:209` e `sistema/core/network.py:334-346`; o acerto está em `sistema/core/schemas.py:49-51`).",
        "4. A maioria simples que o resumo chama de `consensus_accuracy_majority` é calculada sobre as respostas de **todos** os nós, não só da cópia de referência (`sistema/core/network.py:340-346`).",
        "5. As colunas `test_weighted_referencia` e `test_majority_referencia` deste CSV são outro cálculo: os dois agregadores sobre as respostas dos membros da cópia de referência depois da rodada, com os pesos de antes da rodada. Rodada anulada não zera esse cálculo. A coluna do protocolo continua sendo a do item 3.",
        "",
        "Arquivos: `02_execucoes.csv` (uma linha por execução), `02_resumo.csv` (média e desvio), `02_rodadas.csv` (uma linha por rodada, para as trajetórias).",
        "",
    ]
    with open(os.path.join(OUT, "02_reproducao.md"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def write_etapa3_md(rows: list[dict]) -> None:
    lines = [
        "# Etapa 3 — matriz reputação × conluio",
        "",
        f"Commit: `{git_sha()}`.",
        "",
        "Comando:",
        "",
        "```",
        f"{CMD_PREFIX} etapa3",
        "```",
        "",
        "Cada execução calcula, na mesma rodada e sobre as mesmas respostas, o consenso ponderado e a maioria simples. Não são duas simulações.",
        "",
        "- Sem reputação = maioria simples (`sistema/core/consensus.py:111`).",
        "- Com reputação = consenso ponderado (`sistema/core/consensus.py:68`).",
        "- Sem conluio: `collusion_value=None` (cada malicioso erra com um valor diferente, `sistema/core/behavior.py:109-113`) e `leader_attack=none`.",
        "- Com conluio: todos os maliciosos devolvem 999; no dinâmico, `leader_attack=forge` quando a fração é positiva.",
        "- Fixo com gabarito, dinâmico com gabarito e dinâmico sem gabarito, como na etapa 2. Mecanismos `ema`, `ema_asymmetric` e `beta`. α do tracker = 0,3. No dinâmico com `defense=all`, o α efetivo do consenso é 0,05 e o do gabarito é 0,8 (`sistema/core/defenses.py:30-31`).",
        "- Frações: 0, 5, 20, 25, 35, 50, 65 e 80%. 50 nós, 50 rodadas, sementes 0 a 4.",
        "- Figura: só EMA. Eixo y = acurácia nas rodadas de teste, em %, dos dois agregadores sobre a **cópia de referência** (membros de `reference_group()` depois da rodada). A rede inteira está nas colunas `*_rede`.",
        "- Desvio-padrão amostral (n−1).",
        "",
        malicious_table(rows),
        "",
        "Figuras:",
        "",
        "- `figuras/03_fixo_com_gabarito_ema.png`",
        "- `figuras/03_dinamico_com_gabarito_ema.png`",
        "- `figuras/03_dinamico_sem_gabarito_ema.png`",
        "",
        "No fixo a cópia de referência é a rede inteira: não há cadeia. No dinâmico, `rounds_referencia_parcial` conta rodadas em que a cópia de referência tinha menos nós que a rede.",
        "",
        "## Acurácia de teste, EMA, cópia de referência",
        "",
        _matrix_table(rows, "ema"),
        "",
        "## Protocolo, líder, forja, anulação, divisão e cadeias",
        "",
        "No fixo essas colunas não existem no código (orquestrador sem eleição). Ficam vazias no CSV.",
        "",
        _security_table(rows),
        "",
        "O CSV completo, com os três mecanismos e as duas versões da maioria (referência e rede inteira), é `03_matriz_execucoes.csv` e `03_matriz_resumo.csv`.",
        "",
    ]
    with open(os.path.join(OUT, "03_matriz.md"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _matrix_table(rows: list[dict], mechanism: str) -> str:
    header = (
        "| Orquestrador | Fração | Nós maliciosos | "
        "Com reputação, com conluio | Com reputação, sem conluio | "
        "Sem reputação, com conluio | Sem reputação, sem conluio | "
        "Protocolo, com conluio | Maioria da rede, com conluio |"
    )
    sep = "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    lines = [header, sep]
    for label in LABELS:
        for pct in FRACTIONS_ALL:
            base = _sel(rows, label=label, mechanism=mechanism, malicious_pct=pct)
            if not base:
                continue
            n_mal = int(base[0]["n_malicious"])
            cells = []
            for collusion, key in (
                (1, "test_weighted_referencia"),
                (0, "test_weighted_referencia"),
                (1, "test_majority_referencia"),
                (0, "test_majority_referencia"),
                (1, "test_protocol_weighted"),
                (1, "test_majority_rede"),
            ):
                mean, std, _ = _m(_sel(base, collusion=collusion), key)
                cells.append(pm(mean, std))
            lines.append(f"| {label} | {pct}% | {n_mal} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _security_table(rows: list[dict]) -> str:
    lines = [
        "| Orquestrador | Mecanismo | Conluio | Fração | Nós maliciosos | Líder malicioso | Forjas aceitas | Anulações | Divisões | Cadeias no fim | Rodadas com referência parcial |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for label in LABELS:
        for mechanism in MECHANISMS:
            for collusion in (0, 1):
                for pct in FRACTIONS_ALL:
                    group = _sel(rows, label=label, mechanism=mechanism, collusion=collusion, malicious_pct=pct)
                    if not group:
                        continue
                    n_mal = int(group[0]["n_malicious"])
                    cols = []
                    for key in (
                        "leader_malicious_rounds", "forged_accepted", "voided_rounds",
                        "chain_split_rounds", "n_chains_final", "rounds_referencia_parcial",
                    ):
                        mean, std, _ = _m(group, key)
                        cols.append(pm(mean, std, 2))
                    lines.append(
                        f"| {label} | {mechanism} | {collusion} | {pct}% | {n_mal} | " + " | ".join(cols) + " |"
                    )
    return "\n".join(lines)


def write_etapa4_md(rows: list[dict]) -> None:
    dynamic = [r for r in rows if r["label"] == "dinamico_varredura"]
    fixed = [r for r in rows if r["label"] == "fixo_varredura"]
    k_lines = ["| α consenso | α gabarito | menor k | pior acurácia de teste nesse k (mínimo entre frações e sementes) |", "| --- | --- | --- | --- |"]
    answers = []
    for consensus_alpha in CONSENSUS_ALPHAS:
        for oracle_alpha in ORACLE_ALPHAS:
            found = None
            worst = None
            for k in CALIBRATION_KS:
                sub = [
                    r for r in dynamic
                    if int(r["calibration_rounds"]) == k
                    and _near(r["consensus_alpha_efetivo"], consensus_alpha)
                    and _near(r["oracle_alpha_efetivo"], oracle_alpha)
                ]
                pcts = {int(r["malicious_pct"]) for r in sub}
                perfect = len(sub) == len(FRACTIONS_ALL) * len(SEEDS) and pcts == set(FRACTIONS_ALL) and all(
                    abs(float(r["test_protocol_weighted"]) - 1.0) <= 1e-9 for r in sub
                )
                if perfect and found is None:
                    found = k
                    worst = min(float(r["test_protocol_weighted"]) for r in sub)
            k_lines.append(
                f"| {fmt(consensus_alpha, 2)} | {fmt(oracle_alpha, 2)} | {found if found is not None else 'nenhum até 5'} | {fmt(worst) if worst is not None else '—'} |"
            )
            answers.append(f"α consenso {fmt(consensus_alpha, 2)}, α gabarito {fmt(oracle_alpha, 2)}: menor k = {found if found is not None else 'nenhum'}")

    alpha_lines = ["| α único | com conluio, pior acurácia | sem conluio, pior acurácia | 1 em todas as frações e sementes, com e sem conluio |", "| --- | --- | --- | --- |"]
    both = []
    for alpha in ALPHAS_FIXO:
        def subset(collusion, alpha=alpha):
            return [r for r in fixed if int(r["collusion"]) == collusion and _near(r["alpha"], alpha)]

        def worst(collusion):
            sub = subset(collusion)
            if not sub:
                return None
            return min(float(r["test_protocol_weighted"]) for r in sub)

        def perfect(collusion):
            sub = subset(collusion)
            pcts = {int(r["malicious_pct"]) for r in sub}
            return len(sub) == len(FRACTIONS_ALL) * len(SEEDS) and pcts == set(FRACTIONS_ALL) and all(
                abs(float(r["test_protocol_weighted"]) - 1.0) <= 1e-9 for r in sub
            )

        ok_both = perfect(1) and perfect(0)
        if ok_both:
            both.append(alpha)
        alpha_lines.append(
            f"| {fmt(alpha, 2)} | {fmt(worst(1))} | {fmt(worst(0))} | {'sim' if ok_both else 'não'} |"
        )

    both_text = "nenhum" if not both else ", ".join(fmt(a, 2) for a in both)
    lines = [
        "# Etapa 4 — varredura de α e de rodadas de calibração",
        "",
        f"Commit: `{git_sha()}`.",
        "",
        "Comando:",
        "",
        "```",
        f"{CMD_PREFIX} etapa4",
        "```",
        "",
        "Acurácia de teste desta resposta: `test_protocol_weighted`, a do protocolo (`consensus_accuracy_weighted_on_tests`). 100% significa que **cada** semente, em **cada** fração, deu 1. Não é só a média.",
        "",
        "Dinâmico: com gabarito, conluio 999, líder forja, `defense=all` (as outras defesas permanecem; só k, α do gabarito e α do consenso mudam). α do tracker permanece 0,3. Frações da lista de oito. Sementes 0 a 4.",
        "",
        "Fixo: com gabarito, `defense=none`, sem calibração, um único α nas rodadas normais e nas de teste (porque `split_alpha` está desligado e os dois sinais usam `args.alpha`). Com e sem conluio.",
        "",
        malicious_table(rows),
        "",
        "## Resposta",
        "",
        "Menor k com acurácia de teste 1 em todas as frações e sementes:",
        "",
        *[f"- {line}" for line in answers],
        "",
        f"α único do fixo com acurácia de teste 1 em todas as frações, com e sem conluio ao mesmo tempo: {both_text}.",
        "",
        "## Menor k por par de α",
        "",
        *k_lines,
        "",
        "## α único do fixo",
        "",
        *alpha_lines,
        "",
        "Figuras: `figuras/04_varredura_dinamico.png` (k no par α consenso 0,05 e α gabarito 0,80) e `figuras/04_varredura_fixo.png`.",
        "",
        "CSV: `04_varredura_execucoes.csv`, `04_varredura_resumo.csv`.",
        "",
    ]
    with open(os.path.join(OUT, "04_varredura.md"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _near(a, b) -> bool:
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= 1e-6


def _style():
    import matplotlib.pyplot as plt

    os.makedirs(os.path.join(OUT, ".mplconfig"), exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", os.path.join(OUT, ".mplconfig"))
    plt.rcParams.update({
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "axes.facecolor": "white",
        "font.size": 10,
    })
    return plt


def plot_etapa3(rows: list[dict]) -> None:
    plt = _style()
    os.makedirs(FIG, exist_ok=True)
    styles = (
        ("Com reputação, com conluio", 1, "test_weighted_referencia", "#1f4e79", "o", "-"),
        ("Com reputação, sem conluio", 0, "test_weighted_referencia", "#2e7d32", "s", "-"),
        ("Sem reputação, com conluio", 1, "test_majority_referencia", "#e07b00", "^", "--"),
        ("Sem reputação, sem conluio", 0, "test_majority_referencia", "#6a1b9a", "D", "--"),
    )
    titles = {
        "fixo_com_gabarito": "Orquestrador fixo, com gabarito",
        "dinamico_com_gabarito": "Orquestrador dinâmico, com gabarito",
        "dinamico_sem_gabarito": "Orquestrador dinâmico, sem gabarito",
    }
    for label, title in titles.items():
        fig, ax = plt.subplots(figsize=(8.2, 4.8), dpi=140)
        subset = _sel(rows, label=label, mechanism="ema")
        counts = {int(r["malicious_pct"]): int(r["n_malicious"]) for r in subset}
        for name, collusion, key, color, marker, linestyle in styles:
            xs, ys, yerr = [], [], []
            for pct in FRACTIONS_ALL:
                group = _sel(subset, collusion=collusion, malicious_pct=pct)
                mean, std, n = _m(group, key)
                if mean is None:
                    continue
                xs.append(pct)
                ys.append(mean * 100.0)
                yerr.append((std or 0) * 100.0)
            ax.errorbar(xs, ys, yerr=yerr, label=name, color=color, marker=marker, linestyle=linestyle, capsize=3, linewidth=1.6)
        ax.set_xlabel("Fração de nós maliciosos (%)\n(entre parênteses, nós maliciosos usados)")
        ax.set_ylabel("Acurácia nas rodadas de teste (%)")
        ax.set_xticks(list(FRACTIONS_ALL))
        ax.set_xticklabels([f"{pct}\n({counts.get(pct, '?')})" for pct in FRACTIONS_ALL])
        ax.set_ylim(-5, 110)
        ax.set_xlim(-4, 84)
        ax.grid(True, color="#e6e6e6")
        ax.set_title(f"{title}\nEMA, N=50, 50 rodadas, 5 repetições. Barras: desvio-padrão.")
        ax.legend(frameon=True, fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(FIG, f"03_{label}_ema.png"))
        plt.close(fig)


def plot_etapa4(rows: list[dict]) -> None:
    plt = _style()
    os.makedirs(FIG, exist_ok=True)
    dynamic = [r for r in rows if r["label"] == "dinamico_varredura"]
    fixed = [r for r in rows if r["label"] == "fixo_varredura"]

    fig, ax = plt.subplots(figsize=(8.2, 4.8), dpi=140)
    cmap = plt.cm.viridis
    for index, k in enumerate(CALIBRATION_KS):
        xs, ys = [], []
        for pct in FRACTIONS_ALL:
            group = [
                r for r in dynamic
                if int(r["calibration_rounds"]) == k and int(r["malicious_pct"]) == pct
                and _near(r["consensus_alpha_efetivo"], 0.05) and _near(r["oracle_alpha_efetivo"], 0.8)
            ]
            mean, _, _ = _m(group, "test_protocol_weighted")
            if mean is None:
                continue
            xs.append(pct)
            ys.append(mean * 100.0)
        ax.plot(xs, ys, marker="o", color=cmap(index / max(1, len(CALIBRATION_KS) - 1)), label=f"k = {k}")
    counts = {int(r["malicious_pct"]): int(r["n_malicious"]) for r in dynamic}
    ax.set_xticks(list(FRACTIONS_ALL))
    ax.set_xticklabels([f"{pct}\n({counts.get(pct, '?')})" for pct in FRACTIONS_ALL])
    ax.set_ylim(-5, 110)
    ax.set_xlabel("Fração de nós maliciosos (%)")
    ax.set_ylabel("Acurácia de teste do protocolo (%)")
    ax.set_title("Dinâmico com gabarito e conluio\nα consenso 0,05, α gabarito 0,80, média de 5 sementes")
    ax.grid(True, color="#e6e6e6")
    ax.legend(ncol=3, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "04_varredura_dinamico.png"))
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.6), dpi=140, sharey=True)
    for ax, collusion, title in (
        (axes[0], 1, "Com conluio"),
        (axes[1], 0, "Sem conluio"),
    ):
        for index, alpha in enumerate(ALPHAS_FIXO):
            xs, ys = [], []
            for pct in FRACTIONS_ALL:
                group = [
                    r for r in fixed
                    if int(r["collusion"]) == collusion and int(r["malicious_pct"]) == pct and _near(r["alpha"], alpha)
                ]
                mean, _, _ = _m(group, "test_protocol_weighted")
                if mean is None:
                    continue
                xs.append(pct)
                ys.append(mean * 100.0)
            ax.plot(xs, ys, color=cmap(index / (len(ALPHAS_FIXO) - 1)), label=f"{alpha:.2f}")
        ax.set_title(title)
        ax.set_xticks(list(FRACTIONS_ALL))
        ax.set_xticklabels([str(pct) for pct in FRACTIONS_ALL], rotation=45)
        ax.set_ylim(-5, 110)
        ax.grid(True, color="#e6e6e6")
        ax.set_xlabel("Fração de nós maliciosos (%)")
    axes[0].set_ylabel("Acurácia de teste do protocolo (%)")
    axes[1].legend(title="α", fontsize=7, ncol=2)
    fig.suptitle("Fixo com gabarito, α único, média de 5 sementes")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "04_varredura_fixo.png"))
    plt.close(fig)


def _drop_series(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    series_rows = []
    clean = []
    for row in rows:
        series = row.pop("series", None)
        if series:
            for item in series:
                series_rows.append({
                    "label": row["label"],
                    "malicious_pct": row["malicious_pct"],
                    "n_malicious": row["n_malicious"],
                    "seed": row["seed"],
                    **item,
                })
        clean.append(row)
    return clean, series_rows


def finish(etapa: str, rows: list[dict], errors: list[dict], exec_name: str, resumo_name: str) -> list[dict]:
    append_errors(errors, etapa)
    failed = [r for r in rows if not int(r.get("check_ok", 0))]
    if failed:
        path = os.path.join(OUT, "ERROS.md")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"\n## Etapa {etapa} — conferência série×resumo falhou\n\n")
            for row in failed:
                handle.write(
                    f"- {row['label']} pct={row['malicious_pct']} seed={row['seed']} "
                    f"mechanism={row['mechanism']}: {row.get('check_detail')}\n"
                )
    clean, series_rows = _drop_series(rows)
    clean.sort(key=lambda r: (
        str(r["label"]), str(r["mechanism"]), int(r["collusion"]), int(r["malicious_pct"]),
        int(r["calibration_rounds"]), float(r["alpha"]), int(r["seed"]),
    ))
    write_csv(os.path.join(OUT, exec_name), clean, EXEC_FIELDS)
    resumo = summarize(clean)
    resumo_fields = list(GROUP_KEYS) + ["n_reps", "seeds"]
    for measure in MEASURES:
        resumo_fields += [f"{measure}_mean", f"{measure}_std", f"{measure}_n"]
    write_csv(os.path.join(OUT, resumo_name), resumo, resumo_fields)
    if series_rows:
        fields = ["label", "malicious_pct", "n_malicious", "seed"] + list(series_rows[0].keys())
        # keys repeat label; DictWriter extrasaction ignore with explicit unique fields
        seen = []
        for key in fields:
            if key not in seen:
                seen.append(key)
        write_csv(os.path.join(OUT, "02_rodadas.csv"), series_rows, seen)
    if etapa == "2":
        write_etapa2_md(clean)
    elif etapa == "3":
        write_etapa3_md(clean)
        plot_etapa3(clean)
    elif etapa == "4":
        write_etapa4_md(clean)
        plot_etapa4(clean)
    print(f"etapa {etapa}: {len(clean)} execuções, {len(errors)} erros", flush=True)
    return clean


def smoke() -> None:
    for job in jobs_smoke():
        row = execute(job)
        if row.get("error"):
            print(row["error"])
            continue
        print(
            f"{row['label']} pct={row['malicious_pct']} n_mal={row['n_malicious']} "
            f"testW={row['test_protocol_weighted']} testM={row['test_protocol_majority']} "
            f"refW={row['test_weighted_referencia']} refM={row['test_majority_referencia']} "
            f"redeM={row['test_majority_rede']} "
            f"mal1/2/3={row['rep_mal_r1']}/{row['rep_mal_r2']}/{row['rep_mal_r3']} "
            f"hon1={row['rep_hon_r1']} sumMal4={row['sum_mal_r4']} sumHon4={row['sum_hon_r4']} "
            f"lead={row['leader_malicious_rounds']} leadPos={row['leader_malicious_after_calibration']} "
            f"forge={row['forged_accepted']} void={row['voided_rounds']} split={row['chain_split_rounds']} "
            f"chains={row['n_chains_final']} powerMal={row['final_power_malicious']} "
            f"r10={row['rep_mal_r10']} plat={row['rep_mal_mean_r20_50']} peak={row['rep_mal_peak_pre_validacao']} "
            f"check={row['check_ok']} {row['check_detail']} {row['elapsed_s']}s",
            flush=True,
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Gera os dados da correção A4.")
    parser.add_argument("etapa", choices=("smoke", "etapa2", "etapa3", "etapa4", "figuras", "all"))
    parser.add_argument("--workers", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)))
    args = parser.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)
    if args.etapa == "smoke":
        smoke()
        return
    if args.etapa == "figuras":
        plot_etapa3(read_csv(os.path.join(OUT, "03_matriz_execucoes.csv")))
        plot_etapa4(read_csv(os.path.join(OUT, "04_varredura_execucoes.csv")))
        return
    plan = []
    if args.etapa in ("etapa2", "all"):
        plan.append(("2", jobs_etapa2(), "02_execucoes.csv", "02_resumo.csv"))
    if args.etapa in ("etapa3", "all"):
        plan.append(("3", jobs_etapa3(), "03_matriz_execucoes.csv", "03_matriz_resumo.csv"))
    if args.etapa in ("etapa4", "all"):
        plan.append(("4", jobs_etapa4(), "04_varredura_execucoes.csv", "04_varredura_resumo.csv"))
    for etapa, jobs, exec_name, resumo_name in plan:
        print(f"etapa {etapa}: {len(jobs)} execuções, {args.workers} processos", flush=True)
        rows, errors = run_jobs(jobs, args.workers)
        finish(etapa, rows, errors, exec_name, resumo_name)


if __name__ == "__main__":
    main()
