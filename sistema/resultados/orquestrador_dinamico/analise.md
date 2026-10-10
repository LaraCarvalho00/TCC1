# Análise do orquestrador dinâmico

Rodada de testes do orquestrador eleito a cada rodada. O orquestrador fixo
deixa de existir. Em cada rodada:

- a rede elege um líder entre os nós;
- o líder espalha a tarefa pelos vizinhos;
- o líder propõe um registro encadeado por hash, que os nós verificam;
- a rodada só vale se quem confirma soma mais da metade da reputação dos participantes.

A pergunta é se essa versão distribuída mantém o resultado do orquestrador
fixo, inclusive com o conluio em maioria.

## O que foi executado

- **Matriz:** `run_matrix --plan dynamic --seeds 5`, com 1530 execuções, 50
  rodadas cada e teste nas rodadas 10, 20, 30, 40 e 50. São 5 repetições por
  célula (3 no bloco de escala). Resultados em
  `sistema/results/matrix_orquestrador_dinamico/` e índice copiado em
  [`matrix_index.csv`](matrix_index.csv).
- **Parâmetros comuns:**
  - acerto dos honestos de 0,9 e conluio no valor 999;
  - mecanismos beta e EMA assimétrica (as médias juntam os dois);
  - grafo 4-regular e sinal híbrido;
  - calibração de 3 rodadas e taxas 0,05 (consenso) e 0,8 (gabarito);
  - punição com taxa 0,5.
- **Blocos da matriz:**

| Bloco | O que varia | Hipóteses |
| --- | --- | --- |
| `main` | 7, 10 e 20 nós; 0, 25, 50 e 65% maliciosos; líder sem ataque, que forja ou que censura; todas as defesas | H1, H2, H4, H7, H8 |
| `consensus` | o mesmo recorte com sinal só de consenso (sem gabarito) | H5 |
| `auditor` | auditor malicioso que veta rodadas honestas; 25 e 50%; sem defesas e com todas | H3 |
| `ablation` | 20 nós com 50% e 65%; 7 nós com 71%; os 12 presets de defesa; forja e censura | H9 |
| `scale` | 7 a 120 nós, 25% maliciosos, grafo completo × 4-regular | H6 |
| `reference` | orquestrador fixo com gabarito em todas as rodadas, nas mesmas células | comparação |

- **Containers:** 5 cenários de 4, 10 e 20 nós
  ([`validate_docker_dynamic.ps1`](../../scripts/validate_docker_dynamic.ps1)),
  comparados com a simulação em [`docker_vs_simulacao.md`](docker_vs_simulacao.md).
- **Testes unitários:** 43 testes em `sistema/tests/`. Incluem a regressão do
  modo fixo, com os mesmos números de antes, e a paridade entre as cópias da
  cadeia de cada nó (código dos containers) e a rede simulada.

A porcentagem de maliciosos é a real: 0,65 nominal vira 13 de 20 (65%), 6 de 10
(60%) e 5 de 7 (71%); 0,5 em 7 nós vira 4 de 7 (57%).

Gráficos: [`graficos.tex`](graficos.tex) (pgfplots), com prévias em
[`figuras/`](figuras/) e pontos em [`coordenadas.csv`](coordenadas.csv). Todas
as tabelas geradas estão em [`tabelas.md`](tabelas.md).

## Resultado principal: fixo × dinâmico

Líder malicioso que forja, todas as defesas. "Recuperação" é a primeira rodada
a partir da qual o consenso ponderado não erra mais.

| Nós | Maliciosos | Fixo: testes | Fixo: recuperação | Dinâmico: testes | Dinâmico: recuperação | Líder malicioso depois da calibração | Divisões da cadeia | Só consenso: testes |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 25% | 1.000 | 1.0 | 1.000 | 2.0 | 0 | 0 | 1.000 |
| 20 | 50% | 1.000 | 1.9 | 1.000 | 2.0 | 0 | 0 | 0.000 |
| 20 | 65% | 1.000 | 3.7 | 1.000 | 2.0 | 0 | 1 | 0.000 |
| 10 | 50% | 1.000 | 1.6 | 1.000 | 2.0 | 0 | 0 | 0.100 |
| 10 | 60% | 1.000 | 3.5 | 1.000 | 5.6 | 0 | 1 | 0.000 |
| 7 | 57% | 0.940 | 12.3 | 0.940 | 15.9 | 0 | 1 | 0.000 |
| 7 | 71% | 0.900 | 36.7 | 0.880 | 36.5 | 0 | 1 | 0.000 |

