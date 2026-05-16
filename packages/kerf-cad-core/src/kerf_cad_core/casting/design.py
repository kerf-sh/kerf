"""
kerf_cad_core.casting.design — pure-Python metal casting design formulas.

Implements seven public functions:

  shrinkage_allowance(alloy, nominal_dim_mm)
      Pattern shrinkage and machining allowance by alloy.
      Returns scaled pattern dimension and machining stock.

  draft_angle_volume(base_area_m2, height_m, draft_deg)
      Volume added to a vertical face by draft-angle taper.
      Approximates added volume as a prismatic frustum difference.

  chvorinov_solidification(volume_m3, area_m2, B, n)
      Chvorinov's Rule: solidification time t = B · (V/A)^n.
      n defaults to 2.0 (standard form).

  riser_size(casting_volume_m3, casting_surface_area_m2,
             alloy, riser_shape, B, n)
      Modulus method: M_casting = V_casting / A_casting (effective cooling surface);
      riser feeds when M_riser >= 1.2 · M_casting.
      Returns minimum riser dimensions, riser volume, and riser-neck diameter.
      Issues warning if riser modulus is insufficient.

  gating_system(casting_mass_kg, alloy, pouring_time_s,
                sprue_height_m, system_type)
      Sprue/runner/gate choke area from Bernoulli + continuity.
      Returns gate areas, runner area, sprue area, and velocity at choke.
      System types: "pressurised" (1:0.75:0.5) and "unpressurised" (1:2:4).

  casting_yield(casting_mass_kg, total_poured_mass_kg)
      Casting yield as a percentage and quality flag.
      Warns if yield < 60%.

  pouring_guidance(alloy, section_thickness_mm)
      Fluidity and pouring temperature guidance by alloy and section thickness.
      Returns recommended pouring temperature range and fluidity notes.

All functions return plain dicts:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Warnings are issued via the standard `warnings` module
and also collected into the result dict's "warnings" list.

Units
-----
  lengths     — metres (m) unless noted as mm
  volumes     — cubic metres (m³)
  areas       — square metres (m²)
  mass        — kilograms (kg)
  time        — seconds (s)
  temperature — degrees Celsius (°C)
  angles      — degrees (°)
  stress      — Pascals (Pa)

References
----------
Groover, M.P. "Fundamentals of Modern Manufacturing", 5th ed., Ch. 11
Kalpakjian, S. & Schmid, S.R. "Manufacturing Engineering & Technology", 7th ed.
Campbell, J. "Castings", 2nd ed. — Butterworth-Heinemann
AFS Gating and Risering Manual
Chvorinov, N. — Giesserei 27 (1940) 177-186

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_positive(name: str, value: Any) -> str | None:
    """Return an error string if *value* is not a finite positive number."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


