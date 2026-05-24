"""
kerf_cad_core.refrigeration.cycle — vapor-compression refrigeration & heat-pump design.

Distinct from:
  thermocycle/  — idealized gas/Rankine cycles (air-standard, steam)
  hvac/         — duct sizing, airside systems
  psychro/      — moist-air properties
  heatxfer/     — conduction, convection, radiation

Covers single-stage and multi-stage (cascade / two-stage flash/intercooler)
vapor-compression cycles for refrigerants R134a, R410A, R717 (ammonia),
R744 (CO₂), and R290 (propane).

Saturation properties are estimated via simplified Antoine / Clausius-Clapeyron
correlations fitted to published ASHRAE/NIST data for each refrigerant.

Impossible states are flagged via the standard library ``warnings`` module and
NEVER raise exceptions.

Units: SI throughout unless noted.
  Temperatures  — K (Kelvin) for all internal calculations; °C at API boundary
  Pressures     — Pa (absolute)
  Enthalpies    — J/kg
  Mass flow     — kg/s
  Capacity      — W (watts)  [convert from TR: 1 TR = 3516.85 W]
  Displacement  — m³/s
  COP           — dimensionless

References
----------
ASHRAE Fundamentals Handbook, 2021 edition.
Stoecker, W.F. & Jones, J.W., "Refrigeration and Air Conditioning", 2nd ed.
Cengel, Y.A. & Boles, M.A., "Thermodynamics: An Engineering Approach", 8th ed.
NIST WebBook saturation data (used to fit Antoine constants below).

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import Optional
from kerf_cad_core._guards import _err, _guard_nonneg


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TR_TO_W = 3516.853  # 1 ton of refrigeration = 3516.853 W
W_TO_TR = 1.0 / TR_TO_W

# Defrost energy fraction typical for low-temperature freezer coils
DEFROST_ENERGY_FRACTION_DEFAULT = 0.05  # 5% of daily evaporator duty


# ---------------------------------------------------------------------------
# Refrigerant saturation property tables (Antoine / Clausius-Clapeyron fits)
#
# Antoine equation form used:  ln(P_sat / kPa) = A - B / T
#   where T is in Kelvin, P_sat in kPa.
#
# The _sat_pressure() function converts to Pa by multiplying by 1000.
#
# Constants two-point fitted to NIST/ASHRAE saturation data:
#   R134a  : 0°C  292.80 kPa  /  40°C 1017.0 kPa  (NIST WebBook)
#   R410A  : 0°C  797.9 kPa   /  40°C 2419.0 kPa  (ASHRAE)
#   R717   : 0°C  429.44 kPa  /  40°C 1554.9 kPa  (NIST WebBook)
#   R744   : -20°C 1969.1 kPa /   0°C 3482.9 kPa  (NIST WebBook)
#   R290   : 0°C  473.9 kPa   /  40°C 1369.5 kPa  (NIST WebBook)
#
# Additional properties:
#   h_fg_ref  — latent heat of vaporisation at T_ref (J/kg)
#   T_ref     — reference temperature for h_fg (K)
#   cp_liq    — liquid specific heat at ~0°C (J/kg·K)
#   cp_vap    — vapour specific heat at ~0°C (J/kg·K)
#   M_mol     — molar mass (kg/kmol)
# ---------------------------------------------------------------------------

_REFRIGERANT_DATA: dict[str, dict] = {
    "R134a": {
        # 1,1,1,2-Tetrafluoroethane (HFC-134a)
        # Two-point fit: 0°C/292.80 kPa and 40°C/1017.0 kPa
        "A": 15.427,
        "B": 2662.6,
        "C": 0.0,   # C=0 → ln(P_kPa) = A - B/T
        "T_min_K": 220.0,
        "T_max_K": 374.0,   # near critical 374.21 K
        "h_fg_ref": 198_600.0,  # J/kg at 273.15 K (0°C)
        "T_ref": 273.15,
        "cp_liq": 1340.0,   # J/kg·K
        "cp_vap": 911.0,    # J/kg·K
        "M_mol": 102.03,
        "v_suc_ref": 0.0508,  # m³/kg suction-vapour specific volume at ~0°C evap
    },
    "R410A": {
        # Near-azeotropic mixture R32/R125 (50/50 wt%)
        # Two-point fit: 0°C/797.9 kPa and 40°C/2419.0 kPa
        "A": 15.365,
        "B": 2371.8,
        "C": 0.0,
        "T_min_K": 200.0,
        "T_max_K": 344.0,   # near critical ~344 K
        "h_fg_ref": 218_800.0,  # J/kg at 273.15 K
        "T_ref": 273.15,
        "cp_liq": 1680.0,
        "cp_vap": 1040.0,
        "M_mol": 72.58,
        "v_suc_ref": 0.0291,
    },
    "R717": {
        # Ammonia (NH₃)
        # Two-point fit: 0°C/429.44 kPa and 40°C/1554.9 kPa
        "A": 16.136,
        "B": 2751.5,
        "C": 0.0,
        "T_min_K": 200.0,
        "T_max_K": 405.0,   # near critical 405.56 K
        "h_fg_ref": 1262_000.0,  # J/kg at 273.15 K — very high
        "T_ref": 273.15,
        "cp_liq": 4610.0,
        "cp_vap": 2190.0,
        "M_mol": 17.03,
        "v_suc_ref": 0.2885,
    },
    "R744": {
        # Carbon dioxide (CO₂ / R-744)
        # Two-point fit: -20°C/1969.1 kPa and 0°C/3482.9 kPa
        # (subcritical range only; valid below critical 304.13 K)
        "A": 15.374,
        "B": 1971.7,
        "C": 0.0,
        "T_min_K": 220.0,
        "T_max_K": 304.0,   # critical 304.13 K
        "h_fg_ref": 231_000.0,  # J/kg at 253.15 K (−20°C)
        "T_ref": 253.15,
        "cp_liq": 2650.0,
        "cp_vap": 1300.0,
        "M_mol": 44.01,
        "v_suc_ref": 0.0238,
    },
    "R290": {
        # Propane (R-290, natural refrigerant)
        # Two-point fit: 0°C/473.9 kPa and 40°C/1369.5 kPa
        "A": 14.469,
        "B": 2269.3,
        "C": 0.0,
        "T_min_K": 180.0,
        "T_max_K": 369.8,   # critical 369.89 K
        "h_fg_ref": 436_900.0,  # J/kg at 273.15 K
        "T_ref": 273.15,
        "cp_liq": 2370.0,
        "cp_vap": 1630.0,
        "M_mol": 44.10,
        "v_suc_ref": 0.1946,
    },
}

SUPPORTED_REFRIGERANTS = list(_REFRIGERANT_DATA.keys())

# Case-folding map: lowercased/no-space variant → canonical key
_REFRIGERANT_CANONICAL: dict[str, str] = {
    k.lower().replace("-", "").replace(" ", ""): k
    for k in _REFRIGERANT_DATA
}


def _resolve_refrigerant(name: str) -> str | None:
    """Return canonical refrigerant key for name, or None if unknown.

    Accepts case-insensitive names: 'r134a', 'R134A', 'R134a' all → 'R134a'.
    """
    key = str(name).strip().lower().replace("-", "").replace(" ", "")
    return _REFRIGERANT_CANONICAL.get(key)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ok(**kwargs) -> dict:
    return {"ok": True, **kwargs}


def _warn(msg: str) -> None:
    warnings.warn(msg, UserWarning, stacklevel=4)


def _guard_pos(name: str, val) -> Optional[str]:
    """Return error string if val is not a finite positive number."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {val!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


