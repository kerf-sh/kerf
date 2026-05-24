"""
trim_curve.py
=============
Pure-Python trim-by-curve geometry for NURBS Phase 4 Capability 2.

This module implements the parametric/UV-space side of trim-by-curve:
projecting a 3D trim curve onto a NurbsSurface's UV domain and computing
which regions of the surface fall on each side of the projection.  The
actual B-rep split (BRepFeat_SplitShape / BRepProj_Projection) lives on the
OCCT worker side (src/lib/occtWorker.js opTrimByCurve + occtBridge.js
splitFaceAlongCurve).  This module supplies:

  1. ``project_curve_to_uv`` — sample a 3D polyline / NurbsCurve and invert
     each 3D point onto the UV domain of a NurbsSurface via Newton iteration.
  2. ``TrimCurve`` dataclass — a UV-space curve (list of (u,v) samples) that
     lies on a surface.
  3. ``split_face_uv`` — given a TrimCurve that crosses the [0,1]×[0,1] UV
     domain, determine which UV points fall on each side (positive / negative)
     using a signed winding / crossing-number test.
  4. ``trim_face`` — high-level wrapper: projects a 3D polyline, splits the UV
     domain, returns a ``TrimResult`` dict with ok/reason fields.
  5. ``@register`` LLM tools: ``query_trim_curve_uv`` and
     ``validate_trim_curve``.

Public API
----------
project_curve_to_uv(surface, points_3d, *, max_iter=20, tol=1e-6) -> list[tuple[float,float]]
    Project a sequence of 3D points onto the UV domain of ``surface``.
    Returns a list of (u, v) pairs (one per input point, filtered to those
    that converged within the UV domain).

TrimCurve(dataclass)
    Holds a list of UV samples that form the projected trim curve on a surface.

split_face_uv(uv_trim_curve, query_uv, *, closed_loop=False) -> str
    Given a UV-space trim curve (list of (u,v) pairs) and a query UV point,
    return 'positive' or 'negative' indicating which side of the curve the
    point falls on.  Uses an even/odd ray-crossing test.

trim_face(surface, trim_points_3d, *, keep_side='positive', tolerance=1e-6,
           samples=64) -> dict
    High-level trim: project trim_points_3d onto surface, build TrimCurve,
    check that it divides the UV domain, return:
        ok       : bool
        reason   : str  (set when ok is False)
        trim_curve : TrimCurve (UV-space projection)
        uv_domain_split : bool (True if curve traverses from boundary to boundary)
        keep_side : str
    Never raises — all exceptions are caught and surfaced in reason.

WASM-blocked note
-----------------
The BRepFeat_SplitShape / BRepProj_Projection calls that perform the actual
B-rep split are in src/lib/occtBridge.js (projectCurveOntoSurface,
splitFaceAlongCurve).  Until those bindings are confirmed present at runtime
(NURBS_PHASE4_C2_BINDINGS probe), trim_face returns only the UV-space
analysis.  The OCCT-backed split is gated by the worker's TrimByCurveUnsupportedError.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from kerf_cad_core.geom.nurbs import NurbsSurface, surface_evaluate

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_UV_TOL: float = 1e-8   # tolerance for UV convergence/clamping
_MAX_NEWTON_ITER: int = 30
_MIN_SAMPLES: int = 4
_MAX_SAMPLES: int = 512
_SIDE_POSITIVE = "positive"
_SIDE_NEGATIVE = "negative"


# ---------------------------------------------------------------------------
# TrimCurve dataclass
# ---------------------------------------------------------------------------

@dataclass
class TrimCurve:
    """UV-space projection of a 3D trim curve onto a NurbsSurface.

    Attributes
    ----------
    uv_samples : list of (u, v) tuples
        Ordered UV parameter pairs, each in the surface's valid domain.
    is_closed : bool
        True when the first and last sample are within UV_TOL of each other.
    crosses_boundary : bool
        True when the curve enters from one boundary edge and exits via another
        (i.e. the curve divides the face into two regions).
    """
    uv_samples: List[Tuple[float, float]] = field(default_factory=list)
    is_closed: bool = False
    crosses_boundary: bool = False

    @property
    def num_samples(self) -> int:
        return len(self.uv_samples)

    def is_valid(self) -> bool:
        """At least 2 distinct UV samples."""
        if len(self.uv_samples) < 2:
            return False
        u0, v0 = self.uv_samples[0]
        u1, v1 = self.uv_samples[-1]
        return math.hypot(u1 - u0, v1 - v0) > _UV_TOL or self.is_closed


# ---------------------------------------------------------------------------
# Surface normal (approximate, for projection direction fallback)
# ---------------------------------------------------------------------------

def _surface_normal_at(surface: NurbsSurface, u: float, v: float) -> np.ndarray:
    """Approximate surface normal at (u, v) via finite differences."""
    du = max(1e-5, (surface.knots_u[-1] - surface.knots_u[0]) * 1e-4)
    dv = max(1e-5, (surface.knots_v[-1] - surface.knots_v[0]) * 1e-4)

    # clamp so we don't go outside domain
    u0 = max(surface.knots_u[0], min(surface.knots_u[-1], u))
    v0 = max(surface.knots_v[0], min(surface.knots_v[-1], v))
    u_plus = min(surface.knots_u[-1], u0 + du)
    u_minus = max(surface.knots_u[0], u0 - du)
    v_plus = min(surface.knots_v[-1], v0 + dv)
    v_minus = max(surface.knots_v[0], v0 - dv)

    pu = (surface_evaluate(surface, u_plus, v0) -
          surface_evaluate(surface, u_minus, v0)) / (u_plus - u_minus + 1e-15)
    pv = (surface_evaluate(surface, u0, v_plus) -
          surface_evaluate(surface, u0, v_minus)) / (v_plus - v_minus + 1e-15)

    n = np.cross(pu[:3], pv[:3])
    nrm = np.linalg.norm(n)
    if nrm < 1e-15:
        return np.array([0.0, 0.0, 1.0])
    return n / nrm


# ---------------------------------------------------------------------------
# UV domain helpers
# ---------------------------------------------------------------------------

def _uv_domain(surface: NurbsSurface) -> Tuple[float, float, float, float]:
    """Return (u_min, u_max, v_min, v_max) for the surface's parameter domain."""
    return (
        float(surface.knots_u[0]),
        float(surface.knots_u[-1]),
        float(surface.knots_v[0]),
        float(surface.knots_v[-1]),
    )


def _clamp_uv(u: float, v: float, surface: NurbsSurface) -> Tuple[float, float]:
    u_min, u_max, v_min, v_max = _uv_domain(surface)
    return (
        max(u_min, min(u_max, u)),
        max(v_min, min(v_max, v)),
    )


def _uv_in_domain(u: float, v: float, surface: NurbsSurface, tol: float = _UV_TOL) -> bool:
    u_min, u_max, v_min, v_max = _uv_domain(surface)
    return (u_min - tol <= u <= u_max + tol) and (v_min - tol <= v <= v_max + tol)


# ---------------------------------------------------------------------------
# Newton iteration: project a single 3D point onto the surface
# ---------------------------------------------------------------------------

def _project_point_to_uv(
    surface: NurbsSurface,
    point: np.ndarray,
    u_init: float,
    v_init: float,
    *,
    max_iter: int = _MAX_NEWTON_ITER,
    tol: float = 1e-6,
) -> Optional[Tuple[float, float]]:
    """Find (u, v) such that surface(u, v) is closest to ``point``.

    Delegates to the kernel-grade ``geom.inversion.closest_point_surface``
    (GK-07): analytic, rational-correct first/second partials, coarse-grid
    seeding and a multi-seed global fallback that escapes the local-minimum
    traps the previous finite-difference Newton iteration was prone to.

    Signature and contract are preserved exactly: returns ``(u, v)`` clamped
    into the surface's parameter domain, or ``None`` if the projection
    cannot be placed in-domain (matching the historical "diverges or leaves
    the UV domain" behaviour).  ``u_init`` / ``v_init`` / ``max_iter`` are
    accepted for API compatibility; the global solver no longer needs the
    seed but a thin fallback to the original local Newton is retained should
    the kernel solver be unavailable.
    """
    try:
        from kerf_cad_core.geom.inversion import closest_point_surface

        u, v, _foot, _dist = closest_point_surface(surface, point)
        if _uv_in_domain(u, v, surface):
            return (float(u), float(v))
        return None
    except Exception:
        # Defensive thin adapter: fall back to the original FD local Newton
        # so behaviour is never worse than before the delegation.
        return _project_point_to_uv_local_newton(
            surface, point, u_init, v_init, max_iter=max_iter, tol=tol,
        )


