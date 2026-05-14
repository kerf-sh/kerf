"""
5-axis G-code emitter for constant-tilt finishing CL points (T5).

Takes a list of CLPoint dicts  {x, y, z, i, j, k}  (tool-tip position + tool-axis
unit vector) produced by T3 (constant_tilt.py) or T4 (indexed_3_2.py) and emits
real G-code with A/B rotary axis moves.

Angle conventions (head-table kinematic, A-around-X / B-around-Y)
------------------------------------------------------------------
Given a tool-axis unit vector (i, j, k):

    B = atan2(sqrt(i² + j²), k)   — polar angle off +Z  (tilt / inclination)
                                     = 0° when tool is vertical (+Z)
    A = atan2(j, i)               — azimuth around +Z  (rotation in XY-plane)
                                     = 0° when tool tilts in the +X direction

This is the LinuxCNC / head-table convention:
  A rotates around the X axis (front-back tilt)
  B rotates around the Y axis (left-right tilt)
For a tool tilted purely in the +X direction (i>0, j=0): A=0, B=tilt_angle.
For a tool tilted purely in the +Y direction (i=0, j>0): A=90, B=tilt_angle.

Continuous-angle unwrap
-----------------------
A is unwrapped so consecutive A values don't jump by ±360°.  A singularity
near B≈0 (tool nearly vertical) means A is poorly-defined; in that region
the previous A is held (see _safe_a).

TCP (Tool Center Point) mode
-----------------------------
When opts.use_tcp is False (default): the X/Y/Z coordinates are the
tool-tip position directly — the machine must support TCP / RTCP
(G43.4 or equivalent) to translate them into machine joint moves.
When opts.use_tcp is True: a comment is added warning that TCP transformation
is the machine's responsibility; no pivot-offset math is applied here because
we don't know the machine's pivot-to-spindle distance.

Both posts accept the same PostOpts dataclass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# CLPoint type alias  (dict with x, y, z, i, j, k keys)
# ---------------------------------------------------------------------------

CLPoint = dict  # {"x": float, "y": float, "z": float, "i": float, "j": float, "k": float}


# ---------------------------------------------------------------------------
# PostOpts
# ---------------------------------------------------------------------------

@dataclass
class PostOpts:
    """Configuration for 5-axis G-code post-processors.

    machine_kinematic:
        "head_table"   — A rotates around X, B rotates around Y (most common
                         hobbyist + small VMC layout).  DEFAULT.
        "table_table"  — both rotaries are on the table (trunnion); tool stays
                         vertical.  NOT YET SUPPORTED — raises NotImplementedError.
        "head_head"    — both rotaries on the spindle head (A+C variant in plan).
                         NOT YET SUPPORTED — raises NotImplementedError.

    use_tcp:
        False (default) — emit tool-tip X/Y/Z coords; machine handles TCP via
                          G43.4 or operator-configured RTCP.  A comment is
                          inserted in the header.
        True            — same as False for now; emits G43.4 in LinuxCNC post.
                          Full pivot-offset math requires knowing the machine's
                          A-pivot / B-pivot Z-offset, which is machine-specific
                          and not in scope for v1.
    """

    tool_number: int = 1
    feed_rapid_mm_min: float = 5000.0
    feed_cut_mm_min: float = 1000.0
    spindle_rpm: int = 12000
    use_tcp: bool = False
    machine_kinematic: str = "head_table"   # "head_table" | "table_table" | "head_head"
    no_n_numbers: bool = False
    coolant: str = "flood"                  # "flood" | "mist" | "off"


# ---------------------------------------------------------------------------
# Angle math
# ---------------------------------------------------------------------------

_SINGULARITY_COS = math.cos(math.radians(1.0))  # cos(1°) — near-vertical threshold


def _axis_to_ab(i: float, j: float, k: float) -> tuple[float, float]:
    """Convert a unit tool-axis vector to (A_deg, B_deg).

    B = polar angle off +Z (tilt).
    A = azimuth around +Z (rotation in the XY-plane of the tilt direction).

    Returns degrees.
    """
    # Clamp k to valid acos domain.
    k_clamped = max(-1.0, min(1.0, k))
    b_rad = math.acos(k_clamped)          # always in [0, π]
    a_rad = math.atan2(j, i)              # in (-π, +π]
    return math.degrees(a_rad), math.degrees(b_rad)


def _unwrap_angle(prev: float, curr: float) -> float:
    """Unwrap *curr* relative to *prev* so the jump is at most ±180°."""
    delta = curr - prev
    # Fold delta into (-180, +180]
    delta = (delta + 180.0) % 360.0 - 180.0
    return prev + delta


def _safe_a(i: float, j: float, k: float, prev_a: float) -> float:
    """Return A angle, holding prev_a when near the B=0 singularity."""
    if abs(k) >= _SINGULARITY_COS:
        # Tool nearly vertical — A is ill-defined; hold previous value.
        return prev_a
    a, _ = _axis_to_ab(i, j, k)
    return a


# ---------------------------------------------------------------------------
# Core formatting helpers
# ---------------------------------------------------------------------------

def _fmt(v: float, decimals: int = 3) -> str:
    return f"{v:.{decimals}f}"


def _feed_for_point(pt: CLPoint, default_feed: float) -> float:
    """Return per-point feed if present, else default."""
    return float(pt.get("feed", pt.get("feed_rate", default_feed)))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def emit_gcode_constant_tilt(
    cl_points: list[CLPoint],
    post: str,
    opts: Optional[PostOpts] = None,
) -> str:
    """Turn constant-tilt CL points into G-code with A/B-axis rotations.

    Parameters
    ----------
    cl_points : list of dicts with keys x, y, z, i, j, k.
                i/j/k is the tool-axis unit vector at each point.
                Optional key "feed" or "feed_rate" overrides opts.feed_cut_mm_min.
    post      : "linuxcnc" | "fanuc"
    opts      : PostOpts (defaults applied if None)

    Returns
    -------
    str — complete G-code program.
    """
    if opts is None:
        opts = PostOpts()

    if opts.machine_kinematic not in ("head_table",):
        raise NotImplementedError(
            f"machine_kinematic={opts.machine_kinematic!r} is not yet supported. "
            "Only 'head_table' (A-around-X, B-around-Y) is implemented in v0.2."
        )

    post = post.lower().strip()
    if post == "linuxcnc":
        from kerf_cam.five_axis.posts.linuxcnc_5x import emit as _emit
    elif post == "fanuc":
        from kerf_cam.five_axis.posts.fanuc_5x import emit as _emit
    else:
        raise ValueError(f"Unknown post-processor {post!r}. Choose 'linuxcnc' or 'fanuc'.")

    # Compute A/B per point with continuous unwrap.
    ab_pairs: list[tuple[float, float]] = []
    prev_a = 0.0
    singularity_warned = False

    for pt in cl_points:
        i, j, k = float(pt.get("i", 0.0)), float(pt.get("j", 0.0)), float(pt.get("k", 1.0))

        near_singularity = abs(k) >= _SINGULARITY_COS
        a_raw, b_deg = _axis_to_ab(i, j, k)

        if near_singularity:
            a_deg = prev_a          # hold A
            if not singularity_warned:
                singularity_warned = True
        else:
            a_deg = _unwrap_angle(prev_a, a_raw)

        ab_pairs.append((a_deg, b_deg))
        prev_a = a_deg

    warnings: list[str] = []
    if singularity_warned:
        warnings.append(
            "; WARNING: near-singularity detected (B≈0, tool nearly vertical). "
            "A angle held at previous value at affected points."
        )

    warnings.append(
        "; WARNING: no collision/gouge check performed — verify toolpath with "
        "CAMotics before sending to machine (5-axis R7)."
    )

    return _emit(cl_points, ab_pairs, opts, warnings)
