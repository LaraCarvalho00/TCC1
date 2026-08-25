"""Servidor assíncrono do nó (worker) baseado em FastAPI.

Cada nó é executado em um container independente e expõe:

* ``GET /health``  — verificação de disponibilidade.
* ``POST /infer``  — recebe uma tarefa e devolve a resposta do nó.

O comportamento depende de ``PROFILE`` (honest/malicious/unstable) e o modo de
inferência de ``INFERENCE_MODE`` (``mock`` para validar comunicação sem modelo;
``model`` para executar de fato um LLM). A resposta simula o tempo de
processamento com ``asyncio.sleep`` e a inferência real roda em thread separada,
mantendo o servidor responsivo (coleta assíncrona pelo orquestrador).
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from ..core import behavior
from ..core.answer import Answer, normalize
from .inference import MockBackend, ModelBackend

NODE_ID = os.getenv("NODE_ID") or os.getenv("HOSTNAME", "node")
PROFILE = os.getenv("PROFILE", behavior.HONEST)
INFERENCE_MODE = os.getenv("INFERENCE_MODE", "mock")
MODEL_NAME = os.getenv("MODEL_NAME", "HuggingFaceTB/SmolLM3-3B")
SEED = int(os.getenv("SEED", "0"))
MAX_SLEEP_MS = int(os.getenv("MAX_SLEEP_MS", "3000"))
_MALICIOUS_VALUE = os.getenv("MALICIOUS_VALUE")

_config = behavior.BehaviorConfig()
_rng = random.Random(SEED)
_mock_backend = MockBackend(_config, _rng)
_model_backend: Optional[ModelBackend] = None

app = FastAPI(title=f"Node {NODE_ID}", version="1.0")


class InferRequest(BaseModel):
    task_id: str
    question: str
    expected: Optional[float] = None  # preenchido apenas em modo simulação


class InferResponse(BaseModel):
    node_id: str
    task_id: str
    answer: Optional[float] = None
    latency_ms: int
    profile: str


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "node_id": NODE_ID, "profile": PROFILE, "mode": INFERENCE_MODE}


@app.post("/infer", response_model=InferResponse)
async def infer(request: InferRequest) -> InferResponse:
    answer, latency_ms = await _run_inference(request)
    return InferResponse(
        node_id=NODE_ID,
        task_id=request.task_id,
        answer=answer,
        latency_ms=latency_ms,
        profile=PROFILE,
    )


async def _run_inference(request: InferRequest) -> tuple[Optional[Answer], int]:
    if INFERENCE_MODE == "mock":
        answer, latency = _mock_backend.solve(PROFILE, request.question, normalize(request.expected))
        await _sleep_ms(latency)
        return answer, latency

    # INFERENCE_MODE == "model" (processo real: nós não recebem gabarito).
    if PROFILE == behavior.MALICIOUS:
        latency = _rng.randint(*_config.malicious_latency_ms)
        await _sleep_ms(latency)
        return _malicious_answer(), latency

    if PROFILE == behavior.UNSTABLE:
        latency = _rng.randint(*_config.unstable_latency_ms)
        if _rng.random() < _config.unstable_p_drop:
            await _sleep_ms(latency)
            return None, latency
        answer = await _solve_with_model(request.question)
        if _rng.random() > _config.unstable_p_correct:
            answer = _corrupt(answer)
        return answer, latency

    started = time.perf_counter()
    answer = await _solve_with_model(request.question)
    latency = int((time.perf_counter() - started) * 1000)
    return answer, latency


async def _solve_with_model(question: str) -> Optional[Answer]:
    return await asyncio.to_thread(_get_model_backend().solve, question)


def _get_model_backend() -> ModelBackend:
    global _model_backend
    if _model_backend is None:
        _model_backend = ModelBackend(MODEL_NAME)
    return _model_backend


def _malicious_answer() -> Answer:
    if _MALICIOUS_VALUE is not None:
        return int(_MALICIOUS_VALUE)
    return _rng.randint(0, 100)


def _corrupt(answer: Optional[Answer]) -> Optional[Answer]:
    if answer is None:
        return None
    delta = 0
    while delta == 0:
        delta = _rng.randint(-5, 5)
    return answer + delta


async def _sleep_ms(milliseconds: int) -> None:
    await asyncio.sleep(min(milliseconds, MAX_SLEEP_MS) / 1000.0)
