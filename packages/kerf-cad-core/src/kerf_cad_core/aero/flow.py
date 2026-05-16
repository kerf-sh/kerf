"""
kerf_cad_core.aero.flow — pure-Python applied aerodynamics formulas.

Implements the following public functions (all return plain dicts):

  isa_atmosphere(altitude_m)
      ICAO Standard Atmosphere: temperature T (K), pressure p (Pa),
      density rho (kg/m³), speed of sound a (m/s).
      Troposphere (0–11 000 m) + tropopause/stratosphere (11 000–20 000 m).

  dynamic_pressure(rho, V)
      q = ½ ρ V²   (Pa)

  reynolds_number(rho, V, L, mu)
      Re = ρ V L / μ

  mach_number(V, a)
      M = V / a

  prandtl_glauert_factor(M_inf)
      PG compressibility correction β = √(1 − M²).
      Issues a warning for M > 0.7 (transonic).

  thin_airfoil_cl(alpha_rad, alpha0_rad)
      Thin-airfoil theory: Cl = 2π (α − α₀).

  thin_airfoil_cm(alpha_rad, alpha0_rad)
      Quarter-chord pitching moment coefficient: Cm_c/4 = −π(α−α₀)/2  [thin].
      NOTE: thin-airfoil gives Cm_c/4 ≈ −π/4 × (dCl/dα) × (α−α₀)
            For symmetric: Cm_c/4 = 0; for cambered using α₀: Cm_c/4 = −π(α−α₀)/2.
            This returns Cm_c/4 at quarter chord.

  finite_wing_lift_slope(a0, AR, e_planform)
      Prandtl finite-wing: a = a₀ / (1 + a₀/(π AR e))   [rad⁻¹]
      where a₀ = 2π (thin airfoil) or supplied.

  finite_wing_cl(alpha_rad, alpha0_rad, AR, e_planform)
      CL = a_wing × (α − α₀)

  induced_drag_coefficient(CL, AR, e)
      CD_i = CL² / (π AR e)

  total_drag_coefficient(CD0, CL, AR, e)
      CD = CD0 + CL² / (π AR e)

  ld_ratio(CL, CD)
      L/D = CL / CD

  best_glide_cl(CD0, AR, e)
      Best-glide (max L/D) occurs at CL* = √(π AR e CD0)
      (where induced drag = parasite drag).

  level_flight_thrust(W, CL, CD)
      T = W × CD/CL  (level unaccelerated flight)

  level_flight_power(T, V)
      P = T × V  (W)

  stall_speed(W, rho, S, CLmax)
      V_stall = √(2W / (ρ S CLmax))  (m/s)
      Issues a warning if V_stall cannot be computed (negative under root).

  climb_rate(T, D, V, W)
      RC = (T − D) V / W  (m/s)
      Issues a warning for RC ≤ 0 (negative or zero climb margin).

  actuator_disc_thrust(rho, A_disc, V_inf, w)
      Ideal thrust from actuator-disc theory:
        T = ρ A (V_inf + w) × 2w   [Momentum theory]
        where w is the induced velocity at the disc.
      (Equivalently T = 2 ρ A (V_inf + w) w)

  propeller_ideal_efficiency(V_inf, w)
      η_ideal = V_inf / (V_inf + w)
      Issues a warning for zero or very small V_inf (static thrust case).

  breguet_range(eta_p, c_specific, LD, W_initial, W_final)
      Breguet range (propeller / piston):
        R = (η_p/c) × (L/D) × ln(W_i/W_f)   (m)
      c_specific in (N/W) or (kg/(N·s)) — fuel flow per unit thrust × weight.
      NOTE: for jet use breguet_range_jet (not implemented here; use LD/TSFC).

  breguet_endurance(eta_p, c_specific, CL, CD, rho, S, W_initial, W_final)
      Breguet endurance (propeller):
        E = (η_p/c) × (CL^(1/2)/CD) × (2/(ρS))^(1/2) × (W_f^(-1/2) - W_i^(-1/2)) ...
        Simplified for constant altitude/speed:
        E = (η_p/c) × (CL/CD) × (1/g) × ln(W_i/W_f)   (s)
        (This is the fuel-weight form; g=9.80665)

All functions return a plain dict:
    success → {"ok": True, ...computed fields...}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Warnings are issued via the stdlib `warnings` module
for:
  - Transonic regime  (M > 0.7)
  - Stall condition   (if CL > CL_max is known, or V < V_stall)
  - Negative climb rate

Units
-----
  altitude      — metres (m)
  temperature   — Kelvin (K)
  pressure      — Pascals (Pa)
  density       — kg/m³
  speed         — m/s
  angles        — radians (rad) unless noted
  force/weight  — Newtons (N)
  power         — Watts (W)
  area          — m²
  range         — metres (m)
  endurance     — seconds (s)

References
----------
Anderson, J.D. — Introduction to Flight, 8th ed., McGraw-Hill (2016)
Anderson, J.D. — Fundamentals of Aerodynamics, 6th ed., McGraw-Hill (2017)
ICAO Doc 7488  — Manual of the ICAO Standard Atmosphere, 3rd ed. (1993)

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import Any

# ---------------------------------------------------------------------------
# ISA constants
# ---------------------------------------------------------------------------
_T0 = 288.15      # Sea-level temperature (K)
_P0 = 101325.0    # Sea-level pressure (Pa)
_RHO0 = 1.225     # Sea-level density (kg/m³)
_L = -0.0065      # Tropospheric lapse rate (K/m)  — negative: cools with altitude
_R = 287.05287    # Specific gas constant for dry air (J/(kg·K))
_GAMMA = 1.4      # Ratio of specific heats for air
_G0 = 9.80665     # Standard gravity (m/s²)

# Tropopause base
_H_TROP = 11_000.0   # m
_T_TROP = _T0 + _L * _H_TROP   # 216.65 K

# Stratosphere constant temperature up to ~20 km
_H_STRAT_TOP = 20_000.0  # m  (above this a second lapse starts; not modelled)


def _validate_positive(name: str, value: Any, zero_ok: bool = False) -> str | None:
    """Return an error string if value is not a finite positive number, else None."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if zero_ok:
        if v < 0.0:
            return f"{name} must be >= 0, got {v}"
    else:
        if v <= 0.0:
            return f"{name} must be > 0, got {v}"
    return None


