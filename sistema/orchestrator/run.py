"""Coordenador experimental do protocolo de orquestração dinâmica."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any, Optional

import httpx
import yaml

from ..core import dataset as dataset_module
from ..core.answer import normalize
from ..core.defenses import preset as defense_preset, with_overrides
from ..core.ledger import RoundRecord
from ..core.metrics import MetricsLogger, dynamic_summary
from ..core.network import GroupRound, log_round
from ..core.protocol import Decision, ProtocolConfig, Vote, oracle_record, oracle_round, plan_audits
from ..core.reputation import ReputationTracker
from ..core.schedule import DEFAULT_TEST_EVERY, is_test_round, test_rounds_1based
from ..core.schemas import NodeResponse
from ..core.topology import build_graph, diameter, max_degree, node_sort_key

_DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), "..", "config", "experiment.yaml")


# ---------------------------------------------------------------------------
# Config e dataset
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_tasks(config: dict) -> list[dict]:
    source = config.get("dataset", "sample")
    limit = config.get("num_tasks")
    if source == "task_bank":
        with open(config["task_bank"], encoding="utf-8") as handle:
            data = json.load(handle)
        tasks = [{k: task[k] for k in ("id", "question", "answer")} for task in data["tarefas"]]
        return tasks[:limit] if limit else tasks
    if source == "gsm8k":
        return dataset_module.load_gsm8k(split=config.get("split", "test"), limit=limit)
    return dataset_module.load_sample(limit=limit)


# ---------------------------------------------------------------------------
# Coleta de respostas via HTTP
# ---------------------------------------------------------------------------

async def wait_for_nodes(
    client: httpx.AsyncClient,
    nodes: list[dict],
    retries: int = 30,
    delay: float = 1.0,
) -> None:
    """Aguarda todos os nós responderem em ``/health`` antes de iniciar."""
    for node in nodes:
        for _ in range(retries):
            try:
                response = await client.get(f"{node['url']}/health", timeout=2.0)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(delay)


# ---------------------------------------------------------------------------
# Laço principal
# ---------------------------------------------------------------------------

async def _get(client: httpx.AsyncClient, url: str, timeout: float, **params) -> Optional[dict]:
    try:
        response = await client.get(url, params=params or None, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        return None


async def _post(client: httpx.AsyncClient, url: str, payload: dict, timeout: float) -> Optional[dict]:
    try:
        response = await client.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        return None


def _protocol_config(config: dict) -> ProtocolConfig:
    alpha_down = config.get("alpha_down")
    audit_mode = config.get("audit_mode", "fixed")
    audited = plan_audits(int(config.get("seed", 0)), int(config.get("rounds", 20)),
                          int(config.get("test_every", DEFAULT_TEST_EVERY)), float(config.get("audit_p", 0.1))) if audit_mode == "random" else frozenset()
    return ProtocolConfig(
        signal=config.get("signal", "hybrid"),
        alpha=float(config.get("alpha", 0.3)),
        mechanism=config.get("reputation_mechanism", "ema"),
        alpha_down=float(alpha_down) if alpha_down is not None else None,
        initial=float(config.get("initial_reputation", 0.5)),
        test_every=int(config.get("test_every", DEFAULT_TEST_EVERY)),
        consensus_mode=config.get("consensus_mode", "exact"),
        consensus_center=config.get("consensus_center", "medoid"),
        validation_score=config.get("validation_score", "graded"),
        malicious_strategy=config.get("malicious_strategy", "always"),
        honest_rounds=int(config.get("honest_rounds", 5)),
        audit_mode=audit_mode,
        audited_rounds=audited,
        alpha_up=float(config.get("alpha_up", 0.1)),
        defense=with_overrides(
            defense_preset(config.get("defense", "all")),
            calibration_rounds=config.get("calibration_rounds"),
            consensus_alpha=config.get("consensus_alpha"),
            oracle_alpha=config.get("oracle_alpha"),
        ),
    )


def _groups_by_head(states: dict[str, dict]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for node_id in sorted(states, key=node_sort_key):
        groups.setdefault(states[node_id]["head"], []).append(node_id)
    return groups


async def run_dynamic_experiment(config: dict) -> dict:
    """Rodadas conduzidas pelos próprios nós (líder eleito pela cadeia).

    O coordenador não decide nada do protocolo: pergunta a um nó de cada cópia
    da cadeia quem é o eleito, pede que ele conduza a rodada, entrega o
    gabarito nas rodadas de calibração e de teste (juiz do experimento) e lê o
    estado dos nós para registrar as métricas com o mesmo formato da simulação.
    """
    nodes: list[dict] = config["nodes"]
    urls = {node["id"]: node["url"] for node in nodes}
    node_ids = sorted(urls, key=node_sort_key)
    profiles = {node["id"]: node.get("profile", "unknown") for node in nodes}
    malicious = {n for n, p in profiles.items() if p == "malicious"}

    def honest_count(members: list[str]) -> int:
        return sum(1 for m in members if m not in malicious)

    tasks = load_tasks(config)
    if not tasks:
        raise RuntimeError("Nenhuma tarefa carregada.")
    rounds = config.get("rounds") or len(tasks)
    cfg = _protocol_config(config)
    planned_tests = test_rounds_1based(rounds, cfg.test_every)
    mode = config.get("mode", "simulation")
    timeout = float(config.get("timeout_s", 60))
    strict_inference = config.get("inference_mode") in ("gateway", "model")
    output_dir = config.get("output_dir", os.path.join("sistema", "results", "experimento"))
    graph = build_graph(node_ids, config.get("topology", "kregular"), degree=int(config.get("degree", 4)), seed=int(config.get("seed", 0)))

    logger = MetricsLogger(output_dir, experiment_id=config.get("experiment_id"), overwrite=True)
    gid_of: dict[str, int] = {n: 0 for n in node_ids}
    next_gid = 1
    states: dict[str, dict] = {}

    async def read_states(client: httpx.AsyncClient) -> dict[str, dict]:
        got = await asyncio.gather(*(_get(client, f"{urls[n]}/state", timeout) for n in node_ids))
        states = {n: s for n, s in zip(node_ids, got) if s}
        if strict_inference and len(states) != len(node_ids):
            raise RuntimeError("Não foi possível consultar o estado de todos os nós.")
        return states

    try:
        async with httpx.AsyncClient() as client:
            await wait_for_nodes(client, nodes)
            states = await read_states(client)
            for round_index in range(rounds):
                task = tasks[round_index % len(tasks)]
                expected = normalize(task["answer"])
                this_is_test = is_test_round(round_index, cfg.test_every)
                before = {n: s["consensus"].get(n, cfg.initial) for n, s in states.items()}

                groups = _groups_by_head(states)
                reference_head = max(groups, key=lambda h: (honest_count(groups[h]), len(groups[h])))
                outcomes: list[GroupRound] = []
                for head, members in groups.items():
                    outcome = await _lead_group(
                        client, urls, members, head, round_index, task, mode, timeout,
                        gid=gid_of[members[0]], is_reference=head == reference_head,
                        states=states, malicious=malicious,
                    )
                    if outcome is None:
                        continue
                    if outcome.refusers:
                        outcome.fork_gid = next_gid
                        for node in outcome.refusers:
                            gid_of[node] = next_gid
                        next_gid += 1
                    outcomes.append(outcome)

                answers = dict(zip(node_ids, await asyncio.gather(
                    *(_get(client, f"{urls[n]}/answer", timeout, round_index=round_index) for n in node_ids)
                )))
                if strict_inference:
                    missing = [n for n in node_ids if not (answers[n] or {}).get("received")]
                    if missing or not outcomes:
                        raise RuntimeError(f"Rodada incompleta: nós sem resposta registrada: {missing}; grupos: {len(outcomes)}")
                if oracle_round(round_index, cfg):
                    await _judge(client, urls, await read_states(client), answers, outcomes, round_index, task["id"], expected, cfg, timeout,
                                 require_applied=strict_inference)

                states = await read_states(client)
                after = {n: s["consensus"].get(n, cfg.initial) for n, s in states.items()}
                final_groups = _groups_by_head(states)
                reference_members = max(final_groups.values(), key=lambda m: (honest_count(m), len(m)))
                chains = {gid_of[m[0]]: (states[m[0]]["chain_length"], h) for h, m in final_groups.items()}
                responses = [
                    NodeResponse(
                        node_id=n, task_id=task["id"],
                        answer=normalize((answers.get(n) or {}).get("answer")),
                        latency_ms=int((answers.get(n) or {}).get("latency_ms", 0)),
                        profile=profiles[n],
                    )
                    for n in node_ids
                ]
                log_round(
                    logger, round_index=round_index, task_id=task["id"], expected=expected,
                    responses=responses, profiles=profiles, reps_before=before, reps_after=after,
                    reference_members=reference_members, outcomes=outcomes, chains=chains,
                    mechanism=cfg.mechanism, initial=cfg.initial, is_test=this_is_test,
                    consensus_mode=cfg.consensus_mode, consensus_center=cfg.consensus_center,
                    audited=oracle_round(round_index, cfg),
                    calibration=cfg.signal != "consensus" and round_index < cfg.defense.calibration_rounds,
                )
                _print_dynamic_round(round_index, outcomes, this_is_test)

            ledgers = await asyncio.gather(*(_get(client, f"{urls[n]}/ledger", timeout) for n in node_ids))
    except BaseException:
        logger.close()
        raise

    ledger_dir = os.path.join(logger.output_dir, "ledgers")
    os.makedirs(ledger_dir, exist_ok=True)
    for node_id, data in zip(node_ids, ledgers):
        if data:
            with open(os.path.join(ledger_dir, f"{node_id}.json"), "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=1)

    tracker = ReputationTracker(node_ids, alpha=cfg.alpha, initial=cfg.initial, mechanism=cfg.mechanism, alpha_down=cfg.alpha_down)
    run_config = {
        **{k: v for k, v in config.items() if k != "nodes"},
        "n_nodes": len(node_ids),
        "test_every": cfg.test_every,
        "test_rounds": planned_tests,
        "orchestration": "dynamic",
        "signal": cfg.signal,
        "defense": cfg.defense.to_dict(),
        "defense_preset": config.get("defense", "all"),
        "ledgers_valid": all(bool(d and d.get("valid")) for d in ledgers),
    }
    extra = dynamic_summary(
        logger.leadership_rows, profiles,
        calibration_rounds=cfg.defense.calibration_rounds,
        heads={n: s["head"] for n, s in states.items()},
        graph_info={"graph_max_degree": max_degree(graph), "graph_diameter": diameter(graph)},
    )
    summary = logger.flush(
        run_config, tracker, profiles, seed=config.get("seed"), extra=extra,
        final_reputations={n: s["consensus"].get(n, cfg.initial) for n, s in states.items()},
    )
    _print_summary(summary, output_dir)
    return summary


async def _lead_group(
    client: httpx.AsyncClient,
    urls: dict[str, str],
    members: list[str],
    head: str,
    round_index: int,
    task: dict,
    mode: str,
    timeout: float,
    *,
    gid: int,
    is_reference: bool,
    states: dict[str, dict],
    malicious: set[str],
) -> Optional[GroupRound]:
    """Uma rodada numa cópia da cadeia, conduzida pelo líder que ela elege."""
    elected = await _get(client, f"{urls[members[0]]}/leader", timeout)
    if not elected or not elected.get("leader"):
        return None
    leader = elected["leader"]
    payload = {"round_index": round_index, "task_id": task["id"], "question": task["question"], "head": head}
    if mode == "simulation":
        payload["expected"] = task["answer"]
    result = await _post(client, f"{urls[leader]}/lead", payload, timeout)
    if not result:
        return None

    power = states[leader]["power"]
    mass = sum(power.get(m, 0.0) for m in members)
    malicious_mass = sum(power.get(m, 0.0) for m in members if m in malicious) / mass if mass > 0 else 0.0
    record = RoundRecord.from_json(result["record"])
    d = result["decision"]
    decision = Decision(
        accepted=d["accepted"], confirmed_mass=d["confirmed_mass"], total_mass=d["total_mass"],
        objective_reason=d["objective_reason"], censored_complaints=d["censored_complaints"],
        penalties=[tuple(p) for p in d["penalties"]], refuse_penalties=[tuple(p) for p in d["refuse_penalties"]],
        reason=d["reason"],
    )
    refusers = list(result["refusers"])
    return GroupRound(
        gid=gid,
        is_reference=is_reference,
        members=list(result["members"]),
        leader=leader,
        auditor=result["auditor"],
        bootstrap=bool(result["bootstrap"]),
        attack=result["attack"],
        record=record,
        decision=decision,
        votes={n: Vote(n, bool(v["ok"]), v.get("reason", "")) for n, v in result["votes"].items()},
        hops=int(result["hops"]),
        refusers=refusers,
        fork_gid=None,
        malicious_power_mass=malicious_mass,
        margin=float(result["margin"]),
        is_tie=bool(result["is_tie"]),
        committed={m: (record.consensus if decision.accepted and m not in refusers else None) for m in result["members"]},
    )


async def _judge(
    client: httpx.AsyncClient,
    urls: dict[str, str],
    states: dict[str, dict],
    answers: dict[str, Optional[dict]],
    outcomes: list[GroupRound],
    round_index: int,
    task_id: str,
    expected,
    cfg: ProtocolConfig,
    timeout: float,
    *,
    require_applied: bool = False,
) -> None:
    """Entrega o gabarito a cada cópia da cadeia (votado ou direto)."""
    for head, members in _groups_by_head(states).items():
        graded = {m: normalize((answers.get(m) or {}).get("answer")) for m in members}
        record = oracle_record(prev_hash=head, round_index=round_index, task_id=task_id, expected=expected, graded=graded)
        votes = None
        if not cfg.defense.oracle_bypasses_quorum:
            got = await asyncio.gather(*(_post(client, f"{urls[m]}/oracle_vote", {}, timeout) for m in members))
            votes = {m: bool(v and v.get("ok")) for m, v in zip(members, got)}
        statuses = await asyncio.gather(
            *(_post(client, f"{urls[m]}/oracle", {"record": record.to_json(), "votes": votes}, timeout) for m in members)
        )
        if require_applied and any(not item or item.get("status") != "applied" for item in statuses):
            raise RuntimeError(f"Conferência não aplicada em todos os nós: {statuses}")
        status = next((s["status"] for s in statuses if s), "")
        for outcome in outcomes:
            if outcome.leader in members:
                outcome.oracle = status
                outcome.oracle_rejecters = sum(1 for ok in (votes or {}).values() if not ok)


def _print_dynamic_round(round_index: int, outcomes: list[GroupRound], is_test: bool) -> None:
    for outcome in outcomes:
        status = "OK " if outcome.decision and outcome.decision.accepted else "ANUL"
        test_tag = " | TESTE" if is_test else ""
        print(
            f"[{status}] rodada {round_index + 1:>3} | grupo {outcome.gid} | líder {outcome.leader} | "
            f"auditor {outcome.auditor} | consenso={outcome.record.consensus if outcome.record else None} | "
            f"saltos={outcome.hops}{' | oráculo ' + outcome.oracle if outcome.oracle else ''}{test_tag}"
        )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _print_summary(summary: dict, output_dir: str) -> None:
    print(f"\n=== Resumo do experimento [{summary['experiment_id']}] ===")
    print(f"Rodadas: {summary['rounds']}")
    print(f"Rodadas de teste: {summary.get('test_rounds', [])}")
    print(f"Acurácia do consenso ponderado (todas as rodadas): {summary['consensus_accuracy_weighted']:.2%}")
    print(f"Acurácia do consenso por maioria (todas as rodadas): {summary['consensus_accuracy_majority']:.2%}")
    print(f"Acurácia do consenso ponderado (só testes): {summary.get('consensus_accuracy_weighted_on_tests', 0):.2%}")
    print(f"Acurácia do consenso por maioria (só testes): {summary.get('consensus_accuracy_majority_on_tests', 0):.2%}")
    print(f"Tempo médio de resposta: {summary['mean_latency_ms']:.0f} ms")
    print("\nReputação final média por perfil:")
    for profile, value in sorted(summary["final_reputation_by_profile"].items()):
        print(f"  {profile:<10} {value:.3f}")
    print(f"\nMétricas salvas em: {output_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Orquestrador da rede de reputação.")
    parser.add_argument("--config", default=_DEFAULT_CONFIG, help="Arquivo YAML de configuração.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = load_config(args.config)
    if config.get("orchestration", "dynamic") != "dynamic":
        raise ValueError("Somente a orquestração dinâmica é suportada.")
    asyncio.run(run_dynamic_experiment(config))


if __name__ == "__main__":
    main()
