"""
kerf_cad_core.windturbine.rotor — pure-Python wind-turbine power & rotor sizing.

All functions are self-contained (math only, stdlib only).  No OCC dependency.
Warnings are issued via the standard ``warnings`` module; functions never raise
on domain errors — they return result dicts with a ``warnings`` key.

Implements
----------
WIND RESOURCE
  available_power(rho, A, V)
      Available wind power from the kinetic energy flux P = ½·ρ·A·V³.

  betz_limit()
      Return Betz Cp_max = 16/27 and the derivation note.

  air_density(altitude_m, temperature_c)
      ISA air density at altitude (m) and temperature (°C).

ROTOR SIZING
  rotor_diameter(P_rated_W, Cp, rho, V_rated_ms)
      Rotor diameter from rated electrical power, Cp, air density, wind speed.

  rotor_speed(V_ms, tsr, diameter_m)
      Rotor angular velocity (rad/s) and RPM from tip-speed ratio and diameter.

  gearbox_ratio(rotor_rpm, generator_rpm)
      Required gearbox ratio (integer-rounded up).

LOADS
  thrust_force(rho, A, V, Ct)
      Axial thrust force on rotor (N); Ct ≈ 4a(1-a), default a=1/3 → Ct≈8/9.

  overturning_moment(thrust_N, hub_height_m)
      Tower base overturning moment (N·m) from thrust × hub height.

AERODYNAMICS
  blade_element_momentum(tsr, n_blades, chord_r_ratio, twist_deg_list,
                          *, n_annuli, a_init, a_prime_init, max_iter, tol)
      Simplified BEM: iterate axial (a) and tangential (a′) induction factors
      per annulus, return integrated Cp and per-annulus results.

WIND DISTRIBUTIONS & AEP
  weibull_aep(k, c_ms, power_curve_dict, *, hours_per_year)
      Annual energy production (kWh) by integrating power curve × Weibull PDF.

  rayleigh_aep(v_mean_ms, power_curve_dict, *, hours_per_year)
      AEP using Rayleigh distribution (Weibull k=2, c = 2·v_mean/√π).

  power_curve(V_ms, V_cutin, V_rated, V_cutout, P_rated_W, *, Cp, rho, A)
      Power-curve model: zero below cut-in, cubic ramp to rated, flat at
      rated, zero above cut-out.  Cp/rho/A used only when provided.

  capacity_factor(aep_kWh, P_rated_W, *, hours_per_year)
      Capacity factor = AEP / (P_rated × 8760 h).

WAKE & ARRAY
  jensen_wake(u0_ms, Ct, x_m, D_m, *, k_w)
      Jensen single-wake deficit: wind speed behind a turbine at distance x.

NOISE
  sound_pressure_distance(Lw_dB, distance_m)
      SPL at observer distance from turbine sound-power level (hemispherical
      propagation over reflecting ground).

References
----------
Burton, T. et al., "Wind Energy Handbook", 2nd ed., Wiley (2011).
Betz, A. (1920) — momentum theory maximum Cp = 16/27.
Glauert, H. (1935) — BEM method.
Jensen, N.O. (1983) — wake decay model (RISØ M-2411).
ISO 9613-2:1996 — Acoustics — attenuation of sound outdoor propagation.

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import Any


# ---------------------------------------------------------------------------
# WIND RESOURCE
# ---------------------------------------------------------------------------

def available_power(rho: float, A: float, V: float) -> dict[str, Any]:
    """
    Available wind power P = ½·ρ·A·V³.

    Parameters
    ----------
    rho  : air density (kg/m³); standard = 1.225 kg/m³ at sea level / 15°C
    A    : rotor swept area (m²)
    V    : free-stream wind speed (m/s)

    Returns
    -------
    dict with keys:
      power_W       — available wind power (W)
      power_kW      — power in kW
      wind_speed_ms — input wind speed
      swept_area_m2 — input swept area
      rho_kg_m3     — input air density
      warnings      — list of advisory strings
    """
    warns: list[str] = []
    if rho <= 0:
        warnings.warn(f"air density rho={rho} must be > 0; using 1.225 kg/m³", stacklevel=2)
        warns.append(f"air density rho={rho} invalid, defaulted to 1.225 kg/m³")
        rho = 1.225
    if A <= 0:
        warnings.warn(f"swept area A={A} must be > 0", stacklevel=2)
        warns.append(f"swept area A={A} invalid")
        A = 0.0
    if V < 0:
        warnings.warn(f"wind speed V={V} cannot be negative; using 0", stacklevel=2)
        warns.append(f"wind speed V={V} set to 0")
        V = 0.0

    P = 0.5 * rho * A * V ** 3
    return {
        "power_W": P,
        "power_kW": P / 1000.0,
        "wind_speed_ms": V,
        "swept_area_m2": A,
        "rho_kg_m3": rho,
        "warnings": warns,
    }


def betz_limit() -> dict[str, Any]:
    """
    Return the Betz theoretical maximum power coefficient.

    Cp_max = 16/27 ≈ 0.5926 (Betz, 1920).

    At the Betz optimum, the axial induction factor a = 1/3:
      - Wake velocity = (1 - 2a)·V = V/3
      - Rotor plane velocity = (1 - a)·V = 2V/3
    """
    cp_max = 16.0 / 27.0
    return {
        "Cp_max": cp_max,
        "Cp_max_percent": round(cp_max * 100, 4),
        "axial_induction_at_betz": 1.0 / 3.0,
        "note": (
            "Betz (1920) momentum theory upper bound: Cp ≤ 16/27 ≈ 0.5926. "
            "Real turbines achieve Cp ≈ 0.35–0.50 due to wake rotation, "
            "profile drag, tip losses, and finite blade count."
        ),
        "warnings": [],
    }


def air_density(altitude_m: float = 0.0, temperature_c: float = 15.0) -> dict[str, Any]:
    """
    ISA air density corrected for altitude and temperature.

    Uses the barometric formula for pressure and the ideal gas law:
      P(h) = P0 · exp(−M·g·h / (R·T))
      ρ = P / (R_specific · T)

    Parameters
    ----------
    altitude_m    : altitude above sea level (m), default 0
    temperature_c : ambient temperature (°C), default 15

    Returns
    -------
    dict with rho_kg_m3, pressure_Pa, temperature_K
    """
    warns: list[str] = []
    if altitude_m < 0:
        warnings.warn(f"altitude={altitude_m} m is below sea level; using 0", stacklevel=2)
        warns.append(f"altitude={altitude_m} clamped to 0 m")
        altitude_m = 0.0

    T_K = temperature_c + 273.15
    P0 = 101325.0   # Pa, sea-level standard pressure
    M = 0.0289644   # kg/mol, molar mass of dry air
    g = 9.80665     # m/s²
    R = 8.31446     # J/(mol·K)
    R_spec = 287.058  # J/(kg·K)

    P = P0 * math.exp(-M * g * altitude_m / (R * T_K))
    rho = P / (R_spec * T_K)

    if rho < 0.9:
        warnings.warn(
            f"air density {rho:.3f} kg/m³ is very low (high altitude/temperature); "
            "turbine power will be significantly reduced",
            stacklevel=2,
        )
        warns.append(f"low air density {rho:.3f} kg/m³ — verify altitude/temperature")

    return {
        "rho_kg_m3": rho,
        "pressure_Pa": P,
        "temperature_K": T_K,
        "altitude_m": altitude_m,
        "temperature_c": temperature_c,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# ROTOR SIZING
# ---------------------------------------------------------------------------

def rotor_diameter(
    P_rated_W: float,
    Cp: float,
    rho: float,
    V_rated_ms: float,
) -> dict[str, Any]:
    """
    Rotor diameter from rated electrical power.

    From P = ½·ρ·(π·D²/4)·V³·Cp  →  D = sqrt(8·P / (π·ρ·V³·Cp))

    Parameters
    ----------
    P_rated_W   : rated electrical power output (W)
    Cp          : power coefficient (dimensionless); typical 0.35–0.50
    rho         : air density (kg/m³)
    V_rated_ms  : rated (design) wind speed (m/s)

    Returns
    -------
    dict with diameter_m, swept_area_m2, warnings
    """
    warns: list[str] = []
    CP_MAX = 16.0 / 27.0

    if P_rated_W <= 0:
        warnings.warn(f"P_rated_W={P_rated_W} must be > 0", stacklevel=2)
        warns.append("P_rated_W must be > 0")
        return {"diameter_m": None, "swept_area_m2": None, "warnings": warns}
    if Cp <= 0 or Cp > CP_MAX:
        if Cp > CP_MAX:
            warnings.warn(
                f"Cp={Cp} exceeds Betz limit {CP_MAX:.4f} — physically impossible; "
                "clamped to Betz limit",
                stacklevel=2,
            )
            warns.append(f"Cp={Cp} above Betz limit {CP_MAX:.4f}, clamped")
            Cp = CP_MAX
        else:
            warnings.warn(f"Cp={Cp} must be > 0", stacklevel=2)
            warns.append("Cp must be > 0")
            return {"diameter_m": None, "swept_area_m2": None, "warnings": warns}
    if rho <= 0:
        warnings.warn(f"rho={rho} must be > 0", stacklevel=2)
        warns.append("rho must be > 0")
        return {"diameter_m": None, "swept_area_m2": None, "warnings": warns}
    if V_rated_ms <= 0:
        warnings.warn(f"V_rated_ms={V_rated_ms} must be > 0", stacklevel=2)
        warns.append("V_rated_ms must be > 0")
        return {"diameter_m": None, "swept_area_m2": None, "warnings": warns}

    D = math.sqrt(8.0 * P_rated_W / (math.pi * rho * V_rated_ms ** 3 * Cp))
    A = math.pi * D ** 2 / 4.0

    return {
        "diameter_m": D,
        "swept_area_m2": A,
        "Cp_used": Cp,
        "V_rated_ms": V_rated_ms,
        "rho_kg_m3": rho,
        "warnings": warns,
    }


def rotor_speed(
    V_ms: float,
    tsr: float,
    diameter_m: float,
) -> dict[str, Any]:
    """
    Rotor speed from tip-speed ratio.

    TSR = (blade-tip speed) / (wind speed) = (ω · R) / V
    → ω = TSR · V / R   [rad/s]
    → n = ω · 60 / (2π)  [RPM]

    Parameters
    ----------
    V_ms       : wind speed (m/s)
    tsr        : tip-speed ratio (dimensionless); typical 6–10 for 3-blade HAWT
    diameter_m : rotor diameter (m)

    Returns
    -------
    dict with omega_rad_s, rpm, tip_speed_ms, warnings
    """
    warns: list[str] = []
    if V_ms <= 0:
        warnings.warn(f"V_ms={V_ms} must be > 0", stacklevel=2)
        warns.append("V_ms must be > 0")
        return {"omega_rad_s": None, "rpm": None, "warnings": warns}
    if tsr <= 0:
        warnings.warn(f"tsr={tsr} must be > 0", stacklevel=2)
        warns.append("tsr must be > 0")
        return {"omega_rad_s": None, "rpm": None, "warnings": warns}
    if diameter_m <= 0:
        warnings.warn(f"diameter_m={diameter_m} must be > 0", stacklevel=2)
        warns.append("diameter_m must be > 0")
        return {"omega_rad_s": None, "rpm": None, "warnings": warns}

    R = diameter_m / 2.0
    omega = tsr * V_ms / R
    rpm = omega * 60.0 / (2.0 * math.pi)
    tip_speed = omega * R

    if tip_speed > 80.0:
        warnings.warn(
            f"Tip speed {tip_speed:.1f} m/s exceeds 80 m/s — "
            "noise and structural limits typically require ≤ 80 m/s",
            stacklevel=2,
        )
        warns.append(f"tip speed {tip_speed:.1f} m/s > 80 m/s noise/structural limit")

    return {
        "omega_rad_s": omega,
        "rpm": rpm,
        "tip_speed_ms": tip_speed,
        "tsr": tsr,
        "diameter_m": diameter_m,
        "warnings": warns,
    }


def gearbox_ratio(rotor_rpm: float, generator_rpm: float) -> dict[str, Any]:
    """
    Required gearbox ratio from rotor speed to generator speed.

    ratio = generator_rpm / rotor_rpm  (rounded up to next integer for
    standard step-up gearboxes; exact float also returned).

    Parameters
    ----------
    rotor_rpm     : rotor rotational speed (RPM)
    generator_rpm : synchronous or rated generator speed (RPM);
                    e.g. 1500 RPM for 4-pole 50 Hz, 1800 RPM for 4-pole 60 Hz

    Returns
    -------
    dict with ratio_exact, ratio_integer, generator_rpm_actual
    """
    warns: list[str] = []
    if rotor_rpm <= 0:
        warnings.warn(f"rotor_rpm={rotor_rpm} must be > 0", stacklevel=2)
        warns.append("rotor_rpm must be > 0")
        return {"ratio_exact": None, "ratio_integer": None, "warnings": warns}
    if generator_rpm <= 0:
        warnings.warn(f"generator_rpm={generator_rpm} must be > 0", stacklevel=2)
        warns.append("generator_rpm must be > 0")
        return {"ratio_exact": None, "ratio_integer": None, "warnings": warns}

    ratio = generator_rpm / rotor_rpm
    ratio_int = math.ceil(ratio)
    gen_rpm_actual = rotor_rpm * ratio_int

    return {
        "ratio_exact": ratio,
        "ratio_integer": ratio_int,
        "rotor_rpm": rotor_rpm,
        "generator_rpm_target": generator_rpm,
        "generator_rpm_actual": gen_rpm_actual,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# LOADS
# ---------------------------------------------------------------------------

def thrust_force(
    rho: float,
    A: float,
    V: float,
    Ct: float = 8.0 / 9.0,
) -> dict[str, Any]:
    """
    Axial thrust force on the rotor.

    T = ½·ρ·A·V²·Ct

    At the Betz optimum (a = 1/3):  Ct = 4a(1-a) = 4/3·(2/3) = 8/9 ≈ 0.889.

    Parameters
    ----------
    rho : air density (kg/m³)
    A   : swept area (m²)
    V   : wind speed (m/s)
    Ct  : thrust coefficient (dimensionless); default 8/9 (Betz optimum)

    Returns
    -------
    dict with thrust_N, thrust_kN, warnings
    """
    warns: list[str] = []
    for name, val in [("rho", rho), ("A", A), ("V", V)]:
        if val <= 0:
            warnings.warn(f"{name}={val} must be > 0", stacklevel=2)
            warns.append(f"{name} must be > 0")
            return {"thrust_N": None, "thrust_kN": None, "warnings": warns}
    if Ct <= 0 or Ct > 1.0:
        warnings.warn(f"Ct={Ct} outside (0, 1]; using 8/9", stacklevel=2)
        warns.append(f"Ct={Ct} out of range, defaulted to 8/9")
        Ct = 8.0 / 9.0

    T = 0.5 * rho * A * V ** 2 * Ct
    return {
        "thrust_N": T,
        "thrust_kN": T / 1000.0,
        "Ct": Ct,
        "warnings": warns,
    }


def overturning_moment(thrust_N: float, hub_height_m: float) -> dict[str, Any]:
    """
    Tower base overturning moment from rotor thrust.

    M_ot = T × hub_height

    This is a simplified first-order estimate; actual design must also
    account for the tower's own weight eccentricity, wind load on the tower
    tube, and dynamic amplification (tower shadow, turbulence).

    Note: Tower-shadow effect (periodic thrust dip when a blade passes the
    tower) produces a 3P (three-bladed) or 2P (two-bladed) pulsating load
    that excites tower resonance; detailed FEA is needed for full design.

    Parameters
    ----------
    thrust_N     : axial rotor thrust (N)
    hub_height_m : hub centreline height above ground (m)
    """
    warns: list[str] = []
    if thrust_N < 0:
        warnings.warn(f"thrust_N={thrust_N} cannot be negative", stacklevel=2)
        warns.append("thrust_N cannot be negative")
        return {"moment_Nm": None, "moment_kNm": None, "warnings": warns}
    if hub_height_m <= 0:
        warnings.warn(f"hub_height_m={hub_height_m} must be > 0", stacklevel=2)
        warns.append("hub_height_m must be > 0")
        return {"moment_Nm": None, "moment_kNm": None, "warnings": warns}

    M = thrust_N * hub_height_m
    return {
        "moment_Nm": M,
        "moment_kNm": M / 1000.0,
        "thrust_N": thrust_N,
        "hub_height_m": hub_height_m,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# AERODYNAMICS — Blade Element Momentum
# ---------------------------------------------------------------------------

def blade_element_momentum(
    tsr: float,
    n_blades: int = 3,
    chord_r_ratio: float = 0.06,
    twist_deg_list: list[float] | None = None,
    *,
    n_annuli: int = 20,
    a_init: float = 1.0 / 3.0,
    a_prime_init: float = 0.0,
    max_iter: int = 100,
    tol: float = 1e-6,
) -> dict[str, Any]:
    """
    Simplified Blade Element Momentum (BEM) theory — uniform chord & twist.

    Iterates axial induction factor a and tangential induction factor a′ for
    each annular ring.  Uses the simplified momentum equations without tip-loss
    or Glauert correction (a first-order engineering estimate).

    For each annulus at non-dimensional radius r̄ = r/R (from hub to tip):
      Local TSR  λr = tsr · r̄
      Inflow angle  φ = atan2(1 - a, λr · (1 + a′))
      Lift/drag neglected — uses pure momentum balance:
        a  = σ · Cl · cos(φ) / (4 · sin²(φ))     [simplified; Cl assumed 2π·α]
        a′ = σ · Cl · sin(φ) / (4 · sin(φ)·cos(φ))
      σ = n_blades · chord / (2π · r)  — local solidity

    Integrates  Cp = (8/tsr²) · Σ [ a′(1-a) · λr³ · Δr̄ ]

    Parameters
    ----------
    tsr           : design tip-speed ratio
    n_blades      : number of blades (default 3)
    chord_r_ratio : uniform chord-to-radius ratio c/R (default 0.06)
    twist_deg_list: list of twist angles (deg) per annulus (optional;
                    if None, a simple linear twist schedule is assumed)
    n_annuli      : number of BEM annuli (default 20)
    a_init        : initial axial induction guess (default 1/3)
    a_prime_init  : initial tangential induction guess (default 0)
    max_iter      : maximum iterations per annulus (default 100)
    tol           : convergence tolerance (default 1e-6)

    Returns
    -------
    dict with Cp, Ct, annuli (list of per-annulus dicts), warnings
    """
    warns: list[str] = []
    CP_MAX = 16.0 / 27.0

    if tsr <= 0:
        warnings.warn(f"tsr={tsr} must be > 0", stacklevel=2)
        warns.append("tsr must be > 0")
        return {"Cp": None, "Ct": None, "annuli": [], "warnings": warns}
    if n_blades < 1:
        warnings.warn(f"n_blades={n_blades} must be >= 1", stacklevel=2)
        warns.append("n_blades must be >= 1")
        return {"Cp": None, "Ct": None, "annuli": [], "warnings": warns}

    r_hub = 0.05  # non-dimensional hub radius (5% R)
    dr = (1.0 - r_hub) / n_annuli
    annuli_out: list[dict] = []

    Cp = 0.0
    Ct = 0.0

    for i in range(n_annuli):
        r_bar = r_hub + (i + 0.5) * dr
        lambda_r = tsr * r_bar
        # local chord / R
        c_R = chord_r_ratio
        sigma = n_blades * c_R / (2.0 * math.pi * r_bar)

        # linear twist schedule if not provided: 5°+15°*(1-r̄)
        if twist_deg_list is not None and i < len(twist_deg_list):
            twist_deg = twist_deg_list[i]
        else:
            twist_deg = 5.0 + 15.0 * (1.0 - r_bar)

        a = a_init
        a_prime = a_prime_init

        for _it in range(max_iter):
            # inflow angle
            phi = math.atan2(1.0 - a, lambda_r * (1.0 + a_prime))
            # local angle of attack (pitch + twist assumed optimised)
            alpha_rad = phi  # simplification: pitch set to inflow angle (zero alpha)
            Cl = 2.0 * math.pi * math.sin(alpha_rad)  # thin-aerofoil, no drag
            Cl = max(0.0, Cl)

            cos_phi = math.cos(phi)
            sin_phi = math.sin(phi)

            denom_a = (4.0 * sin_phi ** 2) + (sigma * Cl * cos_phi)
            if denom_a < 1e-12:
                a_new = 0.0
            else:
                a_new = sigma * Cl * cos_phi / denom_a

            denom_ap = (4.0 * sin_phi * cos_phi) - (sigma * Cl * sin_phi)
            if abs(denom_ap) < 1e-12:
                a_prime_new = 0.0
            else:
                a_prime_new = sigma * Cl * sin_phi / denom_ap

            # clamp induction to physically stable range
            a_new = max(0.0, min(0.5, a_new))
            a_prime_new = max(0.0, a_prime_new)

            if (abs(a_new - a) < tol) and (abs(a_prime_new - a_prime) < tol):
                a = a_new
                a_prime = a_prime_new
                break
            a = a_new
            a_prime = a_prime_new

        dCp = a_prime * (1.0 - a) * lambda_r ** 3 * dr
        dCt = 4.0 * a * (1.0 - a) * r_bar * dr
        Cp += dCp
        Ct += dCt

        annuli_out.append({
            "r_bar": round(r_bar, 4),
            "a": round(a, 6),
            "a_prime": round(a_prime, 6),
            "phi_deg": round(math.degrees(phi), 3),
            "dCp": round(dCp, 6),
        })

    Cp_integrated = (8.0 / tsr ** 2) * Cp
    Ct_integrated = (2.0 / 1.0) * Ct  # Ct = integral of 4a(1-a) dAr

    if Cp_integrated > CP_MAX:
        warnings.warn(
            f"BEM Cp={Cp_integrated:.4f} exceeds Betz limit {CP_MAX:.4f} — "
            "numerical artefact; check input parameters",
            stacklevel=2,
        )
        warns.append(f"BEM Cp={Cp_integrated:.4f} exceeds Betz limit — numerical issue")

    return {
        "Cp": round(Cp_integrated, 5),
        "Ct": round(Ct_integrated, 5),
        "tsr": tsr,
        "n_blades": n_blades,
        "n_annuli": n_annuli,
        "annuli": annuli_out,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# POWER CURVE
# ---------------------------------------------------------------------------

def power_curve(
    V_ms: float,
    V_cutin: float,
    V_rated: float,
    V_cutout: float,
    P_rated_W: float,
    *,
    Cp: float | None = None,
    rho: float | None = None,
    A: float | None = None,
) -> dict[str, Any]:
    """
    Power-curve model for a horizontal-axis wind turbine.

    Regions:
      V < V_cutin   → P = 0  (turbine parked)
      V_cutin ≤ V < V_rated  → P = P_rated × (V³ − V_cutin³) / (V_rated³ − V_cutin³)
                                  [cubic ramp; physically motivated by P ∝ V³]
      V_rated ≤ V ≤ V_cutout → P = P_rated  (pitch-regulated, constant power)
      V > V_cutout  → P = 0  (turbine furled / shut down)

    If Cp, rho, and A are all provided, the available-wind-power Betz check
    is also performed.

    Parameters
    ----------
    V_ms       : wind speed at hub height (m/s)
    V_cutin    : cut-in wind speed (m/s); typically 3–4 m/s
    V_rated    : rated wind speed (m/s); typically 11–15 m/s
    V_cutout   : cut-out wind speed (m/s); typically 20–25 m/s
    P_rated_W  : rated electrical power (W)

    Returns
    -------
    dict with power_W, power_kW, region ('below-cutin'/'ramp'/'rated'/'above-cutout'),
    capacity_factor_instant, warnings
    """
    warns: list[str] = []
    CP_MAX = 16.0 / 27.0

    if V_cutin < 0 or V_rated <= V_cutin or V_cutout <= V_rated:
        warnings.warn(
            f"Speed sequence invalid: V_cutin={V_cutin}, V_rated={V_rated}, "
            f"V_cutout={V_cutout}; expected 0 ≤ V_cutin < V_rated < V_cutout",
            stacklevel=2,
        )
        warns.append("invalid speed sequence: 0 ≤ V_cutin < V_rated < V_cutout required")

    if V_ms < 0:
        warnings.warn(f"V_ms={V_ms} cannot be negative; using 0", stacklevel=2)
        warns.append("negative wind speed set to 0")
        V_ms = 0.0

    if V_ms < V_cutin:
        region = "below-cutin"
        P = 0.0
        warns.append(f"V={V_ms:.2f} m/s below cut-in {V_cutin} m/s — turbine parked")
    elif V_ms < V_rated:
        region = "ramp"
        range_cube = V_rated ** 3 - V_cutin ** 3
        if range_cube < 1e-9:
            P = P_rated_W
        else:
            P = P_rated_W * (V_ms ** 3 - V_cutin ** 3) / range_cube
    elif V_ms <= V_cutout:
        region = "rated"
        P = P_rated_W
    else:
        region = "above-cutout"
        P = 0.0
        warns.append(f"V={V_ms:.2f} m/s above cut-out {V_cutout} m/s — turbine furled")

    # optional Betz check
    if Cp is not None and rho is not None and A is not None:
        P_avail = 0.5 * rho * A * max(V_ms, 0.0) ** 3
        if P_avail > 0 and P > 0:
            Cp_inst = P / P_avail
            if Cp_inst > CP_MAX:
                warnings.warn(
                    f"Implied Cp={Cp_inst:.4f} > Betz limit {CP_MAX:.4f}; "
                    "check P_rated_W, rho, or A",
                    stacklevel=2,
                )
                warns.append(f"implied Cp={Cp_inst:.4f} exceeds Betz limit")

    return {
        "power_W": P,
        "power_kW": P / 1000.0,
        "wind_speed_ms": V_ms,
        "region": region,
        "capacity_factor_instant": P / P_rated_W if P_rated_W > 0 else 0.0,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# WEIBULL / RAYLEIGH — AEP & CAPACITY FACTOR
# ---------------------------------------------------------------------------

def weibull_aep(
    k: float,
    c_ms: float,
    power_curve_dict: dict,
    *,
    hours_per_year: float = 8760.0,
) -> dict[str, Any]:
    """
    Annual energy production from Weibull wind-speed distribution.

    Integrates  AEP = T × ∫ P(v) · f(v) dv
    where f(v) is the Weibull PDF, numerically via midpoint rule over
    0–40 m/s in 0.1 m/s steps.

    Weibull PDF: f(v) = (k/c)·(v/c)^(k−1)·exp(−(v/c)^k)

    Parameters
    ----------
    k              : Weibull shape parameter (dimensionless); k≈2 for Rayleigh
    c_ms           : Weibull scale parameter (m/s); mean ≈ c·Γ(1+1/k)
    power_curve_dict : dict with keys:
                       V_cutin, V_rated, V_cutout, P_rated_W
                       (optional: Cp, rho, A — not used for AEP integration)
    hours_per_year : hours in a year (default 8760)

    Returns
    -------
    dict with aep_kWh, aep_MWh, mean_power_W, capacity_factor,
    weibull_mean_ms, warnings
    """
    warns: list[str] = []
    if k <= 0:
        warnings.warn(f"Weibull k={k} must be > 0", stacklevel=2)
        warns.append("k must be > 0")
        return {"aep_kWh": None, "warnings": warns}
    if c_ms <= 0:
        warnings.warn(f"Weibull c={c_ms} must be > 0", stacklevel=2)
        warns.append("c_ms must be > 0")
        return {"aep_kWh": None, "warnings": warns}

    V_cutin = power_curve_dict.get("V_cutin", 3.0)
    V_rated = power_curve_dict.get("V_rated", 12.0)
    V_cutout = power_curve_dict.get("V_cutout", 25.0)
    P_rated_W = power_curve_dict.get("P_rated_W", 1.0)

    # Numerical integration 0–40 m/s
    dv = 0.1
    v_values = [i * dv for i in range(1, int(40.0 / dv) + 1)]
    aep_W_h = 0.0

    for v in v_values:
        # Weibull PDF
        pdf = (k / c_ms) * (v / c_ms) ** (k - 1) * math.exp(-((v / c_ms) ** k))
        pc = power_curve(v, V_cutin, V_rated, V_cutout, P_rated_W)
        aep_W_h += pc["power_W"] * pdf * dv

    mean_power = aep_W_h  # mean power = integral of P(v)·f(v)dv (W)
    aep_kWh = mean_power * hours_per_year / 1000.0
    cf = mean_power / P_rated_W if P_rated_W > 0 else 0.0

    # Weibull mean wind speed: v̄ = c·Γ(1+1/k) via math.gamma
    weibull_mean = c_ms * math.gamma(1.0 + 1.0 / k)

    if cf < 0.20:
        warnings.warn(
            f"Capacity factor {cf:.3f} < 0.20 — low-wind site or oversized turbine; "
            "consider a lower rated power or higher-wind location",
            stacklevel=2,
        )
        warns.append(f"low capacity factor {cf:.3f} — site wind resource may be insufficient")

    return {
        "aep_kWh": round(aep_kWh, 1),
        "aep_MWh": round(aep_kWh / 1000.0, 3),
        "mean_power_W": round(mean_power, 1),
        "capacity_factor": round(cf, 4),
        "weibull_mean_ms": round(weibull_mean, 3),
        "k": k,
        "c_ms": c_ms,
        "hours_per_year": hours_per_year,
        "warnings": warns,
    }


def rayleigh_aep(
    v_mean_ms: float,
    power_curve_dict: dict,
    *,
    hours_per_year: float = 8760.0,
) -> dict[str, Any]:
    """
    Annual energy production using Rayleigh wind distribution.

    Rayleigh is Weibull with k=2; scale parameter c = 2·v_mean / √π.

    Parameters
    ----------
    v_mean_ms        : mean wind speed at hub height (m/s)
    power_curve_dict : same structure as weibull_aep
    hours_per_year   : default 8760

    Returns
    -------
    Same dict as weibull_aep with additional rayleigh_c_ms key.
    """
    warns: list[str] = []
    if v_mean_ms <= 0:
        warnings.warn(f"v_mean_ms={v_mean_ms} must be > 0", stacklevel=2)
        warns.append("v_mean_ms must be > 0")
        return {"aep_kWh": None, "warnings": warns}

    # Rayleigh: k=2, c = 2·v_mean/√π
    c = 2.0 * v_mean_ms / math.sqrt(math.pi)
    result = weibull_aep(2.0, c, power_curve_dict, hours_per_year=hours_per_year)
    result["rayleigh_c_ms"] = round(c, 4)
    result["v_mean_ms"] = v_mean_ms
    return result


def capacity_factor(
    aep_kWh: float,
    P_rated_W: float,
    *,
    hours_per_year: float = 8760.0,
) -> dict[str, Any]:
    """
    Capacity factor from annual energy production and rated power.

    CF = AEP / (P_rated × T)  [dimensionless, 0–1]

    Typical values:
      onshore wind  : 0.25–0.40
      offshore wind : 0.35–0.55

    Parameters
    ----------
    aep_kWh        : annual energy production (kWh)
    P_rated_W      : rated turbine power (W)
    hours_per_year : hours per year (default 8760)
    """
    warns: list[str] = []
    if aep_kWh < 0:
        warnings.warn(f"aep_kWh={aep_kWh} cannot be negative", stacklevel=2)
        warns.append("aep_kWh cannot be negative")
        return {"capacity_factor": None, "warnings": warns}
    if P_rated_W <= 0:
        warnings.warn(f"P_rated_W={P_rated_W} must be > 0", stacklevel=2)
        warns.append("P_rated_W must be > 0")
        return {"capacity_factor": None, "warnings": warns}

    full_load_kWh = P_rated_W / 1000.0 * hours_per_year
    cf = aep_kWh / full_load_kWh

    if cf < 0.20:
        warnings.warn(
            f"Capacity factor {cf:.3f} < 0.20 — low-wind site or oversized turbine",
            stacklevel=2,
        )
        warns.append(f"low capacity factor {cf:.3f}")
    if cf > 1.0:
        warnings.warn(
            f"Capacity factor {cf:.3f} > 1.0 — physically impossible; check AEP input",
            stacklevel=2,
        )
        warns.append(f"capacity factor {cf:.3f} > 1.0 — impossible")

    return {
        "capacity_factor": round(cf, 5),
        "capacity_factor_percent": round(cf * 100, 3),
        "aep_kWh": aep_kWh,
        "P_rated_W": P_rated_W,
        "hours_per_year": hours_per_year,
        "full_load_kWh": round(full_load_kWh, 1),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# WAKE MODEL — Jensen
# ---------------------------------------------------------------------------

def jensen_wake(
    u0_ms: float,
    Ct: float,
    x_m: float,
    D_m: float,
    *,
    k_w: float = 0.04,
) -> dict[str, Any]:
    """
    Jensen (1983) single-wake velocity deficit model.

    Wake radius:    r_w(x) = R + k_w · x   (linear expansion)
    Velocity ratio: u/u0 = 1 − (1 − √(1 − Ct)) · (D / (D + 2·k_w·x))²

    Typical k_w values:
      onshore  : 0.04–0.06
      offshore : 0.02–0.04

    Parameters
    ----------
    u0_ms : free-stream wind speed (m/s)
    Ct    : turbine thrust coefficient (dimensionless)
    x_m   : downstream distance from rotor plane (m)
    D_m   : rotor diameter (m)
    k_w   : wake decay constant (default 0.04)

    Returns
    -------
    dict with u_wake_ms, deficit_fraction, deficit_percent, warnings
    """
    warns: list[str] = []
    if u0_ms <= 0:
        warnings.warn(f"u0_ms={u0_ms} must be > 0", stacklevel=2)
        warns.append("u0_ms must be > 0")
        return {"u_wake_ms": None, "warnings": warns}
    if Ct <= 0 or Ct > 1.0:
        warnings.warn(f"Ct={Ct} outside (0, 1]", stacklevel=2)
        warns.append(f"Ct={Ct} out of range (0, 1]")
        return {"u_wake_ms": None, "warnings": warns}
    if x_m < 0:
        warnings.warn(f"x_m={x_m} cannot be negative; using 0", stacklevel=2)
        warns.append("x_m set to 0")
        x_m = 0.0
    if D_m <= 0:
        warnings.warn(f"D_m={D_m} must be > 0", stacklevel=2)
        warns.append("D_m must be > 0")
        return {"u_wake_ms": None, "warnings": warns}

    # Jensen wake equation
    deficit_factor = (1.0 - math.sqrt(1.0 - Ct)) * (D_m / (D_m + 2.0 * k_w * x_m)) ** 2
    u_wake = u0_ms * (1.0 - deficit_factor)
    deficit_frac = 1.0 - u_wake / u0_ms
    # power loss ∝ (u_wake/u0)³
    power_ratio = (u_wake / u0_ms) ** 3

    return {
        "u_wake_ms": round(u_wake, 4),
        "u0_ms": u0_ms,
        "deficit_fraction": round(deficit_frac, 5),
        "deficit_percent": round(deficit_frac * 100, 3),
        "power_ratio": round(power_ratio, 5),
        "x_over_D": round(x_m / D_m, 2) if D_m > 0 else None,
        "k_w": k_w,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# NOISE
# ---------------------------------------------------------------------------

def sound_pressure_distance(
    Lw_dB: float,
    distance_m: float,
) -> dict[str, Any]:
    """
    Sound pressure level (SPL) at a distance from a wind turbine.

    Hemispherical propagation over a reflecting ground (one image source):
      SPL = Lw − 10·log10(2π·r²)  [dB]

    This is a simplified free-field model per ISO 9613-2 (no atmospheric
    attenuation, no ground effect, no shielding).  Full engineering noise
    assessment requires detailed octave-band calculations.

    Note: Tower-shadow also produces infrasound pulsations (< 20 Hz) at the
    blade passage frequency — below most noise regulations but may affect
    some sensitive receptors.  IEC 61400-11 is the measurement standard.

    Parameters
    ----------
    Lw_dB      : turbine A-weighted sound power level (dB(A))
    distance_m : horizontal distance from turbine base (m)

    Returns
    -------
    dict with spl_dBA, distance_m, warnings
    """
    warns: list[str] = []
    if distance_m <= 0:
        warnings.warn(f"distance_m={distance_m} must be > 0", stacklevel=2)
        warns.append("distance_m must be > 0")
        return {"spl_dBA": None, "warnings": warns}
    if distance_m < 50:
        warnings.warn(
            f"distance_m={distance_m} m is very close; near-field model invalid",
            stacklevel=2,
        )
        warns.append(f"distance {distance_m} m < 50 m — near-field; model unreliable")

    spl = Lw_dB - 10.0 * math.log10(2.0 * math.pi * distance_m ** 2)
    return {
        "spl_dBA": round(spl, 2),
        "Lw_dB": Lw_dB,
        "distance_m": distance_m,
        "note": (
            "Simplified hemispherical model. Real SPL depends on terrain, "
            "atmospheric stability, and turbine operating mode. "
            "IEC 61400-11 measurement standard applies."
        ),
        "warnings": warns,
    }
