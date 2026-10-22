"""Etapa 5. Não altera ``sistema/scripts/test_model.py``.

Acurácia em 50 questões: o mesmo caminho de ``ModelBackend.solve`` (guloso).
As 5 amostras com temperatura 0,7 são uma chamada extra de ``generate``,
porque ``solve`` está fixo em ``do_sample=False`` (``sistema/node/inference.py:69-75``).

Uso, na raiz do repositório::

    .venv/bin/python entrega_a4/run_llm.py
"""
from __future__ import annotations

import os
import platform
import resource
import subprocess
import sys
import time
import traceback

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "entrega_a4", "05_llm.md")
MODEL = "HuggingFaceTB/SmolLM3-3B"
N_ACCURACY = 50
N_QUESTIONS = 10
N_SAMPLES = 5
TEMPERATURE = 0.7
SEED = 0


def _rss_gb() -> float:
    # No macOS, ru_maxrss vem em bytes.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 ** 3)


def _machine() -> str:
    lines = [f"- Python: {sys.version.split()[0]} ({sys.executable})", f"- Plataforma: {platform.platform()}"]
    for key, cmd in (
        ("CPU", ["sysctl", "-n", "machdep.cpu.brand_string"]),
        ("Núcleos", ["sysctl", "-n", "hw.ncpu"]),
        ("Memória (bytes)", ["sysctl", "-n", "hw.memsize"]),
    ):
        try:
            value = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        except Exception as exc:
            value = f"NÃO LIDO ({exc})"
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _generate(backend, question: str, *, sample: bool, seed: int | None):
    import torch
    from sistema.core.answer import extract_final_answer
    from sistema.node.inference import _build_prompt

    prompt = _build_prompt(backend.tokenizer, question)
    inputs = backend.tokenizer(prompt, return_tensors="pt").to(backend.device)
    if seed is not None:
        torch.manual_seed(seed)
    kwargs = dict(max_new_tokens=backend.max_new_tokens, pad_token_id=backend.tokenizer.eos_token_id)
    if sample:
        kwargs.update(do_sample=True, temperature=TEMPERATURE)
    else:
        kwargs.update(do_sample=False)
    started = time.perf_counter()
    with torch.no_grad():
        output = backend.model.generate(**inputs, **kwargs)
    elapsed = time.perf_counter() - started
    generated = output[0][inputs["input_ids"].shape[1]:]
    text = backend.tokenizer.decode(generated, skip_special_tokens=True)
    return extract_final_answer(text), text, elapsed


def _fmt(value, nd=3) -> str:
    return f"{value:.{nd}f}".replace(".", ",")


