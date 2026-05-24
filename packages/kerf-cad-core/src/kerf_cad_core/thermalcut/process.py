"""
kerf_cad_core.thermalcut.process — thermal/abrasive cutting-process formulas.

Implements the following public functions:

  laser_cut_speed(thickness_mm, power_W, material, *, assist_gas, efficiency,
                  kerf_mm, heat_content)
      Maximum cutting speed for CO₂/fibre laser via energy-balance model.

  plasma_cut_speed(thickness_mm, amperage, material, *, voltage, efficiency)
      Maximum cutting speed for plasma arc via energy-balance model.

  oxyfuel_cut_speed(thickness_mm, material)
      Empirical maximum traverse speed for oxyfuel (oxy-acetylene/oxy-propane).

  waterjet_cut_speed(thickness_mm, material, *, pump_power_kW, orifice_dia_mm,
                     abrasive_rate_kg_min, machinability_number)
      Traverse speed for abrasive-waterjet based on Hashish machinability model.

  kerf_width(process, thickness_mm, power_or_amp)
      Estimated kerf width (mm) for a given process / thickness / power.

  taper_angle(process, thickness_mm, speed_mm_min, *, nominal_speed_mm_min)
      Kerf taper half-angle (degrees) as a function of speed relative to
      nominal.  Higher speed → more taper on plasma/laser; AWJ almost zero.

  haz_width(process, thickness_mm, speed_mm_min, power_or_amp)
      Estimated heat-affected-zone (HAZ) width (mm).

  pierce_time(process, thickness_mm, *, power_W, amperage)
      Pierce / punch-through time (seconds) before traverse begins.

  lead_in_length(pierce_time_s, speed_mm_min)
      Recommended lead-in ramp length (mm) from pierce time and cut speed.

  edge_quality_regime(process, speed_mm_min, nominal_speed_mm_min)
      Qualitative edge quality string + dross risk for a given speed ratio.

  gas_consumption(process, thickness_mm, cut_length_mm, speed_mm_min)
      Assist gas (laser) or fuel+O₂ (plasma/oxyfuel) consumption (L and cost).

  abrasive_consumption(cut_length_mm, speed_mm_min, abrasive_rate_kg_min)
      Abrasive mass consumed (kg) and cost.

  select_power(process, thickness_mm, material)
      Recommended power (W, laser) or amperage (A, plasma) for a thickness.

  waterjet_params(pump_power_kW, orifice_dia_mm, *, mixing_tube_dia_mm,
                  mixing_tube_length_mm, pressure_MPa, abrasive_rate_kg_min)
      Orifice/mixing-tube sizing, jet power, standoff, and abrasive flow checks.

  part_cost(process, cut_length_mm, speed_mm_min, n_pierces, pierce_time_s,
            machine_rate_usd_hr, consumables_cost_usd)
      Total part cost = (cut length / speed + pierces × pierce_time) ×
                         machine_rate + consumables.

  process_compare(thickness_mm, material, cut_length_mm, n_pierces)
      Side-by-side comparison of laser / plasma / oxyfuel / waterjet for
      the given material and thickness.

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Warnings (too-thick-for-power, poor-edge-speed,
excessive-taper) are accumulated in the "warnings" list and do NOT prevent
a result from being returned.

Units (unless stated otherwise)
--------------------------------
thickness — mm
speed     — mm/min
power     — W (laser) or A (plasma)
length    — mm
time      — seconds
cost      — USD
pressure  — MPa
mass      — kg
volume    — L (litres)

Energy-balance model reference
-------------------------------
The laser and plasma cut-speed models follow the energy-balance approach:

    v = η·P / (ρ·c_p·(T_m - T_0) + L_f + L_v) / (t · w_k)

where η is process efficiency, P is source power (W), ρ is material density
(kg/m³), c_p is specific heat (J/kg·K), T_m is melting point (K), L_f is
specific latent heat of fusion (J/kg), L_v is specific heat of vaporisation
(J/kg, partial contribution), t is thickness (m), w_k is kerf width (m), and
(T_m - T_0) is temperature rise from ambient 293 K.

The model is simplified: it assumes 1-D heat flow into the cut front, steady
state, and that most material is ejected as liquid/vapour.  Results are
accurate to ±20 % for mild steel and aluminium under typical conditions.

References
----------
Steen & Mazumder, "Laser Material Processing", 4th ed., Springer 2010, §4.2
Metcalfe & Quigley, ESAB Plasma Cutting Handbook, 3rd ed.
Hashish, M., "A Model for Abrasive-Waterjet Machining", J. Eng. for Ind. 1989
AWS C5.2 — Recommended Practices for Plasma Arc Cutting

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MATERIALS: dict[str, dict] = {
    # ---- ferrous ----
    "mild_steel": {
        "rho": 7850.0,
        "cp": 500.0,
        "T_melt": 1808.0,
        "L_f": 272_000.0,
        "L_v": 6_090_000.0,
        "oxyfuel_ok": True,
        "wj_mnum": 100.0,
        "haz_coeff": 0.014,
    },
    "stainless_304": {
        "rho": 7900.0,
        "cp": 500.0,
        "T_melt": 1700.0,
        "L_f": 260_000.0,
        "L_v": 6_100_000.0,
        "oxyfuel_ok": False,
        "wj_mnum": 80.0,
        "haz_coeff": 0.012,
    },
    "stainless_316": {
        "rho": 7980.0,
        "cp": 500.0,
        "T_melt": 1680.0,
        "L_f": 265_000.0,
        "L_v": 6_100_000.0,
        "oxyfuel_ok": False,
        "wj_mnum": 75.0,
        "haz_coeff": 0.012,
    },
    "tool_steel": {
        "rho": 7750.0,
        "cp": 460.0,
        "T_melt": 1720.0,
        "L_f": 265_000.0,
        "L_v": 6_000_000.0,
        "oxyfuel_ok": True,
        "wj_mnum": 70.0,
        "haz_coeff": 0.015,
    },
    # ---- aluminium ----
    "aluminium_6061": {
        "rho": 2700.0,
        "cp": 900.0,
        "T_melt": 925.0,
        "L_f": 397_000.0,
        "L_v": 10_500_000.0,
        "oxyfuel_ok": False,
        "wj_mnum": 160.0,
        "haz_coeff": 0.008,
    },
    "aluminium_5052": {
        "rho": 2680.0,
        "cp": 880.0,
        "T_melt": 880.0,
        "L_f": 383_000.0,
        "L_v": 10_200_000.0,
        "oxyfuel_ok": False,
        "wj_mnum": 155.0,
        "haz_coeff": 0.008,
    },
    # ---- copper/brass ----
    "copper": {
        "rho": 8960.0,
        "cp": 385.0,
        "T_melt": 1358.0,
        "L_f": 205_000.0,
        "L_v": 4_730_000.0,
        "oxyfuel_ok": False,
        "wj_mnum": 115.0,
        "haz_coeff": 0.010,
    },
    "brass": {
        "rho": 8500.0,
        "cp": 380.0,
        "T_melt": 1173.0,
        "L_f": 168_000.0,
        "L_v": 4_500_000.0,
        "oxyfuel_ok": False,
        "wj_mnum": 120.0,
        "haz_coeff": 0.010,
    },
    # ---- titanium ----
    "titanium_gr2": {
        "rho": 4507.0,
        "cp": 520.0,
        "T_melt": 1941.0,
        "L_f": 323_000.0,
        "L_v": 8_900_000.0,
        "oxyfuel_ok": False,
        "wj_mnum": 55.0,
        "haz_coeff": 0.020,
    },
    # ---- composites / non-metals ----
    "carbon_fibre_composite": {
        "rho": 1600.0,
        "cp": 720.0,
        "T_melt": 3652.0,    # carbon sublimation ~3925 K; CFRP burns at ~700 K
        "L_f": 716_000.0,
        "L_v": 59_000_000.0,
        "oxyfuel_ok": False,
        "wj_mnum": 30.0,
        "haz_coeff": 0.006,
    },
    "glass": {
        "rho": 2500.0,
        "cp": 840.0,
        "T_melt": 1800.0,
        "L_f": 250_000.0,
        "L_v": 5_500_000.0,
        "oxyfuel_ok": False,
        "wj_mnum": 45.0,
        "haz_coeff": 0.005,
    },
    "granite": {
        "rho": 2700.0,
        "cp": 790.0,
        "T_melt": 1500.0,
        "L_f": 350_000.0,
        "L_v": 10_000_000.0,
        "oxyfuel_ok": False,
        "wj_mnum": 35.0,
        "haz_coeff": 0.004,
    },
}

_VALID_MATERIALS = sorted(_MATERIALS.keys())

# ---------------------------------------------------------------------------
# Process constants
# ---------------------------------------------------------------------------

# Laser default efficiency (fraction of delivered optical power that goes into
# the cut front — not including beam losses to optics/shield gas)
_LASER_ETA_DEFAULT = 0.55   # typical for fiber laser cutting steel with O₂ assist

# Plasma efficiency (fraction of arc power going into the cut)
_PLASMA_ETA_DEFAULT = 0.48

# Ambient temperature (K)
_T_AMBIENT = 293.0

# ---------------------------------------------------------------------------
# Oxyfuel empirical speed table
# Ref: Lincoln Electric oxyfuel guide; speeds in mm/min for mild steel
# Format: (thickness_mm_max, speed_mm_min)
# ---------------------------------------------------------------------------
_OXYFUEL_STEEL_TABLE: list[tuple[float, float]] = [
    (6.0,   900.0),
    (12.0,  600.0),
    (19.0,  440.0),
    (25.0,  360.0),
    (38.0,  270.0),
    (50.0,  220.0),
    (75.0,  160.0),
    (100.0, 120.0),
    (150.0,  80.0),
    (200.0,  60.0),
    (300.0,  38.0),
]

# ---------------------------------------------------------------------------
# Plasma: empirical arc voltage (V) vs thickness
# ---------------------------------------------------------------------------
_PLASMA_VOLTAGE_DEFAULT = 130.0  # V — representative for 100+ A plasma

# ---------------------------------------------------------------------------
# Gas consumption data (L/min) by process and thickness band
# ---------------------------------------------------------------------------
# Laser: assist gas (N₂ or O₂) at nozzle
_LASER_GAS_RATE_L_MIN = {
    "O2":  15.0,   # L/min at 0.5–0.8 MPa for steel <20 mm
    "N2":  30.0,   # L/min at 1.2–2.0 MPa for stainless / aluminium
    "Air": 40.0,
}
_LASER_GAS_COST_PER_L = {
    "O2":  0.008,
    "N2":  0.003,
    "Air": 0.001,
}
_LASER_GAS_DEFAULT = "O2"

# Oxyfuel: fuel (acetylene) + preheat O₂ + cutting O₂
# Simplified: fuel ~10 L/min, O₂ (preheat+cut) ~30–70 L/min — use midpoint
_OXYFUEL_FUEL_RATE_L_MIN = 10.0     # acetylene
_OXYFUEL_O2_RATE_L_MIN   = 45.0    # oxygen (preheat + cutting)
_OXYFUEL_FUEL_COST_PER_L = 0.020   # USD/L acetylene
_OXYFUEL_O2_COST_PER_L   = 0.008   # USD/L oxygen

# Plasma: shield gas ~15 L/min (air or N₂)
_PLASMA_GAS_RATE_L_MIN  = 15.0
_PLASMA_GAS_COST_PER_L  = 0.003    # USD/L

# AWJ: abrasive (garnet) cost
_ABRASIVE_COST_PER_KG = 0.45       # USD/kg garnet #80

# ---------------------------------------------------------------------------
# Default machine rates (USD/hr) — conservative shop-floor estimates
# ---------------------------------------------------------------------------
_MACHINE_RATE_DEFAULT: dict[str, float] = {
    "laser":    65.0,
    "plasma":   45.0,
    "oxyfuel":  25.0,
    "waterjet": 55.0,
}

# ---------------------------------------------------------------------------
# 1. laser_cut_speed
# ---------------------------------------------------------------------------

def laser_cut_speed(
    thickness_mm: float,
    power_W: float,
    material: str = "mild_steel",
    *,
    assist_gas: str = "O2",
    efficiency: float | None = None,
    kerf_mm: float | None = None,
    heat_content: float | None = None,
) -> dict:
    """
    Maximum cutting speed for a laser (CO₂ or fibre) via energy-balance model.

    The model computes the speed at which the laser can supply exactly the
    energy needed to heat, melt, and partially vaporise the material through
    the kerf cross-section.

    Parameters
    ----------
    thickness_mm : float
        Material thickness (mm).  Must be > 0.
    power_W : float
        Laser output power at the workpiece (W).  Must be > 0.
    material : str
        Material key (default "mild_steel").
    assist_gas : str
        Assist gas type: "O2" (default), "N2", or "Air".
    efficiency : float | None
        Fraction of laser power absorbed at cut front (0 < η ≤ 1).
        Defaults to 0.55 for O₂-assist, 0.45 for N₂/Air.
    kerf_mm : float | None
        Override kerf width (mm).  If None, estimated from power & thickness.
    heat_content : float | None
        Override total specific cutting energy (J/kg).  If None, computed
        from material database (c_p·ΔT + L_f + partial L_v).

    Returns
    -------
    dict
        ok              : True
        speed_mm_min    : maximum cutting speed (mm/min)
        speed_m_min     : same in m/min
        thickness_mm    : input thickness (mm)
        power_W         : laser power used (W)
        efficiency      : η used
        kerf_mm         : kerf width used (mm)
        heat_content_J_kg : specific energy used (J/kg)
        material        : material name
        warnings        : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("thickness_mm", thickness_mm)
    if err:
        return _err(err)
    err = _guard_positive("power_W", power_W)
    if err:
        return _err(err)

    mat_key = str(material).strip().lower()
    if mat_key not in _MATERIALS:
        return _err(f"Unknown material {material!r}. Supported: {_VALID_MATERIALS}.")

    mat = _MATERIALS[mat_key]

    gas = str(assist_gas).strip().upper()
    if gas not in _LASER_GAS_RATE_L_MIN:
        return _err(
            f"Unknown assist_gas {assist_gas!r}. Supported: {list(_LASER_GAS_RATE_L_MIN.keys())}."
        )

    # Efficiency
    if efficiency is None:
        eta = _LASER_ETA_DEFAULT if gas == "O2" else 0.45
    else:
        e_err = _guard_positive("efficiency", efficiency)
        if e_err:
            return _err(e_err)
        if float(efficiency) > 1.0:
            return _err("efficiency must be <= 1.0")
        eta = float(efficiency)

    t_mm = float(thickness_mm)
    P = float(power_W)

    # Kerf width estimate (mm): empirical — wider for thick and low power
    if kerf_mm is None:
        # Empirical: w_k = 0.1 + 0.04 * t^0.5 for laser (Steen §4)
        w_k_mm = 0.10 + 0.04 * math.sqrt(t_mm)
        # Clamp to reasonable range
        w_k_mm = max(0.05, min(w_k_mm, 3.0))
    else:
        e_err = _guard_positive("kerf_mm", kerf_mm)
        if e_err:
            return _err(e_err)
        w_k_mm = float(kerf_mm)

    # Specific energy (J/kg)
    if heat_content is None:
        dT = mat["T_melt"] - _T_AMBIENT
        # Include 15% of vaporisation latent heat (material partly vapourised)
        H = mat["cp"] * dT + mat["L_f"] + 0.15 * mat["L_v"]
    else:
        e_err = _guard_positive("heat_content", heat_content)
        if e_err:
            return _err(e_err)
        H = float(heat_content)

    # Energy-balance: v = η·P / (ρ·H·t·w_k)
    # v in m/s; convert to mm/min
    t_m = t_mm * 1e-3
    w_k_m = w_k_mm * 1e-3
    rho = mat["rho"]

    denom = rho * H * t_m * w_k_m
    if denom <= 0:
        return _err("Internal error: zero denominator in energy balance.")

    v_m_s = eta * P / denom
    v_mm_min = v_m_s * 60_000.0  # m/s → mm/min

    # Warnings
    # Too-thick-for-power heuristic: if speed < 100 mm/min, warn
    if v_mm_min < 100.0:
        warnings.append(
            f"Speed {v_mm_min:.0f} mm/min is very low — material may be too thick "
            f"for {P:.0f} W; consider higher power or a different process."
        )

    # Practical upper limit for laser (material-dependent preheat not modelled above ~200 mm)
    if t_mm > 50.0 and mat_key in ("mild_steel", "tool_steel"):
        warnings.append(
            f"Thickness {t_mm} mm exceeds practical laser cutting range "
            f"for {mat_key}; consider plasma or oxyfuel."
        )
    if t_mm > 30.0 and mat_key in ("aluminium_6061", "aluminium_5052"):
        warnings.append(
            f"Thickness {t_mm} mm is near the practical limit for laser cutting "
            f"aluminium; edge quality may be poor."
        )

    return {
        "ok": True,
        "speed_mm_min": round(v_mm_min, 2),
        "speed_m_min": round(v_mm_min / 1000.0, 4),
        "thickness_mm": t_mm,
        "power_W": P,
        "efficiency": eta,
        "kerf_mm": round(w_k_mm, 4),
        "heat_content_J_kg": round(H, 0),
        "material": mat_key,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. plasma_cut_speed
# ---------------------------------------------------------------------------

def plasma_cut_speed(
    thickness_mm: float,
    amperage: float,
    material: str = "mild_steel",
    *,
    voltage: float = _PLASMA_VOLTAGE_DEFAULT,
    efficiency: float = _PLASMA_ETA_DEFAULT,
) -> dict:
    """
    Maximum cutting speed for plasma arc via energy-balance model.

    Arc power = voltage × amperage.  The energy-balance formula is the same
    as for laser, but kerf width is wider (plasma has larger beam spot).

    Parameters
    ----------
    thickness_mm : float
        Material thickness (mm).  Must be > 0.
    amperage : float
        Plasma arc current (A).  Must be > 0.
    material : str
        Material key.
    voltage : float
        Arc voltage (V).  Default 130 V.
    efficiency : float
        Fraction of arc power going into cut front.  Default 0.48.

    Returns
    -------
    dict
        ok           : True
        speed_mm_min : maximum cutting speed (mm/min)
        amperage     : arc current (A)
        voltage      : arc voltage (V)
        power_W      : arc power (W)
        kerf_mm      : estimated kerf width (mm)
        warnings     : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("thickness_mm", thickness_mm)
    if err:
        return _err(err)
    err = _guard_positive("amperage", amperage)
    if err:
        return _err(err)
    err = _guard_positive("voltage", voltage)
    if err:
        return _err(err)
    err = _guard_positive("efficiency", efficiency)
    if err:
        return _err(err)
    if float(efficiency) > 1.0:
        return _err("efficiency must be <= 1.0")

    mat_key = str(material).strip().lower()
    if mat_key not in _MATERIALS:
        return _err(f"Unknown material {material!r}. Supported: {_VALID_MATERIALS}.")
    mat = _MATERIALS[mat_key]

    t_mm = float(thickness_mm)
    I = float(amperage)
    V = float(voltage)
    eta = float(efficiency)

    P = I * V  # arc power (W)

    # Plasma kerf is wider: empirical w_k = 1.5 + 0.12 * t^0.6 (mm)
    w_k_mm = 1.5 + 0.12 * (t_mm ** 0.6)
    w_k_mm = max(1.0, min(w_k_mm, 15.0))

    # Specific energy (same model as laser)
    dT = mat["T_melt"] - _T_AMBIENT
    H = mat["cp"] * dT + mat["L_f"] + 0.10 * mat["L_v"]

    t_m = t_mm * 1e-3
    w_k_m = w_k_mm * 1e-3
    rho = mat["rho"]

    denom = rho * H * t_m * w_k_m
    if denom <= 0:
        return _err("Internal error: zero denominator in energy balance.")

    v_m_s = eta * P / denom
    v_mm_min = v_m_s * 60_000.0

    if v_mm_min < 50.0:
        warnings.append(
            f"Speed {v_mm_min:.0f} mm/min is very low — material may be too thick "
            f"for {I:.0f} A; consider higher amperage."
        )
    if t_mm > 150.0:
        warnings.append(
            f"Thickness {t_mm} mm is beyond the practical range for plasma "
            f"cutting; consider oxyfuel or mechanised cutting."
        )

    return {
        "ok": True,
        "speed_mm_min": round(v_mm_min, 2),
        "speed_m_min": round(v_mm_min / 1000.0, 4),
        "thickness_mm": t_mm,
        "amperage": I,
        "voltage": V,
        "power_W": round(P, 1),
        "efficiency": eta,
        "kerf_mm": round(w_k_mm, 4),
        "material": mat_key,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. oxyfuel_cut_speed
# ---------------------------------------------------------------------------

def oxyfuel_cut_speed(
    thickness_mm: float,
    material: str = "mild_steel",
) -> dict:
    """
    Empirical maximum traverse speed for oxyfuel (oxy-acetylene / oxy-propane).

    Only valid for ferrous materials (mild steel, tool steel).  Uses a
    piecewise-linear interpolation from published Lincoln Electric data.

    Parameters
    ----------
    thickness_mm : float
        Material thickness (mm).  Must be in range [1, 300] mm.
    material : str
        Must be an oxyfuel-compatible material.

    Returns
    -------
    dict
        ok           : True
        speed_mm_min : recommended maximum cutting speed (mm/min)
        thickness_mm : input thickness (mm)
        material     : material name
        warnings     : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("thickness_mm", thickness_mm)
    if err:
        return _err(err)

    mat_key = str(material).strip().lower()
    if mat_key not in _MATERIALS:
        return _err(f"Unknown material {material!r}. Supported: {_VALID_MATERIALS}.")
    mat = _MATERIALS[mat_key]

    if not mat["oxyfuel_ok"]:
        return _err(
            f"Material {mat_key!r} is not compatible with oxyfuel cutting "
            f"(requires ferrous/steel). Use laser, plasma, or waterjet."
        )

    t_mm = float(thickness_mm)

    if t_mm < 1.0:
        return _err("thickness_mm must be >= 1 mm for oxyfuel cutting.")
    if t_mm > 300.0:
        warnings.append(
            f"Thickness {t_mm} mm exceeds the typical oxyfuel range (≤ 300 mm); "
            f"use mechanised oxyfuel or consider alternative processes."
        )

    # Piecewise linear interpolation in the table
    table = _OXYFUEL_STEEL_TABLE
    if t_mm <= table[0][0]:
        speed = table[0][1]
    elif t_mm >= table[-1][0]:
        speed = table[-1][1]
        if t_mm > table[-1][0]:
            warnings.append(
                f"Thickness {t_mm} mm extrapolated beyond table maximum "
                f"{table[-1][0]} mm; result may be less accurate."
            )
    else:
        # Interpolate
        speed = table[0][1]
        for i in range(len(table) - 1):
            t0, v0 = table[i]
            t1, v1 = table[i + 1]
            if t0 <= t_mm <= t1:
                frac = (t_mm - t0) / (t1 - t0)
                speed = v0 + frac * (v1 - v0)
                break

    if t_mm >= 150.0:
        warnings.append(
            f"Thickness {t_mm} mm is heavy section; preheat time will be "
            f"significant; pierce/lead-in cycle adds substantially to job time."
        )

    return {
        "ok": True,
        "speed_mm_min": round(speed, 1),
        "speed_m_min": round(speed / 1000.0, 4),
        "thickness_mm": t_mm,
        "material": mat_key,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. waterjet_cut_speed
# ---------------------------------------------------------------------------

def waterjet_cut_speed(
    thickness_mm: float,
    material: str = "mild_steel",
    *,
    pump_power_kW: float = 30.0,
    orifice_dia_mm: float = 0.356,
    abrasive_rate_kg_min: float = 0.45,
    machinability_number: float | None = None,
) -> dict:
    """
    Traverse speed for abrasive-waterjet (AWJ) based on Hashish machinability model.

    Hashish (1989) cutting rate model:

        v = (C_m · P_j^1.25 · m_a^0.687) / (t · d_f^1.15 · N_m)

    where:
        C_m  = empirical model constant (≈ 47 000 in SI)
        P_j  = jet power (W)
        m_a  = abrasive mass flow rate (kg/s)
        t    = thickness (m)
        d_f  = mixing-tube (focusing tube) diameter (m) — estimated from orifice
        N_m  = machinability number (dimensionless; higher = easier to cut)

    Parameters
    ----------
    thickness_mm : float
        Material thickness (mm).
    material : str
        Material key.
    pump_power_kW : float
        Hydraulic pump power (kW).  Default 30 kW.
    orifice_dia_mm : float
        Water orifice diameter (mm).  Default 0.356 mm.
    abrasive_rate_kg_min : float
        Abrasive (garnet) feed rate (kg/min).  Default 0.45 kg/min.
    machinability_number : float | None
        Override the material machinability number.  If None, uses the
        material database value.

    Returns
    -------
    dict
        ok                    : True
        speed_mm_min          : traverse speed (mm/min)
        pump_power_kW         : pump power used (kW)
        jet_power_W           : estimated hydraulic power at nozzle (W) — 75% efficiency
        orifice_dia_mm        : orifice diameter (mm)
        mixing_tube_dia_mm    : estimated mixing-tube diameter (mm)
        abrasive_rate_kg_min  : abrasive feed rate (kg/min)
        machinability_number  : N_m used
        warnings              : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("thickness_mm", thickness_mm)
    if err:
        return _err(err)
    err = _guard_positive("pump_power_kW", pump_power_kW)
    if err:
        return _err(err)
    err = _guard_positive("orifice_dia_mm", orifice_dia_mm)
    if err:
        return _err(err)
    err = _guard_positive("abrasive_rate_kg_min", abrasive_rate_kg_min)
    if err:
        return _err(err)

    mat_key = str(material).strip().lower()
    if mat_key not in _MATERIALS:
        return _err(f"Unknown material {material!r}. Supported: {_VALID_MATERIALS}.")
    mat = _MATERIALS[mat_key]

    t_mm = float(thickness_mm)

    # Machinability number
    if machinability_number is not None:
        e_err = _guard_positive("machinability_number", machinability_number)
        if e_err:
            return _err(e_err)
        N_m = float(machinability_number)
    else:
        N_m = mat["wj_mnum"]

    # Jet power: pump efficiency ~75%
    P_j = float(pump_power_kW) * 1000.0 * 0.75  # W

    # Mixing-tube diameter: standard ratio ~3.5× orifice
    d_orifice_m = float(orifice_dia_mm) * 1e-3
    d_f_m = d_orifice_m * 3.5

    # Abrasive flow rate in kg/s
    m_a_kg_s = float(abrasive_rate_kg_min) / 60.0

    t_m = t_mm * 1e-3

    # Hashish (1989) model constant — fully SI (speed result in m/s):
    #   v = C_m · P_j^1.25 · m_a^0.687 · N_m / (t · d_f^1.15)
    #   N_m in numerator: higher machinability number → higher speed
    #   C_m ≈ 1.195e-14  (calibrated to garnet #80 / mild steel N_m=100 /
    #                     30 kW pump / 0.356 mm orifice / 0.45 kg/min
    #                     → ~150 mm/min at 10 mm thickness)
    C_m = 1.195e-14

    # Numerator and denominator (all SI: P in W, m_a in kg/s, t in m, d_f in m)
    numerator = C_m * (P_j ** 1.25) * (m_a_kg_s ** 0.687) * N_m
    denominator = t_m * (d_f_m ** 1.15)

    if denominator <= 0:
        return _err("Internal error: zero denominator in Hashish model.")

    v_m_s = numerator / denominator     # m/s
    v_mm_min = v_m_s * 60_000.0         # mm/min

    # Cap at 10 m/min for AWJ (physically unrealistic above that)
    if v_mm_min > 10_000.0:
        v_mm_min = 10_000.0
        warnings.append(
            "Computed speed capped at 10 000 mm/min — verify pump power and "
            "abrasive rate inputs."
        )

    if v_mm_min < 10.0:
        warnings.append(
            f"Speed {v_mm_min:.1f} mm/min is very low — material may be too "
            f"thick / hard for the given pump power."
        )

    if t_mm > 200.0:
        warnings.append(
            f"Thickness {t_mm} mm is near the practical AWJ limit (~300 mm); "
            f"taper will be significant."
        )

    return {
        "ok": True,
        "speed_mm_min": round(v_mm_min, 2),
        "speed_m_min": round(v_mm_min / 1000.0, 5),
        "thickness_mm": t_mm,
        "pump_power_kW": float(pump_power_kW),
        "jet_power_W": round(P_j, 1),
        "orifice_dia_mm": float(orifice_dia_mm),
        "mixing_tube_dia_mm": round(d_f_m * 1000.0, 4),
        "abrasive_rate_kg_min": float(abrasive_rate_kg_min),
        "machinability_number": N_m,
        "material": mat_key,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. kerf_width
# ---------------------------------------------------------------------------

def kerf_width(
    process: str,
    thickness_mm: float,
    power_or_amp: float,
) -> dict:
    """
    Estimated kerf width (mm) for a given process, thickness, and power/current.

    Empirical formulas based on published data ranges:

      laser    : w_k = 0.10 + 0.04·√t        (narrow; varies with power)
      plasma   : w_k = 1.50 + 0.12·t^0.6     (wider)
      oxyfuel  : w_k = 0.80 + 0.06·t^0.7     (medium)
      waterjet : w_k = d_orifice·3.5 + 0.02·t (very narrow, slight taper)
                       where d_orifice is estimated from power as 0.25 + 0.005·√P mm

    For waterjet, power_or_amp represents pump power in kW.

    Parameters
    ----------
    process : str
        "laser", "plasma", "oxyfuel", or "waterjet".
    thickness_mm : float
        Material thickness (mm).
    power_or_amp : float
        Laser power (W), plasma amperage (A), oxyfuel oxygen flow (L/min),
        or waterjet pump power (kW).  Used to scale kerf width.

    Returns
    -------
    dict
        ok           : True
        kerf_mm      : estimated kerf width (mm)
        process      : process name
        thickness_mm : input thickness (mm)
        warnings     : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("thickness_mm", thickness_mm)
    if err:
        return _err(err)
    err = _guard_positive("power_or_amp", power_or_amp)
    if err:
        return _err(err)

    proc = str(process).strip().lower()
    t_mm = float(thickness_mm)
    P = float(power_or_amp)

    if proc == "laser":
        # w_k slightly increases with power (larger spot for high power)
        power_factor = 1.0 + 0.00005 * P
        w_k = (0.10 + 0.04 * math.sqrt(t_mm)) * power_factor
        w_k = max(0.05, min(w_k, 5.0))
    elif proc == "plasma":
        # Plasma kerf wider and more thickness-dependent
        amp_factor = 1.0 + 0.0002 * P
        w_k = (1.50 + 0.12 * (t_mm ** 0.6)) * amp_factor
        w_k = max(1.0, min(w_k, 20.0))
    elif proc == "oxyfuel":
        # Oxyfuel kerf
        w_k = 0.80 + 0.06 * (t_mm ** 0.7)
        w_k = max(0.5, min(w_k, 10.0))
    elif proc == "waterjet":
        # AWJ: orifice ~0.25 + 0.005·√(pump_kW) mm; mixing tube = 3.5× orifice
        d_orifice = 0.25 + 0.005 * math.sqrt(P)
        w_k = d_orifice * 3.5 + 0.02 * t_mm
        w_k = max(0.3, min(w_k, 5.0))
    else:
        return _err(
            f"Unknown process {process!r}. Supported: 'laser', 'plasma', "
            f"'oxyfuel', 'waterjet'."
        )

    if w_k > 3.0 and proc == "laser":
        warnings.append(
            f"Laser kerf {w_k:.2f} mm is wide — check beam focus and nozzle condition."
        )

    return {
        "ok": True,
        "kerf_mm": round(w_k, 4),
        "process": proc,
        "thickness_mm": t_mm,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 6. taper_angle
# ---------------------------------------------------------------------------

def taper_angle(
    process: str,
    thickness_mm: float,
    speed_mm_min: float,
    *,
    nominal_speed_mm_min: float | None = None,
) -> dict:
    """
    Kerf taper half-angle (degrees) as a function of speed relative to nominal.

    At nominal speed the taper is at its minimum.  Above nominal the kerf
    becomes more tapered (V-shaped); below nominal the kerf can be reverse-
    tapered or barrel-shaped on some processes.

    The model uses:

        θ = θ_base + θ_speed_penalty · (v / v_nom - 1)  if v > v_nom
        θ = θ_base                                        if v ≤ v_nom

    where θ_base and θ_speed_penalty are process-specific empirical constants.

    AWJ taper is mostly due to abrasive jet divergence and is nearly
    independent of speed for quality cutting (< 1°).

    Parameters
    ----------
    process : str
        "laser", "plasma", "oxyfuel", or "waterjet".
    thickness_mm : float
        Material thickness (mm).
    speed_mm_min : float
        Actual traverse speed (mm/min).
    nominal_speed_mm_min : float | None
        Nominal / optimal speed (mm/min).  If None, a default of the computed
        speed at 100% efficiency is used (set to 80% of speed_mm_min as a
        rough heuristic when unknown).

    Returns
    -------
    dict
        ok                   : True
        taper_half_angle_deg : kerf taper half-angle (degrees)
        taper_angle_total_deg: total included taper angle (2 × half)
        speed_ratio          : v / v_nom
        process              : process name
        warnings             : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("thickness_mm", thickness_mm)
    if err:
        return _err(err)
    err = _guard_positive("speed_mm_min", speed_mm_min)
    if err:
        return _err(err)

    proc = str(process).strip().lower()
    t_mm = float(thickness_mm)
    v = float(speed_mm_min)

    if nominal_speed_mm_min is None:
        v_nom = v * 0.80  # treat actual as 80% of nominal → mild taper by default
    else:
        e_err = _guard_positive("nominal_speed_mm_min", nominal_speed_mm_min)
        if e_err:
            return _err(e_err)
        v_nom = float(nominal_speed_mm_min)

    # Process-specific empirical taper base angles (degrees, half-angle)
    # and speed-penalty coefficient
    _taper_params: dict[str, tuple[float, float]] = {
        "laser":    (0.5, 2.5),   # (base_deg, penalty_deg per unit speed ratio above 1)
        "plasma":   (1.5, 4.0),
        "oxyfuel":  (1.0, 3.0),
        "waterjet": (0.3, 0.5),
    }

    if proc not in _taper_params:
        return _err(
            f"Unknown process {process!r}. Supported: 'laser', 'plasma', "
            f"'oxyfuel', 'waterjet'."
        )

    theta_base, theta_penalty = _taper_params[proc]
    speed_ratio = v / v_nom

    if speed_ratio > 1.0:
        theta_half = theta_base + theta_penalty * (speed_ratio - 1.0)
    else:
        theta_half = theta_base

    # Thick sections add additional taper regardless of speed
    if t_mm > 25.0:
        theta_half += 0.03 * (t_mm - 25.0) / 25.0  # +0.03° per extra 25 mm

    # Excessive taper warning: > 5° half-angle is problematic for most applications
    if theta_half > 5.0:
        warnings.append(
            f"Taper half-angle {theta_half:.1f}° is excessive — reduce speed or "
            f"increase power; consider a quality cut setting."
        )
    elif theta_half > 2.0:
        warnings.append(
            f"Taper half-angle {theta_half:.1f}° may require secondary finishing "
            f"for tight-tolerance parts."
        )

    return {
        "ok": True,
        "taper_half_angle_deg": round(theta_half, 3),
        "taper_angle_total_deg": round(theta_half * 2.0, 3),
        "speed_ratio": round(speed_ratio, 4),
        "nominal_speed_mm_min": round(v_nom, 2),
        "actual_speed_mm_min": round(v, 2),
        "process": proc,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. haz_width
# ---------------------------------------------------------------------------

def haz_width(
    process: str,
    thickness_mm: float,
    speed_mm_min: float,
    power_or_amp: float,
    material: str = "mild_steel",
) -> dict:
    """
    Estimated heat-affected-zone (HAZ) width (mm) at the cut edge.

    Empirical model:

        HAZ = k_mat · (P / (v · t))^0.5

    where P is power input (W), v is traverse speed (m/s), t is thickness (m),
    and k_mat is a material-dependent HAZ coefficient.

    AWJ produces negligible HAZ (< 0.05 mm), modelled separately.

    Waterjet: HAZ = 0.0 (cold cutting).

    Parameters
    ----------
    process : str
        "laser", "plasma", "oxyfuel", or "waterjet".
    thickness_mm : float
        Material thickness (mm).
    speed_mm_min : float
        Traverse speed (mm/min).
    power_or_amp : float
        Laser power (W), plasma amperage (A), or oxyfuel oxygen flow (L/min).
        For waterjet, any positive value is accepted (result is always 0).
    material : str
        Material key.

    Returns
    -------
    dict
        ok           : True
        haz_mm       : estimated HAZ width (mm) per edge
        process      : process name
        material     : material name
        warnings     : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("thickness_mm", thickness_mm)
    if err:
        return _err(err)
    err = _guard_positive("speed_mm_min", speed_mm_min)
    if err:
        return _err(err)
    err = _guard_positive("power_or_amp", power_or_amp)
    if err:
        return _err(err)

    proc = str(process).strip().lower()
    mat_key = str(material).strip().lower()

    if mat_key not in _MATERIALS:
        return _err(f"Unknown material {material!r}. Supported: {_VALID_MATERIALS}.")

    mat = _MATERIALS[mat_key]
    t_mm = float(thickness_mm)
    v_mm_min = float(speed_mm_min)
    P_raw = float(power_or_amp)

    if proc == "waterjet":
        return {
            "ok": True,
            "haz_mm": 0.0,
            "process": proc,
            "material": mat_key,
            "warnings": ["Waterjet is a cold-cutting process; HAZ is negligible."],
        }

    # Convert plasma amperage to approximate arc power W
    if proc == "plasma":
        P_W = P_raw * _PLASMA_VOLTAGE_DEFAULT
    elif proc == "oxyfuel":
        # Oxyfuel: combustion power approximated as O₂ flow (L/min) × 40 W·min/L
        P_W = P_raw * 40.0 * 60.0  # very rough
    elif proc == "laser":
        P_W = P_raw
    else:
        return _err(
            f"Unknown process {process!r}. Supported: 'laser', 'plasma', "
            f"'oxyfuel', 'waterjet'."
        )

    v_m_s = v_mm_min / 60_000.0  # mm/min → m/s
    t_m = t_mm * 1e-3

    if v_m_s <= 0 or t_m <= 0:
        return _err("speed_mm_min and thickness_mm must be > 0.")

    k = mat["haz_coeff"]
    # HAZ = k · sqrt(P / (v · t))
    haz_mm = k * math.sqrt(P_W / (v_m_s * t_m))
    haz_mm = max(0.01, haz_mm)

    if haz_mm > 3.0:
        warnings.append(
            f"HAZ width {haz_mm:.2f} mm is large — may affect mechanical properties. "
            f"Increase speed or consider waterjet/laser for heat-sensitive materials."
        )
    if haz_mm > 1.0 and mat_key in ("titanium_gr2", "stainless_304", "stainless_316"):
        warnings.append(
            f"HAZ width {haz_mm:.2f} mm on {mat_key} risks sensitisation / "
            f"phase changes; consider low-heat-input parameters or waterjet."
        )

    return {
        "ok": True,
        "haz_mm": round(haz_mm, 4),
        "process": proc,
        "material": mat_key,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 8. pierce_time
# ---------------------------------------------------------------------------

def pierce_time(
    process: str,
    thickness_mm: float,
    *,
    power_W: float | None = None,
    amperage: float | None = None,
) -> dict:
    """
    Pierce / punch-through time (seconds) before traverse begins.

    Empirical models:

      laser:    t_p = 0.05 · t^1.3 / (P / 1000)^0.4  (P in W)
      plasma:   t_p = 0.10 · t^0.9 / (I / 100)^0.5   (I in A)
      oxyfuel:  t_p = 2.0  + 0.40 · t                 (preheat dominates)
      waterjet: t_p = 0.02 · t                         (fast traverse-start)

    Parameters
    ----------
    process : str
        "laser", "plasma", "oxyfuel", or "waterjet".
    thickness_mm : float
        Material thickness (mm).
    power_W : float | None
        Laser power (W).  Required for process="laser".
    amperage : float | None
        Plasma current (A).  Required for process="plasma".

    Returns
    -------
    dict
        ok              : True
        pierce_time_s   : pierce time (seconds)
        process         : process name
        thickness_mm    : input thickness (mm)
        warnings        : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("thickness_mm", thickness_mm)
    if err:
        return _err(err)

    proc = str(process).strip().lower()
    t_mm = float(thickness_mm)

    if proc == "laser":
        if power_W is None:
            return _err("power_W is required for laser pierce_time.")
        e_err = _guard_positive("power_W", power_W)
        if e_err:
            return _err(e_err)
        P_kW = float(power_W) / 1000.0
        tp = 0.05 * (t_mm ** 1.3) / max((P_kW ** 0.4), 0.01)

    elif proc == "plasma":
        if amperage is None:
            return _err("amperage is required for plasma pierce_time.")
        e_err = _guard_positive("amperage", amperage)
        if e_err:
            return _err(e_err)
        I100 = float(amperage) / 100.0
        tp = 0.10 * (t_mm ** 0.9) / max((I100 ** 0.5), 0.01)

    elif proc == "oxyfuel":
        tp = 2.0 + 0.40 * t_mm
        if t_mm > 50.0:
            warnings.append(
                f"Oxyfuel preheat for {t_mm} mm will require additional warm-up "
                f"time not included in this model."
            )

    elif proc == "waterjet":
        tp = 0.02 * t_mm

    else:
        return _err(
            f"Unknown process {process!r}. Supported: 'laser', 'plasma', "
            f"'oxyfuel', 'waterjet'."
        )

    tp = max(0.01, tp)

    if tp > 30.0:
        warnings.append(
            f"Pierce time {tp:.1f} s is long; stationary piercing may cause "
            f"localised burn-back / dross accumulation — consider lead-in piercing."
        )

    return {
        "ok": True,
        "pierce_time_s": round(tp, 3),
        "process": proc,
        "thickness_mm": t_mm,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 9. lead_in_length
# ---------------------------------------------------------------------------

def lead_in_length(
    pierce_time_s: float,
    speed_mm_min: float,
) -> dict:
    """
    Recommended lead-in ramp length (mm) from pierce time and cut speed.

    The lead-in is the distance the machine travels at reduced feed (50%
    of cut speed) from the pierce point to the cut contour start.  A simple
    heuristic: L_lead = (v_cut × 0.50) × pierce_time_s / 60.

    Parameters
    ----------
    pierce_time_s : float
        Pierce time (seconds).  Must be >= 0.
    speed_mm_min : float
        Nominal cut speed (mm/min).  Must be > 0.

    Returns
    -------
    dict
        ok              : True
        lead_in_mm      : recommended lead-in length (mm)
        pierce_time_s   : input pierce time (s)
        cut_speed_mm_min: input cut speed (mm/min)
    """
    err = _guard_nonneg("pierce_time_s", pierce_time_s)
    if err:
        return _err(err)
    err = _guard_positive("speed_mm_min", speed_mm_min)
    if err:
        return _err(err)

    tp = float(pierce_time_s)
    v = float(speed_mm_min)

    # Lead-in at 50% speed over pierce_time duration
    lead_mm = (v * 0.50) * (tp / 60.0)
    lead_mm = max(1.0, lead_mm)  # always at least 1 mm

    return {
        "ok": True,
        "lead_in_mm": round(lead_mm, 3),
        "pierce_time_s": tp,
        "cut_speed_mm_min": v,
    }


# ---------------------------------------------------------------------------
# 10. edge_quality_regime
# ---------------------------------------------------------------------------

def edge_quality_regime(
    process: str,
    speed_mm_min: float,
    nominal_speed_mm_min: float,
) -> dict:
    """
    Qualitative edge quality string and dross risk for a given speed ratio.

    The speed ratio v / v_nom determines the cutting regime:

      v < 0.6·v_nom   → "too slow"   — excessive dross, burn, wide kerf
      v in [0.6, 0.85) → "slow"       — some dross, slight burn
      v in [0.85, 1.15] → "optimal"   — clean cut, minimal dross
      v in (1.15, 1.4] → "fast"       — minor top-edge chamfer, possible dross
      v > 1.4·v_nom   → "too fast"   — incomplete cut / striations, dross

    Parameters
    ----------
    process : str
        "laser", "plasma", "oxyfuel", or "waterjet" (informational only).
    speed_mm_min : float
        Actual traverse speed (mm/min).
    nominal_speed_mm_min : float
        Nominal / optimal speed (mm/min).

    Returns
    -------
    dict
        ok               : True
        regime           : str — "too_slow", "slow", "optimal", "fast", "too_fast"
        dross_risk       : str — "high", "moderate", "low"
        edge_quality     : str — "poor", "fair", "good", "excellent"
        speed_ratio      : v / v_nom
        warnings         : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("speed_mm_min", speed_mm_min)
    if err:
        return _err(err)
    err = _guard_positive("nominal_speed_mm_min", nominal_speed_mm_min)
    if err:
        return _err(err)

    proc = str(process).strip().lower()
    if proc not in ("laser", "plasma", "oxyfuel", "waterjet"):
        return _err(
            f"Unknown process {process!r}. Supported: 'laser', 'plasma', "
            f"'oxyfuel', 'waterjet'."
        )

    ratio = float(speed_mm_min) / float(nominal_speed_mm_min)

    if ratio < 0.6:
        regime = "too_slow"
        dross = "high"
        quality = "poor"
        warnings.append(
            f"Speed ratio {ratio:.2f} (< 0.60) — excessive heat input; "
            f"severe dross and possible burn-through."
        )
    elif ratio < 0.85:
        regime = "slow"
        dross = "moderate"
        quality = "fair"
        warnings.append(
            f"Speed ratio {ratio:.2f} — speed is below optimal; "
            f"moderate dross expected on lower edge."
        )
    elif ratio <= 1.15:
        regime = "optimal"
        dross = "low"
        quality = "excellent"
    elif ratio <= 1.40:
        regime = "fast"
        dross = "moderate"
        quality = "good"
        warnings.append(
            f"Speed ratio {ratio:.2f} — speed is above nominal; "
            f"possible top-edge chamfer and minor dross on lower edge."
        )
    else:
        regime = "too_fast"
        dross = "high"
        quality = "poor"
        warnings.append(
            f"Speed ratio {ratio:.2f} (> 1.40) — insufficient energy input; "
            f"incomplete cut / heavy striations likely."
        )

    return {
        "ok": True,
        "regime": regime,
        "dross_risk": dross,
        "edge_quality": quality,
        "speed_ratio": round(ratio, 4),
        "speed_mm_min": float(speed_mm_min),
        "nominal_speed_mm_min": float(nominal_speed_mm_min),
        "process": proc,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 11. gas_consumption
# ---------------------------------------------------------------------------

def gas_consumption(
    process: str,
    thickness_mm: float,
    cut_length_mm: float,
    speed_mm_min: float,
    *,
    assist_gas: str = "O2",
) -> dict:
    """
    Assist gas (laser) or fuel+O₂ (oxyfuel) / shield gas (plasma) consumption.

    For laser and plasma: gas is consumed during active cutting only.
    For oxyfuel: preheat gas is also consumed (assumed at 50% of cut rate
    during a 5 s preheat per pierce, but pierce count not available here;
    result is per-cut-length only).

    Parameters
    ----------
    process : str
        "laser", "plasma", "oxyfuel", or "waterjet".
    thickness_mm : float
        Material thickness (mm) — used for context / warnings only.
    cut_length_mm : float
        Total cut length (mm).  Must be > 0.
    speed_mm_min : float
        Traverse speed (mm/min).  Must be > 0.
    assist_gas : str
        For laser: "O2" (default), "N2", or "Air".

    Returns
    -------
    dict
        ok               : True
        cut_time_min     : active cutting time (minutes)
        gas_volume_L     : total gas volume consumed (litres)
        gas_cost_usd     : estimated gas cost (USD)
        process          : process name
        warnings         : list of warning strings

    Notes
    -----
    For waterjet, gas consumption is not applicable; gas_volume_L = 0.
    """
    warnings: list[str] = []

    err = _guard_positive("thickness_mm", thickness_mm)
    if err:
        return _err(err)
    err = _guard_positive("cut_length_mm", cut_length_mm)
    if err:
        return _err(err)
    err = _guard_positive("speed_mm_min", speed_mm_min)
    if err:
        return _err(err)

    proc = str(process).strip().lower()
    t_mm = float(thickness_mm)
    L_mm = float(cut_length_mm)
    v = float(speed_mm_min)

    cut_time_min = L_mm / v  # minutes of active cutting

    if proc == "waterjet":
        return {
            "ok": True,
            "cut_time_min": round(cut_time_min, 4),
            "gas_volume_L": 0.0,
            "gas_cost_usd": 0.0,
            "process": proc,
            "warnings": ["Waterjet does not use cutting gas (abrasive only)."],
        }

    if proc == "laser":
        gas = str(assist_gas).strip().upper()
        if gas not in _LASER_GAS_RATE_L_MIN:
            return _err(
                f"Unknown assist_gas {assist_gas!r}. "
                f"Supported: {list(_LASER_GAS_RATE_L_MIN.keys())}."
            )
        rate = _LASER_GAS_RATE_L_MIN[gas]
        cost_per_L = _LASER_GAS_COST_PER_L[gas]
        vol = rate * cut_time_min
        cost = vol * cost_per_L
        if t_mm > 20.0 and gas == "O2":
            warnings.append(
                f"Thickness {t_mm} mm with O₂ assist: consider switching to N₂ "
                f"for stainless or aluminium to reduce oxidation."
            )

    elif proc == "plasma":
        rate = _PLASMA_GAS_RATE_L_MIN
        cost_per_L = _PLASMA_GAS_COST_PER_L
        vol = rate * cut_time_min
        cost = vol * cost_per_L

    elif proc == "oxyfuel":
        # Fuel + oxygen
        fuel_vol = _OXYFUEL_FUEL_RATE_L_MIN * cut_time_min
        o2_vol   = _OXYFUEL_O2_RATE_L_MIN   * cut_time_min
        vol = fuel_vol + o2_vol
        cost = (fuel_vol * _OXYFUEL_FUEL_COST_PER_L +
                o2_vol   * _OXYFUEL_O2_COST_PER_L)

    else:
        return _err(
            f"Unknown process {process!r}. Supported: 'laser', 'plasma', "
            f"'oxyfuel', 'waterjet'."
        )

    return {
        "ok": True,
        "cut_time_min": round(cut_time_min, 4),
        "gas_volume_L": round(vol, 3),
        "gas_cost_usd": round(cost, 4),
        "process": proc,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 12. abrasive_consumption
# ---------------------------------------------------------------------------

def abrasive_consumption(
    cut_length_mm: float,
    speed_mm_min: float,
    abrasive_rate_kg_min: float = 0.45,
) -> dict:
    """
    Abrasive (garnet) mass consumed (kg) and cost (USD) for AWJ cutting.

    Parameters
    ----------
    cut_length_mm : float
        Total cut length (mm).  Must be > 0.
    speed_mm_min : float
        Traverse speed (mm/min).  Must be > 0.
    abrasive_rate_kg_min : float
        Abrasive feed rate (kg/min).  Default 0.45 kg/min.

    Returns
    -------
    dict
        ok                   : True
        cut_time_min         : cutting time (minutes)
        abrasive_mass_kg     : garnet consumed (kg)
        abrasive_cost_usd    : estimated abrasive cost (USD)
        abrasive_rate_kg_min : rate used
    """
    err = _guard_positive("cut_length_mm", cut_length_mm)
    if err:
        return _err(err)
    err = _guard_positive("speed_mm_min", speed_mm_min)
    if err:
        return _err(err)
    err = _guard_positive("abrasive_rate_kg_min", abrasive_rate_kg_min)
    if err:
        return _err(err)

    L_mm = float(cut_length_mm)
    v = float(speed_mm_min)
    rate = float(abrasive_rate_kg_min)

    cut_time_min = L_mm / v
    abrasive_kg = rate * cut_time_min
    cost = abrasive_kg * _ABRASIVE_COST_PER_KG

    return {
        "ok": True,
        "cut_time_min": round(cut_time_min, 4),
        "abrasive_mass_kg": round(abrasive_kg, 4),
        "abrasive_cost_usd": round(cost, 4),
        "abrasive_rate_kg_min": rate,
    }


# ---------------------------------------------------------------------------
# 13. select_power
# ---------------------------------------------------------------------------

# Empirical power/amperage selection tables
# Laser: recommended power (W) per thickness band for mild steel
_LASER_POWER_TABLE: list[tuple[float, float]] = [
    (1.0,   500.0),
    (3.0,  1000.0),
    (6.0,  2000.0),
    (10.0, 3000.0),
    (16.0, 4000.0),
    (20.0, 6000.0),
    (25.0, 8000.0),
    (30.0, 10_000.0),
    (40.0, 12_000.0),
    (50.0, 15_000.0),
]

# Plasma: recommended amperage (A) per thickness band
_PLASMA_AMP_TABLE: list[tuple[float, float]] = [
    (3.0,    45.0),
    (6.0,    65.0),
    (10.0,   85.0),
    (16.0,  100.0),
    (25.0,  130.0),
    (38.0,  170.0),
    (50.0,  200.0),
    (75.0,  260.0),
    (100.0, 360.0),
    (150.0, 450.0),
]


def _interpolate_table(
    table: list[tuple[float, float]], x: float
) -> float:
    """Linear interpolation / extrapolation in a (x, y) table."""
    if x <= table[0][0]:
        return table[0][1]
    if x >= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        x0, y0 = table[i]
        x1, y1 = table[i + 1]
        if x0 <= x <= x1:
            frac = (x - x0) / (x1 - x0)
            return y0 + frac * (y1 - y0)
    return table[-1][1]


def select_power(
    process: str,
    thickness_mm: float,
    material: str = "mild_steel",
) -> dict:
    """
    Recommended power (W, laser) or amperage (A, plasma) for a given thickness.

    For aluminium, the laser power recommendation is scaled up by 1.3×
    (higher reflectivity and thermal conductivity).  For stainless steel, 1.1×.
    Plasma amperage does not change significantly with material.

    Parameters
    ----------
    process : str
        "laser" or "plasma".  Oxyfuel and waterjet do not use "power" selection.
    thickness_mm : float
        Material thickness (mm).  Must be > 0.
    material : str
        Material key.

    Returns
    -------
    dict
        ok               : True
        recommended_W    : recommended laser power (W) [laser only]
        recommended_A    : recommended plasma amperage (A) [plasma only]
        process          : process name
        thickness_mm     : input thickness (mm)
        material         : material name
        warnings         : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("thickness_mm", thickness_mm)
    if err:
        return _err(err)

    proc = str(process).strip().lower()
    mat_key = str(material).strip().lower()

    if mat_key not in _MATERIALS:
        return _err(f"Unknown material {material!r}. Supported: {_VALID_MATERIALS}.")

    t_mm = float(thickness_mm)

    if proc == "laser":
        base = _interpolate_table(_LASER_POWER_TABLE, t_mm)
        # Material scaling factors
        scale = 1.0
        if mat_key in ("aluminium_6061", "aluminium_5052"):
            scale = 1.30
        elif mat_key in ("stainless_304", "stainless_316"):
            scale = 1.10
        elif mat_key == "copper":
            scale = 1.50
        elif mat_key == "titanium_gr2":
            scale = 0.90  # lower cutting energy needed
        elif mat_key == "carbon_fibre_composite":
            scale = 0.60
            warnings.append(
                "CFRP laser cutting generates carcinogenic fumes; "
                "ensure adequate fume extraction."
            )

        recommended_W = base * scale

        if t_mm > 50.0:
            warnings.append(
                f"Thickness {t_mm} mm likely exceeds practical laser cutting range; "
                f"consider plasma or oxyfuel."
            )

        return {
            "ok": True,
            "recommended_W": round(recommended_W, 0),
            "process": proc,
            "thickness_mm": t_mm,
            "material": mat_key,
            "warnings": warnings,
        }

    elif proc == "plasma":
        base_A = _interpolate_table(_PLASMA_AMP_TABLE, t_mm)
        if t_mm > 150.0:
            warnings.append(
                f"Thickness {t_mm} mm exceeds typical plasma cutting range; "
                f"consider oxyfuel or mechanised cutting."
            )
        return {
            "ok": True,
            "recommended_A": round(base_A, 0),
            "process": proc,
            "thickness_mm": t_mm,
            "material": mat_key,
            "warnings": warnings,
        }

    else:
        return _err(
            f"select_power supports 'laser' and 'plasma' only; "
            f"got {process!r}."
        )


# ---------------------------------------------------------------------------
# 14. waterjet_params
# ---------------------------------------------------------------------------

def waterjet_params(
    pump_power_kW: float,
    orifice_dia_mm: float,
    *,
    mixing_tube_dia_mm: float | None = None,
    mixing_tube_length_mm: float | None = None,
    pressure_MPa: float = 380.0,
    abrasive_rate_kg_min: float = 0.45,
) -> dict:
    """
    Orifice/mixing-tube sizing, jet power, standoff, and abrasive flow checks
    for abrasive waterjet cutting.

    Waterjet jet power:
        P_jet = Q · ΔP
    where Q is volumetric flow rate (m³/s) and ΔP is pump pressure (Pa).

    Orifice flow (Bernoulli with discharge coefficient C_d ≈ 0.65):
        Q = C_d · A_orifice · √(2·ΔP/ρ_water)

    Mixing tube: standard ratio d_mixing / d_orifice ∈ [3.0, 4.0].
    Recommended mixing tube length ≈ 75 × d_mixing.
    Standoff: typically 3–5 mm.

    Parameters
    ----------
    pump_power_kW : float
        Hydraulic pump power (kW).
    orifice_dia_mm : float
        Water orifice diameter (mm).
    mixing_tube_dia_mm : float | None
        Mixing (focusing) tube inner diameter (mm).
        If None, defaults to 3.5 × orifice_dia_mm.
    mixing_tube_length_mm : float | None
        Mixing tube length (mm).  If None, defaults to 75 × mixing_tube_dia_mm.
    pressure_MPa : float
        Pump operating pressure (MPa).  Default 380 MPa.
    abrasive_rate_kg_min : float
        Abrasive feed rate (kg/min).  Default 0.45 kg/min.

    Returns
    -------
    dict
        ok                      : True
        orifice_dia_mm          : orifice diameter (mm)
        mixing_tube_dia_mm      : mixing tube diameter (mm)
        mixing_tube_length_mm   : mixing tube length (mm)
        orifice_area_mm2        : orifice cross-sectional area (mm²)
        flow_rate_L_min         : volumetric water flow (L/min)
        jet_power_kW            : hydraulic jet power (kW)
        jet_velocity_m_s        : theoretical jet velocity (m/s)
        standoff_mm             : recommended standoff (mm)
        abrasive_rate_kg_min    : abrasive feed rate (kg/min)
        abrasive_loading_ratio  : abrasive mass / water mass per min
        pressure_MPa            : operating pressure (MPa)
        warnings                : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("pump_power_kW", pump_power_kW)
    if err:
        return _err(err)
    err = _guard_positive("orifice_dia_mm", orifice_dia_mm)
    if err:
        return _err(err)
    err = _guard_positive("pressure_MPa", pressure_MPa)
    if err:
        return _err(err)
    err = _guard_positive("abrasive_rate_kg_min", abrasive_rate_kg_min)
    if err:
        return _err(err)

    P_kW = float(pump_power_kW)
    d_or_mm = float(orifice_dia_mm)
    dP_Pa = float(pressure_MPa) * 1e6  # Pa
    rho_w = 1000.0  # kg/m³

    # Orifice area
    A_or_m2 = math.pi / 4.0 * (d_or_mm * 1e-3) ** 2

    # Jet velocity (Bernoulli, C_d = 0.65)
    C_d = 0.65
    v_jet = C_d * math.sqrt(2.0 * dP_Pa / rho_w)  # m/s

    # Volumetric flow
    Q_m3_s = C_d * A_or_m2 * math.sqrt(2.0 * dP_Pa / rho_w)
    Q_L_min = Q_m3_s * 1000.0 * 60.0  # L/min

    # Jet power
    P_jet_W = Q_m3_s * dP_Pa
    P_jet_kW = P_jet_W / 1000.0

    if P_jet_kW > P_kW * 0.85:
        warnings.append(
            f"Calculated jet power {P_jet_kW:.1f} kW exceeds 85% of pump power "
            f"{P_kW:.1f} kW — verify orifice size and pump capacity."
        )

    # Mixing tube sizing
    if mixing_tube_dia_mm is None:
        d_mt_mm = d_or_mm * 3.5
    else:
        e_err = _guard_positive("mixing_tube_dia_mm", mixing_tube_dia_mm)
        if e_err:
            return _err(e_err)
        d_mt_mm = float(mixing_tube_dia_mm)
        ratio = d_mt_mm / d_or_mm
        if ratio < 2.5 or ratio > 5.0:
            warnings.append(
                f"Mixing tube / orifice ratio {ratio:.1f} is outside the "
                f"recommended range [2.5, 5.0]."
            )

    if mixing_tube_length_mm is None:
        L_mt_mm = 75.0 * d_mt_mm
    else:
        e_err = _guard_positive("mixing_tube_length_mm", mixing_tube_length_mm)
        if e_err:
            return _err(e_err)
        L_mt_mm = float(mixing_tube_length_mm)
        l_ratio = L_mt_mm / d_mt_mm
        if l_ratio < 50.0 or l_ratio > 120.0:
            warnings.append(
                f"Mixing tube L/D ratio {l_ratio:.0f} is outside the "
                f"recommended range [50, 120]."
            )

    # Standoff: 3–5 mm recommended; use 4 mm default
    standoff_mm = 4.0

    # Abrasive loading ratio: mass abrasive / mass water per minute
    abr_kg_min = float(abrasive_rate_kg_min)
    water_mass_kg_min = Q_L_min * rho_w / 1000.0  # kg/min
    abr_loading = abr_kg_min / water_mass_kg_min if water_mass_kg_min > 0 else 0.0

    if abr_loading > 0.8:
        warnings.append(
            f"Abrasive loading ratio {abr_loading:.2f} is high (> 0.8) — "
            f"mixing efficiency will decrease."
        )
    if abr_loading < 0.1:
        warnings.append(
            f"Abrasive loading ratio {abr_loading:.2f} is low (< 0.1) — "
            f"cutting efficiency will be reduced."
        )

    return {
        "ok": True,
        "orifice_dia_mm": d_or_mm,
        "mixing_tube_dia_mm": round(d_mt_mm, 4),
        "mixing_tube_length_mm": round(L_mt_mm, 2),
        "orifice_area_mm2": round(A_or_m2 * 1e6, 6),
        "flow_rate_L_min": round(Q_L_min, 4),
        "jet_power_kW": round(P_jet_kW, 3),
        "jet_velocity_m_s": round(v_jet, 2),
        "standoff_mm": standoff_mm,
        "abrasive_rate_kg_min": abr_kg_min,
        "abrasive_loading_ratio": round(abr_loading, 4),
        "pressure_MPa": float(pressure_MPa),
        "pump_power_kW": P_kW,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 15. part_cost
# ---------------------------------------------------------------------------

def part_cost(
    process: str,
    cut_length_mm: float,
    speed_mm_min: float,
    n_pierces: int,
    pierce_time_s: float,
    machine_rate_usd_hr: float | None = None,
    consumables_cost_usd: float = 0.0,
) -> dict:
    """
    Total part cut cost roll-up.

    Cost = (cut_time_hr + pierce_time_hr) × machine_rate + consumables

    where:
        cut_time_hr    = cut_length_mm / speed_mm_min / 60
        pierce_time_hr = n_pierces × pierce_time_s / 3600

    Parameters
    ----------
    process : str
        "laser", "plasma", "oxyfuel", or "waterjet".  Used to select
        default machine rate.
    cut_length_mm : float
        Total cut length (mm).  Must be > 0.
    speed_mm_min : float
        Average traverse speed (mm/min).  Must be > 0.
    n_pierces : int
        Number of pierce/punch-through operations.  Must be >= 0.
    pierce_time_s : float
        Time per pierce (seconds).  Must be >= 0.
    machine_rate_usd_hr : float | None
        Machine hourly rate (USD/hr).  If None, uses default for process.
    consumables_cost_usd : float
        Consumables cost for the part (USD; e.g. gas + abrasive + nozzle wear).

    Returns
    -------
    dict
        ok                   : True
        total_cost_usd       : total part cost (USD)
        cut_time_min         : active cutting time (minutes)
        pierce_time_total_min: total pierce time (minutes)
        machine_time_min     : total machine time (minutes)
        machine_rate_usd_hr  : rate used (USD/hr)
        consumables_cost_usd : consumables cost used (USD)
        process              : process name
        warnings             : list of warning strings
    """
    warnings: list[str] = []

    err = _guard_positive("cut_length_mm", cut_length_mm)
    if err:
        return _err(err)
    err = _guard_positive("speed_mm_min", speed_mm_min)
    if err:
        return _err(err)
    err = _guard_nonneg("pierce_time_s", pierce_time_s)
    if err:
        return _err(err)
    err = _guard_nonneg("consumables_cost_usd", consumables_cost_usd)
    if err:
        return _err(err)

    try:
        n_p = int(n_pierces)
    except (TypeError, ValueError):
        return _err(f"n_pierces must be an integer, got {n_pierces!r}.")
    if n_p < 0:
        return _err("n_pierces must be >= 0.")

    proc = str(process).strip().lower()
    if proc not in _MACHINE_RATE_DEFAULT:
        return _err(
            f"Unknown process {process!r}. Supported: {list(_MACHINE_RATE_DEFAULT.keys())}."
        )

    if machine_rate_usd_hr is None:
        rate = _MACHINE_RATE_DEFAULT[proc]
    else:
        e_err = _guard_positive("machine_rate_usd_hr", machine_rate_usd_hr)
        if e_err:
            return _err(e_err)
        rate = float(machine_rate_usd_hr)

    L_mm = float(cut_length_mm)
    v = float(speed_mm_min)
    tp_s = float(pierce_time_s)
    cons = float(consumables_cost_usd)

    cut_time_min = L_mm / v
    pierce_total_min = n_p * tp_s / 60.0
    machine_time_min = cut_time_min + pierce_total_min
    machine_time_hr = machine_time_min / 60.0

    machine_cost = machine_time_hr * rate
    total_cost = machine_cost + cons

    if total_cost > 500.0:
        warnings.append(
            f"Part cost ${total_cost:.2f} is high — consider nesting multiple "
            f"parts or optimising cut path to reduce machine time."
        )

    return {
        "ok": True,
        "total_cost_usd": round(total_cost, 4),
        "cut_time_min": round(cut_time_min, 4),
        "pierce_time_total_min": round(pierce_total_min, 4),
        "machine_time_min": round(machine_time_min, 4),
        "machine_rate_usd_hr": rate,
        "consumables_cost_usd": cons,
        "process": proc,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 16. process_compare
# ---------------------------------------------------------------------------

def process_compare(
    thickness_mm: float,
    material: str = "mild_steel",
    cut_length_mm: float = 1000.0,
    n_pierces: int = 4,
) -> dict:
    """
    Side-by-side comparison of laser / plasma / oxyfuel / waterjet for a
    given material and thickness.

    Computes for each applicable process:
      - Cut speed (mm/min)
      - Kerf width (mm)
      - HAZ width (mm)
      - Pierce time per pierce (s)
      - Part cost for cut_length_mm and n_pierces at default machine rates

    Uses default/recommended power levels from select_power().

    Parameters
    ----------
    thickness_mm : float
        Material thickness (mm).  Must be > 0.
    material : str
        Material key.
    cut_length_mm : float
        Hypothetical cut length for cost comparison (mm).  Default 1 000 mm.
    n_pierces : int
        Number of pierces for cost comparison.  Default 4.

    Returns
    -------
    dict
        ok       : True
        results  : dict[str, dict] — one entry per process; value has:
                       speed_mm_min, kerf_mm, haz_mm, pierce_time_s,
                       part_cost_usd, applicable (bool), notes (list[str])
        material : material name
        thickness_mm : input thickness (mm)
        warnings : list of warning strings (overall)
    """
    warnings: list[str] = []

    err = _guard_positive("thickness_mm", thickness_mm)
    if err:
        return _err(err)
    err = _guard_positive("cut_length_mm", cut_length_mm)
    if err:
        return _err(err)

    mat_key = str(material).strip().lower()
    if mat_key not in _MATERIALS:
        return _err(f"Unknown material {material!r}. Supported: {_VALID_MATERIALS}.")

    mat = _MATERIALS[mat_key]
    t_mm = float(thickness_mm)

    try:
        n_p = int(n_pierces)
    except (TypeError, ValueError):
        return _err(f"n_pierces must be an integer, got {n_pierces!r}.")
    if n_p < 0:
        return _err("n_pierces must be >= 0.")

    results: dict[str, dict] = {}

    # ---- LASER ----
    laser_pw = select_power("laser", t_mm, mat_key)
    if laser_pw.get("ok"):
        P_W = laser_pw["recommended_W"]
        spd = laser_cut_speed(t_mm, P_W, mat_key)
        kw = kerf_width("laser", t_mm, P_W)
        hz = haz_width("laser", t_mm, spd["speed_mm_min"] if spd.get("ok") else 500.0, P_W, mat_key)
        pt = pierce_time("laser", t_mm, power_W=P_W)
        v_l = spd["speed_mm_min"] if spd.get("ok") else 500.0
        tp_l = pt["pierce_time_s"] if pt.get("ok") else 1.0
        cons_l_result = gas_consumption("laser", t_mm, float(cut_length_mm), v_l)
        cons_l = cons_l_result.get("gas_cost_usd", 0.0) if cons_l_result.get("ok") else 0.0
        pc = part_cost("laser", float(cut_length_mm), v_l, n_p, tp_l, consumables_cost_usd=cons_l)
        results["laser"] = {
            "applicable": True,
            "speed_mm_min": spd.get("speed_mm_min", 0.0) if spd.get("ok") else 0.0,
            "kerf_mm": kw.get("kerf_mm", 0.0) if kw.get("ok") else 0.0,
            "haz_mm": hz.get("haz_mm", 0.0) if hz.get("ok") else 0.0,
            "pierce_time_s": tp_l,
            "part_cost_usd": pc.get("total_cost_usd", 0.0) if pc.get("ok") else 0.0,
            "recommended_power_W": P_W,
            "notes": (spd.get("warnings", []) + laser_pw.get("warnings", [])),
        }
    else:
        results["laser"] = {"applicable": False, "notes": [laser_pw.get("reason", "")]}

    # ---- PLASMA ----
    plasma_pw = select_power("plasma", t_mm, mat_key)
    if plasma_pw.get("ok"):
        I_A = plasma_pw["recommended_A"]
        spd = plasma_cut_speed(t_mm, I_A, mat_key)
        kw = kerf_width("plasma", t_mm, I_A)
        hz = haz_width("plasma", t_mm, spd["speed_mm_min"] if spd.get("ok") else 200.0, I_A, mat_key)
        pt = pierce_time("plasma", t_mm, amperage=I_A)
        v_p = spd["speed_mm_min"] if spd.get("ok") else 200.0
        tp_p = pt["pierce_time_s"] if pt.get("ok") else 2.0
        cons_p_result = gas_consumption("plasma", t_mm, float(cut_length_mm), v_p)
        cons_p = cons_p_result.get("gas_cost_usd", 0.0) if cons_p_result.get("ok") else 0.0
        pc = part_cost("plasma", float(cut_length_mm), v_p, n_p, tp_p, consumables_cost_usd=cons_p)
        results["plasma"] = {
            "applicable": True,
            "speed_mm_min": spd.get("speed_mm_min", 0.0) if spd.get("ok") else 0.0,
            "kerf_mm": kw.get("kerf_mm", 0.0) if kw.get("ok") else 0.0,
            "haz_mm": hz.get("haz_mm", 0.0) if hz.get("ok") else 0.0,
            "pierce_time_s": tp_p,
            "part_cost_usd": pc.get("total_cost_usd", 0.0) if pc.get("ok") else 0.0,
            "recommended_A": I_A,
            "notes": (spd.get("warnings", []) + plasma_pw.get("warnings", [])),
        }
    else:
        results["plasma"] = {"applicable": False, "notes": [plasma_pw.get("reason", "")]}

    # ---- OXYFUEL ----
    if mat["oxyfuel_ok"]:
        spd = oxyfuel_cut_speed(t_mm, mat_key)
        kw = kerf_width("oxyfuel", t_mm, 45.0)  # 45 L/min O₂ flow
        hz = haz_width("oxyfuel", t_mm, spd["speed_mm_min"] if spd.get("ok") else 200.0, 45.0, mat_key)
        pt = pierce_time("oxyfuel", t_mm)
        v_o = spd["speed_mm_min"] if spd.get("ok") else 200.0
        tp_o = pt["pierce_time_s"] if pt.get("ok") else 10.0
        cons_o_result = gas_consumption("oxyfuel", t_mm, float(cut_length_mm), v_o)
        cons_o = cons_o_result.get("gas_cost_usd", 0.0) if cons_o_result.get("ok") else 0.0
        pc = part_cost("oxyfuel", float(cut_length_mm), v_o, n_p, tp_o, consumables_cost_usd=cons_o)
        results["oxyfuel"] = {
            "applicable": True,
            "speed_mm_min": spd.get("speed_mm_min", 0.0) if spd.get("ok") else 0.0,
            "kerf_mm": kw.get("kerf_mm", 0.0) if kw.get("ok") else 0.0,
            "haz_mm": hz.get("haz_mm", 0.0) if hz.get("ok") else 0.0,
            "pierce_time_s": tp_o,
            "part_cost_usd": pc.get("total_cost_usd", 0.0) if pc.get("ok") else 0.0,
            "notes": spd.get("warnings", []) if spd.get("ok") else [spd.get("reason", "")],
        }
    else:
        results["oxyfuel"] = {
            "applicable": False,
            "notes": [f"{mat_key} is not compatible with oxyfuel cutting."],
        }

    # ---- WATERJET ----
    spd = waterjet_cut_speed(t_mm, mat_key)
    kw = kerf_width("waterjet", t_mm, 30.0)  # 30 kW pump
    hz = haz_width("waterjet", t_mm, spd["speed_mm_min"] if spd.get("ok") else 100.0, 30.0, mat_key)
    pt = pierce_time("waterjet", t_mm)
    v_w = spd["speed_mm_min"] if spd.get("ok") else 100.0
    tp_w = pt["pierce_time_s"] if pt.get("ok") else 0.5
    abr = abrasive_consumption(float(cut_length_mm), v_w)
    cons_w = abr.get("abrasive_cost_usd", 0.0) if abr.get("ok") else 0.0
    pc = part_cost("waterjet", float(cut_length_mm), v_w, n_p, tp_w, consumables_cost_usd=cons_w)
    results["waterjet"] = {
        "applicable": True,
        "speed_mm_min": spd.get("speed_mm_min", 0.0) if spd.get("ok") else 0.0,
        "kerf_mm": kw.get("kerf_mm", 0.0) if kw.get("ok") else 0.0,
        "haz_mm": hz.get("haz_mm", 0.0) if hz.get("ok") else 0.0,
        "pierce_time_s": tp_w,
        "part_cost_usd": pc.get("total_cost_usd", 0.0) if pc.get("ok") else 0.0,
        "notes": spd.get("warnings", []) if spd.get("ok") else [spd.get("reason", "")],
    }

    return {
        "ok": True,
        "results": results,
        "material": mat_key,
        "thickness_mm": t_mm,
        "cut_length_mm": float(cut_length_mm),
        "n_pierces": n_p,
        "warnings": warnings,
    }
