# Plano de execução do TCC no RunPod

Data: 2026-11-16. Base analisada: `d1c0b0471f2f1eae9a6a445dbc7e5d9c3f6455cb`.

O Terraform provisiona um único Pod de duas GPUs com 30 GB em `/workspace`. O workflow publica uma imagem baseada no Runpod PyTorch e o supervisor dessa imagem executa a campanha, envia resultados e publica o progresso.

## Objetivo e escopo

Executar Qwen3-0.6B NF4 com uma instância residente independente por nó. A configuração principal tem 50 processos em duas RTX A6000, com 25 modelos por placa. Cada cenário terá 50 rodadas e 2.500 gerações próprias, incluindo as dos maliciosos. Os cenários rodam em sequência no mesmo Pod.

A grade cruza quatro proporções de maliciosos, duas probabilidades de auditoria e duas formas de pontuação. Usar a revisão Qwen `c1899de289a04d12100db370d81485cdf75e47ca`. O banco `banco_smol.json` fornece as perguntas e o gabarito ao coordenador. A campanha gera todas as respostas no Qwen. O comparativo anterior registrou 34/100 acertos brutos para Qwen e 79/100 para Smol sob arquiteturas diferentes. Identificar modelo, quantização e arquitetura ao apresentar as métricas.

Usar as sementes predefinidas 0, 1, 2, 3 e 4. Isso produz 16 configurações × 5 sementes = 80 execuções, 4.000 rodadas completas e 200.000 gerações. A execução começa pelo primeiro cenário científico da semente 0. Usar as próprias rodadas da campanha para medir tempo e memória.

## Matriz científica

| Maliciosos | Honestos | Nós maliciosos | Auditoria p | Notas | Configurações por semente |
| --- | ---: | ---: | --- | --- | ---: |
| 20% | 40 | 10 | 0,1 e 0,2 | exact e graded | 4 |
| 40% | 30 | 20 | 0,1 e 0,2 | exact e graded | 4 |
| 60% | 20 | 30 | 0,1 e 0,2 | exact e graded | 4 |
| 80% | 10 | 40 | 0,1 e 0,2 | exact e graded | 4 |

Fixar o restante: banco de tarefas e seu SHA-256, revisão do modelo, commit do código, NF4 com dupla quantização, computação float16, thinking desativado, máximo de 256 tokens novos, temperatura 0,7, top-p 0,95, topologia kregular de grau 4, sinal de consenso, centro medoide, consenso por distância, defesa all, mecanismo ema_slow_up, conluio, ruído relativo 0,2 e estratégia knows_schedule. As cinco rodadas iniciais imitam honestidade e já estão incluídas nas 50, não são adicionais.

Identidade completa: campanha, configuração, semente, tentativa, nó, rodada, tarefa e revisão do modelo. Repetições HTTP da mesma solicitação são idempotentes. Cenários e sementes distintos não reutilizam respostas. Os gabaritos ficam no coordenador e não são incluídos no prompt.

O executor lê o manifesto explicitamente e reaproveita a configuração do protocolo dinâmico e a validação dos caches por nó. Cada nó roda num processo HTTP separado dentro do mesmo contêiner do Pod. A inicialização registra o PyTorch, a versão CUDA usada pelo PyTorch e o nome de cada GPU.

## Terraform e armazenamento

O módulo [run/](run/) usa o provider oficial `runpod/runpod` na versão 2.0.0. Basta definir um ID de execução no [arquivo de variáveis](run/run.tfvars.example).

| Item | Configuração |
| --- | --- |
| Pod | Um Pod on-demand no Secure Cloud |
| GPU | Duas NVIDIA RTX A6000, 48 GB por placa, 25 modelos em cada uma |
| Imagem | `runpod/pytorch:2.1.0-cu1320-torch280-ubuntu2404`, fixada por digest |
| Host | Filtro CUDA 13.2, mínimo de 100 GB de RAM e 18 vCPUs |
| Disco temporário | 180 GB |
| Volume do Pod | 30 GB em `/workspace`, criado com o Pod |

