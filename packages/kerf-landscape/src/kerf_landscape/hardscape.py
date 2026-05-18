"""
Hardscape module — paver pattern generators and retaining wall layout.

Public API
----------
paver_pattern(pattern, area_width, area_depth, unit_w, unit_h, joint) -> dict
    Generate paver layout positions for running bond, stack bond, herringbone,
    or basketweave patterns.

retaining_wall_layout(height, length, wall_type, soil_phi_deg,
                      soil_gamma, surcharge) -> dict
    Lateral earth pressure and wall sizing per Rankine theory.

paver_material_estimate(pattern_result, paver_thickness_m, waste_pct) -> dict
    Material takeoff: paver count, area, volume of material.
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Paver patterns
# ---------------------------------------------------------------------------

_VALID_PATTERNS = ("running-bond", "stack-bond", "herringbone-45", "basketweave")


def paver_pattern(
    pattern: str,
    area_width: float,
    area_depth: float,
    unit_w: float,
    unit_h: float,
    joint: float = 0.003,
) -> dict[str, Any]:
    """
    Generate paver unit positions for a rectangular paved area.

    Parameters
    ----------
    pattern    : layout pattern — one of "running-bond", "stack-bond",
                 "herringbone-45", "basketweave".
    area_width : total paved area width [m].
    area_depth : total paved area depth [m].
    unit_w     : paver width [m].
    unit_h     : paver height (length) [m].
    joint      : joint width between pavers [m] (default 3 mm).

    Returns
    -------
    {"ok", "pattern", "positions": [{"x", "y", "angle_deg", "w", "h"}],
     "count": int, "coverage_pct": float}
        positions — lower-left corner (x, y), rotation angle, placed dimensions.
        coverage_pct — fraction of area covered by pavers (not joints).
    """
    if pattern not in _VALID_PATTERNS:
        return {
            "ok": False,
            "reason": f"pattern must be one of {_VALID_PATTERNS}; got '{pattern}'",
        }
    if unit_w <= 0 or unit_h <= 0:
        return {"ok": False, "reason": "unit_w and unit_h must be positive"}
    if area_width <= 0 or area_depth <= 0:
        return {"ok": False, "reason": "area_width and area_depth must be positive"}
    if joint < 0:
        return {"ok": False, "reason": "joint must be non-negative"}

    positions: list[dict] = []

    if pattern == "stack-bond":
        # Grid: all units aligned
        col_pitch = unit_w + joint
        row_pitch = unit_h + joint
        y = 0.0
        while y < area_depth:
            x = 0.0
            while x < area_width:
                positions.append({"x": round(x, 6), "y": round(y, 6),
                                  "angle_deg": 0, "w": unit_w, "h": unit_h})
                x += col_pitch
            y += row_pitch

    elif pattern == "running-bond":
        # Alternate rows offset by half pitch
        col_pitch = unit_w + joint
        row_pitch = unit_h + joint
        row = 0
        y = 0.0
        while y < area_depth:
            x_start = (col_pitch / 2) if (row % 2 == 1) else 0.0
            x = x_start
            while x < area_width:
                positions.append({"x": round(x, 6), "y": round(y, 6),
                                  "angle_deg": 0, "w": unit_w, "h": unit_h})
                x += col_pitch
            y += row_pitch
            row += 1

    elif pattern == "basketweave":
        # 2×1 basketweave: pairs alternate orientation
        # Assumes unit_h == 2 * unit_w (traditional basketweave proportions)
        # Works with any ratio — pairs placed in 2-wide tiles
        tile_w = unit_w * 2 + joint
        tile_h = unit_h + joint
        col_pitch = tile_w + joint
        row_pitch = tile_h * 2 + joint
        y = 0.0
        while y < area_depth:
            x = 0.0
            while x < area_width:
                # Pair 1: horizontal pair at (x, y)
                positions.append({"x": round(x, 6), "y": round(y, 6),
                                  "angle_deg": 0, "w": unit_w, "h": unit_h})
                positions.append({"x": round(x + unit_w + joint, 6), "y": round(y, 6),
                                  "angle_deg": 0, "w": unit_w, "h": unit_h})
                # Pair 2: vertical pair at (x, y + tile_h)
                y2 = y + tile_h
                positions.append({"x": round(x, 6), "y": round(y2, 6),
                                  "angle_deg": 90, "w": unit_h, "h": unit_w})
                positions.append({"x": round(x + unit_h + joint, 6), "y": round(y2, 6),
                                  "angle_deg": 90, "w": unit_h, "h": unit_w})
                x += col_pitch
            y += row_pitch

    elif pattern == "herringbone-45":
        # 45-degree herringbone.  Units placed on a 45° rotated grid.
        # The placed footprint of a rotated paver in plan:
        #   bbox_w = bbox_h = (unit_w + unit_h) / sqrt(2)
        half_diag = (unit_w + unit_h) / (2.0 * math.sqrt(2.0))
        pitch = half_diag + joint / math.sqrt(2.0)

        row = 0
        y = 0.0
        while y < area_depth + pitch:
            x_start = (pitch / 2) if (row % 2 == 1) else 0.0
            x = x_start
            while x < area_width + pitch:
                # Place two units per "slot" — one at +45°, one at −45°
                positions.append({"x": round(x, 6), "y": round(y, 6),
                                  "angle_deg": 45, "w": unit_w, "h": unit_h})
                positions.append({"x": round(x + pitch, 6), "y": round(y, 6),
                                  "angle_deg": -45, "w": unit_w, "h": unit_h})
                x += pitch * 2
            y += pitch
            row += 1

    # Clip to area (keep only units whose centre lies inside the area)
    clipped = []
    for p in positions:
        cx = p["x"] + p["w"] / 2
        cy = p["y"] + p["h"] / 2
        if 0 <= cx <= area_width and 0 <= cy <= area_depth:
            clipped.append(p)

    paver_area = unit_w * unit_h * len(clipped)
    total_area = area_width * area_depth
    coverage_pct = (paver_area / total_area * 100.0) if total_area > 0 else 0.0

    return {
        "ok": True,
        "pattern": pattern,
        "positions": clipped,
        "count": len(clipped),
        "coverage_pct": round(coverage_pct, 2),
        "area_m2": round(total_area, 4),
    }


def paver_material_estimate(
    pattern_result: dict,
    paver_thickness_m: float = 0.06,
    waste_pct: float = 5.0,
) -> dict[str, Any]:
    """
    Material takeoff from a paver pattern result.

    Parameters
    ----------
    pattern_result   : dict returned by paver_pattern().
    paver_thickness_m: paver depth / thickness [m] (default 60 mm).
    waste_pct        : percentage waste allowance (default 5 %).

    Returns
    -------
    {"ok", "paver_count_with_waste", "paver_volume_m3",
     "base_area_m2", "coverage_pct"}
    """
    if not pattern_result.get("ok"):
        return {"ok": False, "reason": "pattern_result is not valid"}
    if paver_thickness_m <= 0:
        return {"ok": False, "reason": "paver_thickness_m must be positive"}
    if waste_pct < 0:
        return {"ok": False, "reason": "waste_pct must be non-negative"}

    count = pattern_result["count"]
    count_with_waste = math.ceil(count * (1 + waste_pct / 100.0))

    unit_w = pattern_result["positions"][0]["w"] if pattern_result["positions"] else 0
    unit_h = pattern_result["positions"][0]["h"] if pattern_result["positions"] else 0
    single_volume = unit_w * unit_h * paver_thickness_m
    total_volume = single_volume * count_with_waste

    return {
        "ok": True,
        "paver_count": count,
        "paver_count_with_waste": count_with_waste,
        "paver_volume_m3": round(total_volume, 4),
        "base_area_m2": pattern_result.get("area_m2", 0.0),
        "coverage_pct": pattern_result.get("coverage_pct", 0.0),
    }


# ---------------------------------------------------------------------------
# Retaining wall layout
# ---------------------------------------------------------------------------

def retaining_wall_layout(
    height: float,
    length: float,
    wall_type: str = "gravity",
    soil_phi_deg: float = 30.0,
    soil_gamma: float = 18000.0,
    surcharge: float = 0.0,
) -> dict[str, Any]:
    """
    Lateral earth pressure and preliminary retaining wall sizing.

    Uses Rankine active earth pressure theory (Rankine, 1857):
        Ka = tan²(45 − φ/2)
        σ_a(z) = Ka · γ · z + Ka · q
        P_total = ½ Ka γ H² + Ka q H

    Parameters
    ----------
    height     : retained height [m].
    length     : wall length [m].
    wall_type  : "gravity" | "cantilevered" | "segmental".
    soil_phi_deg: internal friction angle [degrees] (default 30°).
    soil_gamma : soil unit weight [N/m³] (default 18,000 N/m³ ≈ 1835 kg/m³).
    surcharge  : uniform surcharge pressure at surface [Pa] (default 0).

    Returns
    -------
    {"ok", "Ka", "P_active_N_per_m", "P_total_kN",
     "resultant_height_m", "min_base_width_m",
     "moments_about_toe": {"overturning_kNm", "stabilising_kNm", "FoS_overturning"},
     "wall_type"}
    """
    if height <= 0 or length <= 0:
        return {"ok": False, "reason": "height and length must be positive"}
    if not (0 < soil_phi_deg < 90):
        return {"ok": False, "reason": "soil_phi_deg must be between 0 and 90"}
    if soil_gamma <= 0:
        return {"ok": False, "reason": "soil_gamma must be positive"}
    if surcharge < 0:
        return {"ok": False, "reason": "surcharge must be non-negative"}
    if wall_type not in ("gravity", "cantilevered", "segmental"):
        return {
            "ok": False,
            "reason": "wall_type must be 'gravity', 'cantilevered', or 'segmental'",
        }

    phi = math.radians(soil_phi_deg)
    Ka = math.tan(math.pi / 4 - phi / 2) ** 2

    # Active pressure at base: Ka * gamma * H + Ka * q
    # Total horizontal force per unit length (N/m)
    P_triangular = 0.5 * Ka * soil_gamma * height ** 2
    P_rectangular = Ka * surcharge * height
    P_active_N_per_m = P_triangular + P_rectangular

    # Resultant height from base
    # Triangular component acts at H/3; rectangular at H/2
    if P_active_N_per_m > 0:
        h_result = (P_triangular * height / 3 + P_rectangular * height / 2) / P_active_N_per_m
    else:
        h_result = height / 3

    P_total_kN = P_active_N_per_m * length / 1000.0

    # Preliminary base width (rule of thumb per Das & Sivakugan, 2019):
    #   gravity: B ≈ 0.5–0.7 × H
    #   cantilevered: B ≈ 0.4–0.6 × H
    #   segmental: B ≈ 0.6 × H
    _base_ratio = {
        "gravity": 0.6,
        "cantilevered": 0.5,
        "segmental": 0.6,
    }
    min_base_width = _base_ratio[wall_type] * height

    # Overturning moment about toe [kNm per m of wall]
    overturning_kNm_per_m = P_active_N_per_m * h_result / 1000.0

    # Stabilising moment: assume concrete/masonry gravity wall
    # density ≈ 23,500 N/m³ (concrete), B × H section
    if wall_type == "gravity":
        wall_density = 23500.0
        wall_weight_per_m = wall_density * min_base_width * height
        stab_kNm_per_m = wall_weight_per_m * (min_base_width / 2) / 1000.0
    else:
        # Conservative estimate for cantilevered / segmental
        wall_density = 23500.0
        stem_t = 0.1 * height
        base_t = 0.1 * height
        stem_weight = wall_density * stem_t * (height - base_t)
        base_weight = wall_density * base_t * min_base_width
        stab_kNm_per_m = (stem_weight * (stem_t / 2) + base_weight * (min_base_width / 2)) / 1000.0

    fos_overturning = stab_kNm_per_m / overturning_kNm_per_m if overturning_kNm_per_m > 0 else float("inf")

    return {
        "ok": True,
        "Ka": round(Ka, 6),
        "P_active_N_per_m": round(P_active_N_per_m, 2),
        "P_total_kN": round(P_total_kN, 3),
        "resultant_height_m": round(h_result, 4),
        "min_base_width_m": round(min_base_width, 3),
        "moments_about_toe": {
            "overturning_kNm_per_m": round(overturning_kNm_per_m, 3),
            "stabilising_kNm_per_m": round(stab_kNm_per_m, 3),
            "FoS_overturning": round(fos_overturning, 3),
        },
        "wall_type": wall_type,
    }
