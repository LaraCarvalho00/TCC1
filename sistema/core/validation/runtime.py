"""Integração compartilhada da validação com os laços de experimento."""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
from dataclasses import dataclass

from .. import dataset as dataset_module
from ..node_stats import NodeStats
from ..reputation_history import ReputationHistoryStore
from ..schedule import is_test_round
from .dataset import ValidationDataset
from .models import NodeSpec
from .selector import QuestionSelector
from .service import ValidationRoundService
from .store import ValidationStore


def add_validation_arguments(parser) -> None:
    parser.add_argument("--no-validation", dest="validation_enabled", action="store_false",
                        default=True, help="Desliga somente as consultas de validação.")
    parser.add_argument("--validation-questions", type=int, default=2,
                        help="Perguntas por nó em cada validação.")
    parser.add_argument("--min-confidence", type=float, default=0.55,
                        help="Confiança mínima para atualizar reputação normal.")
    parser.add_argument("--dataset", choices=["sample", "gsm8k"], default="sample")
    parser.add_argument("--dataset-split", choices=["train", "test"], default="train",
                        help="Split usado; escolha train quando a auditoria precisar refletir dados de treinamento.")
    parser.add_argument("--dataset-limit", type=int, default=None)
    parser.add_argument("--validation-pool-size", type=int, default=5,
                        help="Tamanho fixo da partição de auditoria, independente de perguntas por teste.")
    parser.add_argument("--audit-failures-to-lock", type=int, default=2,
                        help="Erros de gabarito no bloco para limitar recuperação operacional.")
    parser.add_argument("--audit-weight-cap", type=float, default=0.10,
                        help="Peso máximo enquanto o nó estiver bloqueado por auditoria.")
    parser.add_argument("--recovery-cap", type=float, default=0.05,
                        help="Aumento operacional máximo do peso por rodada durante bloqueio.")
    parser.add_argument("--audit-timeout-policy", choices=["hold", "penalize"], default="penalize",
                        help="Penalizar após uma sequência de timeouts ou mantê-los em hold.")
    parser.add_argument("--audit-timeout-strikes", type=int, default=3,
                        help="Timeouts consecutivos antes da penalização opcional.")


def load_tasks(source: str, limit=None, split: str = "test") -> list[dict]:
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError("Limite do dataset deve ser inteiro positivo.")
    if source == "sample":
        return dataset_module.load_sample(limit=limit)
    if source == "gsm8k" and split in {"train", "test"}:
        return dataset_module.load_gsm8k(split=split, limit=limit)
    raise ValueError("Use sample ou gsm8k com split=train/test.")


