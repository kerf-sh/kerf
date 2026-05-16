"""
kerf_cad_core.beltchain.drives — pure-Python belt & chain drive calculations.

Implements three public functions:

  vbelt_design(power_kW, n_driver_rpm, n_driven_rpm, *, ...)
      Classical / narrow V-belt drive selection per Shigley §17-5 / RMA IP-20.
      Computes design power (service factor), belt cross-section suggestion,
      pitch diameter pair, belt length and centre distance, wrap angles,
      number of belts from rated per-belt power × correction factors,
      belt speed, tight/slack tensions via capstan equation (e^μθ), shaft load.

  timing_belt_design(power_kW, n_driver_rpm, pitch_mm, *, ...)
      Synchronous (timing) belt sizing per Shigley §17-9.
      Computes pitch diameter, centre distance, belt pitch length,
      teeth-in-mesh on small sprocket, minimum belt width.

  chain_drive_design(power_kW, n_small_rpm, z_small, z_large, *, ...)
      ANSI roller-chain drive per Shigley §17-11 / ANSI B29.1.
      Selects ANSI pitch from tabulated rated power, computes sprocket pitch
      diameters, chain length in pitches (even), service-factor design power,
      lubrication regime from chain speed, breaking-load safety factor.

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.
Warnings (wrap-angle-too-small, speed-out-of-range, undersized) are
appended to the "warnings" list in the return dict, never raised.

Units
-----
  power           — kilowatts (kW) input; Watts used internally
  speed           — rpm
  length / dia    — millimetres (mm) for diameters & chain pitch; metres where noted
  tension         — Newtons (N)
  belt speed      — m/s
  chain speed     — m/s
  angles          — radians (internal), degrees in output

References
----------
Shigley's Mechanical Engineering Design, 10th ed., §§ 17-1 to 17-12
Mott, R.L. "Machine Elements in Mechanical Design", 5th ed., Chs. 7 & 9
ANSI/RMA IP-20 — Classical and Narrow V-Belt Engineering Standard
ANSI/ASME B29.1 — Precision Power Transmission Roller Chains

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings as _warnings_module
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _guard_positive(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


def _guard_nonneg(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < 0:
        return f"{name} must be >= 0, got {v}"
    return None


# ---------------------------------------------------------------------------
# V-belt tables & constants
# ---------------------------------------------------------------------------

# Service factors per Shigley Table 17-11 / RMA IP-20
# Indexed by driver_type × daily_hours bucket
# "normal" = AC motor normal torque; "heavy" = high-torque / single-cyl engine
_VBELT_SERVICE_FACTORS: dict[tuple[str, str], float] = {
    ("normal", "light"):    1.0,
    ("normal", "moderate"): 1.1,
    ("normal", "heavy"):    1.2,
    ("heavy",  "light"):    1.1,
    ("heavy",  "moderate"): 1.2,
    ("heavy",  "heavy"):    1.4,
}

# Approximate per-belt rated power at reference speed (1000 rpm) for
# each cross-section at nominal pitch diameter (kW/belt, indicative).
# Actual rated power is speed-dependent; we use a linear-ish model.
# Source: RMA IP-20 Table 1 / Shigley Table 17-12 condensed.
_VBELT_SECTIONS: list[dict] = [
    # name, min_d_mm, max_d_mm, base_power_kW_per_belt_per_1000rpm
    {"name": "A",  "d_min": 75,  "d_max": 200, "kw_per_1000rpm": 0.90},
    {"name": "B",  "d_min": 125, "d_max": 300, "kw_per_1000rpm": 1.75},
    {"name": "C",  "d_min": 200, "d_max": 600, "kw_per_1000rpm": 3.50},
    {"name": "D",  "d_min": 350, "d_max": 900, "kw_per_1000rpm": 7.50},
    {"name": "3V", "d_min": 67,  "d_max": 250, "kw_per_1000rpm": 1.20},
    {"name": "5V", "d_min": 140, "d_max": 450, "kw_per_1000rpm": 3.80},
    {"name": "8V", "d_min": 280, "d_max": 900, "kw_per_1000rpm": 9.50},
]

# V-belt coefficient of friction (rubber on cast-iron sheave), Shigley §17-2
_VBELT_MU = 0.51

# Belt speed limits (m/s), Shigley §17-5
_VBELT_SPEED_MIN = 5.0
_VBELT_SPEED_MAX = 30.0

# Minimum wrap angle for adequate capacity (degrees), Shigley §17-5
_VBELT_WRAP_MIN_DEG = 120.0

# Length correction factor table: KC at index = (L - L_ref) approach
# Simplified: Kc = 1.0 for nominal; ±10 % range — absorbed into safety note.
# We use the analytic formula: Kc ≈ (L/L_ref)^0.09  (per Gates/RMA)
_VBELT_LENGTH_EXP = 0.09

# Small-sheave correction factor table for wrap angle, Shigley Table 17-13
# Cv = 1 - 0.5123·exp(-0.5723·θ_small)  (θ in radians) — curve fit
def _wrap_correction(theta_rad: float) -> float:
    """Wrap-angle correction factor Cv (Shigley Table 17-13 curve fit)."""
    return 1.0 - 0.5123 * math.exp(-0.5723 * theta_rad)


# Reference belt lengths (mm) per section (nominal catalogue length)
_VBELT_REF_LENGTH_MM: dict[str, float] = {
    "A": 914.0, "B": 1524.0, "C": 2032.0, "D": 3048.0,
    "3V": 914.0, "5V": 1524.0, "8V": 2540.0,
}


def _select_vbelt_section(d_small_mm: float, design_power_kW: float) -> dict:
    """Select the lightest V-belt cross-section that fits d_small and power."""
    for sec in _VBELT_SECTIONS:
        if d_small_mm >= sec["d_min"]:
            return sec
    # Fallback: largest section
    return _VBELT_SECTIONS[-1]


# ---------------------------------------------------------------------------
# 1. vbelt_design
# ---------------------------------------------------------------------------

def vbelt_design(
    power_kW: float,
    n_driver_rpm: float,
    n_driven_rpm: float,
    *,
    d_small_mm: float | None = None,
    center_distance_mm: float | None = None,
    service_factor: float | None = None,
    driver_type: str = "normal",
    load_hours: str = "moderate",
    mu: float = _VBELT_MU,
) -> dict:
    """
    Classical/narrow V-belt drive design.

    Parameters
    ----------
    power_kW : float
        Nominal transmitted power (kW). Must be > 0.
    n_driver_rpm : float
        Driver (small) sheave speed (rpm). Must be > 0.
    n_driven_rpm : float
        Driven (large) sheave speed (rpm). Must be > 0.
    d_small_mm : float | None
        Pitch diameter of small (driver) sheave (mm). If None, a reasonable
        default is chosen from the selected belt section table. Must be > 0.
    center_distance_mm : float | None
        Desired centre distance (mm). If None, defaults to
        D_large + d_small (rule of thumb for initial selection). Must be > 0.
    service_factor : float | None
        Manual override for Ks (service factor). If None, looked up from
        driver_type × load_hours table. Must be > 0.
    driver_type : str
        "normal" (AC motor, normal torque) or "heavy" (high-torque / IC engine).
    load_hours : str
        "light" (< 10 h/day), "moderate" (10-16 h/day), or "heavy" (> 16 h/day).
    mu : float
        Coefficient of friction between belt and sheave. Default 0.51.

    Returns
    -------
    dict
        ok                  : True
        section             : recommended belt cross-section (A/B/C/D/3V/5V/8V)
        design_power_kW     : design power after service factor (kW)
        service_factor      : Ks used
        speed_ratio         : n_driver / n_driven (≥ 1 by convention)
        d_small_mm          : small-sheave pitch diameter (mm)
        d_large_mm          : large-sheave pitch diameter (mm)
        belt_speed_m_s      : belt speed (m/s)
        belt_length_mm      : required pitch belt length (mm)
        center_distance_mm  : computed centre distance (mm)
        wrap_small_deg      : wrap angle on small sheave (degrees)
        wrap_large_deg      : wrap angle on large sheave (degrees)
        Cv                  : wrap-angle correction factor
        Kc                  : length correction factor
        power_per_belt_kW   : corrected rated power per belt (kW)
        n_belts             : number of belts required (integer, rounded up)
        tension_tight_N     : tight-side tension T1 (N)
        tension_slack_N     : slack-side tension T2 (N)
        shaft_load_N        : total resultant shaft load ≈ T1 + T2 (N)
        warnings            : list of advisory strings (never fatal)

    Notes (Shigley §17-5)
    ---------------------
    Design power:   H_d = H_nom × Ks
    Speed ratio:    i = n1 / n2  →  D = i · d
    Belt speed:     v = π·d·n1 / 60 000  (d in mm, n in rpm, v in m/s)
    Belt length (open drive):
        L = 2·C + π·(D+d)/2 + (D-d)²/(4·C)
    Wrap angle (small sheave):
        θ_s = π - 2·arcsin((D-d)/(2·C))   [rad]
    Capstan:        T1/T2 = e^(μ·θ_s)
    Net force:      F_net = H_d·1000 / v  [N]  (H_d in kW)
    Tension split:
        T1 - T2 = F_net
        T1/T2 = e^(μ·θ_s)
        → T2 = F_net / (e^(μ·θ_s) - 1)
        → T1 = T2 + F_net
    """
    warns: list[str] = []

    # --- Validate required inputs ---
    for name, val in [("power_kW", power_kW), ("n_driver_rpm", n_driver_rpm),
                      ("n_driven_rpm", n_driven_rpm)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    if mu is not None:
        e = _guard_positive("mu", mu)
        if e:
            return _err(e)
    mu = float(mu)

    # --- Service factor ---
    if service_factor is not None:
        e = _guard_positive("service_factor", service_factor)
        if e:
            return _err(e)
        Ks = float(service_factor)
    else:
        dt = str(driver_type).strip().lower()
        lh = str(load_hours).strip().lower()
        if dt not in ("normal", "heavy"):
            return _err(f"driver_type must be 'normal' or 'heavy', got {driver_type!r}")
        if lh not in ("light", "moderate", "heavy"):
            return _err(f"load_hours must be 'light', 'moderate', or 'heavy', got {load_hours!r}")
        Ks = _VBELT_SERVICE_FACTORS[(dt, lh)]

    H_nom = float(power_kW)
    H_d = H_nom * Ks  # design power (kW)

    n1 = float(n_driver_rpm)
    n2 = float(n_driven_rpm)

    # Speed ratio (always >= 1)
    speed_ratio = n1 / n2

    # --- Belt section selection ---
    # Preliminary: use d_small or pick from section min
    if d_small_mm is not None:
        e = _guard_positive("d_small_mm", d_small_mm)
        if e:
            return _err(e)
        d = float(d_small_mm)
    else:
        # Default: pick smallest d from suggested section for H_d
        sec_guess = _select_vbelt_section(100.0, H_d)
        d = float(sec_guess["d_min"])

    D = d * speed_ratio  # large sheave diameter (mm)

    # Now select section properly based on actual d and H_d
    section_data = _select_vbelt_section(d, H_d)
    section = section_data["name"]

    # Belt speed (m/s): v = π · d · n1 / (60 × 1000)
    v = math.pi * d * n1 / (60.0 * 1000.0)

    if v < _VBELT_SPEED_MIN:
        warns.append(
            f"belt_speed {v:.2f} m/s is below recommended minimum "
            f"{_VBELT_SPEED_MIN} m/s — consider smaller sheave or higher speed"
        )
    if v > _VBELT_SPEED_MAX:
        warns.append(
            f"belt_speed {v:.2f} m/s exceeds recommended maximum "
            f"{_VBELT_SPEED_MAX} m/s — belt fatigue risk"
        )
        return {**_err(
            f"belt_speed {v:.2f} m/s out of range [{_VBELT_SPEED_MIN}, {_VBELT_SPEED_MAX}] m/s"
        ), "warnings": warns}

    # --- Centre distance ---
    if center_distance_mm is not None:
        e = _guard_positive("center_distance_mm", center_distance_mm)
        if e:
            return _err(e)
        C = float(center_distance_mm)
        # Check practical bounds: D < C < 3(D+d), Shigley §17-5
        if C < D:
            warns.append(
                f"center_distance {C:.1f} mm < large sheave dia {D:.1f} mm — "
                "may cause belt interference; recommend C > D_large"
            )
    else:
        C = D + d  # rule of thumb: C ≈ D_large + d_small

    # --- Belt length (open-belt drive) ---
    # L = 2C + π(D+d)/2 + (D-d)²/(4C)
    L = 2.0 * C + math.pi * (D + d) / 2.0 + (D - d) ** 2 / (4.0 * C)

    # Back-compute actual centre distance from selected L
    # Quadratic: 4C² - (4L - 2π(D+d))C + (D-d)² = 0
    # Use analytic inversion (Shigley eq. 17-17):
    b_coeff = 4.0 * L - 2.0 * math.pi * (D + d)
    discriminant = b_coeff ** 2 - 32.0 * (D - d) ** 2
    if discriminant < 0:
        warns.append("belt length / centre distance geometry is infeasible — using initial estimate")
        C_actual = C
    else:
        C_actual = (b_coeff + math.sqrt(discriminant)) / 8.0

    # --- Wrap angles ---
    arg = (D - d) / (2.0 * C_actual)
    if abs(arg) > 1.0:
        return _err(
            f"(D-d)/(2C) = {arg:.3f} > 1; geometry is impossible — "
            "increase centre distance or reduce speed ratio"
        )
    theta_small = math.pi - 2.0 * math.asin(arg)   # rad, small sheave
    theta_large = math.pi + 2.0 * math.asin(arg)   # rad, large sheave
    theta_small_deg = math.degrees(theta_small)
    theta_large_deg = math.degrees(theta_large)

    if theta_small_deg < _VBELT_WRAP_MIN_DEG:
        warns.append(
            f"wrap angle on small sheave {theta_small_deg:.1f}° < "
            f"recommended minimum {_VBELT_WRAP_MIN_DEG}° — "
            "increase centre distance or reduce speed ratio"
        )

    # --- Correction factors ---
    Cv = _wrap_correction(theta_small)

    # Length correction factor Kc (Gates/RMA approach)
    L_ref = _VBELT_REF_LENGTH_MM.get(section, 1524.0)
    Kc = (L / L_ref) ** _VBELT_LENGTH_EXP

    # --- Per-belt rated power ---
    # H_rated = (kw_per_1000rpm × n1/1000) × Cv × Kc
    H_belt_base = section_data["kw_per_1000rpm"] * (n1 / 1000.0)
    H_belt = H_belt_base * Cv * Kc

    if H_belt <= 0:
        return _err("computed per-belt rated power is zero or negative — check inputs")

    # --- Number of belts ---
    import math as _math
    n_belts = int(_math.ceil(H_d / H_belt))
    if n_belts < 1:
        n_belts = 1

    if H_d > H_belt * n_belts * 1.2:
        warns.append(
            "drive appears undersized — actual capacity <120% of design power; "
            "consider larger sheaves or next belt section"
        )

    # --- Tensions (capstan equation) ---
    # Net force per belt: F_net = H_d_per_belt × 1000 / v  (H in kW, v in m/s)
    H_per_belt = H_d / n_belts  # kW each belt carries
    F_net = H_per_belt * 1000.0 / v  # N, net (tight − slack)

    exp_mu_theta = math.exp(mu * theta_small)
    # T1 - T2 = F_net ; T1/T2 = exp_mu_theta
    # → T2 = F_net / (exp_mu_theta - 1)
    denom = exp_mu_theta - 1.0
    if denom <= 0:
        T2 = 0.0
        T1 = F_net
    else:
        T2 = F_net / denom
        T1 = T2 + F_net

    # Total shaft load (both sides of all belts)
    shaft_load = n_belts * (T1 + T2)

    return {
        "ok": True,
        "section": section,
        "design_power_kW": round(H_d, 4),
        "service_factor": round(Ks, 4),
        "speed_ratio": round(speed_ratio, 4),
        "d_small_mm": round(d, 3),
        "d_large_mm": round(D, 3),
        "belt_speed_m_s": round(v, 4),
        "belt_length_mm": round(L, 2),
        "center_distance_mm": round(C_actual, 2),
        "wrap_small_deg": round(theta_small_deg, 2),
        "wrap_large_deg": round(theta_large_deg, 2),
        "Cv": round(Cv, 4),
        "Kc": round(Kc, 4),
        "power_per_belt_kW": round(H_belt, 4),
        "n_belts": n_belts,
        "tension_tight_N": round(T1, 2),
        "tension_slack_N": round(T2, 2),
        "shaft_load_N": round(shaft_load, 2),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# Timing / synchronous belt tables & constants
# ---------------------------------------------------------------------------

# Standard HTD / MXL / T5 / T10 / AT pitches (mm) in ascending order
# For width selection we use teeth-in-mesh based capacity method (Shigley §17-9)
_TIMING_PITCHES_MM = [2.032, 3.0, 5.0, 8.0, 14.0, 25.4]  # MXL, 3M, 5M, 8M, 14M, H

# Approximate rated power per 25 mm width per 1000 rpm for each pitch (kW)
# Conservative values — actual ratings from manufacturer belt books
_TIMING_PITCH_POWER: dict[float, float] = {
    2.032: 0.040,
    3.0:   0.080,
    5.0:   0.22,
    8.0:   0.65,
    14.0:  2.10,
    25.4:  7.50,
}

# Standard width series (mm) per pitch
_TIMING_WIDTHS_MM: dict[float, list[int]] = {
    2.032: [6, 10, 13],
    3.0:   [6, 9, 15],
    5.0:   [9, 15, 25],
    8.0:   [20, 30, 50, 85],
    14.0:  [40, 55, 85, 115, 170],
    25.4:  [50, 75, 100],
}

# Minimum teeth-in-mesh recommended (Shigley §17-9)
_TIMING_MIN_TEETH_IN_MESH = 6


# ---------------------------------------------------------------------------
# 2. timing_belt_design
# ---------------------------------------------------------------------------

def timing_belt_design(
    power_kW: float,
    n_driver_rpm: float,
    pitch_mm: float | None = None,
    *,
    z_driver: int = 18,
    speed_ratio: float = 1.0,
    center_distance_mm: float | None = None,
    service_factor: float = 1.3,
) -> dict:
    """
    Synchronous (timing) belt drive design.

    Parameters
    ----------
    power_kW : float
        Nominal transmitted power (kW). Must be > 0.
    n_driver_rpm : float
        Driver sprocket speed (rpm). Must be > 0.
    pitch_mm : float | None
        Belt pitch (mm). Supported: 2.032 (MXL), 3, 5, 8, 14, 25.4 (H).
        If None, the smallest pitch capable of transmitting the design power
        is selected automatically.
    z_driver : int
        Number of teeth on driver sprocket. Default 18. Must be >= 10.
    speed_ratio : float
        n_driver / n_driven. Must be >= 1. Default 1.0 (1:1).
    center_distance_mm : float | None
        Desired centre distance (mm). If None, defaults to 3 × pitch diameter
        of the larger sprocket. Must be > 0.
    service_factor : float
        Design service factor Ks. Default 1.3. Must be > 0.

    Returns
    -------
    dict
        ok                   : True
        pitch_mm             : belt pitch used (mm)
        design_power_kW      : design power = power_kW × Ks (kW)
        service_factor       : Ks
        z_driver             : driver sprocket teeth
        z_driven             : driven sprocket teeth
        speed_ratio          : actual speed ratio (z_driven / z_driver)
        d_driver_mm          : driver pitch diameter (mm)
        d_driven_mm          : driven pitch diameter (mm)
        belt_speed_m_s       : belt speed (m/s)
        belt_pitch_length_mm : selected belt pitch length (mm)
        center_distance_mm   : resulting centre distance (mm)
        teeth_in_mesh        : teeth in mesh on small sprocket
        belt_width_mm        : minimum recommended belt width (mm)
        warnings             : list of advisory strings

    Notes (Shigley §17-9)
    ---------------------
    Pitch diameter: d = z · p / π   (p = pitch in mm)
    Belt speed:     v = π · d_s · n / (60 × 1000)   (m/s)
    Teeth in mesh:  m_t = z_s × θ_s / (2π)  ≈ z_s/2 for 1:1
    Belt length:    L = 2C + π(d_l + d_s)/2 + (d_l - d_s)²/(4C)
    Width:          H_belt = (kw_per_25mm_per_1000rpm × (n/1000)) × (w/25)
                    → w = H_d × 25 / (H_unit × n/1000)
    """
    warns: list[str] = []

    for name, val in [("power_kW", power_kW), ("n_driver_rpm", n_driver_rpm)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    e = _guard_positive("service_factor", service_factor)
    if e:
        return _err(e)

    if z_driver < 10:
        return _err(f"z_driver must be >= 10, got {z_driver}")

    e = _guard_positive("speed_ratio", speed_ratio)
    if e:
        return _err(e)
    if speed_ratio < 1.0:
        # Swap convention: we define speed_ratio = n_driver / n_driven >= 1
        warns.append(
            f"speed_ratio {speed_ratio} < 1 — interpreting as n_driven/n_driver; "
            "convention is n_driver/n_driven >= 1"
        )
        speed_ratio = 1.0 / speed_ratio

    H_nom = float(power_kW)
    Ks = float(service_factor)
    H_d = H_nom * Ks

    n1 = float(n_driver_rpm)

    # --- Select pitch ---
    if pitch_mm is not None:
        # Find closest standard pitch
        p = min(_TIMING_PITCHES_MM, key=lambda x: abs(x - float(pitch_mm)))
        if abs(p - float(pitch_mm)) > 1.0:
            warns.append(
                f"pitch_mm {pitch_mm} not a standard pitch; "
                f"using nearest standard {p} mm"
            )
    else:
        # Auto-select: smallest pitch whose unit power exceeds requirement
        p = None
        for candidate in _TIMING_PITCHES_MM:
            unit_kw = _TIMING_PITCH_POWER[candidate]
            # Estimate width at 25 mm reference
            H_unit = unit_kw * (n1 / 1000.0)
            if H_unit > 0 and H_d / H_unit <= 8:
                # Fits within 8× the 25 mm reference width
                p = candidate
                break
        if p is None:
            p = _TIMING_PITCHES_MM[-1]  # largest pitch as fallback

    p_mm = float(p)

    # --- Sprocket teeth ---
    z_s = int(z_driver)  # driver (small) if ratio >= 1
    z_l = max(z_s, int(round(z_s * speed_ratio)))  # driven (large)
    actual_ratio = z_l / z_s

    # --- Pitch diameters (mm) ---
    # d = z · p / π
    d_s = z_s * p_mm / math.pi
    d_l = z_l * p_mm / math.pi

    # --- Belt speed ---
    v = math.pi * d_s * n1 / (60.0 * 1000.0)  # m/s

    # --- Centre distance ---
    if center_distance_mm is not None:
        e = _guard_positive("center_distance_mm", center_distance_mm)
        if e:
            return _err(e)
        C = float(center_distance_mm)
    else:
        C = 3.0 * d_l  # rule of thumb: 3 × large pitch diameter

    # --- Belt pitch length ---
    L = 2.0 * C + math.pi * (d_l + d_s) / 2.0 + (d_l - d_s) ** 2 / (4.0 * C)

    # Teeth in mesh on small sprocket
    arg = (d_l - d_s) / (2.0 * C)
    arg = min(max(arg, -1.0), 1.0)
    theta_s = math.pi - 2.0 * math.asin(arg)  # rad
    m_t = z_s * theta_s / (2.0 * math.pi)

    if m_t < _TIMING_MIN_TEETH_IN_MESH:
        warns.append(
            f"teeth in mesh {m_t:.1f} < recommended minimum "
            f"{_TIMING_MIN_TEETH_IN_MESH} — reduce speed ratio or increase z_driver"
        )

    # --- Belt width ---
    unit_kw_per_25mm = _TIMING_PITCH_POWER[p_mm]
    H_unit_at_n = unit_kw_per_25mm * (n1 / 1000.0)  # kW per 25 mm width
    if H_unit_at_n > 0:
        w_required = H_d * 25.0 / H_unit_at_n  # mm
    else:
        w_required = 25.0

    # Round up to next standard width
    std_widths = _TIMING_WIDTHS_MM.get(p_mm, [25, 50, 100])
    belt_width = next((w for w in sorted(std_widths) if w >= w_required), std_widths[-1])
    if w_required > std_widths[-1]:
        warns.append(
            f"required width {w_required:.1f} mm exceeds maximum standard width "
            f"{std_widths[-1]} mm for pitch {p_mm} mm — use larger pitch"
        )

    return {
        "ok": True,
        "pitch_mm": p_mm,
        "design_power_kW": round(H_d, 4),
        "service_factor": round(Ks, 4),
        "z_driver": z_s,
        "z_driven": z_l,
        "speed_ratio": round(actual_ratio, 4),
        "d_driver_mm": round(d_s, 3),
        "d_driven_mm": round(d_l, 3),
        "belt_speed_m_s": round(v, 4),
        "belt_pitch_length_mm": round(L, 2),
        "center_distance_mm": round(C, 2),
        "teeth_in_mesh": round(m_t, 2),
        "belt_width_mm": int(belt_width),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# Roller chain tables & constants (ANSI B29.1 / Shigley §17-11)
# ---------------------------------------------------------------------------

# ANSI chain number → (pitch_inches, breaking_load_N, max_rpm_for_lube_type)
# Source: Shigley Table 17-20 / ANSI B29.1 selected values
# Tuple: (pitch_in, pitch_mm, breaking_load_N, lube_type_A_max_rpm, lube_type_B_max_rpm)
_CHAIN_TABLE: dict[str, dict] = {
    "25":  {"pitch_mm": 6.35,  "break_N":  3600,  "lube_A_rpm": 1000, "lube_B_rpm": 3000},
    "35":  {"pitch_mm": 9.525, "break_N":  7800,  "lube_A_rpm":  700, "lube_B_rpm": 2200},
    "40":  {"pitch_mm": 12.70, "break_N": 14100,  "lube_A_rpm":  500, "lube_B_rpm": 1600},
    "50":  {"pitch_mm": 15.875,"break_N": 22200,  "lube_A_rpm":  400, "lube_B_rpm": 1300},
    "60":  {"pitch_mm": 19.05, "break_N": 31800,  "lube_A_rpm":  350, "lube_B_rpm": 1000},
    "80":  {"pitch_mm": 25.40, "break_N": 57800,  "lube_A_rpm":  250, "lube_B_rpm":  750},
    "100": {"pitch_mm": 31.75, "break_N": 88900,  "lube_A_rpm":  200, "lube_B_rpm":  600},
    "120": {"pitch_mm": 38.10, "break_N": 127000, "lube_A_rpm":  150, "lube_B_rpm":  500},
    "140": {"pitch_mm": 44.45, "break_N": 172000, "lube_A_rpm":  120, "lube_B_rpm":  400},
    "160": {"pitch_mm": 50.80, "break_N": 222000, "lube_A_rpm":  100, "lube_B_rpm":  350},
    "180": {"pitch_mm": 57.15, "break_N": 281000, "lube_A_rpm":   80, "lube_B_rpm":  300},
    "200": {"pitch_mm": 63.50, "break_N": 347000, "lube_A_rpm":   70, "lube_B_rpm":  250},
    "240": {"pitch_mm": 76.20, "break_N": 498000, "lube_A_rpm":   55, "lube_B_rpm":  200},
}

# Approximate rated horsepower at 1000 rpm for ANSI chains (hp/strand at n=1000, z_s=17)
# Used for chain selection check; source: Shigley Table 17-21 curve-fit
_CHAIN_HP_PER_1000RPM: dict[str, float] = {
    "25":  0.05,  "35":  0.20,  "40":  0.45,
    "50":  0.85,  "60":  1.50,  "80":  3.20,
    "100": 6.00,  "120": 10.0,  "140": 15.0,
    "160": 22.0,  "180": 30.0,  "200": 40.0,  "240": 60.0,
}

# Service factors for roller chain (Shigley Table 17-22)
_CHAIN_SERVICE_FACTORS: dict[str, float] = {
    "smooth":   1.0,
    "moderate": 1.25,
    "heavy":    1.5,
}

# Chain speed lubrication regimes (Shigley §17-11)
_CHAIN_LUBE_A_MAX_M_S = 0.6   # drip/splash type A
_CHAIN_LUBE_B_MAX_M_S = 3.0   # oil bath / stream type B
# Above type B → oil stream (pump) required


# ---------------------------------------------------------------------------
# 3. chain_drive_design
# ---------------------------------------------------------------------------

def chain_drive_design(
    power_kW: float,
    n_small_rpm: float,
    z_small: int,
    z_large: int,
    *,
    chain_no: str | None = None,
    load_type: str = "smooth",
    n_strands: int = 1,
) -> dict:
    """
    ANSI roller-chain drive design.

    Parameters
    ----------
    power_kW : float
        Nominal transmitted power (kW). Must be > 0.
    n_small_rpm : float
        Small sprocket speed (rpm). Must be > 0.
    z_small : int
        Teeth on small sprocket. Must be >= 7.
    z_large : int
        Teeth on large sprocket. Must be >= z_small.
    chain_no : str | None
        ANSI chain number ('25', '35', '40', '50', '60', '80', '100',
        '120', '140', '160', '180', '200', '240'). If None, the smallest
        adequate chain is selected automatically.
    load_type : str
        Load character: 'smooth', 'moderate', or 'heavy'.
    n_strands : int
        Number of parallel strands. Default 1. Must be >= 1.

    Returns
    -------
    dict
        ok                      : True
        chain_no                : ANSI chain number selected
        pitch_mm                : chain pitch (mm)
        design_power_kW         : design power = power_kW × Ks (kW/strand)
        service_factor          : Ks
        speed_ratio             : z_large / z_small
        z_small                 : small sprocket teeth
        z_large                 : large sprocket teeth
        d_small_mm              : small sprocket pitch diameter (mm)
        d_large_mm              : large sprocket pitch diameter (mm)
        chain_speed_m_s         : chain speed (m/s)
        chain_length_pitches    : chain length in pitches (integer, even)
        center_distance_mm      : computed centre distance (mm)
        rated_power_per_strand_kW: rated power per strand at this speed (kW)
        n_strands               : number of strands
        total_rated_power_kW    : n_strands × rated power per strand (kW)
        breaking_load_N         : chain breaking load per strand (N)
        working_tension_N       : maximum chain tension under design power (N)
        safety_factor           : breaking_load / working_tension
        lubrication_regime      : 'type_A_drip', 'type_B_bath', or 'type_C_pump'
        warnings                : list of advisory strings

    Notes (Shigley §17-11)
    ----------------------
    Pitch diameter (mm):  d = p / sin(π / z)
    Chain speed (m/s):    v = z_s × p × n_s / (60 × 1000)   (p in mm)
    Chain length (pitches):
        L_p = 2·C_p + (z_l + z_s)/2 + ((z_l - z_s)/(2·π))² / C_p
        where C_p = C / p (centre distance in pitches)
    Centre distance (pitches):
        C_p = [L_p - (z_l+z_s)/2 + √((L_p-(z_l+z_s)/2)² - 8·((z_l-z_s)/(2π))²)] / 4
    Working tension:
        F = H_d × 1000 / v   (N; H_d in kW per strand)
    Safety factor:
        SF = F_break / F
    """
    warns: list[str] = []

    for name, val in [("power_kW", power_kW), ("n_small_rpm", n_small_rpm)]:
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    if z_small < 7:
        return _err(f"z_small must be >= 7 (ANSI minimum), got {z_small}")
    if z_large < z_small:
        return _err(
            f"z_large ({z_large}) must be >= z_small ({z_small}); "
            "if driving up in speed swap the labels"
        )
    if n_strands < 1:
        return _err(f"n_strands must be >= 1, got {n_strands}")

    lt = str(load_type).strip().lower()
    if lt not in _CHAIN_SERVICE_FACTORS:
        return _err(
            f"load_type must be 'smooth', 'moderate', or 'heavy', got {load_type!r}"
        )
    Ks = _CHAIN_SERVICE_FACTORS[lt]

    H_nom = float(power_kW)
    H_d_total = H_nom * Ks
    H_d_strand = H_d_total / n_strands  # design power per strand

    n1 = float(n_small_rpm)
    zs = int(z_small)
    zl = int(z_large)
    speed_ratio = zl / zs

    # --- Chain selection ---
    if chain_no is not None:
        cn = str(chain_no).strip()
        if cn not in _CHAIN_TABLE:
            valid = list(_CHAIN_TABLE.keys())
            return _err(f"chain_no {chain_no!r} not recognised. Supported: {valid}")
    else:
        # Auto-select: smallest chain whose rated power >= H_d_strand at n1
        cn = None
        for cname in sorted(_CHAIN_TABLE.keys(), key=lambda x: _CHAIN_TABLE[x]["pitch_mm"]):
            hp_unit = _CHAIN_HP_PER_1000RPM[cname]  # hp at 1000 rpm
            kw_unit = hp_unit * 0.7457  # convert hp to kW
            rated_kw = kw_unit * (n1 / 1000.0) * (zs / 17.0)  # scale to actual teeth/speed
            if rated_kw >= H_d_strand:
                cn = cname
                break
        if cn is None:
            cn = "240"  # largest available
            warns.append(
                "no single ANSI chain in table meets the design power; "
                "consider multiple strands or a larger non-standard chain"
            )

    chain = _CHAIN_TABLE[cn]
    p_mm = chain["pitch_mm"]
    p_m = p_mm / 1000.0

    # --- Pitch diameters ---
    # d = p / sin(π / z)
    d_s = p_mm / math.sin(math.pi / zs)
    d_l = p_mm / math.sin(math.pi / zl)

    # --- Chain speed ---
    v = zs * p_mm * n1 / (60.0 * 1000.0)  # m/s

    # Lubrication regime
    if v <= _CHAIN_LUBE_A_MAX_M_S:
        lube = "type_A_drip"
    elif v <= _CHAIN_LUBE_B_MAX_M_S:
        lube = "type_B_bath"
    else:
        lube = "type_C_pump"
        warns.append(
            f"chain speed {v:.2f} m/s requires oil-pump (Type C) lubrication — "
            "ensure pump is sized for operating temperature"
        )

    max_rpm_B = chain["lube_B_rpm"]
    if n1 > max_rpm_B * 1.5:
        warns.append(
            f"sprocket speed {n1:.0f} rpm well above chain max rating "
            f"{max_rpm_B} rpm — consider smaller pitch chain or multi-strand"
        )

    # --- Initial centre distance estimate ---
    # Rule of thumb: C_p in [30, 50] pitches, Shigley §17-11
    C_p_init = 40.0  # pitches

    # --- Chain length in pitches (Shigley eq. 17-33) ---
    L_p_exact = (
        2.0 * C_p_init
        + (zl + zs) / 2.0
        + ((zl - zs) / (2.0 * math.pi)) ** 2 / C_p_init
    )
    # Round up to nearest even number (required for standard chain assembly)
    L_p = int(math.ceil(L_p_exact))
    if L_p % 2 != 0:
        L_p += 1

    # --- Back-compute actual centre distance from even L_p ---
    # C_p = [B + √(B² - 8·K²)] / 4
    # where B = L_p - (zl + zs)/2, K = (zl - zs)/(2π)
    K = (zl - zs) / (2.0 * math.pi)
    B = L_p - (zl + zs) / 2.0
    discr = B ** 2 - 8.0 * K ** 2
    if discr < 0:
        warns.append("chain geometry discriminant negative — using initial estimate")
        C_p = C_p_init
    else:
        C_p = (B + math.sqrt(discr)) / 4.0

    C_mm = C_p * p_mm

    # --- Rated power per strand ---
    hp_unit = _CHAIN_HP_PER_1000RPM[cn]
    kw_unit = hp_unit * 0.7457
    rated_kw_strand = kw_unit * (n1 / 1000.0) * (zs / 17.0)
    total_rated_kw = rated_kw_strand * n_strands

    if total_rated_kw < H_d_total:
        warns.append(
            f"selected chain {cn} with {n_strands} strand(s) rated {total_rated_kw:.2f} kW "
            f"< design power {H_d_total:.2f} kW — add strands or select heavier chain"
        )

    # --- Safety factor ---
    F_break = chain["break_N"]
    if v > 0:
        F_work = H_d_strand * 1000.0 / v  # N working tension per strand
    else:
        F_work = 0.0
    SF = F_break / F_work if F_work > 0 else float("inf")

    if SF < 7.0:
        warns.append(
            f"safety factor {SF:.1f} < 7 — chain may be undersized; "
            "consider next heavier chain or fewer teeth"
        )

    return {
        "ok": True,
        "chain_no": cn,
        "pitch_mm": p_mm,
        "design_power_kW": round(H_d_total, 4),
        "service_factor": round(Ks, 4),
        "speed_ratio": round(speed_ratio, 4),
        "z_small": zs,
        "z_large": zl,
        "d_small_mm": round(d_s, 3),
        "d_large_mm": round(d_l, 3),
        "chain_speed_m_s": round(v, 4),
        "chain_length_pitches": L_p,
        "center_distance_mm": round(C_mm, 2),
        "rated_power_per_strand_kW": round(rated_kw_strand, 4),
        "n_strands": n_strands,
        "total_rated_power_kW": round(total_rated_kw, 4),
        "breaking_load_N": F_break,
        "working_tension_N": round(F_work, 2),
        "safety_factor": round(SF, 2) if math.isfinite(SF) else "inf",
        "lubrication_regime": lube,
        "warnings": warns,
    }
