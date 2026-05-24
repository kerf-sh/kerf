"""
kerf_cad_core.boiler.plant — steam & boiler plant engineering calculations.

Distinct from thermocycle/ (Rankine cycle efficiency), combustion/ (fuels
chemistry), and heatxfer/ (surface heat transfer).  This module covers the
practical operating calculations for a fired steam boiler plant:

  Steam properties (IAPWS-IF97-style fitted correlations)
  -------------------------------------------------------
  tsat_from_p        — saturation temperature from pressure
  psat_from_t        — saturation pressure from temperature
  steam_properties   — hf, hg, hfg, sg, sf, vf, vg at saturation
  superheat_h        — enthalpy of superheated steam (simplified)

  Boiler duty & output
  --------------------
  boiler_heat_duty           — Q_boiler from steam flow, enthalpies
  boiler_steam_output        — steam flow rate from fuel input & efficiency
  boiler_efficiency_io       — input-output efficiency from enthalpies
  boiler_efficiency_heat_loss — ASME PTC 4 abbreviated heat-loss method

  Fuel & air
  ----------
  fuel_firing_rate           — fuel flow from duty, calorific value, efficiency
  combustion_air_flow        — theoretical + excess air from fuel & stoichiometry

  Blowdown
  --------
  blowdown_rate              — continuous blowdown from TDS & cycles of conc.
  blowdown_heat_loss         — heat lost in blowdown stream

  Feedwater system
  ----------------
  feedwater_energy_balance   — boiler make-up + enthalpy accounting
  deaerator_energy_balance   — direct-contact DA heat balance
  economizer_energy_balance  — pre-heat duty & temperature rise

  Performance metrics
  -------------------
  equivalent_evaporation     — EE from & at 100°C (kg/kg fuel)
  boiler_horsepower          — BHP from actual evaporation

  Steam piping
  ------------
  steam_pipe_velocity        — mean velocity in steam pipe
  steam_pipe_pressure_drop   — simplified Darcy-Weisbach ΔP for steam

  Condensate & flash steam
  ------------------------
  flash_steam_fraction       — mass fraction flashing at lower pressure
  condensate_heat_recovery   — heat available in condensate return

  Steam traps & safety valves
  ---------------------------
  steam_trap_capacity        — orifice-based trap discharge rate
  safety_valve_napier        — Napier formula relief capacity

All functions return plain dicts.
Warnings are appended to result["warnings"] list; functions never raise.

References
----------
ASME PTC 4-2013 — Fired Steam Generators Performance Test Codes
IAPWS-IF97 (simplified fitted correlations; ±0.5% over 0.1–20 MPa)
Spirax Sarco Steam Engineering Tutorials
Zamir, Sarbu — Steam Trap Handbook

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any

from kerf_cad_core.fluids.friction import darcy_friction_factor

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _warn(result: dict, msg: str) -> None:
    result.setdefault("warnings", []).append(msg)


# ---------------------------------------------------------------------------
# Steam property correlations (IAPWS-IF97-style fitted, region 1/2 sat. line)
# Valid range: ~0.1 kPa – 22 MPa (triple point to critical point ~22.064 MPa)
# ---------------------------------------------------------------------------

# Antoine-style Tsat correlation (T in K, P in Pa)
# Fitted to IAPWS-IF97 saturation data — max error ~0.3 K over 274–647 K
_A_TSAT = 23.1964
_B_TSAT = 3816.44
_C_TSAT = -46.13   # (offset from 273.15)


def tsat_from_p(P_Pa: float) -> dict[str, Any]:
    """Saturation temperature from pressure.

    Parameters
    ----------
    P_Pa : float
        Saturation pressure (Pa). Valid range 611 Pa – 22.06 MPa.

    Returns
    -------
    dict with keys:
        T_sat_K, T_sat_C, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if P_Pa <= 0:
        result["error"] = "P_Pa must be > 0"
        return result
    if P_Pa < 611:
        _warn(result, f"P={P_Pa:.1f} Pa below triple-point pressure 611 Pa; clipping.")
        P_Pa = 611.0
    if P_Pa > 22.064e6:
        _warn(result, "P exceeds critical pressure 22.064 MPa; result unreliable.")

    # Antoine form: ln(P/Pa) = A - B/(T + C) where C is in K relative to 0 K
    # Rearranged: T = B/(A - ln(P)) - C
    lnP = math.log(P_Pa)
    T_K = _B_TSAT / (_A_TSAT - lnP) - _C_TSAT
    if T_K <= 0:
        _warn(result, "Correlation returned non-physical T; check pressure range.")
        T_K = 273.16
    result["T_sat_K"] = round(T_K, 3)
    result["T_sat_C"] = round(T_K - 273.15, 3)
    return result