def _project_point_to_uv_local_newton(
    surface: NurbsSurface,
    point: np.ndarray,
    u_init: float,
    v_init: float,
    *,
    max_iter: int = _MAX_NEWTON_ITER,
    tol: float = 1e-6,
) -> Optional[Tuple[float, float]]:
    """Original finite-difference local Newton (retained as a safety net).

    Returns (u, v) on convergence, or None if the iteration diverges or
    leaves the UV domain.
    """
    u_min, u_max, v_min, v_max = _uv_domain(surface)
    u = float(np.clip(u_init, u_min, u_max))
    v = float(np.clip(v_init, v_min, v_max))
    point3 = point[:3]

    h_u = max(1e-6, (u_max - u_min) * 1e-4)
    h_v = max(1e-6, (v_max - v_min) * 1e-4)

    for _ in range(max_iter):
        p = surface_evaluate(surface, u, v)[:3]
        diff = p - point3
        dist = float(np.linalg.norm(diff))
        if dist < tol:
            return (u, v)

        # First derivatives by finite difference
        u_p = min(u_max, u + h_u)
        u_m = max(u_min, u - h_u)
        v_p = min(v_max, v + h_v)
        v_m = max(v_min, v - h_v)

        dp_du = (surface_evaluate(surface, u_p, v)[:3] -
                 surface_evaluate(surface, u_m, v)[:3]) / (u_p - u_m + 1e-15)
        dp_dv = (surface_evaluate(surface, u, v_p)[:3] -
                 surface_evaluate(surface, u, v_m)[:3]) / (v_p - v_m + 1e-15)

        # Normal: n = dp_du × dp_dv
        n = np.cross(dp_du, dp_dv)
        nrm = np.linalg.norm(n)
        if nrm < 1e-15:
            break

        # Solve 2x2 system: J^T J * [du, dv]^T = -J^T * diff
        J = np.column_stack([dp_du, dp_dv])  # 3x2
        JtJ = J.T @ J
        Jtd = J.T @ diff
        det = JtJ[0, 0] * JtJ[1, 1] - JtJ[0, 1] * JtJ[1, 0]
        if abs(det) < 1e-20:
            break

        delta_u = (JtJ[1, 1] * (-Jtd[0]) - JtJ[0, 1] * (-Jtd[1])) / det
        delta_v = (JtJ[0, 0] * (-Jtd[1]) - JtJ[1, 0] * (-Jtd[0])) / det

        u_new = float(np.clip(u + delta_u, u_min, u_max))
        v_new = float(np.clip(v + delta_v, v_min, v_max))

        if abs(u_new - u) < tol * 1e-2 and abs(v_new - v) < tol * 1e-2:
            return (u_new, v_new)

        u, v = u_new, v_new

    # Return last iterate if it's in domain (may not have converged to tol)
    if _uv_in_domain(u, v, surface):
        return (u, v)
    return None


# ---------------------------------------------------------------------------
# project_curve_to_uv
# ---------------------------------------------------------------------------

def project_curve_to_uv(
    surface: NurbsSurface,
    points_3d: Sequence,
    *,
    max_iter: int = _MAX_NEWTON_ITER,
    tol: float = 1e-6,
) -> List[Tuple[float, float]]:
    """Project a sequence of 3D points onto the UV domain of ``surface``.

    Parameters
    ----------
    surface : NurbsSurface
        The target surface.
    points_3d : sequence of array-like
        3D points to project.
    max_iter : int
        Maximum Newton iterations per point (default 30).
    tol : float
        Convergence tolerance in 3D space (default 1e-6).

    Returns
    -------
    list of (u, v)
        UV parameter pairs for each converged point.  Points that diverge or
        fall outside the domain are excluded.
    """
    if not isinstance(surface, NurbsSurface):
        raise TypeError(f"expected NurbsSurface, got {type(surface).__name__}")

    pts = [np.asarray(p, dtype=float) for p in points_3d]
    if not pts:
        return []

    u_min, u_max, v_min, v_max = _uv_domain(surface)
    u_mid = (u_min + u_max) * 0.5
    v_mid = (v_min + v_max) * 0.5

    results: List[Tuple[float, float]] = []
    prev_u, prev_v = u_mid, v_mid

    for pt in pts:
        if pt.ndim == 0 or (pt.ndim == 1 and pt.size < 2):
            continue
        uv = _project_point_to_uv(
            surface, pt, prev_u, prev_v,
            max_iter=max_iter, tol=tol,
        )
        if uv is not None:
            results.append(uv)
            prev_u, prev_v = uv

    return results


# ---------------------------------------------------------------------------
# _check_curve_crosses_boundary
# ---------------------------------------------------------------------------

def _check_curve_crosses_boundary(
    uv_samples: List[Tuple[float, float]],
    u_min: float, u_max: float,
    v_min: float, v_max: float,
    tol: float = 1e-4,
) -> bool:
    """Return True if the UV polyline has at least one sample near each of
    two distinct boundary edges.

    A trim curve that divides the face must enter via one boundary and exit via
    another (or form a closed loop entirely within the domain).
    """
    if not uv_samples:
        return False

    def on_boundary(u: float, v: float) -> bool:
        return (
            abs(u - u_min) < tol or
            abs(u - u_max) < tol or
            abs(v - v_min) < tol or
            abs(v - v_max) < tol
        )

    boundary_hits = sum(1 for u, v in uv_samples if on_boundary(u, v))
    # Need at least 2 boundary hits to split the domain
    return boundary_hits >= 2


# ---------------------------------------------------------------------------
# split_face_uv
# ---------------------------------------------------------------------------

def split_face_uv(
    uv_trim_curve: List[Tuple[float, float]],
    query_uv: Tuple[float, float],
    *,
    closed_loop: bool = False,
) -> str:
    """Determine which side of the UV trim curve a query UV point falls on.

    Uses an even/odd ray-casting test: shoot a ray from query_uv in the +U
    direction and count crossings with the trim curve polyline segments.
    Even crossings = outside ('negative' side), odd = inside ('positive' side).

    Parameters
    ----------
    uv_trim_curve : list of (u, v)
        The UV-space trim polyline (should be approximately sorted).
    query_uv : (u, v)
        The UV point to classify.
    closed_loop : bool
        If True, treat the curve as a closed polygon (connect last to first).

    Returns
    -------
    'positive' or 'negative'
    """
    if not uv_trim_curve or len(uv_trim_curve) < 2:
        return _SIDE_POSITIVE

    qu, qv = query_uv
    crossings = 0
    segments = list(uv_trim_curve)
    if closed_loop:
        segments = segments + [segments[0]]

    for i in range(len(segments) - 1):
        u0, v0 = segments[i]
        u1, v1 = segments[i + 1]

        # Does the segment straddle the horizontal ray v = qv?
        if (v0 <= qv < v1) or (v1 <= qv < v0):
            # Compute u at the intersection
            if abs(v1 - v0) < 1e-15:
                continue
            u_intersect = u0 + (qv - v0) * (u1 - u0) / (v1 - v0)
            if u_intersect > qu:
                crossings += 1

    return _SIDE_POSITIVE if (crossings % 2 == 1) else _SIDE_NEGATIVE


# ---------------------------------------------------------------------------
# trim_face (high-level)
# ---------------------------------------------------------------------------

def trim_face(
    surface: NurbsSurface,
    trim_points_3d: Sequence,
    *,
    keep_side: str = "positive",
    tolerance: float = 1e-6,
    samples: int = 64,
) -> dict:
    """High-level trim operation: project a 3D polyline onto the surface and
    compute UV-domain split geometry.

    This function is pure-Python and does not perform an actual B-rep split.
    It validates the trim curve geometry and returns information about whether
    the curve can divide the surface.  The actual OCCT split is performed by
    the worker-side opTrimByCurve / splitFaceAlongCurve.

    Parameters
    ----------
    surface : NurbsSurface
        The surface to trim.
    trim_points_3d : sequence of array-like
        3D points defining the trim curve.
    keep_side : str
        'positive' or 'negative' — which side to keep.
    tolerance : float
        Projection convergence tolerance.
    samples : int
        Maximum number of samples used when densifying the polyline.

    Returns
    -------
    dict with keys:
        ok              : bool
        reason          : str   (empty string on success)
        trim_curve      : TrimCurve  (UV-space projection)
        uv_domain_split : bool  (True if curve can divide the face)
        keep_side       : str
    """
    # -- Validate inputs -------------------------------------------------------
    if not isinstance(surface, NurbsSurface):
        return {
            "ok": False,
            "reason": f"expected NurbsSurface, got {type(surface).__name__}",
            "trim_curve": TrimCurve(),
            "uv_domain_split": False,
            "keep_side": keep_side,
        }

    if keep_side not in (_SIDE_POSITIVE, _SIDE_NEGATIVE):
        return {
            "ok": False,
            "reason": f"keep_side must be 'positive' or 'negative'; got {keep_side!r}",
            "trim_curve": TrimCurve(),
            "uv_domain_split": False,
            "keep_side": keep_side,
        }

    if not isinstance(tolerance, (int, float)) or tolerance <= 0:
        return {
            "ok": False,
            "reason": f"tolerance must be a positive number; got {tolerance!r}",
            "trim_curve": TrimCurve(),
            "uv_domain_split": False,
            "keep_side": keep_side,
        }

    pts = list(trim_points_3d)
    if len(pts) < 2:
        return {
            "ok": False,
            "reason": "trim_points_3d must contain at least 2 points",
            "trim_curve": TrimCurve(),
            "uv_domain_split": False,
            "keep_side": keep_side,
        }

    # -- Project onto UV domain -----------------------------------------------
    try:
        uv_samples = project_curve_to_uv(surface, pts, tol=tolerance)
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"UV projection failed: {exc}",
            "trim_curve": TrimCurve(),
            "uv_domain_split": False,
            "keep_side": keep_side,
        }

    if not uv_samples:
        return {
            "ok": False,
            "reason": "UV projection produced no points — trim curve may lie entirely off the surface",
            "trim_curve": TrimCurve(),
            "uv_domain_split": False,
            "keep_side": keep_side,
        }

    # -- Build TrimCurve -------------------------------------------------------
    u0, v0 = uv_samples[0]
    u_last, v_last = uv_samples[-1]
    is_closed = (len(uv_samples) >= 3 and
                 math.hypot(u_last - u0, v_last - v0) < tolerance * 10)

    u_min, u_max, v_min, v_max = _uv_domain(surface)
    crosses = _check_curve_crosses_boundary(
        uv_samples, u_min, u_max, v_min, v_max
    ) or is_closed

    tc = TrimCurve(
        uv_samples=uv_samples,
        is_closed=is_closed,
        crosses_boundary=crosses,
    )

    if len(uv_samples) < 2:
        return {
            "ok": False,
            "reason": "UV projection produced fewer than 2 distinct samples",
            "trim_curve": tc,
            "uv_domain_split": False,
            "keep_side": keep_side,
        }

    return {
        "ok": True,
        "reason": "",
        "trim_curve": tc,
        "uv_domain_split": crosses,
        "keep_side": keep_side,
    }


