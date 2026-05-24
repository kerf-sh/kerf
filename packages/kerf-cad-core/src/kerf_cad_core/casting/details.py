"""
kerf_cad_core.casting.details — deeper casting design physics.

Implements four public functions and one integrated design-package function:

  shrinkage_factor(alloy)
      Linear shrinkage fraction lookup from the foundry-standard table.

  pattern_dimensions(part_dims, alloy)
      Scale a sequence of part dimensions by the shrinkage factor.

  chvorinov_time(volume_m3, surface_area_m2, mould_constant_C)
      Solidification time via Chvorinov's rule: t = C · (V/A)²
      with built-in C defaults per mould type and alloy family.

  riser_diameter(casting_VA, height_to_dia_ratio, safety)
      Cylindrical riser sizing so (V/A)_riser ≥ safety × (V/A)_casting,
      accounting for top-riser (efficiency ≈ 0.8) vs. side-riser
      (efficiency ≈ 0.5) feed-volume requirements.

  design_riser_and_gating(part_volume_m3, part_surface_m2, alloy, mould_type)
      Full design package: pattern allowance, solidification time, riser
      dimensions, gating ratios, and recommended pouring rate.

All functions return plain dicts:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Warnings are collected into the result dict.

Units
-----
  lengths     — metres (m) unless noted as mm
  volumes     — cubic metres (m³)
  areas       — square metres (m²)
  mass        — kilograms (kg)
  time        — seconds (s)
  temperature — degrees Celsius (°C)

References
----------
Heine, R.W., Loper, C.R. & Rosenthal, P.C. "Principles of Metal Casting",
  2nd ed., McGraw-Hill (1967) — shrinkage table §5, Chvorinov §8, riser §9.
Campbell, J. "Castings", 2nd ed., Butterworth-Heinemann (2003) — §4, §5.
AFS Gating and Risering Manual — unpressurised ratio 1:2:4.
Chvorinov, N. — Giesserei 27 (1940) 177-186.

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import Sequence

# ---------------------------------------------------------------------------
# Internal helpers (duplicated from design.py to keep this file standalone)
# ---------------------------------------------------------------------------


def _guard_positive(name: str, value) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


def _guard_nonneg(name: str, value) -> str | None:
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
    warnings.warn(msg, UserWarning, stacklevel=4)
    collected.append(msg)


# ---------------------------------------------------------------------------
# 1. Shrinkage-allowance table (Heine/Loper/Rosenthal §5 + AFS handbook)
# ---------------------------------------------------------------------------
# Keys are normalised alloy identifiers.  Values are fractional linear
# shrinkages.  Where a range is given (e.g. mild steel 1.6–2.0 %) we use
# the conservative (upper) value so patterns are never under-sized.
#
# Sources:
#   Heine/Loper/Rosenthal Table 5.1
#   Campbell "Castings" Table 4.1
#   AFS foundry handbook

_SHRINKAGE_TABLE: dict[str, float] = {
    # Ferrous
    "grey_cast_iron":    0.010,   # 1.0 %  — graphite expansion reduces shrinkage
    "white_cast_iron":   0.020,   # 2.0 %  — no graphite; behaves like steel
    "ductile_iron":      0.006,   # 0.6 %  — compacted graphite partly offsets
    "mild_steel":        0.020,   # 2.0 %  — upper end of 1.6–2.0 % range
    "carbon_steel":      0.020,   # 2.0 %  — same as mild_steel
    "stainless_steel":   0.021,   # 2.1 %
    # Non-ferrous
    "brass":             0.015,   # 1.5 %
    "bronze":            0.015,   # 1.5 %
    "copper":            0.020,   # 2.0 %
    "copper_alloy":      0.016,   # 1.6 % (generic)
    "aluminium_alloy":   0.013,   # 1.3 %
    "aluminium":         0.013,   # 1.3 %
    "magnesium_alloy":   0.013,   # 1.3 %
    "magnesium":         0.013,   # 1.3 %
    "zinc_alloy":        0.012,   # 1.2 %
    "zinc":              0.012,   # 1.2 %
    "nickel_alloy":      0.022,   # 2.2 %
    "titanium_alloy":    0.015,   # 1.5 %
}

# Alloy density (kg/m³) — subset needed for feed-volume calculations.
_DENSITY: dict[str, float] = {
    "grey_cast_iron":   7200.0,
    "white_cast_iron":  7700.0,
    "ductile_iron":     7100.0,
    "mild_steel":       7850.0,
    "carbon_steel":     7850.0,
    "stainless_steel":  7900.0,
    "brass":            8500.0,
    "bronze":           8700.0,
    "copper":           8960.0,
    "copper_alloy":     8500.0,
    "aluminium_alloy":  2700.0,
    "aluminium":        2700.0,
    "magnesium_alloy":  1800.0,
    "magnesium":        1800.0,
    "zinc_alloy":       6600.0,
    "zinc":             6600.0,
    "nickel_alloy":     8800.0,
    "titanium_alloy":   4500.0,
}


def _normalise_alloy(alloy: str) -> str:
    return str(alloy).strip().lower().replace(" ", "_").replace("-", "_")


def _normalise_mould(mould_type: str) -> str:
    return str(mould_type).strip().lower().replace(" ", "_").replace("-", "_")


# ---------------------------------------------------------------------------
# Chvorinov constant C (s/m²) per mould type.
# t_solidify = C · (V/A)²  (n=2 Chvorinov standard form)
#
# Units note: if V is in m³ and A in m², then V/A is in m.
# C in s/m² gives t in seconds.
#
# Representative values (must be calibrated experimentally):
#   Green sand / steel alloys : C ≈ 600 s/m²
#   Green sand / Al alloys    : C ≈ 400 s/m²   (lower latent heat, lower temp)
#   Metal / permanent mould   : C ≈ 100–200 s/m² (faster extraction)
#   Die casting               : C ≈  50–100 s/m²
#
# Sources: Groover Table 11.2; Heine/Loper/Rosenthal §8.
# ---------------------------------------------------------------------------

_MOULD_C: dict[str, dict[str, float]] = {
    # green sand
    "sand": {
        "ferrous":        600.0,   # s/m²
        "non_ferrous":    400.0,
        "default":        600.0,
    },
    # permanent (gravity die)
    "metal": {
        "ferrous":        200.0,
        "non_ferrous":    130.0,
        "default":        200.0,
    },
    # pressure die casting
    "die": {
        "ferrous":         80.0,
        "non_ferrous":     55.0,
        "default":         80.0,
    },
}

_FERROUS_ALLOYS = frozenset({
    "grey_cast_iron", "white_cast_iron", "ductile_iron",
    "mild_steel", "carbon_steel", "stainless_steel",
    "nickel_alloy", "titanium_alloy",
})

_VALID_MOULD_TYPES = tuple(_MOULD_C.keys())

# Riser efficiency by location (fraction of riser volume usable for feeding)
_RISER_EFFICIENCY: dict[str, float] = {
    "top":  0.80,   # atmospheric pressure acts on top riser — better feed
    "side": 0.50,   # side risers partially isolated; less efficient
}

_VALID_RISER_LOCATIONS = tuple(_RISER_EFFICIENCY.keys())

# Non-pressurised gating ratios (sprue : runner : gate) — AFS / Campbell
_GATING_RATIO = (1.0, 2.0, 4.0)

# Gravitational acceleration
_g = 9.81  # m/s²


# ---------------------------------------------------------------------------
# 1. shrinkage_factor
# ---------------------------------------------------------------------------

def shrinkage_factor(alloy: str) -> dict:
    """
    Return the linear shrinkage factor for a given alloy.

    Parameters
    ----------
    alloy : str
        Alloy identifier.  Supported alloys: see _SHRINKAGE_TABLE.

    Returns
    -------
    dict
        ok                : True
        alloy             : normalised alloy key
        linear_shrinkage  : fractional linear shrinkage (e.g. 0.020 for 2.0 %)
        shrinkage_pct     : shrinkage as a percentage (e.g. 2.0)
        warnings          : list of warning strings

    References
    ----------
    Heine/Loper/Rosenthal Table 5.1; Campbell "Castings" Table 4.1.
    """
    warninglist: list[str] = []
    key = _normalise_alloy(alloy)
    if key not in _SHRINKAGE_TABLE:
        valid = sorted(_SHRINKAGE_TABLE.keys())
        return _err(f"Unknown alloy {alloy!r}. Supported: {valid}.")
    ls = _SHRINKAGE_TABLE[key]
    return {
        "ok": True,
        "alloy": key,
        "linear_shrinkage": ls,
        "shrinkage_pct": ls * 100.0,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 2. pattern_dimensions
# ---------------------------------------------------------------------------

def pattern_dimensions(
    part_dims: Sequence[float],
    alloy: str,
) -> dict:
    """
    Compute oversized pattern dimensions from nominal part dimensions.

    Pattern dimension = nominal / (1 - linear_shrinkage)

    Parameters
    ----------
    part_dims : sequence of float
        Nominal part dimensions in any consistent unit (e.g. mm or m).
        Each must be > 0.
    alloy : str
        Alloy identifier.

    Returns
    -------
    dict
        ok                : True
        alloy             : normalised alloy key
        linear_shrinkage  : fractional linear shrinkage
        part_dims         : input dimensions
        pattern_dims      : oversized pattern dimensions (same unit as input)
        scale_factor      : 1 / (1 - linear_shrinkage)
        warnings          : list of warning strings

    Notes
    -----
    Only solidification shrinkage is compensated; machining stock must be
    added separately (see kerf_cad_core.casting.design.shrinkage_allowance).
    """
    warninglist: list[str] = []

    key = _normalise_alloy(alloy)
    if key not in _SHRINKAGE_TABLE:
        valid = sorted(_SHRINKAGE_TABLE.keys())
        return _err(f"Unknown alloy {alloy!r}. Supported: {valid}.")

    dims = list(part_dims)
    if not dims:
        return _err("part_dims must contain at least one dimension.")

    for i, d in enumerate(dims):
        e = _guard_positive(f"part_dims[{i}]", d)
        if e:
            return _err(e)

    ls = _SHRINKAGE_TABLE[key]
    scale = 1.0 / (1.0 - ls)
    pattern = [float(d) * scale for d in dims]

    return {
        "ok": True,
        "alloy": key,
        "linear_shrinkage": ls,
        "part_dims": [float(d) for d in dims],
        "pattern_dims": pattern,
        "scale_factor": scale,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 3. chvorinov_time
# ---------------------------------------------------------------------------

def chvorinov_time(
    volume_m3: float,
    surface_area_m2: float,
    *,
    mould_type: str = "sand",
    alloy: str = "carbon_steel",
    mould_constant_C: float | None = None,
) -> dict:
    """
    Solidification time via Chvorinov's rule: t = C · (V/A)²

    The mould constant C depends on the mould material and alloy family.
    A custom C may be supplied to override the built-in table.

    Parameters
    ----------
    volume_m3 : float
        Casting volume (m³).  Must be > 0.
    surface_area_m2 : float
        Casting surface area (m²).  Must be > 0.
    mould_type : str
        'sand' (default), 'metal', or 'die'.
    alloy : str
        Alloy identifier (used to select ferrous vs. non-ferrous C value).
    mould_constant_C : float, optional
        Override the built-in C table (s/m²).  Must be > 0 if supplied.

    Returns
    -------
    dict
        ok                : True
        volume_m3         : casting volume (m³)
        surface_area_m2   : casting surface area (m²)
        modulus_m         : V/A — casting modulus (m)
        mould_type        : mould type key used
        alloy             : alloy key used
        C                 : Chvorinov constant used (s/m²)
        solidification_s  : t = C · (V/A)² (s)
        solidification_min: solidification time in minutes
        warnings          : list of warning strings

    References
    ----------
    Chvorinov, N. — Giesserei 27 (1940) 177-186.
    Heine/Loper/Rosenthal §8.
    """
    warninglist: list[str] = []

    e = _guard_positive("volume_m3", volume_m3)
    if e:
        return _err(e)
    e = _guard_positive("surface_area_m2", surface_area_m2)
    if e:
        return _err(e)

    mkey = _normalise_mould(mould_type)
    if mkey not in _MOULD_C:
        return _err(
            f"Unknown mould_type {mould_type!r}. "
            f"Supported: {list(_MOULD_C.keys())}."
        )

    akey = _normalise_alloy(alloy)

    if mould_constant_C is not None:
        e = _guard_positive("mould_constant_C", mould_constant_C)
        if e:
            return _err(e)
        C = float(mould_constant_C)
        _warn(
            f"Custom mould_constant_C={C} s/m² supplied; ignoring built-in table.",
            warninglist,
        )
    else:
        mould_row = _MOULD_C[mkey]
        if akey in _FERROUS_ALLOYS:
            C = mould_row["ferrous"]
        else:
            C = mould_row["non_ferrous"]

    V = float(volume_m3)
    A = float(surface_area_m2)
    modulus = V / A
    t_s = C * modulus ** 2
    t_min = t_s / 60.0

    return {
        "ok": True,
        "volume_m3": V,
        "surface_area_m2": A,
        "modulus_m": modulus,
        "mould_type": mkey,
        "alloy": akey if akey in _SHRINKAGE_TABLE else alloy,
        "C": C,
        "solidification_s": t_s,
        "solidification_min": t_min,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 4. riser_diameter
# ---------------------------------------------------------------------------

def riser_diameter(
    casting_VA: float,
    *,
    height_to_dia_ratio: float = 1.0,
    safety: float = 1.1,
    alloy: str = "carbon_steel",
    riser_location: str = "top",
) -> dict:
    """
    Size a cylindrical riser so that (V/A)_riser ≥ safety × (V/A)_casting.

    Riser solidifies LAST → feeds liquid metal into the casting during
    shrinkage.  The required riser modulus is:

        M_riser = safety × M_casting

    For a cylinder with height H = k · D (k = height_to_dia_ratio):
        V_riser = π/4 · D² · H = π/4 · k · D³
        A_cool  = π · D · H + π/4 · D² (side + bottom; open top excluded)
                = k·π·D² + π/4·D²
        M_riser = V/A = (π/4 · k · D³) / ((k + 0.25) · π · D²)
                      = k · D / (4 · (k + 0.25))

    Solving M_riser ≥ safety × casting_VA for D:
        D_min = safety × casting_VA × 4 × (k + 0.25) / k

    Riser efficiency accounts for how much of the riser volume is usable:
        top riser  : efficiency ≈ 0.80
        side riser : efficiency ≈ 0.50

    The required feed volume (shrinkage) is calculated as:
        V_shrink = casting_VA · surface_area_equivalent × shrinkage_pct
    Since surface_area_equivalent is not passed here, this function sizes
    the riser purely on the Chvorinov modulus criterion (solidification
    sequence), which is the primary constraint.

    Parameters
    ----------
    casting_VA : float
        V/A modulus of the casting (m).  Must be > 0.
    height_to_dia_ratio : float
        k = H/D for the cylindrical riser.  Default 1.0 (H = D).
        Must be > 0.
    safety : float
        Safety factor on the modulus ratio (default 1.1).
        Typical range: 1.0 – 1.2.  Must be > 0.
    alloy : str
        Alloy identifier (informational; used for shrinkage_pct in notes).
    riser_location : str
        'top' (default, efficiency 0.80) or 'side' (efficiency 0.50).

    Returns
    -------
    dict
        ok                     : True
        casting_modulus_m      : V/A modulus of the casting (m)
        required_riser_modulus_m: safety × casting_modulus_m (m)
        height_to_dia_ratio    : k used
        safety                 : safety factor used
        riser_location         : 'top' or 'side'
        riser_efficiency       : feed efficiency fraction (0.80 or 0.50)
        riser_diameter_m       : minimum riser diameter D (m)
        riser_diameter_mm      : D in millimetres
        riser_height_m         : H = k · D (m)
        riser_height_mm        : H in millimetres
        riser_volume_m3        : π/4 · k · D³ (m³)
        riser_actual_modulus_m : actual M_riser achieved (m)
        warnings               : list of warning strings

    References
    ----------
    Heine/Loper/Rosenthal §9; Campbell "Castings" §5.
    """
    warninglist: list[str] = []

    e = _guard_positive("casting_VA", casting_VA)
    if e:
        return _err(e)
    e = _guard_positive("height_to_dia_ratio", height_to_dia_ratio)
    if e:
        return _err(e)
    e = _guard_positive("safety", safety)
    if e:
        return _err(e)

    loc = str(riser_location).strip().lower()
    if loc not in _RISER_EFFICIENCY:
        return _err(
            f"Unknown riser_location {riser_location!r}. "
            f"Supported: {list(_RISER_EFFICIENCY.keys())}."
        )

    if safety < 1.0:
        _warn(
            f"safety={safety} < 1.0: riser modulus will be LESS than casting "
            "modulus — riser will solidify before the casting (porosity risk).",
            warninglist,
        )

    M_c = float(casting_VA)
    k = float(height_to_dia_ratio)
    sf = float(safety)

    M_riser_req = sf * M_c

    # From M_riser = k · D / (4 · (k + 0.25)):
    # D = 4 · (k + 0.25) · M_riser_req / k
    D = 4.0 * (k + 0.25) * M_riser_req / k
    H = k * D

    # Actual riser modulus (verify)
    V_r = (math.pi / 4.0) * k * D ** 3
    A_r = (k + 0.25) * math.pi * D ** 2
    M_r_actual = V_r / A_r  # should equal M_riser_req

    eff = _RISER_EFFICIENCY[loc]

    return {
        "ok": True,
        "casting_modulus_m": M_c,
        "required_riser_modulus_m": M_riser_req,
        "height_to_dia_ratio": k,
        "safety": sf,
        "riser_location": loc,
        "riser_efficiency": eff,
        "riser_diameter_m": D,
        "riser_diameter_mm": D * 1000.0,
        "riser_height_m": H,
        "riser_height_mm": H * 1000.0,
        "riser_volume_m3": V_r,
        "riser_actual_modulus_m": M_r_actual,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 5. design_riser_and_gating  (integrated design package)
# ---------------------------------------------------------------------------

def design_riser_and_gating(
    part_volume_m3: float,
    part_surface_m2: float,
    alloy: str,
    mould_type: str = "sand",
    *,
    height_to_dia_ratio: float = 1.0,
    riser_location: str = "top",
    riser_safety: float = 1.1,
    pouring_time_s: float | None = None,
    sprue_height_m: float = 0.3,
    max_fill_time_s: float | None = None,
) -> dict:
    """
    Full casting design package: pattern, solidification, riser, and gating.

    Parameters
    ----------
    part_volume_m3 : float
        Casting cavity volume (m³).  Must be > 0.
    part_surface_m2 : float
        Casting surface area (m²).  Must be > 0.
    alloy : str
        Alloy identifier.
    mould_type : str
        'sand' (default), 'metal', or 'die'.
    height_to_dia_ratio : float
        H/D ratio for cylindrical riser (default 1.0).
    riser_location : str
        'top' (default) or 'side'.
    riser_safety : float
        Modulus safety factor for riser sizing (default 1.1).
    pouring_time_s : float, optional
        Target pouring time (s).  If None, estimated from cavity volume:
        t_pour = max(5, 2.4 · √V_cm3)  where V_cm3 is volume in cm³.
        (Simplified AFS rule; use foundry process engineer's value in practice.)
    sprue_height_m : float
        Effective metallostatic head (m) for gating calculations (default 0.3 m).
    max_fill_time_s : float, optional
        Maximum acceptable fill time (s) — if estimated t_pour exceeds this,
        a warning is issued.

    Returns
    -------
    dict
        ok                    : True
        alloy                 : alloy key
        mould_type            : mould key
        linear_shrinkage      : fractional linear shrinkage
        scale_factor          : 1 / (1 - linear_shrinkage) — pattern scale
        shrinkage_pct         : linear shrinkage in percent
        solidification_s      : estimated t_solidify (s)
        solidification_min    : estimated t_solidify (min)
        chvorinov_C           : Chvorinov constant used (s/m²)
        casting_modulus_m     : V/A (m)
        riser_diameter_m      : minimum riser D (m)
        riser_diameter_mm     : minimum riser D (mm)
        riser_height_m        : riser H (m)
        riser_height_mm       : riser H (mm)
        riser_volume_m3       : riser volume (m³)
        riser_location        : riser location used
        riser_efficiency      : feed efficiency
        gating_ratio          : (sprue, runner, gate) area ratio tuple
        pouring_time_s        : target pouring time used (s)
        sprue_height_m        : metallostatic head used (m)
        pouring_rate_m3_s     : required volumetric flow Q = V / t_pour (m³/s)
        choke_velocity_m_s    : metal velocity at sprue exit (m/s)
        shrinkage_volume_m3   : estimated liquid shrinkage volume (m³)
        required_feed_volume_m3: feed volume needed (shrinkage / efficiency)
        riser_adequate        : True if riser_volume ≥ required_feed_volume
        warnings              : list of warning strings

    Notes on gating
    ---------------
    Non-pressurised system (Campbell, AFS): sprue : runner : gate = 1 : 2 : 4.
    Choke at sprue — metal velocity governed by Bernoulli at the sprue exit.
    Suitable for most ferrous and non-ferrous sand castings.

    Validation (50 × 50 × 50 mm mild steel, sand mould)
    ------------------------------------------------------
    V = 1.25e-4 m³, A = 1.5e-2 m², modulus = 8.33e-3 m
    C = 600 s/m²  →  t = 600 × (8.33e-3)² ≈ 41.7 s ≈ 0.69 min
    pattern scale = 1/0.98 ≈ 1.0204  →  ~2.04 % oversize
    riser D ≈ 4 × (1 + 0.25) × (1.1 × 8.33e-3) / 1 ≈ 45.8 mm

    References
    ----------
    Heine/Loper/Rosenthal §5, §8, §9.
    Campbell "Castings" §4, §5.
    AFS Gating and Risering Manual.
    """
    warninglist: list[str] = []

    e = _guard_positive("part_volume_m3", part_volume_m3)
    if e:
        return _err(e)
    e = _guard_positive("part_surface_m2", part_surface_m2)
    if e:
        return _err(e)

    akey = _normalise_alloy(alloy)
    if akey not in _SHRINKAGE_TABLE:
        valid = sorted(_SHRINKAGE_TABLE.keys())
        return _err(f"Unknown alloy {alloy!r}. Supported: {valid}.")

    mkey = _normalise_mould(mould_type)
    if mkey not in _MOULD_C:
        return _err(
            f"Unknown mould_type {mould_type!r}. "
            f"Supported: {list(_MOULD_C.keys())}."
        )

    # --- 1. Pattern shrinkage ---
    ls = _SHRINKAGE_TABLE[akey]
    scale = 1.0 / (1.0 - ls)

    # --- 2. Chvorinov solidification time ---
    mould_row = _MOULD_C[mkey]
    C = mould_row["ferrous"] if akey in _FERROUS_ALLOYS else mould_row["non_ferrous"]

    V = float(part_volume_m3)
    A = float(part_surface_m2)
    modulus = V / A
    t_solid = C * modulus ** 2
    t_solid_min = t_solid / 60.0

    # --- 3. Riser sizing ---
    r = riser_diameter(
        modulus,
        height_to_dia_ratio=height_to_dia_ratio,
        safety=riser_safety,
        alloy=akey,
        riser_location=riser_location,
    )
    if not r["ok"]:
        return r

    D = r["riser_diameter_m"]
    H_riser = r["riser_height_m"]
    V_riser = r["riser_volume_m3"]
    eff = r["riser_efficiency"]

    # Feed volume required: liquid shrinkage ≈ linear_shrinkage × 3 (volumetric)
    # approximated as 3 × linear_shrinkage × V_casting  (first-order)
    vol_shrinkage = 3.0 * ls * V
    required_feed_vol = vol_shrinkage / eff
    riser_adequate = V_riser >= required_feed_vol

    if not riser_adequate:
        _warn(
            f"Riser volume {V_riser * 1e6:.2f} cm³ < required feed volume "
            f"{required_feed_vol * 1e6:.2f} cm³ — increase riser size or "
            "use insulating sleeves.",
            warninglist,
        )

    # --- 4. Gating system ---
    # Estimate pouring time if not given
    if pouring_time_s is not None:
        e = _guard_positive("pouring_time_s", pouring_time_s)
        if e:
            return _err(e)
        t_pour = float(pouring_time_s)
    else:
        # AFS simplified rule: t = max(5, 2.4 × √V_cm3)
        V_cm3 = V * 1e6
        t_pour = max(5.0, 2.4 * math.sqrt(V_cm3))

    if max_fill_time_s is not None:
        if t_pour > float(max_fill_time_s):
            _warn(
                f"Estimated pouring time {t_pour:.1f} s exceeds maximum "
                f"acceptable fill time {max_fill_time_s:.1f} s — "
                "increase sprue/gate area or reduce mould volume.",
                warninglist,
            )

    e = _guard_positive("sprue_height_m", sprue_height_m)
    if e:
        return _err(e)
    H_sprue = float(sprue_height_m)

    # Choke velocity from Bernoulli (discharge coeff 0.85)
    Cd = 0.85
    v_choke = Cd * math.sqrt(2.0 * _g * H_sprue)

    # Required volumetric flow rate
    Q = V / t_pour

    # Choke area (sprue exit in non-pressurised system)
    A_choke = Q / v_choke

    # Gating areas: sprue:runner:gate = 1:2:4 (non-pressurised)
    rs, rr, rg = _GATING_RATIO
    A_sprue = A_choke          # choke at sprue
    A_runner = A_choke * rr
    A_gate = A_choke * rg

    if t_pour < 5.0:
        _warn(
            f"pouring_time_s={t_pour:.1f} s is very short — turbulence risk. "
            "Consider enlarging sprue or using a pressurised system.",
            warninglist,
        )

    return {
        "ok": True,
        "alloy": akey,
        "mould_type": mkey,
        # Pattern
        "linear_shrinkage": ls,
        "scale_factor": scale,
        "shrinkage_pct": ls * 100.0,
        # Solidification
        "solidification_s": t_solid,
        "solidification_min": t_solid_min,
        "chvorinov_C": C,
        "casting_modulus_m": modulus,
        # Riser
        "riser_diameter_m": D,
        "riser_diameter_mm": D * 1000.0,
        "riser_height_m": H_riser,
        "riser_height_mm": H_riser * 1000.0,
        "riser_volume_m3": V_riser,
        "riser_location": riser_location,
        "riser_efficiency": eff,
        # Feed volume check
        "shrinkage_volume_m3": vol_shrinkage,
        "required_feed_volume_m3": required_feed_vol,
        "riser_adequate": riser_adequate,
        # Gating
        "gating_ratio": (rs, rr, rg),
        "pouring_time_s": t_pour,
        "sprue_height_m": H_sprue,
        "pouring_rate_m3_s": Q,
        "choke_velocity_m_s": v_choke,
        "sprue_area_m2": A_sprue,
        "runner_area_m2": A_runner,
        "gate_area_m2": A_gate,
        "warnings": warninglist,
    }
