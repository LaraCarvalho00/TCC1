# Encaminhamento da orientação

Nota para a reunião. Responde aos três pedidos: cenários a partir dos trabalhos relacionados, gráficos da reputação e o que cada variável significa.

Os números do simulador são os do artigo já medido: 50 nós, 50 rodadas, cinco repetições, conluio no valor 999. Os números da literatura foram lidos em resumo, HTML ou PDF aberto. Onde o PDF é pago, a célula diz isso.

## Metodologia: de onde saem os cenários

A regra desta entrega é a frase pedida na reunião: o trabalho X testa isso; por isso este cenário entra. Entra só o que dois filtros deixam passar ao mesmo tempo. O primeiro é a literatura: o comportamento aparece numa avaliação já publicada, ou é o limite teórico que essa avaliação usa. O segundo é o código: o simulador já executa esse caso. Cenário que a literatura não avalia, ou que exigiria um mecanismo novo, não entra agora.

65% e 80% não são o cenário usual dos trabalhos abaixo. Ficam como ponto de quebra, acima de um terço de faltosos e acima da maioria. O resultado ruim permanece: no orquestrador fixo, com 50% de maliciosos, a acurácia de teste é 0.

### O que os trabalhos costumam supor

A avaliação publicada quase sempre para antes de um terço de faltosos, ou não varre a fração. O comportamento malicioso que eles trazem é mensagem arbitrária, réplica faltosa, envenenamento no treino, ou arquivo inautêntico. Nenhum deles agrega a mesma pergunta numérica com todos votando 999.

| Trabalho | Comportamento malicioso na avaliação | Fração | O que fazem com a reputação | O que não fazem |
| --- | --- | --- | --- | --- |
| Lamport et al., 1982 | General bizantino: mensagem arbitrária | Limite teórico: sem assinatura, acordo só com n ≥ 3f+1, isto é, menos de 1/3 | Não há reputação | Inferência, conluio numérico, líder eleito entre pares |
| Castro e Liskov, 1999 (PBFT) | Réplica arbitrária; líder faltoso é trocado | No máximo f faltosos, com n ≥ 3f+1 | Sem score. Troca de líder, não quarentena | Peso de voto por histórico; resposta de um modelo |
| Bouhata et al., 2025 | Revisão: envenenamento no treino e agregadores robustos | Não é um experimento com uma fração. O Krum, como agregador, pede n ≥ 2f+3 | Revisão, não um mecanismo deste trabalho | Inferência redundante da mesma pergunta |
| Wei e Liu, 2025 | Taxonomia: envenenamento e bizantino no treino; evasão na inferência | Não é experimento | Confiança como propriedade da arquitetura | Voto igual (999) na inferência redundante |
| Kamvar et al., 2003 (EigenTrust) | Arquivo inautêntico. Modelo A: cada malicioso sozinho. Modelo B: coletivo que se dá confiança alta. Há disfarce: às vezes entrega arquivo bom | Individuais de 0% a 70%, de 10 em 10. Base da tabela: 60 bons, 42 maliciosos, 3 pré-confiáveis | Isola na escolha do download. Não suspende por N rodadas. Poucos pares pré-confiáveis servem de âncora | Inferência; líder de rodada; gabarito de tarefa. O par bom deles erra cerca de 5% dos uploads |
| Chen et al., 2024 (arXiv:2407.19428) | Compartilhador malicioso na previsão de trajetória | O HTML aberto não fixa um percentual único | Opinião local do vizinho, mais recomendação. Não é timer de quarentena | A mesma pergunta para todos; conluio 999; livro com líder eleito |
| Raza, Badidi e El Harrouss, 2026 (*Smart Cities* 9(2), 27) | Envenenamento e gradiente manipulado; cliente que falta rodada | Não é varredura de 10% a 80%. No experimento, os clientes 25–30 entram como maliciosos a partir da rodada 3 | Seleção se a reputação é pelo menos 0,6. Corta a reputação e suspende por algumas rodadas (exemplo do texto: base de 2, teto de 20). Volta se o score passa de 0,6 | Inferência redundante; líder eleito; conluio acima de 50% |
| ur Rehman et al., 2023 (IEEE TNSM) | Participação maliciosa e contribuição injusta | O resumo diz que o ataque fica restrito a menos de 5%. A fração injetada não foi lida: o PDF é pago | Crédito por contribuição. Peso, não quarentena | Resposta numérica agregada; orquestrador de rodada |
| AutoDFL, 2025 (arXiv:2501.04331) | Sybil, falso relato, carona, conluio, difamação, *whitewashing* (identidade nova zera reputação baixa) | Premissa: pelo menos 2/3 dos nós se comportam bem (f < n/3). Sem varredura de 50% a 80% | Reputação pela utilidade do modelo | Não mede inferência redundante |
| McMahan et al., 2017; Kairouz et al., 2021; Bonawitz et al., 2019; Hazarika e Shah, 2024 | Não varrem conluio deste tipo | Sem fração maliciosa nossa | Sem score de voto na resposta agregada | O consenso ponderado deste trabalho |

