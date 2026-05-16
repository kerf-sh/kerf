"""
Switching DC-DC converter design — pure Python (math only).

Distinct from:
  kerf_electronics.battery    — battery pack sizing
  kerf_electronics.pdn        — power distribution network (bulk decoupling)
  kerf_electronics.leddriver  — LED constant-current driver (CC-specific)
  kerf_electronics.afilter    — analog filter design
  kerf_electronics.rfmatch    — RF impedance matching
  kerf_electronics.motordrive — motor & inverter drive sizing

Capabilities
------------
buck_design
    Steady-state CCM design for a synchronous/non-synchronous buck converter:
    duty cycle, inductor, output cap, switch/diode/inductor peak & RMS currents,
    voltage stresses, conduction+switching loss, efficiency.

boost_design
    Steady-state CCM design for a boost converter, including RHP-zero frequency
    warning (critical for closed-loop bandwidth limitation).

buck_boost_design
    Steady-state CCM design for an inverting buck-boost, including RHP-zero
    frequency and polarity inversion note.

flyback_design
    Isolated flyback: turns ratio, primary inductance, peak primary/secondary
    currents, leakage-spike energy, RCD-snubber sizing note, efficiency.

sepic_design
    SEPIC (Single-Ended Primary-Inductance Converter): duty cycle, coupled
    inductor / split inductor sizing, capacitor stresses, peak currents.

converter_thermal
    Junction temperature from power loss × junction-to-ambient thermal resistance.

All functions return plain dicts {ok: bool, ...}.
Out-of-range, DCM-when-CCM-assumed, over-stress, efficiency-low, and
RHP-limited-bandwidth conditions are flagged via warnings.warn; dicts still
carry ok=True with a "warnings" list.  Functions never raise.

References
----------
  Erickson & Maksimovic, "Fundamentals of Power Electronics" (3rd ed., Springer, 2020)
  Pressman, Billings & Morey, "Switching Power Supply Design" (3rd ed., McGraw-Hill, 2009)
  Kazimierczuk, "Pulse-Width Modulated DC-DC Power Converters" (2nd ed., Wiley, 2016)
  Ridley Engineering application notes (boost/buck-boost RHP zero)
  Unitrode/TI SLUP169 (flyback design)

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import List, Optional

# ── Warning thresholds ────────────────────────────────────────────────────────
_MIN_EFFICIENCY_WARN = 0.70       # below 70 % efficiency → warn
_MAX_DUTY_WARN = 0.95             # duty cycle > 95 % → warn (near rail saturation)
_DCM_BOUNDARY_MARGIN = 0.05      # 5 % margin before CCM/DCM boundary warning
_OVER_STRESS_DERATING = 0.80     # voltage stress > 80 % rated → warn
_RHP_BANDWIDTH_FRACTION = 0.20   # if f_rhp < 20 % of fsw → RHP-limited warning


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
    """Return error string if value is not in (0, 1)."""
    if not isinstance(value, (int, float)) or math.isnan(value) or value <= 0 or value >= 1:
        return f"{name} must be in (0, 1), got {value!r}"
    return None


# ── Shared helpers ────────────────────────────────────────────────────────────

def _inductor_rms_current(i_avg: float, delta_il: float) -> float:
    """
    RMS current in an inductor with triangular ripple.

    I_L_rms = sqrt(I_avg² + (ΔIL / (2√3))²)

    This is the exact RMS for a triangle wave riding on a DC offset.
    """
    return math.sqrt(i_avg ** 2 + (delta_il / (2.0 * math.sqrt(3.0))) ** 2)


def _switch_rms_current_buck(i_avg_switch: float, delta_il: float, duty: float) -> float:
    """
    RMS current through the high-side switch (buck/flyback primary).

    For CCM: I_sw_rms = sqrt(D) × sqrt(I_avg_switch² + (ΔIL/(2√3))²)
    where I_avg_switch = I_out / D  (buck average switch current).
    """
    # RMS over the duty cycle only
    return math.sqrt(duty) * math.sqrt(i_avg_switch ** 2 + (delta_il / (2.0 * math.sqrt(3.0))) ** 2)


def _diode_rms_current(i_avg_diode: float, delta_il: float, d_prime: float) -> float:
    """
    RMS current through the catch diode / rectifier.

    I_D_rms = sqrt(D') × sqrt(I_avg_diode² + (ΔIL/(2√3))²)
    """
    return math.sqrt(d_prime) * math.sqrt(i_avg_diode ** 2 + (delta_il / (2.0 * math.sqrt(3.0))) ** 2)


def _output_cap_esr_ripple(delta_il: float, esr_ohm: float) -> float:
    """Output voltage ripple contribution from capacitor ESR: ΔV_esr = ΔIL × ESR."""
    return delta_il * esr_ohm


def _output_cap_ripple(delta_il: float, c_out_f: float, fsw: float, duty: float) -> float:
    """
    Output voltage ripple from finite capacitance (CCM buck/boost/sepic).

    For a buck: ΔVout = ΔIL / (8 × C × fsw)   (parabolic approximation)
    This formula is exact for the buck; for boost/sepic it is used as an
    approximation (per Erickson §2.2).
    """
    if c_out_f <= 0 or fsw <= 0:
        return 0.0
    return delta_il / (8.0 * c_out_f * fsw)


def _switching_loss(
    v_switch: float,
    i_switch: float,
    fsw: float,
    t_rise_s: float,
    t_fall_s: float,
) -> float:
    """
    Estimate MOSFET/IGBT switching loss (hard-switching).

    P_sw = 0.5 × V_switch × I_switch × (t_rise + t_fall) × fsw

    Reference: Erickson §4.3 / Pressman §11.4.
    """
    return 0.5 * v_switch * i_switch * (t_rise_s + t_fall_s) * fsw


def _conduction_loss_switch(i_rms: float, r_ds_on: float) -> float:
    """MOSFET conduction loss: P_cond = I_rms² × Rds(on)."""
    return i_rms ** 2 * r_ds_on


def _diode_loss(i_avg: float, v_forward: float) -> float:
    """Diode conduction loss: P_diode = I_avg × Vf."""
    return i_avg * v_forward


def _inductor_dcr_loss(i_rms: float, dcr_ohm: float) -> float:
    """Inductor DCR copper loss: P_dcr = I_rms² × DCR."""
    return i_rms ** 2 * dcr_ohm


# ═══════════════════════════════════════════════════════════════════════════════
# 1. buck_design
# ═══════════════════════════════════════════════════════════════════════════════

def buck_design(
    v_in: float,
    v_out: float,
    i_out: float,
    fsw: float,
    ripple_frac: float = 0.30,
    c_out_f: float = 100e-6,
    esr_ohm: float = 0.020,
    r_ds_on: float = 0.050,
    v_diode: float = 0.5,
    dcr_ohm: float = 0.010,
    t_rise_s: float = 20e-9,
    t_fall_s: float = 20e-9,
) -> dict:
    """
    Steady-state CCM design for a buck (step-down) converter.

    Duty cycle:
        D = Vout / Vin  (CCM, ideal)

    Critical (boundary) inductance:
        L_crit = (Vin - Vout) × D / (2 × Iout × fsw)

    Inductor for target ripple fraction:
        L = (Vin - Vout) × D / (fsw × ΔIL)   where ΔIL = ripple_frac × Iout

    Peak/valley inductor current:
        I_L_peak = Iout + ΔIL / 2
        I_L_valley = Iout − ΔIL / 2

    Output capacitor for target ripple:
        C_min = ΔIL / (8 × fsw × ΔVout)
        where ΔVout is derived from c_out_f or a target (ΔVout_esr + ΔVout_cap).

    Switch voltage stress: Vds_max = Vin
    Diode voltage stress:  Vd_max  = Vin

    References: Erickson §1.3, §2.2, §4.3.

    Parameters
    ----------
    v_in        : float — input voltage [V]
    v_out       : float — output voltage [V]
    i_out       : float — output (load) current [A]
    fsw         : float — switching frequency [Hz]
    ripple_frac : float — inductor current ripple as a fraction of Iout (default 0.30 = 30 %)
    c_out_f     : float — output capacitor [F] (default 100 µF)
    esr_ohm     : float — output cap ESR [Ω] (default 20 mΩ)
    r_ds_on     : float — switch Rds(on) [Ω] (default 50 mΩ)
    v_diode     : float — catch diode forward voltage [V] (default 0.5 V)
    dcr_ohm     : float — inductor DCR [Ω] (default 10 mΩ)
    t_rise_s    : float — switch current rise time [s] (default 20 ns)
    t_fall_s    : float — switch current fall time [s] (default 20 ns)

    Returns
    -------
    dict: ok, duty, l_h, l_crit_h, ccm, delta_il_a, i_l_peak_a, i_l_valley_a,
          i_l_rms_a, i_sw_rms_a, i_diode_rms_a, v_sw_stress_v, v_diode_stress_v,
          c_out_min_f, delta_v_esr_v, delta_v_cap_v, delta_v_total_v,
          p_sw_cond_w, p_sw_switch_w, p_diode_w, p_dcr_w, p_total_loss_w,
          p_out_w, efficiency, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("v_in", v_in), ("v_out", v_out), ("i_out", i_out), ("fsw", fsw),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    if v_out >= v_in:
        return {"ok": False, "reason": f"v_out ({v_out} V) must be < v_in ({v_in} V) for a buck converter"}

    err = _chk_frac(ripple_frac, "ripple_frac")
    if err:
        return {"ok": False, "reason": err}

    for name, val in [
        ("c_out_f", c_out_f), ("esr_ohm", esr_ohm), ("r_ds_on", r_ds_on),
        ("v_diode", v_diode), ("dcr_ohm", dcr_ohm), ("t_rise_s", t_rise_s), ("t_fall_s", t_fall_s),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    # ── Core design ──────────────────────────────────────────────────────────
    duty = v_out / v_in
    d_prime = 1.0 - duty

    delta_il = ripple_frac * i_out
    l_h = (v_in - v_out) * duty / (fsw * delta_il)
    l_crit_h = (v_in - v_out) * duty / (2.0 * i_out * fsw)
    ccm = l_h >= l_crit_h  # always True by design; warn if close

    i_l_peak = i_out + delta_il / 2.0
    i_l_valley = i_out - delta_il / 2.0
    i_l_rms = _inductor_rms_current(i_out, delta_il)

    # Switch conducts during D; average = I_out
    i_sw_rms = _switch_rms_current_buck(i_out, delta_il, duty)

    # Diode conducts during D'; average through diode = I_out × D'
    i_diode_avg = i_out * d_prime
    i_diode_rms = _diode_rms_current(i_out, delta_il, d_prime)

    # Voltage stresses
    v_sw_stress = v_in
    v_diode_stress = v_in

    # Output cap ripple
    delta_v_esr = _output_cap_esr_ripple(delta_il, esr_ohm)
    delta_v_cap = _output_cap_ripple(delta_il, c_out_f, fsw, duty)
    delta_v_total = delta_v_esr + delta_v_cap

    # Minimum cap for 1 % ripple (design target independent of provided c_out_f)
    target_ripple_v = 0.01 * v_out
    c_out_min = delta_il / (8.0 * fsw * target_ripple_v) if target_ripple_v > 0 else 0.0

    # ── Loss estimate ────────────────────────────────────────────────────────
    p_sw_cond = _conduction_loss_switch(i_sw_rms, r_ds_on)
    p_sw_switch = _switching_loss(v_in, i_out, fsw, t_rise_s, t_fall_s)
    p_diode = _diode_loss(i_diode_avg, v_diode)
    p_dcr = _inductor_dcr_loss(i_l_rms, dcr_ohm)
    p_total_loss = p_sw_cond + p_sw_switch + p_diode + p_dcr

    p_out = v_out * i_out
    p_in = p_out + p_total_loss
    efficiency = p_out / p_in if p_in > 0 else 0.0

    # ── Warnings ─────────────────────────────────────────────────────────────
    if duty > _MAX_DUTY_WARN:
        msg = f"high_duty_cycle: D = {duty:.4f} > {_MAX_DUTY_WARN}; near rail saturation, verify controller minimum off-time."
        sol_warnings.append(msg)
        warnings.warn(f"buck_design: {msg}", stacklevel=2)

    if not ccm:
        msg = f"dcm_at_ccm_assumption: converter is in DCM (L = {l_h*1e6:.3f} µH < L_crit = {l_crit_h*1e6:.3f} µH); CCM equations invalid."
        sol_warnings.append(msg)
        warnings.warn(f"buck_design: {msg}", stacklevel=2)
    elif (l_h - l_crit_h) / l_crit_h < _DCM_BOUNDARY_MARGIN:
        msg = f"near_ccm_boundary: L = {l_h*1e6:.3f} µH is within {_DCM_BOUNDARY_MARGIN*100:.0f} % of L_crit; may enter DCM at light load."
        sol_warnings.append(msg)
        warnings.warn(f"buck_design: {msg}", stacklevel=2)

    if efficiency < _MIN_EFFICIENCY_WARN:
        msg = f"efficiency_low: η = {efficiency*100:.1f} % < {_MIN_EFFICIENCY_WARN*100:.0f} %; review component losses."
        sol_warnings.append(msg)
        warnings.warn(f"buck_design: {msg}", stacklevel=2)

    return {
        "ok": True,
        "duty": round(duty, 6),
        "l_h": round(l_h, 12),
        "l_crit_h": round(l_crit_h, 12),
        "ccm": ccm,
        "delta_il_a": round(delta_il, 6),
        "i_l_peak_a": round(i_l_peak, 6),
        "i_l_valley_a": round(i_l_valley, 6),
        "i_l_rms_a": round(i_l_rms, 6),
        "i_sw_rms_a": round(i_sw_rms, 6),
        "i_diode_rms_a": round(i_diode_rms, 6),
        "v_sw_stress_v": round(v_sw_stress, 4),
        "v_diode_stress_v": round(v_diode_stress, 4),
        "c_out_min_f": round(c_out_min, 12),
        "delta_v_esr_v": round(delta_v_esr, 6),
        "delta_v_cap_v": round(delta_v_cap, 6),
        "delta_v_total_v": round(delta_v_total, 6),
        "p_sw_cond_w": round(p_sw_cond, 6),
        "p_sw_switch_w": round(p_sw_switch, 6),
        "p_diode_w": round(p_diode, 6),
        "p_dcr_w": round(p_dcr, 6),
        "p_total_loss_w": round(p_total_loss, 6),
        "p_out_w": round(p_out, 4),
        "efficiency": round(efficiency, 6),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. boost_design
# ═══════════════════════════════════════════════════════════════════════════════

def boost_design(
    v_in: float,
    v_out: float,
    i_out: float,
    fsw: float,
    ripple_frac: float = 0.30,
    c_out_f: float = 100e-6,
    esr_ohm: float = 0.020,
    r_ds_on: float = 0.050,
    v_diode: float = 0.5,
    dcr_ohm: float = 0.010,
    t_rise_s: float = 20e-9,
    t_fall_s: float = 20e-9,
) -> dict:
    """
    Steady-state CCM design for a boost (step-up) converter.

    Duty cycle:
        D = 1 − Vin / Vout

    Inductor:
        L = Vin × D / (fsw × ΔIL)

    Critical inductance:
        L_crit = D × (1−D)² × Vout / (2 × Iout × fsw)

    Switch voltage stress: Vds_max = Vout
    Diode voltage stress:  Vd_max  = Vout
    Input current (average) = Iout / (1−D) = Iout × Vout/Vin  (power balance)

    RHP zero (Ridley / Erickson §10.3):
        f_RHP = (1−D)² × Vout / (2π × L × Iout)
    A warning is issued when f_RHP < 20 % of fsw.

    References: Erickson §2.3, §10.3.

    Parameters
    ----------
    v_in        : float — input voltage [V]
    v_out       : float — output voltage [V]  (must be > v_in)
    i_out       : float — output (load) current [A]
    fsw         : float — switching frequency [Hz]
    ripple_frac : float — inductor current ripple fraction of input average current (default 0.30)
    c_out_f     : float — output capacitor [F] (default 100 µF)
    esr_ohm     : float — output cap ESR [Ω] (default 20 mΩ)
    r_ds_on     : float — switch Rds(on) [Ω] (default 50 mΩ)
    v_diode     : float — boost diode forward voltage [V] (default 0.5 V)
    dcr_ohm     : float — inductor DCR [Ω] (default 10 mΩ)
    t_rise_s    : float — switch current rise time [s] (default 20 ns)
    t_fall_s    : float — switch current fall time [s] (default 20 ns)

    Returns
    -------
    dict: ok, duty, l_h, l_crit_h, ccm, f_rhp_hz, delta_il_a, i_in_avg_a,
          i_l_peak_a, i_l_rms_a, i_sw_rms_a, i_diode_rms_a, v_sw_stress_v,
          v_diode_stress_v, c_out_min_f, delta_v_esr_v, delta_v_cap_v,
          delta_v_total_v, p_sw_cond_w, p_sw_switch_w, p_diode_w, p_dcr_w,
          p_total_loss_w, p_out_w, efficiency, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("v_in", v_in), ("v_out", v_out), ("i_out", i_out), ("fsw", fsw),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    if v_out <= v_in:
        return {"ok": False, "reason": f"v_out ({v_out} V) must be > v_in ({v_in} V) for a boost converter"}

    err = _chk_frac(ripple_frac, "ripple_frac")
    if err:
        return {"ok": False, "reason": err}

    for name, val in [
        ("c_out_f", c_out_f), ("esr_ohm", esr_ohm), ("r_ds_on", r_ds_on),
        ("v_diode", v_diode), ("dcr_ohm", dcr_ohm), ("t_rise_s", t_rise_s), ("t_fall_s", t_fall_s),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    # ── Core design ──────────────────────────────────────────────────────────
    duty = 1.0 - v_in / v_out
    d_prime = 1.0 - duty

    # Average input current (power balance, ideal)
    i_in_avg = i_out / d_prime

    delta_il = ripple_frac * i_in_avg
    l_h = v_in * duty / (fsw * delta_il)
    l_crit_h = duty * d_prime ** 2 * v_out / (2.0 * i_out * fsw)
    ccm = l_h >= l_crit_h

    i_l_peak = i_in_avg + delta_il / 2.0
    i_l_rms = _inductor_rms_current(i_in_avg, delta_il)

    # Switch: conducts during D, current ≈ i_in_avg
    i_sw_rms = _switch_rms_current_buck(i_in_avg, delta_il, duty)

    # Diode: conducts during D'
    i_diode_rms = _diode_rms_current(i_in_avg, delta_il, d_prime)

    # Voltage stresses
    v_sw_stress = v_out
    v_diode_stress = v_out

    # Output cap ripple (boost: ΔVout ≈ Iout × D / (C × fsw))
    delta_v_esr = _output_cap_esr_ripple(delta_il, esr_ohm)
    # Boost output cap charge balance: ΔVout_cap = Iout × D / (C × fsw)
    delta_v_cap = i_out * duty / (c_out_f * fsw)
    delta_v_total = delta_v_esr + delta_v_cap

    target_ripple_v = 0.01 * v_out
    c_out_min = i_out * duty / (fsw * target_ripple_v) if target_ripple_v > 0 else 0.0

    # RHP zero frequency
    f_rhp = d_prime ** 2 * v_out / (2.0 * math.pi * l_h * i_out)

    # ── Loss estimate ────────────────────────────────────────────────────────
    p_sw_cond = _conduction_loss_switch(i_sw_rms, r_ds_on)
    p_sw_switch = _switching_loss(v_out, i_in_avg, fsw, t_rise_s, t_fall_s)
    p_diode = _diode_loss(i_out, v_diode)   # diode avg current = Iout
    p_dcr = _inductor_dcr_loss(i_l_rms, dcr_ohm)
    p_total_loss = p_sw_cond + p_sw_switch + p_diode + p_dcr

    p_out = v_out * i_out
    p_in = p_out + p_total_loss
    efficiency = p_out / p_in if p_in > 0 else 0.0

    # ── Warnings ─────────────────────────────────────────────────────────────
    if duty > _MAX_DUTY_WARN:
        msg = f"high_duty_cycle: D = {duty:.4f} > {_MAX_DUTY_WARN}; near rail saturation."
        sol_warnings.append(msg)
        warnings.warn(f"boost_design: {msg}", stacklevel=2)

    if not ccm:
        msg = f"dcm_at_ccm_assumption: converter is in DCM (L = {l_h*1e6:.3f} µH < L_crit = {l_crit_h*1e6:.3f} µH); CCM equations invalid."
        sol_warnings.append(msg)
        warnings.warn(f"boost_design: {msg}", stacklevel=2)

    if f_rhp < _RHP_BANDWIDTH_FRACTION * fsw:
        msg = (
            f"rhp_limited_bandwidth: f_RHP = {f_rhp:.1f} Hz < "
            f"{_RHP_BANDWIDTH_FRACTION*100:.0f} % × fsw = {_RHP_BANDWIDTH_FRACTION * fsw:.1f} Hz; "
            "close-loop bandwidth must be well below f_RHP (typically < f_RHP/5). "
            "Consider lower conversion ratio or higher inductance."
        )
        sol_warnings.append(msg)
        warnings.warn(f"boost_design: {msg}", stacklevel=2)

    if efficiency < _MIN_EFFICIENCY_WARN:
        msg = f"efficiency_low: η = {efficiency*100:.1f} % < {_MIN_EFFICIENCY_WARN*100:.0f} %."
        sol_warnings.append(msg)
        warnings.warn(f"boost_design: {msg}", stacklevel=2)

    return {
        "ok": True,
        "duty": round(duty, 6),
        "l_h": round(l_h, 12),
        "l_crit_h": round(l_crit_h, 12),
        "ccm": ccm,
        "f_rhp_hz": round(f_rhp, 4),
        "delta_il_a": round(delta_il, 6),
        "i_in_avg_a": round(i_in_avg, 6),
        "i_l_peak_a": round(i_l_peak, 6),
        "i_l_rms_a": round(i_l_rms, 6),
        "i_sw_rms_a": round(i_sw_rms, 6),
        "i_diode_rms_a": round(i_diode_rms, 6),
        "v_sw_stress_v": round(v_sw_stress, 4),
        "v_diode_stress_v": round(v_diode_stress, 4),
        "c_out_min_f": round(c_out_min, 12),
        "delta_v_esr_v": round(delta_v_esr, 6),
        "delta_v_cap_v": round(delta_v_cap, 6),
        "delta_v_total_v": round(delta_v_total, 6),
        "p_sw_cond_w": round(p_sw_cond, 6),
        "p_sw_switch_w": round(p_sw_switch, 6),
        "p_diode_w": round(p_diode, 6),
        "p_dcr_w": round(p_dcr, 6),
        "p_total_loss_w": round(p_total_loss, 6),
        "p_out_w": round(p_out, 4),
        "efficiency": round(efficiency, 6),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. buck_boost_design
# ═══════════════════════════════════════════════════════════════════════════════

def buck_boost_design(
    v_in: float,
    v_out_mag: float,
    i_out: float,
    fsw: float,
    ripple_frac: float = 0.30,
    c_out_f: float = 100e-6,
    esr_ohm: float = 0.020,
    r_ds_on: float = 0.050,
    v_diode: float = 0.5,
    dcr_ohm: float = 0.010,
    t_rise_s: float = 20e-9,
    t_fall_s: float = 20e-9,
) -> dict:
    """
    Steady-state CCM design for an inverting buck-boost converter.

    The output is negative (inverted) with magnitude v_out_mag.

    Duty cycle:
        D = Vout_mag / (Vin + Vout_mag)

    Inductor:
        L = Vin × D / (fsw × ΔIL)

    Critical inductance:
        L_crit = D × (1−D)² × (Vin + Vout_mag) / (2 × Iout × fsw)
               = (1−D)² × Vin / (2 × Iout × fsw)  (equivalent form)

    RHP zero:
        f_RHP = (1−D)² × Vout_mag / (2π × L × Iout)

    Switch voltage stress: Vds_max = Vin + Vout_mag
    Diode voltage stress:  Vd_max  = Vin + Vout_mag

    References: Erickson §2.4, §10.3.

    Parameters
    ----------
    v_in        : float — input voltage [V]
    v_out_mag   : float — output voltage magnitude [V] (output is −v_out_mag)
    i_out       : float — output (load) current magnitude [A]
    fsw         : float — switching frequency [Hz]
    ripple_frac : float — inductor current ripple fraction of peak current (default 0.30)
    c_out_f     : float — output capacitor [F] (default 100 µF)
    esr_ohm     : float — output cap ESR [Ω] (default 20 mΩ)
    r_ds_on     : float — switch Rds(on) [Ω] (default 50 mΩ)
    v_diode     : float — catch diode forward voltage [V] (default 0.5 V)
    dcr_ohm     : float — inductor DCR [Ω] (default 10 mΩ)
    t_rise_s    : float — switch current rise time [s] (default 20 ns)
    t_fall_s    : float — switch current fall time [s] (default 20 ns)

    Returns
    -------
    dict: ok, duty, polarity_note, l_h, l_crit_h, ccm, f_rhp_hz,
          delta_il_a, i_l_peak_a, i_l_rms_a, i_sw_rms_a, i_diode_rms_a,
          v_sw_stress_v, v_diode_stress_v, c_out_min_f, delta_v_esr_v,
          delta_v_cap_v, delta_v_total_v, p_sw_cond_w, p_sw_switch_w,
          p_diode_w, p_dcr_w, p_total_loss_w, p_out_w, efficiency, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("v_in", v_in), ("v_out_mag", v_out_mag), ("i_out", i_out), ("fsw", fsw),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    err = _chk_frac(ripple_frac, "ripple_frac")
    if err:
        return {"ok": False, "reason": err}

    for name, val in [
        ("c_out_f", c_out_f), ("esr_ohm", esr_ohm), ("r_ds_on", r_ds_on),
        ("v_diode", v_diode), ("dcr_ohm", dcr_ohm), ("t_rise_s", t_rise_s), ("t_fall_s", t_fall_s),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    # ── Core design ──────────────────────────────────────────────────────────
    v_total = v_in + v_out_mag
    duty = v_out_mag / v_total
    d_prime = 1.0 - duty

    # Average inductor current: I_L_avg = I_out / D'  (power balance)
    i_l_avg = i_out / d_prime

    delta_il = ripple_frac * i_l_avg
    l_h = v_in * duty / (fsw * delta_il)
    l_crit_h = d_prime ** 2 * v_in / (2.0 * i_out * fsw)
    ccm = l_h >= l_crit_h

    i_l_peak = i_l_avg + delta_il / 2.0
    i_l_rms = _inductor_rms_current(i_l_avg, delta_il)

    i_sw_rms = _switch_rms_current_buck(i_l_avg, delta_il, duty)
    i_diode_rms = _diode_rms_current(i_l_avg, delta_il, d_prime)

    v_sw_stress = v_total
    v_diode_stress = v_total

    delta_v_esr = _output_cap_esr_ripple(delta_il, esr_ohm)
    delta_v_cap = i_out * duty / (c_out_f * fsw)
    delta_v_total = delta_v_esr + delta_v_cap

    target_ripple_v = 0.01 * v_out_mag
    c_out_min = i_out * duty / (fsw * target_ripple_v) if target_ripple_v > 0 else 0.0

    f_rhp = d_prime ** 2 * v_out_mag / (2.0 * math.pi * l_h * i_out)

    # ── Loss estimate ────────────────────────────────────────────────────────
    p_sw_cond = _conduction_loss_switch(i_sw_rms, r_ds_on)
    p_sw_switch = _switching_loss(v_total, i_l_avg, fsw, t_rise_s, t_fall_s)
    p_diode = _diode_loss(i_out, v_diode)
    p_dcr = _inductor_dcr_loss(i_l_rms, dcr_ohm)
    p_total_loss = p_sw_cond + p_sw_switch + p_diode + p_dcr

    p_out = v_out_mag * i_out
    p_in = p_out + p_total_loss
    efficiency = p_out / p_in if p_in > 0 else 0.0

    # ── Warnings ─────────────────────────────────────────────────────────────
    sol_warnings.append(
        "polarity_inversion: output voltage is negative (−Vout_mag); "
        "ensure load return is referenced to −Vout rail, not input GND."
    )

    if not ccm:
        msg = f"dcm_at_ccm_assumption: converter is in DCM (L < L_crit); CCM equations invalid."
        sol_warnings.append(msg)
        warnings.warn(f"buck_boost_design: {msg}", stacklevel=2)

    if f_rhp < _RHP_BANDWIDTH_FRACTION * fsw:
        msg = (
            f"rhp_limited_bandwidth: f_RHP = {f_rhp:.1f} Hz < "
            f"{_RHP_BANDWIDTH_FRACTION*100:.0f} % × fsw = {_RHP_BANDWIDTH_FRACTION * fsw:.1f} Hz; "
            "restrict loop bandwidth well below f_RHP."
        )
        sol_warnings.append(msg)
        warnings.warn(f"buck_boost_design: {msg}", stacklevel=2)

    if efficiency < _MIN_EFFICIENCY_WARN:
        msg = f"efficiency_low: η = {efficiency*100:.1f} % < {_MIN_EFFICIENCY_WARN*100:.0f} %."
        sol_warnings.append(msg)
        warnings.warn(f"buck_boost_design: {msg}", stacklevel=2)

    return {
        "ok": True,
        "duty": round(duty, 6),
        "polarity_note": "output is -v_out_mag (inverted)",
        "l_h": round(l_h, 12),
        "l_crit_h": round(l_crit_h, 12),
        "ccm": ccm,
        "f_rhp_hz": round(f_rhp, 4),
        "delta_il_a": round(delta_il, 6),
        "i_l_peak_a": round(i_l_peak, 6),
        "i_l_rms_a": round(i_l_rms, 6),
        "i_sw_rms_a": round(i_sw_rms, 6),
        "i_diode_rms_a": round(i_diode_rms, 6),
        "v_sw_stress_v": round(v_sw_stress, 4),
        "v_diode_stress_v": round(v_diode_stress, 4),
        "c_out_min_f": round(c_out_min, 12),
        "delta_v_esr_v": round(delta_v_esr, 6),
        "delta_v_cap_v": round(delta_v_cap, 6),
        "delta_v_total_v": round(delta_v_total, 6),
        "p_sw_cond_w": round(p_sw_cond, 6),
        "p_sw_switch_w": round(p_sw_switch, 6),
        "p_diode_w": round(p_diode, 6),
        "p_dcr_w": round(p_dcr, 6),
        "p_total_loss_w": round(p_total_loss, 6),
        "p_out_w": round(p_out, 4),
        "efficiency": round(efficiency, 6),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. flyback_design
# ═══════════════════════════════════════════════════════════════════════════════

def flyback_design(
    v_in: float,
    v_out: float,
    i_out: float,
    fsw: float,
    n_turns_ratio: Optional[float] = None,
    ripple_frac: float = 0.40,
    c_out_f: float = 100e-6,
    esr_ohm: float = 0.050,
    r_ds_on: float = 0.200,
    v_diode: float = 0.7,
    dcr_primary_ohm: float = 0.100,
    t_rise_s: float = 50e-9,
    t_fall_s: float = 50e-9,
    snubber_note: bool = True,
) -> dict:
    """
    Steady-state CCM flyback converter design.

    Turns ratio (Np:Ns = n):
        n = Vin × D / (Vout × (1−D))  [CCM; chosen for D = 0.4 if not provided]

    Primary inductance:
        Lp = Vin × D / (fsw × ΔIp)

    Critical inductance:
        Lp_crit = Vin × D × (1−D)² / (2 × Iout × n² × fsw)
                (referred primary inductance at CCM boundary)

    Peak primary current:
        Ip_peak = n × Iout / (1−D) + ΔIp / 2

    Peak secondary current:
        Is_peak = Ip_peak × n  (referred to secondary)
        Actually: Is_peak = Ip_peak / n  (transformer polarity: Is = Ip / n)

    Switch voltage stress:
        Vds_max = Vin + n × Vout  (no snubber clamp)
    Secondary diode stress:
        Vd_max = Vout + Vin/n

    Leakage spike: Vds_max may be significantly higher due to primary leakage
    inductance. A note is always included.

    RCD snubber sizing (note only; detailed design requires leakage inductance):
        V_clamp ≈ 1.3 × Vin  (typical 30 % margin over Vin)
        R_snub = V_clamp² × (1−D) / (P_leak)  [P_leak ~ 1-3 % of Pout]

    References: Pressman §7.4, Unitrode/TI SLUP169.

    Parameters
    ----------
    v_in            : float — input voltage [V]
    v_out           : float — output voltage [V]
    i_out           : float — output (load) current [A]
    fsw             : float — switching frequency [Hz]
    n_turns_ratio   : float or None — primary-to-secondary turns ratio Np/Ns
                      (if None, computed for D ≈ 0.40)
    ripple_frac     : float — primary current ripple fraction of peak (default 0.40)
    c_out_f         : float — output capacitor [F] (default 100 µF)
    esr_ohm         : float — output cap ESR [Ω] (default 50 mΩ)
    r_ds_on         : float — primary switch Rds(on) [Ω] (default 200 mΩ)
    v_diode         : float — secondary diode Vf [V] (default 0.7 V)
    dcr_primary_ohm : float — primary winding DCR [Ω] (default 100 mΩ)
    t_rise_s        : float — switch current rise time [s] (default 50 ns)
    t_fall_s        : float — switch current fall time [s] (default 50 ns)
    snubber_note    : bool  — include RCD snubber note in warnings (default True)

    Returns
    -------
    dict: ok, duty, n_turns_ratio, l_primary_h, l_primary_crit_h, ccm,
          ip_peak_a, ip_rms_a, is_peak_a, v_sw_stress_v, v_sec_diode_stress_v,
          c_out_min_f, delta_v_esr_v, delta_v_cap_v, delta_v_total_v,
          p_sw_cond_w, p_sw_switch_w, p_diode_w, p_dcr_w, p_total_loss_w,
          p_out_w, efficiency, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("v_in", v_in), ("v_out", v_out), ("i_out", i_out), ("fsw", fsw),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    err = _chk_frac(ripple_frac, "ripple_frac")
    if err:
        return {"ok": False, "reason": err}

    for name, val in [
        ("c_out_f", c_out_f), ("esr_ohm", esr_ohm), ("r_ds_on", r_ds_on),
        ("v_diode", v_diode), ("dcr_primary_ohm", dcr_primary_ohm),
        ("t_rise_s", t_rise_s), ("t_fall_s", t_fall_s),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    if n_turns_ratio is not None:
        err = _chk_pos(n_turns_ratio, "n_turns_ratio")
        if err:
            return {"ok": False, "reason": err}

    # ── Core design ──────────────────────────────────────────────────────────
    # Choose duty for n=None: target D = 0.40
    d_target = 0.40
    if n_turns_ratio is None:
        n = v_in * d_target / (v_out * (1.0 - d_target))
        duty = d_target
    else:
        n = n_turns_ratio
        # Solve D from n: n = Vin × D / (Vout × (1−D))
        # n × Vout × (1−D) = Vin × D
        # n × Vout − n × Vout × D = Vin × D
        # n × Vout = D × (Vin + n × Vout)
        # D = n × Vout / (Vin + n × Vout)
        duty = n * v_out / (v_in + n * v_out)

    if duty <= 0 or duty >= 1:
        return {"ok": False, "reason": f"computed duty {duty:.4f} is out of (0,1); check n_turns_ratio or v_in/v_out"}

    d_prime = 1.0 - duty

    # Average primary current = n × Iout × D / (1−D) ... but simpler from power:
    # Ip_avg_during_on = Iout × Vout / (Vin × D × η) ≈ n × Iout / (1−D) for CCM
    ip_avg_on = n * i_out / d_prime  # average during ON time (≈ half of peak for DCM, avg for CCM)

    delta_ip = ripple_frac * ip_avg_on
    l_p = v_in * duty / (fsw * delta_ip)
    l_p_crit = v_in * duty * d_prime ** 2 / (2.0 * i_out * n ** 2 * fsw)
    ccm = l_p >= l_p_crit

    ip_peak = ip_avg_on + delta_ip / 2.0
    ip_rms = math.sqrt(duty) * math.sqrt(ip_avg_on ** 2 + (delta_ip / (2.0 * math.sqrt(3.0))) ** 2)

    # Secondary peak current: Is_peak = n × Ip_avg_on  (current reflects by 1/n)
    # Actually for flyback: secondary current during D' is: is_avg = i_out
    # is_peak = i_out + ΔIs/2 where ΔIs = ΔIp / n
    delta_is = delta_ip / n
    is_peak = i_out + delta_is / 2.0

    # Voltage stresses
    v_sw_stress = v_in + n * v_out   # reflected secondary voltage across primary switch
    v_sec_diode_stress = v_out + v_in / n  # Vin/n reflected to secondary

    # Output cap ripple (flyback secondary ≈ boost-like during D')
    delta_v_esr = _output_cap_esr_ripple(delta_is, esr_ohm)
    delta_v_cap = i_out * duty / (c_out_f * fsw)
    delta_v_total = delta_v_esr + delta_v_cap

    target_ripple_v = 0.01 * v_out
    c_out_min = i_out * duty / (fsw * target_ripple_v) if target_ripple_v > 0 else 0.0

    # ── Loss estimate ────────────────────────────────────────────────────────
    p_sw_cond = _conduction_loss_switch(ip_rms, r_ds_on)
    p_sw_switch = _switching_loss(v_sw_stress, ip_peak, fsw, t_rise_s, t_fall_s)
    p_diode = _diode_loss(i_out, v_diode)
    p_dcr = _inductor_dcr_loss(ip_rms, dcr_primary_ohm)
    p_total_loss = p_sw_cond + p_sw_switch + p_diode + p_dcr

    p_out = v_out * i_out
    p_in = p_out + p_total_loss
    efficiency = p_out / p_in if p_in > 0 else 0.0

    # ── Warnings ─────────────────────────────────────────────────────────────
    if not ccm:
        msg = f"dcm_at_ccm_assumption: flyback in DCM (Lp = {l_p*1e6:.3f} µH < Lp_crit = {l_p_crit*1e6:.3f} µH); CCM equations invalid."
        sol_warnings.append(msg)
        warnings.warn(f"flyback_design: {msg}", stacklevel=2)

    if snubber_note:
        msg = (
            "rcd_snubber_required: primary leakage inductance will cause Vds spike > Vin + n×Vout. "
            "Add RCD snubber: V_clamp ≈ 1.3×Vin, C_snub sized for acceptable ripple, "
            "R_snub = V_clamp² / (2 × P_leak × fsw × C_snub)^0.5. "
            "Measure leakage inductance (typically 1-5 % of Lp) for accurate sizing."
        )
        sol_warnings.append(msg)
        warnings.warn(f"flyback_design: {msg}", stacklevel=2)

    if efficiency < _MIN_EFFICIENCY_WARN:
        msg = f"efficiency_low: η = {efficiency*100:.1f} % < {_MIN_EFFICIENCY_WARN*100:.0f} %."
        sol_warnings.append(msg)
        warnings.warn(f"flyback_design: {msg}", stacklevel=2)

    return {
        "ok": True,
        "duty": round(duty, 6),
        "n_turns_ratio": round(n, 6),
        "l_primary_h": round(l_p, 12),
        "l_primary_crit_h": round(l_p_crit, 12),
        "ccm": ccm,
        "ip_peak_a": round(ip_peak, 6),
        "ip_rms_a": round(ip_rms, 6),
        "is_peak_a": round(is_peak, 6),
        "v_sw_stress_v": round(v_sw_stress, 4),
        "v_sec_diode_stress_v": round(v_sec_diode_stress, 4),
        "c_out_min_f": round(c_out_min, 12),
        "delta_v_esr_v": round(delta_v_esr, 6),
        "delta_v_cap_v": round(delta_v_cap, 6),
        "delta_v_total_v": round(delta_v_total, 6),
        "p_sw_cond_w": round(p_sw_cond, 6),
        "p_sw_switch_w": round(p_sw_switch, 6),
        "p_diode_w": round(p_diode, 6),
        "p_dcr_w": round(p_dcr, 6),
        "p_total_loss_w": round(p_total_loss, 6),
        "p_out_w": round(p_out, 4),
        "efficiency": round(efficiency, 6),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. sepic_design
# ═══════════════════════════════════════════════════════════════════════════════

def sepic_design(
    v_in: float,
    v_out: float,
    i_out: float,
    fsw: float,
    ripple_frac: float = 0.30,
    c_out_f: float = 100e-6,
    c_coupling_f: float = 10e-6,
    esr_ohm: float = 0.030,
    r_ds_on: float = 0.100,
    v_diode: float = 0.5,
    dcr_ohm: float = 0.020,
    t_rise_s: float = 30e-9,
    t_fall_s: float = 30e-9,
) -> dict:
    """
    Steady-state CCM design for a SEPIC (Single-Ended Primary-Inductance Converter).

    The SEPIC can step up or step down and produces a positive (non-inverted) output.

    Duty cycle:
        D = Vout / (Vin + Vout)

    Inductors (equal, coupled or split):
        L1 = L2 = Vin × D / (fsw × ΔIL1)
        ΔIL1 = ripple_frac × Iin_avg

    Input average current:
        Iin_avg = Iout × (1 + Vout/Vin) = Iout / (1−D)  [from power balance]

    Peak switch current:
        I_sw_peak = IL1_peak + IL2_peak = Iin_avg + Iout + ΔIL/2

    Capacitor C1 (series coupling capacitor):
        V_C1 = Vin  [steady-state]
        I_C1_rms ≈ Iout (first-order approximation)

    Switch voltage stress: Vds_max = Vin + Vout
    Diode voltage stress:  Vd_max  = Vin + Vout

    References: Erickson §6.4, Kazimierczuk ch.13.

    Parameters
    ----------
    v_in         : float — input voltage [V]
    v_out        : float — output voltage [V]
    i_out        : float — output (load) current [A]
    fsw          : float — switching frequency [Hz]
    ripple_frac  : float — L1 current ripple fraction of Iin_avg (default 0.30)
    c_out_f      : float — output capacitor [F] (default 100 µF)
    c_coupling_f : float — series coupling capacitor C1 [F] (default 10 µF)
    esr_ohm      : float — output cap ESR [Ω] (default 30 mΩ)
    r_ds_on      : float — switch Rds(on) [Ω] (default 100 mΩ)
    v_diode      : float — output diode Vf [V] (default 0.5 V)
    dcr_ohm      : float — inductor DCR [Ω] (per inductor, default 20 mΩ)
    t_rise_s     : float — switch current rise time [s] (default 30 ns)
    t_fall_s     : float — switch current fall time [s] (default 30 ns)

    Returns
    -------
    dict: ok, duty, l1_h, l2_h, l_crit_h, ccm, delta_il1_a, i_in_avg_a,
          i_sw_peak_a, i_sw_rms_a, i_diode_rms_a, i_l1_rms_a, i_l2_rms_a,
          v_c1_v, v_sw_stress_v, v_diode_stress_v, c_out_min_f,
          c_coupling_min_f, delta_v_esr_v, delta_v_cap_v, delta_v_total_v,
          p_sw_cond_w, p_sw_switch_w, p_diode_w, p_dcr_w, p_total_loss_w,
          p_out_w, efficiency, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("v_in", v_in), ("v_out", v_out), ("i_out", i_out), ("fsw", fsw),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    err = _chk_frac(ripple_frac, "ripple_frac")
    if err:
        return {"ok": False, "reason": err}

    for name, val in [
        ("c_out_f", c_out_f), ("c_coupling_f", c_coupling_f), ("esr_ohm", esr_ohm),
        ("r_ds_on", r_ds_on), ("v_diode", v_diode), ("dcr_ohm", dcr_ohm),
        ("t_rise_s", t_rise_s), ("t_fall_s", t_fall_s),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    # ── Core design ──────────────────────────────────────────────────────────
    duty = v_out / (v_in + v_out)
    d_prime = 1.0 - duty

    i_in_avg = i_out / d_prime  # power balance (ideal)

    delta_il1 = ripple_frac * i_in_avg
    l1_h = v_in * duty / (fsw * delta_il1)
    l2_h = l1_h  # equal inductors

    # Critical inductance for CCM (combined L1||L2 effective)
    l_crit_h = v_in * duty * d_prime ** 2 / (2.0 * i_out * fsw)
    ccm = l1_h >= l_crit_h

    il1_peak = i_in_avg + delta_il1 / 2.0
    # L2 carries iout on average; its ripple mirrors L1 for equal inductors
    il2_peak = i_out + delta_il1 / 2.0

    i_l1_rms = _inductor_rms_current(i_in_avg, delta_il1)
    i_l2_rms = _inductor_rms_current(i_out, delta_il1)

    # Switch peak current = IL1_peak + IL2_peak (both inductors discharge through switch during on-time)
    i_sw_peak = il1_peak + il2_peak
    # Switch RMS: sum of both currents during D
    i_sw_rms_combined = math.sqrt(duty) * math.sqrt(
        (i_in_avg + i_out) ** 2 + (delta_il1 / math.sqrt(3.0)) ** 2
    )

    # Diode conducts during D'; current = I_out
    i_diode_rms = _diode_rms_current(i_out, delta_il1, d_prime)

    v_c1 = v_in  # coupling cap voltage in steady state
    v_sw_stress = v_in + v_out
    v_diode_stress = v_in + v_out

    delta_v_esr = _output_cap_esr_ripple(delta_il1, esr_ohm)
    delta_v_cap = i_out * duty / (c_out_f * fsw)
    delta_v_total = delta_v_esr + delta_v_cap

    target_ripple_v = 0.01 * v_out
    c_out_min = i_out * duty / (fsw * target_ripple_v) if target_ripple_v > 0 else 0.0

    # Minimum coupling capacitor: ΔV_C1 = Iout × D / (C1 × fsw) < 1 % of Vin
    target_vc1_ripple = 0.01 * v_in
    c_coupling_min = i_out * duty / (fsw * target_vc1_ripple) if target_vc1_ripple > 0 else 0.0

    # ── Loss estimate ────────────────────────────────────────────────────────
    p_sw_cond = _conduction_loss_switch(i_sw_rms_combined, r_ds_on)
    p_sw_switch = _switching_loss(v_sw_stress, i_sw_peak, fsw, t_rise_s, t_fall_s)
    p_diode = _diode_loss(i_out, v_diode)
    # Two inductor DCR losses
    p_dcr = _inductor_dcr_loss(i_l1_rms, dcr_ohm) + _inductor_dcr_loss(i_l2_rms, dcr_ohm)
    p_total_loss = p_sw_cond + p_sw_switch + p_diode + p_dcr

    p_out = v_out * i_out
    p_in = p_out + p_total_loss
    efficiency = p_out / p_in if p_in > 0 else 0.0

    # ── Warnings ─────────────────────────────────────────────────────────────
    if not ccm:
        msg = f"dcm_at_ccm_assumption: SEPIC in DCM (L = {l1_h*1e6:.3f} µH < L_crit = {l_crit_h*1e6:.3f} µH); CCM equations invalid."
        sol_warnings.append(msg)
        warnings.warn(f"sepic_design: {msg}", stacklevel=2)

    if efficiency < _MIN_EFFICIENCY_WARN:
        msg = f"efficiency_low: η = {efficiency*100:.1f} % < {_MIN_EFFICIENCY_WARN*100:.0f} %."
        sol_warnings.append(msg)
        warnings.warn(f"sepic_design: {msg}", stacklevel=2)

    sol_warnings.append(
        "coupling_cap_esr: series coupling capacitor C1 ESR contributes to switch peak "
        "current and efficiency; use low-ESR film or ceramic capacitor rated for Vin."
    )

    return {
        "ok": True,
        "duty": round(duty, 6),
        "l1_h": round(l1_h, 12),
        "l2_h": round(l2_h, 12),
        "l_crit_h": round(l_crit_h, 12),
        "ccm": ccm,
        "delta_il1_a": round(delta_il1, 6),
        "i_in_avg_a": round(i_in_avg, 6),
        "i_sw_peak_a": round(i_sw_peak, 6),
        "i_sw_rms_a": round(i_sw_rms_combined, 6),
        "i_diode_rms_a": round(i_diode_rms, 6),
        "i_l1_rms_a": round(i_l1_rms, 6),
        "i_l2_rms_a": round(i_l2_rms, 6),
        "v_c1_v": round(v_c1, 4),
        "v_sw_stress_v": round(v_sw_stress, 4),
        "v_diode_stress_v": round(v_diode_stress, 4),
        "c_out_min_f": round(c_out_min, 12),
        "c_coupling_min_f": round(c_coupling_min, 12),
        "delta_v_esr_v": round(delta_v_esr, 6),
        "delta_v_cap_v": round(delta_v_cap, 6),
        "delta_v_total_v": round(delta_v_total, 6),
        "p_sw_cond_w": round(p_sw_cond, 6),
        "p_sw_switch_w": round(p_sw_switch, 6),
        "p_diode_w": round(p_diode, 6),
        "p_dcr_w": round(p_dcr, 6),
        "p_total_loss_w": round(p_total_loss, 6),
        "p_out_w": round(p_out, 4),
        "efficiency": round(efficiency, 6),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. converter_thermal
# ═══════════════════════════════════════════════════════════════════════════════

def converter_thermal(
    p_loss_w: float,
    rth_ja: float,
    t_ambient_c: float = 25.0,
    t_j_max_c: float = 150.0,
    rth_jc: Optional[float] = None,
    rth_cs: Optional[float] = None,
) -> dict:
    """
    Junction temperature estimate for a switching converter semiconductor.

    If only rth_ja is provided (IC or SOT package):
        Tj = T_ambient + P_loss × Rth_JA

    If rth_jc and rth_cs are provided (discrete MOSFET with heatsink):
        Tj = T_ambient + P_loss × (Rth_JC + Rth_CS + Rth_SA)
        where Rth_SA = rth_ja − rth_jc − rth_cs (i.e. rth_ja is treated as Rth_SA
        when rth_jc/rth_cs are given).

    A warning is issued when Tj > t_j_max_c.

    Parameters
    ----------
    p_loss_w    : float — total semiconductor power dissipation [W]
    rth_ja      : float — junction-to-ambient thermal resistance [°C/W]
                  (or Rth_SA when rth_jc + rth_cs are provided)
    t_ambient_c : float — ambient temperature [°C] (default 25 °C)
    t_j_max_c   : float — maximum junction temperature [°C] (default 150 °C)
    rth_jc      : float or None — junction-to-case thermal resistance [°C/W]
    rth_cs      : float or None — case-to-heatsink thermal resistance [°C/W]

    Returns
    -------
    dict: ok, t_junction_c, delta_t_k, t_margin_k, over_temp, warnings
    """
    sol_warnings: List[str] = []

    err = _chk_pos(p_loss_w, "p_loss_w")
    if err:
        return {"ok": False, "reason": err}

    err = _chk_pos(rth_ja, "rth_ja")
    if err:
        return {"ok": False, "reason": err}

    if not isinstance(t_ambient_c, (int, float)) or math.isnan(t_ambient_c):
        return {"ok": False, "reason": f"t_ambient_c must be a finite number, got {t_ambient_c!r}"}

    if not isinstance(t_j_max_c, (int, float)) or math.isnan(t_j_max_c):
        return {"ok": False, "reason": f"t_j_max_c must be a finite number, got {t_j_max_c!r}"}

    # Compute total Rth
    if rth_jc is not None and rth_cs is not None:
        err = _chk_pos(rth_jc, "rth_jc")
        if err:
            return {"ok": False, "reason": err}
        err = _chk_pos(rth_cs, "rth_cs")
        if err:
            return {"ok": False, "reason": err}
        rth_total = rth_jc + rth_cs + rth_ja  # rth_ja treated as Rth_SA
    else:
        rth_total = rth_ja

    delta_t = p_loss_w * rth_total
    t_junction = t_ambient_c + delta_t
    t_margin = t_j_max_c - t_junction
    over_temp = t_junction > t_j_max_c

    if over_temp:
        msg = (
            f"over_temp: Tj = {t_junction:.1f} °C > Tj_max = {t_j_max_c:.1f} °C "
            f"(margin = {t_margin:.1f} K); reduce power dissipation or improve heatsinking."
        )
        sol_warnings.append(msg)
        warnings.warn(f"converter_thermal: {msg}", stacklevel=2)

    return {
        "ok": True,
        "t_junction_c": round(t_junction, 4),
        "delta_t_k": round(delta_t, 4),
        "t_margin_k": round(t_margin, 4),
        "over_temp": over_temp,
        "rth_total": round(rth_total, 4),
        "warnings": sol_warnings,
    }
