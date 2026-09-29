"""Integração compartilhada da validação com os laços de experimento."""
from __future__ import annotations

import hashlib
import json
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
    parser.add_argument("--dataset-limit", type=int, default=None)


def load_tasks(source: str, limit=None, split: str = "test") -> list[dict]:
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError("Limite do dataset deve ser inteiro positivo.")
    if source == "sample":
        return dataset_module.load_sample(limit=limit)
    if source == "gsm8k" and split == "test":
        return dataset_module.load_gsm8k(split=split, limit=limit)
    raise ValueError("Use sample ou gsm8k com split=test.")


@dataclass
class ValidationPlan:
    tasks: list[dict]
    dataset: ValidationDataset
    enabled: bool
    count: int
    seed: int
    test_every: int
    source: str

    @classmethod
    def prepare(cls, rows, *, enabled=True, count=2, seed=42, test_every=10,
                source="sample:test"):
        if not isinstance(enabled, bool):
            raise ValueError("validation_enabled deve ser booleano.")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("validation_questions deve ser inteiro positivo.")
        is_test_round(0, test_every)
        if not rows:
            raise ValueError("Dataset vazio.")
        canonical = json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")
        version = source + ":sha256:" + hashlib.sha256(canonical).hexdigest()
        validated = ValidationDataset.from_rows(rows, version)
        if len({q.prompt for q in validated.questions}) != len(rows):
            raise ValueError("Enunciados duplicados impedem uma partição disjunta.")
        # Reserva pelo menos 20% e nunca esgota as tarefas normais.
        pool_size = max(count, len(rows) // 5)
        if pool_size >= len(rows):
            raise ValueError("Dataset insuficiente para separar tarefas e validação.")
        reserved = random.Random(f"{seed}:partition").sample(range(len(rows)), pool_size)
        reserved_set = set(reserved)
        tasks = [row for i, row in enumerate(rows) if i not in reserved_set]
        dataset = ValidationDataset([validated.questions[i] for i in reserved], version)
        return cls(tasks, dataset, enabled, count, seed, test_every, source)

    def metadata(self):
        return {
            "validation_enabled": self.enabled,
            "validation_questions": self.count,
            "validation_order": "after_normal_task",
            "normal_reputation_uses_ground_truth": False,
            "validation_uses_dataset_answers": True,
            "dataset_source": self.source,
            "dataset_version": self.dataset.version,
            "normal_question_ids": [r["id"] for r in self.tasks],
            "validation_question_ids": [q.question_id for q in self.dataset.questions],
            "dataset_is_training_provenance": False,
        }


class ValidationRuntime:
    def __init__(self, plan, tracker, logger, nodes: list[NodeSpec], client):
        self.plan = plan
        self.nodes = nodes
        self.selector = QuestionSelector(plan.dataset, random.Random(f"{plan.seed}:selection"))
        self.service = ValidationRoundService(
            tracker=tracker, client=client, store=ValidationStore(logger.output_dir),
            stats=NodeStats(), metrics=logger,
            history=ReputationHistoryStore(os.path.join(logger.output_dir, "validation_history.csv")),
        )
        self.experiment_id = logger.experiment_id

    def after_round(self, round_index):
        if not self.plan.enabled or not is_test_round(round_index, self.plan.test_every):
            return None
        return self.service.start(
            round_number=round_index + 1, nodes=self.nodes,
            questions=self.selector.select(self.plan.count), seed=self.plan.seed,
            dataset_version=self.plan.dataset.version,
            round_id=f"{self.experiment_id}:validation:{round_index + 1}",
        )
