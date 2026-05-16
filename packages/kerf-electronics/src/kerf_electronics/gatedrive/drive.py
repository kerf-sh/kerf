"""
Power-switch gate-driver and switching-loss design — pure Python (math only).

Distinct from:
  kerf_electronics.powerconv  — converter topology (buck/boost/flyback/…)
  kerf_electronics.motordrive — motor & inverter sizing
  kerf_electronics.pdn        — power delivery network
  kerf_electronics.protection — overcurrent / overvoltage protection circuits

Capabilities
------------
gate_drive_power
    Gate charge (Qg), average gate-drive current (Ig_avg = Qg × fsw), and
    driver power dissipation (P_drv = Qg × fsw × Vgs).

gate_resistor_design
    Gate resistor for a target turn-on or turn-off time; peak drive current
    (Vpeak / Rg); optional negative-gate-drive note (Vgs_off < 0).

miller_spurious_turnon
    Miller-plateau voltage check and dv/dt-induced spurious-turn-on margin.
    Returns the critical dv/dt threshold and whether the device is at risk
    given a user-supplied bus dv/dt or estimated dv/dt from Rg_off and Cgd.

switching_loss
    Turn-on (Eon) and turn-off (Eoff) energies from current/voltage overlap
    with Rg-scaled transition times.  Total switching loss Psw = (Eon+Eoff)×fsw.

conduction_loss
    MOSFET Rds(on)×Irms² or IGBT Vce(sat)×I_avg conduction loss.

diode_recovery_loss
    Body diode (or external freewheeling diode) reverse-recovery loss from
    stored charge Qrr: P_rr = Qrr × Vbus × fsw.

total_loss_and_thermal
    Aggregate all loss components (switching + conduction + drive + diode recovery),
    compute junction temperature Tj = T_amb + Ploss × (Rθjc + Rθcs + Rθsa), flag
    over-temperature and required heatsink thermal resistance for a Tj target.

dead_time_select
    Minimum dead time from Coss and gate-drive current; also checks that dead
    time does not exceed body-diode conduction limit, warning on shoot-through risk.

bootstrap_cap_sizing
    High-side bootstrap capacitor value for a target voltage droop over N cycles:
    C_boot = Q_total / ΔV_boot.  Includes bias-current, gate-charge, and leakage.

All functions return plain dicts {ok: bool, ...}.
Warnings (over-temp, shoot-through risk, SOA exceeded) are issued via
warnings.warn; functions never raise to callers.

References
----------
  Mohan, Undeland & Robbins, "Power Electronics" (3rd ed., Wiley, 2003)
  International Rectifier / Infineon application notes (AN-978, AN-6076)
  Texas Instruments SLUA618: Gate Drive Topologies
  ON Semiconductor AND9166: IGBT gate driver design
  Fairchild AN-6076: Design and Application Guide for Bootstrap Driver IC

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import Optional

# ── Warning thresholds ────────────────────────────────────────────────────────
_TJ_MAX_DEFAULT = 150.0     # °C — typical MOSFET/IGBT max junction temperature
_SOA_DERATING = 0.80        # flag if Vds or Vce stress > 80 % of rated breakdown
_EFFICIENCY_WARN = 0.70     # flag total converter efficiency estimate if below 70 %

# ── Input validation helpers ──────────────────────────────────────────────────

def _chk_pos(value, name: str) -> Optional[str]:
    """Return error string if value is not a positive finite number."""
    if not isinstance(value, (int, float)) or math.isnan(value) or value <= 0:
        return f"{name} must be a positive finite number, got {value!r}"
    return None


def _chk_nonneg(value, name: str) -> Optional[str]:
    """Return error string if value is not >= 0 and finite."""
    if not isinstance(value, (int, float)) or math.isnan(value) or value < 0:
        return f"{name} must be >= 0, got {value!r}"
    return None


def _chk_range(value, name: str, lo: float, hi: float) -> Optional[str]:
    """Return error string if value is outside [lo, hi]."""
    if not isinstance(value, (int, float)) or math.isnan(value):
        return f"{name} must be a finite number, got {value!r}"
    if not (lo <= value <= hi):
        return f"{name} must be in [{lo}, {hi}], got {value!r}"
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 1. gate_drive_power
# ══════════════════════════════════════════════════════════════════════════════

def gate_drive_power(
    qg_c: float,
    fsw_hz: float,
    vgs_drive_v: float,
    vgs_off_v: float = 0.0,
) -> dict:
    """
    Compute gate charge parameters and gate-driver power dissipation.

    Model (IR AN-978 / TI SLUA618):
        Ig_avg  = Qg × fsw          [A]
        P_drive = Qg × fsw × Vgs   [W]  (energy stored/dumped per cycle × fsw)

    When vgs_off_v < 0 (negative turn-off bias), the total Vgs swing is
    (vgs_drive_v − vgs_off_v) and power is adjusted accordingly.

    Parameters
    ----------
    qg_c        : float — total gate charge [C] (from datasheet, e.g. 100e-9 C)
    fsw_hz      : float — switching frequency [Hz]
    vgs_drive_v : float — gate drive voltage (turn-on), e.g. 12 V or 15 V
    vgs_off_v   : float — gate turn-off voltage (default 0 V; use negative for neg. bias)

    Returns
    -------
    dict: ok, qg_c, fsw_hz, vgs_drive_v, vgs_off_v,
          ig_avg_a, p_drive_w, vgs_swing_v, note
    """
    err = _chk_pos(qg_c, "qg_c")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(fsw_hz, "fsw_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(vgs_drive_v, "vgs_drive_v")
    if err:
        return {"ok": False, "reason": err}
    if not isinstance(vgs_off_v, (int, float)) or math.isnan(vgs_off_v):
        return {"ok": False, "reason": "vgs_off_v must be a finite number"}

    vgs_swing = vgs_drive_v - vgs_off_v   # always positive when vgs_off <= 0

    if vgs_swing <= 0:
        return {
            "ok": False,
            "reason": (
                f"vgs_drive_v ({vgs_drive_v}) must be greater than vgs_off_v ({vgs_off_v})"
            ),
        }

    ig_avg = qg_c * fsw_hz
    p_drive = qg_c * fsw_hz * vgs_swing

    note = ""
    if vgs_off_v < 0:
        note = (
            f"Negative turn-off bias {vgs_off_v} V applied. "
            "Requires isolated or charge-pump gate supply. "
            "Reduces spurious-turn-on risk significantly."
        )

    return {
        "ok": True,
        "qg_c": qg_c,
        "fsw_hz": fsw_hz,
        "vgs_drive_v": vgs_drive_v,
        "vgs_off_v": vgs_off_v,
        "vgs_swing_v": round(vgs_swing, 4),
        "ig_avg_a": ig_avg,
        "p_drive_w": round(p_drive, 6),
        "formula": "P_drive = Qg × fsw × Vgs_swing  (IR AN-978)",
        "note": note,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. gate_resistor_design
# ══════════════════════════════════════════════════════════════════════════════

def gate_resistor_design(
    vgs_drive_v: float,
    qg_c: float,
    t_transition_s: float,
    vgs_off_v: float = 0.0,
    rg_internal_ohm: float = 0.0,
    vgs_th_v: Optional[float] = None,
) -> dict:
    """
    Select external gate resistor for a target switch transition time.

    Model (simplified charge-based, Mohan §6.4):
        Rg_total = V_drive_swing × t_transition / Qg
        Rg_ext   = Rg_total − Rg_internal
        Ipeak    = V_drive_swing / Rg_total

    Parameters
    ----------
    vgs_drive_v      : float — gate drive voltage [V]
    qg_c             : float — total gate charge [C]
    t_transition_s   : float — target turn-on or turn-off time [s]
    vgs_off_v        : float — turn-off voltage (default 0; use negative for neg. bias)
    rg_internal_ohm  : float — device internal gate resistance [Ω] (default 0)
    vgs_th_v         : float — threshold voltage [V] for notes (optional)

    Returns
    -------
    dict: ok, rg_total_ohm, rg_ext_ohm, ipeak_a, vgs_swing_v,
          t_transition_s, note
    """
    err = _chk_pos(vgs_drive_v, "vgs_drive_v")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(qg_c, "qg_c")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(t_transition_s, "t_transition_s")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_nonneg(rg_internal_ohm, "rg_internal_ohm")
    if err:
        return {"ok": False, "reason": err}
    if not isinstance(vgs_off_v, (int, float)) or math.isnan(vgs_off_v):
        return {"ok": False, "reason": "vgs_off_v must be a finite number"}

    vgs_swing = vgs_drive_v - vgs_off_v
    if vgs_swing <= 0:
        return {
            "ok": False,
            "reason": (
                f"vgs_drive_v ({vgs_drive_v}) must be greater than vgs_off_v ({vgs_off_v})"
            ),
        }

    rg_total = vgs_swing * t_transition_s / qg_c
    rg_ext = max(0.0, rg_total - rg_internal_ohm)
    ipeak = vgs_swing / rg_total if rg_total > 0 else math.inf

    note = ""
    if rg_ext == 0.0 and rg_internal_ohm >= rg_total:
        note = (
            "External gate resistor not required: internal resistance meets "
            "transition-time target. "
        )
    if vgs_off_v < 0:
        note += (
            f"Negative turn-off bias ({vgs_off_v} V) reduces spurious-turn-on risk."
        )
    if vgs_th_v is not None and isinstance(vgs_th_v, (int, float)):
        if vgs_th_v > vgs_drive_v * 0.7:
            warnings.warn(
                f"gate_resistor_design: Vth ({vgs_th_v} V) is >70 % of Vgs_drive "
                f"({vgs_drive_v} V). Insufficient gate margin — choose a lower-Vth device.",
                stacklevel=2,
            )

    return {
        "ok": True,
        "vgs_swing_v": round(vgs_swing, 4),
        "rg_total_ohm": round(rg_total, 4),
        "rg_ext_ohm": round(rg_ext, 4),
        "rg_internal_ohm": rg_internal_ohm,
        "ipeak_a": round(ipeak, 4),
        "t_transition_s": t_transition_s,
        "formula": "Rg = Vgs_swing × t_trans / Qg  (Mohan §6.4)",
        "note": note.strip(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3. miller_spurious_turnon
# ══════════════════════════════════════════════════════════════════════════════

def miller_spurious_turnon(
    cgd_f: float,
    vgs_th_v: float,
    rg_off_ohm: float,
    vbus_v: float,
    t_rise_s: Optional[float] = None,
    vgs_off_v: float = 0.0,
) -> dict:
    """
    Miller-plateau analysis and dv/dt-induced spurious-turn-on margin.

    Model (Infineon AN-6076 / IR AN-978):
        dv/dt_critical = (Vgs_th − Vgs_off) / (Cgd × Rg_off)
        If a bus dv/dt (estimated from t_rise_s: dv/dt_bus = Vbus / t_rise_s)
        exceeds dv/dt_critical, spurious turn-on is likely.

    The Miller plateau voltage is reported as Vgs_miller ≈ Vgs_th (simplified;
    actual plateau depends on transconductance and load current, but Vth is the
    conservative margin point for spurious-turn-on analysis).

    Parameters
    ----------
    cgd_f       : float — gate-drain (Miller) capacitance [F]
    vgs_th_v    : float — gate threshold voltage [V]
    rg_off_ohm  : float — total gate resistance during turn-off [Ω]
    vbus_v      : float — DC bus voltage [V] (for dv/dt estimate if t_rise_s given)
    t_rise_s    : float — complementary switch rising time [s] (optional; used to
                          estimate dv/dt_bus = Vbus / t_rise_s)
    vgs_off_v   : float — turn-off gate voltage (default 0; use negative for neg. bias)

    Returns
    -------
    dict: ok, cgd_f, vgs_th_v, rg_off_ohm, vgs_miller_v,
          dvdt_critical_vps, dvdt_bus_vps (if t_rise_s given),
          spurious_risk (bool), margin_ratio, note
    """
    err = _chk_pos(cgd_f, "cgd_f")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(vgs_th_v, "vgs_th_v")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(rg_off_ohm, "rg_off_ohm")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(vbus_v, "vbus_v")
    if err:
        return {"ok": False, "reason": err}
    if not isinstance(vgs_off_v, (int, float)) or math.isnan(vgs_off_v):
        return {"ok": False, "reason": "vgs_off_v must be a finite number"}
    if t_rise_s is not None:
        err = _chk_pos(t_rise_s, "t_rise_s")
        if err:
            return {"ok": False, "reason": err}

    # Miller plateau occurs near Vgs_th; conservative spurious-turn-on check
    vgs_miller = vgs_th_v

    # Critical dv/dt: displacement current through Cgd must not raise Vgs above Vth
    # i_cgd = Cgd × (dv/dt)_drain; this current flows through Rg_off to Vgs_off
    # Vgs_peak = Vgs_off + i_cgd × Rg_off = Vgs_off + Cgd × dvdt × Rg_off < Vth
    vgs_margin = vgs_th_v - vgs_off_v
    if vgs_margin <= 0:
        return {
            "ok": False,
            "reason": (
                f"vgs_off_v ({vgs_off_v}) must be less than vgs_th_v ({vgs_th_v}) "
                "for spurious-turn-on analysis."
            ),
        }

    dvdt_critical = vgs_margin / (cgd_f * rg_off_ohm)

    dvdt_bus = None
    spurious_risk = False
    margin_ratio = None

    if t_rise_s is not None:
        dvdt_bus = vbus_v / t_rise_s
        spurious_risk = dvdt_bus >= dvdt_critical
        margin_ratio = dvdt_critical / dvdt_bus if dvdt_bus > 0 else math.inf

        if spurious_risk:
            warnings.warn(
                f"miller_spurious_turnon: SHOOT-THROUGH RISK — "
                f"dv/dt_bus = {dvdt_bus:.2e} V/s exceeds dv/dt_critical = "
                f"{dvdt_critical:.2e} V/s. "
                f"Reduce Rg_off, use negative turn-off bias, or slow the complementary switch.",
                stacklevel=2,
            )

    note_parts = []
    if vgs_off_v < 0:
        note_parts.append(
            f"Negative turn-off bias ({vgs_off_v} V) increases spurious-turn-on margin."
        )
    note_parts.append(
        "Vgs_miller is approximated as Vgs_th (conservative). "
        "Actual Miller plateau is load-current dependent."
    )

    return {
        "ok": True,
        "cgd_f": cgd_f,
        "vgs_th_v": vgs_th_v,
        "vgs_miller_v": round(vgs_miller, 4),
        "rg_off_ohm": rg_off_ohm,
        "vgs_off_v": vgs_off_v,
        "vgs_margin_v": round(vgs_margin, 4),
        "dvdt_critical_vps": round(dvdt_critical, 4),
        "dvdt_bus_vps": round(dvdt_bus, 4) if dvdt_bus is not None else None,
        "spurious_risk": spurious_risk,
        "margin_ratio": round(margin_ratio, 4) if margin_ratio is not None else None,
        "formula": "dv/dt_crit = (Vth − Vgs_off) / (Cgd × Rg_off)  (Infineon AN-6076)",
        "note": " ".join(note_parts),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. switching_loss
# ══════════════════════════════════════════════════════════════════════════════

def switching_loss(
    vbus_v: float,
    i_load_a: float,
    t_on_s: float,
    t_off_s: float,
    fsw_hz: float,
    rg_actual_ohm: Optional[float] = None,
    rg_ref_ohm: Optional[float] = None,
) -> dict:
    """
    Switching energy (Eon, Eoff) and total switching loss from current/voltage
    overlap model.

    Model (Mohan §6.5 / Pressman ch.3):
        Eon  = 0.5 × Vbus × Iload × t_on
        Eoff = 0.5 × Vbus × Iload × t_off
        Psw  = (Eon + Eoff) × fsw

    When both rg_actual_ohm and rg_ref_ohm are supplied, transition times are
    scaled linearly with gate resistance (linear gate charge model):
        t_scaled = t_ref × (Rg_actual / Rg_ref)

    This is consistent with the datasheet characterisation at a reference Rg;
    actual switching times depend on device non-linearities, but the linear
    scaling is the standard first-order estimate.

    Parameters
    ----------
    vbus_v        : float — DC bus voltage [V]
    i_load_a      : float — load current at switching instant [A]
    t_on_s        : float — turn-on transition time [s] (at Rg_ref if scaling)
    t_off_s       : float — turn-off transition time [s] (at Rg_ref if scaling)
    fsw_hz        : float — switching frequency [Hz]
    rg_actual_ohm : float — actual gate resistance [Ω] (optional, for scaling)
    rg_ref_ohm    : float — reference gate resistance [Ω] (from datasheet test conditions)

    Returns
    -------
    dict: ok, vbus_v, i_load_a, t_on_s, t_off_s (scaled if Rg given),
          eon_j, eoff_j, esw_total_j, psw_w
    """
    err = _chk_pos(vbus_v, "vbus_v")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(i_load_a, "i_load_a")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(t_on_s, "t_on_s")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(t_off_s, "t_off_s")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(fsw_hz, "fsw_hz")
    if err:
        return {"ok": False, "reason": err}

    scale = 1.0
    rg_scaling_applied = False

    if rg_actual_ohm is not None and rg_ref_ohm is not None:
        err = _chk_pos(rg_actual_ohm, "rg_actual_ohm")
        if err:
            return {"ok": False, "reason": err}
        err = _chk_pos(rg_ref_ohm, "rg_ref_ohm")
        if err:
            return {"ok": False, "reason": err}
        scale = rg_actual_ohm / rg_ref_ohm
        rg_scaling_applied = True

    t_on_eff = t_on_s * scale
    t_off_eff = t_off_s * scale

    eon = 0.5 * vbus_v * i_load_a * t_on_eff
    eoff = 0.5 * vbus_v * i_load_a * t_off_eff
    esw_total = eon + eoff
    psw = esw_total * fsw_hz

    return {
        "ok": True,
        "vbus_v": vbus_v,
        "i_load_a": i_load_a,
        "t_on_s": t_on_eff,
        "t_off_s": t_off_eff,
        "t_on_ref_s": t_on_s,
        "t_off_ref_s": t_off_s,
        "rg_scale": round(scale, 6),
        "rg_scaling_applied": rg_scaling_applied,
        "fsw_hz": fsw_hz,
        "eon_j": eon,
        "eoff_j": eoff,
        "esw_total_j": esw_total,
        "psw_w": round(psw, 6),
        "formula": "Eon = 0.5×Vbus×Iload×ton; Eoff = 0.5×Vbus×Iload×toff  (Mohan §6.5)",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 5. conduction_loss
# ══════════════════════════════════════════════════════════════════════════════

def conduction_loss(
    device_type: str,
    i_rms_a: float,
    rds_on_ohm: Optional[float] = None,
    vce_sat_v: Optional[float] = None,
    i_avg_a: Optional[float] = None,
    duty: float = 1.0,
) -> dict:
    """
    Conduction loss for MOSFET (Rds(on)×Irms²) or IGBT (Vce_sat×I_avg).

    For MOSFET:
        P_cond = Rds(on) × Irms²
    For IGBT:
        P_cond = Vce_sat × I_avg   (if i_avg_a provided)
             or  Vce_sat × i_rms_a × duty  (simplified)

    Parameters
    ----------
    device_type  : str   — 'mosfet' or 'igbt'
    i_rms_a      : float — RMS current through device [A]
    rds_on_ohm   : float — MOSFET on-resistance [Ω] (required for mosfet)
    vce_sat_v    : float — IGBT collector-emitter saturation voltage [V] (required for igbt)
    i_avg_a      : float — average current [A] (optional; IGBT preferred)
    duty         : float — duty cycle [0..1] for simplified IGBT i_avg estimate

    Returns
    -------
    dict: ok, device_type, p_cond_w, formula
    """
    device_type = str(device_type).lower().strip()
    if device_type not in ("mosfet", "igbt"):
        return {"ok": False, "reason": "device_type must be 'mosfet' or 'igbt'"}

    err = _chk_pos(i_rms_a, "i_rms_a")
    if err:
        return {"ok": False, "reason": err}

    err = _chk_range(duty, "duty", 0.0, 1.0)
    if err:
        return {"ok": False, "reason": err}

    if device_type == "mosfet":
        if rds_on_ohm is None:
            return {"ok": False, "reason": "rds_on_ohm is required for device_type='mosfet'"}
        err = _chk_pos(rds_on_ohm, "rds_on_ohm")
        if err:
            return {"ok": False, "reason": err}
        p_cond = rds_on_ohm * i_rms_a ** 2
        formula = "P_cond = Rds(on) × Irms²"
        return {
            "ok": True,
            "device_type": "mosfet",
            "rds_on_ohm": rds_on_ohm,
            "i_rms_a": i_rms_a,
            "p_cond_w": round(p_cond, 6),
            "formula": formula,
        }

    else:  # igbt
        if vce_sat_v is None:
            return {"ok": False, "reason": "vce_sat_v is required for device_type='igbt'"}
        err = _chk_pos(vce_sat_v, "vce_sat_v")
        if err:
            return {"ok": False, "reason": err}

        if i_avg_a is not None:
            err = _chk_pos(i_avg_a, "i_avg_a")
            if err:
                return {"ok": False, "reason": err}
            i_for_loss = i_avg_a
            formula = "P_cond = Vce_sat × I_avg  (IGBT)"
        else:
            # simplified: I_avg ≈ I_rms × duty (rough; use explicit i_avg for accuracy)
            i_for_loss = i_rms_a * duty
            formula = "P_cond ≈ Vce_sat × I_rms × duty  (IGBT, simplified)"

        p_cond = vce_sat_v * i_for_loss
        return {
            "ok": True,
            "device_type": "igbt",
            "vce_sat_v": vce_sat_v,
            "i_rms_a": i_rms_a,
            "i_used_a": round(i_for_loss, 6),
            "p_cond_w": round(p_cond, 6),
            "formula": formula,
        }


# ══════════════════════════════════════════════════════════════════════════════
# 6. diode_recovery_loss
# ══════════════════════════════════════════════════════════════════════════════

def diode_recovery_loss(
    qrr_c: float,
    vbus_v: float,
    fsw_hz: float,
) -> dict:
    """
    Body diode (or freewheeling diode) reverse-recovery switching loss.

    Model (standard Mohan §6.2 / Kazimierczuk):
        P_rr = Qrr × Vbus × fsw

    This is the energy dumped per commutation event times the switching frequency.
    It is a significant loss term for hard-switched converters with slow body diodes
    (Si MOSFETs); SiC/GaN devices have negligible Qrr.

    Parameters
    ----------
    qrr_c   : float — reverse-recovery charge [C] (from datasheet)
    vbus_v  : float — DC bus voltage [V]
    fsw_hz  : float — switching frequency [Hz]

    Returns
    -------
    dict: ok, qrr_c, vbus_v, fsw_hz, p_rr_w, e_rr_j
    """
    err = _chk_pos(qrr_c, "qrr_c")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(vbus_v, "vbus_v")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(fsw_hz, "fsw_hz")
    if err:
        return {"ok": False, "reason": err}

    e_rr = qrr_c * vbus_v
    p_rr = e_rr * fsw_hz

    return {
        "ok": True,
        "qrr_c": qrr_c,
        "vbus_v": vbus_v,
        "fsw_hz": fsw_hz,
        "e_rr_j": e_rr,
        "p_rr_w": round(p_rr, 6),
        "formula": "P_rr = Qrr × Vbus × fsw  (Mohan §6.2)",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 7. total_loss_and_thermal
# ══════════════════════════════════════════════════════════════════════════════

def total_loss_and_thermal(
    p_sw_w: float,
    p_cond_w: float,
    p_drive_w: float = 0.0,
    p_rr_w: float = 0.0,
    t_amb_c: float = 25.0,
    r_th_jc: float = 0.0,
    r_th_cs: float = 0.0,
    r_th_sa: float = 0.0,
    tj_max_c: float = _TJ_MAX_DEFAULT,
    vds_stress_v: Optional[float] = None,
    vds_rated_v: Optional[float] = None,
) -> dict:
    """
    Aggregate switching + conduction + drive + diode-recovery losses, compute
    junction temperature, and determine required heatsink.

    Thermal model (linear resistive stack):
        P_total = p_sw_w + p_cond_w + p_drive_w + p_rr_w
        Tj = T_amb + P_total × (Rθjc + Rθcs + Rθsa)

    Heatsink design (required Rθsa for Tj ≤ Tj_max):
        Rθsa_required = (Tj_max − T_amb) / P_total − Rθjc − Rθcs

    SOA derating: if vds_stress_v and vds_rated_v are supplied, a warning is
    issued if vds_stress_v > SOA_DERATING × vds_rated_v.

    Parameters
    ----------
    p_sw_w          : float — switching loss [W]
    p_cond_w        : float — conduction loss [W]
    p_drive_w       : float — gate driver power [W] (default 0)
    p_rr_w          : float — diode recovery loss [W] (default 0)
    t_amb_c         : float — ambient temperature [°C] (default 25)
    r_th_jc         : float — junction-to-case thermal resistance [°C/W] (default 0)
    r_th_cs         : float — case-to-heatsink resistance [°C/W] (default 0)
    r_th_sa         : float — heatsink-to-ambient resistance [°C/W] (default 0 = no heatsink)
    tj_max_c        : float — maximum junction temperature [°C] (default 150)
    vds_stress_v    : float — actual Vds/Vce voltage stress [V] (optional, for SOA check)
    vds_rated_v     : float — rated breakdown voltage [V] (optional, for SOA check)

    Returns
    -------
    dict: ok, p_total_w, tj_c, t_amb_c, r_th_total, over_temp, t_margin_c,
          r_th_sa_required, tj_max_c, warnings_list
    """
    err = _chk_nonneg(p_sw_w, "p_sw_w")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_nonneg(p_cond_w, "p_cond_w")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_nonneg(p_drive_w, "p_drive_w")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_nonneg(p_rr_w, "p_rr_w")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_nonneg(r_th_jc, "r_th_jc")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_nonneg(r_th_cs, "r_th_cs")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_nonneg(r_th_sa, "r_th_sa")
    if err:
        return {"ok": False, "reason": err}
    if not isinstance(t_amb_c, (int, float)) or math.isnan(t_amb_c):
        return {"ok": False, "reason": "t_amb_c must be a finite number"}
    err = _chk_pos(tj_max_c, "tj_max_c")
    if err:
        return {"ok": False, "reason": err}

    warn_list = []

    p_total = p_sw_w + p_cond_w + p_drive_w + p_rr_w
    r_th_total = r_th_jc + r_th_cs + r_th_sa
    tj = t_amb_c + p_total * r_th_total

    over_temp = tj > tj_max_c
    t_margin = tj_max_c - tj

    if over_temp:
        msg = (
            f"OVER-TEMPERATURE: Tj = {tj:.1f} °C exceeds Tj_max = {tj_max_c:.1f} °C "
            f"(margin = {t_margin:.1f} °C). Increase heatsink or reduce losses."
        )
        warnings.warn(msg, stacklevel=2)
        warn_list.append(msg)

    # Required heatsink
    if p_total > 0:
        rth_sa_required = (tj_max_c - t_amb_c) / p_total - r_th_jc - r_th_cs
    else:
        rth_sa_required = math.inf

    # SOA derating check
    soa_ok = True
    if vds_stress_v is not None and vds_rated_v is not None:
        err = _chk_pos(vds_stress_v, "vds_stress_v")
        if err:
            return {"ok": False, "reason": err}
        err = _chk_pos(vds_rated_v, "vds_rated_v")
        if err:
            return {"ok": False, "reason": err}
        if vds_stress_v > _SOA_DERATING * vds_rated_v:
            soa_ok = False
            msg = (
                f"SOA EXCEEDED: Vds_stress = {vds_stress_v:.1f} V > "
                f"{100*_SOA_DERATING:.0f}% × Vds_rated = {vds_rated_v:.1f} V. "
                "Choose a higher-voltage device or add snubber."
            )
            warnings.warn(msg, stacklevel=2)
            warn_list.append(msg)

    return {
        "ok": True,
        "p_sw_w": p_sw_w,
        "p_cond_w": p_cond_w,
        "p_drive_w": p_drive_w,
        "p_rr_w": p_rr_w,
        "p_total_w": round(p_total, 6),
        "r_th_jc": r_th_jc,
        "r_th_cs": r_th_cs,
        "r_th_sa": r_th_sa,
        "r_th_total": round(r_th_total, 6),
        "t_amb_c": t_amb_c,
        "tj_c": round(tj, 4),
        "tj_max_c": tj_max_c,
        "over_temp": over_temp,
        "t_margin_c": round(t_margin, 4),
        "r_th_sa_required": round(rth_sa_required, 4) if math.isfinite(rth_sa_required) else None,
        "soa_ok": soa_ok,
        "warnings_list": warn_list,
        "formula": (
            "Tj = T_amb + P_total × (Rθjc + Rθcs + Rθsa); "
            "Rθsa_req = (Tj_max - T_amb)/P - Rθjc - Rθcs"
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 8. dead_time_select
# ══════════════════════════════════════════════════════════════════════════════

def dead_time_select(
    coss_f: float,
    vbus_v: float,
    i_drive_a: float,
    t_dead_s: Optional[float] = None,
    t_body_diode_max_s: float = 500e-9,
) -> dict:
    """
    Minimum dead time selection and shoot-through / body-diode risk check.

    Model (TI SLUA618 / Infineon AN-6076):
        t_dead_min = Coss × Vbus / I_drive
            — time for Coss to discharge from Vbus to 0 (or charge, depending on
              topology); this is the minimum dead time to avoid shoot-through.

    If t_dead_s is supplied, it is compared against both t_dead_min (shoot-through
    risk) and t_body_diode_max_s (excessive body-diode conduction increases losses
    and can cause hard-recovery on body diode).

    Parameters
    ----------
    coss_f              : float — output capacitance [F] (Coss from datasheet)
    vbus_v              : float — DC bus voltage [V]
    i_drive_a           : float — available drive current during commutation [A]
    t_dead_s            : float — actual dead time used [s] (optional, for check)
    t_body_diode_max_s  : float — maximum recommended body-diode conduction time [s]
                                  (default 500 ns; longer = higher reverse-recovery loss)

    Returns
    -------
    dict: ok, t_dead_min_s, coss_f, vbus_v, i_drive_a,
          shoot_through_risk (bool, if t_dead_s given),
          excessive_body_diode (bool, if t_dead_s given),
          t_dead_s (actual, if supplied)
    """
    err = _chk_pos(coss_f, "coss_f")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(vbus_v, "vbus_v")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(i_drive_a, "i_drive_a")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(t_body_diode_max_s, "t_body_diode_max_s")
    if err:
        return {"ok": False, "reason": err}
    if t_dead_s is not None:
        err = _chk_pos(t_dead_s, "t_dead_s")
        if err:
            return {"ok": False, "reason": err}

    t_dead_min = coss_f * vbus_v / i_drive_a

    result: dict = {
        "ok": True,
        "coss_f": coss_f,
        "vbus_v": vbus_v,
        "i_drive_a": i_drive_a,
        "t_dead_min_s": t_dead_min,
        "t_body_diode_max_s": t_body_diode_max_s,
        "formula": "t_dead_min = Coss × Vbus / I_drive  (TI SLUA618)",
    }

    if t_dead_s is not None:
        result["t_dead_s"] = t_dead_s
        shoot_through_risk = t_dead_s < t_dead_min
        excessive_body_diode = t_dead_s > t_body_diode_max_s

        result["shoot_through_risk"] = shoot_through_risk
        result["excessive_body_diode"] = excessive_body_diode

        if shoot_through_risk:
            warnings.warn(
                f"dead_time_select: SHOOT-THROUGH RISK — "
                f"t_dead = {t_dead_s*1e9:.1f} ns < t_dead_min = {t_dead_min*1e9:.1f} ns. "
                "Increase dead time or reduce gate drive resistance.",
                stacklevel=2,
            )
        if excessive_body_diode:
            warnings.warn(
                f"dead_time_select: Dead time {t_dead_s*1e9:.1f} ns exceeds "
                f"body-diode limit {t_body_diode_max_s*1e9:.1f} ns. "
                "Reduce dead time to avoid excess body-diode conduction loss.",
                stacklevel=2,
            )

    return result


# ══════════════════════════════════════════════════════════════════════════════
# 9. bootstrap_cap_sizing
# ══════════════════════════════════════════════════════════════════════════════

def bootstrap_cap_sizing(
    qg_c: float,
    i_bias_a: float,
    fsw_hz: float,
    dv_max_v: float,
    n_cycles: int = 1,
    i_leakage_a: float = 0.0,
    q_extra_c: float = 0.0,
) -> dict:
    """
    High-side bootstrap capacitor sizing.

    Model (Fairchild AN-6076 / TI SLUA618):
        Q_total = Qg × n_cycles + I_bias × (n_cycles / fsw) + Q_extra + I_leakage × (n_cycles / fsw)
        C_boot = Q_total / ΔV_boot

    where ΔV_boot is the maximum permissible voltage droop on the bootstrap
    capacitor during n_cycles of high-side on-time without refresh.

    Parameters
    ----------
    qg_c        : float — gate charge per switching event [C]
    i_bias_a    : float — quiescent bias current of the high-side driver IC [A]
    fsw_hz      : float — switching frequency [Hz]
    dv_max_v    : float — maximum allowed bootstrap voltage droop [V]
    n_cycles    : int   — number of consecutive high-side switching cycles before
                          bootstrap recharge (default 1)
    i_leakage_a : float — bootstrap capacitor leakage current [A] (default 0)
    q_extra_c   : float — additional charge budget (e.g. level-shifter) [C] (default 0)

    Returns
    -------
    dict: ok, c_boot_f, q_total_c, dv_max_v, fsw_hz, n_cycles
    """
    err = _chk_pos(qg_c, "qg_c")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(i_bias_a, "i_bias_a")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(fsw_hz, "fsw_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_pos(dv_max_v, "dv_max_v")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_nonneg(i_leakage_a, "i_leakage_a")
    if err:
        return {"ok": False, "reason": err}
    err = _chk_nonneg(q_extra_c, "q_extra_c")
    if err:
        return {"ok": False, "reason": err}
    if not isinstance(n_cycles, int) or n_cycles < 1:
        return {"ok": False, "reason": "n_cycles must be a positive integer"}

    t_period = 1.0 / fsw_hz
    t_total = n_cycles * t_period

    q_gate = qg_c * n_cycles
    q_bias = i_bias_a * t_total
    q_leak = i_leakage_a * t_total
    q_total = q_gate + q_bias + q_leak + q_extra_c

    c_boot = q_total / dv_max_v

    return {
        "ok": True,
        "qg_c": qg_c,
        "i_bias_a": i_bias_a,
        "i_leakage_a": i_leakage_a,
        "q_extra_c": q_extra_c,
        "fsw_hz": fsw_hz,
        "n_cycles": n_cycles,
        "dv_max_v": dv_max_v,
        "q_gate_c": q_gate,
        "q_bias_c": round(q_bias, 12),
        "q_leak_c": round(q_leak, 12),
        "q_total_c": round(q_total, 12),
        "c_boot_f": round(c_boot, 12),
        "formula": "C_boot = (Qg×N + I_bias×T + I_leak×T + Q_extra) / ΔV  (Fairchild AN-6076)",
    }
