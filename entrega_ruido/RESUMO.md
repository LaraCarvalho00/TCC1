# Ruído sutil e nota exata

Branch `a4-orientacao-22out`. Autora: Lara Andrade Carvalho &lt;laraandrade312@gmail.com&gt;.

## Commits

| Etapa | Hash | Mensagem |
|---|---|---|
| 1 | `d2b54be1a2f502cfd98a70b23fae14079551dc2a` | Acrescenta o ruído sutil a uma distância relativa fixa, desligado por padrão. |
| 2 | `d45981f2944a37685db100d174a274f9ca8dd60a` | Acrescenta a nota exata nas rodadas com gabarito, desligada por padrão. |
| 2b | `0201bd32b0e6719e184d976ad1e35efd48553330` | Acrescenta mediana e média como centro do consenso, desligadas por padrão. |
| 3 | `6234c9708cb20b05bf228628064eca9fffd91b31` | Acrescenta a comparação do ruído sutil e da nota no gabarito. |
| 3b | `269631f0044663e139f55eeab9d6a11a77636713` | Acrescenta a comparação entre medoide, mediana e média. |

## Testes

`python -m unittest discover -s sistema/tests -t .`

A suíte terminou em 70 testes depois da etapa 1, 71 depois da etapa 2 e 76 depois da etapa 2b. A saída final está em `entrega_ruido/testes.txt`:

```
............................................................................
----------------------------------------------------------------------
Ran 76 tests in 1.551s

OK
```

Os 68 testes que já existiam passam junto com os novos.

## Regressão

As três conferências rodaram no fim das etapas 1, 2 e 2b.

`python -m sistema.scripts.rodar_com_banco --banco sistema/resultados/banco_llm/banco_smol.json --saida /tmp/regressao`

As 14 primeiras colunas de `execucoes.csv` ficaram iguais às de `entrega_llm/04_experimentos/execucoes.csv` (481 linhas). As três vezes o resultado foi `regressao identica`.

`python -m sistema.scripts.rodar_comparacao_genese` numa pasta temporária.

O `execucoes.csv` ficou igual ao de `sistema/resultados/orientacao_22out/execucoes.csv`. As três vezes o resultado foi `comparacao identica`.

As etapas 3 e 3b só acrescentam scripts. O simulador que eles chamam é o da etapa 2b, já conferido nas três regressões. A suíte de 76 testes passou de novo depois desses scripts.

## Dúvidas

O texto abaixo é o de `entrega_ruido/DUVIDAS.md`.

1. No ruído relativo, uma base ausente (`None`) entra como zero e vira `+1` ou `−1`. É o mesmo tratamento do ruído multiplicativo. O pedido só descrevia `b == 0`.

2. A nota exata muda só as duas atualizações pelo gabarito em `apply_record`: o registro `oracle` e a calibração. O orquestrador fixo, quando o sinal da rodada é o gabarito, continua com `1 − d` dentro de `process_round`. Os experimentos desta entrega usam o orquestrador dinâmico, e o gabarito entra por `apply_record`.

3. `consensus_center` diferente de `medoid` é ignorado quando `consensus_mode` é `exact`. O caminho padrão continua o voto por igualdade.

4. Na mediana, reputação negativa pesa zero, como no medoide. "Chegue à metade" é a soma acumulada maior ou igual à metade da soma dos pesos. Se a soma dos pesos é zero, a primeira resposta ordenada é a escolhida.

5. Na média, se a soma dos pesos é zero, o valor é a média simples das respostas recebidas. Sem reputação, a média já é a simples.

6. Mediana e média deixam de fora a resposta ausente, porque ela não tem valor numérico. O medoide continua contando a ausência como distância 1.

7. Mediana e média não têm placar de votos. `margin` fica 0 e `is_tie` fica falso. O medoide continua nas funções que já existiam.

8. `mean_distance_to_truth_no_oracle` usa as mesmas rodadas da acurácia sem gabarito: `audited == 0` e `calibration == 0`. Resposta da rede vazia conta como distância 1. A média é arredondada em 6 casas. Sem essas rodadas, o valor é nulo.

9. `reputacao_por_rodada.csv` usa o checkpoint de `reputation_history.csv`. A coluna `rodada` vai de 0 a 50: 0 é a reputação inicial e 50 é o valor depois da última rodada (índice 49). As colunas novas entram na chave do grupo para não misturar ruído, nota e centro.

10. `n_maliciosos` é `round(fração × 50)`, o mesmo arredondamento de `build_profiles`.

11. Em `sem_genese` as duas notas são conferidas linha a linha, em todas as colunas menos `nota_gabarito`. O resultado dessa conferência vai no resumo e no log.

## Execução

`python -m sistema.scripts.rodar_ruido` e, em seguida, `python -m sistema.scripts.rodar_centros`.

2.560 execuções em 849,4 s e 960 execuções em 320,9 s. Tempo total: 1.170 s. O log está em `entrega_ruido/log.txt`.

`sem_genese` deu o mesmo resultado nas duas notas, nos 320 pares (4 ruídos × 2 conluios × 8 frações × 5 sementes). O log registra `sem_genese identico em 320 pares`.

