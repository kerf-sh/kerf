"""
kerf_cad_core.jewelry.metal_cost
================================

Metal weight and casting-cost estimator for jewelry CAD.

This module is intentionally pure-Python with no external dependencies
so it can be imported, tested, and used on any machine without OCCT.

## Density table

Alloy densities in g/cm³, sourced from industry references:

  - Gold alloys: World Gold Council "Handbook on Gold Alloys" + Legor Group
    technical data sheets (2023). Karat values use standard UK/US compositions.
  - Platinum 950: Platinum Guild International standard composition (95% Pt
    5% Ru/Co/Cu typical). Density 21.4–21.5 g/cm³.
  - Palladium 950: Platinum Guild International, ~11.0 g/cm³.
  - Sterling silver 925: Handy & Harman, 10.36 g/cm³.
  - Fine silver: 10.49 g/cm³ (NIST).
  - Titanium: grade 2 (commercially pure), ASTM B265, 4.51 g/cm³.
  - Brass (70/30 CuZn): Copper Development Association, 8.53 g/cm³.
  - Bronze (90/10 CuSn): Copper Development Association, 8.78 g/cm³.

## Unit conversions

  - 1 troy ounce (ozt) = 31.1034768 g  (NIST)
  - 1 pennyweight (dwt) = 1/20 ozt = 1.55517384 g  (traditional jewelry unit)
  - 1 mm³ = 1e-3 cm³ (used for volume input which is in mm³ = CAD units)

## Casting allowance

Lost-wax casting always produces more metal waste than the net part weight:
  - Sprue / button: the column of metal that fills the sprue tube
    (~8–12% for typical hollow shanks, higher for thick bands)
  - Button: retained casting-button metal (~3–5%)
  - Flashing / overflow seams (~1–3%)

The combined "gross/net" ratio is typically 1.10–1.20 for well-optimised
spruing. The default used here is 15% (gross = net × 1.15), which is a
conservative industry midpoint. Casters who optimise sprue placement and
use a vacuum–pressure machine can reach 10%; high-complexity multi-gate
moulds may need 20–25%. The value is fully configurable via
`casting_allowance_pct`.

## Integration with Kerf material files

If a project has a `.material` file with `physical.rho_kg_m3` populated
(as all seed materials do), you can pass that density directly:

    density_g_cm3 = mat["physical"]["rho_kg_m3"] / 1000.0
    grams = metal_weight(volume_mm3, density_g_cm3=density_g_cm3)

The `metal_weight` function accepts either:
  - `metal` — a string key resolved from `METAL_DENSITY_G_CM3`, or
  - `density_g_cm3` — an explicit float override.

Pass `density_g_cm3` when you have already resolved the density from a
material file; pass `metal` when the user picks from the built-in menu.
"""

from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Density table  (g/cm³)
# ---------------------------------------------------------------------------

METAL_DENSITY_G_CM3: dict[str, float] = {
    # Yellow gold alloys
    "10k_yellow": 11.57,   # 41.7% Au, 52% Ag+Cu, 6.3% Zn  — WGC Handbook
    "14k_yellow": 13.07,   # 58.3% Au, 30% Ag, 11.7% Cu   — WGC Handbook
    "18k_yellow": 15.58,   # 75% Au, 12.5% Ag, 12.5% Cu   — WGC / Legor DS-18Y
    "22k_yellow": 17.80,   # 91.7% Au, 5% Ag, 3.3% Cu     — WGC Handbook
    "24k_yellow": 19.32,   # 99.9% Au                       — NIST pure gold
    # White gold alloys  (Pd-white; Ni-white ≈ same density range)
    "10k_white":  11.61,   # 41.7% Au, Pd/Ag/Cu balance    — Legor DS-10W
    "14k_white":  13.25,   # 58.3% Au, Pd/Cu balance        — Legor DS-14W
    "18k_white":  15.60,   # 75% Au, Pd/Cu balance          — Legor DS-18W-PD
    # Rose gold alloys
    "10k_rose":   11.59,   # 41.7% Au, high Cu              — Legor DS-10R
    "14k_rose":   13.20,   # 58.3% Au, high Cu              — Legor DS-14R
    "18k_rose":   15.45,   # 75% Au, ~22% Cu, 3% Ag         — Legor DS-18R
    # Platinum & palladium
    "platinum_950": 21.40, # 95% Pt 5% Ru/Co   — PGI standard; range 21.4–21.5
    "palladium_950": 11.00, # 95% Pd 5% Ru      — PGI; range 10.9–11.1
    # Silver
    "sterling_925": 10.36, # 92.5% Ag 7.5% Cu   — Handy & Harman
    "fine_silver":  10.49, # 99.9% Ag            — NIST
    # Other jewelry metals
    "titanium":    4.51,   # Grade 2 commercially pure      — ASTM B265
    "brass":       8.53,   # 70/30 CuZn                     — CDA C26000
    "bronze":      8.78,   # 90/10 CuSn (phosphor bronze)   — CDA C52100
}

