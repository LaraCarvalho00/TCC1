# Acompanhamento da Orientação — TCC

**Alunos:** Allan Mateus Arruda de Souza e Lara Andrade Carvalho
**Orientadores:** Prof. Danilo Maia e Prof. Leonardo Vilela Cardoso
**Instituição:** PUC Minas — Engenharia de Software

---

## 1ª Reunião — 20/08/2026, 14h

### Compromissos assumidos até a próxima reunião

1. Definir um modelo de IA e um dataset a serem utilizados no projeto.
2. Testar o modelo com o dataset selecionado.
3. Executar as atividades do cronograma do artigo do TCC I para a primeira quinzena de agosto:
   - **(i)** Parametrização dos containers Docker e comunicação assíncrona;
   - **(ii)** Implementação computacional do mecanismo dinâmico de pontuação de reputação.

### Definições consolidadas na reunião

- Próximas reuniões: **quintas-feiras, 14h**.
- Arquitetura inicial: **orquestrador fixo** em uma **rede bem conectada**, avaliando um
  cenário mais simples para obter uma **versão inicial do sistema em menor tempo**.

---

## Check: solicitado × entregue

| # | Solicitado pela professora | Status | Entregue / Onde está |
|---|----------------------------|:------:|----------------------|
| 1 | Definir um **modelo de IA** e um **dataset** | ✅ Feito | Modelo **SmolLM3-3B** e dataset **GSM8K** definidos e integrados. Ver [core/dataset.py](sistema/core/dataset.py) e [node/inference.py](sistema/node/inference.py) |
| 2 | **Testar o modelo** com o dataset | ⚙️ Pronto para executar | Script [scripts/test_model.py](sistema/scripts/test_model.py) carrega o modelo, resolve N problemas do GSM8K e reporta acurácia e tempo. Falta rodar em hardware adequado |
| 3.i | **Parametrização dos containers Docker** e **comunicação assíncrona** | ✅ Feito | Nós FastAPI assíncronos ([node/app.py](sistema/node/app.py)), orquestrador com coleta concorrente via `httpx` ([orchestrator/run.py](sistema/orchestrator/run.py)), Dockerfiles, [docker-compose.yml](docker-compose.yml) e gerador para N nós ([scripts/gen_compose.py](sistema/scripts/gen_compose.py)) |
| 3.ii | **Mecanismo dinâmico de pontuação de reputação** | ✅ Feito e validado | EMA por rodada em [core/reputation.py](sistema/core/reputation.py); consenso ponderado em [core/consensus.py](sistema/core/consensus.py) |
| — | **Orquestrador fixo** em **rede bem conectada** | ✅ Feito | Topologia estrela: orquestrador central com canal para cada nó |

**Legenda:** ✅ concluído · ⚙️ implementado, pendente de execução em hardware.

---

## Detalhamento por item

### 1. Modelo de IA e dataset

- **Modelo:** `HuggingFaceTB/SmolLM3-3B` — pequeno o suficiente para o hardware disponível,
  conforme discutido (possibilidade de substituir por alternativa menor se necessário).
- **Dataset:** `openai/gsm8k` — problemas de raciocínio matemático em formato textual, que
  exigem interpretação e não apenas cálculo direto, justificando o uso de um LLM.
- Ponto de atenção levantado na reunião: o GSM8K está **em inglês**, o que pode introduzir
  um *gap* linguístico. Registrado para avaliação de alternativas em português.
- Uma **amostra offline** ([core/data/gsm8k_sample.json](sistema/core/data/gsm8k_sample.json))
  foi embutida para validar o pipeline sem depender de download.

### 2. Teste do modelo com o dataset

- Comando:
  ```bash
  pip install -r sistema/requirements-model.txt
  python -m sistema.scripts.test_model --model HuggingFaceTB/SmolLM3-3B --dataset gsm8k --num-samples 20
  ```
- Saída: acurácia (acertos/total) e tempo médio por tarefa — insumo para decidir se o
  modelo é leve o bastante para rodar múltiplos nós simultaneamente ou se será necessária
  uma VM, conforme discutido na reunião.

### 3.i. Containers Docker e comunicação assíncrona

- Cada nó roda em um container isolado (FastAPI) e responde de forma assíncrona; a inferência
  do modelo executa em thread separada, mantendo o servidor responsivo.
- O orquestrador distribui a tarefa a **todos os nós concorrentemente** (`asyncio.gather`) e
  trata **timeouts/falhas** (detecção de instabilidade).
