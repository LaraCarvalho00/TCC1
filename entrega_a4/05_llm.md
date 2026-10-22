# Etapa 5 — teste da LLM

Comando:

```
cd "/Users/gabrielferraz/Desktop/Tcc Lara" && ".venv/bin/python" entrega_a4/run_llm.py
```

Modelo: `HuggingFaceTB/SmolLM3-3B`. Dataset: GSM8K `test`, via `sistema.core.dataset.load_gsm8k`.
Acurácia: `ModelBackend` com `do_sample=False` e no máximo 256 tokens novos (`sistema/node/inference.py:69-75`).
Amostras: temperatura 0,7 , 5 gerações por questão, semente inicial 0.

## Máquina

- Python: 3.12.14 (/Users/gabrielferraz/Desktop/Tcc Lara/.venv/bin/python)
- Plataforma: macOS-26.6.2-arm64-arm-64bit
- CPU: Apple M5
- Núcleos: 10
- Memória (bytes): 17179869184

## Carga do modelo

- Dispositivo escolhido pelo código: `mps` (`sistema/node/inference.py:49-56`).
- Tempo de carga: 13,4 s.
- RSS máximo do processo depois da carga: 3,78 GB.

## Acurácia em 50 questões (guloso)

- Acertos: 39/50.
- Acurácia: 78,0%.
- Tempo médio por tarefa: 8,98 s (mínimo 4,07 s, máximo 14,74 s).
- Tempo total das 50 tarefas: 449,1 s.
- RSS máximo depois dessa leva: 3,78 GB.

## Dez questões, cinco amostras, temperatura 0,7

Resposta distinta = número extraído por `extract_final_answer` (`sistema/core/answer.py:18`). Também se conta o texto bruto, porque dois textos podem extrair o mesmo número.

| Questão | Gabarito | Respostas extraídas | Distintas (número) | Distintas (texto) | Acertos nas 5 |
| --- | --- | --- | --- | --- | --- |
| 0 | 18 | 18, 18, 18, 18, 18 | 1 | 5 | 5/5 |
| 1 | 3 | 3, 3, 3, 3, 3 | 1 | 5 | 5/5 |
| 2 | 70000 | 70000, 70000, 70000, 325000, 150 | 3 | 5 | 3/5 |
| 3 | 540 | 540, 540, 540, 540, 540 | 1 | 5 | 5/5 |
| 4 | 20 | 140, 3, 60, 46.67, 800 | 5 | 5 | 0/5 |
| 5 | 64 | 64, 64, 64, 29, 78 | 3 | 5 | 3/5 |
| 6 | 260 | 260, 260, 260, 260, 260 | 1 | 5 | 5/5 |
| 7 | 160 | 120, 160, 320, 60, 60 | 4 | 5 | 1/5 |
| 8 | 45 | 315, 180, 215, 315, 4 | 4 | 5 | 0/5 |
| 9 | 460 | 460, 460, 460, 460, 460 | 1 | 5 | 5/5 |

Acurácia de cada amostra, nas 10 questões (amostra 0 é a primeira geração de cada questão):

- Amostra 0: 7/10 = 70,0%.
- Amostra 1: 8/10 = 80,0%.
- Amostra 2: 7/10 = 70,0%.
- Amostra 3: 5/10 = 50,0%.
- Amostra 4: 5/10 = 50,0%.

Tempo médio de uma geração com temperatura 0,7: 10,06 s.

## Estimativa de uma rodada com nós honestos

O código de inferência faz uma geração por chamada, sem lote (`sistema/node/inference.py:69-75`). Usando a média gulosa de 8,98 s por chamada, em sequência, nesta máquina, com o modelo já carregado:

| Nós honestos chamando o modelo | Uma rodada | 50 rodadas |
| --- | --- | --- |
| 10 | 1,5 min | 1,25 h |
| 20 | 3,0 min | 2,50 h |
| 50 | 7,5 min | 6,24 h |

O script `sistema/scripts/run_com_smol.py:1-8` não faz isso: gera uma vez por pergunta e todos os honestos reutilizam a resposta. Nesse caminho, 50 rodadas com as 10 tarefas da amostra seriam cerca de 10 gerações, 1,5 min, qualquer que seja o número de nós.

RSS máximo ao fim: 3,78 GB. Uma segunda cópia do modelo de 3B em float16 não foi carregada; 50 processos simultâneos não caberiam nessa conta.