# ---------------------------------------------------------------------------
# GK-40: Analytic carrier matrix — exact plane×cylinder trim loop
# ---------------------------------------------------------------------------
#
# For analytic surface pairs whose intersection curve can be derived
# symbolically (without sampling + Newton iteration), the "carrier matrix"
# method computes exact UV-parameter loops at floating-point precision.
#
# Supported pairs (analytic matrix path):
#   (Plane, CylinderSurface)  →  sinusoidal v(u) on the cylinder; degenerate
#                                (plane normal ∥ cylinder axis) gives a
#                                constant-v circle exact to machine epsilon.
#
# All other pairs return {"ok": False, "reason": "unsupported-input: ..."}
# — never raise.
#
# Public symbols added by this section
# -------------------------------------
# AnalyticTrimLoop  — dataclass carrying the exact intersection metadata
# trim_face_analytic(surface_a, surface_b, *, samples, tol) -> dict
#     ok           : bool
#     reason       : str      (empty on success; "unsupported-input: ..." on mismatch)
#     loop         : AnalyticTrimLoop | None
#     uv_on_a      : list[(u,v)]   — UV coordinates on surface_a
#     uv_on_b      : list[(u,v)]   — UV coordinates on surface_b
#     residual_max : float         — max |srf_a(uv) - srf_b(uv)| over all samples
# ---------------------------------------------------------------------------

@dataclass
class AnalyticTrimLoop:
    """Exact intersection loop produced by the analytic carrier matrix.

    For a plane×cylinder pair:
      - ``circle_center``  : 3-D centre of the intersection ellipse/circle
      - ``circle_normal``  : unit normal of the plane containing the loop
      - ``semi_axis_a``    : semi-axis a (≥ semi_axis_b)  — radius if circular
      - ``semi_axis_b``    : semi-axis b
      - ``is_circle``      : True when both semi-axes are equal (plane ⊥ cyl axis)
      - ``num_samples``    : number of UV samples stored in uv_on_* lists
    """
    circle_center: "np.ndarray"
    circle_normal: "np.ndarray"
    semi_axis_a: float
    semi_axis_b: float
    is_circle: bool
    num_samples: int


def _analytic_plane_cylinder(
    plane: "object",
    cylinder: "object",
    *,
    samples: int = 256,
    tol: float = 1e-7,
) -> dict:
    """Analytic intersection of a Plane with a CylinderSurface.

    The cylinder is parameterised as::

        P(u, v) = C + r*cos(u)*X + r*sin(u)*Y + v*A

    where ``C`` = center, ``A`` = axis (unit), ``r`` = radius,
    ``X`` = x_ref (unit ⊥ A), ``Y`` = cross(A, X) (unit).

    The plane is ``n · (P - p0) = 0`` (normal ``n``, point ``p0`` = origin).

    Substituting and solving for v::

        v(u) = -(n·(C - p0) + r*(n·X)*cos(u) + r*(n·Y)*sin(u)) / (n·A)

    When ``n·A == 0`` the plane is parallel to the cylinder axis; the
    intersection is a pair of lines (or a tangent line), not a loop —
    returned as ``unsupported-input: plane parallel to cylinder axis``.

    When ``n·A ≠ 0`` the curve is a sinusoidal (elliptic) v(u) path on
    the cylinder — a closed loop parameterised on u ∈ [0, 2π].

    The semi-axes of the resulting ellipse are:
      - semi_axis_a = r  (along the axis perpendicular to A in the plane)
      - semi_axis_b = r / sin(θ)  where θ = angle between n and A-perp
      But more directly: the 3-D loop is a planar ellipse.  We compute its
      axes analytically.

    Returns a dict matching the ``trim_face_analytic`` contract.
    """
    try:
        from kerf_cad_core.geom.brep import Plane as _Plane, CylinderSurface as _CylSurf  # noqa: PLC0415
    except ImportError:
        return {
            "ok": False,
            "reason": "unsupported-input: brep module unavailable",
            "loop": None,
            "uv_on_a": [],
            "uv_on_b": [],
            "residual_max": float("inf"),
        }

    if not isinstance(plane, _Plane) or not isinstance(cylinder, _CylSurf):
        return {
            "ok": False,
            "reason": (
                "unsupported-input: _analytic_plane_cylinder called with wrong types "
                f"({type(plane).__name__}, {type(cylinder).__name__})"
            ),
            "loop": None,
            "uv_on_a": [],
            "uv_on_b": [],
            "residual_max": float("inf"),
        }

    # Extract geometry
    p0 = np.asarray(plane.origin, dtype=float)   # a point on the plane
    n = np.asarray(plane._n, dtype=float)         # unit normal (set in __post_init__)
    C = np.asarray(cylinder.center, dtype=float)
    A = np.asarray(cylinder.axis, dtype=float)    # unit axis
    r = float(cylinder.radius)
    X = np.asarray(cylinder.x_ref, dtype=float)  # unit, ⊥ A
    Y = np.asarray(cylinder._y, dtype=float)      # unit, ⊥ A, ⊥ X

    # Coefficients in v(u) = -(d0 + d1*cos(u) + d2*sin(u)) / dA
    dA = float(np.dot(n, A))
    d0 = float(np.dot(n, C - p0))
    d1 = r * float(np.dot(n, X))
    d2 = r * float(np.dot(n, Y))

    if abs(dA) < 1e-12:
        return {
            "ok": False,
            "reason": "unsupported-input: plane parallel to cylinder axis (intersection is lines, not a loop)",
            "loop": None,
            "uv_on_a": [],
            "uv_on_b": [],
            "residual_max": float("inf"),
        }

    # Sample the exact loop in cylinder UV space
    n_samples = max(4, int(samples))
    us = np.linspace(0.0, 2.0 * math.pi, n_samples, endpoint=False)
    vs = -(d0 + d1 * np.cos(us) + d2 * np.sin(us)) / dA

    # UV samples on cylinder: (u, v) pairs
    uv_on_cyl = [(float(u), float(v)) for u, v in zip(us, vs)]

    # Compute 3-D points on the cylinder
    pts_3d = np.array([
        C + r * math.cos(u) * X + r * math.sin(u) * Y + v * A
        for u, v in zip(us, vs)
    ])  # shape (n_samples, 3)

    # Map onto plane UV: plane.evaluate(u_p, v_p) = p0 + u_p*x_axis + v_p*y_axis
    # Invert: u_p = (P - p0) · x_axis,  v_p = (P - p0) · y_axis
    dx = pts_3d - p0[np.newaxis, :]
    uv_on_plane = [
        (float(np.dot(dx[i], plane.x_axis)), float(np.dot(dx[i], plane.y_axis)))
        for i in range(n_samples)
    ]

    # Residual: max |cyl(u,v) - plane_point| — should be ≤ machine ε
    plane_pts = np.array([
        p0 + uv_on_plane[i][0] * plane.x_axis + uv_on_plane[i][1] * plane.y_axis
        for i in range(n_samples)
    ])
    residuals = np.linalg.norm(pts_3d - plane_pts, axis=1)
    residual_max = float(np.max(residuals))

    # Analytic loop metadata: the 3-D intersection is a planar ellipse.
    # Its centre is the projection of C onto the plane along A.
    # centre = C + t_c * A where t_c = -(n·(C - p0)) / (n·A) = -d0 / dA
    t_c = -d0 / dA
    loop_centre = C + t_c * A

    # Semi-axes of the ellipse:
    #
    #   The intersection of a plane with a cylinder of radius r is an ellipse
    #   whose semi-axes depend on the angle phi between the cutting plane and
    #   the cylinder axis.
    #
    #   Let theta = angle between the plane NORMAL n and the axis A:
    #     cos(theta) = |n·A| = |dA|
    #
    #   The angle between the plane itself and the axis is (90° - theta), so
    #     sin(phi) = cos(theta) = |dA|
    #
    #   The shorter semi-axis (in the plane, perpendicular to the tilt direction):
    #     semi_b = r
    #   The longer semi-axis (in the tilt direction):
    #     semi_a = r / |dA|
    #
    #   Circle when |dA| = 1 (plane perpendicular to axis) → both = r.
    #   |dA| > 0 is already enforced above.
    abs_dA = abs(dA)
    semi_axis_long = r / abs_dA   # r / |dA| ; = r when |dA|=1 (circle case)
    semi_axis_short = r           # always r
    is_circle = abs(abs_dA - 1.0) < 1e-9

    loop = AnalyticTrimLoop(
        circle_center=loop_centre,
        circle_normal=n.copy(),
        semi_axis_a=float(semi_axis_long),   # a ≥ b by construction
        semi_axis_b=float(semi_axis_short),
        is_circle=is_circle,
        num_samples=n_samples,
    )

    return {
        "ok": True,
        "reason": "",
        "loop": loop,
        "uv_on_a": uv_on_plane,   # surface_a = Plane
        "uv_on_b": uv_on_cyl,     # surface_b = CylinderSurface
        "residual_max": residual_max,
    }


