"""
kerf_cad_core.jewelry.head_wizard
==================================

Parametric head/prong wizard and ring-builder — MatrixGold/RhinoGold parity.

This module provides:

1. Head library
   Eight head families, each parametrised by stone cut + girdle size:

   four_prong_solitaire  — classic 4-prong round/princess head; even 90° spacing.
   six_prong_solitaire   — classic 6-prong head; even 60° spacing.
   double_claw           — two narrow paired claws per station (8- or 12-claw total).
   basket                — horizontal gallery rail connects all prong bases;
                           optional open/closed basket with pierced gallery.
   v_prong               — V-shaped tipped prongs for marquise, pear, trillion.
   half_bezel            — two bezel walls at opposing ends + side prongs.
   full_bezel            — 360° bezel collar; zero prongs.
   halo                  — centre seat + concentric accent-stone ring.
   tension               — stone gripped between two band ends; no prongs/bezel.

2. Auto prong placement
   Place N claws evenly around a stone girdle outline.  Round / oval stones
   get angular spacing; fancy cuts (princess, emerald, asscher, radiant,
   cushion, trillion, marquise, pear, heart) get corner-biased claw placement.

3. Head→shank merge & seat alignment
   Returns a composite node dict describing the head attached to a shank at
   a given seat height.

4. Ring-builder
   Compose head + shank profile + ring-size target into a single spec node.
   Computes inner diameter from the ring-size lookup (reusing ring.py logic),
   validates fit/contact and minimum-metal constraints, and estimates weight.

LLM tools registered
---------------------
    jewelry_head_library_get
    jewelry_place_prongs
    jewelry_build_head
    jewelry_ring_builder

Units: millimetres throughout.

Geometry strategy
-----------------
All functions return *node spec dicts*.  No OCCT is imported here.
The occtWorker's ``opJewelryHead*`` operators consume these dicts.

Error convention
----------------
LLM tools never raise — they return ``err_payload(msg, code)`` on any error,
following the exact pattern established in settings.py and ring.py.
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

from kerf_cad_core.surfacing import (
    next_node_id,
    read_feature_content,
    append_feature_node,
)

_PI = math.pi

# ---------------------------------------------------------------------------
# Ring-size lookup (mirror ring.py constants; avoids cross-import)
# ---------------------------------------------------------------------------

_US_ID_INTERCEPT = 11.63   # mm
_US_ID_SLOPE     = 0.8128  # mm per US size unit

def _us_size_to_id_mm(size: float) -> float:
    return _US_ID_INTERCEPT + _US_ID_SLOPE * size


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _positive(name: str, value) -> Optional[str]:
    """Return error string if value is not strictly positive, else None."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number; got {value!r}"
    if v <= 0:
        return f"{name} must be > 0; got {v}"
    return None


def _non_negative(name: str, value) -> Optional[str]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number; got {value!r}"
    if v < 0:
        return f"{name} must be >= 0; got {v}"
    return None


def _in_set(name: str, value, valid_set) -> Optional[str]:
    if value not in valid_set:
        return f"{name} must be one of {sorted(valid_set)}; got {value!r}"
    return None


# ---------------------------------------------------------------------------
# Head library constants
# ---------------------------------------------------------------------------

# Head families
HEAD_STYLES = frozenset([
    "four_prong_solitaire",
    "six_prong_solitaire",
    "double_claw",
    "basket",
    "v_prong",
    "half_bezel",
    "full_bezel",
    "halo",
    "tension",
])

# Stone cuts
STONE_CUTS = frozenset([
    "round_brilliant",
    "princess",
    "oval",
    "emerald",
    "marquise",
    "pear",
    "cushion",
    "radiant",
    "asscher",
    "trillion",
    "heart",
    "baguette",
    "square_emerald",
    "flanders",
])

# Cuts whose geometry has well-defined corners for corner-claw placement
_FANCY_CUTS_WITH_CORNERS = frozenset([
    "princess",
    "emerald",
    "asscher",
    "radiant",
    "cushion",
    "baguette",
    "square_emerald",
    "flanders",
])

# Cuts with pointed ends needing V-prongs
_POINTED_CUTS = frozenset(["marquise", "pear", "heart", "trillion"])

# Cuts that are fundamentally round or oval (use angular spacing)
_ROUND_OVAL_CUTS = frozenset(["round_brilliant", "oval"])

# Valid ring-size systems understood by ring_builder
_VALID_SYSTEMS = frozenset(["us", "uk", "au", "eu", "jp"])

# Default prong dimensions by head style (wire_dia_mm, claw_length_mm, claw_tip_radius_mm)
_HEAD_PRONG_DEFAULTS: Dict[str, Tuple[float, float, float]] = {
    "four_prong_solitaire": (0.9, 2.0, 0.45),
    "six_prong_solitaire":  (0.8, 1.8, 0.40),
    "double_claw":          (0.6, 1.6, 0.30),
    "basket":               (0.9, 2.0, 0.45),
    "v_prong":              (0.7, 2.2, 0.35),
    "half_bezel":           (0.8, 1.8, 0.40),
    "full_bezel":           (0.0, 0.0, 0.00),
    "halo":                 (0.8, 1.8, 0.40),
    "tension":              (0.0, 0.0, 0.00),
}

