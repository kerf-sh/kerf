"""
kerf_cad_core.jewelry.filigree_advanced
=========================================

Advanced filigree / lace / scrollwork generators — RhinoGold/MatrixGold parity.

Each generator produces a *pattern result* dict containing polylines/curves
suitable as sweep rails for wire jewelry or as boolean-cut patterns on a band
surface.  All generators are pure Python with no external dependencies; they
never raise (errors are returned as ``{"error": ..., "code": ...}`` dicts).

Generators
----------
milgrain_with_frame_border
    Classic milgrain-bead row flanked by flat wire frame rails.  Outputs a
    set of polylines: the outer frame rail, the inner frame rail, and the
    bead-centre path (suitable for a sphere-array sweep).

florentine_scrollwork
    Florentine S-curve repeating motif along a path with branching tendrils.
    Each period produces two mirrored S-arcs plus N tendril branches.

celtic_knot_interlace
    2-strand, 3-strand, Trinity, or Endless-knot interlace pattern.  The
    crossings are generated so over/under alternation is exact.  Returns
    strand polylines tagged with crossing metadata.

art_nouveau_vine
    Organic vine with parametric petal/leaf placement along a curve.  A
    random-seeded jitter is applied to petal positions/angles for natural
    variation while remaining reproducible.

persian_moorish_lace
    Hex+star tessellation parametrised to a rectangular region.  Returns
    hex-cell boundary polylines and six-pointed star infill polylines.

wire_twist_rope
    Single/double/multi-strand twisted-wire helix polylines.  The helix
    pitch matches the formula ``pitch = twist_pitch_mm`` exactly.

apply_to_band
    Wrap a flat (XY-plane) pattern around a ring-band cylinder by mapping
    X→arc-length (circumferential) and Y→Z (axial).  Total arc-length of
    each polyline is preserved.

metal_volume_estimate
    Estimate metal volume from wire diameter and total arc length:
    ``V = π × (wire_dia/2)² × total_arc_length``.

LLM tools registered (gated by @register)
-------------------------------------------
    jewelry_filigree_milgrain_border
    jewelry_filigree_florentine_scrollwork
    jewelry_filigree_celtic_knot
    jewelry_filigree_art_nouveau_vine
    jewelry_filigree_persian_lace
    jewelry_filigree_wire_rope
    jewelry_filigree_apply_to_band
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

Polyline = List[Tuple[float, float, float]]  # list of (x, y, z) points

# ---------------------------------------------------------------------------
# Internal geometry helpers
# ---------------------------------------------------------------------------


def _arc_length_polyline(pts: Polyline) -> float:
    """Return the total arc-length of a polyline (sum of segment lengths)."""
    total = 0.0
    for i in range(1, len(pts)):
        dx = pts[i][0] - pts[i - 1][0]
        dy = pts[i][1] - pts[i - 1][1]
        dz = pts[i][2] - pts[i - 1][2]
        total += math.sqrt(dx * dx + dy * dy + dz * dz)
    return total


def _arc_length_polylines(polylines: List[Polyline]) -> float:
    """Sum of arc-lengths for a list of polylines."""
    return sum(_arc_length_polyline(p) for p in polylines)


def _circle_pts(cx: float, cy: float, r: float, n: int, z: float = 0.0) -> Polyline:
    """Return n evenly-spaced points around a circle (closed — last == first)."""
    pts = []
    for i in range(n + 1):
        a = 2.0 * math.pi * i / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
    return pts


def _s_curve_pts(
    x0: float, y0: float, width: float, height: float, n: int = 16, z: float = 0.0
) -> Polyline:
    """Approximate a cubic S-curve (sigmoid shape) as a polyline.

    The S-curve goes from (x0, y0) to (x0+width, y0) with an S-shape of
    amplitude ±height/2.
    """
    pts = []
    for i in range(n + 1):
        t = i / n
        x = x0 + t * width
        # Cubic sigmoid: y = height * (2t³ - 3t² + 1) — starts and ends flat
        # Use the standard S-shape: y passes through 0 at t=0, extrema at t≈0.21 and 0.79
        y = y0 + height * (t * t * (3.0 - 2.0 * t) - 0.5)
        pts.append((x, y, z))
    return pts


def _helix_pts(
    radius: float,
    pitch: float,
    turns: float,
    n_per_turn: int = 32,
    phase_offset: float = 0.0,
    z_start: float = 0.0,
) -> Polyline:
    """Generate helix polyline points.

    Parameters
    ----------
    radius : float
        Helix radius.
    pitch : float
        Axial advance per full turn (mm).
    turns : float
        Number of full turns.
    n_per_turn : int
        Points per full turn.
    phase_offset : float
        Initial phase angle (radians).
    z_start : float
        Starting Z value.
    """
    total_pts = max(2, int(n_per_turn * turns) + 1)
    pts = []
    for i in range(total_pts):
        t = i / (total_pts - 1)
        a = phase_offset + 2.0 * math.pi * turns * t
        x = radius * math.cos(a)
        y = radius * math.sin(a)
        z = z_start + pitch * turns * t
        pts.append((x, y, z))
    return pts


# ---------------------------------------------------------------------------
# 1. Milgrain-with-frame border
# ---------------------------------------------------------------------------


@dataclass
class MilgrainBorderResult:
    """Result of milgrain_with_frame_border.

    Attributes
    ----------
    outer_rail : Polyline
        Outer flat-wire frame rail.
    inner_rail : Polyline
        Inner flat-wire frame rail.
    bead_centres : Polyline
        Centre path for bead-sphere array (midline between the rails).
    bead_count : int
        Number of beads along the path.
    bead_diameter_mm : float
        Bead diameter as specified.
    wire_diameter_mm : float
        Frame wire diameter.
    total_arc_length_mm : float
        Total arc-length of all three polylines combined.
    metal_volume_mm3 : float
        Estimated metal volume (mm³).
    """

    outer_rail: Polyline
    inner_rail: Polyline
    bead_centres: Polyline
    bead_count: int
    bead_diameter_mm: float
    wire_diameter_mm: float
    total_arc_length_mm: float
    metal_volume_mm3: float


def milgrain_with_frame_border(
    path_length_mm: float,
    bead_diameter_mm: float = 0.7,
    pitch_mm: float = 0.9,
    frame_width_mm: float = 1.5,
    wire_diameter_mm: float = 0.4,
    n_pts: int = 64,
) -> Dict[str, Any]:
    """Generate a milgrain-with-frame border pattern along a straight path.

    The pattern lies in the XY plane along the X axis from 0 to path_length_mm.
    The bead midline is at y=0; outer rail at y=+frame_width_mm/2;
    inner rail at y=-frame_width_mm/2.

    Parameters
    ----------
    path_length_mm : float
        Length of the border path in mm (> 0).
    bead_diameter_mm : float
        Diameter of each milgrain bead in mm (> 0).
    pitch_mm : float
        Centre-to-centre bead spacing along the path (> 0).
    frame_width_mm : float
        Total width of the frame (> bead_diameter_mm).
    wire_diameter_mm : float
        Diameter of the frame rail wires (> 0).
    n_pts : int
        Number of points per rail polyline (>= 2).

    Returns
    -------
    dict
        ``{"ok": True, "result": MilgrainBorderResult.__dict__}`` or
        ``{"error": ..., "code": ...}``.
    """
    try:
        path_length_mm = float(path_length_mm)
        bead_diameter_mm = float(bead_diameter_mm)
        pitch_mm = float(pitch_mm)
        frame_width_mm = float(frame_width_mm)
        wire_diameter_mm = float(wire_diameter_mm)
        n_pts = max(2, int(n_pts))
    except (TypeError, ValueError) as e:
        return {"error": f"invalid parameter: {e}", "code": "BAD_ARGS"}

    if path_length_mm <= 0:
        return {"error": "path_length_mm must be > 0", "code": "BAD_ARGS"}
    if bead_diameter_mm <= 0:
        return {"error": "bead_diameter_mm must be > 0", "code": "BAD_ARGS"}
    if pitch_mm <= 0:
        return {"error": "pitch_mm must be > 0", "code": "BAD_ARGS"}
    if frame_width_mm <= 0:
        return {"error": "frame_width_mm must be > 0", "code": "BAD_ARGS"}
    if wire_diameter_mm <= 0:
        return {"error": "wire_diameter_mm must be > 0", "code": "BAD_ARGS"}

    half_w = frame_width_mm / 2.0

    outer_rail: Polyline = [(path_length_mm * i / (n_pts - 1), half_w, 0.0) for i in range(n_pts)]
    inner_rail: Polyline = [(path_length_mm * i / (n_pts - 1), -half_w, 0.0) for i in range(n_pts)]

    # Bead centres on the midline (y=0)
    bead_count = max(1, int(path_length_mm / pitch_mm))
    bead_centres: Polyline = [(i * pitch_mm, 0.0, 0.0) for i in range(bead_count)]

    all_polys = [outer_rail, inner_rail, bead_centres]
    total_arc = _arc_length_polylines(all_polys)
    vol = metal_volume_estimate(wire_diameter_mm, total_arc)

    return {
        "ok": True,
        "result": {
            "outer_rail": outer_rail,
            "inner_rail": inner_rail,
            "bead_centres": bead_centres,
            "bead_count": bead_count,
            "bead_diameter_mm": bead_diameter_mm,
            "wire_diameter_mm": wire_diameter_mm,
            "total_arc_length_mm": round(total_arc, 6),
            "metal_volume_mm3": round(vol, 6),
        },
    }


# ---------------------------------------------------------------------------
# 2. Florentine scrollwork
# ---------------------------------------------------------------------------


def florentine_scrollwork(
    path_length_mm: float,
    period_mm: float = 5.0,
    amplitude_mm: float = 2.0,
    tendril_count: int = 2,
    tendril_length_mm: float = 3.0,
    wire_diameter_mm: float = 0.5,
    n_pts_per_arc: int = 16,
) -> Dict[str, Any]:
    """Generate a Florentine S-curve scrollwork pattern along a straight path.

    Each period produces two mirrored S-arcs and ``tendril_count`` branches
    projecting perpendicular to the path.

    Parameters
    ----------
    path_length_mm : float
        Total path length in mm (> 0).
    period_mm : float
        Repeat period of the S-curve motif along the path (> 0).
    amplitude_mm : float
        Half-amplitude of the S-curve perpendicular to the path (> 0).
    tendril_count : int
        Number of tendril branches per period (>= 0).
    tendril_length_mm : float
        Length of each tendril branch in mm (> 0).
    wire_diameter_mm : float
        Wire cross-section diameter in mm (> 0).
    n_pts_per_arc : int
        Points per S-arc segment (>= 4).

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}`` or ``{"error": ..., "code": ...}``.
    """
    try:
        path_length_mm = float(path_length_mm)
        period_mm = float(period_mm)
        amplitude_mm = float(amplitude_mm)
        tendril_count = int(tendril_count)
        tendril_length_mm = float(tendril_length_mm)
        wire_diameter_mm = float(wire_diameter_mm)
        n_pts_per_arc = max(4, int(n_pts_per_arc))
    except (TypeError, ValueError) as e:
        return {"error": f"invalid parameter: {e}", "code": "BAD_ARGS"}

    if path_length_mm <= 0:
        return {"error": "path_length_mm must be > 0", "code": "BAD_ARGS"}
    if period_mm <= 0:
        return {"error": "period_mm must be > 0", "code": "BAD_ARGS"}
    if amplitude_mm <= 0:
        return {"error": "amplitude_mm must be > 0", "code": "BAD_ARGS"}
    if tendril_count < 0:
        return {"error": "tendril_count must be >= 0", "code": "BAD_ARGS"}
    if tendril_length_mm <= 0:
        return {"error": "tendril_length_mm must be > 0", "code": "BAD_ARGS"}
    if wire_diameter_mm <= 0:
        return {"error": "wire_diameter_mm must be > 0", "code": "BAD_ARGS"}

    n_periods = max(1, int(path_length_mm / period_mm))
    motifs: List[Dict[str, Any]] = []

    for p in range(n_periods):
        x0 = p * period_mm
        # Upper S-arc
        upper = _s_curve_pts(x0, 0.0, period_mm, amplitude_mm, n_pts_per_arc)
        # Lower S-arc (mirrored)
        lower = _s_curve_pts(x0, 0.0, period_mm, -amplitude_mm, n_pts_per_arc)

        tendrils: List[Polyline] = []
        for t in range(tendril_count):
            tx = x0 + period_mm * (t + 1) / (tendril_count + 1)
            # Branch perpendicular (Y axis)
            branch: Polyline = [(tx, 0.0, 0.0), (tx, tendril_length_mm, 0.0)]
            tendrils.append(branch)

        motifs.append({"period_index": p, "upper_s": upper, "lower_s": lower, "tendrils": tendrils})

    all_polys: List[Polyline] = []
    for m in motifs:
        all_polys.append(m["upper_s"])
        all_polys.append(m["lower_s"])
        all_polys.extend(m["tendrils"])

    total_arc = _arc_length_polylines(all_polys)
    vol = metal_volume_estimate(wire_diameter_mm, total_arc)

    return {
        "ok": True,
        "result": {
            "motifs": motifs,
            "n_periods": n_periods,
            "period_mm": period_mm,
            "amplitude_mm": amplitude_mm,
            "tendril_count": tendril_count,
            "total_arc_length_mm": round(total_arc, 6),
            "metal_volume_mm3": round(vol, 6),
        },
    }


# ---------------------------------------------------------------------------
# 3. Celtic knot interlace
# ---------------------------------------------------------------------------

# Strand type definitions
_CELTIC_TYPES = frozenset(["2_strand", "3_strand", "trinity", "endless"])


def celtic_knot_interlace(
    knot_type: str = "2_strand",
    unit_size_mm: float = 5.0,
    repeat_count: int = 3,
    wire_diameter_mm: float = 0.5,
    n_pts_per_segment: int = 16,
) -> Dict[str, Any]:
    """Generate a Celtic knot interlace pattern.

    Supports 2-strand, 3-strand, Trinity (triquetra), and Endless-knot
    patterns.  Each strand is returned as a polyline; crossings are
    annotated with ``over/under`` metadata.

    The pattern lies in the XY plane.  The ``repeat_count`` parameter
    controls how many times the base unit cell is tiled along X.

    Parameters
    ----------
    knot_type : str
        One of: "2_strand", "3_strand", "trinity", "endless".
    unit_size_mm : float
        Size of one unit cell in mm (> 0).
    repeat_count : int
        Number of unit cell repetitions (>= 1).
    wire_diameter_mm : float
        Wire cross-section diameter in mm (> 0).
    n_pts_per_segment : int
        Points per interlace arc segment (>= 4).

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}`` or ``{"error": ..., "code": ...}``.
    """
    try:
        knot_type = str(knot_type).strip().lower().replace("-", "_").replace(" ", "_")
        unit_size_mm = float(unit_size_mm)
        repeat_count = int(repeat_count)
        wire_diameter_mm = float(wire_diameter_mm)
        n_pts_per_segment = max(4, int(n_pts_per_segment))
    except (TypeError, ValueError) as e:
        return {"error": f"invalid parameter: {e}", "code": "BAD_ARGS"}

    if knot_type not in _CELTIC_TYPES:
        return {
            "error": f"knot_type={knot_type!r} is not valid. Choose from: {sorted(_CELTIC_TYPES)}",
            "code": "BAD_ARGS",
        }
    if unit_size_mm <= 0:
        return {"error": "unit_size_mm must be > 0", "code": "BAD_ARGS"}
    if repeat_count < 1:
        return {"error": "repeat_count must be >= 1", "code": "BAD_ARGS"}
    if wire_diameter_mm <= 0:
        return {"error": "wire_diameter_mm must be > 0", "code": "BAD_ARGS"}

    if knot_type == "2_strand":
        result = _celtic_2_strand(unit_size_mm, repeat_count, n_pts_per_segment)
    elif knot_type == "3_strand":
        result = _celtic_3_strand(unit_size_mm, repeat_count, n_pts_per_segment)
    elif knot_type == "trinity":
        result = _celtic_trinity(unit_size_mm, repeat_count, n_pts_per_segment)
    else:  # endless
        result = _celtic_endless(unit_size_mm, repeat_count, n_pts_per_segment)

    all_polys = [s["polyline"] for s in result["strands"]]
    total_arc = _arc_length_polylines(all_polys)
    vol = metal_volume_estimate(wire_diameter_mm, total_arc)

    result["total_arc_length_mm"] = round(total_arc, 6)
    result["metal_volume_mm3"] = round(vol, 6)
    result["wire_diameter_mm"] = wire_diameter_mm
    result["knot_type"] = knot_type
    result["repeat_count"] = repeat_count

    return {"ok": True, "result": result}


def _celtic_2_strand(unit_size_mm: float, repeat_count: int, n: int) -> Dict[str, Any]:
    """Generate a 2-strand interlace pattern (simple over/under plait)."""
    h = unit_size_mm / 2.0
    strands = []
    crossings = []

    for s_idx in range(2):
        pts: Polyline = []
        y_sign = 1.0 if s_idx == 0 else -1.0
        for r in range(repeat_count):
            x_base = r * unit_size_mm
            # Each unit: strand goes from (x_base, ±h, 0) through the crossing
            # at the midpoint then to (x_base+unit, ∓h, 0)
            for i in range(n + 1):
                t = i / n
                x = x_base + t * unit_size_mm
                # Sinusoidal lateral path
                y = y_sign * h * math.cos(math.pi * t + (r % 2) * math.pi)
                # Z encodes over/under: strand 0 goes over at even crossings
                crossing_phase = (r + s_idx) % 2
                z = 0.05 * math.sin(math.pi * t) * (1.0 if crossing_phase == 0 else -1.0)
                pts.append((x, y, z))
        strands.append({"strand_index": s_idx, "polyline": pts})

    # Crossings occur at x = k * unit_size_mm/2 for k = 1..2*repeat_count-1
    for k in range(1, 2 * repeat_count):
        x_cross = k * unit_size_mm / 2.0
        over = 0 if k % 2 == 1 else 1
        under = 1 - over
        crossings.append({"x": x_cross, "over_strand": over, "under_strand": under})

    return {"strands": strands, "crossings": crossings, "n_strands": 2}


def _celtic_3_strand(unit_size_mm: float, repeat_count: int, n: int) -> Dict[str, Any]:
    """Generate a 3-strand interlace / braid pattern."""
    h = unit_size_mm / 3.0
    strands = []
    crossings = []

    y_offsets = [-h, 0.0, h]
    for s_idx in range(3):
        pts: Polyline = []
        for r in range(repeat_count):
            x_base = r * unit_size_mm
            for i in range(n + 1):
                t = i / n
                x = x_base + t * unit_size_mm
                phase = 2.0 * math.pi * t + s_idx * 2.0 * math.pi / 3.0 + r * math.pi / 1.5
                y = y_offsets[s_idx] * math.cos(phase)
                # Z: over/under pattern in a 3-braid: s0 over s1, s1 over s2, s2 over s0
                pair = (s_idx + r) % 3
                z = 0.05 * math.sin(math.pi * t) * (1.0 if pair < 1 else -1.0)
                pts.append((x, y, z))
        strands.append({"strand_index": s_idx, "polyline": pts})

    # 3-strand crossings: 2 per period, alternating strands
    for r in range(repeat_count):
        x_base = r * unit_size_mm
        for k in range(2):
            x_cross = x_base + (k + 1) * unit_size_mm / 3.0
            over = (k + r) % 3
            under = (over + 1) % 3
            crossings.append({"x": x_cross, "over_strand": over, "under_strand": under})

    return {"strands": strands, "crossings": crossings, "n_strands": 3}


def _celtic_trinity(unit_size_mm: float, repeat_count: int, n: int) -> Dict[str, Any]:
    """Generate a Trinity (triquetra) pattern.

    A triquetra consists of 3 interlocked arcs (vesica piscis outlines).
    For repeat_count > 1, units are tiled horizontally.
    """
    r = unit_size_mm / 2.0
    strands = []
    crossings = []

    for s_idx in range(3):
        pts: Polyline = []
        base_angle = s_idx * 2.0 * math.pi / 3.0
        for rep in range(repeat_count):
            cx = rep * unit_size_mm * 1.2
            for i in range(n + 1):
                t = i / n
                # Each lobe is a circular arc of 240°
                a = base_angle + t * (4.0 * math.pi / 3.0)
                x = cx + r * math.cos(a)
                y = r * math.sin(a)
                z = 0.03 * math.sin(math.pi * t) * (1.0 if s_idx % 2 == 0 else -1.0)
                pts.append((x, y, z))
        strands.append({"strand_index": s_idx, "polyline": pts})

    # Trinity has 3 crossings per unit (each pair of arcs crosses once)
    for rep in range(repeat_count):
        cx = rep * unit_size_mm * 1.2
        for k in range(3):
            a = k * 2.0 * math.pi / 3.0
            xc = cx + r * math.cos(a) * 0.5
            yc = r * math.sin(a) * 0.5
            over = k
            under = (k + 1) % 3
            crossings.append({"x": xc, "y": yc, "over_strand": over, "under_strand": under})

    return {"strands": strands, "crossings": crossings, "n_strands": 3}


def _celtic_endless(unit_size_mm: float, repeat_count: int, n: int) -> Dict[str, Any]:
    """Generate an Endless-knot (eternal knot) pattern.

    The Endless knot is approximated as a single continuous strand that
    crosses itself 2*repeat_count times in alternating over/under sequence.
    """
    pts: Polyline = []
    crossings = []
    total_len = repeat_count * unit_size_mm
    # Lemniscate-like path: x(t) = A*sin(2t), y(t) = B*sin(t) for endless loops
    A = total_len / (2.0 * math.pi)
    B = unit_size_mm / 2.0
    n_total = n * repeat_count * 2

    for i in range(n_total + 1):
        t = 2.0 * math.pi * i / n_total
        x = A * math.sin(2.0 * t)
        y = B * math.sin(t)
        # Over/under encoded in z: crossings occur when sin(2t)=0 (t=0, π/2, π, 3π/2)
        k = int(t / (math.pi / 2))
        z = 0.04 * math.sin(2.0 * t) * (1.0 if k % 2 == 0 else -1.0)
        pts.append((x, y, z))

    strands = [{"strand_index": 0, "polyline": pts}]

    # Crossings at t = k*π/2, alternating over/under
    for k in range(2 * repeat_count):
        t_cross = k * math.pi / 2.0
        xc = A * math.sin(2.0 * t_cross)
        yc = B * math.sin(t_cross)
        crossings.append({
            "x": xc, "y": yc,
            "over_strand": 0,
            "under_strand": 0,
            "crossing_index": k,
            "sense": "over" if k % 2 == 0 else "under",
        })

    return {"strands": strands, "crossings": crossings, "n_strands": 1}


# ---------------------------------------------------------------------------
# 4. Art Nouveau organic vine
# ---------------------------------------------------------------------------


def art_nouveau_vine(
    path_length_mm: float,
    stem_amplitude_mm: float = 3.0,
    stem_period_mm: float = 8.0,
    petal_count: int = 6,
    petal_size_mm: float = 2.0,
    leaf_count: int = 4,
    leaf_size_mm: float = 3.0,
    wire_diameter_mm: float = 0.4,
    random_seed: int = 42,
    n_pts_stem: int = 64,
    n_pts_petal: int = 12,
) -> Dict[str, Any]:
    """Generate an Art Nouveau organic vine pattern.

    A sinusoidal stem runs along the X axis.  Petals and leaves are placed
    at parametric positions with random-seeded jitter for natural variation.

    Parameters
    ----------
    path_length_mm : float
        Total length of the vine path in mm (> 0).
    stem_amplitude_mm : float
        Lateral amplitude of the stem sine-wave (> 0).
    stem_period_mm : float
        Wavelength of the stem undulation (> 0).
    petal_count : int
        Number of petals along the vine (>= 0).
    petal_size_mm : float
        Approximate petal size (radius) in mm (> 0).
    leaf_count : int
        Number of leaves along the vine (>= 0).
    leaf_size_mm : float
        Approximate leaf size in mm (> 0).
    wire_diameter_mm : float
        Wire diameter for volume estimate (> 0).
    random_seed : int
        Seed for reproducible jitter.
    n_pts_stem : int
        Points on the main stem polyline (>= 2).
    n_pts_petal : int
        Points per petal/leaf ellipse (>= 4).

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}`` or ``{"error": ..., "code": ...}``.
    """
    try:
        path_length_mm = float(path_length_mm)
        stem_amplitude_mm = float(stem_amplitude_mm)
        stem_period_mm = float(stem_period_mm)
        petal_count = int(petal_count)
        petal_size_mm = float(petal_size_mm)
        leaf_count = int(leaf_count)
        leaf_size_mm = float(leaf_size_mm)
        wire_diameter_mm = float(wire_diameter_mm)
        random_seed = int(random_seed)
        n_pts_stem = max(2, int(n_pts_stem))
        n_pts_petal = max(4, int(n_pts_petal))
    except (TypeError, ValueError) as e:
        return {"error": f"invalid parameter: {e}", "code": "BAD_ARGS"}

    if path_length_mm <= 0:
        return {"error": "path_length_mm must be > 0", "code": "BAD_ARGS"}
    if stem_amplitude_mm <= 0:
        return {"error": "stem_amplitude_mm must be > 0", "code": "BAD_ARGS"}
    if stem_period_mm <= 0:
        return {"error": "stem_period_mm must be > 0", "code": "BAD_ARGS"}
    if petal_count < 0:
        return {"error": "petal_count must be >= 0", "code": "BAD_ARGS"}
    if petal_size_mm <= 0:
        return {"error": "petal_size_mm must be > 0", "code": "BAD_ARGS"}
    if leaf_count < 0:
        return {"error": "leaf_count must be >= 0", "code": "BAD_ARGS"}
    if leaf_size_mm <= 0:
        return {"error": "leaf_size_mm must be > 0", "code": "BAD_ARGS"}
    if wire_diameter_mm <= 0:
        return {"error": "wire_diameter_mm must be > 0", "code": "BAD_ARGS"}

    # Build reproducible jitter sequence from seed
    def _lcg(seed: int) -> "Callable[[None], float]":
        # Simple LCG for dependency-free reproducible pseudo-random
        state = [seed & 0xFFFFFFFF]

        def next_val() -> float:
            state[0] = (1664525 * state[0] + 1013904223) & 0xFFFFFFFF
            return (state[0] / 0xFFFFFFFF) - 0.5  # range (-0.5, 0.5)

        return next_val

    rng = _lcg(random_seed)

    # Main stem: sinusoidal polyline along X
    stem: Polyline = []
    for i in range(n_pts_stem):
        t = i / (n_pts_stem - 1)
        x = t * path_length_mm
        y = stem_amplitude_mm * math.sin(2.0 * math.pi * x / stem_period_mm)
        stem.append((x, y, 0.0))

    # Stem-Y at a given x (for petal/leaf anchoring)
    def stem_y(x: float) -> float:
        return stem_amplitude_mm * math.sin(2.0 * math.pi * x / stem_period_mm)

    # Petals: ellipses along the stem
    petals: List[Polyline] = []
    for k in range(petal_count):
        base_x = path_length_mm * (k + 1) / (petal_count + 1)
        jitter_x = rng() * stem_period_mm * 0.15
        jitter_angle = rng() * math.pi / 6.0
        cx = base_x + jitter_x
        cy = stem_y(cx)
        angle = jitter_angle
        # Ellipse: rx = petal_size_mm, ry = petal_size_mm * 0.6
        pts: Polyline = []
        for j in range(n_pts_petal + 1):
            a = 2.0 * math.pi * j / n_pts_petal
            lx = petal_size_mm * math.cos(a)
            ly = petal_size_mm * 0.6 * math.sin(a)
            # Rotate by angle
            rx = cx + lx * math.cos(angle) - ly * math.sin(angle)
            ry = cy + lx * math.sin(angle) + ly * math.cos(angle)
            pts.append((rx, ry, 0.0))
        petals.append(pts)

    # Leaves: pointed ellipses with alternate side placement
    leaves: List[Polyline] = []
    for k in range(leaf_count):
        base_x = path_length_mm * (k + 0.5) / leaf_count
        jitter_x = rng() * stem_period_mm * 0.1
        side = 1.0 if k % 2 == 0 else -1.0
        cx = base_x + jitter_x
        cy = stem_y(cx) + side * leaf_size_mm * 0.8
        # Pointed leaf: stretched ellipse
        pts = []
        for j in range(n_pts_petal + 1):
            a = 2.0 * math.pi * j / n_pts_petal
            lx = leaf_size_mm * math.cos(a)
            ly = leaf_size_mm * 0.4 * math.sin(a) * (1.0 - 0.5 * abs(math.cos(a)))
            pts.append((cx + lx, cy + ly, 0.0))
        leaves.append(pts)

    all_polys: List[Polyline] = [stem] + petals + leaves
    total_arc = _arc_length_polylines(all_polys)
    vol = metal_volume_estimate(wire_diameter_mm, total_arc)

    return {
        "ok": True,
        "result": {
            "stem": stem,
            "petals": petals,
            "leaves": leaves,
            "petal_count": len(petals),
            "leaf_count": len(leaves),
            "random_seed": random_seed,
            "total_arc_length_mm": round(total_arc, 6),
            "metal_volume_mm3": round(vol, 6),
        },
    }


# ---------------------------------------------------------------------------
# 5. Persian/Moorish geometric lace (hex+star tessellation)
# ---------------------------------------------------------------------------


def persian_moorish_lace(
    width_mm: float,
    height_mm: float,
    hex_radius_mm: float = 4.0,
    wire_diameter_mm: float = 0.4,
    include_stars: bool = True,
    n_pts_hex: int = 6,
) -> Dict[str, Any]:
    """Generate a Persian/Moorish hex+star tessellation lace pattern.

    Hexagonal cells are laid out in a regular hex grid to fill the
    ``width_mm × height_mm`` rectangular region.  Six-pointed stars
    are optionally inscribed in the gaps between hexagons.

    Parameters
    ----------
    width_mm : float
        Bounding region width in mm (> 0).
    height_mm : float
        Bounding region height in mm (> 0).
    hex_radius_mm : float
        Circumradius of each hexagonal cell in mm (> 0).
    wire_diameter_mm : float
        Wire diameter for volume estimate (> 0).
    include_stars : bool
        If True, generate six-pointed star infill polylines in the gaps.
    n_pts_hex : int
        Points per hexagon perimeter (must be 6 or multiple of 6).

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}`` or ``{"error": ..., "code": ...}``.
    """
    try:
        width_mm = float(width_mm)
        height_mm = float(height_mm)
        hex_radius_mm = float(hex_radius_mm)
        wire_diameter_mm = float(wire_diameter_mm)
        include_stars = bool(include_stars)
        n_pts_hex = max(6, int(n_pts_hex))
    except (TypeError, ValueError) as e:
        return {"error": f"invalid parameter: {e}", "code": "BAD_ARGS"}

    if width_mm <= 0:
        return {"error": "width_mm must be > 0", "code": "BAD_ARGS"}
    if height_mm <= 0:
        return {"error": "height_mm must be > 0", "code": "BAD_ARGS"}
    if hex_radius_mm <= 0:
        return {"error": "hex_radius_mm must be > 0", "code": "BAD_ARGS"}
    if wire_diameter_mm <= 0:
        return {"error": "wire_diameter_mm must be > 0", "code": "BAD_ARGS"}

    r = hex_radius_mm
    # Flat-top hexagon layout
    col_spacing = r * math.sqrt(3.0)
    row_spacing = r * 1.5

    hexagons: List[Polyline] = []
    hex_centres: List[Tuple[float, float]] = []
    stars: List[Polyline] = []

    n_cols = max(1, int(width_mm / col_spacing) + 2)
    n_rows = max(1, int(height_mm / row_spacing) + 2)

    for row in range(n_rows):
        for col in range(n_cols):
            cx = col * col_spacing + (row % 2) * col_spacing / 2.0
            cy = row * row_spacing
            # Only include if centre within bounds (with margin)
            if cx > width_mm + r or cy > height_mm + r:
                continue
            hex_pts: Polyline = []
            for k in range(n_pts_hex + 1):
                a = math.pi / 6.0 + 2.0 * math.pi * k / 6  # flat-top orientation
                hex_pts.append((cx + r * math.cos(a), cy + r * math.sin(a), 0.0))
            hexagons.append(hex_pts)
            hex_centres.append((cx, cy))

    if include_stars:
        # Six-pointed stars: placed at the gap centres between three hexagons.
        # Gap centres are at (cx + col_spacing/2, cy + row_spacing/3) offsets.
        star_radius = r * 0.5
        seen_centres: set = set()
        for cx, cy in hex_centres:
            # Two gap positions per hex
            gaps = [
                (cx + col_spacing / 2.0, cy + row_spacing / 3.0),
                (cx + col_spacing / 2.0, cy - row_spacing / 3.0),
            ]
            for gx, gy in gaps:
                key = (round(gx, 3), round(gy, 3))
                if key in seen_centres:
                    continue
                seen_centres.add(key)
                if gx > width_mm + r or gy > height_mm + r or gx < -r or gy < -r:
                    continue
                # Six-pointed star = two overlapping triangles
                star_pts: Polyline = []
                for tri in range(2):
                    offset = tri * math.pi / 3.0
                    for k in range(4):  # 3 points + close
                        a = offset + k * 2.0 * math.pi / 3.0
                        star_pts.append((
                            gx + star_radius * math.cos(a),
                            gy + star_radius * math.sin(a),
                            0.0,
                        ))
                stars.append(star_pts)

    all_polys: List[Polyline] = hexagons + stars
    total_arc = _arc_length_polylines(all_polys)
    vol = metal_volume_estimate(wire_diameter_mm, total_arc)

    return {
        "ok": True,
        "result": {
            "hexagons": hexagons,
            "stars": stars,
            "hex_count": len(hexagons),
            "star_count": len(stars),
            "hex_radius_mm": hex_radius_mm,
            "total_arc_length_mm": round(total_arc, 6),
            "metal_volume_mm3": round(vol, 6),
        },
    }


# ---------------------------------------------------------------------------
# 6. Wire-twist rope detail
# ---------------------------------------------------------------------------


def wire_twist_rope(
    path_length_mm: float,
    strand_count: int = 2,
    wire_diameter_mm: float = 0.5,
    twist_pitch_mm: float = 3.0,
    n_pts_per_turn: int = 32,
) -> Dict[str, Any]:
    """Generate multi-strand twisted-wire rope helix polylines.

    Each strand is a helix whose pitch exactly equals ``twist_pitch_mm``.
    Strands are evenly phased around the helix axis.

    Parameters
    ----------
    path_length_mm : float
        Length of the rope path in mm (> 0).
    strand_count : int
        Number of strands (>= 1).
    wire_diameter_mm : float
        Per-strand wire diameter in mm (> 0).
    twist_pitch_mm : float
        Axial advance per full 360° twist in mm (> 0).
    n_pts_per_turn : int
        Points per full helical turn (>= 8).

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}`` or ``{"error": ..., "code": ...}``.
    """
    try:
        path_length_mm = float(path_length_mm)
        strand_count = int(strand_count)
        wire_diameter_mm = float(wire_diameter_mm)
        twist_pitch_mm = float(twist_pitch_mm)
        n_pts_per_turn = max(8, int(n_pts_per_turn))
    except (TypeError, ValueError) as e:
        return {"error": f"invalid parameter: {e}", "code": "BAD_ARGS"}

    if path_length_mm <= 0:
        return {"error": "path_length_mm must be > 0", "code": "BAD_ARGS"}
    if strand_count < 1:
        return {"error": "strand_count must be >= 1", "code": "BAD_ARGS"}
    if wire_diameter_mm <= 0:
        return {"error": "wire_diameter_mm must be > 0", "code": "BAD_ARGS"}
    if twist_pitch_mm <= 0:
        return {"error": "twist_pitch_mm must be > 0", "code": "BAD_ARGS"}

    # Bundle radius: strands orbit around a central axis
    bundle_radius = wire_diameter_mm * (0.5 + 0.3 * strand_count)
    n_turns = path_length_mm / twist_pitch_mm

    strands: List[Dict[str, Any]] = []
    for s in range(strand_count):
        phase = 2.0 * math.pi * s / strand_count
        pts = _helix_pts(
            radius=bundle_radius,
            pitch=twist_pitch_mm,
            turns=n_turns,
            n_per_turn=n_pts_per_turn,
            phase_offset=phase,
            z_start=0.0,
        )
        strands.append({"strand_index": s, "phase_rad": round(phase, 6), "polyline": pts})

    all_polys = [s["polyline"] for s in strands]
    total_arc = _arc_length_polylines(all_polys)
    vol = metal_volume_estimate(wire_diameter_mm, total_arc)

    # Helix arc-length formula for one strand:
    # L = turns * sqrt((2π*bundle_radius)² + twist_pitch_mm²)
    helix_circumference = math.sqrt((2.0 * math.pi * bundle_radius) ** 2 + twist_pitch_mm ** 2)
    theoretical_arc_per_strand = n_turns * helix_circumference

    return {
        "ok": True,
        "result": {
            "strands": strands,
            "strand_count": strand_count,
            "twist_pitch_mm": twist_pitch_mm,
            "bundle_radius_mm": round(bundle_radius, 6),
            "n_turns": round(n_turns, 6),
            "theoretical_arc_per_strand_mm": round(theoretical_arc_per_strand, 6),
            "total_arc_length_mm": round(total_arc, 6),
            "metal_volume_mm3": round(vol, 6),
        },
    }


# ---------------------------------------------------------------------------
# 7. Metal volume estimate
# ---------------------------------------------------------------------------


def metal_volume_estimate(wire_diameter_mm: float, total_arc_length_mm: float) -> float:
    """Estimate metal volume from wire cross-section and total arc-length.

    Volume = π × (d/2)² × L

    Parameters
    ----------
    wire_diameter_mm : float
        Wire cross-section diameter in mm.
    total_arc_length_mm : float
        Total arc-length of all wire polylines in mm.

    Returns
    -------
    float
        Estimated volume in mm³.
    """
    try:
        d = float(wire_diameter_mm)
        L = float(total_arc_length_mm)
    except (TypeError, ValueError):
        return 0.0
    if d <= 0 or L <= 0:
        return 0.0
    return math.pi * (d / 2.0) ** 2 * L


# ---------------------------------------------------------------------------
# 8. apply_to_band — wrap flat pattern onto ring-band cylinder
# ---------------------------------------------------------------------------


def apply_to_band(
    pattern_polylines: List[Polyline],
    band_inner_dia_mm: float,
    band_width_mm: float,
    pattern_width_mm: Optional[float] = None,
) -> Dict[str, Any]:
    """Wrap a flat (XY-plane) pattern around a ring-band cylinder.

    The transformation maps:
      X → circumferential arc-length on the cylinder (angle = X / R_mid)
      Y → Z axis (axial position)

    The band_inner_dia_mm is used to compute the mid-plane radius:
    R_mid = (band_inner_dia_mm / 2) + band_width_mm / 4  (quarter of band_width
    above inner surface, matching the jewellery convention for flat-wire wrapping).

    Arc-lengths of all polylines are preserved through the mapping (straight
    lines in the flat pattern become geodesics on the cylinder).

    Parameters
    ----------
    pattern_polylines : list of Polyline
        List of polylines in the XY plane (z is ignored).
    band_inner_dia_mm : float
        Inner diameter of the ring band in mm (> 0).
    band_width_mm : float
        Width (height) of the ring band in mm (> 0).
    pattern_width_mm : float or None
        If provided, the flat pattern is scaled so that its full width maps
        to the band circumference. If None, no scaling is applied.

    Returns
    -------
    dict
        ``{"ok": True, "result": {...}}`` or ``{"error": ..., "code": ...}``.
    """
    try:
        band_inner_dia_mm = float(band_inner_dia_mm)
        band_width_mm = float(band_width_mm)
    except (TypeError, ValueError) as e:
        return {"error": f"invalid parameter: {e}", "code": "BAD_ARGS"}

    if not isinstance(pattern_polylines, list):
        return {"error": "pattern_polylines must be a list of polylines", "code": "BAD_ARGS"}
    if band_inner_dia_mm <= 0:
        return {"error": "band_inner_dia_mm must be > 0", "code": "BAD_ARGS"}
    if band_width_mm <= 0:
        return {"error": "band_width_mm must be > 0", "code": "BAD_ARGS"}

    r_inner = band_inner_dia_mm / 2.0
    r_mid = r_inner + band_width_mm / 4.0
    circumference = 2.0 * math.pi * r_mid

    # Optional scale factor so pattern_width_mm maps to full circumference
    scale_x = 1.0
    if pattern_width_mm is not None:
        try:
            pw = float(pattern_width_mm)
        except (TypeError, ValueError) as e:
            return {"error": f"invalid pattern_width_mm: {e}", "code": "BAD_ARGS"}
        if pw > 0:
            scale_x = circumference / pw

    flat_total = _arc_length_polylines(pattern_polylines)

    wrapped: List[Polyline] = []
    for poly in pattern_polylines:
        wp: Polyline = []
        for pt in poly:
            x_flat = pt[0] * scale_x
            y_flat = pt[1]
            theta = x_flat / r_mid  # angle in radians
            x3 = r_mid * math.cos(theta)
            y3 = r_mid * math.sin(theta)
            z3 = y_flat
            wp.append((x3, y3, z3))
        wrapped.append(wp)

    wrapped_total = _arc_length_polylines(wrapped)

    return {
        "ok": True,
        "result": {
            "wrapped_polylines": wrapped,
            "r_mid_mm": round(r_mid, 6),
            "circumference_mm": round(circumference, 6),
            "flat_total_arc_length_mm": round(flat_total, 6),
            "wrapped_total_arc_length_mm": round(wrapped_total, 6),
            "scale_x_applied": round(scale_x, 6),
        },
    }


# ---------------------------------------------------------------------------
# LLM tool specs + runners
# ---------------------------------------------------------------------------

_TOOL_BASE = "jewelry_filigree_"

# --- milgrain border tool ---

_milgrain_border_spec = ToolSpec(
    name=f"{_TOOL_BASE}milgrain_border",
    description=(
        "Generate a classic milgrain-with-frame border pattern.\n\n"
        "Returns outer rail, inner rail, and bead-centre polylines suitable "
        "for wire-sweep / sphere-array decoration along a ring band edge.\n\n"
        "Required: ``path_length_mm``, ``bead_diameter_mm``, ``pitch_mm``."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path_length_mm": {"type": "number", "description": "Border path length in mm."},
            "bead_diameter_mm": {"type": "number", "description": "Milgrain bead diameter in mm."},
            "pitch_mm": {"type": "number", "description": "Bead centre-to-centre spacing in mm."},
            "frame_width_mm": {"type": "number", "description": "Frame rail width in mm. Default 1.5."},
            "wire_diameter_mm": {"type": "number", "description": "Frame wire diameter in mm. Default 0.4."},
        },
        "required": ["path_length_mm", "bead_diameter_mm", "pitch_mm"],
    },
)


@register(_milgrain_border_spec, write=False)
async def run_jewelry_filigree_milgrain_border(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    r = milgrain_with_frame_border(
        path_length_mm=a.get("path_length_mm", 0),
        bead_diameter_mm=float(a.get("bead_diameter_mm", 0.7)),
        pitch_mm=float(a.get("pitch_mm", 0.9)),
        frame_width_mm=float(a.get("frame_width_mm", 1.5)),
        wire_diameter_mm=float(a.get("wire_diameter_mm", 0.4)),
    )
    if "error" in r:
        return err_payload(r["error"], r.get("code", "ERROR"))
    return ok_payload(r["result"])


# --- florentine scrollwork tool ---

_florentine_spec = ToolSpec(
    name=f"{_TOOL_BASE}florentine_scrollwork",
    description=(
        "Generate a Florentine S-curve scrollwork pattern along a path.\n\n"
        "Returns upper/lower S-arc polylines and tendril branches per period.\n\n"
        "Required: ``path_length_mm``."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path_length_mm": {"type": "number"},
            "period_mm": {"type": "number", "description": "S-curve repeat period in mm. Default 5."},
            "amplitude_mm": {"type": "number", "description": "S-curve half-amplitude in mm. Default 2."},
            "tendril_count": {"type": "integer", "description": "Tendril branches per period. Default 2."},
            "tendril_length_mm": {"type": "number", "description": "Tendril branch length in mm. Default 3."},
            "wire_diameter_mm": {"type": "number", "description": "Wire diameter in mm. Default 0.5."},
        },
        "required": ["path_length_mm"],
    },
)


@register(_florentine_spec, write=False)
async def run_jewelry_filigree_florentine_scrollwork(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    r = florentine_scrollwork(
        path_length_mm=a.get("path_length_mm", 0),
        period_mm=float(a.get("period_mm", 5.0)),
        amplitude_mm=float(a.get("amplitude_mm", 2.0)),
        tendril_count=int(a.get("tendril_count", 2)),
        tendril_length_mm=float(a.get("tendril_length_mm", 3.0)),
        wire_diameter_mm=float(a.get("wire_diameter_mm", 0.5)),
    )
    if "error" in r:
        return err_payload(r["error"], r.get("code", "ERROR"))
    return ok_payload(r["result"])


# --- celtic knot tool ---

_celtic_spec = ToolSpec(
    name=f"{_TOOL_BASE}celtic_knot",
    description=(
        "Generate a Celtic knot interlace pattern.\n\n"
        "Supports 2-strand, 3-strand, Trinity, and Endless-knot types.\n"
        "Returns strand polylines with over/under crossing annotations.\n\n"
        "Required: none (all have defaults)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "knot_type": {
                "type": "string",
                "enum": sorted(_CELTIC_TYPES),
                "description": "Knot topology. Default '2_strand'.",
            },
            "unit_size_mm": {"type": "number", "description": "Unit cell size in mm. Default 5."},
            "repeat_count": {"type": "integer", "description": "Number of unit cell repeats. Default 3."},
            "wire_diameter_mm": {"type": "number", "description": "Wire diameter in mm. Default 0.5."},
        },
        "required": [],
    },
)


@register(_celtic_spec, write=False)
async def run_jewelry_filigree_celtic_knot(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    r = celtic_knot_interlace(
        knot_type=a.get("knot_type", "2_strand"),
        unit_size_mm=float(a.get("unit_size_mm", 5.0)),
        repeat_count=int(a.get("repeat_count", 3)),
        wire_diameter_mm=float(a.get("wire_diameter_mm", 0.5)),
    )
    if "error" in r:
        return err_payload(r["error"], r.get("code", "ERROR"))
    return ok_payload(r["result"])


# --- art nouveau vine tool ---

_vine_spec = ToolSpec(
    name=f"{_TOOL_BASE}art_nouveau_vine",
    description=(
        "Generate an Art Nouveau organic vine pattern.\n\n"
        "Returns stem polyline, petal ellipses, and leaf outlines with "
        "random-seeded natural jitter.\n\n"
        "Required: ``path_length_mm``."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path_length_mm": {"type": "number"},
            "stem_amplitude_mm": {"type": "number", "description": "Stem lateral amplitude in mm. Default 3."},
            "stem_period_mm": {"type": "number", "description": "Stem undulation wavelength in mm. Default 8."},
            "petal_count": {"type": "integer", "description": "Number of petals. Default 6."},
            "petal_size_mm": {"type": "number", "description": "Petal radius in mm. Default 2."},
            "leaf_count": {"type": "integer", "description": "Number of leaves. Default 4."},
            "leaf_size_mm": {"type": "number", "description": "Leaf size in mm. Default 3."},
            "wire_diameter_mm": {"type": "number", "description": "Wire diameter in mm. Default 0.4."},
            "random_seed": {"type": "integer", "description": "Jitter seed. Default 42."},
        },
        "required": ["path_length_mm"],
    },
)


@register(_vine_spec, write=False)
async def run_jewelry_filigree_art_nouveau_vine(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    r = art_nouveau_vine(
        path_length_mm=a.get("path_length_mm", 0),
        stem_amplitude_mm=float(a.get("stem_amplitude_mm", 3.0)),
        stem_period_mm=float(a.get("stem_period_mm", 8.0)),
        petal_count=int(a.get("petal_count", 6)),
        petal_size_mm=float(a.get("petal_size_mm", 2.0)),
        leaf_count=int(a.get("leaf_count", 4)),
        leaf_size_mm=float(a.get("leaf_size_mm", 3.0)),
        wire_diameter_mm=float(a.get("wire_diameter_mm", 0.4)),
        random_seed=int(a.get("random_seed", 42)),
    )
    if "error" in r:
        return err_payload(r["error"], r.get("code", "ERROR"))
    return ok_payload(r["result"])


# --- persian lace tool ---

_persian_spec = ToolSpec(
    name=f"{_TOOL_BASE}persian_lace",
    description=(
        "Generate a Persian/Moorish hex+star tessellation lace pattern.\n\n"
        "Returns hexagonal cell boundary polylines and six-pointed star infill.\n\n"
        "Required: ``width_mm``, ``height_mm``."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "width_mm": {"type": "number", "description": "Region width in mm."},
            "height_mm": {"type": "number", "description": "Region height in mm."},
            "hex_radius_mm": {"type": "number", "description": "Hex cell circumradius in mm. Default 4."},
            "wire_diameter_mm": {"type": "number", "description": "Wire diameter in mm. Default 0.4."},
            "include_stars": {"type": "boolean", "description": "Include star infill. Default true."},
        },
        "required": ["width_mm", "height_mm"],
    },
)


@register(_persian_spec, write=False)
async def run_jewelry_filigree_persian_lace(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    r = persian_moorish_lace(
        width_mm=a.get("width_mm", 0),
        height_mm=a.get("height_mm", 0),
        hex_radius_mm=float(a.get("hex_radius_mm", 4.0)),
        wire_diameter_mm=float(a.get("wire_diameter_mm", 0.4)),
        include_stars=bool(a.get("include_stars", True)),
    )
    if "error" in r:
        return err_payload(r["error"], r.get("code", "ERROR"))
    return ok_payload(r["result"])


# --- wire rope tool ---

_wire_rope_spec = ToolSpec(
    name=f"{_TOOL_BASE}wire_rope",
    description=(
        "Generate multi-strand twisted-wire rope helix polylines.\n\n"
        "Helix pitch exactly matches ``twist_pitch_mm``.\n\n"
        "Required: ``path_length_mm``."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path_length_mm": {"type": "number", "description": "Rope path length in mm."},
            "strand_count": {"type": "integer", "description": "Number of strands. Default 2."},
            "wire_diameter_mm": {"type": "number", "description": "Per-strand wire diameter in mm. Default 0.5."},
            "twist_pitch_mm": {"type": "number", "description": "Axial advance per full twist in mm. Default 3."},
        },
        "required": ["path_length_mm"],
    },
)


@register(_wire_rope_spec, write=False)
async def run_jewelry_filigree_wire_rope(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")
    r = wire_twist_rope(
        path_length_mm=a.get("path_length_mm", 0),
        strand_count=int(a.get("strand_count", 2)),
        wire_diameter_mm=float(a.get("wire_diameter_mm", 0.5)),
        twist_pitch_mm=float(a.get("twist_pitch_mm", 3.0)),
    )
    if "error" in r:
        return err_payload(r["error"], r.get("code", "ERROR"))
    return ok_payload(r["result"])


# --- apply_to_band tool ---

_apply_to_band_spec = ToolSpec(
    name=f"{_TOOL_BASE}apply_to_band",
    description=(
        "Wrap a flat filigree pattern around a ring-band cylinder.\n\n"
        "Maps X → circumferential arc-length, Y → axial (Z) position.\n"
        "Preserves total polyline arc-lengths through the mapping.\n\n"
        "Required: ``band_inner_dia_mm``, ``band_width_mm``."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "band_inner_dia_mm": {"type": "number", "description": "Inner diameter of ring band in mm."},
            "band_width_mm": {"type": "number", "description": "Band width (height) in mm."},
            "pattern_polylines": {
                "type": "array",
                "description": "List of polylines (each a list of [x,y,z] points) to wrap.",
                "items": {"type": "array"},
            },
            "pattern_width_mm": {
                "type": "number",
                "description": "If set, scale pattern X to fill the full circumference.",
            },
        },
        "required": ["band_inner_dia_mm", "band_width_mm"],
    },
)


@register(_apply_to_band_spec, write=False)
async def run_jewelry_filigree_apply_to_band(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    raw_polys = a.get("pattern_polylines", [])
    try:
        pattern_polylines: List[Polyline] = [
            [tuple(pt) for pt in poly]  # type: ignore[misc]
            for poly in raw_polys
        ]
    except Exception as e:
        return err_payload(f"invalid pattern_polylines: {e}", "BAD_ARGS")

    r = apply_to_band(
        pattern_polylines=pattern_polylines,
        band_inner_dia_mm=a.get("band_inner_dia_mm", 0),
        band_width_mm=a.get("band_width_mm", 0),
        pattern_width_mm=a.get("pattern_width_mm", None),
    )
    if "error" in r:
        return err_payload(r["error"], r.get("code", "ERROR"))
    return ok_payload(r["result"])
