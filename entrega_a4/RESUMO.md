# Resumo da entrega A4

Números gerados em 22/10/2026 a partir de `main` em `44190e7288cedc7d0d05313c3da555412763bc37`, com as alterações locais de `sistema/simulate.py` e `sistema/node/inference.py`. Essas duas alterações não entram nas simulações das etapas 2 a 4: o runner não passa `tasks` nem `model_answers`. A etapa 5 usa o `inference.py` da árvore de trabalho (MPS e `enable_thinking=False`).

Commit dos dados: `0713bad7e2ccd0e54ebd950390b4d40fcab13f0d`, branch `a4-dados`. O mesmo hash está em `COMMIT.txt`.

Nós maliciosos que o código usou, `round(fração × 50)` em `sistema/simulate.py:58`:

| Fração | Nós |
| --- | --- |
| 0% | 0 |
| 5% | 2 |
| 20% | 10 |
| 25% | 12 |
| 35% | 18 |
| 50% | 25 |
| 65% | 32 |
| 80% | 40 |

Desvio-padrão das tabelas: amostral, divisor n−1, cinco sementes (0 a 4).

## Etapa 1 — código

Feito. Branch de partida `main`, commit `44190e7`. `git log --since=2026-10-11 --stat` saiu vazio porque o Git completa a data com a hora do relógio; os commits do dia 11/10 são 00:49 e 00:57. Detalhe em `01_codigo.md`.

A calibração sem líder (três rodadas sem eleição, sem proposta e sem voto) está **NÃO ENCONTRADO NO CÓDIGO**. O que existe é `calibration_rounds = 3`: a rodada elege, propõe e vota, e só depois o gabarito é gravado.

## Etapa 2 — reprodução do A3

Feito. 75 execuções, 0 erros, conferência série×resumo 75/75. Comando: `etapa2`.

Conferem (tolerância ±0,005): acurácia de teste do fixo (1 em 0% e 25%; 0 em 50%, 65% e 80%); acurácia de teste do dinâmico com gabarito em todas as frações pedidas; acurácia de teste do dinâmico sem gabarito em 50%, 65% e 80%; punição da rodada 1 sem gabarito em 50% (0,250 / 0,500); médias da rodada 50 sem gabarito em 50% (0,8667 / 0,0202) e em 80% (0,8811 / 1,0000); reputação de eleição do malicioso em 50% sem gabarito (0,2500); uma divisão e duas cadeias em 65% e 80% sem gabarito; maioria do fixo em 50%, todas as rodadas (média 0,0720; mínimo 0,04; máximo 0,10).

Não conferem: líder malicioso, forjas, anulações e divisões não são 0, 0, 0, 0 a partir de 25% com gabarito (em 65% e 80% há 1 forja aceita, 1 divisão e 2 cadeias). O malicioso depois das rodadas 1, 2 e 3 não é 0,1 / 0,02 / 0,004 (em 25% e 50% é 0,0500 / 0,0095 / 0,0018; em 65% e 80% fica em 0,2000). A soma do peso do conluio na rodada 4 é 0,0451 / 6,4000 / 8,0000, não 0,1 / 0,13 / 0,16. Em 50% com gabarito o malicioso depois da rodada 1 é 0,0500, não 0,100; o honesto é 0,8040. Em 80% com gabarito o malicioso na rodada 50 é 0,2000, não 0,000. A média de todas as rodadas 20 a 50 do malicioso no fixo é 0,8933, não 0,691; 0,6912 aparece só nas rodadas 20, 30, 40 e 50, e 0,9875 é o pico nas rodadas 19, 29, 39 e 49.

A célula isolada «depois da rodada 3» em 50% com gabarito ficou «sim» só porque 0,0018 está a 0,0022 de 0,004.

## Etapa 3 — matriz reputação × conluio

