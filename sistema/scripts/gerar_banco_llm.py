"""Gera o banco de respostas do SmolLM3-3B para os experimentos com LLM.

Para cada uma das N primeiras questões do GSM8K (split ``test``), o modelo
gera S respostas com amostragem (temperatura 0,7, top-p 0,95) e uma resposta
gulosa de referência. Na simulação, cada nó honesto sorteia uma dessas S
respostas a cada rodada, de modo que a resposta vem de inferência real e
nós honestos podem discordar entre si.

O arquivo é salvo a cada questão: se a execução parar, rodar de novo continua
de onde parou.

Uso (na raiz do repositório)::

    python -m sistema.scripts.gerar_banco_llm --questoes 50 --amostras 20 \\
        --saida sistema/resultados/banco_llm/banco_smol.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import time

from sistema.core.answer import normalize
from sistema.core.dataset import load_gsm8k
from sistema.node.inference import ModelBackend


def _parse(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--modelo", default="HuggingFaceTB/SmolLM3-3B")
    p.add_argument("--questoes", type=int, default=50)
    p.add_argument("--amostras", type=int, default=20)
    p.add_argument("--temperatura", type=float, default=0.7)
    p.add_argument("--top-p", type=float, default=0.95, dest="top_p")
    p.add_argument("--max-tokens", type=int, default=256, dest="max_tokens")
    p.add_argument("--semente", type=int, default=0)
    p.add_argument("--saida", default=os.path.join("sistema", "resultados", "banco_llm", "banco_smol.json"))
    return p.parse_args(argv)


def _carregar(path: str, args: argparse.Namespace) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as h:
            banco = json.load(h)
        params = banco["parametros"]
        for chave in ("modelo", "temperatura", "top_p", "max_tokens", "semente"):
            if params[chave] != getattr(args, chave):
                raise SystemExit(f"O arquivo existente usa {chave}={params[chave]!r}; apague-o ou use --saida diferente.")
        return banco
    return {
        "parametros": {
            "modelo": args.modelo, "temperatura": args.temperatura, "top_p": args.top_p,
            "max_tokens": args.max_tokens, "semente": args.semente, "amostras": args.amostras,
            "split": "test", "maquina": platform.platform(),
        },
        "tarefas": [],
    }


def _salvar(path: str, banco: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as h:
        json.dump(banco, h, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def main(argv=None) -> None:
    args = _parse(argv)
    os.makedirs(os.path.dirname(args.saida) or ".", exist_ok=True)
    banco = _carregar(args.saida, args)
    feitas = {t["id"] for t in banco["tarefas"]}
    tarefas = load_gsm8k(split="test", limit=args.questoes)

    print(f"Carregando {args.modelo} ...", flush=True)
    backend = ModelBackend(args.modelo, max_new_tokens=args.max_tokens)
    banco["parametros"]["dispositivo"] = backend.device
    inicio = time.perf_counter()

    for q, tarefa in enumerate(tarefas):
        if tarefa["id"] in feitas:
            continue
        esperado = normalize(tarefa["answer"])
        t0 = time.perf_counter()
        gulosa = normalize(backend.solve(tarefa["question"]))
        amostras = []
        for j in range(args.amostras):
            resposta, texto = backend.sample(
                tarefa["question"], temperature=args.temperatura, top_p=args.top_p,
                seed=args.semente * 1_000_000 + q * 1000 + j,
            )
            amostras.append({"resposta": normalize(resposta), "texto": texto})
        acertos = sum(1 for a in amostras if a["resposta"] is not None and a["resposta"] == esperado)
        banco["tarefas"].append({
            "id": tarefa["id"], "question": tarefa["question"], "answer": esperado,
            "gulosa": gulosa, "amostras": amostras, "segundos": round(time.perf_counter() - t0, 1),
        })
        _salvar(args.saida, banco)
        decorrido = time.perf_counter() - inicio
        print(f"[{len(banco['tarefas'])}/{len(tarefas)}] {tarefa['id']} gabarito={esperado} "
              f"gulosa={gulosa} acertos={acertos}/{args.amostras} ({decorrido / 60:.1f} min)", flush=True)

    total = sum(len(t["amostras"]) for t in banco["tarefas"])
    certas = sum(1 for t in banco["tarefas"] for a in t["amostras"]
                 if a["resposta"] is not None and a["resposta"] == t["answer"])
    print(f"Banco: {len(banco['tarefas'])} questões, {total} amostras, acurácia das amostras "
          f"{certas / max(total, 1):.1%}. Arquivo: {args.saida}", flush=True)


if __name__ == "__main__":
    main()
