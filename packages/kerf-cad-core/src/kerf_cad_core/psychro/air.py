"""
kerf_cad_core.psychro.air — ASHRAE psychrometrics & HVAC load calculations.

Distinct from hvac/ (duct sizing) and thermocycle/ (power/refrigeration cycles).
Covers moist-air properties, state-point solving, load formulas, cooling-coil
analysis, evaporative cooling, and altitude pressure correction.

Unit systems
------------
SI  — temperatures in °C, pressures in Pa, humidity ratio W in kg/kg,
      enthalpy in kJ/kg, specific volume in m³/kg, density in kg/m³.
IP  — temperatures in °F, pressures in psia/in-Hg, W in lb/lb,
      enthalpy in BTU/lb, CFM for airflow, BTU/h for loads.

All functions accept and return SI quantities unless otherwise stated.
IP wrappers / helpers are provided where ASHRAE hand-calc is typically done in IP.

Functions never raise; out-of-range / non-converged conditions are flagged in
the returned dict under ``warnings`` (list[str]).

References
----------
ASHRAE Handbook — Fundamentals (2021), Chapter 1: Psychrometrics
Hyland, R.W. & Wexler, A. (1983) ASHRAE Trans. 89(2A):500-519
  — saturation pressure equations
ASHRAE Standard 55-2020 — Thermal Environmental Conditions for Human Occupancy

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_P_STD_PA = 101_325.0          # Standard atmospheric pressure [Pa]
_P_STD_PSIA = 14.696           # Standard atmospheric pressure [psia]
_R_AIR = 287.055               # Specific gas constant dry air [J/(kg·K)]
_R_WV = 461.522                # Specific gas constant water vapour [J/(kg·K)]
_CP_AIR_SI = 1.006             # Specific heat dry air [kJ/(kg·K)]
_CP_WV_SI = 1.86               # Specific heat water vapour [kJ/(kg·K)]
_HFG_0_SI = 2501.0             # Latent heat of vaporisation at 0°C [kJ/kg]
_W_RATIO = _R_AIR / _R_WV      # ≈ 0.621945

_T0_C = 0.0                    # 0 °C reference
_ABS_ZERO = 273.15             # K offset


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_K(T_C: float) -> float:
    return T_C + _ABS_ZERO


def _to_C(T_K: float) -> float:
    return T_K - _ABS_ZERO


def _to_F(T_C: float) -> float:
    return T_C * 9.0 / 5.0 + 32.0


def _from_F(T_F: float) -> float:
    """°F → °C"""
    return (T_F - 32.0) * 5.0 / 9.0


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


# ---------------------------------------------------------------------------
# Saturation pressure — Hyland-Wexler (1983), ASHRAE 2021 Ch.1
# ---------------------------------------------------------------------------

def sat_pressure(T_C: float) -> dict[str, Any]:
    """Saturation pressure of water vapour over liquid water (or ice).

    Parameters
    ----------
    T_C : float
        Dry-bulb temperature [°C].  Valid range: -100 °C to 200 °C.

    Returns
    -------
    dict with keys:
        ok        : bool
        pws_Pa    : float  — saturation pressure [Pa]
        warnings  : list[str]
    """
    warnings: list[str] = []
    T_K = _to_K(T_C)

    if T_C < -100.0 or T_C > 200.0:
        warnings.append(f"Temperature {T_C:.1f}°C out of recommended range [-100, 200]°C")

    if T_C >= 0.0:
        # Over liquid water (0 °C to 200 °C) — Hyland-Wexler
        C8 = -5.8002206e3
        C9 = 1.3914993
        C10 = -4.8640239e-2
        C11 = 4.1764768e-5
        C12 = -1.4452093e-8
        C13 = 6.5459673
        ln_pws = C8 / T_K + C9 + C10 * T_K + C11 * T_K ** 2 + C12 * T_K ** 3 + C13 * math.log(T_K)
    else:
        # Over ice (-100 °C to 0 °C) — Hyland-Wexler
        C1 = -5.6745359e3
        C2 = 6.3925247
        C3 = -9.677843e-3
        C4 = 6.2215701e-7
        C5 = 2.0747825e-9
        C6 = -9.484024e-13
        C7 = 4.1635019
        ln_pws = C1 / T_K + C2 + C3 * T_K + C4 * T_K ** 2 + C5 * T_K ** 3 + C6 * T_K ** 4 + C7 * math.log(T_K)

    pws = math.exp(ln_pws)
    return {"ok": True, "pws_Pa": pws, "warnings": warnings}


# ---------------------------------------------------------------------------
# Altitude pressure correction
# ---------------------------------------------------------------------------

def altitude_pressure(altitude_m: float) -> dict[str, Any]:
    """Barometric pressure at a given altitude using the ISA troposphere model.

    Parameters
    ----------
    altitude_m : float
        Altitude above sea level [m].  Valid: 0–11 000 m.

    Returns
    -------
    dict with keys:
        ok       : bool
        P_Pa     : float  — barometric pressure [Pa]
        warnings : list[str]
    """
    warnings: list[str] = []
    if altitude_m < 0:
        warnings.append(f"Negative altitude {altitude_m} m; using 0 m.")
        altitude_m = 0.0
    if altitude_m > 11_000.0:
        warnings.append(f"Altitude {altitude_m} m exceeds ISA troposphere limit (11 000 m); result extrapolated.")

    # ISA: P = 101325 × (1 - 2.25577e-5 × z)^5.2559
    P = 101_325.0 * (1.0 - 2.25577e-5 * altitude_m) ** 5.2559
    return {"ok": True, "P_Pa": P, "warnings": warnings}


# ---------------------------------------------------------------------------
# Humidity ratio
# ---------------------------------------------------------------------------

def humidity_ratio_from_rh(T_C: float, RH: float, P_Pa: float = _P_STD_PA) -> dict[str, Any]:
    """Humidity ratio W from dry-bulb temperature and relative humidity.

    Parameters
    ----------
    T_C  : float  — dry-bulb temperature [°C]
    RH   : float  — relative humidity [0–1]
    P_Pa : float  — total atmospheric pressure [Pa] (default: 101 325)

    Returns
    -------
    dict with keys:
        ok        : bool
        W         : float  — humidity ratio [kg_water / kg_dry_air]
        warnings  : list[str]
    """
    warnings: list[str] = []
    if not (0.0 <= RH <= 1.0):
        warnings.append(f"RH={RH} out of [0, 1]; clamped.")
        RH = _clamp(RH, 0.0, 1.0)

    pws_res = sat_pressure(T_C)
    warnings.extend(pws_res["warnings"])
    pws = pws_res["pws_Pa"]
    pw = RH * pws

    if pw >= P_Pa:
        warnings.append("Partial pressure of water vapour exceeds total pressure; supersaturated air.")
        pw = P_Pa * 0.9999

    W = _W_RATIO * pw / (P_Pa - pw)
    if W < 0.0:
        W = 0.0
        warnings.append("Computed W < 0; set to 0.")

    return {"ok": True, "W": W, "warnings": warnings}


def humidity_ratio_from_twb(T_C: float, Twb_C: float, P_Pa: float = _P_STD_PA) -> dict[str, Any]:
    """Humidity ratio W from dry-bulb and wet-bulb temperatures (Sprung formula).

    Parameters
    ----------
    T_C   : float — dry-bulb temperature [°C]
    Twb_C : float — wet-bulb temperature [°C]
    P_Pa  : float — atmospheric pressure [Pa]

    Returns
    -------
    dict with keys:
        ok        : bool
        W         : float  — humidity ratio [kg/kg]
        warnings  : list[str]
    """
    warnings: list[str] = []
    if Twb_C > T_C + 0.001:
        warnings.append(f"Wet-bulb {Twb_C:.2f}°C > dry-bulb {T_C:.2f}°C; clamped to dry-bulb.")
        Twb_C = T_C

    pws_wb = sat_pressure(Twb_C)
    warnings.extend(pws_wb["warnings"])
    Ws_wb = _W_RATIO * pws_wb["pws_Pa"] / (P_Pa - pws_wb["pws_Pa"])

    # Sprung psychrometric equation (ASHRAE 2021 Ch.1 Eq.35)
    # W = Ws_wb - A_psy * P_Pa * (T - Twb)
    # A_psy ≈ 6.6e-4 /°C for sling/aspirated psychrometer
    A_PSY = 6.6e-4
    W = Ws_wb - A_PSY * (P_Pa / _P_STD_PA) * (T_C - Twb_C)
    if W < 0.0:
        W = 0.0
        warnings.append("Computed W < 0; set to 0 (very low humidity or bad inputs).")

    return {"ok": True, "W": W, "warnings": warnings}


# ---------------------------------------------------------------------------
# Relative humidity from W and T
# ---------------------------------------------------------------------------

def relative_humidity(T_C: float, W: float, P_Pa: float = _P_STD_PA) -> dict[str, Any]:
    """Relative humidity from dry-bulb temperature and humidity ratio.

    Parameters
    ----------
    T_C  : float — dry-bulb temperature [°C]
    W    : float — humidity ratio [kg/kg]
    P_Pa : float — atmospheric pressure [Pa]

    Returns
    -------
    dict with keys:
        ok        : bool
        RH        : float  — relative humidity [0–1]
        warnings  : list[str]
    """
    warnings: list[str] = []
    if W < 0.0:
        warnings.append(f"W={W} < 0; set to 0.")
        W = 0.0

    pw = P_Pa * W / (_W_RATIO + W)
    pws_res = sat_pressure(T_C)
    warnings.extend(pws_res["warnings"])
    pws = pws_res["pws_Pa"]

    if pws <= 0.0:
        return {"ok": True, "RH": 0.0, "warnings": warnings}

    RH = pw / pws
    if RH > 1.0:
        warnings.append(f"Computed RH={RH:.4f} > 1; supersaturated air.")

    return {"ok": True, "RH": RH, "warnings": warnings}


# ---------------------------------------------------------------------------
# Dew-point temperature
# ---------------------------------------------------------------------------

def dew_point(T_C: float, RH: float, P_Pa: float = _P_STD_PA) -> dict[str, Any]:
    """Dew-point temperature from dry-bulb and relative humidity.

    Uses Magnus approximation (accurate to ±0.1 °C for 0–60 °C range),
    then refines with Newton iteration against Hyland-Wexler.

    Parameters
    ----------
    T_C  : float — dry-bulb temperature [°C]
    RH   : float — relative humidity [0–1]
    P_Pa : float — atmospheric pressure [Pa]

    Returns
    -------
    dict with keys:
        ok        : bool
        Tdp_C     : float  — dew-point temperature [°C]
        warnings  : list[str]
    """
    warnings: list[str] = []
    if not (0.0 < RH <= 1.0):
        if RH <= 0.0:
            warnings.append("RH <= 0; dew-point undefined (set to -100°C).")
            return {"ok": True, "Tdp_C": -100.0, "warnings": warnings}
        warnings.append(f"RH={RH} > 1; clamped to 1.")
        RH = 1.0

    pws_res = sat_pressure(T_C)
    warnings.extend(pws_res["warnings"])
    pw = RH * pws_res["pws_Pa"]

    # Newton iteration: find Tdp such that pws(Tdp) = pw
    # Magnus initial guess
    alpha = math.log(max(pw, 1.0) / 611.2)
    Tdp = 243.5 * alpha / (17.67 - alpha)
    Tdp = _clamp(Tdp, -80.0, T_C)

    converged = False
    for _ in range(50):
        f_res = sat_pressure(Tdp)
        f = f_res["pws_Pa"] - pw
        # Numerical derivative
        dT = 0.01
        f2_res = sat_pressure(Tdp + dT)
        dfdt = (f2_res["pws_Pa"] - f_res["pws_Pa"]) / dT
        if abs(dfdt) < 1e-30:
            break
        step = -f / dfdt
        Tdp += step
        if abs(step) < 1e-6:
            converged = True
            break

    if not converged:
        warnings.append("Dew-point Newton iteration did not converge; result approximate.")

    Tdp = min(Tdp, T_C)
    return {"ok": True, "Tdp_C": Tdp, "warnings": warnings}


# ---------------------------------------------------------------------------
# Wet-bulb temperature (iterative)
# ---------------------------------------------------------------------------

def wet_bulb(T_C: float, RH: float, P_Pa: float = _P_STD_PA, max_iter: int = 100) -> dict[str, Any]:
    """Wet-bulb temperature by iterative inversion of the Sprung formula.

    Parameters
    ----------
    T_C     : float — dry-bulb temperature [°C]
    RH      : float — relative humidity [0–1]
    P_Pa    : float — atmospheric pressure [Pa]
    max_iter: int   — maximum Newton iterations

    Returns
    -------
    dict with keys:
        ok         : bool
        Twb_C      : float  — wet-bulb temperature [°C]
        converged  : bool
        warnings   : list[str]
    """
    warnings: list[str] = []
    if not (0.0 <= RH <= 1.0):
        warnings.append(f"RH={RH} clamped to [0, 1].")
        RH = _clamp(RH, 0.0, 1.0)

    W_res = humidity_ratio_from_rh(T_C, RH, P_Pa)
    warnings.extend(W_res["warnings"])
    W_target = W_res["W"]

    # Initial guess: Twb ≈ T - (T - Tdp) * 0.3
    dp_res = dew_point(T_C, max(RH, 1e-4), P_Pa)
    Tdp_guess = dp_res["Tdp_C"]
    Twb = T_C - 0.3 * (T_C - Tdp_guess)
    Twb = _clamp(Twb, Tdp_guess - 1.0, T_C)

    A_PSY = 6.6e-4
    converged = False

    for _ in range(max_iter):
        pws_wb = sat_pressure(Twb)["pws_Pa"]
        Ws_wb = _W_RATIO * pws_wb / (P_Pa - pws_wb)
        W_calc = Ws_wb - A_PSY * (P_Pa / _P_STD_PA) * (T_C - Twb)

        # dW/dTwb: numerical
        dTwb = 0.01
        pws_wb2 = sat_pressure(Twb + dTwb)["pws_Pa"]
        Ws_wb2 = _W_RATIO * pws_wb2 / (P_Pa - pws_wb2)
        W_calc2 = Ws_wb2 - A_PSY * (P_Pa / _P_STD_PA) * (T_C - (Twb + dTwb))
        dWdTwb = (W_calc2 - W_calc) / dTwb

        residual = W_calc - W_target
        if abs(dWdTwb) < 1e-30:
            break
        step = -residual / dWdTwb
        Twb += step
        if abs(step) < 1e-6:
            converged = True
            break

    Twb = min(Twb, T_C)
    if not converged:
        warnings.append("Wet-bulb iteration did not converge; result approximate.")

    return {"ok": True, "Twb_C": Twb, "converged": converged, "warnings": warnings}


# ---------------------------------------------------------------------------
# Enthalpy
# ---------------------------------------------------------------------------

def enthalpy(T_C: float, W: float) -> dict[str, Any]:
    """Moist-air specific enthalpy (SI).

    Parameters
    ----------
    T_C : float — dry-bulb temperature [°C]
    W   : float — humidity ratio [kg/kg]

    Returns
    -------
    dict with keys:
        ok        : bool
        h_kJkg    : float  — specific enthalpy [kJ/kg dry air]
        warnings  : list[str]
    """
    warnings: list[str] = []
    if W < 0.0:
        warnings.append(f"W={W} < 0; set to 0.")
        W = 0.0

    # h = cp_a * T + W * (hfg0 + cp_wv * T)   [kJ/kg]
    h = _CP_AIR_SI * T_C + W * (_HFG_0_SI + _CP_WV_SI * T_C)
    return {"ok": True, "h_kJkg": h, "warnings": warnings}


def enthalpy_ip(T_F: float, W_lbperlb: float) -> dict[str, Any]:
    """Moist-air specific enthalpy (IP units).

    Parameters
    ----------
    T_F        : float — dry-bulb temperature [°F]
    W_lbperlb  : float — humidity ratio [lb/lb]

    Returns
    -------
    dict with keys:
        ok        : bool
        h_BTUperlb: float  — enthalpy [BTU/lb dry air]
        warnings  : list[str]
    """
    warnings: list[str] = []
    if W_lbperlb < 0.0:
        warnings.append(f"W={W_lbperlb} < 0; set to 0.")
        W_lbperlb = 0.0
    # ASHRAE IP:  h = 0.240·T + W·(1061 + 0.444·T)   [BTU/lb]
    h = 0.240 * T_F + W_lbperlb * (1061.0 + 0.444 * T_F)
    return {"ok": True, "h_BTUperlb": h, "warnings": warnings}


# ---------------------------------------------------------------------------
# Specific volume and density
# ---------------------------------------------------------------------------

def specific_volume(T_C: float, W: float, P_Pa: float = _P_STD_PA) -> dict[str, Any]:
    """Specific volume of moist air.

    Parameters
    ----------
    T_C  : float — dry-bulb temperature [°C]
    W    : float — humidity ratio [kg/kg]
    P_Pa : float — total atmospheric pressure [Pa]

    Returns
    -------
    dict with keys:
        ok          : bool
        v_m3perkg   : float — specific volume [m³/kg dry air]
        rho_kgperm3 : float — moist-air density [kg/m³]
        warnings    : list[str]
    """
    warnings: list[str] = []
    if W < 0.0:
        warnings.append(f"W={W} < 0; set to 0.")
        W = 0.0

    T_K = _to_K(T_C)
    # v = (R_a / P) * T_K * (1 + W / 0.621945)
    v = (_R_AIR / P_Pa) * T_K * (1.0 + W / _W_RATIO)
    rho = (1.0 + W) / v  # kg moist air per m³
    return {"ok": True, "v_m3perkg": v, "rho_kgperm3": rho, "warnings": warnings}


# ---------------------------------------------------------------------------
# State-point solver — any two of {Tdb, Twb, RH, W, Tdp, h}
# ---------------------------------------------------------------------------

def state_point(
    *,
    Tdb_C: float | None = None,
    Twb_C: float | None = None,
    RH: float | None = None,
    W: float | None = None,
    Tdp_C: float | None = None,
    h_kJkg: float | None = None,
    P_Pa: float = _P_STD_PA,
) -> dict[str, Any]:
    """Solve complete moist-air state from any two independent properties.

    Supported pairs (Tdb is almost always required as the second):
        (Tdb, RH), (Tdb, W), (Tdb, Twb), (Tdb, Tdp), (Tdb, h),
        (Twb, RH) — iterative, (W, h) — iterative.

    Parameters
    ----------
    Tdb_C   : dry-bulb temperature [°C]
    Twb_C   : wet-bulb temperature [°C]
    RH      : relative humidity [0–1]
    W       : humidity ratio [kg/kg]
    Tdp_C   : dew-point temperature [°C]
    h_kJkg  : specific enthalpy [kJ/kg dry air]
    P_Pa    : atmospheric pressure [Pa]

    Returns
    -------
    dict with keys:
        ok          : bool
        Tdb_C       : float
        Twb_C       : float
        RH          : float
        W           : float
        Tdp_C       : float
        h_kJkg      : float
        v_m3perkg   : float
        rho_kgperm3 : float
        warnings    : list[str]
    """
    warnings: list[str] = []

    # ---- resolve Tdb and W -----------------------------------------------
    resolved_Tdb: float | None = Tdb_C
    resolved_W: float | None = W

    if Tdb_C is not None and RH is not None:
        r = humidity_ratio_from_rh(Tdb_C, RH, P_Pa)
        warnings.extend(r["warnings"])
        resolved_W = r["W"]

    elif Tdb_C is not None and Twb_C is not None:
        r = humidity_ratio_from_twb(Tdb_C, Twb_C, P_Pa)
        warnings.extend(r["warnings"])
        resolved_W = r["W"]

    elif Tdb_C is not None and Tdp_C is not None:
        # W from dew-point: pws(Tdp) = pw;  W = 0.621945 * pw / (P - pw)
        if Tdp_C > Tdb_C + 0.001:
            warnings.append(f"Tdp {Tdp_C:.2f}°C > Tdb {Tdb_C:.2f}°C; clamped to Tdb.")
            Tdp_C = Tdb_C
        pws_dp = sat_pressure(Tdp_C)["pws_Pa"]
        resolved_W = _W_RATIO * pws_dp / (P_Pa - pws_dp)

    elif Tdb_C is not None and W is not None:
        resolved_W = W

    elif Tdb_C is not None and h_kJkg is not None:
        # h = cp_a * T + W * (hfg0 + cp_wv * T) → solve for W
        denom = _HFG_0_SI + _CP_WV_SI * Tdb_C
        if abs(denom) < 1e-10:
            warnings.append("Cannot solve W from h: denom near zero.")
            resolved_W = 0.0
        else:
            resolved_W = (h_kJkg - _CP_AIR_SI * Tdb_C) / denom

    elif W is not None and h_kJkg is not None:
        # Solve Tdb from h = cp_a*T + W*(hfg0 + cp_wv*T)
        # h = T*(cp_a + W*cp_wv) + W*hfg0
        denom2 = _CP_AIR_SI + W * _CP_WV_SI
        if abs(denom2) < 1e-10:
            warnings.append("Cannot solve Tdb from (W, h): denom near zero.")
            resolved_Tdb = 20.0
        else:
            resolved_Tdb = (h_kJkg - W * _HFG_0_SI) / denom2
        resolved_W = W

    else:
        given = {k: v for k, v in [
            ("Tdb_C", Tdb_C), ("Twb_C", Twb_C), ("RH", RH),
            ("W", W), ("Tdp_C", Tdp_C), ("h_kJkg", h_kJkg)
        ] if v is not None}
        warnings.append(
            f"Unsupported property pair {list(given.keys())}; "
            "provide two of: Tdb_C, Twb_C, RH, W, Tdp_C, h_kJkg."
        )
        return {"ok": False, "warnings": warnings}

    if resolved_Tdb is None or resolved_W is None:
        warnings.append("Could not resolve Tdb and W from given inputs.")
        return {"ok": False, "warnings": warnings}

    if resolved_W < 0.0:
        warnings.append(f"Resolved W={resolved_W:.6f} < 0; set to 0.")
        resolved_W = 0.0

    # ---- derive remaining properties ------------------------------------
    rh_res = relative_humidity(resolved_Tdb, resolved_W, P_Pa)
    warnings.extend(rh_res["warnings"])
    resolved_RH = rh_res["RH"]

    tdp_res = dew_point(resolved_Tdb, max(resolved_RH, 1e-6), P_Pa)
    warnings.extend(tdp_res["warnings"])
    resolved_Tdp = tdp_res["Tdp_C"]

    twb_res = wet_bulb(resolved_Tdb, resolved_RH, P_Pa)
    warnings.extend(twb_res["warnings"])
    resolved_Twb = twb_res["Twb_C"]

    h_res = enthalpy(resolved_Tdb, resolved_W)
    warnings.extend(h_res["warnings"])
    resolved_h = h_res["h_kJkg"]

    sv_res = specific_volume(resolved_Tdb, resolved_W, P_Pa)
    warnings.extend(sv_res["warnings"])

    return {
        "ok": True,
        "Tdb_C": resolved_Tdb,
        "Twb_C": resolved_Twb,
        "RH": resolved_RH,
        "W": resolved_W,
        "Tdp_C": resolved_Tdp,
        "h_kJkg": resolved_h,
        "v_m3perkg": sv_res["v_m3perkg"],
        "rho_kgperm3": sv_res["rho_kgperm3"],
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Air mixing
# ---------------------------------------------------------------------------

def mix_air_streams(
    cfm1: float, Tdb1_C: float, W1: float,
    cfm2: float, Tdb2_C: float, W2: float,
    P_Pa: float = _P_STD_PA,
) -> dict[str, Any]:
    """Mix two air streams at equal pressure (mass-weighted average).

    Parameters
    ----------
    cfm1, cfm2 : float — volumetric flow rates [CFM] (proportional; ratio used)
    Tdb1_C, Tdb2_C : float — dry-bulb temperatures [°C]
    W1, W2     : float — humidity ratios [kg/kg]
    P_Pa       : float — atmospheric pressure [Pa]

    Returns
    -------
    dict with keys:
        ok       : bool
        Tdb_C    : float — mixed dry-bulb temperature [°C]
        W        : float — mixed humidity ratio [kg/kg]
        h_kJkg   : float — mixed enthalpy [kJ/kg]
        warnings : list[str]
    """
    warnings: list[str] = []
    if cfm1 < 0 or cfm2 < 0:
        warnings.append("Negative CFM values; using absolute values.")
        cfm1, cfm2 = abs(cfm1), abs(cfm2)
    total = cfm1 + cfm2
    if total == 0.0:
        warnings.append("Total flow is zero; returning stream 1 conditions.")
        return {"ok": True, "Tdb_C": Tdb1_C, "W": W1,
                "h_kJkg": enthalpy(Tdb1_C, W1)["h_kJkg"], "warnings": warnings}

    # Convert to mass flows: m_dot ∝ cfm * rho = cfm * (1+W)/v
    sv1 = specific_volume(Tdb1_C, W1, P_Pa)
    sv2 = specific_volume(Tdb2_C, W2, P_Pa)
    mdot1 = cfm1 / sv1["v_m3perkg"]  # proportional mass flow
    mdot2 = cfm2 / sv2["v_m3perkg"]
    total_m = mdot1 + mdot2

    h1 = enthalpy(Tdb1_C, W1)["h_kJkg"]
    h2 = enthalpy(Tdb2_C, W2)["h_kJkg"]

    W_mix = (mdot1 * W1 + mdot2 * W2) / total_m
    h_mix = (mdot1 * h1 + mdot2 * h2) / total_m

    # Solve Tdb from h and W
    sp = state_point(W=W_mix, h_kJkg=h_mix, P_Pa=P_Pa)
    warnings.extend(sp.get("warnings", []))
    Tdb_mix = sp.get("Tdb_C", (mdot1 * Tdb1_C + mdot2 * Tdb2_C) / total_m)

    return {"ok": True, "Tdb_C": Tdb_mix, "W": W_mix, "h_kJkg": h_mix, "warnings": warnings}


# ---------------------------------------------------------------------------
# ASHRAE load calculations (IP)
# ---------------------------------------------------------------------------

def sensible_load_ip(cfm: float, delta_T_F: float) -> dict[str, Any]:
    """Sensible heat load using ASHRAE standard-air formula.

    Q_sensible = 1.08 × CFM × ΔT   [BTU/h]

    Parameters
    ----------
    cfm      : float — airflow [CFM]
    delta_T_F: float — dry-bulb temperature difference [°F]

    Returns
    -------
    dict with keys:
        ok      : bool
        Q_BTUh  : float — sensible load [BTU/h]
        warnings: list[str]
    """
    warnings: list[str] = []
    if cfm < 0:
        warnings.append(f"Negative CFM={cfm}; using absolute value.")
        cfm = abs(cfm)
    Q = 1.08 * cfm * delta_T_F
    return {"ok": True, "Q_BTUh": Q, "warnings": warnings}


def latent_load_ip(cfm: float, delta_W_grains: float | None = None,
                   delta_W_lbperlb: float | None = None) -> dict[str, Any]:
    """Latent heat load using ASHRAE standard-air formula.

    Q_latent = 0.68 × CFM × ΔW_grains  [BTU/h]   (ΔW in grains/lb)
    or equivalently:
    Q_latent = 4840 × CFM × ΔW          [BTU/h]   (ΔW in lb/lb)

    Parameters
    ----------
    cfm             : float — airflow [CFM]
    delta_W_grains  : float | None — humidity ratio diff [grains/lb]
    delta_W_lbperlb : float | None — humidity ratio diff [lb/lb]

    Returns
    -------
    dict with keys:
        ok      : bool
        Q_BTUh  : float — latent load [BTU/h]
        warnings: list[str]
    """
    warnings: list[str] = []
    if cfm < 0:
        warnings.append(f"Negative CFM={cfm}; using absolute value.")
        cfm = abs(cfm)

    if delta_W_grains is not None:
        Q = 0.68 * cfm * delta_W_grains
    elif delta_W_lbperlb is not None:
        Q = 4840.0 * cfm * delta_W_lbperlb
    else:
        return {"ok": False, "warnings": ["Either delta_W_grains or delta_W_lbperlb must be provided."]}

    return {"ok": True, "Q_BTUh": Q, "warnings": warnings}


def total_load_ip(cfm: float, delta_h_BTUperlb: float) -> dict[str, Any]:
    """Total (sensible + latent) heat load.

    Q_total = 4.5 × CFM × Δh   [BTU/h]  (Δh in BTU/lb, standard air)

    Parameters
    ----------
    cfm             : float — airflow [CFM]
    delta_h_BTUperlb: float — enthalpy difference [BTU/lb dry air]

    Returns
    -------
    dict with keys:
        ok      : bool
        Q_BTUh  : float — total load [BTU/h]
        warnings: list[str]
    """
    warnings: list[str] = []
    if cfm < 0:
        warnings.append(f"Negative CFM={cfm}; using absolute value.")
        cfm = abs(cfm)
    Q = 4.5 * cfm * delta_h_BTUperlb
    return {"ok": True, "Q_BTUh": Q, "warnings": warnings}


# ---------------------------------------------------------------------------
# Cooling-coil analysis
# ---------------------------------------------------------------------------

def coil_adp(
    Tdb_entering_C: float, Twb_entering_C: float,
    Tdb_leaving_C: float, Twb_leaving_C: float,
    P_Pa: float = _P_STD_PA,
) -> dict[str, Any]:
    """Cooling-coil Apparatus Dew Point (ADP) and Bypass Factor (BF).

    The ADP is the coil-surface temperature; it lies on the saturation
    curve and on the straight line connecting entering and leaving
    state points on the psychrometric chart.

    Method: iterative ray-to-saturation-curve intersection.

    Parameters
    ----------
    Tdb_entering_C : float — entering dry-bulb [°C]
    Twb_entering_C : float — entering wet-bulb [°C]
    Tdb_leaving_C  : float — leaving dry-bulb [°C]
    Twb_leaving_C  : float — leaving wet-bulb [°C]
    P_Pa           : float — atmospheric pressure [Pa]

    Returns
    -------
    dict with keys:
        ok        : bool
        T_ADP_C   : float — apparatus dew point [°C]
        W_ADP     : float — ADP humidity ratio [kg/kg]
        BF        : float — bypass factor [0–1]
        SHR       : float — sensible heat ratio [0–1]
        warnings  : list[str]
    """
    warnings: list[str] = []

    sp_e = state_point(Tdb_C=Tdb_entering_C, Twb_C=Twb_entering_C, P_Pa=P_Pa)
    sp_l = state_point(Tdb_C=Tdb_leaving_C, Twb_C=Twb_leaving_C, P_Pa=P_Pa)
    warnings.extend(sp_e.get("warnings", []))
    warnings.extend(sp_l.get("warnings", []))

    if not sp_e["ok"] or not sp_l["ok"]:
        return {"ok": False, "warnings": warnings}

    We = sp_e["W"]
    Wl = sp_l["W"]
    Te = Tdb_entering_C
    Tl = Tdb_leaving_C

    if abs(Te - Tl) < 1e-6:
        warnings.append("Entering and leaving Tdb are equal; no cooling.")
        return {"ok": True, "T_ADP_C": Tl, "W_ADP": Wl, "BF": 1.0, "SHR": 1.0, "warnings": warnings}

    # Line parametrically: T = Te + t*(Tl - Te),  W = We + t*(Wl - We)
    # Find t where W = Ws(T) (on saturation curve)
    # Bisect from t_guess towards leaving end extended
    # ADP is at t > 1 if leaving is not on saturation curve
    # Use bisection on f(t) = W(t) - Ws(T(t))

    def state_at_t(t: float) -> tuple[float, float]:
        T = Te + t * (Tl - Te)
        W_line = We + t * (Wl - We)
        return T, W_line

    def residual(t: float) -> float:
        T, W_line = state_at_t(t)
        pws = sat_pressure(T)["pws_Pa"]
        Ws = _W_RATIO * pws / (P_Pa - pws)
        return W_line - Ws

    # At t=0 (entering), W_line > Ws typically (air is not saturated → positive)
    # ADP lies where W_line == Ws; search between t=1 and t=2 (extension)
    # Actually search from t=1 outward
    r1 = residual(1.0)
    r_ext = residual(2.0)

    t_lo, t_hi = 1.0, 2.0
    if r1 * r_ext > 0:
        # Try wider range
        for ext in (3.0, 5.0, 10.0):
            r_ext = residual(ext)
            if r1 * r_ext < 0:
                t_hi = ext
                break
        else:
            # ADP ≈ leaving conditions
            warnings.append("Could not find ADP beyond leaving state; using leaving conditions.")
            T_ADP = Tl
            W_ADP_val = sat_pressure(Tl)["pws_Pa"]
            W_ADP_val = _W_RATIO * W_ADP_val / (P_Pa - W_ADP_val)
            BF = (Tl - T_ADP) / (Te - T_ADP) if abs(Te - T_ADP) > 1e-6 else 0.0
            SHR = _shr(sp_e, sp_l)
            return {"ok": True, "T_ADP_C": T_ADP, "W_ADP": W_ADP_val, "BF": BF, "SHR": SHR, "warnings": warnings}

    # Bisection
    for _ in range(60):
        t_mid = 0.5 * (t_lo + t_hi)
        r_mid = residual(t_mid)
        if abs(r_mid) < 1e-9:
            break
        if r1 * r_mid < 0:
            t_hi = t_mid
        else:
            t_lo = t_mid

    t_adp = 0.5 * (t_lo + t_hi)
    T_ADP_C, W_ADP_line = state_at_t(t_adp)

    # BF = (Tl - T_ADP) / (Te - T_ADP)
    if abs(Te - T_ADP_C) < 1e-6:
        BF = 0.0
    else:
        BF = (Tl - T_ADP_C) / (Te - T_ADP_C)
    BF = _clamp(BF, 0.0, 1.0)

    SHR = _shr(sp_e, sp_l)

    return {
        "ok": True,
        "T_ADP_C": T_ADP_C,
        "W_ADP": W_ADP_line,
        "BF": BF,
        "SHR": SHR,
        "warnings": warnings,
    }


def _shr(sp_entering: dict, sp_leaving: dict) -> float:
    """Sensible heat ratio from entering/leaving state dicts."""
    Te = sp_entering.get("Tdb_C", 0.0)
    Tl = sp_leaving.get("Tdb_C", 0.0)
    he = sp_entering.get("h_kJkg", 0.0)
    hl = sp_leaving.get("h_kJkg", 0.0)
    if abs(he - hl) < 1e-9:
        return 1.0
    # Sensible load proportion: ΔT ratio (approximate, standard air)
    # More precisely: SHR = (cp_a * ΔT) / (Δh)
    # cp_a ≈ 1.006 kJ/(kg·K)
    delta_h = he - hl
    delta_hs = _CP_AIR_SI * (Te - Tl)
    SHR = delta_hs / delta_h if abs(delta_h) > 1e-9 else 1.0
    return _clamp(SHR, 0.0, 1.0)


def coil_leaving_conditions(
    Tdb_entering_C: float, W_entering: float,
    Q_sensible_kW: float, Q_total_kW: float,
    mass_flow_kgs: float,
    P_Pa: float = _P_STD_PA,
) -> dict[str, Any]:
    """Cooling-coil leaving air conditions given loads and entering state.

    Parameters
    ----------
    Tdb_entering_C : float — entering dry-bulb [°C]
    W_entering     : float — entering humidity ratio [kg/kg]
    Q_sensible_kW  : float — sensible cooling load [kW] (positive = cooling)
    Q_total_kW     : float — total cooling load [kW] (positive = cooling)
    mass_flow_kgs  : float — dry-air mass flow rate [kg/s]
    P_Pa           : float — atmospheric pressure [Pa]

    Returns
    -------
    dict with keys:
        ok           : bool
        Tdb_leaving_C: float — leaving dry-bulb [°C]
        W_leaving    : float — leaving humidity ratio [kg/kg]
        h_leaving    : float — leaving enthalpy [kJ/kg]
        SHR          : float — sensible heat ratio
        warnings     : list[str]
    """
    warnings: list[str] = []
    if mass_flow_kgs <= 0.0:
        return {"ok": False, "warnings": ["mass_flow_kgs must be > 0"]}

    h_entering = enthalpy(Tdb_entering_C, W_entering)["h_kJkg"]

    # Leaving enthalpy from total load
    h_leaving = h_entering - Q_total_kW / mass_flow_kgs

    # Leaving Tdb from sensible load
    Tdb_leaving = Tdb_entering_C - Q_sensible_kW / (mass_flow_kgs * _CP_AIR_SI)

    # Leaving W from h and T
    denom = _HFG_0_SI + _CP_WV_SI * Tdb_leaving
    if abs(denom) < 1e-10:
        warnings.append("Cannot solve W_leaving: denom near zero.")
        W_leaving = W_entering
    else:
        W_leaving = (h_leaving - _CP_AIR_SI * Tdb_leaving) / denom

    if W_leaving < 0.0:
        warnings.append(f"Computed W_leaving={W_leaving:.6f} < 0; set to 0.")
        W_leaving = 0.0

    SHR = Q_sensible_kW / Q_total_kW if abs(Q_total_kW) > 1e-9 else 1.0
    SHR = _clamp(SHR, 0.0, 1.0)

    return {
        "ok": True,
        "Tdb_leaving_C": Tdb_leaving,
        "W_leaving": W_leaving,
        "h_leaving": h_leaving,
        "SHR": SHR,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Evaporative cooling effectiveness
# ---------------------------------------------------------------------------

def evaporative_cooling(
    Tdb_C: float, RH: float,
    effectiveness: float = 0.80,
    P_Pa: float = _P_STD_PA,
) -> dict[str, Any]:
    """Direct evaporative cooler leaving conditions.

    Leaving Tdb = Tdb - ε × (Tdb - Twb)
    Leaving W increases (moisture added), but h stays ~constant.

    Parameters
    ----------
    Tdb_C       : float — entering dry-bulb [°C]
    RH          : float — entering relative humidity [0–1]
    effectiveness: float — cooler effectiveness [0–1] (default 0.80)
    P_Pa        : float — atmospheric pressure [Pa]

    Returns
    -------
    dict with keys:
        ok              : bool
        Tdb_leaving_C   : float — leaving dry-bulb [°C]
        W_leaving       : float — leaving humidity ratio [kg/kg]
        RH_leaving      : float — leaving RH [0–1]
        h_leaving_kJkg  : float — leaving enthalpy [kJ/kg]
        warnings        : list[str]
    """
    warnings: list[str] = []
    if not (0.0 < effectiveness <= 1.0):
        warnings.append(f"Effectiveness={effectiveness} clamped to (0, 1].")
        effectiveness = _clamp(effectiveness, 0.001, 1.0)

    sp_entering = state_point(Tdb_C=Tdb_C, RH=RH, P_Pa=P_Pa)
    warnings.extend(sp_entering.get("warnings", []))
    if not sp_entering["ok"]:
        return {"ok": False, "warnings": warnings}

    Twb_C = sp_entering["Twb_C"]
    W_entering = sp_entering["W"]
    h_entering = sp_entering["h_kJkg"]

    # Leaving Tdb
    Tdb_leaving = Tdb_C - effectiveness * (Tdb_C - Twb_C)

    # Enthalpy nearly constant for adiabatic saturation (ideal)
    h_leaving = h_entering

    # Leaving W from h and Tdb_leaving
    denom = _HFG_0_SI + _CP_WV_SI * Tdb_leaving
    W_leaving = (h_leaving - _CP_AIR_SI * Tdb_leaving) / denom if abs(denom) > 1e-10 else W_entering

    if W_leaving < W_entering:
        warnings.append("W_leaving < W_entering after evaporative cooling; using W_entering.")
        W_leaving = W_entering

    rh_res = relative_humidity(Tdb_leaving, W_leaving, P_Pa)
    warnings.extend(rh_res["warnings"])
    RH_leaving = rh_res["RH"]

    h_leaving_actual = enthalpy(Tdb_leaving, W_leaving)["h_kJkg"]

    return {
        "ok": True,
        "Tdb_leaving_C": Tdb_leaving,
        "W_leaving": W_leaving,
        "RH_leaving": RH_leaving,
        "h_leaving_kJkg": h_leaving_actual,
        "warnings": warnings,
    }
