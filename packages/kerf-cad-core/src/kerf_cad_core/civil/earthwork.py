"""
kerf_cad_core.civil.earthwork — Cut/fill earthwork volume computation.

Volume method: grid sampling (modified-prismoidal approach).
    1. Determine the bounding box of the existing TIN surface.
    2. Lay a regular grid of sample points spaced `grid_spacing` metres apart
       (default 1.0 m) over the bounding box.
    3. At each grid node (x, y):
           z_exist = TIN.interpolate_z(x, y)   — existing grade
           z_design = DesignSurface.elevation_at(x, y)  — proposed grade
       Skip nodes where z_exist is None (outside the TIN).
    4. Accumulate:
           Δz = z_design − z_exist
           if Δz > 0:  fill += Δz × cell_area   (raise terrain → fill)
           if Δz < 0:  cut  += |Δz| × cell_area  (lower terrain → cut)
    5. cell_area = grid_spacing²

Units: metres, metres³.

DesignSurface types:
    FLAT_PAD  — constant elevation over a polygon boundary, with optional
                uniform side-slopes (1V:nH — i.e., slope = 1/n horizontal
                run per 1 unit vertical rise).  Points inside the polygon
                return pad_elevation; points outside return a graded
                elevation rising from the pad edge (if slope > 0) or None.
    SLOPED_PAD — single-plane pad defined by a corner elevation + two slope
                 components (dz_dx, dz_dy).

The polygon boundary is expressed as a list of (x, y) tuples in any order
(it is sorted into a convex hull by the point-in-polygon test, or the raw
ring is used for strictly convex/simple polygons).

Point-in-polygon: standard even-odd ray-casting (works for simple polygons).

Author: imranparuk
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from kerf_cad_core.civil.terrain import TIN, Point3D

_EPS = 1e-9


# ---------------------------------------------------------------------------
# Polygon helpers
# ---------------------------------------------------------------------------

def _point_in_polygon(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    """
    Even-odd ray-casting point-in-polygon test.
    Ring is a sequence of (x, y) tuples; it may be open or closed.
    """
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + _EPS) + xi):
            inside = not inside
        j = i
    return inside


def _polygon_bbox(ring: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) for a polygon ring."""
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _distance_to_polygon_edge(
    x: float, y: float, ring: list[tuple[float, float]]
) -> float:
    """
    Minimum distance from (x, y) to the nearest edge of the polygon ring.
    Used to compute the daylight distance for side-slope grading.
    """
    min_dist = math.inf
    n = len(ring)
    j = n - 1
    for i in range(n):
        ax, ay = ring[j]
        bx, by = ring[i]
        dx = bx - ax
        dy = by - ay
        len2 = dx * dx + dy * dy
        if len2 < _EPS:
            d = math.hypot(x - ax, y - ay)
        else:
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / len2))
            px = ax + t * dx
            py = ay + t * dy
            d = math.hypot(x - px, y - py)
        if d < min_dist:
            min_dist = d
    return min_dist


# ---------------------------------------------------------------------------
# Design surface
# ---------------------------------------------------------------------------

@dataclass
class DesignSurface:
    """
    Proposed design surface (pad / graded platform).

    Parameters
    ----------
    pad_elevation : float
        Flat pad elevation (metres) for the platform interior.
    polygon : list[tuple[float, float]]
        Boundary ring of the pad as (x, y) tuples (at least 3 points).
    side_slope_ratio : float
        Horizontal run per 1 m of vertical change (e.g. 2.0 for 1V:2H).
        Zero or negative means no side slopes — elevation outside the
        polygon boundary is not defined (returns None).
    sloped : bool
        If True, interpret the surface as a tilted plane using
        ``dz_dx`` and ``dz_dy`` in addition to ``pad_elevation``
        (which becomes the elevation at the polygon centroid).
    dz_dx : float
        Rate of elevation change per metre in the X direction (m/m).
        Only used when sloped == True.
    dz_dy : float
        Rate of elevation change per metre in the Y direction (m/m).
        Only used when sloped == True.
    """
    pad_elevation: float
    polygon: list[tuple[float, float]]
    side_slope_ratio: float = 0.0
    sloped: bool = False
    dz_dx: float = 0.0
    dz_dy: float = 0.0

    def _centroid(self) -> tuple[float, float]:
        n = len(self.polygon)
        cx = sum(p[0] for p in self.polygon) / n
        cy = sum(p[1] for p in self.polygon) / n
        return cx, cy

    def elevation_at(self, x: float, y: float) -> Optional[float]:
        """
        Return the design elevation at (x, y).

        Inside the polygon:
            flat pad → pad_elevation
            sloped pad → pad_elevation + dz_dx*(x-cx) + dz_dy*(y-cy)
        Outside the polygon (with side slope):
            elev = inside_elevation + dist_to_edge / side_slope_ratio
            (slope rises away from the cut — for fill-side grading use the
             correct sign based on whether the pad is above or below terrain;
             here we compute absolute daylight elevation purely kinematically)
        Outside the polygon (no side slope):
            None
        """
        inside = _point_in_polygon(x, y, self.polygon)

        if self.sloped:
            cx, cy = self._centroid()
            base = self.pad_elevation + self.dz_dx * (x - cx) + self.dz_dy * (y - cy)
        else:
            base = self.pad_elevation

        if inside:
            return base

        # Outside pad boundary
        if self.side_slope_ratio <= 0:
            return None

        dist = _distance_to_polygon_edge(x, y, self.polygon)
        # Elevation steps up from pad edge at 1V:nH.
        return base + dist / self.side_slope_ratio

    def validate(self) -> list[str]:
        """Return a list of validation error strings, empty if valid."""
        errors: list[str] = []
        if not isinstance(self.polygon, (list, tuple)) or len(self.polygon) < 3:
            errors.append("polygon must have at least 3 vertices")
        if self.side_slope_ratio < 0:
            errors.append("side_slope_ratio must be >= 0")
        return errors


