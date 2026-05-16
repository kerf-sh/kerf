"""
kerf_cad_core.jewelry.bangle
=============================

Parametric bangle / cuff / torque (torc) builders.

RhinoGold/MatrixGold parity: implements the "Bangles" wizard family as
pure-Python builders that emit node-spec dicts consumed by the occtWorker.
Distinct from ring.py (sized to finger) and chain.py.

## Bangle types

``closed_bangle``
    A rigid closed hoop sized to wrist inner circumference.  Inner profile
    can be round, oval, cushion (rounded square), or square.  Cross-section
    profile is one of: round_wire, d_shape, square, knife_edge, half_round,
    twisted_wire.  Ergonomic comfort-fit chord is computed.

``open_cuff``
    An open bangle with a configurable gap angle.  Includes alloy spring-back
    allowance so the cuff springs to the target inner diameter after forming.
    Gap narrows by spring-back_deg after release.

``torque``
    A twisted torc: the arm cross-section is swept along the bangle path while
    rotating (``twist_turns`` full turns around the sweep axis).  Finial endcap
    geometry is specified via ``finial_style``.

``hinged_bangle``
    A closed bangle split into two halves joined by a hinge pin, with a box
    clasp or tongue-and-groove clasp.

## Inner-profile sizing

Standard wrist sizes by inner circumference (industry midpoints — caller may
override).  System follows the same convention as ring.py.

    S   → 155 mm  (≈ 49.3 mm inner diameter)
    M   → 165 mm  (≈ 52.5 mm inner diameter)
    L   → 175 mm  (≈ 55.7 mm inner diameter)
    XL  → 185 mm  (≈ 58.9 mm inner diameter)

Values sourced from Pandora / Rio Grande bracelet sizing guides.

## Cross-section areas and second moments

All cross-section properties (area A mm², second moment of area I mm⁴) are
computed analytically.

  round_wire  : A = π r²,    I = π r⁴ / 4
  d_shape     : approximated as half-circle + rectangular tongue strip
  square      : A = s²,      I = s⁴ / 12
  knife_edge  : A ≈ 0.5 · h · w (isosceles triangle approx)
  half_round  : A = π r² / 2,  I = π r⁴ / 8
  twisted_wire: same area as round_wire; pitch and twist angle recorded

## Twisted-wire / torc helix pitch

For a twisted-wire cross-section or torque form, the helix pitch is:

    pitch_mm = wire_diameter_mm × π / tan(twist_angle_deg × π / 180)

consistent with the helix formula used in chain.py rope/wheat hints.

## Metal volume

For a closed bangle (solid torus-like sweep):

    V_mm3 = A_cs_mm2 × path_length_mm

where path_length_mm = inner_circumference_mm + π × width_cs_mm for a
round inner path of diameter = inner_circumference / π.

For oval / cushion / square inner profiles the path length is the perimeter
of that inner shape plus an offset for the cross-section centre-line.

## LLM tools registered

    jewelry_bangle_size          — read-only: wrist-size → inner circumference
    jewelry_create_closed_bangle — write: closed bangle node
    jewelry_create_open_cuff     — write: open cuff node
    jewelry_create_torque        — write: torque/torc node
    jewelry_create_hinged_bangle — write: hinged bangle node
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_cad_core.surfacing import (
    read_feature_content,
    append_feature_node,
    next_node_id,
)
from kerf_cad_core.jewelry.metal_cost import (
    METAL_DENSITY_G_CM3,
    metal_weight,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PI = math.pi

# ---------------------------------------------------------------------------
# Wrist-size table  (inner circumference in mm)
# ---------------------------------------------------------------------------
# Sources: Pandora bracelet sizing chart; Rio Grande "Sizing & Proportion Guide"
# (2024); Stuller bracelet size reference.  Values are industry midpoints for
# adult wrists.  Caller may pass an explicit inner_circumference_mm instead.

WRIST_SIZE_TABLE: dict[str, float] = {
    "XS": 145.0,   # very petite adult  — Pandora 15 cm
    "S":  155.0,   # small adult        — Pandora 16 cm
    "M":  165.0,   # medium adult       — Pandora 17 cm (most common)
    "L":  175.0,   # large adult        — Pandora 18 cm
    "XL": 185.0,   # extra large        — Pandora 19 cm
    "XXL": 195.0,  # extra extra large  — Pandora 20 cm
}

# Human-readable labels
WRIST_SIZE_LABELS: dict[str, str] = {
    "XS":  "XS  (145 mm / ~15.0 cm inner circumference)",
    "S":   "S   (155 mm / ~15.5 cm inner circumference)",
    "M":   "M   (165 mm / ~16.5 cm inner circumference)",
    "L":   "L   (175 mm / ~17.5 cm inner circumference)",
    "XL":  "XL  (185 mm / ~18.5 cm inner circumference)",
    "XXL": "XXL (195 mm / ~19.5 cm inner circumference)",
}

# ---------------------------------------------------------------------------
# Valid enumerations
# ---------------------------------------------------------------------------

# Inner-profile shapes (the cross-section of the bangle bore / the overall
# shape of the hoop when viewed from above, i.e. the "plan silhouette").
_VALID_INNER_PROFILES = frozenset([
    "round",     # circular bore / hoop
    "oval",      # slightly elliptical; defined by major_mm and minor_mm ratio
    "cushion",   # rounded-square / pillow shape
    "square",    # square interior corners
])

# Cross-section profiles (what the wire / band looks like in cut-section).
_VALID_CROSS_SECTIONS = frozenset([
    "round_wire",    # circular wire swept to form the bangle
    "d_shape",       # flat outside, domed inside — classic band
    "square",        # square section with sharp corners
    "knife_edge",    # V-ridge on the outer face — architectural
    "half_round",    # domed outside, flat inside
    "twisted_wire",  # two or more strands twisted together
])

# Finial endcap styles for torque/torc
_VALID_FINIALS = frozenset([
    "ball",          # classic spherical endcap
    "cone",          # tapered cone
    "flat_disc",     # flat round disc cap
    "spiral",        # open spiral / volute curl
    "animal_head",   # sculptural — geometry hint only
    "none",          # no separate endcap; arm ends bluntly
])

# Clasp styles for hinged bangle
_VALID_CLASP_STYLES = frozenset([
    "box_clasp",          # square push-in tongue
    "tongue_groove",      # elongated tongue in groove channel
    "hidden_box",         # recessed box clasp flush with band surface
    "figure_eight_safety", # safety figure-eight over box tongue
])

# Spring-back allowances per alloy group (degrees per 360° of bending arc).
# When an open cuff is formed around a mandrel to a target inner_circumference,
# the metal springs back after mandrel removal.  The spring-back_deg is the
# angle by which the gap opens (negative spring-back) after forming.
# Sources: Metal Techniques for Craftsmen (Oppi Untracht, 1968);
# Metals Handbook Vol 14A (ASM International, 2005).
SPRING_BACK_DEG: dict[str, float] = {
    # Gold alloys: lower work-hardening, moderate spring-back
    "10k_yellow": 3.5,
    "14k_yellow": 4.0,
    "18k_yellow": 4.5,
    "22k_yellow": 2.5,
    "24k_yellow": 1.5,
    "10k_white":  4.0,
    "14k_white":  4.5,
    "18k_white":  5.0,
    "22k_white":  3.5,
    "10k_rose":   4.5,
    "14k_rose":   5.0,
    "18k_rose":   5.5,
    "22k_rose":   3.0,
    # Platinum: high work-hardening; considerable spring-back
    "platinum_950": 6.5,
    "platinum_900": 6.0,
    # Palladium
    "palladium_950": 6.0,
    "palladium_500": 5.0,
    # Silver
    "sterling_925":  5.0,
    "fine_silver":   3.0,
    "argentium_935": 4.5,
    # Base metals
    "titanium": 8.0,
    "brass":    4.0,
    "bronze":   4.5,
}

# Default spring-back for unknown alloys
_DEFAULT_SPRING_BACK_DEG = 4.5


# ---------------------------------------------------------------------------
# Inner-profile geometry helpers
# ---------------------------------------------------------------------------

def wrist_size_to_inner_circumference(size: str) -> float:
    """Return inner circumference in mm for a named wrist size.

    Parameters
    ----------
    size : str
        One of XS, S, M, L, XL, XXL (case-insensitive).

    Returns
    -------
    float   Inner circumference in mm.

    Raises
    ------
    ValueError  For unknown size keys.
    """
    key = size.strip().upper()
    if key not in WRIST_SIZE_TABLE:
        raise ValueError(
            f"Unknown wrist size {size!r}. Valid: {sorted(WRIST_SIZE_TABLE)}"
        )
    return WRIST_SIZE_TABLE[key]


def inner_circumference_to_diameter(inner_circumference_mm: float) -> float:
    """Return inner diameter in mm from inner circumference."""
    if inner_circumference_mm <= 0:
        raise ValueError(
            f"inner_circumference_mm must be positive, got {inner_circumference_mm}"
        )
    return inner_circumference_mm / _PI


def oval_area(major_mm: float, minor_mm: float) -> float:
    """Return the area of an ellipse with semi-axes major_mm/2 and minor_mm/2.

    Parameters
    ----------
    major_mm : float   Full major-axis length (outer diameter long axis).
    minor_mm : float   Full minor-axis length (outer diameter short axis).

    Returns
    -------
    float   Area in mm².
    """
    if major_mm <= 0:
        raise ValueError(f"major_mm must be positive, got {major_mm}")
    if minor_mm <= 0:
        raise ValueError(f"minor_mm must be positive, got {minor_mm}")
    a = major_mm / 2.0
    b = minor_mm / 2.0
    return _PI * a * b


def oval_perimeter(major_mm: float, minor_mm: float) -> float:
    """Approximate perimeter of an ellipse using Ramanujan's second formula.

    Accuracy: better than 0.02% for all aspect ratios.

    Parameters
    ----------
    major_mm : float   Full major-axis length.
    minor_mm : float   Full minor-axis length.

    Returns
    -------
    float   Approximate perimeter in mm.
    """
    if major_mm <= 0:
        raise ValueError(f"major_mm must be positive, got {major_mm}")
    if minor_mm <= 0:
        raise ValueError(f"minor_mm must be positive, got {minor_mm}")
    a = major_mm / 2.0
    b = minor_mm / 2.0
    h = ((a - b) / (a + b)) ** 2
    # Ramanujan second approximation: P ≈ π(a+b)[1 + 3h/(10+√(4-3h))]
    return _PI * (a + b) * (1.0 + 3.0 * h / (10.0 + math.sqrt(4.0 - 3.0 * h)))


def cushion_perimeter(side_mm: float, corner_radius_mm: float) -> float:
    """Perimeter of a rounded-square (cushion) shape.

    A cushion profile is a square with side_mm and rounded corners of radius
    corner_radius_mm.  The perimeter is:

        P = 4 × (side_mm - 2 × corner_radius_mm) + 2π × corner_radius_mm

    Parameters
    ----------
    side_mm         : float   Full side length of the enclosing square.
    corner_radius_mm: float   Radius of the corner rounding (≤ side_mm / 2).

    Returns
    -------
    float   Perimeter in mm.

    Raises
    ------
    ValueError  If corner_radius_mm > side_mm / 2.
    """
    if side_mm <= 0:
        raise ValueError(f"side_mm must be positive, got {side_mm}")
    if corner_radius_mm < 0:
        raise ValueError(f"corner_radius_mm must be >= 0, got {corner_radius_mm}")
    if corner_radius_mm > side_mm / 2.0:
        raise ValueError(
            f"corner_radius_mm ({corner_radius_mm}) must be <= side_mm/2 ({side_mm/2})"
        )
    straight = 4.0 * (side_mm - 2.0 * corner_radius_mm)
    arcs = 2.0 * _PI * corner_radius_mm  # four quarter-circles = one full circle
    return straight + arcs


# ---------------------------------------------------------------------------
# Cross-section property helpers
# ---------------------------------------------------------------------------

def cross_section_properties(
    cross_section: str,
    width_mm: float,
    height_mm: Optional[float] = None,
) -> dict:
    """Compute area (A) and second moment of area (I_xx) for a cross-section.

    Parameters
    ----------
    cross_section : str
        One of the _VALID_CROSS_SECTIONS values.
    width_mm : float
        Width of the cross-section in mm (diameter for round_wire / half_round,
        side for square, base for knife_edge, width for d_shape / twisted_wire).
    height_mm : float, optional
        Height of the cross-section in mm (only used for d_shape and knife_edge).
        Defaults to width_mm if not supplied.

    Returns
    -------
    dict with keys:
        cross_section  — input key
        width_mm       — input width
        height_mm      — effective height used
        area_mm2       — cross-sectional area in mm²
        I_xx_mm4       — second moment of area about the centroidal x-axis in mm⁴
        description    — short description string
    """
    if width_mm <= 0:
        raise ValueError(f"width_mm must be positive, got {width_mm}")
    cs = cross_section.strip().lower()
    if cs not in _VALID_CROSS_SECTIONS:
        raise ValueError(
            f"Unknown cross_section {cross_section!r}. "
            f"Valid: {sorted(_VALID_CROSS_SECTIONS)}"
        )
    h = float(height_mm) if height_mm is not None else float(width_mm)
    if h <= 0:
        raise ValueError(f"height_mm must be positive, got {h}")

    if cs == "round_wire":
        # Solid circular section: A = π r², I = π r⁴ / 4
        r = width_mm / 2.0
        area = _PI * r ** 2
        I_xx = _PI * r ** 4 / 4.0
        desc = f"Solid circular wire ⌀{width_mm} mm"

    elif cs == "half_round":
        # Semi-circular section: A = π r² / 2,  I_xx = π r⁴ / 8
        r = width_mm / 2.0
        area = _PI * r ** 2 / 2.0
        I_xx = _PI * r ** 4 / 8.0
        desc = f"Half-round ⌀{width_mm} mm"

    elif cs == "square":
        # Square section: A = s², I_xx = s⁴ / 12
        s = width_mm
        area = s ** 2
        I_xx = s ** 4 / 12.0
        desc = f"Square section {width_mm}×{width_mm} mm"

    elif cs == "d_shape":
        # Approximate D-shape as a rectangular body + semicircular dome.
        # Total height h; flat side (bottom) width = width_mm.
        # Body rect height ≈ 0.5h; dome radius ≈ width_mm/2.
        rect_h = h * 0.5
        dome_r = width_mm / 2.0
        # Rectangle area + semicircle area
        area_rect = width_mm * rect_h
        area_semi = _PI * dome_r ** 2 / 2.0
        area = area_rect + area_semi
        # I_xx of rectangle about its centroid + parallel axis theorem contribution;
        # I_xx of semicircle about centroid (π r⁴/8 - (4r/3π)² × πr²/2)
        I_rect = width_mm * rect_h ** 3 / 12.0
        I_semi_centroid = _PI * dome_r ** 4 / 8.0 - (4.0 * dome_r / (3.0 * _PI)) ** 2 * area_semi
        # Shift to common centroid — simplified: treat as combined body
        y_centroid_rect = rect_h / 2.0
        y_centroid_semi = rect_h + 4.0 * dome_r / (3.0 * _PI)
        y_bar = (area_rect * y_centroid_rect + area_semi * y_centroid_semi) / area
        d_rect = y_centroid_rect - y_bar
        d_semi = y_centroid_semi - y_bar
        I_xx = (
            I_rect + area_rect * d_rect ** 2
            + I_semi_centroid + area_semi * d_semi ** 2
        )
        desc = f"D-shape {width_mm}×{h} mm"

    elif cs == "knife_edge":
        # Isosceles triangle approximation (V-ridge): base = width_mm, height = h
        area = 0.5 * width_mm * h
        # I_xx of triangle about centroid = b h³ / 36
        I_xx = width_mm * h ** 3 / 36.0
        desc = f"Knife-edge {width_mm}×{h} mm"

    elif cs == "twisted_wire":
        # Treat as circular wire (same cross-section area); twist is a geometry
        # hint in the node spec, not a change to the cross-section area/I.
        r = width_mm / 2.0
        area = _PI * r ** 2
        I_xx = _PI * r ** 4 / 4.0
        desc = f"Twisted wire ⌀{width_mm} mm"

    else:
        raise ValueError(f"Unhandled cross_section: {cross_section!r}")

    return {
        "cross_section": cs,
        "width_mm": width_mm,
        "height_mm": h,
        "area_mm2": round(area, 6),
        "I_xx_mm4": round(I_xx, 8),
        "description": desc,
    }


# ---------------------------------------------------------------------------
# Twisted-wire pitch
# ---------------------------------------------------------------------------

def twisted_wire_pitch(wire_diameter_mm: float, twist_angle_deg: float) -> float:
    """Compute the axial pitch of a twisted-wire cross-section.

    For a helically twisted wire the axial advance per full revolution is:

        pitch_mm = π × wire_diameter_mm / tan(twist_angle_deg)

    where twist_angle_deg is the helix angle (angle between the wire axis
    and the transverse plane), consistent with the helix formulas in chain.py.

    Parameters
    ----------
    wire_diameter_mm : float   Diameter of the individual wire strand.
    twist_angle_deg  : float   Helix angle in degrees (> 0 and < 90).

    Returns
    -------
    float   Axial pitch in mm.
    """
    if wire_diameter_mm <= 0:
        raise ValueError(f"wire_diameter_mm must be positive, got {wire_diameter_mm}")
    if twist_angle_deg <= 0 or twist_angle_deg >= 90.0:
        raise ValueError(
            f"twist_angle_deg must be in (0, 90), got {twist_angle_deg}"
        )
    tan_a = math.tan(math.radians(twist_angle_deg))
    return _PI * wire_diameter_mm / tan_a


# ---------------------------------------------------------------------------
# Bangle path-length helpers
# ---------------------------------------------------------------------------

def _inner_path_length(
    inner_profile: str,
    inner_circumference_mm: float,
    oval_minor_ratio: float = 0.8,
    cushion_corner_ratio: float = 0.15,
    cs_width_mm: float = 0.0,
) -> float:
    """Compute the centre-line path length of the bangle sweep.

    The sweep path runs at the centroid of the cross-section, which is
    approximately at the inner surface plus half the cross-section width.

    Parameters
    ----------
    inner_profile : str
        One of _VALID_INNER_PROFILES.
    inner_circumference_mm : float
        Inner circumference in mm (the circumference at the bore surface).
    oval_minor_ratio : float
        Ratio of minor to major axis for oval profile. Default 0.8.
    cushion_corner_ratio : float
        Corner radius as fraction of cushion side length. Default 0.15.
    cs_width_mm : float
        Cross-section half-width to offset from inner surface to centroid.
        Default 0 (path = inner perimeter).

    Returns
    -------
    float   Centre-line path length in mm.
    """
    inner_d = inner_circumference_mm / _PI
    # Offset centroid = inner surface + cs_width/2
    offset = cs_width_mm / 2.0

    if inner_profile == "round":
        return _PI * (inner_d + 2.0 * offset)

    elif inner_profile == "oval":
        # Major axis = inner_d + 2*offset  (along long axis)
        # Minor axis = (inner_d * oval_minor_ratio) + 2*offset
        major = inner_d + 2.0 * offset
        minor = inner_d * oval_minor_ratio + 2.0 * offset
        return oval_perimeter(major, minor)

    elif inner_profile == "cushion":
        # side = inner_d + 2*offset; corner_r = side * corner_ratio
        side = inner_d + 2.0 * offset
        corner_r = side * cushion_corner_ratio
        return cushion_perimeter(side, corner_r)

    elif inner_profile == "square":
        side = inner_d + 2.0 * offset
        return 4.0 * side

    else:
        raise ValueError(
            f"Unknown inner_profile {inner_profile!r}. "
            f"Valid: {sorted(_VALID_INNER_PROFILES)}"
        )


def bangle_volume_mm3(
    inner_profile: str,
    inner_circumference_mm: float,
    cross_section: str,
    cs_width_mm: float,
    cs_height_mm: Optional[float] = None,
    oval_minor_ratio: float = 0.8,
    cushion_corner_ratio: float = 0.15,
) -> float:
    """Compute the approximate solid volume of a closed bangle in mm³.

    Uses the thin-shell approximation: V ≈ A_cs × path_length.

    Parameters
    ----------
    inner_profile : str
    inner_circumference_mm : float
    cross_section : str
    cs_width_mm : float
        Width of cross-section in mm.
    cs_height_mm : float, optional
    oval_minor_ratio : float
    cushion_corner_ratio : float

    Returns
    -------
    float   Volume in mm³.
    """
    cs_props = cross_section_properties(cross_section, cs_width_mm, cs_height_mm)
    area_mm2 = cs_props["area_mm2"]
    path_mm = _inner_path_length(
        inner_profile,
        inner_circumference_mm,
        oval_minor_ratio=oval_minor_ratio,
        cushion_corner_ratio=cushion_corner_ratio,
        cs_width_mm=cs_width_mm,
    )
    return area_mm2 * path_mm


# ---------------------------------------------------------------------------
# Comfort-fit chord
# ---------------------------------------------------------------------------

def comfort_fit_chord(inner_circumference_mm: float) -> dict:
    """Compute the comfort-fit chord measurement for a bangle.

    The comfort-fit chord is the widest straight-line measurement across the
    inner opening.  For a round bangle this equals the inner diameter.  It
    determines whether the bangle can slip over the widest part of the hand.

    Industry rule-of-thumb: for a round bangle, the comfort chord equals the
    inner diameter.  The bangle is wearable if the chord ≤ the diagonal
    measure of the hand (knuckle breadth + thumb width).

    Parameters
    ----------
    inner_circumference_mm : float
        Inner circumference of the bangle in mm.

    Returns
    -------
    dict with keys:
        inner_circumference_mm  — input circumference
        inner_diameter_mm       — circumference / π
        comfort_chord_mm        — equals inner_diameter_mm for round bangles
        knuckle_clearance_note  — advisory note string
    """
    if inner_circumference_mm <= 0:
        raise ValueError(
            f"inner_circumference_mm must be positive, got {inner_circumference_mm}"
        )
    inner_d = inner_circumference_mm / _PI
    return {
        "inner_circumference_mm": round(inner_circumference_mm, 3),
        "inner_diameter_mm": round(inner_d, 3),
        "comfort_chord_mm": round(inner_d, 3),
        "knuckle_clearance_note": (
            f"Inner diameter {inner_d:.1f} mm — verify against knuckle "
            f"breadth (typical 60–75 mm for adult hand; bangle must pass over "
            f"knuckles to reach wrist)."
        ),
    }


# ---------------------------------------------------------------------------
# Stone-setting stations
# ---------------------------------------------------------------------------

def stone_station_positions(
    n_stations: int,
    inner_circumference_mm: float,
    cs_width_mm: float,
    arc_deg_start: float = 0.0,
    arc_deg_end: float = 360.0,
) -> list[dict]:
    """Compute N equally-spaced stone-setting station positions along the bangle.

    Each station is described by an angular position (degrees, 0 = 12-o'clock
    clockwise from above) and a radius (centreline radius of the bangle path).

    Parameters
    ----------
    n_stations : int
        Number of stone-setting stations.  Must be >= 1.
    inner_circumference_mm : float
        Inner circumference of the bangle.
    cs_width_mm : float
        Cross-section width (used to place station at outer face, not centre).
    arc_deg_start : float
        Start of the setting arc in degrees. Default 0 (12-o'clock).
    arc_deg_end : float
        End of the setting arc in degrees. Default 360 (full circle).

    Returns
    -------
    list of dicts, each with:
        station_index  — 0-based index
        angle_deg      — position in degrees (0 = 12-o'clock)
        radius_mm      — distance from bangle centre to station centre
        arc_spacing_deg — angular spacing between adjacent stations
    """
    if n_stations < 1:
        raise ValueError(f"n_stations must be >= 1, got {n_stations}")
    if inner_circumference_mm <= 0:
        raise ValueError(
            f"inner_circumference_mm must be positive, got {inner_circumference_mm}"
        )
    if arc_deg_end <= arc_deg_start:
        raise ValueError(
            f"arc_deg_end ({arc_deg_end}) must be > arc_deg_start ({arc_deg_start})"
        )

    inner_r = inner_circumference_mm / (2.0 * _PI)
    station_r = inner_r + cs_width_mm / 2.0

    total_arc = arc_deg_end - arc_deg_start
    if n_stations == 1:
        spacing = 0.0
        angles = [arc_deg_start + total_arc / 2.0]
    else:
        spacing = total_arc / n_stations
        angles = [arc_deg_start + spacing * i + spacing / 2.0 for i in range(n_stations)]

    return [
        {
            "station_index": i,
            "angle_deg": round(angles[i], 4),
            "radius_mm": round(station_r, 4),
            "arc_spacing_deg": round(spacing, 4),
        }
        for i in range(n_stations)
    ]


# ---------------------------------------------------------------------------
# Spring-back helpers
# ---------------------------------------------------------------------------

def cuff_forming_circumference(
    target_inner_circumference_mm: float,
    metal: str,
    gap_angle_deg: float,
) -> dict:
    """Compute the mandrel circumference to form an open cuff.

    When a cuff is formed around a mandrel and then released, the metal
    springs back elastically.  The mandrel must be slightly smaller than
    the target to compensate.

    For a cuff with gap_angle_deg, the active metal arc is
    (360 - gap_angle_deg) degrees.  The spring-back reduces the gap angle
    (i.e. the gap slightly narrows after forming because the metal tries to
    return to a smaller radius).

    Parameters
    ----------
    target_inner_circumference_mm : float
        Desired inner circumference after spring-back.
    metal : str
        Alloy key from METAL_DENSITY_G_CM3 / SPRING_BACK_DEG.
    gap_angle_deg : float
        Target gap opening angle in degrees (0 < gap_angle_deg < 360).

    Returns
    -------
    dict with keys:
        target_inner_circumference_mm — input
        target_inner_diameter_mm      — target inner diameter
        metal                         — input alloy key
        spring_back_deg               — spring-back angle used
        gap_angle_deg                 — target gap angle
        gap_angle_after_forming_deg   — gap after release (slightly narrower than mandrel gap)
        mandrel_circumference_mm      — mandrel inner circumference to use
        mandrel_diameter_mm           — mandrel diameter
        active_arc_deg                — degrees of metal actually bent
    """
    if target_inner_circumference_mm <= 0:
        raise ValueError(
            f"target_inner_circumference_mm must be positive, "
            f"got {target_inner_circumference_mm}"
        )
    if gap_angle_deg <= 0 or gap_angle_deg >= 360.0:
        raise ValueError(
            f"gap_angle_deg must be in (0, 360), got {gap_angle_deg}"
        )

    sb = SPRING_BACK_DEG.get(metal, _DEFAULT_SPRING_BACK_DEG)
    target_d = target_inner_circumference_mm / _PI
    active_arc = 360.0 - gap_angle_deg

    # The mandrel must compensate for spring-back: the metal springs open
    # after forming, so we under-bend slightly.  For a cuff the effective
    # spring-back on the radius is proportional to spring_back_deg / active_arc.
    spring_back_fraction = sb / active_arc  # fraction of radius compensation
    mandrel_d = target_d * (1.0 - spring_back_fraction)
    mandrel_circ = _PI * mandrel_d

    # Gap after forming: the gap narrows by spring_back_deg because the
    # cuff tries to close back up after removal from mandrel.
    gap_after = gap_angle_deg - sb

    return {
        "target_inner_circumference_mm": round(target_inner_circumference_mm, 3),
        "target_inner_diameter_mm": round(target_d, 3),
        "metal": metal,
        "spring_back_deg": round(sb, 2),
        "gap_angle_deg": round(gap_angle_deg, 2),
        "gap_angle_after_forming_deg": round(max(gap_after, 0.0), 2),
        "mandrel_circumference_mm": round(mandrel_circ, 3),
        "mandrel_diameter_mm": round(mandrel_d, 3),
        "active_arc_deg": round(active_arc, 2),
    }


# ---------------------------------------------------------------------------
# Core bangle spec builders
# ---------------------------------------------------------------------------

def compute_closed_bangle_params(
    inner_circumference_mm: float,
    cross_section: str = "round_wire",
    cs_width_mm: float = 4.0,
    cs_height_mm: Optional[float] = None,
    inner_profile: str = "round",
    oval_minor_ratio: float = 0.8,
    cushion_corner_ratio: float = 0.15,
    metal: Optional[str] = None,
    n_stone_stations: int = 0,
    stone_arc_deg_start: float = 0.0,
    stone_arc_deg_end: float = 360.0,
) -> dict:
    """Compute geometric parameters for a closed bangle.

    Parameters
    ----------
    inner_circumference_mm : float
        Inner circumference at the bore surface in mm.
    cross_section : str
        Cross-section profile. One of _VALID_CROSS_SECTIONS.
    cs_width_mm : float
        Cross-section width (wire diameter, or band width) in mm.
    cs_height_mm : float, optional
        Cross-section height — only needed for non-symmetric profiles.
    inner_profile : str
        Plan silhouette shape: round, oval, cushion, square.
    oval_minor_ratio : float
        Minor/major axis ratio for oval profile. Default 0.8.
    cushion_corner_ratio : float
        Corner radius fraction for cushion. Default 0.15.
    metal : str, optional
        Alloy key (used for mass calculation).
    n_stone_stations : int
        Number of stone-setting stations along the top. Default 0.
    stone_arc_deg_start : float
        Start of setting arc. Default 0.
    stone_arc_deg_end : float
        End of setting arc. Default 360.

    Returns
    -------
    dict
    """
    if inner_circumference_mm <= 0:
        raise ValueError(
            f"inner_circumference_mm must be positive, got {inner_circumference_mm}"
        )
    if cs_width_mm <= 0:
        raise ValueError(f"cs_width_mm must be positive, got {cs_width_mm}")
    inner_profile = inner_profile.strip().lower()
    if inner_profile not in _VALID_INNER_PROFILES:
        raise ValueError(
            f"Unknown inner_profile {inner_profile!r}. "
            f"Valid: {sorted(_VALID_INNER_PROFILES)}"
        )
    cs = cross_section.strip().lower()
    if cs not in _VALID_CROSS_SECTIONS:
        raise ValueError(
            f"Unknown cross_section {cross_section!r}. "
            f"Valid: {sorted(_VALID_CROSS_SECTIONS)}"
        )

    inner_d = inner_circumference_mm / _PI
    cs_props = cross_section_properties(cs, cs_width_mm, cs_height_mm)
    path_len = _inner_path_length(
        inner_profile, inner_circumference_mm,
        oval_minor_ratio=oval_minor_ratio,
        cushion_corner_ratio=cushion_corner_ratio,
        cs_width_mm=cs_width_mm,
    )
    vol_mm3 = cs_props["area_mm2"] * path_len
    chord = comfort_fit_chord(inner_circumference_mm)

    # Metal mass
    mass_g: Optional[float] = None
    if metal is not None:
        try:
            w = metal_weight(vol_mm3, metal=metal)
            mass_g = round(w["grams"], 4)
        except Exception:
            pass

    # Stone stations
    stations: list[dict] = []
    if n_stone_stations > 0:
        stations = stone_station_positions(
            n_stone_stations, inner_circumference_mm, cs_width_mm,
            arc_deg_start=stone_arc_deg_start, arc_deg_end=stone_arc_deg_end,
        )

    return {
        "type": "closed_bangle",
        "inner_profile": inner_profile,
        "inner_circumference_mm": round(inner_circumference_mm, 3),
        "inner_diameter_mm": round(inner_d, 3),
        "cross_section": cs_props["cross_section"],
        "cs_width_mm": cs_props["width_mm"],
        "cs_height_mm": cs_props["height_mm"],
        "area_mm2": cs_props["area_mm2"],
        "I_xx_mm4": cs_props["I_xx_mm4"],
        "path_length_mm": round(path_len, 3),
        "volume_mm3": round(vol_mm3, 3),
        "mass_g": mass_g,
        "metal": metal,
        "comfort_chord_mm": chord["comfort_chord_mm"],
        "oval_minor_ratio": oval_minor_ratio if inner_profile == "oval" else None,
        "cushion_corner_ratio": cushion_corner_ratio if inner_profile == "cushion" else None,
        "stone_stations": stations,
    }


def compute_open_cuff_params(
    inner_circumference_mm: float,
    gap_angle_deg: float = 30.0,
    cross_section: str = "round_wire",
    cs_width_mm: float = 4.0,
    cs_height_mm: Optional[float] = None,
    metal: Optional[str] = None,
    n_stone_stations: int = 0,
    stone_arc_deg_start: float = 30.0,
    stone_arc_deg_end: float = 330.0,
) -> dict:
    """Compute geometric parameters for an open cuff bangle.

    Parameters
    ----------
    inner_circumference_mm : float
    gap_angle_deg : float
        Opening angle of the gap in degrees. Default 30°.
    cross_section : str
    cs_width_mm : float
    cs_height_mm : float, optional
    metal : str, optional
    n_stone_stations : int
    stone_arc_deg_start : float
    stone_arc_deg_end : float

    Returns
    -------
    dict
    """
    if inner_circumference_mm <= 0:
        raise ValueError(
            f"inner_circumference_mm must be positive, got {inner_circumference_mm}"
        )
    if gap_angle_deg <= 0 or gap_angle_deg >= 360.0:
        raise ValueError(
            f"gap_angle_deg must be in (0, 360), got {gap_angle_deg}"
        )
    if cs_width_mm <= 0:
        raise ValueError(f"cs_width_mm must be positive, got {cs_width_mm}")
    cs = cross_section.strip().lower()
    if cs not in _VALID_CROSS_SECTIONS:
        raise ValueError(
            f"Unknown cross_section {cross_section!r}. "
            f"Valid: {sorted(_VALID_CROSS_SECTIONS)}"
        )

    inner_d = inner_circumference_mm / _PI
    active_arc_frac = (360.0 - gap_angle_deg) / 360.0

    cs_props = cross_section_properties(cs, cs_width_mm, cs_height_mm)
    # Path length = active arc only (closed full circle path × fraction)
    full_path = _inner_path_length("round", inner_circumference_mm, cs_width_mm=cs_width_mm)
    path_len = full_path * active_arc_frac
    vol_mm3 = cs_props["area_mm2"] * path_len

    # Spring-back
    spring_data: Optional[dict] = None
    if metal is not None:
        spring_data = cuff_forming_circumference(
            inner_circumference_mm, metal, gap_angle_deg
        )

    mass_g: Optional[float] = None
    if metal is not None:
        try:
            w = metal_weight(vol_mm3, metal=metal)
            mass_g = round(w["grams"], 4)
        except Exception:
            pass

    # Stone stations (only within the active arc)
    stations: list[dict] = []
    if n_stone_stations > 0:
        stations = stone_station_positions(
            n_stone_stations, inner_circumference_mm, cs_width_mm,
            arc_deg_start=stone_arc_deg_start, arc_deg_end=stone_arc_deg_end,
        )

    result = {
        "type": "open_cuff",
        "inner_circumference_mm": round(inner_circumference_mm, 3),
        "inner_diameter_mm": round(inner_d, 3),
        "gap_angle_deg": round(gap_angle_deg, 2),
        "active_arc_deg": round((360.0 - gap_angle_deg), 2),
        "cross_section": cs_props["cross_section"],
        "cs_width_mm": cs_props["width_mm"],
        "cs_height_mm": cs_props["height_mm"],
        "area_mm2": cs_props["area_mm2"],
        "I_xx_mm4": cs_props["I_xx_mm4"],
        "path_length_mm": round(path_len, 3),
        "volume_mm3": round(vol_mm3, 3),
        "mass_g": mass_g,
        "metal": metal,
        "spring_back": spring_data,
        "stone_stations": stations,
    }
    return result


def compute_torque_params(
    inner_circumference_mm: float,
    cross_section: str = "round_wire",
    cs_width_mm: float = 5.0,
    cs_height_mm: Optional[float] = None,
    twist_turns: float = 2.0,
    finial_style: str = "ball",
    finial_diameter_mm: Optional[float] = None,
    metal: Optional[str] = None,
) -> dict:
    """Compute geometric parameters for a torque / torc bangle.

    The torque is an open-ended torc: the arm cross-section sweeps along
    roughly 330° of arc while rotating twist_turns full turns about the
    sweep axis, producing a twisted-spiral appearance.  The finials at the
    ends are separate geometry hints.

    Twisted helix pitch consistency:
        For the sweep arm, the helical pitch per mm of arc length is:
            turns_per_mm = twist_turns / path_length_mm
        or equivalently the twist angle (helix angle) relative to the
        sweep tangent is arctan(twist_turns × 2π × arm_radius / path_length_mm).

    Parameters
    ----------
    inner_circumference_mm : float
    cross_section : str
    cs_width_mm : float
    cs_height_mm : float, optional
    twist_turns : float
        Number of full twists along the arm. Default 2.
    finial_style : str
        One of _VALID_FINIALS.
    finial_diameter_mm : float, optional
        Diameter of the finial endcap. Default = cs_width_mm × 1.5.
    metal : str, optional

    Returns
    -------
    dict
    """
    if inner_circumference_mm <= 0:
        raise ValueError(
            f"inner_circumference_mm must be positive, got {inner_circumference_mm}"
        )
    if twist_turns < 0:
        raise ValueError(f"twist_turns must be >= 0, got {twist_turns}")
    cs = cross_section.strip().lower()
    if cs not in _VALID_CROSS_SECTIONS:
        raise ValueError(
            f"Unknown cross_section {cross_section!r}. "
            f"Valid: {sorted(_VALID_CROSS_SECTIONS)}"
        )
    finial = finial_style.strip().lower()
    if finial not in _VALID_FINIALS:
        raise ValueError(
            f"Unknown finial_style {finial_style!r}. "
            f"Valid: {sorted(_VALID_FINIALS)}"
        )
    if cs_width_mm <= 0:
        raise ValueError(f"cs_width_mm must be positive, got {cs_width_mm}")

    # Torque: open gap of ~30° (classic torc opening)
    gap_angle_deg = 30.0
    active_arc_frac = (360.0 - gap_angle_deg) / 360.0
    full_path = _inner_path_length("round", inner_circumference_mm, cs_width_mm=cs_width_mm)
    path_len = full_path * active_arc_frac

    cs_props = cross_section_properties(cs, cs_width_mm, cs_height_mm)
    vol_arm_mm3 = cs_props["area_mm2"] * path_len

    # Finial volume (spherical if ball, conical otherwise — simplified)
    fin_d = finial_diameter_mm if finial_diameter_mm is not None else cs_width_mm * 1.5
    if fin_d <= 0:
        raise ValueError(f"finial_diameter_mm must be positive, got {fin_d}")
    if finial == "ball":
        r_fin = fin_d / 2.0
        vol_finial = (4.0 / 3.0) * _PI * r_fin ** 3
    elif finial == "cone":
        r_fin = fin_d / 2.0
        h_fin = fin_d
        vol_finial = _PI * r_fin ** 2 * h_fin / 3.0
    elif finial == "flat_disc":
        r_fin = fin_d / 2.0
        thick = cs_width_mm * 0.3
        vol_finial = _PI * r_fin ** 2 * thick
    else:
        # For other finial styles, estimate as sphere
        r_fin = fin_d / 2.0
        vol_finial = (4.0 / 3.0) * _PI * r_fin ** 3

    total_vol_mm3 = vol_arm_mm3 + 2.0 * vol_finial  # two finials

    # Twist consistency: helix angle at arm centroid
    arm_r = inner_circumference_mm / (2.0 * _PI) + cs_width_mm / 2.0
    if path_len > 0 and twist_turns > 0:
        # tan(helix_angle) = twist_turns × 2π × arm_r / path_len
        helix_angle_deg = math.degrees(
            math.atan(twist_turns * 2.0 * _PI * arm_r / path_len)
        )
    else:
        helix_angle_deg = 0.0

    mass_g: Optional[float] = None
    if metal is not None:
        try:
            w = metal_weight(total_vol_mm3, metal=metal)
            mass_g = round(w["grams"], 4)
        except Exception:
            pass

    return {
        "type": "torque",
        "inner_circumference_mm": round(inner_circumference_mm, 3),
        "inner_diameter_mm": round(inner_circumference_mm / _PI, 3),
        "gap_angle_deg": gap_angle_deg,
        "active_arc_deg": round(360.0 - gap_angle_deg, 2),
        "cross_section": cs_props["cross_section"],
        "cs_width_mm": cs_props["width_mm"],
        "cs_height_mm": cs_props["height_mm"],
        "area_mm2": cs_props["area_mm2"],
        "I_xx_mm4": cs_props["I_xx_mm4"],
        "path_length_mm": round(path_len, 3),
        "twist_turns": twist_turns,
        "helix_angle_deg": round(helix_angle_deg, 4),
        "finial_style": finial,
        "finial_diameter_mm": round(fin_d, 3),
        "volume_arm_mm3": round(vol_arm_mm3, 3),
        "volume_finials_mm3": round(2.0 * vol_finial, 3),
        "volume_total_mm3": round(total_vol_mm3, 3),
        "mass_g": mass_g,
        "metal": metal,
    }


def compute_hinged_bangle_params(
    inner_circumference_mm: float,
    cross_section: str = "d_shape",
    cs_width_mm: float = 6.0,
    cs_height_mm: Optional[float] = None,
    clasp_style: str = "box_clasp",
    hinge_pin_diameter_mm: float = 1.5,
    inner_profile: str = "round",
    metal: Optional[str] = None,
    n_stone_stations: int = 0,
) -> dict:
    """Compute geometric parameters for a hinged bangle.

    A hinged bangle is split into two half-shells joined by a hinge pin on
    one side, with a clasp mechanism on the other.

    Parameters
    ----------
    inner_circumference_mm : float
    cross_section : str
    cs_width_mm : float
    cs_height_mm : float, optional
    clasp_style : str
        One of _VALID_CLASP_STYLES.
    hinge_pin_diameter_mm : float
        Diameter of the hinge pin. Default 1.5 mm.
    inner_profile : str
    metal : str, optional
    n_stone_stations : int

    Returns
    -------
    dict
    """
    if inner_circumference_mm <= 0:
        raise ValueError(
            f"inner_circumference_mm must be positive, got {inner_circumference_mm}"
        )
    if cs_width_mm <= 0:
        raise ValueError(f"cs_width_mm must be positive, got {cs_width_mm}")
    if hinge_pin_diameter_mm <= 0:
        raise ValueError(
            f"hinge_pin_diameter_mm must be positive, got {hinge_pin_diameter_mm}"
        )
    cs = cross_section.strip().lower()
    if cs not in _VALID_CROSS_SECTIONS:
        raise ValueError(
            f"Unknown cross_section {cross_section!r}. "
            f"Valid: {sorted(_VALID_CROSS_SECTIONS)}"
        )
    clasp = clasp_style.strip().lower()
    if clasp not in _VALID_CLASP_STYLES:
        raise ValueError(
            f"Unknown clasp_style {clasp_style!r}. "
            f"Valid: {sorted(_VALID_CLASP_STYLES)}"
        )
    inner_profile = inner_profile.strip().lower()
    if inner_profile not in _VALID_INNER_PROFILES:
        raise ValueError(
            f"Unknown inner_profile {inner_profile!r}. "
            f"Valid: {sorted(_VALID_INNER_PROFILES)}"
        )

    cs_props = cross_section_properties(cs, cs_width_mm, cs_height_mm)
    path_len = _inner_path_length(inner_profile, inner_circumference_mm, cs_width_mm=cs_width_mm)
    vol_mm3 = cs_props["area_mm2"] * path_len

    # Hinge knuckle geometry
    knuckle_count = 3  # standard 3-knuckle hinge (2 on one half, 1 on other)
    knuckle_height = cs_props["width_mm"] * 0.6
    knuckle_outer_d = hinge_pin_diameter_mm * 2.2
    knuckle_vol_each = _PI * (knuckle_outer_d / 2.0) ** 2 * knuckle_height
    hinge_vol = knuckle_count * knuckle_vol_each

    total_vol_mm3 = vol_mm3 + hinge_vol
    chord = comfort_fit_chord(inner_circumference_mm)

    stations: list[dict] = []
    if n_stone_stations > 0:
        stations = stone_station_positions(
            n_stone_stations, inner_circumference_mm, cs_width_mm,
            arc_deg_start=0.0, arc_deg_end=180.0,  # top half only for hinged
        )

    mass_g: Optional[float] = None
    if metal is not None:
        try:
            w = metal_weight(total_vol_mm3, metal=metal)
            mass_g = round(w["grams"], 4)
        except Exception:
            pass

    return {
        "type": "hinged_bangle",
        "inner_profile": inner_profile,
        "inner_circumference_mm": round(inner_circumference_mm, 3),
        "inner_diameter_mm": round(inner_circumference_mm / _PI, 3),
        "cross_section": cs_props["cross_section"],
        "cs_width_mm": cs_props["width_mm"],
        "cs_height_mm": cs_props["height_mm"],
        "area_mm2": cs_props["area_mm2"],
        "I_xx_mm4": cs_props["I_xx_mm4"],
        "path_length_mm": round(path_len, 3),
        "volume_mm3": round(vol_mm3, 3),
        "volume_total_mm3": round(total_vol_mm3, 3),
        "mass_g": mass_g,
        "metal": metal,
        "clasp_style": clasp,
        "hinge_pin_diameter_mm": hinge_pin_diameter_mm,
        "knuckle_count": knuckle_count,
        "hinge_volume_mm3": round(hinge_vol, 3),
        "comfort_chord_mm": chord["comfort_chord_mm"],
        "stone_stations": stations,
    }


# ---------------------------------------------------------------------------
# Build node-spec (for feature file / occtWorker)
# ---------------------------------------------------------------------------

def build_bangle_node(
    file_id: str,
    bangle_type: str,
    params: dict,
    node_id: Optional[str] = None,
) -> dict:
    """Wrap computed bangle params into a feature-file node spec.

    Parameters
    ----------
    file_id : str   UUID of the feature file.
    bangle_type : str   One of: closed_bangle, open_cuff, torque, hinged_bangle.
    params : dict   Output of compute_*_params.
    node_id : str, optional   UUID for the node. Auto-generated if not provided.

    Returns
    -------
    dict  Node spec suitable for append_feature_node.
    """
    nid = node_id or str(uuid.uuid4())
    return {
        "id": nid,
        "op": f"bangle_{bangle_type}",
        "file_id": file_id,
        **params,
    }


# ---------------------------------------------------------------------------
# LLM tool: jewelry_bangle_size  (read-only)
# ---------------------------------------------------------------------------

_bangle_size_spec = ToolSpec(
    name="jewelry_bangle_size",
    description=(
        "Read-only: convert a wrist size (XS/S/M/L/XL/XXL) to inner circumference "
        "and diameter in mm, or look up the wrist-size table.\n\n"
        "Wrist sizes and inner circumferences:\n"
        "  XS  — 145 mm (very petite adult)\n"
        "  S   — 155 mm (small adult)\n"
        "  M   — 165 mm (medium adult — most common)\n"
        "  L   — 175 mm (large adult)\n"
        "  XL  — 185 mm (extra large)\n"
        "  XXL — 195 mm (extra extra large)\n\n"
        "You may also pass an explicit inner_circumference_mm to get diameter + comfort chord.\n"
        "Use jewelry_create_closed_bangle / jewelry_create_open_cuff to build the 3D feature."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "wrist_size": {
                "type": "string",
                "enum": sorted(WRIST_SIZE_TABLE),
                "description": "Named wrist size: XS, S, M, L, XL, or XXL.",
            },
            "inner_circumference_mm": {
                "type": "number",
                "description": (
                    "Explicit inner circumference in mm. "
                    "Mutually exclusive with wrist_size."
                ),
            },
        },
    },
)


@register(_bangle_size_spec, write=False)
async def run_jewelry_bangle_size(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    wrist_size = a.get("wrist_size")
    inner_circ = a.get("inner_circumference_mm")

    if wrist_size is not None:
        ws = str(wrist_size).strip().upper()
        if ws not in WRIST_SIZE_TABLE:
            return err_payload(
                f"Unknown wrist_size {wrist_size!r}. Valid: {sorted(WRIST_SIZE_TABLE)}",
                "BAD_ARGS",
            )
        circ = WRIST_SIZE_TABLE[ws]
    elif inner_circ is not None:
        try:
            circ = float(inner_circ)
        except (TypeError, ValueError):
            return err_payload("inner_circumference_mm must be a number", "BAD_ARGS")
        if circ <= 0:
            return err_payload("inner_circumference_mm must be > 0", "BAD_ARGS")
        ws = None
    else:
        return err_payload(
            "Provide wrist_size (XS/S/M/L/XL/XXL) or inner_circumference_mm",
            "BAD_ARGS",
        )

    chord = comfort_fit_chord(circ)
    return ok_payload({
        "wrist_size": ws,
        "inner_circumference_mm": chord["inner_circumference_mm"],
        "inner_diameter_mm": chord["inner_diameter_mm"],
        "comfort_chord_mm": chord["comfort_chord_mm"],
        "knuckle_clearance_note": chord["knuckle_clearance_note"],
        "all_sizes": WRIST_SIZE_TABLE,
    })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_closed_bangle  (write)
# ---------------------------------------------------------------------------

_closed_bangle_spec = ToolSpec(
    name="jewelry_create_closed_bangle",
    description=(
        "Create a parametric closed bangle (rigid hoop) feature node.\n\n"
        "The bangle is sized by inner circumference (wrist size or explicit mm).\n"
        "Choose the inner profile (round/oval/cushion/square), cross-section shape,\n"
        "and optionally specify N stone-setting station positions.\n\n"
        "Cross-section profiles:\n"
        "  round_wire  — circular wire swept into a hoop\n"
        "  d_shape     — flat outside, domed inside (classic band)\n"
        "  square      — square section with sharp corners\n"
        "  knife_edge  — V-ridge on the outer face\n"
        "  half_round  — domed outside, flat inside\n"
        "  twisted_wire — helically twisted wire strand(s)\n\n"
        "Returns mass (g), volume (mm³), cross-section properties (A, I), "
        "comfort-fit chord, and optional stone-station positions."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the feature file to append to.",
            },
            "wrist_size": {
                "type": "string",
                "enum": sorted(WRIST_SIZE_TABLE),
                "description": (
                    "Named wrist size. Mutually exclusive with inner_circumference_mm."
                ),
            },
            "inner_circumference_mm": {
                "type": "number",
                "description": (
                    "Inner circumference in mm. Mutually exclusive with wrist_size."
                ),
            },
            "inner_profile": {
                "type": "string",
                "enum": sorted(_VALID_INNER_PROFILES),
                "description": (
                    "Plan silhouette of the hoop: round (default), oval, cushion, square."
                ),
            },
            "cross_section": {
                "type": "string",
                "enum": sorted(_VALID_CROSS_SECTIONS),
                "description": "Cross-section profile. Default round_wire.",
            },
            "cs_width_mm": {
                "type": "number",
                "description": (
                    "Cross-section width (wire diameter or band width) in mm. Default 4.0."
                ),
            },
            "cs_height_mm": {
                "type": "number",
                "description": (
                    "Cross-section height mm. Only needed for asymmetric profiles "
                    "(d_shape, knife_edge). Defaults to cs_width_mm."
                ),
            },
            "oval_minor_ratio": {
                "type": "number",
                "description": (
                    "Oval profile minor/major axis ratio (0 < v < 1). Default 0.8."
                ),
            },
            "cushion_corner_ratio": {
                "type": "number",
                "description": (
                    "Cushion corner radius as fraction of side length. Default 0.15."
                ),
            },
            "metal": {
                "type": "string",
                "description": (
                    "Alloy key (e.g. '18k_yellow', 'sterling_925') for mass calculation. "
                    "See jewelry_metal_cost for valid keys."
                ),
            },
            "n_stone_stations": {
                "type": "integer",
                "description": "Number of stone-setting stations. Default 0 (none).",
            },
            "stone_arc_deg_start": {
                "type": "number",
                "description": "Start angle for stone stations (degrees). Default 0.",
            },
            "stone_arc_deg_end": {
                "type": "number",
                "description": "End angle for stone stations (degrees). Default 360.",
            },
            "node_id": {
                "type": "string",
                "description": "Optional UUID for the feature node.",
            },
        },
        "required": ["file_id"],
    },
)


@register(_closed_bangle_spec, write=True)
async def run_jewelry_create_closed_bangle(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    # Resolve inner circumference
    wrist_size = a.get("wrist_size")
    inner_circ = a.get("inner_circumference_mm")
    if wrist_size is not None:
        ws = str(wrist_size).strip().upper()
        if ws not in WRIST_SIZE_TABLE:
            return err_payload(
                f"Unknown wrist_size {wrist_size!r}. Valid: {sorted(WRIST_SIZE_TABLE)}",
                "BAD_ARGS",
            )
        inner_circ_mm = WRIST_SIZE_TABLE[ws]
    elif inner_circ is not None:
        try:
            inner_circ_mm = float(inner_circ)
        except (TypeError, ValueError):
            return err_payload("inner_circumference_mm must be a number", "BAD_ARGS")
        if inner_circ_mm <= 0:
            return err_payload("inner_circumference_mm must be > 0", "BAD_ARGS")
    else:
        return err_payload(
            "Provide wrist_size or inner_circumference_mm", "BAD_ARGS"
        )

    cross_section = str(a.get("cross_section", "round_wire")).strip().lower()
    cs_width_mm_raw = a.get("cs_width_mm", 4.0)
    try:
        cs_width_mm = float(cs_width_mm_raw)
    except (TypeError, ValueError):
        return err_payload("cs_width_mm must be a number", "BAD_ARGS")
    if cs_width_mm <= 0:
        return err_payload("cs_width_mm must be > 0", "BAD_ARGS")

    cs_height_mm = None
    if "cs_height_mm" in a and a["cs_height_mm"] is not None:
        try:
            cs_height_mm = float(a["cs_height_mm"])
        except (TypeError, ValueError):
            return err_payload("cs_height_mm must be a number", "BAD_ARGS")
        if cs_height_mm <= 0:
            return err_payload("cs_height_mm must be > 0", "BAD_ARGS")

    inner_profile = str(a.get("inner_profile", "round")).strip().lower()
    oval_minor_ratio = float(a.get("oval_minor_ratio", 0.8))
    cushion_corner_ratio = float(a.get("cushion_corner_ratio", 0.15))
    metal = a.get("metal")
    if metal is not None:
        metal = str(metal).strip().lower()
    n_stations = int(a.get("n_stone_stations", 0))
    arc_start = float(a.get("stone_arc_deg_start", 0.0))
    arc_end = float(a.get("stone_arc_deg_end", 360.0))

    try:
        file_uuid = uuid.UUID(str(file_id))
    except ValueError:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    try:
        params = compute_closed_bangle_params(
            inner_circumference_mm=inner_circ_mm,
            cross_section=cross_section,
            cs_width_mm=cs_width_mm,
            cs_height_mm=cs_height_mm,
            inner_profile=inner_profile,
            oval_minor_ratio=oval_minor_ratio,
            cushion_corner_ratio=cushion_corner_ratio,
            metal=metal,
            n_stone_stations=n_stations,
            stone_arc_deg_start=arc_start,
            stone_arc_deg_end=arc_end,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    node_id = a.get("node_id") or str(uuid.uuid4())
    node = build_bangle_node(str(file_uuid), "closed_bangle", params, node_id=node_id)

    content_str, err = await read_feature_content(ctx, str(file_uuid))
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    new_content, err2 = append_feature_node(content_str, node)
    if err2:
        return err_payload(err2, "ERROR")

    from kerf_cad_core.surfacing import write_feature_content
    err3 = await write_feature_content(ctx, str(file_uuid), new_content)
    if err3:
        return err_payload(err3, "ERROR")

    return ok_payload({
        "node_id": node_id,
        "file_id": str(file_uuid),
        "bangle": params,
    })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_open_cuff  (write)
# ---------------------------------------------------------------------------

_open_cuff_spec = ToolSpec(
    name="jewelry_create_open_cuff",
    description=(
        "Create a parametric open cuff bangle feature node.\n\n"
        "An open cuff has a gap opening on one side so it can be slipped onto "
        "the wrist.  The gap_angle_deg controls the opening width.\n\n"
        "Alloy spring-back compensation is included: the mandrel forming diameter "
        "is computed so the cuff springs to the target inner diameter after release.\n\n"
        "Returns gap geometry, spring-back allowance, volume, mass, and cross-section "
        "properties."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the feature file to append to.",
            },
            "wrist_size": {
                "type": "string",
                "enum": sorted(WRIST_SIZE_TABLE),
                "description": "Named wrist size. Mutually exclusive with inner_circumference_mm.",
            },
            "inner_circumference_mm": {
                "type": "number",
                "description": "Inner circumference mm. Mutually exclusive with wrist_size.",
            },
            "gap_angle_deg": {
                "type": "number",
                "description": "Gap opening angle in degrees (default 30).",
            },
            "cross_section": {
                "type": "string",
                "enum": sorted(_VALID_CROSS_SECTIONS),
                "description": "Cross-section profile. Default round_wire.",
            },
            "cs_width_mm": {
                "type": "number",
                "description": "Cross-section width in mm. Default 4.0.",
            },
            "cs_height_mm": {
                "type": "number",
                "description": "Cross-section height mm (asymmetric profiles).",
            },
            "metal": {
                "type": "string",
                "description": "Alloy key for mass + spring-back calculation.",
            },
            "n_stone_stations": {
                "type": "integer",
                "description": "Number of stone-setting stations. Default 0.",
            },
            "stone_arc_deg_start": {
                "type": "number",
                "description": "Setting arc start angle. Default 30.",
            },
            "stone_arc_deg_end": {
                "type": "number",
                "description": "Setting arc end angle. Default 330.",
            },
            "node_id": {
                "type": "string",
                "description": "Optional UUID for the feature node.",
            },
        },
        "required": ["file_id"],
    },
)


@register(_open_cuff_spec, write=True)
async def run_jewelry_create_open_cuff(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    wrist_size = a.get("wrist_size")
    inner_circ = a.get("inner_circumference_mm")
    if wrist_size is not None:
        ws = str(wrist_size).strip().upper()
        if ws not in WRIST_SIZE_TABLE:
            return err_payload(
                f"Unknown wrist_size {wrist_size!r}.", "BAD_ARGS"
            )
        inner_circ_mm = WRIST_SIZE_TABLE[ws]
    elif inner_circ is not None:
        try:
            inner_circ_mm = float(inner_circ)
        except (TypeError, ValueError):
            return err_payload("inner_circumference_mm must be a number", "BAD_ARGS")
        if inner_circ_mm <= 0:
            return err_payload("inner_circumference_mm must be > 0", "BAD_ARGS")
    else:
        return err_payload("Provide wrist_size or inner_circumference_mm", "BAD_ARGS")

    gap_angle = float(a.get("gap_angle_deg", 30.0))
    cross_section = str(a.get("cross_section", "round_wire")).strip().lower()
    cs_width_mm_raw = a.get("cs_width_mm", 4.0)
    try:
        cs_width_mm = float(cs_width_mm_raw)
    except (TypeError, ValueError):
        return err_payload("cs_width_mm must be a number", "BAD_ARGS")
    if cs_width_mm <= 0:
        return err_payload("cs_width_mm must be > 0", "BAD_ARGS")

    cs_height_mm = None
    if "cs_height_mm" in a and a["cs_height_mm"] is not None:
        try:
            cs_height_mm = float(a["cs_height_mm"])
        except (TypeError, ValueError):
            return err_payload("cs_height_mm must be a number", "BAD_ARGS")

    metal = a.get("metal")
    if metal is not None:
        metal = str(metal).strip().lower()
    n_stations = int(a.get("n_stone_stations", 0))
    arc_start = float(a.get("stone_arc_deg_start", 30.0))
    arc_end = float(a.get("stone_arc_deg_end", 330.0))

    try:
        file_uuid = uuid.UUID(str(file_id))
    except ValueError:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    try:
        params = compute_open_cuff_params(
            inner_circumference_mm=inner_circ_mm,
            gap_angle_deg=gap_angle,
            cross_section=cross_section,
            cs_width_mm=cs_width_mm,
            cs_height_mm=cs_height_mm,
            metal=metal,
            n_stone_stations=n_stations,
            stone_arc_deg_start=arc_start,
            stone_arc_deg_end=arc_end,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    node_id = a.get("node_id") or str(uuid.uuid4())
    node = build_bangle_node(str(file_uuid), "open_cuff", params, node_id=node_id)

    content_str, err = await read_feature_content(ctx, str(file_uuid))
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    new_content, err2 = append_feature_node(content_str, node)
    if err2:
        return err_payload(err2, "ERROR")

    from kerf_cad_core.surfacing import write_feature_content
    err3 = await write_feature_content(ctx, str(file_uuid), new_content)
    if err3:
        return err_payload(err3, "ERROR")

    return ok_payload({
        "node_id": node_id,
        "file_id": str(file_uuid),
        "cuff": params,
    })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_torque  (write)
# ---------------------------------------------------------------------------

_torque_spec = ToolSpec(
    name="jewelry_create_torque",
    description=(
        "Create a parametric torque (torc) bangle feature node.\n\n"
        "A torque is an open-ended twisted-arm bangle with finial endcaps.  "
        "The arm cross-section is swept along ~330° of arc while rotating "
        "twist_turns full turns around the sweep axis.\n\n"
        "Finial styles: ball, cone, flat_disc, spiral, animal_head, none.\n\n"
        "Returns helix angle, volume, mass, cross-section properties, and "
        "finial geometry hints."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the feature file.",
            },
            "wrist_size": {
                "type": "string",
                "enum": sorted(WRIST_SIZE_TABLE),
                "description": "Named wrist size. Mutually exclusive with inner_circumference_mm.",
            },
            "inner_circumference_mm": {
                "type": "number",
                "description": "Inner circumference mm.",
            },
            "cross_section": {
                "type": "string",
                "enum": sorted(_VALID_CROSS_SECTIONS),
                "description": "Cross-section profile. Default round_wire.",
            },
            "cs_width_mm": {
                "type": "number",
                "description": "Cross-section width mm. Default 5.0.",
            },
            "cs_height_mm": {
                "type": "number",
                "description": "Cross-section height mm.",
            },
            "twist_turns": {
                "type": "number",
                "description": "Number of full twists along the arm. Default 2.0.",
            },
            "finial_style": {
                "type": "string",
                "enum": sorted(_VALID_FINIALS),
                "description": "Finial endcap style. Default ball.",
            },
            "finial_diameter_mm": {
                "type": "number",
                "description": "Finial diameter mm. Default cs_width_mm × 1.5.",
            },
            "metal": {
                "type": "string",
                "description": "Alloy key for mass calculation.",
            },
            "node_id": {
                "type": "string",
                "description": "Optional UUID for the feature node.",
            },
        },
        "required": ["file_id"],
    },
)


@register(_torque_spec, write=True)
async def run_jewelry_create_torque(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    wrist_size = a.get("wrist_size")
    inner_circ = a.get("inner_circumference_mm")
    if wrist_size is not None:
        ws = str(wrist_size).strip().upper()
        if ws not in WRIST_SIZE_TABLE:
            return err_payload(f"Unknown wrist_size {wrist_size!r}.", "BAD_ARGS")
        inner_circ_mm = WRIST_SIZE_TABLE[ws]
    elif inner_circ is not None:
        try:
            inner_circ_mm = float(inner_circ)
        except (TypeError, ValueError):
            return err_payload("inner_circumference_mm must be a number", "BAD_ARGS")
        if inner_circ_mm <= 0:
            return err_payload("inner_circumference_mm must be > 0", "BAD_ARGS")
    else:
        return err_payload("Provide wrist_size or inner_circumference_mm", "BAD_ARGS")

    cross_section = str(a.get("cross_section", "round_wire")).strip().lower()
    cs_width_mm_raw = a.get("cs_width_mm", 5.0)
    try:
        cs_width_mm = float(cs_width_mm_raw)
    except (TypeError, ValueError):
        return err_payload("cs_width_mm must be a number", "BAD_ARGS")
    if cs_width_mm <= 0:
        return err_payload("cs_width_mm must be > 0", "BAD_ARGS")

    cs_height_mm = None
    if "cs_height_mm" in a and a["cs_height_mm"] is not None:
        try:
            cs_height_mm = float(a["cs_height_mm"])
        except (TypeError, ValueError):
            return err_payload("cs_height_mm must be a number", "BAD_ARGS")

    twist_turns = float(a.get("twist_turns", 2.0))
    finial_style = str(a.get("finial_style", "ball")).strip().lower()
    finial_d = a.get("finial_diameter_mm")
    if finial_d is not None:
        try:
            finial_d = float(finial_d)
        except (TypeError, ValueError):
            return err_payload("finial_diameter_mm must be a number", "BAD_ARGS")

    metal = a.get("metal")
    if metal is not None:
        metal = str(metal).strip().lower()

    try:
        file_uuid = uuid.UUID(str(file_id))
    except ValueError:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    try:
        params = compute_torque_params(
            inner_circumference_mm=inner_circ_mm,
            cross_section=cross_section,
            cs_width_mm=cs_width_mm,
            cs_height_mm=cs_height_mm,
            twist_turns=twist_turns,
            finial_style=finial_style,
            finial_diameter_mm=finial_d,
            metal=metal,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    node_id = a.get("node_id") or str(uuid.uuid4())
    node = build_bangle_node(str(file_uuid), "torque", params, node_id=node_id)

    content_str, err = await read_feature_content(ctx, str(file_uuid))
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    new_content, err2 = append_feature_node(content_str, node)
    if err2:
        return err_payload(err2, "ERROR")

    from kerf_cad_core.surfacing import write_feature_content
    err3 = await write_feature_content(ctx, str(file_uuid), new_content)
    if err3:
        return err_payload(err3, "ERROR")

    return ok_payload({
        "node_id": node_id,
        "file_id": str(file_uuid),
        "torque": params,
    })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_hinged_bangle  (write)
# ---------------------------------------------------------------------------

_hinged_bangle_spec = ToolSpec(
    name="jewelry_create_hinged_bangle",
    description=(
        "Create a parametric hinged bangle feature node.\n\n"
        "A hinged bangle is split into two half-shells joined by a hinge pin.  "
        "The clasp style controls the locking mechanism on the opposite side.\n\n"
        "Clasp styles: box_clasp, tongue_groove, hidden_box, figure_eight_safety.\n\n"
        "Returns hinge geometry, clasp spec, volume, mass, comfort chord, and "
        "optional stone-station positions."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the feature file.",
            },
            "wrist_size": {
                "type": "string",
                "enum": sorted(WRIST_SIZE_TABLE),
                "description": "Named wrist size. Mutually exclusive with inner_circumference_mm.",
            },
            "inner_circumference_mm": {
                "type": "number",
                "description": "Inner circumference mm.",
            },
            "inner_profile": {
                "type": "string",
                "enum": sorted(_VALID_INNER_PROFILES),
                "description": "Hoop plan shape. Default round.",
            },
            "cross_section": {
                "type": "string",
                "enum": sorted(_VALID_CROSS_SECTIONS),
                "description": "Cross-section profile. Default d_shape.",
            },
            "cs_width_mm": {
                "type": "number",
                "description": "Cross-section width mm. Default 6.0.",
            },
            "cs_height_mm": {
                "type": "number",
                "description": "Cross-section height mm.",
            },
            "clasp_style": {
                "type": "string",
                "enum": sorted(_VALID_CLASP_STYLES),
                "description": "Clasp/locking mechanism. Default box_clasp.",
            },
            "hinge_pin_diameter_mm": {
                "type": "number",
                "description": "Hinge pin diameter mm. Default 1.5.",
            },
            "metal": {
                "type": "string",
                "description": "Alloy key for mass calculation.",
            },
            "n_stone_stations": {
                "type": "integer",
                "description": "Number of stone-setting stations (top half). Default 0.",
            },
            "node_id": {
                "type": "string",
                "description": "Optional UUID for the feature node.",
            },
        },
        "required": ["file_id"],
    },
)


@register(_hinged_bangle_spec, write=True)
async def run_jewelry_create_hinged_bangle(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id")
    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")

    wrist_size = a.get("wrist_size")
    inner_circ = a.get("inner_circumference_mm")
    if wrist_size is not None:
        ws = str(wrist_size).strip().upper()
        if ws not in WRIST_SIZE_TABLE:
            return err_payload(f"Unknown wrist_size {wrist_size!r}.", "BAD_ARGS")
        inner_circ_mm = WRIST_SIZE_TABLE[ws]
    elif inner_circ is not None:
        try:
            inner_circ_mm = float(inner_circ)
        except (TypeError, ValueError):
            return err_payload("inner_circumference_mm must be a number", "BAD_ARGS")
        if inner_circ_mm <= 0:
            return err_payload("inner_circumference_mm must be > 0", "BAD_ARGS")
    else:
        return err_payload("Provide wrist_size or inner_circumference_mm", "BAD_ARGS")

    inner_profile = str(a.get("inner_profile", "round")).strip().lower()
    cross_section = str(a.get("cross_section", "d_shape")).strip().lower()
    cs_width_mm_raw = a.get("cs_width_mm", 6.0)
    try:
        cs_width_mm = float(cs_width_mm_raw)
    except (TypeError, ValueError):
        return err_payload("cs_width_mm must be a number", "BAD_ARGS")
    if cs_width_mm <= 0:
        return err_payload("cs_width_mm must be > 0", "BAD_ARGS")

    cs_height_mm = None
    if "cs_height_mm" in a and a["cs_height_mm"] is not None:
        try:
            cs_height_mm = float(a["cs_height_mm"])
        except (TypeError, ValueError):
            return err_payload("cs_height_mm must be a number", "BAD_ARGS")

    clasp_style = str(a.get("clasp_style", "box_clasp")).strip().lower()
    hinge_pin_d = float(a.get("hinge_pin_diameter_mm", 1.5))
    metal = a.get("metal")
    if metal is not None:
        metal = str(metal).strip().lower()
    n_stations = int(a.get("n_stone_stations", 0))

    try:
        file_uuid = uuid.UUID(str(file_id))
    except ValueError:
        return err_payload("file_id must be a valid UUID", "BAD_ARGS")

    try:
        params = compute_hinged_bangle_params(
            inner_circumference_mm=inner_circ_mm,
            cross_section=cross_section,
            cs_width_mm=cs_width_mm,
            cs_height_mm=cs_height_mm,
            clasp_style=clasp_style,
            hinge_pin_diameter_mm=hinge_pin_d,
            inner_profile=inner_profile,
            metal=metal,
            n_stone_stations=n_stations,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    node_id = a.get("node_id") or str(uuid.uuid4())
    node = build_bangle_node(str(file_uuid), "hinged_bangle", params, node_id=node_id)

    content_str, err = await read_feature_content(ctx, str(file_uuid))
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    new_content, err2 = append_feature_node(content_str, node)
    if err2:
        return err_payload(err2, "ERROR")

    from kerf_cad_core.surfacing import write_feature_content
    err3 = await write_feature_content(ctx, str(file_uuid), new_content)
    if err3:
        return err_payload(err3, "ERROR")

    return ok_payload({
        "node_id": node_id,
        "file_id": str(file_uuid),
        "hinged_bangle": params,
    })