def main() -> None:
    from sistema.core.answer import normalize
    from sistema.core.dataset import load_gsm8k
    from sistema.node.inference import ModelBackend

    machine = _machine()
    lines = [
        "# Etapa 5 — teste da LLM",
        "",
        "Comando:",
        "",
        "```",
        f'cd "{ROOT}" && ".venv/bin/python" entrega_a4/run_llm.py',
        "```",
        "",
        "Modelo: `HuggingFaceTB/SmolLM3-3B`. Dataset: GSM8K `test`, via `sistema.core.dataset.load_gsm8k`.",
        "Acurácia: `ModelBackend` com `do_sample=False` e no máximo 256 tokens novos (`sistema/node/inference.py:69-75`).",
        f"Amostras: temperatura {str(TEMPERATURE).replace('.', ',')} , {N_SAMPLES} gerações por questão, semente inicial {SEED}.",
        "",
        "## Máquina",
        "",
        machine,
        "",
    ]
    try:
        print("Carregando GSM8K ...", flush=True)
        tasks = load_gsm8k(split="test", limit=N_ACCURACY)
        print(f"Carregando {MODEL} ...", flush=True)
        t_load = time.perf_counter()
        backend = ModelBackend(MODEL, max_new_tokens=256)
        load_s = time.perf_counter() - t_load
        lines += [
            "## Carga do modelo",
            "",
            f"- Dispositivo escolhido pelo código: `{backend.device}` (`sistema/node/inference.py:49-56`).",
            f"- Tempo de carga: {_fmt(load_s, 1)} s.",
            f"- RSS máximo do processo depois da carga: {_fmt(_rss_gb(), 2)} GB.",
            "",
            f"## Acurácia em {N_ACCURACY} questões (guloso)",
            "",
        ]
        correct = 0
        times = []
        for index, task in enumerate(tasks, start=1):
            predicted, _text, elapsed = _generate(backend, task["question"], sample=False, seed=None)
            expected = normalize(task["answer"])
            ok = predicted is not None and normalize(predicted) == expected
            correct += int(ok)
            times.append(elapsed)
            print(f"[{index}/{N_ACCURACY}] {'OK' if ok else 'ERR'} {elapsed:.1f}s esperado={expected} previsto={predicted}", flush=True)
        accuracy = correct / len(tasks)
        mean_t = sum(times) / len(times)
        lines += [
            f"- Acertos: {correct}/{len(tasks)}.",
            f"- Acurácia: {_fmt(accuracy * 100, 1)}%.",
            f"- Tempo médio por tarefa: {_fmt(mean_t, 2)} s (mínimo {_fmt(min(times), 2)} s, máximo {_fmt(max(times), 2)} s).",
            f"- Tempo total das {len(tasks)} tarefas: {_fmt(sum(times), 1)} s.",
            f"- RSS máximo depois dessa leva: {_fmt(_rss_gb(), 2)} GB.",
            "",
            "## Dez questões, cinco amostras, temperatura 0,7",
            "",
            "Resposta distinta = número extraído por `extract_final_answer` (`sistema/core/answer.py:18`). Também se conta o texto bruto, porque dois textos podem extrair o mesmo número.",
            "",
            "| Questão | Gabarito | Respostas extraídas | Distintas (número) | Distintas (texto) | Acertos nas 5 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        sample_hits = [0] * N_SAMPLES
        sample_times = []
        for q_index, task in enumerate(tasks[:N_QUESTIONS]):
            expected = normalize(task["answer"])
            answers = []
            texts = []
            hits = 0
            for sample_index in range(N_SAMPLES):
                predicted, text, elapsed = _generate(
                    backend, task["question"], sample=True, seed=SEED + q_index * N_SAMPLES + sample_index,
                )
                sample_times.append(elapsed)
                answers.append(predicted)
                texts.append(text)
                ok = predicted is not None and normalize(predicted) == expected
                hits += int(ok)
                sample_hits[sample_index] += int(ok)
            shown = ", ".join("—" if a is None else str(a) for a in answers)
            lines.append(
                f"| {q_index} | {expected} | {shown} | {len(set(answers))} | {len(set(texts))} | {hits}/{N_SAMPLES} |"
            )
            print(f"amostras q={q_index} distintas={len(set(answers))} acertos={hits}", flush=True)
        lines += [
            "",
            "Acurácia de cada amostra, nas 10 questões (amostra 0 é a primeira geração de cada questão):",
            "",
        ]
        for sample_index, hits in enumerate(sample_hits):
            lines.append(f"- Amostra {sample_index}: {hits}/{N_QUESTIONS} = {_fmt(100 * hits / N_QUESTIONS, 1)}%.")
        mean_sample = sum(sample_times) / len(sample_times)
        lines += [
            "",
            f"Tempo médio de uma geração com temperatura 0,7: {_fmt(mean_sample, 2)} s.",
            "",
            "## Estimativa de uma rodada com nós honestos",
            "",
            "O código de inferência faz uma geração por chamada, sem lote (`sistema/node/inference.py:69-75`). "
            f"Usando a média gulosa de {_fmt(mean_t, 2)} s por chamada, em sequência, nesta máquina, com o modelo já carregado:",
            "",
            "| Nós honestos chamando o modelo | Uma rodada | 50 rodadas |",
            "| --- | --- | --- |",
        ]
        for n in (10, 20, 50):
            lines.append(
                f"| {n} | {_fmt(n * mean_t / 60, 1)} min | {_fmt(50 * n * mean_t / 3600, 2)} h |"
            )
        lines += [
            "",
            f"O script `sistema/scripts/run_com_smol.py:1-8` não faz isso: gera uma vez por pergunta e todos os honestos reutilizam a resposta. "
            f"Nesse caminho, 50 rodadas com as 10 tarefas da amostra seriam cerca de {10} gerações, {_fmt(10 * mean_t / 60, 1)} min, qualquer que seja o número de nós.",
            "",
            f"RSS máximo ao fim: {_fmt(_rss_gb(), 2)} GB. Uma segunda cópia do modelo de 3B em float16 não foi carregada; 50 processos simultâneos não caberiam nessa conta.",
            "",
        ]
    except Exception:
        err = traceback.format_exc()
        lines += [
            "## Falha",
            "",
            "Não foi possível completar o teste do modelo.",
            "",
            "```",
            err.rstrip(),
            "```",
            "",
        ]
        print(err, flush=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    print(f"escrito {OUT}", flush=True)


if __name__ == "__main__":
    main()
