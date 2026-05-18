"""
kerf_1dsim.causality
====================

DAE causalisation and Block Lower-Triangular (BLT) decomposition.

Given a list of equations (as callables ``f_i(t, x, dx) -> float``) and a
variable index assignment, this module:

1. Builds an incidence matrix (which variables appear in which equation).
2. Runs Dulmage–Mendelsohn-style matching to assign a *lead variable* to each
   equation (structural causality assignment).
3. Applies Tarjan's SCC algorithm to find the Block Lower Triangular (BLT)
   ordering so that, in the absence of algebraic loops, the system can be
   solved one block at a time.

The result is a ``CausalSystem`` describing the sorted equation/variable order
and which blocks contain genuine algebraic loops (size > 1 SCCs).

Public API
----------
    causalise(equations, var_names, incidence) -> CausalSystem

where ``incidence[i]`` is the set of variable indices that appear in equation i.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Block:
    """One block in the BLT ordering."""
    eq_indices: list[int]   # original equation indices
    var_indices: list[int]  # matched variable indices (same length)
    is_loop: bool = False   # True if algebraic loop (size > 1)


@dataclass
class CausalSystem:
    """Result of BLT causalisation."""
    blocks: list[Block]
    eq_order: list[int]    # flattened equation permutation
    var_order: list[int]   # flattened variable permutation
    matching: dict[int, int]  # eq_index -> var_index


# ---------------------------------------------------------------------------
# Matching (maximum bipartite matching via augmenting paths)
# ---------------------------------------------------------------------------

def _maximum_matching(
    n_eq: int,
    n_var: int,
    incidence: list[set[int]],
) -> dict[int, int]:
    """
    Return a maximum matching: eq_index -> var_index.
    Uses Hopcroft-Karp (simplified DFS variant — O(V*E) suffices for
    small systems).
    """
    match_eq: dict[int, int] = {}   # eq -> var
    match_var: dict[int, int] = {}  # var -> eq

    def _try_augment(eq: int, visited: set[int]) -> bool:
        for var in incidence[eq]:
            if var in visited:
                continue
            visited.add(var)
            if var not in match_var or _try_augment(match_var[var], visited):
                match_eq[eq] = var
                match_var[var] = eq
                return True
        return False

    for eq in range(n_eq):
        _try_augment(eq, set())

    return match_eq


# ---------------------------------------------------------------------------
# Tarjan SCC on the directed equation graph
# ---------------------------------------------------------------------------

def _tarjan_scc(
    n: int,
    adj: list[list[int]],   # directed adjacency: node -> [successors]
) -> list[list[int]]:
    """
    Tarjan's algorithm for strongly connected components.
    Returns list of SCCs in reverse topological order (ready for BLT).
    """
    index_counter = [0]
    stack: list[int] = []
    lowlink: dict[int, int] = {}
    index: dict[int, int] = {}
    on_stack: set[int] = set()
    sccs: list[list[int]] = []

    def _strongconnect(v: int):
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)

        for w in adj[v]:
            if w not in index:
                _strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            scc: list[int] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                scc.append(w)
                if w == v:
                    break
            sccs.append(scc)

    for v in range(n):
        if v not in index:
            _strongconnect(v)

    return sccs


# ---------------------------------------------------------------------------
# Public: causalise
# ---------------------------------------------------------------------------

def causalise(
    n_eq: int,
    n_var: int,
    incidence: list[set[int]],
) -> CausalSystem:
    """
    Perform structural BLT decomposition.

    Parameters
    ----------
    n_eq : int
        Number of equations.
    n_var : int
        Number of variables (>= n_eq for well-determined system).
    incidence : list[set[int]]
        incidence[i] = set of variable indices that appear in equation i.

    Returns
    -------
    CausalSystem
        BLT blocks in dependency order (block 0 can be solved first).
    """
    matching = _maximum_matching(n_eq, n_var, incidence)

    # Build directed graph on equations:
    #   eq_i -> eq_j  if eq_j's matched variable appears in eq_i
    #   (i.e. eq_i depends on eq_j's output)
    var_to_eq: dict[int, int] = {v: e for e, v in matching.items()}

    adj: list[list[int]] = [[] for _ in range(n_eq)]
    for eq_i in range(n_eq):
        for var in incidence[eq_i]:
            # If this var is the output of another equation, add edge
            if var in var_to_eq and var_to_eq[var] != eq_i:
                adj[eq_i].append(var_to_eq[var])

    sccs = _tarjan_scc(n_eq, adj)
    # Tarjan returns SCCs in reverse topological order; reverse to get
    # forward evaluation order.
    sccs_forward = list(reversed(sccs))

    blocks: list[Block] = []
    eq_order: list[int] = []
    var_order: list[int] = []

    for scc in sccs_forward:
        eq_indices = scc
        var_indices = [matching.get(e, -1) for e in eq_indices]
        is_loop = len(scc) > 1
        blocks.append(Block(eq_indices=eq_indices, var_indices=var_indices, is_loop=is_loop))
        eq_order.extend(eq_indices)
        var_order.extend(var_indices)

    return CausalSystem(
        blocks=blocks,
        eq_order=eq_order,
        var_order=var_order,
        matching=matching,
    )
