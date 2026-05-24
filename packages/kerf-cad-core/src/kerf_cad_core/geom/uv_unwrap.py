"""uv_unwrap.py — GK-P24: LSCM UV unwrap for mesh→SubD pipelines.

Implements Least-Squares Conformal Mapping (Lévy et al. 2002) as a
pure-Python + NumPy/SciPy solver.  Produces a low-distortion UV
parametrization for triangle meshes and SubD cages.

Public API
----------
lscm_unwrap(mesh, fixed_pins=None) -> dict
    Compute a UV parametrization for *mesh*.

    Parameters
    ----------
    mesh : dict
        ``"vertices"`` (list of [x, y, z]) and ``"faces"`` (triangles only).
    fixed_pins : list of (vertex_index, u, v), optional
        At least two non-coincident pins are required for a unique solution.
        If omitted, two boundary vertices are pinned automatically.

    Returns
    -------
    dict
        ``{"uv": list[list[float]]}`` — one [u, v] per vertex in mesh order.
        Vertices not reachable from the main connected component get uv=[0,0].

Notes
-----
* LSCM minimises angle distortion (conformal energy), making it well-suited
  for SubD cage UV sets where shape-preserving maps reduce texture swim.
* Implemented via the sparse linear system  A·x = b  where x = [U; V]
  (stacked real/imaginary parts of the complex parameterization).
* SciPy sparse least-squares (``scipy.sparse.linalg.lsqr``) is used; if
  SciPy is unavailable a dense NumPy fallback is used instead.
* Pure Python + NumPy (+ optional SciPy).  No OCCT.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def lscm_unwrap(
    mesh: Dict,
    fixed_pins: Optional[List[Tuple[int, float, float]]] = None,
) -> Dict:
    """LSCM UV unwrap.

    Parameters
    ----------
    mesh : dict
        ``"vertices"`` (list[list[float]]) + ``"faces"`` (list[list[int]],
        triangles only).
    fixed_pins : list of (vertex_index, u, v), optional
        At least 2 pins required; if omitted, 2 boundary pins chosen
        automatically.

    Returns
    -------
    dict
        ``{"uv": list[list[float]]}`` — one [u, v] per vertex.
    """
    verts_raw = mesh.get("vertices", [])
    faces_raw = mesh.get("faces", [])

    if not verts_raw or not faces_raw:
        return {"uv": []}

    # Validate / convert
    verts = [list(map(float, v)) for v in verts_raw]
    n_verts = len(verts)
    faces: List[List[int]] = []
    for f in faces_raw:
        if len(f) == 3:
            faces.append([int(f[0]), int(f[1]), int(f[2])])
        # silently skip non-triangles

    if not faces:
        return {"uv": [[0.0, 0.0]] * n_verts}

    # Determine fixed pins
    pins = _resolve_pins(verts, faces, n_verts, fixed_pins)
    if len(pins) < 2:
        # Degenerate — return zero UVs
        return {"uv": [[0.0, 0.0]] * n_verts}

    uv = _solve_lscm(verts, faces, n_verts, pins)
    return {"uv": uv}


# ---------------------------------------------------------------------------
# Pin resolution
# ---------------------------------------------------------------------------


def _boundary_edges(faces: List[List[int]]) -> Dict[Tuple[int, int], List[int]]:
    edge_count: Dict[Tuple[int, int], int] = {}
    for f in faces:
        for k in range(3):
            e = (min(f[k], f[(k + 1) % 3]), max(f[k], f[(k + 1) % 3]))
            edge_count[e] = edge_count.get(e, 0) + 1
    return {e for e, c in edge_count.items() if c == 1}


def _resolve_pins(
    verts: List[List[float]],
    faces: List[List[int]],
    n_verts: int,
    fixed_pins: Optional[List[Tuple[int, float, float]]],
) -> List[Tuple[int, float, float]]:
    if fixed_pins and len(fixed_pins) >= 2:
        # Validate indices
        valid = [(vi, u, v) for vi, u, v in fixed_pins if 0 <= vi < n_verts]
        if len(valid) >= 2:
            return valid[:2]

    # Auto-select two boundary vertices as far apart as possible
    bdry = _boundary_edges(faces)
    if not bdry:
        # Closed mesh — use two arbitrary vertices
        if n_verts >= 2:
            return [(0, 0.0, 0.0), (1, 1.0, 0.0)]
        return []

    bdry_verts: List[int] = list({v for e in bdry for v in e})
    if len(bdry_verts) < 2:
        return [(bdry_verts[0], 0.0, 0.0), (0, 1.0, 0.0)]

    # Pick the two farthest apart boundary vertices
    best_dist, best_pair = -1.0, (bdry_verts[0], bdry_verts[1])
    for i in range(min(len(bdry_verts), 20)):  # O(n²) but capped
        for j in range(i + 1, min(len(bdry_verts), 20)):
            a, b = bdry_verts[i], bdry_verts[j]
            va, vb = verts[a], verts[b]
            d = math.sqrt(sum((va[k] - vb[k]) ** 2 for k in range(3)))
            if d > best_dist:
                best_dist, best_pair = d, (a, b)

    a, b = best_pair
    return [(a, 0.0, 0.0), (b, 1.0, 0.0)]


# ---------------------------------------------------------------------------
# LSCM system assembly
# ---------------------------------------------------------------------------


def _triangle_local_frame(
    p0: List[float], p1: List[float], p2: List[float]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute 2-D coordinates of a triangle's vertices in the triangle's plane.

    Returns (q0, q1, q2) as 2-D numpy arrays.  q0 is always at the origin.
    """
    e1 = np.array(p1) - np.array(p0)
    e2 = np.array(p2) - np.array(p0)
    # Gram-Schmidt for 2-D local axes
    len_e1 = np.linalg.norm(e1)
    if len_e1 < 1e-12:
        return np.zeros(2), np.zeros(2), np.zeros(2)
    x_axis = e1 / len_e1
    n = np.cross(e1, e2)
    n_len = np.linalg.norm(n)
    if n_len < 1e-12:
        return np.zeros(2), np.zeros(2), np.zeros(2)
    n /= n_len
    y_axis = np.cross(n, x_axis)
    q0 = np.array([0.0, 0.0])
    q1 = np.array([np.dot(e1, x_axis), np.dot(e1, y_axis)])
    q2 = np.array([np.dot(e2, x_axis), np.dot(e2, y_axis)])
    return q0, q1, q2