Zhang et al., 2025 (SRFL, IEEE IoT Journal) e o SoK de IA descentralizada não entram na escolha: a fração do primeiro não está no resumo aberto, e o segundo é revisão. Docker e Kubernetes justificam o ambiente de execução, não o comportamento malicioso.

O honesto deste trabalho acerta com probabilidade 0,9. É o mesmo tipo de falha honesta do EigenTrust, em que o par bom devolve arquivo falso em cerca de 5% dos pedidos. O perfil instável do código não entra no artigo.

### O que dá para avaliar, e o que não dá

| Ideia da reunião | Decisão | Justificativa |
| --- | --- | --- |
| 0% e 25% de conluio | Entra | Abaixo de f < n/3 (Lamport, PBFT). EigenTrust começa em 0% e sobe de 10 em 10. O código já mede acurácia de teste 1 no fixo e no dinâmico com gabarito. |
| 50%, todos votam 999 | Entra | Maioria, ainda dentro da varredura do EigenTrust (até 70%) e acima do BFT clássico. É o primeiro empate da maioria simples. Fixo: acurácia de teste 0. Dinâmico sem gabarito: 1 por anulação de quórum na rodada 1. |
| Líder malicioso que forja o registro | Entra | O PBFT trata líder faltoso. Aqui o líder grava peso 1 para o conluio e 0 para os demais. É o ataque já executado no dinâmico. |
| Com gabarito nas rodadas fixas, e sem gabarito | Entra | O EigenTrust precisa de pares pré-confiáveis para quebrar o coletivo. Aqui a âncora é o gabarito externo: nas três primeiras rodadas do dinâmico com gabarito e nas rodadas 10, 20, 30, 40 e 50. Sem gabarito essa âncora não age. |
| Auditor que veta proposta honesta | Entra, como frase | O PBFT confirma por outra réplica, não só pelo líder. Na matriz dinâmica (`false_reject`) o veto não anula a rodada honesta e o auditor perde reputação. Não pede código novo. |
| 65% e 80% como cenário normal | Não | Ponto de quebra. A maioria simples já é 0: 32 contra 18, e 40 contra 10. Sem gabarito, o 1 medido é a cópia dos honestos, não um livro único. |
| Bloquear todo ex-líder | Não | O código não faz isso. Só o líder da rodada anterior fica de fora. Os honestos não se esgotam. |
| Quarentena: congelar, reduzir ou voltar a 0,5 | Não agora | Não está no código. O análogo publicado é Raza et al.: corte da reputação e suspensão por algumas rodadas, volta acima de 0,6. |
| Vizinhos julgam o nó | Não | Chen e EigenTrust começam na opinião local. Este trabalho usa um score só, o do livro. Adotar vizinho mudaria o objeto da comparação com o fixo. |
| Honesto instável no artigo | Não nesta entrega | O erro de 10% já dialoga com os cerca de 5% do EigenTrust. O perfil `--unstable` continua no código, fora do artigo. |
| Espalhar maliciosos no grafo | Não medir agora | Limite anotado: os maliciosos nascem como `node-0` … `node-k-1`. O 4-regular começa como anel por identificador e depois embaralha. A fração de vizinhos maliciosos não foi medida. |
| Líder sempre honesto | Não | A pergunta ficou em aberto. Não está isolada nos cinco. |
| Malicioso que acerta no começo para subir | Não | É o disfarce do EigenTrust e o *whitewashing* do AutoDFL. O perfil atual erra sempre e vota 999. |

