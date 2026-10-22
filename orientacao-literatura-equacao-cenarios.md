# Orientação: literatura, equação e cenários

Material para a próxima reunião. Não muda o simulador nem o artigo. Os números da literatura abaixo foram lidos em resumo, HTML ou PDF aberto; onde o PDF é pago, a célula diz isso em vez de inventar um percentual.

## O que levar para a professora

- A eleição não bloqueia quem já foi orquestrador. Só o líder da rodada anterior fica de fora. Honestos não se esgotam.
- Conluio alto (50%, 65%, 80%) já foi medido. Com gabarito e gênese, os honestos vencem em livro único. Sem gabarito, em 65% e 80% o acerto 1 é a cópia dos honestos.
- A auditoria não é o que vira o jogo. O que vira, com gabarito, é a gênese (três rodadas sem líder, α = 0,8).
- Quarentena não existe no código. O análogo mais próximo na lista de vocês é Raza et al. (2026): corta a reputação e suspende o cliente por algumas rodadas.
- Os cenários que ficam, porque a literatura testa e o código já cobre, são os cinco da seção final. 65% e 80% ficam como ponto de quebra, não como “o que os papers costumam fazer”.

## Correção: reputação e escolha do orquestrador

A anotação dizia: se a reputação não sobe, o nó continua sendo o de maior reputação; se ele é sorteado mais vezes, a gente não pondera isso; e, no limite, todos os honestos já foram orquestradores e ficam bloqueados, o que desfavorece a rede.

As duas primeiras frases batem com o código. A terceira não.

Em [`sistema/core/election.py`](sistema/core/election.py), depois da largada (quando a maior e a menor reputação de eleição se afastam 0,05), lidera o maior score. A única exclusão é o líder da rodada imediatamente anterior:

```python
candidates = [n for n in pool if n != state.last_leader] or pool
```

Não há lista de “já liderou, então está bloqueado”. Em 50 nós, o honesto de maior reputação volta a poder liderar na rodada seguinte. Quem lidera muitas vezes não ganha nem perde reputação por causa da frequência: a eleição não conta mandatos.

O risco que a professora descreveu só aparece se vocês passarem a bloquear todos os ex-líderes por muitas rodadas. Aí, com 65% de maliciosos, sobram 18 honestos, e um cooldown longo os esgota. Isso não é o sistema de hoje. Na reunião, corrigir o ponto antes de discutir “aumentar a rede”.

## O que já está medido (não reabrir como se fosse dúvida)

| Pergunta da reunião | Resposta com os números do artigo |
| --- | --- |
| Vale a pena muito conluio? | Já rodou: 0, 25, 50, 65 e 80% em 50 nós, 50 rodadas, 5 repetições. |
| Com as melhores escolhas, os honestos vencem? | Com gabarito e gênese, a acurácia de teste é 1 até 80%, livro único, zero líder malicioso, zero forja, zero divisão. |
| Sem gabarito? | Em 50%, anulação de quórum. Em 65% e 80%, o 1 é a cópia dos 18 e dos 10 honestos, não um livro único. |
| É a auditoria que vira o jogo? | Não. Com gênese, o empurrão é o gabarito nas rodadas 1–3 (α = 0,8). Sem gênese, é a recusa do registro forjado mais o quórum. O auditor que veta à toa não anula rodada honesta (já medido na matriz dinâmica). |
| E se o líder fosse sempre honesto? | Ainda não foi isolado. Não entra nos cinco cenários desta rodada. |
| Quarentena? | Não existe no código. |
| Honesto é sempre honesto? | Acerta com probabilidade 0,9. O perfil instável existe (`--unstable`) e não entra no artigo. |
| Maliciosos juntos no grafo? | Os maliciosos nascem como `node-0` … `node-k-1`. O 4-regular começa como anel por identificador e depois embaralha. Ninguém mediu a fração de vizinhos maliciosos. |
| Malicioso que quer subir à cúpula? | Não existe. O malicioso erra sempre e vota 999. |

## Tabela da literatura

Colunas pedidas na reunião: ataque, fração, topologia, o que fazem com a reputação, o que não testam.

