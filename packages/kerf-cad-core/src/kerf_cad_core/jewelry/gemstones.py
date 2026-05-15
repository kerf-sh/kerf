"""
Parametric gemstone solid generator.

Supported cuts
--------------
round_brilliant  57/58 facets — the GIA standard.
princess         Square modified brilliant (4-fold symmetry).
oval             Elliptical modified brilliant.
emerald          Rectangular step cut.
marquise         Boat-shaped modified brilliant.
pear             Teardrop modified brilliant.
cushion          Square/rectangular cushion modified brilliant.
radiant          Cropped-corner rectangular modified brilliant.
asscher          Square step cut with cropped corners (high crown).
trillion         Triangular modified brilliant (Trillion™ / triangular brilliant).
heart            Heart-shaped modified brilliant.
baguette         Rectangular step cut (long narrow bar).
briolette        Elongated teardrop with all-facet surface; no table.

Each cut is described by a *proportions dict* whose keys follow GIA/AGS
conventions (all linear dimensions as mm, angles in degrees).

Carat ↔ mm formulae
--------------------
These are empirical weight approximations used industry-wide.

Round brilliant (1 ct ≈ 6.5 mm diameter, diamond density 3.51 g/cm³):
    carat = (diameter_mm / 6.5) ** 3

    Derivation: density of diamond ≈ 3.51 g/cm³; a brilliant approximates a
    flattened cylinder.  The cube exponent captures the volume scaling.
    Inversion: diameter_mm = 6.5 * carat**(1/3)

Other cuts use an equivalent-diameter conversion via their aspect ratio
relative to round brilliant.  E.g. a 1 ct princess ≈ 5.5 mm side length.

Coloured-stone density correction
----------------------------------
The ref_mm constants above are calibrated for diamond (3.51 g/cm³).  For a
different material, the reference dimension scales as:

    ref_mm_material = ref_mm_diamond * (rho_diamond / rho_material) ** (1/3)

so that volume × density = the same 0.2 g per carat.

Pass `density_g_cm3` (or `material`) to carat_from_mm / mm_from_carat to get
accurate carat weights for coloured stones.  Default material is "diamond" for
full backward compatibility.

Density sources: GIA Gemology Reference (https://www.gia.edu/gems-gemology),
Richard T. Liddicoat Jr., "GIA Gem Reference Guide" (GIA 1995), and
*Gemological Institute of America Gem Encyclopedia* (2014 ed.).

Industry reference proportions
-------------------------------
Round brilliant (ideal / "Tolkowsky"):
    table_pct        : 53–58 %   (table width / girdle diameter)
    crown_angle_deg  : 34.5°
    pavilion_angle_deg: 40.75°
    girdle_pct       : 2.5 % (thin-medium girdle thickness / diameter)
    total_depth_pct  : 61–62 %

Princess:
    table_pct: 75 %, crown_angle_deg: 30°, pavilion_angle_deg: 42°,
    pavilion_depth_pct: 43 %, total_depth_pct: 68 %

Emerald:
    table_pct: 60 %, crown_angle_deg: 15°, step_rows: 3,
    total_depth_pct: 60 %, corner_cut_ratio: 0.15

Radiant:
    table_pct: 62 %, crown_angle_deg: 32°, pavilion_angle_deg: 41°,
    aspect_ratio: 0.75, corner_cut_ratio: 0.10

Asscher:
    table_pct: 60 %, crown_angle_deg: 25°, step_rows: 3,
    aspect_ratio: 1.0, corner_cut_ratio: 0.20 (deeper corner cuts than emerald)

Trillion:
    table_pct: 55 %, crown_angle_deg: 34°, pavilion_angle_deg: 41°,
    sides: 3, aspect_ratio: 1.0 (equilateral)

Heart:
    table_pct: 56 %, crown_angle_deg: 34.5°, pavilion_angle_deg: 40.75°,
    aspect_ratio: 0.98 (length ≈ width), cleft_depth_pct: 10

Baguette:
    table_pct: 70 %, crown_angle_deg: 8°, step_rows: 2,
    aspect_ratio: 0.40 (3:1 to 4:1 L:W typical)

Briolette:
    No table; full-facet elongated teardrop; crown_angle_deg = 30° (upper facets),
    pavilion_angle_deg = 45° (lower point), aspect_ratio: 0.50 (height ≈ 2× width)

LLM-facing tools
----------------
  jewelry_create_gemstone  — appends a gemstone node to a .feature file
"""

from __future__ import annotations

import json
import uuid
from typing import Optional, NamedTuple

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx
from kerf_cad_core.surfacing import (
    read_feature_content,
    append_feature_node,
    next_node_id,
)


# ---------------------------------------------------------------------------
# Cut registry
# ---------------------------------------------------------------------------

GEMSTONE_CUTS = {
    "round_brilliant",
    "princess",
    "oval",
    "emerald",
    "marquise",
    "pear",
    "cushion",
    # Fancy cuts added in second slice:
    "radiant",
    "asscher",
    "trillion",
    "heart",
    "baguette",
    "briolette",
    # Historical / specialty cuts added in third slice:
    "old_european",      # Precursor to round brilliant; high crown, small table
    "old_mine",          # Victorian cushion brilliant; high crown, small culet
    "rose_cut",          # Flat base, dome top, triangular facets; no pavilion
    "single_cut",        # Simplified brilliant, 17 facets; melee size
    "french_cut",        # Square step cut with X-pattern table; art-deco
    "half_moon",         # Semi-circular fancy; modified brilliant half-oval
    "trapezoid",         # Trapezoidal step cut; tapered side stone
    "kite",              # Kite/arrowhead angular fancy; triangular derivative
    "bullet",            # Pointed-top rounded-base brilliant; tapered fancy
    "tapered_baguette",  # Baguette with angled ends; channel side stone
    "lozenge",           # Diamond/rhombus four-point step cut
    "shield",            # Irregular pentagon / shield-shaped brilliant
    "calf_head",         # Wide pear variant; low-set teardrop (bouche)
}


# ---------------------------------------------------------------------------
# Gemstone material density table
# ---------------------------------------------------------------------------

# Specific gravity (g/cm³) for common gem materials.
#
# Sources:
#   GIA Gem Reference Guide (Liddicoat, GIA 1995) — primary authority for SG
#   GIA Gemology Reference: https://www.gia.edu/gems-gemology
#   Gemological Institute of America Gem Encyclopedia, 2014 ed.
#   International Gem Society (IGS) gem property tables
#   Values are midpoint of published range where a range is given.
#
# One carat = 0.2 g exactly.  The carat-from-mm formula assumes a specific
# volume for a given cut shape.  For a material with density ρ (g/cm³) vs.
# diamond (3.51 g/cm³), the reference dimension at 1 ct scales as:
#
#     ref_mm_material = ref_mm_diamond × (3.51 / ρ) ^ (1/3)
#
# This keeps the volume × ρ = 0.2 g relationship intact.
GEMSTONE_DENSITIES: dict[str, float] = {
    # Natural stones
    "diamond":      3.51,  # GIA; range 3.50–3.53
    "ruby":         3.99,  # GIA; corundum range 3.97–4.05, midpoint ~4.00
    "sapphire":     4.00,  # GIA; corundum (same mineral as ruby)
    "emerald":      2.72,  # GIA; beryl range 2.67–2.78, typical 2.72
    "amethyst":     2.65,  # GIA; quartz
    "citrine":      2.65,  # GIA; quartz
    "aquamarine":   2.72,  # GIA; beryl
    "morganite":    2.71,  # GIA; beryl
    "topaz":        3.53,  # GIA; range 3.49–3.57
    "garnet":       3.78,  # GIA; pyrope–almandine midpoint (~3.6–4.0)
    "spinel":       3.60,  # GIA; range 3.54–3.63
    "tanzanite":    3.35,  # GIA; zoisite
    "peridot":      3.32,  # GIA; range 3.27–3.37
    "tourmaline":   3.10,  # GIA; range 2.82–3.32, typical ~3.10
    "opal":         2.08,  # GIA; range 1.98–2.20
    "moonstone":    2.56,  # GIA; orthoclase feldspar
    "alexandrite":  3.73,  # GIA; chrysoberyl
    "chrysoberyl":  3.73,  # GIA
    "zircon":       4.67,  # GIA; range 3.93–4.73 (high type ~4.67)
    "pearl":        2.71,  # GIA; nacre range 2.60–2.85
    "coral":        2.65,  # GIA; organic
    "amber":        1.08,  # GIA; organic
    "lapis_lazuli": 2.80,  # GIA; range 2.50–3.00, typical 2.80
    "turquoise":    2.75,  # GIA; range 2.60–2.90
    "jade_jadeite": 3.33,  # GIA; jadeite
    "jade_nephrite":2.95,  # GIA; nephrite
}

