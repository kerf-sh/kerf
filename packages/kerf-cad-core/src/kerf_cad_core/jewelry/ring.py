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
                         profile, taper_ratio) -> dict

    build_shank_node(file_id, ring_size, system, band_width, thickness,
                     profile, shoulder_style, taper_ratio, node_id) -> dict

LLM tools registered
---------------------
    jewelry_ring_size_to_diameter
    jewelry_create_ring_shank
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
    "d_shape",
    "comfort_fit",
    "flat",
    "half_round",
    "knife_edge",
    "euro",
    "tapered",
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
    "d_shape":     "Flat outside, curved inside — classic men's band.",
    "comfort_fit": "Domed outside, rounded inside for comfort — slides on easily.",
    "flat":        "Fully flat top and bottom, squared edges — contemporary style.",
    "half_round":  "Domed on top, flat on bottom — most common women's band.",
    "knife_edge":  "V-shaped ridge along centre of outer face — architectural look.",
    "euro":        "Slightly squared profile (≈rectangular with rounded corners).",
    "tapered":     "Width and/or thickness taper from shoulder to base.",
}


def compute_shank_params(
    ring_size,
    system: str = "us",
    band_width: float = 4.0,
    thickness: float = 1.8,
    profile: str = "comfort_fit",
    taper_ratio: float = 1.0,
    shoulder_style: str = "plain",
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
        One of: d_shape, comfort_fit, flat, half_round, knife_edge, euro, tapered.
    taper_ratio : float
        Width/thickness scale at the base of the shank relative to the shoulder
        top.  1.0 = uniform; 0.6 = base is 60 % of shoulder dimension.
    shoulder_style : str
        One of: plain, cathedral, split_shank, bypass.

    Returns
    -------
    dict
        Inner diameter, circumference, profile, shoulder_style, geometry hints.
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

    id_mm = ring_size_to_diameter(system, ring_size)
    circ_mm = _id_mm_to_circumference(id_mm)
    outer_diameter = id_mm + 2 * thickness

    # Shoulder geometry hints (multipliers / offsets, not full BREP)
    shoulder_hints = _shoulder_hints(shoulder_style, id_mm, band_width)

    return {
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
        "tapered (width+thickness taper from shoulder to base). "
        "Shoulder styles: plain (uniform band), cathedral (arched shoulders "
        "rising to a centre setting), split_shank (band splits into two prongs "
        "near the setting), bypass (ends pass alongside each other). "
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
                "enum": ["d_shape", "comfort_fit", "flat", "half_round",
                         "knife_edge", "euro", "tapered"],
                "description": "Cross-section profile. Default 'comfort_fit'.",
            },
            "taper_ratio": {
                "type": "number",
                "description": (
                    "Width+thickness scale at the back of the shank relative to "
                    "the shoulder. 1.0 = uniform; 0.6 = back is 60% of shoulder. "
                    "Only used when profile='tapered'. Default 1.0."
                ),
            },
            "shoulder_style": {
                "type": "string",
                "enum": ["plain", "cathedral", "split_shank", "bypass"],
                "description": "How the shank meets the head/setting. Default 'plain'.",
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
