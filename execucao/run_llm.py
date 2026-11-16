"""Etapa 5: avaliação opcional da LLM.

Acurácia em 50 questões: o mesmo caminho de ``ModelBackend.solve`` (guloso).
As 5 amostras com temperatura 0,7 são uma chamada extra de ``generate``,
porque ``solve`` está fixo em ``do_sample=False`` (``sistema/node/inference.py:69-75``).

Uso, na raiz do repositório::

    python execucao/run_llm.py --saida resultados/experimentos/05_llm.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shlex
import subprocess
import sys
import time
import traceback

try:
    import resource
except ImportError:  # Windows não possui o módulo resource.
    resource = None

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "resultados", "experimentos", "05_llm.md")
MODEL = "HuggingFaceTB/SmolLM3-3B"
N_ACCURACY = 50
N_QUESTIONS = 10
N_SAMPLES = 5
TEMPERATURE = 0.7
SEED = 0


def _windows_peak_rss_bytes() -> int:
    """Pico de memória residente (working set) do processo no Windows."""
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counters.PeakWorkingSetSize


def _rss_gb() -> float | None:
    """Pico de RSS em GiB, ou None quando indisponível na plataforma."""
    try:
        if sys.platform == "win32":
            value = _windows_peak_rss_bytes()
        elif resource is not None and sys.platform in ("darwin", "linux"):
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # macOS informa bytes; Linux informa KiB.
            value = peak if sys.platform == "darwin" else peak * 1024
        else:
            return None
        return value / (1024 ** 3)
    except (OSError, AttributeError):
        return None


def _format_rss() -> str:
    value = _rss_gb()
    return "indisponível" if value is None else f"{_fmt(value, 2)} GiB"


def _windows_physical_memory_bytes() -> int:
    import ctypes
    from ctypes import wintypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
    kernel32.GlobalMemoryStatusEx.restype = wintypes.BOOL
    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ctypes.WinError(ctypes.get_last_error())
    return status.ullTotalPhys


def _machine() -> str:
    lines = [f"- Python: {sys.version.split()[0]} ({sys.executable})", f"- Plataforma: {platform.platform()}"]
    cpu = platform.processor() or "não identificado"
    memory = None
    if sys.platform == "darwin":
        try:
            memory = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], stderr=subprocess.DEVNULL).decode().strip())
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    elif sys.platform.startswith("linux"):
        try:
            memory = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError, AttributeError):
            pass
    elif sys.platform == "win32":
        try:
            memory = _windows_physical_memory_bytes()
        except (OSError, AttributeError):
            pass
    lines.extend([
        f"- CPU: {cpu}",
        f"- Núcleos lógicos: {os.cpu_count() or 'não identificado'}",
        f"- Memória física (bytes): {memory if memory is not None else 'não disponível'}",
    ])
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


def _load_bank_tasks(path: str, limit: int) -> tuple[list[dict], str]:
    """Lê apenas questões e gabaritos: nenhuma resposta gerada é reutilizada."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Não foi possível ler o banco de questões: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("tarefas"), list) or len(data["tarefas"]) < limit:
        raise ValueError(f"O banco deve conter pelo menos {limit} questões em 'tarefas'.")
    tasks = []
    seen = set()
    for item in data["tarefas"][:limit]:
        if not isinstance(item, dict):
            raise ValueError("Cada questão deve ser um objeto com id, question e answer.")
        task_id, question, answer = item.get("id"), item.get("question"), item.get("answer")
        if not isinstance(task_id, str) or not task_id.strip() or task_id in seen:
            raise ValueError("Cada questão deve ter um id textual único e não vazio.")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Enunciado ausente para {task_id}.")
        if type(answer) not in (int, float) or not math.isfinite(answer):
            raise ValueError(f"Gabarito numérico inválido para {task_id}.")
        seen.add(task_id)
        tasks.append({"id": task_id, "question": question, "answer": answer})
    return tasks, hashlib.sha256(raw).hexdigest()


