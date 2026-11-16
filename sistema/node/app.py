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
from contextlib import asynccontextmanager
import hashlib
import os
import random
import threading
import time
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..core import behavior
from ..core.answer import Answer, normalize
from ..core.distance import choose_weighted
from ..core.defenses import preset as defense_preset, with_overrides
from ..core.ledger import RoundRecord
from ..core.protocol import ProtocolConfig, Vote, malicious_acts_honest, plan_audits
from ..core.replica import Replica
from ..core.topology import build_graph, node_sort_key
from .inference import MockBackend, ModelBackend
from .dedicated_inference import DedicatedModel

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
_dedicated_backend: Optional[DedicatedModel] = None
_model_lock = threading.RLock()

@asynccontextmanager
async def _lifespan(_app):
    if INFERENCE_MODE == "model" and os.getenv("MODEL_RUN_ID"):
        await asyncio.to_thread(lambda: _get_dedicated_backend().ensure_loaded())
    yield


app = FastAPI(title=f"Node {NODE_ID}", version="1.0", lifespan=_lifespan)


class InferRequest(BaseModel):
    task_id: str
    question: str
    expected: Optional[float] = None  # preenchido apenas em modo simulação
    round_index: int = 0


class InferResponse(BaseModel):
    node_id: str
    task_id: str
    answer: Optional[float] = None
    latency_ms: int
    profile: str


@app.get("/health")
async def health() -> dict:
    value = {"status": "ok", "node_id": NODE_ID, "profile": PROFILE, "mode": INFERENCE_MODE}
    if INFERENCE_MODE == "model" and os.getenv("MODEL_RUN_ID"):
        value.update(model_loaded=_dedicated_backend is not None and _dedicated_backend.loaded,
                     model_instances=1 if _dedicated_backend is not None and _dedicated_backend.loaded else 0,
                     quantization=os.getenv("MODEL_QUANTIZATION"))
    return value


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

    if INFERENCE_MODE == "gateway":
        return await _gateway_inference(request)

    if INFERENCE_MODE == "model" and os.getenv("MODEL_RUN_ID"):
        return await _dedicated_inference(request)

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


def _gateway_seed(round_index: int, node_id: str) -> int:
    encoded = f"{int(os.getenv('EXPERIMENT_SEED', '0'))}:{round_index}:{node_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big") & ((1 << 63) - 1)


def _get_dedicated_backend() -> DedicatedModel:
    global _dedicated_backend
    with _model_lock:
        if _dedicated_backend is None:
            _dedicated_backend = DedicatedModel(
                node_id=NODE_ID, run_id=os.environ["MODEL_RUN_ID"], model_name=MODEL_NAME,
                cache_dir=os.environ["MODEL_CACHE_DIR"], quantization=os.getenv("MODEL_QUANTIZATION", "nf4"),
                device=os.getenv("MODEL_DEVICE", "cuda"), revision=os.getenv("MODEL_REVISION"),
                max_new_tokens=int(os.getenv("MODEL_MAX_NEW_TOKENS", "256")),
                temperature=float(os.getenv("MODEL_TEMPERATURE", "0.7")), top_p=float(os.getenv("MODEL_TOP_P", "0.95")))
        return _dedicated_backend


async def _raw_dedicated(request: InferRequest) -> dict:
    return await asyncio.to_thread(_get_dedicated_backend().generate, round_index=request.round_index,
                                   task_id=request.task_id, question=request.question,
                                   seed=_gateway_seed(request.round_index, NODE_ID))


class ModelAnswerRequest(InferRequest):
    run_id: str
    node_id: str


@app.post("/model_answer")
async def model_answer(request: ModelAnswerRequest) -> dict:
    """Raw local generation used only to coordinate the experimental collusion."""
    if INFERENCE_MODE != "model" or not os.getenv("MODEL_RUN_ID"):
        raise HTTPException(status_code=404, detail="Dedicated model disabled")
    if request.run_id != os.environ["MODEL_RUN_ID"] or request.node_id != NODE_ID:
        raise HTTPException(status_code=409, detail="Model request belongs to another scenario or node")
    try:
        return {"node_id": NODE_ID, "run_id": request.run_id, **await _raw_dedicated(request)}
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def _dedicated_inference(request: InferRequest) -> tuple[Optional[Answer], int]:
    # Every participant, including each malicious participant, calls its OWN
    # resident model before applying the experimental attack transformation.
    raw = await _raw_dedicated(request)
    answer, latency, base_id = normalize(raw["answer"]), int(raw["latency_ms"]), NODE_ID
    if PROFILE == behavior.MALICIOUS and not malicious_acts_honest(request.round_index, _protocol):
        base_id = min(COLLUDERS, key=node_sort_key) if COLLUDERS else NODE_ID
        base = answer
        if base_id != NODE_ID:
            response = await _http().post(f"{NODE_URL_TEMPLATE.format(id=base_id)}/model_answer", json={
                "run_id": os.environ["MODEL_RUN_ID"], "node_id": base_id,
                "round_index": request.round_index, "task_id": request.task_id, "question": request.question})
            response.raise_for_status()
            payload = response.json()
            if payload.get("node_id") != base_id or payload.get("run_id") != os.environ["MODEL_RUN_ID"]:
                raise ValueError("Collusion base belongs to another node or scenario")
            base = normalize(payload["answer"])
        rng = random.Random(f"{int(os.getenv('EXPERIMENT_SEED', '0'))}:{request.round_index}:noise")
        noise_mode = os.getenv("NOISE_MODE", "relative")
        if noise_mode == "relative":
            answer = behavior.corrupt_relative(base, rng, float(os.getenv("NOISE_DISTANCE", "0.2")))
        elif noise_mode == "multiplicative":
            answer = behavior.corrupt_with_noise(base, rng)
        else:
            raise ValueError("Modo de ruído inválido.")
    await asyncio.to_thread(_get_dedicated_backend().record_response, request.round_index, answer, base_id)
    return answer, latency


