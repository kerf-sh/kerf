"""
Electrical safety, grounding, isolation and arc-flash engineering calculations.

This module is distinct from:
  • kerf_electronics.protection  — fuses, TVS, MOV (circuit-level protection)
  • kerf_electronics.pdn         — power-delivery network (IR-drop, decap)
  • kerf_electronics.gatedrive   — gate-drive circuitry

Covered topics
--------------
protective_earth_conductor_size
    Protective-earth / equipment-grounding conductor (EGC) minimum cross-sectional
    area using the adiabatic equation from IEC 60364-5-54 / IEEE 141:
        A [mm²] = I × √t / k
    where k is a material constant (copper = 115, aluminium = 76, steel = 52).

bonding_resistance_check
    Bonding conductor resistance check against IEC 60364-4-41 / NEC 250.122.
    GPR = I_fault × R_bond; flag when GPR exceeds safe-touch 50 V limit.

ground_electrode_resistance
    Resistance of a single vertical ground rod (Dwight), plate electrode, or
    Schwarz grid (IEEE 80-2013 §14):
        Rod:   R = ρ/(2πL) × [ln(4L/a) − 1]
        Plate: R = ρ/(8r)   (circular plate, radius r = √(area/π))
        Grid:  Schwarz formula (IEEE 80 §14.2)

ground_potential_rise
    GPR = I_fault × R_ground_electrode.  Flag when GPR > 1000 V (IEEE 80
    hazardous GPR threshold) or when GPR > 5 kV.

touch_step_voltage
    Permissible touch voltage (V_touch) and step voltage (V_step) for a
    human body model (IEC 60479-1 / IEEE 80-2013 §8):
        V_touch_permissible = (1000 + 1.5 × ρs) × I_body
        V_step_permissible  = (1000 + 6 × ρs)   × I_body
    Permissible body current I_body per IEC 60479-1 fibrillation threshold
    (50 kg person, 0.116 A·s^0.5 curve):
        I_body_A = 0.116 / √t_s

creepage_clearance
    Minimum creepage distance and clearance from IEC 60664-1:2007 (and
    Amendment 1) for a given working voltage (peak or RMS), pollution degree
    (1–4), overvoltage category (I–IV), material group (I, II, IIIa, IIIb),
    and altitude (altitude correction factor per IEC 60664-1 Annex A).
    Returns pass/fail flag vs supplied creepage and clearance values.

insulation_hipot
    Basic insulation / reinforced insulation test voltage (Hi-pot) from
    IEC 60664-1 Table F.4 and IEC 62368-1 Annex Q.  Also covers SELV/PELV
    boundary test voltages.

leakage_touch_current_limit
    Permissible leakage / touch current for IEC 60601-1 (medical) and
    IEC 60950-1 / IEC 62368-1 (IT equipment) device classes:
        Class I: earth leakage, touch current, patient leakage (60601)
        Class II: touch current only (60601/60950)
        Class III: SELV, no relevant leakage limit

rcd_gfci_threshold
    RCD / GFCI trip threshold check: verify that measured earth leakage
    current is safely below the device trip level (IEC 61008, UL 943).
    Returns expected trip classification and safety margin.

arc_flash_incident_energy
    Simplified arc-flash incident energy and arc-flash boundary from
    IEEE 1584-2002 Lee equation (empirical open-air model):
        E [J/cm²] = 4.184 × Cf × En × (t/0.2) × (610^x / D^x)
    plus the theoretical maximum (Lee) formula:
        E_Lee = 2.142e6 × V × I_bf × t / D²
    Incident energy category per NFPA 70E Table 130.7(C)(15)(a) and
    arc-flash boundary distance.

wire_ampacity
    Wire ampacity vs insulation temperature rating and application derating:
        Copper: base ampacity from IEC 60228 / NEC 310 simplified tables
        Temperature derating: I_derated = I_base × √((T_max − T_amb)/(T_max − T_ref))
    Insulation types: PVC (70°C), XLPE (90°C), PTFE (200°C), silicone (180°C).
    Returns OVERLOADED warning when load current exceeds derated ampacity.

selv_pelv_check
    SELV / PELV threshold check per IEC 61140 / IEC 60364-4-41:
        SELV: ≤ 50 V AC peak / 120 V DC (ripple-free)
        PELV: same voltage limits, protective earth connected
    Returns the applicable class and a flag when voltage is borderline.

All functions are pure Python (math module only) and follow the kerf
never-raise contract: validation errors are returned as dicts with
{ok: False, reason: str}; hazard flags are reported via warnings.warn;
exceptions are never raised to callers.

References
----------
IEC 60364-5-54:2011  — Earthing arrangements and protective conductors
IEC 60664-1:2007+A1  — Insulation coordination for low-voltage equipment
IEC 60479-1:2005     — Effects of current on human beings
IEC 61140:2016       — Protection against electric shock
IEC 60601-1:2005+A1  — Medical electrical equipment safety (leakage)
IEC 60950-1 / 62368-1 — IT equipment safety
IEC 61008:2010       — RCDs for household use
IEEE 80-2013         — Guide for safety in AC substation grounding
IEEE 1584-2002       — IEEE Guide for performing arc-flash hazard calculations
NFPA 70E-2021        — Standard for electrical safety in the workplace
NEC 310 (2020)       — Conductors for general wiring

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import Optional

# ── Physical / material constants ─────────────────────────────────────────────

# Adiabatic constant k for conductor materials (IEC 60364-5-54 Table 54.2)
_K_COPPER = 115.0       # A·s^0.5 / mm²  — PVC-insulated copper
_K_ALUMINIUM = 76.0     # A·s^0.5 / mm²  — PVC-insulated aluminium
_K_STEEL = 52.0         # A·s^0.5 / mm²  — steel conductor

# IEC 60479-1 fibrillation constant for 50 kg body (0.116 A·√s curve, LF AC)
_IEC60479_C1 = 0.116    # A·s^0.5  (50 kg, AC 15–100 Hz body current threshold)

# Human body resistance (hand-to-foot, IEC 60479-1 Table 1 at 50th percentile)
_R_BODY = 1000.0        # Ω  (used in touch/step voltage permissible calcs)

# Safe touch voltage thresholds (IEC 60364-4-41)
_SAFE_TOUCH_AC = 50.0   # V AC RMS
_SAFE_TOUCH_DC = 120.0  # V DC (ripple-free)

# GPR hazard thresholds (IEEE 80)
_GPR_HAZARD_LOW  = 1000.0   # V — additional precautions required
_GPR_HAZARD_HIGH = 5000.0   # V — extreme hazard

# NFPA 70E arc-flash PPE categories (incident energy boundaries J/cm²)
_AF_CATEGORY_LIMITS = [
    (1,  1.2,   4.0),    # Cat 1: 1.2–4 J/cm²
    (2,  4.0,   12.0),   # Cat 2: 4–12 J/cm²
    (3,  12.0,  40.0),   # Cat 3: 12–40 J/cm²
    (4,  40.0,  167.0),  # Cat 4: 40–167 J/cm²
]
_AF_UNRATED = 167.0  # J/cm² — above Cat 4 (untestable / de-energise)

# Wire ampacity base table for copper, 60°C ambient reference, insulation T_max
# Format: (cross_section_mm2, ampacity_A)
# Simplified from IEC 60228 / NEC 310.15(B)(16)
_COPPER_AMPACITY = [
    (0.5,   3.0),
    (0.75,  6.0),
    (1.0,   10.0),
    (1.5,   13.0),
    (2.5,   18.0),
    (4.0,   25.0),
    (6.0,   32.0),
    (10.0,  44.0),
    (16.0,  58.0),
    (25.0,  76.0),
    (35.0,  94.0),
    (50.0,  117.0),
    (70.0,  149.0),
    (95.0,  180.0),
    (120.0, 207.0),
    (150.0, 237.0),
    (185.0, 271.0),
    (240.0, 321.0),
    (300.0, 369.0),
]

# Insulation temperature ratings
_INSULATION_TMAX = {
    "pvc":      70.0,
    "pvc90":    90.0,
    "xlpe":     90.0,
    "epr":      90.0,
    "ptfe":     200.0,
    "silicone": 180.0,
    "rubber":   60.0,
}
_INSULATION_TREF = 30.0  # °C — reference ambient for base ampacity

# IEC 60664-1 clearance table (simplified): (overvoltage_category, Vpeak) → mm
# Pollution degree 2 (most common for PCB / industrial equipment)
# Table F.2 (IEC 60664-1:2007 + AMD1:2011), micro-environment
# Format: list of (peak_voltage_V, clearance_mm) tuples; linear interp
_CLEARANCE_PD2_CAT2 = [
    (150,   0.2),
    (300,   0.5),
    (600,   1.0),
    (1000,  1.5),
    (1500,  2.5),
    (2000,  3.5),
    (2500,  5.0),
    (4000,  8.0),
    (6000,  14.0),
    (8000,  18.0),
    (12000, 25.0),
]

# IEC 60664-1 creepage distance (mm) for Vpeak, pollution degree, material group
# Simplified from Table A.2 (IEC 60664-1) — working voltage (RMS or DC)
# Format: (working_voltage_V, pd, material_group) → mm
# PD = pollution degree 1..4; MG = I (CTI>=600), II (400<=CTI<600),
#      IIIa (175<=CTI<400), IIIb (100<=CTI<175)
# Base table (PD=2, MG=I) — interpolate / scale for other PD/MG
_CREEPAGE_PD2_MGI = [
    (32,    0.8),
    (63,    1.0),
    (100,   1.25),
    (160,   1.6),
    (250,   2.0),
    (320,   2.5),
    (400,   3.2),
    (500,   4.0),
    (630,   5.0),
    (800,   6.3),
    (1000,  8.0),
    (1250,  10.0),
    (1600,  12.5),
    (2000,  16.0),
    (2500,  20.0),
    (3200,  25.0),
    (4000,  32.0),
    (5000,  40.0),
]

# Pollution degree multiplier for creepage (relative to PD2)
_PD_CREEPAGE_FACTOR = {1: 0.5, 2: 1.0, 3: 2.0, 4: 4.0}

# Material group multiplier for creepage (relative to MG I)
_MG_CREEPAGE_FACTOR = {"I": 1.0, "II": 1.2, "IIIa": 1.6, "IIIb": 2.0}

# Altitude correction for clearance (IEC 60664-1 Annex A, Table A.4 simplified)
# Format: (altitude_m, factor)  — multiply required clearance by factor
_ALTITUDE_CLEARANCE_FACTOR = [
    (2000,  1.0),
    (3000,  1.14),
    (4000,  1.29),
    (5000,  1.48),
    (6000,  1.70),
    (8000,  2.25),
    (10000, 3.00),
]

# ── Helpers ───────────────────────────────────────────────────────────────────


def _validate_positive(value, name: str) -> Optional[str]:
    if not isinstance(value, (int, float)) or math.isnan(value) or value <= 0:
        return f"{name} must be a positive number, got {value!r}"
    return None


def _validate_nonneg(value, name: str) -> Optional[str]:
    if not isinstance(value, (int, float)) or math.isnan(value) or value < 0:
        return f"{name} must be >= 0, got {value!r}"
    return None


def _interp_table(table: list, x: float) -> Optional[float]:
    """Linear interpolation on a sorted (x, y) table; clamp at ends."""
    if not table:
        return None
    if x <= table[0][0]:
        return table[0][1]
    if x >= table[-1][0]:
        return table[-1][1]
    for i in range(1, len(table)):
        x0, y0 = table[i - 1]
        x1, y1 = table[i]
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return table[-1][1]


def _altitude_factor(altitude_m: float) -> float:
    """Return clearance altitude correction factor per IEC 60664-1 Annex A."""
    return _interp_table(_ALTITUDE_CLEARANCE_FACTOR, altitude_m)


# ── 1. Protective-earth / EGC conductor sizing ───────────────────────────────


def protective_earth_conductor_size(
    fault_current_a: float,
    fault_duration_s: float,
    material: str = "copper",
) -> dict:
    """
    Minimum protective-earth (PE) / equipment-grounding conductor (EGC) area.

    Uses the adiabatic equation (IEC 60364-5-54 §543.1):
        A_min [mm²] = I × √t / k

    Parameters
    ----------
    fault_current_a   : float — prospective fault current [A] (RMS symmetrical)
    fault_duration_s  : float — fault clearing time [s]
    material          : str   — 'copper', 'aluminium', or 'steel' (default 'copper')

    Returns
    -------
    dict with keys: ok, area_min_mm2, material, k, fault_current_a, fault_duration_s,
                    warnings
    """
    err = _validate_positive(fault_current_a, "fault_current_a")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(fault_duration_s, "fault_duration_s")
    if err:
        return {"ok": False, "reason": err}

    mat = material.lower().strip()
    k_map = {"copper": _K_COPPER, "aluminium": _K_ALUMINIUM, "steel": _K_STEEL}
    if mat not in k_map:
        return {"ok": False, "reason": f"material must be 'copper', 'aluminium', or 'steel', got {material!r}"}

    k = k_map[mat]
    area_min = fault_current_a * math.sqrt(fault_duration_s) / k

    warns = []
    if fault_duration_s > 5.0:
        warns.append("fault_duration_s > 5 s: adiabatic model may underestimate thermal rise")
    if area_min < 1.5:
        warns.append("calculated area < 1.5 mm²; minimum mechanical limit per IEC 60364-5-54 Table 54.2 is 1.5 mm² (copper) or 16 mm² (earth rod bond)")

    return {
        "ok": True,
        "fault_current_a": fault_current_a,
        "fault_duration_s": fault_duration_s,
        "material": mat,
        "k": k,
        "area_min_mm2": round(area_min, 3),
        "formula": "IEC 60364-5-54 §543.1: A = I × √t / k",
        "warnings": warns,
    }


# ── 2. Bonding resistance check ───────────────────────────────────────────────


def bonding_resistance_check(
    fault_current_a: float,
    bond_resistance_ohm: float,
    safe_touch_voltage_v: float = 50.0,
) -> dict:
    """
    Bonding conductor resistance check for equipotential bonding.

    GPR across the bond = I_fault × R_bond.  Flag when GPR > safe touch voltage.

    Parameters
    ----------
    fault_current_a      : float — maximum fault current through bond [A]
    bond_resistance_ohm  : float — measured bonding conductor resistance [Ω]
    safe_touch_voltage_v : float — permissible touch voltage [V] (default 50 V AC,
                                   per IEC 60364-4-41 §411.3.2)

    Returns
    -------
    dict with keys: ok, gpr_v, gpr_hazard, bond_resistance_ohm, fault_current_a,
                    safe_touch_voltage_v, warnings
    """
    err = _validate_positive(fault_current_a, "fault_current_a")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_nonneg(bond_resistance_ohm, "bond_resistance_ohm")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(safe_touch_voltage_v, "safe_touch_voltage_v")
    if err:
        return {"ok": False, "reason": err}

    gpr = fault_current_a * bond_resistance_ohm
    gpr_hazard = gpr > safe_touch_voltage_v

    warns = []
    if gpr_hazard:
        warnings.warn(
            f"BONDING HAZARD: GPR = {gpr:.1f} V exceeds safe touch limit of "
            f"{safe_touch_voltage_v:.0f} V (I_fault={fault_current_a} A, "
            f"R_bond={bond_resistance_ohm} Ω). Reduce bonding resistance.",
            stacklevel=2,
        )
        warns.append(f"GPR = {gpr:.1f} V exceeds safe touch limit {safe_touch_voltage_v:.0f} V")

    return {
        "ok": True,
        "fault_current_a": fault_current_a,
        "bond_resistance_ohm": bond_resistance_ohm,
        "safe_touch_voltage_v": safe_touch_voltage_v,
        "gpr_v": round(gpr, 3),
        "gpr_hazard": gpr_hazard,
        "warnings": warns,
    }


# ── 3. Ground electrode resistance ────────────────────────────────────────────


def ground_electrode_resistance(
    electrode_type: str,
    soil_resistivity_ohm_m: float,
    length_m: float = 3.0,
    radius_m: float = 0.0079,
    area_m2: float = 1.0,
    grid_area_m2: float = 100.0,
    grid_total_conductor_m: float = 40.0,
    grid_num_meshes: float = 4.0,
) -> dict:
    """
    Ground electrode resistance calculation.

    Supported electrode types:
    - 'rod'   : single vertical rod, Dwight formula (IEEE 80-2013 §14.1)
                 R = ρ/(2πL) × [ln(4L/a) − 1]
    - 'plate' : horizontal plate (circular equivalent, IEEE 80 §14.3)
                 R = ρ/(8r)  where r = √(area/π)
    - 'grid'  : Schwarz formula for a rectangular grid (IEEE 80-2013 §14.2)
                 R_grid = ρ/(π×L_t)×[ln(2×L_t/a') − k1] + ρ×k1/(√(A_grid))

    Parameters
    ----------
    electrode_type             : str   — 'rod', 'plate', or 'grid'
    soil_resistivity_ohm_m     : float — soil resistivity ρ [Ω·m]
    length_m                   : float — rod length [m] (rod only, default 3 m)
    radius_m                   : float — rod radius [m] (rod only, default 7.9 mm)
    area_m2                    : float — plate area [m²] (plate only, default 1 m²)
    grid_area_m2               : float — total grid area [m²] (grid only)
    grid_total_conductor_m     : float — total conductor length [m] (grid only)
    grid_num_meshes            : float — number of meshes (grid only)

    Returns
    -------
    dict with keys: ok, electrode_type, resistance_ohm, soil_resistivity_ohm_m,
                    formula, warnings
    """
    err = _validate_positive(soil_resistivity_ohm_m, "soil_resistivity_ohm_m")
    if err:
        return {"ok": False, "reason": err}

    rho = soil_resistivity_ohm_m
    etype = electrode_type.lower().strip()

    if etype == "rod":
        err = _validate_positive(length_m, "length_m")
        if err:
            return {"ok": False, "reason": err}
        err = _validate_positive(radius_m, "radius_m")
        if err:
            return {"ok": False, "reason": err}
        # Dwight formula: R = ρ/(2πL) × [ln(4L/a) − 1]
        R = (rho / (2.0 * math.pi * length_m)) * (math.log(4.0 * length_m / radius_m) - 1.0)
        formula = "IEEE 80-2013 §14.1 Dwight: R = ρ/(2πL)×[ln(4L/a)−1]"

    elif etype == "plate":
        err = _validate_positive(area_m2, "area_m2")
        if err:
            return {"ok": False, "reason": err}
        r_circ = math.sqrt(area_m2 / math.pi)
        R = rho / (8.0 * r_circ)
        formula = "IEEE 80-2013 §14.3: R = ρ/(8r), r=√(A/π)"

    elif etype == "grid":
        err = _validate_positive(grid_area_m2, "grid_area_m2")
        if err:
            return {"ok": False, "reason": err}
        err = _validate_positive(grid_total_conductor_m, "grid_total_conductor_m")
        if err:
            return {"ok": False, "reason": err}
        err = _validate_positive(grid_num_meshes, "grid_num_meshes")
        if err:
            return {"ok": False, "reason": err}
        # Simplified Schwarz formula (IEEE 80-2013 §14.2)
        # R ≈ ρ/(π×L_t) × [ln(2×L_t/√(grid_area)) + k1×√(grid_area)/L_t − k2]
        # k1≈1.0, k2≈1.0 (constant approximation for square grids)
        Lt = grid_total_conductor_m
        A = grid_area_m2
        k1 = 1.0
        k2 = 1.0
        R = (rho / (math.pi * Lt)) * (math.log(2.0 * Lt / math.sqrt(A)) + k1 * math.sqrt(A) / Lt - k2)
        formula = "IEEE 80-2013 §14.2 Schwarz (simplified): R = ρ/(π×Lt)×[ln(2Lt/√A)+k1×√A/Lt−k2]"

    else:
        return {"ok": False, "reason": f"electrode_type must be 'rod', 'plate', or 'grid', got {electrode_type!r}"}

    # Clamp negative R (can occur for very long grids — means effectively zero)
    R = max(R, 0.0)

    warns = []
    if R > 10.0:
        warns.append(f"Ground resistance {R:.1f} Ω exceeds typical 10 Ω limit (IEC 60364-5-54 §542.2.4 / NEC 250.53(A)(2))")
    if soil_resistivity_ohm_m > 1000.0:
        warns.append(f"Soil resistivity {soil_resistivity_ohm_m} Ω·m is very high (>1000 Ω·m); multiple electrodes or deep-driven rods recommended")

    return {
        "ok": True,
        "electrode_type": etype,
        "soil_resistivity_ohm_m": rho,
        "resistance_ohm": round(R, 4),
        "formula": formula,
        "warnings": warns,
    }


# ── 4. Ground potential rise ──────────────────────────────────────────────────


def ground_potential_rise(
    fault_current_a: float,
    ground_resistance_ohm: float,
) -> dict:
    """
    Ground potential rise (GPR) at a grounding electrode during a fault.

    GPR = I_fault × R_ground  (IEEE 80-2013 §2.2.3)

    Parameters
    ----------
    fault_current_a         : float — symmetrical fault current flowing into earth [A]
    ground_resistance_ohm   : float — total ground electrode resistance [Ω]

    Returns
    -------
    dict with keys: ok, gpr_v, hazard_level, fault_current_a, ground_resistance_ohm,
                    warnings
    """
    err = _validate_positive(fault_current_a, "fault_current_a")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_nonneg(ground_resistance_ohm, "ground_resistance_ohm")
    if err:
        return {"ok": False, "reason": err}

    gpr = fault_current_a * ground_resistance_ohm

    warns = []
    if gpr > _GPR_HAZARD_HIGH:
        hazard = "EXTREME"
        warnings.warn(
            f"GPR EXTREME HAZARD: GPR = {gpr:.0f} V > {_GPR_HAZARD_HIGH:.0f} V "
            f"(IEEE 80 extreme hazard zone). Isolating equipment required.",
            stacklevel=2,
        )
        warns.append(f"GPR = {gpr:.0f} V exceeds 5000 V (IEEE 80 extreme hazard)")
    elif gpr > _GPR_HAZARD_LOW:
        hazard = "HIGH"
        warnings.warn(
            f"GPR HAZARD: GPR = {gpr:.0f} V > {_GPR_HAZARD_LOW:.0f} V "
            f"(IEEE 80 additional precautions required).",
            stacklevel=2,
        )
        warns.append(f"GPR = {gpr:.0f} V exceeds 1000 V (IEEE 80 hazardous)")
    else:
        hazard = "LOW"

    return {
        "ok": True,
        "fault_current_a": fault_current_a,
        "ground_resistance_ohm": ground_resistance_ohm,
        "gpr_v": round(gpr, 2),
        "hazard_level": hazard,
        "warnings": warns,
    }


# ── 5. Touch and step voltage ─────────────────────────────────────────────────


def touch_step_voltage(
    fault_current_a: float,
    fault_duration_s: float,
    surface_layer_resistivity_ohm_m: float = 0.0,
    body_weight_kg: float = 70.0,
) -> dict:
    """
    Permissible touch and step voltage for a human body model.

    Based on IEC 60479-1:2005 and IEEE 80-2013 §8:

    Permissible body current (IEC 60479-1, ventricular fibrillation threshold,
    curve c1 ≈ 0.116 A·s^0.5 for 50 kg):
        I_body = C_b × 0.116 / √t_s
        C_b = 0.58 for 50 kg, 0.70 for 70 kg (scaled from IEEE 80 §8.3)

    Permissible touch voltage (hand-to-foot, IEC 60479-1):
        V_touch = (R_body + R_step/2) × I_body
               = (1000 + 1.5 × ρs) × I_body     [IEEE 80 Eq. 32]

    Permissible step voltage (foot-to-foot):
        V_step = (R_body + 2 × R_step) × I_body
               = (1000 + 6 × ρs) × I_body        [IEEE 80 Eq. 33]

    where ρs = surface layer resistivity [Ω·m] (crushed rock ≈ 2500 Ω·m).

    Parameters
    ----------
    fault_current_a                   : float — fault current [A] (used for GPR context only)
    fault_duration_s                  : float — fault clearing time [s]
    surface_layer_resistivity_ohm_m   : float — surface material resistivity [Ω·m] (default 0)
    body_weight_kg                    : float — body weight [kg] (50 or 70, default 70)

    Returns
    -------
    dict with keys: ok, v_touch_permissible_v, v_step_permissible_v,
                    i_body_permissible_a, fault_duration_s, surface_resistivity_ohm_m,
                    warnings
    """
    err = _validate_positive(fault_current_a, "fault_current_a")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(fault_duration_s, "fault_duration_s")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_nonneg(surface_layer_resistivity_ohm_m, "surface_layer_resistivity_ohm_m")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(body_weight_kg, "body_weight_kg")
    if err:
        return {"ok": False, "reason": err}

    # Body weight correction (IEEE 80 §8.3)
    if body_weight_kg <= 50.0:
        c_b = 0.58
    else:
        c_b = 0.70

    i_body = c_b * _IEC60479_C1 / math.sqrt(fault_duration_s)
    rho_s = surface_layer_resistivity_ohm_m

    v_touch = (1000.0 + 1.5 * rho_s) * i_body
    v_step  = (1000.0 + 6.0  * rho_s) * i_body

    warns = []
    if fault_duration_s > 1.0:
        warns.append(
            f"Fault duration {fault_duration_s:.2f} s > 1 s: IEC 60479-1 "
            "fibrillation curve is valid up to ~10 s; permissible voltages may be conservative"
        )

    return {
        "ok": True,
        "fault_current_a": fault_current_a,
        "fault_duration_s": fault_duration_s,
        "surface_resistivity_ohm_m": rho_s,
        "body_weight_kg": body_weight_kg,
        "c_b": c_b,
        "i_body_permissible_a": round(i_body, 6),
        "v_touch_permissible_v": round(v_touch, 2),
        "v_step_permissible_v":  round(v_step, 2),
        "formula": "IEEE 80-2013 §8 / IEC 60479-1",
        "warnings": warns,
    }


# ── 6. Creepage and clearance ─────────────────────────────────────────────────


def creepage_clearance(
    working_voltage_v_rms: float,
    overvoltage_category: int = 2,
    pollution_degree: int = 2,
    material_group: str = "II",
    altitude_m: float = 2000.0,
    measured_creepage_mm: float = 0.0,
    measured_clearance_mm: float = 0.0,
) -> dict:
    """
    Minimum creepage distance and clearance per IEC 60664-1:2007+A1.

    Parameters
    ----------
    working_voltage_v_rms    : float — working voltage [V RMS or DC]
    overvoltage_category     : int   — I, II, III, or IV (default 2)
    pollution_degree         : int   — 1, 2, 3, or 4 (default 2)
    material_group           : str   — 'I', 'II', 'IIIa', or 'IIIb' (default 'II')
    altitude_m               : float — installation altitude [m] (default 2000 m = no correction)
    measured_creepage_mm     : float — actual creepage on PCB/product [mm] (0 = no check)
    measured_clearance_mm    : float — actual clearance on PCB/product [mm] (0 = no check)

    Returns
    -------
    dict with keys: ok, min_creepage_mm, min_clearance_mm,
                    altitude_correction_factor, altitude_corrected_clearance_mm,
                    creepage_ok, clearance_ok, warnings
    """
    err = _validate_positive(working_voltage_v_rms, "working_voltage_v_rms")
    if err:
        return {"ok": False, "reason": err}
    if overvoltage_category not in (1, 2, 3, 4):
        return {"ok": False, "reason": f"overvoltage_category must be 1-4, got {overvoltage_category!r}"}
    if pollution_degree not in (1, 2, 3, 4):
        return {"ok": False, "reason": f"pollution_degree must be 1-4, got {pollution_degree!r}"}
    mg = str(material_group).strip()
    if mg not in _MG_CREEPAGE_FACTOR:
        return {"ok": False, "reason": f"material_group must be 'I', 'II', 'IIIa', or 'IIIb', got {material_group!r}"}
    err = _validate_nonneg(altitude_m, "altitude_m")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_nonneg(measured_creepage_mm, "measured_creepage_mm")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_nonneg(measured_clearance_mm, "measured_clearance_mm")
    if err:
        return {"ok": False, "reason": err}

    # ── Creepage ──
    # Base creepage from PD=2, MG=I table (IEC 60664-1 Table A.2)
    base_creep = _interp_table(_CREEPAGE_PD2_MGI, working_voltage_v_rms)
    pd_factor  = _PD_CREEPAGE_FACTOR.get(pollution_degree, 1.0)
    mg_factor  = _MG_CREEPAGE_FACTOR[mg]
    min_creep  = base_creep * pd_factor * mg_factor

    # ── Clearance ──
    # Convert working RMS voltage to peak, then look up clearance
    # For AC: V_peak = V_rms × √2; for DC: V_peak = V_rms
    # We use working_voltage_v_rms as V_peak conservative (as IEC 60664 uses peak)
    v_peak = working_voltage_v_rms * math.sqrt(2.0)

    # Overvoltage category scales the required clearance (higher category → lower protection)
    # Categories I..IV add transient overvoltage (IEC 60664-1 Table F.2)
    # Simplified: OVC II is our base; OVC I halves the requirement; OVC III/IV add 25/50%
    ovc_factor = {1: 0.5, 2: 1.0, 3: 1.25, 4: 1.5}[overvoltage_category]
    base_clear = _interp_table(_CLEARANCE_PD2_CAT2, v_peak) * ovc_factor

    # Altitude correction
    alt_factor = _altitude_factor(altitude_m)
    min_clear  = base_clear * alt_factor

    # Pass/fail checks
    creep_ok  = (measured_creepage_mm >= min_creep) if measured_creepage_mm > 0 else None
    clear_ok  = (measured_clearance_mm >= min_clear) if measured_clearance_mm > 0 else None

    warns = []
    if creep_ok is False:
        warnings.warn(
            f"INSUFFICIENT CREEPAGE: measured {measured_creepage_mm:.2f} mm < "
            f"required {min_creep:.2f} mm (IEC 60664-1, PD{pollution_degree}, MG{mg}, "
            f"{working_voltage_v_rms:.0f} V RMS)",
            stacklevel=2,
        )
        warns.append(f"Creepage {measured_creepage_mm:.2f} mm < required {min_creep:.2f} mm")
    if clear_ok is False:
        warnings.warn(
            f"INSUFFICIENT CLEARANCE: measured {measured_clearance_mm:.2f} mm < "
            f"required {min_clear:.2f} mm (IEC 60664-1, OVC-{overvoltage_category}, "
            f"altitude={altitude_m:.0f} m)",
            stacklevel=2,
        )
        warns.append(f"Clearance {measured_clearance_mm:.2f} mm < required {min_clear:.2f} mm")

    return {
        "ok": True,
        "working_voltage_v_rms": working_voltage_v_rms,
        "overvoltage_category": overvoltage_category,
        "pollution_degree": pollution_degree,
        "material_group": mg,
        "altitude_m": altitude_m,
        "altitude_correction_factor": round(alt_factor, 4),
        "min_creepage_mm": round(min_creep, 3),
        "min_clearance_mm": round(min_clear, 3),
        "altitude_corrected_clearance_mm": round(min_clear, 3),
        "measured_creepage_mm": measured_creepage_mm,
        "measured_clearance_mm": measured_clearance_mm,
        "creepage_ok": creep_ok,
        "clearance_ok": clear_ok,
        "warnings": warns,
        "reference": "IEC 60664-1:2007+A1",
    }


# ── 7. Insulation / Hi-pot test voltage ──────────────────────────────────────


def insulation_hipot(
    working_voltage_v_rms: float,
    insulation_class: str = "basic",
    equipment_class: str = "I",
) -> dict:
    """
    Basic / reinforced insulation Hi-pot (dielectric withstand) test voltage.

    Based on IEC 60664-1:2007 Table F.4 and IEC 62368-1:2018 Annex Q.

    Insulation classes:
    - 'basic'       : protects against primary electric shock hazard
    - 'supplementary': secondary protection layer
    - 'reinforced'  : double protection equivalent, test voltage × 1.6
    - 'functional'  : no shock protection required, test voltage = 1.2 × V_peak

    Equipment classes (IEC 60950-1 / IEC 61140):
    - 'I'   : earthed metalwork (basic insulation + PE)
    - 'II'  : double/reinforced insulation (no PE)
    - 'III' : SELV source, low-voltage

    Parameters
    ----------
    working_voltage_v_rms : float — working voltage [V RMS or DC]
    insulation_class      : str   — 'basic', 'supplementary', 'reinforced',
                                    or 'functional' (default 'basic')
    equipment_class       : str   — 'I', 'II', or 'III' (default 'I')

    Returns
    -------
    dict with keys: ok, test_voltage_v_rms, working_voltage_v_rms,
                    insulation_class, equipment_class, warnings
    """
    err = _validate_positive(working_voltage_v_rms, "working_voltage_v_rms")
    if err:
        return {"ok": False, "reason": err}

    ic = insulation_class.lower().strip()
    valid_ic = ("basic", "supplementary", "reinforced", "functional")
    if ic not in valid_ic:
        return {"ok": False, "reason": f"insulation_class must be one of {valid_ic}, got {insulation_class!r}"}

    ec = str(equipment_class).upper().strip()
    if ec not in ("I", "II", "III"):
        return {"ok": False, "reason": f"equipment_class must be 'I', 'II', or 'III', got {equipment_class!r}"}

    v_rms = working_voltage_v_rms
    v_peak = v_rms * math.sqrt(2.0)

    # Base test voltage: IEC 60664-1 Table F.4 (step-function approximation)
    # working_voltage_v_rms → test_voltage_v_rms (1-minute, 50 Hz AC or DC)
    # Values from IEC 60664-1:2007 Table F.4 for basic insulation
    _hipot_table = [
        (50,    500),
        (100,   1000),
        (150,   1500),
        (300,   2000),
        (600,   2500),
        (1000,  3000),
        (1500,  4000),
        (2000,  5000),
        (2500,  6000),
    ]
    base_test_v = _interp_table(_hipot_table, v_rms)

    # Insulation class multiplier
    ic_factor = {
        "basic": 1.0,
        "supplementary": 1.0,
        "reinforced": 2.0,   # IEC 60664-1 §6.1.3.3 — reinforced = 2× basic test voltage
        "functional": 1.2,   # functional: 1.2 × V_peak converted to RMS equivalent
    }
    test_v = base_test_v * ic_factor[ic]

    # Equipment class II always uses reinforced (or double) insulation
    if ec == "II" and ic == "basic":
        test_v = base_test_v * 2.0

    warns = []
    if v_rms > 1000.0:
        warns.append("Working voltage > 1 kV: high-voltage insulation; verify IEC 60664-1 Part 2 / IEC 61010-1 requirements")
    if ec == "III" and v_rms > 50.0:
        warns.append(f"Equipment Class III with V_working={v_rms:.0f} V > 50 V AC; verify SELV/PELV threshold compliance")

    return {
        "ok": True,
        "working_voltage_v_rms": v_rms,
        "insulation_class": ic,
        "equipment_class": ec,
        "test_voltage_v_rms": round(test_v, 1),
        "test_voltage_v_peak": round(test_v * math.sqrt(2.0), 1),
        "warnings": warns,
        "reference": "IEC 60664-1:2007 Table F.4 / IEC 62368-1:2018 Annex Q",
    }


# ── 8. Leakage / touch current limits ────────────────────────────────────────


def leakage_touch_current_limit(
    equipment_class: str = "I",
    application: str = "it",
    connection: str = "normal",
    measured_leakage_a: float = 0.0,
) -> dict:
    """
    Permissible leakage / touch current per IEC 60601-1 (medical) and
    IEC 60950-1 / IEC 62368-1 (IT / AV) equipment.

    IEC 62368-1:2018 Table 5.4 (IT equipment):
        Class I normal: touch current ≤ 3.5 mA (60 Hz), earth leakage ≤ 3.5 mA
        Class II      : touch current ≤ 0.25 mA
        Class III     : not specified (SELV)

    IEC 60601-1:2005+A1 Table 1 (medical, patient environment):
        Class I NC/SFC : earth leakage ≤ 5 mA, enclosure leakage ≤ 100 μA
        Class II       : enclosure leakage ≤ 100 μA
        Type B patient : patient leakage ≤ 500 μA (earth), 5000 μA (mains on F-part)
        Type BF patient: patient leakage ≤ 100 μA, 500 μA (mains on F-part)
        Type CF patient: patient leakage ≤ 10 μA, 50 μA (mains on F-part)

    Parameters
    ----------
    equipment_class     : str   — 'I', 'II', or 'III' (IEC 61140)
    application         : str   — 'it' (IT/AV, 62368-1) or 'medical' (60601-1)
    connection          : str   — for medical: 'normal', 'single_fault', 'patient_b',
                                  'patient_bf', 'patient_cf'; for IT: 'normal'
    measured_leakage_a  : float — measured leakage current [A] (0 = no check)

    Returns
    -------
    dict with keys: ok, limit_a, equipment_class, application, connection,
                    compliant (None if not measured), warnings
    """
    ec = str(equipment_class).upper().strip()
    if ec not in ("I", "II", "III"):
        return {"ok": False, "reason": f"equipment_class must be 'I', 'II', or 'III', got {equipment_class!r}"}

    app = application.lower().strip()
    if app not in ("it", "medical"):
        return {"ok": False, "reason": f"application must be 'it' or 'medical', got {application!r}"}

    conn = connection.lower().strip()

    if app == "it":
        # IEC 62368-1 Table 5.4
        limit_a = {
            "I":   3.5e-3,    # 3.5 mA touch / earth
            "II":  0.25e-3,   # 0.25 mA touch
            "III": None,      # SELV — no limit
        }[ec]
    else:
        # IEC 60601-1 Table 1 (selected limits)
        medical_limits = {
            ("I",   "normal"):        5.0e-3,    # earth leakage NC
            ("I",   "single_fault"):  10.0e-3,   # earth leakage SFC
            ("II",  "normal"):        0.1e-3,    # enclosure leakage
            ("II",  "single_fault"):  0.5e-3,    # enclosure leakage SFC
            ("I",   "patient_b"):     0.5e-3,    # patient leakage B-type
            ("I",   "patient_bf"):    0.1e-3,    # patient leakage BF-type
            ("I",   "patient_cf"):    0.01e-3,   # patient leakage CF-type
            ("III", "normal"):        None,
        }
        limit_a = medical_limits.get((ec, conn))
        if limit_a is None and (ec, conn) not in medical_limits:
            return {
                "ok": False,
                "reason": f"No IEC 60601-1 limit defined for class={ec}, connection={conn}",
            }

    warns = []
    compliant = None
    if measured_leakage_a > 0 and limit_a is not None:
        compliant = measured_leakage_a <= limit_a
        if not compliant:
            warnings.warn(
                f"LEAKAGE CURRENT EXCEEDED: measured {measured_leakage_a*1e3:.3f} mA > "
                f"limit {limit_a*1e3:.3f} mA (Class {ec}, {app.upper()}, {conn})",
                stacklevel=2,
            )
            warns.append(
                f"Leakage {measured_leakage_a*1e3:.3f} mA exceeds {app.upper()} "
                f"Class {ec} limit {limit_a*1e3:.3f} mA"
            )

    return {
        "ok": True,
        "equipment_class": ec,
        "application": app,
        "connection": conn,
        "limit_a": limit_a,
        "limit_ma": round(limit_a * 1000.0, 4) if limit_a is not None else None,
        "measured_leakage_a": measured_leakage_a,
        "compliant": compliant,
        "warnings": warns,
        "reference": "IEC 62368-1:2018 Table 5.4 / IEC 60601-1:2005+A1 Table 1",
    }


# ── 9. RCD / GFCI threshold ───────────────────────────────────────────────────


def rcd_gfci_threshold(
    rcd_rating_a: float,
    measured_leakage_a: float,
    device_type: str = "general",
) -> dict:
    """
    RCD / GFCI trip threshold check per IEC 61008 and UL 943.

    IEC 61008-1:2010 §5.2:
        30 mA RCD (Type AC): trip at I_Δn, non-trip at 0.5 × I_Δn
        10 mA RCD: personal protection
        300 mA RCD: fire protection

    UL 943 Class A GFCI: trip at 6 mA ground fault current (personnel protection)
    UL 943 Class B GFCI: trip at 20 mA (submersible pumps)

    Parameters
    ----------
    rcd_rating_a       : float — RCD rated residual current I_Δn [A]
    measured_leakage_a : float — measured system leakage current [A]
    device_type        : str   — 'general' (IEC 61008), 'ul_class_a', or 'ul_class_b'

    Returns
    -------
    dict with keys: ok, rcd_rating_a, measured_leakage_a, trip_threshold_a,
                    no_trip_threshold_a, will_trip, margin_a, warnings
    """
    err = _validate_positive(rcd_rating_a, "rcd_rating_a")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_nonneg(measured_leakage_a, "measured_leakage_a")
    if err:
        return {"ok": False, "reason": err}

    dt = device_type.lower().strip()
    valid_dt = ("general", "ul_class_a", "ul_class_b")
    if dt not in valid_dt:
        return {"ok": False, "reason": f"device_type must be one of {valid_dt}"}

    if dt == "general":
        # IEC 61008: trip at I_Δn, guaranteed no-trip at 0.5 × I_Δn
        trip_threshold  = rcd_rating_a
        no_trip_threshold = 0.5 * rcd_rating_a
    elif dt == "ul_class_a":
        trip_threshold  = 6e-3   # 6 mA UL 943 Class A
        no_trip_threshold = 4e-3
    else:  # ul_class_b
        trip_threshold  = 20e-3  # 20 mA UL 943 Class B
        no_trip_threshold = 10e-3

    will_trip = measured_leakage_a >= trip_threshold
    margin_a  = trip_threshold - measured_leakage_a

    warns = []
    if measured_leakage_a > no_trip_threshold and not will_trip:
        warns.append(
            f"Leakage {measured_leakage_a*1e3:.2f} mA is in the uncertain zone "
            f"({no_trip_threshold*1e3:.1f}–{trip_threshold*1e3:.1f} mA): "
            "RCD may trip intermittently"
        )
    if will_trip:
        warnings.warn(
            f"RCD WILL TRIP: leakage {measured_leakage_a*1e3:.2f} mA >= "
            f"trip threshold {trip_threshold*1e3:.2f} mA",
            stacklevel=2,
        )
        warns.append(f"Leakage {measured_leakage_a*1e3:.2f} mA will trip RCD at {trip_threshold*1e3:.2f} mA")

    return {
        "ok": True,
        "rcd_rating_a": rcd_rating_a,
        "device_type": dt,
        "measured_leakage_a": measured_leakage_a,
        "trip_threshold_a": trip_threshold,
        "no_trip_threshold_a": no_trip_threshold,
        "will_trip": will_trip,
        "margin_a": round(margin_a, 6),
        "warnings": warns,
        "reference": "IEC 61008-1:2010 / UL 943",
    }


# ── 10. Arc-flash incident energy ─────────────────────────────────────────────


def arc_flash_incident_energy(
    system_voltage_v: float,
    bolted_fault_current_ka: float,
    arcing_duration_s: float,
    working_distance_mm: float = 455.0,
    electrode_gap_mm: float = 32.0,
    system_type: str = "open_air",
) -> dict:
    """
    Simplified arc-flash incident energy and arc-flash boundary.

    Two methods are computed:

    1. IEEE 1584-2002 Lee equation (theoretical maximum, conservative):
          E_Lee [cal/cm²] = 793 × V_kV × I_bf × t / D²
          where V_kV = system_voltage / 1000, I_bf = bolted fault [kA],
          t = duration [s], D = distance [mm].

    2. IEEE 1584-2002 empirical equations (for 208 V–15 kV, 13–152 mm
       gap, 0.7–106 kA, open-air or in-box).  This is the TWO-STEP
       method mandated by IEEE 1584-2002 §9:

       Step 1 — arcing current (IEEE 1584-2002 Eq. 1, V < 1 kV):
          lg I_a = K + 0.662·lg I_bf + 0.0966·V + 0.000526·G
                   + 0.5588·V·lg I_bf − 0.00304·G·lg I_bf
          (K = −0.097 in-box, −0.153 open-air; V in kV, G in mm)
          For V ≥ 1 kV (Eq. 2): lg I_a = 0.00402 + 0.983·lg I_bf

       Step 2 — normalized incident energy (IEEE 1584-2002 Eq. 4) — note
       this uses lg I_a (the ARCING current), NOT lg I_bf:
          lg E_n = K1 + K2 + 1.081·lg I_a + 0.0011·G
          E [J/cm²] = 4.184 · Cf · E_n · (t/0.2) · (610^x / D^x)
       Constants — open-air: K1=−0.792, K2=0 (ungrounded), x=2.000, Cf=1.0
                   in-box:   K1=−0.555, K2=0 (ungrounded), x=1.473, Cf=1.5
       (K2 = −0.113 for grounded systems; conservatively 0 here.)

    Arc-flash boundary (AFB): distance at which E = 1.2 cal/cm² (onset of
    second-degree burn, NFPA 70E Table 130.7).
        AFB = 610 × (4.184 × Cf × En × t / (0.2 × 1.2))^(1/x)

    PPE category per NFPA 70E-2021 Table 130.7(C)(15)(a).

    Parameters
    ----------
    system_voltage_v      : float — system voltage [V] (line-to-line for 3-phase)
    bolted_fault_current_ka: float — symmetrical bolted fault current [kA]
    arcing_duration_s     : float — arc duration (protection clearing time) [s]
    working_distance_mm   : float — working distance from arc [mm] (default 455 mm = 18 in)
    electrode_gap_mm      : float — conductor gap [mm] (default 32 mm for MCC)
    system_type           : str   — 'open_air' or 'enclosure' (default 'open_air')

    Returns
    -------
    dict with keys: ok, incident_energy_cal_cm2_lee, incident_energy_cal_cm2_empirical,
                    incident_energy_cal_cm2, afb_mm, ppe_category,
                    system_voltage_v, bolted_fault_current_ka, arcing_duration_s,
                    working_distance_mm, warnings
    """
    err = _validate_positive(system_voltage_v, "system_voltage_v")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(bolted_fault_current_ka, "bolted_fault_current_ka")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(arcing_duration_s, "arcing_duration_s")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(working_distance_mm, "working_distance_mm")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(electrode_gap_mm, "electrode_gap_mm")
    if err:
        return {"ok": False, "reason": err}

    stype = system_type.lower().strip()
    if stype not in ("open_air", "enclosure"):
        return {"ok": False, "reason": "system_type must be 'open_air' or 'enclosure'"}

    V_kV = system_voltage_v / 1000.0
    I_bf = bolted_fault_current_ka
    t    = arcing_duration_s
    D    = working_distance_mm
    G    = electrode_gap_mm

    # ── Lee equation (conservative theoretical maximum) ──────────────────
    # E_Lee [cal/cm²] = 793 × V_kV × I_bf × t / D²
    e_lee_cal = 793.0 * V_kV * I_bf * t / (D ** 2)

    # ── IEEE 1584-2002 empirical equations (two-step) ─────────────────────
    # Step 1: arcing current I_a from bolted fault I_bf (Eq. 1 / Eq. 2).
    lg_Ibf = math.log10(I_bf)
    if V_kV < 1.0:
        K_arc = -0.097 if stype == "enclosure" else -0.153
        lg_Ia = (
            K_arc
            + 0.662 * lg_Ibf
            + 0.0966 * V_kV
            + 0.000526 * G
            + 0.5588 * V_kV * lg_Ibf
            - 0.00304 * G * lg_Ibf
        )
    else:  # V >= 1 kV (IEEE 1584-2002 Eq. 2)
        lg_Ia = 0.00402 + 0.983 * lg_Ibf
    I_a = 10.0 ** lg_Ia

    # Step 2: normalized incident energy uses lg(I_a), NOT lg(I_bf).
    if stype == "open_air":
        K1, K2, x, Cf = -0.792, 0.0, 2.000, 1.0
    else:  # enclosure / in-box
        K1, K2, x, Cf = -0.555, 0.0, 1.473, 1.5

    log_En = K1 + K2 + 1.081 * lg_Ia + 0.0011 * G
    En = 10.0 ** log_En
    e_empirical_j = 4.184 * Cf * En * (t / 0.2) * ((610 ** x) / (D ** x))
    e_empirical_cal = e_empirical_j / 4.184  # J/cm² → cal/cm²

    # Use the higher of the two estimates (conservative)
    e_incident = max(e_lee_cal, e_empirical_cal)

    # ── Arc-flash boundary ────────────────────────────────────────────────
    # E_limit = 1.2 cal/cm²; AFB = 610 × (4.184×Cf×En×t/(0.2×1.2))^(1/x)
    e_limit_cal = 1.2
    e_limit_j   = e_limit_cal * 4.184
    afb_arg = 4.184 * Cf * En * t / (0.2 * e_limit_j)
    if afb_arg > 0:
        afb_mm = 610.0 * (afb_arg ** (1.0 / x))
    else:
        afb_mm = 0.0

    # ── PPE category ──────────────────────────────────────────────────────
    ppe_cat = None
    for cat, lo, hi in _AF_CATEGORY_LIMITS:
        if lo <= e_incident < hi:
            ppe_cat = cat
            break
    if ppe_cat is None:
        if e_incident < 1.2:
            ppe_cat = 0  # below Cat 1 — no special PPE required
        else:
            ppe_cat = 4  # above Cat 4 — de-energise before work

    warns = []
    if e_incident >= _AF_UNRATED:
        warnings.warn(
            f"ARC-FLASH EXTREME: incident energy {e_incident:.1f} cal/cm² >= "
            f"{_AF_UNRATED:.0f} cal/cm² (above NFPA 70E Cat 4 upper limit). "
            "Equipment MUST be de-energised before work.",
            stacklevel=2,
        )
        warns.append(f"Incident energy {e_incident:.1f} cal/cm² exceeds Cat 4 — de-energise required")
    elif ppe_cat >= 3:
        warnings.warn(
            f"ARC-FLASH HIGH: incident energy {e_incident:.1f} cal/cm² "
            f"→ NFPA 70E PPE Category {ppe_cat}. High-level PPE required.",
            stacklevel=2,
        )
        warns.append(f"High incident energy {e_incident:.1f} cal/cm²: PPE Category {ppe_cat}")

    if arcing_duration_s > 2.0:
        warns.append("Arcing duration > 2 s: verify that upstream protection clears the fault within design limits")

    return {
        "ok": True,
        "system_voltage_v": system_voltage_v,
        "bolted_fault_current_ka": I_bf,
        "arcing_duration_s": t,
        "working_distance_mm": D,
        "electrode_gap_mm": G,
        "system_type": stype,
        "arcing_current_ka":                  round(I_a, 4),
        "incident_energy_cal_cm2_lee":       round(e_lee_cal,       4),
        "incident_energy_cal_cm2_empirical":  round(e_empirical_cal, 4),
        "incident_energy_cal_cm2":            round(e_incident,      4),
        "incident_energy_j_cm2":              round(e_incident * 4.184, 4),
        "afb_mm":     round(afb_mm, 1),
        "ppe_category": ppe_cat,
        "warnings": warns,
        "reference": "IEEE 1584-2002 / NFPA 70E-2021 Table 130.7",
    }


# ── 11. Wire ampacity ─────────────────────────────────────────────────────────


def wire_ampacity(
    cross_section_mm2: float,
    insulation: str = "pvc",
    ambient_temp_c: float = 30.0,
    load_current_a: float = 0.0,
) -> dict:
    """
    Wire ampacity vs insulation temperature rating with ambient derating.

    Base ampacity from a simplified IEC 60228 / NEC 310.15(B)(16) table for copper.
    Temperature derating factor (IEC 60364-5-52 §525.1):
        I_derated = I_base × √((T_max − T_amb) / (T_max − T_ref))
    where T_ref = 30°C (base table reference ambient).

    Parameters
    ----------
    cross_section_mm2 : float — conductor cross-section [mm²]
    insulation        : str   — 'pvc' (70°C), 'pvc90'/'xlpe'/'epr' (90°C),
                                'ptfe' (200°C), 'silicone' (180°C), 'rubber' (60°C)
    ambient_temp_c    : float — ambient temperature [°C] (default 30°C)
    load_current_a    : float — actual load current [A] (0 = no check)

    Returns
    -------
    dict with keys: ok, cross_section_mm2, insulation, t_max_c, ambient_temp_c,
                    base_ampacity_a, derated_ampacity_a, load_current_a,
                    overloaded, derating_factor, warnings
    """
    err = _validate_positive(cross_section_mm2, "cross_section_mm2")
    if err:
        return {"ok": False, "reason": err}

    ins = insulation.lower().strip()
    if ins not in _INSULATION_TMAX:
        return {
            "ok": False,
            "reason": f"insulation must be one of {list(_INSULATION_TMAX.keys())}, got {insulation!r}",
        }

    t_max = _INSULATION_TMAX[ins]

    err = _validate_positive(ambient_temp_c + 273.15, "ambient_temp_c (must be > −273 °C)")
    if err:
        return {"ok": False, "reason": err}

    if ambient_temp_c >= t_max:
        return {
            "ok": False,
            "reason": f"ambient_temp_c ({ambient_temp_c}°C) >= T_max ({t_max}°C) for insulation '{ins}'",
        }

    err = _validate_nonneg(load_current_a, "load_current_a")
    if err:
        return {"ok": False, "reason": err}

    base_amp = _interp_table(_COPPER_AMPACITY, cross_section_mm2)

    derate = math.sqrt((t_max - ambient_temp_c) / (t_max - _INSULATION_TREF))
    derated_amp = base_amp * derate

    overloaded = (load_current_a > derated_amp) if load_current_a > 0 else None

    warns = []
    if overloaded:
        warnings.warn(
            f"OVERLOADED: load {load_current_a:.1f} A > derated ampacity {derated_amp:.1f} A "
            f"({cross_section_mm2} mm² {ins.upper()}, T_amb={ambient_temp_c}°C)",
            stacklevel=2,
        )
        warns.append(f"Load {load_current_a:.1f} A exceeds derated ampacity {derated_amp:.1f} A")
    if ambient_temp_c > 60.0:
        warns.append(f"Ambient temperature {ambient_temp_c}°C is high; verify that grouping/bundling derating is also applied")

    return {
        "ok": True,
        "cross_section_mm2": cross_section_mm2,
        "insulation": ins,
        "t_max_c": t_max,
        "ambient_temp_c": ambient_temp_c,
        "base_ampacity_a": round(base_amp, 2),
        "derating_factor": round(derate, 4),
        "derated_ampacity_a": round(derated_amp, 2),
        "load_current_a": load_current_a,
        "overloaded": overloaded,
        "warnings": warns,
        "reference": "IEC 60228 / NEC 310.15(B)(16) / IEC 60364-5-52",
    }


# ── 12. SELV / PELV threshold check ──────────────────────────────────────────


def selv_pelv_check(
    voltage_v_ac_rms: float = 0.0,
    voltage_v_dc: float = 0.0,
    circuit_type: str = "SELV",
) -> dict:
    """
    SELV / PELV threshold check per IEC 61140:2016 and IEC 60364-4-41.

    Limits (IEC 61140:2016 §6.1 / IEC 60364-4-41 §414):
        AC (RMS):         ≤ 50 V (ordinary environments)
                          ≤ 25 V (in water / swimming pools — IEC 60364-7-702)
        DC (ripple-free): ≤ 120 V

    SELV: separated extra-low voltage, isolated from earth
    PELV: protective extra-low voltage, may have protective earth connection

    Parameters
    ----------
    voltage_v_ac_rms : float — AC RMS voltage [V] (0 if DC)
    voltage_v_dc     : float — DC voltage [V] (0 if AC)
    circuit_type     : str   — 'SELV' or 'PELV' (default 'SELV')

    Returns
    -------
    dict with keys: ok, circuit_type, voltage_v_ac_rms, voltage_v_dc,
                    is_selv_pelv, borderline, warnings
    """
    err = _validate_nonneg(voltage_v_ac_rms, "voltage_v_ac_rms")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_nonneg(voltage_v_dc, "voltage_v_dc")
    if err:
        return {"ok": False, "reason": err}

    if voltage_v_ac_rms == 0.0 and voltage_v_dc == 0.0:
        return {"ok": False, "reason": "At least one of voltage_v_ac_rms or voltage_v_dc must be > 0"}

    ct = circuit_type.upper().strip()
    if ct not in ("SELV", "PELV"):
        return {"ok": False, "reason": f"circuit_type must be 'SELV' or 'PELV', got {circuit_type!r}"}

    _AC_LIMIT  = 50.0    # V RMS
    _DC_LIMIT  = 120.0   # V DC ripple-free
    _AC_BORDER = 42.4    # V RMS (30 V peak used in some standards as borderline)

    ac_ok = (voltage_v_ac_rms == 0.0) or (voltage_v_ac_rms <= _AC_LIMIT)
    dc_ok = (voltage_v_dc == 0.0)     or (voltage_v_dc <= _DC_LIMIT)

    is_selv_pelv = ac_ok and dc_ok
    borderline = (
        (0 < voltage_v_ac_rms > _AC_BORDER) or
        (0 < voltage_v_dc > 110.0)
    )

    warns = []
    if not is_selv_pelv:
        warnings.warn(
            f"NOT SELV/PELV: voltage exceeds IEC 61140 limits "
            f"(AC={voltage_v_ac_rms:.1f} V RMS limit={_AC_LIMIT} V, "
            f"DC={voltage_v_dc:.1f} V limit={_DC_LIMIT} V)",
            stacklevel=2,
        )
        warns.append(
            f"Voltage exceeds SELV/PELV limits "
            f"(AC limit {_AC_LIMIT} V, DC limit {_DC_LIMIT} V)"
        )
    if borderline and is_selv_pelv:
        warns.append("Voltage is close to SELV/PELV boundary; consider 25 V limit for wet/water environments per IEC 60364-7-702")

    return {
        "ok": True,
        "circuit_type": ct,
        "voltage_v_ac_rms": voltage_v_ac_rms,
        "voltage_v_dc": voltage_v_dc,
        "is_selv_pelv": is_selv_pelv,
        "borderline": borderline,
        "ac_limit_v_rms": _AC_LIMIT,
        "dc_limit_v": _DC_LIMIT,
        "warnings": warns,
        "reference": "IEC 61140:2016 §6.1 / IEC 60364-4-41 §414",
    }
