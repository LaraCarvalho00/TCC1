"""Simulação local do sistema, em processo único e sem dependências externas.

Reproduz o fluxo completo do Documento de Visão (distribuição de tarefas,
coleta de respostas, consenso, atualização de reputação e registro de métricas)
sem Docker e sem executar o modelo.  Serve para validar rapidamente o mecanismo
de reputação e o consenso — a "versão mínima funcionando" combinada na reunião.

O laço de rodada é implementado em :mod:`sistema.core.engine` e compartilhado
com o orquestrador Docker, garantindo que os dois caminhos de execução sejam
estritamente comparáveis (mesma lógica de consenso, atualização e logging).

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
import os
import random

from .core import behavior, dataset
from .core.answer import normalize
from .core.defenses import DefenseConfig, preset, preset_names
from .core.engine import process_round
from .core.metrics import MetricsLogger, dynamic_summary
from .core.network import SimulatedNetwork, log_round
from .core.protocol import (
    AUDIT_MODES,
    CONSENSUS_MODES,
    MALICIOUS_STRATEGIES,
    SIGNALS,
    ProtocolConfig,
    oracle_round,
    plan_audits,
)
from .core.reputation import MECHANISMS, ReputationTracker
from .core.schedule import DEFAULT_TEST_EVERY, is_test_round, test_rounds_1based
from .core.schemas import NodeResponse
from .core.topology import KINDS, build_graph, diameter, max_degree

ORCHESTRATIONS = ("fixed", "dynamic")

_DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "results", "simulacao")


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------

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


def run_simulation(args: argparse.Namespace) -> dict:
    """Executa a simulação e retorna o resumo gerado pelo MetricsLogger."""
    rng = random.Random(args.seed)
    noise_rng = random.Random(f"{args.seed}:noise")
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

    test_every = int(getattr(args, "test_every", DEFAULT_TEST_EVERY))
    planned_tests = test_rounds_1based(args.rounds, test_every)
    logger = MetricsLogger(
        output_dir,
        experiment_id=experiment_id,
        overwrite=overwrite,
        row_sync=bool(getattr(args, "row_sync", True)),
    )

    orchestration = getattr(args, "orchestration", "fixed")
    signal = getattr(args, "signal", "truth")
    defense = defense_from_args(args)
    audit_mode = getattr(args, "audit_mode", "fixed")
    audited_rounds = (
        plan_audits(args.seed, args.rounds, test_every, float(getattr(args, "audit_p", 0.1)))
        if audit_mode == "random"
        else frozenset()
    )
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
    )
    network = None
    if orchestration == "dynamic":
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

            model_answers = getattr(args, "model_answers", None)
            answer_bank = getattr(args, "answer_bank", None)
            use_noise = getattr(args, "malicious_answer", "fixed") == "noise"
            laying_low = (
                getattr(args, "malicious_strategy", "always") == "on_off"
                and round_index < int(getattr(args, "honest_rounds", 5))
            )
            shared_noise = None
            if use_noise and bcfg.malicious_collusion_value is not None and not laying_low:
                base = behavior.honest_base(noise_rng, expected, bcfg, answer_bank, task["id"])
                shared_noise = behavior.corrupt_with_noise(base, noise_rng)
            responses: list[NodeResponse] = []
            for node_id in node_ids:
                if node_id in unstable_nodes and unstable_rng.random() < bcfg.unstable_p_drop:
                    answer, latency = None, 0
                elif use_noise and profiles[node_id] == behavior.MALICIOUS and not laying_low:
                    # Consome o gerador principal como o perfil fixo faria, para
                    # os honestos seguintes verem a mesma sequência.
                    _discarded, latency = behavior.simulate_answer(profiles[node_id], expected, bcfg, rng)
                    if shared_noise is not None:
                        answer = shared_noise
                    else:
                        base = behavior.honest_base(noise_rng, expected, bcfg, answer_bank, task["id"])
                        answer = behavior.corrupt_with_noise(base, noise_rng)
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

            if network is not None:
                _dynamic_round(network, logger, round_index, task["id"], expected, responses, profiles,
                               mechanism, initial, this_is_test)
                continue

            # Orquestrador fixo. Com sinal de consenso ou híbrido, a rodada de
            # correção usa o gabarito no lugar do consenso.
            round_signal, round_alpha = "truth", None
            if signal != "truth":
                if oracle_round(round_index, protocol):
                    round_signal, round_alpha = "truth", protocol.oracle_alpha
                else:
                    round_signal, round_alpha = "consensus", protocol.consensus_alpha
            process_round(
                round_index=round_index,
                task_id=task["id"],
                expected=expected,
                responses=responses,
                tracker=tracker,
                logger=logger,
                is_test=this_is_test,
                signal=round_signal,
                alpha=round_alpha,
                consensus_mode=protocol.consensus_mode,
            )
    except BaseException:
        logger.close()
        raise

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
    extra = None
    final_reputations = None
    if orchestration != "fixed" or signal != "truth":
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
        "--malicious-strategy", choices=MALICIOUS_STRATEGIES, default="always", dest="malicious_strategy",
        help="always = ataca sempre; on_off = imita honesto nas primeiras rodadas.",
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
        "--orchestration", choices=ORCHESTRATIONS, default="fixed",
        help="fixed = orquestrador central de hoje; dynamic = líder eleito a cada rodada.",
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
    run_simulation(parse_args())