### Frase para o texto

O PBFT e Lamport testam acordo com menos de um terço de faltosos; o EigenTrust testa arquivo inautêntico, sozinho ou em coletivo, de 0% a 70%, com alguns pares pré-confiáveis; Raza et al. cortam a reputação e suspendem o cliente malicioso em vez de deixá-lo votar. Optamos por 0%, 25% e 50% de conluio no valor 999, com líder que forja o registro, com e sem gabarito, porque esses são os comportamentos que esses trabalhos avaliam e que o simulador já executa. Medimos também 65% e 80% para localizar o ponto em que a maioria simples deixa de acertar e em que, sem gabarito, o livro único se divide. Não adotamos quarentena nem opinião de vizinho: a primeira não está no protocolo atual, e a segunda mudaria o score global do livro, que é o objeto da comparação com o orquestrador fixo.

## O que a reunião perguntou

| Anotação | Resposta com o que já foi medido |
| --- | --- |
| Se a reputação não sobe, o nó continua sendo o de maior reputação. Sortear mais vezes não pondera a frequência. | As duas frases batem com o código. Depois que a maior e a menor reputação de eleição se afastam 0,05, lidera o maior score. A eleição não conta mandatos. |
| Todos os honestos já foram orquestradores e ficam bloqueados; é preciso aumentar a rede. | Isso não ocorre. A única exclusão é o líder da rodada imediatamente anterior (`sistema/core/election.py`). Na rodada seguinte ele volta a poder liderar. O risco só apareceria se todos os ex-líderes fossem bloqueados por muitas rodadas. Com 65% sobram 18 honestos, e um cooldown longo os esgotaria. Não é o sistema de hoje. N permanece 50. |
| Vale a pena muito conluio? | Já rodou: 0, 25, 50, 65 e 80%, em 50 nós, 50 rodadas, cinco repetições. |
| Se o orquestrador fosse sempre honesto, muito conluio mudaria o resultado? | Ainda não foi isolado. Não entra nos cinco cenários. |
| Os honestos vencem nas melhores escolhas do dinâmico? | Vencem a resposta a partir da rodada 2, até 80%, com ou sem gabarito. Vencem o score dentro de um livro só em 50%. Em 65% e em 80% o 1 é a cópia dos 18 e dos 10 honestos. O conluio continua com a outra cópia. |
| É a auditoria que vira o jogo? | Não. Com gabarito, o empurrão das três primeiras rodadas é o gabarito com α = 0,8. Sem gabarito, é a recusa do registro forjado mais o quórum. O auditor que veta uma proposta honesta não anula essa rodada. |
| Quarentena: a reputação congela, reduz ou volta a 0,5? O nó se recupera? Os vizinhos opinam? | Quarentena não existe no código. Não há congelamento, redução nem reset. Vizinho não opina: a reputação é a do livro. |
| O honesto é sempre honesto? | Acerta com probabilidade 0,9. Não é instável no artigo. |
| Maliciosos juntos no grafo, e malicioso que quer chegar à cúpula. | O agrupamento inicial não foi medido como fração de vizinhos. Malicioso que às vezes acerta, para subir, não existe: ele vota 999 em toda rodada. |

## Gráficos

Os dois gráficos são os do artigo. Cada ponto do primeiro é a média das cinco repetições. As verticais T1 a T5 são as rodadas 10, 20, 30, 40 e 50. Quando há gabarito, essas rodadas também são validação.

![Acerto do consenso ponderado em 50%, 65% e 80%](artigo/figuras/acerto_por_rodada_50_65_80.png)

No acerto, o círculo é o fixo com gabarito, o triângulo é o dinâmico com gabarito e a estrela é o dinâmico sem gabarito. Nos três painéis o fixo fica em 0 da primeira à última rodada. No dinâmico, a rodada 1 erra e, da rodada 2 em diante, o consenso ponderado acerta. Em 50% há uma cadeia só: os 25 maliciosos não fecham o quórum e a rodada forjada é anulada. Em 65% o 1 é a cópia dos 18 honestos. Em 80% é a cópia dos 10. A maioria simples, contada sobre as 50 respostas, fica em 0 nesses dois casos.