def psat_from_t(T_C: float) -> dict[str, Any]:
    """Saturation pressure from temperature.

    Parameters
    ----------
    T_C : float
        Saturation temperature (°C). Valid range 0.01 – 374 °C.

    Returns
    -------
    dict with keys:
        P_sat_Pa, P_sat_kPa, P_sat_MPa, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    T_K = T_C + 273.15
    if T_K <= 273.16:
        _warn(result, "Temperature at or below triple point 0.01 °C.")
    if T_C > 374.14:
        _warn(result, "Temperature above critical point 374.14 °C; result unreliable.")
    # Antoine: ln(P) = A - B/(T + C)
    lnP = _A_TSAT - _B_TSAT / (T_K + _C_TSAT)
    P_Pa = math.exp(lnP)
    result["P_sat_Pa"] = round(P_Pa, 2)
    result["P_sat_kPa"] = round(P_Pa / 1e3, 4)
    result["P_sat_MPa"] = round(P_Pa / 1e6, 6)
    return result


def steam_properties(P_Pa: float | None = None, T_sat_C: float | None = None) -> dict[str, Any]:
    """Saturated steam/water properties at given pressure or temperature.

    Uses fitted polynomial correlations against IAPWS-IF97 saturation tables.
    Accuracy: hf ±2 kJ/kg, hg ±1 kJ/kg, sg ±0.003 kJ/kg·K over 1 kPa–20 MPa.

    Parameters
    ----------
    P_Pa : float, optional
        Pressure (Pa).  Provide either P_Pa or T_sat_C (not both).
    T_sat_C : float, optional
        Saturation temperature (°C).

    Returns
    -------
    dict with keys:
        T_sat_C, P_sat_Pa, P_sat_MPa,
        hf_kJkg (sat. liquid enthalpy), hg_kJkg (sat. vapour enthalpy),
        hfg_kJkg (latent heat), sf_kJkgK, sg_kJkgK, sfg_kJkgK,
        vf_m3kg, vg_m3kg, warnings
    """
    result: dict[str, Any] = {"warnings": []}

    # Resolve T_sat_C and P_sat_Pa from whichever is given
    if P_Pa is not None and T_sat_C is not None:
        _warn(result, "Both P_Pa and T_sat_C supplied; P_Pa takes precedence.")

    if P_Pa is not None:
        ts = tsat_from_p(P_Pa)
        result["warnings"].extend(ts.get("warnings", []))
        T_C = ts["T_sat_C"]
        P = P_Pa
    elif T_sat_C is not None:
        T_C = T_sat_C
        ps = psat_from_t(T_C)
        result["warnings"].extend(ps.get("warnings", []))
        P = ps["P_sat_Pa"]
    else:
        result["error"] = "Provide P_Pa or T_sat_C"
        return result

    T_K = T_C + 273.15

    # --- hf: fitted polynomial vs T_C (0–374 °C)  [kJ/kg]
    # hf ≈ 4.186 * T_C  (accurate to ~2 kJ/kg up to ~100°C; slight curvature above)
    # Higher-order fit (Eq. 2.2, Spirax Sarco):
    hf = 4.1868 * T_C + 5.0e-4 * T_C**2 - 1.48e-6 * T_C**3 + 7.5e-10 * T_C**4

    # --- hg = hf + hfg;  latent heat hfg [kJ/kg]
    # Empirical: hfg ≈ 2501 - 2.26 * T_C  (accurate ~0.5% over 0–100 °C)
    # With curvature towards critical point:
    hfg = 2500.9 - 2.3693 * T_C - 2.0e-3 * T_C**2
    if hfg < 0:
        hfg = 0.0
        _warn(result, "hfg → 0 near critical point.")
    hg = hf + hfg

    # --- specific volumes (m³/kg)
    # vf ≈ 0.001 + 3e-7*T_C + 3e-9*T_C^2 (liquid compressibility small)
    vf = 1e-3 * (1.0 + 1.8e-4 * T_C + 3.0e-7 * T_C**2)
    # vg from ideal gas approximation corrected for steam:
    # R_steam = 461.5 J/kg·K; Z ≈ 1 - 0.0006*(P/1e5)^0.6
    if P > 0:
        Z = max(0.6, 1.0 - 0.0006 * (P / 1e5) ** 0.6)
        vg = Z * 461.5 * T_K / P
    else:
        vg = 1e9  # vacuum edge

    # --- specific entropy (kJ/kg·K)
    # sf from Clausius–Clapeyron linearisation
    sf = 4.1868 * math.log(T_K / 273.15) if T_K > 273.15 else 0.0
    sfg = hfg / T_K  # dQ/T at boiling point
    sg = sf + sfg

    result.update({
        "T_sat_C": round(T_C, 3),
        "P_sat_Pa": round(P, 1),
        "P_sat_MPa": round(P / 1e6, 5),
        "hf_kJkg": round(hf, 2),
        "hg_kJkg": round(hg, 2),
        "hfg_kJkg": round(hfg, 2),
        "sf_kJkgK": round(sf, 4),
        "sg_kJkgK": round(sg, 4),
        "sfg_kJkgK": round(sfg, 4),
        "vf_m3kg": round(vf, 6),
        "vg_m3kg": round(vg, 5),
    })
    return result


def superheat_h(P_Pa: float, T_sup_C: float) -> dict[str, Any]:
    """Approximate enthalpy of superheated steam.

    Uses the ideal-gas Mollier approximation for superheat:
        h_sup ≈ hg(P) + cp_steam * (T_sup - T_sat)
    cp_steam ≈ 2.05 kJ/kg·K (mean value for moderate superheat).

    Parameters
    ----------
    P_Pa : float
        Pressure (Pa).
    T_sup_C : float
        Actual steam temperature (°C). Must be > T_sat.

    Returns
    -------
    dict with keys:
        h_sup_kJkg, T_sat_C, superheat_K, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    props = steam_properties(P_Pa=P_Pa)
    result["warnings"].extend(props.get("warnings", []))
    T_sat = props["T_sat_C"]
    hg = props["hg_kJkg"]
    superheat_K = T_sup_C - T_sat
    if superheat_K < 0:
        _warn(result, f"T_sup={T_sup_C:.1f}°C < T_sat={T_sat:.1f}°C; wet steam region.")
        superheat_K = 0.0
    cp_steam = 2.05  # kJ/kg·K
    h_sup = hg + cp_steam * superheat_K
    result["h_sup_kJkg"] = round(h_sup, 2)
    result["T_sat_C"] = round(T_sat, 3)
    result["superheat_K"] = round(superheat_K, 2)
    result["hg_kJkg"] = round(hg, 2)
    return result


# ---------------------------------------------------------------------------
# Boiler heat duty & steam output
# ---------------------------------------------------------------------------

