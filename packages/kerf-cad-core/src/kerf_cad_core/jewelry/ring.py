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
    jewelry_create_eternity_band
    jewelry_create_signet_ring
    jewelry_create_stacking_band_set
    jewelry_create_contoured_band
    jewelry_create_solitaire_ring
    jewelry_create_mens_band
    jewelry_create_wedding_set
    jewelry_create_cocktail_ring
    jewelry_create_bypass_ring

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

New ring types (v3)
-------------------
    eternity_band  — full/half/three-quarter circle stone channel; EternityBandSpec
    signet_ring    — flat/oval/cushion engravable seal face; SignetRingSpec
    stacking_band_set — set of N thin stacking bands + optional wishbone; StackingBandSpec
    contoured_band — band with curved/notched top to hug an engagement ring; ContouredBandSpec

New ring types (v4) — composite / style builders
-------------------------------------------------
    solitaire_ring  — shank + centre-stone attach-point hint; SolitaireRingSpec
    mens_band       — wide comfort/euro/bevel band + groove/milgrain/surface hints; MensBandSpec
    wedding_set     — engagement ring + matched contoured band, paired; WeddingSetSpec
    cocktail_ring   — tapered shank + large dome/cluster mount attach-point; CocktailRingSpec
    bypass_ring     — two-arm crossover / toi-et-moi with two stone attach-points; BypassRingSpec

Attach-point hint schema (v4)
------------------------------
Each composite ring builder emits an ``attach_points`` list.  Each entry:

    {
      "type": "circular_seat" | "toi_et_moi",
      "position_deg": float,          # 0 = 12-o'clock, clockwise from above
      "height_mm": float,             # above bore centre-plane
      "diameter_mm": float,           # seat opening (= stone diameter)
      "normal": [0, 0, 1],            # shank-axis-aligned unit normal
      # bypass arms also carry:
      "arm": "A" | "B",
      "lateral_offset_mm": float,     # ± from centreline
      # cocktail also carries:
      "mount_style": str,
      "mount_diameter_mm": float,
    }
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


# ===========================================================================
# v3 Ring Types
# ===========================================================================

# ---------------------------------------------------------------------------
# Constants for v3 types
# ---------------------------------------------------------------------------

_VALID_ETERNITY_COVERAGES = frozenset(["full", "half", "three_quarter"])
_VALID_ETERNITY_SETTINGS = frozenset(["channel", "shared_prong", "pave"])
_VALID_SIGNET_FACE_SHAPES = frozenset(["flat", "oval", "cushion"])
_VALID_STACKING_PROFILES = frozenset([
    "flat", "half_round", "knife_edge", "euro", "comfort_fit",
    "d_shape", "cigar_band", "concave",
])


# ---------------------------------------------------------------------------
# v3 spec dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EternityBandSpec:
    """Parametric eternity / anniversary band descriptor.

    Describes a full-circle (or half / three-quarter) band set with equal
    stones around the circumference in channel, shared-prong, or pavé style.
    This is a geometry hint; the occtWorker resolves actual stone-seat geometry.

    Fields
    ------
    ring_size : int | float | str
        Size in the given system.
    system : str
        Ring-size standard ("us", "uk", "au", "eu", "jp").
    stone_diameter_mm : float
        Diameter of each stone, mm.  > 0.
    coverage : str
        Arc coverage: "full" (360°), "half" (180°), "three_quarter" (270°).
    stone_count : int | None
        Number of stones.  If None (default) the count is auto-derived from
        the inner circumference and stone pitch.  Must be ≥ 1 if specified.
    setting_style : str
        Geometry hint for the stone setting style: "channel", "shared_prong",
        or "pave".  Consumed by the occtWorker; does not affect stone_count math.
    band_width_mm : float
        Band width along the finger axis, mm.  Defaults to stone_diameter_mm
        + 0.6 mm (seat walls).  Must be ≥ stone_diameter_mm.
    thickness_mm : float
        Radial wall thickness below the stone seats, mm.  > 0.
    stone_spacing_mm : float
        Edge-to-edge gap between adjacent stones, mm.  ≥ 0.
        Default 0.1 mm (minimal; channel / shared-prong standard).
    """
    ring_size: object  # int | float | str
    system: str = "us"
    stone_diameter_mm: float = 2.0
    coverage: str = "full"
    stone_count: Optional[int] = None
    setting_style: str = "channel"
    band_width_mm: Optional[float] = None   # None → auto (stone_diam + 0.6)
    thickness_mm: float = 1.2
    stone_spacing_mm: float = 0.1

    def _resolve_band_width(self) -> float:
        if self.band_width_mm is not None:
            return self.band_width_mm
        return round(self.stone_diameter_mm + 0.6, 3)

    def auto_stone_count(self, inner_diameter_mm: float) -> int:
        """Derive stone count from circumference when stone_count is None.

        Uses the stone pitch (diameter + spacing) and the arc length that
        corresponds to ``coverage``.

        Returns
        -------
        int
            Derived stone count, ≥ 1.
        """
        coverage_fraction = {
            "full": 1.0,
            "three_quarter": 0.75,
            "half": 0.5,
        }[self.coverage]
        arc_length = _PI * inner_diameter_mm * coverage_fraction
        pitch = self.stone_diameter_mm + self.stone_spacing_mm
        count = max(1, round(arc_length / pitch))
        return count

    def validate(self, inner_diameter_mm: float) -> None:
        if self.stone_diameter_mm <= 0:
            raise ValueError(
                f"eternity.stone_diameter_mm must be > 0; got {self.stone_diameter_mm}"
            )
        if self.coverage not in _VALID_ETERNITY_COVERAGES:
            raise ValueError(
                f"eternity.coverage must be one of {sorted(_VALID_ETERNITY_COVERAGES)}; "
                f"got {self.coverage!r}"
            )
        if self.setting_style not in _VALID_ETERNITY_SETTINGS:
            raise ValueError(
                f"eternity.setting_style must be one of "
                f"{sorted(_VALID_ETERNITY_SETTINGS)}; got {self.setting_style!r}"
            )
        bw = self._resolve_band_width()
        if bw < self.stone_diameter_mm:
            raise ValueError(
                f"eternity.band_width_mm ({bw}) must be ≥ stone_diameter_mm "
                f"({self.stone_diameter_mm})"
            )
        if self.thickness_mm <= 0:
            raise ValueError(
                f"eternity.thickness_mm must be > 0; got {self.thickness_mm}"
            )
        if self.stone_spacing_mm < 0:
            raise ValueError(
                f"eternity.stone_spacing_mm must be ≥ 0; got {self.stone_spacing_mm}"
            )
        if self.stone_count is not None:
            if self.stone_count < 1:
                raise ValueError(
                    f"eternity.stone_count must be ≥ 1; got {self.stone_count}"
                )
        if inner_diameter_mm <= 0:
            raise ValueError(
                f"inner_diameter_mm must be > 0; got {inner_diameter_mm}"
            )

    def to_dict(self, inner_diameter_mm: float) -> dict:
        self.validate(inner_diameter_mm)
        bw = self._resolve_band_width()
        if self.stone_count is not None:
            sc = self.stone_count
        else:
            sc = self.auto_stone_count(inner_diameter_mm)
        coverage_deg = {
            "full": 360.0,
            "three_quarter": 270.0,
            "half": 180.0,
        }[self.coverage]
        arc_length = _PI * inner_diameter_mm * coverage_deg / 360.0
        pitch = self.stone_diameter_mm + self.stone_spacing_mm
        return {
            "stone_diameter_mm": self.stone_diameter_mm,
            "coverage": self.coverage,
            "coverage_deg": coverage_deg,
            "stone_count": sc,
            "stone_count_auto": self.stone_count is None,
            "setting_style": self.setting_style,
            "band_width_mm": round(bw, 4),
            "thickness_mm": self.thickness_mm,
            "stone_spacing_mm": self.stone_spacing_mm,
            "stone_pitch_mm": round(pitch, 4),
            "arc_length_mm": round(arc_length, 4),
        }


@dataclass
class SignetRingSpec:
    """Parametric signet ring descriptor.

    Describes a flat/oval/cushion engravable seal face fused to the ring shank.
    Engraving depth is a geometry hint consumed by the occtWorker.

    Fields
    ------
    ring_size : int | float | str
        Size in the given system.
    system : str
        Ring-size standard.
    face_shape : str
        Shape of the seal face: "flat", "oval", or "cushion".
    face_length_mm : float
        Length of the seal face (finger-axis direction), mm.  > 0.
    face_width_mm : float
        Width of the seal face (across the finger), mm.  > 0.
    face_height_mm : float
        Height (thickness) of the seal face above the shank, mm.  > 0.
    intaglio_depth_mm : float
        Depth of the intaglio / relief engraving cut into the seal face.
        0 = no engraving.  ≥ 0; must be < face_height_mm.
    engraving : EngravingSpec | None
        Optional text engraving on the seal face (same convention as shank
        engraving; geometry hint only).
    band_width_mm : float
        Shank band width, mm.  Default 4.0.
    thickness_mm : float
        Shank wall thickness, mm.  Default 1.8.
    shoulder_style : str
        Shank shoulder style (plain / cathedral / split_shank / bypass).
    """
    ring_size: object
    system: str = "us"
    face_shape: str = "oval"
    face_length_mm: float = 12.0
    face_width_mm: float = 10.0
    face_height_mm: float = 3.0
    intaglio_depth_mm: float = 0.0
    engraving: Optional[EngravingSpec] = None
    band_width_mm: float = 4.0
    thickness_mm: float = 1.8
    shoulder_style: str = "plain"

    def validate(self) -> None:
        if self.face_shape not in _VALID_SIGNET_FACE_SHAPES:
            raise ValueError(
                f"signet.face_shape must be one of "
                f"{sorted(_VALID_SIGNET_FACE_SHAPES)}; got {self.face_shape!r}"
            )
        if self.face_length_mm <= 0:
            raise ValueError(
                f"signet.face_length_mm must be > 0; got {self.face_length_mm}"
            )
        if self.face_width_mm <= 0:
            raise ValueError(
                f"signet.face_width_mm must be > 0; got {self.face_width_mm}"
            )
        if self.face_height_mm <= 0:
            raise ValueError(
                f"signet.face_height_mm must be > 0; got {self.face_height_mm}"
            )
        if self.intaglio_depth_mm < 0:
            raise ValueError(
                f"signet.intaglio_depth_mm must be ≥ 0; got {self.intaglio_depth_mm}"
            )
        if self.intaglio_depth_mm >= self.face_height_mm:
            raise ValueError(
                f"signet.intaglio_depth_mm ({self.intaglio_depth_mm}) must be < "
                f"face_height_mm ({self.face_height_mm})"
            )
        if self.band_width_mm <= 0:
            raise ValueError(
                f"signet.band_width_mm must be > 0; got {self.band_width_mm}"
            )
        if self.thickness_mm <= 0:
            raise ValueError(
                f"signet.thickness_mm must be > 0; got {self.thickness_mm}"
            )
        if self.shoulder_style not in _VALID_SHOULDER_STYLES:
            raise ValueError(
                f"signet.shoulder_style must be one of "
                f"{sorted(_VALID_SHOULDER_STYLES)}; got {self.shoulder_style!r}"
            )
        if self.engraving is not None:
            self.engraving.validate()

    def to_dict(self, inner_diameter_mm: float) -> dict:
        self.validate()
        result: dict = {
            "face_shape": self.face_shape,
            "face_length_mm": self.face_length_mm,
            "face_width_mm": self.face_width_mm,
            "face_height_mm": self.face_height_mm,
            "face_area_mm2": round(self._face_area(), 4),
            "intaglio_depth_mm": self.intaglio_depth_mm,
            "band_width_mm": self.band_width_mm,
            "thickness_mm": self.thickness_mm,
            "shoulder_style": self.shoulder_style,
        }
        if self.engraving is not None:
            result["engraving"] = self.engraving.to_dict()
        return result

    def _face_area(self) -> float:
        """Approximate seal-face area in mm² (for metal-cost hints)."""
        if self.face_shape == "flat":
            return self.face_length_mm * self.face_width_mm
        elif self.face_shape == "oval":
            return _PI * (self.face_length_mm / 2.0) * (self.face_width_mm / 2.0)
        else:  # cushion — approximate as rounded rectangle (90% of bounding box)
            return self.face_length_mm * self.face_width_mm * 0.9


@dataclass
class StackingBandSpec:
    """Parametric stacking / nesting band-set descriptor.

    Describes a set of N thin stacking bands that sit side-by-side on the
    finger.  Optionally includes a contour / wishbone band that nests against
    a named solitaire's shank profile.

    Fields
    ------
    ring_size : int | float | str
        Size in the given system.
    system : str
        Ring-size standard.
    band_count : int
        Number of bands in the set.  1–8.
    band_width_mm : float
        Width of each band along the finger axis, mm.  > 0.
    thickness_mm : float
        Radial wall thickness of each band, mm.  > 0.
    profile : str
        Cross-section profile shared by all bands in the set.
        Subset of the main profile set (flat, half_round, knife_edge, euro,
        comfort_fit, d_shape, cigar_band, concave).
    nest_gap_mm : float
        Gap between adjacent bands when stacked, mm.  ≥ 0.  Default 0.1 mm.
    include_wishbone : bool
        Whether to include a contour/wishbone band designed to nest against
        an engagement ring.  Default False.
    wishbone_notch_depth_mm : float
        Depth of the notch cut into the top of the wishbone band, mm.
        Only meaningful when include_wishbone=True.  > 0 when set.
    solitaire_node_id : str | None
        Optional node ID of the solitaire ring_shank whose profile the
        wishbone band should match.  Geometry hint only.
    per_band_profiles : list[str] | None
        Optional per-band profile override list (len must equal band_count).
        None = all bands use the ``profile`` field.
    """
    ring_size: object
    system: str = "us"
    band_count: int = 3
    band_width_mm: float = 2.0
    thickness_mm: float = 1.4
    profile: str = "flat"
    nest_gap_mm: float = 0.1
    include_wishbone: bool = False
    wishbone_notch_depth_mm: float = 0.8
    solitaire_node_id: Optional[str] = None
    per_band_profiles: Optional[List[str]] = None

    def validate(self) -> None:
        if not (1 <= self.band_count <= 8):
            raise ValueError(
                f"stacking.band_count must be 1–8; got {self.band_count}"
            )
        if self.band_width_mm <= 0:
            raise ValueError(
                f"stacking.band_width_mm must be > 0; got {self.band_width_mm}"
            )
        if self.thickness_mm <= 0:
            raise ValueError(
                f"stacking.thickness_mm must be > 0; got {self.thickness_mm}"
            )
        if self.profile not in _VALID_STACKING_PROFILES:
            raise ValueError(
                f"stacking.profile must be one of "
                f"{sorted(_VALID_STACKING_PROFILES)}; got {self.profile!r}"
            )
        if self.nest_gap_mm < 0:
            raise ValueError(
                f"stacking.nest_gap_mm must be ≥ 0; got {self.nest_gap_mm}"
            )
        if self.include_wishbone:
            if self.wishbone_notch_depth_mm <= 0:
                raise ValueError(
                    f"stacking.wishbone_notch_depth_mm must be > 0 when "
                    f"include_wishbone is True; got {self.wishbone_notch_depth_mm}"
                )
            if self.wishbone_notch_depth_mm >= self.thickness_mm:
                raise ValueError(
                    f"stacking.wishbone_notch_depth_mm ({self.wishbone_notch_depth_mm}) "
                    f"must be < thickness_mm ({self.thickness_mm})"
                )
        if self.per_band_profiles is not None:
            if len(self.per_band_profiles) != self.band_count:
                raise ValueError(
                    f"stacking.per_band_profiles length ({len(self.per_band_profiles)}) "
                    f"must equal band_count ({self.band_count})"
                )
            for i, p in enumerate(self.per_band_profiles):
                if p not in _VALID_STACKING_PROFILES:
                    raise ValueError(
                        f"stacking.per_band_profiles[{i}] must be one of "
                        f"{sorted(_VALID_STACKING_PROFILES)}; got {p!r}"
                    )

    def to_dict(self, inner_diameter_mm: float) -> dict:
        self.validate()
        pitch = self.band_width_mm + self.nest_gap_mm
        total_span = pitch * self.band_count - self.nest_gap_mm
        bands = []
        profiles = (
            self.per_band_profiles
            if self.per_band_profiles is not None
            else [self.profile] * self.band_count
        )
        for i in range(self.band_count):
            bands.append({
                "index": i,
                "profile": profiles[i],
                "band_width_mm": self.band_width_mm,
                "thickness_mm": self.thickness_mm,
                "offset_mm": round(i * pitch, 4),
            })
        result: dict = {
            "band_count": self.band_count,
            "band_width_mm": self.band_width_mm,
            "thickness_mm": self.thickness_mm,
            "profile": self.profile,
            "nest_gap_mm": self.nest_gap_mm,
            "total_span_mm": round(total_span, 4),
            "bands": bands,
            "include_wishbone": self.include_wishbone,
        }
        if self.include_wishbone:
            result["wishbone_notch_depth_mm"] = self.wishbone_notch_depth_mm
        if self.solitaire_node_id:
            result["solitaire_node_id"] = self.solitaire_node_id
        if self.per_band_profiles is not None:
            result["per_band_profiles"] = self.per_band_profiles
        return result