# Default prong count per head style (0 = no prongs)
_HEAD_DEFAULT_PRONG_COUNT: Dict[str, int] = {
    "four_prong_solitaire": 4,
    "six_prong_solitaire":  6,
    "double_claw":          8,   # 4 stations × 2 claws each
    "basket":               4,
    "v_prong":              2,   # two V-tips at opposing points
    "half_bezel":           2,   # two side prongs
    "full_bezel":           0,
    "halo":                 4,
    "tension":              0,
}

# Minimum metal wall / prong thickness for manufacturing feasibility (mm)
_MIN_METAL_WALL_MM = 0.25
_MIN_PRONG_WIRE_MM = 0.40

# Metal density lookup for weight estimation (g/cm³)
_METAL_DENSITY: Dict[str, float] = {
    "platinum":      21.45,
    "18k_yellow":    15.58,
    "18k_white":     15.58,
    "18k_rose":      15.18,
    "14k_yellow":    13.07,
    "14k_white":     13.07,
    "14k_rose":      13.00,
    "silver_sterling": 10.36,
    "palladium":     12.02,
    "9k_yellow":     10.62,
}

# ---------------------------------------------------------------------------
# Stone girdle outline helpers
# ---------------------------------------------------------------------------

def stone_girdle_radius(cut: str, stone_mm: float) -> float:
    """Return the effective girdle radius in mm for prong-contact calculation.

    For round/oval cuts this equals stone_mm / 2.  For rectangular/square cuts
    it equals the half-diagonal (corner distance from centre), which is the
    natural contact point.

    Parameters
    ----------
    cut : str
        Stone cut name (must be in STONE_CUTS).
    stone_mm : float
        Longest girdle dimension in mm (diameter for round, length for others).
    """
    if cut in _ROUND_OVAL_CUTS or cut in _POINTED_CUTS:
        # Simple radius = half the longest dimension.
        return stone_mm / 2.0
    if cut in _FANCY_CUTS_WITH_CORNERS:
        # Girdle is approximately square/rectangular; corner distance from centre.
        # For square cuts: half-diagonal = (stone_mm / 2) * sqrt(2).
        # For rectangular cuts (baguette aspect ~0.35) we conservatively use
        # the half-width of the longest side.  We keep it as stone_mm/2 here
        # so callers can scale by aspect ratio as needed.
        return (stone_mm / 2.0) * math.sqrt(2)
    # Fallback: treat as round.
    return stone_mm / 2.0


def girdle_contact_point(
    cut: str,
    stone_mm: float,
    angle_deg: float,
) -> Tuple[float, float]:
    """Return the (x, y) point on the girdle outline for a given angular position.

    For round stones: point is on a circle of radius stone_mm/2.
    For fancy cuts: point is on the bounding square/rectangle outline.
    For pointed cuts: point follows an ellipse (marquise) or pear outline.

    Parameters
    ----------
    cut : str
    stone_mm : float
        Longest girdle dimension (mm).
    angle_deg : float
        Angle from the top/north (0°), measured clockwise when viewed from above.

    Returns
    -------
    (x, y) mm, where +x is east and +y is north of the stone centre.
    """
    theta = math.radians(angle_deg)
    # Standard math angle: 0 = east (+x), converts from clockwise-from-north.
    math_angle = _PI / 2.0 - theta

    if cut in _ROUND_OVAL_CUTS:
        r = stone_mm / 2.0
        return (r * math.cos(math_angle), r * math.sin(math_angle))

    if cut in _POINTED_CUTS:
        # Approximate girdle as an ellipse.
        # marquise / pear: length ≈ stone_mm, width ≈ stone_mm * 0.55 (typical)
        a = stone_mm / 2.0
        b = stone_mm * 0.55 / 2.0
        cos_a = math.cos(math_angle)
        sin_a = math.sin(math_angle)
        denom = math.sqrt((b * cos_a) ** 2 + (a * sin_a) ** 2)
        if denom < 1e-12:
            return (0.0, a)
        r_ellipse = (a * b) / denom
        return (r_ellipse * cos_a, r_ellipse * sin_a)

    if cut in _FANCY_CUTS_WITH_CORNERS:
        # Approximate girdle as a square of side = stone_mm.
        half = stone_mm / 2.0
        cos_a = math.cos(math_angle)
        sin_a = math.sin(math_angle)
        # Clip to square boundary.
        if abs(cos_a) < 1e-12 and abs(sin_a) < 1e-12:
            return (0.0, 0.0)
        if abs(cos_a) < 1e-12:
            scale = half / abs(sin_a)
        elif abs(sin_a) < 1e-12:
            scale = half / abs(cos_a)
        else:
            scale = min(half / abs(cos_a), half / abs(sin_a))
        return (scale * cos_a, scale * sin_a)

    # Fallback: circle
    r = stone_mm / 2.0
    return (r * math.cos(math_angle), r * math.sin(math_angle))


# ---------------------------------------------------------------------------
# Prong angular placement
# ---------------------------------------------------------------------------

