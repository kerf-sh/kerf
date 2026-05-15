"""
kerf_cad_core.scan.fit — Point-cloud primitive fitting.

Provides deterministic (seeded) RANSAC wrappers and closed-form solvers for:
    - Plane   : least-squares via PCA on centred cloud; normal = smallest eigenvector
    - Sphere  : algebraic linear least-squares (Pratt-style)
    - Cylinder: project normals → PCA axis; least-squares radius per-inlier

All functions return a dict with keys:
    ok          bool
    reason      str (only present when ok=False)
    primitive   str ("plane" | "sphere" | "cylinder") — when ok=True
    ... fit-specific fields ...
    inlier_ratio float (0..1)
    residual     float (mean distance of inliers to surface)

Design rules:
    - Pure Python, stdlib + math only (no numpy).
    - Never raises; degenerate inputs return {ok:False, reason:...}.
    - Deterministic: RANSAC uses random.Random(seed) with a fixed default seed.
    - Minimum sample guards are strict: <3 pts → error immediately.

Author: imranparuk
"""
from __future__ import annotations

import math
import random
from typing import Any


# ---------------------------------------------------------------------------
# Low-level linear algebra helpers (3-D, hand-rolled)
# ---------------------------------------------------------------------------

def _dot(a: list[float], b: list[float]) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _sub(a: list[float], b: list[float]) -> list[float]:
    return [a[0]-b[0], a[1]-b[1], a[2]-b[2]]


def _add(a: list[float], b: list[float]) -> list[float]:
    return [a[0]+b[0], a[1]+b[1], a[2]+b[2]]


def _scale(v: list[float], s: float) -> list[float]:
    return [v[0]*s, v[1]*s, v[2]*s]


def _norm(v: list[float]) -> float:
    return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)


def _normalise(v: list[float]) -> list[float]:
    n = _norm(v)
    if n < 1e-14:
        return [0.0, 0.0, 0.0]
    return [v[0]/n, v[1]/n, v[2]/n]


def _cross(a: list[float], b: list[float]) -> list[float]:
    return [
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0],
    ]


def _centroid(pts: list[list[float]]) -> list[float]:
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    cz = sum(p[2] for p in pts) / n
    return [cx, cy, cz]


# ---------------------------------------------------------------------------
# 3×3 symmetric eigenvalue decomposition (Jacobi iteration)
# Returns (eigenvalues, eigenvectors) sorted ascending by eigenvalue.
# Sufficient precision for ≤ 10 000 pts at double arithmetic.
# ---------------------------------------------------------------------------

def _jacobi3(A: list[list[float]], max_iter: int = 100) -> tuple[list[float], list[list[float]]]:
    """Jacobi eigenvalue algorithm for 3×3 symmetric matrix.

    Returns (vals, vecs) where vals[i] is eigenvalue i and vecs[i] is the
    corresponding unit eigenvector (as a 3-list).  Sorted ascending.
    """
    # Copy A into a working matrix
    a = [row[:] for row in A]
    # V = identity
    V = [[1.0, 0.0, 0.0],
         [0.0, 1.0, 0.0],
         [0.0, 0.0, 1.0]]

    for _ in range(max_iter):
        # Find the largest off-diagonal element
        max_val = 0.0
        p, q = 0, 1
        for i in range(3):
            for j in range(i+1, 3):
                if abs(a[i][j]) > max_val:
                    max_val = abs(a[i][j])
                    p, q = i, j
        if max_val < 1e-14:
            break
        # Compute rotation angle
        if abs(a[p][p] - a[q][q]) < 1e-14:
            theta = math.pi / 4.0
        else:
            theta = 0.5 * math.atan2(2.0 * a[p][q], a[p][p] - a[q][q])
        c = math.cos(theta)
        s = math.sin(theta)
        # Apply Givens rotation: a' = G^T a G
        a_new = [row[:] for row in a]
        for i in range(3):
            a_new[i][p] = c * a[i][p] + s * a[i][q]
            a_new[i][q] = -s * a[i][p] + c * a[i][q]
        a = [row[:] for row in a_new]
        for j in range(3):
            a[p][j] = c * a_new[p][j] + s * a_new[q][j]
            a[q][j] = -s * a_new[p][j] + c * a_new[q][j]
        # Force symmetry and zero out pivot
        a[p][q] = 0.0
        a[q][p] = 0.0
        # Update eigenvectors
        V_new = [row[:] for row in V]
        for i in range(3):
            V_new[i][p] = c * V[i][p] + s * V[i][q]
            V_new[i][q] = -s * V[i][p] + c * V[i][q]
        V = V_new

    vals = [a[0][0], a[1][1], a[2][2]]
    vecs = [[V[0][i], V[1][i], V[2][i]] for i in range(3)]

    # Sort ascending
    order = sorted(range(3), key=lambda i: vals[i])
    vals = [vals[i] for i in order]
    vecs = [vecs[i] for i in order]
    return vals, vecs