@dataclass
class ContouredBandSpec:
    """Parametric contoured / shadow band descriptor.

    A wedding / shadow band whose top profile is cut to hug the underside
    of an engagement ring (curved or notched top).  The contour lets the
    two rings sit flush against each other on the finger.

    Fields
    ------
    ring_size : int | float | str
        Size in the given system.
    system : str
        Ring-size standard.
    notch_depth_mm : float
        Depth of the top-centre notch / curve cut, mm.  > 0.
    notch_width_mm : float
        Width of the notch across the band, mm.  > 0; must be ≤ band_width_mm.
    match_radius_mm : float
        Radius of the concave curve that mirrors the engagement ring's profile,
        mm.  > 0.  Should match the engagement ring's outer radius (≈ outer
        diameter / 2) for a perfect shadow fit.
    contour_style : str
        "curved" — smooth concave arc cut across the top face.
        "notched" — V or U notch cut into the centre of the top face.
    band_width_mm : float
        Band width along the finger axis, mm.  > 0.
    thickness_mm : float
        Radial wall thickness, mm.  > 0.
    profile : str
        Cross-section profile for the lower (shank) portion of the band.
        Valid: flat, half_round, comfort_fit, d_shape, euro.  Default "flat".
    shoulder_style : str
        Shank shoulder style.  Default "plain".
    engagement_ring_node_id : str | None
        Optional node ID of the engagement ring this band is contoured to.
        Geometry hint only; occtWorker uses match_radius_mm regardless.
    """
    ring_size: object
    system: str = "us"
    notch_depth_mm: float = 1.2
    notch_width_mm: float = 3.0
    match_radius_mm: float = 10.5
    contour_style: str = "curved"
    band_width_mm: float = 3.5
    thickness_mm: float = 1.6
    profile: str = "flat"
    shoulder_style: str = "plain"
    engagement_ring_node_id: Optional[str] = None

    _VALID_CONTOUR_STYLES = frozenset(["curved", "notched"])
    _VALID_CONTOUR_BASE_PROFILES = frozenset([
        "flat", "half_round", "comfort_fit", "d_shape", "euro",
    ])

    def validate(self) -> None:
        if self.notch_depth_mm <= 0:
            raise ValueError(
                f"contoured.notch_depth_mm must be > 0; got {self.notch_depth_mm}"
            )
        if self.notch_width_mm <= 0:
            raise ValueError(
                f"contoured.notch_width_mm must be > 0; got {self.notch_width_mm}"
            )
        if self.notch_width_mm > self.band_width_mm:
            raise ValueError(
                f"contoured.notch_width_mm ({self.notch_width_mm}) must be ≤ "
                f"band_width_mm ({self.band_width_mm})"
            )
        if self.match_radius_mm <= 0:
            raise ValueError(
                f"contoured.match_radius_mm must be > 0; got {self.match_radius_mm}"
            )
        if self.contour_style not in self._VALID_CONTOUR_STYLES:
            raise ValueError(
                f"contoured.contour_style must be one of "
                f"{sorted(self._VALID_CONTOUR_STYLES)}; got {self.contour_style!r}"
            )
        if self.band_width_mm <= 0:
            raise ValueError(
                f"contoured.band_width_mm must be > 0; got {self.band_width_mm}"
            )
        if self.thickness_mm <= 0:
            raise ValueError(
                f"contoured.thickness_mm must be > 0; got {self.thickness_mm}"
            )
        if self.notch_depth_mm >= self.thickness_mm:
            raise ValueError(
                f"contoured.notch_depth_mm ({self.notch_depth_mm}) must be < "
                f"thickness_mm ({self.thickness_mm})"
            )
        if self.profile not in self._VALID_CONTOUR_BASE_PROFILES:
            raise ValueError(
                f"contoured.profile must be one of "
                f"{sorted(self._VALID_CONTOUR_BASE_PROFILES)}; got {self.profile!r}"
            )
        if self.shoulder_style not in _VALID_SHOULDER_STYLES:
            raise ValueError(
                f"contoured.shoulder_style must be one of "
                f"{sorted(_VALID_SHOULDER_STYLES)}; got {self.shoulder_style!r}"
            )

    def to_dict(self, inner_diameter_mm: float) -> dict:
        self.validate()
        outer_diameter_mm = inner_diameter_mm + 2 * self.thickness_mm
        result: dict = {
            "notch_depth_mm": self.notch_depth_mm,
            "notch_width_mm": self.notch_width_mm,
            "match_radius_mm": self.match_radius_mm,
            "contour_style": self.contour_style,
            "band_width_mm": self.band_width_mm,
            "thickness_mm": self.thickness_mm,
            "profile": self.profile,
            "shoulder_style": self.shoulder_style,
            "inner_diameter_mm": round(inner_diameter_mm, 4),
            "outer_diameter_mm": round(outer_diameter_mm, 4),
            "contour_hints": {
                "type": self.contour_style,
                "notch_depth_mm": self.notch_depth_mm,
                "notch_width_mm": self.notch_width_mm,
                "match_radius_mm": self.match_radius_mm,
                # Clearance angle: half-angle of the notch span at match radius
                "notch_half_angle_deg": round(
                    math.degrees(
                        math.asin(min(1.0, (self.notch_width_mm / 2.0) / self.match_radius_mm))
                    ), 4
                ),
            },
        }
        if self.engagement_ring_node_id:
            result["engagement_ring_node_id"] = self.engagement_ring_node_id
        return result


# ---------------------------------------------------------------------------
# v3 compute functions
# ---------------------------------------------------------------------------

def compute_eternity_band_params(
    ring_size,
    system: str = "us",
    stone_diameter_mm: float = 2.0,
    coverage: str = "full",
    stone_count: Optional[int] = None,
    setting_style: str = "channel",
    band_width_mm: Optional[float] = None,
    thickness_mm: float = 1.2,
    stone_spacing_mm: float = 0.1,
) -> dict:
    """Compute validated eternity band descriptor.

    Returns a dict suitable for embedding in a feature JSON node
    (op = ``eternity_band``).

    Raises
    ------
    ValueError
        On any constraint violation.
    """
    id_mm = ring_size_to_diameter(system, ring_size)
    circ_mm = _id_mm_to_circumference(id_mm)

    spec = EternityBandSpec(
        ring_size=ring_size,
        system=system,
        stone_diameter_mm=float(stone_diameter_mm),
        coverage=str(coverage),
        stone_count=int(stone_count) if stone_count is not None else None,
        setting_style=str(setting_style),
        band_width_mm=float(band_width_mm) if band_width_mm is not None else None,
        thickness_mm=float(thickness_mm),
        stone_spacing_mm=float(stone_spacing_mm),
    )
    # validate raises if bad
    spec.validate(id_mm)
    stone_dict = spec.to_dict(id_mm)

    return {
        "inner_diameter_mm": round(id_mm, 4),
        "outer_diameter_mm": round(id_mm + 2 * thickness_mm, 4),
        "circumference_mm": round(circ_mm, 4),
        "size_system": system,
        "ring_size": ring_size,
        **stone_dict,
    }


def compute_signet_ring_params(
    ring_size,
    system: str = "us",
    face_shape: str = "oval",
    face_length_mm: float = 12.0,
    face_width_mm: float = 10.0,
    face_height_mm: float = 3.0,
    intaglio_depth_mm: float = 0.0,
    engraving: Optional[EngravingSpec] = None,
    band_width_mm: float = 4.0,
    thickness_mm: float = 1.8,
    shoulder_style: str = "plain",
) -> dict:
    """Compute validated signet ring descriptor.

    Returns a dict suitable for embedding in a feature JSON node
    (op = ``signet_ring``).
    """
    id_mm = ring_size_to_diameter(system, ring_size)
    circ_mm = _id_mm_to_circumference(id_mm)

    spec = SignetRingSpec(
        ring_size=ring_size,
        system=system,
        face_shape=str(face_shape),
        face_length_mm=float(face_length_mm),
        face_width_mm=float(face_width_mm),
        face_height_mm=float(face_height_mm),
        intaglio_depth_mm=float(intaglio_depth_mm),
        engraving=engraving,
        band_width_mm=float(band_width_mm),
        thickness_mm=float(thickness_mm),
        shoulder_style=str(shoulder_style),
    )
    spec.validate()
    face_dict = spec.to_dict(id_mm)
    shoulder_hints = _shoulder_hints(shoulder_style, id_mm, band_width_mm)

    return {
        "inner_diameter_mm": round(id_mm, 4),
        "outer_diameter_mm": round(id_mm + 2 * thickness_mm, 4),
        "circumference_mm": round(circ_mm, 4),
        "size_system": system,
        "ring_size": ring_size,
        "shoulder_hints": shoulder_hints,
        **face_dict,
    }


def compute_stacking_band_params(
    ring_size,
    system: str = "us",
    band_count: int = 3,
    band_width_mm: float = 2.0,
    thickness_mm: float = 1.4,
    profile: str = "flat",
    nest_gap_mm: float = 0.1,
    include_wishbone: bool = False,
    wishbone_notch_depth_mm: float = 0.8,
    solitaire_node_id: Optional[str] = None,
    per_band_profiles: Optional[List[str]] = None,
) -> dict:
    """Compute validated stacking band set descriptor.

    Returns a dict suitable for embedding in a feature JSON node
    (op = ``stacking_band_set``).
    """
    id_mm = ring_size_to_diameter(system, ring_size)
    circ_mm = _id_mm_to_circumference(id_mm)

    spec = StackingBandSpec(
        ring_size=ring_size,
        system=system,
        band_count=int(band_count),
        band_width_mm=float(band_width_mm),
        thickness_mm=float(thickness_mm),
        profile=str(profile),
        nest_gap_mm=float(nest_gap_mm),
        include_wishbone=bool(include_wishbone),
        wishbone_notch_depth_mm=float(wishbone_notch_depth_mm),
        solitaire_node_id=solitaire_node_id,
        per_band_profiles=per_band_profiles,
    )
    spec.validate()
    stack_dict = spec.to_dict(id_mm)

    return {
        "inner_diameter_mm": round(id_mm, 4),
        "outer_diameter_mm": round(id_mm + 2 * thickness_mm, 4),
        "circumference_mm": round(circ_mm, 4),
        "size_system": system,
        "ring_size": ring_size,
        **stack_dict,
    }


def compute_contoured_band_params(
    ring_size,
    system: str = "us",
    notch_depth_mm: float = 1.2,
    notch_width_mm: float = 3.0,
    match_radius_mm: float = 10.5,
    contour_style: str = "curved",
    band_width_mm: float = 3.5,
    thickness_mm: float = 1.6,
    profile: str = "flat",
    shoulder_style: str = "plain",
    engagement_ring_node_id: Optional[str] = None,
) -> dict:
    """Compute validated contoured / shadow band descriptor.

    Returns a dict suitable for embedding in a feature JSON node
    (op = ``contoured_band``).
    """
    id_mm = ring_size_to_diameter(system, ring_size)
    circ_mm = _id_mm_to_circumference(id_mm)

    spec = ContouredBandSpec(
        ring_size=ring_size,
        system=system,
        notch_depth_mm=float(notch_depth_mm),
        notch_width_mm=float(notch_width_mm),
        match_radius_mm=float(match_radius_mm),
        contour_style=str(contour_style),
        band_width_mm=float(band_width_mm),
        thickness_mm=float(thickness_mm),
        profile=str(profile),
        shoulder_style=str(shoulder_style),
        engagement_ring_node_id=engagement_ring_node_id,
    )
    spec.validate()
    contour_dict = spec.to_dict(id_mm)
    shoulder_hints = _shoulder_hints(shoulder_style, id_mm, band_width_mm)

    result = {
        "size_system": system,
        "ring_size": ring_size,
        "circumference_mm": round(circ_mm, 4),
        "shoulder_hints": shoulder_hints,
        **contour_dict,
    }
    return result


# ---------------------------------------------------------------------------
# v3 node ID helpers
# ---------------------------------------------------------------------------

def _next_op_id(content: str, op: str) -> str:
    """Generate a unique node id for the given op prefix."""
    try:
        doc = json.loads(content)
        features = doc.get("features", [])
        prefix = f"{op}-"
        max_n = 0
        for item in features:
            nid = item.get("id", "")
            if nid.startswith(prefix):
                try:
                    n = int(nid[len(prefix):])
                    max_n = max(max_n, n)
                except ValueError:
                    pass
        return f"{prefix}{max_n + 1}"
    except Exception:
        return f"{op}-1"


def _load_feature_doc(content: str) -> dict:
    """Parse or initialise a feature document."""
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
    return doc


def _fetch_feature_file(ctx: ProjectCtx, fid):
    """Fetch content from the pool; return (content, error_str)."""
    try:
        row = ctx.pool.fetchone(
            "select content, kind from files where id = $1 and project_id = $2 "
            "and deleted_at is null",
            fid, ctx.project_id,
        )
        if not row:
            return None, f"file {fid} not found"
        content, kind = row[0], row[1]
        if kind != "feature":
            return None, f"file {fid} is not a feature file"
        return content, None
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_eternity_band
# ---------------------------------------------------------------------------

