# Sistema de inferência distribuída

Este projeto estuda, em simulação, como um protocolo de orquestração dinâmica com reputação se comporta diante de respostas maliciosas. Os participantes recebem a mesma tarefa; a rede elege um líder, verifica a proposta e decide o registro por quórum. O código inclui as séries experimentais do artigo, uma demonstração em contêineres e uma avaliação opcional de modelo de linguagem.

O projeto está em camadas: a interface recebe os comandos; os módulos de experimentos geram e executam as grades; o simulador e os serviços em contêineres usam as regras de consenso, eleição, reputação e registro em `sistema/core/`. Os registros são encadeados por hash, mas isso não implica mineração, contratos inteligentes ou uma plataforma blockchain completa.

## Estrutura

- `sistema/interfaces/cli.py`: entrada principal de linha de comando.
- `sistema/interfaces/artigo_cli.py`: coordenação das séries do artigo.
- `sistema/experimentos/`: grades de ruído, centros de consenso e séries complementares.
- `sistema/dados/banco_smol.json`: banco de tarefas e respostas pré-geradas do modelo.
- `sistema/simulate.py`: simulação local da rede em um processo.
- `sistema/core/`: perfis, consenso, reputação, eleição, protocolo, topologia, registros e métricas.
- `sistema/node/` e `sistema/orchestrator/`: serviços dos nós e coordenador experimental em contêineres; a liderança das rodadas pertence aos nós eleitos.
- `sistema/config/` e `docker-compose.yml`: configuração de demonstração.
- `execucao/run_llm.py`: avaliação opcional do modelo.
- `sistema/tests/`: testes automatizados.

Os materiais anteriores permanecem no histórico do repositório. A comparação das séries atuais com os resultados e as versões do artigo deve ser feita com os parâmetros, as sementes e o banco correspondentes.

## Instalação no Windows

Use Python 3.10 ou superior; as imagens Docker do projeto usam Python 3.11. No PowerShell, na raiz do repositório:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

Se `python` não estiver disponível, instale uma versão compatível ou use o lançador instalado na máquina, por exemplo `py -3.11 -m venv .venv`. Os exemplos invocam o Python do ambiente virtual diretamente e não precisam de ativação no PowerShell.

As séries de simulação e os testes usam a biblioteca padrão. Para os serviços HTTP locais, instale `sistema/requirements.txt`; para a avaliação de LLM, instale `sistema/requirements-model.txt`. O Docker constrói imagens com as dependências dos serviços.

## Cenários do artigo

As séries principais usam o banco `sistema/dados/banco_smol.json`, com 50 tarefas e 20 respostas pré-geradas por tarefa com **SmolLM3-3B** (o nome do arquivo é histórico). O simulador seleciona respostas desse banco: ele não executa a LLM a cada rodada. Esses lotes são a referência do artigo; **não** devem ser renomeados nem fundidos com execuções Qwen. As grades principais somam **3.670 execuções**; o contraste, com 10 execuções, é uma série adicional.

| Série | O que varia | Execuções |
| --- | --- | ---: |
| `ruido` | Configuração dinâmica, ruído malicioso, nota de gabarito, conluio, fração maliciosa e semente | 2.560 |
| `centros` | Centro de consenso, configuração dinâmica, ruído, conluio, fração maliciosa e semente | 960 |
| `sensibilidade` | Mecanismo de reputação, taxas de atualização, fração maliciosa e semente | 120 |
| `instabilidade` | Fração de nós instáveis, fração maliciosa e semente | 30 |
| `contraste` | Estratégia maliciosa e semente; série complementar fora do total principal | 10 |

Use a entrada principal para planejar ou executar as séries:

```powershell
.\.venv\Scripts\python.exe -m sistema.interfaces.cli experimentos todas --planejar
.\.venv\Scripts\python.exe -m sistema.interfaces.cli experimentos ruido --workers 4
.\.venv\Scripts\python.exe -m sistema.interfaces.cli experimentos centros --workers 4
.\.venv\Scripts\python.exe -m sistema.interfaces.cli experimentos sensibilidade --workers 4
.\.venv\Scripts\python.exe -m sistema.interfaces.cli experimentos instabilidade --workers 4
.\.venv\Scripts\python.exe -m sistema.interfaces.cli experimentos contraste --workers 4
.\.venv\Scripts\python.exe -m sistema.interfaces.cli experimentos todas --workers 4
```

