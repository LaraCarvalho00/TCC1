# Etapa 6 — fatos do código para a metodologia

Cada item é o que o código faz. Linhas conferidas em `44190e7` mais a árvore de trabalho; os arquivos citados de `sistema/` não foram editados por esta entrega, exceto `sistema/simulate.py` e `sistema/node/inference.py` (nenhum dos dois muda as definições abaixo).

## Orquestrador fixo

Um único processo aplica consenso e reputação sobre as respostas de todos os nós. Não há líder, auditor nem cadeia. Na simulação local o laço está em `sistema/simulate.py:172-190`, que chama `process_round` (`sistema/core/engine.py:36`). No Docker, o mesmo `process_round` é chamado por `sistema/orchestrator/run.py:173`. A grade do artigo usa a simulação local (`sistema/scripts/run_a3_n50.py:22` e `sistema/scripts/run_a3_n50.py:80`).

## Orquestrador dinâmico

Cada grupo que compartilha uma cadeia elege um líder, que propõe um registro; os membros conferem e votam; o registro entra na cadeia se houver quórum (`sistema/core/network.py:116-136` e `sistema/core/network.py:139-229`). As mesmas funções puras servem o nó em container (`sistema/core/replica.py:47-76` e `sistema/orchestrator/run.py:241-248`).

## Líder

Não há eleição por voto. Quem tem a cadeia calcula `elect_leader` (`sistema/core/election.py:73-97`). Na simulação, quem chama é o grupo (`sistema/core/network.py:154`); no container, a réplica (`sistema/core/replica.py:47-51`). Elegível é quem, na janela de presença lida da cadeia, faltou no máximo `max_absences` vezes (`sistema/core/election.py:30-44`; janela 5 e no máximo 1 falta em `sistema/core/protocol.py:60-61`). Enquanto a maior reputação de eleição menos a menor for estritamente menor que 0,05, o líder sai do rodízio da lista ordenada de membros, pulando quem liderou a rodada anterior (`sistema/core/election.py:54-63` e `sistema/core/election.py:89-96`). A margem 0,05 é `bootstrap_margin` (`sistema/core/protocol.py:62`). O índice do rodízio é `state.rotation`, que aumenta em registro de rodada e em anulação (`sistema/core/protocol.py:447` e `sistema/core/protocol.py:452`). Fora da largada, lidera o maior score, excluindo o líder anterior; empate fica com o menor `node_id` (`sistema/core/election.py:66-70` e `sistema/core/election.py:97`).

## Auditor

É o maior score de eleição entre os elegíveis a pelo menos dois saltos do líder no grafo (`sistema/core/election.py:100-117`). Se ninguém está tão longe (na estrela todos são vizinhos), cai para o maior score do restante. O auditor não tem uma conferência própria: vota com `verify_record`, como qualquer nó honesto (`sistema/core/replica.py:70-71` e `sistema/core/protocol.py:276-299`). Essa função confere o elo `prev_hash`, o hash do registro, se a própria resposta foi omitida ou trocada, e se o consenso e o hash do estado batem com o recálculo local. Se a proposta é aceita e o auditor recusou sem motivo objetivo e sem censura, ele é punido por `false_reject` (`sistema/core/protocol.py:338-341`).

## Registro

Um `RoundRecord` imutável (`sistema/core/ledger.py:32-54`). Os tipos são `round`, `void`, `penalty` e `oracle` (`sistema/core/ledger.py:29`). O de rodada guarda índice, hash anterior, tarefa, líder, auditor, respostas, consenso, estado da reputação e o hash desse estado. O de anulação ou punição guarda a lista `(nó, motivo)`. O de gabarito guarda a resposta esperada e as respostas julgadas.

## Estado

Reputação de consenso, reputação de poder e a lista recente de presença (`sistema/core/protocol.py:90-103`). Sem `split_scores`, poder e consenso são o mesmo objeto (`sistema/core/protocol.py:100`). O estado que entra no registro é o snapshot (`sistema/core/protocol.py:126-130`). Quem aplica um registro de rodada restaura esse snapshot, em vez de recalcular (`sistema/core/protocol.py:439-447`).

