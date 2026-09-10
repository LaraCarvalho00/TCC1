"""Registro de métricas do experimento em CSV e JSON.

Gera quatro arquivos por execução:

* ``per_node.csv``           — uma linha por nó por rodada, com a decomposição
                               completa da atualização de reputação.
* ``rounds.csv``             — uma linha por rodada, com métricas de dispersão
                               das respostas e dados do consenso.
* ``reputation_history.csv`` — série temporal da reputação por nó (checkpoint 0
                               = inicial, checkpoint k+1 = após a rodada k).
* ``summary.json``           — acurácia agregada, reputação final e média por
                               perfil, configuração e identificação do experimento.
* ``manifest.json``          — configuração completa, semente, mecanismo e git sha,
                               para reprodutibilidade.

Cada linha é identificada por ``experiment_id``, permitindo agregar múltiplos
experimentos para análise comparativa.
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import statistics
import subprocess
from typing import TYPE_CHECKING, Optional

from .schemas import RoundResult

if TYPE_CHECKING:
    from .reputation import ReputationTracker, ReputationUpdate

# ---------------------------------------------------------------------------
# Schemas dos CSVs
# ---------------------------------------------------------------------------

PER_NODE_FIELDS = [
    "experiment_id",
    "round_index",
    "task_id",
    "node_id",
    "profile",
    "answered",          # 1 se o nó respondeu, 0 se ausente/timeout
    "answer",
    "expected",
    "correct",           # 0/1
    "abs_error",         # |answer - expected|; vazio se ausente
    "rel_error",         # abs_error / |expected|; vazio se ausente ou expected=0
    "latency_ms",
    "score_initial",     # reputação inicial do experimento (constante)
    "reputation_before",
    "reputation_after",
    "delta",             # reputation_after - reputation_before
    "reward",            # max(0, delta)
    "punishment",        # max(0, -delta)
    "alpha_used",        # taxa de aprendizado efetivamente aplicada
    "mechanism",         # ema | ema_asymmetric | beta
    "weight_used",       # peso usado no consenso ponderado (= reputation_before)
    "consensus_weighted_result",
    "consensus_majority_result",
    "consensus_weighted_correct",
    "consensus_majority_correct",
    "is_tie_weighted",
    "is_tie_majority",
]

ROUND_FIELDS = [
    "experiment_id",
    "round_index",
    "task_id",
    "expected",
    "consensus_weighted",
    "consensus_correct",
    "consensus_majority",
    "majority_correct",
    "num_responses",
    "num_nodes",
    "mean_latency_ms",
    "n_distinct_answers",    # nº de valores distintos (excluindo ausências)
    "n_absent",              # nº de nós sem resposta
    "absent_rate",           # n_absent / num_nodes
    "std_answers",           # desvio padrão das respostas numéricas
    "median_answers",        # mediana das respostas
    "mad_answers",           # MAD (desvio mediano absoluto)
    "consensus_margin_weighted",
    "consensus_margin_majority",
    "is_tie_weighted",
    "is_tie_majority",
]

HISTORY_FIELDS = [
    "experiment_id",
    "node_id",
    "profile",
    "checkpoint",   # 0 = inicial; k+1 = após rodada k
    "reputation",
]


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

class MetricsLogger:
    """Acumula e persiste as métricas de um experimento.

    Parameters
    ----------
    output_dir : str
        Caminho do diretório de saída.  Se ``overwrite=False`` (padrão) e o
        diretório já existir, levanta :class:`FileExistsError`.
    experiment_id : str, optional
        Identificador único do experimento.  Auto-gerado se não informado.
    overwrite : bool
        Se ``True``, escreve mesmo que o diretório já exista.  Use apenas
        para compatibilidade com execuções Docker onde o volume é pré-criado.
    """

    def __init__(
        self,
        output_dir: str,
        experiment_id: Optional[str] = None,
        overwrite: bool = False,
    ) -> None:
        if not overwrite and os.path.exists(output_dir):
            raise FileExistsError(
                f"Diretório já existe: {output_dir!r}. "
                "Use um experiment_id diferente ou experiment_id=None para auto-gerar."
            )
        os.makedirs(output_dir, exist_ok=True)
        self.output_dir = output_dir
        self.experiment_id = experiment_id or _generate_id()
        self.per_node_rows: list[dict] = []
        self.round_rows: list[dict] = []

    # ------------------------------------------------------------------
    def record_node(
        self,
        *,
        round_index: int,
        task_id: str,
        node_id: str,
        profile: str,
        answered: bool,
        answer,
        expected,
        correct: bool,
        abs_error,
        rel_error,
        latency_ms: int,
        score_initial: float,
        rep_update: "ReputationUpdate",
        weight_used: float,
        consensus_weighted_result,
        consensus_majority_result,
        consensus_weighted_correct: bool,
        consensus_majority_correct: bool,
        is_tie_weighted: bool,
        is_tie_majority: bool,
    ) -> None:
        self.per_node_rows.append({
            "experiment_id": self.experiment_id,
            "round_index": round_index,
            "task_id": task_id,
            "node_id": node_id,
            "profile": profile,
            "answered": int(answered),
            "answer": "" if answer is None else answer,
            "expected": "" if expected is None else expected,
            "correct": int(correct),
            "abs_error": "" if abs_error is None else round(abs_error, 4),
            "rel_error": "" if rel_error is None else round(rel_error, 4),
            "latency_ms": latency_ms,
            "score_initial": round(score_initial, 6),
            "reputation_before": round(rep_update.score_before, 6),
            "reputation_after": round(rep_update.score_after, 6),
            "delta": round(rep_update.delta, 6),
            "reward": round(rep_update.reward, 6),
            "punishment": round(rep_update.punishment, 6),
            "alpha_used": round(rep_update.alpha_used, 6),
            "mechanism": rep_update.mechanism,
            "weight_used": round(weight_used, 6),
            "consensus_weighted_result": (
                "" if consensus_weighted_result is None else consensus_weighted_result
            ),
            "consensus_majority_result": (
                "" if consensus_majority_result is None else consensus_majority_result
            ),
            "consensus_weighted_correct": int(consensus_weighted_correct),
            "consensus_majority_correct": int(consensus_majority_correct),
            "is_tie_weighted": int(is_tie_weighted),
            "is_tie_majority": int(is_tie_majority),
        })

    # ------------------------------------------------------------------
    def record_round(
        self,
        result: RoundResult,
        *,
        num_nodes: int,
        n_distinct_answers: int,
        n_absent: int,
        std_answers: Optional[float],
        median_answers: Optional[float],
        mad_answers: Optional[float],
        consensus_margin_weighted: float,
        consensus_margin_majority: float,
        is_tie_weighted: bool,
        is_tie_majority: bool,
    ) -> None:
        latencies = [r.latency_ms for r in result.responses if r.answer is not None]
        mean_latency = round(statistics.mean(latencies), 1) if latencies else 0.0
        absent_rate = round(n_absent / num_nodes, 4) if num_nodes else 0.0

        self.round_rows.append({
            "experiment_id": self.experiment_id,
            "round_index": result.round_index,
            "task_id": result.task_id,
            "expected": "" if result.expected is None else result.expected,
            "consensus_weighted": (
                "" if result.consensus_weighted is None else result.consensus_weighted
            ),
            "consensus_correct": int(result.consensus_correct),
            "consensus_majority": (
                "" if result.consensus_majority is None else result.consensus_majority
            ),
            "majority_correct": int(result.majority_correct),
            "num_responses": len(latencies),
            "num_nodes": num_nodes,
            "mean_latency_ms": mean_latency,
            "n_distinct_answers": n_distinct_answers,
            "n_absent": n_absent,
            "absent_rate": absent_rate,
            "std_answers": "" if std_answers is None else round(std_answers, 4),
            "median_answers": "" if median_answers is None else round(median_answers, 4),
            "mad_answers": "" if mad_answers is None else round(mad_answers, 4),
            "consensus_margin_weighted": round(consensus_margin_weighted, 6),
            "consensus_margin_majority": round(consensus_margin_majority, 6),
            "is_tie_weighted": int(is_tie_weighted),
            "is_tie_majority": int(is_tie_majority),
        })

    # ------------------------------------------------------------------
    def summary(
        self,
        final_reputations: dict[str, float],
        profiles: dict[str, str],
        tracker: Optional["ReputationTracker"] = None,
    ) -> dict:
        rounds = len(self.round_rows)
        consensus_correct = sum(r["consensus_correct"] for r in self.round_rows)
        majority_correct = sum(r["majority_correct"] for r in self.round_rows)
        latencies = [r["latency_ms"] for r in self.per_node_rows if r["answered"]]

        # Reputação final por perfil (instantâneo)
        by_profile_final: dict[str, list[float]] = {}
        for node_id, reputation in final_reputations.items():
            by_profile_final.setdefault(profiles.get(node_id, "unknown"), []).append(reputation)
        mean_rep_final = {
            p: round(statistics.mean(v), 4) for p, v in by_profile_final.items()
        }

        # Reputação média por perfil ao longo de todas as rodadas
        by_profile_mean: dict[str, list[float]] = {}
        for row in self.per_node_rows:
            profile = row["profile"]
            rep_after = row["reputation_after"]
            if isinstance(rep_after, (int, float)):
                by_profile_mean.setdefault(profile, []).append(float(rep_after))
        mean_rep_across_rounds = {
            p: round(statistics.mean(v), 4) for p, v in by_profile_mean.items()
        }

        result = {
            "experiment_id": self.experiment_id,
            "rounds": rounds,
            "consensus_accuracy_weighted": _ratio(consensus_correct, rounds),
            "consensus_accuracy_majority": _ratio(majority_correct, rounds),
            "mean_latency_ms": round(statistics.mean(latencies), 1) if latencies else 0.0,
            "final_reputation_by_profile": mean_rep_final,
            "final_reputation_by_node": {k: round(v, 4) for k, v in final_reputations.items()},
            "mean_reputation_by_profile_across_rounds": mean_rep_across_rounds,
        }
        return result

    # ------------------------------------------------------------------
    def flush(
        self,
        config: dict,
        tracker: "ReputationTracker",
        profiles: dict[str, str],
        seed: Optional[int] = None,
    ) -> dict:
        """Persiste todos os arquivos e retorna o resumo."""
        _write_csv(os.path.join(self.output_dir, "per_node.csv"), PER_NODE_FIELDS, self.per_node_rows)
        _write_csv(os.path.join(self.output_dir, "rounds.csv"), ROUND_FIELDS, self.round_rows)

        # Histórico de reputação (série temporal desnormalizada para plotar)
        history_rows = _build_history(self.experiment_id, tracker, profiles)
        _write_csv(
            os.path.join(self.output_dir, "reputation_history.csv"),
            HISTORY_FIELDS,
            history_rows,
        )

        final_reps = tracker.weights()
        summ = self.summary(final_reps, profiles, tracker)
        payload = {"config": config, "summary": summ}
        with open(os.path.join(self.output_dir, "summary.json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

        _write_manifest(
            os.path.join(self.output_dir, "manifest.json"),
            experiment_id=self.experiment_id,
            config=config,
            seed=seed,
            mechanism=tracker.mechanism,
            alpha=tracker.alpha,
            alpha_down=tracker.alpha_down,
            initial=tracker.initial,
        )
        return summ


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _generate_id() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _ratio(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


def _build_history(
    experiment_id: str,
    tracker: "ReputationTracker",
    profiles: dict[str, str],
) -> list[dict]:
    rows = []
    for node_id, checkpoints in tracker.history.items():
        profile = profiles.get(node_id, "unknown")
        for i, rep in enumerate(checkpoints):
            rows.append({
                "experiment_id": experiment_id,
                "node_id": node_id,
                "profile": profile,
                "checkpoint": i,   # 0 = inicial; k+1 = após rodada k
                "reputation": round(rep, 6),
            })
    return rows


def _write_manifest(
    path: str,
    *,
    experiment_id: str,
    config: dict,
    seed: Optional[int],
    mechanism: str,
    alpha: float,
    alpha_down: float,
    initial: float,
) -> None:
    git_sha = _git_sha()
    manifest = {
        "experiment_id": experiment_id,
        "created_at": datetime.datetime.now().isoformat(),
        "git_sha": git_sha,
        "mechanism": mechanism,
        "alpha": alpha,
        "alpha_down": alpha_down,
        "initial_reputation": initial,
        "seed": seed,
        "config": config,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)


def _git_sha() -> str:
    try:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return sha
    except Exception:
        return "unknown"


def _write_csv(path: str, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
