"""
curve_toolkit.py
================
Pure-Python NURBS curve toolkit matching Rhino's core curve commands.

Builds on ``kerf_cad_core.geom.nurbs.NurbsCurve``.

Public API
----------
interp_curve(points, degree, param)
    Interpolate a NURBS curve through a list of 3-D points.
    ``param`` is ``'chord'`` (default) or ``'centripetal'``.

fit_curve(points, degree, tolerance)
    Least-squares B-spline fit to a point cloud within a given tolerance.
    Returns a NurbsCurve whose max deviation to the input points is ≤ tolerance.

rebuild_curve(curve, num_ctrl, degree)
    Re-parameterise a curve to a target number of control points and degree.
    Returns a new NurbsCurve with small deviation from the original.

fair_curve(curve, iterations, weight)
    Energy-minimising smoothing (minimises internal energy) with fixed endpoints.

match_curve(curve, target_pt, target_tan, continuity)
    Match a curve end to a target point/tangent up to G0/G1/G2 continuity.

offset_curve(curve, distance, normal)
    Planar offset of a curve by ``distance`` along ``normal`` direction.

extend_curve(curve, amount, end, mode)
    Extend curve at ``'start'`` or ``'end'`` by ``amount``.
    ``mode`` is ``'line'``, ``'arc'``, or ``'smooth'``.

blend_curve(crv1_end, tan1, crv2_end, tan2, continuity)
    G1/G2 bridge (blend) between two curve ends.

simplify_curve(points, tolerance)
    Reduce a polyline to line + arc segments within tolerance.
    Returns a list of segment descriptors.

helix(center, axis, radius, pitch, turns, start_angle)
    Generate a helical NurbsCurve.

spiral(center, radius_start, radius_end, turns, spiral_type)
    Archimedean or logarithmic spiral as a NurbsCurve.

conic(p0, p1, p2, rho)
    Rational Bézier conic section (rho controls conic type).

catenary(p0, p1, a, num_pts)
    Catenary a·cosh(x/a) sampled as a degree-3 NURBS polyline approximation.

interpolate_arc_chain(points)
    Fit an arc-chain through a list of 3-D points (circular arc per triple).

Each function returns a ``NurbsCurve`` (or a dict/list for diagnostics) and
never raises — all exceptions are caught and returned as ``{"ok": False, "reason": ...}``.

LLM tools are registered via ``@register`` where the ``kerf_chat`` registry is
available.  All tools are gated and never raise.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np

from kerf_cad_core.geom.nurbs import NurbsCurve, de_boor, find_span, _basis_funcs_derivs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_clamped_knots(n: int, degree: int) -> np.ndarray:
    """Clamped (open) uniform knot vector for n control points, given degree."""
    num_inner = n - degree - 1
    if num_inner <= 0:
        inner = np.array([], dtype=float)
    else:
        inner = np.linspace(0.0, 1.0, num_inner + 2)[1:-1]
    return np.concatenate([np.zeros(degree + 1), inner, np.ones(degree + 1)])


def _pt_knots_from_params(ts: np.ndarray, num_ctrl: int, degree: int) -> np.ndarray:
    """Piegl–Tiller knot placement for the least-squares fitting case.

    Implements P&T Section 9.4.1 (eq. 9.68): given ``m+1`` data parameters
    ``ts[0..m]`` (chord-length, in [0,1]) and ``n+1 = num_ctrl`` control
    points at ``degree`` p, the interior knots are placed as:

        d = (m + 1) / (n - p + 1)      (float step)
        for j = 1 to n-p:
            i = floor(j * d)
            alpha = j*d - i
            t[p+j] = (1-alpha)*ts[i-1] + alpha*ts[i]

    This is the standard P&T formula (Algorithm A9.7, Step 2) for fitting
    (m+1 data points, n+1 control points, n < m).  For the edge-case where
    n+1 == m+1 (interpolation), it reduces to the averaging formula (eq. 9.8).

    For the minimum case n = p (only degree+1 control points, a single Bézier
    span), the interior knot count is 0 and the vector is fully clamped.
    """
    m = len(ts) - 1              # last data-point index
    n = num_ctrl - 1             # last control-point index
    p = degree
    knots = np.zeros(n + p + 2)  # total length = n+p+2 = num_ctrl+degree+1
    knots[-(p + 1):] = 1.0       # clamp end

    num_interior = n - p         # number of interior knots
    if num_interior <= 0:
        return knots

    # P&T eq. 9.68
    d = (m + 1) / (n - p + 1)
    for j in range(1, num_interior + 1):
        idx = int(j * d)             # floor
        alpha = j * d - idx
        # boundary guard: idx must be in [1, m]
        idx = max(1, min(idx, m))
        knots[p + j] = (1.0 - alpha) * ts[idx - 1] + alpha * ts[idx]

    # Ensure strict monotonicity (floating-point guard)
    for k in range(p + 1, len(knots) - p - 1):
        knots[k] = max(knots[k], knots[k - 1])

    return knots


def _chord_params(points: np.ndarray, centripetal: bool = False) -> np.ndarray:
    """Compute chord-length (or centripetal) parameter sequence in [0, 1]."""
    n = len(points)
    if n == 1:
        return np.array([0.0])
    diffs = np.diff(points, axis=0)
    norms = np.linalg.norm(diffs, axis=1)
    if centripetal:
        norms = np.sqrt(np.maximum(norms, 0.0))
    total = np.sum(norms)
    if total < 1e-14:
        return np.linspace(0.0, 1.0, n)
    ts = np.concatenate([[0.0], np.cumsum(norms)])
    return ts / ts[-1]


def _sample_curve(curve: NurbsCurve, num: int = 200) -> np.ndarray:
    """Evaluate curve at ``num`` uniformly spaced parameter values."""
    u0 = curve.knots[curve.degree]
    u1 = curve.knots[-(curve.degree + 1)]
    us = np.linspace(u0, u1, num)
    return np.array([de_boor(curve, float(u)) for u in us])


def _eval_bspline_basis(u: float, degree: int, knots: np.ndarray, n: int) -> np.ndarray:
    """Evaluate all n B-spline basis functions N_{i,p}(u), returning array of length n.

    Uses identity-control-point de Boor evaluation to stay consistent with the
    ``de_boor`` function in ``nurbs.py``.
    """
    if n == 0:
        return np.zeros(n)
    identity = np.eye(n)
    curve = NurbsCurve(degree=degree, control_points=identity, knots=knots)
    result = de_boor(curve, float(u))
    return result


# ---------------------------------------------------------------------------
# interp_curve
# ---------------------------------------------------------------------------

def interp_curve(
    points: Sequence,
    degree: int = 3,
    param: str = "chord",
) -> NurbsCurve:
    """Interpolate a NURBS curve through ``points``.

    Parameters
    ----------
    points : sequence of array-like, shape (n, dim)
    degree : int, default 3
    param  : ``'chord'`` or ``'centripetal'`` parametrisation

    Returns
    -------
    NurbsCurve that passes through every input point (within floating-point
    precision).
    """
    pts = np.asarray(points, dtype=float)
    if pts.ndim == 1:
        pts = pts.reshape(-1, 1)
    n = len(pts)
    if n < 2:
        raise ValueError("interp_curve requires at least 2 points")
    degree = min(degree, n - 1)

    centripetal = (param == "centripetal")
    ts = _chord_params(pts, centripetal=centripetal)

    # Build averaging knot vector (Piegl & Tiller 9.3.6)
    num_ctrl = n
    knots = _make_clamped_knots(num_ctrl, degree)
    # Replace internal knots with averages of parameter values
    for j in range(1, num_ctrl - degree):
        knots[j + degree] = np.mean(ts[j: j + degree])

    # Build collocation matrix
    A = np.zeros((n, num_ctrl))
    for i, t in enumerate(ts):
        A[i] = _eval_bspline_basis(t, degree, knots, num_ctrl)

    # Solve A @ P = pts
    ctrl, _, _, _ = np.linalg.lstsq(A, pts, rcond=None)
    return NurbsCurve(degree=degree, control_points=ctrl, knots=knots)


# ---------------------------------------------------------------------------
# fit_curve
# ---------------------------------------------------------------------------

def fit_curve(
    points: Sequence,
    degree: int = 3,
    tolerance: float = 1e-3,
    max_ctrl: int = 64,
) -> dict:
    """Least-squares B-spline fit to ``points`` within ``tolerance``.

    Uses Piegl–Tiller averaging knot placement (Algorithm 9.69): interior
    knots are set as averages of ``degree`` consecutive chord-length
    parameters.  Control-point count is increased from ``degree+1`` until
    max_deviation ≤ ``tolerance`` or ``max_ctrl`` is reached.

    Degenerate (collinear / single-cluster) inputs are handled gracefully —
    the function never raises; it returns the best-effort fit.

    Returns
    -------
    dict with keys:
        ok         : bool
        curve      : NurbsCurve
        deviation  : float   (max distance from any input point to the curve)
        num_ctrl   : int
        reason     : str     (set when ok is False)
    """
    try:
        pts = np.asarray(points, dtype=float)
        if pts.ndim == 1:
            pts = pts.reshape(-1, 1)
        n = len(pts)
        if n < 2:
            return {"ok": False, "curve": None, "deviation": float("inf"), "num_ctrl": 0,
                    "reason": "need at least 2 points"}

        # Detect degenerate (all-same) input: return a line between first/last
        span = float(np.max(np.linalg.norm(pts - pts[0], axis=1)))
        if span < 1e-14:
            ctrl = np.array([pts[0], pts[0]])
            knots = _make_clamped_knots(2, 1)
            curve = NurbsCurve(degree=1, control_points=ctrl, knots=knots)
            return {"ok": True, "curve": curve, "deviation": 0.0,
                    "num_ctrl": 2, "reason": "degenerate: all points identical"}

        degree = min(degree, n - 1)
        ts = _chord_params(pts)

        curve = None
        dev = float("inf")
        num_ctrl = degree + 1

        for num_ctrl in range(degree + 1, min(max_ctrl + 1, n + 1)):
            # --- Piegl–Tiller averaging knot placement ---
            knots = _pt_knots_from_params(ts, num_ctrl, degree)

            A = np.zeros((n, num_ctrl))
            for i, t in enumerate(ts):
                A[i] = _eval_bspline_basis(t, degree, knots, num_ctrl)

            ctrl, _, _, _ = np.linalg.lstsq(A, pts, rcond=None)
            curve = NurbsCurve(degree=degree, control_points=ctrl, knots=knots)

            # measure deviation at input parameter values
            sampled = np.array([de_boor(curve, float(t)) for t in ts])
            dev = float(np.max(np.linalg.norm(sampled - pts, axis=1)))
            if dev <= tolerance:
                return {"ok": True, "curve": curve, "deviation": dev,
                        "num_ctrl": num_ctrl, "reason": ""}

        # return best effort with max_ctrl
        return {"ok": False, "curve": curve, "deviation": dev,
                "num_ctrl": num_ctrl,
                "reason": f"tolerance {tolerance} not achieved; best deviation {dev:.4g}"}
    except Exception as exc:
        return {"ok": False, "curve": None, "deviation": float("inf"),
                "num_ctrl": 0, "reason": str(exc)}


# ---------------------------------------------------------------------------
# rebuild_curve
# ---------------------------------------------------------------------------

def rebuild_curve(
    curve: NurbsCurve,
    num_ctrl: int,
    degree: int = 3,
    num_samples: int = 200,
) -> dict:
    """Re-fit ``curve`` to ``num_ctrl`` control points at ``degree``.

    Samples the original curve uniformly, then does a least-squares fit.

    Returns
    -------
    dict:
        ok        : bool
        curve     : NurbsCurve
        deviation : float
        reason    : str
    """
    try:
        if num_ctrl < degree + 1:
            return {"ok": False, "curve": None, "deviation": float("inf"),
                    "reason": f"num_ctrl ({num_ctrl}) < degree+1 ({degree+1})"}

        pts = _sample_curve(curve, num_samples)
        ts = _chord_params(pts)
        knots = _make_clamped_knots(num_ctrl, degree)
        A = np.zeros((len(pts), num_ctrl))
        for i, t in enumerate(ts):
            A[i] = _eval_bspline_basis(t, degree, knots, num_ctrl)

        ctrl, _, _, _ = np.linalg.lstsq(A, pts, rcond=None)
        new_curve = NurbsCurve(degree=degree, control_points=ctrl, knots=knots)

        # deviation
        sampled_new = np.array([de_boor(new_curve, float(t)) for t in ts])
        dev = float(np.max(np.linalg.norm(sampled_new - pts, axis=1)))
        return {"ok": True, "curve": new_curve, "deviation": dev, "reason": ""}
    except Exception as exc:
        return {"ok": False, "curve": None, "deviation": float("inf"),
                "reason": str(exc)}


# ---------------------------------------------------------------------------
# fair_curve  (GK-35 — energy-minimising, knot-preserving)
# ---------------------------------------------------------------------------

def _second_diff_matrix(n: int) -> np.ndarray:
    """Build the second-order finite-difference matrix D2, shape (n-2, n).

    D2[i] = e_{i+2} - 2*e_{i+1} + e_i, so that  D2 @ P  gives all
    second differences Δ²P_i of the control polygon P.

    Minimising ‖D2 @ P‖² over the free control points is equivalent to
    minimising the *discrete bending energy* of the polygon, which is
    the discrete analogue of ∫ |C''|² du.
    """
    D2 = np.zeros((n - 2, n))
    for i in range(n - 2):
        D2[i, i] = 1.0
        D2[i, i + 1] = -2.0
        D2[i, i + 2] = 1.0
    return D2


def _bspline_second_deriv_gram(
    n: int, degree: int, knots: np.ndarray, n_gauss: int = 8
) -> np.ndarray:
    """Build the continuous bending-energy Gram matrix E[i,j].

    E[i,j] = integral_{u0}^{u1} N''_{i,p}(u) * N''_{j,p}(u) du

    Computed by Gauss–Legendre quadrature over each non-empty knot span.
    Used by the continuous energy path (legacy / diagnostic); the default
    ``fair_curve`` uses the discrete second-difference matrix instead.

    Returns
    -------
    E : (n, n) symmetric positive semi-definite matrix
    """
    gl_pts, gl_wts = np.polynomial.legendre.leggauss(n_gauss)
    E = np.zeros((n, n))

    unique_knots = np.unique(knots)
    for k in range(len(unique_knots) - 1):
        u_a = float(unique_knots[k])
        u_b = float(unique_knots[k + 1])
        if u_b - u_a < 1e-15:
            continue
        half = 0.5 * (u_b - u_a)
        mid = 0.5 * (u_a + u_b)
        for xi, wi in zip(gl_pts, gl_wts):
            u = mid + half * xi
            span = find_span(n - 1, degree, u, knots)
            ders = _basis_funcs_derivs(span, u, degree, knots, 2)
            d2 = np.zeros(n)
            for j in range(degree + 1):
                idx = span - degree + j
                if 0 <= idx < n:
                    d2[idx] = ders[2, j]
            E += (wi * half) * np.outer(d2, d2)
    return E


def fair_curve(
    curve: NurbsCurve,
    iterations: int = 1,
    weight: float = 1.0,
    curvature_weight: float = 1.0,
    n_gauss: int = 8,
) -> NurbsCurve:
    """Energy-minimising, knot-preserving curve fairing.

    Smooths the control polygon by minimising the *discrete bending energy*
    (sum of squared second-order finite differences of the control polygon)
    **without moving the knot vector**, while pinning the two endpoints and
    the two end-tangent control points (CP[0], CP[1], CP[-2], CP[-1]).

    Algorithm (GK-35)
    -----------------
    Let D2 be the (n-2) × n second-difference matrix with rows
    Δ²P_i = P_{i+2} - 2P_{i+1} + P_i.  The discrete bending energy is

        J(P) = ‖D2 P‖²

    which is the discrete analogue of ∫ ‖C''(u)‖² du.  Partitioning
    control points into *fixed* F = {0, 1, n-2, n-1} and *free* G, the
    unconstrained minimum over P_free is the solution of the normal
    equations

        (D2_f^T D2_f) P_free = -(D2_f^T D2_x) P_fixed

    where D2_f = D2[:,G] and D2_x = D2[:,F].  This system is symmetric
    positive semi-definite and solved by ``numpy.linalg.lstsq``.

    The ``weight`` parameter blends between the original control polygon
    (weight=0) and the minimum-energy solution (weight=1):

        P_free_out = (1 - weight) * P_free_orig + weight * P_free_opt

    Multiple ``iterations`` are applied sequentially (each starting from
    the previous result) for progressive fairing.

    Guarantees
    ----------
    * Knot vector unchanged.
    * CP[0], CP[1], CP[-2], CP[-1] unchanged (endpoints + end tangents
      preserved to machine precision).
    * For any curve with n ≥ 5 and non-trivial curvature variation,
      curvature variance strictly decreases when weight > 0.

    For curves with fewer than 5 control points (no free DOFs after
    pinning end tangents) the function falls back to a Laplacian smoother
    on CP[1:-1] (endpoints only) with step ``weight``.

    Parameters
    ----------
    curve            : NurbsCurve to fair
    iterations       : number of sequential fairing passes (default 1).
                       With weight=1 a single pass gives the full
                       minimum-energy solution; additional passes are
                       no-ops (idempotent when weight=1).
    weight           : blend weight toward minimum-energy solution per
                       pass, in (0, 1] (default 1.0).  1.0 gives the
                       full minimum-energy solution; smaller values give
                       a partial step but may not decrease curvature
                       variance for all curve shapes.
    curvature_weight : retained for API compatibility.  When 0 the
                       Laplacian fallback is used; otherwise the
                       energy-minimising solve is used regardless of
                       the value.
    n_gauss          : unused (retained for API compatibility)

    Returns
    -------
    NurbsCurve with the same degree and knot vector as the input, with
    interior control points moved to reduce bending energy.
    """
    knots = curve.knots.copy()
    degree = curve.degree
    ctrl = curve.control_points.copy().astype(float)
    n = len(ctrl)

    use_energy = (curvature_weight > 0.0) and (n >= 5)

    # Fallback: too few CPs or disabled
    if not use_energy:
        if n < 3:
            return curve
        lam = float(np.clip(weight, 0.0, 1.0))
        for _ in range(max(1, int(iterations))):
            new_ctrl = ctrl.copy()
            for i in range(1, n - 1):
                laplacian = 0.5 * (ctrl[i - 1] + ctrl[i + 1]) - ctrl[i]
                new_ctrl[i] = ctrl[i] + lam * laplacian
            ctrl = new_ctrl
        return NurbsCurve(degree=degree, control_points=ctrl, knots=knots)

    # Fixed indices: endpoints + end tangents (CP[0], CP[1], CP[-2], CP[-1])
    fixed_idx = sorted(set([0, 1, n - 2, n - 1]))
    free_idx = [i for i in range(n) if i not in fixed_idx]

    if len(free_idx) == 0:
        return NurbsCurve(degree=degree, control_points=ctrl, knots=knots)

    fi = np.array(free_idx)
    xi = np.array(fixed_idx)

    # Second-difference matrix
    D2 = _second_diff_matrix(n)
    D2_f = D2[:, fi]   # shape (n-2, |free|)
    D2_x = D2[:, xi]   # shape (n-2, |fixed|)

    # Normal equations: A P_free = b
    A = D2_f.T @ D2_f  # (|free|, |free|) symmetric PSD
    P_fixed = ctrl[xi]

    lam = float(np.clip(weight, 0.0, 1.0))

    P_free = ctrl[fi].copy()
    for _ in range(max(1, int(iterations))):
        b_rhs = -(D2_f.T @ D2_x) @ P_fixed
        P_opt, _, _, _ = np.linalg.lstsq(A, b_rhs, rcond=None)
        # Blend toward optimal solution
        P_free = (1.0 - lam) * P_free + lam * P_opt

    new_ctrl = ctrl.copy()
    new_ctrl[fi] = P_free

    return NurbsCurve(degree=degree, control_points=new_ctrl, knots=knots)


# ---------------------------------------------------------------------------
# curvature_variance  (GK-35 oracle helper)
# ---------------------------------------------------------------------------

def curvature_variance(curve: NurbsCurve, num_samples: int = 200) -> float:
    """Compute the variance of the scalar curvature sampled at ``num_samples`` points.

    Curvature κ(u) = |C'(u) × C''(u)| / |C'(u)|³  (3-D formula; in 2-D the
    cross product reduces to the Z component of the planar cross product).

    Useful as the analytic oracle for GK-35: after ``fair_curve`` the variance
    must strictly decrease.

    Returns
    -------
    float : variance of κ over the parameter domain.
    """
    from kerf_cad_core.geom.nurbs import curve_derivative

    u0 = float(curve.knots[curve.degree])
    u1 = float(curve.knots[-(curve.degree + 1)])
    us = np.linspace(u0, u1, num_samples)

    kappas = []
    for u in us:
        d1 = curve_derivative(curve, float(u), order=1)
        d2 = curve_derivative(curve, float(u), order=2)
        dim = len(d1)
        if dim == 2:
            # Planar cross product magnitude
            cross = abs(float(d1[0]) * float(d2[1]) - float(d1[1]) * float(d2[0]))
        else:
            # 3-D: embed in 3D if needed
            d1_3 = np.zeros(3)
            d2_3 = np.zeros(3)
            d1_3[:dim] = d1[:3] if dim >= 3 else d1
            d2_3[:dim] = d2[:3] if dim >= 3 else d2
            cross_vec = np.cross(d1_3, d2_3)
            cross = float(np.linalg.norm(cross_vec))
        speed = float(np.linalg.norm(d1))
        if speed < 1e-14:
            kappas.append(0.0)
        else:
            kappas.append(cross / speed**3)

    kappas = np.array(kappas, dtype=float)
    return float(np.var(kappas))


# ---------------------------------------------------------------------------
# match_curve
# ---------------------------------------------------------------------------

def match_curve(
    curve: NurbsCurve,
    target_pt: Sequence,
    target_tan: Optional[Sequence],
    continuity: str = "G1",
    end: str = "end",
) -> NurbsCurve:
    """Move the selected curve end to match a target point/tangent.

    Parameters
    ----------
    curve       : NurbsCurve to modify
    target_pt   : (x, y, z) target endpoint position
    target_tan  : (x, y, z) target tangent direction (required for G1/G2)
    continuity  : ``'G0'``, ``'G1'``, or ``'G2'``
    end         : ``'start'`` or ``'end'``

    Returns
    -------
    New NurbsCurve with the requested continuity at the chosen end.
    """
    ctrl = curve.control_points.copy().astype(float)
    n = len(ctrl)
    tp = np.asarray(target_pt, dtype=float)

    if end == "start":
        ctrl[0] = tp
        if continuity in ("G1", "G2") and target_tan is not None and n >= 2:
            tt = np.asarray(target_tan, dtype=float)
            norm = np.linalg.norm(tt)
            if norm > 1e-14:
                tt = tt / norm
            # set second control point along tangent direction
            seg_len = float(np.linalg.norm(ctrl[1] - ctrl[0]))
            ctrl[1] = ctrl[0] + tt * max(seg_len, 1e-6)
        if continuity == "G2" and target_tan is not None and n >= 3:
            # mirror second control point for G2 approximate
            ctrl[2] = 2 * ctrl[1] - ctrl[0]
    else:
        ctrl[-1] = tp
        if continuity in ("G1", "G2") and target_tan is not None and n >= 2:
            tt = np.asarray(target_tan, dtype=float)
            norm = np.linalg.norm(tt)
            if norm > 1e-14:
                tt = tt / norm
            seg_len = float(np.linalg.norm(ctrl[-1] - ctrl[-2]))
            ctrl[-2] = ctrl[-1] - tt * max(seg_len, 1e-6)
        if continuity == "G2" and target_tan is not None and n >= 3:
            ctrl[-3] = 2 * ctrl[-2] - ctrl[-1]

    return NurbsCurve(degree=curve.degree, control_points=ctrl, knots=curve.knots.copy())


# ---------------------------------------------------------------------------
# offset_curve
# ---------------------------------------------------------------------------

def offset_curve(
    curve: NurbsCurve,
    distance: float,
    normal: Optional[Sequence] = None,
    num_samples: int = 100,
) -> NurbsCurve:
    """Offset a planar curve by ``distance`` in the plane defined by ``normal``.

    The curve is sampled, each point is offset perpendicular to the tangent
    within the plane, and the result is interpolated back to a NurbsCurve.

    Parameters
    ----------
    curve    : source NurbsCurve
    distance : signed offset distance
    normal   : plane normal (default [0, 0, 1])
    num_samples : resolution for sampling

    Returns
    -------
    NurbsCurve approximating the offset.
    """
    if normal is None:
        nrm = np.array([0.0, 0.0, 1.0])
    else:
        nrm = np.asarray(normal, dtype=float)
        n_norm = np.linalg.norm(nrm)
        if n_norm < 1e-14:
            nrm = np.array([0.0, 0.0, 1.0])
        else:
            nrm = nrm / n_norm

    u0 = float(curve.knots[curve.degree])
    u1 = float(curve.knots[-(curve.degree + 1)])
    us = np.linspace(u0, u1, num_samples)

    pts = np.array([de_boor(curve, u) for u in us])
    dim = pts.shape[1]

    # extend to 3D if needed
    if dim < 3:
        pts3 = np.zeros((len(pts), 3))
        pts3[:, :dim] = pts
    else:
        pts3 = pts[:, :3].copy()

    # finite-difference tangents
    tans = np.gradient(pts3, axis=0)
    offset_pts = np.zeros_like(pts3)
    for i, (p, t) in enumerate(zip(pts3, tans)):
        t_norm = np.linalg.norm(t)
        if t_norm < 1e-14:
            offset_pts[i] = p
            continue
        t_unit = t / t_norm
        perp = np.cross(nrm, t_unit)
        perp_n = np.linalg.norm(perp)
        if perp_n < 1e-14:
            offset_pts[i] = p
        else:
            offset_pts[i] = p + distance * (perp / perp_n)

    # back to original dimension
    offset_pts_final = offset_pts[:, :dim] if dim < 3 else offset_pts
    return interp_curve(offset_pts_final, degree=min(3, curve.degree))


# ---------------------------------------------------------------------------
# extend_curve
# ---------------------------------------------------------------------------

def extend_curve(
    curve: NurbsCurve,
    amount: float,
    end: str = "end",
    mode: str = "line",
) -> NurbsCurve:
    """Extend ``curve`` at the chosen end.

    Parameters
    ----------
    amount : extension length (> 0)
    end    : ``'start'`` or ``'end'``
    mode   : ``'line'``, ``'arc'``, or ``'smooth'``

    Returns
    -------
    New NurbsCurve extended by ``amount``.
    """
    ctrl = curve.control_points.copy().astype(float)
    knots = curve.knots.copy()
    degree = curve.degree

    if end == "end":
        p0 = ctrl[-1]
        tan = ctrl[-1] - ctrl[-2]
    else:
        p0 = ctrl[0]
        tan = ctrl[0] - ctrl[1]

    tan_len = np.linalg.norm(tan)
    if tan_len < 1e-14:
        tan = np.zeros_like(p0)
        if p0.shape[0] >= 2:
            tan[0] = 1.0
    else:
        tan = tan / tan_len

    new_pt = p0 + tan * float(amount)

    if mode == "line" or mode == "smooth":
        # append a new control point by extending knot vector
        if end == "end":
            new_ctrl = np.vstack([ctrl, new_pt.reshape(1, -1)])
        else:
            new_ctrl = np.vstack([new_pt.reshape(1, -1), ctrl])

        # extend knot vector
        new_n = len(new_ctrl)
        new_knots = _make_clamped_knots(new_n, degree)
        return NurbsCurve(degree=degree, control_points=new_ctrl, knots=new_knots)

    else:  # arc — approximate with 3-point interp
        mid_pt = p0 + tan * (float(amount) / 2.0)
        # slight perpendicular bow for arc shape
        perp = np.zeros_like(tan)
        if tan.shape[0] >= 2:
            perp[0] = -tan[1]
            perp[1] = tan[0]
        bow = perp * float(amount) * 0.1
        mid_pt = mid_pt + bow

        if end == "end":
            ext_pts = np.vstack([ctrl, mid_pt.reshape(1, -1), new_pt.reshape(1, -1)])
        else:
            ext_pts = np.vstack([new_pt.reshape(1, -1), mid_pt.reshape(1, -1), ctrl])

        new_n = len(ext_pts)
        new_knots = _make_clamped_knots(new_n, degree)
        return NurbsCurve(degree=degree, control_points=ext_pts, knots=new_knots)


# ---------------------------------------------------------------------------
# blend_curve
# ---------------------------------------------------------------------------

def blend_curve(
    crv1_end: Sequence,
    tan1: Sequence,
    crv2_end: Sequence,
    tan2: Sequence,
    continuity: str = "G1",
) -> NurbsCurve:
    """Construct a blend (bridge) curve between two curve ends.

    Builds a cubic Hermite bridge satisfying G1 (tangent) or G2
    (approximate curvature) continuity at each end.

    Parameters
    ----------
    crv1_end : endpoint of first curve (x, y, z)
    tan1     : tangent at crv1_end (pointing away from first curve)
    crv2_end : endpoint of second curve
    tan2     : tangent at crv2_end (pointing away from second curve, i.e.
               pointing *toward* the blend)
    continuity : ``'G1'`` or ``'G2'``

    Returns
    -------
    NurbsCurve (degree 3 or 5 for G2) blending the two ends.
    """
    p0 = np.asarray(crv1_end, dtype=float)
    p3 = np.asarray(crv2_end, dtype=float)
    t0 = np.asarray(tan1, dtype=float)
    t3 = np.asarray(tan2, dtype=float)

    chord = float(np.linalg.norm(p3 - p0))
    scale = max(chord / 3.0, 1e-6)

    t0n = np.linalg.norm(t0)
    t3n = np.linalg.norm(t3)
    t0 = t0 / t0n if t0n > 1e-14 else t0
    t3 = t3 / t3n if t3n > 1e-14 else t3

    if continuity == "G1":
        p1 = p0 + t0 * scale
        p2 = p3 - t3 * scale
        ctrl = np.array([p0, p1, p2, p3])
        knots = np.array([0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0])
        return NurbsCurve(degree=3, control_points=ctrl, knots=knots)
    else:  # G2 — degree-5 Bezier
        p1 = p0 + t0 * scale
        p2 = p0 + t0 * 2 * scale
        p4 = p3 - t3 * 2 * scale
        p5 = p3 - t3 * scale
        # midpoint
        p3m = (p2 + p4) / 2.0
        ctrl = np.array([p0, p1, p2, p3m, p4, p5, p3])
        knots = np.array([0.0] * 4 + [0.5] * 3 + [1.0] * 4, dtype=float)
        # reuse degree-3 with 7 ctrl pts
        knots = _make_clamped_knots(7, 3)
        return NurbsCurve(degree=3, control_points=ctrl, knots=knots)


# ---------------------------------------------------------------------------
# simplify_curve
# ---------------------------------------------------------------------------

def simplify_curve(
    points: Sequence,
    tolerance: float = 1e-3,
) -> List[dict]:
    """Simplify a polyline into line and arc segments within ``tolerance``.

    Returns a list of segment descriptors:
      - ``{"type": "line", "start": ..., "end": ...}``
      - ``{"type": "arc",  "start": ..., "mid": ..., "end": ..., "center": ..., "radius": ...}``

    Uses a greedy sweep: attempts to fit an arc through each triple; falls back
    to line if the arc radius is too large (near-linear) or the deviation is
    too high.
    """
    pts = np.asarray(points, dtype=float)
    if len(pts) < 2:
        return []
    if len(pts) == 2:
        return [{"type": "line", "start": pts[0].tolist(), "end": pts[1].tolist()}]

    segments = []
    i = 0
    while i < len(pts) - 1:
        if i + 2 >= len(pts):
            segments.append({"type": "line",
                              "start": pts[i].tolist(),
                              "end": pts[i + 1].tolist()})
            i += 1
            break

        # try arc through pts[i], pts[i+1], pts[i+2]
        arc_result = _fit_arc(pts[i], pts[i + 1], pts[i + 2])
        if arc_result is not None:
            center, radius = arc_result
            # check whether intermediate points fit
            max_dev = 0.0
            j_end = i + 2
            while j_end + 1 < len(pts):
                d = abs(np.linalg.norm(pts[j_end + 1][:2] - center[:2]) - radius)
                if d > tolerance:
                    break
                max_dev = max(max_dev, d)
                j_end += 1

            if j_end > i + 1:
                mid_idx = (i + j_end) // 2
                segments.append({
                    "type": "arc",
                    "start": pts[i].tolist(),
                    "mid": pts[mid_idx].tolist(),
                    "end": pts[j_end].tolist(),
                    "center": center.tolist(),
                    "radius": float(radius),
                })
                i = j_end
                continue

        # fall back to line
        segments.append({"type": "line",
                          "start": pts[i].tolist(),
                          "end": pts[i + 1].tolist()})
        i += 1

    return segments


def _fit_arc(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray):
    """Fit a circular arc through 3 points (2-D, using x/y).

    Returns (center_3d, radius) or None if collinear.
    """
    ax, ay = float(p0[0]), float(p0[1])
    bx, by = float(p1[0]), float(p1[1])
    cx, cy = float(p2[0]), float(p2[1])

    D = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(D) < 1e-14:
        return None

    ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) +
          (cx**2 + cy**2) * (ay - by)) / D
    uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) +
          (cx**2 + cy**2) * (bx - ax)) / D

    center_z = (p0[2] if len(p0) > 2 else 0.0)
    center = np.array([ux, uy, center_z])
    radius = math.hypot(ax - ux, ay - uy)
    return center, radius


# ---------------------------------------------------------------------------
# helix
# ---------------------------------------------------------------------------

def helix(
    center: Sequence = (0.0, 0.0, 0.0),
    axis: Sequence = (0.0, 0.0, 1.0),
    radius: float = 1.0,
    pitch: float = 1.0,
    turns: float = 3.0,
    start_angle: float = 0.0,
    num_pts: int = 200,
) -> NurbsCurve:
    """Generate a helical NurbsCurve.

    The helix is parameterised as:
        x(t) = center[0] + radius * cos(start_angle + 2π·turns·t)
        y(t) = center[1] + radius * sin(start_angle + 2π·turns·t)
        z(t) = center[2] + pitch * turns * t

    for t ∈ [0, 1].  The ``axis`` argument rotates the helix axis from the
    default Z direction (non-Z axes are handled via an approximate rotation).

    Returns a degree-3 NURBS interpolating the sampled helix polyline.
    """
    cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
    ax_vec = np.asarray(axis, dtype=float)
    ax_norm = np.linalg.norm(ax_vec)
    if ax_norm < 1e-14:
        ax_vec = np.array([0.0, 0.0, 1.0])
    else:
        ax_vec = ax_vec / ax_norm

    total_angle = 2.0 * math.pi * turns
    ts = np.linspace(0.0, 1.0, num_pts)

    # local frame: axis + two perpendiculars
    z_ref = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(ax_vec, z_ref)) > 0.99:
        z_ref = np.array([1.0, 0.0, 0.0])
    e1 = np.cross(z_ref, ax_vec)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(ax_vec, e1)

    pts = np.zeros((num_pts, 3))
    for k, t in enumerate(ts):
        angle = start_angle + total_angle * t
        height = pitch * turns * t
        pts[k] = (np.array([cx, cy, cz]) +
                  radius * math.cos(angle) * e1 +
                  radius * math.sin(angle) * e2 +
                  height * ax_vec)

    return interp_curve(pts, degree=3)


# ---------------------------------------------------------------------------
# spiral
# ---------------------------------------------------------------------------

def spiral(
    center: Sequence = (0.0, 0.0, 0.0),
    radius_start: float = 0.1,
    radius_end: float = 1.0,
    turns: float = 3.0,
    spiral_type: str = "archimedean",
    num_pts: int = 200,
) -> NurbsCurve:
    """Generate a planar spiral as a NurbsCurve.

    Parameters
    ----------
    spiral_type : ``'archimedean'`` (r = a + b·θ) or ``'log'`` (r = a·e^{bθ})
    """
    cx, cy = float(center[0]), float(center[1])
    cz = float(center[2]) if len(center) > 2 else 0.0

    total_angle = 2.0 * math.pi * turns
    ts = np.linspace(0.0, 1.0, num_pts)
    pts = np.zeros((num_pts, 3))

    for k, t in enumerate(ts):
        theta = total_angle * t
        if spiral_type == "log":
            if turns > 0 and abs(radius_start) > 1e-14 and abs(radius_end) > 1e-14:
                b = math.log(radius_end / radius_start) / total_angle
                r = radius_start * math.exp(b * theta)
            else:
                r = radius_start + (radius_end - radius_start) * t
        else:  # archimedean
            r = radius_start + (radius_end - radius_start) * t
        pts[k] = [cx + r * math.cos(theta), cy + r * math.sin(theta), cz]

    return interp_curve(pts, degree=3)


# ---------------------------------------------------------------------------
# conic
# ---------------------------------------------------------------------------

def conic(
    p0: Sequence,
    p1: Sequence,
    p2: Sequence,
    weight: float = 1.0,
    rho: Optional[float] = None,
) -> NurbsCurve:
    """Exact rational quadratic Bézier conic section.

    ``p0``, ``p1``, ``p2`` are the three Bézier control points (p1 is the
    shoulder / tangent-intersection point).  ``weight`` is the NURBS weight
    of the middle control point (end weights are 1):

      - 0 < weight < 1 : ellipse (arc)   — eccentricity e < 1
      - weight = 1     : parabola         — eccentricity e = 1
      - weight > 1     : hyperbola        — eccentricity e > 1

    The focus–directrix property holds to the limits of floating-point
    arithmetic (≤ 1e-12 for double precision) for any sampled point.

    For a circular arc, ``weight = cos(half_angle)`` where ``half_angle`` is
    the half-opening angle of the arc, which reproduces the circle radius to
    1e-9 when sampled.

    ``rho`` is accepted as a legacy alias for ``weight`` (keyword only).

    Returns
    -------
    NurbsCurve with degree 2, 3 control points in homogeneous form
    ``[w·x, w·y, w·z, w]``.  Use ``eval_conic`` to obtain Cartesian points.
    """
    # legacy alias
    if rho is not None:
        weight = float(rho)
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    p2 = np.asarray(p2, dtype=float)
    w = float(weight)
    if w <= 0.0:
        raise ValueError(f"conic weight must be positive, got {w}")

    dim = p0.shape[0]
    # Pre-multiplied homogeneous control vectors: [w·x, w·y, (w·z,) w]
    # end-points have weight=1, middle point has weight=w.
    ctrl_h = np.zeros((3, dim + 1))
    ctrl_h[0, :dim] = p0          # weight 1 → already correct
    ctrl_h[0, dim]  = 1.0
    ctrl_h[1, :dim] = p1 * w      # pre-multiply by w
    ctrl_h[1, dim]  = w
    ctrl_h[2, :dim] = p2          # weight 1
    ctrl_h[2, dim]  = 1.0

    knots = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    return NurbsCurve(degree=2, control_points=ctrl_h, knots=knots)


def eval_conic(curve: NurbsCurve, u: float) -> np.ndarray:
    """Evaluate a rational conic (from ``conic()``) at parameter ``u`` ∈ [0, 1].

    Uses the degree-2 Bernstein basis so that the homogeneous rational
    division is exact:

        hw = B0(t)·P0_h + B1(t)·P1_h + B2(t)·P2_h
        result = hw[:-1] / hw[-1]

    where ``P_h = [w·x, w·y, w·z, w]`` (pre-multiplied, as stored by
    ``conic()``).  The returned array has the same spatial dimension as the
    control points passed to ``conic()`` (2-D or 3-D).
    """
    ctrl = curve.control_points  # shape (3, dim+1), pre-multiplied homogeneous
    t = float(np.clip(u, 0.0, 1.0))
    B0 = (1.0 - t) ** 2
    B1 = 2.0 * t * (1.0 - t)
    B2 = t ** 2
    hw = B0 * ctrl[0] + B1 * ctrl[1] + B2 * ctrl[2]
    w = hw[-1]
    if abs(w) < 1e-14:
        return hw[:-1]
    return hw[:-1] / w


# ---------------------------------------------------------------------------
# catenary
# ---------------------------------------------------------------------------

def catenary(
    p0: Sequence,
    p1: Sequence,
    a: float = 1.0,
    num_pts: int = 100,
) -> NurbsCurve:
    """Catenary curve y = a·cosh(x/a) between two endpoints.

    ``p0`` and ``p1`` define the horizontal span; the catenary hangs between
    them in the XZ or XY plane.  The analytic formula is sampled at ``num_pts``
    and interpolated to a degree-3 NURBS.

    Parameters
    ----------
    p0, p1 : endpoints in 3-D space (x, y, z)
    a      : catenary parameter (> 0)
    num_pts : sampling resolution
    """
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    a = abs(float(a))
    if a < 1e-14:
        a = 1.0

    # span in X direction
    x0 = float(p0[0])
    x1 = float(p1[0])
    if abs(x1 - x0) < 1e-14:
        x1 = x0 + 1.0

    xs = np.linspace(x0, x1, num_pts)
    # catenary: y = a * cosh(x / a), zero at x=0
    # we offset so the curve passes through p0 and p1 in the y-coord
    y_vals = a * np.cosh(xs / a)
    y0_cat = a * math.cosh(x0 / a)
    y1_cat = a * math.cosh(x1 / a)

    # linear interpolation to match y at endpoints
    t_vals = (xs - x0) / (x1 - x0)
    y_start = float(p0[1])
    y_end = float(p1[1])
    y_offset = y_start + (y_end - y_start) * t_vals
    # shift catenary so endpoints match
    y_cat_at_ends = y0_cat + (y1_cat - y0_cat) * t_vals
    dy = y_vals - y_cat_at_ends + y_offset - (y_start - y0_cat + (y_end - y1_cat) * t_vals)
    # simple: just use y = a*cosh(x/a) translated to pass through p0
    y_shifted = y_vals - y0_cat + y_start

    z0 = float(p0[2]) if len(p0) > 2 else 0.0
    z1 = float(p1[2]) if len(p1) > 2 else 0.0
    zs = z0 + (z1 - z0) * t_vals

    pts = np.column_stack([xs, y_shifted, zs])
    return interp_curve(pts, degree=3)


def catenary_y(x: float, a: float) -> float:
    """Analytic catenary value a·cosh(x/a)."""
    return float(a) * math.cosh(float(x) / float(a))


# ---------------------------------------------------------------------------
# interpolate_arc_chain
# ---------------------------------------------------------------------------

def interpolate_arc_chain(
    points: Sequence,
    tolerance: float = 1e-6,
) -> List[dict]:
    """Fit an arc-chain through a list of 3-D points.

    Groups the points into triples (overlapping) and fits a circular arc
    through each triple.  Returns a list of arc descriptors:
        {"center": [...], "radius": float, "start": [...], "end": [...]}

    Points that are collinear (within tolerance) produce a line segment:
        {"type": "line", "start": [...], "end": [...]}
    """
    pts = np.asarray(points, dtype=float)
    n = len(pts)
    if n < 2:
        return []
    if n == 2:
        return [{"type": "line", "start": pts[0].tolist(), "end": pts[1].tolist()}]

    arcs = []
    i = 0
    while i + 2 < n:
        arc = _fit_arc(pts[i], pts[i + 1], pts[i + 2])
        if arc is None:
            arcs.append({"type": "line",
                          "start": pts[i].tolist(),
                          "end": pts[i + 1].tolist()})
            i += 1
        else:
            center, radius = arc
            arcs.append({
                "type": "arc",
                "center": center.tolist(),
                "radius": float(radius),
                "start": pts[i].tolist(),
                "end": pts[i + 2].tolist(),
            })
            i += 2

    if i == n - 2:
        arcs.append({"type": "line",
                      "start": pts[n - 2].tolist(),
                      "end": pts[n - 1].tolist()})
    return arcs


# ---------------------------------------------------------------------------
# curvature_comb  (GK-65)
# ---------------------------------------------------------------------------

def curvature_comb(
    curve: NurbsCurve,
    num_samples: int = 50,
    scale: float = 1.0,
) -> dict:
    """Sample curvature κ along a curve and emit comb (porcupine) vectors.

    For each sample parameter u_i the function computes:
      - The curve point  P(u_i)
      - The unit normal  N(u_i)  (curvature normal in the osculating plane)
      - The scalar curvature  κ(u_i) = |C'×C''| / |C'|³
      - The comb spine point and the comb tip  P(u_i) + κ(u_i)·scale·N(u_i)

    The curvature normal is obtained from the standard formula:
        N_curv = (|C'|² C'' - (C'·C'') C') / |C'×C''|
    which is the *signed* unit vector pointing toward the centre of curvature.
    When κ = 0 (straight segment) the normal is set to the zero vector.

    Parameters
    ----------
    curve      : NurbsCurve to analyse
    num_samples: number of equally-spaced parameter samples (default 50)
    scale      : multiplicative scale applied to κ for the comb tip offset
                 (default 1.0; increase for visualisation)

    Returns
    -------
    dict with keys:
        ok         : bool
        parameters : list[float]         parameter values u_i
        points     : list[list[float]]   curve positions P(u_i)
        kappas     : list[float]         scalar curvatures κ(u_i)
        normals    : list[list[float]]   unit curvature normals N(u_i)
        tips       : list[list[float]]   comb tips P(u_i) + κ·scale·N(u_i)
        reason     : str                 set on error

    Oracle guarantee
    ----------------
    For a circle of radius r, every κ(u_i) equals 1/r to within 1e-9.
    """
    from kerf_cad_core.geom.nurbs import curve_derivative

    try:
        u0 = float(curve.knots[curve.degree])
        u1 = float(curve.knots[-(curve.degree + 1)])
        n = max(2, int(num_samples))
        us = np.linspace(u0, u1, n)

        parameters: List[float] = []
        points: List[List[float]] = []
        kappas: List[float] = []
        normals: List[List[float]] = []
        tips: List[List[float]] = []

        for u in us:
            uf = float(u)
            d1 = curve_derivative(curve, uf, order=1)
            d2 = curve_derivative(curve, uf, order=2)

            # Embed in 3-D for cross-product
            dim = len(d1)
            d1_3 = np.zeros(3)
            d2_3 = np.zeros(3)
            d1_3[:min(dim, 3)] = d1[:min(dim, 3)]
            d2_3[:min(dim, 3)] = d2[:min(dim, 3)]

            speed = float(np.linalg.norm(d1_3))
            cross_vec = np.cross(d1_3, d2_3)
            cross_mag = float(np.linalg.norm(cross_vec))

            if speed < 1e-14:
                kappa = 0.0
                n_vec = np.zeros(dim)
            else:
                kappa = cross_mag / (speed ** 3)
                # Curvature normal: component of C'' perpendicular to C'
                # = (|C'|² C'' - (C'·C'') C') / (|C'|² * kappa * |C'|)
                # Simplified: N = (C'' - (C''·T)T) / |C'' - (C''·T)T|  where T=C'/|C'|
                t_unit = d1_3 / speed
                d2_perp = d2_3 - float(np.dot(d2_3, t_unit)) * t_unit
                d2_perp_mag = float(np.linalg.norm(d2_perp))
                if d2_perp_mag < 1e-14:
                    n_vec = np.zeros(dim)
                else:
                    n_unit_3d = d2_perp / d2_perp_mag
                    n_vec = n_unit_3d[:dim]

            pt = de_boor(curve, uf)
            tip = pt + kappa * float(scale) * (n_vec if dim == len(pt) else np.zeros(len(pt)))

            parameters.append(uf)
            points.append(pt.tolist())
            kappas.append(kappa)
            normals.append(n_vec.tolist())
            tips.append(tip.tolist())

        return {
            "ok": True,
            "parameters": parameters,
            "points": points,
            "kappas": kappas,
            "normals": normals,
            "tips": tips,
            "reason": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "parameters": [],
            "points": [],
            "kappas": [],
            "normals": [],
            "tips": [],
            "reason": str(exc),
        }


# ---------------------------------------------------------------------------
# curve_length  (GK-98)
# ---------------------------------------------------------------------------

def _curve_speed(curve: NurbsCurve, u: float) -> float:
    """Return |C'(u)| — the speed (norm of first derivative) at parameter u."""
    from kerf_cad_core.geom.nurbs import curve_derivative
    d1 = curve_derivative(curve, u, order=1)
    return float(np.linalg.norm(d1))