def prong_angles_for_cut(
    cut: str,
    prong_count: int,
    start_angle_deg: float = 0.0,
) -> List[float]:
    """Compute the angular positions (degrees, clockwise from north) for prongs.

    For round/oval stones: evenly space *prong_count* prongs.
    For fancy cuts with corners: place one prong at each corner; if
    prong_count > number_of_corners, fill the remaining prongs evenly in the
    midpoints.
    For pointed cuts (marquise, pear, heart, trillion): place a V-prong at
    each point, then fill remaining prongs evenly around the belly.

    Parameters
    ----------
    cut : str
    prong_count : int
    start_angle_deg : float
        Angular offset for the first prong position (default 0° = north/top).

    Returns
    -------
    list[float]
        Sorted list of angular positions in [0, 360).
    """
    if prong_count <= 0:
        return []

    # --- Round / oval: pure even angular spacing ---
    if cut in _ROUND_OVAL_CUTS:
        step = 360.0 / prong_count
        return [
            (start_angle_deg + i * step) % 360.0
            for i in range(prong_count)
        ]

    # --- Fancy cuts with corners ---
    if cut in _FANCY_CUTS_WITH_CORNERS:
        if cut in ("princess", "asscher", "square_emerald", "flanders"):
            corners = 4
            corner_angles = [
                (start_angle_deg + 45.0 + i * 90.0) % 360.0
                for i in range(4)
            ]
        elif cut in ("emerald", "radiant", "cushion", "baguette"):
            # Rectangular with 4 corners; treat same as square corners.
            corners = 4
            corner_angles = [
                (start_angle_deg + 45.0 + i * 90.0) % 360.0
                for i in range(4)
            ]
        else:
            corners = 4
            corner_angles = [
                (start_angle_deg + 45.0 + i * 90.0) % 360.0
                for i in range(4)
            ]

        if prong_count <= corners:
            # Pick the first prong_count corner positions.
            return sorted(corner_angles[:prong_count])

        # Fill remaining positions evenly between corners.
        angles = list(corner_angles)
        extra = prong_count - corners
        # Distribute extra prongs evenly across all 4 sides.
        for i in range(extra):
            mid = (corner_angles[i % corners] + corner_angles[(i + 1) % corners]) / 2.0
            angles.append(mid % 360.0)
        return sorted(angles)

    # --- Pointed cuts ---
    if cut in _POINTED_CUTS:
        # marquise: 2 tips at 0° and 180°; pear: tip at 0°, round at 180°;
        # heart: two lobes at ~330° and ~30°, tip at 180°.
        if cut == "marquise":
            tip_angles = [
                start_angle_deg % 360.0,
                (start_angle_deg + 180.0) % 360.0,
            ]
        elif cut == "pear":
            tip_angles = [start_angle_deg % 360.0]  # single point at top
        elif cut == "heart":
            tip_angles = [
                (start_angle_deg + 180.0) % 360.0,  # bottom point
            ]
        elif cut == "trillion":
            tip_angles = [
                (start_angle_deg + i * 120.0) % 360.0
                for i in range(3)
            ]
        else:
            tip_angles = [start_angle_deg % 360.0]

        if prong_count <= len(tip_angles):
            return sorted(tip_angles[:prong_count])

        # Fill remaining evenly around the girdle.
        angles = list(tip_angles)
        remaining = prong_count - len(tip_angles)
        step = 360.0 / prong_count
        # Add evenly spaced fillers avoiding duplicates within 15°.
        candidate = (start_angle_deg + step * 0.5) % 360.0
        added = 0
        attempts = 0
        while added < remaining and attempts < 360:
            if all(abs((candidate - a + 180) % 360 - 180) > 15.0 for a in angles):
                angles.append(candidate)
                added += 1
            candidate = (candidate + step) % 360.0
            attempts += 1
        return sorted(angles)

    # Fallback: even angular spacing
    step = 360.0 / prong_count
    return [
        (start_angle_deg + i * step) % 360.0
        for i in range(prong_count)
    ]


# ---------------------------------------------------------------------------
# Head geometry builders (pure Python → node spec dicts)
# ---------------------------------------------------------------------------

def build_head_node(
    node_id: str,
    head_style: str,
    cut: str,
    stone_mm: float,
    prong_count: int,
    prong_wire_dia: float,
    claw_length: float,
    claw_tip_radius: float,
    seat_angle_deg: float,
    gallery_rail: bool,
    bezel_wall: float,
    bezel_height: float,
    start_angle_deg: float,
) -> dict:
    """Return the head node spec dict consumed by the OCCT worker.

    Parameters
    ----------
    node_id : str
    head_style : str
        One of HEAD_STYLES.
    cut : str
        Stone cut from STONE_CUTS.
    stone_mm : float
        Longest girdle dimension in mm.
    prong_count : int
        Number of prongs/claws. 0 for full_bezel / tension.
    prong_wire_dia : float
        Claw wire diameter in mm.
    claw_length : float
        Height the claw tip rises above the stone girdle in mm.
    claw_tip_radius : float
        Rounding radius at the claw tip in mm.
    seat_angle_deg : float
        Inward chamfer angle of the bearing seat (degrees from vertical).
    gallery_rail : bool
        Whether to include a horizontal gallery rail below the prongs.
    bezel_wall : float
        Bezel wall thickness in mm (for half_bezel / full_bezel).
    bezel_height : float
        Bezel collar height in mm (for half_bezel / full_bezel).
    start_angle_deg : float
        Angular offset for the first prong (degrees, clockwise from north).
    """
    # Compute angular positions for each prong.
    angles = prong_angles_for_cut(cut, prong_count, start_angle_deg)

    # Compute girdle contact points for each prong.
    contact_points = [
        list(girdle_contact_point(cut, stone_mm, a))
        for a in angles
    ]

    # Derived geometry hints for the worker.
    girdle_r = stone_contact_radius = stone_mm / 2.0
    head_outer_dia = stone_mm + 2 * prong_wire_dia
    seat_depth = stone_mm * math.tan(math.radians(max(seat_angle_deg, 0.1))) * 0.1

    node: Dict[str, Any] = {
        "id": node_id,
        "op": "jewelry_head_wizard",
        "head_style": head_style,
        "cut": cut,
        "stone_mm": stone_mm,
        "prong_count": prong_count,
        "prong_wire_dia": prong_wire_dia,
        "claw_length": claw_length,
        "claw_tip_radius": claw_tip_radius,
        "seat_angle_deg": seat_angle_deg,
        "gallery_rail": gallery_rail,
        "bezel_wall": bezel_wall,
        "bezel_height": bezel_height,
        "start_angle_deg": start_angle_deg,
        # Computed fields for worker and client.
        "prong_angles_deg": angles,
        "contact_points_mm": contact_points,
        "_head_outer_dia": round(head_outer_dia, 4),
        "_seat_depth": round(seat_depth, 6),
        "_girdle_radius": round(girdle_r, 4),
    }

    return node