### O que entra (ataque, reputação ou consenso)

| Trabalho | O que eles chamam de malicioso | Fração que testam | Topologia | Reputação / quarentena | O que não testam |
| --- | --- | --- | --- | --- | --- |
| Lamport et al., 1982 | General bizantino: mensagem arbitrária | Limite teórico: sem assinatura, acordo só com n ≥ 3f+1 (menos de 1/3) | Réplicas de um serviço | Não há reputação | Inferência, conluio numérico, líder eleito entre pares |
| Castro e Liskov, 1999 (PBFT) | Réplica arbitrária; líder faltoso é trocado | O serviço continua com no máximo f faltosos em n ≥ 3f+1 | Réplicas com líder e confirmação em fases | Sem score. Troca de líder, não quarentena por reputação | Peso de voto por histórico; resposta de um modelo |
| Bouhata et al., 2025 | Revisão de BFT em aprendizado distribuído (envenenamento no treino, agregadores robustos) | Não é um experimento com uma fração só. O limite clássico de um agregador como o Krum é n ≥ 2f+3; isso é propriedade do agregador, não um número medido por Bouhata | Treinamento distribuído | Revisão, não um mecanismo nosso | Inferência redundante da mesma pergunta; orquestrador eleito |
| Wei e Liu, 2025 | Taxonomia: envenenamento e bizantino no treinamento; evasão na inferência | Não é experimento com uma fração | Arquitetura que coordena participantes | Confiança como propriedade da arquitetura | O ataque de voto igual (999) na inferência redundante |
| Kamvar et al., 2003 (EigenTrust) | Arquivo inautêntico. Modelo A: cada malicioso sozinho. Modelo B: coletivo que se dá confiança alta. Há disfarce (às vezes entrega arquivo bom) | Individuais: 0% a 70%, de 10 em 10. Base da tabela: 60 bons, 42 maliciosos, 3 pré-confiáveis | P2P; confiança local nas interações, depois global por autovetor | Isola na escolha do download (quem tem confiança 0 quase não é escolhido). Não é suspensão por N rodadas. Âncora: poucos pares pré-confiáveis | Inferência; líder de rodada; gabarito de tarefa. O honesto deles erra cerca de 5% dos uploads |
| Chen et al., 2024 (arXiv:2407.19428) | Compartilhador malicioso que atrapalha a previsão de trajetória | O HTML aberto não fixa um percentual único de “bad nodes” | Veículos, RSU, opinião entre vizinhos | Opinião local (confiança, desconfiança, incerteza) mais recomendação dos vizinhos. Agrupa por reputação; peso baixo vai para agregação rasa. Não é timer de quarentena | A mesma pergunta respondida por todos; conluio no valor 999; livro com líder eleito |
| McMahan et al., 2017 | Não é artigo de ataque. Dados não-IID e custo de comunicação | Sem fração maliciosa | Estrela: servidor agrega | Sem reputação | Bizantino, conluio, inferência redundante |
| Kairouz et al., 2021 | Revisão; robustez é problema em aberto | Não é uma fração | FL clássico | Revisão | Um protocolo de inferência |
| Bonawitz et al., 2019 | Sistema de FL em produção; agregação segura | Sem varredura de conluio | Servidor e celulares | Sem score de voto | O nosso consenso ponderado |
| Hazarika e Shah, 2024 | Compartilhar modelo em armazenamento imutável | Sem experimento de conluio nosso | Blockchain | Confiança no registro, não na resposta agregada | Acurácia contra gabarito |
| Raza, Badidi e El Harrouss, 2026 (*Smart Cities* 9(2), 27) | Envenenamento e gradiente manipulado; cliente que falta rodada | Não é uma varredura 10–80%. No experimento, os clientes 25–30 entram como maliciosos a partir da rodada 3 | FL veicular, servidor seleciona clientes | Seleção se reputação ≥ 0,6. Punição em dois tempos: corte da reputação (coeficiente citado 1,5) e suspensão temporária (exemplo do texto: base de 2 rodadas, teto de 20). Esquecimento se o cliente some | Inferência redundante; líder eleito; conluio acima de 50% |
| ur Rehman et al., 2023 (IEEE TNSM) | Participação maliciosa e contribuição injusta; detecção por atribuição de características | O resumo diz que o ataque fica restrito a menos de 5% e que a agregação é robusta a bizantinos. A fração injetada não foi lida: o PDF é pago | FL com blockchain, sem servidor único de agregação | Crédito por contribuição, relevância e passado. Peso, não quarentena | Resposta numérica agregada; orquestrador de rodada |
| AutoDFL, 2025 (arXiv:2501.04331) | Lista: Sybil, falso relato, carona (*free-riding*), conluio, inferência do modelo, difamação, *whitewashing* (sair e voltar com identidade nova para zerar reputação baixa) | Premissa da cadeia: pelo menos 2/3 dos nós de blockchain e do oráculo se comportam bem (f < n/3). Não há varredura de acurácia contra 50–80% | P2P + blockchain | Reputação pela utilidade do modelo. *Whitewashing* é o contrário da quarentena: reset por identidade nova | A simulação de reputação confirma o que a fórmula já faz (bom sobe, malicioso cai). Não mede inferência redundante |
| SRFL, Zhang et al., 2025 (IEEE IoT Journal) | Quem prejudica a estabilidade do aprendizado | A fração não está no resumo aberto (IEEE pago). Não usar um percentual | Comitê DAO, aprendizado federado autonômico | Recompensa e punição hierárquicas (“swarm reputation”) | Não dá para citar fração nem quarentena até abrir o PDF |
| SoK DeAI (a entrada da lista de selecionados) | Sistematização de ataques no ciclo de IA descentralizada | Não é um experimento | Vários | Revisão | Não substitui uma linha com fração |

