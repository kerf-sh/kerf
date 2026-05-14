"""
Assembly mate chain-walk for tolerance stack-up.

Given an assembly document and two feature references (start + end),
this module walks the mate graph via BFS to find the shortest path between
them and builds a dimension chain for use with `tolerance_stack`.

Mate type contributions:
  - distance: nominal = mate value; plus/minus from mate tolerance slot
  - angle:    nominal = mate value; plus/minus from mate tolerance slot
  - coincident/concentric/parallel/perpendicular/tangent:
              nominal = 0; plus/minus = 0 (unless mate has tolerance slot)

The `.assembly` mate schema gains an optional backward-compatible field:

  "tolerance": {"plus": <float>, "minus": <float>}

If the slot is absent, plus=minus=0 is assumed.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# A feature reference uniquely identifies a feature on a component.
# Canonical form: {"component_id": str, "feature_id": str}
FeatureRef = dict[str, str]

# A chain entry in the same format accepted by tolerance_stack / worst_case.
ChainEntry = dict[str, Any]


# ---------------------------------------------------------------------------
# Zero-contribution mate types (positional constraints that carry no
# dimensional value unless the mate itself has a tolerance slot).
# ---------------------------------------------------------------------------
_ZERO_CONTRIBUTION_TYPES = frozenset({
    "coincident",
    "concentric",
    "parallel",
    "perpendicular",
    "tangent",
})


def _mate_contribution(mate: dict) -> ChainEntry:
    """Return the dimensional contribution of a single mate as a chain entry."""
    mate_type = mate.get("type", "")
    value = mate.get("value", 0.0) or 0.0

    # Per-mate tolerance slot (optional, backward-compatible)
    tol = mate.get("tolerance") or {}
    plus = float(tol.get("plus", 0.0) or 0.0)
    minus = float(tol.get("minus", 0.0) or 0.0)

    # Legacy flat fields (solver.py uses these)
    if not plus:
        plus = float(mate.get("tolerance_plus", 0.0) or 0.0)
    if not minus:
        minus = float(mate.get("tolerance_minus", 0.0) or 0.0)

    if mate_type in _ZERO_CONTRIBUTION_TYPES:
        nominal = 0.0
    else:
        # distance or angle — carry their value
        nominal = float(value)

    unit = mate.get("unit", "mm") or "mm"

    return {
        "name": f"mate:{mate.get('id', mate_type)}",
        "nominal": nominal,
        "plus": plus,
        "minus": minus,
        "unit": unit,
        "source": "mate",
        "mate_id": mate.get("id", ""),
        "mate_type": mate_type,
    }


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _build_graph(mates: list[dict]) -> dict[str, list[tuple[str, dict | None]]]:
    """
    Build an undirected adjacency graph keyed by "component_id::feature_id".

    Two kinds of edges:
    1. **Mate edges** (mate != None): across component boundaries, from
       (compA, featA) to (compB, featB).  Carry the mate dict for dimensional
       contribution.
    2. **Intra-component edges** (mate == None): zero-cost edges connecting
       every pair of features that belong to the same component.  These allow
       the BFS to move from the feature where one mate arrives to the feature
       where the next mate departs — both on the same component.

    Returns: {node_key: [(neighbour_key, mate_or_None), ...]}
    """
    graph: dict[str, list[tuple[str, dict | None]]] = {}

    def _key(ref: dict) -> str:
        return f"{ref['component_id']}::{ref['feature_id']}"

    def _add_edge(a: str, b: str, mate) -> None:
        graph.setdefault(a, []).append((b, mate))
        graph.setdefault(b, []).append((a, mate))

    # Collect all node keys per component so we can add intra-component edges
    comp_features: dict[str, set[str]] = {}

    for mate in mates:
        ref_a = mate.get("a")
        ref_b = mate.get("b")
        if not ref_a or not ref_b:
            continue
        if not ref_a.get("component_id") or not ref_a.get("feature_id"):
            continue
        if not ref_b.get("component_id") or not ref_b.get("feature_id"):
            continue
        key_a = _key(ref_a)
        key_b = _key(ref_b)
        _add_edge(key_a, key_b, mate)

        comp_a = ref_a["component_id"]
        comp_b = ref_b["component_id"]
        comp_features.setdefault(comp_a, set()).add(key_a)
        comp_features.setdefault(comp_b, set()).add(key_b)

    # Intra-component zero-cost edges
    for _comp_id, feature_keys in comp_features.items():
        keys = list(feature_keys)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                _add_edge(keys[i], keys[j], None)

    return graph


def _bfs_path(
    graph: dict[str, list[tuple[str, dict | None]]],
    start: str,
    end: str,
) -> list[tuple[str, dict | None]] | None:
    """
    BFS from start to end in the mate graph.

    Each edge is (neighbour_key, mate_or_None).  Intra-component edges carry
    mate=None (zero dimensional contribution).

    Returns a list of (node_key, mate_or_None) tuples representing the path
    edges, or None if no path exists.
    """
    if start == end:
        return []

    visited = {start}
    # Queue entries: (current_node, path_so_far)
    queue: deque[tuple[str, list[tuple[str, dict | None]]]] = deque()
    queue.append((start, []))

    while queue:
        current, path = queue.popleft()
        for neighbour, mate in graph.get(current, []):
            if neighbour in visited:
                continue
            new_path = path + [(neighbour, mate)]
            if neighbour == end:
                return new_path
            visited.add(neighbour)
            queue.append((neighbour, new_path))

    return None


# ---------------------------------------------------------------------------
# Part dimension lookup (optional callback)
# ---------------------------------------------------------------------------

def _default_fetch_part_dim(component_id: str, feature_id: str) -> ChainEntry | None:
    """Default no-op: returns None (no part-level dimension contributed)."""
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_chain_from_assembly(
    assembly_doc: dict,
    start_ref: FeatureRef,
    end_ref: FeatureRef,
    *,
    fetch_part_dim: Callable[[str, str], ChainEntry | None] | None = None,
) -> list[ChainEntry] | dict:
    """
    Walk the assembly mate graph and build a tolerance chain.

    Parameters
    ----------
    assembly_doc:
        Parsed JSON of an `.assembly` file (must contain ``"mates"`` list).
    start_ref:
        {"component_id": str, "feature_id": str} — start of the chain.
    end_ref:
        {"component_id": str, "feature_id": str} — end of the chain.
    fetch_part_dim:
        Optional callback(component_id, feature_id) -> ChainEntry | None.
        When provided, called for each *node* crossed; if it returns a dict
        that dict is inserted into the chain before the outgoing mate edge.
        Keeps the pure helper test-friendly (no DB in tests).

    Returns
    -------
    list[ChainEntry]
        Chain ready for ``tolerance_stack`` — each entry has
        ``{name, nominal, plus, minus, unit}``.

    dict
        ``{"error": str, "code": str}`` when no path exists or inputs are
        invalid.
    """
    if fetch_part_dim is None:
        fetch_part_dim = _default_fetch_part_dim

    # Validate refs
    for label, ref in (("start_ref", start_ref), ("end_ref", end_ref)):
        if not isinstance(ref, dict):
            return {"error": f"{label} must be a dict", "code": "BAD_REF"}
        if not ref.get("component_id") or not ref.get("feature_id"):
            return {"error": f"{label} must have component_id and feature_id", "code": "BAD_REF"}

    mates = assembly_doc.get("mates")
    if not isinstance(mates, list):
        mates = []

    graph = _build_graph(mates)

    start_key = f"{start_ref['component_id']}::{start_ref['feature_id']}"
    end_key = f"{end_ref['component_id']}::{end_ref['feature_id']}"

    if start_key == end_key:
        return []

    # If start node doesn't appear in any mate, it won't be in the graph
    if start_key not in graph and end_key not in graph:
        return {"error": "neither start nor end feature found in any mate", "code": "NO_PATH"}
    if start_key not in graph:
        return {"error": "start feature not found in any mate", "code": "NO_PATH"}
    if end_key not in graph:
        return {"error": "end feature not found in any mate", "code": "NO_PATH"}

    path = _bfs_path(graph, start_key, end_key)

    if path is None:
        return {"error": "no mate path found between start and end", "code": "NO_PATH"}

    # Build chain from path edges
    chain: list[ChainEntry] = []

    # Optional part dim at the start node
    start_part_dim = fetch_part_dim(
        start_ref["component_id"], start_ref["feature_id"]
    )
    if start_part_dim is not None:
        chain.append(start_part_dim)

    # Walk path: each step is (reached_node_key, via_mate_or_None)
    for node_key, mate in path:
        if mate is not None:
            # Mate edge: dimensional contribution
            entry = _mate_contribution(mate)
            chain.append(entry)

            # Optional part dim at reached node (only when crossing component
            # boundary via a real mate — intra-component hops don't add dims)
            comp_id, feat_id = node_key.split("::", 1)
            part_dim = fetch_part_dim(comp_id, feat_id)
            if part_dim is not None:
                chain.append(part_dim)
        # else: intra-component zero-cost hop — no contribution, no callback

    return chain
