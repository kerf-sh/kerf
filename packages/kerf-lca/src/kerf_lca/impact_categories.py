"""
Multi-impact characterisation factors — ISO 14040/44 beyond GWP100.

Implemented categories:
  gwp100      — Global Warming Potential 100yr  (kg CO₂-eq)   [IPCC AR6]
  ap          — Acidification Potential          (kg SO₂-eq)   [CML 2002]
  ep          — Eutrophication Potential         (kg PO₄-eq)   [CML 2002]
  htp         — Human Toxicity Potential         (CTUh)         [USEtox simplified]
  water       — Water Consumption               (m³)
  pm25        — Particulate Matter formation    (kg PM2.5-eq)  [ReCiPe 2016]

Characterisation factors are material-level approximations drawn from:
  - Ecoinvent 3.9.1 system-processes (EN15804+A2 framework)
  - SimaPro reference datasets
  - Published EPDs for common construction materials
  - USEtox 2.1 characterisation factors

These are conservative mid-point factors suitable for screening-level LCA.
For comparative assertions or EPD declarations, use a licensed Ecoinvent dataset.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Characterisation factors per material
# Keys match ICE v3 material IDs in materials.py / data/ice_v3.json
# Units:
#   gwp100  kg CO₂-eq / kg material
#   ap      kg SO₂-eq / kg material
#   ep      kg PO₄-eq / kg material
#   htp     CTUh / kg material
#   water   m³ / kg material
#   pm25    kg PM2.5-eq / kg material
# ---------------------------------------------------------------------------

_CF: dict[str, dict[str, float]] = {
    "steel_general": {
        "gwp100": 1.80, "ap": 7.2e-3, "ep": 5.1e-4, "htp": 2.5e-8, "water": 0.012, "pm25": 3.8e-4,
    },
    "steel_recycled": {
        "gwp100": 0.43, "ap": 3.0e-3, "ep": 2.5e-4, "htp": 1.1e-8, "water": 0.006, "pm25": 1.8e-4,
    },
    "steel_stainless": {
        "gwp100": 5.10, "ap": 1.8e-2, "ep": 8.0e-4, "htp": 5.0e-8, "water": 0.040, "pm25": 6.5e-4,
    },
    "aluminium_primary": {
        "gwp100": 9.16, "ap": 4.0e-2, "ep": 1.5e-3, "htp": 1.2e-7, "water": 0.150, "pm25": 9.0e-4,
    },
    "aluminium_recycled": {
        "gwp100": 0.59, "ap": 3.5e-3, "ep": 1.8e-4, "htp": 8.0e-9, "water": 0.010, "pm25": 1.2e-4,
    },
    "copper": {
        "gwp100": 3.80, "ap": 2.5e-2, "ep": 8.0e-4, "htp": 1.5e-7, "water": 0.070, "pm25": 4.5e-4,
    },
    "titanium": {
        "gwp100": 35.0, "ap": 1.2e-1, "ep": 3.5e-3, "htp": 4.0e-7, "water": 0.500, "pm25": 3.5e-3,
    },
    "concrete_general": {
        "gwp100": 0.115, "ap": 4.0e-4, "ep": 3.5e-5, "htp": 2.0e-9, "water": 0.080, "pm25": 4.0e-5,
    },
    "timber_softwood": {
        "gwp100": 0.46, "ap": 1.2e-3, "ep": 8.0e-5, "htp": 5.0e-9, "water": 0.002, "pm25": 1.5e-4,
    },
    "timber_hardwood": {
        "gwp100": 0.72, "ap": 1.5e-3, "ep": 1.0e-4, "htp": 6.0e-9, "water": 0.003, "pm25": 2.0e-4,
    },
    "plywood": {
        "gwp100": 0.81, "ap": 1.8e-3, "ep": 1.2e-4, "htp": 1.0e-8, "water": 0.004, "pm25": 2.5e-4,
    },
    "glass_flat": {
        "gwp100": 1.35, "ap": 5.0e-3, "ep": 2.5e-4, "htp": 1.5e-8, "water": 0.008, "pm25": 3.0e-4,
    },
    "pvc": {
        "gwp100": 2.80, "ap": 8.0e-3, "ep": 3.5e-4, "htp": 3.0e-7, "water": 0.015, "pm25": 5.5e-4,
    },
    "abs": {
        "gwp100": 3.50, "ap": 9.0e-3, "ep": 4.0e-4, "htp": 3.5e-7, "water": 0.018, "pm25": 6.0e-4,
    },
    "nylon": {
        "gwp100": 7.90, "ap": 2.2e-2, "ep": 9.0e-4, "htp": 5.0e-7, "water": 0.040, "pm25": 8.0e-4,
    },
    "carbon_fibre": {
        "gwp100": 29.0, "ap": 6.5e-2, "ep": 2.8e-3, "htp": 3.0e-7, "water": 0.090, "pm25": 2.5e-3,
    },
    "rubber_natural": {
        "gwp100": 3.20, "ap": 6.0e-3, "ep": 4.0e-4, "htp": 1.0e-8, "water": 0.025, "pm25": 4.0e-4,
    },
    "paper_kraft": {
        "gwp100": 0.98, "ap": 4.5e-3, "ep": 3.0e-4, "htp": 1.0e-8, "water": 0.020, "pm25": 2.0e-4,
    },
}

# Default/fallback characterisation factors (unknown material)
_CF_DEFAULT: dict[str, float] = {
    "gwp100": 0.0, "ap": 0.0, "ep": 0.0, "htp": 0.0, "water": 0.0, "pm25": 0.0,
}

IMPACT_UNITS: dict[str, str] = {
    "gwp100": "kg CO₂-eq",
    "ap": "kg SO₂-eq",
    "ep": "kg PO₄-eq",
    "htp": "CTUh",
    "water": "m³",
    "pm25": "kg PM2.5-eq",
}

IMPACT_METHODS: dict[str, str] = {
    "gwp100": "IPCC AR6 GWP100",
    "ap": "CML 2002",
    "ep": "CML 2002",
    "htp": "USEtox 2.1 (simplified)",
    "water": "Ecoinvent 3.9 water scarcity proxy",
    "pm25": "ReCiPe 2016 Midpoint (H)",
}


def get_characterisation_factors(material_id: str) -> dict[str, float]:
    """
    Return all impact characterisation factors for a given material ID.

    Falls back to zeros for unknown materials.
    """
    return dict(_CF.get(material_id, _CF_DEFAULT))


def multi_impact(
    product_breakdown: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Compute multi-impact characterisation for a product breakdown.

    Args:
        product_breakdown: list of dicts with:
            material_id  (str)   — ICE v3 material key
            mass_kg      (float) — total mass for this material

    Returns:
        dict with keys per impact category → total impact value,
        plus 'units' and 'method' sub-dicts.

    Example:
        >>> multi_impact([{"material_id": "aluminium_primary", "mass_kg": 1.0},
        ...               {"material_id": "steel_general", "mass_kg": 2.0}])
    """
    totals: dict[str, float] = {cat: 0.0 for cat in IMPACT_UNITS}
    warnings: list[str] = []

    for item in product_breakdown:
        mid = item.get("material_id", "")
        mass = float(item.get("mass_kg", 0.0))
        cf = _CF.get(mid)
        if cf is None:
            if mid:
                warnings.append(
                    f"No characterisation factors for '{mid}'; skipped from multi-impact."
                )
            continue
        for cat, factor in cf.items():
            totals[cat] += factor * mass

    return {
        "impacts": {cat: round(v, 10) for cat, v in totals.items()},
        "units": IMPACT_UNITS,
        "methods": IMPACT_METHODS,
        "warnings": warnings,
    }


def list_characterised_materials() -> list[str]:
    """Return list of material IDs with multi-impact characterisation factors."""
    return list(_CF.keys())