## Livro e cadeia (hash)

`Ledger` é a lista de registros de uma cópia (`sistema/core/ledger.py:86-110`). Cada registro aponta para o hash do anterior. Cadeia vazia: a cabeça é `GENESIS_HASH`, 64 zeros (`sistema/core/ledger.py:28` e `sistema/core/ledger.py:95-96`). O hash é SHA-256 de um JSON canônico, chaves ordenadas, sem espaços (`sistema/core/ledger.py:80-83`). `append` recusa elo quebrado ou hash que não bate com o conteúdo (`sistema/core/ledger.py:101-106`).

## Quórum

Soma das reputações de poder de quem votou e de quem confirmou. Passa só se a massa confirmada for estritamente maior que a metade da massa total (`sistema/core/protocol.py:306-310`). O empate (metade exata) não confirma. Os pesos são os de poder, não os do consenso (`sistema/core/protocol.py:327-328`). Peso negativo entra como zero.

## Voto e peso do voto

O voto é um booleano mais um motivo (`sistema/core/protocol.py:252-256`). Nó honesto usa `verify_record`. Nó malicioso confirma o que um líder do conluio propõe; fora isso, vota como honesto, salvo o auditor no ataque `false_reject` (`sistema/core/behavior.py:64-77`). O peso do voto no consenso ponderado é a reputação de consenso de antes da rodada, cortada em zero (`sistema/core/consensus.py:87-91` e `sistema/core/engine.py:116`). Ausente não entra na soma (`sistema/core/consensus.py:89-90`). No empate de pontuação, ganha o menor valor numérico (`sistema/core/consensus.py:12-16` e `sistema/core/consensus.py:57-65`). Isso é desempate de resposta, não o empate de quórum.

## Reputação de eleição × peso do voto

São dois scores quando `split_scores` está ligado (`sistema/core/defenses.py:13-15` e `sistema/core/protocol.py:100`). O peso do voto é o score de consenso. A eleição e o quórum usam o score de poder (`sistema/core/election.py:60` e `sistema/core/protocol.py:328`). O score de eleição, em EMA, é a própria reputação de poder; em beta, é `acertos / (acertos + erros + caution)`, com `caution = 2` (`sistema/core/election.py:47-52` e `sistema/core/protocol.py:63`). Rodada aceita atualiza o consenso pelo sinal da rodada e restaura o poder como estava no snapshot, sem o sinal de consenso (`sistema/core/protocol.py:176-179`). Poder muda na punição e no gabarito (`sistema/core/protocol.py:430-434` e `sistema/core/protocol.py:456-462`). Sem `split_scores`, os dois nomes são o mesmo número.

## Rodada normal, rodada de teste, Rodada de Validação, calibração

Rodada de teste: `(índice + 1)` divisível por `test_every`. O padrão é 10, logo as rodadas 10, 20, 30, 40 e 50 (`sistema/core/schedule.py:11-18`). O flag não troca o sinal sozinho; a reputação continua sendo atualizada (`sistema/core/engine.py:73-75`).

«Rodada de Validação» não é uma função. O nome aparece no script da grade A3 para as rodadas de teste em que o gabarito entra (`sistema/scripts/run_a3_n50.py:1-9`).

Calibração: índices menores que `calibration_rounds`. O preset `all` usa 3, isto é, as rodadas 1, 2 e 3 (`sistema/core/defenses.py:23` e `sistema/core/protocol.py:150`). Há líder, proposta e voto nessas rodadas (`sistema/core/network.py:154`). O gabarito é um registro extra depois disso (`sistema/core/network.py:128-131`). Com sinal `consensus`, `oracle_round` é sempre falso: nem calibração nem teste aplicam gabarito (`sistema/core/protocol.py:146-147`).

Sinal `s` da EMA: 1 se a regra da rodada conta a resposta como certa, 0 se erra ou falta (`sistema/core/reputation.py:108` e `sistema/core/reputation.py:10-11`). Fórmula: `r ← (1 − α) r + α s` (`sistema/core/reputation.py:114`).

