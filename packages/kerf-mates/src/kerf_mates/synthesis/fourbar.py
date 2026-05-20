"""
kerf_mates.synthesis.fourbar — 4-bar linkage synthesis (Burmester theory).

Given three coupler-curve points the synthesiser returns the link lengths
(r1, r2, r3, r4) of a planar 4-bar mechanism whose coupler point passes
through all three target positions within 0.5 mm.

Theory
------
Burmester point synthesis (Sandor & Erdman, "Mechanism Design: Analysis and
Synthesis", Vol. 1, 4th ed., Ch. 5) provides an analytical approach: for
three prescribed positions of a coupler point, the locus of fixed-pivot
candidates forms the "Burmester curve".  For the simpler (and reliable) case
of three coupler-curve precision points, the approach used here is:

  1. Fit the coupler point to the three target positions with an optimisation
     over the coupler-point offset (px, py) and the link lengths so the
     coupler curve passes within tolerance of all three points.

  2. A good starting-point strategy selects the crank length as 1/3 of the
     span of the target points, and uses an equal-link geometry (r1=r4,
     r2=r3) — a "parallelogram default" — then optimises with the Nelder-Mead
     simplex method.

  3. The result is verified: all three target points appear within 0.5 mm on
     the computed coupler curve (using the forward kinematics from
     kerf_cad_core.kinematics.linkage or the bundled fast path here).

Public API
----------
synthesise_four_bar(points, *, tol_mm=0.5, max_iters=2000) -> dict
    points : list of three (x, y) tuples  (mm)
    Returns dict with keys:
        ok            bool
        r1, r2, r3, r4  float   link lengths (mm)
        px, py        float   coupler-point offset from coupler pivot A (mm)
        max_error_mm  float   maximum distance from any target to coupler curve
        grashof       str     Grashof classification
        warnings      list[str]
        reason        str     (only when ok=False)

References
----------
Burmester, L. (1888). Lehrbuch der Kinematik, Vol. 1.
Sandor, G.N. & Erdman, A.G. (1984). Advanced Mechanism Design, Vol. 2.
Norton, R.L. (2012). Design of Machinery, 5th ed., Ch. 5.

Author: imranparuk
"""

from __future__ import annotations

import math
import itertools
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _four_bar_position_fast(
    r1: float, r2: float, r3: float, r4: float,
    theta2: float,  # radians
    branch: int = 1,
) -> tuple[float, float] | None:
    """
    Freudenstein solution for theta3, theta4 (radians).
    Returns (theta3, theta4) or None if locked.
    """
    K1 = r1 / r2
    K2 = r1 / r4
    K3 = (r1 * r1 + r4 * r4 + r2 * r2 - r3 * r3) / (2.0 * r2 * r4)

    cos2 = math.cos(theta2)
    sin2 = math.sin(theta2)

    A_f = K3 - K2 * cos2
    B_f = K1 - cos2

    aa = A_f - B_f
    bb = -2.0 * sin2
    cc = A_f + B_f

    if abs(aa) < 1e-14:
        if abs(bb) < 1e-14:
            return None
        t = -cc / bb
    else:
        disc = bb * bb - 4.0 * aa * cc
        if disc < -1e-9:
            return None
        disc = max(disc, 0.0)
        t = (-bb + branch * math.sqrt(disc)) / (2.0 * aa)

    theta4 = 2.0 * math.atan(t)

    ex = r1 + r4 * math.cos(theta4) - r2 * cos2
    ey = r4 * math.sin(theta4) - r2 * sin2
    theta3 = math.atan2(ey, ex)

    return theta3, theta4


def _coupler_point_xy(
    r2: float, theta2: float,
    theta3: float,
    px: float, py: float,
) -> tuple[float, float]:
    """World-frame position of the coupler point."""
    Ax = r2 * math.cos(theta2)
    Ay = r2 * math.sin(theta2)
    cos3 = math.cos(theta3)
    sin3 = math.sin(theta3)
    return (Ax + px * cos3 - py * sin3,
            Ay + px * sin3 + py * cos3)


def _nearest_on_curve(
    r1: float, r2: float, r3: float, r4: float,
    px: float, py: float,
    target_x: float, target_y: float,
    n_samples: int = 360,
    branch: int = 1,
) -> float:
    """
    Minimum distance from (target_x, target_y) to the coupler curve.
    Samples the curve at n_samples crank angles and returns the min distance.
    """
    min_dist = float("inf")
    step = 2.0 * math.pi / n_samples
    theta2 = 0.0
    for _ in range(n_samples):
        res = _four_bar_position_fast(r1, r2, r3, r4, theta2, branch)
        if res is not None:
            theta3, _ = res
            cx, cy = _coupler_point_xy(r2, theta2, theta3, px, py)
            d = math.sqrt((cx - target_x) ** 2 + (cy - target_y) ** 2)
            if d < min_dist:
                min_dist = d
        theta2 += step
    return min_dist