`todas` executa as quatro séries principais, em sequência; `contraste` é executado separadamente. `--workers` deve ser pelo menos 1. `--planejar` mostra as quantidades sem iniciar as simulações. As grades completas podem demorar; para listar as opções, execute `.\.venv\Scripts\python.exe -m sistema.interfaces.cli experimentos --help`.

A saída-base padrão é `resultados/artigo/`. Use `--saida CAMINHO` para escolher outro diretório-base ou `--banco CAMINHO` para selecionar outro banco. Cada comando cria uma pasta própria e não sobrescreve uma execução anterior. `--guardar-brutos` preserva os CSVs individuais de ruído e centros; em `todas`, a opção se aplica a essas duas séries.

## Resultados e reprodutibilidade

Cada execução pela entrada principal cria `manifesto_execucao.json`, que registra as séries programadas, seus estados e códigos de saída. Os processos das séries geram manifestos próprios, CSVs e resumos dentro da pasta criada. Confira os manifestos antes de usar os resultados; se uma etapa falhar, as etapas seguintes não são iniciadas.

Os manifestos das séries registram parâmetros, sementes, identificação e hash do banco, versão do Python, commit, alterações locais e hashes de código. Esses dados ajudam a identificar o ambiente, mas não substituem preservar o código e as dependências. Os resultados gerados ficam fora do Git por padrão.

Para gerar os gráficos a partir de lotes concluídos, instale `sistema/requirements-analysis.txt` e execute:

```powershell
.\.venv\Scripts\python.exe -m sistema.experimentos.gerar_graficos `
  --ruido CAMINHO_DO_LOTE_DE_RUIDO --centros CAMINHO_DO_LOTE_DE_CENTROS `
  --sensibilidade CAMINHO_DA_SENSIBILIDADE --instabilidade CAMINHO_DA_INSTABILIDADE `
  --saida NOVA_PASTA
```

Quando sensibilidade, instabilidade e contraste tiverem sido executados juntos em um lote complementar de 160 execuções, use `--complementares CAMINHO_DO_LOTE` no lugar das duas opções separadas. Informe `--banco CAMINHO` se os lotes usaram outro banco; o gerador verifica se o hash do banco coincide com o registrado em todos os manifestos.

O comando cria figuras em PNG e PDF, legendas explicativas e um manifesto com hashes das fontes. A pasta de saída deve ser nova. Os gráficos das simulações e o gráfico do banco pré-gerado não representam uma nova medição da LLM.

As métricas incluem acurácia com e sem reputação, acurácia nas rodadas sem gabarito, reputações, rodadas auditadas e número de cadeias. Em cenários com divisão, uma medida da cópia de referência não demonstra que todos os nós compartilham uma única cadeia. Compare a acurácia com as demais métricas e os dados de cada cenário antes de interpretar os resultados.

## Execução em contêineres

Com Docker e Docker Compose disponíveis, a demonstração inicia quatro nós e um coordenador experimental:

```powershell
docker compose up --build --abort-on-container-exit --exit-code-from orchestrator
```

A configuração está em `sistema/config/experiment.yaml`, e os resultados da demonstração são gravados em `sistema/results/`. Depois da execução, os serviços desse projeto Compose podem ser encerrados com `docker compose down`.

A demonstração usa nós em modo `mock`, rede de quatro nós e 20 rodadas; ela não executa as grades completas do artigo. O script `sistema/scripts/validate_docker_dynamic.ps1` contém outra validação selecionada com 4, 10 e 20 nós; consulte seus requisitos de imagens antes de executá-lo. Contêineres em uma única máquina não demonstram distribuição física entre computadores.

### Grade local com LLMs compartilhadas

O runner também executa 50 nós Docker e um orquestrador dinâmico com inferência real em um gateway no host. O gateway mantém de uma a cinco instâncias NF4 e atende as chamadas por fila. Cada nó gera uma resposta nova em cada rodada, inclusive os maliciosos; os caches são exclusivos de cada cenário e servem para retomar uma execução interrompida.

Depois de construir as imagens `tcc-node:latest` e `tcc-orch:latest` e disponibilizar o snapshot do modelo no host:

```powershell
.\.venv-llm\Scripts\python.exe -m sistema.scripts.runner_containers `
  --saida sistema/results/NOVA-GRADE `
  --nos 50 --rodadas 50 --rodadas-honestas 5 --semente 0 `
  --modelo Qwen/Qwen3-0.6B --inference-layout shared --inference-workers 5 `
  --model-snapshot CAMINHO_DO_SNAPSHOT --model-revision SHA_DA_REVISAO `
  --codigo-da-imagem --timeout-protocolo 1800 `
  --prazo-estendido --limite-segundos 604800
