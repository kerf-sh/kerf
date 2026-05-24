"""
kerf_cad_core.reverse_engineering.fit_cone — Cone primitive fitting.

A cone is parameterised by:
    apex    : [x, y, z]      — the apex point
    axis    : [ax, ay, az]   — unit vector along the cone axis (from apex)
    half_angle : float       — half-aperture angle in radians (0 < α < π/2)

The algebraic residual for point p is:
    r(p) = cos(α) * ||p - apex|| - dot(p - apex, axis)

which equals 0 when p lies exactly on the cone surface.

Two-stage approach
------------------
1. fit_cone_direct  — linear seed using PCA axis + linear-regression apex.
2. refine_cone_lm   — Levenberg-Marquardt (LM) non-linear refinement.
3. ransac_fit_cone  — RANSAC wrapper calling seed → LM refinement.

Linear-regression apex finder
------------------------------
For a cone with known axis direction a:
  - Each point p has axial position t_i = dot(p - centroid, a)
  - Each point p has radial distance r_i = |p - centroid - t_i * a|
  - A perfect cone has r_i = tan(α) * (t_i - t_apex)  [linear in t]
So we fit r vs t by least squares: r = m * t + b, giving:
    tan(α) = m
    t_apex = -b / m  (i.e. where the line r(t)=0 crosses)
    apex = centroid + t_apex * a

Design notes
------------
- Pure Python + math.  No external deps.
- LM operates on 6 parameters: [apex_x, apex_y, apex_z, theta, phi, alpha].
- The axis is kept as a unit vector via a (θ, φ) spherical representation
  during LM so that the norm constraint is never violated.
- Linear algebra helpers (_dot, _sub, _scale, _norm, _normalise, _centroid,
  _covariance3, _jacobi3) are imported from scan.fit to avoid duplication.

Author: imranparuk
"""
from __future__ import annotations

import math
import random
from typing import Any

# Delegate shared linalg helpers to the canonical implementation in scan.fit
# rather than duplicating them here.
from kerf_cad_core.scan.fit import (
    _dot,
    _sub,
    _scale,
    _norm,
    _normalise,
    _centroid,
    _covariance3,
    _jacobi3,
)


# ---------------------------------------------------------------------------
# Cone residual
# ---------------------------------------------------------------------------

def _cone_residual(p: list[float], apex: list[float], axis: list[float], alpha: float) -> float:
    """Signed algebraic residual: cos(α)·||p-apex|| - dot(p-apex, axis)."""
    v = _sub(p, apex)
    d = _norm(v)
    if d < 1e-14:
        return 0.0
    return math.cos(alpha) * d - _dot(v, axis)


def _dist_to_cone(p: list[float], res: dict[str, Any]) -> float:
    """Unsigned residual used for RANSAC inlier counting."""
    return abs(_cone_residual(p, res["apex"], res["axis"], res["half_angle"]))


# ---------------------------------------------------------------------------
# Linear least-squares 2-D line fit: r = m*t + b
# ---------------------------------------------------------------------------