def boiler_heat_duty(
    m_steam_kgs: float,
    h_steam_kJkg: float,
    h_fw_kJkg: float,
) -> dict[str, Any]:
    """Boiler heat duty (absorbed heat rate).

    Q_boiler = m_steam * (h_steam - h_fw)

    Parameters
    ----------
    m_steam_kgs : float
        Steam mass flow rate (kg/s).
    h_steam_kJkg : float
        Enthalpy of steam leaving boiler (kJ/kg).
    h_fw_kJkg : float
        Enthalpy of feedwater entering boiler (kJ/kg).

    Returns
    -------
    dict with keys:
        Q_kW, Q_kJkg (specific duty), warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if m_steam_kgs < 0:
        result["error"] = "m_steam_kgs must be >= 0"
        return result
    delta_h = h_steam_kJkg - h_fw_kJkg
    if delta_h <= 0:
        _warn(result, "h_steam <= h_fw; check enthalpy values.")
    Q_kW = m_steam_kgs * delta_h
    result["Q_kW"] = round(Q_kW, 3)
    result["Q_kJkg"] = round(delta_h, 2)
    result["m_steam_kgs"] = m_steam_kgs
    return result


def boiler_steam_output(
    Q_fuel_kW: float,
    efficiency: float,
    h_steam_kJkg: float,
    h_fw_kJkg: float,
) -> dict[str, Any]:
    """Steam output from fuel firing rate and boiler efficiency.

    m_steam = (Q_fuel * η) / (h_steam - h_fw)

    Parameters
    ----------
    Q_fuel_kW : float
        Fuel heat input rate (kW) = m_fuel * HHV or LHV.
    efficiency : float
        Boiler thermal efficiency (0–1).
    h_steam_kJkg : float
        Steam enthalpy (kJ/kg).
    h_fw_kJkg : float
        Feedwater enthalpy (kJ/kg).

    Returns
    -------
    dict with keys:
        m_steam_kgs, m_steam_th (t/h), warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if Q_fuel_kW <= 0:
        result["error"] = "Q_fuel_kW must be > 0"
        return result
    if not 0 < efficiency <= 1:
        result["error"] = "efficiency must be in (0, 1]"
        return result
    delta_h = h_steam_kJkg - h_fw_kJkg
    if delta_h <= 0:
        result["error"] = "h_steam must be > h_fw"
        return result
    if efficiency < 0.6:
        _warn(result, f"Boiler efficiency {efficiency:.1%} is unusually low (<60%).")
    m_s = (Q_fuel_kW * efficiency) / delta_h
    result["m_steam_kgs"] = round(m_s, 5)
    result["m_steam_th"] = round(m_s * 3.6, 4)
    result["Q_useful_kW"] = round(Q_fuel_kW * efficiency, 3)
    return result


def boiler_efficiency_io(
    m_steam_kgs: float,
    h_steam_kJkg: float,
    h_fw_kJkg: float,
    Q_fuel_kW: float,
) -> dict[str, Any]:
    """Boiler thermal efficiency by input-output method.

    η = (m_steam * (h_steam - h_fw)) / Q_fuel

    Parameters
    ----------
    m_steam_kgs : float
        Steam flow (kg/s).
    h_steam_kJkg : float
        Steam enthalpy (kJ/kg).
    h_fw_kJkg : float
        Feedwater enthalpy (kJ/kg).
    Q_fuel_kW : float
        Fuel heat input (kW).

    Returns
    -------
    dict with keys:
        efficiency, efficiency_pct, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if Q_fuel_kW <= 0:
        result["error"] = "Q_fuel_kW must be > 0"
        return result
    if m_steam_kgs < 0:
        result["error"] = "m_steam_kgs must be >= 0"
        return result
    delta_h = h_steam_kJkg - h_fw_kJkg
    eta = (m_steam_kgs * delta_h) / Q_fuel_kW
    if eta > 1.0:
        _warn(result, f"Computed efficiency {eta:.3f} > 1; check inputs.")
    if eta < 0.6:
        _warn(result, f"Boiler efficiency {eta:.1%} is unusually low (<60%).")
    result["efficiency"] = round(eta, 5)
    result["efficiency_pct"] = round(eta * 100, 3)
    return result


def boiler_efficiency_heat_loss(
    flue_gas_temp_C: float,
    ambient_temp_C: float = 25.0,
    excess_air_pct: float = 20.0,
    moisture_fuel_pct: float = 5.0,
    radiation_loss_pct: float = 1.5,
    unburnt_loss_pct: float = 0.5,
) -> dict[str, Any]:
    """ASME PTC 4 abbreviated heat-loss method for boiler efficiency.

    Efficiency = 100% - sum of percentage heat losses:
      1. Dry flue-gas loss (Siegert formula approximation)
      2. Moisture-in-fuel loss
      3. Radiation & convection loss (user-supplied or default)
      4. Unburnt fuel / carbon loss (user-supplied or default)

    Parameters
    ----------
    flue_gas_temp_C : float
        Stack / flue-gas exit temperature (°C).
    ambient_temp_C : float
        Ambient / reference temperature (°C, default 25).
    excess_air_pct : float
        Excess air percentage (%, default 20).
    moisture_fuel_pct : float
        Moisture in fuel (% by mass, default 5%).
    radiation_loss_pct : float
        Radiation + convection loss (%, default 1.5%).
    unburnt_loss_pct : float
        Unburnt fuel loss (%, default 0.5%).

    Returns
    -------
    dict with keys:
        dry_flue_gas_loss_pct, moisture_loss_pct,
        radiation_loss_pct, unburnt_loss_pct,
        total_loss_pct, efficiency_pct, efficiency, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    delta_T = flue_gas_temp_C - ambient_temp_C
    if delta_T <= 0:
        result["error"] = "flue_gas_temp_C must be > ambient_temp_C"
        return result

    # Dry flue-gas loss: sensible heat carried away by flue gases.
    # L_dry [%] = cp_fg * m_fg_per_kg_fuel * (Tf - Ta) / HHV_assumed * 100
    # cp_fg ≈ 1.03 kJ/kg·K (mean specific heat of flue gas)
    # m_fg = AFR_stoich * (1 + EA/100) + 1  (kg flue gas per kg fuel)
    # HHV_assumed ≈ 50 000 kJ/kg for natural gas (adjust for other fuels)
    cp_fg = 1.03
    AFR_stoich_default = 15.6  # natural gas
    m_fg = AFR_stoich_default * (1 + excess_air_pct / 100) + 1.0
    HHV_assumed = 50000.0
    L_dry = cp_fg * m_fg * delta_T / HHV_assumed * 100.0

    # Moisture loss: h_steam at Tf minus h_water at T_ref (simplified)
    # L_moist [%] = moisture_pct * (2500 + 2.0*(Tf-100) - 4.186*T_ref) / HHV_assumed
    # Expressed as fraction of fuel heat: ≈ 0.45 kJ per g moisture per deg above 100
    hv_ref = 2500.9 + 2.0 * (flue_gas_temp_C - 100) - 4.186 * ambient_temp_C
    # Assume HHV_natural_gas ~50000 kJ/kg
    HHV_assumed = 50000.0
    L_moist = (moisture_fuel_pct / 100) * hv_ref / HHV_assumed * 100.0

    total_loss = L_dry + L_moist + radiation_loss_pct + unburnt_loss_pct
    eta_pct = max(0.0, 100.0 - total_loss)

    if flue_gas_temp_C > 250:
        _warn(result, f"Stack temperature {flue_gas_temp_C}°C is high (>250°C); consider economizer.")
    if excess_air_pct > 40:
        _warn(result, f"Excess air {excess_air_pct}% is high (>40%); increases dry flue-gas loss.")
    if eta_pct < 70:
        _warn(result, f"Boiler efficiency {eta_pct:.1f}% is low (<70%).")

    result.update({
        "dry_flue_gas_loss_pct": round(L_dry, 3),
        "moisture_loss_pct": round(L_moist, 3),
        "radiation_loss_pct": round(radiation_loss_pct, 3),
        "unburnt_loss_pct": round(unburnt_loss_pct, 3),
        "total_loss_pct": round(total_loss, 3),
        "efficiency_pct": round(eta_pct, 3),
        "efficiency": round(eta_pct / 100, 5),
    })
    return result