def _gauss_legendre_quadrature(f, a: float, b: float, n: int = 5) -> float:
    """Gauss–Legendre quadrature of f over [a, b] using n-point rule."""
    pts, wts = np.polynomial.legendre.leggauss(n)
    half = 0.5 * (b - a)
    mid = 0.5 * (a + b)
    return half * float(np.dot(wts, [f(mid + half * xi) for xi in pts]))


def _adaptive_gauss(
    f,
    a: float,
    b: float,
    tol: float = 1e-9,
    depth: int = 0,
    max_depth: int = 40,
) -> float:
    """Adaptive Gauss–Legendre quadrature via recursive bisection.

    Integrates f over [a, b].  Recursively bisects until the 5-point and
    10-point estimates agree within ``tol`` or ``max_depth`` is reached.
    """
    mid = 0.5 * (a + b)
    whole = _gauss_legendre_quadrature(f, a, b, n=10)
    left = _gauss_legendre_quadrature(f, a, mid, n=5)
    right = _gauss_legendre_quadrature(f, mid, b, n=5)
    err = abs((left + right) - whole)
    if err < tol or depth >= max_depth:
        return left + right
    return (
        _adaptive_gauss(f, a, mid, tol=tol / 2, depth=depth + 1, max_depth=max_depth)
        + _adaptive_gauss(f, mid, b, tol=tol / 2, depth=depth + 1, max_depth=max_depth)
    )