def _linreg(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Fit y = m*x + b.  Returns (m, b)."""
    n = len(xs)
    if n < 2:
        return 0.0, 0.0
    sx = sum(xs); sy = sum(ys)
    sxx = sum(x*x for x in xs); sxy = sum(x*y for x, y in zip(xs, ys))
    denom = n*sxx - sx*sx
    if abs(denom) < 1e-14:
        return 0.0, sy / n
    m = (n*sxy - sx*sy) / denom
    b = (sy - m*sx) / n
    return m, b


# ---------------------------------------------------------------------------
# Closed-form cone seed (PCA axis + linear regression apex)
# ---------------------------------------------------------------------------

def fit_cone_direct(pts: list[list[float]]) -> dict[str, Any]:
    """Linear seed for a cone using PCA axis + linear-regression apex.

    Algorithm
    ---------
    1. Compute the PCA axis (largest eigenvalue direction).
    2. For each point p, compute:
         t_i = dot(p - centroid, axis)  [axial position]
         r_i = |p - centroid - t_i * axis|  [radial distance]
    3. Fit a line r = m*t + b by least squares.
       - slope m = tan(α)   → half_angle = atan(m) if m > 0
       - intercept b and slope m give apex position: t_apex = -b/m
       - apex = centroid + t_apex * axis
    4. Verify the apex makes sense (all points have t_i - t_apex > 0,
       or flip axis direction).

    Parameters
    ----------
    pts : list of [x, y, z]
        Minimum 6 points.

    Returns
    -------
    dict with ok, primitive, apex, axis, half_angle (rad), inlier_ratio, residual.
    """
    if len(pts) < 6:
        return {"ok": False, "reason": f"need ≥6 points for cone fit; got {len(pts)}"}

    c = _centroid(pts)
    cov = _covariance3(pts, c)
    vals, vecs = _jacobi3(cov)

    if abs(vals[2]) < 1e-14:
        return {"ok": False, "reason": "degenerate point cloud for cone fit"}

    # Try all three eigenvectors as axis candidates; pick the one that
    # gives the best linear fit (smallest r² of the linear model).
    best_candidate = None
    best_r2 = float("inf")

    for eig_idx in range(3):
        axis_cand = _normalise(vecs[eig_idx])
        ts_cand = [_dot(_sub(p, c), axis_cand) for p in pts]
        rs_cand = []
        for i, p in enumerate(pts):
            along_vec = _scale(axis_cand, ts_cand[i])
            perp_vec = _sub(_sub(p, c), along_vec)
            rs_cand.append(_norm(perp_vec))

        # Try both orientations
        for flip in (1, -1):
            ts_try = [flip * t for t in ts_cand]
            m_try, b_try = _linreg(ts_try, rs_cand)
            if m_try <= 1e-8:
                continue
            # r² = residual sum of squares of the linear model
            r2 = sum((rs_cand[i] - (m_try * ts_try[i] + b_try))**2 for i in range(len(pts)))
            if r2 < best_r2:
                best_r2 = r2
                axis_use = axis_cand if flip == 1 else [-axis_cand[0], -axis_cand[1], -axis_cand[2]]
                best_candidate = (axis_use, m_try, b_try)

    if best_candidate is None:
        return {"ok": False, "reason": "cone fit: cannot find axis with positive slope"}

    axis, m, b = best_candidate

    # Apex axial position: where r → 0, i.e. m*t_apex + b = 0 → t_apex = -b/m
    t_apex = -b / m
    apex = [c[0] + t_apex * axis[0], c[1] + t_apex * axis[1], c[2] + t_apex * axis[2]]
    half_angle = math.atan(m)  # m = tan(α)
    half_angle = max(1e-4, min(math.pi/2 - 1e-4, half_angle))

    # Compute residuals
    residuals = [abs(_cone_residual(p, apex, axis, half_angle)) for p in pts]
    mean_res = sum(residuals) / len(residuals)

    return {
        "ok": True,
        "primitive": "cone",
        "apex": apex,
        "axis": axis,
        "half_angle": half_angle,
        "inlier_ratio": 1.0,
        "residual": mean_res,
    }


# ---------------------------------------------------------------------------
# LM refinement
# ---------------------------------------------------------------------------

def _axis_to_spherical(axis: list[float]) -> tuple[float, float]:
    """Convert unit axis vector to (theta, phi) spherical angles."""
    az = max(-1.0, min(1.0, axis[2]))
    theta = math.acos(az)
    phi = math.atan2(axis[1], axis[0])
    return theta, phi


def _spherical_to_axis(theta: float, phi: float) -> list[float]:
    """Convert (theta, phi) spherical angles back to unit vector."""
    st = math.sin(theta)
    return [st * math.cos(phi), st * math.sin(phi), math.cos(theta)]


def _solve_nxn(A: list[list[float]], b: list[float]) -> list[float] | None:
    """Solve n×n system via Gaussian elimination with partial pivoting."""
    n = len(b)
    M = [A[i][:] + [b[i]] for i in range(n)]
    for col in range(n):
        max_row = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[max_row] = M[max_row], M[col]
        if abs(M[col][col]) < 1e-14:
            return None
        piv = M[col][col]
        for row in range(col+1, n):
            f = M[row][col] / piv
            for k in range(col, n+1):
                M[row][k] -= f * M[col][k]
    x = [0.0]*n
    for i in range(n-1, -1, -1):
        x[i] = M[i][n]
        for j in range(i+1, n):
            x[i] -= M[i][j]*x[j]
        if abs(M[i][i]) < 1e-14:
            return None
        x[i] /= M[i][i]
    return x


def refine_cone_lm(
    pts: list[list[float]],
    seed: dict[str, Any],
    max_iter: int = 100,
    tol: float = 1e-9,
    lam_init: float = 1e-3,
) -> dict[str, Any]:
    """Levenberg-Marquardt refinement of cone parameters.

    Refines apex (3 params), axis direction (2 spherical params θ,φ),
    and half-angle (1 param) — total 6 parameters.

    The residual for point pᵢ is:
        f(pᵢ) = cos(α) * ||pᵢ - apex|| - dot(pᵢ - apex, axis)

    Parameters
    ----------
    pts : list of [x,y,z]
        Inlier points to refine on.
    seed : dict
        Output of fit_cone_direct or ransac_fit_cone (without refine).
    max_iter : int
        Maximum LM iterations.
    tol : float
        Convergence tolerance on parameter step norm.
    lam_init : float
        Initial LM damping factor.

    Returns
    -------
    dict  — same structure as fit_cone_direct output, with refined params.
            Falls back to seed if LM diverges or fails.
    """
    if not seed.get("ok"):
        return seed
    if len(pts) < 6:
        return seed

    # Unpack initial parameters
    apex = list(seed["apex"])
    axis = _normalise(list(seed["axis"]))
    alpha = float(seed["half_angle"])

    theta, phi = _axis_to_spherical(axis)
    # Param vector: [apex_x, apex_y, apex_z, theta, phi, alpha]
    params = [apex[0], apex[1], apex[2], theta, phi, alpha]

    def _residuals(p_vec: list[float]) -> list[float]:
        ax, ay, az_p = p_vec[0], p_vec[1], p_vec[2]
        th, ph = p_vec[3], p_vec[4]
        al = max(1e-4, min(math.pi/2 - 1e-4, p_vec[5]))
        ax_vec = _spherical_to_axis(th, ph)
        apex_v = [ax, ay, az_p]
        cos_al = math.cos(al)
        res = []
        for pt in pts:
            v = _sub(pt, apex_v)
            d = _norm(v)
            if d < 1e-14:
                res.append(0.0)
            else:
                res.append(cos_al * d - _dot(v, ax_vec))
        return res

    def _cost(p_vec: list[float]) -> float:
        r = _residuals(p_vec)
        return sum(x*x for x in r)

    best_cost = _cost(params)
    best_params = params[:]
    lam = lam_init
    eps = 1e-6  # central finite-difference step
    n_pts = len(pts)

    for _ in range(max_iter):
        res = _residuals(params)
        cost = sum(x*x for x in res)
        if cost < best_cost:
            best_cost = cost
            best_params = params[:]

        # Build Jacobian J (n_pts × 6) via central finite differences
        J = [[0.0]*6 for _ in range(n_pts)]
        for j in range(6):
            p_plus = params[:]
            p_plus[j] += eps
            r_plus = _residuals(p_plus)
            p_minus = params[:]
            p_minus[j] -= eps
            r_minus = _residuals(p_minus)
            for i in range(n_pts):
                J[i][j] = (r_plus[i] - r_minus[i]) / (2.0 * eps)

        # JtJ and Jt*r
        JtJ = [[0.0]*6 for _ in range(6)]
        Jtr = [0.0]*6
        for i in range(n_pts):
            for r_i in range(6):
                Jtr[r_i] += J[i][r_i] * res[i]
                for c_i in range(6):
                    JtJ[r_i][c_i] += J[i][r_i] * J[i][c_i]

        # Damped normal equations: (JtJ + lam*I) delta = -Jtr
        improved = False
        lam_trial = lam
        for _ in range(12):
            A_mat = [[JtJ[r_i][c_i] + (lam_trial if r_i == c_i else 0.0)
                      for c_i in range(6)] for r_i in range(6)]
            b_vec = [-Jtr[i] for i in range(6)]
            delta = _solve_nxn(A_mat, b_vec)
            if delta is None:
                lam_trial *= 10.0
                continue
            new_params = [params[k] + delta[k] for k in range(6)]
            new_params[5] = max(1e-4, min(math.pi/2 - 1e-4, new_params[5]))
            new_cost = _cost(new_params)
            if new_cost < cost:
                params = new_params
                lam = max(lam_trial * 0.1, 1e-12)
                improved = True
                # Convergence check
                step_norm = math.sqrt(sum(d*d for d in delta))
                if step_norm < tol:
                    break
                break
            lam_trial *= 10.0
        if not improved:
            break

    # Use best params found
    p = best_params
    apex_refined = [p[0], p[1], p[2]]
    axis_refined = _normalise(_spherical_to_axis(p[3], p[4]))
    alpha_refined = max(1e-4, min(math.pi/2 - 1e-4, p[5]))

    # Normalise: axis should point from apex toward the body of the cone.
    # Verify by checking if the mean axial projection of (pts - apex) is positive.
    mean_proj = sum(_dot(_sub(pt, apex_refined), axis_refined) for pt in pts) / len(pts)
    if mean_proj < 0:
        axis_refined = [-axis_refined[0], -axis_refined[1], -axis_refined[2]]
        alpha_refined = math.pi - alpha_refined
        alpha_refined = max(1e-4, min(math.pi/2 - 1e-4, alpha_refined))
        # Re-estimate alpha from data with flipped axis
        angles = []
        for pt in pts:
            vv = _sub(pt, apex_refined)
            d = _norm(vv)
            if d < 1e-10:
                continue
            cos_a = _dot(vv, axis_refined) / d
            cos_a = max(-1.0, min(1.0, cos_a))
            a = math.acos(cos_a)
            if 0.01 < a < math.pi/2 - 0.01:
                angles.append(a)
        if angles:
            alpha_refined = sum(angles) / len(angles)
            alpha_refined = max(1e-4, min(math.pi/2 - 1e-4, alpha_refined))

    residuals = [abs(_cone_residual(pt, apex_refined, axis_refined, alpha_refined)) for pt in pts]
    mean_res = sum(residuals) / len(residuals)

    return {
        "ok": True,
        "primitive": "cone",
        "apex": apex_refined,
        "axis": axis_refined,
        "half_angle": alpha_refined,
        "inlier_ratio": seed.get("inlier_ratio", 1.0),
        "residual": mean_res,
        "lm_refined": True,
    }


# ---------------------------------------------------------------------------
# RANSAC wrapper
# ---------------------------------------------------------------------------

_DEFAULT_SEED_INT = 42
_RANSAC_ITERS = 200


def ransac_fit_cone(
    pts: list[list[float]],
    threshold: float = 0.01,
    n_iters: int = _RANSAC_ITERS,
    seed: int = _DEFAULT_SEED_INT,
    refine: bool = True,
) -> dict[str, Any]:
    """RANSAC cone fit with optional LM refinement.

    Parameters
    ----------
    pts : list of [x,y,z]
    threshold : float
        Inlier distance threshold (same units as pts).
    n_iters : int
        RANSAC iterations.
    seed : int
        Random seed.
    refine : bool
        If True (default), run LM refinement on the inlier set.

    Returns
    -------
    dict  — ok, primitive, apex, axis, half_angle, inlier_ratio, residual.
    """
    if len(pts) < 6:
        return {"ok": False, "reason": f"need ≥6 points for cone RANSAC; got {len(pts)}"}

    rng = random.Random(seed)
    n = len(pts)
    best: dict[str, Any] | None = None
    best_inlier_count = 0
    # Use at least 12 points per sample for a better fit (more constraints for apex)
    sample_size = min(max(12, n // 5), n)

    for _ in range(n_iters):
        sample = [pts[i] for i in rng.sample(range(n), sample_size)]
        res = fit_cone_direct(sample)
        if not res.get("ok"):
            continue
        inliers = [p for p in pts if _dist_to_cone(p, res) <= threshold]
        if len(inliers) > best_inlier_count:
            best_inlier_count = len(inliers)
            best = res
            best["_inliers"] = inliers

    if best is None:
        return {"ok": False, "reason": "RANSAC cone: no valid consensus set found"}

    inliers = best.pop("_inliers")

    # Refit on inliers
    refit = fit_cone_direct(inliers)
    if not refit.get("ok"):
        refit = best

    refit["inlier_ratio"] = len(inliers) / n
    dists = [_dist_to_cone(p, refit) for p in inliers]
    refit["residual"] = sum(dists) / max(len(dists), 1)

    if refine:
        refined = refine_cone_lm(inliers, refit)
        if refined.get("ok"):
            refined["inlier_ratio"] = len(inliers) / n
            return refined

    return refit
