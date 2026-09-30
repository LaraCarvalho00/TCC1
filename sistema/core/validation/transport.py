"""Cliente de nós para validação: payload nunca inclui gabarito."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .. import behavior
from ..answer import Answer, normalize
from ..enums import EvaluationOutcome
from .models import NodeSpec


FORBIDDEN_PAYLOAD_KEYS = ("expected", "expectedAnswer", "expected_answer", "answer")


def build_validation_payload(task_id: str, question: str) -> dict[str, Any]:
    payload = {"task_id": task_id, "question": question}
    for key in FORBIDDEN_PAYLOAD_KEYS:
        payload.pop(key, None)
    return payload


@dataclass
class NodeReply:
    node_id: str
    question_id: str
    answer: Optional[Answer]
    outcome_hint: str
    payload_sent: dict[str, Any]
    latency_ms: int = 0


class NodeClient:
    """Porta: envia só ``task_id`` + ``question``."""

    def ask(self, node: NodeSpec, task_id: str, question: str) -> NodeReply:
        raise NotImplementedError


Responder = Callable[[str, str], tuple[Optional[Answer], str]]


class ScriptedNodeClient(NodeClient):
    """Testes: mapa ``(node_id, question_id) -> (answer, outcome_hint)`` ou callable."""

    def __init__(self, responders: dict[str, Any] | None = None) -> None:
        self.responders = responders or {}
        self.payloads: list[dict[str, Any]] = []

    def ask(self, node: NodeSpec, task_id: str, question: str) -> NodeReply:
        payload = build_validation_payload(task_id, question)
        self.payloads.append(dict(payload))
        key = (node.node_id, task_id)
        spec = self.responders.get(key, self.responders.get(node.node_id))
        if callable(spec):
            answer, hint = spec(task_id, question)
        elif spec is None:
            answer, hint = None, EvaluationOutcome.TIMEOUT
        elif isinstance(spec, tuple):
            answer, hint = spec[0], spec[1] if len(spec) > 1 else EvaluationOutcome.CORRECT
        else:
            answer, hint = spec, EvaluationOutcome.CORRECT
        return NodeReply(
            node_id=node.node_id,
            question_id=task_id,
            answer=normalize(answer) if hint not in {EvaluationOutcome.TIMEOUT, EvaluationOutcome.ERROR} else None,
            outcome_hint=hint,
            payload_sent=payload,
        )


class SimulatedProfileClient(NodeClient):
    """Simula perfis localmente. Gabarito só no simulador, nunca no payload."""

    def __init__(
        self,
        profiles: dict[str, str],
        expected_by_question: dict[str, Answer],
        rng: random.Random,
        config: behavior.BehaviorConfig | None = None,
    ) -> None:
        self.profiles = profiles
        self.expected_by_question = expected_by_question
        self.rng = rng
        self.config = config or behavior.BehaviorConfig()
        self.payloads: list[dict[str, Any]] = []

    def ask(self, node: NodeSpec, task_id: str, question: str) -> NodeReply:
        payload = build_validation_payload(task_id, question)
        self.payloads.append(dict(payload))
        profile = self.profiles.get(node.node_id, node.profile)
        expected = self.expected_by_question[task_id]
        answer, latency = behavior.simulate_answer(profile, expected, self.config, self.rng)
        hint = EvaluationOutcome.TIMEOUT if answer is None else EvaluationOutcome.CORRECT
        return NodeReply(
            node_id=node.node_id,
            question_id=task_id,
            answer=normalize(answer),
            outcome_hint=hint,
            payload_sent=payload,
            latency_ms=latency,
        )


class HttpNodeClient(NodeClient):
    """Consulta HTTP ``POST /infer`` sem gabarito no JSON."""

    def __init__(self, timeout_s: float = 10.0) -> None:
        self.timeout_s = timeout_s
        self.payloads: list[dict[str, Any]] = []

    def ask(self, node: NodeSpec, task_id: str, question: str) -> NodeReply:
        payload = build_validation_payload(task_id, question)
        self.payloads.append(dict(payload))
        if not node.url:
            return NodeReply(
                node_id=node.node_id,
                question_id=task_id,
                answer=None,
                outcome_hint=EvaluationOutcome.ERROR,
                payload_sent=payload,
            )
        try:
            import httpx
        except ImportError:
            return NodeReply(
                node_id=node.node_id,
                question_id=task_id,
                answer=None,
                outcome_hint=EvaluationOutcome.ERROR,
                payload_sent=payload,
            )
        try:
            response = httpx.post(f"{node.url}/infer", json=payload, timeout=self.timeout_s)
            response.raise_for_status()
            data = response.json()
            return NodeReply(
                node_id=node.node_id,
                question_id=task_id,
                answer=normalize(data.get("answer")),
                outcome_hint=EvaluationOutcome.CORRECT,
                payload_sent=payload,
                latency_ms=int(data.get("latency_ms", 0)),
            )
        except httpx.TimeoutException:
            return NodeReply(
                node_id=node.node_id,
                question_id=task_id,
                answer=None,
                outcome_hint=EvaluationOutcome.TIMEOUT,
                payload_sent=payload,
                latency_ms=int(self.timeout_s * 1000),
            )
        except (httpx.HTTPError, ValueError, TypeError):
            return NodeReply(
                node_id=node.node_id,
                question_id=task_id,
                answer=None,
                outcome_hint=EvaluationOutcome.ERROR,
                payload_sent=payload,
            )
