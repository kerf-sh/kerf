"""
kerf_cad_core.jewelry.stringing
================================

Pearl / bead stringing design — distinct from metal-link chain (chain.py).

Covers:
  - Bead count for a target length:
      n = floor((L - clasp_length) / (bead_d + knot_gap))
  - Knotted (pearl), unknotted, and floating-illusion layouts
  - Thread / cord selection: silk size (A–FFF) and Beadalon-style wire
    gauge keyed to bead-hole diameter, weight class, and drape quality
  - Graduated / taper schedules (centre bead → shoulders, monotone, symmetric)
  - Multi-strand torsade specification
  - Standard necklace length presets
      collar   ≈ 30–33 cm
      choker   ≈ 35–40 cm
      princess ≈ 43–48 cm  (target 45 cm)
      matinee  ≈ 50–60 cm
      opera    ≈ 70–85 cm
      rope     ≈ 100–120 cm
  - Clasp recommendation by strand count and weight
  - Crimp-tube / French-wire finishing specs
  - Cord length including knot take-up and finishing tails

All computation functions are pure Python and never raise on graceful
fallback; invalid inputs return an ``error`` key in the result dict.

LLM tools registered (gated)
------------------------------
    jewelry_stringing_layout   — bead count, layout, cord length, clasp/thread pick
    jewelry_stringing_graduated — graduated taper schedule
    jewelry_stringing_torsade   — multi-strand torsade spec
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Standard necklace length presets (name → nominal_mm)
NECKLACE_PRESETS: dict[str, float] = {
    "collar":   320.0,   # 32 cm
    "choker":   380.0,   # 38 cm
    "princess": 450.0,   # 45 cm
    "matinee":  560.0,   # 56 cm
    "opera":    760.0,   # 76 cm
    "rope":    1070.0,   # 107 cm
}

# Silk thread size → approximate diameter in mm
# Sizes A through FFF; higher = thicker
_SILK_SIZES: dict[str, float] = {
    "A":   0.33,
    "B":   0.38,
    "C":   0.43,
    "D":   0.48,
    "E":   0.56,
    "F":   0.71,
    "FF":  0.89,
    "FFF": 1.02,
}

# Beadalon-style wire gauge → (diameter_mm, drape_quality)
# drape_quality: "stiff" | "medium" | "flexible" | "ultra_flexible"
_WIRE_GAUGES: dict[str, tuple[float, str]] = {
    "0.010in": (0.254, "ultra_flexible"),
    "0.012in": (0.305, "ultra_flexible"),
    "0.014in": (0.356, "flexible"),
    "0.015in": (0.381, "flexible"),
    "0.018in": (0.457, "medium"),
    "0.019in": (0.483, "medium"),
    "0.021in": (0.533, "stiff"),
    "0.024in": (0.610, "stiff"),
}

# Clasp specs: (min_strands, max_weight_g, style_name)
# Sorted preference: lightest/fewest-strand first
_CLASP_RULES: list[tuple[int, float, str]] = [
    (1,  20.0, "lobster"),
    (1,  60.0, "box"),
    (1, 150.0, "toggle"),
    (2,  60.0, "box"),
    (2, 150.0, "toggle"),
    (3,  60.0, "box"),
    (3, 999.0, "toggle"),
    (4, 999.0, "toggle"),
    (1, 999.0, "magnetic"),
]

# Knot diameter as multiple of thread diameter (typical pearl knot)
_KNOT_DIAMETER_MULT = 2.2

# French-wire (gimp) default length per end in mm
_FRENCH_WIRE_LENGTH_PER_END_MM = 10.0

# Finishing tails (thread beyond last bead on each end before clasp)
_TAIL_LENGTH_MM = 75.0  # 75 mm per end (folded through clasp loop)

# Crimp tube default length
_CRIMP_TUBE_LENGTH_MM = 2.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _silk_for_hole(hole_diameter_mm: float, drape: str = "medium") -> str:
    """Pick the largest silk size that fits through the bead hole with clearance.

    Clearance factor: thread diameter ≤ hole_diameter * 0.75 so the thread
    passes twice through (for looping at clasps).

    Parameters
    ----------
    hole_diameter_mm : float
        Bead-hole inner diameter in mm.
    drape : str
        "fine" selects a smaller thread; "heavy" selects a larger one.
        Accepted values: "fine", "medium", "heavy".

    Returns
    -------
    str
        Silk size code (e.g. "D").
    """
    clearance = hole_diameter_mm * 0.38   # must pass doubled: 2 × thread_d ≤ hole_d
    if drape == "fine":
        clearance *= 0.85
    elif drape == "heavy":
        clearance *= 1.15

    best = "A"
    for size, diam in _SILK_SIZES.items():
        if diam <= clearance:
            best = size
    return best


def _wire_gauge_for_hole(hole_diameter_mm: float, drape: str = "medium") -> str:
    """Pick a Beadalon-style wire gauge for the given hole diameter.

    Selects largest gauge diameter ≤ hole_diameter * 0.45 (leaves room for
    crimp and double-pass at ends).

    Parameters
    ----------
    hole_diameter_mm : float
        Bead-hole inner diameter in mm.
    drape : str
        "flexible"/"ultra_flexible" preferred for necklaces; "stiff" for bracelets.

    Returns
    -------
    str
        Wire gauge key (e.g. "0.018in").
    """
    target_max = hole_diameter_mm * 0.45
    if drape in ("flexible", "ultra_flexible"):
        # Prefer more flexible gauges (smaller diameter)
        candidates = sorted(
            ((d, g) for g, (d, q) in _WIRE_GAUGES.items() if d <= target_max),
            reverse=True,
        )
    else:
        # Accept stiffer gauges
        candidates = sorted(
            ((d, g) for g, (d, q) in _WIRE_GAUGES.items() if d <= target_max),
            reverse=True,
        )
    if not candidates:
        return "0.010in"
    return candidates[0][1]


def _pick_clasp(strand_count: int, total_weight_g: float) -> str:
    """Select a clasp style based on strand count and estimated weight.

    Parameters
    ----------
    strand_count : int
        Number of parallel strands (1 for a single strand).
    total_weight_g : float
        Estimated total weight of the beads in grams.

    Returns
    -------
    str
        Clasp style name.
    """
    for min_strands, max_weight, style in _CLASP_RULES:
        if strand_count >= min_strands and total_weight_g <= max_weight:
            return style
    return "toggle"


def _estimate_bead_weight_g(
    bead_diameter_mm: float,
    bead_count: int,
    material: str = "freshwater_pearl",
) -> float:
    """Rough weight estimate for a string of beads.

    Uses volume of a sphere scaled by a material density:
      - freshwater_pearl / akoya / south_sea: ~2.7 g/cm³
      - crystal / glass: ~2.5 g/cm³
      - gemstone / semi_precious: ~3.2 g/cm³
      - plastic / acrylic: ~1.2 g/cm³
    """
    _DENSITY: dict[str, float] = {
        "freshwater_pearl":  2.7,
        "akoya_pearl":       2.7,
        "south_sea_pearl":   2.7,
        "tahitian_pearl":    2.7,
        "crystal":           2.5,
        "glass":             2.5,
        "gemstone":          3.2,
        "semi_precious":     3.2,
        "wood":              0.7,
        "plastic":           1.2,
        "acrylic":           1.2,
        "metal":             8.5,
    }
    density = _DENSITY.get(material.lower().replace(" ", "_"), 2.7)
    r_cm = (bead_diameter_mm / 2.0) / 10.0
    vol_cm3 = (4.0 / 3.0) * math.pi * r_cm ** 3
    return round(vol_cm3 * density * bead_count, 3)


def _knot_gap_effective(thread_diameter_mm: float) -> float:
    """Effective gap added by a knot between beads.

    A hand-tied pearl knot adds approximately 2.2 × thread_diameter.
    """
    return round(_KNOT_DIAMETER_MULT * thread_diameter_mm, 4)


# ---------------------------------------------------------------------------
# Core computation: stringing layout
# ---------------------------------------------------------------------------

def compute_stringing_layout(
    target_length_mm: float,
    bead_diameter_mm: float,
    *,
    clasp_length_mm: float = 10.0,
    style: str = "knotted",
    hole_diameter_mm: Optional[float] = None,
    thread_diameter_mm: Optional[float] = None,
    strand_count: int = 1,
    material: str = "freshwater_pearl",
    drape: str = "medium",
) -> dict:
    """Compute a complete bead-stringing layout.

    Parameters
    ----------
    target_length_mm : float
        Desired finished length of the necklace/bracelet in mm.
    bead_diameter_mm : float
        Diameter of each bead in mm (assumes uniform beads; use
        compute_graduated_schedule for tapered designs).
    clasp_length_mm : float
        Total length contribution of the clasp assembly in mm. Default 10 mm.
    style : str
        Layout style.  One of:
          "knotted"       — pearl-knotted between every bead (silk thread)
          "unknotted"     — beads strung directly, no knots (wire or silk)
          "floating"      — illusion/floating: beads crimped at intervals on
                           monofilament / wire, visible gaps between beads
    hole_diameter_mm : float, optional
        Inner diameter of bead holes in mm.  Defaults to bead_diameter_mm * 0.15.
    thread_diameter_mm : float, optional
        Explicit thread/wire diameter override in mm.  If omitted, one is
        selected automatically based on hole_diameter_mm and style.
    strand_count : int
        Number of parallel strands (1 = single strand; ≥ 2 = multi-strand).
    material : str
        Bead material (used for weight estimate and clasp selection).
    drape : str
        Desired drape quality: "fine", "medium", or "heavy".

    Returns
    -------
    dict
        Layout spec including bead_count, cord_length_needed_mm, thread/wire pick,
        finishing, clasp recommendation, and per-strand details.

    Notes
    -----
    Never raises.  Returns ``{"error": "...", "code": "..."}`` on invalid input.
    """
    # --- Validate inputs ---
    if target_length_mm <= 0:
        return {"error": "target_length_mm must be > 0", "code": "BAD_ARGS"}
    if bead_diameter_mm <= 0:
        return {"error": "bead_diameter_mm must be > 0", "code": "BAD_ARGS"}
    if clasp_length_mm < 0:
        return {"error": "clasp_length_mm must be >= 0", "code": "BAD_ARGS"}
    if strand_count < 1:
        return {"error": "strand_count must be >= 1", "code": "BAD_ARGS"}

    _valid_styles = {"knotted", "unknotted", "floating"}
    style = style.strip().lower().replace("-", "_").replace(" ", "_")
    if style not in _valid_styles:
        return {
            "error": f"Unknown style {style!r}. Valid: {sorted(_valid_styles)}",
            "code": "BAD_ARGS",
        }

    _valid_drapes = {"fine", "medium", "heavy", "flexible", "ultra_flexible", "stiff"}
    drape = drape.strip().lower()
    if drape not in _valid_drapes:
        drape = "medium"

    # Default hole diameter
    if hole_diameter_mm is None:
        hole_diameter_mm = round(bead_diameter_mm * 0.15, 3)
    if hole_diameter_mm <= 0:
        return {"error": "hole_diameter_mm must be > 0", "code": "BAD_ARGS"}

    # --- Thread / wire selection ---
    thread_type: str
    if style == "knotted":
        thread_type = "silk"
        if thread_diameter_mm is None:
            size = _silk_for_hole(hole_diameter_mm, drape)
            thread_diameter_mm = _SILK_SIZES[size]
            thread_spec = {"type": "silk", "size": size, "diameter_mm": thread_diameter_mm}
        else:
            # Match provided diameter to nearest silk size
            best_size = min(_SILK_SIZES, key=lambda s: abs(_SILK_SIZES[s] - thread_diameter_mm))
            thread_spec = {"type": "silk", "size": best_size, "diameter_mm": round(thread_diameter_mm, 4)}
    else:
        thread_type = "wire"
        if thread_diameter_mm is None:
            gauge = _wire_gauge_for_hole(hole_diameter_mm, drape)
            thread_diameter_mm = _WIRE_GAUGES[gauge][0]
            thread_spec = {
                "type": "wire",
                "gauge": gauge,
                "diameter_mm": thread_diameter_mm,
                "drape_quality": _WIRE_GAUGES[gauge][1],
            }
        else:
            gauge = _wire_gauge_for_hole(hole_diameter_mm, drape)
            thread_spec = {
                "type": "wire",
                "gauge": gauge,
                "diameter_mm": round(thread_diameter_mm, 4),
                "drape_quality": _WIRE_GAUGES[gauge][1],
            }

    # --- Bead count calculation ---
    # Knot gap: only for knotted style; floating gaps are larger
    if style == "knotted":
        knot_gap_mm = _knot_gap_effective(thread_diameter_mm)
    elif style == "floating":
        # Floating illusion: beads spaced at roughly 2× bead diameter apart
        knot_gap_mm = bead_diameter_mm * 2.0
    else:
        knot_gap_mm = 0.0

    working_length = target_length_mm - clasp_length_mm
    if working_length <= 0:
        return {
            "error": (
                f"target_length_mm ({target_length_mm}) must be greater than "
                f"clasp_length_mm ({clasp_length_mm})"
            ),
            "code": "BAD_ARGS",
        }

    slot = bead_diameter_mm + knot_gap_mm
    bead_count = max(1, math.floor(working_length / slot))

    # Actual strung length (without clasp)
    strung_length_mm = round(bead_count * slot, 3)
    # Final necklace length with clasp
    actual_length_mm = round(strung_length_mm + clasp_length_mm, 3)

    # --- Cord length needed ---
    # Thread runs through every bead + through every knot + finishing tails
    # Knot take-up: each knot consumes thread_diameter * pi (wraps + tuck)
    knot_takeup_mm = 0.0
    if style == "knotted":
        knots_count = bead_count - 1  # knots between beads; +2 at ends optional
        knot_takeup_mm = round(knots_count * math.pi * thread_diameter_mm, 3)

    cord_for_beads_mm = target_length_mm  # thread spans the full finished length
    cord_length_needed_mm = round(
        cord_for_beads_mm + knot_takeup_mm + 2.0 * _TAIL_LENGTH_MM,
        1,
    )

    # --- Weight estimate and clasp ---
    weight_g = _estimate_bead_weight_g(bead_diameter_mm, bead_count * strand_count, material)
    clasp_style = _pick_clasp(strand_count, weight_g)

    # --- Finishing ---
    if style == "knotted":
        finishing = {
            "method": "french_wire",
            "french_wire_length_per_end_mm": _FRENCH_WIRE_LENGTH_PER_END_MM,
            "half_hitch_knots_at_ends": 2,
        }
    else:
        finishing = {
            "method": "crimp_tube",
            "crimp_tube_count_per_end": 1,
            "crimp_tube_length_mm": _CRIMP_TUBE_LENGTH_MM,
            "crimp_covers": True,
        }

    return {
        "style": style,
        "target_length_mm": target_length_mm,
        "actual_length_mm": actual_length_mm,
        "bead_count": bead_count,
        "bead_diameter_mm": round(bead_diameter_mm, 4),
        "knot_gap_mm": round(knot_gap_mm, 4),
        "clasp_length_mm": round(clasp_length_mm, 4),
        "clasp_style": clasp_style,
        "strand_count": strand_count,
        "thread": thread_spec,
        "cord_length_needed_mm": cord_length_needed_mm,
        "knot_takeup_mm": round(knot_takeup_mm, 3),
        "tail_length_per_end_mm": _TAIL_LENGTH_MM,
        "finishing": finishing,
        "weight_estimate_g": weight_g,
        "material": material,
    }


# ---------------------------------------------------------------------------
# Graduated / taper schedule
# ---------------------------------------------------------------------------

def compute_graduated_schedule(
    center_bead_diameter_mm: float,
    end_bead_diameter_mm: float,
    bead_count: int,
    *,
    taper_steps: Optional[int] = None,
    step_size_mm: Optional[float] = None,
) -> dict:
    """Compute a graduated (tapered) bead-size schedule.

    The schedule runs from ``end_bead_diameter_mm`` at position 0 (clasp end)
    through symmetric steps up to ``center_bead_diameter_mm`` at the centre,
    then mirrors back.

    Parameters
    ----------
    center_bead_diameter_mm : float
        Largest bead diameter (at centre) in mm.
    end_bead_diameter_mm : float
        Smallest bead diameter (at ends, near clasp) in mm.
    bead_count : int
        Total number of beads in the strand (must be odd for a symmetric design;
        even count is accepted and the centre two beads share the peak diameter).
    taper_steps : int, optional
        Number of distinct size steps from end to centre.  If omitted, one step
        per 2 mm of diameter range (minimum 2).
    step_size_mm : float, optional
        Explicit size increment per step in mm.  Takes precedence over
        ``taper_steps`` when provided.

    Returns
    -------
    dict
        ``{
            "bead_count": int,
            "schedule": list[float],   # diameter per bead position, mm
            "unique_sizes": list[float],
            "is_symmetric": bool,
            "is_monotone": bool,
          }``

    Notes
    -----
    Never raises; returns ``{"error": ..., "code": ...}`` on bad input.
    """
    if center_bead_diameter_mm <= 0:
        return {"error": "center_bead_diameter_mm must be > 0", "code": "BAD_ARGS"}
    if end_bead_diameter_mm <= 0:
        return {"error": "end_bead_diameter_mm must be > 0", "code": "BAD_ARGS"}
    if center_bead_diameter_mm < end_bead_diameter_mm:
        return {
            "error": "center_bead_diameter_mm must be >= end_bead_diameter_mm",
            "code": "BAD_ARGS",
        }
    if bead_count < 1:
        return {"error": "bead_count must be >= 1", "code": "BAD_ARGS"}

    diameter_range = center_bead_diameter_mm - end_bead_diameter_mm

    # Determine step size
    if step_size_mm is not None:
        if step_size_mm <= 0:
            return {"error": "step_size_mm must be > 0", "code": "BAD_ARGS"}
        steps = max(1, round(diameter_range / step_size_mm))
    elif taper_steps is not None:
        if taper_steps < 1:
            return {"error": "taper_steps must be >= 1", "code": "BAD_ARGS"}
        steps = taper_steps
    else:
        steps = max(2, round(diameter_range / 2.0))

    # Build the half-schedule (end → centre inclusive)
    if steps == 0 or diameter_range == 0:
        half = [center_bead_diameter_mm] * ((bead_count + 1) // 2)
    else:
        half_count = (bead_count + 1) // 2
        # Interpolate linearly from end to centre
        half = []
        for i in range(half_count):
            t = i / max(half_count - 1, 1)
            d = end_bead_diameter_mm + t * diameter_range
            half.append(round(d, 4))

    # Mirror to build full schedule
    if bead_count % 2 == 1:
        # Odd: centre bead is single peak
        schedule = half + list(reversed(half[:-1]))
    else:
        # Even: two centre beads share peak
        schedule = half + list(reversed(half))

    # Trim / pad to exact bead_count
    schedule = schedule[:bead_count]
    while len(schedule) < bead_count:
        schedule.append(end_bead_diameter_mm)

    unique_sizes = sorted(set(round(d, 4) for d in schedule))
    is_symmetric = schedule == list(reversed(schedule))
    # Monotone up to centre then monotone down
    mid = bead_count // 2
    ascending = all(schedule[i] <= schedule[i + 1] for i in range(mid))
    descending = all(schedule[mid + i] >= schedule[mid + i + 1] for i in range(len(schedule) - mid - 1))
    is_monotone = ascending and descending

    return {
        "bead_count": bead_count,
        "schedule": schedule,
        "unique_sizes": unique_sizes,
        "is_symmetric": is_symmetric,
        "is_monotone": is_monotone,
        "center_bead_diameter_mm": round(center_bead_diameter_mm, 4),
        "end_bead_diameter_mm": round(end_bead_diameter_mm, 4),
    }


# ---------------------------------------------------------------------------
# Multi-strand torsade
# ---------------------------------------------------------------------------

def compute_torsade_spec(
    strand_count: int,
    target_length_mm: float,
    bead_diameter_mm: float,
    *,
    clasp_length_mm: float = 15.0,
    style: str = "knotted",
    hole_diameter_mm: Optional[float] = None,
    material: str = "freshwater_pearl",
    drape: str = "medium",
    twist_period_mm: Optional[float] = None,
) -> dict:
    """Compute a multi-strand torsade (twisted necklace) specification.

    Each strand in the torsade is slightly longer than the finished length to
    allow for the twist.  The twist take-up factor depends on the number of
    strands and the twist period.

    Parameters
    ----------
    strand_count : int
        Number of strands in the torsade (typically 2–7).
    target_length_mm : float
        Desired finished length after twisting in mm.
    bead_diameter_mm : float
        Uniform bead diameter on all strands in mm.
    clasp_length_mm : float
        Clasp contribution in mm.  Multi-strand clasps are typically longer.
    style : str
        Stringing style per strand: "knotted" or "unknotted".
    hole_diameter_mm : float, optional
        Bead-hole diameter in mm.
    material : str
        Bead material.
    drape : str
        Drape preference.
    twist_period_mm : float, optional
        Distance along the necklace for one full twist.  Defaults to
        ``target_length_mm / (strand_count * 1.5)``.

    Returns
    -------
    dict
        Torsade spec with per-strand layout, twist take-up, and multi-strand
        clasp recommendation.
    """
    if strand_count < 2:
        return {"error": "strand_count must be >= 2 for a torsade", "code": "BAD_ARGS"}
    if strand_count > 20:
        return {"error": "strand_count must be <= 20", "code": "BAD_ARGS"}
    if target_length_mm <= 0:
        return {"error": "target_length_mm must be > 0", "code": "BAD_ARGS"}
    if bead_diameter_mm <= 0:
        return {"error": "bead_diameter_mm must be > 0", "code": "BAD_ARGS"}

    if twist_period_mm is None:
        twist_period_mm = round(target_length_mm / (strand_count * 1.5), 1)
    if twist_period_mm <= 0:
        return {"error": "twist_period_mm must be > 0", "code": "BAD_ARGS"}

    # Twist take-up: each strand follows a helical path.
    # For a helix with pitch P and radius r = bead_diameter * strand_count / (2 * pi):
    # helix_length / straight_length ≈ sqrt(1 + (2*pi*r/P)^2)
    # Approximation: ~1–3 % for typical values.
    n_turns = target_length_mm / twist_period_mm
    helix_radius_mm = (bead_diameter_mm * strand_count) / (2.0 * math.pi)
    helix_circumference_per_turn = 2.0 * math.pi * helix_radius_mm
    strand_per_turn_length = math.sqrt(twist_period_mm ** 2 + helix_circumference_per_turn ** 2)
    twist_factor = strand_per_turn_length / twist_period_mm  # > 1

    per_strand_target_mm = round(target_length_mm * twist_factor, 1)

    # Compute layout for a single strand at the extended length
    strand_layout = compute_stringing_layout(
        per_strand_target_mm,
        bead_diameter_mm,
        clasp_length_mm=clasp_length_mm,
        style=style,
        hole_diameter_mm=hole_diameter_mm,
        strand_count=1,   # per-strand calculation
        material=material,
        drape=drape,
    )

    if "error" in strand_layout:
        return strand_layout

    total_bead_count = strand_layout["bead_count"] * strand_count
    total_weight_g = _estimate_bead_weight_g(bead_diameter_mm, total_bead_count, material)
    clasp_style = _pick_clasp(strand_count, total_weight_g)

    # Multi-strand clasps: upgrade to box or toggle for >= 3 strands
    if strand_count >= 3 and clasp_style == "lobster":
        clasp_style = "box"

    return {
        "strand_count": strand_count,
        "target_length_mm": target_length_mm,
        "per_strand_target_mm": per_strand_target_mm,
        "twist_factor": round(twist_factor, 4),
        "twist_period_mm": round(twist_period_mm, 1),
        "n_full_turns": round(n_turns, 2),
        "per_strand_bead_count": strand_layout["bead_count"],
        "total_bead_count": total_bead_count,
        "per_strand_cord_length_mm": strand_layout["cord_length_needed_mm"],
        "clasp_style": clasp_style,
        "clasp_length_mm": clasp_length_mm,
        "thread": strand_layout["thread"],
        "finishing": strand_layout["finishing"],
        "total_weight_estimate_g": round(total_weight_g, 3),
        "style": style,
        "material": material,
    }


# ---------------------------------------------------------------------------
# Necklace preset helper
# ---------------------------------------------------------------------------

def necklace_preset_mm(name: str) -> Optional[float]:
    """Return the nominal length in mm for a named necklace preset.

    Parameters
    ----------
    name : str
        One of: collar, choker, princess, matinee, opera, rope.

    Returns
    -------
    float or None
        Nominal length in mm, or None if the name is unrecognised.
    """
    return NECKLACE_PRESETS.get(name.strip().lower())


# ---------------------------------------------------------------------------
# LLM tool specs
# ---------------------------------------------------------------------------

_VALID_STYLES = sorted({"knotted", "unknotted", "floating"})
_VALID_MATERIALS = sorted({
    "freshwater_pearl", "akoya_pearl", "south_sea_pearl", "tahitian_pearl",
    "crystal", "glass", "gemstone", "semi_precious", "wood", "plastic", "acrylic", "metal",
})
_VALID_PRESETS = sorted(NECKLACE_PRESETS.keys())
_VALID_CLASP_STYLES = sorted({"box", "lobster", "toggle", "magnetic"})
_VALID_DRAPES = sorted({"fine", "medium", "heavy"})


# -- jewelry_stringing_layout ------------------------------------------------

jewelry_stringing_layout_spec = ToolSpec(
    name="jewelry_stringing_layout",
    description=(
        "Design a bead-stringing layout: compute bead count, cord length, thread/wire "
        "pick, clasp recommendation, and finishing details for a pearl or bead necklace.\n\n"
        "Supports knotted (pearl), unknotted, and floating-illusion styles.\n\n"
        "Provide either ``target_length_mm`` or ``preset`` (collar/choker/princess/matinee/"
        "opera/rope).  All other parameters are optional with sensible defaults.\n\n"
        "Returns: bead_count, actual_length_mm, cord_length_needed_mm, thread spec, "
        "clasp_style, finishing method, weight estimate."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "target_length_mm": {
                "type": "number",
                "description": (
                    "Desired finished necklace / bracelet length in mm. "
                    "Superseded by ``preset`` if both are provided."
                ),
            },
            "preset": {
                "type": "string",
                "enum": _VALID_PRESETS,
                "description": (
                    "Named necklace length preset. "
                    "One of: " + ", ".join(_VALID_PRESETS) + ". "
                    "Sets target_length_mm to the nominal preset value."
                ),
            },
            "bead_diameter_mm": {
                "type": "number",
                "description": "Uniform bead diameter in mm (e.g. 7.0 for 7 mm pearls).",
            },
            "clasp_length_mm": {
                "type": "number",
                "description": (
                    "Total length contribution of the clasp assembly in mm. "
                    "Default 10 mm.  Increase for multi-row clasps (15–20 mm)."
                ),
            },
            "style": {
                "type": "string",
                "enum": _VALID_STYLES,
                "description": (
                    "Stringing style. "
                    "knotted = silk with hand-tied pearl knots between beads; "
                    "unknotted = beads directly on wire/silk, no spacer knots; "
                    "floating = illusion/floating strand, large gaps between beads."
                ),
            },
            "hole_diameter_mm": {
                "type": "number",
                "description": (
                    "Bead-hole inner diameter in mm. "
                    "Defaults to bead_diameter_mm × 0.15 if omitted."
                ),
            },
            "thread_diameter_mm": {
                "type": "number",
                "description": (
                    "Explicit thread or wire diameter in mm. "
                    "If omitted, the best thread is selected automatically."
                ),
            },
            "strand_count": {
                "type": "integer",
                "description": "Number of parallel strands (1 = single; 2+ = multi-strand). Default 1.",
            },
            "material": {
                "type": "string",
                "enum": _VALID_MATERIALS,
                "description": (
                    "Bead material — used for weight estimate and clasp selection. "
                    "Default freshwater_pearl."
                ),
            },
            "drape": {
                "type": "string",
                "enum": _VALID_DRAPES,
                "description": (
                    "Desired thread / wire drape quality: fine, medium, or heavy. "
                    "Influences thread size selection. Default medium."
                ),
            },
        },
        "required": ["bead_diameter_mm"],
    },
)


@register(jewelry_stringing_layout_spec, write=False)
async def run_jewelry_stringing_layout(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args) if args.strip() else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    bead_d_raw = a.get("bead_diameter_mm", None)
    if bead_d_raw is None:
        return err_payload("bead_diameter_mm is required", "BAD_ARGS")
    try:
        bead_diameter_mm = float(bead_d_raw)
    except (TypeError, ValueError):
        return err_payload("bead_diameter_mm must be a number", "BAD_ARGS")

    # Resolve target length
    preset = a.get("preset", None)
    if preset is not None:
        target_mm = necklace_preset_mm(str(preset))
        if target_mm is None:
            return err_payload(
                f"Unknown preset {preset!r}. Valid: {_VALID_PRESETS}", "BAD_ARGS"
            )
    else:
        raw_len = a.get("target_length_mm", None)
        if raw_len is None:
            return err_payload(
                "Either target_length_mm or preset is required", "BAD_ARGS"
            )
        try:
            target_mm = float(raw_len)
        except (TypeError, ValueError):
            return err_payload("target_length_mm must be a number", "BAD_ARGS")

    kwargs: dict = {}
    _opt_floats = ["clasp_length_mm", "hole_diameter_mm", "thread_diameter_mm"]
    for key in _opt_floats:
        raw = a.get(key, None)
        if raw is not None:
            try:
                kwargs[key] = float(raw)
            except (TypeError, ValueError):
                return err_payload(f"{key} must be a number", "BAD_ARGS")

    if "strand_count" in a:
        try:
            kwargs["strand_count"] = int(a["strand_count"])
        except (TypeError, ValueError):
            return err_payload("strand_count must be an integer", "BAD_ARGS")

    for key in ("style", "material", "drape"):
        if key in a:
            kwargs[key] = str(a[key])

    result = compute_stringing_layout(target_mm, bead_diameter_mm, **kwargs)
    if "error" in result:
        return err_payload(result["error"], result.get("code", "ERROR"))
    return ok_payload(result)


# -- jewelry_stringing_graduated ---------------------------------------------

jewelry_stringing_graduated_spec = ToolSpec(
    name="jewelry_stringing_graduated",
    description=(
        "Compute a graduated / tapered bead schedule for a pearl or bead necklace.\n\n"
        "Returns the diameter at each bead position from clasp-end to clasp-end, "
        "symmetric around the centre.  Verifies the schedule is monotone and symmetric.\n\n"
        "Use ``bead_count`` from ``jewelry_stringing_layout`` as input here."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "center_bead_diameter_mm": {
                "type": "number",
                "description": "Largest (centre) bead diameter in mm.",
            },
            "end_bead_diameter_mm": {
                "type": "number",
                "description": "Smallest (end / clasp) bead diameter in mm.",
            },
            "bead_count": {
                "type": "integer",
                "description": "Total number of beads in the strand.",
            },
            "taper_steps": {
                "type": "integer",
                "description": (
                    "Number of distinct size steps from end to centre. "
                    "Omit to auto-derive from diameter range."
                ),
            },
            "step_size_mm": {
                "type": "number",
                "description": (
                    "Explicit step increment in mm.  Overrides taper_steps when provided."
                ),
            },
        },
        "required": ["center_bead_diameter_mm", "end_bead_diameter_mm", "bead_count"],
    },
)


@register(jewelry_stringing_graduated_spec, write=False)
async def run_jewelry_stringing_graduated(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args) if args.strip() else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    for key in ("center_bead_diameter_mm", "end_bead_diameter_mm"):
        if key not in a:
            return err_payload(f"{key} is required", "BAD_ARGS")
        try:
            a[key] = float(a[key])
        except (TypeError, ValueError):
            return err_payload(f"{key} must be a number", "BAD_ARGS")

    if "bead_count" not in a:
        return err_payload("bead_count is required", "BAD_ARGS")
    try:
        bead_count = int(a["bead_count"])
    except (TypeError, ValueError):
        return err_payload("bead_count must be an integer", "BAD_ARGS")

    kwargs: dict = {}
    if "taper_steps" in a:
        try:
            kwargs["taper_steps"] = int(a["taper_steps"])
        except (TypeError, ValueError):
            return err_payload("taper_steps must be an integer", "BAD_ARGS")
    if "step_size_mm" in a:
        try:
            kwargs["step_size_mm"] = float(a["step_size_mm"])
        except (TypeError, ValueError):
            return err_payload("step_size_mm must be a number", "BAD_ARGS")

    result = compute_graduated_schedule(
        float(a["center_bead_diameter_mm"]),
        float(a["end_bead_diameter_mm"]),
        bead_count,
        **kwargs,
    )
    if "error" in result:
        return err_payload(result["error"], result.get("code", "ERROR"))
    return ok_payload(result)


# -- jewelry_stringing_torsade -----------------------------------------------

jewelry_stringing_torsade_spec = ToolSpec(
    name="jewelry_stringing_torsade",
    description=(
        "Compute a multi-strand torsade (twisted necklace) specification.\n\n"
        "Each strand is slightly longer than the finished length to accommodate "
        "the helical twist.  Returns per-strand bead count, cord length, twist factor, "
        "and a multi-strand clasp recommendation."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "strand_count": {
                "type": "integer",
                "description": "Number of strands in the torsade (2–7 typical).",
            },
            "target_length_mm": {
                "type": "number",
                "description": "Desired finished length after twisting in mm.",
            },
            "bead_diameter_mm": {
                "type": "number",
                "description": "Bead diameter on all strands in mm.",
            },
            "clasp_length_mm": {
                "type": "number",
                "description": "Clasp length in mm. Default 15 mm for multi-strand clasps.",
            },
            "style": {
                "type": "string",
                "enum": _VALID_STYLES,
                "description": "Stringing style per strand.",
            },
            "hole_diameter_mm": {
                "type": "number",
                "description": "Bead-hole inner diameter in mm.",
            },
            "material": {
                "type": "string",
                "enum": _VALID_MATERIALS,
                "description": "Bead material. Default freshwater_pearl.",
            },
            "drape": {
                "type": "string",
                "enum": _VALID_DRAPES,
                "description": "Desired drape quality. Default medium.",
            },
            "twist_period_mm": {
                "type": "number",
                "description": (
                    "Distance along necklace for one complete twist in mm. "
                    "Defaults to target_length_mm / (strand_count × 1.5)."
                ),
            },
        },
        "required": ["strand_count", "target_length_mm", "bead_diameter_mm"],
    },
)


@register(jewelry_stringing_torsade_spec, write=False)
async def run_jewelry_stringing_torsade(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args) if args.strip() else {}
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    for key in ("strand_count",):
        if key not in a:
            return err_payload(f"{key} is required", "BAD_ARGS")
        try:
            a[key] = int(a[key])
        except (TypeError, ValueError):
            return err_payload(f"{key} must be an integer", "BAD_ARGS")

    for key in ("target_length_mm", "bead_diameter_mm"):
        if key not in a:
            return err_payload(f"{key} is required", "BAD_ARGS")
        try:
            a[key] = float(a[key])
        except (TypeError, ValueError):
            return err_payload(f"{key} must be a number", "BAD_ARGS")

    kwargs: dict = {}
    for key in ("clasp_length_mm", "hole_diameter_mm", "twist_period_mm"):
        if key in a:
            try:
                kwargs[key] = float(a[key])
            except (TypeError, ValueError):
                return err_payload(f"{key} must be a number", "BAD_ARGS")

    for key in ("style", "material", "drape"):
        if key in a:
            kwargs[key] = str(a[key])

    result = compute_torsade_spec(
        int(a["strand_count"]),
        float(a["target_length_mm"]),
        float(a["bead_diameter_mm"]),
        **kwargs,
    )
    if "error" in result:
        return err_payload(result["error"], result.get("code", "ERROR"))
    return ok_payload(result)
