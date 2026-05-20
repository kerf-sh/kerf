"""
kerf_cad_core.reverse_engineering.segmentation — Sequential RANSAC segmentation.

Extends the existing ``kerf_cad_core.scan.fit`` primitives with:
  - Cone fitting (RANSAC + closed-form)
  - Sequential RANSAC driver that removes inliers after each fit

Sequential RANSAC algorithm
----------------------------
Given a point cloud ``pts`` and a priority-ordered list of primitives to try:

1. Attempt to fit every primitive type against the current remaining cloud.
2. Pick the fit with the highest inlier count (above ``min_inliers`` threshold).
3. Remove those inliers from the remaining cloud.
4. Append a segment record to the output list.
5. Repeat from step 1 until the cloud is exhausted or no fit clears the
   minimum-inlier threshold.

Primitives supported (v1)
--------------------------
plane, cylinder, sphere, cone

Cone (v1 limits)
----------------
The cone fitter estimates the apex by intersecting axis-aligned normals.
It degrades when the apex is far outside the sampled surface arc (very
shallow cones, scan truncations).  A robust half-angle estimator is
planned for v2.

Author: imranparuk
"""
from __future__ import annotations

import math
import random
from typing import Any

# Re-export helpers from the existing scan.fit module
from kerf_cad_core.scan.fit import (
    _centroid,
    _covariance3,
    _jacobi3,
    _cross,
    _dot,
    _sub,
    _add,
    _scale,
    _norm,
    _normalise,
    _dist_to_plane,
    _dist_to_sphere,
    _dist_to_cylinder,
    ransac_fit_plane,
    ransac_fit_sphere,
    ransac_fit_cylinder,
    _RANSAC_ITERS,
    _DEFAULT_SEED,
)

# ---------------------------------------------------------------------------
# Cone fitting (closed-form + RANSAC)
# ---------------------------------------------------------------------------

def _dist_to_cone(p: list[float], apex: list[float], axis: list[float], half_angle: float) -> float:
    """Signed distance from point p to the cone surface.

    The cone is defined by its apex, unit axis, and half-angle (radians).
    Returns the absolute distance to the nearest point on the cone surface.
    """
    d = _sub(p, apex)
    along = _dot(d, axis)
    perp_sq = _dot(d, d) - along * along
    perp = math.sqrt(max(0.0, perp_sq))
    # Distance along the cone surface measured perpendicular to the axis line
    # Surface: perp = along * tan(half_angle)  (for along >= 0)
    # Distance to cone = |perp - along * tan(half_angle)| * cos(half_angle)
    tan_ha = math.tan(half_angle)
    cos_ha = math.cos(half_angle)
    return abs(perp - along * tan_ha) * cos_ha


def _fit_cone_given_axis(
    pts: list[list[float]],
    axis: list[float],
) -> dict[str, Any] | None:
    """Fit cone parameters (apex, half-angle) given a fixed axis direction.

    Projects each point onto the axis to get (h, r) pairs, then fits
    r = a*h + b via least squares.  Returns None if degenerate.
    """
    c = _centroid(pts)
    ax = _normalise(axis)
    ref = [1.0, 0.0, 0.0]
    if abs(_dot(ax, ref)) > 0.9:
        ref = [0.0, 1.0, 0.0]
    u = _normalise(_cross(ax, ref))
    v = _cross(ax, u)

    hs = []
    rs = []
    for p in pts:
        dp = _sub(p, c)
        h = _dot(dp, ax)
        pu = _dot(dp, u)
        pv = _dot(dp, v)
        r = math.sqrt(pu*pu + pv*pv)
        hs.append(h)
        rs.append(r)

    n = len(hs)
    sh = sum(hs)
    sr = sum(rs)
    shh = sum(hi*hi for hi in hs)
    shr = sum(hs[i]*rs[i] for i in range(n))
    denom = n * shh - sh * sh
    if abs(denom) < 1e-14:
        return None
    a = (n * shr - sh * sr) / denom
    b = (sr - a * sh) / n

    # If slope negative, flip axis
    if a < 0.0:
        ax = [-ax[0], -ax[1], -ax[2]]
        hs = [-h for h in hs]
        a = -a
        b = (sum(rs) - a * sum(hs)) / n

    if a < 1e-8:
        return None  # degenerate (cylinder-like or flat)

    half_angle = math.atan(a)
    if half_angle <= 0 or half_angle >= math.pi / 2:
        return None

    h_apex = -b / a
    apex = _add(c, _scale(ax, h_apex))

    h_min = min(hs)
    h_max = max(hs)
    height = h_max - h_min

    residuals = [_dist_to_cone(p, apex, ax, half_angle) for p in pts]
    mean_res = sum(residuals) / len(residuals)

    return {
        "ok": True,
        "primitive": "cone",
        "apex": apex,
        "axis": ax,
        "half_angle": half_angle,
        "height": height,
        "inlier_ratio": 1.0,
        "residual": mean_res,
        "_mean_residual": mean_res,
    }


