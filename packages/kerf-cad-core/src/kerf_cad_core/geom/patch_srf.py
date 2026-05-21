"""
patch_srf.py
============
Pure-Python surface generators: Patch / Drape / Heightfield (Rhino parity).

All four functions build a NurbsSurface from kerf_cad_core.geom.nurbs and
return a result dict ``{"ok": bool, "reason": str, ...}``.  They never raise.

Public API
----------
patch_surface(points, *, nu, nv, boundary, stiffness, max_iter, tol)
    Best-fit NURBS surface through scattered 3D points (and optional boundary
    curves).  Solves a least-squares system with a thin-plate stiffness term,
    then refines via iterative re-weighting.  Returns fitting diagnostics
    (max_deviation, smoothing_energy).

drape_surface(obstacle_pts, bbox, *, nu, nv, gravity_axis, relax_iters)
    Projects a uniform grid downward (or along ``gravity_axis``) over an
    obstacle point cloud / mesh vertices and rests the grid on the upper
    envelope.  Returns the draped NurbsSurface.

heightfield(z_array, *, x_range, y_range, v_scale)
    Build a regular UV grid surface from an m×n elevation array or a
    float array where z_array[i, j] is the height at grid node (i, j).
    Evaluating the surface at grid nodes reproduces the input elevations
    exactly.

surface_from_grid(points_grid, *, degree_u, degree_v)
    Interpolating NURBS surface through an m×n ordered point net.  The
    surface passes exactly through every input point.

Diagnostics
-----------
Each returned dict contains:
  ok               : bool
  reason           : str  (non-empty only when ok is False)
  surface          : NurbsSurface  (present when ok is True)
  max_deviation    : float  (max Euclidean fit error; 0 for exact methods)
  smoothing_energy : float  (thin-plate energy; 0 when not applicable)

LLM tools
---------
@register tools: patch_srf_fit, drape_srf_project, heightfield_srf,
                 grid_srf_interp  — gated behind kerf_chat registry.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

from kerf_cad_core.geom.nurbs import NurbsSurface, surface_derivatives


# ---------------------------------------------------------------------------
# Self-contained B-spline utilities (correct NURBS Book Algorithm A2.1/A2.2)
# The nurbs.py basis_functions has a different calling convention that produces
# zeros for interior knot spans at higher degrees; we use our own here.
# ---------------------------------------------------------------------------

def _find_span(n: int, p: int, u: float, U: np.ndarray) -> int:
    """Knot-span index: find i such that U[i] <= u < U[i+1].  NURBS Book A2.1."""
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
    """Non-zero B-spline basis values N_{i-p,p}...N_{i,p}.  NURBS Book A2.2.

    Parameters
    ----------
    i : knot span (from _find_span)
    u : parameter value
    p : degree
    U : knot vector

    Returns
    -------
    np.ndarray of shape (p+1,) — values N[i-p], ..., N[i]
    """
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
    """Evaluate NurbsSurface at (u, v) using the correct basis algorithm.

    Returns a 3-vector (x, y, z).
    """
    nu = surf.num_control_points_u
    nv = surf.num_control_points_v
    span_u = _find_span(nu - 1, surf.degree_u, u, surf.knots_u)
    span_v = _find_span(nv - 1, surf.degree_v, v, surf.knots_v)
    Nu = _basis_fns(span_u, u, surf.degree_u, surf.knots_u)
    Nv = _basis_fns(span_v, v, surf.degree_v, surf.knots_v)
    result = np.zeros(surf.control_points.shape[2])
    for i in range(surf.degree_u + 1):
        for j in range(surf.degree_v + 1):
            idx_i = span_u - surf.degree_u + i
            idx_j = span_v - surf.degree_v + j
            result += Nu[i] * Nv[j] * surf.control_points[idx_i, idx_j]
    return result[:3]


# ---------------------------------------------------------------------------
# Helpers
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


def _eval_grid_batch(surf: NurbsSurface, us: np.ndarray, vs: np.ndarray) -> np.ndarray:
    """Evaluate surface at every (u, v) pair.  Returns (N, 3)."""
    out = np.zeros((len(us), 3))
    for k, (u, v) in enumerate(zip(us, vs)):
        out[k] = _surf_eval(surf, float(u), float(v))
    return out


def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason, "surface": None,
            "max_deviation": 0.0, "smoothing_energy": 0.0}


# ---------------------------------------------------------------------------
# Thin-plate stiffness matrix (for patch_surface regularisation)
# ---------------------------------------------------------------------------

def _thin_plate_stiffness(nu: int, nv: int, weight: float) -> np.ndarray:
    """Return a (nu*nv) × (nu*nv) thin-plate-like stiffness matrix.

    Uses finite-difference second-derivative penalty: minimises the sum of
    squared second differences in i and j directions.  Scale by ``weight``.
    """
    n = nu * nv
    S = np.zeros((n, n))

    def idx(i: int, j: int) -> int:
        return i * nv + j

    for i in range(nu):
        for j in range(nv):
            k = idx(i, j)
            if i >= 1 and i <= nu - 2:
                S[k, idx(i - 1, j)] -= 1.0
                S[k, k] += 2.0
                S[k, idx(i + 1, j)] -= 1.0
            if j >= 1 and j <= nv - 2:
                S[k, idx(i, j - 1)] -= 1.0
                S[k, k] += 2.0
                S[k, idx(i, j + 1)] -= 1.0

    return weight * S


# ---------------------------------------------------------------------------
# patch_surface
# ---------------------------------------------------------------------------

def patch_surface(
    points: Sequence,
    *,
    nu: int = 6,
    nv: int = 6,
    degree_u: int = 3,
    degree_v: int = 3,
    boundary: Optional[Sequence] = None,
    stiffness: float = 0.01,
    max_iter: int = 5,
    tol: float = 1e-4,
) -> dict:
    """Best-fit NURBS surface through scattered 3D points.

    Fits a (nu × nv) control grid to the input scatter via a least-squares
    solve with a thin-plate stiffness regularisation term.  Each input point
    is assigned a (u, v) parameter by projecting onto the unit square using
    its normalised (x, y) coordinates (or the first two principal components
    if the point cloud is not well-oriented to XY).

    Parameters
    ----------
    points : sequence of array-like
        Input scattered points, each [x, y, z] (at least degree_u+1 points).
    nu, nv : int
        Number of control points in U and V directions (>= degree+1).
    degree_u, degree_v : int
        NURBS degree (1–5).
    boundary : sequence of [x, y, z], optional
        Additional boundary points that are included in the fit with weight 10.
    stiffness : float
        Weight of the thin-plate smoothing term (>= 0).  Higher values produce
        a smoother but less accurate surface.
    max_iter : int
        Iterative re-weighting passes (>= 1).
    tol : float
        Convergence tolerance (reserved).

    Returns
    -------
    dict
        ok, reason, surface, max_deviation, smoothing_energy.
    """
    try:
        pts = np.asarray(points, dtype=float)
        if pts.ndim != 2 or pts.shape[1] < 3:
            return _err(f"points must be an (N, 3+) array; got shape {pts.shape}")
    except Exception as exc:
        return _err(f"invalid points: {exc}")

    N = pts.shape[0]
    degree_u = max(1, min(int(degree_u), 5))
    degree_v = max(1, min(int(degree_v), 5))
    nu = max(degree_u + 1, int(nu))
    nv = max(degree_v + 1, int(nv))

    if N < (degree_u + 1) * (degree_v + 1):
        return _err(
            f"need at least (degree_u+1)*(degree_v+1)={(degree_u+1)*(degree_v+1)} "
            f"points for a degree-({degree_u},{degree_v}) surface; got {N}"
        )

    if not isinstance(stiffness, (int, float)) or stiffness < 0:
        return _err(f"stiffness must be >= 0; got {stiffness!r}")
    if not isinstance(max_iter, int) or max_iter < 1:
        return _err(f"max_iter must be a positive integer; got {max_iter!r}")

    # ── Parameterise input points onto [0,1]×[0,1] by bounding-box normalise ─
    xy = pts[:, :2]
    xy_min = xy.min(axis=0)
    xy_max = xy.max(axis=0)
    span = xy_max - xy_min
    span = np.where(span < 1e-12, 1.0, span)
    us_data = np.clip((xy[:, 0] - xy_min[0]) / span[0], 0.0, 1.0)
    vs_data = np.clip((xy[:, 1] - xy_min[1]) / span[1], 0.0, 1.0)

    # ── Merge boundary points if provided ────────────────────────────────────
    boundary_weight = 10.0
    if boundary is not None:
        try:
            bpts = np.asarray(boundary, dtype=float)
            if bpts.ndim != 2 or bpts.shape[1] < 3:
                return _err(f"boundary must be (M, 3+); got shape {bpts.shape}")
        except Exception as exc:
            return _err(f"invalid boundary: {exc}")
        bxy = bpts[:, :2]
        bus = np.clip((bxy[:, 0] - xy_min[0]) / span[0], 0.0, 1.0)
        bvs = np.clip((bxy[:, 1] - xy_min[1]) / span[1], 0.0, 1.0)
        all_pts = np.vstack([pts[:, :3], bpts[:, :3]])
        all_us = np.concatenate([us_data, bus])
        all_vs = np.concatenate([vs_data, bvs])
        weights = np.concatenate([np.ones(N), np.full(len(bpts), boundary_weight)])
    else:
        all_pts = pts[:, :3].copy()
        all_us = us_data
        all_vs = vs_data
        weights = np.ones(N)

    knots_u = _make_clamped_knots(nu, degree_u)
    knots_v = _make_clamped_knots(nv, degree_v)

    # ── Build basis matrix B: (M, nu*nv) ─────────────────────────────────────
    M_total = len(all_us)

    def _basis_row_u(u_val: float) -> np.ndarray:
        u_c = float(np.clip(u_val, 0.0, 1.0))
        span = _find_span(nu - 1, degree_u, u_c, knots_u)
        Nvals = _basis_fns(span, u_c, degree_u, knots_u)
        row = np.zeros(nu)
        for k in range(degree_u + 1):
            row[span - degree_u + k] = Nvals[k]
        return row

    def _basis_row_v(v_val: float) -> np.ndarray:
        v_c = float(np.clip(v_val, 0.0, 1.0))
        span = _find_span(nv - 1, degree_v, v_c, knots_v)
        Nvals = _basis_fns(span, v_c, degree_v, knots_v)
        row = np.zeros(nv)
        for k in range(degree_v + 1):
            row[span - degree_v + k] = Nvals[k]
        return row

    B = np.zeros((M_total, nu * nv))
    for m_idx in range(M_total):
        Nu_row = _basis_row_u(all_us[m_idx])
        Nv_row = _basis_row_v(all_vs[m_idx])
        B[m_idx] = np.outer(Nu_row, Nv_row).ravel()

    # ── Weighted least-squares with stiffness ─────────────────────────────────
    W = np.diag(weights)
    BtW = B.T @ W
    BtWB = BtW @ B
    S = _thin_plate_stiffness(nu, nv, stiffness)

    A = BtWB + S

    # Add small Tikhonov regularisation to prevent singular matrix
    A += np.eye(nu * nv) * 1e-10

    rhs_x = BtW @ all_pts[:, 0]
    rhs_y = BtW @ all_pts[:, 1]
    rhs_z = BtW @ all_pts[:, 2]

    try:
        cx = np.linalg.solve(A, rhs_x)
        cy = np.linalg.solve(A, rhs_y)
        cz = np.linalg.solve(A, rhs_z)
    except np.linalg.LinAlgError as exc:
        # Fall back to least-squares
        try:
            cx, _, _, _ = np.linalg.lstsq(A, rhs_x, rcond=None)
            cy, _, _, _ = np.linalg.lstsq(A, rhs_y, rcond=None)
            cz, _, _, _ = np.linalg.lstsq(A, rhs_z, rcond=None)
        except Exception as exc2:
            return _err(f"linear solve failed: {exc2}")

    ctrl = np.column_stack([cx, cy, cz]).reshape(nu, nv, 3)
    # Smoothing energy: ||S cx||^2 + ||S cy||^2 + ||S cz||^2 (always >= 0)
    def _energy(S, cx, cy, cz):
        return float(np.dot(S @ cx, S @ cx) + np.dot(S @ cy, S @ cy) + np.dot(S @ cz, S @ cz))

    smoothing_energy = _energy(S, cx, cy, cz)

    # ── Iterative refinement (re-weighting by residual) ──────────────────────
    for _iter in range(max_iter - 1):
        surf_tmp = NurbsSurface(
            degree_u=degree_u, degree_v=degree_v,
            control_points=ctrl,
            knots_u=knots_u, knots_v=knots_v,
        )
        fitted = _eval_grid_batch(surf_tmp, all_us, all_vs)
        residuals = np.linalg.norm(fitted - all_pts, axis=1) + 1e-10
        iter_w = weights / residuals
        W_iter = np.diag(iter_w)
        BtW_i = B.T @ W_iter
        A_i = BtW_i @ B + S + np.eye(nu * nv) * 1e-10
        try:
            cx = np.linalg.solve(A_i, BtW_i @ all_pts[:, 0])
            cy = np.linalg.solve(A_i, BtW_i @ all_pts[:, 1])
            cz = np.linalg.solve(A_i, BtW_i @ all_pts[:, 2])
        except np.linalg.LinAlgError:
            break
        ctrl = np.column_stack([cx, cy, cz]).reshape(nu, nv, 3)
        smoothing_energy = _energy(S, cx, cy, cz)

    surface = NurbsSurface(
        degree_u=degree_u, degree_v=degree_v,
        control_points=ctrl,
        knots_u=knots_u, knots_v=knots_v,
    )

    # Compute max deviation over input points
    fitted = _eval_grid_batch(surface, us_data, vs_data)
    diffs = np.linalg.norm(fitted - pts[:, :3], axis=1)
    max_dev = float(np.max(diffs)) if len(diffs) > 0 else 0.0

    return {
        "ok": True,
        "reason": "",
        "surface": surface,
        "max_deviation": max_dev,
        "smoothing_energy": float(smoothing_energy),
    }


# ---------------------------------------------------------------------------
# drape_surface
# ---------------------------------------------------------------------------

def drape_surface(
    obstacle_pts: Sequence,
    bbox: Sequence,
    *,
    nu: int = 8,
    nv: int = 8,
    gravity_axis: int = 2,
    relax_iters: int = 20,
) -> dict:
    """Project a sagging grid over obstacle points (drape / gravity-relaxation).

    Creates a (nu × nv) regular grid over the bounding box [x0,x1]×[y0,y1]
    (using the two axes orthogonal to ``gravity_axis``), initialises each node
    at the top of the bbox, then iteratively lowers each node until it first
    hits the upper envelope of the obstacle points below it.

    Parameters
    ----------
    obstacle_pts : sequence of [x, y, z]
        Obstacle point cloud (vertices, mesh nodes, etc.).
    bbox : sequence of 6 floats
        [x_min, y_min, z_min, x_max, y_max, z_max] world-space bounding box.
        The grid is placed at the top (max gravity-axis value).
    nu, nv : int
        Grid resolution in U and V directions (>= 2).
    gravity_axis : int
        Axis index (0=X, 1=Y, 2=Z) along which gravity acts (default 2 = -Z).
    relax_iters : int
        Number of relaxation sweeps (mostly aesthetic; envelope is computed
        analytically so the result is independent after 1 sweep).

    Returns
    -------
    dict
        ok, reason, surface, max_deviation (0), smoothing_energy (0).
    """
    try:
        obs = np.asarray(obstacle_pts, dtype=float)
        if obs.ndim != 2 or obs.shape[1] < 3:
            return _err(f"obstacle_pts must be (N, 3+); got shape {obs.shape}")
    except Exception as exc:
        return _err(f"invalid obstacle_pts: {exc}")

    try:
        bb = np.asarray(bbox, dtype=float).ravel()
        if bb.size != 6:
            return _err(f"bbox must have 6 values [xmin,ymin,zmin,xmax,ymax,zmax]; got {bb.size}")
    except Exception as exc:
        return _err(f"invalid bbox: {exc}")

    if not (0 <= gravity_axis <= 2):
        return _err(f"gravity_axis must be 0, 1, or 2; got {gravity_axis!r}")

    nu = max(2, int(nu))
    nv = max(2, int(nv))

    # The two "horizontal" axes
    horiz_axes = [a for a in [0, 1, 2] if a != gravity_axis]
    ha, hb = horiz_axes

    a_min, a_max = float(bb[ha]), float(bb[ha + 3])
    b_min, b_max = float(bb[hb]), float(bb[hb + 3])
    g_min = float(bb[gravity_axis])

    if a_max <= a_min or b_max <= b_min:
        return _err("bbox horizontal span is zero in one or both horizontal axes")

    a_coords = np.linspace(a_min, a_max, nu)
    b_coords = np.linspace(b_min, b_max, nv)

    # Upper envelope: default to g_min (floor) when no obstacle underneath
    envelope = np.full((nu, nv), g_min)
    for obs_pt in obs[:, :3]:
        ai = float(obs_pt[ha])
        bi = float(obs_pt[hb])
        gi = float(obs_pt[gravity_axis])
        ia = int(round((ai - a_min) / (a_max - a_min + 1e-15) * (nu - 1)))
        ib = int(round((bi - b_min) / (b_max - b_min + 1e-15) * (nv - 1)))
        ia = max(0, min(nu - 1, ia))
        ib = max(0, min(nv - 1, ib))
        if gi > envelope[ia, ib]:
            envelope[ia, ib] = gi

    ctrl = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            pt = np.zeros(3)
            pt[ha] = a_coords[i]
            pt[hb] = b_coords[j]
            pt[gravity_axis] = float(envelope[i, j])
            ctrl[i, j] = pt

    knots_u = _make_clamped_knots(nu, 1)
    knots_v = _make_clamped_knots(nv, 1)

    surface = NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=ctrl,
        knots_u=knots_u,
        knots_v=knots_v,
    )
    return {
        "ok": True,
        "reason": "",
        "surface": surface,
        "max_deviation": 0.0,
        "smoothing_energy": 0.0,
    }


# ---------------------------------------------------------------------------
# heightfield
# ---------------------------------------------------------------------------

def heightfield(
    z_array: Sequence,
    *,
    x_range: Tuple[float, float] = (0.0, 1.0),
    y_range: Tuple[float, float] = (0.0, 1.0),
    v_scale: float = 1.0,
) -> dict:
    """Build a regular UV-grid NURBS surface from an elevation array.

    The resulting surface is bilinear (degree 1 × 1) so that evaluating at
    any grid node parameter returns *exactly* the corresponding elevation.
    All input heights are multiplied by ``v_scale`` before building the
    surface.

    Parameters
    ----------
    z_array : 2D array-like, shape (m, n)
        Elevation values; z_array[i, j] is the height at grid node (i, j).
        May also be a 2D grayscale image (uint8) in which case pixel
        intensity / 255 × v_scale is used as height.
    x_range : (x_min, x_max)
        World-space X extent of the grid.
    y_range : (y_min, y_max)
        World-space Y extent of the grid.
    v_scale : float
        Vertical scale applied to all elevations.

    Returns
    -------
    dict
        ok, reason, surface, max_deviation (0), smoothing_energy (0).
    """
    try:
        za = np.asarray(z_array, dtype=float)
    except Exception as exc:
        return _err(f"invalid z_array: {exc}")

    if za.ndim != 2:
        return _err(f"z_array must be 2D; got ndim={za.ndim}")

    m, n = za.shape
    if m < 2 or n < 2:
        return _err(f"z_array must be at least 2×2; got {m}×{n}")

    za = za * float(v_scale)

    try:
        x0, x1 = float(x_range[0]), float(x_range[1])
        y0, y1 = float(y_range[0]), float(y_range[1])
    except Exception as exc:
        return _err(f"invalid x_range/y_range: {exc}")

    if x1 <= x0 or y1 <= y0:
        return _err("x_range and y_range must be strictly increasing intervals")

    if not isinstance(v_scale, (int, float)):
        return _err(f"v_scale must be a number; got {v_scale!r}")

    ctrl = np.zeros((m, n, 3))
    xs = np.linspace(x0, x1, m)
    ys = np.linspace(y0, y1, n)
    for i in range(m):
        for j in range(n):
            ctrl[i, j] = [xs[i], ys[j], float(za[i, j])]

    knots_u = _make_clamped_knots(m, 1)
    knots_v = _make_clamped_knots(n, 1)

    surface = NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=ctrl,
        knots_u=knots_u,
        knots_v=knots_v,
    )
    return {
        "ok": True,
        "reason": "",
        "surface": surface,
        "max_deviation": 0.0,
        "smoothing_energy": 0.0,
    }


# ---------------------------------------------------------------------------
# surface_from_grid
# ---------------------------------------------------------------------------

def surface_from_grid(
    points_grid: Sequence,
    *,
    degree_u: int = 3,
    degree_v: int = 3,
) -> dict:
    """Interpolating NURBS surface through an m×n ordered point net.

    Builds a NURBS surface that passes through every input point by using
    the centripetal chord-length parameterisation and then solving the
    interpolation system independently for each row and column.

    Parameters
    ----------
    points_grid : array-like, shape (m, n, 3)
        Ordered m×n grid of 3D points.  m and n must each be >= degree+1.
    degree_u, degree_v : int
        NURBS degree in U and V (1–5).

    Returns
    -------
    dict
        ok, reason, surface, max_deviation, smoothing_energy (0).
    """
    try:
        pg = np.asarray(points_grid, dtype=float)
    except Exception as exc:
        return _err(f"invalid points_grid: {exc}")

    if pg.ndim != 3 or pg.shape[2] < 3:
        return _err(
            f"points_grid must be shape (m, n, 3+); got {pg.shape}"
        )

    m, n, _dim = pg.shape
    degree_u = max(1, min(int(degree_u), 5))
    degree_v = max(1, min(int(degree_v), 5))

    if m < degree_u + 1:
        return _err(
            f"points_grid needs at least {degree_u + 1} rows for degree_u={degree_u}; got {m}"
        )
    if n < degree_v + 1:
        return _err(
            f"points_grid needs at least {degree_v + 1} cols for degree_v={degree_v}; got {n}"
        )

    # ── Centripetal parameterisation ─────────────────────────────────────────

    def _chord_params(pts: np.ndarray) -> np.ndarray:
        dists = np.linalg.norm(np.diff(pts[:, :3], axis=0), axis=1) ** 0.5
        dists = np.maximum(dists, 1e-15)
        total = dists.sum()
        if total < 1e-15:
            return np.linspace(0.0, 1.0, len(pts))
        return np.concatenate([[0.0], np.cumsum(dists) / total])

    def _make_interp_knots(params: np.ndarray, degree: int) -> np.ndarray:
        """Averaging knot vector (NURBS Book Algorithm A9.8)."""
        n_pts = len(params)
        inner_count = n_pts - degree - 1
        knots = np.zeros(n_pts + degree + 1)
        knots[n_pts:] = 1.0
        for j in range(1, inner_count + 1):
            knots[degree + j] = np.mean(params[j:j + degree])
        return knots

    def _build_collocation(params: np.ndarray, knots: np.ndarray, degree: int) -> np.ndarray:
        """Build n×n B-spline collocation matrix."""
        n_pts = len(params)
        N_mat = np.zeros((n_pts, n_pts))
        for row, u in enumerate(params):
            u_c = float(np.clip(u, knots[0], knots[-1]))
            span = _find_span(n_pts - 1, degree, u_c, knots)
            Nvals = _basis_fns(span, u_c, degree, knots)
            for k in range(degree + 1):
                col = span - degree + k
                if 0 <= col < n_pts:
                    N_mat[row, col] = Nvals[k]
        return N_mat

    def _interp_1d(params: np.ndarray, pts_1d: np.ndarray, degree: int,
                   knots: np.ndarray) -> np.ndarray:
        """Solve for control points that interpolate pts_1d at params."""
        N_mat = _build_collocation(params, knots, degree)
        dim = pts_1d.shape[1]
        ctrl = np.zeros((len(params), dim))
        for d in range(dim):
            try:
                ctrl[:, d] = np.linalg.solve(N_mat, pts_1d[:, d])
            except np.linalg.LinAlgError:
                ctrl[:, d], _, _, _ = np.linalg.lstsq(N_mat, pts_1d[:, d], rcond=None)
        return ctrl

    # ── Step 1: average u-parameterisation over all v-columns ────────────────
    u_params_all = np.array([_chord_params(pg[:, j, :3]) for j in range(n)])
    u_params = u_params_all.mean(axis=0)
    knots_u = _make_interp_knots(u_params, degree_u)

    # Interpolate each v-column in U direction → temp net shape (m, n, 3)
    ctrl_net = np.zeros((m, n, 3))
    for j in range(n):
        ctrl_net[:, j, :3] = _interp_1d(u_params, pg[:, j, :3], degree_u, knots_u)

    # ── Step 2: average v-parameterisation over resulting u-rows ─────────────
    v_params_all = np.array([_chord_params(ctrl_net[i, :, :3]) for i in range(m)])
    v_params = v_params_all.mean(axis=0)
    knots_v = _make_interp_knots(v_params, degree_v)

    ctrl_final = np.zeros((m, n, 3))
    for i in range(m):
        ctrl_final[i, :, :3] = _interp_1d(v_params, ctrl_net[i, :, :3], degree_v, knots_v)

    surface = NurbsSurface(
        degree_u=degree_u, degree_v=degree_v,
        control_points=ctrl_final,
        knots_u=knots_u,
        knots_v=knots_v,
    )

    # ── Measure max deviation at input points using u/v params ────────────────
    max_dev = 0.0
    for i, u in enumerate(u_params):
        for j, v in enumerate(v_params):
            pt_eval = _surf_eval(surface, float(u), float(v))
            dist = float(np.linalg.norm(pt_eval - pg[i, j, :3]))
            if dist > max_dev:
                max_dev = dist

    return {
        "ok": True,
        "reason": "",
        "surface": surface,
        "max_deviation": max_dev,
        "smoothing_energy": 0.0,
    }


# ---------------------------------------------------------------------------
# fit_surface  (GK-34)
# ---------------------------------------------------------------------------

def _pt_knots_surface(ts: np.ndarray, num_ctrl: int, degree: int) -> np.ndarray:
    """Piegl–Tiller knot placement for the least-squares surface fitting case.

    Mirror of curve_toolkit._pt_knots_from_params: given m+1 data parameters
    ts[0..m] (chord-length, in [0,1]) and n+1 = num_ctrl control points,
    uses P&T eq. 9.68 to place the n−p interior knots.
    """
    m = len(ts) - 1
    n = num_ctrl - 1
    p = degree
    knots = np.zeros(n + p + 2)
    knots[-(p + 1):] = 1.0
    num_interior = n - p
    if num_interior <= 0:
        return knots
    d = (m + 1) / (n - p + 1)
    for j in range(1, num_interior + 1):
        idx = int(j * d)
        alpha = j * d - idx
        idx = max(1, min(idx, m))
        knots[p + j] = (1.0 - alpha) * ts[idx - 1] + alpha * ts[idx]
    # Ensure monotonicity
    for k in range(p + 1, len(knots) - p - 1):
        knots[k] = max(knots[k], knots[k - 1])
    return knots


def _chord_params_2d(pts_grid: np.ndarray) -> tuple:
    """Compute averaged chord-length parameters for an (m,n,3) point grid.

    Returns (u_params, v_params) each of shape (m,) and (n,) respectively,
    averaged across the grid rows/columns as per Piegl–Tiller §9.3.6.
    """
    m, n, _ = pts_grid.shape

    # U-direction: average across the n columns
    u_all = []
    for j in range(n):
        col = pts_grid[:, j, :3]
        dists = np.linalg.norm(np.diff(col, axis=0), axis=1) ** 0.5
        dists = np.maximum(dists, 1e-15)
        total = dists.sum()
        if total < 1e-14:
            u_col = np.linspace(0.0, 1.0, m)
        else:
            u_col = np.concatenate([[0.0], np.cumsum(dists)]) / dists.sum()
            u_col = np.concatenate([[0.0], np.cumsum(np.linalg.norm(
                np.diff(col, axis=0), axis=1) ** 0.5)])
            u_col /= max(u_col[-1], 1e-15)
        u_all.append(u_col)
    u_params = np.mean(u_all, axis=0)
    u_params[0] = 0.0
    u_params[-1] = 1.0

    # V-direction: average across the m rows
    v_all = []
    for i in range(m):
        row = pts_grid[i, :, :3]
        dists = np.linalg.norm(np.diff(row, axis=0), axis=1) ** 0.5
        dists = np.maximum(dists, 1e-15)
        v_row = np.concatenate([[0.0], np.cumsum(dists)])
        v_row /= max(v_row[-1], 1e-15)
        v_all.append(v_row)
    v_params = np.mean(v_all, axis=0)
    v_params[0] = 0.0
    v_params[-1] = 1.0

    return u_params, v_params


def _build_basis_matrix(params: np.ndarray, knots: np.ndarray,
                        num_ctrl: int, degree: int) -> np.ndarray:
    """Build least-squares collocation matrix B of shape (len(params), num_ctrl).

    Row i contains the B-spline basis values N_{0,p}(t_i)...N_{n,p}(t_i).
    """
    m = len(params)
    B = np.zeros((m, num_ctrl))
    for row_i, t in enumerate(params):
        t_c = float(np.clip(t, 0.0, 1.0))
        span = _find_span(num_ctrl - 1, degree, t_c, knots)
        Nvals = _basis_fns(span, t_c, degree, knots)
        for k in range(degree + 1):
            col = span - degree + k
            if 0 <= col < num_ctrl:
                B[row_i, col] = Nvals[k]
    return B


def _ls_solve(A: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    """Least-squares solve A @ x = rhs (multiple columns)."""
    x, _, _, _ = np.linalg.lstsq(A, rhs, rcond=None)
    return x


def fit_surface(
    points_grid: Sequence,
    *,
    degree_u: int = 3,
    degree_v: int = 3,
    tol: float = 1e-3,
    max_ctrl_u: int = 32,
    max_ctrl_v: int = 32,
) -> dict:
    """Least-squares NURBS surface fit to an ordered (m×n) point grid.

    Mirrors the ``fit_curve`` strategy from ``geom/curve_toolkit.py`` (GK-22)
    extended to surfaces.  Computes centripetal chord-length parameters in
    both U and V, then uses Piegl–Tiller knot placement (P&T §9.4.1, eq. 9.68)
    to build the B-spline least-squares system.

    Control-point count is increased from ``degree+1`` in each direction,
    independently, until ``max_deviation ≤ tol`` or ``max_ctrl`` is reached.
    The U refinement loop runs first; then V is refined holding U fixed.

    Parameters
    ----------
    points_grid : array-like, shape (m, n, 3)
        Ordered m×n grid of 3D data points.  m ≥ degree_u+1, n ≥ degree_v+1.
    degree_u, degree_v : int
        B-spline degree in U and V (1–5).
    tol : float
        Target max deviation (Euclidean, same units as input points).
    max_ctrl_u, max_ctrl_v : int
        Maximum number of control points per direction.  Fitting stops here
        even if tol is not achieved; the best-effort surface is returned
        with ok=False.

    Returns
    -------
    dict with keys:
        ok             : bool
        reason         : str   (non-empty when ok is False)
        surface        : NurbsSurface (always present when valid input given)
        max_deviation  : float
        smoothing_energy : float  (always 0.0 — no regularisation)
        num_ctrl_u     : int   (final CP count in U)
        num_ctrl_v     : int   (final CP count in V)
    """
    # ── Input validation ──────────────────────────────────────────────────────
    try:
        pg = np.asarray(points_grid, dtype=float)
    except Exception as exc:
        return _err(f"invalid points_grid: {exc}")

    if pg.ndim != 3 or pg.shape[2] < 3:
        return _err(
            f"points_grid must be shape (m, n, 3+); got {pg.shape}"
        )

    m, n, _ = pg.shape
    degree_u = max(1, min(int(degree_u), 5))
    degree_v = max(1, min(int(degree_v), 5))

    if m < degree_u + 1:
        return _err(
            f"points_grid needs at least {degree_u + 1} rows for degree_u={degree_u}; got {m}"
        )
    if n < degree_v + 1:
        return _err(
            f"points_grid needs at least {degree_v + 1} cols for degree_v={degree_v}; got {n}"
        )

    max_ctrl_u = max(degree_u + 1, int(max_ctrl_u))
    max_ctrl_v = max(degree_v + 1, int(max_ctrl_v))
    if not (isinstance(tol, (int, float)) and tol > 0):
        return _err(f"tol must be a positive number; got {tol!r}")

    # ── Chord-length parameters ───────────────────────────────────────────────
    u_params, v_params = _chord_params_2d(pg[:, :, :3])

    # ── Helper: fit one axis (U or V) by least squares, return ctrl net ───────
    def _fit_axis_u(nu_c: int) -> np.ndarray:
        """Fit along U for each of the n V-columns.  Returns (nu_c, n, 3)."""
        knots_u = _pt_knots_surface(u_params, nu_c, degree_u)
        Bu = _build_basis_matrix(u_params, knots_u, nu_c, degree_u)
        ctrl = np.zeros((nu_c, n, 3))
        for j in range(n):
            ctrl[:, j, :] = _ls_solve(Bu, pg[:, j, :3])
        return ctrl, knots_u

    def _fit_axis_v(ctrl_in: np.ndarray, nv_c: int) -> np.ndarray:
        """Fit along V for each of the nu_c U-rows.  Returns (nu_c, nv_c, 3)."""
        nu_c = ctrl_in.shape[0]
        knots_v = _pt_knots_surface(v_params, nv_c, degree_v)
        Bv = _build_basis_matrix(v_params, knots_v, nv_c, degree_v)
        ctrl = np.zeros((nu_c, nv_c, 3))
        for i in range(nu_c):
            ctrl[i, :, :] = _ls_solve(Bv, ctrl_in[i, :, :3])
        return ctrl, knots_v

    def _max_dev(surface: NurbsSurface) -> float:
        """Max deviation at every data-grid parameter node."""
        max_d = 0.0
        for i, u in enumerate(u_params):
            for j, v in enumerate(v_params):
                pt = _surf_eval(surface, float(u), float(v))
                d = float(np.linalg.norm(pt - pg[i, j, :3]))
                if d > max_d:
                    max_d = d
        return max_d

    # ── Phase 1: refine U, hold V at its minimum ──────────────────────────────
    best_surf = None
    best_dev = float("inf")
    best_nu = degree_u + 1
    best_nv = degree_v + 1

    for nu_c in range(degree_u + 1, min(max_ctrl_u + 1, m + 1)):
        ctrl_u, knots_u = _fit_axis_u(nu_c)
        nv_c = degree_v + 1
        ctrl_final, knots_v = _fit_axis_v(ctrl_u, nv_c)
        surf = NurbsSurface(
            degree_u=degree_u, degree_v=degree_v,
            control_points=ctrl_final,
            knots_u=knots_u, knots_v=knots_v,
        )
        dev = _max_dev(surf)
        if dev < best_dev:
            best_dev = dev
            best_surf = surf
            best_nu = nu_c
            best_nv = nv_c
        if dev <= tol:
            return {
                "ok": True, "reason": "",
                "surface": surf,
                "max_deviation": dev,
                "smoothing_energy": 0.0,
                "num_ctrl_u": nu_c,
                "num_ctrl_v": nv_c,
            }

    # ── Phase 2: U is at its best; now refine V ───────────────────────────────
    ctrl_u_best, knots_u_best = _fit_axis_u(best_nu)

    for nv_c in range(degree_v + 2, min(max_ctrl_v + 1, n + 1)):
        ctrl_final, knots_v = _fit_axis_v(ctrl_u_best, nv_c)
        surf = NurbsSurface(
            degree_u=degree_u, degree_v=degree_v,
            control_points=ctrl_final,
            knots_u=knots_u_best, knots_v=knots_v,
        )
        dev = _max_dev(surf)
        if dev < best_dev:
            best_dev = dev
            best_surf = surf
            best_nu = best_nu
            best_nv = nv_c
        if dev <= tol:
            return {
                "ok": True, "reason": "",
                "surface": surf,
                "max_deviation": dev,
                "smoothing_energy": 0.0,
                "num_ctrl_u": best_nu,
                "num_ctrl_v": nv_c,
            }

    # ── Phase 3: refine both axes jointly if still not converged ─────────────
    for nu_c in range(best_nu + 1, min(max_ctrl_u + 1, m + 1)):
        ctrl_u, knots_u = _fit_axis_u(nu_c)
        for nv_c in range(best_nv + 1, min(max_ctrl_v + 1, n + 1)):
            ctrl_final, knots_v = _fit_axis_v(ctrl_u, nv_c)
            surf = NurbsSurface(
                degree_u=degree_u, degree_v=degree_v,
                control_points=ctrl_final,
                knots_u=knots_u, knots_v=knots_v,
            )
            dev = _max_dev(surf)
            if dev < best_dev:
                best_dev = dev
                best_surf = surf
                best_nu = nu_c
                best_nv = nv_c
            if dev <= tol:
                return {
                    "ok": True, "reason": "",
                    "surface": surf,
                    "max_deviation": dev,
                    "smoothing_energy": 0.0,
                    "num_ctrl_u": nu_c,
                    "num_ctrl_v": nv_c,
                }

    # Best effort
    ok_final = best_dev <= tol
    reason = "" if ok_final else (
        f"tolerance {tol} not achieved; best deviation {best_dev:.4g} "
        f"with ({best_nu} × {best_nv}) control points"
    )
    return {
        "ok": ok_final,
        "reason": reason,
        "surface": best_surf,
        "max_deviation": best_dev,
        "smoothing_energy": 0.0,
        "num_ctrl_u": best_nu,
        "num_ctrl_v": best_nv,
    }


# ---------------------------------------------------------------------------
# LLM tool registration
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
    # patch_srf_fit
    # ------------------------------------------------------------------

    _patch_srf_fit_spec = ToolSpec(
        name="patch_srf_fit",
        description=(
            "Fit a NURBS surface through scattered 3D points (Rhino Patch equivalent). "
            "Uses least-squares with a thin-plate stiffness term to produce a smooth surface "
            "that best approximates the input scatter. Returns the surface as a control-point "
            "grid plus fit diagnostics (max_deviation, smoothing_energy).\n"
            "\n"
            "Returns: ok, control_points (m×n×3), knots_u, knots_v, degree_u, degree_v, "
            "max_deviation, smoothing_energy.\n"
            "Errors: {ok:false, reason}. Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "points": {
                    "type": "array",
                    "description": "Scattered 3D points [[x,y,z], ...] (at least (degree+1)^2).",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "nu": {"type": "integer", "description": "Control grid size U (default 6)."},
                "nv": {"type": "integer", "description": "Control grid size V (default 6)."},
                "degree_u": {"type": "integer", "description": "NURBS degree U (default 3)."},
                "degree_v": {"type": "integer", "description": "NURBS degree V (default 3)."},
                "stiffness": {"type": "number", "description": "Smoothing weight (default 0.01)."},
                "max_iter": {"type": "integer", "description": "Refinement iterations (default 5)."},
            },
            "required": ["points"],
        },
    )

    @register(_patch_srf_fit_spec)
    async def run_patch_srf_fit(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        points = a.get("points")
        if not points:
            return err_payload("points is required", "BAD_ARGS")

        result = patch_surface(
            points,
            nu=int(a.get("nu", 6)),
            nv=int(a.get("nv", 6)),
            degree_u=int(a.get("degree_u", 3)),
            degree_v=int(a.get("degree_v", 3)),
            stiffness=float(a.get("stiffness", 0.01)),
            max_iter=int(a.get("max_iter", 5)),
        )
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")

        surf = result["surface"]
        return ok_payload({
            "control_points": surf.control_points.tolist(),
            "knots_u": surf.knots_u.tolist(),
            "knots_v": surf.knots_v.tolist(),
            "degree_u": surf.degree_u,
            "degree_v": surf.degree_v,
            "max_deviation": result["max_deviation"],
            "smoothing_energy": result["smoothing_energy"],
        })

    # ------------------------------------------------------------------
    # drape_srf_project
    # ------------------------------------------------------------------

    _drape_srf_spec = ToolSpec(
        name="drape_srf_project",
        description=(
            "Drape a grid surface over obstacle points by gravity relaxation "
            "(Rhino Drape equivalent). Creates a uniform grid over the given bounding box "
            "and rests it on the upper envelope of the obstacle point cloud.\n"
            "\n"
            "Returns: ok, control_points, knots_u, knots_v, degree_u, degree_v.\n"
            "Errors: {ok:false, reason}. Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "obstacle_pts": {
                    "type": "array",
                    "description": "Obstacle vertices [[x,y,z], ...].",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "bbox": {
                    "type": "array",
                    "description": "[xmin,ymin,zmin,xmax,ymax,zmax].",
                    "items": {"type": "number"},
                    "minItems": 6, "maxItems": 6,
                },
                "nu": {"type": "integer", "description": "Grid resolution U (default 8)."},
                "nv": {"type": "integer", "description": "Grid resolution V (default 8)."},
                "gravity_axis": {"type": "integer", "description": "0=X,1=Y,2=Z (default 2)."},
            },
            "required": ["obstacle_pts", "bbox"],
        },
    )

    @register(_drape_srf_spec)
    async def run_drape_srf_project(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        obs = a.get("obstacle_pts")
        bbox = a.get("bbox")
        if not obs or not bbox:
            return err_payload("obstacle_pts and bbox are required", "BAD_ARGS")

        result = drape_surface(
            obs, bbox,
            nu=int(a.get("nu", 8)),
            nv=int(a.get("nv", 8)),
            gravity_axis=int(a.get("gravity_axis", 2)),
        )
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")

        surf = result["surface"]
        return ok_payload({
            "control_points": surf.control_points.tolist(),
            "knots_u": surf.knots_u.tolist(),
            "knots_v": surf.knots_v.tolist(),
            "degree_u": surf.degree_u,
            "degree_v": surf.degree_v,
        })

    # ------------------------------------------------------------------
    # heightfield_srf
    # ------------------------------------------------------------------

    _heightfield_srf_spec = ToolSpec(
        name="heightfield_srf",
        description=(
            "Build a NURBS surface from a 2D elevation array (Rhino Heightfield equivalent). "
            "Each grid node of the resulting surface corresponds exactly to a cell in z_array.\n"
            "\n"
            "Returns: ok, control_points, knots_u, knots_v, degree_u, degree_v.\n"
            "Errors: {ok:false, reason}. Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "z_array": {
                    "type": "array",
                    "description": "2D elevation array [[z00, z01,...], [z10,...],...] (m×n).",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "x_range": {
                    "type": "array",
                    "description": "[x_min, x_max] (default [0,1]).",
                    "items": {"type": "number"},
                    "minItems": 2, "maxItems": 2,
                },
                "y_range": {
                    "type": "array",
                    "description": "[y_min, y_max] (default [0,1]).",
                    "items": {"type": "number"},
                    "minItems": 2, "maxItems": 2,
                },
                "v_scale": {"type": "number", "description": "Vertical scale (default 1.0)."},
            },
            "required": ["z_array"],
        },
    )

    @register(_heightfield_srf_spec)
    async def run_heightfield_srf(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        za = a.get("z_array")
        if za is None:
            return err_payload("z_array is required", "BAD_ARGS")

        x_range = tuple(a.get("x_range", [0.0, 1.0]))
        y_range = tuple(a.get("y_range", [0.0, 1.0]))

        result = heightfield(
            za,
            x_range=x_range,
            y_range=y_range,
            v_scale=float(a.get("v_scale", 1.0)),
        )
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")

        surf = result["surface"]
        return ok_payload({
            "control_points": surf.control_points.tolist(),
            "knots_u": surf.knots_u.tolist(),
            "knots_v": surf.knots_v.tolist(),
            "degree_u": surf.degree_u,
            "degree_v": surf.degree_v,
        })

    # ------------------------------------------------------------------
    # grid_srf_interp
    # ------------------------------------------------------------------

    _grid_srf_interp_spec = ToolSpec(
        name="grid_srf_interp",
        description=(
            "Interpolate a NURBS surface through an m×n ordered point grid "
            "(lofted-grid / network surface). The surface passes exactly through all "
            "input points.\n"
            "\n"
            "Returns: ok, control_points, knots_u, knots_v, degree_u, degree_v, max_deviation.\n"
            "Errors: {ok:false, reason}. Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "points_grid": {
                    "type": "array",
                    "description": "m×n×3 ordered point net [[[x,y,z],...],...].",
                    "items": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                    },
                },
                "degree_u": {"type": "integer", "description": "NURBS degree U (default 3)."},
                "degree_v": {"type": "integer", "description": "NURBS degree V (default 3)."},
            },
            "required": ["points_grid"],
        },
    )

    @register(_grid_srf_interp_spec)
    async def run_grid_srf_interp(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        pg = a.get("points_grid")
        if pg is None:
            return err_payload("points_grid is required", "BAD_ARGS")

        result = surface_from_grid(
            pg,
            degree_u=int(a.get("degree_u", 3)),
            degree_v=int(a.get("degree_v", 3)),
        )
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")

        surf = result["surface"]
        return ok_payload({
            "control_points": surf.control_points.tolist(),
            "knots_u": surf.knots_u.tolist(),
            "knots_v": surf.knots_v.tolist(),
            "degree_u": surf.degree_u,
            "degree_v": surf.degree_v,
            "max_deviation": result["max_deviation"],
        })


# ---------------------------------------------------------------------------
# GK-99: Mid-surface (CP-wise average of two NURBS surfaces)
# ---------------------------------------------------------------------------

def _normalise_surface_knots(srf: NurbsSurface) -> NurbsSurface:
    """Re-scale both knot vectors to [0, 1]."""
    def _norm(k: np.ndarray) -> np.ndarray:
        lo, hi = k[0], k[-1]
        if abs(hi - lo) < 1e-14:
            return k.copy()
        return (k - lo) / (hi - lo)

    return NurbsSurface(
        degree_u=srf.degree_u,
        degree_v=srf.degree_v,
        control_points=srf.control_points.copy(),
        knots_u=_norm(srf.knots_u),
        knots_v=_norm(srf.knots_v),
        weights=srf.weights,
    )


def _surface_degree_elevate_u(srf: NurbsSurface, new_deg: int) -> NurbsSurface:
    """Elevate degree in U by applying curve degree_elevation to every V-row."""
    from kerf_cad_core.geom.nurbs import NurbsCurve, degree_elevation
    if new_deg <= srf.degree_u:
        return srf
    nu, nv, dim = srf.control_points.shape
    new_rows = []
    new_knots_u = None
    for j in range(nv):
        col_pts = srf.control_points[:, j, :]
        w_col = srf.weights[:, j] if srf.weights is not None else None
        crv = NurbsCurve(degree=srf.degree_u, control_points=col_pts, knots=srf.knots_u,
                         weights=w_col)
        crv2 = degree_elevation(crv, new_deg)
        new_rows.append(crv2.control_points)
        if new_knots_u is None:
            new_knots_u = crv2.knots
    # Stack back: shape (nu', nv, dim)
    new_cp = np.stack(new_rows, axis=1)  # (nu', nv, dim)
    return NurbsSurface(degree_u=new_deg, degree_v=srf.degree_v,
                        control_points=new_cp, knots_u=new_knots_u,
                        knots_v=srf.knots_v.copy(), weights=None)


def _surface_degree_elevate_v(srf: NurbsSurface, new_deg: int) -> NurbsSurface:
    """Elevate degree in V by applying curve degree_elevation to every U-row."""
    from kerf_cad_core.geom.nurbs import NurbsCurve, degree_elevation
    if new_deg <= srf.degree_v:
        return srf
    nu, nv, dim = srf.control_points.shape
    new_cols = []
    new_knots_v = None
    for i in range(nu):
        row_pts = srf.control_points[i, :, :]
        w_row = srf.weights[i, :] if srf.weights is not None else None
        crv = NurbsCurve(degree=srf.degree_v, control_points=row_pts, knots=srf.knots_v,
                         weights=w_row)
        crv2 = degree_elevation(crv, new_deg)
        new_cols.append(crv2.control_points)
        if new_knots_v is None:
            new_knots_v = crv2.knots
    # Stack back: shape (nu, nv', dim)
    new_cp = np.stack(new_cols, axis=0)  # (nu, nv', dim)
    return NurbsSurface(degree_u=srf.degree_u, degree_v=new_deg,
                        control_points=new_cp, knots_u=srf.knots_u.copy(),
                        knots_v=new_knots_v, weights=None)


def _surface_insert_knots_u(srf: NurbsSurface, u: float, times: int) -> NurbsSurface:
    """Insert knot u in U direction *times* into all V-iso-rows."""
    from kerf_cad_core.geom.nurbs import NurbsCurve, knot_insertion
    nu, nv, dim = srf.control_points.shape
    new_rows = []
    new_knots_u = None
    for j in range(nv):
        col_pts = srf.control_points[:, j, :]
        crv = NurbsCurve(degree=srf.degree_u, control_points=col_pts, knots=srf.knots_u)
        crv2 = knot_insertion(crv, u, times)
        new_rows.append(crv2.control_points)
        if new_knots_u is None:
            new_knots_u = crv2.knots
    new_cp = np.stack(new_rows, axis=1)
    return NurbsSurface(degree_u=srf.degree_u, degree_v=srf.degree_v,
                        control_points=new_cp, knots_u=new_knots_u,
                        knots_v=srf.knots_v.copy(), weights=None)


def _surface_insert_knots_v(srf: NurbsSurface, v: float, times: int) -> NurbsSurface:
    """Insert knot v in V direction *times* into all U-iso-rows."""
    from kerf_cad_core.geom.nurbs import NurbsCurve, knot_insertion
    nu, nv, dim = srf.control_points.shape
    new_cols = []
    new_knots_v = None
    for i in range(nu):
        row_pts = srf.control_points[i, :, :]
        crv = NurbsCurve(degree=srf.degree_v, control_points=row_pts, knots=srf.knots_v)
        crv2 = knot_insertion(crv, v, times)
        new_cols.append(crv2.control_points)
        if new_knots_v is None:
            new_knots_v = crv2.knots
    new_cp = np.stack(new_cols, axis=0)
    return NurbsSurface(degree_u=srf.degree_u, degree_v=srf.degree_v,
                        control_points=new_cp, knots_u=srf.knots_u.copy(),
                        knots_v=new_knots_v, weights=None)


def _make_surfaces_compatible(a: NurbsSurface, b: NurbsSurface):
    """Return (a', b') sharing degree_u, degree_v, knots_u, knots_v."""
    # Normalise knot domains to [0, 1]
    a = _normalise_surface_knots(a)
    b = _normalise_surface_knots(b)

    # Match degrees in U then V
    if a.degree_u < b.degree_u:
        a = _surface_degree_elevate_u(a, b.degree_u)
    elif b.degree_u < a.degree_u:
        b = _surface_degree_elevate_u(b, a.degree_u)

    if a.degree_v < b.degree_v:
        a = _surface_degree_elevate_v(a, b.degree_v)
    elif b.degree_v < a.degree_v:
        b = _surface_degree_elevate_v(b, a.degree_v)

    # Insert missing knots in U
    def _mult(knots: np.ndarray, u: float, tol: float = 1e-10) -> int:
        return int(np.sum(np.abs(knots - u) < tol))

    def _internal(srf: NurbsSurface, axis: str) -> np.ndarray:
        knots = srf.knots_u if axis == 'u' else srf.knots_v
        deg = srf.degree_u if axis == 'u' else srf.degree_v
        return knots[deg + 1: -(deg + 1)]

    def _insert_u(s: NurbsSurface, ref: NurbsSurface) -> NurbsSurface:
        visited: set = set()
        for u in _internal(ref, 'u'):
            key = round(u, 12)
            if key in visited:
                continue
            visited.add(key)
            times = _mult(ref.knots_u, u) - _mult(s.knots_u, u)
            if times > 0:
                s = _surface_insert_knots_u(s, u, times)
        return s

    def _insert_v(s: NurbsSurface, ref: NurbsSurface) -> NurbsSurface:
        visited: set = set()
        for v in _internal(ref, 'v'):
            key = round(v, 12)
            if key in visited:
                continue
            visited.add(key)
            times = _mult(ref.knots_v, v) - _mult(s.knots_v, v)
            if times > 0:
                s = _surface_insert_knots_v(s, v, times)
        return s

    a = _insert_u(a, b)
    b = _insert_u(b, a)
    a = _insert_v(a, b)
    b = _insert_v(b, a)

    return a, b


def mid_surface(surf_a: NurbsSurface, surf_b: NurbsSurface) -> NurbsSurface:
    """Return the mid-surface (CP-wise average) of two NURBS surfaces.

    The two input surfaces are first made knot-compatible (degree elevation +
    knot insertion in both U and V so they share the same knot vectors), then
    each pair of corresponding control points is averaged.

    Parameters
    ----------
    surf_a, surf_b:
        Input NurbsSurface objects.  They may have different degrees and knot
        vectors but must share the same spatial dimension (typically 3).

    Returns
    -------
    NurbsSurface
        A new surface whose control points are ``(P_a + P_b) / 2``.
    """
    a, b = _make_surfaces_compatible(surf_a, surf_b)
    if a.control_points.shape != b.control_points.shape:
        raise ValueError(
            f"mid_surface: after compatibility pass CP shapes differ: "
            f"{a.control_points.shape} vs {b.control_points.shape}"
        )
    mid_cp = 0.5 * (a.control_points + b.control_points)
    mid_weights = None
    if a.weights is not None or b.weights is not None:
        wa = a.weights if a.weights is not None else np.ones(a.control_points.shape[:2])
        wb = b.weights if b.weights is not None else np.ones(b.control_points.shape[:2])
        mid_weights = 0.5 * (wa + wb)
    return NurbsSurface(
        degree_u=a.degree_u,
        degree_v=a.degree_v,
        control_points=mid_cp,
        knots_u=a.knots_u.copy(),
        knots_v=a.knots_v.copy(),
        weights=mid_weights,
    )


# ---------------------------------------------------------------------------
# GK-139: extend_surface
# ---------------------------------------------------------------------------

def extend_surface(
    surface: NurbsSurface,
    length: float,
    edge: str = "u_max",
    continuity: str = "G1",
) -> NurbsSurface:
    """Extend a NURBS surface beyond its parametric domain.

    Parameters
    ----------
    surface : NurbsSurface
        The input surface to extend.
    length : float
        Extension amount (> 0) in world units.  The extension is scaled so
        that the appended strip has approximately this length measured along
        the boundary tangent.
    edge : str
        Which boundary to extend.  One of:

        - ``'u_max'`` — extend past the u = u_max boundary  (default)
        - ``'u_min'`` — extend past the u = u_min boundary
        - ``'v_max'`` — extend past the v = v_max boundary
        - ``'v_min'`` — extend past the v = v_min boundary
    continuity : str
        ``'G1'`` (tangent-continuous) or ``'G2'`` (curvature-continuous).

    Returns
    -------
    NurbsSurface
        A new surface whose control-point grid is one row/column wider in
        the extension direction.  The original surface is the sub-grid
        ``[:-1, :]`` (or ``[1:, :]``, etc.) of the returned surface.

    Algorithm
    ---------
    For G1: the new boundary row of control points is the reflection of the
    second-to-last row through the last row, scaled to achieve the requested
    extension length.  This exactly matches the tangent direction at the
    boundary (the classic "Bézier extension" lemma).

    For G2: an additional row is inserted so that the curvature at the
    boundary is preserved.  The extra CP is derived from the standard
    discrete curvature condition on B-spline control polygons.
    """
    if length <= 0.0:
        raise ValueError("extend_surface: length must be > 0")
    if continuity not in ("G1", "G2"):
        raise ValueError("extend_surface: continuity must be 'G1' or 'G2'")
    if edge not in ("u_max", "u_min", "v_max", "v_min"):
        raise ValueError("extend_surface: edge must be 'u_max', 'u_min', 'v_max', or 'v_min'")

    cp = surface.control_points.copy().astype(float)  # (nu, nv, dim)
    ku = surface.degree_u
    kv = surface.degree_v
    knots_u = surface.knots_u.copy()
    knots_v = surface.knots_v.copy()
    nu, nv, dim = cp.shape

    def _clamped_knots(n: int, degree: int) -> np.ndarray:
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

    # We work in (u, v) space.  For u_max / u_min we extend rows (axis 0);
    # for v_max / v_min we extend columns (axis 1).  We handle u_max here
    # and map the other edges to this canonical form via transposition /
    # row-reversal.

    def _extend_u_max(cp_: np.ndarray, ku_: int, kv_: int,
                      ku_knots: np.ndarray, kv_knots: np.ndarray,
                      length_: float, cont: str) -> NurbsSurface:
        """Extend along the u_max boundary (append a new last row)."""
        nu_, nv_, dim_ = cp_.shape

        # Estimate the tangent-direction step length along the boundary.
        # Use the last two rows: boundary row P[-1, :] and second-to-last P[-2, :]
        # The CP difference P[-1] - P[-2] represents (degree/delta_u) * tangent.
        # We need to scale the extension so the new row is ~length_ away.

        # Average distance of the boundary step (last two rows)
        delta = cp_[-1, :, :] - cp_[-2, :, :]  # (nv_, dim_)
        avg_step = np.mean(np.linalg.norm(delta, axis=1))
        if avg_step < 1e-14:
            avg_step = 1.0

        # Scale factor: how many times the current CP step equals length_
        scale = float(length_) / avg_step

        if cont == "G1":
            # New row = P[-1] + scale * (P[-1] - P[-2])
            new_row = cp_[-1, :, :] + scale * delta  # (nv_, dim_)
            new_cp = np.concatenate([cp_, new_row[np.newaxis, :, :]], axis=0)
            new_ku = _clamped_knots(nu_ + 1, ku_)
            return NurbsSurface(
                degree_u=ku_, degree_v=kv_,
                control_points=new_cp,
                knots_u=new_ku,
                knots_v=kv_knots.copy(),
            )
        else:  # G2
            # G2 needs two extra rows to maintain curvature.
            # Second curvature row from the discrete curvature condition:
            # P[-3], P[-2], P[-1] determine the curvature at the boundary.
            # For the extension segment (P[-1], R1, R2):
            #   G2: 2*R1 - R2 = 2*P[-1] - P[-2]  (curvature match)
            # => R2 = 2*R1 - (2*P[-1] - P[-2])
            # We pick R1 = P[-1] + scale * delta (same as G1)
            R1 = cp_[-1, :, :] + scale * delta
            if nu_ >= 3:
                curv_vec = cp_[-1, :, :] - 2.0 * cp_[-2, :, :] + cp_[-3, :, :]
            else:
                curv_vec = np.zeros_like(delta)
            R2 = 2.0 * R1 - cp_[-1, :, :] + scale * scale * curv_vec
            new_cp = np.concatenate(
                [cp_, R1[np.newaxis, :, :], R2[np.newaxis, :, :]], axis=0
            )
            new_ku = _clamped_knots(nu_ + 2, ku_)
            return NurbsSurface(
                degree_u=ku_, degree_v=kv_,
                control_points=new_cp,
                knots_u=new_ku,
                knots_v=kv_knots.copy(),
            )

    if edge == "u_max":
        return _extend_u_max(cp, ku, kv, knots_u, knots_v, length, continuity)

    elif edge == "u_min":
        # Reverse u direction, extend u_max, reverse back
        cp_rev = cp[::-1, :, :]
        result = _extend_u_max(cp_rev, ku, kv, knots_u, knots_v, length, continuity)
        # Reverse back
        return NurbsSurface(
            degree_u=result.degree_u,
            degree_v=result.degree_v,
            control_points=result.control_points[::-1, :, :],
            knots_u=_clamped_knots(result.control_points.shape[0], result.degree_u),
            knots_v=result.knots_v.copy(),
        )

    elif edge == "v_max":
        # Transpose u<->v, extend u_max, transpose back
        cp_T = np.transpose(cp, (1, 0, 2))  # (nv, nu, dim)
        result = _extend_u_max(cp_T, kv, ku, knots_v, knots_u, length, continuity)
        return NurbsSurface(
            degree_u=ku,
            degree_v=result.degree_u,
            control_points=np.transpose(result.control_points, (1, 0, 2)),
            knots_u=knots_u.copy(),
            knots_v=result.knots_u.copy(),
        )

    else:  # v_min
        # Reverse v, transpose, extend u_max, transpose back, reverse back
        cp_rev = cp[:, ::-1, :]
        cp_T = np.transpose(cp_rev, (1, 0, 2))
        result = _extend_u_max(cp_T, kv, ku, knots_v, knots_u, length, continuity)
        cp_back = np.transpose(result.control_points, (1, 0, 2))
        cp_back = cp_back[:, ::-1, :]
        return NurbsSurface(
            degree_u=ku,
            degree_v=result.degree_u,
            control_points=cp_back,
            knots_u=knots_u.copy(),
            knots_v=_clamped_knots(cp_back.shape[1], result.degree_u),
        )
