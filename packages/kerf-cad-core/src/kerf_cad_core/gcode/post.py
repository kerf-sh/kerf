"""
kerf_cad_core.gcode.post — pure-Python G-code post-processing & toolpath utilities.

Implements:

  parse_gcode(text)
      Modal-state-machine parser → list of Segment dicts with absolute endpoints.
      Handles: G0/1/2/3 motion, G17-19 plane select, G20/21 unit select,
               G90/91 absolute/incremental, F/S/T/M words, comments (parentheses
               and semicolons).  Arc (G2/G3) → chord-tolerance polyline
               segmentation via arc_to_polyline().

  arc_to_polyline(cx, cy, r, a_start, a_end, cw, chord_tol)
      Segment arc into polyline points respecting chord tolerance.

  toolpath_stats(segments)
      Toolpath length, air-move (rapid) length, feed-move length, segment count.

  cycle_time(segments, rapid_rate, accel)
      Estimated cycle time with trapezoidal accel/decel feed model.

  bounding_box(segments)
      Axis-aligned bounding box of all segment endpoints.

  clamp_feedrate(segments, f_min, f_max)
      Clamp all feed rates in the segment list to [f_min, f_max].

  override_feedrate(segments, factor)
      Scale all feed rates by factor.

  reduce_arcs_to_lines(segments, chord_tol)
      Replace arc segments with polyline segments within chord tolerance.

  fit_lines_to_arcs(segments, tol)
      Merge co-circular consecutive line segments back into a single arc.

  expand_drill_cycles(segments)
      Expand G81/G82/G83 canned drill cycles to explicit G0/G1 moves.

  transform_program(segments, translate, rotate_deg, scale, mirror_axis)
      Coordinate transform (translate/rotate/scale/mirror) of a segment list.

  renumber_lines(text, start, step)
      Strip existing N-words and re-number each block.

  apply_header_footer(text, header, footer)
      Prepend header and append footer to a G-code program string.

  backplot_points(segments, max_points)
      Sample toolpath as a flat list of (x, y, z) tuples for back-plotting.

All functions return plain dicts / lists.  Unsupported codes, non-modal errors
and large-rapid moves are appended to a top-level "warnings" list; functions
NEVER raise.

Units
-----
All linear values are in the program's native units (mm or inches per G20/21).
Angles in degrees.  Time in seconds.

Author: imranparuk
"""

from __future__ import annotations

import math
import re
import warnings as _warnings_module
from copy import deepcopy
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(
    r"([A-Za-z])([+-]?\d+(?:\.\d*)?(?:[Ee][+-]?\d+)?)"
)
_COMMENT_PAREN_RE = re.compile(r"\(([^)]*)\)")
_COMMENT_SEMI_RE = re.compile(r";.*$")


def _strip_comment(line: str) -> tuple[str, str]:
    """Return (clean_line, comment_text)."""
    comment = ""
    m = _COMMENT_SEMI_RE.search(line)
    if m:
        comment += m.group(0)[1:].strip()
        line = line[: m.start()]
    parens = _COMMENT_PAREN_RE.findall(line)
    if parens:
        comment = " ".join(parens) + (" " + comment if comment else "")
        line = _COMMENT_PAREN_RE.sub("", line)
    return line.strip(), comment.strip()


def _parse_words(line: str) -> dict[str, Any]:
    """Return dict of {letter_upper: value} for all words in line.

    The ``G`` key is special: because multiple G-codes from different modal
    groups can appear on one block (e.g. ``G17 G90 G0 X10``), its value is
    always a ``list[float]`` containing every G number found on the line.
    All other letters store only the last occurrence (standard behaviour).
    """
    result: dict[str, Any] = {}
    g_vals: list[float] = []
    for m in _WORD_RE.finditer(line):
        letter = m.group(1).upper()
        value = float(m.group(2))
        if letter == "G":
            g_vals.append(value)
        else:
            result[letter] = value
    if g_vals:
        result["G"] = g_vals
    return result


