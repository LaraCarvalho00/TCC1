# Evolução da rede de 50 nós e impacto da validação


## Principais resultados

- **80% sem conluio / ema:** acurácia de 82.8% para 96.0%, ganho de 13.2 pontos percentuais.
- **80% sem conluio / ema_asymmetric:** acurácia de 82.8% para 96.0%, ganho de 13.2 pontos percentuais.
- **80% sem conluio / beta:** acurácia de 82.8% para 96.0%, ganho de 13.2 pontos percentuais.
- **60% e 80% com conluio:** acurácia permaneceu em 0% nos três mecanismos, apesar da correção imediata dos scores em cada teste. Duas perguntas por dez tarefas não foram suficientes neste modelo.

## Experimento realizado

Foram concluídas **540 execuções (270 pares)**, com 50 rodadas cada, dez sementes (0–9), três mecanismos (EMA, EMA assimétrica e Beta), 0/20/40/60/80% de maliciosos e variantes com/sem conluio. O cenário 0% não é duplicado. Cada execução começa com score 0,5. São **1350 eventos de validação e 135000 consultas individuais**.

A cada dez rodadas, cada nó recebe duas perguntas de uma partição reservada da amostra local do dataset. Os percentuais são cenários independentes, não uma invasão gradual dentro da mesma execução. Honestidade simulada: probabilidade de acerto 0,9; EMA alpha=0,3; confiança mínima 0,55.

**Natureza dos resultados:** respostas simuladas por perfil, como na matriz da Lara; não houve inferência de uma LLM. O simulador utiliza a resposta esperada para fabricar respostas conforme o perfil. Em execução HTTP real, o payload dos nós contém apenas identificador/pergunta. A atualização operacional não usa gabarito; o avaliador da validação usa. Este dataset não comprova o treinamento da LLM.

## Como interpretar as marcações

- Linhas verticais: validações concluídas após as rodadas 10, 20, 30, 40 e 50, somente na condição ligada.
- Reputação: símbolo vazio = antes do primeiro item do teste; cheio = depois do segundo. Segmento vertical = impacto imediato total.
- O consenso da rodada 10 ocorre antes do teste; o efeito possível começa na 11. A validação 50 altera o score final, mas não há rodada 51 para medir consenso posterior.
- Curvas: médias das dez sementes. Faixas: média ± 1,96 erro-padrão, aproximação descritiva com dez repetições. Não usar nós como repetições independentes.
- Painéis de acurácia mostram proporção de sementes corretas naquela rodada. Mapas de calor mostram cada nó da semente 0; todos os nós e sementes estão nos CSVs.

## Resultado agregado das 50 rodadas

| Conluio | Mecanismo | Maliciosos | Sem validação | Com validação | Ganho (p.p.) | Score honesto final | Score malicioso final |
|---|---|---:|---:|---:|---:|---:|---:|
| Não | ema | 0% | 100.0% | 100.0% | +0.0 | 0.898 |  |
| Não | ema | 20% | 100.0% | 100.0% | +0.0 | 0.891 | 0.000 |
| Não | ema | 40% | 100.0% | 100.0% | +0.0 | 0.907 | 0.000 |
| Não | ema | 60% | 100.0% | 100.0% | +0.0 | 0.888 | 0.000 |
| Não | ema | 80% | 82.8% | 96.0% | +13.2 | 0.894 | 0.000 |
| Não | ema_asymmetric | 0% | 100.0% | 100.0% | +0.0 | 0.946 |  |
| Não | ema_asymmetric | 20% | 100.0% | 100.0% | +0.0 | 0.942 | 0.000 |
| Não | ema_asymmetric | 40% | 100.0% | 100.0% | +0.0 | 0.951 | 0.000 |
| Não | ema_asymmetric | 60% | 100.0% | 100.0% | +0.0 | 0.940 | 0.001 |
| Não | ema_asymmetric | 80% | 82.8% | 96.0% | +13.2 | 0.944 | 0.023 |
| Não | beta | 0% | 100.0% | 100.0% | +0.0 | 0.886 |  |
| Não | beta | 20% | 100.0% | 100.0% | +0.0 | 0.884 | 0.016 |
| Não | beta | 40% | 100.0% | 100.0% | +0.0 | 0.890 | 0.016 |
| Não | beta | 60% | 100.0% | 100.0% | +0.0 | 0.886 | 0.019 |
| Não | beta | 80% | 82.8% | 96.0% | +13.2 | 0.880 | 0.034 |
| Sim | ema | 20% | 100.0% | 100.0% | +0.0 | 0.889 | 0.000 |
| Sim | ema | 40% | 100.0% | 100.0% | +0.0 | 0.889 | 0.000 |
| Sim | ema | 60% | 0.0% | 0.0% | +0.0 | 0.475 | 0.483 |
| Sim | ema | 80% | 0.0% | 0.0% | +0.0 | 0.463 | 0.483 |
| Sim | ema_asymmetric | 20% | 100.0% | 100.0% | +0.0 | 0.941 | 0.000 |
| Sim | ema_asymmetric | 40% | 100.0% | 100.0% | +0.0 | 0.942 | 0.000 |
| Sim | ema_asymmetric | 60% | 0.0% | 0.0% | +0.0 | 0.524 | 0.717 |
| Sim | ema_asymmetric | 80% | 0.0% | 0.0% | +0.0 | 0.513 | 0.717 |
| Sim | beta | 20% | 100.0% | 100.0% | +0.0 | 0.884 | 0.016 |
| Sim | beta | 40% | 100.0% | 100.0% | +0.0 | 0.890 | 0.016 |
| Sim | beta | 60% | 0.0% | 0.0% | +0.0 | 0.162 | 0.823 |
| Sim | beta | 80% | 0.0% | 0.0% | +0.0 | 0.161 | 0.823 |

