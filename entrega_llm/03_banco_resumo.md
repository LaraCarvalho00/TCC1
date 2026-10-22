# Banco SmolLM3-3B

Comando: `.venv/bin/python -m sistema.scripts.gerar_banco_llm --questoes 50 --amostras 20 --saida sistema/resultados/banco_llm/banco_smol.json`

Tempo de parede, do início do comando até o fim, incluindo a carga do modelo: 11468,7 s (3 h 11 min). O relógio do script, somado depois da carga, é 11457.7 s (191.0 min).
Dispositivo: `mps`. Máquina registrada no banco: `macOS-26.6.2-arm64-arm-64bit`.
Modelo: `HuggingFaceTB/SmolLM3-3B`. Temperatura 0.7, top-p 0.95, semente 0, máximo de tokens 256.
Acurácia das amostras: 740/1000 = 74.0%.
Acurácia da resposta gulosa: 39/50 = 78.0%.

Desvio-padrão não se aplica: há uma geração do banco, não repetições.

| id | gabarito | gulosa | acertos em 20 | distintas | mais frequente (contagem) | a mais frequente é o gabarito |
| --- | --- | --- | --- | --- | --- | --- |
| gsm8k-test-0 | 18 | 18 | 20 | 1 | 18 (20) | sim |
| gsm8k-test-1 | 3 | 3 | 20 | 1 | 3 (20) | sim |
| gsm8k-test-2 | 70000 | 70000 | 4 | 12 | 245000, 70000 (4) | empate |
| gsm8k-test-3 | 540 | 540 | 19 | 2 | 540 (19) | sim |
| gsm8k-test-4 | 20 | -620 | 6 | 10 | 20 (6) | sim |
| gsm8k-test-5 | 64 | 64 | 8 | 2 | 16 (12) | não |
| gsm8k-test-6 | 260 | 260 | 20 | 1 | 260 (20) | sim |
| gsm8k-test-7 | 160 | 80 | 1 | 11 | 120 (7) | não |
| gsm8k-test-8 | 45 | 120 | 0 | 12 | 315 (5) | não |
| gsm8k-test-9 | 460 | 460 | 20 | 1 | 460 (20) | sim |
| gsm8k-test-10 | 366 | 366 | 20 | 1 | 366 (20) | sim |
| gsm8k-test-11 | 694 | 694 | 15 | 2 | 694 (15) | sim |
| gsm8k-test-12 | 13 | 12 | 0 | 4 | 12 (17) | não |
| gsm8k-test-13 | 18 | 18 | 4 | 10 | 2 (5) | não |
| gsm8k-test-14 | 60 | 60 | 19 | 2 | 60 (19) | sim |
| gsm8k-test-15 | 125 | 125 | 12 | 6 | 125 (12) | sim |
| gsm8k-test-16 | 230 | 230 | 13 | 4 | 230 (13) | sim |
| gsm8k-test-17 | 57500 | 57500 | 18 | 3 | 57500 (18) | sim |
| gsm8k-test-18 | 7 | 7 | 17 | 2 | 7 (17) | sim |
| gsm8k-test-19 | 6 | 6 | 15 | 6 | 6 (15) | sim |
| gsm8k-test-20 | 15 | 15 | 10 | 7 | 15 (10) | sim |
| gsm8k-test-21 | 14 | 23 | 5 | 4 | 2 (9) | não |
| gsm8k-test-22 | 7 | 7 | 17 | 2 | 7 (17) | sim |
| gsm8k-test-23 | 8 | 0 | 15 | 2 | 8 (15) | sim |
| gsm8k-test-24 | 26 | 26 | 20 | 1 | 26 (20) | sim |
| gsm8k-test-25 | 2 | 2 | 20 | 1 | 2 (20) | sim |
| gsm8k-test-26 | 243 | 243 | 11 | 2 | 243 (11) | sim |
| gsm8k-test-27 | 16 | 16 | 20 | 1 | 16 (20) | sim |
| gsm8k-test-28 | 25 | 25 | 14 | 5 | 25 (14) | sim |
| gsm8k-test-29 | 104 | 94 | 20 | 1 | 104 (20) | sim |
| gsm8k-test-30 | 109 | 109 | 20 | 1 | 109 (20) | sim |
| gsm8k-test-31 | 80 | 80 | 20 | 1 | 80 (20) | sim |
| gsm8k-test-32 | 35 | 35 | 20 | 1 | 35 (20) | sim |
| gsm8k-test-33 | 70 | 70 | 20 | 1 | 70 (20) | sim |
| gsm8k-test-34 | 23 | 23 | 20 | 1 | 23 (20) | sim |
| gsm8k-test-35 | 9 | 9 | 19 | 2 | 9 (19) | sim |
| gsm8k-test-36 | 75 | 75 | 19 | 2 | 75 (19) | sim |
| gsm8k-test-37 | 2 | 13 | 0 | 6 | 0 (12) | não |
| gsm8k-test-38 | 10 | 10 | 8 | 7 | 10 (8) | sim |
| gsm8k-test-39 | 18 | 4 | 9 | 7 | 18 (9) | sim |
| gsm8k-test-40 | 8 | 8 | 20 | 1 | 8 (20) | sim |
| gsm8k-test-41 | 200 | 200 | 19 | 2 | 200 (19) | sim |
| gsm8k-test-42 | 26 | 26 | 20 | 1 | 26 (20) | sim |
| gsm8k-test-43 | 48 | 240 | 15 | 5 | 48 (15) | sim |
| gsm8k-test-44 | 20 | 20 | 20 | 1 | 20 (20) | sim |
| gsm8k-test-45 | 104 | 104 | 20 | 1 | 104 (20) | sim |
| gsm8k-test-46 | 163 | 277 | 10 | 8 | 163 (10) | sim |
| gsm8k-test-47 | 800 | 800 | 19 | 2 | 800 (19) | sim |
| gsm8k-test-48 | 8 | 8 | 19 | 2 | 8 (19) | sim |
| gsm8k-test-49 | 30 | 30 | 20 | 1 | 30 (20) | sim |