# Diamond SG used as the calibration baseline for ref_mm constants
_DIAMOND_DENSITY: float = GEMSTONE_DENSITIES["diamond"]


# ---------------------------------------------------------------------------
# Carat ↔ mm sizing
# ---------------------------------------------------------------------------

# Exponent k for: carat = (dim_mm / ref_mm) ** k
# ref_mm = diameter at 1 carat for DIAMOND; k = 3 for a cubic scaling approx.

_CARAT_REF: dict[str, tuple[float, float]] = {
    # (ref_diameter_mm_for_diamond, exponent)
    "round_brilliant": (6.5, 3.0),
    "princess":        (5.5, 3.0),   # side length
    "oval":            (7.7, 3.0),   # long axis
    "emerald":         (7.0, 3.0),   # long axis
    "marquise":        (10.0, 3.0),  # long axis
    "pear":            (8.0, 3.0),   # long axis
    "cushion":         (5.5, 3.0),   # side length
    # Fancy cuts (ref_mm derived from equivalent-volume comparison to round brilliant):
    "radiant":         (6.0, 3.0),   # similar footprint to princess; ~10% larger
    "asscher":         (5.5, 3.0),   # square step; similar depth to emerald
    "trillion":        (7.0, 3.0),   # equilateral triangle; large face, shallow
    "heart":           (6.5, 3.0),   # same ref as round brilliant (≈same volume)
    "baguette":        (5.0, 3.0),   # 3:1 narrow bar; shallow step cut
    "briolette":       (5.5, 3.0),   # elongated teardrop; half-round cross-section
    # Historical / specialty cuts (third slice):
    "old_european":    (6.5, 3.0),   # same footprint as round brilliant
    "old_mine":        (5.5, 3.0),   # cushion outline; ~same depth as princess
    "rose_cut":        (7.8, 3.0),   # flat base = more spread per carat; ~1.2× round
    "single_cut":      (4.1, 3.0),   # tiny melee; shallow ~17-facet brilliant
    "french_cut":      (5.0, 3.0),   # small square step; similar to small baguette
    "half_moon":       (8.5, 3.0),   # half-oval; wide face, shallow depth
    "trapezoid":       (6.5, 3.0),   # trapezoidal step; similar volume to baguette
    "kite":            (6.0, 3.0),   # kite/arrowhead; triangular derivative, moderate depth
    "bullet":          (5.5, 3.0),   # tapered pear; similar volume to small pear
    "tapered_baguette":(5.2, 3.0),   # baguette with angled ends; slightly deeper
    "lozenge":         (6.5, 3.0),   # rhombus step cut; similar to marquise volume
    "shield":          (6.8, 3.0),   # irregular pentagon; large face, moderate depth
    "calf_head":       (8.5, 3.0),   # wide low-set pear variant; large spread
}


def _effective_ref_mm(cut: str, density_g_cm3: float) -> float:
    """Return ref_mm adjusted for material density.

    The published ref_mm values assume diamond density (3.51 g/cm³).
    For a different material:
        ref_mm_material = ref_mm_diamond × (rho_diamond / rho_material) ^ (1/3)

    This ensures that ref_mm_material × density = 0.2 g (1 carat) for the
    same cut geometry.
    """
    ref_mm, _exp = _CARAT_REF[cut]
    if density_g_cm3 == _DIAMOND_DENSITY:
        return ref_mm
    return ref_mm * (_DIAMOND_DENSITY / density_g_cm3) ** (1.0 / 3.0)


def _resolve_density(material: Optional[str], density_g_cm3: Optional[float]) -> float:
    """Return density in g/cm³ from material name or explicit override.

    Precedence: explicit density_g_cm3 > GEMSTONE_DENSITIES lookup > diamond default.
    """
    if density_g_cm3 is not None:
        if density_g_cm3 <= 0:
            raise ValueError("density_g_cm3 must be positive")
        return density_g_cm3
    if material is not None:
        key = material.lower().replace(" ", "_")
        if key in GEMSTONE_DENSITIES:
            return GEMSTONE_DENSITIES[key]
        # Unknown material: fall back to diamond with no error (backward-compat)
    return _DIAMOND_DENSITY


def carat_from_mm(
    cut: str,
    dim_mm: float,
    *,
    material: Optional[str] = None,
    density_g_cm3: Optional[float] = None,
) -> float:
    """Return estimated carat weight from the primary dimension in mm.

    For round_brilliant, dim_mm is the girdle diameter.
    For all other cuts, dim_mm is the long-axis length.

    Formula: carat = (dim_mm / ref_mm_material) ** exponent
    where ref_mm_material is the ~1-carat dimension for that cut at the
    given material density (default: diamond, 3.51 g/cm³).

    Parameters
    ----------
    cut : str
        One of the GEMSTONE_CUTS keys.
    dim_mm : float
        Primary dimension in mm (>0).
    material : str, optional
        Material name (e.g. ``"ruby"``).  Looked up in GEMSTONE_DENSITIES.
        Ignored if ``density_g_cm3`` is also supplied.
    density_g_cm3 : float, optional
        Explicit material density in g/cm³.  Overrides ``material``.
    """
    if cut not in _CARAT_REF:
        raise ValueError(f"Unknown cut: {cut!r}")
    if dim_mm <= 0:
        raise ValueError("dim_mm must be positive")
    rho = _resolve_density(material, density_g_cm3)
    _ref_mm, exp = _CARAT_REF[cut]
    ref_mm = _effective_ref_mm(cut, rho)
    return (dim_mm / ref_mm) ** exp


def mm_from_carat(
    cut: str,
    carat: float,
    *,
    material: Optional[str] = None,
    density_g_cm3: Optional[float] = None,
) -> float:
    """Return the primary dimension in mm for a given carat weight.

    Inverse of carat_from_mm:
        dim_mm = ref_mm_material * carat ** (1 / exponent)

    Parameters
    ----------
    cut : str
        One of the GEMSTONE_CUTS keys.
    carat : float
        Stone weight in carats (>0).
    material : str, optional
        Material name (e.g. ``"ruby"``).  Looked up in GEMSTONE_DENSITIES.
    density_g_cm3 : float, optional
        Explicit density in g/cm³.  Overrides ``material``.
    """
    if cut not in _CARAT_REF:
        raise ValueError(f"Unknown cut: {cut!r}")
    if carat <= 0:
        raise ValueError("carat must be positive")
    rho = _resolve_density(material, density_g_cm3)
    _ref_mm, exp = _CARAT_REF[cut]
    ref_mm = _effective_ref_mm(cut, rho)
    return ref_mm * (carat ** (1.0 / exp))


