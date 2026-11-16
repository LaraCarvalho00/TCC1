"""Grade local de inferência real com retomada por cenário.

Cada cenário usa um cache exclusivo e cada tentativa usa uma pasta nova. A
rede é simulada em um processo; os workers da LLM são processos locais.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS = ROOT / "sistema" / "dados" / "banco_smol.json"
DEFAULT_MODEL = "HuggingFaceTB/SmolLM3-3B"
FRACTIONS = (0.2, 0.4, 0.6, 0.8)
PROBABILITIES = (0.1, 0.2)


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, value: dict) -> None:
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)


def _task_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scenarios(seeds: list[int], scores: list[str], fractions: tuple[float, ...] = FRACTIONS,
              probabilities: tuple[float, ...] = PROBABILITIES,
              nodes: int = 50, rounds: int = 50) -> list[dict]:
    if not seeds or len(seeds) != len(set(seeds)) or any(x < 0 for x in seeds):
        raise ValueError("As sementes devem ser inteiros não negativos e sem repetição.")
    if not scores or len(scores) != len(set(scores)) or any(x not in ("exact", "graded") for x in scores):
        raise ValueError("As notas devem ser exact e/ou graded, sem repetição.")
    if not fractions or len(fractions) != len(set(fractions)) or any(x not in FRACTIONS for x in fractions):
        raise ValueError("As frações devem ser 0,2, 0,4, 0,6 e/ou 0,8, sem repetição.")
    if not probabilities or len(probabilities) != len(set(probabilities)) or any(x not in PROBABILITIES for x in probabilities):
        raise ValueError("As probabilidades devem ser 0,1 e/ou 0,2, sem repetição.")
    entries = []
    for fraction, probability, score, seed in itertools.product(fractions, probabilities, scores, seeds):
        identifier = f"n{nodes}-r{rounds}-m{round(fraction * 100):02d}-p{round(probability * 100):02d}-{score}-s{seed}"
        entries.append({"id": identifier, "fracao_maliciosos": fraction, "audit_p": probability,
                        "nota": score, "semente": seed, "status": "pendente", "tentativas": []})
    return entries


def command(entry: dict, config: dict, scenario_dir: Path, attempt_id: str) -> list[str]:
    cache = scenario_dir / "inferencias.sqlite"
    return [sys.executable, "-m", "sistema.simulate",
            "--inference-model", config["modelo"], "--model-quantization", "nf4",
            "--inference-workers", "2", "--inference-cache", str(cache),
            "--inference-run-id", entry["id"], "--task-bank", config["tarefas"],
            "--nodes", str(config["nos"]), "--rounds", str(config["rodadas"]), "--malicious", str(entry["fracao_maliciosos"]),
            "--seed", str(entry["semente"]), "--orchestration", "dynamic", "--topology", "kregular",
            "--degree", "4", "--defense", "all", "--signal", "consensus",
            "--consensus-mode", "distance", "--consensus-center", "medoid", "--mechanism", "ema_slow_up",
            "--audit-mode", "random", "--audit-p", str(entry["audit_p"]),
            "--validation-score", entry["nota"], "--malicious-strategy", "knows_schedule", "--honest-rounds", "5",
            "--malicious-answer", "noise", "--noise-mode", config["ruido_modo"],
            "--noise-distance", str(config["ruido_distancia"]), "--collusion-value", "999",
            "--model-temperature", "0.7", "--model-top-p", "0.95", "--model-max-new-tokens", "256",
            "--output", str(scenario_dir), "--experiment-id", attempt_id]


def execute(destination: Path, tasks: Path, seeds: list[int], scores: list[str],
            *, resume: bool = False, model: str = DEFAULT_MODEL,
            noise_mode: str = "relative", noise_distance: float = 0.2,
            fractions: tuple[float, ...] = FRACTIONS,
            probabilities: tuple[float, ...] = PROBABILITIES,
            nodes: int = 50, rounds: int = 50) -> tuple[Path, bool]:
    if noise_mode not in ("relative", "multiplicative") or not 0 < noise_distance < 1:
        raise ValueError("Ruído inválido: distância deve estar em (0, 1).")
    if nodes < 5 or rounds < 1:
        raise ValueError("São necessários pelo menos 5 nós e 1 rodada para a topologia de grau 4.")
    if any(abs(round(f * nodes) - f * nodes) > 1e-9 for f in fractions):
        raise ValueError("As frações devem corresponder a números inteiros de nós maliciosos.")
    jobs = scenarios(seeds, scores, fractions, probabilities, nodes, rounds)
    tasks = tasks.resolve(strict=True)
    if not tasks.is_file():
        raise ValueError("O banco de tarefas deve ser um arquivo.")
    destination = destination.resolve()
    manifest_path = destination / "manifesto_grade.json"
    config = {"modelo": model, "quantizacao": "nf4", "workers": 2, "tarefas": str(tasks),
              "tarefas_sha256": _task_hash(tasks), "nos": nodes, "rodadas": rounds,
              "sementes": seeds, "notas": scores, "fracoes": list(fractions),
              "probabilidades": list(probabilities), "ruido_modo": noise_mode,
              "ruido_distancia": noise_distance, "conluio": True}
    if resume:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("configuracao") != config:
            raise ValueError("A configuração ou o hash das tarefas mudou; não é possível retomar esta grade.")
        immutable = ("id", "fracao_maliciosos", "audit_p", "nota", "semente")
        existing = manifest.get("cenarios", [])
        if len(existing) != len(jobs) or any(
            any(current.get(key) != expected[key] for key in immutable)
            for current, expected in zip(existing, jobs)
        ):
            raise ValueError("Os cenários do manifesto não correspondem à configuração.")
    else:
        destination.mkdir(parents=True, exist_ok=False)
        manifest = {"versao": 1, "inicio_utc": _stamp(), "status": "em_andamento", "configuracao": config,
                    "total_cenarios": len(jobs), "chamadas_previstas": len(jobs) * nodes * rounds,
                    "observacao": "Simulação local; duas instâncias quantizadas em processos locais, não contêineres.",
                    "cenarios": jobs}
        _atomic_json(manifest_path, manifest)
    manifest["status"] = "em_andamento"
    _atomic_json(manifest_path, manifest)
    try:
        for index, entry in enumerate(manifest["cenarios"], 1):
            if entry["status"] == "concluido":
                previous = entry["tentativas"][-1]
                result_dir = destination / "cenarios" / entry["id"] / previous["id"]
                completion = json.loads((result_dir / "inferencia_manifesto.json").read_text(encoding="utf-8"))
                if completion.get("status") != "concluido" or not (result_dir / "summary.json").is_file():
                    raise ValueError(f"O cenário {entry['id']} não tem resultado concluído verificável.")
                continue
            scenario_dir = destination / "cenarios" / entry["id"]
            scenario_dir.mkdir(parents=True, exist_ok=True)
            # A tentativa nunca sobrescreve dados de falhas ou interrupções anteriores.
            next_attempt = len(entry["tentativas"]) + 1
            attempt_id = f"tentativa-{next_attempt:04d}"
            while (scenario_dir / attempt_id).exists():
                next_attempt += 1
                attempt_id = f"tentativa-{next_attempt:04d}"
            cmd = command(entry, config, scenario_dir, attempt_id)
            attempt = {"id": attempt_id, "inicio_utc": _stamp(), "comando": cmd, "status": "em_andamento"}
            entry["tentativas"].append(attempt)
            entry["status"] = "em_andamento"
            _atomic_json(manifest_path, manifest)
            print(f"Cenário {index}/{len(jobs)}: {entry['id']} ({attempt_id})", flush=True)
            result = subprocess.run(cmd, cwd=ROOT, check=False)
            attempt["fim_utc"] = _stamp()
            attempt["codigo_saida"] = result.returncode
            complete = False
            if result.returncode == 0:
                result_dir = scenario_dir / attempt_id
                try:
                    completion = json.loads((result_dir / "inferencia_manifesto.json").read_text(encoding="utf-8"))
                    complete = completion.get("status") == "concluido" and (result_dir / "summary.json").is_file()
                except (OSError, ValueError):
                    complete = False
            attempt["status"] = "concluido" if complete else "falhou"
            entry["status"] = attempt["status"]
            _atomic_json(manifest_path, manifest)
            if not complete:
                manifest["status"] = "falhou"
                _atomic_json(manifest_path, manifest)
                return manifest_path, False
        manifest["status"] = "concluido"
        manifest["fim_utc"] = _stamp()
        _atomic_json(manifest_path, manifest)
        return manifest_path, True
    except BaseException as exc:
        manifest["status"] = "interrompido"
        manifest["erro"] = f"{type(exc).__name__}: {exc}"
        _atomic_json(manifest_path, manifest)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade local com duas instâncias quantizadas e cache por cenário")
    parser.add_argument("--saida", required=True, help="Diretório novo da grade, ou existente com --retomar")
    parser.add_argument("--tarefas", default=str(DEFAULT_TASKS))
    parser.add_argument("--sementes", type=int, nargs="+", default=[0])
    parser.add_argument("--notas", choices=("exact", "graded"), nargs="+", default=["exact", "graded"])
    parser.add_argument("--fracoes", type=float, choices=FRACTIONS, nargs="+", default=list(FRACTIONS))
    parser.add_argument("--probabilidades", type=float, choices=PROBABILITIES, nargs="+", default=list(PROBABILITIES))
    parser.add_argument("--modelo", default=DEFAULT_MODEL)
    parser.add_argument("--nos", type=int, default=50)
    parser.add_argument("--rodadas", type=int, default=50)
    parser.add_argument("--ruido-modo", choices=("relative", "multiplicative"), default="relative")
    parser.add_argument("--ruido-distancia", type=float, default=0.2)
    parser.add_argument("--retomar", action="store_true")
    parser.add_argument("--planejar", action="store_true")
    args = parser.parse_args(argv)
    try:
        jobs = scenarios(args.sementes, args.notas, tuple(args.fracoes), tuple(args.probabilidades),
                         args.nos, args.rodadas)
        if args.nos < 5 or args.rodadas < 1:
            raise ValueError("São necessários pelo menos 5 nós e 1 rodada para a topologia de grau 4.")
        if any(abs(round(f * args.nos) - f * args.nos) > 1e-9 for f in args.fracoes):
            raise ValueError("As frações devem corresponder a números inteiros de nós maliciosos.")
        if args.planejar:
            print(f"{len(jobs)} cenários; {args.nos} nós; {args.rodadas} rodadas; "
                  f"{len(jobs) * args.nos * args.rodadas} chamadas à LLM")
            for entry in jobs:
                print(entry["id"])
            return 0
        path, ok = execute(Path(args.saida), Path(args.tarefas), args.sementes, args.notas,
                           resume=args.retomar, model=args.modelo,
                           noise_mode=args.ruido_modo, noise_distance=args.ruido_distancia,
                           fractions=tuple(args.fracoes), probabilities=tuple(args.probabilidades),
                           nodes=args.nos, rounds=args.rodadas)
        print(f"Manifesto: {path}", flush=True)
        return 0 if ok else 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
