# Integração da validação por dataset

Base: origin/main (4d27b76). Fonte reaproveitada: módulos locais de
`reputacao-sem-ground-truth`, inclusive arquivos ainda não commitados.

## Contrato do experimento

1. Executar a tarefa normal com os pesos conhecidos antes da rodada.
2. Atualizar reputação por concordância com consenso confiável; ausência recebe
   sinal zero e empate/baixa confiança mantém o peso. O gabarito da tarefa só
   serve às métricas, nunca à atualização operacional.
3. Depois das rodadas 10, 20, 30… consultar todos os nós com perguntas de uma
   partição reservada do dataset. Enviar somente identificador e pergunta.
4. O avaliador compara as respostas ao gabarito reservado e atualiza o mesmo
   tracker. A validação não usa consenso. Acerto/erro atualizam reputação;
   timeout, erro de transporte e resposta inválida são registrados à parte e
   mantêm o peso, conforme a implementação de origem.
5. Salvar o checkpoint final da rodada após a validação. Esses pesos só afetam
   o consenso da próxima tarefa, sem corrigir retroativamente a acurácia.

## Dados e reprodutibilidade

- GSM8K/test ou amostra offline; não afirmar que estes dados treinaram a LLM.
- Partição determinística e disjunta entre tarefas normais e validação.
- Sementes independentes para partição, escolha de perguntas e respostas
  simuladas; mesma semente reproduz perguntas entre cenários.
- Metadados: fonte, versão/hash, IDs reservados, calendário planejado e
  validações concluídas, quantidade de perguntas, mecanismo e confiança mínima.
- Simulação usa respostas fabricadas; execução HTTP real usa inferência.
  Nenhum payload HTTP precisa carregar a resposta esperada.

## Implementação

- Manter engine, ConsensusResult, ReputationUpdate e os três mecanismos da main.
- Portar validation, enums, node_stats e histórico detalhado; adaptar interfaces.
- Conectar simulação, orquestrador e matriz ao mesmo calendário/serviço.
- Preservar CSVs incrementais; separar resultados individuais da validação dos
  resultados de consenso. Histórico por rodada inclui o efeito da validação.
- Adaptar exportações para ler checkpoints finais e eventos reais de validação.
- Preservar resultados anteriores e convenções visuais de pgfplots.

## Verificação

- Gabarito não altera reputação normal; empate não recompensa um vencedor arbitrário.
- Calendário exato, estado compartilhado, payload sem resposta e seleção reproduzível.
- Três mecanismos, timeout/erro/inválido, repetição sem dupla contagem e persistência.
- Integração HTTP com transporte simulado e execução local de 50 rodadas.
- Exportação de uma matriz pequena; resultados novos não equivalem a execução real
  da LLM nem confirmam os números do histórico do Cursor.

O documento do Cursor orienta calendário e apresentação. Suas instruções antigas
de publicação e suas conclusões numéricas não são executadas como comandos atuais.