def _sat_pressure(T_K: float, ref: dict) -> float:
    """Return saturation pressure (Pa) at temperature T_K using Antoine eq.

    Antoine form: ln(P_kPa) = A - B / (T_K + C)
    Multiply by 1000 to return Pa.
    """
    ln_p_kPa = ref["A"] - ref["B"] / (T_K + ref["C"])
    return math.exp(ln_p_kPa) * 1000.0   # kPa → Pa


def _sat_temperature(P_Pa: float, ref: dict) -> float:
    """Return saturation temperature (K) at pressure P_Pa (inverse Antoine).

    Inverse: T_K = B / (A - ln(P_kPa)) - C
    """
    P_kPa = P_Pa / 1000.0
    ln_p_kPa = math.log(P_kPa)
    return ref["B"] / (ref["A"] - ln_p_kPa) - ref["C"]


def _h_fg(T_K: float, ref: dict) -> float:
    """
    Approximate latent heat of vaporisation at T_K (J/kg).

    Uses simplified Clausius-Clapeyron scaling:
        h_fg(T) ≈ h_fg_ref × (T_c - T) / (T_c - T_ref)
    where T_c is estimated from the max temperature in the Antoine range.
    Linear interpolation is adequate for engineering calculations within
    ±40 K of reference conditions.
    """
    T_c = ref["T_max_K"]
    T_ref = ref["T_ref"]
    h_fg_ref = ref["h_fg_ref"]
    if T_c <= T_ref:
        return h_fg_ref
    ratio = max(0.0, (T_c - T_K) / (T_c - T_ref))
    return h_fg_ref * ratio


def _cp_liq(ref: dict) -> float:
    return ref["cp_liq"]


def _cp_vap(ref: dict) -> float:
    return ref["cp_vap"]


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

def _C_to_K(T_C: float) -> float:
    return T_C + 273.15


def _K_to_C(T_K: float) -> float:
    return T_K - 273.15


# ---------------------------------------------------------------------------
# 1. saturation_pressure — saturation pressure at a given temperature
# ---------------------------------------------------------------------------

def saturation_pressure(
    T_C: float,
    refrigerant: str = "R134a",
) -> dict:
    """
    Saturation pressure at temperature T_C (°C) for the given refrigerant.

    Parameters
    ----------
    T_C         : float — saturation temperature (°C)
    refrigerant : str  — one of R134a, R410A, R717, R744, R290

    Returns
    -------
    dict with ok=True, P_sat_Pa, T_K, refrigerant
    """
    ref_key = _resolve_refrigerant(refrigerant)
    if ref_key is None:
        return _err(f"Unknown refrigerant {refrigerant!r}. Supported: {SUPPORTED_REFRIGERANTS}.")
    ref = _REFRIGERANT_DATA[ref_key]

    # Temperature can be negative, so just check finiteness
    try:
        T_C_f = float(T_C)
    except (TypeError, ValueError):
        return _err(f"T_C must be a number, got {T_C!r}")
    if not math.isfinite(T_C_f):
        return _err(f"T_C must be finite, got {T_C_f}")

    T_K = _C_to_K(T_C_f)
    if T_K <= 0:
        return _err("T_C results in T_K <= 0; unphysical.")
    if T_K > ref["T_max_K"]:
        _warn(
            f"{ref_key}: T_C={T_C_f:.1f}°C (T_K={T_K:.1f}) exceeds Antoine "
            f"validity limit {ref['T_max_K']} K (near-critical region). "
            f"Result is extrapolated."
        )
    if T_K < ref["T_min_K"]:
        _warn(
            f"{ref_key}: T_C={T_C_f:.1f}°C (T_K={T_K:.1f}) is below Antoine "
            f"validity limit {ref['T_min_K']} K. Result is extrapolated."
        )

    P_sat = _sat_pressure(T_K, ref)
    return _ok(P_sat_Pa=P_sat, T_C=T_C_f, T_K=T_K, refrigerant=ref_key)


# ---------------------------------------------------------------------------
# 2. single_stage_cycle — main single-stage vapor-compression cycle analysis
# ---------------------------------------------------------------------------

