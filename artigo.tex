%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Template TCC Engenharia de Software - PUC Minas
% Versão alinhada ao sistema implementado e à grade experimental
% de 8.400 execuções (simulação in-process, sem LLM).
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\documentclass[12pt]{article}

\usepackage[utf8]{inputenc}
\usepackage{sbc-template}
\usepackage{graphicx,url}
\usepackage{float}
\usepackage[brazil]{babel}
\usepackage{tabularx}
\newcolumntype{C}{>{\centering\arraybackslash}X}
\newcolumntype{L}[1]{>{\raggedright\arraybackslash}m{#1}}
\usepackage[inline]{enumitem}
\usepackage{tcolorbox}
\usepackage{amsmath}
\usepackage{tikz}
\usetikzlibrary{arrows.meta,positioning,shapes.geometric}

%%%%%%%%%%%%%%%%% Pacotes para inserção de algoritmos - BEGIN
\usepackage[ruled,lined]{algorithm2e}

\usepackage{xcolor}
\usepackage{pgfplots}
\usepgfplotslibrary{groupplots}
\pgfplotsset{compat=1.17}
\definecolor{verde}{rgb}{0.25,0.5,0.35}
\definecolor{jpurple}{rgb}{0.5,0,0.35}
\definecolor{darkgreen}{rgb}{0.0, 0.2, 0.13}

\usepackage{listings}
\lstset{
    language=Python,
    basicstyle=\ttfamily\small,
    keywordstyle=\color{jpurple}\bfseries,
    stringstyle=\color{red},
    commentstyle=\color{verde},
    morecomment=[s][\color{blue}]{/**}{*/},
    extendedchars=true,
    showspaces=false,
    showstringspaces=false,
    numbers=left,
    numberstyle=\tiny,
    breaklines=true,
    backgroundcolor=\color{white!10},
    breakautoindent=true,
    captionpos=b,
    xleftmargin=0pt,
    tabsize=2
}
%%%%%%%%%%%%%%%%% Pacotes para inserção de algoritmos - END

\sloppy
\raggedbottom

\title{Simulação de Rede Distribuída para Inferência de IA com Avaliação de Confiabilidade baseada em Reputação}

\author{Allan Mateus de Souza Arruda\inst{1}, Lara Andrade Carvalho\inst{1}}

\address{Curso de Engenharia de Software -- Pontifícia Universidade Católica de Minas Gerais (PUC Minas)\\
  Belo Horizonte -- MG -- Brasil
  \email{\{allan.arruda, lara.carvalho\}@sga.pucminas.br}
}

\begin{document}

\maketitle

\begin{abstract}
  Distributed execution of Artificial Intelligence (AI) inference can reduce dependence on a single provider, but it also exposes the aggregated result to honest errors, timeouts, and Byzantine behaviour. This undergraduate thesis investigates whether a lightweight reputation mechanism can mitigate that impact in a \emph{simulated} network of redundant inference. The implemented architecture is a star: a fixed central orchestrator broadcasts the same task to $N$ nodes, aggregates answers by reputation-weighted consensus and by simple majority, and then evaluates accuracy against a held-out Ground Truth. Operational reputation is an exponential moving average driven by agreement with the weighted consensus and by missing answers; Ground Truth is not used to update reputation in the main experimental loop. A separate Validation Round, which may use Ground Truth, is implemented but was not enabled in the reported grid. Quantitative experiments cover 8{,}400 in-process simulation runs (ten network sizes, seven adversary levels, four behavioural configurations, 50 rounds, 30 seeds). Without collusion, both aggregators remain accurate up to high fractions of independent wrong answers. With collusion at 50\% of $N=50$ nodes, weighted consensus and majority both fall to $7.9\%\pm 3.7\%$: equal initial weights and a hold rule under weak consensus keep reputation from separating the groups; at higher collusion the same update rule starts rewarding the attacking block. The study does not claim a deployed peer-to-peer system, a blockchain, or superiority of reputation in every regime.
\end{abstract}

\begin{resumo}
  A execução distribuída de inferência de Inteligência Artificial (IA) pode reduzir a dependência de um único provedor, mas também expõe o resultado agregado a erros honestos, ausências de resposta e comportamento bizantino. Este trabalho investiga se um mecanismo leve de reputação mitiga esse impacto em uma rede \emph{simulada} de inferência redundante. A arquitetura implementada é em estrela: um orquestrador central fixo envia a mesma tarefa a $N$ nós, agrega as respostas por consenso ponderado por reputação e por maioria simples e, em seguida, avalia a acurácia em relação a um \textit{Ground Truth} retido. A reputação operacional é uma média móvel exponencial alimentada pela concordância com o consenso ponderado e pela ausência de resposta; o \textit{Ground Truth} não atualiza a reputação no laço experimental principal. Uma Rodada de Validação separada, que pode usar o gabarito, está implementada, mas não participou da grade relatada. Os experimentos quantitativos abrangem 8.400 execuções em simulação in-process (dez tamanhos de rede, sete níveis de adversários, quatro configurações comportamentais, 50 rodadas e 30 sementes). Sem conluio, ambos os agregadores permanecem acurados até frações altas de respostas incorretas independentes. Com conluio em 50\% dos nós em $N=50$, o consenso ponderado e a maioria caem ambos para $7{,}9\%\pm 3{,}7\%$: pesos iniciais iguais e a regra de manutenção sob consenso fraco impedem que a reputação separe os grupos; com conluio maior, a mesma regra de atualização passa a premiar o bloco atacante. O estudo não afirma tratar-se de uma rede par-a-par implantada, de uma \textit{blockchain} ou de superioridade da reputação em todos os regimes.
\end{resumo}

\begin{tcolorbox}
\footnotesize
\textbf{Bacharelado em Engenharia de \emph{Software} - PUC Minas\\
Trabalho de Conclusão de Curso (TCC)} \\

\indent Orientadora do TCC II: Isabela Borlido Barcelos \\ \\
Belo Horizonte, 20 de setembro de 2026.
\end{tcolorbox}

% -----------------------------------------------------------
% SEÇÃO 1 - INTRODUÇÃO (contínua, sem subseções)
% -----------------------------------------------------------
\section{Introdução}

A demanda por tarefas de Inteligência Artificial (IA) motiva arquiteturas que repartem a inferência entre múltiplos participantes, inclusive na borda da rede, para ampliar a disponibilidade e aproveitar recursos computacionais distribuídos \cite{shi2016,tanenbaum2017,coulouris2021,russell2020}. Este trabalho avalia a \textbf{confiabilidade do resultado agregado} quando a mesma tarefa é enviada a vários nós e uma decisão coletiva precisa ser formada. Nesse arranjo de inferência redundante, a replicação oferece diversidade de respostas, mas transfere para o mecanismo de agregação a responsabilidade de lidar com falhas, indisponibilidade e manipulação intencional.

Nessa organização, os participantes operam com autonomia limitada pelo protocolo experimental, mas não são igualmente confiáveis. Um nó pode responder de forma correta na maior parte das vezes, falhar em devolver resposta no prazo ou enviar propositalmente um valor inconsistente. O último caso corresponde, no vocabulário clássico de sistemas distribuídos, a uma Falha Bizantina: um subconjunto de agentes transmite informações arbitrárias para corromper a decisão coletiva \cite{lamport1982,castro1999}. Tais falhas não são exclusivas do treinamento colaborativo de modelos; elas também afetam a fase de inferência, na qual o bem a proteger é a resposta devolvida, e não o vetor de parâmetros. Garantir consistência sob falhas arbitrárias com protocolos criptograficamente pesados pode ser desproporcional ao escopo de um simulador acadêmico. Por isso, este trabalho investiga o seguinte problema de pesquisa: \textbf{como um mecanismo de reputação, atualizado apenas com sinais observáveis da própria rede, altera a acurácia do consenso em uma rede simulada de inferência redundante na presença de nós maliciosos e instáveis?}

A reputação entra como \emph{hipótese operacional}, não como solução já comprovadamente superior. Sistemas clássicos como o \textit{EigenTrust} mostram que o histórico de interações pode reduzir a influência de pares não confiáveis em redes par-a-par \cite{kamvar2003}. Trabalhos recentes aplicam ideia semelhante ao \emph{treinamento} federado, ponderando atualizações de modelo \cite{chen2024}. Este TCC desloca a pergunta para a \emph{inferência}: os nós não treinam em conjunto; eles respondem à mesma questão e o orquestrador agrega as respostas. A reputação atribui pesos distintos aos votos. Se o histórico refletir o comportamento observado, nós que sistematicamente divergem do consenso tendem a perder influência. Se o consenso estiver empatado ou capturado por um bloco em conluio, o mesmo mecanismo pode falhar em distinguir o grupo honesto. Essa ambiguidade é exatamente o que o experimento procura medir.

A investigação situa-se na Engenharia de Software voltada à confiabilidade e à observabilidade: interessa definir uma arquitetura reproduzível, instrumentar rodadas e comparar dois agregadores sob as mesmas condições. O mecanismo leve de reputação atua sobre respostas de inferência; diferentemente de abordagens baseadas em \textit{blockchain}, não envolve armazenamento imutável, mineração, validação criptográfica ou contratos inteligentes \cite{blockchainAI2024}. Docker, APIs HTTP e um backend opcional de modelo de linguagem compõem a infraestrutura, enquanto os resultados numéricos deste documento provêm de simulação in-process com perfis comportamentais, sem execução de LLM e sem rede física.

O \textbf{objetivo geral} é analisar, por experimentação quantitativa em ambiente simulado e controlado, o impacto de um mecanismo de reputação na acurácia do consenso de inferência redundante. Os objetivos específicos são: (i) especificar e implementar um simulador com orquestrador central, nós com perfis honesto, malicioso e instável, consenso ponderado e maioria simples; (ii) atualizar reputação por média móvel exponencial a partir de concordância com o consenso ponderado e de ausência de resposta, sem usar \textit{Ground Truth} no laço principal; (iii) comparar os dois agregadores em uma grade que varia o tamanho da rede, a fração de nós problemáticos e a presença de conluio e de instabilidade. Espera-se um diagnóstico empírico --- inclusive dos regimes em que a reputação \emph{não} separa os grupos --- e não a demonstração de um sistema pronto para implantação.

O restante deste documento está organizado da seguinte forma. A Seção~\ref{sec:fundamentacao} apresenta a fundamentação teórica. A Seção~\ref{sec:relacionados} discute trabalhos relacionados, com ênfase no contraste entre treinamento colaborativo e inferência redundante. A Seção~\ref{sec:metodos} descreve materiais e métodos alinhados ao código. A Seção~\ref{sec:resultados} reporta os resultados da grade de 8.400 execuções. A Seção~\ref{sec:conclusao} sintetiza limitações e trabalho futuro.

% -----------------------------------------------------------
% SEÇÃO 2 - FUNDAMENTAÇÃO TEÓRICA
% -----------------------------------------------------------
\section{Fundamentação Teórica}
\label{sec:fundamentacao}

A literatura de sistemas distribuídos trata coordenação, falhas e consistência como problemas de projeto, independentemente de o payload ser um arquivo, um log de transações ou a saída de um modelo de IA \cite{tanenbaum2017,coulouris2021}. A computação em borda motiva processar dados perto da fonte \cite{shi2016}, e revisões de IA distribuída discutem robustez, privacidade e governança em larga escala \cite{wei2025,wang2025}. Neste TCC, esses conceitos apenas situam o problema: a implementação avaliada é um simulador local com topologia em estrela, não uma implantação em dispositivos de borda.

\subsection{Inteligência Artificial Distribuída: treinamento versus inferência}

Inteligência Artificial Distribuída cobre pelo menos dois arranjos distintos. No \emph{treinamento colaborativo} (aprendizado federado), os participantes enviam atualizações de parâmetros derivadas de dados locais; o coordenador agrega pesos ou gradientes \cite{mcmahan2017,bonawitz2019,kairouz2021}. Na \emph{inferência redundante}, adotada aqui, não há aprendizado conjunto: a mesma tarefa é submetida a vários nós e a rede devolve uma única resposta. A escolha pela redundância permite medir acurácia contra um gabarito e injetar comportamento malicioso controlado sem particionar o modelo (paralelismo de camadas ou de tensores fica fora do escopo).

Falhas Bizantinas \cite{lamport1982,castro1999} aplicam-se aos dois arranjos. No treinamento, o adversário corrompe o modelo; na inferência, corrompe a resposta agregada. O simulador representa o segundo caso por nós maliciosos que devolvem valores incorretos --- eventualmente o mesmo valor, para modelar conluio --- e por nós instáveis que omitem a resposta com probabilidade configurável. Essa modelagem é deliberadamente simples e não reproduz a heterogeneidade de uma rede real.

Protocolos de consenso clássicos alinham estado entre réplicas \cite{tanenbaum2017}. O mecanismo deste trabalho não é PBFT nem um registro imutável. Ele é um agregador de votos: maioria simples, como linha de base sem memória, e soma de reputações por resposta, como hipótese de confiança incremental. Abordagens inspiradas em \textit{blockchain} para compartilhar modelos \cite{blockchainAI2024,chen2024} permanecem apenas como contraste: o repositório não contém cadeia de blocos.

\subsection{Sistemas de Reputação em Redes Distribuídas}

Sistemas de reputação registram o histórico de comportamento e modulam a influência de cada participante. O \textit{EigenTrust} constrói confiança global a partir de interações locais em redes P2P \cite{kamvar2003}. Em aprendizado federado, a reputação pode ponderar atualizações maliciosas \cite{chen2024}. O mecanismo implementado neste TCC é mais restrito. Cada nó inicia com reputação $0{,}5$. Após cada rodada de inferência, um sinal $s \in \{0,1\}$ deriva da concordância com o consenso ponderado já calculado, ou da ausência de resposta; se não houver consenso com confiança mínima, a reputação permanece inalterada. Não se calcula centralidade de autovetor, não se usa similaridade de cosseno e, no fluxo principal, não se consulta o gabarito para atualizar pesos. O \textit{EigenTrust} e a federação com reputação fundamentam a \emph{ideia} de histórico; as equações efetivamente executadas estão na Seção~\ref{sec:metodos}.

% -----------------------------------------------------------
% SEÇÃO 3 - TRABALHOS RELACIONADOS
% -----------------------------------------------------------
\section{Trabalhos Relacionados}
\label{sec:relacionados}

Esta seção organiza a literatura em cinco eixos. Para cada um, distingue-se o que este trabalho reutiliza conceitualmente do que ele deliberadamente não implementa. O objetivo não é cobrir exaustivamente cada campo, mas situar com precisão um recorte estreito: a confiabilidade de uma resposta agregada na fase de inferência.

\subsection{Confiança e governança em IA distribuída}

Wei e Liu \cite{wei2025} sistematizam robustez, privacidade e governança em sistemas de IA distribuída e propõem uma taxonomia de contramedidas que separa dois momentos do ciclo de vida: a robustez a ataques de evasão e a consultas irregulares na \textit{inferência}, e a robustez a envenenamento, ataques bizantinos e distribuição irregular de dados no \textit{treinamento}. Os autores argumentam que confiança não é atributo isolado do modelo, mas propriedade da arquitetura que coordena os participantes.

Duas consequências interessam a este trabalho. Primeira, a própria taxonomia reconhece a inferência como superfície de ataque autônoma, e não como subproduto do treinamento --- recorte adotado aqui. Segunda, o estudo organiza contramedidas em nível conceitual, mas não define o procedimento experimental de inferência redundante usado neste TCC. Este trabalho apropria-se da ênfase arquitetural e a reduz a um experimento mensurável, com orquestrador, perfis comportamentais e dois agregadores comparados sob as mesmas sementes.

Abordagens inspiradas em \textit{blockchain} para compartilhamento confiável de modelos \cite{blockchainAI2024} situam-se no mesmo eixo, mas deslocam a garantia para armazenamento imutável e validação criptográfica. Este trabalho não implementa cadeia de blocos, mineração nem contratos inteligentes: mede como pesos de confiança afetam a resposta agregada em uma rede simulada.

\subsection{Aprendizado federado: o contraste}

McMahan et al. \cite{mcmahan2017}, Bonawitz et al. \cite{bonawitz2019} e Kairouz et al. \cite{kairouz2021} consolidaram o treinamento colaborativo a partir de dados descentralizados: formalização do protocolo de agregação de parâmetros, arquiteturas de larga escala e mapeamento de desafios como custo de comunicação, heterogeneidade de dados e disponibilidade variável dos nós. Wang et al. \cite{wang2025} estendem a discussão para execução assíncrona em dispositivos de borda.

O objeto protegido nesses trabalhos é o vetor de parâmetros; o sinal agregado é um gradiente ou um conjunto de pesos. A limitação para este estudo é direta: eles não avaliam inferência redundante, na qual o bem a proteger é a resposta devolvida e a agregação ocorre sobre valores discretos comparáveis a um gabarito. Reutiliza-se apenas a intuição de coordenar participantes autônomos, deslocando a métrica para a acurácia da resposta agregada.

Chen et al. \cite{chen2024} aproximam-se mais ao aplicar reputação para mitigar atualizações maliciosas em aprendizado federado assíncrono associado a \textit{blockchain}. A ideia de ponderar por histórico é reaproveitada aqui. O vínculo com a atualização de modelo e com a cadeia de blocos não é reproduzido, e a ponderação passa a incidir sobre respostas, não sobre parâmetros.

\subsection{Reputação em redes par-a-par}

O \textit{EigenTrust} \cite{kamvar2003} constrói uma medida de confiança global a partir de interações locais entre pares, propaga confiança sobre uma matriz de interações e ancora o cálculo em participantes previamente confiáveis. O algoritmo mostra que histórico local, agregado adequadamente, pode reduzir a influência de pares que distribuem conteúdo inautêntico.

A diferença para este TCC é dupla. O algoritmo foi concebido para compartilhamento de arquivos, no qual a avaliação de uma transação é binária e verificável localmente; além disso, pressupõe uma rede par-a-par, enquanto a arquitetura aqui avaliada é uma estrela com orquestrador fixo. O mecanismo implementado adapta somente o princípio de memória de interações, na forma de uma média móvel exponencial sobre a concordância observada com o consenso ponderado. Não se calcula matriz de confiança transitiva, não se adotam nós previamente confiáveis e não se emprega centralidade sobre um grafo de concordância.

\subsection{Falhas bizantinas e consenso}

Lamport et al. \cite{lamport1982} formalizam o problema de acordo sob falhas arbitrárias, e Castro e Liskov \cite{castro1999} demonstram um protocolo prático capaz de tolerar um número limitado de réplicas maliciosas. A discussão permanece ativa: Wu et al. \cite{wu2024} sistematizam a evolução dos protocolos tolerantes a falhas bizantinas, enquanto Bouhata et al. \cite{bouhata2025} revisam a tolerância bizantina em aprendizado de máquina distribuído, com ênfase em otimização e treinamento. Essa segunda linha reforça, por contraste, o recorte deste trabalho na fase de inferência.

Essas formulações visam réplicas de serviço ou agregação de gradientes, não respostas numéricas produzidas por participantes simulados. O mecanismo avaliado aqui não é PBFT nem pretende equivalência com ele: é um agregador de votos sem autenticação nem registro imutável.

Os limites clássicos de acordo bizantino pressupõem uma fração minoritária de participantes faltosos. O colapso observado neste trabalho a partir de 50\% de nós coludidos é coerente com esses limites e não deve ser lido como uma violação das garantias dos protocolos clássicos. O experimento mede onde e como a degradação ocorre em um agregador leve, inclusive o regime em que a própria atualização de reputação passa a favorecer o bloco atacante.

\subsection{Conteinerização de ambientes experimentais}

A conteinerização \cite{docker2026,burns2022} é prática corrente para isolar processos, dependências e configurações de execução e fornece fundamentos de reprodutibilidade para experimentos rastreáveis. O repositório inclui \texttt{Dockerfile} e um servidor HTTP por nó, úteis para execuções com comunicação em rede. Essa infraestrutura não constitui contribuição científica e não sustentou a grade relatada, realizada em processo. Contêineres tampouco substituem uma implantação real com latência física, falhas de hardware e heterogeneidade plena.

\subsection{Síntese da lacuna}

Parte da literatura discute confiança em IA distribuída em nível conceitual; outra parte aplica reputação ao treinamento federado; uma terceira formaliza consenso sob falhas arbitrárias para réplicas de serviço. A lacuna abordada é estreita e empírica: medir, em simulação controlada e reprodutível, se um mecanismo de reputação atualizado apenas com sinais observáveis da própria rede melhora a acurácia da inferência redundante frente à maioria simples --- e identificar os regimes em que isso deixa de ocorrer.

% -----------------------------------------------------------
% SEÇÃO 4 - MATERIAIS E MÉTODOS
% -----------------------------------------------------------
\section{Materiais e Métodos}
\label{sec:metodos}

A metodologia é experimental quantitativa. As variáveis independentes são o tamanho da rede $N$, o percentual nominal de nós problemáticos e a configuração comportamental (conluio e presença de instáveis). As variáveis dependentes principais são a acurácia do consenso ponderado e a acurácia da maioria simples, ambas medidas contra o \textit{Ground Truth} \emph{depois} da agregação. A simulação local permite controlar perfis e sementes; em contrapartida, não generaliza para redes reais. A Figura~\ref{fig:visao-geral} resume o fluxo. A Figura~\ref{fig:arquitetura-gt} separa os três fluxos do sistema: a operação normal, a avaliação experimental e a Rodada de Validação controlada.

\begin{figure}[H]
\centering
\resizebox{0.98\textwidth}{!}{%
\begin{tikzpicture}[
    fase/.style={
        rectangle, rounded corners=3pt, draw=black!70, fill=gray!8,
        minimum height=1.6cm, text width=2.7cm, align=center, font=\footnotesize
    },
    seta/.style={-{Latex[length=2.5mm]}, thick}
]
\node[fase] (f1) {\textbf{1. Configuração}\\ $N$, percentual, conluio/instáveis, semente};
\node[fase, right=0.45cm of f1] (f2) {\textbf{2. Simulação}\\ Perfis honestos, maliciosos e instáveis in-process};
\node[fase, right=0.45cm of f2] (f3) {\textbf{3. Consenso}\\ Ponderado por reputação e maioria simples};
\node[fase, right=0.45cm of f3] (f4) {\textbf{4. Reputação}\\ Concordância com o consenso ou ausência; sem gabarito};
\node[fase, right=0.45cm of f4] (f5) {\textbf{5. Avaliação}\\ Acurácia \textit{versus} \textit{Ground Truth} e registro};
\draw[seta] (f1) -- (f2);
\draw[seta] (f2) -- (f3);
\draw[seta] (f3) -- (f4);
\draw[seta] (f4) -- (f5);
\end{tikzpicture}%
}
\caption{Etapas do laço experimental principal. O \textit{Ground Truth} entra só na etapa 5.}
\label{fig:visao-geral}
\end{figure}

\begin{figure}[H]
\centering
\resizebox{0.96\textwidth}{!}{%
\begin{tikzpicture}[
    bloco/.style={rectangle, rounded corners=2pt, draw=black!70, fill=gray!8,
        minimum height=1.2cm, text width=2.7cm, align=center, font=\footnotesize},
    externo/.style={bloco, fill=green!10, draw=green!50!black},
    opcional/.style={bloco, fill=orange!12, draw=orange!70!black},
    seta/.style={-{Latex[length=2.3mm]}, thick}
]
\node[bloco] (task) {\textbf{Tarefa normal}\\Pergunta sem gabarito};
\node[bloco, right=0.55cm of task] (orch) {\textbf{Orquestrador}\\Distribuição e coleta};
\node[bloco, right=0.55cm of orch] (nodes) {\textbf{Nós de inferência}\\Honestos, maliciosos e instáveis};
\node[bloco, right=0.55cm of nodes] (cons) {\textbf{Consenso}\\Maioria e ponderado};
\node[bloco, right=0.55cm of cons] (answer) {\textbf{Resposta final}};
\node[externo, below=0.65cm of cons] (eval) {\textbf{Avaliador experimental}\\Gabarito GSM8K $\rightarrow$ métricas};
\node[opcional, below=0.65cm of orch] (validation) {\textbf{Rodada de Validação}\\Pergunta reservada; atualização individual};
\draw[seta] (task) -- (orch);
\draw[seta] (orch) -- (nodes);
\draw[seta] (nodes) -- node[above,font=\scriptsize]{respostas} (cons);
\draw[seta] (cons) -- (answer);
\draw[seta] (answer) -- (eval);
\draw[seta,dashed] (validation) -- (nodes);
\draw[seta,dashed] (nodes) -- (validation);
\end{tikzpicture}%
}
\caption{Separação entre operação normal, avaliação experimental (verde) e validação controlada opcional (laranja). O gabarito do avaliador não realimenta o consenso normal; a Rodada de Validação não participou dos resultados relatados.}
\label{fig:arquitetura-gt}
\end{figure}

\subsection{Ambiente de Simulação e Ferramentas}

O núcleo do experimento está em Python\footnote{Repositório do projeto: \url{https://github.com/LaraCarvalho00/TCC1}}. Cada ``nó'' é um identificador com perfil comportamental; o orquestrador chama o pipeline em processo, sem Docker na grade relatada. Tarefas vêm da amostra offline do GSM8K \cite{cobbe2021}, com extração da resposta numérica após o marcador \texttt{\#\#\#\#} e correspondência exata. Latências são amostradas de intervalos uniformes configuráveis e \textbf{não} representam tempo de inferência de um modelo. O repositório prevê um modo com modelo causal (SmolLM3-3B via Transformers) e nós HTTP; esses modos não geraram os números da Seção~\ref{sec:resultados}. Ollama não é o backend do código atual.

As 8.400 execuções foram concluídas em 92{,}24\,s\footnote{Máquina de coleta: Intel Core i7-13650HX (20 núcleos lógicos), 15{,}73\,GB de RAM.}, tempo compatível com simulação de perfis e incompatível com 8.400 sessões de LLM.

\subsection{Arquitetura e Componentes do Simulador}

A topologia é em \textbf{estrela}. Na grade executada, o identificador \texttt{node-0} representa o orquestrador e também emite uma resposta honesta; por isso, conta em $N$. Os demais $N-1$ participantes podem ser sorteados como maliciosos ou instáveis. Essa convenção é registrada nos artefatos e deve ser considerada ao comparar os resultados com arquiteturas nas quais o coordenador não realiza inferência. Não há overlay P2P nem eleição de coordenador.

\begin{itemize}[nosep]
    \item \textbf{Orquestrador:} escolhe a tarefa, coleta respostas, invoca consenso, reputação e métricas.
    \item \textbf{Nós simulados:} devolvem um valor numérico ou ausência, segundo o perfil.
    \item \textbf{Consenso:} calcula o vencedor ponderado e o vencedor por maioria.
    \item \textbf{Reputação:} aplica a média móvel exponencial ou a regra de manutenção (\textit{hold}).
    \item \textbf{Métricas:} grava acurácia, reputações por grupo, respostas e metadados da célula experimental.
\end{itemize}

A inferência é redundante: todos os nós recebem a mesma pergunta. Não há particionamento interno do modelo.

\subsection{Perfis comportamentais}

O perfil \textbf{honesto} não significa acerto determinístico: em simulação, ele devolve a resposta de referência com probabilidade $0{,}9$ e produz um erro numérico nos demais casos. O perfil \textbf{malicioso} altera deliberadamente o resultado, de maneira independente ou coordenada; no conluio, todos os maliciosos devolvem o valor $999$. O perfil \textbf{instável} representa intermitência: omite a resposta com probabilidade $0{,}3$, apresenta latência sintética variável e, quando responde, acerta com probabilidade $0{,}5$. Os limites de latência são parâmetros do simulador, e não medições de rede ou de LLM.

\subsection{Dataset, \textit{Ground Truth} e Rodada de Validação}

As tarefas são problemas aritméticos do GSM8K com gabarito conhecido. O \textit{Ground Truth} existe no orquestrador para (i) fabricar o comportamento do perfil na simulação (o nó honesto acerta com probabilidade $0{,}9$ em relação ao gabarito; o malicioso devolve um valor incorreto) e (ii) avaliar a acurácia do consenso. Os nós, no fluxo real previsto, não recebem o gabarito. A reputação operacional \textbf{não} compara a resposta ao gabarito.

Há um módulo separado de \textbf{Rodada de Validação}: o orquestrador envia perguntas cujo gabarito permanece no avaliador, não participa do consenso normal e pode atualizar reputação com $s=1$ (acerto) ou $s=0$ (erro); \textit{timeout} não penaliza, apenas mantém o valor. Esse fluxo está implementado e coberto por testes, mas \textbf{não} foi ativado nas 8.400 execuções. Também não há, nos resultados apresentados, agendamento probabilístico ou periódico dessas validações. Uma futura avaliação deverá reservar tarefas não usadas nas rodadas normais, registrar a estratégia de amostragem e comparar explicitamente reputação sem auditoria e reputação com auditoria.

Não se utiliza similaridade de cosseno. Respostas não numéricas extraíveis são tratadas como ausência na agregação.

O \textit{prompt} previsto para o modo com modelo (não usado na grade) é o da Listagem~\ref{lst:prompt-real}.

\begin{lstlisting}[language=Python,caption={\textit{Prompt} de inferência previsto para o modo com modelo (\texttt{sistema/node/inference.py}).},label={lst:prompt-real}]
_PROMPT_TEMPLATE = (
    "Solve the following math word problem. "
    "Show brief reasoning and end with the final numeric answer "
    "after '####'.\n\n"
    "Question: {question}\nAnswer:"
)
\end{lstlisting}

\subsection{Fluxo de uma rodada}

A ordem implementada é fixa: (1) agregar com as reputações já conhecidas; (2) atualizar reputação só com sinal observável; (3) comparar o consenso com o gabarito para métricas. Inverter (2) e (3) seria usar informação que a rede operacional não teria.

\subsection{Estratégia Experimental}

A Tabela~\ref{tab:grade} descreve a grade. O percentual nominal $p$ converte-se em inteiro por truncamento $n_{\mathrm{prob}} = \lfloor N \cdot p / 100 \rfloor$ (em código, \texttt{N * p // 100}). Assim, 5\% em $N=5$, $10$ ou $15$ resulta em \emph{zero} nós problemáticos. Nas configurações com instáveis, os nós problemáticos dividem-se 50--50; em quantidade ímpar, a sobra vai para malicioso. A variação de $N$ observa o efeito da escala sobre o agregador, sem empregar métricas de centralidade de grafos.

\begin{table}[htbp]
\centering
\caption{Configuração da grade experimental relatada.}
\label{tab:grade}
\footnotesize
\begin{tabular}{|l|p{9.2cm}|}
\hline
\textbf{Parâmetro} & \textbf{Valor} \\
\hline
Tamanhos $N$ & 5, 10, 15, 20, 25, 30, 35, 40, 45, 50 (orquestrador incluído) \\
\hline
Níveis nominais & 0\%, 5\%, 20\%, 35\%, 50\%, 65\%, 80\% \\
\hline
Configurações & Sem conluio; com conluio; sem conluio + instáveis; com conluio + instáveis \\
\hline
Rodadas por execução & 50 \\
\hline
Repetições (sementes) & 30 por célula, semente derivada da célula e do índice \\
\hline
Total & $10 \times 7 \times 4 \times 30 = 8{.}400$ execuções \\
\hline
$\alpha$ / reputação inicial / confiança mínima & $0{,}25$ / $0{,}5$ / $0{,}55$ \\
\hline
Conluio / $p$ de falha instável & valor $999$ / $0{,}3$ \\
\hline
Modo & simulação in-process (sem LLM, sem Docker) \\
\hline
\end{tabular}
\end{table}

\subsection{Consenso, reputação e GQM}

Seja $v_i$ a resposta normalizada do nó $i$ (ausências são ignoradas na soma) e $R_i^{(t)}$ a reputação \emph{antes} da rodada. O consenso ponderado escolhe

\begin{equation}
\label{eq:consenso}
\hat{v}_{\mathrm{pond}} = \arg\max_{a} \sum_{i:\, v_i = a} R_i^{(t)}.
\end{equation}

A maioria simples escolhe $\arg\max_{a} |\{i: v_i = a\}|$. Empates seguem a ordem de descoberta do máximo no dicionário de placar; não há desempate por centralidade. O fator $C_i$ de centralidade de autovetor \textbf{não} está implementado e não entra nas Equações~\ref{eq:consenso}--\ref{eq:reputacao}.

A reputação atualiza-se pela média móvel exponencial adotada neste trabalho:

\begin{equation}
\label{eq:reputacao}
R_i^{(t+1)} = (1-\alpha)\, R_i^{(t)} + \alpha\, s_i^{(t)},
\end{equation}

com $\alpha = 0{,}25$ e $R_i^{(0)} = 0{,}5$. A Equação~\ref{eq:reputacao} é uma formulação própria baseada em EMA, e não a equação do \textit{EigenTrust}. Nesta parametrização, valores maiores de $\alpha$ aumentam a influência da observação recente e aceleram a reação; valores menores preservam mais o histórico. Não foi executada análise de sensibilidade para outros valores de $\alpha$, de modo que os resultados se restringem a $0{,}25$. O sinal observável é: $s_i=0$ se $v_i$ é ausente; $s_i=1$ se $v_i$ coincide com $\hat{v}_{\mathrm{pond}}$ e a fração de peso no vencedor é $\geq 0{,}55$; $s_i=0$ se diverge desse consenso confiável; se a confiança for inferior ao limiar, $R_i$ \textbf{não muda} (\textit{hold}). Essa regra evita gravar um empate ou um conluio ainda sem maioria como se fosse verdade da rede.

\subsubsection{Evidência direta, validação e extensões não implementadas}

Nas rodadas normais, a única evidência direta é concordância ou divergência em relação ao consenso ponderado, além de ausência de resposta. A Rodada de Validação constitui um canal separado de evidência conhecida e não participou da grade. O sistema atual não coleta recomendações explícitas entre pares, não calcula reputação indireta e não mantém estados operacionais como suspeito ou em quarentena. Portanto, isolamento temporário, recuperação por auditorias positivas, resistência a inflação do tipo \textit{Sybil} e ponderação de recomendações são propostas de trabalho futuro, e nenhuma tabela deste artigo lhes atribui efeito.

Adota-se a abordagem \textit{Goal Question Metric} (GQM) para alinhar objetivos, questões e métricas, conforme a Tabela~\ref{tab:gqm}. A Tabela~\ref{tab:metricas} detalha a definição operacional de cada métrica coletada. Não se reporta ``taxa de detecção'' de maliciosos: o sistema não classifica nós, apenas reduz ou mantém pesos. Centralidade de reputação também não é métrica do código.

\begin{table}[htbp]
\centering
\caption{Modelo GQM utilizado no trabalho (métricas efetivamente coletadas).}
\label{tab:gqm}
\footnotesize
\begin{tabular}{|L{3.2cm}|L{5.0cm}|L{4.0cm}|}
\hline
\textbf{Objetivo} & \textbf{Questão} & \textbf{Métrica} \\
\hline
Avaliar a confiabilidade da agregação &
O consenso ponderado e a maioria diferem em acurácia frente ao gabarito? &
Acurácia ponderada; acurácia da maioria \\
\hline
Avaliar influência de maliciosos e instáveis &
A reputação média dos grupos se separa ao longo das rodadas? &
Evolução da reputação por perfil \\
\hline
Registrar condições de execução &
Qual a fração de respostas recebidas e o tempo amostrado? &
Disponibilidade; latência amostrada (não é tempo de LLM) \\
\hline
\end{tabular}
\end{table}

\begin{table}[htbp]
\centering
\caption{Definição operacional das métricas.}
\label{tab:metricas}
\footnotesize
\begin{tabularx}{\textwidth}{|X|X|}
\hline
\textbf{Métrica} & \textbf{Descrição} \\
\hline
Acurácia ponderada &
Fração de rodadas em que $\hat{v}_{\mathrm{pond}}$ coincide com o \textit{Ground Truth}. \\
\hline
Acurácia da maioria &
Fração de rodadas em que o voto majoritário coincide com o \textit{Ground Truth}. \\
\hline
Evolução da reputação &
Média, por rodada e por perfil, das reputações após o passo de atualização. \\
\hline
Disponibilidade &
Fração de nós que devolveram resposta na rodada (complementar aos \textit{timeouts} do perfil instável). \\
\hline
Latência amostrada &
Tempo sintético sorteado pelo perfil; não é evidência de desempenho de inferência real. \\
\hline
\end{tabularx}
\end{table}

\subsection{Rastreabilidade}

Cada célula do experimento registra o tamanho da rede, o nível nominal, a configuração comportamental, a semente, as reputações por rodada, os dois consensos e o gabarito. Esse registro permite recomputar integralmente as tabelas e as figuras da Seção~\ref{sec:resultados} a partir das sementes informadas. Os arquivos de saída e os scripts de análise estão disponíveis no repositório do projeto.

\subsection{Limitações do Estudo}

Os resultados descrevem um simulador: perfis conhecidos, gabarito usado para fabricar honestos e maliciosos, latência artificial, orquestrador infalível e tarefas exclusivamente numéricas. Não se avalia rede real, heterogeneidade de hardware, particionamento de modelo, similaridade semântica, centralidade nem inferência com LLM. Embora a Rodada de Validação esteja implementada separadamente, faltam experimentos que a amostrem durante a operação. Também não foram implementadas reputação indireta, quarentena, recuperação de nós ou métricas de falso positivo de isolamento. A convenção de contar o orquestrador honesto em $N$ reduz em uma unidade o conjunto sorteável e limita a comparação direta com trabalhos que contam apenas participantes de inferência. Generalizações para sistemas produtivos seriam indevidas.

% -----------------------------------------------------------
% SEÇÃO 5 - RESULTADOS
% -----------------------------------------------------------
\section{Resultados de Simulação}
\label{sec:resultados}

Os números a seguir foram agregados a partir dos registros das 8.400 execuções, com 30 execuções por célula. Cada execução compreende 50 rodadas. Reporta-se média $\pm$ desvio-padrão amostral da acurácia, em percentual. Esses dados validam o comportamento do simulador e permitem comparar agregadores sob perfis fabricados; não constituem resultado de desempenho ou de qualidade de inferência do SmolLM3-3B.

A Figura~\ref{fig:acuracia-n} mostra a acurácia ponderada em função de $N$ para os sete níveis e as quatro configurações. Sem conluio, as curvas permanecem próximas de 1 até 65\% e só recuam de modo visível em 80\%, de forma menos acentuada à medida que $N$ cresce. Com conluio, a acurácia colapsa a partir de 50\% e vai a zero em 65\% e 80\%. Instáveis no esquema 50--50 reduzem o tamanho do bloco malicioso e deslocam o colapso para percentuais nominais mais altos.

\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{groupplot}[
  group style={group size=2 by 2, horizontal sep=1.4cm, vertical sep=1.5cm,
    xlabels at=edge bottom, ylabels at=edge left},
  width=0.42\textwidth, height=3.7cm,
  ymin=0, ymax=1.05, xmin=5, xmax=50,
  xtick={5,20,35,50},
  ylabel={Acurácia ponderada},
  xlabel={$N$ (nós)},
  grid=major, grid style={dotted,gray!40},
  legend style={font=\tiny, draw=none, fill=none, legend columns=4,
    at={(0.5,1.18)}, anchor=south, /tikz/every even column/.append style={column sep=4pt}},
  mark size=1.1pt, line width=0.7pt]
\nextgroupplot[title={\small Sem conluio}]
  \addplot+[mark=*] coordinates {(5,0.9993) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addlegendentry{0\%}
  \addplot+[mark=*] coordinates {(5,0.9960) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addlegendentry{5\%}
  \addplot+[mark=*] coordinates {(5,0.9960) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addlegendentry{20\%}
  \addplot+[mark=*] coordinates {(5,0.9960) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addlegendentry{35\%}
  \addplot+[mark=*] coordinates {(5,0.9773) (10,0.9907) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addlegendentry{50\%}
  \addplot+[mark=*] coordinates {(5,0.7427) (10,0.9560) (15,0.9880) (20,0.9827) (25,0.9947) (30,0.9993) (35,1.0000) (40,0.9993) (45,1.0000) (50,1.0000)};
  \addlegendentry{65\%}
  \addplot+[mark=*] coordinates {(5,0.2367) (10,0.5040) (15,0.5553) (20,0.6120) (25,0.6927) (30,0.7160) (35,0.7833) (40,0.8273) (45,0.8627) (50,0.8820)};
  \addlegendentry{80\%}
\nextgroupplot[title={\small Com conluio}]
  \addplot+[mark=*, forget plot] coordinates {(5,0.9953) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.9953) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.9953) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.9947) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.9747) (10,0.6007) (15,0.7933) (20,0.3467) (25,0.6087) (30,0.2153) (35,0.4493) (40,0.1187) (45,0.2867) (50,0.0793)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.0000) (10,0.0000) (15,0.0000) (20,0.0000) (25,0.0000) (30,0.0000) (35,0.0000) (40,0.0000) (45,0.0000) (50,0.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.0000) (10,0.0000) (15,0.0000) (20,0.0000) (25,0.0000) (30,0.0000) (35,0.0000) (40,0.0000) (45,0.0000) (50,0.0000)};
\nextgroupplot[title={\small Sem + inst.}]
  \addplot+[mark=*, forget plot] coordinates {(5,0.9967) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.9987) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.9927) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.9933) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.9847) (10,0.9987) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.8700) (10,0.9967) (15,1.0000) (20,0.9993) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.4120) (10,0.7960) (15,0.8980) (20,0.9480) (25,0.9667) (30,0.9793) (35,0.9907) (40,0.9967) (45,0.9980) (50,0.9980)};
