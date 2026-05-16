"""
intersection.py
===============
Pure-Python intersection geometry: curve-surface, surface-surface, and
curve-curve intersections (Rhino parity).

Public API
----------
curve_surface_intersect(curve, surface, *, tol, samples_c, samples_u, samples_v)
    -> list[dict]
    Find all intersection points between a NurbsCurve and a NurbsSurface.
    Strategy: subdivide curve parameter space into segments and the surface into
    (u, v) patches, cull non-overlapping AABBs, then refine each candidate pair
    via Newton iteration on the residual  surface(u, v) - curve(t) = 0.
    Returns a list of dicts, each with:
        t       : float   -- curve parameter
        u, v    : float   -- surface parameters
        point   : list[float, float, float]  -- 3-D intersection point
    Never raises.  Duplicate hits closer than ``tol`` are merged.

surface_surface_intersect(surf_a, surf_b, *, tol, samples_u, samples_v, step, max_steps)
    -> dict
    Compute intersection curve(s) between two NurbsSurfaces via a marching
    method.
    Returns a dict with:
        ok          : bool
        reason      : str        (empty on success)
        branches    : list[dict] -- one dict per branch, each with:
            points  : list[[x,y,z]]  -- ordered 3-D polyline vertices
            params_a: list[[u,v]]    -- surface A parameters per vertex
            params_b: list[[u,v]]    -- surface B parameters per vertex
            closed  : bool
        branch_count: int
    Never raises.

curve_curve_intersect(curve_a, curve_b, *, tol, samples_a, samples_b)
    -> list[dict]
    Find all intersection points between two NurbsCurves (planar or 3-D).
    Returns a list of dicts, each with:
        ta      : float  -- parameter on curve_a
        tb      : float  -- parameter on curve_b
        point   : list[float, float, float]
    Never raises.  Duplicate hits closer than ``tol`` are merged.

Implementation note
-------------------
The surface_evaluate function in geom/nurbs.py has a known limitation with its
basis_functions computation.  This module implements a correct NURBS surface
evaluator (_nurbs_surface_eval) that properly handles the triangular recurrence
for B-spline basis functions, while still using the NurbsSurface/NurbsCurve data
structures from geom/nurbs.py.  Curve evaluation uses de_boor from nurbs.py
which works correctly for NurbsCurve.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

from kerf_cad_core.geom.nurbs import (
    NurbsCurve,
    NurbsSurface,
    de_boor,
    surface_derivatives,
    surface_evaluate,
    surface_normal,
)

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_DEFAULT_TOL: float = 1e-6
_DEFAULT_SAMPLES_C: int = 64
_DEFAULT_SAMPLES_UV: int = 24
_DEFAULT_MARCH_STEP: float = 0.02
_DEFAULT_MAX_STEPS: int = 2000
_MAX_NEWTON_ITER: int = 40
_MIN_BRANCH_PTS: int = 2


# ---------------------------------------------------------------------------
# Correct NURBS evaluators
# ---------------------------------------------------------------------------

def _find_span(n: int, degree: int, u: float, knots: np.ndarray) -> int:
    """Binary-search knot span index (standard algorithm)."""
    if u >= knots[n + 1]:
        return n
    if u <= knots[degree]:
        return degree
    low, high = degree, n + 1
    mid = (low + high) // 2
    while u < knots[mid] or u >= knots[mid + 1]:
        if u < knots[mid]:
            high = mid
        else:
            low = mid
        mid = (low + high) // 2
    return mid


def _basis_fns(span: int, u: float, degree: int, knots: np.ndarray) -> np.ndarray:
    """Compute the (degree+1) non-zero B-spline basis functions at u.

    Uses the correct triangular recurrence (Cox-de Boor).  Returns N[0..degree]
    where N[j] = N_{span-degree+j,degree}(u).
    """
    N = np.zeros(degree + 1)
    N[0] = 1.0
    left = np.zeros(degree + 1)
    right = np.zeros(degree + 1)
    for j in range(1, degree + 1):
        left[j] = u - knots[span + 1 - j]
        right[j] = knots[span + j] - u
        saved = 0.0
        for r in range(j):
            denom = right[r + 1] + left[j - r]
            if abs(denom) < 1e-15:
                temp = 0.0
            else:
                temp = N[r] / denom
            N[r] = saved + right[r + 1] * temp
            saved = left[j - r] * temp
        N[j] = saved
    return N


def _nurbs_curve_eval(c: NurbsCurve, t: float) -> np.ndarray:
    """Evaluate NurbsCurve at t, return 3-element array (uses de_boor)."""
    pt = de_boor(c, float(t))
    arr = np.asarray(pt, dtype=float).ravel()
    out = np.zeros(3)
    n = min(3, arr.size)
    out[:n] = arr[:n]
    return out


def _nurbs_surface_eval(s: NurbsSurface, u: float, v: float) -> np.ndarray:
    """Evaluate NurbsSurface at (u, v) using the correct Cox-de Boor algorithm."""
    n_u = s.num_control_points_u - 1
    n_v = s.num_control_points_v - 1
    span_u = _find_span(n_u, s.degree_u, float(u), s.knots_u)
    span_v = _find_span(n_v, s.degree_v, float(v), s.knots_v)
    Nu = _basis_fns(span_u, float(u), s.degree_u, s.knots_u)
    Nv = _basis_fns(span_v, float(v), s.degree_v, s.knots_v)
    dim = s.control_points.shape[2]
    result = np.zeros(dim)
    for i in range(s.degree_u + 1):
        for j in range(s.degree_v + 1):
            idx_i = span_u - s.degree_u + i
            idx_j = span_v - s.degree_v + j
            result += Nu[i] * Nv[j] * s.control_points[idx_i, idx_j]
    out = np.zeros(3)
    n = min(3, dim)
    out[:n] = result[:n]
    return out


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _curve_param_range(c: NurbsCurve) -> Tuple[float, float]:
    return float(c.knots[c.degree]), float(c.knots[-(c.degree + 1)])


def _surface_param_range(s: NurbsSurface) -> Tuple[float, float, float, float]:
    return (
        float(s.knots_u[0]), float(s.knots_u[-1]),
        float(s.knots_v[0]), float(s.knots_v[-1]),
    )


def _curve_eval(c: NurbsCurve, t: float) -> np.ndarray:
    return _nurbs_curve_eval(c, t)


def _surf_eval(s: NurbsSurface, u: float, v: float) -> np.ndarray:
    """Evaluate a NURBS surface (rational-correct).

    Routes to the unified GK-01 evaluator ``nurbs.surface_evaluate`` which
    correctly applies per-control-point weights (the legacy
    ``_nurbs_surface_eval`` here silently ignored ``surf.weights`` — the
    root cause of SSI being weak on exact rational primitives such as
    spheres / cylinders).  Falls back to the local non-rational evaluator
    only if the unified path is unavailable.
    """
    try:
        p = surface_evaluate(s, float(u), float(v))
        arr = np.asarray(p, dtype=float).ravel()
        out = np.zeros(3)
        n = min(3, arr.size)
        out[:n] = arr[:n]
        if np.all(np.isfinite(out)):
            return out
    except Exception:
        pass
    return _nurbs_surface_eval(s, u, v)


def _surf_partials_fd(
    s: NurbsSurface, u: float, v: float
) -> Tuple[np.ndarray, np.ndarray]:
    """Central finite-difference partials dp/du and dp/dv (fallback path)."""
    u_min, u_max, v_min, v_max = _surface_param_range(s)
    hu = max(1e-6, (u_max - u_min) * 1e-4)
    hv = max(1e-6, (v_max - v_min) * 1e-4)
    u0 = float(np.clip(u, u_min, u_max))
    v0 = float(np.clip(v, v_min, v_max))
    up = min(u_max, u0 + hu); um = max(u_min, u0 - hu)
    vp = min(v_max, v0 + hv); vm = max(v_min, v0 - hv)
    dp_du = (_surf_eval(s, up, v0) - _surf_eval(s, um, v0)) / (up - um + 1e-15)
    dp_dv = (_surf_eval(s, u0, vp) - _surf_eval(s, u0, vm)) / (vp - vm + 1e-15)
    return dp_du, dp_dv


def _surf_partials(
    s: NurbsSurface, u: float, v: float
) -> Tuple[np.ndarray, np.ndarray]:
    """First partials dp/du, dp/dv.

    Uses the analytic Cox-de Boor / rational quotient-rule derivatives from
    ``nurbs.surface_derivatives`` (GK-01/02) which are exact for rational
    primitives.  Falls back to central finite differences only if the analytic
    path is unavailable or returns a degenerate result.
    """
    try:
        SKL = surface_derivatives(s, float(u), float(v), d=1)
        du = np.asarray(SKL[1, 0][:3], dtype=float)
        dv = np.asarray(SKL[0, 1][:3], dtype=float)
        if np.all(np.isfinite(du)) and np.all(np.isfinite(dv)):
            return du, dv
    except Exception:
        pass
    return _surf_partials_fd(s, u, v)


def _surf_second_partials(
    s: NurbsSurface, u: float, v: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Analytic second partials (S_uu, S_uv, S_vv); zeros on failure."""
    try:
        SKL = surface_derivatives(s, float(u), float(v), d=2)
        suu = np.asarray(SKL[2, 0][:3], dtype=float)
        suv = np.asarray(SKL[1, 1][:3], dtype=float)
        svv = np.asarray(SKL[0, 2][:3], dtype=float)
        if (np.all(np.isfinite(suu)) and np.all(np.isfinite(suv))
                and np.all(np.isfinite(svv))):
            return suu, suv, svv
    except Exception:
        pass
    return np.zeros(3), np.zeros(3), np.zeros(3)