async def _gateway_inference(request: InferRequest) -> tuple[Optional[Answer], int]:
    gateway = os.environ["GATEWAY_URL"].rstrip("/")
    run_id = os.environ["GATEWAY_RUN_ID"]
    async def generate(node_id: str, profile: str) -> tuple[Optional[Answer], int]:
        payload = {"run_id": run_id, "node_id": node_id, "profile": profile,
                   "round_index": request.round_index, "task_id": request.task_id,
                   "question": request.question, "seed": _gateway_seed(request.round_index, node_id)}
        # Muitos nós podem abrir a conexão ao mesmo tempo. Uma falha de
        # conexão não deve invalidar toda a rodada: repita com o mesmo pedido,
        # cuja identidade é idempotente no gateway. Não repetimos erros HTTP ou
        # de leitura, para não mascarar falhas de geração já em andamento.
        for attempt in range(8):
            try:
                response = await _http().post(f"{gateway}/inference", json=payload)
                break
            except httpx.ConnectError:
                if attempt == 7:
                    raise
                jitter = int.from_bytes(hashlib.sha256(node_id.encode("utf-8")).digest()[:2], "big") / 65535
                await asyncio.sleep(min(4.0, 0.25 * (2 ** attempt)) + jitter * 0.25)
        response.raise_for_status()
        result = response.json()
        return normalize(result["answer"]), int(result["latency_ms"])

    answer, latency = await generate(NODE_ID, PROFILE)
    if PROFILE == behavior.MALICIOUS and not malicious_acts_honest(request.round_index, _protocol):
        base_id = min(COLLUDERS, key=node_sort_key) if COLLUDERS else NODE_ID
        if base_id != NODE_ID:
            base, _ = await generate(base_id, behavior.MALICIOUS)
        else:
            base = answer
        noise_rng = random.Random(f"{int(os.getenv('EXPERIMENT_SEED', '0'))}:{request.round_index}:noise")
        noise_mode = os.getenv("NOISE_MODE", "relative")
        if noise_mode == "relative":
            answer = behavior.corrupt_relative(base, noise_rng, float(os.getenv("NOISE_DISTANCE", "0.2")))
        elif noise_mode == "multiplicative":
            answer = behavior.corrupt_with_noise(base, noise_rng)
        else:
            raise ValueError("Modo de ruído inválido.")
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
_audit_mode = os.getenv("AUDIT_MODE", "fixed")
_rounds = int(os.getenv("ROUNDS", "20"))
_test_every = int(os.getenv("TEST_EVERY", "10"))
_audited = plan_audits(int(os.getenv("EXPERIMENT_SEED", "0")), _rounds, _test_every,
                       float(os.getenv("AUDIT_P", "0.1"))) if _audit_mode == "random" else frozenset()
_protocol = ProtocolConfig(
    signal=os.getenv("SIGNAL", "hybrid"),
    alpha=float(os.getenv("ALPHA", "0.3")),
    mechanism=os.getenv("MECHANISM", "ema"),
    alpha_down=float(_alpha_down) if _alpha_down else None,
    initial=float(os.getenv("INITIAL_REPUTATION", "0.5")),
    test_every=_test_every,
    consensus_mode=os.getenv("CONSENSUS_MODE", "exact"),
    consensus_center=os.getenv("CONSENSUS_CENTER", "medoid"),
    validation_score=os.getenv("VALIDATION_SCORE", "graded"),
    malicious_strategy=os.getenv("MALICIOUS_STRATEGY", "always"),
    honest_rounds=int(os.getenv("HONEST_ROUNDS", "5")),
    audit_mode=_audit_mode,
    audited_rounds=_audited,
    alpha_up=float(os.getenv("ALPHA_UP", "0.1")),
    defense=with_overrides(
        defense_preset(os.getenv("DEFENSE", "all")),
        calibration_rounds=os.getenv("CALIBRATION_ROUNDS"),
        consensus_alpha=os.getenv("CONSENSUS_ALPHA"),
        oracle_alpha=os.getenv("ORACLE_ALPHA"),
    ),
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
                InferRequest(task_id=message.task_id, question=message.question, expected=message.expected,
                             round_index=message.round_index),
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
    cons = choose_weighted(
        list(record.responses), replica.state.consensus.weights(),
        replica.state.config.consensus_mode, replica.state.config.consensus_center,
    )

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