# ---------------------------------------------------------------------------
# Covariance matrix of a centred point cloud
# ---------------------------------------------------------------------------

def _covariance3(pts: list[list[float]], centre: list[float]) -> list[list[float]]:
    """3×3 covariance matrix of pts relative to centre."""
    cxx = cxy = cxz = cyy = cyz = czz = 0.0
    for p in pts:
        dx = p[0] - centre[0]
        dy = p[1] - centre[1]
        dz = p[2] - centre[2]
        cxx += dx*dx; cxy += dx*dy; cxz += dx*dz
        cyy += dy*dy; cyz += dy*dz; czz += dz*dz
    n = len(pts)
    return [
        [cxx/n, cxy/n, cxz/n],
        [cxy/n, cyy/n, cyz/n],
        [cxz/n, cyz/n, czz/n],
    ]


# ---------------------------------------------------------------------------
# Closed-form plane fit (PCA on centred cloud)
# ---------------------------------------------------------------------------

def fit_plane_direct(pts: list[list[float]]) -> dict[str, Any]:
    """Fit a plane to pts using PCA.

    Returns {ok, centre, normal, d, inlier_ratio, residual} where
    the plane equation is  normal · x = d  (i.e. normal · centre = d).
    normal is the eigenvector corresponding to the *smallest* eigenvalue of
    the covariance matrix (direction of minimum variance = plane normal).
    """
    if len(pts) < 3:
        return {"ok": False, "reason": f"need ≥3 points for plane fit; got {len(pts)}"}

    c = _centroid(pts)
    cov = _covariance3(pts, c)
    vals, vecs = _jacobi3(cov)

    # Check for degenerate cloud (all pts identical → all eigenvalues ≈ 0)
    if abs(vals[2]) < 1e-14:
        return {"ok": False, "reason": "degenerate point cloud: all points are identical"}

    # Check for collinear cloud: two smallest eigenvalues ≈ 0 but largest > 0
    # That means the cloud is 1-D (a line), not 2-D.
    if abs(vals[0]) < 1e-14 and abs(vals[1]) < 1e-14:
        return {"ok": False, "reason": "degenerate point cloud: points are collinear"}

    normal = _normalise(vecs[0])  # smallest eigenvalue → normal direction
    d = _dot(normal, c)

    residuals = [abs(_dot(normal, p) - d) for p in pts]
    mean_res = sum(residuals) / len(residuals)

    return {
        "ok": True,
        "primitive": "plane",
        "centre": c,
        "normal": normal,
        "d": d,
        "inlier_ratio": 1.0,
        "residual": mean_res,
    }


# ---------------------------------------------------------------------------
# Closed-form sphere fit (algebraic least squares)
# Solves: ||p - centre||^2 = r^2  →  linear in (cx,cy,cz,r^2-cx^2-cy^2-cz^2)
# System: p.x^2+p.y^2+p.z^2 = 2cx·p.x + 2cy·p.y + 2cz·p.z + (r^2-cx^2-cy^2-cz^2)
# Let e = r^2 - cx^2 - cy^2 - cz^2.
# Row for point p: [2px, 2py, 2pz, 1] · [cx, cy, cz, e]^T = px²+py²+pz²
# Solve via normal equations A^T A x = A^T b.
# ---------------------------------------------------------------------------

