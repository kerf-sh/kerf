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
    """Newton iteration to find (u, v) such that surface(u, v) is closest to point.

    Returns (u, v) on convergence, or None if the iteration diverges or leaves
    the UV domain.
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
