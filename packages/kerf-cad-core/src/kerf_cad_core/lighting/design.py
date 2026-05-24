"""
kerf_cad_core.lighting.design — pure-Python illumination engineering calculations.

Covers:

  Lumen (zonal-cavity) method
    room_cavity_ratio(length, width, height_cavity)
    coefficient_of_utilization(rcr, rho_ceiling, rho_walls, cu_table)
    light_loss_factor(lld, ldd, ballast_factor, temperature_factor)
    luminaires_for_target_lux(area, target_lux, lumens_per_luminaire,
                               fixtures_per_luminaire, cu, llf)
    lux_from_luminaires(n_luminaires, lumens_per_luminaire,
                         fixtures_per_luminaire, cu, llf, area)
    spacing_to_mounting_height_ratio(spacing, mounting_height)
    uniformity_check(min_lux, avg_lux)

  Point method (inverse-square + cosine)
    horizontal_illuminance(intensity_cd, distance_m, angle_deg)
    vertical_illuminance(intensity_cd, distance_m, angle_deg)
    multi_luminaire_illuminance(luminaires, point, plane)

  Luminance, exitance, contrast
    luminance_from_illuminance(illuminance_lux, reflectance)
    exitance(illuminance_lux, reflectance)
    contrast_ratio(luminance_task, luminance_background)

  Unified Glare Rating (CIE simplified)
    ugr(background_luminance, luminaire_luminances_cd_m2,
        solid_angles_sr, guth_position_indices)

  Roadway lighting (luminance method)
    road_luminance(intensity_cd, distance_m, angle_deg, r_table_factor)
    pole_spacing(mounting_height, spacing_to_height_ratio)
    roadway_utilization(luminaire_lumens, utilization_factor, road_width,
                         spacing, mounting_height)

  Emergency lighting
    emergency_spacing(mounting_height, min_lux_target, intensity_cd)
    emergency_lux_at_floor(intensity_cd, distance_m)

  Lamp / luminaire energy
    lamp_lumens_per_watt(lamp_type)
    lamp_energy(wattage_W, hours)
    lpd_check(total_watts, area_m2, building_type)

All functions return a plain dict:
    success → {"ok": True, ...fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "..."}

Functions NEVER raise.

Units
-----
  lengths     — metres (m)
  areas       — square metres (m²)
  angles      — degrees
  luminous intensity — candela (cd)
  luminous flux      — lumens (lm)
  illuminance        — lux (lx = lm/m²)
  luminance          — cd/m²
  solid angle        — steradians (sr)
  power              — watts (W)
  energy             — watt-hours (Wh)
  LPD                — W/m²

References
----------
IES Lighting Handbook, 10th ed. (2011), IESNA
CIE 117-1995 — Discomfort Glare in Interior Lighting
EN 12464-1:2021 — Light and Lighting
ASHRAE 90.1-2022, §9 — Lighting
California Title 24, Part 6 (2022 Building Energy Efficiency Standards)
NFPA 101 / BS 5266 — Emergency lighting

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_RESULT = dict[str, Any]


def _ok(**kwargs: Any) -> _RESULT:
    d: _RESULT = {"ok": True}
    d.update(kwargs)
    if "warnings" not in d:
        d["warnings"] = []
    return d


_DEFAULT_CU_TABLE: dict[tuple[int, int], list[float]] = {
    # (rho_ceiling %, rho_walls %)  →  CU at RCR 0,1,2,3,4,5,6,7,8,9,10
    (80, 50): [1.19, 1.07, 0.97, 0.88, 0.80, 0.73, 0.67, 0.62, 0.57, 0.53, 0.49],
    (80, 30): [1.19, 1.02, 0.91, 0.82, 0.74, 0.67, 0.61, 0.56, 0.52, 0.48, 0.45],
    (70, 50): [1.10, 1.00, 0.91, 0.83, 0.76, 0.69, 0.63, 0.58, 0.54, 0.50, 0.47],
    (70, 30): [1.10, 0.96, 0.85, 0.76, 0.69, 0.63, 0.57, 0.52, 0.48, 0.44, 0.41],
    (50, 50): [0.96, 0.88, 0.81, 0.74, 0.68, 0.62, 0.57, 0.53, 0.49, 0.45, 0.42],
    (50, 30): [0.96, 0.84, 0.75, 0.68, 0.61, 0.55, 0.50, 0.46, 0.42, 0.39, 0.36],
    (30, 50): [0.84, 0.77, 0.71, 0.65, 0.60, 0.55, 0.51, 0.47, 0.44, 0.41, 0.38],
    (30, 30): [0.84, 0.74, 0.66, 0.59, 0.53, 0.48, 0.44, 0.40, 0.37, 0.34, 0.31],
    (10, 10): [0.65, 0.57, 0.50, 0.44, 0.39, 0.35, 0.32, 0.29, 0.26, 0.24, 0.22],
}

# LPD allowances (W/m²) by building type — ASHRAE 90.1-2022 Table 9.5.1
_LPD_ASHRAE: dict[str, float] = {
    "office":         10.8,
    "classroom":      12.0,
    "retail":         15.1,
    "warehouse":       8.1,
    "hospital":       13.5,
    "restaurant":     13.5,
    "gymnasium":      11.8,
    "hotel_lobby":    14.0,
    "parking_garage":  2.2,
    "corridor":        5.4,
    "stairway":        6.5,
    "lobby":           9.7,
    "manufacturing":  13.5,
}

# Title-24 LPD allowances (W/m²) — California 2022
_LPD_TITLE24: dict[str, float] = {
    "office":         10.3,
    "classroom":      11.3,
    "retail":         13.0,
    "warehouse":       6.9,
    "hospital":       12.9,
    "restaurant":     12.9,
    "gymnasium":      10.8,
    "hotel_lobby":    12.4,
    "parking_garage":  2.2,
    "corridor":        4.3,
    "stairway":        5.4,
    "lobby":           8.6,
    "manufacturing":  12.9,
}

# Approximate initial lumens per watt for common lamp types
_LAMP_LPW: dict[str, float] = {
    "led_standard":   100.0,
    "led_high_output": 140.0,
    "fluorescent_t8":  85.0,
    "fluorescent_t5":  90.0,
    "metal_halide":    80.0,
    "high_pressure_sodium": 100.0,
    "low_pressure_sodium":  180.0,
    "incandescent":    15.0,
    "halogen":         20.0,
    "cfl":             65.0,
    "ceramic_mh":      90.0,
    "induction":       70.0,
}


# ---------------------------------------------------------------------------
# 1. Lumen / zonal-cavity method
# ---------------------------------------------------------------------------

def room_cavity_ratio(
    length_m: float,
    width_m: float,
    height_cavity_m: float,
) -> _RESULT:
    """
    Compute the Room Cavity Ratio (RCR) per IES HB-10.

    RCR = 5 × h_c × (l + w) / (l × w)

    Parameters
    ----------
    length_m : room length (m)
    width_m  : room width (m)
    height_cavity_m : cavity height from work-plane to luminaire plane (m)

    Returns
    -------
    {"ok": True, "rcr": float}
    """
    if length_m <= 0:
        return _err("length_m must be > 0")
    if width_m <= 0:
        return _err("width_m must be > 0")
    if height_cavity_m <= 0:
        return _err("height_cavity_m must be > 0")

    area = length_m * width_m
    perimeter = length_m + width_m
    rcr = 5.0 * height_cavity_m * perimeter / area
    return _ok(rcr=round(rcr, 4))


def coefficient_of_utilization(
    rcr: float,
    rho_ceiling_pct: int = 70,
    rho_walls_pct: int = 50,
    cu_table: dict[tuple[int, int], list[float]] | None = None,
) -> _RESULT:
    """
    Interpolate the Coefficient of Utilization (CU) from a CU table.

    Parameters
    ----------
    rcr : Room Cavity Ratio (0–10).
    rho_ceiling_pct : effective ceiling cavity reflectance (%, nearest key used).
    rho_walls_pct   : wall reflectance (%, nearest key used).
    cu_table : optional CU table dict mapping (rho_c%, rho_w%) →
               list of 11 CU values at RCR 0,1,...,10.
               If None, the built-in representative table is used.

    Returns
    -------
    {"ok": True, "cu": float, "rcr_used": float}
    """
    if rcr < 0:
        return _err("rcr must be >= 0")
    if not (0 <= rho_ceiling_pct <= 100):
        return _err("rho_ceiling_pct must be 0–100")
    if not (0 <= rho_walls_pct <= 100):
        return _err("rho_walls_pct must be 0–100")

    tbl = cu_table if cu_table is not None else _DEFAULT_CU_TABLE
    if not tbl:
        return _err("cu_table is empty")

    # Find nearest key
    def _nearest_key(target_c: int, target_w: int) -> tuple[int, int]:
        return min(
            tbl.keys(),
            key=lambda k: (k[0] - target_c) ** 2 + (k[1] - target_w) ** 2,
        )

    key = _nearest_key(rho_ceiling_pct, rho_walls_pct)
    values = tbl[key]
    if len(values) < 11:
        return _err("cu_table row must have 11 values (RCR 0–10)")

    rcr_clamped = max(0.0, min(rcr, 10.0))
    lo = int(rcr_clamped)
    hi = min(lo + 1, 10)
    frac = rcr_clamped - lo

    cu = values[lo] + frac * (values[hi] - values[lo])
    return _ok(cu=round(cu, 4), rcr_used=round(rcr_clamped, 4),
               key_used=key)


def light_loss_factor(
    lld: float = 0.85,
    ldd: float = 0.90,
    ballast_factor: float = 1.0,
    temperature_factor: float = 1.0,
) -> _RESULT:
    """
    Compute the total Light Loss Factor (LLF).

    LLF = LLD × LDD × ballast_factor × temperature_factor

    Parameters
    ----------
    lld  : Lamp Lumen Depreciation (0 < lld ≤ 1, default 0.85).
    ldd  : Luminaire Dirt Depreciation (0 < ldd ≤ 1, default 0.90).
    ballast_factor : ballast factor (default 1.0).
    temperature_factor : temperature correction factor (default 1.0).

    Returns
    -------
    {"ok": True, "llf": float}
    """
    for name, val in [("lld", lld), ("ldd", ldd),
                      ("ballast_factor", ballast_factor),
                      ("temperature_factor", temperature_factor)]:
        if val <= 0:
            return _err(f"{name} must be > 0")
        if val > 2.0:
            return _err(f"{name} unusually large (> 2.0) — check inputs")

    llf = lld * ldd * ballast_factor * temperature_factor
    return _ok(llf=round(llf, 6))


def luminaires_for_target_lux(
    area_m2: float,
    target_lux: float,
    lumens_per_lamp: float,
    lamps_per_luminaire: int = 1,
    cu: float = 0.65,
    llf: float = 0.80,
) -> _RESULT:
    """
    Calculate the number of luminaires required to achieve a target illuminance.

    Lumen method:
      N = (E × A) / (Φ_lamp × n_lamps × CU × LLF)

    where N is rounded up to the nearest integer.

    Parameters
    ----------
    area_m2            : room area (m²).
    target_lux         : target maintained illuminance (lx).
    lumens_per_lamp    : initial lamp lumens (lm).
    lamps_per_luminaire: number of lamps per luminaire (default 1).
    cu                 : coefficient of utilization (default 0.65).
    llf                : light loss factor (default 0.80).

    Returns
    -------
    {"ok": True, "n_luminaires": int, "actual_lux": float, "warnings": [...]}
    """
    warnings: list[str] = []

    if area_m2 <= 0:
        return _err("area_m2 must be > 0")
    if target_lux <= 0:
        return _err("target_lux must be > 0")
    if lumens_per_lamp <= 0:
        return _err("lumens_per_lamp must be > 0")
    if lamps_per_luminaire < 1:
        return _err("lamps_per_luminaire must be >= 1")
    if cu <= 0 or cu > 1.5:
        return _err("cu must be in (0, 1.5]")
    if llf <= 0 or llf > 1.5:
        return _err("llf must be in (0, 1.5]")

    luminaire_lumens = lumens_per_lamp * lamps_per_luminaire
    n_exact = (target_lux * area_m2) / (luminaire_lumens * cu * llf)
    n = math.ceil(n_exact)

    actual_lux = (n * luminaire_lumens * cu * llf) / area_m2

    if actual_lux < target_lux * 0.99:
        warnings.append(
            f"under-lit: actual {actual_lux:.1f} lx < target {target_lux:.1f} lx"
        )

    return _ok(n_luminaires=n, n_exact=round(n_exact, 3),
               actual_lux=round(actual_lux, 2),
               luminaire_lumens=round(luminaire_lumens, 1),
               warnings=warnings)


def lux_from_luminaires(
    n_luminaires: int,
    lumens_per_lamp: float,
    lamps_per_luminaire: int = 1,
    cu: float = 0.65,
    llf: float = 0.80,
    area_m2: float = 1.0,
) -> _RESULT:
    """
    Calculate average maintained illuminance from a given number of luminaires.

    E = (N × Φ_lamp × n_lamps × CU × LLF) / A

    Returns
    -------
    {"ok": True, "avg_lux": float, "warnings": [...]}
    """
    warnings: list[str] = []

    if n_luminaires < 0:
        return _err("n_luminaires must be >= 0")
    if lumens_per_lamp <= 0:
        return _err("lumens_per_lamp must be > 0")
    if lamps_per_luminaire < 1:
        return _err("lamps_per_luminaire must be >= 1")
    if cu <= 0 or cu > 1.5:
        return _err("cu must be in (0, 1.5]")
    if llf <= 0 or llf > 1.5:
        return _err("llf must be in (0, 1.5]")
    if area_m2 <= 0:
        return _err("area_m2 must be > 0")

    luminaire_lumens = lumens_per_lamp * lamps_per_luminaire
    avg_lux = (n_luminaires * luminaire_lumens * cu * llf) / area_m2
    return _ok(avg_lux=round(avg_lux, 2), warnings=warnings)


def spacing_to_mounting_height_ratio(
    spacing_m: float,
    mounting_height_m: float,
) -> _RESULT:
    """
    Compute the spacing-to-mounting-height (S/MH) ratio.

    IES recommends S/MH ≤ the luminaire's rated maximum S/MH (typically 1.0–1.5).

    Parameters
    ----------
    spacing_m        : centre-to-centre luminaire spacing (m).
    mounting_height_m: height above work plane (m).

    Returns
    -------
    {"ok": True, "s_mh": float, "warnings": [...]}
    """
    warnings: list[str] = []

    if spacing_m <= 0:
        return _err("spacing_m must be > 0")
    if mounting_height_m <= 0:
        return _err("mounting_height_m must be > 0")

    s_mh = spacing_m / mounting_height_m
    if s_mh > 1.5:
        warnings.append(
            f"poor-uniformity: S/MH = {s_mh:.2f} exceeds recommended limit of 1.5"
        )
    return _ok(s_mh=round(s_mh, 4), warnings=warnings)


def uniformity_check(
    min_lux: float,
    avg_lux: float,
    uniformity_limit: float = 0.70,
) -> _RESULT:
    """
    Check illuminance uniformity ratio: U = E_min / E_avg.

    EN 12464-1 requires U ≥ 0.70 for task areas (default limit).

    Parameters
    ----------
    min_lux          : minimum point illuminance (lx).
    avg_lux          : average illuminance (lx).
    uniformity_limit : minimum acceptable uniformity ratio (default 0.70).

    Returns
    -------
    {"ok": True, "uniformity": float, "pass": bool, "warnings": [...]}
    """
    warnings: list[str] = []

    if min_lux < 0:
        return _err("min_lux must be >= 0")
    if avg_lux <= 0:
        return _err("avg_lux must be > 0")
    if min_lux > avg_lux:
        return _err("min_lux cannot exceed avg_lux")

    uniformity = min_lux / avg_lux
    passed = uniformity >= uniformity_limit

    if not passed:
        warnings.append(
            f"poor-uniformity: U = {uniformity:.3f} < limit {uniformity_limit:.2f}"
        )

    return _ok(uniformity=round(uniformity, 4), passed=passed,
               uniformity_limit=uniformity_limit, warnings=warnings)


# ---------------------------------------------------------------------------
# 2. Point method — inverse-square + cosine law
# ---------------------------------------------------------------------------

def horizontal_illuminance(
    intensity_cd: float,
    distance_m: float,
    angle_from_nadir_deg: float = 0.0,
) -> _RESULT:
    """
    Compute horizontal illuminance at a point from a point source.

    E_h = I × cos³(θ) / h²

    where h = distance_m × cos(θ) is the mounting height component,
    and θ is the angle from the nadir (vertical downward direction).

    Equivalent form: E_h = I × cos³(θ) / h²  [IES inverse-square law]

    Parameters
    ----------
    intensity_cd         : luminous intensity toward the point (cd).
    distance_m           : direct distance from luminaire to point (m).
    angle_from_nadir_deg : angle from nadir (θ), degrees. 0 = directly below.

    Returns
    -------
    {"ok": True, "e_horizontal_lux": float, "warnings": [...]}
    """
    warnings: list[str] = []

    if intensity_cd < 0:
        return _err("intensity_cd must be >= 0")
    if distance_m <= 0:
        return _err("distance_m must be > 0")
    if not (-90.0 < angle_from_nadir_deg < 90.0):
        return _err("angle_from_nadir_deg must be in (-90, 90)")

    theta = math.radians(angle_from_nadir_deg)
    cos_t = math.cos(theta)
    # h = d × cos(θ)  →  E_h = I cos(θ) / d²  ... IES standard form
    # IES: E_h = I × cos(θ) / d²  when d is slant distance
    e_h = intensity_cd * cos_t / (distance_m ** 2)

    return _ok(e_horizontal_lux=round(e_h, 6),
               mounting_height_m=round(distance_m * cos_t, 4),
               warnings=warnings)


def vertical_illuminance(
    intensity_cd: float,
    distance_m: float,
    angle_from_nadir_deg: float,
) -> _RESULT:
    """
    Compute vertical illuminance at a point from a point source.

    E_v = I × sin(θ) × cos(θ) / d²  (for a vertical plane facing the source)

    where θ is the angle from the nadir.

    Parameters
    ----------
    intensity_cd         : luminous intensity (cd).
    distance_m           : slant distance from luminaire to point (m).
    angle_from_nadir_deg : angle from nadir θ, degrees.

    Returns
    -------
    {"ok": True, "e_vertical_lux": float}
    """
    if intensity_cd < 0:
        return _err("intensity_cd must be >= 0")
    if distance_m <= 0:
        return _err("distance_m must be > 0")
    if not (0.0 <= angle_from_nadir_deg <= 90.0):
        return _err("angle_from_nadir_deg must be in [0, 90]")

    theta = math.radians(angle_from_nadir_deg)
    e_v = intensity_cd * math.sin(theta) * math.cos(theta) / (distance_m ** 2)
    return _ok(e_vertical_lux=round(e_v, 6))


def multi_luminaire_illuminance(
    luminaires: list[dict[str, float]],
    point: dict[str, float],
    plane: str = "horizontal",
) -> _RESULT:
    """
    Superposition of horizontal or vertical illuminance at a point from
    multiple luminaires.

    Each luminaire dict:
        {"x": float, "y": float, "z": float, "intensity_cd": float}

    Point dict:
        {"x": float, "y": float, "z": float}

    Parameters
    ----------
    luminaires : list of luminaire dicts (positions in metres, intensity in cd).
    point      : target point dict.
    plane      : "horizontal" (default) or "vertical".

    Returns
    -------
    {"ok": True, "total_lux": float, "contributions": [...], "warnings": [...]}
    """
    warnings: list[str] = []

    if not luminaires:
        return _err("luminaires list is empty")
    if plane not in ("horizontal", "vertical"):
        return _err("plane must be 'horizontal' or 'vertical'")

    px, py, pz = point.get("x", 0.0), point.get("y", 0.0), point.get("z", 0.0)
    contributions: list[dict] = []
    total = 0.0

    for i, lum in enumerate(luminaires):
        lx = lum.get("x", 0.0)
        ly = lum.get("y", 0.0)
        lz = lum.get("z", 0.0)
        I = lum.get("intensity_cd", 0.0)

        if I < 0:
            warnings.append(f"luminaire[{i}] has negative intensity; skipped")
            continue

        dx = px - lx
        dy = py - ly
        dz = pz - lz
        d = math.sqrt(dx**2 + dy**2 + dz**2)

        if d < 1e-9:
            warnings.append(f"luminaire[{i}] coincides with point; skipped")
            continue

        # vertical distance from luminaire to point (luminaire above → dz < 0)
        h = lz - pz  # height of luminaire above point
        if h < 0:
            warnings.append(
                f"luminaire[{i}] is below the point; contribution may be unphysical"
            )
            h = abs(h)

        cos_theta = h / d if d > 0 else 0.0
        theta = math.acos(max(-1.0, min(1.0, cos_theta)))

        if plane == "horizontal":
            e = I * (cos_theta ** 2) / (d ** 2) * cos_theta  # = I cos³(θ)/d²... but use h form
            # Cleaner: E_h = I * cos(θ) / d²
            e = I * cos_theta / (d ** 2)
        else:
            sin_theta = math.sqrt(max(0.0, 1.0 - cos_theta**2))
            e = I * sin_theta * cos_theta / (d ** 2)

        total += e
        contributions.append({"luminaire_index": i, "lux": round(e, 6),
                               "distance_m": round(d, 4),
                               "angle_deg": round(math.degrees(theta), 2)})

    if total < 1.0:
        warnings.append(f"total illuminance {total:.2f} lx is very low")

    return _ok(total_lux=round(total, 4), contributions=contributions,
               warnings=warnings)


# ---------------------------------------------------------------------------
# 3. Luminance, exitance, contrast
# ---------------------------------------------------------------------------

def luminance_from_illuminance(
    illuminance_lux: float,
    reflectance: float,
) -> _RESULT:
    """
    Compute luminance of a Lambertian (perfectly diffuse) surface.

    L = E × ρ / π   [cd/m²]

    Parameters
    ----------
    illuminance_lux : incident illuminance (lx).
    reflectance     : surface reflectance ρ (0–1).

    Returns
    -------
    {"ok": True, "luminance_cd_m2": float}
    """
    if illuminance_lux < 0:
        return _err("illuminance_lux must be >= 0")
    if not (0.0 <= reflectance <= 1.0):
        return _err("reflectance must be in [0, 1]")

    L = illuminance_lux * reflectance / math.pi
    return _ok(luminance_cd_m2=round(L, 6))


def exitance(
    illuminance_lux: float,
    reflectance: float,
) -> _RESULT:
    """
    Compute luminous exitance (emitted flux per unit area) of a Lambertian surface.

    M = E × ρ   [lm/m²]

    Parameters
    ----------
    illuminance_lux : incident illuminance (lx).
    reflectance     : surface reflectance ρ (0–1).

    Returns
    -------
    {"ok": True, "exitance_lm_m2": float}
    """
    if illuminance_lux < 0:
        return _err("illuminance_lux must be >= 0")
    if not (0.0 <= reflectance <= 1.0):
        return _err("reflectance must be in [0, 1]")

    M = illuminance_lux * reflectance
    return _ok(exitance_lm_m2=round(M, 6))


def contrast_ratio(
    luminance_task: float,
    luminance_background: float,
) -> _RESULT:
    """
    Compute Weber contrast ratio C = (L_task - L_bg) / L_bg.

    Positive → task brighter than background.
    Negative → task darker than background.

    Parameters
    ----------
    luminance_task       : task luminance (cd/m²).
    luminance_background : background luminance (cd/m²). Must be > 0.

    Returns
    -------
    {"ok": True, "contrast": float}
    """
    if luminance_task < 0:
        return _err("luminance_task must be >= 0")
    if luminance_background <= 0:
        return _err("luminance_background must be > 0")

    C = (luminance_task - luminance_background) / luminance_background
    return _ok(contrast=round(C, 6))


# ---------------------------------------------------------------------------
# 4. Unified Glare Rating (CIE 117 simplified)
# ---------------------------------------------------------------------------

def ugr(
    background_luminance_cd_m2: float,
    luminaire_luminances_cd_m2: list[float],
    solid_angles_sr: list[float],
    guth_position_indices: list[float],
) -> _RESULT:
    """
    Compute the Unified Glare Rating (UGR) per CIE 117-1995 simplified formula.

    UGR = 8 × log10( 0.25/Lb × Σ(Li² × Ωi / pi²) )

    where:
      Lb   = background luminance (cd/m²) = E_ind / π
      Li   = luminance of glare source i (cd/m²)
      Ωi   = solid angle of glare source i (sr)
      pi   = Guth position index for source i

    Parameters
    ----------
    background_luminance_cd_m2   : background (indirect) luminance, Lb (cd/m²).
    luminaire_luminances_cd_m2   : list of Li values.
    solid_angles_sr              : list of Ωi values (sr).
    guth_position_indices        : list of pi values (≥ 1).

    Returns
    -------
    {"ok": True, "ugr": float, "warnings": [...]}
    """
    warnings: list[str] = []

    if background_luminance_cd_m2 <= 0:
        return _err("background_luminance_cd_m2 must be > 0")
    n = len(luminaire_luminances_cd_m2)
    if n == 0:
        return _err("luminaire_luminances_cd_m2 must not be empty")
    if len(solid_angles_sr) != n:
        return _err("solid_angles_sr must have same length as luminaire_luminances_cd_m2")
    if len(guth_position_indices) != n:
        return _err("guth_position_indices must have same length as luminaire_luminances_cd_m2")

    for i, (Li, Oi, pi) in enumerate(
        zip(luminaire_luminances_cd_m2, solid_angles_sr, guth_position_indices)
    ):
        if Li < 0:
            return _err(f"luminaire_luminances_cd_m2[{i}] must be >= 0")
        if Oi <= 0:
            return _err(f"solid_angles_sr[{i}] must be > 0")
        if pi < 1.0:
            return _err(f"guth_position_indices[{i}] must be >= 1")

    Lb = background_luminance_cd_m2
    summation = sum(
        (Li ** 2) * Oi / (pi ** 2)
        for Li, Oi, pi in zip(
            luminaire_luminances_cd_m2, solid_angles_sr, guth_position_indices
        )
    )

    if summation <= 0:
        return _ok(ugr=-999.0, warnings=["all luminaires have zero luminance"])

    ugr_val = 8.0 * math.log10(0.25 / Lb * summation)

    # EN 12464-1 UGR limits: offices ≤ 19, classrooms ≤ 19, industrial ≤ 25
    if ugr_val > 28:
        warnings.append(
            f"glare-exceeds: UGR = {ugr_val:.1f} exceeds 28 (severe discomfort glare)"
        )
    elif ugr_val > 22:
        warnings.append(
            f"glare-exceeds: UGR = {ugr_val:.1f} exceeds 22 (typical office/classroom limit 19)"
        )

    return _ok(ugr=round(ugr_val, 2), warnings=warnings)


# ---------------------------------------------------------------------------
# 5. Roadway lighting
# ---------------------------------------------------------------------------

def road_luminance(
    intensity_cd: float,
    distance_m: float,
    angle_from_nadir_deg: float,
    r_table_factor: float = 0.07,
) -> _RESULT:
    """
    Estimate road surface luminance using a simplified R-table model.

    L = I × r(γ, β) / H²

    where H = distance × cos(θ) (mounting height) and r is the reduced
    luminance coefficient from CIE R-table (represented here as r_table_factor).

    Parameters
    ----------
    intensity_cd         : luminaire intensity in direction of point (cd).
    distance_m           : slant distance from luminaire to road point (m).
    angle_from_nadir_deg : angle from nadir (θ), degrees.
    r_table_factor       : reduced luminance coefficient r (default 0.07 for
                           typical asphalt R2/R3 surface, CIE 30.2).

    Returns
    -------
    {"ok": True, "luminance_cd_m2": float}
    """
    if intensity_cd < 0:
        return _err("intensity_cd must be >= 0")
    if distance_m <= 0:
        return _err("distance_m must be > 0")
    if not (0.0 <= angle_from_nadir_deg < 90.0):
        return _err("angle_from_nadir_deg must be in [0, 90)")
    if r_table_factor <= 0:
        return _err("r_table_factor must be > 0")

    theta = math.radians(angle_from_nadir_deg)
    H = distance_m * math.cos(theta)
    if H < 1e-9:
        return _err("computed mounting height is effectively zero")

    L = intensity_cd * r_table_factor / (H ** 2)
    return _ok(luminance_cd_m2=round(L, 6),
               mounting_height_m=round(H, 4))


def pole_spacing(
    mounting_height_m: float,
    spacing_to_height_ratio: float = 3.0,
) -> _RESULT:
    """
    Compute recommended pole spacing for roadway luminaires.

    Spacing = S/H_ratio × mounting_height_m

    Typical S/H ratios: 3.0 (single-sided), 4.0 (staggered), 5.0 (opposite).

    Parameters
    ----------
    mounting_height_m        : luminaire mounting height above road (m).
    spacing_to_height_ratio  : S/H ratio (default 3.0).

    Returns
    -------
    {"ok": True, "spacing_m": float}
    """
    if mounting_height_m <= 0:
        return _err("mounting_height_m must be > 0")
    if spacing_to_height_ratio <= 0:
        return _err("spacing_to_height_ratio must be > 0")

    spacing = mounting_height_m * spacing_to_height_ratio
    return _ok(spacing_m=round(spacing, 3),
               s_h_ratio=round(spacing_to_height_ratio, 3))


def roadway_utilization(
    luminaire_lumens: float,
    utilization_factor: float,
    road_width_m: float,
    spacing_m: float,
    mounting_height_m: float,
) -> _RESULT:
    """
    Compute average road luminance via the luminance (utilization) method.

    E_road = (Φ × UF) / (W × S)   [lx]
    L_road ≈ E_road × q0             [cd/m²]  (q0 ≈ 0.07 for R2 asphalt)

    Parameters
    ----------
    luminaire_lumens   : total initial lamp lumens per luminaire (lm).
    utilization_factor : fraction of lumens falling on road (0–1).
    road_width_m       : carriageway width (m).
    spacing_m          : pole spacing (m).
    mounting_height_m  : mounting height (m), used for S/H check.

    Returns
    -------
    {"ok": True, "avg_road_lux": float, "avg_road_luminance_cd_m2": float,
     "s_h_ratio": float, "warnings": [...]}
    """
    warnings: list[str] = []

    if luminaire_lumens <= 0:
        return _err("luminaire_lumens must be > 0")
    if not (0.0 < utilization_factor <= 1.0):
        return _err("utilization_factor must be in (0, 1]")
    if road_width_m <= 0:
        return _err("road_width_m must be > 0")
    if spacing_m <= 0:
        return _err("spacing_m must be > 0")
    if mounting_height_m <= 0:
        return _err("mounting_height_m must be > 0")

    e_road = (luminaire_lumens * utilization_factor) / (road_width_m * spacing_m)
    q0 = 0.07  # typical R2 asphalt reduced luminance coefficient
    l_road = e_road * q0

    s_h = spacing_m / mounting_height_m
    if s_h > 5.0:
        warnings.append(
            f"poor-uniformity: pole S/H = {s_h:.1f} exceeds 5.0 — check spacing"
        )

    return _ok(avg_road_lux=round(e_road, 3),
               avg_road_luminance_cd_m2=round(l_road, 4),
               s_h_ratio=round(s_h, 3),
               warnings=warnings)


# ---------------------------------------------------------------------------
# 6. Emergency lighting
# ---------------------------------------------------------------------------

def emergency_lux_at_floor(
    intensity_cd: float,
    distance_m: float,
) -> _RESULT:
    """
    Compute floor-level illuminance directly below an emergency luminaire.

    E = I / d²   (θ = 0, normal incidence — point source, nadir direction)

    Parameters
    ----------
    intensity_cd : luminous intensity at nadir (cd).
    distance_m   : mounting height / slant distance to floor (m).

    Returns
    -------
    {"ok": True, "e_floor_lux": float, "warnings": [...]}
    """
    warnings: list[str] = []

    if intensity_cd < 0:
        return _err("intensity_cd must be >= 0")
    if distance_m <= 0:
        return _err("distance_m must be > 0")

    e = intensity_cd / (distance_m ** 2)

    # NFPA 101 / BS 5266 minimum: 1 lx on escape route centreline
    if e < 1.0:
        warnings.append(
            f"under-lit: floor illuminance {e:.3f} lx < 1.0 lx emergency minimum (NFPA 101)"
        )

    return _ok(e_floor_lux=round(e, 4), warnings=warnings)


def emergency_spacing(
    mounting_height_m: float,
    min_lux_target: float = 1.0,
    intensity_cd: float = 100.0,
) -> _RESULT:
    """
    Compute maximum centre-to-centre spacing between emergency luminaires so
    that the midpoint illuminance (worst case) meets the minimum lux target.

    Simplified: midpoint E = I / (mounting_height² + (spacing/2)²)
    Solve for spacing given E_min.

    Parameters
    ----------
    mounting_height_m : mounting height above floor (m).
    min_lux_target    : minimum illuminance at midpoint (lx), default 1.0.
    intensity_cd      : nadir luminous intensity (cd), default 100.

    Returns
    -------
    {"ok": True, "max_spacing_m": float, "warnings": [...]}
    """
    warnings: list[str] = []

    if mounting_height_m <= 0:
        return _err("mounting_height_m must be > 0")
    if min_lux_target <= 0:
        return _err("min_lux_target must be > 0")
    if intensity_cd <= 0:
        return _err("intensity_cd must be > 0")

    # E_mid = I / (h² + (s/2)²)   →   s = 2 × sqrt(I/E_min - h²)
    ratio = intensity_cd / min_lux_target
    h2 = mounting_height_m ** 2
    if ratio <= h2:
        # Even nadir is below target
        warnings.append(
            "under-lit: luminaire cannot meet min_lux_target even directly below"
        )
        return _ok(max_spacing_m=0.0, warnings=warnings)

    s_half = math.sqrt(ratio - h2)
    max_spacing = 2.0 * s_half

    if max_spacing < 2.0:
        warnings.append(
            f"under-lit: max spacing {max_spacing:.2f} m is very short — "
            "consider higher-intensity emergency luminaires"
        )

    return _ok(max_spacing_m=round(max_spacing, 3), warnings=warnings)


# ---------------------------------------------------------------------------
# 7. Lamp / luminaire energy and LPD compliance
# ---------------------------------------------------------------------------

def lamp_lumens_per_watt(
    lamp_type: str,
) -> _RESULT:
    """
    Return the approximate initial luminous efficacy (lm/W) for a lamp type.

    Supported types: led_standard, led_high_output, fluorescent_t8,
    fluorescent_t5, metal_halide, high_pressure_sodium, low_pressure_sodium,
    incandescent, halogen, cfl, ceramic_mh, induction.

    Returns
    -------
    {"ok": True, "lamp_type": str, "lumens_per_watt": float}
    """
    if lamp_type not in _LAMP_LPW:
        return _err(
            f"unknown lamp_type '{lamp_type}'. "
            f"Valid: {', '.join(sorted(_LAMP_LPW))}"
        )
    return _ok(lamp_type=lamp_type, lumens_per_watt=_LAMP_LPW[lamp_type])


def lamp_energy(
    wattage_W: float,
    hours: float,
) -> _RESULT:
    """
    Compute lamp energy consumption.

    Energy (Wh) = W × h
    Energy (kWh) = W × h / 1000

    Parameters
    ----------
    wattage_W : lamp wattage (W). Must be > 0.
    hours     : operating hours. Must be > 0.

    Returns
    -------
    {"ok": True, "energy_Wh": float, "energy_kWh": float}
    """
    if wattage_W <= 0:
        return _err("wattage_W must be > 0")
    if hours <= 0:
        return _err("hours must be > 0")

    e_wh = wattage_W * hours
    return _ok(energy_Wh=round(e_wh, 3),
               energy_kWh=round(e_wh / 1000.0, 6))


def lpd_check(
    total_watts: float,
    area_m2: float,
    building_type: str = "office",
    standard: str = "ASHRAE",
) -> _RESULT:
    """
    Check Lighting Power Density (LPD) against ASHRAE 90.1-2022 or Title-24
    allowances.

    LPD = total_watts / area_m2   [W/m²]

    Parameters
    ----------
    total_watts   : total connected lighting power (W).
    area_m2       : floor area (m²).
    building_type : one of the keys in the LPD table (default 'office').
    standard      : 'ASHRAE' (default) or 'Title24'.

    Returns
    -------
    {"ok": True, "lpd_W_m2": float, "allowance_W_m2": float,
     "margin_W_m2": float, "compliant": bool, "warnings": [...]}
    """
    warnings: list[str] = []

    if total_watts <= 0:
        return _err("total_watts must be > 0")
    if area_m2 <= 0:
        return _err("area_m2 must be > 0")
    if standard not in ("ASHRAE", "Title24"):
        return _err("standard must be 'ASHRAE' or 'Title24'")

    tbl = _LPD_ASHRAE if standard == "ASHRAE" else _LPD_TITLE24
    if building_type not in tbl:
        return _err(
            f"building_type '{building_type}' not found for {standard}. "
            f"Valid: {', '.join(sorted(tbl))}"
        )

    lpd = total_watts / area_m2
    allowance = tbl[building_type]
    margin = allowance - lpd
    compliant = lpd <= allowance

    if not compliant:
        warnings.append(
            f"LPD-over-allowance: {lpd:.2f} W/m² exceeds {standard} {building_type} "
            f"allowance of {allowance:.2f} W/m² by {-margin:.2f} W/m²"
        )

    return _ok(lpd_W_m2=round(lpd, 3),
               allowance_W_m2=allowance,
               margin_W_m2=round(margin, 3),
               compliant=compliant,
               standard=standard,
               building_type=building_type,
               warnings=warnings)
