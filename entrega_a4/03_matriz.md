# Etapa 3 — matriz reputação × conluio

Commit: `44190e7288cedc7d0d05313c3da555412763bc37`.

Comando:

```
cd "/Users/gabrielferraz/Desktop/Tcc Lara" && "/Users/gabrielferraz/Desktop/Tcc Lara/.venv/bin/python" entrega_a4/run_a4.py etapa3
```

Cada execução calcula, na mesma rodada e sobre as mesmas respostas, o consenso ponderado e a maioria simples. Não são duas simulações.

- Sem reputação = maioria simples (`sistema/core/consensus.py:111`).
- Com reputação = consenso ponderado (`sistema/core/consensus.py:68`).
- Sem conluio: `collusion_value=None` (cada malicioso erra com um valor diferente, `sistema/core/behavior.py:109-113`) e `leader_attack=none`.
- Com conluio: todos os maliciosos devolvem 999; no dinâmico, `leader_attack=forge` quando a fração é positiva.
- Fixo com gabarito, dinâmico com gabarito e dinâmico sem gabarito, como na etapa 2. Mecanismos `ema`, `ema_asymmetric` e `beta`. α do tracker = 0,3. No dinâmico com `defense=all`, o α efetivo do consenso é 0,05 e o do gabarito é 0,8 (`sistema/core/defenses.py:30-31`).
- Frações: 0, 5, 20, 25, 35, 50, 65 e 80%. 50 nós, 50 rodadas, sementes 0 a 4.
- Figura: só EMA. Eixo y = acurácia nas rodadas de teste, em %, dos dois agregadores sobre a **cópia de referência** (membros de `reference_group()` depois da rodada). A rede inteira está nas colunas `*_rede`.
- Desvio-padrão amostral (n−1).

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

Figuras:

- `figuras/03_fixo_com_gabarito_ema.png`
- `figuras/03_dinamico_com_gabarito_ema.png`
- `figuras/03_dinamico_sem_gabarito_ema.png`

No fixo a cópia de referência é a rede inteira: não há cadeia. No dinâmico, `rounds_referencia_parcial` conta rodadas em que a cópia de referência tinha menos nós que a rede.

## Acurácia de teste, EMA, cópia de referência

| Orquestrador | Fração | Nós maliciosos | Com reputação, com conluio | Com reputação, sem conluio | Sem reputação, com conluio | Sem reputação, sem conluio | Protocolo, com conluio | Maioria da rede, com conluio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixo_com_gabarito | 0% | 0 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| fixo_com_gabarito | 5% | 2 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| fixo_com_gabarito | 20% | 10 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| fixo_com_gabarito | 25% | 12 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| fixo_com_gabarito | 35% | 18 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| fixo_com_gabarito | 50% | 25 | 0,0000 ± 0,0000 | 1,0000 ± 0,0000 | 0,1200 ± 0,1095 | 1,0000 ± 0,0000 | 0,0000 ± 0,0000 | 0,1200 ± 0,1095 |
| fixo_com_gabarito | 65% | 32 | 0,0000 ± 0,0000 | 1,0000 ± 0,0000 | 0,0000 ± 0,0000 | 1,0000 ± 0,0000 | 0,0000 ± 0,0000 | 0,0000 ± 0,0000 |
| fixo_com_gabarito | 80% | 40 | 0,0000 ± 0,0000 | 0,9200 ± 0,1095 | 0,0000 ± 0,0000 | 0,7600 ± 0,2608 | 0,0000 ± 0,0000 | 0,0000 ± 0,0000 |
| dinamico_com_gabarito | 0% | 0 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| dinamico_com_gabarito | 5% | 2 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| dinamico_com_gabarito | 20% | 10 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| dinamico_com_gabarito | 25% | 12 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| dinamico_com_gabarito | 35% | 18 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| dinamico_com_gabarito | 50% | 25 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 0,1200 ± 0,1095 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 0,1200 ± 0,1095 |
| dinamico_com_gabarito | 65% | 32 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 0,0000 ± 0,0000 |
| dinamico_com_gabarito | 80% | 40 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 0,7600 ± 0,2608 | 1,0000 ± 0,0000 | 0,0000 ± 0,0000 |
| dinamico_sem_gabarito | 0% | 0 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| dinamico_sem_gabarito | 5% | 2 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| dinamico_sem_gabarito | 20% | 10 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| dinamico_sem_gabarito | 25% | 12 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| dinamico_sem_gabarito | 35% | 18 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 |
| dinamico_sem_gabarito | 50% | 25 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 0,1200 ± 0,1095 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 0,1200 ± 0,1095 |
| dinamico_sem_gabarito | 65% | 32 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 0,0000 ± 0,0000 |
| dinamico_sem_gabarito | 80% | 40 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 1,0000 ± 0,0000 | 0,7600 ± 0,2608 | 1,0000 ± 0,0000 | 0,0000 ± 0,0000 |

## Protocolo, líder, forja, anulação, divisão e cadeias

No fixo essas colunas não existem no código (orquestrador sem eleição). Ficam vazias no CSV.

