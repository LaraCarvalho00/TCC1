"""Análise dos experimentos da matriz de reputação.

Agrega todos os experimentos encontrados em ``--input`` (diretório da matriz),
valida as instrumentações, testa H1/H2/H5 contra predições fechadas e gera os
gráficos necessários para o artigo.

Hipóteses testadas
------------------
* **H1** — punição desproporcional: ``punishment = alpha * reputation_before``
  (relação linear para o mecanismo EMA; verificada por scatter + regressão).
* **H2** — recompensa insuficiente: rodadas para retornar à reputação pré-erro
  após um único erro isolado (predição: 6 rodadas contra 1 de queda).
* **H5** — acúmulo de penalizações: sequências de erro consecutivo em honestos
  levam a sobreposição das distribuições de reputação com maliciosos.

Validação de instrumentação (EMA)
----------------------------------
Para cada linha de per_node.csv com mechanism=ema:
  - erro  : punishment / reputation_before ≈ alpha  (tolerância 1e-4)
  - acerto: reward    / (1 - reputation_before) ≈ alpha  (tolerância 1e-4)

Gráficos gerados
----------------
1. ``rep_evolution.png``   — evolução da reputação por perfil (média ± std).
2. ``rep_delta.png``       — delta de reputação por rodada (honesto vs malicioso).
3. ``h1_punishment.png``   — punição vs reputação_antes (scatter por perfil).
4. ``h2_recovery.png``     — distribuição de rodadas de recuperação.
5. ``h5_overlap.png``      — distribuição de reputação final por perfil.
6. ``fp_fn_tau.png``       — curva FP/FN em função do limiar tau.
7. ``mechanism_compare.png`` — acurácia ponderada por mecanismo e % maliciosos.

Uso::

    python -m sistema.scripts.analyze
    python -m sistema.scripts.analyze --input sistema/results/matrix \\
                                       --output sistema/results/analysis \\
                                       --filter-mechanism ema
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import statistics
from collections import defaultdict
from typing import Optional

# Garante que o stdout use UTF-8 mesmo em terminais com codepage restrito (Windows).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Importação condicional do matplotlib
# ---------------------------------------------------------------------------
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print(
        "AVISO: matplotlib não encontrado. Instale com:\n"
        "  pip install matplotlib\n"
        "Os gráficos serão omitidos; as estatísticas serão geradas normalmente.",
        file=sys.stderr,
    )

_DEFAULT_INPUT = os.path.join(os.path.dirname(__file__), "..", "results", "matrix")
_DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "results", "analysis")


# ---------------------------------------------------------------------------
# Carregamento de dados
# ---------------------------------------------------------------------------

def _csv_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _float(val: str, default: float = float("nan")) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _int(val: str, default: int = 0) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def discover_experiments(base_dir: str) -> list[str]:
    """Retorna caminhos de diretórios com manifest.json."""
    found = []
    for name in sorted(os.listdir(base_dir)):
        path = os.path.join(base_dir, name)
        if os.path.isdir(path) and os.path.exists(os.path.join(path, "manifest.json")):
            found.append(path)
    return found


def load_per_node(exp_dirs: list[str], mechanism_filter: Optional[str] = None) -> list[dict]:
    """Carrega e concatena todos os per_node.csv."""
    rows = []
    for d in exp_dirs:
        path = os.path.join(d, "per_node.csv")
        if not os.path.exists(path):
            continue
        for row in _csv_rows(path):
            if mechanism_filter and row.get("mechanism") != mechanism_filter:
                continue
            rows.append(row)
    return rows


def load_rounds(exp_dirs: list[str], mechanism_filter: Optional[str] = None) -> list[dict]:
    rows = []
    for d in exp_dirs:
        path = os.path.join(d, "rounds.csv")
        if not os.path.exists(path):
            continue
        for row in _csv_rows(path):
            # Recupera mecanismo a partir do manifest
            manifest_path = os.path.join(d, "manifest.json")
            mech = "ema"
            if os.path.exists(manifest_path):
                with open(manifest_path, encoding="utf-8") as fh:
                    mf = json.load(fh)
                mech = mf.get("mechanism", "ema")
            if mechanism_filter and mech != mechanism_filter:
                continue
            row["_mechanism"] = mech
            rows.append(row)
    return rows


def load_history(exp_dirs: list[str], mechanism_filter: Optional[str] = None) -> list[dict]:
    rows = []
    for d in exp_dirs:
        path = os.path.join(d, "reputation_history.csv")
        if not os.path.exists(path):
            continue
        manifest_path = os.path.join(d, "manifest.json")
        mech = "ema"
        if os.path.exists(manifest_path):
            with open(manifest_path, encoding="utf-8") as fh:
                mf = json.load(fh)
            mech = mf.get("mechanism", "ema")
        if mechanism_filter and mech != mechanism_filter:
            continue
        for row in _csv_rows(path):
            row["_mechanism"] = mech
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Validação de instrumentação (H1 predição fechada)
# ---------------------------------------------------------------------------

def validate_instrumentation(rows: list[dict], tol: float = 1e-4) -> dict:
    """Verifica que punishment/reward são derivados corretamente da fórmula EMA."""
    ema_rows = [r for r in rows if r.get("mechanism") == "ema"]
    errors = []
    ok_count = 0
    skip_count = 0

    for row in ema_rows:
        alpha = _float(row.get("alpha_used", ""), 0.3)
        r_before = _float(row.get("reputation_before", ""))
        punishment = _float(row.get("punishment", ""))
        reward = _float(row.get("reward", ""))
        correct = _int(row.get("correct", "0"))
        answered = _int(row.get("answered", "1"))

        if math.isnan(r_before) or math.isnan(punishment) or math.isnan(reward):
            skip_count += 1
            continue

        if not answered:
            # Ausente = erro, mesma fórmula
            expected_p = alpha * r_before
            if abs(punishment - expected_p) > tol:
                errors.append({
                    "exp_id": row.get("experiment_id"),
                    "round": row.get("round_index"),
                    "node": row.get("node_id"),
                    "expected_p": expected_p,
                    "got_p": punishment,
                })
            else:
                ok_count += 1
        elif correct:
            expected_r = alpha * (1 - r_before)
            if abs(reward - expected_r) > tol:
                errors.append({
                    "exp_id": row.get("experiment_id"),
                    "round": row.get("round_index"),
                    "node": row.get("node_id"),
                    "expected_r": expected_r,
                    "got_r": reward,
                })
            else:
                ok_count += 1
        else:
            expected_p = alpha * r_before
            if abs(punishment - expected_p) > tol:
                errors.append({
                    "exp_id": row.get("experiment_id"),
                    "round": row.get("round_index"),
                    "node": row.get("node_id"),
                    "expected_p": expected_p,
                    "got_p": punishment,
                })
            else:
                ok_count += 1

    return {
        "ema_rows_checked": len(ema_rows) - skip_count,
        "ok": ok_count,
        "errors": len(errors),
        "error_rate": round(len(errors) / max(len(ema_rows) - skip_count, 1), 6),
        "first_errors": errors[:5],
    }


# ---------------------------------------------------------------------------
# H1 — Punição desproporcional
# ---------------------------------------------------------------------------

def h1_punishment_data(rows: list[dict]) -> dict:
    """Coleta dados para H1: punishment vs reputation_before por perfil."""
    by_profile: dict[str, tuple[list, list]] = {}
    for row in rows:
        if _int(row.get("correct", "0")) or _int(row.get("answered", "1")) == 0:
            # só linhas de erro
            pass
        correct_flag = _int(row.get("correct", "0"))
        answered_flag = _int(row.get("answered", "1"))
        if correct_flag:
            continue  # só erros

        r_before = _float(row.get("reputation_before", ""))
        punishment = _float(row.get("punishment", ""))
        profile = row.get("profile", "unknown")

        if math.isnan(r_before) or math.isnan(punishment):
            continue

        if profile not in by_profile:
            by_profile[profile] = ([], [])
        by_profile[profile][0].append(r_before)
        by_profile[profile][1].append(punishment)

    # Regressão linear simples: punishment = a * r_before + b
    results = {}
    for profile, (xs, ys) in by_profile.items():
        n = len(xs)
        if n < 2:
            results[profile] = {"n": n}
            continue
        mean_x = statistics.mean(xs)
        mean_y = statistics.mean(ys)
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / (n - 1)
        var_x = statistics.variance(xs) if n >= 2 else 1e-9
        slope = cov / max(var_x, 1e-9)
        intercept = mean_y - slope * mean_x
        results[profile] = {"n": n, "slope": round(slope, 4), "intercept": round(intercept, 6)}

    return {"by_profile": by_profile, "regression": results}


# ---------------------------------------------------------------------------
# H2 — Rodadas de recuperação
# ---------------------------------------------------------------------------

def h2_recovery_data(history_rows: list[dict]) -> dict:
    """Para cada erro isolado de nó honesto, mede rodadas até recuperar."""
    # Agrupa histórico por (experiment_id, node_id)
    node_histories: dict[tuple, list] = defaultdict(list)
    node_profile: dict[tuple, str] = {}
    for row in history_rows:
        key = (row.get("experiment_id", ""), row.get("node_id", ""))
        node_profile[key] = row.get("profile", "unknown")
        chk = _int(row.get("checkpoint", "0"))
        rep = _float(row.get("reputation", ""))
        node_histories[key].append((chk, rep))

    recovery_rounds: list[int] = []
    for key, checkpoints in node_histories.items():
        if node_profile.get(key) != "honest":
            continue
        checkpoints.sort(key=lambda x: x[0])
        reps = [rep for _, rep in checkpoints]
        # Detecta queda abrupta seguida de recuperação.
        for i in range(1, len(reps) - 1):
            drop = reps[i - 1] - reps[i]
            # Queda significativa (> alpha/2 = 0.15): candidato a erro isolado.
            if drop < 0.12:
                continue
            # Verifica se a rodada anterior foi acerto (reps[i] < reps[i-1]).
            # Conta rodadas até retornar ao valor pré-queda.
            target = reps[i - 1]
            rounds_to_recover = 0
            for j in range(i + 1, len(reps)):
                rounds_to_recover += 1
                if reps[j] >= target - 0.005:  # tolerância de arredondamento
                    break
            else:
                rounds_to_recover = -1  # não recuperou
            if rounds_to_recover > 0:
                recovery_rounds.append(rounds_to_recover)

    if not recovery_rounds:
        return {"n_events": 0}

    return {
        "n_events": len(recovery_rounds),
        "median_recovery": statistics.median(recovery_rounds),
        "mean_recovery": round(statistics.mean(recovery_rounds), 2),
        "min": min(recovery_rounds),
        "max": max(recovery_rounds),
        "distribution": recovery_rounds,
        "h2_sustained": statistics.median(recovery_rounds) >= 3,  # predição: >= 3
    }


# ---------------------------------------------------------------------------
# H5 — Sobreposição de distribuições
# ---------------------------------------------------------------------------

def h5_overlap_data(rows: list[dict]) -> dict:
    """Analisa sobreposição das distribuições de reputação final por perfil."""
    # Pega o reputation_after da última rodada por (experiment_id, node_id).
    last_rep: dict[tuple, dict] = {}
    for row in rows:
        key = (row.get("experiment_id", ""), row.get("node_id", ""))
        ri = _int(row.get("round_index", "0"))
        current = last_rep.get(key, {})
        if not current or ri > _int(current.get("round_index", "0")):
            last_rep[key] = {
                "reputation_after": _float(row.get("reputation_after", "")),
                "profile": row.get("profile", "unknown"),
                "round_index": ri,
            }

    by_profile: dict[str, list[float]] = defaultdict(list)
    for data in last_rep.values():
        rep = data["reputation_after"]
        if not math.isnan(rep):
            by_profile[data["profile"]].append(rep)

    stats = {}
    for profile, reps in by_profile.items():
        if not reps:
            continue
        stats[profile] = {
            "n": len(reps),
            "mean": round(statistics.mean(reps), 4),
            "median": round(statistics.median(reps), 4),
            "stdev": round(statistics.stdev(reps), 4) if len(reps) >= 2 else 0.0,
            "min": round(min(reps), 4),
            "max": round(max(reps), 4),
        }

    # Sobreposição entre honest e malicious: fração de honestos abaixo do
    # percentil 90 dos maliciosos.
    honest_reps = sorted(by_profile.get("honest", []))
    mal_reps = sorted(by_profile.get("malicious", []))
    overlap = None
    if honest_reps and mal_reps:
        p90_malicious = mal_reps[int(0.9 * len(mal_reps))] if len(mal_reps) >= 10 else max(mal_reps)
        overlap = round(sum(1 for r in honest_reps if r <= p90_malicious) / len(honest_reps), 4)

    return {
        "stats_by_profile": stats,
        "honest_below_p90_malicious": overlap,
        "h5_sustained": overlap is not None and overlap > 0.05,
    }


# ---------------------------------------------------------------------------
# FP/FN em função de tau
# ---------------------------------------------------------------------------

def fp_fn_curve(rows: list[dict], num_points: int = 100) -> dict:
    """Curva de falsos positivos/negativos como função do limiar tau."""
    last_rep: dict[tuple, dict] = {}
    for row in rows:
        key = (row.get("experiment_id", ""), row.get("node_id", ""))
        ri = _int(row.get("round_index", "0"))
        current = last_rep.get(key, {})
        if not current or ri > _int(current.get("round_index", "0")):
            last_rep[key] = {
                "rep": _float(row.get("reputation_after", "")),
                "profile": row.get("profile", "unknown"),
            }

    honest_reps = [d["rep"] for d in last_rep.values() if d["profile"] == "honest" and not math.isnan(d["rep"])]
    mal_reps = [d["rep"] for d in last_rep.values() if d["profile"] == "malicious" and not math.isnan(d["rep"])]

    if not honest_reps or not mal_reps:
        return {"taus": [], "fp_rate": [], "fn_rate": []}

    taus = [i / num_points for i in range(num_points + 1)]
    fp_rates = []
    fn_rates = []
    for tau in taus:
        # FP: honestos abaixo de tau (seriam excluídos indevidamente)
        fp = sum(1 for r in honest_reps if r < tau) / len(honest_reps)
        # FN: maliciosos acima de tau (passariam despercebidos)
        fn = sum(1 for r in mal_reps if r >= tau) / len(mal_reps)
        fp_rates.append(round(fp, 4))
        fn_rates.append(round(fn, 4))

    return {"taus": taus, "fp_rate": fp_rates, "fn_rate": fn_rates,
            "n_honest": len(honest_reps), "n_malicious": len(mal_reps)}


# ---------------------------------------------------------------------------
# Métricas por mecanismo para comparação (Fase 4)
# ---------------------------------------------------------------------------

def mechanism_compare_data(exp_dirs: list[str]) -> dict:
    """Lê summary.json de cada experimento e agrega por mecanismo."""
    by_mech_by_mal: dict[str, dict[float, list[float]]] = defaultdict(lambda: defaultdict(list))
    for d in exp_dirs:
        manifest_path = os.path.join(d, "manifest.json")
        summary_path = os.path.join(d, "summary.json")
        if not os.path.exists(manifest_path) or not os.path.exists(summary_path):
            continue
        with open(manifest_path, encoding="utf-8") as fh:
            mf = json.load(fh)
        with open(summary_path, encoding="utf-8") as fh:
            payload = json.load(fh)
        mech = mf.get("mechanism", "ema")
        cfg = payload.get("config", {})
        mal_frac = float(cfg.get("malicious_frac", 0.0))
        acc = payload.get("summary", {}).get("consensus_accuracy_weighted")
        if acc is not None:
            by_mech_by_mal[mech][mal_frac].append(float(acc))

    result: dict[str, dict] = {}
    for mech, by_mal in by_mech_by_mal.items():
        result[mech] = {
            str(round(mal_frac, 2)): {
                "n": len(accs),
                "mean": round(statistics.mean(accs), 4),
                "stdev": round(statistics.stdev(accs), 4) if len(accs) >= 2 else 0.0,
            }
            for mal_frac, accs in sorted(by_mal.items())
        }
    return result


# ---------------------------------------------------------------------------
# Geração de gráficos
# ---------------------------------------------------------------------------

def _save(fig, path: str) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Salvo: {path}")


def plot_reputation_evolution(history_rows: list[dict], output_dir: str) -> None:
    """Gráfico 1: evolução média da reputação por perfil ao longo dos checkpoints."""
    by_profile_chk: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in history_rows:
        profile = row.get("profile", "unknown")
        chk = _int(row.get("checkpoint", "0"))
        rep = _float(row.get("reputation", ""))
        if not math.isnan(rep):
            by_profile_chk[profile][chk].append(rep)

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = {"honest": "#2196F3", "malicious": "#F44336", "unstable": "#FF9800"}
    for profile, by_chk in sorted(by_profile_chk.items()):
        chks = sorted(by_chk)
        means = [statistics.mean(by_chk[c]) for c in chks]
        stds = [statistics.stdev(by_chk[c]) if len(by_chk[c]) >= 2 else 0.0 for c in chks]
        color = colors.get(profile, "#9E9E9E")
        ax.plot(chks, means, label=profile, color=color, linewidth=2)
        ax.fill_between(
            chks,
            [m - s for m, s in zip(means, stds)],
            [m + s for m, s in zip(means, stds)],
            alpha=0.2, color=color,
        )
    ax.set_xlabel("Checkpoint (rodada)")
    ax.set_ylabel("Reputação")
    ax.set_title("Evolução da reputação por perfil (média ± std)")
    ax.legend()
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    _save(fig, os.path.join(output_dir, "rep_evolution.png"))


def plot_delta(rows: list[dict], output_dir: str) -> None:
    """Gráfico 2: delta de reputação por rodada, separado por perfil."""
    by_profile_round: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        profile = row.get("profile", "unknown")
        ri = _int(row.get("round_index", "0"))
        delta = _float(row.get("delta", ""))
        if not math.isnan(delta):
            by_profile_round[profile][ri].append(delta)

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = {"honest": "#2196F3", "malicious": "#F44336", "unstable": "#FF9800"}
    for profile, by_round in sorted(by_profile_round.items()):
        rounds = sorted(by_round)
        means = [statistics.mean(by_round[r]) for r in rounds]
        color = colors.get(profile, "#9E9E9E")
        ax.plot(rounds, means, label=profile, color=color, linewidth=1.5, alpha=0.85)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Rodada")
    ax.set_ylabel("Delta de reputação")
    ax.set_title("Delta de reputação médio por rodada e por perfil")
    ax.legend()
    ax.grid(True, alpha=0.3)
    _save(fig, os.path.join(output_dir, "rep_delta.png"))


def plot_h1_punishment(h1_data: dict, output_dir: str) -> None:
    """Gráfico 3 (H1): scatter de punição vs reputação_antes por perfil."""
    by_profile = h1_data["by_profile"]
    regression = h1_data["regression"]

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = {"honest": "#2196F3", "malicious": "#F44336", "unstable": "#FF9800"}
    for profile, (xs, ys) in sorted(by_profile.items()):
        color = colors.get(profile, "#9E9E9E")
        sample_size = min(len(xs), 3000)  # limita pontos para legibilidade
        step = max(1, len(xs) // sample_size)
        ax.scatter(xs[::step], ys[::step], s=6, alpha=0.4, color=color, label=profile)

    # Linha teórica: punishment = alpha * r  (EMA com alpha=0.3)
    r_vals = [i / 100 for i in range(101)]
    ax.plot(r_vals, [0.3 * r for r in r_vals], "k--", linewidth=1.5,
            label="Teórico EMA (α=0.3)")

    # Regressão empírica por perfil.
    for profile, reg in regression.items():
        if "slope" not in reg:
            continue
        ax.annotate(
            f"{profile}: slope={reg['slope']:.3f}",
            xy=(0.02, 0.05 + list(regression).index(profile) * 0.08),
            xycoords="axes fraction", fontsize=8,
        )

    ax.set_xlabel("Reputação antes da atualização")
    ax.set_ylabel("Punição (perda de reputação)")
    ax.set_title("H1 — Punição vs reputação anterior por perfil")
    ax.legend(markerscale=3)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 0.35)
    ax.grid(True, alpha=0.3)
    _save(fig, os.path.join(output_dir, "h1_punishment.png"))


def plot_h2_recovery(h2_data: dict, output_dir: str) -> None:
    """Gráfico 4 (H2): distribuição de rodadas de recuperação."""
    fig, ax = plt.subplots(figsize=(7, 5))
    dist = h2_data.get("distribution", [])
    if not dist:
        ax.text(0.5, 0.5, "Sem dados de recuperação", ha="center", va="center")
        _save(fig, os.path.join(output_dir, "h2_recovery.png"))
        return

    max_val = max(dist)
    bins = range(1, min(max_val + 2, 30))
    ax.hist(dist, bins=list(bins), color="#2196F3", alpha=0.7, edgecolor="white")
    median_r = h2_data.get("median_recovery", 0)
    ax.axvline(median_r, color="red", linestyle="--", linewidth=1.5,
               label=f"Mediana = {median_r:.1f} rodadas")
    ax.axvline(1, color="green", linestyle=":", linewidth=1.5,
               label="Queda (1 rodada)")
    ax.set_xlabel("Rodadas para recuperar a reputação pré-erro")
    ax.set_ylabel("Frequência (eventos)")
    ax.set_title(
        f"H2 — Assimetria temporal: queda (1 rodada) vs recuperação (mediana {median_r:.0f})"
    )
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    _save(fig, os.path.join(output_dir, "h2_recovery.png"))


def plot_h5_overlap(h5_data: dict, rows: list[dict], output_dir: str) -> None:
    """Gráfico 5 (H5): distribuição de reputação final por perfil (box + hist)."""
    last_rep: dict[tuple, dict] = {}
    for row in rows:
        key = (row.get("experiment_id", ""), row.get("node_id", ""))
        ri = _int(row.get("round_index", "0"))
        current = last_rep.get(key, {})
        if not current or ri > _int(current.get("round_index", "0")):
            last_rep[key] = {
                "rep": _float(row.get("reputation_after", "")),
                "profile": row.get("profile", "unknown"),
            }

    by_profile: dict[str, list[float]] = defaultdict(list)
    for d in last_rep.values():
        if not math.isnan(d["rep"]):
            by_profile[d["profile"]].append(d["rep"])

    profiles_order = [p for p in ["honest", "malicious", "unstable"] if p in by_profile]
    colors = {"honest": "#2196F3", "malicious": "#F44336", "unstable": "#FF9800"}

    fig, ax = plt.subplots(figsize=(8, 5))
    for i, profile in enumerate(profiles_order):
        reps = by_profile[profile]
        color = colors.get(profile, "#9E9E9E")
        ax.hist(reps, bins=30, alpha=0.5, color=color, label=profile,
                density=True, range=(0, 1))
    ax.set_xlabel("Reputação final")
    ax.set_ylabel("Densidade")
    ax.set_title("H5 — Sobreposição das distribuições de reputação por perfil")
    ax.legend()
    ax.grid(True, alpha=0.3)
    _save(fig, os.path.join(output_dir, "h5_overlap.png"))


def plot_fp_fn(curve_data: dict, output_dir: str) -> None:
    """Gráfico 6: curva FP/FN em função de tau."""
    taus = curve_data.get("taus", [])
    fp_rate = curve_data.get("fp_rate", [])
    fn_rate = curve_data.get("fn_rate", [])

    if not taus:
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(taus, fp_rate, label="Taxa de Falsos Positivos (honestos excluídos)",
            color="#2196F3", linewidth=2)
    ax.plot(taus, fn_rate, label="Taxa de Falsos Negativos (maliciosos passam)",
            color="#F44336", linewidth=2)

    # Ponto de cruzamento (tau ótimo).
    for i in range(len(taus) - 1):
        if abs(fp_rate[i] - fn_rate[i]) <= 0.02:
            ax.axvline(taus[i], color="green", linestyle="--", linewidth=1.2,
                       label=f"τ ≈ {taus[i]:.2f} (equilíbrio)")
            break

    ax.set_xlabel("Limiar de exclusão (τ)")
    ax.set_ylabel("Taxa de erro")
    ax.set_title("Curva FP/FN em função do limiar de reputação τ")
    ax.legend()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    _save(fig, os.path.join(output_dir, "fp_fn_tau.png"))


def plot_mechanism_compare(compare_data: dict, output_dir: str) -> None:
    """Gráfico 7: acurácia ponderada por mecanismo e fração de maliciosos."""
    if not compare_data:
        return

    mal_fracs = sorted({
        float(mal)
        for mech_data in compare_data.values()
        for mal in mech_data.keys()
    })
    mechanisms = sorted(compare_data.keys())
    colors_list = ["#2196F3", "#F44336", "#4CAF50", "#FF9800"]
    x = range(len(mal_fracs))
    width = 0.8 / max(len(mechanisms), 1)

    fig, ax = plt.subplots(figsize=(9, 5))
    for i, mech in enumerate(mechanisms):
        means = []
        errs = []
        for mal in mal_fracs:
            entry = compare_data[mech].get(str(round(mal, 2)), {})
            means.append(entry.get("mean", 0))
            errs.append(entry.get("stdev", 0))
        offset = (i - (len(mechanisms) - 1) / 2) * width
        ax.bar(
            [xi + offset for xi in x], means, width=width * 0.9,
            label=mech, color=colors_list[i % len(colors_list)], alpha=0.8,
        )
        ax.errorbar(
            [xi + offset for xi in x], means, yerr=errs,
            fmt="none", color="black", capsize=3,
        )

    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{int(m*100)}% mal." for m in mal_fracs])
    ax.set_ylabel("Acurácia do consenso ponderado")
    ax.set_title("Comparação de mecanismos de reputação (média ± std)")
    ax.legend()
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3, axis="y")
    _save(fig, os.path.join(output_dir, "mechanism_compare.png"))


# ---------------------------------------------------------------------------
# Análise principal
# ---------------------------------------------------------------------------

def run_analysis(args: argparse.Namespace) -> None:
    os.makedirs(args.output, exist_ok=True)

    print(f"Descobrindo experimentos em: {args.input}")
    exp_dirs = discover_experiments(args.input)
    print(f"  {len(exp_dirs)} experimentos encontrados.")

    if not exp_dirs:
        print("Nenhum experimento encontrado. Execute run_matrix.py primeiro.")
        return

    mf = args.filter_mechanism or None

    print("Carregando dados...")
    per_node = load_per_node(exp_dirs, mf)
    history = load_history(exp_dirs, mf)
    print(f"  per_node: {len(per_node)} linhas | history: {len(history)} linhas")

    # ----------------------------------------------------------------
    # Validação de instrumentação
    # ----------------------------------------------------------------
    print("\n[Validação] Verificando instrumentação EMA...")
    val = validate_instrumentation(per_node)
    print(f"  Verificadas: {val['ema_rows_checked']} linhas | OK: {val['ok']} | Erros: {val['errors']}")
    if val["errors"] > 0:
        print(f"  AVISO: taxa de erro = {val['error_rate']:.4%}. Verifique engine.py.")
        for e in val["first_errors"]:
            print(f"    → {e}")

    # ----------------------------------------------------------------
    # H1
    # ----------------------------------------------------------------
    print("\n[H1] Punição proporcional à reputação...")
    h1 = h1_punishment_data(per_node)
    for profile, reg in h1["regression"].items():
        slope = reg.get("slope", "N/A")
        print(f"  {profile}: slope={slope} (esperado ~0.3 para EMA)")

    # ----------------------------------------------------------------
    # H2
    # ----------------------------------------------------------------
    print("\n[H2] Assimetria temporal de recuperação...")
    h2 = h2_recovery_data(history)
    if h2.get("n_events", 0) > 0:
        print(f"  Eventos: {h2['n_events']} | Mediana recuperação: {h2['median_recovery']} rodadas")
        print(f"  H2 sustentada: {h2.get('h2_sustained', False)}")
    else:
        print("  Sem eventos de recuperação detectados.")

    # ----------------------------------------------------------------
    # H5
    # ----------------------------------------------------------------
    print("\n[H5] Sobreposição de distribuições de reputação...")
    h5 = h5_overlap_data(per_node)
    for profile, st in h5.get("stats_by_profile", {}).items():
        print(f"  {profile}: média={st['mean']:.3f} std={st['stdev']:.3f} [{st['min']:.3f},{st['max']:.3f}]")
    print(f"  Honestos abaixo do P90 dos maliciosos: {h5.get('honest_below_p90_malicious')}")
    print(f"  H5 sustentada: {h5.get('h5_sustained', False)}")

    # ----------------------------------------------------------------
    # FP/FN
    # ----------------------------------------------------------------
    print("\n[FP/FN] Calculando curva em função de τ...")
    curve = fp_fn_curve(per_node)
    print(f"  Honestos: {curve.get('n_honest', 0)} | Maliciosos: {curve.get('n_malicious', 0)}")

    # ----------------------------------------------------------------
    # Comparação de mecanismos
    # ----------------------------------------------------------------
    print("\n[Fase 4] Comparando mecanismos...")
    compare = mechanism_compare_data(exp_dirs)
    for mech, by_mal in sorted(compare.items()):
        parts = [f"{k}→{v['mean']:.3f}±{v['stdev']:.3f}" for k, v in sorted(by_mal.items())]
        print(f"  {mech}: " + "  ".join(parts))

    # ----------------------------------------------------------------
    # Salvamento do relatório de hipóteses
    # ----------------------------------------------------------------
    report = {
        "instrumentation_validation": val,
        "h1": {k: {kk: vv for kk, vv in v.items() if kk != "by_profile_data"}
               for k, v in {"regression": h1["regression"]}.items()},
        "h2": {k: v for k, v in h2.items() if k != "distribution"},
        "h5": {k: v for k, v in h5.items() if k != "stats_by_profile"},
        "h5_stats": h5.get("stats_by_profile", {}),
        "mechanism_compare": compare,
    }
    report_path = os.path.join(args.output, "hypotheses_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(f"\nRelatório de hipóteses salvo em: {report_path}")

    # ----------------------------------------------------------------
    # Gráficos
    # ----------------------------------------------------------------
    if HAS_MPL:
        print("\n[Gráficos] Gerando visualizações...")
        plot_reputation_evolution(history, args.output)
        plot_delta(per_node, args.output)
        plot_h1_punishment(h1, args.output)
        plot_h2_recovery(h2, args.output)
        plot_h5_overlap(h5, per_node, args.output)
        plot_fp_fn(curve, args.output)
        plot_mechanism_compare(compare, args.output)
        print(f"\nGráficos salvos em: {args.output}")
    else:
        print("\nInstale matplotlib para gerar gráficos: pip install matplotlib")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Análise dos experimentos de reputação.")
    parser.add_argument("--input", default=_DEFAULT_INPUT, help="Diretório da matriz de resultados.")
    parser.add_argument("--output", default=_DEFAULT_OUTPUT, help="Diretório de saída da análise.")
    parser.add_argument(
        "--filter-mechanism", default=None, dest="filter_mechanism",
        choices=list(("ema", "ema_asymmetric", "beta")) + [None],
        help="Filtrar por mecanismo (None = todos).",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    run_analysis(parse_args())