def _dist2d(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def _dist3d(p1: tuple, p2: tuple) -> float:
    return math.sqrt(sum((b - a) ** 2 for a, b in zip(p1, p2)))


# ---------------------------------------------------------------------------
# Arc → polyline
# ---------------------------------------------------------------------------

def arc_to_polyline(
    cx: float,
    cy: float,
    r: float,
    a_start_rad: float,
    a_end_rad: float,
    cw: bool,
    chord_tol: float = 0.01,
) -> list[tuple[float, float]]:
    """Segment an arc into a polyline respecting chord tolerance.

    Parameters
    ----------
    cx, cy      : arc centre
    r           : radius (must be > 0)
    a_start_rad : start angle (radians)
    a_end_rad   : end angle (radians)
    cw          : True for clockwise (G2), False for CCW (G3)
    chord_tol   : maximum chord-height error

    Returns list of (x, y) points INCLUDING the start point.
    The caller should append the arc end point.
    """
    if r <= 0 or chord_tol <= 0:
        return []

    # normalise sweep direction
    TWO_PI = 2.0 * math.pi
    if cw:
        # CW: sweep goes from start decreasing to end
        sweep = a_start_rad - a_end_rad
        if sweep < 0:
            sweep += TWO_PI
        if sweep == 0:
            sweep = TWO_PI
        da_step = -1.0
    else:
        sweep = a_end_rad - a_start_rad
        if sweep <= 0:
            sweep += TWO_PI
        if sweep == 0:
            sweep = TWO_PI
        da_step = 1.0

    # max step angle from chord tolerance: chord = 2r·sin(dθ/2) ≤ tol
    # → dθ ≤ 2·arcsin(tol / (2r))
    half_angle = math.asin(min(chord_tol / (2.0 * r), 1.0))
    d_theta = 2.0 * half_angle
    if d_theta <= 0:
        d_theta = sweep  # single segment

    n_segs = max(1, math.ceil(sweep / d_theta))
    actual_step = sweep / n_segs * da_step

    points: list[tuple[float, float]] = []
    for i in range(n_segs):
        angle = a_start_rad + actual_step * i
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points


def _arc_endpoints_and_centre(
    x0: float, y0: float, z0: float,
    x1: float, y1: float, z1: float,
    words: dict[str, float],
    plane: str,
    modal: dict,
) -> tuple[float, float, float, float, float, float, float]:
    """Return (cx, cy, cz, r, a_start_rad, a_end_rad, z_level).

    Plane XY (G17): I, J offsets → centre in XY, Z=z0.
    Plane XZ (G18): I, K offsets → centre in XZ (mapped to x,z).
    Plane YZ (G19): J, K offsets → centre in YZ (mapped to y,z).
    """
    I = words.get("I", 0.0)
    J = words.get("J", 0.0)
    K = words.get("K", 0.0)

    if plane == "G17":  # XY
        cx, cy, cz = x0 + I, y0 + J, z0
        a_start = math.atan2(y0 - cy, x0 - cx)
        a_end = math.atan2(y1 - cy, x1 - cx)
    elif plane == "G18":  # XZ
        cx, cy, cz = x0 + I, y0, z0 + K
        a_start = math.atan2(z0 - cz, x0 - cx)
        a_end = math.atan2(z1 - cz, x1 - cx)
        cy = y0  # keep Y constant
    else:  # G19 YZ
        cx, cy, cz = x0, y0 + J, z0 + K
        a_start = math.atan2(z0 - cz, y0 - cy)
        a_end = math.atan2(z1 - cz, y1 - cy)
        cx = x0

    r = math.hypot(x0 - cx, y0 - cy) if plane == "G17" else (
        math.hypot(x0 - cx, z0 - cz) if plane == "G18" else
        math.hypot(y0 - cy, z0 - cz)
    )
    return cx, cy, cz, r, a_start, a_end


# ---------------------------------------------------------------------------
# Default modal state
# ---------------------------------------------------------------------------

def _default_modal() -> dict:
    return {
        "motion": "G0",      # G0/G1/G2/G3
        "plane": "G17",      # G17/G18/G19
        "units": "G21",      # G20 inch / G21 mm
        "distance": "G90",   # G90 abs / G91 inc
        "x": 0.0,
        "y": 0.0,
        "z": 0.0,
        "f": 0.0,
        "s": 0.0,
        "t": 0,
        "tool_number": 0,
    }


# ---------------------------------------------------------------------------
# parse_gcode
# ---------------------------------------------------------------------------

_LARGE_RAPID_MM = 5000.0  # warn if rapid move longer than this (mm)


def parse_gcode(
    text: str,
    chord_tol: float = 0.01,
) -> dict[str, Any]:
    """Parse a G-code program into a list of segments.

    Parameters
    ----------
    text       : raw G-code string
    chord_tol  : arc → polyline chord tolerance (program units)

    Returns
    -------
    {
        "segments": [
            {
                "type":     "rapid" | "feed" | "arc" | "arc_segment" | "dwell"
                            | "tool_change" | "comment" | "other",
                "motion":   "G0" | "G1" | "G2" | "G3" | ...,
                "start":    (x, y, z),
                "end":      (x, y, z),
                "f":        feed rate (mm/min or in/min),
                "s":        spindle speed (rpm),
                "t":        tool number,
                "plane":    "G17" | "G18" | "G19",
                "units":    "G20" | "G21",
                "distance_mode": "G90" | "G91",
                # arc-only extra fields:
                "cx": ..., "cy": ..., "cz": ..., "radius": ...,
                "a_start_rad": ..., "a_end_rad": ...,
                "polyline": [(x,y), ...],   # arc → chord-segmented 2D points
                # drill-cycle fields (unexpanded):
                "cycle": "G81"|"G82"|"G83",
                "r_plane": ..., "depth": ...,
                # comment/other:
                "comment": "...",
                "raw": "original line",
                "line_no": int,
            },
            ...
        ],
        "warnings": ["..."],
        "units": "G20" | "G21",
        "final_pos": (x, y, z),
        "line_count": int,
    }
    """
    modal = _default_modal()
    segments: list[dict] = []
    warn: list[str] = []

    lines = text.splitlines()
    for line_no, raw_line in enumerate(lines, start=1):
        line, comment_text = _strip_comment(raw_line)
        line = line.strip().upper()

        # skip blank / pure comment lines
        if not line:
            if comment_text:
                segments.append({
                    "type": "comment",
                    "motion": None,
                    "start": (modal["x"], modal["y"], modal["z"]),
                    "end": (modal["x"], modal["y"], modal["z"]),
                    "f": modal["f"],
                    "s": modal["s"],
                    "t": modal["t"],
                    "plane": modal["plane"],
                    "units": modal["units"],
                    "distance_mode": modal["distance"],
                    "comment": comment_text,
                    "raw": raw_line,
                    "line_no": line_no,
                })
            continue

        # strip line numbers (N-words handled below via _parse_words)
        words = _parse_words(line)

        # ── modal G-code updates ──────────────────────────────────────────
        # words["G"] is always a list[float] (see _parse_words); multiple G
        # codes from different modal groups on one block are all honoured.
        for g_val in sorted(words.get("G", [])):
            g_int = int(g_val)
            if g_int in (0, 1, 2, 3):
                modal["motion"] = f"G{g_int}"
            elif g_int in (17, 18, 19):
                modal["plane"] = f"G{g_int}"
            elif g_int == 20:
                modal["units"] = "G20"
            elif g_int == 21:
                modal["units"] = "G21"
            elif g_int == 90:
                modal["distance"] = "G90"
            elif g_int == 91:
                modal["distance"] = "G91"
            elif g_int in (81, 82, 83):
                modal["motion"] = f"G{g_int}"
            elif g_int in (4,):  # dwell
                pass
            elif g_int not in (
                17, 18, 19, 20, 21, 40, 41, 42, 43, 44, 49,
                54, 55, 56, 57, 58, 59,
                94, 95, 96, 97, 98, 99,
            ):
                warn.append(
                    f"line {line_no}: unsupported G{g_int} (ignored)"
                )

        # ── tool / spindle / feed updates ────────────────────────────────
        if "T" in words:
            modal["t"] = int(words["T"])
            modal["tool_number"] = int(words["T"])
        if "S" in words:
            modal["s"] = words["S"]
        if "F" in words:
            modal["f"] = words["F"]

        # ── compute target position ───────────────────────────────────────
        x0, y0, z0 = modal["x"], modal["y"], modal["z"]
        has_xyz = any(k in words for k in ("X", "Y", "Z"))

        if modal["distance"] == "G91":  # incremental
            dx = words.get("X", 0.0)
            dy = words.get("Y", 0.0)
            dz = words.get("Z", 0.0)
            x1 = x0 + dx
            y1 = y0 + dy
            z1 = z0 + dz
        else:  # absolute
            x1 = words.get("X", x0)
            y1 = words.get("Y", y0)
            z1 = words.get("Z", z0)

        motion = modal["motion"]

        # ── M-codes ───────────────────────────────────────────────────────
        if "M" in words:
            m_val = int(words["M"])
            if m_val in (6,):  # tool change
                seg = {
                    "type": "tool_change",
                    "motion": "M6",
                    "start": (x0, y0, z0),
                    "end": (x0, y0, z0),
                    "f": modal["f"],
                    "s": modal["s"],
                    "t": modal["t"],
                    "plane": modal["plane"],
                    "units": modal["units"],
                    "distance_mode": modal["distance"],
                    "comment": comment_text,
                    "raw": raw_line,
                    "line_no": line_no,
                }
                segments.append(seg)

        # ── dwell ─────────────────────────────────────────────────────────
        if "G" in words and 4.0 in words["G"]:
            p_dwell = words.get("P", 0.0)
            seg = {
                "type": "dwell",
                "motion": "G4",
                "start": (x0, y0, z0),
                "end": (x0, y0, z0),
                "dwell_ms": p_dwell,
                "f": modal["f"],
                "s": modal["s"],
                "t": modal["t"],
                "plane": modal["plane"],
                "units": modal["units"],
                "distance_mode": modal["distance"],
                "comment": comment_text,
                "raw": raw_line,
                "line_no": line_no,
            }
            segments.append(seg)
            continue

        # ── canned drill cycles ───────────────────────────────────────────
        if motion in ("G81", "G82", "G83"):
            r_plane = words.get("R", z0)
            depth = words.get("Z", z0)
            q_peck = words.get("Q", 0.0)  # G83 peck depth
            seg = {
                "type": "drill_cycle",
                "motion": motion,
                "cycle": motion,
                "start": (x0, y0, z0),
                "end": (x1, y1, z0),  # end at same Z (retract happens inside)
                "depth": depth,
                "r_plane": r_plane,
                "q_peck": q_peck,
                "f": modal["f"],
                "s": modal["s"],
                "t": modal["t"],
                "plane": modal["plane"],
                "units": modal["units"],
                "distance_mode": modal["distance"],
                "comment": comment_text,
                "raw": raw_line,
                "line_no": line_no,
            }
            segments.append(seg)
            modal["x"], modal["y"], modal["z"] = x1, y1, z0
            continue

        # ── rapid (G0) ────────────────────────────────────────────────────
        if motion == "G0" and has_xyz:
            dist = _dist3d((x0, y0, z0), (x1, y1, z1))
            if dist > _LARGE_RAPID_MM:
                warn.append(
                    f"line {line_no}: large rapid move {dist:.1f} units"
                )
            seg = {
                "type": "rapid",
                "motion": "G0",
                "start": (x0, y0, z0),
                "end": (x1, y1, z1),
                "f": modal["f"],
                "s": modal["s"],
                "t": modal["t"],
                "plane": modal["plane"],
                "units": modal["units"],
                "distance_mode": modal["distance"],
                "comment": comment_text,
                "raw": raw_line,
                "line_no": line_no,
            }
            segments.append(seg)
            modal["x"], modal["y"], modal["z"] = x1, y1, z1
            continue

        # ── feed (G1) ─────────────────────────────────────────────────────
        if motion == "G1" and has_xyz:
            seg = {
                "type": "feed",
                "motion": "G1",
                "start": (x0, y0, z0),
                "end": (x1, y1, z1),
                "f": modal["f"],
                "s": modal["s"],
                "t": modal["t"],
                "plane": modal["plane"],
                "units": modal["units"],
                "distance_mode": modal["distance"],
                "comment": comment_text,
                "raw": raw_line,
                "line_no": line_no,
            }
            segments.append(seg)
            modal["x"], modal["y"], modal["z"] = x1, y1, z1
            continue

        # ── arc (G2/G3) ───────────────────────────────────────────────────
        if motion in ("G2", "G3"):
            cw = motion == "G2"
            try:
                cx, cy, cz, radius, a_start, a_end = _arc_endpoints_and_centre(
                    x0, y0, z0, x1, y1, z1, words, modal["plane"], modal
                )
                polyline = arc_to_polyline(
                    cx, cy, radius, a_start, a_end, cw, chord_tol
                )
            except Exception as exc:
                warn.append(f"line {line_no}: arc computation error: {exc}")
                cx, cy, cz, radius, a_start, a_end = x0, y0, z0, 0.0, 0.0, 0.0
                polyline = []

            seg = {
                "type": "arc",
                "motion": motion,
                "start": (x0, y0, z0),
                "end": (x1, y1, z1),
                "f": modal["f"],
                "s": modal["s"],
                "t": modal["t"],
                "plane": modal["plane"],
                "units": modal["units"],
                "distance_mode": modal["distance"],
                "cx": cx,
                "cy": cy,
                "cz": cz,
                "radius": radius,
                "a_start_rad": a_start,
                "a_end_rad": a_end,
                "polyline": polyline,
                "comment": comment_text,
                "raw": raw_line,
                "line_no": line_no,
            }
            segments.append(seg)
            modal["x"], modal["y"], modal["z"] = x1, y1, z1
            continue

        # ── no motion word on this line (comment / modal-only) ────────────
        if comment_text and not any(k in words for k in ("X", "Y", "Z")):
            seg = {
                "type": "comment",
                "motion": None,
                "start": (x0, y0, z0),
                "end": (x0, y0, z0),
                "f": modal["f"],
                "s": modal["s"],
                "t": modal["t"],
                "plane": modal["plane"],
                "units": modal["units"],
                "distance_mode": modal["distance"],
                "comment": comment_text,
                "raw": raw_line,
                "line_no": line_no,
            }
            segments.append(seg)

    return {
        "ok": True,
        "segments": segments,
        "warnings": warn,
        "units": modal["units"],
        "final_pos": (modal["x"], modal["y"], modal["z"]),
        "line_count": len(lines),
    }


# ---------------------------------------------------------------------------
# toolpath_stats
# ---------------------------------------------------------------------------

def toolpath_stats(segments: list[dict]) -> dict[str, Any]:
    """Compute toolpath statistics from a segment list.

    Returns
    -------
    {
        "ok": True,
        "total_length": float,
        "feed_length": float,
        "rapid_length": float,
        "arc_length": float,
        "segment_count": int,
        "feed_count": int,
        "rapid_count": int,
        "arc_count": int,
        "tool_changes": int,
    }
    """
    total = 0.0
    feed_len = 0.0
    rapid_len = 0.0
    arc_len = 0.0
    feed_count = 0
    rapid_count = 0
    arc_count = 0
    tool_changes = 0

    for seg in segments:
        stype = seg.get("type")
        start = seg.get("start", (0, 0, 0))
        end = seg.get("end", (0, 0, 0))
        dist = _dist3d(start, end)

        if stype == "rapid":
            rapid_len += dist
            total += dist
            rapid_count += 1
        elif stype == "feed":
            feed_len += dist
            total += dist
            feed_count += 1
        elif stype == "arc":
            # arc length = |sweep| * radius
            r = seg.get("radius", 0.0)
            a_start = seg.get("a_start_rad", 0.0)
            a_end = seg.get("a_end_rad", 0.0)
            cw = seg.get("motion") == "G2"
            if cw:
                sweep = a_start - a_end
                if sweep <= 0:
                    sweep += 2 * math.pi
            else:
                sweep = a_end - a_start
                if sweep <= 0:
                    sweep += 2 * math.pi
            arc_chord = r * abs(sweep)
            arc_len += arc_chord
            total += arc_chord
            arc_count += 1
        elif stype == "tool_change":
            tool_changes += 1

    return {
        "ok": True,
        "total_length": total,
        "feed_length": feed_len,
        "rapid_length": rapid_len,
        "arc_length": arc_len,
        "segment_count": len(segments),
        "feed_count": feed_count,
        "rapid_count": rapid_count,
        "arc_count": arc_count,
        "tool_changes": tool_changes,
    }


# ---------------------------------------------------------------------------
# cycle_time
# ---------------------------------------------------------------------------

def cycle_time(
    segments: list[dict],
    rapid_rate: float = 10000.0,
    accel: float = 500.0,
) -> dict[str, Any]:
    """Estimate machining cycle time with trapezoidal accel/decel model.

    Parameters
    ----------
    segments    : from parse_gcode()
    rapid_rate  : rapid traverse rate (mm/min or in/min, same units as program)
    accel       : axis acceleration (mm/s² or in/s²)

    The trapezoidal model for a single move:
      v_feed = F / 60  (mm/s)
      d_accel = v² / (2a)   (ramp-up distance)
      If move is shorter than 2*d_accel: triangular profile, t = 2*sqrt(d/a)
      Otherwise: t = 2*d_accel/v + (d - 2*d_accel)/v

    Returns
    -------
    {
        "ok": True,
        "total_s": float,       # total time (seconds)
        "feed_s": float,
        "rapid_s": float,
        "arc_s": float,
    }
    """

    def _move_time(dist: float, f_per_min: float) -> float:
        if dist <= 0 or f_per_min <= 0:
            return 0.0
        v = f_per_min / 60.0  # mm/s
        if accel <= 0:
            return dist / v
        d_ramp = v * v / (2.0 * accel)
        if dist < 2.0 * d_ramp:
            # triangular: t = 2 * sqrt(d/a)
            return 2.0 * math.sqrt(dist / accel)
        t_ramp = 2.0 * d_ramp / v  # accel + decel
        t_cruise = (dist - 2.0 * d_ramp) / v
        return t_ramp + t_cruise

    total_s = 0.0
    feed_s = 0.0
    rapid_s = 0.0
    arc_s = 0.0

    for seg in segments:
        stype = seg.get("type")
        start = seg.get("start", (0, 0, 0))
        end = seg.get("end", (0, 0, 0))
        dist = _dist3d(start, end)

        if stype == "rapid":
            t = _move_time(dist, rapid_rate)
            rapid_s += t
            total_s += t
        elif stype == "feed":
            f = seg.get("f", 0.0) or 0.0
            t = _move_time(dist, f)
            feed_s += t
            total_s += t
        elif stype == "arc":
            r = seg.get("radius", 0.0)
            a_start = seg.get("a_start_rad", 0.0)
            a_end = seg.get("a_end_rad", 0.0)
            cw = seg.get("motion") == "G2"
            if cw:
                sweep = a_start - a_end
                if sweep <= 0:
                    sweep += 2 * math.pi
            else:
                sweep = a_end - a_start
                if sweep <= 0:
                    sweep += 2 * math.pi
            arc_dist = r * abs(sweep)
            f = seg.get("f", 0.0) or 0.0
            t = _move_time(arc_dist, f)
            arc_s += t
            total_s += t
        elif stype == "dwell":
            dwell_ms = seg.get("dwell_ms", 0.0) or 0.0
            t = dwell_ms / 1000.0
            total_s += t

    return {
        "ok": True,
        "total_s": total_s,
        "feed_s": feed_s,
        "rapid_s": rapid_s,
        "arc_s": arc_s,
    }


# ---------------------------------------------------------------------------
# bounding_box
# ---------------------------------------------------------------------------

def bounding_box(segments: list[dict]) -> dict[str, Any]:
    """Compute axis-aligned bounding box over all segment endpoints.

    Returns
    -------
    {
        "ok": True,
        "xmin": float, "xmax": float,
        "ymin": float, "ymax": float,
        "zmin": float, "zmax": float,
        "dx": float, "dy": float, "dz": float,
    }
    or {"ok": False, "reason": "..."} if no segments.
    """
    if not segments:
        return {"ok": False, "reason": "no segments"}

    xs, ys, zs = [], [], []
    for seg in segments:
        for pt in (seg.get("start", ()), seg.get("end", ())):
            if len(pt) == 3:
                xs.append(pt[0])
                ys.append(pt[1])
                zs.append(pt[2])

    if not xs:
        return {"ok": False, "reason": "no valid endpoints"}

    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    zmin, zmax = min(zs), max(zs)
    return {
        "ok": True,
        "xmin": xmin, "xmax": xmax,
        "ymin": ymin, "ymax": ymax,
        "zmin": zmin, "zmax": zmax,
        "dx": xmax - xmin,
        "dy": ymax - ymin,
        "dz": zmax - zmin,
    }


# ---------------------------------------------------------------------------
# Feed rate helpers
# ---------------------------------------------------------------------------

def clamp_feedrate(
    segments: list[dict],
    f_min: float,
    f_max: float,
) -> list[dict]:
    """Return a new segment list with all feed rates clamped to [f_min, f_max].

    Rapid segments are not affected (they run at machine rapid rate).
    """
    result = []
    for seg in segments:
        s = dict(seg)
        if s.get("type") in ("feed", "arc") and s.get("f") is not None:
            s["f"] = max(f_min, min(f_max, s["f"]))
        result.append(s)
    return result


def override_feedrate(segments: list[dict], factor: float) -> list[dict]:
    """Return a new segment list with all feed rates scaled by factor.

    Rapid segments are not affected.
    """
    result = []
    for seg in segments:
        s = dict(seg)
        if s.get("type") in ("feed", "arc") and s.get("f") is not None:
            s["f"] = s["f"] * factor
        result.append(s)
    return result


# ---------------------------------------------------------------------------
# Arc <-> line converters
# ---------------------------------------------------------------------------

def reduce_arcs_to_lines(
    segments: list[dict],
    chord_tol: float = 0.01,
) -> list[dict]:
    """Replace arc segments with chord-segmented polyline feed moves.

    Each arc is replaced by N G1 line segments whose chord error ≤ chord_tol.
    """
    result: list[dict] = []
    for seg in segments:
        if seg.get("type") != "arc":
            result.append(seg)
            continue

        cx = seg["cx"]
        cy = seg["cy"]
        r = seg["radius"]
        a_start = seg["a_start_rad"]
        a_end = seg["a_end_rad"]
        cw = seg["motion"] == "G2"
        plane = seg["plane"]
        z_start = seg["start"][2]
        z_end = seg["end"][2]
        pts = arc_to_polyline(cx, cy, r, a_start, a_end, cw, chord_tol)
        # add end point
        end_angle = a_end
        pts.append((cx + r * math.cos(end_angle), cy + r * math.sin(end_angle)))

        if len(pts) < 2:
            result.append(seg)
            continue

        n = len(pts) - 1
        for i in range(n):
            px0, py0 = pts[i]
            px1, py1 = pts[i + 1]
            frac_start = i / n
            frac_end = (i + 1) / n
            zs = z_start + frac_start * (z_end - z_start)
            ze = z_start + frac_end * (z_end - z_start)
            line_seg = dict(seg)
            line_seg["type"] = "feed"
            line_seg["motion"] = "G1"
            line_seg["start"] = (px0, py0, zs)
            line_seg["end"] = (px1, py1, ze)
            # remove arc-specific fields
            for k in ("cx", "cy", "cz", "radius", "a_start_rad", "a_end_rad", "polyline"):
                line_seg.pop(k, None)
            result.append(line_seg)

    return result


def fit_lines_to_arcs(
    segments: list[dict],
    tol: float = 0.01,
) -> list[dict]:
    """Merge consecutive co-circular G1 line segments back into a single arc.

    Two line segments are co-circular if their midpoints and endpoints all lie
    within tol of the same circle centre.  Merged segments become type 'arc'.
    This is a best-effort reducer; it processes runs of consecutive feed moves.
    """
    if not segments:
        return []

    def _fit_circle_3pts(
        p1: tuple, p2: tuple, p3: tuple
    ) -> tuple[float, float, float] | None:
        """Return (cx, cy, r) or None if points are collinear."""
        ax, ay = p1[0], p1[1]
        bx, by = p2[0], p2[1]
        cx_, cy_ = p3[0], p3[1]
        D = 2 * (ax * (by - cy_) + bx * (cy_ - ay) + cx_ * (ay - by))
        if abs(D) < 1e-12:
            return None
        ux = ((ax**2 + ay**2) * (by - cy_) + (bx**2 + by**2) * (cy_ - ay)
              + (cx_**2 + cy_**2) * (ay - by)) / D
        uy = ((ax**2 + ay**2) * (cx_ - bx) + (bx**2 + by**2) * (ax - cx_)
              + (cx_**2 + cy_**2) * (bx - ax)) / D
        r = math.hypot(ax - ux, ay - uy)
        return ux, uy, r

    result: list[dict] = []
    i = 0
    while i < len(segments):
        seg = segments[i]
        if seg.get("type") != "feed":
            result.append(seg)
            i += 1
            continue

        # try to grow a co-circular run
        run = [seg]
        j = i + 1
        while j < len(segments) and segments[j].get("type") == "feed":
            run.append(segments[j])
            j += 1

        if len(run) < 3:
            result.extend(run)
            i = j
            continue

        # collect all unique points in run
        pts = [run[0]["start"]]
        for s in run:
            pts.append(s["end"])

        # fit circle to first, middle, last point
        mid_idx = len(pts) // 2
        circle = _fit_circle_3pts(pts[0], pts[mid_idx], pts[-1])
        if circle is None:
            result.extend(run)
            i = j
            continue

        cx_fit, cy_fit, r_fit = circle

        # check all points lie on the circle within tol
        all_on = all(
            abs(math.hypot(p[0] - cx_fit, p[1] - cy_fit) - r_fit) <= tol
            for p in pts
        )
        if not all_on:
            result.extend(run)
            i = j
            continue

        # determine CW/CCW from cross-product of first two chords
        p0, p1_, p2_ = pts[0], pts[1], pts[2]
        cross = ((p1_[0] - p0[0]) * (p2_[1] - p0[1]) -
                 (p1_[1] - p0[1]) * (p2_[0] - p0[0]))
        cw = cross < 0

        a_start = math.atan2(pts[0][1] - cy_fit, pts[0][0] - cx_fit)
        a_end = math.atan2(pts[-1][1] - cy_fit, pts[-1][0] - cx_fit)

        z_start = pts[0][2] if len(pts[0]) > 2 else 0.0
        z_end = pts[-1][2] if len(pts[-1]) > 2 else 0.0

        arc_seg = dict(run[0])
        arc_seg["type"] = "arc"
        arc_seg["motion"] = "G2" if cw else "G3"
        arc_seg["start"] = pts[0]
        arc_seg["end"] = pts[-1]
        arc_seg["cx"] = cx_fit
        arc_seg["cy"] = cy_fit
        arc_seg["cz"] = z_start
        arc_seg["radius"] = r_fit
        arc_seg["a_start_rad"] = a_start
        arc_seg["a_end_rad"] = a_end
        arc_seg["polyline"] = [(p[0], p[1]) for p in pts]
        result.append(arc_seg)
        i = j

    return result


# ---------------------------------------------------------------------------
# expand_drill_cycles
# ---------------------------------------------------------------------------

def expand_drill_cycles(segments: list[dict]) -> list[dict]:
    """Expand G81/G82/G83 canned drill cycles to explicit G0/G1 moves.

    G81: rapid to XY, feed to depth, rapid retract to R-plane
    G82: same as G81 + dwell at depth
    G83: peck drilling — repeated peck to depth in Q increments

    Returns a new segment list with drill_cycle segments replaced.
    """
    result: list[dict] = []
    for seg in segments:
        if seg.get("type") != "drill_cycle":
            result.append(seg)
            continue

        cycle = seg["cycle"]
        x1 = seg["end"][0]
        y1 = seg["end"][1]
        z_start = seg["start"][2]
        r_plane = seg.get("r_plane", z_start)
        depth = seg.get("depth", z_start)
        q_peck = seg.get("q_peck", 0.0)
        feed = seg.get("f", 100.0)
        base = {
            "f": feed,
            "s": seg.get("s", 0.0),
            "t": seg.get("t", 0),
            "plane": seg.get("plane", "G17"),
            "units": seg.get("units", "G21"),
            "distance_mode": "G90",
            "comment": seg.get("comment", ""),
            "raw": seg.get("raw", ""),
            "line_no": seg.get("line_no", 0),
        }

        # rapid to XY
        result.append({
            **base,
            "type": "rapid",
            "motion": "G0",
            "start": seg["start"],
            "end": (x1, y1, z_start),
        })
        # rapid to R-plane
        result.append({
            **base,
            "type": "rapid",
            "motion": "G0",
            "start": (x1, y1, z_start),
            "end": (x1, y1, r_plane),
        })

        if cycle == "G81":
            result.append({
                **base,
                "type": "feed",
                "motion": "G1",
                "start": (x1, y1, r_plane),
                "end": (x1, y1, depth),
            })
            result.append({
                **base,
                "type": "rapid",
                "motion": "G0",
                "start": (x1, y1, depth),
                "end": (x1, y1, r_plane),
            })
        elif cycle == "G82":
            result.append({
                **base,
                "type": "feed",
                "motion": "G1",
                "start": (x1, y1, r_plane),
                "end": (x1, y1, depth),
            })
            # dwell
            result.append({
                **base,
                "type": "dwell",
                "motion": "G4",
                "start": (x1, y1, depth),
                "end": (x1, y1, depth),
                "dwell_ms": seg.get("dwell_ms", 0.0),
            })
            result.append({
                **base,
                "type": "rapid",
                "motion": "G0",
                "start": (x1, y1, depth),
                "end": (x1, y1, r_plane),
            })
        elif cycle == "G83":
            peck = q_peck if q_peck and q_peck > 0 else abs(depth - r_plane)
            current_z = r_plane
            target_z = depth
            step = -abs(peck) if target_z < r_plane else abs(peck)
            while True:
                next_z = current_z + step
                if (step < 0 and next_z < target_z) or (step > 0 and next_z > target_z):
                    next_z = target_z
                result.append({
                    **base,
                    "type": "feed",
                    "motion": "G1",
                    "start": (x1, y1, current_z),
                    "end": (x1, y1, next_z),
                })
                current_z = next_z
                if current_z == target_z:
                    break
                # retract to R-plane for chip clearing
                result.append({
                    **base,
                    "type": "rapid",
                    "motion": "G0",
                    "start": (x1, y1, current_z),
                    "end": (x1, y1, r_plane),
                })
                # rapid back to just above previous peck
                result.append({
                    **base,
                    "type": "rapid",
                    "motion": "G0",
                    "start": (x1, y1, r_plane),
                    "end": (x1, y1, current_z),
                })
            # final retract
            result.append({
                **base,
                "type": "rapid",
                "motion": "G0",
                "start": (x1, y1, target_z),
                "end": (x1, y1, r_plane),
            })

    return result


# ---------------------------------------------------------------------------
# transform_program
# ---------------------------------------------------------------------------

def transform_program(
    segments: list[dict],
    translate: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotate_deg: float = 0.0,
    scale: float = 1.0,
    mirror_axis: str | None = None,
) -> list[dict]:
    """Apply coordinate transform to all segment endpoints.

    Operations are applied in order: scale → mirror → rotate → translate.

    Parameters
    ----------
    translate   : (dx, dy, dz) translation
    rotate_deg  : rotation about Z-axis (degrees, CCW positive)
    scale       : uniform scale factor
    mirror_axis : None | "X" | "Y" | "Z"
    """
    dx, dy, dz = translate
    cos_r = math.cos(math.radians(rotate_deg))
    sin_r = math.sin(math.radians(rotate_deg))

    def _transform_pt(pt: tuple) -> tuple:
        x, y, z = pt[0], pt[1], pt[2] if len(pt) > 2 else 0.0
        # scale
        x *= scale
        y *= scale
        z *= scale
        # mirror
        if mirror_axis == "X":
            x = -x
        elif mirror_axis == "Y":
            y = -y
        elif mirror_axis == "Z":
            z = -z
        # rotate about Z
        xr = x * cos_r - y * sin_r
        yr = x * sin_r + y * cos_r
        x, y = xr, yr
        # translate
        x += dx
        y += dy
        z += dz
        return (x, y, z)

    result: list[dict] = []
    for seg in segments:
        s = dict(seg)
        if "start" in s and len(s["start"]) >= 3:
            s["start"] = _transform_pt(s["start"])
        if "end" in s and len(s["end"]) >= 3:
            s["end"] = _transform_pt(s["end"])
        if "cx" in s:
            cx_t, cy_t, _ = _transform_pt((s["cx"], s["cy"], s.get("cz", 0.0)))
            s["cx"] = cx_t
            s["cy"] = cy_t
        result.append(s)
    return result


# ---------------------------------------------------------------------------
# renumber_lines
# ---------------------------------------------------------------------------

_NWORD_RE = re.compile(r"^N\d+\s*", re.IGNORECASE)


def renumber_lines(
    text: str,
    start: int = 10,
    step: int = 10,
) -> str:
    """Strip existing N-words and re-number each non-blank block.

    Parameters
    ----------
    text  : G-code program string
    start : first line number
    step  : increment between line numbers

    Returns new program string with N-numbers prepended.
    """
    lines = text.splitlines()
    result = []
    n = start
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append("")
            continue
        # strip existing N-word
        stripped = _NWORD_RE.sub("", stripped).strip()
        if stripped:
            result.append(f"N{n} {stripped}")
            n += step
        else:
            result.append("")
    return "\n".join(result)


# ---------------------------------------------------------------------------
# apply_header_footer
# ---------------------------------------------------------------------------

def apply_header_footer(
    text: str,
    header: str = "",
    footer: str = "",
) -> str:
    """Prepend header and append footer to a G-code program string.

    Blank header/footer strings are ignored.
    """
    parts = []
    if header:
        parts.append(header)
    parts.append(text)
    if footer:
        parts.append(footer)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# backplot_points
# ---------------------------------------------------------------------------

def backplot_points(
    segments: list[dict],
    max_points: int = 500,
) -> list[tuple[float, float, float]]:
    """Sample toolpath as a flat list of (x, y, z) tuples for back-plotting.

    For arc segments the polyline is used if available.
    Rapid moves are included (they are part of the path).

    Parameters
    ----------
    segments   : from parse_gcode()
    max_points : maximum number of points to return (downsampled if needed)

    Returns list of (x, y, z) tuples.
    """
    pts: list[tuple[float, float, float]] = []

    for seg in segments:
        stype = seg.get("type")
        if stype in ("comment", "tool_change", "dwell", "other"):
            continue

        start = seg.get("start", (0, 0, 0))
        end = seg.get("end", (0, 0, 0))

        if not pts:
            pts.append(start)

        if stype == "arc" and seg.get("polyline"):
            z_start = start[2]
            z_end = end[2]
            poly = seg["polyline"]
            n = len(poly)
            for idx, (px, py) in enumerate(poly):
                pz = z_start + (z_end - z_start) * idx / max(n - 1, 1)
                pts.append((px, py, pz))
        else:
            pts.append(end)

    # downsample if needed
    if max_points > 0 and len(pts) > max_points:
        step = len(pts) / max_points
        pts = [pts[int(i * step)] for i in range(max_points)]

    return pts