# Human-readable labels for the UI (maps key → display name)
METAL_LABELS: dict[str, str] = {
    "10k_yellow":    "10k Yellow Gold",
    "14k_yellow":    "14k Yellow Gold",
    "18k_yellow":    "18k Yellow Gold",
    "22k_yellow":    "22k Yellow Gold",
    "24k_yellow":    "24k Yellow Gold (Fine)",
    "10k_white":     "10k White Gold",
    "14k_white":     "14k White Gold",
    "18k_white":     "18k White Gold",
    "10k_rose":      "10k Rose Gold",
    "14k_rose":      "14k Rose Gold",
    "18k_rose":      "18k Rose Gold",
    "platinum_950":  "Platinum 950",
    "palladium_950": "Palladium 950",
    "sterling_925":  "Sterling Silver 925",
    "fine_silver":   "Fine Silver",
    "titanium":      "Titanium (Grade 2)",
    "brass":         "Brass (70/30)",
    "bronze":        "Bronze (90/10)",
}

# ---------------------------------------------------------------------------
# Unit conversion constants
# ---------------------------------------------------------------------------

GRAMS_PER_DWT: float = 1.55517384   # 1 pennyweight = 1.55517384 g  (NIST)
GRAMS_PER_OZT: float = 31.1034768   # 1 troy ounce  = 31.1034768 g  (NIST)
MM3_PER_CM3:   float = 1000.0       # 1 cm³ = 1000 mm³


# ---------------------------------------------------------------------------
# Core calculations
# ---------------------------------------------------------------------------

def grams_to_dwt(grams: float) -> float:
    """Convert grams to pennyweight (dwt)."""
    return grams / GRAMS_PER_DWT


def grams_to_ozt(grams: float) -> float:
    """Convert grams to troy ounces (ozt)."""
    return grams / GRAMS_PER_OZT


def dwt_to_grams(dwt: float) -> float:
    """Convert pennyweight to grams."""
    return dwt * GRAMS_PER_DWT


def ozt_to_grams(ozt: float) -> float:
    """Convert troy ounces to grams."""
    return ozt * GRAMS_PER_OZT


def resolve_density(
    metal: Optional[str] = None,
    density_g_cm3: Optional[float] = None,
) -> float:
    """
    Resolve density in g/cm³.

    Priority: explicit `density_g_cm3` > `metal` key lookup.
    Raises ValueError for unknown metal keys or invalid density values.
    """
    if density_g_cm3 is not None:
        if density_g_cm3 <= 0:
            raise ValueError(f"density_g_cm3 must be positive, got {density_g_cm3}")
        return float(density_g_cm3)
    if metal is None:
        raise ValueError("Either metal or density_g_cm3 must be provided")
    key = metal.strip().lower()
    if key not in METAL_DENSITY_G_CM3:
        raise ValueError(
            f"Unknown metal '{metal}'. Valid keys: {sorted(METAL_DENSITY_G_CM3)}"
        )
    return METAL_DENSITY_G_CM3[key]


