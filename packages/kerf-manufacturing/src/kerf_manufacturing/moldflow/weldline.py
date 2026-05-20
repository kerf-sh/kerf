"""Weld-line prediction from a completed fill-time map.

Theory
------
A weld line (also: knit line, meld line) forms where two separate flow
fronts meet.  In the Hele-Shaw mid-plane framework the simplest sufficient
condition is:

    Two *different* flow streams arrive at a node from opposite sides
    (convergence angle θ > θ_weld, typically 120–135°).

We identify weld-line *nodes* during the fill-front advancement (see
hele_shaw.py) and then extract the shared *edges* of those nodes to form
line segments that can be rendered or post-processed.

v1 Algorithm
------------
1.  During fill, each node records its *arrival direction* — the
    normalised vector from the gate projected onto the surface (stored as
    a 2D direction per node in the fill solver).
2.  After fill, we walk every internal edge (i, j).  If the fill-time
    difference across the edge is below a tolerance AND the dot-product of
    the arrival vectors at i and j is below -cos(θ_weld) the edge is
    classified as a weld-line edge.
3.  Connected weld-line edges are returned as a list of (node_i, node_j)
    pairs.

Out of scope (v2):
  * Meld-line vs weld-line distinction (flow angle < 45° vs > 135°)
  * Temperature at meeting-front — needed for weld-line strength
  * Fibre orientation disruption at weld line

References
----------
S. Trochu et al., "Mold filling in resin transfer molding", 1993.
A. Couniot & R. Keunings, "FEM simulation of injection moulding", 1992.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np


def predict_weld_lines(
    nodes: np.ndarray,               # (N, 2) or (N, 3) node coordinates
    triangles: np.ndarray,            # (T, 3) int triangle connectivity
    fill_time: np.ndarray,            # (N,) float, inf = unfilled
    arrival_dirs: np.ndarray | None,  # (N, 2) unit vectors; None → derive from coords
    gate_node: int,
    *,
    time_tol_fraction: float = 0.05,  # edges filled within 5 % of total fill time
    weld_angle_deg: float = 120.0,    # meeting angle threshold (°)
) -> list[tuple[int, int]]:
    """Return list of (node_i, node_j) edges that carry a weld line.

    Parameters
    ----------
    nodes : (N, 2|3) array of node positions.
    triangles : (T, 3) connectivity array (0-indexed).
    fill_time : (N,) per-node fill time. ``inf`` means the node was never
        reached (short-shot node).
    arrival_dirs : (N, 2) unit arrival-direction vectors, or ``None``.
        When ``None``, the vector from gate to node is used as a proxy.
    gate_node : index of the gate node (single gate v1).
    time_tol_fraction : two nodes are "simultaneously filled" if their
        fill-time difference is ≤ ``time_tol_fraction * max_fill_time``.
    weld_angle_deg : minimum meeting angle (degrees) to classify as a weld.

    Returns
    -------
    list of (int, int) edge tuples.
    """
    filled = np.isfinite(fill_time)
    if not filled.any():
        return []

    max_t = float(fill_time[filled].max())
    tol = time_tol_fraction * max_t

    cos_threshold = -math.cos(math.radians(weld_angle_deg))

    # Derive arrival directions if not provided: gate → node
    if arrival_dirs is None:
        gate_pos = nodes[gate_node, :2]
        vecs = nodes[:, :2] - gate_pos
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.where(norms < 1e-12, 1.0, norms)
        arrival_dirs = vecs / norms

    # Build edge set from triangles (unique edges only)
    edges: set[tuple[int, int]] = set()
    for tri in triangles:
        a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
        for u, v in ((a, b), (b, c), (c, a)):
            edges.add((min(u, v), max(u, v)))

    weld_edges: list[tuple[int, int]] = []
    for i, j in edges:
        # Both nodes must be filled
        if not (filled[i] and filled[j]):
            continue
        # Fill times must be close (simultaneous front meeting)
        if abs(fill_time[i] - fill_time[j]) > tol:
            continue
        # Arrival directions must be nearly opposing
        d_i = arrival_dirs[i]
        d_j = arrival_dirs[j]
        dot = float(d_i @ d_j)
        if dot <= cos_threshold:
            weld_edges.append((i, j))

    return weld_edges


def weld_line_segments(
    nodes: np.ndarray,
    weld_edges: list[tuple[int, int]],
) -> list[tuple[tuple[float, ...], tuple[float, ...]]]:
    """Convert weld-line edge indices to coordinate pairs.

    Returns a list of ``((x0, y0[, z0]), (x1, y1[, z1]))`` tuples.
    """
    return [
        (tuple(map(float, nodes[i])), tuple(map(float, nodes[j])))
        for i, j in weld_edges
    ]