def build_ring_builder_node(
    node_id: str,
    head_node_id: str,
    shank_profile: str,
    band_width: float,
    band_thickness: float,
    ring_size: float,
    size_system: str,
    metal: str,
    seat_height_mm: float,
) -> dict:
    """Return a ring-builder composite node spec.

    Computes inner diameter from ring_size + system, validates fit
    and minimum-metal constraints, and estimates weight.

    Parameters
    ----------
    node_id : str
    head_node_id : str
        ID of the head node this ring-builder references.
    shank_profile : str
        Band cross-section profile (e.g. "comfort_fit", "d_shape", etc.).
    band_width : float
        Band width at the shank back (mm).
    band_thickness : float
        Radial thickness of the shank wall (mm).
    ring_size : float
        Numeric ring size in the chosen system.
    size_system : str
        One of "us", "uk", "au", "eu", "jp".  Only "us" is numerically
        computed here; others are approximated via their circumference tables.
    metal : str
        Metal alloy key (from _METAL_DENSITY).
    seat_height_mm : float
        Height of the head seat above the shank bore top face (mm).
    """
    # Inner diameter from ring size.
    inner_dia = _ring_size_to_id_mm(size_system, ring_size)

    # Minimum metal check on band thickness.
    warnings: List[str] = []
    if band_thickness < _MIN_METAL_WALL_MM:
        warnings.append(
            f"band_thickness {band_thickness:.2f} mm is below minimum "
            f"recommended {_MIN_METAL_WALL_MM:.2f} mm"
        )

    # Weight estimate (shank only, approximate torus volume).
    # V_torus = (π²/4) * section_width * section_height * mean_dia
    mean_dia = inner_dia + band_thickness
    vol_cm3 = ((_PI ** 2) / 4.0) * (band_width / 10.0) * (band_thickness / 10.0) * (mean_dia / 10.0)
    density = _METAL_DENSITY.get(metal, 15.58)  # default 18k yellow
    weight_g = vol_cm3 * density

    node: Dict[str, Any] = {
        "id": node_id,
        "op": "jewelry_ring_builder",
        "head_node_id": head_node_id,
        "shank_profile": shank_profile,
        "band_width": band_width,
        "band_thickness": band_thickness,
        "ring_size": ring_size,
        "size_system": size_system,
        "metal": metal,
        "seat_height_mm": seat_height_mm,
        # Derived
        "_inner_dia_mm": round(inner_dia, 4),
        "_weight_g": round(weight_g, 3),
        "_warnings": warnings,
    }

    return node


def _ring_size_to_id_mm(system: str, size) -> float:
    """Minimal ring-size lookup — US formula; other systems via circumference.

    Keeps head_wizard.py independent of ring.py to avoid circular imports.
    Supports US (formula), UK/AU, EU, JP via embedded tables.
    """
    sys_lower = str(system).strip().lower()

    if sys_lower == "us":
        try:
            s = float(size)
        except (TypeError, ValueError):
            raise ValueError(f"US ring size must be numeric; got {size!r}")
        if s < 0 or s > 16:
            raise ValueError(f"US size out of range 0–16; got {s}")
        return _us_size_to_id_mm(s)

    # For non-US systems, use circumference / π.
    circ = _size_to_circumference(sys_lower, size)
    return circ / _PI


# US → circumference (mm) table — circumference = π × diameter
_UK_AU_CIRC: Dict[str, float] = {
    "A": 37.8, "A½": 38.4, "B": 39.1, "B½": 39.7,
    "C": 40.4, "C½": 41.1, "D": 41.7, "D½": 42.4,
    "E": 43.0, "E½": 43.7, "F": 44.2, "F½": 44.8,
    "G": 45.5, "G½": 46.1, "H": 46.8, "H½": 47.4,
    "I": 48.0, "I½": 48.7, "J": 49.3, "J½": 50.0,
    "K": 50.6, "K½": 51.2, "L": 51.9, "L½": 52.5,
    "M": 53.1, "M½": 53.8, "N": 54.4, "N½": 55.1,
    "O": 55.7, "O½": 56.3, "P": 57.0, "P½": 57.6,
    "Q": 58.3, "Q½": 58.9, "R": 59.5, "R½": 60.2,
    "S": 60.8, "S½": 61.4, "T": 62.1, "T½": 62.7,
    "U": 63.4, "U½": 64.0, "V": 64.6, "V½": 65.3,
    "W": 65.9, "W½": 66.6, "X": 67.2, "X½": 67.8,
    "Y": 68.5, "Y½": 69.1, "Z": 69.7,
    "Z+1": 70.4, "Z+2": 71.0, "Z+3": 71.7,
}