def metal_weight(
    volume_mm3: float,
    metal: Optional[str] = None,
    density_g_cm3: Optional[float] = None,
) -> dict:
    """
    Calculate the net weight of a metal body.

    Parameters
    ----------
    volume_mm3 : float
        Volume of the part in cubic millimetres (standard CAD unit in Kerf).
        You can pass the volume from a OCCT GProp_GProps result directly:
            props = GProp_GProps()
            brepgprop.VolumeProperties(shape, props)
            vol = props.Mass()  # mm³ when model units are mm
    metal : str, optional
        Key from METAL_DENSITY_G_CM3.  Mutually exclusive with density_g_cm3.
    density_g_cm3 : float, optional
        Explicit density override (from a .material file or lab measurement).
        When provided, `metal` is ignored.

    Returns
    -------
    dict with keys:
        grams     — net weight in grams
        dwt       — net weight in pennyweight
        ozt       — net weight in troy ounces
        metal     — the resolved metal key (or None if density override used)
        density_g_cm3 — density used
        volume_mm3    — volume used
    """
    if volume_mm3 <= 0:
        raise ValueError(f"volume_mm3 must be positive, got {volume_mm3}")
    density = resolve_density(metal, density_g_cm3)
    volume_cm3 = volume_mm3 / MM3_PER_CM3
    grams = density * volume_cm3
    return {
        "grams": grams,
        "dwt": grams_to_dwt(grams),
        "ozt": grams_to_ozt(grams),
        "metal": metal,
        "density_g_cm3": density,
        "volume_mm3": volume_mm3,
    }


def casting_weight(
    net_grams: float,
    casting_allowance_pct: float = 15.0,
) -> dict:
    """
    Estimate gross casting weight including sprue/button/flashing allowance.

    Parameters
    ----------
    net_grams : float
        Net part weight in grams (from metal_weight).
    casting_allowance_pct : float
        Percentage overhead for sprue, button, and flashing.
        Default 15% (gross = net × 1.15).
        Typical range: 10% (optimised gate) to 25% (complex multi-gate).

    Returns
    -------
    dict with keys:
        net_grams           — the input net weight
        allowance_pct       — the configured allowance percentage
        allowance_grams     — overhead grams (sprue + button + flashing)
        gross_grams         — total casting weight (net + allowance)
        gross_dwt           — gross weight in pennyweight
        gross_ozt           — gross weight in troy ounces
    """
    if net_grams <= 0:
        raise ValueError(f"net_grams must be positive, got {net_grams}")
    if casting_allowance_pct < 0:
        raise ValueError(f"casting_allowance_pct must be >= 0, got {casting_allowance_pct}")
    factor = 1.0 + casting_allowance_pct / 100.0
    gross = net_grams * factor
    allowance = gross - net_grams
    return {
        "net_grams": net_grams,
        "allowance_pct": casting_allowance_pct,
        "allowance_grams": allowance,
        "gross_grams": gross,
        "gross_dwt": grams_to_dwt(gross),
        "gross_ozt": grams_to_ozt(gross),
    }