def _guard_nonneg(name: str, value: Any) -> str | None:
    """Return an error string if *value* is not a finite non-negative number."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < 0:
        return f"{name} must be >= 0, got {v}"
    return None


def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _warn(msg: str, collected: list) -> None:
    """Issue a warning and append to a collected list."""
    warnings.warn(msg, UserWarning, stacklevel=4)
    collected.append(msg)


# ---------------------------------------------------------------------------
# Alloy data tables
# ---------------------------------------------------------------------------

# Shrinkage allowances (volumetric % → linear shrinkage as a fraction of
# nominal dimension) and machining stock (mm per surface, each side).
# Sources: AFS handbook; Groover Table 11.3; Campbell Ch. 3
_ALLOY_DATA: dict[str, dict] = {
    # Ferrous
    "grey_cast_iron": {
        "linear_shrinkage": 0.010,   # 1.0 %  (sometimes 0–1 %; low due to graphite expansion)
        "machining_stock_mm": 3.0,
        "pouring_temp_C": (1300, 1400),
        "fluidity_note": "Good fluidity; thin sections feasible. Graphite expansion reduces shrinkage.",
        "density_kg_m3": 7200.0,
    },
    "white_cast_iron": {
        "linear_shrinkage": 0.021,   # 2.1 %
        "machining_stock_mm": 4.0,
        "pouring_temp_C": (1350, 1450),
        "fluidity_note": "Hard and brittle; mainly used where abrasion resistance is needed.",
        "density_kg_m3": 7700.0,
    },
    "ductile_iron": {
        "linear_shrinkage": 0.009,   # 0.9 %
        "machining_stock_mm": 3.0,
        "pouring_temp_C": (1300, 1420),
        "fluidity_note": "Good; treated with Mg. Slightly lower fluidity than grey iron.",
        "density_kg_m3": 7100.0,
    },
    "carbon_steel": {
        "linear_shrinkage": 0.020,   # 2.0 %
        "machining_stock_mm": 5.0,
        "pouring_temp_C": (1540, 1650),
        "fluidity_note": "Poor fluidity vs cast iron. Riser design critical. High shrinkage.",
        "density_kg_m3": 7850.0,
    },
    "stainless_steel": {
        "linear_shrinkage": 0.021,   # 2.1 %
        "machining_stock_mm": 5.0,
        "pouring_temp_C": (1540, 1680),
        "fluidity_note": "Similar to carbon steel. Oxidation risk; inert atmosphere preferred.",
        "density_kg_m3": 7900.0,
    },
    # Non-ferrous
    "aluminium_alloy": {
        "linear_shrinkage": 0.013,   # 1.3 %
        "machining_stock_mm": 2.5,
        "pouring_temp_C": (680, 780),
        "fluidity_note": "Good fluidity for most Al-Si alloys. Hydrogen porosity risk; degas melt.",
        "density_kg_m3": 2700.0,
    },
    "copper_alloy": {
        "linear_shrinkage": 0.016,   # 1.6 %
        "machining_stock_mm": 3.0,
        "pouring_temp_C": (1000, 1200),
        "fluidity_note": "Moderate fluidity. Dezincification risk in brasses. Gas porosity possible.",
        "density_kg_m3": 8500.0,
    },
    "bronze": {
        "linear_shrinkage": 0.015,   # 1.5 %
        "machining_stock_mm": 3.0,
        "pouring_temp_C": (1000, 1150),
        "fluidity_note": "Good fluidity for tin bronzes. Requires attention to solidification range.",
        "density_kg_m3": 8700.0,
    },
    "zinc_alloy": {
        "linear_shrinkage": 0.007,   # 0.7 %  (die cast; low shrinkage)
        "machining_stock_mm": 1.0,
        "pouring_temp_C": (380, 450),
        "fluidity_note": "Excellent fluidity for die casting. Low pouring temp; minimal oxidation.",
        "density_kg_m3": 6600.0,
    },
    "magnesium_alloy": {
        "linear_shrinkage": 0.013,   # 1.3 %
        "machining_stock_mm": 2.0,
        "pouring_temp_C": (630, 730),
        "fluidity_note": "Light alloy; fire hazard — SF6/CO2 cover gas required.",
        "density_kg_m3": 1800.0,
    },
    "nickel_alloy": {
        "linear_shrinkage": 0.022,   # 2.2 %
        "machining_stock_mm": 5.0,
        "pouring_temp_C": (1400, 1550),
        "fluidity_note": "Investment casting preferred for complex geometries. High pouring temp.",
        "density_kg_m3": 8800.0,
    },
    "titanium_alloy": {
        "linear_shrinkage": 0.015,   # 1.5 %
        "machining_stock_mm": 4.0,
        "pouring_temp_C": (1670, 1750),
        "fluidity_note": "Vacuum investment casting only. Extreme reactivity with atmosphere and molds.",
        "density_kg_m3": 4500.0,
    },
}

# Chvorinov constant B (s/m²) — typical mold-material-specific values.
# These are representative; actual B must be determined experimentally.
# Source: Groover Table 11.2 approximate ranges.
_DEFAULT_CHVORINOV_B = 600.0   # s/m²  (green sand mold, steel)
_DEFAULT_CHVORINOV_N = 2.0     # standard exponent

# Riser feeding criterion (AFS): M_riser >= RISER_MODULUS_FACTOR * M_casting
RISER_MODULUS_FACTOR = 1.2

# Gating system type → (sprue : runner : gate) area ratios.
# "pressurised" — choke at gate; fast fill, turbulence risk
# "unpressurised" — choke at sprue; smooth flow preferred for non-ferrous
_GATING_RATIOS: dict[str, tuple[float, float, float]] = {
    "pressurised":   (1.0, 0.75, 0.5),
    "unpressurised": (1.0, 2.0,  4.0),
}

# Gravitational acceleration (m/s²)
_g = 9.81


# ---------------------------------------------------------------------------
# 1. shrinkage_allowance
# ---------------------------------------------------------------------------

def shrinkage_allowance(
    alloy: str,
    nominal_dim_mm: float,
    *,
    extra_machining_mm: float = 0.0,
) -> dict:
    """
    Pattern dimension incorporating shrinkage and machining allowance.

    The foundry pattern must be made larger than the final casting dimension
    to account for:
      1. Solidification (and subsequent solid-state) shrinkage of the alloy.
      2. Machining stock required to reach finished dimensions.

    Parameters
    ----------
    alloy : str
        Alloy name from the built-in catalog.
        Supported: grey_cast_iron, white_cast_iron, ductile_iron, carbon_steel,
        stainless_steel, aluminium_alloy, copper_alloy, bronze, zinc_alloy,
        magnesium_alloy, nickel_alloy, titanium_alloy.
    nominal_dim_mm : float
        Final desired dimension of the casting (mm).  Must be > 0.
    extra_machining_mm : float
        Additional machining stock per surface beyond the alloy default (mm).
        Must be >= 0 (default 0.0).

    Returns
    -------
    dict
        ok                    : True
        alloy                 : alloy name
        nominal_dim_mm        : input final dimension (mm)
        linear_shrinkage      : fractional linear shrinkage (e.g. 0.013 for 1.3%)
        shrinkage_dim_mm      : dimension after shrinkage allowance (mm)
        machining_stock_mm    : machining stock per surface added (mm)
        pattern_dim_mm        : total pattern dimension = shrinkage_dim + machining (mm)
        warnings              : list of warning strings (empty if none)

    Formula
    -------
    shrinkage_dim = nominal_dim / (1 - linear_shrinkage)
    pattern_dim   = shrinkage_dim + machining_stock_mm + extra_machining_mm

    Notes
    -----
    The machining stock is added to each relevant surface.  For a through-hole
    or diameter, apply twice the stock (once per side).
    """
    warninglist: list[str] = []

    err = _guard_positive("nominal_dim_mm", nominal_dim_mm)
    if err:
        return _err(err)
    err = _guard_nonneg("extra_machining_mm", extra_machining_mm)
    if err:
        return _err(err)

    alloy_key = str(alloy).strip().lower().replace(" ", "_").replace("-", "_")
    if alloy_key not in _ALLOY_DATA:
        valid = sorted(_ALLOY_DATA.keys())
        return _err(f"Unknown alloy {alloy!r}. Supported: {valid}.")

    data = _ALLOY_DATA[alloy_key]
    ls = data["linear_shrinkage"]
    stock = data["machining_stock_mm"] + float(extra_machining_mm)

    d = float(nominal_dim_mm)
    # Linear shrinkage allowance: pattern must be larger so that after
    # solidification it contracts to the nominal dimension.
    shrinkage_dim = d / (1.0 - ls)
    pattern_dim = shrinkage_dim + stock

    return {
        "ok": True,
        "alloy": alloy_key,
        "nominal_dim_mm": d,
        "linear_shrinkage": ls,
        "shrinkage_dim_mm": shrinkage_dim,
        "machining_stock_mm": stock,
        "pattern_dim_mm": pattern_dim,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 2. draft_angle_volume
# ---------------------------------------------------------------------------

def draft_angle_volume(
    base_area_m2: float,
    height_m: float,
    draft_deg: float,
) -> dict:
    """
    Volume added to a vertical face by a draft angle taper.

    When a pattern is withdrawn from a sand mold, vertical faces must be
    tapered (drafted) to prevent tearing the mold wall.  This function
    computes the extra volume introduced by the draft taper, approximating
    the face as a rectangular prism-to-frustum transition.

    The draft taper expands the base perimeter.  For a face of width W and
    height H, the draft increases the width at top (or bottom, depending on
    draw direction) by 2·H·tan(θ) for an included-angle taper.  The added
    volume is approximately:

        ΔV = base_area · H · tan(θ)

    This is equivalent to the volume difference between the drafted solid and
    the vertical-wall prism, using the mean-section approximation.

    Parameters
    ----------
    base_area_m2 : float
        Cross-sectional area at the parting plane (m²).  Must be > 0.
    height_m : float
        Height of the drafted face / core (m).  Must be > 0.
    draft_deg : float
        Draft angle in degrees.  Typical range: 0.5° – 5°.  Must be > 0.

    Returns
    -------
    dict
        ok               : True
        base_area_m2     : cross-sectional area at base (m²)
        height_m         : face height (m)
        draft_deg        : draft angle (°)
        tan_draft        : tan(draft_deg)
        added_volume_m3  : extra volume due to draft (m³)
        total_volume_m3  : base_area × height + added_volume (m³)
        warnings         : list of warning strings

    Notes
    -----
    Draft angles below 1° may cause mold damage in sand casting.
    Investment casting tolerates near-zero draft.
    """
    warninglist: list[str] = []

    err = _guard_positive("base_area_m2", base_area_m2)
    if err:
        return _err(err)
    err = _guard_positive("height_m", height_m)
    if err:
        return _err(err)
    err = _guard_positive("draft_deg", draft_deg)
    if err:
        return _err(err)

    if draft_deg > 10.0:
        _warn(
            f"draft_deg={draft_deg}° is unusually large (>10°); verify design intent.",
            warninglist,
        )

    theta = math.radians(float(draft_deg))
    tan_d = math.tan(theta)
    A = float(base_area_m2)
    H = float(height_m)

    # Mean-section approximation for added volume by draft
    added_vol = A * H * tan_d
    base_vol = A * H
    total_vol = base_vol + added_vol

    return {
        "ok": True,
        "base_area_m2": A,
        "height_m": H,
        "draft_deg": float(draft_deg),
        "tan_draft": tan_d,
        "added_volume_m3": added_vol,
        "total_volume_m3": total_vol,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 3. chvorinov_solidification
# ---------------------------------------------------------------------------

def chvorinov_solidification(
    volume_m3: float,
    area_m2: float,
    *,
    B: float = _DEFAULT_CHVORINOV_B,
    n: float = _DEFAULT_CHVORINOV_N,
) -> dict:
    """
    Chvorinov's Rule: solidification time estimate.

    Chvorinov (1940) showed empirically that the total solidification time
    is related to the casting's volume-to-surface-area ratio (the "casting
    modulus"):

        t = B · (V / A)^n

    where:
      t  — total solidification time (s)
      B  — mold constant (s/m²) — depends on mold material, alloy, temperature
      V  — casting volume (m³)
      A  — casting surface area (m²)
      n  — exponent (typically 2.0; range 1.5–2.0)

    Parameters
    ----------
    volume_m3 : float
        Casting volume (m³).  Must be > 0.
    area_m2 : float
        Casting surface area exposed to mold (m²).  Must be > 0.
    B : float
        Chvorinov mold constant (s/m²).  Default 600 s/m² (green sand / steel).
        Must be > 0.
    n : float
        Exponent in Chvorinov's rule.  Default 2.0.  Typical range [1.5, 2.0].
        Must be > 0.

    Returns
    -------
    dict
        ok                : True
        volume_m3         : casting volume (m³)
        area_m2           : casting surface area (m²)
        modulus_m         : V/A — casting modulus (m)
        B                 : mold constant used (s/m²)
        n                 : exponent used
        solidification_s  : estimated total solidification time (s)
        warnings          : list of warning strings

    Notes
    -----
    B must be calibrated experimentally for a specific alloy-mold combination.
    The default 600 s/m² is representative for green-sand steel castings;
    permanent-mold (B ≈ 200 s/m²) and investment-cast (B ≈ 1 000–2 000 s/m²)
    differ significantly.
    """
    warninglist: list[str] = []

    err = _guard_positive("volume_m3", volume_m3)
    if err:
        return _err(err)
    err = _guard_positive("area_m2", area_m2)
    if err:
        return _err(err)
    err = _guard_positive("B", B)
    if err:
        return _err(err)
    err = _guard_positive("n", n)
    if err:
        return _err(err)

    V = float(volume_m3)
    A = float(area_m2)
    B_val = float(B)
    n_val = float(n)

    if not (1.5 <= n_val <= 2.0):
        _warn(
            f"Chvorinov exponent n={n_val} is outside the typical range [1.5, 2.0].",
            warninglist,
        )

    modulus = V / A
    t_solid = B_val * (modulus ** n_val)

    return {
        "ok": True,
        "volume_m3": V,
        "area_m2": A,
        "modulus_m": modulus,
        "B": B_val,
        "n": n_val,
        "solidification_s": t_solid,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 4. riser_size
# ---------------------------------------------------------------------------

def riser_size(
    casting_volume_m3: float,
    casting_surface_area_m2: float,
    *,
    alloy: str = "carbon_steel",
    riser_shape: str = "cylindrical",
    B: float = _DEFAULT_CHVORINOV_B,
    n: float = _DEFAULT_CHVORINOV_N,
) -> dict:
    """
    Riser sizing by the modulus method (AFS / Chvorinov-based).

    A riser must remain molten longer than the casting it feeds, so that
    liquid metal can flow from the riser to compensate for shrinkage.
    The modulus method requires:

        M_riser >= 1.2 · M_casting        (AFS feeding criterion)

    where the modulus M = V / A_cooling (only the cooling surfaces are counted;
    the riser-neck and top (open riser) face are excluded in practice — here a
    simplified cylindrical geometry with H = D is used).

    For a cylindrical riser with height H = diameter D:
        V_riser = π/4 · D² · H = π/4 · D³
        A_cooling (side + bottom) = π·D·H + π/4·D² = π·D² + π/4·D²
                                  = 5π/4 · D²
        M_riser = V_riser / A_cooling = (π/4 · D³) / (5π/4 · D²) = D / 5

    Solving M_riser >= 1.2 · M_casting for D:
        D_min = 5 · 1.2 · M_casting = 6 · M_casting

    Parameters
    ----------
    casting_volume_m3 : float
        Casting volume (m³).  Must be > 0.
    casting_surface_area_m2 : float
        Casting surface area (m²).  Must be > 0.
    alloy : str
        Alloy name (default 'carbon_steel').  Used only for warning text.
    riser_shape : str
        'cylindrical' (default) — H = D cylinder.
        Only cylindrical supported; other strings return error.
    B : float
        Chvorinov B constant (default 600 s/m²).
    n : float
        Chvorinov n exponent (default 2.0).

    Returns
    -------
    dict
        ok                      : True
        casting_modulus_m       : M_casting = V_casting / A_casting (m)
        riser_modulus_required_m: 1.2 × M_casting (m)
        riser_diameter_m        : minimum riser diameter D_min (m)
        riser_height_m          : = D_min (H = D cylinder)
        riser_volume_m3         : π/4 · D³ (m³)
        riser_neck_diameter_m   : recommended neck ≈ 0.65 · D_min (m)
        casting_solidification_s: estimated t_casting via Chvorinov (s)
        riser_solidification_s  : estimated t_riser via Chvorinov (s)
        feeds_ok                : True if riser solidifies after casting
        alloy                   : alloy name used
        riser_shape             : riser shape used
        warnings                : list of warning strings

    Notes
    -----
    The riser-neck diameter is set to 0.65·D to allow easy breakoff while
    maintaining sufficient feed path cross-section (AFS guideline).

    Shrinkage-porosity risk is flagged if the riser modulus is marginal.
    """
    warninglist: list[str] = []

    err = _guard_positive("casting_volume_m3", casting_volume_m3)
    if err:
        return _err(err)
    err = _guard_positive("casting_surface_area_m2", casting_surface_area_m2)
    if err:
        return _err(err)
    err = _guard_positive("B", B)
    if err:
        return _err(err)
    err = _guard_positive("n", n)
    if err:
        return _err(err)

    shape = str(riser_shape).strip().lower()
    if shape not in ("cylindrical",):
        return _err(
            f"Unknown riser_shape {riser_shape!r}. Supported: 'cylindrical'."
        )

    alloy_key = str(alloy).strip().lower().replace(" ", "_").replace("-", "_")
    # alloy is informational only here — no error if unknown

    V_c = float(casting_volume_m3)
    A_c = float(casting_surface_area_m2)
    B_val = float(B)
    n_val = float(n)

    M_casting = V_c / A_c  # casting modulus (m)
    M_riser_req = RISER_MODULUS_FACTOR * M_casting

    # For cylindrical H=D riser:
    # M_riser = D / 5  =>  D_min = 5 * M_riser_req
    D_min = 5.0 * M_riser_req
    H_min = D_min  # H = D

    # Riser volume
    V_riser = (math.pi / 4.0) * D_min ** 3

    # Riser neck: 0.65 × D (AFS)
    neck_d = 0.65 * D_min

    # Chvorinov solidification times
    t_casting = B_val * (M_casting ** n_val)

    # Riser cooling area (side + bottom, open top excluded):
    A_riser_cool = math.pi * D_min * H_min + (math.pi / 4.0) * D_min ** 2
    M_riser_actual = V_riser / A_riser_cool
    t_riser = B_val * (M_riser_actual ** n_val)

    feeds_ok = t_riser > t_casting

    if not feeds_ok:
        _warn(
            "INSUFFICIENT RISER: riser solidification time does not exceed casting "
            "solidification time — shrinkage-porosity risk. Increase riser size.",
            warninglist,
        )

    if M_riser_actual < M_riser_req:
        # Numerical consistency check (should not happen with exact formula)
        _warn(
            f"Riser modulus {M_riser_actual:.6f} m is below required "
            f"{M_riser_req:.6f} m — check formula implementation.",
            warninglist,
        )

    return {
        "ok": True,
        "casting_modulus_m": M_casting,
        "riser_modulus_required_m": M_riser_req,
        "riser_modulus_actual_m": M_riser_actual,
        "riser_diameter_m": D_min,
        "riser_height_m": H_min,
        "riser_volume_m3": V_riser,
        "riser_neck_diameter_m": neck_d,
        "casting_solidification_s": t_casting,
        "riser_solidification_s": t_riser,
        "feeds_ok": feeds_ok,
        "alloy": alloy_key,
        "riser_shape": shape,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 5. gating_system
# ---------------------------------------------------------------------------

def gating_system(
    casting_mass_kg: float,
    alloy: str,
    pouring_time_s: float,
    sprue_height_m: float,
    *,
    system_type: str = "unpressurised",
    discharge_coeff: float = 0.85,
    mold_efficiency: float = 1.0,
) -> dict:
    """
    Gating system design: choke area from Bernoulli equation + continuity.

    The choke area (minimum cross-section in the gating system) controls the
    metal flow rate and fill time.  All other areas are scaled from the choke
    using the gating ratio.

    Bernoulli at the choke (sprue exit or gate depending on system type):

        v_choke = C_d · √(2 · g · H_eff)

    where H_eff is the effective metallostatic head.  By continuity:

        A_choke = Q / v_choke = (m / ρ) / (t_pour · v_choke)

    Parameters
    ----------
    casting_mass_kg : float
        Total mass of metal to pour including runners (kg).  Must be > 0.
    alloy : str
        Alloy name (used for density lookup).  Must be in catalog.
    pouring_time_s : float
        Target total pouring time (s).  Must be > 0.
    sprue_height_m : float
        Effective metallostatic head at choke (m).  Must be > 0.
        For a simple sprue this is the sprue height; for a pressurised system
        use the full sprue height; for unpressurised use H_eff = H_t - H_c²/(2H_t)
        where H_t = sprue height, H_c = casting height (simplified here to H_t).
    system_type : str
        'unpressurised' (default) — choke at sprue; ratios 1:2:4.
        'pressurised'             — choke at gate; ratios 1:0.75:0.5.
    discharge_coeff : float
        Discharge coefficient C_d (default 0.85).  Range (0, 1].
    mold_efficiency : float
        Fill efficiency accounting for back pressure (default 1.0).  Range (0, 1].

    Returns
    -------
    dict
        ok                : True
        alloy             : alloy name
        system_type       : gating system type
        casting_mass_kg   : mass poured (kg)
        density_kg_m3     : alloy density used (kg/m³)
        volume_to_fill_m3 : total volume = mass / density (m³)
        flow_rate_m3_s    : required volumetric flow Q = V / t_pour (m³/s)
        velocity_m_s      : metal velocity at choke (m/s)
        choke_area_m2     : minimum cross-section at choke (m²)
        sprue_area_m2     : sprue cross-section area (m²)
        runner_area_m2    : total runner cross-section area (m²)
        gate_area_m2      : total in-gate cross-section area (m²)
        gating_ratio      : (sprue:runner:gate) tuple
        warnings          : list of warning strings

    Notes
    -----
    For a pressurised system the choke is at the gate; for unpressurised the
    choke is at the sprue exit.  The ratios given are sprue:runner:gate.
    In a pressurised system the gate is smaller than sprue/runner, so the
    choke area is the gate area.  In an unpressurised system the sprue is
    smallest and is the choke.
    """
    warninglist: list[str] = []

    err = _guard_positive("casting_mass_kg", casting_mass_kg)
    if err:
        return _err(err)
    err = _guard_positive("pouring_time_s", pouring_time_s)
    if err:
        return _err(err)
    err = _guard_positive("sprue_height_m", sprue_height_m)
    if err:
        return _err(err)
    err = _guard_positive("discharge_coeff", discharge_coeff)
    if err:
        return _err(err)
    if discharge_coeff > 1.0:
        return _err(f"discharge_coeff must be <= 1.0, got {discharge_coeff}")
    err = _guard_positive("mold_efficiency", mold_efficiency)
    if err:
        return _err(err)
    if mold_efficiency > 1.0:
        return _err(f"mold_efficiency must be <= 1.0, got {mold_efficiency}")

    stype = str(system_type).strip().lower().replace("-", "").replace("_", "")
    if stype not in ("pressurised", "unpressurised"):
        return _err(
            f"Unknown system_type {system_type!r}. Supported: 'pressurised', 'unpressurised'."
        )

    alloy_key = str(alloy).strip().lower().replace(" ", "_").replace("-", "_")
    if alloy_key not in _ALLOY_DATA:
        valid = sorted(_ALLOY_DATA.keys())
        return _err(f"Unknown alloy {alloy!r}. Supported: {valid}.")

    rho = _ALLOY_DATA[alloy_key]["density_kg_m3"]
    m = float(casting_mass_kg)
    t = float(pouring_time_s)
    H = float(sprue_height_m)
    Cd = float(discharge_coeff)
    eta = float(mold_efficiency)

    # Total volume of metal
    V_fill = m / rho

    # Required volumetric flow rate
    Q = V_fill / t

    # Bernoulli: velocity at choke
    v_choke = Cd * math.sqrt(2.0 * _g * H) * eta

    # Choke area from continuity
    A_choke = Q / v_choke

    # Gating ratios
    if stype == "pressurised":
        rs, rr, rg = _GATING_RATIOS["pressurised"]
    else:
        rs, rr, rg = _GATING_RATIOS["unpressurised"]

    # For pressurised: choke is gate (smallest); sprue and runner are larger
    # Ratios are sprue:runner:gate = 1:0.75:0.5 → gate = 0.5 × sprue_area
    # So A_choke = 0.5 × A_sprue → A_sprue = A_choke / 0.5 = 2 × A_choke
    # For unpressurised: choke is sprue (1); runner = 2×; gate = 4×
    # A_choke = A_sprue, A_runner = 2×A_sprue, A_gate = 4×A_sprue

    # Normalize ratios relative to choke
    if stype == "pressurised":
        # choke is the gate (ratio rg)
        A_gate = A_choke
        A_sprue = A_choke * (rs / rg)
        A_runner = A_choke * (rr / rg)
    else:
        # choke is the sprue (ratio rs)
        A_sprue = A_choke
        A_runner = A_choke * (rr / rs)
        A_gate = A_choke * (rg / rs)

    if A_sprue < 1e-8:
        _warn("Sprue area is extremely small — check inputs.", warninglist)
    if pouring_time_s < 5.0:
        _warn(
            f"pouring_time_s={pouring_time_s:.1f} s is very short — turbulence risk.",
            warninglist,
        )

    return {
        "ok": True,
        "alloy": alloy_key,
        "system_type": stype,
        "casting_mass_kg": m,
        "density_kg_m3": rho,
        "volume_to_fill_m3": V_fill,
        "flow_rate_m3_s": Q,
        "velocity_m_s": v_choke,
        "choke_area_m2": A_choke,
        "sprue_area_m2": A_sprue,
        "runner_area_m2": A_runner,
        "gate_area_m2": A_gate,
        "gating_ratio": (rs, rr, rg),
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 6. casting_yield
# ---------------------------------------------------------------------------

def casting_yield(
    casting_mass_kg: float,
    total_poured_mass_kg: float,
) -> dict:
    """
    Casting yield calculation.

    Casting yield is the ratio of useful casting mass to total metal poured,
    expressed as a percentage.  Metal poured includes the casting itself plus
    risers, runners, sprues, and gates.

    A low yield indicates excessive gating/risering mass and higher cost.

    Parameters
    ----------
    casting_mass_kg : float
        Mass of the finished casting (kg).  Must be > 0.
    total_poured_mass_kg : float
        Total mass of metal poured into the mold (casting + gating system,
        risers, etc.) (kg).  Must be >= casting_mass_kg > 0.

    Returns
    -------
    dict
        ok                     : True
        casting_mass_kg        : casting mass (kg)
        total_poured_mass_kg   : total poured mass (kg)
        gating_riser_mass_kg   : mass in gating + risers (kg)
        yield_pct              : casting yield (%)
        warnings               : list of warning strings

    Notes
    -----
    Typical yields:
      Sand casting — 50–70%
      Investment casting — 80–95% (less gating waste)
      Die casting — 60–80%
    Yields below 50% warrant gating/risering redesign.
    """
    warninglist: list[str] = []

    err = _guard_positive("casting_mass_kg", casting_mass_kg)
    if err:
        return _err(err)
    err = _guard_positive("total_poured_mass_kg", total_poured_mass_kg)
    if err:
        return _err(err)

    m_cast = float(casting_mass_kg)
    m_total = float(total_poured_mass_kg)

    if m_cast > m_total:
        return _err(
            "casting_mass_kg must be <= total_poured_mass_kg "
            f"(got {m_cast} > {m_total})."
        )

    m_gating = m_total - m_cast
    yield_pct = (m_cast / m_total) * 100.0

    if yield_pct < 60.0:
        _warn(
            f"Casting yield {yield_pct:.1f}% is below 60% — "
            "consider reducing riser/gating mass to improve economics.",
            warninglist,
        )
    if yield_pct < 50.0:
        _warn(
            f"Casting yield {yield_pct:.1f}% is very poor (<50%) — "
            "significant shrinkage-porosity or oversized risers; redesign required.",
            warninglist,
        )

    return {
        "ok": True,
        "casting_mass_kg": m_cast,
        "total_poured_mass_kg": m_total,
        "gating_riser_mass_kg": m_gating,
        "yield_pct": yield_pct,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 7. pouring_guidance
# ---------------------------------------------------------------------------

def pouring_guidance(
    alloy: str,
    section_thickness_mm: float,
) -> dict:
    """
    Fluidity and pouring temperature guidance by alloy and section thickness.

    Pouring temperature must be high enough above the liquidus to maintain
    fluidity to the thinnest section, yet not so high as to cause excessive
    shrinkage, hot tearing, or gas absorption.

    Parameters
    ----------
    alloy : str
        Alloy name from the built-in catalog.
    section_thickness_mm : float
        Minimum section thickness in the casting (mm).  Must be > 0.
        Used to flag thin-section risk.

    Returns
    -------
    dict
        ok                      : True
        alloy                   : alloy name
        section_thickness_mm    : minimum section thickness (mm)
        pouring_temp_low_C      : recommended minimum pouring temperature (°C)
        pouring_temp_high_C     : recommended maximum pouring temperature (°C)
        fluidity_note           : alloy-specific fluidity guidance string
        thin_section_warning    : True if section_thickness_mm < threshold
        warnings                : list of warning strings

    Notes
    -----
    Thin-section thresholds (indicative):
      Ferrous alloys  : < 5 mm is considered thin
      Aluminium alloys: < 3 mm is considered thin
      Other non-ferrous: < 2 mm is considered thin

    For investment casting, thin sections down to 0.5 mm are achievable.
    These thresholds apply primarily to sand and permanent-mold casting.
    """
    warninglist: list[str] = []

    err = _guard_positive("section_thickness_mm", section_thickness_mm)
    if err:
        return _err(err)

    alloy_key = str(alloy).strip().lower().replace(" ", "_").replace("-", "_")
    if alloy_key not in _ALLOY_DATA:
        valid = sorted(_ALLOY_DATA.keys())
        return _err(f"Unknown alloy {alloy!r}. Supported: {valid}.")

    data = _ALLOY_DATA[alloy_key]
    t_low, t_high = data["pouring_temp_C"]
    note = data["fluidity_note"]

    # Thin-section thresholds
    ferrous = alloy_key in (
        "grey_cast_iron", "white_cast_iron", "ductile_iron",
        "carbon_steel", "stainless_steel", "nickel_alloy",
    )
    if ferrous:
        thin_threshold = 5.0
    elif alloy_key in ("aluminium_alloy", "magnesium_alloy"):
        thin_threshold = 3.0
    else:
        thin_threshold = 2.0

    thin_warn = float(section_thickness_mm) < thin_threshold

    if thin_warn:
        _warn(
            f"Section thickness {section_thickness_mm:.1f} mm is below the "
            f"threshold of {thin_threshold:.0f} mm for {alloy_key} — "
            "ensure pouring temperature is at the upper limit and consider "
            "pressurised gating or investment casting.",
            warninglist,
        )

    return {
        "ok": True,
        "alloy": alloy_key,
        "section_thickness_mm": float(section_thickness_mm),
        "pouring_temp_low_C": t_low,
        "pouring_temp_high_C": t_high,
        "fluidity_note": note,
        "thin_section_warning": thin_warn,
        "warnings": warninglist,
    }