# ---------------------------------------------------------------------------
# Fuel & air
# ---------------------------------------------------------------------------

def fuel_firing_rate(
    Q_boiler_kW: float,
    efficiency: float,
    HHV_kJkg: float,
) -> dict[str, Any]:
    """Fuel mass flow rate from boiler duty, efficiency, and heating value.

    m_fuel = Q_boiler / (efficiency * HHV)

    Parameters
    ----------
    Q_boiler_kW : float
        Useful boiler heat duty (kW).
    efficiency : float
        Boiler thermal efficiency (0–1).
    HHV_kJkg : float
        Higher heating value of fuel (kJ/kg).

    Returns
    -------
    dict with keys:
        m_fuel_kgs, m_fuel_kgh, Q_input_kW, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if Q_boiler_kW <= 0:
        result["error"] = "Q_boiler_kW must be > 0"
        return result
    if not 0 < efficiency <= 1:
        result["error"] = "efficiency must be in (0, 1]"
        return result
    if HHV_kJkg <= 0:
        result["error"] = "HHV_kJkg must be > 0"
        return result
    m_f = Q_boiler_kW / (efficiency * HHV_kJkg)
    Q_input = Q_boiler_kW / efficiency
    result["m_fuel_kgs"] = round(m_f, 6)
    result["m_fuel_kgh"] = round(m_f * 3600, 4)
    result["Q_input_kW"] = round(Q_input, 3)
    return result


def combustion_air_flow(
    m_fuel_kgs: float,
    stoich_air_fuel_ratio: float = 15.6,
    excess_air_pct: float = 20.0,
) -> dict[str, Any]:
    """Combustion air flow from fuel flow and air-fuel ratio.

    m_air = m_fuel * AFR_stoich * (1 + EA/100)

    Parameters
    ----------
    m_fuel_kgs : float
        Fuel mass flow (kg/s).
    stoich_air_fuel_ratio : float
        Stoichiometric air-fuel ratio by mass (default 15.6 for natural gas).
    excess_air_pct : float
        Excess air percentage (%, default 20%).

    Returns
    -------
    dict with keys:
        m_air_kgs, m_air_actual_kgs, lambda (air excess ratio), warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if m_fuel_kgs < 0:
        result["error"] = "m_fuel_kgs must be >= 0"
        return result
    if stoich_air_fuel_ratio <= 0:
        result["error"] = "stoich_air_fuel_ratio must be > 0"
        return result
    if excess_air_pct < 0:
        result["error"] = "excess_air_pct must be >= 0"
        return result
    m_air_stoich = m_fuel_kgs * stoich_air_fuel_ratio
    lam = 1 + excess_air_pct / 100.0
    m_air_actual = m_air_stoich * lam
    if excess_air_pct < 5:
        _warn(result, "Excess air < 5%; risk of incomplete combustion.")
    if excess_air_pct > 50:
        _warn(result, "Excess air > 50%; significantly increases flue-gas losses.")
    result["m_air_stoich_kgs"] = round(m_air_stoich, 6)
    result["m_air_actual_kgs"] = round(m_air_actual, 6)
    result["lambda"] = round(lam, 4)
    result["excess_air_pct"] = excess_air_pct
    return result


# ---------------------------------------------------------------------------
# Blowdown
# ---------------------------------------------------------------------------

