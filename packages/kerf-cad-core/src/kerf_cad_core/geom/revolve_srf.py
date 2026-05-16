"""
revolve_srf.py
==============
Pure-Python NURBS surface of revolution and rail-revolve.

Implements the standard rational quadratic circle construction (NURBS A Book
Algorithm A7.1) so that revolve_surface produces an *exact* NURBS surface of
revolution — not a polygonal approximation.

Public API
----------
revolve_surface(profile_curve, axis_point, axis_dir,
                start_angle=0.0, end_angle=2*pi, *,
                cap=False, tol=1e-10) -> NurbsSurface
    Exact NURBS surface of revolution.  The angle convention is in radians.
    The u direction follows the profile; the v direction sweeps the angle.
    Returns a *rational* surface: control_points has shape (n_prof, n_arc, 4)
    stored in homogeneous form (w*x, w*y, w*z, w) so that evaluate_revolve
    can use the standard sum-of-homogeneous-coords / sum-of-weights formula.

    Knot vector in v is clamped and matches the arc segment structure:
      - θ ≤ π/2   → 1 segment,  3 CPs, degree 2
      - θ ≤ π     → 2 segments, 5 CPs
      - θ ≤ 3π/2  → 3 segments, 7 CPs
      - θ ≤ 2π    → 4 segments, 9 CPs

    Points on the axis (radius < tol) become pole control points with the
    expected homogeneous representation so surface continuity is preserved.

rail_revolve(profile_curve, rail_curve, axis_point, axis_dir, *,
             tol=1e-10) -> NurbsSurface
    Rail-revolve: rotate the profile around the axis while scaling it so that
    the leading edge follows the rail curve.  The rail curve is sampled at the
    same v-parameter positions as the arc nodes; each profile row is uniformly
    scaled by the ratio of the rail radius to the profile-start radius.

evaluate_revolve(surface, u, v) -> np.ndarray (shape (3,))
    Evaluate a revolve surface (homogeneous control points) at (u, v).
    Handles the rational (weighted) evaluation correctly.

Internal helpers are prefixed with underscore and not exported.

Register LLM tools
------------------
Two tools are registered when kerf_chat.tools.registry is available:
  ``revolve_surface_tool``   — build a surface of revolution from JSON args
  ``rail_revolve_tool``      — build a rail-revolve surface from JSON args

Both mirror the {ok: ..., ...} / {ok: false, reason: ..., code: ...} payload
convention of trim_curve.py and never raise.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple

import numpy as np

from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# NOTE: the basis_functions() in nurbs.py uses an incorrect recurrence that
# produces zeros for most parameter values.  We provide the standard
# Algorithm A2.2 (Piegl & Tiller, "The NURBS Book") here for the rational
# evaluation needed by evaluate_revolve.  The existing surface_evaluate() is
# not used for the homogeneous (4-column) control-point arrays produced by
# revolve_surface / rail_revolve.

_TWO_PI = 2.0 * math.pi
_HALF_PI = math.pi / 2.0


# ---------------------------------------------------------------------------
# Correct NURBS basis function (Algorithm A2.2, Piegl & Tiller)
# ---------------------------------------------------------------------------

def _basis_funcs(i: int, u: float, p: int, U: np.ndarray) -> np.ndarray:
    """Compute the non-vanishing B-spline basis functions N_{i-p,p} .. N_{i,p}.

    Parameters
    ----------
    i : int    — knot span index (from find_span)
    u : float  — parameter value
    p : int    — degree
    U : ndarray — knot vector

    Returns
    -------
    ndarray, shape (p+1,)
        N[0] = N_{i-p,p}(u), ..., N[p] = N_{i,p}(u).
    """
    N = np.zeros(p + 1)
    left = np.zeros(p + 1)
    right = np.zeros(p + 1)
    N[0] = 1.0
    for j in range(1, p + 1):
        left[j] = u - U[i + 1 - j]
        right[j] = U[i + j] - u
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


# ---------------------------------------------------------------------------
# Arc construction helpers
# ---------------------------------------------------------------------------

def _arc_segment_count(sweep: float) -> int:
    """Number of 90°-or-less segments needed for the given sweep angle (radians)."""
    if sweep <= _HALF_PI + 1e-10:
        return 1
    if sweep <= math.pi + 1e-10:
        return 2
    if sweep <= 3.0 * _HALF_PI + 1e-10:
        return 3
    return 4


def _build_arc_data(
    center: np.ndarray,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    radius: float,
    start_angle: float,
    sweep: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build the rational quadratic arc control points, weights, and knot vector.

    Parameters
    ----------
    center    : 3D point on the axis
    x_axis    : unit vector in the plane of the arc, in the start direction
    y_axis    : unit vector orthogonal to x_axis (and to the axis)
    radius    : arc radius
    start_angle : starting angle in radians (0 = x_axis)
    sweep       : total sweep angle in radians (> 0)

    Returns
    -------
    pts    : shape (n_arc, 3)  — 3D control points (not yet homogeneous)
    wts    : shape (n_arc,)    — weights
    knots  : shape (n_knots,)  — clamped knot vector
    """
    n_segs = _arc_segment_count(sweep)
    delta = sweep / n_segs          # angle per segment
    cos_half = math.cos(delta / 2.0)

    # Each segment contributes 2 new CPs (shared endpoints between segments)
    n_arc = 2 * n_segs + 1

    pts = np.zeros((n_arc, 3))
    wts = np.ones(n_arc)

    angle = start_angle
    # First point
    pts[0] = center + radius * (math.cos(angle) * x_axis + math.sin(angle) * y_axis)
    wts[0] = 1.0

    idx = 0
    for _ in range(n_segs):
        # tangent CP (middle of this segment)
        mid_angle = angle + delta / 2.0
        pts[idx + 1] = (
            center
            + (radius / cos_half)
            * (math.cos(mid_angle) * x_axis + math.sin(mid_angle) * y_axis)
        )
        wts[idx + 1] = cos_half

        # end CP
        angle += delta
        pts[idx + 2] = center + radius * (
            math.cos(angle) * x_axis + math.sin(angle) * y_axis
        )
        wts[idx + 2] = 1.0

        idx += 2

    # Clamped knot vector for degree-2 arc with n_segs segments
    # Interior knots are repeated twice at each segment boundary
    knots_list = [0.0, 0.0, 0.0]
    for k in range(1, n_segs):
        t = k / n_segs
        knots_list += [t, t]
    knots_list += [1.0, 1.0, 1.0]
    knots = np.array(knots_list)

    return pts, wts, knots