```

São 16 configurações: 20%, 40%, 60% e 80% de maliciosos, probabilidades de auditoria 0,1 e 0,2 e notas exata e graduada, com uma semente por configuração. A grade exige 40.000 gerações; sua duração depende do hardware e do modelo. Cinco modelos na GPU são compartilhados pelos 50 nós. A quantidade de modelos residentes deve ser validada junto à RAM necessária aos contêineres.

`--codigo-da-imagem` fixa o código dos contêineres nas imagens e copia o código do gateway para a pasta da grade. O modo real envia a pergunta aos nós sem gabarito. O experimento grava `rounds.csv`, `per_node.csv`, `reputation_history.csv`, caches SQLite, logs e um manifesto de progresso. Para retomar, repita os mesmos parâmetros com `--retomar`; o runner verifica código, imagens e configuração e gera apenas as respostas ausentes da mesma execução. O cache não é compartilhado entre cenários. Uma grade interrompida pode deixar o marcador `PARAR` na pasta de saída; não remova esse arquivo nem retome cenários sem uma decisão explícita — os caches existentes dependem do mesmo fingerprint de código e configuração.

### Extensão Qwen3-0.6B: metodologia, resultados disponíveis e limites

A execução com **Qwen3-0.6B** é uma **condição experimental adicional** do mesmo protocolo de consenso e reputação. Ela **não** reproduz integralmente a matriz do artigo nem substitui os resultados gerados com **SmolLM3-3B**. Mantenha as duas linhas separadas no texto do TCC: modelo, origem das respostas, arquitetura e sementes.

| Aspecto | Artigo e séries `resultados/artigo/` | Grade local Qwen (`sistema/results/…` e `resultados/llm/…`) |
| --- | --- | --- |
| Modelo | SmolLM3-3B | Qwen3-0.6B, revisão `c1899de289a04d12100db370d81485cdf75e47ca` |
| Respostas honestas | 20 saídas pré-geradas por tarefa no banco (1.000 no total; ~74% de acerto no banco, conforme o artigo) | Inferência **nova** a cada rodada; o banco fornece pergunta e gabarito, não a resposta do nó |
| Participantes | Simulação em processo | 50 nós lógicos em contêineres |
| LLM no host | Não usada nas grades principais | **Cinco** instâncias NF4 compartilhadas (layout `shared`); fila no gateway — não são 50 modelos residentes |
| Matriz | Várias frações, defesas e **cinco sementes** por condição | Grade planejada de 16 cenários (20/40/60/80% maliciosos, `p` 0,1 e 0,2, nota exata/graduada), **uma semente** (0) por configuração na execução interrompida |
| Infra cloud | — | Defaults AWS continuam orientados a Smol; não confundir com esta grade local |

**Parâmetros de geração** usados nos ensaios Qwen já persistidos (descreva exatamente assim ao citar os dados; não retroaja alterações de código sobre resultados antigos): quantização NF4; temperatura 0,7; top-p 0,95 (o cartão oficial do Qwen recomenda 0,8 no modo sem *thinking* — 0,95 é a condição medida); até 256 tokens novos; *thinking* desativado; prompt em inglês para GSM8K; extrator que prefere o número após `####` e, se o marcador faltar, o último número do texto. **Acerto bruto** e **aderência ao formato** são métricas distintas: no primeiro cenário completo, `####` ausente em 313/2.500 textos; isso não prova truncamento (os caches não registram tokens gerados nem motivo de parada).

**Estado da grade (16/11/2026, execução interrompida):**

