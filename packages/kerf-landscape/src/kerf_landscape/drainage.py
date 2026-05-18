"""
Drainage module — surface runoff via the Rational Method and D8 flow
accumulation on a DEM grid.

References
----------
* American Society of Civil Engineers (ASCE) / WEF Manual of Engineering Practice
  No. 92 "Design and Construction of Urban Stormwater Management Systems" (1992)
* Chow, Maidment & Mays, "Applied Hydrology", McGraw-Hill (1988)
* O'Callaghan & Mark (1984), "The extraction of drainage networks from digital
  elevation models", Computer Vision, Graphics and Image Processing, 28, 323-344.

Public API
----------
rational_method(C, i_in_per_hr, A_acres) -> dict
    Q = C · i · A   (peak runoff in cfs and m³/s)

flow_accumulation_d8(dem, cell_size) -> dict
    D8 single-direction flow routing; returns upstream cell counts and the
    flat list of outlet cells (cells draining off-grid or into no-data).

catchment_runoff(dem, x_coords, y_coords, C_grid, design_storm_in_per_hr) -> dict
    Full catchment: split into contributing areas, apply rational method per
    sub-catchment, return total peak flow and per-cell flow accumulation.
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 1 acre = 43,560 ft²;  1 ft = 0.3048 m  →  1 ft³/s = 0.028316846 m³/s
_CFS_TO_M3S = 0.028316846


# ---------------------------------------------------------------------------
# Rational Method
# ---------------------------------------------------------------------------

def rational_method(
    C: float,
    i_in_per_hr: float,
    A_acres: float,
) -> dict[str, Any]:
    """
    Compute peak surface runoff using the Rational Method.

    Q = C · i · A

    where Q is in ft³/s (cfs) when i is in in/hr and A is in acres.

    Parameters
    ----------
    C           : runoff coefficient (dimensionless, 0–1).
    i_in_per_hr : rainfall intensity [in/hr].
    A_acres     : drainage area [acres].

    Returns
    -------
    {"ok", "Q_cfs", "Q_m3s"}
        Q_cfs  — peak flow [ft³/s]
        Q_m3s  — peak flow [m³/s]
    """
    if not (0.0 <= C <= 1.0):
        return {"ok": False, "reason": "C must be between 0 and 1"}
    if i_in_per_hr < 0:
        return {"ok": False, "reason": "i_in_per_hr must be non-negative"}
    if A_acres < 0:
        return {"ok": False, "reason": "A_acres must be non-negative"}

    Q_cfs = C * i_in_per_hr * A_acres
    Q_m3s = Q_cfs * _CFS_TO_M3S

    return {
        "ok": True,
        "Q_cfs": Q_cfs,
        "Q_m3s": Q_m3s,
        "C": C,
        "i_in_per_hr": i_in_per_hr,
        "A_acres": A_acres,
    }


# ---------------------------------------------------------------------------
# D8 flow routing
# ---------------------------------------------------------------------------

# D8 neighbour offsets (row_delta, col_delta) and their approximate distances
# in multiples of cell_size.  Diagonal cells are sqrt(2) farther.
_D8_NEIGHBOURS = [
    (-1, -1, math.sqrt(2)),
    (-1,  0, 1.0),
    (-1,  1, math.sqrt(2)),
    ( 0, -1, 1.0),
    ( 0,  1, 1.0),
    ( 1, -1, math.sqrt(2)),
    ( 1,  0, 1.0),
    ( 1,  1, math.sqrt(2)),
]


def _d8_flow_dir(dem: list[list[float]], ny: int, nx: int) -> list[list[int | None]]:
    """
    Compute D8 flow direction for every cell.

    Returns a grid where each value is the linear index (row*nx+col) of the
    downstream cell, or None if the cell drains off-grid or is a local minimum.
    """
    flow = [[None] * nx for _ in range(ny)]

    for row in range(ny):
        for col in range(nx):
            z = dem[row][col]
            best_slope = 0.0
            best_idx: int | None = None
            for dr, dc, dist in _D8_NEIGHBOURS:
                nr, nc = row + dr, col + dc
                if 0 <= nr < ny and 0 <= nc < nx:
                    slope = (z - dem[nr][nc]) / dist
                    if slope > best_slope:
                        best_slope = slope
                        best_idx = nr * nx + nc
            # If best_idx is None, cell drains off-grid or is a pit
            # Edge cells with no steeper neighbour drain off-grid (None)
            flow[row][col] = best_idx

    return flow


def flow_accumulation_d8(
    dem: list[list[float]],
    cell_size: float = 1.0,
) -> dict[str, Any]:
    """
    D8 flow accumulation on a DEM grid.

    Each cell starts with 1 unit.  Flow is routed downstream following the
    steepest descent (D8 single-direction).  The accumulation at each cell is
    the total number of upstream cells (including itself).

    Parameters
    ----------
    dem       : 2-D elevation grid.
    cell_size : grid spacing [m] (used for slope computation, does not affect
                the cell-count accumulation).

    Returns
    -------
    {"ok", "accumulation": list[list[int]], "outlets": list[(row, col)]}
        accumulation — upstream cell counts (same shape as dem).
        outlets      — cells that drain off-grid (watershed boundary).
    """
    if not dem or not dem[0]:
        return {"ok": False, "reason": "dem must be non-empty"}
    if cell_size <= 0:
        return {"ok": False, "reason": "cell_size must be positive"}

    ny = len(dem)
    nx = len(dem[0])

    flow = _d8_flow_dir(dem, ny, nx)

    # Topological sort (Kahn's algorithm on the flow DAG)
    # in_degree[i] = number of cells that flow INTO cell i
    in_degree = [0] * (ny * nx)
    for row in range(ny):
        for col in range(nx):
            downstream = flow[row][col]
            if downstream is not None:
                in_degree[downstream] += 1

    # Start from cells with no incoming flow (headwater cells)
    queue = [row * nx + col
             for row in range(ny) for col in range(nx)
             if in_degree[row * nx + col] == 0]

    accum = [1] * (ny * nx)   # each cell counts itself

    while queue:
        idx = queue.pop()
        downstream = flow[idx // nx][idx % nx]
        if downstream is not None:
            accum[downstream] += accum[idx]
            in_degree[downstream] -= 1
            if in_degree[downstream] == 0:
                queue.append(downstream)

    # Reshape to 2-D
    accum_2d = [[accum[row * nx + col] for col in range(nx)] for row in range(ny)]

    # Outlets: cells that flow off-grid (flow direction is None)
    outlets = [
        (row, col)
        for row in range(ny) for col in range(nx)
        if flow[row][col] is None and any(
            0 <= row + dr < ny and 0 <= col + dc < nx
            for dr, dc, _ in _D8_NEIGHBOURS
        )
        or (flow[row][col] is None and (row == 0 or row == ny - 1 or col == 0 or col == nx - 1))
    ]

    return {
        "ok": True,
        "accumulation": accum_2d,
        "outlets": outlets,
    }


# ---------------------------------------------------------------------------
# Full catchment runoff
# ---------------------------------------------------------------------------

def catchment_runoff(
    dem: list[list[float]],
    x_coords: list[float],
    y_coords: list[float],
    C_grid: list[list[float]],
    design_storm_in_per_hr: float,
) -> dict[str, Any]:
    """
    Compute peak runoff for a catchment using flow accumulation + Rational Method.

    Each cell's contributing area is the flow-accumulation count multiplied by
    the cell area.  The peak flow at each outlet is computed using the area-
    weighted average runoff coefficient from the upstream cells.

    Parameters
    ----------
    dem                   : 2-D elevation grid.
    x_coords, y_coords    : grid coordinate arrays.
    C_grid                : runoff coefficient per cell (0–1), same shape as dem.
    design_storm_in_per_hr: rainfall intensity [in/hr].

    Returns
    -------
    {"ok", "total_Q_cfs", "total_Q_m3s",
     "accumulation": list[list[int]],
     "C_weighted": list[list[float]]}
    """
    if not dem or not x_coords or not y_coords:
        return {"ok": False, "reason": "inputs must be non-empty"}

    ny = len(dem)
    nx = len(dem[0]) if dem else 0
    if len(C_grid) != ny or (ny and len(C_grid[0]) != nx):
        return {"ok": False, "reason": "C_grid must have the same shape as dem"}

    if design_storm_in_per_hr < 0:
        return {"ok": False, "reason": "design_storm_in_per_hr must be non-negative"}

    # Infer cell size from coordinate arrays
    if nx < 2 or ny < 2:
        return {"ok": False, "reason": "grid must be at least 2×2"}

    cell_w = (x_coords[-1] - x_coords[0]) / (nx - 1)
    cell_h = (y_coords[-1] - y_coords[0]) / (ny - 1)
    cell_area_m2 = abs(cell_w * cell_h)
    # 1 acre = 4046.856 m²
    cell_area_acres = cell_area_m2 / 4046.856

    fa_result = flow_accumulation_d8(dem, cell_size=max(abs(cell_w), abs(cell_h)))
    if not fa_result["ok"]:
        return fa_result

    accum = fa_result["accumulation"]

    # Flow direction for weighted-C propagation
    flow = _d8_flow_dir(dem, ny, nx)

    # Accumulate C×count (to compute area-weighted average C at each cell)
    c_accum = [C_grid[r][c] for r in range(ny) for c in range(nx)]

    in_degree = [0] * (ny * nx)
    for row in range(ny):
        for col in range(nx):
            ds = flow[row][col]
            if ds is not None:
                in_degree[ds] += 1

    queue = [row * nx + col
             for row in range(ny) for col in range(nx)
             if in_degree[row * nx + col] == 0]

    # Track accumulated C*count
    c_count = [C_grid[row][col] for row in range(ny) for col in range(nx)]

    while queue:
        idx = queue.pop()
        ds = flow[idx // nx][idx % nx]
        if ds is not None:
            c_accum[ds] += c_accum[idx]
            in_degree[ds] -= 1
            if in_degree[ds] == 0:
                queue.append(ds)

    # C_weighted at each cell = c_accum / accum (flat)
    c_weighted_flat = [
        c_accum[i] / accum[i // nx][i % nx]
        if accum[i // nx][i % nx] > 0 else 0.0
        for i in range(ny * nx)
    ]
    c_weighted_2d = [[c_weighted_flat[row * nx + col] for col in range(nx)] for row in range(ny)]

    # Total peak flow = sum over all outlet cells
    outlets = fa_result["outlets"]
    total_Q_cfs = 0.0
    seen_outlet_set = set()
    for row, col in outlets:
        key = row * nx + col
        if key in seen_outlet_set:
            continue
        seen_outlet_set.add(key)
        A_acres = accum[row][col] * cell_area_acres
        C_eff = c_weighted_2d[row][col]
        q = rational_method(C_eff, design_storm_in_per_hr, A_acres)
        if q["ok"]:
            total_Q_cfs += q["Q_cfs"]

    return {
        "ok": True,
        "total_Q_cfs": total_Q_cfs,
        "total_Q_m3s": total_Q_cfs * _CFS_TO_M3S,
        "accumulation": accum,
        "C_weighted": c_weighted_2d,
    }
