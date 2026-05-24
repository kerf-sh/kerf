"""
kerf_cad_core.reverse_engineering.fit_torus — Torus primitive fitting.

A torus is parameterised by:
    centre     : [x, y, z]   — centre of the torus ring
    axis       : [ax, ay, az] — unit normal to the torus plane
    R          : float        — major radius (centre-of-torus to centre-of-tube)
    r          : float        — minor radius (tube radius)

Algebraic residual for point p:
    Let d = distance from p to the ring circle (projection onto torus plane,
    offset by R).

    dist_from_centre = ||p - centre||
    proj_along_axis  = dot(p - centre, axis)
    dist_in_plane    = sqrt(dist_from_centre² - proj_along_axis²)
    dist_to_ring     = sqrt((dist_in_plane - R)² + proj_along_axis²)
    residual         = dist_to_ring - r

Fitting strategy
----------------
fit_torus_direct:
    Given a sample of ≥7 points, use a two-stage approach:
    1. Estimate the torus axis by fitting a plane (PCA normal) to the projected
       circle centres (i.e. minimise spread perpendicular to the mean plane).
    2. With the axis fixed, optimise R and centre as a 1-D circle fit on the
       projected (in-plane) distances.

ransac_fit_torus:
    Standard RANSAC loop around fit_torus_direct with inlier refit.

Design notes
------------
- Pure Python + math.  No external deps.
- Minimum sample is 7 points (enough to constrain centre, axis, R, r).
- The axis is estimated robustly via the covariance of the point cloud.
- Linear algebra helpers (_dot, _sub, _add, _scale, _norm, _normalise,
  _cross, _centroid, _covariance3, _jacobi3) are imported from scan.fit
  to avoid duplication.

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
    _add,
    _scale,
    _norm,
    _normalise,
    _cross,
    _centroid,
    _covariance3,
    _jacobi3,
)


# ---------------------------------------------------------------------------
# 2-D algebraic circle fit (for in-plane projection)
# ---------------------------------------------------------------------------

def _fit_circle_2d(pts2: list[tuple[float, float]]) -> dict[str, Any]:
    """Algebraic circle fit in 2-D.  pts2 = [(x,y), ...]."""
    if len(pts2) < 3:
        return {"ok": False, "reason": "circle2d: need ≥3 pts"}
    # System: 2cx·px + 2cy·py + e = px²+py²
    AtA = [[0.0]*3 for _ in range(3)]
    Atb = [0.0]*3
    for px, py in pts2:
        row = [2*px, 2*py, 1.0]
        rhs = px*px + py*py
        for r in range(3):
            Atb[r] += row[r]*rhs
            for c in range(3):
                AtA[r][c] += row[r]*row[c]
    # Gauss elim 3×3
    n = 3
    M = [AtA[i][:]+[Atb[i]] for i in range(n)]
    for col in range(n):
        mr = max(range(col,n), key=lambda r: abs(M[r][col]))
        M[col], M[mr] = M[mr], M[col]
        if abs(M[col][col]) < 1e-14:
            return {"ok": False, "reason": "circle2d: singular"}
        piv = M[col][col]
        for row in range(col+1,n):
            f = M[row][col]/piv
            for k in range(col,n+1):
                M[row][k] -= f*M[col][k]
    x = [0.0]*n
    for i in range(n-1,-1,-1):
        x[i] = M[i][n]
        for j in range(i+1,n):
            x[i] -= M[i][j]*x[j]
        if abs(M[i][i]) < 1e-14:
            return {"ok": False, "reason": "circle2d: singular back-sub"}
        x[i] /= M[i][i]
    cx2, cy2, e = x
    r2 = e + cx2*cx2 + cy2*cy2
    if r2 < 0:
        return {"ok": False, "reason": "circle2d: negative r²"}
    return {"ok": True, "cx": cx2, "cy": cy2, "r": math.sqrt(r2)}


# ---------------------------------------------------------------------------
# Torus distance
# ---------------------------------------------------------------------------

def _dist_to_torus(
    p: list[float],
    centre: list[float],
    axis: list[float],
    R: float,
    r: float,
) -> float:
    """Euclidean distance from point p to the torus surface."""
    v = _sub(p, centre)
    along = _dot(v, axis)
    perp_vec = _sub(v, _scale(axis, along))
    d_plane = _norm(perp_vec)  # distance from axis in the torus plane
    # Distance from p to the ring circle
    dist_to_ring = math.sqrt((d_plane - R)**2 + along**2)
    return abs(dist_to_ring - r)


def _dist_fn(p: list[float], res: dict[str, Any]) -> float:
    return _dist_to_torus(p, res["centre"], res["axis"], res["R"], res["r"])


# ---------------------------------------------------------------------------
# Closed-form torus fit
# ---------------------------------------------------------------------------

def fit_torus_direct(pts: list[list[float]]) -> dict[str, Any]:
    """Fit a torus to ≥7 points.

    Strategy
    --------
    1. Estimate torus axis as the normal to the best-fit plane (PCA smallest
       eigenvalue direction).
    2. Build an orthonormal basis {u, v} in the torus plane.
    3. Project each point onto the torus plane → 2-D coordinate (u_i, v_i).
    4. Fit a 2-D circle to these projections → gives in-plane centre (cx, cy)
       and major radius R.
    5. Reconstruct 3-D centre = 3-D centroid + cx*u + cy*v (approximate).
    6. Compute minor radius r = mean of ||p - nearest-ring-point|| over all pts.

    Parameters
    ----------
    pts : list of [x, y, z]
        Minimum 7 points.

    Returns
    -------
    dict with ok, primitive, centre, axis, R, r, inlier_ratio, residual.
    """
    if len(pts) < 7:
        return {"ok": False, "reason": f"need ≥7 points for torus fit; got {len(pts)}"}

    c = _centroid(pts)
    cov = _covariance3(pts, c)
    vals, vecs = _jacobi3(cov)

    if abs(vals[2]) < 1e-14:
        return {"ok": False, "reason": "degenerate point cloud for torus fit"}

    # Torus axis = normal to best-fit plane = smallest eigenvector
    axis = _normalise(vecs[0])

    # Build orthonormal basis in torus plane
    ref = [1.0, 0.0, 0.0] if abs(axis[2]) < 0.9 else [0.0, 1.0, 0.0]
    u = _normalise(_cross(axis, ref))
    v = _cross(axis, u)  # already unit since axis ⊥ u

    # Project points onto torus plane (relative to centroid)
    pts2: list[tuple[float, float]] = []
    for p in pts:
        dp = _sub(p, c)
        pts2.append((_dot(dp, u), _dot(dp, v)))

    circ = _fit_circle_2d(pts2)
    if not circ["ok"]:
        return {"ok": False, "reason": f"torus: 2-D circle fit failed: {circ['reason']}"}

    # 3-D centre from algebraic circle fit (good approximate in-plane centre)
    cx_u = circ["cx"]
    cy_v = circ["cy"]
    centre_3d = _add(c, _add(_scale(u, cx_u), _scale(v, cy_v)))

    # Unbiased major radius: mean of the in-plane distances from the 3-D centre.
    # For a torus, each point has in-plane distance R + r*cos(theta), and
    # E[R + r*cos(theta)] = R for uniformly distributed theta.
    # This is more accurate than the algebraic circle fit R for wide tubes.
    d_planes = []
    for p in pts:
        vv = _sub(p, centre_3d)
        along = _dot(vv, axis)
        perp = _sub(vv, _scale(axis, along))
        d_planes.append(_norm(perp))

    R = sum(d_planes) / len(d_planes)
    if R < 1e-10:
        return {"ok": False, "reason": "torus: degenerate major radius"}

    # Minor radius: mean distance from each point to the nearest ring circle
    tube_dists = []
    for i, p in enumerate(pts):
        vv = _sub(p, centre_3d)
        along = _dot(vv, axis)
        dist_to_ring = math.sqrt((d_planes[i] - R)**2 + along**2)
        tube_dists.append(dist_to_ring)

    r = sum(tube_dists) / len(tube_dists)
    if r < 1e-10:
        return {"ok": False, "reason": "torus: degenerate minor radius"}

    residuals = [abs(d - r) for d in tube_dists]
    mean_res = sum(residuals) / len(residuals)

    return {
        "ok": True,
        "primitive": "torus",
        "centre": centre_3d,
        "axis": axis,
        "R": R,
        "r": r,
        "inlier_ratio": 1.0,
        "residual": mean_res,
    }


# ---------------------------------------------------------------------------
# RANSAC wrapper
# ---------------------------------------------------------------------------

_DEFAULT_SEED_INT = 42
_RANSAC_ITERS = 200


def ransac_fit_torus(
    pts: list[list[float]],
    threshold: float = 0.01,
    n_iters: int = _RANSAC_ITERS,
    seed: int = _DEFAULT_SEED_INT,
) -> dict[str, Any]:
    """RANSAC torus fit.

    Uses larger sub-samples (min(30, n//3)) per iteration since torus fitting
    requires good coverage of the surface to get accurate R and r estimates.
    Falls back to fitting on the full cloud if RANSAC doesn't find a good model,
    then does a final refit on all inliers.

    Parameters
    ----------
    pts : list of [x,y,z]
    threshold : float
        Inlier distance threshold.
    n_iters : int
        RANSAC iterations.
    seed : int
        Random seed.

    Returns
    -------
    dict — ok, primitive, centre, axis, R, r, inlier_ratio, residual.
    """
    if len(pts) < 7:
        return {"ok": False, "reason": f"need ≥7 points for torus RANSAC; got {len(pts)}"}

    rng = random.Random(seed)
    n = len(pts)
    # Use a larger sample size for torus fitting — small samples give biased estimates.
    # Use at least 30% of the cloud or 30 points, whichever is larger, up to n.
    sample_size = max(30, min(n // 3, n))
    sample_size = min(sample_size, n)

    best: dict[str, Any] | None = None
    best_inlier_count = 0

    for _ in range(n_iters):
        if sample_size >= n:
            sample = pts
        else:
            sample = [pts[i] for i in rng.sample(range(n), sample_size)]
        res = fit_torus_direct(sample)
        if not res.get("ok"):
            continue
        inliers = [p for p in pts if _dist_fn(p, res) <= threshold]
        if len(inliers) > best_inlier_count:
            best_inlier_count = len(inliers)
            best = res
            best["_inliers"] = inliers

    if best is None:
        # Fallback: fit on the entire cloud
        best = fit_torus_direct(pts)
        if not best.get("ok"):
            return {"ok": False, "reason": "RANSAC torus: no valid model found"}
        inliers = [p for p in pts if _dist_fn(p, best) <= threshold]
    else:
        inliers = best.pop("_inliers")

    # Refit on inliers
    if len(inliers) >= 7:
        refit = fit_torus_direct(inliers)
        if not refit.get("ok"):
            refit = best
    else:
        refit = best

    refit["inlier_ratio"] = len(inliers) / n
    dists = [_dist_fn(p, refit) for p in inliers]
    refit["residual"] = sum(dists) / max(len(dists), 1)

    return refit
