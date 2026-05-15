"""
kerf_cad_core.jewelry.ring
==========================

Ring-size system (US / UK+AU / EU / JP), parametric shank generator, and
shoulder/style builders for jewelry-CAD ring-band construction.

Ring-size formula
-----------------
US system (per Hoover & Strong / industry standard):

    inner_diameter_mm = 11.63 + 0.8128 * us_size

Cross-checked against published Stuller chart (2024) and Town Talk reference
table.  Sample values:
    US 0  → 11.63 mm  (inner diam)  circumference 36.5 mm
    US 5  → 15.69 mm                circumference 49.3 mm
    US 7  → 17.32 mm                circumference 54.4 mm
    US 10 → 19.76 mm                circumference 62.1 mm
    US 16 → 24.65 mm                circumference 77.4 mm

UK/AU letters map to specific circumferences per the ISO 8653 / British
Standards chart.  JP sizes (1–30, integers only) map to circumference in mm
(JP size = circumference − 37 approximately; precise table used here).

All circumference / inner-diameter math:
    circumference_mm = π * inner_diameter_mm
    inner_diameter_mm = circumference_mm / π

Public API
----------
    ring_size_to_diameter(system, size) -> float          # mm
    ring_diameter_to_size(system, diameter_mm) -> str|float

    compute_shank_params(ring_size, system, band_width, thickness,
                         profile, taper_ratio, ...) -> dict

    build_shank_node(file_id, ring_size, system, band_width, thickness,
                     profile, shoulder_style, taper_ratio, node_id) -> dict

LLM tools registered
---------------------
    jewelry_ring_size_to_diameter
    jewelry_create_ring_shank

New profiles (v2)
-----------------
    cigar_band   — wide, flat-topped band with heavy bevelled edges
    bombe        — domed (convex) outer surface, flat inner bore
    concave      — concave outer channel running around the band
    square       — square cross-section with sharp corners
    hammered     — faceted outer surface; facet_count controls the number
                   of hammer-strike facets around the circumference
    split_band   — geometry hint for a true split-band (two parallel rails);
                   gap_mm controls the gap between the rails

New node-spec fields (v2)
--------------------------
    engraving          — EngravingSpec: text on band (geometry hint, no OCCT render)
    sizing_beads       — SizingBeadSpec: small interior beads for snug fit
    comfort_fit_radius — float: interior dome radius override (mm)
    finger_fit_taper   — float: asymmetric taper angle (degrees) for knuckle fit
    width_profile      — list[float]: width taper curve (shoulder→back, 2–10 points,
                         each 0 < v ≤ 1.0, relative to band_width)
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PI = math.pi

# US size formula: ID_mm = 11.63 + 0.8128 * us_size
# Source: Hoover & Strong ring-size guide; cross-checked against Stuller 2024
# and Town Talk reference tables.
_US_ID_INTERCEPT = 11.63
_US_ID_SLOPE = 0.8128

# US half-sizes: 0, 0.5, 1, 1.5, ..., 16
_US_SIZES: list[float] = [n / 2 for n in range(0, 33)]  # 0 to 16 inclusive

# UK/AU letter sizes → circumference in mm
# Source: ISO 8653 + British Measurement Standard (Cookson Gold reference 2023)
# A–Z then Z+1, Z+2, Z+3 where needed.  Full A–Z+ (27 entries) standard.
_UK_AU_SIZES: dict[str, float] = {
    "A":    37.8,
    "A½":   38.4,
    "B":    39.1,
    "B½":   39.7,
    "C":    40.4,
    "C½":   41.1,
    "D":    41.7,
    "D½":   42.4,
    "E":    43.0,
    "E½":   43.7,
    "F":    44.2,
    "F½":   44.8,
    "G":    45.5,
    "G½":   46.1,
    "H":    46.8,
    "H½":   47.4,
    "I":    48.0,
    "I½":   48.7,
    "J":    49.3,
    "J½":   50.0,
    "K":    50.6,
    "K½":   51.2,
    "L":    51.9,
    "L½":   52.5,
    "M":    53.1,
    "M½":   53.8,
    "N":    54.4,
    "N½":   55.1,
    "O":    55.7,
    "O½":   56.3,
    "P":    57.0,
    "P½":   57.6,
    "Q":    58.3,
    "Q½":   58.9,
    "R":    59.5,
    "R½":   60.2,
    "S":    60.8,
    "S½":   61.4,
    "T":    62.1,
    "T½":   62.7,
    "U":    63.4,
    "U½":   64.0,
    "V":    64.6,
    "V½":   65.3,
    "W":    65.9,
    "W½":   66.6,
    "X":    67.2,
    "X½":   67.8,
    "Y":    68.5,
    "Y½":   69.1,
    "Z":    69.7,
    "Z+1":  70.4,
    "Z+2":  71.0,
    "Z+3":  71.7,
}

# JP ring sizes (1–30 integers)
# Source: JIS B 4901 standard table (circumference in mm)
# JP size = (circumference_mm - 37) rounded to nearest integer (approx).
# Full lookup table used for accuracy.
_JP_SIZES: dict[int, float] = {
    1:  38.1,
    2:  39.0,
    3:  39.9,
    4:  40.8,
    5:  41.7,
    6:  42.6,
    7:  43.5,
    8:  44.4,
    9:  45.3,
    10: 46.2,
    11: 47.1,
    12: 47.9,
    13: 48.8,
    14: 49.7,
    15: 50.6,
    16: 51.5,
    17: 52.4,
    18: 53.3,
    19: 54.2,
    20: 55.1,
    21: 55.9,
    22: 56.8,
    23: 57.7,
    24: 58.6,
    25: 59.5,
    26: 60.4,
    27: 61.3,
    28: 62.2,
    29: 63.1,
    30: 64.0,
}

# EU ring sizes = inner circumference in mm (integer or .5, range 41–76)
_EU_MIN_CIRC = 41.0
_EU_MAX_CIRC = 76.0

# Valid profile strings
_VALID_PROFILES = frozenset([
    # original profiles
    "d_shape",
    "comfort_fit",
    "flat",
    "half_round",
    "knife_edge",
    "euro",
    "tapered",
    # v2 profiles
    "cigar_band",
    "bombe",
    "concave",
    "square",
    "hammered",
    "split_band",
])

# Valid shoulder styles
_VALID_SHOULDER_STYLES = frozenset([
    "plain",
    "cathedral",
    "split_shank",
    "bypass",
])

# Valid size systems
_VALID_SYSTEMS = frozenset(["us", "uk", "au", "eu", "jp"])


# ---------------------------------------------------------------------------
# Ring-size math
# ---------------------------------------------------------------------------

def _us_size_to_id_mm(size: float) -> float:
    """US size → inner diameter in mm."""
    return _US_ID_INTERCEPT + _US_ID_SLOPE * size


def _id_mm_to_circumference(id_mm: float) -> float:
    return _PI * id_mm


def _circumference_to_id_mm(circ_mm: float) -> float:
    return circ_mm / _PI


def ring_size_to_diameter(system: str, size) -> float:
    """Convert a ring size in the given system to inner diameter in mm.

    Parameters
    ----------
    system : str
        One of ``"us"``, ``"uk"``, ``"au"``, ``"eu"``, ``"jp"``.
    size : int | float | str
        - US: numeric 0–16, half-sizes allowed (e.g. 7, 7.5, "7½")
        - UK/AU: letter string (e.g. "N", "N½", "Z+1")
        - EU: numeric circumference in mm (41–76)
        - JP: integer 1–30

    Returns
    -------
    float
        Inner diameter in mm.

    Raises
    ------
    ValueError
        On unknown system, out-of-range size, or unparseable input.
    """
    sys_lower = str(system).lower().strip()

    if sys_lower == "us":
        us = _parse_us_size(size)
        if us < 0 or us > 16:
            raise ValueError(f"US ring size must be 0–16; got {us!r}")
        return _us_size_to_id_mm(us)

    elif sys_lower in ("uk", "au"):
        key = _normalise_uk_key(size)
        if key not in _UK_AU_SIZES:
            raise ValueError(
                f"Unknown UK/AU ring size {size!r}. "
                f"Valid values: {sorted(_UK_AU_SIZES)}"
            )
        return _circumference_to_id_mm(_UK_AU_SIZES[key])

    elif sys_lower == "eu":
        try:
            circ = float(size)
        except (TypeError, ValueError):
            raise ValueError(f"EU size must be a number (circumference mm); got {size!r}")
        if circ < _EU_MIN_CIRC or circ > _EU_MAX_CIRC:
            raise ValueError(f"EU ring size must be {_EU_MIN_CIRC}–{_EU_MAX_CIRC} mm; got {circ}")
        return _circumference_to_id_mm(circ)

    elif sys_lower == "jp":
        try:
            jp = int(size)
        except (TypeError, ValueError):
            raise ValueError(f"JP size must be an integer 1–30; got {size!r}")
        if jp not in _JP_SIZES:
            raise ValueError(f"JP ring size must be 1–30; got {jp}")
        return _circumference_to_id_mm(_JP_SIZES[jp])

    else:
        raise ValueError(
            f"Unknown ring-size system {system!r}. "
            f"Valid: {sorted(_VALID_SYSTEMS)}"
        )


def ring_diameter_to_size(system: str, diameter_mm: float):
    """Convert inner diameter (mm) back to the nearest ring size string/number.

    Returns the nearest valid size in the requested system.

    Parameters
    ----------
    system : str
        One of ``"us"``, ``"uk"``, ``"au"``, ``"eu"``, ``"jp"``.
    diameter_mm : float
        Inner diameter in mm.

    Returns
    -------
    float | str
        - US: nearest half-size float (0–16)
        - UK/AU: nearest letter string
        - EU: circumference in mm (rounded to nearest 0.5)
        - JP: nearest integer (1–30)
    """
    sys_lower = str(system).lower().strip()

    if sys_lower not in _VALID_SYSTEMS:
        raise ValueError(
            f"Unknown ring-size system {system!r}. Valid: {sorted(_VALID_SYSTEMS)}"
        )

    if diameter_mm <= 0:
        raise ValueError(f"diameter_mm must be positive; got {diameter_mm}")

    if sys_lower == "us":
        raw = (diameter_mm - _US_ID_INTERCEPT) / _US_ID_SLOPE
        # Snap to nearest half-size in 0–16
        nearest = min(_US_SIZES, key=lambda s: abs(s - raw))
        return nearest

    elif sys_lower in ("uk", "au"):
        circ = _id_mm_to_circumference(diameter_mm)
        nearest_key = min(_UK_AU_SIZES.keys(), key=lambda k: abs(_UK_AU_SIZES[k] - circ))
        return nearest_key

    elif sys_lower == "eu":
        circ = _id_mm_to_circumference(diameter_mm)
        # Round to nearest 0.5
        rounded = round(circ * 2) / 2
        clamped = max(_EU_MIN_CIRC, min(_EU_MAX_CIRC, rounded))
        return clamped

    elif sys_lower == "jp":
        circ = _id_mm_to_circumference(diameter_mm)
        nearest_jp = min(_JP_SIZES.keys(), key=lambda k: abs(_JP_SIZES[k] - circ))
        return nearest_jp

    raise ValueError(f"Unknown system: {system!r}")


def _parse_us_size(size) -> float:
    """Parse US size from float, int, or string like '7½'."""
    if isinstance(size, (int, float)):
        return float(size)
    s = str(size).strip().replace("½", ".5").replace("¼", ".25").replace("¾", ".75")
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"Cannot parse US ring size {size!r}")


def _normalise_uk_key(size) -> str:
    """Normalise a UK/AU size string to the table key format."""
    s = str(size).strip()
    # Accept "N1/2" → "N½", "N 1/2" → "N½"
    s = s.replace("1/2", "½").replace(" ", "")
    # Accept lowercase
    if len(s) >= 1 and s[0].islower():
        s = s[0].upper() + s[1:]
    return s


# ---------------------------------------------------------------------------
# Shank parameter computation (pure Python, no OCC)
# ---------------------------------------------------------------------------

# Profile cross-section descriptions for the feature node
_PROFILE_DESCRIPTIONS: dict[str, str] = {
    # original
    "d_shape":     "Flat outside, curved inside — classic men's band.",
    "comfort_fit": "Domed outside, rounded inside for comfort — slides on easily.",
    "flat":        "Fully flat top and bottom, squared edges — contemporary style.",
    "half_round":  "Domed on top, flat on bottom — most common women's band.",
    "knife_edge":  "V-shaped ridge along centre of outer face — architectural look.",
    "euro":        "Slightly squared profile (≈rectangular with rounded corners).",
    "tapered":     "Width and/or thickness taper from shoulder to base.",
    # v2
    "cigar_band":  "Wide flat-topped band with heavy bevelled edges — bold statement.",
    "bombe":       "Convex domed outer surface, flat inner bore — full rounded look.",
    "concave":     "Concave channel carved into the outer face — elegant groove detail.",
    "square":      "Square cross-section with sharp 90° corners — architectural/modern.",
    "hammered":    "Outer surface divided into flat hammer-strike facets — artisan texture.",
    "split_band":  "Two parallel rail bands separated by a central gap — open split look.",
}


# ---------------------------------------------------------------------------
# v2 spec dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EngravingSpec:
    """Parametric band-engraving descriptor.

    Geometry hint only — the occtWorker subtracts an engraved text channel
    from the outer face of the band.  Actual OCCT font / text rendering is
    deferred to the worker; this spec carries only the layout parameters.

    Fields
    ------
    text : str
        The text string to engrave (UTF-8, max 200 chars).
    font_height_mm : float
        Nominal glyph cap-height in mm.  > 0.
    depth_mm : float
        Engraving cut depth below the outer surface, mm.  > 0, must be < thickness.
    position_deg : float
        Angular start position around the band in degrees (0 = bottom / 6-o'clock,
        positive = clockwise when viewed from below).  0–360.
    align : str
        Text alignment relative to position_deg: "centre", "left", or "right".
    """
    text: str
    font_height_mm: float = 1.5
    depth_mm: float = 0.3
    position_deg: float = 180.0  # bottom of the band by default
    align: str = "centre"

    # valid alignment tokens
    _VALID_ALIGN = frozenset(["centre", "left", "right"])

    def validate(self) -> None:
        if not self.text or not str(self.text).strip():
            raise ValueError("engraving.text must be a non-empty string")
        if len(str(self.text)) > 200:
            raise ValueError("engraving.text must be ≤ 200 characters")
        if self.font_height_mm <= 0:
            raise ValueError(f"engraving.font_height_mm must be > 0; got {self.font_height_mm}")
        if self.depth_mm <= 0:
            raise ValueError(f"engraving.depth_mm must be > 0; got {self.depth_mm}")
        if not (0.0 <= self.position_deg <= 360.0):
            raise ValueError(
                f"engraving.position_deg must be 0–360; got {self.position_deg}"
            )
        if self.align not in self._VALID_ALIGN:
            raise ValueError(
                f"engraving.align must be one of {sorted(self._VALID_ALIGN)}; "
                f"got {self.align!r}"
            )

    def to_dict(self) -> dict:
        self.validate()
        return {
            "text": str(self.text),
            "font_height_mm": self.font_height_mm,
            "depth_mm": self.depth_mm,
            "position_deg": self.position_deg,
            "align": self.align,
        }


@dataclass
class SizingBeadSpec:
    """Small hemispherical protrusions on the inner bore to snug ring fit.

    The worker adds two diametrically-opposed (or equidistant) beads on
    the inner surface.  This is a geometry hint; the worker resolves the
    bead subtraction / union from the band solid.

    Fields
    ------
    count : int
        Number of beads equally spaced around the bore.  1–4.
    bead_diameter_mm : float
        Diameter of each bead hemisphere, mm.  > 0, typically 0.8–1.5 mm.
    bead_height_mm : float
        How far each bead protrudes inward from the inner surface, mm.  > 0.
        Must be < (thickness / 4) to avoid punching through the band.
    position_deg : float
        Angular position of the first bead (0 = bottom of the ring,
        positive clockwise from below).  0–360.
    """
    count: int = 2
    bead_diameter_mm: float = 1.0
    bead_height_mm: float = 0.4
    position_deg: float = 270.0  # 9-o'clock = comfortable lateral position

    def validate(self, band_thickness_mm: float = 0.0) -> None:
        if not (1 <= self.count <= 4):
            raise ValueError(f"sizing_beads.count must be 1–4; got {self.count}")
        if self.bead_diameter_mm <= 0:
            raise ValueError(
                f"sizing_beads.bead_diameter_mm must be > 0; got {self.bead_diameter_mm}"
            )
        if self.bead_height_mm <= 0:
            raise ValueError(
                f"sizing_beads.bead_height_mm must be > 0; got {self.bead_height_mm}"
            )
        if not (0.0 <= self.position_deg <= 360.0):
            raise ValueError(
                f"sizing_beads.position_deg must be 0–360; got {self.position_deg}"
            )
        if band_thickness_mm > 0 and self.bead_height_mm >= band_thickness_mm / 4.0:
            raise ValueError(
                f"sizing_beads.bead_height_mm ({self.bead_height_mm}) must be < "
                f"thickness/4 ({band_thickness_mm / 4.0:.3f}) to avoid perforation"
            )

    def to_dict(self) -> dict:
        self.validate()
        return {
            "count": self.count,
            "bead_diameter_mm": self.bead_diameter_mm,
            "bead_height_mm": self.bead_height_mm,
            "position_deg": self.position_deg,
        }


def _validate_width_profile(curve: list) -> list[float]:
    """Validate and normalise a width_profile curve.

    Parameters
    ----------
    curve : list
        2–10 floats, each in range (0, 1].  Index 0 = shoulder end,
        last index = back of the band.  1.0 = full band_width.

    Returns
    -------
    list[float]
        Validated list of floats.

    Raises
    ------
    ValueError
    """
    if not isinstance(curve, (list, tuple)) or len(curve) < 2 or len(curve) > 10:
        raise ValueError(
            f"width_profile must be a list of 2–10 floats; got {len(curve) if isinstance(curve, (list, tuple)) else type(curve)}"
        )
    result = []
    for i, v in enumerate(curve):
        try:
            fv = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"width_profile[{i}] must be a number; got {v!r}")
        if fv <= 0 or fv > 1.0:
            raise ValueError(
                f"width_profile[{i}] must be in (0, 1]; got {fv}"
            )
        result.append(fv)
    return result


def _profile_extra_hints(
    profile: str,
    thickness: float,
    band_width: float,
    *,
    hammered_facet_count: int = 32,
    split_band_gap_mm: float = 1.0,
    bombe_dome_ratio: float = 0.5,
    concave_depth_ratio: float = 0.3,
    cigar_bevel_ratio: float = 0.2,
) -> dict:
    """Return profile-specific geometry hints for v2 profiles.

    Original profiles return an empty dict (no extra hints beyond profile name).
    v2 profiles return a hints sub-dict embedded in the node under
    ``profile_hints``.

    Parameters
    ----------
    profile : str
        One of the _VALID_PROFILES values.
    thickness : float
        Band radial wall thickness, mm.
    band_width : float
        Band width along finger axis, mm.
    hammered_facet_count : int
        Number of flat facets around the outer circumference for
        ``hammered`` profile.  4–128.  Default 32.
    split_band_gap_mm : float
        Gap between the two rails for ``split_band`` profile.  > 0.
        Must be < band_width − 0.5 mm (leaves at least 0.25 mm per rail).
        Default 1.0 mm.
    bombe_dome_ratio : float
        Outer dome height as a fraction of the half-width for ``bombe``.
        0 < v ≤ 1.0.  Default 0.5.
    concave_depth_ratio : float
        Depth of the concave channel as a fraction of band_width for
        ``concave``.  0 < v < 0.5.  Default 0.3.
    cigar_bevel_ratio : float
        Bevel edge width as a fraction of band_width for ``cigar_band``.
        0 < v < 0.4.  Default 0.2 (so bevel occupies 20% of each edge).
    """
    _ORIG_PROFILES = frozenset([
        "d_shape", "comfort_fit", "flat", "half_round",
        "knife_edge", "euro", "tapered",
    ])
    if profile in _ORIG_PROFILES:
        return {}

    if profile == "cigar_band":
        if not (0 < cigar_bevel_ratio < 0.4):
            raise ValueError(
                f"cigar_bevel_ratio must be in (0, 0.4); got {cigar_bevel_ratio}"
            )
        bevel_mm = round(band_width * cigar_bevel_ratio, 3)
        return {
            "type": "cigar_band",
            "bevel_width_mm": bevel_mm,
            "flat_top_width_mm": round(band_width * (1.0 - 2 * cigar_bevel_ratio), 3),
        }

    elif profile == "bombe":
        if not (0 < bombe_dome_ratio <= 1.0):
            raise ValueError(
                f"bombe_dome_ratio must be in (0, 1]; got {bombe_dome_ratio}"
            )
        dome_height = round(band_width * 0.5 * bombe_dome_ratio, 3)
        return {
            "type": "bombe",
            "dome_height_mm": dome_height,
            "dome_ratio": bombe_dome_ratio,
        }

    elif profile == "concave":
        if not (0 < concave_depth_ratio < 0.5):
            raise ValueError(
                f"concave_depth_ratio must be in (0, 0.5); got {concave_depth_ratio}"
            )
        channel_depth = round(thickness * concave_depth_ratio, 3)
        channel_width = round(band_width * 0.6, 3)
        return {
            "type": "concave",
            "channel_depth_mm": channel_depth,
            "channel_width_mm": channel_width,
        }

    elif profile == "square":
        return {
            "type": "square",
            "corner_radius_mm": 0.0,  # truly sharp — worker may add micro-fillet
        }

    elif profile == "hammered":
        fc = int(hammered_facet_count)
        if not (4 <= fc <= 128):
            raise ValueError(
                f"hammered_facet_count must be 4–128; got {fc}"
            )
        facet_arc_deg = round(360.0 / fc, 4)
        return {
            "type": "hammered",
            "facet_count": fc,
            "facet_arc_deg": facet_arc_deg,
        }

    elif profile == "split_band":
        if split_band_gap_mm <= 0:
            raise ValueError(
                f"split_band_gap_mm must be > 0; got {split_band_gap_mm}"
            )
        min_rail = 0.25
        if split_band_gap_mm >= band_width - 2 * min_rail:
            raise ValueError(
                f"split_band_gap_mm ({split_band_gap_mm}) too large for "
                f"band_width {band_width} — each rail must be ≥ {min_rail} mm"
            )
        rail_width = round((band_width - split_band_gap_mm) / 2.0, 3)
        return {
            "type": "split_band",
            "gap_mm": round(split_band_gap_mm, 3),
            "rail_width_mm": rail_width,
        }

    return {}


def compute_shank_params(
    ring_size,
    system: str = "us",
    band_width: float = 4.0,
    thickness: float = 1.8,
    profile: str = "comfort_fit",
    taper_ratio: float = 1.0,
    shoulder_style: str = "plain",
    # v2 profile-specific params
    hammered_facet_count: int = 32,
    split_band_gap_mm: float = 1.0,
    bombe_dome_ratio: float = 0.5,
    concave_depth_ratio: float = 0.3,
    cigar_bevel_ratio: float = 0.2,
    # v2 engraving
    engraving: Optional[EngravingSpec] = None,
    # v2 sizing / fit features
    sizing_beads: Optional[SizingBeadSpec] = None,
    comfort_fit_radius: Optional[float] = None,
    finger_fit_taper: float = 0.0,
    width_profile: Optional[list] = None,
) -> dict:
    """Compute validated parametric shank descriptor.

    All dimensions in mm.  Returns a dict suitable for embedding in a feature
    JSON node (op = ``ring_shank``).

    Parameters
    ----------
    ring_size : int | float | str
        Size in the requested system.
    system : str
        "us", "uk", "au", "eu", "jp"
    band_width : float
        Width of the band (finger-axis direction), mm.  > 0.
    thickness : float
        Radial thickness of the band wall, mm.  > 0.
    profile : str
        One of: d_shape, comfort_fit, flat, half_round, knife_edge, euro,
        tapered, cigar_band, bombe, concave, square, hammered, split_band.
    taper_ratio : float
        Width/thickness scale at the base of the shank relative to the shoulder
        top.  1.0 = uniform; 0.6 = base is 60 % of shoulder dimension.
    shoulder_style : str
        One of: plain, cathedral, split_shank, bypass.
    hammered_facet_count : int
        Number of hammer-strike facets (only used for ``hammered`` profile).
        4–128, default 32.
    split_band_gap_mm : float
        Gap between rails in mm (only used for ``split_band`` profile).  > 0.
    bombe_dome_ratio : float
        Dome height fraction of half-width (only ``bombe``).  0 < v ≤ 1.0.
    concave_depth_ratio : float
        Concave channel depth as fraction of thickness (only ``concave``).
        0 < v < 0.5.
    cigar_bevel_ratio : float
        Bevel edge width fraction of band_width (only ``cigar_band``).
        0 < v < 0.4.
    engraving : EngravingSpec | None
        Optional band-engraving geometry hint.  See EngravingSpec.
    sizing_beads : SizingBeadSpec | None
        Optional interior sizing beads for snug fit.  See SizingBeadSpec.
    comfort_fit_radius : float | None
        Override the interior dome radius (mm) when using comfort_fit profile.
        If None, the worker uses its default (≈ 0.8 × inner_radius).  > 0.
    finger_fit_taper : float
        Asymmetric taper angle (degrees) to accommodate knuckle sizing.
        The band is slightly wider on one side by this taper angle.
        0 = symmetric (default); 0–15 degrees accepted.
    width_profile : list[float] | None
        2–10 floats (0 < v ≤ 1.0) describing width ratio from shoulder (index 0)
        to back of band (last index).  1.0 = full band_width.
        None = no width taper (uniform).

    Returns
    -------
    dict
        Inner diameter, circumference, profile, shoulder_style, geometry hints,
        and all v2 feature fields.
    """
    if profile not in _VALID_PROFILES:
        raise ValueError(
            f"Unknown profile {profile!r}. Valid: {sorted(_VALID_PROFILES)}"
        )
    if shoulder_style not in _VALID_SHOULDER_STYLES:
        raise ValueError(
            f"Unknown shoulder_style {shoulder_style!r}. "
            f"Valid: {sorted(_VALID_SHOULDER_STYLES)}"
        )
    if band_width <= 0:
        raise ValueError(f"band_width must be > 0; got {band_width}")
    if thickness <= 0:
        raise ValueError(f"thickness must be > 0; got {thickness}")
    if taper_ratio <= 0:
        raise ValueError(f"taper_ratio must be > 0; got {taper_ratio}")

    # v2 param validation
    if comfort_fit_radius is not None:
        if comfort_fit_radius <= 0:
            raise ValueError(
                f"comfort_fit_radius must be > 0; got {comfort_fit_radius}"
            )
    if not (0.0 <= finger_fit_taper <= 15.0):
        raise ValueError(
            f"finger_fit_taper must be 0–15 degrees; got {finger_fit_taper}"
        )

    id_mm = ring_size_to_diameter(system, ring_size)
    circ_mm = _id_mm_to_circumference(id_mm)
    outer_diameter = id_mm + 2 * thickness

    # Shoulder geometry hints (multipliers / offsets, not full BREP)
    shoulder_hints = _shoulder_hints(shoulder_style, id_mm, band_width)

    # v2 profile hints
    profile_hints = _profile_extra_hints(
        profile,
        thickness,
        band_width,
        hammered_facet_count=hammered_facet_count,
        split_band_gap_mm=split_band_gap_mm,
        bombe_dome_ratio=bombe_dome_ratio,
        concave_depth_ratio=concave_depth_ratio,
        cigar_bevel_ratio=cigar_bevel_ratio,
    )

    result: dict = {
        "inner_diameter_mm": round(id_mm, 4),
        "outer_diameter_mm": round(outer_diameter, 4),
        "circumference_mm": round(circ_mm, 4),
        "band_width_mm": band_width,
        "thickness_mm": thickness,
        "profile": profile,
        "taper_ratio": taper_ratio,
        "shoulder_style": shoulder_style,
        "shoulder_hints": shoulder_hints,
        "size_system": system,
        "ring_size": ring_size,
    }

    if profile_hints:
        result["profile_hints"] = profile_hints

    # Engraving spec
    if engraving is not None:
        engraving.validate()
        result["engraving"] = engraving.to_dict()

    # Sizing beads
    if sizing_beads is not None:
        sizing_beads.validate(band_thickness_mm=thickness)
        result["sizing_beads"] = sizing_beads.to_dict()

    # Comfort fit interior radius override
    if comfort_fit_radius is not None:
        result["comfort_fit_radius_mm"] = round(comfort_fit_radius, 4)

    # Asymmetric finger-fit taper
    if finger_fit_taper != 0.0:
        result["finger_fit_taper_deg"] = round(finger_fit_taper, 4)

    # Width profile curve
    if width_profile is not None:
        result["width_profile"] = _validate_width_profile(width_profile)

    return result


def _shoulder_hints(style: str, id_mm: float, band_width: float) -> dict:
    """Return geometry hint parameters for the shoulder style.

    These are parameters that the occtWorker's ``opRingShank`` uses to modify
    the base swept band.  Values are all in mm unless noted.
    """
    radius = id_mm / 2.0
    if style == "plain":
        return {"type": "plain"}

    elif style == "cathedral":
        # Cathedral arch: shoulders rise from the base of the shank toward a
        # raised centre setting.  The arch height above the top of the band is
        # typically 30–50% of the finger radius; default 35%.
        arch_height = round(radius * 0.35, 3)
        # The arch starts at ±70° from the top (12 o'clock) and meets at the
        # setting centre at the top.
        arch_start_deg = 70.0
        return {
            "type": "cathedral",
            "arch_height_mm": arch_height,
            "arch_start_deg": arch_start_deg,
            "blend_radius_mm": round(band_width * 0.4, 3),
        }

    elif style == "split_shank":
        # Split shank: the band splits into two prongs near the setting.
        # The split starts at ±55° from the top.
        split_start_deg = 55.0
        gap_mm = round(band_width * 0.45, 3)
        return {
            "type": "split_shank",
            "split_start_deg": split_start_deg,
            "prong_gap_mm": gap_mm,
            "prong_width_mm": round((band_width - gap_mm) / 2.0, 3),
        }

    elif style == "bypass":
        # Bypass: the two ends of the band pass alongside each other rather than
        # meeting at the top.  Offset each end by half the band width.
        bypass_offset_mm = round(band_width * 0.6, 3)
        return {
            "type": "bypass",
            "bypass_offset_mm": bypass_offset_mm,
            "overlap_deg": 30.0,
        }

    return {"type": style}


# ---------------------------------------------------------------------------
# Feature node builder (for direct use by the LLM tool runner)
# ---------------------------------------------------------------------------

def _next_ring_shank_id(content: str) -> str:
    """Generate a unique node id for a ring_shank feature node."""
    try:
        doc = json.loads(content)
        features = doc.get("features", [])
        max_n = 0
        for item in features:
            nid = item.get("id", "")
            if nid.startswith("ring_shank-"):
                try:
                    n = int(nid[len("ring_shank-"):])
                    max_n = max(max_n, n)
                except ValueError:
                    pass
        return f"ring_shank-{max_n + 1}"
    except Exception:
        return "ring_shank-1"


# ---------------------------------------------------------------------------
# LLM tool: jewelry_ring_size_to_diameter
# ---------------------------------------------------------------------------

jewelry_ring_size_to_diameter_spec = ToolSpec(
    name="jewelry_ring_size_to_diameter",
    description=(
        "Convert a ring size in US, UK/AU, EU, or JP system to inner diameter "
        "(and circumference) in mm. Also supports the inverse: given a diameter, "
        "return the nearest ring size. "
        "Systems: 'us' (0–16, halves OK), 'uk'/'au' (A–Z+), 'eu' (circumference "
        "mm 41–76), 'jp' (1–30 integers). "
        "Use this to compute the inner bore radius before calling "
        "jewelry_create_ring_shank."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "system": {
                "type": "string",
                "enum": ["us", "uk", "au", "eu", "jp"],
                "description": "Ring-size standard to use.",
            },
            "size": {
                "description": (
                    "Size in the chosen system. "
                    "US: number or string like '7' or '7½'. "
                    "UK/AU: letter string like 'N' or 'N½'. "
                    "EU: circumference in mm as a number. "
                    "JP: integer 1–30."
                ),
            },
            "diameter_mm": {
                "type": "number",
                "description": (
                    "If provided (and size is omitted), perform the inverse lookup: "
                    "return the nearest ring size in the chosen system for this "
                    "inner diameter in mm."
                ),
            },
        },
        "required": ["system"],
    },
)


@register(jewelry_ring_size_to_diameter_spec, write=False)
async def run_jewelry_ring_size_to_diameter(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    system = a.get("system", "").strip().lower()
    size = a.get("size", None)
    diameter_mm = a.get("diameter_mm", None)

    if system not in _VALID_SYSTEMS:
        return err_payload(
            f"system must be one of {sorted(_VALID_SYSTEMS)}; got {system!r}",
            "BAD_ARGS",
        )

    # Inverse lookup
    if diameter_mm is not None and size is None:
        try:
            d = float(diameter_mm)
        except (TypeError, ValueError):
            return err_payload("diameter_mm must be a number", "BAD_ARGS")
        if d <= 0:
            return err_payload("diameter_mm must be positive", "BAD_ARGS")
        try:
            nearest = ring_diameter_to_size(system, d)
        except ValueError as e:
            return err_payload(str(e), "BAD_ARGS")
        return ok_payload({
            "system": system,
            "diameter_mm": d,
            "nearest_size": nearest,
            "nearest_size_diameter_mm": round(ring_size_to_diameter(system, nearest), 4),
        })

    # Forward lookup
    if size is None:
        return err_payload("either 'size' or 'diameter_mm' is required", "BAD_ARGS")

    try:
        id_mm = ring_size_to_diameter(system, size)
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    return ok_payload({
        "system": system,
        "size": size,
        "inner_diameter_mm": round(id_mm, 4),
        "inner_radius_mm": round(id_mm / 2.0, 4),
        "circumference_mm": round(_id_mm_to_circumference(id_mm), 4),
    })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_ring_shank
# ---------------------------------------------------------------------------

jewelry_create_ring_shank_spec = ToolSpec(
    name="jewelry_create_ring_shank",
    description=(
        "Append a `ring_shank` node to a `.feature` file. "
        "Builds a parametric ring band swept along the finger circle. "
        "Profile options: d_shape (flat outside / curved inside), "
        "comfort_fit (domed outside / rounded inside — standard ladies' band), "
        "flat (contemporary squared profile), half_round (classic domed top), "
        "knife_edge (V-ridge centre line), euro (square-ish), "
        "tapered (width+thickness taper from shoulder to base), "
        "cigar_band (wide flat-top with bevelled edges), "
        "bombe (convex domed outer surface), "
        "concave (concave outer channel), "
        "square (sharp 90° corners), "
        "hammered (faceted artisan texture, use hammered_facet_count to control), "
        "split_band (two parallel rails with a central gap, use split_band_gap_mm). "
        "Shoulder styles: plain (uniform band), cathedral (arched shoulders "
        "rising to a centre setting), split_shank (band splits into two prongs "
        "near the setting), bypass (ends pass alongside each other). "
        "v2 extras: engraving (text on band), sizing_beads (interior snug-fit beads), "
        "comfort_fit_radius (custom interior dome radius), finger_fit_taper (knuckle "
        "asymmetry), width_profile (taper curve shoulder→back). "
        "All dimensions in mm. Ring size is auto-converted to inner diameter. "
        "The feature node is stored and evaluated by the occtWorker opRingShank "
        "sweep using a corrected_frenet frame on the circular path."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "ring_size": {
                "description": (
                    "Size in the chosen system. "
                    "US number/string (0–16), UK/AU letter (e.g. 'N'), "
                    "EU circumference mm (41–76), JP integer (1–30)."
                ),
            },
            "system": {
                "type": "string",
                "enum": ["us", "uk", "au", "eu", "jp"],
                "description": "Ring-size standard. Default 'us'.",
            },
            "band_width": {
                "type": "number",
                "description": "Band width along the finger axis, mm. Default 4.0.",
            },
            "thickness": {
                "type": "number",
                "description": "Radial wall thickness, mm. Default 1.8.",
            },
            "profile": {
                "type": "string",
                "enum": [
                    "d_shape", "comfort_fit", "flat", "half_round",
                    "knife_edge", "euro", "tapered",
                    "cigar_band", "bombe", "concave", "square",
                    "hammered", "split_band",
                ],
                "description": "Cross-section profile. Default 'comfort_fit'.",
            },
            "taper_ratio": {
                "type": "number",
                "description": (
                    "Width+thickness scale at the back of the shank relative to "
                    "the shoulder. 1.0 = uniform; 0.6 = back is 60% of shoulder. "
                    "Default 1.0."
                ),
            },
            "shoulder_style": {
                "type": "string",
                "enum": ["plain", "cathedral", "split_shank", "bypass"],
                "description": "How the shank meets the head/setting. Default 'plain'.",
            },
            # v2 profile-specific params
            "hammered_facet_count": {
                "type": "integer",
                "description": (
                    "Number of flat hammer-strike facets around the outer "
                    "circumference. Only used for profile='hammered'. "
                    "Range 4–128. Default 32."
                ),
            },
            "split_band_gap_mm": {
                "type": "number",
                "description": (
                    "Gap between the two parallel rails for profile='split_band'. "
                    "Must be > 0 and < band_width − 0.5 mm. Default 1.0 mm."
                ),
            },
            "bombe_dome_ratio": {
                "type": "number",
                "description": (
                    "Dome height as fraction of half-band-width for profile='bombe'. "
                    "0 < v ≤ 1.0. Default 0.5."
                ),
            },
            "concave_depth_ratio": {
                "type": "number",
                "description": (
                    "Concave channel depth as fraction of thickness for "
                    "profile='concave'. 0 < v < 0.5. Default 0.3."
                ),
            },
            "cigar_bevel_ratio": {
                "type": "number",
                "description": (
                    "Bevel edge fraction of band_width for profile='cigar_band'. "
                    "0 < v < 0.4. Default 0.2."
                ),
            },
            # v2 engraving
            "engraving": {
                "type": "object",
                "description": (
                    "Optional band-engraving spec (geometry hint only; "
                    "OCCT text rendering deferred to occtWorker). "
                    "Fields: text (str, required), font_height_mm (float, default 1.5), "
                    "depth_mm (float, default 0.3), position_deg (float 0–360, default 180), "
                    "align ('centre'|'left'|'right', default 'centre')."
                ),
                "properties": {
                    "text": {"type": "string"},
                    "font_height_mm": {"type": "number"},
                    "depth_mm": {"type": "number"},
                    "position_deg": {"type": "number"},
                    "align": {"type": "string", "enum": ["centre", "left", "right"]},
                },
                "required": ["text"],
            },
            # v2 sizing/fit
            "sizing_beads": {
                "type": "object",
                "description": (
                    "Optional interior sizing-bead spec for snug fit. "
                    "Fields: count (int 1–4, default 2), bead_diameter_mm (float, "
                    "default 1.0), bead_height_mm (float, default 0.4), "
                    "position_deg (float 0–360, default 270)."
                ),
                "properties": {
                    "count": {"type": "integer"},
                    "bead_diameter_mm": {"type": "number"},
                    "bead_height_mm": {"type": "number"},
                    "position_deg": {"type": "number"},
                },
            },
            "comfort_fit_radius": {
                "type": "number",
                "description": (
                    "Override for the interior dome radius (mm) when using "
                    "comfort_fit profile. If omitted the worker uses its default "
                    "(≈ 0.8 × inner_radius). Must be > 0."
                ),
            },
            "finger_fit_taper": {
                "type": "number",
                "description": (
                    "Asymmetric taper angle (degrees) to accommodate a larger "
                    "knuckle: the band is slightly wider on the knuckle side. "
                    "0 = symmetric (default). Range 0–15."
                ),
            },
            "width_profile": {
                "type": "array",
                "description": (
                    "Width taper curve from shoulder (index 0) to back of band "
                    "(last index). Each value is a ratio relative to band_width "
                    "(0 < v ≤ 1.0). Must have 2–10 elements. "
                    "Omit for uniform width (no taper)."
                ),
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 10,
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "ring_size"],
    },
)


@register(jewelry_create_ring_shank_spec, write=True)
async def run_jewelry_create_ring_shank(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    ring_size = a.get("ring_size", None)
    system = str(a.get("system", "us")).strip().lower()
    band_width = a.get("band_width", 4.0)
    thickness = a.get("thickness", 1.8)
    profile = str(a.get("profile", "comfort_fit")).strip()
    taper_ratio = a.get("taper_ratio", 1.0)
    shoulder_style = str(a.get("shoulder_style", "plain")).strip()
    node_id = str(a.get("id", "")).strip()

    # v2 profile-specific params
    hammered_facet_count = a.get("hammered_facet_count", 32)
    split_band_gap_mm = a.get("split_band_gap_mm", 1.0)
    bombe_dome_ratio = a.get("bombe_dome_ratio", 0.5)
    concave_depth_ratio = a.get("concave_depth_ratio", 0.3)
    cigar_bevel_ratio = a.get("cigar_bevel_ratio", 0.2)

    # v2 engraving
    engraving_raw = a.get("engraving", None)

    # v2 sizing/fit
    sizing_beads_raw = a.get("sizing_beads", None)
    comfort_fit_radius = a.get("comfort_fit_radius", None)
    finger_fit_taper = a.get("finger_fit_taper", 0.0)
    width_profile = a.get("width_profile", None)

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if ring_size is None:
        return err_payload("ring_size is required", "BAD_ARGS")

    if system not in _VALID_SYSTEMS:
        return err_payload(
            f"system must be one of {sorted(_VALID_SYSTEMS)}; got {system!r}",
            "BAD_ARGS",
        )
    if profile not in _VALID_PROFILES:
        return err_payload(
            f"profile must be one of {sorted(_VALID_PROFILES)}; got {profile!r}",
            "BAD_ARGS",
        )
    if shoulder_style not in _VALID_SHOULDER_STYLES:
        return err_payload(
            f"shoulder_style must be one of {sorted(_VALID_SHOULDER_STYLES)}; "
            f"got {shoulder_style!r}",
            "BAD_ARGS",
        )

    try:
        band_width = float(band_width)
        thickness = float(thickness)
        taper_ratio = float(taper_ratio)
    except (TypeError, ValueError) as e:
        return err_payload(f"band_width, thickness, taper_ratio must be numbers: {e}", "BAD_ARGS")

    if band_width <= 0:
        return err_payload(f"band_width must be > 0; got {band_width}", "BAD_ARGS")
    if thickness <= 0:
        return err_payload(f"thickness must be > 0; got {thickness}", "BAD_ARGS")
    if taper_ratio <= 0:
        return err_payload(f"taper_ratio must be > 0; got {taper_ratio}", "BAD_ARGS")

    # Parse v2 numeric params
    try:
        hammered_facet_count = int(hammered_facet_count)
        split_band_gap_mm = float(split_band_gap_mm)
        bombe_dome_ratio = float(bombe_dome_ratio)
        concave_depth_ratio = float(concave_depth_ratio)
        cigar_bevel_ratio = float(cigar_bevel_ratio)
    except (TypeError, ValueError) as e:
        return err_payload(f"v2 profile param error: {e}", "BAD_ARGS")

    # Parse comfort_fit_radius
    if comfort_fit_radius is not None:
        try:
            comfort_fit_radius = float(comfort_fit_radius)
        except (TypeError, ValueError) as e:
            return err_payload(f"comfort_fit_radius must be a number: {e}", "BAD_ARGS")
        if comfort_fit_radius <= 0:
            return err_payload(
                f"comfort_fit_radius must be > 0; got {comfort_fit_radius}", "BAD_ARGS"
            )

    # Parse finger_fit_taper
    try:
        finger_fit_taper = float(finger_fit_taper)
    except (TypeError, ValueError) as e:
        return err_payload(f"finger_fit_taper must be a number: {e}", "BAD_ARGS")

    # Parse engraving
    engraving_spec: Optional[EngravingSpec] = None
    if engraving_raw is not None:
        if not isinstance(engraving_raw, dict):
            return err_payload("engraving must be an object", "BAD_ARGS")
        eng_text = engraving_raw.get("text", "")
        if not eng_text:
            return err_payload("engraving.text is required", "BAD_ARGS")
        try:
            engraving_spec = EngravingSpec(
                text=str(eng_text),
                font_height_mm=float(engraving_raw.get("font_height_mm", 1.5)),
                depth_mm=float(engraving_raw.get("depth_mm", 0.3)),
                position_deg=float(engraving_raw.get("position_deg", 180.0)),
                align=str(engraving_raw.get("align", "centre")),
            )
            engraving_spec.validate()
        except ValueError as e:
            return err_payload(str(e), "BAD_ARGS")

    # Parse sizing beads
    sizing_beads_spec: Optional[SizingBeadSpec] = None
    if sizing_beads_raw is not None:
        if not isinstance(sizing_beads_raw, dict):
            return err_payload("sizing_beads must be an object", "BAD_ARGS")
        try:
            sizing_beads_spec = SizingBeadSpec(
                count=int(sizing_beads_raw.get("count", 2)),
                bead_diameter_mm=float(sizing_beads_raw.get("bead_diameter_mm", 1.0)),
                bead_height_mm=float(sizing_beads_raw.get("bead_height_mm", 0.4)),
                position_deg=float(sizing_beads_raw.get("position_deg", 270.0)),
            )
            # full validation (with thickness) happens inside compute_shank_params
        except (TypeError, ValueError) as e:
            return err_payload(f"sizing_beads parse error: {e}", "BAD_ARGS")

    # Validate and compute ring sizing
    try:
        shank_params = compute_shank_params(
            ring_size=ring_size,
            system=system,
            band_width=band_width,
            thickness=thickness,
            profile=profile,
            taper_ratio=taper_ratio,
            shoulder_style=shoulder_style,
            hammered_facet_count=hammered_facet_count,
            split_band_gap_mm=split_band_gap_mm,
            bombe_dome_ratio=bombe_dome_ratio,
            concave_depth_ratio=concave_depth_ratio,
            cigar_bevel_ratio=cigar_bevel_ratio,
            engraving=engraving_spec,
            sizing_beads=sizing_beads_spec,
            comfort_fit_radius=comfort_fit_radius,
            finger_fit_taper=finger_fit_taper,
            width_profile=width_profile,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    # Load feature file
    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    try:
        row = ctx.pool.fetchone(
            "select content, kind from files where id = $1 and project_id = $2 "
            "and deleted_at is null",
            fid, ctx.project_id,
        )
        if not row:
            return err_payload(f"file {file_id_str} not found", "NOT_FOUND")
        content, kind = row[0], row[1]
        if kind != "feature":
            return err_payload(f"file {file_id_str} is not a feature file", "NOT_FOUND")
    except Exception as e:
        return err_payload(str(e), "ERROR")

    if not node_id:
        node_id = _next_ring_shank_id(content or "")

    node = {
        "id": node_id,
        "op": "ring_shank",
        **shank_params,
    }

    # Append node to feature document
    doc: dict
    if content and content.strip():
        try:
            doc = json.loads(content)
        except Exception:
            doc = {"version": 1, "features": []}
    else:
        doc = {"version": 1, "features": []}

    if "version" not in doc:
        doc["version"] = 1
    if "features" not in doc or not isinstance(doc["features"], list):
        doc["features"] = []

    doc["features"].append(node)

    try:
        body = json.dumps(doc, indent=2)
    except Exception as e:
        return err_payload(f"encode: {e}", "ERROR")

    try:
        ctx.pool.execute(
            "update files set content = $1, updated_at = now() "
            "where id = $2 and project_id = $3",
            body, fid, ctx.project_id,
        )
    except Exception as e:
        return err_payload(str(e), "ERROR")

    return ok_payload({
        "file_id": file_id_str,
        "id": node_id,
        "op": "ring_shank",
        "inner_diameter_mm": shank_params["inner_diameter_mm"],
        "outer_diameter_mm": shank_params["outer_diameter_mm"],
        "circumference_mm": shank_params["circumference_mm"],
        "profile": profile,
        "shoulder_style": shoulder_style,
        "band_width_mm": band_width,
        "thickness_mm": thickness,
    })