\nextgroupplot[title={\small Com + inst.}]
  \addplot+[mark=*, forget plot] coordinates {(5,0.9980) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,1.0000) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.9907) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.9907) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.9840) (10,0.9987) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.9033) (10,0.9973) (15,0.9940) (20,0.8633) (25,0.9727) (30,0.9007) (35,0.9880) (40,0.8400) (45,0.8007) (50,0.9227)};
  \addplot+[mark=*, forget plot] coordinates {(5,0.3920) (10,0.1500) (15,0.0247) (20,0.0140) (25,0.0073) (30,0.0107) (35,0.0047) (40,0.0027) (45,0.0040) (50,0.0013)};
\end{groupplot}
\end{tikzpicture}
\caption{Acurácia do consenso ponderado em função de $N$ (média de 30 sementes).}
\label{fig:acuracia-n}
\end{figure}

A Tabela~\ref{tab:n50-pond} concentra o recorte $N=50$, no qual 0\% corresponde a 0 maliciosos, 5\% a 2, 50\% a 25 e 80\% a 40 (truncamento inteiro). A Tabela~\ref{tab:n50-maj} traz a maioria simples nas mesmas células.

\begin{table}[htbp]
\centering
\caption{Acurácia do consenso ponderado em $N=50$ (média $\pm$ desvio, 30 sementes, 50 rodadas).}
\label{tab:n50-pond}
\footnotesize
\begin{tabular}{|l|c|c|c|c|}
\hline
\textbf{Nível} & \textbf{Sem conluio} & \textbf{Com conluio} & \textbf{Sem + inst.} & \textbf{Com + inst.} \\
\hline
0\%  & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ \\
5\%  & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ \\
20\% & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ \\
35\% & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ \\
50\% & $100{,}0\pm 0{,}0$ & $7{,}9\pm 3{,}7$   & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ \\
65\% & $100{,}0\pm 0{,}0$ & $0{,}0\pm 0{,}0$   & $100{,}0\pm 0{,}0$ & $92{,}3\pm 9{,}7$ \\
80\% & $88{,}2\pm 3{,}7$  & $0{,}0\pm 0{,}0$   & $99{,}8\pm 0{,}6$  & $0{,}1\pm 0{,}5$ \\
\hline
\end{tabular}
\end{table}

