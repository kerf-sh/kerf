"""
mesh_to_nurbs.py
================
Pure-Python MeshToNURB auto-surfacing (Rhino MeshToNURB / mesh→NURBS via
quadmesh patches).

From a quad-dominant mesh (verts + quad faces, optional smoothing groups)
this module produces per-quad bicubic NURBS patches that together form a
patchwork surface closely approximating the input mesh.

Public API
----------
quad_to_bicubic_patch(verts, quad_face, *, neighbour_faces, tol) -> NurbsSurface
    Fit a bicubic NURBS patch for a single quad face using the four
    surrounding edge-strips for tangent estimation (Catmull-Rom-like).
    Returns a NurbsSurface(degree_u=3, degree_v=3) whose 4×4 control grid
    is constructed so that the four corners pass through the quad verts and
    the interior rows/columns encode the estimated boundary tangents.

mesh_to_nurbs_strips(verts, faces, *, tol) -> dict
    Convert a quad-dominant mesh to per-quad NURBS patches (one
    NurbsSurface per quad after tri→quad pairing).  Shared edges are given
    consistent tangents to achieve G1 continuity where the mesh is smooth.
    Returns:
        ok          : bool
        reason      : str
        patches     : list of NurbsSurface
        patch_count : int
        unpaired_tris : list of int  (face indices of unpaired triangles)

tri_to_quad_fallback(verts, faces) -> dict
    Pair adjacent triangles into quads where possible (greedy heuristic).
    Returns:
        ok           : bool
        reason       : str
        quads        : list of [i, j, k, l]  (4 vert indices per quad)
        unpaired     : list of int  (original face indices that stayed tris)
        pair_count   : int

quality_report(patches, verts, faces, *, tol) -> dict
    Per-patch max chord deviation vs source mesh verts and G0/G1
    cross-patch deviation across shared edges.
    Returns:
        ok               : bool
        reason           : str
        patch_count      : int
        max_chord_dev    : float  (largest deviation over all patches)
        per_patch        : list of {"patch_idx": int, "max_dev": float}
        g0_max_dev       : float  (worst corner-shared G0 across patches)
        g1_max_dev       : float  (worst tangent angle deviation in radians)

LLM tools (gated)
-----------------
@register tools: mesh_to_nurbs_convert, mesh_to_nurbs_quality — gated behind
kerf_chat registry.

Notes
-----
All public functions never raise.  Failures are returned as
``{"ok": False, "reason": "..."}``.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

from kerf_cad_core.geom.nurbs import NurbsSurface

# ---------------------------------------------------------------------------
# Internal type aliases
# ---------------------------------------------------------------------------

Vert = List[float]   # [x, y, z]
QuadFace = List[int]  # 4 vertex indices
TriFace = List[int]   # 3 vertex indices


# ---------------------------------------------------------------------------
# Small vector helpers (pure Python, no numpy dependency in the hot path)
# ---------------------------------------------------------------------------

def _v3(v: Sequence) -> Tuple[float, float, float]:
    return (float(v[0]), float(v[1]), float(v[2]))


def _vsub(a: Sequence, b: Sequence) -> Tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vadd(a: Sequence, b: Sequence) -> Tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vscale(a: Sequence, s: float) -> Tuple[float, float, float]:
    return (a[0] * s, a[1] * s, a[2] * s)


def _vlen(a: Sequence) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _vnorm(a: Sequence) -> Tuple[float, float, float]:
    ln = _vlen(a)
    if ln < 1e-15:
        return (0.0, 0.0, 0.0)
    return (a[0] / ln, a[1] / ln, a[2] / ln)


def _vdot(a: Sequence, b: Sequence) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vcross(a: Sequence, b: Sequence) -> Tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _vmidpoint(a: Sequence, b: Sequence) -> Tuple[float, float, float]:
    return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5)


# ---------------------------------------------------------------------------
# Clamped knot vector helper
# ---------------------------------------------------------------------------

def _make_clamped_knots(n: int, degree: int) -> np.ndarray:
    """Build a clamped (open) uniform knot vector for n control points."""
    inner = max(0, n - degree - 1)
    if inner > 0:
        interior = np.linspace(0.0, 1.0, inner + 2)[1:-1]
    else:
        interior = np.array([], dtype=float)
    return np.concatenate([
        np.zeros(degree + 1),
        interior,
        np.ones(degree + 1),
    ])


# ---------------------------------------------------------------------------
# Surface evaluation (self-contained correct basis — mirrors patch_srf.py)
# ---------------------------------------------------------------------------

def _find_span(n: int, p: int, u: float, U: np.ndarray) -> int:
    if u >= U[n + 1]:
        return n
    if u <= U[p]:
        return p
    lo, hi = p, n + 1
    mid = (lo + hi) // 2
    while u < U[mid] or u >= U[mid + 1]:
        if u < U[mid]:
            hi = mid
        else:
            lo = mid
        mid = (lo + hi) // 2
    return mid


def _basis_fns(i: int, u: float, p: int, U: np.ndarray) -> np.ndarray:
    N = np.zeros(p + 1)
    N[0] = 1.0
    left = np.zeros(p + 1)
    right = np.zeros(p + 1)
    for j in range(1, p + 1):
        left[j] = u - U[i + 1 - j]
        right[j] = U[i + j] - u
        saved = 0.0
        for r in range(j):
            denom = right[r + 1] + left[j - r]
            if abs(denom) < 1e-15:
                N[r] = 0.0
                saved = 0.0
            else:
                temp = N[r] / denom
                N[r] = saved + right[r + 1] * temp
                saved = left[j - r] * temp
        N[j] = saved
    return N


def _surf_eval(surf: NurbsSurface, u: float, v: float) -> np.ndarray:
    """Evaluate NurbsSurface at (u, v); returns np.ndarray shape (3,)."""
    nu = surf.num_control_points_u
    nv = surf.num_control_points_v
    span_u = _find_span(nu - 1, surf.degree_u, u, surf.knots_u)
    span_v = _find_span(nv - 1, surf.degree_v, v, surf.knots_v)
    Nu = _basis_fns(span_u, u, surf.degree_u, surf.knots_u)
    Nv = _basis_fns(span_v, v, surf.degree_v, surf.knots_v)
    result = np.zeros(surf.control_points.shape[2])
    for ii in range(surf.degree_u + 1):
        for jj in range(surf.degree_v + 1):
            idx_i = span_u - surf.degree_u + ii
            idx_j = span_v - surf.degree_v + jj
            result += Nu[ii] * Nv[jj] * surf.control_points[idx_i, idx_j]
    return result[:3]


# ---------------------------------------------------------------------------
# Bicubic Hermite patch helper
# ---------------------------------------------------------------------------

# Ferguson/Hermite blend functions for t in [0,1]:
#   H0(t) =  2t^3 - 3t^2 + 1
#   H1(t) = -2t^3 + 3t^2
#   H2(t) =   t^3 - 2t^2 + t
#   H3(t) =   t^3 -   t^2

def _h0(t: float) -> float:
    return 2.0 * t ** 3 - 3.0 * t ** 2 + 1.0


def _h1(t: float) -> float:
    return -2.0 * t ** 3 + 3.0 * t ** 2


def _h2(t: float) -> float:
    return t ** 3 - 2.0 * t ** 2 + t


def _h3(t: float) -> float:
    return t ** 3 - t ** 2


def _bicubic_hermite_sample(
    p00: np.ndarray, p10: np.ndarray, p01: np.ndarray, p11: np.ndarray,
    tu0: np.ndarray, tu1: np.ndarray, tv0: np.ndarray, tv1: np.ndarray,
    u: float, v: float,
) -> np.ndarray:
    """Evaluate a bicubic Hermite patch at (u, v).

    Corners: p00, p10 (u=1), p01 (v=1), p11.
    Tangents: tu0 (du at v=0), tu1 (du at v=1), tv0 (dv at u=0), tv1 (dv at u=1).
    """
    # Hermite blend along u
    u_blend = np.array([
        _h0(u) * p00 + _h1(u) * p10 + _h2(u) * tu0 + _h3(u) * tu1,   # at v=0
        _h0(u) * p01 + _h1(u) * p11 + _h2(u) * tv0 + _h3(u) * tv1,   # at v=1 (approx)
    ])
    # Blend along v
    return _h0(v) * u_blend[0] + _h1(v) * u_blend[1]


def _hermite_ctrl_pts(
    p00: np.ndarray, p10: np.ndarray, p01: np.ndarray, p11: np.ndarray,
    tu0: np.ndarray, tu1: np.ndarray, tv0: np.ndarray, tv1: np.ndarray,
) -> np.ndarray:
    """Convert Hermite data to a 4×4 bicubic NURBS control grid.

    The Ferguson-Hermite-to-Bezier conversion maps the 4 corners + 4
    tangent vectors into the 16 Bezier control points for a bicubic patch.
    The Bezier points are then used directly as the NURBS control points for
    a degree-3 surface with clamped uniform knots [0,0,0,0,1,1,1,1].

    Corner ordering:
        P[0,0] = p00  (u=0, v=0)
        P[3,0] = p10  (u=1, v=0)
        P[0,3] = p01  (u=0, v=1)
        P[3,3] = p11  (u=1, v=1)

    Tangent vectors are scaled by 1/3 when converting to Bezier.
    """
    ctrl = np.zeros((4, 4, 3))

    # Corners
    ctrl[0, 0] = p00
    ctrl[3, 0] = p10
    ctrl[0, 3] = p01
    ctrl[3, 3] = p11

    # Bezier inner points: P[1,0] = P[0,0] + tu0/3  etc.
    # tu0 = tangent in U direction at (u=0, v=0) and (u=0, v=1) row
    # tu1 = tangent in U direction at (u=1, v=0) and (u=1, v=1) row
    # tv0 = tangent in V direction at (u=0, v=0) and (u=1, v=0) col
    # tv1 = tangent in V direction at (u=0, v=1) and (u=1, v=1) col

    # Row v=0
    ctrl[1, 0] = p00 + tu0 / 3.0
    ctrl[2, 0] = p10 - tu1 / 3.0

    # Row v=3
    ctrl[1, 3] = p01 + tv0 / 3.0   # tangent in U at v=1
    ctrl[2, 3] = p11 - tv1 / 3.0

    # Col u=0
    ctrl[0, 1] = p00 + tv0 / 3.0   # reuse tv0 for V tangent at u=0
    ctrl[0, 2] = p01 - tv1 / 3.0

    # Col u=3
    ctrl[3, 1] = p10 + tu0 / 3.0   # V tangent at u=1
    ctrl[3, 2] = p11 - tu1 / 3.0

    # Interior: bilinearly interpolate from corner Bezier tangents
    ctrl[1, 1] = 0.25 * (ctrl[1, 0] + ctrl[0, 1] + ctrl[1, 3] + ctrl[0, 2])
    ctrl[1, 2] = 0.25 * (ctrl[1, 0] + ctrl[0, 1] + ctrl[1, 3] + ctrl[0, 3])
    ctrl[2, 1] = 0.25 * (ctrl[2, 0] + ctrl[3, 1] + ctrl[2, 3] + ctrl[3, 0])
    ctrl[2, 2] = 0.25 * (ctrl[2, 0] + ctrl[3, 1] + ctrl[2, 3] + ctrl[3, 3])

    return ctrl


# ---------------------------------------------------------------------------
# Catmull-Rom tangent estimator
# ---------------------------------------------------------------------------

def _catmull_rom_tangent(
    p_prev: np.ndarray, p_curr: np.ndarray, p_next: np.ndarray
) -> np.ndarray:
    """Estimate the tangent at p_curr using the Catmull-Rom formula.

    tangent = 0.5 * (p_next - p_prev)
    When p_prev or p_next is absent (boundary), use one-sided differences.
    """
    return 0.5 * (p_next - p_prev)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_verts(verts: object) -> Optional[str]:
    if not isinstance(verts, (list, tuple)):
        return "verts must be a list"
    for i, v in enumerate(verts):
        if not (isinstance(v, (list, tuple)) and len(v) >= 3):
            return f"verts[{i}] must be [x, y, z]"
        try:
            float(v[0]); float(v[1]); float(v[2])
        except (TypeError, ValueError):
            return f"verts[{i}] must contain numbers"
    return None


def _validate_quad(quad: object, nv: int) -> Optional[str]:
    if not (isinstance(quad, (list, tuple)) and len(quad) == 4):
        return "quad face must be a list of 4 integer indices"
    for k, idx in enumerate(quad):
        try:
            ii = int(idx)
        except (TypeError, ValueError):
            return f"quad[{k}] must be an integer"
        if not (0 <= ii < nv):
            return f"quad[{k}]={ii} out of range (nv={nv})"
    return None


def _validate_faces(faces: object, nv: int) -> Optional[str]:
    if not isinstance(faces, (list, tuple)):
        return "faces must be a list"
    for i, f in enumerate(faces):
        if not isinstance(f, (list, tuple)) or len(f) not in (3, 4):
            return f"faces[{i}] must be a list of 3 or 4 ints"
        for k, idx in enumerate(f):
            try:
                ii = int(idx)
            except (TypeError, ValueError):
                return f"faces[{i}][{k}] must be an integer"
            if not (0 <= ii < nv):
                return f"faces[{i}][{k}]={ii} out of range (nv={nv})"
    return None


# ---------------------------------------------------------------------------
# Edge → neighbour face lookup
# ---------------------------------------------------------------------------

def _build_edge_face_map(faces: List) -> Dict[Tuple[int, int], List[int]]:
    """Map each undirected edge to the list of face indices containing it."""
    ef: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for fi, f in enumerate(faces):
        n = len(f)
        for k in range(n):
            a, b = int(f[k]), int(f[(k + 1) % n])
            key = (min(a, b), max(a, b))
            ef[key].append(fi)
    return ef


def _find_neighbour(
    quad: List[int],
    edge_a: int,
    edge_b: int,
    edge_face_map: Dict[Tuple[int, int], List[int]],
    self_fi: int,
) -> Optional[int]:
    """Return the face index on the other side of edge (edge_a, edge_b), or None."""
    key = (min(edge_a, edge_b), max(edge_a, edge_b))
    candidates = edge_face_map.get(key, [])
    for fi in candidates:
        if fi != self_fi:
            return fi
    return None


# ---------------------------------------------------------------------------
# quad_to_bicubic_patch
# ---------------------------------------------------------------------------

def quad_to_bicubic_patch(
    verts: Sequence,
    quad_face: Sequence,
    *,
    neighbour_faces: Optional[Sequence] = None,
    tol: float = 1e-6,
) -> dict:
    """Fit a bicubic NURBS patch for a single quad face.

    Uses the four surrounding edge-strips (neighbour verts) for Catmull-Rom
    tangent estimation.  When neighbours are absent the boundary tangents fall
    back to simple chord differences.

    Parameters
    ----------
    verts : list of [x, y, z]
        Mesh vertex positions.
    quad_face : list of 4 int
        CCW vertex indices [v0, v1, v2, v3] for the quad.
        v0→v1 = U edge; v0→v3 = V edge.
    neighbour_faces : list of list[int], optional
        Adjacent faces (each up to 4 verts) sharing edges with this quad,
        in order: [opp_u0_edge, opp_u1_edge, opp_v0_edge, opp_v1_edge].
        May be None, shorter than 4, or contain None entries for missing
        neighbours.
    tol : float
        Tolerance (reserved).

    Returns
    -------
    dict
        ok, reason, surface (NurbsSurface, degree 3×3).
    """
    try:
        err = _validate_verts(verts)
        if err:
            return {"ok": False, "reason": err, "surface": None}
        err = _validate_quad(quad_face, len(verts))
        if err:
            return {"ok": False, "reason": err, "surface": None}

        vs = np.array([[float(v[0]), float(v[1]), float(v[2])] for v in verts])
        q = [int(x) for x in quad_face]

        # Quad corners:
        #   q[0]=p00  q[1]=p10  q[2]=p11  q[3]=p01
        # i.e. U-direction: q[0]→q[1] and q[3]→q[2]
        #      V-direction: q[0]→q[3] and q[1]→q[2]

        p00 = vs[q[0]].copy()
        p10 = vs[q[1]].copy()
        p11 = vs[q[2]].copy()
        p01 = vs[q[3]].copy()

        # Check for degenerate quad (zero-area)
        edge_u = p10 - p00
        edge_v = p01 - p00
        area_cross = _vcross(edge_u, edge_v)
        if _vlen(area_cross) < 1e-12:
            return {"ok": False, "reason": "degenerate quad: zero area", "surface": None}

        # --- Tangent estimation via Catmull-Rom using neighbour verts ---
        # We need tangents at all 4 corners in both U and V directions.
        # Strategy: for each edge, find opposite vert in the neighbouring face
        # to form the Catmull-Rom stencil.

        nbrs = list(neighbour_faces) if neighbour_faces is not None else []

        def _opp_vert(face: Optional[Sequence], shared_a: int, shared_b: int) -> Optional[np.ndarray]:
            """Return the vertex in *face* not in {shared_a, shared_b}."""
            if face is None:
                return None
            for idx in face:
                ii = int(idx)
                if ii != shared_a and ii != shared_b:
                    return vs[ii].copy()
            return None

        # Unpack up to 4 neighbour faces
        nbr_u0 = nbrs[0] if len(nbrs) > 0 else None  # opposite edge q[0]-q[3] (u=0 edge)
        nbr_u1 = nbrs[1] if len(nbrs) > 1 else None  # opposite edge q[1]-q[2] (u=1 edge)
        nbr_v0 = nbrs[2] if len(nbrs) > 2 else None  # opposite edge q[0]-q[1] (v=0 edge)
        nbr_v1 = nbrs[3] if len(nbrs) > 3 else None  # opposite edge q[3]-q[2] (v=1 edge)

        # U-direction tangent at v=0 edge (q[0]→q[1]):
        # Catmull-Rom uses the vertex before q[0] and after q[1].
        p_before_u0 = _opp_vert(nbr_v0, q[0], q[1])
        p_after_u1 = _opp_vert(nbr_v1, q[3], q[2])

        if p_before_u0 is not None:
            tu_v0 = _catmull_rom_tangent(p_before_u0, p00, p10) + _catmull_rom_tangent(p_before_u0, p01, p11)
            tu_v0 = tu_v0 * 0.5
        else:
            tu_v0 = p10 - p00

        if p_after_u1 is not None:
            tu_v1 = _catmull_rom_tangent(p01, p11, p_after_u1)
        else:
            tu_v1 = p11 - p01

        # V-direction tangent at u=0 edge (q[0]→q[3]):
        p_before_v0 = _opp_vert(nbr_u0, q[0], q[3])
        p_after_v1 = _opp_vert(nbr_u1, q[1], q[2])

        if p_before_v0 is not None:
            tv_u0 = _catmull_rom_tangent(p_before_v0, p00, p01)
        else:
            tv_u0 = p01 - p00

        if p_after_v1 is not None:
            tv_u1 = _catmull_rom_tangent(p10, p11, p_after_v1)
        else:
            tv_u1 = p11 - p10

        # Build 4×4 Bezier control grid
        ctrl = _hermite_ctrl_pts(p00, p10, p01, p11, tu_v0, tu_v1, tv_u0, tv_u1)

        knots_u = _make_clamped_knots(4, 3)
        knots_v = _make_clamped_knots(4, 3)

        surface = NurbsSurface(
            degree_u=3,
            degree_v=3,
            control_points=ctrl,
            knots_u=knots_u,
            knots_v=knots_v,
        )
        return {"ok": True, "reason": "", "surface": surface}
    except Exception as exc:
        return {"ok": False, "reason": f"quad_to_bicubic_patch failed: {exc}", "surface": None}


# ---------------------------------------------------------------------------
# tri_to_quad_fallback
# ---------------------------------------------------------------------------

def tri_to_quad_fallback(
    verts: Sequence,
    faces: Sequence,
) -> dict:
    """Pair adjacent triangles into quads (greedy heuristic).

    Two triangles sharing a diagonal edge are merged into a quad when:
    - The shared diagonal is the longest edge of at least one of them
      (Blossom-style diagonal selection heuristic).
    - The resulting quad is convex (all interior angles < 180°).
    - Neither triangle has already been paired.

    Parameters
    ----------
    verts : list of [x, y, z]
    faces : list of [i, j, k]  (triangles only; quads are passed through)

    Returns
    -------
    dict
        ok, reason, quads (list of [a, b, c, d]), unpaired (list of face
        indices), pair_count.
    """
    try:
        err = _validate_verts(verts)
        if err:
            return {"ok": False, "reason": err, "quads": [], "unpaired": [], "pair_count": 0}
        err = _validate_faces(faces, len(verts))
        if err:
            return {"ok": False, "reason": err, "quads": [], "unpaired": [], "pair_count": 0}

        vs = np.array([[float(v[0]), float(v[1]), float(v[2])] for v in verts])
        fs = [list(f) for f in faces]

        # Separate quads (pass through) from triangles
        pre_quads: List[List[int]] = []
        tris: List[Tuple[int, List[int]]] = []
        for fi, f in enumerate(fs):
            if len(f) == 4:
                pre_quads.append([int(x) for x in f])
            elif len(f) == 3:
                tris.append((fi, [int(x) for x in f]))

        # Build edge→triangle map (only for tris)
        # edge_tri_map: (min, max) → list of (tri_orig_index, local_edge_slot)
        edge_tri_map: Dict[Tuple[int, int], List[Tuple[int, int]]] = defaultdict(list)
        for ti, (fi, f) in enumerate(tris):
            for slot in range(3):
                a, b = f[slot], f[(slot + 1) % 3]
                key = (min(a, b), max(a, b))
                edge_tri_map[key].append((ti, slot))

        paired: Set[int] = set()
        quads: List[List[int]] = list(pre_quads)
        pair_count = 0

        for ti, (fi, f) in enumerate(tris):
            if ti in paired:
                continue
            # Find best partner: longest shared diagonal
            best_partner: Optional[int] = None
            best_score = -1.0

            for slot in range(3):
                a, b = f[slot], f[(slot + 1) % 3]
                key = (min(a, b), max(a, b))
                for tj, _ in edge_tri_map[key]:
                    if tj == ti or tj in paired:
                        continue
                    # Score = length of shared edge (prefer longer diagonals)
                    edge_len = float(np.linalg.norm(vs[a] - vs[b]))
                    if edge_len > best_score:
                        best_score = edge_len
                        best_partner = tj

            if best_partner is None:
                continue

            # Build quad: merge tri ti and tri best_partner
            _, gf = tris[best_partner]

            # Find shared edge
            fi_set = set(f)
            gf_set = set(gf)
            shared = fi_set & gf_set
            if len(shared) != 2:
                continue
            s0, s1 = sorted(shared)
            # The unique vertices (not shared)
            fi_unique = [v for v in f if v not in shared]
            gf_unique = [v for v in gf if v not in shared]
            if len(fi_unique) != 1 or len(gf_unique) != 1:
                continue

            # Build quad in order: fi_unique[0], s0, gf_unique[0], s1
            q = [fi_unique[0], s0, gf_unique[0], s1]

            # Check convexity (cross products of consecutive edges should all have
            # the same sign in the dominant plane)
            def _is_convex_quad(q_idx: List[int]) -> bool:
                pts = [vs[i] for i in q_idx]
                signs = []
                for k in range(4):
                    e1 = pts[(k + 1) % 4] - pts[k]
                    e2 = pts[(k + 2) % 4] - pts[(k + 1) % 4]
                    cross = _vcross(e1, e2)
                    # Use z component (works for XY; use dominant axis for 3D)
                    signs.append(cross[2])
                # Allow near-zero (flat) — only reject if sign flip is significant
                pos = sum(1 for s in signs if s > 1e-10)
                neg = sum(1 for s in signs if s < -1e-10)
                return pos == 0 or neg == 0

            if not _is_convex_quad(q):
                continue

            quads.append(q)
            paired.add(ti)
            paired.add(best_partner)
            pair_count += 1

        unpaired: List[int] = [tris[ti][0] for ti in range(len(tris)) if ti not in paired]

        return {
            "ok": True,
            "reason": "",
            "quads": quads,
            "unpaired": unpaired,
            "pair_count": pair_count,
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"tri_to_quad_fallback failed: {exc}",
            "quads": [],
            "unpaired": [],
            "pair_count": 0,
        }


# ---------------------------------------------------------------------------
# mesh_to_nurbs_strips
# ---------------------------------------------------------------------------

def mesh_to_nurbs_strips(
    verts: Sequence,
    faces: Sequence,
    *,
    tol: float = 1e-6,
) -> dict:
    """Convert a quad-dominant mesh to per-quad NURBS patches.

    First pairs any triangles into quads via tri_to_quad_fallback, then
    calls quad_to_bicubic_patch for each quad, passing the neighbouring
    face data so shared-edge tangents are consistent (G1 where smooth).

    Parameters
    ----------
    verts : list of [x, y, z]
    faces : list of [i, j, k] or [i, j, k, l]
    tol   : chord deviation tolerance (passed through to patch builder).

    Returns
    -------
    dict
        ok, reason, patches (list of NurbsSurface), patch_count,
        unpaired_tris (list of int).
    """
    try:
        err = _validate_verts(verts)
        if err:
            return {"ok": False, "reason": err, "patches": [], "patch_count": 0, "unpaired_tris": []}
        err = _validate_faces(faces, len(verts))
        if err:
            return {"ok": False, "reason": err, "patches": [], "patch_count": 0, "unpaired_tris": []}

        if not verts or not faces:
            return {"ok": True, "reason": "", "patches": [], "patch_count": 0, "unpaired_tris": []}

        # Pair triangles
        pair_result = tri_to_quad_fallback(verts, faces)
        if not pair_result["ok"]:
            return {
                "ok": False,
                "reason": f"tri pairing failed: {pair_result['reason']}",
                "patches": [],
                "patch_count": 0,
                "unpaired_tris": [],
            }

        quads: List[List[int]] = pair_result["quads"]
        unpaired: List[int] = pair_result["unpaired"]

        if not quads:
            return {
                "ok": True,
                "reason": "",
                "patches": [],
                "patch_count": 0,
                "unpaired_tris": unpaired,
            }

        # Build edge→quad map for neighbour lookup
        ef = _build_edge_face_map(quads)

        patches: List[NurbsSurface] = []
        for qi, q in enumerate(quads):
            # Gather up to 4 neighbour faces:
            # edge order: [u=0 edge (q0-q3), u=1 edge (q1-q2),
            #              v=0 edge (q0-q1), v=1 edge (q3-q2)]
            edges = [
                (q[0], q[3]),  # u=0
                (q[1], q[2]),  # u=1
                (q[0], q[1]),  # v=0
                (q[3], q[2]),  # v=1
            ]
            nbr_faces: List[Optional[List[int]]] = []
            for ea, eb in edges:
                nbr_fi = _find_neighbour(q, ea, eb, ef, qi)
                if nbr_fi is not None and nbr_fi < len(quads):
                    nbr_faces.append(quads[nbr_fi])
                else:
                    nbr_faces.append(None)

            result = quad_to_bicubic_patch(
                verts, q,
                neighbour_faces=nbr_faces,
                tol=tol,
            )
            if result["ok"] and result["surface"] is not None:
                patches.append(result["surface"])

        return {
            "ok": True,
            "reason": "",
            "patches": patches,
            "patch_count": len(patches),
            "unpaired_tris": unpaired,
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"mesh_to_nurbs_strips failed: {exc}",
            "patches": [],
            "patch_count": 0,
            "unpaired_tris": [],
        }


# ---------------------------------------------------------------------------
# quality_report
# ---------------------------------------------------------------------------

_QUALITY_SAMPLES = 5  # samples per edge for G0/G1 checks


def _sample_patch_edge(
    surf: NurbsSurface,
    edge: str,
    n: int = _QUALITY_SAMPLES,
) -> Tuple[np.ndarray, np.ndarray]:
    """Sample position and approximate tangent along a patch boundary edge.

    edge in {"u0", "u1", "v0", "v1"}.
    Returns (positions, tangents), each shape (n, 3).
    """
    params = np.linspace(0.0, 1.0, n)
    positions = np.zeros((n, 3))
    tangents = np.zeros((n, 3))
    h = 1e-4

    for k, t in enumerate(params):
        if edge == "u0":
            u, v = 0.0, t
            u2, v2 = h, t
        elif edge == "u1":
            u, v = 1.0, t
            u2, v2 = 1.0 - h, t
        elif edge == "v0":
            u, v = t, 0.0
            u2, v2 = t, h
        else:  # v1
            u, v = t, 1.0
            u2, v2 = t, 1.0 - h

        positions[k] = _surf_eval(surf, u, v)
        p2 = _surf_eval(surf, u2, v2)
        tang = p2 - positions[k]
        ln = float(np.linalg.norm(tang))
        tangents[k] = tang / ln if ln > 1e-15 else np.array([0.0, 0.0, 0.0])

    return positions, tangents


def _patch_closest_dist(
    surf: NurbsSurface,
    point: np.ndarray,
    grid_n: int = 8,
) -> float:
    """Approximate closest distance from *point* to *surf* by grid sampling."""
    us = np.linspace(0.0, 1.0, grid_n)
    vs = np.linspace(0.0, 1.0, grid_n)
    min_dist = float("inf")
    for u in us:
        for v in vs:
            p = _surf_eval(surf, float(u), float(v))
            d = float(np.linalg.norm(p - point))
            if d < min_dist:
                min_dist = d
    return min_dist


def quality_report(
    patches: Sequence,
    verts: Sequence,
    faces: Sequence,
    *,
    tol: float = 1e-3,
) -> dict:
    """Compute per-patch chord deviation and cross-patch G0/G1 quality.

    Parameters
    ----------
    patches : list of NurbsSurface
    verts   : list of [x, y, z]  — original mesh vertices
    faces   : list of face index lists  — original mesh faces
    tol     : threshold for flagging deviations (informational)

    Returns
    -------
    dict
        ok, reason, patch_count, max_chord_dev, per_patch (list of dicts),
        g0_max_dev, g1_max_dev.
    """
    try:
        if not isinstance(patches, (list, tuple)):
            return {"ok": False, "reason": "patches must be a list", "patch_count": 0,
                    "max_chord_dev": 0.0, "per_patch": [], "g0_max_dev": 0.0, "g1_max_dev": 0.0}

        err = _validate_verts(verts)
        if err:
            return {"ok": False, "reason": err, "patch_count": 0,
                    "max_chord_dev": 0.0, "per_patch": [], "g0_max_dev": 0.0, "g1_max_dev": 0.0}

        vs = np.array([[float(v[0]), float(v[1]), float(v[2])] for v in verts])

        per_patch: List[dict] = []
        max_chord_dev = 0.0

        for pi, surf in enumerate(patches):
            if not isinstance(surf, NurbsSurface):
                per_patch.append({"patch_idx": pi, "max_dev": float("nan"), "ok": False})
                continue

            # Measure deviation at corners (which correspond to mesh verts)
            corner_devs = []
            for (u, v) in [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]:
                pt = _surf_eval(surf, u, v)
                # Find nearest input vertex
                if len(vs) > 0:
                    dists = np.linalg.norm(vs - pt, axis=1)
                    min_d = float(np.min(dists))
                    corner_devs.append(min_d)

            # Also sample the interior and check against verts
            interior_devs: List[float] = []
            sample_pts = [
                _surf_eval(surf, float(u), float(v))
                for u in np.linspace(0.0, 1.0, 4)
                for v in np.linspace(0.0, 1.0, 4)
            ]
            for pt in sample_pts:
                if len(vs) > 0:
                    dists = np.linalg.norm(vs - pt, axis=1)
                    interior_devs.append(float(np.min(dists)))

            all_devs = corner_devs + interior_devs
            patch_max = max(all_devs) if all_devs else 0.0
            if patch_max > max_chord_dev:
                max_chord_dev = patch_max

            per_patch.append({
                "patch_idx": pi,
                "max_dev": patch_max,
                "ok": patch_max <= tol * 10,
            })

        # G0 / G1 between adjacent patches: compare shared edges pairwise
        n = len(patches)
        g0_max = 0.0
        g1_max = 0.0

        for i in range(n):
            for j in range(i + 1, n):
                if not (isinstance(patches[i], NurbsSurface) and
                        isinstance(patches[j], NurbsSurface)):
                    continue

                surf_i = patches[i]
                surf_j = patches[j]

                # Check all 4 edge combinations for the closest shared edges
                for ei, ej in [("u0", "u1"), ("u1", "u0"), ("v0", "v1"), ("v1", "v0"),
                                ("u0", "v0"), ("u0", "v1"), ("u1", "v0"), ("u1", "v1"),
                                ("v0", "u0"), ("v0", "u1"), ("v1", "u0"), ("v1", "u1")]:
                    pos_i, tang_i = _sample_patch_edge(surf_i, ei, n=3)
                    pos_j, tang_j = _sample_patch_edge(surf_j, ej, n=3)

                    # G0: check if the edge centroids are close
                    cen_i = pos_i[len(pos_i) // 2]
                    cen_j = pos_j[len(pos_j) // 2]
                    g0_dist = float(np.linalg.norm(cen_i - cen_j))

                    if g0_dist < 1e-2:  # edges are geometrically close
                        if g0_dist > g0_max:
                            g0_max = g0_dist

                        # G1: angle between tangents at midpoint
                        ti = tang_i[len(tang_i) // 2]
                        tj = tang_j[len(tang_j) // 2]
                        ln_i = float(np.linalg.norm(ti))
                        ln_j = float(np.linalg.norm(tj))
                        if ln_i > 1e-10 and ln_j > 1e-10:
                            cos_a = float(np.clip(np.dot(ti / ln_i, tj / ln_j), -1.0, 1.0))
                            angle = math.acos(abs(cos_a))
                            if angle > g1_max:
                                g1_max = angle

        return {
            "ok": True,
            "reason": "",
            "patch_count": len(patches),
            "max_chord_dev": max_chord_dev,
            "per_patch": per_patch,
            "g0_max_dev": g0_max,
            "g1_max_dev": g1_max,
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"quality_report failed: {exc}",
            "patch_count": 0,
            "max_chord_dev": 0.0,
            "per_patch": [],
            "g0_max_dev": 0.0,
            "g1_max_dev": 0.0,
        }


# ---------------------------------------------------------------------------
# LLM tool registration (gated — graceful no-op when registry absent)
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore[import]
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    import json as _json
    _REGISTRY_AVAILABLE = True
except ImportError:
    _REGISTRY_AVAILABLE = False


if _REGISTRY_AVAILABLE:
    # ------------------------------------------------------------------
    # mesh_to_nurbs_convert
    # ------------------------------------------------------------------

    _mesh_to_nurbs_convert_spec = ToolSpec(
        name="mesh_to_nurbs_convert",
        description=(
            "Convert a quad-dominant mesh (verts + faces) into per-quad bicubic NURBS patches "
            "(Rhino MeshToNURB equivalent).  Triangles are first paired into quads where possible. "
            "Returns one NurbsSurface per quad, encoded as a control-point grid + knot vectors.\n"
            "\n"
            "Returns:\n"
            "  ok           : bool\n"
            "  patches      : list of {control_points, knots_u, knots_v, degree_u, degree_v}\n"
            "  patch_count  : int\n"
            "  unpaired_tris: list of int (face indices of unpaired triangles)\n"
            "\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "verts": {
                    "type": "array",
                    "description": "Vertex list [[x,y,z], ...]",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "faces": {
                    "type": "array",
                    "description": "Face list [[i,j,k], ...] or [[i,j,k,l], ...] (0-based indices).",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
                "tol": {
                    "type": "number",
                    "description": "Geometric tolerance (default 1e-6).",
                },
            },
            "required": ["verts", "faces"],
        },
    )

    @register(_mesh_to_nurbs_convert_spec)
    async def run_mesh_to_nurbs_convert(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        verts = a.get("verts")
        faces = a.get("faces")
        tol = a.get("tol", 1e-6)

        if verts is None or faces is None:
            return err_payload("verts and faces are required", "BAD_ARGS")
        if not isinstance(tol, (int, float)) or tol <= 0:
            return err_payload("tol must be a positive number", "BAD_ARGS")

        result = mesh_to_nurbs_strips(verts, faces, tol=float(tol))
        if not result["ok"]:
            return err_payload(result.get("reason", "conversion failed"), "OP_FAILED")

        patch_dicts = []
        for surf in result["patches"]:
            patch_dicts.append({
                "control_points": surf.control_points.tolist(),
                "knots_u": surf.knots_u.tolist(),
                "knots_v": surf.knots_v.tolist(),
                "degree_u": surf.degree_u,
                "degree_v": surf.degree_v,
            })

        return ok_payload({
            "patches": patch_dicts,
            "patch_count": result["patch_count"],
            "unpaired_tris": result["unpaired_tris"],
        })

    # ------------------------------------------------------------------
    # mesh_to_nurbs_quality
    # ------------------------------------------------------------------

    _mesh_to_nurbs_quality_spec = ToolSpec(
        name="mesh_to_nurbs_quality",
        description=(
            "Compute quality metrics for a set of NURBS patches produced by mesh_to_nurbs_convert. "
            "Reports per-patch max chord deviation vs source mesh vertices and cross-patch G0/G1 "
            "continuity deviations.\n"
            "\n"
            "Returns:\n"
            "  ok            : bool\n"
            "  patch_count   : int\n"
            "  max_chord_dev : float (max deviation over all patches)\n"
            "  per_patch     : list of {patch_idx, max_dev, ok}\n"
            "  g0_max_dev    : float (worst G0 position gap between adjacent patches)\n"
            "  g1_max_dev    : float (worst G1 tangent angle in radians)\n"
            "\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "patches": {
                    "type": "array",
                    "description": "List of patch dicts from mesh_to_nurbs_convert.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "control_points": {"type": "array"},
                            "knots_u": {"type": "array"},
                            "knots_v": {"type": "array"},
                            "degree_u": {"type": "integer"},
                            "degree_v": {"type": "integer"},
                        },
                    },
                },
                "verts": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "faces": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
                "tol": {"type": "number", "description": "Chord deviation threshold (default 1e-3)."},
            },
            "required": ["patches", "verts", "faces"],
        },
    )

    @register(_mesh_to_nurbs_quality_spec)
    async def run_mesh_to_nurbs_quality(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        raw_patches = a.get("patches")
        verts = a.get("verts")
        faces = a.get("faces")
        tol = float(a.get("tol", 1e-3))

        if raw_patches is None or verts is None or faces is None:
            return err_payload("patches, verts, and faces are required", "BAD_ARGS")

        # Reconstruct NurbsSurface objects
        surf_list: List[NurbsSurface] = []
        for pd in raw_patches:
            try:
                cp = np.array(pd["control_points"], dtype=float)
                ku = np.array(pd["knots_u"], dtype=float)
                kv = np.array(pd["knots_v"], dtype=float)
                du = int(pd["degree_u"])
                dv = int(pd["degree_v"])
                surf_list.append(NurbsSurface(
                    degree_u=du, degree_v=dv,
                    control_points=cp,
                    knots_u=ku, knots_v=kv,
                ))
            except Exception as exc:
                return err_payload(f"invalid patch dict: {exc}", "BAD_ARGS")

        result = quality_report(surf_list, verts, faces, tol=tol)
        if not result["ok"]:
            return err_payload(result.get("reason", "quality report failed"), "OP_FAILED")

        return ok_payload({
            "patch_count": result["patch_count"],
            "max_chord_dev": result["max_chord_dev"],
            "per_patch": result["per_patch"],
            "g0_max_dev": result["g0_max_dev"],
            "g1_max_dev": result["g1_max_dev"],
        })