# ---------------------------------------------------------------------------
# ISA Standard Atmosphere
# ---------------------------------------------------------------------------

def isa_atmosphere(altitude_m: float) -> dict:
    """
    ICAO Standard Atmosphere at a given geopotential altitude.

    Troposphere  : 0 – 11 000 m  (temperature lapse rate −6.5 K/km)
    Tropopause   : 11 000 – 20 000 m  (isothermal at 216.65 K)

    Parameters
    ----------
    altitude_m : float
        Geopotential altitude (m).  Range: 0 – 20 000 m.

    Returns
    -------
    dict with keys: ok, altitude_m, T_K, p_Pa, rho_kg_m3, a_m_s
    """
    try:
        h = float(altitude_m)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "altitude_m must be a number"}
    if not math.isfinite(h):
        return {"ok": False, "reason": "altitude_m must be finite"}
    if h < 0.0:
        return {"ok": False, "reason": "altitude_m must be >= 0"}
    if h > _H_STRAT_TOP:
        return {
            "ok": False,
            "reason": (
                f"altitude_m={h} m exceeds 20 000 m; "
                "second stratospheric lapse layer not modelled"
            ),
        }

    if h <= _H_TROP:
        # Troposphere
        T = _T0 + _L * h
        exponent = -_G0 / (_L * _R)
        p = _P0 * (T / _T0) ** exponent
    else:
        # Isothermal stratosphere (tropopause)
        T = _T_TROP
        # Pressure at tropopause base
        p_trop = _P0 * (_T_TROP / _T0) ** (-_G0 / (_L * _R))
        p = p_trop * math.exp(-_G0 * (h - _H_TROP) / (_R * _T_TROP))

    rho = p / (_R * T)
    a = math.sqrt(_GAMMA * _R * T)

    return {
        "ok": True,
        "altitude_m": h,
        "T_K": T,
        "p_Pa": p,
        "rho_kg_m3": rho,
        "a_m_s": a,
    }


# ---------------------------------------------------------------------------
# Dynamic pressure
# ---------------------------------------------------------------------------

def dynamic_pressure(rho: float, V: float) -> dict:
    """
    Dynamic pressure q = ½ ρ V²  (Pa).

    Parameters
    ----------
    rho : float
        Air density (kg/m³). Must be > 0.
    V : float
        Airspeed (m/s). Must be >= 0.

    Returns
    -------
    dict with keys: ok, q_Pa
    """
    err = _validate_positive("rho", rho)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("V", V, zero_ok=True)
    if err:
        return {"ok": False, "reason": err}
    q = 0.5 * float(rho) * float(V) ** 2
    return {"ok": True, "q_Pa": q}


