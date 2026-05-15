"""
kerf_cad_core.harness.route — 3D wiring harness routing.

Given connector endpoints, guide points (via-points), and optional obstacle
bounding boxes, this module:

  1. Builds a sequence of control points: start → guides → end.
  2. Smooths the path using Catmull-Rom spline sampling, producing a dense
     polyline.
  3. Computes total arc-length, minimum bend radius in the smoothed path, and
     checks it against the bundle's minimum allowable bend radius.
  4. Models T-split branches: each branch has its own guide list; branch paths
     are routed independently and then merged into a HarnessPath.
  5. Provides bundle_diameter() from wire count + gauge, and harness_bom() to
     roll up wire lengths per segment/branch.

Obstacle avoidance is not path-planned (no A*) — obstacles are noted and
the returned path is flagged if any control point lies inside an obstacle.
Full obstacle-avoiding path planning is out of scope for this primitive.

Units: metres (m).  Wire gauge OD constants are in millimetres then converted.

Catmull-Rom alpha=0.5 (centripetal) — avoids cusps and self-intersections
better than uniform parameterisation for arbitrary guide points.

Minimum bend radius check: the bend radius at each interior smoothed point is
approximated as R = ds / dtheta where ds is the segment length and dtheta is
the turn angle.  If any R < bundle_od * MIN_BEND_OD_RATIO the path is
flagged as failing the bend-radius check (ok=False, reported in result, but
never raised as an exception).

Author: imranparuk
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Typical minimum bend radius = 10× bundle OD (automotive standard).
MIN_BEND_OD_RATIO: float = 10.0

# Catmull-Rom samples per span (between two consecutive control points).
_CR_SAMPLES_PER_SPAN: int = 20

# AWG/metric wire gauge outer diameter lookup table (mm).
# Key: gauge string (e.g. "0.5", "0.75", "1.0", "1.5", "2.5", "4.0", "6.0")
# representing cross-section area in mm².
# Values: conductor OD (mm) — approximate; insulated OD adds ~0.4 mm each side.
_WIRE_OD_MM: dict[str, float] = {
    "0.35": 0.80,
    "0.5":  0.90,
    "0.75": 1.10,
    "1.0":  1.25,
    "1.5":  1.50,
    "2.5":  1.90,
    "4.0":  2.35,
    "6.0":  2.90,
    "10.0": 3.70,
    "16.0": 4.70,
    "25.0": 5.85,
    "35.0": 6.90,
}

# Insulation wall per side (mm) added to conductor OD.
_INSULATION_WALL_MM: float = 0.4

# Bundle packing factor: π/(2√3) ≈ 0.9069 (hexagonal close packing limit).
# We use 0.78 as a practical fill factor for round wires in a round bundle.
_BUNDLE_FILL_FACTOR: float = 0.78

# ---------------------------------------------------------------------------
# Vec3
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Vec3:
    """Immutable 3-D point / vector."""
    x: float
    y: float
    z: float

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, s: float) -> "Vec3":
        return Vec3(self.x * s, self.y * s, self.z * s)

    def __rmul__(self, s: float) -> "Vec3":
        return self.__mul__(s)

    def __truediv__(self, s: float) -> "Vec3":
        return Vec3(self.x / s, self.y / s, self.z / s)

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def norm(self) -> float:
        return math.sqrt(self.dot(self))

    def normalized(self) -> "Vec3":
        n = self.norm()
        if n < 1e-12:
            return Vec3(0.0, 0.0, 0.0)
        return self / n

    def dist(self, other: "Vec3") -> float:
        return (self - other).norm()

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.z]


def _vec3_from(pt: object) -> Vec3:
    """Parse a point from list/tuple/dict/{x,y,z} to Vec3."""
    if isinstance(pt, Vec3):
        return pt
    if isinstance(pt, (list, tuple)):
        if len(pt) < 3:
            raise ValueError(f"point must have 3 coordinates; got {pt}")
        return Vec3(float(pt[0]), float(pt[1]), float(pt[2]))
    if isinstance(pt, dict):
        try:
            return Vec3(float(pt["x"]), float(pt["y"]), float(pt["z"]))
        except KeyError as e:
            raise ValueError(f"point dict missing key {e}: {pt}") from e
    raise TypeError(f"cannot convert {type(pt).__name__} to Vec3")


# ---------------------------------------------------------------------------
# Catmull-Rom spline
# ---------------------------------------------------------------------------

def _catmull_rom_point(
    p0: Vec3, p1: Vec3, p2: Vec3, p3: Vec3, t: float, alpha: float = 0.5
) -> Vec3:
    """
    Evaluate centripetal Catmull-Rom spline at parameter t ∈ [0, 1]
    for segment p1→p2 with phantom points p0 and p3.

    alpha=0.5 is centripetal parameterisation.
    """
    def _tj(ti: float, pi: Vec3, pj: Vec3) -> float:
        d = pi.dist(pj)
        if d < 1e-12:
            return ti
        return ti + d ** alpha

    t0 = 0.0
    t1 = _tj(t0, p0, p1)
    t2 = _tj(t1, p1, p2)
    t3 = _tj(t2, p2, p3)

    # Remap t from [0,1] to [t1, t2]
    tr = t1 + t * (t2 - t1)

    def _lerp(a: Vec3, b: Vec3, ta: float, tb: float, tc: float) -> Vec3:
        if abs(tb - ta) < 1e-12:
            return a
        frac = (tc - ta) / (tb - ta)
        return a + (b - a) * frac

    a1 = _lerp(p0, p1, t0, t1, tr)
    a2 = _lerp(p1, p2, t1, t2, tr)
    a3 = _lerp(p2, p3, t2, t3, tr)

    b1 = _lerp(a1, a2, t0, t2, tr)
    b2 = _lerp(a2, a3, t1, t3, tr)

    return _lerp(b1, b2, t1, t2, tr)


def _smooth_polyline(control_points: list[Vec3], samples_per_span: int = _CR_SAMPLES_PER_SPAN) -> list[Vec3]:
    """
    Produce a smoothed polyline through control_points using centripetal
    Catmull-Rom splines.

    For N control points, N-1 spans are generated, each sampled at
    samples_per_span+1 points (last point of each span is the first of next,
    so deduplication is applied).

    Edge phantom points are reflections: p_phantom = 2*p0 - p1.
    """
    n = len(control_points)
    if n == 0:
        return []
    if n == 1:
        return [control_points[0]]
    if n == 2:
        # Linear interpolation (no curvature data for spline)
        pts: list[Vec3] = []
        p0, p1 = control_points[0], control_points[1]
        for i in range(samples_per_span + 1):
            t = i / samples_per_span
            pts.append(p0 + (p1 - p0) * t)
        return pts

    result: list[Vec3] = []
    # Phantom end points
    pts_ext = (
        [control_points[0] * 2 - control_points[1]]
        + control_points
        + [control_points[-1] * 2 - control_points[-2]]
    )

    for span in range(n - 1):
        p0 = pts_ext[span]
        p1 = pts_ext[span + 1]
        p2 = pts_ext[span + 2]
        p3 = pts_ext[span + 3]

        start_i = 0 if span == 0 else 1
        for i in range(start_i, samples_per_span + 1):
            t = i / samples_per_span
            result.append(_catmull_rom_point(p0, p1, p2, p3, t))

    return result


# ---------------------------------------------------------------------------
# Bend-radius check
# ---------------------------------------------------------------------------

def _polyline_length(pts: list[Vec3]) -> float:
    """Compute total arc-length of a polyline."""
    total = 0.0
    for i in range(1, len(pts)):
        total += pts[i - 1].dist(pts[i])
    return total


def _min_bend_radius(pts: list[Vec3]) -> float:
    """
    Estimate the minimum bend radius along a polyline.

    At each interior point i, compute:
        v_in  = pts[i] - pts[i-1]
        v_out = pts[i+1] - pts[i]
        dtheta = angle between v_in and v_out
        ds = 0.5 * (|v_in| + |v_out|)   (avg segment length around joint)
        R = ds / dtheta  (if dtheta > 0)

    Returns math.inf if the path is a straight line.
    """
    min_r = math.inf
    for i in range(1, len(pts) - 1):
        v_in = pts[i] - pts[i - 1]
        v_out = pts[i + 1] - pts[i]
        len_in = v_in.norm()
        len_out = v_out.norm()
        if len_in < 1e-12 or len_out < 1e-12:
            continue
        cos_theta = max(-1.0, min(1.0, v_in.dot(v_out) / (len_in * len_out)))
        dtheta = math.acos(cos_theta)
        if dtheta < 1e-9:
            continue
        ds = 0.5 * (len_in + len_out)
        r = ds / dtheta
        if r < min_r:
            min_r = r
    return min_r


# ---------------------------------------------------------------------------
# Obstacle check
# ---------------------------------------------------------------------------

@dataclass
class ObstacleBBox:
    """Axis-aligned bounding box obstacle."""
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def contains(self, p: Vec3) -> bool:
        return (
            self.min_x <= p.x <= self.max_x
            and self.min_y <= p.y <= self.max_y
            and self.min_z <= p.z <= self.max_z
        )


def _parse_obstacles(raw: list[dict]) -> list[ObstacleBBox]:
    obstacles = []
    for item in (raw or []):
        try:
            obstacles.append(ObstacleBBox(
                min_x=float(item["min_x"]),
                min_y=float(item["min_y"]),
                min_z=float(item["min_z"]),
                max_x=float(item["max_x"]),
                max_y=float(item["max_y"]),
                max_z=float(item["max_z"]),
            ))
        except (KeyError, TypeError, ValueError):
            pass  # skip malformed obstacles silently
    return obstacles


def _path_intersects_obstacles(pts: list[Vec3], obstacles: list[ObstacleBBox]) -> bool:
    """Return True if any path point lies inside any obstacle bbox."""
    for p in pts:
        for obs in obstacles:
            if obs.contains(p):
                return True
    return False


# ---------------------------------------------------------------------------
# Wire gauge / bundle diameter
# ---------------------------------------------------------------------------

def _wire_od_mm(gauge: str) -> float:
    """
    Return insulated wire outer diameter in mm for a gauge string (mm² area).
    Falls back to a formula for unknown gauges.
    """
    g = str(gauge).strip()
    if g in _WIRE_OD_MM:
        return _WIRE_OD_MM[g] + 2 * _INSULATION_WALL_MM
    # Fallback: conductor diameter from cross-section area
    try:
        area_mm2 = float(g)
        cond_d_mm = 2.0 * math.sqrt(area_mm2 / math.pi)
        return cond_d_mm + 2 * _INSULATION_WALL_MM
    except ValueError:
        return 2.5  # safe default (mm)


@dataclass
class WireSpec:
    """Specification for a set of wires in a harness."""
    gauge: str   # mm² cross-section area string, e.g. "1.0"
    count: int   # number of wires of this gauge


def bundle_diameter(wire_specs: list[WireSpec]) -> float:
    """
    Compute bundle outer diameter (metres) for a list of WireSpec.

    Method: sum insulated wire cross-section areas, apply bundle fill factor,
    compute equivalent circular bundle diameter.

        A_total = Σ (π/4 × od²)        [sum of insulated OD areas]
        A_bundle = A_total / fill_factor
        D_bundle = 2 × sqrt(A_bundle / π)

    Returns diameter in metres.  Minimum 1 wire enforced.
    """
    total_area_mm2 = 0.0
    for ws in wire_specs:
        od_mm = _wire_od_mm(ws.gauge)
        total_area_mm2 += math.pi / 4.0 * od_mm ** 2 * max(1, ws.count)

    if total_area_mm2 < 1e-12:
        return 0.001  # 1 mm minimum

    bundle_area_mm2 = total_area_mm2 / _BUNDLE_FILL_FACTOR
    d_mm = 2.0 * math.sqrt(bundle_area_mm2 / math.pi)
    return d_mm / 1000.0  # convert mm → m


# ---------------------------------------------------------------------------
# Segment and Branch models
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    """A single routed segment of a harness branch."""
    name: str
    control_points: list[Vec3]
    smoothed_points: list[Vec3]
    length_m: float
    wire_specs: list[WireSpec]
    bundle_od_m: float
    min_bend_radius_m: float
    bend_ok: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "control_points": [p.to_list() for p in self.control_points],
            "smoothed_point_count": len(self.smoothed_points),
            "length_m": round(self.length_m, 6),
            "bundle_od_mm": round(self.bundle_od_m * 1000, 3),
            "min_bend_radius_m": round(self.min_bend_radius_m, 6)
            if math.isfinite(self.min_bend_radius_m) else None,
            "bend_ok": self.bend_ok,
            "wire_count": sum(ws.count for ws in self.wire_specs),
            "wire_specs": [{"gauge": ws.gauge, "count": ws.count} for ws in self.wire_specs],
        }


@dataclass
class Branch:
    """
    A branch of the harness (T-split model).

    A harness may have one or more branches.  Each branch starts from a
    split point (or the main start connector) and terminates at a connector.
    """
    branch_id: str
    segments: list[Segment]

    @property
    def total_length_m(self) -> float:
        return sum(s.length_m for s in self.segments)

    @property
    def bend_ok(self) -> bool:
        return all(s.bend_ok for s in self.segments)

    def to_dict(self) -> dict:
        return {
            "branch_id": self.branch_id,
            "total_length_m": round(self.total_length_m, 6),
            "bend_ok": self.bend_ok,
            "segments": [s.to_dict() for s in self.segments],
        }


@dataclass
class HarnessPath:
    """
    Complete routed harness: one or more branches.

    ok          — False if any bend-radius violation or obstacle intersection
    reason      — human-readable reason when ok=False (never raised)
    branches    — list of Branch objects
    total_length_m — sum of all branch lengths
    bundle_od_m — maximum bundle OD across all segments
    """
    ok: bool
    reason: str
    branches: list[Branch]
    total_length_m: float
    bundle_od_m: float
    obstacles_hit: bool

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "total_length_m": round(self.total_length_m, 6),
            "bundle_od_mm": round(self.bundle_od_m * 1000, 3),
            "obstacles_hit": self.obstacles_hit,
            "branch_count": len(self.branches),
            "branches": [b.to_dict() for b in self.branches],
        }


# ---------------------------------------------------------------------------
# BOM
# ---------------------------------------------------------------------------

@dataclass
class BomEntry:
    """One line in the harness BOM."""
    gauge: str
    count: int
    segment_name: str
    branch_id: str
    length_m: float

    def to_dict(self) -> dict:
        return {
            "gauge": self.gauge,
            "count": self.count,
            "segment_name": self.segment_name,
            "branch_id": self.branch_id,
            "length_m": round(self.length_m, 6),
            "total_wire_length_m": round(self.length_m * self.count, 6),
        }


@dataclass
class BomResult:
    """Harness BOM rollup."""
    entries: list[BomEntry]
    # Totals per gauge: gauge → total_wire_length_m
    totals_by_gauge: dict[str, float]
    grand_total_wire_length_m: float

    def to_dict(self) -> dict:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "totals_by_gauge": {
                g: round(v, 6) for g, v in self.totals_by_gauge.items()
            },
            "grand_total_wire_length_m": round(self.grand_total_wire_length_m, 6),
        }


def harness_bom(harness: HarnessPath) -> BomResult:
    """
    Roll up harness wire lengths into a BOM.

    For each segment in each branch, multiply segment length_m × wire count
    for each gauge to produce per-segment BOM entries.  Then aggregate by
    gauge for totals.
    """
    entries: list[BomEntry] = []

    for branch in harness.branches:
        for seg in branch.segments:
            for ws in seg.wire_specs:
                entries.append(BomEntry(
                    gauge=ws.gauge,
                    count=ws.count,
                    segment_name=seg.name,
                    branch_id=branch.branch_id,
                    length_m=seg.length_m,
                ))

    totals: dict[str, float] = {}
    for e in entries:
        totals[e.gauge] = totals.get(e.gauge, 0.0) + e.length_m * e.count

    grand_total = sum(totals.values())

    return BomResult(
        entries=entries,
        totals_by_gauge=totals,
        grand_total_wire_length_m=grand_total,
    )


# ---------------------------------------------------------------------------
# Core routing function
# ---------------------------------------------------------------------------

def _route_segment(
    name: str,
    start: Vec3,
    end: Vec3,
    guides: list[Vec3],
    wire_specs: list[WireSpec],
) -> Segment:
    """
    Route a single segment from start to end through guide points.

    Builds control points: [start] + guides + [end], smooths with
    Catmull-Rom, computes length and bend-radius check.
    """
    control_pts = [start] + guides + [end]
    smoothed = _smooth_polyline(control_pts)
    length = _polyline_length(smoothed)
    min_r = _min_bend_radius(smoothed)

    od_m = bundle_diameter(wire_specs) if wire_specs else 0.001
    min_allowable_r = od_m * MIN_BEND_OD_RATIO
    bend_ok = (min_r >= min_allowable_r)

    return Segment(
        name=name,
        control_points=control_pts,
        smoothed_points=smoothed,
        length_m=length,
        wire_specs=wire_specs,
        bundle_od_m=od_m,
        min_bend_radius_m=min_r,
        bend_ok=bend_ok,
    )


def route_harness(
    endpoints: list[object],
    guides: list[object] | None = None,
    wire_specs: list[WireSpec] | None = None,
    obstacles: list[dict] | None = None,
    branches: list[dict] | None = None,
) -> HarnessPath:
    """
    Route a wiring harness in 3D.

    Parameters
    ----------
    endpoints : list of point-like
        Exactly 2 points [start, end] for a simple (no T-split) harness, or
        used as the trunk start for a branched harness.
        Each point is [x, y, z] list, (x,y,z) tuple, or {x,y,z} dict.
    guides : list of point-like, optional
        Via-points the harness must pass near.
    wire_specs : list of WireSpec, optional
        Wire gauge+count for the trunk.
    obstacles : list of bbox dicts, optional
        Each bbox: {min_x, min_y, min_z, max_x, max_y, max_z} (metres).
        Path points inside any bbox → obstacles_hit=True in result.
    branches : list of branch dicts, optional
        Each branch: {
            "branch_id": str,
            "start": point,      # split point (or omit to use trunk end)
            "end": point,        # connector endpoint
            "guides": [...],     # optional via-points for this branch
            "wire_specs": [...]  # optional: list of {gauge, count}
        }
        If provided, the main trunk runs from endpoints[0]→endpoints[1]
        through guides, then each branch extends from its split point.

    Returns
    -------
    HarnessPath
        ok=False (with reason) if bend-radius check fails anywhere or
        obstacles are hit.  Never raises.
    """
    # --- Validate endpoints ---
    try:
        pts = [_vec3_from(p) for p in (endpoints or [])]
    except (TypeError, ValueError) as exc:
        return HarnessPath(
            ok=False, reason=f"invalid endpoint: {exc}",
            branches=[], total_length_m=0.0, bundle_od_m=0.0, obstacles_hit=False,
        )

    if len(pts) < 2:
        return HarnessPath(
            ok=False, reason=f"endpoints must have at least 2 points; got {len(pts)}",
            branches=[], total_length_m=0.0, bundle_od_m=0.0, obstacles_hit=False,
        )

    # --- Normalize guides ---
    try:
        guide_pts = [_vec3_from(g) for g in (guides or [])]
    except (TypeError, ValueError) as exc:
        return HarnessPath(
            ok=False, reason=f"invalid guide point: {exc}",
            branches=[], total_length_m=0.0, bundle_od_m=0.0, obstacles_hit=False,
        )

    # --- Normalize wire specs ---
    specs = wire_specs or []

    # --- Parse obstacles ---
    obs_list = _parse_obstacles(obstacles or [])

    # --- Build branches ---
    all_branches: list[Branch] = []

    # Trunk segment: endpoints[0] → endpoints[1] through guides
    trunk_seg = _route_segment(
        name="trunk",
        start=pts[0],
        end=pts[1],
        guides=guide_pts,
        wire_specs=specs,
    )
    trunk_branch = Branch(branch_id="trunk", segments=[trunk_seg])
    all_branches.append(trunk_branch)

    # Additional T-split branches
    for bdef in (branches or []):
        b_id = str(bdef.get("branch_id", f"branch_{len(all_branches)}"))

        # Parse branch start (default: trunk end = pts[1])
        b_start_raw = bdef.get("start", pts[1])
        try:
            b_start = _vec3_from(b_start_raw)
        except (TypeError, ValueError) as exc:
            return HarnessPath(
                ok=False, reason=f"branch {b_id} invalid start: {exc}",
                branches=all_branches, total_length_m=0.0, bundle_od_m=0.0, obstacles_hit=False,
            )

        b_end_raw = bdef.get("end")
        if b_end_raw is None:
            return HarnessPath(
                ok=False, reason=f"branch {b_id} missing 'end' point",
                branches=all_branches, total_length_m=0.0, bundle_od_m=0.0, obstacles_hit=False,
            )
        try:
            b_end = _vec3_from(b_end_raw)
        except (TypeError, ValueError) as exc:
            return HarnessPath(
                ok=False, reason=f"branch {b_id} invalid end: {exc}",
                branches=all_branches, total_length_m=0.0, bundle_od_m=0.0, obstacles_hit=False,
            )

        try:
            b_guides = [_vec3_from(g) for g in bdef.get("guides", [])]
        except (TypeError, ValueError) as exc:
            return HarnessPath(
                ok=False, reason=f"branch {b_id} invalid guide: {exc}",
                branches=all_branches, total_length_m=0.0, bundle_od_m=0.0, obstacles_hit=False,
            )

        # Parse branch wire_specs
        b_specs_raw = bdef.get("wire_specs", [])
        b_specs: list[WireSpec] = []
        for ws_raw in b_specs_raw:
            try:
                b_specs.append(WireSpec(
                    gauge=str(ws_raw["gauge"]),
                    count=int(ws_raw["count"]),
                ))
            except (KeyError, TypeError, ValueError):
                pass  # skip malformed entries

        if not b_specs:
            b_specs = specs  # inherit trunk wire specs

        b_seg = _route_segment(
            name=b_id,
            start=b_start,
            end=b_end,
            guides=b_guides,
            wire_specs=b_specs,
        )
        all_branches.append(Branch(branch_id=b_id, segments=[b_seg]))

    # --- Collect metrics ---
    total_length = sum(b.total_length_m for b in all_branches)
    max_od = max(
        (s.bundle_od_m for b in all_branches for s in b.segments),
        default=0.001,
    )

    # --- Obstacle check ---
    obstacles_hit = False
    for b in all_branches:
        for seg in b.segments:
            if _path_intersects_obstacles(seg.smoothed_points, obs_list):
                obstacles_hit = True
                break
        if obstacles_hit:
            break

    # --- Bend-radius check ---
    bend_fails: list[str] = []
    for b in all_branches:
        for seg in b.segments:
            if not seg.bend_ok:
                bend_fails.append(
                    f"segment '{seg.name}' (branch '{b.branch_id}'): "
                    f"min bend radius {seg.min_bend_radius_m*1000:.1f} mm < "
                    f"required {seg.bundle_od_m * MIN_BEND_OD_RATIO * 1000:.1f} mm"
                )

    reasons: list[str] = []
    if bend_fails:
        reasons.append("bend-radius violation: " + "; ".join(bend_fails))
    if obstacles_hit:
        reasons.append("path intersects obstacle")

    ok = not reasons
    reason_str = " | ".join(reasons) if reasons else "ok"

    return HarnessPath(
        ok=ok,
        reason=reason_str,
        branches=all_branches,
        total_length_m=total_length,
        bundle_od_m=max_od,
        obstacles_hit=obstacles_hit,
    )