### O que fica fora desta tabela

Não avaliam ataque, reputação nem consenso. Não servem para justificar cenário.

- Adoção de IA generativa em engenharia de software (arXiv:2512.23327).
- Clones de modelos de processo no GitHub (EMSE, 2025).
- Benchmark de datasets de modelo (arXiv:2603.05250).
- Desafios de teste de sistemas IoT (o link da lista não é um experimento de conluio).

Docker e Kubernetes, no artigo, justificam o ambiente, não o comportamento malicioso.

## O que a literatura costuma supor (para a escrita)

- **Fração.** BFT clássico para antes de 1/3. Agregador robusto de treino (Krum) pede n ≥ 2f+3. FL com reputação que vocês listaram ou não varre fração (Chen, AutoDFL) ou fica em poucos maliciosos injetados (Raza: seis clientes) ou afirma robustez sem abrir a fração injetada (ur Rehman: ataque contido abaixo de 5% no resumo). EigenTrust é a exceção: chega a 70%, mas em download de arquivo, com pares pré-confiáveis.
- Por isso 65% e 80% não são “o cenário da literatura”. São o ponto de quebra, acima de f < n/3 e acima da maioria. A frase para o texto: o trabalho X testa até a minoria bizantina (ou até 70% no EigenTrust, com âncora pré-confiável); nós medimos 25% e 50% por causa disso, e 65% e 80% para ver onde o consenso ponderado deixa de ser o da rede inteira.
- **Quarentena.** Ninguém da lista congela, reduz um pouco ou reseta para 0,5 como três opções nossas. O que existe de perto é Raza et al.: corta a reputação e suspende por algumas rodadas, e o cliente volta se o score passar de 0,6. EigenTrust só deixa de escolher quem tem confiança baixa. AutoDFL avisa o risco oposto: identidade nova zera o histórico (*whitewashing*).
- **Vizinhos.** Chen e EigenTrust começam na opinião local. O artigo de vocês usa reputação global no livro. Isso se recusa por escrito, não se implementa agora: “não adotamos opinião de vizinho porque o consenso usa um score só, o do livro; EigenTrust e Chen fazem o contrário”.
- **Honesto imperfeito.** EigenTrust: o par bom devolve arquivo falso em cerca de 5% dos pedidos. O honesto deste TCC acerta com 0,9 (10% de erro). Dá para citar como o mesmo tipo de falha honesta, sem precisar do perfil instável no artigo.
- **Malicioso que sobe.** EigenTrust tem disfarce (nem sempre entrega arquivo ruim). AutoDFL tem carona e *whitewashing*. O perfil atual (sempre 999) é o modelo A do EigenTrust, o mais simples. O *on-off* fica para depois, e só se a banca pedir o disfarce.

