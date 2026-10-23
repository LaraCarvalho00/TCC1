# Comparação da gênese

Branch `a4-orientacao-22out`. Autora: Lara Andrade Carvalho &lt;laraandrade312@gmail.com&gt;.

## Commits

| Etapa | Hash | Mensagem |
|---|---|---|
| 1 | `8da18650bfe074151c5efc9325fcb4dd8261d66d` | Acrescenta o malicioso que conhece o calendário fixo, desligado por padrão. |
| 2 | `76a7114bfef9545c458842fe66ea0dca4bb62251` | Acrescenta a acurácia nas rodadas sem gabarito. |
| 3 | `d81c661d09f342da1e004157a767bbb48a8afa35` | Acrescenta o script da comparação entre gênese, auditoria e calendário. |

## Testes

`python -m unittest discover -s sistema/tests -t .`

```
....................................................................
----------------------------------------------------------------------
Ran 68 tests in 1.531s

OK
```

Os 64 testes que já existiam passam junto com 4 novos. A saída está em `entrega_comparacao/testes.txt`.

## Regressão

`python -m sistema.scripts.rodar_com_banco --banco sistema/resultados/banco_llm/banco_smol.json --saida /tmp/regressao`

As 14 primeiras colunas de `/tmp/regressao/execucoes.csv` e de `entrega_llm/04_experimentos/execucoes.csv` têm 481 linhas. A comparação depois da etapa 1 e a comparação depois da etapa 2 terminaram em `regressao identica`. A etapa 3 só acrescenta um script novo.

## Dúvidas

O texto abaixo é o de `entrega_comparacao/DUVIDAS.md`. Não há `ERROS.md`.

1. O teste de indistinguibilidade precisa de duas execuções iguais que só diferem nas rodadas auditadas. `run_simulation` sorteia esse conjunto a partir da semente, então a semente sozinha não separa os dois casos. Entrou `audited_rounds_override`, usado só quando o argumento vem preenchido. Sem ele, o sorteio continua o de `plan_audits`. A estratégia `knows_schedule` não lê esse conjunto nem `audited_rounds`.

2. `reputacao_por_rodada.csv` usa o checkpoint de `reputation_history.csv`. A coluna `rodada` vai de 0 a 50: 0 é a reputação inicial e 50 é o valor depois da última rodada (índice 49).

3. `execucoes.csv` ganhou a coluna `fracao_instavel`. O resumo agrupa por ela, e a divisão entre instáveis honestos e maliciosos muda de semente para semente. Nos blocos `respostas` e `forja` o valor é 0.

4. `auditoria_p20_ema` usa o preset `all`, inclusive o `split_alpha` (consenso 0,05 e gabarito 0,8). A diferença para `auditoria_p20` é só o mecanismo: `ema` no lugar de `ema_slow_up`.

5. `n_maliciosos` é `round(fração × 50)`, o mesmo arredondamento de `build_profiles`.

6. Uma rodada conta como calibração quando o sinal não é `consensus` e o índice é menor que `calibration_rounds`. No calendário híbrido fixo essas rodadas também são `oracle_round`. A acurácia sem gabarito deixa de fora as duas condições.

7. A coluna "sem reputação" usa o consenso de maioria já gravado na rodada. Com `consensus_mode="distance"`, esse valor é o medoide sem peso.

## Execução

`python -m sistema.scripts.rodar_comparacao_genese`

1.400 execuções em 471,1 s. O log está em `entrega_comparacao/log.txt`. Saídas em `sistema/resultados/orientacao_22out/`: `execucoes.csv` (1.400 linhas), `resumo.csv` (280 grupos) e `reputacao_por_rodada.csv` (14.280 linhas, rodadas 0 a 50). A pasta `brutos/` não entra no commit.

## Bloco `respostas`, com conluio

Acurácia sem gabarito, com reputação. Média ± desvio-padrão amostral das 5 sementes.

| Estratégia | Config | 35% | 50% | 65% | 80% |
|---|---|---|---|---|---|
| on_off | sem_genese | 0.844 ± 0.016733 | 0.092 ± 0.010954 | 0.092 ± 0.010954 | 0.092 ± 0.010954 |
| on_off | com_genese | 0.82854 ± 0.026072 | 0.8095 ± 0.0238 | 0.8095 ± 0.016829 | 0.79046 ± 0.039107 |
| on_off | auditoria_p10 | 0.85184 ± 0.01983 | 0.77568 ± 0.113009 | 0.71862 ± 0.278799 | 0.35376 ± 0.280364 |
| on_off | auditoria_p20 | 0.86188 ± 0.031524 | 0.78174 ± 0.121567 | 0.79714 ± 0.144605 | 0.75622 ± 0.111123 |
| on_off | auditoria_p20_ema | 0.86188 ± 0.031524 | 0.78174 ± 0.121567 | 0.79714 ± 0.144605 | 0.77162 ± 0.109813 |
| knows_schedule | sem_genese | 0.844 ± 0.016733 | 0.092 ± 0.010954 | 0.092 ± 0.010954 | 0.092 ± 0.010954 |
| knows_schedule | com_genese | 0.8476 ± 0.021327 | 0.09522 ± 0.093745 | 0.0476 ± 0.0 | 0.0476 ± 0.0 |
| knows_schedule | auditoria_p10 | 0.85184 ± 0.01983 | 0.77568 ± 0.113009 | 0.71862 ± 0.278799 | 0.35376 ± 0.280364 |
| knows_schedule | auditoria_p20 | 0.86188 ± 0.031524 | 0.78174 ± 0.121567 | 0.79714 ± 0.144605 | 0.75622 ± 0.111123 |
| knows_schedule | auditoria_p20_ema | 0.86188 ± 0.031524 | 0.78174 ± 0.121567 | 0.79714 ± 0.144605 | 0.77162 ± 0.109813 |
