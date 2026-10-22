"""Backends de inferência dos nós.

* ``MockBackend``: reproduz o comportamento do perfil sem executar o modelo
  (rápido, para validar containers e comunicação assíncrona).
* ``ModelBackend``: executa um modelo de linguagem (ex.: SmolLM3-3B) via
  Hugging Face ``transformers`` para resolver a tarefa GSM8K de fato.
"""

from __future__ import annotations

import random
from typing import Optional

from ..core import behavior
from ..core.answer import Answer, extract_final_answer

_PROMPT_TEMPLATE = (
    "Solve the following math word problem. "
    "Show brief reasoning and end with the final numeric answer after '####'.\n\n"
    "Question: {question}\nAnswer:"
)


class MockBackend:
    """Gera respostas simuladas por perfil (usa o gabarito recebido na tarefa)."""

    def __init__(self, config: behavior.BehaviorConfig, rng: random.Random) -> None:
        self.config = config
        self.rng = rng

    def solve(self, profile: str, question: str, expected: Optional[Answer]) -> tuple[Optional[Answer], int]:
        return behavior.simulate_answer(profile, expected, self.config, self.rng)


class ModelBackend:
    """Resolve a tarefa executando um modelo de linguagem causal."""

    def __init__(
        self,
        model_name: str,
        device: Optional[str] = None,
        max_new_tokens: int = 256,
    ) -> None:
        from transformers import AutoModelForCausalLM, AutoTokenizer  # import tardio
        import torch

        self.model_name = model_name
        self.max_new_tokens = max_new_tokens
        if device:
            self.device = device
        elif torch.cuda.is_available():
            self.device = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"
        dtype = torch.float16 if self.device in ("cuda", "mps") else torch.float32
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=dtype,
        ).to(self.device)

    def solve(self, question: str) -> Optional[Answer]:
        import torch

        prompt = _build_prompt(self.tokenizer, question)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        generated = output[0][inputs["input_ids"].shape[1]:]
        text = self.tokenizer.decode(generated, skip_special_tokens=True)
        return extract_final_answer(text)


def _build_prompt(tokenizer, question: str) -> str:
    """Usa o chat template do tokenizer quando disponível."""
    content = _PROMPT_TEMPLATE.format(question=question)
    chat_template = getattr(tokenizer, "chat_template", None)
    if chat_template:
        messages = [{"role": "user", "content": content}]
        try:
            return tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except TypeError:
            return tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
    return content
