# Implementação da orientação de 22/10

Branch `a4-orientacao-22out`, a partir de `a4-calibracao-llm` (`6b28fda`).
Autora dos commits: Lara Andrade Carvalho &lt;laraandrade312@gmail.com&gt;.

As opções novas nascem desligadas. Com o padrão, o resultado das 480 execuções do banco não muda.

## Commits

| Etapa | Hash | Mensagem |
|---|---|---|
| 1 | `14e74381517ed47c1eb7e2c891057a7d7faee04a` | Acrescenta a distância relativa e o medoide, sem ligar isso ao protocolo. |
| 2 | `55350395966a5cfcedbcab6796cbe5b204efa455` | Acrescenta o consenso por distância, desligado por padrão. |
| 3 | `0f57dcad83a6962aba275b25a18b933fa892c50f` | Acrescenta a resposta maliciosa por ruído, desligada por padrão. |
| 4 | `e5b78aa5681e8320ea99c9a68a6269690eb8ed62` | Acrescenta o instável como marca sobre o perfil, desligada por padrão. |
| 5 | `81350d2953bebb6daea52c9114b9a5c8af20fa7e` | Acrescenta o malicioso que imita honesto nas primeiras rodadas, desligado por padrão. |
| 6 | `8040c2e2a663962a8c1c6f20905ca4053e3fd20f` | Acrescenta a auditoria sorteada e a reputação que sobe devagar, desligadas por padrão. |
| 7 | `0ca7424d49dae327571a59816ab0a3cb3f604b41` | Registra a fração exata dos honestos, a auditoria e os vetos do auditor. |
| 8 | `42ff60592a65c69d91999268ac5f67015e4e61df` | Acrescenta o teste curto das quatro configurações da comparação da gênese. |

## Testes

`python -m unittest discover -s sistema/tests -t .`

```
................................................................
----------------------------------------------------------------------
Ran 64 tests in 3.434s

OK
```

São os 49 testes que já existiam e 15 novos em `sistema/tests/test_orientacao_22out.py`. A saída completa está em `entrega_impl/testes.txt`.

## Regressão

`python -m sistema.scripts.rodar_com_banco --banco sistema/resultados/banco_llm/banco_smol.json --saida /tmp/regressao`

As 14 primeiras colunas de `/tmp/regressao/execucoes.csv` foram comparadas com `entrega_llm/04_experimentos/execucoes.csv`. Nas duas há 481 linhas. A comparação no código da etapa 7, com todas as opções novas desligadas, terminou em `regressao identica`.

A mesma identidade apareceu nas corridas feitas depois das etapas 1, 2 e 4. As etapas 5 e 6 não tiveram uma corrida isolada: a corrida da etapa 7 já as inclui, com as opções desligadas. O script da etapa 8 não entra nessa comparação.

## Dúvidas

O texto abaixo é o de `entrega_impl/DUVIDAS.md`. Não há `ERROS.md`.

1. O arquivo `prompt_cursor_validacao_orientacao.md` e a pasta `orientacao_22out/` não estavam no repositório nem na máquina. A implementação seguiu o prompt colado e o código do branch `a4-calibracao-llm`.

2. O sorteio de `σ` "entre −1 e +1", se fosse uniforme contínuo, pode deixar `|m| < 1000`. O teste pede `|m| ≥ 1000` em todos os 10.000 sorteios. `σ` ficou em {−1, +1}, que é o sinal da fórmula `resposta × 10^k ± 10^k`. `k` continua contínuo e uniforme em [3, 6]. Se a resposta base do banco vier vazia, a base usada na conta é 0, para o ruído não sair zero.

3. `--alpha-down` já existia, com padrão `None` (no `ema_asymmetric`, isso vale `alpha/2`). O padrão não foi trocado para 0,8. O `ema_slow_up` usa 0,8 na descida só quando o mecanismo é esse e a opção não foi passada. `--alpha-up` é novo, padrão 0,1. Os dois valem na atualização pelo gabarito. Na rodada comum, o `ema_slow_up` usa o α de consenso, como a EMA.

4. `pct_honest_exact` é o número de honestos com resposta igual ao gabarito dividido por todos os honestos da rodada, inclusive os que não responderam. `pct_honest_responded` usa o mesmo denominador. Sem honesto na rodada, a célula fica vazia.

5. O teste curto não fixa o tamanho da rede. Ficou em 50 nós e 50 rodadas, como os experimentos do banco. Sementes 0 e 1. Instável desligado. Conluio ligado nas quatro configurações. `com_genese` usa o preset `all`, sinal híbrido, calibração sem líder de 3 rodadas e gabarito fixo nas rodadas de teste. `sem_genese` e as duas auditorias usam sinal `consensus` e zero rodadas de calibração. A lista `audited_rounds` no `summary.json` usa o índice 0-based de `rounds.csv`.