def single_stage_cycle(
    T_evap_C: float,
    T_cond_C: float,
    capacity_W: float,
    refrigerant: str = "R134a",
    *,
    eta_isentropic: float = 0.75,
    superheat_K: float = 5.0,
    subcool_K: float = 3.0,
    eta_volumetric: float = 0.85,
) -> dict:
    """
    Single-stage vapor-compression refrigeration cycle analysis.

    Implements a standard vapor-compression cycle:
      1→2s isentropic compression (compressor)
      2→3  condensation at constant pressure
      3→4  isenthalpic expansion (expansion valve)
      4→1  evaporation at constant pressure

    Saturation pressures are derived from temperatures using per-refrigerant
    Antoine/Clausius-Clapeyron correlations. Compressor work uses the
    isentropic efficiency model.

    Parameters
    ----------
    T_evap_C       : float — evaporator saturation temperature (°C)
    T_cond_C       : float — condenser saturation temperature (°C)
    capacity_W     : float — refrigerating capacity Q_L (W); must be > 0
    refrigerant    : str   — R134a | R410A | R717 | R744 | R290
    eta_isentropic : float — compressor isentropic efficiency (default 0.75)
    superheat_K    : float — superheat at compressor suction (K, default 5)
    subcool_K      : float — subcooling at condenser outlet (K, default 3)
    eta_volumetric : float — volumetric efficiency for displacement (default 0.85)

    Returns
    -------
    dict with ok=True and the following fields:
      refrigerant         — refrigerant name
      T_evap_C            — evaporator sat. temp (°C)
      T_cond_C            — condenser sat. temp (°C)
      P_evap_Pa           — evaporator pressure (Pa)
      P_cond_Pa           — condenser pressure (Pa)
      pressure_ratio      — P_cond / P_evap
      h_fg_evap           — latent heat at evaporator (J/kg)
      h_fg_cond           — latent heat at condenser (J/kg)
      superheat_K         — suction superheat (K)
      subcool_K           — liquid subcooling (K)
      refrigerating_effect — specific refrigerating effect (J/kg)
      w_compressor_ideal  — ideal (isentropic) specific compressor work (J/kg)
      w_compressor_real   — actual specific compressor work (J/kg)
      COP_cooling         — refrigeration COP = Q_L / W_compressor
      COP_heating         — heat-pump COP = Q_H / W_compressor (= COP_cooling + 1)
      mass_flow_kg_s      — refrigerant mass flow rate (kg/s)
      Q_evap_W            — evaporator duty = capacity_W (W)
      Q_cond_W            — condenser duty (W)
      W_compressor_W      — compressor power input (W)
      volumetric_flow_m3s — suction volumetric flow (m³/s)
      compressor_displacement_m3s — swept volume flow at eta_vol (m³/s)
      discharge_temp_est_C — estimated discharge temperature (°C)
      warnings            — list of warning strings (empty if none)
    """
    # --- Validate inputs ---
    ref_key = _resolve_refrigerant(refrigerant)
    if ref_key is None:
        return _err(f"Unknown refrigerant {refrigerant!r}. Supported: {SUPPORTED_REFRIGERANTS}.")
    ref = _REFRIGERANT_DATA[ref_key]

    for name, val in [("T_evap_C", T_evap_C), ("T_cond_C", T_cond_C)]:
        try:
            float(val)
        except (TypeError, ValueError):
            return _err(f"{name} must be a number, got {val!r}")
        if not math.isfinite(float(val)):
            return _err(f"{name} must be finite")

    e = _guard_pos("capacity_W", capacity_W)
    if e:
        return _err(e)
    e = _guard_pos("eta_isentropic", eta_isentropic)
    if e:
        return _err(e)
    e = _guard_nonneg("superheat_K", superheat_K)
    if e:
        return _err(e)
    e = _guard_nonneg("subcool_K", subcool_K)
    if e:
        return _err(e)
    e = _guard_pos("eta_volumetric", eta_volumetric)
    if e:
        return _err(e)

    T_evap_C_f = float(T_evap_C)
    T_cond_C_f = float(T_cond_C)

    if T_evap_C_f >= T_cond_C_f:
        return _err(
            f"T_evap_C ({T_evap_C_f}°C) must be less than T_cond_C ({T_cond_C_f}°C)."
        )

    T_evap_K = _C_to_K(T_evap_C_f)
    T_cond_K = _C_to_K(T_cond_C_f)
    cap = float(capacity_W)
    eta_s = float(eta_isentropic)
    dT_sh = float(superheat_K)
    dT_sc = float(subcool_K)
    eta_v = float(eta_volumetric)

    warn_list: list[str] = []

    # --- Saturation pressures ---
    P_evap = _sat_pressure(T_evap_K, ref)
    P_cond = _sat_pressure(T_cond_K, ref)
    pressure_ratio = P_cond / P_evap

    # --- Latent heats ---
    h_fg_e = _h_fg(T_evap_K, ref)
    h_fg_c = _h_fg(T_cond_K, ref)

    # --- Refrigerating effect (per kg of refrigerant) ---
    # State 1: superheated vapour leaving evaporator
    #   h1 = h_g_evap + cp_vap × superheat
    # State 3: subcooled liquid leaving condenser
    #   h3 = h_f_cond - cp_liq × subcool
    # Expansion (4): isenthalpic → h4 = h3
    # Refrigerating effect = h1 - h4
    cp_v = _cp_vap(ref)
    cp_l = _cp_liq(ref)

    # Reference: specific enthalpy of saturated vapour at evap ≈ h_fg_evap
    # (absolute values cancel out; we work with differences)
    # h1 - h4 = (h_g_evap + cp_v·dT_sh) - (h_f_cond - cp_l·dT_sc)
    #         = h_fg_evap + cp_v·dT_sh - 0 - h_fg_cond + h_fg_cond - cp_l·dT_sc
    # Since h_f = 0 reference → h_g = h_fg, h4 = h_f_cond - cp_l·dT_sc:
    # We track differences from h_f_evap = 0 (arbitrary reference at evap sat liquid).
    h_g_evap = h_fg_e            # J/kg (sat. vapour at evap = h_fg + h_f, ref h_f=0)
    h1 = h_g_evap + cp_v * dT_sh  # superheated suction

    # h_f_cond relative to evap reference requires enthalpy lift calculation.
    # Use a consistent scheme: set h_f_evap = 0, then
    #   h_f_cond = cp_l × (T_cond_K - T_evap_K)   (sensible liquid enthalpy rise)
    h_f_cond = cp_l * (T_cond_K - T_evap_K)
    h3 = h_f_cond - cp_l * dT_sc   # subcooled liquid
    h4 = h3                          # isenthalpic expansion

    refrig_effect = h1 - h4
    if refrig_effect <= 0:
        return _err(
            f"Refrigerating effect is non-positive ({refrig_effect:.1f} J/kg). "
            f"Check T_evap_C, T_cond_C, subcool_K, superheat_K."
        )

    # --- Isentropic compressor work ---
    # Ideal: h2s - h1 using Clausius-Clapeyron / simplified polytropic relation
    # For vapour compression cycles, approximate isentropic work via:
    #   w_s = h_fg_evap × (T_cond_K - T_evap_K) / T_evap_K   (Clausius-Clapeyron)
    # This is equivalent to: Δh_s ≈ T·Δs_vap × (pressure ratio - 1)
    # A commonly used approximation for belt-drive estimate:
    #   w_ideal ≈ cp_vap × T_evap_K × ((P_cond/P_evap)^((k-1)/k) - 1)
    # We use the enthalpy-based Clausius-Clapeyron form as primary:
    w_ideal = h_fg_e * (T_cond_K - T_evap_K) / T_evap_K

    # Real compressor work (accounting for isentropic efficiency)
    w_real = w_ideal / eta_s

    # --- COP ---
    COP_cooling = refrig_effect / w_real
    COP_heating = COP_cooling + 1.0  # Q_H / W = (Q_L + W) / W = COP + 1

    # --- Mass flow rate ---
    m_dot = cap / refrig_effect       # kg/s

    # --- Condenser and evaporator duty ---
    Q_evap = cap
    Q_cond = m_dot * (refrig_effect + w_real)  # Q_H = Q_L + W
    W_comp = m_dot * w_real

    # --- Volumetric flow ---
    # Suction specific volume: ideal gas approx at evap conditions
    # v_suc ≈ R_gas × T1 / P_evap
    # Use stored reference specific volume scaled by T and P
    v_suc_ref = ref["v_suc_ref"]
    T_suc = T_evap_K + dT_sh
    P_evap_ref = _sat_pressure(_C_to_K(0.0), ref)   # ref at 0°C
    T_suc_ref = _C_to_K(0.0) + 5.0                   # ref superheat 5 K
    v_suc = v_suc_ref * (T_suc / T_suc_ref) * (P_evap_ref / P_evap)  # ideal gas scaling

    vol_flow = m_dot * v_suc
    displacement = vol_flow / eta_v

    # --- Discharge temperature estimate ---
    # T_dis ≈ T_suc × (P_cond/P_evap)^((k-1)/k)
    # Use k = cp_vap / (cp_vap - R_gas), approximate R_gas from M_mol
    R_gas = 8314.0 / ref["M_mol"]     # J/kg·K
    k_vap = cp_v / (cp_v - R_gas) if cp_v > R_gas else 1.25
    k_vap = max(1.05, min(k_vap, 1.5))
    T_dis_K = T_suc * (pressure_ratio ** ((k_vap - 1.0) / k_vap))
    T_dis_C = _K_to_C(T_dis_K)

    # --- Warnings ---
    if COP_cooling < 1.5:
        msg = (
            f"Low COP: COP_cooling={COP_cooling:.2f}. "
            f"Consider higher evaporator temperature or lower condenser temperature."
        )
        _warn(msg)
        warn_list.append(msg)

    if pressure_ratio > 10.0:
        msg = (
            f"Excessive pressure ratio: {pressure_ratio:.1f} (> 10). "
            f"Consider two-stage or cascade cycle."
        )
        _warn(msg)
        warn_list.append(msg)

    if T_dis_C > 130.0:
        msg = (
            f"High discharge temperature estimate: {T_dis_C:.1f}°C (> 130°C). "
            f"Risk of oil degradation; check superheat and pressure ratio."
        )
        _warn(msg)
        warn_list.append(msg)

    if dT_sh < 3.0:
        msg = (
            f"Superheat={dT_sh:.1f} K < 3 K: risk of liquid floodback to compressor."
        )
        _warn(msg)
        warn_list.append(msg)

    if eta_isentropic > 0.95:
        msg = (
            f"eta_isentropic={eta_isentropic:.2f} > 0.95 is unrealistically high "
            f"for a typical vapour-compression compressor."
        )
        _warn(msg)
        warn_list.append(msg)

    return _ok(
        refrigerant=ref_key,
        T_evap_C=T_evap_C_f,
        T_cond_C=T_cond_C_f,
        P_evap_Pa=P_evap,
        P_cond_Pa=P_cond,
        pressure_ratio=pressure_ratio,
        h_fg_evap=h_fg_e,
        h_fg_cond=h_fg_c,
        superheat_K=dT_sh,
        subcool_K=dT_sc,
        refrigerating_effect=refrig_effect,
        w_compressor_ideal=w_ideal,
        w_compressor_real=w_real,
        COP_cooling=COP_cooling,
        COP_heating=COP_heating,
        mass_flow_kg_s=m_dot,
        Q_evap_W=Q_evap,
        Q_cond_W=Q_cond,
        W_compressor_W=W_comp,
        volumetric_flow_m3s=vol_flow,
        compressor_displacement_m3s=displacement,
        discharge_temp_est_C=T_dis_C,
        capacity_TR=cap * W_TO_TR,
        warnings=warn_list,
    )


