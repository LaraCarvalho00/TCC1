# Etapa 4 — varredura de α e de rodadas de calibração

Commit: `44190e7288cedc7d0d05313c3da555412763bc37`.

Comando:

```
cd "/Users/gabrielferraz/Desktop/Tcc Lara" && "/Users/gabrielferraz/Desktop/Tcc Lara/.venv/bin/python" entrega_a4/run_a4.py etapa4
```

Acurácia de teste desta resposta: `test_protocol_weighted`, a do protocolo (`consensus_accuracy_weighted_on_tests`). 100% significa que **cada** semente, em **cada** fração, deu 1. Não é só a média.

Dinâmico: com gabarito, conluio 999, líder forja, `defense=all` (as outras defesas permanecem; só k, α do gabarito e α do consenso mudam). α do tracker permanece 0,3. Frações da lista de oito. Sementes 0 a 4.

Fixo: com gabarito, `defense=none`, sem calibração, um único α nas rodadas normais e nas de teste (porque `split_alpha` está desligado e os dois sinais usam `args.alpha`). Com e sem conluio.

| Fração | Nós maliciosos (`round(fração × 50)`, `sistema/simulate.py:58`) |
| --- | --- |
| 0% | 0 |
| 5% | 2 |
| 20% | 10 |
| 25% | 12 |
| 35% | 18 |
| 50% | 25 |
| 65% | 32 |
| 80% | 40 |

## Resposta

Menor k com acurácia de teste 1 em todas as frações e sementes:

- α consenso 0,05, α gabarito 0,50: menor k = 0
- α consenso 0,05, α gabarito 0,80: menor k = 0
- α consenso 0,05, α gabarito 0,95: menor k = 0
- α consenso 0,30, α gabarito 0,50: menor k = 0
- α consenso 0,30, α gabarito 0,80: menor k = 0
- α consenso 0,30, α gabarito 0,95: menor k = 0

α único do fixo com acurácia de teste 1 em todas as frações, com e sem conluio ao mesmo tempo: nenhum.

k = 0 não é livro único. Em 80%, com α de consenso 0,05, α de gabarito 0,80 e k = 0, as cinco sementes deram acurácia de teste 1, 1 rodada com líder malicioso, 1 forja aceita, 1 divisão e 2 cadeias. A acurácia 1 é a da cópia de referência. Com k = 0 o preset `all` continua com as outras defesas; só a calibração é que fica em zero.

## Menor k por par de α

| α consenso | α gabarito | menor k | pior acurácia de teste nesse k (mínimo entre frações e sementes) |
| --- | --- | --- | --- |
| 0,05 | 0,50 | 0 | 1,0000 |
| 0,05 | 0,80 | 0 | 1,0000 |
| 0,05 | 0,95 | 0 | 1,0000 |
| 0,30 | 0,50 | 0 | 1,0000 |
| 0,30 | 0,80 | 0 | 1,0000 |
| 0,30 | 0,95 | 0 | 1,0000 |

## α único do fixo

| α único | com conluio, pior acurácia | sem conluio, pior acurácia | 1 em todas as frações e sementes, com e sem conluio |
| --- | --- | --- | --- |
| 0,05 | 0,0000 | 1,0000 | não |
| 0,10 | 0,0000 | 1,0000 | não |
| 0,20 | 0,0000 | 1,0000 | não |
| 0,30 | 0,0000 | 0,8000 | não |
| 0,40 | 0,0000 | 0,8000 | não |
| 0,50 | 0,0000 | 0,8000 | não |
| 0,60 | 0,0000 | 0,8000 | não |
| 0,70 | 0,0000 | 0,8000 | não |
| 0,80 | 0,0000 | 0,8000 | não |
| 0,90 | 0,8000 | 0,8000 | não |

Figuras: `figuras/04_varredura_dinamico.png` (k no par α consenso 0,05 e α gabarito 0,80) e `figuras/04_varredura_fixo.png`.

CSV: `04_varredura_execucoes.csv`, `04_varredura_resumo.csv`.
