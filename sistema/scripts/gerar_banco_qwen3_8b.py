"""Gera o banco 50×20 do Qwen3-8B e grava cada amostra assim que termina.

A sondagem ``--limite 50`` mede o ritmo antes de comprometer as 1000.
O JSON em ``sistema/dados`` só é escrito quando as 1000 existem; até lá o
parcial fica em ``resultados/llm``. Retoma amostras já gravadas no jsonl.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from sistema.core.answer import normalize
from sistema.scripts.piloto_qwen3_8b import MODEL, LOCAL_MODEL, ensure_model, gateway_seed
from sistema.scripts.piloto_local import gpu, save

ROOT = Path(__file__).resolve().parents[2]
TAREFAS = ROOT / "sistema" / "dados" / "banco_smol.json"
DADOS = ROOT / "sistema" / "dados" / "banco_qwen3_8b.json"
AMOSTRAS = 20
QUESTOES = 50


def _atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    last = None
    for attempt in range(8):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(0.05 * (attempt + 1))
    if last is not None:
        raise last
    save(path, payload)


def _checkpoint(path: Path, payload: dict) -> None:
    """Manifesto/parcial não pode abortar depois que a amostra já está no jsonl."""
    try:
        _atomic(path, payload)
    except OSError as exc:
        print(f"aviso checkpoint {path.name}: {exc}", flush=True)


def plano(tarefas: list[dict]) -> list[tuple[int, int, dict]]:
    return [(qi, si, tarefas[qi]) for qi in range(len(tarefas)) for si in range(AMOSTRAS)]


def carregar_feitos(jsonl: Path) -> dict[tuple[int, int], dict]:
    feitos = {}
    if not jsonl.is_file():
        return feitos
    with jsonl.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            feitos[(int(item["questao"]), int(item["amostra"]))] = item
    return feitos


def montar_banco(tarefas: list[dict], feitos: dict[tuple[int, int], dict], parametros: dict) -> dict:
    saida = []
    for qi, task in enumerate(tarefas):
        amostras = []
        for si in range(AMOSTRAS):
            item = feitos.get((qi, si))
            if item is None:
                continue
            amostras.append({"resposta": item["resposta"], "texto": item["texto"]})
        saida.append({
            "id": task["id"],
            "question": task["question"],
            "answer": task["answer"],
            "amostras": amostras,
        })
    return {"parametros": parametros, "tarefas": saida}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--limite", type=int, default=0, help="0 = 1000 amostras; 50 = sondagem")
    args = parser.parse_args(argv)
    saida = args.saida.resolve()
    saida.mkdir(parents=True, exist_ok=True)
    bruto = json.loads(TAREFAS.read_text(encoding="utf-8"))
    tarefas = bruto["tarefas"][:QUESTOES]
    if len(tarefas) != QUESTOES:
        raise ValueError("O arquivo de tarefas precisa de 50 questões")
    jobs = plano(tarefas)
    limite = len(jobs) if args.limite <= 0 else min(args.limite, len(jobs))
    jsonl = saida / "amostras.jsonl"
    manifesto_path = saida / "manifesto.json"
    snapshot_path = saida / "banco_parcial.json"
    feitos = carregar_feitos(jsonl)
    parametros = {
        "modelo": MODEL,
        "quantizacao": "nf4",
        "temperatura": 0.7,
        "top_p": 0.95,
        "max_tokens": 256,
        "semente": 0,
        "amostras": AMOSTRAS,
        "split": "test",
        "thinking": False,
        "semente_formula": "0:{indice_questao}:sample-{indice_amostra}",
    }
    manifesto = {
        "status": "em_andamento",
        "inicio_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "banco_qwen3_8b",
        "modelo": MODEL,
        "planejadas": limite,
        "total_banco": len(jobs),
        "ja_gravadas": len(feitos),
        "tarefas_sha256": hashlib.sha256(TAREFAS.read_bytes()).hexdigest(),
        "gpu_antes": gpu(),
        "parametros": parametros,
    }
    _atomic(manifesto_path, manifesto)
    snapshot = ensure_model()
    from sistema.node.inference import ModelBackend
    carga = time.perf_counter()
    backend = ModelBackend(str(snapshot), device="cuda", max_new_tokens=256, quantization="nf4")
    manifesto["carga_s"] = time.perf_counter() - carga
    manifesto["gpu_depois_carga"] = gpu()
    _atomic(manifesto_path, manifesto)
    print(f"MODELO_PRONTO {manifesto['carga_s']:.1f}s", flush=True)
    inicio = time.perf_counter()
    geradas = 0
    latencias = []
    with jsonl.open("a", encoding="utf-8") as stream:
        for qi, si, task in jobs:
            if geradas >= limite:
                break
            chave = (qi, si)
            if chave in feitos:
                continue
            seed = gateway_seed(0, qi, f"sample-{si}")
            t0 = time.perf_counter()
            answer, text = backend.sample(
                task["question"], temperature=0.7, top_p=0.95, seed=seed,
            )
            dt = time.perf_counter() - t0
            item = {
                "questao": qi,
                "amostra": si,
                "id": task["id"],
                "semente": seed,
                "resposta": normalize(answer),
                "texto": text,
                "correta": int(normalize(answer) == normalize(task["answer"])),
                "model_s": dt,
            }
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
            stream.flush()
            feitos[chave] = item
            geradas += 1
            latencias.append(dt)
            manifesto["ja_gravadas"] = len(feitos)
            manifesto["geradas_nesta_sessao"] = geradas
            manifesto["media_s"] = sum(latencias) / len(latencias)
            manifesto["elapsed_s"] = time.perf_counter() - inicio
            if geradas == 1 or geradas % 10 == 0:
                _checkpoint(snapshot_path, montar_banco(tarefas, feitos, parametros))
                _checkpoint(manifesto_path, manifesto)
            print(
                f"{len(feitos)}/{len(jobs)} q{qi} a{si} {dt:.1f}s "
                f"ok={item['correta']} media={manifesto['media_s']:.1f}s",
                flush=True,
            )
    elapsed = time.perf_counter() - inicio
    media = (sum(latencias) / len(latencias)) if latencias else None
    faltam = len(jobs) - len(feitos)
    proj = None if media is None else faltam * media
    manifesto.update({
        "status": "sondagem" if len(feitos) < len(jobs) else "concluido",
        "fim_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": elapsed,
        "media_s": media,
        "faltam": faltam,
        "projecao_restante_s": proj,
        "gpu_fim": gpu(),
    })
    _atomic(manifesto_path, manifesto)
    banco = montar_banco(tarefas, feitos, parametros)
    _atomic(snapshot_path, banco)
    if len(feitos) == len(jobs) and all(len(t["amostras"]) == AMOSTRAS for t in banco["tarefas"]):
        _atomic(DADOS, banco)
        print(f"BANCO {DADOS}", flush=True)
    print(
        f"SONDAGEM geradas={geradas} gravadas={len(feitos)}/{len(jobs)} "
        f"elapsed={elapsed:.1f}s media={media:.1f}s "
        f"faltam={faltam} proj_restante_h={(proj or 0)/3600:.2f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
