"""Protocolo de uma rodada com orquestrador eleito.

Funções puras usadas tanto pela simulação local quanto pelos nós em
containers. O estado da reputação (:class:`NetworkState`) é sempre derivado da
cadeia (:class:`~sistema.core.ledger.Ledger`) por :func:`apply_record`.

Fluxo de uma rodada:

1. ``elect_leader`` / ``pick_auditor`` (em :mod:`sistema.core.election`).
2. O líder monta a proposta com :func:`propose_record` a partir das respostas
   que chegaram pela árvore de difusão.
3. Cada participante confere com :func:`verify_record`: a própria resposta
   está no registro sem alteração, o consenso bate com as respostas e o estado
   da reputação bate com o recálculo local.
4. :func:`decide` soma a massa de reputação de poder de quem confirmou. Passa
   de metade da massa dos participantes: a proposta entra. Senão, a rodada é
   anulada e o líder é punido quando há motivo (forja, consenso falso ou
   censura).
5. Nas rodadas de calibração e de teste, o juiz do experimento emite um
   registro ``oracle`` (:func:`oracle_record`) que corrige pelo gabarito.

Sinais de reputação (``signal``):

* ``truth``     : só o gabarito atualiza a reputação, em toda rodada (equivale
                  ao orquestrador fixo de hoje).
* ``consensus`` : só a concordância com o consenso aceito (sem juiz).
* ``hybrid``    : consenso nas rodadas normais; gabarito na calibração e nos
                  testes.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .answer import Answer, normalize
from .behavior import AUDITOR_ATTACKS, LEADER_ATTACKS  # noqa: F401 (reexportados)
from .consensus import ConsensusResult
from .defenses import DefenseConfig
from .distance import choose_weighted, relative_distance
from .ledger import RoundRecord, canonical_hash
from .reputation import ReputationTracker, ReputationUpdate
from .schedule import DEFAULT_TEST_EVERY, is_test_round
from .topology import node_sort_key

SIGNALS = ("truth", "consensus", "hybrid")
CONSENSUS_MODES = ("exact", "distance")
MALICIOUS_STRATEGIES = ("always", "on_off")

# Motivos de recusa que qualquer nó consegue reproduzir a partir do registro.
OBJECTIVE_REASONS = ("false_consensus", "forged")


@dataclass(frozen=True)
class ProtocolConfig:
    signal: str = "hybrid"
    alpha: float = 0.3
    mechanism: str = "ema"
    alpha_down: Optional[float] = None
    initial: float = 0.5
    test_every: int = DEFAULT_TEST_EVERY
    punish_alpha: float = 0.5
    availability_window: int = 5
    max_absences: int = 1
    bootstrap_margin: float = 0.05
    election_caution: float = 2.0
    defense: DefenseConfig = field(default_factory=DefenseConfig)
    consensus_mode: str = "exact"
    malicious_strategy: str = "always"
    honest_rounds: int = 5

    def __post_init__(self) -> None:
        if self.signal not in SIGNALS:
            raise ValueError(f"signal deve ser um de {SIGNALS!r}.")
        if self.consensus_mode not in CONSENSUS_MODES:
            raise ValueError(f"consensus_mode deve ser um de {CONSENSUS_MODES!r}.")
        if self.malicious_strategy not in MALICIOUS_STRATEGIES:
            raise ValueError(f"malicious_strategy deve ser um de {MALICIOUS_STRATEGIES!r}.")

    @property
    def consensus_alpha(self) -> Optional[float]:
        return self.defense.consensus_alpha if self.defense.split_alpha else None

    @property
    def oracle_alpha(self) -> Optional[float]:
        return self.defense.oracle_alpha if self.defense.split_alpha else None

    def election_kwargs(self) -> dict:
        return {
            "window": self.availability_window,
            "max_absences": self.max_absences,
            "caution": self.election_caution,
        }


# ---------------------------------------------------------------------------
# Estado derivado da cadeia
# ---------------------------------------------------------------------------

class NetworkState:
    """Reputação de consenso, reputação de poder e disponibilidade.

    Sem ``split_scores``, ``power`` é a mesma instância de ``consensus``.
    """

    def __init__(self, node_ids: Iterable[str], config: ProtocolConfig) -> None:
        self.config = config
        self.node_ids = sorted(node_ids, key=node_sort_key)
        self.consensus = self._tracker()
        self.power = self._tracker() if config.defense.split_scores else self.consensus
        self.presence: dict[str, list[bool]] = {nid: [] for nid in self.node_ids}
        self.last_leader: Optional[str] = None
        self.rotation = 0

    def _tracker(self) -> ReputationTracker:
        c = self.config
        return ReputationTracker(
            self.node_ids, alpha=c.alpha, initial=c.initial, mechanism=c.mechanism, alpha_down=c.alpha_down,
        )

    @property
    def split(self) -> bool:
        return self.power is not self.consensus

    def clone(self) -> "NetworkState":
        twin = NetworkState.__new__(NetworkState)
        twin.config = self.config
        twin.node_ids = list(self.node_ids)
        twin.consensus = self.consensus.clone()
        twin.power = self.power.clone() if self.split else twin.consensus
        twin.presence = {nid: list(values) for nid, values in self.presence.items()}
        twin.last_leader = self.last_leader
        twin.rotation = self.rotation
        return twin

    def snapshot(self) -> dict:
        state = {"consensus": self.consensus.snapshot()}
        if self.split:
            state["power"] = self.power.snapshot()
        return state

    def restore(self, snapshot: dict) -> None:
        self.consensus.restore(snapshot["consensus"])
        if self.split and "power" in snapshot:
            self.power.restore(snapshot["power"])

    def state_hash(self) -> str:
        return canonical_hash(self.snapshot())

    def power_mass(self, nodes: Iterable[str]) -> float:
        return sum(max(0.0, self.power.get(n)) for n in nodes)


def leaderless_calibration_round(round_index: int, config: ProtocolConfig) -> bool:
    """Rodada de calibração sem líder (só com gabarito e a opção ligada)."""
    return (
        config.signal != "consensus"
        and config.defense.leaderless_calibration
        and round_index < config.defense.calibration_rounds
    )


def oracle_round(round_index: int, config: ProtocolConfig) -> bool:
    """Indica se o juiz do experimento corrige esta rodada pelo gabarito."""
    if config.signal == "consensus":
        return False
    if config.signal == "truth":
        return True
    return round_index < config.defense.calibration_rounds or is_test_round(round_index, config.test_every)


# ---------------------------------------------------------------------------
# Recálculo da rodada
# ---------------------------------------------------------------------------

def _pairs(responses: dict[str, Optional[Answer]]) -> list[tuple[str, Optional[Answer]]]:
    return [(nid, normalize(responses[nid])) for nid in sorted(responses, key=node_sort_key)]


def compute_round(
    state: NetworkState,
    responses: dict[str, Optional[Answer]],
    consensus: Any = "auto",
) -> tuple[ConsensusResult, Any, dict, dict[str, ReputationUpdate]]:
    """Consenso e estado da reputação depois da rodada, sem alterar ``state``.

    ``consensus`` força a resposta usada como referência do sinal (para o
    ataque de consenso falso); ``"auto"`` usa o consenso ponderado.
    """
    pairs = _pairs(responses)
    mode = state.config.consensus_mode
    result = choose_weighted(pairs, state.consensus.weights(), mode)
    reference = result.answer if consensus == "auto" else normalize(consensus)
    after = state.clone()
    updates: dict[str, ReputationUpdate] = {}
    if state.config.signal != "truth":
        for node_id, answer in pairs:
            if mode == "distance":
                if answer is None:
                    updates[node_id] = after.consensus.skip(node_id)
                    continue
                signal = 0.0 if reference is None else 1.0 - relative_distance(answer, reference)
                updates[node_id] = after.consensus.update(node_id, signal, alpha=state.config.consensus_alpha)
            else:
                agree = answer is not None and reference is not None and answer == reference
                updates[node_id] = after.consensus.update(node_id, agree, alpha=state.config.consensus_alpha)
    return result, reference, after.snapshot(), updates


def _forge(snapshot: dict, colluders: set[str]) -> dict:
    forged: dict = {}
    for part, data in snapshot.items():
        reputation = {}
        successes = dict(data.get("successes", {}))
        failures = dict(data.get("failures", {}))
        for nid in data["reputation"]:
            if "successes" in data:
                if nid in colluders:
                    successes[nid] = successes[nid] + 20.0
                else:
                    failures[nid] = failures[nid] + 20.0
                reputation[nid] = round(successes[nid] / (successes[nid] + failures[nid]), 12)
            else:
                reputation[nid] = 1.0 if nid in colluders else 0.0
        forged[part] = {"reputation": reputation}
        if "successes" in data:
            forged[part]["successes"] = successes
            forged[part]["failures"] = failures
    return forged


def propose_record(
    state: NetworkState,
    *,
    round_index: int,
    task_id: str,
    leader: str,
    auditor: Optional[str],
    responses: dict[str, Optional[Answer]],
    prev_hash: str,
    attack: Optional[str] = None,
    colluders: Iterable[str] = (),
) -> RoundRecord:
    """Proposta do líder. ``attack`` só é usado quando o líder é malicioso."""
    colluders = set(colluders)
    proposed = dict(responses)
    if attack == "censor":
        proposed = {nid: ans for nid, ans in proposed.items() if nid in colluders}

    result, reference, snapshot, _ = compute_round(state, proposed)
    consensus = reference
    if attack == "false_consensus":
        votes = Counter(normalize(a) for n, a in proposed.items() if n in colluders and a is not None)
        fake = votes.most_common(1)[0][0] if votes else None
        if fake is None or fake == consensus:
            fake = (consensus + 1) if isinstance(consensus, (int, float)) else 0
        _, consensus, snapshot, _ = compute_round(state, proposed, consensus=fake)
    if attack == "forge":
        snapshot = _forge(snapshot, colluders)

    return RoundRecord(
        kind="round",
        round_index=round_index,
        prev_hash=prev_hash,
        task_id=task_id,
        leader=leader,
        auditor=auditor,
        responses=tuple(tuple(p) for p in _pairs(proposed)),
        consensus=consensus,
        state_after=snapshot,
        state_hash=canonical_hash(snapshot),
    ).sealed()


# ---------------------------------------------------------------------------
# Verificação
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Vote:
    node_id: str
    ok: bool
    reason: str = ""


_MISSING = object()


def objective_check(state: NetworkState, record: RoundRecord) -> str:
    """Motivo objetivo de recusa ('' se a proposta é coerente).

    Qualquer nó com o mesmo estado chega ao mesmo resultado, sem precisar ter
    visto as respostas originais.
    """
    _, reference, snapshot, _ = compute_round(state, record.responses_map())
    if normalize(reference) != normalize(record.consensus):
        return "false_consensus"
    if canonical_hash(snapshot) != record.state_hash or canonical_hash(record.state_after) != record.state_hash:
        return "forged"
    return ""


def verify_record(
    state: NetworkState,
    record: RoundRecord,
    *,
    node_id: str,
    own_answer: Optional[Answer],
    prev_hash: str,
    objective: Optional[str] = None,
) -> Vote:
    """Voto de um nó honesto sobre a proposta.

    ``objective`` pode ser passado já calculado (é o mesmo para todos os nós
    com o mesmo estado).
    """
    if record.prev_hash != prev_hash:
        return Vote(node_id, False, "chain")
    if record.hash != canonical_hash(record.content()):
        return Vote(node_id, False, "hash")
    if own_answer is not None:
        listed = record.responses_map().get(node_id, _MISSING)
        if listed is _MISSING or normalize(listed) != normalize(own_answer):
            return Vote(node_id, False, "censored")
    reason = objective_check(state, record) if objective is None else objective
    return Vote(node_id, not reason, reason)


# ---------------------------------------------------------------------------
# Quórum e decisão
# ---------------------------------------------------------------------------

def tally_quorum(votes: dict[str, bool], weights: dict[str, float]) -> tuple[float, float, bool]:
    """Massa confirmada, massa total e se passou de metade (empate não passa)."""
    total = sum(max(0.0, weights.get(n, 0.0)) for n in votes)
    confirmed = sum(max(0.0, weights.get(n, 0.0)) for n, ok in votes.items() if ok)
    return confirmed, total, total > 0 and confirmed > 0.5 * total


@dataclass
class Decision:
    accepted: bool
    confirmed_mass: float
    total_mass: float
    objective_reason: str
    censored_complaints: int
    penalties: list[tuple[str, str]]
    refuse_penalties: list[tuple[str, str]]
    reason: str


def decide(state: NetworkState, record: RoundRecord, votes: dict[str, Vote], objective: str) -> Decision:
    """Resultado da votação, igual para todos que veem os mesmos votos."""
    confirmed, total, accepted = tally_quorum(
        {n: v.ok for n, v in votes.items()}, state.power.weights(),
    )
    censored = sum(1 for v in votes.values() if not v.ok and v.reason == "censored")
    leader, auditor = record.leader, record.auditor
    confirmers = sorted((n for n, v in votes.items() if v.ok and n != leader), key=node_sort_key)

    reason = objective or ("censored" if censored else "")
    culprits = [(leader, reason or "invalid")] + [(n, "confirmed_invalid") for n in confirmers]

    penalties: list[tuple[str, str]] = []
    if accepted:
        audit = votes.get(auditor) if auditor else None
        if audit is not None and not audit.ok and not objective and audit.reason != "censored":
            penalties.append((auditor, "false_reject"))
    elif objective:
        penalties = culprits
    elif censored:
        penalties = [(leader, "censored")]
    return Decision(
        accepted=accepted,
        confirmed_mass=confirmed,
        total_mass=total,
        objective_reason=objective,
        censored_complaints=censored,
        penalties=penalties,
        refuse_penalties=culprits,
        reason=reason,
    )


def refusers(votes: dict[str, Vote], decision: Decision, config: ProtocolConfig) -> list[str]:
    """Quem não aceita a proposta aprovada e passa a seguir a própria cópia.

    Só vale com ``refuse_forged``. Conta quem recusou com motivo verificável:
    censura da própria resposta, ou forja/consenso falso quando o recálculo
    objetivo confirma. Um veto sem fundamento (ex.: auditor que alega forja numa
    proposta coerente) não tira ninguém da rede.
    """
    if not (decision.accepted and config.defense.refuse_forged):
        return []
    out = []
    for node_id, vote in votes.items():
        if vote.ok:
            continue
        if vote.reason == "censored" or (decision.objective_reason and vote.reason == decision.objective_reason):
            out.append(node_id)
    return sorted(out, key=node_sort_key)


def outcome_records(record: RoundRecord, decision: Decision, *, refuse: bool = False) -> list[RoundRecord]:
    """Registros que uma réplica anexa depois da votação.

    ``refuse=True`` é o nó honesto que não aceita uma proposta aprovada pelo
    quórum (medida ``refuse_forged``): ele anexa uma anulação punindo o líder
    e quem confirmou, e passa a seguir a própria cópia da cadeia.
    """
    base = dict(round_index=record.round_index, task_id=record.task_id, leader=record.leader, auditor=record.auditor)
    if refuse:
        return [RoundRecord(
            kind="void", prev_hash=record.prev_hash, penalties=tuple(decision.refuse_penalties),
            reason=f"refused:{decision.reason or 'invalid'}", **base,
        ).sealed()]
    if not decision.accepted:
        return [RoundRecord(
            kind="void", prev_hash=record.prev_hash, penalties=tuple(decision.penalties),
            reason=decision.reason or "no_quorum", **base,
        ).sealed()]
    out = [record]
    if decision.penalties:
        out.append(RoundRecord(
            kind="penalty", prev_hash=record.hash, penalties=tuple(decision.penalties),
            reason="audit", **base,
        ).sealed())
    return out


# ---------------------------------------------------------------------------
# Gabarito (juiz do experimento)
# ---------------------------------------------------------------------------

def oracle_record(
    *,
    prev_hash: str,
    round_index: int,
    task_id: str,
    expected: Optional[Answer],
    graded: dict[str, Optional[Answer]],
) -> RoundRecord:
    return RoundRecord(
        kind="oracle",
        round_index=round_index,
        prev_hash=prev_hash,
        task_id=task_id,
        expected=normalize(expected),
        graded=tuple(tuple(p) for p in _pairs(graded)),
    ).sealed()


def calibration_record(
    *,
    prev_hash: str,
    round_index: int,
    task_id: str,
    expected: Optional[Answer],
    responses: dict[str, Optional[Answer]],
    consensus: Optional[Answer],
) -> RoundRecord:
    """Registro de uma rodada de calibração sem líder.

    ``consensus`` é só informativo (o consenso ponderado calculado com a
    reputação de antes da rodada); a reputação é atualizada pelo gabarito.
    """
    pairs = tuple(tuple(p) for p in _pairs(responses))
    return RoundRecord(
        kind="calibration",
        round_index=round_index,
        prev_hash=prev_hash,
        task_id=task_id,
        responses=pairs,
        consensus=normalize(consensus),
        expected=normalize(expected),
        graded=pairs,
    ).sealed()


# ---------------------------------------------------------------------------
# Aplicação de registros
# ---------------------------------------------------------------------------

def _punish(state: NetworkState, node_id: str) -> None:
    alpha = state.config.punish_alpha
    state.power.update(node_id, False, alpha=alpha)
    if state.split:
        state.consensus.update(node_id, False, alpha=alpha)


def apply_record(state: NetworkState, record: RoundRecord) -> None:
    """Atualiza o estado derivado com um registro já aceito pela réplica."""
    if record.kind == "round":
        state.restore(record.state_after)
        listed = record.responses_map()
        for nid in state.node_ids:
            history = state.presence.setdefault(nid, [])
            history.append(listed.get(nid) is not None)
            del history[:-max(1, state.config.availability_window)]
        state.last_leader = record.leader
        state.rotation += 1
    elif record.kind == "void":
        for nid, _ in record.penalties:
            _punish(state, nid)
        state.last_leader = record.leader
        state.rotation += 1
    elif record.kind == "penalty":
        for nid, _ in record.penalties:
            _punish(state, nid)
    elif record.kind in ("oracle", "calibration"):
        if record.kind == "calibration":
            listed = record.responses_map()
            for nid in state.node_ids:
                history = state.presence.setdefault(nid, [])
                history.append(listed.get(nid) is not None)
                del history[:-max(1, state.config.availability_window)]
        alpha = state.config.oracle_alpha
        for nid, answer in record.graded:
            if state.config.consensus_mode == "distance":
                if answer is None:
                    state.consensus.skip(nid)
                    if state.split:
                        state.power.skip(nid)
                    continue
                signal = 1.0 - relative_distance(answer, record.expected)
                state.consensus.update(nid, signal, alpha=alpha)
                if state.split:
                    state.power.update(nid, signal, alpha=alpha)
            else:
                correct = answer is not None and normalize(answer) == normalize(record.expected)
                state.consensus.update(nid, correct, alpha=alpha)
                if state.split:
                    state.power.update(nid, correct, alpha=alpha)


def replay(records: Iterable[RoundRecord], node_ids: Iterable[str], config: ProtocolConfig) -> NetworkState:
    """Reconstrói o estado a partir da origem (auditoria por reexecução)."""
    state = NetworkState(node_ids, config)
    for record in records:
        apply_record(state, record)
    return state