def casting_cost(
    volume_mm3: float,
    metal: Optional[str] = None,
    density_g_cm3: Optional[float] = None,
    metal_price_per_gram: float = 0.0,
    labor: float = 0.0,
    finishing: float = 0.0,
    casting_allowance_pct: float = 15.0,
) -> dict:
    """
    Produce an itemised casting cost estimate.

    Metal price is supplied by the user (no live market feed — prices vary
    by supplier, purity, form, and currency). Use spot gold/silver prices
    as a baseline and add your supplier's premium.

    Parameters
    ----------
    volume_mm3 : float
        Part volume in mm³.
    metal : str, optional
        Metal key (see METAL_DENSITY_G_CM3). Mutually exclusive with
        density_g_cm3.
    density_g_cm3 : float, optional
        Explicit density override.
    metal_price_per_gram : float
        Metal spot price in your currency per gram.
        Example: 18k yellow gold ≈ $38 USD/g at ~$1950/ozt spot.
    labor : float
        Bench labor cost (casting, cleanup, polishing) in your currency.
    finishing : float
        Finishing / plating / rhodium cost in your currency.
    casting_allowance_pct : float
        Sprue/button/flashing overhead, default 15%.

    Returns
    -------
    dict with full itemised breakdown:
        metal            — metal key
        density_g_cm3    — density used
        volume_mm3       — input volume
        net_grams        — net part weight
        net_dwt          — net weight in dwt
        net_ozt          — net weight in ozt
        allowance_pct    — casting allowance used
        gross_grams      — total metal to purchase
        gross_dwt        — gross weight in dwt
        gross_ozt        — gross weight in ozt
        metal_price_per_gram  — input price
        metal_cost       — gross_grams × metal_price_per_gram
        labor            — input labor cost
        finishing        — input finishing cost
        total_cost       — metal_cost + labor + finishing
    """
    if volume_mm3 <= 0:
        raise ValueError(f"volume_mm3 must be positive, got {volume_mm3}")
    if metal_price_per_gram < 0:
        raise ValueError(f"metal_price_per_gram must be >= 0, got {metal_price_per_gram}")
    if labor < 0:
        raise ValueError(f"labor must be >= 0, got {labor}")
    if finishing < 0:
        raise ValueError(f"finishing must be >= 0, got {finishing}")

    weight = metal_weight(volume_mm3, metal=metal, density_g_cm3=density_g_cm3)
    cast = casting_weight(weight["grams"], casting_allowance_pct=casting_allowance_pct)
    metal_cost_value = cast["gross_grams"] * metal_price_per_gram
    total = metal_cost_value + labor + finishing

    return {
        "metal": weight["metal"],
        "density_g_cm3": weight["density_g_cm3"],
        "volume_mm3": volume_mm3,
        "net_grams": weight["grams"],
        "net_dwt": weight["dwt"],
        "net_ozt": weight["ozt"],
        "allowance_pct": casting_allowance_pct,
        "gross_grams": cast["gross_grams"],
        "gross_dwt": cast["gross_dwt"],
        "gross_ozt": cast["gross_ozt"],
        "metal_price_per_gram": metal_price_per_gram,
        "metal_cost": metal_cost_value,
        "labor": labor,
        "finishing": finishing,
        "total_cost": total,
    }


def multi_metal_compare(
    volume_mm3: float,
    metals: Optional[list[str]] = None,
    metal_prices: Optional[dict[str, float]] = None,
    labor: float = 0.0,
    finishing: float = 0.0,
    casting_allowance_pct: float = 15.0,
) -> list[dict]:
    """
    Compare casting cost across multiple metals for the same volume.

    Useful for helping a jeweler decide on metal choice before committing
    to a casting order.

    Parameters
    ----------
    volume_mm3 : float
        Part volume in mm³.
    metals : list[str], optional
        List of metal keys to compare.  Defaults to the common jewelry
        metals: 14k_yellow, 14k_white, 18k_yellow, sterling_925,
        platinum_950, palladium_950.
    metal_prices : dict[str, float], optional
        Per-metal price overrides {metal_key: price_per_gram}.
        Metals not present in the dict use price 0.0 (weight-only output).
    labor : float
        Common labor cost applied to all metals.
    finishing : float
        Common finishing cost applied to all metals.
    casting_allowance_pct : float
        Common casting allowance applied to all metals.

    Returns
    -------
    List of casting_cost dicts sorted by total_cost ascending.
    """
    DEFAULT_METALS = [
        "14k_yellow", "14k_white", "14k_rose",
        "18k_yellow", "18k_white",
        "sterling_925", "platinum_950", "palladium_950",
    ]
    if metals is None:
        metals = DEFAULT_METALS
    if metal_prices is None:
        metal_prices = {}

    results = []
    for m in metals:
        price = metal_prices.get(m, 0.0)
        row = casting_cost(
            volume_mm3,
            metal=m,
            metal_price_per_gram=price,
            labor=labor,
            finishing=finishing,
            casting_allowance_pct=casting_allowance_pct,
        )
        row["label"] = METAL_LABELS.get(m, m)
        results.append(row)

    results.sort(key=lambda r: r["total_cost"])
    return results
