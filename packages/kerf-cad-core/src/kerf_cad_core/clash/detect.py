"""
kerf_cad_core.clash.detect — Broad-phase + narrow-phase clash detection.

Algorithm
---------
1. Broad phase: axis-aligned bounding box (AABB) overlap test on world-space
   AABBs derived from each component's local bbox transformed by its 4x4
   matrix.  Pairs that don't overlap in AABB cannot clash → early reject.

2. Narrow phase (per overlapping pair):
   a. Oriented bounding box (OBB) separating-axis theorem (SAT) — if the OBBs
      don't overlap the pair is clear.  If they do, estimate penetration depth
      along the minimum-overlap axis.
   b. If triangle meshes are supplied, fall back to triangle/triangle
      intersection for the final hard/clearance decision.
   c. Coincident check: if both bbox centres are within COINCIDENT_TOL the
      pair is flagged as COINCIDENT (supersedes HARD).

Data model
----------
ComponentShape — lightweight descriptor:
    instance_id  str           unique instance identifier
    transform    list[float]   16-float row-major 4x4 matrix (world placement)
    bbox_min     tuple[float, float, float]   local-frame AABB min corner (mm)
    bbox_max     tuple[float, float, float]   local-frame AABB max corner (mm)
    triangles    list[tuple[tuple,tuple,tuple]] | None
                 optional list of (v0, v1, v2) in local frame for narrow-phase

clash_detect(components, min_clearance) -> dict
    Always returns a dict; never raises.

Output dict
-----------
{
  "ok": bool,
  "clashes": [
    {
      "a": <instance_id>,
      "b": <instance_id>,
      "type": "hard" | "clearance" | "coincident",
      "depth": float,   # penetration depth (>0 hard) or gap (<=0 clearance)
    },
    ...
  ],
  "errors": [str, ...]   # non-fatal parse/input warnings
}

Units: mm throughout.
Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any

# Re-use the 4x4 matrix helpers from the assembly layer — no duplication.
from kerf_cad_core.assembly.model import (
    _identity,
    _transform_point,
    _transform_vector,
    _validate_transform,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Two components whose bbox centres are within this distance (mm) are
#: considered coincident/duplicate placements.
COINCIDENT_TOL: float = 1e-4

#: Minimum OBB half-extent — prevents degenerate zero-size boxes.
_MIN_HALF: float = 1e-9


# ---------------------------------------------------------------------------
# ClashType
# ---------------------------------------------------------------------------

class ClashType:
    """String constants for clash category — not an enum so JSON-serialisable directly."""
    HARD = "hard"
    CLEARANCE = "clearance"
    COINCIDENT = "coincident"


# ---------------------------------------------------------------------------
# ClashRecord
# ---------------------------------------------------------------------------

class ClashRecord:
    """
    A single pairwise clash event.

    Attributes
    ----------
    a, b    : instance_id of the two components
    type    : ClashType constant
    depth   : penetration depth in mm (positive = interpenetrating for HARD/COINCIDENT,
              negative = separation for CLEARANCE)
    """

    __slots__ = ("a", "b", "type", "depth")

    def __init__(self, a: str, b: str, clash_type: str, depth: float) -> None:
        self.a = a
        self.b = b
        self.type = clash_type
        self.depth = depth

    def to_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "type": self.type, "depth": self.depth}

    def __repr__(self) -> str:  # pragma: no cover
        return f"ClashRecord({self.a!r}, {self.b!r}, {self.type!r}, depth={self.depth:.4f})"


# ---------------------------------------------------------------------------
# ComponentShape
# ---------------------------------------------------------------------------

class ComponentShape:
    """
    Geometric descriptor for one placed component instance.

    Parameters
    ----------
    instance_id : str
    transform   : 16-float row-major 4x4 matrix; None → identity
    bbox_min    : local-frame AABB min corner (x, y, z) in mm
    bbox_max    : local-frame AABB max corner (x, y, z) in mm
    triangles   : optional list of triangles [(v0,v1,v2), ...] in local frame
                  for narrow-phase mesh intersection
    """

    __slots__ = ("instance_id", "transform", "bbox_min", "bbox_max", "triangles")

    def __init__(
        self,
        instance_id: str,
        transform: list[float] | None = None,
        bbox_min: tuple[float, float, float] = (0.0, 0.0, 0.0),
        bbox_max: tuple[float, float, float] = (1.0, 1.0, 1.0),
        triangles: list[tuple] | None = None,
    ) -> None:
        if not instance_id or not str(instance_id).strip():
            raise ValueError("instance_id must be a non-empty string")
        self.instance_id: str = str(instance_id).strip()
        self.transform: list[float] = _validate_transform(transform)
        self.bbox_min: tuple[float, float, float] = tuple(float(v) for v in bbox_min)  # type: ignore[assignment]
        self.bbox_max: tuple[float, float, float] = tuple(float(v) for v in bbox_max)  # type: ignore[assignment]
        self.triangles: list[tuple] | None = triangles


# ---------------------------------------------------------------------------
# Vector helpers (all pure-Python, no numpy)
# ---------------------------------------------------------------------------

def _dot(a: tuple, b: tuple) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a: tuple, b: tuple) -> tuple:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: tuple, b: tuple) -> tuple:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: tuple, s: float) -> tuple:
    return (a[0] * s, a[1] * s, a[2] * s)


def _cross(a: tuple, b: tuple) -> tuple:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(v: tuple) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _normalize(v: tuple) -> tuple:
    n = _norm(v)
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


# ---------------------------------------------------------------------------
# OBB construction from ComponentShape
# ---------------------------------------------------------------------------

class _OBB:
    """Oriented bounding box derived from a ComponentShape's local bbox + transform."""

    __slots__ = ("centre", "axes", "half_extents")

    def __init__(self, shape: ComponentShape) -> None:
        T = shape.transform
        lo = shape.bbox_min
        hi = shape.bbox_max

        # Local-frame centre
        lc = (
            (lo[0] + hi[0]) * 0.5,
            (lo[1] + hi[1]) * 0.5,
            (lo[2] + hi[2]) * 0.5,
        )
        # Half extents in local frame
        he = (
            max((hi[0] - lo[0]) * 0.5, _MIN_HALF),
            max((hi[1] - lo[1]) * 0.5, _MIN_HALF),
            max((hi[2] - lo[2]) * 0.5, _MIN_HALF),
        )

        # World-space centre = T * lc
        self.centre: tuple = _transform_point(T, lc)

        # World-space axes = rotation part of T applied to local unit axes
        # (strip translation by using _transform_vector)
        ax = _transform_vector(T, (1.0, 0.0, 0.0))
        ay = _transform_vector(T, (0.0, 1.0, 0.0))
        az = _transform_vector(T, (0.0, 0.0, 1.0))

        # Scale half-extents by the axis lengths (handles uniform scale in T)
        lx = _norm(ax)
        ly = _norm(ay)
        lz = _norm(az)

        # Normalised axes
        self.axes: tuple = (
            _normalize(ax),
            _normalize(ay),
            _normalize(az),
        )
        # Scaled half-extents
        self.half_extents: tuple = (
            he[0] * (lx if lx > 1e-12 else 1.0),
            he[1] * (ly if ly > 1e-12 else 1.0),
            he[2] * (lz if lz > 1e-12 else 1.0),
        )