O dinâmico chega à mesma acurácia de teste do fixo em quase todas as células.
O único desvio é em 7 nós com 71%: 0.880 contra 0.900. A rodada 1 erra quando o
primeiro líder do rodízio é malicioso, porque a forja dele é anulada e a rodada
fica sem consenso. Por isso a recuperação é 2.0 onde o fixo tem 1.0.

O ponto que muda é como ele chega lá com o conluio em maioria (57% ou mais):

1. Na rodada 1 o conluio aprova a própria forja: tem mais de metade da massa.
2. Os honestos recusam o registro e seguem a própria cópia da cadeia.
3. A rede se divide em duas. Daí em diante a cópia dos honestos não tem nenhum
   malicioso: líder, quórum e consenso são só deles.

O sinal só de consenso, sem gabarito, cai para 0 a partir de 50%.

## Hipóteses

### H1 — rotação: **parcial**

- **Aprovado.** Nenhum nó liderou duas rodadas seguidas: a maior sequência é 1
  em todas as células. Depois da calibração, nenhum malicioso foi eleito com
  todas as defesas (gráfico `lideranca_maliciosa`).
- **Reprovado.** A liderança não se distribui entre os honestos. Os dois
  maiores scores ficam com 76% a 98% das rodadas, e só 3 a 5 nós distintos
  lideram em 50 rodadas. A regra "maior score sem repetir o anterior" vira um
  revezamento entre o primeiro e o segundo colocados.
- **Para corrigir:** a eleição precisa de algo que espalhe o papel, como
  sorteio ponderado pelo score ou carência de várias rodadas.

### H2 — forja: **aprovada**

- Com massa honesta acima de 0.5 (até 50% de maliciosos), nenhum registro
  forjado foi aceito. A forja só derruba a rodada do próprio líder malicioso:
  há 1 rodada anulada por execução e nenhuma forja aceita.
- Com o conluio em maioria (57% ou mais), a forja da rodada 1 passa no quórum
  da cópia original. É justamente isso que dispara a divisão descrita acima.

### H3 — veto falso do auditor: **aprovada**

O auditor malicioso que recusa propostas honestas alegando forja nunca anulou
uma rodada: 0 rodadas anuladas em todas as células do bloco `auditor`. O
quórum decide, e o recálculo mostra que a proposta é coerente. O auditor é
punido a cada veto e termina com reputação entre 0.015 e 0.019 com todas as
defesas.

Com 10 e 20 nós e todas as defesas, um malicioso quase nunca é escolhido
auditor depois da calibração: 0% das rodadas. Em 7 nós com 57%, ele é auditor
em 60% das rodadas e acumula 29,6 penalidades por execução. A causa é o grafo:
no 4-regular de 7 nós, só 2 nós ficam a 2 saltos do líder, e a regra pega o
melhor desses 2 mesmo que tenha reputação baixa. O efeito é inofensivo, porque
a acurácia de teste fica em 0.960 e nenhuma rodada é anulada, mas o papel de
auditor fica sem uso.

### H4 — censura: **aprovada**

Até 50% de maliciosos, nenhuma rodada com respostas honestas removidas fechou
quórum (0 censuras aceitas). Cada honesto censurado vê que a própria resposta
não está no registro e vota contra. Acima de 50% vale o mesmo que na forja: o
conluio aprova a censura na rodada 1 e os honestos saem com a própria cópia.

### H5 — só consenso, sem gabarito: **reprovada, como previsto**

| Nós | Maliciosos | Híbrido: testes | Híbrido: massa maliciosa | Só consenso: testes | Só consenso: massa maliciosa | Só consenso: rodadas com líder malicioso |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 25% | 1.000 | 0.012 | 1.000 | 0.250 | 12 de 47 |
| 20 | 50% | 1.000 | 0.035 | 0.000 | 0.500 | 27 de 47 |
| 20 | 65% | 1.000 | 0.063 | 0.000 | 0.650 | 33 de 47 |
| 7 | 71% | 0.880 | 0.081 | 0.000 | 0.714 | 33 de 47 |