# ---------------------------------------------------------------------------
# Reynolds number
# ---------------------------------------------------------------------------

def reynolds_number(rho: float, V: float, L: float, mu: float) -> dict:
    """
    Reynolds number Re = ρ V L / μ.

    Parameters
    ----------
    rho : float
        Air density (kg/m³). Must be > 0.
    V : float
        Airspeed (m/s). Must be > 0.
    L : float
        Reference length (m), typically chord length. Must be > 0.
    mu : float
        Dynamic viscosity (Pa·s). Must be > 0.
        Standard sea level: ~1.789e-5 Pa·s.

    Returns
    -------
    dict with keys: ok, Re
    """
    for name, val in (("rho", rho), ("V", V), ("L", L), ("mu", mu)):
        err = _validate_positive(name, val)
        if err:
            return {"ok": False, "reason": err}
    Re = float(rho) * float(V) * float(L) / float(mu)
    return {"ok": True, "Re": Re}


# ---------------------------------------------------------------------------
# Mach number
# ---------------------------------------------------------------------------

def mach_number(V: float, a: float) -> dict:
    """
    Mach number M = V / a.

    Issues a transonic warning if M > 0.7.

    Parameters
    ----------
    V : float
        Airspeed (m/s). Must be >= 0.
    a : float
        Speed of sound (m/s). Must be > 0.

    Returns
    -------
    dict with keys: ok, M, transonic (bool)
    """
    err = _validate_positive("V", V, zero_ok=True)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("a", a)
    if err:
        return {"ok": False, "reason": err}
    M = float(V) / float(a)
    transonic = M > 0.7
    if transonic:
        warnings.warn(
            f"Mach {M:.3f} > 0.7: transonic/supersonic regime; "
            "incompressible and Prandtl-Glauert results are unreliable.",
            stacklevel=2,
        )
    return {"ok": True, "M": M, "transonic": transonic}


# ---------------------------------------------------------------------------
# Prandtl-Glauert compressibility correction
# ---------------------------------------------------------------------------

def prandtl_glauert_factor(M_inf: float) -> dict:
    """
    Prandtl-Glauert subsonic compressibility correction.

    β = √(1 − M_inf²)

    Corrected lift-curve slope: a_compressible = a_incompressible / β.

    Issues a warning if M_inf > 0.7 (transonic; PG breaks down).

    Parameters
    ----------
    M_inf : float
        Freestream Mach number.  Must satisfy 0 ≤ M_inf < 1.

    Returns
    -------
    dict with keys: ok, M_inf, beta, transonic_warning (bool)
    """
    try:
        M = float(M_inf)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "M_inf must be a number"}
    if not math.isfinite(M):
        return {"ok": False, "reason": "M_inf must be finite"}
    if M < 0.0:
        return {"ok": False, "reason": "M_inf must be >= 0"}
    if M >= 1.0:
        return {
            "ok": False,
            "reason": "M_inf must be < 1 (Prandtl-Glauert is subsonic only)",
        }
    transonic = M > 0.7
    if transonic:
        warnings.warn(
            f"M_inf={M:.3f} > 0.7: Prandtl-Glauert correction is increasingly "
            "inaccurate in the transonic regime.",
            stacklevel=2,
        )
    beta = math.sqrt(1.0 - M ** 2)
    return {"ok": True, "M_inf": M, "beta": beta, "transonic_warning": transonic}


# ---------------------------------------------------------------------------
# Thin-airfoil theory
# ---------------------------------------------------------------------------