def _world_aabb(shape: ComponentShape) -> tuple[tuple, tuple]:
    """Compute world-space AABB by transforming all 8 bbox corners."""
    T = shape.transform
    lo = shape.bbox_min
    hi = shape.bbox_max
    corners = [
        _transform_point(T, (lo[0], lo[1], lo[2])),
        _transform_point(T, (hi[0], lo[1], lo[2])),
        _transform_point(T, (lo[0], hi[1], lo[2])),
        _transform_point(T, (hi[0], hi[1], lo[2])),
        _transform_point(T, (lo[0], lo[1], hi[2])),
        _transform_point(T, (hi[0], lo[1], hi[2])),
        _transform_point(T, (lo[0], hi[1], hi[2])),
        _transform_point(T, (hi[0], hi[1], hi[2])),
    ]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    zs = [c[2] for c in corners]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _aabb_overlap(a_min, a_max, b_min, b_max) -> bool:
    """Return True if two AABBs overlap."""
    return (
        a_min[0] <= b_max[0] and a_max[0] >= b_min[0] and
        a_min[1] <= b_max[1] and a_max[1] >= b_min[1] and
        a_min[2] <= b_max[2] and a_max[2] >= b_min[2]
    )


def _aabb_gap(a_min, a_max, b_min, b_max) -> float:
    """
    Minimum gap between two AABBs (negative means overlap).
    This is a conservative lower bound for clearance checking.
    """
    dx = max(a_min[0] - b_max[0], b_min[0] - a_max[0], 0.0)
    dy = max(a_min[1] - b_max[1], b_min[1] - a_max[1], 0.0)
    dz = max(a_min[2] - b_max[2], b_min[2] - a_max[2], 0.0)
    if dx > 0 or dy > 0 or dz > 0:
        # Separated: return Euclidean gap
        return math.sqrt(dx * dx + dy * dy + dz * dz)
    # Overlapping: return negative
    ox = min(a_max[0], b_max[0]) - max(a_min[0], b_min[0])
    oy = min(a_max[1], b_max[1]) - max(a_min[1], b_min[1])
    oz = min(a_max[2], b_max[2]) - max(a_min[2], b_min[2])
    return -min(ox, oy, oz)