## Glossário: equação e variáveis

Uma página. É o que a reunião pediu em “gráficos e equação” e “o que cada variável significa”. Os gráficos que já estão no artigo (acerto por rodada; reputação com bolinha = honesto e estrela = malicioso) continuam valendo. Não há figura nova.

### Equação

```text
R_i^(t+1) = (1 - α) R_i^(t) + α s_i^(t)
```

Todo nó começa com R_i^(0) = 0,5.

| Símbolo | O que é | Valor neste trabalho |
| --- | --- | --- |
| R_i^(t) | Reputação do nó i antes da rodada t. É o peso do voto nessa rodada. | Entre 0 e 1 |
| R_i^(t+1) | Reputação depois da atualização. Entra na rodada seguinte. | — |
| α | Quanto a rodada atual mexe no histórico. α perto de 1 esquece o passado; perto de 0 quase não muda. | Fixo: 0,3 em toda rodada. Dinâmico: 0,05 quando o sinal é o consenso; 0,8 quando o sinal é o gabarito (gênese ou validação); 0,5 na punição de rodada anulada |
| s_i^(t) | Sinal da rodada. 1 se a resposta conta como certa para aquela regra; 0 se erra, diverge ou falta. | Consenso nas rodadas normais. Gabarito na gênese (rodadas 1–3 do dinâmico com gabarito) e nas rodadas 10, 20, 30, 40 e 50 quando há gabarito |
| Peso do voto | O R que entra na soma do consenso ponderado. | No dinâmico, é um dos dois scores |
| Reputação de eleição | O outro score. Só entra na eleição do líder e no quórum. | No dinâmico, separada do peso do voto. Na rodada normal aceita ela não se mexe |

O consenso ponderado escolhe a resposta cuja soma de pesos é a maior. A maioria simples conta votos, sem peso. No empate, os dois ficam com o menor número. O valor de conluio 999 perde esse desempate nas dez tarefas da amostra, porque a resposta certa é menor que 999.

### Variáveis do experimento (as que já entram no artigo)

| Variável | Significado | Valor |
| --- | --- | --- |
| N | Nós de inferência. O orquestrador não entra na conta. | 50 |
| Rodadas | Uma execução inteira. | 50 |
| Repetições | Outro sorteio, mesma configuração. | 5 (sementes 0 a 4) |
| Fração maliciosa | Arredondamento para o par mais próximo. | 0% (0), 25% (12), 50% (25), 65% (32), 80% (40) |
| Conluio | Todos os maliciosos devolvem o mesmo valor errado. | 999, quando a fração é positiva |
| Honesto | Acerta a resposta de referência com essa probabilidade. | 0,9 |
| Grafo | Quem fala com quem no dinâmico. | 4-regular |
| Margem 0,05 | Enquanto o maior e o menor score diferem menos que isso, a liderança gira. Não é a regra de “quem passa a liderar”. | 0,05 |
| Quórum | A soma das reputações de eleição de quem confirma tem de ser estritamente maior que a metade da soma. Empate não confirma. | Metade estrita |
| Gênese | Rodadas 1 a 3 do dinâmico com gabarito: sem líder, sem proposta, sem voto. O livro grava o gabarito com α = 0,8. | 3 rodadas |
| T1–T5 | Rodadas de teste e, quando há gabarito, também de validação. | 10, 20, 30, 40, 50 |
| Acurácia de teste | Fração dessas cinco rodadas em que o consenso ponderado coincide com o gabarito. | 0 ou 1 nas células do artigo |

### O que ainda não é variável

Quarentena, opinião do vizinho, cooldown de todos os ex-líderes, perfil instável, malicioso que às vezes acerta. Não aparecem na equação nem na tabela de experimentos.

## Cinco cenários que ficam