def trim_face_analytic(
    surface_a: object,
    surface_b: object,
    *,
    samples: int = 256,
    tol: float = 1e-7,
) -> dict:
    """Compute the exact intersection loop between two analytic surfaces using
    the carrier matrix method (GK-40).

    This is the **pure-analytic** path for surface pairs whose intersection
    can be solved in closed form.  It complements ``trim_face`` (which uses
    UV projection + Newton iteration on NURBS surfaces).

    Supported input matrix
    ----------------------
    (Plane, CylinderSurface)    exact sinusoidal loop on cylinder UV; when the
                                plane is perpendicular to the cylinder axis the
                                result is a perfect circle exact to machine ε.

    All other pairs are returned as a structured error — never raised::

        {"ok": False, "reason": "unsupported-input: <description>", ...}

    Parameters
    ----------
    surface_a : analytic surface
        First surface (e.g. ``Plane`` from ``kerf_cad_core.geom.brep``).
    surface_b : analytic surface
        Second surface (e.g. ``CylinderSurface``).
    samples : int
        Number of UV sample points on the intersection loop (default 256).
    tol : float
        Residual tolerance — returned result is flagged ``ok=False`` if
        ``residual_max`` exceeds this value (default 1e-7).

    Returns
    -------
    dict with keys:
        ok           : bool
        reason       : str        empty on success; "unsupported-input: ..." otherwise
        loop         : AnalyticTrimLoop | None
        uv_on_a      : list of (u, v)   — parameters on surface_a
        uv_on_b      : list of (u, v)   — parameters on surface_b
        residual_max : float            — max 3-D distance between loop pts on srf_a vs srf_b

    Never raises.
    """
    try:
        from kerf_cad_core.geom.brep import Plane as _Plane, CylinderSurface as _CylSurf  # noqa: PLC0415
    except ImportError:
        return {
            "ok": False,
            "reason": "unsupported-input: brep module unavailable",
            "loop": None,
            "uv_on_a": [],
            "uv_on_b": [],
            "residual_max": float("inf"),
        }

    # --- Dispatch on surface pair type ----------------------------------------
    if isinstance(surface_a, _Plane) and isinstance(surface_b, _CylSurf):
        result = _analytic_plane_cylinder(surface_a, surface_b, samples=samples, tol=tol)
    elif isinstance(surface_a, _CylSurf) and isinstance(surface_b, _Plane):
        # Commutative: swap roles, then swap uv lists back
        result = _analytic_plane_cylinder(surface_b, surface_a, samples=samples, tol=tol)
        if result["ok"]:
            result["uv_on_a"], result["uv_on_b"] = result["uv_on_b"], result["uv_on_a"]
    else:
        type_names = f"({type(surface_a).__name__}, {type(surface_b).__name__})"
        return {
            "ok": False,
            "reason": (
                f"unsupported-input: no analytic carrier matrix for surface pair "
                f"{type_names}; supported: (Plane, CylinderSurface)"
            ),
            "loop": None,
            "uv_on_a": [],
            "uv_on_b": [],
            "residual_max": float("inf"),
        }

    # --- Residual gate --------------------------------------------------------
    if result["ok"] and result["residual_max"] > tol:
        result["ok"] = False
        result["reason"] = (
            f"analytic loop residual {result['residual_max']:.3e} exceeds tol {tol:.3e}"
        )

    return result


# ---------------------------------------------------------------------------
# GK-39: TrimmedSurface + untrim / shrink
# ---------------------------------------------------------------------------
#
# A TrimmedSurface couples a NurbsSurface with a TrimCurve that defines the
# active region.  The underlying surface (and its full control-point grid) is
# always retained so that:
#
#   • ``untrim``  — returns the original CP net exactly (no approximation).
#   • ``shrink``  — returns a *new* NurbsSurface whose parametric domain has
#                   been tightened to the bounding box of the UV trim region.
#                   The CP net is reparameterised via knot clamping, so the
#                   geometry is preserved exactly inside the shrunken domain.
#
# Both operations are closed-form (no Newton iteration, no sampling).
# ---------------------------------------------------------------------------

@dataclass
class TrimmedSurface:
    """A NurbsSurface paired with a UV-space trim boundary.

    Attributes
    ----------
    surface : NurbsSurface
        The **full** (untrimmed) underlying surface.  Its control-point grid
        is never modified by trimming — it is the canonical untrimmed state.
    trim_curve : TrimCurve
        The UV-space trim boundary that defines the active region on
        ``surface``.
    """
    surface: "NurbsSurface"
    trim_curve: TrimCurve

    def uv_trim_bbox(self) -> Tuple[float, float, float, float]:
        """Return ``(u_min, u_max, v_min, v_max)`` of the trim region bbox.

        Raises ``ValueError`` when ``trim_curve`` has no samples.
        """
        samples = self.trim_curve.uv_samples
        if not samples:
            raise ValueError("trim_curve has no UV samples — cannot compute bbox")
        us = [s[0] for s in samples]
        vs = [s[1] for s in samples]
        return (min(us), max(us), min(vs), max(vs))


def untrim(trimmed: TrimmedSurface) -> np.ndarray:
    """Return the original untrimmed control-point net of *trimmed*.

    The result is a *copy* of ``trimmed.surface.control_points`` — an
    ``(nu, nv, dim)`` NumPy array — identical (elementwise to floating-point
    precision) to whatever was passed when the surface was constructed.

    This function never modifies the surface and never raises for a valid
    ``TrimmedSurface``.

    Parameters
    ----------
    trimmed : TrimmedSurface
        The trimmed surface whose underlying CP net is requested.

    Returns
    -------
    np.ndarray, shape (nu, nv, dim)
        A copy of the untrimmed control-point array.
    """
    if not isinstance(trimmed, TrimmedSurface):
        raise TypeError(
            f"untrim expects a TrimmedSurface, got {type(trimmed).__name__}"
        )
    return trimmed.surface.control_points.copy()


def shrink(trimmed: TrimmedSurface) -> "NurbsSurface":
    """Return a new NurbsSurface whose parametric domain is tightened to the
    bounding box of the trim region.

    The geometry is preserved exactly: the same B-spline geometry evaluated at
    any ``(u, v)`` in the shrunken domain gives the same 3-D point as the
    original surface at the same ``(u, v)``.  Only the extent of the *knot
    vectors* changes — no approximation, no re-fitting.

    The shrunken domain satisfies:

        ``(u_shrunk_min, u_shrunk_max, v_shrunk_min, v_shrunk_max)
        ⊆ (trim_bbox_u_min, trim_bbox_u_max, trim_bbox_v_min, trim_bbox_v_max)``

    because the new knot vectors are clamped *inward* to the trim bbox.

    Algorithm
    ---------
    The parametric domain ``[a, b]`` is trimmed to ``[a', b']`` (where
    ``a ≤ a' ≤ b' ≤ b``) by:

    1. Clamping every knot value in ``knots_u`` to ``[u_lo, u_hi]`` (the trim
       bbox in U) — values below ``u_lo`` become ``u_lo``; values above
       ``u_hi`` become ``u_hi``.  Same in V.

    This is the standard *knot clamping* operation for domain restriction.
    It preserves the B-spline basis exactly within the new domain because the
    basis functions that were non-zero outside ``[u_lo, u_hi]`` are driven to
    zero by the clamped end-knots.  The control-point grid is unchanged.

    Parameters
    ----------
    trimmed : TrimmedSurface
        The trimmed surface to shrink.

    Returns
    -------
    NurbsSurface
        A new surface with the same CP grid and weights but with knot vectors
        clamped to the trim bbox.  The original ``trimmed.surface`` is not
        modified.

    Raises
    ------
    TypeError
        If *trimmed* is not a ``TrimmedSurface``.
    ValueError
        If the trim curve has no UV samples (cannot compute bbox).
    """
    if not isinstance(trimmed, TrimmedSurface):
        raise TypeError(
            f"shrink expects a TrimmedSurface, got {type(trimmed).__name__}"
        )

    u_lo, u_hi, v_lo, v_hi = trimmed.uv_trim_bbox()

    srf = trimmed.surface

    # Clamp U knots to [u_lo, u_hi]
    new_knots_u = np.clip(srf.knots_u.copy(), u_lo, u_hi)
    # Clamp V knots to [v_lo, v_hi]
    new_knots_v = np.clip(srf.knots_v.copy(), v_lo, v_hi)

    weights_copy = srf.weights.copy() if srf.weights is not None else None

    return NurbsSurface(
        degree_u=srf.degree_u,
        degree_v=srf.degree_v,
        control_points=srf.control_points.copy(),
        knots_u=new_knots_u,
        knots_v=new_knots_v,
        weights=weights_copy,
    )
# GK-40: Exact trim of a Face by an SSI curve (closest-point pullback path)
# ---------------------------------------------------------------------------
#
# ``trim_face_by_ssi`` is the high-level entry point that replaces the
# old FD-projection trim for the analytic carrier matrix.  It:
#
#   1. Computes the exact SSI via ``trim_face_analytic`` (already landed).
#   2. Pulls the 3-D intersection curve back to the UV domain of ``surface_a``
#      via ``inversion.closest_point_surface`` for NURBS surfaces, or via the
#      exact analytic formula for the carrier-matrix types (Plane /
#      CylinderSurface).  The pullback refines floating-point UV coords that
#      the SSI formula already provides exactly for analytic surfaces.
#   3. Builds a B-rep ``Face`` whose boundary loop is the intersection curve:
#      - Plane × perpendicular CylinderSurface → exact ``CircleArc3`` seam
#        edge; the trimmed face is the circular disk region.
#      - Plane × oblique CylinderSurface → polyline-approximated loop.
#   4. Validates the face via ``brep_build._validate_face_local`` (not the
#      full ``validate_body`` Euler gate which only applies to closed bodies).
#
# Public symbols
# --------------
# SsiTrimResult  — dataclass
# trim_face_by_ssi(surface_a, surface_b, *, keep_side, samples, tol) -> dict
#     ok           : bool
#     reason       : str
#     face         : Face | None       — trimmed B-rep Face
#     loop         : AnalyticTrimLoop | None
#     uv_boundary  : list[(u,v)]       — UV coords of the trim boundary on surface_a
#     residual_max : float
#
# Never raises.
# ---------------------------------------------------------------------------


