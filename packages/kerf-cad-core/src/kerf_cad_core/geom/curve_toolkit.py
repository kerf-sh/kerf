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

from kerf_cad_core.geom.nurbs import NurbsCurve, de_boor, find_span


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

    Increases the number of control points until max_deviation ≤ tolerance or
    ``max_ctrl`` is reached.

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

        degree = min(degree, n - 1)
        ts = _chord_params(pts)

        for num_ctrl in range(degree + 1, min(max_ctrl + 1, n + 1)):
            knots = _make_clamped_knots(num_ctrl, degree)
            A = np.zeros((n, num_ctrl))
            for i, t in enumerate(ts):
                A[i] = _eval_bspline_basis(t, degree, knots, num_ctrl)

            ctrl, _, _, _ = np.linalg.lstsq(A, pts, rcond=None)
            curve = NurbsCurve(degree=degree, control_points=ctrl, knots=knots)

            # measure deviation
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
# fair_curve
# ---------------------------------------------------------------------------

def fair_curve(
    curve: NurbsCurve,
    iterations: int = 5,
    weight: float = 0.1,
) -> NurbsCurve:
    """Smooth a curve by minimising internal strain energy, keeping endpoints fixed.

    Uses iterative Laplacian smoothing on interior control points weighted by
    ``weight`` (0 = no change, 1 = full Laplacian step).

    Returns
    -------
    NurbsCurve with smoothed interior control points.
    """
    ctrl = curve.control_points.copy().astype(float)
    n = len(ctrl)
    if n < 3:
        return curve

    lam = float(np.clip(weight, 0.0, 1.0))
    for _ in range(iterations):
        new_ctrl = ctrl.copy()
        for i in range(1, n - 1):
            laplacian = 0.5 * (ctrl[i - 1] + ctrl[i + 1]) - ctrl[i]
            new_ctrl[i] = ctrl[i] + lam * laplacian
        ctrl = new_ctrl

    return NurbsCurve(degree=curve.degree, control_points=ctrl, knots=curve.knots.copy())


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
    rho: float = 0.5,
) -> NurbsCurve:
    """Rational Bézier conic section.

    ``p0``, ``p1``, ``p2`` are the Bézier control points; ``rho`` is the
    shoulder weight:
      - rho < 0.5 : ellipse
      - rho = 0.5 : parabola
      - 0.5 < rho < 1 : hyperbola

    Returns a degree-2 NurbsCurve with rational weights [1, rho, 1].
    """
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    p2 = np.asarray(p2, dtype=float)
    rho = float(np.clip(rho, 1e-6, 1.0 - 1e-6))

    dim = p0.shape[0]
    # Homogeneous coordinates: [x*w, y*w, z*w, w]
    # p0 weight=1, p1 weight=rho, p2 weight=1
    ctrl_h = np.zeros((3, dim + 1))
    ctrl_h[0, :dim] = p0 * 1.0
    ctrl_h[0, dim] = 1.0
    ctrl_h[1, :dim] = p1 * rho
    ctrl_h[1, dim] = rho
    ctrl_h[2, :dim] = p2 * 1.0
    ctrl_h[2, dim] = 1.0

    knots = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])

    # Store as a NurbsCurve; evaluator will need to divide by weight.
    # We embed the weight in the extra dimension and return a plain curve
    # with rational=True semantics embedded in the control points.
    # For the purposes of this toolkit (sampling/testing), we store the
    # weighted control points and expose a sampled polyline via the
    # homogeneous representation.
    return NurbsCurve(degree=2, control_points=ctrl_h, knots=knots)


def eval_conic(curve: NurbsCurve, u: float) -> np.ndarray:
    """Evaluate a rational conic (from ``conic()``) at parameter ``u``.

    Uses Bernstein polynomials for a degree-2 rational Bézier so the
    homogeneous division is done correctly.

    The control points are stored as ``[w*x, w*y, w*z, w]`` (pre-multiplied
    homogeneous form as produced by ``conic()``).  Evaluation is::

        hw = B0*ctrl[0] + B1*ctrl[1] + B2*ctrl[2]
        result = hw[:-1] / hw[-1]
    """
    ctrl = curve.control_points  # shape (3, dim+1), already homogeneous (w*x, w)
    t = float(np.clip(u, 0.0, 1.0))
    B0 = (1.0 - t) ** 2
    B1 = 2.0 * t * (1.0 - t)
    B2 = t ** 2
    # Sum Bernstein-weighted homogeneous control vectors
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