- **Concluídos (2):** 20% maliciosos, `p = 0,1`, semente 0 — um com nota de gabarito **exata** e outro **graduada** (mesmas 2.500 gerações brutas; comparam regras de nota, não são réplicas independentes do modelo).
- **Parcial (1):** 20% maliciosos, `p = 0,2`, nota exata — 47 rodadas de rede concluídas, 2.391 gerações registradas; 41 gerações da rodada seguinte **não** formam rodada concluída.
- **Não executados:** os outros 13 cenários (40%, 60%, 80% e demais combinações de `p`/nota).
- **Contagem total:** 7.391 gerações persistidas — volume de trabalho salvo, não amostra independente para inferir toda a grade.

**O que os números permitem dizer** (sem alegar causalidade isolada do tamanho do modelo nem superioridade geral de uma nota com uma semente):

- Comparativo descritivo Smol × Qwen nas **mesmas 100** tuplas tarefa/nó/rodada/semente (piloto Smol vs cache Qwen): 79/100 e 34/100 acertos brutos — arquiteturas diferentes; semente numérica igual não iguala amostragem entre modelos.
- Primeiro cenário Qwen completo: **914/2.500** (36,56%) acertos nas gerações brutas; honestos publicaram **730/2.000** corretas — honestidade é seguir o protocolo, não acertar a conta.
- Consenso exato nas 48 rodadas sem auditoria nem calibração: **20/48** (exata) e **19/48** (graduada).
- Reputação média final: honestos **0,6993** (exata) e **0,7520** (graduada); maliciosos **0,5580** e **0,6325**; a graduada aumentou ambos os grupos e **reduziu** a separação entre eles.

Auditoria reprodutível (somente leitura dos SQLite/CSVs, sem inferência): pasta `resultados/llm/impacto-qwen-20261116/` — [VALIDACAO_IMPACTO.md](resultados/llm/impacto-qwen-20261116/VALIDACAO_IMPACTO.md), [RELATORIO_RESULTADOS.md](resultados/llm/impacto-qwen-20261116/RELATORIO_RESULTADOS.md), `dados_auditoria.json`, `comparacao_por_questao.csv` e `auditar_resultados.py`. A relação com o PDF do artigo está em `paginas_artigo.json` na mesma pasta. Dados brutos da grade em execução costumam ficar em `sistema/results/grade-n50-r50-qwen3-20261116/` (fora do Git por padrão).

**Três efeitos que não devem ser misturados no TCC:** (1) troca de família de modelo; (2) passagem de banco pré-gerado para inferência online; (3) passagem de simulação pura para 50 contêineres com pool de cinco LLMs. Conclusões do artigo baseadas em Smol permanecem válidas **no escopo Smol**; qualquer conclusão com Qwen exige rotular modelo, configuração e limitações acima.

## Avaliação opcional da LLM

Para avaliar o modelo separadamente, instale as dependências e execute:

```powershell
.\.venv\Scripts\python.exe -m pip install -r sistema/requirements-model.txt
.\.venv\Scripts\python.exe execucao/run_llm.py `
  --banco-tarefas sistema/dados/banco_smol.json `
  --saida resultados/llm/relatorio.md --progresso resultados/llm/progresso.jsonl
```

O script usa `HuggingFaceTB/SmolLM3-3B`: avalia 50 questões com geração gulosa e cinco amostras por questão nas primeiras dez, com temperatura 0,7. `--banco-tarefas` lê apenas as perguntas e os gabaritos do banco local; as respostas são geradas novamente. Sem essa opção, o script carrega o conjunto de teste GSM8K pela biblioteca `datasets`. `--progresso` grava cada resultado em JSONL e exige um caminho novo; o relatório existente só é substituído com `--sobrescrever`. O modelo pode exigir download, memória e tempo consideráveis. Para usar GPU NVIDIA, instale uma versão do PyTorch compatível com o CUDA da máquina antes das demais dependências.

Após concluir as 100 gerações, é possível produzir gráficos específicos dessa nova avaliação, sem misturá-los aos gráficos do banco histórico:

```powershell
.\.venv\Scripts\python.exe -m sistema.experimentos.graficos_inferencia `
  --progresso resultados/llm/progresso.jsonl --saida resultados/llm/graficos