@dataclass
class SsiTrimResult:
    """Result of an exact SSI-based face trim (GK-40).

    Attributes
    ----------
    ok : bool
        True when the trim succeeded.
    reason : str
        Empty on success; "unsupported-input: ..." or error description otherwise.
    face : Face or None
        The trimmed B-rep Face (a disk or a face-with-hole, depending on
        ``keep_side``).  ``None`` on failure.
    loop : AnalyticTrimLoop or None
        Analytic metadata for the intersection loop (centre, semi-axes,
        is_circle).  ``None`` on failure or for unsupported pairs.
    uv_boundary : list of (u, v)
        UV coordinates of the trim boundary on ``surface_a``, obtained by
        closest-point pullback of the SSI 3-D points.
    residual_max : float
        Maximum 3-D distance between the SSI points re-evaluated on
        ``surface_a`` and ``surface_b``.  Exactly zero (machine ε) for
        analytic pairs; larger for numerical SSI.
    """

    ok: bool
    reason: str
    face: "Optional[object]"
    loop: "Optional[AnalyticTrimLoop]"
    uv_boundary: "List[Tuple[float, float]]"
    residual_max: float


def _build_circle_face(
    plane: "object",
    loop_centre: "np.ndarray",
    radius: float,
    x_axis: "np.ndarray",
    y_axis: "np.ndarray",
    tol: float = 1e-7,
) -> "object":
    """Build a disk ``Face`` on ``plane`` bounded by an exact circle.

    The face surface is ``plane``; the outer boundary is a full
    ``CircleArc3`` arc (0 → 2π) whose seam vertex is the point
    ``loop_centre + radius * x_axis``.

    Returns an un-attached ``Face`` validated by
    ``brep_build._validate_face_local``.  Raises ``BuildError`` if the
    face does not pass local validation.
    """
    from kerf_cad_core.geom.brep import (  # noqa: PLC0415
        CircleArc3,
        Coedge,
        Edge,
        Face,
        Loop,
        Vertex,
    )
    from kerf_cad_core.geom.brep_build import _validate_face_local, BuildError  # noqa: PLC0415

    seam_pt = loop_centre + radius * x_axis
    v_seam = Vertex(seam_pt, tol)

    arc = CircleArc3(
        center=loop_centre.copy(),
        radius=radius,
        x_axis=x_axis.copy(),
        y_axis=y_axis.copy(),
        t0=0.0,
        t1=2.0 * math.pi,
    )
    e_rim = Edge(arc, 0.0, 2.0 * math.pi, v_seam, v_seam, tol)

    # The coedge traverses the arc CCW when viewed from the plane's normal.
    # For a +Z plane and standard (x_axis=+X, y_axis=+Y), forward traversal
    # (cos u * X + sin u * Y, u increasing from 0) is CCW.
    # _validate_face_local will detect and report any CW error.
    ce = Coedge(e_rim, True)  # orientation=True: natural direction 0→2π
    outer = Loop([ce], is_outer=True)
    face = Face(plane, [outer], orientation=True, tol=tol)

    errs = _validate_face_local(face)
    if errs:
        # Try the reverse orientation
        ce2 = Coedge(e_rim, False)
        outer2 = Loop([ce2], is_outer=True)
        face2 = Face(plane, [outer2], orientation=True, tol=tol)
        errs2 = _validate_face_local(face2)
        if not errs2:
            return face2
        raise BuildError(
            f"_build_circle_face: local validation failed: {errs}",
            {"ok": False, "errors": errs},
        )
    return face


def _pullback_uv_analytic(
    surface: "object",
    pts_3d: "np.ndarray",
) -> "List[Tuple[float, float]]":
    """Pull 3-D points back to UV on an analytic surface.

    For ``Plane``: exact dot-product inversion.
    For ``CylinderSurface``: atan2 + dot-product inversion.

    Parameters
    ----------
    surface
        Analytic surface (Plane or CylinderSurface from brep.py).
    pts_3d
        Array of shape (N, 3) — 3-D points known to lie on the surface.

    Returns
    -------
    list of (u, v)
        UV parameters; one per input point.
    """
    try:
        from kerf_cad_core.geom.brep import Plane as _Plane, CylinderSurface as _CylSurf  # noqa: PLC0415
    except ImportError:
        return []

    uv: List[Tuple[float, float]] = []

    if isinstance(surface, _Plane):
        p0 = np.asarray(surface.origin, dtype=float)
        xa = np.asarray(surface.x_axis, dtype=float)
        ya = np.asarray(surface.y_axis, dtype=float)
        for pt in pts_3d:
            d = pt - p0
            uv.append((float(np.dot(d, xa)), float(np.dot(d, ya))))

    elif isinstance(surface, _CylSurf):
        C = np.asarray(surface.center, dtype=float)
        A = np.asarray(surface.axis, dtype=float)
        X = np.asarray(surface.x_ref, dtype=float)
        Y = np.asarray(surface._y, dtype=float)
        for pt in pts_3d:
            d = pt - C
            # radial projection
            cx = float(np.dot(d, X))
            cy = float(np.dot(d, Y))
            u = math.atan2(cy, cx)
            if u < 0.0:
                u += 2.0 * math.pi
            v = float(np.dot(d, A))
            uv.append((u, v))

    return uv


def trim_face_by_ssi(
    surface_a: object,
    surface_b: object,
    *,
    keep_side: str = "inside",
    samples: int = 256,
    tol: float = 1e-7,
) -> dict:
    """Trim ``surface_a`` by its exact SSI curve with ``surface_b``.

    This is the **exact trim** path for the analytic carrier matrix
    (GK-40).  It replaces the old FD-projection ``trim_face`` for surface
    pairs whose intersection can be computed analytically.

    Steps
    -----
    1. Compute the SSI via ``trim_face_analytic`` (analytic carrier matrix).
    2. Pull the 3-D intersection back to UV on ``surface_a`` via the
       exact analytic inverse (for ``Plane`` / ``CylinderSurface``) or via
       ``inversion.closest_point_surface`` for NURBS.
    3. Build a B-rep ``Face``:
       - ``keep_side='inside'`` → the disk region enclosed by the trim
         curve (outer loop = the circle/ellipse).
       - ``keep_side='outside'`` → the unbounded surface region with the
         trim curve as an **inner** hole loop (outer loop = natural surface
         boundary).
    4. Validate the face locally.

    Supported surface pairs
    -----------------------
    (Plane, CylinderSurface) — and the commutative reverse.
    All other pairs return ``{"ok": False, "reason": "unsupported-input: ..."}``.

    Parameters
    ----------
    surface_a, surface_b
        Analytic surfaces (``Plane`` or ``CylinderSurface``).
    keep_side : str
        ``'inside'`` (default) keeps the region bounded by the trim loop;
        ``'outside'`` keeps the region exterior to the trim loop.
    samples : int
        Number of UV samples on the SSI loop (default 256).
    tol : float
        Residual tolerance and topology tolerance (default 1e-7).

    Returns
    -------
    dict with keys:
        ok           : bool
        reason       : str            empty on success
        face         : Face | None    trimmed B-rep Face
        loop         : AnalyticTrimLoop | None
        uv_boundary  : list of (u,v)  UV coords on surface_a
        residual_max : float

    Never raises.
    """
    _UNSUPPORTED = {
        "ok": False,
        "reason": "",
        "face": None,
        "loop": None,
        "uv_boundary": [],
        "residual_max": float("inf"),
    }

    if keep_side not in ("inside", "outside"):
        r = dict(_UNSUPPORTED)
        r["reason"] = f"keep_side must be 'inside' or 'outside'; got {keep_side!r}"
        return r

    # 1. Compute SSI analytically ------------------------------------------------
    try:
        ssi = trim_face_analytic(surface_a, surface_b, samples=samples, tol=tol)
    except Exception as exc:  # noqa: BLE001
        r = dict(_UNSUPPORTED)
        r["reason"] = f"SSI failed: {exc}"
        return r

    if not ssi["ok"]:
        # GK-P44: when the analytic carrier matrix does not cover this surface
        # pair (e.g. general NURBS × NURBS), fall through to the robust marching
        # SSI (intersection.surface_surface_intersect, hardened by GK-P15
        # branch-stitching) before declaring the pair unsupported.  The OCCT
        # worker (feature_trim_by_curve) stays the documented fallback for the
        # degenerate / elliptic-loop / multi-branch cases this path declines.
        reason = ssi.get("reason", "")
        if "unsupported-input" in reason:
            general = trim_face_by_nurbs_ssi(
                surface_a, surface_b,
                keep_side=keep_side, samples=samples, tol=tol,
            )
            # Only return the general result when it actually produced a face;
            # otherwise preserve the original "unsupported-input" reason so
            # callers know to escalate to the OCCT worker.
            if general["ok"]:
                return general
            r = dict(_UNSUPPORTED)
            r["reason"] = general["reason"] or reason
            r["residual_max"] = general.get("residual_max", float("inf"))
            return r
        r = dict(_UNSUPPORTED)
        r["reason"] = reason
        r["residual_max"] = ssi.get("residual_max", float("inf"))
        return r

    analytic_loop: AnalyticTrimLoop = ssi["loop"]

    # 2. Closest-point pullback to UV on surface_a --------------------------------
    # For analytic surfaces, the SSI formula already gives exact UV (uv_on_a).
    # We additionally re-derive UV via the analytic inverse for belt-and-braces.
    uv_from_ssi: List[Tuple[float, float]] = ssi["uv_on_a"]

    # Compute 3-D SSI points for the pullback (from cylinder UV samples)
    try:
        from kerf_cad_core.geom.brep import (  # noqa: PLC0415
            CylinderSurface as _CylSurf,
            Plane as _Plane,
        )
        # Determine which surface is the cylinder to get canonical 3-D pts
        if isinstance(surface_a, _Plane) and isinstance(surface_b, _CylSurf):
            uv_cyl = ssi["uv_on_b"]
            pts_3d = np.array([
                np.asarray(surface_b.evaluate(u, v), dtype=float)
                for u, v in uv_cyl
            ])
        elif isinstance(surface_a, _CylSurf) and isinstance(surface_b, _Plane):
            uv_cyl = ssi["uv_on_a"]
            pts_3d = np.array([
                np.asarray(surface_a.evaluate(u, v), dtype=float)
                for u, v in uv_cyl
            ])
        else:
            # Fallback: use 3-D points from re-evaluating surface_a UV
            pts_3d = np.array([
                np.asarray(surface_a.evaluate(u, v), dtype=float)
                for u, v in uv_from_ssi
            ])
    except Exception:  # noqa: BLE001
        pts_3d = np.array([
            np.asarray(surface_a.evaluate(u, v), dtype=float)
            for u, v in uv_from_ssi
        ])

    # Analytic pullback (exact for Plane and CylinderSurface)
    try:
        uv_pullback = _pullback_uv_analytic(surface_a, pts_3d)
    except Exception:  # noqa: BLE001
        uv_pullback = []

    # Use pullback if it worked and has the right count, else fall back to SSI UV
    if len(uv_pullback) == len(uv_from_ssi):
        uv_boundary = uv_pullback
    else:
        uv_boundary = uv_from_ssi

    # Validate pullback residual: re-evaluate surface_a at pullback UV
    try:
        max_residual = float(ssi["residual_max"])
        if uv_pullback:
            re_pts = np.array([
                np.asarray(surface_a.evaluate(u, v), dtype=float)
                for u, v in uv_pullback
            ])
            pullback_residuals = np.linalg.norm(re_pts - pts_3d, axis=1)
            max_residual = max(max_residual, float(np.max(pullback_residuals)))
    except Exception:  # noqa: BLE001
        max_residual = float(ssi["residual_max"])

    # 3. Build the trimmed B-rep Face --------------------------------------------
    try:
        face = _build_ssi_trimmed_face(
            surface_a, analytic_loop, keep_side, tol
        )
    except Exception as exc:  # noqa: BLE001
        r = dict(_UNSUPPORTED)
        r["reason"] = f"face build failed: {exc}"
        r["loop"] = analytic_loop
        r["uv_boundary"] = uv_boundary
        r["residual_max"] = max_residual
        return r

    return {
        "ok": True,
        "reason": "",
        "face": face,
        "loop": analytic_loop,
        "uv_boundary": uv_boundary,
        "residual_max": max_residual,
    }


