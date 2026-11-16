"""Parâmetros de execução independentes dos scripts históricos."""
from __future__ import annotations

import argparse


def argumentos_simulacao(exp_id: str, **overrides) -> argparse.Namespace:
    values = dict(
        nodes=50, malicious=0.0, unstable=0.0, rounds=50, alpha=0.3,
        seed=0, honest_accuracy=0.9, collusion_value=None, unstable_p_drop=0.3,
        unstable_p_correct=0.5, mechanism="ema", alpha_down=None,
        initial_reputation=0.5, output="sistema/resultados/artigo_n50",
        experiment_id=exp_id, overwrite=True, test_every=10,
        row_sync=False, quiet=True, orchestration="dynamic", signal="hybrid",
        topology="kregular", degree=4, leader_attack="none", auditor_attack="none",
        defense="none", calibration_rounds=None, consensus_alpha=None,
        oracle_alpha=None, split_alpha=False, oracle_bypasses_quorum=False,
        split_scores=False, refuse_forged=False,
    )
    values.update(overrides)
    if values["malicious"] > 0 and values["collusion_value"] is None:
        values["collusion_value"] = 999
    return argparse.Namespace(**values)
