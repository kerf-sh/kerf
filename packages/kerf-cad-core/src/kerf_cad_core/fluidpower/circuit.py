"""
kerf_cad_core.fluidpower.circuit — hydraulic fluid-power circuit sizing.

Implements nine public functions:

  cylinder(bore_m, rod_m, pressure_Pa, flow_m3s, *, regen)
      Extend/retract force, velocity, differential (regenerative) mode.

  pump(displacement_m3, rpm, vol_eff, overall_eff, pressure_Pa)
      Flow from displacement × rpm × vol-eff; input power from P × Q / eff.

  motor(displacement_m3, pressure_Pa, rpm, *, mech_eff, vol_eff)
      Output torque and shaft speed from displacement, pressure, and efficiencies.

  accumulator(V_total_m3, P1_Pa, P2_Pa, P3_Pa, *, process)
      Gas pre-charge sizing (Boyle isothermal or adiabatic).

  valve_cv(Q_m3s, delta_P_Pa, SG, *, metric)
      Valve flow coefficient Cv (US) or Kv (metric) and reverse sizing.

  line_pressure_drop(Q_m3s, rho, mu, D_i_m, L_m, *, roughness_m, fittings_Le_m)
      Hagen-Poiseuille (laminar) or Darcy-Weisbach/Colebrook (turbulent)
      pressure drop through hydraulic lines.

  line_size(Q_m3s, *, service, fluid_rho, fluid_mu)
      Recommended minimum bore diameter from ISO velocity limits.

  reservoir(pump_flow_m3s, *, rule_factor)
      Rule-of-thumb reservoir volume.

  thermal_balance(input_power_W, eff_overall, *, area_m2, U_Wm2K, dT_K,
                  cooling_flow_m3s, fluid_cp, fluid_rho)
      Steady-state heat load and heat-exchanger sizing / thermal check.

All functions return plain dicts:
    success → {"ok": True, ..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise; exceedance conditions add entries to the "warnings"
list in the returned dict but still return ok=True.

Units (SI throughout unless noted)
-----------------------------------
  length         — metres (m)
  area           — m²
  volume         — m³ (or litres where labelled _L)
  pressure       — Pascals (Pa)
  flow rate      — m³/s
  density        — kg/m³
  viscosity      — Pa·s (dynamic)
  force          — Newtons (N)
  torque         — N·m
  power          — Watts (W)
  speed          — rpm (rotational); m/s (velocity)
  temperature    — K (delta T) / °C (absolute where noted)

Valve sizing convention (US Cv):
  Q [gpm] = Cv × √(ΔP [psi] / SG)
  Re-arranged for SI:
    Q [m³/s] → Q_gpm = Q / 6.30902e-5
    ΔP [Pa]  → ΔP_psi = ΔP / 6894.757

Metric Kv (ISO 4288):
  Q [m³/h] = Kv × √(ΔP [bar] / SG)
  Relation: Cv ≈ Kv × 1.156  (exact factor = √(0.0160/0.0138))

References
----------
Vickers Industrial Hydraulics Manual (4th ed.) §§ 2, 4, 5, 8
Parker Hannifin Hydraulic Systems Design Guide rev 2022
ISO 4399 — Hydraulic fluid power; Terminology
ISO 3322 — Hydraulic fluid power; Fluid requirements
Shigley's Machine Design (10th ed.) — heat transfer / reservoir sizing

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings as _warnings_mod
from typing import Any

from kerf_cad_core.fluids.friction import darcy_friction_factor


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _ok(**fields) -> dict:
    d = {"ok": True, "warnings": []}
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


def _guard_nonneg(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite"
    if v < 0:
        return f"{name} must be >= 0, got {v}"
    return None


def _guard_frac(name: str, value: Any) -> str | None:
    """Efficiency / fraction — must be in (0, 1]."""
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
# Unit-conversion constants
# ---------------------------------------------------------------------------

_M3S_TO_GPM = 1.0 / 6.30902e-5       # 1 m³/s = 15850.3 gpm
_PA_TO_PSI   = 1.0 / 6894.757         # 1 Pa   = 0.0001450 psi
_PA_TO_BAR   = 1.0 / 1e5              # 1 Pa   = 1e-5 bar
_M3S_TO_M3H  = 3600.0                 # 1 m³/s = 3600 m³/h
_CV_TO_KV    = 1.0 / 1.15626          # Cv → Kv: Kv = Cv / 1.15626

# ---------------------------------------------------------------------------
# Recommended velocity limits (m/s) per service (Vickers manual §4-2)
# ---------------------------------------------------------------------------

_VEL_LIMITS: dict[str, tuple[float, float]] = {
    # (v_min_m/s, v_max_m/s) — max is the recommended upper limit
    "suction":  (0.5,  1.5),
    "return":   (2.0,  4.0),
    "pressure": (3.0,  6.0),   # max for standard steel tubing ≤ 250 bar
}

# Absolute max velocity before cavitation / erosion risk warning
_VEL_CAVITATION = 1.2   # suction lines

# ---------------------------------------------------------------------------
# 1. cylinder
# ---------------------------------------------------------------------------

def cylinder(
    bore_m: float,
    rod_m: float,
    pressure_Pa: float,
    flow_m3s: float,
    *,
    regen: bool = False,
) -> dict:
    """
    Hydraulic cylinder extend/retract force, velocity, and regeneration.

    For a double-acting cylinder:

      Piston area (full bore):  A_bore = π/4 × bore²
      Annulus area (rod side):  A_rod  = π/4 × (bore² - rod²)

    Extend stroke (pressure on bore side):
        F_extend  = pressure × A_bore
        v_extend  = flow / A_bore

    Retract stroke (pressure on rod side, bore vents):
        F_retract = pressure × A_rod
        v_retract = flow / A_rod

    Regenerative (regen=True) — bore-side return oil is routed to the inlet:
        effective area = A_bore - A_rod = A_rod_area  (net = rod area)
        F_regen  = pressure × A_rod  (same force as retract)
        v_regen  = flow / A_rod      (same velocity as retract, but faster
                                       than standard extend when rod is large)
        Note: in practice F_regen < F_extend and v_regen > v_extend.

    Parameters
    ----------
    bore_m     : float — cylinder bore diameter (m). Must be > 0.
    rod_m      : float — piston rod diameter (m). Must be > 0 and < bore.
    pressure_Pa: float — supply pressure (Pa). Must be > 0.
    flow_m3s   : float — supply flow rate (m³/s). Must be > 0.
    regen      : bool  — True to compute regenerative extend mode.

    Returns
    -------
    dict (ok=True)
        bore_m, rod_m, pressure_Pa, flow_m3s
        A_bore_m2, A_rod_m2       — piston and annulus areas (m²)
        F_extend_N                — extend force (N)
        F_retract_N               — retract force (N)
        v_extend_ms               — extend velocity (m/s)
        v_retract_ms              — retract velocity (m/s)
        F_regen_N                 — regen extend force (N) [same as F_retract]
        v_regen_ms                — regen extend velocity (m/s)
        regen_active              — whether regen mode was requested
        warnings                  — list of warning strings
    """
    e = _guard_pos("bore_m", bore_m)
    if e:
        return _err(e)
    e = _guard_pos("rod_m", rod_m)
    if e:
        return _err(e)
    e = _guard_pos("pressure_Pa", pressure_Pa)
    if e:
        return _err(e)
    e = _guard_pos("flow_m3s", flow_m3s)
    if e:
        return _err(e)

    D = float(bore_m)
    d = float(rod_m)
    P = float(pressure_Pa)
    Q = float(flow_m3s)

    if d >= D:
        return _err(f"rod_m ({d}) must be < bore_m ({D})")

    A_bore = math.pi / 4.0 * D ** 2
    A_rod  = math.pi / 4.0 * (D ** 2 - d ** 2)
    A_regen = A_bore - A_rod  # = π/4 × d² (rod cross-section area)

    F_extend  = P * A_bore
    F_retract = P * A_rod
    v_extend  = Q / A_bore
    v_retract = Q / A_rod

    # Regen mode: net effective area = rod cross-section (A_regen)
    F_regen = P * A_regen
    v_regen = Q / A_regen if A_regen > 0 else float("inf")

    warns: list[str] = []

    # Check rod area ratio for regen practicality (rod/bore > 0.7 is unusual)
    area_ratio = A_rod / A_bore
    if area_ratio < 0.2:
        warns.append(
            f"Area ratio A_rod/A_bore={area_ratio:.3f} < 0.20: "
            "retract force may be insufficient for load"
        )

    if regen and F_regen < 0.5 * F_extend:
        warns.append(
            f"Regen extend force ({F_regen:.0f} N) < 50% of standard extend "
            f"({F_extend:.0f} N); verify load requirements"
        )

    result = _ok(
        bore_m=D,
        rod_m=d,
        pressure_Pa=P,
        flow_m3s=Q,
        A_bore_m2=A_bore,
        A_rod_m2=A_rod,
        F_extend_N=F_extend,
        F_retract_N=F_retract,
        v_extend_ms=v_extend,
        v_retract_ms=v_retract,
        F_regen_N=F_regen,
        v_regen_ms=v_regen,
        regen_active=bool(regen),
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 2. pump
# ---------------------------------------------------------------------------

def pump(
    displacement_m3: float,
    rpm: float,
    vol_eff: float,
    overall_eff: float,
    pressure_Pa: float,
) -> dict:
    """
    Hydraulic pump sizing: flow output and input power.

    Actual flow:
        Q_actual = D × n × η_v           (m³/rev × rev/s × vol-eff)

    Input shaft power:
        P_input = (P_supply × Q_actual) / η_overall

    Also reports theoretical torque input:
        T_input = D × ΔP / (2π × η_mech)
    where η_mech = η_overall / η_v  (mechanical efficiency isolated).

    Parameters
    ----------
    displacement_m3 : float — pump displacement per revolution (m³/rev). > 0.
    rpm             : float — shaft rotational speed (rpm). > 0.
    vol_eff         : float — volumetric efficiency η_v in (0, 1]. Typical 0.85–0.98.
    overall_eff     : float — overall efficiency η_overall in (0, 1]. Typical 0.80–0.92.
    pressure_Pa     : float — system supply pressure (Pa). > 0.

    Returns
    -------
    dict (ok=True)
        displacement_m3, rpm, vol_eff, overall_eff, pressure_Pa
        Q_theoretical_m3s — theoretical (no-loss) flow (m³/s)
        Q_actual_m3s      — actual flow = D × n [rev/s] × η_v
        P_hydraulic_W     — hydraulic power P × Q_actual
        P_input_W         — required shaft input power
        T_input_Nm        — input shaft torque (N·m)
        mech_eff          — isolated mechanical efficiency η_m = η_overall/η_v
        warnings
    """
    e = _guard_pos("displacement_m3", displacement_m3)
    if e:
        return _err(e)
    e = _guard_pos("rpm", rpm)
    if e:
        return _err(e)
    e = _guard_frac("vol_eff", vol_eff)
    if e:
        return _err(e)
    e = _guard_frac("overall_eff", overall_eff)
    if e:
        return _err(e)
    e = _guard_pos("pressure_Pa", pressure_Pa)
    if e:
        return _err(e)

    D   = float(displacement_m3)
    n   = float(rpm) / 60.0          # rev/s
    ev  = float(vol_eff)
    eta = float(overall_eff)
    P   = float(pressure_Pa)

    Q_theoretical = D * n
    Q_actual      = Q_theoretical * ev
    P_hydraulic   = P * Q_actual
    P_input       = P_hydraulic / eta

    # Mechanical efficiency isolated: η_m = η_overall / η_v
    eta_m = eta / ev

    # Input torque: T = D × ΔP / (2π × η_m)
    T_input = (D * P) / (2.0 * math.pi * eta_m)

    warns: list[str] = []
    if vol_eff < 0.80:
        warns.append(
            f"Volumetric efficiency {vol_eff:.2f} < 0.80: "
            "pump may be worn or under-sized; check leakage path"
        )
    if overall_eff < 0.75:
        warns.append(
            f"Overall efficiency {overall_eff:.2f} < 0.75: "
            "check for excessive mechanical friction or wear"
        )
    # Pressure > 350 bar is beyond typical industrial rated pressure
    if P > 35e6:
        warns.append(
            f"Pressure {P/1e6:.1f} MPa > 35 MPa: verify pump pressure rating"
        )

    result = _ok(
        displacement_m3=D,
        rpm=float(rpm),
        vol_eff=ev,
        overall_eff=eta,
        mech_eff=eta_m,
        pressure_Pa=P,
        Q_theoretical_m3s=Q_theoretical,
        Q_actual_m3s=Q_actual,
        P_hydraulic_W=P_hydraulic,
        P_input_W=P_input,
        T_input_Nm=T_input,
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 3. motor
# ---------------------------------------------------------------------------

def motor(
    displacement_m3: float,
    pressure_Pa: float,
    rpm: float,
    *,
    mech_eff: float = 0.92,
    vol_eff: float = 0.95,
) -> dict:
    """
    Hydraulic motor: output torque and speed from displacement and pressure.

    Output torque:
        T_out = D × ΔP × η_m / (2π)

    Theoretical flow required (to sustain rpm):
        Q_theoretical = D × n   (rev/s × m³/rev)

    Actual flow required (accounting for internal leakage):
        Q_actual = Q_theoretical / η_v

    Output shaft power:
        P_out = T_out × ω  = T_out × 2π × n

    Parameters
    ----------
    displacement_m3 : float — motor displacement (m³/rev). > 0.
    pressure_Pa     : float — differential pressure across motor (Pa). > 0.
    rpm             : float — desired output shaft speed (rpm). > 0.
    mech_eff        : float — mechanical efficiency η_m in (0, 1]. Default 0.92.
    vol_eff         : float — volumetric efficiency η_v in (0, 1]. Default 0.95.

    Returns
    -------
    dict (ok=True)
        displacement_m3, pressure_Pa, rpm, mech_eff, vol_eff
        T_output_Nm         — output shaft torque (N·m)
        T_theoretical_Nm    — no-loss torque (η_m = 1)
        Q_theoretical_m3s   — theoretical flow consumed (m³/s)
        Q_actual_m3s        — actual flow consumed (accounting for leakage)
        P_output_W          — output shaft power (W)
        omega_rad_s         — angular velocity (rad/s)
        warnings
    """
    e = _guard_pos("displacement_m3", displacement_m3)
    if e:
        return _err(e)
    e = _guard_pos("pressure_Pa", pressure_Pa)
    if e:
        return _err(e)
    e = _guard_pos("rpm", rpm)
    if e:
        return _err(e)
    e = _guard_frac("mech_eff", mech_eff)
    if e:
        return _err(e)
    e = _guard_frac("vol_eff", vol_eff)
    if e:
        return _err(e)

    D  = float(displacement_m3)
    P  = float(pressure_Pa)
    n  = float(rpm) / 60.0     # rev/s
    em = float(mech_eff)
    ev = float(vol_eff)

    T_theoretical = D * P / (2.0 * math.pi)
    T_output      = T_theoretical * em

    Q_theoretical = D * n
    Q_actual      = Q_theoretical / ev

    omega   = 2.0 * math.pi * n
    P_output = T_output * omega

    warns: list[str] = []
    if mech_eff < 0.85:
        warns.append(
            f"Motor mechanical efficiency {mech_eff:.2f} < 0.85: "
            "verify motor sizing and condition"
        )

    result = _ok(
        displacement_m3=D,
        pressure_Pa=P,
        rpm=float(rpm),
        mech_eff=em,
        vol_eff=ev,
        T_theoretical_Nm=T_theoretical,
        T_output_Nm=T_output,
        Q_theoretical_m3s=Q_theoretical,
        Q_actual_m3s=Q_actual,
        omega_rad_s=omega,
        P_output_W=P_output,
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 4. accumulator
# ---------------------------------------------------------------------------

def accumulator(
    V_total_m3: float,
    P1_Pa: float,
    P2_Pa: float,
    P3_Pa: float,
    *,
    process: str = "isothermal",
) -> dict:
    """
    Gas-charged accumulator sizing using Boyle's Law.

    Notation (Parker/Vickers convention):
        P1 — gas pre-charge pressure (Pa)  [must be set; this is what we solve for
             when V_total is known, or v.v.]
        P2 — minimum system working pressure (Pa)  [gas fully expanded at V_total]
        P3 — maximum system pressure (Pa)          [gas compressed to V_min]

    Pre-charge rule:  P1 ≤ 0.9 × P2  (ISO/Parker recommendation)

    Usable (delivered) fluid volume:
        ΔV = V_total × (P1/P2 - P1/P3)   for isothermal (Boyle's law)
        ΔV = V_total × (P1/P2)^(1/n) - V_total × (P1/P3)^(1/n)
             where n=1.4 for adiabatic (isentropic, fast cycling)

    Alternatively, given ΔV required, total accumulator volume required:
        V_total = ΔV / ((P1/P2)^(1/n) - (P1/P3)^(1/n))

    This function takes all four parameters as given; it computes:
      - usable volume ΔV from V_total, P1, P2, P3
      - equivalent required V_total to deliver ΔV fluid (cross-check)
      - pre-charge compliance flag

    Parameters
    ----------
    V_total_m3 : float — total gas volume of accumulator (m³). > 0.
    P1_Pa      : float — gas pre-charge pressure (Pa). > 0.
    P2_Pa      : float — minimum working pressure (Pa). > P1.
    P3_Pa      : float — maximum working pressure (Pa). > P2.
    process    : str   — "isothermal" (Boyle, n=1, slow cycling, default)
                          or "adiabatic" (isentropic, n=1.4, fast cycling).

    Returns
    -------
    dict (ok=True)
        V_total_m3, P1_Pa, P2_Pa, P3_Pa, process
        n_exponent          — polytropic exponent (1.0 or 1.4)
        V_gas_at_P2_m3      — gas volume at P2 (= V_total, fully expanded)
        V_gas_at_P3_m3      — gas volume at P3 (compressed state)
        delta_V_m3          — usable/delivered fluid volume (m³)
        delta_V_L           — usable volume in litres
        precharge_ok        — True if P1 <= 0.9 × P2
        precharge_ratio     — P1 / P2
        warnings
    """
    e = _guard_pos("V_total_m3", V_total_m3)
    if e:
        return _err(e)
    e = _guard_pos("P1_Pa", P1_Pa)
    if e:
        return _err(e)
    e = _guard_pos("P2_Pa", P2_Pa)
    if e:
        return _err(e)
    e = _guard_pos("P3_Pa", P3_Pa)
    if e:
        return _err(e)

    V  = float(V_total_m3)
    P1 = float(P1_Pa)
    P2 = float(P2_Pa)
    P3 = float(P3_Pa)

    if P2 <= P1:
        return _err(
            f"P2_Pa ({P2:.0f}) must be > P1_Pa ({P1:.0f}) "
            "(minimum working pressure must exceed pre-charge)"
        )
    if P3 <= P2:
        return _err(
            f"P3_Pa ({P3:.0f}) must be > P2_Pa ({P2:.0f}) "
            "(maximum pressure must exceed minimum working pressure)"
        )

    proc = str(process).strip().lower()
    if proc not in ("isothermal", "adiabatic"):
        return _err(
            f"process must be 'isothermal' or 'adiabatic', got {process!r}"
        )

    n = 1.0 if proc == "isothermal" else 1.4

    # V_gas at P2 = V_total (fully expanded — accumulator fully charged with fluid)
    V_at_P2 = V

    # Gas volume at P3 via polytropic: P1×V1^n = P3×V3^n → V3 = V1×(P1/P3)^(1/n)
    # At P2 (fully expanded): V2 = V_total, so P1×V_precharge^n = P2×V2^n
    # Solve: V_precharge = V2 × (P2/P1)^(1/n)  — this is the gas volume at pre-charge state.
    # But for accumulator sizing the conventional formulas use:
    #   Boyle: P1·V_precharge = P2·V2 = P3·V3
    #   So V3 = P2·V2 / P3  (isothermal)
    #      ΔV = V2 - V3 = V2 × (1 - P2/P3)
    # BUT we must also ensure gas doesn't exceed V_total:
    #   V2 = V_total (gas fully expanded at minimum pressure P2)
    #   V_precharge = V2 × P2/P1 > V_total (pre-charge volume if unconstrained)
    #   → since V_precharge > V_total, actual accumulator must be sized so V_total
    #     accommodates the pre-charge gas at P1.
    # Standard practice: V_total is the physical shell volume.
    #   At P1 (pre-charge, no fluid): gas = V_total  ← shell is gas-filled
    #   At P2 (min working): P1×V_total = P2×V2 → V2 = P1×V_total/P2
    #   At P3 (max working): P1×V_total = P3×V3 → V3 = P1×V_total/P3
    #   ΔV = V2 - V3 = P1×V_total × (1/P2 - 1/P3)

    # Polytropic generalisation:
    #   P1^(1/n) × V_total = P2^(1/n) × V2  → V2 = V_total × (P1/P2)^(1/n)
    #   ΔV = V2 - V3 = V_total × [(P1/P2)^(1/n) - (P1/P3)^(1/n)]

    V_at_P2_actual = V * (P1 / P2) ** (1.0 / n)
    V_at_P3        = V * (P1 / P3) ** (1.0 / n)
    delta_V        = V_at_P2_actual - V_at_P3

    precharge_ratio = P1 / P2
    precharge_ok    = precharge_ratio <= 0.90

    warns: list[str] = []
    if not precharge_ok:
        warns.append(
            f"Pre-charge ratio P1/P2 = {precharge_ratio:.3f} > 0.90: "
            "ISO/Parker recommendation is P1 ≤ 0.90 × P2; "
            "reduce P1 or increase P2 to avoid cavitation at minimum pressure"
        )
    if delta_V <= 0:
        warns.append(
            "Usable volume delta_V <= 0: check that P2 < P3 with adequate spread"
        )
    if V_at_P3 / V < 0.05:
        warns.append(
            f"Gas volume at P3 ({V_at_P3*1000:.2f} L) is < 5% of shell volume: "
            "pressure ratio P3/P1 is very high; consider larger accumulator"
        )

    result = _ok(
        V_total_m3=V,
        P1_Pa=P1,
        P2_Pa=P2,
        P3_Pa=P3,
        process=proc,
        n_exponent=n,
        V_gas_at_P2_m3=V_at_P2_actual,
        V_gas_at_P3_m3=V_at_P3,
        delta_V_m3=delta_V,
        delta_V_L=delta_V * 1000.0,
        precharge_ratio=precharge_ratio,
        precharge_ok=precharge_ok,
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 5. valve_cv
# ---------------------------------------------------------------------------

def valve_cv(
    Q_m3s: float,
    delta_P_Pa: float,
    SG: float,
    *,
    metric: bool = False,
) -> dict:
    """
    Valve sizing via flow coefficient Cv (US) or Kv (metric).

    US Cv formula (liquid, fully open, turbulent flow):
        Q [gpm] = Cv × √(ΔP [psi] / SG)
        → Cv = Q_gpm / √(ΔP_psi / SG)

    Metric Kv formula (ISO 6358 / DIN 2400):
        Q [m³/h] = Kv × √(ΔP [bar] / SG)
        → Kv = Q_m3h / √(ΔP_bar / SG)

    Relationship: Cv ≈ Kv × 1.15626  (rounded from exact 1/√(0.0138/0.0160))

    Parameters
    ----------
    Q_m3s      : float — volumetric flow rate (m³/s). > 0.
    delta_P_Pa : float — pressure drop across valve at full-open (Pa). > 0.
    SG         : float — specific gravity of fluid relative to water. > 0.
    metric     : bool  — True → report Kv (m³/h, bar); False (default) → Cv (gpm, psi).

    Returns
    -------
    dict (ok=True)
        Q_m3s, delta_P_Pa, SG
        Q_gpm       — flow in US gal/min
        Q_m3h       — flow in m³/h
        delta_P_psi — pressure drop in psi
        delta_P_bar — pressure drop in bar
        Cv          — US flow coefficient
        Kv          — metric flow coefficient (m³/h per √bar)
        primary     — "Cv" or "Kv" depending on `metric` flag
        warnings
    """
    e = _guard_pos("Q_m3s", Q_m3s)
    if e:
        return _err(e)
    e = _guard_pos("delta_P_Pa", delta_P_Pa)
    if e:
        return _err(e)
    e = _guard_pos("SG", SG)
    if e:
        return _err(e)

    Q  = float(Q_m3s)
    dP = float(delta_P_Pa)
    sg = float(SG)

    Q_gpm  = Q * _M3S_TO_GPM
    dP_psi = dP * _PA_TO_PSI
    Q_m3h  = Q * _M3S_TO_M3H
    dP_bar = dP * _PA_TO_BAR

    # Cv = Q_gpm / √(ΔP_psi / SG)
    Cv = Q_gpm / math.sqrt(dP_psi / sg)

    # Kv = Q_m3h / √(ΔP_bar / SG)
    Kv = Q_m3h / math.sqrt(dP_bar / sg)

    warns: list[str] = []
    # Very high ΔP across a single valve (>50% of system pressure) may indicate
    # the valve is throttling excessively — flag if ΔP > 5 MPa
    if dP > 5e6:
        warns.append(
            f"Valve ΔP {dP/1e6:.1f} MPa is high; consider pressure-reducing valve "
            "or multi-stage throttling to reduce heat generation"
        )
    if sg < 0.5 or sg > 2.0:
        warns.append(
            f"Specific gravity SG={sg:.2f} is outside typical hydraulic fluid range "
            "(0.85–0.90); verify fluid properties"
        )

    result = _ok(
        Q_m3s=Q,
        delta_P_Pa=dP,
        SG=sg,
        Q_gpm=Q_gpm,
        Q_m3h=Q_m3h,
        delta_P_psi=dP_psi,
        delta_P_bar=dP_bar,
        Cv=Cv,
        Kv=Kv,
        primary="Kv" if metric else "Cv",
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 6. line_pressure_drop
# ---------------------------------------------------------------------------

def line_pressure_drop(
    Q_m3s: float,
    rho: float,
    mu: float,
    D_i_m: float,
    L_m: float,
    *,
    roughness_m: float = 4.6e-5,    # commercial steel roughness (m)
    fittings_Le_m: float = 0.0,
) -> dict:
    """
    Hydraulic line pressure drop (Darcy-Weisbach / Hagen-Poiseuille).

    Flow regime:
        Re = ρ × v × D / μ

        Re < 2300  → laminar: Hagen-Poiseuille
            ΔP = 128 × μ × L × Q / (π × D⁴)
            f  = 64 / Re

        Re ≥ 2300  → turbulent: Darcy-Weisbach with Colebrook-White
            ΔP = f × (L_total / D) × (ρ × v² / 2)
            Colebrook-White: 1/√f = -2·log₁₀(ε/(3.7D) + 2.51/(Re·√f))
            Solved by Swamee-Jain explicit approximation.

    Parameters
    ----------
    Q_m3s        : float — volumetric flow (m³/s). > 0.
    rho          : float — fluid density (kg/m³). > 0.
    mu           : float — dynamic viscosity (Pa·s). > 0.
    D_i_m        : float — internal pipe diameter (m). > 0.
    L_m          : float — pipe length (m). > 0.
    roughness_m  : float — absolute pipe wall roughness (m). Default 4.6e-5 (steel).
    fittings_Le_m: float — equivalent length of fittings (m). Default 0.

    Returns
    -------
    dict (ok=True)
        Q_m3s, rho, mu, D_i_m, L_m, roughness_m, fittings_Le_m
        velocity_ms     — mean flow velocity (m/s)
        Re              — Reynolds number
        regime          — "laminar" or "turbulent"
        f_darcy         — Darcy friction factor
        L_total_m       — effective length including fittings equivalent length
        delta_P_Pa      — total pressure drop (Pa)
        delta_P_bar     — total pressure drop (bar)
        warnings
    """
    e = _guard_pos("Q_m3s", Q_m3s)
    if e:
        return _err(e)
    e = _guard_pos("rho", rho)
    if e:
        return _err(e)
    e = _guard_pos("mu", mu)
    if e:
        return _err(e)
    e = _guard_pos("D_i_m", D_i_m)
    if e:
        return _err(e)
    e = _guard_pos("L_m", L_m)
    if e:
        return _err(e)
    e = _guard_nonneg("roughness_m", roughness_m)
    if e:
        return _err(e)
    e = _guard_nonneg("fittings_Le_m", fittings_Le_m)
    if e:
        return _err(e)

    Q   = float(Q_m3s)
    rho_ = float(rho)
    mu_  = float(mu)
    D   = float(D_i_m)
    L   = float(L_m)
    eps = float(roughness_m)
    L_f = float(fittings_Le_m)

    A   = math.pi / 4.0 * D ** 2
    v   = Q / A
    Re  = rho_ * v * D / mu_
    L_total = L + L_f

    warns: list[str] = []

    rel_rough = eps / D
    f = darcy_friction_factor(Re, rel_rough)
    dP = f * (L_total / D) * (rho_ * v ** 2 / 2.0)
    if Re < 2300:
        regime = "laminar"
    else:
        regime = "turbulent"

    # Velocity warnings
    # Suction lines should be ≤ 1.5 m/s; pressure lines ≤ 6 m/s
    if v > 6.0:
        warns.append(
            f"Line velocity {v:.2f} m/s > 6.0 m/s: erosion and noise risk; "
            "increase bore diameter"
        )
    elif v > 4.0:
        warns.append(
            f"Line velocity {v:.2f} m/s > 4.0 m/s: check for pressure-line service"
        )

    result = _ok(
        Q_m3s=Q,
        rho=rho_,
        mu=mu_,
        D_i_m=D,
        L_m=L,
        roughness_m=eps,
        fittings_Le_m=L_f,
        velocity_ms=v,
        Re=Re,
        regime=regime,
        f_darcy=f,
        L_total_m=L_total,
        delta_P_Pa=dP,
        delta_P_bar=dP * _PA_TO_BAR,
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 7. line_size
# ---------------------------------------------------------------------------

def line_size(
    Q_m3s: float,
    *,
    service: str = "pressure",
    fluid_rho: float = 870.0,     # typical hydraulic oil kg/m³
    fluid_mu: float  = 0.046,     # ISO VG 46 at 40°C in Pa·s
) -> dict:
    """
    Recommended hydraulic line internal diameter from ISO velocity limits.

    Recommended velocity limits (Vickers / Parker guidance):
        suction  lines: 0.5 – 1.5 m/s  (avoid pump cavitation)
        return   lines: 2.0 – 4.0 m/s
        pressure lines: 3.0 – 6.0 m/s

    Minimum bore:
        D_min = √(4Q / (π × v_max))

    Recommended bore:
        D_rec = √(4Q / (π × v_rec))
        where v_rec = (v_min + v_max) / 2

    Parameters
    ----------
    Q_m3s     : float — flow rate (m³/s). > 0.
    service   : str   — "suction", "return", or "pressure" (default).
    fluid_rho : float — fluid density (kg/m³). Default 870 (ISO VG46 oil).
    fluid_mu  : float — dynamic viscosity (Pa·s). Default 0.046 (VG46 at 40°C).

    Returns
    -------
    dict (ok=True)
        Q_m3s, service, fluid_rho, fluid_mu
        v_min_ms            — minimum recommended velocity (m/s)
        v_max_ms            — maximum recommended velocity (m/s)
        D_min_m             — minimum bore for v_max (m)
        D_min_mm            — minimum bore (mm)
        D_rec_m             — recommended bore at mid-range velocity (m)
        D_rec_mm            — recommended bore (mm)
        Re_at_D_rec         — Reynolds number at recommended bore
        regime_at_D_rec     — "laminar" or "turbulent"
        warnings
    """
    e = _guard_pos("Q_m3s", Q_m3s)
    if e:
        return _err(e)
    e = _guard_pos("fluid_rho", fluid_rho)
    if e:
        return _err(e)
    e = _guard_pos("fluid_mu", fluid_mu)
    if e:
        return _err(e)

    svc = str(service).strip().lower()
    if svc not in _VEL_LIMITS:
        return _err(
            f"service must be one of {list(_VEL_LIMITS.keys())}, got {service!r}"
        )

    v_min, v_max = _VEL_LIMITS[svc]
    v_rec = (v_min + v_max) / 2.0

    Q = float(Q_m3s)

    # D = √(4Q / (π × v))
    D_min = math.sqrt(4.0 * Q / (math.pi * v_max))
    D_rec = math.sqrt(4.0 * Q / (math.pi * v_rec))

    rho = float(fluid_rho)
    mu  = float(fluid_mu)

    # Re at recommended diameter
    v_at_Drec = Q / (math.pi / 4.0 * D_rec ** 2)  # ≈ v_rec by construction
    Re_rec = rho * v_at_Drec * D_rec / mu
    regime_rec = "laminar" if Re_rec < 2300 else "turbulent"

    warns: list[str] = []
    if svc == "suction" and Q / (math.pi / 4.0 * D_min ** 2) > _VEL_CAVITATION:
        warns.append(
            f"Suction line velocity at minimum bore exceeds {_VEL_CAVITATION} m/s: "
            "cavitation risk; use larger bore or reduce pump speed"
        )

    result = _ok(
        Q_m3s=Q,
        service=svc,
        fluid_rho=rho,
        fluid_mu=mu,
        v_min_ms=v_min,
        v_max_ms=v_max,
        D_min_m=D_min,
        D_min_mm=D_min * 1000.0,
        D_rec_m=D_rec,
        D_rec_mm=D_rec * 1000.0,
        Re_at_D_rec=Re_rec,
        regime_at_D_rec=regime_rec,
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 8. reservoir
# ---------------------------------------------------------------------------

def reservoir(
    pump_flow_m3s: float,
    *,
    rule_factor: float = 3.0,
) -> dict:
    """
    Hydraulic reservoir volume rule-of-thumb.

    Industry rule: V_reservoir ≥ rule_factor × Q_pump_per_minute

    Typical rule_factor values:
        3  — standard industrial (Vickers manual §8)
        5  — high-duty or contamination-sensitive systems
        1  — emergency/compact mobile where space is critical (minimum)

    This is a gross-sizing guideline only; thermal balance should be checked
    separately (see thermal_balance).

    Parameters
    ----------
    pump_flow_m3s : float — total pump flow rate (m³/s). > 0.
    rule_factor   : float — V = factor × Q_per_min. Default 3.0. Must be > 0.

    Returns
    -------
    dict (ok=True)
        pump_flow_m3s
        pump_flow_Lmin     — pump flow (L/min)
        rule_factor
        V_reservoir_m3     — recommended reservoir volume (m³)
        V_reservoir_L      — recommended reservoir volume (litres)
        warnings
    """
    e = _guard_pos("pump_flow_m3s", pump_flow_m3s)
    if e:
        return _err(e)
    e = _guard_pos("rule_factor", rule_factor)
    if e:
        return _err(e)

    Q   = float(pump_flow_m3s)
    rf  = float(rule_factor)
    Q_Lmin = Q * 1000.0 * 60.0  # m³/s → L/min

    V_m3 = rf * (Q * 60.0)      # rule_factor × Q [m³/min]
    V_L  = V_m3 * 1000.0

    warns: list[str] = []
    if rf < 2.0:
        warns.append(
            f"rule_factor={rf:.1f} < 2.0: reservoir may be under-sized; "
            "check thermal balance and contamination settling time"
        )
    if rf > 10.0:
        warns.append(
            f"rule_factor={rf:.1f} > 10.0: unusually large reservoir; "
            "verify this is intentional (e.g., thermal buffer)"
        )

    result = _ok(
        pump_flow_m3s=Q,
        pump_flow_Lmin=Q_Lmin,
        rule_factor=rf,
        V_reservoir_m3=V_m3,
        V_reservoir_L=V_L,
    )
    result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 9. thermal_balance
# ---------------------------------------------------------------------------

def thermal_balance(
    input_power_W: float,
    eff_overall: float,
    *,
    area_m2: float | None    = None,
    U_Wm2K: float            = 10.0,
    dT_K: float              = 40.0,
    cooling_flow_m3s: float | None = None,
    fluid_cp: float          = 1880.0,   # J/(kg·K) for mineral oil
    fluid_rho: float         = 870.0,    # kg/m³
) -> dict:
    """
    Steady-state hydraulic system heat load and thermal-balance check.

    Heat generated (losses):
        Q_heat = P_input × (1 - η_overall)    [W]

    Reservoir surface cooling (natural convection, simplified):
        Q_dissipated_surface = U × A × ΔT     [W]
        where U ≈ 10 W/(m²·K) for unpainted steel reservoir (still air)

    Auxiliary heat exchanger (liquid cooling):
        Q_cooler = ṁ_cool × cp × ΔT
                 = rho × Q_cool × cp × ΔT

    Thermal balance:
        System is thermally balanced when:
          Q_heat ≤ Q_dissipated_surface + Q_cooler

    Parameters
    ----------
    input_power_W    : float — shaft input power to pump (W). > 0.
    eff_overall      : float — overall system efficiency (0, 1]. Losses generate heat.
    area_m2          : float | None — reservoir surface area (m²). None → skip surface calc.
    U_Wm2K           : float — overall heat-transfer coefficient (W/(m²·K)). Default 10.
    dT_K             : float — temperature rise above ambient (K). Default 40 K.
    cooling_flow_m3s : float | None — auxiliary cooler fluid flow (m³/s). None → no cooler.
    fluid_cp         : float — cooler fluid specific heat J/(kg·K). Default 1880 (mineral oil).
    fluid_rho        : float — cooler fluid density kg/m³. Default 870.

    Returns
    -------
    dict (ok=True)
        input_power_W, eff_overall
        Q_heat_W               — heat generated by losses (W)
        Q_surface_W            — heat dissipated by reservoir surface (W; 0 if area_m2 None)
        Q_cooler_W             — heat removed by auxiliary cooler (W; 0 if cooling_flow None)
        Q_total_dissipated_W   — total heat dissipated (W)
        thermal_balanced       — True if Q_heat <= Q_total_dissipated
        heat_surplus_W         — Q_total_dissipated - Q_heat (positive = surplus capacity)
        warnings
    """
    e = _guard_pos("input_power_W", input_power_W)
    if e:
        return _err(e)
    e = _guard_frac("eff_overall", eff_overall)
    if e:
        return _err(e)
    e = _guard_pos("U_Wm2K", U_Wm2K)
    if e:
        return _err(e)
    e = _guard_pos("dT_K", dT_K)
    if e:
        return _err(e)
    e = _guard_pos("fluid_cp", fluid_cp)
    if e:
        return _err(e)
    e = _guard_pos("fluid_rho", fluid_rho)
    if e:
        return _err(e)

    if area_m2 is not None:
        e = _guard_pos("area_m2", area_m2)
        if e:
            return _err(e)
    if cooling_flow_m3s is not None:
        e = _guard_pos("cooling_flow_m3s", cooling_flow_m3s)
        if e:
            return _err(e)

    P_in   = float(input_power_W)
    eta    = float(eff_overall)
    U      = float(U_Wm2K)
    dT     = float(dT_K)
    cp     = float(fluid_cp)
    rho_f  = float(fluid_rho)

    Q_heat   = P_in * (1.0 - eta)

    Q_surface = 0.0
    if area_m2 is not None:
        Q_surface = U * float(area_m2) * dT

    Q_cooler = 0.0
    if cooling_flow_m3s is not None:
        mdot = rho_f * float(cooling_flow_m3s)
        Q_cooler = mdot * cp * dT

    Q_total_dissipated = Q_surface + Q_cooler
    heat_surplus = Q_total_dissipated - Q_heat
    thermal_ok   = heat_surplus >= 0.0

    warns: list[str] = []
    if not thermal_ok:
        warns.append(
            f"System NOT thermally balanced: heat generated {Q_heat:.0f} W > "
            f"heat dissipated {Q_total_dissipated:.0f} W; "
            "add/enlarge heat exchanger or improve reservoir surface cooling"
        )
    if dT > 60.0:
        warns.append(
            f"Temperature rise dT_K={dT:.0f} K > 60 K: "
            "fluid degradation and seal damage risk above ~70°C operating temperature"
        )
    if eff_overall < 0.70:
        warns.append(
            f"Overall system efficiency {eta:.2f} < 0.70: "
            "excessive losses; audit pump, motor, valve, and line sizing"
        )

    result = _ok(
        input_power_W=P_in,
        eff_overall=eta,
        dT_K=dT,
        Q_heat_W=Q_heat,
        Q_surface_W=Q_surface,
        Q_cooler_W=Q_cooler,
        Q_total_dissipated_W=Q_total_dissipated,
        thermal_balanced=thermal_ok,
        heat_surplus_W=heat_surplus,
    )
    result["warnings"] = warns
    return result