# ---------------------------------------------------------------------------
# 3. tons_of_refrigeration — convert cooling load to tons of refrigeration
# ---------------------------------------------------------------------------

def tons_of_refrigeration(
    capacity_W: float = 0.0,
    capacity_TR: float = 0.0,
    capacity_kW: float = 0.0,
    capacity_BTUh: float = 0.0,
) -> dict:
    """
    Convert cooling capacity between common units:
      W (watts), kW, TR (tons of refrigeration), BTU/h.

    Provide exactly one non-zero input (others default to 0).
    1 TR = 3516.853 W = 3.516853 kW = 12,000 BTU/h.

    Returns all four unit values in a dict with ok=True.
    """
    # Determine which input is provided
    inputs = {
        "capacity_W": float(capacity_W),
        "capacity_TR": float(capacity_TR),
        "capacity_kW": float(capacity_kW),
        "capacity_BTUh": float(capacity_BTUh),
    }
    nonzero = [(k, v) for k, v in inputs.items() if v != 0.0]
    if not nonzero:
        return _err("Provide at least one non-zero capacity input.")

    # Convert everything to Watts from the first non-zero input
    k0, v0 = nonzero[0]
    if k0 == "capacity_W":
        W = v0
    elif k0 == "capacity_TR":
        W = v0 * TR_TO_W
    elif k0 == "capacity_kW":
        W = v0 * 1000.0
    elif k0 == "capacity_BTUh":
        W = v0 / 3.41214  # 1 W = 3.41214 BTU/h
    else:
        return _err(f"Unexpected input key: {k0}")

    if W <= 0:
        return _err(f"Capacity must be > 0, got {W:.3f} W.")

    return _ok(
        capacity_W=W,
        capacity_kW=W / 1000.0,
        capacity_TR=W * W_TO_TR,
        capacity_BTUh=W * 3.41214,
    )


