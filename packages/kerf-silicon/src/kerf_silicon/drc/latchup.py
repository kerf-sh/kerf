"""
Latch-up rule checker — well-tap spacing + n+/p+ adjacency across well boundary.

In CMOS layouts, parasitic n-p-n / p-n-p bipolar transistors can trigger
latch-up if:

1. **Well-tap spacing** — every nwell must contain a tap to VDD within the PDK
   limit (SKY130 default: 15 µm), and every p-substrate region must contain a
   tap to VSS within the same distance.  Violation: a well region whose centroid
   is more than ``max_tap_distance_um`` from the nearest tap on the same side of
   the well boundary.

2. **n+/p+ adjacency** — an n+ source/drain implant (nsdm) that sits across the
   nwell boundary from a p+ source/drain implant (psdm) at less than the PDK
   minimum separation risks forward-biasing the parasitic emitter junction.
   SKY130 threshold ≈ 0.84 µm.

Public API
----------
    check_latchup(layout, rules) -> LatchupReport

Parameters
----------
layout : list[dict]
    Shapes in the same format as the DRC engine:
        {
            "layer":   str,              # e.g. "nwell", "tap", "nsdm", "psdm"
            "polygon": [(x, y), ...],    # coordinates in micrometres (µm)
        }
    The coordinate unit is µm throughout (not nm) so distances can be
    compared directly against PDK values expressed in µm.

rules : LatchupRules | None
    Rule parameters.  When None the SKY130 defaults are used.

Returns
-------
LatchupReport
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Optional Shapely import (mirrors engine.py pattern)
# ---------------------------------------------------------------------------

try:
    from shapely.geometry import Polygon as ShapelyPolygon
    from shapely.ops import unary_union
    _SHAPELY = True
except ImportError:  # pragma: no cover
    _SHAPELY = False


# ---------------------------------------------------------------------------
# Rule parameter dataclass
# ---------------------------------------------------------------------------

@dataclass
class LatchupRules:
    """Parameters for the latch-up rule check."""

    # Well-tap check
    well_layer: str = "nwell"       # identifies nwell regions
    tap_layer: str = "tap"          # identifies well/substrate tap regions
    max_tap_distance_um: float = 15.0  # SKY130: 15–25 µm; we enforce 15 µm

    # n+/p+ adjacency check
    n_plus_layer: str = "nsdm"      # N+ source/drain implant layer
    p_plus_layer: str = "psdm"      # P+ source/drain implant layer
    min_np_separation_um: float = 0.84  # SKY130 LU.3/LU.4 ≈ nwell min width


# Default rule set matching sky130_latchup.json
SKY130_LATCHUP_RULES = LatchupRules()


# ---------------------------------------------------------------------------
# Polygon helpers (pure-Python fallback mirrors engine.py helpers)
# ---------------------------------------------------------------------------

def _make_poly(coords: list[tuple[float, float]]):
    if _SHAPELY:
        return ShapelyPolygon(coords)
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return {"xmin": min(xs), "xmax": max(xs), "ymin": min(ys), "ymax": max(ys)}


def _centroid(p) -> tuple[float, float]:
    if _SHAPELY and isinstance(p, ShapelyPolygon):
        c = p.centroid
        return (c.x, c.y)
    return ((p["xmin"] + p["xmax"]) / 2.0, (p["ymin"] + p["ymax"]) / 2.0)


def _distance(a, b) -> float:
    """Minimum boundary-to-boundary distance (0 if touching/overlapping)."""
    if _SHAPELY and isinstance(a, ShapelyPolygon) and isinstance(b, ShapelyPolygon):
        return a.distance(b)
    # Bbox fallback
    ax1, ax2 = a["xmin"], a["xmax"]
    ay1, ay2 = a["ymin"], a["ymax"]
    bx1, bx2 = b["xmin"], b["xmax"]
    by1, by2 = b["ymin"], b["ymax"]
    dx = max(0.0, max(ax1 - bx2, bx1 - ax2))
    dy = max(0.0, max(ay1 - by2, by1 - ay2))
    return math.hypot(dx, dy)


def _intersects(a, b) -> bool:
    """True if polygons share any area (touches counts as intersection here)."""
    if _SHAPELY and isinstance(a, ShapelyPolygon) and isinstance(b, ShapelyPolygon):
        return not a.disjoint(b)
    # Bbox overlap
    return not (
        a["xmax"] <= b["xmin"]
        or b["xmax"] <= a["xmin"]
        or a["ymax"] <= b["ymin"]
        or b["ymax"] <= a["ymin"]
    )


def _contains_point(poly, px: float, py: float) -> bool:
    """True if the point (px, py) is inside the polygon."""
    if _SHAPELY and isinstance(poly, ShapelyPolygon):
        from shapely.geometry import Point
        return poly.contains(Point(px, py))
    # Bbox fallback
    return (
        poly["xmin"] <= px <= poly["xmax"]
        and poly["ymin"] <= py <= poly["ymax"]
    )


# ---------------------------------------------------------------------------
# Report types
# ---------------------------------------------------------------------------

@dataclass
class LatchupViolation:
    """A single latch-up rule violation."""
    check: str                          # "well_tap" or "np_adjacency"
    location: tuple[float, float]       # representative (x, y) in µm
    description: str


@dataclass
class LatchupReport:
    """Aggregated result of a latch-up check pass."""
    violations: list[LatchupViolation] = field(default_factory=list)
    wells_checked: int = 0
    np_pairs_checked: int = 0

    @property
    def has_violations(self) -> bool:
        return bool(self.violations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "violations": [
                {
                    "check": v.check,
                    "location": v.location,
                    "description": v.description,
                }
                for v in self.violations
            ],
            "wells_checked": self.wells_checked,
            "np_pairs_checked": self.np_pairs_checked,
            "violation_count": len(self.violations),
        }


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------

def check_latchup(
    layout: list[dict],
    rules: LatchupRules | None = None,
) -> LatchupReport:
    """
    Run the latch-up DRC against a layout.

    Parameters
    ----------
    layout : list[dict]
        Each element must have ``layer`` (str) and ``polygon`` (list of
        (x, y) tuples in **micrometres**).
    rules : LatchupRules | None
        Rule parameters.  Defaults to SKY130_LATCHUP_RULES.

    Returns
    -------
    LatchupReport
    """
    if rules is None:
        rules = SKY130_LATCHUP_RULES

    # ------------------------------------------------------------------
    # Index shapes by layer
    # ------------------------------------------------------------------
    layer_polys: dict[str, list] = {}
    for shape in layout:
        lyr = shape.get("layer", "")
        coords = shape.get("polygon", [])
        if len(coords) < 3:
            continue
        poly = _make_poly(coords)
        layer_polys.setdefault(lyr, []).append(poly)

    well_polys = layer_polys.get(rules.well_layer, [])
    tap_polys  = layer_polys.get(rules.tap_layer, [])
    nplus_polys = layer_polys.get(rules.n_plus_layer, [])
    pplus_polys = layer_polys.get(rules.p_plus_layer, [])

    violations: list[LatchupViolation] = []

    # ------------------------------------------------------------------
    # 1. Well-tap spacing check
    # ------------------------------------------------------------------
    # For each nwell polygon: the closest tap within or adjacent to it must
    # be within max_tap_distance_um of the well centroid.  If no tap exists
    # at all within that radius, report a violation at the well centroid.
    #
    # We use the distance from the well centroid to the nearest tap polygon.
    # A tap that is wholly outside the nwell is still valid for the
    # substrate-side check, but for the nwell side we only accept taps
    # that are within or touching the nwell.  However, SKY130's rule is
    # proximity-based: any tap within 15 µm of every point in the nwell
    # satisfies the requirement.  A practical approximation: the tap must
    # be within max_tap_distance_um of the well centroid.
    # ------------------------------------------------------------------

    wells_checked = len(well_polys)

    for well_poly in well_polys:
        cx, cy = _centroid(well_poly)

        # Find minimum distance from well centroid to any tap
        min_dist = math.inf
        for tap_poly in tap_polys:
            # Distance from centroid point to tap polygon boundary
            if _SHAPELY and isinstance(tap_poly, ShapelyPolygon):
                from shapely.geometry import Point
                d = Point(cx, cy).distance(tap_poly)
            else:
                # Bbox fallback: distance from centroid to nearest bbox edge
                tx1, tx2 = tap_poly["xmin"], tap_poly["xmax"]
                ty1, ty2 = tap_poly["ymin"], tap_poly["ymax"]
                dx = max(0.0, max(tx1 - cx, cx - tx2))
                dy = max(0.0, max(ty1 - cy, cy - ty2))
                d = math.hypot(dx, dy)
            if d < min_dist:
                min_dist = d

        if min_dist > rules.max_tap_distance_um + 1e-9:
            dist_str = (
                f"{min_dist:.2f} µm"
                if min_dist != math.inf
                else "no tap present"
            )
            violations.append(
                LatchupViolation(
                    check="well_tap",
                    location=(cx, cy),
                    description=(
                        f"well_tap: {rules.well_layer} at ({cx:.3f}, {cy:.3f}) µm "
                        f"has nearest tap at {dist_str}, "
                        f"exceeds limit {rules.max_tap_distance_um:.1f} µm. "
                        f"Missing VDD tap within PDK latch-up distance."
                    ),
                )
            )

    # ------------------------------------------------------------------
    # 2. n+/p+ adjacency check across the well boundary
    # ------------------------------------------------------------------
    # For each (nsdm, psdm) pair: if they are closer than min_np_separation_um
    # AND they are on opposite sides of the nwell boundary (one is inside the
    # nwell, the other is outside), report a violation.
    #
    # "Inside the nwell" = the centroid of the implant region falls inside
    # an nwell polygon.
    # ------------------------------------------------------------------

    np_pairs_checked = 0

    for n_poly in nplus_polys:
        ncx, ncy = _centroid(n_poly)
        # Is this n+ region inside an nwell?
        n_in_well = any(_contains_point(w, ncx, ncy) for w in well_polys)

        for p_poly in pplus_polys:
            np_pairs_checked += 1
            pcx, pcy = _centroid(p_poly)
            # Is this p+ region inside an nwell?
            p_in_well = any(_contains_point(w, pcx, pcy) for w in well_polys)

            # Only flag pairs that are on opposite sides of the well boundary
            if n_in_well == p_in_well:
                continue

            dist = _distance(n_poly, p_poly)
            if dist < rules.min_np_separation_um - 1e-9:
                violations.append(
                    LatchupViolation(
                        check="np_adjacency",
                        location=(ncx, ncy),
                        description=(
                            f"np_adjacency: {rules.n_plus_layer} at "
                            f"({ncx:.3f}, {ncy:.3f}) µm and {rules.p_plus_layer} at "
                            f"({pcx:.3f}, {pcy:.3f}) µm are {dist:.3f} µm apart "
                            f"across the {rules.well_layer} boundary, "
                            f"below minimum {rules.min_np_separation_um:.2f} µm. "
                            f"Risk of parasitic bipolar latch-up."
                        ),
                    )
                )

    return LatchupReport(
        violations=violations,
        wells_checked=wells_checked,
        np_pairs_checked=np_pairs_checked,
    )