# ---------------------------------------------------------------------------
# Industry-standard default proportions per cut
# ---------------------------------------------------------------------------

class GemProportions(NamedTuple):
    """All dimensions in mm (relative to the girdle diameter = 1 when normalised).
    Angles in degrees.
    """
    cut: str
    # Primary sizing
    diameter_mm: float          # girdle diameter (round) or long-axis (others)
    aspect_ratio: float         # width / long-axis  (1.0 for round/square)
    # Crown
    table_pct: float            # table width / girdle diameter, percent
    crown_angle_deg: float
    crown_height_pct: float     # crown height / diameter, percent
    # Pavilion
    pavilion_angle_deg: float
    pavilion_depth_pct: float   # pavilion depth / diameter, percent
    # Girdle
    girdle_pct: float           # girdle thickness / diameter, percent
    # Derived
    total_depth_pct: float      # crown + girdle + pavilion
    # Cut-specific extras
    extras: dict


def gemstone_proportions(
    cut: str,
    diameter_mm: Optional[float] = None,
    carat: Optional[float] = None,
    *,
    # Optional overrides (None = use industry default)
    table_pct: Optional[float] = None,
    crown_angle_deg: Optional[float] = None,
    pavilion_angle_deg: Optional[float] = None,
    girdle_pct: Optional[float] = None,
    aspect_ratio: Optional[float] = None,
    # Material density for correct carat↔mm conversion
    material: Optional[str] = None,
    density_g_cm3: Optional[float] = None,
) -> GemProportions:
    """Return a GemProportions for the given cut + sizing.

    Exactly one of diameter_mm or carat must be provided.

    Parameters
    ----------
    cut : str
        One of the GEMSTONE_CUTS keys.
    diameter_mm : float, optional
        Primary dimension in mm.  Exclusive with ``carat``.
    carat : float, optional
        Stone weight in carats.  Converted to mm via carat formula.
    material : str, optional
        Material name for density lookup (e.g. ``"ruby"``).  Used only when
        ``carat`` is given.  Ignored if ``density_g_cm3`` is also supplied.
    density_g_cm3 : float, optional
        Explicit material density in g/cm³.  Overrides ``material``.
    """
    if cut not in GEMSTONE_CUTS:
        raise ValueError(f"Unknown cut {cut!r}. Valid: {sorted(GEMSTONE_CUTS)}")

    # Resolve sizing
    if diameter_mm is not None and carat is not None:
        raise ValueError("Provide diameter_mm OR carat, not both")
    if diameter_mm is None and carat is None:
        raise ValueError("One of diameter_mm or carat is required")
    if carat is not None:
        if carat <= 0:
            raise ValueError("carat must be positive")
        diameter_mm = mm_from_carat(cut, carat, material=material, density_g_cm3=density_g_cm3)
    if diameter_mm <= 0:
        raise ValueError("diameter_mm must be positive")

    # Industry defaults per cut
    _defaults = _CUT_DEFAULTS[cut]

    ta_pct    = table_pct         if table_pct         is not None else _defaults["table_pct"]
    ca_deg    = crown_angle_deg   if crown_angle_deg    is not None else _defaults["crown_angle_deg"]
    pa_deg    = pavilion_angle_deg if pavilion_angle_deg is not None else _defaults["pavilion_angle_deg"]
    gi_pct    = girdle_pct        if girdle_pct         is not None else _defaults["girdle_pct"]
    ar        = aspect_ratio      if aspect_ratio        is not None else _defaults.get("aspect_ratio", 1.0)

    # Compute derived heights (fraction of diameter).
    # When a cut has explicit crown_height_pct / pavilion_depth_pct in its
    # defaults those values take precedence; otherwise derive from angles.
    # Note: briolette has table_pct=0 (no table) — handled naturally.
    import math
    stored_ch = _defaults.get("crown_height_pct")
    crown_h_pct = (
        stored_ch if stored_ch is not None and stored_ch != 0
        else (1 - ta_pct / 100.0) / 2 * math.tan(math.radians(ca_deg)) * 100
    )
    stored_pd = _defaults.get("pavilion_depth_pct")
    pav_d_pct = (
        stored_pd if stored_pd is not None and stored_pd != 0
        else 0.5 * math.tan(math.radians(pa_deg)) * 100
    )
    gi_mm_pct = gi_pct
    total = crown_h_pct + gi_mm_pct + pav_d_pct

    return GemProportions(
        cut=cut,
        diameter_mm=diameter_mm,
        aspect_ratio=ar,
        table_pct=ta_pct,
        crown_angle_deg=ca_deg,
        crown_height_pct=crown_h_pct,
        pavilion_angle_deg=pa_deg,
        pavilion_depth_pct=pav_d_pct,
        girdle_pct=gi_mm_pct,
        total_depth_pct=total,
        extras=dict(_defaults.get("extras", {})),
    )