![Peso médio do voto no dinâmico, em 50% e em 80%](artigo/figuras/reputacao_dinamico_50_e_80.png)

No peso do voto, o círculo azul é o honesto e o triângulo laranja é o malicioso. O fixo não está nesta figura. Em 50% as duas curvas estão na mesma cadeia. Com gabarito, a calibração separa na primeira rodada: honesto 0,804 e malicioso 0,050; na rodada 50, 0,878 e 0,000. Sem gabarito, a punição deixa o malicioso em 0,250 e o honesto em 0,500; na rodada 50, 0,867 e 0,020. Em 80% cada curva é a média na cópia daquele perfil. Com gabarito, o registro forjado grava 1 para o conluio e a validação puxa esse peso a 0,2: daí o dente de serra. Sem gabarito, o malicioso permanece em 1 na cópia dele, e o honesto chega a 0,881 na cópia dos 10.

Uma rodada com gabarito e α = 0,8 deixa cada malicioso com no máximo 0,2. Em 80% isso soma 40 × 0,2 = 8, contra cerca de 6,5 do lado dos 10 honestos. Essa conta não põe o honesto à frente dentro do mesmo livro.

## Equação e variáveis

A reputação de cada nó é a média móvel

```text
R_i^(t+1) = (1 − α) R_i^(t) + α s_i^(t)
```

Todo nó começa com R_i^(0) = 0,5.

| Símbolo | O que é | Valor neste trabalho |
| --- | --- | --- |
| R_i^(t) | Reputação do nó i antes da rodada t. É o peso usado no consenso dessa rodada. | Entre 0 e 1 |
| α | Quanto a rodada atual mexe no histórico. Perto de 1, esquece o passado. Perto de 0, quase não muda. | Fixo: 0,3 em toda rodada. Dinâmico: 0,05 quando o sinal é o consenso; 0,8 quando o sinal é o gabarito; 0,5 na punição de rodada anulada |
| s_i^(t) | Sinal da rodada. 1 se a resposta conta como certa para aquela regra; 0 se erra, diverge ou falta. | Consenso nas rodadas normais. Gabarito nas três primeiras rodadas do dinâmico com gabarito e nas rodadas 10, 20, 30, 40 e 50, quando há gabarito |
| Peso do voto | O R que entra na soma do consenso ponderado. | No dinâmico, é um dos dois scores |
| Reputação de eleição | O outro score. Só entra na eleição do líder e no quórum. | Na rodada normal aceita, não se mexe |

O consenso ponderado escolhe a resposta cuja soma de pesos é a maior. A maioria simples conta votos, sem peso. No empate, os dois ficam com o menor número. O valor 999 perde esse desempate nas dez tarefas da amostra, porque a resposta certa é menor que 999.

| Variável | Significado | Valor |
| --- | --- | --- |
| N | Nós de inferência. O orquestrador não entra na conta. | 50 |
| Rodadas | Uma execução inteira. | 50 |
| Repetições | Outro sorteio, mesma configuração. | 5, numeradas de 0 a 4 |
| Fração maliciosa | Arredondada para o inteiro mais próximo. | 0% (0), 25% (12), 50% (25), 65% (32), 80% (40) |
| Conluio | Todos os maliciosos devolvem o mesmo valor errado. | 999, quando a fração é positiva |
| Honesto | Probabilidade de acertar a resposta de referência. | 0,9 |
| Grafo | Quem fala com quem no dinâmico. | 4-regular |
| Margem 0,05 | Enquanto o maior e o menor score diferem menos que isso, a liderança gira. Não é a regra de quem passa a liderar. | 0,05 |
| Quórum | A soma das reputações de eleição de quem confirma tem de ser estritamente maior que a metade da soma. | Empate não confirma |
| Calibração | As três primeiras rodadas do dinâmico com gabarito. O líder ainda é eleito. O gabarito entra na reputação com α = 0,8. | 3 rodadas |
| T1–T5 | Rodadas de teste e, quando há gabarito, também de validação. | 10, 20, 30, 40, 50 |

Quarentena, opinião do vizinho, bloqueio de todos os ex-líderes, perfil instável e malicioso que às vezes acerta não entram na equação nem nesta série.