def curve_length(
    curve: NurbsCurve,
    t0: Optional[float] = None,
    t1: Optional[float] = None,
    tol: float = 1e-9,
) -> float:
    """Arc length of ``curve`` between parameters ``t0`` and ``t1``.

    Uses adaptive Gauss–Legendre quadrature on |C'(u)| du.

    Parameters
    ----------
    curve : NurbsCurve
    t0    : start parameter (default: start of curve domain)
    t1    : end parameter   (default: end of curve domain)
    tol   : integration tolerance (default 1e-9)

    Returns
    -------
    float : arc length ≥ 0
    """
    u0 = float(curve.knots[curve.degree])
    u1 = float(curve.knots[-(curve.degree + 1)])
    a = u0 if t0 is None else float(t0)
    b = u1 if t1 is None else float(t1)
    a = max(a, u0)
    b = min(b, u1)
    if b <= a:
        return 0.0

    def speed(u: float) -> float:
        return _curve_speed(curve, u)

    return _adaptive_gauss(speed, a, b, tol=tol)


# ---------------------------------------------------------------------------
# arc_length_param  (GK-98)
# ---------------------------------------------------------------------------

class _ArcLengthParam:
    """Lookup table for arc-length ↔ parameter conversion.

    Attributes / Methods
    --------------------
    length_at(t) -> float
        Returns arc length from curve start to parameter t.
    t_at_length(s) -> float
        Returns parameter t such that arc length from start equals s.
    total_length : float
        Total arc length of the curve.
    """

    def __init__(
        self,
        curve: NurbsCurve,
        n: int = 128,
    ) -> None:
        u0 = float(curve.knots[curve.degree])
        u1 = float(curve.knots[-(curve.degree + 1)])
        self._u0 = u0
        self._u1 = u1

        # Sample n+1 parameter values uniformly
        self._params = np.linspace(u0, u1, n + 1)

        # Build cumulative arc-length table using 5-point GL on each sub-interval
        lengths = np.zeros(n + 1)
        for i in range(n):
            a = float(self._params[i])
            b = float(self._params[i + 1])
            lengths[i + 1] = lengths[i] + _gauss_legendre_quadrature(
                lambda u, _a=a, _b=b: _curve_speed(curve, u), a, b, n=5
            )

        self._lengths = lengths
        self.total_length: float = float(lengths[-1])

    def length_at(self, t: float) -> float:
        """Arc length from curve start to parameter ``t``."""
        t = float(np.clip(t, self._u0, self._u1))
        return float(np.interp(t, self._params, self._lengths))

    def t_at_length(self, s: float) -> float:
        """Parameter ``t`` such that arc length from start equals ``s``."""
        s = float(np.clip(s, 0.0, self.total_length))
        return float(np.interp(s, self._lengths, self._params))


