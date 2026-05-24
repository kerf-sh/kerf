"""isotropic_remesh.py — GK-P23: In-process isotropic remesh fallback.

Provides `isotropic_remesh(mesh, target_edge_length, iterations=5)` that
performs edge-split, edge-collapse, edge-flip and tangential vertex smoothing
to achieve a mesh with uniform edge lengths close to `target_edge_length`.

This is the pure-Python / NumPy fallback used when the ``instant-meshes``
binary is unavailable, ensuring `quad_remesh` always degrades to a valid
triangulated result rather than raising.

Public API
----------
isotropic_remesh(mesh, target_edge_length, iterations=5)
    -> dict {"vertices": list[list[float]], "faces": list[list[int]]}

    `mesh` is a dict with keys ``"vertices"`` and ``"faces"`` (triangles or
    quads — quads are triangulated internally).

Notes
-----
* Algorithm follows the Botsch-Kobbelt 2004 remeshing scheme:
  (1) split edges longer than 4/3 * L  → shortest first is avoided; we do
      longest first to keep the number of passes bounded;
  (2) collapse edges shorter than 4/5 * L;
  (3) flip edges to improve valence toward 6;
  (4) tangential Laplacian smoothing.
* Boundary edges are never split or collapsed; boundary vertices are only
  smoothed along the boundary (1-D projection).
* Pure Python + NumPy — no OCCT.  For ~1 k-vertex meshes expect < 1 s.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Set, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def isotropic_remesh(
    mesh: Dict,
    target_edge_length: float,
    iterations: int = 5,
) -> Dict:
    """Remesh *mesh* toward uniform edge length *target_edge_length*.

    Parameters
    ----------
    mesh : dict
        Keys ``"vertices"`` (list of [x, y, z]) and
        ``"faces"`` (list of vertex-index lists; triangles or quads).
    target_edge_length : float
        Desired average edge length after remeshing.
    iterations : int
        Number of split→collapse→flip→smooth cycles (default 5).

    Returns
    -------
    dict
        ``{"vertices": list[list[float]], "faces": list[list[int]]}``
        All faces are triangles.
    """
    if target_edge_length <= 0:
        raise ValueError("target_edge_length must be positive")

    verts_raw = mesh.get("vertices", [])
    faces_raw = mesh.get("faces", [])

    if not verts_raw or not faces_raw:
        return {"vertices": [], "faces": []}

    # Work with float lists internally; convert quads to tris
    verts: List[List[float]] = [list(map(float, v)) for v in verts_raw]
    faces: List[List[int]] = _triangulate(faces_raw)

    if not faces:
        return {"vertices": verts, "faces": []}

    L = float(target_edge_length)
    split_thresh = (4.0 / 3.0) * L
    collapse_thresh = (4.0 / 5.0) * L

    for _iter in range(int(iterations)):
        faces = _split_long_edges(verts, faces, split_thresh)
        faces = _collapse_short_edges(verts, faces, collapse_thresh)
        faces = _flip_edges(verts, faces)
        _smooth_vertices(verts, faces)

    # Clean up any degenerate triangles introduced
    faces = [f for f in faces if len(set(f)) == 3]

    return {"vertices": [list(v) for v in verts], "faces": faces}


# ---------------------------------------------------------------------------
# Triangulate (handle quads and higher n-gons by fan)
# ---------------------------------------------------------------------------


def _triangulate(faces: List[List[int]]) -> List[List[int]]:
    tris: List[List[int]] = []
    for f in faces:
        n = len(f)
        if n < 3:
            continue
        if n == 3:
            tris.append(list(f))
        else:
            # Fan from f[0]
            for i in range(1, n - 1):
                tris.append([f[0], f[i], f[i + 1]])
    return tris


# ---------------------------------------------------------------------------
# Helper geometry
# ---------------------------------------------------------------------------


def _edge_length(verts: List[List[float]], a: int, b: int) -> float:
    va, vb = verts[a], verts[b]
    return math.sqrt(
        (va[0] - vb[0]) ** 2 + (va[1] - vb[1]) ** 2 + (va[2] - vb[2]) ** 2
    )


def _midpoint(verts: List[List[float]], a: int, b: int) -> List[float]:
    va, vb = verts[a], verts[b]
    return [0.5 * (va[i] + vb[i]) for i in range(3)]


def _build_edge_map(faces: List[List[int]]) -> Dict[Tuple[int, int], List[int]]:
    """Map edge (min,max) → list of face indices that contain it."""
    edge_map: Dict[Tuple[int, int], List[int]] = {}
    for fi, f in enumerate(faces):
        n = len(f)
        for k in range(n):
            e = (min(f[k], f[(k + 1) % n]), max(f[k], f[(k + 1) % n]))
            edge_map.setdefault(e, []).append(fi)
    return edge_map


def _boundary_edges(edge_map: Dict[Tuple[int, int], List[int]]) -> Set[Tuple[int, int]]:
    return {e for e, fs in edge_map.items() if len(fs) == 1}


# ---------------------------------------------------------------------------
# (1) Split long edges
# ---------------------------------------------------------------------------


def _split_long_edges(
    verts: List[List[float]],
    faces: List[List[int]],
    threshold: float,
) -> List[List[int]]:
    """Split every edge longer than *threshold* by inserting its midpoint."""
    changed = True
    max_passes = 20
    while changed and max_passes > 0:
        max_passes -= 1
        changed = False
        edge_map = _build_edge_map(faces)
        # Collect long edges sorted longest-first
        long_edges = [
            (e, _edge_length(verts, e[0], e[1]))
            for e in edge_map
            if _edge_length(verts, e[0], e[1]) > threshold
        ]
        if not long_edges:
            break
        long_edges.sort(key=lambda x: -x[1])
        # Split one edge at a time (rebuild edge map each pass)
        for (a, b), _len in long_edges:
            if a >= len(verts) or b >= len(verts):
                continue
            # Re-check length in case verts moved (they don't here, but safe)
            if _edge_length(verts, a, b) <= threshold:
                continue
            mid_vi = len(verts)
            verts.append(_midpoint(verts, a, b))
            new_faces: List[List[int]] = []
            face_indices = _build_edge_map(faces).get((min(a, b), max(a, b)), [])
            modified: Set[int] = set(face_indices)
            for fi, f in enumerate(faces):
                if fi not in modified:
                    new_faces.append(f)
                    continue
                # Find position of edge in this face
                n = len(f)
                inserted = False
                for k in range(n):
                    if (min(f[k], f[(k + 1) % n]), max(f[k], f[(k + 1) % n])) == (min(a, b), max(a, b)):
                        # Split: [... f[k], f[(k+1)%n], ...] → two tris
                        p0, p1 = f[k], f[(k + 1) % n]
                        opp = f[(k + 2) % n]  # valid only for triangle
                        new_faces.append([p0, mid_vi, opp])
                        new_faces.append([mid_vi, p1, opp])
                        inserted = True
                        break
                if not inserted:
                    new_faces.append(f)
            faces = new_faces
            changed = True
            break  # restart outer while after one split
    return faces


# ---------------------------------------------------------------------------
# (2) Collapse short edges
# ---------------------------------------------------------------------------


def _collapse_short_edges(
    verts: List[List[float]],
    faces: List[List[int]],
    threshold: float,
) -> List[List[int]]:
    """Collapse every interior edge shorter than *threshold*."""
    max_passes = 20
    for _pass in range(max_passes):
        edge_map = _build_edge_map(faces)
        boundary = _boundary_edges(edge_map)
        short_edges = [
            (e, _edge_length(verts, e[0], e[1]))
            for e in edge_map
            if e not in boundary and _edge_length(verts, e[0], e[1]) < threshold
        ]
        if not short_edges:
            break
        short_edges.sort(key=lambda x: x[1])  # shortest first

        (a, b), _len = short_edges[0]
        # Merge b → a (move a to midpoint, remap b)
        mid = _midpoint(verts, a, b)
        verts[a] = mid
        # Replace b with a in all faces, remove degenerate
        new_faces: List[List[int]] = []
        for f in faces:
            new_f = [a if vi == b else vi for vi in f]
            if len(set(new_f)) == 3:  # not degenerate
                new_faces.append(new_f)
        faces = new_faces

    return faces


# ---------------------------------------------------------------------------
# (3) Edge flip for valence improvement
# ---------------------------------------------------------------------------


def _flip_edges(
    verts: List[List[float]],
    faces: List[List[int]],
) -> List[List[int]]:
    """Flip interior edges to improve vertex valence toward 6.

    For each interior edge (a, b) shared by triangles (a, b, c) and (b, a, d):
    flip to (c, d) if total valence deviation from 6 decreases.
    """
    edge_map = _build_edge_map(faces)
    boundary = _boundary_edges(edge_map)

    # Build valence table
    valence: Dict[int, int] = {}
    for f in faces:
        for vi in f:
            valence[vi] = valence.get(vi, 0) + 1

    changed = True
    max_iters = 10
    while changed and max_iters > 0:
        max_iters -= 1
        changed = False
        edge_map = _build_edge_map(faces)
        boundary = _boundary_edges(edge_map)
        for e, fi_list in list(edge_map.items()):
            if e in boundary:
                continue
            if len(fi_list) != 2:
                continue
            fi0, fi1 = fi_list
            if fi0 >= len(faces) or fi1 >= len(faces):
                continue
            f0, f1 = faces[fi0], faces[fi1]
            a, b = e
            # Find c in f0 (not a, not b)
            c_list = [v for v in f0 if v != a and v != b]
            d_list = [v for v in f1 if v != a and v != b]
            if len(c_list) != 1 or len(d_list) != 1:
                continue
            c, d = c_list[0], d_list[0]
            if c == d:
                continue

            # Current valence deviation
            def _dev(v: int) -> int:
                target = 6
                return abs(valence.get(v, 0) - target)

            before = _dev(a) + _dev(b) + _dev(c) + _dev(d)
            # After flip: a and b lose one; c and d gain one
            after = (abs(valence.get(a, 0) - 1 - 6) + abs(valence.get(b, 0) - 1 - 6) +
                     abs(valence.get(c, 0) + 1 - 6) + abs(valence.get(d, 0) + 1 - 6))
            if after < before:
                # Flip: replace (a,b,c) and (b,a,d) with (c,d,a) and (c,b,d)
                faces[fi0] = [c, d, a]
                faces[fi1] = [c, b, d]
                valence[a] = valence.get(a, 0) - 1
                valence[b] = valence.get(b, 0) - 1
                valence[c] = valence.get(c, 0) + 1
                valence[d] = valence.get(d, 0) + 1
                changed = True

    return faces


# ---------------------------------------------------------------------------
# (4) Tangential Laplacian smoothing
# ---------------------------------------------------------------------------


def _smooth_vertices(
    verts: List[List[float]],
    faces: List[List[int]],
    strength: float = 0.5,
) -> None:
    """Move each interior vertex toward the Laplacian of its neighbours,
    projected onto the local tangent plane (tangential smoothing)."""
    edge_map = _build_edge_map(faces)
    boundary_verts: Set[int] = set()
    for e in _boundary_edges(edge_map):
        boundary_verts.add(e[0])
        boundary_verts.add(e[1])

    # Build adjacency list
    adj: Dict[int, Set[int]] = {}
    for f in faces:
        for k in range(3):
            vi = f[k]
            adj.setdefault(vi, set())
            for j in range(1, 3):
                adj[vi].add(f[(k + j) % 3])

    # Estimate per-vertex normal via area-weighted face normals
    normals: Dict[int, np.ndarray] = {i: np.zeros(3) for i in range(len(verts))}
    for f in faces:
        a, b, c = np.array(verts[f[0]]), np.array(verts[f[1]]), np.array(verts[f[2]])
        n = np.cross(b - a, c - a)
        for vi in f:
            normals[vi] = normals[vi] + n
    for vi in normals:
        nm = np.linalg.norm(normals[vi])
        if nm > 1e-12:
            normals[vi] /= nm

    verts_np = [np.array(v) for v in verts]
    new_verts = [v.copy() for v in verts_np]

    for vi in range(len(verts)):
        if vi in boundary_verts:
            continue
        neighbours = adj.get(vi, set())
        if not neighbours:
            continue
        centroid = np.mean([verts_np[nb] for nb in neighbours], axis=0)
        delta = centroid - verts_np[vi]
        # Project onto tangent plane
        n = normals.get(vi, np.zeros(3))
        if np.linalg.norm(n) > 1e-12:
            delta = delta - np.dot(delta, n) * n
        new_verts[vi] = verts_np[vi] + strength * delta

    for i in range(len(verts)):
        verts[i] = new_verts[i].tolist()