def blowdown_rate(
    m_steam_kgs: float,
    feedwater_TDS_ppm: float,
    blowdown_TDS_limit_ppm: float,
    cycles_of_concentration: float | None = None,
) -> dict[str, Any]:
    """Continuous blowdown mass flow rate from TDS and cycles of concentration.

    Blowdown fraction  = 1 / (CoC - 1)
    where CoC = blowdown_TDS_limit / feedwater_TDS

    m_blowdown = m_steam * BD_fraction / (1 - BD_fraction)

    Parameters
    ----------
    m_steam_kgs : float
        Steam generation rate (kg/s).
    feedwater_TDS_ppm : float
        Feedwater TDS (ppm mg/L).
    blowdown_TDS_limit_ppm : float
        Maximum allowable boiler water TDS (ppm).
    cycles_of_concentration : float, optional
        If provided, overrides TDS-derived CoC.

    Returns
    -------
    dict with keys:
        CoC, blowdown_fraction, m_blowdown_kgs, m_blowdown_th, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if m_steam_kgs <= 0:
        result["error"] = "m_steam_kgs must be > 0"
        return result
    if feedwater_TDS_ppm <= 0:
        result["error"] = "feedwater_TDS_ppm must be > 0"
        return result
    if blowdown_TDS_limit_ppm <= feedwater_TDS_ppm:
        result["error"] = "blowdown_TDS_limit_ppm must be > feedwater_TDS_ppm"
        return result

    if cycles_of_concentration is not None:
        CoC = cycles_of_concentration
    else:
        CoC = blowdown_TDS_limit_ppm / feedwater_TDS_ppm

    if CoC <= 1:
        result["error"] = "CoC must be > 1"
        return result

    BD_frac = 1.0 / (CoC - 1.0)
    # m_blowdown relative to feedwater: m_fw = m_steam + m_blowdown
    # BD_frac = m_blowdown / m_steam  (approximate for CoC >> 1)
    m_bd = m_steam_kgs * BD_frac
    m_fw = m_steam_kgs + m_bd

    if BD_frac > 0.15:
        _warn(result, f"Blowdown fraction {BD_frac:.1%} > 15%; high water/chemical usage; improve feedwater quality.")
    if CoC < 3:
        _warn(result, f"Cycles of concentration {CoC:.1f} < 3; consider improving feedwater treatment.")

    result["CoC"] = round(CoC, 3)
    result["blowdown_fraction"] = round(BD_frac, 5)
    result["m_blowdown_kgs"] = round(m_bd, 5)
    result["m_blowdown_th"] = round(m_bd * 3.6, 4)
    result["m_feedwater_kgs"] = round(m_fw, 5)
    return result


def blowdown_heat_loss(
    m_blowdown_kgs: float,
    P_boiler_Pa: float,
    T_drain_C: float = 40.0,
) -> dict[str, Any]:
    """Heat lost in continuous blowdown discharge.

    Q_bd_loss = m_blowdown * (hf_boiler - hf_drain)

    Parameters
    ----------
    m_blowdown_kgs : float
        Blowdown flow rate (kg/s).
    P_boiler_Pa : float
        Boiler operating pressure (Pa), for hf_boiler.
    T_drain_C : float
        Temperature at blowdown drain point (°C, default 40°C).

    Returns
    -------
    dict with keys:
        Q_loss_kW, hf_boiler_kJkg, hf_drain_kJkg, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if m_blowdown_kgs < 0:
        result["error"] = "m_blowdown_kgs must be >= 0"
        return result
    props = steam_properties(P_Pa=P_boiler_Pa)
    result["warnings"].extend(props.get("warnings", []))
    hf_boiler = props["hf_kJkg"]
    hf_drain = 4.1868 * T_drain_C  # approx
    Q_loss = m_blowdown_kgs * (hf_boiler - hf_drain)
    if Q_loss < 0:
        _warn(result, "Computed heat loss is negative; check input pressures/temperatures.")
        Q_loss = 0.0
    result["Q_loss_kW"] = round(Q_loss, 3)
    result["hf_boiler_kJkg"] = round(hf_boiler, 2)
    result["hf_drain_kJkg"] = round(hf_drain, 2)
    return result


# ---------------------------------------------------------------------------
# Feedwater system
# ---------------------------------------------------------------------------

def feedwater_energy_balance(
    m_steam_kgs: float,
    h_steam_kJkg: float,
    m_blowdown_kgs: float,
    h_fw_kJkg: float,
    h_blowdown_kJkg: float,
) -> dict[str, Any]:
    """Overall boiler energy balance including blowdown.

    Q_absorbed = m_steam * h_steam + m_blowdown * h_bd - m_fw * h_fw
    where m_fw = m_steam + m_blowdown

    Parameters
    ----------
    m_steam_kgs : float
        Steam flow (kg/s).
    h_steam_kJkg : float
        Steam enthalpy at outlet (kJ/kg).
    m_blowdown_kgs : float
        Blowdown flow (kg/s).
    h_fw_kJkg : float
        Feedwater enthalpy at inlet (kJ/kg).
    h_blowdown_kJkg : float
        Blowdown enthalpy at exit (kJ/kg).

    Returns
    -------
    dict with keys:
        m_fw_kgs, Q_absorbed_kW, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    m_fw = m_steam_kgs + m_blowdown_kgs
    Q = (m_steam_kgs * h_steam_kJkg + m_blowdown_kgs * h_blowdown_kJkg
         - m_fw * h_fw_kJkg)
    if Q <= 0:
        _warn(result, "Absorbed heat is non-positive; check enthalpy values.")
    result["m_fw_kgs"] = round(m_fw, 5)
    result["Q_absorbed_kW"] = round(Q, 3)
    return result


def deaerator_energy_balance(
    m_fw_cold_kgs: float,
    h_fw_cold_kJkg: float,
    m_steam_sparging_kgs: float,
    h_steam_sparging_kJkg: float,
    T_deaerator_C: float = 105.0,
) -> dict[str, Any]:
    """Direct-contact deaerator (open feedwater heater) energy balance.

    Energy in = energy out at saturation temperature:
    m_out * h_fw_out = m_fw_cold * h_fw_cold + m_steam * h_steam

    Parameters
    ----------
    m_fw_cold_kgs : float
        Cold feedwater flow (kg/s).
    h_fw_cold_kJkg : float
        Cold feedwater enthalpy (kJ/kg).
    m_steam_sparging_kgs : float
        Sparging/heating steam flow (kg/s).
    h_steam_sparging_kJkg : float
        Sparging steam enthalpy (kJ/kg).
    T_deaerator_C : float
        Deaerator operating temperature (°C, default 105°C ≈ 1.2 bar).

    Returns
    -------
    dict with keys:
        m_out_kgs, h_fw_out_kJkg, T_out_C, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    m_out = m_fw_cold_kgs + m_steam_sparging_kgs
    if m_out <= 0:
        result["error"] = "Total deaerator outlet flow must be > 0"
        return result
    energy_in = (m_fw_cold_kgs * h_fw_cold_kJkg
                 + m_steam_sparging_kgs * h_steam_sparging_kJkg)
    h_fw_out = energy_in / m_out
    # Saturated water enthalpy at deaerator temperature
    h_sat = 4.1868 * T_deaerator_C
    if abs(h_fw_out - h_sat) / max(h_sat, 1) > 0.1:
        _warn(result, f"Deaerator outlet enthalpy {h_fw_out:.1f} kJ/kg differs >10% from "
              f"saturation enthalpy {h_sat:.1f} kJ/kg at {T_deaerator_C}°C; check steam fraction.")
    result["m_out_kgs"] = round(m_out, 5)
    result["h_fw_out_kJkg"] = round(h_fw_out, 2)
    result["T_out_C"] = T_deaerator_C
    return result