α no fixo híbrido com `defense=none` (o do artigo): um só α, o do tracker. No A3 é 0,3 (`sistema/scripts/run_a3_n50.py:35`). Nas rodadas de teste o sinal é o gabarito; nas outras, a concordância com o consenso ponderado (`sistema/simulate.py:172-179`). Como `split_alpha` está desligado, o α passado é `None` e vale o do tracker (`sistema/core/protocol.py:71-76` e `sistema/core/reputation.py:110`).

α no dinâmico com `defense=all`: 0,05 no sinal de consenso e 0,8 no gabarito (`sistema/core/defenses.py:30-32`). Punição de anulação: α = 0,5 (`sistema/core/protocol.py:59` e `sistema/core/protocol.py:430-432`). Todo nó começa em 0,5 (`sistema/core/reputation.py:59` e `sistema/core/protocol.py:57`).

## Rodada anulada

Quando a massa que confirma não passa de metade (`sistema/core/protocol.py:390-394`). Grava-se um registro `void`. Se a proposta tinha motivo objetivo (forja ou consenso falso) ou censura, o líder e quem confirmou uma proposta objetivamente inválida são punidos com `s = 0` e α = 0,5 (`sistema/core/protocol.py:334-345` e `sistema/core/protocol.py:448-452`). Falta de quórum sem esse motivo não lista punição (`penalties` fica vazio).

## Recusa

Quem recusa é o nó cujo voto é não. Se a proposta mesmo assim foi aceita, `refuse_forged` está ligado, e o motivo é censura da própria resposta ou forja/consenso falso confirmados pelo recálculo, esse nó sai com uma cópia da cadeia (`sistema/core/protocol.py:358-374` e `sistema/core/network.py:194-207`). A cópia recebe um `void` que pune o líder e quem confirmou (`sistema/core/protocol.py:385-389`). Recusa sem motivo verificável não tira ninguém da rede. O ataque `false_reject` do auditor, sem forja real, não gera saída (`sistema/core/protocol.py:363-364`).

## Divisão da cadeia e «seguir outra cópia»

Os nós que recusaram uma proposta aceita formam um grupo novo, com cópia do livro e do estado de antes de aceitar o registro (`sistema/core/network.py:196-207`). Daí em diante cada grupo elege e vota só entre os próprios membros (`sistema/core/network.py:7-10`). «Seguir outra cópia» é isso: a cabeça da cadeia deixa de ser a do grupo que aceitou o registro. A cópia de referência, onde a acurácia do protocolo é lida, é o grupo com mais nós não maliciosos (`sistema/core/network.py:105-110`).

## Registro forjado

Se o líder é malicioso e o ataque é `forge`, o estado proposto é reescrito: no EMA, reputação 1 para o conluio e 0 para os demais (`sistema/core/protocol.py:183-202` e `sistema/core/protocol.py:231-232`). O recálculo honesto não reproduz esse estado, então `objective_check` devolve `"forged"` (`sistema/core/protocol.py:267-273`). No beta, a forja soma 20 nas contagens de acerto do conluio e de erro dos outros (`sistema/core/protocol.py:190-195`).

## «Recompensa»

Não há mensagem de recompensa no protocolo. No registro da EMA, recompensa é `max(0, delta)` e, na fórmula, `α (1 − r)` quando `s = 1` (`sistema/core/reputation.py:13-16` e `sistema/core/reputation.py:144`). A coluna `reward` do CSV é esse número (`sistema/core/metrics.py:63`).

## Gênese

No código, gênese é só `GENESIS_HASH` (`sistema/core/ledger.py:28`). Três rodadas sem líder, sem proposta e sem voto: **NÃO ENCONTRADO NO CÓDIGO**. A calibração de três rodadas continua elegendo líder, como descrito acima.

## Resposta omitida ou ausente

