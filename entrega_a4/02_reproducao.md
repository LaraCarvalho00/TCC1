# Etapa 2 — reprodução dos números do artigo A3

Commit em que os números foram gerados: `44190e7288cedc7d0d05313c3da555412763bc37`.

Comando:

```
cd "/Users/gabrielferraz/Desktop/Tcc Lara" && "/Users/gabrielferraz/Desktop/Tcc Lara/.venv/bin/python" entrega_a4/run_a4.py etapa2
```

Configuração, a mesma de `sistema/scripts/run_a3_n50.py:30-98`, com duas extensões pedidas para a A4: a fração 80% e o dinâmico sem gabarito nas cinco frações (o script do A3 só roda sem gabarito em 50% e 65%, e não roda 80%).

- 50 nós, 50 rodadas, sementes 0 a 4, `test_every=10` (rodadas de teste 10, 20, 30, 40 e 50).
- Conluio: `collusion_value=999` quando a fração é positiva (`run_a3_n50.py:66-67`).
- Honesto acerta com probabilidade 0,9 (`run_a3_n50.py:37`).
- Fixo com gabarito: `orchestration=fixed`, `signal=hybrid`, `defense=none`, `alpha=0,3`, topologia estrela.
- Dinâmico com gabarito: `orchestration=dynamic`, `signal=hybrid`, `defense=all` (calibração de 3 rodadas, α de consenso 0,05, α de gabarito 0,8), grafo 4-regular, líder `forge` se a fração é positiva.
- Dinâmico sem gabarito: igual ao dinâmico, com `signal=consensus`. Nesse sinal o código não aplica gabarito em rodada alguma (`sistema/core/protocol.py:144-150`).
- Acurácia de teste do protocolo: `consensus_accuracy_weighted_on_tests` (`sistema/core/metrics.py:391`).
- Desvio-padrão: amostral, divisor n−1, das 5 sementes. Tolerância do «confere»: ±0,005 sobre a média.

| Fração | Nós maliciosos (`round(fração × 50)`, `sistema/simulate.py:58`) |
| --- | --- |
| 0% | 0 |
| 25% | 12 |
| 50% | 25 |
| 65% | 32 |
| 80% | 40 |

Conferência interna série×resumo: 75/75 execuções com `check_ok=1`.

## Tabela pedida

| Afirmação do artigo A3 | Valor no artigo | Valor obtido (média ± desvio) | Confere? |
| --- | --- | --- | --- |
| Acurácia de teste, fixo com gabarito, 0% e 25% | 1 | 0%: 1,0000 ± 0,0000; 25%: 1,0000 ± 0,0000 | sim |
| Acurácia de teste, fixo com gabarito, 50%, 65% e 80% | 0 | 50%: 0,0000 ± 0,0000; 65%: 0,0000 ± 0,0000; 80%: 0,0000 ± 0,0000 | sim |
| Acurácia de teste, dinâmico com gabarito, todas as frações | 1 | 0%: 1,0000 ± 0,0000; 25%: 1,0000 ± 0,0000; 50%: 1,0000 ± 0,0000; 65%: 1,0000 ± 0,0000; 80%: 1,0000 ± 0,0000 | sim |
| Acurácia de teste, dinâmico sem gabarito, 50%, 65% e 80% | 1 | 50%: 1,0000 ± 0,0000; 65%: 1,0000 ± 0,0000; 80%: 1,0000 ± 0,0000 | sim |
| Dinâmico com gabarito: rodadas com líder malicioso, forjas aceitas, anulações e divisões (todas as frações) | 0, 0, 0, 0 | 0%: líder 0,00, forjas 0,00, anulações 0,00, divisões 0,00; 25%: líder 1,00, forjas 0,00, anulações 1,00, divisões 0,00; 50%: líder 1,00, forjas 0,00, anulações 1,00, divisões 0,00; 65%: líder 1,00, forjas 1,00, anulações 0,00, divisões 1,00; 80%: líder 1,00, forjas 1,00, anulações 0,00, divisões 1,00 | não |
| Dinâmico com gabarito: número de cadeias no fim | 1 | 0%: 1,00 ± 0,00; 25%: 1,00 ± 0,00; 50%: 1,00 ± 0,00; 65%: 2,00 ± 0,00; 80%: 2,00 ± 0,00 | não |
| Malicioso após as rodadas 1, 2 e 3 (dinâmico com gabarito) | 0,1 / 0,02 / 0,004 | 25%: 0,0500 / 0,0095 / 0,0018; 50%: 0,0500 / 0,0095 / 0,0018; 65%: 0,2000 / 0,2000 / 0,2000; 80%: 0,2000 / 0,2000 / 0,2000 | não |
| Soma do peso do conluio na rodada 4, em 50%, 65% e 80% | 0,1 / 0,13 / 0,16 | 50%: 0,0451 ± 0,0000; 65%: 6,4000 ± 0,0000; 80%: 8,0000 ± 0,0000 | não |
| Soma do peso dos honestos na rodada 4, em 50%, 65% e 80% | 21,8 / 16,5 / 9,3 | 50%: 21,8002 ± 0,9063; 65%: 16,5378 ± 0,7833; 80%: 9,3028 ± 0,6632 | não |
| 50% com gabarito: honesto e malicioso após a rodada 1 | 0,804 / 0,100 | 0,8040 ± 0,0750 / 0,0500 ± 0,0000 | não |
| 50% com gabarito: honesto e malicioso após a rodada 3 | 0,872 / 0,004 | 0,8720 ± 0,0363 / 0,0018 ± 0,0000 | sim |
| 50% sem gabarito: malicioso e honesto após a punição da rodada 1 | 0,250 / 0,500 | 0,2500 ± 0,0000 / 0,5000 ± 0,0000 | sim |
| 50% sem gabarito: médias na rodada 50 (honesto / malicioso) | 0,867 / 0,020 | 0,8667 ± 0,0080 / 0,0202 ± 0,0000 | sim |
| 50% sem gabarito: reputação de eleição do malicioso | 0,25 | 0,2500 ± 0,0000 | sim |
| 80% com gabarito: honesto após rodadas 1 e 3; médias na rodada 50 | 0,756 / 0,929; 0,980 / 0,000 | 0,7560 / 0,9303; 0,9804 / 0,2000 | não |
| 80% sem gabarito: médias na rodada 50 (honesto / malicioso) | 0,881 / 1 | 0,8811 ± 0,0106 / 1,0000 ± 0,0000 | sim |
| 65% e 80% sem gabarito: divisões e cadeias no fim | 1 divisão, 2 cadeias | 65%: divisões 1,00 ± 0,00, cadeias 2,00 ± 0,00; 80%: divisões 1,00 ± 0,00, cadeias 2,00 ± 0,00 | sim |
| Fixo: reputação média do malicioso na rodada 10 / rodadas 20–50 / pico antes da validação | 0,686 / 0,691 / 0,987 | 50%: após rodada 10 0,6859; média das rodadas 20 a 50 0,8933; média só nas rodadas 20, 30, 40 e 50 0,6912; pico nas rodadas 1 a 9 0,9798; pico nas rodadas 19, 29, 39 e 49 0,9875; 65%: após rodada 10 0,6859; média das rodadas 20 a 50 0,8933; média só nas rodadas 20, 30, 40 e 50 0,6912; pico nas rodadas 1 a 9 0,9798; pico nas rodadas 19, 29, 39 e 49 0,9875; 80%: após rodada 10 0,6859; média das rodadas 20 a 50 0,8933; média só nas rodadas 20, 30, 40 e 50 0,6912; pico nas rodadas 1 a 9 0,9798; pico nas rodadas 19, 29, 39 e 49 0,9875. Fração não indicada no pedido; valores em 50%, 65% e 80%. Confere na leitura literal (média de todas as rodadas 20–50 e pico das rodadas 1–9): não. Confere se 0,691 for o valor depois das validações 20/30/40/50 e 0,987 for o pico nas rodadas 19/29/39/49: sim. | não |
| Fixo, 50%: acurácia da maioria em todas as rodadas (média; mínimo–máximo) | 0,072; 0,04–0,10 | média 0,0720 ± 0,0228; mín 0,04; máx 0,10; sementes [0,04, 0,06, 0,08, 0,08, 0,10] | sim |