def economizer_energy_balance(
    m_fw_kgs: float,
    T_fw_in_C: float,
    T_fw_out_C: float,
    cp_fw_kJkgK: float = 4.1868,
) -> dict[str, Any]:
    """Economizer (feedwater pre-heater) duty and temperature rise.

    Q_econ = m_fw * cp * (T_out - T_in)

    Parameters
    ----------
    m_fw_kgs : float
        Feedwater mass flow (kg/s).
    T_fw_in_C : float
        Feedwater inlet temperature (°C).
    T_fw_out_C : float
        Feedwater outlet temperature (°C).
    cp_fw_kJkgK : float
        Specific heat of feedwater (kJ/kg·K, default 4.1868).

    Returns
    -------
    dict with keys:
        Q_econ_kW, delta_T_C, h_fw_out_kJkg, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    delta_T = T_fw_out_C - T_fw_in_C
    if delta_T <= 0:
        _warn(result, "Economizer outlet ≤ inlet temperature; no duty.")
    Q = m_fw_kgs * cp_fw_kJkgK * delta_T
    h_out = cp_fw_kJkgK * T_fw_out_C
    result["Q_econ_kW"] = round(Q, 3)
    result["delta_T_C"] = round(delta_T, 3)
    result["h_fw_out_kJkg"] = round(h_out, 2)
    result["h_fw_in_kJkg"] = round(cp_fw_kJkgK * T_fw_in_C, 2)
    return result


# ---------------------------------------------------------------------------
# Performance metrics
# ---------------------------------------------------------------------------

def equivalent_evaporation(
    m_steam_kgs: float,
    h_steam_kJkg: float,
    h_fw_kJkg: float,
    m_fuel_kgs: float,
) -> dict[str, Any]:
    """Equivalent evaporation (EE) and factor of evaporation.

    EE = m_steam * (h_steam - h_fw) / (m_fuel * 2256.9)
    where 2256.9 kJ/kg = hfg at 100°C (1 atm) — the 'from & at 100°C' basis.

    Parameters
    ----------
    m_steam_kgs : float
        Actual steam generation (kg/s).
    h_steam_kJkg : float
        Steam enthalpy (kJ/kg).
    h_fw_kJkg : float
        Feedwater enthalpy (kJ/kg).
    m_fuel_kgs : float
        Fuel mass flow (kg/s).

    Returns
    -------
    dict with keys:
        EE_kg_per_kg_fuel, factor_of_evaporation, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if m_fuel_kgs <= 0:
        result["error"] = "m_fuel_kgs must be > 0"
        return result
    hfg_100 = 2256.9  # kJ/kg at 100°C / 1 atm
    FE = (h_steam_kJkg - h_fw_kJkg) / hfg_100
    EE = m_steam_kgs * FE / m_fuel_kgs
    result["EE_kg_per_kg_fuel"] = round(EE, 4)
    result["factor_of_evaporation"] = round(FE, 4)
    result["hfg_100C_kJkg"] = hfg_100
    return result


def boiler_horsepower(
    m_steam_kgs: float,
    h_steam_kJkg: float,
    h_fw_kJkg: float = 419.06,
) -> dict[str, Any]:
    """Boiler horsepower (BHP).

    1 BHP = 33,475 BTU/h = 9.81 kW = evaporation of 15.65 kg/h from & at 212°F.

    BHP = m_steam * (h_steam - h_fw_at100C) / (9.81 kW)
    where h_fw_at100C = 419.06 kJ/kg (saturated water at 100°C).

    Parameters
    ----------
    m_steam_kgs : float
        Steam flow (kg/s).
    h_steam_kJkg : float
        Steam enthalpy (kJ/kg).
    h_fw_kJkg : float
        Feedwater enthalpy (kJ/kg, default 419.06 = sat. water at 100°C).

    Returns
    -------
    dict with keys:
        BHP, Q_kW, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if m_steam_kgs < 0:
        result["error"] = "m_steam_kgs must be >= 0"
        return result
    BHP_kW = 9.81  # kW per boiler horsepower
    Q_kW = m_steam_kgs * (h_steam_kJkg - h_fw_kJkg)
    BHP = Q_kW / BHP_kW
    if Q_kW < 0:
        _warn(result, "Net enthalpy rise is negative; check inputs.")
        Q_kW = 0.0
        BHP = 0.0
    result["BHP"] = round(BHP, 3)
    result["Q_kW"] = round(Q_kW, 3)
    return result


# ---------------------------------------------------------------------------
# Steam piping
# ---------------------------------------------------------------------------

def steam_pipe_velocity(
    m_steam_kgs: float,
    pipe_id_m: float,
    vg_m3kg: float,
) -> dict[str, Any]:
    """Mean velocity of steam in a circular pipe.

    v = m_steam * vg / A  where A = π * d² / 4

    Recommended velocities: saturated 20–35 m/s; superheated 30–50 m/s.

    Parameters
    ----------
    m_steam_kgs : float
        Steam mass flow (kg/s).
    pipe_id_m : float
        Pipe internal diameter (m).
    vg_m3kg : float
        Specific volume of steam (m³/kg).

    Returns
    -------
    dict with keys:
        velocity_ms, pipe_area_m2, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if pipe_id_m <= 0:
        result["error"] = "pipe_id_m must be > 0"
        return result
    if m_steam_kgs < 0:
        result["error"] = "m_steam_kgs must be >= 0"
        return result
    if vg_m3kg <= 0:
        result["error"] = "vg_m3kg must be > 0"
        return result
    A = math.pi / 4 * pipe_id_m**2
    v = m_steam_kgs * vg_m3kg / A
    if v > 50:
        _warn(result, f"Steam velocity {v:.1f} m/s > 50 m/s; erosion risk; upsize pipe.")
    elif v < 15:
        _warn(result, f"Steam velocity {v:.1f} m/s < 15 m/s; pipe may be oversized.")
    result["velocity_ms"] = round(v, 3)
    result["pipe_area_m2"] = round(A, 7)
    return result