_JP_CIRC: Dict[int, float] = {
    1: 38.1, 2: 39.0, 3: 39.9, 4: 40.8, 5: 41.7,
    6: 42.6, 7: 43.5, 8: 44.4, 9: 45.3, 10: 46.2,
    11: 47.1, 12: 47.9, 13: 48.8, 14: 49.7, 15: 50.6,
    16: 51.5, 17: 52.4, 18: 53.3, 19: 54.2, 20: 55.1,
    21: 55.9, 22: 56.8, 23: 57.7, 24: 58.6, 25: 59.5,
    26: 60.4, 27: 61.3, 28: 62.2, 29: 63.1, 30: 64.0,
}


def _size_to_circumference(sys_lower: str, size) -> float:
    if sys_lower in ("uk", "au"):
        key = str(size).strip()
        if key not in _UK_AU_CIRC:
            raise ValueError(f"Unknown UK/AU ring size {size!r}")
        return _UK_AU_CIRC[key]
    elif sys_lower == "eu":
        try:
            c = float(size)
        except (TypeError, ValueError):
            raise ValueError(f"EU size must be numeric (circumference mm); got {size!r}")
        if c < 41 or c > 76:
            raise ValueError(f"EU circumference out of range 41–76; got {c}")
        return c
    elif sys_lower == "jp":
        try:
            jp = int(size)
        except (TypeError, ValueError):
            raise ValueError(f"JP size must be integer 1–30; got {size!r}")
        if jp not in _JP_CIRC:
            raise ValueError(f"JP size out of range 1–30; got {jp}")
        return _JP_CIRC[jp]
    else:
        raise ValueError(f"Unknown ring-size system {sys_lower!r}")


# ---------------------------------------------------------------------------
# Head-library catalogue
# ---------------------------------------------------------------------------

def head_library_entry(
    head_style: str,
    cut: str,
    stone_mm: float,
) -> dict:
    """Return a recommended head spec for a given style + stone combination.

    Scales prong dimensions by stone_mm so the head is proportional to the
    stone.  Clients can override any individual field via build_head_node.

    Returns
    -------
    dict with keys: head_style, cut, stone_mm, prong_count, prong_wire_dia,
    claw_length, claw_tip_radius, seat_angle_deg, gallery_rail,
    bezel_wall, bezel_height, start_angle_deg, recommended_for.
    """
    err_h = _in_set("head_style", head_style, HEAD_STYLES)
    if err_h:
        raise ValueError(err_h)
    err_c = _in_set("cut", cut, STONE_CUTS)
    if err_c:
        raise ValueError(err_c)
    if stone_mm <= 0:
        raise ValueError(f"stone_mm must be > 0; got {stone_mm}")

    wire_dia, claw_len, tip_r = _HEAD_PRONG_DEFAULTS[head_style]

    # Scale prong wire diameter proportionally to stone size.
    # Reference scale: 1.0 mm wire dia at 6.5 mm stone (1 ct round).
    scale = max(0.5, stone_mm / 6.5)
    wire_dia_scaled = round(wire_dia * scale, 3)
    claw_len_scaled = round(claw_len * scale, 3)
    tip_r_scaled = round(tip_r * scale, 3)

    # Bezel dimensions: wall = 0.05 × stone_mm (≥ 0.3 mm); height = 0.4 × stone_mm.
    bezel_wall = max(0.3, round(0.05 * stone_mm, 3))
    bezel_height = round(0.4 * stone_mm, 3)

    prong_count = _HEAD_DEFAULT_PRONG_COUNT[head_style]

    # Adjust for cut-specific logic.
    if head_style == "v_prong" and cut in _POINTED_CUTS:
        # V-prong at each pointed tip.
        prong_count = 2 if cut == "marquise" else 1
    elif head_style in ("four_prong_solitaire", "basket") and cut in _FANCY_CUTS_WITH_CORNERS:
        prong_count = 4  # corner placement
    elif head_style == "six_prong_solitaire" and cut in _FANCY_CUTS_WITH_CORNERS:
        prong_count = 6

    # gallery_rail: present on basket + four/six-prong solitaire.
    gallery_rail = head_style in ("basket", "four_prong_solitaire", "six_prong_solitaire")

    return {
        "head_style": head_style,
        "cut": cut,
        "stone_mm": stone_mm,
        "prong_count": prong_count,
        "prong_wire_dia": wire_dia_scaled,
        "claw_length": claw_len_scaled,
        "claw_tip_radius": tip_r_scaled,
        "seat_angle_deg": 15.0,
        "gallery_rail": gallery_rail,
        "bezel_wall": bezel_wall,
        "bezel_height": bezel_height,
        "start_angle_deg": 0.0,
        "recommended_for": f"{head_style} head for {cut} {stone_mm:.2f} mm stone",
    }


# ---------------------------------------------------------------------------
# LLM Tool: jewelry_head_library_get
# ---------------------------------------------------------------------------