- Parametrização por variáveis de ambiente: `NODE_ID`, `PROFILE`, `INFERENCE_MODE`,
  `MODEL_NAME`, `SEED`, `MALICIOUS_VALUE`.
- Cenário inicial em [docker-compose.yml](docker-compose.yml): **4 nós** (3 honestos + 1 malicioso),
  rede bem conectada. Escalável para 5/10/20 nós via `gen_compose`.

### 3.ii. Mecanismo dinâmico de reputação

- Reputação em `[0, 1]`, inicial `0.5`, atualizada **a cada rodada** por média móvel
  exponencial: `r ← (1 - α)·r + α·s`, com `s = 1` (acerto) ou `s = 0` (erro/ausência) e `α = 0.3`.
- **Consenso ponderado** pela reputação (proposta do trabalho) comparado com **maioria simples**
  (linha de base), permitindo medir o ganho do mecanismo.

---

## Validação já realizada

Simulação local (sem Docker/modelo) executada com sucesso:

| Cenário | Consenso ponderado (reputação) | Maioria simples (base) |
|---|:---:|:---:|
| 4 nós, 25% malicioso | 100% | 100% |
| 4 nós, 50% malicioso **em conluio** | **85%** | **0%** |
| 6 nós, 33% malicioso + 17% instável | 100% | 100% |

Reputação final por perfil converge como esperado: honestos ≈ 0.88–0.99, maliciosos ≈ 0.00,
instáveis ≈ 0.07. O cenário de conluio evidencia a **contribuição central do TCC**: a reputação
mantém 85% de acerto onde a maioria simples zera.

Métricas registradas por execução (variáveis dependentes do Documento de Visão):
acurácia agregada, taxa de consenso correto, tempo médio de resposta e evolução da reputação.

---

## Pendências para a próxima reunião (quinta, 14h)

- [ ] Executar `test_model` com o SmolLM3-3B no GSM8K e registrar acurácia/tempo.
- [ ] Avaliar risco de *gap* linguístico (GSM8K em inglês) e possíveis datasets em português.
- [ ] Rodar a rede em containers (`docker compose up`) e coletar métricas em modo `mock`.
- [ ] Decidir se nós instáveis serão categoria distinta ou agrupados com maliciosos na v1.
- [ ] Avaliar necessidade de VM para executar múltiplos nós com o modelo real.

---

## Orientação de 26/09/2026 — rodadas de teste fixas

A rodada de avaliação deixou de ser indefinida. Em todos os experimentos há um teste a cada 10 rodadas (10, 20, 30, 40 e 50). Cada teste fica em `rounds.csv` (`is_test`, `test_round`) e no `summary.json`.

A matriz foi reexecutada em `sistema/results/matrix_testes_fixos/` (840 execuções). Os gráficos em LaTeX e a leitura dos números estão em `sistema/resultados/rodadas_teste_fixas/`. As execuções anteriores não foram apagadas.

Outras topologias, além da estrela, continuam para o próximo ciclo.

---

## Orquestrador dinâmico — líder eleito, auditoria e quórum

O orquestrador fixo foi trocado por um líder eleito a cada rodada entre os próprios nós. A reputação fica numa cadeia de registros encadeados por hash, e cada nó guarda e confere a sua cópia. Os nós só conhecem os vizinhos do grafo. Leitura completa em [analise.md](sistema/resultados/orquestrador_dinamico/analise.md) e texto para o artigo em [texto_resultados.md](sistema/resultados/orquestrador_dinamico/texto_resultados.md).

### Check: solicitado × entregue

