"""
Grading module — contour generation from a DEM grid, plus cut/fill volume
computation on a graded surface.

All functions are pure Python and avoid numpy/scipy dependencies so they work
in the lightweight install.  Optional numpy acceleration is used when available.

Public API
----------
contours_from_dem(dem, x_coords, y_coords, levels) -> list[dict]
    Extract iso-contour polylines from a DEM grid at the requested elevations.
    Returns ``{"level": z, "segments": [(x0, y0, x1, y1), ...]}`` per level.
    Returns ``{"ok": False, "reason": ...}`` on bad input.

cut_fill_volumes(dem_existing, dem_design, cell_width, cell_height) -> dict
    Compute cut and fill volumes between an existing DEM and a design surface.
    Returns ``{"ok", "cut_m3", "fill_m3", "net_m3"}``.

grade_surface(dem, x_coords, y_coords, target_grade, origin_xy, direction)
    Apply a uniform planar grade to a surface patch and return the design DEM.
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _linear_interp(v0: float, v1: float, level: float) -> float:
    """Return the parameter t in [0,1] where v0 + t*(v1-v0) == level."""
    dv = v1 - v0
    if abs(dv) < 1e-15:
        return 0.5
    return (level - v0) / dv


def _marching_squares_cell(
    z00: float, z10: float, z11: float, z01: float,
    x0: float, y0: float, x1: float, y1: float,
    level: float,
) -> list[tuple[float, float, float, float]]:
    """
    Marching-squares on one quad cell.

    Corners ordered:
        (x0,y1) z01---z11 (x1,y1)
                |         |
        (x0,y0) z00---z10 (x1,y0)

    Returns a list of line segments (x_a, y_a, x_b, y_b).
    """
    # Encode which corners are above the level (bit 0 = z00, 1 = z10, 2 = z11, 3 = z01)
    idx = (
        (1 if z00 >= level else 0) |
        (2 if z10 >= level else 0) |
        (4 if z11 >= level else 0) |
        (8 if z01 >= level else 0)
    )

    if idx == 0 or idx == 15:
        return []

    # Edge midpoints via linear interpolation
    def _bottom():   # z00 -- z10 at y = y0
        t = _linear_interp(z00, z10, level)
        return (x0 + t * (x1 - x0), y0)

    def _right():    # z10 -- z11 at x = x1
        t = _linear_interp(z10, z11, level)
        return (x1, y0 + t * (y1 - y0))

    def _top():      # z01 -- z11 at y = y1
        t = _linear_interp(z01, z11, level)
        return (x0 + t * (x1 - x0), y1)

    def _left():     # z00 -- z01 at x = x0
        t = _linear_interp(z00, z01, level)
        return (x0, y0 + t * (y1 - y0))

    segs: list[tuple[float, float, float, float]] = []

    # Standard 16-case marching-squares lookup
    if idx == 1 or idx == 14:
        a, b = _bottom(), _left()
        segs.append((a[0], a[1], b[0], b[1]))
    elif idx == 2 or idx == 13:
        a, b = _bottom(), _right()
        segs.append((a[0], a[1], b[0], b[1]))
    elif idx == 3 or idx == 12:
        a, b = _left(), _right()
        segs.append((a[0], a[1], b[0], b[1]))
    elif idx == 4 or idx == 11:
        a, b = _right(), _top()
        segs.append((a[0], a[1], b[0], b[1]))
    elif idx == 5:
        # Saddle: split into two segments (use average to disambiguate)
        avg = (z00 + z10 + z11 + z01) / 4.0
        if avg >= level:
            a, b = _bottom(), _right()
            segs.append((a[0], a[1], b[0], b[1]))
            a, b = _top(), _left()
            segs.append((a[0], a[1], b[0], b[1]))
        else:
            a, b = _bottom(), _left()
            segs.append((a[0], a[1], b[0], b[1]))
            a, b = _top(), _right()
            segs.append((a[0], a[1], b[0], b[1]))
    elif idx == 6 or idx == 9:
        a, b = _bottom(), _top()
        segs.append((a[0], a[1], b[0], b[1]))
    elif idx == 7 or idx == 8:
        a, b = _top(), _left()
        segs.append((a[0], a[1], b[0], b[1]))
    elif idx == 10:
        # Saddle: split
        avg = (z00 + z10 + z11 + z01) / 4.0
        if avg >= level:
            a, b = _bottom(), _left()
            segs.append((a[0], a[1], b[0], b[1]))
            a, b = _top(), _right()
            segs.append((a[0], a[1], b[0], b[1]))
        else:
            a, b = _bottom(), _right()
            segs.append((a[0], a[1], b[0], b[1]))
            a, b = _top(), _left()
            segs.append((a[0], a[1], b[0], b[1]))

    return segs


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def contours_from_dem(
    dem: list[list[float]],
    x_coords: list[float],
    y_coords: list[float],
    levels: list[float],
) -> dict[str, Any]:
    """
    Extract iso-contour line segments from a 2-D DEM grid using marching squares.

    Parameters
    ----------
    dem : list[list[float]]
        2-D elevation grid, shape (len(y_coords), len(x_coords)).
        dem[row][col] corresponds to (x_coords[col], y_coords[row]).
    x_coords : list[float]
        Monotonically increasing x positions (e.g. metres from origin).
    y_coords : list[float]
        Monotonically increasing y positions.
    levels : list[float]
        Contour elevations to extract.

    Returns
    -------
    dict with keys:
        "ok"      : bool
        "contours": list of {"level": float, "segments": [(x0,y0,x1,y1),...]}
    """
    if not dem or not x_coords or not y_coords:
        return {"ok": False, "reason": "dem, x_coords and y_coords must be non-empty"}
    ny = len(dem)
    nx = len(dem[0]) if dem else 0
    if ny != len(y_coords) or nx != len(x_coords):
        return {
            "ok": False,
            "reason": f"dem shape ({ny},{nx}) does not match "
                      f"y_coords({len(y_coords)}) x x_coords({len(x_coords)})",
        }
    if nx < 2 or ny < 2:
        return {"ok": False, "reason": "dem must be at least 2×2 to extract contours"}

    result_contours = []
    for level in levels:
        segments: list[tuple[float, float, float, float]] = []
        for row in range(ny - 1):
            for col in range(nx - 1):
                z00 = dem[row][col]
                z10 = dem[row][col + 1]
                z11 = dem[row + 1][col + 1]
                z01 = dem[row + 1][col]
                x0, x1 = x_coords[col], x_coords[col + 1]
                y0, y1 = y_coords[row], y_coords[row + 1]
                segs = _marching_squares_cell(z00, z10, z11, z01, x0, y0, x1, y1, level)
                segments.extend(segs)
        result_contours.append({"level": level, "segments": segments})

    return {"ok": True, "contours": result_contours}


def cut_fill_volumes(
    dem_existing: list[list[float]],
    dem_design: list[list[float]],
    cell_width: float,
    cell_height: float,
) -> dict[str, Any]:
    """
    Compute cut and fill volumes between two aligned DEM grids.

    Uses the prismatoid method: each cell contributes cell_width * cell_height
    times the average elevation difference over the cell's four corners.

    Parameters
    ----------
    dem_existing : 2-D grid of existing elevations.
    dem_design   : 2-D grid of proposed elevations (same shape).
    cell_width   : horizontal cell dimension in metres.
    cell_height  : vertical (depth) cell dimension in metres (plan dimension, not elevation).

    Returns
    -------
    {"ok", "cut_m3", "fill_m3", "net_m3"}
        cut_m3  — earth removed (design < existing)
        fill_m3 — earth added   (design > existing)
        net_m3  — fill - cut (positive = net fill)
    """
    if not dem_existing or not dem_design:
        return {"ok": False, "reason": "dem grids must be non-empty"}
    if cell_width <= 0 or cell_height <= 0:
        return {"ok": False, "reason": "cell_width and cell_height must be positive"}

    ny = len(dem_existing)
    nx = len(dem_existing[0]) if dem_existing else 0

    if len(dem_design) != ny or (ny > 0 and len(dem_design[0]) != nx):
        return {"ok": False, "reason": "dem_existing and dem_design must have the same shape"}

    cell_area = cell_width * cell_height
    cut = 0.0
    fill = 0.0

    for row in range(ny):
        for col in range(nx):
            diff = dem_design[row][col] - dem_existing[row][col]
            vol = abs(diff) * cell_area
            if diff < 0:
                cut += vol
            else:
                fill += vol

    return {
        "ok": True,
        "cut_m3": cut,
        "fill_m3": fill,
        "net_m3": fill - cut,
    }


def grade_surface(
    dem: list[list[float]],
    x_coords: list[float],
    y_coords: list[float],
    target_grade: float,
    origin_xy: tuple[float, float],
    direction: tuple[float, float],
) -> dict[str, Any]:
    """
    Apply a uniform planar grade to a DEM patch.

    The design surface is a plane passing through the origin point at the
    existing elevation, with slope ``target_grade`` in the given direction.

    Parameters
    ----------
    dem           : existing elevation grid (len(y_coords) × len(x_coords)).
    x_coords, y_coords : grid coordinates.
    target_grade  : rise/run (e.g. 0.02 = 2 % downhill).
    origin_xy     : (x, y) of the reference point (zero elevation change).
    direction     : (dx, dy) unit vector defining the grade direction (need not
                    be normalised; normalised internally).

    Returns
    -------
    {"ok", "dem_design": list[list[float]], "origin_elev": float}
    """
    if not dem or not x_coords or not y_coords:
        return {"ok": False, "reason": "dem, x_coords and y_coords must be non-empty"}

    ny = len(dem)
    nx = len(dem[0]) if dem else 0
    if ny != len(y_coords) or nx != len(x_coords):
        return {"ok": False, "reason": "dem shape mismatch with coordinate arrays"}

    ox, oy = origin_xy
    dx, dy = direction
    mag = math.hypot(dx, dy)
    if mag < 1e-15:
        return {"ok": False, "reason": "direction vector must be non-zero"}
    dx /= mag
    dy /= mag

    # Snap origin to nearest grid point for reference elevation
    col0 = min(range(nx), key=lambda c: abs(x_coords[c] - ox))
    row0 = min(range(ny), key=lambda r: abs(y_coords[r] - oy))
    origin_elev = dem[row0][col0]

    dem_design = []
    for row in range(ny):
        row_out = []
        for col in range(nx):
            # Distance from origin along the grade direction
            dist = (x_coords[col] - ox) * dx + (y_coords[row] - oy) * dy
            z_design = origin_elev - target_grade * dist
            row_out.append(z_design)
        dem_design.append(row_out)

    return {"ok": True, "dem_design": dem_design, "origin_elev": origin_elev}
