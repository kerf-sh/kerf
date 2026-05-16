"""
LED driver / lighting electronics design — pure Python (math only).

Distinct from:
  kerf_electronics.battery  — battery pack sizing
  kerf_electronics.pdn      — power distribution network
  kerf_electronics.afilter  — analog filter design
  kerf_electronics.rfmatch  — RF impedance matching

Capabilities
------------
led_string_layout
    Determine series/parallel LED string configuration from supply voltage,
    target lumens, per-LED Vf/If/lm spec.  Forward-current binning headroom
    applied; string-mismatch between strings flagged in warnings.

series_resistor
    Simple series-resistor sizing for a single LED string: R, power dissipated,
    efficiency (V_led/V_supply).

driver_topology_choice
    Linear constant-current (LDO-CC) vs switching recommendation based on
    (V_supply - V_string) headroom and efficiency threshold.

buck_cc_design
    Buck converter constant-current LED driver: duty cycle, peak and average
    inductor current, inductor value (ripple spec), output capacitor (ripple
    spec), switch voltage/current stress.

boost_cc_design
    Boost converter constant-current LED driver: duty cycle, inductor value,
    output capacitor, switch stress.

thermal_derating
    Junction temperature from thermal resistance + ambient; per-LED lumen and
    Vf derating based on Tj.  Over-temp flag in warnings.

pwm_dimming
    Average LED current, apparent brightness and percent-flicker from PWM
    frequency/duty-cycle/peak current.  Human-visible flicker note (< 1 kHz
    at low duty cycle).

All functions return plain dicts {ok: bool, ...}.
Out-of-range / over-temp / low-efficiency / string-mismatch cases are flagged
via warnings.warn; dicts still carry ok=True with a "warnings" list.
Functions never raise.

References
----------
  Lenk, "Practical Illumination Design with LEDs" (Wiley 2011)
  Winder, "Power Supplies for LED Driving" (Newnes 2008)
  Erickson & Maksimovic, "Fundamentals of Power Electronics" (3rd ed.)
  IES TM-21 (lumen depreciation); ENERGY STAR flicker < 30% threshold.

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import List, Optional

# ── Efficiency warning threshold ──────────────────────────────────────────────
_LOW_EFF_THRESHOLD = 0.60   # below 60 % total efficiency → warn
_OVER_TEMP_THRESHOLD = 125.0  # junction temperature [°C]
_FLICKER_VISIBLE_FREQ_HZ = 1000.0  # below this PWM frequency may cause visible flicker
_FLICKER_ENERGY_STAR_MAX = 0.30    # ENERGY STAR: percent-flicker <= 30 %


# ── Input validation helpers ──────────────────────────────────────────────────

def _chk_pos(value, name: str) -> Optional[str]:
    if not isinstance(value, (int, float)) or math.isnan(value) or value <= 0:
        return f"{name} must be a positive finite number, got {value!r}"
    return None


def _chk_nonneg(value, name: str) -> Optional[str]:
    if not isinstance(value, (int, float)) or math.isnan(value) or value < 0:
        return f"{name} must be >= 0, got {value!r}"
    return None


def _chk_frac(value, name: str) -> Optional[str]:
    """0 < value <= 1."""
    if not isinstance(value, (int, float)) or math.isnan(value) or value <= 0 or value > 1:
        return f"{name} must be in (0, 1], got {value!r}"
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. led_string_layout
# ═══════════════════════════════════════════════════════════════════════════════

def led_string_layout(
    supply_v: float,
    target_lumens: float,
    led_vf: float,
    led_if_a: float,
    led_lumens: float,
    vf_headroom_v: float = 1.5,
    binning_headroom_frac: float = 0.05,
    max_parallel_strings: int = 8,
) -> dict:
    """
    Determine series/parallel LED string configuration.

    Steps
    -----
    1.  Compute minimum LEDs in series so that V_string ≤ supply_v − vf_headroom_v.
    2.  Compute number of strings in parallel so that total_lumens ≥ target_lumens,
        derated by (1 − binning_headroom_frac) to allow for Vf/If bin spread.
    3.  Report V_string, I_total, total_lumens, efficiency_lm_per_w.

    Warnings
    --------
    - "string_mismatch" if n_parallel > 1 and binning_headroom_frac < 0.05
      (strings may not balance without a per-string CC driver).
    - "efficiency_low" if (V_string / supply_v) < _LOW_EFF_THRESHOLD.
    - "exceeds_max_parallel" if n_parallel > max_parallel_strings.

    Parameters
    ----------
    supply_v             : float — supply voltage [V]
    target_lumens        : float — required total luminous flux [lm]
    led_vf               : float — typical LED forward voltage [V]
    led_if_a             : float — rated LED forward current [A]
    led_lumens           : float — luminous flux per LED at led_if_a [lm]
    vf_headroom_v        : float — minimum driver headroom above V_string [V] (default 1.5 V)
    binning_headroom_frac: float — fraction of lm derating for binning spread (default 0.05)
    max_parallel_strings : int   — advisory maximum parallel strings (default 8)

    Returns
    -------
    dict: ok, n_series, n_parallel, n_total, v_string_v, i_total_a,
          total_lumens_achievable, input_power_w, efficiency_lm_per_w,
          warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("supply_v", supply_v), ("target_lumens", target_lumens),
        ("led_vf", led_vf), ("led_if_a", led_if_a), ("led_lumens", led_lumens),
        ("vf_headroom_v", vf_headroom_v),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    err = _chk_frac(binning_headroom_frac + 1e-15, "binning_headroom_frac+guard")
    # Actually allow 0 <= binning_headroom_frac < 1
    if not isinstance(binning_headroom_frac, (int, float)) or math.isnan(binning_headroom_frac) \
            or binning_headroom_frac < 0 or binning_headroom_frac >= 1:
        return {"ok": False, "reason": f"binning_headroom_frac must be in [0, 1), got {binning_headroom_frac!r}"}

    if not isinstance(max_parallel_strings, int) or max_parallel_strings < 1:
        return {"ok": False, "reason": f"max_parallel_strings must be a positive integer, got {max_parallel_strings!r}"}

    available_v = supply_v - vf_headroom_v
    if available_v <= 0:
        return {
            "ok": False,
            "reason": (
                f"supply_v ({supply_v} V) minus vf_headroom_v ({vf_headroom_v} V) "
                f"leaves no room for LEDs ({available_v:.3f} V ≤ 0)"
            ),
        }

    # Maximum LEDs in series
    n_series = max(1, int(available_v / led_vf))
    v_string = n_series * led_vf

    # Derated lumens per string
    lm_per_led_derated = led_lumens * (1.0 - binning_headroom_frac)
    lm_per_string = n_series * lm_per_led_derated

    if lm_per_string <= 0:
        return {"ok": False, "reason": "Derated lumens per string is zero; check led_lumens / binning_headroom_frac"}

    n_parallel = math.ceil(target_lumens / lm_per_string)
    n_total = n_series * n_parallel

    i_total = n_parallel * led_if_a
    total_lm_achievable = n_parallel * lm_per_string
    input_power_w = supply_v * i_total
    efficiency_lm_per_w = total_lm_achievable / input_power_w if input_power_w > 0 else 0.0

    # Warnings
    eff_v = v_string / supply_v
    if eff_v < _LOW_EFF_THRESHOLD:
        msg = (
            f"efficiency_low: V_string/V_supply = {eff_v:.2%} < {_LOW_EFF_THRESHOLD:.0%}; "
            "consider a higher supply voltage or fewer series LEDs."
        )
        sol_warnings.append(msg)
        warnings.warn(f"led_string_layout: {msg}", stacklevel=2)

    if n_parallel > 1 and binning_headroom_frac < 0.05:
        msg = (
            f"string_mismatch: {n_parallel} parallel strings with binning_headroom_frac "
            f"= {binning_headroom_frac:.2%} < 5 %; Vf spread may cause current imbalance. "
            "Use a per-string constant-current regulator."
        )
        sol_warnings.append(msg)
        warnings.warn(f"led_string_layout: {msg}", stacklevel=2)

    if n_parallel > max_parallel_strings:
        msg = (
            f"exceeds_max_parallel: {n_parallel} strings > advisory limit {max_parallel_strings}; "
            "consider a higher-flux LED or a multi-channel driver IC."
        )
        sol_warnings.append(msg)
        warnings.warn(f"led_string_layout: {msg}", stacklevel=2)

    return {
        "ok": True,
        "n_series": n_series,
        "n_parallel": n_parallel,
        "n_total": n_total,
        "v_string_v": round(v_string, 6),
        "i_total_a": round(i_total, 6),
        "total_lumens_achievable": round(total_lm_achievable, 4),
        "input_power_w": round(input_power_w, 6),
        "efficiency_lm_per_w": round(efficiency_lm_per_w, 4),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. series_resistor
# ═══════════════════════════════════════════════════════════════════════════════

def series_resistor(
    supply_v: float,
    led_vf: float,
    led_if_a: float,
    n_series: int = 1,
) -> dict:
    """
    Size a simple series resistor for an LED string.

    R = (V_supply - n_series × Vf) / If
    P_R = R × If²
    efficiency = (n_series × Vf × If) / (V_supply × If) = n_series × Vf / V_supply

    Parameters
    ----------
    supply_v  : float — supply voltage [V]
    led_vf    : float — LED forward voltage [V]
    led_if_a  : float — target LED forward current [A]
    n_series  : int   — number of LEDs in series (default 1)

    Returns
    -------
    dict: ok, r_series_ohm, p_resistor_w, p_led_w, efficiency,
          v_string_v, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [("supply_v", supply_v), ("led_vf", led_vf), ("led_if_a", led_if_a)]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    if not isinstance(n_series, int) or n_series < 1:
        return {"ok": False, "reason": f"n_series must be a positive integer, got {n_series!r}"}

    v_string = n_series * led_vf
    v_drop = supply_v - v_string

    if v_drop <= 0:
        return {
            "ok": False,
            "reason": (
                f"V_supply ({supply_v} V) ≤ V_string ({v_string} V) = "
                f"{n_series} × {led_vf} V; no headroom for series resistor."
            ),
        }

    r_series = v_drop / led_if_a
    p_resistor = r_series * led_if_a ** 2
    p_led = v_string * led_if_a
    efficiency = v_string / supply_v

    if efficiency < _LOW_EFF_THRESHOLD:
        msg = (
            f"efficiency_low: series-resistor efficiency = {efficiency:.2%} < {_LOW_EFF_THRESHOLD:.0%}; "
            "consider a switching CC driver."
        )
        sol_warnings.append(msg)
        warnings.warn(f"series_resistor: {msg}", stacklevel=2)

    return {
        "ok": True,
        "r_series_ohm": round(r_series, 6),
        "p_resistor_w": round(p_resistor, 6),
        "p_led_w": round(p_led, 6),
        "efficiency": round(efficiency, 6),
        "v_string_v": round(v_string, 6),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. driver_topology_choice
# ═══════════════════════════════════════════════════════════════════════════════

def driver_topology_choice(
    supply_v: float,
    v_string_v: float,
    led_if_a: float,
    efficiency_threshold: float = 0.80,
) -> dict:
    """
    Recommend linear CC (LDO-type) or switching CC topology.

    Decision rule:
      - V_drop = V_supply − V_string
      - Linear efficiency ≈ V_string / V_supply
      - If linear_efficiency >= efficiency_threshold → linear is acceptable.
      - If V_string > V_supply → boost required.
      - Otherwise → buck CC recommended.
      - Power dissipated in linear regulator: P_linear = V_drop × I_led.

    Warnings
    --------
    - "efficiency_low" if linear_efficiency < _LOW_EFF_THRESHOLD, even if
      switching is chosen.

    Parameters
    ----------
    supply_v             : float — supply voltage [V]
    v_string_v           : float — LED string voltage [V]
    led_if_a             : float — LED forward current [A]
    efficiency_threshold : float — min acceptable linear efficiency (default 0.80)

    Returns
    -------
    dict: ok, topology ('linear'|'buck'|'boost'), linear_efficiency,
          p_linear_dissipation_w, v_drop_v, recommend_switching, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("supply_v", supply_v), ("v_string_v", v_string_v), ("led_if_a", led_if_a)
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    if not isinstance(efficiency_threshold, (int, float)) or \
            math.isnan(efficiency_threshold) or efficiency_threshold <= 0 or efficiency_threshold >= 1:
        return {"ok": False, "reason": f"efficiency_threshold must be in (0, 1), got {efficiency_threshold!r}"}

    v_drop = supply_v - v_string_v
    linear_eff = v_string_v / supply_v
    p_linear = max(0.0, v_drop) * led_if_a

    if v_string_v > supply_v:
        topology = "boost"
        recommend_switching = True
    elif linear_eff >= efficiency_threshold:
        topology = "linear"
        recommend_switching = False
    else:
        topology = "buck"
        recommend_switching = True

    if linear_eff < _LOW_EFF_THRESHOLD:
        msg = (
            f"efficiency_low: linear efficiency = {linear_eff:.2%} < {_LOW_EFF_THRESHOLD:.0%}; "
            "switching driver strongly recommended."
        )
        sol_warnings.append(msg)
        warnings.warn(f"driver_topology_choice: {msg}", stacklevel=2)

    return {
        "ok": True,
        "topology": topology,
        "linear_efficiency": round(linear_eff, 6),
        "p_linear_dissipation_w": round(p_linear, 6),
        "v_drop_v": round(v_drop, 6),
        "recommend_switching": recommend_switching,
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. buck_cc_design
# ═══════════════════════════════════════════════════════════════════════════════

def buck_cc_design(
    v_in: float,
    v_string: float,
    i_led: float,
    fsw_hz: float,
    inductor_ripple_frac: float = 0.20,
    cap_ripple_v: float = 0.05,
    eta: float = 0.90,
) -> dict:
    """
    Buck converter constant-current LED driver design.

    Duty cycle:
        D = V_out / (V_in × η)  where V_out = V_string (LED string voltage).
        (η approximates conduction + switching losses)

    Inductor (for CC LED load, average inductor current = I_led):
        ΔI_L = inductor_ripple_frac × I_led  (peak-to-peak ripple)
        L = V_in × D × (1 − D) / (ΔI_L × fsw)

    Output capacitor (CC load; caps absorb inductor ripple):
        C_out = ΔI_L / (8 × fsw × ΔV_out)
        where ΔV_out = cap_ripple_v.

    Switch stress:
        V_sw_max = V_in
        I_sw_peak = I_led + ΔI_L / 2

    Warnings
    --------
    - D > 0.95 → "duty_cycle_high": effective regulation margin lost.
    - D < 0.05 → "duty_cycle_low": discontinuous operation likely.
    - efficiency_too_low if D > 1 (infeasible: V_out > V_in × η).

    Parameters
    ----------
    v_in              : float — input voltage [V]
    v_string          : float — LED string voltage = converter output [V]
    i_led             : float — LED (output) current [A]
    fsw_hz            : float — switching frequency [Hz]
    inductor_ripple_frac: float — peak-to-peak inductor ripple / I_led (default 0.20)
    cap_ripple_v      : float — max output voltage ripple [V] (default 0.05 V)
    eta               : float — estimated converter efficiency 0 < η ≤ 1 (default 0.90)

    Returns
    -------
    dict: ok, duty_cycle, l_inductor_h, c_out_f, i_l_peak_a, i_l_valley_a,
          v_sw_max_v, i_sw_peak_a, delta_il_a, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("v_in", v_in), ("v_string", v_string), ("i_led", i_led), ("fsw_hz", fsw_hz),
        ("cap_ripple_v", cap_ripple_v),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    err = _chk_frac(inductor_ripple_frac, "inductor_ripple_frac")
    if err:
        return {"ok": False, "reason": err}

    err = _chk_frac(eta, "eta")
    if err:
        return {"ok": False, "reason": err}

    if v_string >= v_in:
        return {
            "ok": False,
            "reason": (
                f"v_string ({v_string} V) >= v_in ({v_in} V); "
                "buck converter requires V_out < V_in. Use boost topology."
            ),
        }

    D = v_string / (v_in * eta)

    if D > 1.0:
        msg = (
            f"efficiency_too_low: duty_cycle D = {D:.4f} > 1 after η = {eta:.2%} correction; "
            "increase η estimate or reduce v_string."
        )
        sol_warnings.append(msg)
        warnings.warn(f"buck_cc_design: {msg}", stacklevel=2)
        D = min(D, 1.0)

    if D > 0.95:
        msg = f"duty_cycle_high: D = {D:.4f} > 0.95; regulation headroom is limited."
        sol_warnings.append(msg)
        warnings.warn(f"buck_cc_design: {msg}", stacklevel=2)

    if D < 0.05:
        msg = f"duty_cycle_low: D = {D:.4f} < 0.05; converter may enter DCM."
        sol_warnings.append(msg)
        warnings.warn(f"buck_cc_design: {msg}", stacklevel=2)

    delta_il = inductor_ripple_frac * i_led
    # L = V_in * D * (1-D) / (delta_il * fsw)
    L = v_in * D * (1.0 - D) / (delta_il * fsw_hz)
    # C_out for CC load (inductor ripple → cap ripple)
    C_out = delta_il / (8.0 * fsw_hz * cap_ripple_v)

    i_l_peak = i_led + delta_il / 2.0
    i_l_valley = i_led - delta_il / 2.0
    v_sw_max = v_in
    i_sw_peak = i_l_peak  # same as peak inductor current (sync buck or diode)

    return {
        "ok": True,
        "duty_cycle": round(D, 6),
        "l_inductor_h": round(L, 10),
        "c_out_f": round(C_out, 12),
        "i_l_peak_a": round(i_l_peak, 6),
        "i_l_valley_a": round(i_l_valley, 6),
        "delta_il_a": round(delta_il, 6),
        "v_sw_max_v": round(v_sw_max, 6),
        "i_sw_peak_a": round(i_sw_peak, 6),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. boost_cc_design
# ═══════════════════════════════════════════════════════════════════════════════

def boost_cc_design(
    v_in: float,
    v_string: float,
    i_led: float,
    fsw_hz: float,
    inductor_ripple_frac: float = 0.20,
    cap_ripple_v: float = 0.10,
    eta: float = 0.88,
) -> dict:
    """
    Boost converter constant-current LED driver design.

    Duty cycle:
        D = 1 − V_in × η / V_out

    Inductor (CCM):
        ΔI_L = inductor_ripple_frac × I_in  where I_in = I_led × V_out / (V_in × η)
        L = V_in × D / (ΔI_L × fsw)

    Output capacitor:
        C_out = I_led × D / (fsw × ΔV_out)

    Switch stress:
        V_sw_max = V_out
        I_sw_peak = I_in + ΔI_L / 2

    Warnings
    --------
    - D > 0.90 → "duty_cycle_high" (boost converters become lossy above ~0.9).
    - D < 0 → infeasible (V_in > V_out).

    Parameters
    ----------
    v_in              : float — input voltage [V]
    v_string          : float — LED string voltage = converter output [V]
    i_led             : float — LED (output) current [A]
    fsw_hz            : float — switching frequency [Hz]
    inductor_ripple_frac: float — peak-to-peak ripple / I_in (default 0.20)
    cap_ripple_v      : float — max output voltage ripple [V] (default 0.10 V)
    eta               : float — estimated efficiency 0 < η ≤ 1 (default 0.88)

    Returns
    -------
    dict: ok, duty_cycle, l_inductor_h, c_out_f, i_in_a, i_l_peak_a,
          v_sw_max_v, i_sw_peak_a, delta_il_a, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("v_in", v_in), ("v_string", v_string), ("i_led", i_led), ("fsw_hz", fsw_hz),
        ("cap_ripple_v", cap_ripple_v),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    err = _chk_frac(inductor_ripple_frac, "inductor_ripple_frac")
    if err:
        return {"ok": False, "reason": err}

    err = _chk_frac(eta, "eta")
    if err:
        return {"ok": False, "reason": err}

    if v_string <= v_in:
        return {
            "ok": False,
            "reason": (
                f"v_string ({v_string} V) <= v_in ({v_in} V); "
                "boost converter requires V_out > V_in. Use buck topology."
            ),
        }

    D = 1.0 - v_in * eta / v_string

    if D <= 0:
        return {
            "ok": False,
            "reason": f"Computed duty cycle D = {D:.4f} ≤ 0 (V_in × η ≥ V_string); check inputs.",
        }

    if D > 0.90:
        msg = f"duty_cycle_high: D = {D:.4f} > 0.90; boost efficiency degrades significantly above 90 % duty cycle."
        sol_warnings.append(msg)
        warnings.warn(f"boost_cc_design: {msg}", stacklevel=2)

    i_in = i_led * v_string / (v_in * eta)
    delta_il = inductor_ripple_frac * i_in
    L = v_in * D / (delta_il * fsw_hz)
    C_out = i_led * D / (fsw_hz * cap_ripple_v)

    i_l_peak = i_in + delta_il / 2.0
    v_sw_max = v_string
    i_sw_peak = i_l_peak

    return {
        "ok": True,
        "duty_cycle": round(D, 6),
        "l_inductor_h": round(L, 10),
        "c_out_f": round(C_out, 12),
        "i_in_a": round(i_in, 6),
        "i_l_peak_a": round(i_l_peak, 6),
        "delta_il_a": round(delta_il, 6),
        "v_sw_max_v": round(v_sw_max, 6),
        "i_sw_peak_a": round(i_sw_peak, 6),
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. thermal_derating
# ═══════════════════════════════════════════════════════════════════════════════

def thermal_derating(
    p_dissipated_w: float,
    rth_jc: float,
    rth_cs: float,
    t_ambient_c: float,
    lm_rated: float,
    vf_rated_v: float,
    lm_derating_per_k: float = 0.005,
    vf_derating_per_k: float = 0.002,
    tj_max_c: float = 125.0,
) -> dict:
    """
    Compute LED junction temperature and apply lumen/Vf thermal derating.

    Thermal model (simple Rth chain):
        T_j = T_ambient + P_dissipated × (Rth_jc + Rth_cs)

    Derating (linear approximation from datasheet):
        ΔT = T_j − 25 °C  (standard test condition)
        lm_derated  = lm_rated  × (1 − lm_derating_per_k  × max(ΔT, 0))
        vf_derated  = vf_rated  × (1 − vf_derating_per_k  × max(ΔT, 0))
        (Vf drops slightly at higher temperature for most LEDs)

    Warnings
    --------
    - "over_temp" if T_j > tj_max_c.
    - "derating_exceeds_50pct" if lm_derated < 0.5 × lm_rated.

    Parameters
    ----------
    p_dissipated_w    : float — total power dissipated in LED junction [W]
    rth_jc            : float — junction-to-case thermal resistance [°C/W]
    rth_cs            : float — case-to-sink (or board) thermal resistance [°C/W]
    t_ambient_c       : float — ambient (heatsink) temperature [°C]
    lm_rated          : float — rated luminous flux at 25 °C [lm]
    vf_rated_v        : float — rated forward voltage at 25 °C [V]
    lm_derating_per_k : float — fractional lm decrease per °C above 25 °C (default 0.005 = 0.5 %/K)
    vf_derating_per_k : float — fractional Vf decrease per °C above 25 °C (default 0.002 = 0.2 %/K)
    tj_max_c          : float — maximum rated junction temperature [°C] (default 125 °C)

    Returns
    -------
    dict: ok, t_junction_c, delta_t_k, lm_derated, vf_derated_v,
          lm_derating_frac, vf_derating_frac, over_temp, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [
        ("p_dissipated_w", p_dissipated_w), ("rth_jc", rth_jc), ("rth_cs", rth_cs),
        ("lm_rated", lm_rated), ("vf_rated_v", vf_rated_v),
    ]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    if not isinstance(t_ambient_c, (int, float)) or math.isnan(t_ambient_c):
        return {"ok": False, "reason": f"t_ambient_c must be a finite number, got {t_ambient_c!r}"}

    for name, val in [("lm_derating_per_k", lm_derating_per_k), ("vf_derating_per_k", vf_derating_per_k)]:
        err = _chk_nonneg(val, name)
        if err:
            return {"ok": False, "reason": err}

    err = _chk_pos(tj_max_c + 273.15, "tj_max_c (must be > −273.15 °C)")  # sanity
    if tj_max_c < 0:
        return {"ok": False, "reason": f"tj_max_c must be ≥ 0 °C, got {tj_max_c!r}"}

    rth_total = rth_jc + rth_cs
    t_junction = t_ambient_c + p_dissipated_w * rth_total
    delta_t = t_junction - 25.0  # deviation from standard test condition

    lm_derating_frac = lm_derating_per_k * max(delta_t, 0.0)
    vf_derating_frac = vf_derating_per_k * max(delta_t, 0.0)

    lm_derated = lm_rated * max(0.0, 1.0 - lm_derating_frac)
    vf_derated = vf_rated_v * max(0.0, 1.0 - vf_derating_frac)

    over_temp = t_junction > tj_max_c

    if over_temp:
        msg = (
            f"over_temp: T_junction = {t_junction:.1f} °C > T_j_max = {tj_max_c:.1f} °C; "
            "improve heatsinking or reduce power."
        )
        sol_warnings.append(msg)
        warnings.warn(f"thermal_derating: {msg}", stacklevel=2)

    if lm_derated < 0.5 * lm_rated:
        msg = (
            f"derating_exceeds_50pct: lm_derated = {lm_derated:.1f} lm < 50 % of rated {lm_rated:.1f} lm; "
            "thermal management is inadequate."
        )
        sol_warnings.append(msg)
        warnings.warn(f"thermal_derating: {msg}", stacklevel=2)

    return {
        "ok": True,
        "t_junction_c": round(t_junction, 4),
        "delta_t_k": round(delta_t, 4),
        "lm_derated": round(lm_derated, 4),
        "vf_derated_v": round(vf_derated, 6),
        "lm_derating_frac": round(lm_derating_frac, 6),
        "vf_derating_frac": round(vf_derating_frac, 6),
        "over_temp": over_temp,
        "warnings": sol_warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 7. pwm_dimming
# ═══════════════════════════════════════════════════════════════════════════════

def pwm_dimming(
    pwm_freq_hz: float,
    duty_cycle: float,
    i_peak_a: float,
) -> dict:
    """
    Compute average LED current, apparent brightness ratio, and percent-flicker.

    Average current:
        I_avg = duty_cycle × I_peak

    Apparent brightness ratio (approximately linear with current for LEDs):
        brightness_ratio = duty_cycle

    Percent flicker (IEEE 1789 / ENERGY STAR definition):
        percent_flicker = (I_max − I_min) / (I_max + I_min) × 100
        For ideal PWM: I_max = I_peak, I_min = 0:
        percent_flicker = 100 %  (at any duty cycle)
        This is the worst case.  Driver output filtering will reduce this.

    Flicker index (area-based, not computed here) requires waveform integration.
    percent_flicker note: values > 30 % may be perceptible below 1 kHz (ENERGY STAR
    flicker criterion).

    Warnings
    --------
    - "visible_flicker" if pwm_freq_hz < _FLICKER_VISIBLE_FREQ_HZ and
      percent_flicker > _FLICKER_ENERGY_STAR_MAX × 100.

    Parameters
    ----------
    pwm_freq_hz : float — PWM switching frequency [Hz]
    duty_cycle  : float — PWM duty cycle (0 < D ≤ 1)
    i_peak_a    : float — peak LED current [A] during on-time

    Returns
    -------
    dict: ok, i_avg_a, brightness_ratio, percent_flicker,
          pwm_period_s, visible_flicker_risk, warnings
    """
    sol_warnings: List[str] = []

    for name, val in [("pwm_freq_hz", pwm_freq_hz), ("i_peak_a", i_peak_a)]:
        err = _chk_pos(val, name)
        if err:
            return {"ok": False, "reason": err}

    err = _chk_frac(duty_cycle, "duty_cycle")
    if err:
        return {"ok": False, "reason": err}

    i_avg = duty_cycle * i_peak_a
    brightness_ratio = duty_cycle
    # Ideal PWM: on-state = I_peak, off-state = 0
    percent_flicker = 100.0  # (I_peak - 0) / (I_peak + 0) × 100

    pwm_period_s = 1.0 / pwm_freq_hz

    visible_flicker_risk = (
        pwm_freq_hz < _FLICKER_VISIBLE_FREQ_HZ
        and percent_flicker > _FLICKER_ENERGY_STAR_MAX * 100.0
    )

    if visible_flicker_risk:
        msg = (
            f"visible_flicker: PWM frequency {pwm_freq_hz:.0f} Hz < {_FLICKER_VISIBLE_FREQ_HZ:.0f} Hz "
            f"with percent_flicker = {percent_flicker:.0f} % > {_FLICKER_ENERGY_STAR_MAX * 100:.0f} %; "
            "may cause perceptible flicker. Increase PWM frequency above 1 kHz "
            "or use analog dimming."
        )
        sol_warnings.append(msg)
        warnings.warn(f"pwm_dimming: {msg}", stacklevel=2)

    return {
        "ok": True,
        "i_avg_a": round(i_avg, 8),
        "brightness_ratio": round(brightness_ratio, 6),
        "percent_flicker": round(percent_flicker, 4),
        "pwm_period_s": round(pwm_period_s, 10),
        "visible_flicker_risk": visible_flicker_risk,
        "warnings": sol_warnings,
    }