Sem gabarito, a reputação só mede concordância com o próprio consenso. O
conluio vota sempre igual e não perde nada. O poder de voto, que só se move
com o gabarito, fica parado em 0,5 para todos. Duas consequências:

- A massa maliciosa é exatamente a fração de maliciosos, e passa de 0.5 assim
  que a fração passa de 50%.
- A eleição nunca sai da largada e vira rodízio puro. Os maliciosos lideram na
  proporção do número deles.

A acurácia cai para 0 a partir de 50%, onde o empate de massa já basta para o
bloco igual vencer as respostas honestas espalhadas. O híbrido, que usa o
gabarito só em 8 das 50 rodadas (3 de calibração e 5 de teste), recupera para
1.000 em 20 nós.

### H6 — escala: **aprovada**

| Nós | 4-regular: saltos médios | 4-regular: diâmetro | 4-regular: conexões por nó | Completo: conexões por nó |
| ---: | ---: | ---: | ---: | ---: |
| 7 | 2.00 | 2 | 4 | 6 |
| 20 | 3.17 | 4 | 4 | 19 |
| 60 | 5.00 | 5 | 4 | 59 |
| 120 | 5.79 | 6 | 4 | 119 |

Os saltos crescem devagar (de 2 para 5,8 quando N vai de 7 para 120), e nenhum
nó abre mais que 4 conexões. No grafo completo é sempre 1 salto, mas cada nó
precisa de N−1 conexões. A acurácia de teste é 1.000 em todos os tamanhos.

### H7 — consistência das cópias: **aprovada**

- **Simulação.** Em todas as células, as cópias dos nós honestos terminam com
  a mesma cabeça de cadeia (0 cópias honestas divergentes).
- **Containers.** Cada nó guardou a própria cadeia e todas passaram na
  verificação de hash.
- **Paridade.** Os testes unitários mostram que as cópias por nó, rodando o
  mesmo código dos containers, terminam com as mesmas cadeias e reputações da
  rede simulada, inclusive quando há divisão.
- **Ressalva.** Com o conluio em maioria há duas cadeias no fim, por desenho:
  a dos honestos e a do conluio.

### H8 — conluio em maioria com todas as defesas: **aprovada, com ressalva**

O consenso ponderado se recupera no prazo do fixo ou antes, e o conluio não
lidera depois da calibração em nenhum caso:

- **20 nós, 50%:** recuperação na rodada 2.0, contra 1.9 no fixo.
- **20 nós, 65%:** rodada 2.0, contra 3.7 no fixo.
- **7 nós, 71%:** rodada 36.5, contra 36.7 no fixo.

A ressalva é como isso acontece. Acima de 50% a proteção é a divisão da rede,
e não o quórum. Na ablação, sem a recusa, 65% em 20 nós cai para 0.500 e 71%
em 7 nós cai para 0.380.

Em 7 nós com 71%, a cópia honesta tem só 2 nós. Quando um deles erra por ruído,
o consenso empata, e é daí que vêm o 0.880 e a recuperação tardia.

### H9 — o que cada defesa faz: **respondida**

Acurácia ponderada nas rodadas de teste, líder que forja (entre parênteses, o
líder que censura, quando difere):

| Preset | 20 nós, 50% | 20 nós, 65% | 7 nós, 71% |
| --- | ---: | ---: | ---: |
| nenhuma | 0.800 | 0.000 | 0.000 |
| só calibração | 1.000 (0.900) | 0.000 | 0.000 |
| só gabarito fora do quórum | 0.800 | 0.000 | 0.000 |
| só taxas separadas | 1.000 (0.800) | 0.000 | 0.000 |
| só dois scores | 0.800 | 0.000 | 0.000 |
| só recusa (divisão) | 1.000 (0.800) | 1.000 | 0.880 |
| todas | 1.000 | 1.000 | 0.880 |
| todas menos calibração | 0.960 (0.800) | 1.000 | 0.840 |
| todas menos gabarito fora | 1.000 | 1.000 | 0.880 |
| todas menos taxas | 1.000 (0.900) | 1.000 | 0.880 |
| todas menos dois scores | 1.000 | 1.000 | 0.880 |
| todas menos recusa | 1.000 | 0.500 (1.000) | 0.380 (0.880) |