O perfil instável pode devolver `None` (`sistema/core/behavior.py:115-118`). A grade do artigo usa `unstable=0` (`sistema/scripts/run_a3_n50.py:33`), e honesto e malicioso sempre devolvem um número (`sistema/core/behavior.py:103-113`). Nestes experimentos a omissão não ocorre. O ataque `censor` tira do registro as respostas de quem não é do conluio (`sistema/core/protocol.py:220-221`); a grade A3 usa `forge`, não `censor` (`sistema/scripts/run_a3_n50.py:83`). Ausência, quando existe, não entra no consenso (`sistema/core/consensus.py:89-90`) e conta como `s = 0` (`sistema/core/engine.py:111-115`).

## Topologia 4-regular

`build_graph(..., "kregular", degree=4, seed)` (`sistema/core/topology.py:37-72`; o padrão `degree=4` está em `sistema/simulate.py:395`). Começa como anel: cada nó liga a `degree/2` vizinhos de cada lado (`sistema/core/topology.py:131-136`). Depois troca arestas ao acaso, com semente `topology:{seed}:{n}:{k}`, mantendo o grau e a conexidade (`sistema/core/topology.py:61-63` e `sistema/core/topology.py:144-166`). Os vizinhos são sorteados por essa semente; o nó não escolhe. Motivo, no repositório, para o grau ser 4 e não outro número: **NÃO ENCONTRADO NO CÓDIGO**. O artigo comenta o que aconteceria se a reputação fosse local nesse grau (`artigo/artigov2.tex:149`); isso não é um comentário do gerador.

## Conjunto de dados

A simulação sem modelo carrega `sistema/core/data/gsm8k_sample.json`, que tem 10 tarefas, `sample-0` a `sample-9`, com `id`, `question` e `answer` já numérico (`sistema/core/dataset.py:22-26`). São contas curtas (maçãs, páginas, troco, times, tanque, poupança, ovos, trem, cadernos, alunos). A rodada `t` usa a tarefa `t mod 10` (`sistema/simulate.py:146`), então 50 rodadas repetem as 10 tarefas cinco vezes. O comentário do carregador diz que a amostra é offline para não baixar o GSM8K (`sistema/core/dataset.py:5-6`). Motivo, no código, para serem exatamente 10: **NÃO ENCONTRADO NO CÓDIGO**. A extração pelo marcador `####`, ou pelo último número, está em `sistema/core/answer.py:18-34`. Ela vale para o GSM8K oficial (`sistema/core/dataset.py:48-52`) e para o texto do modelo (`sistema/node/inference.py:78`). A amostra da simulação não passa por essa função: o campo `answer` já é o número.

## Perfil honesto, perfil malicioso, e onde o gabarito entra

Honesto: com probabilidade `honest_p_correct` (0,9 na grade A3, `sistema/scripts/run_a3_n50.py:37`) devolve o gabarito; senão, o gabarito mais um inteiro de −5 a 5, diferente de zero (`sistema/core/behavior.py:103-107` e `sistema/core/behavior.py:126-134`). Malicioso: se há valor de conluio, devolve esse valor (999 na grade); senão, um erro diferente, pela mesma função (`sistema/core/behavior.py:109-113`). Os dois perfis, na simulação, recebem o gabarito só para fabricar a resposta. O comentário diz que no processo real o nó não recebe o gabarito (`sistema/core/behavior.py:11-12` e `sistema/core/schemas.py:16-18`).

Na reputação, o gabarito entra assim. Fixo híbrido: nas rodadas de teste o sinal é acerto contra o gabarito; nas outras, concordância com o consenso ponderado (`sistema/simulate.py:172-179`). Dinâmico híbrido: o registro `oracle` marca certo quem respondeu igual ao gabarito, com α do gabarito, na calibração e nos testes (`sistema/core/protocol.py:456-462` e `sistema/core/protocol.py:150`). Dinâmico só com consenso: o gabarito não atualiza reputação (`sistema/core/protocol.py:146-147`). A coluna `correct` dos CSVs continua comparando com o gabarito mesmo quando o sinal da reputação é o consenso (`sistema/core/engine.py:78-79` e `sistema/core/engine.py:111`).