## Impacto nos cenários com maioria maliciosa em conluio

- **60% / ema:** acurácia 0.0% → 0.0%; ganho +0.0 p.p.; peso malicioso final 60.4%. No primeiro teste: honest: 0.014 → 0.457 (Δ +0.443), malicious: 0.986 → 0.483 (Δ -0.503).
- **60% / ema_asymmetric:** acurácia 0.0% → 0.0%; ganho +0.0 p.p.; peso malicioso final 67.3%. No primeiro teste: honest: 0.098 → 0.505 (Δ +0.407), malicious: 0.986 → 0.712 (Δ -0.274).
- **60% / beta:** acurácia 0.0% → 0.0%; ganho +0.0 p.p.; peso malicioso final 88.4%. No primeiro teste: honest: 0.083 → 0.198 (Δ +0.114), malicious: 0.917 → 0.786 (Δ -0.131).
- **80% / ema:** acurácia 0.0% → 0.0%; ganho +0.0 p.p.; peso malicioso final 80.7%. No primeiro teste: honest: 0.014 → 0.453 (Δ +0.439), malicious: 0.986 → 0.483 (Δ -0.503).
- **80% / ema_asymmetric:** acurácia 0.0% → 0.0%; ganho +0.0 p.p.; peso malicioso final 84.8%. No primeiro teste: honest: 0.098 → 0.502 (Δ +0.404), malicious: 0.986 → 0.712 (Δ -0.274).
- **80% / beta:** acurácia 0.0% → 0.0%; ganho +0.0 p.p.; peso malicioso final 95.3%. No primeiro teste: honest: 0.083 → 0.196 (Δ +0.113), malicious: 0.917 → 0.786 (Δ -0.131).

Mudança imediata de score não garante recuperação do consenso. O efeito líquido depende das atualizações das dez tarefas normais entre testes, da frequência/quantidade de perguntas e do mecanismo. Os cenários sem conluio permitem que votos maliciosos se dispersem; acurácia alta nesse caso não prova resistência a uma maioria coordenada.

## Gráficos

### Acurácia do consenso — EMA · sem conluio · média de 10 sementes

![Acurácia do consenso — EMA · sem conluio · média de 10 sementes](graficos/acuracia_ema_sem_conluio.png)

[PDF vetorial](graficos/acuracia_ema_sem_conluio.pdf)

### Evolução dos scores — EMA · sem conluio · média de 10 sementes

![Evolução dos scores — EMA · sem conluio · média de 10 sementes](graficos/scores_ema_sem_conluio.png)

[PDF vetorial](graficos/scores_ema_sem_conluio.pdf)

### Influência dos nós maliciosos — EMA · sem conluio · média de 10 sementes

![Influência dos nós maliciosos — EMA · sem conluio · média de 10 sementes](graficos/influencia_ema_sem_conluio.png)

[PDF vetorial](graficos/influencia_ema_sem_conluio.pdf)

### Mudança de score causada por cada teste — EMA · sem conluio · média de 10 sementes

![Mudança de score causada por cada teste — EMA · sem conluio · média de 10 sementes](graficos/impacto_ema_sem_conluio.png)

