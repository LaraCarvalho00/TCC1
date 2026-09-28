# Análise com rodadas de teste fixas

Calendário usado em todos os experimentos: uma rodada de teste a cada 10 rodadas (10, 20, 30, 40 e 50). A acurácia de teste é a média só nessas rodadas. A acurácia de todas as rodadas permanece registrada para comparação.

A rede de 20 nós é a referência dos gráficos porque 65% corresponde exatamente a 13 nós maliciosos. Nas outras redes a fração nominal 0,65 cai no inteiro mais próximo (por exemplo, 6 de 10 nós = 60%, 10 de 15 = 66,7%, 5 de 7 = 71,4%).

## Por que a acurácia parecia igual entre os cenários

Sem conluio, cada nó malicioso erra com um valor diferente. Os honestos, com probabilidade 0,9 de acerto, concentram o voto na resposta certa. A maioria e o consenso ponderado continuam escolhendo essa resposta mesmo quando a fração de maliciosos sobe. A acurácia agregada em todas as rodadas fica então quase estável, e a diferença entre cenários some.

Com conluio, os maliciosos votam todos o mesmo valor errado. Abaixo de 50% os honestos ainda são maioria. Em 50% e em 65% a maioria simples acompanha o bloco malicioso. O consenso ponderado só se separa da maioria depois que a reputação dos maliciosos cai. Por isso a comparação que mostra o método é a do cenário com conluio, e não a média de todas as rodadas sem conluio.

### EMA, 20 nós, média de 10 sementes

| Conluio | Maliciosos | Acurácia ponderada (todas) | Acurácia ponderada (testes) | Acurácia da maioria (testes) |
| --- | ---: | ---: | ---: | ---: |
| não | 0% | 1.000 | 1.000 | 1.000 |
| não | 25% | 1.000 | 1.000 | 1.000 |
| não | 50% | 1.000 | 1.000 | 1.000 |
| não | 65% | 1.000 | 1.000 | 1.000 |
| sim | 25% | 1.000 | 1.000 | 1.000 |
| sim | 50% | 0.984 | 1.000 | 0.340 |
| sim | 65% | 0.958 | 1.000 | 0.000 |

## Rodadas 20 a 30 e a rodada 40

Com os testes na mesma rodada em todos os experimentos, a mudança de regime do consenso ponderado aparece antes da primeira linha vertical. Em 65% com conluio (EMA, 20 nós) a acurácia média é 0.000 na rodada 1, 0.000 na rodada 2 e 0.900 na rodada 3. Da rodada 4 em diante ela fica em 1,000.

Nas rodadas 20 a 30 a média continua 1.000; na rodada 40 também é 1.000. Não há um segundo regime de acurácia nesse trecho. Os testes 20, 30 e 40 caem todos no patamar já recuperado. Quando a rodada de teste era aleatória, um experimento podia ser avaliado ainda na queda inicial e outro já no patamar, e o gráfico misturava os dois comportamentos.

O que ainda se move entre 20 e 40 é a reputação, e pouco. Os maliciosos estão em 0.014 na rodada 10, 0.000 na 20 e 0.000 na 40. Os honestos vão de 0.882 na rodada 20 a 0.909 na 40. A maioria permanece em 0.000, porque 13 votos iguais vencem 7.

Acurácia ponderada nos testes (65%, conluio, EMA, 20 nós): rodada 10 = 1.000, rodada 20 = 1.000, rodada 30 = 1.000, rodada 40 = 1.000, rodada 50 = 1.000.

## Cerca de 65% de nós maliciosos

Com 13 maliciosos em 20 (65%) votando em conluio, a maioria simples não recupera: acurácia de teste 0.000. O consenso ponderado chega a 1.000 nas cinco rodadas de teste. O método segue correto mesmo com os maliciosos em maioria numérica.

O limite aparece um pouco acima disso. Em 7 nós, a fração nominal 0,65 vira 5 maliciosos em 7 (71%). Aí a acurácia ponderada nos testes cai para 0.880, e a da maioria continua em 0. Cerca de 65% ainda é um bom desempenho; perto de 70% em rede pequena a margem começa a faltar.

## Outras redes

A mesma regra de teste (rodadas 10, 20, 30, 40 e 50) foi usada em 7, 10, 15 e 20 nós. A tabela abaixo é a acurácia ponderada só nos testes, com conluio e EMA.

| Nós | Maliciosos reais | Acurácia ponderada nos testes | Acurácia da maioria nos testes |
| ---: | ---: | ---: | ---: |
| 7 | 28.57% | 1.000 | 1.000 |
| 7 | 57.14% | 0.980 | 0.000 |
| 7 | 71.43% | 0.880 | 0.000 |
| 10 | 20.0% | 1.000 | 1.000 |
| 10 | 50.0% | 1.000 | 0.600 |
| 10 | 60.0% | 1.000 | 0.000 |
| 15 | 26.67% | 1.000 | 1.000 |
| 15 | 53.33% | 1.000 | 0.000 |
| 15 | 66.67% | 1.000 | 0.000 |
| 20 | 25.0% | 1.000 | 1.000 |
| 20 | 50.0% | 1.000 | 0.340 |
| 20 | 65.0% | 1.000 | 0.000 |

Outras topologias, além da estrela, ficam para o próximo ciclo de experimentos.

