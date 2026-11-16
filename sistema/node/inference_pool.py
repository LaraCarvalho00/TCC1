"""Inferência NF4 em processos independentes, com cache transacional por execução.

Uma resposta confirmada é gravada no SQLite antes de iniciar outra chamada no
mesmo processo. A recuperação repete a simulação usando exclusivamente as
gerações já gravadas para o mesmo cenário e gera apenas as ausentes.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
from multiprocessing.connection import wait
import os
import sqlite3
import time
import traceback


def validate_workers(workers):
    """Reject invalid concurrency before opening a cache or loading CUDA."""
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 5:
        raise ValueError("Use de uma a cinco instâncias NF4.")
    return workers


def _worker(pipe, snapshot, max_tokens):
    try:
        from .inference import ModelBackend
        model = ModelBackend(snapshot, device="cuda", max_new_tokens=max_tokens, quantization="nf4")
        pipe.send({"ready": True})
        while True:
            job = pipe.recv()
            if job is None:
                break
            start = time.perf_counter()
            answer, text = model.sample(job["question"], temperature=job["temperature"],
                                        top_p=job["top_p"], seed=job["seed"])
            pipe.send({"seed": job["seed"], "answer": answer, "text": text,
                       "latency_ms": int((time.perf_counter() - start) * 1000)})
    except BaseException:
        try:
            pipe.send({"error": traceback.format_exc()})
        except BaseException:
            pass
    finally:
        pipe.close()


class InferencePool:
    def __init__(self, model_name, snapshot, revision, max_new_tokens, workers, cache_path, config):
        validate_workers(workers)
        config = dict(config)
        if validate_workers(config.get("workers", workers)) != workers:
            raise ValueError("A quantidade de instâncias diverge da configuração do cache.")
        config["workers"] = workers
        self.model_name, self.max_new_tokens = model_name, max_new_tokens
        self.revision, self.quantization, self.workers = revision, "nf4", workers
        os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
        self.db = sqlite3.connect(cache_path, timeout=2)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS generations (seed INTEGER PRIMARY KEY, question_hash TEXT NOT NULL, answer TEXT NOT NULL, text TEXT NOT NULL, latency_ms INTEGER NOT NULL)")
        identity = json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        existing = self.db.execute("SELECT config FROM meta WHERE id=1").fetchone()
        if existing is not None and existing[0] != identity:
            self.db.close()
            raise ValueError("O cache pertence a outra configuração ou revisão do modelo.")
        if existing is None:
            self.db.execute("INSERT INTO meta VALUES (1, ?)", (identity,))
            self.db.commit()
        self.connections, self.processes = [], []
        try:
            ctx = mp.get_context("spawn")
            # Carga sequencial evita picos simultâneos na mesma GPU.
            for _ in range(workers):
                parent, child = ctx.Pipe()
                self.connections.append(parent)
                try:
                    process = ctx.Process(target=_worker, args=(child, snapshot, max_new_tokens))
                    process.start()
                    self.processes.append(process)
                finally:
                    child.close()
                if not parent.poll(300):
                    raise TimeoutError("Tempo limite ao carregar modelo quantizado.")
                message = parent.recv()
                if "error" in message:
                    raise RuntimeError(message["error"])
                if not message.get("ready"):
                    raise RuntimeError("Falha ao carregar modelo quantizado.")
        except BaseException:
            self.close()
            raise

    def batch_sample(self, jobs, temperature, top_p):
        """Retorna resultados na ordem de entrada e confirma cada geração assim que chega."""
        answers, remaining = {}, []
        for question, seed in jobs:
            question_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()
            row = self.db.execute("SELECT question_hash, answer, text, latency_ms FROM generations WHERE seed=?", (seed,)).fetchone()
            if row:
                if row[0] != question_hash:
                    raise ValueError("Semente já associada a outra questão no cache.")
                answers[seed] = (json.loads(row[1]), row[2], row[3])
            else:
                remaining.append((question, seed, question_hash))
        active = {}
        while remaining or active:
            for conn in self.connections:
                if remaining and conn not in active:
                    question, seed, question_hash = remaining.pop(0)
                    conn.send({"question": question, "seed": seed, "temperature": temperature, "top_p": top_p})
                    active[conn] = (seed, question_hash)
            ready = wait(list(active), timeout=300)
            if not ready:
                raise TimeoutError("Tempo limite aguardando inferência.")
            for conn in ready:
                seed, question_hash = active.pop(conn)
                result = conn.recv()
                if "error" in result:
                    raise RuntimeError(result["error"])
                if result["seed"] != seed:
                    raise RuntimeError("Resposta recebida para outra semente.")
                value = (result["answer"], result["text"], result["latency_ms"])
                self.db.execute("INSERT INTO generations VALUES (?, ?, ?, ?, ?)",
                                (seed, question_hash, json.dumps(value[0]), value[1], value[2]))
                self.db.commit()
                answers[seed] = value
        return [answers[seed] for _question, seed in jobs]

    def close(self):
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self.cleanup_errors = []
        for conn in getattr(self, "connections", []):
            try:
                conn.send(None)
            except (OSError, EOFError):
                pass
        for process in getattr(self, "processes", []):
            try:
                process.join(5)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
                if process.is_alive():
                    self.cleanup_errors.append("Worker continuou ativo após kill.")
            except Exception as exc:
                self.cleanup_errors.append(f"{type(exc).__name__}: {exc}")
                try:
                    if process.is_alive():
                        process.kill()
                        process.join(5)
                except Exception as cleanup_exc:
                    self.cleanup_errors.append(f"{type(cleanup_exc).__name__}: {cleanup_exc}")
        for conn in getattr(self, "connections", []):
            try:
                conn.close()
            except Exception as exc:
                self.cleanup_errors.append(f"{type(exc).__name__}: {exc}")
        if getattr(self, "db", None) is not None:
            try:
                self.db.close()
            finally:
                self.db = None