# ---------------------------------------------------------------------------
# 4. compressor_sizing — mass flow, volumetric flow, displacement from capacity
# ---------------------------------------------------------------------------

def compressor_sizing(
    capacity_W: float,
    T_evap_C: float,
    T_cond_C: float,
    refrigerant: str = "R134a",
    *,
    eta_isentropic: float = 0.75,
    superheat_K: float = 5.0,
    subcool_K: float = 3.0,
    eta_volumetric: float = 0.85,
) -> dict:
    """
    Convenience wrapper: derives compressor sizing quantities from cycle analysis.

    Returns a subset of single_stage_cycle output focused on compressor sizing:
      mass_flow_kg_s, volumetric_flow_m3s, compressor_displacement_m3s,
      W_compressor_W, pressure_ratio, discharge_temp_est_C, COP_cooling.
    """
    result = single_stage_cycle(
        T_evap_C, T_cond_C, capacity_W, refrigerant,
        eta_isentropic=eta_isentropic,
        superheat_K=superheat_K,
        subcool_K=subcool_K,
        eta_volumetric=eta_volumetric,
    )
    if not result.get("ok"):
        return result

    return _ok(
        refrigerant=result["refrigerant"],
        capacity_W=capacity_W,
        capacity_TR=result["capacity_TR"],
        mass_flow_kg_s=result["mass_flow_kg_s"],
        volumetric_flow_m3s=result["volumetric_flow_m3s"],
        compressor_displacement_m3s=result["compressor_displacement_m3s"],
        W_compressor_W=result["W_compressor_W"],
        pressure_ratio=result["pressure_ratio"],
        discharge_temp_est_C=result["discharge_temp_est_C"],
        COP_cooling=result["COP_cooling"],
        warnings=result["warnings"],
    )


# ---------------------------------------------------------------------------
# 5. superheat_subcool_effect — effect of superheat & subcooling on cycle
# ---------------------------------------------------------------------------

def superheat_subcool_effect(
    T_evap_C: float,
    T_cond_C: float,
    capacity_W: float,
    refrigerant: str = "R134a",
    *,
    superheat_K: float = 5.0,
    subcool_K: float = 3.0,
) -> dict:
    """
    Quantify the effect of suction superheat and liquid subcooling on cycle COP.

    Compares the cycle with given superheat/subcool against the saturated cycle
    (superheat=0, subcool=0) to show the improvement from superheating and
    subcooling.

    Returns base and modified COP, refrigerating effect, and percentage changes.
    """
    base = single_stage_cycle(
        T_evap_C, T_cond_C, capacity_W, refrigerant,
        superheat_K=0.0, subcool_K=0.0,
    )
    if not base.get("ok"):
        return base

    modified = single_stage_cycle(
        T_evap_C, T_cond_C, capacity_W, refrigerant,
        superheat_K=superheat_K, subcool_K=subcool_K,
    )
    if not modified.get("ok"):
        return modified

    d_cop = modified["COP_cooling"] - base["COP_cooling"]
    d_re = modified["refrigerating_effect"] - base["refrigerating_effect"]

    return _ok(
        refrigerant=modified["refrigerant"],
        T_evap_C=T_evap_C,
        T_cond_C=T_cond_C,
        superheat_K=superheat_K,
        subcool_K=subcool_K,
        COP_base=base["COP_cooling"],
        COP_modified=modified["COP_cooling"],
        COP_change=d_cop,
        COP_change_pct=100.0 * d_cop / base["COP_cooling"] if base["COP_cooling"] else 0.0,
        refrig_effect_base=base["refrigerating_effect"],
        refrig_effect_modified=modified["refrigerating_effect"],
        refrig_effect_change=d_re,
    )


# ---------------------------------------------------------------------------
# 6. two_stage_cycle — two-stage compression with flash intercooler
# ---------------------------------------------------------------------------

