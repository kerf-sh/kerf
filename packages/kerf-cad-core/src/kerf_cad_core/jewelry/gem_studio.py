"""
MatrixGold-style gem studio + cutter library.

Capabilities
------------
gem_cutter_spec()
    For every supported cut (round_brilliant, princess, emerald, asscher,
    oval, marquise, pear, cushion, radiant, baguette, trillion, heart,
    briolette, rose_cut, cabochon) produce:
      - the gemstone solid spec (proportions dict identical in shape to
        GemProportions from gemstones.py)
      - a matching boolean **cutter** solid specification sized with
        configurable girdle clearance, culet allowance, and table offset —
        ready to boolean-subtract from a setting host

gem_catalog_lookup()
    Rich catalog: for each material return carat↔mm reference dimensions,
    refractive index, dispersion, hardness (Mohs), typical colour grades,
    price-per-carat band, density.

gem_fit_check()
    Given a cutter spec and a metal wall thickness, report whether the
    cutter fits safely and emit min-clearance warnings.

melee_sequence()
    Auto-size a row of melee/accent stones: given total channel length,
    stone cut, and target carat, return a list of sized stone positions and
    cutter specs ready for channel-set layout.

LLM-facing tools (registered via @register)
--------------------------------------------
  jewelry_gem_studio_cutter       — parametric cutter spec for any cut
  jewelry_gem_studio_catalog      — material / optical / price catalog
  jewelry_gem_studio_fit_check    — fit + clearance validation
  jewelry_gem_studio_melee_seq    — melee auto-sizing sequencer
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

from kerf_cad_core.jewelry.gemstones import (
    GEMSTONE_CUTS,
    GEMSTONE_DENSITIES,
    GEM_CATALOG,
    _CARAT_REF,
    _CUT_DEFAULTS,
    _DIAMOND_DENSITY,
    carat_from_mm,
    mm_from_carat,
    gemstone_proportions,
)


# ---------------------------------------------------------------------------
# Gem studio supported cuts (subset of GEMSTONE_CUTS with cutter geometry)
# ---------------------------------------------------------------------------

GEM_STUDIO_CUTS = {
    "round_brilliant",
    "princess",
    "emerald",
    "asscher",
    "oval",
    "marquise",
    "pear",
    "cushion",
    "radiant",
    "baguette",
    "trillion",
    "heart",
    "briolette",
    "rose_cut",
    "cabochon",
}

# ---------------------------------------------------------------------------
# Extended optical + price catalog
# ---------------------------------------------------------------------------
# Each entry adds optical / trade data beyond the base GEM_CATALOG.
#
# Sources:
#   GIA Gem Reference Guide (Liddicoat, GIA 1995)
#   GIA Gem Encyclopedia 2014
#   International Gem Society (IGS) property tables
#   AGS/GIA 4Cs colour grade scale
#   Gemval / GemPrice industry price-per-carat orientation data (2023–2024)
#   Note: price_per_ct_band is orientation-only; verify with current market.

GEM_STUDIO_CATALOG: dict[str, dict] = {
    "diamond": {
        "density":          3.51,
        "ri":               (2.417, 2.419),
        "dispersion":       0.044,     # fire (B–G interval)
        "mohs":             10.0,
        "colour_grades":    ["D", "E", "F", "G", "H", "I", "J", "K–Z", "Fancy"],
        "clarity_grades":   ["FL", "IF", "VVS1", "VVS2", "VS1", "VS2", "SI1", "SI2", "I1", "I2", "I3"],
        "price_per_ct_band": (3_000, 25_000),   # USD; 1-ct round, D-I / VS orientation
        "typical_cuts":     ["round_brilliant", "princess", "cushion", "oval", "pear",
                             "marquise", "radiant", "asscher", "heart", "emerald"],
        "notes":            "Isotropic cubic; highest dispersion of common gem minerals.",
    },
    "ruby": {
        "density":          3.99,
        "ri":               (1.762, 1.770),
        "dispersion":       0.018,
        "mohs":             9.0,
        "colour_grades":    ["Pinkish-red", "Red", "Vivid red", "Pigeon's blood"],
        "clarity_grades":   ["Eye-clean", "Slightly included", "Moderately included"],
        "price_per_ct_band": (1_000, 30_000),   # Burmese unheated up to $100k+/ct
        "typical_cuts":     ["oval", "cushion", "round_brilliant", "pear", "emerald"],
        "notes":            "Corundum; finest are unheated Burmese 'pigeon's blood' red.",
    },
    "sapphire": {
        "density":          4.00,
        "ri":               (1.762, 1.770),
        "dispersion":       0.018,
        "mohs":             9.0,
        "colour_grades":    ["Cornflower blue", "Royal blue", "Kashmir blue", "Padparadscha",
                             "Yellow", "Pink", "Parti"],
        "clarity_grades":   ["Eye-clean", "Slightly included", "Moderately included"],
        "price_per_ct_band": (500, 20_000),
        "typical_cuts":     ["oval", "cushion", "round_brilliant", "princess", "pear"],
        "notes":            "Corundum; same mineral as ruby; wide colour range.",
    },
    "emerald": {
        "density":          2.72,
        "ri":               (1.565, 1.602),
        "dispersion":       0.014,
        "mohs":             7.75,     # midpoint of 7.5–8.0
        "colour_grades":    ["Light green", "Medium green", "Vivid green", "Deep green"],
        "clarity_grades":   ["Eye-clean", "Slightly jardin", "Jardin"],
        "price_per_ct_band": (500, 15_000),
        "typical_cuts":     ["emerald", "oval", "cushion", "pear", "round_brilliant"],
        "notes":            "Beryl; jardin (inclusions/fissures) are expected and accepted.",
    },
    "amethyst": {
        "density":          2.65,
        "ri":               (1.544, 1.553),
        "dispersion":       0.013,
        "mohs":             7.0,
        "colour_grades":    ["Pale lilac", "Medium purple", "Deep purple", "Siberian (vivid)"],
        "clarity_grades":   ["Eye-clean", "Slightly included"],
        "price_per_ct_band": (5, 50),
        "typical_cuts":     ["round_brilliant", "oval", "cushion", "pear", "trillion"],
        "notes":            "Quartz; heat treatment can lighten or produce citrine.",
    },
    "aquamarine": {
        "density":          2.72,
        "ri":               (1.567, 1.590),
        "dispersion":       0.014,
        "mohs":             7.75,
        "colour_grades":    ["Pale blue", "Medium blue", "Santa Maria blue", "Blue-green"],
        "clarity_grades":   ["Eye-clean", "Slightly included"],
        "price_per_ct_band": (50, 600),
        "typical_cuts":     ["emerald", "oval", "round_brilliant", "pear", "cushion"],
        "notes":            "Beryl; finest are deep Santa Maria or Espirito Santo blues.",
    },
    "topaz": {
        "density":          3.53,
        "ri":               (1.609, 1.643),
        "dispersion":       0.014,
        "mohs":             8.0,
        "colour_grades":    ["Imperial orange-yellow", "Pink", "Blue (treated)",
                             "Colourless", "Red"],
        "clarity_grades":   ["Eye-clean", "Slightly included"],
        "price_per_ct_band": (10, 2_000),   # imperial topaz at high end
        "typical_cuts":     ["oval", "cushion", "pear", "round_brilliant", "princess"],
        "notes":            "Perfect cleavage in one direction; handle with care.",
    },
    "garnet": {
        "density":          3.78,
        "ri":               (1.714, 1.888),
        "dispersion":       0.027,     # demantoid has 0.057; typical pyrope/almandine 0.024
        "mohs":             7.0,       # midpoint 6.5–7.5
        "colour_grades":    ["Red", "Orange (spessartine)", "Green (tsavorite/demantoid)",
                             "Purple-red (rhodolite)", "Colour-change"],
        "clarity_grades":   ["Eye-clean", "Slightly included"],
        "price_per_ct_band": (20, 3_000),   # tsavorite/demantoid at high end
        "typical_cuts":     ["round_brilliant", "oval", "cushion", "pear", "trillion"],
        "notes":            "Includes many species; demantoid has higher dispersion than diamond.",
    },
    "peridot": {
        "density":          3.32,
        "ri":               (1.650, 1.703),
        "dispersion":       0.020,
        "mohs":             6.75,
        "colour_grades":    ["Yellowish-green", "Lime green", "Olive green"],
        "clarity_grades":   ["Eye-clean", "Slightly included"],
        "price_per_ct_band": (30, 400),
        "typical_cuts":     ["oval", "round_brilliant", "cushion", "pear", "trillion"],
        "notes":            "Idiochromatic (iron); Myanmar and Zaghabain sources most prized.",
    },
    "citrine": {
        "density":          2.65,
        "ri":               (1.544, 1.553),
        "dispersion":       0.013,
        "mohs":             7.0,
        "colour_grades":    ["Pale yellow", "Golden yellow", "Madeira orange", "Palmeira brown"],
        "clarity_grades":   ["Eye-clean", "Slightly included"],
        "price_per_ct_band": (5, 30),
        "typical_cuts":     ["round_brilliant", "oval", "cushion", "pear", "trillion"],
        "notes":            "Quartz; most heat-treated amethyst or smoky quartz.",
    },
    "tanzanite": {
        "density":          3.35,
        "ri":               (1.691, 1.700),
        "dispersion":       0.021,
        "mohs":             6.5,
        "colour_grades":    ["Violetish-blue", "Blue-violet", "Intense violet-blue"],
        "clarity_grades":   ["Eye-clean", "Slightly included"],
        "price_per_ct_band": (300, 1_200),
        "typical_cuts":     ["oval", "cushion", "round_brilliant", "pear", "trillion"],
        "notes":            "Zoisite; trichroic; single source (Merelani Hills, Tanzania).",
    },
    "spinel": {
        "density":          3.60,
        "ri":               (1.712, 1.762),
        "dispersion":       0.026,
        "mohs":             8.0,
        "colour_grades":    ["Red", "Pink", "Orange", "Blue", "Purple", "Black"],
        "clarity_grades":   ["Eye-clean", "Slightly included"],
        "price_per_ct_band": (200, 5_000),
        "typical_cuts":     ["oval", "cushion", "round_brilliant", "pear"],
        "notes":            "Isotropic; historically confused with ruby; Burmese red most prized.",
    },
    "tourmaline": {
        "density":          3.10,
        "ri":               (1.624, 1.644),
        "dispersion":       0.017,
        "mohs":             7.25,
        "colour_grades":    ["Paraíba neon blue-green", "Rubellite red-pink",
                             "Chrome green", "Watermelon bicolour", "Indicolite blue"],
        "clarity_grades":   ["Eye-clean", "Slightly included"],
        "price_per_ct_band": (50, 10_000),  # Paraíba up to $50k+/ct
        "typical_cuts":     ["oval", "pear", "cushion", "round_brilliant", "emerald"],
        "notes":            "Elbaite most common gem species; Paraíba commands premium.",
    },
    "opal": {
        "density":          2.08,
        "ri":               (1.370, 1.520),
        "dispersion":       0.000,     # amorphous; not measured conventionally
        "mohs":             5.75,
        "colour_grades":    ["White", "Crystal", "Black", "Fire", "Boulder"],
        "clarity_grades":   ["No-crack", "Minor fissure", "Crazing"],
        "price_per_ct_band": (10, 3_000),   # black opal at high end
        "typical_cuts":     ["oval", "cushion", "round_brilliant"],
        "notes":            "Amorphous silica; cabochon most common; sensitive to dehydration.",
    },
    "morganite": {
        "density":          2.71,
        "ri":               (1.572, 1.600),
        "dispersion":       0.014,
        "mohs":             7.75,
        "colour_grades":    ["Pale pink", "Peach-pink", "Rose", "Salmon"],
        "clarity_grades":   ["Eye-clean", "Slightly included"],
        "price_per_ct_band": (100, 800),
        "typical_cuts":     ["oval", "cushion", "round_brilliant", "pear", "heart"],
        "notes":            "Pink beryl; pairs well with rose/yellow gold settings.",
    },
    "alexandrite": {
        "density":          3.73,
        "ri":               (1.746, 1.755),
        "dispersion":       0.015,
        "mohs":             8.75,
        "colour_grades":    ["Green/red (classic)", "Teal/purple (Brazilian)"],
        "clarity_grades":   ["Eye-clean", "Slightly included"],
        "price_per_ct_band": (5_000, 50_000),
        "typical_cuts":     ["oval", "cushion", "round_brilliant", "pear"],
        "notes":            "Chrysoberyl; colour-change; Ural Mountains finest.",
    },
    "moonstone": {
        "density":          2.56,
        "ri":               (1.518, 1.526),
        "dispersion":       0.012,
        "mohs":             6.25,
        "colour_grades":    ["Blue adularescence", "White", "Peach", "Grey-green"],
        "clarity_grades":   ["Eye-clean", "Slightly included"],
        "price_per_ct_band": (10, 250),
        "typical_cuts":     ["oval", "cushion", "round_brilliant"],
        "notes":            "Orthoclase feldspar; adularescence requires cabochon orientation.",
    },
    "zircon": {
        "density":          4.67,
        "ri":               (1.925, 1.984),
        "dispersion":       0.039,
        "mohs":             6.75,
        "colour_grades":    ["Blue (treated)", "Golden-yellow", "Orange", "Red", "Colourless"],
        "clarity_grades":   ["Eye-clean", "Slightly included"],
        "price_per_ct_band": (50, 400),
        "typical_cuts":     ["round_brilliant", "oval", "cushion", "princess"],
        "notes":            "High RI/dispersion; natural (not synthetic CZ).",
    },
}

# ---------------------------------------------------------------------------
# Cabochon cutter parameters (special: no facets, domed top, flat bottom)
# ---------------------------------------------------------------------------

_CABOCHON_DEFAULTS = {
    "table_pct":          0.0,    # no table; full dome
    "crown_angle_deg":    20.0,   # dome slope
    "crown_height_pct":   35.0,   # dome height / diameter
    "pavilion_angle_deg": 0.0,    # flat base
    "pavilion_depth_pct": 2.0,    # thin base ledge
    "girdle_pct":         3.0,
    "aspect_ratio":       1.0,
    "extras":             {"facet_count": 0, "style": "cabochon"},
}

# ---------------------------------------------------------------------------
# Cutter geometry
# ---------------------------------------------------------------------------

def gem_cutter_spec(
    cut: str,
    diameter_mm: float,
    *,
    carat: Optional[float] = None,
    material: Optional[str] = None,
    density_g_cm3: Optional[float] = None,
    # Clearance parameters
    girdle_clearance_mm: float = 0.05,
    culet_allowance_mm: float = 0.10,
    table_offset_mm: float = 0.05,
    seat_allowance_mm: float = 0.02,
    crown_relief_mm: float = 0.30,
    aspect_ratio: Optional[float] = None,
) -> dict:
    """Return a gemstone solid spec + boolean cutter spec for any supported cut.

    For ``cabochon`` the returned geometry reflects a dome solid with a flat
    base bearing ledge.  For ``briolette`` the cutter wraps the full elongated
    teardrop.

    Parameters
    ----------
    cut               : cut name (must be in GEM_STUDIO_CUTS)
    diameter_mm       : primary dimension (girdle diameter for round; long axis otherwise)
                        Ignored when carat is provided (converted via mm_from_carat).
    carat             : alternative to diameter_mm; converted via carat-to-mm formula
    material          : gem material name (e.g. "ruby"); affects carat↔mm conversion
    density_g_cm3     : explicit density override
    girdle_clearance_mm : radial clearance added around the girdle for the cutter
    culet_allowance_mm  : extra axial depth below culet for the cutter
    table_offset_mm     : axial gap between stone table and cutter top opening
    seat_allowance_mm   : extra axial height on girdle ledge
    crown_relief_mm     : depth of crown-relief countersink in the cutter
    aspect_ratio        : width / long-axis override (None = cut default)

    Returns
    -------
    dict with keys:
        cut               : str
        diameter_mm       : float  (resolved from carat if given)
        carat             : float
        material          : str or None
        gemstone          : dict   — GemProportions-equivalent dict
        cutter            : dict   — boolean cutter envelope
        warnings          : list[str]
    """
    if cut not in GEM_STUDIO_CUTS:
        raise ValueError(
            f"Unknown gem-studio cut {cut!r}. Valid: {sorted(GEM_STUDIO_CUTS)}"
        )

    # Resolve diameter from carat when needed
    if carat is not None and diameter_mm not in (None, 0.0) and diameter_mm > 0:
        raise ValueError("Provide diameter_mm OR carat, not both")
    if carat is not None:
        if carat <= 0:
            raise ValueError("carat must be positive")
        # cabochon uses diamond ref as baseline (treated like round brilliant)
        _cut_for_ref = "round_brilliant" if cut == "cabochon" else cut
        if _cut_for_ref not in _CARAT_REF:
            _cut_for_ref = "round_brilliant"
        diameter_mm = mm_from_carat(_cut_for_ref, carat, material=material,
                                     density_g_cm3=density_g_cm3)
    else:
        if diameter_mm is None or diameter_mm <= 0:
            raise ValueError("diameter_mm must be positive (or supply carat)")

    # Compute carat from diameter if not given
    if carat is None:
        _cut_for_ref = "round_brilliant" if cut == "cabochon" else cut
        if _cut_for_ref not in _CARAT_REF:
            _cut_for_ref = "round_brilliant"
        carat = carat_from_mm(_cut_for_ref, diameter_mm, material=material,
                               density_g_cm3=density_g_cm3)

    # Gemstone proportions
    if cut == "cabochon":
        defaults = dict(_CABOCHON_DEFAULTS)
        ar = aspect_ratio if aspect_ratio is not None else defaults["aspect_ratio"]
        crown_h_mm = diameter_mm * defaults["crown_height_pct"] / 100.0
        pav_d_mm = diameter_mm * defaults["pavilion_depth_pct"] / 100.0
        gird_mm = diameter_mm * defaults["girdle_pct"] / 100.0
        gemstone = {
            "cut":                "cabochon",
            "diameter_mm":        round(diameter_mm, 4),
            "aspect_ratio":       round(ar, 4),
            "table_pct":          0.0,
            "crown_angle_deg":    defaults["crown_angle_deg"],
            "crown_height_pct":   defaults["crown_height_pct"],
            "pavilion_angle_deg": 0.0,
            "pavilion_depth_pct": defaults["pavilion_depth_pct"],
            "girdle_pct":         defaults["girdle_pct"],
            "total_depth_pct":    round(defaults["crown_height_pct"] +
                                        defaults["girdle_pct"] +
                                        defaults["pavilion_depth_pct"], 2),
            "extras":             dict(defaults["extras"]),
        }
    else:
        props = gemstone_proportions(
            cut, diameter_mm=diameter_mm,
            aspect_ratio=aspect_ratio,
            material=material,
            density_g_cm3=density_g_cm3,
        )
        ar = props.aspect_ratio
        crown_h_mm = diameter_mm * props.crown_height_pct / 100.0
        pav_d_mm = diameter_mm * props.pavilion_depth_pct / 100.0
        gird_mm = diameter_mm * props.girdle_pct / 100.0
        gemstone = {
            "cut":                props.cut,
            "diameter_mm":        round(props.diameter_mm, 4),
            "aspect_ratio":       round(props.aspect_ratio, 4),
            "table_pct":          round(props.table_pct, 2),
            "crown_angle_deg":    round(props.crown_angle_deg, 2),
            "crown_height_pct":   round(props.crown_height_pct, 2),
            "pavilion_angle_deg": round(props.pavilion_angle_deg, 2),
            "pavilion_depth_pct": round(props.pavilion_depth_pct, 2),
            "girdle_pct":         round(props.girdle_pct, 2),
            "total_depth_pct":    round(props.total_depth_pct, 2),
            "extras":             dict(props.extras),
        }

    # Cutter envelope
    # The cutter is an oversized solid that, when subtracted from the host,
    # creates the bearing seat.  Key dimensions:
    #   - girdle_radius_mm : radius at the girdle plane = stone_radius + clearance
    #   - cutter_depth_mm  : total axial depth of the cutter
    #   - table_offset_mm  : gap at top so cutter opening is slightly above stone
    #   - short_axis_mm    : cutter short-axis for non-round cuts

    stone_long_r = diameter_mm / 2.0
    stone_short_r = diameter_mm * ar / 2.0
    cutter_long_r = stone_long_r + girdle_clearance_mm
    cutter_short_r = stone_short_r + girdle_clearance_mm

    # Axial breakdown (from table down):
    #   table_offset → crown_relief → girdle_ledge → pavilion → culet_allowance
    total_stone_depth_mm = (crown_h_mm + gird_mm + pav_d_mm)
    cutter_depth_mm = (
        table_offset_mm
        + crown_relief_mm
        + (gird_mm + seat_allowance_mm)
        + pav_d_mm
        + culet_allowance_mm
    )

    warnings: list[str] = []

    # Warn if cutter diameter is extremely small (melee sizes < 1 mm)
    if diameter_mm < 1.0:
        warnings.append(
            f"Melee stone diameter {diameter_mm:.3f} mm is very small; "
            "verify cutter tolerances with your casting house."
        )

    cutter = {
        "girdle_long_radius_mm":  round(cutter_long_r, 4),
        "girdle_short_radius_mm": round(cutter_short_r, 4),
        "aspect_ratio":           round(ar, 4),
        "cutter_depth_mm":        round(cutter_depth_mm, 4),
        "table_offset_mm":        round(table_offset_mm, 4),
        "crown_relief_mm":        round(crown_relief_mm, 4),
        "girdle_ledge_mm":        round(gird_mm + seat_allowance_mm, 4),
        "pavilion_depth_mm":      round(pav_d_mm, 4),
        "culet_allowance_mm":     round(culet_allowance_mm, 4),
        "girdle_clearance_mm":    round(girdle_clearance_mm, 4),
        "seat_allowance_mm":      round(seat_allowance_mm, 4),
        # Bounds envelope for the OCCT worker to build the cutter solid
        "bounding_long_axis_mm":  round(cutter_long_r * 2.0, 4),
        "bounding_short_axis_mm": round(cutter_short_r * 2.0, 4),
        "total_stone_depth_mm":   round(total_stone_depth_mm, 4),
    }

    return {
        "cut":        cut,
        "diameter_mm": round(diameter_mm, 4),
        "carat":      round(carat, 4),
        "material":   material,
        "gemstone":   gemstone,
        "cutter":     cutter,
        "warnings":   warnings,
    }


# ---------------------------------------------------------------------------
# Fit check
# ---------------------------------------------------------------------------

# Minimum metal wall thicknesses (mm) recommended per setting type
_MIN_WALL_DEFAULTS = {
    "prong":   0.6,   # minimum prong width at girdle
    "bezel":   0.5,   # bezel wall at thinnest
    "channel": 0.4,   # channel rail
    "pave":    0.35,  # pave dividers
    "flush":   0.45,  # gypsy/flush
    "tension": 0.8,   # tension setting wall
    "bar":     0.5,   # bar/straight channel
    "default": 0.5,
}


def gem_fit_check(
    cutter: dict,
    *,
    wall_thickness_mm: float,
    setting_type: str = "default",
    min_wall_override_mm: Optional[float] = None,
) -> dict:
    """Check if a cutter fits safely within available metal wall thickness.

    Parameters
    ----------
    cutter            : cutter dict as returned by gem_cutter_spec()["cutter"]
    wall_thickness_mm : available metal wall thickness in mm
    setting_type      : one of prong, bezel, channel, pave, flush, tension, bar
    min_wall_override_mm : override minimum wall (None = use setting_type default)

    Returns
    -------
    dict with keys:
        ok              : bool
        available_mm    : float
        required_mm     : float  (2 × girdle_long_radius + min_wall_both_sides)
        clearance_mm    : float  (available minus required; negative = violation)
        warnings        : list[str]
        setting_type    : str
    """
    min_wall = (
        min_wall_override_mm
        if min_wall_override_mm is not None
        else _MIN_WALL_DEFAULTS.get(setting_type.lower(), _MIN_WALL_DEFAULTS["default"])
    )

    cutter_diameter = cutter.get("bounding_long_axis_mm", 0.0)
    # Required: the cutter diameter plus two walls (one each side)
    required = cutter_diameter + 2.0 * min_wall
    clearance = wall_thickness_mm - required

    warnings: list[str] = []
    ok = clearance >= 0.0

    if not ok:
        warnings.append(
            f"WALL TOO THIN: cutter needs {required:.3f} mm "
            f"(cutter {cutter_diameter:.3f} mm + {2*min_wall:.3f} mm walls); "
            f"only {wall_thickness_mm:.3f} mm available — deficit {-clearance:.3f} mm."
        )
    elif clearance < min_wall * 0.5:
        warnings.append(
            f"Tight clearance: only {clearance:.3f} mm beyond minimum wall; "
            "consider thinning the cutter or increasing metal width."
        )

    culet_allow = cutter.get("culet_allowance_mm", 0.0)
    if culet_allow < 0.05:
        warnings.append(
            "Culet allowance is very small (< 0.05 mm); "
            "stone may bottom out during setting."
        )

    return {
        "ok":            ok,
        "available_mm":  round(wall_thickness_mm, 4),
        "required_mm":   round(required, 4),
        "clearance_mm":  round(clearance, 4),
        "min_wall_mm":   round(min_wall, 4),
        "warnings":      warnings,
        "setting_type":  setting_type,
    }


# ---------------------------------------------------------------------------
# Melee / auto-size sequencing
# ---------------------------------------------------------------------------

def melee_sequence(
    cut: str,
    channel_length_mm: float,
    *,
    target_carat: Optional[float] = None,
    target_diameter_mm: Optional[float] = None,
    girdle_clearance_mm: float = 0.05,
    seat_gap_mm: float = 0.10,
    material: Optional[str] = None,
    density_g_cm3: Optional[float] = None,
) -> dict:
    """Auto-size a row of melee stones to fill a channel.

    The sequence optimises stone count so all stones fit within
    ``channel_length_mm`` with ``seat_gap_mm`` between each cutter envelope.

    Parameters
    ----------
    cut               : cut name
    channel_length_mm : total available channel length in mm
    target_carat      : preferred stone weight in carats (stone size preference)
    target_diameter_mm: preferred diameter; exclusive with target_carat
    girdle_clearance_mm : clearance passed to gem_cutter_spec
    seat_gap_mm       : axial gap between adjacent cutter envelopes
    material / density_g_cm3 : gem material for carat↔mm conversion

    Returns
    -------
    dict with keys:
        stone_cut        : str
        stone_diameter_mm: float (actual stone size used)
        stone_carat      : float
        n_stones         : int
        pitch_mm         : float (centre-to-centre)
        total_set_length_mm : float
        positions_mm     : list[float] (x-offsets from channel start, centred)
        cutter_spec      : dict  (single-stone cutter spec, common to all)
        warnings         : list[str]
    """
    if cut not in GEM_STUDIO_CUTS:
        raise ValueError(f"Unknown cut {cut!r}. Valid: {sorted(GEM_STUDIO_CUTS)}")
    if channel_length_mm <= 0:
        raise ValueError("channel_length_mm must be positive")
    if target_carat is not None and target_diameter_mm is not None:
        raise ValueError("Provide target_carat OR target_diameter_mm, not both")

    # Resolve diameter
    if target_carat is not None:
        if target_carat <= 0:
            raise ValueError("target_carat must be positive")
        _ref_cut = "round_brilliant" if cut == "cabochon" else cut
        if _ref_cut not in _CARAT_REF:
            _ref_cut = "round_brilliant"
        stone_d = mm_from_carat(_ref_cut, target_carat,
                                material=material, density_g_cm3=density_g_cm3)
    elif target_diameter_mm is not None:
        if target_diameter_mm <= 0:
            raise ValueError("target_diameter_mm must be positive")
        stone_d = target_diameter_mm
    else:
        # Default to 0.10 ct (1.3 mm diameter) melee
        _ref_cut = "round_brilliant" if cut == "cabochon" else cut
        if _ref_cut not in _CARAT_REF:
            _ref_cut = "round_brilliant"
        stone_d = mm_from_carat(_ref_cut, 0.10,
                                material=material, density_g_cm3=density_g_cm3)

    single = gem_cutter_spec(
        cut, stone_d,
        girdle_clearance_mm=girdle_clearance_mm,
        material=material,
        density_g_cm3=density_g_cm3,
    )
    cutter_w = single["cutter"]["bounding_long_axis_mm"]
    pitch = cutter_w + seat_gap_mm

    if pitch <= 0 or pitch > channel_length_mm:
        n_stones = 0
    else:
        n_stones = max(1, int(channel_length_mm / pitch))

    total_set = n_stones * cutter_w + max(0, n_stones - 1) * seat_gap_mm
    # Centre the array within the channel
    start_offset = (channel_length_mm - total_set) / 2.0
    positions = [round(start_offset + i * pitch + cutter_w / 2.0, 4)
                 for i in range(n_stones)]

    warnings: list[str] = single.get("warnings", [])
    if total_set > channel_length_mm:
        warnings.append(
            f"Total set length {total_set:.3f} mm exceeds channel "
            f"{channel_length_mm:.3f} mm — reduce stone size or gap."
        )

    return {
        "stone_cut":         cut,
        "stone_diameter_mm": round(stone_d, 4),
        "stone_carat":       round(single["carat"], 4),
        "n_stones":          n_stones,
        "pitch_mm":          round(pitch, 4),
        "total_set_length_mm": round(total_set, 4),
        "positions_mm":      positions,
        "cutter_spec":       single,
        "warnings":          warnings,
    }


# ---------------------------------------------------------------------------
# LLM tool: jewelry_gem_studio_cutter
# ---------------------------------------------------------------------------

_jewelry_gem_studio_cutter_spec = ToolSpec(
    name="jewelry_gem_studio_cutter",
    description=(
        "Generate a parametric gemstone solid spec AND a matching boolean cutter "
        "envelope for any gem cut (MatrixGold-style gem studio).  The cutter solid "
        "is sized with configurable girdle clearance, culet allowance, and table "
        "offset — ready to boolean-subtract from a ring shank or setting host.\n"
        "\n"
        "Supported cuts: round_brilliant, princess, emerald, asscher, oval, "
        "marquise, pear, cushion, radiant, baguette, trillion, heart, briolette, "
        "rose_cut, cabochon.\n"
        "\n"
        "Size the stone by carat (recommended) or by primary dimension (diameter_mm "
        "for round/cabochon; long axis for all other cuts).  Supply material for "
        "accurate carat↔mm conversion on coloured stones (default: diamond density).\n"
        "\n"
        "Returns: gemstone proportions dict + cutter envelope dict + any clearance "
        "warnings.  Pass the cutter dict to jewelry_gem_studio_fit_check to validate "
        "wall thickness before sending to the OCCT worker."
    ),
    input_schema={
        "type": "object",
        "required": ["cut"],
        "properties": {
            "cut": {
                "type": "string",
                "description": (
                    "Gemstone cut. One of: round_brilliant, princess, emerald, "
                    "asscher, oval, marquise, pear, cushion, radiant, baguette, "
                    "trillion, heart, briolette, rose_cut, cabochon."
                ),
            },
            "diameter_mm": {
                "type": "number",
                "description": (
                    "Primary dimension in mm. Girdle diameter for round/cabochon; "
                    "long axis for other cuts. Exclusive with carat."
                ),
            },
            "carat": {
                "type": "number",
                "description": (
                    "Stone weight in carats.  Converted to mm using the cut's "
                    "carat-to-mm reference (calibrated for diamond; adjusted via "
                    "material/density when provided). Exclusive with diameter_mm."
                ),
            },
            "material": {
                "type": "string",
                "description": (
                    "Gem material name for density lookup, e.g. 'ruby', 'sapphire', "
                    "'emerald', 'amethyst'.  Affects carat↔mm conversion. "
                    "Default is 'diamond' density."
                ),
            },
            "density_g_cm3": {
                "type": "number",
                "description": "Explicit material density override in g/cm³.",
            },
            "girdle_clearance_mm": {
                "type": "number",
                "description": "Radial clearance around the girdle in the cutter. Default 0.05.",
            },
            "culet_allowance_mm": {
                "type": "number",
                "description": "Extra depth below culet for tool access. Default 0.10.",
            },
            "table_offset_mm": {
                "type": "number",
                "description": "Axial gap between stone table and cutter top. Default 0.05.",
            },
            "seat_allowance_mm": {
                "type": "number",
                "description": "Extra axial height on girdle ledge. Default 0.02.",
            },
            "crown_relief_mm": {
                "type": "number",
                "description": "Depth of crown-relief countersink in cutter. Default 0.30.",
            },
            "aspect_ratio": {
                "type": "number",
                "description": "Width / long-axis override. None = cut default.",
            },
        },
    },
)


@register(_jewelry_gem_studio_cutter_spec, write=False)
async def run_jewelry_gem_studio_cutter(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    cut = a.get("cut")
    if not cut:
        return err_payload("cut is required", "BAD_ARGS")
    cut = str(cut).strip().lower()
    if cut not in GEM_STUDIO_CUTS:
        return err_payload(
            f"Unknown cut {cut!r}. Valid: {sorted(GEM_STUDIO_CUTS)}", "BAD_ARGS"
        )

    diameter_mm = a.get("diameter_mm")
    carat = a.get("carat")
    if diameter_mm is None and carat is None:
        return err_payload("Provide diameter_mm or carat", "BAD_ARGS")
    if diameter_mm is not None and carat is not None:
        return err_payload("Provide diameter_mm OR carat, not both", "BAD_ARGS")

    try:
        if diameter_mm is not None:
            diameter_mm = float(diameter_mm)
            if diameter_mm <= 0:
                return err_payload("diameter_mm must be positive", "BAD_ARGS")
        if carat is not None:
            carat = float(carat)
            if carat <= 0:
                return err_payload("carat must be positive", "BAD_ARGS")
    except (TypeError, ValueError) as exc:
        return err_payload(f"numeric conversion error: {exc}", "BAD_ARGS")

    material = a.get("material")
    density_g_cm3 = a.get("density_g_cm3")
    if density_g_cm3 is not None:
        try:
            density_g_cm3 = float(density_g_cm3)
        except (TypeError, ValueError):
            return err_payload("density_g_cm3 must be a number", "BAD_ARGS")
        if density_g_cm3 <= 0:
            return err_payload("density_g_cm3 must be positive", "BAD_ARGS")

    # Optional clearance overrides
    def _opt_float(key: str, default: float, *, positive: bool = True) -> tuple[float, str]:
        v = a.get(key, default)
        try:
            v = float(v)
        except (TypeError, ValueError):
            return default, f"{key} must be a number"
        if positive and v < 0:
            return default, f"{key} must be >= 0"
        return v, ""

    girdle_clearance_mm, e = _opt_float("girdle_clearance_mm", 0.05)
    if e:
        return err_payload(e, "BAD_ARGS")
    culet_allowance_mm, e = _opt_float("culet_allowance_mm", 0.10)
    if e:
        return err_payload(e, "BAD_ARGS")
    table_offset_mm, e = _opt_float("table_offset_mm", 0.05)
    if e:
        return err_payload(e, "BAD_ARGS")
    seat_allowance_mm, e = _opt_float("seat_allowance_mm", 0.02)
    if e:
        return err_payload(e, "BAD_ARGS")
    crown_relief_mm, e = _opt_float("crown_relief_mm", 0.30)
    if e:
        return err_payload(e, "BAD_ARGS")

    aspect_ratio = a.get("aspect_ratio")
    if aspect_ratio is not None:
        try:
            aspect_ratio = float(aspect_ratio)
        except (TypeError, ValueError):
            return err_payload("aspect_ratio must be a number", "BAD_ARGS")
        if not (0.05 <= aspect_ratio <= 2.0):
            return err_payload("aspect_ratio must be between 0.05 and 2.0", "BAD_ARGS")

    try:
        result = gem_cutter_spec(
            cut,
            diameter_mm or 0.0,
            carat=carat,
            material=material,
            density_g_cm3=density_g_cm3,
            girdle_clearance_mm=girdle_clearance_mm,
            culet_allowance_mm=culet_allowance_mm,
            table_offset_mm=table_offset_mm,
            seat_allowance_mm=seat_allowance_mm,
            crown_relief_mm=crown_relief_mm,
            aspect_ratio=aspect_ratio,
        )
    except ValueError as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(f"cutter computation error: {exc}", "ERROR")

    return ok_payload(result)


# ---------------------------------------------------------------------------
# LLM tool: jewelry_gem_studio_catalog
# ---------------------------------------------------------------------------

_jewelry_gem_studio_catalog_spec = ToolSpec(
    name="jewelry_gem_studio_catalog",
    description=(
        "Look up optical properties, colour grades, hardness (Mohs), dispersion, "
        "refractive index, density, and price-per-carat orientation for gem materials.\n"
        "\n"
        "Query by material name (e.g. 'ruby') or by cut name to get the list of "
        "gem materials commonly used with that cut.  Returns one or more catalog "
        "entries from the gem studio material library.\n"
        "\n"
        "Price data is orientation-only (GemVal / trade 2023–2024); always verify "
        "with current market prices before quoting."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "material": {
                "type": "string",
                "description": "Gem material name, e.g. 'ruby', 'diamond', 'tanzanite'.",
            },
            "cut": {
                "type": "string",
                "description": (
                    "Return materials commonly used in this cut "
                    "(e.g. 'round_brilliant' returns all materials that list it)."
                ),
            },
        },
    },
)


@register(_jewelry_gem_studio_catalog_spec, write=False)
async def run_jewelry_gem_studio_catalog(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    material = a.get("material")
    cut = a.get("cut")

    if material is None and cut is None:
        # Return full catalog summary
        summary = {
            name: {
                k: v for k, v in entry.items()
                if k in ("density", "mohs", "dispersion", "ri",
                         "price_per_ct_band", "typical_cuts", "colour_grades")
            }
            for name, entry in GEM_STUDIO_CATALOG.items()
        }
        return ok_payload({"catalog": summary, "count": len(summary)})

    results = {}

    if material is not None:
        key = str(material).strip().lower().replace(" ", "_")
        if key in GEM_STUDIO_CATALOG:
            results[key] = GEM_STUDIO_CATALOG[key]
        else:
            # Fuzzy substring match
            for k, v in GEM_STUDIO_CATALOG.items():
                if key in k:
                    results[k] = v
        if not results:
            return err_payload(
                f"Material {material!r} not found in gem studio catalog. "
                f"Available: {sorted(GEM_STUDIO_CATALOG)}", "NOT_FOUND"
            )

    if cut is not None:
        cut_key = str(cut).strip().lower()
        for k, v in GEM_STUDIO_CATALOG.items():
            if cut_key in v.get("typical_cuts", []):
                if k not in results:
                    results[k] = v

    if not results:
        return err_payload(
            f"No catalog entries found for material={material!r}, cut={cut!r}",
            "NOT_FOUND"
        )

    return ok_payload({"results": results, "count": len(results)})


# ---------------------------------------------------------------------------
# LLM tool: jewelry_gem_studio_fit_check
# ---------------------------------------------------------------------------

_jewelry_gem_studio_fit_check_spec = ToolSpec(
    name="jewelry_gem_studio_fit_check",
    description=(
        "Validate that a gem cutter envelope fits within available metal wall "
        "thickness for a given setting type.  Reports minimum clearance, whether "
        "the fit is within tolerance, and any warnings.\n"
        "\n"
        "Pass the cutter dict from jewelry_gem_studio_cutter as the cutter argument "
        "together with the metal wall thickness from your ring/setting geometry.\n"
        "\n"
        "Setting types: prong, bezel, channel, pave, flush, tension, bar."
    ),
    input_schema={
        "type": "object",
        "required": ["cutter", "wall_thickness_mm"],
        "properties": {
            "cutter": {
                "type": "object",
                "description": (
                    "Cutter dict returned by jewelry_gem_studio_cutter "
                    "(the 'cutter' sub-dict, not the full result)."
                ),
            },
            "wall_thickness_mm": {
                "type": "number",
                "description": "Available metal wall thickness in mm.",
            },
            "setting_type": {
                "type": "string",
                "description": "Setting style: prong, bezel, channel, pave, flush, tension, bar.",
            },
            "min_wall_override_mm": {
                "type": "number",
                "description": "Override minimum wall thickness (mm). Overrides setting_type default.",
            },
        },
    },
)


@register(_jewelry_gem_studio_fit_check_spec, write=False)
async def run_jewelry_gem_studio_fit_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    cutter = a.get("cutter")
    if not isinstance(cutter, dict):
        return err_payload("cutter must be the cutter dict from jewelry_gem_studio_cutter", "BAD_ARGS")

    wall_thickness_mm = a.get("wall_thickness_mm")
    if wall_thickness_mm is None:
        return err_payload("wall_thickness_mm is required", "BAD_ARGS")
    try:
        wall_thickness_mm = float(wall_thickness_mm)
    except (TypeError, ValueError):
        return err_payload("wall_thickness_mm must be a number", "BAD_ARGS")
    if wall_thickness_mm <= 0:
        return err_payload("wall_thickness_mm must be positive", "BAD_ARGS")

    setting_type = str(a.get("setting_type", "default")).lower()
    min_wall_override = a.get("min_wall_override_mm")
    if min_wall_override is not None:
        try:
            min_wall_override = float(min_wall_override)
        except (TypeError, ValueError):
            return err_payload("min_wall_override_mm must be a number", "BAD_ARGS")
        if min_wall_override <= 0:
            return err_payload("min_wall_override_mm must be positive", "BAD_ARGS")

    try:
        result = gem_fit_check(
            cutter,
            wall_thickness_mm=wall_thickness_mm,
            setting_type=setting_type,
            min_wall_override_mm=min_wall_override,
        )
    except Exception as exc:
        return err_payload(f"fit check error: {exc}", "ERROR")

    return ok_payload(result)


# ---------------------------------------------------------------------------
# LLM tool: jewelry_gem_studio_melee_seq
# ---------------------------------------------------------------------------

_jewelry_gem_studio_melee_seq_spec = ToolSpec(
    name="jewelry_gem_studio_melee_seq",
    description=(
        "Auto-size and sequence a row of melee / accent stones to fill a "
        "channel of given length.  Returns stone count, pitch, centre positions, "
        "and per-stone cutter specs.\n"
        "\n"
        "Specify stone size via target_carat or target_diameter_mm.  If neither "
        "is given, defaults to 0.10 ct melee.  The sequencer packs the channel "
        "with uniform-size stones and centres the row.\n"
        "\n"
        "Supported cuts: round_brilliant, princess, emerald, asscher, oval, "
        "marquise, pear, cushion, radiant, baguette, trillion, heart, briolette, "
        "rose_cut, cabochon."
    ),
    input_schema={
        "type": "object",
        "required": ["cut", "channel_length_mm"],
        "properties": {
            "cut": {
                "type": "string",
                "description": "Gemstone cut for the melee stones.",
            },
            "channel_length_mm": {
                "type": "number",
                "description": "Total available channel length in mm.",
            },
            "target_carat": {
                "type": "number",
                "description": "Preferred stone weight in carats. Exclusive with target_diameter_mm.",
            },
            "target_diameter_mm": {
                "type": "number",
                "description": "Preferred stone diameter in mm. Exclusive with target_carat.",
            },
            "girdle_clearance_mm": {
                "type": "number",
                "description": "Radial clearance around girdle in cutter. Default 0.05.",
            },
            "seat_gap_mm": {
                "type": "number",
                "description": "Gap between adjacent cutter envelopes in mm. Default 0.10.",
            },
            "material": {
                "type": "string",
                "description": "Gem material name for carat↔mm conversion.",
            },
            "density_g_cm3": {
                "type": "number",
                "description": "Explicit material density in g/cm³.",
            },
        },
    },
)


@register(_jewelry_gem_studio_melee_seq_spec, write=False)
async def run_jewelry_gem_studio_melee_seq(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    cut = a.get("cut")
    if not cut:
        return err_payload("cut is required", "BAD_ARGS")
    cut = str(cut).strip().lower()
    if cut not in GEM_STUDIO_CUTS:
        return err_payload(
            f"Unknown cut {cut!r}. Valid: {sorted(GEM_STUDIO_CUTS)}", "BAD_ARGS"
        )

    channel_length_mm = a.get("channel_length_mm")
    if channel_length_mm is None:
        return err_payload("channel_length_mm is required", "BAD_ARGS")
    try:
        channel_length_mm = float(channel_length_mm)
    except (TypeError, ValueError):
        return err_payload("channel_length_mm must be a number", "BAD_ARGS")
    if channel_length_mm <= 0:
        return err_payload("channel_length_mm must be positive", "BAD_ARGS")

    target_carat = a.get("target_carat")
    target_diameter_mm = a.get("target_diameter_mm")
    if target_carat is not None and target_diameter_mm is not None:
        return err_payload("Provide target_carat OR target_diameter_mm, not both", "BAD_ARGS")
    if target_carat is not None:
        try:
            target_carat = float(target_carat)
        except (TypeError, ValueError):
            return err_payload("target_carat must be a number", "BAD_ARGS")
        if target_carat <= 0:
            return err_payload("target_carat must be positive", "BAD_ARGS")
    if target_diameter_mm is not None:
        try:
            target_diameter_mm = float(target_diameter_mm)
        except (TypeError, ValueError):
            return err_payload("target_diameter_mm must be a number", "BAD_ARGS")
        if target_diameter_mm <= 0:
            return err_payload("target_diameter_mm must be positive", "BAD_ARGS")

    girdle_clearance_mm = float(a.get("girdle_clearance_mm", 0.05))
    seat_gap_mm = float(a.get("seat_gap_mm", 0.10))
    material = a.get("material")
    density_g_cm3 = a.get("density_g_cm3")
    if density_g_cm3 is not None:
        try:
            density_g_cm3 = float(density_g_cm3)
        except (TypeError, ValueError):
            return err_payload("density_g_cm3 must be a number", "BAD_ARGS")

    try:
        result = melee_sequence(
            cut,
            channel_length_mm,
            target_carat=target_carat,
            target_diameter_mm=target_diameter_mm,
            girdle_clearance_mm=girdle_clearance_mm,
            seat_gap_mm=seat_gap_mm,
            material=material,
            density_g_cm3=density_g_cm3,
        )
    except ValueError as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(f"melee sequence error: {exc}", "ERROR")

    return ok_payload(result)
