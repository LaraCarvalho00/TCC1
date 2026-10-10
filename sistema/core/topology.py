"""Topologia lógica da rede: quem fala com quem.

Dois tipos de grafo:

* ``star``     : estrela com centro rotativo. Qualquer líder fala direto com
                 todos os nós (grafo completo), como o orquestrador fixo de hoje,
                 mas o papel de centro muda de nó a cada rodada.
* ``kregular`` : grafo aleatório k-regular. Cada nó conhece só ``degree``
                 vizinhos; a mensagem chega aos demais por repasse.

O grafo é gerado de forma determinística a partir do identificador de execução
(``seed``), para que a simulação local e os containers usem as mesmas arestas.

O k-regular parte de um anel em que cada nó liga a ``degree/2`` vizinhos de cada
lado (conexo por construção) e embaralha as arestas com trocas duplas, que
preservam o grau. Uma troca só é aceita se o grafo continuar conexo.
"""
from __future__ import annotations

import random
from collections import deque
from typing import Iterable, Optional

Graph = dict[str, list[str]]

KINDS = ("star", "kregular")


def node_sort_key(node_id: str) -> tuple:
    """Ordena ``node-2`` antes de ``node-10`` (parte numérica como inteiro)."""
    prefix, _, suffix = node_id.rpartition("-")
    if suffix.isdigit():
        return (prefix, int(suffix))
    return (node_id, -1)


def build_graph(
    node_ids: Iterable[str],
    kind: str = "star",
    degree: int = 4,
    seed: int = 0,
) -> Graph:
    """Constrói a lista de adjacência para os nós informados."""
    ids = sorted(node_ids, key=node_sort_key)
    if kind not in KINDS:
        raise ValueError(f"kind deve ser um de {KINDS!r}.")
    n = len(ids)
    if n <= 1:
        return {nid: [] for nid in ids}

    if kind == "star" or degree >= n - 1:
        return {nid: [other for other in ids if other != nid] for nid in ids}

    if degree < 2:
        raise ValueError("degree deve ser >= 2 para manter o grafo conexo.")
    # Grafo k-regular exige n*k par; com n ímpar e k ímpar, usa k+1.
    k = degree if (n * degree) % 2 == 0 else degree + 1
    if k >= n - 1:
        return {nid: [other for other in ids if other != nid] for nid in ids}

    rng = random.Random(f"topology:{seed}:{n}:{k}")
    edges = _ring_lattice(n, k)
    edges = _randomize(edges, n, rng, swaps=10 * len(edges))

    adjacency: dict[int, set[int]] = {i: set() for i in range(n)}
    for a, b in edges:
        adjacency[a].add(b)
        adjacency[b].add(a)
    return {
        ids[i]: sorted((ids[j] for j in adjacency[i]), key=node_sort_key)
        for i in range(n)
    }


def distances(graph: Graph, source: str, allowed: Optional[set[str]] = None) -> dict[str, int]:
    """Distância em saltos de ``source`` até cada nó alcançável (BFS).

    ``allowed`` restringe a busca a um subconjunto de nós (por exemplo, os
    membros de uma mesma cópia da cadeia depois de uma divisão).
    """
    if allowed is not None and source not in allowed:
        return {}
    dist = {source: 0}
    queue = deque([source])
    while queue:
        current = queue.popleft()
        for neighbor in graph.get(current, []):
            if neighbor in dist or (allowed is not None and neighbor not in allowed):
                continue
            dist[neighbor] = dist[current] + 1
            queue.append(neighbor)
    return dist


def spanning_tree(graph: Graph, root: str, allowed: Optional[set[str]] = None) -> dict[str, Optional[str]]:
    """Árvore de difusão a partir de ``root``: mapa ``nó -> pai`` (raiz -> None).

    A tarefa desce por essa árvore e as respostas sobem pelo mesmo caminho.
    """
    parent: dict[str, Optional[str]] = {root: None}
    queue = deque([root])
    while queue:
        current = queue.popleft()
        for neighbor in graph.get(current, []):
            if neighbor in parent or (allowed is not None and neighbor not in allowed):
                continue
            parent[neighbor] = current
            queue.append(neighbor)
    return parent


def diameter(graph: Graph) -> int:
    """Maior distância entre dois nós (grafo desconexo devolve -1)."""
    best = 0
    for node in graph:
        dist = distances(graph, node)
        if len(dist) < len(graph):
            return -1
        best = max(best, max(dist.values()))
    return best


def max_degree(graph: Graph) -> int:
    return max((len(neighbors) for neighbors in graph.values()), default=0)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _ring_lattice(n: int, k: int) -> set[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()
    half = k // 2
    for i in range(n):
        for step in range(1, half + 1):
            edges.add(_edge(i, (i + step) % n))
    if k % 2 == 1:
        # k ímpar só ocorre com n par: liga cada nó ao oposto do anel.
        for i in range(n // 2):
            edges.add(_edge(i, i + n // 2))
    return edges


def _randomize(edges: set[tuple[int, int]], n: int, rng: random.Random, swaps: int) -> set[tuple[int, int]]:
    edge_list = sorted(edges)
    edge_set = set(edge_list)
    for _ in range(swaps):
        i, j = rng.sample(range(len(edge_list)), 2)
        a, b = edge_list[i]
        c, d = edge_list[j]
        if rng.random() < 0.5:
            c, d = d, c
        new_1, new_2 = _edge(a, d), _edge(c, b)
        if a == d or c == b or new_1 == new_2 or new_1 in edge_set or new_2 in edge_set:
            continue
        candidate = set(edge_set)
        candidate.discard(edge_list[i])
        candidate.discard(edge_list[j])
        candidate.add(new_1)
        candidate.add(new_2)
        if not _connected(candidate, n):
            continue
        edge_set = candidate
        edge_list[i] = new_1
        edge_list[j] = new_2
    return edge_set


def _connected(edges: set[tuple[int, int]], n: int) -> bool:
    adjacency: dict[int, list[int]] = {i: [] for i in range(n)}
    for a, b in edges:
        adjacency[a].append(b)
        adjacency[b].append(a)
    seen = {0}
    queue = deque([0])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency[current]:
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return len(seen) == n


def _edge(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)