[PDF vetorial](graficos/impacto_ema_sem_conluio.pdf)

### Ganho de acurácia após as validações — EMA · sem conluio · média de 10 sementes

![Ganho de acurácia após as validações — EMA · sem conluio · média de 10 sementes](graficos/janelas_ema_sem_conluio.png)

[PDF vetorial](graficos/janelas_ema_sem_conluio.pdf)

### Scores individuais — EMA · sem conluio · semente 0

![Scores individuais — EMA · sem conluio · semente 0](graficos/nos_ema_sem_conluio.png)

[PDF vetorial](graficos/nos_ema_sem_conluio.pdf)

### Acurácia do consenso — EMA assimétrica · sem conluio · média de 10 sementes

![Acurácia do consenso — EMA assimétrica · sem conluio · média de 10 sementes](graficos/acuracia_ema_asymmetric_sem_conluio.png)

[PDF vetorial](graficos/acuracia_ema_asymmetric_sem_conluio.pdf)

### Evolução dos scores — EMA assimétrica · sem conluio · média de 10 sementes

![Evolução dos scores — EMA assimétrica · sem conluio · média de 10 sementes](graficos/scores_ema_asymmetric_sem_conluio.png)

[PDF vetorial](graficos/scores_ema_asymmetric_sem_conluio.pdf)

### Influência dos nós maliciosos — EMA assimétrica · sem conluio · média de 10 sementes

![Influência dos nós maliciosos — EMA assimétrica · sem conluio · média de 10 sementes](graficos/influencia_ema_asymmetric_sem_conluio.png)

[PDF vetorial](graficos/influencia_ema_asymmetric_sem_conluio.pdf)

### Mudança de score causada por cada teste — EMA assimétrica · sem conluio · média de 10 sementes

![Mudança de score causada por cada teste — EMA assimétrica · sem conluio · média de 10 sementes](graficos/impacto_ema_asymmetric_sem_conluio.png)

[PDF vetorial](graficos/impacto_ema_asymmetric_sem_conluio.pdf)

### Ganho de acurácia após as validações — EMA assimétrica · sem conluio · média de 10 sementes

![Ganho de acurácia após as validações — EMA assimétrica · sem conluio · média de 10 sementes](graficos/janelas_ema_asymmetric_sem_conluio.png)

[PDF vetorial](graficos/janelas_ema_asymmetric_sem_conluio.pdf)

### Scores individuais — EMA assimétrica · sem conluio · semente 0

![Scores individuais — EMA assimétrica · sem conluio · semente 0](graficos/nos_ema_asymmetric_sem_conluio.png)

[PDF vetorial](graficos/nos_ema_asymmetric_sem_conluio.pdf)

### Acurácia do consenso — Beta · sem conluio · média de 10 sementes

![Acurácia do consenso — Beta · sem conluio · média de 10 sementes](graficos/acuracia_beta_sem_conluio.png)

[PDF vetorial](graficos/acuracia_beta_sem_conluio.pdf)

### Evolução dos scores — Beta · sem conluio · média de 10 sementes

![Evolução dos scores — Beta · sem conluio · média de 10 sementes](graficos/scores_beta_sem_conluio.png)

[PDF vetorial](graficos/scores_beta_sem_conluio.pdf)

### Influência dos nós maliciosos — Beta · sem conluio · média de 10 sementes

![Influência dos nós maliciosos — Beta · sem conluio · média de 10 sementes](graficos/influencia_beta_sem_conluio.png)

[PDF vetorial](graficos/influencia_beta_sem_conluio.pdf)

### Mudança de score causada por cada teste — Beta · sem conluio · média de 10 sementes

![Mudança de score causada por cada teste — Beta · sem conluio · média de 10 sementes](graficos/impacto_beta_sem_conluio.png)

[PDF vetorial](graficos/impacto_beta_sem_conluio.pdf)

### Ganho de acurácia após as validações — Beta · sem conluio · média de 10 sementes

![Ganho de acurácia após as validações — Beta · sem conluio · média de 10 sementes](graficos/janelas_beta_sem_conluio.png)

[PDF vetorial](graficos/janelas_beta_sem_conluio.pdf)

### Scores individuais — Beta · sem conluio · semente 0

![Scores individuais — Beta · sem conluio · semente 0](graficos/nos_beta_sem_conluio.png)

[PDF vetorial](graficos/nos_beta_sem_conluio.pdf)

### Acurácia do consenso — EMA · com conluio · média de 10 sementes

![Acurácia do consenso — EMA · com conluio · média de 10 sementes](graficos/acuracia_ema_com_conluio.png)