def _surf_normal(s: NurbsSurface, u: float, v: float) -> np.ndarray:
    """Unit surface normal via analytic partials (FD fallback)."""
    try:
        n = surface_normal(s, float(u), float(v))
        n = np.asarray(n[:3], dtype=float)
        if np.all(np.isfinite(n)) and np.linalg.norm(n) > 1e-12:
            return n / np.linalg.norm(n)
    except Exception:
        pass
    dp_du, dp_dv = _surf_partials(s, u, v)
    n = np.cross(dp_du, dp_dv)
    nrm = np.linalg.norm(n)
    if nrm < 1e-15:
        return np.array([0.0, 0.0, 1.0])
    return n / nrm


def _aabb(pts: List[np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    arr = np.stack(pts)
    return arr.min(axis=0), arr.max(axis=0)


def _aabb_overlap(lo_a: np.ndarray, hi_a: np.ndarray,
                  lo_b: np.ndarray, hi_b: np.ndarray,
                  tol: float) -> bool:
    for i in range(3):
        if lo_a[i] - tol > hi_b[i] or lo_b[i] - tol > hi_a[i]:
            return False
    return True


def _merge_close_hits(
    hits: List[dict],
    tol: float,
    key: str = "point",
) -> List[dict]:
    merged: List[dict] = []
    for h in hits:
        p = np.array(h[key])
        close = any(
            np.linalg.norm(p - np.array(m[key])) < tol
            for m in merged
        )
        if not close:
            merged.append(h)
    return merged


# ---------------------------------------------------------------------------
# Newton: curve-surface
# ---------------------------------------------------------------------------

def _newton_curve_surface(
    curve: NurbsCurve,
    surface: NurbsSurface,
    t0: float,
    u0: float,
    v0: float,
    *,
    tol: float = _DEFAULT_TOL,
    max_iter: int = _MAX_NEWTON_ITER,
) -> Optional[Tuple[float, float, float]]:
    """Refine a curve-surface intersection via Newton iteration.

    Solves F(t, u, v) = surface(u,v) - curve(t) = 0  (3 eq, 3 unknowns).
    Returns (t, u, v) on convergence, else None.
    """
    t_min, t_max = _curve_param_range(curve)
    u_min, u_max, v_min, v_max = _surface_param_range(surface)

    t = float(np.clip(t0, t_min, t_max))
    u = float(np.clip(u0, u_min, u_max))
    v = float(np.clip(v0, v_min, v_max))

    ht = max(1e-6, (t_max - t_min) * 1e-4)

    for _ in range(max_iter):
        S = _surf_eval(surface, u, v)
        C = _curve_eval(curve, t)
        F = S - C
        if np.linalg.norm(F) < tol:
            return (t, u, v)

        dp_du, dp_dv = _surf_partials(surface, u, v)
        tp = min(t_max, t + ht); tm = max(t_min, t - ht)
        dC_dt = (_curve_eval(curve, tp) - _curve_eval(curve, tm)) / (tp - tm + 1e-15)

        # Jacobian columns: [dp_du, dp_dv, -dC_dt]  shape (3, 3)
        J = np.column_stack([dp_du, dp_dv, -dC_dt])
        det = np.linalg.det(J)
        if abs(det) < 1e-20:
            # Fall back to pseudo-inverse
            delta, *_ = np.linalg.lstsq(J, -F, rcond=None)
        else:
            delta = np.linalg.solve(J, -F)

        u_new = float(np.clip(u + delta[0], u_min, u_max))
        v_new = float(np.clip(v + delta[1], v_min, v_max))
        t_new = float(np.clip(t + delta[2], t_min, t_max))

        if (abs(u_new - u) < tol * 1e-2 and
                abs(v_new - v) < tol * 1e-2 and
                abs(t_new - t) < tol * 1e-2):
            return (t_new, u_new, v_new)

        u, v, t = u_new, v_new, t_new

    # Accept if residual is small
    F_fin = _surf_eval(surface, u, v) - _curve_eval(curve, t)
    if np.linalg.norm(F_fin) < tol * 1e3:
        return (t, u, v)
    return None


# ---------------------------------------------------------------------------
# curve_surface_intersect
# ---------------------------------------------------------------------------

def curve_surface_intersect(
    curve: NurbsCurve,
    surface: NurbsSurface,
    *,
    tol: float = _DEFAULT_TOL,
    samples_c: int = _DEFAULT_SAMPLES_C,
    samples_u: int = _DEFAULT_SAMPLES_UV,
    samples_v: int = _DEFAULT_SAMPLES_UV,
) -> List[dict]:
    """Find all intersection points between a NurbsCurve and a NurbsSurface.

    Parameters
    ----------
    curve : NurbsCurve
    surface : NurbsSurface
    tol : float
        Spatial convergence tolerance and duplicate-merge radius.
    samples_c : int
        Number of curve subdivisions for AABB cull.
    samples_u, samples_v : int
        Number of surface subdivisions in U and V for AABB cull.

    Returns
    -------
    list of dict with keys: t, u, v, point.  Never raises.
    """
    try:
        return _curve_surface_intersect_impl(
            curve, surface,
            tol=tol, samples_c=samples_c,
            samples_u=samples_u, samples_v=samples_v,
        )
    except Exception:
        return []


def _curve_surface_intersect_impl(
    curve: NurbsCurve,
    surface: NurbsSurface,
    *,
    tol: float,
    samples_c: int,
    samples_u: int,
    samples_v: int,
) -> List[dict]:
    if not isinstance(curve, NurbsCurve):
        return []
    if not isinstance(surface, NurbsSurface):
        return []

    t_min, t_max = _curve_param_range(curve)
    u_min, u_max, v_min, v_max = _surface_param_range(surface)

    sc = max(4, int(samples_c))
    su = max(4, int(samples_u))
    sv = max(4, int(samples_v))

    t_vals = np.linspace(t_min, t_max, sc + 1)
    u_vals = np.linspace(u_min, u_max, su + 1)
    v_vals = np.linspace(v_min, v_max, sv + 1)

    c_pts = [_curve_eval(curve, float(t)) for t in t_vals]
    s_pts = {
        (i, j): _surf_eval(surface, float(u_vals[i]), float(v_vals[j]))
        for i in range(su + 1)
        for j in range(sv + 1)
    }

    candidates: List[Tuple[float, float, float]] = []

    for ci in range(sc):
        c_seg = [c_pts[ci], c_pts[ci + 1]]
        c_lo, c_hi = _aabb(c_seg)

        for si in range(su):
            for sj in range(sv):
                s_seg = [
                    s_pts[(si, sj)], s_pts[(si + 1, sj)],
                    s_pts[(si, sj + 1)], s_pts[(si + 1, sj + 1)],
                ]
                s_lo, s_hi = _aabb(s_seg)

                if not _aabb_overlap(c_lo, c_hi, s_lo, s_hi, tol * 10):
                    continue

                t0 = (t_vals[ci] + t_vals[ci + 1]) * 0.5
                u0 = (u_vals[si] + u_vals[si + 1]) * 0.5
                v0 = (v_vals[sj] + v_vals[sj + 1]) * 0.5
                candidates.append((t0, u0, v0))

    hits: List[dict] = []
    for t0, u0, v0 in candidates:
        result = _newton_curve_surface(curve, surface, t0, u0, v0, tol=tol)
        if result is None:
            continue
        t_ref, u_ref, v_ref = result
        S = _surf_eval(surface, u_ref, v_ref)
        C = _curve_eval(curve, t_ref)
        if np.linalg.norm(S - C) > tol * 1e3:
            continue
        pt = ((S + C) * 0.5).tolist()
        hits.append({"t": t_ref, "u": u_ref, "v": v_ref, "point": pt})

    return _merge_close_hits(hits, tol)


# ---------------------------------------------------------------------------
# Newton: surface-surface seed
# ---------------------------------------------------------------------------

def _newton_surf_surf_point(
    surf_a: NurbsSurface,
    surf_b: NurbsSurface,
    uA0: float, vA0: float,
    uB0: float, vB0: float,
    *,
    tol: float = _DEFAULT_TOL,
    max_iter: int = _MAX_NEWTON_ITER,
) -> Optional[Tuple[float, float, float, float]]:
    """Newton refinement for surface-surface intersection seed.

    Solves surf_a(uA, vA) - surf_b(uB, vB) = 0  (3 eq, 4 unknowns).
    Uses least-norm pseudo-inverse solution.
    Returns (uA, vA, uB, vB) or None.
    """
    uA_min, uA_max, vA_min, vA_max = _surface_param_range(surf_a)
    uB_min, uB_max, vB_min, vB_max = _surface_param_range(surf_b)

    uA = float(np.clip(uA0, uA_min, uA_max))
    vA = float(np.clip(vA0, vA_min, vA_max))
    uB = float(np.clip(uB0, uB_min, uB_max))
    vB = float(np.clip(vB0, vB_min, vB_max))

    for _ in range(max_iter):
        PA = _surf_eval(surf_a, uA, vA)
        PB = _surf_eval(surf_b, uB, vB)
        F = PA - PB
        if np.linalg.norm(F) < tol:
            return (uA, vA, uB, vB)

        dpA_du, dpA_dv = _surf_partials(surf_a, uA, vA)
        dpB_du, dpB_dv = _surf_partials(surf_b, uB, vB)

        J = np.column_stack([dpA_du, dpA_dv, -dpB_du, -dpB_dv])  # (3, 4)
        # Least-norm: delta = J^T (J J^T)^-1 (-F)
        JJT = J @ J.T
        try:
            lam = np.linalg.solve(JJT, -F)
        except np.linalg.LinAlgError:
            break
        delta = J.T @ lam

        uA_new = float(np.clip(uA + delta[0], uA_min, uA_max))
        vA_new = float(np.clip(vA + delta[1], vA_min, vA_max))
        uB_new = float(np.clip(uB + delta[2], uB_min, uB_max))
        vB_new = float(np.clip(vB + delta[3], vB_min, vB_max))

        if (abs(uA_new - uA) < tol * 1e-2 and abs(vA_new - vA) < tol * 1e-2 and
                abs(uB_new - uB) < tol * 1e-2 and abs(vB_new - vB) < tol * 1e-2):
            return (uA_new, vA_new, uB_new, vB_new)

        uA, vA, uB, vB = uA_new, vA_new, uB_new, vB_new

    PA = _surf_eval(surf_a, uA, vA)
    PB = _surf_eval(surf_b, uB, vB)
    if np.linalg.norm(PA - PB) < tol * 1e3:
        return (uA, vA, uB, vB)
    return None


# ---------------------------------------------------------------------------
# GK-10 — Analytic primitive recognition + closed-form specialisations
# ---------------------------------------------------------------------------
#
# When BOTH surfaces are recognisable analytic primitives (plane / sphere /
# cylinder) we solve the intersection in closed form.  This gives exact seeds
# AND exact oracles (line∩sphere, plane∩sphere, sphere∩sphere, cyl∩cyl, ...).
# Recognition fits the surface's sampled point set to the primitive's implicit
# equation and only accepts the fit when the algebraic residual is below
# ``tol``.  Anything not recognised falls back to the hardened marcher.

_PRIM_FIT_TOL: float = 1e-7


def _sample_surface_grid(s: NurbsSurface, n: int = 11) -> np.ndarray:
    """Interior sample grid for primitive fitting.

    Samples strictly *inside* the parameter domain (a small margin from each
    edge), then deduplicates near-coincident points.  This stops the collapsed
    poles / seam of a surface of revolution from piling dozens of identical
    points onto one location and biasing the algebraic least-squares fits.
    """
    u0, u1, v0, v1 = _surface_param_range(s)
    mu = (u1 - u0) * 0.04
    mv = (v1 - v0) * 0.04
    us = np.linspace(u0 + mu, u1 - mu, n)
    vs = np.linspace(v0 + mv, v1 - mv, n)
    raw = np.array([_surf_eval(s, float(u), float(v)) for u in us for v in vs])
    # Deduplicate (poles / seam collapse to a single point).
    keep: List[np.ndarray] = []
    for p in raw:
        if not any(np.linalg.norm(p - q) < 1e-9 for q in keep):
            keep.append(p)
    return np.array(keep) if keep else raw


def _fit_plane(pts: np.ndarray) -> Optional[Tuple[np.ndarray, np.ndarray, float]]:
    """Best-fit plane.  Returns (point, unit_normal, max_abs_residual)."""
    c = pts.mean(axis=0)
    q = pts - c
    # SVD: smallest right-singular vector is the plane normal.
    try:
        _, sv, vh = np.linalg.svd(q, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    n = vh[-1]
    nn = np.linalg.norm(n)
    if nn < 1e-14:
        return None
    n = n / nn
    resid = float(np.max(np.abs(q @ n)))
    return c, n, resid


def _fit_sphere(pts: np.ndarray) -> Optional[Tuple[np.ndarray, float, float]]:
    """Algebraic sphere fit.  Returns (centre, radius, max_abs_residual)."""
    if pts.shape[0] < 4:
        return None
    A = np.hstack([2.0 * pts, np.ones((pts.shape[0], 1))])
    b = np.sum(pts * pts, axis=1)
    try:
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    centre = sol[:3]
    r2 = sol[3] + float(centre @ centre)
    if r2 <= 1e-18:
        return None
    radius = math.sqrt(r2)
    resid = float(np.max(np.abs(np.linalg.norm(pts - centre, axis=1) - radius)))
    return centre, radius, resid


def _fit_cylinder(
    pts: np.ndarray,
) -> Optional[Tuple[np.ndarray, np.ndarray, float, float]]:
    """Fit an (infinite) right circular cylinder.

    Returns (axis_point, unit_axis_dir, radius, max_abs_residual).  The axis
    direction is taken as the largest-variance principal direction of the point
    set (works for a tubular patch) and the radius/centre as the circle fit of
    the points projected onto the plane perpendicular to that axis.
    """
    if pts.shape[0] < 6:
        return None
    c = pts.mean(axis=0)
    q = pts - c
    try:
        _, _, vh = np.linalg.svd(q, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    axis = vh[0]
    axis = axis / (np.linalg.norm(axis) + 1e-300)
    # Project points onto the plane perpendicular to axis, then fit a circle.
    proj = q - np.outer(q @ axis, axis)
    # 2-D basis in that plane.
    e1 = vh[1] - (vh[1] @ axis) * axis
    e1 = e1 / (np.linalg.norm(e1) + 1e-300)
    e2 = np.cross(axis, e1)
    x = proj @ e1
    y = proj @ e2
    M = np.column_stack([2.0 * x, 2.0 * y, np.ones_like(x)])
    rhs = x * x + y * y
    try:
        sol, *_ = np.linalg.lstsq(M, rhs, rcond=None)
    except np.linalg.LinAlgError:
        return None
    cx, cy = sol[0], sol[1]
    r2 = sol[2] + cx * cx + cy * cy
    if r2 <= 1e-18:
        return None
    radius = math.sqrt(r2)
    axis_pt = c + cx * e1 + cy * e2
    # Residual = |perp distance to axis - radius| over all points.
    d = pts - axis_pt
    perp = d - np.outer(d @ axis, axis)
    resid = float(np.max(np.abs(np.linalg.norm(perp, axis=1) - radius)))
    return axis_pt, axis, radius, resid


def _classify_primitive(s: NurbsSurface, tol: float) -> Optional[dict]:
    """Return a primitive descriptor dict or None if not recognised.

    Recognition is *strict*: we only take the closed-form path when the
    algebraic residual is below ``abs_tol`` (scaled by the patch size).  An
    exact rational primitive fits to ~1e-12; anything sculpted/freeform fits
    far worse and is left to the hardened marcher.
    """
    pts = _sample_surface_grid(s)
    if pts.shape[0] < 6:
        return None
    span = float(np.max(np.linalg.norm(pts - pts.mean(axis=0), axis=1))) + 1.0
    abs_tol = max(tol, _PRIM_FIT_TOL) * span

    pl = _fit_plane(pts)
    if pl is not None and pl[2] <= abs_tol:
        return {"kind": "plane", "point": pl[0], "normal": pl[1]}

    sp = _fit_sphere(pts)
    cy = _fit_cylinder(pts)
    sp_ok = sp is not None and sp[2] <= abs_tol
    cy_ok = cy is not None and cy[3] <= abs_tol
    # Prefer the tighter fit when both look plausible (a sphere patch can
    # masquerade as a fat cylinder over a small region).
    if sp_ok and cy_ok:
        if sp[2] <= cy[3]:
            return {"kind": "sphere", "center": sp[0], "radius": sp[1]}
        return {"kind": "cylinder", "axis_point": cy[0],
                "axis_dir": cy[1], "radius": cy[2]}
    if sp_ok:
        return {"kind": "sphere", "center": sp[0], "radius": sp[1]}
    if cy_ok:
        return {"kind": "cylinder", "axis_point": cy[0],
                "axis_dir": cy[1], "radius": cy[2]}
    return None


def _circle_polyline(
    center: np.ndarray, radius: float, x_axis: np.ndarray, y_axis: np.ndarray,
    n: int = 121,
) -> List[List[float]]:
    """Deterministic uniformly-sampled closed circle polyline (n>=2)."""
    th = np.linspace(0.0, 2.0 * math.pi, n)
    X = x_axis / (np.linalg.norm(x_axis) + 1e-300)
    Y = y_axis / (np.linalg.norm(y_axis) + 1e-300)
    return [
        (center + radius * math.cos(t) * X + radius * math.sin(t) * Y).tolist()
        for t in th
    ]


def _analytic_ssi(
    prim_a: dict, prim_b: dict, tol: float,
) -> Optional[List[dict]]:
    """Closed-form surface∩surface for recognised primitive pairs.

    Returns a list of branch dicts (points/params_a/params_b/closed) or None
    when the pair has no closed-form handler (caller falls back to marching).
    Empty list ⇒ recognised pair with no real intersection.
    """
    ka, kb = prim_a["kind"], prim_b["kind"]
    pair = {ka, kb}

    def _empty_params(n: int):
        return [[0.0, 0.0]] * n

    # ---- plane ∩ sphere → circle (or tangent point / none) ----
    if pair == {"plane", "sphere"}:
        pl = prim_a if ka == "plane" else prim_b
        sp = prim_a if ka == "sphere" else prim_b
        n = pl["normal"] / (np.linalg.norm(pl["normal"]) + 1e-300)
        d = float((sp["center"] - pl["point"]) @ n)
        rr = sp["radius"] ** 2 - d * d
        if rr < -(max(tol, 1e-12)):
            return []
        foot = sp["center"] - d * n
        if rr <= max(tol, 1e-12) ** 2:
            # Tangent: single degenerate point, NOT a garbage loop.
            return [{
                "points": [foot.tolist()],
                "params_a": _empty_params(1),
                "params_b": _empty_params(1),
                "closed": False,
            }]
        rc = math.sqrt(max(rr, 0.0))
        # Build an in-plane orthonormal frame.
        ref = np.array([1.0, 0.0, 0.0])
        if abs(n @ ref) > 0.9:
            ref = np.array([0.0, 1.0, 0.0])
        ex = ref - (ref @ n) * n
        ex = ex / (np.linalg.norm(ex) + 1e-300)
        ey = np.cross(n, ex)
        poly = _circle_polyline(foot, rc, ex, ey)
        return [{
            "points": poly,
            "params_a": _empty_params(len(poly)),
            "params_b": _empty_params(len(poly)),
            "closed": True,
        }]

    # ---- sphere ∩ sphere → circle (or tangent point / none) ----
    if ka == "sphere" and kb == "sphere":
        cA, rA = prim_a["center"], prim_a["radius"]
        cB, rB = prim_b["center"], prim_b["radius"]
        dvec = cB - cA
        dist = float(np.linalg.norm(dvec))
        if dist < max(tol, 1e-12):
            return None  # concentric / coincident: not a clean circle
        if dist > rA + rB + max(tol, 1e-9):
            return []
        if dist < abs(rA - rB) - max(tol, 1e-9):
            return []
        axis = dvec / dist
        # Standard two-sphere formula.
        a = (dist * dist - rB * rB + rA * rA) / (2.0 * dist)
        h2 = rA * rA - a * a
        center = cA + a * axis
        if h2 <= max(tol, 1e-12) ** 2:
            return [{
                "points": [center.tolist()],
                "params_a": _empty_params(1),
                "params_b": _empty_params(1),
                "closed": False,
            }]
        rc = math.sqrt(max(h2, 0.0))
        ref = np.array([1.0, 0.0, 0.0])
        if abs(axis @ ref) > 0.9:
            ref = np.array([0.0, 1.0, 0.0])
        ex = ref - (ref @ axis) * axis
        ex = ex / (np.linalg.norm(ex) + 1e-300)
        ey = np.cross(axis, ex)
        poly = _circle_polyline(center, rc, ex, ey)
        return [{
            "points": poly,
            "params_a": _empty_params(len(poly)),
            "params_b": _empty_params(len(poly)),
            "closed": True,
        }]

    # ---- plane ∩ cylinder (axis ⟂ plane → circle) ----
    if pair == {"plane", "cylinder"}:
        pl = prim_a if ka == "plane" else prim_b
        cy = prim_a if ka == "cylinder" else prim_b
        n = pl["normal"] / (np.linalg.norm(pl["normal"]) + 1e-300)
        ax = cy["axis_dir"] / (np.linalg.norm(cy["axis_dir"]) + 1e-300)
        if abs(abs(float(n @ ax)) - 1.0) < 1e-6:
            # Plane perpendicular to the cylinder axis → exact circle.
            t = float(((pl["point"] - cy["axis_point"]) @ n) / (ax @ n))
            center = cy["axis_point"] + t * ax
            ref = np.array([1.0, 0.0, 0.0])
            if abs(ax @ ref) > 0.9:
                ref = np.array([0.0, 1.0, 0.0])
            ex = ref - (ref @ ax) * ax
            ex = ex / (np.linalg.norm(ex) + 1e-300)
            ey = np.cross(ax, ex)
            poly = _circle_polyline(center, cy["radius"], ex, ey)
            return [{
                "points": poly,
                "params_a": _empty_params(len(poly)),
                "params_b": _empty_params(len(poly)),
                "closed": True,
            }]
        return None  # oblique plane∩cyl → ellipse: leave to marcher

    # ---- cylinder ∩ cylinder, equal radius, crossing perpendicular axes ----
    if ka == "cylinder" and kb == "cylinder":
        rA, rB = prim_a["radius"], prim_b["radius"]
        axA = prim_a["axis_dir"] / (np.linalg.norm(prim_a["axis_dir"]) + 1e-300)
        axB = prim_b["axis_dir"] / (np.linalg.norm(prim_b["axis_dir"]) + 1e-300)
        if abs(rA - rB) > max(tol, 1e-7) * (abs(rA) + 1.0):
            return None
        if abs(float(axA @ axB)) > 1e-6:
            return None  # not perpendicular
        # Closest points of the two axes; require them to (nearly) cross.
        w0 = prim_a["axis_point"] - prim_b["axis_point"]
        aa, bb, cc = 1.0, float(axA @ axB), 1.0
        dd = float(axA @ w0)
        ee = float(axB @ w0)
        den = aa * cc - bb * bb
        if abs(den) < 1e-12:
            return None
        sA = (bb * ee - cc * dd) / den
        sB = (aa * ee - bb * dd) / den
        pA_axis = prim_a["axis_point"] + sA * axA
        pB_axis = prim_b["axis_point"] + sB * axB
        if float(np.linalg.norm(pA_axis - pB_axis)) > max(tol, 1e-6) * (
            float(np.linalg.norm(w0)) + 1.0
        ):
            return None  # axes do not cross
        r = 0.5 * (rA + rB)
        ctr = 0.5 * (pA_axis + pB_axis)
        # Steinmetz: the two branch ellipses lie in the planes spanned by the
        # bisectors of the two axes.  Parameterise on cylinder A:
        #   x(φ)=r cosφ along eA1, y(φ)=r sinφ along eA2 (eA2 ⟂ axA),
        #   the axA-coordinate is ± sqrt(r² - (r sinφ)²) ... but with equal
        #   radius and perpendicular crossing axes the exact curves are the
        #   two planar ellipses below.
        eA = axA
        eB = axB
        e3 = np.cross(eA, eB)
        e3 = e3 / (np.linalg.norm(e3) + 1e-300)
        branches: List[dict] = []
        for sgn in (+1.0, -1.0):
            # Ellipse: point on cyl A at radial angle φ around axA in the
            # (e3, eB) circle, with axial position chosen so it also lies on
            # cyl B.  For equal r and perpendicular axes this reduces to:
            #   P(φ) = ctr + r cosφ e3 + r sinφ eB + sgn * r sinφ * eA  (no),
            # use the standard result: the intersection is two ellipses each
            # the image of a circle of radius r under a 45° shear, lying in
            # the planes n± = (eA ∓ eB)/√2.
            npn = (eA - sgn * eB)
            npn = npn / (np.linalg.norm(npn) + 1e-300)
            u1 = e3
            u2 = np.cross(npn, u1)
            u2 = u2 / (np.linalg.norm(u2) + 1e-300)
            th = np.linspace(0.0, 2.0 * math.pi, 121)
            pts = []
            for t in th:
                # Semi-axes: r along u1 (shared), r*sqrt(2) along u2 (sheared).
                p = ctr + r * math.cos(t) * u1 + r * math.sqrt(2.0) * math.sin(t) * u2
                pts.append(p.tolist())
            branches.append({
                "points": pts,
                "params_a": _empty_params(len(pts)),
                "params_b": _empty_params(len(pts)),
                "closed": True,
            })
        return branches

    return None


def _line_from_curve(c: NurbsCurve) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Return (P0, dir) if the curve is (numerically) a straight segment."""
    try:
        t0, t1 = _curve_param_range(c)
    except Exception:
        return None
    ts = np.linspace(t0, t1, 9)
    pts = np.array([_curve_eval(c, float(t)) for t in ts])
    p0 = pts[0]
    d = pts[-1] - pts[0]
    dn = np.linalg.norm(d)
    if dn < 1e-14:
        return None
    d = d / dn
    # Max deviation of interior points from the chord line.
    rel = pts - p0
    perp = rel - np.outer(rel @ d, d)
    if float(np.max(np.linalg.norm(perp, axis=1))) > 1e-9 * (dn + 1.0):
        return None
    return p0, d


def line_sphere_roots(
    p0: np.ndarray, d: np.ndarray, center: np.ndarray, radius: float,
    *, tol: float = 1e-12,
) -> List[float]:
    """Closed-form line∩sphere ray parameters s (point = p0 + s d).

    Returns 0, 1 (tangent) or 2 sorted roots, exact to machine precision.
    """
    p0 = np.asarray(p0, dtype=float)
    d = np.asarray(d, dtype=float)
    center = np.asarray(center, dtype=float)
    oc = p0 - center
    a = float(d @ d)
    b = 2.0 * float(oc @ d)
    c = float(oc @ oc) - float(radius) ** 2
    if a < 1e-300:
        return []
    disc = b * b - 4.0 * a * c
    if disc < -tol:
        return []
    if abs(disc) <= tol:
        return [-b / (2.0 * a)]
    sq = math.sqrt(disc)
    r1 = (-b - sq) / (2.0 * a)
    r2 = (-b + sq) / (2.0 * a)
    return sorted([r1, r2])


def line_plane_root(
    p0: np.ndarray, d: np.ndarray, plane_pt: np.ndarray, plane_n: np.ndarray,
    *, tol: float = 1e-12,
) -> Optional[float]:
    """Closed-form line∩plane ray parameter, or None if parallel."""
    p0 = np.asarray(p0, dtype=float)
    d = np.asarray(d, dtype=float)
    n = np.asarray(plane_n, dtype=float)
    denom = float(d @ n)
    if abs(denom) < tol:
        return None
    return float(((np.asarray(plane_pt, dtype=float) - p0) @ n) / denom)


# ---------------------------------------------------------------------------
# Marching (hardened)
# ---------------------------------------------------------------------------

def _signed_distance(
    surf_b: NurbsSurface, P: np.ndarray, uB: float, vB: float,
) -> Tuple[float, np.ndarray]:
    """Signed distance of P to surf_b near (uB,vB) and its 3-D gradient.

    Gradient ≈ outward unit normal of surf_b (∇ of the SDF of a smooth
    surface).  Used to recover a marching direction when the two surface
    normals are parallel (tangential branch) and the cross-product tangent
    degenerates.
    """
    PB = _surf_eval(surf_b, uB, vB)
    nB = _surf_normal(surf_b, uB, vB)
    sd = float((P - PB) @ nB)
    return sd, nB


def _march_branch(
    surf_a: NurbsSurface,
    surf_b: NurbsSurface,
    uA_seed: float, vA_seed: float,
    uB_seed: float, vB_seed: float,
    step: float,
    tol: float,
    max_steps: int,
) -> dict:
    """March in both directions from a seed to build one intersection branch.

    Hardening (GK-09):
      * Real loop detection — a branch is ``closed`` only when the march
        actually returns to the *seed* in parameter space (and 3-D), not via
        the old ``step*3`` endpoint heuristic.
      * Tangential branches — when ``|nA × nB|`` is ~0 the marching direction
        is rebuilt from the signed-distance-field gradient + surface curvature
        (second partials) instead of bailing out.
      * Boundary handling that records whether the branch terminated on a
        trim boundary (so an open branch is not mistaken for a closed loop).
    """
    uA_min, uA_max, vA_min, vA_max = _surface_param_range(surf_a)
    uB_min, uB_max, vB_min, vB_max = _surface_param_range(surf_b)
    seed_pt = (
        (_surf_eval(surf_a, uA_seed, vA_seed)
         + _surf_eval(surf_b, uB_seed, vB_seed)) * 0.5
    )

    def _tangent(uA, vA, uB, vB):
        """Marching tangent at the current point (curvature-aware fallback)."""
        nA = _surf_normal(surf_a, uA, vA)
        nB = _surf_normal(surf_b, uB, vB)
        tang = np.cross(nA, nB)
        t_nrm = np.linalg.norm(tang)
        if t_nrm >= 1e-9:
            return tang / t_nrm, False
        # Tangential / near-tangential: normals (anti-)parallel.  March along
        # the curve f=0 of the signed-distance field.  The branch direction is
        # the eigenvector of the relative second-fundamental form with the
        # smallest |curvature|; approximate it from the second partials of A.
        dpA_du, dpA_dv = _surf_partials(surf_a, uA, vA)
        suu, suv, svv = _surf_second_partials(surf_a, uA, vA)
        # Difference of normal curvatures along the two surface param dirs;
        # pick the in-tangent-plane direction minimising the SDF curvature so
        # the step stays on f=0 to second order.
        e_u = dpA_du / (np.linalg.norm(dpA_du) + 1e-300)
        e_v = dpA_dv / (np.linalg.norm(dpA_dv) + 1e-300)
        kuu = float(suu @ nA)
        kvv = float(svv @ nA)
        kuv = float(suv @ nA)
        # 2x2 shape-difference form eigenvector for the smaller |eigval|.
        m = np.array([[kuu, kuv], [kuv, kvv]])
        try:
            w, V = np.linalg.eigh(m)
            idx = int(np.argmin(np.abs(w)))
            vec = V[:, idx]
        except np.linalg.LinAlgError:
            vec = np.array([1.0, 0.0])
        dirv = vec[0] * e_u + vec[1] * e_v
        dn = np.linalg.norm(dirv)
        if dn < 1e-12:
            # last resort: any in-plane direction
            dirv = e_u
            dn = np.linalg.norm(dirv)
        return dirv / (dn + 1e-300), True

    def _on_boundary(uA, vA, uB, vB):
        b = tol * 10.0
        return (
            abs(uA - uA_min) < b or abs(uA - uA_max) < b or
            abs(vA - vA_min) < b or abs(vA - vA_max) < b or
            abs(uB - uB_min) < b or abs(uB - uB_max) < b or
            abs(vB - vB_min) < b or abs(vB - vB_max) < b
        )

    def _collect(sign):
        pts, pa, pb = [], [], []
        uA, vA, uB, vB = uA_seed, vA_seed, uB_seed, vB_seed
        hit_boundary = False
        returned_to_seed = False
        prev_dir = None
        n_iter = max(4, max_steps // 2)
        for it in range(n_iter):
            tang, tangential = _tangent(uA, vA, uB, vB)
            if prev_dir is not None and float(tang @ prev_dir) < 0.0:
                tang = -tang  # keep a consistent travel direction
            prev_dir = tang

            PA = _surf_eval(surf_a, uA, vA)
            PB = _surf_eval(surf_b, uB, vB)
            P_curr = (PA + PB) * 0.5
            P_next = P_curr + sign * step * tang

            # Tangential branch: pull the predictor back onto f=0 of surf_b's
            # signed-distance field (one Newton step on the SDF) before the
            # tangent-plane projection.  This keeps the march on the
            # intersection when the cross-product tangent has degenerated.
            if tangential:
                sd, grad = _signed_distance(surf_b, P_next, uB, vB)
                P_next = P_next - sd * grad

            dpA_du, dpA_dv = _surf_partials(surf_a, uA, vA)
            dpB_du, dpB_dv = _surf_partials(surf_b, uB, vB)

            delta = P_next - PA
            nuA = np.dot(delta, dpA_du) / (np.dot(dpA_du, dpA_du) + 1e-15)
            nvA = np.dot(delta, dpA_dv) / (np.dot(dpA_dv, dpA_dv) + 1e-15)
            uA_g = float(np.clip(uA + nuA, uA_min, uA_max))
            vA_g = float(np.clip(vA + nvA, vA_min, vA_max))

            delta_b = P_next - PB
            nuB = np.dot(delta_b, dpB_du) / (np.dot(dpB_du, dpB_du) + 1e-15)
            nvB = np.dot(delta_b, dpB_dv) / (np.dot(dpB_dv, dpB_dv) + 1e-15)
            uB_g = float(np.clip(uB + nuB, uB_min, uB_max))
            vB_g = float(np.clip(vB + nvB, vB_min, vB_max))

            refined = _newton_surf_surf_point(
                surf_a, surf_b, uA_g, vA_g, uB_g, vB_g, tol=tol
            )
            if refined is None:
                break
            uA_new, vA_new, uB_new, vB_new = refined

            PA_new = _surf_eval(surf_a, uA_new, vA_new)
            PB_new = _surf_eval(surf_b, uB_new, vB_new)
            P_new = (PA_new + PB_new) * 0.5
            if np.linalg.norm(P_new - P_curr) < tol * 0.1:
                break

            pts.append(P_new.tolist())
            pa.append([uA_new, vA_new])
            pb.append([uB_new, vB_new])
            uA, vA, uB, vB = uA_new, vA_new, uB_new, vB_new

            # Real loop detection: returned to the seed in 3-D after a few
            # genuine steps ⇒ closed branch.
            if it >= 3 and np.linalg.norm(P_new - seed_pt) < step * 0.75:
                returned_to_seed = True
                break

            if _on_boundary(uA_new, vA_new, uB_new, vB_new):
                hit_boundary = True
                break
        return pts, pa, pb, hit_boundary, returned_to_seed

    fwd_pts, fwd_pa, fwd_pb, fwd_bnd, fwd_loop = _collect(+1.0)
    if fwd_loop:
        # Forward march closed the loop on its own.
        all_pts = [seed_pt.tolist()] + fwd_pts
        all_pa = [[uA_seed, vA_seed]] + fwd_pa
        all_pb = [[uB_seed, vB_seed]] + fwd_pb
        return {"points": all_pts, "params_a": all_pa,
                "params_b": all_pb, "closed": True}

    bwd_pts, bwd_pa, bwd_pb, bwd_bnd, bwd_loop = _collect(-1.0)

    all_pts = list(reversed(bwd_pts)) + [seed_pt.tolist()] + fwd_pts
    all_pa = list(reversed(bwd_pa)) + [[uA_seed, vA_seed]] + fwd_pa
    all_pb = list(reversed(bwd_pb)) + [[uB_seed, vB_seed]] + fwd_pb

    # Closed iff BOTH directions ran free (no trim boundary) and the two free
    # ends meet — i.e. a genuine return-to-start loop, not a heuristic.
    closed = False
    if len(all_pts) >= 4 and not fwd_bnd and not bwd_bnd:
        p0 = np.array(all_pts[0])
        p1 = np.array(all_pts[-1])
        if np.linalg.norm(p1 - p0) < step * 1.5:
            closed = True

    return {"points": all_pts, "params_a": all_pa,
            "params_b": all_pb, "closed": closed}


# ---------------------------------------------------------------------------
# surface_surface_intersect
# ---------------------------------------------------------------------------

def surface_surface_intersect(
    surf_a: NurbsSurface,
    surf_b: NurbsSurface,
    *,
    tol: float = _DEFAULT_TOL,
    samples_u: int = _DEFAULT_SAMPLES_UV,
    samples_v: int = _DEFAULT_SAMPLES_UV,
    step: float = _DEFAULT_MARCH_STEP,
    max_steps: int = _DEFAULT_MAX_STEPS,
) -> dict:
    """Compute intersection curve(s) between two NurbsSurfaces.

    Parameters
    ----------
    surf_a, surf_b : NurbsSurface
    tol : float
    samples_u, samples_v : int  -- Grid resolution for seeding.
    step : float  -- Marching step (scaled by bounding-box diagonal).
    max_steps : int

    Returns
    -------
    dict with ok, reason, branches, branch_count.  Never raises.
    """
    try:
        return _surface_surface_intersect_impl(
            surf_a, surf_b,
            tol=tol, samples_u=samples_u, samples_v=samples_v,
            step=step, max_steps=max_steps,
        )
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"surface_surface_intersect internal error: {exc}",
            "branches": [],
            "branch_count": 0,
        }


def _surface_surface_intersect_impl(
    surf_a: NurbsSurface,
    surf_b: NurbsSurface,
    *,
    tol: float,
    samples_u: int,
    samples_v: int,
    step: float,
    max_steps: int,
) -> dict:
    if not isinstance(surf_a, NurbsSurface):
        return {"ok": False, "reason": "surf_a must be a NurbsSurface",
                "branches": [], "branch_count": 0}
    if not isinstance(surf_b, NurbsSurface):
        return {"ok": False, "reason": "surf_b must be a NurbsSurface",
                "branches": [], "branch_count": 0}

    # ---- GK-10: closed-form specialisation when both are analytic ----
    try:
        prim_a = _classify_primitive(surf_a, tol)
        prim_b = _classify_primitive(surf_b, tol)
        if prim_a is not None and prim_b is not None:
            analytic = _analytic_ssi(prim_a, prim_b, tol)
            if analytic is not None:
                return {
                    "ok": True,
                    "reason": "",
                    "branches": analytic,
                    "branch_count": len(analytic),
                }
    except Exception:
        pass  # fall through to the hardened marcher

    su = max(4, int(samples_u))
    sv = max(4, int(samples_v))

    uA_min, uA_max, vA_min, vA_max = _surface_param_range(surf_a)
    uB_min, uB_max, vB_min, vB_max = _surface_param_range(surf_b)

    # Deterministic grid (fixed, reproducible iteration order).
    uA_vals = np.linspace(uA_min, uA_max, su + 1)
    vA_vals = np.linspace(vA_min, vA_max, sv + 1)
    uB_vals = np.linspace(uB_min, uB_max, su + 1)
    vB_vals = np.linspace(vB_min, vB_max, sv + 1)

    pA = np.array([[_surf_eval(surf_a, float(u), float(v))
                    for v in vA_vals] for u in uA_vals])
    pB = np.array([[_surf_eval(surf_b, float(u), float(v))
                    for v in vB_vals] for u in uB_vals])

    # Estimate step size from bounding boxes
    bboxA = np.max(pA.reshape(-1, 3), axis=0) - np.min(pA.reshape(-1, 3), axis=0)
    bboxB = np.max(pB.reshape(-1, 3), axis=0) - np.min(pB.reshape(-1, 3), axis=0)
    diag_avg = (np.linalg.norm(bboxA) + np.linalg.norm(bboxB)) * 0.5
    actual_step = step if diag_avg < 1e-10 else step * diag_avg

    def _collect_seeds(uAv, vAv, uBv, vBv) -> List[Tuple[float, float, float, float]]:
        """Nearest-pair grid seeding with a deterministic ordered scan."""
        pa_grid = np.array([[_surf_eval(surf_a, float(u), float(v))
                             for v in vAv] for u in uAv])
        pb_grid = np.array([[_surf_eval(surf_b, float(u), float(v))
                             for v in vBv] for u in uBv])
        nB_v = len(vBv)
        seed_tol = max(tol * 1e3, actual_step * 2)
        out: List[Tuple[float, float, float, float]] = []
        for i in range(len(uAv)):
            for j in range(len(vAv)):
                d = np.linalg.norm(
                    pb_grid.reshape(-1, 3) - pa_grid[i, j], axis=1
                )
                k = int(np.argmin(d))
                if d[k] < seed_tol:
                    out.append((
                        float(uAv[i]), float(vAv[j]),
                        float(uBv[k // nB_v]), float(vBv[k % nB_v]),
                    ))
        return out

    raw_seeds = _collect_seeds(uA_vals, vA_vals, uB_vals, vB_vals)

    # Refine + merge (deterministic order preserved).
    def _refine_and_merge(raws):
        refined: List[Tuple[float, float, float, float]] = []
        for (uA, vA, uB, vB) in raws:
            r = _newton_surf_surf_point(surf_a, surf_b, uA, vA, uB, vB, tol=tol)
            if r is not None:
                refined.append(r)
        merged: List[Tuple[float, float, float, float]] = []
        for s in refined:
            PA = _surf_eval(surf_a, s[0], s[1])
            if not any(
                np.linalg.norm(PA - _surf_eval(surf_a, m[0], m[1]))
                < actual_step * 2
                for m in merged
            ):
                merged.append(s)
        return merged

    merged_seeds = _refine_and_merge(raw_seeds)

    branches: List[dict] = []
    visited_pts: List[np.ndarray] = []

    def _run_seed(seed) -> bool:
        uA_s, vA_s, uB_s, vB_s = seed
        sp = _surf_eval(surf_a, uA_s, vA_s)
        if any(np.linalg.norm(sp - vp) < actual_step * 1.5
               for vp in visited_pts):
            return False
        branch = _march_branch(
            surf_a, surf_b, uA_s, vA_s, uB_s, vB_s,
            step=actual_step, tol=tol, max_steps=max_steps,
        )
        if len(branch["points"]) < _MIN_BRANCH_PTS:
            return False
        branches.append(branch)
        for pt in branch["points"]:
            visited_pts.append(np.array(pt))
        return True

    for seed in merged_seeds:
        _run_seed(seed)

    # ---- GK-09: small-loop adaptive reseed ----
    # A loop smaller than the seed grid spacing is invisible to the coarse
    # grid.  Re-scan on a refined sub-grid over cells whose nearest-surface
    # distance is small but which no existing branch passes through.
    try:
        sub = 2
        fu = np.linspace(uA_min, uA_max, su * sub + 1)
        fv = np.linspace(vA_min, vA_max, sv * sub + 1)
        fuB = np.linspace(uB_min, uB_max, su * sub + 1)
        fvB = np.linspace(vB_min, vB_max, sv * sub + 1)
        fine_seeds = _collect_seeds(fu, fv, fuB, fvB)
        fine_merged = _refine_and_merge(fine_seeds)
        for seed in fine_merged:
            _run_seed(seed)
    except Exception:
        pass

    return {
        "ok": True,
        "reason": "",
        "branches": branches,
        "branch_count": len(branches),
    }


# ---------------------------------------------------------------------------
# Newton: curve-curve
# ---------------------------------------------------------------------------

def _newton_curve_curve(
    curve_a: NurbsCurve,
    curve_b: NurbsCurve,
    ta0: float,
    tb0: float,
    *,
    tol: float = _DEFAULT_TOL,
    max_iter: int = _MAX_NEWTON_ITER,
) -> Optional[Tuple[float, float]]:
    """Newton refinement for curve-curve intersection.

    Solves F(ta, tb) = curve_a(ta) - curve_b(tb) = 0  (3 eq, 2 unknowns).
    Returns (ta, tb) or None.
    """
    ta_min, ta_max = _curve_param_range(curve_a)
    tb_min, tb_max = _curve_param_range(curve_b)

    ta = float(np.clip(ta0, ta_min, ta_max))
    tb = float(np.clip(tb0, tb_min, tb_max))

    h_a = max(1e-6, (ta_max - ta_min) * 1e-4)
    h_b = max(1e-6, (tb_max - tb_min) * 1e-4)

    for _ in range(max_iter):
        A = _curve_eval(curve_a, ta)
        B = _curve_eval(curve_b, tb)
        F = A - B
        if np.linalg.norm(F) < tol:
            return (ta, tb)

        ta_p = min(ta_max, ta + h_a); ta_m = max(ta_min, ta - h_a)
        tb_p = min(tb_max, tb + h_b); tb_m = max(tb_min, tb - h_b)

        dA_dt = (_curve_eval(curve_a, ta_p) - _curve_eval(curve_a, ta_m)) / (ta_p - ta_m + 1e-15)
        dB_dt = (_curve_eval(curve_b, tb_p) - _curve_eval(curve_b, tb_m)) / (tb_p - tb_m + 1e-15)

        # J shape (3, 2): columns [dA_dt, -dB_dt]
        J = np.column_stack([dA_dt, -dB_dt])
        JtJ = J.T @ J
        Jtf = J.T @ (-F)
        det = JtJ[0, 0] * JtJ[1, 1] - JtJ[0, 1] * JtJ[1, 0]
        if abs(det) < 1e-20:
            break
        delta_ta = (JtJ[1, 1] * Jtf[0] - JtJ[0, 1] * Jtf[1]) / det
        delta_tb = (JtJ[0, 0] * Jtf[1] - JtJ[1, 0] * Jtf[0]) / det

        ta_new = float(np.clip(ta + delta_ta, ta_min, ta_max))
        tb_new = float(np.clip(tb + delta_tb, tb_min, tb_max))

        if abs(ta_new - ta) < tol * 1e-2 and abs(tb_new - tb) < tol * 1e-2:
            return (ta_new, tb_new)
        ta, tb = ta_new, tb_new

    A = _curve_eval(curve_a, ta); B = _curve_eval(curve_b, tb)
    if np.linalg.norm(A - B) < tol * 1e3:
        return (ta, tb)
    return None


# ---------------------------------------------------------------------------
# curve_curve_intersect
# ---------------------------------------------------------------------------

def curve_curve_intersect(
    curve_a: NurbsCurve,
    curve_b: NurbsCurve,
    *,
    tol: float = _DEFAULT_TOL,
    samples_a: int = _DEFAULT_SAMPLES_C,
    samples_b: int = _DEFAULT_SAMPLES_C,
) -> List[dict]:
    """Find all intersection points between two NurbsCurves.

    Parameters
    ----------
    curve_a, curve_b : NurbsCurve
    tol : float
    samples_a, samples_b : int  -- Sampling intervals per curve.

    Returns
    -------
    list of dict with keys: ta, tb, point.  Never raises.
    """
    try:
        return _curve_curve_intersect_impl(
            curve_a, curve_b, tol=tol,
            samples_a=samples_a, samples_b=samples_b,
        )
    except Exception:
        return []


def _curve_curve_intersect_impl(
    curve_a: NurbsCurve,
    curve_b: NurbsCurve,
    *,
    tol: float,
    samples_a: int,
    samples_b: int,
) -> List[dict]:
    if not isinstance(curve_a, NurbsCurve):
        return []
    if not isinstance(curve_b, NurbsCurve):
        return []

    sa = max(4, int(samples_a))
    sb = max(4, int(samples_b))

    ta_min, ta_max = _curve_param_range(curve_a)
    tb_min, tb_max = _curve_param_range(curve_b)

    ta_vals = np.linspace(ta_min, ta_max, sa + 1)
    tb_vals = np.linspace(tb_min, tb_max, sb + 1)

    a_pts = [_curve_eval(curve_a, float(t)) for t in ta_vals]
    b_pts = [_curve_eval(curve_b, float(t)) for t in tb_vals]

    candidates: List[Tuple[float, float]] = []
    for i in range(sa):
        a_seg = [a_pts[i], a_pts[i + 1]]
        a_lo, a_hi = _aabb(a_seg)
        for j in range(sb):
            b_seg = [b_pts[j], b_pts[j + 1]]
            b_lo, b_hi = _aabb(b_seg)
            if _aabb_overlap(a_lo, a_hi, b_lo, b_hi, tol * 10):
                ta0 = (ta_vals[i] + ta_vals[i + 1]) * 0.5
                tb0 = (tb_vals[j] + tb_vals[j + 1]) * 0.5
                candidates.append((ta0, tb0))

    hits: List[dict] = []
    for ta0, tb0 in candidates:
        result = _newton_curve_curve(curve_a, curve_b, ta0, tb0, tol=tol)
        if result is None:
            continue
        ta_ref, tb_ref = result
        A = _curve_eval(curve_a, ta_ref)
        B = _curve_eval(curve_b, tb_ref)
        if np.linalg.norm(A - B) > tol * 1e3:
            continue
        pt = ((A + B) * 0.5).tolist()
        hits.append({"ta": ta_ref, "tb": tb_ref, "point": pt})

    return _merge_close_hits(hits, tol)


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
    # curve_surface_intersect tool
    # ------------------------------------------------------------------

    _CSI_SPEC = ToolSpec(
        name="curve_surface_intersect",
        description=(
            "Find all intersection points between a NURBS curve and a NURBS surface. "
            "Returns each intersection point with its curve parameter t and surface "
            "parameters (u, v).  Uses subdivision + AABB cull + Newton refinement.\n"
            "\n"
            "Returns:\n"
            "  ok           : bool\n"
            "  intersections: list of {t, u, v, point:[x,y,z]}\n"
            "  count        : int\n"
            "\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "curve_control_points": {
                    "type": "array",
                    "description": "[[x,y,z], ...] control points of the NURBS curve.",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "curve_degree": {"type": "integer"},
                "curve_knots": {"type": "array", "items": {"type": "number"}},
                "surface_control_points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "surface_degree_u": {"type": "integer"},
                "surface_degree_v": {"type": "integer"},
                "surface_num_u": {"type": "integer"},
                "surface_num_v": {"type": "integer"},
                "tolerance": {"type": "number"},
            },
            "required": [
                "curve_control_points", "curve_degree", "curve_knots",
                "surface_control_points", "surface_degree_u", "surface_degree_v",
                "surface_num_u", "surface_num_v",
            ],
        },
    )

    @register(_CSI_SPEC)
    async def run_curve_surface_intersect(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")
        try:
            c_cp = np.array(a.get("curve_control_points", []), dtype=float)
            c_deg = int(a["curve_degree"])
            c_knots = np.asarray(a["curve_knots"], dtype=float)
            curve = NurbsCurve(degree=c_deg, control_points=c_cp, knots=c_knots)
        except Exception as exc:
            return err_payload(f"invalid curve: {exc}", "BAD_ARGS")
        try:
            nu = int(a["surface_num_u"]); nv = int(a["surface_num_v"])
            scp = np.array(a.get("surface_control_points", []), dtype=float).reshape(nu, nv, -1)
            deg_u = int(a["surface_degree_u"]); deg_v = int(a["surface_degree_v"])
            def _mk(n, d):
                inner = max(0, n - d - 1)
                return np.concatenate([
                    np.zeros(d + 1),
                    np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else np.array([]),
                    np.ones(d + 1),
                ])
            surface = NurbsSurface(
                degree_u=deg_u, degree_v=deg_v, control_points=scp,
                knots_u=_mk(nu, deg_u), knots_v=_mk(nv, deg_v),
            )
        except Exception as exc:
            return err_payload(f"invalid surface: {exc}", "BAD_ARGS")
        tol = float(a.get("tolerance", _DEFAULT_TOL))
        hits = curve_surface_intersect(curve, surface, tol=tol)
        return ok_payload({"ok": True, "intersections": hits, "count": len(hits)})

    # ------------------------------------------------------------------
    # surface_surface_intersect tool
    # ------------------------------------------------------------------

    _SSI_SPEC = ToolSpec(
        name="surface_surface_intersect",
        description=(
            "Compute intersection curve(s) between two NURBS surfaces using a marching "
            "method.  Returns polyline branches with 3-D points and parameter pairs.\n"
            "\n"
            "Returns:\n"
            "  ok           : bool\n"
            "  branch_count : int\n"
            "  branches     : list of {points, params_a, params_b, closed}\n"
            "\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "surf_a_control_points": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                "surf_a_degree_u": {"type": "integer"},
                "surf_a_degree_v": {"type": "integer"},
                "surf_a_num_u": {"type": "integer"},
                "surf_a_num_v": {"type": "integer"},
                "surf_b_control_points": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                "surf_b_degree_u": {"type": "integer"},
                "surf_b_degree_v": {"type": "integer"},
                "surf_b_num_u": {"type": "integer"},
                "surf_b_num_v": {"type": "integer"},
                "tolerance": {"type": "number"},
                "step": {"type": "number"},
            },
            "required": [
                "surf_a_control_points", "surf_a_degree_u", "surf_a_degree_v",
                "surf_a_num_u", "surf_a_num_v",
                "surf_b_control_points", "surf_b_degree_u", "surf_b_degree_v",
                "surf_b_num_u", "surf_b_num_v",
            ],
        },
    )

    @register(_SSI_SPEC)
    async def run_surface_surface_intersect(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        def _build(prefix):
            nu = int(a[f"{prefix}num_u"]); nv = int(a[f"{prefix}num_v"])
            cp = np.array(a.get(f"{prefix}control_points", []), dtype=float).reshape(nu, nv, -1)
            du = int(a[f"{prefix}degree_u"]); dv = int(a[f"{prefix}degree_v"])
            def _mk(n, d):
                inner = max(0, n - d - 1)
                return np.concatenate([
                    np.zeros(d + 1),
                    np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else np.array([]),
                    np.ones(d + 1),
                ])
            return NurbsSurface(degree_u=du, degree_v=dv, control_points=cp,
                                knots_u=_mk(nu, du), knots_v=_mk(nv, dv))

        try:
            sA = _build("surf_a_"); sB = _build("surf_b_")
        except Exception as exc:
            return err_payload(f"invalid surface: {exc}", "BAD_ARGS")

        tol = float(a.get("tolerance", _DEFAULT_TOL))
        step = float(a.get("step", _DEFAULT_MARCH_STEP))
        result = surface_surface_intersect(sA, sB, tol=tol, step=step)
        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")
        return ok_payload(result)
