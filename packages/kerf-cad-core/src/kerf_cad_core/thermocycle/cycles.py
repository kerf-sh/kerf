"""
kerf_cad_core.thermocycle.cycles — ideal-gas process relations and standard cycles.

Air-standard assumptions are used throughout:
  - Working fluid is air treated as an ideal gas.
  - All processes are internally reversible (ideal / isentropic where noted).
  - cp_air = 1.005 kJ/kg·K, cv_air = 0.718 kJ/kg·K, k_air = 1.4, R_air = 0.287 kJ/kg·K

Impossible states (efficiency > Carnot, invalid state combinations) are flagged
via the standard library ``warnings`` module and never raise exceptions.

Units: SI throughout — Pa, K, J/kg (specific quantities), kJ/kg where noted.

References
----------
Cengel, Y.A. & Boles, M.A., "Thermodynamics: An Engineering Approach", 8th ed.
Moran, M.J. et al., "Fundamentals of Engineering Thermodynamics", 7th ed.

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import Optional

from kerf_cad_core.fluids.steam import steam_properties as _steam_props


# ---------------------------------------------------------------------------
# Air-standard constant properties
# ---------------------------------------------------------------------------

CP_AIR = 1005.0    # J/kg·K
CV_AIR = 717.86    # J/kg·K  (= R/(k-1), using k=1.4, R=287 J/kg·K)
K_AIR  = 1.4       # specific heat ratio (isentropic exponent)
R_AIR  = 287.0     # J/kg·K  (specific gas constant for air)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ok(**kwargs) -> dict:
    return {"ok": True, **kwargs}


def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _validate_positive(*pairs: tuple) -> Optional[dict]:
    """Return error dict if any named value is non-positive, else None."""
    for name, val in pairs:
        if val is None:
            return _err(f"{name} is required")
        if not isinstance(val, (int, float)):
            return _err(f"{name} must be a number")
        if val <= 0:
            return _err(f"{name} must be > 0")
    return None


def _validate_positive_or_zero(*pairs: tuple) -> Optional[dict]:
    """Return error dict if any named value is negative, else None."""
    for name, val in pairs:
        if val is None:
            return _err(f"{name} is required")
        if not isinstance(val, (int, float)):
            return _err(f"{name} must be a number")
        if val < 0:
            return _err(f"{name} must be >= 0")
    return None


# ---------------------------------------------------------------------------
# Isentropic relations (ideal gas with constant k)
# ---------------------------------------------------------------------------

def isentropic_relations(
    T1: float,
    p1: float,
    *,
    T2: Optional[float] = None,
    p2: Optional[float] = None,
    v1: Optional[float] = None,
    v2: Optional[float] = None,
    k: float = K_AIR,
) -> dict:
    """Isentropic relations for an ideal gas with constant specific-heat ratio k.

    Computes the unknown state-2 property (T2 or p2) from one pair of inputs.
    At least one of (T2, p2, v2/v1) must be supplied.

    Relations:
        T2/T1 = (p2/p1)^((k-1)/k)
        T2/T1 = (v1/v2)^(k-1)
        p2/p1 = (v1/v2)^k

    Parameters
    ----------
    T1 : float   Initial temperature (K). Must be > 0.
    p1 : float   Initial pressure (Pa). Must be > 0.
    T2 : float, optional   Final temperature (K).
    p2 : float, optional   Final pressure (Pa).
    v1 : float, optional   Specific volume at state 1 (m³/kg). Must be > 0 if given.
    v2 : float, optional   Specific volume at state 2 (m³/kg). Must be > 0 if given.
    k  : float   Specific heat ratio (default 1.4 for air).

    Returns
    -------
    dict with ok, T1, T2, p1, p2, pressure_ratio, temp_ratio, k
    """
    e = _validate_positive(("T1", T1), ("p1", p1), ("k", k))
    if e:
        return e

    if k <= 1.0:
        return _err("k must be > 1.0 for an ideal gas with internal energy")

    # Determine what we can compute
    if T2 is not None and T2 > 0:
        temp_ratio = T2 / T1
        p2_calc = p1 * temp_ratio ** (k / (k - 1.0))
        if p2 is not None and abs(p2 / p2_calc - 1.0) > 1e-4:
            warnings.warn(
                f"isentropic_relations: supplied p2={p2} Pa inconsistent with "
                f"computed p2={p2_calc:.4g} Pa from T ratio; using T2.",
                stacklevel=2,
            )
        p2_out = p2_calc
        T2_out = T2
    elif p2 is not None and p2 > 0:
        pressure_ratio = p2 / p1
        T2_out = T1 * pressure_ratio ** ((k - 1.0) / k)
        p2_out = p2
    elif v1 is not None and v2 is not None:
        e2 = _validate_positive(("v1", v1), ("v2", v2))
        if e2:
            return e2
        vr = v1 / v2
        T2_out = T1 * vr ** (k - 1.0)
        p2_out = p1 * vr ** k
    else:
        return _err(
            "One of T2, p2, or (v1, v2) must be provided to fix isentropic state 2"
        )

    pressure_ratio = p2_out / p1
    temp_ratio     = T2_out / T1

    return _ok(
        T1=T1, T2=T2_out,
        p1=p1, p2=p2_out,
        pressure_ratio=pressure_ratio,
        temp_ratio=temp_ratio,
        k=k,
    )


# ---------------------------------------------------------------------------
# Ideal-gas process relations (per unit mass, J/kg)
# ---------------------------------------------------------------------------

def isothermal_process(
    p1: float,
    v1: float,
    v2: float,
    *,
    T: Optional[float] = None,
) -> dict:
    """Isothermal (constant-temperature) process for an ideal gas.

    p·v = R·T = const   →   p2 = p1·v1/v2
    Work (per unit mass): w = p1·v1 · ln(v2/v1)  [J/kg]
    Heat:                 q = w   (since Δu = 0 for ideal gas at const T)

    Parameters
    ----------
    p1 : float   Initial pressure (Pa).
    v1 : float   Initial specific volume (m³/kg).
    v2 : float   Final specific volume (m³/kg).
    T  : float, optional   Temperature (K); if given, used to compute R·T.

    Returns
    -------
    dict with ok, p1, p2, v1, v2, T, w_J_kg, q_J_kg, delta_u_J_kg
    """
    e = _validate_positive(("p1", p1), ("v1", v1), ("v2", v2))
    if e:
        return e

    p2 = p1 * v1 / v2
    w  = p1 * v1 * math.log(v2 / v1)   # positive when expansion
    q  = w                               # Δu = 0 → q = w
    T_out = T if (T is not None and T > 0) else (p1 * v1 / R_AIR)

    return _ok(
        p1=p1, p2=p2, v1=v1, v2=v2, T=T_out,
        w_J_kg=w, q_J_kg=q, delta_u_J_kg=0.0,
    )


def isobaric_process(
    T1: float,
    T2: float,
    *,
    cp: float = CP_AIR,
) -> dict:
    """Isobaric (constant-pressure) process for an ideal gas.

    q  = cp · (T2 - T1)   [J/kg]
    w  = R · (T2 - T1)    [J/kg]  (boundary work; uses R = cp - cv for air)
    Δu = cv · (T2 - T1)   [J/kg]

    Parameters
    ----------
    T1 : float   Initial temperature (K).
    T2 : float   Final temperature (K).
    cp : float   Specific heat at constant pressure (J/kg·K). Default CP_AIR.

    Returns
    -------
    dict with ok, T1, T2, q_J_kg, w_J_kg, delta_u_J_kg, cp, cv, T_ratio
    """
    e = _validate_positive(("T1", T1), ("T2", T2), ("cp", cp))
    if e:
        return e

    # Derive cv from cp via cp - cv = R; assume air k unless cp/R leads elsewhere
    # Use exact relationship: cv = cp / k for constant k.  For custom cp, use
    # the air k=1.4 by default.
    k  = K_AIR
    cv = cp / k
    R  = cp - cv

    q      = cp * (T2 - T1)
    delta_u = cv * (T2 - T1)
    w      = R  * (T2 - T1)          # = q - Δu = boundary work

    return _ok(
        T1=T1, T2=T2, T_ratio=T2 / T1,
        q_J_kg=q, w_J_kg=w, delta_u_J_kg=delta_u,
        cp=cp, cv=cv,
    )


def isochoric_process(
    T1: float,
    T2: float,
    *,
    cv: float = CV_AIR,
) -> dict:
    """Isochoric (constant-volume) process for an ideal gas.

    q  = cv · (T2 - T1)   [J/kg]
    w  = 0                 (no boundary work at constant volume)
    Δu = q

    Parameters
    ----------
    T1 : float   Initial temperature (K).
    T2 : float   Final temperature (K).
    cv : float   Specific heat at constant volume (J/kg·K). Default CV_AIR.

    Returns
    -------
    dict with ok, T1, T2, q_J_kg, w_J_kg, delta_u_J_kg, cv, T_ratio
    """
    e = _validate_positive(("T1", T1), ("T2", T2), ("cv", cv))
    if e:
        return e

    q = cv * (T2 - T1)

    return _ok(
        T1=T1, T2=T2, T_ratio=T2 / T1,
        q_J_kg=q, w_J_kg=0.0, delta_u_J_kg=q,
        cv=cv,
    )


def isentropic_process(
    T1: float,
    p1: float,
    p2: float,
    *,
    k: float = K_AIR,
    cp: float = CP_AIR,
) -> dict:
    """Isentropic (adiabatic, reversible) compression or expansion.

    T2/T1 = (p2/p1)^((k-1)/k)
    w_s   = cp · (T1 - T2)     [J/kg]  (specific work on shaft; positive = work out)
    q     = 0

    Parameters
    ----------
    T1 : float   Initial temperature (K).
    p1 : float   Initial pressure (Pa).
    p2 : float   Final pressure (Pa).
    k  : float   Specific heat ratio (default K_AIR = 1.4).
    cp : float   Specific heat at const pressure (J/kg·K). Default CP_AIR.

    Returns
    -------
    dict with ok, T1, T2, p1, p2, pressure_ratio, w_s_J_kg, q_J_kg, k, cp
    """
    e = _validate_positive(("T1", T1), ("p1", p1), ("p2", p2), ("k", k), ("cp", cp))
    if e:
        return e
    if k <= 1.0:
        return _err("k must be > 1.0")

    pr    = p2 / p1
    T2    = T1 * pr ** ((k - 1.0) / k)
    w_s   = cp * (T1 - T2)   # positive = expansion work out

    return _ok(
        T1=T1, T2=T2, p1=p1, p2=p2,
        pressure_ratio=pr,
        w_s_J_kg=w_s, q_J_kg=0.0,
        k=k, cp=cp,
    )


def polytropic_process(
    p1: float,
    v1: float,
    v2: float,
    n: float,
    *,
    T1: Optional[float] = None,
) -> dict:
    """Polytropic process: p · v^n = const.

    p2   = p1 · (v1/v2)^n
    w    = (p2·v2 - p1·v1) / (1 - n)   for n ≠ 1  [J/kg]
    w    = p1·v1 · ln(v2/v1)            for n = 1  (isothermal)
    T2/T1 = p2·v2 / (p1·v1)            (ideal gas)

    q is computed from Δu + w using cv for air.

    Parameters
    ----------
    p1 : float   Initial pressure (Pa).
    v1 : float   Initial specific volume (m³/kg).
    v2 : float   Final specific volume (m³/kg).
    n  : float   Polytropic index.  n=0: isobaric, n=1: isothermal,
                 n=k: isentropic, n=∞: isochoric (passed as large number).
    T1 : float, optional   Initial temperature (K). Used to compute T2 if given.

    Returns
    -------
    dict with ok, p1, p2, v1, v2, n, w_J_kg, delta_u_J_kg, q_J_kg, T1, T2
    """
    e = _validate_positive(("p1", p1), ("v1", v1), ("v2", v2))
    if e:
        return e

    p2 = p1 * (v1 / v2) ** n

    if abs(n - 1.0) < 1e-10:
        w = p1 * v1 * math.log(v2 / v1)
    else:
        w = (p2 * v2 - p1 * v1) / (1.0 - n)

    T1_out = T1 if (T1 is not None and T1 > 0) else (p1 * v1 / R_AIR)
    T2_out = T1_out * (p2 * v2) / (p1 * v1)

    delta_u = CV_AIR * (T2_out - T1_out)
    q       = delta_u + w

    return _ok(
        p1=p1, p2=p2, v1=v1, v2=v2, n=n,
        T1=T1_out, T2=T2_out,
        w_J_kg=w, delta_u_J_kg=delta_u, q_J_kg=q,
    )


# ---------------------------------------------------------------------------
# Carnot limits
# ---------------------------------------------------------------------------

def carnot_efficiency(T_H: float, T_L: float) -> dict:
    """Maximum (Carnot) thermal efficiency of a heat engine.

    η_Carnot = 1 - T_L / T_H

    Parameters
    ----------
    T_H : float   High-temperature reservoir temperature (K). Must be > T_L > 0.
    T_L : float   Low-temperature reservoir temperature (K). Must be > 0.

    Returns
    -------
    dict with ok, eta_carnot, T_H, T_L, W_net_per_Q_H
    """
    e = _validate_positive(("T_H", T_H), ("T_L", T_L))
    if e:
        return e
    if T_L >= T_H:
        return _err("T_H must be > T_L for a heat engine")

    eta = 1.0 - T_L / T_H

    return _ok(T_H=T_H, T_L=T_L, eta_carnot=eta, W_net_per_Q_H=eta)


def carnot_cop_refrigeration(T_H: float, T_L: float) -> dict:
    """Maximum (reverse-Carnot) COP for a refrigeration cycle.

    COP_R = T_L / (T_H - T_L)

    Parameters
    ----------
    T_H : float   High-temperature reservoir temperature (K). Must be > T_L > 0.
    T_L : float   Low-temperature reservoir temperature (K). Must be > 0.

    Returns
    -------
    dict with ok, COP_R, T_H, T_L
    """
    e = _validate_positive(("T_H", T_H), ("T_L", T_L))
    if e:
        return e
    if T_L >= T_H:
        return _err("T_H must be > T_L for a refrigeration cycle")

    cop = T_L / (T_H - T_L)

    return _ok(T_H=T_H, T_L=T_L, COP_R=cop)


def carnot_cop_heat_pump(T_H: float, T_L: float) -> dict:
    """Maximum (reverse-Carnot) COP for a heat-pump cycle.

    COP_HP = T_H / (T_H - T_L)  = 1 + COP_R

    Parameters
    ----------
    T_H : float   High-temperature reservoir (desired heat output) (K). Must be > T_L > 0.
    T_L : float   Low-temperature source (K). Must be > 0.

    Returns
    -------
    dict with ok, COP_HP, T_H, T_L
    """
    e = _validate_positive(("T_H", T_H), ("T_L", T_L))
    if e:
        return e
    if T_L >= T_H:
        return _err("T_H must be > T_L for a heat-pump cycle")

    cop = T_H / (T_H - T_L)

    return _ok(T_H=T_H, T_L=T_L, COP_HP=cop)


# ---------------------------------------------------------------------------
# Air-standard Otto cycle
# ---------------------------------------------------------------------------

def otto_cycle(
    r: float,
    T1: float,
    T3: float,
    *,
    k: float = K_AIR,
    cp: float = CP_AIR,
    cv: float = CV_AIR,
) -> dict:
    """Air-standard Otto cycle (ideal spark-ignition engine).

    States: 1 (BDC start), 2 (TDC after isentropic compression),
            3 (after const-volume heat addition), 4 (BDC after isentropic expansion).

    Compression ratio: r = v1/v2
    η_Otto = 1 - 1/r^(k-1)
    T2 = T1 · r^(k-1)
    T4 = T3 / r^(k-1)
    q_in  = cv · (T3 - T2)   [J/kg]
    q_out = cv · (T4 - T1)   [J/kg]
    w_net = q_in - q_out      [J/kg]
    MEP   = w_net / (v1 - v2) [Pa]  — mean effective pressure

    Flags a warning if supplied efficiency would exceed Carnot (impossible).

    Parameters
    ----------
    r  : float   Compression ratio v1/v2. Must be > 1.
    T1 : float   Temperature at state 1 (K). Must be > 0.
    T3 : float   Temperature at state 3 (peak, after heat addition) (K). Must be > T2.
    k  : float   Specific heat ratio (default 1.4).
    cp : float   cp (J/kg·K).
    cv : float   cv (J/kg·K).

    Returns
    -------
    dict with ok, T1, T2, T3, T4, r, k,
          eta_otto, q_in_J_kg, q_out_J_kg, w_net_J_kg, MEP_Pa
    """
    e = _validate_positive(("r", r), ("T1", T1), ("T3", T3), ("k", k))
    if e:
        return e
    if r <= 1.0:
        return _err("compression ratio r must be > 1.0")
    if k <= 1.0:
        return _err("k must be > 1.0")

    T2 = T1 * r ** (k - 1.0)
    if T3 <= T2:
        return _err(
            f"T3 ({T3} K) must be > T2 ({T2:.2f} K); "
            "heat addition must raise temperature"
        )

    T4   = T3 / r ** (k - 1.0)
    eta  = 1.0 - 1.0 / r ** (k - 1.0)

    q_in  = cv * (T3 - T2)
    q_out = cv * (T4 - T1)
    w_net = q_in - q_out

    # Check η vs Carnot (T_H = T3, T_L = T1)
    eta_carnot = 1.0 - T1 / T3
    if eta > eta_carnot + 1e-9:
        warnings.warn(
            f"otto_cycle: computed η={eta:.4f} exceeds Carnot limit {eta_carnot:.4f} "
            f"for T_H={T3} K, T_L={T1} K. Check inputs.",
            stacklevel=2,
        )

    # Specific volumes for MEP (ideal gas; p1 = 1 atm assumed for relative MEP)
    # MEP = w_net / (v1 - v2); v1 = R T1/p1, v2 = v1/r
    # Expressed per unit mass: MEP proportional, but we compute symbolically.
    # Use p1=1 atm as a normalised reference so the user can scale.
    p1_ref = 101_325.0  # Pa (1 atm reference)
    v1_ref = R_AIR * T1 / p1_ref
    v2_ref = v1_ref / r
    MEP    = w_net / (v1_ref - v2_ref)

    return _ok(
        T1=T1, T2=T2, T3=T3, T4=T4,
        r=r, k=k,
        eta_otto=eta,
        q_in_J_kg=q_in, q_out_J_kg=q_out, w_net_J_kg=w_net,
        MEP_Pa=MEP,
        eta_carnot_limit=eta_carnot,
    )


# ---------------------------------------------------------------------------
# Air-standard Diesel cycle
# ---------------------------------------------------------------------------

def diesel_cycle(
    r: float,
    r_c: float,
    T1: float,
    *,
    k: float = K_AIR,
    cp: float = CP_AIR,
    cv: float = CV_AIR,
) -> dict:
    """Air-standard Diesel cycle (ideal compression-ignition engine).

    States: 1 (BDC), 2 (TDC, end of isentropic compression),
            3 (end of constant-pressure heat addition, cutoff),
            4 (BDC after isentropic expansion).

    r   = v1/v2  (compression ratio)
    r_c = v3/v2  (cutoff ratio; r_c > 1)
    η_Diesel = 1 - (r_c^k - 1) / (k · r^(k-1) · (r_c - 1))

    Parameters
    ----------
    r   : float   Compression ratio. Must be > 1.
    r_c : float   Cutoff ratio v3/v2. Must be in (1, r).
    T1  : float   Temperature at state 1 (K). Must be > 0.
    k   : float   Specific heat ratio (default 1.4).
    cp  : float   cp (J/kg·K).
    cv  : float   cv (J/kg·K).

    Returns
    -------
    dict with ok, T1, T2, T3, T4, r, r_c, k,
          eta_diesel, q_in_J_kg, q_out_J_kg, w_net_J_kg, MEP_Pa
    """
    e = _validate_positive(("r", r), ("r_c", r_c), ("T1", T1), ("k", k))
    if e:
        return e
    if r <= 1.0:
        return _err("compression ratio r must be > 1.0")
    if r_c <= 1.0:
        return _err("cutoff ratio r_c must be > 1.0")
    if r_c >= r:
        return _err("cutoff ratio r_c must be < compression ratio r")
    if k <= 1.0:
        return _err("k must be > 1.0")

    T2 = T1 * r ** (k - 1.0)
    T3 = T2 * r_c                          # constant-pressure heat addition
    T4 = T3 * (r_c / r) ** (k - 1.0)      # isentropic expansion back to v1

    q_in  = cp * (T3 - T2)
    q_out = cv * (T4 - T1)
    w_net = q_in - q_out
    eta   = 1.0 - q_out / q_in

    # MEP reference
    p1_ref = 101_325.0
    v1_ref = R_AIR * T1 / p1_ref
    v2_ref = v1_ref / r
    MEP    = w_net / (v1_ref - v2_ref)

    eta_carnot = 1.0 - T1 / T3
    if eta > eta_carnot + 1e-9:
        warnings.warn(
            f"diesel_cycle: computed η={eta:.4f} exceeds Carnot limit {eta_carnot:.4f}. "
            "Check inputs.",
            stacklevel=2,
        )

    return _ok(
        T1=T1, T2=T2, T3=T3, T4=T4,
        r=r, r_c=r_c, k=k,
        eta_diesel=eta,
        q_in_J_kg=q_in, q_out_J_kg=q_out, w_net_J_kg=w_net,
        MEP_Pa=MEP,
        eta_carnot_limit=eta_carnot,
    )


# ---------------------------------------------------------------------------
# Air-standard Dual (mixed) cycle
# ---------------------------------------------------------------------------

def dual_cycle(
    r: float,
    r_p: float,
    r_c: float,
    T1: float,
    *,
    k: float = K_AIR,
    cp: float = CP_AIR,
    cv: float = CV_AIR,
) -> dict:
    """Air-standard Dual (mixed) cycle.

    Heat is added partly at constant volume (2→3, pressure ratio r_p)
    and partly at constant pressure (3→4, cutoff ratio r_c).

    States: 1 BDC, 2 TDC (isentropic compression),
            3 end of const-volume heat addition,
            4 end of const-pressure heat addition,
            5 BDC (isentropic expansion).

    Parameters
    ----------
    r   : float   Compression ratio v1/v2. Must be > 1.
    r_p : float   Pressure ratio at const-volume addition p3/p2. Must be >= 1.
    r_c : float   Cutoff ratio v4/v3. Must be >= 1.
    T1  : float   Temperature at state 1 (K). Must be > 0.
    k   : float   Specific heat ratio (default 1.4).

    Returns
    -------
    dict with ok, T1..T5, r, r_p, r_c, k,
          eta_dual, q_in_J_kg, q_out_J_kg, w_net_J_kg, MEP_Pa
    """
    e = _validate_positive(("r", r), ("r_p", r_p), ("r_c", r_c), ("T1", T1), ("k", k))
    if e:
        return e
    if r <= 1.0:
        return _err("compression ratio r must be > 1.0")
    if r_p < 1.0:
        return _err("pressure ratio r_p must be >= 1.0")
    if r_c < 1.0:
        return _err("cutoff ratio r_c must be >= 1.0")
    if k <= 1.0:
        return _err("k must be > 1.0")

    T2 = T1 * r ** (k - 1.0)
    T3 = T2 * r_p                   # const-volume heat addition
    T4 = T3 * r_c                   # const-pressure heat addition
    # Isentropic expansion 4→5 (back to BDC v5=v1):
    # v4 = v2 * r_c = (v1/r) * r_c  →  v4/v5 = r_c/r
    T5 = T4 * (r_c / r) ** (k - 1.0)            # isentropic expansion 4→5

    q_in_v  = cv * (T3 - T2)
    q_in_p  = cp * (T4 - T3)
    q_in    = q_in_v + q_in_p
    q_out   = cv * (T5 - T1)
    w_net   = q_in - q_out
    eta     = w_net / q_in if q_in > 0 else 0.0

    p1_ref  = 101_325.0
    v1_ref  = R_AIR * T1 / p1_ref
    v2_ref  = v1_ref / r
    MEP     = w_net / (v1_ref - v2_ref)

    eta_carnot = 1.0 - T1 / T4
    if eta > eta_carnot + 1e-9:
        warnings.warn(
            f"dual_cycle: computed η={eta:.4f} exceeds Carnot limit {eta_carnot:.4f}. "
            "Check inputs.",
            stacklevel=2,
        )

    return _ok(
        T1=T1, T2=T2, T3=T3, T4=T4, T5=T5,
        r=r, r_p=r_p, r_c=r_c, k=k,
        q_in_v_J_kg=q_in_v, q_in_p_J_kg=q_in_p,
        eta_dual=eta,
        q_in_J_kg=q_in, q_out_J_kg=q_out, w_net_J_kg=w_net,
        MEP_Pa=MEP,
        eta_carnot_limit=eta_carnot,
    )


# ---------------------------------------------------------------------------
# Air-standard Brayton cycle (with optional regeneration and real efficiencies)
# ---------------------------------------------------------------------------

def brayton_cycle(
    r_p: float,
    T1: float,
    T3: float,
    *,
    k: float = K_AIR,
    cp: float = CP_AIR,
    eta_c: float = 1.0,
    eta_t: float = 1.0,
    eta_regen: float = 0.0,
) -> dict:
    """Air-standard Brayton cycle (gas-turbine cycle).

    Ideal (eta_c=eta_t=1) or with isentropic efficiencies.
    Optional regeneration (heat exchanger) pre-heats compressed air.

    States (ideal): 1 compressor inlet, 2 compressor exit,
                    3 turbine inlet (after combustor), 4 turbine exit.
    With regeneration: state 5 (after regenerator, before turbine exhaust rejects heat).

    η_cycle = w_net / q_in

    Parameters
    ----------
    r_p     : float   Pressure ratio p2/p1 = p3/p4. Must be > 1.
    T1      : float   Compressor inlet temperature (K). Must be > 0.
    T3      : float   Turbine inlet temperature (K). Must be > T2.
    k       : float   Specific heat ratio (default 1.4).
    cp      : float   cp (J/kg·K).
    eta_c   : float   Isentropic efficiency of compressor (0, 1]. Default 1.0 (ideal).
    eta_t   : float   Isentropic efficiency of turbine (0, 1]. Default 1.0 (ideal).
    eta_regen : float Regenerator effectiveness [0, 1). 0 = no regeneration (default).

    Returns
    -------
    dict with ok, T1, T2s, T2, T3, T4s, T4, T_regen,
          r_p, k, eta_c, eta_t, eta_regen,
          w_c_J_kg, w_t_J_kg, w_net_J_kg, q_in_J_kg,
          eta_brayton, back_work_ratio, bwr
    """
    e = _validate_positive(
        ("r_p", r_p), ("T1", T1), ("T3", T3), ("k", k), ("cp", cp),
        ("eta_c", eta_c), ("eta_t", eta_t),
    )
    if e:
        return e
    e2 = _validate_positive_or_zero(("eta_regen", eta_regen))
    if e2:
        return e2
    if r_p <= 1.0:
        return _err("pressure ratio r_p must be > 1.0")
    if eta_c <= 0 or eta_c > 1.0:
        return _err("eta_c must be in (0, 1]")
    if eta_t <= 0 or eta_t > 1.0:
        return _err("eta_t must be in (0, 1]")
    if eta_regen < 0 or eta_regen >= 1.0:
        return _err("eta_regen must be in [0, 1)")
    if k <= 1.0:
        return _err("k must be > 1.0")

    # Isentropic temperatures
    T2s = T1 * r_p ** ((k - 1.0) / k)
    T4s = T3 / r_p ** ((k - 1.0) / k)

    # Actual temperatures with component efficiencies
    T2 = T1 + (T2s - T1) / eta_c    # compressor exit (actual)
    T4 = T3 - eta_t * (T3 - T4s)    # turbine exit (actual)

    if T3 <= T2:
        return _err(
            f"T3 ({T3} K) must be > actual T2 ({T2:.2f} K); "
            "turbine inlet must be hotter than compressor exit"
        )

    # Regeneration: pre-heat compressed air from T2 to T_regen using hot turbine exhaust
    T_regen = T2 + eta_regen * (T4 - T2)

    q_in  = cp * (T3 - T_regen)    # heat addition in combustor
    w_c   = cp * (T2 - T1)         # compressor specific work (positive = work input)
    w_t   = cp * (T3 - T4)         # turbine specific work (positive = work output)
    w_net = w_t - w_c

    if q_in <= 0:
        return _err(
            "q_in <= 0: regeneration or compressor exit temperature exceeds T3; "
            "check T3 vs T2 and eta_regen."
        )

    eta   = w_net / q_in
    bwr   = w_c / w_t if w_t > 0 else float("inf")

    eta_carnot = 1.0 - T1 / T3
    if eta > eta_carnot + 1e-9:
        warnings.warn(
            f"brayton_cycle: computed η={eta:.4f} exceeds Carnot limit {eta_carnot:.4f}. "
            "Check inputs.",
            stacklevel=2,
        )

    return _ok(
        T1=T1, T2s=T2s, T2=T2, T3=T3, T4s=T4s, T4=T4,
        T_regen=T_regen,
        r_p=r_p, k=k, eta_c=eta_c, eta_t=eta_t, eta_regen=eta_regen,
        w_c_J_kg=w_c, w_t_J_kg=w_t, w_net_J_kg=w_net,
        q_in_J_kg=q_in,
        eta_brayton=eta,
        back_work_ratio=bwr, bwr=bwr,
        eta_carnot_limit=eta_carnot,
    )


# ---------------------------------------------------------------------------
# Ideal Rankine cycle (steam / vapour-power cycle)
# ---------------------------------------------------------------------------

def rankine_cycle_ideal(
    p_high: float,
    p_low: float,
    T_superheat: Optional[float],
    *,
    eta_pump: float = 1.0,
    eta_turbine: float = 1.0,
    T_reheat: Optional[float] = None,
    p_reheat: Optional[float] = None,
    n_feedwater_heaters: int = 0,
) -> dict:
    """Ideal Rankine cycle — simplified steam-table approximation.

    Uses the compressed-liquid / superheated-vapour approximation:
      - Water properties at saturation approximated by correlations.
      - Enthalpy calculation uses simplified Antoine-based saturation
        temperature to bound the cycle; intended for parametric studies,
        NOT as a substitute for IAPWS-IF97 lookup.

    Supports:
      - Basic ideal Rankine (saturated or superheated steam at turbine inlet)
      - Optional turbine/pump isentropic efficiencies
      - Single reheat stage (T_reheat at p_reheat)
      - Open feedwater heater count note (does not compute bleed fractions —
        notes their benefit on cycle efficiency)

    Saturation temperature approximation (ASHRAE simplified):
        T_sat(p) ≈ T_ref + B · ln(p / p_ref)  with calibrated constants.

    Parameters
    ----------
    p_high    : float   Boiler pressure (Pa). Must be > p_low.
    p_low     : float   Condenser pressure (Pa). Must be > 0.
    T_superheat : float or None
                  Turbine inlet (superheated) temperature (K).
                  If None, saturated vapour at p_high is assumed.
    eta_pump    : float   Isentropic pump efficiency (0, 1]. Default 1.0.
    eta_turbine : float   Isentropic turbine efficiency (0, 1]. Default 1.0.
    T_reheat    : float or None
                  Reheat temperature (K) at p_reheat. None = no reheat.
    p_reheat    : float or None
                  Reheat pressure (Pa). Required if T_reheat is given.
    n_feedwater_heaters : int
                  Number of open feedwater heaters (0-3). For informational
                  note on efficiency benefit; no bleed-fraction calculation.

    Returns
    -------
    dict with ok, T_sat_high, T_sat_low, T_turbine_in, T_condenser_in,
          h1..h4 (kJ/kg), w_pump_kJ_kg, w_turbine_kJ_kg, w_net_kJ_kg,
          q_in_kJ_kg, q_out_kJ_kg, eta_rankine, bwr,
          reheat_applied, feedwater_heater_note
    """
    e = _validate_positive(("p_high", p_high), ("p_low", p_low))
    if e:
        return e
    if p_high <= p_low:
        return _err("p_high must be > p_low")
    if eta_pump <= 0 or eta_pump > 1.0:
        return _err("eta_pump must be in (0, 1]")
    if eta_turbine <= 0 or eta_turbine > 1.0:
        return _err("eta_turbine must be in (0, 1]")
    if n_feedwater_heaters < 0:
        return _err("n_feedwater_heaters must be >= 0")

    # ── Saturation properties via canonical fluids.steam module ─────────────
    props_high = _steam_props(P_Pa=p_high)
    props_low  = _steam_props(P_Pa=p_low)

    if "error" in props_high:
        return _err(f"steam_properties at p_high failed: {props_high['error']}")
    if "error" in props_low:
        return _err(f"steam_properties at p_low failed: {props_low['error']}")

    T_sat_high = props_high["T_sat_C"] + 273.15   # K
    T_sat_low  = props_low["T_sat_C"] + 273.15    # K

    # Enthalpies in J/kg (canonical module returns kJ/kg → multiply by 1000)
    hf_high = props_high["hf_kJkg"] * 1000.0   # J/kg
    hg_high = props_high["hg_kJkg"] * 1000.0   # J/kg
    hf_low  = props_low["hf_kJkg"]  * 1000.0   # J/kg
    vf_low  = props_low["vf_m3kg"]              # m³/kg (from canonical)

    # ── State points (all enthalpies in J/kg, converted to kJ/kg at return) ─
    # State 1: Saturated liquid at condenser (p_low)
    h1 = hf_low

    # State 2: Compressed liquid after pump (isentropic ideal, use v_f from sat. props)
    w_pump_ideal = vf_low * (p_high - p_low)       # J/kg
    w_pump_actual = w_pump_ideal / eta_pump
    h2 = h1 + w_pump_actual                        # J/kg

    # State 3: Turbine inlet
    CP_STEAM = 2000.0   # J/kg·K (approximate for superheated steam)
    if T_superheat is not None:
        if T_superheat < T_sat_high:
            return _err(
                f"T_superheat ({T_superheat} K) must be >= T_sat(p_high) "
                f"= {T_sat_high:.2f} K"
            )
        T_turb_in = T_superheat
        # Superheated steam enthalpy: hg at p_high + cp_steam × (T_sup - T_sat_high)
        h3 = hg_high + CP_STEAM * (T_superheat - T_sat_high)
    else:
        T_turb_in = T_sat_high
        h3 = hg_high   # saturated vapour

    # State 4: Turbine exit (isentropic approximation via constant-cp steam)
    # T4s = T_turb_in * (p_low/p_high)^((k-1)/k), k_steam ≈ 1.13
    k_steam = 1.13
    T4s = T_turb_in * (p_low / p_high) ** ((k_steam - 1.0) / k_steam)
    CP_STEAM_EXP = 2000.0
    h4s = h3 - CP_STEAM_EXP * (T_turb_in - T4s)

    # Apply turbine efficiency
    w_turbine_actual = eta_turbine * (h3 - h4s)   # J/kg
    h4 = h3 - w_turbine_actual

    # ── Optional reheat ──────────────────────────────────────────────────────
    reheat_applied = False
    w_turbine_reheat = 0.0
    if T_reheat is not None:
        if p_reheat is None:
            return _err("p_reheat is required when T_reheat is given")
        e3 = _validate_positive(("T_reheat", T_reheat), ("p_reheat", p_reheat))
        if e3:
            return e3
        if p_reheat >= p_high or p_reheat <= p_low:
            return _err("p_reheat must be between p_low and p_high")
        # Reheat adds heat: h_reheat_in = h4, T enters at T_reheat
        # Additional turbine work from reheat stage (p_reheat → p_low)
        T4s_rh = T_reheat * (p_low / p_reheat) ** ((k_steam - 1.0) / k_steam)
        h_rh_out_s = h4 + CP_STEAM_EXP * (T_reheat - T4s_rh)
        w_turbine_reheat = eta_turbine * (h_rh_out_s - h4)  # negative sign handled
        # Reheat heat input
        q_reheat = CP_STEAM_EXP * (T_reheat - T4s)  # approx
        h4 = h4 + q_reheat - w_turbine_reheat        # state after second turbine
        w_turbine_actual += w_turbine_reheat
        reheat_applied = True

    # ── Cycle analysis ───────────────────────────────────────────────────────
    q_in  = h3 - h2 + (CP_STEAM_EXP * (T_reheat - T4s) if reheat_applied else 0.0)  # J/kg
    q_out = h4 - h1                                                                    # J/kg
    w_net = w_turbine_actual - w_pump_actual

    if q_in <= 0:
        return _err("q_in <= 0; check p_high, p_low and T_superheat values")

    eta   = w_net / q_in
    bwr   = w_pump_actual / w_turbine_actual if w_turbine_actual > 0 else float("inf")

    eta_carnot = 1.0 - T_sat_low / T_turb_in
    if eta > eta_carnot + 1e-9:
        warnings.warn(
            f"rankine_cycle_ideal: computed η={eta:.4f} exceeds Carnot limit "
            f"{eta_carnot:.4f}. Check inputs.",
            stacklevel=2,
        )

    # Feedwater heater note
    fwh_note = (
        f"{n_feedwater_heaters} open FWH(s) noted. "
        "Each reduces boiler heat input and typically improves η by 1-3 percentage points. "
        "Bleed fraction optimisation not computed here."
    ) if n_feedwater_heaters > 0 else "No feedwater heating."

    return _ok(
        T_sat_high_K=T_sat_high,
        T_sat_low_K=T_sat_low,
        T_turbine_in_K=T_turb_in,
        T4s_K=T4s,
        p_high_Pa=p_high,
        p_low_Pa=p_low,
        h1_kJ_kg=h1 / 1000.0,
        h2_kJ_kg=h2 / 1000.0,
        h3_kJ_kg=h3 / 1000.0,
        h4_kJ_kg=h4 / 1000.0,
        w_pump_kJ_kg=w_pump_actual / 1000.0,
        w_turbine_kJ_kg=w_turbine_actual / 1000.0,
        w_net_kJ_kg=w_net / 1000.0,
        q_in_kJ_kg=q_in / 1000.0,
        q_out_kJ_kg=q_out / 1000.0,
        eta_rankine=eta,
        bwr=bwr,
        reheat_applied=reheat_applied,
        eta_pump=eta_pump,
        eta_turbine=eta_turbine,
        feedwater_heater_note=fwh_note,
        eta_carnot_limit=eta_carnot,
    )


# ---------------------------------------------------------------------------
# Refrigeration / heat-pump COP
# ---------------------------------------------------------------------------

def refrigeration_cop(
    Q_L: float,
    W_in: float,
    *,
    T_H: Optional[float] = None,
    T_L: Optional[float] = None,
    mode: str = "refrigeration",
) -> dict:
    """Coefficient of Performance for a refrigeration or heat-pump cycle.

    COP_R  = Q_L / W_in      (refrigeration: heat removed from cold space)
    COP_HP = Q_H / W_in      (heat pump: heat delivered to hot space)
    Q_H = Q_L + W_in

    If T_H and T_L are supplied, the computed COP is checked against the
    Carnot (reverse-Carnot) limit and a warning is issued if exceeded.

    Parameters
    ----------
    Q_L    : float   Heat removed from cold reservoir per cycle (J or W). Must be > 0.
    W_in   : float   Net work input per cycle (J or W). Must be > 0.
    T_H    : float, optional   High-temperature reservoir (K).
    T_L    : float, optional   Low-temperature reservoir (K).
    mode   : str    'refrigeration' (default) or 'heat_pump'.

    Returns
    -------
    dict with ok, mode, Q_L, W_in, Q_H, COP, COP_carnot_limit (if T_H/T_L given)
    """
    e = _validate_positive(("Q_L", Q_L), ("W_in", W_in))
    if e:
        return e
    if mode not in ("refrigeration", "heat_pump"):
        return _err("mode must be 'refrigeration' or 'heat_pump'")

    Q_H = Q_L + W_in

    if mode == "refrigeration":
        COP = Q_L / W_in
        cop_label = "COP_R"
    else:
        COP = Q_H / W_in
        cop_label = "COP_HP"

    result: dict = dict(
        ok=True,
        mode=mode,
        Q_L=Q_L, W_in=W_in, Q_H=Q_H,
        **{cop_label: COP},
        COP=COP,
    )

    if T_H is not None and T_L is not None:
        e2 = _validate_positive(("T_H", T_H), ("T_L", T_L))
        if e2:
            return e2
        if T_L >= T_H:
            return _err("T_H must be > T_L")

        if mode == "refrigeration":
            COP_carnot = T_L / (T_H - T_L)
        else:
            COP_carnot = T_H / (T_H - T_L)

        result["COP_carnot_limit"] = COP_carnot
        result["T_H"] = T_H
        result["T_L"] = T_L

        if COP > COP_carnot + 1e-9:
            warnings.warn(
                f"refrigeration_cop: computed COP={COP:.4f} exceeds Carnot limit "
                f"{COP_carnot:.4f} for T_H={T_H} K, T_L={T_L} K. "
                "This is thermodynamically impossible; check inputs.",
                stacklevel=2,
            )

    return result
