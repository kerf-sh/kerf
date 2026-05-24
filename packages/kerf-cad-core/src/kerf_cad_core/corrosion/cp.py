"""
kerf_cad_core.corrosion.cp — pure-Python corrosion engineering & cathodic
protection calculations.

Implements ten public functions:

  galvanic_couple(anode_metal, cathode_metal, *, anode_area_m2, cathode_area_m2)
      Galvanic series open-circuit potentials, driving voltage, and area-ratio
      effect (higher cathode/anode ratio accelerates anode attack).

  faraday_corrosion_rate(current_density_A_m2, equivalent_weight_g_mol, density_g_cm3)
      Corrosion rate via Faraday's law in mpy, mm/yr, and g·m⁻²·d⁻¹.

  penetration_remaining_life(wall_thickness_mm, corrosion_rate_mm_yr,
                             *, minimum_thickness_mm)
      Current penetration depth and estimated remaining life from wall loss.

  sacrificial_anode_demand(bare_area_m2, coating_efficiency, current_density_mA_m2)
      Total protection current from coating breakdown and bare area.

  anode_mass_design_life(current_A, design_life_yr, *, utilisation_factor,
                          anode_type)
      Net mass of sacrificial anode material required for a design life.

  anode_count_dwight(anode_mass_kg, individual_anode_mass_kg,
                      resistance_env_ohm, driving_voltage_V, *, coating_breakdown)
      Number of anodes using Dwight/McCoy formula for groundbed resistance and
      current output per anode.

  iccp_sizing(protected_area_m2, coating_efficiency, current_density_mA_m2,
              groundbed_resistance_ohm, *, safety_factor, attenuation_factor)
      Impressed current cathodic protection: rectifier current & voltage sizing.

  pourbaix_region(potential_V_she, pH, *, metal)
      Simplified Pourbaix (E-pH) region assessment: immune / passive / corrosion.

  corrosivity_category(soil_resistivity_ohm_m, *, environment)
      Atmospheric or soil corrosivity category from resistivity / environment.

  coating_breakdown_factor(age_yr, design_life_yr, *, initial_breakdown_frac,
                            final_breakdown_frac)
      Time-varying coating breakdown factor for CP current demand calculations.

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Warnings list flags rapid-corrosion / under-protected /
over-protection conditions; it is always present on success (may be empty).

Units (unless otherwise stated)
--------------------------------
  area         — m²
  current      — A (milliamps noted explicitly as mA)
  potential    — V vs SHE (standard hydrogen electrode)
  mass         — kg
  thickness    — mm
  corrosion rate — mm/yr  (also mpy = mils per year, g·m⁻²·d⁻¹)
  resistivity  — Ω·m

References
----------
NACE SP0169-2013  — Control of External Corrosion on Underground/Submerged
                    Metallic Piping Systems
NACE SP0176-2007  — Corrosion Control of Steel Fixed Offshore Platforms
DNV-RP-B401:2021  — Cathodic Protection Design
ISO 15589-1:2015  — Cathodic protection of pipeline systems (land)
Peabody, A.W.     — Peabody's Control of Pipeline Corrosion, 2nd ed. (NACE)
Fontana, M.G.     — Corrosion Engineering, 3rd ed.
Shreir, L.L. et al. — Corrosion (3rd ed.), Butterworth-Heinemann

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_fraction(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite"
    if not (0.0 <= v <= 1.0):
        return f"{name} must be in [0, 1], got {v}"
    return None


_GALVANIC_SERIES: dict[str, float] = {
    # Active (anodic) end
    "magnesium":          -1.75,
    "mg_alloy":           -1.60,
    "zinc":               -1.05,
    "galvanized_steel":   -1.05,
    "aluminum_alloy":     -0.80,
    "aluminum":           -0.76,
    "cadmium":            -0.40,
    "mild_steel":         -0.50,
    "carbon_steel":       -0.50,
    "cast_iron":          -0.50,
    "stainless_304_active": -0.46,
    "lead":               -0.26,
    "tin":                -0.14,
    "nickel_active":      -0.11,
    "brass":              -0.08,
    "bronze":             -0.04,
    "copper":             -0.02,
    "copper_nickel":       0.05,
    "nickel_passive":      0.13,
    "stainless_316_passive": 0.18,
    "stainless_304_passive": 0.17,
    "titanium":            0.20,
    "platinum":            0.52,
    # Noble (cathodic) end
    "gold":                0.95,
    "graphite":            0.30,
}

# Sacrificial anode electrochemical data
# (capacity A·h/kg, typical closed-circuit potential vs SHE)
_ANODE_DATA: dict[str, dict] = {
    "zinc":       {"capacity_Ah_kg": 780.0,  "potential_V_she": -1.05},
    "magnesium":  {"capacity_Ah_kg": 1100.0, "potential_V_she": -1.75},
    "aluminum":   {"capacity_Ah_kg": 2000.0, "potential_V_she": -1.10},
}

# Steel protection potential threshold (NACE SP0169: -0.85 V CSE → -0.608 V SHE)
_STEEL_PROTECTION_POTENTIAL_SHE = -0.608  # V vs SHE (−850 mV vs Cu/CuSO4)
# Over-protection threshold for hydrogen embrittlement risk
_STEEL_OVERPROTECTION_POTENTIAL_SHE = -1.10  # V vs SHE

# Faraday constant
_FARADAY = 96485.0  # C/mol


# ---------------------------------------------------------------------------
# 1. galvanic_couple
# ---------------------------------------------------------------------------

def galvanic_couple(
    anode_metal: str,
    cathode_metal: str,
    *,
    anode_area_m2: float = 1.0,
    cathode_area_m2: float = 1.0,
) -> dict:
    """
    Galvanic couple analysis from the galvanic series.

    Identifies which metal is anodic (more negative potential) and which is
    cathodic, computes the driving voltage (E_cathode − E_anode), and flags
    the area-ratio effect: a large cathode-to-anode area ratio concentrates
    corrosion attack and accelerates wastage.

    Parameters
    ----------
    anode_metal : str
        Name of the (intended or predicted) anode metal from the built-in
        galvanic series table.
    cathode_metal : str
        Name of the cathode metal.
    anode_area_m2 : float
        Exposed anode area (m²). Default 1.0. Must be > 0.
    cathode_area_m2 : float
        Exposed cathode area (m²). Default 1.0. Must be > 0.

    Returns
    -------
    dict
        ok                   : True
        anode_metal          : confirmed anode metal (more negative)
        cathode_metal        : confirmed cathode metal (more positive)
        anode_potential_V    : open-circuit potential of anode (V vs SHE)
        cathode_potential_V  : open-circuit potential of cathode (V vs SHE)
        driving_voltage_V    : E_cathode − E_anode (V); always >= 0
        area_ratio           : cathode_area / anode_area
        area_effect_note     : qualitative note on area-ratio severity
        warnings             : list of warning strings
    """
    err = _guard_positive("anode_area_m2", anode_area_m2)
    if err:
        return _err(err)
    err = _guard_positive("cathode_area_m2", cathode_area_m2)
    if err:
        return _err(err)

    a_key = str(anode_metal).strip().lower().replace(" ", "_").replace("-", "_")
    c_key = str(cathode_metal).strip().lower().replace(" ", "_").replace("-", "_")

    if a_key not in _GALVANIC_SERIES:
        valid = sorted(_GALVANIC_SERIES.keys())
        return _err(
            f"anode_metal {anode_metal!r} not in galvanic series. "
            f"Supported: {valid}"
        )
    if c_key not in _GALVANIC_SERIES:
        valid = sorted(_GALVANIC_SERIES.keys())
        return _err(
            f"cathode_metal {cathode_metal!r} not in galvanic series. "
            f"Supported: {valid}"
        )

    E_a = _GALVANIC_SERIES[a_key]
    E_c = _GALVANIC_SERIES[c_key]

    # If user supplied them reversed, swap so anode is always the active one.
    if E_a > E_c:
        # Swap: the user's "anode" is actually more noble — reassign.
        a_key, c_key = c_key, a_key
        E_a, E_c = E_c, E_a
        anode_metal, cathode_metal = cathode_metal, anode_metal
        anode_area_m2, cathode_area_m2 = cathode_area_m2, anode_area_m2

    driving_voltage = E_c - E_a  # always >= 0

    area_ratio = float(cathode_area_m2) / float(anode_area_m2)

    if area_ratio >= 100.0:
        area_note = "SEVERE: extremely unfavorable area ratio; accelerated anode attack"
    elif area_ratio >= 10.0:
        area_note = "UNFAVORABLE: high area ratio accelerates anode corrosion"
    elif area_ratio >= 2.0:
        area_note = "MODERATE: some acceleration of anode corrosion expected"
    else:
        area_note = "ACCEPTABLE: area ratio within typical design range"

    warnings: list[str] = []
    if driving_voltage > 1.0:
        warnings.append(
            f"RAPID_CORROSION: driving voltage {driving_voltage:.3f} V > 1.0 V "
            "indicates aggressive galvanic attack."
        )
    if area_ratio >= 10.0:
        warnings.append(
            f"UNFAVORABLE_AREA_RATIO: cathode/anode={area_ratio:.1f}; "
            "isolate dissimilar metals or increase anode area."
        )
    if abs(E_a - E_c) < 0.05:
        warnings.append(
            "LOW_DRIVING_VOLTAGE: metals are close in galvanic series; "
            "galvanic attack likely minimal."
        )

    return {
        "ok": True,
        "anode_metal": anode_metal,
        "cathode_metal": cathode_metal,
        "anode_potential_V_she": E_a,
        "cathode_potential_V_she": E_c,
        "driving_voltage_V": driving_voltage,
        "area_ratio": area_ratio,
        "area_effect_note": area_note,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. faraday_corrosion_rate
# ---------------------------------------------------------------------------

def faraday_corrosion_rate(
    current_density_A_m2: float,
    equivalent_weight_g_mol: float,
    density_g_cm3: float,
) -> dict:
    """
    Corrosion rate from Faraday's Law.

    Faraday's Law:  m = (i × EW × t) / (F × n) [mass per unit area per time]

    For current density i (A/m²):
        corrosion rate (g·m⁻²·d⁻¹) = i × EW / F × seconds_per_day
        penetration rate (mm/yr)    = corrosion_rate_g_m2_d × 365.25 /
                                       (density_g_cm3 × 10)

    where:
        EW = equivalent weight = molar_mass / valence  (g/mol)
        F  = Faraday constant = 96485 C/mol

    Parameters
    ----------
    current_density_A_m2 : float
        Corrosion current density (A/m²). Must be >= 0.
    equivalent_weight_g_mol : float
        Equivalent weight of the corroding metal (g/mol).
        For steel (Fe, valence=2): EW = 55.85/2 = 27.93 g/mol.
        For zinc (Zn, valence=2): EW = 65.38/2 = 32.69 g/mol.
        Must be > 0.
    density_g_cm3 : float
        Density of the corroding metal (g/cm³). Must be > 0.

    Returns
    -------
    dict
        ok                       : True
        corrosion_rate_mpy       : mils per year (1 mil = 0.0254 mm)
        corrosion_rate_mm_yr     : penetration rate (mm/yr)
        corrosion_rate_g_m2_d    : mass loss rate (g·m⁻²·d⁻¹)
        current_density_A_m2     : input current density
        equivalent_weight_g_mol  : EW used
        density_g_cm3            : density used
        warnings                 : list of warning strings

    References
    ----------
    Fontana, Corrosion Engineering (3rd ed.), eq. 3-2.
    ASTM G102-89 — Standard Practice for Calculation of Corrosion Rates.
    """
    err = _guard_nonneg("current_density_A_m2", current_density_A_m2)
    if err:
        return _err(err)
    err = _guard_positive("equivalent_weight_g_mol", equivalent_weight_g_mol)
    if err:
        return _err(err)
    err = _guard_positive("density_g_cm3", density_g_cm3)
    if err:
        return _err(err)

    i = float(current_density_A_m2)
    EW = float(equivalent_weight_g_mol)
    rho = float(density_g_cm3)

    # Mass loss rate: g·m⁻²·d⁻¹
    # i [A/m²] = i [C/(s·m²)]
    # mass_rate [g/m²/s] = i × EW / F
    # convert to g/m²/day:
    seconds_per_day = 86400.0
    rate_g_m2_d = i * EW / _FARADAY * seconds_per_day

    # Penetration rate: mm/yr
    # density rho [g/cm³] = rho × 1e6 [g/m³] / 1e3 [mm³/cm³] ... cleaner path:
    # rate_g_m2_d [g/m²/day] → rate_g_m2_yr = rate_g_m2_d × 365.25
    # thickness loss [mm/yr] = rate_g_m2_yr / (rho [g/cm³] × 1000 [mm/cm] × 100²)
    # rho [g/cm³] × (10 mm/cm)³ = rho × 1000 g/mm³ → rho [g/mm³] = rho/1000 g/mm³
    # penetration [mm/yr] = rate_g_m2_yr [g/m²/yr] / (rho [g/cm³] × 10⁴ cm²/m² × 0.1 cm/mm)
    # Simplify: pen [mm/yr] = rate_g_m2_yr / (rho × 10000)
    # where rho×10000 converts g/cm³ to g/m²/mm: 1 g/cm³ = 10 g/(cm²·mm) = 1e5 g/(m²·cm) ...
    # Use ASTM G102 formula:  CR [mm/yr] = K × i × EW / (rho × F)
    # with K = 3.27e-3 mm·g·A⁻¹·cm⁻³·yr⁻¹   (ASTM G102, SI variant)
    # K = EW_constant accounting for unit conversions
    # Direct derivation: pen [mm/yr] = rate_g_m2_d × 365.25 / (rho [g/cm³] × 1e4)
    # 1 g/cm³ = 1e-3 kg/cm³ = 1e3 kg/m³ but area in m²:
    # rho [g/cm³] × (1 cm / 10 mm) × (100 cm/m)² = rho × 1e3 g/m²/mm
    # pen [mm/yr] = rate_g_m2_yr / (rho × 1e3)
    # Check: rho = 7.87 g/cm³ steel; 1 mm/yr = 7870 g/m²/yr  ✓
    rate_g_m2_yr = rate_g_m2_d * 365.25
    pen_mm_yr = rate_g_m2_yr / (rho * 1e3) if rho > 0 else 0.0

    # mpy: 1 mm = 39.3701 mils → mpy = pen_mm_yr × 39.3701
    pen_mpy = pen_mm_yr * 39.3701

    warnings: list[str] = []
    if pen_mm_yr > 1.0:
        warnings.append(
            f"RAPID_CORROSION: penetration rate {pen_mm_yr:.3f} mm/yr > 1.0 mm/yr "
            "(high corrosion — immediate protective action recommended)."
        )
    elif pen_mm_yr > 0.25:
        warnings.append(
            f"ELEVATED_CORROSION: penetration rate {pen_mm_yr:.3f} mm/yr "
            "(moderate-high; review coating/CP system)."
        )

    return {
        "ok": True,
        "corrosion_rate_mpy": pen_mpy,
        "corrosion_rate_mm_yr": pen_mm_yr,
        "corrosion_rate_g_m2_d": rate_g_m2_d,
        "current_density_A_m2": i,
        "equivalent_weight_g_mol": EW,
        "density_g_cm3": rho,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. penetration_remaining_life
# ---------------------------------------------------------------------------

def penetration_remaining_life(
    wall_thickness_mm: float,
    corrosion_rate_mm_yr: float,
    *,
    minimum_thickness_mm: float = 0.0,
) -> dict:
    """
    Remaining life estimate from wall loss and corrosion rate.

    remaining_life [yr] = (wall_thickness − minimum_thickness) / corrosion_rate

    Parameters
    ----------
    wall_thickness_mm : float
        Current (measured) wall thickness (mm). Must be > 0.
    corrosion_rate_mm_yr : float
        Corrosion (penetration) rate (mm/yr). Must be >= 0.
    minimum_thickness_mm : float
        Minimum acceptable remaining wall thickness (mm). Default 0.0.
        Must be >= 0 and < wall_thickness_mm.

    Returns
    -------
    dict
        ok                       : True
        remaining_life_yr        : estimated years until minimum thickness reached
                                   (inf if corrosion_rate = 0)
        wall_thickness_mm        : input value
        minimum_thickness_mm     : minimum threshold used
        available_loss_mm        : wall_thickness − minimum_thickness
        corrosion_rate_mm_yr     : rate used
        warnings                 : list of warning strings
    """
    err = _guard_positive("wall_thickness_mm", wall_thickness_mm)
    if err:
        return _err(err)
    err = _guard_nonneg("corrosion_rate_mm_yr", corrosion_rate_mm_yr)
    if err:
        return _err(err)
    err = _guard_nonneg("minimum_thickness_mm", minimum_thickness_mm)
    if err:
        return _err(err)

    t = float(wall_thickness_mm)
    r = float(corrosion_rate_mm_yr)
    t_min = float(minimum_thickness_mm)

    if t_min >= t:
        return _err(
            f"minimum_thickness_mm ({t_min}) must be less than "
            f"wall_thickness_mm ({t})."
        )

    available = t - t_min
    remaining_life = available / r if r > 0 else float("inf")

    warnings: list[str] = []
    if remaining_life < 5.0 and math.isfinite(remaining_life):
        warnings.append(
            f"RAPID_CORROSION: estimated remaining life {remaining_life:.2f} yr < 5 yr; "
            "inspect and repair immediately."
        )
    elif remaining_life < 10.0 and math.isfinite(remaining_life):
        warnings.append(
            f"SHORT_REMAINING_LIFE: {remaining_life:.2f} yr remaining; "
            "schedule inspection and CP review."
        )

    return {
        "ok": True,
        "remaining_life_yr": remaining_life,
        "wall_thickness_mm": t,
        "minimum_thickness_mm": t_min,
        "available_loss_mm": available,
        "corrosion_rate_mm_yr": r,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. sacrificial_anode_demand
# ---------------------------------------------------------------------------

def sacrificial_anode_demand(
    bare_area_m2: float,
    coating_efficiency: float,
    current_density_mA_m2: float,
) -> dict:
    """
    Total cathodic protection current demand for a coated structure.

    The total current required accounts for:
      - The bare (uncoated) fraction of the structure (worst-case coating breakdown)
      - The protective current density for cathodic protection

    I_total [A] = bare_area_m2 × (1 − coating_efficiency) × current_density_A_m2
                + bare_area_m2 × coating_efficiency ... no: simplified model:

    I_total [A] = bare_area_m2 × (1 − coating_efficiency) × i_c [A/m²]

    Here (1 − coating_efficiency) is the fraction of bare or holiday-exposed
    steel, and i_c is the design current density (typically 10–150 mA/m² for
    bare steel per NACE SP0169 / DNV-RP-B401).

    Parameters
    ----------
    bare_area_m2 : float
        Total structure surface area (m²). Must be > 0.
    coating_efficiency : float
        Fraction of area protected by intact coating [0, 1].
        1.0 = fully coated (no current needed); 0.0 = fully bare.
    current_density_mA_m2 : float
        Design cathodic protection current density for bare steel (mA/m²).
        Typical: 10–50 mA/m² buried; 50–150 mA/m² submerged. Must be > 0.

    Returns
    -------
    dict
        ok                     : True
        total_current_A        : total protection current required (A)
        total_current_mA       : same in mA
        effective_bare_area_m2 : bare_area_m2 × (1 − coating_efficiency)
        current_density_A_m2   : design current density (A/m²)
        coating_efficiency     : fraction used
        warnings               : list of warning strings
    """
    err = _guard_positive("bare_area_m2", bare_area_m2)
    if err:
        return _err(err)
    err = _guard_fraction("coating_efficiency", coating_efficiency)
    if err:
        return _err(err)
    err = _guard_positive("current_density_mA_m2", current_density_mA_m2)
    if err:
        return _err(err)

    A = float(bare_area_m2)
    ce = float(coating_efficiency)
    i_c = float(current_density_mA_m2) * 1e-3  # convert to A/m²

    effective_bare = A * (1.0 - ce)
    I_total = effective_bare * i_c

    warnings: list[str] = []
    if ce < 0.5:
        warnings.append(
            f"UNDER_PROTECTED: coating efficiency {ce:.0%} < 50%; "
            "high bare area increases CP current demand significantly."
        )
    if i_c > 0.15:
        warnings.append(
            f"HIGH_CURRENT_DENSITY: {i_c * 1000:.1f} mA/m² > 150 mA/m²; "
            "verify environment and coating condition."
        )

    return {
        "ok": True,
        "total_current_A": I_total,
        "total_current_mA": I_total * 1e3,
        "effective_bare_area_m2": effective_bare,
        "current_density_A_m2": i_c,
        "coating_efficiency": ce,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. anode_mass_design_life
# ---------------------------------------------------------------------------

def anode_mass_design_life(
    current_A: float,
    design_life_yr: float,
    *,
    utilisation_factor: float = 0.85,
    anode_type: str = "aluminum",
) -> dict:
    """
    Net mass of sacrificial anode material required for a design life.

    M_net [kg] = (I [A] × T [yr] × 8760 [h/yr]) / (u × C [A·h/kg])

    where:
        u = utilisation factor (fraction of anode consumed at end of life)
        C = electrochemical capacity of the anode alloy (A·h/kg)

    Parameters
    ----------
    current_A : float
        Total protection current required (A). Must be > 0.
    design_life_yr : float
        Required service life (years). Must be > 0.
    utilisation_factor : float
        Fraction of anode mass consumed at end of life.
        Typical: 0.80–0.90 (DNV-RP-B401 default 0.85). Must be in (0, 1].
    anode_type : str
        Sacrificial anode alloy: 'zinc', 'magnesium', or 'aluminum' (default).

    Returns
    -------
    dict
        ok                  : True
        anode_mass_net_kg   : net anode mass required (kg)
        current_A           : protection current used (A)
        design_life_yr      : design life used
        utilisation_factor  : factor used
        anode_type          : alloy name
        capacity_Ah_kg      : electrochemical capacity of the anode (A·h/kg)
        warnings            : list of warning strings

    References
    ----------
    DNV-RP-B401:2021, Section 6.
    """
    err = _guard_positive("current_A", current_A)
    if err:
        return _err(err)
    err = _guard_positive("design_life_yr", design_life_yr)
    if err:
        return _err(err)

    u = float(utilisation_factor)
    if not (0.0 < u <= 1.0):
        return _err(f"utilisation_factor must be in (0, 1], got {u}")

    at = str(anode_type).strip().lower()
    if at not in _ANODE_DATA:
        return _err(
            f"anode_type {anode_type!r} not supported. "
            f"Supported: {list(_ANODE_DATA.keys())}"
        )

    I = float(current_A)
    T = float(design_life_yr)
    C = _ANODE_DATA[at]["capacity_Ah_kg"]

    hours = T * 8760.0
    M_net = (I * hours) / (u * C)

    warnings: list[str] = []
    if M_net > 1e4:
        warnings.append(
            f"LARGE_ANODE_MASS: {M_net:.1f} kg required; verify current demand and "
            "consider ICCP (impressed current) system."
        )
    if design_life_yr > 30.0:
        warnings.append(
            f"LONG_DESIGN_LIFE: {design_life_yr} yr; re-assess anode consumption "
            "at periodic inspection intervals."
        )

    return {
        "ok": True,
        "anode_mass_net_kg": M_net,
        "current_A": I,
        "design_life_yr": T,
        "utilisation_factor": u,
        "anode_type": at,
        "capacity_Ah_kg": C,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 6. anode_count_dwight
# ---------------------------------------------------------------------------

def anode_count_dwight(
    total_current_A: float,
    anode_length_m: float,
    anode_radius_m: float,
    soil_resistivity_ohm_m: float,
    driving_voltage_V: float,
    *,
    burial_depth_m: float = 1.0,
) -> dict:
    """
    Number of sacrificial anodes from Dwight (vertical rod) formula for
    groundbed resistance and per-anode current output.

    Dwight formula for a single vertical rod anode:
        R_a = (rho / (2π L)) × (ln(4L/r) − 1 + 2L/4s × ln((4s+L)/(4s−L)))

    Simplified for deeply buried anode (burial_depth >> length):
        R_a ≈ (rho / (2π L)) × (ln(8L/d) − 1)

    where:
        rho = soil resistivity (Ω·m)
        L   = anode length (m)
        d   = anode diameter = 2r (m)
        (Dwight 1936; McCoy approximation)

    Current per anode:
        I_anode = driving_voltage / R_a

    Number of anodes (conservative — parallel resistance ignored):
        N = ceil(total_current / I_anode)

    Parameters
    ----------
    total_current_A : float
        Total CP current required (A). Must be > 0.
    anode_length_m : float
        Individual anode length (m). Must be > 0.
    anode_radius_m : float
        Individual anode radius (m) = diameter / 2. Must be > 0.
    soil_resistivity_ohm_m : float
        Soil (or seawater) resistivity (Ω·m). Must be > 0.
    driving_voltage_V : float
        Net driving voltage = E_anode − E_structure (V). Must be > 0.
    burial_depth_m : float
        Anode burial depth (m). Default 1.0. Used for deep-burial check.

    Returns
    -------
    dict
        ok                       : True
        anode_resistance_ohm     : Dwight single-anode resistance (Ω)
        current_per_anode_A      : current output of one anode (A)
        n_anodes                 : number of anodes required (integer)
        total_current_A          : input protection current
        driving_voltage_V        : input driving voltage
        soil_resistivity_ohm_m   : input resistivity
        warnings                 : list of warning strings

    References
    ----------
    Dwight, H.B. (1936). "Calculations of resistances to ground."
    AIEE Trans., 55, 1319–1328.
    Peabody, Control of Pipeline Corrosion (NACE, 2001), Chapter 4.
    """
    err = _guard_positive("total_current_A", total_current_A)
    if err:
        return _err(err)
    err = _guard_positive("anode_length_m", anode_length_m)
    if err:
        return _err(err)
    err = _guard_positive("anode_radius_m", anode_radius_m)
    if err:
        return _err(err)
    err = _guard_positive("soil_resistivity_ohm_m", soil_resistivity_ohm_m)
    if err:
        return _err(err)
    err = _guard_positive("driving_voltage_V", driving_voltage_V)
    if err:
        return _err(err)
    err = _guard_positive("burial_depth_m", burial_depth_m)
    if err:
        return _err(err)

    I_total = float(total_current_A)
    L = float(anode_length_m)
    r = float(anode_radius_m)
    d = 2.0 * r
    rho = float(soil_resistivity_ohm_m)
    E_drive = float(driving_voltage_V)

    # Dwight formula: R = rho/(2πL) × (ln(8L/d) − 1)  [simplified, deep burial]
    if d <= 0 or L <= 0 or (8.0 * L / d) <= math.e:
        return _err(
            "Anode dimensions are too small for Dwight formula to apply."
        )

    R_a = (rho / (2.0 * math.pi * L)) * (math.log(8.0 * L / d) - 1.0)

    if R_a <= 0:
        return _err(
            f"Computed anode resistance R_a={R_a:.4f} Ω is non-positive; "
            "check anode dimensions."
        )

    I_per_anode = E_drive / R_a
    n_anodes = math.ceil(I_total / I_per_anode) if I_per_anode > 0 else 0

    warnings: list[str] = []
    if rho < 2.0:
        warnings.append(
            f"LOW_RESISTIVITY: soil resistivity {rho:.2f} Ω·m (seawater range); "
            "confirm environment is seawater and use appropriate current density."
        )
    if rho > 100.0:
        warnings.append(
            f"HIGH_RESISTIVITY: soil resistivity {rho:.1f} Ω·m; "
            "galvanic system may be ineffective — consider ICCP."
        )
    if n_anodes > 100:
        warnings.append(
            f"LARGE_ANODE_COUNT: {n_anodes} anodes required; "
            "consider impressed-current cathodic protection (ICCP)."
        )
    if I_per_anode < 0.01:
        warnings.append(
            "UNDER_PROTECTED: very low current per anode; "
            "check resistivity and driving voltage."
        )

    return {
        "ok": True,
        "anode_resistance_ohm": R_a,
        "current_per_anode_A": I_per_anode,
        "n_anodes": n_anodes,
        "total_current_A": I_total,
        "driving_voltage_V": E_drive,
        "soil_resistivity_ohm_m": rho,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. iccp_sizing
# ---------------------------------------------------------------------------

def iccp_sizing(
    protected_area_m2: float,
    coating_efficiency: float,
    current_density_mA_m2: float,
    groundbed_resistance_ohm: float,
    *,
    safety_factor: float = 1.25,
    attenuation_factor: float = 1.0,
) -> dict:
    """
    Impressed current cathodic protection (ICCP) rectifier sizing.

    Design current:
        I_design = (protected_area × (1 − coating_efficiency) ×
                    current_density) × safety_factor × attenuation_factor

    Rectifier voltage:
        V_rect = I_design × (R_groundbed + R_cable_approx)
                 (with a minimum of 12 V for typical rectifiers)

    The minimum voltage accounts for back-EMF from anode potential
    and pipe-to-electrolyte potential differences (simplified model).

    Parameters
    ----------
    protected_area_m2 : float
        Total structure surface area (m²). Must be > 0.
    coating_efficiency : float
        Fraction of area with intact coating [0, 1].
    current_density_mA_m2 : float
        Design current density for bare steel (mA/m²). Must be > 0.
    groundbed_resistance_ohm : float
        Total groundbed-to-electrolyte resistance (Ω). Must be > 0.
    safety_factor : float
        Safety factor applied to current demand (default 1.25). Must be >= 1.
    attenuation_factor : float
        Factor > 1.0 to account for current attenuation on long pipelines
        (default 1.0 = no attenuation). Must be >= 1.

    Returns
    -------
    dict
        ok                       : True
        rectifier_current_A      : required rectifier output current (A)
        rectifier_voltage_V      : required rectifier output voltage (V)
        design_current_A         : current demand before safety factor
        effective_bare_area_m2   : area × (1 − coating_efficiency)
        groundbed_resistance_ohm : resistance used
        warnings                 : list of warning strings
    """
    err = _guard_positive("protected_area_m2", protected_area_m2)
    if err:
        return _err(err)
    err = _guard_fraction("coating_efficiency", coating_efficiency)
    if err:
        return _err(err)
    err = _guard_positive("current_density_mA_m2", current_density_mA_m2)
    if err:
        return _err(err)
    err = _guard_positive("groundbed_resistance_ohm", groundbed_resistance_ohm)
    if err:
        return _err(err)

    sf = float(safety_factor)
    if sf < 1.0:
        return _err(f"safety_factor must be >= 1.0, got {sf}")
    af = float(attenuation_factor)
    if af < 1.0:
        return _err(f"attenuation_factor must be >= 1.0, got {af}")

    A = float(protected_area_m2)
    ce = float(coating_efficiency)
    i_c = float(current_density_mA_m2) * 1e-3  # A/m²
    R_gb = float(groundbed_resistance_ohm)

    effective_bare = A * (1.0 - ce)
    I_demand = effective_bare * i_c
    I_design = I_demand * sf * af

    # Voltage: V = I × R + V_back_emf
    # Simplified: back-EMF ≈ 2V (typical anode-to-steel potential difference)
    V_back_emf = 2.0
    V_rect = I_design * R_gb + V_back_emf
    # Minimum practical rectifier voltage
    V_rect = max(V_rect, 12.0)

    warnings: list[str] = []
    if ce < 0.5:
        warnings.append(
            f"UNDER_PROTECTED: coating efficiency {ce:.0%} < 50%; "
            "large current demand — inspect and repair coating."
        )
    if I_design > 100.0:
        warnings.append(
            f"HIGH_CURRENT: rectifier current {I_design:.1f} A; "
            "consider multiple rectifier units."
        )
    if V_rect > 50.0:
        warnings.append(
            f"HIGH_VOLTAGE: rectifier voltage {V_rect:.1f} V; "
            "verify groundbed resistance and cable sizing."
        )
    if I_design < 0.5:
        warnings.append(
            f"OVER_PROTECTION: very low current demand {I_design:.3f} A; "
            "verify coating efficiency and area inputs."
        )

    return {
        "ok": True,
        "rectifier_current_A": I_design,
        "rectifier_voltage_V": V_rect,
        "design_current_A": I_demand,
        "effective_bare_area_m2": effective_bare,
        "groundbed_resistance_ohm": R_gb,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 8. pourbaix_region
# ---------------------------------------------------------------------------

# Simplified Pourbaix region boundaries for iron (Fe) in water at 25 °C.
# Corrosion boundary: E > -0.059 × pH − 0.44  (approx. Fe/Fe²⁺ line)
# Passivity boundary: E > -0.059 × pH + 0.059 (approx. Fe₂O₃/Fe²⁺ line)
# Immunity:  E < Fe/Fe²⁺ lower boundary
# For other metals, boundaries are shifted; a simplified lookup is used.

# Boundaries vs SHE for selected metals at 25 °C (simplified)
# Format: (immune_upper_V_at_pH7, passive_lower_V_at_pH7, corrosion_lower_V_at_pH7)
_POURBAIX_PARAMS: dict[str, dict] = {
    "iron": {
        # Fe: immune below −0.62 V SHE at pH 7; passive −0.62 to ~+0.0 V at pH 7
        "immune_upper_slope": -0.059,
        "immune_upper_intercept": -0.44,
        "passive_lower_slope": -0.059,
        "passive_lower_intercept": -0.44,
        "passive_upper_slope": 0.0,
        "passive_upper_intercept": 0.59,
    },
    "steel": {  # same as iron
        "immune_upper_slope": -0.059,
        "immune_upper_intercept": -0.44,
        "passive_lower_slope": -0.059,
        "passive_lower_intercept": -0.44,
        "passive_upper_slope": 0.0,
        "passive_upper_intercept": 0.59,
    },
    "zinc": {
        # Zn: immune below ~−1.0 V at pH 7
        "immune_upper_slope": -0.059,
        "immune_upper_intercept": -0.59,
        "passive_lower_slope": -0.059,
        "passive_lower_intercept": -0.59,
        "passive_upper_slope": -0.059,
        "passive_upper_intercept": 0.0,
    },
    "aluminum": {
        # Al: passive in mid-pH range; corrodes in acidic and alkaline
        "immune_upper_slope": -0.059,
        "immune_upper_intercept": -1.67,
        "passive_lower_slope": -0.059,
        "passive_lower_intercept": -1.67,
        "passive_upper_slope": -0.059,
        "passive_upper_intercept": -1.1,
    },
    "copper": {
        # Cu: noble; immune at low potentials
        "immune_upper_slope": 0.0,
        "immune_upper_intercept": 0.34,
        "passive_lower_slope": 0.0,
        "passive_lower_intercept": 0.34,
        "passive_upper_slope": 0.0,
        "passive_upper_intercept": 0.70,
    },
}


def pourbaix_region(
    potential_V_she: float,
    pH: float,
    *,
    metal: str = "iron",
) -> dict:
    """
    Simplified Pourbaix (E-pH) diagram region classification.

    Classifies the operating point (E, pH) as:
      - 'immune'   : thermodynamically stable metal; corrosion cannot occur
      - 'passive'  : stable oxide/hydroxide film; corrosion kinetically inhibited
      - 'corrosion': active dissolution; corrosion likely

    Uses simplified linear boundary lines from standard Pourbaix diagrams at
    25 °C (ambient temperature). Not valid for elevated temperature.

    Parameters
    ----------
    potential_V_she : float
        Electrode potential vs SHE (V). Finite number required.
    pH : float
        Solution pH. Must be in [0, 14].
    metal : str
        Metal: 'iron'/'steel' (default), 'zinc', 'aluminum', or 'copper'.

    Returns
    -------
    dict
        ok       : True
        region   : 'immune', 'passive', or 'corrosion'
        potential_V_she : input potential
        pH       : input pH
        metal    : metal used
        note     : brief explanation
        warnings : list of warning strings
    """
    try:
        E = float(potential_V_she)
    except (TypeError, ValueError):
        return _err(f"potential_V_she must be a number, got {potential_V_she!r}")
    if not math.isfinite(E):
        return _err(f"potential_V_she must be finite, got {E}")

    try:
        ph = float(pH)
    except (TypeError, ValueError):
        return _err(f"pH must be a number, got {pH!r}")
    if not (0.0 <= ph <= 14.0):
        return _err(f"pH must be in [0, 14], got {ph}")

    m_key = str(metal).strip().lower()
    if m_key not in _POURBAIX_PARAMS:
        return _err(
            f"metal {metal!r} not supported. "
            f"Supported: {list(_POURBAIX_PARAMS.keys())}"
        )

    p = _POURBAIX_PARAMS[m_key]

    # Boundary potentials at the given pH
    E_immune_upper = p["immune_upper_slope"] * ph + p["immune_upper_intercept"]
    E_passive_upper = p["passive_upper_slope"] * ph + p["passive_upper_intercept"]

    warnings: list[str] = []

    if E < E_immune_upper:
        region = "immune"
        note = (
            f"E={E:.3f} V < E_immune_upper={E_immune_upper:.3f} V at pH {ph:.1f}; "
            "metal is thermodynamically stable — no corrosion."
        )
    elif E < E_passive_upper:
        region = "passive"
        note = (
            f"E_immune_upper={E_immune_upper:.3f} V <= E={E:.3f} V < "
            f"E_passive_upper={E_passive_upper:.3f} V at pH {ph:.1f}; "
            "stable oxide film expected — corrosion kinetically inhibited."
        )
    else:
        region = "corrosion"
        note = (
            f"E={E:.3f} V >= E_passive_upper={E_passive_upper:.3f} V at pH {ph:.1f}; "
            "active dissolution region — corrosion likely."
        )
        warnings.append(
            "CORROSION_REGION: operating point lies in active dissolution zone; "
            "apply CP or change operating conditions."
        )

    # Check for over-protection (H2 evolution risk for steel)
    if m_key in ("iron", "steel") and E < _STEEL_OVERPROTECTION_POTENTIAL_SHE:
        warnings.append(
            f"OVER_PROTECTION: E={E:.3f} V < {_STEEL_OVERPROTECTION_POTENTIAL_SHE} V SHE; "
            "risk of hydrogen embrittlement in high-strength steels."
        )

    return {
        "ok": True,
        "region": region,
        "potential_V_she": E,
        "pH": ph,
        "metal": m_key,
        "note": note,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 9. corrosivity_category
# ---------------------------------------------------------------------------

# Soil corrosivity classification by resistivity (NACE SP0169 / BS EN ISO 12944)
# Resistivity ranges (Ω·m) and corrosivity class
_SOIL_RESISTIVITY_CATEGORIES = [
    (0.0,   2.0,   "C5", "Extremely corrosive (seawater/saturated soil)"),
    (2.0,   10.0,  "C4", "Very corrosive (wet, low-resistivity soil)"),
    (10.0,  30.0,  "C3", "Moderately corrosive"),
    (30.0,  100.0, "C2", "Mildly corrosive"),
    (100.0, float("inf"), "C1", "Low corrosivity (dry/high-resistivity)"),
]

# Atmospheric corrosivity categories (ISO 9223 / ISO 12944)
_ATMOSPHERIC_CATEGORIES = {
    "rural":             "C2",
    "urban":             "C3",
    "industrial":        "C4",
    "marine":            "C4",
    "offshore":          "C5",
    "tropical_marine":   "C5",
    "severe_industrial": "C5",
    "indoor_dry":        "C1",
}


def corrosivity_category(
    soil_resistivity_ohm_m: float | None = None,
    *,
    environment: str | None = None,
) -> dict:
    """
    Corrosivity category from soil resistivity or atmospheric environment.

    Either soil_resistivity_ohm_m or environment must be supplied.

    If soil_resistivity_ohm_m is provided, classifies per NACE SP0169 / ASTM
    resistivity-based corrosivity table.

    If environment is provided, classifies per ISO 12944 atmospheric corrosivity
    categories.

    Parameters
    ----------
    soil_resistivity_ohm_m : float or None
        Soil resistivity (Ω·m). Must be >= 0 if provided.
    environment : str or None
        Atmospheric environment type. One of:
        'rural', 'urban', 'industrial', 'marine', 'offshore',
        'tropical_marine', 'severe_industrial', 'indoor_dry'.

    Returns
    -------
    dict
        ok                     : True
        corrosivity_category   : ISO 12944 category string (C1–C5)
        description            : human-readable description
        basis                  : 'soil_resistivity' or 'atmosphere'
        soil_resistivity_ohm_m : resistivity used (None for atmosphere)
        environment            : environment string (None for soil)
        warnings               : list of warning strings
    """
    if soil_resistivity_ohm_m is None and environment is None:
        return _err(
            "Either soil_resistivity_ohm_m or environment must be provided."
        )
    if soil_resistivity_ohm_m is not None and environment is not None:
        return _err(
            "Provide either soil_resistivity_ohm_m or environment, not both."
        )

    warnings: list[str] = []

    if soil_resistivity_ohm_m is not None:
        err = _guard_nonneg("soil_resistivity_ohm_m", soil_resistivity_ohm_m)
        if err:
            return _err(err)
        rho = float(soil_resistivity_ohm_m)
        cat = "C1"
        desc = "Unknown"
        for lo, hi, c, d in _SOIL_RESISTIVITY_CATEGORIES:
            if lo <= rho < hi:
                cat = c
                desc = d
                break
        if rho == 0.0:
            cat = "C5"
            desc = "Extremely corrosive (seawater/saturated soil)"

        if cat in ("C4", "C5"):
            warnings.append(
                f"HIGH_CORROSIVITY: soil resistivity {rho:.1f} Ω·m → category {cat}; "
                "CP and/or protective coating is essential."
            )

        return {
            "ok": True,
            "corrosivity_category": cat,
            "description": desc,
            "basis": "soil_resistivity",
            "soil_resistivity_ohm_m": rho,
            "environment": None,
            "warnings": warnings,
        }

    else:
        env_key = str(environment).strip().lower().replace(" ", "_").replace("-", "_")
        if env_key not in _ATMOSPHERIC_CATEGORIES:
            return _err(
                f"environment {environment!r} not supported. "
                f"Supported: {list(_ATMOSPHERIC_CATEGORIES.keys())}"
            )
        cat = _ATMOSPHERIC_CATEGORIES[env_key]

        descriptions = {
            "C1": "Very low corrosivity (indoor/dry)",
            "C2": "Low corrosivity (rural/inland)",
            "C3": "Medium corrosivity (urban/industrial, moderate humidity)",
            "C4": "High corrosivity (industrial/marine)",
            "C5": "Very high corrosivity (marine/severe industrial)",
        }
        desc = descriptions.get(cat, cat)

        if cat in ("C4", "C5"):
            warnings.append(
                f"HIGH_CORROSIVITY: {environment} environment → category {cat}; "
                "use high-performance coating system and CP where appropriate."
            )

        return {
            "ok": True,
            "corrosivity_category": cat,
            "description": desc,
            "basis": "atmosphere",
            "soil_resistivity_ohm_m": None,
            "environment": env_key,
            "warnings": warnings,
        }


# ---------------------------------------------------------------------------
# 10. coating_breakdown_factor
# ---------------------------------------------------------------------------

def coating_breakdown_factor(
    age_yr: float,
    design_life_yr: float,
    *,
    initial_breakdown_frac: float = 0.01,
    final_breakdown_frac: float = 0.05,
) -> dict:
    """
    Time-varying coating breakdown factor for CP current demand.

    The coating breakdown factor (CBF) represents the fraction of bare (holiday-
    exposed) steel area at a given point in time.  It increases linearly from
    an initial value at commissioning to a final value at end of design life,
    as assumed by DNV-RP-B401 and ISO 15589-1.

    CBF(t) = CBF_initial + (CBF_final − CBF_initial) × (t / T_design)

    The mean breakdown factor used for average current demand over the design life:
        CBF_mean = (CBF_initial + CBF_final) / 2

    Parameters
    ----------
    age_yr : float
        Current age of the coating (years). Must be >= 0.
    design_life_yr : float
        Total design life of the coating (years). Must be > 0.
    initial_breakdown_frac : float
        Coating breakdown fraction at time zero (default 0.01 = 1%).
        Must be in [0, 1].
    final_breakdown_frac : float
        Coating breakdown fraction at end of design life (default 0.05 = 5%).
        Must be in [0, 1] and >= initial_breakdown_frac.

    Returns
    -------
    dict
        ok                      : True
        breakdown_factor        : CBF at age_yr (fraction bare)
        mean_breakdown_factor   : average CBF over design life
        age_yr                  : age used
        design_life_yr          : design life used
        initial_breakdown_frac  : initial fraction
        final_breakdown_frac    : final fraction
        fraction_life_consumed  : age_yr / design_life_yr
        warnings                : list of warning strings

    References
    ----------
    DNV-RP-B401:2021, Table 10-1.
    ISO 15589-1:2015, Annex A.
    """
    err = _guard_nonneg("age_yr", age_yr)
    if err:
        return _err(err)
    err = _guard_positive("design_life_yr", design_life_yr)
    if err:
        return _err(err)
    err = _guard_fraction("initial_breakdown_frac", initial_breakdown_frac)
    if err:
        return _err(err)
    err = _guard_fraction("final_breakdown_frac", final_breakdown_frac)
    if err:
        return _err(err)

    cbf_i = float(initial_breakdown_frac)
    cbf_f = float(final_breakdown_frac)

    if cbf_f < cbf_i:
        return _err(
            f"final_breakdown_frac ({cbf_f}) must be >= "
            f"initial_breakdown_frac ({cbf_i})."
        )

    t = float(age_yr)
    T = float(design_life_yr)

    frac_life = min(t / T, 1.0)  # clamp at end of life
    cbf = cbf_i + (cbf_f - cbf_i) * frac_life
    cbf_mean = (cbf_i + cbf_f) / 2.0

    warnings: list[str] = []
    if t > T:
        warnings.append(
            f"COATING_EXPIRED: age {t:.1f} yr exceeds design life {T:.1f} yr; "
            "coating breakdown factor clamped at final value — inspect immediately."
        )
    if cbf > 0.10:
        warnings.append(
            f"HIGH_BREAKDOWN: CBF={cbf:.1%} > 10%; "
            "coating in poor condition — repair or replace before continuing."
        )

    return {
        "ok": True,
        "breakdown_factor": cbf,
        "mean_breakdown_factor": cbf_mean,
        "age_yr": t,
        "design_life_yr": T,
        "initial_breakdown_frac": cbf_i,
        "final_breakdown_frac": cbf_f,
        "fraction_life_consumed": frac_life,
        "warnings": warnings,
    }
