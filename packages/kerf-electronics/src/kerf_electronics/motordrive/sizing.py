"""
Electric motor & inverter-drive sizing — pure Python (math only).

Distinct from:
  kerf_electronics.battery   — battery pack sizing
  kerf_electronics.pdn       — power distribution network
  kerf_electronics.leddriver — LED driver design
  kerf_electronics.afilter   — analog filter design
  kerf_electronics.rfmatch   — RF impedance matching

Capabilities
------------
load_torque_power
    Mechanical load torque and shaft power from angular speed, with
    friction, viscous damping, and inertial acceleration terms.

reflected_inertia
    Load inertia reflected to the motor shaft through a gearbox
    (ratio N:1 → J_reflected = J_load / N²).

inertia_match_ratio
    Optimal gear ratio for inertia matching and load/motor inertia
    mismatch flag (mismatch > threshold).

rms_torque_trapezoidal
    RMS torque over a trapezoidal velocity profile (accel/cruise/decel/dwell)
    for continuous-rating motor selection.

motor_constants
    Derive Kt (torque constant), Ke (back-EMF constant), and winding I²R
    loss from motor datasheet parameters.

dc_operating_point
    DC brush motor operating point: voltage, current, speed, back-EMF,
    efficiency at a given torque and speed.

bldc_pmsm_operating_point
    BLDC/PMSM operating point: d-q axis currents, back-EMF, required
    terminal voltage, copper loss at given speed + torque.

induction_motor_slip_torque
    Basic induction motor slip and torque using the equivalent-circuit
    approximate model (Thevenin reduced circuit).

inverter_sizing
    Three-phase inverter sizing: required DC-link voltage, peak phase
    current, estimated switching + conduction loss, required device ratings.

regen_energy
    Energy recovered during regenerative deceleration from a given inertia
    and speed change, accounting for drivetrain efficiency.

brake_resistor_sizing
    Brake resistor value and power rating from regen energy, DC-link
    voltage, and maximum allowable discharge time.

thermal_duty_check
    Motor thermal duty-cycle check: steady-state winding temperature from
    ambient + losses + thermal resistance, with over-temp warning.

All functions return plain dicts {ok: bool, ...}.
Out-of-range / over-temp / voltage-insufficient / inertia-mismatch cases
are flagged via warnings.warn; dicts still carry ok=True with a "warnings"
list.  Functions never raise.

References
----------
  Krishnan, "Electric Motor Drives" (Prentice Hall, 2001)
  Mohan, Undeland & Robbins, "Power Electronics" (Wiley, 2002)
  Boldea & Nasar, "Electric Drive Systems and Operation" (CRC, 2006)
  Chapman, "Electric Machinery Fundamentals" (5th ed., McGraw-Hill, 2011)
  IEC 60034-1 (motor ratings and continuous duty cycle S1)
  NEMA MG1 (motor standard parameters and duty ratings)

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import List, Optional

# ── Warning thresholds ────────────────────────────────────────────────────────
_OVER_TEMP_MAX_C = 130.0          # typical Class F winding insulation limit
_INERTIA_MISMATCH_MAX = 10.0     # J_load/J_motor mismatch ratio advisory limit
_VOLTAGE_HEADROOM_FRAC = 0.05    # 5 % headroom check on DC-link vs back-EMF
_MAX_SLIP = 0.20                  # induction motor: slip > 20 % → warn


# ── Input validation helpers ──────────────────────────────────────────────────

def _chk_pos(value, name: str) -> Optional[str]:
    """Return error string if value is not a positive finite number."""
    if not isinstance(value, (int, float)) or math.isnan(value) or value <= 0:
        return f"{name} must be a positive finite number, got {value!r}"
    return None


def _chk_nonneg(value, name: str) -> Optional[str]:
    """Return error string if value is not a non-negative finite number."""
    if not isinstance(value, (int, float)) or math.isnan(value) or value < 0:
        return f"{name} must be >= 0, got {value!r}"
    return None


def _chk_frac(value, name: str) -> Optional[str]:
    """Return error string if value is not in (0, 1]."""
    if not isinstance(value, (int, float)) or math.isnan(value) or value <= 0 or value > 1:
        return f"{name} must be in (0, 1], got {value!r}"
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. load_torque_power
# ═══════════════════════════════════════════════════════════════════════════════

def load_torque_power(
    speed_rpm: float,
    torque_load_nm: float,
    inertia_kgm2: float = 0.0,
    accel_rad_s2: float = 0.0,
    friction_nm: float = 0.0,
    viscous_nm_per_rad_s: float = 0.0,
) -> dict:
    """
    Compute total shaft torque and mechanical power required from the motor.

    Total torque:
        T_total = T_load + J × α + T_friction + B × ω

    Mechanical power:
        P_mech = T_total × ω  [W]

    Parameters
    ----------
    speed_rpm            : float — shaft speed [RPM]
    torque_load_nm       : float — load (useful output) torque [N·m]
    inertia_kgm2         : float — total reflected inertia [kg·m²] (default 0)
    accel_rad_s2         : float — angular acceleration [rad/s²] (default 0)
    friction_nm          : float — constant friction torque [N·m] (default 0)
    viscous_nm_per_rad_s : float — viscous damping coefficient [N·m·s/rad] (default 0)

    Returns
    -------
    dict: ok, omega_rad_s, t_total_nm, t_inertial_nm, t_friction_nm,
          t_viscous_nm, p_mech_w, warnings
    """
    sol_warnings: List[str] = []

    err = _chk_pos(speed_rpm, "speed_rpm")
    if err:
        return {"ok": False, "reason": err}

    err = _chk_nonneg(torque_load_nm, "torque_load_nm")
    if err:
        return {"ok": False, "reason": err}

    for name, val in [
        ("inertia_kgm2", inertia_kgm2),
        ("accel_rad_s2", accel_rad_s2),
        ("friction_nm", friction_nm),
        ("viscous_nm_per_rad_s", viscous_nm_per_rad_s),
    ]:
        err = _chk_nonneg(val, name)
        if err:
            return {"ok": False, "reason": err}

    omega = speed_rpm * (2.0 * math.pi / 60.0)   # [rad/s]
    t_inertial = inertia_kgm2 * accel_rad_s2
    t_friction = friction_nm
    t_viscous = viscous_nm_per_rad_s * omega
    t_total = torque_load_nm + t_inertial + t_friction + t_viscous
    p_mech = t_total * omega

    return {
        "ok": True,
        "omega_rad_s": round(omega, 6),
        "t_total_nm": round(t_total, 6),
        "t_inertial_nm": round(t_inertial, 6),
        "t_friction_nm": round(t_friction, 6),
        "t_viscous_nm": round(t_viscous, 6),
        "p_mech_w": round(p_mech, 4),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. reflected_inertia
# ═══════════════════════════════════════════════════════════════════════════════

def reflected_inertia(
    j_load_kgm2: float,
    gear_ratio: float,
    gearbox_efficiency: float = 1.0,
) -> dict:
    """
    Reflect load inertia to the motor shaft through a gearbox.

    J_reflected = J_load / (N² × η_gb)

    where N = gear_ratio (motor speed / load speed) and η_gb is gearbox
    mechanical efficiency (accounts for reflected inertia increase due to
    losses — conservative: set η_gb = 1 for an ideal gearbox).

    Parameters
    ----------
    j_load_kgm2        : float — load-side inertia [kg·m²]
    gear_ratio         : float — N = ω_motor / ω_load (> 1 = speed reduction)
    gearbox_efficiency : float — gearbox mechanical efficiency (0 < η ≤ 1, default 1.0)

    Returns
    -------
    dict: ok, j_reflected_kgm2, gear_ratio, warnings
    """
    sol_warnings: List[str] = []

    err = _chk_pos(j_load_kgm2, "j_load_kgm2")
    if err:
        return {"ok": False, "reason": err}

    err = _chk_pos(gear_ratio, "gear_ratio")
    if err:
        return {"ok": False, "reason": err}

    err = _chk_frac(gearbox_efficiency, "gearbox_efficiency")
    if err:
        return {"ok": False, "reason": err}

    j_reflected = j_load_kgm2 / (gear_ratio ** 2 * gearbox_efficiency)

    return {
        "ok": True,
        "j_reflected_kgm2": round(j_reflected, 12),
        "gear_ratio": gear_ratio,
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. inertia_match_ratio
# ═══════════════════════════════════════════════════════════════════════════════

def inertia_match_ratio(
    j_motor_kgm2: float,
    j_load_kgm2: float,
    gear_ratio: float = 1.0,
    mismatch_threshold: float = _INERTIA_MISMATCH_MAX,
) -> dict:
    """
    Compute load-to-motor inertia mismatch ratio and optimal gear ratio
    for inertia matching.

    Optimal gear ratio for inertia matching:
        N_opt = sqrt(J_load / J_motor)

    Effective mismatch at given gear ratio:
        mismatch = J_load / (gear_ratio² × J_motor)

    A mismatch > mismatch_threshold is flagged in warnings.

    Parameters
    ----------
    j_motor_kgm2       : float — motor rotor inertia [kg·m²]
    j_load_kgm2        : float — load inertia (at load shaft) [kg·m²]
    gear_ratio         : float — current gear ratio N = ω_motor / ω_load (default 1)
    mismatch_threshold : float — advisory mismatch ratio limit (default 10)

    Returns
    -------
    dict: ok, mismatch_ratio, n_opt, inertia_matched, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [("j_motor_kgm2", j_motor_kgm2), ("j_load_kgm2", j_load_kgm2)]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    err = _chk_pos(gear_ratio, "gear_ratio")
    if err:
        return {"ok": False, "reason": err}

    err = _chk_pos(mismatch_threshold, "mismatch_threshold")
    if err:
        return {"ok": False, "reason": err}

    n_opt = math.sqrt(j_load_kgm2 / j_motor_kgm2)
    # Effective mismatch = J_reflected / J_motor = J_load / (N^2 * J_motor)
    mismatch = j_load_kgm2 / (gear_ratio ** 2 * j_motor_kgm2)
    inertia_matched = mismatch <= mismatch_threshold

    if not inertia_matched:
        msg = (
            f"inertia_mismatch: J_load/J_motor (reflected) = {mismatch:.2f} > "
            f"threshold {mismatch_threshold:.1f}; consider increasing gear ratio toward "
            f"N_opt = {n_opt:.2f} for better dynamic response."
        )
        sol_warnings.append(msg)
        warnings.warn(f"inertia_match_ratio: {msg}", stacklevel=2)

    return {
        "ok": True,
        "mismatch_ratio": round(mismatch, 6),
        "n_opt": round(n_opt, 6),
        "inertia_matched": inertia_matched,
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. rms_torque_trapezoidal
# ═══════════════════════════════════════════════════════════════════════════════

def rms_torque_trapezoidal(
    t_accel_nm: float,
    t_cruise_nm: float,
    t_decel_nm: float,
    t_dwell_nm: float,
    dt_accel_s: float,
    dt_cruise_s: float,
    dt_decel_s: float,
    dt_dwell_s: float,
) -> dict:
    """
    Compute RMS torque over a trapezoidal velocity move profile for
    continuous-rating motor selection.

    A trapezoidal move profile has four phases:
      1. Acceleration  — constant torque T_accel over time dt_accel
      2. Cruise        — constant torque T_cruise over time dt_cruise
      3. Deceleration  — constant torque T_decel over time dt_decel
      4. Dwell         — constant torque T_dwell over time dt_dwell
         (e.g. holding torque or zero, depending on the axis brake/load)

    RMS torque:
        T_rms = sqrt( (T_a² × dt_a + T_c² × dt_c + T_d² × dt_d + T_dw² × dt_dw)
                       / (dt_a + dt_c + dt_d + dt_dw) )

    The motor continuous torque rating must exceed T_rms.

    Parameters
    ----------
    t_accel_nm   : float — peak torque during acceleration [N·m]
    t_cruise_nm  : float — torque during cruise (constant speed) [N·m]
    t_decel_nm   : float — torque during deceleration [N·m] (magnitude; sign handled internally)
    t_dwell_nm   : float — torque during dwell (holding or 0) [N·m]
    dt_accel_s   : float — acceleration phase duration [s]
    dt_cruise_s  : float — cruise phase duration [s]
    dt_decel_s   : float — deceleration phase duration [s]
    dt_dwell_s   : float — dwell phase duration [s]

    Returns
    -------
    dict: ok, t_rms_nm, t_peak_nm, cycle_time_s, duty_cycle_active, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("t_accel_nm", t_accel_nm), ("t_cruise_nm", t_cruise_nm),
        ("t_decel_nm", t_decel_nm),
    ]:
        err = _chk_nonneg(val, name)
        if err:
            return {"ok": False, "reason": err}

    err = _chk_nonneg(t_dwell_nm, "t_dwell_nm")
    if err:
        return {"ok": False, "reason": err}

    for name, val in [
        ("dt_accel_s", dt_accel_s), ("dt_cruise_s", dt_cruise_s),
        ("dt_decel_s", dt_decel_s), ("dt_dwell_s", dt_dwell_s),
    ]:
        err = _chk_nonneg(val, name)
        if err:
            return {"ok": False, "reason": err}

    cycle_time = dt_accel_s + dt_cruise_s + dt_decel_s + dt_dwell_s
    if cycle_time <= 0.0:
        return {"ok": False, "reason": "total cycle time (sum of all dt_*) must be > 0"}

    t_rms_sq = (
        t_accel_nm ** 2 * dt_accel_s
        + t_cruise_nm ** 2 * dt_cruise_s
        + t_decel_nm ** 2 * dt_decel_s
        + t_dwell_nm ** 2 * dt_dwell_s
    ) / cycle_time

    t_rms = math.sqrt(max(0.0, t_rms_sq))
    t_peak = max(t_accel_nm, t_cruise_nm, t_decel_nm, t_dwell_nm)
    dt_active = dt_accel_s + dt_cruise_s + dt_decel_s
    duty_cycle_active = dt_active / cycle_time

    return {
        "ok": True,
        "t_rms_nm": round(t_rms, 6),
        "t_peak_nm": round(t_peak, 6),
        "cycle_time_s": round(cycle_time, 6),
        "duty_cycle_active": round(duty_cycle_active, 6),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. motor_constants
# ═══════════════════════════════════════════════════════════════════════════════

def motor_constants(
    rated_torque_nm: float,
    rated_current_a: float,
    no_load_speed_rpm: float,
    rated_voltage_v: float,
    winding_resistance_ohm: float,
    poles: int = 2,
) -> dict:
    """
    Derive motor constants from datasheet parameters.

    Torque constant:
        Kt [N·m/A] = rated_torque / rated_current

    Back-EMF constant (Ke = Kt for SI units):
        Ke [V·s/rad] = Kt  (they are equal in consistent SI units)

    No-load back-EMF at rated speed:
        E_bemf [V] = Ke × ω_no_load

    Winding I²R copper loss at rated current:
        P_copper [W] = I_rated² × R_winding

    Stall torque estimate (from voltage/Ke/R):
        T_stall [N·m] = Kt × V_rated / R_winding
        (at zero speed, all voltage drops across resistance)

    Parameters
    ----------
    rated_torque_nm       : float — rated output torque [N·m]
    rated_current_a       : float — rated current (phase or armature) [A]
    no_load_speed_rpm     : float — no-load (ideal) speed at rated voltage [RPM]
    rated_voltage_v       : float — rated terminal/supply voltage [V]
    winding_resistance_ohm: float — phase (or armature) resistance [Ω]
    poles                 : int   — number of motor poles (default 2; used for electrical frequency)

    Returns
    -------
    dict: ok, kt_nm_per_a, ke_v_s_per_rad, omega_no_load_rad_s,
          e_bemf_rated_v, p_copper_w, t_stall_nm, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("rated_torque_nm", rated_torque_nm),
        ("rated_current_a", rated_current_a),
        ("no_load_speed_rpm", no_load_speed_rpm),
        ("rated_voltage_v", rated_voltage_v),
        ("winding_resistance_ohm", winding_resistance_ohm),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    if not isinstance(poles, int) or poles < 2 or poles % 2 != 0:
        return {"ok": False, "reason": f"poles must be an even integer >= 2, got {poles!r}"}

    kt = rated_torque_nm / rated_current_a
    ke = kt  # Kt == Ke in consistent SI units (V·s/rad = N·m/A)

    omega_no_load = no_load_speed_rpm * (2.0 * math.pi / 60.0)
    e_bemf = ke * omega_no_load
    p_copper = rated_current_a ** 2 * winding_resistance_ohm
    t_stall = kt * rated_voltage_v / winding_resistance_ohm

    if e_bemf > rated_voltage_v * (1.0 + _VOLTAGE_HEADROOM_FRAC):
        msg = (
            f"voltage_insufficient: back-EMF at no-load speed "
            f"({e_bemf:.3f} V) exceeds rated voltage ({rated_voltage_v:.3f} V); "
            "check no_load_speed_rpm or rated_voltage_v inputs."
        )
        sol_warnings.append(msg)
        warnings.warn(f"motor_constants: {msg}", stacklevel=2)

    return {
        "ok": True,
        "kt_nm_per_a": round(kt, 8),
        "ke_v_s_per_rad": round(ke, 8),
        "omega_no_load_rad_s": round(omega_no_load, 6),
        "e_bemf_rated_v": round(e_bemf, 6),
        "p_copper_w": round(p_copper, 6),
        "t_stall_nm": round(t_stall, 6),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. dc_operating_point
# ═══════════════════════════════════════════════════════════════════════════════

def dc_operating_point(
    speed_rpm: float,
    torque_nm: float,
    kt_nm_per_a: float,
    ke_v_s_per_rad: float,
    winding_resistance_ohm: float,
    supply_voltage_v: float,
) -> dict:
    """
    DC brush motor operating point at a given speed and torque.

    Armature current:
        I_a = T / Kt

    Back-EMF:
        E_bemf = Ke × ω

    Required terminal voltage:
        V_t = E_bemf + I_a × Ra

    Copper loss:
        P_copper = I_a² × Ra

    Output power:
        P_out = T × ω

    Efficiency:
        η = P_out / (V_t × I_a)

    Warnings
    --------
    - "voltage_insufficient" if V_t > supply_voltage_v.
    - "over_current" if I_a > rated (not checked here; caller must compare).

    Parameters
    ----------
    speed_rpm             : float — shaft speed [RPM]
    torque_nm             : float — output torque [N·m]
    kt_nm_per_a           : float — torque constant [N·m/A]
    ke_v_s_per_rad        : float — back-EMF constant [V·s/rad]
    winding_resistance_ohm: float — armature resistance [Ω]
    supply_voltage_v      : float — available DC supply voltage [V]

    Returns
    -------
    dict: ok, omega_rad_s, i_a_a, e_bemf_v, v_terminal_v, p_copper_w,
          p_out_w, p_input_w, efficiency, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("speed_rpm", speed_rpm), ("torque_nm", torque_nm),
        ("kt_nm_per_a", kt_nm_per_a), ("ke_v_s_per_rad", ke_v_s_per_rad),
        ("winding_resistance_ohm", winding_resistance_ohm),
        ("supply_voltage_v", supply_voltage_v),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    omega = speed_rpm * (2.0 * math.pi / 60.0)
    i_a = torque_nm / kt_nm_per_a
    e_bemf = ke_v_s_per_rad * omega
    v_terminal = e_bemf + i_a * winding_resistance_ohm
    p_copper = i_a ** 2 * winding_resistance_ohm
    p_out = torque_nm * omega
    p_input = v_terminal * i_a
    efficiency = p_out / p_input if p_input > 0 else 0.0

    if v_terminal > supply_voltage_v:
        msg = (
            f"voltage_insufficient: required terminal voltage {v_terminal:.3f} V "
            f"> supply {supply_voltage_v:.3f} V at {speed_rpm:.1f} RPM, "
            f"{torque_nm:.3f} N·m; operating point is not achievable."
        )
        sol_warnings.append(msg)
        warnings.warn(f"dc_operating_point: {msg}", stacklevel=2)

    return {
        "ok": True,
        "omega_rad_s": round(omega, 6),
        "i_a_a": round(i_a, 6),
        "e_bemf_v": round(e_bemf, 6),
        "v_terminal_v": round(v_terminal, 6),
        "p_copper_w": round(p_copper, 6),
        "p_out_w": round(p_out, 4),
        "p_input_w": round(p_input, 4),
        "efficiency": round(efficiency, 6),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 7. bldc_pmsm_operating_point
# ═══════════════════════════════════════════════════════════════════════════════

def bldc_pmsm_operating_point(
    speed_rpm: float,
    torque_nm: float,
    kt_nm_per_a: float,
    ke_v_s_per_rad: float,
    phase_resistance_ohm: float,
    dc_link_voltage_v: float,
    pole_pairs: int = 2,
    id_a: float = 0.0,
) -> dict:
    """
    BLDC/PMSM operating point using simplified d-q axis model.

    In the q-axis (torque-producing current):
        Iq = T / (1.5 × p × Ke)   [p = pole pairs; 1.5 factor for three-phase]
        (For BLDC with trapezoidal commutation the factor is 1.0; 1.5 is PMSM FOC)

    Phase back-EMF (line-to-neutral peak):
        E_ph = Ke × ω_elec  where ω_elec = pole_pairs × ω_mech

    Required terminal voltage (no inductance voltage drop approximation):
        V_ph = sqrt((E_ph + Id × 0)² + (Iq × R_s)²)
        (simplified: V_ph ≈ sqrt(E_ph² + (Iq × R_s)²))

    Required DC-link voltage (six-step modulation, V_dc >= sqrt(2) × V_line_peak):
        V_line_peak = sqrt(3) × V_ph
        V_dc_min = sqrt(2) × V_line_peak / sqrt(3)   (simplified)
        Simpler conservative estimate: V_dc_min = E_ph × sqrt(2) + 2 × I_s × R_s

    Copper loss (three phases):
        P_copper = 1.5 × R_s × (Iq² + Id²)

    Parameters
    ----------
    speed_rpm           : float — mechanical shaft speed [RPM]
    torque_nm           : float — output torque [N·m]
    kt_nm_per_a         : float — torque constant [N·m/A_peak]
    ke_v_s_per_rad      : float — back-EMF constant [V·s/rad_mech, line-to-line peak / ω_mech]
    phase_resistance_ohm: float — per-phase resistance [Ω]
    dc_link_voltage_v   : float — available DC bus voltage [V]
    pole_pairs          : int   — number of pole pairs (default 2)
    id_a                : float — d-axis current [A] (flux weakening; 0 for max-torque-per-amp)

    Returns
    -------
    dict: ok, omega_mech_rad_s, omega_elec_rad_s, iq_a, is_a, e_bemf_v,
          v_phase_v, v_dc_min_v, p_copper_w, p_out_w, efficiency, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("speed_rpm", speed_rpm), ("torque_nm", torque_nm),
        ("kt_nm_per_a", kt_nm_per_a), ("ke_v_s_per_rad", ke_v_s_per_rad),
        ("phase_resistance_ohm", phase_resistance_ohm),
        ("dc_link_voltage_v", dc_link_voltage_v),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    if not isinstance(pole_pairs, int) or pole_pairs < 1:
        return {"ok": False, "reason": f"pole_pairs must be a positive integer, got {pole_pairs!r}"}

    err = _chk_nonneg(id_a, "id_a")
    if err:
        return {"ok": False, "reason": err}

    omega_mech = speed_rpm * (2.0 * math.pi / 60.0)
    omega_elec = pole_pairs * omega_mech

    # Torque equation for PMSM FOC: T = 1.5 × p × Kt × Iq  (where Kt = Ke in SI)
    iq_a = torque_nm / (1.5 * pole_pairs * kt_nm_per_a)

    # Phase back-EMF (line-to-neutral peak)
    e_bemf = ke_v_s_per_rad * omega_elec / math.sqrt(3.0)  # simplified per-phase

    is_a = math.sqrt(iq_a ** 2 + id_a ** 2)  # total phase current magnitude

    # Phase terminal voltage (simplified, ignoring inductance)
    v_phase = math.sqrt(e_bemf ** 2 + (iq_a * phase_resistance_ohm) ** 2)

    # Minimum DC-link voltage (conservatively: V_dc >= sqrt(3) × V_ph_peak × sqrt(2)/sqrt(3))
    v_dc_min = math.sqrt(3.0) * v_phase * math.sqrt(2.0) / math.sqrt(3.0)  # ≈ sqrt(2) × V_ph
    v_dc_min = math.sqrt(2.0) * v_phase  # simplified

    p_copper = 1.5 * phase_resistance_ohm * (iq_a ** 2 + id_a ** 2)
    p_out = torque_nm * omega_mech
    p_input = p_out + p_copper
    efficiency = p_out / p_input if p_input > 0 else 0.0

    if v_dc_min > dc_link_voltage_v:
        msg = (
            f"voltage_insufficient: minimum DC-link voltage required "
            f"{v_dc_min:.2f} V > available {dc_link_voltage_v:.2f} V "
            f"at {speed_rpm:.1f} RPM, {torque_nm:.3f} N·m."
        )
        sol_warnings.append(msg)
        warnings.warn(f"bldc_pmsm_operating_point: {msg}", stacklevel=2)

    return {
        "ok": True,
        "omega_mech_rad_s": round(omega_mech, 6),
        "omega_elec_rad_s": round(omega_elec, 6),
        "iq_a": round(iq_a, 6),
        "is_a": round(is_a, 6),
        "e_bemf_v": round(e_bemf, 6),
        "v_phase_v": round(v_phase, 6),
        "v_dc_min_v": round(v_dc_min, 6),
        "p_copper_w": round(p_copper, 6),
        "p_out_w": round(p_out, 4),
        "p_input_w": round(p_input, 4),
        "efficiency": round(efficiency, 6),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 8. induction_motor_slip_torque
# ═══════════════════════════════════════════════════════════════════════════════

def induction_motor_slip_torque(
    synchronous_speed_rpm: float,
    rotor_resistance_ohm: float,
    stator_resistance_ohm: float,
    leakage_reactance_ohm: float,
    supply_voltage_v: float,
    slip: float,
) -> dict:
    """
    Basic induction motor torque at a given slip using the approximate
    equivalent circuit (Thevenin-reduced, ignoring magnetizing branch for
    torque calculation — Chapman §6.4 approximate model).

    Air-gap power:
        P_ag = 3 × V_s² × (R2/s) / [(Rs + R2/s)² + X_eq²]

    Torque:
        T = P_ag / ω_sync

    where X_eq = stator + rotor leakage reactance (lumped),
          R2 = rotor resistance referred to stator.

    Warnings
    --------
    - "high_slip": slip > _MAX_SLIP (20 %) → unstable operating region.
    - "negative_slip": generator mode if slip < 0 (allowed, noted).

    Parameters
    ----------
    synchronous_speed_rpm : float — synchronous (no-load) speed [RPM]
    rotor_resistance_ohm  : float — rotor resistance referred to stator [Ω]
    stator_resistance_ohm : float — stator resistance [Ω]
    leakage_reactance_ohm : float — total leakage reactance (stator + rotor) [Ω]
    supply_voltage_v      : float — per-phase RMS supply voltage [V] (line-to-neutral)
    slip                  : float — per-unit slip s = (ω_s − ω_r) / ω_s

    Returns
    -------
    dict: ok, omega_sync_rad_s, omega_rotor_rad_s, rotor_speed_rpm,
          torque_nm, air_gap_power_w, stator_copper_loss_w, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("synchronous_speed_rpm", synchronous_speed_rpm),
        ("rotor_resistance_ohm", rotor_resistance_ohm),
        ("stator_resistance_ohm", stator_resistance_ohm),
        ("leakage_reactance_ohm", leakage_reactance_ohm),
        ("supply_voltage_v", supply_voltage_v),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    if not isinstance(slip, (int, float)) or math.isnan(slip):
        return {"ok": False, "reason": f"slip must be a finite number, got {slip!r}"}

    if slip == 0.0:
        return {"ok": False, "reason": "slip must be non-zero (zero slip = synchronous speed, no torque)"}

    omega_sync = synchronous_speed_rpm * (2.0 * math.pi / 60.0)
    omega_rotor = omega_sync * (1.0 - slip)
    rotor_speed_rpm = omega_rotor * (60.0 / (2.0 * math.pi))

    # Approximate equivalent circuit
    r2_over_s = rotor_resistance_ohm / slip
    denom = (stator_resistance_ohm + r2_over_s) ** 2 + leakage_reactance_ohm ** 2
    if denom == 0.0:
        return {"ok": False, "reason": "denominator in torque equation is zero; check inputs"}

    # Air-gap power (3-phase)
    p_ag = 3.0 * supply_voltage_v ** 2 * r2_over_s / denom
    torque = p_ag / omega_sync if omega_sync > 0 else 0.0

    # Stator copper loss estimate (same current used)
    i_s_sq = supply_voltage_v ** 2 / denom  # per-phase current squared
    p_stator_copper = 3.0 * stator_resistance_ohm * i_s_sq

    if abs(slip) > _MAX_SLIP:
        msg = (
            f"high_slip: slip = {slip:.3f} > {_MAX_SLIP:.2f}; "
            "operating in unstable region (beyond breakdown torque). "
            "Reduce load or check motor selection."
        )
        sol_warnings.append(msg)
        warnings.warn(f"induction_motor_slip_torque: {msg}", stacklevel=2)

    if slip < 0.0:
        msg = (
            f"negative_slip: slip = {slip:.4f} < 0; motor is in generator mode "
            "(rotor faster than synchronous speed)."
        )
        sol_warnings.append(msg)
        warnings.warn(f"induction_motor_slip_torque: {msg}", stacklevel=2)

    return {
        "ok": True,
        "omega_sync_rad_s": round(omega_sync, 6),
        "omega_rotor_rad_s": round(omega_rotor, 6),
        "rotor_speed_rpm": round(rotor_speed_rpm, 4),
        "torque_nm": round(torque, 6),
        "air_gap_power_w": round(p_ag, 4),
        "stator_copper_loss_w": round(p_stator_copper, 4),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 9. inverter_sizing
# ═══════════════════════════════════════════════════════════════════════════════

def inverter_sizing(
    peak_phase_current_a: float,
    peak_phase_voltage_v: float,
    dc_link_voltage_v: float,
    switching_freq_hz: float,
    conduction_voltage_drop_v: float = 2.0,
    switching_energy_uj: float = 100.0,
    phases: int = 3,
    current_derating: float = 0.80,
) -> dict:
    """
    Three-phase inverter sizing: required device ratings, estimated
    switching and conduction losses.

    Device ratings (with derating):
        I_device_rated = I_peak / current_derating
        V_device_rated = dc_link_voltage_v × 2  (conservative for transients)

    Switching loss per device (per switching cycle):
        P_sw = N_switches × switching_energy_uj × 1e-6 × switching_freq_hz

    Conduction loss (all switches, worst case all conducting):
        P_cond = phases × 2 × conduction_voltage_drop_v × I_rms
        I_rms ≈ I_peak / sqrt(2)

    Total inverter loss:
        P_total = P_sw + P_cond

    Parameters
    ----------
    peak_phase_current_a    : float — peak phase current [A]
    peak_phase_voltage_v    : float — peak phase voltage [V]
    dc_link_voltage_v       : float — DC bus voltage [V]
    switching_freq_hz       : float — PWM switching frequency [Hz]
    conduction_voltage_drop_v: float — device on-state voltage drop [V] (default 2.0 V)
    switching_energy_uj     : float — per-device switching energy [μJ/cycle] (default 100 μJ)
    phases                  : int   — number of phases (default 3)
    current_derating        : float — device current derating factor 0 < factor ≤ 1 (default 0.80)

    Returns
    -------
    dict: ok, i_device_rated_a, v_device_rated_v, i_rms_a, p_switching_w,
          p_conduction_w, p_total_loss_w, n_devices, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("peak_phase_current_a", peak_phase_current_a),
        ("peak_phase_voltage_v", peak_phase_voltage_v),
        ("dc_link_voltage_v", dc_link_voltage_v),
        ("switching_freq_hz", switching_freq_hz),
        ("conduction_voltage_drop_v", conduction_voltage_drop_v),
        ("switching_energy_uj", switching_energy_uj),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    if not isinstance(phases, int) or phases < 1:
        return {"ok": False, "reason": f"phases must be a positive integer, got {phases!r}"}

    err = _chk_frac(current_derating, "current_derating")
    if err:
        return {"ok": False, "reason": err}

    n_devices = phases * 2  # high-side + low-side per phase
    i_device_rated = peak_phase_current_a / current_derating
    v_device_rated = dc_link_voltage_v * 2.0  # conservative (include transient overshoot)

    i_rms = peak_phase_current_a / math.sqrt(2.0)
    p_switching = n_devices * (switching_energy_uj * 1e-6) * switching_freq_hz
    p_conduction = phases * 2.0 * conduction_voltage_drop_v * i_rms
    p_total = p_switching + p_conduction

    return {
        "ok": True,
        "i_device_rated_a": round(i_device_rated, 4),
        "v_device_rated_v": round(v_device_rated, 4),
        "i_rms_a": round(i_rms, 6),
        "p_switching_w": round(p_switching, 4),
        "p_conduction_w": round(p_conduction, 4),
        "p_total_loss_w": round(p_total, 4),
        "n_devices": n_devices,
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 10. regen_energy
# ═══════════════════════════════════════════════════════════════════════════════

def regen_energy(
    inertia_kgm2: float,
    speed_initial_rpm: float,
    speed_final_rpm: float,
    drivetrain_efficiency: float = 0.90,
) -> dict:
    """
    Compute recoverable energy during regenerative deceleration.

    Kinetic energy change:
        ΔKE = 0.5 × J × (ω_i² − ω_f²)

    Recoverable energy:
        E_regen = ΔKE × η_drivetrain   [J]

    Parameters
    ----------
    inertia_kgm2          : float — total rotating inertia [kg·m²]
    speed_initial_rpm      : float — initial speed [RPM]
    speed_final_rpm        : float — final speed [RPM] (can be 0)
    drivetrain_efficiency  : float — round-trip drivetrain efficiency (default 0.90)

    Returns
    -------
    dict: ok, delta_ke_j, e_regen_j, e_dissipated_j, warnings
    """
    sol_warnings: List[str] = []

    err = _chk_pos(inertia_kgm2, "inertia_kgm2")
    if err:
        return {"ok": False, "reason": err}

    err = _chk_pos(speed_initial_rpm, "speed_initial_rpm")
    if err:
        return {"ok": False, "reason": err}

    err = _chk_nonneg(speed_final_rpm, "speed_final_rpm")
    if err:
        return {"ok": False, "reason": err}

    err = _chk_frac(drivetrain_efficiency, "drivetrain_efficiency")
    if err:
        return {"ok": False, "reason": err}

    if speed_final_rpm >= speed_initial_rpm:
        return {
            "ok": False,
            "reason": (
                f"speed_final_rpm ({speed_final_rpm}) must be less than "
                f"speed_initial_rpm ({speed_initial_rpm}) for regenerative braking."
            ),
        }

    omega_i = speed_initial_rpm * (2.0 * math.pi / 60.0)
    omega_f = speed_final_rpm * (2.0 * math.pi / 60.0)
    delta_ke = 0.5 * inertia_kgm2 * (omega_i ** 2 - omega_f ** 2)
    e_regen = delta_ke * drivetrain_efficiency
    e_dissipated = delta_ke - e_regen

    return {
        "ok": True,
        "delta_ke_j": round(delta_ke, 4),
        "e_regen_j": round(e_regen, 4),
        "e_dissipated_j": round(e_dissipated, 4),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 11. brake_resistor_sizing
# ═══════════════════════════════════════════════════════════════════════════════

def brake_resistor_sizing(
    regen_energy_j: float,
    dc_link_voltage_v: float,
    discharge_time_s: float,
    overvoltage_margin_frac: float = 0.10,
) -> dict:
    """
    Size a brake resistor (dynamic braking resistor) for a DC-link inverter.

    The brake chopper activates when V_dc exceeds a threshold and discharges
    regen energy through the resistor.

    Brake threshold voltage:
        V_brake = dc_link_voltage × (1 + overvoltage_margin_frac)

    Required resistor value (for a given discharge time from E = V²/R × t → R):
        R_brake = V_brake² × discharge_time / (2 × E_regen)
        (Derived from: E = integral(V²/R dt) ≈ V²/R × t for constant voltage)

    Average power in resistor:
        P_avg = E_regen / discharge_time

    Peak power (at V_brake):
        P_peak = V_brake² / R_brake

    Parameters
    ----------
    regen_energy_j        : float — total energy to dissipate [J]
    dc_link_voltage_v     : float — nominal DC-link voltage [V]
    discharge_time_s      : float — maximum allowable discharge time [s]
    overvoltage_margin_frac: float — fractional overvoltage above nominal (default 0.10 = 10 %)

    Returns
    -------
    dict: ok, v_brake_v, r_brake_ohm, p_avg_w, p_peak_w, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("regen_energy_j", regen_energy_j),
        ("dc_link_voltage_v", dc_link_voltage_v),
        ("discharge_time_s", discharge_time_s),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    err = _chk_nonneg(overvoltage_margin_frac, "overvoltage_margin_frac")
    if err:
        return {"ok": False, "reason": err}

    v_brake = dc_link_voltage_v * (1.0 + overvoltage_margin_frac)
    r_brake = v_brake ** 2 * discharge_time_s / (2.0 * regen_energy_j)
    p_avg = regen_energy_j / discharge_time_s
    p_peak = v_brake ** 2 / r_brake

    return {
        "ok": True,
        "v_brake_v": round(v_brake, 4),
        "r_brake_ohm": round(r_brake, 4),
        "p_avg_w": round(p_avg, 4),
        "p_peak_w": round(p_peak, 4),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 12. thermal_duty_check
# ═══════════════════════════════════════════════════════════════════════════════

def thermal_duty_check(
    p_loss_w: float,
    rth_winding_ambient: float,
    t_ambient_c: float,
    duty_cycle: float = 1.0,
    t_max_c: float = _OVER_TEMP_MAX_C,
    thermal_time_constant_s: float = 0.0,
    cycle_time_s: float = 0.0,
) -> dict:
    """
    Motor thermal duty-cycle check: steady-state winding temperature from
    ambient, losses, and thermal resistance, with over-temperature warning.

    Steady-state temperature rise (IEC 60034-1 S1 continuous duty):
        ΔT_ss = P_loss × Rth_winding_ambient

    Effective losses for intermittent duty (duty_cycle < 1):
        P_eff = P_loss × duty_cycle

    Approximate temperature with duty cycle:
        ΔT = P_eff × Rth

    Thermal time constant check (if both thermal_time_constant_s and
    cycle_time_s are provided):
        Effective temperature rise accounts for incomplete heating/cooling:
        ΔT_eff = ΔT_ss × (1 - exp(-t_on / τ))  where t_on = duty × cycle_time

    Parameters
    ----------
    p_loss_w                : float — total motor loss at operating point [W]
    rth_winding_ambient     : float — winding-to-ambient thermal resistance [°C/W]
    t_ambient_c             : float — ambient temperature [°C]
    duty_cycle              : float — duty cycle S (0 < S ≤ 1, default 1.0 = continuous)
    t_max_c                 : float — maximum winding temperature [°C] (default 130 °C Class F)
    thermal_time_constant_s : float — motor thermal time constant [s] (0 = not used)
    cycle_time_s            : float — cycle time for intermittent duty [s] (0 = not used)

    Returns
    -------
    dict: ok, t_winding_c, delta_t_k, t_margin_k, over_temp, warnings
    """
    sol_warnings: List[str] = []

    err = _chk_pos(p_loss_w, "p_loss_w")
    if err:
        return {"ok": False, "reason": err}

    err = _chk_pos(rth_winding_ambient, "rth_winding_ambient")
    if err:
        return {"ok": False, "reason": err}

    if not isinstance(t_ambient_c, (int, float)) or math.isnan(t_ambient_c):
        return {"ok": False, "reason": f"t_ambient_c must be a finite number, got {t_ambient_c!r}"}

    err = _chk_frac(duty_cycle, "duty_cycle")
    if err:
        return {"ok": False, "reason": err}

    err = _chk_pos(t_max_c + 273.15, "t_max_c (must be > −273.15 °C)")
    if t_max_c < 0:
        return {"ok": False, "reason": f"t_max_c must be >= 0 °C, got {t_max_c!r}"}

    for name, val in [
        ("thermal_time_constant_s", thermal_time_constant_s),
        ("cycle_time_s", cycle_time_s),
    ]:
        err = _chk_nonneg(val, name)
        if err:
            return {"ok": False, "reason": err}

    # Effective power with duty cycle
    p_eff = p_loss_w * duty_cycle
    delta_t_ss = p_eff * rth_winding_ambient

    # Apply thermal time-constant correction if data is available
    delta_t = delta_t_ss
    if thermal_time_constant_s > 0 and cycle_time_s > 0:
        t_on = duty_cycle * cycle_time_s
        delta_t = delta_t_ss * (1.0 - math.exp(-t_on / thermal_time_constant_s))

    t_winding = t_ambient_c + delta_t
    t_margin = t_max_c - t_winding
    over_temp = t_winding > t_max_c

    if over_temp:
        msg = (
            f"over_temp: winding temperature {t_winding:.1f} °C > T_max {t_max_c:.1f} °C "
            f"(margin = {t_margin:.1f} K); improve cooling or derate motor output."
        )
        sol_warnings.append(msg)
        warnings.warn(f"thermal_duty_check: {msg}", stacklevel=2)

    return {
        "ok": True,
        "t_winding_c": round(t_winding, 4),
        "delta_t_k": round(delta_t, 4),
        "t_margin_k": round(t_margin, 4),
        "over_temp": over_temp,
        "warnings": sol_warnings,
    }