# Industry-standard defaults
_CUT_DEFAULTS: dict[str, dict] = {
    "round_brilliant": {
        "table_pct": 57.0,
        "crown_angle_deg": 34.5,
        "crown_height_pct": 16.2,
        "pavilion_angle_deg": 40.75,
        "pavilion_depth_pct": 43.1,
        "girdle_pct": 2.5,
        "aspect_ratio": 1.0,
        "extras": {"facet_count": 57, "culet": "none"},
    },
    "princess": {
        "table_pct": 75.0,
        "crown_angle_deg": 30.0,
        "crown_height_pct": 10.5,
        "pavilion_angle_deg": 42.0,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 2.0,
        "aspect_ratio": 1.0,
        "extras": {"facet_count": 57},
    },
    "oval": {
        "table_pct": 56.0,
        "crown_angle_deg": 34.5,
        "crown_height_pct": 15.0,
        "pavilion_angle_deg": 40.75,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 2.5,
        "aspect_ratio": 0.66,       # width = 0.66 × length (typical 1.35:1 L:W)
        "extras": {"facet_count": 57},
    },
    "emerald": {
        "table_pct": 60.0,
        "crown_angle_deg": 15.0,
        "crown_height_pct": 8.0,
        "pavilion_angle_deg": 45.0,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 2.0,
        "aspect_ratio": 0.71,       # width = 0.71 × length (standard ~1.4:1)
        "extras": {"step_rows": 3, "corner_cut_ratio": 0.15},
    },
    "marquise": {
        "table_pct": 56.0,
        "crown_angle_deg": 33.5,
        "crown_height_pct": 14.0,
        "pavilion_angle_deg": 41.0,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 2.5,
        "aspect_ratio": 0.50,       # width = 0.50 × length (~2:1 L:W)
        "extras": {"facet_count": 57},
    },
    "pear": {
        "table_pct": 55.0,
        "crown_angle_deg": 35.0,
        "crown_height_pct": 15.0,
        "pavilion_angle_deg": 41.0,
        "pavilion_depth_pct": 43.5,
        "girdle_pct": 2.5,
        "aspect_ratio": 0.62,       # width = 0.62 × length
        "extras": {"facet_count": 57},
    },
    "cushion": {
        "table_pct": 60.0,
        "crown_angle_deg": 35.0,
        "crown_height_pct": 14.0,
        "pavilion_angle_deg": 41.0,
        "pavilion_depth_pct": 43.5,
        "girdle_pct": 2.0,
        "aspect_ratio": 1.0,
        "extras": {"corner_radius_pct": 15},  # corner radius as % of side
    },
    # -----------------------------------------------------------------------
    # Fancy cuts (GIA/AGS industry standards; see module docstring for refs)
    # -----------------------------------------------------------------------
    "radiant": {
        # Cropped-corner rectangular modified brilliant.
        # GIA reference: table 62–70%, depth 61–67%, typical 1.0–1.5 L:W.
        "table_pct": 62.0,
        "crown_angle_deg": 32.0,
        "crown_height_pct": 13.0,
        "pavilion_angle_deg": 41.0,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 2.5,
        "aspect_ratio": 0.75,       # width = 0.75 × length (~1.33:1 L:W)
        "extras": {
            "corner_cut_ratio": 0.10,  # fraction of corner removed
            "facet_count": 70,         # typical radiant facet count
        },
    },
    "asscher": {
        # Square step cut with heavily cropped corners (deep high crown).
        # GIA reference: table 60–68%, depth 60–66%, 1:1 L:W.
        "table_pct": 60.0,
        "crown_angle_deg": 25.0,
        "crown_height_pct": 15.0,
        "pavilion_angle_deg": 43.0,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 2.0,
        "aspect_ratio": 1.0,
        "extras": {
            "step_rows": 3,
            "corner_cut_ratio": 0.20,   # deeper corner cuts than emerald
        },
    },
    "trillion": {
        # Equilateral triangular modified brilliant (also called triangular brilliant).
        # GIA reference: table 50–60%, depth 32–48%, equilateral (L:W ≈ 1:1).
        "table_pct": 55.0,
        "crown_angle_deg": 34.0,
        "crown_height_pct": 11.0,
        "pavilion_angle_deg": 41.0,
        "pavilion_depth_pct": 37.0,
        "girdle_pct": 2.5,
        "aspect_ratio": 1.0,    # equilateral triangle; "width" = same as "length"
        "extras": {
            "sides": 3,
            "facet_count": 43,  # standard trillion facet count
        },
    },
    "heart": {
        # Heart-shaped modified brilliant.
        # GIA reference: table 53–63%, depth 58–62%, L:W ratio 0.90–1.10.
        "table_pct": 56.0,
        "crown_angle_deg": 34.5,
        "crown_height_pct": 15.0,
        "pavilion_angle_deg": 40.75,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 2.5,
        "aspect_ratio": 0.98,   # slight width/length imbalance typical for heart
        "extras": {
            "cleft_depth_pct": 10,  # depth of the V-cleft as % of width
            "facet_count": 59,
        },
    },
    "baguette": {
        # Rectangular step cut (narrow bar); common in channel-set side stones.
        # GIA reference: table 60–75%, depth 42–50%, L:W typically 2.5:1 to 4:1.
        "table_pct": 70.0,
        "crown_angle_deg": 8.0,
        "crown_height_pct": 4.0,
        "pavilion_angle_deg": 43.0,
        "pavilion_depth_pct": 40.0,
        "girdle_pct": 1.5,
        "aspect_ratio": 0.33,   # width = 0.33 × length (3:1 L:W)
        "extras": {
            "step_rows": 2,
            "corner_cut_ratio": 0.0,    # straight (no corner cut); tapered baguette has corners cut
        },
    },
    "briolette": {
        # Elongated double-cone (teardrop) with all-facet surface; no table or girdle.
        # Dimensions: height (long axis) × width; typical aspect ~0.50 (2:1 H:W).
        # "crown" facets are the upper hemisphere; "pavilion" the lower point.
        "table_pct": 0.0,           # no table on a briolette
        "crown_angle_deg": 30.0,
        "crown_height_pct": 50.0,   # upper half
        "pavilion_angle_deg": 45.0,
        "pavilion_depth_pct": 50.0, # lower half / pointed end
        "girdle_pct": 2.0,          # thin equatorial band
        "aspect_ratio": 0.50,       # width = 0.50 × height (~2:1 H:W)
        "extras": {
            "facet_rows": 8,    # horizontal rows of triangular facets
        },
    },

    # -----------------------------------------------------------------------
    # Historical / specialty cuts (third slice)
    # All map to an existing facet family; no worker change needed.
    # -----------------------------------------------------------------------

    "old_european": {
        # Precursor to round brilliant (pre-1930s).  Characteristics:
        # very high crown (~22%), small table (~40%), large open culet (visible from above).
        # Family: round_brilliant (N-gon facets, circular girdle).
        # GIA reference: crown angle ~40°, pavilion angle ~40°, table 35–53%.
        "table_pct": 40.0,
        "crown_angle_deg": 40.0,
        "crown_height_pct": 22.0,
        "pavilion_angle_deg": 40.0,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 3.0,
        "aspect_ratio": 1.0,
        "extras": {
            "facet_count": 58,
            "culet": "large",          # characteristic open culet
            "facet_family": "round_brilliant",
        },
    },

    "old_mine": {
        # Victorian-era cushion brilliant (pre-round brilliant).
        # High crown, small round table, large culet, squarish cushion outline.
        # Family: cushion (modified brilliant, soft-square footprint).
        # GIA reference: crown angle ~38–42°, cushion outline, large culet.
        "table_pct": 40.0,
        "crown_angle_deg": 38.0,
        "crown_height_pct": 20.0,
        "pavilion_angle_deg": 41.0,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 3.0,
        "aspect_ratio": 1.0,          # squarish cushion
        "extras": {
            "facet_count": 58,
            "culet": "large",
            "corner_radius_pct": 20,  # rounder corners than modern cushion
            "facet_family": "cushion",
        },
    },

    "rose_cut": {
        # Flat-base dome-top cut; triangular facets arranged in two rows.
        # No pavilion — all volume is in the crown dome.  table_pct=0 (no flat table).
        # Family: round_brilliant (circular girdle, N-gon facet rows).
        # GIA reference: crown angle ~15–25°, flat bottom, 6–24 triangular facets.
        # pavilion_angle_deg is a nominal placeholder (flat base = pavilion_depth_pct=0).
        "table_pct": 0.0,            # no table facet
        "crown_angle_deg": 20.0,     # shallow dome
        "crown_height_pct": 25.0,    # dome is ~25% of diameter
        "pavilion_angle_deg": 1.0,   # nominal; flat base encoded in pavilion_depth_pct=0
        "pavilion_depth_pct": 0.0,   # flat base; girdle sits on the stone
        "girdle_pct": 2.0,
        "aspect_ratio": 1.0,
        "extras": {
            "facet_count": 24,        # full rose cut (double rose = 24 facets)
            "facet_rows": 2,          # 6 base + 6 upper triangular facets per half
            "flat_base": True,
            "facet_family": "round_brilliant",
        },
    },

    "single_cut": {
        # Simplified brilliant, 17 or 18 facets — melee size side stones.
        # Table + 8 crown facets + 8 pavilion facets + girdle.
        # Family: round_brilliant (circular girdle, simplified N-gon facets).
        # Industry reference: table 60–70%, total depth ~50–55%.
        "table_pct": 65.0,
        "crown_angle_deg": 30.0,
        "crown_height_pct": 10.0,
        "pavilion_angle_deg": 40.0,
        "pavilion_depth_pct": 42.0,
        "girdle_pct": 2.0,
        "aspect_ratio": 1.0,
        "extras": {
            "facet_count": 17,
            "facet_family": "round_brilliant",
        },
    },

    "french_cut": {
        # Square step cut with X-pattern table; art-deco favourite.
        # High crown relative to width; corners sharp (no corner cut).
        # Family: princess (square modified brilliant footprint, step-like crown).
        # Industry reference: table ~65–70%, total depth ~55–60%, 1:1 L:W.
        "table_pct": 68.0,
        "crown_angle_deg": 28.0,
        "crown_height_pct": 11.0,
        "pavilion_angle_deg": 43.0,
        "pavilion_depth_pct": 42.0,
        "girdle_pct": 2.0,
        "aspect_ratio": 1.0,          # square
        "extras": {
            "step_rows": 1,            # single step row (X cross on table)
            "corner_cut_ratio": 0.0,   # sharp corners
            "facet_family": "princess",
        },
    },

    "half_moon": {
        # Semi-circular fancy (D-shaped or crescent).
        # One straight edge, one curved; modified brilliant facet pattern.
        # Family: oval (elliptical modified brilliant; worker trims to half).
        # Industry reference: table ~56%, depth ~58–62%, aspect ~0.56 (2:1 L:W).
        "table_pct": 56.0,
        "crown_angle_deg": 34.5,
        "crown_height_pct": 14.0,
        "pavilion_angle_deg": 40.75,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 2.5,
        "aspect_ratio": 0.56,         # width ≈ 0.56 × length (half-oval proportions)
        "extras": {
            "straight_edge": True,     # flat chord edge (trimmed oval)
            "facet_family": "oval",
        },
    },

    "trapezoid": {
        # Trapezoidal step cut — common tapered side stone alongside emerald cuts.
        # Four sides; two parallel (top/bottom) with one pair of angled sides.
        # Family: baguette (rectangular step cut; worker uses angled girdle).
        # Industry reference: table ~65%, depth ~45–50%, step_rows=2–3.
        "table_pct": 65.0,
        "crown_angle_deg": 10.0,
        "crown_height_pct": 5.0,
        "pavilion_angle_deg": 43.0,
        "pavilion_depth_pct": 40.0,
        "girdle_pct": 2.0,
        "aspect_ratio": 0.55,         # mid-range trapezoid width/length
        "extras": {
            "step_rows": 2,
            "taper_ratio": 0.80,       # ratio of narrow end to wide end
            "facet_family": "baguette",
        },
    },

    "kite": {
        # Kite or arrowhead cut — four-sided polygon with one acute point.
        # Brilliant-cut facet arrangement; angular fancy.
        # Family: trillion (triangular/polygonal modified brilliant).
        # Industry reference: table ~55%, depth ~45–55%, aspect ~0.65.
        "table_pct": 55.0,
        "crown_angle_deg": 34.0,
        "crown_height_pct": 12.0,
        "pavilion_angle_deg": 41.0,
        "pavilion_depth_pct": 40.0,
        "girdle_pct": 2.5,
        "aspect_ratio": 0.65,         # width ≈ 0.65 × length (kite outline)
        "extras": {
            "sides": 4,
            "acute_point": True,
            "facet_family": "trillion",
        },
    },

    "bullet": {
        # Bullet / tapered baguette with one pointed end.
        # Top is flat/rounded; bottom terminates in a point (like a pear with
        # a flattened rounded top instead of a second lobe).
        # Family: pear (teardrop modified brilliant; worker uses asymmetric outline).
        # Industry reference: table ~55%, depth ~55–60%, aspect ~0.60.
        "table_pct": 55.0,
        "crown_angle_deg": 33.0,
        "crown_height_pct": 13.0,
        "pavilion_angle_deg": 41.0,
        "pavilion_depth_pct": 43.0,
        "girdle_pct": 2.5,
        "aspect_ratio": 0.60,         # width ≈ 0.60 × length
        "extras": {
            "flat_top": True,          # rounded/flat top end (not pointed)
            "facet_family": "pear",
        },
    },

    "tapered_baguette": {
        # Baguette with both short ends angled inward (trapezoidal bar).
        # Narrower at one end; very common channel-set side stone.
        # Family: baguette (rectangular step cut; worker angles the short faces).
        # Industry reference: table ~68–72%, depth ~40–48%, step_rows=2.
        "table_pct": 70.0,
        "crown_angle_deg": 8.0,
        "crown_height_pct": 4.0,
        "pavilion_angle_deg": 43.0,
        "pavilion_depth_pct": 40.0,
        "girdle_pct": 1.5,
        "aspect_ratio": 0.30,         # narrow bar; slightly wider than baguette
        "extras": {
            "step_rows": 2,
            "taper_ratio": 0.70,       # narrow end / wide end width ratio
            "facet_family": "baguette",
        },
    },

    "lozenge": {
        # Four-pointed rhombus (diamond shape); step-cut facets.
        # Equal diagonals (square lozenge) or unequal (elongated).
        # Family: marquise (boat/pointed-oval; worker uses rhombus outline).
        # Industry reference: table ~55–65%, depth ~45–55%, L:W ≈ 1.5:1.
        "table_pct": 58.0,
        "crown_angle_deg": 18.0,
        "crown_height_pct": 9.0,
        "pavilion_angle_deg": 42.0,
        "pavilion_depth_pct": 42.0,
        "girdle_pct": 2.0,
        "aspect_ratio": 0.65,         # width = 0.65 × length (1.5:1 lozenge)
        "extras": {
            "step_rows": 2,
            "facet_family": "marquise",
        },
    },

    "shield": {
        # Irregular five-sided / shield-shaped stone.
        # Wide at top, tapering to a central point at bottom.
        # Brilliant-cut facets on large surface.
        # Family: trillion (polygonal modified brilliant; worker uses 5-sided outline).
        # Industry reference: table ~55%, depth ~45–55%, aspect ~0.85.
        "table_pct": 55.0,
        "crown_angle_deg": 35.0,
        "crown_height_pct": 13.0,
        "pavilion_angle_deg": 41.0,
        "pavilion_depth_pct": 42.0,
        "girdle_pct": 2.5,
        "aspect_ratio": 0.85,         # wide shield
        "extras": {
            "sides": 5,
            "facet_family": "trillion",
        },
    },

    "calf_head": {
        # Wide pear variant (also called "bouche"); low dome, very wide teardrop.
        # Broader than a standard pear; head is more oval and lower in profile.
        # Family: pear (teardrop modified brilliant; worker uses wider aspect).
        # Industry reference: table ~55%, depth ~55%, aspect ~0.75–0.80.
        "table_pct": 55.0,
        "crown_angle_deg": 32.0,
        "crown_height_pct": 13.0,
        "pavilion_angle_deg": 40.0,
        "pavilion_depth_pct": 42.0,
        "girdle_pct": 2.5,
        "aspect_ratio": 0.78,         # notably wider than standard pear (0.62)
        "extras": {
            "wide_head": True,
            "facet_family": "pear",
        },
    },
}


