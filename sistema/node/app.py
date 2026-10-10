"""Servidor assíncrono do nó (worker) baseado em FastAPI.

Cada nó é executado em um container independente e expõe:

* ``GET /health``  — verificação de disponibilidade.
* ``POST /infer``  — recebe uma tarefa e devolve a resposta do nó.

Com ``PEERS`` definido o nó também participa do orquestrador dinâmico: guarda
uma cópia da cadeia (:class:`sistema.core.replica.Replica`), conversa apenas
com os vizinhos de ``NEIGHBORS`` e expõe:

* ``GET /leader``  — quem esta cópia elege para a próxima rodada.
* ``POST /lead``   — o eleito conduz a rodada: espalha a tarefa, monta a
  proposta, coleta os votos e divulga o resultado.
* ``POST /task``, ``POST /verify``, ``POST /commit`` — repassados de vizinho em
  vizinho (cada nó trata uma vez por rodada; se a mensagem é de outra cadeia,
  só repassa, sem responder nem votar).
* ``POST /oracle_vote``, ``POST /oracle`` — correção pelo gabarito.
* ``GET /answer``, ``GET /state``, ``GET /ledger`` — leitura para o
  coordenador de experimentos.

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

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..core import behavior
from ..core.answer import Answer, normalize
from ..core.consensus import weighted_consensus
from ..core.defenses import preset as defense_preset
from ..core.ledger import RoundRecord
from ..core.protocol import ProtocolConfig, Vote
from ..core.replica import Replica
from ..core.topology import build_graph
from .inference import MockBackend, ModelBackend

NODE_ID = os.getenv("NODE_ID") or os.getenv("HOSTNAME", "node")
PROFILE = os.getenv("PROFILE", behavior.HONEST)
INFERENCE_MODE = os.getenv("INFERENCE_MODE", "mock")
MODEL_NAME = os.getenv("MODEL_NAME", "HuggingFaceTB/SmolLM3-3B")
SEED = int(os.getenv("SEED", "0"))
MAX_SLEEP_MS = int(os.getenv("MAX_SLEEP_MS", "3000"))

# Parâmetros de comportamento propagados via environment (gen_compose.py).
_MALICIOUS_VALUE = os.getenv("MALICIOUS_VALUE")
_HONEST_P_CORRECT = os.getenv("HONEST_P_CORRECT")
_UNSTABLE_P_DROP = os.getenv("UNSTABLE_P_DROP")
_UNSTABLE_P_CORRECT = os.getenv("UNSTABLE_P_CORRECT")

_config = behavior.BehaviorConfig(
    malicious_collusion_value=int(_MALICIOUS_VALUE) if _MALICIOUS_VALUE else None,
    honest_p_correct=float(_HONEST_P_CORRECT) if _HONEST_P_CORRECT else 0.9,
    unstable_p_drop=float(_UNSTABLE_P_DROP) if _UNSTABLE_P_DROP else 0.3,
    unstable_p_correct=float(_UNSTABLE_P_CORRECT) if _UNSTABLE_P_CORRECT else 0.5,
)
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
    if _config.malicious_collusion_value is not None:
        return _config.malicious_collusion_value
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


# ---------------------------------------------------------------------------
# Orquestrador dinâmico
# ---------------------------------------------------------------------------

def _env_list(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


PEERS = _env_list("PEERS")
NEIGHBORS = _env_list("NEIGHBORS")
COLLUDERS = set(_env_list("COLLUDERS"))
NODE_URL_TEMPLATE = os.getenv("NODE_URL_TEMPLATE", "http://{id}:8000")
PROTOCOL_TIMEOUT_S = float(os.getenv("PROTOCOL_TIMEOUT_S", "60"))

_attacks = behavior.AttackConfig(
    leader_attack=os.getenv("LEADER_ATTACK", "none"),
    auditor_attack=os.getenv("AUDITOR_ATTACK", "none"),
)
_alpha_down = os.getenv("ALPHA_DOWN")
_protocol = ProtocolConfig(
    signal=os.getenv("SIGNAL", "hybrid"),
    alpha=float(os.getenv("ALPHA", "0.3")),
    mechanism=os.getenv("MECHANISM", "ema"),
    alpha_down=float(_alpha_down) if _alpha_down else None,
    initial=float(os.getenv("INITIAL_REPUTATION", "0.5")),
    test_every=int(os.getenv("TEST_EVERY", "10")),
    defense=defense_preset(os.getenv("DEFENSE", "all")),
)
_replica: Optional[Replica] = None
if PEERS:
    _graph = build_graph(
        PEERS,
        os.getenv("TOPOLOGY", "kregular"),
        degree=int(os.getenv("DEGREE", "4")),
        seed=int(os.getenv("GRAPH_SEED", "0")),
    )
    _replica = Replica(NODE_ID, PEERS, _protocol, _graph)

_answers: dict[int, tuple[Optional[Answer], int]] = {}
_seen: set[tuple[str, int]] = set()
_client: Optional[httpx.AsyncClient] = None


class TaskMessage(BaseModel):
    round_index: int
    task_id: str
    question: str
    expected: Optional[float] = None
    head: str
    sender: Optional[str] = None


class RecordMessage(BaseModel):
    round_index: int
    head: str
    record: dict
    votes: dict[str, dict] = {}
    sender: Optional[str] = None


class OracleMessage(BaseModel):
    record: dict
    votes: Optional[dict[str, bool]] = None


def _require_replica() -> Replica:
    if _replica is None:
        raise HTTPException(status_code=404, detail="Nó sem PEERS: orquestrador dinâmico desligado.")
    return _replica


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=PROTOCOL_TIMEOUT_S)
    return _client


async def _flood(path: str, payload: dict, exclude: Optional[str]) -> list[dict]:
    """Repassa a mensagem aos vizinhos (menos quem mandou) e junta as respostas."""
    targets = [n for n in NEIGHBORS if n != exclude]

    async def send(neighbor: str) -> Optional[dict]:
        try:
            response = await _http().post(
                f"{NODE_URL_TEMPLATE.format(id=neighbor)}{path}", json={**payload, "sender": NODE_ID},
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            return None

    results = await asyncio.gather(*(send(n) for n in targets))
    return [r for r in results if r]


def _route(phase: str, round_index: int, head: str, replica: Replica) -> str:
    """``skip`` (já vista), ``relay`` (outra cadeia: só repassa) ou ``process``."""
    key = (phase, round_index, head)
    if key in _seen:
        return "skip"
    _seen.add(key)
    return "process" if head == replica.head else "relay"


def _vote_json(vote: Vote) -> dict:
    return {"ok": vote.ok, "reason": vote.reason}


@app.get("/leader")
async def leader() -> dict:
    replica = _require_replica()
    elected, auditor, bootstrap = replica.elect()
    return {"leader": elected, "auditor": auditor, "bootstrap": bootstrap, "head": replica.head, "members": replica.members}


@app.post("/task")
async def task(message: TaskMessage) -> dict:
    replica = _require_replica()
    route = _route("task", message.round_index, message.head, replica)
    if route == "skip":
        return {"responses": {}, "depth": -1}

    async def own() -> None:
        if route == "process":
            _answers[message.round_index] = await _run_inference(
                InferRequest(task_id=message.task_id, question=message.question, expected=message.expected),
            )

    _, children = await asyncio.gather(own(), _flood("/task", message.model_dump(), message.sender))
    responses = {NODE_ID: _answers[message.round_index][0]} if route == "process" else {}
    depth = 0 if route == "process" else -1
    for child in children:
        responses.update(child.get("responses", {}))
        if child.get("depth", -1) >= 0:
            depth = max(depth, child["depth"] + 1)
    return {"responses": responses, "depth": depth}


@app.post("/verify")
async def verify(message: RecordMessage) -> dict:
    replica = _require_replica()
    route = _route("verify", message.round_index, message.head, replica)
    if route == "skip":
        return {"votes": {}}
    if route == "relay":
        votes: dict[str, dict] = {}
        for child in await _flood("/verify", message.model_dump(), message.sender):
            votes.update(child.get("votes", {}))
        return {"votes": votes}
    record = RoundRecord.from_json(message.record)
    own_answer = _answers.get(message.round_index, (None, 0))[0]
    vote = replica.vote(record, own_answer)
    if PROFILE == behavior.MALICIOUS:
        ok, reason = behavior.malicious_vote(
            leader_is_colluder=record.leader in COLLUDERS,
            is_auditor=record.auditor == NODE_ID,
            honest_ok=vote.ok,
            honest_reason=vote.reason,
            config=_attacks,
        )
        vote = Vote(NODE_ID, ok, reason)
    votes = {NODE_ID: _vote_json(vote)}
    for child in await _flood("/verify", message.model_dump(), message.sender):
        votes.update(child.get("votes", {}))
    return {"votes": votes}


@app.post("/commit")
async def commit(message: RecordMessage) -> dict:
    replica = _require_replica()
    route = _route("commit", message.round_index, message.head, replica)
    if route != "process":
        if route == "relay":
            await _flood("/commit", message.model_dump(), message.sender)
        return {"applied": False}
    record = RoundRecord.from_json(message.record)
    votes = {n: Vote(n, bool(v.get("ok")), v.get("reason", "")) for n, v in message.votes.items()}
    decision, refused, leaving = replica.commit(record, votes)
    await _flood("/commit", message.model_dump(), message.sender)
    return {
        "applied": True,
        "left": leaving,
        "refusers": refused,
        "decision": {
            "accepted": decision.accepted,
            "confirmed_mass": decision.confirmed_mass,
            "total_mass": decision.total_mass,
            "objective_reason": decision.objective_reason,
            "censored_complaints": decision.censored_complaints,
            "penalties": decision.penalties,
            "refuse_penalties": decision.refuse_penalties,
            "reason": decision.reason,
        },
    }


@app.post("/lead")
async def lead(message: TaskMessage) -> dict:
    """Conduz a rodada quando esta cópia elege o próprio nó."""
    replica = _require_replica()
    if message.head != replica.head:
        raise HTTPException(status_code=409, detail="Cadeia diferente da do coordenador.")
    elected, auditor, bootstrap = replica.elect()
    if elected != NODE_ID:
        raise HTTPException(status_code=409, detail=f"Esta cópia elege {elected}, não {NODE_ID}.")
    members = list(replica.members)
    head = replica.head

    spread = await task(message.model_copy(update={"sender": None}))
    attack = behavior.leader_attack(PROFILE, _attacks)
    record = replica.propose(
        round_index=message.round_index, task_id=message.task_id, leader=NODE_ID, auditor=auditor,
        responses={n: normalize(a) for n, a in spread["responses"].items()},
        attack=attack, colluders=COLLUDERS,
    )
    cons = weighted_consensus(list(record.responses), replica.state.consensus.weights())

    proposal = RecordMessage(round_index=message.round_index, head=head, record=record.to_json())
    votes = (await verify(proposal))["votes"]
    result = await commit(proposal.model_copy(update={"votes": votes}))
    return {
        "leader": NODE_ID,
        "auditor": auditor,
        "bootstrap": bootstrap,
        "attack": attack,
        "members": members,
        "hops": max(spread["depth"], 0),
        "record": record.to_json(),
        "votes": votes,
        "decision": result["decision"],
        "refusers": result["refusers"],
        "margin": cons.margin,
        "is_tie": cons.is_tie,
    }


@app.post("/oracle_vote")
async def oracle_vote() -> dict:
    _require_replica()
    ok = behavior.malicious_oracle_vote() if PROFILE == behavior.MALICIOUS else True
    return {"node_id": NODE_ID, "ok": ok}


@app.post("/oracle")
async def oracle(message: OracleMessage) -> dict:
    replica = _require_replica()
    status = replica.oracle(RoundRecord.from_json(message.record), message.votes)
    return {"node_id": NODE_ID, "status": status, "head": replica.head}


@app.get("/answer")
async def answer(round_index: int) -> dict:
    value, latency = _answers.get(round_index, (None, 0))
    return {"node_id": NODE_ID, "round_index": round_index, "answer": value, "latency_ms": latency, "received": round_index in _answers}


@app.get("/state")
async def state() -> dict:
    return _require_replica().snapshot()


@app.get("/ledger")
async def ledger() -> dict:
    replica = _require_replica()
    return {"node_id": NODE_ID, "valid": replica.ledger.verify_chain(), "records": replica.ledger.to_json()}
