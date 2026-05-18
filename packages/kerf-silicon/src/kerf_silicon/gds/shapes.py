"""KLayout-compatible shape data model for GDS-II layouts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Primitive geometry types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Point:
    """Integer coordinate point in database units."""
    x: int
    y: int

    def __iter__(self):
        yield self.x
        yield self.y


# ---------------------------------------------------------------------------
# Shape types (mirroring KLayout's data model)
# ---------------------------------------------------------------------------

@dataclass
class Box:
    """Axis-aligned rectangle defined by two corner points.

    Equivalent to KLayout ``DBox`` in integer database units.
    Stored as a BOUNDARY (polygon) element in GDS-II.
    """
    layer: int
    datatype: int
    p1: Point   # lower-left corner
    p2: Point   # upper-right corner

    def to_polygon_points(self) -> List[Point]:
        """Return the 5-point closed polygon (first == last) for GDS-II."""
        x1, y1 = self.p1.x, self.p1.y
        x2, y2 = self.p2.x, self.p2.y
        return [
            Point(x1, y1),
            Point(x2, y1),
            Point(x2, y2),
            Point(x1, y2),
            Point(x1, y1),  # close
        ]


@dataclass
class Polygon:
    """Arbitrary polygon shape.

    The point list may or may not include the closing point — the writer
    will always close it by repeating the first point.
    """
    layer: int
    datatype: int
    points: List[Point]

    def closed_points(self) -> List[Point]:
        """Return points ensuring the polygon is closed."""
        pts = list(self.points)
        if pts and pts[-1] != pts[0]:
            pts.append(pts[0])
        return pts


@dataclass
class Path:
    """Centreline path with a uniform width.

    Equivalent to KLayout ``DPath``.
    """
    layer: int
    datatype: int
    points: List[Point]
    width: int = 0   # half-width in database units (0 = single-pixel)


@dataclass
class Text:
    """Text label at a given position.

    Equivalent to KLayout ``DText``.
    """
    layer: int
    datatype: int = 0
    text: str = ""
    position: Point = field(default_factory=lambda: Point(0, 0))
    texttype: int = 0


@dataclass
class Reference:
    """Structure reference (SREF) — places a named cell at a position.

    Equivalent to KLayout ``DCellInstArray`` (single placement).
    """
    cell_name: str
    position: Point = field(default_factory=lambda: Point(0, 0))
    rotation: float = 0.0   # degrees, counter-clockwise
    magnification: float = 1.0
    mirror_x: bool = False


# ---------------------------------------------------------------------------
# Cell / Library containers
# ---------------------------------------------------------------------------

@dataclass
class Cell:
    """A named GDS-II structure (BGNSTR … ENDSTR block)."""
    name: str
    shapes: List = field(default_factory=list)   # Box | Polygon | Path | Text | Reference
    # Timestamps are optional; writer will use epoch zero if not provided.
    mod_year:  int = 0
    mod_month: int = 0
    mod_day:   int = 0
    mod_hour:  int = 0
    mod_minute: int = 0
    mod_second: int = 0
    acc_year:  int = 0
    acc_month: int = 0
    acc_day:   int = 0
    acc_hour:  int = 0
    acc_minute: int = 0
    acc_second: int = 0

    def add(self, shape) -> "Cell":
        self.shapes.append(shape)
        return self


@dataclass
class Library:
    """Top-level GDS-II library (BGNLIB … ENDLIB block)."""
    name: str = "KERF"
    cells: List[Cell] = field(default_factory=list)
    user_unit: float = 1e-6    # metres per database unit (e.g. 1 µm)
    db_unit: float = 1e-9      # metres per database unit (precision, e.g. 1 nm)
    version: int = 5
    # Library timestamps
    mod_year:  int = 0
    mod_month: int = 0
    mod_day:   int = 0
    mod_hour:  int = 0
    mod_minute: int = 0
    mod_second: int = 0
    acc_year:  int = 0
    acc_month: int = 0
    acc_day:   int = 0
    acc_hour:  int = 0
    acc_minute: int = 0
    acc_second: int = 0

    def add_cell(self, cell: Cell) -> "Library":
        self.cells.append(cell)
        return self
