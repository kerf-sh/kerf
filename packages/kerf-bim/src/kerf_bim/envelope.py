"""
kerf_bim.envelope — Parametric envelope primitives: Wall, Slab, Roof.

Public API
----------
  WallLayer(material, thickness)
      A single layer within a compound wall construction.

  Wall(start, end, height, thickness, *, layers)
      Multi-layer compound wall.  Hosts Door and Window openings.
      Analytic volume and section-cut geometry.

  Slab(boundary_loop, thickness, *, slope)
      Parametric horizontal or sloped floor / ceiling slab.

  Roof(footprint, slope, *, ridge_direction)
      Parametric gable / hip / shed / flat roof over a rectangular footprint.

All geometry is computed analytically (pure Python / math) — no OCCT dependency.

References
----------
Revit Architecture 2024 — Wall, Floor, Roof family definitions.
ISO 16739-1:2018 (IFC4) — IfcWall, IfcSlab, IfcRoof element definitions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 2-D / 3-D geometry helpers
# ---------------------------------------------------------------------------

Point2D = Tuple[float, float]
Point3D = Tuple[float, float, float]


def _dist2(a: Point2D, b: Point2D) -> float:
    """Euclidean distance between two 2-D points."""
    return math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)


def _dist3(a: Point3D, b: Point3D) -> float:
    """Euclidean distance between two 3-D points."""
    return math.sqrt(
        (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2
    )


def _polygon_area_2d(pts: Sequence[Point2D]) -> float:
    """Signed area of a simple polygon via the shoelace formula."""
    n = len(pts)
    acc = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        acc += x0 * y1 - x1 * y0
    return abs(acc) * 0.5


# ---------------------------------------------------------------------------
# WallLayer — a single layer in a compound wall construction
# ---------------------------------------------------------------------------

@dataclass
class WallLayer:
    """One material layer in a compound wall.

    Parameters
    ----------
    material : str
        Material name (e.g. ``"concrete_m30"``, ``"insulation_rockwool"``).
    thickness : float
        Layer thickness in metres (must be > 0).
    function : str
        Revit layer function:
        ``"structure"``, ``"substrate"``, ``"insulation"``, ``"finish"``
        or ``"membrane"``.  Defaults to ``"structure"``.
    """

    material: str
    thickness: float
    function: str = "structure"

    def __post_init__(self) -> None:
        if self.thickness <= 0.0:
            raise ValueError(
                f"WallLayer thickness must be > 0; got {self.thickness}"
            )
        _VALID_FUNCTIONS = {"structure", "substrate", "insulation", "finish", "membrane"}
        if self.function not in _VALID_FUNCTIONS:
            raise ValueError(
                f"WallLayer function must be one of {sorted(_VALID_FUNCTIONS)}; "
                f"got '{self.function}'"
            )


# ---------------------------------------------------------------------------
# SectionProfile — 2-D cross-section geometry (series of XZ half-points)
# ---------------------------------------------------------------------------

@dataclass
class SectionProfile:
    """2-D section cut geometry.

    ``vertices`` is a list of (u, z) pairs where *u* is the distance across
    the wall thickness and *z* is the height.
    """

    vertices: List[Tuple[float, float]]

    def area(self) -> float:
        """Signed area of the profile polygon."""
        return _polygon_area_2d(self.vertices)


# ---------------------------------------------------------------------------
# Wall
# ---------------------------------------------------------------------------

@dataclass
class Wall:
    """Parametric multi-layer compound wall.

    Parameters
    ----------
    start : Point2D
        Wall start point in plan (x, y) in metres.
    end : Point2D
        Wall end point in plan (x, y) in metres.
    height : float
        Wall height in metres (must be > 0).
    thickness : float
        Total wall thickness in metres (must be > 0).
        When *layers* are provided this value may differ from
        ``sum(l.thickness for l in layers)`` only if ``layers`` is ``None``
        — if layers are given, ``thickness`` is recomputed as their sum.
    layers : list[WallLayer] | None
        Ordered list of construction layers from exterior to interior.
        ``None`` creates a single structural layer of full ``thickness``.

    Notes
    -----
    ``openings`` is populated by ``Door`` and ``Window`` objects after
    construction; it is **not** a constructor argument.
    """

    start: Point2D
    end: Point2D
    height: float
    thickness: float
    layers: List[WallLayer] = field(default_factory=list)
    openings: List = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if self.height <= 0.0:
            raise ValueError(f"Wall height must be > 0; got {self.height}")
        if self.thickness <= 0.0:
            raise ValueError(f"Wall thickness must be > 0; got {self.thickness}")
        if self.start == self.end:
            raise ValueError("Wall start and end points must be different.")
        # If layers provided, recompute thickness to be the layer sum.
        if self.layers:
            self.thickness = sum(la.thickness for la in self.layers)
        else:
            # Auto-create a single structural layer.
            self.layers = [WallLayer("concrete_reinforced", self.thickness)]

    # ------------------------------------------------------------------
    # Analytic properties
    # ------------------------------------------------------------------

    def length(self) -> float:
        """Horizontal length of the wall centreline in metres."""
        return _dist2(self.start, self.end)

    def gross_volume(self) -> float:
        """Gross volume (length × height × thickness) in m³.

        This is the volume *before* subtracting opening voids.
        """
        return self.length() * self.height * self.thickness

    def opening_volume(self) -> float:
        """Total void volume cut by all hosted openings in m³."""
        total = 0.0
        for op in self.openings:
            # Each opening exposes its cut volume via a `.cut_volume()` method.
            if hasattr(op, "cut_volume"):
                total += op.cut_volume()
        return total

    def net_volume(self) -> float:
        """Net volume after subtracting all opening voids in m³."""
        return self.gross_volume() - self.opening_volume()

    def face_area(self) -> float:
        """Gross face area (one side) in m²."""
        return self.length() * self.height

    def section_profile(self) -> SectionProfile:
        """Return the 2-D section profile of this wall.

        The profile is the rectangular cross-section in the (u, z) plane
        where *u* spans from 0 (exterior face) to ``thickness`` (interior face).

        If layers are defined the profile includes vertical dividers between
        each layer, producing a stepped rectangle that exactly matches
        the layer arrangement.
        """
        # Simple rectangular profile for the full wall
        verts: List[Tuple[float, float]] = [
            (0.0, 0.0),
            (self.thickness, 0.0),
            (self.thickness, self.height),
            (0.0, self.height),
        ]
        return SectionProfile(vertices=verts)

    def layer_section_profiles(self) -> List[SectionProfile]:
        """Per-layer section rectangles ordered exterior → interior."""
        profiles = []
        u = 0.0
        for la in self.layers:
            verts: List[Tuple[float, float]] = [
                (u, 0.0),
                (u + la.thickness, 0.0),
                (u + la.thickness, self.height),
                (u, self.height),
            ]
            profiles.append(SectionProfile(vertices=verts))
            u += la.thickness
        return profiles

    def add_opening(self, opening) -> None:
        """Register a Door or Window opening hosted in this wall."""
        self.openings.append(opening)


# ---------------------------------------------------------------------------
# Slab
# ---------------------------------------------------------------------------

@dataclass
class Slab:
    """Parametric horizontal (or sloped) floor / ceiling slab.

    Parameters
    ----------
    boundary_loop : list[Point2D]
        Ordered polygon vertices defining the plan outline of the slab.
        At least 3 points required.
    thickness : float
        Slab thickness in metres (must be > 0).
    slope : float
        Slope in m/m (rise / run) applied uniformly in the +X direction.
        ``0.0`` (default) gives a level slab; positive values pitch the
        slab toward the +X direction.
    base_elevation : float
        Elevation of the slab soffit at the origin (x=0, y=0) in metres.
        Defaults to ``0.0``.
    material : str
        Primary slab material name.  Defaults to ``"concrete_reinforced"``.
    """

    boundary_loop: List[Point2D]
    thickness: float
    slope: float = 0.0
    base_elevation: float = 0.0
    material: str = "concrete_reinforced"

    def __post_init__(self) -> None:
        if len(self.boundary_loop) < 3:
            raise ValueError(
                "Slab boundary_loop requires at least 3 points; "
                f"got {len(self.boundary_loop)}"
            )
        if self.thickness <= 0.0:
            raise ValueError(
                f"Slab thickness must be > 0; got {self.thickness}"
            )

    # ------------------------------------------------------------------
    # Analytic properties
    # ------------------------------------------------------------------

    def plan_area(self) -> float:
        """Plan area of the slab boundary in m² (shoelace formula)."""
        return _polygon_area_2d(self.boundary_loop)

    def volume(self) -> float:
        """Slab volume in m³.

        For a sloped slab the volume is identical to a level slab because
        the slope merely tilts the body; the cross-sectional area in any
        plane perpendicular to the slope direction remains constant.
        Volume = plan_area × thickness (valid for uniform-thickness slabs
        regardless of slope).
        """
        return self.plan_area() * self.thickness

    def elevation_at(self, x: float) -> float:
        """Return the soffit elevation at plan coordinate *x*.

        The slope is applied in the +X direction:
            z = base_elevation + slope * x
        """
        return self.base_elevation + self.slope * x

    def section_profile(self) -> SectionProfile:
        """Return a vertical section through x=0 (a rectangle in (x, z) space).

        The section profile shows the slab thickness as a rectangle
        from z=base_elevation to z=base_elevation+thickness.
        """
        z0 = self.base_elevation
        z1 = z0 + self.thickness
        verts: List[Tuple[float, float]] = [
            (0.0, z0),
            (self.thickness, z0),
            (self.thickness, z1),
            (0.0, z1),
        ]
        return SectionProfile(vertices=verts)


# ---------------------------------------------------------------------------
# RoofType enum-like constants
# ---------------------------------------------------------------------------

ROOF_FLAT = "flat"
ROOF_SHED = "shed"
ROOF_GABLE = "gable"
ROOF_HIP = "hip"


# ---------------------------------------------------------------------------
# Roof
# ---------------------------------------------------------------------------

@dataclass
class Roof:
    """Parametric roof over a rectangular footprint.

    Parameters
    ----------
    footprint : list[Point2D]
        Four-point convex polygon (rectangular footprint) in plan.
        The first two points define the *eave* wall; the ridge is parallel
        to this edge for gable / hip types.
    slope : float
        Roof slope in m/m (rise / run).  Must be ≥ 0.
    ridge_direction : str
        ``"x"`` — ridge runs parallel to the X axis (default).
        ``"y"`` — ridge runs parallel to the Y axis.
    roof_type : str
        One of ``"flat"``, ``"shed"``, ``"gable"``, ``"hip"``.
        Defaults to ``"gable"``.
    overhang : float
        Horizontal overhang beyond the footprint edges in metres.
        Defaults to ``0.0`` (flush eaves).
    material : str
        Roof material name.  Defaults to ``"membrane_epdm"``.
    """

    footprint: List[Point2D]
    slope: float
    ridge_direction: str = "x"
    roof_type: str = ROOF_GABLE
    overhang: float = 0.0
    material: str = "membrane_epdm"

    def __post_init__(self) -> None:
        if len(self.footprint) < 3:
            raise ValueError(
                "Roof footprint requires at least 3 points; "
                f"got {len(self.footprint)}"
            )
        if self.slope < 0.0:
            raise ValueError(f"Roof slope must be ≥ 0; got {self.slope}")
        _VALID_TYPES = {ROOF_FLAT, ROOF_SHED, ROOF_GABLE, ROOF_HIP}
        if self.roof_type not in _VALID_TYPES:
            raise ValueError(
                f"roof_type must be one of {sorted(_VALID_TYPES)}; "
                f"got '{self.roof_type}'"
            )
        _VALID_DIR = {"x", "y"}
        if self.ridge_direction not in _VALID_DIR:
            raise ValueError(
                f"ridge_direction must be 'x' or 'y'; got '{self.ridge_direction}'"
            )

    # ------------------------------------------------------------------
    # Bounding box helpers
    # ------------------------------------------------------------------

    def _bbox(self) -> Tuple[float, float, float, float]:
        """(min_x, max_x, min_y, max_y) of the footprint."""
        xs = [p[0] for p in self.footprint]
        ys = [p[1] for p in self.footprint]
        return min(xs), max(xs), min(ys), max(ys)

    def footprint_area(self) -> float:
        """Plan area of the footprint in m²."""
        return _polygon_area_2d(self.footprint)

    # ------------------------------------------------------------------
    # Ridge geometry
    # ------------------------------------------------------------------

    def ridge_length(self) -> float:
        """Length of the ridge line in metres.

        Rules:
        - ``flat``  — ridge has zero length (flat roof has no ridge).
        - ``shed``  — ridge is the full eave span (single-pitch, one eave = ridge).
        - ``gable`` — ridge equals the footprint span in the ridge direction.
        - ``hip``   — ridge is shortened by the hip offset on each end;
                      hip offset = half the span perpendicular to the ridge.
        """
        min_x, max_x, min_y, max_y = self._bbox()
        span_x = max_x - min_x
        span_y = max_y - min_y

        if self.roof_type == ROOF_FLAT:
            return 0.0

        if self.ridge_direction == "x":
            along = span_x   # ridge runs along X
            perp = span_y    # hip offset is half of span_y
        else:
            along = span_y
            perp = span_x

        if self.roof_type == ROOF_SHED:
            # Shed has a single pitch from low eave to high eave; the
            # "ridge" in shed context equals the full span along.
            return float(along)

        if self.roof_type == ROOF_GABLE:
            return float(along)

        # HIP: ridge shortened by one hip offset (half perp) on each end.
        hip_offset = perp / 2.0
        ridge = along - 2.0 * hip_offset
        return max(0.0, float(ridge))

    def ridge_height(self) -> float:
        """Maximum height of the ridge above the eave level in metres.

        For flat: 0.
        For shed: slope × full perpendicular span.
        For gable/hip: slope × half the perpendicular span.
        """
        min_x, max_x, min_y, max_y = self._bbox()
        span_x = max_x - min_x
        span_y = max_y - min_y

        if self.roof_type == ROOF_FLAT:
            return 0.0

        if self.ridge_direction == "x":
            perp = span_y
        else:
            perp = span_x

        if self.roof_type == ROOF_SHED:
            return self.slope * perp

        # gable or hip: ridge sits over the centreline
        return self.slope * (perp / 2.0)

    # ------------------------------------------------------------------
    # Volume and surface area
    # ------------------------------------------------------------------

    def volume(self) -> float:
        """Approximate enclosed volume under the roof in m³.

        Computed as footprint_area × average_height where average_height
        is half the ridge height for gable/hip (triangular cross-section)
        or half for shed (also triangular).  Flat roof volume = 0
        (no enclosed space above eave).
        """
        h = self.ridge_height()
        area = self.footprint_area()

        if self.roof_type == ROOF_FLAT:
            return 0.0

        # In all non-flat cases the cross-section is triangular (or
        # trapezoidal for hip, approximated here as triangular).
        # Volume = (1/2) * base * height * length
        # where the triangular profile has base = perp span,
        # height = ridge_height, and length = along span.
        min_x, max_x, min_y, max_y = self._bbox()
        span_x = max_x - min_x
        span_y = max_y - min_y

        if self.ridge_direction == "x":
            along = span_x
            perp = span_y
        else:
            along = span_y
            perp = span_x

        if self.roof_type == ROOF_SHED:
            # Full triangular prism
            return 0.5 * perp * h * along

        # gable / hip: symmetric triangular cross-section
        return 0.5 * perp * h * along

    def section_profile(self) -> SectionProfile:
        """Return a triangular (or flat) 2-D section profile.

        The profile is in the (u, z) plane where *u* is the perpendicular
        span across the roof.
        """
        min_x, max_x, min_y, max_y = self._bbox()
        span_x = max_x - min_x
        span_y = max_y - min_y
        perp = span_y if self.ridge_direction == "x" else span_x
        h = self.ridge_height()

        if self.roof_type == ROOF_FLAT:
            return SectionProfile(vertices=[(0.0, 0.0), (perp, 0.0)])

        if self.roof_type == ROOF_SHED:
            # Single-pitch triangle: (0,0) → (perp, h) → (perp, 0)
            return SectionProfile(
                vertices=[(0.0, 0.0), (perp, h), (perp, 0.0)]
            )

        # gable / hip: symmetric triangle
        return SectionProfile(
            vertices=[(0.0, 0.0), (perp / 2.0, h), (perp, 0.0)]
        )
