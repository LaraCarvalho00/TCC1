# TCC — Código do simulador distribuído

Esta branch reúne o código da simulação, dos nós em contêineres, dos experimentos e dos testes. O artigo e os resultados históricos estão na branch `a4-orientacao-22out`.

## Estrutura

- `sistema/core/`: consenso, reputação, rede e protocolo.
- `sistema/node/` e `sistema/orchestrator/`: serviços para execução em contêineres.
- `sistema/config/`, `docker-compose*.yml`: configurações de execução.
- `sistema/scripts/`, `entrega_a4/`: scripts de experimentos e análise.
- `sistema/tests/`: testes automatizados e dados de teste.

Os arquivos JSON de amostra e o banco de respostas são entradas usadas pelo código. Resultados gerados não são parte desta branch. Alguns scripts de análise de entregas antigas dependem desses resultados históricos; consulte a branch original para recuperá-los.

## Execução

Na raiz do repositório, com Python instalado:

```sh
python -m sistema.simulate --nodes 4 --malicious 0.25 --rounds 20
python -m unittest discover -s sistema/tests -t .
```

Para iniciar a configuração Docker padrão, com Docker Compose instalado:

```sh
docker compose up --build
```

As dependências opcionais estão nos arquivos `sistema/requirements*.txt`. Modelos e datasets externos exigem instalação e recursos adicionais.