def two_stage_cycle(
    T_evap_C: float,
    T_cond_C: float,
    capacity_W: float,
    refrigerant: str = "R134a",
    *,
    eta_isentropic: float = 0.75,
    superheat_K: float = 5.0,
    subcool_K: float = 3.0,
    eta_volumetric: float = 0.85,
    T_interstage_C: Optional[float] = None,
) -> dict:
    """
    Two-stage vapor-compression cycle with flash intercooler.

    The interstage temperature is typically chosen as the geometric mean of
    evap and cond saturation temperatures:
        T_int ≈ √(T_evap_K × T_cond_K) - 273.15  (°C)

    Each stage is modelled as a single-stage cycle. The overall COP accounts
    for both compressor stages.

    Parameters
    ----------
    T_evap_C         : float — evaporator sat. temp (°C)
    T_cond_C         : float — condenser sat. temp (°C)
    capacity_W       : float — total refrigerating capacity (W)
    refrigerant      : str
    eta_isentropic   : float — per-stage compressor isentropic efficiency
    superheat_K      : float — suction superheat for low stage (K)
    subcool_K        : float — condenser liquid subcooling (K)
    eta_volumetric   : float — per-stage volumetric efficiency
    T_interstage_C   : float | None — interstage temp (°C); geometric mean if None

    Returns
    -------
    dict with ok=True:
      T_interstage_C, P_interstage_Pa,
      COP_cooling_two_stage, COP_heating_two_stage,
      W_total_W, Q_evap_W, Q_cond_W,
      pressure_ratio_low, pressure_ratio_high,
      mass_flow_low_kg_s, mass_flow_high_kg_s, warnings
    """
    ref_key = _resolve_refrigerant(refrigerant)
    if ref_key is None:
        return _err(f"Unknown refrigerant {refrigerant!r}. Supported: {SUPPORTED_REFRIGERANTS}.")
    ref = _REFRIGERANT_DATA[ref_key]

    for name, val in [("T_evap_C", T_evap_C), ("T_cond_C", T_cond_C)]:
        try:
            float(val)
        except (TypeError, ValueError):
            return _err(f"{name} must be a number")
        if not math.isfinite(float(val)):
            return _err(f"{name} must be finite")

    e = _guard_pos("capacity_W", capacity_W)
    if e:
        return _err(e)

    T_evap_K = _C_to_K(float(T_evap_C))
    T_cond_K = _C_to_K(float(T_cond_C))

    if T_evap_K >= T_cond_K:
        return _err("T_evap_C must be less than T_cond_C.")

    # Interstage temperature — geometric mean of saturation temperatures
    if T_interstage_C is None:
        T_int_K = math.sqrt(T_evap_K * T_cond_K)
        T_int_C = _K_to_C(T_int_K)
    else:
        T_int_C = float(T_interstage_C)
        T_int_K = _C_to_K(T_int_C)

    if T_int_K <= T_evap_K or T_int_K >= T_cond_K:
        return _err(
            f"T_interstage_C={T_int_C:.1f}°C must be between "
            f"T_evap_C={T_evap_C}°C and T_cond_C={T_cond_C}°C."
        )

    P_int = _sat_pressure(T_int_K, ref)

    warn_list: list[str] = []

    # Low-stage: evap → interstage
    low = single_stage_cycle(
        float(T_evap_C), T_int_C, float(capacity_W), ref_key,
        eta_isentropic=eta_isentropic,
        superheat_K=superheat_K,
        subcool_K=0.0,     # flash intercooler saturates the liquid
        eta_volumetric=eta_volumetric,
    )
    if not low.get("ok"):
        return _err(f"Low stage failed: {low.get('reason')}")

    # High-stage: interstage → condenser
    # Flash intercooler means additional refrigerant from flash at interstage;
    # high-stage handles flash vapour plus low-stage discharge.
    # Simplified: assume flash fraction x_fl and high-stage mass flow scales.
    h_fg_int = _h_fg(T_int_K, ref)
    cp_l_ref = _cp_liq(ref)
    # Flash fraction at interstage
    # Liquid enthalpy difference from cond to interstage
    h_f_cond = cp_l_ref * (T_cond_K - T_evap_K)
    h_f_int = cp_l_ref * (T_int_K - T_evap_K)
    h4_flash = h_f_cond - cp_l_ref * float(subcool_K)
    h_g_int = h_fg_int + h_f_int   # sat. vapour enthalpy at interstage

    # Flash fraction: x = (h4_flash - h_f_int) / h_fg_int if h4_flash > h_f_int else 0
    if h_fg_int > 0:
        x_flash = max(0.0, min(1.0, (h4_flash - h_f_int) / h_fg_int))
    else:
        x_flash = 0.0

    m_low = low["mass_flow_kg_s"]
    # High-stage mass flow accounts for flash vapour
    m_high = m_low / max(1e-9, 1.0 - x_flash) if x_flash < 1.0 else m_low * 1.5

    high = single_stage_cycle(
        T_int_C, float(T_cond_C),
        m_high * low["refrigerating_effect"],   # high-stage capacity estimate
        ref_key,
        eta_isentropic=eta_isentropic,
        superheat_K=0.0,   # flash intercooler provides saturated suction
        subcool_K=float(subcool_K),
        eta_volumetric=eta_volumetric,
    )
    if not high.get("ok"):
        return _err(f"High stage failed: {high.get('reason')}")

    W_total = low["W_compressor_W"] + high["W_compressor_W"]
    Q_evap = float(capacity_W)
    Q_cond = Q_evap + W_total
    COP_cool = Q_evap / W_total if W_total > 0 else 0.0
    COP_heat = (Q_evap + W_total) / W_total if W_total > 0 else 0.0

    if low["warnings"]:
        warn_list.extend([f"[low-stage] {w}" for w in low["warnings"]])
    if high["warnings"]:
        warn_list.extend([f"[high-stage] {w}" for w in high["warnings"]])

    return _ok(
        refrigerant=ref_key,
        T_evap_C=float(T_evap_C),
        T_cond_C=float(T_cond_C),
        T_interstage_C=T_int_C,
        P_evap_Pa=low["P_evap_Pa"],
        P_interstage_Pa=P_int,
        P_cond_Pa=high["P_cond_Pa"],
        pressure_ratio_low=low["pressure_ratio"],
        pressure_ratio_high=high["pressure_ratio"],
        pressure_ratio_overall=high["P_cond_Pa"] / low["P_evap_Pa"],
        flash_fraction=x_flash,
        mass_flow_low_kg_s=m_low,
        mass_flow_high_kg_s=m_high,
        W_low_stage_W=low["W_compressor_W"],
        W_high_stage_W=high["W_compressor_W"],
        W_total_W=W_total,
        Q_evap_W=Q_evap,
        Q_cond_W=Q_cond,
        COP_cooling_two_stage=COP_cool,
        COP_heating_two_stage=COP_heat,
        warnings=warn_list,
    )


# ---------------------------------------------------------------------------
# 7. cascade_cycle — two-refrigerant cascade cycle
# ---------------------------------------------------------------------------