Leitura por medida:

- **Recusa (divisão): necessária com o conluio em maioria.** Sozinha resolve
  65% e 71%. Removida, a acurácia cai pela metade na forja. Com censura o
  estrago é menor, porque censurar não entrega ao conluio uma reputação forjada
  em 1,0.
- **Calibração: necessária em 50%.** Separa os scores antes de o conluio se
  firmar. Removida, a censura em 50% cai para 0.800 e 71% cai para 0.840.
- **Taxas separadas: ajudam em 50%.** Sozinhas resolvem a forja em 50%;
  removidas de "todas", a censura em 50% cai para 0.900.
- **Gabarito fora do quórum e dois scores: redundantes nesta grade.** Sozinhos
  não mudam nada em relação a "nenhuma", e removê-los de "todas" também não.

Mesmo sem nenhuma defesa, 50% em 20 nós dá 0.800, e não 0. O empate de massa
não basta para o conluio fechar o quórum (precisa de mais da metade), então
parte das rodadas segue com propostas honestas.

## Containers × simulação

Os 5 cenários subiram em containers, com o nó conversando só com os vizinhos
(`NEIGHBORS`). Na mesma repetição, as contagens do protocolo batem com a
simulação em todos eles:

- líderes maliciosos, rodadas aceitas e anuladas;
- forjas e censuras aceitas;
- divisões e número de cadeias no fim;
- acurácia nas rodadas de teste, igual nos dois.

Diferem a reputação dos honestos, porque cada container sorteia com o próprio
gerador, e os saltos médios, um pouco maiores em containers. A árvore de
difusão segue a ordem de chegada das mensagens e nem sempre é a do menor
caminho: em 10 nós, 2.53 contra 2.07. Tabela completa em
[`docker_vs_simulacao.md`](docker_vs_simulacao.md).

## Decisões que mudaram em relação ao plano

- **Largada.** Termina quando o maior e o menor score de poder se afastam
  0,05, e não "maior menos o terceiro". Com a regra do plano, os scores dos
  honestos ficavam próximos e os maliciosos lideraram 15 rodadas em 25%.
- **Estrela.** `star` é o grafo completo, sem centro fixo, porque o "centro"
  passa a ser o líder da rodada.
- **Punição do líder.** Só acontece quando a anulação tem motivo verificável
  (forja ou consenso falso pelo recálculo, ou uma reclamação de censura). Uma
  rodada que só não junta quórum não pune ninguém.
- **Divisão e repasse.** Quem recusa um registro forjado aprovado sai com a
  própria cópia da cadeia. As mensagens passam por nós de outra cópia, que só
  repassam (como numa rede P2P); sem isso, os honestos que saíssem poderiam
  ficar ilhados no grafo. Os saltos contam esse caminho.
- **Bloco `auditor`.** Foi acrescentado à matriz, que não tinha ataque de
  auditor e por isso não testava a H3.
- **Script dos gráficos.** Os do dinâmico ficam em
  `scripts/export_graficos_dinamico.py`, para não mexer no gerador e nas
  figuras das rodadas de teste fixas.

## Limites conhecidos

- **Liderança concentrada** nos dois maiores scores (H1).
- **Votos sem assinatura.** Nos containers um líder malicioso poderia inventar
  confirmações na mensagem de `commit`. Cada nó refaz a decisão a partir dos
  votos que recebe, mas não verifica quem votou. Identidade e ataques Sybil
  ficam fora desta etapa.
- **Divisão não é consenso.** Depois da divisão, um cliente externo precisa
  saber qual cadeia seguir. Aqui quem decide é o juiz do experimento, que mede
  a acurácia na cópia seguida pela maioria dos honestos.
- **Sinal só de consenso** não se sustenta com o conluio na metade da rede ou
  mais (H5). Algum gabarito periódico continua necessário.