def fit_cone_direct(pts: list[list[float]]) -> dict[str, Any]:
    """Fit a cone to a point cloud by trying multiple axis candidates.

    Strategy
    --------
    1. Compute PCA eigenvectors for the cloud.
    2. Try all three eigenvectors (and their negatives) as candidate axis
       directions, plus the direction from the cloud centroid to each of the
       first ~10 sample points.
    3. For each candidate axis, fit (h, r) data via least squares:
           r = a * h + b
       where h is the axial coordinate and r is the radial distance.
       The slope gives tan(half_angle); the intercept locates the apex.
    4. Return the best fit (lowest mean residual).

    Rationale: the cone axis is NOT always the largest-variance PCA direction
    (the radial spread can dominate axial spread), so all PCA axes must be
    tried.

    Returns a dict with:
        ok, primitive, apex, axis, half_angle (rad), height, inlier_ratio, residual
    """
    if len(pts) < 6:
        return {"ok": False, "reason": f"need ≥6 points for cone fit; got {len(pts)}"}

    c = _centroid(pts)
    cov = _covariance3(pts, c)
    vals, vecs = _jacobi3(cov)

    if abs(vals[2]) < 1e-14:
        return {"ok": False, "reason": "degenerate point cloud for cone fit"}

    # Candidate axes: all three PCA eigenvectors and their negatives
    candidates: list[list[float]] = []
    for vec in vecs:
        if _norm(vec) > 1e-10:
            candidates.append(list(vec))
            candidates.append([-vec[0], -vec[1], -vec[2]])

    # Also try centroid-to-point directions (up to first 10 points)
    for p in pts[:min(len(pts), 10)]:
        d = _sub(p, c)
        if _norm(d) > 1e-10:
            candidates.append(_normalise(d))

    best_fit: dict[str, Any] | None = None
    best_res = float("inf")

    for axis_cand in candidates:
        fit = _fit_cone_given_axis(pts, axis_cand)
        if fit is None:
            continue
        r = fit["_mean_residual"]
        if r < best_res:
            best_res = r
            best_fit = fit

    if best_fit is None:
        return {"ok": False, "reason": "cone fit: no valid axis candidate found"}

    # Clean up internal key
    best_fit.pop("_mean_residual", None)
    return best_fit


def _cone_dist_fn(p: list[float], res: dict[str, Any]) -> float:
    return _dist_to_cone(p, res["apex"], res["axis"], res["half_angle"])


def ransac_fit_cone(
    pts: list[list[float]],
    threshold: float = 0.01,
    n_iters: int = _RANSAC_ITERS,
    seed: int = _DEFAULT_SEED,
) -> dict[str, Any]:
    """RANSAC cone fit."""
    if len(pts) < 6:
        return {"ok": False, "reason": f"need ≥6 points for cone fit; got {len(pts)}"}
    rng = random.Random(seed)

    n = len(pts)
    best: dict[str, Any] | None = None
    best_inlier_count = 0

    for _ in range(n_iters):
        sample_idx = rng.sample(range(n), 6)
        sample = [pts[i] for i in sample_idx]
        res = fit_cone_direct(sample)
        if not res.get("ok"):
            continue
        inliers = [p for p in pts if _cone_dist_fn(p, res) <= threshold]
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
    dists = [_cone_dist_fn(p, refit) for p in inliers]
    refit["residual"] = sum(dists) / max(len(dists), 1)
    return refit


