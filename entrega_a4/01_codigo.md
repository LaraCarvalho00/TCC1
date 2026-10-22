# Etapa 1 — identificação do código

Os comandos abaixo foram executados na raiz do repositório em 22/10/2026, por volta de 11:13 (−03).

## 1. Branch, commit, status e log

- Branch no início da tarefa: `main`, acompanhando `origin/main`.
- Hash: `44190e7288cedc7d0d05313c3da555412763bc37` (curto: `44190e7`).
- Autor e data: Lara Andrade Carvalho, `laraandrade312@gmail.com`, Sun Oct 11 00:57:30 2026 −0300.
- Mensagem: «Explica os dois gráficos do artigo, painel por painel, e aponta os scripts para a pasta organizada.»

`git status` no início (antes de criar `entrega_a4/`):

```
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
	modified:   sistema/node/inference.py
	modified:   sistema/simulate.py

Untracked files:
	.DS_Store
	Protótipos/Definicoes-equacoes-artigo.md
	artigo.md
	artigo.tex
	artigo/artigov2.zip
	entrega-orientacao.md
	entrega-orientacao/
	figuras/
	orientacao-literatura-equacao-cenarios.md
	sistema/scripts/run_com_smol.py
	sistema/scripts/run_com_smol_escala.py
	sistema/scripts/run_gradativo_n50.py
```

`git log --since=2026-10-11 --stat` devolveu saída vazia (exit 0). O Git completa uma data sem horário com a hora atual do relógio. Às 11:13, `--since=2026-10-11` significa «desde 11/10 às 11:13». Os dois commits desse dia são anteriores a isso:

| Hash | CommitDate | Assunto |
| --- | --- | --- |
| `44190e7` | 2026-10-11 00:57:30 −0300 | Explica os dois gráficos do artigo, painel por painel, e aponta os scripts para a pasta organizada. |
| `8c1dcea` | 2026-10-11 00:49:47 −0300 | Guarda os gráficos da A3 e o texto revisado que os explica. |

O mesmo intervalo com horário explícito, `git log --since='2026-10-11 00:00:00' --oneline`, lista esses dois commits. Nenhum commit é posterior a 11/10/2026. O commit anterior, `04159bb`, é de 10/10/2026 (merge do orquestrador dinâmico).

Remote: `origin` = `https://github.com/LaraCarvalho00/TCC1.git`.

## 2. Diferença em relação a `44190e7`

`git diff --stat 44190e7` só enxerga arquivo rastreado. A saída, com a árvore ainda suja, foi:

```
 sistema/node/inference.py | 31 ++++++++++++++++++++++++-------
 sistema/simulate.py       |  8 ++++++--
 2 files changed, 30 insertions(+), 9 deletions(-)
```

Arquivos não rastreados não entram nesse comando. Estão listados no status acima.

Uma linha por mudança em relação a `44190e7`:

| Arquivo | O que muda |
| --- | --- |
| `sistema/node/inference.py` | Passa a usar MPS quando não há CUDA, com `float16` em CUDA/MPS, e tenta `enable_thinking=False` no chat template. |
| `sistema/simulate.py` | Aceita `tasks` e `model_answers` opcionais; se houver resposta de modelo, o nó honesto usa essa resposta em vez de sortear. |
| `sistema/scripts/run_com_smol.py` | Arquivo novo. Roda o protocolo com respostas do SmolLM3-3B; a decodificação é gulosa, então todo honesto repete a mesma resposta. |
| `sistema/scripts/run_com_smol_escala.py` | Arquivo novo. O mesmo modelo em redes de 100 e 200 nós, uma pergunta nova do GSM8K por rodada. |
| `sistema/scripts/run_gradativo_n50.py` | Arquivo novo. Curvas rodada a rodada em 50 nós, frações 0, 5, 20, 35, 50, 65 e 80%, fixo com gabarito em toda rodada. |
| `artigo.md`, `artigo.tex`, `artigo/artigov2.zip` | Arquivos novos. Texto e pacote do artigo; não estavam neste commit. |
| `entrega-orientacao.md`, `entrega-orientacao/` | Arquivos novos. Nota de encaminhamento, HTML e duas figuras (acerto por rodada; reputação em 50% e 80%). |
| `figuras/artigo/` | Arquivos novos. PDFs dos gráficos do artigo. |
| `orientacao-literatura-equacao-cenarios.md` | Arquivo novo. Notas de literatura, equação e cenários. |
| `Protótipos/Definicoes-equacoes-artigo.md` | Arquivo novo. Definições e equações em rascunho. |
| `.DS_Store` | Metadado do macOS. Não entra no commit. |

Os números desta entrega chamam `run_simulation` sem `tasks` e sem `model_answers`. O trecho novo de `simulate.py` não muda essas execuções: com os dois atributos ausentes, o fluxo é o de `44190e7`. `inference.py` não é importado pela simulação sem modelo.

## 3. Calibração sem líder

**NÃO ENCONTRADO NO CÓDIGO** o procedimento «três primeiras rodadas sem eleição, sem proposta e sem voto, gravando a gênese».

O que existe com o nome de calibração é outra coisa: nas primeiras rodadas o gabarito também atualiza a reputação, **depois** de eleger, propor e votar.

O preset liga três rodadas (`sistema/core/defenses.py`):

```22:33:sistema/core/defenses.py
MEASURES = ("calibration", "oracle_bypass", "split_alpha", "split_scores", "refuse_forged")
DEFAULT_CALIBRATION_ROUNDS = 3
...
    calibration_rounds: int = 0
```

```52:53:sistema/core/defenses.py
    if measure == "calibration":
        return replace(config, calibration_rounds=DEFAULT_CALIBRATION_ROUNDS if on else 0)
```

`preset("all")` liga essa medida (`sistema/core/defenses.py:74-77`). A rodada é de gabarito quando o índice é menor que `calibration_rounds`, no sinal híbrido (`sistema/core/protocol.py`):

```144:150:sistema/core/protocol.py
def oracle_round(round_index: int, config: ProtocolConfig) -> bool:
    """Indica se o juiz do experimento corrige esta rodada pelo gabarito."""
    if config.signal == "consensus":
        return False
    if config.signal == "truth":
        return True
    return round_index < config.defense.calibration_rounds or is_test_round(round_index, config.test_every)
```

A simulação dinâmica não desvia essas rodadas. Ela sempre elege o líder e monta a proposta (`sistema/core/network.py:154-174`) e só então, se `oracle_round` for verdadeiro, anexa o registro de gabarito (`sistema/core/network.py:128-131`).

A palavra «gênese» no código é o hash anterior da cadeia vazia, 64 zeros, não um bloco de rodadas (`sistema/core/ledger.py:28` e `sistema/core/ledger.py:95-96`).

O texto que descreve três rodadas sem líder está em `orientacao-literatura-equacao-cenarios.md` (por exemplo as linhas 123 e 140). Isso é nota, não implementação.

## 4. Branch `a4-dados`

Commit dos dados e do código local: `0713bad7e2ccd0e54ebd950390b4d40fcab13f0d` (curto: `0713bad`), branch `a4-dados`. Mensagem: «Publica os dados da correção A4 junto com o código local ainda não commitado.»

Esse commit parte de `44190e7`. O commit seguinte nesta branch só grava este hash em `COMMIT.txt`, `01_codigo.md` e `RESUMO.md`. O push da branch `a4-dados` para `https://github.com/LaraCarvalho00/TCC1.git` foi aceito.