def _write_progress(handle, *, task, question_index, mode, sample_index, predicted, expected, correct, elapsed):
    """Registra apenas identificadores e métricas; não salva enunciados ou texto do modelo."""
    if handle is None:
        return
    entry = {
        "id_questao": task.get("id", f"questao-{question_index}"),
        "questao": question_index,
        "modo": mode,
        "amostra": sample_index,
        "previsto": predicted,
        "esperado": expected,
        "correto": bool(correct),
        "duracao_segundos": elapsed,
    }
    handle.write(json.dumps(entry, ensure_ascii=False, allow_nan=False) + "\n")
    handle.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Executa a avaliação opcional da LLM da etapa 5.")
    parser.add_argument("--saida", default=OUT, help="Caminho do relatório Markdown gerado.")
    parser.add_argument("--sobrescrever", action="store_true", help="Permite substituir um relatório existente.")
    parser.add_argument("--banco-tarefas", help="JSON local: usa apenas as questões e os gabaritos, sem reutilizar respostas.")
    parser.add_argument("--progresso", help="Arquivo JSONL novo com uma linha por inferência concluída.")
    args = parser.parse_args(argv)
    output = os.path.abspath(os.path.expanduser(args.saida))
    bank = os.path.abspath(os.path.expanduser(args.banco_tarefas)) if args.banco_tarefas else None
    progress = os.path.abspath(os.path.expanduser(args.progresso)) if args.progresso else None
    from pathlib import Path
    resolved = lambda path: os.path.normcase(str(Path(path).resolve()))
    targets = [resolved(path) for path in (output, bank, progress) if path]
    if len(targets) != len(set(targets)):
        parser.error("relatório, banco e progresso devem ser arquivos diferentes")
    if os.path.lexists(output) and not args.sobrescrever:
        parser.error(f"o relatório já existe: {output}; use --sobrescrever para substituí-lo")
    if os.path.isdir(output):
        parser.error(f"a saída deve ser um arquivo, não uma pasta: {output}")
    if progress and os.path.lexists(progress):
        parser.error(f"o arquivo de progresso já existe: {progress}")
    tasks_from_bank, bank_sha = None, None
    if bank:
        try:
            tasks_from_bank, bank_sha = _load_bank_tasks(bank, N_ACCURACY)
        except ValueError as exc:
            parser.error(str(exc))
    os.makedirs(os.path.dirname(output), exist_ok=True)

    from sistema.core.answer import normalize
    from sistema.core.dataset import load_gsm8k
    from sistema.node.inference import ModelBackend

    machine = _machine()
    command_args = [sys.executable, "execucao/run_llm.py", "--saida", output]
    if bank:
        command_args.extend(["--banco-tarefas", bank])
    if progress:
        command_args.extend(["--progresso", progress])
    if args.sobrescrever:
        command_args.append("--sobrescrever")
    command = subprocess.list2cmdline(command_args) if os.name == "nt" else shlex.join(command_args)
    lines = [
        "# Etapa 5 — teste da LLM",
        "",
        "Comando:",
        "",
        "```",
        command,
        "```",
        "",
        "Modelo: `HuggingFaceTB/SmolLM3-3B`.",
        (f"Questões e gabaritos: banco local `{bank}` (SHA-256 `{bank_sha}`). "
         "As respostas pré-geradas do banco não foram reutilizadas; o modelo executa cada inferência."
         if bank else "Dataset: GSM8K `test`, via `sistema.core.dataset.load_gsm8k`."),
        "Acurácia: `ModelBackend` com `do_sample=False` e no máximo 256 tokens novos (`sistema/node/inference.py:69-75`).",
        f"Amostras: temperatura {str(TEMPERATURE).replace('.', ',')} , {N_SAMPLES} gerações por questão, semente inicial {SEED}.",
        "",
        "## Máquina",
        "",
        machine,
        "",
    ]
    exit_code = 0
    progress_handle = None
    try:
        if progress:
            os.makedirs(os.path.dirname(progress), exist_ok=True)
            progress_handle = open(progress, "x", encoding="utf-8", newline="\n")
            lines.extend([f"Progresso incremental: `{progress}` (identificadores, respostas e métricas; sem enunciados ou textos gerados).", ""])
        if tasks_from_bank is not None:
            print(f"Carregadas {len(tasks_from_bank)} questões do banco local.", flush=True)
            tasks = tasks_from_bank
        else:
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
            f"- RSS máximo do processo depois da carga: {_format_rss()}.",
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
            _write_progress(progress_handle, task=task, question_index=index, mode="gulosa", sample_index=None,
                            predicted=predicted, expected=expected, correct=ok, elapsed=elapsed)
            print(f"[{index}/{N_ACCURACY}] {'OK' if ok else 'ERR'} {elapsed:.1f}s esperado={expected} previsto={predicted}", flush=True)
        accuracy = correct / len(tasks)
        mean_t = sum(times) / len(times)
        lines += [
            f"- Acertos: {correct}/{len(tasks)}.",
            f"- Acurácia: {_fmt(accuracy * 100, 1)}%.",
            f"- Tempo médio por tarefa: {_fmt(mean_t, 2)} s (mínimo {_fmt(min(times), 2)} s, máximo {_fmt(max(times), 2)} s).",
            f"- Tempo total das {len(tasks)} tarefas: {_fmt(sum(times), 1)} s.",
            f"- RSS máximo depois dessa leva: {_format_rss()}.",
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
                _write_progress(progress_handle, task=task, question_index=q_index + 1, mode="amostragem",
                                sample_index=sample_index + 1, predicted=predicted, expected=expected,
                                correct=ok, elapsed=elapsed)
            shown = ", ".join("—" if a is None else str(a) for a in answers)
            lines.append(
                f"| {q_index + 1} | {expected} | {shown} | {len(set(answers))} | {len(set(texts))} | {hits}/{N_SAMPLES} |"
            )
            print(f"amostras q={q_index + 1} distintas={len(set(answers))} acertos={hits}", flush=True)
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
            f"Na alternativa de reutilização, gera-se uma vez por pergunta e todos os honestos reutilizam a resposta. "
            f"Nesse caminho, 50 rodadas com as 10 tarefas da amostra seriam cerca de {10} gerações, {_fmt(10 * mean_t / 60, 1)} min, qualquer que seja o número de nós.",
            "",
            f"RSS máximo ao fim: {_format_rss()}. Uma segunda cópia do modelo de 3B em float16 não foi carregada; a capacidade para 50 processos simultâneos não foi medida.",
            "",
        ]
    except Exception:
        exit_code = 1
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
    finally:
        if progress_handle is not None:
            progress_handle.close()
    try:
        # O modo exclusivo também protege contra criação concorrente durante a inferência.
        with open(output, "w" if args.sobrescrever else "x", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
    except OSError as exc:
        print(f"Não foi possível salvar o relatório em {output}: {exc}", file=sys.stderr, flush=True)
        return 1
    print(f"escrito {output}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