# ---------------------------------------------------------------------------
# Feature node helpers
# ---------------------------------------------------------------------------

def _gemstone_node(
    node_id: str,
    cut: str,
    diameter_mm: float,
    props: GemProportions,
    position: Optional[list] = None,
    orientation_deg: Optional[list] = None,
    material: str = "diamond",
) -> dict:
    """Build the JSON feature node for a gemstone."""
    node: dict = {
        "id": node_id,
        "op": "gemstone",
        "cut": cut,
        "diameter_mm": diameter_mm,
        "aspect_ratio": props.aspect_ratio,
        "table_pct": props.table_pct,
        "crown_angle_deg": props.crown_angle_deg,
        "crown_height_pct": props.crown_height_pct,
        "pavilion_angle_deg": props.pavilion_angle_deg,
        "pavilion_depth_pct": props.pavilion_depth_pct,
        "girdle_pct": props.girdle_pct,
        "total_depth_pct": props.total_depth_pct,
        "material": material,
    }
    if props.extras:
        node["extras"] = props.extras
    if position is not None:
        node["position"] = position
    if orientation_deg is not None:
        node["orientation_deg"] = orientation_deg
    return node


# ---------------------------------------------------------------------------
# LLM tool: jewelry_create_gemstone
# ---------------------------------------------------------------------------

