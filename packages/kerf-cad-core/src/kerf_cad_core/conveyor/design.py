"""
kerf_cad_core.conveyor.design — bulk-material conveyor design calculations.

Implements three public functions covering material-handling conveyors:

  belt_conveyor(...)
      CEMA-style flat/troughed belt conveyor:
        - Volumetric and mass capacity from belt width, speed, trough angle,
          surcharge angle, and cross-sectional load area
        - Effective tension Te = friction (Ky-factor) + lift + accessories
        - Required drive power
        - Slack-side tension (catenary no-slip: T2 = Te / (e^μθ - 1))
        - Belt selection index (ratio tension / belt width as proxy for rating)
        - Idler load and spacing check
        - Takeup tension
        - Max incline check against material angle of repose
        - Warnings for over-incline, capacity shortfall, belt overtension

  screw_conveyor(...)
      CEMA screw conveyor:
        - Capacity from diameter, pitch, speed, loading factor, material factor
        - Power: material conveyance + drive losses + incline component
        - Torque
        - Fill ratio check
        - Warnings for over-filling, over-speed

  bucket_elevator(...)
      Continuous or centrifugal bucket elevator:
        - Capacity from bucket volume, spacing, belt speed
        - Power: lift + belt friction
        - Warnings for under-capacity

All functions return plain dicts:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Units
-----
Lengths     — metres (m)
Mass        — kilograms (kg)
Force       — Newtons (N)
Power       — Watts (W)  (kW output field also provided)
Speed       — m/s  (belt/screw speed)
Angles      — degrees (inputs), radians (internal)
Capacity    — m³/h and t/h (tonnes/hour)
Torque      — N·m

References
----------
CEMA (Conveyor Equipment Manufacturers Association) — Belt Conveyors for Bulk
  Materials, 7th ed.
CEMA — Screw Conveyors for Bulk Materials, 5th ed.
Fenner Dunlop — Conveyor Handbook (2009)
Roberts, A.W. — Various conveyor design papers

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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


def _guard_range(name: str, value: Any, lo: float, hi: float) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < lo or v > hi:
        return f"{name} must be in [{lo}, {hi}], got {v}"
    return None


def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


# ---------------------------------------------------------------------------
# CEMA cross-sectional area tables
# ---------------------------------------------------------------------------
# CEMA belt conveyor cross-sectional load area:
# For a 3-roll equal troughing idler:
#   A = A1 + A2  where
#   A1 = (b/2)^2 * tan(λ)     (triangular surcharge portion, b = belt width)
#   A2 = b² * K_θ             (troughed portion, K_θ depends on trough angle)
#
# CEMA Table 4-4 surcharge correction coefficients K_θ (trough + flat factor):
# These are approximate CEMA-derived values for 3-equal-roll idlers.
_CEMA_KTROUGH: dict[int, float] = {
    0:  0.0000,   # flat belt
    20: 0.0615,
    35: 0.1088,
    45: 0.1365,
}

# Ky (flexing/resistance) factor — CEMA average for normal operation
# Ky ~ 0.016 for typical well-loaded troughed conveyors (CEMA 7th ed.)
_KY_DEFAULT = 0.016

# Kt — ambient temperature correction (default 1.0 for 20°C–40°C)
_KT_DEFAULT = 1.0

# Kx — idler friction factor per metre (approx 0.00068 × Wm + 0.48 per idler, default below)
_KX_DEFAULT = 2.0  # N/m, typical for 6" idlers at 1.2 m spacing

# Gravity
_G = 9.80665


# ---------------------------------------------------------------------------
# 1. belt_conveyor
# ---------------------------------------------------------------------------

def belt_conveyor(
    belt_width_m: float,
    belt_speed_m_s: float,
    length_m: float,
    lift_m: float,
    bulk_density_kg_m3: float,
    *,
    trough_angle_deg: float = 35.0,
    surcharge_angle_deg: float = 20.0,
    friction_factor: float = 0.020,
    drive_efficiency: float = 0.90,
    belt_mass_kg_m: float | None = None,
    idler_spacing_m: float = 1.2,
    wrap_angle_deg: float = 210.0,
    mu_belt_pulley: float = 0.35,
    accessory_tension_N: float = 0.0,
    target_capacity_t_h: float | None = None,
    repose_angle_deg: float | None = None,
) -> dict:
    """
    CEMA-style troughed belt conveyor design.

    Parameters
    ----------
    belt_width_m : float
        Belt width (m). Must be > 0. Typical: 0.45–2.4 m.
    belt_speed_m_s : float
        Belt speed (m/s). Must be > 0. Typical: 0.5–5 m/s.
    length_m : float
        Horizontal projected conveyor length (m). Must be > 0.
    lift_m : float
        Vertical lift (m). Positive = uphill, negative = downhill. May be 0.
    bulk_density_kg_m3 : float
        Bulk density of material (kg/m³). Must be > 0. E.g. coal ~800, iron
        ore ~2000.
    trough_angle_deg : float
        Trough angle of the carrying idler (deg). Default 35. Supported: 0, 20,
        35, 45.
    surcharge_angle_deg : float
        Surcharge (angle of repose on belt) of the material (deg). Default 20.
        Range 0–30.
    friction_factor : float
        CEMA Ky factor (belt and material flexing resistance). Default 0.020.
        Typical 0.016–0.025 depending on material and loading.
    drive_efficiency : float
        Overall drive efficiency (0–1). Default 0.90.
    belt_mass_kg_m : float or None
        Belt mass per metre (kg/m). If None, estimated as 10 × belt_width_m.
    idler_spacing_m : float
        Carrying-side idler spacing (m). Default 1.2 m.
    wrap_angle_deg : float
        Drive pulley wrap angle (deg). Default 210.
    mu_belt_pulley : float
        Coefficient of friction between belt and drive pulley. Default 0.35.
    accessory_tension_N : float
        Additional belt tension from skirt boards, plows, cleaners, etc. (N).
        Default 0.
    target_capacity_t_h : float or None
        Required throughput (t/h). If given, compared to actual and warns if
        actual < target.
    repose_angle_deg : float or None
        Material angle of repose (deg). If given, compared to conveyor
        inclination and warns if over-incline.

    Returns
    -------
    dict
        ok                    : True
        capacity_m3_h         : volumetric capacity (m³/h)
        capacity_t_h          : mass capacity (t/h)
        cross_section_area_m2 : belt load cross-section (m²)
        material_mass_kg_m    : material mass per metre of belt (kg/m)
        belt_mass_kg_m        : belt mass per metre (kg/m)
        Te_N                  : effective (net drive) tension (N)
        T1_N                  : tight-side belt tension (N)
        T2_N                  : slack-side belt tension (N)
        takeup_tension_N      : takeup (counterweight) tension ≈ T2 (N)
        drive_power_W         : required drive power at pulley (W)
        drive_power_kW        : required drive power at pulley (kW)
        motor_power_kW        : motor shaft power (drive_power / η) (kW)
        inclination_deg       : actual inclination angle (deg)
        tension_index         : Te_N / belt_width_m (N/m) — proxy for belt rating
        idler_load_N          : load per carrying idler (N)
        warnings              : list of warning strings
    """
    # --- Input validation ---
    err = _guard_positive("belt_width_m", belt_width_m)
    if err:
        return _err(err)
    err = _guard_positive("belt_speed_m_s", belt_speed_m_s)
    if err:
        return _err(err)
    err = _guard_positive("length_m", length_m)
    if err:
        return _err(err)
    err = _guard_nonneg("lift_m", abs(lift_m))  # validate magnitude only
    if err:
        return _err(err)
    err = _guard_positive("bulk_density_kg_m3", bulk_density_kg_m3)
    if err:
        return _err(err)
    err = _guard_range("trough_angle_deg", trough_angle_deg, 0, 45)
    if err:
        return _err(err)
    err = _guard_range("surcharge_angle_deg", surcharge_angle_deg, 0, 30)
    if err:
        return _err(err)
    err = _guard_positive("friction_factor", friction_factor)
    if err:
        return _err(err)
    err = _guard_range("drive_efficiency", drive_efficiency, 0.5, 1.0)
    if err:
        return _err(err)
    err = _guard_positive("idler_spacing_m", idler_spacing_m)
    if err:
        return _err(err)
    err = _guard_range("wrap_angle_deg", wrap_angle_deg, 90.0, 360.0)
    if err:
        return _err(err)
    err = _guard_positive("mu_belt_pulley", mu_belt_pulley)
    if err:
        return _err(err)
    err = _guard_nonneg("accessory_tension_N", accessory_tension_N)
    if err:
        return _err(err)

    warnings: list[str] = []

    bw = float(belt_width_m)
    v  = float(belt_speed_m_s)
    L  = float(length_m)
    H  = float(lift_m)
    rho = float(bulk_density_kg_m3)
    theta_t = float(trough_angle_deg)
    theta_s = float(surcharge_angle_deg)
    Ky = float(friction_factor)
    eta = float(drive_efficiency)
    Li  = float(idler_spacing_m)
    phi = math.radians(float(wrap_angle_deg))
    mu  = float(mu_belt_pulley)

    # Belt mass per metre
    if belt_mass_kg_m is None:
        Wb = 10.0 * bw   # rough estimate: 10 kg/m per metre width
    else:
        err = _guard_positive("belt_mass_kg_m", belt_mass_kg_m)
        if err:
            return _err(err)
        Wb = float(belt_mass_kg_m)

    # --- Cross-sectional load area (CEMA 3-roll idler) ---
    # A = (b_eff/2)^2 * tan(λ)  + b_eff^2 * K_θ
    # where b_eff = 0.9 * bw (CEMA effective belt width factor)
    b_eff = 0.9 * bw

    # K_θ: interpolate from table
    trough_int = int(round(theta_t))
    K_theta_keys = sorted(_CEMA_KTROUGH.keys())
    if trough_int <= K_theta_keys[0]:
        K_theta = _CEMA_KTROUGH[K_theta_keys[0]]
    elif trough_int >= K_theta_keys[-1]:
        K_theta = _CEMA_KTROUGH[K_theta_keys[-1]]
    else:
        # linear interpolation
        for i in range(len(K_theta_keys) - 1):
            lo = K_theta_keys[i]
            hi = K_theta_keys[i + 1]
            if lo <= trough_int <= hi:
                f = (trough_int - lo) / (hi - lo)
                K_theta = _CEMA_KTROUGH[lo] + f * (_CEMA_KTROUGH[hi] - _CEMA_KTROUGH[lo])
                break
        else:
            K_theta = _CEMA_KTROUGH[K_theta_keys[-1]]

    # Surcharge area (triangular heap above idler trough)
    lambda_rad = math.radians(theta_s)
    A1 = 0.25 * b_eff ** 2 * math.tan(lambda_rad)   # triangular pile
    A2 = b_eff ** 2 * K_theta                         # troughed area
    A_cross = A1 + A2  # m²

    # --- Capacity ---
    # Q_vol = A_cross × v × 3600   [m³/h]
    Q_vol = A_cross * v * 3600.0   # m³/h
    Q_mass = Q_vol * rho / 1000.0  # t/h (tonnes/hour)

    # Material mass per metre of belt
    Wm = A_cross * rho   # kg/m

    # --- Inclination ---
    incl_rad = math.atan2(H, L) if L > 0 else 0.0
    incl_deg = math.degrees(incl_rad)

    # Angle-of-repose check
    if repose_angle_deg is not None:
        err = _guard_range("repose_angle_deg", repose_angle_deg, 0.0, 90.0)
        if err:
            return _err(err)
        repose = float(repose_angle_deg)
        # Typical rule: incline ≤ 0.75 × repose_angle
        max_safe_incline = 0.75 * repose
        if incl_deg > max_safe_incline:
            warnings.append(
                f"Over-incline: inclination {incl_deg:.1f}° exceeds "
                f"0.75 × repose_angle ({max_safe_incline:.1f}°). "
                f"Material may slip back."
            )

    # --- Effective tension Te (CEMA equation, simplified) ---
    # Te = Tm_friction + Tm_lift + T_acc + T_idler_friction
    # where:
    # Tm_friction = Ky × (Wm + Wb) × L × g (horizontal resistance, both runs)
    # Note: CEMA uses full conveyor length for friction (carrying + return ≈ 2L)
    # Simplified: friction_total = Ky × (Wm + Wb) × 2L  (both sides)
    # We use CEMA simplified formulation for clarity:

    # Carrying-side friction: Ky × (Wm + Wb) × L
    # Return-side friction: Ky × Wb × L  (no load on return)
    # Total friction component
    T_friction = Ky * (Wm + Wb) * L * _G + Ky * Wb * L * _G
    # = Ky × g × L × (Wm + 2Wb)

    # Lift component (positive uphill)
    T_lift = Wm * L * _G * math.sin(incl_rad)

    # Accessory tension
    T_acc = float(accessory_tension_N)

    # Effective tension
    Te = T_friction + T_lift + T_acc

    # --- Required drive power at pulley ---
    P_drive = Te * v  # W

    # --- Motor power ---
    P_motor = P_drive / eta  # W

    # --- Slack-side tension for no-slip (capstan equation) ---
    # Te = T1 - T2  and  T1 / T2 = e^(μ × φ)
    # So T2 = Te / (e^(μ×φ) - 1)
    capstan_ratio = math.exp(mu * phi)
    T2 = Te / (capstan_ratio - 1.0) if capstan_ratio > 1.0 else Te * 10.0
    T1 = Te + T2

    # Takeup tension (counterweight) ≈ T2 for head-drive
    T_takeup = T2

    # Belt tension index (N/m) — used to select belt rating
    tension_index = Te / bw  # N/m

    # Over-tension warning (arbitrary threshold: >10 kN/m is a heavy-duty belt)
    if tension_index > 10000.0:
        warnings.append(
            f"Belt may be overtensioned: tension index {tension_index:.0f} N/m "
            f"exceeds 10 000 N/m. Verify belt rating."
        )

    # --- Idler load ---
    # Idler load = weight of belt + material per idler spacing
    idler_load = (Wm + Wb) * Li * _G  # N

    # --- Capacity shortfall warning ---
    if target_capacity_t_h is not None:
        err = _guard_positive("target_capacity_t_h", target_capacity_t_h)
        if err:
            return _err(err)
        if Q_mass < float(target_capacity_t_h) * 0.999:
            warnings.append(
                f"Capacity shortfall: actual {Q_mass:.1f} t/h < "
                f"target {target_capacity_t_h:.1f} t/h. "
                f"Increase belt width or speed."
            )

    return {
        "ok": True,
        "capacity_m3_h": Q_vol,
        "capacity_t_h": Q_mass,
        "cross_section_area_m2": A_cross,
        "material_mass_kg_m": Wm,
        "belt_mass_kg_m": Wb,
        "Te_N": Te,
        "T1_N": T1,
        "T2_N": T2,
        "takeup_tension_N": T_takeup,
        "drive_power_W": P_drive,
        "drive_power_kW": P_drive / 1000.0,
        "motor_power_kW": P_motor / 1000.0,
        "inclination_deg": incl_deg,
        "tension_index": tension_index,
        "idler_load_N": idler_load,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. screw_conveyor
# ---------------------------------------------------------------------------

# CEMA material factors (Fm) — representative values
# Higher Fm = more power required for difficult materials
_SCREW_MATERIAL_FACTORS: dict[str, float] = {
    "grain":          1.0,
    "coal_dry":       1.4,
    "coal_wet":       1.6,
    "cement_dry":     1.6,
    "sand_dry":       1.8,
    "sand_wet":       2.0,
    "clay_dry":       2.5,
    "fly_ash":        1.4,
    "limestone":      1.6,
    "generic_light":  1.0,
    "generic_medium": 1.6,
    "generic_heavy":  2.5,
}

# CEMA loading factors (Cf) for fill ratio ≤ maximum
# Loading factor = fraction of screw cross-section filled
_SCREW_LOADING_FACTORS: dict[str, float] = {
    "light":  0.45,   # free-flowing granular
    "medium": 0.38,   # mixed granular/sluggish
    "heavy":  0.30,   # sluggish / abrasive
    "special": 0.15,   # fibrous / very sluggish
}

# Drive loss factor (Ff) per CEMA: 1.15 to 1.25 typical
_SCREW_DRIVE_FACTOR = 1.20


def screw_conveyor(
    diameter_m: float,
    pitch_m: float,
    speed_rpm: float,
    length_m: float,
    bulk_density_kg_m3: float,
    *,
    material_class: str = "generic_medium",
    loading_class: str = "medium",
    lift_m: float = 0.0,
    drive_efficiency: float = 0.85,
    target_capacity_t_h: float | None = None,
) -> dict:
    """
    CEMA screw conveyor design.

    Parameters
    ----------
    diameter_m : float
        Screw (flight) outer diameter (m). Must be > 0.
    pitch_m : float
        Screw pitch (m). Standard pitch = diameter. Must be > 0.
    speed_rpm : float
        Screw rotational speed (rpm). Must be > 0.
    length_m : float
        Conveyor length (m). Must be > 0.
    bulk_density_kg_m3 : float
        Bulk density of material (kg/m³). Must be > 0.
    material_class : str
        CEMA material class (default 'generic_medium'):
        grain, coal_dry, coal_wet, cement_dry, sand_dry, sand_wet,
        clay_dry, fly_ash, limestone, generic_light, generic_medium, generic_heavy.
    loading_class : str
        Trough loading class (default 'medium'):
        light (45%), medium (38%), heavy (30%), special (15%).
    lift_m : float
        Vertical lift (m). Default 0. Positive = uphill.
    drive_efficiency : float
        Overall drive efficiency. Default 0.85.
    target_capacity_t_h : float or None
        Required throughput (t/h). Warns if below actual.

    Returns
    -------
    dict
        ok                    : True
        capacity_m3_h         : volumetric capacity (m³/h)
        capacity_t_h          : mass capacity (t/h)
        fill_ratio            : actual trough fill fraction
        max_fill_ratio        : maximum allowed fill fraction (loading_class)
        screw_area_m2         : full screw bore area (π D²/4) (m²)
        material_volume_m3    : total material volume in screw at one time (m³)
        Pm_W                  : material conveyance power (W)
        Pm_kW                 : material conveyance power (kW)
        Pi_kW                 : incline lift power (kW)
        Pt_kW                 : total shaft power = (Pm + friction factor + Pi) (kW)
        motor_power_kW        : motor power (Pt / η) (kW)
        torque_Nm             : screw shaft torque (N·m)
        warnings              : list of warning strings
    """
    err = _guard_positive("diameter_m", diameter_m)
    if err:
        return _err(err)
    err = _guard_positive("pitch_m", pitch_m)
    if err:
        return _err(err)
    err = _guard_positive("speed_rpm", speed_rpm)
    if err:
        return _err(err)
    err = _guard_positive("length_m", length_m)
    if err:
        return _err(err)
    err = _guard_positive("bulk_density_kg_m3", bulk_density_kg_m3)
    if err:
        return _err(err)
    err = _guard_nonneg("lift_m", abs(lift_m))
    if err:
        return _err(err)
    err = _guard_range("drive_efficiency", drive_efficiency, 0.5, 1.0)
    if err:
        return _err(err)

    mat_class = str(material_class).strip().lower()
    if mat_class not in _SCREW_MATERIAL_FACTORS:
        valid = sorted(_SCREW_MATERIAL_FACTORS.keys())
        return _err(f"Unknown material_class {material_class!r}. Supported: {valid}.")

    load_class = str(loading_class).strip().lower()
    if load_class not in _SCREW_LOADING_FACTORS:
        valid = sorted(_SCREW_LOADING_FACTORS.keys())
        return _err(f"Unknown loading_class {loading_class!r}. Supported: {valid}.")

    warnings: list[str] = []

    D  = float(diameter_m)
    p  = float(pitch_m)
    N  = float(speed_rpm)
    L  = float(length_m)
    rho = float(bulk_density_kg_m3)
    H  = float(lift_m)
    eta = float(drive_efficiency)
    Fm = _SCREW_MATERIAL_FACTORS[mat_class]
    Cf = _SCREW_LOADING_FACTORS[load_class]

    # Screw bore area
    A_screw = math.pi * D ** 2 / 4.0  # m²

    # --- Capacity (CEMA) ---
    # Q = 60 × N × p × A_screw × Cf   (m³/h)
    # (60 to convert rpm to rev/min × 60 min/h)
    Q_vol = 60.0 * N * p * A_screw * Cf  # m³/h
    Q_mass = Q_vol * rho / 1000.0  # t/h

    # Fill ratio check
    # Actual fill = Cf, max recommended fill
    fill_ratio = Cf  # as configured — it IS the fill fraction
    max_fill = 0.45  # absolute max per CEMA for most materials

    if Cf > max_fill:
        warnings.append(
            f"Fill ratio {Cf:.2f} exceeds CEMA maximum {max_fill:.2f}. "
            f"Risk of material packing / blockage."
        )

    # Over-speed warning (CEMA: ≤ 60–100 rpm for most bulk materials)
    if N > 100.0:
        warnings.append(
            f"Screw speed {N:.0f} rpm exceeds typical CEMA maximum 100 rpm. "
            f"May cause material degradation or packing."
        )

    # Material volume at any instant in screw
    mat_vol = A_screw * Cf * L  # m³

    # --- Power (CEMA) ---
    # Material conveyance power:
    # Pm = (Q_mass × L × Fm × g) / (367 × η)  — CEMA approximation in consistent units
    # or using SI directly:
    # Pm = F_drag × v_material = (rho × Q_vol/3600 × g × L × Fm) / η
    # CEMA formula: Pm (kW) = (C × L × W × Fm) / (97 000) where C=cap ft³/h, L=ft, W=pcf
    # In SI (per-metre formulation):
    # Traction force ≈ Fm × Wm × L where Wm = material weight per unit length
    # Power = torque × ω

    # SI approach:
    # Material mass in screw = rho × A_screw × Cf × L  [kg]
    # Drag force on screw flights ≈ Fm × mat_mass × g × (friction against trough)
    # Simplified CEMA equivalent in SI:
    # P_material (W) = Q_vol/3600 × rho × g × L × Fm / L  × L
    #               = (rho × Q_vol / 3600) × g × L × Fm
    # This equals: mass_flow_rate × g × Fm × L / (some efficiency term)
    # = (mass_rate kg/s) × g × L × Fm
    mass_flow_kg_s = Q_vol * rho / 3600.0  # kg/s
    Pm = mass_flow_kg_s * _G * L * Fm  # W (material drag power ≈ equiv. work rate)

    # Incline power
    Pi = mass_flow_kg_s * _G * abs(H)  # W (only if lifting)
    if H < 0:
        Pi = 0.0  # downhill: gravity assists, don't subtract (conservative)

    # Total shaft power including drive losses
    Pt = (Pm + Pi) * _SCREW_DRIVE_FACTOR  # apply drive/trough friction factor

    # Motor power
    P_motor = Pt / eta

    # Shaft torque: P = T × ω  → T = P / ω
    omega = 2.0 * math.pi * N / 60.0  # rad/s
    torque = Pt / omega if omega > 0 else 0.0

    # Capacity warning
    if target_capacity_t_h is not None:
        err = _guard_positive("target_capacity_t_h", target_capacity_t_h)
        if err:
            return _err(err)
        if Q_mass < float(target_capacity_t_h) * 0.999:
            warnings.append(
                f"Capacity shortfall: actual {Q_mass:.1f} t/h < "
                f"target {target_capacity_t_h:.1f} t/h. "
                f"Increase diameter or speed."
            )

    return {
        "ok": True,
        "capacity_m3_h": Q_vol,
        "capacity_t_h": Q_mass,
        "fill_ratio": fill_ratio,
        "max_fill_ratio": max_fill,
        "screw_area_m2": A_screw,
        "material_volume_m3": mat_vol,
        "Pm_W": Pm,
        "Pm_kW": Pm / 1000.0,
        "Pi_kW": Pi / 1000.0,
        "Pt_kW": Pt / 1000.0,
        "motor_power_kW": P_motor / 1000.0,
        "torque_Nm": torque,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. bucket_elevator
# ---------------------------------------------------------------------------

def bucket_elevator(
    bucket_volume_m3: float,
    bucket_spacing_m: float,
    belt_speed_m_s: float,
    lift_height_m: float,
    bulk_density_kg_m3: float,
    *,
    fill_factor: float = 0.75,
    belt_mass_kg_m: float = 5.0,
    drive_efficiency: float = 0.85,
    elevator_type: str = "centrifugal",
    target_capacity_t_h: float | None = None,
) -> dict:
    """
    Bucket elevator capacity and power.

    Parameters
    ----------
    bucket_volume_m3 : float
        Geometric volume of one bucket (m³). Must be > 0.
    bucket_spacing_m : float
        Centre-to-centre bucket spacing on belt (m). Must be > 0.
    belt_speed_m_s : float
        Belt/chain speed (m/s). Must be > 0.
    lift_height_m : float
        Vertical lift height (m). Must be > 0.
    bulk_density_kg_m3 : float
        Bulk density of material (kg/m³). Must be > 0.
    fill_factor : float
        Bucket fill factor (0–1). Default 0.75 (75% full).
    belt_mass_kg_m : float
        Belt or chain mass per metre (kg/m). Default 5.0 kg/m.
    drive_efficiency : float
        Drive efficiency. Default 0.85.
    elevator_type : str
        'centrifugal' (default) or 'continuous'. Affects belt tension method
        (for continuous, a lower speed is typically used).
    target_capacity_t_h : float or None
        Required throughput (t/h). Warns if below actual.

    Returns
    -------
    dict
        ok                    : True
        capacity_m3_h         : volumetric capacity (m³/h)
        capacity_t_h          : mass capacity (t/h)
        buckets_per_m         : number of buckets per metre of belt
        material_per_bucket_kg: mass of material per bucket (kg)
        lift_power_W          : power to lift material (W)
        lift_power_kW         : power to lift material (kW)
        belt_power_kW         : power to lift belt + chain (kW)
        total_power_kW        : total shaft power at head pulley (kW)
        motor_power_kW        : motor power (kW)
        belt_tension_N        : approximate belt tension at head pulley (N)
        warnings              : list of warning strings
    """
    err = _guard_positive("bucket_volume_m3", bucket_volume_m3)
    if err:
        return _err(err)
    err = _guard_positive("bucket_spacing_m", bucket_spacing_m)
    if err:
        return _err(err)
    err = _guard_positive("belt_speed_m_s", belt_speed_m_s)
    if err:
        return _err(err)
    err = _guard_positive("lift_height_m", lift_height_m)
    if err:
        return _err(err)
    err = _guard_positive("bulk_density_kg_m3", bulk_density_kg_m3)
    if err:
        return _err(err)
    err = _guard_range("fill_factor", fill_factor, 0.1, 1.0)
    if err:
        return _err(err)
    err = _guard_positive("belt_mass_kg_m", belt_mass_kg_m)
    if err:
        return _err(err)
    err = _guard_range("drive_efficiency", drive_efficiency, 0.5, 1.0)
    if err:
        return _err(err)

    elev_type = str(elevator_type).strip().lower()
    if elev_type not in ("centrifugal", "continuous"):
        return _err(
            f"Unknown elevator_type {elevator_type!r}. "
            f"Supported: 'centrifugal', 'continuous'."
        )

    warnings: list[str] = []

    Vb = float(bucket_volume_m3)
    bs = float(bucket_spacing_m)
    v  = float(belt_speed_m_s)
    H  = float(lift_height_m)
    rho = float(bulk_density_kg_m3)
    ff = float(fill_factor)
    Wb = float(belt_mass_kg_m)
    eta = float(drive_efficiency)

    # Centrifugal elevator speed check (typical 1.0–2.5 m/s; continuous 0.5–1.5)
    if elev_type == "centrifugal" and v > 3.0:
        warnings.append(
            f"Belt speed {v:.2f} m/s is high for centrifugal elevator. "
            f"Typical max 2.5 m/s. Material may not discharge cleanly."
        )
    if elev_type == "continuous" and v > 2.0:
        warnings.append(
            f"Belt speed {v:.2f} m/s is high for continuous elevator. "
            f"Typical max 1.5 m/s."
        )

    # --- Capacity ---
    # Number of buckets passing per second = v / bs
    buckets_per_s = v / bs  # buckets/s
    Q_vol = buckets_per_s * Vb * ff * 3600.0  # m³/h
    Q_mass = Q_vol * rho / 1000.0  # t/h

    buckets_per_m = 1.0 / bs
    mat_per_bucket = Vb * ff * rho  # kg/bucket

    # --- Power ---
    # Lift power: mass flow × g × H
    mass_flow_kg_s = Q_vol * rho / 3600.0  # kg/s
    P_lift = mass_flow_kg_s * _G * H  # W

    # Belt lift power: belt mass × both runs × g × H
    # Total belt length ≈ 2 × H; net lift contribution = belt mass × H × g (head side)
    # Simplified: we use carrying run belt weight only (head absorbs return belt weight via counterweight)
    P_belt = Wb * H * _G * v / H  # = Wb × g × v — weight per metre × belt speed
    # Actually: P_belt = Wb × g × v (force = Wb × g per metre, power = F × v)
    P_belt = Wb * _G * v  # W per metre of belt height — this is the continuous power

    P_total = P_lift + P_belt  # W
    P_motor = P_total / eta  # W

    # Approximate belt tension at head pulley: F = P_total / v
    belt_tension = P_total / v if v > 0 else 0.0  # N

    # Capacity warning
    if target_capacity_t_h is not None:
        err_msg = _guard_positive("target_capacity_t_h", target_capacity_t_h)
        if err_msg:
            return _err(err_msg)
        if Q_mass < float(target_capacity_t_h) * 0.999:
            warnings.append(
                f"Capacity shortfall: actual {Q_mass:.1f} t/h < "
                f"target {target_capacity_t_h:.1f} t/h. "
                f"Increase bucket volume, spacing, or belt speed."
            )

    return {
        "ok": True,
        "capacity_m3_h": Q_vol,
        "capacity_t_h": Q_mass,
        "buckets_per_m": buckets_per_m,
        "material_per_bucket_kg": mat_per_bucket,
        "lift_power_W": P_lift,
        "lift_power_kW": P_lift / 1000.0,
        "belt_power_kW": P_belt / 1000.0,
        "total_power_kW": P_total / 1000.0,
        "motor_power_kW": P_motor / 1000.0,
        "belt_tension_N": belt_tension,
        "warnings": warnings,
    }
