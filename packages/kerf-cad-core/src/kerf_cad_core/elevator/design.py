"""
kerf_cad_core.elevator.design — vertical-transportation engineering calculations.

Implements seven public functions covering passenger/goods lifts and escalators:

  traction_lift(...)
      Traction lift roping analysis:
        - 1:1 and 2:1 roping configurations
        - Counterweight balance percentage and overbalance
        - Traction ratio T1/T2 check vs e^(fα) limit (EN 81-1 §9.3)
        - Rope count, diameter and minimum traction sheave D/d ratio
        - Suspension warnings: inadequate traction, excessive fleet angle

  hydraulic_lift(...)
      Hydraulic (direct / indirect) lift:
        - Jack/cylinder force from car + rated load + roping ratio
        - Pump flow rate from piston area and car speed
        - Motor/pump power
        - Working pressure and proof pressure
        - Warnings: excessive pressure, low pump efficiency

  motor_power(...)
      Traction motor power from balanced-load method:
        - Net force at no-load and full-load
        - Motor power = (unbalanced force × speed) / efficiency
        - Duty cycle and starts-per-hour thermal derating
        - Continuous equivalent motor power

  kinematics(...)
      Travel kinematics with trapezoidal or S-curve jerk profile:
        - Acceleration / jerk profile
        - Time to rated speed (acceleration phase)
        - Flight time for a given floor height
        - Floor-to-floor time (acceleration + constant speed + deceleration)
        - Warnings: excessive jerk/acceleration, floor shorter than accel distance

  traffic_analysis(...)
      CIBSE Guide D round-trip time (RTT) traffic analysis:
        - Probable stops S and highest reversal floor H (Barney formula)
        - Round-trip time RTT (s)
        - Average interval (s) and 5-minute handling capacity (%)
        - Cars required for a target interval
        - Warnings: interval too long, handling capacity shortfall

  buffer_stroke(...)
      EN 81-1 buffer stroke and overspeed governor trip speed:
        - Minimum oil/polyurethane buffer stroke from rated + overrun speed
        - Overspeed governor minimum tripping speed
        - Safety gear deceleration distance

  escalator(...)
      Escalator / moving walk:
        - Step width × speed → theoretical persons/hour capacity
        - Actual capacity with utilisation factor
        - Truss incline angle check (EN 115 limits: 30° / 35° for escalators)
        - Drive power = mass flow × g × vertical rise + horizontal friction
        - Warnings: over-incline, under-capacity, excessive speed

All functions return plain dicts:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Units
-----
Lengths     — metres (m)
Mass        — kilograms (kg)
Force       — Newtons (N)
Power       — Watts (W); kW output field also provided
Speed       — m/s
Pressure    — Pascals (Pa); MPa output also provided
Flow        — m³/s; L/min output also provided
Angles      — degrees (inputs), radians (internal)
Time        — seconds (s)

References
----------
CIBSE Guide D: Transportation Systems in Buildings, 4th ed.
EN 81-1:1998+A3:2009 — Safety rules for electric traction lifts
EN 81-2:1998+A3:2009 — Safety rules for hydraulic lifts
EN 115-1:2017 — Safety of escalators and moving walks
ISO 4190-1:2010 — Lift installations — Part 1: Classes I, II, III and VI
Barney, G.C. — Elevator Traffic Handbook (2003)
Strakosch, G.R. — The Vertical Transportation Handbook, 4th ed.

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_G = 9.80665  # m/s²

# EN 81-1 Table 9.1: groove factor K for undercut / semi-circular grooves.
# We use a representative value: k=1 for semi-circular groove (conservative).
# Users can override the traction coefficient μ.

# CIBSE Guide D default average inter-floor height for population estimates
_DEFAULT_FLOOR_HEIGHT_M = 3.3  # m


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
# 1. traction_lift
# ---------------------------------------------------------------------------

def traction_lift(
    rated_load_kg: float,
    car_mass_kg: float,
    rated_speed_m_s: float,
    *,
    roping: int = 1,
    counterweight_balance_pct: float = 50.0,
    mu: float = 0.09,
    groove_angle_deg: float = 40.0,
    wrap_angle_deg: float = 180.0,
    n_ropes: int | None = None,
    rope_diameter_mm: float = 13.0,
    sheave_diameter_mm: float | None = None,
) -> dict:
    """
    Traction lift roping and traction safety analysis.

    Parameters
    ----------
    rated_load_kg : float
        Rated payload (kg). Must be > 0.
    car_mass_kg : float
        Empty car mass (kg). Must be > 0.
    rated_speed_m_s : float
        Rated car speed (m/s). Must be > 0.
    roping : int
        Roping ratio: 1 for 1:1 (direct), 2 for 2:1 (indirect). Default 1.
    counterweight_balance_pct : float
        Counterweight expressed as car_mass + balance_pct × rated_load.
        Balance percentage (%). Default 50 (counterweights 50% of rated load).
        Range 40–55 %.
    mu : float
        Equivalent coefficient of friction between rope and sheave groove.
        Default 0.09 for grooved sheave (EN 81-1 §9.3). Typical 0.07–0.12.
    groove_angle_deg : float
        Half-angle of V-groove (°). Default 40°. For semicircular groove use 90°.
    wrap_angle_deg : float
        Rope wrap angle on traction sheave (°). Default 180°.
    n_ropes : int or None
        Number of suspension ropes. If None, recommended minimum computed.
    rope_diameter_mm : float
        Nominal rope diameter (mm). Default 13 mm.
    sheave_diameter_mm : float or None
        Traction sheave pitch diameter (mm). If None, minimum D/d = 40 is applied.

    Returns
    -------
    dict
        ok                         : True
        counterweight_mass_kg      : CW mass (kg)
        car_side_force_full_N      : car side rope tension, full load (N)
        car_side_force_empty_N     : car side rope tension, empty car (N)
        cw_side_force_N            : counterweight side rope tension (N)
        traction_ratio_full        : T1/T2 (full load ascending — worst case)
        traction_ratio_empty       : T1/T2 (empty car ascending — worst case)
        traction_limit             : e^(μ_eff × α) limit
        traction_adequate_full     : True if ratio_full <= limit
        traction_adequate_empty    : True if ratio_empty <= limit
        n_ropes_recommended        : minimum rope count (EN 81-1 §9.2)
        rope_diameter_mm           : rope diameter used (mm)
        sheave_diameter_mm         : traction sheave diameter (mm)
        sheave_D_d_ratio           : sheave_diameter / rope_diameter
        overbalance_kg             : CW overbalance above half-load (kg)
        warnings                   : list of warning strings
    """
    err = _guard_positive("rated_load_kg", rated_load_kg)
    if err:
        return _err(err)
    err = _guard_positive("car_mass_kg", car_mass_kg)
    if err:
        return _err(err)
    err = _guard_positive("rated_speed_m_s", rated_speed_m_s)
    if err:
        return _err(err)
    if roping not in (1, 2):
        return _err(f"roping must be 1 or 2, got {roping!r}")
    err = _guard_range("counterweight_balance_pct", counterweight_balance_pct, 35.0, 65.0)
    if err:
        return _err(err)
    err = _guard_range("mu", mu, 0.01, 0.35)
    if err:
        return _err(err)
    err = _guard_range("groove_angle_deg", groove_angle_deg, 10.0, 90.0)
    if err:
        return _err(err)
    err = _guard_range("wrap_angle_deg", wrap_angle_deg, 90.0, 360.0)
    if err:
        return _err(err)
    err = _guard_positive("rope_diameter_mm", rope_diameter_mm)
    if err:
        return _err(err)
    if n_ropes is not None:
        err = _guard_range("n_ropes", n_ropes, 1, 20)
        if err:
            return _err(err)
    if sheave_diameter_mm is not None:
        err = _guard_positive("sheave_diameter_mm", sheave_diameter_mm)
        if err:
            return _err(err)

    warnings: list[str] = []

    Q   = float(rated_load_kg)
    M_c = float(car_mass_kg)
    v   = float(rated_speed_m_s)
    bal = float(counterweight_balance_pct) / 100.0  # fraction
    rope_d = float(rope_diameter_mm)

    # Counterweight mass
    M_cw = M_c + bal * Q  # kg

    # Overbalance (mass above 50 % balance)
    overbalance = M_cw - (M_c + 0.5 * Q)  # kg

    # Suspension forces at roping ratio
    # For 2:1 roping the sheave tension = total weight / 2
    # but for traction ratio we compare the loads on either side of the sheave.
    # Car side (full load): W_car_full = (M_c + Q) × g
    # Car side (empty):     W_car_empty = M_c × g
    # CW side:              W_cw = M_cw × g
    # Factor = 1 for 1:1; = 0.5 for 2:1 (because the load divides between two ropes)

    rope_factor = 1.0 / roping  # rope tension = weight × rope_factor

    F_car_full  = (M_c + Q)  * _G * rope_factor  # N
    F_car_empty = M_c        * _G * rope_factor  # N
    F_cw        = M_cw       * _G * rope_factor  # N

    # Effective mu for groove shape (EN 81-1 §9.3):
    # For a V-groove: μ_eff = μ / sin(β)  where β = groove half-angle
    # For a semicircular groove (β=90°): μ_eff = μ
    beta_rad = math.radians(float(groove_angle_deg))
    if abs(groove_angle_deg - 90.0) < 0.01:
        mu_eff = float(mu)
    else:
        mu_eff = float(mu) / math.sin(beta_rad)

    alpha_rad = math.radians(float(wrap_angle_deg))
    e_mu_alpha = math.exp(mu_eff * alpha_rad)

    # Traction ratio: ascending car full load → car side is heavy (T1), CW is light (T2)
    #   T1 = F_car_full, T2 = F_cw  → must satisfy T1/T2 <= e^(μ_eff × α)
    # Ascending car empty → CW is heavy (T1), car side is light (T2)
    #   T1 = F_cw, T2 = F_car_empty
    ratio_full  = F_car_full  / F_cw        if F_cw        > 0 else float("inf")
    ratio_empty = F_cw        / F_car_empty if F_car_empty > 0 else float("inf")

    traction_ok_full  = ratio_full  <= e_mu_alpha
    traction_ok_empty = ratio_empty <= e_mu_alpha

    if not traction_ok_full:
        warnings.append(
            f"Inadequate traction (full load): T1/T2={ratio_full:.3f} > "
            f"e^(μ_eff·α)={e_mu_alpha:.3f}. Increase wrap angle, groove angle, "
            f"or friction coefficient."
        )
    if not traction_ok_empty:
        warnings.append(
            f"Inadequate traction (empty car): T1/T2={ratio_empty:.3f} > "
            f"e^(μ_eff·α)={e_mu_alpha:.3f}. Adjust counterweight balance or "
            f"increase traction."
        )

    # Counterweight balance warning
    if float(counterweight_balance_pct) < 40.0 or float(counterweight_balance_pct) > 55.0:
        warnings.append(
            f"Balance percentage {counterweight_balance_pct:.1f}% is outside the "
            f"recommended 40–55% range (CIBSE Guide D)."
        )

    # Rope count recommendation (EN 81-1 §9.2: minimum 3 ropes; for speeds > 3.5 m/s
    # typically 4+ ropes; a minimum based on total suspended load is used here).
    # Simplified: use 3 ropes as absolute minimum; for Q > 1000 kg use 4+.
    min_ropes = 3 if Q <= 1000.0 else 4
    if n_ropes is None:
        n_ropes_used = min_ropes
    else:
        n_ropes_used = int(n_ropes)
        if n_ropes_used < 3:
            warnings.append(
                f"n_ropes={n_ropes_used} is below the EN 81-1 minimum of 3."
            )

    # Sheave diameter
    # EN 81-1 §9.7: D/d >= 40 for roping 1:1; >= 40 for 2:1 as well (common practice).
    min_D_d = 40.0
    min_sheave_mm = min_D_d * rope_d
    if sheave_diameter_mm is None:
        sheave_mm = min_sheave_mm
    else:
        sheave_mm = float(sheave_diameter_mm)
        if sheave_mm < min_sheave_mm:
            warnings.append(
                f"Traction sheave diameter {sheave_mm:.0f} mm gives D/d="
                f"{sheave_mm/rope_d:.1f} < minimum {min_D_d:.0f} (EN 81-1 §9.7)."
            )

    D_d_ratio = sheave_mm / rope_d

    return {
        "ok": True,
        "counterweight_mass_kg": M_cw,
        "car_side_force_full_N": F_car_full,
        "car_side_force_empty_N": F_car_empty,
        "cw_side_force_N": F_cw,
        "traction_ratio_full": ratio_full,
        "traction_ratio_empty": ratio_empty,
        "traction_limit": e_mu_alpha,
        "traction_adequate_full": traction_ok_full,
        "traction_adequate_empty": traction_ok_empty,
        "n_ropes_recommended": n_ropes_used,
        "rope_diameter_mm": rope_d,
        "sheave_diameter_mm": sheave_mm,
        "sheave_D_d_ratio": D_d_ratio,
        "overbalance_kg": overbalance,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. hydraulic_lift
# ---------------------------------------------------------------------------

def hydraulic_lift(
    rated_load_kg: float,
    car_mass_kg: float,
    rated_speed_m_s: float,
    piston_diameter_mm: float,
    *,
    roping: int = 1,
    pump_efficiency: float = 0.80,
    motor_efficiency: float = 0.90,
    safety_factor: float = 2.5,
    fluid_density_kg_m3: float = 870.0,
    max_working_pressure_MPa: float = 15.0,
) -> dict:
    """
    Hydraulic (jack) lift jack force, pump flow, and power.

    Parameters
    ----------
    rated_load_kg : float
        Rated payload (kg). Must be > 0.
    car_mass_kg : float
        Empty car mass (kg). Must be > 0.
    rated_speed_m_s : float
        Rated car speed (m/s). Must be > 0.
    piston_diameter_mm : float
        Hydraulic piston/plunger outer diameter (mm). Must be > 0.
    roping : int
        Hydraulic roping ratio: 1 for direct, 2 for indirect (2:1). Default 1.
    pump_efficiency : float
        Hydraulic pump volumetric + mechanical efficiency (0–1). Default 0.80.
    motor_efficiency : float
        Electric motor efficiency (0–1). Default 0.90.
    safety_factor : float
        Pressure safety factor for proof pressure. Default 2.5 (EN 81-2).
    fluid_density_kg_m3 : float
        Hydraulic fluid density (kg/m³). Default 870 (mineral oil).
    max_working_pressure_MPa : float
        Maximum allowable working pressure (MPa). Default 15 MPa.
        Warning if computed pressure exceeds this.

    Returns
    -------
    dict
        ok                   : True
        jack_force_N         : required jack/piston force (N)
        piston_area_m2       : piston cross-sectional area (m²)
        working_pressure_Pa  : working pressure (Pa)
        working_pressure_MPa : working pressure (MPa)
        proof_pressure_MPa   : proof pressure = working × safety_factor (MPa)
        pump_flow_m3_s       : required pump flow rate (m³/s)
        pump_flow_L_min      : required pump flow rate (L/min)
        pump_power_W         : hydraulic pump shaft power (W)
        pump_power_kW        : hydraulic pump shaft power (kW)
        motor_power_W        : electric motor power (W)
        motor_power_kW       : electric motor power (kW)
        warnings             : list of warning strings
    """
    err = _guard_positive("rated_load_kg", rated_load_kg)
    if err:
        return _err(err)
    err = _guard_positive("car_mass_kg", car_mass_kg)
    if err:
        return _err(err)
    err = _guard_positive("rated_speed_m_s", rated_speed_m_s)
    if err:
        return _err(err)
    err = _guard_positive("piston_diameter_mm", piston_diameter_mm)
    if err:
        return _err(err)
    if roping not in (1, 2):
        return _err(f"roping must be 1 or 2, got {roping!r}")
    err = _guard_range("pump_efficiency", pump_efficiency, 0.3, 1.0)
    if err:
        return _err(err)
    err = _guard_range("motor_efficiency", motor_efficiency, 0.3, 1.0)
    if err:
        return _err(err)
    err = _guard_positive("safety_factor", safety_factor)
    if err:
        return _err(err)
    err = _guard_positive("fluid_density_kg_m3", fluid_density_kg_m3)
    if err:
        return _err(err)
    err = _guard_positive("max_working_pressure_MPa", max_working_pressure_MPa)
    if err:
        return _err(err)

    warnings: list[str] = []

    Q   = float(rated_load_kg)
    M_c = float(car_mass_kg)
    v   = float(rated_speed_m_s)
    d_p = float(piston_diameter_mm) / 1000.0  # m
    eta_p = float(pump_efficiency)
    eta_m = float(motor_efficiency)
    SF  = float(safety_factor)
    P_max = float(max_working_pressure_MPa) * 1e6  # Pa

    # Total suspended weight
    W_total = (M_c + Q) * _G  # N

    # For 2:1 roping: jack force = W_total / 2 (the load is shared by two rope runs)
    jack_force = W_total / roping  # N

    # Piston area
    A_piston = math.pi * d_p ** 2 / 4.0  # m²

    # Working pressure
    p_work = jack_force / A_piston  # Pa

    # Proof pressure
    p_proof = p_work * SF  # Pa

    # Pressure warning
    if p_work > P_max:
        warnings.append(
            f"Working pressure {p_work/1e6:.2f} MPa exceeds maximum allowable "
            f"{max_working_pressure_MPa:.1f} MPa. Increase piston diameter."
        )

    # Pump flow rate: Q_pump = A_piston × car_speed (for 1:1);
    # for 2:1 roping car speed = jack speed × 2 → jack speed = v/2
    jack_speed = v / roping  # piston/jack travel speed (m/s)
    Q_pump = A_piston * jack_speed  # m³/s (theoretical; actual = Q_pump / eta_p)

    Q_pump_actual = Q_pump / eta_p  # m³/s

    # Hydraulic power (fluid power at pump outlet)
    P_hydraulic = p_work * Q_pump  # W (ideal)

    # Pump shaft power = hydraulic power / pump_efficiency
    P_pump = P_hydraulic / eta_p  # W

    # Motor power = pump shaft power / motor_efficiency
    P_motor = P_pump / eta_m  # W

    if eta_p < 0.65:
        warnings.append(
            f"Pump efficiency {eta_p:.2f} is low. Typical hydraulic pump "
            f"efficiency is 0.75–0.90."
        )

    return {
        "ok": True,
        "jack_force_N": jack_force,
        "piston_area_m2": A_piston,
        "working_pressure_Pa": p_work,
        "working_pressure_MPa": p_work / 1e6,
        "proof_pressure_MPa": p_proof / 1e6,
        "pump_flow_m3_s": Q_pump_actual,
        "pump_flow_L_min": Q_pump_actual * 1000.0 * 60.0,
        "pump_power_W": P_pump,
        "pump_power_kW": P_pump / 1000.0,
        "motor_power_W": P_motor,
        "motor_power_kW": P_motor / 1000.0,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. motor_power
# ---------------------------------------------------------------------------

def motor_power(
    rated_load_kg: float,
    car_mass_kg: float,
    counterweight_mass_kg: float,
    rated_speed_m_s: float,
    *,
    roping: int = 1,
    drive_efficiency: float = 0.80,
    starts_per_hour: int = 180,
    duty_factor: float = 1.0,
) -> dict:
    """
    Traction lift motor power from balanced-load method.

    Computes the motor power required to drive the traction sheave under
    the worst-case load imbalance (full load ascending or empty car
    descending), accounting for roping ratio and drive train efficiency.

    Parameters
    ----------
    rated_load_kg : float
        Rated payload (kg). Must be > 0.
    car_mass_kg : float
        Empty car mass (kg). Must be > 0.
    counterweight_mass_kg : float
        Counterweight mass (kg). Must be > 0.
    rated_speed_m_s : float
        Rated car speed (m/s). Must be > 0.
    roping : int
        Roping ratio (1 or 2). Default 1.
    drive_efficiency : float
        Mechanical + electrical drive efficiency (0–1). Default 0.80.
    starts_per_hour : int
        Motor starts per hour. Default 180. EN 81-1 / motor IEC rating.
        Warning if > 240.
    duty_factor : float
        Thermal duty-cycle derating factor (0–1). Default 1.0.
        For S3 duty (% on-time), set duty_factor = sqrt(on_time/100).

    Returns
    -------
    dict
        ok                      : True
        net_force_full_load_N   : net unbalanced force (full load ascending) (N)
        net_force_empty_N       : net unbalanced force (empty ascending = CW heavy) (N)
        worst_case_force_N      : max(full, empty) force (N)
        motor_power_W           : rated motor power (W)
        motor_power_kW          : rated motor power (kW)
        derated_motor_power_kW  : motor power after duty_factor derating (kW)
        starts_per_hour         : starts/hour used
        warnings                : list of warning strings
    """
    err = _guard_positive("rated_load_kg", rated_load_kg)
    if err:
        return _err(err)
    err = _guard_positive("car_mass_kg", car_mass_kg)
    if err:
        return _err(err)
    err = _guard_positive("counterweight_mass_kg", counterweight_mass_kg)
    if err:
        return _err(err)
    err = _guard_positive("rated_speed_m_s", rated_speed_m_s)
    if err:
        return _err(err)
    if roping not in (1, 2):
        return _err(f"roping must be 1 or 2, got {roping!r}")
    err = _guard_range("drive_efficiency", drive_efficiency, 0.3, 1.0)
    if err:
        return _err(err)
    err = _guard_range("duty_factor", duty_factor, 0.01, 1.0)
    if err:
        return _err(err)
    err = _guard_range("starts_per_hour", starts_per_hour, 1, 600)
    if err:
        return _err(err)

    warnings: list[str] = []

    Q   = float(rated_load_kg)
    M_c = float(car_mass_kg)
    M_cw = float(counterweight_mass_kg)
    v   = float(rated_speed_m_s)
    eta = float(drive_efficiency)
    sph = int(starts_per_hour)
    df  = float(duty_factor)

    # Net unbalanced forces at sheave
    # Full load ascending: (car + load) − counterweight
    F_full = (M_c + Q - M_cw) * _G / roping  # N (positive = motor must lift)

    # Empty car ascending: car − counterweight (CW heavier → negative means CW assists
    # car descent = motor must brake; but for worst-case motor power use abs value)
    F_empty = (M_c - M_cw) * _G / roping  # N (typically negative)

    # Worst case is whichever requires more motor force
    F_worst = max(abs(F_full), abs(F_empty))

    # Motor shaft power
    # For motoring: P = F × v / η
    # For regenerating: the motor still needs to be sized for P_mech = F × v
    P_motor = F_worst * v / eta  # W

    # Derated power (duty cycle)
    P_derated = P_motor / df  # W

    if sph > 240:
        warnings.append(
            f"starts_per_hour={sph} exceeds typical traction motor rating of 240 "
            f"starts/h. Verify motor S3/S4 duty class and thermal capacity."
        )

    if eta < 0.70:
        warnings.append(
            f"Drive efficiency {eta:.2f} is low. Typical gearless drive 0.85–0.93; "
            f"geared drive 0.75–0.85."
        )

    return {
        "ok": True,
        "net_force_full_load_N": F_full,
        "net_force_empty_N": F_empty,
        "worst_case_force_N": F_worst,
        "motor_power_W": P_motor,
        "motor_power_kW": P_motor / 1000.0,
        "derated_motor_power_kW": P_derated / 1000.0,
        "starts_per_hour": sph,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. kinematics
# ---------------------------------------------------------------------------

def kinematics(
    floor_height_m: float,
    rated_speed_m_s: float,
    *,
    acceleration_m_s2: float = 1.0,
    jerk_m_s3: float = 2.0,
    door_time_s: float = 5.0,
    n_floors: int | None = None,
) -> dict:
    """
    Lift travel kinematics for a single floor-to-floor journey.

    Uses a symmetric S-curve (trapezoidal jerk) profile:
      Phase 1: jerk up    (0 → a_max in t_j = a_max / jerk)
      Phase 2: constant a (a_max → v_max reached)
      Phase 3: jerk down  (a_max → 0)
      Phase 4: constant v
      Phases 5–7 mirror 1–3 for deceleration.

    For short floors where rated speed is not reached, the profile is
    triangular and the maximum achieved speed is less than rated speed.

    Parameters
    ----------
    floor_height_m : float
        Floor-to-floor travel distance (m). Must be > 0.
    rated_speed_m_s : float
        Rated car speed (m/s). Must be > 0.
    acceleration_m_s2 : float
        Maximum acceleration (m/s²). Default 1.0 m/s².
        CIBSE Guide D comfort: 0.8–1.2 m/s².
    jerk_m_s3 : float
        Maximum jerk (m/s³). Default 2.0 m/s³.
        CIBSE Guide D comfort: ≤ 2.0 m/s³.
    door_time_s : float
        Time for door open + dwell + close (s). Default 5.0 s.
    n_floors : int or None
        Total number of served floors. Used only for full-trip estimate if
        provided. Optional.

    Returns
    -------
    dict
        ok                    : True
        t_jerk_s              : time for jerk phase (s)
        t_accel_s             : total acceleration phase time (s)
        v_max_achieved_m_s    : maximum speed actually achieved (m/s) (<= rated)
        d_accel_m             : distance used during acceleration phase (m)
        d_constant_m          : distance at constant speed (m)
        flight_time_s         : travel time excluding door time (s)
        floor_to_floor_time_s : total floor-to-floor time including doors (s)
        warnings              : list of warning strings
    """
    err = _guard_positive("floor_height_m", floor_height_m)
    if err:
        return _err(err)
    err = _guard_positive("rated_speed_m_s", rated_speed_m_s)
    if err:
        return _err(err)
    err = _guard_positive("acceleration_m_s2", acceleration_m_s2)
    if err:
        return _err(err)
    err = _guard_positive("jerk_m_s3", jerk_m_s3)
    if err:
        return _err(err)
    err = _guard_nonneg("door_time_s", door_time_s)
    if err:
        return _err(err)

    warnings: list[str] = []

    H  = float(floor_height_m)
    v  = float(rated_speed_m_s)
    a  = float(acceleration_m_s2)
    j  = float(jerk_m_s3)
    t_door = float(door_time_s)

    # Comfort warnings
    if a > 1.5:
        warnings.append(
            f"Acceleration {a:.2f} m/s² exceeds CIBSE Guide D comfort limit of 1.5 m/s². "
            f"Passengers may experience discomfort."
        )
    if j > 2.0:
        warnings.append(
            f"Jerk {j:.2f} m/s³ exceeds CIBSE Guide D comfort limit of 2.0 m/s³. "
            f"Passengers may experience discomfort."
        )

    # S-curve kinematics
    # t_j: time to ramp from 0 to a_max
    t_j = a / j  # s

    # Distance and speed after one jerk ramp (Phase 1 alone):
    # v after phase 1 = 0.5 × a × t_j  (triangular ramp)
    # Actually: v1 = j × t_j² / 2 = a × t_j / 2
    v_after_jerk = 0.5 * a * t_j  # m/s

    # Full acceleration phase: phase1 (jerk up) + phase2 (constant a) + phase3 (jerk down)
    # Speed at end of phase 2: v = v_after_jerk + a × t_a2  (must reach rated speed)
    # Total speed gained in accel phases 1+2+3 must = v_rated
    # v_rated = j*t_j²/2 + a*t_a2 + j*t_j²/2 = a*t_j + a*t_a2
    # t_a2 = (v_rated - a*t_j) / a  [time at constant acceleration]

    t_a2 = (v - a * t_j) / a  # s (time at constant a in mid-section)

    if t_a2 < 0:
        # Peak speed during accel is less than rated — pure jerk profile
        # Max speed from pure jerk ramp: v = j × (t_j')² / 2 = a² / (2j) × 2 = a²/j...
        # For a triangular jerk profile without plateau:
        # v_peak = j × t_peak² / 4 ... actually re-derive:
        # If we jerk up from 0 → a_peak in t_j' then immediately jerk back
        # v_peak = a_peak² / (2j) where a_peak = j × t_j'
        # Set v_peak = v_rated: t_j' = sqrt(2 × v_rated / j), a_peak = sqrt(2 × v_rated × j)
        # For short floor we might not even reach v_rated
        t_a2 = 0.0
        # Jerk up, jerk down (no constant-a phase)
        t_j_needed = math.sqrt(v / j)  # time for half-accel ramp
        v_peak = j * t_j_needed ** 2  # = v (by construction)
        t_accel = 2.0 * t_j_needed   # full acceleration phase
        d_accel = j * t_j_needed ** 3 / 3.0 * 2  # symmetric
    else:
        # Distance during accel (phase 1 + 2 + 3):
        # d1 = j × t_j³ / 6  (jerk-up quarter)
        # d2 = v_after_jerk × t_a2 + 0.5 × a × t_a2²
        # d3 = (v_after_jerk + a × t_a2) × t_j - 0.5 × a × t_j² + j_down × t_j³/6
        #    = (v - v_after_jerk) × t_j - 0.5 × a × t_j² + j × t_j³/6
        d1 = j * t_j ** 3 / 6.0
        d2 = v_after_jerk * t_a2 + 0.5 * a * t_a2 ** 2
        # Phase 3: speed starts at (v - v_after_jerk), ends at v; jerk down
        d3 = (v - v_after_jerk) * t_j - 0.5 * a * t_j ** 2 + j * t_j ** 3 / 6.0
        d_accel_half = d1 + d2 + d3
        t_accel_half = t_j + t_a2 + t_j
        t_accel = t_accel_half
        d_accel = d_accel_half
        v_peak = v

    # Total distance to accelerate to v and decelerate back to 0 (symmetric):
    d_total_accel_decel = 2.0 * d_accel  # m

    # Check if floor height allows full-speed cruise
    if d_total_accel_decel >= H:
        # Short floor: can't reach rated speed — use triangular approximation
        # The car accelerates to some v_max < v, then immediately decelerates.
        # d_total_accel_decel ≈ v_max² / a  (trapezoidal simplified)
        # v_max = sqrt(H × a)
        v_max = math.sqrt(H * a)
        if v_max > v:
            v_max = v
        # Recalculate times with v_max
        t_j_short = a / j
        t_a2_short = max(0.0, (v_max - a * t_j_short) / a)
        t_accel_total = 2.0 * t_j_short + t_a2_short
        # Symmetric: total travel time = 2 × accel phase
        t_travel = 2.0 * t_accel_total
        d_const = 0.0
        warnings.append(
            f"Floor height {H:.2f} m is too short to reach rated speed "
            f"{v:.2f} m/s. Maximum achieved speed ≈ {v_max:.2f} m/s."
        )
    else:
        v_max = v_peak
        d_const = H - d_total_accel_decel  # m
        # Flight time = 2 × t_accel + d_const / v
        t_const = d_const / v
        t_travel = 2.0 * t_accel + t_const

    t_floor_to_floor = t_travel + t_door

    return {
        "ok": True,
        "t_jerk_s": t_j,
        "t_accel_s": t_accel,
        "v_max_achieved_m_s": v_max,
        "d_accel_m": d_accel,
        "d_constant_m": d_const if d_total_accel_decel < H else 0.0,
        "flight_time_s": t_travel,
        "floor_to_floor_time_s": t_floor_to_floor,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. traffic_analysis
# ---------------------------------------------------------------------------

def traffic_analysis(
    n_floors: int,
    floor_height_m: float,
    n_persons: int,
    rated_load_persons: int,
    rated_speed_m_s: float,
    *,
    population_per_floor: int | None = None,
    acceleration_m_s2: float = 1.0,
    jerk_m_s3: float = 2.0,
    door_time_s: float = 5.0,
    n_cars: int = 1,
    target_interval_s: float | None = None,
    target_handling_pct: float | None = None,
) -> dict:
    """
    CIBSE Guide D round-trip time (RTT) lift traffic analysis.

    Uses the Barney & Dos Santos (2003) probable-stops and highest-reversal
    formulae for a single-entrance building with uniform population.

    Parameters
    ----------
    n_floors : int
        Number of served floors above entry level. Must be >= 2.
    floor_height_m : float
        Average floor-to-floor height (m). Must be > 0.
    n_persons : int
        Estimated total building population (above entry level). Must be > 0.
    rated_load_persons : int
        Car rated capacity in persons. Must be >= 1.
        CIBSE Guide D: rated capacity = rated_load_kg / 75 kg.
    rated_speed_m_s : float
        Rated car speed (m/s). Must be > 0.
    population_per_floor : int or None
        Override uniform population per floor. If None, uses n_persons / n_floors.
    acceleration_m_s2 : float
        Peak acceleration (m/s²). Default 1.0 m/s².
    jerk_m_s3 : float
        Maximum jerk (m/s³). Default 2.0 m/s³.
    door_time_s : float
        Door open + dwell + close time per stop (s). Default 5.0 s.
    n_cars : int
        Number of cars in the group. Default 1.
    target_interval_s : float or None
        Desired average interval (s). Warning if computed > target.
        CIBSE Guide D good service: ≤ 30 s.
    target_handling_pct : float or None
        Required 5-minute handling capacity (%). Warning if computed < target.

    Returns
    -------
    dict
        ok                      : True
        probable_stops_S        : probable number of stops (Barney formula)
        highest_reversal_H      : highest reversal floor
        rtt_s                   : round-trip time per car (s)
        interval_s              : average interval between car departures (s)
        handling_capacity_pct   : 5-minute handling capacity (% of population)
        n_cars_for_target       : cars needed for target_interval_s (if given)
        persons_per_trip        : persons per trip = rated_load_persons × 0.8
        warnings                : list of warning strings
    """
    if not isinstance(n_floors, int) or n_floors < 2:
        return _err(f"n_floors must be an integer >= 2, got {n_floors!r}")
    err = _guard_positive("floor_height_m", floor_height_m)
    if err:
        return _err(err)
    if not isinstance(n_persons, int) or n_persons < 1:
        return _err(f"n_persons must be an integer >= 1, got {n_persons!r}")
    if not isinstance(rated_load_persons, int) or rated_load_persons < 1:
        return _err(f"rated_load_persons must be an integer >= 1, got {rated_load_persons!r}")
    err = _guard_positive("rated_speed_m_s", rated_speed_m_s)
    if err:
        return _err(err)
    if not isinstance(n_cars, int) or n_cars < 1:
        return _err(f"n_cars must be an integer >= 1, got {n_cars!r}")

    warnings: list[str] = []

    N  = int(n_floors)
    H_fh = float(floor_height_m)
    P  = int(n_persons)
    CC = int(rated_load_persons)  # car capacity (persons)
    v  = float(rated_speed_m_s)
    a  = float(acceleration_m_s2)
    j  = float(jerk_m_s3)
    t_d = float(door_time_s)
    nc = int(n_cars)

    # Persons per trip (CIBSE Guide D: use 80% of rated capacity)
    P_trip = CC * 0.80

    # --- Probable stops (S) — Barney formula ---
    # S = N × (1 - (1 - 1/N)^P_trip)
    # where N = number of floors above entry
    S = N * (1.0 - (1.0 - 1.0 / N) ** P_trip)

    # --- Highest reversal floor (H_rev) ---
    # H = N × (1 - (N/(N+1))^P_trip)  ... Barney 2003 simplified
    # More accurate: H = N - sum_{i=1}^{N} (1 - i/N)^P_trip
    # Use the Barney/Dos Santos approximation (CIBSE Guide D Appendix):
    # H_rev = N × [1 - (N-1)^P_trip / N^P_trip] ... or the standard:
    # H_rev = N - (N-1)*(1 - 1/(N-1))^P_trip  ... several variants exist
    # CIBSE Guide D Table 3.9 standard: H = N × (1 - ((N-1)/N)^P_trip)
    # + correction term  (= N × (1-(1-1/N)^P_trip) actually — same as S but for H)
    # Use the classic Barney 1 formula (Guide D §3):
    # H_rev = N - N × ((N-1)/N)^P_trip
    H_rev = N * (1.0 - ((N - 1.0) / N) ** P_trip) if N > 1 else 1.0

    # --- Round-trip time (RTT) ---
    # RTT = 2 × H_rev × t_floor  +  S × t_door  +  2 × t_floor × (v/a ...)
    # CIBSE Guide D simplified formula (Guide D §3.4):
    # RTT = (2 × H_rev × H_fh / v) + (S × t_d) + (2 × t_tv)
    # where t_tv = time lost to velocity changes per stop ≈ v/a
    # More precise S-curve correction: t_tv ≈ v/a + a/(2j) (Barney 2003)

    # Flight time from ground to H_rev floor
    travel_distance = H_rev * H_fh  # m
    # Use kinematics for the full H_rev travel
    kin = kinematics(
        travel_distance if travel_distance > 0.01 else 0.01,
        v,
        acceleration_m_s2=a,
        jerk_m_s3=j,
        door_time_s=0.0,  # doors handled separately
    )
    t_up = kin["flight_time_s"]   # one-way travel time

    # Return trip: same distance
    t_down = t_up

    # Transition time per stop (lost time due to speed changes at intermediate stops)
    # CIBSE Guide D uses: t_tv ≈ v/a (simplified) or v/a + a/j (S-curve)
    t_tv = v / a + a / j  # s per stop

    # RTT = up_travel + down_travel + S × door_time + (S-1) × t_tv
    # (S-1 intermediate transitions; entry and exit are within the travel time)
    # CIBSE Guide D §3.4 (Barney 2003 Eq. 3.9):
    # RTT = 2 × tv + S × (t_d + t_tv)
    # where tv = one-way travel time from entry to highest reversal
    # Then add return + loading time
    # Simplified widely-used form:
    rtt = 2.0 * t_up + S * (t_d + t_tv)  # s

    # Average interval
    interval = rtt / nc  # s

    # 5-minute handling capacity
    # persons per 5 min = (5 × 60 / rtt) × P_trip × nc
    persons_5min = (300.0 / rtt) * P_trip * nc
    handling_pct = (persons_5min / P) * 100.0  # % of total population

    # Cars needed for target interval
    n_cars_target: int | None = None
    if target_interval_s is not None:
        err_t = _guard_positive("target_interval_s", target_interval_s)
        if err_t:
            return _err(err_t)
        t_tgt = float(target_interval_s)
        n_cars_target = max(1, math.ceil(rtt / t_tgt))
        if interval > t_tgt:
            warnings.append(
                f"Average interval {interval:.1f} s exceeds target {t_tgt:.1f} s. "
                f"Need {n_cars_target} cars to achieve target interval."
            )

    # Standard CIBSE interval thresholds
    if interval > 60.0:
        warnings.append(
            f"Interval {interval:.1f} s > 60 s — very poor service level "
            f"(CIBSE Guide D: good service ≤ 30 s)."
        )
    elif interval > 30.0:
        warnings.append(
            f"Interval {interval:.1f} s > 30 s — poor service level "
            f"(CIBSE Guide D: good service ≤ 30 s)."
        )

    if target_handling_pct is not None:
        err_h = _guard_positive("target_handling_pct", target_handling_pct)
        if err_h:
            return _err(err_h)
        if handling_pct < float(target_handling_pct):
            warnings.append(
                f"Handling capacity {handling_pct:.1f}% is below target "
                f"{target_handling_pct:.1f}%. Add more cars or increase speed."
            )

    result = {
        "ok": True,
        "probable_stops_S": S,
        "highest_reversal_H": H_rev,
        "rtt_s": rtt,
        "interval_s": interval,
        "handling_capacity_pct": handling_pct,
        "persons_per_trip": P_trip,
        "warnings": warnings,
    }
    if n_cars_target is not None:
        result["n_cars_for_target"] = n_cars_target

    return result


# ---------------------------------------------------------------------------
# 6. buffer_stroke
# ---------------------------------------------------------------------------

def buffer_stroke(
    rated_speed_m_s: float,
    *,
    overspeed_governor_factor: float = 1.10,
    buffer_type: str = "oil",
    gravity_deceleration_m_s2: float | None = None,
) -> dict:
    """
    EN 81-1 buffer stroke and overspeed governor trip speed.

    Parameters
    ----------
    rated_speed_m_s : float
        Rated car speed (m/s). Must be > 0.
    overspeed_governor_factor : float
        Overspeed governor trip speed as a fraction of rated speed.
        EN 81-1 §10.4.1: trip speed = (115% to 140% of rated speed) → default 1.10.
    buffer_type : str
        'oil' (hydraulic buffer) or 'polyurethane' / 'spring'. Default 'oil'.
        Oil buffers: stroke from EN 81-1 §10.4.3.
        Polyurethane/spring: EN 81-1 §10.4.2.
    gravity_deceleration_m_s2 : float or None
        Safety gear deceleration (m/s²). Default: 9.81/2 (0.5 g) for oil,
        or rated_speed² / 0.1 for spring.

    Returns
    -------
    dict
        ok                          : True
        governor_trip_speed_m_s     : overspeed governor trip speed (m/s)
        buffer_impact_speed_m_s     : speed at buffer impact (m/s)
        buffer_stroke_min_mm        : minimum buffer stroke (mm) per EN 81-1
        safety_gear_stop_distance_m : stopping distance under gravity deceleration (m)
        warnings                    : list of warning strings
    """
    err = _guard_positive("rated_speed_m_s", rated_speed_m_s)
    if err:
        return _err(err)
    err = _guard_range("overspeed_governor_factor", overspeed_governor_factor, 1.0, 1.50)
    if err:
        return _err(err)

    buf_type = str(buffer_type).strip().lower()
    if buf_type not in ("oil", "polyurethane", "spring"):
        return _err(
            f"buffer_type must be 'oil', 'polyurethane', or 'spring', got {buf_type!r}"
        )

    warnings: list[str] = []

    v  = float(rated_speed_m_s)
    k  = float(overspeed_governor_factor)

    # EN 81-1 §10.4.1: governor trip speed range
    v_trip = v * k  # m/s

    if k < 1.115:
        warnings.append(
            f"EN 81-1 §10.4.1 requires overspeed governor trip speed "
            f">= 115% of rated speed. Factor {k:.3f} ({k*100:.1f}%) is below minimum."
        )
    if k > 1.40:
        warnings.append(
            f"EN 81-1 §10.4.1: governor trip speed factor {k:.3f} exceeds 1.40. "
            f"Verify compliance."
        )

    # Buffer impact speed: car/CW reaches the buffer at v_trip (worst case)
    v_impact = v_trip  # m/s

    # EN 81-1 §10.4.3 (oil buffer): minimum stroke
    # s_min = v²_impact / (2 × g_d)  where g_d >= 0.5 g (min decel)
    # EN 81-1 §10.4.3: s_min = v²/(2×g) for g_d = g (full gravity retardation)
    # For oil buffers: s_min ≥ v²/g  per EN 81-1 simplified
    # (The standard formula: s_min = v_impact² / (2 × a_mean) with a_mean >= g/2)
    if gravity_deceleration_m_s2 is None:
        if buf_type == "oil":
            g_d = _G * 1.0   # EN 81-1: use 1g for oil buffer stroke calc
        else:
            g_d = _G * 0.5   # spring/polyurethane: 0.5g minimum
    else:
        err_gd = _guard_positive("gravity_deceleration_m_s2", gravity_deceleration_m_s2)
        if err_gd:
            return _err(err_gd)
        g_d = float(gravity_deceleration_m_s2)

    # Minimum buffer stroke: s = v_impact² / (2 × g_d)
    s_min = v_impact ** 2 / (2.0 * g_d)  # m
    s_min_mm = s_min * 1000.0

    # EN 81-1 §10.4.3: absolute minimum stroke
    s_abs_min_mm = 420.0 if buf_type == "oil" else 150.0
    if s_min_mm < s_abs_min_mm:
        s_min_mm = s_abs_min_mm  # EN 81-1 absolute minimum
        s_min = s_min_mm / 1000.0

    # Safety gear stopping distance (for progressive safety gear)
    # Using: v² = 2 × a × d → d = v_impact² / (2 × a_sg)
    # EN 81-1 §9.8: safety gear deceleration 0.2–1.0 g
    a_sg = _G * 0.5  # 0.5 g for progressive safety gear
    d_stop = v_impact ** 2 / (2.0 * a_sg)  # m

    return {
        "ok": True,
        "governor_trip_speed_m_s": v_trip,
        "buffer_impact_speed_m_s": v_impact,
        "buffer_stroke_min_mm": s_min_mm,
        "safety_gear_stop_distance_m": d_stop,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. escalator
# ---------------------------------------------------------------------------

# EN 115-1:2017 maximum inclination angles
_ESCALATOR_MAX_INCLINE: dict[str, float] = {
    "escalator_low":    30.0,   # for rise ≤ 6 m (EN 115-1 §5.4.1)
    "escalator_high":   35.0,   # for rise > 6 m (EN 115-1 §5.4.1)
    "moving_walk":      12.0,   # moving walk (EN 115-1 §5.4.2)
}

# EN 115-1 step width to theoretical capacity (persons/hour) at v=0.5 m/s
# Base capacities per EN 115-1 §5.3.2 and CIBSE Guide D Table 7.1
_ESCALATOR_BASE_CAPACITY: dict[float, int] = {
    0.60: 4500,   # 600 mm step width
    0.80: 6750,   # 800 mm step width (standard)
    1.00: 9000,   # 1000 mm step width (wide)
}


def escalator(
    step_width_m: float,
    belt_speed_m_s: float,
    rise_m: float,
    *,
    inclination_deg: float = 30.0,
    escalator_type: str = "escalator",
    utilisation_factor: float = 0.75,
    step_depth_m: float = 0.40,
    drive_efficiency: float = 0.85,
    handrail_mass_kg_m: float = 2.5,
    balustrade_friction_factor: float = 0.015,
    n_persons_per_step: float | None = None,
    target_capacity_pph: float | None = None,
) -> dict:
    """
    Escalator / moving walk capacity and drive power.

    Parameters
    ----------
    step_width_m : float
        Clear step width (m). Standard values: 0.60, 0.80, 1.00 m.
    belt_speed_m_s : float
        Belt/step chain speed (m/s). EN 115 max: 0.75 m/s escalator,
        0.9 m/s moving walk. Must be > 0.
    rise_m : float
        Total vertical rise (m). Must be > 0.
    inclination_deg : float
        Incline angle from horizontal (°). Default 30°.
        EN 115-1 limits: ≤ 30° for low rise, ≤ 35° for high rise, ≤ 12° for walks.
    escalator_type : str
        'escalator' or 'moving_walk'. Default 'escalator'.
    utilisation_factor : float
        Fraction of theoretical capacity achieved in practice. Default 0.75.
        Range 0.1–1.0.
    step_depth_m : float
        Step depth (horizontal, m). Default 0.40 m.
    drive_efficiency : float
        Drive efficiency. Default 0.85.
    handrail_mass_kg_m : float
        Handrail chain + step mass per metre of escalator length (kg/m). Default 2.5.
    balustrade_friction_factor : float
        Friction factor for horizontal components. Default 0.015.
    n_persons_per_step : float or None
        Override: persons per step (used for capacity). If None, computed from
        step width (0.60 m → 1, 0.80 m → 1.5 [dual occupancy], 1.0 m → 2).
    target_capacity_pph : float or None
        Required capacity (persons/hour). Warns if actual < target.

    Returns
    -------
    dict
        ok                      : True
        incline_rad             : inclination in radians
        escalator_length_m      : inclined length along truss (m)
        steps_per_m             : number of steps per metre of escalator length
        theoretical_capacity_pph: theoretical capacity (persons/hour)
        actual_capacity_pph     : actual capacity with utilisation (persons/hour)
        lift_power_W            : power to lift passengers (W)
        lift_power_kW           : power to lift passengers (kW)
        friction_power_W        : friction/horizontal component power (W)
        friction_power_kW       : friction power (kW)
        total_power_W           : total escalator drive power (W)
        total_power_kW          : total escalator drive power (kW)
        motor_power_kW          : motor power including efficiency (kW)
        warnings                : list of warning strings
    """
    err = _guard_positive("step_width_m", step_width_m)
    if err:
        return _err(err)
    err = _guard_positive("belt_speed_m_s", belt_speed_m_s)
    if err:
        return _err(err)
    err = _guard_positive("rise_m", rise_m)
    if err:
        return _err(err)
    err = _guard_range("inclination_deg", inclination_deg, 0.0, 45.0)
    if err:
        return _err(err)
    err = _guard_range("utilisation_factor", utilisation_factor, 0.1, 1.0)
    if err:
        return _err(err)
    err = _guard_positive("step_depth_m", step_depth_m)
    if err:
        return _err(err)
    err = _guard_range("drive_efficiency", drive_efficiency, 0.5, 1.0)
    if err:
        return _err(err)
    err = _guard_positive("handrail_mass_kg_m", handrail_mass_kg_m)
    if err:
        return _err(err)

    esc_type = str(escalator_type).strip().lower()
    if esc_type not in ("escalator", "moving_walk"):
        return _err(
            f"escalator_type must be 'escalator' or 'moving_walk', got {esc_type!r}"
        )

    warnings: list[str] = []

    w   = float(step_width_m)
    v   = float(belt_speed_m_s)
    H   = float(rise_m)
    phi_deg = float(inclination_deg)
    phi = math.radians(phi_deg)
    uf  = float(utilisation_factor)
    sd  = float(step_depth_m)
    eta = float(drive_efficiency)
    Wh  = float(handrail_mass_kg_m)
    kf  = float(balustrade_friction_factor)

    # --- Inclination check ---
    if esc_type == "escalator":
        # EN 115-1: ≤ 30° for rise ≤ 6 m, ≤ 35° for rise > 6 m
        max_angle = 30.0 if H <= 6.0 else 35.0
    else:
        max_angle = 12.0

    if phi_deg > max_angle:
        warnings.append(
            f"Inclination {phi_deg:.1f}° exceeds EN 115-1 limit of {max_angle:.0f}° "
            f"for {esc_type} with rise {H:.1f} m."
        )

    # --- Speed check ---
    max_speed = 0.75 if esc_type == "escalator" else 0.90  # m/s per EN 115-1
    if v > max_speed:
        warnings.append(
            f"Speed {v:.2f} m/s exceeds EN 115-1 maximum {max_speed:.2f} m/s "
            f"for {esc_type}."
        )

    # --- Escalator geometry ---
    if phi > 0.001:
        L_esc = H / math.sin(phi)  # inclined length (m)
    else:
        # Moving walk: nearly horizontal; use horizontal length = H/tan(phi)
        # If inclination is negligible, use rise as a proxy (degenerate case)
        L_esc = H / math.tan(phi) if phi > 1e-6 else H * 10.0

    # --- Capacity ---
    # Persons per step: depends on width
    if n_persons_per_step is not None:
        pps = float(n_persons_per_step)
    else:
        if w <= 0.65:
            pps = 1.0
        elif w <= 0.90:
            pps = 1.5   # people stand side by side on 800 mm step
        else:
            pps = 2.0   # 1000 mm step

    # Steps per metre of escalator length (step pitch = step_depth / cos(phi))
    step_pitch_m = sd / math.cos(phi) if phi < math.pi / 2 - 0.01 else sd
    steps_per_m = 1.0 / step_pitch_m if step_pitch_m > 0 else 0.0

    # Theoretical capacity: Q_th = pps × (v / step_pitch_m) × 3600
    Q_theory = pps * (v / step_pitch_m) * 3600.0  # persons/hour

    # Actual capacity
    Q_actual = Q_theory * uf

    if target_capacity_pph is not None:
        err_cap = _guard_positive("target_capacity_pph", target_capacity_pph)
        if err_cap:
            return _err(err_cap)
        if Q_actual < float(target_capacity_pph):
            warnings.append(
                f"Actual capacity {Q_actual:.0f} persons/h < "
                f"target {target_capacity_pph:.0f} persons/h. "
                f"Increase step width or speed."
            )

    # --- Power ---
    # Passenger mass flow: mass_flow = Q_actual × 75 kg/person / 3600 s/h
    persons_per_second = Q_actual / 3600.0
    mass_flow_kg_s = persons_per_second * 75.0  # kg/s (75 kg per person EN 81)

    # Lift power: P_lift = mass_flow × g × vertical_speed
    vertical_speed = v * math.sin(phi)  # m/s (vertical component)
    P_lift = mass_flow_kg_s * _G * vertical_speed  # W

    # Handrail / chain / step weight friction power:
    # P_friction = handrail_mass × g × total_chain_length × friction_factor × v
    # (Both the ascending and return sides carry the chain weight)
    # Simplified: P_friction ≈ Wh × g × L_esc × kf × v (per side; both sides = 2×)
    P_friction = 2.0 * Wh * _G * L_esc * kf * v  # W (both directions)

    P_total = P_lift + P_friction  # W
    P_motor = P_total / eta  # W

    return {
        "ok": True,
        "incline_rad": phi,
        "escalator_length_m": L_esc,
        "steps_per_m": steps_per_m,
        "theoretical_capacity_pph": Q_theory,
        "actual_capacity_pph": Q_actual,
        "lift_power_W": P_lift,
        "lift_power_kW": P_lift / 1000.0,
        "friction_power_W": P_friction,
        "friction_power_kW": P_friction / 1000.0,
        "total_power_W": P_total,
        "total_power_kW": P_total / 1000.0,
        "motor_power_kW": P_motor / 1000.0,
        "warnings": warnings,
    }