def cascade_cycle(
    T_evap_C: float,
    T_cond_C: float,
    capacity_W: float,
    refrigerant_low: str = "R744",
    refrigerant_high: str = "R134a",
    *,
    eta_isentropic: float = 0.75,
    T_cascade_C: Optional[float] = None,
    superheat_K: float = 5.0,
    subcool_K: float = 3.0,
    cascade_approach_K: float = 5.0,
) -> dict:
    """
    Two-stage cascade vapor-compression cycle.

    Two separate refrigerant circuits share a cascade heat exchanger.
    The low-temperature circuit (refrigerant_low) rejects heat to the
    cascade heat exchanger, which acts as the condenser for the low circuit
    and the evaporator for the high circuit.

    Best suited for very low temperatures (below −40°C) where a single-stage
    cycle would have an impractically high pressure ratio.

    Parameters
    ----------
    T_evap_C         : float — low-circuit evaporator temperature (°C)
    T_cond_C         : float — high-circuit condenser temperature (°C)
    capacity_W       : float — total refrigerating capacity (W)
    refrigerant_low  : str   — low-circuit refrigerant (default R744 for deep freeze)
    refrigerant_high : str   — high-circuit refrigerant (default R134a)
    eta_isentropic   : float — compressor isentropic efficiency (both circuits)
    T_cascade_C      : float | None — cascade HX temperature (°C); geometric mean if None
    superheat_K      : float — suction superheat (K)
    subcool_K        : float — liquid subcooling (K)
    cascade_approach_K : float — temperature approach in cascade HX (K)

    Returns
    -------
    dict with ok=True and cascade cycle performance metrics.
    """
    ref_lo_key = _resolve_refrigerant(refrigerant_low)
    ref_hi_key = _resolve_refrigerant(refrigerant_high)

    for orig, resolved in [(refrigerant_low, ref_lo_key), (refrigerant_high, ref_hi_key)]:
        if resolved is None:
            return _err(f"Unknown refrigerant {orig!r}. Supported: {SUPPORTED_REFRIGERANTS}.")

    for name, val in [("T_evap_C", T_evap_C), ("T_cond_C", T_cond_C)]:
        try:
            float(val)
        except (TypeError, ValueError):
            return _err(f"{name} must be a number")
        if not math.isfinite(float(val)):
            return _err(f"{name} must be finite")

    e = _guard_pos("capacity_W", capacity_W)
    if e:
        return _err(e)
    e = _guard_pos("cascade_approach_K", cascade_approach_K)
    if e:
        return _err(e)

    T_evap_K = _C_to_K(float(T_evap_C))
    T_cond_K = _C_to_K(float(T_cond_C))

    if T_evap_K >= T_cond_K:
        return _err("T_evap_C must be less than T_cond_C.")

    # Cascade temperature
    if T_cascade_C is None:
        T_cas_K = math.sqrt(T_evap_K * T_cond_K)
        T_cas_C = _K_to_C(T_cas_K)
    else:
        T_cas_C = float(T_cascade_C)
        T_cas_K = _C_to_K(T_cas_C)

    if T_cas_K <= T_evap_K or T_cas_K >= T_cond_K:
        return _err(
            f"T_cascade_C={T_cas_C:.1f}°C must be between "
            f"T_evap_C={T_evap_C}°C and T_cond_C={T_cond_C}°C."
        )

    # Low circuit condenser = cascade HX (low side)
    T_lo_cond_C = T_cas_C
    # High circuit evaporator = cascade HX (high side) with approach
    T_hi_evap_C = T_cas_C - float(cascade_approach_K)

    warn_list: list[str] = []

    # Analyse low circuit
    low_c = single_stage_cycle(
        float(T_evap_C), T_lo_cond_C, float(capacity_W), ref_lo_key,
        eta_isentropic=eta_isentropic,
        superheat_K=superheat_K,
        subcool_K=subcool_K,
    )
    if not low_c.get("ok"):
        return _err(f"Low circuit failed: {low_c.get('reason')}")

    # High circuit capacity = low circuit condenser duty (heat rejected into cascade HX)
    Q_cascade = low_c["Q_cond_W"]

    high_c = single_stage_cycle(
        T_hi_evap_C, float(T_cond_C), Q_cascade, ref_hi_key,
        eta_isentropic=eta_isentropic,
        superheat_K=superheat_K,
        subcool_K=subcool_K,
    )
    if not high_c.get("ok"):
        return _err(f"High circuit failed: {high_c.get('reason')}")

    W_total = low_c["W_compressor_W"] + high_c["W_compressor_W"]
    Q_evap = float(capacity_W)
    Q_cond = Q_evap + W_total
    COP_cool = Q_evap / W_total if W_total > 0 else 0.0

    if low_c["warnings"]:
        warn_list.extend([f"[low-circuit] {w}" for w in low_c["warnings"]])
    if high_c["warnings"]:
        warn_list.extend([f"[high-circuit] {w}" for w in high_c["warnings"]])

    return _ok(
        refrigerant_low=ref_lo_key,
        refrigerant_high=ref_hi_key,
        T_evap_C=float(T_evap_C),
        T_cond_C=float(T_cond_C),
        T_cascade_C=T_cas_C,
        T_hi_evap_C=T_hi_evap_C,
        P_evap_low_Pa=low_c["P_evap_Pa"],
        P_cond_low_Pa=low_c["P_cond_Pa"],
        P_evap_high_Pa=high_c["P_evap_Pa"],
        P_cond_high_Pa=high_c["P_cond_Pa"],
        pressure_ratio_low=low_c["pressure_ratio"],
        pressure_ratio_high=high_c["pressure_ratio"],
        mass_flow_low_kg_s=low_c["mass_flow_kg_s"],
        mass_flow_high_kg_s=high_c["mass_flow_kg_s"],
        W_low_W=low_c["W_compressor_W"],
        W_high_W=high_c["W_compressor_W"],
        W_total_W=W_total,
        Q_evap_W=Q_evap,
        Q_cascade_W=Q_cascade,
        Q_cond_W=Q_cond,
        COP_cooling=COP_cool,
        COP_heating=COP_cool + 1.0,
        warnings=warn_list,
    )


# ---------------------------------------------------------------------------
# 8. defrost_energy — defrost energy estimate for low-temperature coils
# ---------------------------------------------------------------------------

