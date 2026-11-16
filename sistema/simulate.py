"""Simulação local do sistema em processo único.

Reproduz o fluxo completo do Documento de Visão (distribuição de tarefas,
coleta de respostas, consenso, atualização de reputação e registro de métricas)
sem Docker e, por padrão, sem executar o modelo. A inferência ao vivo opcional
executa uma geração por nó e rodada. Serve para validar rapidamente o mecanismo
de reputação e o consenso — a "versão mínima funcionando" combinada na reunião.

O protocolo dinâmico é compartilhado pelas simulações e pelos serviços em
contêineres. A comparação de execução deve considerar as diferenças de rede.

Uso::

    python -m sistema.simulate --nodes 4 --malicious 0.25 --rounds 50

    # Orquestrador eleito a cada rodada, grafo 4-regular, todas as defesas
    python -m sistema.simulate --orchestration dynamic --topology kregular \\
        --nodes 20 --malicious 0.65 --collusion-value 999 --rounds 50 \\
        --signal hybrid --defense all --leader-attack forge

Observação: em simulação, o comportamento dos perfis é fabricado a partir do
gabarito.  No processo real (containers), os nós não recebem o gabarito.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import random
import time

from .core import behavior, dataset
from .core.answer import normalize
from .core.defenses import DefenseConfig, preset, preset_names
from .core.metrics import MetricsLogger, dynamic_summary
from .core.network import SimulatedNetwork, log_round
from .core.protocol import (
    AUDIT_MODES,
    CONSENSUS_CENTERS,
    CONSENSUS_MODES,
    MALICIOUS_STRATEGIES,
    SIGNALS,
    VALIDATION_SCORES,
    ProtocolConfig,
    malicious_acts_honest,
    oracle_round,
    plan_audits,
)
from .core.reputation import MECHANISMS, ReputationTracker
from .core.schedule import DEFAULT_TEST_EVERY, is_test_round, test_rounds_1based
from .core.schemas import NodeResponse
from .core.topology import KINDS, build_graph, diameter, max_degree

ORCHESTRATIONS = ("dynamic",)

_DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "results", "simulacao")


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------

def _corrupt(base, rng: random.Random, noise_mode: str, noise_distance: float):
    """Ruído multiplicativo de hoje, ou ruído a uma distância relativa fixa."""
    if noise_mode == "relative":
        return behavior.corrupt_relative(base, rng, noise_distance)
    return behavior.corrupt_with_noise(base, rng)


def _inference_seed(seed: int, round_index: int, node_id: str) -> int:
    """Semente estável por execução, rodada e nó, independente da ordem de chamadas."""
    encoded = f"{seed}:{round_index}:{node_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big") & ((1 << 63) - 1)


def _write_live_manifest(path: str, manifest: dict) -> None:
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def build_profiles(
    num_nodes: int,
    malicious_frac: float,
    unstable_frac: float = 0.0,
) -> dict[str, str]:
    """Distribui perfis entre os nós a partir das frações informadas."""
    num_malicious = round(malicious_frac * num_nodes)
    num_unstable = round(unstable_frac * num_nodes)
    if num_malicious + num_unstable > num_nodes:
        raise ValueError("Soma de nós maliciosos e instáveis excede o total de nós.")

    profiles: dict[str, str] = {}
    for index in range(num_nodes):
        node_id = f"node-{index}"
        if index < num_malicious:
            profiles[node_id] = behavior.MALICIOUS
        elif index < num_malicious + num_unstable:
            profiles[node_id] = behavior.UNSTABLE
        else:
            profiles[node_id] = behavior.HONEST
    return profiles


def run_simulation(args: argparse.Namespace, *, round_observer=None) -> dict:
    """Executa a simulação e retorna o resumo gerado pelo MetricsLogger.

    ``round_observer``, quando informado, recebe uma fotografia das respostas,
    reputações e grupos de referência antes e depois de cada rodada concluída.
    """
    live_model = getattr(args, "live_model_backend", None)
    if live_model is not None:
        if getattr(args, "answer_bank", None) is not None or getattr(args, "model_answers", None) is not None:
            raise ValueError("Inferência ao vivo não aceita banco de respostas ou respostas prontas.")
        if float(args.unstable) != 0:
            raise ValueError("Inferência ao vivo ainda não suporta nós instáveis.")
        if not 0 < float(getattr(args, "model_temperature", 0.7)) or not 0 < float(getattr(args, "model_top_p", 0.95)) <= 1:
            raise ValueError("Temperatura deve ser positiva e top_p deve estar em (0, 1].")
    orchestration = getattr(args, "orchestration", "dynamic")
    if orchestration != "dynamic":
        raise ValueError("Este projeto aceita apenas orquestração dynamic.")
    rng = random.Random(args.seed)
    noise_rng = random.Random(f"{args.seed}:noise")
    noise_mode = getattr(args, "noise_mode", "multiplicative")
    noise_distance = float(getattr(args, "noise_distance", 0.2))
    unstable_mode = getattr(args, "unstable_mode", "profile")
    if unstable_mode == "attribute":
        profiles = build_profiles(args.nodes, args.malicious, 0.0)
    else:
        profiles = build_profiles(args.nodes, args.malicious, args.unstable)
    node_ids = list(profiles)
    unstable_rng = random.Random(f"{args.seed}:unstable")
    if unstable_mode == "attribute":
        marked = round(float(args.unstable) * len(node_ids))
        unstable_nodes = set(unstable_rng.sample(node_ids, marked)) if marked else set()
    else:
        unstable_nodes = set()

    tasks = getattr(args, "tasks", None) or dataset.load_sample()
    if not tasks:
        raise RuntimeError("Amostra de dataset vazia.")

    bcfg = behavior.BehaviorConfig(
        honest_p_correct=args.honest_accuracy,
        malicious_collusion_value=args.collusion_value,
        unstable_p_drop=getattr(args, "unstable_p_drop", 0.3),
        unstable_p_correct=getattr(args, "unstable_p_correct", 0.5),
    )

    # Mecanismo e parâmetros de reputação.
    mechanism = getattr(args, "mechanism", "ema")
    alpha_down = getattr(args, "alpha_down", None)
    initial = getattr(args, "initial_reputation", 0.5)
    alpha_up = float(getattr(args, "alpha_up", 0.1))
    tracker = ReputationTracker(
        node_ids,
        alpha=args.alpha,
        initial=initial,
        mechanism=mechanism,
        alpha_down=alpha_down,
        alpha_up=alpha_up,
    )

    # Experiment ID e diretório de saída.
    experiment_id = getattr(args, "experiment_id", None)
    overwrite = getattr(args, "overwrite", True)
    output_dir = args.output
    if experiment_id:
        output_dir = os.path.join(output_dir, experiment_id)
    inference_path = os.path.join(output_dir, "inferencias.jsonl")
    live_manifest_path = os.path.join(output_dir, "inferencia_manifesto.json")
    if live_model is not None and (os.path.exists(inference_path) or os.path.exists(live_manifest_path)):
        raise FileExistsError(f"Registro de inferências já existe em {output_dir!r}.")

    test_every = int(getattr(args, "test_every", DEFAULT_TEST_EVERY))
    planned_tests = test_rounds_1based(args.rounds, test_every)
    logger = MetricsLogger(
        output_dir,
        experiment_id=experiment_id,
        overwrite=overwrite,
        row_sync=bool(getattr(args, "row_sync", True)),
        git_sha=getattr(args, "git_sha", None),
    )
    inference_log = open(inference_path, "x", encoding="utf-8") if live_model is not None else None
    live_manifest = None
    if live_model is not None:
        live_manifest = {
            "status": "em_andamento", "modelo": getattr(live_model, "model_name", "desconhecido"),
            "tarefas_origem": getattr(args, "task_bank", None), "tarefas_sha256": getattr(args, "task_bank_sha256", None),
            "nos": args.nodes, "rodadas": args.rounds, "fracao_maliciosos": args.malicious,
            "semente": args.seed, "temperatura": float(getattr(args, "model_temperature", 0.7)),
            "top_p": float(getattr(args, "model_top_p", 0.95)), "max_new_tokens": getattr(live_model, "max_new_tokens", None),
            "audit_mode": getattr(args, "audit_mode", "fixed"), "audit_p": float(getattr(args, "audit_p", 0.1)),
            "validation_score": getattr(args, "validation_score", "graded"),
            "malicious_strategy": getattr(args, "malicious_strategy", "always"),
            "malicious_answer": getattr(args, "malicious_answer", "fixed"),
            "noise_mode": noise_mode, "noise_distance": noise_distance,
            "conluio": args.collusion_value is not None, "chamadas_previstas": args.nodes * args.rounds,
            "registro": "inferencias.jsonl", "retomada_automatica": False,
        }
        _write_live_manifest(live_manifest_path, live_manifest)

    signal = getattr(args, "signal", "truth")
    defense = defense_from_args(args)
    audit_mode = getattr(args, "audit_mode", "fixed")
    override = getattr(args, "audited_rounds_override", None)
    if override is not None:
        audited_rounds = frozenset(override)
    elif audit_mode == "random":
        audited_rounds = plan_audits(args.seed, args.rounds, test_every, float(getattr(args, "audit_p", 0.1)))
    else:
        audited_rounds = frozenset()
    protocol = ProtocolConfig(
        signal=signal,
        alpha=args.alpha,
        mechanism=mechanism,
        alpha_down=alpha_down,
        initial=initial,
        test_every=test_every,
        defense=defense,
        consensus_mode=getattr(args, "consensus_mode", "exact"),
        malicious_strategy=getattr(args, "malicious_strategy", "always"),
        honest_rounds=int(getattr(args, "honest_rounds", 5)),
        audit_mode=audit_mode,
        audited_rounds=audited_rounds,
        alpha_up=alpha_up,
        validation_score=getattr(args, "validation_score", "graded"),
        consensus_center=getattr(args, "consensus_center", "medoid"),
    )
    graph = build_graph(node_ids, getattr(args, "topology", "star"), getattr(args, "degree", 4), args.seed)
    attacks = behavior.AttackConfig(
        leader_attack=getattr(args, "leader_attack", "none"),
        auditor_attack=getattr(args, "auditor_attack", "none"),
    )
    network = SimulatedNetwork(node_ids, profiles, graph, protocol, attacks)

    # Laço de rodadas.  Se interrompido, os CSVs incrementais (per_node.csv,
    # rounds.csv, reputation_history.csv) já contêm todas as rodadas concluídas.
    # A rodada de teste é fixa: uma a cada `test_every` rodadas (10, 20, 30, …).
    try:
        for round_index in range(args.rounds):
            task = tasks[round_index % len(tasks)]
            expected = normalize(task["answer"])
            this_is_test = is_test_round(round_index, test_every)

            concurrent_answers = None
            if live_model is not None and hasattr(live_model, "batch_sample"):
                jobs = [(task["question"], _inference_seed(args.seed, round_index, nid)) for nid in node_ids]
                concurrent_answers = dict(zip(node_ids, live_model.batch_sample(
                    jobs, temperature=float(getattr(args, "model_temperature", 0.7)),
                    top_p=float(getattr(args, "model_top_p", 0.95)))))

            model_answers = getattr(args, "model_answers", None)
            answer_bank = getattr(args, "answer_bank", None)
            use_noise = getattr(args, "malicious_answer", "fixed") == "noise"
            laying_low = malicious_acts_honest(round_index, protocol)
            shared_noise = None
            shared_noise_base_node = None
            if live_model is None and use_noise and bcfg.malicious_collusion_value is not None and not laying_low:
                base = behavior.honest_base(noise_rng, expected, bcfg, answer_bank, task["id"])
                shared_noise = _corrupt(base, noise_rng, noise_mode, noise_distance)
            responses: list[NodeResponse] = []
            for node_id in node_ids:
                if live_model is not None:
                    infer_seed = _inference_seed(args.seed, round_index, node_id)
                    if concurrent_answers is not None:
                        base, generated_text, latency = concurrent_answers[node_id]
                    else:
                        started = time.perf_counter()
                        base, generated_text = live_model.sample(
                            task["question"], temperature=float(getattr(args, "model_temperature", 0.7)),
                            top_p=float(getattr(args, "model_top_p", 0.95)), seed=infer_seed,
                        )
                        latency = int((time.perf_counter() - started) * 1000)
                    answer = base
                    source = "modelo"
                    if profiles[node_id] == behavior.MALICIOUS and not laying_low:
                        if use_noise:
                            if bcfg.malicious_collusion_value is not None:
                                if shared_noise is None:
                                    shared_noise = _corrupt(base, noise_rng, noise_mode, noise_distance)
                                    shared_noise_base_node = node_id
                                answer = shared_noise
                                source = "ruido_compartilhado"
                            else:
                                answer = _corrupt(base, noise_rng, noise_mode, noise_distance)
                                source = "ruido_individual"
                        else:
                            answer, _ = behavior.simulate_answer(behavior.MALICIOUS, expected, bcfg, rng)
                            source = "ataque_fixo"
                    inference_log.write(json.dumps({
                        "rodada": round_index + 1, "no": node_id, "perfil": profiles[node_id],
                        "tarefa": task["id"], "semente": infer_seed, "latencia_ms": latency,
                        "texto_gerado": generated_text, "resposta_modelo": normalize(base), "resposta_enviada": normalize(answer),
                        "origem_resposta": source, "no_base_ruido_compartilhado": shared_noise_base_node if source == "ruido_compartilhado" else None,
                    }, ensure_ascii=False) + "\n")
                    inference_log.flush()
                elif node_id in unstable_nodes and unstable_rng.random() < bcfg.unstable_p_drop:
                    answer, latency = None, 0
                elif use_noise and profiles[node_id] == behavior.MALICIOUS and not laying_low:
                    # Consome o gerador principal como o perfil fixo faria, para
                    # os honestos seguintes verem a mesma sequência.
                    _discarded, latency = behavior.simulate_answer(profiles[node_id], expected, bcfg, rng)
                    if shared_noise is not None:
                        answer = shared_noise
                    else:
                        base = behavior.honest_base(noise_rng, expected, bcfg, answer_bank, task["id"])
                        answer = _corrupt(base, noise_rng, noise_mode, noise_distance)
                elif answer_bank is not None and (
                    profiles[node_id] == behavior.HONEST or (laying_low and profiles[node_id] == behavior.MALICIOUS)
                ):
                    # Cada nó honesto sorteia uma das respostas que o modelo gerou
                    # para esta pergunta (banco gerado com amostragem).
                    answer, latency = rng.choice(answer_bank[task["id"]]), 0
                elif model_answers is not None and (
                    profiles[node_id] == behavior.HONEST or (laying_low and profiles[node_id] == behavior.MALICIOUS)
                ):
                    answer, latency = model_answers.get(task["id"]), 0
                else:
                    answering_as = (
                        behavior.HONEST
                        if laying_low and profiles[node_id] == behavior.MALICIOUS
                        else profiles[node_id]
                    )
                    answer, latency = behavior.simulate_answer(answering_as, expected, bcfg, rng)
                if node_id in unstable_nodes:
                    latency = unstable_rng.randint(*bcfg.unstable_latency_ms)
                responses.append(
                    NodeResponse(
                        node_id=node_id,
                        task_id=task["id"],
                        answer=normalize(answer),
                        latency_ms=latency,
                        profile=profiles[node_id],
                    )
                )

            if round_observer is not None:
                before = {n: network.group_of(n).state.consensus.get(n) for n in profiles}
                power_before = {n: network.group_of(n).state.power.get(n) for n in profiles}
                ref_before = list(network.reference_group().members)
            _dynamic_round(network, logger, round_index, task["id"], expected, responses, profiles,
                           mechanism, initial, this_is_test)
            if round_observer is not None:
                last = logger.round_rows[-1]
                if int(last["round_index"]) != round_index:
                    raise RuntimeError("a última linha de rounds.csv não é a rodada que acabou de terminar")
                round_observer(
                    round_index=round_index, is_test=this_is_test, expected=expected,
                    responses=responses, profiles=profiles, before=before,
                    after={n: network.group_of(n).state.consensus.get(n) for n in profiles},
                    power_before=power_before,
                    power_after={n: network.group_of(n).state.power.get(n) for n in profiles},
                    ref_before=ref_before, ref_after=list(network.reference_group().members),
                    protocol_w_ok=int(last["consensus_correct"]),
                    protocol_m_ok=int(last["majority_correct"]),
                )
    except BaseException as exc:
        logger.close()
        if inference_log is not None:
            inference_log.close()
            live_manifest["status"] = "falhou"
            live_manifest["erro"] = f"{type(exc).__name__}: {exc}"
            _write_live_manifest(live_manifest_path, live_manifest)
        raise

    if inference_log is not None:
        inference_log.close()

    # Configuração que vai para o manifest / summary.
    run_config = {
        "source": "simulate",
        "nodes": args.nodes,
        "malicious_frac": args.malicious,
        "unstable_frac": args.unstable,
        "rounds": args.rounds,
        "alpha": args.alpha,
        "seed": args.seed,
        "honest_accuracy": args.honest_accuracy,
        "collusion_value": args.collusion_value,
        "mechanism": mechanism,
        "alpha_down": alpha_down,
        "initial_reputation": initial,
        "profiles": profiles,
        "test_every": test_every,
        "test_rounds": planned_tests,
    }
    if live_model is not None:
        run_config["inferencia"] = {
            "tipo": "modelo_ao_vivo", "modelo": getattr(live_model, "model_name", "desconhecido"),
            "temperatura": float(getattr(args, "model_temperature", 0.7)),
            "top_p": float(getattr(args, "model_top_p", 0.95)),
            "max_new_tokens": getattr(live_model, "max_new_tokens", None),
            "registro": "inferencias.jsonl", "chamadas": args.nodes * args.rounds,
            "audit_mode": audit_mode, "audit_p": float(getattr(args, "audit_p", 0.1)),
            "validation_score": protocol.validation_score, "noise_mode": noise_mode,
            "noise_distance": noise_distance, "malicious_strategy": protocol.malicious_strategy,
            "concorrencia": getattr(live_model, "workers", 1),
            "quantizacao": getattr(live_model, "quantization", None),
            "revisao_modelo": getattr(live_model, "revision", None),
            "tarefas_origem": getattr(args, "task_bank", None),
            "tarefas_sha256": getattr(args, "task_bank_sha256", None),
        }
    extra = None
    final_reputations = None
    run_config.update({
        "orchestration": orchestration,
        "signal": signal,
        "defense": defense.to_dict(),
        "defense_preset": getattr(args, "defense", "none"),
    })
    if network is not None:
        run_config.update({
            "topology": getattr(args, "topology", "star"),
            "degree": getattr(args, "degree", 4),
            "leader_attack": network.attacks.leader_attack,
            "auditor_attack": network.attacks.auditor_attack,
        })
        extra = dynamic_summary(
            logger.leadership_rows,
            profiles,
            calibration_rounds=defense.calibration_rounds,
            heads=network.heads(),
            graph_info={"graph_max_degree": max_degree(network.graph), "graph_diameter": diameter(network.graph)},
        )
        final_reputations = {n: network.group_of(n).state.consensus.get(n) for n in node_ids}
    if unstable_mode == "attribute":
        extra = {
            **(extra or {}),
            "unstable_honest": sum(profiles[n] == behavior.HONEST for n in unstable_nodes),
            "unstable_malicious": sum(profiles[n] == behavior.MALICIOUS for n in unstable_nodes),
        }
    if audit_mode == "random":
        extra = {
            **(extra or {}),
            "n_audited": len(audited_rounds),
            "audited_rounds": sorted(audited_rounds),
        }
    summary = logger.flush(
        run_config, tracker, profiles, seed=args.seed, extra=extra, final_reputations=final_reputations,
    )
    if live_manifest is not None:
        live_manifest["status"] = "concluido"
        _write_live_manifest(live_manifest_path, live_manifest)
    if not getattr(args, "quiet", False):
        _print_summary(summary, profiles, logger.output_dir)
    return summary


def defense_from_args(args: argparse.Namespace) -> DefenseConfig:
    """Preset de defesa com os ajustes individuais da linha de comando."""
    config = preset(getattr(args, "defense", "none") or "none")
    overrides = {}
    if getattr(args, "calibration_rounds", None) is not None:
        overrides["calibration_rounds"] = args.calibration_rounds
    if getattr(args, "consensus_alpha", None) is not None:
        overrides["consensus_alpha"] = args.consensus_alpha
    if getattr(args, "oracle_alpha", None) is not None:
        overrides["oracle_alpha"] = args.oracle_alpha
    for flag in ("split_alpha", "oracle_bypasses_quorum", "split_scores", "refuse_forged", "leaderless_calibration"):
        if getattr(args, flag, False):
            overrides[flag] = True
    return dataclasses.replace(config, **overrides) if overrides else config


def _dynamic_round(
    network: SimulatedNetwork,
    logger: MetricsLogger,
    round_index: int,
    task_id: str,
    expected,
    responses: list[NodeResponse],
    profiles: dict[str, str],
    mechanism: str,
    initial: float,
    is_test: bool,
) -> None:
    answers = {r.node_id: r.answer for r in responses}
    before = {n: network.group_of(n).state.consensus.get(n) for n in answers}
    outcomes = network.run_round(round_index, task_id, expected, answers)
    after = {n: network.group_of(n).state.consensus.get(n) for n in answers}
    log_round(
        logger,
        round_index=round_index,
        task_id=task_id,
        expected=expected,
        responses=responses,
        profiles=profiles,
        reps_before=before,
        reps_after=after,
        reference_members=network.reference_group().members,
        outcomes=outcomes,
        chains={g.gid: (len(g.ledger), g.ledger.head) for g in network.groups},
        mechanism=mechanism,
        initial=initial,
        is_test=is_test,
        consensus_mode=network.config.consensus_mode,
        consensus_center=network.config.consensus_center,
        audited=oracle_round(round_index, network.config),
        calibration=(
            network.config.signal != "consensus"
            and round_index < network.config.defense.calibration_rounds
        ),
    )


# ---------------------------------------------------------------------------
# Helpers de saída
# ---------------------------------------------------------------------------

def _print_summary(summary: dict, profiles: dict[str, str], output_dir: str) -> None:
    print(f"\n=== Resumo da simulação [{summary['experiment_id']}] ===")
    print(f"Rodadas: {summary['rounds']}")
    print(f"Rodadas de teste: {summary.get('test_rounds', [])}")
    print(f"Acurácia do consenso ponderado (todas as rodadas): {summary['consensus_accuracy_weighted']:.2%}")
    print(f"Acurácia do consenso por maioria (todas as rodadas): {summary['consensus_accuracy_majority']:.2%}")
    print(f"Acurácia do consenso ponderado (só testes): {summary.get('consensus_accuracy_weighted_on_tests', 0):.2%}")
    print(f"Acurácia do consenso por maioria (só testes): {summary.get('consensus_accuracy_majority_on_tests', 0):.2%}")
    print(f"Tempo médio de resposta: {summary['mean_latency_ms']:.0f} ms")
    print(f"Rodada de recuperação do consenso: {summary.get('recovery_round')}")
    dyn = summary.get("dynamic")
    if dyn:
        print("\nOrquestrador eleito (grupo de referência):")
        print(f"  Líderes por perfil: {dyn['leader_rounds_by_profile']}")
        print(f"  Maior sequência do mesmo líder: {dyn['max_consecutive_same_leader']}")
        print(f"  Líder do conluio depois da calibração: {dyn['leader_malicious_rounds_after_calibration']}")
        print(f"  Rodadas aceitas / anuladas: {dyn['accepted_rounds']} / {dyn['voided_rounds']}")
        print(f"  Forjas aceitas: {dyn['forged_accepted']} | censuras aceitas: {dyn['censored_accepted']}")
        print(f"  Divisões da cadeia: {dyn['chain_split_rounds']} | cópias no fim: {dyn['n_chains_final']}")
        print(f"  Correções bloqueadas: {dyn['oracle_blocked_rounds']} de {dyn['oracle_rounds']}")
        print(f"  Massa de poder do conluio no fim: {dyn['malicious_power_mass_final']:.3f}")
        print(f"  Saltos médios / máximo: {dyn['mean_hops']} / {dyn['max_hops']} (grau {dyn['graph_max_degree']})")
    print("\nReputação final média por perfil:")
    for profile, value in sorted(summary["final_reputation_by_profile"].items()):
        print(f"  {profile:<10} {value:.3f}")
    print(f"\nMétricas salvas em: {output_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulação local da rede de reputação.")
    parser.add_argument("--nodes", type=int, default=4, help="Número de nós.")
    parser.add_argument("--inference-model", default=None, help="Executa uma inferência amostrada por nó e rodada usando este modelo Hugging Face.")
    parser.add_argument("--task-bank", default="sistema/dados/banco_smol.json", help="Arquivo JSON de tarefas; somente perguntas e gabaritos serão lidos.")
    parser.add_argument("--model-temperature", type=float, default=0.7)
    parser.add_argument("--model-top-p", type=float, default=0.95)
    parser.add_argument("--model-max-new-tokens", type=int, default=256)
    parser.add_argument("--model-quantization", choices=("nf4",), default=None)
    parser.add_argument("--inference-workers", type=int, choices=(1, 2), default=1)
    parser.add_argument("--inference-cache", default=None, help="SQLite exclusivo da execução lógica, para retomada sem gerar respostas já concluídas.")
    parser.add_argument("--inference-run-id", default=None, help="Identificador estável da execução lógica, inclusive nas tentativas de retomada.")
    parser.add_argument("--malicious", type=float, default=0.25, help="Fração de nós maliciosos.")
    parser.add_argument("--unstable", type=float, default=0.0, help="Fração de nós instáveis.")
    parser.add_argument(
        "--unstable-mode", choices=("profile", "attribute"), default="profile", dest="unstable_mode",
        help="profile = perfil próprio, como hoje; attribute = marca sobre o perfil.",
    )
    parser.add_argument("--rounds", type=int, default=10, help="Número de rodadas.")
    parser.add_argument(
        "--test-every", type=int, default=DEFAULT_TEST_EVERY, dest="test_every",
        help="Uma rodada de teste a cada N rodadas (padrão: 10 → rodadas 10, 20, 30, …).",
    )
    parser.add_argument("--alpha", type=float, default=0.3, help="Taxa de aprendizado (EMA).")
    parser.add_argument("--seed", type=int, default=42, help="Identificador da repetição (semente do gerador aleatório).")
    parser.add_argument(
        "--honest-accuracy", type=float, default=0.9,
        help="Probabilidade de acerto de um nó honesto.",
    )
    parser.add_argument(
        "--collusion-value", type=int, default=None,
        help="Valor de conluio (todos os maliciosos respondem este valor).",
    )
    parser.add_argument(
        "--malicious-answer", choices=("fixed", "noise"), default="fixed", dest="malicious_answer",
        help="fixed = 999 ou ±5, como hoje; noise = resposta honesta corrompida.",
    )
    parser.add_argument(
        "--noise-mode", choices=("multiplicative", "relative"), default="multiplicative", dest="noise_mode",
        help="multiplicative = 10^k, como hoje; relative = distância relativa fixa.",
    )
    parser.add_argument(
        "--noise-distance", type=float, default=0.2, dest="noise_distance",
        help="Distância relativa do ruído sutil, em (0, 1). Padrão 0,2.",
    )
    parser.add_argument(
        "--validation-score", choices=VALIDATION_SCORES, default="graded", dest="validation_score",
        help="graded = 1 − distância no gabarito; exact = 1 só se a resposta for igual.",
    )
    parser.add_argument(
        "--consensus-center", choices=CONSENSUS_CENTERS, default="medoid", dest="consensus_center",
        help="Centro no modo de distância: medoid, median ou mean. Padrão medoid.",
    )
    parser.add_argument(
        "--malicious-strategy", choices=MALICIOUS_STRATEGIES, default="always", dest="malicious_strategy",
        help="always = ataca sempre; on_off = imita no início; knows_schedule = conhece o calendário fixo.",
    )
    parser.add_argument(
        "--honest-rounds", type=int, default=5, dest="honest_rounds",
        help="Rodadas iniciais em que a estratégia on_off imita um honesto.",
    )
    parser.add_argument(
        "--unstable-p-drop", type=float, default=0.3, dest="unstable_p_drop",
        help="Probabilidade de o nó instável descartar a resposta.",
    )
    parser.add_argument(
        "--unstable-p-correct", type=float, default=0.5, dest="unstable_p_correct",
        help="Probabilidade de acerto de um nó instável quando responde.",
    )
    parser.add_argument(
        "--mechanism", choices=MECHANISMS, default="ema",
        help="Mecanismo de reputação.",
    )
    parser.add_argument(
        "--alpha-down", type=float, default=None, dest="alpha_down",
        help="Descida do ema_asymmetric (padrão alpha/2). No ema_slow_up, omissão vale 0,8.",
    )
    parser.add_argument(
        "--alpha-up", type=float, default=0.1, dest="alpha_up",
        help="Subida do ema_slow_up nas rodadas com gabarito.",
    )
    parser.add_argument(
        "--audit-mode", choices=AUDIT_MODES, default="fixed", dest="audit_mode",
        help="fixed = gabarito nas rodadas de teste; random = auditoria sorteada.",
    )
    parser.add_argument(
        "--audit-p", type=float, default=0.1, dest="audit_p",
        help="Probabilidade de auditar uma rodada que não é de teste.",
    )
    parser.add_argument(
        "--initial-reputation", type=float, default=0.5, dest="initial_reputation",
        help="Reputação inicial de todos os nós.",
    )
    parser.add_argument("--output", default=_DEFAULT_OUTPUT, help="Diretório base de saída.")
    parser.add_argument(
        "--experiment-id", default=None, dest="experiment_id",
        help="Identificador único do experimento (auto-gerado se omitido).",
    )
    parser.add_argument(
        "--overwrite", action="store_true", default=False,
        help="Sobrescrever diretório de saída se já existir.",
    )
    parser.add_argument(
        "--no-row-sync", action="store_false", dest="row_sync", default=True,
        help="Não sincroniza cada linha de CSV em disco (mais rápido em lote).",
    )
    parser.add_argument("--quiet", action="store_true", help="Não imprime o resumo.")
    # Orquestrador eleito.
    parser.add_argument(
        "--orchestration", choices=ORCHESTRATIONS, default="dynamic",
        help="Orquestração dinâmica, com líder eleito a cada rodada.",
    )
    parser.add_argument(
        "--signal", choices=SIGNALS, default="truth",
        help="Sinal da reputação: truth (gabarito), consensus ou hybrid.",
    )
    parser.add_argument(
        "--consensus-mode", choices=CONSENSUS_MODES, default="exact", dest="consensus_mode",
        help="exact = igualdade de hoje; distance = medoide e sinal contínuo.",
    )
    parser.add_argument("--topology", choices=KINDS, default="star", help="Grafo entre os nós.")
    parser.add_argument("--degree", type=int, default=4, help="Vizinhos por nó no grafo kregular.")
    parser.add_argument(
        "--leader-attack", choices=behavior.LEADER_ATTACKS, default="none", dest="leader_attack",
        help="Ataque do líder malicioso.",
    )
    parser.add_argument(
        "--auditor-attack", choices=behavior.AUDITOR_ATTACKS, default="none", dest="auditor_attack",
        help="Ataque do auditor malicioso.",
    )
    parser.add_argument(
        "--defense", choices=preset_names(), default="none",
        help="Preset das medidas contra conluio (ablação).",
    )
    parser.add_argument("--calibration-rounds", type=int, default=None, dest="calibration_rounds")
    parser.add_argument("--consensus-alpha", type=float, default=None, dest="consensus_alpha")
    parser.add_argument("--oracle-alpha", type=float, default=None, dest="oracle_alpha")
    parser.add_argument("--split-alpha", action="store_true", dest="split_alpha")
    parser.add_argument("--oracle-bypasses-quorum", action="store_true", dest="oracle_bypasses_quorum")
    parser.add_argument("--split-scores", action="store_true", dest="split_scores")
    parser.add_argument("--refuse-forged", action="store_true", dest="refuse_forged")
    parser.add_argument(
        "--leaderless-calibration", action="store_true", dest="leaderless_calibration",
        help="Rodadas de calibração sem eleição, proposta nem voto; gabarito aplicado sem quórum.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    pool = None
    if args.inference_model:
        from .node.inference import ModelBackend

        with open(args.task_bank, "rb") as file:
            raw_tasks = file.read()
        document = json.loads(raw_tasks)
        tasks = document.get("tarefas", [])
        if not tasks or any(not all(field in task for field in ("id", "question", "answer")) for task in tasks):
            raise ValueError("Arquivo deve conter tarefas com id, question e answer.")
        args.tasks = [{key: task[key] for key in ("id", "question", "answer")} for task in tasks]
        args.task_bank_sha256 = hashlib.sha256(raw_tasks).hexdigest()
        if args.inference_workers == 2:
            if args.model_quantization != "nf4" or not args.inference_cache or not args.inference_run_id:
                raise ValueError("Duas instâncias exigem --model-quantization nf4, --inference-cache e --inference-run-id.")
            from huggingface_hub import snapshot_download
            from importlib.metadata import version
            from pathlib import Path
            from .node.inference_pool import InferencePool

            snapshot = snapshot_download(args.inference_model, local_files_only=True)
            revision = Path(snapshot).name
            source_paths = sorted(Path(__file__).parent.joinpath("core").glob("*.py")) + [
                Path(__file__), Path(__file__).parent / "node" / "inference.py",
                Path(__file__).parent / "node" / "inference_pool.py"]
            code_hash = hashlib.sha256()
            for source in source_paths:
                code_hash.update(str(source.relative_to(Path(__file__).parent)).encode("utf-8"))
                code_hash.update(source.read_bytes())
            ignored = {"output", "experiment_id", "overwrite", "quiet", "row_sync", "inference_cache"}
            config = {k: v for k, v in vars(args).items() if k not in ignored}
            config.update({"model_revision": revision, "source_sha256": code_hash.hexdigest(),
                "torch_version": version("torch"), "transformers_version": version("transformers"),
                "bitsandbytes_version": version("bitsandbytes")})
            pool = InferencePool(args.inference_model, snapshot, revision, args.model_max_new_tokens,
                                 args.inference_workers, args.inference_cache, config)
            args.live_model_backend = pool
        else:
            if args.inference_cache or args.inference_run_id:
                raise ValueError("Cache e identificador de execução exigem duas instâncias NF4.")
            args.live_model_backend = ModelBackend(args.inference_model, max_new_tokens=args.model_max_new_tokens,
                                                   quantization=args.model_quantization)
    elif args.inference_cache or args.inference_run_id or args.inference_workers != 1 or args.model_quantization:
        raise ValueError("Configuração de inferência requer --inference-model.")
    try:
        run_simulation(args)
    finally:
        if pool is not None:
            pool.close()