jewelry_create_eternity_band_spec = ToolSpec(
    name="jewelry_create_eternity_band",
    description=(
        "Append an `eternity_band` node to a `.feature` file. "
        "Builds a parametric full-circle (or half / three-quarter) eternity / "
        "anniversary band set with equal stones around the band in channel, "
        "shared-prong, or pavé style. "
        "Stone count is auto-derived from ring circumference and stone diameter "
        "unless stone_count is specified explicitly. "
        "All dimensions in mm. Ring size is auto-converted to inner diameter."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "ring_size": {
                "description": "Size in the chosen system.",
            },
            "system": {
                "type": "string",
                "enum": ["us", "uk", "au", "eu", "jp"],
                "description": "Ring-size standard. Default 'us'.",
            },
            "stone_diameter_mm": {
                "type": "number",
                "description": "Diameter of each stone, mm. > 0. Default 2.0.",
            },
            "coverage": {
                "type": "string",
                "enum": ["full", "half", "three_quarter"],
                "description": (
                    "Arc coverage of stones around the band. "
                    "'full' = 360°, 'half' = 180°, 'three_quarter' = 270°. "
                    "Default 'full'."
                ),
            },
            "stone_count": {
                "type": "integer",
                "description": (
                    "Explicit number of stones. If omitted, auto-derived from "
                    "circumference and stone pitch. Must be ≥ 1."
                ),
            },
            "setting_style": {
                "type": "string",
                "enum": ["channel", "shared_prong", "pave"],
                "description": (
                    "Stone setting style (geometry hint for occtWorker). "
                    "Default 'channel'."
                ),
            },
            "band_width_mm": {
                "type": "number",
                "description": (
                    "Band width along finger axis, mm. "
                    "Default = stone_diameter_mm + 0.6 mm. "
                    "Must be ≥ stone_diameter_mm."
                ),
            },
            "thickness_mm": {
                "type": "number",
                "description": "Radial wall thickness below stone seats, mm. > 0. Default 1.2.",
            },
            "stone_spacing_mm": {
                "type": "number",
                "description": (
                    "Edge-to-edge gap between adjacent stones, mm. ≥ 0. "
                    "Default 0.1 mm."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "ring_size"],
    },
)


@register(jewelry_create_eternity_band_spec, write=True)
async def run_jewelry_create_eternity_band(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    ring_size = a.get("ring_size", None)
    system = str(a.get("system", "us")).strip().lower()
    stone_diameter_mm = a.get("stone_diameter_mm", 2.0)
    coverage = str(a.get("coverage", "full")).strip()
    stone_count = a.get("stone_count", None)
    setting_style = str(a.get("setting_style", "channel")).strip()
    band_width_mm = a.get("band_width_mm", None)
    thickness_mm = a.get("thickness_mm", 1.2)
    stone_spacing_mm = a.get("stone_spacing_mm", 0.1)
    node_id = str(a.get("id", "")).strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if ring_size is None:
        return err_payload("ring_size is required", "BAD_ARGS")
    if system not in _VALID_SYSTEMS:
        return err_payload(
            f"system must be one of {sorted(_VALID_SYSTEMS)}; got {system!r}",
            "BAD_ARGS",
        )
    if coverage not in _VALID_ETERNITY_COVERAGES:
        return err_payload(
            f"coverage must be one of {sorted(_VALID_ETERNITY_COVERAGES)}; "
            f"got {coverage!r}", "BAD_ARGS",
        )
    if setting_style not in _VALID_ETERNITY_SETTINGS:
        return err_payload(
            f"setting_style must be one of {sorted(_VALID_ETERNITY_SETTINGS)}; "
            f"got {setting_style!r}", "BAD_ARGS",
        )

    try:
        stone_diameter_mm = float(stone_diameter_mm)
        thickness_mm = float(thickness_mm)
        stone_spacing_mm = float(stone_spacing_mm)
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric param error: {e}", "BAD_ARGS")

    if stone_count is not None:
        try:
            stone_count = int(stone_count)
        except (TypeError, ValueError) as e:
            return err_payload(f"stone_count must be an integer: {e}", "BAD_ARGS")

    if band_width_mm is not None:
        try:
            band_width_mm = float(band_width_mm)
        except (TypeError, ValueError) as e:
            return err_payload(f"band_width_mm must be a number: {e}", "BAD_ARGS")

    try:
        params = compute_eternity_band_params(
            ring_size=ring_size,
            system=system,
            stone_diameter_mm=stone_diameter_mm,
            coverage=coverage,
            stone_count=stone_count,
            setting_style=setting_style,
            band_width_mm=band_width_mm,
            thickness_mm=thickness_mm,
            stone_spacing_mm=stone_spacing_mm,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = _fetch_feature_file(ctx, fid)
    if err:
        code = "NOT_FOUND" if "not found" in err or "not a feature" in err else "ERROR"
        return err_payload(err, code)

    if not node_id:
        node_id = _next_op_id(content or "", "eternity_band")

    node = {"id": node_id, "op": "eternity_band", **params}
    doc = _load_feature_doc(content or "")
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
        "op": "eternity_band",
        "inner_diameter_mm": params["inner_diameter_mm"],
        "stone_count": params["stone_count"],
        "stone_diameter_mm": params["stone_diameter_mm"],
        "coverage": params["coverage"],
        "setting_style": params["setting_style"],
        "band_width_mm": params["band_width_mm"],
        "thickness_mm": params["thickness_mm"],
    })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_signet_ring
# ---------------------------------------------------------------------------

jewelry_create_signet_ring_spec = ToolSpec(
    name="jewelry_create_signet_ring",
    description=(
        "Append a `signet_ring` node to a `.feature` file. "
        "Builds a parametric signet ring with a flat, oval, or cushion "
        "engravable seal face fused to the shank. "
        "Optional intaglio/relief engraving depth is a geometry hint consumed "
        "by the occtWorker. The engraving field (text/font) follows the same "
        "convention as the ring_shank engraving field. "
        "All dimensions in mm. Ring size is auto-converted to inner diameter."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "ring_size": {
                "description": "Size in the chosen system.",
            },
            "system": {
                "type": "string",
                "enum": ["us", "uk", "au", "eu", "jp"],
                "description": "Ring-size standard. Default 'us'.",
            },
            "face_shape": {
                "type": "string",
                "enum": ["flat", "oval", "cushion"],
                "description": "Shape of the seal face. Default 'oval'.",
            },
            "face_length_mm": {
                "type": "number",
                "description": "Seal face length (finger-axis direction), mm. > 0. Default 12.0.",
            },
            "face_width_mm": {
                "type": "number",
                "description": "Seal face width (across finger), mm. > 0. Default 10.0.",
            },
            "face_height_mm": {
                "type": "number",
                "description": "Seal face height above shank, mm. > 0. Default 3.0.",
            },
            "intaglio_depth_mm": {
                "type": "number",
                "description": (
                    "Depth of intaglio / relief engraving cut into the seal face, mm. "
                    "0 = no engraving. Must be < face_height_mm. Default 0."
                ),
            },
            "engraving": {
                "type": "object",
                "description": (
                    "Optional text engraving on seal face (geometry hint only). "
                    "Fields: text (required), font_height_mm (default 1.5), "
                    "depth_mm (default 0.3), position_deg (default 180), "
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
            "band_width_mm": {
                "type": "number",
                "description": "Shank band width, mm. > 0. Default 4.0.",
            },
            "thickness_mm": {
                "type": "number",
                "description": "Shank radial wall thickness, mm. > 0. Default 1.8.",
            },
            "shoulder_style": {
                "type": "string",
                "enum": ["plain", "cathedral", "split_shank", "bypass"],
                "description": "Shank shoulder style. Default 'plain'.",
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "ring_size"],
    },
)


@register(jewelry_create_signet_ring_spec, write=True)
async def run_jewelry_create_signet_ring(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    ring_size = a.get("ring_size", None)
    system = str(a.get("system", "us")).strip().lower()
    face_shape = str(a.get("face_shape", "oval")).strip()
    face_length_mm = a.get("face_length_mm", 12.0)
    face_width_mm = a.get("face_width_mm", 10.0)
    face_height_mm = a.get("face_height_mm", 3.0)
    intaglio_depth_mm = a.get("intaglio_depth_mm", 0.0)
    engraving_raw = a.get("engraving", None)
    band_width_mm = a.get("band_width_mm", 4.0)
    thickness_mm = a.get("thickness_mm", 1.8)
    shoulder_style = str(a.get("shoulder_style", "plain")).strip()
    node_id = str(a.get("id", "")).strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if ring_size is None:
        return err_payload("ring_size is required", "BAD_ARGS")
    if system not in _VALID_SYSTEMS:
        return err_payload(
            f"system must be one of {sorted(_VALID_SYSTEMS)}; got {system!r}",
            "BAD_ARGS",
        )
    if face_shape not in _VALID_SIGNET_FACE_SHAPES:
        return err_payload(
            f"face_shape must be one of {sorted(_VALID_SIGNET_FACE_SHAPES)}; "
            f"got {face_shape!r}", "BAD_ARGS",
        )
    if shoulder_style not in _VALID_SHOULDER_STYLES:
        return err_payload(
            f"shoulder_style must be one of {sorted(_VALID_SHOULDER_STYLES)}; "
            f"got {shoulder_style!r}", "BAD_ARGS",
        )

    try:
        face_length_mm = float(face_length_mm)
        face_width_mm = float(face_width_mm)
        face_height_mm = float(face_height_mm)
        intaglio_depth_mm = float(intaglio_depth_mm)
        band_width_mm = float(band_width_mm)
        thickness_mm = float(thickness_mm)
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric param error: {e}", "BAD_ARGS")

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

    try:
        params = compute_signet_ring_params(
            ring_size=ring_size,
            system=system,
            face_shape=face_shape,
            face_length_mm=face_length_mm,
            face_width_mm=face_width_mm,
            face_height_mm=face_height_mm,
            intaglio_depth_mm=intaglio_depth_mm,
            engraving=engraving_spec,
            band_width_mm=band_width_mm,
            thickness_mm=thickness_mm,
            shoulder_style=shoulder_style,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = _fetch_feature_file(ctx, fid)
    if err:
        code = "NOT_FOUND" if "not found" in err or "not a feature" in err else "ERROR"
        return err_payload(err, code)

    if not node_id:
        node_id = _next_op_id(content or "", "signet_ring")

    node = {"id": node_id, "op": "signet_ring", **params}
    doc = _load_feature_doc(content or "")
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
        "op": "signet_ring",
        "inner_diameter_mm": params["inner_diameter_mm"],
        "face_shape": params["face_shape"],
        "face_length_mm": params["face_length_mm"],
        "face_width_mm": params["face_width_mm"],
        "face_height_mm": params["face_height_mm"],
        "intaglio_depth_mm": params["intaglio_depth_mm"],
    })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_stacking_band_set
# ---------------------------------------------------------------------------

jewelry_create_stacking_band_set_spec = ToolSpec(
    name="jewelry_create_stacking_band_set",
    description=(
        "Append a `stacking_band_set` node to a `.feature` file. "
        "Generates a set of N thin stacking bands that sit side-by-side on the "
        "finger with a controlled gap between them. "
        "Optionally includes a contour/wishbone band that nests against a named "
        "solitaire ring shank (set include_wishbone=true and provide "
        "solitaire_node_id). "
        "All dimensions in mm. Ring size is auto-converted to inner diameter."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "ring_size": {
                "description": "Size in the chosen system.",
            },
            "system": {
                "type": "string",
                "enum": ["us", "uk", "au", "eu", "jp"],
                "description": "Ring-size standard. Default 'us'.",
            },
            "band_count": {
                "type": "integer",
                "description": "Number of bands in the set. 1–8. Default 3.",
            },
            "band_width_mm": {
                "type": "number",
                "description": "Width of each band, mm. > 0. Default 2.0.",
            },
            "thickness_mm": {
                "type": "number",
                "description": "Radial wall thickness of each band, mm. > 0. Default 1.4.",
            },
            "profile": {
                "type": "string",
                "enum": sorted(_VALID_STACKING_PROFILES),
                "description": "Cross-section profile for all bands. Default 'flat'.",
            },
            "nest_gap_mm": {
                "type": "number",
                "description": "Gap between adjacent bands when stacked, mm. ≥ 0. Default 0.1.",
            },
            "include_wishbone": {
                "type": "boolean",
                "description": (
                    "Include a contour/wishbone band that nests against an "
                    "engagement ring. Default false."
                ),
            },
            "wishbone_notch_depth_mm": {
                "type": "number",
                "description": (
                    "Notch depth in the wishbone band top, mm. > 0. "
                    "Required when include_wishbone=true. Default 0.8."
                ),
            },
            "solitaire_node_id": {
                "type": "string",
                "description": (
                    "Node ID of the engagement ring_shank whose profile the "
                    "wishbone band should match. Geometry hint only."
                ),
            },
            "per_band_profiles": {
                "type": "array",
                "description": (
                    "Optional per-band profile override (one per band, same "
                    "valid values as profile). Must have exactly band_count elements."
                ),
                "items": {
                    "type": "string",
                    "enum": sorted(_VALID_STACKING_PROFILES),
                },
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "ring_size"],
    },
)


@register(jewelry_create_stacking_band_set_spec, write=True)
async def run_jewelry_create_stacking_band_set(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    ring_size = a.get("ring_size", None)
    system = str(a.get("system", "us")).strip().lower()
    band_count = a.get("band_count", 3)
    band_width_mm = a.get("band_width_mm", 2.0)
    thickness_mm = a.get("thickness_mm", 1.4)
    profile = str(a.get("profile", "flat")).strip()
    nest_gap_mm = a.get("nest_gap_mm", 0.1)
    include_wishbone = bool(a.get("include_wishbone", False))
    wishbone_notch_depth_mm = a.get("wishbone_notch_depth_mm", 0.8)
    solitaire_node_id = a.get("solitaire_node_id", None)
    per_band_profiles = a.get("per_band_profiles", None)
    node_id = str(a.get("id", "")).strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if ring_size is None:
        return err_payload("ring_size is required", "BAD_ARGS")
    if system not in _VALID_SYSTEMS:
        return err_payload(
            f"system must be one of {sorted(_VALID_SYSTEMS)}; got {system!r}",
            "BAD_ARGS",
        )
    if profile not in _VALID_STACKING_PROFILES:
        return err_payload(
            f"profile must be one of {sorted(_VALID_STACKING_PROFILES)}; "
            f"got {profile!r}", "BAD_ARGS",
        )

    try:
        band_count = int(band_count)
        band_width_mm = float(band_width_mm)
        thickness_mm = float(thickness_mm)
        nest_gap_mm = float(nest_gap_mm)
        wishbone_notch_depth_mm = float(wishbone_notch_depth_mm)
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric param error: {e}", "BAD_ARGS")

    try:
        params = compute_stacking_band_params(
            ring_size=ring_size,
            system=system,
            band_count=band_count,
            band_width_mm=band_width_mm,
            thickness_mm=thickness_mm,
            profile=profile,
            nest_gap_mm=nest_gap_mm,
            include_wishbone=include_wishbone,
            wishbone_notch_depth_mm=wishbone_notch_depth_mm,
            solitaire_node_id=solitaire_node_id,
            per_band_profiles=per_band_profiles,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = _fetch_feature_file(ctx, fid)
    if err:
        code = "NOT_FOUND" if "not found" in err or "not a feature" in err else "ERROR"
        return err_payload(err, code)

    if not node_id:
        node_id = _next_op_id(content or "", "stacking_band_set")

    node = {"id": node_id, "op": "stacking_band_set", **params}
    doc = _load_feature_doc(content or "")
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
        "op": "stacking_band_set",
        "inner_diameter_mm": params["inner_diameter_mm"],
        "band_count": params["band_count"],
        "band_width_mm": params["band_width_mm"],
        "thickness_mm": params["thickness_mm"],
        "total_span_mm": params["total_span_mm"],
        "include_wishbone": params["include_wishbone"],
    })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_contoured_band
# ---------------------------------------------------------------------------

jewelry_create_contoured_band_spec = ToolSpec(
    name="jewelry_create_contoured_band",
    description=(
        "Append a `contoured_band` node to a `.feature` file. "
        "Builds a parametric contoured / shadow wedding band whose top profile "
        "is cut to hug an engagement ring (curved concave arc or notched top). "
        "Set match_radius_mm to the engagement ring's outer radius (outer_diameter/2) "
        "for a perfect shadow fit. "
        "contour_style='curved' produces a smooth concave arc; 'notched' produces a "
        "V/U notch in the centre of the top face. "
        "All dimensions in mm. Ring size is auto-converted to inner diameter."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "ring_size": {
                "description": "Size in the chosen system.",
            },
            "system": {
                "type": "string",
                "enum": ["us", "uk", "au", "eu", "jp"],
                "description": "Ring-size standard. Default 'us'.",
            },
            "notch_depth_mm": {
                "type": "number",
                "description": (
                    "Depth of the contour cut / notch at the top of the band, mm. "
                    "> 0; must be < thickness_mm. Default 1.2."
                ),
            },
            "notch_width_mm": {
                "type": "number",
                "description": (
                    "Width of the contour notch across the band, mm. "
                    "> 0; must be ≤ band_width_mm. Default 3.0."
                ),
            },
            "match_radius_mm": {
                "type": "number",
                "description": (
                    "Radius of the concave curve that mirrors the engagement ring "
                    "outer surface, mm. > 0. "
                    "Use engagement_ring outer_diameter / 2 for a perfect fit. "
                    "Default 10.5."
                ),
            },
            "contour_style": {
                "type": "string",
                "enum": ["curved", "notched"],
                "description": (
                    "'curved' = smooth concave arc across the top face (shadow band). "
                    "'notched' = V/U notch at centre of top face. "
                    "Default 'curved'."
                ),
            },
            "band_width_mm": {
                "type": "number",
                "description": "Band width along finger axis, mm. > 0. Default 3.5.",
            },
            "thickness_mm": {
                "type": "number",
                "description": "Radial wall thickness, mm. > 0. Default 1.6.",
            },
            "profile": {
                "type": "string",
                "enum": ["flat", "half_round", "comfort_fit", "d_shape", "euro"],
                "description": "Cross-section profile for the lower (shank) portion. Default 'flat'.",
            },
            "shoulder_style": {
                "type": "string",
                "enum": ["plain", "cathedral", "split_shank", "bypass"],
                "description": "Shank shoulder style. Default 'plain'.",
            },
            "engagement_ring_node_id": {
                "type": "string",
                "description": (
                    "Optional node ID of the engagement ring this band is contoured to. "
                    "Geometry hint for the occtWorker; match_radius_mm is used regardless."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "ring_size"],
    },
)


@register(jewelry_create_contoured_band_spec, write=True)
async def run_jewelry_create_contoured_band(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    ring_size = a.get("ring_size", None)
    system = str(a.get("system", "us")).strip().lower()
    notch_depth_mm = a.get("notch_depth_mm", 1.2)
    notch_width_mm = a.get("notch_width_mm", 3.0)
    match_radius_mm = a.get("match_radius_mm", 10.5)
    contour_style = str(a.get("contour_style", "curved")).strip()
    band_width_mm = a.get("band_width_mm", 3.5)
    thickness_mm = a.get("thickness_mm", 1.6)
    profile = str(a.get("profile", "flat")).strip()
    shoulder_style = str(a.get("shoulder_style", "plain")).strip()
    engagement_ring_node_id = a.get("engagement_ring_node_id", None)
    node_id = str(a.get("id", "")).strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if ring_size is None:
        return err_payload("ring_size is required", "BAD_ARGS")
    if system not in _VALID_SYSTEMS:
        return err_payload(
            f"system must be one of {sorted(_VALID_SYSTEMS)}; got {system!r}",
            "BAD_ARGS",
        )

    _VALID_CONTOUR_STYLES = frozenset(["curved", "notched"])
    _VALID_CONTOUR_BASE_PROFILES = frozenset([
        "flat", "half_round", "comfort_fit", "d_shape", "euro",
    ])
    if contour_style not in _VALID_CONTOUR_STYLES:
        return err_payload(
            f"contour_style must be one of {sorted(_VALID_CONTOUR_STYLES)}; "
            f"got {contour_style!r}", "BAD_ARGS",
        )
    if profile not in _VALID_CONTOUR_BASE_PROFILES:
        return err_payload(
            f"profile must be one of {sorted(_VALID_CONTOUR_BASE_PROFILES)}; "
            f"got {profile!r}", "BAD_ARGS",
        )
    if shoulder_style not in _VALID_SHOULDER_STYLES:
        return err_payload(
            f"shoulder_style must be one of {sorted(_VALID_SHOULDER_STYLES)}; "
            f"got {shoulder_style!r}", "BAD_ARGS",
        )

    try:
        notch_depth_mm = float(notch_depth_mm)
        notch_width_mm = float(notch_width_mm)
        match_radius_mm = float(match_radius_mm)
        band_width_mm = float(band_width_mm)
        thickness_mm = float(thickness_mm)
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric param error: {e}", "BAD_ARGS")

    try:
        params = compute_contoured_band_params(
            ring_size=ring_size,
            system=system,
            notch_depth_mm=notch_depth_mm,
            notch_width_mm=notch_width_mm,
            match_radius_mm=match_radius_mm,
            contour_style=contour_style,
            band_width_mm=band_width_mm,
            thickness_mm=thickness_mm,
            profile=profile,
            shoulder_style=shoulder_style,
            engagement_ring_node_id=engagement_ring_node_id,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = _fetch_feature_file(ctx, fid)
    if err:
        code = "NOT_FOUND" if "not found" in err or "not a feature" in err else "ERROR"
        return err_payload(err, code)

    if not node_id:
        node_id = _next_op_id(content or "", "contoured_band")

    node = {"id": node_id, "op": "contoured_band", **params}
    doc = _load_feature_doc(content or "")
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
        "op": "contoured_band",
        "inner_diameter_mm": params["inner_diameter_mm"],
        "outer_diameter_mm": params["outer_diameter_mm"],
        "notch_depth_mm": params["notch_depth_mm"],
        "notch_width_mm": params["notch_width_mm"],
        "match_radius_mm": params["match_radius_mm"],
        "contour_style": params["contour_style"],
        "band_width_mm": params["band_width_mm"],
        "thickness_mm": params["thickness_mm"],
    })


# ===========================================================================
# v4 Composite / Style Ring Builders
# ===========================================================================
#
# Five new composite ring builders, each emitting a single feature node that
# the generic occtWorker can evaluate.  Each node uses the same doc structure
# (op + params dict) as existing v2/v3 nodes.
#
# Attach-point hints schema (consumed by downstream setting/gem-seat nodes):
# -------------------------------------------------------------------------
#  {
#    "type": "circular_seat" | "toi_et_moi",
#    "position_deg": <float, 0–360>,  # 0 = 12-o'clock top of shank
#    "height_mm": <float>,            # height above bore centre-plane
#    "diameter_mm": <float>,          # nominal seat opening diameter (= stone diam)
#    "normal": [0, 0, 1]              # unit normal, always shank-axis-aligned for now
#  }
# -------------------------------------------------------------------------
# Node ops added:
#   solitaire_ring   — shank + centre-stone seat attach point
#   mens_band        — wide comfort/euro/bevel band + optional groove/inlay + surface hints
#   wedding_set      — engagement ring node + matched contoured band, paired in one node
#   cocktail_ring    — tapered shank + large dome/cluster mount attach point
#   bypass_ring      — two-element crossover shank + toi-et-moi two stone mount points
# ===========================================================================

# ---------------------------------------------------------------------------
# v4 constants
# ---------------------------------------------------------------------------

_VALID_MENS_PROFILES = frozenset([
    "comfort_fit", "euro", "d_shape", "flat", "cigar_band",
    "bombe", "concave", "square", "half_round",
])

_VALID_MENS_SURFACE_HINTS = frozenset([
    "polished", "matte", "hammered", "satin", "brushed",
])

_VALID_COCKTAIL_MOUNT_STYLES = frozenset([
    "dome", "cluster", "bezel", "prong",
])

_VALID_BYPASS_CROSS_STYLES = frozenset([
    "crossover", "toi_et_moi",
])

_VALID_WEDDING_SET_BAND_PROFILES = frozenset([
    "flat", "half_round", "comfort_fit", "d_shape", "euro",
])


# ---------------------------------------------------------------------------
# v4 spec dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SolitaireRingSpec:
    """Composite solitaire ring descriptor.

    Emits a ``solitaire_ring`` node whose occtWorker op sweeps the shank and
    then emits a single ``attach_point`` hint at the top of the shank for a
    downstream setting node (prong, bezel, etc.) to fuse onto.

    Fields
    ------
    ring_size : int | float | str
        Size in the given system.
    system : str
        Ring-size standard ("us", "uk", "au", "eu", "jp").
    shank_profile : str
        Cross-section profile for the shank.  Any profile from _VALID_PROFILES.
    shoulder_style : str
        How the shank meets the head.  Default "cathedral".
    band_width_mm : float
        Shank band width along the finger axis, mm.  > 0.  Default 3.0.
    thickness_mm : float
        Shank radial wall thickness, mm.  > 0.  Default 1.6.
    head_height_mm : float
        Height of the setting mount point above the bore centre-plane, mm.
        > 0.  Drives the attach-point position hint consumed by a head/setting
        node.  Default 5.0.
    center_stone_diameter_mm : float
        Nominal centre-stone diameter, mm.  > 0.  Stored as the ``diameter_mm``
        of the attach-point hint so a downstream gem-seat node can resolve the
        prong / bezel geometry.  Default 6.5 mm (≈ 1 ct round brilliant).
    taper_ratio : float
        Shank width/thickness taper shoulder→back.  1.0 = uniform.
        0 < v ≤ 1.  Default 1.0.
    """
    ring_size: object
    system: str = "us"
    shank_profile: str = "comfort_fit"
    shoulder_style: str = "cathedral"
    band_width_mm: float = 3.0
    thickness_mm: float = 1.6
    head_height_mm: float = 5.0
    center_stone_diameter_mm: float = 6.5
    taper_ratio: float = 1.0

    def validate(self) -> None:
        if self.shank_profile not in _VALID_PROFILES:
            raise ValueError(
                f"solitaire.shank_profile must be one of "
                f"{sorted(_VALID_PROFILES)}; got {self.shank_profile!r}"
            )
        if self.shoulder_style not in _VALID_SHOULDER_STYLES:
            raise ValueError(
                f"solitaire.shoulder_style must be one of "
                f"{sorted(_VALID_SHOULDER_STYLES)}; got {self.shoulder_style!r}"
            )
        if self.band_width_mm <= 0:
            raise ValueError(
                f"solitaire.band_width_mm must be > 0; got {self.band_width_mm}"
            )
        if self.thickness_mm <= 0:
            raise ValueError(
                f"solitaire.thickness_mm must be > 0; got {self.thickness_mm}"
            )
        if self.head_height_mm <= 0:
            raise ValueError(
                f"solitaire.head_height_mm must be > 0; got {self.head_height_mm}"
            )
        if self.center_stone_diameter_mm <= 0:
            raise ValueError(
                f"solitaire.center_stone_diameter_mm must be > 0; "
                f"got {self.center_stone_diameter_mm}"
            )
        if not (0 < self.taper_ratio <= 1.0):
            raise ValueError(
                f"solitaire.taper_ratio must be in (0, 1]; got {self.taper_ratio}"
            )

    def to_dict(self, inner_diameter_mm: float) -> dict:
        self.validate()
        outer_diameter_mm = inner_diameter_mm + 2 * self.thickness_mm
        shank_params = compute_shank_params(
            ring_size=self.ring_size,
            system=self.system,
            band_width=self.band_width_mm,
            thickness=self.thickness_mm,
            profile=self.shank_profile,
            taper_ratio=self.taper_ratio,
            shoulder_style=self.shoulder_style,
        )
        attach_point = {
            "type": "circular_seat",
            "position_deg": 0.0,
            "height_mm": round(self.head_height_mm, 4),
            "diameter_mm": round(self.center_stone_diameter_mm, 4),
            "normal": [0, 0, 1],
        }
        return {
            "inner_diameter_mm": round(inner_diameter_mm, 4),
            "outer_diameter_mm": round(outer_diameter_mm, 4),
            "shank": shank_params,
            "head_height_mm": round(self.head_height_mm, 4),
            "center_stone_diameter_mm": round(self.center_stone_diameter_mm, 4),
            "attach_points": [attach_point],
            "composite_ops": ["ring_shank", "setting_mount"],
        }


@dataclass
class MensBandSpec:
    """Wide comfort/euro/bevel men's band descriptor.

    Builds a wider-than-standard band with optional:
      - centre groove / inlay channel (geometry hint)
      - milgrain-edge hint (geometry hint for occtWorker bead-milling pass)
      - surface finish hint (matte / hammered / satin / brushed / polished)

    Fields
    ------
    ring_size : int | float | str
        Size in the given system.
    system : str
        Ring-size standard.
    profile : str
        Cross-section profile.  Valid profiles: comfort_fit, euro, d_shape,
        flat, cigar_band, bombe, concave, square, half_round.
        Default "comfort_fit".
    band_width_mm : float
        Band width along the finger axis, mm.  > 0.  Typically 6–12 mm for
        men's bands.  Default 8.0.
    thickness_mm : float
        Radial wall thickness, mm.  > 0.  Default 2.0.
    taper_ratio : float
        Width/thickness scale at the back of the shank vs. shoulder.
        1.0 = uniform; < 1 = tapers.  > 0.  Default 1.0.
    groove_depth_mm : float
        Depth of optional centre groove / inlay channel, mm.
        0.0 = no groove.  ≥ 0; if > 0 must be < thickness_mm / 2.
    groove_width_mm : float
        Width of the groove / inlay channel, mm.  > 0 when groove_depth_mm > 0;
        must be < band_width_mm.
    milgrain_edges : bool
        Geometry hint: worker adds a milgrain bead row on each outer edge of
        the band.  False by default.
    milgrain_bead_diameter_mm : float
        Diameter of each milgrain bead, mm.  > 0.  Only used when
        milgrain_edges is True.  Default 0.5 mm.
    surface_finish : str
        Surface finish hint: "polished", "matte", "hammered", "satin",
        "brushed".  Default "polished".
    hammered_facet_count : int
        Facet count for the hammered profile or hammered surface finish.
        4–128.  Default 32.
    """
    ring_size: object
    system: str = "us"
    profile: str = "comfort_fit"
    band_width_mm: float = 8.0
    thickness_mm: float = 2.0
    taper_ratio: float = 1.0
    groove_depth_mm: float = 0.0
    groove_width_mm: float = 1.5
    milgrain_edges: bool = False
    milgrain_bead_diameter_mm: float = 0.5
    surface_finish: str = "polished"
    hammered_facet_count: int = 32

    def validate(self) -> None:
        if self.profile not in _VALID_MENS_PROFILES:
            raise ValueError(
                f"mens_band.profile must be one of "
                f"{sorted(_VALID_MENS_PROFILES)}; got {self.profile!r}"
            )
        if self.band_width_mm <= 0:
            raise ValueError(
                f"mens_band.band_width_mm must be > 0; got {self.band_width_mm}"
            )
        if self.thickness_mm <= 0:
            raise ValueError(
                f"mens_band.thickness_mm must be > 0; got {self.thickness_mm}"
            )
        if self.taper_ratio <= 0:
            raise ValueError(
                f"mens_band.taper_ratio must be > 0; got {self.taper_ratio}"
            )
        if self.groove_depth_mm < 0:
            raise ValueError(
                f"mens_band.groove_depth_mm must be ≥ 0; got {self.groove_depth_mm}"
            )
        if self.groove_depth_mm > 0:
            if self.groove_depth_mm >= self.thickness_mm / 2.0:
                raise ValueError(
                    f"mens_band.groove_depth_mm ({self.groove_depth_mm}) must be < "
                    f"thickness_mm / 2 ({self.thickness_mm / 2.0:.3f})"
                )
            if self.groove_width_mm <= 0:
                raise ValueError(
                    f"mens_band.groove_width_mm must be > 0 when groove_depth_mm > 0; "
                    f"got {self.groove_width_mm}"
                )
            if self.groove_width_mm >= self.band_width_mm:
                raise ValueError(
                    f"mens_band.groove_width_mm ({self.groove_width_mm}) must be < "
                    f"band_width_mm ({self.band_width_mm})"
                )
        if self.surface_finish not in _VALID_MENS_SURFACE_HINTS:
            raise ValueError(
                f"mens_band.surface_finish must be one of "
                f"{sorted(_VALID_MENS_SURFACE_HINTS)}; got {self.surface_finish!r}"
            )
        if self.milgrain_edges:
            if self.milgrain_bead_diameter_mm <= 0:
                raise ValueError(
                    f"mens_band.milgrain_bead_diameter_mm must be > 0; "
                    f"got {self.milgrain_bead_diameter_mm}"
                )
        fc = int(self.hammered_facet_count)
        if not (4 <= fc <= 128):
            raise ValueError(
                f"mens_band.hammered_facet_count must be 4–128; got {fc}"
            )

    def to_dict(self, inner_diameter_mm: float) -> dict:
        self.validate()
        outer_diameter_mm = inner_diameter_mm + 2 * self.thickness_mm
        result: dict = {
            "inner_diameter_mm": round(inner_diameter_mm, 4),
            "outer_diameter_mm": round(outer_diameter_mm, 4),
            "profile": self.profile,
            "band_width_mm": self.band_width_mm,
            "thickness_mm": self.thickness_mm,
            "taper_ratio": self.taper_ratio,
            "surface_finish": self.surface_finish,
        }
        if self.groove_depth_mm > 0:
            result["groove_hint"] = {
                "type": "centre_groove",
                "depth_mm": round(self.groove_depth_mm, 4),
                "width_mm": round(self.groove_width_mm, 4),
                "position_deg": 0.0,
            }
        if self.milgrain_edges:
            result["milgrain_hint"] = {
                "type": "milgrain_edge",
                "bead_diameter_mm": round(self.milgrain_bead_diameter_mm, 4),
                "edges": ["top", "bottom"],
            }
        if self.surface_finish == "hammered":
            fc = int(self.hammered_facet_count)
            result["surface_hint"] = {
                "type": "hammered",
                "facet_count": fc,
                "facet_arc_deg": round(360.0 / fc, 4),
            }
        elif self.surface_finish != "polished":
            result["surface_hint"] = {"type": self.surface_finish}
        return result


@dataclass
class WeddingSetSpec:
    """Engagement ring + matched contoured wedding band, as a paired composite.

    Produces a single ``wedding_set`` node whose two sub-node specs are stored
    under ``engagement_ring`` and ``wedding_band``.  The occtWorker resolves
    each sub-node using ``ring_shank`` and ``contoured_band`` ops respectively,
    then positions them so the wedding band's contour matches the engagement
    ring's outer radius.

    Fields
    ------
    ring_size : int | float | str
        Shared ring size for both rings (same finger).
    system : str
        Ring-size standard.
    eng_profile : str
        Shank profile for the engagement ring.  Default "comfort_fit".
    eng_shoulder_style : str
        Shoulder style for the engagement ring.  Default "cathedral".
    eng_band_width_mm : float
        Engagement ring band width, mm.  > 0.  Default 2.5.
    eng_thickness_mm : float
        Engagement ring wall thickness, mm.  > 0.  Default 1.6.
    eng_taper_ratio : float
        Engagement ring shank taper ratio.  > 0.  Default 1.0.
    band_profile : str
        Cross-section profile for the wedding band's lower shank portion.
        Valid: flat, half_round, comfort_fit, d_shape, euro.  Default "flat".
    band_width_mm : float
        Wedding band width, mm.  > 0.  Default 3.0.
    band_thickness_mm : float
        Wedding band wall thickness, mm.  > 0.  Default 1.6.
    notch_depth_mm : float
        Depth of the contour notch in the wedding band, mm.  > 0;
        must be < band_thickness_mm.  Default 1.2.
    notch_width_mm : float
        Width of the contour notch, mm.  > 0; ≤ band_width_mm.  Default 2.5.
    contour_style : str
        "curved" or "notched".  Default "curved".
    """
    ring_size: object
    system: str = "us"
    eng_profile: str = "comfort_fit"
    eng_shoulder_style: str = "cathedral"
    eng_band_width_mm: float = 2.5
    eng_thickness_mm: float = 1.6
    eng_taper_ratio: float = 1.0
    band_profile: str = "flat"
    band_width_mm: float = 3.0
    band_thickness_mm: float = 1.6
    notch_depth_mm: float = 1.2
    notch_width_mm: float = 2.5
    contour_style: str = "curved"

    _VALID_BAND_BASE_PROFILES = frozenset([
        "flat", "half_round", "comfort_fit", "d_shape", "euro",
    ])
    _VALID_CONTOUR_STYLES = frozenset(["curved", "notched"])

    def validate(self) -> None:
        if self.eng_profile not in _VALID_PROFILES:
            raise ValueError(
                f"wedding_set.eng_profile must be one of "
                f"{sorted(_VALID_PROFILES)}; got {self.eng_profile!r}"
            )
        if self.eng_shoulder_style not in _VALID_SHOULDER_STYLES:
            raise ValueError(
                f"wedding_set.eng_shoulder_style must be one of "
                f"{sorted(_VALID_SHOULDER_STYLES)}; got {self.eng_shoulder_style!r}"
            )
        if self.eng_band_width_mm <= 0:
            raise ValueError(
                f"wedding_set.eng_band_width_mm must be > 0; got {self.eng_band_width_mm}"
            )
        if self.eng_thickness_mm <= 0:
            raise ValueError(
                f"wedding_set.eng_thickness_mm must be > 0; got {self.eng_thickness_mm}"
            )
        if self.eng_taper_ratio <= 0:
            raise ValueError(
                f"wedding_set.eng_taper_ratio must be > 0; got {self.eng_taper_ratio}"
            )
        if self.band_profile not in self._VALID_BAND_BASE_PROFILES:
            raise ValueError(
                f"wedding_set.band_profile must be one of "
                f"{sorted(self._VALID_BAND_BASE_PROFILES)}; got {self.band_profile!r}"
            )
        if self.band_width_mm <= 0:
            raise ValueError(
                f"wedding_set.band_width_mm must be > 0; got {self.band_width_mm}"
            )
        if self.band_thickness_mm <= 0:
            raise ValueError(
                f"wedding_set.band_thickness_mm must be > 0; got {self.band_thickness_mm}"
            )
        if self.notch_depth_mm <= 0:
            raise ValueError(
                f"wedding_set.notch_depth_mm must be > 0; got {self.notch_depth_mm}"
            )
        if self.notch_depth_mm >= self.band_thickness_mm:
            raise ValueError(
                f"wedding_set.notch_depth_mm ({self.notch_depth_mm}) must be < "
                f"band_thickness_mm ({self.band_thickness_mm})"
            )
        if self.notch_width_mm <= 0:
            raise ValueError(
                f"wedding_set.notch_width_mm must be > 0; got {self.notch_width_mm}"
            )
        if self.notch_width_mm > self.band_width_mm:
            raise ValueError(
                f"wedding_set.notch_width_mm ({self.notch_width_mm}) must be ≤ "
                f"band_width_mm ({self.band_width_mm})"
            )
        if self.contour_style not in self._VALID_CONTOUR_STYLES:
            raise ValueError(
                f"wedding_set.contour_style must be one of "
                f"{sorted(self._VALID_CONTOUR_STYLES)}; got {self.contour_style!r}"
            )

    def to_dict(self, inner_diameter_mm: float) -> dict:
        self.validate()
        eng_outer_radius = round(
            (inner_diameter_mm + 2 * self.eng_thickness_mm) / 2.0, 4
        )
        notch_half_angle = math.degrees(
            math.asin(min(1.0, (self.notch_width_mm / 2.0) / eng_outer_radius))
        )
        engagement_ring = {
            "op": "ring_shank",
            "profile": self.eng_profile,
            "shoulder_style": self.eng_shoulder_style,
            "band_width_mm": self.eng_band_width_mm,
            "thickness_mm": self.eng_thickness_mm,
            "taper_ratio": self.eng_taper_ratio,
            "inner_diameter_mm": round(inner_diameter_mm, 4),
            "outer_diameter_mm": round(inner_diameter_mm + 2 * self.eng_thickness_mm, 4),
        }
        wedding_band = {
            "op": "contoured_band",
            "profile": self.band_profile,
            "shoulder_style": "plain",
            "band_width_mm": self.band_width_mm,
            "thickness_mm": self.band_thickness_mm,
            "notch_depth_mm": self.notch_depth_mm,
            "notch_width_mm": self.notch_width_mm,
            "contour_style": self.contour_style,
            "match_radius_mm": eng_outer_radius,
            "inner_diameter_mm": round(inner_diameter_mm, 4),
            "outer_diameter_mm": round(
                inner_diameter_mm + 2 * self.band_thickness_mm, 4
            ),
            "contour_hints": {
                "type": self.contour_style,
                "notch_depth_mm": self.notch_depth_mm,
                "notch_width_mm": self.notch_width_mm,
                "match_radius_mm": eng_outer_radius,
                "notch_half_angle_deg": round(notch_half_angle, 4),
            },
        }
        return {
            "inner_diameter_mm": round(inner_diameter_mm, 4),
            "engagement_ring": engagement_ring,
            "wedding_band": wedding_band,
            "match_radius_mm": eng_outer_radius,
            "composite_ops": ["ring_shank", "contoured_band"],
        }


@dataclass
class CocktailRingSpec:
    """Cocktail / statement ring descriptor.

    A tapered shank leading to a large dome / cluster / bezel / prong mount
    point.  Emits a single ``cocktail_ring`` node with a ``attach_points``
    array containing one large circular-seat hint for the mount.

    Fields
    ------
    ring_size : int | float | str
        Size in the given system.
    system : str
        Ring-size standard.
    shank_profile : str
        Shank cross-section profile.  Any of _VALID_PROFILES.
        Default "tapered".
    shoulder_style : str
        How the shank meets the mount.  Default "plain".
    band_width_mm : float
        Shank band width at the shoulder (widest point), mm.  > 0.  Default 4.0.
    thickness_mm : float
        Shank radial wall thickness at the shoulder, mm.  > 0.  Default 1.8.
    taper_ratio : float
        Width+thickness scale at the back of the shank vs. shoulder.
        (0, 1].  Default 0.7 (tapers to 70% at back).
    mount_style : str
        Style of the large top mount: "dome", "cluster", "bezel", "prong".
        Default "dome".
    mount_diameter_mm : float
        Nominal outer diameter of the top mount, mm.  > 0.
        This is the platform / table diameter, not the stone's diameter.
        Default 18.0 mm (large statement mount).
    mount_height_mm : float
        Height of the mount platform above the bore centre-plane, mm.
        > 0.  Default 8.0.
    stone_diameter_mm : float
        Diameter of the centre stone or cluster, mm.  > 0.
        Stored in the attach-point hint.  Default 14.0 mm.
    """
    ring_size: object
    system: str = "us"
    shank_profile: str = "tapered"
    shoulder_style: str = "plain"
    band_width_mm: float = 4.0
    thickness_mm: float = 1.8
    taper_ratio: float = 0.7
    mount_style: str = "dome"
    mount_diameter_mm: float = 18.0
    mount_height_mm: float = 8.0
    stone_diameter_mm: float = 14.0

    def validate(self) -> None:
        if self.shank_profile not in _VALID_PROFILES:
            raise ValueError(
                f"cocktail.shank_profile must be one of "
                f"{sorted(_VALID_PROFILES)}; got {self.shank_profile!r}"
            )
        if self.shoulder_style not in _VALID_SHOULDER_STYLES:
            raise ValueError(
                f"cocktail.shoulder_style must be one of "
                f"{sorted(_VALID_SHOULDER_STYLES)}; got {self.shoulder_style!r}"
            )
        if self.band_width_mm <= 0:
            raise ValueError(
                f"cocktail.band_width_mm must be > 0; got {self.band_width_mm}"
            )
        if self.thickness_mm <= 0:
            raise ValueError(
                f"cocktail.thickness_mm must be > 0; got {self.thickness_mm}"
            )
        if not (0 < self.taper_ratio <= 1.0):
            raise ValueError(
                f"cocktail.taper_ratio must be in (0, 1]; got {self.taper_ratio}"
            )
        if self.mount_style not in _VALID_COCKTAIL_MOUNT_STYLES:
            raise ValueError(
                f"cocktail.mount_style must be one of "
                f"{sorted(_VALID_COCKTAIL_MOUNT_STYLES)}; got {self.mount_style!r}"
            )
        if self.mount_diameter_mm <= 0:
            raise ValueError(
                f"cocktail.mount_diameter_mm must be > 0; got {self.mount_diameter_mm}"
            )
        if self.mount_height_mm <= 0:
            raise ValueError(
                f"cocktail.mount_height_mm must be > 0; got {self.mount_height_mm}"
            )
        if self.stone_diameter_mm <= 0:
            raise ValueError(
                f"cocktail.stone_diameter_mm must be > 0; got {self.stone_diameter_mm}"
            )
        if self.stone_diameter_mm > self.mount_diameter_mm:
            raise ValueError(
                f"cocktail.stone_diameter_mm ({self.stone_diameter_mm}) must be ≤ "
                f"mount_diameter_mm ({self.mount_diameter_mm})"
            )

    def to_dict(self, inner_diameter_mm: float) -> dict:
        self.validate()
        outer_diameter_mm = inner_diameter_mm + 2 * self.thickness_mm
        attach_point = {
            "type": "circular_seat",
            "position_deg": 0.0,
            "height_mm": round(self.mount_height_mm, 4),
            "diameter_mm": round(self.stone_diameter_mm, 4),
            "mount_style": self.mount_style,
            "mount_diameter_mm": round(self.mount_diameter_mm, 4),
            "normal": [0, 0, 1],
        }
        return {
            "inner_diameter_mm": round(inner_diameter_mm, 4),
            "outer_diameter_mm": round(outer_diameter_mm, 4),
            "profile": self.shank_profile,
            "shoulder_style": self.shoulder_style,
            "band_width_mm": self.band_width_mm,
            "thickness_mm": self.thickness_mm,
            "taper_ratio": self.taper_ratio,
            "mount_style": self.mount_style,
            "mount_diameter_mm": round(self.mount_diameter_mm, 4),
            "mount_height_mm": round(self.mount_height_mm, 4),
            "stone_diameter_mm": round(self.stone_diameter_mm, 4),
            "attach_points": [attach_point],
            "composite_ops": ["ring_shank", "mount_platform"],
        }


@dataclass
class BypassRingSpec:
    """Bypass / crossover & toi-et-moi ring descriptor.

    Two-element shank that sweeps two offset arcs crossing at the top of the
    finger.  Each arc terminates in a stone mount point (attach_point hint).
    Models both a simple crossover and a toi-et-moi (two separate stone seats
    side by side at the top).

    Fields
    ------
    ring_size : int | float | str
        Size in the given system.
    system : str
        Ring-size standard.
    cross_style : str
        "crossover" — two arcs that visually intersect at the top (offset in Z).
        "toi_et_moi" — two parallel arcs that place two stones side by side.
        Default "crossover".
    profile : str
        Cross-section profile for each arm.  Any of _VALID_PROFILES.
        Default "half_round".
    band_width_mm : float
        Width of each arm, mm.  > 0.  Default 3.0.
    thickness_mm : float
        Radial wall thickness of each arm, mm.  > 0.  Default 1.5.
    bypass_offset_mm : float
        Lateral offset of each arm end from the centreline, mm.  > 0.
        Controls how far apart the two stone seats are.
        Default 4.0 mm.
    overlap_deg : float
        Degrees past the 12-o'clock position that each arm extends before
        terminating.  0–90.  Default 20.0.
    stone_a_diameter_mm : float
        Diameter of stone for arm A, mm.  > 0.  Default 6.0 mm.
    stone_b_diameter_mm : float
        Diameter of stone for arm B, mm.  > 0.  Default 6.0 mm.
    mount_height_mm : float
        Height of each stone mount above the bore centre-plane, mm.  > 0.
        Default 4.5.
    """
    ring_size: object
    system: str = "us"
    cross_style: str = "crossover"
    profile: str = "half_round"
    band_width_mm: float = 3.0
    thickness_mm: float = 1.5
    bypass_offset_mm: float = 4.0
    overlap_deg: float = 20.0
    stone_a_diameter_mm: float = 6.0
    stone_b_diameter_mm: float = 6.0
    mount_height_mm: float = 4.5

    def validate(self) -> None:
        if self.cross_style not in _VALID_BYPASS_CROSS_STYLES:
            raise ValueError(
                f"bypass.cross_style must be one of "
                f"{sorted(_VALID_BYPASS_CROSS_STYLES)}; got {self.cross_style!r}"
            )
        if self.profile not in _VALID_PROFILES:
            raise ValueError(
                f"bypass.profile must be one of "
                f"{sorted(_VALID_PROFILES)}; got {self.profile!r}"
            )
        if self.band_width_mm <= 0:
            raise ValueError(
                f"bypass.band_width_mm must be > 0; got {self.band_width_mm}"
            )
        if self.thickness_mm <= 0:
            raise ValueError(
                f"bypass.thickness_mm must be > 0; got {self.thickness_mm}"
            )
        if self.bypass_offset_mm <= 0:
            raise ValueError(
                f"bypass.bypass_offset_mm must be > 0; got {self.bypass_offset_mm}"
            )
        if not (0 <= self.overlap_deg <= 90):
            raise ValueError(
                f"bypass.overlap_deg must be 0–90; got {self.overlap_deg}"
            )
        if self.stone_a_diameter_mm <= 0:
            raise ValueError(
                f"bypass.stone_a_diameter_mm must be > 0; got {self.stone_a_diameter_mm}"
            )
        if self.stone_b_diameter_mm <= 0:
            raise ValueError(
                f"bypass.stone_b_diameter_mm must be > 0; got {self.stone_b_diameter_mm}"
            )
        if self.mount_height_mm <= 0:
            raise ValueError(
                f"bypass.mount_height_mm must be > 0; got {self.mount_height_mm}"
            )

    def to_dict(self, inner_diameter_mm: float) -> dict:
        self.validate()
        outer_diameter_mm = inner_diameter_mm + 2 * self.thickness_mm
        # For crossover: arms pass over/under each other at 12-o'clock.
        # For toi-et-moi: arms end side by side at +/- bypass_offset from centre.
        # Attach-point A is at +offset_mm, B at -offset_mm.
        attach_type = "toi_et_moi" if self.cross_style == "toi_et_moi" else "circular_seat"
        attach_a = {
            "type": attach_type,
            "arm": "A",
            "position_deg": round(360.0 - self.overlap_deg, 4),  # just before top
            "height_mm": round(self.mount_height_mm, 4),
            "diameter_mm": round(self.stone_a_diameter_mm, 4),
            "lateral_offset_mm": round(self.bypass_offset_mm, 4),
            "normal": [0, 0, 1],
        }
        attach_b = {
            "type": attach_type,
            "arm": "B",
            "position_deg": round(self.overlap_deg, 4),          # just past top
            "height_mm": round(self.mount_height_mm, 4),
            "diameter_mm": round(self.stone_b_diameter_mm, 4),
            "lateral_offset_mm": round(-self.bypass_offset_mm, 4),
            "normal": [0, 0, 1],
        }
        return {
            "inner_diameter_mm": round(inner_diameter_mm, 4),
            "outer_diameter_mm": round(outer_diameter_mm, 4),
            "cross_style": self.cross_style,
            "profile": self.profile,
            "band_width_mm": self.band_width_mm,
            "thickness_mm": self.thickness_mm,
            "bypass_offset_mm": round(self.bypass_offset_mm, 4),
            "overlap_deg": round(self.overlap_deg, 4),
            "stone_a_diameter_mm": round(self.stone_a_diameter_mm, 4),
            "stone_b_diameter_mm": round(self.stone_b_diameter_mm, 4),
            "mount_height_mm": round(self.mount_height_mm, 4),
            "attach_points": [attach_a, attach_b],
            "composite_ops": ["bypass_arm_a", "bypass_arm_b"],
        }


# ---------------------------------------------------------------------------
# v4 compute functions
# ---------------------------------------------------------------------------

def compute_solitaire_ring_params(
    ring_size,
    system: str = "us",
    shank_profile: str = "comfort_fit",
    shoulder_style: str = "cathedral",
    band_width_mm: float = 3.0,
    thickness_mm: float = 1.6,
    head_height_mm: float = 5.0,
    center_stone_diameter_mm: float = 6.5,
    taper_ratio: float = 1.0,
) -> dict:
    """Compute validated solitaire ring descriptor.

    Returns a dict suitable for a ``solitaire_ring`` feature node.

    Raises
    ------
    ValueError
        On any constraint violation.
    """
    id_mm = ring_size_to_diameter(system, ring_size)
    circ_mm = _id_mm_to_circumference(id_mm)

    spec = SolitaireRingSpec(
        ring_size=ring_size,
        system=system,
        shank_profile=str(shank_profile),
        shoulder_style=str(shoulder_style),
        band_width_mm=float(band_width_mm),
        thickness_mm=float(thickness_mm),
        head_height_mm=float(head_height_mm),
        center_stone_diameter_mm=float(center_stone_diameter_mm),
        taper_ratio=float(taper_ratio),
    )
    spec.validate()
    d = spec.to_dict(id_mm)

    return {
        "circumference_mm": round(circ_mm, 4),
        "size_system": system,
        "ring_size": ring_size,
        **d,
    }


def compute_mens_band_params(
    ring_size,
    system: str = "us",
    profile: str = "comfort_fit",
    band_width_mm: float = 8.0,
    thickness_mm: float = 2.0,
    taper_ratio: float = 1.0,
    groove_depth_mm: float = 0.0,
    groove_width_mm: float = 1.5,
    milgrain_edges: bool = False,
    milgrain_bead_diameter_mm: float = 0.5,
    surface_finish: str = "polished",
    hammered_facet_count: int = 32,
) -> dict:
    """Compute validated men's band descriptor.

    Returns a dict suitable for a ``mens_band`` feature node.
    """
    id_mm = ring_size_to_diameter(system, ring_size)
    circ_mm = _id_mm_to_circumference(id_mm)

    spec = MensBandSpec(
        ring_size=ring_size,
        system=system,
        profile=str(profile),
        band_width_mm=float(band_width_mm),
        thickness_mm=float(thickness_mm),
        taper_ratio=float(taper_ratio),
        groove_depth_mm=float(groove_depth_mm),
        groove_width_mm=float(groove_width_mm),
        milgrain_edges=bool(milgrain_edges),
        milgrain_bead_diameter_mm=float(milgrain_bead_diameter_mm),
        surface_finish=str(surface_finish),
        hammered_facet_count=int(hammered_facet_count),
    )
    spec.validate()
    d = spec.to_dict(id_mm)

    return {
        "circumference_mm": round(circ_mm, 4),
        "size_system": system,
        "ring_size": ring_size,
        **d,
    }


def compute_wedding_set_params(
    ring_size,
    system: str = "us",
    eng_profile: str = "comfort_fit",
    eng_shoulder_style: str = "cathedral",
    eng_band_width_mm: float = 2.5,
    eng_thickness_mm: float = 1.6,
    eng_taper_ratio: float = 1.0,
    band_profile: str = "flat",
    band_width_mm: float = 3.0,
    band_thickness_mm: float = 1.6,
    notch_depth_mm: float = 1.2,
    notch_width_mm: float = 2.5,
    contour_style: str = "curved",
) -> dict:
    """Compute validated wedding set descriptor.

    Returns a dict suitable for a ``wedding_set`` feature node.
    """
    id_mm = ring_size_to_diameter(system, ring_size)
    circ_mm = _id_mm_to_circumference(id_mm)

    spec = WeddingSetSpec(
        ring_size=ring_size,
        system=system,
        eng_profile=str(eng_profile),
        eng_shoulder_style=str(eng_shoulder_style),
        eng_band_width_mm=float(eng_band_width_mm),
        eng_thickness_mm=float(eng_thickness_mm),
        eng_taper_ratio=float(eng_taper_ratio),
        band_profile=str(band_profile),
        band_width_mm=float(band_width_mm),
        band_thickness_mm=float(band_thickness_mm),
        notch_depth_mm=float(notch_depth_mm),
        notch_width_mm=float(notch_width_mm),
        contour_style=str(contour_style),
    )
    spec.validate()
    d = spec.to_dict(id_mm)

    return {
        "circumference_mm": round(circ_mm, 4),
        "size_system": system,
        "ring_size": ring_size,
        **d,
    }


def compute_cocktail_ring_params(
    ring_size,
    system: str = "us",
    shank_profile: str = "tapered",
    shoulder_style: str = "plain",
    band_width_mm: float = 4.0,
    thickness_mm: float = 1.8,
    taper_ratio: float = 0.7,
    mount_style: str = "dome",
    mount_diameter_mm: float = 18.0,
    mount_height_mm: float = 8.0,
    stone_diameter_mm: float = 14.0,
) -> dict:
    """Compute validated cocktail ring descriptor.

    Returns a dict suitable for a ``cocktail_ring`` feature node.
    """
    id_mm = ring_size_to_diameter(system, ring_size)
    circ_mm = _id_mm_to_circumference(id_mm)

    spec = CocktailRingSpec(
        ring_size=ring_size,
        system=system,
        shank_profile=str(shank_profile),
        shoulder_style=str(shoulder_style),
        band_width_mm=float(band_width_mm),
        thickness_mm=float(thickness_mm),
        taper_ratio=float(taper_ratio),
        mount_style=str(mount_style),
        mount_diameter_mm=float(mount_diameter_mm),
        mount_height_mm=float(mount_height_mm),
        stone_diameter_mm=float(stone_diameter_mm),
    )
    spec.validate()
    d = spec.to_dict(id_mm)

    return {
        "circumference_mm": round(circ_mm, 4),
        "size_system": system,
        "ring_size": ring_size,
        **d,
    }


def compute_bypass_ring_params(
    ring_size,
    system: str = "us",
    cross_style: str = "crossover",
    profile: str = "half_round",
    band_width_mm: float = 3.0,
    thickness_mm: float = 1.5,
    bypass_offset_mm: float = 4.0,
    overlap_deg: float = 20.0,
    stone_a_diameter_mm: float = 6.0,
    stone_b_diameter_mm: float = 6.0,
    mount_height_mm: float = 4.5,
) -> dict:
    """Compute validated bypass / toi-et-moi ring descriptor.

    Returns a dict suitable for a ``bypass_ring`` feature node.
    """
    id_mm = ring_size_to_diameter(system, ring_size)
    circ_mm = _id_mm_to_circumference(id_mm)

    spec = BypassRingSpec(
        ring_size=ring_size,
        system=system,
        cross_style=str(cross_style),
        profile=str(profile),
        band_width_mm=float(band_width_mm),
        thickness_mm=float(thickness_mm),
        bypass_offset_mm=float(bypass_offset_mm),
        overlap_deg=float(overlap_deg),
        stone_a_diameter_mm=float(stone_a_diameter_mm),
        stone_b_diameter_mm=float(stone_b_diameter_mm),
        mount_height_mm=float(mount_height_mm),
    )
    spec.validate()
    d = spec.to_dict(id_mm)

    return {
        "circumference_mm": round(circ_mm, 4),
        "size_system": system,
        "ring_size": ring_size,
        **d,
    }


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_solitaire_ring
# ---------------------------------------------------------------------------

jewelry_create_solitaire_ring_spec = ToolSpec(
    name="jewelry_create_solitaire_ring",
    description=(
        "Append a `solitaire_ring` composite node to a `.feature` file. "
        "Builds a parametric shank + a centre-stone head/setting attach-point hint. "
        "The shank is swept from the chosen profile along the finger circle; "
        "the attach-point at the top carries the head_height_mm and "
        "center_stone_diameter_mm so a downstream setting (prong, bezel) node "
        "can fuse onto it. "
        "shoulder_style='cathedral' (default) adds arched shoulders rising to the head. "
        "shoulder_style='split_shank' splits the band into two prongs near the head. "
        "All dimensions in mm. Ring size is auto-converted to inner diameter. "
        "The node op is `solitaire_ring`; the occtWorker evaluates it via "
        "opSolitaireRing (shank sweep + setting-mount attach-point emission)."
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
                    "US number/string (0–16), UK/AU letter, "
                    "EU circumference mm (41–76), JP integer (1–30)."
                ),
            },
            "system": {
                "type": "string",
                "enum": ["us", "uk", "au", "eu", "jp"],
                "description": "Ring-size standard. Default 'us'.",
            },
            "shank_profile": {
                "type": "string",
                "enum": sorted(_VALID_PROFILES),
                "description": "Shank cross-section profile. Default 'comfort_fit'.",
            },
            "shoulder_style": {
                "type": "string",
                "enum": ["plain", "cathedral", "split_shank", "bypass"],
                "description": (
                    "How the shank meets the head. Default 'cathedral'. "
                    "cathedral = arched shoulders (classic solitaire). "
                    "split_shank = two prongs near the head (halo/split look)."
                ),
            },
            "band_width_mm": {
                "type": "number",
                "description": "Shank band width along the finger axis, mm. > 0. Default 3.0.",
            },
            "thickness_mm": {
                "type": "number",
                "description": "Shank radial wall thickness, mm. > 0. Default 1.6.",
            },
            "head_height_mm": {
                "type": "number",
                "description": (
                    "Height of the setting mount point above the bore centre-plane, mm. "
                    "> 0. Consumed by the downstream setting node. Default 5.0."
                ),
            },
            "center_stone_diameter_mm": {
                "type": "number",
                "description": (
                    "Nominal centre-stone diameter, mm. > 0. "
                    "Stored as the attach-point seat diameter so a gem-seat / "
                    "prong node can resolve correct prong geometry. "
                    "Default 6.5 mm (≈ 1 ct round brilliant)."
                ),
            },
            "taper_ratio": {
                "type": "number",
                "description": (
                    "Width+thickness scale at the back of the shank vs. shoulder. "
                    "(0, 1]. 1.0 = uniform; 0.8 = back is 80% of shoulder. "
                    "Default 1.0."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "ring_size"],
    },
)


@register(jewelry_create_solitaire_ring_spec, write=True)
async def run_jewelry_create_solitaire_ring(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    ring_size = a.get("ring_size", None)
    system = str(a.get("system", "us")).strip().lower()
    shank_profile = str(a.get("shank_profile", "comfort_fit")).strip()
    shoulder_style = str(a.get("shoulder_style", "cathedral")).strip()
    band_width_mm = a.get("band_width_mm", 3.0)
    thickness_mm = a.get("thickness_mm", 1.6)
    head_height_mm = a.get("head_height_mm", 5.0)
    center_stone_diameter_mm = a.get("center_stone_diameter_mm", 6.5)
    taper_ratio = a.get("taper_ratio", 1.0)
    node_id = str(a.get("id", "")).strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if ring_size is None:
        return err_payload("ring_size is required", "BAD_ARGS")
    if system not in _VALID_SYSTEMS:
        return err_payload(
            f"system must be one of {sorted(_VALID_SYSTEMS)}; got {system!r}",
            "BAD_ARGS",
        )
    if shank_profile not in _VALID_PROFILES:
        return err_payload(
            f"shank_profile must be one of {sorted(_VALID_PROFILES)}; "
            f"got {shank_profile!r}", "BAD_ARGS",
        )
    if shoulder_style not in _VALID_SHOULDER_STYLES:
        return err_payload(
            f"shoulder_style must be one of {sorted(_VALID_SHOULDER_STYLES)}; "
            f"got {shoulder_style!r}", "BAD_ARGS",
        )

    try:
        band_width_mm = float(band_width_mm)
        thickness_mm = float(thickness_mm)
        head_height_mm = float(head_height_mm)
        center_stone_diameter_mm = float(center_stone_diameter_mm)
        taper_ratio = float(taper_ratio)
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric param error: {e}", "BAD_ARGS")

    try:
        params = compute_solitaire_ring_params(
            ring_size=ring_size,
            system=system,
            shank_profile=shank_profile,
            shoulder_style=shoulder_style,
            band_width_mm=band_width_mm,
            thickness_mm=thickness_mm,
            head_height_mm=head_height_mm,
            center_stone_diameter_mm=center_stone_diameter_mm,
            taper_ratio=taper_ratio,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = _fetch_feature_file(ctx, fid)
    if err:
        code = "NOT_FOUND" if "not found" in err or "not a feature" in err else "ERROR"
        return err_payload(err, code)

    if not node_id:
        node_id = _next_op_id(content or "", "solitaire_ring")

    node = {"id": node_id, "op": "solitaire_ring", **params}
    doc = _load_feature_doc(content or "")
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
        "op": "solitaire_ring",
        "inner_diameter_mm": params["inner_diameter_mm"],
        "outer_diameter_mm": params["outer_diameter_mm"],
        "shank_profile": shank_profile,
        "shoulder_style": shoulder_style,
        "head_height_mm": params["head_height_mm"],
        "center_stone_diameter_mm": params["center_stone_diameter_mm"],
        "attach_points": params["attach_points"],
    })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_mens_band
# ---------------------------------------------------------------------------

jewelry_create_mens_band_spec = ToolSpec(
    name="jewelry_create_mens_band",
    description=(
        "Append a `mens_band` node to a `.feature` file. "
        "Builds a wider comfort/euro/bevel-style men's band with optional "
        "centre groove / inlay channel, milgrain-edge hint, and surface-finish hint. "
        "Valid profiles: comfort_fit (default), euro, d_shape, flat, cigar_band, "
        "bombe, concave, square, half_round. "
        "groove_depth_mm > 0 adds a centre groove (inlay channel) geometry hint. "
        "milgrain_edges=true adds a milgrain bead row on both outer edges. "
        "surface_finish options: polished (default), matte, hammered, satin, brushed. "
        "All dimensions in mm. Ring size is auto-converted to inner diameter. "
        "The node op is `mens_band`."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "ring_size": {
                "description": "Size in the chosen system.",
            },
            "system": {
                "type": "string",
                "enum": ["us", "uk", "au", "eu", "jp"],
                "description": "Ring-size standard. Default 'us'.",
            },
            "profile": {
                "type": "string",
                "enum": sorted(_VALID_MENS_PROFILES),
                "description": "Cross-section profile. Default 'comfort_fit'.",
            },
            "band_width_mm": {
                "type": "number",
                "description": "Band width along the finger axis, mm. > 0. Default 8.0.",
            },
            "thickness_mm": {
                "type": "number",
                "description": "Radial wall thickness, mm. > 0. Default 2.0.",
            },
            "taper_ratio": {
                "type": "number",
                "description": (
                    "Width+thickness scale at back of shank vs. shoulder. "
                    "> 0; 1.0 = uniform. Default 1.0."
                ),
            },
            "groove_depth_mm": {
                "type": "number",
                "description": (
                    "Depth of optional centre groove / inlay channel, mm. "
                    "0 = no groove; if > 0 must be < thickness_mm / 2. Default 0."
                ),
            },
            "groove_width_mm": {
                "type": "number",
                "description": (
                    "Width of the groove / inlay channel, mm. "
                    "> 0; < band_width_mm. Required when groove_depth_mm > 0. Default 1.5."
                ),
            },
            "milgrain_edges": {
                "type": "boolean",
                "description": (
                    "Geometry hint: add milgrain bead row on both outer edges. "
                    "Default false."
                ),
            },
            "milgrain_bead_diameter_mm": {
                "type": "number",
                "description": (
                    "Milgrain bead diameter, mm. > 0. "
                    "Only used when milgrain_edges=true. Default 0.5."
                ),
            },
            "surface_finish": {
                "type": "string",
                "enum": sorted(_VALID_MENS_SURFACE_HINTS),
                "description": (
                    "Surface finish hint for the occtWorker. "
                    "Default 'polished'."
                ),
            },
            "hammered_facet_count": {
                "type": "integer",
                "description": (
                    "Number of facets for hammered surface finish. "
                    "4–128. Default 32."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "ring_size"],
    },
)


@register(jewelry_create_mens_band_spec, write=True)
async def run_jewelry_create_mens_band(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    ring_size = a.get("ring_size", None)
    system = str(a.get("system", "us")).strip().lower()
    profile = str(a.get("profile", "comfort_fit")).strip()
    band_width_mm = a.get("band_width_mm", 8.0)
    thickness_mm = a.get("thickness_mm", 2.0)
    taper_ratio = a.get("taper_ratio", 1.0)
    groove_depth_mm = a.get("groove_depth_mm", 0.0)
    groove_width_mm = a.get("groove_width_mm", 1.5)
    milgrain_edges = bool(a.get("milgrain_edges", False))
    milgrain_bead_diameter_mm = a.get("milgrain_bead_diameter_mm", 0.5)
    surface_finish = str(a.get("surface_finish", "polished")).strip()
    hammered_facet_count = a.get("hammered_facet_count", 32)
    node_id = str(a.get("id", "")).strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if ring_size is None:
        return err_payload("ring_size is required", "BAD_ARGS")
    if system not in _VALID_SYSTEMS:
        return err_payload(
            f"system must be one of {sorted(_VALID_SYSTEMS)}; got {system!r}",
            "BAD_ARGS",
        )
    if profile not in _VALID_MENS_PROFILES:
        return err_payload(
            f"profile must be one of {sorted(_VALID_MENS_PROFILES)}; "
            f"got {profile!r}", "BAD_ARGS",
        )
    if surface_finish not in _VALID_MENS_SURFACE_HINTS:
        return err_payload(
            f"surface_finish must be one of {sorted(_VALID_MENS_SURFACE_HINTS)}; "
            f"got {surface_finish!r}", "BAD_ARGS",
        )

    try:
        band_width_mm = float(band_width_mm)
        thickness_mm = float(thickness_mm)
        taper_ratio = float(taper_ratio)
        groove_depth_mm = float(groove_depth_mm)
        groove_width_mm = float(groove_width_mm)
        milgrain_bead_diameter_mm = float(milgrain_bead_diameter_mm)
        hammered_facet_count = int(hammered_facet_count)
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric param error: {e}", "BAD_ARGS")

    try:
        params = compute_mens_band_params(
            ring_size=ring_size,
            system=system,
            profile=profile,
            band_width_mm=band_width_mm,
            thickness_mm=thickness_mm,
            taper_ratio=taper_ratio,
            groove_depth_mm=groove_depth_mm,
            groove_width_mm=groove_width_mm,
            milgrain_edges=milgrain_edges,
            milgrain_bead_diameter_mm=milgrain_bead_diameter_mm,
            surface_finish=surface_finish,
            hammered_facet_count=hammered_facet_count,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = _fetch_feature_file(ctx, fid)
    if err:
        code = "NOT_FOUND" if "not found" in err or "not a feature" in err else "ERROR"
        return err_payload(err, code)

    if not node_id:
        node_id = _next_op_id(content or "", "mens_band")

    node = {"id": node_id, "op": "mens_band", **params}
    doc = _load_feature_doc(content or "")
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
        "op": "mens_band",
        "inner_diameter_mm": params["inner_diameter_mm"],
        "outer_diameter_mm": params["outer_diameter_mm"],
        "profile": params["profile"],
        "band_width_mm": params["band_width_mm"],
        "thickness_mm": params["thickness_mm"],
        "surface_finish": params["surface_finish"],
    })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_wedding_set
# ---------------------------------------------------------------------------

jewelry_create_wedding_set_spec = ToolSpec(
    name="jewelry_create_wedding_set",
    description=(
        "Append a `wedding_set` composite node to a `.feature` file. "
        "Produces an engagement ring + a matched contoured wedding band as a "
        "paired output in one node.  Both rings share the same ring size. "
        "The wedding band's contour match_radius is auto-derived from the "
        "engagement ring's outer radius so the two sit flush on the finger. "
        "engagement ring params are prefixed with 'eng_'; wedding band params "
        "are prefixed with 'band_'. "
        "All dimensions in mm. Ring size is auto-converted to inner diameter. "
        "The node op is `wedding_set`; sub-ops are `ring_shank` and `contoured_band`."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "ring_size": {
                "description": "Shared ring size (same finger) in the chosen system.",
            },
            "system": {
                "type": "string",
                "enum": ["us", "uk", "au", "eu", "jp"],
                "description": "Ring-size standard. Default 'us'.",
            },
            "eng_profile": {
                "type": "string",
                "enum": sorted(_VALID_PROFILES),
                "description": "Engagement ring shank profile. Default 'comfort_fit'.",
            },
            "eng_shoulder_style": {
                "type": "string",
                "enum": ["plain", "cathedral", "split_shank", "bypass"],
                "description": "Engagement ring shoulder style. Default 'cathedral'.",
            },
            "eng_band_width_mm": {
                "type": "number",
                "description": "Engagement ring band width, mm. > 0. Default 2.5.",
            },
            "eng_thickness_mm": {
                "type": "number",
                "description": "Engagement ring wall thickness, mm. > 0. Default 1.6.",
            },
            "eng_taper_ratio": {
                "type": "number",
                "description": "Engagement ring taper ratio. > 0. Default 1.0.",
            },
            "band_profile": {
                "type": "string",
                "enum": ["flat", "half_round", "comfort_fit", "d_shape", "euro"],
                "description": "Wedding band lower shank profile. Default 'flat'.",
            },
            "band_width_mm": {
                "type": "number",
                "description": "Wedding band width, mm. > 0. Default 3.0.",
            },
            "band_thickness_mm": {
                "type": "number",
                "description": "Wedding band wall thickness, mm. > 0. Default 1.6.",
            },
            "notch_depth_mm": {
                "type": "number",
                "description": (
                    "Depth of the contour notch in the wedding band, mm. "
                    "> 0; < band_thickness_mm. Default 1.2."
                ),
            },
            "notch_width_mm": {
                "type": "number",
                "description": (
                    "Width of the contour notch, mm. "
                    "> 0; ≤ band_width_mm. Default 2.5."
                ),
            },
            "contour_style": {
                "type": "string",
                "enum": ["curved", "notched"],
                "description": (
                    "Wedding band contour style. "
                    "'curved' = smooth arc (shadow band); "
                    "'notched' = V/U notch. Default 'curved'."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "ring_size"],
    },
)


@register(jewelry_create_wedding_set_spec, write=True)
async def run_jewelry_create_wedding_set(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    ring_size = a.get("ring_size", None)
    system = str(a.get("system", "us")).strip().lower()
    eng_profile = str(a.get("eng_profile", "comfort_fit")).strip()
    eng_shoulder_style = str(a.get("eng_shoulder_style", "cathedral")).strip()
    eng_band_width_mm = a.get("eng_band_width_mm", 2.5)
    eng_thickness_mm = a.get("eng_thickness_mm", 1.6)
    eng_taper_ratio = a.get("eng_taper_ratio", 1.0)
    band_profile = str(a.get("band_profile", "flat")).strip()
    band_width_mm = a.get("band_width_mm", 3.0)
    band_thickness_mm = a.get("band_thickness_mm", 1.6)
    notch_depth_mm = a.get("notch_depth_mm", 1.2)
    notch_width_mm = a.get("notch_width_mm", 2.5)
    contour_style = str(a.get("contour_style", "curved")).strip()
    node_id = str(a.get("id", "")).strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if ring_size is None:
        return err_payload("ring_size is required", "BAD_ARGS")
    if system not in _VALID_SYSTEMS:
        return err_payload(
            f"system must be one of {sorted(_VALID_SYSTEMS)}; got {system!r}",
            "BAD_ARGS",
        )

    _VALID_BAND_PROFILES_LOCAL = frozenset([
        "flat", "half_round", "comfort_fit", "d_shape", "euro",
    ])
    _VALID_CONTOUR_LOCAL = frozenset(["curved", "notched"])

    if eng_profile not in _VALID_PROFILES:
        return err_payload(
            f"eng_profile must be one of {sorted(_VALID_PROFILES)}; "
            f"got {eng_profile!r}", "BAD_ARGS",
        )
    if eng_shoulder_style not in _VALID_SHOULDER_STYLES:
        return err_payload(
            f"eng_shoulder_style must be one of {sorted(_VALID_SHOULDER_STYLES)}; "
            f"got {eng_shoulder_style!r}", "BAD_ARGS",
        )
    if band_profile not in _VALID_BAND_PROFILES_LOCAL:
        return err_payload(
            f"band_profile must be one of {sorted(_VALID_BAND_PROFILES_LOCAL)}; "
            f"got {band_profile!r}", "BAD_ARGS",
        )
    if contour_style not in _VALID_CONTOUR_LOCAL:
        return err_payload(
            f"contour_style must be one of {sorted(_VALID_CONTOUR_LOCAL)}; "
            f"got {contour_style!r}", "BAD_ARGS",
        )

    try:
        eng_band_width_mm = float(eng_band_width_mm)
        eng_thickness_mm = float(eng_thickness_mm)
        eng_taper_ratio = float(eng_taper_ratio)
        band_width_mm = float(band_width_mm)
        band_thickness_mm = float(band_thickness_mm)
        notch_depth_mm = float(notch_depth_mm)
        notch_width_mm = float(notch_width_mm)
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric param error: {e}", "BAD_ARGS")

    try:
        params = compute_wedding_set_params(
            ring_size=ring_size,
            system=system,
            eng_profile=eng_profile,
            eng_shoulder_style=eng_shoulder_style,
            eng_band_width_mm=eng_band_width_mm,
            eng_thickness_mm=eng_thickness_mm,
            eng_taper_ratio=eng_taper_ratio,
            band_profile=band_profile,
            band_width_mm=band_width_mm,
            band_thickness_mm=band_thickness_mm,
            notch_depth_mm=notch_depth_mm,
            notch_width_mm=notch_width_mm,
            contour_style=contour_style,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = _fetch_feature_file(ctx, fid)
    if err:
        code = "NOT_FOUND" if "not found" in err or "not a feature" in err else "ERROR"
        return err_payload(err, code)

    if not node_id:
        node_id = _next_op_id(content or "", "wedding_set")

    node = {"id": node_id, "op": "wedding_set", **params}
    doc = _load_feature_doc(content or "")
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
        "op": "wedding_set",
        "inner_diameter_mm": params["inner_diameter_mm"],
        "match_radius_mm": params["match_radius_mm"],
        "composite_ops": params["composite_ops"],
    })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_cocktail_ring
# ---------------------------------------------------------------------------

jewelry_create_cocktail_ring_spec = ToolSpec(
    name="jewelry_create_cocktail_ring",
    description=(
        "Append a `cocktail_ring` composite node to a `.feature` file. "
        "Builds a tapered shank + a large dome/cluster/bezel/prong top-mount "
        "attach-point hint.  The shank tapers from a wider shoulder down to "
        "a slimmer back, leading into a large platform mount at the top. "
        "The attach-point hint carries mount_style, mount_diameter_mm, "
        "mount_height_mm, and stone_diameter_mm so a downstream gem-seat node "
        "can resolve the correct mount geometry. "
        "All dimensions in mm. Ring size is auto-converted to inner diameter. "
        "The node op is `cocktail_ring`."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "ring_size": {
                "description": "Size in the chosen system.",
            },
            "system": {
                "type": "string",
                "enum": ["us", "uk", "au", "eu", "jp"],
                "description": "Ring-size standard. Default 'us'.",
            },
            "shank_profile": {
                "type": "string",
                "enum": sorted(_VALID_PROFILES),
                "description": "Shank cross-section profile. Default 'tapered'.",
            },
            "shoulder_style": {
                "type": "string",
                "enum": ["plain", "cathedral", "split_shank", "bypass"],
                "description": "Shank shoulder style. Default 'plain'.",
            },
            "band_width_mm": {
                "type": "number",
                "description": "Shank band width at shoulder (widest), mm. > 0. Default 4.0.",
            },
            "thickness_mm": {
                "type": "number",
                "description": "Shank radial wall thickness at shoulder, mm. > 0. Default 1.8.",
            },
            "taper_ratio": {
                "type": "number",
                "description": (
                    "Width+thickness scale at back vs. shoulder. (0, 1]. "
                    "Default 0.7 (back = 70% of shoulder)."
                ),
            },
            "mount_style": {
                "type": "string",
                "enum": sorted(_VALID_COCKTAIL_MOUNT_STYLES),
                "description": "Style of the top mount platform. Default 'dome'.",
            },
            "mount_diameter_mm": {
                "type": "number",
                "description": (
                    "Outer diameter of the top mount platform, mm. > 0. "
                    "Default 18.0 mm."
                ),
            },
            "mount_height_mm": {
                "type": "number",
                "description": (
                    "Height of the mount platform above bore centre-plane, mm. "
                    "> 0. Default 8.0."
                ),
            },
            "stone_diameter_mm": {
                "type": "number",
                "description": (
                    "Diameter of the centre stone or cluster, mm. "
                    "> 0; ≤ mount_diameter_mm. Default 14.0."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "ring_size"],
    },
)


@register(jewelry_create_cocktail_ring_spec, write=True)
async def run_jewelry_create_cocktail_ring(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    ring_size = a.get("ring_size", None)
    system = str(a.get("system", "us")).strip().lower()
    shank_profile = str(a.get("shank_profile", "tapered")).strip()
    shoulder_style = str(a.get("shoulder_style", "plain")).strip()
    band_width_mm = a.get("band_width_mm", 4.0)
    thickness_mm = a.get("thickness_mm", 1.8)
    taper_ratio = a.get("taper_ratio", 0.7)
    mount_style = str(a.get("mount_style", "dome")).strip()
    mount_diameter_mm = a.get("mount_diameter_mm", 18.0)
    mount_height_mm = a.get("mount_height_mm", 8.0)
    stone_diameter_mm = a.get("stone_diameter_mm", 14.0)
    node_id = str(a.get("id", "")).strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if ring_size is None:
        return err_payload("ring_size is required", "BAD_ARGS")
    if system not in _VALID_SYSTEMS:
        return err_payload(
            f"system must be one of {sorted(_VALID_SYSTEMS)}; got {system!r}",
            "BAD_ARGS",
        )
    if shank_profile not in _VALID_PROFILES:
        return err_payload(
            f"shank_profile must be one of {sorted(_VALID_PROFILES)}; "
            f"got {shank_profile!r}", "BAD_ARGS",
        )
    if shoulder_style not in _VALID_SHOULDER_STYLES:
        return err_payload(
            f"shoulder_style must be one of {sorted(_VALID_SHOULDER_STYLES)}; "
            f"got {shoulder_style!r}", "BAD_ARGS",
        )
    if mount_style not in _VALID_COCKTAIL_MOUNT_STYLES:
        return err_payload(
            f"mount_style must be one of {sorted(_VALID_COCKTAIL_MOUNT_STYLES)}; "
            f"got {mount_style!r}", "BAD_ARGS",
        )

    try:
        band_width_mm = float(band_width_mm)
        thickness_mm = float(thickness_mm)
        taper_ratio = float(taper_ratio)
        mount_diameter_mm = float(mount_diameter_mm)
        mount_height_mm = float(mount_height_mm)
        stone_diameter_mm = float(stone_diameter_mm)
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric param error: {e}", "BAD_ARGS")

    try:
        params = compute_cocktail_ring_params(
            ring_size=ring_size,
            system=system,
            shank_profile=shank_profile,
            shoulder_style=shoulder_style,
            band_width_mm=band_width_mm,
            thickness_mm=thickness_mm,
            taper_ratio=taper_ratio,
            mount_style=mount_style,
            mount_diameter_mm=mount_diameter_mm,
            mount_height_mm=mount_height_mm,
            stone_diameter_mm=stone_diameter_mm,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = _fetch_feature_file(ctx, fid)
    if err:
        code = "NOT_FOUND" if "not found" in err or "not a feature" in err else "ERROR"
        return err_payload(err, code)

    if not node_id:
        node_id = _next_op_id(content or "", "cocktail_ring")

    node = {"id": node_id, "op": "cocktail_ring", **params}
    doc = _load_feature_doc(content or "")
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
        "op": "cocktail_ring",
        "inner_diameter_mm": params["inner_diameter_mm"],
        "outer_diameter_mm": params["outer_diameter_mm"],
        "mount_style": params["mount_style"],
        "mount_diameter_mm": params["mount_diameter_mm"],
        "mount_height_mm": params["mount_height_mm"],
        "stone_diameter_mm": params["stone_diameter_mm"],
        "attach_points": params["attach_points"],
    })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_bypass_ring
# ---------------------------------------------------------------------------

jewelry_create_bypass_ring_spec = ToolSpec(
    name="jewelry_create_bypass_ring",
    description=(
        "Append a `bypass_ring` composite node to a `.feature` file. "
        "Builds a two-element crossover or toi-et-moi ring with two stone "
        "mount attach-points. "
        "cross_style='crossover': two arms cross over each other at the top "
        "(offset in Z); each arm ends near the 12-o'clock position. "
        "cross_style='toi_et_moi': two arms run side by side, placing two "
        "stones at lateral offsets from the centreline (classic toi-et-moi). "
        "Each arm terminates in an attach-point hint with the stone diameter "
        "and lateral offset for a downstream gem-seat node. "
        "All dimensions in mm. Ring size is auto-converted to inner diameter. "
        "The node op is `bypass_ring`."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "ring_size": {
                "description": "Size in the chosen system.",
            },
            "system": {
                "type": "string",
                "enum": ["us", "uk", "au", "eu", "jp"],
                "description": "Ring-size standard. Default 'us'.",
            },
            "cross_style": {
                "type": "string",
                "enum": ["crossover", "toi_et_moi"],
                "description": (
                    "Two-element shank style. "
                    "'crossover' = arms visually intersect at the top. "
                    "'toi_et_moi' = two stones side by side. "
                    "Default 'crossover'."
                ),
            },
            "profile": {
                "type": "string",
                "enum": sorted(_VALID_PROFILES),
                "description": "Cross-section profile for each arm. Default 'half_round'.",
            },
            "band_width_mm": {
                "type": "number",
                "description": "Width of each arm, mm. > 0. Default 3.0.",
            },
            "thickness_mm": {
                "type": "number",
                "description": "Radial wall thickness of each arm, mm. > 0. Default 1.5.",
            },
            "bypass_offset_mm": {
                "type": "number",
                "description": (
                    "Lateral offset of each arm end from the centreline, mm. "
                    "> 0. Controls stone seat separation. Default 4.0."
                ),
            },
            "overlap_deg": {
                "type": "number",
                "description": (
                    "Degrees past 12-o'clock that each arm extends before "
                    "terminating. 0–90. Default 20."
                ),
            },
            "stone_a_diameter_mm": {
                "type": "number",
                "description": "Diameter of stone for arm A, mm. > 0. Default 6.0.",
            },
            "stone_b_diameter_mm": {
                "type": "number",
                "description": "Diameter of stone for arm B, mm. > 0. Default 6.0.",
            },
            "mount_height_mm": {
                "type": "number",
                "description": (
                    "Height of each stone mount above bore centre-plane, mm. "
                    "> 0. Default 4.5."
                ),
            },
            "id": {
                "type": "string",
                "description": "Optional explicit node id.",
            },
        },
        "required": ["file_id", "ring_size"],
    },
)


@register(jewelry_create_bypass_ring_spec, write=True)
async def run_jewelry_create_bypass_ring(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    ring_size = a.get("ring_size", None)
    system = str(a.get("system", "us")).strip().lower()
    cross_style = str(a.get("cross_style", "crossover")).strip()
    profile = str(a.get("profile", "half_round")).strip()
    band_width_mm = a.get("band_width_mm", 3.0)
    thickness_mm = a.get("thickness_mm", 1.5)
    bypass_offset_mm = a.get("bypass_offset_mm", 4.0)
    overlap_deg = a.get("overlap_deg", 20.0)
    stone_a_diameter_mm = a.get("stone_a_diameter_mm", 6.0)
    stone_b_diameter_mm = a.get("stone_b_diameter_mm", 6.0)
    mount_height_mm = a.get("mount_height_mm", 4.5)
    node_id = str(a.get("id", "")).strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if ring_size is None:
        return err_payload("ring_size is required", "BAD_ARGS")
    if system not in _VALID_SYSTEMS:
        return err_payload(
            f"system must be one of {sorted(_VALID_SYSTEMS)}; got {system!r}",
            "BAD_ARGS",
        )
    if cross_style not in _VALID_BYPASS_CROSS_STYLES:
        return err_payload(
            f"cross_style must be one of {sorted(_VALID_BYPASS_CROSS_STYLES)}; "
            f"got {cross_style!r}", "BAD_ARGS",
        )
    if profile not in _VALID_PROFILES:
        return err_payload(
            f"profile must be one of {sorted(_VALID_PROFILES)}; "
            f"got {profile!r}", "BAD_ARGS",
        )

    try:
        band_width_mm = float(band_width_mm)
        thickness_mm = float(thickness_mm)
        bypass_offset_mm = float(bypass_offset_mm)
        overlap_deg = float(overlap_deg)
        stone_a_diameter_mm = float(stone_a_diameter_mm)
        stone_b_diameter_mm = float(stone_b_diameter_mm)
        mount_height_mm = float(mount_height_mm)
    except (TypeError, ValueError) as e:
        return err_payload(f"numeric param error: {e}", "BAD_ARGS")

    try:
        params = compute_bypass_ring_params(
            ring_size=ring_size,
            system=system,
            cross_style=cross_style,
            profile=profile,
            band_width_mm=band_width_mm,
            thickness_mm=thickness_mm,
            bypass_offset_mm=bypass_offset_mm,
            overlap_deg=overlap_deg,
            stone_a_diameter_mm=stone_a_diameter_mm,
            stone_b_diameter_mm=stone_b_diameter_mm,
            mount_height_mm=mount_height_mm,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = _fetch_feature_file(ctx, fid)
    if err:
        code = "NOT_FOUND" if "not found" in err or "not a feature" in err else "ERROR"
        return err_payload(err, code)

    if not node_id:
        node_id = _next_op_id(content or "", "bypass_ring")

    node = {"id": node_id, "op": "bypass_ring", **params}
    doc = _load_feature_doc(content or "")
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
        "op": "bypass_ring",
        "inner_diameter_mm": params["inner_diameter_mm"],
        "outer_diameter_mm": params["outer_diameter_mm"],
        "cross_style": params["cross_style"],
        "profile": params["profile"],
        "bypass_offset_mm": params["bypass_offset_mm"],
        "stone_a_diameter_mm": params["stone_a_diameter_mm"],
        "stone_b_diameter_mm": params["stone_b_diameter_mm"],
        "attach_points": params["attach_points"],
    })