| Orquestrador | Mecanismo | Conluio | Fração | Nós maliciosos | Líder malicioso | Forjas aceitas | Anulações | Divisões | Cadeias no fim | Rodadas com referência parcial |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixo_com_gabarito | ema | 0 | 0% | 0 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 0 | 5% | 2 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 0 | 20% | 10 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 0 | 25% | 12 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 0 | 35% | 18 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 0 | 50% | 25 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 0 | 65% | 32 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 0 | 80% | 40 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 1 | 0% | 0 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 1 | 5% | 2 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 1 | 20% | 10 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 1 | 25% | 12 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 1 | 35% | 18 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 1 | 50% | 25 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 1 | 65% | 32 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema | 1 | 80% | 40 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 0 | 0% | 0 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 0 | 5% | 2 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 0 | 20% | 10 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 0 | 25% | 12 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 0 | 35% | 18 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 0 | 50% | 25 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 0 | 65% | 32 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 0 | 80% | 40 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 1 | 0% | 0 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 1 | 5% | 2 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 1 | 20% | 10 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 1 | 25% | 12 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 1 | 35% | 18 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 1 | 50% | 25 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 1 | 65% | 32 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | ema_asymmetric | 1 | 80% | 40 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 0 | 0% | 0 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 0 | 5% | 2 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 0 | 20% | 10 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 0 | 25% | 12 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 0 | 35% | 18 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 0 | 50% | 25 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 0 | 65% | 32 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 0 | 80% | 40 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 1 | 0% | 0 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 1 | 5% | 2 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 1 | 20% | 10 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 1 | 25% | 12 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 1 | 35% | 18 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 1 | 50% | 25 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 1 | 65% | 32 | — | — | — | — | — | 0,00 ± 0,00 |
| fixo_com_gabarito | beta | 1 | 80% | 40 | — | — | — | — | — | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 0 | 0% | 0 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 0 | 5% | 2 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 0 | 20% | 10 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 0 | 25% | 12 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 0 | 35% | 18 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 0 | 50% | 25 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 0 | 65% | 32 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 0 | 80% | 40 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 1 | 0% | 0 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 1 | 5% | 2 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 1 | 20% | 10 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 1 | 25% | 12 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 1 | 35% | 18 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 1 | 50% | 25 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema | 1 | 65% | 32 | 1,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 2,00 ± 0,00 | 50,00 ± 0,00 |
| dinamico_com_gabarito | ema | 1 | 80% | 40 | 1,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 2,00 ± 0,00 | 50,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 0 | 0% | 0 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 0 | 5% | 2 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 0 | 20% | 10 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 0 | 25% | 12 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 0 | 35% | 18 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 0 | 50% | 25 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 0 | 65% | 32 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 0 | 80% | 40 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 1 | 0% | 0 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 1 | 5% | 2 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 1 | 20% | 10 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 1 | 25% | 12 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 1 | 35% | 18 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 1 | 50% | 25 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 1 | 65% | 32 | 1,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 2,00 ± 0,00 | 50,00 ± 0,00 |
| dinamico_com_gabarito | ema_asymmetric | 1 | 80% | 40 | 1,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 2,00 ± 0,00 | 50,00 ± 0,00 |
| dinamico_com_gabarito | beta | 0 | 0% | 0 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 0 | 5% | 2 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 0 | 20% | 10 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 0 | 25% | 12 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 0 | 35% | 18 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 0 | 50% | 25 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 0 | 65% | 32 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 0 | 80% | 40 | 1,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 1 | 0% | 0 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 1 | 5% | 2 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 1 | 20% | 10 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 1 | 25% | 12 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 1 | 35% | 18 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 1 | 50% | 25 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_com_gabarito | beta | 1 | 65% | 32 | 1,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 2,00 ± 0,00 | 50,00 ± 0,00 |
| dinamico_com_gabarito | beta | 1 | 80% | 40 | 1,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 2,00 ± 0,00 | 50,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 0 | 0% | 0 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 0 | 5% | 2 | 2,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 0 | 20% | 10 | 10,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 0 | 25% | 12 | 12,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 0 | 35% | 18 | 18,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 0 | 50% | 25 | 25,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 0 | 65% | 32 | 32,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 0 | 80% | 40 | 40,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 1 | 0% | 0 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 1 | 5% | 2 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 1 | 20% | 10 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 1 | 25% | 12 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 1 | 35% | 18 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 1 | 50% | 25 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 1 | 65% | 32 | 1,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 2,00 ± 0,00 | 50,00 ± 0,00 |
| dinamico_sem_gabarito | ema | 1 | 80% | 40 | 1,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 2,00 ± 0,00 | 50,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 0 | 0% | 0 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 0 | 5% | 2 | 2,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 0 | 20% | 10 | 10,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 0 | 25% | 12 | 12,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 0 | 35% | 18 | 18,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 0 | 50% | 25 | 25,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 0 | 65% | 32 | 32,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 0 | 80% | 40 | 40,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 1 | 0% | 0 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 1 | 5% | 2 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 1 | 20% | 10 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 1 | 25% | 12 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 1 | 35% | 18 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 1 | 50% | 25 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 1 | 65% | 32 | 1,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 2,00 ± 0,00 | 50,00 ± 0,00 |
| dinamico_sem_gabarito | ema_asymmetric | 1 | 80% | 40 | 1,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 2,00 ± 0,00 | 50,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 0 | 0% | 0 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 0 | 5% | 2 | 2,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 0 | 20% | 10 | 10,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 0 | 25% | 12 | 12,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 0 | 35% | 18 | 18,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 0 | 50% | 25 | 25,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 0 | 65% | 32 | 32,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 0 | 80% | 40 | 40,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 1 | 0% | 0 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 1 | 5% | 2 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 1 | 20% | 10 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 1 | 25% | 12 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 1 | 35% | 18 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 1 | 50% | 25 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 1 | 65% | 32 | 1,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 2,00 ± 0,00 | 50,00 ± 0,00 |
| dinamico_sem_gabarito | beta | 1 | 80% | 40 | 1,00 ± 0,00 | 1,00 ± 0,00 | 0,00 ± 0,00 | 1,00 ± 0,00 | 2,00 ± 0,00 | 50,00 ± 0,00 |

O CSV completo, com os três mecanismos e as duas versões da maioria (referência e rede inteira), é `03_matriz_execucoes.csv` e `03_matriz_resumo.csv`.
