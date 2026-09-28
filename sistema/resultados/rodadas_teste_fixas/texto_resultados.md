# Resultados com rodadas de teste fixas

Em todos os experimentos há um teste a cada 10 rodadas: 10, 20, 30, 40 e 50. A acurácia de teste é a média só nessas rodadas. Os valores abaixo são média de 10 sementes, mecanismo EMA, topologia em estrela. A rede de referência tem 20 nós, em que 65% corresponde a 13 nós maliciosos.

## 1. A comparação que mostra o método

Com 65% de nós maliciosos em conluio, a maioria simples fica em 0,000 nos cinco testes. O consenso ponderado pela reputação fica em 1,000 nesses mesmos testes. Treze nós votam o mesmo valor errado e sete votam a resposta certa. A maioria acompanha o bloco malicioso do início ao fim. O ponderado erra enquanto as reputações ainda são próximas e acerta depois que a reputação dos maliciosos cai.

Sem conluio, a acurácia fica em 1,000 em 0%, 25%, 50% e 65%, tanto no ponderado quanto na maioria. Cada malicioso erra com um valor diferente. Os honestos, com probabilidade 0,9 de acerto, concentram o voto na resposta certa. Por isso a acurácia parecia igual entre os cenários: sem um bloco único de votos errados, os dois consensos escolhem a mesma resposta, e a fração de maliciosos não separa as curvas.

A diferença aparece quando os maliciosos votam juntos. Em 20 nós, com conluio e EMA:

| Maliciosos | Acurácia ponderada nos testes | Acurácia da maioria nos testes |
| ---: | ---: | ---: |
| 25% | 1,000 | 1,000 |
| 50% | 1,000 | 0,340 |
| 65% | 1,000 | 0,000 |

Abaixo de 50% os honestos ainda são maioria, e os dois consensos acertam. Em 50% a maioria já cai para 0,340 nos testes. Em 65% ela zera, e o ponderado permanece em 1,000.

## 2. O que as linhas verticais mostram

As linhas verticais marcam as rodadas 10, 20, 30, 40 e 50 em todos os gráficos.

No cenário de 65% com conluio, a acurácia do consenso ponderado é 0,000 na rodada 1, 0,000 na rodada 2 e 0,900 na rodada 3. Da rodada 4 em diante ela fica em 1,000. A mudança de regime acontece antes da primeira linha vertical.

Nas rodadas 20 a 30 a média é 1,000. Na rodada 40 também é 1,000. Os testes 20, 30 e 40 caem no patamar já recuperado. Não há um segundo regime de acurácia nesse trecho. Nos cinco testes (10, 20, 30, 40 e 50) a acurácia ponderada é 1,000. A maioria permanece em 0,000, porque 13 votos iguais vencem 7.

O que ainda se move entre as rodadas 20 e 40 é a reputação, e pouco. A reputação média dos maliciosos está em 0,014 na rodada 10, em 0,000 na rodada 20 e em 0,000 na rodada 40. A dos honestos vai de 0,882 na rodada 20 a 0,909 na rodada 40.

## 3. O limite perto de 65%

Com 13 maliciosos em 20 (65%) votando em conluio, o método segue correto nos testes mesmo com os maliciosos em maioria numérica: acurácia ponderada 1,000 e acurácia da maioria 0,000.

O limite aparece um pouco acima disso. Em 7 nós, a fração nominal 0,65 vira 5 maliciosos em 7, ou seja, 71%. Nesse caso a acurácia ponderada nos testes cai para 0,880, e a da maioria continua em 0,000. Cerca de 65% ainda é um bom desempenho. Perto de 70%, em rede pequena, a margem começa a faltar.