A oferta exibida tem 19 vCPUs. O Runpod expressa o mínimo em CPUs inteiras por GPU. Pedir 9 por GPU aceita a oferta de 19 e permite um host com 18. Conferir o total alocado e a tarifa no console. O volume do Pod preserva `/workspace` após parada, mas é excluído ao terminar o Pod. Exportar resultados para armazenamento externo antes do encerramento.

O teste reportado de cinco instâncias numa RTX 4060 Laptop de 8 GB atingiu 7,1 GB de pico. A extrapolação para 25 instâncias dá `25 × 7,1 / 5 = 35,5 GB`, com folga nominal de 12,5 GB numa A6000 de 48 GB. Essa conta depende de quantização, contexto e concorrência semelhantes. Registrar VRAM e RAM no carregamento e nas primeiras rodadas científicas. Se o executor encontrar falta de memória, salvar diagnóstico e encerrar a execução.

O plano manual usa estado local. O lançamento no GitHub usa um bucket R2 exclusivo para estado Terraform com locking e uma chave por execução. O controlador registra a intenção de lançamento antes de aplicar o plano. Se faltar o ID após falha de criação, consulta o Runpod pelo nome exato reservado para a execução.

Para verificar localmente, sem criar o Pod:

```sh
terraform -chdir=infra/runpod/run init -backend=false
terraform -chdir=infra/runpod/run validate
terraform -chdir=infra/runpod/run test -no-color -verbose
```

Para revisar um plano conectado, preencher um `run.tfvars` a partir do exemplo e fornecer `RUNPOD_API_KEY` ao Terraform por variável de ambiente. O workflow de lançamento preenche automaticamente o digest da imagem derivada e as variáveis da campanha.

```sh
terraform -chdir=infra/runpod/run plan -var-file=run.tfvars -out=run.tfplan
terraform -chdir=infra/runpod/run show -no-color run.tfplan
```

Se o Registry retornar `armor invalid` na instalação do provider 2.0.0, usar o ZIP oficial da versão para sua plataforma. Verificar o SHA-256 contra `.terraform.lock.hcl`, colocar o ZIP em `<mirror>/registry.terraform.io/runpod/runpod/` e executar o `init` acima com `-plugin-dir=<mirror> -lockfile=readonly`. O workflow usa esse procedimento no Linux e simula o provider nos testes de planejamento.

## Executor no Pod

O supervisor inicia um processo por nó, com `CUDA_VISIBLE_DEVICES` atribuído pela posição do nó no plano, uma porta local exclusiva e um cache exclusivo. Uvicorn roda com um worker por processo e threads de CPU limitadas. As portas dos nós ficam em loopback.

O executor carrega um processo por GPU a cada lote e confirma `/health` dos 50 modelos antes das rodadas. Reutiliza o snapshot de pesos em disco e reinicia os processos e o estado entre cenários. Cada nó registra o uso de memória CUDA no arquivo `model-runtime.json`.

Preservar protocolo, formação de grupos, auditoria e ataque existentes. Registrar separadamente a resposta bruta de cada LLM e a resposta enviada após o ataque. Não substituir erro de inferência por mock, resultado em cache de outro cenário ou execução silenciosa em CPU.

O supervisor envia um pacote por cenário concluído. Em interrupções, tenta enviar o cenário parcial antes de parar. Os dados ficam preservados para análise. A retomada automática de uma campanha interrompida ainda exige implementar a recuperação do manifesto e dos checkpoints.

## GitHub Actions

O workflow [runpod-check.yml](../../.github/workflows/runpod-check.yml) valida o código e publica o plano simulado. O [runpod-campaign.yml](../../.github/workflows/runpod-campaign.yml) publica a imagem no GHCR, provisiona a GPU sob acionamento manual e acompanha o Pod. Colocar o workflow da campanha na branch padrão antes do primeiro lançamento para que a verificação agendada funcione.

Antes de habilitar a automação:

1. Criar no Cloudflare R2 dois buckets privados Standard, um para estado Terraform e outro para resultados. Criar chaves separadas com acesso somente ao próprio bucket.
2. Criar o ambiente `runpod` em **GitHub → Settings → Environments**. Restringir as branches que podem usar esse ambiente à branch confiável. A reconciliação agendada precisa ter acesso ao ambiente sem intervenção.
3. Configurar as variáveis e Secrets abaixo. No console Runpod, cadastrar as chaves do bucket de resultados em **Secrets** como `tcc_results_access_key` e `tcc_results_secret_key`. O Terraform passa somente referências a esses nomes.
4. Cadastrar no Runpod uma credencial de registry com leitura do pacote GHCR privado `ghcr.io/<owner>/<repo>/runpod-qwen` e registrar seu identificador no GitHub. A Action publica a imagem usando o token automático do GitHub.
5. Criar a variável de repositório `RUNPOD_AUTOMATION_ENABLED=true` quando o workflow e os acessos estiverem prontos.

| Onde | Configuração |
| --- | --- |
| Variáveis do ambiente GitHub | `RUNPOD_R2_ENDPOINT`, `RUNPOD_STATE_BUCKET`, `RUNPOD_RESULTS_BUCKET`, `RUNPOD_GHCR_REGISTRY_ID` |
| Variável de preço opcional | `RUNPOD_MAX_HOURLY_USD`, padrão `1.42` |
| Secrets do ambiente GitHub | `RUNPOD_API_KEY`, `RUNPOD_R2_STATE_KEY`, `RUNPOD_R2_STATE_SECRET`, `RUNPOD_R2_RESULTS_KEY`, `RUNPOD_R2_RESULTS_SECRET` |

Em **Actions → RunPod Qwen campaign → Run workflow**, escolher `launch` e informar o prazo em horas. O padrão é 48 h desde a tentativa de provisionamento. O job retorna o ID `gh-...`. Para acompanhar ou pedir a interrupção, usar `status` ou `stop` com esse ID.

O worker aguarda uma autorização no bucket até que a Action confira as duas A6000 e o preço informado pela API. O reconciliador roda a cada dez minutos, sujeito ao agendamento do GitHub. Após confirmar os 80 pacotes, termina o Pod. Em falha, interrupção ou prazo vencido, solicita a parada e preserva o volume para recuperação. O Runpod continua cobrando o volume de um Pod parado. Conferir no console se a parada foi concluída, especialmente em falhas do GitHub ou do R2. O cron não representa um teto financeiro rígido.

O bucket guarda `tcc-runpod/runs/<run_id>/status.json`, `manifest.json`, `index.json` e `scenarios/*.tar.gz`. Cada pacote inclui CSVs, cadeias, logs e SQLite dos nós. A Action de lançamento termina em minutos e o Pod continua a campanha. A conclusão é confirmada pelo status final e pela presença dos 80 pacotes.

## Sequência de testes e critérios de aceite

| Etapa | Carga | Critério para avançar |
| --- | --- | --- |
| Local/CI | Sem LLM paga | Matriz completa/sem IDs repetidos, identidades e isolamento, seed, erros, replay, encerramento idempotente |
| Inicialização da campanha | 50 modelos em duas GPUs | 25 por GPU, NF4/CUDA registrados, memória registrada durante carregamento e nas primeiras rodadas |
| Matriz inicial | 16 configurações, semente 0, 50 rodadas | 40.000 gerações próprias, todos os arquivos e métricas íntegros |
| Repetições | Mesmas 16 configurações, sementes 1–4 | Mais 160.000 gerações; total científico de 200.000 |
| Consolidação | 80 execuções completas | Agregações, gráficos, manifesto final, backup verificado e Pod encerrado |

O manifesto de smoke fica disponível para uso opcional. O cronograma e o orçamento atuais começam no primeiro cenário da campanha.

Testes de falha: morte de um processo, timeout, resposta sem número extraível, HTTP duplicado, reinício do supervisor, falha temporária de upload, erro na publicação final e prazo excedido. Testar falhas com dublês localmente e um conjunto mínimo no Pod. Verificar encerramento também após cancelamento do lançamento.