def thin_airfoil_cl(alpha_rad: float, alpha0_rad: float = 0.0) -> dict:
    """
    Thin-airfoil theory lift coefficient: Cl = 2π (α − α₀).

    Parameters
    ----------
    alpha_rad : float
        Geometric angle of attack (rad).
    alpha0_rad : float
        Zero-lift angle of attack (rad).  0 for symmetric airfoils.

    Returns
    -------
    dict with keys: ok, Cl, alpha_rad, alpha0_rad, stall_warning (bool)
    """
    try:
        alpha = float(alpha_rad)
        alpha0 = float(alpha0_rad)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "alpha_rad and alpha0_rad must be numbers"}
    if not (math.isfinite(alpha) and math.isfinite(alpha0)):
        return {"ok": False, "reason": "alpha_rad and alpha0_rad must be finite"}
    Cl = 2.0 * math.pi * (alpha - alpha0)
    # Rough stall warning: typical Cl_max ~ 1.4 for thin airfoils
    stall = abs(Cl) > 1.4
    if stall:
        warnings.warn(
            f"Thin-airfoil Cl={Cl:.3f} exceeds typical maximum (~1.4); "
            "stall likely; thin-airfoil theory is invalid post-stall.",
            stacklevel=2,
        )
    return {
        "ok": True,
        "Cl": Cl,
        "alpha_rad": alpha,
        "alpha0_rad": alpha0,
        "stall_warning": stall,
    }


def thin_airfoil_cm(alpha_rad: float, alpha0_rad: float = 0.0) -> dict:
    """
    Quarter-chord pitching moment coefficient from thin-airfoil theory.

    For a thin airfoil the moment coefficient about the aerodynamic centre
    (quarter-chord) is:
        Cm_c/4 = −π/2 × (α − α₀)     [cambered airfoil, zero-camber → 0]

    NOTE: For symmetric airfoils (α₀ = 0) Cm_c/4 = 0 identically.
    For cambered airfoils α₀ ≠ 0 and Cm_c/4 is non-zero.

    Parameters
    ----------
    alpha_rad : float
        Angle of attack (rad).
    alpha0_rad : float
        Zero-lift angle of attack (rad).

    Returns
    -------
    dict with keys: ok, Cm_c4, alpha_rad, alpha0_rad
    """
    try:
        alpha = float(alpha_rad)
        alpha0 = float(alpha0_rad)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "alpha_rad and alpha0_rad must be numbers"}
    if not (math.isfinite(alpha) and math.isfinite(alpha0)):
        return {"ok": False, "reason": "alpha_rad and alpha0_rad must be finite"}
    # Thin-airfoil: Cm_c/4 = -(π/2)(α - α₀)
    Cm_c4 = -(math.pi / 2.0) * (alpha - alpha0)
    return {"ok": True, "Cm_c4": Cm_c4, "alpha_rad": alpha, "alpha0_rad": alpha0}


# ---------------------------------------------------------------------------
# Finite-wing (Prandtl lifting-line)
# ---------------------------------------------------------------------------

def finite_wing_lift_slope(
    a0: float = 2.0 * math.pi,
    AR: float = 6.0,
    e_planform: float = 1.0,
) -> dict:
    """
    Prandtl lifting-line finite-wing lift-curve slope.

    a = a₀ / (1 + a₀ / (π AR e))   (rad⁻¹)

    Parameters
    ----------
    a0 : float
        Section (2D) lift-curve slope (rad⁻¹).  Default 2π (thin airfoil).
    AR : float
        Wing aspect ratio b²/S. Must be > 0.
    e_planform : float
        Planform efficiency (Oswald span efficiency) for slope correction.
        Typically 0.9–1.0 for elliptical planforms.  Must be in (0, 1].

    Returns
    -------
    dict with keys: ok, a_rad_inv, a0, AR, e_planform
    """
    err = _validate_positive("a0", a0)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("AR", AR)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("e_planform", e_planform)
    if err:
        return {"ok": False, "reason": err}
    a0f = float(a0)
    ARf = float(AR)
    ef = float(e_planform)
    a = a0f / (1.0 + a0f / (math.pi * ARf * ef))
    return {"ok": True, "a_rad_inv": a, "a0": a0f, "AR": ARf, "e_planform": ef}