\begin{table}[htbp]
\centering
\caption{Acurácia da maioria simples em $N=50$ (média $\pm$ desvio, 30 sementes, 50 rodadas).}
\label{tab:n50-maj}
\footnotesize
\begin{tabular}{|l|c|c|c|c|}
\hline
\textbf{Nível} & \textbf{Sem conluio} & \textbf{Com conluio} & \textbf{Sem + inst.} & \textbf{Com + inst.} \\
\hline
0\%  & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ \\
5\%  & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ \\
20\% & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ \\
35\% & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ \\
50\% & $100{,}0\pm 0{,}0$ & $7{,}9\pm 3{,}7$   & $100{,}0\pm 0{,}0$ & $100{,}0\pm 0{,}0$ \\
65\% & $100{,}0\pm 0{,}0$ & $0{,}0\pm 0{,}0$   & $100{,}0\pm 0{,}0$ & $99{,}7\pm 0{,}8$ \\
80\% & $88{,}2\pm 3{,}7$  & $0{,}0\pm 0{,}0$   & $100{,}0\pm 0{,}0$ & $6{,}4\pm 3{,}6$ \\
\hline
\end{tabular}
\end{table}

Três observações seguem dos números, sem extrapolar para redes reais.

Primeiro, \textbf{sem conluio} os maliciosos geram valores incorretos distintos. Eles não formam um bloco e, até 65\% em $N=50$, ponderado e maioria coincidem em 100\%. Em 80\% (40 votos errados independentes e 10 honestos, incluído o orquestrador), ambos caem para $88{,}2\%\pm 3{,}7\%$. A reputação não se diferencia da maioria nesse regime, o que é esperado: não há um único valor falso a penalizar de forma coordenada.