Para cada execução científica concluída exigir: 50 nós × 50 pares nó/rodada únicos, cache `generations` e `responses` coerentes, 2.500 gerações próprias e respostas submetidas, modelo/revisão corretos, protocolo completo e métricas finitas. Resposta matematicamente errada ou não extraível é resultado científico a contabilizar, não autorização para repetir a LLM até acertar. Falha de infraestrutura deve permanecer explícita.

## Resultados e gráficos

O pacote de cada cenário guarda configuração, saídas, latências, cadeias, histórico de reputação e metadados CUDA por nó. O supervisor encerra os processos antes de empacotar os caches SQLite.

Gerar reputação por rodada e perfil, acurácia individual bruta, acurácia do consenso ponderado e por maioria, resultados nas rodadas com e sem auditoria e na fase de ataque, comparação exact/graded, latências e consumo. Agregar pelas cinco sementes, mostrando dispersão e tamanho da amostra. Usar a semente como unidade de repetição para os resultados agregados.

Critério de conclusão: matriz inteira verificada, exportações e upload confirmados, resumo final publicado e destruição do Pod comprovada. Resultados parciais não serão apresentados como campanha concluída.

## Custos condicionais

Pela oferta, as duas GPUs custam US$ 1,38/h e o disco temporário custa US$ 0,025/h. O volume de 30 GB acrescenta aproximadamente US$ 0,0042/h durante a execução, usando US$ 0,10/GB/mês e um mês de 720 horas. Total estimado de **US$ 1,409/h**, cerca de **US$ 1,41/h** com o volume. Conferir a cotação final na criação.

| Tempo médio de uma rodada completa | 16 execuções/1 semente | Custo base | 80 execuções/5 sementes | Custo base |
| --- | --- | --- | --- | --- |
| 20 s | 4h27 | US$ 6,26 | 22h13 | US$ 31,31 |
| 30 s | 6h40 | US$ 9,39 | 33h20 | US$ 46,97 |
| 45 s | 10h | US$ 14,09 | 50h | US$ 70,46 |
| 60 s | 13h20 | US$ 18,79 | 66h40 | US$ 93,94 |

O teste da 4060 informa capacidade. A tabela usa hipóteses de duração para o Pod de duas GPUs. A duração inclui espera pelos últimos nós, comunicação, auditoria e consenso. Na referência de 30 s, 33h20 de rodadas mais 20% para preparação, carregamento e exportação dão **40 horas e US$ 56,37**. Atualizar a estimativa com a duração dos cenários da semente 0. Eventual armazenamento externo, GitHub Actions acima da franquia, impostos e conversão de moeda são cobrados à parte.

## Entregáveis de implementação

O repositório contém o módulo Terraform, a imagem, o executor dos 50 processos e os workflows de validação, lançamento, acompanhamento e encerramento. A primeira execução real depende dos acessos, dos dois buckets, da imagem publicada pelo workflow e da disponibilidade das duas GPUs. A duração medida e os gráficos científicos dependem dos resultados da campanha.

## Fontes verificadas

- Provider oficial: https://registry.terraform.io/providers/runpod/runpod/latest/docs
- Imagem selecionada: https://hub.docker.com/r/runpod/pytorch/tags?name=2.1.0-cu1320-torch280-ubuntu2404
- Limitação de Docker Compose em GPU Pod: https://docs.runpod.io/tutorials/pods/build-docker-images
- Preços e cobrança: https://docs.runpod.io/pods/pricing
- Persistência e volumes: https://docs.runpod.io/pods/storage/types
- Limites GitHub Actions: https://docs.github.com/en/actions/reference/limits
- Agendamentos GitHub: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

Fontes locais: `infra/aws/README.md`, workflows AWS, `runner_containers.py`, `gen_compose.py`, `grade_llm.py`, `cloud_run.py`, pilotos de capacidade e código de inferência dedicada.