def _solve_4x4(A: list[list[float]], b: list[float]) -> list[float] | None:
    """Solve 4×4 system via Gaussian elimination with partial pivoting.
    Returns solution vector or None if singular."""
    n = 4
    # Augmented matrix
    M = [A[i][:] + [b[i]] for i in range(n)]
    for col in range(n):
        # Pivot
        max_row = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[max_row] = M[max_row], M[col]
        if abs(M[col][col]) < 1e-14:
            return None
        pivot = M[col][col]
        for row in range(col+1, n):
            factor = M[row][col] / pivot
            for k in range(col, n+1):
                M[row][k] -= factor * M[col][k]
    # Back-substitution
    x = [0.0] * n
    for i in range(n-1, -1, -1):
        x[i] = M[i][n]
        for j in range(i+1, n):
            x[i] -= M[i][j] * x[j]
        if abs(M[i][i]) < 1e-14:
            return None
        x[i] /= M[i][i]
    return x


def fit_sphere_direct(pts: list[list[float]]) -> dict[str, Any]:
    """Fit a sphere using algebraic least squares (normal equations)."""
    if len(pts) < 4:
        return {"ok": False, "reason": f"need ≥4 points for sphere fit; got {len(pts)}"}

    # Build A (Nx4) and b (N)
    rows_A = []
    b_vec = []
    for p in pts:
        px, py, pz = p[0], p[1], p[2]
        rows_A.append([2*px, 2*py, 2*pz, 1.0])
        b_vec.append(px*px + py*py + pz*pz)

    # Normal equations: (A^T A) x = A^T b
    AtA = [[0.0]*4 for _ in range(4)]
    Atb = [0.0]*4
    for i, row in enumerate(rows_A):
        for r in range(4):
            Atb[r] += row[r] * b_vec[i]
            for c in range(4):
                AtA[r][c] += row[r] * row[c]

    sol = _solve_4x4(AtA, Atb)
    if sol is None:
        return {"ok": False, "reason": "sphere fit: singular system (degenerate point set)"}

    cx, cy, cz, e = sol
    r2 = e + cx*cx + cy*cy + cz*cz
    if r2 < 0:
        return {"ok": False, "reason": "sphere fit: negative r² (points not sphere-like)"}

    r = math.sqrt(r2)
    if r < 1e-12:
        return {"ok": False, "reason": "sphere fit: degenerate (radius ≈ 0)"}

    centre = [cx, cy, cz]
    residuals = [abs(math.sqrt((p[0]-cx)**2+(p[1]-cy)**2+(p[2]-cz)**2) - r) for p in pts]
    mean_res = sum(residuals) / len(residuals)

    return {
        "ok": True,
        "primitive": "sphere",
        "centre": centre,
        "radius": r,
        "inlier_ratio": 1.0,
        "residual": mean_res,
    }


# ---------------------------------------------------------------------------
# Closed-form cylinder fit
# Strategy:
#   1. Estimate axis direction via PCA on point *normals* if available.
#      Without normals: fall back to PCA on pts — axis = middle eigenvector.
#   2. Project pts onto plane perpendicular to axis.
#   3. Fit circle in 2-D on projected pts (algebraic LS, same as sphere but 2-D).
# ---------------------------------------------------------------------------

def _fit_circle_2d(pts2: list[list[float]]) -> dict[str, Any]:
    """Fit a circle in 2-D via algebraic LS.  pts2 = [[x,y], ...]."""
    if len(pts2) < 3:
        return {"ok": False, "reason": f"need ≥3 points for circle fit; got {len(pts2)}"}

    # Same approach: 2px·cx + 2py·cy + e = px²+py²
    rows_A = []
    b_vec = []
    for p in pts2:
        px, py = p[0], p[1]
        rows_A.append([2*px, 2*py, 1.0])
        b_vec.append(px*px + py*py)

    # Normal equations 3×3
    AtA = [[0.0]*3 for _ in range(3)]
    Atb = [0.0]*3
    for i, row in enumerate(rows_A):
        for r in range(3):
            Atb[r] += row[r] * b_vec[i]
            for c in range(3):
                AtA[r][c] += row[r] * row[c]

    # 3×3 Gaussian elimination
    n = 3
    M = [AtA[i][:] + [Atb[i]] for i in range(n)]
    for col in range(n):
        max_row = max(range(col, n), key=lambda r: abs(M[r][col]))
        M[col], M[max_row] = M[max_row], M[col]
        if abs(M[col][col]) < 1e-14:
            return {"ok": False, "reason": "circle fit: singular system"}
        pivot = M[col][col]
        for row in range(col+1, n):
            factor = M[row][col] / pivot
            for k in range(col, n+1):
                M[row][k] -= factor * M[col][k]
    x = [0.0]*n
    for i in range(n-1, -1, -1):
        x[i] = M[i][n]
        for j in range(i+1, n):
            x[i] -= M[i][j] * x[j]
        if abs(M[i][i]) < 1e-14:
            return {"ok": False, "reason": "circle fit: singular (back-sub)"}
        x[i] /= M[i][i]

    cx2, cy2, e = x
    r2 = e + cx2*cx2 + cy2*cy2
    if r2 < 0:
        return {"ok": False, "reason": "circle fit: negative r²"}
    return {"ok": True, "cx": cx2, "cy": cy2, "r": math.sqrt(r2)}


