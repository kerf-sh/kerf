"""
DRC engine for kerf-silicon.

A *layout* is a list of shape dicts.  Each shape has at minimum:
    {
        "layer": str,           # e.g. "met1"
        "polygon": [(x, y), ...] # coordinates in nanometres, last point != first
    }

Optional fields:
    "name": str     — human label for error messages

`check(layout, rules) -> DrcReport`

Polygon operations use Shapely when available, falling back to a pure-Python
bounding-box approximation for environments that don't have Shapely installed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .rules import (
    DensityRule,
    EnclosureRule,
    OverlapRule,
    RuleFamily,
    SpacingRule,
    WidthRule,
)

# ---------------------------------------------------------------------------
# Optional Shapely import
# ---------------------------------------------------------------------------

try:
    from shapely.geometry import Polygon as ShapelyPolygon
    from shapely.ops import unary_union
    _SHAPELY = True
except ImportError:  # pragma: no cover
    _SHAPELY = False


# ---------------------------------------------------------------------------
# Internal polygon helpers
# ---------------------------------------------------------------------------

def _make_poly(coords: list[tuple[float, float]]):
    """Return a Shapely polygon or a plain dict with area/bbox fallback."""
    if _SHAPELY:
        return ShapelyPolygon(coords)
    # Fallback: axis-aligned bounding box
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return {"xmin": min(xs), "xmax": max(xs), "ymin": min(ys), "ymax": max(ys)}


def _poly_area(p) -> float:
    if _SHAPELY and isinstance(p, ShapelyPolygon):
        return p.area
    # Shoelace formula on raw coords — but we only have bbox fallback here
    # so use bbox area as approximation
    return (p["xmax"] - p["xmin"]) * (p["ymax"] - p["ymin"])


def _poly_distance(a, b) -> float:
    """Minimum distance between two polygon boundaries (0 if overlapping)."""
    if _SHAPELY and isinstance(a, ShapelyPolygon) and isinstance(b, ShapelyPolygon):
        return a.distance(b)
    # Bbox fallback: distance between nearest edges
    ax1, ax2 = a["xmin"], a["xmax"]
    ay1, ay2 = a["ymin"], a["ymax"]
    bx1, bx2 = b["xmin"], b["xmax"]
    by1, by2 = b["ymin"], b["ymax"]
    dx = max(0.0, max(ax1 - bx2, bx1 - ax2))
    dy = max(0.0, max(ay1 - by2, by1 - ay2))
    return math.hypot(dx, dy)


def _poly_min_width(p) -> float:
    """Approximate minimum width of the polygon."""
    if _SHAPELY and isinstance(p, ShapelyPolygon):
        # Use minimum rotated rectangle width
        mrr = p.minimum_rotated_rectangle
        if mrr is None or mrr.is_empty:
            return 0.0
        coords = list(mrr.exterior.coords)
        side_a = math.dist(coords[0], coords[1])
        side_b = math.dist(coords[1], coords[2])
        return min(side_a, side_b)
    # Bbox fallback
    return min(p["xmax"] - p["xmin"], p["ymax"] - p["ymin"])


def _poly_contains(outer, inner) -> bool:
    """True if outer polygon fully contains inner polygon."""
    if _SHAPELY and isinstance(outer, ShapelyPolygon) and isinstance(inner, ShapelyPolygon):
        return outer.contains(inner)
    # Bbox fallback
    return (
        outer["xmin"] <= inner["xmin"]
        and outer["xmax"] >= inner["xmax"]
        and outer["ymin"] <= inner["ymin"]
        and outer["ymax"] >= inner["ymax"]
    )


def _poly_enclosure_margin(outer, inner) -> float:
    """Minimum enclosure margin of outer around inner (may be negative)."""
    if _SHAPELY and isinstance(outer, ShapelyPolygon) and isinstance(inner, ShapelyPolygon):
        # Erode outer by offset and test containment, or use buffer diff
        # Simpler: signed distance = negative distance from inner boundary to
        # outer interior.  We use exterior distance proxy.
        if not outer.contains(inner):
            return -_poly_distance(outer, inner) if outer.disjoint(inner) else 0.0
        # Contained: margin = minimum distance from inner boundary to outer boundary
        return inner.exterior.distance(outer.exterior)
    # Bbox fallback
    if not _poly_contains(outer, inner):
        return -1.0  # triggers violation
    return min(
        inner["xmin"] - outer["xmin"],
        outer["xmax"] - inner["xmax"],
        inner["ymin"] - outer["ymin"],
        outer["ymax"] - inner["ymax"],
    )


def _poly_overlaps(a, b) -> bool:
    """True if two polygons have any intersection (including touching)."""
    if _SHAPELY and isinstance(a, ShapelyPolygon) and isinstance(b, ShapelyPolygon):
        return not a.disjoint(b)
    # Bbox fallback
    return not (
        a["xmax"] <= b["xmin"]
        or b["xmax"] <= a["xmin"]
        or a["ymax"] <= b["ymin"]
        or b["ymax"] <= a["ymin"]
    )


def _poly_centroid(p) -> tuple[float, float]:
    if _SHAPELY and isinstance(p, ShapelyPolygon):
        c = p.centroid
        return (c.x, c.y)
    return (
        (p["xmin"] + p["xmax"]) / 2,
        (p["ymin"] + p["ymax"]) / 2,
    )


# ---------------------------------------------------------------------------
# Report types
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    rule_name: str
    layer: str
    location: tuple[float, float]
    description: str


@dataclass
class DrcReport:
    violations: list[Violation] = field(default_factory=list)
    passed_rules: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "violations": [
                {
                    "rule_name": v.rule_name,
                    "layer": v.layer,
                    "location": v.location,
                    "description": v.description,
                }
                for v in self.violations
            ],
            "passed_rules": self.passed_rules,
            "violation_count": len(self.violations),
        }


# ---------------------------------------------------------------------------
# Main check entry-point
# ---------------------------------------------------------------------------

def check(layout: list[dict], rules: list) -> DrcReport:
    """
    Run DRC rules against the layout.

    Parameters
    ----------
    layout : list[dict]
        Each element is a shape dict with at least ``layer`` (str) and
        ``polygon`` (list of (x, y) tuples in nanometres).
    rules : list
        A list of rule objects from ``kerf_silicon.drc.rules``.

    Returns
    -------
    DrcReport
        Aggregated violations and count of passing rule checks.
    """
    violations: list[Violation] = []
    passed = 0

    # Pre-build per-layer lists of (poly_obj, shape_dict)
    layer_shapes: dict[str, list[tuple]] = {}
    for shape in layout:
        layer = shape.get("layer", "")
        coords = shape.get("polygon", [])
        if len(coords) < 3:
            continue
        poly = _make_poly(coords)
        layer_shapes.setdefault(layer, []).append((poly, shape))

    for rule in rules:
        if rule.family is RuleFamily.WIDTH:
            viols = _check_width(rule, layer_shapes)
        elif rule.family is RuleFamily.SPACING:
            viols = _check_spacing(rule, layer_shapes)
        elif rule.family is RuleFamily.ENCLOSURE:
            viols = _check_enclosure(rule, layer_shapes)
        elif rule.family is RuleFamily.DENSITY:
            viols = _check_density(rule, layer_shapes)
        elif rule.family is RuleFamily.OVERLAP:
            viols = _check_overlap(rule, layer_shapes)
        else:
            viols = []

        if viols:
            violations.extend(viols)
        else:
            passed += 1

    return DrcReport(violations=violations, passed_rules=passed)


# ---------------------------------------------------------------------------
# Per-family check helpers
# ---------------------------------------------------------------------------

def _check_width(rule: WidthRule, layer_shapes: dict) -> list[Violation]:
    viols = []
    for poly, shape in layer_shapes.get(rule.layer, []):
        w = _poly_min_width(poly)
        if w < rule.min_nm - 1e-3:  # 1 pm tolerance
            cx, cy = _poly_centroid(poly)
            viols.append(
                Violation(
                    rule_name=rule.rule_name,
                    layer=rule.layer,
                    location=(cx, cy),
                    description=(
                        f"{rule.rule_name}: shape on layer '{rule.layer}' has "
                        f"minimum width {w:.1f} nm, required >= {rule.min_nm} nm. "
                        f"{rule.description}"
                    ),
                )
            )
    return viols


def _check_spacing(rule: SpacingRule, layer_shapes: dict) -> list[Violation]:
    viols = []
    shapes = layer_shapes.get(rule.layer, [])
    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            poly_a, shape_a = shapes[i]
            poly_b, shape_b = shapes[j]
            dist = _poly_distance(poly_a, poly_b)
            if 0 < dist < rule.min_nm - 1e-3:
                cx, cy = _poly_centroid(poly_a)
                viols.append(
                    Violation(
                        rule_name=rule.rule_name,
                        layer=rule.layer,
                        location=(cx, cy),
                        description=(
                            f"{rule.rule_name}: shapes on layer '{rule.layer}' are "
                            f"{dist:.1f} nm apart, required >= {rule.min_nm} nm. "
                            f"{rule.description}"
                        ),
                    )
                )
    return viols


def _check_enclosure(rule: EnclosureRule, layer_shapes: dict) -> list[Violation]:
    viols = []
    outer_shapes = layer_shapes.get(rule.outer_layer, [])
    inner_shapes = layer_shapes.get(rule.inner_layer, [])

    for inner_poly, inner_shape in inner_shapes:
        # Find the first outer shape that encloses (or partially overlaps) this inner
        enclosing = None
        for outer_poly, _ in outer_shapes:
            if _poly_overlaps(outer_poly, inner_poly) or _poly_contains(outer_poly, inner_poly):
                enclosing = outer_poly
                break

        if enclosing is None:
            # No outer shape at all → zero enclosure
            cx, cy = _poly_centroid(inner_poly)
            viols.append(
                Violation(
                    rule_name=rule.rule_name,
                    layer=rule.inner_layer,
                    location=(cx, cy),
                    description=(
                        f"{rule.rule_name}: shape on '{rule.inner_layer}' has no "
                        f"enclosing '{rule.outer_layer}' shape. "
                        f"Required enclosure >= {rule.enc_nm} nm. "
                        f"{rule.description}"
                    ),
                )
            )
        else:
            margin = _poly_enclosure_margin(enclosing, inner_poly)
            if margin < rule.enc_nm - 1e-3:
                cx, cy = _poly_centroid(inner_poly)
                viols.append(
                    Violation(
                        rule_name=rule.rule_name,
                        layer=rule.inner_layer,
                        location=(cx, cy),
                        description=(
                            f"{rule.rule_name}: '{rule.outer_layer}' encloses "
                            f"'{rule.inner_layer}' by only {margin:.1f} nm, "
                            f"required >= {rule.enc_nm} nm. "
                            f"{rule.description}"
                        ),
                    )
                )
    return viols


def _check_density(rule: DensityRule, layer_shapes: dict) -> list[Violation]:
    """
    Density check across a single tile that covers the full layout bounding box.

    For a real PDK flow this would tile the die; here we use a single-tile
    approximation which is sufficient for unit-test purposes.
    """
    viols = []
    shapes = layer_shapes.get(rule.layer, [])

    # Collect all shapes across the entire layout to get the tile bounds
    all_shapes_flat = [s for sl in layer_shapes.values() for s in sl]

    if not all_shapes_flat:
        # Empty layout — use default tile size
        tile_area = rule.tile_nm ** 2
    else:
        # Bounding box of all shapes as the tile
        if _SHAPELY:
            all_polys = [p for p, _ in all_shapes_flat]
            union = unary_union(all_polys)
            b = union.bounds  # (minx, miny, maxx, maxy)
            w = max(b[2] - b[0], rule.tile_nm)
            h = max(b[3] - b[1], rule.tile_nm)
        else:
            all_xmin = min(s["xmin"] for p, s in all_shapes_flat if isinstance(s, dict) and "xmin" in s)
            all_xmax = max(s["xmax"] for p, s in all_shapes_flat if isinstance(s, dict) and "xmax" in s)
            all_ymin = min(s["ymin"] for p, s in all_shapes_flat if isinstance(s, dict) and "ymin" in s)
            all_ymax = max(s["ymax"] for p, s in all_shapes_flat if isinstance(s, dict) and "ymax" in s)
            w = max(all_xmax - all_xmin, rule.tile_nm)
            h = max(all_ymax - all_ymin, rule.tile_nm)
        tile_area = w * h

    layer_area = sum(_poly_area(p) for p, _ in shapes)
    density_pct = 100.0 * layer_area / tile_area if tile_area > 0 else 0.0

    if density_pct < rule.min_pct:
        viols.append(
            Violation(
                rule_name=rule.rule_name,
                layer=rule.layer,
                location=(0.0, 0.0),
                description=(
                    f"{rule.rule_name}: layer '{rule.layer}' density is "
                    f"{density_pct:.1f} %, below minimum {rule.min_pct} %. "
                    f"{rule.description}"
                ),
            )
        )
    elif density_pct > rule.max_pct:
        viols.append(
            Violation(
                rule_name=rule.rule_name,
                layer=rule.layer,
                location=(0.0, 0.0),
                description=(
                    f"{rule.rule_name}: layer '{rule.layer}' density is "
                    f"{density_pct:.1f} %, above maximum {rule.max_pct} %. "
                    f"{rule.description}"
                ),
            )
        )

    return viols


def _check_overlap(rule: OverlapRule, layer_shapes: dict) -> list[Violation]:
    viols = []
    shapes_a = layer_shapes.get(rule.layer_a, [])
    shapes_b = layer_shapes.get(rule.layer_b, [])

    for poly_a, _ in shapes_a:
        for poly_b, _ in shapes_b:
            if _poly_overlaps(poly_a, poly_b):
                cx, cy = _poly_centroid(poly_a)
                viols.append(
                    Violation(
                        rule_name=rule.rule_name,
                        layer=rule.layer_a,
                        location=(cx, cy),
                        description=(
                            f"{rule.rule_name}: forbidden overlap between "
                            f"'{rule.layer_a}' and '{rule.layer_b}'. "
                            f"{rule.description}"
                        ),
                    )
                )
    return viols