def finite_wing_cl(
    alpha_rad: float,
    alpha0_rad: float = 0.0,
    AR: float = 6.0,
    e_planform: float = 1.0,
    a0: float = 2.0 * math.pi,
) -> dict:
    """
    Finite-wing lift coefficient using Prandtl lifting-line.

    CL = a × (α − α₀)
    where a = a₀ / (1 + a₀/(π AR e)).

    Parameters
    ----------
    alpha_rad : float
        Angle of attack (rad).
    alpha0_rad : float
        Zero-lift angle of attack (rad).  Default 0.
    AR : float
        Aspect ratio. Must be > 0.
    e_planform : float
        Oswald planform efficiency.  Must be in (0, 1].
    a0 : float
        Section lift-curve slope (rad⁻¹).  Default 2π.

    Returns
    -------
    dict with keys: ok, CL, a_rad_inv, alpha_rad, alpha0_rad, AR, e_planform, stall_warning
    """
    slope_res = finite_wing_lift_slope(a0=a0, AR=AR, e_planform=e_planform)
    if not slope_res["ok"]:
        return slope_res
    try:
        alpha = float(alpha_rad)
        alpha0 = float(alpha0_rad)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "alpha_rad and alpha0_rad must be numbers"}
    if not (math.isfinite(alpha) and math.isfinite(alpha0)):
        return {"ok": False, "reason": "alpha_rad and alpha0_rad must be finite"}
    CL = slope_res["a_rad_inv"] * (alpha - alpha0)
    stall = abs(CL) > 1.6
    if stall:
        warnings.warn(
            f"Finite-wing CL={CL:.3f} exceeds typical CLmax (~1.6) for "
            "unflapped wings; stall likely.",
            stacklevel=2,
        )
    return {
        "ok": True,
        "CL": CL,
        "a_rad_inv": slope_res["a_rad_inv"],
        "alpha_rad": alpha,
        "alpha0_rad": alpha0,
        "AR": float(AR),
        "e_planform": float(e_planform),
        "stall_warning": stall,
    }


# ---------------------------------------------------------------------------
# Drag coefficients
# ---------------------------------------------------------------------------

def induced_drag_coefficient(CL: float, AR: float, e: float) -> dict:
    """
    Induced drag coefficient from Prandtl's formula.

    CD_i = CL² / (π AR e)

    Parameters
    ----------
    CL : float
        Lift coefficient. May be negative (drag is always positive).
    AR : float
        Aspect ratio. Must be > 0.
    e : float
        Oswald span efficiency factor.  Must be in (0, 1].

    Returns
    -------
    dict with keys: ok, CDi, CL, AR, e
    """
    err = _validate_positive("AR", AR)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("e", e)
    if err:
        return {"ok": False, "reason": err}
    try:
        CL_f = float(CL)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "CL must be a number"}
    if not math.isfinite(CL_f):
        return {"ok": False, "reason": "CL must be finite"}
    CDi = CL_f ** 2 / (math.pi * float(AR) * float(e))
    return {"ok": True, "CDi": CDi, "CL": CL_f, "AR": float(AR), "e": float(e)}


def total_drag_coefficient(CD0: float, CL: float, AR: float, e: float) -> dict:
    """
    Total drag coefficient: parasite + induced.

    CD = CD0 + CL² / (π AR e)

    Parameters
    ----------
    CD0 : float
        Zero-lift (parasite) drag coefficient. Must be >= 0.
    CL : float
        Lift coefficient.
    AR : float
        Aspect ratio. Must be > 0.
    e : float
        Oswald span efficiency. Must be in (0, 1].

    Returns
    -------
    dict with keys: ok, CD, CD0, CDi, CL, AR, e
    """
    err = _validate_positive("CD0", CD0, zero_ok=True)
    if err:
        return {"ok": False, "reason": err}
    cdi_res = induced_drag_coefficient(CL=CL, AR=AR, e=e)
    if not cdi_res["ok"]:
        return cdi_res
    CD = float(CD0) + cdi_res["CDi"]
    return {
        "ok": True,
        "CD": CD,
        "CD0": float(CD0),
        "CDi": cdi_res["CDi"],
        "CL": cdi_res["CL"],
        "AR": float(AR),
        "e": float(e),
    }


# ---------------------------------------------------------------------------
# L/D and best glide
# ---------------------------------------------------------------------------

def ld_ratio(CL: float, CD: float) -> dict:
    """
    Lift-to-drag ratio.

    L/D = CL / CD

    Parameters
    ----------
    CL : float
        Lift coefficient. May be any finite value.
    CD : float
        Drag coefficient. Must be > 0.

    Returns
    -------
    dict with keys: ok, LD, CL, CD
    """
    try:
        CL_f = float(CL)
        CD_f = float(CD)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "CL and CD must be numbers"}
    if not (math.isfinite(CL_f) and math.isfinite(CD_f)):
        return {"ok": False, "reason": "CL and CD must be finite"}
    if CD_f <= 0.0:
        return {"ok": False, "reason": "CD must be > 0"}
    return {"ok": True, "LD": CL_f / CD_f, "CL": CL_f, "CD": CD_f}


