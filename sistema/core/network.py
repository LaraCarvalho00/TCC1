"""Rede simulada com orquestrador eleito, em processo único.

Cada **grupo** é um conjunto de nós que compartilham a mesma cadeia (mesma
cabeça). No início todos estão no mesmo grupo. Se a medida ``refuse_forged``
está ligada e nós honestos recusam um registro que o quórum aprovou, eles
saem com a própria cópia da cadeia e formam um grupo novo: a rede se divide em
vez de aceitar a adulteração. Daí em diante cada grupo elege seu líder e roda
o protocolo só entre os próprios membros. As mensagens andam pelo grafo
inteiro: um nó de outra cadeia repassa aos vizinhos o que recebe, mas não
responde, não vota e não grava (os saltos contam esse caminho).

As decisões (eleição, proposta, verificação, quórum, gabarito) são as funções
puras de :mod:`sistema.core.protocol` e :mod:`sistema.core.election`, as
mesmas usadas pelos nós em containers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import behavior
from .answer import Answer
from .distance import choose_baseline, choose_weighted
from .election import elect_leader, pick_auditor
from .ledger import Ledger, RoundRecord
from .protocol import (
    Decision,
    NetworkState,
    ProtocolConfig,
    Vote,
    apply_record,
    calibration_record,
    decide,
    leaderless_calibration_round,
    malicious_acts_honest,
    objective_check,
    oracle_record,
    oracle_round,
    outcome_records,
    propose_record,
    tally_quorum,
    verify_record,
)
from .protocol import refusers as protocol_refusers
from .topology import Graph, distances, node_sort_key


@dataclass
class Group:
    gid: int
    members: list[str]
    ledger: Ledger
    state: NetworkState


@dataclass
class GroupRound:
    """O que aconteceu em um grupo numa rodada (uma linha de ``leadership.csv``)."""

    gid: int
    is_reference: bool
    members: list[str]
    leader: Optional[str]
    auditor: Optional[str]
    bootstrap: bool
    attack: Optional[str]
    record: Optional[RoundRecord]
    decision: Optional[Decision]
    votes: dict[str, Vote]
    hops: int
    refusers: list[str]
    fork_gid: Optional[int]
    malicious_power_mass: float
    margin: float
    is_tie: bool
    oracle: str = ""
    oracle_rejecters: int = 0
    committed: dict[str, Optional[Answer]] = field(default_factory=dict)


class SimulatedNetwork:
    def __init__(
        self,
        node_ids: list[str],
        profiles: dict[str, str],
        graph: Graph,
        config: ProtocolConfig,
        attacks: behavior.AttackConfig = behavior.AttackConfig(),
    ) -> None:
        self.node_ids = sorted(node_ids, key=node_sort_key)
        self.profiles = profiles
        self.graph = graph
        self.config = config
        self.attacks = attacks
        self.groups: list[Group] = [Group(0, list(self.node_ids), Ledger(), NetworkState(self.node_ids, config))]
        self._next_gid = 1

    # ------------------------------------------------------------------
    def _laying_low(self, round_index: int) -> bool:
        """Malicioso estratégico imita um honesto nesta rodada."""
        return malicious_acts_honest(round_index, self.config)

    def malicious(self, node_id: str) -> bool:
        return self.profiles.get(node_id) == behavior.MALICIOUS

    def group_of(self, node_id: str) -> Group:
        for group in self.groups:
            if node_id in group.members:
                return group
        raise KeyError(node_id)

    def reference_group(self) -> Group:
        """Grupo com mais nós não maliciosos (é onde a acurácia é medida)."""
        return max(
            self.groups,
            key=lambda g: (sum(1 for m in g.members if not self.malicious(m)), len(g.members), -g.gid),
        )

    def heads(self) -> dict[str, str]:
        return {m: g.ledger.head for g in self.groups for m in g.members}

    # ------------------------------------------------------------------
    def run_round(
        self,
        round_index: int,
        task_id: str,
        expected: Optional[Answer],
        answers: dict[str, Optional[Answer]],
    ) -> list[GroupRound]:
        reference_gid = self.reference_group().gid
        outcomes: list[GroupRound] = []
        forks: list[Group] = []
        if leaderless_calibration_round(round_index, self.config):
            return [
                self._calibration_in_group(group, round_index, task_id, expected, answers, group.gid == reference_gid)
                for group in self.groups
            ]
        for group in list(self.groups):
            outcome, fork = self._round_in_group(group, round_index, task_id, answers, group.gid == reference_gid)
            if oracle_round(round_index, self.config):
                outcome.oracle, outcome.oracle_rejecters = self._oracle(group, round_index, task_id, expected, answers)
                if fork is not None:
                    self._oracle(fork, round_index, task_id, expected, answers)
            if fork is not None:
                forks.append(fork)
            outcomes.append(outcome)
        self.groups = [g for g in self.groups + forks if g.members]
        return outcomes

    # ------------------------------------------------------------------
    def _round_in_group(
        self,
        group: Group,
        round_index: int,
        task_id: str,
        answers: dict[str, Optional[Answer]],
        is_reference: bool,
    ) -> tuple[GroupRound, Optional[Group]]:
        cfg = self.config
        state = group.state
        members = list(group.members)
        colluders = {m for m in members if self.malicious(m)}
        mass = state.power_mass(members)
        malicious_mass = state.power_mass(colluders) / mass if mass > 0 else 0.0

        leader, bootstrap = elect_leader(state, members, margin=cfg.bootstrap_margin, **cfg.election_kwargs())
        auditor = pick_auditor(state, members, leader, self.graph, **cfg.election_kwargs())

        dist = distances(self.graph, leader)
        reached = [m for m in members if m in dist]
        hops = max((dist[m] for m in reached), default=0)
        responses = {m: answers.get(m) for m in reached}

        leader_profile = self.profiles.get(leader, "")
        if self._laying_low(round_index):
            leader_profile = behavior.HONEST
        attack = behavior.leader_attack(leader_profile, self.attacks)
        prev = group.ledger.head
        record = propose_record(
            state,
            round_index=round_index,
            task_id=task_id,
            leader=leader,
            auditor=auditor,
            responses=responses,
            prev_hash=prev,
            attack=attack,
            colluders=colluders,
        )
        cons = choose_weighted(list(record.responses), state.consensus.weights(), cfg.consensus_mode)

        objective = objective_check(state, record)
        votes: dict[str, Vote] = {}
        for node in reached:
            honest = verify_record(state, record, node_id=node, own_answer=answers.get(node), prev_hash=prev, objective=objective)
            if self.malicious(node) and not self._laying_low(round_index):
                ok, reason = behavior.malicious_vote(
                    leader_is_colluder=self.malicious(leader),
                    is_auditor=node == auditor,
                    honest_ok=honest.ok,
                    honest_reason=honest.reason,
                    config=self.attacks,
                )
                votes[node] = Vote(node, ok, reason)
            else:
                votes[node] = honest
        decision = decide(state, record, votes, objective)

        refusers = protocol_refusers(votes, decision, cfg)

        fork: Optional[Group] = None
        if refusers:
            fork = Group(self._next_gid, refusers, group.ledger.copy(), state.clone())
            self._next_gid += 1
            for rec in outcome_records(record, decision, refuse=True):
                fork.ledger.append(rec)
                apply_record(fork.state, rec)

        for rec in outcome_records(record, decision):
            group.ledger.append(rec)
            apply_record(state, rec)
        group.members = [m for m in members if m not in refusers]

        committed = {m: (record.consensus if decision.accepted and m not in refusers else None) for m in members}
        outcome = GroupRound(
            gid=group.gid,
            is_reference=is_reference,
            members=members,
            leader=leader,
            auditor=auditor,
            bootstrap=bootstrap,
            attack=attack,
            record=record,
            decision=decision,
            votes=votes,
            hops=hops,
            refusers=refusers,
            fork_gid=fork.gid if fork else None,
            malicious_power_mass=malicious_mass,
            margin=cons.margin,
            is_tie=cons.is_tie,
            committed=committed,
        )
        return outcome, fork

    def _calibration_in_group(
        self,
        group: Group,
        round_index: int,
        task_id: str,
        expected: Optional[Answer],
        answers: dict[str, Optional[Answer]],
        is_reference: bool,
    ) -> GroupRound:
        """Rodada de calibração sem líder.

        A tarefa se espalha pelo grafo a partir do primeiro membro do grupo,
        cada nó responde e o registro grava as respostas e o gabarito. Não há
        eleição, proposta, voto nem quórum, então não há forja a aprovar. O
        consenso ponderado da rodada é calculado com a reputação de antes,
        só para a medida de acurácia; a reputação muda pelo gabarito.
        """
        state = group.state
        members = list(group.members)
        colluders = {m for m in members if self.malicious(m)}
        mass = state.power_mass(members)
        malicious_mass = state.power_mass(colluders) / mass if mass > 0 else 0.0

        dist = distances(self.graph, members[0])
        reached = [m for m in members if m in dist]
        hops = max((dist[m] for m in reached), default=0)
        responses = {m: answers.get(m) for m in reached}
        cons = choose_weighted(list(responses.items()), state.consensus.weights(), self.config.consensus_mode)

        record = calibration_record(
            prev_hash=group.ledger.head,
            round_index=round_index,
            task_id=task_id,
            expected=expected,
            responses=responses,
            consensus=cons.answer,
        )
        group.ledger.append(record)
        apply_record(state, record)

        return GroupRound(
            gid=group.gid,
            is_reference=is_reference,
            members=members,
            leader=None,
            auditor=None,
            bootstrap=False,
            attack=None,
            record=record,
            decision=None,
            votes={},
            hops=hops,
            refusers=[],
            fork_gid=None,
            malicious_power_mass=malicious_mass,
            margin=cons.margin,
            is_tie=cons.is_tie,
            oracle="calibration",
            committed={m: cons.answer for m in members},
        )

    def _oracle(
        self,
        group: Group,
        round_index: int,
        task_id: str,
        expected: Optional[Answer],
        answers: dict[str, Optional[Answer]],
    ) -> tuple[str, int]:
        """Correção pelo gabarito. Retorna ``(status, quantos votaram contra)``."""
        if not group.members:
            return "", 0
        graded = {m: answers.get(m) for m in group.members}
        record = oracle_record(
            prev_hash=group.ledger.head, round_index=round_index, task_id=task_id, expected=expected, graded=graded,
        )
        rejecters = 0
        if not self.config.defense.oracle_bypasses_quorum:
            votes = {
                m: (
                    behavior.malicious_oracle_vote()
                    if self.malicious(m) and not self._laying_low(round_index)
                    else True
                )
                for m in group.members
            }
            rejecters = sum(1 for ok in votes.values() if not ok)
            _, _, accepted = tally_quorum(votes, group.state.power.weights())
            if not accepted:
                return "blocked", rejecters
        group.ledger.append(record)
        apply_record(group.state, record)
        return "applied", rejecters


# ---------------------------------------------------------------------------
# Registro de métricas de uma rodada com orquestrador eleito
# ---------------------------------------------------------------------------

def leadership_row(
    outcome: GroupRound,
    *,
    round_index: int,
    profiles: dict[str, str],
    chain_length: int,
    chain_head: str,
) -> dict:
    decision = outcome.decision
    audit = outcome.votes.get(outcome.auditor) if outcome.auditor else None
    return {
        "round_index": round_index,
        "group_id": outcome.gid,
        "is_reference": int(outcome.is_reference),
        "n_members": len(outcome.members),
        "leader": outcome.leader or "",
        "leader_profile": profiles.get(outcome.leader or "", ""),
        "auditor": outcome.auditor or "",
        "auditor_profile": profiles.get(outcome.auditor or "", ""),
        "bootstrap": int(outcome.bootstrap),
        "attack": outcome.attack or "",
        "outcome": (
            "calibration" if outcome.oracle == "calibration"
            else "accepted" if decision and decision.accepted else "voided"
        ),
        "objective_reason": decision.objective_reason if decision else "",
        "reason": decision.reason if decision else "",
        "censored_complaints": decision.censored_complaints if decision else 0,
        "confirmed_mass": round(decision.confirmed_mass, 6) if decision else 0.0,
        "total_mass": round(decision.total_mass, 6) if decision else 0.0,
        "auditor_vote": "" if audit is None else int(audit.ok),
        "penalties": ";".join(f"{n}:{why}" for n, why in (decision.penalties if decision else [])),
        "refused_nodes": ";".join(outcome.refusers),
        "fork_group_id": "" if outcome.fork_gid is None else outcome.fork_gid,
        "hops": outcome.hops,
        "oracle": outcome.oracle,
        "oracle_rejecters": outcome.oracle_rejecters,
        "malicious_power_mass": round(outcome.malicious_power_mass, 6),
        "chain_length": chain_length,
        "chain_head": chain_head[:12],
    }


def log_round(
    logger,
    *,
    round_index: int,
    task_id: str,
    expected: Optional[Answer],
    responses: list,
    profiles: dict[str, str],
    reps_before: dict[str, float],
    reps_after: dict[str, float],
    reference_members: list[str],
    outcomes: list[GroupRound],
    chains: dict[int, tuple[int, str]],
    mechanism: str,
    initial: float,
    is_test: bool,
    consensus_mode: str = "exact",
    audited: bool = False,
    calibration: bool = False,
) -> None:
    """Grava ``per_node.csv``, ``rounds.csv`` e ``leadership.csv`` da rodada.

    O consenso da rodada é o que o grupo de referência (maioria dos nós não
    maliciosos, depois da rodada) gravou na própria cadeia; rodada anulada conta
    como sem consenso. A maioria simples continua sendo a linha de base sobre
    as respostas de todos os nós.
    """
    from .engine import answer_dispersion
    from .reputation import ReputationUpdate
    from .schemas import RoundResult

    committed: dict[str, Optional[Answer]] = {}
    for outcome in outcomes:
        committed.update(outcome.committed)
    anchor = next((m for m in reference_members if profiles.get(m) != behavior.MALICIOUS), None)
    if anchor is None and reference_members:
        anchor = reference_members[0]
    reference_consensus = committed.get(anchor) if anchor else None
    reference = next((o for o in outcomes if o.is_reference), outcomes[0] if outcomes else None)

    cons_m = choose_baseline([(r.node_id, r.answer) for r in responses], consensus_mode)
    result = RoundResult(
        round_index=round_index,
        task_id=task_id,
        expected=expected,
        consensus_weighted=reference_consensus,
        consensus_majority=cons_m.answer,
        responses=list(responses),
    )
    tie_w = reference.is_tie if reference else False
    for response in responses:
        node = response.node_id
        before = reps_before.get(node, initial)
        after = reps_after.get(node, before)
        delta = after - before
        update = ReputationUpdate(
            node_id=node,
            score_before=round(before, 6),
            score_after=round(after, 6),
            delta=round(delta, 6),
            reward=round(max(0.0, delta), 6),
            punishment=round(max(0.0, -delta), 6),
            alpha_used=0.0,
            s=1.0 if delta > 0 else 0.0,
            mechanism=mechanism,
        )
        correct = response.answer is not None and response.answer == expected
        abs_error = rel_error = None
        if response.answer is not None and expected is not None and not correct:
            try:
                abs_error = abs(float(response.answer) - float(expected))
                rel_error = abs_error / abs(float(expected)) if float(expected) != 0.0 else None
            except (TypeError, ValueError):
                pass
        logger.record_node(
            round_index=round_index,
            task_id=task_id,
            node_id=node,
            profile=response.profile,
            answered=response.answer is not None,
            answer=response.answer,
            expected=expected,
            correct=correct,
            abs_error=abs_error,
            rel_error=rel_error,
            latency_ms=response.latency_ms,
            score_initial=initial,
            rep_update=update,
            weight_used=before,
            consensus_weighted_result=reference_consensus,
            consensus_majority_result=cons_m.answer,
            consensus_weighted_correct=result.consensus_correct,
            consensus_majority_correct=result.majority_correct,
            is_tie_weighted=tie_w,
            is_tie_majority=cons_m.is_tie,
            is_test=is_test,
        )

    logger.record_round(
        result,
        num_nodes=len(responses),
        **answer_dispersion(responses),
        consensus_margin_weighted=reference.margin if reference else 0.0,
        consensus_margin_majority=cons_m.margin,
        is_tie_weighted=tie_w,
        is_tie_majority=cons_m.is_tie,
        is_test=is_test,
        audited=audited,
        calibration=calibration,
    )
    for outcome in outcomes:
        length, head = chains.get(outcome.gid, (0, ""))
        logger.record_leadership(
            leadership_row(outcome, round_index=round_index, profiles=profiles, chain_length=length, chain_head=head)
        )
