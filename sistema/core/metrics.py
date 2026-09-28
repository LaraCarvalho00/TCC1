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

``per_node.csv``, ``rounds.csv`` e ``reputation_history.csv`` são gravados de
forma **incremental**: cada linha é escrita e sincronizada em disco assim que a
rodada correspondente termina (ver :meth:`MetricsLogger.record_node` e
:meth:`MetricsLogger.record_round`).  Assim, se a execução for interrompida no
meio, todas as rodadas já processadas permanecem salvas.  ``flush`` apenas
finaliza os arquivos derivados (``summary.json``, ``manifest.json``) e fecha os
streams abertos.
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
    "is_test",           # 1 se a rodada é um teste fixo
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
    "is_test",               # 1 se esta rodada é um teste
    "test_round",            # número 1-based da rodada, vazio quando não é teste
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
    row_sync : bool
        Se ``True`` (padrão), cada linha de CSV é sincronizada em disco.
        A matriz de experimentos pode desligar isso para acelerar o lote;
        o fechamento do arquivo ainda descarrega o buffer.
    """

    def __init__(
        self,
        output_dir: str,
        experiment_id: Optional[str] = None,
        overwrite: bool = False,
        row_sync: bool = True,
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

        # --- Gravação incremental --------------------------------------
        # Abrimos os três CSVs de série temporal já no início e escrevemos
        # cada linha assim que a rodada é processada, sincronizando em disco.
        # Assim nenhuma rodada já concluída se perde numa interrupção.
        self._per_node_stream = _CsvStream(
            os.path.join(output_dir, "per_node.csv"), PER_NODE_FIELDS, sync=row_sync
        )
        self._round_stream = _CsvStream(
            os.path.join(output_dir, "rounds.csv"), ROUND_FIELDS, sync=row_sync
        )
        self._history_stream = _CsvStream(
            os.path.join(output_dir, "reputation_history.csv"), HISTORY_FIELDS, sync=row_sync
        )
        # Nós cujo checkpoint 0 (reputação inicial) já foi escrito no histórico.
        self._history_seed_written: set[str] = set()
        self._closed = False

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
        is_test: bool = False,
    ) -> None:
        row = {
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
            "is_test": int(is_test),
        }
        self.per_node_rows.append(row)
        self._per_node_stream.write(row)

        # Série temporal de reputação, gravada rodada a rodada.
        # checkpoint 0 = reputação inicial; checkpoint k+1 = após a rodada k.
        if node_id not in self._history_seed_written:
            self._history_stream.write({
                "experiment_id": self.experiment_id,
                "node_id": node_id,
                "profile": profile,
                "checkpoint": 0,
                "reputation": round(rep_update.score_before, 6),
            })
            self._history_seed_written.add(node_id)
        self._history_stream.write({
            "experiment_id": self.experiment_id,
            "node_id": node_id,
            "profile": profile,
            "checkpoint": round_index + 1,
            "reputation": round(rep_update.score_after, 6),
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
        is_test: bool = False,
    ) -> None:
        latencies = [r.latency_ms for r in result.responses if r.answer is not None]
        mean_latency = round(statistics.mean(latencies), 1) if latencies else 0.0
        absent_rate = round(n_absent / num_nodes, 4) if num_nodes else 0.0

        row = {
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
            "is_test": int(is_test),
            "test_round": (result.round_index + 1) if is_test else "",
        }
        self.round_rows.append(row)
        self._round_stream.write(row)

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
        test_rows = [r for r in self.round_rows if int(r.get("is_test", 0)) == 1]
        test_weighted = sum(r["consensus_correct"] for r in test_rows)
        test_majority = sum(r["majority_correct"] for r in test_rows)
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
            "test_rounds": [int(r["test_round"]) for r in test_rows],
            "n_test_rounds": len(test_rows),
            "consensus_accuracy_weighted_on_tests": _ratio(test_weighted, len(test_rows)),
            "consensus_accuracy_majority_on_tests": _ratio(test_majority, len(test_rows)),
            "tests": [
                {
                    "round": int(r["test_round"]),
                    "consensus_weighted_correct": int(r["consensus_correct"]),
                    "consensus_majority_correct": int(r["majority_correct"]),
                }
                for r in test_rows
            ],
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
        """Finaliza os arquivos derivados e retorna o resumo.

        ``per_node.csv``, ``rounds.csv`` e ``reputation_history.csv`` já foram
        gravados linha a linha durante a execução; aqui apenas fechamos os
        streams e escrevemos ``summary.json`` / ``manifest.json``.
        """
        self.close()

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

    # ------------------------------------------------------------------
    def close(self) -> None:
        """Fecha os streams CSV incrementais.  Idempotente."""
        if self._closed:
            return
        self._per_node_stream.close()
        self._round_stream.close()
        self._history_stream.close()
        self._closed = True

    def __enter__(self) -> "MetricsLogger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

class _CsvStream:
    """CSV gravado linha a linha, com ``flush`` + ``fsync`` a cada escrita.

    Mantém o arquivo aberto durante toda a execução e sincroniza cada linha
    em disco, de modo que uma interrupção (Ctrl+C, queda do container) não
    perca as rodadas já processadas.
    """

    def __init__(self, path: str, fieldnames: list[str], sync: bool = True) -> None:
        self.path = path
        self._sync_each = sync
        self._fh = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, fieldnames=fieldnames)
        self._writer.writeheader()
        self._sync()

    def write(self, row: dict) -> None:
        self._writer.writerow(row)
        self._sync()

    def _sync(self) -> None:
        self._fh.flush()
        if not self._sync_each:
            return
        try:
            os.fsync(self._fh.fileno())
        except (OSError, ValueError):
            # fsync pode não estar disponível (ex.: alguns sistemas de arquivos
            # de rede); flush já garante a entrega ao SO.
            pass

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

def _generate_id() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _ratio(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


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
