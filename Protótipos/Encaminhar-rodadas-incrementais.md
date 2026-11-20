# Rodadas incrementais — 20 nós × 50 rodadas

Para encaminhar (Lara / outra máquina / orientação). Não substitui o artigo nem as 3.670 execuções.

## O que é a história

Sete etapas, **uma mudança por vez**. Só se **executam** as etapas 4, 5, 6 e 7. As etapas **1, 2 e 3** saem da 4: mesma simulação, lendo o consenso **sem peso** (medoide).

| Etapa | O que entra | Jobs no recorte 20×50 |
| --- | --- | --- |
| 1 | Caso base, 0% maliciosos, sem reputação | Derivada da 4 |
| 2 | Maliciosos **sem** conluio, sem reputação | Derivada da 4 |
| 3 | **Conluio** (valor 999), sem reputação | Derivada da 4 |
| 4 | **Reputação EMA** (consenso), auditoria fixed p=0,1, nota exact | 7 |
| 5 | **Auditoria por sorteio p=0,2** | 7 |
| 6 | **Nota graduada**, só com conluio | 3 |
| 7 | **20% instáveis** (drop depois de gerar), conluio, exact | 3 |
| **Total de configurações** | | **20** |

Protocolo fixo em todo job: 20 nós, 50 rodadas, grafo 4-regular, orquestrador dinâmico, medoide, ruído relativo δ=0,2, EMA αc=0,05 / αv=0,95, **sem gênese**, malicioso coopera nas rodadas 10, 20, 30, 40 e 50 (`honest_rounds=5`), `knows_schedule`.

Frações maliciosas neste recorte: **0 / 20 / 40 / 80%** (0, 4, 8 ou 16 nós). **Não** entra 60% nem p=0,1 (isso é o recorte Isabela 50 nós).

## 20 ou 100 execuções

- **20** = as 20 configurações × **1 semente** (semente 0).
- **100** = as mesmas 20 × **5 sementes** (0 a 4) — o que a figura com 100 pede.

Texto e figura têm que usar o **mesmo** número.

- **Banco** (CPU): 5 sementes / 100 execuções é barato (segundos).
- **Ao vivo** (GPU): 1 semente = até 1.000 gerações novas (20×50); 5 sementes = 5.000. Nesta 4060 8 GB, 5 sementes ao vivo do 8B não cabe no prazo.

Barras de desvio-padrão só fazem sentido com **5 sementes**.

## Dois scripts

Código na branch `codex/runpod-qwen`, commit `bec41d3` (e o recorte `n20s5` no working tree local).

1. **Banco Qwen3-8B** (o que a 4060 está gerando agora):  
   `sistema/scripts/gerar_banco_qwen3_8b.py`  
   50 questões GSM8K × 20 amostras, NF4, temp 0,7, top-p 0,95, max 256, thinking off.

2. **Rodadas incrementais:**  
   `sistema/scripts/rodadas_incrementais_n20.py`

```powershell
$env:PYTHONPATH = (Get-Location).Path

# Ver a lista (não executa)
python -m sistema.scripts.rodadas_incrementais_n20 --planejar --sementes 1
python -m sistema.scripts.rodadas_incrementais_n20 --planejar --sementes 5
```

## Como rodar cada condição

**Não misturar** no mesmo gráfico: banco Smol ≠ Smol ao vivo ≠ Qwen 8B NF4.

### A) Smol no banco (CPU) — 100 execuções, alinhado à figura

Usa `sistema/dados/banco_smol.json` (20 amostras/questão). Honestos sorteiam uma amostra; não chama a LLM.

```powershell
python -m sistema.scripts.rodadas_incrementais_n20 --sementes 5 --fonte banco --llm smol --saida resultados/incremental/smol-banco-n20s5
```

### B) Smol sem banco (GPU, cada nó gera)

`banco_smol.json` entra só com pergunta e gabarito. Até 2 cópias NF4 do SmolLM3-3B nesta 4060.

```powershell
python -m sistema.scripts.rodadas_incrementais_n20 --sementes 1 --fonte vivo --llm smol --workers 2 --saida resultados/incremental/smol-vivo-n20
```

Primeiro job: até 1.000 gerações (`0:rodada:node_id` no SQLite). Os outros 19 reusam o texto.

**Não rode junto com o gerador Qwen3-8B** — a 4060 só cabe um dos dois.

### C) Qwen3-8B no banco — depois que as 1.000 amostras fecharem

O JSON final aparece em `sistema/dados/banco_qwen3_8b.json`. Até lá não rode C.

```powershell
python -m sistema.scripts.rodadas_incrementais_n20 --sementes 5 --fonte banco --llm qwen3-8b --tarefas sistema/dados/banco_qwen3_8b.json --saida resultados/incremental/qwen3-8b-banco-n20s5
```

Modelo: `Qwen/Qwen3-8B`, NF4 (bitsandbytes), mesmos 0,7 / 0,95 / 256. **Não** misturar com as 313+ amostras NF4 desta máquina um banco FP16 da outra GPU.

## LLMs (para o texto)

| Condição | Modelo | Quantização | Geração |
| --- | --- | --- | --- |
| Banco / artigo Smol | `HuggingFaceTB/SmolLM3-3B` | Mac `mps`, sem NF4 no JSON do banco | temp 0,7, top-p 0,95, 256 |
| Smol vivo nesta 4060 | `HuggingFaceTB/SmolLM3-3B` | NF4 | iguais |
| Grade Qwen 0,6B (já documentada) | `Qwen/Qwen3-0.6B` rev. `c1899de…` | NF4 | iguais; thinking off |
| Zip Mac 20×50 | `Qwen/Qwen3-0.6B-MLX-4bit` | MLX 4-bit | iguais |
| Banco 8B desta 4060 | `Qwen/Qwen3-8B` | NF4 | iguais; thinking off |

Stack do piloto 8B: torch 2.7.1+cu126, transformers 4.57.6, bitsandbytes 0.50.2.

## Git (outra máquina)

Push **não** foi para `allanmateusk` (403: credencial `allansouzaallu`). O `bec41d3` está em:

https://github.com/allansouzaallu/TCC1/tree/codex/runpod-qwen

```powershell
git clone -b codex/runpod-qwen https://github.com/allansouzaallu/TCC1.git
```

O recorte `n20s5` e `rodadas_incrementais_n20.py` podem estar só no working tree local se não houver commit novo depois do `bec41d3`. Bundle de backup: `codex-runpod-qwen.bundle`.

## O que não fazer

- `--fonte vivo` na série que a Lara pediu **banco**.
- Copiar o jsonl NF4 da 4060 para um gerador FP16.
- Escrever “20 execuções” no texto e “100” na figura.
- Reescrever o artigo / pasta dos gráficos oficiais sem pedido.
