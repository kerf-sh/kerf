"""
kerf_cad_core.buildingenergy.energy — Building energy & daylighting calculations.

All functions are self-contained (math + stdlib only).  No OCC dependency.
Warnings are issued via the standard ``warnings`` module; functions never raise
on domain errors — they return ``{"ok": False, "reason": "..."}`` dicts instead.

Unit system
-----------
SI throughout unless otherwise noted in the function docstring.
  Length   : metres (m)
  Area     : m²
  Temp     : °C (delta values also °C / K equivalent)
  Power    : W
  Energy   : kWh or MJ (noted per function)
  Pressure : Pa
  U-value  : W/(m²·K)
  R-value  : m²·K/W

Implements
----------
ENVELOPE THERMAL PERFORMANCE
  uvalue_series(layers)
      Overall U-value for opaque assembly with layers in series.
      layers: list of {"r": R-value (m²K/W)} or {"k": k (W/mK), "d": thickness (m)}.
      Air-film resistances should be included in the layer list.
      Reference: ISO 6946:2017 §6.

  uvalue_parallel(fractions_and_uvalues)
      Area-weighted U-value for a surface with parallel heat-flow paths
      (e.g., stud framing vs. cavity).
      fractions_and_uvalues: list of (area_fraction, U).
      Reference: ISO 6946:2017 §6.9 (combined method simplified).

  uvalue_bridged(U_clear, U_bridge, bridge_fraction)
      Combined U-value accounting for thermal bridging using the fractional-area
      (linear combination) method.
      Reference: ASHRAE Fundamentals 2021 Ch. 27.

WHOLE-BUILDING THERMAL PERFORMANCE
  whole_building_ua(surfaces)
      Whole-building UA coefficient (W/K).
      surfaces: list of {"area_m2": A, "U": U} dicts.

  balance_point_temperature(T_indoor_C, internal_gains_W, ua_W_per_K)
      Balance-point temperature (°C) — outdoor temperature at which the building
      is in thermal equilibrium with internal gains only.
      T_balance = T_indoor - Q_internal / UA

  degree_day_energy(HDD_or_CDD, UA_W_per_K, *, mode, efficiency)
      Annual heating or cooling energy (kWh) from degree-days.
      mode = "heating" → uses HDD; mode = "cooling" → uses CDD.
      efficiency: AFUE (0–1) for heating; COP for cooling (≥1).
      Reference: ASHRAE Fundamentals 2021 Ch. 18.

  annual_fuel_cost(energy_kWh, fuel_type, *, price_per_unit)
      Estimated annual fuel or electricity cost.
      fuel_type: "electricity" (kWh), "natural_gas" (m³, HHV 10.55 kWh/m³),
                 "propane" (litres, HHV 7.08 kWh/L), "oil" (litres, HHV 10.35 kWh/L).

DESIGN LOADS
  design_heating_load(surfaces, T_indoor_C, T_outdoor_C, *,
                      infiltration_W_per_K, ventilation_W_per_K, internal_gains_W)
      Design heating load (W) — envelope transmission + infiltration +
      ventilation − internal gains.
      Reference: ASHRAE Fundamentals 2021 Ch. 18.

  design_cooling_load(surfaces, T_indoor_C, T_outdoor_C, *,
                      infiltration_W_per_K, ventilation_W_per_K, internal_gains_W,
                      solar_gain_W, latent_gain_W)
      Design cooling load (W) — envelope transmission + infiltration +
      ventilation + internal gains + solar + latent.
      Reference: ASHRAE Fundamentals 2021 Ch. 18.

INFILTRATION
  infiltration_ach_blower_door(ACH50, *, n)
      Estimate natural infiltration ACH from blower-door result at 50 Pa.
      ACH_nat = ACH50 / N  (N typically 20 for tight, 17 for average).
      Reference: Sherman & Grimsrud (1980); ASHRAE 62.2.

  infiltration_ach_aim2(floor_area_m2, height_m, C_i, n_exp,
                        delta_T_C, wind_speed_m_s, *, terrain_class)
      AIM-2 (Alberta Infiltration Model) / LBL model infiltration ACH.
      Stack and wind components combined:
          Q = C_i × (A_s × ΔT + A_w × v²)^0.5   [m³/s simplified]
      Returns ACH and volumetric flow rate (m³/h).
      Reference: Shaw & Tamura (1977); ASHRAE Fundamentals 2021 Ch. 16.

INTERSTITIAL CONDENSATION
  glaser_condensation(layers, T_inside_C, T_outside_C,
                      RH_inside, RH_outside)
      Glaser dew-point method for interstitial condensation risk.
      layers: list of {"name", "d_m", "k_W_mK", "mu"} where mu is vapour-
              diffusion resistance factor (dimensionless, μ).
      Returns temperature and dew-point at each interface; flags
      condensation risk in warnings when T_interface < T_dew_interface.
      Reference: ISO 13788:2012; Glaser (1958).

SOLAR HEAT GAIN
  solar_heat_gain(area_m2, SHGC, irradiance_W_m2, *,
                  incidence_angle_deg, shading_factor)
      Instantaneous solar heat gain through glazing (W).
      Applies incidence angle modifier (IAM) per ASHRAE simple model:
          IAM = 1 − b₀ × (1/cos θ − 1),  b₀ = 0.1 default.
      Reference: ASHRAE Fundamentals 2021 Ch. 15.

  shading_projection_factor(overhang_depth_m, window_height_m,
                             solar_altitude_deg, solar_azimuth_deg,
                             facade_azimuth_deg)
      Fraction of window area shaded by a horizontal overhang.
      Uses geometric projection; returns shaded fraction 0–1.
      Reference: CIBSE Guide A (2015) §5.

DAYLIGHTING
  daylight_factor(window_area_m2, floor_area_m2, Tv, *,
                  room_depth_m, room_width_m, reflectance_avg,
                  sky_component_fraction)
      Average daylight factor (DF) using the BRE simplified formula:
          DF = Tv × A_w × θ / (A_floor × (1 − R̄²))
      where θ is the visible sky angle factor.
      Reference: CIBSE Lighting Guide LG10; BRE (1986).

  window_to_floor_ratio(window_area_m2, floor_area_m2)
      Simple window-to-floor ratio (dimensionless).
      Typical targets: 0.10–0.20 for residential, 0.15–0.25 for office.

  no_sky_line_depth(window_head_height_m, *, multiplier)
      Depth from window at which a point on the working plane can just see
      the sky (no-sky line).
          depth = multiplier × window_head_height_m   (multiplier ≈ 2.0)
      Reference: BRE Digest 309.

OVERHEATING
  overheating_hours(internal_gains_W, solar_gain_W, UA_W_per_K,
                    T_outdoor_C_list, T_comfort_max_C)
      Estimate hours above comfort threshold for a given list of hourly
      outdoor temperatures.  Simple steady-state balance per hour.
      Returns count and fraction of hours exceeding T_comfort_max_C.
      Reference: CIBSE TM52 (simplified).

BENCHMARKING & COMPLIANCE
  eui(annual_energy_kWh, floor_area_m2)
      Energy Use Intensity (EUI) in kWh/(m²·yr).

  ashrae901_envelope_compliance(assembly_type, U_proposed, climate_zone, *)
      Check if a proposed assembly U-value meets ASHRAE 90.1-2022 prescriptive
      maximum U-value for the given climate zone.
      assembly_type: "roof", "wall_above_grade", "floor", "window_vertical",
                     "door_opaque", "slab_on_grade" (uses F-factor check).
      Returns compliance status and ASHRAE 90.1-2022 table reference.
      Flags non-compliance in warnings.
      Reference: ASHRAE 90.1-2022 Tables 5.5-1 through 5.5-8.

All functions return plain dicts:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

References
----------
ASHRAE Handbook — Fundamentals (2021), Chapters 15, 16, 18, 27
ASHRAE Standard 90.1-2022 — Energy Standard for Buildings
ISO 6946:2017 — Thermal resistance and thermal transmittance
ISO 13788:2012 — Hygrothermal performance (Glaser method)
CIBSE Guide A (2015) — Environmental Design
BRE Digest 309 (1986) — Estimating daylight in buildings
Glaser, H. (1958) — Vereinfachte Berechnung der Dampfdiffusion

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings as _warnings
from typing import List, Dict, Any, Optional


# ---------------------------------------------------------------------------
# Saturation vapour pressure helper (used by Glaser method)
# ---------------------------------------------------------------------------

def _sat_vapour_pressure_Pa(T_C: float) -> float:
    """Buck (1981) equation for saturation vapour pressure (Pa)."""
    # Buck equation: Psat = 611.21 * exp((18.678 - T/234.5) * (T / (257.14 + T)))
    T = T_C
    return 611.21 * math.exp((18.678 - T / 234.5) * (T / (257.14 + T)))


def _dew_point_C(T_C: float, RH: float) -> float:
    """Magnus approximation dew point (°C) from temperature and RH (0–1)."""
    if RH <= 0.0:
        return -273.0
    if RH >= 1.0:
        return T_C
    a, b = 17.62, 243.12
    gamma = math.log(RH) + a * T_C / (b + T_C)
    return b * gamma / (a - gamma)


# ---------------------------------------------------------------------------
# ENVELOPE THERMAL PERFORMANCE
# ---------------------------------------------------------------------------

def uvalue_series(layers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Overall U-value for an opaque assembly with layers in thermal series.

    Parameters (SI)
    ---------------
    layers : list of dicts, each with either:
        {"r": float}               — layer R-value (m²·K/W)  OR
        {"k": float, "d": float}   — conductivity (W/m·K) and thickness (m)

    Returns
    -------
    {"ok": True, "U_W_m2K": float, "R_total_m2KW": float, "warnings": list}

    Reference: ISO 6946:2017 §6.
    Units: SI (U in W/(m²·K), R in m²·K/W).
    """
    try:
        if not layers:
            return {"ok": False, "reason": "layers list is empty"}

        R_total = 0.0
        for i, layer in enumerate(layers):
            if "r" in layer:
                r = float(layer["r"])
                if r < 0:
                    return {"ok": False, "reason": f"layer {i} has negative R-value"}
                R_total += r
            elif "k" in layer and "d" in layer:
                k = float(layer["k"])
                d = float(layer["d"])
                if k <= 0:
                    return {"ok": False, "reason": f"layer {i}: k must be > 0"}
                if d <= 0:
                    return {"ok": False, "reason": f"layer {i}: d must be > 0"}
                R_total += d / k
            else:
                return {
                    "ok": False,
                    "reason": f"layer {i}: must have 'r', or both 'k' and 'd'",
                }

        if R_total <= 0:
            return {"ok": False, "reason": "total R-value must be > 0"}

        U = 1.0 / R_total
        warn_list: List[str] = []
        if U > 5.0:
            msg = f"U-value {U:.2f} W/(m²·K) is very high — check inputs"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "U_W_m2K": round(U, 6),
            "R_total_m2KW": round(R_total, 6),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def uvalue_parallel(fractions_and_uvalues: List[tuple]) -> Dict[str, Any]:
    """Area-weighted parallel U-value for mixed-path assemblies.

    Parameters (SI)
    ---------------
    fractions_and_uvalues : list of (area_fraction, U) tuples.
        area_fraction values must sum to 1.0 (tolerance ±0.01).
        U in W/(m²·K).

    Returns
    -------
    {"ok": True, "U_W_m2K": float, "warnings": list}

    Reference: ISO 6946:2017 §6.9 simplified.
    Units: SI.
    """
    try:
        if not fractions_and_uvalues:
            return {"ok": False, "reason": "fractions_and_uvalues is empty"}

        total_frac = 0.0
        U_combined = 0.0
        for i, item in enumerate(fractions_and_uvalues):
            frac, U = float(item[0]), float(item[1])
            if frac < 0:
                return {"ok": False, "reason": f"item {i}: fraction must be >= 0"}
            if U < 0:
                return {"ok": False, "reason": f"item {i}: U must be >= 0"}
            total_frac += frac
            U_combined += frac * U

        warn_list: List[str] = []
        if abs(total_frac - 1.0) > 0.01:
            msg = f"area fractions sum to {total_frac:.4f}, expected 1.0"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "U_W_m2K": round(U_combined, 6),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def uvalue_bridged(
    U_clear: float,
    U_bridge: float,
    bridge_fraction: float,
) -> Dict[str, Any]:
    """Combined U-value with thermal bridging (linear/fractional-area method).

    Parameters (SI)
    ---------------
    U_clear       : U-value of the clear-field (unbridged) area  W/(m²·K)
    U_bridge      : U-value through the thermal bridge            W/(m²·K)
    bridge_fraction: fraction of total area occupied by bridges  [0–1]

    Returns
    -------
    {"ok": True, "U_combined_W_m2K": float,
     "U_clear_W_m2K": float, "U_bridge_W_m2K": float,
     "bridge_fraction": float, "warnings": list}

    Reference: ASHRAE Fundamentals 2021 Ch. 27.
    Units: SI.
    """
    try:
        U_clear = float(U_clear)
        U_bridge = float(U_bridge)
        bridge_fraction = float(bridge_fraction)

        if U_clear < 0:
            return {"ok": False, "reason": "U_clear must be >= 0"}
        if U_bridge < 0:
            return {"ok": False, "reason": "U_bridge must be >= 0"}
        if not (0.0 <= bridge_fraction <= 1.0):
            return {"ok": False, "reason": "bridge_fraction must be in [0, 1]"}

        U_combined = (1.0 - bridge_fraction) * U_clear + bridge_fraction * U_bridge

        warn_list: List[str] = []
        if bridge_fraction > 0.3:
            msg = f"bridge_fraction {bridge_fraction:.2%} is high — consider point/linear thermal bridge correction"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "U_combined_W_m2K": round(U_combined, 6),
            "U_clear_W_m2K": round(U_clear, 6),
            "U_bridge_W_m2K": round(U_bridge, 6),
            "bridge_fraction": round(bridge_fraction, 6),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# WHOLE-BUILDING THERMAL PERFORMANCE
