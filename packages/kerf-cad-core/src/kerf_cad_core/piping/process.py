"""
kerf_cad_core.piping.process — ASME B31.3 process piping engineering calculations.

Implements seven public functions:

  required_wall_thickness(P, D, S, E, W, Y, c_corr, c_mill)
      Minimum required wall thickness per ASME B31.3 Eq. 3a:
          t = P·D / (2·(S·E·W + P·Y)) + c_corr + c_mill

  pressure_drop(Q, rho, mu, D_i, L, roughness, fittings_Le)
      Single-phase Darcy-Weisbach pressure drop with Colebrook-White
      friction factor; fittings added as equivalent-length sum.

  allowable_span(D_o, D_i, rho_pipe, rho_fluid, E, S_allow, method)
      Maximum allowable support span limited by deflection or bending stress
      (the lesser), per MSS SP-69 / beam-on-two-supports approach.

  thermal_expansion(L, alpha, T_install, T_operating)
      Thermal-expansion free elongation ΔL = L·α·ΔT.

  guided_cantilever_leg(D_o, t, E, S_allow, delta)
      Minimum leg length for a guided-cantilever L-bend to absorb
      pipe displacement δ within allowable stress:
          L_leg = √(3·E·D_o·δ / (2·S_allow·(D_o - 2t)))  ... (simplified)
      Uses the pipe section modulus form: L_leg = √(3·E·I·δ / (S_allow·Z))

  expansion_stress_check(delta_x, delta_y, delta_z, L_x, L_y, E, D_o, t, S_allow)
      Simple two-anchor guided-cantilever expansion stress check for an
      L- or Z-shaped piping leg.  Returns computed stress and pass/fail.

  schedule_lookup(nominal_size_in, schedule)
      Look up pipe OD and wall thickness from ASME B36.10M / B36.19M tables
      for common nominal pipe sizes and schedules.

All functions return plain dicts:
    success → {"ok": True, ...fields...}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise; code-exceedance conditions issue warnings.warnings.warn
but still return ok=True with a "warnings" list in the payload.

Units
-----
  lengths      — metres (m)   unless noted (schedule_lookup returns mm)
  pressure     — Pascals (Pa)
  stress       — Pascals (Pa)
  flow rate    — m³/s
  density      — kg/m³
  viscosity    — Pa·s (dynamic)
  temperature  — °C
  CTE          — 1/°C

References
----------
ASME B31.3-2022 — Process Piping
ASME B36.10M-2018 — Welded and Seamless Wrought Steel Pipe
ASME B36.19M-2018 — Stainless Steel Pipe
Crane TP-410 — Flow of Fluids Through Valves, Fittings and Pipe
MSS SP-69 — Pipe Hangers and Supports
Shigley's Mechanical Engineering Design, 10th ed.

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive

from kerf_cad_core.fluids.friction import darcy_friction_factor


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_NPS_TABLE: dict[str, tuple[float, dict[str, float]]] = {
    # NPS: (OD_mm, {sch: wall_mm})
    "0.25": (13.7,  {"40": 2.24,  "80": 3.02,  "160": 3.73,  "XXS": 4.78}),
    "0.375":(17.1,  {"40": 2.31,  "80": 3.20,  "160": 4.55,  "XXS": 5.56}),
    "0.5":  (21.3,  {"40": 2.77,  "80": 3.73,  "160": 4.78,  "XXS": 7.47}),
    "0.75": (26.7,  {"40": 2.87,  "80": 3.91,  "160": 5.56,  "XXS": 7.82}),
    "1":    (33.4,  {"40": 3.38,  "80": 4.55,  "160": 6.35,  "XXS": 9.09}),
    "1.25": (42.2,  {"40": 3.56,  "80": 4.85,  "160": 6.35,  "XXS": 9.70}),
    "1.5":  (48.3,  {"40": 3.68,  "80": 5.08,  "160": 7.14,  "XXS": 10.16}),
    "2":    (60.3,  {"40": 3.91,  "80": 5.54,  "160": 8.74,  "XXS": 11.07}),
    "2.5":  (73.0,  {"40": 5.16,  "80": 7.01,  "160": 9.53,  "XXS": 14.02}),
    "3":    (88.9,  {"40": 5.49,  "80": 7.62,  "160": 11.13, "XXS": 15.24}),
    "4":    (114.3, {"40": 6.02,  "80": 8.56,  "120": 11.13, "160": 13.49, "XXS": 17.12}),
    "6":    (168.3, {"40": 7.11,  "80": 10.97, "120": 14.27, "160": 18.26, "XXS": 21.95}),
    "8":    (219.1, {"40": 8.18,  "80": 12.70, "100": 15.09, "120": 17.48, "160": 23.01, "XXS": 22.23}),
    "10":   (273.1, {"40": 9.27,  "80": 15.09, "100": 18.26, "120": 21.44, "160": 28.58}),
    "12":   (323.9, {"40": 9.53,  "80": 17.48, "100": 21.44, "120": 25.40, "160": 33.32}),
    "16":   (406.4, {"40": 9.53,  "80": 21.44, "100": 26.19, "120": 30.96, "160": 36.53}),
    "20":   (508.0, {"20": 9.53,  "40": 12.70, "60": 20.62, "80": 22.23,  "100": 28.58, "120": 34.93, "160": 44.45}),
    "24":   (609.6, {"20": 9.53,  "40": 14.27, "60": 24.61, "80": 30.96,  "100": 38.10, "120": 46.02, "160": 59.54}),
}


def schedule_lookup(nominal_size_in: str | float, schedule: str) -> dict:
    """
    Look up pipe OD and wall thickness from ASME B36.10M tables.

    Parameters
    ----------
    nominal_size_in : str or float
        Nominal pipe size in inches.  Supported: 0.5, 0.75, 1, 1.25, 1.5, 2,
        2.5, 3, 4, 6, 8, 10, 12, 16, 20, 24.
    schedule : str
        Pipe schedule string, e.g. "40", "80", "160", "XXS", "20", "100",
        "120".  Case-insensitive.

    Returns
    -------
    dict
        ok             : True
        nps_in         : NPS as string
        schedule       : schedule string (normalised)
        OD_mm          : outside diameter (mm)
        wall_mm        : wall thickness (mm)
        ID_mm          : inside diameter (mm)
        OD_m           : outside diameter (m)
        wall_m         : wall thickness (m)
        ID_m           : inside diameter (m)
    """
    key = str(nominal_size_in).strip()
    # Accept float-like keys: "1.0" → "1", "0.500" → "0.5"
    try:
        f = float(key)
        # Round-trip through common representations
        for candidate in (key, f"{f:g}", str(int(f)) if f == int(f) else None):
            if candidate and candidate in _NPS_TABLE:
                key = candidate
                break
    except ValueError:
        pass

    if key not in _NPS_TABLE:
        supported = list(_NPS_TABLE.keys())
        return _err(
            f"Nominal pipe size {nominal_size_in!r} not found in table. "
            f"Supported NPS (inches): {supported}"
        )

    od_mm, sch_map = _NPS_TABLE[key]
    sch_clean = str(schedule).strip().upper()
    if sch_clean not in sch_map:
        available = list(sch_map.keys())
        return _err(
            f"Schedule {schedule!r} not available for NPS {key} in. "
            f"Available: {available}"
        )

    wall_mm = sch_map[sch_clean]
    id_mm = od_mm - 2.0 * wall_mm

    return {
        "ok": True,
        "nps_in": key,
        "schedule": sch_clean,
        "OD_mm": od_mm,
        "wall_mm": wall_mm,
        "ID_mm": id_mm,
        "OD_m": od_mm * 1e-3,
        "wall_m": wall_mm * 1e-3,
        "ID_m": id_mm * 1e-3,
    }


# ---------------------------------------------------------------------------
# 1. required_wall_thickness
#    ASME B31.3-2022 Eq. (3a):
#        t_m = P·D / (2·(S·E_w·W + P·Y))
#    Then add mill tolerance and corrosion allowance:
#        t_req = t_m / (1 - mill_tol) + c_corr   (mill_tol as fraction, e.g. 0.125)
# ---------------------------------------------------------------------------

# B31.3 Table 304.1.1 Y coefficient — for ferritic steels < 482 °C, Y = 0.4
_Y_DEFAULT = 0.4


def required_wall_thickness(
    P: float,
    D: float,
    S: float,
    E: float = 1.0,
    W: float = 1.0,
    Y: float = _Y_DEFAULT,
    c_corr: float = 0.0,
    c_mill: float = 0.0,
) -> dict:
    """
    Required pipe wall thickness per ASME B31.3 Eq. (3a).

    The formula gives the design (minimum) wall thickness, to which
    corrosion and mill-tolerance allowances are then added.

    Parameters
    ----------
    P : float
        Internal design pressure (Pa). Must be >= 0.
    D : float
        Outside diameter of the pipe (m). Must be > 0.
    S : float
        Allowable stress of the pipe material at design temperature (Pa).
        Must be > 0.  From ASME B31.3 Appendix A tables.
    E : float
        Longitudinal-joint quality factor (default 1.0, seamless).
        Typical values: 1.0 (seamless), 0.85 (ERW), 0.80 (furnace butt-weld).
        Must be in (0, 1].
    W : float
        Weld-joint strength reduction factor (default 1.0).
        Required for temps > 510 °C (950 °F); otherwise 1.0.
        Must be in (0, 1].
    Y : float
        B31.3 Table 304.1.1 Y coefficient (default 0.4 — ferritic/austenitic
        steels and nickel alloys below 482 °C (900 °F)).
        Other values: 0.4 for T < 482 °C, 0.5 for cast iron/non-metals.
        Must be in [0, 1).
    c_corr : float
        Corrosion/erosion allowance (m). Must be >= 0.  Commonly 1.5–3 mm
        for carbon steel in process service.
    c_mill : float
        Mill under-tolerance allowance as a thickness fraction (dimensionless).
        Typically 0.125 (12.5%) per ASTM A106.  Must be in [0, 1).
        The gross required wall = t_design / (1 - c_mill) + c_corr.

    Returns
    -------
    dict
        ok                  : True
        t_design_m          : design wall thickness from Eq. (3a) (m)
        t_required_m        : t_design / (1 - c_mill) + c_corr (m)
        t_required_mm       : same in mm
        P_Pa                : design pressure used (Pa)
        D_m                 : OD used (m)
        S_Pa                : allowable stress used (Pa)
        E_factor            : joint quality factor used
        W_factor            : weld strength factor used
        Y_factor            : Y coefficient used
        c_corr_m            : corrosion allowance used (m)
        c_mill_fraction     : mill tolerance fraction used
        warnings            : list of code-exceedance warning strings

    Formula (ASME B31.3 §304.1.2)
    --------------------------------
        t_m = P·D / (2·(S·E·W + P·Y))
        t_req = t_m / (1 - c_mill) + c_corr
    """
    warn_list: list[str] = []

    err = _guard_nonneg("P", P)
    if err:
        return _err(err)
    err = _guard_positive("D", D)
    if err:
        return _err(err)
    err = _guard_positive("S", S)
    if err:
        return _err(err)

    E_f = float(E)
    if not (0 < E_f <= 1.0):
        return _err(f"E (joint quality factor) must be in (0, 1], got {E_f}")
    W_f = float(W)
    if not (0 < W_f <= 1.0):
        return _err(f"W (weld strength reduction) must be in (0, 1], got {W_f}")
    Y_f = float(Y)
    if not (0 <= Y_f < 1.0):
        return _err(f"Y coefficient must be in [0, 1), got {Y_f}")

    err = _guard_nonneg("c_corr", c_corr)
    if err:
        return _err(err)

    c_mill_f = float(c_mill)
    if not (0 <= c_mill_f < 1.0):
        return _err(f"c_mill must be in [0, 1), got {c_mill_f}")

    P_v = float(P)
    D_v = float(D)
    S_v = float(S)
    c_corr_v = float(c_corr)

    denom = 2.0 * (S_v * E_f * W_f + P_v * Y_f)
    if denom <= 0:
        return _err("Denominator 2(SEW + PY) is non-positive — check inputs")

    t_design = P_v * D_v / denom
    t_required = t_design / (1.0 - c_mill_f) + c_corr_v

    # Code check: t_required must not exceed D/6 (thick-cylinder limit of eq)
    if t_required > D_v / 6.0:
        msg = (
            f"Required wall {t_required*1e3:.2f} mm exceeds D/6 = {D_v/6*1e3:.2f} mm. "
            "ASME B31.3 Eq. (3a) is not valid for thick cylinders; "
            "use the B31.3 thick-wall (high-pressure) formula."
        )
        warn_list.append(msg)
        warnings.warn(msg, stacklevel=2)

    return {
        "ok": True,
        "t_design_m": t_design,
        "t_required_m": t_required,
        "t_required_mm": t_required * 1e3,
        "P_Pa": P_v,
        "D_m": D_v,
        "S_Pa": S_v,
        "E_factor": E_f,
        "W_factor": W_f,
        "Y_factor": Y_f,
        "c_corr_m": c_corr_v,
        "c_mill_fraction": c_mill_f,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 2. pressure_drop — single-phase Darcy-Weisbach
#    ΔP = f · (L_eff / D_i) · (ρ · V² / 2)
#    Friction factor by Colebrook-White (iterative), seeded by Swamee-Jain.
# ---------------------------------------------------------------------------

# _colebrook is kept as a thin shim for any internal callers; it now delegates
# to the canonical darcy_friction_factor in kerf_cad_core.fluids.friction.
def _colebrook(Re: float, eps_D: float, max_iter: int = 50) -> float:
    """Darcy friction factor — delegates to canonical darcy_friction_factor."""
    return darcy_friction_factor(Re, eps_D)


def pressure_drop(
    Q: float,
    rho: float,
    mu: float,
    D_i: float,
    L: float,
    roughness: float = 46e-6,
    fittings_Le: float = 0.0,
) -> dict:
    """
    Single-phase Darcy-Weisbach pressure drop (Crane TP-410 / B31.3).

    Computes pressure drop for fully-developed turbulent or laminar flow
    in a circular pipe, including the contribution of fittings expressed
    as an equivalent pipe length.

    Parameters
    ----------
    Q : float
        Volumetric flow rate (m³/s). Must be > 0.
    rho : float
        Fluid density (kg/m³). Must be > 0.
    mu : float
        Dynamic viscosity (Pa·s). Must be > 0.
    D_i : float
        Pipe inside diameter (m). Must be > 0.
    L : float
        Straight pipe length (m). Must be >= 0.
    roughness : float
        Absolute pipe-wall roughness (m). Default 46×10⁻⁶ m
        (commercial steel per Moody).  Must be >= 0.
    fittings_Le : float
        Sum of equivalent lengths of all fittings and valves (m).
        Adds directly to L.  Must be >= 0.

    Returns
    -------
    dict
        ok              : True
        dP_Pa           : total pressure drop (Pa)
        dP_kPa          : same in kPa
        dP_bar          : same in bar
        velocity_m_s    : mean flow velocity (m/s)
        Re              : Reynolds number
        friction_factor : Darcy-Weisbach f
        flow_regime     : "laminar" | "turbulent" | "transition"
        L_eff_m         : effective pipe length (L + fittings_Le) (m)
        warnings        : list of code-exceedance warning strings

    Formula
    -------
        V   = Q / (π/4 · D_i²)
        Re  = ρ·V·D_i / μ
        f   = Colebrook-White(Re, ε/D)     [Darcy]
        ΔP  = f · (L_eff/D_i) · (ρ·V²/2)
    """
    warn_list: list[str] = []

    err = _guard_positive("Q", Q)
    if err:
        return _err(err)
    err = _guard_positive("rho", rho)
    if err:
        return _err(err)
    err = _guard_positive("mu", mu)
    if err:
        return _err(err)
    err = _guard_positive("D_i", D_i)
    if err:
        return _err(err)
    err = _guard_nonneg("L", L)
    if err:
        return _err(err)
    err = _guard_nonneg("roughness", roughness)
    if err:
        return _err(err)
    err = _guard_nonneg("fittings_Le", fittings_Le)
    if err:
        return _err(err)

    Q_v = float(Q)
    rho_v = float(rho)
    mu_v = float(mu)
    D_v = float(D_i)
    L_v = float(L)
    eps = float(roughness)
    Le = float(fittings_Le)

    A = math.pi / 4.0 * D_v ** 2
    V = Q_v / A
    Re = rho_v * V * D_v / mu_v
    eps_D = eps / D_v

    if Re < 2300.0:
        regime = "laminar"
    elif Re < 4000.0:
        regime = "transition"
        msg = f"Re = {Re:.0f} is in the transition zone (2300–4000); results are approximate."
        warn_list.append(msg)
        warnings.warn(msg, stacklevel=2)
    else:
        regime = "turbulent"

    f = _colebrook(Re, eps_D)
    L_eff = L_v + Le
    dP = f * (L_eff / D_v) * (rho_v * V ** 2 / 2.0)

    # Velocity check — warn if > 3 m/s (typical B31.3 erosion threshold for liquid)
    if V > 3.0:
        msg = f"Velocity {V:.2f} m/s exceeds 3 m/s; check for erosion per B31.3 §305.1."
        warn_list.append(msg)
        warnings.warn(msg, stacklevel=2)

    return {
        "ok": True,
        "dP_Pa": dP,
        "dP_kPa": dP * 1e-3,
        "dP_bar": dP * 1e-5,
        "velocity_m_s": V,
        "Re": Re,
        "friction_factor": f,
        "flow_regime": regime,
        "L_eff_m": L_eff,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 3. allowable_span — pipe support spacing
#    Per MSS SP-69 and Roark's deflection / stress limits for a simply-
#    supported beam with uniform load (self-weight + fluid weight).
#
#    Two limits:
#      (a) Deflection limit: δ = 5wL⁴/(384EI) ≤ δ_allow  → L ≤ (384EI·δ_allow/(5w))^0.25
#      (b) Stress limit: M_max = wL²/8; σ = M_max/Z ≤ S_allow → L ≤ √(8·S_allow·Z/w)
# ---------------------------------------------------------------------------

def allowable_span(
    D_o: float,
    D_i: float,
    rho_pipe: float,
    rho_fluid: float,
    E: float,
    S_allow: float,
    deflection_limit: float = 0.0254,
) -> dict:
    """
    Maximum allowable support span for a simply-supported pipe.

    Both a deflection criterion and a bending-stress criterion are computed;
    the smaller governs.

    Parameters
    ----------
    D_o : float
        Pipe outside diameter (m). Must be > 0.
    D_i : float
        Pipe inside diameter (m). Must be > 0 and < D_o.
    rho_pipe : float
        Pipe material density (kg/m³). Must be > 0. Carbon steel ≈ 7850.
    rho_fluid : float
        Fluid density inside the pipe (kg/m³). Must be >= 0. Water = 1000.
    E : float
        Young's modulus of pipe material (Pa). Must be > 0. CS ≈ 200e9 Pa.
    S_allow : float
        Allowable bending stress (Pa). Must be > 0.
        Typically the ASME B31.3 hot-allowable stress S_h.
    deflection_limit : float
        Maximum allowable mid-span deflection (m). Default 25.4 mm (1 in)
        per MSS SP-69.  Must be > 0.

    Returns
    -------
    dict
        ok                  : True
        L_deflection_m      : span limited by deflection (m)
        L_stress_m          : span limited by bending stress (m)
        L_allowable_m       : governing (minimum) allowable span (m)
        governing           : "deflection" | "stress"
        w_N_per_m           : distributed weight per unit length (N/m)
        I_m4                : pipe second moment of area (m⁴)
        Z_m3                : pipe section modulus (m³)
        EI_Nm2              : flexural rigidity (N·m²)
        warnings            : list of code-exceedance warning strings

    Formulas
    --------
    Cross-section properties:
        A_metal = π/4·(D_o² - D_i²)
        I       = π/64·(D_o⁴ - D_i⁴)
        Z       = I / (D_o/2)

    Distributed loading:
        w = (A_metal·ρ_pipe + π/4·D_i²·ρ_fluid) · g

    Deflection-limited span (simply supported, uniform load):
        L_d = (384·E·I·δ_allow / (5·w))^(1/4)

    Stress-limited span:
        σ_max = w·L²/(8·Z) ≤ S_allow
        L_s = √(8·S_allow·Z / w)
    """
    warn_list: list[str] = []

    err = _guard_positive("D_o", D_o)
    if err:
        return _err(err)
    err = _guard_positive("D_i", D_i)
    if err:
        return _err(err)
    if D_i >= D_o:
        return _err(f"D_i ({D_i} m) must be < D_o ({D_o} m)")
    err = _guard_positive("rho_pipe", rho_pipe)
    if err:
        return _err(err)
    err = _guard_nonneg("rho_fluid", rho_fluid)
    if err:
        return _err(err)
    err = _guard_positive("E", E)
    if err:
        return _err(err)
    err = _guard_positive("S_allow", S_allow)
    if err:
        return _err(err)
    err = _guard_positive("deflection_limit", deflection_limit)
    if err:
        return _err(err)

    _G = 9.80665

    A_metal = math.pi / 4.0 * (D_o ** 2 - D_i ** 2)
    A_fluid = math.pi / 4.0 * D_i ** 2
    I = math.pi / 64.0 * (D_o ** 4 - D_i ** 4)
    Z = I / (D_o / 2.0)

    w = (A_metal * rho_pipe + A_fluid * rho_fluid) * _G  # N/m

    if w <= 0:
        return _err("Distributed weight w <= 0 — check density inputs")

    EI = float(E) * I

    # Deflection-limited span: δ = 5wL⁴/(384EI) ≤ δ_allow
    L_deflection = (384.0 * EI * deflection_limit / (5.0 * w)) ** 0.25

    # Stress-limited span: σ = wL²/(8Z) ≤ S_allow
    L_stress = math.sqrt(8.0 * float(S_allow) * Z / w)

    L_allowable = min(L_deflection, L_stress)
    governing = "deflection" if L_deflection <= L_stress else "stress"

    return {
        "ok": True,
        "L_deflection_m": L_deflection,
        "L_stress_m": L_stress,
        "L_allowable_m": L_allowable,
        "governing": governing,
        "w_N_per_m": w,
        "I_m4": I,
        "Z_m3": Z,
        "EI_Nm2": EI,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 4. thermal_expansion — free elongation ΔL
# ---------------------------------------------------------------------------

def thermal_expansion(
    L: float,
    alpha: float,
    T_install: float,
    T_operating: float,
) -> dict:
    """
    Thermal free elongation for a pipe segment.

    Parameters
    ----------
    L : float
        Pipe segment length (m). Must be > 0.
    alpha : float
        Coefficient of thermal expansion (1/°C). Must be > 0.
        Carbon steel ≈ 11.7e-6 / °C; austenitic SS 316 ≈ 16.0e-6 / °C.
    T_install : float
        Installation (ambient) temperature (°C).
    T_operating : float
        Operating temperature (°C).

    Returns
    -------
    dict
        ok              : True
        delta_L_m       : free elongation ΔL = L·α·ΔT (m)
        delta_L_mm      : same in mm
        delta_T         : temperature difference ΔT = T_op - T_install (°C)
        L_m             : pipe length used (m)
        alpha           : CTE used (1/°C)
        T_install       : installation temperature (°C)
        T_operating     : operating temperature (°C)
        warnings        : list of strings

    Formula
    -------
        ΔL = L · α · (T_operating - T_install)
    """
    warn_list: list[str] = []

    err = _guard_positive("L", L)
    if err:
        return _err(err)
    err = _guard_positive("alpha", alpha)
    if err:
        return _err(err)

    L_v = float(L)
    alpha_v = float(alpha)
    T_inst = float(T_install)
    T_op = float(T_operating)

    dT = T_op - T_inst
    dL = L_v * alpha_v * dT

    if abs(dT) < 1e-9:
        msg = "ΔT ≈ 0 °C; thermal expansion is negligible."
        warn_list.append(msg)
        warnings.warn(msg, stacklevel=2)

    return {
        "ok": True,
        "delta_L_m": dL,
        "delta_L_mm": dL * 1e3,
        "delta_T": dT,
        "L_m": L_v,
        "alpha": alpha_v,
        "T_install": T_inst,
        "T_operating": T_op,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 5. guided_cantilever_leg — minimum leg length to absorb a displacement
#
# For a guided-cantilever (both ends fixed in rotation but free to translate),
# the displacement δ at the free end relates to stress by:
#
#     σ = 3·E·D_o·δ / (2·L²)  ... for a thin-wall pipe treated as a beam
#
# Setting σ = S_allow and solving for L:
#     L = √(3·E·D_o·δ / (2·S_allow))
#
# For a hollow pipe section (more accurate via section modulus Z = I/(D_o/2)):
#     M_max = 3·E·I·δ / L²    (guided-cantilever, fixed-guided)
#     σ = M_max / Z = 3·E·I·δ / (L²·Z)
# Solving: L = √(3·E·I·δ / (S_allow·Z))
# ---------------------------------------------------------------------------

def guided_cantilever_leg(
    D_o: float,
    t: float,
    E: float,
    S_allow: float,
    delta: float,
) -> dict:
    """
    Minimum leg length for a guided-cantilever piping elbow to absorb displacement.

    Used for L-shaped or Z-shaped pipe loops subjected to thermal growth δ.
    The formula assumes both ends are guided (fixed in rotation, free in
    translation in the direction of δ), which is the conservative Guided
    Cantilever method per ASME B31.3 Appendix D / Kellogg.

    Parameters
    ----------
    D_o : float
        Pipe outside diameter (m). Must be > 0.
    t : float
        Pipe wall thickness (m). Must be > 0 and < D_o/2.
    E : float
        Young's modulus (Pa). Must be > 0.
    S_allow : float
        Allowable expansion stress range (Pa). Must be > 0.
        Typically S_A = f·(1.25·S_c + 0.25·S_h) per B31.3 §302.3.5.
    delta : float
        Displacement to absorb (m). Must be > 0.

    Returns
    -------
    dict
        ok              : True
        L_leg_m         : minimum leg length (m)
        L_leg_mm        : same in mm
        I_m4            : pipe second moment of area (m⁴)
        Z_m3            : pipe section modulus (m³)
        sigma_at_L_Pa   : bending stress at the minimum leg length (Pa)
        warnings        : list of strings

    Formula
    -------
    For a guided cantilever:
        M_max = 3·E·I·δ / L²
        σ = M_max / Z

    Setting σ ≤ S_allow:
        L_leg = √(3·E·I·δ / (S_allow·Z))
    """
    warn_list: list[str] = []

    err = _guard_positive("D_o", D_o)
    if err:
        return _err(err)
    err = _guard_positive("t", t)
    if err:
        return _err(err)
    if t >= D_o / 2.0:
        return _err(f"Wall thickness t={t} m must be < D_o/2 = {D_o/2} m")
    err = _guard_positive("E", E)
    if err:
        return _err(err)
    err = _guard_positive("S_allow", S_allow)
    if err:
        return _err(err)
    err = _guard_positive("delta", delta)
    if err:
        return _err(err)

    D_i = float(D_o) - 2.0 * float(t)
    I = math.pi / 64.0 * (float(D_o) ** 4 - D_i ** 4)
    Z = I / (float(D_o) / 2.0)

    L_leg = math.sqrt(3.0 * float(E) * I * float(delta) / (float(S_allow) * Z))
    sigma_check = 3.0 * float(E) * I * float(delta) / (L_leg ** 2 * Z)

    if abs(sigma_check - float(S_allow)) / float(S_allow) > 1e-6:
        msg = f"Consistency check: σ at L_leg = {sigma_check:.2f} Pa vs S_allow = {S_allow:.2f} Pa"
        warn_list.append(msg)

    return {
        "ok": True,
        "L_leg_m": L_leg,
        "L_leg_mm": L_leg * 1e3,
        "I_m4": I,
        "Z_m3": Z,
        "sigma_at_L_Pa": sigma_check,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 6. expansion_stress_check — two-anchor expansion stress
#
# Simplified guided-cantilever stress check for a two-anchor piping system
# with legs L_x (along x-axis) and L_y (along y-axis).
#
# For each leg the stress contribution from its perpendicular displacement is:
#    σ_i = 3·E·D_o·δ_i / (2·L_i²)    [thin-walled approx]
# or using the section-modulus form:
#    σ_i = 3·E·I·δ_i / (L_i²·Z)      [exact for hollow section]
#
# Total expansion stress = SRSS (conservative sum used by many codes):
#    σ_E = √(σ_x² + σ_y² + σ_z²)
#
# Pass: σ_E ≤ S_allow
# ---------------------------------------------------------------------------

def expansion_stress_check(
    delta_x: float,
    delta_y: float,
    delta_z: float,
    L_x: float,
    L_y: float,
    E: float,
    D_o: float,
    t: float,
    S_allow: float,
) -> dict:
    """
    Simplified two-anchor expansion stress check per guided-cantilever method.

    Computes the bending stress in each absorbing leg due to its displacement,
    then combines them by SRSS (square root of sum of squares) to obtain the
    total expansion stress.  Checks the result against the allowable expansion
    stress range S_allow.

    Parameters
    ----------
    delta_x : float
        Displacement absorbed by leg L_x (perpendicular to L_x axis) (m).
        May be 0 if no motion in that direction. Must be >= 0.
    delta_y : float
        Displacement absorbed by leg L_y (m). Must be >= 0.
    delta_z : float
        Out-of-plane displacement component (m). Must be >= 0.
        For a 2D analysis set to 0.
    L_x : float
        Length of leg in the x-direction (m). Must be > 0.
    L_y : float
        Length of leg in the y-direction (m). Must be > 0.
    E : float
        Young's modulus (Pa). Must be > 0.
    D_o : float
        Pipe outside diameter (m). Must be > 0.
    t : float
        Pipe wall thickness (m). Must be > 0 and < D_o/2.
    S_allow : float
        Allowable expansion stress range (Pa). Must be > 0.

    Returns
    -------
    dict
        ok              : True
        sigma_x_Pa      : bending stress from δ_x in leg L_x (Pa)
        sigma_y_Pa      : bending stress from δ_y in leg L_y (Pa)
        sigma_z_Pa      : out-of-plane stress contribution (Pa)
        sigma_E_Pa      : combined expansion stress (SRSS) (Pa)
        S_allow_Pa      : allowable expansion stress used (Pa)
        pass_fail       : True if σ_E ≤ S_allow
        safety_factor   : S_allow / σ_E (inf if σ_E = 0)
        warnings        : list of code-exceedance warning strings
    """
    warn_list: list[str] = []

    for name, val in (("delta_x", delta_x), ("delta_y", delta_y), ("delta_z", delta_z)):
        err = _guard_nonneg(name, val)
        if err:
            return _err(err)
    for name, val in (("L_x", L_x), ("L_y", L_y), ("E", E), ("D_o", D_o), ("t", t), ("S_allow", S_allow)):
        err = _guard_positive(name, val)
        if err:
            return _err(err)
    if float(t) >= float(D_o) / 2.0:
        return _err(f"Wall thickness t={t} m must be < D_o/2 = {D_o/2} m")

    D_o_v = float(D_o)
    t_v = float(t)
    E_v = float(E)
    S_v = float(S_allow)

    D_i = D_o_v - 2.0 * t_v
    I = math.pi / 64.0 * (D_o_v ** 4 - D_i ** 4)
    Z = I / (D_o_v / 2.0)

    def _sigma_leg(delta: float, L: float) -> float:
        if delta == 0.0 or L <= 0:
            return 0.0
        return 3.0 * E_v * I * delta / (L ** 2 * Z)

    sx = _sigma_leg(float(delta_x), float(L_x))
    sy = _sigma_leg(float(delta_y), float(L_y))
    # For delta_z: use the shorter leg for a conservative estimate
    sz = _sigma_leg(float(delta_z), min(float(L_x), float(L_y)))

    sigma_E = math.sqrt(sx ** 2 + sy ** 2 + sz ** 2)
    pass_fail = sigma_E <= S_v

    if not pass_fail:
        msg = (
            f"Expansion stress σ_E = {sigma_E/1e6:.2f} MPa exceeds "
            f"S_allow = {S_v/1e6:.2f} MPa. Increase leg lengths or add expansion loops."
        )
        warn_list.append(msg)
        warnings.warn(msg, stacklevel=2)

    sf = S_v / sigma_E if sigma_E > 0 else float("inf")

    return {
        "ok": True,
        "sigma_x_Pa": sx,
        "sigma_y_Pa": sy,
        "sigma_z_Pa": sz,
        "sigma_E_Pa": sigma_E,
        "S_allow_Pa": S_v,
        "pass_fail": pass_fail,
        "safety_factor": sf,
        "warnings": warn_list,
    }
