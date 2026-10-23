# Dúvidas da comparação da gênese

Onde o pedido ficou ambíguo, ficou a opção que não muda os resultados antigos.

1. O teste de indistinguibilidade precisa de duas execuções iguais que só diferem nas rodadas auditadas. `run_simulation` sorteia esse conjunto a partir da semente, então a semente sozinha não separa os dois casos. Entrou `audited_rounds_override`, usado só quando o argumento vem preenchido. Sem ele, o sorteio continua o de `plan_audits`. A estratégia `knows_schedule` não lê esse conjunto nem `audited_rounds`.

2. `reputacao_por_rodada.csv` usa o checkpoint de `reputation_history.csv`. A coluna `rodada` vai de 0 a 50: 0 é a reputação inicial e 50 é o valor depois da última rodada (índice 49).

3. `execucoes.csv` ganhou a coluna `fracao_instavel`. O resumo agrupa por ela, e a divisão entre instáveis honestos e maliciosos muda de semente para semente. Nos blocos `respostas` e `forja` o valor é 0.

4. `auditoria_p20_ema` usa o preset `all`, inclusive o `split_alpha` (consenso 0,05 e gabarito 0,8). A diferença para `auditoria_p20` é só o mecanismo: `ema` no lugar de `ema_slow_up`.

5. `n_maliciosos` é `round(fração × 50)`, o mesmo arredondamento de `build_profiles`.

6. Uma rodada conta como calibração quando o sinal não é `consensus` e o índice é menor que `calibration_rounds`. No calendário híbrido fixo essas rodadas também são `oracle_round`. A acurácia sem gabarito deixa de fora as duas condições.

7. A coluna "sem reputação" usa o consenso de maioria já gravado na rodada. Com `consensus_mode="distance"`, esse valor é o medoide sem peso.