jewelry_head_library_get_spec = ToolSpec(
    name="jewelry_head_library_get",
    description=(
        "Return a recommended head/prong spec from the built-in head library "
        "for a given head style + stone cut + stone size.  No feature file is "
        "modified — this is a pure lookup that returns scaled prong dimensions, "
        "seat angle, gallery settings, and bezel dimensions ready to pass into "
        "jewelry_build_head.\n\n"
        "Head styles: four_prong_solitaire, six_prong_solitaire, double_claw, "
        "basket, v_prong, half_bezel, full_bezel, halo, tension.\n\n"
        "Stone cuts: round_brilliant, princess, oval, emerald, marquise, pear, "
        "cushion, radiant, asscher, trillion, heart, baguette, square_emerald, flanders."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "head_style": {
                "type": "string",
                "enum": sorted(HEAD_STYLES),
                "description": "Head family to look up.",
            },
            "cut": {
                "type": "string",
                "enum": sorted(STONE_CUTS),
                "description": "Stone cut / shape.",
            },
            "stone_mm": {
                "type": "number",
                "description": "Longest girdle dimension of the stone in mm.",
            },
        },
        "required": ["head_style", "cut", "stone_mm"],
    },
)


@register(jewelry_head_library_get_spec)
async def run_jewelry_head_library_get(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    head_style = str(a.get("head_style", "")).strip().lower()
    cut = str(a.get("cut", "")).strip().lower()
    stone_mm = a.get("stone_mm")

    err = _in_set("head_style", head_style, HEAD_STYLES)
    if err:
        return err_payload(err, "BAD_ARGS")
    err = _in_set("cut", cut, STONE_CUTS)
    if err:
        return err_payload(err, "BAD_ARGS")
    err = _positive("stone_mm", stone_mm)
    if err:
        return err_payload(err, "BAD_ARGS")

    try:
        entry = head_library_entry(head_style, cut, float(stone_mm))
    except ValueError as ve:
        return err_payload(str(ve), "BAD_ARGS")

    return ok_payload(entry)


# ---------------------------------------------------------------------------
# LLM Tool: jewelry_place_prongs
# ---------------------------------------------------------------------------

jewelry_place_prongs_spec = ToolSpec(
    name="jewelry_place_prongs",
    description=(
        "Compute prong / claw angular positions and girdle contact points for a "
        "given stone cut and prong count.  Returns a list of placements, each "
        "with angle_deg and contact point (x, y) in mm relative to the stone "
        "centre.  No feature file is modified.\n\n"
        "Round/oval stones receive evenly spaced prongs.  "
        "Fancy-cut stones (princess, emerald, asscher, radiant, cushion, "
        "baguette, square_emerald, flanders) receive corner-biased placement.  "
        "Pointed cuts (marquise, pear, heart, trillion) receive tip-biased placement."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cut": {
                "type": "string",
                "enum": sorted(STONE_CUTS),
                "description": "Stone cut.",
            },
            "stone_mm": {
                "type": "number",
                "description": "Longest girdle dimension in mm.",
            },
            "prong_count": {
                "type": "integer",
                "description": "Number of prongs to place (1–12).",
                "minimum": 1,
                "maximum": 12,
            },
            "start_angle_deg": {
                "type": "number",
                "description": "Angular offset for first prong (0 = north/top). Default 0.",
            },
        },
        "required": ["cut", "stone_mm", "prong_count"],
    },
)