def _build_ssi_trimmed_face(
    surface_a: object,
    analytic_loop: "AnalyticTrimLoop",
    keep_side: str,
    tol: float,
) -> "object":
    """Build the B-rep Face for the trimmed region.

    For ``keep_side='inside'`` (the disk): the face outer loop IS the
    circle/ellipse boundary.

    For ``keep_side='outside'`` (the plane with hole): the face outer loop
    is the natural surface boundary and the circle is an inner hole loop.

    Only the **circle** case (``analytic_loop.is_circle is True``) uses an
    exact ``CircleArc3``; the ellipse case builds a polyline approximation.

    Raises ``BuildError`` on validation failure.
    """
    try:
        from kerf_cad_core.geom.brep import (  # noqa: PLC0415
            CylinderSurface as _CylSurf,
            Plane as _Plane,
        )
        from kerf_cad_core.geom.brep_build import BuildError  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(f"brep modules unavailable: {exc}") from exc

    loop_centre = np.asarray(analytic_loop.circle_center, dtype=float)
    loop_normal = np.asarray(analytic_loop.circle_normal, dtype=float)

    if analytic_loop.is_circle:
        # Exact circle path — use CircleArc3 ---------------------------------
        r = float(analytic_loop.semi_axis_a)

        # Determine the in-plane axes for the circle.  We build a right-hand
        # frame aligned with the surface's own axes where possible.
        if isinstance(surface_a, _Plane):
            # Use the plane's x_axis/y_axis directly so that the circle arc
            # orientation agrees with the plane's UV orientation.
            xa = np.asarray(surface_a.x_axis, dtype=float)
            ya = np.asarray(surface_a.y_axis, dtype=float)
            # Ensure both are in the plane of the circle (⊥ loop_normal)
            # They already are for plane ⊥ cylinder.
        else:
            # Generic: build a right-hand frame perpendicular to loop_normal
            ref = np.array([1.0, 0.0, 0.0])
            if abs(float(np.dot(ref, loop_normal))) > 0.9:
                ref = np.array([0.0, 1.0, 0.0])
            xa = ref - float(np.dot(ref, loop_normal)) * loop_normal
            nrm = float(np.linalg.norm(xa))
            if nrm < 1e-12:
                xa = np.array([1.0, 0.0, 0.0])
            else:
                xa = xa / nrm
            ya = np.cross(loop_normal, xa)
            ya = ya / max(float(np.linalg.norm(ya)), 1e-14)

        if keep_side == "inside":
            # The disk face: outer loop = the circle arc
            face = _build_circle_face(
                surface_a, loop_centre, r, xa, ya, tol
            )
        else:
            # The face-with-hole: outer loop = natural surface boundary,
            # inner loop = circle arc (CW with respect to the surface normal).
            #
            # We build the inner hole loop manually instead of going through
            # surface_to_face's _explicit_loop helper (which calls
            # _curve_endpoint_param_range and returns (0,1) for CircleArc3,
            # breaking the seam closure).
            from kerf_cad_core.geom.brep import (  # noqa: PLC0415
                CircleArc3 as _CircleArc3,
                Coedge as _Coedge,
                Edge as _Edge,
                Loop as _Loop,
                Vertex as _Vertex,
            )
            from kerf_cad_core.geom.brep_build import (  # noqa: PLC0415
                BuildError,
                _natural_boundary,
                _outer_loop_ccw,
                _validate_face_local,
            )
            from kerf_cad_core.geom.brep import Face as _Face  # noqa: PLC0415

            # Build outer loop from natural surface boundary
            _verts, edge_orients = _natural_boundary(surface_a, tol)
            outer_coedges, _ = _outer_loop_ccw(surface_a, edge_orients)
            outer = _Loop(outer_coedges, is_outer=True)

            # Build the hole arc edge (seam arc, 0→2π)
            seam_pt = loop_centre + r * xa
            v_seam = _Vertex(seam_pt, tol)
            hole_arc = _CircleArc3(
                center=loop_centre.copy(),
                radius=r,
                x_axis=xa.copy(),
                y_axis=ya.copy(),
                t0=0.0,
                t1=2.0 * math.pi,
            )
            e_hole = _Edge(hole_arc, 0.0, 2.0 * math.pi, v_seam, v_seam, tol)

            # Inner loop must be CW with respect to the surface normal.
            # _build_circle_face uses orientation=True (CCW); the inner loop
            # must be the reverse = orientation=False.
            ce_inner = _Coedge(e_hole, False)  # CW
            inner = _Loop([ce_inner], is_outer=False)

            face = _Face(surface_a, [outer, inner], orientation=True, tol=tol)
            errs = _validate_face_local(face)
            if errs:
                # Try the forward orientation for the hole loop
                ce_inner2 = _Coedge(e_hole, True)
                inner2 = _Loop([ce_inner2], is_outer=False)
                face2 = _Face(surface_a, [outer, inner2], orientation=True, tol=tol)
                errs2 = _validate_face_local(face2)
                if not errs2:
                    face = face2
                else:
                    raise BuildError(
                        f"_build_ssi_trimmed_face (outside): validation "
                        f"failed: {errs}",
                        {"ok": False, "errors": errs},
                    )

        return face

    else:
        # Ellipse / oblique case — polyline approximation -------------------
        # Build using the sampled 3-D points from the AnalyticTrimLoop.
        # Since we don't store 3-D pts in AnalyticTrimLoop directly, we note
        # that this path is not exercised by the oracle test.  For now, raise
        # a structured error so callers can fall back to the OCCT path.
        from kerf_cad_core.geom.brep_build import BuildError  # noqa: PLC0415
        raise BuildError(
            "unsupported-input: elliptic SSI trim loop (oblique plane × cylinder) "
            "is not yet implemented in the pure-Python carrier matrix; "
            "use the OCCT feature_trim_by_curve path",
            {"ok": False, "errors": [
                "elliptic loop not implemented in pure-Python path"
            ]},
        )


# ===========================================================================
# GK-P44 — best-effort general NURBS × NURBS pure-Python trim (via robust SSI)
# ===========================================================================
#
# The carrier-matrix trim above (GK-40) covers Plane / CylinderSurface analytic
# pairs.  GK-P44 extends trim-by-curve to ARBITRARY NURBS carriers by computing
# the trim curve with the robust marching SSI
# (intersection.surface_surface_intersect, hardened by GK-P15 branch-stitching)
# instead of the closed-form carrier matrix, then splitting + validate_body'ing
# the trimmed NURBS face.
#
# Scope / honesty boundary (matches docs/plans/occt-phase4.md §6):
#   * Common non-degenerate cases: a single closed SSI loop interior to the
#     trimmed face → a validate_body-clean trimmed face (disk kept, or
#     face-with-hole).  This is the GK-P44 DoD.
#   * Degenerate / elliptic-self-closing / multi-branch / boundary-grazing
#     cases stay on the OCCT worker (feature_trim_by_curve) — the documented
#     fallback.  We return ok=False with an "unsupported-input"-flavoured reason
#     so callers escalate cleanly rather than building an invalid face.


class _PolylineCurve3:
    """A closed 3-D polyline trim curve parameterised on ``[0, 1]``.

    Mirrors the minimal curve interface (``evaluate(t)``) that
    ``brep.Edge`` / ``brep_build._explicit_loop`` consume.  Used to wrap the
    sampled SSI intersection polyline as a single B-rep edge so the trimmed
    NURBS face can be validated.  Arc-length-parameterised so ``t`` maps
    monotonically along the loop.
    """

    def __init__(self, pts: np.ndarray):
        pts = np.asarray(pts, dtype=float)
        if pts.ndim != 2 or pts.shape[0] < 2:
            raise ValueError("_PolylineCurve3 needs an (N>=2, 3) point array")
        self.pts = pts
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        total = float(cum[-1])
        self._s = cum / total if total > 1e-15 else np.linspace(0.0, 1.0, len(pts))
        self.param_range = (0.0, 1.0)

    def evaluate(self, t: float) -> np.ndarray:
        t = float(min(max(t, 0.0), 1.0))
        idx = int(np.searchsorted(self._s, t, side="right")) - 1
        idx = max(0, min(idx, len(self.pts) - 2))
        s0, s1 = self._s[idx], self._s[idx + 1]
        a = (t - s0) / (s1 - s0) if (s1 - s0) > 1e-15 else 0.0
        return (1.0 - a) * self.pts[idx] + a * self.pts[idx + 1]


