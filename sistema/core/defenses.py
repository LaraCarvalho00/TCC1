"""Medidas contra conluio em maioria, com liga/desliga para a ablação.

Cada medida corresponde a um ponto em que um conluio com mais da metade da
massa de reputação vence o protocolo:

* ``calibration_rounds``     : o gabarito entra também nas primeiras rodadas,
                               fechando a largada com pesos iguais.
* ``oracle_bypasses_quorum`` : a correção pelo gabarito é aplicada por todas as
                               réplicas sem votação (o conluio não veta).
* ``split_alpha``            : taxa pequena para o sinal de consenso
                               (``consensus_alpha``) e alta para o gabarito
                               (``oracle_alpha``).
* ``split_scores``           : dois scores — consenso (peso da resposta) e poder
                               (eleição e quórum, só atualizado pelo gabarito).
* ``refuse_forged``          : nó honesto que não confirma um registro aceito
                               pelo quórum mantém a própria cópia da cadeia.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math

MEASURES = ("calibration", "oracle_bypass", "split_alpha", "split_scores", "refuse_forged")
DEFAULT_CALIBRATION_ROUNDS = 3


@dataclass(frozen=True)
class DefenseConfig:
    calibration_rounds: int = 0
    oracle_bypasses_quorum: bool = False
    split_alpha: bool = False
    consensus_alpha: float = 0.05
    oracle_alpha: float = 0.8
    split_scores: bool = False
    refuse_forged: bool = False
    # Calibração sem líder: nas ``calibration_rounds`` primeiras rodadas não há
    # eleição, proposta nem voto; o gabarito é gravado e aplicado sem quórum.
    # Fica fora de MEASURES para não alterar os presets da ablação.
    leaderless_calibration: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def active(self) -> list[str]:
        """Nomes das medidas ligadas, na ordem de :data:`MEASURES`."""
        flags = {
            "calibration": self.calibration_rounds > 0,
            "oracle_bypass": self.oracle_bypasses_quorum,
            "split_alpha": self.split_alpha,
            "split_scores": self.split_scores,
            "refuse_forged": self.refuse_forged,
        }
        return [name for name in MEASURES if flags[name]]


def _with(config: DefenseConfig, measure: str, on: bool) -> DefenseConfig:
    if measure == "calibration":
        return replace(config, calibration_rounds=DEFAULT_CALIBRATION_ROUNDS if on else 0)
    if measure == "oracle_bypass":
        return replace(config, oracle_bypasses_quorum=on)
    if measure == "split_alpha":
        return replace(config, split_alpha=on)
    if measure == "split_scores":
        return replace(config, split_scores=on)
    if measure == "refuse_forged":
        return replace(config, refuse_forged=on)
    raise ValueError(f"Medida desconhecida: {measure!r}")


def preset(name: str) -> DefenseConfig:
    """Perfis da ablação.

    ``none``, ``all``, o nome de uma medida (só ela ligada) ou
    ``all_minus_<medida>`` (todas menos ela).
    """
    base = DefenseConfig()
    if name == "none":
        return base
    if name == "all":
        config = base
        for measure in MEASURES:
            config = _with(config, measure, True)
        return config
    if name in MEASURES:
        return _with(base, name, True)
    if name.startswith("all_minus_"):
        measure = name[len("all_minus_"):]
        return _with(preset("all"), measure, False)
    raise ValueError(f"Preset desconhecido: {name!r}")


def preset_names() -> list[str]:
    """Todos os presets da ablação, na ordem usada nos gráficos."""
    return ["none", *MEASURES, "all", *(f"all_minus_{m}" for m in MEASURES)]


def with_overrides(config: DefenseConfig, *, calibration_rounds=None, consensus_alpha=None, oracle_alpha=None) -> DefenseConfig:
    """Aplica os parâmetros validados de defesa em todos os nós."""
    updates = {}
    if calibration_rounds is not None:
        try:
            if isinstance(calibration_rounds, bool):
                raise ValueError
            converted = int(calibration_rounds)
            if converted < 0 or str(converted) != str(calibration_rounds).strip():
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("calibration_rounds deve ser um inteiro não negativo") from exc
        updates["calibration_rounds"] = converted
    for name, value in (("consensus_alpha", consensus_alpha), ("oracle_alpha", oracle_alpha)):
        if value is not None:
            try:
                if isinstance(value, bool):
                    raise ValueError
                number = float(value)
                if not math.isfinite(number) or not 0 <= number <= 1:
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} deve estar entre 0 e 1") from exc
            updates[name] = number
    return replace(config, **updates)