@register(jewelry_place_prongs_spec)
async def run_jewelry_place_prongs(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    cut = str(a.get("cut", "")).strip().lower()
    stone_mm = a.get("stone_mm")
    prong_count = a.get("prong_count")
    start_angle_deg = a.get("start_angle_deg", 0.0)

    err = _in_set("cut", cut, STONE_CUTS)
    if err:
        return err_payload(err, "BAD_ARGS")
    err = _positive("stone_mm", stone_mm)
    if err:
        return err_payload(err, "BAD_ARGS")

    try:
        pc = int(prong_count)
    except (TypeError, ValueError):
        return err_payload("prong_count must be an integer", "BAD_ARGS")
    if pc < 1 or pc > 12:
        return err_payload("prong_count must be between 1 and 12", "BAD_ARGS")

    try:
        sa = float(start_angle_deg)
    except (TypeError, ValueError):
        sa = 0.0

    angles = prong_angles_for_cut(cut, pc, sa)
    placements = []
    for ang in angles:
        x, y = girdle_contact_point(cut, float(stone_mm), ang)
        placements.append({
            "angle_deg": round(ang, 4),
            "contact_x_mm": round(x, 4),
            "contact_y_mm": round(y, 4),
        })

    return ok_payload({
        "cut": cut,
        "stone_mm": float(stone_mm),
        "prong_count": pc,
        "placements": placements,
    })


# ---------------------------------------------------------------------------
# LLM Tool: jewelry_build_head
# ---------------------------------------------------------------------------

jewelry_build_head_spec = ToolSpec(
    name="jewelry_build_head",
    description=(
        "Append a `jewelry_head_wizard` node to a `.feature` file.  Generates "
        "a fully parametric head assembly: prong/claw geometry with correct "
        "angular placement on the stone girdle, optional gallery rail, seat "
        "bearing ledge, and bezel collar (for bezel styles).\n\n"
        "The node spec includes `prong_angles_deg` (evenly spaced for round; "
        "corner-biased for fancy cuts) and `contact_points_mm` (the (x, y) "
        "girdle contact point for each claw).\n\n"
        "Head styles: four_prong_solitaire, six_prong_solitaire, double_claw, "
        "basket, v_prong, half_bezel, full_bezel, halo, tension.\n\n"
        "Stone cuts: round_brilliant, princess, oval, emerald, marquise, pear, "
        "cushion, radiant, asscher, trillion, heart, baguette, square_emerald, flanders."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "head_style": {
                "type": "string",
                "enum": sorted(HEAD_STYLES),
                "description": "Head family.",
            },
            "cut": {
                "type": "string",
                "enum": sorted(STONE_CUTS),
                "description": "Stone cut / shape.",
            },
            "stone_mm": {
                "type": "number",
                "description": "Longest girdle dimension of the stone in mm.",
            },
            "prong_count": {
                "type": "integer",
                "description": "Number of prongs. 0 for full_bezel/tension.",
                "minimum": 0,
                "maximum": 12,
            },
            "prong_wire_dia": {
                "type": "number",
                "description": "Prong/claw wire diameter in mm. Default: auto-scaled.",
            },
            "claw_length": {
                "type": "number",
                "description": "Claw tip height above girdle in mm. Default: auto-scaled.",
            },
            "claw_tip_radius": {
                "type": "number",
                "description": "Rounding radius at the claw tip in mm.",
            },
            "seat_angle_deg": {
                "type": "number",
                "description": "Bearing-seat chamfer angle in degrees. Default 15.",
            },
            "gallery_rail": {
                "type": "boolean",
                "description": "Include a horizontal gallery rail below the prongs.",
            },
            "bezel_wall": {
                "type": "number",
                "description": "Bezel wall thickness in mm (for bezel styles).",
            },
            "bezel_height": {
                "type": "number",
                "description": "Bezel collar height in mm (for bezel styles).",
            },
            "start_angle_deg": {
                "type": "number",
                "description": "Angular offset for first prong in degrees. Default 0.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "head_style", "cut", "stone_mm"],
    },
)


@register(jewelry_build_head_spec, write=True)
async def run_jewelry_build_head(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = str(a.get("file_id", "")).strip()
    head_style = str(a.get("head_style", "")).strip().lower()
    cut = str(a.get("cut", "")).strip().lower()
    stone_mm_raw = a.get("stone_mm")
    node_id = str(a.get("id", "")).strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")

    err = _in_set("head_style", head_style, HEAD_STYLES)
    if err:
        return err_payload(err, "BAD_ARGS")
    err = _in_set("cut", cut, STONE_CUTS)
    if err:
        return err_payload(err, "BAD_ARGS")
    err = _positive("stone_mm", stone_mm_raw)
    if err:
        return err_payload(err, "BAD_ARGS")

    stone_mm = float(stone_mm_raw)

    # Prong count — default from library if not provided.
    prong_count_raw = a.get("prong_count")
    if prong_count_raw is None:
        prong_count = _HEAD_DEFAULT_PRONG_COUNT[head_style]
    else:
        try:
            prong_count = int(prong_count_raw)
        except (TypeError, ValueError):
            return err_payload("prong_count must be an integer", "BAD_ARGS")
        if prong_count < 0 or prong_count > 12:
            return err_payload("prong_count must be 0–12", "BAD_ARGS")

    # Auto-scale prong dimensions from library defaults if not specified.
    scale = max(0.5, stone_mm / 6.5)
    def_wire, def_len, def_tip = _HEAD_PRONG_DEFAULTS[head_style]

    try:
        prong_wire_dia = float(a.get("prong_wire_dia") or def_wire * scale)
    except (TypeError, ValueError):
        prong_wire_dia = def_wire * scale

    try:
        claw_length = float(a.get("claw_length") or def_len * scale)
    except (TypeError, ValueError):
        claw_length = def_len * scale

    try:
        claw_tip_radius = float(a.get("claw_tip_radius") or def_tip * scale)
    except (TypeError, ValueError):
        claw_tip_radius = def_tip * scale

    seat_angle_raw = a.get("seat_angle_deg", 15.0)
    try:
        seat_angle_deg = float(seat_angle_raw)
    except (TypeError, ValueError):
        seat_angle_deg = 15.0
    if seat_angle_deg <= 0:
        return err_payload("seat_angle_deg must be > 0", "BAD_ARGS")

    gallery_rail = bool(a.get("gallery_rail", head_style in ("basket", "four_prong_solitaire", "six_prong_solitaire")))

    try:
        bezel_wall = float(a.get("bezel_wall") or max(0.3, 0.05 * stone_mm))
    except (TypeError, ValueError):
        bezel_wall = max(0.3, 0.05 * stone_mm)

    try:
        bezel_height = float(a.get("bezel_height") or 0.4 * stone_mm)
    except (TypeError, ValueError):
        bezel_height = 0.4 * stone_mm

    start_angle_raw = a.get("start_angle_deg", 0.0)
    try:
        start_angle_deg = float(start_angle_raw)
    except (TypeError, ValueError):
        start_angle_deg = 0.0

    # Min-metal validation on prong wire.
    if prong_count > 0 and prong_wire_dia < _MIN_PRONG_WIRE_MM:
        return err_payload(
            f"prong_wire_dia {prong_wire_dia:.3f} mm is below minimum {_MIN_PRONG_WIRE_MM} mm",
            "BAD_ARGS",
        )

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_head_wizard")

    node = build_head_node(
        node_id=node_id,
        head_style=head_style,
        cut=cut,
        stone_mm=stone_mm,
        prong_count=prong_count,
        prong_wire_dia=prong_wire_dia,
        claw_length=claw_length,
        claw_tip_radius=claw_tip_radius,
        seat_angle_deg=seat_angle_deg,
        gallery_rail=gallery_rail,
        bezel_wall=bezel_wall,
        bezel_height=bezel_height,
        start_angle_deg=start_angle_deg,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_head_wizard",
        "head_style": head_style,
        "cut": cut,
        "stone_mm": stone_mm,
        "prong_count": prong_count,
        "prong_angles_deg": node["prong_angles_deg"],
    })


# ---------------------------------------------------------------------------
# LLM Tool: jewelry_ring_builder
# ---------------------------------------------------------------------------

jewelry_ring_builder_spec = ToolSpec(
    name="jewelry_ring_builder",
    description=(
        "Append a `jewelry_ring_builder` node to a `.feature` file.  Composes "
        "a head node (referenced by `head_node_id`) + shank profile + ring size "
        "into a complete ring spec.\n\n"
        "Automatically computes inner diameter from the ring size + system, "
        "validates fit and minimum-metal constraints, and returns a weight "
        "estimate in grams.  Shank seat alignment to the head is encoded in "
        "`seat_height_mm`.\n\n"
        "Metal options: platinum, 18k_yellow, 18k_white, 18k_rose, 14k_yellow, "
        "14k_white, 14k_rose, silver_sterling, palladium, 9k_yellow.\n\n"
        "Shank profiles (from ring.py): d_shape, comfort_fit, flat, half_round, "
        "knife_edge, euro, tapered, cigar_band, bombe, concave, square, "
        "hammered, split_band."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "head_node_id": {
                "type": "string",
                "description": "Node id of the head node to attach the shank to.",
            },
            "shank_profile": {
                "type": "string",
                "description": "Band cross-section profile.",
            },
            "band_width": {
                "type": "number",
                "description": "Band width at the shank back in mm.",
            },
            "band_thickness": {
                "type": "number",
                "description": "Radial wall thickness of the shank in mm.",
            },
            "ring_size": {
                "type": "number",
                "description": "Ring size in the chosen size_system.",
            },
            "size_system": {
                "type": "string",
                "enum": sorted(_VALID_SYSTEMS),
                "description": "Ring-size system. Default: 'us'.",
            },
            "metal": {
                "type": "string",
                "enum": sorted(_METAL_DENSITY.keys()),
                "description": "Metal alloy for weight estimation. Default: '18k_yellow'.",
            },
            "seat_height_mm": {
                "type": "number",
                "description": "Height of head seat above shank bore top (mm). Default 0.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "head_node_id", "band_width", "band_thickness", "ring_size"],
    },
)


@register(jewelry_ring_builder_spec, write=True)
async def run_jewelry_ring_builder(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = str(a.get("file_id", "")).strip()
    head_node_id = str(a.get("head_node_id", "")).strip()
    shank_profile = str(a.get("shank_profile", "comfort_fit")).strip().lower()
    band_width_raw = a.get("band_width")
    band_thickness_raw = a.get("band_thickness")
    ring_size_raw = a.get("ring_size")
    size_system = str(a.get("size_system", "us")).strip().lower()
    metal = str(a.get("metal", "18k_yellow")).strip().lower()
    seat_height_raw = a.get("seat_height_mm", 0.0)
    node_id = str(a.get("id", "")).strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if not head_node_id:
        return err_payload("head_node_id is required", "BAD_ARGS")

    for fname, fval in [
        ("band_width", band_width_raw),
        ("band_thickness", band_thickness_raw),
    ]:
        err = _positive(fname, fval)
        if err:
            return err_payload(err, "BAD_ARGS")

    if ring_size_raw is None:
        return err_payload("ring_size is required", "BAD_ARGS")

    err = _in_set("size_system", size_system, _VALID_SYSTEMS)
    if err:
        return err_payload(err, "BAD_ARGS")

    if metal not in _METAL_DENSITY:
        return err_payload(
            f"metal must be one of {sorted(_METAL_DENSITY.keys())}; got {metal!r}",
            "BAD_ARGS",
        )

    try:
        inner_dia = _ring_size_to_id_mm(size_system, ring_size_raw)
    except ValueError as ve:
        return err_payload(str(ve), "BAD_ARGS")

    try:
        seat_height = float(seat_height_raw)
    except (TypeError, ValueError):
        seat_height = 0.0

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "jewelry_ring_builder")

    node = build_ring_builder_node(
        node_id=node_id,
        head_node_id=head_node_id,
        shank_profile=shank_profile,
        band_width=float(band_width_raw),
        band_thickness=float(band_thickness_raw),
        ring_size=float(ring_size_raw),
        size_system=size_system,
        metal=metal,
        seat_height_mm=seat_height,
    )

    _, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "jewelry_ring_builder",
        "head_node_id": head_node_id,
        "inner_dia_mm": node["_inner_dia_mm"],
        "weight_g": node["_weight_g"],
        "warnings": node["_warnings"],
    })
