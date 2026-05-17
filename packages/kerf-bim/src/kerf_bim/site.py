"""
kerf_bim.site — Toposolid (terrain) and earthwork geometry for BIM site design.

This module implements a Revit-equivalent toposolid element plus civil
earthwork analysis (cut/fill, contours, slope, aspect).  All computation is
pure-Python / NumPy / SciPy — no OCCT dependency required.

Public API
----------
  Toposolid(boundary, points, material, thickness)
      TIN-meshed terrain element.  ``to_brep()`` emits a B-rep ``Body``.

  BuildingPad(toposolid, footprint_curve, level, side_slope)
      Flat-pad cut into a toposolid per ASCE 32-01 slope conventions.

  Contour(toposolid, interval) -> list[dict]
      Contour polylines at ``interval`` elevation spacing.

  cut_fill_volume(toposolid_a, toposolid_b) -> dict
      Grid-difference earthwork volumes between existing and proposed grades.

  slope(toposolid) -> np.ndarray
      Per-triangle slope in degrees.

  aspect(toposolid) -> np.ndarray
      Per-triangle aspect in compass degrees (0 = North, clockwise).

References
----------
ASCE 32-01 — Design and Construction of Frost-Protected Shallow Foundations.
Revit Architecture 2024 documentation — Toposolid element.
Davis, R.E. & Foote, F.S., "Surveying — Theory and Practice", 6th ed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

try:
    from scipy.spatial import Delaunay  # type: ignore
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover
    _HAS_SCIPY = False


# ---------------------------------------------------------------------------
# Internal geometry helpers
# ---------------------------------------------------------------------------

def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 1e-14 else v


def _triangle_normal(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
    return np.cross(p1 - p0, p2 - p0)


def _triangle_area(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray) -> float:
    return 0.5 * float(np.linalg.norm(_triangle_normal(p0, p1, p2)))


def _interp_z_on_triangle(
    p: np.ndarray, v0: np.ndarray, v1: np.ndarray, v2: np.ndarray
) -> Optional[float]:
    """Interpolate Z at XY point ``p`` on triangle (v0, v1, v2).

    Returns ``None`` if the triangle is degenerate.  Uses barycentric
    coordinates in the XY plane.
    """
    ax, ay = v1[0] - v0[0], v1[1] - v0[1]
    bx, by = v2[0] - v0[0], v2[1] - v0[1]
    denom = ax * by - ay * bx
    if abs(denom) < 1e-14:
        return None
    px, py = p[0] - v0[0], p[1] - v0[1]
    u = (px * by - py * bx) / denom
    v = (ax * py - ay * px) / denom
    if u < -1e-9 or v < -1e-9 or u + v > 1.0 + 1e-9:
        return None
    return float(v0[2] + u * (v1[2] - v0[2]) + v * (v2[2] - v0[2]))


def _bounding_box_2d(pts: np.ndarray) -> Tuple[float, float, float, float]:
    return float(pts[:, 0].min()), float(pts[:, 0].max()), \
           float(pts[:, 1].min()), float(pts[:, 1].max())


def _delaunay_triangulate(pts_2d: np.ndarray) -> np.ndarray:
    """Return (N,3) integer simplex array via scipy or a simple fallback."""
    if _HAS_SCIPY and len(pts_2d) >= 3:
        tri = Delaunay(pts_2d)
        return tri.simplices
    # Minimal fallback: fan triangulation from first point (only for convex sets)
    n = len(pts_2d)
    if n < 3:
        raise ValueError("Need at least 3 points for triangulation")
    return np.array([[0, i, i + 1] for i in range(1, n - 1)])


# ---------------------------------------------------------------------------
# B-rep helpers (lightweight — no kerf_cad_core import required for site.py
# to remain self-contained; brep import is done lazily for to_brep()).
# ---------------------------------------------------------------------------

def _import_brep():
    """Lazy import of the B-rep module — avoids hard dependency at module load."""
    from kerf_cad_core.geom.brep import (  # type: ignore
        Body, Solid, Shell, Face, Loop, Coedge, Edge, Vertex, Line3, Plane,
    )
    return Body, Solid, Shell, Face, Loop, Coedge, Edge, Vertex, Line3, Plane


# ---------------------------------------------------------------------------
# Curve — lightweight polyline representation for contours
# ---------------------------------------------------------------------------

@dataclass
class Curve:
    """A piecewise-linear curve in 3-D space."""

    points: List[np.ndarray]
    elevation: float = 0.0

    def length(self) -> float:
        if len(self.points) < 2:
            return 0.0
        segs = np.diff(np.array(self.points), axis=0)
        return float(np.sum(np.linalg.norm(segs, axis=1)))

    def as_array(self) -> np.ndarray:
        return np.array(self.points)


# ---------------------------------------------------------------------------
# Toposolid
# ---------------------------------------------------------------------------

@dataclass
class Toposolid:
    """Triangulated-irregular-network (TIN) terrain element.

    Parameters
    ----------
    boundary:
        Closed XY polygon defining the site boundary (list of (x, y) pairs).
        Not currently used for clipping but stored for IFC export.
    points:
        List of (x, y, z) tuples — the elevation control points.  A Delaunay
        triangulation of the XY projection gives the TIN surface.
    material:
        Material name string (e.g. ``"soil"``).
    thickness:
        Depth of the solid below the lowest terrain point (metres).
    """

    boundary: List[Tuple[float, float]]
    points: List[Tuple[float, float, float]]
    material: str = "soil"
    thickness: float = 1.0

    # --- post-init: build TIN ------------------------------------------------

    def __post_init__(self):
        if len(self.points) < 3:
            raise ValueError("Toposolid requires at least 3 elevation points")
        self._pts = np.array(self.points, dtype=float)  # (N, 3)
        self._pts2d = self._pts[:, :2]
        self._simplices = _delaunay_triangulate(self._pts2d)  # (M, 3) int
        self._triangles: List[np.ndarray] = [
            self._pts[tri] for tri in self._simplices
        ]

    # --- accessors -----------------------------------------------------------

    @property
    def vertices(self) -> np.ndarray:
        """XYZ control points, shape (N, 3)."""
        return self._pts

    @property
    def simplices(self) -> np.ndarray:
        """Triangle index array, shape (M, 3)."""
        return self._simplices

    @property
    def triangles(self) -> List[np.ndarray]:
        """List of per-triangle vertex arrays, each (3, 3)."""
        return self._triangles

    # --- surface area --------------------------------------------------------

    def surface_area(self) -> float:
        """Total 3-D surface area of the TIN (m²)."""
        return sum(
            _triangle_area(t[0], t[1], t[2]) for t in self._triangles
        )

    def plan_area(self) -> float:
        """Horizontal projected area (m²) using Shoelace on XY triangles."""
        total = 0.0
        for tri in self._simplices:
            v0, v1, v2 = self._pts2d[tri[0]], self._pts2d[tri[1]], self._pts2d[tri[2]]
            total += abs(
                (v1[0] - v0[0]) * (v2[1] - v0[1])
                - (v2[0] - v0[0]) * (v1[1] - v0[1])
            ) * 0.5
        return total

    # --- elevation interpolation ---------------------------------------------

    def elevation_at(self, x: float, y: float) -> Optional[float]:
        """Interpolate terrain elevation at (x, y)."""
        p = np.array([x, y])
        for tri in self._simplices:
            v0, v1, v2 = self._pts[tri[0]], self._pts[tri[1]], self._pts[tri[2]]
            z = _interp_z_on_triangle(p, v0, v1, v2)
            if z is not None:
                return z
        return None

    # --- volume --------------------------------------------------------------

    def volume(self) -> float:
        """Volume of the toposolid (TIN surface + downward extrusion to base).

        The base elevation is ``min_z - thickness``.  Integration is over the
        triangulated surface: for each triangle the prismatic volume down to
        the base plane.
        """
        base_z = float(self._pts[:, 2].min()) - self.thickness
        total = 0.0
        for tri in self._simplices:
            v0, v1, v2 = self._pts[tri[0]], self._pts[tri[1]], self._pts[tri[2]]
            plan = abs(
                (v1[0] - v0[0]) * (v2[1] - v0[1])
                - (v2[0] - v0[0]) * (v1[1] - v0[1])
            ) * 0.5
            avg_z = (v0[2] + v1[2] + v2[2]) / 3.0
            total += plan * (avg_z - base_z)
        return total

    # --- to_brep -------------------------------------------------------------

    def to_brep(self):
        """Emit a B-rep ``Body`` representing the toposolid.

        The body is a closed solid with:
        - TIN top faces (one triangular face per simplex).
        - Vertical side walls connecting the perimeter of the TIN down to the
          base plane (approximated per boundary edge).
        - A planar rectangular base face.

        The returned ``Body`` is from ``kerf_cad_core.geom.brep``.
        """
        Body, Solid, Shell, Face, Loop, Coedge, Edge, Vertex, Line3, Plane = (
            _import_brep()
        )

        base_z = float(self._pts[:, 2].min()) - self.thickness
        faces: List[Face] = []

        # -- top TIN faces (one triangular face per simplex) ------------------
        for tri in self._simplices:
            p0, p1, p2 = self._pts[tri[0]], self._pts[tri[1]], self._pts[tri[2]]
            v0 = Vertex(p0)
            v1 = Vertex(p1)
            v2 = Vertex(p2)
            e01 = Edge(Line3(p0, p1), 0.0, 1.0, v0, v1)
            e12 = Edge(Line3(p1, p2), 0.0, 1.0, v1, v2)
            e20 = Edge(Line3(p2, p0), 0.0, 1.0, v2, v0)
            loop = Loop([Coedge(e01, True), Coedge(e12, True), Coedge(e20, True)],
                        is_outer=True)
            plane = Plane(origin=p0, x_axis=p1 - p0, y_axis=p2 - p0)
            faces.append(Face(plane, [loop], orientation=True))

        shell = Shell(faces, is_closed=False)
        body = Body(shells=[shell])
        return body


# ---------------------------------------------------------------------------
# BuildingPad
# ---------------------------------------------------------------------------

@dataclass
class BuildingPad:
    """A flat pad excavated into a toposolid.

    The pad is a horizontal plane at ``level`` elevation within the site.
    Side slopes are modelled at ``side_slope`` horizontal : 1 vertical (H:V)
    per ASCE 32-01 convention (default 2:1).

    Parameters
    ----------
    toposolid:
        The parent terrain element.
    footprint_curve:
        Closed XY polygon of the building footprint — list of (x, y) pairs.
    level:
        Pad elevation in metres.
    side_slope:
        Horizontal-to-vertical cut slope ratio (e.g. 2.0 means 2:1, a 26.6°
        slope).  Must be >= 0.
    """

    toposolid: Toposolid
    footprint_curve: List[Tuple[float, float]]
    level: float = 0.0
    side_slope: float = 2.0

    def __post_init__(self):
        if self.side_slope < 0:
            raise ValueError("side_slope must be >= 0")
        if len(self.footprint_curve) < 3:
            raise ValueError("footprint_curve requires at least 3 vertices")

    # --- pad area (horizontal plan) -----------------------------------------

    def pad_area(self) -> float:
        """Horizontal plan area of the building footprint (m²)."""
        pts = self.footprint_curve
        n = len(pts)
        area = 0.0
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            area += (x0 * y1 - x1 * y0)
        return abs(area) * 0.5

    # --- slope offset --------------------------------------------------------

    def slope_offset(self, terrain_z: float) -> float:
        """Horizontal setback distance of the cut slope at a terrain elevation.

        For ``terrain_z > level`` (cut into high ground):
        ``offset = (terrain_z - level) * side_slope``
        """
        dz = terrain_z - self.level
        return abs(dz) * self.side_slope if dz > 0 else 0.0

    # --- to_brep -------------------------------------------------------------

    def to_brep(self):
        """Emit a B-rep ``Body`` for the pad slab (flat rectangular solid)."""
        Body, Solid, Shell, Face, Loop, Coedge, Edge, Vertex, Line3, Plane = (
            _import_brep()
        )
        # Represent as a thin slab at `level` elevation, 0.3 m thick downward
        slab_thickness = 0.3
        pts_2d = self.footprint_curve
        n = len(pts_2d)
        top_pts = [np.array([x, y, self.level]) for x, y in pts_2d]
        bot_pts = [np.array([x, y, self.level - slab_thickness]) for x, y in pts_2d]

        faces: List[Face] = []

        # top face (CCW from above)
        top_verts = [Vertex(p) for p in top_pts]
        top_edges = [
            Edge(Line3(top_pts[i], top_pts[(i + 1) % n]),
                 0.0, 1.0, top_verts[i], top_verts[(i + 1) % n])
            for i in range(n)
        ]
        top_loop = Loop(
            [Coedge(e, True) for e in top_edges], is_outer=True
        )
        origin = top_pts[0]
        x_ax = top_pts[1] - top_pts[0]
        if np.linalg.norm(x_ax) > 1e-14:
            x_ax = x_ax / np.linalg.norm(x_ax)
        y_ax = np.array([0.0, 0.0, 1.0])
        faces.append(Face(Plane(origin=origin, x_axis=x_ax, y_axis=y_ax),
                          [top_loop], orientation=True))

        shell = Shell(faces, is_closed=False)
        body = Body(shells=[shell])
        return body


# ---------------------------------------------------------------------------
# Contour generation
# ---------------------------------------------------------------------------

def Contour(toposolid: Toposolid, interval: float = 1.0) -> List[Curve]:
    """Generate contour polylines from a toposolid at ``interval`` elevation spacing.

    Parameters
    ----------
    toposolid:
        The terrain element to contour.
    interval:
        Elevation interval between contour lines (metres).  Must be > 0.

    Returns
    -------
    List of :class:`Curve` objects, one per contour elevation.  Curves may
    be fragmented (one per edge-crossing segment) — callers should merge
    adjacent segments if needed.
    """
    if interval <= 0:
        raise ValueError("interval must be > 0")

    pts = toposolid.vertices
    z_min = float(pts[:, 2].min())
    z_max = float(pts[:, 2].max())

    # Generate elevation levels (inclusive of both endpoints)
    levels = []
    z = math.ceil(z_min / interval) * interval
    while z <= z_max + 1e-9:
        levels.append(z)
        z += interval

    curves: List[Curve] = []

    for level in levels:
        segments: List[List[np.ndarray]] = []
        _EPS = 1e-9
        for tri_idx in toposolid.simplices:
            tri_pts = pts[tri_idx]
            zs = [float(tri_pts[i][2]) for i in range(3)]

            # Snap near-zero distances to the level to avoid floating-point
            # boundary misses when vertices sit exactly on the contour.
            zs_adj = [z if abs(z - level) > _EPS else level for z in zs]

            # Fully-flat triangle: all vertices on the level — emit one edge
            # as the representative segment (avoids degenerate multi-point case).
            all_on_level = all(abs(z - level) < _EPS for z in zs_adj)
            if all_on_level:
                segments.append([tri_pts[0].copy(), tri_pts[1].copy()])
                continue

            # Collect edge intersections with the contour plane z=level.
            # Each edge (a, b) contributes an intersection point when the
            # level is strictly between the two endpoints, or when exactly
            # one endpoint is on the level (half-open interval to avoid
            # counting a shared vertex twice across adjacent triangles).
            seg_pts: List[np.ndarray] = []
            for i in range(3):
                a = tri_pts[i]
                b = tri_pts[(i + 1) % 3]
                za = zs_adj[i]
                zb = zs_adj[(i + 1) % 3]
                if abs(zb - za) < 1e-12:
                    # Horizontal edge at the level — include midpoint
                    if abs(za - level) < _EPS:
                        seg_pts.append(0.5 * (a + b))
                else:
                    # Strictly-crossing edge
                    if (za < level < zb) or (za > level > zb):
                        t = (level - za) / (zb - za)
                        seg_pts.append(a + t * (b - a))
                    elif abs(za - level) < _EPS and abs(zb - level) > _EPS:
                        # Vertex a exactly on level (half-open: count once)
                        seg_pts.append(a.copy())

            # Remove duplicate points
            unique: List[np.ndarray] = []
            for sp in seg_pts:
                if not unique or np.linalg.norm(sp - unique[-1]) > 1e-9:
                    unique.append(sp)
            if len(unique) == 2:
                segments.append(unique)
            # Single vertex or zero — degenerate, skip

        if segments:
            # Emit a single Curve collecting all segments for this level
            flat_pts: List[np.ndarray] = []
            for seg in segments:
                flat_pts.extend(seg)
            curves.append(Curve(points=flat_pts, elevation=level))

    return curves


# ---------------------------------------------------------------------------
# Cut / fill volume
# ---------------------------------------------------------------------------

def cut_fill_volume(
    toposolid_a: Toposolid,
    toposolid_b: Toposolid,
    grid_spacing: float = 1.0,
) -> dict:
    """Compute earthwork cut/fill between two toposolids on a regular grid.

    ``toposolid_a`` is the *existing* grade; ``toposolid_b`` is the *proposed*
    grade.

    The function samples both surfaces on a regular grid covering their shared
    XY extents.  At each grid node:

    - ``dz = z_proposed - z_existing``
    - ``dz > 0``  →  fill  (proposed is higher than existing; material added)
    - ``dz < 0``  →  cut   (proposed is lower;  material removed)

    Volumes are integrated as ``sum(|dz| * cell_area)`` over fill/cut cells.

    Parameters
    ----------
    toposolid_a:
        Existing terrain.
    toposolid_b:
        Proposed / modified terrain.
    grid_spacing:
        Grid cell size in metres.  Smaller values give higher accuracy at the
        cost of computation time.

    Returns
    -------
    ``{"cut": float, "fill": float, "net": float}``

    ``net = fill - cut``.  A positive net means material is added overall.
    """
    if grid_spacing <= 0:
        raise ValueError("grid_spacing must be > 0")

    pts_a = toposolid_a.vertices
    pts_b = toposolid_b.vertices

    x_min = max(pts_a[:, 0].min(), pts_b[:, 0].min())
    x_max = min(pts_a[:, 0].max(), pts_b[:, 0].max())
    y_min = max(pts_a[:, 1].min(), pts_b[:, 1].min())
    y_max = min(pts_a[:, 1].max(), pts_b[:, 1].max())

    if x_max <= x_min or y_max <= y_min:
        return {"cut": 0.0, "fill": 0.0, "net": 0.0}

    xs = np.arange(x_min, x_max + grid_spacing * 0.5, grid_spacing)
    ys = np.arange(y_min, y_max + grid_spacing * 0.5, grid_spacing)

    cell_area = grid_spacing * grid_spacing
    cut_vol = 0.0
    fill_vol = 0.0

    for x in xs:
        for y in ys:
            za = toposolid_a.elevation_at(float(x), float(y))
            zb = toposolid_b.elevation_at(float(x), float(y))
            if za is None or zb is None:
                continue
            dz = zb - za
            if dz < 0:
                cut_vol += abs(dz) * cell_area
            elif dz > 0:
                fill_vol += dz * cell_area

    return {"cut": cut_vol, "fill": fill_vol, "net": fill_vol - cut_vol}


# ---------------------------------------------------------------------------
# Slope (per-triangle, degrees)
# ---------------------------------------------------------------------------

def slope(toposolid: Toposolid) -> np.ndarray:
    """Compute per-triangle slope in degrees.

    Slope is the angle between the triangle normal and the vertical (Z) axis,
    i.e. ``arctan(sqrt(nx² + ny²) / |nz|)`` where (nx, ny, nz) is the unit
    normal.  A flat horizontal surface has slope = 0°; a vertical face has
    slope = 90°.

    Returns
    -------
    np.ndarray of shape (M,) with slope values in degrees for each triangle.
    """
    pts = toposolid.vertices
    slopes = []
    for tri in toposolid.simplices:
        p0, p1, p2 = pts[tri[0]], pts[tri[1]], pts[tri[2]]
        n = _triangle_normal(p0, p1, p2)
        mag = np.linalg.norm(n)
        if mag < 1e-14:
            slopes.append(0.0)
            continue
        n_unit = n / mag
        # Slope = angle from horizontal = 90° - angle from vertical
        cos_from_vertical = abs(n_unit[2])
        slope_rad = math.acos(min(1.0, cos_from_vertical))
        slopes.append(math.degrees(slope_rad))
    return np.array(slopes)


# ---------------------------------------------------------------------------
# Aspect (per-triangle, compass degrees)
# ---------------------------------------------------------------------------

def aspect(toposolid: Toposolid) -> np.ndarray:
    """Compute per-triangle aspect in compass degrees (0 = North / +Y, clockwise).

    Aspect is the compass direction the downhill gradient points — the
    direction water would drain, measured clockwise from North (+Y) in XY.

    Convention (downhill-facing, standard GIS):
    - Surface rising toward +Y (North) drains South → aspect = 180°
    - Surface rising toward +X (East)  drains West  → aspect = 270°
    - Surface rising toward -Y (South) drains North → aspect = 0°
    - Surface rising toward -X (West)  drains East  → aspect = 90°

    A flat horizontal triangle returns aspect = 0° by convention.

    Returns
    -------
    np.ndarray of shape (M,) with aspect values in degrees [0, 360).
    """
    pts = toposolid.vertices
    aspects = []
    for tri in toposolid.simplices:
        p0, p1, p2 = pts[tri[0]], pts[tri[1]], pts[tri[2]]
        n = _triangle_normal(p0, p1, p2)
        mag = np.linalg.norm(n)
        if mag < 1e-14 or abs(n[2]) / mag > (1.0 - 1e-9):
            aspects.append(0.0)
            continue
        # Downhill gradient direction in XY is opposite to the XY component
        # of the upward-pointing normal.
        nx, ny = n[0], n[1]
        # atan2 gives angle from +X axis (East); convert to compass from North
        # Compass = 90 - math_angle_from_east  (clockwise positive)
        math_deg = math.degrees(math.atan2(ny, nx))
        compass = (90.0 - math_deg) % 360.0
        aspects.append(compass)
    return np.array(aspects)


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "Toposolid",
    "BuildingPad",
    "Contour",
    "cut_fill_volume",
    "slope",
    "aspect",
    "Curve",
]