O código também conta o líder malicioso só a partir da rodada de índice `calibration_rounds` (`sistema/core/metrics.py:565-567`). Dinâmico com gabarito, essa conta por fração: 0%: 0,00 ± 0,00; 25%: 0,00 ± 0,00; 50%: 0,00 ± 0,00; 65%: 0,00 ± 0,00; 80%: 0,00 ± 0,00.

## Onde a acurácia do dinâmico é medida

A acurácia de teste do protocolo, no dinâmico, não é um novo consenso calculado no fim. É o valor que a cópia de referência gravou.

1. A cópia de referência é o grupo com mais nós não maliciosos; empate no tamanho fica com o grupo de `gid` menor (`sistema/core/network.py:105-110`).
2. `run_simulation` passa para o registro os membros desse grupo **depois** da rodada (`sistema/simulate.py:286`).
3. O consenso ponderado da rodada é a resposta adotada por um nó não malicioso dessa cópia. Se a rodada foi anulada ou o nó recusou o registro, essa resposta é `None` e a rodada conta como erro (`sistema/core/network.py:209` e `sistema/core/network.py:334-346`; o acerto está em `sistema/core/schemas.py:49-51`).
4. A maioria simples que o resumo chama de `consensus_accuracy_majority` é calculada sobre as respostas de **todos** os nós, não só da cópia de referência (`sistema/core/network.py:340-346`).
5. As colunas `test_weighted_referencia` e `test_majority_referencia` deste CSV são outro cálculo: os dois agregadores sobre as respostas dos membros da cópia de referência depois da rodada, com os pesos de antes da rodada. Rodada anulada não zera esse cálculo. A coluna do protocolo continua sendo a do item 3.

Arquivos: `02_execucoes.csv` (uma linha por execução), `02_resumo.csv` (média e desvio), `02_rodadas.csv` (uma linha por rodada, para as trajetórias).

## Leitura das células que ficam na fronteira da tolerância

A célula «honesto e malicioso após a rodada 3» em 50% com gabarito está como «sim» porque 0,0018 e 0,004 diferem de 0,0022, dentro de ±0,005. A série das três rodadas não é a do artigo: o código deu 0,0500 / 0,0095 / 0,0018, e o artigo lista 0,1 / 0,02 / 0,004. O 0,0500 da primeira rodada é a punição (α = 0,5, de 0,5 para 0,25) seguida do gabarito (α = 0,8, de 0,25 para 0,05), não um único passo de gabarito a partir de 0,5.

Na reputação do fixo, 0,6859 fecha com 0,686. O 0,6912 é a média só das rodadas 20, 30, 40 e 50, depois da validação. A média de todas as rodadas 20 a 50 é 0,8933. O 0,9875 é o pico nas rodadas 19, 29, 39 e 49. O pico das rodadas 1 a 9, antes da primeira validação, é 0,9798. Por isso a linha da tabela, na leitura literal, está como «não».

O líder malicioso contado só depois da calibração é 0 em todas as frações com gabarito. A contagem da tabela, que inclui a rodada 1, não é 0 a partir de 25%.