def _solve_lscm(
    verts: List[List[float]],
    faces: List[List[int]],
    n_verts: int,
    pins: List[Tuple[int, float, float]],
) -> List[List[float]]:
    """Build and solve the LSCM least-squares system.

    The unknown vector is x = [U_0, …, U_{n-1}, V_0, …, V_{n-1}] for free
    vertices.  Pinned vertices are moved to the right-hand side.

    We use the complex formulation:  for each triangle, the conformal energy
    contributes 2 rows to the system (real and imaginary parts of the
    Cauchy-Riemann constraint).
    """
    # Identify free / fixed vertex sets
    pin_dict: Dict[int, Tuple[float, float]] = {vi: (u, v) for vi, u, v in pins}
    free_verts: List[int] = [i for i in range(n_verts) if i not in pin_dict]
    n_free = len(free_verts)
    free_index: Dict[int, int] = {vi: k for k, vi in enumerate(free_verts)}

    if n_free == 0:
        uv = [[0.0, 0.0]] * n_verts
        for vi, (u, v) in pin_dict.items():
            uv[vi] = [u, v]
        return uv

    # Build sparse-ish system as lists of (row, col, val)
    # x layout: x[:n_free] = U values, x[n_free:] = V values
    n_unknowns = 2 * n_free
    n_rows = 2 * len(faces)

    rows_A: List[int] = []
    cols_A: List[int] = []
    vals_A: List[float] = []
    b = np.zeros(n_rows)

    for row_base, f in enumerate(faces):
        i0, i1, i2 = f
        q0, q1, q2 = _triangle_local_frame(verts[i0], verts[i1], verts[i2])

        # Area (needed for weighting; use absolute 2-D area)
        area2 = abs((q1[0] - q0[0]) * (q2[1] - q0[1]) - (q2[0] - q0[0]) * (q1[1] - q0[1]))
        if area2 < 1e-12:
            continue  # degenerate triangle

        # LSCM coefficient derivation (Lévy 2002 eq. 17):
        # W_r = (q2 - q0) complex coefficients, W_i = (q1 - q0)
        # Conformal constraint: sum_k coeff_k * z_k = 0
        # where z_k = u_k + i*v_k
        # Coefficients per vertex:
        # c0 = (q2 - q1) = (q2[0]-q1[0]) + i*(q2[1]-q1[1])
        # c1 = (q0 - q2)
        # c2 = (q1 - q0)
        c = [
            (q2[0] - q1[0], q2[1] - q1[1]),
            (q0[0] - q2[0], q0[1] - q2[1]),
            (q1[0] - q0[0], q1[1] - q0[1]),
        ]

        row_re = 2 * row_base
        row_im = 2 * row_base + 1

        for local_k, vi in enumerate(f):
            cr, ci = c[local_k]
            # Real part: cr * U - ci * V
            # Imag part: ci * U + cr * V
            if vi in free_index:
                k = free_index[vi]
                # U column
                rows_A.append(row_re); cols_A.append(k);          vals_A.append(cr)
                rows_A.append(row_im); cols_A.append(k);          vals_A.append(ci)
                # V column
                rows_A.append(row_re); cols_A.append(n_free + k); vals_A.append(-ci)
                rows_A.append(row_im); cols_A.append(n_free + k); vals_A.append(cr)
            else:
                # Pinned: move to RHS
                u_pin, v_pin = pin_dict[vi]
                b[row_re] -= cr * u_pin - ci * v_pin
                b[row_im] -= ci * u_pin + cr * v_pin

    if not rows_A:
        # All triangles degenerate
        uv = [[0.0, 0.0]] * n_verts
        for vi, (u, v) in pin_dict.items():
            uv[vi] = [u, v]
        return uv

    # Build matrix and solve via least squares
    A_dense = np.zeros((n_rows, n_unknowns))
    for r, c_idx, v in zip(rows_A, cols_A, vals_A):
        A_dense[r, c_idx] += v

    try:
        from scipy.sparse import csr_matrix
        from scipy.sparse.linalg import lsqr as sp_lsqr
        A_sp = csr_matrix(A_dense)
        sol = sp_lsqr(A_sp, b)[0]
    except ImportError:
        # NumPy dense fallback
        sol, _, _, _ = np.linalg.lstsq(A_dense, b, rcond=None)

    U_free = sol[:n_free]
    V_free = sol[n_free:]

    uv: List[List[float]] = [[0.0, 0.0]] * n_verts
    for k, vi in enumerate(free_verts):
        uv[vi] = [float(U_free[k]), float(V_free[k])]
    for vi, (u, v) in pin_dict.items():
        uv[vi] = [float(u), float(v)]
    return uv
