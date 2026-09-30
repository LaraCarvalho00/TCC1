# Implementação da validação por dataset

Integração baseada em `origin/main` 4d27b76, com os módulos locais de validação
da branch `reputacao-sem-ground-truth`. O checkout original e seu trabalho sem
commit foram preservados. Plano: `PLANO_VALIDACAO.md`.

## Comportamento implementado

- Reputação operacional sem gabarito; confiança mínima e manutenção dos pesos em empate.
- Validação individual após as rodadas 10, 20, 30, 40 e 50, configurável por `test_every`.
- Perguntas reservadas do dataset para todos os nós, sem resposta no pedido HTTP.
- Avaliador com resposta esperada; EMA, EMA assimétrica e Beta compartilham o estado
  entre tarefas e validações. Os pesos atualizados afetam a tarefa seguinte.
- Perguntas normais e de validação disjuntas, seleção reproduzível por semente,
  hash do dataset e IDs registrados no manifesto.
- CSVs incrementais, histórico final após validação, erros e cobertura separados.
- Exportação usando os estilos da main e coordenadas lidas dos CSVs. Conclusões
  textuais do experimento antigo não são reutilizadas para os dados novos.

## Verificação executada

- 22 testes aprovados: regras sem gabarito, empate, calendário padrão/customizado,
  reprodutibilidade, estado compartilhado, persistência, repetição sem dupla
  contagem, transporte HTTP simulado, payload, falhas e exportação.
- Compilação sintática dos módulos Python e `git diff --check` sem erros.
- 42 simulações: 20 nós × 4 frações (0/25/50/65%) × 2 sementes × 3 mecanismos,
  com e sem conluio (sem duplicar 0%), 50 rodadas e 2 perguntas por validação.
- 210 validações concluídas e 8.400 consultas individuais de validação.
- 21 cenários agregados e cinco figuras em pgfplots gerados. Coordenadas e
  calendário verificados por testes; compilação e layout do PDF não verificados.

Comandos (na raiz do checkout da integração):

```powershell
python -m unittest discover -s sistema/tests -v
python -m sistema.scripts.run_matrix --nodes 20 --seeds 2 --rounds 50 --output sistema/results/integracao_validacao_smoke
python -m sistema.scripts.export_graficos sistema/results/integracao_validacao_smoke sistema/resultados/integracao_validacao_smoke
```

Os resultados foram gerados durante a implementação, antes do commit final.
Para uma nova execução, escolher pastas de saída novas. Os dados brutos ficam
em `sistema/results/integracao_validacao_smoke` (ignorados pelo Git). Os CSVs
agregados e fontes dos gráficos estão em `sistema/resultados/integracao_validacao_smoke`.

## Interpretação e limites

Esta é uma verificação com amostra offline e respostas simuladas, não uma
execução real do SmolLM3 nem uma repetição da matriz completa do TCC. O caminho
HTTP foi verificado com transporte controlado, sem containers ou download do modelo.

Em 20 nós e 65% de maliciosos em conluio, os três mecanismos tiveram acurácia
do consenso zero nos cinco pontos medidos, nas duas sementes. A validação
individual acontece e altera pesos, mas duas perguntas a cada dez tarefas
não garantem superar o reforço do consenso malicioso. Os números anteriores
da main usavam gabarito em todas as atualizações e não são comparáveis diretamente.

O dataset não é apresentado como evidência de treinamento da LLM. Seu gabarito
fica no avaliador; dizer que a validação inteira é “sem ground truth” seria
incorreto. O que não usa gabarito é a atualização operacional e o payload dos nós.

Timeout/erro/resposta inválida não altera reputação na validação e não entra no
denominador de acurácia individual; cobertura e contagens expõem as ausências.
Retomada após interrupção não é implementada: use outra pasta e preserve o parcial.
