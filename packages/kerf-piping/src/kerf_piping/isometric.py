"""
Piping isometric routing — orthogonal route helper.

Routes a pipe between two 3D nozzle positions using only axis-aligned segments
(X, Y, Z), inserting 90° elbows at direction changes and tees at branches.

Key functions
-------------
route_orthogonal(start, end, *, prefer_axis='Z')
    Compute a list of orthogonal pipe segments between start and end.
    Returns a list of Segment namedtuples.

count_fittings(segments)
    Count elbows and tees in a routed segment list.

pipe_length(segments)
    Total run length (mm) of straight pipe segments.

Pipe schedule elbow library
---------------------------
ELBOW_RADIUS_MM  Mapping from (nominal_mm, schedule) → elbow centre-line radius.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from kerf_piping.pid import Point3, PipeSchedule


# ---------------------------------------------------------------------------
# Fitting types
# ---------------------------------------------------------------------------

class FittingType(str, Enum):
    PIPE = "pipe"       # straight run
    ELBOW_90 = "elbow_90"
    ELBOW_45 = "elbow_45"
    TEE = "tee"


# ---------------------------------------------------------------------------
# Segment
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    """
    One segment of an isometric pipe route.

    Attributes
    ----------
    start       Start point (mm or m — caller's units, consistent with nozzle positions).
    end         End point.
    fitting     PIPE (straight run) or ELBOW_90 at start vertex.
    diameter_mm Nominal pipe diameter.
    schedule    Pipe schedule.
    direction   Unit vector (dx, dy, dz) — one of ±X, ±Y, ±Z.
    """

    start: Point3
    end: Point3
    fitting: FittingType = FittingType.PIPE
    diameter_mm: float = 50.0
    schedule: PipeSchedule = PipeSchedule.SCH_40

    @property
    def length(self) -> float:
        return self.start.distance_to(self.end)

    @property
    def direction(self) -> tuple[float, float, float]:
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        dz = self.end.z - self.start.z
        mag = math.sqrt(dx * dx + dy * dy + dz * dz)
        if mag < 1e-9:
            return (0.0, 0.0, 0.0)
        return (dx / mag, dy / mag, dz / mag)

    def is_zero_length(self) -> bool:
        return self.length < 1e-6


# ---------------------------------------------------------------------------
# Elbow centrelineradius look-up table (long-radius elbows, 1.5D)
# ---------------------------------------------------------------------------
# Values in mm. Keys: (nominal_dn_mm, schedule)
# Source: ASME B16.9 long-radius (1.5D) elbow dimensions

ELBOW_RADIUS_MM: dict[tuple[int, str], float] = {
    (15,  "40"):  22.5,
    (20,  "40"):  30.0,
    (25,  "40"):  37.5,
    (32,  "40"):  48.0,
    (40,  "40"):  57.0,
    (50,  "40"):  76.0,
    (65,  "40"):  95.0,
    (80,  "40"): 114.0,
    (100, "40"): 152.0,
    (150, "40"): 228.0,
    (200, "40"): 305.0,
    (250, "40"): 381.0,
    (300, "40"): 457.0,
    (15,  "80"):  22.5,
    (20,  "80"):  30.0,
    (25,  "80"):  37.5,
    (50,  "80"):  76.0,
    (80,  "80"): 114.0,
    (100, "80"): 152.0,
    (150, "80"): 228.0,
}


def elbow_radius_mm(diameter_mm: float, schedule: PipeSchedule) -> float:
    """
    Return the long-radius (1.5D) elbow centre-line radius for the given
    pipe size.  Falls back to 1.5 × nominal_radius if not in the table.
    """
    key = (int(round(diameter_mm)), schedule.value)
    if key in ELBOW_RADIUS_MM:
        return ELBOW_RADIUS_MM[key]
    return 1.5 * diameter_mm / 2.0


# ---------------------------------------------------------------------------
# Orthogonal routing
# ---------------------------------------------------------------------------

def _snap_orthogonal(
    start: Point3,
    end: Point3,
    prefer_axis: str = "Z",
) -> list[tuple[Point3, Point3]]:
    """
    Return 1–3 orthogonal run-pairs that connect start to end.

    Strategy
    --------
    1.  If start == end → empty list.
    2.  If already axis-aligned → one segment.
    3.  Decompose the offset into up to three orthogonal steps:
            first  → preferred axis (Z = vertical, X or Y = horizontal)
            second → one horizontal axis
            third  → the remaining horizontal axis
        This models the typical "rise first, then run" piping convention.
    """
    dx = end.x - start.x
    dy = end.y - start.y
    dz = end.z - start.z

    runs: list[tuple[Point3, Point3]] = []
    current = start

    def step(axis: str) -> None:
        nonlocal current
        if axis == "Z":
            delta = dz
            nxt = Point3(current.x, current.y, current.z + delta)
        elif axis == "X":
            delta = dx
            nxt = Point3(current.x + delta, current.y, current.z)
        else:  # Y
            delta = dy
            nxt = Point3(current.x, current.y + delta, current.z)
        if abs(delta) > 1e-9:
            runs.append((current, nxt))
            nonlocal_update(nxt)

    # local helper to update current
    _current_box = [current]

    def nonlocal_update(pt: Point3) -> None:
        nonlocal current
        current = pt

    ax_order = _axis_order(prefer_axis)
    for ax in ax_order:
        step(ax)

    return runs


def _axis_order(prefer: str) -> list[str]:
    all_axes = ["Z", "X", "Y"]
    prefer = prefer.upper()
    if prefer not in all_axes:
        prefer = "Z"
    rest = [a for a in all_axes if a != prefer]
    return [prefer] + rest


def route_orthogonal(
    start: Point3,
    end: Point3,
    *,
    diameter_mm: float = 50.0,
    schedule: PipeSchedule = PipeSchedule.SCH_40,
    prefer_axis: str = "Z",
) -> list[Segment]:
    """
    Route a pipe orthogonally from *start* to *end*.

    Returns a list of Segment objects (fitting=PIPE for straights,
    fitting=ELBOW_90 for change-of-direction vertices).  A zero-length
    route returns an empty list.

    Parameters
    ----------
    start, end    Start / end nozzle positions (any consistent units).
    diameter_mm   Nominal pipe diameter.
    schedule      Pipe schedule.
    prefer_axis   Which axis to travel first: 'Z' (vertical), 'X', or 'Y'.
    """
    runs = _snap_orthogonal(start, end, prefer_axis)
    if not runs:
        return []

    segments: list[Segment] = []
    for i, (seg_start, seg_end) in enumerate(runs):
        fitting = FittingType.ELBOW_90 if i > 0 else FittingType.PIPE
        seg = Segment(
            start=seg_start,
            end=seg_end,
            fitting=fitting,
            diameter_mm=diameter_mm,
            schedule=schedule,
        )
        if not seg.is_zero_length():
            segments.append(seg)

    return segments


# ---------------------------------------------------------------------------
# Fitting count + pipe length
# ---------------------------------------------------------------------------

@dataclass
class FittingCount:
    elbows_90: int = 0
    elbows_45: int = 0
    tees: int = 0
    straight_segments: int = 0

    @property
    def total_fittings(self) -> int:
        return self.elbows_90 + self.elbows_45 + self.tees


def count_fittings(segments: list[Segment]) -> FittingCount:
    """Count fittings in a routed segment list."""
    fc = FittingCount()
    for seg in segments:
        if seg.fitting == FittingType.ELBOW_90:
            fc.elbows_90 += 1
        elif seg.fitting == FittingType.ELBOW_45:
            fc.elbows_45 += 1
        elif seg.fitting == FittingType.TEE:
            fc.tees += 1
        else:
            fc.straight_segments += 1
    return fc


def pipe_length(segments: list[Segment]) -> float:
    """
    Total straight-run length of all segments (excluding zero-length fittings).

    Every segment represents a run of pipe — the fitting field records the
    fitting at the *start* of that segment, not a zero-length element — so all
    non-zero segments contribute to the pipe bill-of-materials length.
    """
    return sum(s.length for s in segments if not s.is_zero_length())


# ---------------------------------------------------------------------------
# Multi-leg route (equipment loop)
# ---------------------------------------------------------------------------

def route_loop(
    waypoints: list[Point3],
    *,
    diameter_mm: float = 50.0,
    schedule: PipeSchedule = PipeSchedule.SCH_40,
    prefer_axis: str = "Z",
) -> list[list[Segment]]:
    """
    Route a multi-leg pipe loop through a sequence of nozzle positions.

    Parameters
    ----------
    waypoints   Ordered list of nozzle positions (at least 2).

    Returns a list of per-leg segment lists.
    """
    if len(waypoints) < 2:
        raise ValueError("route_loop requires at least 2 waypoints")

    legs: list[list[Segment]] = []
    for i in range(len(waypoints) - 1):
        leg = route_orthogonal(
            waypoints[i],
            waypoints[i + 1],
            diameter_mm=diameter_mm,
            schedule=schedule,
            prefer_axis=prefer_axis,
        )
        legs.append(leg)
    return legs


# ---------------------------------------------------------------------------
# Isometric route summary (for LLM / export)
# ---------------------------------------------------------------------------

@dataclass
class IsometricSummary:
    """Human-readable summary of a routed isometric."""

    legs: int
    total_segments: int
    total_elbows_90: int
    total_elbows_45: int
    total_tees: int
    total_pipe_length: float
    diameter_mm: float
    schedule: str

    def as_dict(self) -> dict:
        return {
            "legs": self.legs,
            "total_segments": self.total_segments,
            "total_elbows_90": self.total_elbows_90,
            "total_elbows_45": self.total_elbows_45,
            "total_tees": self.total_tees,
            "total_pipe_length": round(self.total_pipe_length, 3),
            "diameter_mm": self.diameter_mm,
            "schedule": self.schedule,
        }


def summarise_route(
    legs: list[list[Segment]],
) -> IsometricSummary:
    """Summarise a multi-leg route for reporting."""
    all_segs = [s for leg in legs for s in leg]
    fc_total = FittingCount()
    total_len = 0.0
    for seg in all_segs:
        if seg.fitting == FittingType.ELBOW_90:
            fc_total.elbows_90 += 1
        elif seg.fitting == FittingType.ELBOW_45:
            fc_total.elbows_45 += 1
        elif seg.fitting == FittingType.TEE:
            fc_total.tees += 1
        if not seg.is_zero_length():
            total_len += seg.length

    diam = all_segs[0].diameter_mm if all_segs else 0.0
    sched = all_segs[0].schedule.value if all_segs else ""

    return IsometricSummary(
        legs=len(legs),
        total_segments=len(all_segs),
        total_elbows_90=fc_total.elbows_90,
        total_elbows_45=fc_total.elbows_45,
        total_tees=fc_total.tees,
        total_pipe_length=total_len,
        diameter_mm=diam,
        schedule=sched,
    )
