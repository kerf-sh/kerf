"""
Planting module — xeriscape-friendly plant catalogue, growth dimensions,
and hardiness zone filtering.

References
----------
* USDA Plant Hardiness Zone Map (2023 edition)
* Water Use Classification of Landscape Species (WUCOLS IV, 2014)
* RHS Award of Garden Merit plant database

Public API
----------
get_plant_catalogue() -> list[dict]
    Return the full xeriscape plant catalogue.

filter_by_zone(catalogue, zone) -> list[dict]
    Return plants that can survive in the given USDA hardiness zone.

filter_by_water_use(catalogue, max_water_use) -> list[dict]
    Return plants with water use at or below the given level.
    Levels: "very-low", "low", "moderate", "high".

plant_spacing_grid(plant, area_width, area_depth, offset_rows=True) -> dict
    Generate a planting grid for a rectangular bed using the plant's
    recommended spacing.  Returns grid of (x, y) positions.
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Water-use ranking (lower = drier)
# ---------------------------------------------------------------------------

_WATER_RANK: dict[str, int] = {
    "very-low": 0,
    "low": 1,
    "moderate": 2,
    "high": 3,
}


# ---------------------------------------------------------------------------
# Plant catalogue
# ---------------------------------------------------------------------------

# Each entry:
#   name            : common name
#   scientific_name : binomial
#   type            : "tree" | "shrub" | "perennial" | "grass" | "groundcover" | "succulent"
#   zone_min        : minimum USDA hardiness zone (integer)
#   zone_max        : maximum USDA hardiness zone (integer)
#   water_use       : "very-low" | "low" | "moderate" | "high"   (WUCOLS)
#   mature_height_m : typical mature height [m]
#   spread_m        : typical canopy spread [m]
#   spacing_m       : recommended on-centre planting spacing [m]
#   sun             : "full-sun" | "part-shade" | "full-shade"
#   notes           : short description / design use

_CATALOGUE: list[dict] = [
    {
        "name": "Blue Oat Grass",
        "scientific_name": "Helictotrichon sempervirens",
        "type": "grass",
        "zone_min": 4, "zone_max": 9,
        "water_use": "low",
        "mature_height_m": 0.6, "spread_m": 0.6, "spacing_m": 0.5,
        "sun": "full-sun",
        "notes": "Striking silver-blue foliage; excellent erosion control.",
    },
    {
        "name": "Lavender",
        "scientific_name": "Lavandula angustifolia",
        "type": "shrub",
        "zone_min": 5, "zone_max": 10,
        "water_use": "low",
        "mature_height_m": 0.6, "spread_m": 0.9, "spacing_m": 0.75,
        "sun": "full-sun",
        "notes": "Fragrant, drought-tolerant Mediterranean subshrub.",
    },
    {
        "name": "Agave",
        "scientific_name": "Agave americana",
        "type": "succulent",
        "zone_min": 8, "zone_max": 12,
        "water_use": "very-low",
        "mature_height_m": 1.8, "spread_m": 3.0, "spacing_m": 2.0,
        "sun": "full-sun",
        "notes": "Bold architectural accent; monocarpic after decades.",
    },
    {
        "name": "Texas Ranger",
        "scientific_name": "Leucophyllum frutescens",
        "type": "shrub",
        "zone_min": 7, "zone_max": 11,
        "water_use": "very-low",
        "mature_height_m": 1.8, "spread_m": 1.5, "spacing_m": 1.2,
        "sun": "full-sun",
        "notes": "Silvery foliage; purple blooms after summer rain.",
    },
    {
        "name": "Russian Sage",
        "scientific_name": "Perovskia atriplicifolia",
        "type": "perennial",
        "zone_min": 4, "zone_max": 9,
        "water_use": "low",
        "mature_height_m": 1.2, "spread_m": 0.9, "spacing_m": 0.75,
        "sun": "full-sun",
        "notes": "Airy blue-violet flowers; deer-resistant.",
    },
    {
        "name": "Desert Willow",
        "scientific_name": "Chilopsis linearis",
        "type": "tree",
        "zone_min": 7, "zone_max": 11,
        "water_use": "low",
        "mature_height_m": 6.0, "spread_m": 4.5, "spacing_m": 3.5,
        "sun": "full-sun",
        "notes": "Native southwest USA; orchid-like flowers in summer.",
    },
    {
        "name": "Creosote Bush",
        "scientific_name": "Larrea tridentata",
        "type": "shrub",
        "zone_min": 7, "zone_max": 11,
        "water_use": "very-low",
        "mature_height_m": 2.0, "spread_m": 2.0, "spacing_m": 1.8,
        "sun": "full-sun",
        "notes": "Iconic Chihuahuan desert species; rain-scented resin.",
    },
    {
        "name": "Buffalo Grass",
        "scientific_name": "Bouteloua dactyloides",
        "type": "grass",
        "zone_min": 3, "zone_max": 9,
        "water_use": "low",
        "mature_height_m": 0.25, "spread_m": 0.3, "spacing_m": 0.3,
        "sun": "full-sun",
        "notes": "Native prairie turf; very low water once established.",
    },
    {
        "name": "Catmint",
        "scientific_name": "Nepeta x faassenii",
        "type": "perennial",
        "zone_min": 3, "zone_max": 8,
        "water_use": "low",
        "mature_height_m": 0.5, "spread_m": 0.6, "spacing_m": 0.5,
        "sun": "full-sun",
        "notes": "Long-blooming blue-purple groundcover; attracts pollinators.",
    },
    {
        "name": "Mexican Feather Grass",
        "scientific_name": "Nassella tenuissima",
        "type": "grass",
        "zone_min": 6, "zone_max": 11,
        "water_use": "low",
        "mature_height_m": 0.6, "spread_m": 0.5, "spacing_m": 0.45,
        "sun": "full-sun",
        "notes": "Feathery texture; self-seeds freely.",
    },
    {
        "name": "Rosemary",
        "scientific_name": "Salvia rosmarinus",
        "type": "shrub",
        "zone_min": 7, "zone_max": 11,
        "water_use": "low",
        "mature_height_m": 1.2, "spread_m": 1.2, "spacing_m": 0.9,
        "sun": "full-sun",
        "notes": "Culinary herb / landscape shrub; excellent in rock gardens.",
    },
    {
        "name": "Prickly Pear Cactus",
        "scientific_name": "Opuntia ficus-indica",
        "type": "succulent",
        "zone_min": 8, "zone_max": 12,
        "water_use": "very-low",
        "mature_height_m": 1.8, "spread_m": 2.0, "spacing_m": 1.5,
        "sun": "full-sun",
        "notes": "Edible fruit; bold texture; wind and erosion resistant.",
    },
    {
        "name": "Blue Wild Rye",
        "scientific_name": "Elymus glaucus",
        "type": "grass",
        "zone_min": 4, "zone_max": 9,
        "water_use": "low",
        "mature_height_m": 0.9, "spread_m": 0.6, "spacing_m": 0.5,
        "sun": "part-shade",
        "notes": "Native West Coast species; thrives under oaks.",
    },
    {
        "name": "Desert Marigold",
        "scientific_name": "Baileya multiradiata",
        "type": "perennial",
        "zone_min": 7, "zone_max": 11,
        "water_use": "very-low",
        "mature_height_m": 0.5, "spread_m": 0.5, "spacing_m": 0.4,
        "sun": "full-sun",
        "notes": "Bright yellow blooms; long season; Sonoran desert native.",
    },
    {
        "name": "Fernbush",
        "scientific_name": "Chamaebatiaria millefolium",
        "type": "shrub",
        "zone_min": 4, "zone_max": 8,
        "water_use": "low",
        "mature_height_m": 1.8, "spread_m": 1.5, "spacing_m": 1.2,
        "sun": "full-sun",
        "notes": "Fern-like aromatic foliage; white flowers in summer.",
    },
    {
        "name": "Sedum 'Autumn Joy'",
        "scientific_name": "Hylotelephium 'Herbstfreude'",
        "type": "perennial",
        "zone_min": 3, "zone_max": 9,
        "water_use": "low",
        "mature_height_m": 0.6, "spread_m": 0.5, "spacing_m": 0.45,
        "sun": "full-sun",
        "notes": "Four-season interest; autumn pink-to-rust flowerheads.",
    },
    {
        "name": "Honey Mesquite",
        "scientific_name": "Prosopis glandulosa",
        "type": "tree",
        "zone_min": 7, "zone_max": 11,
        "water_use": "very-low",
        "mature_height_m": 9.0, "spread_m": 12.0, "spacing_m": 6.0,
        "sun": "full-sun",
        "notes": "Deep taproot; nitrogen-fixing; excellent shade and pods.",
    },
    {
        "name": "Deerweed",
        "scientific_name": "Acmispon glaber",
        "type": "perennial",
        "zone_min": 8, "zone_max": 10,
        "water_use": "very-low",
        "mature_height_m": 0.9, "spread_m": 1.2, "spacing_m": 0.9,
        "sun": "full-sun",
        "notes": "California native; yellow pea flowers; good wildlife plant.",
    },
    {
        "name": "Apache Plume",
        "scientific_name": "Fallugia paradoxa",
        "type": "shrub",
        "zone_min": 4, "zone_max": 9,
        "water_use": "low",
        "mature_height_m": 1.8, "spread_m": 1.5, "spacing_m": 1.2,
        "sun": "full-sun",
        "notes": "White flowers followed by feathery pink seed heads.",
    },
    {
        "name": "Wooly Thyme",
        "scientific_name": "Thymus pseudolanuginosus",
        "type": "groundcover",
        "zone_min": 4, "zone_max": 8,
        "water_use": "low",
        "mature_height_m": 0.05, "spread_m": 0.3, "spacing_m": 0.25,
        "sun": "full-sun",
        "notes": "Low mat; fragrant; tolerates light foot traffic.",
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_plant_catalogue() -> list[dict]:
    """Return the full xeriscape plant catalogue (shallow copies)."""
    return [dict(p) for p in _CATALOGUE]


def filter_by_zone(catalogue: list[dict], zone: int) -> list[dict]:
    """
    Return plants that are hardy in the given USDA hardiness zone.

    Parameters
    ----------
    catalogue : plant list (from get_plant_catalogue or a subset).
    zone      : integer USDA zone (1–13).

    Returns
    -------
    Filtered list.  Returns ``[]`` for an out-of-range zone rather than raising.
    """
    return [
        dict(p) for p in catalogue
        if p["zone_min"] <= zone <= p["zone_max"]
    ]


def filter_by_water_use(catalogue: list[dict], max_water_use: str) -> list[dict]:
    """
    Return plants with water use at or below ``max_water_use``.

    Parameters
    ----------
    catalogue     : plant list.
    max_water_use : one of "very-low", "low", "moderate", "high".

    Returns
    -------
    Filtered list.  Returns ``{"ok": False, ...}`` for an unrecognised level.
    """
    if max_water_use not in _WATER_RANK:
        return []   # caller can check length or use the dict form below
    threshold = _WATER_RANK[max_water_use]
    return [
        dict(p) for p in catalogue
        if _WATER_RANK.get(p.get("water_use", "high"), 3) <= threshold
    ]


def plant_spacing_grid(
    plant: dict,
    area_width: float,
    area_depth: float,
    offset_rows: bool = True,
) -> dict[str, Any]:
    """
    Generate a planting grid for a rectangular bed.

    Parameters
    ----------
    plant       : plant dict with a "spacing_m" key.
    area_width  : bed width [m].
    area_depth  : bed depth (perpendicular to width) [m].
    offset_rows : if True, alternate rows are offset by half the spacing
                  (triangular grid), improving coverage efficiency.

    Returns
    -------
    {"ok", "positions": [(x, y), ...], "count": int,
     "spacing_m": float, "row_spacing_m": float}
    """
    spacing = plant.get("spacing_m")
    if spacing is None or spacing <= 0:
        return {"ok": False, "reason": "plant must have a positive spacing_m"}
    if area_width <= 0 or area_depth <= 0:
        return {"ok": False, "reason": "area_width and area_depth must be positive"}

    row_spacing = spacing * (math.sqrt(3) / 2) if offset_rows else spacing

    positions: list[tuple[float, float]] = []
    row = 0
    y = spacing / 2
    while y < area_depth:
        x_start = spacing / 2
        if offset_rows and row % 2 == 1:
            x_start += spacing / 2
        x = x_start
        while x < area_width:
            positions.append((round(x, 6), round(y, 6)))
            x += spacing
        y += row_spacing
        row += 1

    return {
        "ok": True,
        "positions": positions,
        "count": len(positions),
        "spacing_m": spacing,
        "row_spacing_m": row_spacing,
    }


def plant_water_budget(
    plants: list[tuple[dict, int]],
    area_m2: float,
    eto_mm_per_year: float,
) -> dict[str, Any]:
    """
    Estimate annual irrigation water budget for a mixed planting.

    Uses ET adjustment factors per WUCOLS water-use class:
        very-low → kl = 0.1
        low      → kl = 0.3
        moderate → kl = 0.6
        high     → kl = 1.0

    Water volume = Σ (kl_i · ETo · coverage_area_i)

    Parameters
    ----------
    plants         : list of (plant_dict, count) tuples.
    area_m2        : total planted area [m²].
    eto_mm_per_year: reference evapotranspiration [mm/year].

    Returns
    -------
    {"ok", "water_L_per_year", "water_m3_per_year",
     "breakdown": [{name, count, kl, area_m2, water_L}]}
    """
    _kl_map = {"very-low": 0.1, "low": 0.3, "moderate": 0.6, "high": 1.0}

    if not plants:
        return {"ok": False, "reason": "plants list must not be empty"}
    if area_m2 <= 0 or eto_mm_per_year < 0:
        return {"ok": False, "reason": "area_m2 must be positive and eto_mm_per_year non-negative"}

    # Allocate area proportionally to each plant's coverage (spread²)
    total_coverage = sum(
        p.get("spread_m", 1.0) ** 2 * count for p, count in plants
    )

    breakdown = []
    total_water_L = 0.0

    for plant, count in plants:
        kl = _kl_map.get(plant.get("water_use", "moderate"), 0.6)
        if total_coverage > 0:
            coverage_frac = (plant.get("spread_m", 1.0) ** 2 * count) / total_coverage
        else:
            coverage_frac = 1.0 / len(plants)
        plant_area = area_m2 * coverage_frac
        # Volume = kl * ETo [mm] * area [m²] → litres (1 mm × 1 m² = 1 L)
        water_L = kl * eto_mm_per_year * plant_area
        total_water_L += water_L
        breakdown.append({
            "name": plant.get("name", "unknown"),
            "count": count,
            "kl": kl,
            "area_m2": round(plant_area, 2),
            "water_L": round(water_L, 1),
        })

    return {
        "ok": True,
        "water_L_per_year": round(total_water_L, 1),
        "water_m3_per_year": round(total_water_L / 1000.0, 3),
        "breakdown": breakdown,
    }