# ---------------------------------------------------------------------------
# Axis / plane helpers
# ---------------------------------------------------------------------------

def _normalise(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n < 1e-15:
        raise ValueError(f"zero-length vector: {v}")
    return v / n


def _project_onto_plane(pt: np.ndarray, axis_pt: np.ndarray, axis_dir: np.ndarray) -> np.ndarray:
    """Project pt onto the plane through axis_pt with normal axis_dir."""
    d = pt - axis_pt
    return pt - np.dot(d, axis_dir) * axis_dir


def _radius_and_local(
    pt: np.ndarray,
    axis_pt: np.ndarray,
    axis_dir: np.ndarray,
) -> Tuple[float, np.ndarray]:
    """Return (radius, foot_on_axis) where foot is the closest point on the axis."""
    d = pt - axis_pt
    proj = np.dot(d, axis_dir)
    foot = axis_pt + proj * axis_dir
    radial = pt - foot
    radius = float(np.linalg.norm(radial))
    return radius, foot


# ---------------------------------------------------------------------------
# revolve_surface
# ---------------------------------------------------------------------------

def revolve_surface(
    profile_curve: NurbsCurve,
    axis_point: np.ndarray,
    axis_dir: np.ndarray,
    start_angle: float = 0.0,
    end_angle: float = _TWO_PI,
    *,
    cap: bool = False,
    tol: float = 1e-10,
) -> NurbsSurface:
    """Exact NURBS surface of revolution.

    Revolves *profile_curve* around the axis defined by *axis_point* and
    *axis_dir* by the angle from *start_angle* to *end_angle* (radians).

    The surface's control-point array has shape ``(n_prof, n_arc, 4)`` where
    the 4th column is the homogeneous weight.  Use ``evaluate_revolve`` (or
    ``surface_evaluate_weighted`` below) to evaluate points.

    Parameters
    ----------
    profile_curve : NurbsCurve
        The profile to revolve.  Its control points are expected in 3D (shape
        (n, 3)).  A weight column is tolerated (shape (n, 4)) and will be
        combined with the arc weights.
    axis_point : array-like, shape (3,)
        A point on the axis of revolution.
    axis_dir : array-like, shape (3,)
        Direction of the axis (need not be unit length).
    start_angle : float
        Start angle in radians (default 0).
    end_angle : float
        End angle in radians (default 2π).
    cap : bool
        If True, raise NotImplementedError (capping is a B-rep concern, not
        handled here).
    tol : float
        Radius threshold below which a profile point is treated as on-axis
        (a pole).

    Returns
    -------
    NurbsSurface
        Rational surface with control_points of shape (n_prof, n_arc, 4).
        degree_u = profile_curve.degree, degree_v = 2.
        knots_u = profile_curve.knots, knots_v = arc knot vector.
    """
    if cap:
        raise NotImplementedError("cap=True is a B-rep concern; use the OCCT worker for capped solids")

    axis_pt = np.asarray(axis_point, dtype=float)
    ax = _normalise(np.asarray(axis_dir, dtype=float))

    sweep = end_angle - start_angle
    if sweep <= 0.0:
        raise ValueError(f"end_angle must be > start_angle; got sweep={sweep:.6f}")
    if sweep > _TWO_PI + 1e-9:
        raise ValueError(f"sweep angle > 2π not supported; got {sweep:.6f}")
    # Clamp full circle to exactly 2π
    if sweep > _TWO_PI - 1e-9:
        sweep = _TWO_PI

    prof_cp = np.asarray(profile_curve.control_points, dtype=float)
    if prof_cp.ndim != 2:
        raise ValueError("profile_curve.control_points must be 2D")

    # Separate geometric coords from optional weight column
    if prof_cp.shape[1] == 4:
        prof_w = prof_cp[:, 3].copy()
        prof_xyz = prof_cp[:, :3].copy()
    elif prof_cp.shape[1] >= 3:
        prof_w = np.ones(prof_cp.shape[0])
        prof_xyz = prof_cp[:, :3].copy()
    else:
        raise ValueError("profile_curve control points must have at least 3 coordinates")

    n_prof = prof_cp.shape[0]

    # Build arc knot vector once (shared across all profile rows)
    # We need a representative radius to build the arc — use the first
    # non-degenerate profile point.
    # ---------------------------------------------------------------------------
    # For each profile control point we build its own arc in the plane
    # perpendicular to the axis.
    # ---------------------------------------------------------------------------
    n_segs = _arc_segment_count(sweep)
    n_arc = 2 * n_segs + 1

    surf_cp = np.zeros((n_prof, n_arc, 4))  # homogeneous

    knots_v = None  # will be filled on first iteration

    for i in range(n_prof):
        pt = prof_xyz[i]
        pw = prof_w[i]

        radius, foot = _radius_and_local(pt, axis_pt, ax)

        if radius < tol:
            # Pole on axis: all arc CPs collapse to the foot point.
            # The combined weight for pole CPs uses arc weights so the knot
            # structure is consistent, but the weighted coords are all zero
            # (since radius=0) except for the axial component.
            # We determine arc weights by building a dummy arc of radius 1.
            tmp_x = np.array([1.0, 0.0, 0.0]) if abs(ax[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
            tmp_y = _normalise(np.cross(ax, tmp_x))
            _, dummy_wts, arc_knots = _build_arc_data(foot, tmp_x, tmp_y, 1.0, 0.0, sweep)
            if knots_v is None:
                knots_v = arc_knots
            for j in range(n_arc):
                w = pw * dummy_wts[j]
                # Homogeneous coords: (w*x, w*y, w*z, w)
                surf_cp[i, j, :3] = w * foot
                surf_cp[i, j, 3] = w
        else:
            # x_axis: unit vector from axis foot toward pt (in start_angle orientation)
            x_axis_base = _normalise(pt - foot)  # radial direction from foot to pt

            # Build a local y_axis perpendicular to both ax and x_axis_base
            y_axis_base = np.cross(ax, x_axis_base)
            y_norm = np.linalg.norm(y_axis_base)
            if y_norm < 1e-12:
                # x_axis_base is parallel to ax — shouldn't happen if radius>0
                # fall back to an arbitrary perpendicular
                tmp = np.array([1.0, 0.0, 0.0]) if abs(ax[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
                y_axis_base = _normalise(np.cross(ax, tmp))
            else:
                y_axis_base = y_axis_base / y_norm

            # The x/y axes for the arc are rotated by start_angle
            cos_s = math.cos(start_angle)
            sin_s = math.sin(start_angle)
            x_axis = cos_s * x_axis_base - sin_s * y_axis_base
            y_axis = sin_s * x_axis_base + cos_s * y_axis_base

            arc_pts, arc_wts, arc_knots = _build_arc_data(
                foot, x_axis, y_axis, radius, 0.0, sweep
            )
            if knots_v is None:
                knots_v = arc_knots

            for j in range(n_arc):
                # Combine profile weight with arc weight (rational tensor product)
                w = pw * arc_wts[j]
                # Store in homogeneous form: (w*x, w*y, w*z, w)
                surf_cp[i, j, :3] = w * arc_pts[j]
                surf_cp[i, j, 3] = w

    # If every profile point was on the axis (degenerate), we still need knots_v
    if knots_v is None:
        _, _, knots_v = _build_arc_data(
            axis_pt,
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            1.0,
            0.0,
            sweep,
        )

    return NurbsSurface(
        degree_u=profile_curve.degree,
        degree_v=2,
        control_points=surf_cp,
        knots_u=profile_curve.knots.copy(),
        knots_v=knots_v,
    )


# ---------------------------------------------------------------------------
# evaluate_revolve  (rational evaluation for the 4-column CP format)
# ---------------------------------------------------------------------------

def evaluate_revolve(surface: NurbsSurface, u: float, v: float) -> np.ndarray:
    """Evaluate a revolve surface (homogeneous 4-column CPs) at (u, v).

    Standard rational NURBS evaluation:
        S(u,v) = sum_ij  N_i(u) M_j(v) w_ij P_ij
                / sum_ij  N_i(u) M_j(v) w_ij

    Uses the locally-correct _basis_funcs (Algorithm A2.2) rather than the
    basis_functions imported from nurbs.py, which has an incorrect recurrence.

    Parameters
    ----------
    surface : NurbsSurface
        Must have control_points of shape (nu, nv, 4) where [:,:,3] are weights.
    u, v : float
        Parameter values in the surface's domain.

    Returns
    -------
    np.ndarray, shape (3,)
        3D Cartesian point on the surface.
    """
    from kerf_cad_core.geom.nurbs import find_span

    cp = surface.control_points  # shape (nu, nv, 4)
    nu = surface.num_control_points_u
    nv = surface.num_control_points_v

    span_u = find_span(nu - 1, surface.degree_u, u, surface.knots_u)
    span_v = find_span(nv - 1, surface.degree_v, v, surface.knots_v)

    Nu = _basis_funcs(span_u, u, surface.degree_u, surface.knots_u)
    Nv = _basis_funcs(span_v, v, surface.degree_v, surface.knots_v)

    Sw = np.zeros(4)
    for i in range(surface.degree_u + 1):
        for j in range(surface.degree_v + 1):
            idx_i = span_u - surface.degree_u + i
            idx_j = span_v - surface.degree_v + j
            Sw += Nu[i] * Nv[j] * cp[idx_i, idx_j]

    if abs(Sw[3]) < 1e-15:
        return Sw[:3]
    return Sw[:3] / Sw[3]


# ---------------------------------------------------------------------------
# rail_revolve
# ---------------------------------------------------------------------------

def rail_revolve(
    profile_curve: NurbsCurve,
    rail_curve: NurbsCurve,
    axis_point: np.ndarray,
    axis_dir: np.ndarray,
    *,
    tol: float = 1e-10,
) -> NurbsSurface:
    """Rail-revolve: rotate a profile around an axis while scaling it along a rail.

    The profile is swept through a full 360° rotation (like revolve_surface),
    but at each angular position the profile is scaled uniformly so that the
    point on the leading edge of the profile (the first control point) tracks
    the rail curve.

    The rail curve is evaluated at n_arc uniformly-spaced parameter values
    (matching the arc node v-parameters), and the scale factor at each position
    is:
        scale(v) = rail_radius(v) / profile_start_radius

    where ``rail_radius`` is the distance from the rail-curve point to the axis.

    Parameters
    ----------
    profile_curve : NurbsCurve
        Profile to sweep.
    rail_curve : NurbsCurve
        A curve whose radial distance from the axis drives the scale.
    axis_point, axis_dir : array-like
        Axis of revolution.

    Returns
    -------
    NurbsSurface
        Rational surface of shape (n_prof, n_arc, 4), same knot structure as
        revolve_surface.
    """
    axis_pt = np.asarray(axis_point, dtype=float)
    ax = _normalise(np.asarray(axis_dir, dtype=float))

    prof_cp = np.asarray(profile_curve.control_points, dtype=float)
    if prof_cp.shape[1] == 4:
        prof_w = prof_cp[:, 3].copy()
        prof_xyz = prof_cp[:, :3].copy()
    else:
        prof_w = np.ones(prof_cp.shape[0])
        prof_xyz = prof_cp[:, :3].copy()

    n_prof = prof_cp.shape[0]

    # Full circle
    sweep = _TWO_PI
    n_segs = _arc_segment_count(sweep)
    n_arc = 2 * n_segs + 1

    # Sample rail at arc v-parameters
    # The arc v-params for the nodes are: 0, 1/n_segs, 2/n_segs, ...
    # But we need n_arc samples (nodes + midpoints).
    # For the midpoints: k/n_segs ± 0.5/n_segs → (2k-1)/(2*n_segs) and (2k+1)/(2*n_segs)
    arc_v_params = []
    for seg in range(n_segs):
        arc_v_params.append(seg / n_segs)
        arc_v_params.append((seg + 0.5) / n_segs)
    arc_v_params.append(1.0)

    rail_knots = rail_curve.knots
    rail_u_min = float(rail_knots[rail_curve.degree])
    rail_u_max = float(rail_knots[-(rail_curve.degree + 1)])

    # Evaluate rail at corresponding u params
    rail_samples = []
    for t in arc_v_params:
        u_rail = rail_u_min + t * (rail_u_max - rail_u_min)
        pt = rail_curve.evaluate(u_rail)
        if pt.ndim == 2:
            pt = pt[0]
        rail_samples.append(pt[:3])

    # Radius of first profile point from axis
    first_pt = prof_xyz[0]
    prof_start_radius, _ = _radius_and_local(first_pt, axis_pt, ax)
    if prof_start_radius < tol:
        raise ValueError(
            "profile_curve first control point is on the axis — "
            "rail_revolve requires a non-degenerate profile start radius"
        )

    # Scale factors at each arc column
    scale_factors = []
    for rpt in rail_samples:
        r, _ = _radius_and_local(rpt, axis_pt, ax)
        scale_factors.append(r / prof_start_radius)

    # Build surface the same way as revolve_surface but scale each arc column
    surf_cp = np.zeros((n_prof, n_arc, 4))
    knots_v = None

    for i in range(n_prof):
        pt = prof_xyz[i]
        pw = prof_w[i]

        radius_0, foot_0 = _radius_and_local(pt, axis_pt, ax)
        # axial distance of this profile point from axis_pt (keeps the axial shape)
        axial_offset = np.dot(pt - axis_pt, ax)

        x_axis_base = _normalise(pt - foot_0) if radius_0 >= tol else np.array([1.0, 0.0, 0.0])
        y_axis_base = np.cross(ax, x_axis_base)
        y_norm = np.linalg.norm(y_axis_base)
        if y_norm < 1e-12:
            tmp = np.array([1.0, 0.0, 0.0]) if abs(ax[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
            y_axis_base = _normalise(np.cross(ax, tmp))
        else:
            y_axis_base = y_axis_base / y_norm

        # Ratio of this profile point's radius to the start point's radius
        radial_ratio = radius_0 / prof_start_radius if radius_0 >= tol else 0.0

        for j in range(n_arc):
            sf = scale_factors[j]
            scaled_radius = radial_ratio * sf * prof_start_radius

            # Arc angle for column j
            frac = arc_v_params[j]  # 0..1
            angle = frac * sweep

            cos_a = math.cos(angle)
            sin_a = math.sin(angle)

            # Arc weight: 1 for on-arc nodes, cos(delta/2) for tangent CPs
            delta = sweep / n_segs
            cos_half = math.cos(delta / 2.0)
            # j=0,2,4,... are on-arc nodes; j=1,3,5,... are tangent CPs
            arc_w = 1.0 if (j % 2 == 0) else cos_half

            if scaled_radius < tol:
                # On axis
                foot_j = axis_pt + (np.dot(pt - axis_pt, ax)) * ax
                pt3 = foot_j
            else:
                # Rotate x_axis_base by arc angle
                x_rot = cos_a * x_axis_base - sin_a * y_axis_base
                foot_j = axis_pt + axial_offset * ax
                pt3 = foot_j + scaled_radius * x_rot

            if j % 2 == 1:
                # Tangent CP: move radially outward by 1/cos_half
                if scaled_radius >= tol:
                    mid_angle = angle  # already mid-angle because arc_v_params uses half-steps
                    x_rot = cos_a * x_axis_base - sin_a * y_axis_base
                    pt3 = foot_j + (scaled_radius / cos_half) * x_rot

            w = pw * arc_w
            # Store in homogeneous form: (w*x, w*y, w*z, w)
            surf_cp[i, j, :3] = w * pt3
            surf_cp[i, j, 3] = w

        if knots_v is None:
            _, _, knots_v = _build_arc_data(
                foot_0, x_axis_base, y_axis_base, radius_0, 0.0, sweep
            )

    if knots_v is None:
        _, _, knots_v = _build_arc_data(
            axis_pt, np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), 1.0, 0.0, sweep
        )

    return NurbsSurface(
        degree_u=profile_curve.degree,
        degree_v=2,
        control_points=surf_cp,
        knots_u=profile_curve.knots.copy(),
        knots_v=knots_v,
    )


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
    # revolve_surface_tool
    # ------------------------------------------------------------------

    _revolve_surface_spec = ToolSpec(
        name="revolve_surface_tool",
        description=(
            "Build an exact NURBS surface of revolution by revolving a profile "
            "curve around an axis.  Uses the standard rational quadratic circle "
            "construction (correct arc weights, clamped knot vector).  Supports "
            "partial-angle sweeps (0 < sweep ≤ 2π) and handles profile points on "
            "the axis as poles.\n"
            "\n"
            "Returns:\n"
            "  ok            : bool\n"
            "  degree_u      : int  (profile degree)\n"
            "  degree_v      : int  (always 2 — rational quadratic arc)\n"
            "  num_cp_u      : int\n"
            "  num_cp_v      : int\n"
            "  knots_u       : list[float]\n"
            "  knots_v       : list[float]\n"
            "  control_points: list[list[float]]  (flattened nu*nv x 4, homogeneous)\n"
            "  n_arc_segments: int  (1/2/3/4 depending on sweep)\n"
            "\n"
            "Errors: {ok:false, reason, code} — never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "profile_points": {
                    "type": "array",
                    "description": "Control points of the profile curve, [[x,y,z], ...].",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "profile_degree": {
                    "type": "integer",
                    "description": "Degree of the profile NURBS curve (>= 1).",
                },
                "axis_point": {
                    "type": "array",
                    "description": "[x, y, z] — a point on the axis of revolution.",
                    "items": {"type": "number"},
                },
                "axis_dir": {
                    "type": "array",
                    "description": "[dx, dy, dz] — direction of the revolution axis.",
                    "items": {"type": "number"},
                },
                "start_angle": {
                    "type": "number",
                    "description": "Start angle in radians (default 0).",
                },
                "end_angle": {
                    "type": "number",
                    "description": "End angle in radians (default 2π ≈ 6.2832).",
                },
            },
            "required": ["profile_points", "profile_degree", "axis_point", "axis_dir"],
        },
    )

    @register(_revolve_surface_spec)
    async def run_revolve_surface_tool(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        raw_pts = a.get("profile_points")
        degree = a.get("profile_degree")
        ax_pt = a.get("axis_point")
        ax_dir = a.get("axis_dir")

        if not raw_pts or degree is None or not ax_pt or not ax_dir:
            return err_payload(
                "profile_points, profile_degree, axis_point, axis_dir are required",
                "BAD_ARGS",
            )

        try:
            degree = int(degree)
        except (TypeError, ValueError) as exc:
            return err_payload(f"profile_degree must be integer: {exc}", "BAD_ARGS")

        if degree < 1:
            return err_payload("profile_degree must be >= 1", "BAD_ARGS")

        try:
            cp = np.array(raw_pts, dtype=float)
            if cp.ndim != 2 or cp.shape[1] < 3:
                return err_payload("profile_points must be [[x,y,z], ...] with >= 3 coords", "BAD_ARGS")
        except Exception as exc:
            return err_payload(f"invalid profile_points: {exc}", "BAD_ARGS")

        n_cp = cp.shape[0]
        if n_cp < degree + 1:
            return err_payload(
                f"need at least degree+1={degree+1} profile control points; got {n_cp}",
                "BAD_ARGS",
            )

        # Build uniform clamped knot vector for profile
        inner = max(0, n_cp - degree - 1)
        knots_u = np.concatenate([
            np.zeros(degree + 1),
            np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else np.array([]),
            np.ones(degree + 1),
        ])

        profile = NurbsCurve(degree=degree, control_points=cp, knots=knots_u)

        start_angle = float(a.get("start_angle", 0.0))
        end_angle = float(a.get("end_angle", _TWO_PI))

        try:
            ax_pt_arr = np.asarray(ax_pt, dtype=float)
            ax_dir_arr = np.asarray(ax_dir, dtype=float)
        except Exception as exc:
            return err_payload(f"invalid axis_point/axis_dir: {exc}", "BAD_ARGS")

        try:
            surf = revolve_surface(
                profile, ax_pt_arr, ax_dir_arr, start_angle, end_angle
            )
        except Exception as exc:
            return err_payload(str(exc), "OP_FAILED")

        cp_out = surf.control_points  # (nu, nv, 4)
        nu, nv, _ = cp_out.shape
        flat = cp_out.reshape(-1, 4).tolist()

        return ok_payload({
            "degree_u": surf.degree_u,
            "degree_v": surf.degree_v,
            "num_cp_u": nu,
            "num_cp_v": nv,
            "knots_u": surf.knots_u.tolist(),
            "knots_v": surf.knots_v.tolist(),
            "control_points": flat,
            "n_arc_segments": _arc_segment_count(end_angle - start_angle),
        })

    # ------------------------------------------------------------------
    # rail_revolve_tool
    # ------------------------------------------------------------------

    _rail_revolve_spec = ToolSpec(
        name="rail_revolve_tool",
        description=(
            "Build a rail-revolve NURBS surface: the profile is rotated around the "
            "axis while being scaled so its leading edge tracks a rail curve.  "
            "Full 360° sweep always.\n"
            "\n"
            "Returns the same payload shape as revolve_surface_tool.\n"
            "\n"
            "Errors: {ok:false, reason, code} — never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "profile_points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "profile_degree": {"type": "integer"},
                "rail_points": {
                    "type": "array",
                    "description": "Control points of the rail curve [[x,y,z], ...].",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "rail_degree": {"type": "integer"},
                "axis_point": {
                    "type": "array",
                    "items": {"type": "number"},
                },
                "axis_dir": {
                    "type": "array",
                    "items": {"type": "number"},
                },
            },
            "required": [
                "profile_points", "profile_degree",
                "rail_points", "rail_degree",
                "axis_point", "axis_dir",
            ],
        },
    )

    @register(_rail_revolve_spec)
    async def run_rail_revolve_tool(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        def _make_curve(pts_raw, deg_raw, name: str):
            try:
                deg = int(deg_raw)
            except (TypeError, ValueError):
                return None, err_payload(f"{name}_degree must be integer", "BAD_ARGS")
            if deg < 1:
                return None, err_payload(f"{name}_degree must be >= 1", "BAD_ARGS")
            try:
                cp = np.array(pts_raw, dtype=float)
                if cp.ndim != 2 or cp.shape[1] < 3:
                    return None, err_payload(f"{name}_points must be [[x,y,z],...]", "BAD_ARGS")
            except Exception as exc:
                return None, err_payload(f"invalid {name}_points: {exc}", "BAD_ARGS")
            n = cp.shape[0]
            if n < deg + 1:
                return None, err_payload(f"{name} needs >= {deg+1} CPs; got {n}", "BAD_ARGS")
            inner = max(0, n - deg - 1)
            knots = np.concatenate([
                np.zeros(deg + 1),
                np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else np.array([]),
                np.ones(deg + 1),
            ])
            return NurbsCurve(degree=deg, control_points=cp, knots=knots), None

        profile, err = _make_curve(
            a.get("profile_points"), a.get("profile_degree"), "profile"
        )
        if err:
            return err
        rail, err = _make_curve(
            a.get("rail_points"), a.get("rail_degree"), "rail"
        )
        if err:
            return err

        try:
            ax_pt = np.asarray(a["axis_point"], dtype=float)
            ax_dir = np.asarray(a["axis_dir"], dtype=float)
        except Exception as exc:
            return err_payload(f"invalid axis: {exc}", "BAD_ARGS")

        try:
            surf = rail_revolve(profile, rail, ax_pt, ax_dir)
        except Exception as exc:
            return err_payload(str(exc), "OP_FAILED")

        cp_out = surf.control_points
        nu, nv, _ = cp_out.shape
        flat = cp_out.reshape(-1, 4).tolist()

        return ok_payload({
            "degree_u": surf.degree_u,
            "degree_v": surf.degree_v,
            "num_cp_u": nu,
            "num_cp_v": nv,
            "knots_u": surf.knots_u.tolist(),
            "knots_v": surf.knots_v.tolist(),
            "control_points": flat,
            "n_arc_segments": _arc_segment_count(_TWO_PI),
        })