[PDF vetorial](graficos/acuracia_ema_com_conluio.pdf)

### Evolução dos scores — EMA · com conluio · média de 10 sementes

![Evolução dos scores — EMA · com conluio · média de 10 sementes](graficos/scores_ema_com_conluio.png)

[PDF vetorial](graficos/scores_ema_com_conluio.pdf)

### Influência dos nós maliciosos — EMA · com conluio · média de 10 sementes

![Influência dos nós maliciosos — EMA · com conluio · média de 10 sementes](graficos/influencia_ema_com_conluio.png)

[PDF vetorial](graficos/influencia_ema_com_conluio.pdf)

### Mudança de score causada por cada teste — EMA · com conluio · média de 10 sementes

![Mudança de score causada por cada teste — EMA · com conluio · média de 10 sementes](graficos/impacto_ema_com_conluio.png)

[PDF vetorial](graficos/impacto_ema_com_conluio.pdf)

### Ganho de acurácia após as validações — EMA · com conluio · média de 10 sementes

![Ganho de acurácia após as validações — EMA · com conluio · média de 10 sementes](graficos/janelas_ema_com_conluio.png)

[PDF vetorial](graficos/janelas_ema_com_conluio.pdf)

### Scores individuais — EMA · com conluio · semente 0

![Scores individuais — EMA · com conluio · semente 0](graficos/nos_ema_com_conluio.png)

[PDF vetorial](graficos/nos_ema_com_conluio.pdf)

### Detalhe dos cenários críticos — EMA · com conluio · média de 10 sementes

![Detalhe dos cenários críticos — EMA · com conluio · média de 10 sementes](graficos/detalhe_ema_com_conluio.png)

[PDF vetorial](graficos/detalhe_ema_com_conluio.pdf)

### Acurácia do consenso — EMA assimétrica · com conluio · média de 10 sementes

![Acurácia do consenso — EMA assimétrica · com conluio · média de 10 sementes](graficos/acuracia_ema_asymmetric_com_conluio.png)

[PDF vetorial](graficos/acuracia_ema_asymmetric_com_conluio.pdf)

### Evolução dos scores — EMA assimétrica · com conluio · média de 10 sementes

![Evolução dos scores — EMA assimétrica · com conluio · média de 10 sementes](graficos/scores_ema_asymmetric_com_conluio.png)

[PDF vetorial](graficos/scores_ema_asymmetric_com_conluio.pdf)

### Influência dos nós maliciosos — EMA assimétrica · com conluio · média de 10 sementes

![Influência dos nós maliciosos — EMA assimétrica · com conluio · média de 10 sementes](graficos/influencia_ema_asymmetric_com_conluio.png)

[PDF vetorial](graficos/influencia_ema_asymmetric_com_conluio.pdf)

### Mudança de score causada por cada teste — EMA assimétrica · com conluio · média de 10 sementes

![Mudança de score causada por cada teste — EMA assimétrica · com conluio · média de 10 sementes](graficos/impacto_ema_asymmetric_com_conluio.png)

[PDF vetorial](graficos/impacto_ema_asymmetric_com_conluio.pdf)

### Ganho de acurácia após as validações — EMA assimétrica · com conluio · média de 10 sementes

![Ganho de acurácia após as validações — EMA assimétrica · com conluio · média de 10 sementes](graficos/janelas_ema_asymmetric_com_conluio.png)

[PDF vetorial](graficos/janelas_ema_asymmetric_com_conluio.pdf)

### Scores individuais — EMA assimétrica · com conluio · semente 0

![Scores individuais — EMA assimétrica · com conluio · semente 0](graficos/nos_ema_asymmetric_com_conluio.png)

[PDF vetorial](graficos/nos_ema_asymmetric_com_conluio.pdf)

### Detalhe dos cenários críticos — EMA assimétrica · com conluio · média de 10 sementes

![Detalhe dos cenários críticos — EMA assimétrica · com conluio · média de 10 sementes](graficos/detalhe_ema_asymmetric_com_conluio.png)

[PDF vetorial](graficos/detalhe_ema_asymmetric_com_conluio.pdf)

### Acurácia do consenso — Beta · com conluio · média de 10 sementes

![Acurácia do consenso — Beta · com conluio · média de 10 sementes](graficos/acuracia_beta_com_conluio.png)

[PDF vetorial](graficos/acuracia_beta_com_conluio.pdf)

### Evolução dos scores — Beta · com conluio · média de 10 sementes