# ---------------------------------------------------------------------------
# OBB SAT (Separating Axis Theorem)
# ---------------------------------------------------------------------------

def _project_obb(obb: "_OBB", axis: tuple) -> tuple[float, float]:
    """Project OBB onto *axis*, return (min, max) scalar interval."""
    c = _dot(obb.centre, axis)
    r = (
        abs(_dot(obb.axes[0], axis)) * obb.half_extents[0] +
        abs(_dot(obb.axes[1], axis)) * obb.half_extents[1] +
        abs(_dot(obb.axes[2], axis)) * obb.half_extents[2]
    )
    return c - r, c + r


def _intervals_overlap(a: tuple, b: tuple) -> float:
    """
    Return overlap amount (positive) or gap (negative) between two 1-D intervals.
    """
    lo = max(a[0], b[0])
    hi = min(a[1], b[1])
    return hi - lo  # positive = overlap, negative = gap


def _obb_sat(obb_a: "_OBB", obb_b: "_OBB") -> tuple[bool, float]:
    """
    Separating-axis theorem for two OBBs.

    Returns
    -------
    (overlapping: bool, min_overlap: float)
        min_overlap is the penetration depth along the minimum-overlap axis
        when overlapping=True, or the smallest gap when overlapping=False.
    """
    # 15 candidate axes: 3 face normals of A, 3 face normals of B,
    # 9 cross-products of edge directions.
    axes: list[tuple] = []
    axes.extend(obb_a.axes)
    axes.extend(obb_b.axes)
    for i in range(3):
        for j in range(3):
            ax = _cross(obb_a.axes[i], obb_b.axes[j])
            n = _norm(ax)
            if n > 1e-10:
                axes.append((ax[0] / n, ax[1] / n, ax[2] / n))

    min_overlap = float("inf")
    for axis in axes:
        if _norm(axis) < 1e-10:
            continue
        ia = _project_obb(obb_a, axis)
        ib = _project_obb(obb_b, axis)
        overlap = _intervals_overlap(ia, ib)
        if overlap < 0:
            # Separating axis found — no collision
            return False, -overlap  # return gap magnitude
        if overlap < min_overlap:
            min_overlap = overlap

    return True, min_overlap


# ---------------------------------------------------------------------------
# Triangle/triangle intersection (Möller–Trumbore style, pure Python)
# ---------------------------------------------------------------------------