Segundo, \textbf{com conluio} o bloco malicioso vota $999$. Em 50\% de $N=50$ há 25 nós coludidos e 25 honestos, incluído o orquestrador. Como cada honesto acerta com $p=0{,}9$ de forma independente, o bloco correto raramente se forma por completo: a probabilidade de os 25 acertarem na mesma rodada é $0{,}9^{25} \approx 7{,}2\%$, compatível com os $7{,}9\%\pm 3{,}7\%$ medidos. A acurácia observada não é, portanto, o resultado de um empate mal resolvido --- é essencialmente a frequência com que o bloco honesto consegue igualar o bloco coludido. No empate, a implementação escolhe a primeira resposta inserida no placar; como o \texttt{node-0} honesto responde primeiro, o gabarito vence quando todos os honestos acertam.

A regra de \textit{hold} não causa esse colapso; ela o contém. Com a fração de peso do vencedor em $0{,}50 < 0{,}55$, o \textit{hold} dispara nas rodadas desse cenário e congela as reputações, o que explica as curvas planas da Figura~\ref{fig:n50-p50-rep}. Sem ele, o sinal premiaria a concordância com um consenso já capturado.

O regime seguinte torna esse risco explícito. Em 65\%, o bloco coludido alcança 32 dos 50 votos, e a fração de peso do vencedor ($0{,}64$) ultrapassa o limiar de confiança. O \textit{hold} deixa de agir e a atualização se inverte: os nós maliciosos recebem $s=1$ por concordarem com o consenso ponderado, e os honestos recebem $s=0$ por divergirem dele. A reputação passa a premiar o ataque. Esse --- e não o cenário de 50\% --- é o modo de falha mais relevante do mecanismo atual, e delimita o que a Rodada de Validação precisaria corrigir. Esse resultado substitui a narrativa preliminar de 95\% versus 0\% obtida em outra grade (20 rodadas e uma semente). A Figura~\ref{fig:n50-panorama} resume os sete níveis em $N=50$.