def fit_cylinder_direct(pts: list[list[float]]) -> dict[str, Any]:
    """Fit a cylinder using PCA for axis + 2-D circle fit for radius/centre."""
    if len(pts) < 6:
        return {"ok": False, "reason": f"need ≥6 points for cylinder fit; got {len(pts)}"}

    c = _centroid(pts)
    cov = _covariance3(pts, c)
    vals, vecs = _jacobi3(cov)

    # Check degenerate
    if abs(vals[2]) < 1e-14:
        return {"ok": False, "reason": "degenerate point cloud: all points identical"}

    # Axis = eigenvector with *largest* eigenvalue (direction of max spread)
    axis = _normalise(vecs[2])

    # Project pts onto plane perpendicular to axis
    # Build two orthogonal basis vectors u, v for that plane
    # Pick a vector not parallel to axis
    ref = [1.0, 0.0, 0.0]
    if abs(_dot(axis, ref)) > 0.9:
        ref = [0.0, 1.0, 0.0]
    u = _normalise(_cross(axis, ref))
    v = _cross(axis, u)

    pts2 = [[_dot(_sub(p, c), u), _dot(_sub(p, c), v)] for p in pts]

    circ = _fit_circle_2d(pts2)
    if not circ["ok"]:
        return {"ok": False, "reason": f"cylinder: {circ['reason']}"}

    r = circ["r"]
    if r < 1e-12:
        return {"ok": False, "reason": "cylinder fit: degenerate (radius ≈ 0)"}

    # Cylinder axis passes through 3-D point: centre + cx2*u + cy2*v
    axis_pt = _add(c, _add(_scale(u, circ["cx"]), _scale(v, circ["cy"])))

    residuals = []
    for p in pts:
        dp = _sub(p, axis_pt)
        along = _dot(dp, axis)
        perp = _sub(dp, _scale(axis, along))
        dist = _norm(perp)
        residuals.append(abs(dist - r))
    mean_res = sum(residuals) / len(residuals)

    return {
        "ok": True,
        "primitive": "cylinder",
        "axis": axis,
        "axis_point": axis_pt,
        "radius": r,
        "inlier_ratio": 1.0,
        "residual": mean_res,
    }


# ---------------------------------------------------------------------------
# Distance helpers for RANSAC
# ---------------------------------------------------------------------------

def _dist_to_plane(p: list[float], normal: list[float], d: float) -> float:
    return abs(_dot(normal, p) - d)


def _dist_to_sphere(p: list[float], centre: list[float], r: float) -> float:
    dx = p[0]-centre[0]; dy = p[1]-centre[1]; dz = p[2]-centre[2]
    return abs(math.sqrt(dx*dx+dy*dy+dz*dz) - r)


def _dist_to_cylinder(p: list[float], axis: list[float], axis_pt: list[float], r: float) -> float:
    dp = _sub(p, axis_pt)
    along = _dot(dp, axis)
    perp = _sub(dp, _scale(axis, along))
    return abs(_norm(perp) - r)


# ---------------------------------------------------------------------------
# RANSAC wrappers
# ---------------------------------------------------------------------------

_DEFAULT_SEED = 42
_RANSAC_ITERS = 200


