"""
kerf_cad_core.solarpv.sizing — pure-Python photovoltaic system sizing formulas.

All functions are self-contained (math only, stdlib only).  No OCC dependency.
Warnings are issued via the standard ``warnings`` module; functions never raise
on domain errors — they return ``{"warnings": [...]}`` keys instead.

Implements
----------
SOLAR GEOMETRY
  solar_declination(day_of_year)
      Spencer (1971) declination δ (degrees) for day-of-year n (1–365).

  equation_of_time(day_of_year)
      Equation of time E (minutes) via Spencer approximation.

  solar_hour_angle(solar_time_h)
      Hour angle ω (degrees) from solar time (hours, 0–24).

  solar_position(latitude_deg, day_of_year, solar_time_h)
      Solar altitude α and azimuth γ_s (degrees from south, + east).

  sunrise_sunset(latitude_deg, day_of_year)
      Sunrise and sunset solar hour angles ω_s (degrees); also clock time
      from solar noon as hours.

  day_length(latitude_deg, day_of_year)
      Day length in hours (time between sunrise and sunset).

PLANE-OF-ARRAY IRRADIANCE
  poa_irradiance(ghi, dni, dhi, tilt_deg, azimuth_deg, solar_altitude_deg,
                 solar_azimuth_deg, *, albedo)
      Isotropic-sky (Liu & Jordan) transposition model.
      Returns beam, diffuse-sky, reflected, and total POA irradiance (W/m²).

  optimal_tilt(latitude_deg)
      Rule-of-thumb optimal fixed-tilt angle (degrees) for maximum annual
      energy yield — commonly |latitude| ± 0-15° depending on climate.
      Returns tilt and a confidence note.

ARRAY & MODULE SIZING
  array_size(daily_load_kWh, peak_sun_hours, derate_pr, *, safety_factor)
      Required DC array peak power (kWp) from daily load, peak-sun-hours, and
      performance ratio.

  module_string_sizing(modules, inverter, *, t_min_c, t_max_c, t_stc_c)
      String sizing: modules in series constrained by inverter max DC input
      voltage (Voc temperature rise) and MPPT window (Vmp); modules in
      parallel from target current vs Isc.
      Flags string-overvoltage in warnings.

  inverter_dc_ac_ratio(array_kWp, inverter_kVAc, *, min_ratio, max_ratio)
      Checks DC/AC clipping ratio; flags under- or over-sizing in warnings.

BATTERY BANK (off-grid)
  battery_bank(daily_load_kWh, autonomy_days, dod_fraction, system_voltage_v,
               *, efficiency, safety_factor)
      Required battery bank: Ah, kWh usable, number of cells in series/
      parallel for a given cell Ah capacity.
      Flags undersized bank (autonomy < 1 day or DoD > 0.8) in warnings.

CABLE SIZING
  cable_sizing(current_a, length_m, voltage_v, max_drop_pct, *, resistivity,
               temperature_c)
      Minimum cable cross-section (mm²) for a DC run at given %voltage-drop.
      Flags excess-drop condition in warnings.

ENERGY YIELD & PERFORMANCE
  energy_yield(array_kWp, poa_annual_kWh_m2, pr, *, degradation_rate,
               years)
      Annual and lifetime energy yield (kWh), specific yield (kWh/kWp),
      performance ratio PR.

ROW SPACING / SHADING
  row_spacing(module_length_m, tilt_deg, latitude_deg, *, gcr, winter_margin_h)
      Minimum row pitch and ground-cover ratio (GCR) for no inter-row shading
      at a given minimum solar elevation (based on worst-case winter sun angle).

References
----------
Duffie, J.A. & Beckman, W.A., "Solar Engineering of Thermal Processes", 4th ed.
Liu, B.Y.H. & Jordan, R.C. (1963) — The long-term average performance of flat-
  plate solar energy collectors.
Spencer, J.W. (1971) — Fourier series representation of the position of the sun.
IEC 60364-5-52 — Electrical installations of buildings — Selection and erection.

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import Any


# ---------------------------------------------------------------------------
# SOLAR GEOMETRY
# ---------------------------------------------------------------------------

def solar_declination(day_of_year: int) -> float:
    """Return solar declination δ (degrees) for day-of-year n (1–365).

    Uses the Spencer (1971) Fourier approximation.  Accuracy ~ ±0.01°.

    Parameters
    ----------
    day_of_year : int
        Julian day number (1 = 1 Jan, 365 = 31 Dec).

    Returns
    -------
    float
        Declination in degrees.  Range ≈ −23.45° to +23.45°.
    """
    B = 2 * math.pi * (day_of_year - 1) / 365.0
    delta_rad = (
        0.006918
        - 0.399912 * math.cos(B)
        + 0.070257 * math.sin(B)
        - 0.006758 * math.cos(2 * B)
        + 0.000907 * math.sin(2 * B)
        - 0.002697 * math.cos(3 * B)
        + 0.00148  * math.sin(3 * B)
    )
    return math.degrees(delta_rad)


def equation_of_time(day_of_year: int) -> float:
    """Return the Equation of Time E (minutes) for day-of-year n.

    Uses Spencer (1971) approximation.

    Parameters
    ----------
    day_of_year : int

    Returns
    -------
    float
        E in minutes (positive → solar noon before clock noon).
    """
    B = 2 * math.pi * (day_of_year - 1) / 365.0
    E_min = 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)
    return E_min


def solar_hour_angle(solar_time_h: float) -> float:
    """Return the hour angle ω (degrees) from solar time.

    ω = 0 at solar noon, positive in the afternoon, negative in the morning.
    Solar noon corresponds to solar_time_h = 12.0.

    Parameters
    ----------
    solar_time_h : float
        Solar (apparent) time in decimal hours (0–24).

    Returns
    -------
    float
        Hour angle in degrees.
    """
    return 15.0 * (solar_time_h - 12.0)


def solar_position(
    latitude_deg: float,
    day_of_year: int,
    solar_time_h: float,
) -> dict[str, float]:
    """Return solar altitude α and azimuth γ_s for a given location and time.

    Uses spherical trigonometry (Duffie & Beckman §1.6).

    Parameters
    ----------
    latitude_deg : float
        Site latitude (degrees, + north, − south).  Range −90 to +90.
    day_of_year : int
        Julian day (1–365).
    solar_time_h : float
        Solar time (decimal hours, 0–24).

    Returns
    -------
    dict with keys:
      altitude_deg  : float — solar altitude (degrees above horizon, 0–90).
      azimuth_deg   : float — solar azimuth (degrees from south, + east,
                              − west).  Range −180 to +180.
      zenith_deg    : float — solar zenith angle (90 − altitude).
    """
    phi = math.radians(latitude_deg)
    delta = math.radians(solar_declination(day_of_year))
    omega = math.radians(solar_hour_angle(solar_time_h))

    # Altitude
    sin_alpha = (
        math.sin(phi) * math.sin(delta)
        + math.cos(phi) * math.cos(delta) * math.cos(omega)
    )
    sin_alpha = max(-1.0, min(1.0, sin_alpha))
    alpha = math.degrees(math.asin(sin_alpha))

    # Azimuth (from south, positive east)
    # When the sun is near zenith (altitude close to 90°), azimuth is ill-defined;
    # use a 1e-3 threshold on cos_alpha to avoid division instability.
    cos_alpha = math.cos(math.radians(alpha))
    if cos_alpha < 0.01:  # altitude > ~89.4° — sun effectively at zenith, azimuth undefined
        gamma_s = 0.0
    else:
        cos_phi = math.cos(phi)
        if cos_phi < 1e-9:  # pole — azimuth undefined
            gamma_s = 0.0
        else:
            cos_gamma_s = (
                math.sin(delta) - math.sin(phi) * sin_alpha
            ) / (cos_phi * cos_alpha)
            cos_gamma_s = max(-1.0, min(1.0, cos_gamma_s))
            gamma_s = math.degrees(math.acos(cos_gamma_s))
            if omega > 0:  # afternoon → positive (east of south is negative by convention)
                gamma_s = -gamma_s

    zenith = 90.0 - alpha

    return {
        "altitude_deg": round(alpha, 6),
        "azimuth_deg": round(gamma_s, 6),
        "zenith_deg": round(zenith, 6),
    }


def sunrise_sunset(
    latitude_deg: float,
    day_of_year: int,
) -> dict[str, float]:
    """Return sunrise and sunset hour angles and times relative to solar noon.

    Parameters
    ----------
    latitude_deg : float
        Site latitude (degrees, + north).
    day_of_year : int
        Julian day (1–365).

    Returns
    -------
    dict with keys:
      omega_sunrise_deg   : float — sunrise hour angle (negative, degrees).
      omega_sunset_deg    : float — sunset hour angle (positive, degrees).
      sunrise_solar_h     : float — sunrise solar time (hours from midnight).
      sunset_solar_h      : float — sunset solar time (hours from midnight).
      day_length_h        : float — day length (hours).
    """
    phi = math.radians(latitude_deg)
    delta = math.radians(solar_declination(day_of_year))

    cos_omega_s = -math.tan(phi) * math.tan(delta)
    # Clamp for polar day/night
    cos_omega_s = max(-1.0, min(1.0, cos_omega_s))
    omega_s = math.degrees(math.acos(cos_omega_s))

    sunrise_h = 12.0 - omega_s / 15.0
    sunset_h  = 12.0 + omega_s / 15.0
    dl = 2 * omega_s / 15.0

    return {
        "omega_sunrise_deg": round(-omega_s, 6),
        "omega_sunset_deg":  round( omega_s, 6),
        "sunrise_solar_h":   round(sunrise_h, 6),
        "sunset_solar_h":    round(sunset_h,  6),
        "day_length_h":      round(dl, 6),
    }


def day_length(latitude_deg: float, day_of_year: int) -> float:
    """Return day length (hours) for given latitude and day-of-year."""
    return sunrise_sunset(latitude_deg, day_of_year)["day_length_h"]


# ---------------------------------------------------------------------------
# PLANE-OF-ARRAY IRRADIANCE
# ---------------------------------------------------------------------------

def poa_irradiance(
    ghi: float,
    dni: float,
    dhi: float,
    tilt_deg: float,
    azimuth_deg: float,
    solar_altitude_deg: float,
    solar_azimuth_deg: float,
    *,
    albedo: float = 0.2,
) -> dict[str, float]:
    """Isotropic-sky transposition: GHI/DNI/DHI → plane-of-array irradiance.

    Uses the Liu & Jordan (1963) isotropic diffuse model.

    Parameters
    ----------
    ghi : float
        Global horizontal irradiance (W/m²). Must be >= 0.
    dni : float
        Direct normal irradiance (W/m²). Must be >= 0.
    dhi : float
        Diffuse horizontal irradiance (W/m²). Must be >= 0.
    tilt_deg : float
        Collector tilt from horizontal (degrees, 0 = horizontal, 90 = vertical).
    azimuth_deg : float
        Collector azimuth from south (degrees, + east, − west).
    solar_altitude_deg : float
        Solar altitude above horizon (degrees).
    solar_azimuth_deg : float
        Solar azimuth from south (degrees, + east, − west).
    albedo : float
        Ground reflectance (default 0.2 = grass/soil).

    Returns
    -------
    dict with keys:
      beam_W_m2     : float — beam (direct) component on POA.
      diffuse_W_m2  : float — isotropic sky diffuse component on POA.
      reflected_W_m2: float — ground-reflected component on POA.
      total_W_m2    : float — total POA irradiance (W/m²).
    """
    beta = math.radians(tilt_deg)
    gamma = math.radians(azimuth_deg)
    alpha = math.radians(solar_altitude_deg)
    gamma_s = math.radians(solar_azimuth_deg)

    cos_theta_z = math.sin(alpha)  # = cos(zenith)
    cos_theta_z = max(1e-9, cos_theta_z)

    # Angle of incidence on tilted plane
    cos_theta_i = (
        math.sin(alpha) * math.cos(beta)
        + math.cos(alpha) * math.sin(beta) * math.cos(gamma_s - gamma)
    )
    cos_theta_i = max(0.0, cos_theta_i)

    # Geometric factor R_b = cos(θ_i) / cos(θ_z)
    R_b = cos_theta_i / cos_theta_z

    beam_poa = max(0.0, dni * cos_theta_i)

    # Isotropic sky diffuse
    diffuse_poa = dhi * (1 + math.cos(beta)) / 2.0

    # Ground reflected
    reflected_poa = ghi * albedo * (1 - math.cos(beta)) / 2.0

    total = beam_poa + diffuse_poa + reflected_poa

    return {
        "beam_W_m2":      round(beam_poa, 4),
        "diffuse_W_m2":   round(diffuse_poa, 4),
        "reflected_W_m2": round(reflected_poa, 4),
        "total_W_m2":     round(total, 4),
        "R_b":            round(R_b, 6),
    }


def optimal_tilt(latitude_deg: float) -> dict[str, Any]:
    """Return rule-of-thumb optimal fixed tilt angle for annual energy yield.

    For southern hemisphere, latitude is negative; tilt is always positive
    (modules face north).

    Rule (common engineering heuristic):
      - Equatorial sites (|lat| < 15°): tilt ≈ |lat| + 5°
      - Mid-latitudes (15–45°)        : tilt ≈ |lat|
      - High latitudes (> 45°)        : tilt ≈ |lat| − 5° to keep winter gain

    Parameters
    ----------
    latitude_deg : float
        Site latitude (degrees, + north, − south).

    Returns
    -------
    dict with keys:
      tilt_deg     : float — recommended tilt (degrees from horizontal).
      faces        : str   — 'south' (north hemisphere) or 'north' (south).
      note         : str   — confidence note.
    """
    abs_lat = abs(latitude_deg)
    if abs_lat < 15.0:
        tilt = abs_lat + 5.0
        note = "Low-latitude site: tilt set to |lat|+5° to boost diffuse capture"
    elif abs_lat <= 45.0:
        tilt = abs_lat
        note = "Mid-latitude site: tilt matched to |latitude|"
    else:
        tilt = max(abs_lat - 5.0, 0.0)
        note = "High-latitude site: tilt reduced 5° below |latitude| to retain winter gain"

    faces = "south" if latitude_deg >= 0 else "north"
    return {
        "tilt_deg": round(tilt, 2),
        "faces": faces,
        "note": note,
    }


# ---------------------------------------------------------------------------
# ARRAY SIZE FROM LOAD
# ---------------------------------------------------------------------------

def array_size(
    daily_load_kWh: float,
    peak_sun_hours: float,
    derate_pr: float,
    *,
    safety_factor: float = 1.25,
) -> dict[str, Any]:
    """Required DC array peak power from daily energy load.

    Formula:
        P_kWp = (daily_load_kWh / peak_sun_hours / derate_pr) * safety_factor

    Parameters
    ----------
    daily_load_kWh : float
        Daily energy consumption (kWh/day). Must be > 0.
    peak_sun_hours : float
        Peak sun hours (PSH) at the site (h/day).  Equivalent to daily in-plane
        irradiation in kWh/m².  Must be > 0.
    derate_pr : float
        System performance ratio (PR), accounting for losses (soiling, wiring,
        inverter, temperature, etc.).  Typical 0.70–0.85.  Must be in (0, 1].
    safety_factor : float
        Additional array oversize factor (default 1.25).  Must be >= 1.

    Returns
    -------
    dict with keys:
      array_kWp          : float — required DC peak power (kWp).
      daily_load_kWh     : float
      peak_sun_hours     : float
      derate_pr          : float
      safety_factor      : float
      warnings           : list[str]
    """
    warns: list[str] = []
    if daily_load_kWh <= 0:
        warns.append("daily_load_kWh must be > 0; result may be invalid")
    if peak_sun_hours <= 0:
        warns.append("peak_sun_hours must be > 0; result may be invalid")
    if not (0 < derate_pr <= 1.0):
        warns.append("derate_pr should be in (0, 1]; result may be invalid")
    if safety_factor < 1.0:
        warns.append("safety_factor < 1.0 is unusual; check intent")

    denom = peak_sun_hours * derate_pr
    if denom <= 0:
        denom = 1e-9
    array_kWp = (daily_load_kWh / denom) * safety_factor

    for w in warns:
        warnings.warn(w, stacklevel=2)

    return {
        "array_kWp":      round(array_kWp, 4),
        "daily_load_kWh": daily_load_kWh,
        "peak_sun_hours": peak_sun_hours,
        "derate_pr":      derate_pr,
        "safety_factor":  safety_factor,
        "warnings":       warns,
    }


# ---------------------------------------------------------------------------
# MODULE STRING SIZING
# ---------------------------------------------------------------------------

def module_string_sizing(
    modules: dict[str, float],
    inverter: dict[str, float],
    *,
    t_min_c: float = -10.0,
    t_max_c: float = 70.0,
    t_stc_c: float = 25.0,
) -> dict[str, Any]:
    """String sizing: modules in series / parallel given inverter limits.

    Temperature correction for open-circuit voltage:
        Voc(T) = Voc_stc * (1 + (T - T_stc) * beta_Voc)

    At T_min (coldest, highest Voc) the string must not exceed inverter
    max DC input voltage.  At T_max (hottest, lowest Vmp) the string Vmp
    must remain within the inverter MPPT range.

    Parameters
    ----------
    modules : dict with keys:
        voc_v       : float — open-circuit voltage at STC (V)
        vmp_v       : float — max-power voltage at STC (V)
        isc_a       : float — short-circuit current at STC (A)
        imp_a       : float — max-power current at STC (A)
        pmax_w      : float — peak power at STC (W)
        beta_voc    : float — Voc temperature coefficient (1/°C, typically
                              negative, e.g. −0.003)
        gamma_pmax  : float — Pmax temperature coefficient (1/°C, e.g. −0.004)
    inverter : dict with keys:
        vdc_max_v   : float — max DC input voltage (V)
        mppt_vmin_v : float — MPPT minimum voltage (V)
        mppt_vmax_v : float — MPPT maximum voltage (V)
        idc_max_a   : float — max DC input current per MPPT (A)

    t_min_c : float
        Minimum expected ambient temperature (°C). Default −10°C.
    t_max_c : float
        Maximum expected module (cell) temperature (°C). Default 70°C.
    t_stc_c : float
        STC temperature (°C). Default 25°C.

    Returns
    -------
    dict with keys:
      modules_per_string      : int — max safe modules in series
      strings_in_parallel     : int — strings in parallel for target Idc
      string_voc_cold_v       : float — string Voc at T_min
      string_vmp_hot_v        : float — string Vmp at T_max
      string_isc_a            : float — string short-circuit current (1 string)
      total_modules           : int
      total_kWp               : float
      warnings                : list[str]
    """
    warns: list[str] = []

    voc_stc   = modules["voc_v"]
    vmp_stc   = modules["vmp_v"]
    isc_stc   = modules["isc_a"]
    imp_stc   = modules["imp_a"]
    pmax_w    = modules["pmax_w"]
    beta_voc  = modules["beta_voc"]

    inv_vdc_max  = inverter["vdc_max_v"]
    inv_mppt_min = inverter["mppt_vmin_v"]
    inv_mppt_max = inverter["mppt_vmax_v"]
    inv_idc_max  = inverter["idc_max_a"]

    # Corrected Voc at T_min (highest)
    voc_cold = voc_stc * (1 + beta_voc * (t_min_c - t_stc_c))
    # Corrected Vmp at T_max (lowest)
    vmp_hot  = vmp_stc * (1 + beta_voc * (t_max_c - t_stc_c))

    # Max modules in series limited by Voc_cold ≤ inv_vdc_max
    if voc_cold <= 0:
        max_series_voc = 1
        warns.append("Calculated voc_cold <= 0; check beta_voc sign/magnitude")
    else:
        max_series_voc = int(inv_vdc_max / voc_cold)

    # Min modules for Vmp_hot to reach MPPT minimum
    if vmp_hot <= 0:
        min_series_mppt = 1
        warns.append("Calculated vmp_hot <= 0; check beta_voc sign/magnitude")
    else:
        min_series_mppt = math.ceil(inv_mppt_min / vmp_hot)

    # Max modules so Vmp_hot ≤ MPPT max
    if vmp_hot <= 0:
        max_series_mppt = max_series_voc
    else:
        max_series_mppt = int(inv_mppt_max / vmp_hot)

    # Choose series count: max feasible
    modules_per_string = min(max_series_voc, max_series_mppt)
    if modules_per_string < min_series_mppt:
        warns.append(
            f"No valid series count: min_series_mppt={min_series_mppt} > "
            f"max feasible={modules_per_string}. Check inverter MPPT range."
        )
        modules_per_string = max(modules_per_string, 1)

    # String voltages
    string_voc_cold = modules_per_string * voc_cold
    string_vmp_hot  = modules_per_string * vmp_hot

    if string_voc_cold > inv_vdc_max:
        warns.append(
            f"STRING OVERVOLTAGE: string Voc at {t_min_c}°C = "
            f"{string_voc_cold:.1f} V exceeds inverter max {inv_vdc_max} V"
        )

    # Strings in parallel: limited by inv_idc_max / Isc per string
    strings_parallel = max(1, int(inv_idc_max / isc_stc))
    string_isc = isc_stc  # per string (parallel = 1)

    total_modules = modules_per_string * strings_parallel
    total_kWp = total_modules * pmax_w / 1000.0

    for w in warns:
        warnings.warn(w, stacklevel=2)

    return {
        "modules_per_string":   modules_per_string,
        "strings_in_parallel":  strings_parallel,
        "string_voc_cold_v":    round(string_voc_cold, 2),
        "string_vmp_hot_v":     round(string_vmp_hot, 2),
        "string_isc_a":         round(string_isc, 3),
        "total_modules":        total_modules,
        "total_kWp":            round(total_kWp, 3),
        "warnings":             warns,
    }


# ---------------------------------------------------------------------------
# INVERTER DC/AC RATIO
# ---------------------------------------------------------------------------

def inverter_dc_ac_ratio(
    array_kWp: float,
    inverter_kVAc: float,
    *,
    min_ratio: float = 1.0,
    max_ratio: float = 1.35,
) -> dict[str, Any]:
    """Check the DC/AC ratio (clipping ratio) of a PV system.

    Parameters
    ----------
    array_kWp : float
        DC peak power of the array (kWp).
    inverter_kVAc : float
        Inverter nominal AC output power (kVAc or kWac).
    min_ratio : float
        Minimum acceptable DC/AC ratio (default 1.0).
    max_ratio : float
        Maximum acceptable DC/AC ratio before significant clipping (default 1.35).

    Returns
    -------
    dict with keys:
      dc_ac_ratio  : float
      status       : str  — 'ok', 'undersized', or 'oversized'
      warnings     : list[str]
    """
    warns: list[str] = []
    if inverter_kVAc <= 0:
        warns.append("inverter_kVAc must be > 0")
        ratio = float("nan")
        status = "invalid"
    else:
        ratio = array_kWp / inverter_kVAc
        if ratio < min_ratio:
            status = "undersized"
            warns.append(
                f"DC/AC ratio {ratio:.3f} < {min_ratio}: inverter may be "
                "oversized; lower yield during low-irradiance periods"
            )
        elif ratio > max_ratio:
            status = "oversized"
            warns.append(
                f"DC/AC ratio {ratio:.3f} > {max_ratio}: significant AC "
                "clipping expected; review inverter sizing"
            )
        else:
            status = "ok"

    for w in warns:
        warnings.warn(w, stacklevel=2)

    return {
        "dc_ac_ratio": round(ratio, 4) if not math.isnan(ratio) else ratio,
        "status":      status,
        "warnings":    warns,
    }


# ---------------------------------------------------------------------------
# OFF-GRID BATTERY BANK
# ---------------------------------------------------------------------------

def battery_bank(
    daily_load_kWh: float,
    autonomy_days: float,
    dod_fraction: float,
    system_voltage_v: float,
    *,
    cell_ah: float = 100.0,
    efficiency: float = 0.85,
    safety_factor: float = 1.1,
) -> dict[str, Any]:
    """Size an off-grid battery bank for given autonomy and depth-of-discharge.

    Parameters
    ----------
    daily_load_kWh : float
        Daily energy consumption (kWh/day).
    autonomy_days : float
        Number of days of autonomy (no solar charging).  Typically 1–5 days.
    dod_fraction : float
        Maximum allowable depth of discharge (0–1).  Lead-acid 0.5, Li-ion 0.8.
    system_voltage_v : float
        Nominal DC system voltage (V). Typical: 12, 24, 48 V.
    cell_ah : float
        Individual battery/cell nominal capacity (Ah). Default 100 Ah.
    efficiency : float
        Round-trip battery efficiency (default 0.85).
    safety_factor : float
        Oversize factor (default 1.1).

    Returns
    -------
    dict with keys:
      total_kWh_required    : float — gross energy required (kWh)
      usable_kWh            : float — usable energy (after DoD)
      bank_ah               : float — required bank capacity (Ah at system V)
      strings_series        : int   — always 1 (cells in series for system V,
                                      depends on cell nominal V; assumed 12 V
                                      nominal cell)
      parallel_strings      : int   — parallel strings of cells
      total_cells           : int
      warnings              : list[str]
    """
    warns: list[str] = []

    if autonomy_days < 1:
        warns.append(
            f"autonomy_days={autonomy_days} < 1: battery bank may be undersized "
            "for typical off-grid applications"
        )
    if dod_fraction > 0.8:
        warns.append(
            f"dod_fraction={dod_fraction} > 0.8: exceeds recommended maximum DoD "
            "for most battery chemistries; may reduce cycle life"
        )
    if dod_fraction <= 0:
        warns.append("dod_fraction must be > 0; defaulting to 0.5")
        dod_fraction = 0.5

    # Energy the bank must supply (accounting for efficiency losses on discharge)
    energy_needed = daily_load_kWh * autonomy_days / efficiency * safety_factor

    # Gross (nameplate) bank capacity = energy / DoD
    gross_kWh = energy_needed / dod_fraction

    # Bank capacity in Ah at system voltage
    bank_ah = gross_kWh * 1000.0 / system_voltage_v

    # Assume 12 V nominal cell; cells in series for system voltage
    cell_v_nominal = 12.0
    cells_series = max(1, round(system_voltage_v / cell_v_nominal))
    parallel_strings = math.ceil(bank_ah / cell_ah)
    total_cells = cells_series * parallel_strings

    usable_kWh = gross_kWh * dod_fraction

    for w in warns:
        warnings.warn(w, stacklevel=2)

    return {
        "total_kWh_required": round(gross_kWh, 3),
        "usable_kWh":         round(usable_kWh, 3),
        "bank_ah":            round(bank_ah, 2),
        "cells_in_series":    cells_series,
        "parallel_strings":   parallel_strings,
        "total_cells":        total_cells,
        "autonomy_days":      autonomy_days,
        "dod_fraction":       dod_fraction,
        "warnings":           warns,
    }


# ---------------------------------------------------------------------------
# CABLE SIZING
# ---------------------------------------------------------------------------

def cable_sizing(
    current_a: float,
    length_m: float,
    voltage_v: float,
    max_drop_pct: float,
    *,
    resistivity: float = 1.72e-8,
    temperature_c: float = 75.0,
) -> dict[str, Any]:
    """Minimum cable cross-section for a DC run at given %voltage-drop.

    Uses Ohm's law for a two-conductor DC circuit (round-trip length = 2×L):
        A_mm2 = (2 × L × I × ρ) / (V × drop_fraction)

    Temperature correction for copper resistivity:
        ρ(T) = ρ_20 × (1 + 0.00393 × (T − 20))

    Parameters
    ----------
    current_a : float
        Design current (A). Must be > 0.
    length_m : float
        One-way cable run length (m). Must be > 0.
    voltage_v : float
        DC system voltage (V). Must be > 0.
    max_drop_pct : float
        Maximum allowable voltage drop (%). Typical 1–3% for PV strings.
    resistivity : float
        Conductor resistivity at 20°C (Ω·m). Default 1.72e-8 (annealed copper).
    temperature_c : float
        Maximum conductor operating temperature (°C). Default 75°C.

    Returns
    -------
    dict with keys:
      min_cross_section_mm2  : float — calculated minimum cross-section (mm²)
      recommended_mm2        : float — next standard size from {1.5, 2.5, 4, 6, 10,
                                       16, 25, 35, 50, 70, 95, 120, 150, 185, 240}
      actual_drop_pct        : float — voltage drop at recommended size (%)
      warnings               : list[str]
    """
    _STANDARD_SIZES = [
        1.5, 2.5, 4.0, 6.0, 10.0, 16.0, 25.0, 35.0, 50.0,
        70.0, 95.0, 120.0, 150.0, 185.0, 240.0,
    ]
    warns: list[str] = []

    # Temperature-corrected resistivity
    rho = resistivity * (1 + 0.00393 * (temperature_c - 20.0))

    drop_fraction = max_drop_pct / 100.0
    if drop_fraction <= 0:
        warns.append("max_drop_pct must be > 0; defaulting to 1%")
        drop_fraction = 0.01

    # Round-trip length
    min_area_m2 = (2 * length_m * current_a * rho) / (voltage_v * drop_fraction)
    min_area_mm2 = min_area_m2 * 1e6

    # Next standard size up
    recommended = None
    for s in _STANDARD_SIZES:
        if s >= min_area_mm2:
            recommended = s
            break
    if recommended is None:
        recommended = _STANDARD_SIZES[-1]
        warns.append(
            f"Required cross-section {min_area_mm2:.1f} mm² exceeds largest "
            f"standard size {_STANDARD_SIZES[-1]} mm²; consider parallel cables"
        )

    # Actual drop at recommended size
    actual_resistance = rho * 2 * length_m / (recommended * 1e-6)
    actual_drop_v = current_a * actual_resistance
    actual_drop_pct = (actual_drop_v / voltage_v) * 100.0

    if actual_drop_pct > max_drop_pct * 1.05:
        warns.append(
            f"Actual voltage drop {actual_drop_pct:.2f}% exceeds maximum "
            f"{max_drop_pct}% — verify cable selection"
        )

    for w in warns:
        warnings.warn(w, stacklevel=2)

    return {
        "min_cross_section_mm2": round(min_area_mm2, 4),
        "recommended_mm2":       recommended,
        "actual_drop_pct":       round(actual_drop_pct, 4),
        "warnings":              warns,
    }


# ---------------------------------------------------------------------------
# ENERGY YIELD & PERFORMANCE RATIO
# ---------------------------------------------------------------------------

def energy_yield(
    array_kWp: float,
    poa_annual_kWh_m2: float,
    pr: float,
    *,
    degradation_rate: float = 0.005,
    years: int = 25,
) -> dict[str, Any]:
    """Annual and lifetime energy yield, specific yield, and performance ratio.

    Formula:
        E_yr1 = array_kWp × poa_annual_kWh_m2 × PR  (kWh)
        E_yr_n = E_yr1 × (1 − degradation_rate)^(n−1)

    Parameters
    ----------
    array_kWp : float
        DC peak power of the array (kWp).
    poa_annual_kWh_m2 : float
        Annual plane-of-array irradiation (kWh/m²/year).
    pr : float
        System performance ratio (0–1).
    degradation_rate : float
        Annual module degradation fraction (default 0.005 = 0.5%/year).
    years : int
        System lifetime for lifetime yield calculation (default 25 years).

    Returns
    -------
    dict with keys:
      annual_yield_yr1_kWh    : float — year-1 energy yield (kWh)
      specific_yield_kWh_kWp  : float — year-1 specific yield (kWh/kWp)
      lifetime_yield_kWh      : float — sum over `years` with degradation
      performance_ratio       : float — PR (passed through)
      warnings                : list[str]
    """
    warns: list[str] = []
    if pr <= 0 or pr > 1.0:
        warns.append(f"pr={pr} outside (0,1]; check value")

    e_yr1 = array_kWp * poa_annual_kWh_m2 * pr
    specific = e_yr1 / array_kWp if array_kWp > 0 else 0.0

    lifetime = sum(
        e_yr1 * ((1 - degradation_rate) ** (n - 1))
        for n in range(1, years + 1)
    )

    for w in warns:
        warnings.warn(w, stacklevel=2)

    return {
        "annual_yield_yr1_kWh":   round(e_yr1, 2),
        "specific_yield_kWh_kWp": round(specific, 2),
        "lifetime_yield_kWh":     round(lifetime, 2),
        "performance_ratio":      pr,
        "degradation_rate":       degradation_rate,
        "years":                  years,
        "warnings":               warns,
    }


# ---------------------------------------------------------------------------
# ROW SPACING / SHADING
# ---------------------------------------------------------------------------

def row_spacing(
    module_length_m: float,
    tilt_deg: float,
    latitude_deg: float,
    *,
    gcr: float | None = None,
    winter_margin_h: float = 3.0,
) -> dict[str, Any]:
    """Minimum row pitch and ground-cover ratio for no inter-row shading.

    The worst-case shading condition is at the winter solstice (day 355 for
    northern hemisphere, day 172 for southern) at the lowest solar elevation
    around solar noon ± winter_margin_h hours.

    Shadow length cast by a row of height h = L·sin(tilt) onto the horizontal:
        shadow = h / tan(solar_altitude_min)

    Row pitch (horizontal distance between front edges of successive rows):
        pitch = L·cos(tilt) + shadow

    Ground-cover ratio:
        GCR = L·cos(tilt) / pitch  (horizontal projection / pitch)

    Note: GCR here is the ratio of module horizontal projection to row spacing,
    i.e. GCR = cos(β)·L / pitch.  Some sources define GCR = L / pitch.

    Parameters
    ----------
    module_length_m : float
        Module (or row) length in the tilt direction (m).
    tilt_deg : float
        Array tilt from horizontal (degrees).
    latitude_deg : float
        Site latitude (degrees, + north, − south).
    gcr : float or None
        If provided, calculate the row pitch from GCR instead.  Must be in (0,1).
    winter_margin_h : float
        Hours from solar noon to define worst-case shading window (default 3 h).

    Returns
    -------
    dict with keys:
      row_pitch_m          : float — minimum row pitch (m)
      gcr                  : float — ground-cover ratio
      module_horizontal_m  : float — horizontal module projection (m)
      shadow_length_m      : float — shadow length at worst-case altitude (m)
      min_solar_altitude_deg: float — worst-case solar altitude used (°)
      warnings             : list[str]
    """
    warns: list[str] = []

    beta = math.radians(tilt_deg)
    # Module height (vertical projection)
    h = module_length_m * math.sin(beta)
    # Module horizontal projection
    horiz = module_length_m * math.cos(beta)

    # Worst-case: winter solstice
    if latitude_deg >= 0:
        solstice_day = 355  # Dec 21 in northern hemisphere
    else:
        solstice_day = 172  # Jun 21 in southern hemisphere

    # Solar altitude at solar noon ± winter_margin_h on solstice
    altitudes: list[float] = []
    for dt in [-winter_margin_h, 0.0, winter_margin_h]:
        solar_t = 12.0 + dt
        pos = solar_position(latitude_deg, solstice_day, solar_t)
        alt = pos["altitude_deg"]
        if alt > 0:
            altitudes.append(alt)

    if not altitudes:
        warns.append(
            "Sun is below horizon at all checked times on winter solstice "
            f"(lat={latitude_deg}°); using 5° minimum altitude"
        )
        min_alt = 5.0
    else:
        min_alt = min(altitudes)

    if min_alt < 5.0:
        warns.append(
            f"Very low solar altitude ({min_alt:.1f}°) will result in very long "
            "shadows; consider a lower tilt or accepting some winter shading"
        )

    tan_alt = math.tan(math.radians(min_alt))
    shadow = h / tan_alt if tan_alt > 0 else float("inf")
    pitch = horiz + shadow

    gcr_calc = horiz / pitch if pitch > 0 else 0.0

    if gcr is not None:
        if not (0 < gcr < 1):
            warns.append("gcr must be in (0, 1); ignoring provided gcr")
        else:
            # Override: pitch from GCR
            pitch = horiz / gcr
            gcr_calc = gcr
            # Recalculate implied shadow
            shadow = pitch - horiz

    for w in warns:
        warnings.warn(w, stacklevel=2)

    return {
        "row_pitch_m":           round(pitch, 4),
        "gcr":                   round(gcr_calc, 4),
        "module_horizontal_m":   round(horiz, 4),
        "shadow_length_m":       round(shadow, 4),
        "min_solar_altitude_deg": round(min_alt, 4),
        "warnings":              warns,
    }