\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{axis}[
  width=0.82\textwidth, height=4.6cm,
  ymin=0, ymax=1.05, xmin=0, xmax=80,
  xtick={0,5,20,35,50,65,80},
  xlabel={Percentual nominal de nós problemáticos (\%)},
  ylabel={Acurácia ponderada},
  grid=major, grid style={dotted,gray!40},
  legend style={font=\footnotesize, draw=none, fill=none, legend columns=2,
    at={(0.02,0.22)}, anchor=west},
  mark size=2pt, line width=0.9pt, error bars/y dir=both,
  error bars/y explicit, error bars/error bar style={line width=0.5pt}]
  \addplot+[mark=*] coordinates {(0,1.0000) +- (0,0.0000) (5,1.0000) +- (0,0.0000) (20,1.0000) +- (0,0.0000) (35,1.0000) +- (0,0.0000) (50,1.0000) +- (0,0.0000) (65,1.0000) +- (0,0.0000) (80,0.8820) +- (0,0.0373)};
  \addlegendentry{Sem conluio}
  \addplot+[mark=*] coordinates {(0,1.0000) +- (0,0.0000) (5,1.0000) +- (0,0.0000) (20,1.0000) +- (0,0.0000) (35,1.0000) +- (0,0.0000) (50,0.0793) +- (0,0.0369) (65,0.0000) +- (0,0.0000) (80,0.0000) +- (0,0.0000)};
  \addlegendentry{Com conluio}
  \addplot+[mark=*] coordinates {(0,1.0000) +- (0,0.0000) (5,1.0000) +- (0,0.0000) (20,1.0000) +- (0,0.0000) (35,1.0000) +- (0,0.0000) (50,1.0000) +- (0,0.0000) (65,1.0000) +- (0,0.0000) (80,0.9980) +- (0,0.0061)};
  \addlegendentry{Sem + inst.}
  \addplot+[mark=*] coordinates {(0,1.0000) +- (0,0.0000) (5,1.0000) +- (0,0.0000) (20,1.0000) +- (0,0.0000) (35,1.0000) +- (0,0.0000) (50,1.0000) +- (0,0.0000) (65,0.9227) +- (0,0.0971) (80,0.0013) +- (0,0.0051)};
  \addlegendentry{Com + inst.}
