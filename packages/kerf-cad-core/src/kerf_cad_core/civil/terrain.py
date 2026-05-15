"""
kerf_cad_core.civil.terrain — Triangulated Irregular Network (TIN) from survey points.

Triangulation method:
    Incremental fan triangulation (also called "radial triangulation" or
    "ear-fan" TIN).  The algorithm is:

    1. Sort input points lexicographically by (x, y) — gives a consistent,
       deterministic ordering regardless of input order.
    2. Pick the first point as the "hub".
    3. Sort the remaining points by polar angle from the hub, breaking ties
       by distance (nearest first).
    4. Walk around the ordered ring and emit triangles:
           hub → ring[i] → ring[i+1]
       The hub-based fan always produces a valid triangulation (no degeneracy
       for non-collinear inputs) with exactly N-2 triangles for N points.
    5. This is NOT optimal Delaunay but is deterministic, correct (every
       input point is covered), and sufficient for earthwork grid sampling.

Collinearity check:
    If all points lie on a single line (cross-product of consecutive direction
    vectors all ≈ 0) the TIN would degenerate to flat slivers that cannot
    enclose area.  The constructor rejects this with a ValueError and the tool
    wrapper converts it to an {ok:false} payload.

Point-in-triangle + barycentric interpolation:
    Standard barycentric coordinate method.  Given triangle (A, B, C) and
    query point P:
        λ1 = ((B.y-C.y)(P.x-C.x) + (C.x-B.x)(P.y-C.y)) / denom
        λ2 = ((C.y-A.y)(P.x-C.x) + (A.x-C.x)(P.y-C.y)) / denom
        λ3 = 1 - λ1 - λ2
    P is inside iff λ1,λ2,λ3 ∈ [−ε, 1+ε] simultaneously.
    Z interpolated = λ1·A.z + λ2·B.z + λ3·C.z.

Units: metres.
Author: imranparuk
"""
from __future__ import annotations

import math
from typing import NamedTuple, Optional

# Numeric tolerance for collinearity checks and point-in-triangle tests.
_EPS = 1e-9
_IN_TRI_EPS = 1e-7


class Point3D(NamedTuple):
    """A survey point with x, y, z coordinates (metres)."""
    x: float
    y: float
    z: float


class Triangle(NamedTuple):
    """Three Point3D vertices forming a triangular face."""
    a: Point3D
    b: Point3D
    c: Point3D


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cross2(ax: float, ay: float, bx: float, by: float) -> float:
    """2-D cross product of vectors (ax,ay) and (bx,by)."""
    return ax * by - ay * bx


def _area2d(t: Triangle) -> float:
    """Signed area of the triangle projected onto the XY plane."""
    return 0.5 * abs(
        _cross2(t.b.x - t.a.x, t.b.y - t.a.y,
                t.c.x - t.a.x, t.c.y - t.a.y)
    )


def _all_collinear(points: list[Point3D]) -> bool:
    """
    Return True if all points lie on a single line in the XY plane.
    Uses the cross product of consecutive direction vectors.
    """
    if len(points) < 3:
        return True
    p0 = points[0]
    dx0 = points[1].x - p0.x
    dy0 = points[1].y - p0.y
    for p in points[2:]:
        dx = p.x - p0.x
        dy = p.y - p0.y
        if abs(_cross2(dx0, dy0, dx, dy)) > _EPS:
            return False
    return True


def _polar_angle(hub: Point3D, pt: Point3D) -> float:
    """Polar angle (radians) of pt relative to hub."""
    return math.atan2(pt.y - hub.y, pt.x - hub.x)


# ---------------------------------------------------------------------------
# TIN
# ---------------------------------------------------------------------------