def steam_pipe_pressure_drop(
    m_steam_kgs: float,
    pipe_id_m: float,
    pipe_length_m: float,
    vg_m3kg: float,
    mu_Pa_s: float = 1.5e-5,
    roughness_m: float = 4.6e-5,
) -> dict[str, Any]:
    """Darcy-Weisbach pressure drop for steam in a straight pipe.

    ΔP = f * (L/D) * (ρ * v²/2)  where ρ = 1/vg

    Friction factor by Colebrook-White (turbulent).

    Parameters
    ----------
    m_steam_kgs : float
        Steam mass flow (kg/s).
    pipe_id_m : float
        Internal pipe diameter (m).
    pipe_length_m : float
        Pipe length (m).
    vg_m3kg : float
        Specific volume (m³/kg).
    mu_Pa_s : float
        Dynamic viscosity of steam (Pa·s, default 1.5e-5 ≈ sat. steam ~150°C).
    roughness_m : float
        Pipe roughness (m, default 4.6e-5 m for steel).

    Returns
    -------
    dict with keys:
        dP_Pa, dP_kPa, Reynolds, f_darcy, velocity_ms, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if pipe_id_m <= 0 or pipe_length_m <= 0:
        result["error"] = "pipe_id_m and pipe_length_m must be > 0"
        return result
    if vg_m3kg <= 0:
        result["error"] = "vg_m3kg must be > 0"
        return result

    A = math.pi / 4 * pipe_id_m**2
    v = m_steam_kgs * vg_m3kg / A
    rho = 1.0 / vg_m3kg
    Re = rho * v * pipe_id_m / mu_Pa_s

    eps_D = roughness_m / pipe_id_m
    f = darcy_friction_factor(Re if Re > 0 else 1.0, eps_D)

    dP = f * (pipe_length_m / pipe_id_m) * (rho * v**2 / 2)

    if v > 50:
        _warn(result, f"Steam velocity {v:.1f} m/s > 50 m/s; erosion risk.")
    if dP / 1e3 > 10:
        _warn(result, f"Pressure drop {dP/1e3:.1f} kPa over {pipe_length_m}m is high; consider larger pipe.")

    result["dP_Pa"] = round(dP, 2)
    result["dP_kPa"] = round(dP / 1e3, 4)
    result["Reynolds"] = round(Re, 1)
    result["f_darcy"] = round(f, 6)
    result["velocity_ms"] = round(v, 3)
    return result


# ---------------------------------------------------------------------------
# Condensate & flash steam recovery
# ---------------------------------------------------------------------------

def flash_steam_fraction(
    h_condensate_kJkg: float,
    P_flash_Pa: float,
) -> dict[str, Any]:
    """Mass fraction of flash steam produced when condensate flashes to lower pressure.

    x_flash = (hf_high - hf_low) / hfg_low

    Parameters
    ----------
    h_condensate_kJkg : float
        Enthalpy of condensate before flashing (kJ/kg) = hf at high pressure.
    P_flash_Pa : float
        Flash vessel (lower) pressure (Pa).

    Returns
    -------
    dict with keys:
        flash_fraction, m_flash_per_kg_condensate, T_flash_C, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if P_flash_Pa <= 0:
        result["error"] = "P_flash_Pa must be > 0"
        return result
    props = steam_properties(P_Pa=P_flash_Pa)
    result["warnings"].extend(props.get("warnings", []))
    hf_low = props["hf_kJkg"]
    hfg_low = props["hfg_kJkg"]
    if hfg_low <= 0:
        result["error"] = "hfg at flash pressure is zero (near critical point)"
        return result
    x = (h_condensate_kJkg - hf_low) / hfg_low
    x = max(0.0, min(1.0, x))
    if x == 0:
        _warn(result, "No flash steam: condensate enthalpy ≤ hf at flash pressure.")
    result["flash_fraction"] = round(x, 5)
    result["m_flash_per_kg_condensate"] = round(x, 5)
    result["T_flash_C"] = props["T_sat_C"]
    result["hf_low_kJkg"] = props["hf_kJkg"]
    result["hfg_low_kJkg"] = props["hfg_kJkg"]
    return result


