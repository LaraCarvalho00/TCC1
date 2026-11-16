"""Registro encadeado das decisões da rede.

Cada decisão (rodada aceita, rodada anulada, punição, correção pelo gabarito)
vira um :class:`RoundRecord` que aponta para o hash do registro anterior. O
estado da reputação é sempre derivado da cadeia: quem tem a mesma cadeia tem o
mesmo estado, e reescrever um registro antigo quebra o elo com o seguinte.

Não há mineração nem moeda: a cadeia serve só para que um líder não consiga
alterar o histórico de score sem que as outras cópias percebam.

Tipos de registro (``kind``):

* ``round``   : proposta do líder aceita pelo quórum (respostas, consenso e
                estado da reputação depois da rodada).
* ``void``    : rodada anulada; lista quem é punido.
* ``penalty`` : punição aplicada depois de uma rodada aceita (ex.: auditor que
                vetou uma proposta válida).
* ``oracle``  : correção pelo gabarito, emitida pelo juiz do experimento nas
                rodadas de calibração e de teste.
* ``calibration`` : rodada de calibração sem líder (opção
                ``leaderless_calibration``). Não há eleição, proposta nem voto:
                o registro guarda as respostas e o gabarito, e a reputação é
                atualizada pelo gabarito sem passar pelo quórum.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Callable, Optional

GENESIS_HASH = "0" * 64
KINDS = ("round", "void", "penalty", "oracle", "calibration")


@dataclass(frozen=True)
class RoundRecord:
    """Registro imutável de uma decisão da rede."""

    kind: str
    round_index: int
    prev_hash: str = GENESIS_HASH
    task_id: str = ""
    leader: Optional[str] = None
    auditor: Optional[str] = None
    # Pares [node_id, resposta] ordenados por node_id (resposta None = ausente).
    responses: tuple = ()
    consensus: Any = None
    # Estado completo da reputação depois do registro (só em ``round``).
    state_after: Optional[dict] = None
    state_hash: str = ""
    # Punições (``void`` / ``penalty``): pares [node_id, motivo].
    penalties: tuple = ()
    reason: str = ""
    # Correção (``oracle``): gabarito e respostas entregues ao juiz.
    expected: Any = None
    graded: tuple = ()
    hash: str = field(default="", compare=False)

    def content(self) -> dict:
        data = asdict(self)
        data.pop("hash", None)
        return data

    def sealed(self) -> "RoundRecord":
        """Devolve uma cópia com ``hash`` calculado sobre o conteúdo."""
        return replace(self, hash=canonical_hash(self.content()))

    def responses_map(self) -> dict[str, Any]:
        return {node_id: answer for node_id, answer in self.responses}

    def to_json(self) -> dict:
        return {**self.content(), "hash": self.hash}

    @staticmethod
    def from_json(data: dict) -> "RoundRecord":
        payload = dict(data)
        payload["responses"] = tuple(tuple(item) for item in payload.get("responses", ()))
        payload["penalties"] = tuple(tuple(item) for item in payload.get("penalties", ()))
        payload["graded"] = tuple(tuple(item) for item in payload.get("graded", ()))
        return RoundRecord(**payload)


def canonical_hash(obj: Any) -> str:
    """SHA-256 de um JSON canônico (chaves ordenadas, sem espaços)."""
    encoded = json.dumps(_canonical(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class Ledger:
    """Cadeia de registros de uma cópia (réplica) da rede."""

    def __init__(self, records: Optional[list[RoundRecord]] = None) -> None:
        self.records: list[RoundRecord] = []
        for record in records or []:
            self.append(record)

    @property
    def head(self) -> str:
        return self.records[-1].hash if self.records else GENESIS_HASH

    def __len__(self) -> int:
        return len(self.records)

    def append(self, record: RoundRecord) -> RoundRecord:
        """Anexa um registro; recusa elo quebrado ou hash adulterado."""
        if record.prev_hash != self.head:
            raise ValueError("prev_hash não aponta para a cabeça da cadeia.")
        if record.hash != canonical_hash(record.content()):
            raise ValueError("hash do registro não confere com o conteúdo.")
        if record.kind not in KINDS:
            raise ValueError(f"kind inválido: {record.kind!r}")
        self.records.append(record)
        return record

    def verify_chain(self) -> bool:
        """Confere todos os elos e hashes desde a origem."""
        prev = GENESIS_HASH
        for record in self.records:
            if record.prev_hash != prev or record.hash != canonical_hash(record.content()):
                return False
            prev = record.hash
        return True

    def copy(self) -> "Ledger":
        clone = Ledger()
        clone.records = list(self.records)
        return clone

    def replay(self, state: Any, apply: Callable[[Any, RoundRecord], None]) -> Any:
        """Reaplica todos os registros sobre ``state`` (auditoria por reexecução)."""
        for record in self.records:
            apply(state, record)
        return state

    def to_json(self) -> list[dict]:
        return [record.to_json() for record in self.records]

    @staticmethod
    def from_json(items: list[dict]) -> "Ledger":
        return Ledger([RoundRecord.from_json(item) for item in items])


def _canonical(obj: Any) -> Any:
    if isinstance(obj, float):
        if obj.is_integer():
            return int(obj)
        return round(obj, 10)
    if isinstance(obj, dict):
        return {str(key): _canonical(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_canonical(item) for item in obj]
    return obj
