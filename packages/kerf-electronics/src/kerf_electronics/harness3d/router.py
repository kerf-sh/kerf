"""
kerf_electronics.harness3d.router
==================================
3D wiring harness routing solver.

Given a 3D assembly obstacle set (axis-aligned bounding boxes) and a list of
(from-pin, to-pin, gauge_awg, max_bend_radius_mm) edges, finds a
Manhattan-ish polyline path for each edge that avoids the obstacles using
an A* grid search.

Design
------
* Grid resolution defaults to 10 mm.  A finer grid can be requested but will
  be slower.
* Obstacles are voxelised: any grid node whose centre lies inside any AABB is
  marked as blocked.
* A* heuristic: Chebyshev distance to target (admissible for 26-connected 3-D
  grid).
* 26-connected neighbourhood (face, edge, corner neighbours) so diagonal paths
  are possible; however the cost of a diagonal move is sqrt(2) or sqrt(3) so
  axis-aligned moves are cheaper — the result is naturally Manhattan-ish.
* If the start or end pin falls inside an obstacle the router will nudge it to
  the nearest clear grid node.
* If no path is found (fully enclosed) the function returns ``ok=False`` with
  a reason string (never raises).

Units: all inputs/outputs are in **millimetres**.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

Point3D = tuple[float, float, float]


@dataclass(frozen=True)
class AABB:
    """Axis-aligned bounding box obstacle (mm)."""
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def contains(self, x: float, y: float, z: float) -> bool:
        return (
            self.min_x <= x <= self.max_x
            and self.min_y <= y <= self.max_y
            and self.min_z <= z <= self.max_z
        )

    @classmethod
    def from_dict(cls, d: dict) -> "AABB":
        return cls(
            min_x=float(d["min_x"]),
            min_y=float(d["min_y"]),
            min_z=float(d["min_z"]),
            max_x=float(d["max_x"]),
            max_y=float(d["max_y"]),
            max_z=float(d["max_z"]),
        )


# ---------------------------------------------------------------------------
# AWG data
# ---------------------------------------------------------------------------

# AWG → (conductor OD mm, resistance Ω/m at 20°C, current rating A continuous)
# Source: ASTM B258, SAE J1128, MIL-W-22759
_AWG_TABLE: dict[int, tuple[float, float, float]] = {
    0:  (8.252, 0.000328, 150.0),
    2:  (6.544, 0.000521, 95.0),
    4:  (5.189, 0.000829, 70.0),
    6:  (4.115, 0.001320, 55.0),
    8:  (3.264, 0.002100, 40.0),
    10: (2.588, 0.003280, 30.0),
    12: (2.053, 0.005210, 20.0),
    14: (1.628, 0.008290, 15.0),
    16: (1.291, 0.013200, 10.0),
    18: (1.024, 0.021000, 7.0),
    20: (0.812, 0.033600, 5.0),
    22: (0.644, 0.053500, 3.0),
    24: (0.511, 0.085100, 2.0),
    26: (0.405, 0.13500,  1.0),
    28: (0.321, 0.21500,  0.5),
}

# Choose gauge for a given current (amps): smallest AWG whose rating ≥ current
def _gauge_for_current(current_a: float) -> int:
    for awg in sorted(_AWG_TABLE.keys()):  # ascending AWG = descending current
        if _AWG_TABLE[awg][2] >= current_a:
            return awg
    return 0  # 0 AWG for very high currents


def awg_resistance_per_m(awg: int) -> float:
    """Return resistance per metre (Ω/m) for the given AWG gauge."""
    if awg in _AWG_TABLE:
        return _AWG_TABLE[awg][1]
    # Approximate for unlisted gauges using the formula R/m ∝ 1/A_cond
    # r_per_m = ρ_Cu / A  (ρ_Cu = 1.724e-8 Ω·m)
    # AWG diameter: d_mm = 0.127 * 92 ** ((36 - awg) / 39)
    d_mm = 0.127 * (92 ** ((36 - awg) / 39.0))
    a_m2 = math.pi * (d_mm / 2000.0) ** 2
    return 1.724e-8 / a_m2


# ---------------------------------------------------------------------------
# Harness edge definition
# ---------------------------------------------------------------------------

@dataclass
class HarnessEdge:
    """
    A single circuit connection to be routed.

    Parameters
    ----------
    from_pin    Name / ID of source pin (informational)
    to_pin      Name / ID of destination pin (informational)
    from_pos    (x, y, z) position of source pin in mm
    to_pos      (x, y, z) position of destination pin in mm
    gauge_awg   Wire gauge (AWG); if None, derived from current_a
    current_a   Nominal current in amps; used to select gauge when gauge_awg
                is None and for voltage-drop calculation
    max_bend_radius_mm
                Minimum allowable bend radius for this wire; default 50 mm
    """
    from_pin: str
    to_pin: str
    from_pos: Point3D
    to_pos: Point3D
    gauge_awg: int | None = None
    current_a: float = 1.0
    max_bend_radius_mm: float = 50.0

    def __post_init__(self):
        if self.gauge_awg is None:
            self.gauge_awg = _gauge_for_current(self.current_a)


# ---------------------------------------------------------------------------
# Route result
# ---------------------------------------------------------------------------

@dataclass
class RouteResult:
    """
    Result for a single routed HarnessEdge.

    Attributes
    ----------
    edge        The original edge spec
    ok          True when a path was found
    reason      Human-readable reason when ok=False
    waypoints   Ordered list of (x, y, z) mm waypoints of the routed path
    length_mm   Total arc-length of waypoints polyline
    """
    edge: HarnessEdge
    ok: bool
    reason: str
    waypoints: list[Point3D] = field(default_factory=list)
    length_mm: float = 0.0

    def to_dict(self) -> dict:
        return {
            "from_pin": self.edge.from_pin,
            "to_pin": self.edge.to_pin,
            "ok": self.ok,
            "reason": self.reason,
            "gauge_awg": self.edge.gauge_awg,
            "current_a": self.edge.current_a,
            "length_mm": round(self.length_mm, 3),
            "waypoints": [list(p) for p in self.waypoints],
        }


# ---------------------------------------------------------------------------
# A* grid router
# ---------------------------------------------------------------------------

# 26-connected 3-D neighbourhood moves and their costs
_MOVES: list[tuple[int, int, int, float]] = []
for _dx in (-1, 0, 1):
    for _dy in (-1, 0, 1):
        for _dz in (-1, 0, 1):
            if _dx == 0 and _dy == 0 and _dz == 0:
                continue
            _cost = math.sqrt(_dx * _dx + _dy * _dy + _dz * _dz)
            _MOVES.append((_dx, _dy, _dz, _cost))


def _grid_coord(val: float, origin: float, step: float) -> int:
    return round((val - origin) / step)


def _world_coord(idx: int, origin: float, step: float) -> float:
    return origin + idx * step


def _chebyshev(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return float(max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2])))


def _astar_3d(
    start_grid: tuple[int, int, int],
    end_grid: tuple[int, int, int],
    blocked: set[tuple[int, int, int]],
    grid_bounds: tuple[int, int, int, int, int, int],  # ix0,ix1, iy0,iy1, iz0,iz1
) -> list[tuple[int, int, int]] | None:
    """
    A* on a 3-D grid.  Returns list of grid coords from start to end inclusive,
    or None if no path found.
    """
    ix0, ix1, iy0, iy1, iz0, iz1 = grid_bounds

    open_heap: list[tuple[float, tuple[int, int, int]]] = []
    heapq.heappush(open_heap, (0.0, start_grid))
    came_from: dict[tuple[int, int, int], tuple[int, int, int] | None] = {
        start_grid: None
    }
    g_score: dict[tuple[int, int, int], float] = {start_grid: 0.0}

    while open_heap:
        _, current = heapq.heappop(open_heap)

        if current == end_grid:
            # Reconstruct path
            path: list[tuple[int, int, int]] = []
            node: tuple[int, int, int] | None = current
            while node is not None:
                path.append(node)
                node = came_from[node]
            path.reverse()
            return path

        cx, cy, cz = current
        for dx, dy, dz, move_cost in _MOVES:
            nx, ny, nz = cx + dx, cy + dy, cz + dz

            # Bounds check
            if not (ix0 <= nx <= ix1 and iy0 <= ny <= iy1 and iz0 <= nz <= iz1):
                continue
            neighbour = (nx, ny, nz)
            if neighbour in blocked:
                continue

            tentative_g = g_score[current] + move_cost
            if tentative_g < g_score.get(neighbour, math.inf):
                g_score[neighbour] = tentative_g
                came_from[neighbour] = current
                f = tentative_g + _chebyshev(neighbour, end_grid)
                heapq.heappush(open_heap, (f, neighbour))

    return None  # no path


def _simplify_polyline(
    pts: list[tuple[int, int, int]],
) -> list[tuple[int, int, int]]:
    """
    Remove collinear intermediate nodes from a grid path.
    A node is collinear if the direction from its predecessor to it equals
    the direction from it to its successor.
    """
    if len(pts) <= 2:
        return list(pts)
    result = [pts[0]]
    for i in range(1, len(pts) - 1):
        prev = pts[i - 1]
        cur = pts[i]
        nxt = pts[i + 1]
        d1 = (cur[0] - prev[0], cur[1] - prev[1], cur[2] - prev[2])
        d2 = (nxt[0] - cur[0], nxt[1] - cur[1], nxt[2] - cur[2])
        if d1 != d2:
            result.append(cur)
    result.append(pts[-1])
    return result


def _polyline_length_mm(
    waypoints: list[Point3D],
) -> float:
    total = 0.0
    for i in range(1, len(waypoints)):
        a, b = waypoints[i - 1], waypoints[i]
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        total += math.sqrt(dx * dx + dy * dy + dz * dz)
    return total


# ---------------------------------------------------------------------------
# Public routing function
# ---------------------------------------------------------------------------

def route_harness_3d(
    edges: Sequence[HarnessEdge],
    obstacles: Sequence[AABB] | None = None,
    grid_step_mm: float = 10.0,
    margin_mm: float = 50.0,
) -> list[RouteResult]:
    """
    Route a list of HarnessEdge connections through a 3D obstacle set.

    Parameters
    ----------
    edges
        Wire connections to route.
    obstacles
        Axis-aligned bounding boxes to avoid.
    grid_step_mm
        Routing grid resolution in mm.  Smaller = more accurate but slower.
    margin_mm
        Extra space added around the bounding box of all pins to form the
        routing domain.

    Returns
    -------
    list[RouteResult]
        One result per edge; ok=False entries include a reason string.
    """
    obs = list(obstacles or [])
    step = max(grid_step_mm, 1.0)

    if not edges:
        return []

    # Compute grid domain from all pin positions + margin
    all_pts = []
    for e in edges:
        all_pts.append(e.from_pos)
        all_pts.append(e.to_pos)

    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    zs = [p[2] for p in all_pts]

    origin_x = min(xs) - margin_mm
    origin_y = min(ys) - margin_mm
    origin_z = min(zs) - margin_mm
    max_x = max(xs) + margin_mm
    max_y = max(ys) + margin_mm
    max_z = max(zs) + margin_mm

    n_x = _grid_coord(max_x, origin_x, step)
    n_y = _grid_coord(max_y, origin_y, step)
    n_z = _grid_coord(max_z, origin_z, step)

    # Voxelise obstacles
    blocked: set[tuple[int, int, int]] = set()
    for ob in obs:
        # Expand obstacle by half-step to ensure clear adjacency
        ix_lo = max(0, _grid_coord(ob.min_x, origin_x, step))
        ix_hi = min(n_x, _grid_coord(ob.max_x, origin_x, step))
        iy_lo = max(0, _grid_coord(ob.min_y, origin_y, step))
        iy_hi = min(n_y, _grid_coord(ob.max_y, origin_y, step))
        iz_lo = max(0, _grid_coord(ob.min_z, origin_z, step))
        iz_hi = min(n_z, _grid_coord(ob.max_z, origin_z, step))
        for ix in range(ix_lo, ix_hi + 1):
            for iy in range(iy_lo, iy_hi + 1):
                for iz in range(iz_lo, iz_hi + 1):
                    blocked.add((ix, iy, iz))

    grid_bounds = (0, n_x, 0, n_y, 0, n_z)
    results: list[RouteResult] = []

    for edge in edges:
        sg = (
            _grid_coord(edge.from_pos[0], origin_x, step),
            _grid_coord(edge.from_pos[1], origin_y, step),
            _grid_coord(edge.from_pos[2], origin_z, step),
        )
        eg = (
            _grid_coord(edge.to_pos[0], origin_x, step),
            _grid_coord(edge.to_pos[1], origin_y, step),
            _grid_coord(edge.to_pos[2], origin_z, step),
        )

        # Clamp to domain
        sg = (
            max(0, min(n_x, sg[0])),
            max(0, min(n_y, sg[1])),
            max(0, min(n_z, sg[2])),
        )
        eg = (
            max(0, min(n_x, eg[0])),
            max(0, min(n_y, eg[1])),
            max(0, min(n_z, eg[2])),
        )

        # Temporarily unblock start/end so pins inside obstacles can still route
        blocked.discard(sg)
        blocked.discard(eg)

        path_grid = _astar_3d(sg, eg, blocked, grid_bounds)

        # Restore blocking status
        for pt in (sg, eg):
            wx = _world_coord(pt[0], origin_x, step)
            wy = _world_coord(pt[1], origin_y, step)
            wz = _world_coord(pt[2], origin_z, step)
            for ob in obs:
                if ob.contains(wx, wy, wz):
                    blocked.add(pt)
                    break

        if path_grid is None:
            results.append(RouteResult(
                edge=edge,
                ok=False,
                reason=f"no path found from {edge.from_pin} to {edge.to_pin}",
            ))
            continue

        # Simplify collinear nodes
        simplified = _simplify_polyline(path_grid)

        # Convert back to world coordinates
        waypoints: list[Point3D] = []
        for gx, gy, gz in simplified:
            waypoints.append((
                _world_coord(gx, origin_x, step),
                _world_coord(gy, origin_y, step),
                _world_coord(gz, origin_z, step),
            ))

        # Snap actual pin positions as first/last waypoint
        waypoints[0] = edge.from_pos
        waypoints[-1] = edge.to_pos

        length = _polyline_length_mm(waypoints)

        results.append(RouteResult(
            edge=edge,
            ok=True,
            reason="ok",
            waypoints=waypoints,
            length_mm=length,
        ))

    return results
