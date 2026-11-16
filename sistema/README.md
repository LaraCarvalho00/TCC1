# Sistema

O código do simulador está em `core/`, as séries em `experimentos/`, a entrada de linha de comando em `interfaces/`, os serviços Docker em `node/` e `orchestrator/`, e os testes em `tests/`. Para comandos e estrutura, consulte o [README principal](../README.md).

## Dados e resultados fora do código

- `dados/banco_smol.json`: tarefas GSM8K e respostas pré-geradas **Smol** usadas pelas séries do artigo (sorteio com reposição, sem inferência por rodada).
- Saída padrão das séries do artigo: `resultados/artigo/` (manifestos, CSVs, gráficos).
- Grade local com inferência Qwen: em geral `sistema/results/` e pilôs em `resultados/llm/`; auditoria consolidada em `resultados/llm/impacto-qwen-20261116/` ([VALIDACAO_IMPACTO.md](../resultados/llm/impacto-qwen-20261116/VALIDACAO_IMPACTO.md), [RELATORIO_RESULTADOS.md](../resultados/llm/impacto-qwen-20261116/RELATORIO_RESULTADOS.md)).
- Inferência em nó: `node/inference.py`, `inference_gateway.py`, `inference_pool.py`; runner `scripts/runner_containers.py`. Alterações nesses módulos mudam o fingerprint usado para retomar caches — evite mudanças desnecessárias enquanto houver grade interrompida.

A seção **Extensão Qwen3-0.6B** no README principal descreve diferenças metodológicas Smol × Qwen, o pool de cinco modelos e o estado parcial da grade.
