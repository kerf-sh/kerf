"""
kerf_cad_core.pneumatics.circuit — pneumatic (compressible-air) circuit sizing.

Implements eight public functions:

  cylinder(bore_m, rod_m, supply_pressure_Pa, *, load_N, friction_ratio,
           back_pressure_Pa)
      Theoretical & effective extend/retract forces; load-ratio check.

  air_consumption(bore_m, rod_m, stroke_m, supply_pressure_Pa, cycles_per_min,
                  *, double_acting, T_K)
      Free-air consumption (Nl/min) using compression ratio from gauge pressure.

  valve_flow_iso6358(P1_Pa, P2_Pa, T1_K, C_m3s_Pa, b, *, A_m2)
      Mass-flow/volumetric-flow through a valve per ISO 6358 using sonic
      conductance C and critical pressure ratio b. Distinguishes choked
      (P2/P1 <= b) and subsonic (P2/P1 > b) branches.

  valve_flow_cv(Cv, P1_Pa, P2_Pa, T_K, *, SG_gas, P_atm_Pa)
      Volumetric flow through a valve using the US Cv coefficient; includes
      choked (critical) and subsonic branches for compressible gas.

  receiver_sizing(V_receiver_m3, P_high_Pa, P_low_Pa, Q_demand_m3s_free, *,
                  P_atm_Pa, T_K)
      Time a receiver can supply demand between P_high and P_low; and the
      minimum receiver volume for a given allowable pressure-drop time.

  blowdown_time(V_m3, P_initial_Pa, P_final_Pa, C_m3s_Pa, b, *, T_K,
                P_atm_Pa)
      Time to exhaust a receiver to atmosphere through a fixed orifice/valve
      (ISO 6358 choked/subsonic branches integrated piecewise).

  charge_time(V_m3, P_initial_Pa, P_final_Pa, Q_compressor_m3s_free, *,
              P_atm_Pa, T_K)
      Time to charge a receiver from a compressor at constant free-air flow.

  frl_pressure_drop(Q_free_m3s, supply_pressure_Pa, *, filter_dP_Pa,
                    regulator_dP_Pa, lubricator_dP_Pa)
      Total pressure drop across a filter-regulator-lubricator (FRL) unit.

All functions return plain dicts:
    success → {"ok": True, ..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise; exceedance conditions add entries to the "warnings"
list in the returned dict but still return ok=True.

Units (SI throughout unless noted)
-----------------------------------
  length         — metres (m)
  area           — m²
  volume         — m³ (or Nl = normal litres where labelled _Nl)
  pressure       — Pascals absolute (Pa_abs) or gauge (Pa_g) as noted
  flow rate      — m³/s (actual conditions) or Nl/min (normal/free-air)
  force          — Newtons (N)
  temperature    — Kelvin (K); ambient = 293.15 K (20 °C) by default
  sonic conductance C — m³/(s·Pa)  (ISO 6358)
  critical pressure ratio b — dimensionless (ISO 6358)

Pressure convention:
  supply_pressure_Pa and P1_Pa/P2_Pa are ABSOLUTE pressures unless the
  parameter name explicitly contains "gauge".
  Standard atmosphere P_atm = 101325 Pa.
  Normal conditions: T_N = 293.15 K, P_N = 101325 Pa.

Compression ratio (for free-air calculations):
  r = P_abs / P_atm   where P_abs = P_gauge + P_atm

References
----------
ISO 6358-1:2013 — Pneumatic fluid power; Flow-rate characteristics
SMC Technical Data — Pneumatic Actuator Selection Guide
Parker Hannifin Pneumatics — P3E Actuator Catalogue
Festo Pneumatic Fundamentals (2nd ed.)
NFPA T3.21.3 — Cylinder force and speed calculations

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_P_ATM = 101_325.0      # Pa, standard atmosphere
_T_N   = 293.15         # K,  normal reference temperature (ISO 6358)
_P_N   = 101_325.0      # Pa, normal reference pressure

# Ratio of specific heats for dry air (isentropic exponent)
_GAMMA = 1.4

# Critical pressure ratio for isentropic nozzle (ideal gas):
# b_ideal = (2 / (γ+1))^(γ/(γ−1)) = (2/2.4)^3.5 ≈ 0.528
_B_IDEAL = (2.0 / (_GAMMA + 1.0)) ** (_GAMMA / (_GAMMA - 1.0))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ok(**fields) -> dict:
    d: dict = {"ok": True, "warnings": []}
    d.update(fields)
    return d


def _guard_pos(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


def _guard_frac(name: str, value: Any) -> str | None:
    """Fraction in (0, 1]."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite"
    if not (0.0 < v <= 1.0):
        return f"{name} must be in (0, 1], got {v}"
    return None


# ---------------------------------------------------------------------------
# 1. cylinder
# ---------------------------------------------------------------------------