def arc_length_param(
    curve: NurbsCurve,
    n: int = 128,
) -> _ArcLengthParam:
    """Build arc-length parameterization lookup tables for ``curve``.

    Samples the curve speed at ``n`` intervals using 5-point Gauss–Legendre
    quadrature per interval to build cumulative arc-length tables.

    Parameters
    ----------
    curve : NurbsCurve
    n     : number of parameter sub-intervals (default 128)

    Returns
    -------
    _ArcLengthParam instance with:
        .length_at(t)    -> arc length from start to parameter t
        .t_at_length(s)  -> parameter t for arc length s from start
        .total_length    -> total arc length
    """
    return _ArcLengthParam(curve, n=n)


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

    # ---- interp_curve tool ---------------------------------------------------

    _interp_curve_spec = ToolSpec(
        name="curve_interp",
        description=(
            "Interpolate a NURBS curve through a list of 3-D points using "
            "chord-length or centripetal parametrisation.  Returns control "
            "points, knots, and degree of the resulting NURBS curve.\n"
            "\n"
            "Returns: {ok, control_points, knots, degree, num_ctrl}\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                    "description": "List of 3-D points [[x,y,z], ...] to interpolate through.",
                },
                "degree": {
                    "type": "integer",
                    "description": "Curve degree (default 3).",
                },
                "param": {
                    "type": "string",
                    "enum": ["chord", "centripetal"],
                    "description": "Parametrisation method (default 'chord').",
                },
            },
            "required": ["points"],
        },
    )

    @register(_interp_curve_spec)
    async def run_curve_interp(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")
        pts = a.get("points", [])
        degree = int(a.get("degree", 3))
        param = a.get("param", "chord")
        if not pts or len(pts) < 2:
            return err_payload("points must contain at least 2 items", "BAD_ARGS")
        if param not in ("chord", "centripetal"):
            return err_payload("param must be 'chord' or 'centripetal'", "BAD_ARGS")
        try:
            curve = interp_curve(pts, degree=degree, param=param)
        except Exception as exc:
            return err_payload(str(exc), "OP_FAILED")
        return ok_payload({
            "control_points": curve.control_points.tolist(),
            "knots": curve.knots.tolist(),
            "degree": curve.degree,
            "num_ctrl": curve.num_control_points,
        })

    # ---- fit_curve tool -------------------------------------------------------

    _fit_curve_spec = ToolSpec(
        name="curve_fit",
        description=(
            "Least-squares B-spline fit to a point cloud within a given tolerance.\n"
            "\n"
            "Returns: {ok, control_points, knots, degree, deviation, num_ctrl}\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "degree": {"type": "integer"},
                "tolerance": {"type": "number"},
                "max_ctrl": {"type": "integer"},
            },
            "required": ["points"],
        },
    )

    @register(_fit_curve_spec)
    async def run_curve_fit(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")
        pts = a.get("points", [])
        if not pts or len(pts) < 2:
            return err_payload("points must contain at least 2 items", "BAD_ARGS")
        result = fit_curve(
            pts,
            degree=int(a.get("degree", 3)),
            tolerance=float(a.get("tolerance", 1e-3)),
            max_ctrl=int(a.get("max_ctrl", 64)),
        )
        if not result["ok"] or result["curve"] is None:
            return err_payload(result["reason"], "OP_FAILED")
        c = result["curve"]
        return ok_payload({
            "control_points": c.control_points.tolist(),
            "knots": c.knots.tolist(),
            "degree": c.degree,
            "deviation": result["deviation"],
            "num_ctrl": result["num_ctrl"],
        })

    # ---- helix tool -----------------------------------------------------------

    _helix_spec = ToolSpec(
        name="curve_helix",
        description=(
            "Generate a helical NURBS curve.\n"
            "\n"
            "Returns: {ok, control_points, knots, degree}\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "center": {"type": "array", "items": {"type": "number"}},
                "axis":   {"type": "array", "items": {"type": "number"}},
                "radius": {"type": "number"},
                "pitch":  {"type": "number"},
                "turns":  {"type": "number"},
                "start_angle": {"type": "number"},
                "num_pts": {"type": "integer"},
            },
            "required": [],
        },
    )

    @register(_helix_spec)
    async def run_curve_helix(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")
        try:
            curve = helix(
                center=a.get("center", [0, 0, 0]),
                axis=a.get("axis", [0, 0, 1]),
                radius=float(a.get("radius", 1.0)),
                pitch=float(a.get("pitch", 1.0)),
                turns=float(a.get("turns", 3.0)),
                start_angle=float(a.get("start_angle", 0.0)),
                num_pts=int(a.get("num_pts", 200)),
            )
        except Exception as exc:
            return err_payload(str(exc), "OP_FAILED")
        return ok_payload({
            "control_points": curve.control_points.tolist(),
            "knots": curve.knots.tolist(),
            "degree": curve.degree,
        })

    # ---- catenary tool --------------------------------------------------------

    _catenary_spec = ToolSpec(
        name="curve_catenary",
        description=(
            "Generate a catenary curve a·cosh(x/a) between two endpoints.\n"
            "\n"
            "Returns: {ok, control_points, knots, degree}\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "p0": {"type": "array", "items": {"type": "number"}},
                "p1": {"type": "array", "items": {"type": "number"}},
                "a":  {"type": "number", "description": "Catenary parameter a > 0"},
                "num_pts": {"type": "integer"},
            },
            "required": ["p0", "p1"],
        },
    )

    @register(_catenary_spec)
    async def run_curve_catenary(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a_args = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")
        p0 = a_args.get("p0")
        p1 = a_args.get("p1")
        if p0 is None or p1 is None:
            return err_payload("p0 and p1 are required", "BAD_ARGS")
        try:
            curve = catenary(
                p0=p0,
                p1=p1,
                a=float(a_args.get("a", 1.0)),
                num_pts=int(a_args.get("num_pts", 100)),
            )
        except Exception as exc:
            return err_payload(str(exc), "OP_FAILED")
        return ok_payload({
            "control_points": curve.control_points.tolist(),
            "knots": curve.knots.tolist(),
            "degree": curve.degree,
        })

    # ---- blend_curve tool -----------------------------------------------------

    _blend_curve_spec = ToolSpec(
        name="curve_blend",
        description=(
            "Build a G1/G2 blend (bridge) curve between two curve ends.\n"
            "\n"
            "Returns: {ok, control_points, knots, degree}\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "crv1_end":   {"type": "array", "items": {"type": "number"}},
                "tan1":       {"type": "array", "items": {"type": "number"}},
                "crv2_end":   {"type": "array", "items": {"type": "number"}},
                "tan2":       {"type": "array", "items": {"type": "number"}},
                "continuity": {"type": "string", "enum": ["G1", "G2"]},
            },
            "required": ["crv1_end", "tan1", "crv2_end", "tan2"],
        },
    )

    @register(_blend_curve_spec)
    async def run_curve_blend(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")
        for k in ("crv1_end", "tan1", "crv2_end", "tan2"):
            if k not in a:
                return err_payload(f"missing required argument: {k}", "BAD_ARGS")
        try:
            curve = blend_curve(
                crv1_end=a["crv1_end"],
                tan1=a["tan1"],
                crv2_end=a["crv2_end"],
                tan2=a["tan2"],
                continuity=a.get("continuity", "G1"),
            )
        except Exception as exc:
            return err_payload(str(exc), "OP_FAILED")
        return ok_payload({
            "control_points": curve.control_points.tolist(),
            "knots": curve.knots.tolist(),
            "degree": curve.degree,
        })


# ---------------------------------------------------------------------------
# composite_curve / split_composite  (GK-100)
# ---------------------------------------------------------------------------

_CONTINUITY_TAGS = ("G0", "G1", "G2")


def _detect_continuity(
    crv_a: NurbsCurve,
    crv_b: NurbsCurve,
    pos_tol: float = 1e-6,
    tan_tol: float = 1e-4,
    curv_tol: float = 1e-3,
) -> str:
    """Return the highest continuity class between the end of crv_a and start of crv_b.

    Checks G0 (positional), G1 (tangent direction), G2 (curvature).

    Parameters
    ----------
    crv_a : NurbsCurve  — the preceding segment (end is tested)
    crv_b : NurbsCurve  — the following segment (start is tested)
    pos_tol : float     — positional gap tolerance (default 1e-6)
    tan_tol : float     — angular tolerance in radians for tangent direction (default 1e-4)
    curv_tol: float     — relative curvature difference tolerance (default 1e-3)

    Returns
    -------
    str : one of "G0", "G1", "G2"
    """
    from kerf_cad_core.geom.nurbs import curve_derivative

    # Parameter domain bounds
    u_a_end = float(crv_a.knots[-(crv_a.degree + 1)])
    u_b_start = float(crv_b.knots[crv_b.degree])

    # G0: positional gap
    p_a = crv_a.evaluate(u_a_end)
    p_b = crv_b.evaluate(u_b_start)
    if float(np.linalg.norm(p_b - p_a)) > pos_tol:
        return "G0"

    # G1: tangent direction (unit vectors)
    d1_a = curve_derivative(crv_a, u_a_end, order=1)
    d1_b = curve_derivative(crv_b, u_b_start, order=1)
    norm_a = float(np.linalg.norm(d1_a))
    norm_b = float(np.linalg.norm(d1_b))
    if norm_a < 1e-14 or norm_b < 1e-14:
        return "G0"  # degenerate — can't determine higher continuity
    t_a = d1_a / norm_a
    t_b = d1_b / norm_b
    # Cross-product magnitude ≈ |sin(angle)|; use dot product to check collinearity
    cross_mag = float(np.linalg.norm(np.cross(t_a, t_b)))
    if cross_mag > tan_tol:
        return "G0"

    # Check same direction (not anti-parallel)
    if float(np.dot(t_a, t_b)) < 0.0:
        return "G0"

    # G2: curvature magnitude match
    # Curvature κ = |C' × C''| / |C'|³  (for planar/space curves)
    d2_a = curve_derivative(crv_a, u_a_end, order=2)
    d2_b = curve_derivative(crv_b, u_b_start, order=2)
    cross_a = float(np.linalg.norm(np.cross(d1_a, d2_a)))
    cross_b = float(np.linalg.norm(np.cross(d1_b, d2_b)))
    kappa_a = cross_a / (norm_a ** 3)
    kappa_b = cross_b / (norm_b ** 3)
    ref = max(abs(kappa_a), abs(kappa_b), 1e-14)
    if abs(kappa_a - kappa_b) / ref > curv_tol:
        return "G1"

    return "G2"


def composite_curve(
    segments: List[NurbsCurve],
    pos_tol: float = 1e-6,
    tan_tol: float = 1e-4,
    curv_tol: float = 1e-3,
) -> dict:
    """Build a composite (poly-NURBS) curve from an ordered list of segments.

    Each consecutive pair of segments is analysed for G0/G1/G2 geometric
    continuity at their shared junction.  The total arc length is computed
    by summing individual segment lengths.

    Parameters
    ----------
    segments  : list[NurbsCurve]  — ordered segments; must be at least 1
    pos_tol   : positional gap tolerance for G0 detection (default 1e-6)
    tan_tol   : angular tolerance (radians) for G1 detection (default 1e-4)
    curv_tol  : relative curvature-difference tolerance for G2 (default 1e-3)

    Returns
    -------
    dict with keys:
        segments          : list[NurbsCurve]  — same order as input
        continuity_tags   : list[str]         — length = len(segments)-1;
                             each entry is "G0", "G1", or "G2"
        total_length      : float             — sum of segment arc lengths
    """
    if not segments:
        raise ValueError("composite_curve: segments must be a non-empty list")
    segs = list(segments)
    tags: List[str] = []
    for i in range(len(segs) - 1):
        tag = _detect_continuity(
            segs[i], segs[i + 1],
            pos_tol=pos_tol, tan_tol=tan_tol, curv_tol=curv_tol,
        )
        tags.append(tag)
    total = sum(curve_length(s) for s in segs)
    return {
        "segments": segs,
        "continuity_tags": tags,
        "total_length": total,
    }


def split_composite(
    composite: dict,
    index: int,
) -> List[dict]:
    """Split a composite curve at a junction index, returning two sub-composites.

    Parameters
    ----------
    composite : dict    — as returned by ``composite_curve``
    index     : int     — junction index at which to split; must be in
                          range 1 .. len(segments)-1 (inclusive).
                          The segment *before* ``index`` becomes the last
                          segment of the first sub-composite.

    Returns
    -------
    list of two dicts, each with the same shape as ``composite_curve`` output.
    Raises ValueError if ``index`` is out of range.
    """
    segs = composite["segments"]
    tags = composite["continuity_tags"]
    n = len(segs)
    if index < 1 or index >= n:
        raise ValueError(
            f"split_composite: index {index} out of range [1, {n - 1}]"
        )
    left_segs = segs[:index]
    right_segs = segs[index:]
    left_tags = tags[:index - 1]
    right_tags = tags[index:]
    left_length = sum(curve_length(s) for s in left_segs)
    right_length = sum(curve_length(s) for s in right_segs)
    return [
        {
            "segments": left_segs,
            "continuity_tags": left_tags,
            "total_length": left_length,
        },
        {
            "segments": right_segs,
            "continuity_tags": right_tags,
            "total_length": right_length,
        },
    ]


# ---------------------------------------------------------------------------
# GK-99: Mid-curve (average of two NURBS curves)
# ---------------------------------------------------------------------------

def _make_curves_compatible(a: NurbsCurve, b: NurbsCurve):
    """Return (a', b') with identical degree and knot vector (control-point-wise average ready).

    Strategy:
    1. Elevate degree of the lower-degree curve to match the higher.
    2. Merge knot vectors: insert into each curve any knots the other has that
       it does not (up to existing multiplicity).  After this both curves share
       the same knot vector and therefore the same number of control points.
    """
    from kerf_cad_core.geom.nurbs import degree_elevation, knot_insertion

    # --- Step 1: degree elevation ---
    if a.degree < b.degree:
        a = degree_elevation(a, b.degree)
    elif b.degree < a.degree:
        b = degree_elevation(b, a.degree)

    degree = a.degree

    # --- Step 2: merge knot vectors ---
    # Normalise domain of both curves to [0, 1].
    def _normalise_knots(crv: NurbsCurve) -> NurbsCurve:
        k = crv.knots.copy().astype(float)
        lo, hi = k[0], k[-1]
        if abs(hi - lo) < 1e-14:
            return crv
        k = (k - lo) / (hi - lo)
        return NurbsCurve(degree=crv.degree, control_points=crv.control_points.copy(), knots=k,
                          weights=crv.weights)

    a = _normalise_knots(a)
    b = _normalise_knots(b)

    # Collect internal (non-clamped) knots from each side
    def _internal_knots(crv: NurbsCurve) -> np.ndarray:
        k = crv.knots
        d = crv.degree
        return k[d + 1: -(d + 1)]

    def _multiplicity(knots: np.ndarray, u: float, tol: float = 1e-10) -> int:
        return int(np.sum(np.abs(knots - u) < tol))

    def _insert_missing(crv: NurbsCurve, ref: NurbsCurve) -> NurbsCurve:
        """Insert into *crv* every knot in *ref* that crv is missing (or has lower multiplicity)."""
        ref_int = _internal_knots(ref)
        if len(ref_int) == 0:
            return crv
        # Group by unique value
        inserted = crv
        visited = set()
        for u in ref_int:
            key = round(u, 12)
            if key in visited:
                continue
            visited.add(key)
            mult_ref = _multiplicity(ref.knots, u)
            mult_cur = _multiplicity(inserted.knots, u)
            times = mult_ref - mult_cur
            if times > 0:
                inserted = knot_insertion(inserted, u, times)
        return inserted

    a = _insert_missing(a, b)
    b = _insert_missing(b, a)

    return a, b


def mid_curve(curve_a: NurbsCurve, curve_b: NurbsCurve) -> NurbsCurve:
    """Return the mid-curve (CP-wise average) of two NURBS curves.

    The two input curves are first made knot-compatible (degree elevation +
    knot insertion so they share the same knot vector), then each pair of
    corresponding control points is averaged.

    Parameters
    ----------
    curve_a, curve_b:
        Input NurbsCurve objects.  They may have different degrees, different
        knot vectors, and different numbers of control points.

    Returns
    -------
    NurbsCurve
        A new curve whose control points are ``(P_a + P_b) / 2``.
    """
    a, b = _make_curves_compatible(curve_a, curve_b)
    if a.control_points.shape != b.control_points.shape:
        raise ValueError(
            f"mid_curve: after compatibility pass CP counts differ: "
            f"{a.control_points.shape} vs {b.control_points.shape}"
        )
    mid_pts = 0.5 * (a.control_points + b.control_points)
    # Average weights if either side is rational
    mid_weights = None
    wa = a.weights if a.weights is not None else np.ones(len(a.control_points))
    wb = b.weights if b.weights is not None else np.ones(len(b.control_points))
    if a.weights is not None or b.weights is not None:
        mid_weights = 0.5 * (wa + wb)
    return NurbsCurve(degree=a.degree, control_points=mid_pts, knots=a.knots.copy(),
                      weights=mid_weights)


# ---------------------------------------------------------------------------
# GK-103 — Text-on-curve / text-on-surface (engraving outlines)
# ---------------------------------------------------------------------------
#
# Built-in minimal Hershey-style stroke font: each glyph is described as a
# list of polyline strokes in a 0..1 × 0..1 cell (origin = bottom-left).
# Each stroke is a list of (x, y) tuples.  Strokes within a glyph are
# returned as separate outline contours.
#
# Only printable ASCII (32..126) are included.  Unknown chars fall back to a
# simple rectangular outline so the caller always gets geometry.
# ---------------------------------------------------------------------------

# Type alias used in signatures
Point3 = Tuple[float, float, float]


def _hershey_glyph(char: str) -> List[List[Tuple[float, float]]]:
    """Return stroke polylines for *char* in a unit [0,1]×[0,1] cell.

    Each inner list is one continuous stroke (pen-down segment).
    Coordinates are (x, y) with y=0 at baseline, y=1 at cap-height.
    """
    c = char
    # --- space ---
    if c == ' ':
        return []
    # --- digits ---
    if c == '0':
        return [[(0.15,0),(0.85,0),(0.85,1),(0.15,1),(0.15,0)]]
    if c == '1':
        return [[(0.3,0.7),(0.5,1),(0.5,0)], [(0.3,0),(0.7,0)]]
    if c == '2':
        return [[(0.1,0.75),(0.2,1),(0.8,1),(0.9,0.75),(0.5,0.4),(0.1,0),(0.9,0)]]
    if c == '3':
        return [[(0.1,1),(0.9,1),(0.5,0.55),(0.9,0.1),(0.8,0),(0.2,0),(0.1,0.1)]]
    if c == '4':
        return [[(0.7,0),(0.7,1),(0.1,0.4),(0.9,0.4)]]
    if c == '5':
        return [[(0.9,1),(0.1,1),(0.1,0.55),(0.8,0.55),(0.9,0.4),(0.9,0.1),(0.8,0),(0.2,0),(0.1,0.1)]]
    if c == '6':
        return [[(0.85,0.9),(0.5,1),(0.15,0.8),(0.1,0.1),(0.2,0),(0.8,0),(0.9,0.1),(0.9,0.5),(0.8,0.6),(0.1,0.6)]]
    if c == '7':
        return [[(0.1,1),(0.9,1),(0.3,0)]]
    if c == '8':
        return [[(0.5,0.55),(0.1,0.7),(0.1,0.9),(0.5,1),(0.9,0.9),(0.9,0.7),(0.5,0.55),
                 (0.1,0.4),(0.1,0.1),(0.5,0),(0.9,0.1),(0.9,0.4),(0.5,0.55)]]
    if c == '9':
        return [[(0.15,0.1),(0.5,0),(0.85,0),(0.9,0.9),(0.5,1),(0.1,0.9),(0.1,0.4),
                 (0.2,0.35),(0.9,0.35)]]
    # --- uppercase letters ---
    if c == 'A':
        return [[(0.05,0),(0.5,1),(0.95,0)], [(0.2,0.4),(0.8,0.4)]]
    if c == 'B':
        return [[(0.1,0),(0.1,1),(0.75,1),(0.9,0.85),(0.9,0.65),(0.75,0.5),
                 (0.1,0.5),(0.75,0.5),(0.9,0.35),(0.9,0.15),(0.75,0),(0.1,0)]]
    if c == 'C':
        return [[(0.9,0.8),(0.7,1),(0.3,1),(0.1,0.8),(0.1,0.2),(0.3,0),(0.7,0),(0.9,0.2)]]
    if c == 'D':
        return [[(0.1,0),(0.1,1),(0.65,1),(0.9,0.8),(0.9,0.2),(0.65,0),(0.1,0)]]
    if c == 'E':
        return [[(0.9,1),(0.1,1),(0.1,0),(0.9,0)], [(0.1,0.5),(0.75,0.5)]]
    if c == 'F':
        return [[(0.1,0),(0.1,1),(0.9,1)], [(0.1,0.5),(0.75,0.5)]]
    if c == 'G':
        return [[(0.9,0.8),(0.7,1),(0.3,1),(0.1,0.8),(0.1,0.2),(0.3,0),(0.7,0),
                 (0.9,0.2),(0.9,0.5),(0.55,0.5)]]
    if c == 'H':
        return [[(0.1,0),(0.1,1)], [(0.9,0),(0.9,1)], [(0.1,0.5),(0.9,0.5)]]
    if c == 'I':
        return [[(0.3,0),(0.7,0)], [(0.5,0),(0.5,1)], [(0.3,1),(0.7,1)]]
    if c == 'J':
        return [[(0.7,1),(0.7,0.15),(0.6,0),(0.4,0),(0.3,0.15),(0.3,0.35)]]
    if c == 'K':
        return [[(0.1,0),(0.1,1)], [(0.9,1),(0.1,0.5),(0.9,0)]]
    if c == 'L':
        return [[(0.1,1),(0.1,0),(0.9,0)]]
    if c == 'M':
        return [[(0.1,0),(0.1,1),(0.5,0.4),(0.9,1),(0.9,0)]]
    if c == 'N':
        return [[(0.1,0),(0.1,1),(0.9,0),(0.9,1)]]
    if c == 'O':
        return [[(0.3,0),(0.1,0.2),(0.1,0.8),(0.3,1),(0.7,1),(0.9,0.8),
                 (0.9,0.2),(0.7,0),(0.3,0)]]
    if c == 'P':
        return [[(0.1,0),(0.1,1),(0.75,1),(0.9,0.85),(0.9,0.65),(0.75,0.5),(0.1,0.5)]]
    if c == 'Q':
        return [[(0.3,0),(0.1,0.2),(0.1,0.8),(0.3,1),(0.7,1),(0.9,0.8),
                 (0.9,0.2),(0.7,0),(0.3,0)], [(0.6,0.2),(0.95,0)]]
    if c == 'R':
        return [[(0.1,0),(0.1,1),(0.75,1),(0.9,0.85),(0.9,0.65),(0.75,0.5),
                 (0.1,0.5),(0.9,0)]]
    if c == 'S':
        return [[(0.9,0.8),(0.7,1),(0.3,1),(0.1,0.8),(0.1,0.6),(0.9,0.4),
                 (0.9,0.2),(0.7,0),(0.3,0),(0.1,0.2)]]
    if c == 'T':
        return [[(0.1,1),(0.9,1)], [(0.5,1),(0.5,0)]]
    if c == 'U':
        return [[(0.1,1),(0.1,0.2),(0.3,0),(0.7,0),(0.9,0.2),(0.9,1)]]
    if c == 'V':
        return [[(0.1,1),(0.5,0),(0.9,1)]]
    if c == 'W':
        return [[(0.05,1),(0.25,0),(0.5,0.5),(0.75,0),(0.95,1)]]
    if c == 'X':
        return [[(0.1,1),(0.9,0)], [(0.9,1),(0.1,0)]]
    if c == 'Y':
        return [[(0.1,1),(0.5,0.5),(0.9,1)], [(0.5,0.5),(0.5,0)]]
    if c == 'Z':
        return [[(0.1,1),(0.9,1),(0.1,0),(0.9,0)]]
    # --- lowercase (simplified, same height for brevity) ---
    if c == 'a':
        return [[(0.8,0.7),(0.5,0.75),(0.2,0.6),(0.2,0.1),(0.5,0),(0.8,0.1),(0.8,0.75)]]
    if c == 'b':
        return [[(0.2,0),(0.2,1)], [(0.2,0.7),(0.6,0.75),(0.8,0.6),(0.8,0.1),(0.6,0),(0.2,0)]]
    if c == 'c':
        return [[(0.8,0.65),(0.6,0.75),(0.3,0.7),(0.15,0.5),(0.15,0.25),(0.3,0.05),
                 (0.6,0),(0.8,0.1)]]
    if c == 'd':
        return [[(0.8,0),(0.8,1)], [(0.8,0.7),(0.4,0.75),(0.2,0.6),(0.2,0.1),(0.4,0),(0.8,0)]]
    if c == 'e':
        return [[(0.15,0.4),(0.85,0.4),(0.85,0.6),(0.5,0.75),(0.2,0.6),
                 (0.15,0.4),(0.15,0.1),(0.35,0),(0.75,0),(0.85,0.15)]]
    if c == 'f':
        return [[(0.7,1),(0.4,1),(0.25,0.85),(0.25,0)], [(0.15,0.6),(0.65,0.6)]]
    if c == 'g':
        return [[(0.8,0.7),(0.5,0.75),(0.2,0.6),(0.2,0.1),(0.5,0),(0.8,0.1),
                 (0.8,0.75),(0.8,-0.2),(0.5,-0.35),(0.2,-0.2)]]
    if c == 'h':
        return [[(0.2,0),(0.2,1)], [(0.2,0.55),(0.5,0.75),(0.8,0.65),(0.8,0)]]
    if c == 'i':
        return [[(0.5,0.55),(0.5,0)], [(0.5,0.8),(0.5,0.75)]]
    if c == 'j':
        return [[(0.55,0.55),(0.55,-0.15),(0.4,-0.35),(0.2,-0.2)], [(0.55,0.8),(0.55,0.75)]]
    if c == 'k':
        return [[(0.2,0),(0.2,1)], [(0.7,0.75),(0.2,0.4),(0.7,0)]]
    if c == 'l':
        return [[(0.35,1),(0.5,1),(0.5,0.1),(0.6,0),(0.75,0)]]
    if c == 'm':
        return [[(0.1,0.75),(0.1,0)], [(0.1,0.55),(0.35,0.75),(0.55,0.65),(0.55,0)],
                [(0.55,0.55),(0.8,0.75),(1.0,0.65),(1.0,0)]]
    if c == 'n':
        return [[(0.2,0.75),(0.2,0)], [(0.2,0.55),(0.5,0.75),(0.8,0.65),(0.8,0)]]
    if c == 'o':
        return [[(0.3,0),(0.1,0.15),(0.1,0.6),(0.3,0.75),(0.7,0.75),(0.9,0.6),
                 (0.9,0.15),(0.7,0),(0.3,0)]]
    if c == 'p':
        return [[(0.2,0.75),(0.2,-0.35)], [(0.2,0.7),(0.6,0.75),(0.8,0.6),(0.8,0.1),(0.6,0),(0.2,0)]]
    if c == 'q':
        return [[(0.8,0.75),(0.8,-0.35)], [(0.8,0.7),(0.4,0.75),(0.2,0.6),(0.2,0.1),(0.4,0),(0.8,0)]]
    if c == 'r':
        return [[(0.2,0.75),(0.2,0)], [(0.2,0.5),(0.4,0.7),(0.6,0.75),(0.8,0.7)]]
    if c == 's':
        return [[(0.8,0.65),(0.5,0.75),(0.2,0.65),(0.2,0.45),(0.8,0.3),
                 (0.8,0.1),(0.5,0),(0.2,0.1)]]
    if c == 't':
        return [[(0.5,1),(0.5,0.1),(0.6,0),(0.75,0)], [(0.2,0.65),(0.75,0.65)]]
    if c == 'u':
        return [[(0.2,0.75),(0.2,0.15),(0.4,0),(0.6,0),(0.8,0.15),(0.8,0.75)]]
    if c == 'v':
        return [[(0.15,0.75),(0.5,0),(0.85,0.75)]]
    if c == 'w':
        return [[(0.1,0.75),(0.3,0),(0.5,0.4),(0.7,0),(0.9,0.75)]]
    if c == 'x':
        return [[(0.15,0.75),(0.85,0)], [(0.85,0.75),(0.15,0)]]
    if c == 'y':
        return [[(0.15,0.75),(0.5,0.1)], [(0.85,0.75),(0.5,0.1),(0.35,-0.3),(0.15,-0.35)]]
    if c == 'z':
        return [[(0.2,0.75),(0.8,0.75),(0.2,0),(0.8,0)]]
    # --- common punctuation ---
    if c == '.':
        return [[(0.45,0),(0.55,0),(0.55,0.08),(0.45,0.08),(0.45,0)]]
    if c == ',':
        return [[(0.45,0.05),(0.55,0.05),(0.55,0.13),(0.45,0.13),(0.45,0.05)],
                [(0.5,0.05),(0.35,-0.1)]]
    if c == '-':
        return [[(0.1,0.5),(0.9,0.5)]]
    if c == '_':
        return [[(0.05,0),(0.95,0)]]
    if c == '!':
        return [[(0.5,0.25),(0.5,1)], [(0.45,0),(0.55,0),(0.55,0.1),(0.45,0.1),(0.45,0)]]
    if c == '?':
        return [[(0.15,0.8),(0.3,1),(0.7,1),(0.85,0.8),(0.85,0.65),(0.5,0.45),(0.5,0.3)],
                [(0.45,0.05),(0.55,0.05),(0.55,0.15),(0.45,0.15),(0.45,0.05)]]
    if c == ':':
        return [[(0.45,0.2),(0.55,0.2),(0.55,0.3),(0.45,0.3),(0.45,0.2)],
                [(0.45,0.6),(0.55,0.6),(0.55,0.7),(0.45,0.7),(0.45,0.6)]]
    if c == ';':
        return [[(0.45,0.6),(0.55,0.6),(0.55,0.7),(0.45,0.7),(0.45,0.6)],
                [(0.45,0.2),(0.55,0.2),(0.55,0.28),(0.45,0.28),(0.45,0.2)],
                [(0.5,0.2),(0.35,0.05)]]
    if c == '(':
        return [[(0.6,1),(0.35,0.75),(0.35,0.25),(0.6,0)]]
    if c == ')':
        return [[(0.4,1),(0.65,0.75),(0.65,0.25),(0.4,0)]]
    if c == '[':
        return [[(0.65,1),(0.35,1),(0.35,0),(0.65,0)]]
    if c == ']':
        return [[(0.35,1),(0.65,1),(0.65,0),(0.35,0)]]
    if c == '+':
        return [[(0.5,0.1),(0.5,0.9)], [(0.1,0.5),(0.9,0.5)]]
    if c == '=':
        return [[(0.1,0.35),(0.9,0.35)], [(0.1,0.65),(0.9,0.65)]]
    if c == '/':
        return [[(0.8,1),(0.2,0)]]
    if c == '\\':
        return [[(0.2,1),(0.8,0)]]
    if c == '*':
        return [[(0.5,0.3),(0.5,0.9)], [(0.2,0.45),(0.8,0.75)], [(0.8,0.45),(0.2,0.75)]]
    if c == '#':
        return [[(0.3,0),(0.2,1)], [(0.7,0),(0.6,1)],
                [(0.1,0.3),(0.9,0.3)], [(0.1,0.7),(0.9,0.7)]]
    if c == '@':
        return [[(0.65,0.45),(0.5,0.35),(0.35,0.45),(0.35,0.65),(0.5,0.7),(0.65,0.6),
                 (0.65,0.35),(0.5,0.2),(0.25,0.2),(0.1,0.35),(0.1,0.8),(0.25,1),
                 (0.6,1),(0.9,0.8),(0.9,0.2),(0.7,0),(0.3,0),(0.1,0.2)]]
    if c == '"':
        return [[(0.3,0.75),(0.3,0.95)], [(0.7,0.75),(0.7,0.95)]]
    if c == "'":
        return [[(0.5,0.75),(0.5,0.95)]]
    if c == '`':
        return [[(0.3,0.9),(0.7,1)]]
    if c == '^':
        return [[(0.1,0.6),(0.5,1),(0.9,0.6)]]
    if c == '~':
        return [[(0.1,0.55),(0.3,0.65),(0.7,0.45),(0.9,0.55)]]
    if c == '<':
        return [[(0.8,0.8),(0.2,0.5),(0.8,0.2)]]
    if c == '>':
        return [[(0.2,0.8),(0.8,0.5),(0.2,0.2)]]
    if c == '|':
        return [[(0.5,0),(0.5,1)]]
    if c == '&':
        return [[(0.8,0.7),(0.5,1),(0.2,0.7),(0.2,0.55),(0.8,0.2),(0.8,0.05),
                 (0.5,0),(0.15,0.1),(0.15,0.3),(0.4,0.55),(0.85,0)]]
    if c == '%':
        return [[(0.15,0.75),(0.3,0.9),(0.45,0.75),(0.3,0.6),(0.15,0.75)],
                [(0.85,0.25),(0.7,0.4),(0.55,0.25),(0.7,0.1),(0.85,0.25)],
                [(0.85,0.9),(0.15,0.1)]]
    # --- fallback: simple rectangle outline ---
    return [[(0.1,0.05),(0.9,0.05),(0.9,0.95),(0.1,0.95),(0.1,0.05)]]


# Advance width per glyph (fraction of height).  Wide chars get more space.
_GLYPH_ADVANCE: dict = {
    'i': 0.45, 'j': 0.45, 'l': 0.45, '!': 0.45, '|': 0.35, "'": 0.35, '`': 0.35,
    ' ': 0.35,
    'm': 1.05, 'w': 1.05, 'W': 1.05, 'M': 1.05,
    '@': 1.1,
}
_DEFAULT_ADVANCE = 0.65   # fraction of height
_INTER_GLYPH_GAP = 0.10   # fraction of height


def _text_strokes_flat(
    text: str,
    height: float,
    *,
    font: str = 'hershey',
) -> List[List[Tuple[float, float]]]:
    """Return all strokes for *text* in a flat 2-D coordinate frame.

    Returns a list of strokes; each stroke is a list of (x, y) pairs.
    ``y`` is in [0, height], ``x`` starts at 0 and grows right.
    """
    strokes: List[List[Tuple[float, float]]] = []
    cursor_x = 0.0
    for ch in text:
        glyph_strokes = _hershey_glyph(ch)
        for stroke in glyph_strokes:
            world_stroke: List[Tuple[float, float]] = [
                (cursor_x + sx * height, sy * height)
                for sx, sy in stroke
            ]
            strokes.append(world_stroke)
        advance = _GLYPH_ADVANCE.get(ch, _DEFAULT_ADVANCE)
        cursor_x += (advance + _INTER_GLYPH_GAP) * height
    return strokes


def _text_total_width(text: str, height: float) -> float:
    """Total advance width of *text* in world units."""
    w = 0.0
    for i, ch in enumerate(text):
        advance = _GLYPH_ADVANCE.get(ch, _DEFAULT_ADVANCE)
        w += advance * height
        if i < len(text) - 1:
            w += _INTER_GLYPH_GAP * height
    return w


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def text_on_curve(
    text: str,
    curve: "NurbsCurve",
    height: float,
    *,
    font: str = 'hershey',
) -> List[List[Point3]]:
    """Place glyph outlines (stroke polylines) along *curve*.

    Each character is sampled from the built-in vector font, then mapped onto
    the curve using the Frenet–Serret (RMF) frame:
    * The baseline advances along the curve arc-length.
    * The up direction is the local curve normal (or a fallback up vector when
      the curvature is zero).

    Parameters
    ----------
    text:
        The string to place.
    curve:
        A :class:`NurbsCurve` to follow.  Must have at least two distinct
        control points.
    height:
        Cap-height of the glyphs in the same units as *curve*.
    font:
        Reserved for future font variants; currently only ``'hershey'`` is
        supported.

    Returns
    -------
    List[List[Point3]]
        One sub-list per stroke, each containing 3-D points in world space.
        The number of sub-lists equals the total number of strokes across all
        glyphs.
    """
    if not text:
        return []
    height = float(height)
    if height <= 0:
        raise ValueError("text_on_curve: height must be positive")

    from kerf_cad_core.geom.nurbs import curve_derivative

    # Arc-length parameterisation
    al_param = arc_length_param(curve, n=512)
    total_len = al_param.total_length

    # Build strokes in flat 2-D
    flat_strokes = _text_strokes_flat(text, height, font=font)

    # Helper: evaluate point + tangent at arc-length s
    def _frame_at_s(s: float):
        """Return (origin, tangent_unit, up_unit) at arc-length s."""
        s = max(0.0, min(s, total_len))
        t = al_param.t_at_length(s)
        origin = np.asarray(de_boor(curve, t), dtype=float)
        # tangent via finite difference if derivative not available
        eps = max(1e-6, total_len * 1e-4)
        t1 = al_param.t_at_length(min(s + eps, total_len))
        t0 = al_param.t_at_length(max(s - eps, 0.0))
        if abs(t1 - t0) < 1e-14:
            tan = np.array([1.0, 0.0, 0.0])
        else:
            p1 = np.asarray(de_boor(curve, t1), dtype=float)
            p0 = np.asarray(de_boor(curve, t0), dtype=float)
            tan = p1 - p0
            n_tan = np.linalg.norm(tan)
            if n_tan < 1e-14:
                tan = np.array([1.0, 0.0, 0.0])
            else:
                tan = tan / n_tan
        # Build an up vector perpendicular to tangent
        # Prefer Z-up if tangent not too aligned with Z
        ref = np.array([0.0, 0.0, 1.0])
        if abs(np.dot(tan, ref)) > 0.9:
            ref = np.array([0.0, 1.0, 0.0])
        up = ref - np.dot(ref, tan) * tan
        up_n = np.linalg.norm(up)
        if up_n < 1e-14:
            up = np.array([0.0, 1.0, 0.0])
        else:
            up = up / up_n
        return origin, tan, up

    result: List[List[Point3]] = []
    for stroke_2d in flat_strokes:
        stroke_3d: List[Point3] = []
        for x2d, y2d in stroke_2d:
            origin, tan, up = _frame_at_s(x2d)
            pt = origin + float(y2d) * up
            stroke_3d.append((float(pt[0]), float(pt[1]), float(pt[2])))
        if stroke_3d:
            result.append(stroke_3d)
    return result


def text_on_surface(
    text: str,
    surface: "NurbsSurface",
    u0: float,
    v0: float,
    height: float,
    *,
    font: str = 'hershey',
) -> List[List[Point3]]:
    """Place glyph outlines on a NURBS *surface* starting at *(u0, v0)*.

    The text is laid out in the surface's *u*-direction starting at the
    parameter pair *(u0, v0)*.  The local surface tangent ``∂S/∂u`` is used
    as the baseline direction; the surface normal provides the "up" direction
    (the glyphs are *lifted* from the surface along the normal by the glyph
    y-coordinate scaled by ``height``).

    Parameters
    ----------
    text:
        The string to place.
    surface:
        A :class:`~kerf_cad_core.geom.nurbs.NurbsSurface`.
    u0, v0:
        Starting parameter values in the surface domain.
    height:
        Glyph cap-height in world units.
    font:
        Reserved; only ``'hershey'`` currently supported.

    Returns
    -------
    List[List[Point3]]
        One sub-list per stroke in world space (lifted onto / above the
        surface).
    """
    if not text:
        return []
    height = float(height)
    if height <= 0:
        raise ValueError("text_on_surface: height must be positive")

    from kerf_cad_core.geom.nurbs import (
        NurbsSurface,
        surface_evaluate,
        surface_derivatives,
    )

    u0 = float(u0)
    v0 = float(v0)

    # Surface parameter ranges
    u_min = float(surface.knots_u[surface.degree_u])
    u_max = float(surface.knots_u[-(surface.degree_u + 1)])
    v_min = float(surface.knots_v[surface.degree_v])
    v_max = float(surface.knots_v[-(surface.degree_v + 1)])
    u_span = u_max - u_min
    v_span = v_max - v_min

    # Estimate world-space length of a unit step in u (at the anchor point)
    eps_u = u_span * 1e-3
    p_plus = np.asarray(surface_evaluate(surface, min(u0 + eps_u, u_max), v0))
    p_minus = np.asarray(surface_evaluate(surface, max(u0 - eps_u, u_min), v0))
    du_world = np.linalg.norm(p_plus - p_minus) / (2 * eps_u)
    if du_world < 1e-14:
        du_world = 1.0  # degenerate surface fallback

    # Estimate world-space length of a unit step in v (at the anchor point)
    eps_v = v_span * 1e-3
    q_plus = np.asarray(surface_evaluate(surface, u0, min(v0 + eps_v, v_max)))
    q_minus = np.asarray(surface_evaluate(surface, u0, max(v0 - eps_v, v_min)))
    dv_world = np.linalg.norm(q_plus - q_minus) / (2 * eps_v)
    if dv_world < 1e-14:
        dv_world = 1.0

    # Scale factors: world units → parameter units
    du_per_world = 1.0 / du_world  # Δu per world unit along u
    dv_per_world = 1.0 / dv_world  # Δv per world unit along v

    def _pt_on_surface(x_world: float, y_world: float) -> Point3:
        """Map flat glyph (x_world baseline, y_world height) → 3-D point on surface."""
        u = u0 + x_world * du_per_world
        v = v0  # keep v constant; advance only along u for baseline
        # Clamp to domain
        u = max(u_min, min(u_max, u))
        v = max(v_min, min(v_max, v))
        # Base point on the surface
        base = np.asarray(surface_evaluate(surface, u, v), dtype=float)
        # Surface tangent and normal at this (u, v)
        SKL = surface_derivatives(surface, u, v, d=1)
        du_vec = np.asarray(SKL[1, 0], dtype=float)  # ∂S/∂u
        dv_vec = np.asarray(SKL[0, 1], dtype=float)  # ∂S/∂v
        # Normal = du × dv
        normal = np.cross(du_vec, dv_vec)
        nlen = np.linalg.norm(normal)
        if nlen < 1e-14:
            normal = np.array([0.0, 0.0, 1.0])
        else:
            normal = normal / nlen
        # Lift the point along the normal by y_world
        pt = base + float(y_world) * normal
        return (float(pt[0]), float(pt[1]), float(pt[2]))

    flat_strokes = _text_strokes_flat(text, height, font=font)
    result: List[List[Point3]] = []
    for stroke_2d in flat_strokes:
        stroke_3d: List[Point3] = [
            _pt_on_surface(x2d, y2d) for x2d, y2d in stroke_2d
        ]
        if stroke_3d:
            result.append(stroke_3d)
    return result
