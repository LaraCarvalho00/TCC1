# Notas para o artigo — entrega 20/09/2026

Texto para colar/adaptar no artigo. Hardware medido nesta máquina. Comentários
do PDF do Canvas não estão neste repositório; o que segue cobre o combinado
na reunião (método, reputação, dataset, trabalhos relacionados, novidade).

## Hardware utilizado

Os experimentos de simulação e a rede em containers (modo mock) foram
executados em um notebook **Dell Inspiron 15 3511**, processador **11th Gen
Intel Core i5-1135G7 @ 2.40 GHz** (4 núcleos físicos, 8 threads), **8 GB** de
memória RAM e GPU integrada **Intel Iris Xe Graphics**, sistema Windows 10,
Python 3.11. Essa limitação de memória impede redes grandes e a execução
simultânea de vários nós com LLM. Por isso a avaliação reportada usa **6 nós**
e prioriza simulação local / containers em modo mock. Inferência com
SmolLM3-3B, quando houver, é pontual (script `test_model`), não em dezenas de
réplicas.

## Correção metodológica (reputação sem ground-truth)

Na versão anterior, o score de reputação usava o gabarito da tarefa
(`s = 1` se a resposta coincidia com a resposta correta). Isso vaza informação
que a rede **não teria** em produção e infla o ganho do mecanismo — em
especial contra conluio.

Na versão corrigida:

1. O consenso ponderado da rodada *t* usa só as reputações de *t−1*.
2. O sinal de reputação é acordo com esse consenso, exigindo confiança mínima
   (fração de peso no vencedor ≥ 0,55).
3. Nó que não responde é penalizado (`s = 0`): tratamento do comportamento
   instável.
4. O gabarito entra apenas na métrica de acurácia do consenso (avaliação
   *offline*), nunca no update da reputação.

Consequência esperada, alinhada à orientação: **nós em conluio podem degradar
gravemente o resultado** quando capturam o consenso; a reputação deixa de ser
um oráculo.

## Dataset de treino vs avaliação

O modelo **não é treinado neste trabalho**. Usa-se SmolLM3-3B pré-treinado.
As tarefas dos experimentos vêm do split de **teste** do GSM8K (ou de uma
amostra offline equivalente, distinta do split de treino oficial). Scripts
recusam `split=train`. Eventual contaminação do pré-treino do modelo com
GSM8K não é controlável aqui; o que se garante é a separação **no protocolo
deste TCC**.

## Cenários experimentais (rede pequena)

| Cenário | Composição (6 nós) | Objetivo |
| --- | --- | --- |
| (i) Honestos vs maliciosos | 4 honestos, 2 maliciosos em conluio | Isolar adversário deliberado |
| (ii) Honestos vs instáveis | 4 honestos, 2 instáveis | Isolar o tratamento de indisponibilidade/erro |
| (iii) Honestos vs maliciosos vs instáveis | 3 honestos, 2 maliciosos, 1 instável | Interação dos três perfis com maioria honesta |
| Extra: conluio 50% | 3 honestos, 3 maliciosos em conluio | Mostra o colapso sem oráculo (pedido da orientação) |

Linha de base: consenso por maioria simples (sem reputação).

## Trabalhos relacionados — reputação (rascunho)

Mecanismos de reputação em aprendizado distribuído aparecem sobretudo em
**Federated Learning**, não em inferência colaborativa:

- Kang et al. e variantes posteriores combinam reputação com incentivos para
  filtrar clientes que enviam atualizações ruins no treino federado.
- **AutoDFL** automatiza reputação em FL descentralizado, com ênfase em
  escala e operação sem servidor central de treino.
- **SRFL** associa reputação de enxame a FL em AIoT, isolando nós pouco
  confiáveis no ciclo de agregação de modelos.
- Frameworks com **blockchain** (ex.: reputação assistida por ledger em DFL)
  registram scores de forma auditável, ao custo de overhead de consenso de
  plataforma.

Inspiração direta do mecanismo deste TCC: reputação **subjetiva / por acordo
entre pares** (linha de EigenTrust e de scores por consistência com o
agregado), adaptada para **respostas de inferência**, não para pesos de
modelo.

## Qual é a novidade?

Até onde a revisão alcança, os mecanismos acima pontuam **contribuição ao
treino** (updates, qualidade do gradiente, participação). O mecanismo
proposto pontua **saídas de inferência** em uma rede que agrega respostas a
uma mesma tarefa, sem gabarito em tempo de execução, com penalização explícita
de indisponibilidade (nós instáveis) e consenso ponderado comparado a maioria
simples. Não se usa blockchain. A reivindicação a afirmar no texto: reputação
para **sistemas distribuídos de inferência de IA**, não para FL de treinamento.

## O que não entra mais no artigo

Resultados da matriz 5/10/20 nós e qualquer tabela em que a reputação tenha
sido atualizada com gabarito. Esses testes foram apagados do repositório.