# ---------------------------------------------------------------------------
# Earthwork result
# ---------------------------------------------------------------------------

@dataclass
class EarthworkResult:
    """
    Result of an earthwork cut/fill computation.

    Attributes
    ----------
    cut_m3 : float
        Total cut volume in cubic metres (material removed).
    fill_m3 : float
        Total fill volume in cubic metres (material added).
    net_m3 : float
        Net = fill - cut. Positive → more fill needed; negative → surplus.
    balance_ratio : float
        cut_m3 / fill_m3. Value ≈ 1.0 means balanced earthwork.
        float('inf') when fill_m3 == 0; 0.0 when cut_m3 == 0.
    sample_count : int
        Number of grid sample points used.
    grid_spacing_m : float
        Grid spacing used for sampling.
    cell_area_m2 : float
        Area of each sample cell (grid_spacing²).
    """
    cut_m3: float
    fill_m3: float
    net_m3: float
    balance_ratio: float
    sample_count: int
    grid_spacing_m: float
    cell_area_m2: float

    def to_dict(self) -> dict:
        return {
            "cut_m3": round(self.cut_m3, 4),
            "fill_m3": round(self.fill_m3, 4),
            "net_m3": round(self.net_m3, 4),
            "balance_ratio": round(self.balance_ratio, 4)
            if math.isfinite(self.balance_ratio) else None,
            "sample_count": self.sample_count,
            "grid_spacing_m": self.grid_spacing_m,
            "cell_area_m2": round(self.cell_area_m2, 6),
            "note": _balance_note(self.balance_ratio),
        }


def _balance_note(ratio: float) -> str:
    if not math.isfinite(ratio):
        return "All cut; no fill required."
    if ratio == 0.0:
        return "All fill; no cut required."
    if 0.9 <= ratio <= 1.1:
        return "Earthwork is approximately balanced (ratio ≈ 1.0)."
    if ratio > 1.0:
        return "More cut than fill — surplus material to export."
    return "More fill than cut — import material required."


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

def compute_earthwork(
    tin: TIN,
    design: DesignSurface,
    grid_spacing: float = 1.0,
) -> EarthworkResult:
    """
    Compute cut/fill volumes by grid-sampling between the existing TIN and the
    design surface.

    Parameters
    ----------
    tin : TIN
        Existing ground surface.
    design : DesignSurface
        Proposed design surface.
    grid_spacing : float
        Sample spacing in metres (default 1.0 m).  Smaller = more accurate.

    Returns
    -------
    EarthworkResult

    Algorithm
    ---------
    1. Bounding box from TIN point extents.
    2. Regular grid at `grid_spacing` intervals.
    3. At each node, interpolate z_exist from TIN (skip if outside TIN).
    4. Get z_design from DesignSurface.elevation_at (skip if None).
    5. Δz = z_design − z_exist:
           Δz > 0 → fill (raise terrain)
           Δz < 0 → cut  (lower terrain)
    6. Multiply by cell_area = grid_spacing².
    """
    if grid_spacing <= 0:
        raise ValueError(f"grid_spacing must be > 0; got {grid_spacing}")

    xs_pts = [p.x for p in tin.points]
    ys_pts = [p.y for p in tin.points]
    min_x, max_x = min(xs_pts), max(xs_pts)
    min_y, max_y = min(ys_pts), max(ys_pts)

    cell_area = grid_spacing * grid_spacing
    cut_vol = 0.0
    fill_vol = 0.0
    sample_count = 0

    # Grid nodes: half-step offset to centre cells.
    x = min_x + grid_spacing * 0.5
    while x <= max_x + _EPS:
        y = min_y + grid_spacing * 0.5
        while y <= max_y + _EPS:
            z_exist = tin.interpolate_z(x, y)
            if z_exist is not None:
                z_design = design.elevation_at(x, y)
                if z_design is not None:
                    dz = z_design - z_exist
                    if dz > 0:
                        fill_vol += dz * cell_area
                    elif dz < 0:
                        cut_vol += (-dz) * cell_area
                    sample_count += 1
            y += grid_spacing
        x += grid_spacing

    net = fill_vol - cut_vol
    if fill_vol > _EPS:
        balance = cut_vol / fill_vol
    elif cut_vol > _EPS:
        balance = math.inf
    else:
        balance = 1.0  # trivially balanced (zero earthwork)

    return EarthworkResult(
        cut_m3=cut_vol,
        fill_m3=fill_vol,
        net_m3=net,
        balance_ratio=balance,
        sample_count=sample_count,
        grid_spacing_m=grid_spacing,
        cell_area_m2=cell_area,
    )


# ---------------------------------------------------------------------------
# Validation helper (used by tools.py)
# ---------------------------------------------------------------------------

def validate_polygon(polygon: object) -> list[str]:
    """Return validation errors for a polygon specification."""
    errors: list[str] = []
    if not isinstance(polygon, (list, tuple)):
        errors.append("polygon must be a list of [x, y] pairs")
        return errors
    if len(polygon) < 3:
        errors.append(f"polygon must have at least 3 vertices; got {len(polygon)}")
        return errors
    ring: list[tuple[float, float]] = []
    for i, item in enumerate(polygon):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            errors.append(f"polygon[{i}]: must be [x, y]")
            continue
        try:
            ring.append((float(item[0]), float(item[1])))
        except (TypeError, ValueError) as exc:
            errors.append(f"polygon[{i}]: {exc}")
    return errors