```

A avaliação da LLM é separada das grades de simulação com respostas pré-geradas. As imagens Docker padrão instalam apenas dependências do modo `mock`; inferência real em contêineres exige preparar imagem, modelo e recursos apropriados.

### Simulação com inferência por nó e rodada

O simulador também pode executar o modelo durante as rodadas. O comando abaixo usa 50 nós, 50 rodadas, 50% de nós maliciosos e probabilidade de conferência de 0,2. Para testar 0,1, altere `--audit-p` e escolha outro `--experiment-id`:

```powershell
.\.venv\Scripts\python.exe -m sistema.simulate `
  --inference-model HuggingFaceTB/SmolLM3-3B `
  --task-bank sistema/dados/banco_smol.json `
  --nodes 50 --rounds 50 --malicious 0.5 --seed 0 `
  --orchestration dynamic --topology kregular --degree 4 --defense all `
  --signal consensus --consensus-mode distance --mechanism ema_slow_up `
  --audit-mode random --audit-p 0.2 --validation-score graded `
  --malicious-strategy knows_schedule --honest-rounds 5 `
  --malicious-answer noise --noise-mode relative --noise-distance 0.2 --collusion-value 999 `
  --output resultados/llm-por-no --experiment-id p20-seed0
```

Cada nó faz uma geração nova em cada rodada, inclusive os maliciosos. No ataque com conluio, a primeira geração maliciosa da rodada fornece a base para o ruído compartilhado; as demais gerações maliciosas são registradas, embora a resposta enviada seja a mesma. No início, os maliciosos podem imitar honestos conforme a estratégia escolhida. O arquivo de tarefas fornece apenas perguntas e gabaritos: nenhuma resposta pré-gerada é usada. A opção não suporta nós instáveis.

As chamadas são sequenciais, com uma instância do modelo; 50 nós e 50 rodadas representam 2.500 gerações por execução. `inferencias.jsonl` registra incrementalmente nó, rodada, semente, tempo, texto gerado, resposta extraída e resposta enviada. `inferencia_manifesto.json` registra os parâmetros e o estado da execução desde o início; o manifesto final registra parâmetros e hash da fonte das tarefas. Uma semente fixa permite rastrear as chamadas, mas não garante resultados idênticos entre diferentes ambientes de GPU. A rede continua simulada em um único processo; esse modo não mede comunicação real entre contêineres nem executa quatro modelos simultaneamente. Se a execução for interrompida, os registros parciais permanecem, mas **a retomada automática ainda não está implementada**: é necessário recomeçar em outro diretório.

## Validação temporária na AWS

O projeto também possui Terraform e GitHub Actions para executar os cenários em uma única máquina com várias GPUs. **Cada nó Docker carrega e consulta sua própria instância quantizada NF4 do SmolLM3**: a grade de 50 nós mantém 50 modelos residentes, distribuídos entre as GPUs. A grade padrão compara 50 rodadas com 20%, 40%, 60% e 80% de maliciosos, p = 0,1 e 0,2 e notas exata/graduada: 16 configurações e 40.000 chamadas novas. Um modo personalizado permite informar as quantidades de honestos e maliciosos, respeitando o orçamento de VRAM do perfil.

O servidor publica CSVs, logs e gráficos no S3 e é terminado ao finalizar ou atingir o prazo máximo. A configuração da conta AWS, os controles de encerramento, a execução e a recuperação dos resultados estão em [infra/aws/README.md](infra/aws/README.md).

## Testes

### Piloto de tempo na GPU local

Com o ambiente CUDA/NF4 e as dependências HTTP instalados, é possível medir dois nós com modelos próprios nas 50 questões:

```powershell
.\.venv-llm\Scripts\python.exe -m sistema.scripts.piloto_local `
  --saida resultados/llm/piloto-local-NOVA-PASTA
```

O comando exige uma pasta nova e o modelo já baixado. Inicia dois serviços HTTP locais em processos separados, cada um com uma LLM NF4 residente, e registra 100 gerações novas, tempos de carga, CSV de respostas, telemetria e caches separados. Encerra apenas os processos criados pelo piloto. Essa medição não executa consenso ou Docker e não comprova a capacidade de 50 modelos simultâneos; a extrapolação para várias GPUs é apenas uma hipótese de planejamento. As dependências HTTP estão em `sistema/requirements-node.txt`, e as versões de quantização em `sistema/node/requirements-dedicated.txt`.

### Suíte automatizada

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s sistema/tests -t .
```

Os testes verificam a lógica do protocolo, a criação de cenários e a execução dos componentes. Eles não substituem a avaliação da LLM real, a validação em múltiplas máquinas ou a análise científica dos resultados.