![Evolução dos scores — Beta · com conluio · média de 10 sementes](graficos/scores_beta_com_conluio.png)

[PDF vetorial](graficos/scores_beta_com_conluio.pdf)

### Influência dos nós maliciosos — Beta · com conluio · média de 10 sementes

![Influência dos nós maliciosos — Beta · com conluio · média de 10 sementes](graficos/influencia_beta_com_conluio.png)

[PDF vetorial](graficos/influencia_beta_com_conluio.pdf)

### Mudança de score causada por cada teste — Beta · com conluio · média de 10 sementes

![Mudança de score causada por cada teste — Beta · com conluio · média de 10 sementes](graficos/impacto_beta_com_conluio.png)

[PDF vetorial](graficos/impacto_beta_com_conluio.pdf)

### Ganho de acurácia após as validações — Beta · com conluio · média de 10 sementes

![Ganho de acurácia após as validações — Beta · com conluio · média de 10 sementes](graficos/janelas_beta_com_conluio.png)

[PDF vetorial](graficos/janelas_beta_com_conluio.pdf)

### Scores individuais — Beta · com conluio · semente 0

![Scores individuais — Beta · com conluio · semente 0](graficos/nos_beta_com_conluio.png)

[PDF vetorial](graficos/nos_beta_com_conluio.pdf)

### Detalhe dos cenários críticos — Beta · com conluio · média de 10 sementes

![Detalhe dos cenários críticos — Beta · com conluio · média de 10 sementes](graficos/detalhe_beta_com_conluio.png)

[PDF vetorial](graficos/detalhe_beta_com_conluio.pdf)

## Dados, rastreabilidade e limites

- [Resumo comparativo](resumo_comparativo.csv): resultados por cenário e erro-padrão do ganho pareado.
- [Evolução por rodada](evolucao_por_rodada.csv): consenso, scores por perfil e fração de peso malicioso para cada semente.
- [Score final de cada nó](scores_finais_por_no.csv). Histórico completo por nó: `reputation_history.csv` em cada execução bruta.
- [Impacto por teste e nó](impacto_por_teste_e_no.csv): antes/depois agregado das duas perguntas.
- [Impacto médio por teste](impacto_medio_por_teste.csv).
- [Efeito na janela seguinte](impacto_na_janela_seguinte.csv): comparação de 1–10, 11–20, 21–30, 31–40 e 41–50.
- [Verificações](verificacao.json): fontes e conferências estruturais e pareadas.

As perguntas/respostas/latências das tarefas normais foram verificadas como idênticas entre cada par. Os dados da Lara usam outra atualização operacional, portanto não são o controle causal deste experimento. A inferência é restrita ao modelo simulado, às dez sementes e à amostra local; não demonstra desempenho real de uma LLM.

A primeira tentativa com validação foi interrompida por bloqueio transitório de arquivo no Windows. O parcial foi preservado e excluído da análise; a repetição completa usou `com_validacao_v2`, após retry limitado na persistência. Nenhuma configuração científica foi alterada.

## Reprodução

```powershell
python -X utf8 -m sistema.scripts.run_matrix --nodes 50 --malicious 0 .2 .4 .6 .8 --seeds 10 --rounds 50 --validation-questions 2 --output NOVA_PASTA_COM
python -X utf8 -m sistema.scripts.run_matrix --nodes 50 --malicious 0 .2 .4 .6 .8 --seeds 10 --rounds 50 --validation-questions 2 --no-validation --output NOVA_PASTA_SEM
python -X utf8 -m sistema.scripts.report_rede50 --on NOVA_PASTA_COM --off NOVA_PASTA_SEM --output NOVA_PASTA_RELATORIO
```


## Verificação do código

Os dois testes novos de retry da persistência passaram. A suíte executou 24 testes: 21 passaram e três testes HTTP não puderam executar por falta de `httpx`/`pydantic` no ambiente. As 540 simulações não dependem desses módulos. As verificações dos dados pareados e dos checkpoints passaram; `git diff --check` sem erros.

## Revisão visual

39 figuras com cores, símbolos e tipos de linha distintos; versões PNG a 240 dpi e PDF vetorial. Calendário lido dos eventos, score antes/depois no mesmo instante, legendas externas e métricas separadas. Mapas individuais identificam honestos/maliciosos e mostram apenas a semente 0. Os quatro testes de desenho temporal passaram; os seis CSVs numéricos foram comparados por SHA-256 e são idênticos à exportação anterior. Nenhuma simulação foi refeita.
