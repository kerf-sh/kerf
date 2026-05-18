"""
kerf_packaging.dieline — Dieline data model for flat-layout packaging.

A *dieline* is the 2-D flat cut-and-score pattern that, when creased and
assembled, forms a 3-D carton or corrugated box.

Data model
----------
A ``Dieline`` collects:

* **panels** — rectangular (or polygonal) flat surfaces.
* **lines** — individual 2-D segments tagged by kind:
    ``cut``   — outer boundary; cut all the way through the board.
    ``fold``  — crease / score; fold along this line to assemble the box.
    ``score`` — partial cut (half-cut) for thicker boards.
    ``perf``  — perforation; tear-open feature.

Public API
----------
``Dieline``
    Dataclass carrying ``panels``, ``lines``, ``width``, ``height``,
    ``material``, ``units``.

``DiePanel``
    One panel rectangle or polygon on the flat layout.

``DieLine``
    A single 2-D line segment with a ``kind`` tag.

``FoldEdge``
    Identifies which two panels share a fold line (used by ``fold.py``).

``validate_dieline(d) -> list[str]``
    Light sanity-checks; returns a list of warning strings (empty = clean).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class LineKind(str, Enum):
    """Classification of a dieline line segment."""
    CUT   = "cut"    # outer cut boundary
    FOLD  = "fold"   # crease / fold line
    SCORE = "score"  # partial cut / score
    PERF  = "perf"   # perforation


class Material(str, Enum):
    """Board material hint."""
    SBS          = "sbs"          # solid bleached sulphate (folding carton)
    CRB          = "crb"          # coated recycled board (folding carton)
    FLUTE_B      = "flute_b"      # single-wall B-flute corrugated
    FLUTE_C      = "flute_c"      # single-wall C-flute corrugated
    FLUTE_BC     = "flute_bc"     # double-wall BC-flute corrugated
    FLUTE_E      = "flute_e"      # E-flute (micro-flute)
    KRAFT        = "kraft"        # plain kraft / brown paper
    UNKNOWN      = "unknown"


# ---------------------------------------------------------------------------
# 2-D geometry primitives
# ---------------------------------------------------------------------------

@dataclass
class Point2D:
    """A 2-D point in the flat layout coordinate system (mm)."""
    x: float
    y: float

    def __iter__(self):
        yield self.x
        yield self.y

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass
class DieLine:
    """
    A single 2-D line segment on the dieline flat layout.

    Parameters
    ----------
    x1, y1 : float
        Start point (mm).
    x2, y2 : float
        End point (mm).
    kind : LineKind
        Semantic role of the line.
    layer : str
        Optional DXF layer name (defaults to the kind value).
    """
    x1: float
    y1: float
    x2: float
    y2: float
    kind: LineKind = LineKind.CUT
    layer: str = ""

    def __post_init__(self):
        if not self.layer:
            self.layer = self.kind.value

    def length(self) -> float:
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        return math.hypot(dx, dy)

    def midpoint(self) -> Point2D:
        return Point2D((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    def angle_deg(self) -> float:
        """Angle of the line from the positive X axis, in degrees [0, 360)."""
        a = math.degrees(math.atan2(self.y2 - self.y1, self.x2 - self.x1))
        return a % 360.0

    def as_entity(self) -> dict:
        """Serialise to a DXF entity dict (for dxf_export)."""
        return {
            "type": "line",
            "layer": self.layer,
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
        }


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

@dataclass
class DiePanelVertex:
    """One vertex of a polygonal panel outline."""
    x: float
    y: float


@dataclass
class DiPanel:
    """
    A single panel (flat face) of the box on the dieline layout.

    Panels are the contiguous regions bounded by cut/fold lines.  A
    rectangular panel is defined by its lower-left corner (``x``, ``y``),
    ``width``, and ``height``.  For non-rectangular panels, supply
    ``polygon`` vertices instead.

    Parameters
    ----------
    name : str
        Human-readable label (e.g. ``"front"``, ``"back"``, ``"top_flap"``).
    x, y : float
        Lower-left corner of the bounding rectangle (mm).
    width, height : float
        Panel dimensions (mm).
    polygon : list of DiePanelVertex
        If provided, overrides the rectangle.  Vertices should be ordered
        counter-clockwise.
    """
    name: str
    x: float
    y: float
    width: float
    height: float
    polygon: list[DiePanelVertex] = field(default_factory=list)

    def bounding_box(self) -> tuple[float, float, float, float]:
        """Return (x_min, y_min, x_max, y_max)."""
        if self.polygon:
            xs = [v.x for v in self.polygon]
            ys = [v.y for v in self.polygon]
            return min(xs), min(ys), max(xs), max(ys)
        return self.x, self.y, self.x + self.width, self.y + self.height

    def area(self) -> float:
        """Approximate area (shoelace for polygon; W×H for rectangle)."""
        if self.polygon:
            n = len(self.polygon)
            if n < 3:
                return 0.0
            verts = self.polygon
            a = 0.0
            for i in range(n):
                j = (i + 1) % n
                a += verts[i].x * verts[j].y
                a -= verts[j].x * verts[i].y
            return abs(a) / 2.0
        return self.width * self.height

    def outline_lines(self, kind: LineKind = LineKind.CUT) -> list[DieLine]:
        """Return the four cut lines forming the rectangle outline."""
        if self.polygon:
            lines = []
            verts = self.polygon
            n = len(verts)
            for i in range(n):
                j = (i + 1) % n
                lines.append(DieLine(
                    verts[i].x, verts[i].y,
                    verts[j].x, verts[j].y,
                    kind=kind,
                ))
            return lines
        x0, y0 = self.x, self.y
        x1, y1 = self.x + self.width, self.y + self.height
        return [
            DieLine(x0, y0, x1, y0, kind=kind),
            DieLine(x1, y0, x1, y1, kind=kind),
            DieLine(x1, y1, x0, y1, kind=kind),
            DieLine(x0, y1, x0, y0, kind=kind),
        ]


# ---------------------------------------------------------------------------
# Fold edge
# ---------------------------------------------------------------------------

@dataclass
class FoldEdge:
    """
    Identifies a shared fold edge between two panels.

    Parameters
    ----------
    panel_a, panel_b : str
        Names of the two panels sharing this fold.
    line : DieLine
        The fold line geometry.
    angle_deg : float
        Target dihedral fold angle in degrees (0 = flat, 90 = right angle).
    """
    panel_a: str
    panel_b: str
    line: DieLine
    angle_deg: float = 90.0


# ---------------------------------------------------------------------------
# Dieline root container
# ---------------------------------------------------------------------------

@dataclass
class Dieline:
    """
    Complete 2-D dieline layout.

    Attributes
    ----------
    name : str
        Box name / style (e.g. ``"ECMA-C02"``).
    panels : list of DiPanel
        Flat panels on the layout.
    lines : list of DieLine
        All cut, fold, score, and perf lines.
    fold_edges : list of FoldEdge
        Semantic fold-edge descriptors linking pairs of panels.
    width : float
        Overall flat-layout width (mm).
    height : float
        Overall flat-layout height (mm).
    material : Material
        Board material.
    units : str
        Unit system (always ``"mm"`` for dieline work).
    metadata : dict
        Freeform metadata (standard name, customer ref, etc.).
    """
    name: str = ""
    panels: list[DiPanel] = field(default_factory=list)
    lines: list[DieLine] = field(default_factory=list)
    fold_edges: list[FoldEdge] = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0
    material: Material = Material.SBS
    units: str = "mm"
    metadata: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Convenience accessors                                                #
    # ------------------------------------------------------------------ #

    def cut_lines(self) -> list[DieLine]:
        return [l for l in self.lines if l.kind == LineKind.CUT]

    def fold_lines(self) -> list[DieLine]:
        return [l for l in self.lines if l.kind == LineKind.FOLD]

    def score_lines(self) -> list[DieLine]:
        return [l for l in self.lines if l.kind == LineKind.SCORE]

    def lines_by_layer(self, layer: str) -> list[DieLine]:
        return [l for l in self.lines if l.layer == layer]

    def to_drawing_dict(self) -> dict:
        """
        Convert the dieline to a drawing dict suitable for ``dxf_export``.

        Layers used:
            ``cut``   — red (ACI 1)
            ``fold``  — cyan (ACI 4)
            ``score`` — yellow (ACI 2)
            ``perf``  — magenta (ACI 6)
        """
        _layer_colors = {
            "cut":   1,  # red
            "fold":  4,  # cyan
            "score": 2,  # yellow
            "perf":  6,  # magenta
        }
        entities = [line.as_entity() for line in self.lines]
        layers = [
            {"name": name, "color": color, "linetype": "CONTINUOUS"}
            for name, color in _layer_colors.items()
        ]
        return {
            "entities": entities,
            "layers": layers,
            "units": self.units,
        }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_dieline(d: Dieline) -> list[str]:
    """
    Light sanity-checks on a dieline.

    Returns a list of warning strings.  An empty list means the dieline
    passed all checks.
    """
    warnings: list[str] = []

    if not d.name:
        warnings.append("dieline has no name")

    if not d.panels:
        warnings.append("dieline has no panels")

    if not d.lines:
        warnings.append("dieline has no lines")

    if d.width <= 0 or d.height <= 0:
        warnings.append(
            f"dieline layout size {d.width:.1f}×{d.height:.1f} mm is non-positive"
        )

    # Check fold lines are within layout bounds (with 1 mm tolerance)
    tol = 1.0
    for i, line in enumerate(d.lines):
        for coord, bound, label in [
            (line.x1, d.width, "x1"), (line.x2, d.width, "x2"),
            (line.y1, d.height, "y1"), (line.y2, d.height, "y2"),
        ]:
            if coord < -tol or coord > bound + tol:
                warnings.append(
                    f"line[{i}] {label}={coord:.1f} is outside layout "
                    f"[0, {bound:.1f}] mm"
                )

    # Check panels have positive dimensions
    for p in d.panels:
        if not p.polygon and (p.width <= 0 or p.height <= 0):
            warnings.append(
                f"panel '{p.name}' has non-positive dimensions "
                f"{p.width:.1f}×{p.height:.1f}"
            )

    return warnings