def best_glide_cl(CD0: float, AR: float, e: float) -> dict:
    """
    Lift coefficient for maximum L/D (best glide).

    At maximum L/D, parasite drag = induced drag:
        CD0 = CL² / (π AR e)
        →  CL* = √(π AR e CD0)

    Maximum L/D:
        (L/D)_max = CL* / (2 CD0)

    Parameters
    ----------
    CD0 : float
        Parasite drag coefficient. Must be > 0.
    AR : float
        Aspect ratio. Must be > 0.
    e : float
        Oswald span efficiency. Must be > 0.

    Returns
    -------
    dict with keys: ok, CL_best, LD_max, CD0, AR, e
    """
    for name, val in (("CD0", CD0), ("AR", AR), ("e", e)):
        err = _validate_positive(name, val)
        if err:
            return {"ok": False, "reason": err}
    CL_best = math.sqrt(math.pi * float(AR) * float(e) * float(CD0))
    CD_best = 2.0 * float(CD0)   # parasite = induced at best glide
    LD_max = CL_best / CD_best
    return {
        "ok": True,
        "CL_best": CL_best,
        "LD_max": LD_max,
        "CD0": float(CD0),
        "AR": float(AR),
        "e": float(e),
    }


# ---------------------------------------------------------------------------
# Level-flight performance
# ---------------------------------------------------------------------------

def level_flight_thrust(W: float, CL: float, CD: float) -> dict:
    """
    Required thrust for steady, level, unaccelerated flight.

    T_req = W × (CD / CL)   =   W / (L/D)

    Parameters
    ----------
    W : float
        Aircraft weight (N). Must be > 0.
    CL : float
        Lift coefficient at flight condition. Must be > 0.
    CD : float
        Drag coefficient at flight condition. Must be > 0.

    Returns
    -------
    dict with keys: ok, T_req_N, W, CL, CD, LD
    """
    for name, val in (("W", W), ("CL", CL), ("CD", CD)):
        err = _validate_positive(name, val)
        if err:
            return {"ok": False, "reason": err}
    W_f, CL_f, CD_f = float(W), float(CL), float(CD)
    T_req = W_f * CD_f / CL_f
    return {
        "ok": True,
        "T_req_N": T_req,
        "W": W_f,
        "CL": CL_f,
        "CD": CD_f,
        "LD": CL_f / CD_f,
    }


def level_flight_power(T: float, V: float) -> dict:
    """
    Required shaft/engine power for level flight.

    P_req = T × V

    Parameters
    ----------
    T : float
        Thrust required (N). Must be >= 0.
    V : float
        True airspeed (m/s). Must be > 0.

    Returns
    -------
    dict with keys: ok, P_req_W, T, V
    """
    err = _validate_positive("T", T, zero_ok=True)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("V", V)
    if err:
        return {"ok": False, "reason": err}
    P = float(T) * float(V)
    return {"ok": True, "P_req_W": P, "T": float(T), "V": float(V)}


def stall_speed(W: float, rho: float, S: float, CLmax: float) -> dict:
    """
    Aircraft stall speed.

    V_stall = √(2W / (ρ S CL_max))

    Parameters
    ----------
    W : float
        Aircraft weight (N). Must be > 0.
    rho : float
        Air density (kg/m³). Must be > 0.
    S : float
        Wing reference area (m²). Must be > 0.
    CLmax : float
        Maximum lift coefficient. Must be > 0.

    Returns
    -------
    dict with keys: ok, V_stall_m_s, W, rho, S, CLmax
    """
    for name, val in (("W", W), ("rho", rho), ("S", S), ("CLmax", CLmax)):
        err = _validate_positive(name, val)
        if err:
            return {"ok": False, "reason": err}
    W_f = float(W)
    rho_f = float(rho)
    S_f = float(S)
    CLmax_f = float(CLmax)
    under_root = 2.0 * W_f / (rho_f * S_f * CLmax_f)
    if under_root < 0.0:
        warnings.warn(
            "Stall speed: negative value under square root; check inputs.",
            stacklevel=2,
        )
        return {"ok": False, "reason": "Negative value under square root in stall speed"}
    V_stall = math.sqrt(under_root)
    return {
        "ok": True,
        "V_stall_m_s": V_stall,
        "W": W_f,
        "rho": rho_f,
        "S": S_f,
        "CLmax": CLmax_f,
    }


# ---------------------------------------------------------------------------
# Climb performance
# ---------------------------------------------------------------------------