Feito. 720 execuções, 0 erros. Comando: `etapa3`. Três orquestradores, EMA, EMA assimétrica e beta, com e sem conluio, oito frações. Os dois agregadores saem das mesmas respostas. A figura EMA usa a cópia de referência. A maioria da rede inteira está na tabela e no CSV: em 65% e 80% com conluio ela é 0, enquanto a maioria da cópia de referência é 1.

## Etapa 4 — varredura

Feito. 2240 execuções, 0 erros. Comando: `etapa4`.

Menor k com acurácia de teste do protocolo igual a 1 em todas as frações e sementes: 0, para os seis pares (α de consenso 0,05 ou 0,30 × α de gabarito 0,50, 0,80 ou 0,95). Em 80% com k = 0, α 0,05 e 0,80, isso convive com 1 forja aceita, 1 divisão e 2 cadeias.

α único do fixo que dê acurácia de teste 1 com e sem conluio, em todas as frações e sementes: nenhum. Com conluio, o pior valor vai de 0 (α de 0,05 a 0,80) a 0,8000 (α = 0,90). Sem conluio, α 0,05, 0,10 e 0,20 ficam em 1; de 0,30 a 0,90 o pior é 0,8000.

## Etapa 5 — LLM

Feito, nesta máquina (Apple M5, 10 núcleos, 16 GB, GPU MPS). SmolLM3-3B, GSM8K test, guloso: 39/50 = 78,0%. Tempo médio 8,98 s por tarefa. RSS máximo 3,78 GB.

Nas 10 primeiras questões, temperatura 0,7, cinco amostras: o texto foi sempre diferente (5 textos distintos em todas). O número extraído foi único em 5 questões e chegou a 5 valores distintos em uma. Acurácia das cinco amostras: 70%, 80%, 70%, 50% e 50%.

Estimativa sequencial, uma geração por nó honesto, modelo já carregado: 10 nós, 1,5 min por rodada e 1,25 h em 50 rodadas; 20 nós, 3,0 min e 2,50 h; 50 nós, 7,5 min e 6,24 h. O script `run_com_smol.py` gera uma vez por pergunta e reutiliza a resposta: 10 gerações, cerca de 1,5 min.

## Etapa 6 — fatos

Feito em `06_fatos.md`, lendo o código. Não é saída de simulação.

## O que falhou

Nenhuma execução das etapas 2, 3, 4 ou 5. O que não existe no código está marcado como NÃO ENCONTRADO NO CÓDIGO (calibração sem líder; motivo do grau 4; motivo de a amostra ter exatamente 10 tarefas).

## Arquivos

- `01_codigo.md`
- `02_reproducao.md`, `02_execucoes.csv`, `02_resumo.csv`, `02_rodadas.csv`
- `03_matriz.md`, `03_matriz_execucoes.csv`, `03_matriz_resumo.csv`
- `figuras/03_fixo_com_gabarito_ema.png`
- `figuras/03_dinamico_com_gabarito_ema.png`
- `figuras/03_dinamico_sem_gabarito_ema.png`
- `04_varredura.md`, `04_varredura_execucoes.csv`, `04_varredura_resumo.csv`
- `figuras/04_varredura_dinamico.png`, `figuras/04_varredura_fixo.png`
- `05_llm.md`
- `06_fatos.md`
- `ERROS.md`
- `RESUMO.md`
- `run_a4.py`, `run_llm.py`
- `COMMIT.txt` (gravado depois do commit dos dados)

## Comandos

Na raiz do repositório:

```
git status
git log --since='2026-10-11 00:00:00' --stat
git diff --stat 44190e7

.venv/bin/python entrega_a4/run_a4.py etapa2
.venv/bin/python entrega_a4/run_a4.py etapa3
.venv/bin/python entrega_a4/run_a4.py etapa4
.venv/bin/python entrega_a4/run_llm.py
```

`etapa2`, `etapa3` e `etapa4` reescrevem os CSV, os markdown e as figuras dessas etapas. A etapa 6 não tem comando: é a leitura citada em `06_fatos.md`.