# ---------------------------------------------------------------------------
# Sequential RANSAC driver
# ---------------------------------------------------------------------------

def _refit_on_inliers(
    inliers: list[list[float]],
    kind: str,
) -> dict[str, Any] | None:
    """Refit a primitive on its full inlier set using the direct (non-RANSAC) fitter.

    Returns the refit result or None if the refit fails.
    """
    from kerf_cad_core.scan.fit import (
        fit_plane_direct,
        fit_sphere_direct,
        fit_cylinder_direct,
    )
    if kind == "plane":
        r = fit_plane_direct(inliers)
    elif kind == "sphere":
        r = fit_sphere_direct(inliers)
    elif kind == "cylinder":
        r = fit_cylinder_direct(inliers)
    elif kind == "cone":
        r = fit_cone_direct(inliers)
    else:
        return None
    return r if r.get("ok") else None


def _try_fit_primitive(
    pts: list[list[float]],
    kind: str,
    threshold: float,
    seed: int,
) -> dict[str, Any]:
    """Attempt to fit one primitive type."""
    if kind == "plane":
        return ransac_fit_plane(pts, threshold=threshold, seed=seed)
    if kind == "sphere":
        return ransac_fit_sphere(pts, threshold=threshold, seed=seed)
    if kind == "cylinder":
        return ransac_fit_cylinder(pts, threshold=threshold, seed=seed)
    if kind == "cone":
        return ransac_fit_cone(pts, threshold=threshold, seed=seed)
    return {"ok": False, "reason": f"unknown primitive type: {kind}"}


def _dist_fn_for(kind: str, res: dict[str, Any]):
    """Return a callable dist(p) → float for the fitted primitive."""
    if kind == "plane":
        return lambda p: _dist_to_plane(p, res["normal"], res["d"])
    if kind == "sphere":
        return lambda p: _dist_to_sphere(p, res["centre"], res["radius"])
    if kind == "cylinder":
        return lambda p: _dist_to_cylinder(p, res["axis"], res["axis_point"], res["radius"])
    if kind == "cone":
        return lambda p: _dist_to_cone(p, res["apex"], res["axis"], res["half_angle"])
    raise ValueError(f"unknown primitive kind: {kind}")