| # | Solicitado | Status | Entregue / Onde está |
|---|------------|:------:|----------------------|
| 1 | Orquestrador = nó de **maior score e disponibilidade**, mudando a cada rodada | ✅ Feito | [core/election.py](sistema/core/election.py): disponível = no máximo 1 ausência nas últimas 5 rodadas; maior score sem repetir o líder anterior; rodízio enquanto os scores estão empatados. Nenhum nó liderou duas rodadas seguidas |
| 2 | **Segundo melhor nó audita** | ✅ Feito | Auditor = melhor nó disponível a pelo menos 2 saltos do líder. Veto falso do auditor nunca anulou rodada e custa reputação a ele |
| 3 | Nós **conhecem só os vizinhos** e o histórico dos outros | ✅ Feito | [core/topology.py](sistema/core/topology.py) (grafo 4-regular) e [core/ledger.py](sistema/core/ledger.py) (cadeia com hash); nos containers cada nó recebe `NEIGHBORS` e guarda a própria cadeia ([node/app.py](sistema/node/app.py)) |
| 4 | Impedir que o líder **manipule os scores** | ✅ Feito | [core/protocol.py](sistema/core/protocol.py): cada nó refaz a conta e confere a própria resposta; forja e censura são recusadas; quórum por massa de reputação. Até 50% de maliciosos, nenhuma forja ou censura aceita |
| 5 | Conceitos de **grafos, blockchain e computação distribuída** | ✅ Feito | Difusão por vizinhos com repasse, cadeia encadeada por hash, quórum ponderado, divisão da rede (fork) quando os honestos recusam um registro aprovado |
| 6 | Maliciosos **em maioria** não quebrarem a rede | ⚠️ Parcial | Com todas as defesas, 65% em 20 nós dá 1,000 nos testes e 71% em 7 nós dá 0,880, igual ao fixo. A proteção acima de 50% é a **divisão**: os honestos saem com a própria cadeia |
| 7 | Medidas contra conluio, testadas uma a uma | ✅ Feito | [core/defenses.py](sistema/core/defenses.py): calibração, gabarito fora do quórum, taxas separadas, dois scores, recusa. A ablação mostra que a recusa é necessária com maioria maliciosa; calibração e taxas ajudam em 50% |
| 8 | Sinal **híbrido** (consenso + gabarito) | ✅ Feito | `--signal hybrid`: gabarito nas 3 rodadas de calibração e nas de teste. Só consenso cai para 0 com 50% ou mais de maliciosos |
| 9 | Rodar **em containers** e comparar com a simulação | ✅ Feito | `/lead /task /verify /commit /oracle /ledger /leader` nos nós; [orchestrator/run.py](sistema/orchestrator/run.py) vira coordenador; [gen_compose.py](sistema/scripts/gen_compose.py) gera `PEERS`/`NEIGHBORS`. 4, 10 e 20 nós batem com a simulação ([docker_vs_simulacao.md](sistema/resultados/orquestrador_dinamico/docker_vs_simulacao.md)) |
| 10 | Trocar "semente" por um nome mais claro | ✅ Feito | "repetição" nos textos, legendas e scripts de documento. `--seed`, `seed:` e colunas de CSV (`n_sementes`, `semente`) ficaram como estavam |
| 11 | Resumo no mesmo formato dos anteriores | ✅ Feito | [analise.md](sistema/resultados/orquestrador_dinamico/analise.md), [texto_resultados.md](sistema/resultados/orquestrador_dinamico/texto_resultados.md), [graficos.tex](sistema/resultados/orquestrador_dinamico/graficos.tex) e esta seção |

**Legenda:** ✅ concluído · ⚠️ funciona com ressalva.

### O que funcionou

- **Acurácia:** a mesma acurácia de teste do orquestrador fixo em 20 nós (1,000 com 25%, 50% e 65% em conluio). A recuperação vem no mesmo prazo ou antes (rodada 2,0 contra 3,7 em 65%).
- **Liderança:** depois da calibração, nenhum líder malicioso com todas as defesas.
- **Ataques sem efeito:** forja, censura e veto falso não passam com a maioria honesta.
- **Escala:** no 4-regular os saltos crescem devagar (2,0 em 7 nós, 5,8 em 120) e cada nó mantém 4 conexões.
- **Containers e simulação:** os 43 testes unitários passam, inclusive a regressão do modo fixo e a paridade entre o código dos containers e a simulação.

### O que não funcionou ou ficou com ressalva

- **Liderança concentrada:** os dois maiores scores ficam com 76% a 98% das rodadas. A regra precisa de algo que espalhe o papel (sorteio ponderado ou carência).
- **Conluio em maioria:** acima de 50% a rede se divide, em vez de o quórum barrar o ataque. Um cliente externo precisa saber qual cadeia seguir.
- **Só consenso:** sem gabarito, a acurácia cai para 0 com 50% ou mais de maliciosos.
- **Auditor em rede pequena:** em 7 nós, só 2 nós ficam a 2 saltos do líder, e um malicioso de reputação baixa vira auditor com frequência. É inofensivo, mas o papel de auditor fica sem uso.
- **Votos sem assinatura:** identidade e ataques Sybil ficam para a próxima etapa.

### Mudanças em relação ao plano

- A largada termina quando o maior e o menor score se afastam 0,05.
- `star` é o grafo completo.
- O líder só é punido quando a anulação tem motivo verificável.
- Os nós de outra cadeia repassam mensagens sem processá-las.
- Entrou um bloco de auditor malicioso na matriz.