\end{axis}
\end{tikzpicture}
\caption{Acurácia ponderada em $N=50$ nos sete percentuais nominais (média $\pm$ desvio, 30 sementes).}
\label{fig:n50-panorama}
\end{figure}

\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{groupplot}[
  group style={group size=2 by 2, horizontal sep=1.3cm, vertical sep=1.4cm,
    xlabels at=edge bottom, ylabels at=edge left},
  width=0.42\textwidth, height=3.6cm,
  ymin=0, ymax=1.05, xmin=0, xmax=50,
  ylabel={Reputação média}, xlabel={Rodada},
  grid=major, grid style={dotted,gray!40},
  legend style={font=\tiny, draw=none, fill=none, legend columns=3,
    at={(0.5,1.16)}, anchor=south},
  mark size=1.0pt, line width=0.8pt]
\nextgroupplot[title={\small Sem conluio}]
  \addplot[solid, mark=o, color=blue!70!black] coordinates {(0,0.5000) (2,0.5000) (4,0.5000) (6,0.5000) (8,0.5000) (10,0.5000) (12,0.5000) (14,0.5000) (16,0.5000) (18,0.5000) (20,0.5000) (22,0.5000) (24,0.5000) (26,0.5000) (28,0.5000) (30,0.5000) (32,0.5000) (34,0.5000) (36,0.5000) (38,0.5000) (40,0.5000) (42,0.5000) (44,0.5000) (46,0.5000) (48,0.5000) (49,0.5000)};
  \addlegendentry{Honestos}
  \addplot[dashed, mark=square, color=red!70!black] coordinates {(0,0.5000) (2,0.5000) (4,0.5000) (6,0.5000) (8,0.5000) (10,0.5000) (12,0.5000) (14,0.5000) (16,0.5000) (18,0.5000) (20,0.5000) (22,0.5000) (24,0.5000) (26,0.5000) (28,0.5000) (30,0.5000) (32,0.5000) (34,0.5000) (36,0.5000) (38,0.5000) (40,0.5000) (42,0.5000) (44,0.5000) (46,0.5000) (48,0.5000) (49,0.5000)};
  \addlegendentry{Maliciosos}