6. No modo ruído, `collusion_value` não nulo continua significando conluio. O valor 999 não é enviado: o grupo sorteia uma base, um `k` e um sinal. O malicioso ainda consome o gerador principal como no modo fixo, e o ruído sai de `Random(f"{semente}:noise")`, para a sequência dos honestos não mudar quando a opção está desligada.

7. A marca de instável e o sorteio da auditoria usam geradores próprios, `Random(f"{semente}:unstable")` e `Random(f"{semente}:audit")`. Com as opções no padrão, esses geradores não são consultados.

## Teste curto

24 execuções: 4 configurações, frações 0, 0,5 e 0,8, sementes 0 e 1, banco do SmolLM3-3B. Saída em `entrega_impl/teste_curto/`. `n_audited` vazio significa que a configuração não usa auditoria sorteada. `audited_rounds` é o índice 0-based.

| config | fração | semente | com reputação (teste) | sem reputação (teste) | com reputação (todas) | auditadas | rodadas auditadas | média exata dos honestos | auditor malicioso | vetos |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| sem_genese | 0 | 0 | 1.0 | 1.0 | 0.86 |  |  | 0.7432 | 0 | 0 |
| sem_genese | 0 | 1 | 1.0 | 1.0 | 0.84 |  |  | 0.7372 | 0 | 0 |
| sem_genese | 0.5 | 0 | 0.8 | 0.4 | 0.84 |  |  | 0.7568 | 6 | 0 |
| sem_genese | 0.5 | 1 | 0.8 | 0.2 | 0.82 |  |  | 0.7376 | 6 | 0 |
| sem_genese | 0.8 | 0 | 1.0 | 0.0 | 0.84 |  |  | 0.756 | 6 | 0 |
| sem_genese | 0.8 | 1 | 1.0 | 0.0 | 0.86 |  |  | 0.726 | 6 | 0 |
| com_genese | 0 | 0 | 1.0 | 1.0 | 0.86 |  |  | 0.7432 | 0 | 0 |
| com_genese | 0 | 1 | 1.0 | 1.0 | 0.84 |  |  | 0.7372 | 0 | 0 |
| com_genese | 0.5 | 0 | 0.8 | 0.4 | 0.84 |  |  | 0.7568 | 3 | 0 |
| com_genese | 0.5 | 1 | 0.8 | 0.2 | 0.82 |  |  | 0.7376 | 3 | 0 |
| com_genese | 0.8 | 0 | 1.0 | 0.0 | 0.84 |  |  | 0.756 | 3 | 0 |
| com_genese | 0.8 | 1 | 1.0 | 0.0 | 0.86 |  |  | 0.726 | 3 | 0 |
| auditoria_sorteada_p10 | 0 | 0 | 1.0 | 1.0 | 0.86 | 2 | 7 23 | 0.7432 | 0 | 0 |
| auditoria_sorteada_p10 | 0 | 1 | 1.0 | 1.0 | 0.84 | 8 | 1 7 17 27 30 35 40 42 | 0.7372 | 0 | 0 |
| auditoria_sorteada_p10 | 0.5 | 0 | 0.8 | 0.4 | 0.84 | 2 | 7 23 | 0.7568 | 6 | 0 |
| auditoria_sorteada_p10 | 0.5 | 1 | 0.8 | 0.2 | 0.82 | 8 | 1 7 17 27 30 35 40 42 | 0.7376 | 6 | 0 |
| auditoria_sorteada_p10 | 0.8 | 0 | 1.0 | 0.0 | 0.84 | 2 | 7 23 | 0.756 | 6 | 0 |
| auditoria_sorteada_p10 | 0.8 | 1 | 1.0 | 0.0 | 0.86 | 8 | 1 7 17 27 30 35 40 42 | 0.726 | 6 | 0 |
| auditoria_sorteada_p20 | 0 | 0 | 1.0 | 1.0 | 0.86 | 11 | 5 7 8 13 18 22 23 34 38 41 43 | 0.7432 | 0 | 0 |
| auditoria_sorteada_p20 | 0 | 1 | 1.0 | 1.0 | 0.84 | 10 | 1 7 13 14 17 27 30 35 40 42 | 0.7372 | 0 | 0 |
| auditoria_sorteada_p20 | 0.5 | 0 | 0.8 | 0.4 | 0.84 | 11 | 5 7 8 13 18 22 23 34 38 41 43 | 0.7568 | 6 | 0 |
| auditoria_sorteada_p20 | 0.5 | 1 | 0.8 | 0.2 | 0.82 | 10 | 1 7 13 14 17 27 30 35 40 42 | 0.7376 | 6 | 0 |
| auditoria_sorteada_p20 | 0.8 | 0 | 1.0 | 0.0 | 0.84 | 11 | 5 7 8 13 18 22 23 34 38 41 43 | 0.756 | 6 | 0 |
| auditoria_sorteada_p20 | 0.8 | 1 | 1.0 | 0.0 | 0.86 | 10 | 1 7 13 14 17 27 30 35 40 42 | 0.726 | 6 | 0 |
