# Definições, equações e o que entra no artigo

Texto para a orientadora e para colar no artigo. Cobre o que ficou sem nome na última reunião: o que é cada tipo de rodada, as equações por trás dos gráficos, a limitação do malicioso errático, a distância entre o primeiro e o segundo score, e o risco de vizinhos pontuarem vizinhos.

O tamanho de referência continua **50 nós**. Os gráficos de 20 nós ilustram o mecanismo; a grade do artigo é a que vai até 50.

---

## 1. Nomes usados no texto

A reunião pediu para definir cada nome e dizer o que ele não cobre. Estes são os termos que já aparecem no artigo, nos gráficos e no orquestrador dinâmico.

| Nome | Definição | Não é |
| --- | --- | --- |
| **Rodada normal** | Uma tarefa enviada aos nós. O consenso usa as reputações já conhecidas. A reputação é atualizada depois, com o sinal daquela rodada. | Não é ponto de medida. Não é auditoria com gabarito. |
| **Rodada de teste** | Rodada normal cujo índice é múltiplo de 10 (rodadas 10, 20, 30, 40 e 50). A acurácia “de teste” é a média só nessas rodadas, para todos os experimentos serem comparados no mesmo ponto. A reputação continua sendo atualizada. As linhas verticais dos gráficos marcam essas rodadas. | Não usa um protocolo diferente. Não é a Rodada de Validação. |
| **Rodada de Validação** | Canal separado, já implementado no código da branch `reputacao-sem-ground-truth`. O orquestrador envia perguntas reservadas, o gabarito fica no avaliador, e a reputação de cada nó pode ser atualizada com \(s=1\) (acertou o gabarito) ou \(s=0\) (errou). Quem não responde não é penalizado: a reputação fica como está. O resultado dessa rodada não entra no consenso da rodada normal. | Não participou das 8.400 execuções do artigo. Não é sinônimo de rodada de teste. Não é o sinal que move a reputação no laço principal do artigo. |
| **Ground truth (gabarito)** | Resposta correta da tarefa GSM8K. Serve para fabricar o perfil na simulação e para calcular a acurácia do consenso depois da agregação. | No laço principal do artigo, não é o sinal \(s\) da reputação. Nos gráficos enviados da rede com orquestrador fixo e EMA, o gabarito ainda é o sinal. As duas coisas não podem ser lidas como o mesmo experimento. |
| **Consenso ponderado** | A resposta que reúne a maior soma de reputações. O peso de cada nó é a reputação de antes da rodada. | Não é um voto por nó. |
| **Maioria simples** | A resposta dita pelo maior número de nós, um voto cada. É a linha de base, sem memória. | Não usa reputação. |
| **Hold** | Se a fração de reputação concentrada na resposta vencedora fica abaixo de 0,55, a reputação de quem respondeu não muda naquela rodada. | Não é punição. Não é acerto. |
| **Conluio** | Todos os maliciosos devolvem o mesmo valor errado (999). | Não é o malicioso que erra com um valor diferente a cada vez. |
| **Score de consenso** | Peso da resposta do nó no consenso ponderado. Muda toda rodada. No orquestrador dinâmico, com a defesa “dois scores” ligada, é distinto do score de poder. | Não elege o líder. |
| **Score de poder** | Peso usado na eleição do líder e no quórum. Só muda com o gabarito e com punições. | Não é o peso do voto na resposta da tarefa. |
| **Orquestrador fixo** | Um processo central, sempre o mesmo, fala com todos os nós (estrela). | Não é eleito. É um ponto único de confiança. |
| **Orquestrador dinâmico** | A cada rodada a rede elege um líder entre os nós. Um auditor confere a conta. Cada nó guarda uma cadeia de registros. A rodada vale se quem confirma soma mais da metade da reputação de poder. | O código descrito (grafo, cadeia, eleição, defesas) não está no GitHub. O que segue sobre ele usa o resumo da implementação. |

Frase para o artigo, no lugar em que os dois nomes aparecem juntos:

> A **rodada de teste** é uma rodada normal marcada para medição (a cada 10 rodadas). A **Rodada de Validação** é uma auditoria opcional com gabarito, fora do consenso normal. Uma não substitui a outra. A grade de 8.400 execuções mede rodadas de teste e não executa Rodada de Validação.

---

## 2. Equações do que foi calculado

### 2.1 Consenso

Seja \(v_i\) a resposta do nó \(i\) e \(R_i^{(t)}\) a reputação antes da rodada. Ausência não entra na soma.