def _grashof_type(r1: float, r2: float, r3: float, r4: float) -> str:
    links = sorted([r1, r2, r3, r4])
    S, P, Q, L = links[0], links[1], links[2], links[3]
    if S + L <= P + Q + 1e-9 * L:
        shortest_idx = [r1, r2, r3, r4].index(S)
        types = {0: "double-crank", 1: "crank-rocker",
                 2: "double-rocker", 3: "rocker-crank"}
        return f"Grashof / {types.get(shortest_idx, 'crank-rocker')}"
    return "non-Grashof"


# ---------------------------------------------------------------------------
# Nelder-Mead simplex (pure Python, no scipy dependency)
# ---------------------------------------------------------------------------

def _nelder_mead(
    func,
    x0: list[float],
    *,
    max_iters: int = 2000,
    tol: float = 1e-9,
    alpha: float = 1.0,
    gamma: float = 2.0,
    rho: float = 0.5,
    sigma: float = 0.5,
) -> tuple[list[float], float]:
    """
    Minimise func(x) starting from x0.
    Returns (best_x, best_f).
    """
    n = len(x0)
    # Build initial simplex
    simplex = [list(x0)]
    for i in range(n):
        x = list(x0)
        x[i] += max(abs(x[i]) * 0.1, 0.1)
        simplex.append(x)

    def fsafe(x: list[float]) -> float:
        try:
            v = func(x)
            return v if math.isfinite(v) else 1e30
        except Exception:
            return 1e30

    scores = [fsafe(x) for x in simplex]

    for _iter in range(max_iters):
        # Sort
        order = sorted(range(n + 1), key=lambda i: scores[i])
        simplex = [simplex[i] for i in order]
        scores = [scores[i] for i in order]

        best_f = scores[0]
        worst_f = scores[-1]

        # Convergence
        if worst_f - best_f < tol and _iter > 10:
            break

        # Centroid (excluding worst)
        centroid = [sum(simplex[j][k] for j in range(n)) / n for k in range(n)]

        # Reflection
        xr = [centroid[k] + alpha * (centroid[k] - simplex[-1][k]) for k in range(n)]
        fr = fsafe(xr)

        if scores[0] <= fr < scores[-2]:
            simplex[-1] = xr
            scores[-1] = fr
            continue

        if fr < scores[0]:
            # Expansion
            xe = [centroid[k] + gamma * (xr[k] - centroid[k]) for k in range(n)]
            fe = fsafe(xe)
            if fe < fr:
                simplex[-1] = xe
                scores[-1] = fe
            else:
                simplex[-1] = xr
                scores[-1] = fr
            continue

        # Contraction
        xc = [centroid[k] + rho * (simplex[-1][k] - centroid[k]) for k in range(n)]
        fc = fsafe(xc)
        if fc < scores[-1]:
            simplex[-1] = xc
            scores[-1] = fc
            continue

        # Shrink
        best = simplex[0]
        for j in range(1, n + 1):
            simplex[j] = [best[k] + sigma * (simplex[j][k] - best[k]) for k in range(n)]
            scores[j] = fsafe(simplex[j])

    return simplex[0], scores[0]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def synthesise_four_bar(
    points: list[tuple[float, float]],
    *,
    tol_mm: float = 0.5,
    max_iters: int = 2000,
) -> dict[str, Any]:
    """
    Synthesise a 4-bar linkage whose coupler curve passes through three
    specified precision points (Burmester theory).

    Parameters
    ----------
    points    : list of exactly three (x, y) tuples, in mm.
    tol_mm    : acceptable maximum distance from any target to the coupler
                curve (default 0.5 mm).
    max_iters : Nelder-Mead iteration budget (default 2000).

    Returns
    -------
    dict with keys:
        ok            bool
        r1            float   ground / frame link (mm)
        r2            float   crank (mm)
        r3            float   coupler (mm)
        r4            float   output / rocker (mm)
        px            float   coupler-point x-offset from pivot A (mm)
        py            float   coupler-point y-offset from pivot A (mm)
        max_error_mm  float   maximum distance from any target to curve
        grashof       str     Grashof type string
        warnings      list[str]
        reason        str     (only when ok=False)

    Notes
    -----
    The optimisation objective minimises the sum of squared minimum distances
    from each target point to the coupler curve, sampled at 360 crank angles.
    A penalty on negative or degenerate link lengths keeps the search in
    physically meaningful territory.

    The ground pivot O2 is fixed at the origin; the output pivot O4 is at
    (r1, 0).  Coupler-point offsets (px, py) are expressed in the coupler
    body frame (x along the coupler, y perpendicular).
    """
    warnings_list: list[str] = []

    # -- Validate input -------------------------------------------------------
    if not isinstance(points, (list, tuple)) or len(points) != 3:
        return _err("points must be a list of exactly three (x, y) tuples")

    pts: list[tuple[float, float]] = []
    for i, p in enumerate(points):
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            return _err(f"points[{i}] must be a (x, y) tuple of numbers")
        if not (math.isfinite(x) and math.isfinite(y)):
            return _err(f"points[{i}] contains non-finite coordinate")
        pts.append((x, y))

    if not math.isfinite(tol_mm) or tol_mm <= 0:
        return _err(f"tol_mm must be > 0, got {tol_mm!r}")

    # -- Characteristic scale -------------------------------------------------
    all_x = [p[0] for p in pts]
    all_y = [p[1] for p in pts]
    span = max(
        max(all_x) - min(all_x),
        max(all_y) - min(all_y),
        1.0,
    )
    # Centroid of the three points
    cx0 = sum(all_x) / 3.0
    cy0 = sum(all_y) / 3.0

    # -- Objective function ---------------------------------------------------
    def objective(x: list[float]) -> float:
        r1, r2, r3, r4, px, py = x

        # Penalty for degenerate / non-physical configurations
        penalty = 0.0
        min_len = 1e-3 * span
        for val in (r1, r2, r3, r4):
            if val < min_len:
                penalty += (min_len - val) ** 2 * 1e6

        # Penalty for excessively long links (keep within 10× span)
        max_len = 10.0 * span
        for val in (r1, r2, r3, r4):
            if val > max_len:
                penalty += (val - max_len) ** 2 * 1e3

        if penalty > 1e10:
            return penalty

        # Try both branches; take the best
        total = 0.0
        for pt in pts:
            best_d = min(
                _nearest_on_curve(r1, r2, r3, r4, px, py,
                                  pt[0], pt[1], n_samples=180, branch=b)
                for b in (1, -1)
            )
            total += best_d ** 2

        return total + penalty

    # -- Initial guess strategy -----------------------------------------------
    # Use the span and centroid to build a sensible starting link geometry.
    # Start: r2 ~ span/3, equal-length ground/output, coupler ~ span/2.
    r2_0 = span / 3.0
    r1_0 = span / 2.0
    r4_0 = span / 2.0
    r3_0 = span * 0.6

    # Coupler point initially at the centroid of the three target points,
    # expressed relative to the crank-coupler joint A at (r2, 0).
    # (A rough guess; the optimiser adjusts it.)
    px_0 = cx0 - r2_0
    py_0 = cy0

    x0 = [r1_0, r2_0, r3_0, r4_0, px_0, py_0]

    best_x, best_f = _nelder_mead(objective, x0, max_iters=max_iters)

    # -- Try a few alternative starting guesses and keep the best -------------
    candidates = [
        [span * 0.4, span * 0.25, span * 0.5, span * 0.4, cx0 - span * 0.25, cy0],
        [span * 0.6, span * 0.3, span * 0.7, span * 0.6, cx0 - span * 0.3, cy0 * 0.5],
        [span * 0.5, span * 0.4, span * 0.45, span * 0.5, cx0, cy0],
    ]
    for cand in candidates:
        xc, fc = _nelder_mead(objective, cand, max_iters=max_iters // 2)
        if fc < best_f:
            best_f = fc
            best_x = xc

    r1, r2, r3, r4, px, py = best_x

    # -- Verify: measure actual max error -------------------------------------
    max_err = 0.0
    for pt in pts:
        d = min(
            _nearest_on_curve(r1, r2, r3, r4, px, py,
                               pt[0], pt[1], n_samples=720, branch=b)
            for b in (1, -1)
        )
        if d > max_err:
            max_err = d

    if max_err > tol_mm:
        warnings_list.append(
            f"Synthesised linkage max coupler-curve error {max_err:.4f} mm "
            f"exceeds requested tolerance {tol_mm} mm. "
            "Consider more iterations or different target points."
        )

    grashof = _grashof_type(r1, r2, r3, r4)

    return {
        "ok":           True,
        "r1":           round(r1, 6),
        "r2":           round(r2, 6),
        "r3":           round(r3, 6),
        "r4":           round(r4, 6),
        "px":           round(px, 6),
        "py":           round(py, 6),
        "max_error_mm": round(max_err, 6),
        "grashof":      grashof,
        "warnings":     warnings_list,
    }
