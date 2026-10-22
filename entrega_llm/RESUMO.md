# Resumo da entrega LLM

Branch `a4-calibracao-llm`, criada a partir de `a4-dados` (`e5e406b`). Autor dos commits deste repositório: Lara Andrade Carvalho (laraandrade312@gmail.com).

O hash do commit dos resultados fica registrado abaixo, no commit seguinte a este arquivo.

## Etapa 1 — patch e testes

`git apply --check` e `git apply calibracao_sem_lider_e_banco_llm.patch` na raiz. 49 testes, OK, em 1,3 s. Saída em `01_testes.txt`.

Commit do código, sem o arquivo `.patch`: `3e2e413`, mensagem «Calibração sem líder, banco de respostas do SmolLM3-3B e scripts da A4».

## Etapa 2 — teste curto

Comando: `.venv/bin/python -m sistema.scripts.gerar_banco_llm --questoes 2 --amostras 3 --saida entrega_llm/banco_teste.json`

62 s. Duas questões, três amostras cada, respostas numéricas. Dispositivo `mps`. Log em `02_teste_banco.txt`.

## Etapa 3 — banco completo

Comando: `.venv/bin/python -m sistema.scripts.gerar_banco_llm --questoes 50 --amostras 20 --saida sistema/resultados/banco_llm/banco_smol.json`

Tempo de parede: 11468,7 s (3 h 11 min), incluindo a carga do modelo. Dispositivo `mps`. Acurácia das 1000 amostras: 740/1000 = 74,0%. Acurácia gulosa: 39/50 = 78,0%. Tabela em `03_banco_resumo.md`. Log em `03_banco_log.txt`.

## Etapa 4 — experimentos

Comando: `.venv/bin/python -m sistema.scripts.rodar_com_banco --banco sistema/resultados/banco_llm/banco_smol.json --saida sistema/resultados/banco_llm/experimentos`

480 execuções em 106,9 s. `resumo.csv`, `execucoes.csv` e as três figuras estão em `04_experimentos/`. Tabelas em `04_experimentos.md`.

## Etapa 5 — varredura

Comando: `.venv/bin/python -m sistema.scripts.varredura_calibracao entrega_llm/05_varredura`

1440 execuções em 2254,7 s. `resumo.csv` copiado para `05_varredura_resumo.csv`.

## O que falhou

Nada, depois que o patch estava na raiz. O detalhe da tentativa anterior está em `ERROS.md`.

## Arquivos

- `01_testes.txt`
- `02_teste_banco.txt`, `banco_teste.json`
- `03_banco_log.txt`, `03_banco_resumo.md`
- `04_experimentos.md`, `04_experimentos_log.txt`, `04_experimentos/`
- `05_varredura_log.txt`, `05_varredura_resumo.csv`, `05_varredura/resumo.csv`, `05_varredura/execucoes.csv`
- `ERROS.md`, `RESUMO.md`

O banco completo está em `sistema/resultados/banco_llm/banco_smol.json`. As pastas `brutos/` não entram no commit.