def _tri_tri_intersect(
    p0: tuple, p1: tuple, p2: tuple,
    q0: tuple, q1: tuple, q2: tuple,
) -> bool:
    """
    Detect whether two triangles (p0,p1,p2) and (q0,q1,q2) in 3-D intersect.

    Uses interval overlap on the line of intersection between the two
    triangle planes (Möller 1997 style).  Handles coplanar case via 2-D SAT.
    Returns True if they share any interior, edge, or vertex point.
    """
    _EPS = 1e-8

    def _plane_of(a, b, c):
        n = _cross(_sub(b, a), _sub(c, a))
        return n, -_dot(n, a)

    def _signed_dists(n, d, pts):
        return [_dot(n, p) + d for p in pts]

    def _interval_on_line(L, verts, dists):
        """
        Return the [min,max] interval of the triangle's intersection
        with the line L, parameterised as t = dot(L, point).
        The intersection is defined by edges that straddle sign changes.
        """
        n = len(verts)
        interval = []
        for i in range(n):
            j = (i + 1) % n
            di, dj = dists[i], dists[j]
            vi, vj = verts[i], verts[j]
            # Include vertices on the plane
            if abs(di) <= _EPS:
                interval.append(_dot(L, vi))
            # Edge straddles the plane
            if (di > _EPS and dj < -_EPS) or (di < -_EPS and dj > _EPS):
                t_frac = di / (di - dj)
                pt = _add(vi, _scale(_sub(vj, vi), t_frac))
                interval.append(_dot(L, pt))
        return interval

    # ── Test 1: reject by plane of triangle P ─────────────────────────────
    n1, d1 = _plane_of(p0, p1, p2)
    dq = _signed_dists(n1, d1, [q0, q1, q2])
    if all(v > _EPS for v in dq) or all(v < -_EPS for v in dq):
        return False

    # ── Test 2: reject by plane of triangle Q ─────────────────────────────
    n2, d2 = _plane_of(q0, q1, q2)
    dp = _signed_dists(n2, d2, [p0, p1, p2])
    if all(v > _EPS for v in dp) or all(v < -_EPS for v in dp):
        return False

    # ── Intersection line ─────────────────────────────────────────────────
    L = _cross(n1, n2)
    if _norm(L) < _EPS:
        # Coplanar — use 2-D SAT
        return _coplanar_tri_intersect(p0, p1, p2, q0, q1, q2, n1)

    # ── Compute intervals on L ────────────────────────────────────────────
    int_p = _interval_on_line(L, [p0, p1, p2], dp)
    int_q = _interval_on_line(L, [q0, q1, q2], dq)

    if len(int_p) < 2 or len(int_q) < 2:
        # One or both triangles graze the plane — check vertex containment
        if len(int_p) == 1 and len(int_q) >= 2:
            t = int_p[0]
            return min(int_q) - _EPS <= t <= max(int_q) + _EPS
        if len(int_q) == 1 and len(int_p) >= 2:
            t = int_q[0]
            return min(int_p) - _EPS <= t <= max(int_p) + _EPS
        if len(int_p) == 1 and len(int_q) == 1:
            return abs(int_p[0] - int_q[0]) < _EPS
        return False

    p_lo, p_hi = min(int_p), max(int_p)
    q_lo, q_hi = min(int_q), max(int_q)

    return p_lo <= q_hi + _EPS and q_lo <= p_hi + _EPS


def _coplanar_tri_intersect(
    p0, p1, p2, q0, q1, q2, normal
) -> bool:
    """2-D SAT for two coplanar triangles projected onto their shared plane."""
    # Pick the dominant axis to drop and project to 2D
    nx, ny, nz = abs(normal[0]), abs(normal[1]), abs(normal[2])
    if nz >= nx and nz >= ny:
        def _p2(v): return (v[0], v[1])
    elif ny >= nx:
        def _p2(v): return (v[0], v[2])
    else:
        def _p2(v): return (v[1], v[2])

    def _project_axis_2d(pts, axis):
        ds = [pt[0] * axis[0] + pt[1] * axis[1] for pt in pts]
        return min(ds), max(ds)

    tris_p = [_p2(p0), _p2(p1), _p2(p2)]
    tris_q = [_p2(q0), _p2(q1), _p2(q2)]

    for tri in [tris_p, tris_q]:
        for i in range(3):
            a = tri[i]
            b = tri[(i + 1) % 3]
            edge = (b[0] - a[0], b[1] - a[1])
            axis = (-edge[1], edge[0])  # perpendicular
            n = math.sqrt(axis[0] ** 2 + axis[1] ** 2)
            if n < 1e-12:
                continue
            axis = (axis[0] / n, axis[1] / n)
            lo_p, hi_p = _project_axis_2d(tris_p, axis)
            lo_q, hi_q = _project_axis_2d(tris_q, axis)
            if hi_p < lo_q - 1e-10 or hi_q < lo_p - 1e-10:
                return False
    return True


def _mesh_intersect(
    tris_a: list[tuple], T_a: list[float],
    tris_b: list[tuple], T_b: list[float],
) -> bool:
    """
    Return True if any triangle from mesh A intersects any triangle from mesh B.
    Triangles are given in local frame; T_a and T_b are their world transforms.
    """
    def _world_tri(tri, T):
        return (
            _transform_point(T, tri[0]),
            _transform_point(T, tri[1]),
            _transform_point(T, tri[2]),
        )

    for ta in tris_a:
        wa = _world_tri(ta, T_a)
        for tb in tris_b:
            wb = _world_tri(tb, T_b)
            if _tri_tri_intersect(wa[0], wa[1], wa[2], wb[0], wb[1], wb[2]):
                return True
    return False