\[
\hat{v}_{\mathrm{pond}}
= \arg\max_{a} \sum_{i:\, v_i = a} R_i^{(t)}
\]

\[
\hat{v}_{\mathrm{maj}}
= \arg\max_{a} \bigl|\{i : v_i = a\}\bigr|
\]

A acurácia de um agregador em \(T\) rodadas é a fração em que o valor escolhido coincide com o gabarito. A acurácia de teste usa só \(t \in \{10,20,30,40,50\}\).

### 2.2 Reputação

\[
R_i^{(t+1)} = (1-\alpha)\, R_i^{(t)} + \alpha\, s_i^{(t)},
\qquad R_i^{(0)} = 0{,}5.
\]

O que muda entre os dois conjuntos de resultados é o sinal \(s\).

**Sinal dos gráficos enviados** (orquestrador fixo, EMA, \(\alpha = 0{,}3\)): \(s_i = 1\) se a resposta coincide com o gabarito, \(s_i = 0\) se erra ou não responde. Esse sinal é um oráculo. Ele explica por que, com 65% em conluio, a curva do ponderado sobe a 1 e a dos maliciosos cai a 0.

**Sinal do artigo** (grade de 8.400 execuções, \(\alpha = 0{,}25\), confiança mínima 0,55): \(s_i = 0\) se o nó não responde; \(s_i = 1\) se a resposta coincide com \(\hat{v}_{\mathrm{pond}}\) e a fração de peso no vencedor é pelo menos 0,55; \(s_i = 0\) se diverge desse consenso; se a fração fica abaixo de 0,55, a reputação não muda (hold). O gabarito não entra em \(s\).

Com o segundo sinal, um bloco em conluio que já venceu o consenso recebe \(s=1\) e o grupo honesto recebe \(s=0\). A reputação passa a reforçar o ataque. É o que a tabela do artigo mostra em \(N=50\) com conluio: 7,9% em 50% de maliciosos e 0% em 65% e 80%.

### 2.3 Por que o gráfico de 65% em conluio sobe na rodada 3

Rede de 20 nós, 13 maliciosos e 7 honestos, conluio no valor 999, \(\alpha=0{,}3\), sinal = gabarito. Cada honesto acerta com probabilidade 0,9, então o peso honesto esperado usa \(0{,}9 \times 7 = 6{,}3\) votos certos.

Malicioso sempre erra, então a média fecha em forma fechada:

\[
R_{\mathrm{m}}(k) = 0{,}5 \cdot (0{,}7)^{k}.
\]

Honesto com \(E[s]=0{,}9\), partindo de 0,5, converge para 0,9:

\[
R_{\mathrm{h}}(k) = 0{,}9 - 0{,}4 \cdot (0{,}7)^{k}.
\]

O ponderado acerta quando o peso honesto esperado passa o peso do conluio:

\[
6{,}3 \, R_{\mathrm{h}}(k) > 13 \, R_{\mathrm{m}}(k).
\]

| Atualizações \(k\) já aplicadas | \(R_{\mathrm{h}}\) | \(R_{\mathrm{m}}\) | Peso honesto | Peso do conluio | Quem vence a rodada \(k+1\) |
| ---: | ---: | ---: | ---: | ---: | --- |
| 0 | 0,500 | 0,500 | 3,15 | 6,50 | conluio |
| 1 | 0,620 | 0,350 | 3,91 | 4,55 | conluio |
| 2 | 0,704 | 0,245 | 4,44 | 3,19 | honestos |

A rodada 1 e a rodada 2 acompanham o conluio. A rodada 3 já usa as reputações depois de duas punições, e o ponderado vira. A acurácia medida na rodada 3 fica perto de 0,9 porque cada honesto ainda erra com probabilidade 0,1. Daí em diante \(R_{\mathrm{m}}\) continua caindo por \((1-\alpha)\) a cada rodada e, na rodada 10, \(0{,}5 \cdot (0{,}7)^{10} \approx 0{,}014\), que é o valor lido no gráfico de reputação.

A maioria não tem essa conta. Treze votos iguais vencem sete em toda rodada, então a acurácia da maioria permanece 0. As linhas verticais (10, 20, 30, 40, 50) caem todas depois da virada: por isso a acurácia de teste do ponderado é 1,000 e a da maioria é 0,000. A virada em si não aparece nessas linhas; aparece na equação acima.

