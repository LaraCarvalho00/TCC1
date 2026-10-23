# Dúvidas do ruído sutil e da nota exata

Onde o pedido ficou ambíguo, ficou a opção que não muda os resultados antigos.

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
