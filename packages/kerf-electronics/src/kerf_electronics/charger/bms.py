"""
Battery charger & BMS design calculator.

Distinct from kerf_electronics.battery (pack sizing/runtime),
kerf_electronics.powerconv (DC-DC topology), kerf_electronics.leddriver,
and kerf_electronics.protection (discrete over-current / ESD).

This module operates at the *charger + BMS* level:
  - CC-CV charge profiles per chemistry
  - Charger power, input power, efficiency, and thermal dissipation
  - Passive cell balancing (bleed resistor) and active cell balancing
  - State-of-charge: coulomb counting with OCV-SOC blend
  - State-of-health: capacity fade and resistance growth
  - Protection thresholds with hysteresis (OV/UV/OC/OT/short-circuit)
  - Pack cell-matching tolerance impact on usable capacity
  - MPPT solar-charge operating point and daily energy

Physics summary
---------------
CC-CV charging
  CC phase: charger holds constant current I_cc = cc_fraction * capacity_ah.
    Time = DoD * Q / I_cc.
  CV phase: voltage held at V_max; current decays toward cv_cutoff_fraction * I_cc.
    Time modelled as: t_cv = -tau * ln(cv_cutoff_fraction), where
    tau = Q / I_cc  (same time constant as CC phase).
  Lead-acid temperature compensation: V_max adjusted by
    dV/dT = temp_coeff_mv_c * (T_cell_c - T_ref_c) (typically −3 to −5 mV/°C/cell).

Charger power & thermal
  P_out = V_bat * I_cc  (W, output to battery during CC)
  P_in  = P_out / efficiency
  P_loss = P_in - P_out  (charger heat dissipation)
  Charger junction temperature rise: ΔT = P_loss * Rth_c_a (°C)

Passive balancing (bleed resistor)
  Bleed current: I_bleed = (V_cell_max - V_cell_min) / R_bleed
  Balance time: t_bal = dQ_ah / I_bleed  (h)
  Power dissipated: P_bleed = V_cell_max * I_bleed  (W)

Active balancing (charge transfer)
  Transfer current: I_xfer  (given; e.g. from inductor-based or flying-cap balancer)
  dQ = (V_max - V_min) * C_cell_ah  (Ah mismatch)
  Transfer time: t_xfer = dQ / I_xfer  (h)

Coulomb counting SOC
  SOC_cc = SOC_init - ∫I dt / Q_rated (drift accumulates over time)
  Drift budget: drift_fraction_per_hour * elapsed_hours
  Blend with OCV-SOC lookup: SOC_blend = (1 - alpha) * SOC_cc + alpha * SOC_ocv

State-of-health (SoH)
  Capacity fade:     Q_now = Q_new * (1 - capacity_fade_per_cycle * n_cycles)
  Resistance growth: R_now = R_new * (1 + resistance_growth_per_cycle * n_cycles)
  SoH (%) = 100 * Q_now / Q_new

Protection thresholds with hysteresis
  OV trip:   V >= V_ov_trip   → flag; release when V < V_ov_trip - hysteresis_v
  UV trip:   V <= V_uv_trip   → flag; release when V > V_uv_trip + hysteresis_v
  OC trip:   I >= I_oc_trip   → flag
  OT trip:   T >= T_ot_trip   → flag; release when T < T_ot_trip - hysteresis_t
  Short:     I >= I_sc_trip   → flag (higher threshold than OC)

Cell-matching tolerance
  If cell capacities spread by ±tol fraction, the weakest cell limits pack:
  Q_usable = Q_nominal * (1 - tol)
  Energy loss fraction ≈ tol

MPPT solar-charge
  Power at MPPT: P_mppt = V_mpp * I_mpp
  Operating point derating for temperature: I_mpp reduced by
    isc_temp_coeff * (T_cell_c - 25.0) fraction.
  Daily energy: E_day = P_mppt * irradiance_peak_sun_hours (Wh/day)
  SOC gained per day: ΔSOC = E_day / (V_bat * Q_ah)

All public functions return dict { ok: True/False, ... }.  They NEVER raise.
Warnings (over-temp-charge, imbalance, over-C-rate) are reported in "warnings"
list field.

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings as _warnings_mod
from typing import Any

# ── Chemistry tables ──────────────────────────────────────────────────────────

#: Per-chemistry defaults: (V_min, V_max, cc_fraction, cv_cutoff_fraction,
#:                          temp_coeff_mv_c_per_cell, T_ref_c)
#: temp_coeff_mv_c_per_cell: lead-acid temperature compensation coefficient
#:   (mV/°C/cell); negative means lower voltage at higher temperature.
#:   Set to 0 for Li-ion / LiFePO4 / NiMH (no significant compensation).
_CHEMISTRY = {
    "li-ion": {
        "v_min": 2.5,
        "v_max": 4.2,
        "cc_fraction": 0.5,      # 0.5 C default CC rate
        "cv_cutoff_fraction": 0.05,  # taper to 5% of I_cc
        "temp_coeff_mv_c": 0.0,
        "t_ref_c": 25.0,
        "max_charge_temp_c": 45.0,
        "min_charge_temp_c": 0.0,
    },
    "lifepo4": {
        "v_min": 2.5,
        "v_max": 3.65,
        "cc_fraction": 0.5,
        "cv_cutoff_fraction": 0.05,
        "temp_coeff_mv_c": 0.0,
        "t_ref_c": 25.0,
        "max_charge_temp_c": 45.0,
        "min_charge_temp_c": 0.0,
    },
    "nimh": {
        "v_min": 1.0,
        "v_max": 1.45,
        "cc_fraction": 0.3,      # NiMH charged slower, 0.3C typical
        "cv_cutoff_fraction": 0.1,
        "temp_coeff_mv_c": 0.0,
        "t_ref_c": 25.0,
        "max_charge_temp_c": 40.0,
        "min_charge_temp_c": 0.0,
    },
    "lead-acid": {
        "v_min": 1.75,           # per cell (6-cell = 10.5 V for 12 V battery)
        "v_max": 2.45,           # typical float/absorption voltage per cell
        "cc_fraction": 0.2,      # C/5 standard charge
        "cv_cutoff_fraction": 0.05,
        "temp_coeff_mv_c": -4.0, # −4 mV/°C/cell (Yuasa / SBS standard)
        "t_ref_c": 25.0,
        "max_charge_temp_c": 40.0,
        "min_charge_temp_c": -10.0,
    },
}


# ── Validation helpers ────────────────────────────────────────────────────────

def _require_positive(value: Any, name: str) -> tuple[float | None, str | None]:
    if value is None:
        return None, f"{name} is required"
    if not isinstance(value, (int, float)) or math.isnan(value) or math.isinf(value):
        return None, f"{name} must be a finite number, got {value!r}"
    if value <= 0:
        return None, f"{name} must be positive, got {value}"
    return float(value), None


def _require_nonneg(value: Any, name: str) -> tuple[float | None, str | None]:
    if value is None:
        return None, f"{name} is required"
    if not isinstance(value, (int, float)) or math.isnan(value) or math.isinf(value):
        return None, f"{name} must be a finite number, got {value!r}"
    if value < 0:
        return None, f"{name} must be >= 0, got {value}"
    return float(value), None


def _lookup_chemistry(chemistry: str) -> tuple[dict | None, str | None]:
    key = chemistry.lower().replace("_", "-")
    if key not in _CHEMISTRY:
        valid = ", ".join(_CHEMISTRY)
        return None, f"unknown chemistry '{chemistry}'; valid: {valid}"
    return _CHEMISTRY[key], None


# ── CC-CV charge profile ──────────────────────────────────────────────────────

def cc_cv_charge_profile(
    capacity_ah: float,
    chemistry: str = "li-ion",
    n_cells_series: int = 1,
    dod: float = 0.8,
    cc_fraction: float | None = None,
    cv_cutoff_fraction: float | None = None,
    v_max_override_v: float | None = None,
    t_cell_c: float = 25.0,
) -> dict:
    """
    Compute CC-CV charge profile for a given chemistry and pack configuration.

    Parameters
    ----------
    capacity_ah:
        Cell (or single-cell-equivalent) rated capacity (Ah).
    chemistry:
        One of 'li-ion', 'lifepo4', 'nimh', 'lead-acid'.
    n_cells_series:
        Number of cells in series (default 1; scales V_max to pack voltage).
    dod:
        Depth of discharge at start of charge (0–1).
    cc_fraction:
        CC rate as fraction of capacity (A per Ah). Overrides chemistry default.
    cv_cutoff_fraction:
        CV taper cutoff as fraction of I_cc. Overrides chemistry default.
    v_max_override_v:
        Override the per-cell V_max (V). If given, uses this instead of chemistry table.
    t_cell_c:
        Cell temperature (°C); used for lead-acid temperature compensation.

    Returns
    -------
    dict with keys:
        ok, chemistry, v_max_cell_v, v_max_pack_v, v_max_adjusted_v (lead-acid),
        i_cc_a, t_cc_h, t_cv_h, total_time_h, total_time_min,
        charge_accepted_ah, warnings
    """
    warn: list[str] = []

    chem, err = _lookup_chemistry(chemistry)
    if err:
        return {"ok": False, "reason": err}

    q, err = _require_positive(capacity_ah, "capacity_ah")
    if err:
        return {"ok": False, "reason": err}

    if not isinstance(n_cells_series, int) or n_cells_series < 1:
        return {"ok": False, "reason": "n_cells_series must be a positive integer"}

    dod_v, err = _require_positive(dod, "dod")
    if err:
        return {"ok": False, "reason": err}
    if dod_v > 1.0:
        return {"ok": False, "reason": "dod must be <= 1.0"}

    cc_frac = float(cc_fraction) if cc_fraction is not None else chem["cc_fraction"]
    if cc_frac <= 0:
        return {"ok": False, "reason": "cc_fraction must be positive"}

    cv_cut = float(cv_cutoff_fraction) if cv_cutoff_fraction is not None else chem["cv_cutoff_fraction"]
    if not (0 < cv_cut < 1):
        return {"ok": False, "reason": "cv_cutoff_fraction must be between 0 and 1 exclusive"}

    v_max_cell = float(v_max_override_v) if v_max_override_v is not None else chem["v_max"]

    # Lead-acid temperature compensation
    v_max_adjusted = v_max_cell
    if chem["temp_coeff_mv_c"] != 0.0:
        delta_t = t_cell_c - chem["t_ref_c"]
        v_max_adjusted = v_max_cell + chem["temp_coeff_mv_c"] * 1e-3 * delta_t
        if abs(v_max_adjusted - v_max_cell) > 0.001:
            direction = "reduced" if v_max_adjusted < v_max_cell else "raised"
            warn.append(
                f"Lead-acid V_max {direction} by "
                f"{abs(v_max_adjusted - v_max_cell)*1000:.1f} mV/cell "
                f"for T={t_cell_c:.1f}°C (ref {chem['t_ref_c']:.0f}°C)"
            )

    # Temperature warnings
    if t_cell_c > chem["max_charge_temp_c"]:
        warn.append(
            f"over-temp-charge: cell temperature {t_cell_c:.1f}°C exceeds "
            f"max charge temperature {chem['max_charge_temp_c']:.0f}°C for {chemistry}"
        )
        _warnings_mod.warn(warn[-1], stacklevel=2)
    if t_cell_c < chem["min_charge_temp_c"]:
        warn.append(
            f"under-temp-charge: cell temperature {t_cell_c:.1f}°C below "
            f"min charge temperature {chem['min_charge_temp_c']:.0f}°C for {chemistry}"
        )
        _warnings_mod.warn(warn[-1], stacklevel=2)

    # C-rate check
    if cc_frac > 2.0:
        warn.append(f"over-C-rate: cc_fraction {cc_frac}C is very high; may damage cells")
        _warnings_mod.warn(warn[-1], stacklevel=2)

    i_cc = cc_frac * q  # CC current (A)
    q_to_restore = dod_v * q  # Ah to restore

    # CC phase time
    t_cc = q_to_restore / i_cc  # hours

    # CV phase: current decays from I_cc to cv_cut * I_cc
    # Model: I(t) = I_cc * exp(-t / tau), tau = Q / I_cc
    # Solve for t when I = cv_cut * I_cc: t_cv = -tau * ln(cv_cut)
    tau = q / i_cc  # time constant (h)
    t_cv = -tau * math.log(cv_cut)

    total_h = t_cc + t_cv
    charge_accepted = dod_v * q  # Ah (charge returned in CC + CV)

    v_max_pack = v_max_adjusted * n_cells_series

    return {
        "ok": True,
        "chemistry": chemistry.lower(),
        "v_max_cell_v": round(v_max_cell, 4),
        "v_max_adjusted_v": round(v_max_adjusted, 4),
        "v_max_pack_v": round(v_max_pack, 4),
        "i_cc_a": round(i_cc, 4),
        "cc_fraction": round(cc_frac, 4),
        "cv_cutoff_fraction": round(cv_cut, 5),
        "t_cc_h": round(t_cc, 4),
        "t_cv_h": round(t_cv, 4),
        "total_time_h": round(total_h, 4),
        "total_time_min": round(total_h * 60.0, 2),
        "charge_accepted_ah": round(charge_accepted, 6),
        "dod": dod_v,
        "t_cell_c": t_cell_c,
        "warnings": warn,
    }


# ── Charger power & thermal ───────────────────────────────────────────────────

def charger_power(
    v_bat_v: float,
    i_charge_a: float,
    efficiency: float = 0.90,
    rth_c_a_k_per_w: float | None = None,
    t_ambient_c: float = 25.0,
) -> dict:
    """
    Compute charger output power, input power, losses, and junction temperature.

    Parameters
    ----------
    v_bat_v:
        Battery terminal voltage during charging (V).
    i_charge_a:
        Charge current (A).
    efficiency:
        Charger conversion efficiency (0–1, default 0.90).
    rth_c_a_k_per_w:
        Charger thermal resistance case-to-ambient (K/W). Optional; when given,
        junction temperature rise is computed.
    t_ambient_c:
        Ambient temperature (°C; default 25.0).

    Returns
    -------
    dict with keys:
        ok, p_out_w, p_in_w, p_loss_w, efficiency,
        t_junction_c (if rth given), warnings
    """
    warn: list[str] = []

    v, err = _require_positive(v_bat_v, "v_bat_v")
    if err:
        return {"ok": False, "reason": err}
    i, err = _require_positive(i_charge_a, "i_charge_a")
    if err:
        return {"ok": False, "reason": err}
    eff, err = _require_positive(efficiency, "efficiency")
    if err:
        return {"ok": False, "reason": err}
    if eff > 1.0:
        return {"ok": False, "reason": "efficiency must be <= 1.0"}

    p_out = v * i
    p_in = p_out / eff
    p_loss = p_in - p_out

    t_junc = None
    if rth_c_a_k_per_w is not None:
        rth, err = _require_positive(rth_c_a_k_per_w, "rth_c_a_k_per_w")
        if err:
            return {"ok": False, "reason": err}
        t_junc = t_ambient_c + p_loss * rth
        if t_junc > 125.0:
            warn.append(
                f"Charger junction temperature {t_junc:.1f}°C exceeds 125°C; "
                "heatsink or derating required"
            )
            _warnings_mod.warn(warn[-1], stacklevel=2)

    result: dict = {
        "ok": True,
        "p_out_w": round(p_out, 4),
        "p_in_w": round(p_in, 4),
        "p_loss_w": round(p_loss, 4),
        "efficiency": round(eff, 4),
        "warnings": warn,
    }
    if t_junc is not None:
        result["t_junction_c"] = round(t_junc, 2)
    return result


# ── Passive cell balancing ────────────────────────────────────────────────────

def passive_balance(
    v_high_v: float,
    v_low_v: float,
    cell_capacity_ah: float,
    r_bleed_ohm: float,
) -> dict:
    """
    Passive balancing: bleed resistor dissipates excess charge from high cell.

    Parameters
    ----------
    v_high_v:
        Voltage of the highest cell (V).
    v_low_v:
        Voltage of the lowest cell (V).
    cell_capacity_ah:
        Cell capacity (Ah) — used to estimate balance time from dV imbalance.
    r_bleed_ohm:
        Bleed resistor value (Ω).

    Returns
    -------
    dict with keys:
        ok, delta_v_v, i_bleed_a, p_bleed_w, balance_time_h,
        balance_time_min, r_bleed_ohm, warnings
    """
    warn: list[str] = []

    v_hi, err = _require_positive(v_high_v, "v_high_v")
    if err:
        return {"ok": False, "reason": err}
    v_lo, err = _require_nonneg(v_low_v, "v_low_v")
    if err:
        return {"ok": False, "reason": err}
    q, err = _require_positive(cell_capacity_ah, "cell_capacity_ah")
    if err:
        return {"ok": False, "reason": err}
    r, err = _require_positive(r_bleed_ohm, "r_bleed_ohm")
    if err:
        return {"ok": False, "reason": err}

    dv = v_hi - v_lo
    if dv < 0:
        return {"ok": False, "reason": "v_high_v must be >= v_low_v"}

    if dv > 0.1:
        warn.append(
            f"imbalance: cell voltage spread {dv*1000:.1f} mV exceeds 100 mV; "
            "pack may be degraded"
        )
        _warnings_mod.warn(warn[-1], stacklevel=2)

    if dv == 0.0:
        return {
            "ok": True,
            "delta_v_v": 0.0,
            "i_bleed_a": 0.0,
            "p_bleed_w": 0.0,
            "balance_time_h": 0.0,
            "balance_time_min": 0.0,
            "r_bleed_ohm": r,
            "warnings": warn,
        }

    i_bleed = v_hi / r  # bleed current through resistor
    p_bleed = v_hi * i_bleed  # power dissipated

    # Charge imbalance: approximate dQ from dV using a linear cell model
    # dQ ≈ dV * C_cell where C_cell = Q / V_range (simplified)
    # More physically, we use a constant-current approach:
    # time to bleed dV * C_cell charge: t_bal = dQ / I_bleed
    # We model dQ = dV * (cell_capacity_ah / v_hi) as a rough OCV slope estimate
    dq_ah = dv * (q / v_hi)
    t_bal_h = dq_ah / i_bleed  # hours

    return {
        "ok": True,
        "delta_v_v": round(dv, 6),
        "i_bleed_a": round(i_bleed, 6),
        "p_bleed_w": round(p_bleed, 6),
        "balance_time_h": round(t_bal_h, 4),
        "balance_time_min": round(t_bal_h * 60.0, 2),
        "r_bleed_ohm": r,
        "warnings": warn,
    }


# ── Active cell balancing ─────────────────────────────────────────────────────

def active_balance(
    v_high_v: float,
    v_low_v: float,
    cell_capacity_ah: float,
    transfer_current_a: float,
    efficiency: float = 0.90,
) -> dict:
    """
    Active balancing: energy transferred from high cell to low cell.

    Parameters
    ----------
    v_high_v:
        Voltage of highest cell (V).
    v_low_v:
        Voltage of lowest cell (V).
    cell_capacity_ah:
        Cell capacity (Ah).
    transfer_current_a:
        Active balancer transfer current (A).
    efficiency:
        Balancer efficiency (0–1, default 0.90).

    Returns
    -------
    dict with keys:
        ok, delta_v_v, dq_ah, transfer_time_h, transfer_time_min,
        energy_loss_wh, efficiency, warnings
    """
    warn: list[str] = []

    v_hi, err = _require_positive(v_high_v, "v_high_v")
    if err:
        return {"ok": False, "reason": err}
    v_lo, err = _require_nonneg(v_low_v, "v_low_v")
    if err:
        return {"ok": False, "reason": err}
    q, err = _require_positive(cell_capacity_ah, "cell_capacity_ah")
    if err:
        return {"ok": False, "reason": err}
    i_xfer, err = _require_positive(transfer_current_a, "transfer_current_a")
    if err:
        return {"ok": False, "reason": err}
    eff, err = _require_positive(efficiency, "efficiency")
    if err:
        return {"ok": False, "reason": err}
    if eff > 1.0:
        return {"ok": False, "reason": "efficiency must be <= 1.0"}

    dv = v_hi - v_lo
    if dv < 0:
        return {"ok": False, "reason": "v_high_v must be >= v_low_v"}

    if dv > 0.1:
        warn.append(
            f"imbalance: cell voltage spread {dv*1000:.1f} mV exceeds 100 mV"
        )
        _warnings_mod.warn(warn[-1], stacklevel=2)

    if dv == 0.0:
        return {
            "ok": True,
            "delta_v_v": 0.0,
            "dq_ah": 0.0,
            "transfer_time_h": 0.0,
            "transfer_time_min": 0.0,
            "energy_loss_wh": 0.0,
            "efficiency": eff,
            "warnings": warn,
        }

    # Charge mismatch
    dq_ah = dv * (q / v_hi)
    t_xfer_h = dq_ah / i_xfer

    # Energy transferred from high cell; fraction (1 - eff) is lost as heat
    e_transferred = v_hi * dq_ah  # Wh ideal
    e_loss = e_transferred * (1.0 - eff)

    return {
        "ok": True,
        "delta_v_v": round(dv, 6),
        "dq_ah": round(dq_ah, 6),
        "transfer_time_h": round(t_xfer_h, 4),
        "transfer_time_min": round(t_xfer_h * 60.0, 2),
        "energy_loss_wh": round(e_loss, 6),
        "efficiency": round(eff, 4),
        "warnings": warn,
    }


# ── Coulomb-counting SOC with OCV blend ──────────────────────────────────────

def coulomb_soc(
    soc_init: float,
    charge_ah: float,
    capacity_ah: float,
    elapsed_h: float,
    drift_fraction_per_hour: float = 0.001,
    ocv_soc: float | None = None,
    alpha_ocv: float = 0.1,
) -> dict:
    """
    Estimate state-of-charge using coulomb counting with OCV-SOC blend.

    Parameters
    ----------
    soc_init:
        Initial SOC (0–1).
    charge_ah:
        Charge added (+) or removed (−) since last reset (Ah).
    capacity_ah:
        Cell/pack rated capacity (Ah).
    elapsed_h:
        Time elapsed since last SOC reset (h); used for drift budget.
    drift_fraction_per_hour:
        Coulomb-counting drift rate (fraction of full scale per hour; default 0.001 = 0.1%/h).
    ocv_soc:
        Open-circuit-voltage SOC estimate (0–1). Optional; when given, blends with CC.
    alpha_ocv:
        Blending weight for OCV-SOC (0–1; default 0.1 = 10% OCV). Only used when ocv_soc given.

    Returns
    -------
    dict with keys:
        ok, soc_cc, drift_budget, soc_blend, soc_final, warnings
    """
    warn: list[str] = []

    si, err = _require_nonneg(soc_init, "soc_init")
    if err:
        return {"ok": False, "reason": err}
    if si > 1.0:
        return {"ok": False, "reason": "soc_init must be <= 1.0"}

    q, err = _require_positive(capacity_ah, "capacity_ah")
    if err:
        return {"ok": False, "reason": err}

    elapsed, err = _require_nonneg(elapsed_h, "elapsed_h")
    if err:
        return {"ok": False, "reason": err}

    drift_r, err = _require_nonneg(drift_fraction_per_hour, "drift_fraction_per_hour")
    if err:
        return {"ok": False, "reason": err}

    charge = float(charge_ah) if charge_ah is not None else 0.0

    # Coulomb-counting SOC
    soc_cc = si + charge / q
    soc_cc = max(0.0, min(1.0, soc_cc))

    # Drift budget
    drift = drift_r * elapsed
    drift = min(drift, 1.0)

    # OCV blend
    soc_blend = soc_cc
    if ocv_soc is not None:
        al, err = _require_nonneg(alpha_ocv, "alpha_ocv")
        if err:
            return {"ok": False, "reason": err}
        if al > 1.0:
            return {"ok": False, "reason": "alpha_ocv must be <= 1.0"}
        ocv = float(ocv_soc)
        if not 0.0 <= ocv <= 1.0:
            return {"ok": False, "reason": "ocv_soc must be between 0 and 1"}
        soc_blend = (1.0 - al) * soc_cc + al * ocv

    soc_final = max(0.0, min(1.0, soc_blend))

    if drift > 0.05:
        warn.append(
            f"coulomb-counting drift budget {drift*100:.1f}% after {elapsed:.1f}h; "
            "consider OCV recalibration"
        )

    return {
        "ok": True,
        "soc_cc": round(soc_cc, 6),
        "drift_budget": round(drift, 6),
        "soc_blend": round(soc_blend, 6),
        "soc_final": round(soc_final, 6),
        "warnings": warn,
    }


# ── State-of-health ───────────────────────────────────────────────────────────

def state_of_health(
    q_new_ah: float,
    r_new_ohm: float,
    n_cycles: int,
    capacity_fade_per_cycle: float = 0.00005,
    resistance_growth_per_cycle: float = 0.0001,
) -> dict:
    """
    Estimate state-of-health from cycle count, capacity fade, and resistance growth.

    Parameters
    ----------
    q_new_ah:
        Fresh cell capacity (Ah).
    r_new_ohm:
        Fresh cell internal resistance (Ω).
    n_cycles:
        Number of full charge/discharge cycles completed.
    capacity_fade_per_cycle:
        Fractional capacity loss per cycle (default 5e-5, ~80% at 4000 cycles).
    resistance_growth_per_cycle:
        Fractional resistance increase per cycle (default 1e-4, 2× at 10000 cycles).

    Returns
    -------
    dict with keys:
        ok, q_now_ah, r_now_ohm, soh_pct, cycles_to_80pct, warnings
    """
    warn: list[str] = []

    q0, err = _require_positive(q_new_ah, "q_new_ah")
    if err:
        return {"ok": False, "reason": err}
    r0, err = _require_positive(r_new_ohm, "r_new_ohm")
    if err:
        return {"ok": False, "reason": err}

    if not isinstance(n_cycles, int) or n_cycles < 0:
        return {"ok": False, "reason": "n_cycles must be a non-negative integer"}

    cf, err = _require_nonneg(capacity_fade_per_cycle, "capacity_fade_per_cycle")
    if err:
        return {"ok": False, "reason": err}
    rg, err = _require_nonneg(resistance_growth_per_cycle, "resistance_growth_per_cycle")
    if err:
        return {"ok": False, "reason": err}

    fade = 1.0 - cf * n_cycles
    fade = max(0.0, fade)
    q_now = q0 * fade
    r_now = r0 * (1.0 + rg * n_cycles)

    soh_pct = 100.0 * q_now / q0

    if soh_pct < 80.0:
        warn.append(
            f"SoH {soh_pct:.1f}% is below 80% EOL threshold at {n_cycles} cycles"
        )

    # Cycles to 80% SoH
    if cf > 0:
        cycles_to_80 = int(0.20 / cf)
    else:
        cycles_to_80 = None  # no fade: infinite

    return {
        "ok": True,
        "q_now_ah": round(q_now, 6),
        "r_now_ohm": round(r_now, 6),
        "soh_pct": round(soh_pct, 3),
        "cycles_to_80pct": cycles_to_80,
        "warnings": warn,
    }


# ── Protection thresholds ─────────────────────────────────────────────────────

def protection_thresholds(
    v_ov_trip_v: float,
    v_uv_trip_v: float,
    i_oc_trip_a: float,
    t_ot_trip_c: float,
    i_sc_trip_a: float,
    hysteresis_v: float = 0.05,
    hysteresis_t_c: float = 5.0,
    v_cell_v: float | None = None,
    i_cell_a: float | None = None,
    t_cell_c: float | None = None,
) -> dict:
    """
    Evaluate BMS protection thresholds with hysteresis.

    Parameters
    ----------
    v_ov_trip_v:
        Over-voltage trip threshold (V/cell).
    v_uv_trip_v:
        Under-voltage trip threshold (V/cell).
    i_oc_trip_a:
        Over-current trip threshold (A).
    t_ot_trip_c:
        Over-temperature trip threshold (°C).
    i_sc_trip_a:
        Short-circuit trip threshold (A); must be > i_oc_trip_a.
    hysteresis_v:
        Voltage hysteresis (V; default 0.05 V). OV releases when V < V_ov_trip − hysteresis_v.
    hysteresis_t_c:
        Temperature hysteresis (°C; default 5 °C).
    v_cell_v:
        Present cell voltage (V). Optional; when given, OV/UV flags are evaluated.
    i_cell_a:
        Present cell current (A). Optional; when given, OC/SC flags are evaluated.
    t_cell_c:
        Present cell temperature (°C). Optional; when given, OT flag is evaluated.

    Returns
    -------
    dict with keys:
        ok, ov_trip_v, ov_release_v, uv_trip_v, uv_release_v,
        oc_trip_a, sc_trip_a, ot_trip_c, ot_release_c,
        flags (dict: ov, uv, oc, ot, short_circuit — present when inputs given),
        warnings
    """
    warn: list[str] = []

    ov, err = _require_positive(v_ov_trip_v, "v_ov_trip_v")
    if err:
        return {"ok": False, "reason": err}
    uv, err = _require_nonneg(v_uv_trip_v, "v_uv_trip_v")
    if err:
        return {"ok": False, "reason": err}
    if uv >= ov:
        return {"ok": False, "reason": "v_uv_trip_v must be < v_ov_trip_v"}

    i_oc, err = _require_positive(i_oc_trip_a, "i_oc_trip_a")
    if err:
        return {"ok": False, "reason": err}
    i_sc, err = _require_positive(i_sc_trip_a, "i_sc_trip_a")
    if err:
        return {"ok": False, "reason": err}
    if i_sc <= i_oc:
        return {"ok": False, "reason": "i_sc_trip_a must be > i_oc_trip_a"}

    t_ot, err = _require_positive(t_ot_trip_c, "t_ot_trip_c")
    if err:
        return {"ok": False, "reason": err}

    hv, err = _require_nonneg(hysteresis_v, "hysteresis_v")
    if err:
        return {"ok": False, "reason": err}
    ht, err = _require_nonneg(hysteresis_t_c, "hysteresis_t_c")
    if err:
        return {"ok": False, "reason": err}

    ov_release = ov - hv
    uv_release = uv + hv
    ot_release = t_ot - ht

    flags: dict = {}
    if v_cell_v is not None:
        v_c = float(v_cell_v)
        flags["ov"] = v_c >= ov
        flags["uv"] = v_c <= uv
        if flags["ov"]:
            warn.append(f"OV: cell voltage {v_c:.3f}V >= trip {ov:.3f}V")
            _warnings_mod.warn(warn[-1], stacklevel=2)
        if flags["uv"]:
            warn.append(f"UV: cell voltage {v_c:.3f}V <= trip {uv:.3f}V")
            _warnings_mod.warn(warn[-1], stacklevel=2)

    if i_cell_a is not None:
        i_c = abs(float(i_cell_a))
        flags["oc"] = i_c >= i_oc
        flags["short_circuit"] = i_c >= i_sc
        if flags["short_circuit"]:
            warn.append(f"SHORT-CIRCUIT: current {i_c:.1f}A >= trip {i_sc:.1f}A")
            _warnings_mod.warn(warn[-1], stacklevel=2)
        elif flags["oc"]:
            warn.append(f"OC: current {i_c:.1f}A >= trip {i_oc:.1f}A")
            _warnings_mod.warn(warn[-1], stacklevel=2)

    if t_cell_c is not None:
        t_c = float(t_cell_c)
        flags["ot"] = t_c >= t_ot
        if flags["ot"]:
            warn.append(f"OT: cell temperature {t_c:.1f}°C >= trip {t_ot:.1f}°C")
            _warnings_mod.warn(warn[-1], stacklevel=2)

    result: dict = {
        "ok": True,
        "ov_trip_v": round(ov, 4),
        "ov_release_v": round(ov_release, 4),
        "uv_trip_v": round(uv, 4),
        "uv_release_v": round(uv_release, 4),
        "oc_trip_a": round(i_oc, 4),
        "sc_trip_a": round(i_sc, 4),
        "ot_trip_c": round(t_ot, 2),
        "ot_release_c": round(ot_release, 2),
        "hysteresis_v": hv,
        "hysteresis_t_c": ht,
        "warnings": warn,
    }
    if flags:
        result["flags"] = flags
    return result


# ── Cell-matching tolerance ───────────────────────────────────────────────────

def cell_matching_usable_capacity(
    q_nominal_ah: float,
    tolerance_fraction: float,
    n_series: int = 1,
    n_parallel: int = 1,
) -> dict:
    """
    Estimate usable pack capacity accounting for cell-to-cell capacity spread.

    The weakest cell in a series string limits the string's usable capacity.
    Modelled as: Q_usable = Q_nominal * (1 - tolerance_fraction).

    Parameters
    ----------
    q_nominal_ah:
        Nominal cell capacity (Ah).
    tolerance_fraction:
        Cell capacity spread (±fraction; e.g. 0.02 = ±2%).
    n_series, n_parallel:
        Pack topology; affects total pack capacity output.

    Returns
    -------
    dict with keys:
        ok, q_cell_usable_ah, q_pack_usable_ah, energy_loss_fraction,
        usable_fraction, warnings
    """
    warn: list[str] = []

    q0, err = _require_positive(q_nominal_ah, "q_nominal_ah")
    if err:
        return {"ok": False, "reason": err}
    tol, err = _require_nonneg(tolerance_fraction, "tolerance_fraction")
    if err:
        return {"ok": False, "reason": err}
    if tol >= 1.0:
        return {"ok": False, "reason": "tolerance_fraction must be < 1.0"}

    if not isinstance(n_series, int) or n_series < 1:
        return {"ok": False, "reason": "n_series must be a positive integer"}
    if not isinstance(n_parallel, int) or n_parallel < 1:
        return {"ok": False, "reason": "n_parallel must be a positive integer"}

    q_usable_cell = q0 * (1.0 - tol)
    q_usable_pack = q_usable_cell * n_parallel  # series doesn't multiply Ah
    energy_loss_frac = tol

    if tol > 0.05:
        warn.append(
            f"imbalance: cell tolerance {tol*100:.1f}% > 5%; "
            f"usable capacity reduced by {energy_loss_frac*100:.1f}%"
        )
        _warnings_mod.warn(warn[-1], stacklevel=2)

    return {
        "ok": True,
        "q_cell_usable_ah": round(q_usable_cell, 6),
        "q_pack_usable_ah": round(q_usable_pack, 6),
        "energy_loss_fraction": round(energy_loss_frac, 6),
        "usable_fraction": round(1.0 - tol, 6),
        "n_series": n_series,
        "n_parallel": n_parallel,
        "warnings": warn,
    }


# ── MPPT solar charge ─────────────────────────────────────────────────────────

def mppt_solar_charge(
    v_mpp_v: float,
    i_mpp_a: float,
    peak_sun_hours: float,
    v_bat_v: float,
    capacity_ah: float,
    soc_init: float = 0.5,
    t_panel_c: float = 25.0,
    isc_temp_coeff_per_c: float = 0.0004,
    mppt_efficiency: float = 0.95,
) -> dict:
    """
    Estimate MPPT solar-charge operating point and daily energy delivered to battery.

    Parameters
    ----------
    v_mpp_v:
        Panel MPP voltage at STC (V).
    i_mpp_a:
        Panel MPP current at STC (A).
    peak_sun_hours:
        Daily peak sun hours at the installation site (h/day).
    v_bat_v:
        Battery terminal voltage during charging (V).
    capacity_ah:
        Battery capacity (Ah); used to compute ΔSOC.
    soc_init:
        SOC at start of day (0–1; default 0.5).
    t_panel_c:
        Panel operating temperature (°C; default 25 = STC).
    isc_temp_coeff_per_c:
        I_sc temperature coefficient (fraction/°C; default 0.0004 = +0.04%/°C typical
        crystalline silicon; negative for some technologies).
    mppt_efficiency:
        MPPT converter efficiency (0–1; default 0.95).

    Returns
    -------
    dict with keys:
        ok, p_mppt_w, p_mppt_derated_w, e_day_wh, delta_soc,
        soc_end, mppt_efficiency, warnings
    """
    warn: list[str] = []

    vm, err = _require_positive(v_mpp_v, "v_mpp_v")
    if err:
        return {"ok": False, "reason": err}
    im, err = _require_positive(i_mpp_a, "i_mpp_a")
    if err:
        return {"ok": False, "reason": err}
    psh, err = _require_positive(peak_sun_hours, "peak_sun_hours")
    if err:
        return {"ok": False, "reason": err}
    vb, err = _require_positive(v_bat_v, "v_bat_v")
    if err:
        return {"ok": False, "reason": err}
    q, err = _require_positive(capacity_ah, "capacity_ah")
    if err:
        return {"ok": False, "reason": err}
    si, err = _require_nonneg(soc_init, "soc_init")
    if err:
        return {"ok": False, "reason": err}
    if si > 1.0:
        return {"ok": False, "reason": "soc_init must be <= 1.0"}
    me, err = _require_positive(mppt_efficiency, "mppt_efficiency")
    if err:
        return {"ok": False, "reason": err}
    if me > 1.0:
        return {"ok": False, "reason": "mppt_efficiency must be <= 1.0"}

    # Temperature derating of MPP current
    delta_t = t_panel_c - 25.0
    i_mpp_derated = im * (1.0 + isc_temp_coeff_per_c * delta_t)
    i_mpp_derated = max(0.0, i_mpp_derated)

    p_mppt = vm * i_mpp_derated
    p_mppt_to_bat = p_mppt * me  # after MPPT converter efficiency

    e_day_wh = p_mppt_to_bat * psh  # Wh delivered per day
    delta_soc = e_day_wh / (vb * q)  # SOC gained per day
    delta_soc = min(delta_soc, 1.0 - si)  # can't exceed 100% SOC
    soc_end = min(1.0, si + delta_soc)

    if p_mppt_to_bat < 1.0:
        warn.append(
            f"MPPT output {p_mppt_to_bat:.2f}W is very low; check panel orientation "
            "or shading"
        )

    if t_panel_c > 70.0:
        warn.append(
            f"Panel temperature {t_panel_c:.1f}°C is high; significant power derating"
        )

    return {
        "ok": True,
        "p_mppt_w": round(p_mppt, 4),
        "p_mppt_to_bat_w": round(p_mppt_to_bat, 4),
        "e_day_wh": round(e_day_wh, 4),
        "delta_soc": round(delta_soc, 6),
        "soc_end": round(soc_end, 6),
        "i_mpp_derated_a": round(i_mpp_derated, 6),
        "t_panel_c": t_panel_c,
        "mppt_efficiency": me,
        "warnings": warn,
    }