@dataclass
class ValidationPlan:
    tasks: list[dict]
    dataset: ValidationDataset
    enabled: bool
    count: int
    seed: int
    test_every: int
    source: str
    pool_size: int
    audit_failures_to_lock: int = 2
    audit_weight_cap: float = 0.10
    recovery_cap: float = 0.05
    audit_timeout_policy: str = "penalize"
    audit_timeout_strikes: int = 3

    @classmethod
    def prepare(cls, rows, *, enabled=True, count=2, pool_size=5, seed=42, test_every=10,
                source="sample:test", audit_failures_to_lock=2, audit_weight_cap=0.10,
                recovery_cap=0.05, audit_timeout_policy="penalize", audit_timeout_strikes=3):
        if not isinstance(enabled, bool):
            raise ValueError("validation_enabled deve ser booleano.")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("validation_questions deve ser inteiro positivo.")
        if isinstance(pool_size, bool) or not isinstance(pool_size, int) or pool_size < count:
            raise ValueError("validation_pool_size deve ser inteiro e maior ou igual às perguntas por teste.")
        is_test_round(0, test_every)
        if not rows:
            raise ValueError("Dataset vazio.")
        canonical = json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")
        version = source + ":sha256:" + hashlib.sha256(canonical).hexdigest()
        validated = ValidationDataset.from_rows(rows, version)
        if len({q.prompt for q in validated.questions}) != len(rows):
            raise ValueError("Enunciados duplicados impedem uma partição disjunta.")
        if pool_size >= len(rows):
            raise ValueError("Dataset insuficiente para separar tarefas e validação.")
        if isinstance(audit_failures_to_lock, bool) or not isinstance(audit_failures_to_lock, int) or audit_failures_to_lock < 1:
            raise ValueError("audit_failures_to_lock deve ser inteiro positivo.")
        if (isinstance(audit_weight_cap, bool) or not isinstance(audit_weight_cap, (int, float))
                or not math.isfinite(audit_weight_cap) or not 0 <= audit_weight_cap <= 1
                or isinstance(recovery_cap, bool) or not isinstance(recovery_cap, (int, float))
                or not math.isfinite(recovery_cap) or not 0 <= recovery_cap <= 1):
            raise ValueError("Limites de peso/recovery devem estar em [0, 1].")
        if audit_timeout_policy not in {"hold", "penalize"}:
            raise ValueError("audit_timeout_policy deve ser hold ou penalize.")
        if isinstance(audit_timeout_strikes, bool) or not isinstance(audit_timeout_strikes, int) or audit_timeout_strikes < 1:
            raise ValueError("audit_timeout_strikes deve ser inteiro positivo.")
        reserved = random.Random(f"{seed}:partition").sample(range(len(rows)), pool_size)
        reserved_set = set(reserved)
        tasks = [row for i, row in enumerate(rows) if i not in reserved_set]
        dataset = ValidationDataset([validated.questions[i] for i in reserved], version)
        return cls(tasks, dataset, enabled, count, seed, test_every, source, pool_size,
                   audit_failures_to_lock, audit_weight_cap, recovery_cap,
                   audit_timeout_policy, audit_timeout_strikes)

    def metadata(self):
        return {
            "validation_enabled": self.enabled,
            "validation_questions": self.count,
            "validation_pool_size": self.pool_size,
            "audit_failures_to_lock": self.audit_failures_to_lock,
            "audit_weight_cap": self.audit_weight_cap,
            "recovery_cap": self.recovery_cap,
            "audit_timeout_policy": self.audit_timeout_policy,
            "audit_timeout_strikes": self.audit_timeout_strikes,
            "validation_order": "after_normal_task",
            "normal_reputation_uses_ground_truth": False,
            "validation_uses_dataset_answers": True,
            "dataset_source": self.source,
            "dataset_version": self.dataset.version,
            "dataset_split": ("bundled" if self.source.startswith("sample:")
                              else self.source.rsplit(":", 1)[-1]),
            "normal_question_ids": [r["id"] for r in self.tasks],
            "validation_question_ids": [q.question_id for q in self.dataset.questions],
            "dataset_is_training_provenance": (
                self.source.startswith("gsm8k:") and self.source.endswith(":train")
            ),
        }


class ValidationRuntime:
    def __init__(self, plan, tracker, logger, nodes: list[NodeSpec], client):
        self.plan = plan
        self.nodes = nodes
        self.selector = QuestionSelector(plan.dataset, random.Random(f"{plan.seed}:selection"))
        self.stats = NodeStats()
        self.store = ValidationStore(logger.output_dir)
        self.stats.rebuild_from_results(self.store.results)
        tracker.configure_audit(
            failures_to_lock=getattr(plan, "audit_failures_to_lock", 2),
            weight_cap=getattr(plan, "audit_weight_cap", 0.10),
            recovery_cap=getattr(plan, "recovery_cap", 0.05),
        )
        self.tracker = tracker
        self.service = ValidationRoundService(
            tracker=tracker, client=client, store=self.store,
            stats=self.stats, metrics=logger,
            history=ReputationHistoryStore(os.path.join(logger.output_dir, "validation_history.csv")),
            timeout_policy=getattr(plan, "audit_timeout_policy", "penalize"),
            timeout_strikes=getattr(plan, "audit_timeout_strikes", 3),
        )
        self.experiment_id = logger.experiment_id

    def after_round(self, round_index):
        if not self.plan.enabled or not is_test_round(round_index, self.plan.test_every):
            return None
        round_number = round_index + 1
        if self.service.metrics is not None:
            self.service.metrics.record_audit_state(round_number, self.tracker, "before")
        result = self.service.start(
            round_number=round_number, nodes=self.nodes,
            questions=self.selector.select(self.plan.count), seed=self.plan.seed,
            dataset_version=self.plan.dataset.version,
            round_id=f"{self.experiment_id}:validation:{round_index + 1}",
        )
        if result.status == "COMPLETED":
            outcomes = self.service.store.results_for_round(result.id)
            self.tracker.apply_audit_round(outcomes, self.plan.count, len(self.nodes))
            if self.service.metrics is not None:
                self.service.metrics.record_audit_state(result.round_number, self.tracker, "after")
        return result