# ---------------------------------------------------------------------------
# Coincident detection
# ---------------------------------------------------------------------------

def _centres_coincident(obb_a: "_OBB", obb_b: "_OBB") -> bool:
    d = _norm(_sub(obb_a.centre, obb_b.centre))
    return d < COINCIDENT_TOL


# ---------------------------------------------------------------------------
# Clearance gap between two OBBs (approximate via vertex sampling)
# ---------------------------------------------------------------------------

def _obb_corners(obb: "_OBB") -> list[tuple]:
    """Return the 8 corner points of an OBB in world space."""
    c = obb.centre
    a0, a1, a2 = obb.axes
    h0, h1, h2 = obb.half_extents
    corners = []
    for s0 in (-1, 1):
        for s1 in (-1, 1):
            for s2 in (-1, 1):
                corner = (
                    c[0] + s0 * h0 * a0[0] + s1 * h1 * a1[0] + s2 * h2 * a2[0],
                    c[1] + s0 * h0 * a0[1] + s1 * h1 * a1[1] + s2 * h2 * a2[1],
                    c[2] + s0 * h0 * a0[2] + s1 * h1 * a1[2] + s2 * h2 * a2[2],
                )
                corners.append(corner)
    return corners


def _point_to_obb_sq_dist(pt: tuple, obb: "_OBB") -> float:
    """
    Squared distance from a point to the closest point on/in an OBB.
    Returns 0.0 if the point is inside the OBB.
    """
    d = _sub(pt, obb.centre)
    sq_dist = 0.0
    for i in range(3):
        proj = _dot(d, obb.axes[i])
        half = obb.half_extents[i]
        excess = abs(proj) - half
        if excess > 0:
            sq_dist += excess * excess
    return sq_dist