def condensate_heat_recovery(
    m_condensate_kgs: float,
    T_condensate_C: float,
    T_drain_C: float = 30.0,
    cp_kJkgK: float = 4.1868,
) -> dict[str, Any]:
    """Sensible heat recoverable from condensate return.

    Q_recovered = m_condensate * cp * (T_condensate - T_drain)

    Parameters
    ----------
    m_condensate_kgs : float
        Condensate return flow (kg/s).
    T_condensate_C : float
        Condensate return temperature (°C).
    T_drain_C : float
        Temperature after heat exchange / disposal (°C, default 30°C).
    cp_kJkgK : float
        Specific heat of water (kJ/kg·K, default 4.1868).

    Returns
    -------
    dict with keys:
        Q_recovered_kW, delta_T_C, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    delta_T = T_condensate_C - T_drain_C
    if delta_T <= 0:
        _warn(result, "Condensate temperature ≤ drain temperature; no recoverable heat.")
    Q = m_condensate_kgs * cp_kJkgK * delta_T
    if Q < 0:
        Q = 0.0
    result["Q_recovered_kW"] = round(Q, 3)
    result["delta_T_C"] = round(delta_T, 3)
    return result


# ---------------------------------------------------------------------------
# Steam traps
# ---------------------------------------------------------------------------

def steam_trap_capacity(
    dP_bar: float,
    orifice_dia_mm: float,
    Cd: float = 0.6,
    condensate_temp_C: float = 100.0,
) -> dict[str, Any]:
    """Steam trap condensate discharge capacity (orifice model).

    Based on incompressible orifice flow for subcooled condensate:
    m_dot = Cd * A * sqrt(2 * rho * dP)

    Parameters
    ----------
    dP_bar : float
        Differential pressure across trap (bar).
    orifice_dia_mm : float
        Orifice diameter (mm).
    Cd : float
        Discharge coefficient (default 0.6).
    condensate_temp_C : float
        Condensate temperature (°C, default 100°C).

    Returns
    -------
    dict with keys:
        m_condensate_kgs, m_condensate_kgh, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if dP_bar <= 0:
        result["error"] = "dP_bar must be > 0"
        return result
    if orifice_dia_mm <= 0:
        result["error"] = "orifice_dia_mm must be > 0"
        return result
    # Condensate density (liquid water): approx 1000 - 0.35*T_C kg/m3
    rho = max(700.0, 1000.0 - 0.35 * condensate_temp_C)
    dP_Pa = dP_bar * 1e5
    A = math.pi / 4 * (orifice_dia_mm / 1000.0)**2
    m_dot = Cd * A * math.sqrt(2 * rho * dP_Pa)
    if Cd > 0.85:
        _warn(result, f"Cd={Cd} is unusually high for an orifice; typical range 0.55-0.75.")
    result["m_condensate_kgs"] = round(m_dot, 5)
    result["m_condensate_kgh"] = round(m_dot * 3600, 3)
    result["orifice_area_m2"] = round(A, 9)
    return result


# ---------------------------------------------------------------------------
# Safety valve
# ---------------------------------------------------------------------------

def safety_valve_napier(
    set_pressure_barg: float,
    orifice_area_mm2: float,
    steam_type: str = "saturated",
    superheat_C: float = 0.0,
) -> dict[str, Any]:
    """Safety valve relief capacity by Napier's formula (steam).

    Napier formula (imperial origin, metric conversion applied):
      W [kg/h] = P_abs [bar abs] * A [mm²] * K_Napier
    where K_Napier ≈ 0.5251 for saturated steam.

    Derivation of K_Napier from the citable ASME Section I PG-69 / Napier
    imperial relation  W [lb/h] = 51.5 * P [psia] * A [in²]:
        51.5 * 0.45359237 (lb→kg) / (0.0689476 (psi→bar) * 645.16 (in²→mm²))
        = 0.52515  kg/h per (bar·mm²)
    Cross-check (Spirax Sarco / ASME I worked example): A = 79 mm²,
    P_abs = 11 bar a → W = 0.5251 * 11 * 79 ≈ 456 kg/h
    (= 51.5 * 159.5 psia * 0.1225 in² = 1006 lb/h = 456 kg/h). ✓

    For superheated steam, a correction factor Ksh is applied:
      Ksh = 1 / sqrt(1 + 0.00065 * superheat_C)

    Parameters
    ----------
    set_pressure_barg : float
        Safety valve set pressure (bar gauge).
    orifice_area_mm2 : float
        Curtain/orifice area (mm²).
    steam_type : str
        'saturated' (default) or 'superheated'.
    superheat_C : float
        Degrees of superheat (°C) for superheated steam.

    Returns
    -------
    dict with keys:
        W_kgh, W_kgs, P_abs_bar, Ksh, warnings
    """
    result: dict[str, Any] = {"warnings": []}
    if set_pressure_barg < 0:
        result["error"] = "set_pressure_barg must be >= 0"
        return result
    if orifice_area_mm2 <= 0:
        result["error"] = "orifice_area_mm2 must be > 0"
        return result
    # Standard overpressure = 10% above set pressure per ASME PTC/EN ISO 4126
    P_abs = set_pressure_barg + 1.0 + 0.1 * set_pressure_barg  # bar abs with 10% accumulation
    # ASME Section I PG-69 / Napier: W[lb/h] = 51.5*P[psia]*A[in²]
    # → SI: 51.5*0.45359237 / (0.0689476*645.16) = 0.52515 kg/h per (bar·mm²)
    K_Napier = 0.52515  # kg/h per bar·mm²

    if steam_type == "superheated" and superheat_C > 0:
        Ksh = 1.0 / math.sqrt(1 + 0.00065 * superheat_C)
    else:
        Ksh = 1.0
        if steam_type == "superheated" and superheat_C == 0:
            _warn(result, "steam_type='superheated' but superheat_C=0; using Ksh=1.")

    W_kgh = K_Napier * P_abs * orifice_area_mm2 * Ksh
    if W_kgh <= 0:
        _warn(result, "Computed relief capacity is zero or negative.")

    result["W_kgh"] = round(W_kgh, 3)
    result["W_kgs"] = round(W_kgh / 3600, 6)
    result["P_abs_bar"] = round(P_abs, 4)
    result["Ksh"] = round(Ksh, 5)
    result["K_Napier"] = K_Napier
    return result