\nextgroupplot[title={\small Com conluio}]
  \addplot[solid, mark=o, color=blue!70!black, forget plot] coordinates {(0,0.5000) (2,0.5000) (4,0.5000) (6,0.5000) (8,0.5000) (10,0.5000) (12,0.5000) (14,0.5000) (16,0.5000) (18,0.5000) (20,0.5000) (22,0.5000) (24,0.5000) (26,0.5000) (28,0.5000) (30,0.5000) (32,0.5000) (34,0.5000) (36,0.5000) (38,0.5000) (40,0.5000) (42,0.5000) (44,0.5000) (46,0.5000) (48,0.5000) (49,0.5000)};
  \addplot[dashed, mark=square, color=red!70!black, forget plot] coordinates {(0,0.5000) (2,0.5000) (4,0.5000) (6,0.5000) (8,0.5000) (10,0.5000) (12,0.5000) (14,0.5000) (16,0.5000) (18,0.5000) (20,0.5000) (22,0.5000) (24,0.5000) (26,0.5000) (28,0.5000) (30,0.5000) (32,0.5000) (34,0.5000) (36,0.5000) (38,0.5000) (40,0.5000) (42,0.5000) (44,0.5000) (46,0.5000) (48,0.5000) (49,0.5000)};
  \node[font=\tiny, align=center, fill=white, fill opacity=0.85, inner sep=1pt]    at (axis cs:38,0.52) {Empate / hold};
\nextgroupplot[title={\small Sem + inst.}]
  \addplot[solid, mark=o, color=blue!70!black, forget plot] coordinates {(0,0.5778) (2,0.7095) (4,0.7935) (6,0.8409) (8,0.8613) (10,0.8803) (12,0.8909) (14,0.8961) (16,0.8973) (18,0.8938) (20,0.8984) (22,0.8959) (24,0.8938) (26,0.9044) (28,0.9039) (30,0.9019) (32,0.9051) (34,0.9045) (36,0.9032) (38,0.8966) (40,0.8996) (42,0.9002) (44,0.9028) (46,0.8937) (48,0.8899) (49,0.8951)};
  \addplot[dashed, mark=square, color=red!70!black, forget plot] coordinates {(0,0.4042) (2,0.2401) (4,0.1351) (6,0.0759) (8,0.0427) (10,0.0240) (12,0.0135) (14,0.0076) (16,0.0043) (18,0.0024) (20,0.0014) (22,0.0008) (24,0.0004) (26,0.0002) (28,0.0001) (30,0.0001) (32,0.0000) (34,0.0000) (36,0.0000) (38,0.0000) (40,0.0000) (42,0.0000) (44,0.0000) (46,0.0000) (48,0.0000) (49,0.0000)};
  \addplot[dotted, mark=triangle, color=orange!80!black, forget plot] coordinates {(0,0.4639) (2,0.4185) (4,0.3960) (6,0.3714) (8,0.3596) (10,0.3623) (12,0.3573) (14,0.3583) (16,0.3531) (18,0.3444) (20,0.3472) (22,0.3557) (24,0.3549) (26,0.3584) (28,0.3530) (30,0.3489) (32,0.3554) (34,0.3371) (36,0.3400) (38,0.3310) (40,0.3530) (42,0.3566) (44,0.3481) (46,0.3439) (48,0.3426) (49,0.3375)};
\nextgroupplot[title={\small Com + inst.}]
  \addplot[solid, mark=o, color=blue!70!black, forget plot] coordinates {(0,0.5720) (2,0.7077) (4,0.7942) (6,0.8396) (8,0.8696) (10,0.8766) (12,0.8846) (14,0.8944) (16,0.8942) (18,0.8941) (20,0.8992) (22,0.8992) (24,0.9022) (26,0.9056) (28,0.9016) (30,0.9018) (32,0.9012) (34,0.8999) (36,0.8969) (38,0.8961) (40,0.8945) (42,0.8966) (44,0.9000) (46,0.8999) (48,0.9029) (49,0.9045)};
  \addplot[dashed, mark=square, color=red!70!black, forget plot] coordinates {(0,0.4167) (2,0.2445) (4,0.1376) (6,0.0774) (8,0.0435) (10,0.0245) (12,0.0138) (14,0.0078) (16,0.0044) (18,0.0024) (20,0.0014) (22,0.0008) (24,0.0004) (26,0.0002) (28,0.0001) (30,0.0001) (32,0.0000) (34,0.0000) (36,0.0000) (38,0.0000) (40,0.0000) (42,0.0000) (44,0.0000) (46,0.0000) (48,0.0000) (49,0.0000)};
  \addplot[dotted, mark=triangle, color=orange!80!black, forget plot] coordinates {(0,0.4663) (2,0.4128) (4,0.4034) (6,0.3880) (8,0.3783) (10,0.3788) (12,0.3655) (14,0.3697) (16,0.3748) (18,0.3622) (20,0.3438) (22,0.3488) (24,0.3542) (26,0.3589) (28,0.3509) (30,0.3611) (32,0.3587) (34,0.3577) (36,0.3607) (38,0.3461) (40,0.3589) (42,0.3536) (44,0.3566) (46,0.3582) (48,0.3643) (49,0.3739)};
\end{groupplot}
\end{tikzpicture}
\caption{Reputação média por perfil em $N=50$ e 50\% de nós problemáticos.}
\label{fig:n50-p50-rep}
\end{figure}

Terceiro, o \textbf{split 50--50 com instáveis} dilui o conluio. Em 50\% nominal, apenas metade dos problemáticos cola no valor $999$, e ambos os agregadores permanecem em 100\%. Em 65\% com conluio e instáveis, a maioria ($99{,}7\%\pm 0{,}8\%$) supera o ponderado ($92{,}3\%\pm 9{,}7\%$): a reputação, nesse recorte, não é superior. Em 80\% com conluio e instáveis os dois colapsam (ponderado $0{,}1\%\pm 0{,}5\%$; maioria $6{,}4\%\pm 3{,}6\%$). A Figura~\ref{fig:n50-p80} compara os agregadores nesse extremo.

\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{axis}[
  ybar, bar width=9pt,
  width=0.82\textwidth, height=4.5cm,
  ymin=0, ymax=1.15,
  ylabel={Acurácia},
  symbolic x coords={Sem conluio, Com conluio, Sem + inst., Com + inst.},
  xtick=data, x tick label style={font=\small},
  enlarge x limits=0.18,
  grid=major, grid style={dotted,gray!40},
  legend style={font=\footnotesize, draw=none, fill=none, at={(0.5,0.98)},
    anchor=north, legend columns=2},
  nodes near coords, nodes near coords style={font=\tiny, /pgf/number format/fixed,
    /pgf/number format/precision=2}]
  \addplot coordinates {({Sem conluio},0.8820) ({Com conluio},0.0000) ({Sem + inst.},0.9980) ({Com + inst.},0.0013)};
  \addlegendentry{Ponderado}
  \addplot coordinates {({Sem conluio},0.8820) ({Com conluio},0.0000) ({Sem + inst.},1.0000) ({Com + inst.},0.0640)};
  \addlegendentry{Maioria}
\end{axis}
\end{tikzpicture}
\caption{Acurácia ponderada e por maioria em $N=50$ e 80\% nominal, nas quatro configurações (30 sementes).}
\label{fig:n50-p80}
\end{figure}

A escala $N$ também importa no pior caso sem conluio. Em 80\%, a acurácia ponderada média vai de $23{,}7\%\pm 18{,}2\%$ em $N=5$ para $88{,}2\%\pm 3{,}7\%$ em $N=50$: redes maiores diluem erros independentes. Com conluio a 80\%, a acurácia é $0\%$ já a partir de $N=5$. A Figura~\ref{fig:acuracia-conluio} isola essa configuração.

