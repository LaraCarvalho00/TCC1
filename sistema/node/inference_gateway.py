"""Gateway HTTP de uma a cinco instâncias NF4 para nós em contêineres.

Uma instância do gateway atende exatamente uma execução. Cada requisição é
identificada por rodada e nó, e as gerações são confirmadas no cache SQLite do
pool. Uma chamada repetida retorna o resultado já registrado.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
import os
from pathlib import Path
import queue
import threading

from .inference_pool import InferencePool, validate_workers


class RequestError(ValueError):
    pass


class Dispatcher:
    """Serializa o SQLite e mantém os workers configurados ocupados."""

    def __init__(self, factory, run_id, tasks, temperature, top_p, workers=2):
        self.workers = validate_workers(workers)
        self.model_instances = 0
        self.factory, self.run_id, self.tasks = factory, run_id, tasks
        self.temperature, self.top_p = temperature, top_p
        self.jobs = queue.Queue()
        self.ready = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.ready.wait()
        if self.error:
            raise RuntimeError("Falha ao iniciar gateway") from self.error

    def validate(self, value):
        if not isinstance(value, dict):
            raise RequestError("O corpo deve ser um objeto JSON.")
        for name in ("run_id", "node_id", "task_id", "question", "profile"):
            if not isinstance(value.get(name), str) or not value[name]:
                raise RequestError(f"Campo obrigatório inválido: {name}.")
        if value["run_id"] != self.run_id:
            raise RequestError("Identificador de execução divergente.")
        if value["profile"] not in ("honest", "malicious"):
            raise RequestError("Perfil inválido.")
        for name in ("round_index", "seed"):
            if isinstance(value.get(name), bool) or not isinstance(value.get(name), int) or not 0 <= value[name] < (1 << 63):
                raise RequestError(f"Campo obrigatório inválido: {name}.")
        if self.tasks.get(value["task_id"]) != value["question"]:
            raise RequestError("Tarefa ou enunciado diverge do banco configurado.")
        return {name: value[name] for name in ("run_id", "node_id", "round_index", "task_id", "question", "profile", "seed")}

    def submit(self, value):
        value = self.validate(value)
        if self.error is not None or not self.thread.is_alive():
            raise RuntimeError("O processo de atendimento do gateway terminou.") from self.error
        done = threading.Event()
        job = {"value": value, "done": done}
        self.jobs.put(job)
        # Modelo e cache fazem suas próprias validações de timeout; a fila pode
        # precisar atender dezenas de nós antes deste pedido.
        while not done.wait(1):
            if not self.thread.is_alive():
                raise RuntimeError("O processo de atendimento do gateway terminou.") from self.error
        if "error" in job:
            raise job["error"]
        return job["result"]

    def _run(self):
        pool = None
        try:
            pool = self.factory()
            actual_workers = validate_workers(getattr(pool, "workers", self.workers))
            if actual_workers != self.workers:
                raise ValueError("Quantidade de workers do pool diverge do gateway.")
            self.model_instances = actual_workers
            pool.db.execute("CREATE TABLE IF NOT EXISTS gateway_requests (round_index INTEGER NOT NULL, node_id TEXT NOT NULL, task_id TEXT NOT NULL, profile TEXT NOT NULL, seed INTEGER NOT NULL UNIQUE, question_hash TEXT NOT NULL, PRIMARY KEY (round_index, node_id))")
            pool.db.commit()
            self.ready.set()
            while True:
                first = self.jobs.get()
                if first is None:
                    return
                pending = [first]
                while len(pending) < self.workers:
                    try:
                        following = self.jobs.get(timeout=0.05)
                        pending.append(following)
                        if following is None:
                            break
                    except queue.Empty:
                        break
                stop = None in pending
                pending = [job for job in pending if job is not None]
                valid = []
                for job in pending:
                    value = job["value"]
                    digest = hashlib.sha256(value["question"].encode("utf-8")).hexdigest()
                    row = (value["round_index"], value["node_id"], value["task_id"], value["profile"], value["seed"], digest)
                    existing = pool.db.execute("SELECT round_index,node_id,task_id,profile,seed,question_hash FROM gateway_requests WHERE round_index=? AND node_id=?", row[:2]).fetchone()
                    try:
                        if existing is not None and existing != row:
                            raise RequestError("Pedido repetido com dados diferentes.")
                        if existing is None:
                            pool.db.execute("INSERT INTO gateway_requests VALUES (?,?,?,?,?,?)", row)
                            pool.db.commit()
                        valid.append(job)
                    except Exception as exc:
                        # Colisão de seed entre identidades também deve ser rejeitada.
                        job["error"] = RequestError(str(exc))
                        job["done"].set()
                # Pedido simultâneo repetido deve gerar uma única vez.
                unique = {}
                for job in valid:
                    unique.setdefault(job["value"]["seed"], job["value"])
                if unique:
                    try:
                        generated = pool.batch_sample([(v["question"], v["seed"]) for v in unique.values()], self.temperature, self.top_p)
                        outputs = dict(zip(unique, generated))
                        for job in valid:
                            answer, text, latency = outputs[job["value"]["seed"]]
                            job["result"] = {"answer": answer, "text": text, "latency_ms": latency}
                            job["done"].set()
                    except Exception as exc:
                        for job in valid:
                            job["error"] = exc
                            job["done"].set()
                        # A worker failure can leave other pipe replies pending.
                        # Stop this pool; a new gateway resumes confirmed cache rows.
                        raise
                if stop:
                    return
        except BaseException as exc:
            self.error = exc
            self.ready.set()
            while True:
                try:
                    job = self.jobs.get_nowait()
                except queue.Empty:
                    break
                if job is not None:
                    job["error"] = exc
                    job["done"].set()
        finally:
            try:
                if pool is not None:
                    pool.close()
            finally:
                self.model_instances = 0

    def close(self):
        self.jobs.put(None)
        self.thread.join()


def handler_for(dispatcher, control_token=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send_json(self, status, content):
            body = json.dumps(content, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                ready = dispatcher.error is None and dispatcher.thread.is_alive()
                return self.send_json(200 if ready else 503,
                                      {"status": "ready" if ready else "error", "run_id": dispatcher.run_id,
                                       "workers": dispatcher.workers,
                                       "model_instances": dispatcher.model_instances})
            return self.send_json(404, {"error": "Rota desconhecida."})

        def do_POST(self):
            if self.path == "/shutdown":
                provided = self.headers.get("Authorization", "")
                if not control_token or not hmac.compare_digest(provided, "Bearer " + control_token):
                    return self.send_json(403, {"error": "Acesso negado."})
                self.send_json(200, {"status": "stopping"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if self.path not in ("/infer", "/inference"):
                return self.send_json(404, {"error": "Rota desconhecida."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024 * 1024:
                    raise RequestError("Tamanho do corpo inválido.")
                value = json.loads(self.rfile.read(length))
                result = dispatcher.submit(value)
                return self.send_json(200, result)
            except (RequestError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                return self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                return self.send_json(500, {"error": str(exc)})
    return Handler


def resolve_model_snapshot(model_name, snapshot_path=None, revision=None):
    """Resolve only local files, including explicitly pinned manual snapshots."""
    if snapshot_path:
        snapshot = Path(snapshot_path).resolve()
        if not snapshot.is_dir():
            raise ValueError("O snapshot local do modelo não existe.")
        if revision is not None and snapshot.name != revision:
            raise ValueError("A revisão informada diverge do nome do snapshot local.")
        return str(snapshot), snapshot.name
    from huggingface_hub import snapshot_download
    options = {"local_files_only": True}
    if revision is not None:
        options["revision"] = revision
    snapshot = snapshot_download(model_name, **options)
    return snapshot, Path(snapshot).name


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gateway NF4 com uma a cinco instâncias e cache por execução")
    parser.add_argument("--model", default="HuggingFaceTB/SmolLM3-3B")
    parser.add_argument("--model-snapshot", help="Snapshot local já disponível; não acessa a rede.")
    parser.add_argument("--model-revision", help="Revisão fixada; deve corresponder ao nome do snapshot informado.")
    parser.add_argument("--workers", type=int, choices=range(1, 6), default=2)
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args(argv)
    if not 0 < args.temperature or not 0 < args.top_p <= 1 or args.max_new_tokens <= 0:
        parser.error("Parâmetros de geração inválidos.")
    raw = Path(args.tasks).read_bytes()
    data = json.loads(raw)
    tasks = {item["id"]: item["question"] for item in data["tarefas"]}
    if len(tasks) != len(data["tarefas"]):
        raise ValueError("O banco de tarefas contém IDs duplicados.")
    snapshot, revision = resolve_model_snapshot(args.model, args.model_snapshot, args.model_revision)
    source_digest = hashlib.sha256()
    for source in (Path(__file__), Path(__file__).with_name("inference_pool.py"), Path(__file__).with_name("inference.py")):
        source_digest.update(source.read_bytes())
    config = {"run_id": args.run_id, "model": args.model, "model_revision": revision,
              "tasks_sha256": hashlib.sha256(raw).hexdigest(), "temperature": args.temperature,
              "top_p": args.top_p, "max_new_tokens": args.max_new_tokens, "quantization": "nf4",
              "workers": args.workers, "source_sha256": source_digest.hexdigest(), "torch": version("torch"),
              "transformers": version("transformers"), "bitsandbytes": version("bitsandbytes")}
    factory = lambda: InferencePool(args.model, snapshot, revision, args.max_new_tokens, args.workers, args.cache, config)
    dispatcher = Dispatcher(factory, args.run_id, tasks, args.temperature, args.top_p, workers=args.workers)
    # Apenas o processo que conhece o token pode encerrar o gateway. A opção
    # permanece desabilitada quando a variável não é fornecida.
    control_token = os.environ.get("INFERENCE_GATEWAY_CONTROL_TOKEN")
    server = None
    try:
        server = ThreadingHTTPServer((args.host, args.port), handler_for(dispatcher, control_token))
        print(f"Gateway pronto: {args.host}:{args.port} (execução {args.run_id}, {args.workers} instâncias NF4)", flush=True)
        server.serve_forever()
    finally:
        if server is not None:
            server.server_close()
        dispatcher.close()


if __name__ == "__main__":
    main()