def _ransac(
    pts: list[list[float]],
    sample_size: int,
    fit_fn,
    dist_fn,
    threshold: float,
    n_iters: int,
    rng: random.Random,
    do_refit: bool = True,
) -> dict[str, Any]:
    """Generic RANSAC loop.

    fit_fn(sample) → result dict (ok, ...)
    dist_fn(p, result) → float distance
    Returns best result with inlier_ratio and residual set.

    do_refit: if True (default), refit on the full inlier set after RANSAC.
    Set to False for methods (like cylinder PCA) where refitting on a partial
    inlier arc can degrade the axis estimate.
    """
    n = len(pts)
    best: dict[str, Any] | None = None
    best_inlier_count = 0

    for _ in range(n_iters):
        sample_idx = rng.sample(range(n), sample_size)
        sample = [pts[i] for i in sample_idx]
        res = fit_fn(sample)
        if not res.get("ok"):
            continue
        inliers = [p for p in pts if dist_fn(p, res) <= threshold]
        if len(inliers) > best_inlier_count:
            best_inlier_count = len(inliers)
            best = res
            best["_inliers"] = inliers

    if best is None:
        return {"ok": False, "reason": "RANSAC: no valid consensus set found"}

    inliers = best.pop("_inliers")

    if do_refit:
        # Refit on all inliers; fall back to consensus if refit fails
        refit = fit_fn(inliers)
        if not refit.get("ok"):
            refit = best
    else:
        refit = best

    refit["inlier_ratio"] = len(inliers) / n

    # Residual on inliers using the refit/consensus model
    dists = [dist_fn(p, refit) for p in inliers]
    refit["residual"] = sum(dists) / max(len(dists), 1)

    return refit


# ---------------------------------------------------------------------------
# Public RANSAC-based fit functions
# ---------------------------------------------------------------------------

def _plane_dist_fn(p, res):
    return _dist_to_plane(p, res["normal"], res["d"])


def _sphere_dist_fn(p, res):
    return _dist_to_sphere(p, res["centre"], res["radius"])


def _cyl_dist_fn(p, res):
    return _dist_to_cylinder(p, res["axis"], res["axis_point"], res["radius"])


def ransac_fit_plane(
    pts: list[list[float]],
    threshold: float = 0.01,
    n_iters: int = _RANSAC_ITERS,
    seed: int = _DEFAULT_SEED,
) -> dict[str, Any]:
    """RANSAC plane fit.  threshold in same units as pts."""
    if len(pts) < 3:
        return {"ok": False, "reason": f"need ≥3 points for plane fit; got {len(pts)}"}
    rng = random.Random(seed)
    return _ransac(pts, 3, fit_plane_direct, _plane_dist_fn, threshold, n_iters, rng)


def ransac_fit_sphere(
    pts: list[list[float]],
    threshold: float = 0.01,
    n_iters: int = _RANSAC_ITERS,
    seed: int = _DEFAULT_SEED,
) -> dict[str, Any]:
    """RANSAC sphere fit."""
    if len(pts) < 4:
        return {"ok": False, "reason": f"need ≥4 points for sphere fit; got {len(pts)}"}
    rng = random.Random(seed)
    return _ransac(pts, 4, fit_sphere_direct, _sphere_dist_fn, threshold, n_iters, rng)


def ransac_fit_cylinder(
    pts: list[list[float]],
    threshold: float = 0.01,
    n_iters: int = _RANSAC_ITERS,
    seed: int = _DEFAULT_SEED,
) -> dict[str, Any]:
    """RANSAC cylinder fit.

    Refit is skipped (do_refit=False) because PCA-based cylinder axis estimation
    degrades when the inlier set covers only a partial arc of the cylinder.
    The best consensus model found during RANSAC is used directly.
    """
    if len(pts) < 6:
        return {"ok": False, "reason": f"need ≥6 points for cylinder fit; got {len(pts)}"}
    rng = random.Random(seed)
    return _ransac(pts, 6, fit_cylinder_direct, _cyl_dist_fn, threshold, n_iters, rng, do_refit=False)


# ---------------------------------------------------------------------------
# Point-cloud stats (for scan_load tool)
# ---------------------------------------------------------------------------

