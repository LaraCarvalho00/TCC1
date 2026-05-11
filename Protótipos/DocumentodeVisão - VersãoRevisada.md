# Documento de Visão — Versão Revisada

## Sistema de Simulação de Rede Distribuída para Inferência de IA com Avaliação de Confiabilidade Baseada em Reputação

**Autores:** Allan Mateus Arruda de Souza e Lara Andrade Carvalho  
**Data:** 10 de março de 2026

Proposta apresentada ao curso de Engenharia de Software da **PUC Minas** como projeto de Trabalho de Conclusão de Curso (TCC).

**Orientações:**
* **Conteúdo:** Professor Leonardo Vilela Cardoso
* **Académica:** Professor Danilo Maia

---

## 1. Problema de Pesquisa

Em ambientes distribuídos de inferência de Inteligência Artificial, múltiplos nós independentes processam uma mesma tarefa e retornam resultados que podem divergir entre si. Essa divergência pode ocorrer por falhas de execução, instabilidade de ambiente, heterogeneidade de configuração ou comportamento malicioso deliberado.

Na ausência de um mecanismo central de confiança, surge um problema clássico de sistemas distribuídos: **como agregar respostas potencialmente conflitantes e ainda produzir um resultado confiável**.

O problema investigado neste trabalho é:
> **Em que medida mecanismos de reputação podem reduzir a influência de nós maliciosos e aumentar a confiabilidade do resultado agregado em uma rede distribuída de inferência de IA?**

---

## 2. Relevância

O crescimento de arquiteturas distribuídas, *edge computing*, *fog computing* e ambientes colaborativos amplia a necessidade de mecanismos que permitam coordenar múltiplos participantes sem depender de infraestrutura centralizada. Sistemas distribuídos enfrentam desafios como:

* Ausência de autoridade central de validação;
* Heterogeneidade de comportamento entre participantes;
* Presença de respostas incorretas, inconsistentes ou adversariais;
* Necessidade de agregação robusta de resultados.

Este projeto avalia experimentalmente como mecanismos leves de reputação contribuem para a confiabilidade, reduzindo a influência de participantes maliciosos sem depender de blockchain ou protocolos pesados de consenso.

---

## 3. Objetivos

### Objetivo Geral
Analisar experimentalmente o impacto de mecanismos de reputação na confiabilidade de redes distribuídas de inferência de IA, considerando cenários com nós honestos, instáveis e maliciosos.

### Objetivos Específicos
* Construir um ambiente de simulação distribuída utilizando **containers Docker**.
* Implementar múltiplos nós independentes capazes de processar tarefas de inferência.
* Definir diferentes perfis de comportamento dos nós.
* Implementar mecanismo de consenso baseado em reputação.
* Medir o impacto de nós maliciosos na qualidade do resultado agregado.
* Comparar cenários com e sem reputação.
* Coletar métricas quantitativas de desempenho e confiabilidade.

---

## 4. Especificação da Rede Distribuída

O sistema será caracterizado por:
* **Isolamento:** Múltiplos nós executados em containers independentes.
* **Paralelismo:** Execução paralela de tarefas de inferência.
* **Assincronismo:** Coleta assíncrona de respostas pelo coordenador.
* **Dinamismo:** Atualização de reputação baseada no histórico de comportamento.

*Nota: O foco é simular experimentalmente propriedades de coordenação e consenso, e não construir uma rede P2P de produção.*

---

## 5. Metodologia

A pesquisa adota uma abordagem **experimental quantitativa**, utilizando **Python** e **Docker**.

### Variáveis Independentes
* **Número de nós:** 5, 10 e 20.
* **Proporção de nós maliciosos:** 0%, 25% e 50%.
* **Política de atualização de reputação.**

### Variáveis Dependentes
* Acurácia do resultado agregado.
* Taxa de consenso correto.
* Tempo médio de processamento.
* Estabilidade da reputação ao longo das execuções.

---

## 6. Fluxo Metodológico

```mermaid
graph TD
    A[Inicialização do cenário] --> B[Criação dos containers]
    B --> C[Definição dos perfis dos nós]
    C --> D[Geração e Distribuição da tarefa]
    D --> E[Execução local em cada nó]
    E --> F[Retorno e Agregação das respostas]
    F --> G[Aplicação do consenso]
    G --> H[Comparação com resultado esperado]
    H --> I[Atualização de reputação e Registro de métricas]
    I --> J{Nova rodada?}
    J -- Sim --> D
    J -- Não --> K[Fim do Experimento]