Critério da reunião: o trabalho X testa isso; por isso testamos estes. Só entra o que o código já cobre. Se um deles “ficar ruim”, o artigo já mostra isso (o fixo em 50% fica em 0) e a professora aceitou resultado ruim.

| # | Cenário | Por que, com base em quem | O que o código já fez |
| --- | --- | --- | --- |
| 1 | Sem maliciosos e com 25% em conluio | Abaixo de f < n/3 (Lamport, PBFT) e perto do que FL com reputação trata como minoria. EigenTrust começa em 0% e sobe de 10 em 10. | Acurácia de teste 1 no fixo e no dinâmico com gabarito. |
| 2 | 50% em conluio, todos votam 999 | Maioria, ainda dentro da varredura do EigenTrust (até 70%), acima do BFT clássico. É o primeiro ponto em que a maioria simples empata. | Fixo: acurácia de teste 0. Dinâmico com gênese: 1, livro único. Dinâmico sem gabarito: 1 por anulação na rodada 1. |
| 3 | Líder malicioso que forja o registro | PBFT trata líder faltoso. Aqui o líder grava peso 1 para o conluio. | É o ataque do dinâmico no artigo. Com gênese, zero forjas aceitas. Sem gabarito, a forja passa em 65% e 80%. |
| 4 | Com gabarito nas rodadas fixas versus sem gabarito | EigenTrust precisa de pares pré-confiáveis para quebrar o coletivo. A gênese é a âncora equivalente: gabarito externo nas três primeiras rodadas, antes de alguém liderar. | As duas colunas dinâmicas do artigo. Sem gabarito a gênese não age. |
| 5 | Auditor que veta uma proposta honesta | PBFT tem confirmação por outra réplica, não só pelo líder. | Já medido na matriz (`false_reject`): o veto não anula a rodada honesta e o auditor perde reputação. Não está no texto curto do artigo; uma frase basta. Não precisa de código novo. |

### O que não entra agora

Fica escrito como recusa ou como próximo passo, não como experimento desta semana.

| Ideia da reunião | Decisão |
| --- | --- |
| 65% e 80% como cenário “normal” | Não. Ficam no artigo como ponto de quebra, com a frase da seção de literatura. A maioria simples já é 0 (32 contra 18, 40 contra 10). |
| Bloquear todo ex-líder | Não. O código não faz isso, e em rede de 50 nós o honesto não se esgota. |
| Quarentena (congelar, reduzir ou resetar para 0,5) | Não inventar as três. Se for implementar depois, a regra citada é a de Raza et al.: corte da reputação e suspensão por algumas rodadas, volta se o score passar de 0,6. |
| Vizinhos julgam o nó novo | Não. Reputação global no livro. Chen e EigenTrust fazem local; a recusa fica na escrita. |
| Honesto instável no artigo | Não nesta rodada. O erro de 10% já dialoga com os 5% de arquivo falso do EigenTrust. O perfil `--unstable` continua no código, fora do artigo. |
| Espalhar maliciosos no grafo para não ficarem juntos | Não medir agora. Anotar como limite: o anel inicial agrupa `node-0`…`node-k-1` antes do embaralhamento. |
| Forçar líder sempre honesto | Não. A pergunta ficou em aberto; não está isolada nos cinco. |
| Malicioso que acerta no começo para chegar à cúpula | Não. É o disfarce do EigenTrust. O perfil atual é sempre 999. |

## Frase para o texto

O PBFT e Lamport testam acordo com menos de um terço de faltosos; o EigenTrust testa arquivo inautêntico, sozinho ou em coletivo, de 0% a 70%, com alguns pares pré-confiáveis; Raza et al. cortam a reputação e suspendem o cliente malicioso em vez de deixá-lo votar. Optamos por 0%, 25% e 50% de conluio no valor 999, com líder que forja o registro, com e sem gabarito, porque esses são os comportamentos que esses trabalhos avaliam e que o simulador já executa. Medimos também 65% e 80% para localizar o ponto em que a maioria simples deixa de acertar e em que, sem gabarito, o livro único se divide. Não adotamos quarentena nem opinião de vizinho: a primeira não está no protocolo atual, e a segunda mudaria o score global do livro, que é o objeto da comparação com o orquestrador fixo.
