# Sistema — Rede Distribuída de Inferência com Reputação

Orquestrador central fixo distribui tarefas a nós em containers, coleta
respostas de forma assíncrona, aplica **consenso ponderado por reputação** e
atualiza reputação **sem usar o gabarito**. O ground-truth entra só nas métricas.

## O que mudou após a reunião de orientação

Erro metodológico corrigido: a reputação **não** compara a resposta com o
gabarito. O sinal é (1) acordo com o consenso ponderado da própria rodada e
(2) penalização se o nó não responde (tratamento do perfil instável).

## Uso rápido

Simulação local (sem Docker, sem modelo) — caminho principal no hardware da equipe:

```bash
python -m sistema.scripts.run_scenarios
```

Um cenário avulso:

```bash
python -m sistema.simulate --nodes 6 --malicious 0.33 --collusion-value 999 --rounds 30
python -m sistema.simulate --nodes 6 --unstable 0.33 --rounds 30
```

Containers (modo mock):

```bash
docker compose up --build
```

Avaliação do modelo no **split de teste** do GSM8K (nunca `train`):

```bash
pip install -r sistema/requirements-model.txt
python -m sistema.scripts.test_model --dataset gsm8k --split test --num-samples 20
```

## Mecanismo de reputação

Cada nó começa em `0.5`. A cada rodada:

1. O consenso ponderado usa as reputações **já conhecidas**.
2. Se a fração de peso no vencedor ≥ `min_confidence` (padrão 0.55), quem
   concordou recebe `s = 1` e quem divergiu recebe `s = 0`.
3. Ausência de resposta (timeout / drop do instável) recebe `s = 0` mesmo sem
   consenso confiável.
4. Empate ou consenso fraco: reputação **não muda**.
5. EMA: `r ← (1 - α)·r + α·s`, com `α = 0.25`.

O gabarito **não** entra nos passos 1–5. Ele só marca `correct` no CSV de avaliação.

Isso implica um resultado científico honesto: **conluio com maioria pode
comprometer a rede** — exatamente o que a orientação pediu para recalibrar e
observar, em vez de mascarar com um oráculo.

## Tratamento do nó instável

| Evento | Consenso | Reputação |
| --- | --- | --- |
| Não responde / timeout | voto ignorado | `s = 0` |
| Responde, mas diverge do consenso confiável | voto entra com peso atual | `s = 0` |
| Responde e concorda | voto entra | `s = 1` |

## Dataset: treino vs avaliação

Este TCC **não faz fine-tune**. O SmolLM3-3B é usado pré-treinado. Tarefas de
experimento vêm do split **`test`** do GSM8K (ou da amostra offline, que não é
o conjunto de treino). O split `train` é recusado pelos scripts de avaliação.

## Métricas (`sistema/results/`)

- `per_node.csv` — `correct` (vs gabarito, só avaliação) e `reputation_score` (sinal real).
- `rounds.csv` — consenso ponderado vs maioria, confiança da rodada.
- `summary.json` — acurácias e reputação final por perfil (`reputation_uses_ground_truth: false`).

## Hardware de referência (máquina da equipe)

Dell Inspiron 15 3511, Intel Core i5-1135G7 (4 núcleos / 8 threads), ~8 GB RAM,
Intel Iris Xe. Por isso as redes avaliadas ficam em **6 nós** e a matriz 5/10/20
foi descartada.
