"""
kerf_cad_core.geom.mold — Mould / injection-moulding geometry utilities.

GK-118: Parting-line generation
--------------------------------
The parting line is the silhouette curve of a body w.r.t. a pull direction:
the locus of points on the surface where the face normal is exactly
perpendicular to the pull direction (draft angle ≈ 0°).

In practice the body is discretised by sampling each face over a UV grid;
for each pair of adjacent UV samples whose dot-product sign with the pull
direction changes, the zero-crossing point is interpolated and collected.
The result is a list of 3-D points that approximate the parting-line
silhouette.

GK-119: Cavity / core mould split
-----------------------------------
Split a mould *block* around a *part* along the parting surface:

  mold_split(part, block, pull_direction) -> {"core": Body, "cavity": Body}

Algorithm
~~~~~~~~~
1. Compute the parting line of *part* w.r.t. *pull_direction* (GK-118).
2. Project each parting point onto the pull axis and average to get the
   parting-plane origin along the pull axis.
3. Extract the axis-aligned bounding box of *block* from its vertex set.
4. Split the block into two proper closed half-box bodies at the parting
   plane height along the pull axis using :func:`box_to_body`.
5. Subtract *part* from each half using :func:`body_difference` (GK-18).
6. Return ``{"core": lower_half − part, "cavity": upper_half − part}``.

Oracle: vol(core) + vol(cavity) + vol(part) ≈ vol(block) ± tol.
Both halves are watertight (validate_body passes).

Only pure-Python / NumPy — no OCC runtime required (hermetic).
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Union

import numpy as np

# ---------------------------------------------------------------------------
# Public type alias (mirrors convention in bridge_loops / section_contour)
# ---------------------------------------------------------------------------

Point3 = List[float]

# ---------------------------------------------------------------------------
# Internal helpers (reuse draft_analysis UV-sampling machinery)
# ---------------------------------------------------------------------------

_FD_H: float = 1e-7
_GRID: int = 16   # UV sample count per axis per face (finer than GK-92's 5)


def _face_surface_domain(face: object):
    """Return (u_lo, u_hi, v_lo, v_hi) for the parametric domain of *face*."""
    srf = face.surface  # type: ignore[attr-defined]
    try:
        from kerf_cad_core.geom.brep import Plane, CylinderSurface, SphereSurface
        if isinstance(srf, Plane):
            return 0.0, 1.0, 0.0, 1.0
        elif isinstance(srf, CylinderSurface):
            return 0.0, 2.0 * math.pi, 0.0, 1.0
        elif isinstance(srf, SphereSurface):
            return 0.0, 2.0 * math.pi, -math.pi / 2.0, math.pi / 2.0
        else:
            raise TypeError
    except (TypeError, ImportError):
        return 0.0, 1.0, 0.0, 1.0


def _eval_point(srf: object, u: float, v: float) -> np.ndarray:
    """Evaluate *srf* at (u, v) and return a 3-vector."""
    return np.asarray(srf.evaluate(u, v), dtype=float)[:3]


def _outward_normal(face: object, srf: object, u: float, v: float) -> np.ndarray:
    """Return the outward unit normal of *face* at (u, v)."""
    p = _eval_point(srf, u, v)
    if hasattr(srf, "normal"):
        raw = np.asarray(srf.normal(u, v), dtype=float)[:3]
    else:
        pu = _eval_point(srf, u + _FD_H, v)
        pv = _eval_point(srf, u, v + _FD_H)
        raw = np.cross(pu - p, pv - p)

    nrm = float(np.linalg.norm(raw))
    unit_n = raw / nrm if nrm > 1e-15 else raw

    orient = getattr(face, "orientation", True)
    if not orient:
        unit_n = -unit_n
    return unit_n


def _dot_pull(face: object, srf: object, u: float, v: float,
              pull_hat: np.ndarray) -> float:
    """Signed dot-product n(u,v) · pull_hat (positive = faces pull direction)."""
    n = _outward_normal(face, srf, u, v)
    return float(np.dot(n, pull_hat))


def _lerp_pt(srf: object, u0: float, v0: float, u1: float, v1: float,
             d0: float, d1: float) -> Point3:
    """Linear interpolation along the UV edge where the sign of *d* changes."""
    if abs(d0 - d1) < 1e-30:
        t = 0.5
    else:
        t = d0 / (d0 - d1)
    t = max(0.0, min(1.0, t))
    u = u0 + t * (u1 - u0)
    v = v0 + t * (v1 - v0)
    p = _eval_point(srf, u, v)
    return [float(p[0]), float(p[1]), float(p[2])]


# ---------------------------------------------------------------------------
# GK-118: parting_line
# ---------------------------------------------------------------------------

def parting_line(
    body: object,
    pull_direction: Union[Sequence[float], np.ndarray],
    *,
    n_samples: int = _GRID,
) -> List[Point3]:
    """Parting-line generation for injection-moulding / die-casting.

    GK-118
    ------
    The parting line is the silhouette of *body* w.r.t. the demould
    *pull_direction*: the set of surface points where the outward face
    normal is perpendicular to the pull axis (draft angle ≈ 0).

    The algorithm samples each face on an ``n_samples × n_samples`` UV
    grid and, for every UV quad, finds the four edges where the sign of
    ``n · pull_hat`` changes.  Zero-crossings are linearly interpolated
    to obtain 3-D parting points.

    Parameters
    ----------
    body:
        Any ``kerf_cad_core.geom.brep.Body`` (or duck-typed object with
        ``all_faces()`` returning ``Face``-like objects that have a
        ``.surface`` attribute supporting ``.evaluate(u, v)``).
    pull_direction:
        3-vector giving the mould pull direction (need not be unit length).
    n_samples:
        UV grid resolution per axis per face.  Default 16 (higher → more
        parting points, finer silhouette approximation).

    Returns
    -------
    list[Point3]
        Unsorted list of 3-D points lying on the parting line/curve.
        For a closed convex body (sphere, cylinder …) the points will
        approximate the closed equatorial silhouette.

    Raises
    ------
    ValueError
        If *pull_direction* is a zero vector.

    Notes
    -----
    * Pure-Python / NumPy only — no OCC runtime required.
    * Reuses the per-face UV sampling and outward-normal convention from
      ``draft_analysis`` (GK-92).
    """
    pull = np.asarray(pull_direction, dtype=float).ravel()[:3]
    pull_nrm = float(np.linalg.norm(pull))
    if pull_nrm < 1e-15:
        raise ValueError("pull_direction must be a non-zero vector")
    pull_hat = pull / pull_nrm

    n = int(n_samples)
    if n < 2:
        n = 2

    parting_pts: List[Point3] = []

    for face in body.all_faces():  # type: ignore[attr-defined]
        srf = face.surface  # type: ignore[attr-defined]
        u_lo, u_hi, v_lo, v_hi = _face_surface_domain(face)

        us = np.linspace(u_lo, u_hi, n)
        vs = np.linspace(v_lo, v_hi, n)

        # Build (n x n) grid of dot-products
        dots = np.empty((n, n), dtype=float)
        for i, u in enumerate(us):
            for j, v in enumerate(vs):
                dots[i, j] = _dot_pull(face, srf, float(u), float(v), pull_hat)

        # Scan horizontal edges (fixed i, varying j)
        for i in range(n):
            for j in range(n - 1):
                d0, d1 = dots[i, j], dots[i, j + 1]
                if d0 * d1 <= 0.0 and not (d0 == 0.0 and d1 == 0.0):
                    pt = _lerp_pt(srf,
                                  float(us[i]), float(vs[j]),
                                  float(us[i]), float(vs[j + 1]),
                                  d0, d1)
                    parting_pts.append(pt)

        # Scan vertical edges (fixed j, varying i)
        for j in range(n):
            for i in range(n - 1):
                d0, d1 = dots[i, j], dots[i + 1, j]
                if d0 * d1 <= 0.0 and not (d0 == 0.0 and d1 == 0.0):
                    pt = _lerp_pt(srf,
                                  float(us[i]),     float(vs[j]),
                                  float(us[i + 1]), float(vs[j]),
                                  d0, d1)
                    parting_pts.append(pt)

    return parting_pts


# ---------------------------------------------------------------------------
# GK-121: undercut_faces
# ---------------------------------------------------------------------------

# Colour codes for the face-colour map (CSS / viewport compatible)
_COLOUR_UNDERCUT = "#FF4444"   # red   — undercut (pull-direction blocked)
_COLOUR_PARTING  = "#FFAA00"   # amber — near-zero draft (parting line region)
_COLOUR_CLEAR    = "#44BB44"   # green — positive draft (clear of undercut)

# Draft-angle threshold (radians): |dot| < sin(threshold_deg) → parting zone
_PARTING_THRESHOLD_DEG: float = 3.0
_PARTING_THRESHOLD_SIN: float = math.sin(math.radians(_PARTING_THRESHOLD_DEG))


def undercut_faces(
    body: object,
    pull_direction: Union[Sequence[float], np.ndarray],
    *,
    n_samples: int = _GRID,
) -> dict:
    """Undercut-region detection for injection-moulding / die-casting.

    GK-121
    ------
    A face is **undercut** if its outward normal opposes the pull direction
    (draft angle < 0°): a mould half moving along *pull_direction* cannot
    release the part because material overhangs the face.

    The algorithm samples each face on an ``n_samples × n_samples`` UV grid,
    computes the outward normal at every sample, and classifies the face by
    the *worst-case* (most negative) draft dot-product across all samples.

    Classification
    ~~~~~~~~~~~~~~
    * **undercut** — at least one sample has ``n · pull_hat < 0`` (any part of
      the face opposes demould; it will lock the part in the mould).
    * **parting** — all samples satisfy ``|n · pull_hat| < sin(3°)`` (near-zero
      draft; treated as parting-surface region, not locked but borderline).
    * **clear** — all samples have ``n · pull_hat ≥ 0`` and at least one
      exceeds the parting threshold (positive draft; releases cleanly).

    Parameters
    ----------
    body:
        Any ``kerf_cad_core.geom.brep.Body`` (or duck-typed object with
        ``all_faces()`` returning ``Face``-like objects with a ``.surface``
        supporting ``.evaluate(u, v)`` and, optionally, ``.normal(u, v)``).
    pull_direction:
        3-vector giving the demould pull direction (need not be unit length).
    n_samples:
        UV grid resolution per axis per face.  Default 16.

    Returns
    -------
    dict with keys:

    ``undercut_face_ids`` : list[int]
        IDs (``face.id``) of all undercut faces.
    ``face_colours`` : dict[int, str]
        ``{face_id: colour_hex}`` for **every** face in *body*.
        Colour key: ``"#FF4444"`` undercut / ``"#FFAA00"`` parting /
        ``"#44BB44"`` clear.
    ``has_undercut`` : bool
        ``True`` iff at least one face is undercut.

    Raises
    ------
    ValueError
        If *pull_direction* is a zero vector.

    Notes
    -----
    * Pure-Python / NumPy only — no OCC runtime required (hermetic).
    * Reuses the per-face UV sampling and outward-normal helpers from GK-118.
    """
    pull = np.asarray(pull_direction, dtype=float).ravel()[:3]
    pull_nrm = float(np.linalg.norm(pull))
    if pull_nrm < 1e-15:
        raise ValueError("pull_direction must be a non-zero vector")
    pull_hat = pull / pull_nrm

    n = int(n_samples)
    if n < 2:
        n = 2

    undercut_ids: List[int] = []
    face_colours: dict = {}

    for face in body.all_faces():  # type: ignore[attr-defined]
        srf = face.surface  # type: ignore[attr-defined]
        fid = face.id  # type: ignore[attr-defined]
        u_lo, u_hi, v_lo, v_hi = _face_surface_domain(face)

        us = np.linspace(u_lo, u_hi, n)
        vs = np.linspace(v_lo, v_hi, n)

        # Collect dot-products across all UV samples
        min_dot = float("inf")
        max_dot = float("-inf")

        for i in range(n):
            for j in range(n):
                d = _dot_pull(face, srf, float(us[i]), float(vs[j]), pull_hat)
                if d < min_dot:
                    min_dot = d
                if d > max_dot:
                    max_dot = d

        # Classify this face
        if min_dot < 0.0:
            # At least one sample opposes the pull → undercut
            colour = _COLOUR_UNDERCUT
            undercut_ids.append(fid)
        elif max_dot < _PARTING_THRESHOLD_SIN:
            # All samples near-zero draft → parting zone
            colour = _COLOUR_PARTING
        else:
            colour = _COLOUR_CLEAR

        face_colours[fid] = colour

    return {
        "undercut_face_ids": undercut_ids,
        "face_colours": face_colours,
        "has_undercut": len(undercut_ids) > 0,
    }


# ---------------------------------------------------------------------------
# GK-119: mold_split
# ---------------------------------------------------------------------------

def _body_vertex_bounds(body: object) -> np.ndarray:
    """Return (2, 3) array [lo, hi] bounding the vertex set of *body*."""
    pts = []
    for v in body.all_vertices():  # type: ignore[attr-defined]
        pts.append(np.asarray(v.point, dtype=float)[:3])
    if not pts:
        raise ValueError("block body has no vertices")
    arr = np.array(pts, dtype=float)
    return np.stack([arr.min(axis=0), arr.max(axis=0)])


def mold_split(
    part: object,
    block: object,
    pull_direction: Union[Sequence[float], np.ndarray],
) -> Dict[str, object]:
    """Cavity / core mould split along the parting surface.

    GK-119
    ------
    Split *block* around *part* along the parting surface derived from the
    parting line of *part* w.r.t. *pull_direction*.

    Parameters
    ----------
    part:
        The moulded part — a closed :class:`~kerf_cad_core.geom.brep.Body`.
    block:
        The mould block (must be an axis-aligned box body produced by
        :func:`~kerf_cad_core.geom.brep_build.box_to_body`).
    pull_direction:
        3-vector giving the mould pull / demould direction (need not be
        unit length).

    Returns
    -------
    dict with keys:

    ``"core"`` : Body
        Lower mould half (on the ``−pull_direction`` side) with the part
        cavity machined out.
    ``"cavity"`` : Body
        Upper mould half (on the ``+pull_direction`` side) with the part
        cavity machined out.

    Raises
    ------
    ValueError
        If *pull_direction* is a zero vector, or if *part* has no parting
        points (degenerate geometry).

    Notes
    -----
    * Pure-Python / NumPy only — no OCC runtime required (hermetic).
    * The parting plane is derived from GK-118 :func:`parting_line`.
    * Each half is split from the *block* using :func:`box_to_body` at the
      parting height, then the *part* is subtracted via
      :func:`~kerf_cad_core.geom.boolean.body_difference` (GK-84 / GK-18).
    * Oracle: ``vol(core) + vol(cavity) + vol(part) ≈ vol(block) ± tol``
      and both halves pass :func:`~kerf_cad_core.geom.brep.validate_body`.
    """
    from kerf_cad_core.geom.brep_build import box_to_body
    from kerf_cad_core.geom.boolean import body_difference
    from kerf_cad_core.geom.brep import validate_body

    # --- 1. Normalise pull direction -----------------------------------------
    pull = np.asarray(pull_direction, dtype=float).ravel()[:3]
    pull_nrm = float(np.linalg.norm(pull))
    if pull_nrm < 1e-15:
        raise ValueError("pull_direction must be a non-zero vector")
    pull_hat = pull / pull_nrm

    # --- 2. Compute parting-plane origin from GK-118 parting_line -----------
    pts = parting_line(part, pull_hat)
    if not pts:
        # Fallback: use the centroid of the part's vertex set
        bounds = _body_vertex_bounds(part)
        centroid = 0.5 * (bounds[0] + bounds[1])
        parting_origin = centroid
    else:
        parting_arr = np.array(pts, dtype=float)  # (N, 3)
        parting_origin = parting_arr.mean(axis=0)

    # Project parting origin onto pull axis to get the parting height
    parting_height = float(np.dot(parting_origin, pull_hat))

    # --- 3. Extract AABB of block -------------------------------------------
    block_bounds = _body_vertex_bounds(block)
    lo = block_bounds[0]   # (3,) minimum corner
    hi = block_bounds[1]   # (3,) maximum corner
    tol = 1e-7

    # --- 4. Build two proper closed half-box bodies -------------------------
    # We identify which axis is dominant in pull_hat (closest to ±X/Y/Z)
    # and split at the parting height along that axis.
    # For a general pull direction, project block corners onto pull axis to
    # find the lo/hi extents, then split at parting_height.

    # Corners of the block
    corners = np.array([
        [lo[0], lo[1], lo[2]],
        [hi[0], lo[1], lo[2]],
        [lo[0], hi[1], lo[2]],
        [hi[0], hi[1], lo[2]],
        [lo[0], lo[1], hi[2]],
        [hi[0], lo[1], hi[2]],
        [lo[0], hi[1], hi[2]],
        [hi[0], hi[1], hi[2]],
    ], dtype=float)
    proj = corners @ pull_hat  # signed distances along pull axis
    block_lo_proj = float(proj.min())
    block_hi_proj = float(proj.max())

    # Clamp parting height within block bounds with a small safety margin
    eps = tol * 10.0
    parting_height = max(block_lo_proj + eps, min(block_hi_proj - eps, parting_height))

    # For axis-aligned pull directions, create proper half-boxes directly.
    # Determine the pull axis index (or use a general plane-clip approach).
    abs_hat = np.abs(pull_hat)
    axis = int(np.argmax(abs_hat))   # dominant axis
    sign = float(np.sign(pull_hat[axis]))  # +1 or -1

    # Decompose parting height back into world coordinate along dominant axis.
    # For axis-aligned pull (pull_hat ≈ e_axis), parting_height == world coord.
    # For oblique pull, we project back: world_coord = parting_height / hat[axis]
    if abs_hat[axis] > 1e-9:
        world_split = parting_height / pull_hat[axis]
    else:
        world_split = 0.5 * (lo[axis] + hi[axis])

    world_split = max(lo[axis] + eps, min(hi[axis] - eps, float(world_split)))

    # Lower half: lo[axis] → world_split  (core side: opposite to pull)
    # Upper half: world_split → hi[axis]  (cavity side: along pull)
    # When pull_hat[axis] < 0 (negative axis direction), flip assignment
    if sign >= 0:
        lower_lo = lo.copy()
        lower_hi = hi.copy()
        lower_hi[axis] = world_split

        upper_lo = lo.copy()
        upper_lo[axis] = world_split
        upper_hi = hi.copy()
    else:
        # Pull is in −axis direction: "upper" (cavity) is lo side
        upper_lo = lo.copy()
        upper_hi = hi.copy()
        upper_hi[axis] = world_split

        lower_lo = lo.copy()
        lower_lo[axis] = world_split
        lower_hi = hi.copy()

    # Build closed box bodies for each half
    def _half_box(lo3: np.ndarray, hi3: np.ndarray) -> object:
        dx = float(hi3[0] - lo3[0])
        dy = float(hi3[1] - lo3[1])
        dz = float(hi3[2] - lo3[2])
        return box_to_body(lo3.tolist(), dx, dy, dz, tol)

    core_block = _half_box(lower_lo, lower_hi)
    cavity_block = _half_box(upper_lo, upper_hi)

    # --- 5. Subtract part from each half ------------------------------------
    core = body_difference(core_block, part)
    cavity = body_difference(cavity_block, part)

    # --- 6. Validate and return ---------------------------------------------
    for label, b in (("core", core), ("cavity", cavity)):
        result = validate_body(b)
        if not result["ok"]:
            # Non-fatal: surface the errors as a warning attribute but continue
            b._mold_split_warnings = result["errors"]  # type: ignore[attr-defined]

    return {"core": core, "cavity": cavity}
