"""Execução isolada e rastreável das grades do artigo."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import importlib
import json
import multiprocessing
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback
import uuid

RAIZ = Path(__file__).resolve().parents[2]
BANCO_PADRAO = RAIZ / "sistema" / "dados" / "banco_smol.json"
SAIDA_PADRAO = RAIZ / "resultados" / "artigo"
_WORKER = None


def _iniciar_worker(nome, tarefas, banco, bruto, git_sha):
    global _WORKER
    modulo = importlib.import_module(f"sistema.experimentos.{nome}")
    _WORKER = (modulo, tarefas, banco, bruto, git_sha)


def _executar_worker(job):
    modulo, tarefas, banco, bruto, git_sha = _WORKER
    return modulo.executar(job, tarefas, banco, bruto, git_sha=git_sha)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=RAIZ, stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _manifesto(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def executar_grade(nome, modulo, destino, banco_path, jobs, workers=1, guardar_brutos=False):
    """Executa a grade num subdiretório novo, sem sobrescrever saídas anteriores."""
    if nome not in ("ruido", "centros") or workers < 1:
        raise ValueError("Experimento desconhecido ou número inválido de processos")
    if not jobs or len({json.dumps(job, sort_keys=True) for job in jobs}) != len(jobs):
        raise ValueError("A grade deve conter trabalhos distintos")
    banco_path = Path(banco_path).resolve(strict=True)
    tarefas, banco = modulo.carregar_banco(str(banco_path))
    if not tarefas or any(not banco.get(t["id"]) for t in tarefas):
        raise ValueError("Banco de respostas vazio ou sem amostras para uma tarefa")
    root = Path(destino).resolve() / nome
    root.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    path = root / (started.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    path.mkdir()
    bruto = path / "brutos"
    bruto.mkdir()
    manifest = {
        "experimento": nome, "status": "em_andamento", "inicio_utc": started.isoformat(),
        "commit": _git("rev-parse", "HEAD"), "alteracoes_locais": _git("status", "--porcelain"),
        "python": sys.version, "plataforma": platform.platform(),
        "banco": str(banco_path), "banco_sha256": _sha(banco_path),
        "codigo_sha256": {p.relative_to(RAIZ).as_posix(): _sha(p) for base in (RAIZ / "sistema" / "core", RAIZ / "sistema" / "experimentos", RAIZ / "sistema" / "aplicacao") for p in sorted(base.glob("*.py"))},
        "simulador_sha256": _sha(RAIZ / "sistema" / "simulate.py"),
        "tarefas": len(tarefas), "jobs": jobs, "concluidas": 0, "workers": workers,
        "guardar_brutos": guardar_brutos,
        "observacao": "Respostas honestas sorteadas do banco; rede simulada em processo único.",
    }
    manifest_path = path / "manifesto.json"
    _manifesto(manifest_path, manifest)
    accumulator = {}
    rows = []
    timer = time.perf_counter()
    run_git_sha = _git("rev-parse", "--short", "HEAD") or "unknown"
    try:
        with (path / "execucoes.csv").open("x", newline="", encoding="utf8") as handle:
            writer = csv.DictWriter(handle, fieldnames=modulo.CAMPOS)
            writer.writeheader()
            ctx = multiprocessing.get_context("spawn")
            with ctx.Pool(processes=workers, initializer=_iniciar_worker,
                          initargs=(nome, tarefas, banco, str(bruto), run_git_sha)) as pool:
                for index, (row, run_dir) in enumerate(pool.imap(_executar_worker, jobs, chunksize=1), 1):
                    writer.writerow(row)
                    handle.flush()
                    rows.append(row)
                    modulo.acumular_reputacao(run_dir, tuple(row[key] for key in modulo.CHAVES), accumulator)
                    if not guardar_brutos:
                        resolved = Path(run_dir).resolve(strict=True)
                        if resolved == bruto.resolve() or not resolved.is_relative_to(bruto.resolve()):
                            raise ValueError("Caminho de dados brutos fora da execução")
                        shutil.rmtree(resolved)
                    manifest["concluidas"] = index
                    if index == 1 or index % 25 == 0 or index == len(jobs):
                        _manifesto(manifest_path, manifest)
                        print(f"{index}/{len(jobs)} {time.perf_counter() - timer:.0f}s", flush=True)
        summary = modulo.resumir(rows)
        with (path / "resumo.csv").open("x", newline="", encoding="utf8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)
        modulo.gravar_reputacao(accumulator, str(path / "reputacao_por_rodada.csv"))
        if nome == "ruido":
            divergences, pairs = modulo.conferir_sem_genese(rows)
            manifest["comparacao_sem_genese"] = {"pares": pairs, "divergencias": divergences}
            if divergences:
                raise RuntimeError(f"Comparação sem gabarito divergiu em {divergences} de {pairs} pares")
        if not guardar_brutos:
            resolved = bruto.resolve(strict=True)
            if resolved.parent != path.resolve():
                raise ValueError("Caminho de dados brutos fora da execução")
            shutil.rmtree(resolved)
        manifest["status"] = "concluido"
    except BaseException:
        manifest["status"] = "falhou"
        manifest["erro"] = traceback.format_exc()
        raise
    finally:
        manifest["fim_utc"] = datetime.now(timezone.utc).isoformat()
        _manifesto(manifest_path, manifest)
    return path