# ---------------------------------------------------------------------------

def whole_building_ua(surfaces: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Whole-building UA coefficient (W/K).

    Parameters (SI)
    ---------------
    surfaces : list of dicts {"area_m2": float, "U": float [W/(m²·K)]}

    Returns
    -------
    {"ok": True, "UA_W_per_K": float,
     "total_area_m2": float, "mean_U_W_m2K": float, "warnings": list}

    Units: SI.
    """
    try:
        if not surfaces:
            return {"ok": False, "reason": "surfaces list is empty"}

        UA = 0.0
        A_total = 0.0
        for i, s in enumerate(surfaces):
            A = float(s.get("area_m2", 0.0))
            U = float(s.get("U", 0.0))
            if A < 0:
                return {"ok": False, "reason": f"surface {i}: area_m2 must be >= 0"}
            if U < 0:
                return {"ok": False, "reason": f"surface {i}: U must be >= 0"}
            UA += A * U
            A_total += A

        warn_list: List[str] = []
        mean_U = UA / A_total if A_total > 0 else 0.0

        return {
            "ok": True,
            "UA_W_per_K": round(UA, 4),
            "total_area_m2": round(A_total, 4),
            "mean_U_W_m2K": round(mean_U, 6),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def balance_point_temperature(
    T_indoor_C: float,
    internal_gains_W: float,
    ua_W_per_K: float,
) -> Dict[str, Any]:
    """Balance-point temperature (°C).

    The outdoor temperature at which the building is in thermal equilibrium
    using internal gains alone (no mechanical heating required above this point).

    Parameters (SI)
    ---------------
    T_indoor_C      : indoor setpoint temperature (°C)
    internal_gains_W: total steady-state internal heat gains (W)
    ua_W_per_K      : whole-building UA coefficient (W/K)

    Returns
    -------
    {"ok": True, "T_balance_C": float, "warnings": list}

    T_balance = T_indoor − Q_internal / UA
    Reference: ASHRAE Fundamentals 2021 Ch. 18.
    Units: SI.
    """
    try:
        T_indoor_C = float(T_indoor_C)
        internal_gains_W = float(internal_gains_W)
        ua_W_per_K = float(ua_W_per_K)

        if ua_W_per_K <= 0:
            return {"ok": False, "reason": "ua_W_per_K must be > 0"}
        if internal_gains_W < 0:
            return {"ok": False, "reason": "internal_gains_W must be >= 0"}

        T_balance = T_indoor_C - internal_gains_W / ua_W_per_K

        warn_list: List[str] = []
        if T_balance < -30:
            msg = f"Balance-point temperature {T_balance:.1f} °C is very low — check inputs"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "T_balance_C": round(T_balance, 3),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def degree_day_energy(
    HDD_or_CDD: float,
    UA_W_per_K: float,
    *,
    mode: str = "heating",
    efficiency: float = 0.9,
) -> Dict[str, Any]:
    """Annual heating or cooling energy from degree-days (kWh).

    Parameters (SI / mixed)
    -----------------------
    HDD_or_CDD  : heating (HDD) or cooling (CDD) degree-days (K·day or °C·day)
    UA_W_per_K  : whole-building UA coefficient (W/K)
    mode        : "heating" (default) or "cooling"
    efficiency  : AFUE fraction for heating (e.g. 0.9); COP for cooling (e.g. 3.5)

    Returns
    -------
    {"ok": True, "energy_kWh": float, "mode": str,
     "HDD_or_CDD": float, "efficiency": float, "warnings": list}

    Formula: E = UA × DD × 24 h/day / efficiency / 1000  [kWh]
    Reference: ASHRAE Fundamentals 2021 Ch. 18 §18.3.
    Units: SI (energy in kWh).
    """
    try:
        HDD_or_CDD = float(HDD_or_CDD)
        UA_W_per_K = float(UA_W_per_K)
        efficiency = float(efficiency)

        if HDD_or_CDD < 0:
            return {"ok": False, "reason": "HDD_or_CDD must be >= 0"}
        if UA_W_per_K <= 0:
            return {"ok": False, "reason": "UA_W_per_K must be > 0"}
        if mode not in ("heating", "cooling"):
            return {"ok": False, "reason": "mode must be 'heating' or 'cooling'"}
        if efficiency <= 0:
            return {"ok": False, "reason": "efficiency must be > 0"}

        # E [kWh] = UA [W/K] × DD [K·day] × 24 [h/day] / efficiency / 1000
        energy_kWh = UA_W_per_K * HDD_or_CDD * 24.0 / efficiency / 1000.0

        warn_list: List[str] = []
        if mode == "heating" and efficiency > 1.0:
            msg = "heating efficiency > 1.0 — use COP not AFUE? Check value."
            _warnings.warn(msg)
            warn_list.append(msg)
        if mode == "cooling" and efficiency < 1.0:
            msg = "cooling efficiency < 1.0 — COP should be >= 1.0"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "energy_kWh": round(energy_kWh, 2),
            "mode": mode,
            "HDD_or_CDD": HDD_or_CDD,
            "efficiency": efficiency,
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def annual_fuel_cost(
    energy_kWh: float,
    fuel_type: str,
    *,
    price_per_unit: float,
) -> Dict[str, Any]:
    """Estimated annual fuel or electricity cost.

    Parameters (SI / mixed)
    -----------------------
    energy_kWh     : building energy demand (kWh)
    fuel_type      : "electricity" | "natural_gas" | "propane" | "oil"
    price_per_unit : cost per unit of fuel:
                     electricity  → $/kWh
                     natural_gas  → $/m³
                     propane      → $/litre
                     oil          → $/litre

    Returns
    -------
    {"ok": True, "cost": float, "fuel_units_required": float,
     "fuel_type": str, "unit": str, "warnings": list}

    Fuel HHV: natural_gas 10.55 kWh/m³, propane 7.08 kWh/L, oil 10.35 kWh/L.
    Units: mixed (energy kWh, volume m³ or L, cost in currency of price_per_unit).
    """
    try:
        energy_kWh = float(energy_kWh)
        price_per_unit = float(price_per_unit)

        if energy_kWh < 0:
            return {"ok": False, "reason": "energy_kWh must be >= 0"}
        if price_per_unit < 0:
            return {"ok": False, "reason": "price_per_unit must be >= 0"}

        _HHV = {
            "electricity":   1.0,       # kWh/kWh
            "natural_gas":   10.55,     # kWh/m³
            "propane":       7.08,      # kWh/L
            "oil":           10.35,     # kWh/L
        }
        _unit_label = {
            "electricity": "kWh",
            "natural_gas": "m³",
            "propane":     "litre",
            "oil":         "litre",
        }

        if fuel_type not in _HHV:
            return {
                "ok": False,
                "reason": f"fuel_type must be one of {list(_HHV.keys())}",
            }

        hhv = _HHV[fuel_type]
        fuel_units = energy_kWh / hhv
        cost = fuel_units * price_per_unit

        return {
            "ok": True,
            "cost": round(cost, 2),
            "fuel_units_required": round(fuel_units, 4),
            "fuel_type": fuel_type,
            "unit": _unit_label[fuel_type],
            "warnings": [],
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# DESIGN LOADS
# ---------------------------------------------------------------------------

def design_heating_load(
    surfaces: List[Dict[str, Any]],
    T_indoor_C: float,
    T_outdoor_C: float,
    *,
    infiltration_W_per_K: float = 0.0,
    ventilation_W_per_K: float = 0.0,
    internal_gains_W: float = 0.0,
) -> Dict[str, Any]:
    """Design heating load (W).

    Parameters (SI)
    ---------------
    surfaces           : list of {"area_m2", "U"} envelope surfaces
    T_indoor_C         : indoor setpoint (°C)
    T_outdoor_C        : design outdoor (°C) — must be < T_indoor_C for heating
    infiltration_W_per_K: infiltration UA contribution (W/K)
    ventilation_W_per_K : mechanical ventilation UA contribution (W/K)
    internal_gains_W   : total internal heat gains (W) — reduces heating load

    Returns
    -------
    {"ok": True, "heating_load_W": float,
     "envelope_W": float, "infiltration_W": float,
     "ventilation_W": float, "internal_gains_W": float, "warnings": list}

    Q_heat = (UA_env + UA_inf + UA_vent) × (T_in − T_out) − Q_internal
    Reference: ASHRAE Fundamentals 2021 Ch. 18.
    Units: SI (W).
    """
    try:
        T_indoor_C = float(T_indoor_C)
        T_outdoor_C = float(T_outdoor_C)
        infiltration_W_per_K = float(infiltration_W_per_K)
        ventilation_W_per_K = float(ventilation_W_per_K)
        internal_gains_W = float(internal_gains_W)

        ua_res = whole_building_ua(surfaces)
        if not ua_res["ok"]:
            return ua_res

        UA_env = ua_res["UA_W_per_K"]
        delta_T = T_indoor_C - T_outdoor_C

        warn_list: List[str] = []
        if delta_T <= 0:
            msg = "T_outdoor_C >= T_indoor_C — no heating required at this condition"
            _warnings.warn(msg)
            warn_list.append(msg)

        envelope_W = UA_env * delta_T
        inf_W = infiltration_W_per_K * delta_T
        vent_W = ventilation_W_per_K * delta_T
        Q_heat = envelope_W + inf_W + vent_W - internal_gains_W

        if Q_heat < 0:
            Q_heat = 0.0
            warn_list.append("Heating load is negative (internal gains exceed losses) — set to 0")

        return {
            "ok": True,
            "heating_load_W": round(Q_heat, 2),
            "envelope_W": round(envelope_W, 2),
            "infiltration_W": round(inf_W, 2),
            "ventilation_W": round(vent_W, 2),
            "internal_gains_W": round(internal_gains_W, 2),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def design_cooling_load(
    surfaces: List[Dict[str, Any]],
    T_indoor_C: float,
    T_outdoor_C: float,
    *,
    infiltration_W_per_K: float = 0.0,
    ventilation_W_per_K: float = 0.0,
    internal_gains_W: float = 0.0,
    solar_gain_W: float = 0.0,
    latent_gain_W: float = 0.0,
) -> Dict[str, Any]:
    """Design cooling load (W).

    Parameters (SI)
    ---------------
    surfaces           : list of {"area_m2", "U"} envelope surfaces
    T_indoor_C         : indoor setpoint (°C)
    T_outdoor_C        : design outdoor (°C) — must be > T_indoor_C for cooling
    infiltration_W_per_K: infiltration UA contribution (W/K)
    ventilation_W_per_K : mechanical ventilation UA contribution (W/K)
    internal_gains_W   : total sensible internal gains (W)
    solar_gain_W       : total solar heat gain through glazing (W)
    latent_gain_W      : latent (moisture) gains (W)

    Returns
    -------
    {"ok": True, "cooling_load_W": float,
     "sensible_load_W": float, "latent_load_W": float,
     "envelope_W": float, "infiltration_W": float,
     "ventilation_W": float, "internal_gains_W": float,
     "solar_gain_W": float, "latent_gain_W": float, "warnings": list}

    Q_cool = (UA_env + UA_inf + UA_vent) × (T_out − T_in) + Q_int + Q_solar + Q_latent
    Reference: ASHRAE Fundamentals 2021 Ch. 18.
    Units: SI (W).
    """
    try:
        T_indoor_C = float(T_indoor_C)
        T_outdoor_C = float(T_outdoor_C)
        infiltration_W_per_K = float(infiltration_W_per_K)
        ventilation_W_per_K = float(ventilation_W_per_K)
        internal_gains_W = float(internal_gains_W)
        solar_gain_W = float(solar_gain_W)
        latent_gain_W = float(latent_gain_W)

        ua_res = whole_building_ua(surfaces)
        if not ua_res["ok"]:
            return ua_res

        UA_env = ua_res["UA_W_per_K"]
        delta_T = T_outdoor_C - T_indoor_C

        warn_list: List[str] = []
        if delta_T <= 0:
            msg = "T_outdoor_C <= T_indoor_C — no envelope cooling gain at this condition"
            _warnings.warn(msg)
            warn_list.append(msg)

        envelope_W = UA_env * delta_T
        inf_W = infiltration_W_per_K * delta_T
        vent_W = ventilation_W_per_K * delta_T
        sensible_W = envelope_W + inf_W + vent_W + internal_gains_W + solar_gain_W
        Q_cool = sensible_W + latent_gain_W

        if Q_cool < 0:
            Q_cool = 0.0
            warn_list.append("Cooling load is negative — set to 0")

        return {
            "ok": True,
            "cooling_load_W": round(Q_cool, 2),
            "sensible_load_W": round(sensible_W, 2),
            "latent_load_W": round(latent_gain_W, 2),
            "envelope_W": round(envelope_W, 2),
            "infiltration_W": round(inf_W, 2),
            "ventilation_W": round(vent_W, 2),
            "internal_gains_W": round(internal_gains_W, 2),
            "solar_gain_W": round(solar_gain_W, 2),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# INFILTRATION
# ---------------------------------------------------------------------------

def infiltration_ach_blower_door(
    ACH50: float,
    *,
    n: float = 20.0,
) -> Dict[str, Any]:
    """Estimate natural infiltration ACH from blower-door test at 50 Pa.

    Parameters (SI / mixed)
    -----------------------
    ACH50 : measured air-changes per hour at 50 Pa pressurisation (h⁻¹)
    n     : divisor — typically 20 (tight/low-rise) to 10 (leaky/tall buildings)

    Returns
    -------
    {"ok": True, "ACH_natural": float, "ACH50": float, "n": float, "warnings": list}

    ACH_nat = ACH50 / n
    Reference: Sherman & Grimsrud (1980); ASHRAE 62.2-2022.
    Units: h⁻¹.
    """
    try:
        ACH50 = float(ACH50)
        n = float(n)

        if ACH50 < 0:
            return {"ok": False, "reason": "ACH50 must be >= 0"}
        if n <= 0:
            return {"ok": False, "reason": "n must be > 0"}

        ACH_nat = ACH50 / n

        warn_list: List[str] = []
        if ACH50 > 10.0:
            msg = f"ACH50 = {ACH50:.1f} is very high — poor air-tightness"
            _warnings.warn(msg)
            warn_list.append(msg)
        if ACH_nat < 0.03:
            msg = f"Natural ACH {ACH_nat:.3f} < 0.03 — extremely tight; verify ventilation provision"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "ACH_natural": round(ACH_nat, 5),
            "ACH50": ACH50,
            "n": n,
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def infiltration_ach_aim2(
    floor_area_m2: float,
    height_m: float,
    C_i: float,
    n_exp: float,
    delta_T_C: float,
    wind_speed_m_s: float,
    *,
    terrain_class: str = "suburban",
) -> Dict[str, Any]:
    """AIM-2 / LBL model: infiltration ACH from stack and wind effects.

    Parameters (SI)
    ---------------
    floor_area_m2  : conditioned floor area (m²)
    height_m       : mean ceiling/stack height (m)
    C_i            : envelope leakage coefficient (m³/s·Pa^n) — from blower door
    n_exp          : pressure exponent (typically 0.65)
    delta_T_C      : indoor–outdoor temperature difference |ΔT| (K or °C)
    wind_speed_m_s : local wind speed at building height (m/s)
    terrain_class  : "urban" | "suburban" (default) | "rural"

    Returns
    -------
    {"ok": True, "ACH": float, "Q_m3_per_h": float,
     "Q_stack_m3_per_h": float, "Q_wind_m3_per_h": float, "warnings": list}

    Combined: Q = sqrt(Q_stack² + Q_wind²)
    Stack:    Q_stack = C_i × (A_s × g × H × ΔT / T_avg)^n
    Wind:     Q_wind  = C_i × (A_w × v²)^n
    Reference: Shaw & Tamura (1977); ASHRAE Fundamentals 2021 Ch. 16.
    Units: SI (m³/h, h⁻¹).
    """
    try:
        floor_area_m2 = float(floor_area_m2)
        height_m = float(height_m)
        C_i = float(C_i)
        n_exp = float(n_exp)
        delta_T_C = float(abs(delta_T_C))
        wind_speed_m_s = float(wind_speed_m_s)

        if floor_area_m2 <= 0:
            return {"ok": False, "reason": "floor_area_m2 must be > 0"}
        if height_m <= 0:
            return {"ok": False, "reason": "height_m must be > 0"}
        if C_i <= 0:
            return {"ok": False, "reason": "C_i must be > 0"}
        if not (0.4 <= n_exp <= 1.0):
            return {"ok": False, "reason": "n_exp typically 0.4–1.0"}
        if wind_speed_m_s < 0:
            return {"ok": False, "reason": "wind_speed_m_s must be >= 0"}

        # Terrain shielding coefficients for wind
        _Cs = {"urban": 0.01, "suburban": 0.02, "rural": 0.04}
        if terrain_class not in _Cs:
            return {
                "ok": False,
                "reason": f"terrain_class must be one of {list(_Cs.keys())}",
            }
        Cs = _Cs[terrain_class]

        volume_m3 = floor_area_m2 * height_m
        g = 9.81  # m/s²
        T_avg_K = 273.15 + 10.0  # approximate average (10°C ref)

        # Stack driving pressure (Pa): ΔP_s = ρ × g × H × ΔT / T_avg
        rho = 1.2  # kg/m³ at ~10°C
        dP_stack = rho * g * height_m * delta_T_C / T_avg_K  # Pa
        Q_stack_m3s = C_i * (dP_stack ** n_exp)

        # Wind driving pressure (Pa): ΔP_w = 0.5 × ρ × Cs × v²
        dP_wind = 0.5 * rho * Cs * (wind_speed_m_s ** 2)  # Pa
        Q_wind_m3s = C_i * (dP_wind ** n_exp) if dP_wind > 0 else 0.0

        # Combined (quadrature)
        Q_total_m3s = math.sqrt(Q_stack_m3s ** 2 + Q_wind_m3s ** 2)

        Q_m3h = Q_total_m3s * 3600.0
        Q_stack_m3h = Q_stack_m3s * 3600.0
        Q_wind_m3h = Q_wind_m3s * 3600.0
        ACH = Q_m3h / volume_m3

        warn_list: List[str] = []
        if ACH > 2.0:
            msg = f"Infiltration ACH {ACH:.2f} > 2.0 — very leaky building"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "ACH": round(ACH, 4),
            "Q_m3_per_h": round(Q_m3h, 4),
            "Q_stack_m3_per_h": round(Q_stack_m3h, 4),
            "Q_wind_m3_per_h": round(Q_wind_m3h, 4),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# INTERSTITIAL CONDENSATION (GLASER METHOD)
# ---------------------------------------------------------------------------

def glaser_condensation(
    layers: List[Dict[str, Any]],
    T_inside_C: float,
    T_outside_C: float,
    RH_inside: float,
    RH_outside: float,
) -> Dict[str, Any]:
    """Glaser dew-point method for interstitial condensation risk.

    Parameters (SI)
    ---------------
    layers       : list of {"name": str, "d_m": float, "k_W_mK": float, "mu": float}
                   mu = vapour diffusion resistance factor (dimensionless, e.g. 1 for air,
                   50 for EPS, 100 for XPS, 10 for mineral wool, 10000 for polyethylene VCL)
    T_inside_C   : indoor air temperature (°C)
    T_outside_C  : outdoor air temperature (°C)
    RH_inside    : indoor relative humidity (0–1)
    RH_outside   : outdoor relative humidity (0–1)

    Returns
    -------
    {"ok": True, "interfaces": list of interface dicts,
     "condensation_risk": bool, "warnings": list}

    Each interface dict: {"name": str, "T_C": float, "T_dew_C": float,
                          "p_vapour_Pa": float, "p_sat_Pa": float,
                          "condensation": bool}

    Reference: ISO 13788:2012; Glaser, H. (1958).
    Units: SI (°C, Pa).
    """
    try:
        T_inside_C = float(T_inside_C)
        T_outside_C = float(T_outside_C)
        RH_inside = float(RH_inside)
        RH_outside = float(RH_outside)

        if not layers:
            return {"ok": False, "reason": "layers list is empty"}
        if not (0.0 < RH_inside <= 1.0):
            return {"ok": False, "reason": "RH_inside must be in (0, 1]"}
        if not (0.0 < RH_outside <= 1.0):
            return {"ok": False, "reason": "RH_outside must be in (0, 1]"}

        # Validate layers
        R_total = 0.0
        Sd_total = 0.0  # total vapour diffusion equivalent air-layer thickness
        layer_R = []
        layer_Sd = []

        for i, lyr in enumerate(layers):
            d = float(lyr.get("d_m", 0.0))
            k = float(lyr.get("k_W_mK", 0.0))
            mu = float(lyr.get("mu", 1.0))
            if d <= 0:
                return {"ok": False, "reason": f"layer {i}: d_m must be > 0"}
            if k <= 0:
                return {"ok": False, "reason": f"layer {i}: k_W_mK must be > 0"}
            if mu < 1.0:
                return {"ok": False, "reason": f"layer {i}: mu must be >= 1"}
            R = d / k
            Sd = mu * d  # m (equivalent air thickness for vapour)
            R_total += R
            Sd_total += Sd
            layer_R.append(R)
            layer_Sd.append(Sd)

        # Temperature profile at each interface (linear through layers)
        delta_T = T_inside_C - T_outside_C
        # Vapour pressure profile at each interface (linear through Sd)
        p_inside = _sat_vapour_pressure_Pa(T_inside_C) * RH_inside
        p_outside = _sat_vapour_pressure_Pa(T_outside_C) * RH_outside
        delta_p = p_inside - p_outside

        interfaces = []
        R_cum = 0.0
        Sd_cum = 0.0
        condensation_risk = False

        # Include inner surface
        for idx, (lyr, R, Sd) in enumerate(zip(layers, layer_R, layer_Sd)):
            # Interface at far side of this layer
            R_cum += R
            Sd_cum += Sd

            T_int = T_inside_C - delta_T * (R_cum / R_total) if R_total > 0 else T_inside_C
            p_vap = p_inside - delta_p * (Sd_cum / Sd_total) if Sd_total > 0 else p_inside
            p_sat_int = _sat_vapour_pressure_Pa(T_int)
            T_dew = _dew_point_C(T_int, p_vap / p_sat_int) if p_sat_int > 0 else T_int

            condensation = T_int < T_dew
            if condensation:
                condensation_risk = True

            interfaces.append({
                "name": str(lyr.get("name", f"layer_{idx}")),
                "T_C": round(T_int, 3),
                "T_dew_C": round(T_dew, 3),
                "p_vapour_Pa": round(p_vap, 2),
                "p_sat_Pa": round(p_sat_int, 2),
                "condensation": condensation,
            })

        warn_list: List[str] = []
        if condensation_risk:
            n_layers = sum(1 for ifc in interfaces if ifc["condensation"])
            msg = (
                f"Interstitial condensation risk detected at {n_layers} interface(s). "
                "Consider vapour control layer, improved insulation position, or dehumidification."
            )
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "interfaces": interfaces,
            "condensation_risk": condensation_risk,
            "R_total_m2KW": round(R_total, 5),
            "Sd_total_m": round(Sd_total, 4),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# SOLAR HEAT GAIN
# ---------------------------------------------------------------------------

def solar_heat_gain(
    area_m2: float,
    SHGC: float,
    irradiance_W_m2: float,
    *,
    incidence_angle_deg: float = 0.0,
    shading_factor: float = 1.0,
    b0: float = 0.1,
) -> Dict[str, Any]:
    """Instantaneous solar heat gain through glazing (W).

    Parameters (SI)
    ---------------
    area_m2            : glazing area (m²)
    SHGC               : solar heat gain coefficient at normal incidence (dimensionless, 0–1)
    irradiance_W_m2    : total solar irradiance on glazing plane (W/m²)
    incidence_angle_deg: angle of incidence from normal (degrees, 0 = perpendicular)
    shading_factor     : external shading factor [0–1], 1 = no shading
    b0                 : incidence angle modifier coefficient (default 0.1 per ASHRAE)

    Returns
    -------
    {"ok": True, "solar_gain_W": float, "IAM": float,
     "SHGC_eff": float, "warnings": list}

    IAM = 1 − b₀ × (1/cosθ − 1)
    Q_solar = area × SHGC × IAM × irradiance × shading_factor
    Reference: ASHRAE Fundamentals 2021 Ch. 15.
    Units: SI (W).
    """
    try:
        area_m2 = float(area_m2)
        SHGC = float(SHGC)
        irradiance_W_m2 = float(irradiance_W_m2)
        incidence_angle_deg = float(incidence_angle_deg)
        shading_factor = float(shading_factor)
        b0 = float(b0)

        if area_m2 < 0:
            return {"ok": False, "reason": "area_m2 must be >= 0"}
        if not (0.0 <= SHGC <= 1.0):
            return {"ok": False, "reason": "SHGC must be in [0, 1]"}
        if irradiance_W_m2 < 0:
            return {"ok": False, "reason": "irradiance_W_m2 must be >= 0"}
        if not (0.0 <= incidence_angle_deg < 90.0):
            return {"ok": False, "reason": "incidence_angle_deg must be in [0, 90)"}
        if not (0.0 <= shading_factor <= 1.0):
            return {"ok": False, "reason": "shading_factor must be in [0, 1]"}

        cos_theta = math.cos(math.radians(incidence_angle_deg))
        if cos_theta < 1e-6:
            cos_theta = 1e-6

        IAM = 1.0 - b0 * (1.0 / cos_theta - 1.0)
        IAM = max(0.0, IAM)  # cannot be negative
        SHGC_eff = SHGC * IAM

        Q_solar = area_m2 * SHGC_eff * irradiance_W_m2 * shading_factor

        warn_list: List[str] = []
        if SHGC_eff < 0.15 and SHGC > 0.3:
            msg = f"High incidence angle reduces effective SHGC to {SHGC_eff:.3f}"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "solar_gain_W": round(Q_solar, 3),
            "IAM": round(IAM, 5),
            "SHGC_eff": round(SHGC_eff, 5),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def shading_projection_factor(
    overhang_depth_m: float,
    window_height_m: float,
    solar_altitude_deg: float,
    solar_azimuth_deg: float,
    facade_azimuth_deg: float,
) -> Dict[str, Any]:
    """Fraction of window area shaded by a horizontal overhang.

    Parameters (SI / degrees)
    -------------------------
    overhang_depth_m  : horizontal projection depth of overhang (m)
    window_height_m   : window height (m)
    solar_altitude_deg: solar altitude above horizon (degrees, 0–90)
    solar_azimuth_deg : solar azimuth (degrees from north, clockwise)
    facade_azimuth_deg: facade normal azimuth (degrees from north, clockwise)

    Returns
    -------
    {"ok": True, "shaded_fraction": float, "shadow_depth_m": float, "warnings": list}

    Geometric projection: shadow depth on window = overhang_depth × tan(alt) / cos(Δaz)
    shaded_fraction = min(shadow_depth / window_height, 1.0)
    Reference: CIBSE Guide A (2015) §5.5.
    Units: SI (m, dimensionless fraction).
    """
    try:
        overhang_depth_m = float(overhang_depth_m)
        window_height_m = float(window_height_m)
        solar_altitude_deg = float(solar_altitude_deg)
        solar_azimuth_deg = float(solar_azimuth_deg)
        facade_azimuth_deg = float(facade_azimuth_deg)

        if overhang_depth_m < 0:
            return {"ok": False, "reason": "overhang_depth_m must be >= 0"}
        if window_height_m <= 0:
            return {"ok": False, "reason": "window_height_m must be > 0"}
        if not (0.0 <= solar_altitude_deg <= 90.0):
            return {"ok": False, "reason": "solar_altitude_deg must be in [0, 90]"}

        # Angle between solar azimuth and facade normal
        delta_az = abs(solar_azimuth_deg - facade_azimuth_deg) % 360.0
        if delta_az > 180.0:
            delta_az = 360.0 - delta_az

        warn_list: List[str] = []

        # If sun is behind the facade, no direct shading from overhang
        if delta_az > 90.0:
            return {
                "ok": True,
                "shaded_fraction": 0.0,
                "shadow_depth_m": 0.0,
                "warnings": ["Sun is behind the facade — no direct solar incidence"],
            }

        alt_rad = math.radians(solar_altitude_deg)
        daz_rad = math.radians(delta_az)

        cos_daz = math.cos(daz_rad)
        if cos_daz < 1e-6:
            cos_daz = 1e-6

        tan_alt = math.tan(alt_rad)
        shadow_depth_m = overhang_depth_m * tan_alt / cos_daz
        shaded_fraction = min(shadow_depth_m / window_height_m, 1.0)
        shaded_fraction = max(shaded_fraction, 0.0)

        if shaded_fraction >= 1.0:
            msg = "Window is fully shaded by overhang at this sun position"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "shaded_fraction": round(shaded_fraction, 5),
            "shadow_depth_m": round(shadow_depth_m, 4),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# DAYLIGHTING
# ---------------------------------------------------------------------------

def daylight_factor(
    window_area_m2: float,
    floor_area_m2: float,
    Tv: float,
    *,
    room_depth_m: float = 5.0,
    room_width_m: float = 5.0,
    reflectance_avg: float = 0.5,
    sky_component_fraction: float = 0.45,
) -> Dict[str, Any]:
    """Average daylight factor (DF) using the BRE simplified formula.

    Parameters (SI / dimensionless)
    --------------------------------
    window_area_m2       : total glazing area (m²)
    floor_area_m2        : room floor area (m²)
    Tv                   : visible light transmittance of glazing (0–1)
    room_depth_m         : room depth perpendicular to window (m, default 5)
    room_width_m         : room width parallel to window (m, default 5)
    reflectance_avg      : area-weighted average surface reflectance (0–1, default 0.5)
    sky_component_fraction: fraction of unobstructed sky (0–1, default 0.45 for urban)

    Returns
    -------
    {"ok": True, "DF_percent": float,
     "window_to_floor_ratio": float, "warnings": list}

    DF = Tv × A_w × θ / (A_floor × (1 − R̄²))
    where θ = sky_component_fraction (Waldram diagram approximation).
    Reference: CIBSE Lighting Guide LG10; BRE Digest 309.
    Units: dimensionless (DF in %).
    """
    try:
        window_area_m2 = float(window_area_m2)
        floor_area_m2 = float(floor_area_m2)
        Tv = float(Tv)
        room_depth_m = float(room_depth_m)
        room_width_m = float(room_width_m)
        reflectance_avg = float(reflectance_avg)
        sky_component_fraction = float(sky_component_fraction)

        if window_area_m2 < 0:
            return {"ok": False, "reason": "window_area_m2 must be >= 0"}
        if floor_area_m2 <= 0:
            return {"ok": False, "reason": "floor_area_m2 must be > 0"}
        if not (0.0 <= Tv <= 1.0):
            return {"ok": False, "reason": "Tv must be in [0, 1]"}
        if not (0.0 < reflectance_avg < 1.0):
            return {"ok": False, "reason": "reflectance_avg must be in (0, 1)"}
        if not (0.0 < sky_component_fraction <= 1.0):
            return {"ok": False, "reason": "sky_component_fraction must be in (0, 1]"}

        denom = 1.0 - reflectance_avg ** 2
        if denom < 1e-6:
            return {"ok": False, "reason": "reflectance_avg too close to 1.0"}

        DF = Tv * window_area_m2 * sky_component_fraction / (floor_area_m2 * denom)
        DF_percent = DF * 100.0

        WFR = window_area_m2 / floor_area_m2

        warn_list: List[str] = []
        if DF_percent < 2.0:
            msg = f"Daylight factor {DF_percent:.2f}% < 2% — likely inadequate daylighting (CIBSE target: 2% residential)"
            _warnings.warn(msg)
            warn_list.append(msg)
        if DF_percent > 6.0:
            msg = f"Daylight factor {DF_percent:.2f}% > 6% — potential overheating risk"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "DF_percent": round(DF_percent, 3),
            "window_to_floor_ratio": round(WFR, 4),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def window_to_floor_ratio(
    window_area_m2: float,
    floor_area_m2: float,
) -> Dict[str, Any]:
    """Window-to-floor ratio (dimensionless).

    Parameters (SI)
    ---------------
    window_area_m2 : total glazing area (m²)
    floor_area_m2  : room or zone floor area (m²)

    Returns
    -------
    {"ok": True, "WFR": float,
     "window_area_m2": float, "floor_area_m2": float, "warnings": list}

    Typical targets: 0.10–0.20 residential, 0.15–0.25 office.
    Units: dimensionless.
    """
    try:
        window_area_m2 = float(window_area_m2)
        floor_area_m2 = float(floor_area_m2)

        if window_area_m2 < 0:
            return {"ok": False, "reason": "window_area_m2 must be >= 0"}
        if floor_area_m2 <= 0:
            return {"ok": False, "reason": "floor_area_m2 must be > 0"}

        WFR = window_area_m2 / floor_area_m2

        warn_list: List[str] = []
        if WFR < 0.10:
            msg = f"WFR {WFR:.3f} < 0.10 — potentially insufficient daylighting"
            _warnings.warn(msg)
            warn_list.append(msg)
        if WFR > 0.40:
            msg = f"WFR {WFR:.3f} > 0.40 — high glazing fraction, check solar gain and thermal performance"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "WFR": round(WFR, 5),
            "window_area_m2": round(window_area_m2, 4),
            "floor_area_m2": round(floor_area_m2, 4),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def no_sky_line_depth(
    window_head_height_m: float,
    *,
    multiplier: float = 2.0,
) -> Dict[str, Any]:
    """Depth at which no-sky-line falls (point where sky is no longer visible).

    Parameters (SI)
    ---------------
    window_head_height_m : height of window head above working plane (m)
    multiplier           : depth = multiplier × head height (default 2.0)

    Returns
    -------
    {"ok": True, "no_sky_line_depth_m": float, "window_head_height_m": float, "warnings": list}

    depth = multiplier × window_head_height_m
    Reference: BRE Digest 309 (1986); CIBSE Lighting Guide LG10.
    Units: SI (m).
    """
    try:
        window_head_height_m = float(window_head_height_m)
        multiplier = float(multiplier)

        if window_head_height_m <= 0:
            return {"ok": False, "reason": "window_head_height_m must be > 0"}
        if multiplier <= 0:
            return {"ok": False, "reason": "multiplier must be > 0"}

        depth = multiplier * window_head_height_m

        warn_list: List[str] = []
        return {
            "ok": True,
            "no_sky_line_depth_m": round(depth, 4),
            "window_head_height_m": round(window_head_height_m, 4),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# OVERHEATING
# ---------------------------------------------------------------------------

def overheating_hours(
    internal_gains_W: float,
    solar_gain_W: float,
    UA_W_per_K: float,
    T_outdoor_C_list: List[float],
    T_comfort_max_C: float,
) -> Dict[str, Any]:
    """Estimate hours above comfort threshold (simplified steady-state per hour).

    Parameters (SI)
    ---------------
    internal_gains_W  : total steady internal heat gains (W)
    solar_gain_W      : average solar heat gain (W) applied each hour
    UA_W_per_K        : whole-building UA (W/K)
    T_outdoor_C_list  : list of hourly outdoor temperatures (°C)
    T_comfort_max_C   : upper comfort threshold (°C)

    Returns
    -------
    {"ok": True, "overheating_hours": int, "total_hours": int,
     "overheating_fraction": float, "T_indoor_list": list (first 24), "warnings": list}

    T_indoor_h = T_outdoor_h + (Q_int + Q_solar) / UA  [free-floating steady state]
    Reference: CIBSE TM52:2013 (simplified free-float estimate).
    Units: SI (°C, hours).
    """
    try:
        internal_gains_W = float(internal_gains_W)
        solar_gain_W = float(solar_gain_W)
        UA_W_per_K = float(UA_W_per_K)
        T_comfort_max_C = float(T_comfort_max_C)

        if not T_outdoor_C_list:
            return {"ok": False, "reason": "T_outdoor_C_list is empty"}
        if UA_W_per_K <= 0:
            return {"ok": False, "reason": "UA_W_per_K must be > 0"}

        Q_total = internal_gains_W + solar_gain_W
        delta_T_rise = Q_total / UA_W_per_K

        overheating_count = 0
        T_indoor_sample: List[float] = []
        for i, T_out in enumerate(T_outdoor_C_list):
            T_in = float(T_out) + delta_T_rise
            if i < 24:
                T_indoor_sample.append(round(T_in, 2))
            if T_in > T_comfort_max_C:
                overheating_count += 1

        total_hours = len(T_outdoor_C_list)
        frac = overheating_count / total_hours

        warn_list: List[str] = []
        if frac > 0.10:
            msg = (
                f"Overheating fraction {frac:.1%} > 10% — significant overheating risk; "
                "consider solar shading, night ventilation, or reduced internal gains."
            )
            _warnings.warn(msg)
            warn_list.append(msg)
        elif frac > 0.01:
            msg = f"Overheating fraction {frac:.1%} — monitor overheating risk"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "overheating_hours": overheating_count,
            "total_hours": total_hours,
            "overheating_fraction": round(frac, 5),
            "T_indoor_sample_first24": T_indoor_sample,
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# BENCHMARKING & COMPLIANCE
# ---------------------------------------------------------------------------

def eui(
    annual_energy_kWh: float,
    floor_area_m2: float,
) -> Dict[str, Any]:
    """Energy Use Intensity (EUI) in kWh/(m²·yr).

    Parameters (SI)
    ---------------
    annual_energy_kWh : total annual building energy use (kWh)
    floor_area_m2     : gross conditioned floor area (m²)

    Returns
    -------
    {"ok": True, "EUI_kWh_m2yr": float, "warnings": list}

    Typical ranges: residential 50–150, office 100–250, hospital 300–700 kWh/(m²·yr).
    Units: kWh/(m²·yr).
    """
    try:
        annual_energy_kWh = float(annual_energy_kWh)
        floor_area_m2 = float(floor_area_m2)

        if annual_energy_kWh < 0:
            return {"ok": False, "reason": "annual_energy_kWh must be >= 0"}
        if floor_area_m2 <= 0:
            return {"ok": False, "reason": "floor_area_m2 must be > 0"}

        EUI = annual_energy_kWh / floor_area_m2

        warn_list: List[str] = []
        if EUI > 500:
            msg = f"EUI {EUI:.0f} kWh/(m²·yr) is very high — review energy use breakdown"
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "EUI_kWh_m2yr": round(EUI, 3),
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# ASHRAE 90.1 ENVELOPE COMPLIANCE
# ---------------------------------------------------------------------------

# ASHRAE 90.1-2022 Table 5.5-x maximum U-values (W/(m²·K)) by climate zone
# Climate zones: 1A/1B, 2A/2B, 3A/3B/3C, 4A/4B/4C, 5A/5B/5C, 6A/6B, 7, 8
# Simplified: zones mapped to integer 1–8 (use zone number, not letter)
# Values from ASHRAE 90.1-2022 Tables 5.5-1 through 5.5-8 (Non-Residential)
# Note: Residential and semi-heated may differ — flag if needed.

_ASHRAE_901_MAX_U: Dict[str, Dict[int, float]] = {
    "roof": {
        1: 0.273, 2: 0.273, 3: 0.273, 4: 0.180, 5: 0.180, 6: 0.136, 7: 0.119, 8: 0.119,
    },
    "wall_above_grade": {
        1: 0.857, 2: 0.701, 3: 0.513, 4: 0.365, 5: 0.365, 6: 0.319, 7: 0.278, 8: 0.234,
    },
    "floor": {
        1: 9.999, 2: 9.999, 3: 1.136, 4: 0.278, 5: 0.278, 6: 0.236, 7: 0.200, 8: 0.200,
    },
    "window_vertical": {
        1: 3.977, 2: 3.693, 3: 3.977, 4: 3.977, 5: 3.693, 6: 3.977, 7: 3.977, 8: 3.977,
    },
    "door_opaque": {
        1: 3.977, 2: 3.977, 3: 3.977, 4: 2.839, 5: 2.839, 6: 2.839, 7: 2.839, 8: 2.839,
    },
}

# Note: slab_on_grade uses F-factor (W/(m·K)) not U-factor — handled separately
_ASHRAE_901_MAX_F_SLAB: Dict[int, float] = {
    1: 9.999, 2: 9.999, 3: 9.999, 4: 0.860, 5: 0.860, 6: 0.738, 7: 0.738, 8: 0.738,
}


def ashrae901_envelope_compliance(
    assembly_type: str,
    U_proposed: float,
    climate_zone: int,
    *,
    F_proposed: Optional[float] = None,
) -> Dict[str, Any]:
    """ASHRAE 90.1-2022 prescriptive envelope compliance check.

    Parameters (SI)
    ---------------
    assembly_type : "roof" | "wall_above_grade" | "floor" | "window_vertical"
                    | "door_opaque" | "slab_on_grade"
    U_proposed    : proposed U-value (W/(m²·K)); for slab_on_grade, ignored
    climate_zone  : integer 1–8 (use primary number; sub-zones a/b/c treated as same)
    F_proposed    : for slab_on_grade only — proposed F-factor (W/(m·K))

    Returns
    -------
    {"ok": True, "compliant": bool, "U_proposed": float,
     "U_max_W_m2K": float (or "F_max_W_mK": float for slab),
     "assembly_type": str, "climate_zone": int,
     "table_reference": str, "warnings": list}

    Reference: ASHRAE 90.1-2022 Tables 5.5-1 through 5.5-8.
    Units: SI (W/(m²·K) for U, W/(m·K) for F).
    """
    try:
        assembly_type = str(assembly_type)
        climate_zone = int(climate_zone)

        valid_types = list(_ASHRAE_901_MAX_U.keys()) + ["slab_on_grade"]
        if assembly_type not in valid_types:
            return {
                "ok": False,
                "reason": f"assembly_type must be one of {valid_types}",
            }
        if climate_zone not in range(1, 9):
            return {"ok": False, "reason": "climate_zone must be an integer 1–8"}

        warn_list: List[str] = []

        if assembly_type == "slab_on_grade":
            F_max = _ASHRAE_901_MAX_F_SLAB[climate_zone]
            if F_proposed is None:
                return {"ok": False, "reason": "slab_on_grade requires F_proposed (W/(m·K))"}
            F_proposed = float(F_proposed)
            compliant = F_proposed <= F_max
            if not compliant:
                msg = (
                    f"slab_on_grade F-factor {F_proposed:.3f} W/(m·K) exceeds "
                    f"ASHRAE 90.1-2022 maximum {F_max:.3f} W/(m·K) for CZ{climate_zone}"
                )
                _warnings.warn(msg)
                warn_list.append(msg)
            return {
                "ok": True,
                "compliant": compliant,
                "F_proposed_W_mK": F_proposed,
                "F_max_W_mK": F_max,
                "assembly_type": assembly_type,
                "climate_zone": climate_zone,
                "table_reference": f"ASHRAE 90.1-2022 Table 5.5-{climate_zone} (Non-Res)",
                "warnings": warn_list,
            }

        U_proposed_val = float(U_proposed)
        U_max = _ASHRAE_901_MAX_U[assembly_type][climate_zone]
        compliant = U_proposed_val <= U_max

        if not compliant:
            msg = (
                f"{assembly_type} U-value {U_proposed_val:.3f} W/(m²·K) exceeds "
                f"ASHRAE 90.1-2022 maximum {U_max:.3f} W/(m²·K) for CZ{climate_zone} — "
                "fails envelope criterion"
            )
            _warnings.warn(msg)
            warn_list.append(msg)

        return {
            "ok": True,
            "compliant": compliant,
            "U_proposed_W_m2K": round(U_proposed_val, 6),
            "U_max_W_m2K": round(U_max, 6),
            "assembly_type": assembly_type,
            "climate_zone": climate_zone,
            "table_reference": f"ASHRAE 90.1-2022 Table 5.5-{climate_zone} (Non-Res)",
            "warnings": warn_list,
        }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}