Saídas do ruído, em `sistema/resultados/orientacao_22out_ruido/`: `execucoes.csv` (2.560 linhas), `resumo.csv` (512 grupos) e `reputacao_por_rodada.csv` (26.112 linhas, rodadas 0 a 50).

Saídas dos centros, em `sistema/resultados/orientacao_22out_centros/`: `execucoes.csv` (960 linhas), `resumo.csv` (192 grupos) e `reputacao_por_rodada.csv` (9.792 linhas, rodadas 0 a 50).

A pasta `brutos/` não entra no commit.

## Conluio, `auditoria_p20`

Acurácia sem gabarito, com reputação. Média ± desvio-padrão amostral das 5 sementes.

| Ruído | Nota no gabarito | 35% | 50% | 65% | 80% |
|---|---|---|---|---|---|
| alto | graded | 0.86188 ± 0.031524 | 0.78174 ± 0.121567 | 0.79714 ± 0.144605 | 0.75622 ± 0.111123 |
| alto | exact | 0.867 ± 0.0304 | 0.7565 ± 0.128514 | 0.72046 ± 0.126406 | 0.57854 ± 0.233386 |
| sutil_0.5 | graded | 0.81598 ± 0.053639 | 0.47878 ± 0.301694 | 0.1944 ± 0.140553 | 0.11246 ± 0.035001 |
| sutil_0.5 | exact | 0.857 ± 0.034988 | 0.76162 ± 0.116951 | 0.70494 ± 0.092578 | 0.4754 ± 0.063872 |
| sutil_0.2 | graded | 0.7753 ± 0.029844 | 0.29568 ± 0.234639 | 0.14798 ± 0.066347 | 0.10734 ± 0.028758 |
| sutil_0.2 | exact | 0.82662 ± 0.048576 | 0.74624 ± 0.110498 | 0.61406 ± 0.123447 | 0.4032 ± 0.037872 |
| sutil_0.05 | graded | 0.75466 ± 0.041827 | 0.27018 ± 0.194194 | 0.13772 ± 0.046339 | 0.10734 ± 0.028758 |
| sutil_0.05 | exact | 0.81624 ± 0.05551 | 0.7307 ± 0.117299 | 0.58286 ± 0.097068 | 0.38266 ± 0.029866 |

## Centros, conluio, `auditoria_p20`

Acurácia sem gabarito, com reputação, e distância média ao gabarito. Média ± desvio-padrão amostral das 5 sementes. A nota no gabarito é `exact`.

| Centro | Ruído | Medida | 35% | 50% | 65% | 80% |
|---|---|---|---|---|---|---|
| medoid | alto | acurácia sem gabarito | 0.867 ± 0.0304 | 0.7565 ± 0.128514 | 0.72046 ± 0.126406 | 0.57854 ± 0.233386 |
| medoid | alto | distância média ao gabarito | 0.062554 ± 0.01728 | 0.184966 ± 0.143189 | 0.234755 ± 0.132981 | 0.394553 ± 0.249892 |
| medoid | sutil_0.2 | acurácia sem gabarito | 0.82662 ± 0.048576 | 0.74624 ± 0.110498 | 0.61406 ± 0.123447 | 0.4032 ± 0.037872 |
| medoid | sutil_0.2 | distância média ao gabarito | 0.07501 ± 0.014002 | 0.096376 ± 0.032749 | 0.123257 ± 0.029334 | 0.171188 ± 0.013002 |
| median | alto | acurácia sem gabarito | 0.877 ± 0.057787 | 0.78174 ± 0.133804 | 0.787 ± 0.147505 | 0.62828 ± 0.170036 |
| median | alto | distância média ao gabarito | 0.052836 ± 0.023095 | 0.148182 ± 0.149897 | 0.17418 ± 0.144483 | 0.331768 ± 0.164112 |
| median | sutil_0.2 | acurácia sem gabarito | 0.83174 ± 0.052357 | 0.74112 ± 0.123277 | 0.62456 ± 0.147093 | 0.38294 ± 0.049485 |
| median | sutil_0.2 | distância média ao gabarito | 0.06835 ± 0.011994 | 0.095564 ± 0.035619 | 0.117543 ± 0.033255 | 0.169657 ± 0.015866 |
| mean | alto | acurácia sem gabarito | 0.03064 ± 0.011562 | 0.03064 ± 0.011562 | 0.03064 ± 0.011562 | 0.03064 ± 0.011562 |
| mean | alto | distância média ao gabarito | 0.892356 ± 0.026841 | 0.904888 ± 0.020404 | 0.906023 ± 0.020903 | 0.90634 ± 0.020924 |
| mean | sutil_0.2 | acurácia sem gabarito | 0.03064 ± 0.011562 | 0.03064 ± 0.011562 | 0.03064 ± 0.011562 | 0.03064 ± 0.011562 |
| mean | sutil_0.2 | distância média ao gabarito | 0.129286 ± 0.020019 | 0.138894 ± 0.020767 | 0.151192 ± 0.014263 | 0.179101 ± 0.016575 |