Essa recuperação **depende do gabarito dentro de \(s\)**. Com o sinal do artigo (concordância com o consenso), a rodada 1 já entrega \(s=1\) aos 13 maliciosos, o hold não segura porque \(13/20 = 0{,}65 \geq 0{,}55\), e a desigualdade não se inverte.

### 2.4 Os outros gráficos, na mesma equação

**Sem conluio.** Cada malicioso erra com um valor distinto. O único valor repetido é o gabarito, concentrado pelos honestos. Ponderado e maioria escolhem o mesmo número, e a fração de maliciosos não separa as curvas. Por isso as quatro séries ficam sobrepostas em 1.

**Três mecanismos em 65% com conluio.** EMA (\(\alpha=0{,}3\)), EMA assimétrica (descida com \(\alpha/2\)) e Beta (\(a/(a+e)\), prior 1 e 1) usam o mesmo sinal de gabarito. Os três zeram o peso do conluio; a assimétrica desce mais devagar, e a curva laranja chega a 1 uma rodada depois. No teste (rodada 10 em diante) os três já estão em 1, então a rodada de teste não distingue o mecanismo. Quem distingue é a equação da descida nas rodadas 1 a 4.

**Liderança maliciosa.** Fração das rodadas em que o líder eleito é malicioso, no orquestrador dinâmico. Com todas as defesas ligadas a fração é 0 de 7 a 20 nós. Sem defesas, em 20 nós, a fração sobe com o percentual de maliciosos e chega a 1 perto de 65%. “Só consenso” (sem gabarito, rodízio) acompanha a própria fração de maliciosos, um pouco acima dela.

---

## 3. Limitação: o malicioso destes experimentos não é errático

O perfil malicioso erra em toda rodada. Sem conluio, o erro é um valor qualquer. Com conluio, é sempre 999. Não há rodada em que ele responda certo para preservar reputação.

Isso torna a separação de reputação mais limpa do que um ataque cuidadoso. Com sinal de gabarito e \(s=0\) permanente,

\[
R_{\mathrm{m}}(k) = R_{\mathrm{m}}(0)\,(1-\alpha)^{k}
\]

cai em progressão geométrica. Um malicioso errático, que acerta com probabilidade \(q>0\) para não se denunciar, converge para \(R^\* = q\), não para 0. Se \(q\) fica perto da taxa de acerto honesta (0,9), os dois grupos não se separam e o ponderado deixa de ter o que ponderar.

Esta limitação vale para os gráficos e para a grade do artigo. Nenhum dos dois mede um adversário que escolhe quando errar.

---

## 4. Cenário de borda: um nó começa com score melhor

Pergunta da reunião: se um nó começa à frente, qual estratégia usar, e quão distante o segundo score precisa estar para deixar de ser uma boa opção.

Um passo de EMA muda a ordem só quando o líder erra (\(s=0\)) e o segundo acerta (\(s=1\)):

\[
(1-\alpha)\,R_2 + \alpha > (1-\alpha)\,R_1
\quad\Longleftrightarrow\quad
R_1 - R_2 < \frac{\alpha}{1-\alpha}.
\]

Com \(\alpha = 0{,}3\), esse limite é \(0{,}3/0{,}7 \approx 0{,}43\). Com \(\alpha = 0{,}25\), é \(0{,}33\).

- Enquanto a diferença fica **abaixo** de \(\alpha/(1-\alpha)\), o segundo score ainda alcança o primeiro depois de um único erro do líder. Ele continua sendo uma opção razoável de líder.
- Quando a diferença fica **acima** de \(\alpha/(1-\alpha)\), um erro isolado do líder não entrega a dianteira. Aí o segundo deixa de ser uma boa opção para aquela rodada.

O limiar 0,05 usado na largada do orquestrador dinâmico (a rotação acaba quando o maior e o menor score se afastam 0,05) é bem menor que 0,43. Ele só marca que os scores deixaram de ser praticamente iguais. Não marca que o segundo ficou ruim. Por isso, assim que a rotação acaba, a regra “maior score, sem repetir o anterior” reveza os dois primeiros e eles ficam com 76% a 98% das rodadas: os honestos continuam dentro da faixa em que o segundo ainda seria uma boa opção, e a regra não usa essa faixa.

Estratégia coerente com a equação, para o próximo experimento:

1. Enquanto \(R_{(1)} - R_{(2)} < \alpha/(1-\alpha)\), o líder sai de um sorteio ponderado pelo score entre os nós disponíveis dentro dessa faixa. Assim a liderança não cola nos dois primeiros enquanto eles ainda são intercambiáveis.
2. Quando a diferença passa de \(\alpha/(1-\alpha)\), lidera o maior score. O segundo só volta se o primeiro errar o bastante para reentrar na faixa.
3. Um nó que **começa** com vantagem \(\delta\): com sinal de gabarito, a vantagem de um malicioso é temporária, porque \(R_{\mathrm{m}}(k)=R_{\mathrm{m}}(0)\,(1-\alpha)^{k}\) cruza o honesto em poucas rodadas mesmo partindo de 1. Com sinal de consenso, a mesma vantagem inicial, se for suficiente para o nó capturar a primeira rodada, se reforça: quem concordou com ele ganha \(s=1\). Nesse segundo caso a estratégia não é “esperar a EMA corrigir”. É impedir a captura antes dela, com Rodada de Validação nas primeiras rodadas ou com a recusa que divide a rede no orquestrador dinâmico.

---

## 5. Vizinhos pontuam vizinhos

Ideia: tirar o centro e deixar cada nó atualizar o score dos nós com quem fala.

\[
R_{i \leftarrow j}^{(t+1)}
= (1-\alpha)\, R_{i \leftarrow j}^{(t)} + \alpha\, s_{ij}^{(t)},
\]

em que \(s_{ij}=1\) quando a resposta de \(j\) coincide com o consenso que \(i\) vê na própria vizinhança.

A contrapartida é direta. Se os vizinhos de um malicioso são maliciosos e estão em conluio, \(s_{ij}=1\) dentro do grupo, e o score interno sobe para 1. O grupo se confirma sozinho. A topologia decide se isso acontece.

No grafo 4-regular já usado no orquestrador dinâmico, cada nó tem 4 vizinhos sorteados, e o nó não escolhe com quem se liga. A vizinhança de um nó é captura local quando 3 ou 4 vizinhos são maliciosos. Com fração \(p\) de maliciosos e grau 4, isso é uma binomial:

\[
P(\mathrm{Bin}(4,p) \geq 3)
= 4\, p^{3}(1-p) + p^{4}.
\]

| Fração de maliciosos | Chance de a vizinhança ter maioria maliciosa |
| ---: | ---: |
| 25% | 5% |
| 50% | 31% |
| 65% | 56% |

Abaixo de 50%, pontuar só os vizinhos ainda enxerga maioria honesta na maior parte dos nós. Em 65%, mais da metade das vizinhanças já confirma o conluio. Aí a topologia não “filtra” o malicioso: ela dá a ele vizinhos que também são maliciosos, e o score local os promove.

O que a topologia precisa fixar antes do experimento:

- O nó não escolhe os vizinhos. A lista sai do grafo da repetição (a mesma semente gera o mesmo grafo).
- O grau fica pequeno (4), para 50 nós não virarem um completo disfarçado.
- A leitura de “vizinhos pontuam vizinhos” fica restrita, neste ciclo, a \(p \leq 0{,}5\). Acima disso o mecanismo que segura é o da rede dividida (recusa), não o score local.
- \(N=50\) permanece o tamanho máximo desta entrega. Cinquenta já é uma rede pequena para a pergunta; não reduzimos.

---

## 6. O que mandar agora, e o que fica de fora

Entram nesta entrega:

1. A tabela de nomes da seção 1, dentro de Materiais e Métodos, antes dos resultados.
2. As equações da seção 2 ao lado dos gráficos, com o sinal \(s\) escrito em cima de cada figura (gabarito ou consenso).
3. O parágrafo da limitação do malicioso errático, na seção de limitações.
4. A regra \(\alpha/(1-\alpha)\) como critério do segundo score, no lugar do 0,05 sem derivação.
5. A tabela da vizinhança como o desenho de topologia que será testado em seguida, ainda sem resultado novo.
6. \(N=50\) como rede de referência da grade já calculada (10 tamanhos, até 50, 8.400 execuções).

Ficam de fora desta mensagem, para a análise ir direta ao ponto:

- a matriz inteira de 7, 10, 15 e 20 nós com os três mecanismos;
- gráficos em que ponderado e maioria coincidem (sem conluio);
- qualquer frase que trate rodada de teste e Rodada de Validação como a mesma coisa;
- resultado do orquestrador dinâmico como se o código já estivesse na branch `main`. Ele está no resumo da implementação; no GitHub, `main` coincide com este repositório, o artigo sem gabarito na reputação está em `reputacao-sem-ground-truth`, e a integração da Rodada de Validação está em `codex/integracao-validacao`.