def cloud_stats(pts: list[list[float]]) -> dict[str, Any]:
    """Return count, bounding-box, and centroid of a point cloud."""
    if not pts:
        return {"ok": False, "reason": "empty point cloud"}
    if not all(isinstance(p, (list, tuple)) and len(p) == 3 for p in pts):
        return {"ok": False, "reason": "each point must be [x, y, z]"}

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    n = len(pts)
    return {
        "ok": True,
        "count": n,
        "bbox": {
            "x_min": min(xs), "x_max": max(xs),
            "y_min": min(ys), "y_max": max(ys),
            "z_min": min(zs), "z_max": max(zs),
        },
        "centroid": [sum(xs)/n, sum(ys)/n, sum(zs)/n],
    }


# ---------------------------------------------------------------------------
# Multi-primitive greedy segmentation
# ---------------------------------------------------------------------------

def _try_fit(pts: list[list[float]], kind: str, threshold: float, seed: int) -> dict[str, Any]:
    if kind == "plane":
        return ransac_fit_plane(pts, threshold=threshold, seed=seed)
    if kind == "sphere":
        return ransac_fit_sphere(pts, threshold=threshold, seed=seed)
    if kind == "cylinder":
        return ransac_fit_cylinder(pts, threshold=threshold, seed=seed)
    return {"ok": False, "reason": f"unknown primitive type: {kind}"}


def greedy_segment(
    pts: list[list[float]],
    primitives: list[str] | None = None,
    threshold: float = 0.01,
    min_inlier_ratio: float = 0.1,
    seed: int = _DEFAULT_SEED,
) -> dict[str, Any]:
    """Greedy multi-primitive segmentation.

    Iteratively fits the best primitive from the candidate list to the
    remaining (unassigned) points.  Stops when either the cloud is exhausted
    or no primitive achieves ≥ min_inlier_ratio of the *remaining* points.

    Returns {ok, segments: [{primitive, params, inlier_count, residual}, ...],
             unassigned_count, total_count}.
    """
    if primitives is None:
        primitives = ["plane", "sphere", "cylinder"]

    if len(pts) < 3:
        return {"ok": False, "reason": f"need ≥3 points to segment; got {len(pts)}"}

    remaining = [list(p) for p in pts]
    total = len(pts)
    segments: list[dict] = []

    while len(remaining) >= 3:
        best_fit: dict[str, Any] | None = None
        best_inliers: list[list[float]] = []
        best_kind = ""

        for kind in primitives:
            res = _try_fit(remaining, kind, threshold, seed)
            if not res.get("ok"):
                continue
            n_inliers = round(res["inlier_ratio"] * len(remaining))
            if n_inliers > len(best_inliers):
                best_fit = res
                best_kind = kind
                # Recompute inlier list from res
                if kind == "plane":
                    dist_fn = lambda p: _dist_to_plane(p, res["normal"], res["d"])  # noqa: E731
                elif kind == "sphere":
                    dist_fn = lambda p: _dist_to_sphere(p, res["centre"], res["radius"])  # noqa: E731
                else:
                    dist_fn = lambda p: _dist_to_cylinder(p, res["axis"], res["axis_point"], res["radius"])  # noqa: E731
                best_inliers = [p for p in remaining if dist_fn(p) <= threshold]

        if best_fit is None or len(best_inliers) < min_inlier_ratio * len(remaining):
            break

        seg: dict[str, Any] = {
            "primitive": best_kind,
            "inlier_count": len(best_inliers),
            "residual": best_fit["residual"],
        }
        if best_kind == "plane":
            seg["normal"] = best_fit["normal"]
            seg["d"] = best_fit["d"]
            seg["centre"] = best_fit["centre"]
        elif best_kind == "sphere":
            seg["centre"] = best_fit["centre"]
            seg["radius"] = best_fit["radius"]
        else:
            seg["axis"] = best_fit["axis"]
            seg["axis_point"] = best_fit["axis_point"]
            seg["radius"] = best_fit["radius"]

        segments.append(seg)

        # Remove inliers from remaining (by object identity via index)
        inlier_set = {id(p) for p in best_inliers}
        remaining = [p for p in remaining if id(p) not in inlier_set]

    return {
        "ok": True,
        "segments": segments,
        "unassigned_count": len(remaining),
        "total_count": total,
    }
