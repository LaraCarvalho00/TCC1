"""História incremental com inferência ao vivo (uma geração por nó e rodada).

Não usa o banco de amostras. ``banco_smol.json`` entra só com id, pergunta e
gabarito. As gerações vão para um SQLite compartilhado, indexado pela semente
``0:rodada:node_id``; etapas seguintes reutilizam o texto já gravado.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

from concurrent.futures import ProcessPoolExecutor, as_completed

from sistema.core.answer import normalize
from sistema.experimentos.execucao import RAIZ
from sistema.simulate import parse_args, run_simulation

MODELOS = {
    "smol": "HuggingFaceTB/SmolLM3-3B",
    "qwen3-8b": "Qwen/Qwen3-8B",
}
TAREFAS_PADRAO = RAIZ / "sistema" / "dados" / "banco_smol.json"
RECORTE_TCC = {
    "fracoes": (0.0, 0.2, 0.4, 0.8),
    "ps": (0.2,),
    "sementes": (0,),
    "nos": 10,
    "rodadas": 20,
}
RECORTE_N20 = {
    "fracoes": (0.0, 0.2, 0.4, 0.8),
    "ps": (0.2,),
    "sementes": (0,),
    "nos": 20,
    "rodadas": 50,
}
RECORTE_ISABELA = {
    "fracoes": (0.0, 0.2, 0.4, 0.6, 0.8),
    "ps": (0.1, 0.2),
    "sementes": tuple(range(5)),
    "nos": 50,
    "rodadas": 50,
}
CAMPOS = (
    "id", "etapa", "conluio", "fracao", "fracao_instavel", "audit_mode", "audit_p",
    "nota", "semente", "com_reputacao_sem_gabarito", "sem_reputacao_sem_gabarito",
    "com_reputacao_teste", "rodadas_auditadas", "pasta",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=RAIZ, stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _job_id(etapa, conluio, fracao, audit_p, nota, instavel, semente) -> str:
    return (
        f"e{etapa}-c{int(conluio)}-m{round(fracao * 100):02d}-p{round(audit_p * 100):02d}"
        f"-{nota}-u{round(instavel * 100):02d}-s{semente}"
    )


def _item(etapa, fracao, conluio, semente, audit_mode, audit_p, nota, instavel) -> dict:
    return {
        "id": _job_id(etapa, conluio, fracao, audit_p, nota, instavel, semente),
        "etapa": etapa, "fracao": fracao, "conluio": conluio, "semente": semente,
        "audit_mode": audit_mode, "audit_p": audit_p, "nota": nota, "fracao_instavel": instavel,
    }


def spec_recorte(nome: str) -> dict:
    if nome == "tcc":
        return dict(RECORTE_TCC)
    if nome == "n20":
        return dict(RECORTE_N20)
    if nome == "isabela":
        return dict(RECORTE_ISABELA)
    raise ValueError("Recorte deve ser tcc, n20 ou isabela")


def trabalhos(nome: str) -> tuple[list[dict], dict]:
    spec = spec_recorte(nome)
    jobs: list[dict] = []
    for fracao in spec["fracoes"]:
        for conluio in ((False,) if fracao == 0 else (False, True)):
            for semente in spec["sementes"]:
                jobs.append(_item(4, fracao, conluio, semente, "fixed", 0.1, "exact", 0.0))
    for audit_p in spec["ps"]:
        for fracao in spec["fracoes"]:
            for conluio in ((False,) if fracao == 0 else (False, True)):
                for semente in spec["sementes"]:
                    jobs.append(_item(5, fracao, conluio, semente, "random", audit_p, "exact", 0.0))
    for etapa, nota, instavel in ((6, "graded", 0.0), (7, "exact", 0.2)):
        for fracao in spec["fracoes"]:
            if fracao == 0:
                continue
            for semente in spec["sementes"]:
                jobs.append(_item(etapa, fracao, True, semente, "random", 0.2, nota, instavel))
    ids = [job["id"] for job in jobs]
    if len(ids) != len(set(ids)):
        raise ValueError("Identificadores de cenário repetidos")
    return jobs, spec


def carregar_tarefas(path: Path) -> tuple[list[dict], str]:
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    tasks = data["tarefas"]
    if len(tasks) < 1 or any(not all(key in task for key in ("id", "question", "answer")) for task in tasks):
        raise ValueError("O arquivo de tarefas precisa de id, question e answer")
    questions = [{"id": item["id"], "question": item["question"], "answer": item["answer"]} for item in tasks]
    return questions, hashlib.sha256(raw).hexdigest()


def carregar_banco(path: Path) -> tuple[list[dict], dict, str, dict]:
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    tasks = data["tarefas"]
    if len(tasks) != 50 or any(len(item.get("amostras") or []) != 20 for item in tasks):
        raise ValueError("O banco precisa de 50 questões e 20 amostras por questão")
    questions, digest = carregar_tarefas(path)
    answers = {item["id"]: [normalize(sample["resposta"]) for sample in item["amostras"]] for item in tasks}
    correct = sum(
        int(sample is not None and sample == normalize(item["answer"]))
        for item in tasks for sample in answers[item["id"]]
    )
    return questions, answers, digest, {"acertos": correct, "total": 1000, "modelo": (data.get("parametros") or {}).get("modelo")}


def modelo_caminho(llm: str) -> str:
    if llm == "qwen3-8b":
        local = RAIZ / ".cache" / "Qwen3-8B"
        if (local / "config.json").is_file():
            return str(local)
    return MODELOS[llm]


def argv_job(job: dict, output: Path, spec: dict) -> list[str]:
    argv = [
        "--nodes", str(spec["nos"]), "--rounds", str(spec["rodadas"]),
        "--malicious", str(job["fracao"]), "--seed", str(job["semente"]),
        "--output", str(output), "--experiment-id", job["id"],
        "--overwrite", "--quiet", "--no-row-sync",
        "--orchestration", "dynamic", "--topology", "kregular", "--degree", "4",
        "--defense", "all", "--signal", "consensus",
        "--consensus-mode", "distance", "--consensus-center", "medoid",
        "--mechanism", "ema", "--consensus-alpha", "0.05", "--oracle-alpha", "0.95",
        "--malicious-answer", "noise", "--malicious-strategy", "knows_schedule",
        "--honest-rounds", "5", "--noise-mode", "relative", "--noise-distance", "0.2",
        "--calibration-rounds", "0",
        "--audit-mode", job["audit_mode"], "--audit-p", str(job["audit_p"]),
        "--validation-score", job["nota"],
        "--unstable", str(job["fracao_instavel"]), "--unstable-mode", "attribute",
        "--model-temperature", "0.7", "--model-top-p", "0.95",
    ]
    if job["conluio"]:
        argv.extend(["--collusion-value", "999"])
    return argv


def _linha(job: dict, resumo: dict, pasta: Path) -> dict:
    return {
        "id": job["id"], "etapa": job["etapa"], "conluio": int(job["conluio"]),
        "fracao": job["fracao"], "fracao_instavel": job["fracao_instavel"],
        "audit_mode": job["audit_mode"], "audit_p": job["audit_p"], "nota": job["nota"],
        "semente": job["semente"],
        "com_reputacao_sem_gabarito": resumo["consensus_accuracy_weighted_no_oracle"],
        "sem_reputacao_sem_gabarito": resumo["consensus_accuracy_majority_no_oracle"],
        "com_reputacao_teste": resumo["consensus_accuracy_weighted_on_tests"],
        "rodadas_auditadas": resumo.get("n_audited", ""),
        "pasta": str(pasta),
    }


def _media_dp(valores: list[float]) -> tuple[float, float]:
    media = statistics.mean(valores) * 100
    dp = statistics.stdev(valores) * 100 if len(valores) > 1 else 0.0
    return round(media, 4), round(dp, 4)


def _num(row: dict) -> dict:
    item = dict(row)
    item["etapa"] = int(row["etapa"])
    item["conluio"] = int(row["conluio"])
    item["fracao"] = float(row["fracao"])
    item["audit_p"] = float(row["audit_p"])
    item["com_reputacao_sem_gabarito"] = float(row["com_reputacao_sem_gabarito"])
    item["sem_reputacao_sem_gabarito"] = float(row["sem_reputacao_sem_gabarito"])
    return item


def resumir_etapas(rows: list[dict]) -> list[dict]:
    rows = [_num(row) for row in rows]
    saida = []
    etapa4 = [row for row in rows if row["etapa"] == 4]
    grupos: dict[tuple, list[dict]] = {}
    for row in etapa4:
        grupos.setdefault((int(row["conluio"]), float(row["fracao"])), []).append(row)
    for (conluio, fracao), grupo in sorted(grupos.items()):
        sem = [float(item["sem_reputacao_sem_gabarito"]) for item in grupo]
        com = [float(item["com_reputacao_sem_gabarito"]) for item in grupo]
        if fracao == 0 and conluio == 0:
            media, dp = _media_dp(sem)
            saida.append({"etapa": 1, "descricao": "Caso base, 0% maliciosos, sem reputação",
                          "conluio": 0, "fracao": fracao, "audit_p": "", "acuracia_media": media, "acuracia_dp": dp, "n": len(grupo)})
        if fracao > 0:
            etapa = 3 if conluio else 2
            rotulo = "com conluio" if conluio else "sem conluio"
            media, dp = _media_dp(sem)
            saida.append({"etapa": etapa, "descricao": f"Maliciosos {rotulo}, sem reputação",
                          "conluio": conluio, "fracao": fracao, "audit_p": "", "acuracia_media": media, "acuracia_dp": dp, "n": len(grupo)})
        media, dp = _media_dp(com)
        saida.append({"etapa": 4, "descricao": "Reputação por consenso, sem auditoria",
                      "conluio": conluio, "fracao": fracao, "audit_p": "", "acuracia_media": media, "acuracia_dp": dp, "n": len(grupo)})
    for etapa, descricao, filtro in (
        (5, "Auditoria por sorteio", lambda r: r["etapa"] == 5),
        (6, "Nota graduada, conluio, p=0,2", lambda r: r["etapa"] == 6),
        (7, "20% instáveis, conluio, p=0,2", lambda r: r["etapa"] == 7),
    ):
        blocos: dict[tuple, list[dict]] = {}
        for row in rows:
            if filtro(row):
                blocos.setdefault((int(row["conluio"]), float(row["fracao"]), float(row["audit_p"])), []).append(row)
        for (conluio, fracao, audit_p), grupo in sorted(blocos.items()):
            valores = [float(item["com_reputacao_sem_gabarito"]) for item in grupo]
            media, dp = _media_dp(valores)
            extra = f", p={audit_p:g}" if etapa == 5 else ""
            saida.append({"etapa": etapa, "descricao": descricao + extra, "conluio": conluio,
                          "fracao": fracao, "audit_p": audit_p, "acuracia_media": media, "acuracia_dp": dp, "n": len(grupo)})
    return saida


def acumular_reputacao(pasta: Path, chave: tuple, acumulado: dict) -> None:
    grupos: dict[tuple[int, str], list[float]] = {}
    with (pasta / "reputation_history.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["profile"] not in ("honest", "malicious"):
                continue
            grupos.setdefault((int(row["checkpoint"]), row["profile"]), []).append(float(row["reputation"]))
    slot = acumulado.setdefault(chave, {})
    for (checkpoint, profile), values in grupos.items():
        slot.setdefault(checkpoint, {}).setdefault(profile, []).append(statistics.mean(values))


def gravar_reputacao(acumulado: dict, path: Path, rodadas: int) -> None:
    campos = ("etapa", "conluio", "fracao", "nota", "fracao_instavel", "rodada",
              "reputacao_media_honestos", "reputacao_media_maliciosos")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=campos)
        writer.writeheader()
        for chave in sorted(acumulado):
            etapa, conluio, fracao, nota, instavel = chave
            for rodada in range(rodadas + 1):
                perfis = acumulado[chave].get(rodada, {})
                honestos = perfis.get("honest", [])
                maliciosos = perfis.get("malicious", [])
                writer.writerow({
                    "etapa": etapa, "conluio": conluio, "fracao": fracao, "nota": nota,
                    "fracao_instavel": instavel, "rodada": rodada,
                    "reputacao_media_honestos": "" if not honestos else round(statistics.mean(honestos), 6),
                    "reputacao_media_maliciosos": "" if not maliciosos else round(statistics.mean(maliciosos), 6),
                })


def simular_job(job: dict, tarefas: list, banco, output: str, spec: dict, git_sha):
    """Uma execução no banco de respostas (pode rodar em processo filho)."""
    args = parse_args(argv_job(job, Path(output), spec))
    args.tasks = tarefas
    args.answer_bank = banco
    args.git_sha = git_sha
    resumo = run_simulation(args)
    pasta = Path(output) / job["id"]
    return _linha(job, resumo, pasta)


def _abrir_pool(modelo: str, workers: int, cache: Path, task_hash: str):
    from huggingface_hub import snapshot_download
    from importlib.metadata import version
    from sistema.node.inference_pool import InferencePool

    local = Path(modelo)
    snapshot = str(local) if (local / "config.json").is_file() else snapshot_download(modelo, local_files_only=True)
    revision = Path(snapshot).name
    config = {
        "modelo": modelo, "revisao": revision, "workers": workers, "quantizacao": "nf4",
        "temperatura": 0.7, "top_p": 0.95, "max_new_tokens": 256,
        "tarefas_sha256": task_hash, "torch": version("torch"),
        "transformers": version("transformers"), "bitsandbytes": version("bitsandbytes"),
    }
    return InferencePool(modelo, snapshot, revision, 256, workers, str(cache), config)


def _chave_rep(job: dict) -> tuple:
    return (job["etapa"], int(job["conluio"]), job["fracao"], job["nota"], job["fracao_instavel"])


def _fechar_lote(saida: Path, rows: list, spec: dict, fonte: str, manifest: dict, manifesto_path: Path, started: float, acumulado: dict) -> None:
    etapas = resumir_etapas(rows)
    with (saida / "etapas.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("etapa", "descricao", "conluio", "fracao", "audit_p",
                                                    "acuracia_media", "acuracia_dp", "n"))
        writer.writeheader()
        writer.writerows(etapas)
    gravar_reputacao(acumulado, saida / "reputacao_por_rodada.csv", spec["rodadas"])
    from sistema.experimentos.graficos_incrementais import gerar as gerar_figuras
    gerar_figuras(saida, spec, fonte=fonte)
    manifest["status"] = "concluido"
    manifest["fim_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["elapsed_s"] = time.perf_counter() - started
    manifesto_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def executar(saida: Path, *, recorte: str, llm: str, tarefas: Path, workers: int,
             confirmar_isabela: bool = False, fonte: str = "banco") -> Path:
    if fonte not in ("banco", "vivo"):
        raise ValueError("fonte deve ser banco ou vivo")
    jobs, spec = trabalhos(recorte)
    spec["rotulo_banco"] = {
        "smol": "banco SmolLM3-3B (20 amostras/questão, sem nova inferência)",
        "qwen3-8b": "banco Qwen3-8B (20 amostras/questão, sem nova inferência)",
    }.get(llm, "banco (20 amostras/questão, sem nova inferência)")
    spec["modelo_nome"] = MODELOS.get(llm, llm)
    unicas = spec["nos"] * spec["rodadas"] * len(spec["sementes"])
    if fonte == "vivo" and recorte == "isabela" and not confirmar_isabela:
        raise ValueError(
            f"O recorte isabela ao vivo pede {len(jobs)} execuções e até {unicas} gerações. "
            "Use --fonte banco, --recorte n20, --recorte tcc ou --confirmar-isabela."
        )
    if workers < 1:
        raise ValueError("workers deve ser ≥ 1")
    if fonte == "vivo" and llm == "qwen3-8b" and workers > 1:
        raise ValueError("Qwen3-8B nesta GPU cabe só uma instância NF4")
    saida = saida.resolve()
    manifesto_path = saida / "manifesto.json"
    if saida.exists() and not manifesto_path.is_file():
        raise FileExistsError(f"A pasta {saida} já existe sem manifesto desta série")
    bruto = None
    banco = None
    if fonte == "banco":
        tasks, banco, task_hash, bruto = carregar_banco(tarefas)
    else:
        tasks, task_hash = carregar_tarefas(tarefas)
    if len(tasks) < spec["rodadas"]:
        raise ValueError("Há menos tarefas que rodadas")
    modelo = modelo_caminho(llm) if fonte == "vivo" else (bruto or {}).get("modelo") or MODELOS[llm]
    if manifesto_path.is_file():
        manifest = json.loads(manifesto_path.read_text(encoding="utf-8"))
        if manifest.get("status") == "concluido":
            raise FileExistsError("Esta série já concluiu; use outra pasta")
        if manifest.get("jobs") != [job["id"] for job in jobs] or manifest.get("recorte") != recorte:
            raise ValueError("O manifesto não corresponde a este recorte")
        if manifest.get("inferencia") not in (fonte, "ao_vivo" if fonte == "vivo" else "banco"):
            raise ValueError("O manifesto não corresponde a esta fonte de respostas")
        rows = list(csv.DictReader((saida / "execucoes.csv").open(encoding="utf-8")))
        done = {row["id"] for row in rows}
    else:
        saida.mkdir(parents=True, exist_ok=False)
        (saida / "execucoes").mkdir()
        rows, done = [], set()
        manifest = {
            "status": "em_andamento",
            "inicio_utc": datetime.now(timezone.utc).isoformat(),
            "recorte": recorte, "llm": llm, "modelo": modelo,
            "inferencia": fonte,
            "nos": spec["nos"], "rodadas": spec["rodadas"],
            "sementes": list(spec["sementes"]), "fracoes": list(spec["fracoes"]),
            "jobs": [job["id"] for job in jobs],
            "chamadas_unicas_previstas": 0 if fonte == "banco" else unicas,
            "banco_acerto": bruto,
            "observacao": (
                "Honestos sorteiam uma das 20 respostas pré-geradas do Smol; sem LLM nesta série."
                if fonte == "banco" else
                "Cada nó gera na hora; o SQLite compartilhado evita repetir a mesma semente."
            ),
            "tarefas": str(tarefas.resolve()), "tarefas_sha256": task_hash,
            "commit": _git("rev-parse", "HEAD"),
            "codigo_sha256": _sha(Path(__file__)),
        }
        manifesto_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with (saida / "execucoes.csv").open("w", newline="", encoding="utf-8") as handle:
            csv.DictWriter(handle, fieldnames=CAMPOS).writeheader()
    acumulado: dict = {}
    started = time.perf_counter()
    git_sha = _git("rev-parse", "--short", "HEAD")
    if fonte == "banco":
        pending = [job for job in jobs if job["id"] not in done]
        with (saida / "execucoes.csv").open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CAMPOS)
            if pending:
                with ProcessPoolExecutor(max_workers=workers) as pool:
                    futures = {
                        pool.submit(simular_job, job, tasks, banco, str(saida / "execucoes"), spec, git_sha): job
                        for job in pending
                    }
                    for count, future in enumerate(as_completed(futures), 1):
                        job = futures[future]
                        row = future.result()
                        writer.writerow(row)
                        handle.flush()
                        rows.append(row)
                        done.add(job["id"])
                        pasta = Path(row["pasta"])
                        acumular_reputacao(pasta, _chave_rep(job), acumulado)
                        manifest["concluidas"] = len(done)
                        if count == 1 or count % 25 == 0 or count == len(pending):
                            manifesto_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                            print(f"{len(done)}/{len(jobs)} {job['id']}", flush=True)
        _fechar_lote(saida, rows, spec, fonte, manifest, manifesto_path, started, acumulado)
        return saida

    pool = _abrir_pool(modelo, workers, saida / "inferencias.sqlite", task_hash)
    try:
        with (saida / "execucoes.csv").open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CAMPOS)
            for index, job in enumerate(jobs, 1):
                if job["id"] in done:
                    pasta = saida / "execucoes" / job["id"]
                    if pasta.is_dir():
                        acumular_reputacao(pasta, _chave_rep(job), acumulado)
                    print(f"{index}/{len(jobs)} {job['id']} cache/retomada", flush=True)
                    continue
                pasta_job = saida / "execucoes" / job["id"]
                if pasta_job.exists():
                    shutil.rmtree(pasta_job)
                args = parse_args(argv_job(job, saida / "execucoes", spec))
                args.live_model_backend = pool
                args.tasks = tasks
                args.task_bank = str(tarefas)
                args.task_bank_sha256 = task_hash
                args.git_sha = git_sha
                print(f"{index}/{len(jobs)} {job['id']}", flush=True)
                resumo = run_simulation(args)
                pasta = saida / "execucoes" / job["id"]
                row = _linha(job, resumo, pasta)
                writer.writerow(row)
                handle.flush()
                rows.append(row)
                done.add(job["id"])
                acumular_reputacao(pasta, _chave_rep(job), acumulado)
                manifest["concluidas"] = len(done)
                manifesto_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        pool.close()
    _fechar_lote(saida, rows, spec, fonte, manifest, manifesto_path, started, acumulado)
    return saida


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--planejar", action="store_true")
    parser.add_argument("--recorte", choices=("tcc", "n20", "isabela"), default="tcc")
    parser.add_argument("--llm", choices=tuple(MODELOS), default="smol")
    parser.add_argument("--tarefas", type=Path, default=TAREFAS_PADRAO)
    parser.add_argument("--saida", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--fonte", choices=("banco", "vivo"), default="banco")
    parser.add_argument("--confirmar-isabela", action="store_true")
    args = parser.parse_args(argv)
    try:
        jobs, spec = trabalhos(args.recorte)
        unicas = spec["nos"] * spec["rodadas"] * len(spec["sementes"])
        if args.planejar:
            print(
                f"{len(jobs)} execuções; {spec['nos']} nós; {spec['rodadas']} rodadas; "
                f"{len(spec['sementes'])} semente(s); fonte {args.fonte}; recorte {args.recorte}; "
                f"LLM {args.llm}"
                + (f"; até {unicas} gerações novas" if args.fonte == "vivo" else "; banco de 20 amostras/questão")
            )
            for job in jobs:
                print(job["id"])
            return 0
        if args.saida is None:
            raise ValueError("Informe --saida")
        path = executar(args.saida, recorte=args.recorte, llm=args.llm, tarefas=args.tarefas,
                        workers=args.workers, confirmar_isabela=args.confirmar_isabela,
                        fonte=args.fonte)
        print(f"Resultado: {path}", flush=True)
        return 0
    except (OSError, ValueError, FileExistsError, json.JSONDecodeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
