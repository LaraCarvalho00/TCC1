"""One resident model and one transactional generation cache owned by a node.

Only model files on disk may be shared. Model weights in CUDA, the process,
random seed and generated responses belong to this node and scenario.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time


class DedicatedModel:
    def __init__(self, *, node_id, run_id, model_name, cache_dir, quantization="nf4",
                 device="cuda", revision=None, max_new_tokens=256, temperature=.7,
                 top_p=.95, factory=None):
        if quantization != "nf4" or device != "cuda":
            raise ValueError("Dedicated inference requires NF4 on CUDA")
        self.node_id, self.run_id = node_id, run_id
        self.model_name, self.quantization, self.device = model_name, quantization, device
        self.max_new_tokens, self.temperature, self.top_p = max_new_tokens, temperature, top_p
        self.lock = threading.RLock()
        self.model = None
        self.factory = factory
        self.path = Path(cache_dir) / "inferencias.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        identity = {"run_id": run_id, "node_id": node_id, "model": model_name,
                    "revision": revision, "quantization": quantization, "device": device,
                    "max_new_tokens": max_new_tokens, "temperature": temperature, "top_p": top_p}
        self.config = json.dumps(identity, sort_keys=True, ensure_ascii=False)
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL)")
            existing = db.execute("SELECT config FROM meta WHERE id=1").fetchone()
            if existing is not None and existing[0] != self.config:
                raise ValueError("Node inference cache belongs to another node, scenario or model")
            db.execute("INSERT OR IGNORE INTO meta VALUES (1,?)", (self.config,))
            db.execute("CREATE TABLE IF NOT EXISTS generations (round_index INTEGER PRIMARY KEY, node_id TEXT NOT NULL, task_id TEXT NOT NULL, question_hash TEXT NOT NULL, seed INTEGER NOT NULL UNIQUE, answer TEXT NOT NULL, text TEXT NOT NULL, latency_ms INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS responses (round_index INTEGER PRIMARY KEY, answer TEXT NOT NULL, base_node TEXT NOT NULL)")
            db.commit()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA synchronous=FULL")
        return db

    def ensure_loaded(self):
        with self.lock:
            if self.model is None:
                if self.factory is None:
                    from .inference import ModelBackend
                    self.model = ModelBackend(self.model_name, device=self.device,
                                              max_new_tokens=self.max_new_tokens, quantization=self.quantization)
                else:
                    self.model = self.factory()
                if self.factory is None:
                    self._record_memory()
            return self.model

    def _record_memory(self):
        """Actual per-process CUDA use; planned slot capacity is only an estimate."""
        import torch
        data = {"node_id": self.node_id, "run_id": self.run_id,
                "device_name": torch.cuda.get_device_name(0),
                "allocated_bytes": torch.cuda.memory_allocated(0),
                "reserved_bytes": torch.cuda.memory_reserved(0),
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(0),
                "peak_reserved_bytes": torch.cuda.max_memory_reserved(0),
                "weights_bytes": self.model.model.get_memory_footprint()}
        destination = self.path.parent / "model-runtime.json"
        pending = destination.with_suffix(".tmp")
        pending.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        pending.replace(destination)

    @property
    def loaded(self):
        return self.model is not None

    def generate(self, *, round_index, task_id, question, seed):
        if isinstance(round_index, bool) or round_index < 0:
            raise ValueError("Invalid round index")
        digest = hashlib.sha256(question.encode("utf-8")).hexdigest()
        with self.lock, closing(self._connect()) as db:
            old = db.execute("SELECT node_id,task_id,question_hash,seed,answer,text,latency_ms FROM generations WHERE round_index=?", (round_index,)).fetchone()
            if old:
                if old[:4] != (self.node_id, task_id, digest, seed):
                    raise ValueError("Repeated node/round request contains conflicting task or seed")
                return {"answer": json.loads(old[4]), "text": old[5], "latency_ms": old[6]}
            model = self.ensure_loaded()
            started = time.perf_counter()
            answer, text = model.sample(question, temperature=self.temperature, top_p=self.top_p, seed=seed)
            latency = int((time.perf_counter() - started) * 1000)
            if self.factory is None:
                self._record_memory()
            db.execute("INSERT INTO generations VALUES (?,?,?,?,?,?,?,?)",
                       (round_index, self.node_id, task_id, digest, seed, json.dumps(answer), text, latency))
            db.commit()
            return {"answer": answer, "text": text, "latency_ms": latency}

    def record_response(self, round_index, answer, base_node):
        with self.lock, closing(self._connect()) as db:
            encoded = json.dumps(answer)
            old = db.execute("SELECT answer,base_node FROM responses WHERE round_index=?", (round_index,)).fetchone()
            if old and old != (encoded, base_node):
                raise ValueError("Repeated round produced a conflicting submitted response")
            db.execute("INSERT OR IGNORE INTO responses VALUES (?,?,?)", (round_index, encoded, base_node))
            db.commit()