def defrost_energy(
    Q_evap_W: float,
    operating_hours_per_day: float,
    defrost_cycles_per_day: int,
    defrost_duration_min: float,
    *,
    defrost_fraction: float = DEFROST_ENERGY_FRACTION_DEFAULT,
) -> dict:
    """
    Estimate defrost energy for low-temperature refrigerated coils.

    Uses a simplified model: defrost energy = fraction of daily evaporator
    heat load, adjusted for the number and duration of defrost cycles.

    Parameters
    ----------
    Q_evap_W              : float — evaporator capacity (W)
    operating_hours_per_day: float — daily operating hours (h)
    defrost_cycles_per_day : int  — number of defrosts per day
    defrost_duration_min   : float — duration of each defrost cycle (min)
    defrost_fraction       : float — fraction of evaporator duty used for defrost
                                      (default 0.05 = 5%; typical hot-gas defrost)

    Returns
    -------
    dict with ok=True:
      daily_evap_energy_Wh  — total daily evaporator heat load (W·h)
      defrost_energy_Wh     — estimated daily defrost energy (W·h)
      defrost_energy_per_cycle_Wh — per-cycle defrost energy (W·h)
      defrost_duration_h_total    — total daily defrost time (h)
      effective_operating_hours   — operating hours minus defrost time
    """
    e = _guard_pos("Q_evap_W", Q_evap_W)
    if e:
        return _err(e)
    e = _guard_pos("operating_hours_per_day", operating_hours_per_day)
    if e:
        return _err(e)
    e = _guard_pos("defrost_duration_min", defrost_duration_min)
    if e:
        return _err(e)
    if not isinstance(defrost_cycles_per_day, int) or defrost_cycles_per_day < 1:
        # Allow float that is whole number
        try:
            defrost_cycles_per_day = int(defrost_cycles_per_day)
            if defrost_cycles_per_day < 1:
                raise ValueError
        except (TypeError, ValueError):
            return _err("defrost_cycles_per_day must be a positive integer.")
    e = _guard_pos("defrost_fraction", defrost_fraction)
    if e:
        return _err(e)

    daily_evap_Wh = float(Q_evap_W) * float(operating_hours_per_day)
    defrost_Wh = daily_evap_Wh * float(defrost_fraction)
    per_cycle_Wh = defrost_Wh / defrost_cycles_per_day
    defrost_h = defrost_cycles_per_day * float(defrost_duration_min) / 60.0
    eff_op_h = max(0.0, float(operating_hours_per_day) - defrost_h)

    return _ok(
        Q_evap_W=float(Q_evap_W),
        operating_hours_per_day=float(operating_hours_per_day),
        defrost_cycles_per_day=defrost_cycles_per_day,
        defrost_duration_min=float(defrost_duration_min),
        defrost_fraction=float(defrost_fraction),
        daily_evap_energy_Wh=daily_evap_Wh,
        defrost_energy_Wh=defrost_Wh,
        defrost_energy_per_cycle_Wh=per_cycle_Wh,
        defrost_duration_h_total=defrost_h,
        effective_operating_hours=eff_op_h,
    )


# ---------------------------------------------------------------------------
# 9. pressure_ratio_check — standalone pressure-ratio and discharge-temp check
# ---------------------------------------------------------------------------

def pressure_ratio_check(
    T_evap_C: float,
    T_cond_C: float,
    refrigerant: str = "R134a",
    *,
    superheat_K: float = 5.0,
) -> dict:
    """
    Check pressure ratio and estimate discharge temperature for a given
    condensing/evaporating temperature pair.

    Parameters
    ----------
    T_evap_C    : float — evaporator saturation temperature (°C)
    T_cond_C    : float — condenser saturation temperature (°C)
    refrigerant : str
    superheat_K : float — suction superheat (K, default 5)

    Returns
    -------
    dict with ok=True:
      P_evap_Pa, P_cond_Pa, pressure_ratio,
      discharge_temp_est_C, flag_high_ratio, flag_high_discharge
    """
    ref_key = _resolve_refrigerant(refrigerant)
    if ref_key is None:
        return _err(f"Unknown refrigerant {refrigerant!r}. Supported: {SUPPORTED_REFRIGERANTS}.")
    ref = _REFRIGERANT_DATA[ref_key]

    for name, val in [("T_evap_C", T_evap_C), ("T_cond_C", T_cond_C)]:
        try:
            float(val)
        except (TypeError, ValueError):
            return _err(f"{name} must be a number")
        if not math.isfinite(float(val)):
            return _err(f"{name} must be finite")

    e = _guard_nonneg("superheat_K", superheat_K)
    if e:
        return _err(e)

    T_evap_K = _C_to_K(float(T_evap_C))
    T_cond_K = _C_to_K(float(T_cond_C))

    if T_evap_K >= T_cond_K:
        return _err("T_evap_C must be less than T_cond_C.")

    P_evap = _sat_pressure(T_evap_K, ref)
    P_cond = _sat_pressure(T_cond_K, ref)
    pr = P_cond / P_evap

    R_gas = 8314.0 / ref["M_mol"]
    cp_v = _cp_vap(ref)
    k_vap = cp_v / (cp_v - R_gas) if cp_v > R_gas else 1.25
    k_vap = max(1.05, min(k_vap, 1.5))
    T_suc = T_evap_K + float(superheat_K)
    T_dis_K = T_suc * (pr ** ((k_vap - 1.0) / k_vap))
    T_dis_C = _K_to_C(T_dis_K)

    warn_list: list[str] = []
    if pr > 10.0:
        msg = f"High pressure ratio {pr:.1f} > 10; consider multi-stage."
        _warn(msg)
        warn_list.append(msg)
    if T_dis_C > 130.0:
        msg = f"High discharge temperature {T_dis_C:.1f}°C > 130°C."
        _warn(msg)
        warn_list.append(msg)

    return _ok(
        refrigerant=ref_key,
        T_evap_C=float(T_evap_C),
        T_cond_C=float(T_cond_C),
        P_evap_Pa=P_evap,
        P_cond_Pa=P_cond,
        pressure_ratio=pr,
        discharge_temp_est_C=T_dis_C,
        flag_high_ratio=pr > 10.0,
        flag_high_discharge=T_dis_C > 130.0,
        warnings=warn_list,
    )