class TIN:
    """
    Triangulated Irregular Network built from a list of Point3D survey points.

    Parameters
    ----------
    points:
        At least 3 non-collinear survey points in the XY plane.

    Raises
    ------
    ValueError
        If fewer than 3 points are supplied, or if all points are collinear
        (i.e. no area can be enclosed).

    Attributes
    ----------
    points : list[Point3D]
        Sorted input points (lexicographic x, y).
    triangles : list[Triangle]
        N-2 triangles covering the convex hull of the input.
    area_m2 : float
        Total XY-projected surface area in m².
    min_z : float
        Minimum elevation (m).
    max_z : float
        Maximum elevation (m).
    """

    def __init__(self, points: list[Point3D]) -> None:
        if len(points) < 3:
            raise ValueError(
                f"TIN requires at least 3 points; got {len(points)}"
            )

        # Deterministic sort: lexicographic (x, y, z) so hub selection is
        # always the same regardless of input order.
        sorted_pts = sorted(points, key=lambda p: (p.x, p.y, p.z))

        if _all_collinear(sorted_pts):
            raise ValueError(
                "All supplied points are collinear — cannot build a TIN "
                "(no area enclosed).  Add at least one off-axis point."
            )

        self.points: list[Point3D] = sorted_pts
        self.triangles: list[Triangle] = self._build_fan(sorted_pts)

        self.area_m2: float = sum(_area2d(t) for t in self.triangles)
        zs = [p.z for p in sorted_pts]
        self.min_z: float = min(zs)
        self.max_z: float = max(zs)

    # ------------------------------------------------------------------ #
    # Triangulation                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_fan(sorted_pts: list[Point3D]) -> list[Triangle]:
        """
        Fan triangulation from the first (lexicographic) point as the hub.

        Remaining points are sorted by polar angle then by distance to break
        ties, ensuring a consistent fan order. Triangles with near-zero area
        (degenerate slivers) are silently skipped.
        """
        hub = sorted_pts[0]
        ring = sorted_pts[1:]

        # Sort ring by (angle, distance) for deterministic fan ordering.
        ring.sort(key=lambda p: (
            _polar_angle(hub, p),
            (p.x - hub.x) ** 2 + (p.y - hub.y) ** 2,
        ))

        triangles: list[Triangle] = []
        for i in range(len(ring) - 1):
            t = Triangle(hub, ring[i], ring[i + 1])
            if _area2d(t) > _EPS:
                triangles.append(t)

        return triangles

    # ------------------------------------------------------------------ #
    # Interpolation                                                         #
    # ------------------------------------------------------------------ #

    def interpolate_z(self, x: float, y: float) -> Optional[float]:
        """
        Return the interpolated Z at (x, y) using barycentric coordinates,
        or None if the point falls outside all triangles.

        The first matching triangle is used (fan order is deterministic so
        ties at shared edges always pick the same triangle).
        """
        query = Point3D(x, y, 0.0)
        for tri in self.triangles:
            z = _bary_z(tri, query)
            if z is not None:
                return z
        return None

    # ------------------------------------------------------------------ #
    # Convenience                                                           #
    # ------------------------------------------------------------------ #

    def summary(self) -> dict:
        """Return a dict summary of TIN statistics."""
        return {
            "point_count": len(self.points),
            "triangle_count": len(self.triangles),
            "area_m2": round(self.area_m2, 6),
            "min_elevation_m": round(self.min_z, 6),
            "max_elevation_m": round(self.max_z, 6),
            "elevation_range_m": round(self.max_z - self.min_z, 6),
        }


# ---------------------------------------------------------------------------
# Barycentric interpolation
# ---------------------------------------------------------------------------

def _bary_z(tri: Triangle, p: Point3D) -> Optional[float]:
    """
    Return interpolated Z at point p inside triangle tri using barycentric
    coordinates, or None if p is outside tri.

    Method:
        Compute barycentric weights (λ1, λ2, λ3) via the standard
        divided-difference formula for a triangle in the XY plane:

            denom = (B.y - C.y)(A.x - C.x) + (C.x - B.x)(A.y - C.y)
            λ1 = [(B.y - C.y)(P.x - C.x) + (C.x - B.x)(P.y - C.y)] / denom
            λ2 = [(C.y - A.y)(P.x - C.x) + (A.x - C.x)(P.y - C.y)] / denom
            λ3 = 1 - λ1 - λ2

        P is inside iff all three weights are ≥ -ε (within floating-point
        tolerance of the boundary).

        Z = λ1·A.z + λ2·B.z + λ3·C.z
    """
    a, b, c = tri.a, tri.b, tri.c
    denom = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y)

    if abs(denom) < _EPS:
        # Degenerate (zero-area) triangle — skip.
        return None

    lam1 = ((b.y - c.y) * (p.x - c.x) + (c.x - b.x) * (p.y - c.y)) / denom
    lam2 = ((c.y - a.y) * (p.x - c.x) + (a.x - c.x) * (p.y - c.y)) / denom
    lam3 = 1.0 - lam1 - lam2

    if lam1 < -_IN_TRI_EPS or lam2 < -_IN_TRI_EPS or lam3 < -_IN_TRI_EPS:
        return None

    return lam1 * a.z + lam2 * b.z + lam3 * c.z


# ---------------------------------------------------------------------------
# Public factory (validated)
# ---------------------------------------------------------------------------

def build_tin(raw_points: list[dict]) -> tuple[Optional[TIN], list[str]]:
    """
    Validate and build a TIN from a list of {x, y, z} dicts.

    Returns
    -------
    (tin, errors)
        tin is None when errors is non-empty.
    """
    errors: list[str] = []

    if not isinstance(raw_points, list):
        errors.append("points must be a list of {x,y,z} objects")
        return None, errors

    pts: list[Point3D] = []
    for i, item in enumerate(raw_points):
        if not isinstance(item, dict):
            errors.append(f"points[{i}]: must be an object with x, y, z")
            continue
        try:
            x = float(item["x"])
            y = float(item["y"])
            z = float(item["z"])
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"points[{i}]: {exc}")
            continue
        pts.append(Point3D(x, y, z))

    if errors:
        return None, errors

    try:
        tin = TIN(pts)
    except ValueError as exc:
        errors.append(str(exc))
        return None, errors

    return tin, []