def _obb_clearance_gap(obb_a: "_OBB", obb_b: "_OBB") -> float:
    """
    Estimate the minimum gap between two OBBs.

    Uses point-to-OBB distance for all 16 corner/centre samples.
    This is a conservative lower bound (may underestimate true gap) but
    is exact for the coincident/separation decision.

    Returns a positive value when separated, negative when overlapping
    (via SAT fallback).
    """
    min_sq = float("inf")
    for corner in _obb_corners(obb_a):
        sq = _point_to_obb_sq_dist(corner, obb_b)
        if sq < min_sq:
            min_sq = sq
    for corner in _obb_corners(obb_b):
        sq = _point_to_obb_sq_dist(corner, obb_a)
        if sq < min_sq:
            min_sq = sq
    # Also check centres
    sq = _point_to_obb_sq_dist(obb_a.centre, obb_b)
    if sq < min_sq:
        min_sq = sq
    sq = _point_to_obb_sq_dist(obb_b.centre, obb_a)
    if sq < min_sq:
        min_sq = sq

    if min_sq < 1e-10:
        # Overlapping or touching — use SAT to get depth
        overlapping, depth = _obb_sat(obb_a, obb_b)
        if overlapping:
            return -depth  # negative = penetration
        return 0.0
    return math.sqrt(min_sq)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def clash_detect(
    components: list[Any],
    min_clearance: float = 0.0,
) -> dict:
    """
    Detect spatial clashes between a list of component shapes.

    Parameters
    ----------
    components    : list of ComponentShape (or dicts with matching keys)
    min_clearance : minimum required gap in mm (default 0 — only hard clashes)

    Returns
    -------
    {
      "ok": bool,          # True even when clashes are found
      "clashes": [...],    # list of ClashRecord.to_dict() entries
      "errors": [...],     # non-fatal parse warnings
    }

    Never raises.
    """
    errors: list[str] = []
    clashes: list[dict] = []

    # ── Parse inputs ─────────────────────────────────────────────────────
    shapes: list[ComponentShape] = []
    if not isinstance(components, list):
        return {
            "ok": False,
            "clashes": [],
            "errors": ["components must be a list"],
        }

    for i, raw in enumerate(components):
        if isinstance(raw, ComponentShape):
            shapes.append(raw)
        elif isinstance(raw, dict):
            try:
                shapes.append(_shape_from_dict(raw))
            except Exception as exc:
                errors.append(f"components[{i}]: {exc}")
        else:
            errors.append(f"components[{i}]: expected ComponentShape or dict, got {type(raw).__name__}")

    if len(shapes) < 2:
        return {"ok": True, "clashes": [], "errors": errors}

    try:
        min_clearance = float(min_clearance)
    except (TypeError, ValueError):
        errors.append(f"min_clearance must be a number; defaulting to 0")
        min_clearance = 0.0

    # ── Pre-compute world AABBs and OBBs ────────────────────────────────
    aabbs: list[tuple[tuple, tuple]] = []
    obbs: list[_OBB] = []
    for s in shapes:
        aabbs.append(_world_aabb(s))
        obbs.append(_OBB(s))

    # ── Pairwise tests ───────────────────────────────────────────────────
    n = len(shapes)
    for i in range(n):
        for j in range(i + 1, n):
            sha, shb = shapes[i], shapes[j]
            obb_a, obb_b = obbs[i], obbs[j]
            aabb_a, aabb_b = aabbs[i], aabbs[j]

            # Step 1: Coincident bbox centres — flag and continue
            if _centres_coincident(obb_a, obb_b):
                clashes.append(ClashRecord(
                    sha.instance_id, shb.instance_id,
                    ClashType.COINCIDENT, 0.0,
                ).to_dict())
                continue

            # Step 2: AABB broad-phase reject
            aabb_gap = _aabb_gap(aabb_a[0], aabb_a[1], aabb_b[0], aabb_b[1])
            if aabb_gap > min_clearance and not _aabb_overlap(aabb_a[0], aabb_a[1], aabb_b[0], aabb_b[1]):
                # AABB gap > min_clearance: definitely clear
                continue

            # Step 3: OBB narrow phase
            if sha.triangles and shb.triangles:
                # Triangle mesh path
                intersecting = _mesh_intersect(
                    sha.triangles, sha.transform,
                    shb.triangles, shb.transform,
                )
                if intersecting:
                    # Use OBB SAT for depth estimate
                    _, depth = _obb_sat(obb_a, obb_b)
                    clashes.append(ClashRecord(
                        sha.instance_id, shb.instance_id,
                        ClashType.HARD, depth,
                    ).to_dict())
                else:
                    # Check clearance
                    gap = _obb_clearance_gap(obb_a, obb_b)
                    if gap < min_clearance:
                        clashes.append(ClashRecord(
                            sha.instance_id, shb.instance_id,
                            ClashType.CLEARANCE, gap,
                        ).to_dict())
            else:
                # OBB SAT path
                overlapping, depth = _obb_sat(obb_a, obb_b)
                if overlapping:
                    clashes.append(ClashRecord(
                        sha.instance_id, shb.instance_id,
                        ClashType.HARD, depth,
                    ).to_dict())
                else:
                    # depth here is the separation distance from SAT
                    gap = _obb_clearance_gap(obb_a, obb_b)
                    if 0.0 <= gap < min_clearance:
                        clashes.append(ClashRecord(
                            sha.instance_id, shb.instance_id,
                            ClashType.CLEARANCE, gap,
                        ).to_dict())

    return {
        "ok": True,
        "clashes": clashes,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Dict deserialisation helper
# ---------------------------------------------------------------------------

def _shape_from_dict(d: dict) -> ComponentShape:
    """Parse a ComponentShape from a plain dict (e.g. from JSON)."""
    iid = d.get("instance_id")
    if not iid:
        raise ValueError("instance_id is required")
    transform = d.get("transform")
    bbox_min = tuple(d.get("bbox_min", [0.0, 0.0, 0.0]))
    bbox_max = tuple(d.get("bbox_max", [1.0, 1.0, 1.0]))
    tris_raw = d.get("triangles")
    triangles = None
    if tris_raw is not None:
        triangles = [
            (tuple(t[0]), tuple(t[1]), tuple(t[2]))
            for t in tris_raw
        ]
    return ComponentShape(
        instance_id=iid,
        transform=transform,
        bbox_min=bbox_min,  # type: ignore[arg-type]
        bbox_max=bbox_max,  # type: ignore[arg-type]
        triangles=triangles,
    )


__all__ = [
    "COINCIDENT_TOL",
    "ClashType",
    "ClashRecord",
    "ComponentShape",
    "clash_detect",
    "_shape_from_dict",
]