\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{axis}[
  width=0.82\textwidth, height=4.6cm,
  ymin=0, ymax=1.05, xmin=5, xmax=50,
  xtick={5,10,15,20,25,30,35,40,45,50},
  xlabel={$N$ (nós, orquestrador incluído)},
  ylabel={Acurácia ponderada},
  grid=major, grid style={dotted,gray!40},
  legend style={font=\footnotesize, draw=none, fill=none, legend columns=4,
    at={(0.5,1.05)}, anchor=south},
  mark size=1.4pt, line width=0.8pt]
  \addplot+[mark=*] coordinates {(5,0.9953) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addlegendentry{0\%}
  \addplot+[mark=*] coordinates {(5,0.9953) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addlegendentry{5\%}
  \addplot+[mark=*] coordinates {(5,0.9953) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addlegendentry{20\%}
  \addplot+[mark=*] coordinates {(5,0.9947) (10,1.0000) (15,1.0000) (20,1.0000) (25,1.0000) (30,1.0000) (35,1.0000) (40,1.0000) (45,1.0000) (50,1.0000)};
  \addlegendentry{35\%}
  \addplot+[mark=*] coordinates {(5,0.9747) (10,0.6007) (15,0.7933) (20,0.3467) (25,0.6087) (30,0.2153) (35,0.4493) (40,0.1187) (45,0.2867) (50,0.0793)};
  \addlegendentry{50\%}
  \addplot+[mark=*] coordinates {(5,0.0000) (10,0.0000) (15,0.0000) (20,0.0000) (25,0.0000) (30,0.0000) (35,0.0000) (40,0.0000) (45,0.0000) (50,0.0000)};
  \addlegendentry{65\%}
  \addplot+[mark=*] coordinates {(5,0.0000) (10,0.0000) (15,0.0000) (20,0.0000) (25,0.0000) (30,0.0000) (35,0.0000) (40,0.0000) (45,0.0000) (50,0.0000)};
  \addlegendentry{80\%}
\end{axis}
\end{tikzpicture}
\caption{Acurácia ponderada versus $N$ na configuração com conluio (sem instáveis).}
\label{fig:acuracia-conluio}
\end{figure}

Em síntese, a reputação sem oráculo \textbf{não} recupera o consenso quando um bloco coludido iguala ou supera os honestos sob pesos iniciais iguais. Ela também não piora o caso sem conluio, no qual a maioria já é suficiente. Qualquer afirmação de ``detecção de maliciosos'' ou de superioridade geral seria incompatível com estas tabelas.

% -----------------------------------------------------------
% SEÇÃO 6 - CONCLUSÃO
% -----------------------------------------------------------
\section{Conclusão}
\label{sec:conclusao}

Este TCC implementou e avaliou um simulador de inferência redundante com orquestrador central, dois agregadores e reputação por concordância observada. A pergunta de pesquisa permanece em aberto como hipótese contextual: a reputação ajuda em alguns desenhos de ataque e falha em outros. Em conluio de 50\%, o limitante é estatístico --- o bloco honesto raramente se forma por completo, e a regra de \textit{hold} apenas impede que o empate seja gravado como verdade da rede. Acima do limiar de confiança, o problema muda de natureza: a própria regra de atualização passa a premiar o bloco atacante.

Limitações já enumeradas na Seção~\ref{sec:metodos} restringem o alcance das afirmações. Trabalho futuro, ainda não medido nesta grade, inclui: (i) integrar a Rodada de Validação ao protocolo por amostragem probabilística ou periódica, com tarefas reservadas; (ii) executar o modo com uma instância lógica do SmolLM3-3B em escala compatível com o hardware; (iii) estudar desempates, reputação inicial assimétrica e um sinal capaz de identificar conluio; (iv) avaliar isolamento temporário, recuperação e recomendação ponderada entre pares; (v) testar outras topologias de rede, além da estrela com orquestrador fixo; (vi) avaliar um orquestrador dinâmico, eliminando o ponto único de confiança do desenho atual; (vii) reexecutar cenários em que $N$ conte apenas nós de inferência, deixando o orquestrador fora da população; (viii) conduzir análise de sensibilidade de $\alpha$; e (ix) avaliar similaridade semântica apenas em tarefas não numéricas. Centralidade estrutural não é priorizada porque a estrela fixa não diferencia os participantes de inferência.

\begin{thebibliography}{Coulouris et al. 2021}

\bibitem[Blockchain-based AI 2024]{blockchainAI2024}
Blockchain-based distributed AI models: Trust in AI model sharing (2024). \textit{International Journal of Science and Research Archive}.

\bibitem[Bonawitz et al. 2019]{bonawitz2019}
Bonawitz, K. et al. (2019). Towards federated learning at scale: System design. In \textit{Proceedings of Machine Learning and Systems}.

\bibitem[Bouhata et al. 2025]{bouhata2025}
Bouhata, D., Moumen, H., Mazari, J. A., and Bounceur, A. (2025). Byzantine fault tolerance in distributed machine learning: a survey. \textit{Journal of Experimental \& Theoretical Artificial Intelligence}, 37(8):1331--1389. Publicado online em 2024. DOI: \url{https://doi.org/10.1080/0952813X.2024.2391778}.

\bibitem[Burns et al. 2022]{burns2022}
Burns, B., Beda, J., and Hightower, K. (2022). \textit{Kubernetes: Up and Running}. O'Reilly Media, Sebastopol, 3 edition.

\bibitem[Castro and Liskov 1999]{castro1999}
Castro, M. and Liskov, B. (1999). Practical Byzantine fault tolerance. In \textit{Proceedings of the Third Symposium on Operating Systems Design and Implementation (OSDI)}, pages 173--186, New Orleans. USENIX Association.

\bibitem[Chen et al. 2024]{chen2024}
Chen, W., Jia, L., Zhou, Y., and Ren, Q. (2024). Reputation-driven asynchronous federated learning for enhanced trajectory prediction with blockchain. \textit{arXiv preprint arXiv:2407.19428}.

\bibitem[Cobbe et al. 2021]{cobbe2021}
Cobbe, K., Kosaraju, V., Bavarian, M., et al. (2021). Training verifiers to solve math word problems. \textit{arXiv preprint arXiv:2110.14168}.

\bibitem[Coulouris et al. 2021]{coulouris2021}
Coulouris, G., Dollimore, J., Kindberg, T., and Blair, G. (2021). \textit{Distributed Systems: Concepts and Design}. Pearson, Boston, 6 edition.

\bibitem[Docker Inc. 2026]{docker2026}
Docker Inc. (2026). \textit{Docker Documentation}. Disponível em: \url{https://docs.docker.com}. Acesso em: 03 jun. 2026.

\bibitem[Kairouz et al. 2021]{kairouz2021}
Kairouz, P. et al. (2021). Advances and open problems in federated learning. \textit{Foundations and Trends in Machine Learning}, 14(1--2):1--210.

\bibitem[Kamvar et al. 2003]{kamvar2003}
Kamvar, S., Schlosser, M., and Garcia-Molina, H. (2003). The EigenTrust algorithm for reputation management in P2P networks. In \textit{Proceedings of the 12th International Conference on World Wide Web}.

\bibitem[Lamport et al. 1982]{lamport1982}
Lamport, L., Shostak, R., and Pease, M. (1982). The Byzantine generals problem. \textit{ACM Transactions on Programming Languages and Systems}, 4(3):382--401.

\bibitem[McMahan et al. 2017]{mcmahan2017}
McMahan, B. et al. (2017). Communication-efficient learning of deep networks from decentralized data. In \textit{Proceedings of the 20th International Conference on Artificial Intelligence and Statistics (AISTATS)}.

\bibitem[Russell and Norvig 2020]{russell2020}
Russell, S. and Norvig, P. (2020). \textit{Artificial Intelligence: A Modern Approach}. Pearson, Hoboken, 4 edition.

\bibitem[Shi et al. 2016]{shi2016}
Shi, W., Cao, J., Zhang, Q., Li, Y., and Xu, L. (2016). Edge computing: Vision and challenges. \textit{IEEE Internet of Things Journal}, 3(5):637--646.

\bibitem[Tanenbaum and van Steen 2017]{tanenbaum2017}
Tanenbaum, A. S. and van Steen, M. (2017). \textit{Distributed Systems}. Maarten van Steen, Amsterdam, 3 edition.

\bibitem[Wang et al. 2025]{wang2025}
Wang, B. et al. (2025). A decentralized asynchronous federated learning framework for edge devices. \textit{Future Generation Computer Systems}.

\bibitem[Wei and Liu 2025]{wei2025}
Wei, W. and Liu, L. (2025). Trustworthy distributed AI systems: Robustness, privacy, and governance. \textit{ACM Computing Surveys}, 57(6), Article 144, pages 1--42. DOI: \url{https://doi.org/10.1145/3645102}.

\bibitem[Wu et al. 2024]{wu2024}
Wu, H., Yue, C., Fan, Y., Li, Y., Flynn, D., and Zhang, L. (2024). Half a century of distributed Byzantine fault-tolerant consensus: Design principles and evolutionary pathways. \textit{arXiv preprint arXiv:2407.19863}.

\end{thebibliography}
\end{document}