jewelry_create_gemstone_spec = ToolSpec(
    name="jewelry_create_gemstone",
    description=(
        "Append a `gemstone` node to a `.feature` file. "
        "Generates a parametric gemstone solid with industry-standard proportions. "
        "Classic cuts: round_brilliant, princess, oval, emerald, marquise, pear, cushion. "
        "Fancy cuts: radiant, asscher, trillion, heart, baguette, briolette. "
        "Historical/specialty cuts: old_european, old_mine, rose_cut, single_cut, french_cut, "
        "half_moon, trapezoid, kite, bullet, tapered_baguette, lozenge, shield, calf_head. "
        "Size the stone by carat OR by diameter_mm (long axis for non-round cuts). "
        "Carat formula: carat = (diameter_mm / ref_mm)^3 where ref_mm is calibrated per cut "
        "and material density (default: diamond, 3.51 g/cm³). "
        "Pass material='ruby' (or density_g_cm3=4.00) for accurate coloured-stone carat weights. "
        "The gemstone node stores proportions used by the OCCT "
        "worker to build a closed solid (pavilion cone + girdle cylinder + crown prism). "
        "Use jewelry_cut_gem_seat to cut the matching seat from a ring shank or bezel. "
        "Use jewelry_gem_report for a read-only gemologist-style proportion analysis."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "cut": {
                "type": "string",
                "enum": sorted(GEMSTONE_CUTS),
                "description": (
                    "Gemstone cut style. "
                    "Classic: round_brilliant=57 facets, princess=square brilliant, oval=elliptical, "
                    "emerald=rectangular step, marquise=boat, pear=teardrop, cushion=soft square. "
                    "Fancy: radiant=cropped-corner rectangular brilliant, asscher=square step, "
                    "trillion=triangular brilliant, heart=heart-shaped, "
                    "baguette=narrow step cut, briolette=all-facet teardrop. "
                    "Historical: old_european=high-crown round precursor, old_mine=Victorian cushion, "
                    "rose_cut=flat-base dome, single_cut=17-facet melee brilliant, "
                    "french_cut=square step art-deco, half_moon=D-shaped semi-circular, "
                    "trapezoid=tapered step side stone, kite=arrowhead angular fancy, "
                    "bullet=pointed-base tapered fancy, tapered_baguette=angled-end bar, "
                    "lozenge=rhombus step cut, shield=five-sided brilliant, "
                    "calf_head=wide-pear bouche variant."
                ),
            },
            "carat": {
                "type": "number",
                "description": (
                    "Stone weight in carats. Converted to mm via the carat formula. "
                    "Provide carat OR diameter_mm, not both. "
                    "For coloured stones supply material or density_g_cm3 for accuracy."
                ),
            },
            "diameter_mm": {
                "type": "number",
                "description": (
                    "Primary dimension in mm: girdle diameter (round brilliant) or "
                    "long axis (all other cuts). Provide diameter_mm OR carat, not both."
                ),
            },
            "material": {
                "type": "string",
                "description": (
                    "Stone material name, e.g. 'diamond', 'ruby', 'sapphire', 'emerald', "
                    "'amethyst', 'topaz', 'garnet', 'aquamarine', 'citrine', 'peridot', "
                    "'tanzanite', 'opal'. Used for density lookup (carat↔mm). Default: 'diamond'."
                ),
            },
            "density_g_cm3": {
                "type": "number",
                "description": (
                    "Explicit material density in g/cm³. Overrides material lookup. "
                    "Use this for unusual stones not in the built-in density table."
                ),
            },
            "position": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[x, y, z] placement in model space (mm). Default: [0, 0, 0].",
            },
            "orientation_deg": {
                "type": "array",
                "items": {"type": "number"},
                "description": "[rx, ry, rz] Euler angles in degrees. Default: [0, 0, 0].",
            },
            "table_pct": {"type": "number", "description": "Table width override (% of diameter). Optional."},
            "crown_angle_deg": {"type": "number", "description": "Crown angle override (degrees). Optional."},
            "pavilion_angle_deg": {"type": "number", "description": "Pavilion angle override (degrees). Optional."},
            "girdle_pct": {"type": "number", "description": "Girdle thickness override (% of diameter). Optional."},
            "aspect_ratio": {
                "type": "number",
                "description": "Width/length ratio override. 1.0=square/round. Default per cut.",
            },
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id", "cut"],
    },
)


