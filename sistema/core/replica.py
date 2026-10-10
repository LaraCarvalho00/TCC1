"""Cópia da cadeia guardada por um nó em container.

Reúne o que um nó precisa para participar do protocolo sem conhecer os perfis
dos outros: a cadeia, o estado derivado dela, os membros que seguem a mesma
cópia e o grafo (para escolher um auditor distante). Todas as decisões chamam
as mesmas funções de :mod:`sistema.core.protocol` usadas pela simulação local.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .answer import Answer
from .election import elect_leader, pick_auditor
from .ledger import Ledger, RoundRecord
from .protocol import (
    Decision,
    NetworkState,
    ProtocolConfig,
    Vote,
    apply_record,
    decide,
    objective_check,
    outcome_records,
    propose_record,
    refusers,
    tally_quorum,
    verify_record,
)
from .topology import Graph, node_sort_key


class Replica:
    def __init__(self, node_id: str, peers: Iterable[str], config: ProtocolConfig, graph: Graph) -> None:
        self.node_id = node_id
        self.config = config
        self.graph = graph
        ids = sorted(peers, key=node_sort_key)
        self.members: list[str] = list(ids)
        self.ledger = Ledger()
        self.state = NetworkState(ids, config)

    @property
    def head(self) -> str:
        return self.ledger.head

    # ------------------------------------------------------------------
    def elect(self) -> tuple[Optional[str], Optional[str], bool]:
        kwargs = self.config.election_kwargs()
        leader, bootstrap = elect_leader(self.state, self.members, margin=self.config.bootstrap_margin, **kwargs)
        auditor = pick_auditor(self.state, self.members, leader, self.graph, **kwargs)
        return leader, auditor, bootstrap

    def propose(
        self,
        *,
        round_index: int,
        task_id: str,
        leader: str,
        auditor: Optional[str],
        responses: dict[str, Optional[Answer]],
        attack: Optional[str] = None,
        colluders: Iterable[str] = (),
    ) -> RoundRecord:
        listed = {n: a for n, a in responses.items() if n in self.members}
        return propose_record(
            self.state, round_index=round_index, task_id=task_id, leader=leader, auditor=auditor,
            responses=listed, prev_hash=self.head, attack=attack, colluders=colluders,
        )

    def vote(self, record: RoundRecord, own_answer: Optional[Answer]) -> Vote:
        return verify_record(self.state, record, node_id=self.node_id, own_answer=own_answer, prev_hash=self.head)

    def commit(self, record: RoundRecord, votes: dict[str, Vote]) -> tuple[Decision, list[str], bool]:
        """Aplica o resultado da votação. Retorna ``(decisão, recusantes, saí?)``."""
        objective = objective_check(self.state, record)
        decision = decide(self.state, record, votes, objective)
        refused = refusers(votes, decision, self.config)
        leaving = self.node_id in refused
        for rec in outcome_records(record, decision, refuse=leaving):
            self.ledger.append(rec)
            apply_record(self.state, rec)
        if leaving:
            self.members = [m for m in self.members if m in refused]
        else:
            self.members = [m for m in self.members if m not in refused]
        return decision, refused, leaving

    def oracle(self, record: RoundRecord, votes: Optional[dict[str, bool]]) -> str:
        """Aplica a correção pelo gabarito (direto, ou se passou no quórum)."""
        if record.prev_hash != self.head:
            return "stale"
        if not self.config.defense.oracle_bypasses_quorum:
            members_votes = {n: ok for n, ok in (votes or {}).items() if n in self.members}
            _, _, accepted = tally_quorum(members_votes, self.state.power.weights())
            if not accepted:
                return "blocked"
        self.ledger.append(record)
        apply_record(self.state, record)
        return "applied"

    def snapshot(self) -> dict:
        return {
            "node_id": self.node_id,
            "head": self.head,
            "chain_length": len(self.ledger),
            "members": self.members,
            "consensus": self.state.consensus.weights(),
            "power": self.state.power.weights(),
        }