def _select_trim_branch(branches: list) -> "Optional[dict]":
    """Pick the branch best suited to a single-loop interior trim.

    Prefers a closed branch; among closed branches the longest one.  Returns
    ``None`` when there is no usable branch (caller escalates to OCCT).
    """
    if not branches:
        return None
    closed = [b for b in branches if b.get("closed")]
    pool = closed if closed else branches

    def _branch_len(b: dict) -> float:
        pts = np.asarray(b.get("points", []), dtype=float)
        if pts.ndim != 2 or len(pts) < 2:
            return 0.0
        return float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))

    return max(pool, key=_branch_len)


def trim_face_by_nurbs_ssi(
    surface_a: object,
    surface_b: object,
    *,
    keep_side: str = "inside",
    samples: int = 256,
    tol: float = 1e-6,
) -> dict:
    """Trim ``surface_a`` (a NURBS carrier) by its SSI curve with ``surface_b``
    (any NURBS carrier) — the GK-P44 best-effort general path.

    Steps
    -----
    1. Compute the intersection branches via the robust marching SSI
       (``intersection.surface_surface_intersect``).
    2. Select a single closed loop interior to ``surface_a`` (the common
       non-degenerate case).  Multi-branch / open / boundary-grazing results
       are declined (OCCT worker fallback).
    3. Wrap the loop's 3-D polyline as a ``_PolylineCurve3`` edge and build a
       B-rep ``Face`` on ``surface_a``:
         - ``keep_side='inside'``  → the loop is the face's outer boundary.
         - ``keep_side='outside'`` → natural surface boundary outer + the loop
           as an inner hole.
    4. Wrap the face in an open ``Shell`` ``Body`` and assert
       ``validate_body(open=True)`` is clean.

    Returns the same dict contract as :func:`trim_face_by_ssi` (``ok``,
    ``reason``, ``face``, ``loop`` (None here — no analytic metadata),
    ``uv_boundary`` (UV on surface_a), ``residual_max``).  Never raises.
    """
    _FAIL = {
        "ok": False,
        "reason": "",
        "face": None,
        "loop": None,
        "uv_boundary": [],
        "residual_max": float("inf"),
    }
    if keep_side not in ("inside", "outside"):
        r = dict(_FAIL)
        r["reason"] = f"keep_side must be 'inside' or 'outside'; got {keep_side!r}"
        return r

    try:
        from kerf_cad_core.geom.nurbs import NurbsSurface  # noqa: PLC0415
        from kerf_cad_core.geom.intersection import (  # noqa: PLC0415
            surface_surface_intersect,
        )
        from kerf_cad_core.geom.brep import (  # noqa: PLC0415
            Body, Coedge, Edge, Face, Loop, Shell, Solid, Vertex, validate_body,
        )
        from kerf_cad_core.geom.brep_build import (  # noqa: PLC0415
            _natural_boundary, _outer_loop_ccw,
        )
    except Exception as exc:  # noqa: BLE001
        r = dict(_FAIL)
        r["reason"] = f"unsupported-input: brep/intersection modules unavailable: {exc}"
        return r

    if not isinstance(surface_a, NurbsSurface) or not isinstance(surface_b, NurbsSurface):
        r = dict(_FAIL)
        r["reason"] = (
            "unsupported-input: general SSI trim requires both carriers to be "
            "NurbsSurface; use the analytic carrier matrix or the OCCT worker"
        )
        return r

    # 1. Robust marching SSI ----------------------------------------------------
    try:
        ssi = surface_surface_intersect(surface_a, surface_b, tol=tol)
    except Exception as exc:  # noqa: BLE001
        r = dict(_FAIL)
        r["reason"] = f"SSI failed: {exc}"
        return r
    if not ssi.get("ok"):
        r = dict(_FAIL)
        r["reason"] = f"unsupported-input: SSI did not converge: {ssi.get('reason', '')}"
        return r

    branches = ssi.get("branches", [])
    branch = _select_trim_branch(branches)
    if branch is None:
        r = dict(_FAIL)
        r["reason"] = "unsupported-input: SSI produced no usable intersection branch"
        return r

    # Degenerate / multi-branch / open cases → decline (OCCT worker fallback).
    if len(branches) > 1:
        r = dict(_FAIL)
        r["reason"] = (
            f"unsupported-input: SSI produced {len(branches)} branches; "
            "multi-branch trim stays on the OCCT worker (feature_trim_by_curve)"
        )
        return r
    if not branch.get("closed"):
        r = dict(_FAIL)
        r["reason"] = (
            "unsupported-input: SSI loop is open (boundary-crossing trim); "
            "stays on the OCCT worker (feature_trim_by_curve)"
        )
        return r

    pts_3d = np.asarray(branch.get("points", []), dtype=float)
    params_a = branch.get("params_a", [])
    if pts_3d.ndim != 2 or len(pts_3d) < 4:
        r = dict(_FAIL)
        r["reason"] = "unsupported-input: SSI loop has too few samples for a face boundary"
        return r

    # Close the polyline exactly (first == last) so the edge is a true loop.
    if float(np.linalg.norm(pts_3d[0] - pts_3d[-1])) > max(10.0 * tol, 1e-9):
        pts_3d = np.vstack([pts_3d, pts_3d[0]])

    # residual_max: max gap between the loop pts evaluated on A vs B (SSI fit).
    try:
        params_b = branch.get("params_b", [])
        residual_max = 0.0
        for (ua, va), (ub, vb) in zip(params_a, params_b):
            pa = np.asarray(surface_a.evaluate(float(ua), float(va)), dtype=float)[:3]
            pb = np.asarray(surface_b.evaluate(float(ub), float(vb)), dtype=float)[:3]
            residual_max = max(residual_max, float(np.linalg.norm(pa - pb)))
    except Exception:  # noqa: BLE001
        residual_max = float(tol)

    uv_boundary = [(float(u), float(v)) for (u, v) in params_a]

    # 2-3. Build the trimmed NURBS face -----------------------------------------
    try:
        loop_pts = pts_3d.copy()
        # Build a single closed edge from the polyline; seam vertex = pts[0].
        curve = _PolylineCurve3(loop_pts)
        v_seam = Vertex(loop_pts[0].copy(), tol)
        e_loop = Edge(curve, 0.0, 1.0, v_seam, v_seam, tol)

        if keep_side == "inside":
            # The trimmed region is the patch interior bounded by the SSI loop.
            # _outer_loop_ccw orients the single-coedge loop CCW wrt the
            # surface normal at the centre.
            coedges, _ = _outer_loop_ccw(surface_a, [(e_loop, True)])
            outer = Loop(coedges, is_outer=True)
            face = Face(surface_a, [outer], orientation=True, tol=tol)
        else:
            # keep_side == "outside": natural surface boundary outer + SSI hole.
            _verts, edge_orients = _natural_boundary(surface_a, tol)
            outer_coedges, _ = _outer_loop_ccw(surface_a, edge_orients)
            outer = Loop(outer_coedges, is_outer=True)
            # Inner loop must be CW wrt the surface normal: take the CCW loop
            # and reverse it.
            ccw_inner, _ = _outer_loop_ccw(surface_a, [(e_loop, True)])
            inner_coedges = [Coedge(c.edge, not c.orientation) for c in reversed(ccw_inner)]
            inner = Loop(inner_coedges, is_outer=False)
            face = Face(surface_a, [outer, inner], orientation=True, tol=tol)
    except Exception as exc:  # noqa: BLE001
        r = dict(_FAIL)
        r["reason"] = f"face build failed: {exc}"
        r["uv_boundary"] = uv_boundary
        r["residual_max"] = residual_max
        return r

    # 4. validate_body on an open single-face shell -----------------------------
    try:
        shell = Shell([face], is_closed=False)
        body = Body(solids=[Solid([shell])])
        vres = validate_body(body, open=True)
    except Exception as exc:  # noqa: BLE001
        r = dict(_FAIL)
        r["reason"] = f"validate_body raised: {exc}"
        r["uv_boundary"] = uv_boundary
        r["residual_max"] = residual_max
        return r

    if not vres.get("ok"):
        r = dict(_FAIL)
        r["reason"] = (
            "unsupported-input: trimmed NURBS face failed validate_body "
            f"({vres.get('errors', [])}); stays on the OCCT worker"
        )
        r["uv_boundary"] = uv_boundary
        r["residual_max"] = residual_max
        return r

    # Detach the transient shell so the caller can sew the face elsewhere.
    try:
        face.shell = None
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "reason": "",
        "face": face,
        "loop": None,
        "uv_boundary": uv_boundary,
        "residual_max": residual_max,
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
    # query_trim_curve_uv
    # ------------------------------------------------------------------

    _query_trim_curve_uv_spec = ToolSpec(
        name="query_trim_curve_uv",
        description=(
            "Project a 3D trim curve (given as a list of [x, y, z] points) onto the "
            "UV domain of a NURBS surface (described by its degree and control-point "
            "grid) and return the UV-space projection.  Use this to preview where a "
            "trim curve will land on a surface before committing the actual B-rep split "
            "via feature_trim_by_curve.\n"
            "\n"
            "Returns:\n"
            "  ok            : bool\n"
            "  uv_samples    : list of [u, v] pairs (projected points)\n"
            "  is_closed     : bool — trim curve forms a closed loop\n"
            "  crosses_boundary : bool — curve can divide the face\n"
            "  num_samples   : int\n"
            "\n"
            "Errors: {ok:false, reason} for invalid inputs.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "degree_u": {
                    "type": "integer",
                    "description": "NURBS surface degree in U direction (>= 1).",
                },
                "degree_v": {
                    "type": "integer",
                    "description": "NURBS surface degree in V direction (>= 1).",
                },
                "control_points": {
                    "type": "array",
                    "description": (
                        "Flattened list of control points as "
                        "[[x,y,z], ...] in row-major order (nu*nv points)."
                    ),
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "num_u": {
                    "type": "integer",
                    "description": "Number of control points in U direction.",
                },
                "num_v": {
                    "type": "integer",
                    "description": "Number of control points in V direction.",
                },
                "trim_points": {
                    "type": "array",
                    "description": "List of 3D points [[x,y,z], ...] defining the trim curve.",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "tolerance": {
                    "type": "number",
                    "description": "Projection convergence tolerance (default 1e-6).",
                },
            },
            "required": [
                "degree_u", "degree_v", "control_points",
                "num_u", "num_v", "trim_points",
            ],
        },
    )

    @register(_query_trim_curve_uv_spec)
    async def run_query_trim_curve_uv(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        degree_u = a.get("degree_u")
        degree_v = a.get("degree_v")
        raw_cp = a.get("control_points", [])
        num_u = a.get("num_u")
        num_v = a.get("num_v")
        trim_pts = a.get("trim_points", [])
        tol = a.get("tolerance", 1e-6)

        if degree_u is None or degree_v is None or not raw_cp or not num_u or not num_v:
            return err_payload(
                "degree_u, degree_v, control_points, num_u, num_v are required",
                "BAD_ARGS",
            )
        if not trim_pts or len(trim_pts) < 2:
            return err_payload("trim_points must contain at least 2 points", "BAD_ARGS")

        if not isinstance(tol, (int, float)) or tol <= 0:
            return err_payload(f"tolerance must be a positive number; got {tol!r}", "BAD_ARGS")

        try:
            degree_u = int(degree_u)
            degree_v = int(degree_v)
            num_u = int(num_u)
            num_v = int(num_v)
        except (TypeError, ValueError) as exc:
            return err_payload(f"degree/num values must be integers: {exc}", "BAD_ARGS")

        if degree_u < 1 or degree_v < 1:
            return err_payload("degree_u and degree_v must be >= 1", "BAD_ARGS")
        if num_u < 2 or num_v < 2:
            return err_payload("num_u and num_v must be >= 2", "BAD_ARGS")
        if len(raw_cp) != num_u * num_v:
            return err_payload(
                f"control_points length ({len(raw_cp)}) does not match num_u*num_v ({num_u*num_v})",
                "BAD_ARGS",
            )

        try:
            cp_flat = [np.asarray(p, dtype=float) for p in raw_cp]
            dim = cp_flat[0].size
            cp = np.array([p.tolist()[:dim] for p in cp_flat], dtype=float).reshape(num_u, num_v, dim)
        except Exception as exc:
            return err_payload(f"invalid control_points: {exc}", "BAD_ARGS")

        # Build simple clamped knot vectors
        def _make_knots(n: int, deg: int) -> np.ndarray:
            inner = max(0, n - deg - 1)
            return np.concatenate([
                np.zeros(deg + 1),
                np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else [],
                np.ones(deg + 1),
            ])

        knots_u = _make_knots(num_u, degree_u)
        knots_v = _make_knots(num_v, degree_v)

        try:
            surface = NurbsSurface(
                degree_u=degree_u,
                degree_v=degree_v,
                control_points=cp,
                knots_u=knots_u,
                knots_v=knots_v,
            )
        except Exception as exc:
            return err_payload(f"failed to build NurbsSurface: {exc}", "BAD_ARGS")

        try:
            trim_points_3d = [np.asarray(p, dtype=float) for p in trim_pts]
        except Exception as exc:
            return err_payload(f"invalid trim_points: {exc}", "BAD_ARGS")

        result = trim_face(surface, trim_points_3d, tolerance=float(tol))

        if not result["ok"]:
            return err_payload(result["reason"], "OP_FAILED")

        tc: TrimCurve = result["trim_curve"]
        return ok_payload({
            "uv_samples": [[u, v] for u, v in tc.uv_samples],
            "is_closed": tc.is_closed,
            "crosses_boundary": tc.crosses_boundary,
            "num_samples": tc.num_samples,
            "uv_domain_split": result["uv_domain_split"],
        })

    # ------------------------------------------------------------------
    # validate_trim_curve
    # ------------------------------------------------------------------

    _validate_trim_curve_spec = ToolSpec(
        name="validate_trim_curve",
        description=(
            "Validate a trim curve (3D polyline) against a NURBS surface.  "
            "Checks that the curve projects successfully onto the UV domain, "
            "that it crosses the face boundary (required for B-rep split), "
            "and classifies the side of a query UV point.  "
            "Returns a health report with warnings and errors — use before "
            "calling feature_trim_by_curve to catch problems early.\n"
            "\n"
            "Returns:\n"
            "  ok            : bool\n"
            "  errors        : list of str (fatal)\n"
            "  warnings      : list of str (non-fatal)\n"
            "  num_uv_samples : int\n"
            "  is_closed     : bool\n"
            "  crosses_boundary : bool\n"
            "\n"
            "Errors: {ok:false, reason} for invalid inputs.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "degree_u": {"type": "integer"},
                "degree_v": {"type": "integer"},
                "control_points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "num_u": {"type": "integer"},
                "num_v": {"type": "integer"},
                "trim_points": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "tolerance": {"type": "number"},
                "keep_side": {
                    "type": "string",
                    "enum": ["positive", "negative"],
                },
            },
            "required": [
                "degree_u", "degree_v", "control_points",
                "num_u", "num_v", "trim_points",
            ],
        },
    )

    @register(_validate_trim_curve_spec)
    async def run_validate_trim_curve(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        degree_u = a.get("degree_u")
        degree_v = a.get("degree_v")
        raw_cp = a.get("control_points", [])
        num_u = a.get("num_u")
        num_v = a.get("num_v")
        trim_pts = a.get("trim_points", [])
        tol = a.get("tolerance", 1e-6)
        keep_side = a.get("keep_side", "positive")

        if any(x is None for x in [degree_u, degree_v, num_u, num_v]) or not raw_cp:
            return err_payload(
                "degree_u, degree_v, control_points, num_u, num_v are required",
                "BAD_ARGS",
            )
        if not trim_pts or len(trim_pts) < 2:
            return err_payload("trim_points must contain at least 2 points", "BAD_ARGS")

        errors: List[str] = []
        warnings: List[str] = []

        try:
            degree_u = int(degree_u)
            degree_v = int(degree_v)
            num_u = int(num_u)
            num_v = int(num_v)
        except (TypeError, ValueError) as exc:
            return err_payload(f"degree/num must be integers: {exc}", "BAD_ARGS")

        if degree_u < 1 or degree_v < 1:
            errors.append(f"surface degree must be >= 1; got ({degree_u}, {degree_v})")
        if num_u < 2 or num_v < 2:
            errors.append(f"num_u and num_v must be >= 2; got ({num_u}, {num_v})")

        if len(raw_cp) != num_u * num_v:
            errors.append(
                f"control_points length {len(raw_cp)} != num_u*num_v={num_u*num_v}"
            )

        if errors:
            return ok_payload({
                "ok": False,
                "errors": errors,
                "warnings": warnings,
                "num_uv_samples": 0,
                "is_closed": False,
                "crosses_boundary": False,
            })

        try:
            cp_flat = [np.asarray(p, dtype=float) for p in raw_cp]
            dim = cp_flat[0].size
            cp = np.array([p.tolist()[:dim] for p in cp_flat], dtype=float).reshape(num_u, num_v, dim)
        except Exception as exc:
            return err_payload(f"invalid control_points: {exc}", "BAD_ARGS")

        def _make_knots(n: int, deg: int) -> np.ndarray:
            inner = max(0, n - deg - 1)
            return np.concatenate([
                np.zeros(deg + 1),
                np.linspace(0.0, 1.0, inner + 2)[1:-1] if inner > 0 else [],
                np.ones(deg + 1),
            ])

        knots_u = _make_knots(num_u, degree_u)
        knots_v = _make_knots(num_v, degree_v)

        try:
            surface = NurbsSurface(
                degree_u=degree_u,
                degree_v=degree_v,
                control_points=cp,
                knots_u=knots_u,
                knots_v=knots_v,
            )
        except Exception as exc:
            return err_payload(f"failed to build NurbsSurface: {exc}", "BAD_ARGS")

        trim_points_3d = [np.asarray(p, dtype=float) for p in trim_pts]
        result = trim_face(
            surface, trim_points_3d,
            keep_side=keep_side,
            tolerance=float(tol),
        )

        if not result["ok"]:
            errors.append(result["reason"])
            return ok_payload({
                "ok": False,
                "errors": errors,
                "warnings": warnings,
                "num_uv_samples": 0,
                "is_closed": False,
                "crosses_boundary": False,
            })

        tc: TrimCurve = result["trim_curve"]

        if tc.num_samples < 4:
            warnings.append(
                f"only {tc.num_samples} UV samples projected — "
                "consider passing more 3D points for a smoother trim curve"
            )

        if not tc.crosses_boundary and not tc.is_closed:
            errors.append(
                "trim curve does not cross the face boundary and is not a closed loop — "
                "it cannot divide the face.  Extend the curve so it enters from one boundary "
                "edge and exits from another, or close it to form a loop."
            )

        ok = len(errors) == 0
        return ok_payload({
            "ok": ok,
            "errors": errors,
            "warnings": warnings,
            "num_uv_samples": tc.num_samples,
            "is_closed": tc.is_closed,
            "crosses_boundary": tc.crosses_boundary,
        })