def sequential_ransac(
    pts: list[list[float]],
    primitives: list[str] | None = None,
    threshold: float = 0.01,
    min_inliers: int = 6,
    min_inlier_fraction: float = 0.05,
    seed: int = _DEFAULT_SEED,
) -> dict[str, Any]:
    """Sequential RANSAC: iteratively find and remove dominant primitives.

    Parameters
    ----------
    pts:
        Input point cloud as [[x, y, z], ...].
    primitives:
        Ordered list of primitive types to try.
        Default: ``["plane", "cylinder", "sphere", "cone"]``.
    threshold:
        RANSAC inlier distance threshold (same units as pts).
    min_inliers:
        Absolute minimum inlier count for a segment to be accepted.
    min_inlier_fraction:
        Minimum fraction of the *remaining* cloud that a fit must claim.
    seed:
        Random seed for reproducibility.

    Returns
    -------
    dict with keys:
        ok             bool
        segments       list of segment dicts (see below)
        unassigned     list of remaining [x,y,z] points
        total_count    int
        segment_count  int

    Each segment dict has:
        primitive      str
        inlier_count   int
        inlier_fraction float
        residual       float
        ... fit-specific parameters (normal/d, centre/radius, axis/axis_point/radius, apex/axis/half_angle) ...
    """
    if primitives is None:
        primitives = ["plane", "cylinder", "sphere", "cone"]

    if len(pts) < 3:
        return {
            "ok": False,
            "reason": f"need ≥3 points; got {len(pts)}",
        }

    remaining = [list(p) for p in pts]
    total = len(pts)
    segments: list[dict[str, Any]] = []

    while len(remaining) >= max(min_inliers, 3):
        best_fit: dict[str, Any] | None = None
        best_inliers: list[list[float]] = []
        best_kind = ""

        for kind in primitives:
            res = _try_fit_primitive(remaining, kind, threshold, seed)
            if not res.get("ok"):
                continue
            dist_fn = _dist_fn_for(kind, res)
            inliers = [p for p in remaining if dist_fn(p) <= threshold]
            if len(inliers) > len(best_inliers):
                best_fit = res
                best_kind = kind
                best_inliers = inliers

        # Check stop conditions
        if best_fit is None:
            break
        if len(best_inliers) < min_inliers:
            break
        if len(best_inliers) < min_inlier_fraction * len(remaining):
            break

        # ── Refine: iterative refit to improve axis/parameter estimates ──
        # The RANSAC result may have a slightly biased fit (e.g. tilted cylinder
        # axis) when the minimal sample set was not representative.  Iterate:
        # refit on the current inlier set, re-expand inliers, repeat until
        # convergence (no new inliers added).
        for _refit_iter in range(3):
            refit = _refit_on_inliers(best_inliers, best_kind)
            if refit is None:
                break
            dist_fn_refit = _dist_fn_for(best_kind, refit)
            refined_inliers = [p for p in remaining if dist_fn_refit(p) <= threshold]
            if len(refined_inliers) > len(best_inliers):
                best_fit = refit
                best_inliers = refined_inliers
            else:
                # No improvement — also try direct fit on all remaining
                refit_all = _refit_on_inliers(remaining, best_kind)
                if refit_all is not None:
                    dist_fn_all = _dist_fn_for(best_kind, refit_all)
                    inliers_all = [p for p in remaining if dist_fn_all(p) <= threshold]
                    if len(inliers_all) > len(best_inliers):
                        best_fit = refit_all
                        best_inliers = inliers_all
                break

        # Build segment record
        seg: dict[str, Any] = {
            "primitive": best_kind,
            "inlier_count": len(best_inliers),
            "inlier_fraction": len(best_inliers) / len(remaining),
            "residual": best_fit["residual"],
        }
        # Copy primitive-specific params
        for key in ("normal", "d", "centre", "radius", "axis", "axis_point",
                    "apex", "half_angle", "height"):
            if key in best_fit:
                seg[key] = best_fit[key]

        # Compute derived geometry from inliers (cylinder height, plane extent)
        if best_kind == "cylinder" and "axis" in best_fit and "axis_point" in best_fit:
            ax = best_fit["axis"]
            axpt = best_fit["axis_point"]
            hs_cyl = [_dot(_sub(p, axpt), ax) for p in best_inliers]
            seg["height"] = max(hs_cyl) - min(hs_cyl)
        elif best_kind == "plane" and "normal" in best_fit and "centre" in best_fit:
            # Compute bbox extent of inlier points projected onto the plane
            norm = best_fit["normal"]
            ctr = best_fit["centre"]
            ref_p = [1.0, 0.0, 0.0]
            if abs(_dot(norm, ref_p)) > 0.9:
                ref_p = [0.0, 1.0, 0.0]
            pu = _normalise(_cross(norm, ref_p))
            pv = _cross(norm, pu)
            us = [_dot(_sub(p, ctr), pu) for p in best_inliers]
            vs = [_dot(_sub(p, ctr), pv) for p in best_inliers]
            seg["extent"] = max(
                (max(us) - min(us)) / 2.0,
                (max(vs) - min(vs)) / 2.0,
                0.01,
            )

        segments.append(seg)

        # Remove inliers by object identity
        inlier_ids = {id(p) for p in best_inliers}
        remaining = [p for p in remaining if id(p) not in inlier_ids]

    return {
        "ok": True,
        "segments": segments,
        "unassigned": remaining,
        "total_count": total,
        "segment_count": len(segments),
    }
