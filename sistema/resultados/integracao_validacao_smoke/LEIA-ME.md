# Resultados da integração

Execuções: 42. Validações concluídas: [10, 20, 30, 40, 50].

Simulação por perfis, sem inferência real da LLM. O dataset não comprova proveniência de treinamento. O consenso é medido antes da validação e as curvas de reputação usam o checkpoint após a validação.

`validacao_por_execucao.csv` separa a acurácia individual e a cobertura (respostas avaliáveis/consultas). Timeout/erro não conta como resposta errada. Os CSVs em `analise/` descrevem o consenso nas tarefas normais.

Figuras incluídas: 5; somente as que possuem todos os cenários necessários. Compile `main.tex` a partir desta pasta. Cada figura lê diretamente os CSVs; o estilo compartilhado preserva cores, marcadores e transparência da main.
