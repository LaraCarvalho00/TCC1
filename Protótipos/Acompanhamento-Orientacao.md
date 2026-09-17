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

- [x] Decidir tratamento dos nós instáveis (categoria distinta, penalização por ausência).
- [ ] Executar `test_model` com o SmolLM3-3B no GSM8K **test** e registrar acurácia/tempo.
- [ ] Colar no artigo: hardware, TR de reputação e novidade ([Notas-artigo-20-09.md](Notas-artigo-20-09.md)).
- [ ] Aplicar os comentários do PDF do Canvas (arquivo não está neste repositório).

---

## Reunião — setembro/2026 (erro metodológico e retrabalho)

### Diagnóstico da orientação

- Usar o gabarito para atualizar reputação **durante a inferência** é erro metodológico.
- Nós instáveis estavam no artigo sem tratamento definido.
- Testes anteriores devem ser **descartados** e refeitos.
- Conluio deve poder degradar a rede; a reputação precisa ser recalibrada sem oráculo.
- Hardware limitado → redes pequenas; avaliar comportamentos **separados** e um misto leve.
- Conferir que a base de avaliação não é a de treino.
- Artigo (20/09): hardware, trabalhos relacionados de reputação, novidade, correções do PDF.

### O que foi feito no repositório

| Item | Decisão / entrega |
| --- | --- |
| Ground-truth na reputação | Removido. Sinal = acordo com consenso + penalização de timeout. |
| Testes antigos (matriz 5/10/20) | Apagados. |
| Instável | Não vota se não responde; reputação `s = 0`. |
| Recalibração | `α = 0.25`, `min_confidence = 0.55` (não atualiza em empate). |
| Cenários | `python -m sistema.scripts.run_scenarios` (6 nós). |
| Dataset | Scripts recusam split `train`; avaliação em `test`. |
| Texto | [Notas-artigo-20-09.md](Notas-artigo-20-09.md) |

A tabela de “validação já realizada” **acima desta seção está invalidada** (usava gabarito na reputação). Usar só os novos CSVs em `sistema/results/cenarios/`.