def climb_rate(T: float, D: float, V: float, W: float) -> dict:
    """
    Rate of climb (excess power method).

    RC = (T − D) × V / W   (m/s)

    Issues a warning if RC ≤ 0 (insufficient thrust for climb or descent).

    Parameters
    ----------
    T : float
        Available thrust (N). Must be >= 0.
    D : float
        Drag at the climb airspeed (N). Must be >= 0.
    V : float
        True airspeed (m/s). Must be > 0.
    W : float
        Aircraft weight (N). Must be > 0.

    Returns
    -------
    dict with keys: ok, RC_m_s, T, D, V, W, excess_thrust_N, negative_climb (bool)
    """
    err = _validate_positive("T", T, zero_ok=True)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("D", D, zero_ok=True)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("V", V)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("W", W)
    if err:
        return {"ok": False, "reason": err}
    T_f, D_f, V_f, W_f = float(T), float(D), float(V), float(W)
    excess = T_f - D_f
    RC = excess * V_f / W_f
    negative = RC <= 0.0
    if negative:
        warnings.warn(
            f"Climb rate RC={RC:.3f} m/s is non-positive; "
            "insufficient thrust margin for climb.",
            stacklevel=2,
        )
    return {
        "ok": True,
        "RC_m_s": RC,
        "T": T_f,
        "D": D_f,
        "V": V_f,
        "W": W_f,
        "excess_thrust_N": excess,
        "negative_climb": negative,
    }


# ---------------------------------------------------------------------------
# Propulsion: Actuator disc / ideal propeller
# ---------------------------------------------------------------------------

def actuator_disc_thrust(
    rho: float,
    A_disc: float,
    V_inf: float,
    w: float,
) -> dict:
    """
    Ideal thrust from actuator-disc (Froude momentum) theory.

    Thrust:   T = 2 ρ A (V_inf + w) w
    Power in: P_in = T × (V_inf + w)  =  2 ρ A (V_inf + w)² w

    where w is the induced velocity at the disc plane.

    Parameters
    ----------
    rho : float
        Air density (kg/m³). Must be > 0.
    A_disc : float
        Propeller disc area (m²) = π r² for radius r. Must be > 0.
    V_inf : float
        Freestream (inflow) velocity (m/s). Must be >= 0.
    w : float
        Induced velocity at disc (m/s). Must be > 0.

    Returns
    -------
    dict with keys: ok, T_N, P_in_W, rho, A_disc, V_inf, w
    """
    err = _validate_positive("rho", rho)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("A_disc", A_disc)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("V_inf", V_inf, zero_ok=True)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("w", w)
    if err:
        return {"ok": False, "reason": err}
    rho_f = float(rho)
    A_f = float(A_disc)
    V_f = float(V_inf)
    w_f = float(w)
    T = 2.0 * rho_f * A_f * (V_f + w_f) * w_f
    P_in = T * (V_f + w_f)
    return {
        "ok": True,
        "T_N": T,
        "P_in_W": P_in,
        "rho": rho_f,
        "A_disc": A_f,
        "V_inf": V_f,
        "w": w_f,
    }


def propeller_ideal_efficiency(V_inf: float, w: float) -> dict:
    """
    Ideal propulsive efficiency from actuator-disc theory.

    η = V_inf / (V_inf + w) = 1 / (1 + w/V_inf)

    Issues a warning if V_inf ≈ 0 (static-thrust / hover; η → 0 is expected).

    Parameters
    ----------
    V_inf : float
        Freestream velocity (m/s). Must be >= 0.
    w : float
        Induced velocity (m/s). Must be > 0.

    Returns
    -------
    dict with keys: ok, eta_ideal, V_inf, w, static_thrust_note (bool)
    """
    err = _validate_positive("V_inf", V_inf, zero_ok=True)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("w", w)
    if err:
        return {"ok": False, "reason": err}
    V_f = float(V_inf)
    w_f = float(w)
    static = V_f < 1e-6
    if static:
        warnings.warn(
            "V_inf ≈ 0: static thrust condition; ideal efficiency → 0 "
            "(all power goes to kinetic energy of slipstream, not useful work).",
            stacklevel=2,
        )
        eta = 0.0
    else:
        eta = V_f / (V_f + w_f)
    return {
        "ok": True,
        "eta_ideal": eta,
        "V_inf": V_f,
        "w": w_f,
        "static_thrust_note": static,
    }


