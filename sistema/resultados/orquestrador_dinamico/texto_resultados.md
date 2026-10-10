# Resultados do orquestrador dinâmico

Nesta etapa o orquestrador fixo foi substituído por um líder eleito a cada rodada entre os próprios nós. A eleição usa a reputação gravada numa cadeia de registros encadeados por hash, que cada nó guarda e confere. O líder espalha a tarefa só pelos vizinhos de um grafo 4-regular, propõe o consenso ponderado e o novo estado de reputação, e a rodada só vale se os nós que confirmam somam mais da metade da reputação dos participantes. O gabarito entra nas 3 primeiras rodadas (calibração) e nas rodadas de teste (10, 20, 30, 40 e 50); nas demais a reputação acompanha o consenso. Os valores abaixo são média de 5 repetições e dos mecanismos beta e EMA assimétrica, com 50 rodadas por execução.

## 1. O dinâmico mantém o resultado do fixo

Com o líder malicioso tentando forjar o registro e todas as defesas ligadas, o consenso ponderado chega à mesma acurácia de teste do orquestrador fixo. Em 20 nós ela é 1,000 com 25%, 50% e 65% de maliciosos em conluio, como no fixo. Em 7 nós com 71% de maliciosos ela fica em 0,880, contra 0,900 no fixo.

A recuperação também acontece no mesmo prazo ou antes. Em 20 nós com 65%, o consenso ponderado não erra mais a partir da rodada 2,0 em média, contra 3,7 no fixo. Em 7 nós com 71%, a recuperação é na rodada 36,5, contra 36,7. Depois da calibração, nenhum líder eleito foi malicioso em nenhuma célula.

Com até 50% de maliciosos, nenhum registro forjado e nenhuma censura foram aceitos. A tentativa do líder malicioso só derruba a própria rodada. O auditor malicioso que veta propostas honestas nunca anulou uma rodada, porque o quórum decide e o recálculo mostra que a proposta é coerente. O veto sem fundamento custa reputação ao próprio auditor, que termina perto de 0,02.

## 2. Com o conluio em maioria, a proteção é a divisão da rede

Acima de 50%, o conluio tem mais da metade da reputação no início e aprova a primeira forja. Os honestos recusam o registro e seguem a própria cópia da cadeia. A rede se divide em duas, e a cópia dos honestos passa a ter só nós honestos. É nela que a acurácia volta a 1,000.

A ablação mostra que essa recusa é a defesa necessária com o conluio em maioria. Sozinha ela leva 65% em 20 nós a 1,000 e 71% em 7 nós a 0,880. Sem ela, mesmo com as outras quatro medidas, os mesmos casos caem para 0,500 e 0,380. A calibração e as taxas separadas para consenso e gabarito ajudam em 50%: removê-las faz a censura em 50% cair para 0,800 e 0,900. Tirar o gabarito do quórum ou separar o score de eleição do score de consenso não mudou o resultado nesta grade.

## 3. Sem gabarito o método não se sustenta

Com o sinal só de consenso, a reputação mede apenas concordância com a maioria ponderada. O conluio sempre vota igual e não perde reputação. A acurácia de teste cai para 0,000 a partir de 50% de maliciosos em 20 nós, e a massa de reputação maliciosa fica igual à fração de maliciosos. O sinal híbrido, que usa o gabarito em 8 das 50 rodadas, recupera para 1,000 nos mesmos cenários.

## 4. Escala e containers

No grafo 4-regular cada nó mantém 4 conexões, e o número médio de saltos da tarefa cresce devagar: 2,0 em 7 nós, 3,2 em 20, 5,0 em 60 e 5,8 em 120. No grafo completo é sempre 1 salto, mas cada nó precisa de N−1 conexões.

A mesma lógica rodou em containers, com cada nó conversando só com os vizinhos e guardando a própria cadeia. Em 4, 10 e 20 nós, as contagens do protocolo bateram com a simulação na mesma repetição, e todas as cadeias passaram na verificação de hash:

- líderes maliciosos;
- rodadas aceitas e anuladas;
- forjas aceitas;
- divisões da rede.

## 5. Limites encontrados

A regra "maior score sem repetir o líder anterior" impede a mesma liderança em duas rodadas seguidas, mas não distribui o papel: os dois maiores scores ficam com 76% a 98% das rodadas. Em 7 nós com 71%, a cópia honesta tem só 2 nós, e um erro de ruído de um deles já empata o consenso, o que explica o 0,880. Os votos ainda não são assinados, então identidade e ataques Sybil ficam para a próxima etapa.