def cylinder(
    bore_m: float,
    rod_m: float,
    supply_pressure_Pa: float,
    *,
    load_N: float = 0.0,
    friction_ratio: float = 0.05,
    back_pressure_Pa: float = _P_ATM,
) -> dict:
    """
    Pneumatic cylinder theoretical and effective force.

    Theoretical (no friction, no back-pressure):
        F_extend_th  = (P_supply − P_atm) × A_bore        [gauge pressure × area]
        F_retract_th = (P_supply − P_atm) × A_rod

    Effective (with friction and back-pressure on exhaust side):
        F_extend_eff  = P_supply × A_bore  − back_pressure × A_rod
                        − friction_ratio × F_extend_th
        F_retract_eff = P_supply × A_rod   − back_pressure × A_bore
                        − friction_ratio × F_retract_th

    Load ratio (extend):
        LR = load_N / F_extend_eff     (should be <= 0.70 for reliable operation)

    Parameters
    ----------
    bore_m             : float — cylinder bore diameter (m). > 0.
    rod_m              : float — piston rod diameter (m). > 0 and < bore_m.
    supply_pressure_Pa : float — supply pressure ABSOLUTE (Pa). > P_atm.
    load_N             : float — applied load on extend stroke (N). >= 0. Default 0.
    friction_ratio     : float — friction as fraction of theoretical force. (0,1].
                                  Default 0.05 (5%).
    back_pressure_Pa   : float — exhaust-side back pressure ABSOLUTE (Pa). Default P_atm.

    Returns
    -------
    dict (ok=True)
        bore_m, rod_m, supply_pressure_Pa, back_pressure_Pa, friction_ratio
        A_bore_m2, A_rod_m2
        F_extend_th_N, F_retract_th_N         — theoretical forces (N)
        F_extend_eff_N, F_retract_eff_N       — effective forces (N)
        load_ratio_extend                      — load_N / F_extend_eff
        load_ratio_ok                          — True if LR <= 0.70
        warnings
    """
    e = _guard_pos("bore_m", bore_m)
    if e:
        return _err(e)
    e = _guard_pos("rod_m", rod_m)
    if e:
        return _err(e)
    e = _guard_pos("supply_pressure_Pa", supply_pressure_Pa)
    if e:
        return _err(e)
    e = _guard_nonneg("load_N", load_N)
    if e:
        return _err(e)
    e = _guard_frac("friction_ratio", friction_ratio)
    if e:
        return _err(e)
    e = _guard_pos("back_pressure_Pa", back_pressure_Pa)
    if e:
        return _err(e)

    D = float(bore_m)
    d = float(rod_m)
    P_s = float(supply_pressure_Pa)
    P_b = float(back_pressure_Pa)
    mu  = float(friction_ratio)
    F_L = float(load_N)

    if d >= D:
        return _err(f"rod_m ({d}) must be < bore_m ({D})")
    if P_s <= _P_ATM:
        return _err(
            f"supply_pressure_Pa ({P_s:.0f}) must be > atmospheric ({_P_ATM:.0f} Pa); "
            "use absolute pressure"
        )

    A_bore = math.pi / 4.0 * D ** 2
    A_rod  = math.pi / 4.0 * (D ** 2 - d ** 2)

    # Gauge pressure available for work
    P_gauge = P_s - _P_ATM

    # Theoretical forces (gauge × area)
    F_extend_th  = P_gauge * A_bore
    F_retract_th = P_gauge * A_rod

    # Effective forces: supply on drive side, back-pressure on exhaust side, friction deducted
    F_extend_eff  = P_s * A_bore  - P_b * A_rod  - mu * F_extend_th
    F_retract_eff = P_s * A_rod   - P_b * A_bore - mu * F_retract_th

    warns: list[str] = []

    # Load ratio
    if F_extend_eff > 0:
        load_ratio = F_L / F_extend_eff
    else:
        load_ratio = float("inf")
        warns.append(
            "F_extend_eff <= 0: back-pressure and friction exceed drive force; "
            "cylinder will not move on extend stroke"
        )

    load_ratio_ok = load_ratio <= 0.70
    if not load_ratio_ok and math.isfinite(load_ratio):
        warns.append(
            f"Load ratio {load_ratio:.3f} > 0.70: cylinder may stall or be unreliable; "
            "increase bore or supply pressure, or reduce load"
        )

    if F_retract_eff <= 0:
        warns.append(
            "F_retract_eff <= 0: back-pressure on bore side exceeds rod-side drive force; "
            "cylinder will not retract"
        )

    result = _ok(
        bore_m=D,
        rod_m=d,
        supply_pressure_Pa=P_s,
        back_pressure_Pa=P_b,
        friction_ratio=mu,
        load_N=F_L,
        A_bore_m2=A_bore,
        A_rod_m2=A_rod,
        F_extend_th_N=F_extend_th,
        F_retract_th_N=F_retract_th,
        F_extend_eff_N=F_extend_eff,
        F_retract_eff_N=F_retract_eff,
        load_ratio_extend=load_ratio,
        load_ratio_ok=load_ratio_ok,
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 2. air_consumption
# ---------------------------------------------------------------------------

def air_consumption(
    bore_m: float,
    rod_m: float,
    stroke_m: float,
    supply_pressure_Pa: float,
    cycles_per_min: float,
    *,
    double_acting: bool = True,
    T_K: float = _T_N,
) -> dict:
    """
    Free-air (normal) consumption of a pneumatic cylinder in Nl/min.

    Compression ratio from absolute supply pressure:
        r = P_supply / P_atm

    Volume swept per stroke:
        V_extend  = A_bore × stroke   [m³]
        V_retract = A_rod  × stroke   [m³]

    Actual air volume per cycle (single-acting: extend only):
        V_cycle = V_extend × r            (single-acting)
        V_cycle = (V_extend + V_retract) × r  (double-acting)

    Temperature correction to normal conditions:
        V_free = V_cycle × (T_N / T_K)

    Free-air consumption rate:
        Q_free_Nl_min = V_free × cycles_per_min × 1000   [Nl/min]

    Parameters
    ----------
    bore_m             : float — cylinder bore (m). > 0.
    rod_m              : float — rod diameter (m). > 0 and < bore.
    stroke_m           : float — piston stroke (m). > 0.
    supply_pressure_Pa : float — supply pressure ABSOLUTE (Pa). > P_atm.
    cycles_per_min     : float — complete cycles per minute. > 0.
    double_acting      : bool  — True (default) for double-acting; False for single-acting.
    T_K                : float — supply air temperature (K). Default 293.15 K (20 °C).

    Returns
    -------
    dict (ok=True)
        bore_m, rod_m, stroke_m, supply_pressure_Pa, cycles_per_min, double_acting
        A_bore_m2, A_rod_m2
        compression_ratio          — P_supply / P_atm
        V_extend_m3                — swept volume, bore side (m³)
        V_retract_m3               — swept volume, rod side (m³)
        V_cycle_actual_m3          — actual air volume per cycle (at supply P, T_K)
        V_cycle_free_m3            — free-air volume per cycle (at P_atm, T_N)
        Q_free_Nl_min              — free-air consumption rate (Nl/min)
        warnings
    """
    e = _guard_pos("bore_m", bore_m)
    if e:
        return _err(e)
    e = _guard_pos("rod_m", rod_m)
    if e:
        return _err(e)
    e = _guard_pos("stroke_m", stroke_m)
    if e:
        return _err(e)
    e = _guard_pos("supply_pressure_Pa", supply_pressure_Pa)
    if e:
        return _err(e)
    e = _guard_pos("cycles_per_min", cycles_per_min)
    if e:
        return _err(e)
    e = _guard_pos("T_K", T_K)
    if e:
        return _err(e)

    D    = float(bore_m)
    d    = float(rod_m)
    s    = float(stroke_m)
    P_s  = float(supply_pressure_Pa)
    cpm  = float(cycles_per_min)
    T    = float(T_K)

    if d >= D:
        return _err(f"rod_m ({d}) must be < bore_m ({D})")
    if P_s <= _P_ATM:
        return _err(
            f"supply_pressure_Pa ({P_s:.0f}) must be > P_atm ({_P_ATM:.0f}); "
            "use absolute pressure"
        )

    A_bore = math.pi / 4.0 * D ** 2
    A_rod  = math.pi / 4.0 * (D ** 2 - d ** 2)

    r = P_s / _P_ATM          # compression ratio

    V_extend  = A_bore * s
    V_retract = A_rod  * s

    if double_acting:
        V_cycle_actual = (V_extend + V_retract) * r
    else:
        V_cycle_actual = V_extend * r

    # Correct to normal temperature
    V_cycle_free = V_cycle_actual * (_T_N / T)

    Q_free_Nl_min = V_cycle_free * cpm * 1000.0  # m³ → litres, × cycles

    warns: list[str] = []
    if Q_free_Nl_min > 1000.0:
        warns.append(
            f"Free-air consumption {Q_free_Nl_min:.0f} Nl/min is high; "
            "verify compressor capacity and line sizing"
        )
    if r > 12.0:
        warns.append(
            f"Compression ratio {r:.1f} > 12: very high supply pressure; "
            "verify cylinder and FRL pressure rating"
        )

    result = _ok(
        bore_m=D,
        rod_m=d,
        stroke_m=s,
        supply_pressure_Pa=P_s,
        cycles_per_min=cpm,
        double_acting=bool(double_acting),
        T_K=T,
        A_bore_m2=A_bore,
        A_rod_m2=A_rod,
        compression_ratio=r,
        V_extend_m3=V_extend,
        V_retract_m3=V_retract,
        V_cycle_actual_m3=V_cycle_actual,
        V_cycle_free_m3=V_cycle_free,
        Q_free_Nl_min=Q_free_Nl_min,
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 3. valve_flow_iso6358
# ---------------------------------------------------------------------------

def valve_flow_iso6358(
    P1_Pa: float,
    P2_Pa: float,
    T1_K: float,
    C_m3s_Pa: float,
    b: float,
) -> dict:
    """
    Volumetric flow through a pneumatic valve per ISO 6358.

    ISO 6358 flow model for compressible gas:

    Choked (sonic) flow — when P2/P1 <= b:
        q_choked = C × P1 × √(T_N / T1)

    Subsonic flow — when P2/P1 > b:
        q_subsonic = C × P1 × √(T_N / T1)
                       × √(1 − ((P2/P1 − b) / (1 − b))²)

    where:
        C — sonic conductance (m³/(s·Pa))
        b — critical pressure ratio (dimensionless, typically 0.2–0.5)
        q — volumetric flow at normal conditions (m³/s at T_N, P_N)

    Returns volumetric flow in m³/s (normal conditions) and Nl/min.

    Parameters
    ----------
    P1_Pa     : float — upstream absolute pressure (Pa). > 0.
    P2_Pa     : float — downstream absolute pressure (Pa). > 0 and <= P1.
    T1_K      : float — upstream temperature (K). > 0.
    C_m3s_Pa  : float — sonic conductance (m³/(s·Pa)). > 0.
    b         : float — critical pressure ratio (dimensionless). In (0, 1).

    Returns
    -------
    dict (ok=True)
        P1_Pa, P2_Pa, T1_K, C_m3s_Pa, b
        pressure_ratio       — P2/P1
        choked               — True if flow is choked (P2/P1 <= b)
        q_m3s_normal         — volumetric flow at normal conditions (m³/s)
        q_Nl_min             — volumetric flow (Nl/min)
        q_max_m3s_normal     — maximum (choked) flow at normal conditions (m³/s)
        warnings
    """
    e = _guard_pos("P1_Pa", P1_Pa)
    if e:
        return _err(e)
    e = _guard_pos("P2_Pa", P2_Pa)
    if e:
        return _err(e)
    e = _guard_pos("T1_K", T1_K)
    if e:
        return _err(e)
    e = _guard_pos("C_m3s_Pa", C_m3s_Pa)
    if e:
        return _err(e)

    try:
        b_val = float(b)
    except (TypeError, ValueError):
        return _err(f"b must be a number, got {b!r}")
    if not (0.0 < b_val < 1.0):
        return _err(f"b (critical pressure ratio) must be in (0, 1), got {b_val}")

    P1 = float(P1_Pa)
    P2 = float(P2_Pa)
    T1 = float(T1_K)
    C  = float(C_m3s_Pa)

    if P2 > P1:
        return _err(
            f"P2_Pa ({P2:.0f}) must be <= P1_Pa ({P1:.0f}) "
            "(downstream pressure cannot exceed upstream)"
        )

    ratio = P2 / P1
    temp_factor = math.sqrt(_T_N / T1)

    # Choked (maximum) flow
    q_max = C * P1 * temp_factor

    warns: list[str] = []

    if ratio <= b_val:
        # Sonic / choked flow
        q = q_max
        choked = True
        warns.append(
            f"Flow is CHOKED (P2/P1={ratio:.4f} <= b={b_val:.4f}): "
            "valve is at maximum flow; reducing downstream pressure further "
            "will not increase flow"
        )
    else:
        # Subsonic flow
        choked = False
        inner = (ratio - b_val) / (1.0 - b_val)
        # Clamp to avoid sqrt of negative due to floating-point
        subsonic_factor = math.sqrt(max(0.0, 1.0 - inner ** 2))
        q = q_max * subsonic_factor

    # Check if valve is undersized (flow near maximum and not choked)
    if not choked and ratio < b_val * 1.1:
        warns.append(
            f"Pressure ratio P2/P1={ratio:.4f} is close to critical ratio b={b_val:.4f}; "
            "valve is operating near choked conditions — consider larger valve"
        )

    q_Nl_min = q * 1000.0 * 60.0  # m³/s → Nl/min

    result = _ok(
        P1_Pa=P1,
        P2_Pa=P2,
        T1_K=T1,
        C_m3s_Pa=C,
        b=b_val,
        pressure_ratio=ratio,
        choked=choked,
        q_m3s_normal=q,
        q_Nl_min=q_Nl_min,
        q_max_m3s_normal=q_max,
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 4. valve_flow_cv
# ---------------------------------------------------------------------------

def valve_flow_cv(
    Cv: float,
    P1_Pa: float,
    P2_Pa: float,
    T_K: float,
    *,
    SG_gas: float = 1.0,
    P_atm_Pa: float = _P_ATM,
) -> dict:
    """
    Volumetric flow through a pneumatic valve using the US Cv coefficient.

    ISA/ANSI compressible gas flow equations (simplified — ideal gas):

    Critical flow ratio (choked when P2/P1 <= Fk × Xt ≈ 0.528 for air):
        ΔP_choke = P1 × 0.5   (approximation; exact: P2 ≤ 0.528 × P1)

    Subsonic flow (P2 > 0.528 × P1):
        Q_scfh = Cv × 963 × P1_psia × Y × √(ΔP_psia / (SG × T_R × P1_psia))
            where Y = 1 − ΔP / (3 × Xt × Fk × P1)  ≈ 1 − ΔP/(3×P1/2)

    Simplified standard form used here (Masoneilan / Fisher method):

    q_Nl_min  — volumetric flow at normal conditions (Nl/min, at P_N, T_N)

    Choked flow (P2 ≤ 0.528 × P1):
        q_Nl_min = 417 × Cv × P1_bar × √(T_N / (SG × T_K))   [Nl/min]

    Subsonic flow (P2 > 0.528 × P1):
        q_Nl_min = 417 × Cv × √(ΔP_bar × P1_bar / (SG × T_K)) × √T_N  [Nl/min]

    These are the Masoneilan/Fisher pneumatic Cv equations in metric units.

    Note: 417 = 417 (empirical constant from ISA S75 for Nl/min with bar/K).

    Parameters
    ----------
    Cv         : float — valve flow coefficient (US gpm/√psi). > 0.
    P1_Pa      : float — upstream absolute pressure (Pa). > 0.
    P2_Pa      : float — downstream absolute pressure (Pa). > 0 and <= P1.
    T_K        : float — gas temperature at valve inlet (K). > 0.
    SG_gas     : float — specific gravity of gas vs air (default 1.0 for air). > 0.
    P_atm_Pa   : float — local atmospheric pressure (Pa). Default 101325.

    Returns
    -------
    dict (ok=True)
        Cv, P1_Pa, P2_Pa, T_K, SG_gas
        P1_bar, P2_bar, dP_bar
        pressure_ratio        — P2/P1
        choked                — True if P2/P1 <= 0.528
        q_Nl_min              — normal volumetric flow (Nl/min)
        q_m3s_normal          — normal volumetric flow (m³/s)
        q_max_Nl_min          — choked (maximum) flow (Nl/min)
        warnings
    """
    e = _guard_pos("Cv", Cv)
    if e:
        return _err(e)
    e = _guard_pos("P1_Pa", P1_Pa)
    if e:
        return _err(e)
    e = _guard_pos("P2_Pa", P2_Pa)
    if e:
        return _err(e)
    e = _guard_pos("T_K", T_K)
    if e:
        return _err(e)
    e = _guard_pos("SG_gas", SG_gas)
    if e:
        return _err(e)

    cv  = float(Cv)
    P1  = float(P1_Pa)
    P2  = float(P2_Pa)
    T   = float(T_K)
    sg  = float(SG_gas)

    if P2 > P1:
        return _err(
            f"P2_Pa ({P2:.0f}) must be <= P1_Pa ({P1:.0f})"
        )

    P1_bar = P1 / 1e5
    P2_bar = P2 / 1e5
    dP_bar = P1_bar - P2_bar
    ratio  = P2 / P1

    warns: list[str] = []

    # Choked condition: P2/P1 <= 0.528 (isentropic critical ratio for γ=1.4)
    choked = ratio <= _B_IDEAL

    # Maximum (choked) flow
    q_max_Nl_min = 417.0 * cv * P1_bar * math.sqrt(_T_N / (sg * T))

    if choked:
        q_Nl_min = q_max_Nl_min
        warns.append(
            f"Flow is CHOKED (P2/P1={ratio:.4f} <= {_B_IDEAL:.4f}): "
            "valve is at maximum flow capacity"
        )
    else:
        # Subsonic branch: q = 417 × Cv × √(ΔP × P1 / (SG × T)) × √T_N
        # derived from Masoneilan pneumatic Cv formula
        inner = dP_bar * P1_bar / (sg * T)
        if inner <= 0:
            q_Nl_min = 0.0
        else:
            q_Nl_min = 417.0 * cv * math.sqrt(inner) * math.sqrt(_T_N)

    # Undersized valve warning: if choked and flow < demand, or
    # if subsonic but operating very close to choked
    if not choked and ratio < _B_IDEAL * 1.05:
        warns.append(
            f"Valve operating near choked condition (P2/P1={ratio:.4f}); "
            "consider a larger Cv to reduce pressure drop"
        )

    q_m3s_normal = q_Nl_min / (1000.0 * 60.0)

    result = _ok(
        Cv=cv,
        P1_Pa=P1,
        P2_Pa=P2,
        T_K=T,
        SG_gas=sg,
        P1_bar=P1_bar,
        P2_bar=P2_bar,
        dP_bar=dP_bar,
        pressure_ratio=ratio,
        choked=choked,
        q_Nl_min=q_Nl_min,
        q_m3s_normal=q_m3s_normal,
        q_max_Nl_min=q_max_Nl_min,
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 5. receiver_sizing
# ---------------------------------------------------------------------------

def receiver_sizing(
    V_receiver_m3: float,
    P_high_Pa: float,
    P_low_Pa: float,
    Q_demand_m3s_free: float,
    *,
    P_atm_Pa: float = _P_ATM,
    T_K: float = _T_N,
) -> dict:
    """
    Receiver/tank sizing for allowable pressure drop.

    The receiver stores compressed air between P_high and P_low.
    Available free-air in the receiver:
        ΔV_free = V_receiver × (P_high − P_low) / P_atm × (T_N / T_K)

    Time to supply demand at Q_demand (constant demand, no compressor):
        t_supply = ΔV_free / Q_demand_free    [seconds]

    Minimum receiver volume for a required hold-up time t_required:
        V_min = Q_demand_free × t_required × P_atm / (P_high − P_low)

    Parameters
    ----------
    V_receiver_m3       : float — receiver volume (m³). > 0.
    P_high_Pa           : float — upper working pressure ABSOLUTE (Pa). > P_low.
    P_low_Pa            : float — lower (cut-in) pressure ABSOLUTE (Pa). > P_atm.
    Q_demand_m3s_free   : float — demand flow at normal conditions (m³/s free-air). > 0.
    P_atm_Pa            : float — atmospheric pressure (Pa). Default 101325.
    T_K                 : float — temperature (K). Default 293.15.

    Returns
    -------
    dict (ok=True)
        V_receiver_m3, P_high_Pa, P_low_Pa, Q_demand_m3s_free
        delta_P_Pa               — P_high − P_low (Pa)
        delta_V_free_m3          — free-air volume stored in receiver
        delta_V_free_Nl          — free-air stored (Nl)
        t_supply_s               — time before pressure reaches P_low (s)
        t_supply_min             — same in minutes
        warnings
    """
    e = _guard_pos("V_receiver_m3", V_receiver_m3)
    if e:
        return _err(e)
    e = _guard_pos("P_high_Pa", P_high_Pa)
    if e:
        return _err(e)
    e = _guard_pos("P_low_Pa", P_low_Pa)
    if e:
        return _err(e)
    e = _guard_pos("Q_demand_m3s_free", Q_demand_m3s_free)
    if e:
        return _err(e)
    e = _guard_pos("P_atm_Pa", P_atm_Pa)
    if e:
        return _err(e)
    e = _guard_pos("T_K", T_K)
    if e:
        return _err(e)

    V    = float(V_receiver_m3)
    P_hi = float(P_high_Pa)
    P_lo = float(P_low_Pa)
    Q_d  = float(Q_demand_m3s_free)
    P_a  = float(P_atm_Pa)
    T    = float(T_K)

    if P_hi <= P_lo:
        return _err(
            f"P_high_Pa ({P_hi:.0f}) must be > P_low_Pa ({P_lo:.0f})"
        )
    if P_lo <= P_a:
        return _err(
            f"P_low_Pa ({P_lo:.0f}) must be > P_atm ({P_a:.0f}); "
            "use absolute pressure (P_atm + gauge)"
        )

    delta_P = P_hi - P_lo
    # Free-air stored in the band
    delta_V_free = V * (delta_P / P_a) * (_T_N / T)
    t_supply = delta_V_free / Q_d

    warns: list[str] = []
    if t_supply < 5.0:
        warns.append(
            f"Receiver hold-up time {t_supply:.1f} s is very short; "
            "consider a larger receiver or narrower pressure band"
        )
    if delta_P / P_hi < 0.05:
        warns.append(
            f"Pressure band delta_P/P_high = {delta_P/P_hi:.3f} < 5%: "
            "very tight band; receiver will cycle frequently"
        )

    result = _ok(
        V_receiver_m3=V,
        P_high_Pa=P_hi,
        P_low_Pa=P_lo,
        Q_demand_m3s_free=Q_d,
        P_atm_Pa=P_a,
        T_K=T,
        delta_P_Pa=delta_P,
        delta_V_free_m3=delta_V_free,
        delta_V_free_Nl=delta_V_free * 1000.0,
        t_supply_s=t_supply,
        t_supply_min=t_supply / 60.0,
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 6. blowdown_time
# ---------------------------------------------------------------------------

def blowdown_time(
    V_m3: float,
    P_initial_Pa: float,
    P_final_Pa: float,
    C_m3s_Pa: float,
    b: float,
    *,
    T_K: float = _T_N,
    P_atm_Pa: float = _P_ATM,
) -> dict:
    """
    Time to exhaust a receiver to atmosphere through a fixed ISO 6358 orifice/valve.

    Uses ISO 6358 flow model integrated in two phases:

    Phase 1 — Choked: receiver pressure P > P_atm / b → flow rate = C × P × √(T_N/T)
        dP/dt = −C × P × √(T_N/T) × P_atm / V
        Solution (isothermal): P(t) = P0 × exp(−C × √(T_N/T) × P_atm / V × t)
        t_choked = V / (C × P_atm × √(T_N/T)) × ln(P_initial / P_choke_end)
        where P_choke_end = P_atm / b (transition to subsonic)

    Phase 2 — Subsonic: P <= P_atm / b → numerical approximation
        For the subsonic phase we use a simple linear approximation since
        the pressure difference is small relative to P_atm:
        t_subsonic ≈ (P_choke_end − P_final) / (average subsonic dP/dt)

    This is a conservative engineering estimate.

    Parameters
    ----------
    V_m3          : float — receiver volume (m³). > 0.
    P_initial_Pa  : float — initial pressure ABSOLUTE (Pa). > P_atm.
    P_final_Pa    : float — final pressure ABSOLUTE (Pa). >= P_atm. Default = P_atm.
    C_m3s_Pa      : float — sonic conductance (m³/(s·Pa)). > 0.
    b             : float — critical pressure ratio. In (0, 1).
    T_K           : float — temperature (K). Default 293.15.
    P_atm_Pa      : float — atmospheric pressure (Pa). Default 101325.

    Returns
    -------
    dict (ok=True)
        V_m3, P_initial_Pa, P_final_Pa, C_m3s_Pa, b, T_K
        P_choke_transition_Pa    — pressure at which choked flow ends
        t_choked_s               — time during choked phase (s)
        t_subsonic_s             — estimated time during subsonic phase (s)
        t_total_s                — total blowdown time (s)
        warnings
    """
    e = _guard_pos("V_m3", V_m3)
    if e:
        return _err(e)
    e = _guard_pos("P_initial_Pa", P_initial_Pa)
    if e:
        return _err(e)
    e = _guard_pos("P_final_Pa", P_final_Pa)
    if e:
        return _err(e)
    e = _guard_pos("C_m3s_Pa", C_m3s_Pa)
    if e:
        return _err(e)
    e = _guard_pos("T_K", T_K)
    if e:
        return _err(e)
    e = _guard_pos("P_atm_Pa", P_atm_Pa)
    if e:
        return _err(e)

    try:
        b_val = float(b)
    except (TypeError, ValueError):
        return _err(f"b must be a number, got {b!r}")
    if not (0.0 < b_val < 1.0):
        return _err(f"b must be in (0, 1), got {b_val}")

    V    = float(V_m3)
    P0   = float(P_initial_Pa)
    P_f  = float(P_final_Pa)
    C    = float(C_m3s_Pa)
    T    = float(T_K)
    P_a  = float(P_atm_Pa)

    if P0 <= P_a:
        return _err(
            f"P_initial_Pa ({P0:.0f}) must be > P_atm ({P_a:.0f})"
        )
    if P_f < P_a:
        return _err(
            f"P_final_Pa ({P_f:.0f}) must be >= P_atm ({P_a:.0f})"
        )
    if P_f >= P0:
        return _err(
            f"P_final_Pa ({P_f:.0f}) must be < P_initial_Pa ({P0:.0f})"
        )

    # Temperature factor for ISO 6358
    temp_factor = math.sqrt(_T_N / T)

    # Pressure at which choked flow ends: P_choke = P_atm / b
    P_choke = P_a / b_val

    warns: list[str] = []

    # ---- Phase 1: Choked blowdown ----
    if P0 <= P_choke:
        # Initial pressure already below choked threshold → skip Phase 1
        t_choked = 0.0
        P_end_choked = P0
    else:
        # Exponential decay: t = V/(C·P_a·temp_factor) × ln(P0/P_choke)
        # But we need P_end_choked = max(P_choke, P_f)
        P_end_choked = max(P_choke, P_f)
        time_constant = V / (C * P_a * temp_factor)
        if P_end_choked >= P0:
            t_choked = 0.0
        else:
            t_choked = time_constant * math.log(P0 / P_end_choked)

    # ---- Phase 2: Subsonic blowdown ----
    if P_f < P_choke and P_end_choked > P_f:
        # Approximate: integrate subsonic phase numerically with small steps
        # dP/dt = -C * P1 * temp_factor * √(1 − ((P_a/P1 − b)/(1−b))²) * P_a / V
        # We use 200-step numerical integration
        n_steps = 200
        P_start_sub = P_end_choked
        P_stop_sub  = max(P_f, P_a)
        dP_sub = (P_start_sub - P_stop_sub) / n_steps
        t_subsonic = 0.0
        P_cur = P_start_sub
        for _ in range(n_steps):
            P_mid = P_cur - dP_sub / 2.0
            if P_mid <= P_a:
                break
            r_mid = P_a / P_mid
            inner = (r_mid - b_val) / (1.0 - b_val)
            inner = max(0.0, min(1.0, inner))
            subsonic_f = math.sqrt(1.0 - inner ** 2)
            q_mid = C * P_mid * temp_factor * subsonic_f  # m³/s normal
            if q_mid <= 0:
                break
            # dP/dt = -q × P_a / V  (isothermal, conservation of mass)
            dP_dt = q_mid * P_a / V
            dt = dP_sub / dP_dt
            t_subsonic += dt
            P_cur -= dP_sub
    else:
        t_subsonic = 0.0

    t_total = t_choked + t_subsonic

    if t_total < 1.0:
        warns.append(
            f"Blowdown time {t_total:.3f} s is very short; verify orifice sizing "
            "and safety requirements for rapid pressure release"
        )

    result = _ok(
        V_m3=V,
        P_initial_Pa=P0,
        P_final_Pa=P_f,
        C_m3s_Pa=C,
        b=b_val,
        T_K=T,
        P_atm_Pa=P_a,
        P_choke_transition_Pa=P_choke,
        t_choked_s=t_choked,
        t_subsonic_s=t_subsonic,
        t_total_s=t_total,
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 7. charge_time
# ---------------------------------------------------------------------------

def charge_time(
    V_m3: float,
    P_initial_Pa: float,
    P_final_Pa: float,
    Q_compressor_m3s_free: float,
    *,
    P_atm_Pa: float = _P_ATM,
    T_K: float = _T_N,
) -> dict:
    """
    Time to charge a receiver from a compressor at constant free-air flow.

    Assumes isothermal process (constant temperature).
    Free-air added:
        ΔV_free = V × (P_final − P_initial) / P_atm × (T_N/T)

    Charge time:
        t_charge = ΔV_free / Q_compressor_free

    Parameters
    ----------
    V_m3                    : float — receiver volume (m³). > 0.
    P_initial_Pa            : float — starting pressure ABSOLUTE (Pa). >= P_atm.
    P_final_Pa              : float — target pressure ABSOLUTE (Pa). > P_initial.
    Q_compressor_m3s_free   : float — compressor free-air delivery (m³/s). > 0.
    P_atm_Pa                : float — atmospheric pressure (Pa). Default 101325.
    T_K                     : float — temperature (K). Default 293.15.

    Returns
    -------
    dict (ok=True)
        V_m3, P_initial_Pa, P_final_Pa, Q_compressor_m3s_free
        delta_P_Pa               — P_final − P_initial (Pa)
        delta_V_free_m3          — free-air volume to be added (m³)
        delta_V_free_Nl          — free-air to be added (Nl)
        t_charge_s               — charge time (s)
        t_charge_min             — charge time (minutes)
        warnings
    """
    e = _guard_pos("V_m3", V_m3)
    if e:
        return _err(e)
    e = _guard_pos("P_initial_Pa", P_initial_Pa)
    if e:
        return _err(e)
    e = _guard_pos("P_final_Pa", P_final_Pa)
    if e:
        return _err(e)
    e = _guard_pos("Q_compressor_m3s_free", Q_compressor_m3s_free)
    if e:
        return _err(e)
    e = _guard_pos("P_atm_Pa", P_atm_Pa)
    if e:
        return _err(e)
    e = _guard_pos("T_K", T_K)
    if e:
        return _err(e)

    V    = float(V_m3)
    P0   = float(P_initial_Pa)
    P_tg = float(P_final_Pa)
    Q_c  = float(Q_compressor_m3s_free)
    P_a  = float(P_atm_Pa)
    T    = float(T_K)

    if P_tg <= P0:
        return _err(
            f"P_final_Pa ({P_tg:.0f}) must be > P_initial_Pa ({P0:.0f})"
        )
    if P0 < P_a:
        return _err(
            f"P_initial_Pa ({P0:.0f}) must be >= P_atm ({P_a:.0f})"
        )

    delta_P = P_tg - P0
    delta_V_free = V * (delta_P / P_a) * (_T_N / T)
    t_charge = delta_V_free / Q_c

    warns: list[str] = []
    if t_charge > 600.0:
        warns.append(
            f"Charge time {t_charge:.0f} s ({t_charge/60.0:.1f} min) is long; "
            "consider a higher-capacity compressor or smaller receiver"
        )

    result = _ok(
        V_m3=V,
        P_initial_Pa=P0,
        P_final_Pa=P_tg,
        Q_compressor_m3s_free=Q_c,
        P_atm_Pa=P_a,
        T_K=T,
        delta_P_Pa=delta_P,
        delta_V_free_m3=delta_V_free,
        delta_V_free_Nl=delta_V_free * 1000.0,
        t_charge_s=t_charge,
        t_charge_min=t_charge / 60.0,
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 8. frl_pressure_drop
# ---------------------------------------------------------------------------

def frl_pressure_drop(
    Q_free_m3s: float,
    supply_pressure_Pa: float,
    *,
    filter_dP_Pa: float = 10_000.0,
    regulator_dP_Pa: float = 20_000.0,
    lubricator_dP_Pa: float = 10_000.0,
) -> dict:
    """
    Total pressure drop across an FRL (Filter-Regulator-Lubricator) unit.

    Simple additive model for individual component pressure drops.
    Each component drop is assumed to scale with flow squared relative to
    the rated conditions; however, if fixed values are provided they are
    used directly (conservative approach).

    The total outlet pressure:
        P_outlet = supply_pressure − (filter_dP + regulator_dP + lubricator_dP)

    Parameters
    ----------
    Q_free_m3s        : float — free-air flow through FRL (m³/s). > 0.
    supply_pressure_Pa: float — supply pressure ABSOLUTE (Pa). > P_atm.
    filter_dP_Pa      : float — pressure drop across filter (Pa). >= 0. Default 10000.
    regulator_dP_Pa   : float — pressure drop across regulator (Pa). >= 0. Default 20000.
    lubricator_dP_Pa  : float — pressure drop across lubricator (Pa). >= 0. Default 10000.

    Returns
    -------
    dict (ok=True)
        Q_free_m3s, supply_pressure_Pa
        filter_dP_Pa, regulator_dP_Pa, lubricator_dP_Pa
        total_dP_Pa              — total FRL pressure drop (Pa)
        total_dP_bar             — total FRL pressure drop (bar)
        P_outlet_Pa              — outlet pressure after FRL (Pa)
        P_outlet_bar             — outlet pressure (bar)
        efficiency_pct           — P_outlet / supply × 100
        warnings
    """
    e = _guard_pos("Q_free_m3s", Q_free_m3s)
    if e:
        return _err(e)
    e = _guard_pos("supply_pressure_Pa", supply_pressure_Pa)
    if e:
        return _err(e)
    e = _guard_nonneg("filter_dP_Pa", filter_dP_Pa)
    if e:
        return _err(e)
    e = _guard_nonneg("regulator_dP_Pa", regulator_dP_Pa)
    if e:
        return _err(e)
    e = _guard_nonneg("lubricator_dP_Pa", lubricator_dP_Pa)
    if e:
        return _err(e)

    Q   = float(Q_free_m3s)
    P_s = float(supply_pressure_Pa)
    dP_f = float(filter_dP_Pa)
    dP_r = float(regulator_dP_Pa)
    dP_l = float(lubricator_dP_Pa)

    if P_s <= _P_ATM:
        return _err(
            f"supply_pressure_Pa ({P_s:.0f}) must be > P_atm ({_P_ATM:.0f})"
        )

    total_dP = dP_f + dP_r + dP_l
    P_outlet = P_s - total_dP

    warns: list[str] = []

    if P_outlet <= _P_ATM:
        warns.append(
            f"FRL total pressure drop ({total_dP/1e5:.2f} bar) exceeds supply gauge "
            f"pressure ({(P_s-_P_ATM)/1e5:.2f} bar); outlet pressure is at or below "
            "atmospheric — FRL is severely undersized or clogged"
        )

    eff_pct = (P_outlet / P_s) * 100.0 if P_s > 0 else 0.0

    if eff_pct < 85.0 and P_outlet > _P_ATM:
        warns.append(
            f"FRL pressure efficiency {eff_pct:.1f}% < 85%: "
            "total FRL drop is high; check filter clogging, regulator set-point, "
            "or lubricator bowl restriction"
        )

    result = _ok(
        Q_free_m3s=Q,
        supply_pressure_Pa=P_s,
        filter_dP_Pa=dP_f,
        regulator_dP_Pa=dP_r,
        lubricator_dP_Pa=dP_l,
        total_dP_Pa=total_dP,
        total_dP_bar=total_dP / 1e5,
        P_outlet_Pa=P_outlet,
        P_outlet_bar=P_outlet / 1e5,
        efficiency_pct=eff_pct,
    )
    result["warnings"] = warns
    return result