@register(jewelry_create_gemstone_spec, write=True)
async def run_jewelry_create_gemstone(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id_str     = a.get("file_id", "").strip()
    cut             = a.get("cut", "").strip()
    carat           = a.get("carat", None)
    diameter_mm     = a.get("diameter_mm", None)
    material        = a.get("material", "diamond")
    density_g_cm3   = a.get("density_g_cm3", None)
    position        = a.get("position", None)
    orientation_deg = a.get("orientation_deg", None)
    node_id         = a.get("id", "").strip()

    prop_overrides = {
        k: a.get(k)
        for k in ("table_pct", "crown_angle_deg", "pavilion_angle_deg", "girdle_pct", "aspect_ratio")
        if a.get(k) is not None
    }

    # Validate required fields
    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if not cut:
        return err_payload("cut is required", "BAD_ARGS")
    if cut not in GEMSTONE_CUTS:
        return err_payload(
            f"Unknown cut {cut!r}. Valid cuts: {sorted(GEMSTONE_CUTS)}", "BAD_ARGS"
        )

    if carat is not None and diameter_mm is not None:
        return err_payload("Provide carat OR diameter_mm, not both", "BAD_ARGS")
    if carat is None and diameter_mm is None:
        return err_payload("One of carat or diameter_mm is required", "BAD_ARGS")

    if carat is not None:
        try:
            carat = float(carat)
        except Exception:
            return err_payload("carat must be a number", "BAD_ARGS")
        if carat <= 0:
            return err_payload("carat must be positive", "BAD_ARGS")

    if diameter_mm is not None:
        try:
            diameter_mm = float(diameter_mm)
        except Exception:
            return err_payload("diameter_mm must be a number", "BAD_ARGS")
        if diameter_mm <= 0:
            return err_payload("diameter_mm must be positive", "BAD_ARGS")

    # Validate numeric overrides
    for key in ("table_pct", "crown_angle_deg", "pavilion_angle_deg", "girdle_pct"):
        val = prop_overrides.get(key)
        if val is not None:
            try:
                prop_overrides[key] = float(val)
            except Exception:
                return err_payload(f"{key} must be a number", "BAD_ARGS")
            if prop_overrides[key] <= 0:
                return err_payload(f"{key} must be positive", "BAD_ARGS")

    ar = prop_overrides.get("aspect_ratio")
    if ar is not None:
        try:
            prop_overrides["aspect_ratio"] = float(ar)
        except Exception:
            return err_payload("aspect_ratio must be a number", "BAD_ARGS")
        if prop_overrides["aspect_ratio"] <= 0:
            return err_payload("aspect_ratio must be positive", "BAD_ARGS")

    if density_g_cm3 is not None:
        try:
            density_g_cm3 = float(density_g_cm3)
        except Exception:
            return err_payload("density_g_cm3 must be a number", "BAD_ARGS")
        if density_g_cm3 <= 0:
            return err_payload("density_g_cm3 must be positive", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    # Resolve proportions (pass material + density for correct carat→mm sizing)
    try:
        props = gemstone_proportions(
            cut,
            diameter_mm=diameter_mm,
            carat=carat,
            material=str(material) if material else None,
            density_g_cm3=density_g_cm3,
            **prop_overrides,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    if not node_id:
        node_id = next_node_id(content, "gemstone")

    node = _gemstone_node(
        node_id,
        cut,
        props.diameter_mm,
        props,
        position=position,
        orientation_deg=orientation_deg,
        material=str(material) if material else "diamond",
    )

    _name, nid, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    # carat_approx uses the same material density so the value is accurate
    mat_label = str(material) if material else None
    return ok_payload({
        "file_id": file_id_str,
        "id": nid,
        "op": "gemstone",
        "cut": cut,
        "diameter_mm": props.diameter_mm,
        "carat_approx": round(
            carat_from_mm(cut, props.diameter_mm, material=mat_label, density_g_cm3=density_g_cm3),
            3,
        ),
        "total_depth_mm": round(props.total_depth_pct / 100 * props.diameter_mm, 3),
    })


# ---------------------------------------------------------------------------
# LLM tool: jewelry_gem_report  (read-only)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Light-return / proportion grade heuristic
# ---------------------------------------------------------------------------

# Per-family ideal proportion windows used to grade light return.
# Keys: facet family label → {
#   "table_pct"     : (min, max),  # ideal table % range
#   "depth_pct"     : (min, max),  # ideal total depth % range
#   "crown_angle"   : (min, max),  # ideal crown angle (degrees)
#   "pavilion_angle": (min, max),  # ideal pavilion angle (degrees)
# }
# Grades: Excellent (all in ideal), Very Good (1 miss), Good (2 miss), Fair (3+).
# Sources: GIA 4Cs cut grade methodology; AGS cut grading system.
_GRADE_WINDOWS: dict[str, dict] = {
    "round_brilliant": {
        "table_pct":      (53.0, 58.0),
        "depth_pct":      (59.0, 62.5),
        "crown_angle":    (33.7, 35.8),
        "pavilion_angle": (40.6, 41.8),
    },
    "princess": {
        "table_pct":      (62.0, 82.0),
        "depth_pct":      (64.0, 75.0),
        "crown_angle":    (25.0, 35.0),
        "pavilion_angle": (40.0, 45.0),
    },
    "oval": {
        "table_pct":      (53.0, 63.0),
        "depth_pct":      (58.0, 62.0),
        "crown_angle":    (30.0, 38.0),
        "pavilion_angle": (38.0, 43.0),
    },
    "emerald": {
        "table_pct":      (60.0, 72.0),
        "depth_pct":      (60.0, 68.0),
        "crown_angle":    (12.0, 20.0),
        "pavilion_angle": (43.0, 48.0),
    },
    "marquise": {
        "table_pct":      (53.0, 63.0),
        "depth_pct":      (58.0, 62.0),
        "crown_angle":    (30.0, 36.0),
        "pavilion_angle": (38.0, 43.0),
    },
    "pear": {
        "table_pct":      (53.0, 63.0),
        "depth_pct":      (58.0, 62.0),
        "crown_angle":    (30.0, 38.0),
        "pavilion_angle": (38.0, 43.0),
    },
    "cushion": {
        "table_pct":      (55.0, 68.0),
        "depth_pct":      (60.0, 68.0),
        "crown_angle":    (30.0, 38.0),
        "pavilion_angle": (38.0, 44.0),
    },
    "radiant": {
        "table_pct":      (58.0, 72.0),
        "depth_pct":      (59.0, 67.0),
        "crown_angle":    (28.0, 36.0),
        "pavilion_angle": (38.0, 44.0),
    },
    "asscher": {
        "table_pct":      (60.0, 68.0),
        "depth_pct":      (60.0, 66.0),
        "crown_angle":    (20.0, 30.0),
        "pavilion_angle": (40.0, 46.0),
    },
    "trillion": {
        "table_pct":      (50.0, 60.0),
        "depth_pct":      (36.0, 52.0),
        "crown_angle":    (30.0, 38.0),
        "pavilion_angle": (38.0, 44.0),
    },
    "heart": {
        "table_pct":      (53.0, 63.0),
        "depth_pct":      (58.0, 62.0),
        "crown_angle":    (32.0, 37.0),
        "pavilion_angle": (39.0, 43.0),
    },
    "baguette": {
        "table_pct":      (60.0, 75.0),
        "depth_pct":      (42.0, 52.0),
        "crown_angle":    (5.0, 15.0),
        "pavilion_angle": (40.0, 46.0),
    },
    "briolette": {
        # No flat table; graded on crown/pavilion balance only.
        "table_pct":      (0.0, 5.0),    # effectively 0
        "depth_pct":      (95.0, 110.0), # deep double-cone
        "crown_angle":    (25.0, 35.0),
        "pavilion_angle": (40.0, 50.0),
    },
    # Historical / specialty — use nearest-family windows
    "old_european":    {"table_pct": (35.0, 53.0), "depth_pct": (58.0, 70.0),
                        "crown_angle": (38.0, 44.0), "pavilion_angle": (38.0, 43.0)},
    "old_mine":        {"table_pct": (35.0, 53.0), "depth_pct": (58.0, 70.0),
                        "crown_angle": (36.0, 42.0), "pavilion_angle": (38.0, 44.0)},
    "rose_cut":        {"table_pct": (0.0, 5.0), "depth_pct": (20.0, 35.0),
                        "crown_angle": (15.0, 27.0), "pavilion_angle": (0.0, 5.0)},
    "single_cut":      {"table_pct": (55.0, 75.0), "depth_pct": (48.0, 58.0),
                        "crown_angle": (25.0, 35.0), "pavilion_angle": (38.0, 44.0)},
    "french_cut":      {"table_pct": (60.0, 74.0), "depth_pct": (50.0, 64.0),
                        "crown_angle": (22.0, 34.0), "pavilion_angle": (40.0, 46.0)},
    "half_moon":       {"table_pct": (52.0, 64.0), "depth_pct": (56.0, 64.0),
                        "crown_angle": (30.0, 38.0), "pavilion_angle": (38.0, 43.0)},
    "trapezoid":       {"table_pct": (60.0, 74.0), "depth_pct": (42.0, 52.0),
                        "crown_angle": (7.0, 15.0), "pavilion_angle": (40.0, 46.0)},
    "kite":            {"table_pct": (50.0, 62.0), "depth_pct": (44.0, 56.0),
                        "crown_angle": (30.0, 38.0), "pavilion_angle": (38.0, 44.0)},
    "bullet":          {"table_pct": (52.0, 62.0), "depth_pct": (54.0, 64.0),
                        "crown_angle": (29.0, 37.0), "pavilion_angle": (38.0, 44.0)},
    "tapered_baguette":{"table_pct": (62.0, 76.0), "depth_pct": (40.0, 50.0),
                        "crown_angle": (5.0, 13.0), "pavilion_angle": (40.0, 46.0)},
    "lozenge":         {"table_pct": (52.0, 68.0), "depth_pct": (44.0, 56.0),
                        "crown_angle": (14.0, 24.0), "pavilion_angle": (38.0, 46.0)},
    "shield":          {"table_pct": (50.0, 62.0), "depth_pct": (44.0, 56.0),
                        "crown_angle": (31.0, 39.0), "pavilion_angle": (38.0, 44.0)},
    "calf_head":       {"table_pct": (52.0, 62.0), "depth_pct": (54.0, 64.0),
                        "crown_angle": (29.0, 36.0), "pavilion_angle": (37.0, 43.0)},
}


def _proportion_grade(props: GemProportions) -> str:
    """Return a simple light-return / proportion grade for the given proportions.

    Grades:
        Excellent  — all four proportion indicators fall within the ideal window
        Very Good  — one indicator outside the ideal window
        Good       — two indicators outside the ideal window
        Fair       — three or more indicators outside the ideal window

    The ideal windows are per-cut (see ``_GRADE_WINDOWS``).  For cuts not in
    the table, the nearest applicable family is used.
    """
    windows = _GRADE_WINDOWS.get(props.cut, _GRADE_WINDOWS["round_brilliant"])

    def _in(val: float, lo: float, hi: float) -> bool:
        return lo <= val <= hi

    checks = [
        _in(props.table_pct,         *windows["table_pct"]),
        _in(props.total_depth_pct,   *windows["depth_pct"]),
        _in(props.crown_angle_deg,   *windows["crown_angle"]),
        _in(props.pavilion_angle_deg,*windows["pavilion_angle"]),
    ]
    misses = checks.count(False)
    if misses == 0:
        return "Excellent"
    if misses == 1:
        return "Very Good"
    if misses == 2:
        return "Good"
    return "Fair"


jewelry_gem_report_spec = ToolSpec(
    name="jewelry_gem_report",
    description=(
        "Read-only gemologist-style report for a gemstone cut + size. "
        "Given a cut and either carat or diameter_mm (plus optional material), "
        "returns: estimated carat, spread (mm), depth %, table %, length/width ratio, "
        "crown and pavilion angle summary, and a light-return/proportion grade "
        "(Excellent / Very Good / Good / Fair) based on GIA/AGS ideal windows. "
        "Does NOT write any file — use this to inspect proportions before calling "
        "jewelry_create_gemstone."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cut": {
                "type": "string",
                "enum": sorted(GEMSTONE_CUTS),
                "description": "Gemstone cut style.",
            },
            "carat": {
                "type": "number",
                "description": (
                    "Stone weight in carats. Converted to mm via the carat formula. "
                    "Provide carat OR diameter_mm, not both."
                ),
            },
            "diameter_mm": {
                "type": "number",
                "description": (
                    "Primary dimension in mm (girdle diameter for round_brilliant, "
                    "long axis for all others). Provide diameter_mm OR carat, not both."
                ),
            },
            "material": {
                "type": "string",
                "description": (
                    "Stone material for density lookup (e.g. 'diamond', 'ruby', 'sapphire'). "
                    "Affects carat↔mm conversion only.  Default: 'diamond'."
                ),
            },
            "density_g_cm3": {
                "type": "number",
                "description": "Explicit material density in g/cm³. Overrides material lookup.",
            },
        },
        "required": ["cut"],
    },
)


@register(jewelry_gem_report_spec, write=False)
async def run_jewelry_gem_report(ctx: ProjectCtx, args: bytes) -> str:
    """Read-only gemologist report — computes from spec, writes nothing."""
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    cut           = a.get("cut", "").strip()
    carat         = a.get("carat", None)
    diameter_mm   = a.get("diameter_mm", None)
    material      = a.get("material", None)
    density_g_cm3 = a.get("density_g_cm3", None)

    if not cut:
        return err_payload("cut is required", "BAD_ARGS")
    if cut not in GEMSTONE_CUTS:
        return err_payload(
            f"Unknown cut {cut!r}. Valid cuts: {sorted(GEMSTONE_CUTS)}", "BAD_ARGS"
        )
    if carat is not None and diameter_mm is not None:
        return err_payload("Provide carat OR diameter_mm, not both", "BAD_ARGS")
    if carat is None and diameter_mm is None:
        return err_payload("One of carat or diameter_mm is required", "BAD_ARGS")

    if carat is not None:
        try:
            carat = float(carat)
        except Exception:
            return err_payload("carat must be a number", "BAD_ARGS")
        if carat <= 0:
            return err_payload("carat must be positive", "BAD_ARGS")

    if diameter_mm is not None:
        try:
            diameter_mm = float(diameter_mm)
        except Exception:
            return err_payload("diameter_mm must be a number", "BAD_ARGS")
        if diameter_mm <= 0:
            return err_payload("diameter_mm must be positive", "BAD_ARGS")

    if density_g_cm3 is not None:
        try:
            density_g_cm3 = float(density_g_cm3)
        except Exception:
            return err_payload("density_g_cm3 must be a number", "BAD_ARGS")
        if density_g_cm3 <= 0:
            return err_payload("density_g_cm3 must be positive", "BAD_ARGS")

    try:
        props = gemstone_proportions(
            cut,
            diameter_mm=diameter_mm,
            carat=carat,
            material=str(material) if material else None,
            density_g_cm3=density_g_cm3,
        )
    except ValueError as e:
        return err_payload(str(e), "BAD_ARGS")

    mat_label = str(material) if material else None
    carat_est = carat_from_mm(
        cut, props.diameter_mm, material=mat_label, density_g_cm3=density_g_cm3
    )

    # Length/width ratio: long axis / short axis (≥ 1.0).
    # For round brilliant both axes equal, so lw_ratio = 1.0.
    # For others: long axis = diameter_mm, short axis = diameter_mm * aspect_ratio.
    if props.aspect_ratio > 0:
        lw_ratio = round(1.0 / props.aspect_ratio, 3)
    else:
        lw_ratio = None  # degenerate

    # Depth in mm
    depth_mm = round(props.total_depth_pct / 100.0 * props.diameter_mm, 3)
    # Width (short axis) in mm
    width_mm = round(props.diameter_mm * props.aspect_ratio, 3)

    grade = _proportion_grade(props)

    # Facet family (from extras if tagged, else the cut itself)
    facet_family = props.extras.get("facet_family", cut)

    return ok_payload({
        "cut": cut,
        "facet_family": facet_family,
        "material": mat_label or "diamond",
        # Sizing
        "spread_mm": round(props.diameter_mm, 3),
        "width_mm": width_mm,
        "depth_mm": depth_mm,
        "carat_est": round(carat_est, 3),
        # Proportions
        "table_pct": round(props.table_pct, 1),
        "total_depth_pct": round(props.total_depth_pct, 1),
        "crown_height_pct": round(props.crown_height_pct, 1),
        "pavilion_depth_pct": round(props.pavilion_depth_pct, 1),
        "girdle_pct": round(props.girdle_pct, 1),
        # Angles
        "crown_angle_deg": round(props.crown_angle_deg, 2),
        "pavilion_angle_deg": round(props.pavilion_angle_deg, 2),
        # Shape
        "aspect_ratio": round(props.aspect_ratio, 3),
        "lw_ratio": lw_ratio,
        # Grade
        "proportion_grade": grade,
    })
