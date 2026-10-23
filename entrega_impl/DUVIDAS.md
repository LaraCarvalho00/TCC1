# Dúvidas da implementação de 22/10

Onde o pedido ficou ambíguo, ficou a opção que não muda os resultados antigos.

1. O arquivo `prompt_cursor_validacao_orientacao.md` e a pasta `orientacao_22out/` não estavam no repositório nem na máquina. A implementação seguiu o prompt colado e o código do branch `a4-calibracao-llm`.

2. O sorteio de `σ` "entre −1 e +1", se fosse uniforme contínuo, pode deixar `|m| < 1000`. O teste pede `|m| ≥ 1000` em todos os 10.000 sorteios. `σ` ficou em {−1, +1}, que é o sinal da fórmula `resposta × 10^k ± 10^k`. `k` continua contínuo e uniforme em [3, 6]. Se a resposta base do banco vier vazia, a base usada na conta é 0, para o ruído não sair zero.

3. `--alpha-down` já existia, com padrão `None` (no `ema_asymmetric`, isso vale `alpha/2`). O padrão não foi trocado para 0,8. O `ema_slow_up` usa 0,8 na descida só quando o mecanismo é esse e a opção não foi passada. `--alpha-up` é novo, padrão 0,1. Os dois valem na atualização pelo gabarito. Na rodada comum, o `ema_slow_up` usa o α de consenso, como a EMA.

4. `pct_honest_exact` é o número de honestos com resposta igual ao gabarito dividido por todos os honestos da rodada, inclusive os que não responderam. `pct_honest_responded` usa o mesmo denominador. Sem honesto na rodada, a célula fica vazia.

5. O teste curto não fixa o tamanho da rede. Ficou em 50 nós e 50 rodadas, como os experimentos do banco. Sementes 0 e 1. Instável desligado. Conluio ligado nas quatro configurações. `com_genese` usa o preset `all`, sinal híbrido, calibração sem líder de 3 rodadas e gabarito fixo nas rodadas de teste. `sem_genese` e as duas auditorias usam sinal `consensus` e zero rodadas de calibração, para a métrica "depois da calibração" não pular três rodadas. A lista `audited_rounds` no `summary.json` usa o índice 0-based de `rounds.csv`.

6. No modo ruído, `collusion_value` não nulo continua significando conluio. O valor 999 não é enviado: o grupo sorteia uma base, um `k` e um sinal. O malicioso ainda consome o gerador principal como no modo fixo, e o ruído sai de `Random(f"{semente}:noise")`, para a sequência dos honestos não mudar quando a opção está desligada.

7. A marca de instável e o sorteio da auditoria usam geradores próprios, `Random(f"{semente}:unstable")` e `Random(f"{semente}:audit")`. Com as opções no padrão, esses geradores não são consultados.