# ---------------------------------------------------------------------------
# Breguet range and endurance
# ---------------------------------------------------------------------------

def breguet_range(
    eta_p: float,
    c_specific: float,
    LD: float,
    W_initial: float,
    W_final: float,
) -> dict:
    """
    Breguet range equation for propeller-driven aircraft.

    R = (η_p / c) × (L/D) × ln(W_i / W_f)   (metres)

    where c_specific is the specific fuel consumption in N/(W·s) = kg/(N·s).

    Parameters
    ----------
    eta_p : float
        Propeller efficiency (dimensionless). Must be in (0, 1].
    c_specific : float
        Specific fuel consumption (kg/(N·s) or equivalently 1/m).
        Must be > 0.  Typical piston: ~8e-8 kg/(N·s).
    LD : float
        Lift-to-drag ratio. Must be > 0.
    W_initial : float
        Initial (take-off) weight (N). Must be > W_final.
    W_final : float
        Final (landing) weight (N). Must be > 0.

    Returns
    -------
    dict with keys: ok, range_m, range_km, eta_p, c_specific, LD, W_initial, W_final
    """
    err = _validate_positive("eta_p", eta_p)
    if err:
        return {"ok": False, "reason": err}
    if float(eta_p) > 1.0:
        return {"ok": False, "reason": "eta_p must be <= 1"}
    err = _validate_positive("c_specific", c_specific)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("LD", LD)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("W_initial", W_initial)
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive("W_final", W_final)
    if err:
        return {"ok": False, "reason": err}
    eta_f = float(eta_p)
    c_f = float(c_specific)
    LD_f = float(LD)
    Wi = float(W_initial)
    Wf = float(W_final)
    if Wi <= Wf:
        return {
            "ok": False,
            "reason": "W_initial must be > W_final (fuel must be consumed)",
        }
    R = (eta_f / c_f) * LD_f * math.log(Wi / Wf)
    return {
        "ok": True,
        "range_m": R,
        "range_km": R / 1000.0,
        "eta_p": eta_f,
        "c_specific": c_f,
        "LD": LD_f,
        "W_initial": Wi,
        "W_final": Wf,
    }


def breguet_endurance(
    eta_p: float,
    c_specific: float,
    CL: float,
    CD: float,
    W_initial: float,
    W_final: float,
) -> dict:
    """
    Breguet endurance for propeller-driven aircraft (fuel-weight form).

    E = (η_p / c) × (CL / CD) × (1/g) × ln(W_i / W_f)   (seconds)

    where g = 9.80665 m/s².

    Parameters
    ----------
    eta_p : float
        Propeller efficiency. Must be in (0, 1].
    c_specific : float
        Specific fuel consumption (kg/(N·s)). Must be > 0.
    CL : float
        Lift coefficient at endurance condition. Must be > 0.
    CD : float
        Drag coefficient at endurance condition. Must be > 0.
    W_initial : float
        Initial weight (N). Must be > W_final.
    W_final : float
        Final weight (N). Must be > 0.

    Returns
    -------
    dict with keys: ok, endurance_s, endurance_hr, eta_p, c_specific, CL, CD,
                    LD, W_initial, W_final
    """
    err = _validate_positive("eta_p", eta_p)
    if err:
        return {"ok": False, "reason": err}
    if float(eta_p) > 1.0:
        return {"ok": False, "reason": "eta_p must be <= 1"}
    for name, val in (
        ("c_specific", c_specific), ("CL", CL), ("CD", CD),
        ("W_initial", W_initial), ("W_final", W_final),
    ):
        err = _validate_positive(name, val)
        if err:
            return {"ok": False, "reason": err}
    eta_f = float(eta_p)
    c_f = float(c_specific)
    CL_f = float(CL)
    CD_f = float(CD)
    Wi = float(W_initial)
    Wf = float(W_final)
    if Wi <= Wf:
        return {
            "ok": False,
            "reason": "W_initial must be > W_final (fuel must be consumed)",
        }
    LD = CL_f / CD_f
    E = (eta_f / c_f) * LD * (1.0 / _G0) * math.log(Wi / Wf)
    return {
        "ok": True,
        "endurance_s": E,
        "endurance_hr": E / 3600.0,
        "eta_p": eta_f,
        "c_specific": c_f,
        "CL": CL_f,
        "CD": CD_f,
        "LD": LD,
        "W_initial": Wi,
        "W_final": Wf,
    }
