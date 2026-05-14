"""Topological sort for plugin dependency ordering.

Usage::

    from kerf_core.utils.topo_sort import topo_sort

    order = topo_sort(
        nodes=["kerf-fem", "kerf-core", "kerf-api"],
        edges={
            "kerf-fem": ["kerf-api"],
            "kerf-api": ["kerf-core"],
        },
    )
    # order == ["kerf-core", "kerf-api", "kerf-fem"]
"""
from __future__ import annotations

from collections import defaultdict, deque


def topo_sort(nodes: list[str], edges: dict[str, list[str]]) -> list[str]:
    """Kahn's algorithm topological sort. Dependencies appear before dependants."""
    dep_of: dict[str, set[str]] = defaultdict(set)
    in_degree: dict[str, int] = {n: 0 for n in nodes}

    for node in nodes:
        for dep in edges.get(node, []):
            if dep not in in_degree:
                in_degree[dep] = 0
            dep_of[dep].add(node)
            in_degree[node] += 1

    queue: deque[str] = deque(n for n, d in in_degree.items() if d == 0)
    result: list[str] = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for dependant in dep_of.get(node, set()):
            in_degree[dependant] -= 1
            if in_degree[dependant] == 0:
                queue.append(dependant)

    if len(result) != len(in_degree):
        cycle_nodes = [n for n, d in in_degree.items() if d > 0]
        raise ValueError(f"Plugin dependency cycle detected among: {cycle_nodes}")

    return result
