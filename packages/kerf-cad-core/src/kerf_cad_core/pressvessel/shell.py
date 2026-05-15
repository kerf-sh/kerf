"""
kerf_cad_core.pressvessel.shell — ASME BPVC Section VIII Div.1 pressure-vessel sizing.

Distinct from kerf_cad_core.piping (ASME B31.3 process piping).

Implements eight public functions:

  cylindrical_shell_thickness(P, R, S, E, c)
      Minimum required thickness for a cylindrical shell under internal pressure.
      Circumferential (hoop) stress governs per UG-27(c)(1).
      Longitudinal stress check per UG-27(c)(2) also performed.

  spherical_head_thickness(P, R, S, E, c)
      Required thickness for a hemispherical head under internal pressure (UG-32(f)).

  ellipsoidal_head_thickness(P, D, S, E, c)
      Required thickness for a 2:1 semi-ellipsoidal head (UG-32(d)).
      Equivalent to a sphere of radius 0.9 × D for a 2:1 head.

  torispherical_head_thickness(P, D, S, E, c)
      Required thickness for a standard flanged-and-dished (torispherical) head
      per UG-32(e); L = D, r_knuckle = 0.06D (standard proportions).

  external_pressure_check(P_ext, D_o, L, t, E_mod, nu)
      Simplified UG-28 external-pressure / buckling check using
      a factor-A / factor-B approach with a polynomial B-chart approximation
      for carbon steel at ambient temperature.

  mawp_cylindrical(t, R, S, E, c)
      Maximum Allowable Working Pressure from a given cylindrical shell thickness,
      inverse of UG-27(c)(1).

  nozzle_reinforcement(P, D_shell, t_shell, d_nozzle, t_nozzle, S, E, c, F)
      Nozzle opening area-replacement check per UG-37.
      Returns required area A_required, available areas A1–A4, total available,
      and pass/fail.

  hydrostatic_test_pressure(MAWP, S_test, S_design)
      Hydrostatic test pressure per UG-99: 1.3 × MAWP × (S_test / S_design).

All functions return plain dicts:
    success → {"ok": True, ...fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise; code-exceedance conditions populate "warnings" list.

Units
-----
  lengths  — metres (m)
  pressure — Pascals (Pa)
  stress   — Pascals (Pa)
  E_mod    — Pascals (Pa)   (Young's modulus for external-pressure check)

References
----------
ASME BPVC Section VIII Division 1, 2021 Edition
  UG-27, UG-28, UG-32, UG-37, UG-99
Megyesy, E.F. "Pressure Vessel Handbook", 14th ed.

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings as _warnings_mod
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_positive(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


def _guard_nonneg(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < 0:
        return f"{name} must be >= 0, got {v}"
    return None


def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


# ---------------------------------------------------------------------------
# 1. cylindrical_shell_thickness — UG-27(c)(1) & UG-27(c)(2)
#
# Circumferential (hoop) stress governs (UG-27(c)(1)):
#     t_c = P·R / (S·E - 0.6·P) + c
#
# Longitudinal stress check (UG-27(c)(2)) — typically half of hoop:
#     t_l = P·R / (2·S·E + 0.4·P) + c
#
# The larger of the two is the required thickness.
# ---------------------------------------------------------------------------

def cylindrical_shell_thickness(
    P: float,
    R: float,
    S: float,
    E: float = 1.0,
    c: float = 0.0,
) -> dict:
    """
    Required minimum wall thickness for a cylindrical shell under internal pressure.

    Implements ASME BPVC VIII-1 UG-27(c):
      Circumferential stress (hoop, governs): t_circ = P·R / (S·E - 0.6·P) + c
      Longitudinal stress check:             t_long = P·R / (2·S·E + 0.4·P) + c

    Parameters
    ----------
    P : float
        Internal design pressure (Pa, gauge). Must be >= 0.
    R : float
        Inside radius of the shell (m). Must be > 0.
    S : float
        Maximum allowable stress of the material at design temperature (Pa).
        Must be > 0.  From ASME BPVC VIII-1 Section II Part D tables.
    E : float
        Joint efficiency factor (default 1.0 = full radiography).
        Typical: 1.0 (RT-1), 0.85 (RT-2), 0.70 (no RT).
        Must be in (0, 1].
    c : float
        Corrosion allowance (m). Must be >= 0.  Default 0.0.

    Returns
    -------
    dict
        ok               : True
        t_circ_m         : circumferential-stress required thickness (m)
        t_long_m         : longitudinal-stress required thickness (m)
        t_required_m     : max(t_circ, t_long) — governing thickness (m)
        t_required_mm    : same in mm
        t_no_ca_m        : required thickness before corrosion allowance (m)
        MAWP_Pa          : MAWP at the required thickness (gross, including CA)
        P_Pa             : design pressure used (Pa)
        R_m              : inside radius used (m)
        S_Pa             : allowable stress used (Pa)
        E_factor         : joint efficiency used
        c_m              : corrosion allowance used (m)
        governing        : "circumferential" | "longitudinal"
        warnings         : list of code-exceedance warning strings

    Applicability limit (UG-27 Note): formula valid when t < 0.5R.
    """
    warn_list: list[str] = []

    err = _guard_nonneg("P", P)
    if err:
        return _err(err)
    err = _guard_positive("R", R)
    if err:
        return _err(err)
    err = _guard_positive("S", S)
    if err:
        return _err(err)
    err = _guard_nonneg("c", c)
    if err:
        return _err(err)

    E_f = float(E)
    if not (0 < E_f <= 1.0):
        return _err(f"E (joint efficiency) must be in (0, 1], got {E_f}")

    P_v = float(P)
    R_v = float(R)
    S_v = float(S)
    c_v = float(c)

    # Circumferential stress governs (UG-27(c)(1))
    denom_circ = S_v * E_f - 0.6 * P_v
    if denom_circ <= 0:
        return _err(
            f"S·E - 0.6·P = {denom_circ:.2f} Pa ≤ 0; "
            "pressure exceeds material/efficiency limit for UG-27(c)(1)."
        )
    t_circ = P_v * R_v / denom_circ + c_v

    # Longitudinal stress check (UG-27(c)(2))
    denom_long = 2.0 * S_v * E_f + 0.4 * P_v
    t_long = P_v * R_v / denom_long + c_v

    t_required = max(t_circ, t_long)
    governing = "circumferential" if t_circ >= t_long else "longitudinal"

    # Applicability check: t < 0.5R
    t_net = t_required - c_v
    if t_net >= 0.5 * R_v:
        msg = (
            f"Net wall thickness {t_net*1e3:.2f} mm >= 0.5·R = {0.5*R_v*1e3:.2f} mm. "
            "UG-27 formula not valid for thick-wall vessels; "
            "use the Lamé equation or Division 3."
        )
        warn_list.append(msg)
        _warnings_mod.warn(msg, stacklevel=2)

    # MAWP at required thickness (back-calculated from circ formula)
    t_net_req = t_required - c_v
    mawp = S_v * E_f * t_net_req / (R_v + 0.6 * t_net_req)

    return {
        "ok": True,
        "t_circ_m": t_circ,
        "t_long_m": t_long,
        "t_required_m": t_required,
        "t_required_mm": t_required * 1e3,
        "t_no_ca_m": t_required - c_v,
        "MAWP_Pa": mawp,
        "P_Pa": P_v,
        "R_m": R_v,
        "S_Pa": S_v,
        "E_factor": E_f,
        "c_m": c_v,
        "governing": governing,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 2. spherical_head_thickness — UG-32(f) / UG-27(d)
#
#     t = P·R / (2·S·E - 0.2·P) + c
# ---------------------------------------------------------------------------

def spherical_head_thickness(
    P: float,
    R: float,
    S: float,
    E: float = 1.0,
    c: float = 0.0,
) -> dict:
    """
    Required thickness for a hemispherical head under internal pressure.

    Implements ASME BPVC VIII-1 UG-32(f) (same as UG-27(d)):

        t = P·R / (2·S·E - 0.2·P) + c

    Parameters
    ----------
    P : float
        Internal design pressure (Pa, gauge). Must be >= 0.
    R : float
        Inside radius of the spherical head (m). Must be > 0.
    S : float
        Maximum allowable stress (Pa). Must be > 0.
    E : float
        Joint efficiency (default 1.0). Must be in (0, 1].
    c : float
        Corrosion allowance (m). Must be >= 0.

    Returns
    -------
    dict
        ok            : True
        t_required_m  : required thickness (m)
        t_required_mm : same in mm
        t_no_ca_m     : required thickness without corrosion allowance (m)
        MAWP_Pa       : MAWP at the required thickness
        P_Pa, R_m, S_Pa, E_factor, c_m: inputs echoed
        warnings      : list of strings
    """
    warn_list: list[str] = []

    err = _guard_nonneg("P", P)
    if err:
        return _err(err)
    err = _guard_positive("R", R)
    if err:
        return _err(err)
    err = _guard_positive("S", S)
    if err:
        return _err(err)
    err = _guard_nonneg("c", c)
    if err:
        return _err(err)

    E_f = float(E)
    if not (0 < E_f <= 1.0):
        return _err(f"E (joint efficiency) must be in (0, 1], got {E_f}")

    P_v, R_v, S_v, c_v = float(P), float(R), float(S), float(c)

    denom = 2.0 * S_v * E_f - 0.2 * P_v
    if denom <= 0:
        return _err(
            f"2·S·E - 0.2·P = {denom:.2f} Pa ≤ 0; "
            "pressure exceeds material/efficiency limit for UG-32(f)."
        )

    t_req = P_v * R_v / denom + c_v

    # Applicability: t < 0.356R (equivalent thin-shell limit for sphere)
    t_net = t_req - c_v
    if t_net >= 0.356 * R_v:
        msg = (
            f"Net wall {t_net*1e3:.2f} mm >= 0.356·R = {0.356*R_v*1e3:.2f} mm; "
            "thick-wall limit exceeded for spherical head formula."
        )
        warn_list.append(msg)
        _warnings_mod.warn(msg, stacklevel=2)

    mawp = 2.0 * S_v * E_f * t_net / (R_v + 0.2 * t_net)

    return {
        "ok": True,
        "t_required_m": t_req,
        "t_required_mm": t_req * 1e3,
        "t_no_ca_m": t_net,
        "MAWP_Pa": mawp,
        "P_Pa": P_v,
        "R_m": R_v,
        "S_Pa": S_v,
        "E_factor": E_f,
        "c_m": c_v,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 3. ellipsoidal_head_thickness — UG-32(d)
#
# Standard 2:1 semi-ellipsoidal head (h = D/4):
#     t = P·D / (2·S·E - 0.2·P) + c
#
# where D is the inside shell diameter.
# This is equivalent to a sphere of radius 0.9D.
# ---------------------------------------------------------------------------

def ellipsoidal_head_thickness(
    P: float,
    D: float,
    S: float,
    E: float = 1.0,
    c: float = 0.0,
) -> dict:
    """
    Required thickness for a 2:1 semi-ellipsoidal head (UG-32(d)).

    Standard proportions: head depth h = D/4 (2:1 ratio).
    Formula:
        t = P·D / (2·S·E - 0.2·P) + c

    Parameters
    ----------
    P : float
        Internal design pressure (Pa, gauge). Must be >= 0.
    D : float
        Inside diameter of the shell/head (m). Must be > 0.
    S : float
        Maximum allowable stress (Pa). Must be > 0.
    E : float
        Joint efficiency (default 1.0). Must be in (0, 1].
    c : float
        Corrosion allowance (m). Must be >= 0.

    Returns
    -------
    dict
        ok            : True
        t_required_m  : required thickness (m)
        t_required_mm : same in mm
        t_no_ca_m     : required thickness without CA (m)
        MAWP_Pa       : MAWP at the required thickness
        head_depth_m  : head depth h = D/4 (m)
        P_Pa, D_m, S_Pa, E_factor, c_m: inputs echoed
        warnings      : list of strings
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
    err = _guard_nonneg("c", c)
    if err:
        return _err(err)

    E_f = float(E)
    if not (0 < E_f <= 1.0):
        return _err(f"E (joint efficiency) must be in (0, 1], got {E_f}")

    P_v, D_v, S_v, c_v = float(P), float(D), float(S), float(c)

    denom = 2.0 * S_v * E_f - 0.2 * P_v
    if denom <= 0:
        return _err(
            f"2·S·E - 0.2·P = {denom:.2f} Pa ≤ 0; "
            "pressure exceeds material/efficiency limit for UG-32(d)."
        )

    t_req = P_v * D_v / denom + c_v
    t_net = t_req - c_v
    mawp = (2.0 * S_v * E_f * t_net) / (D_v + 0.2 * t_net)

    return {
        "ok": True,
        "t_required_m": t_req,
        "t_required_mm": t_req * 1e3,
        "t_no_ca_m": t_net,
        "MAWP_Pa": mawp,
        "head_depth_m": D_v / 4.0,
        "P_Pa": P_v,
        "D_m": D_v,
        "S_Pa": S_v,
        "E_factor": E_f,
        "c_m": c_v,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 4. torispherical_head_thickness — UG-32(e)
#
# Standard flanged-and-dished (F&D) head with:
#   Crown radius L_crown = D (outside diameter ≈ inside diameter for thin heads)
#   Knuckle radius r_k = 0.06·D (minimum per code: r_k >= 3t and r_k >= 0.06·L)
#
# Formula (UG-32(e)):
#     t = 0.885·P·L / (S·E - 0.1·P) + c
#
# where L is the inside crown radius (= D for standard head).
# ---------------------------------------------------------------------------

def torispherical_head_thickness(
    P: float,
    D: float,
    S: float,
    E: float = 1.0,
    c: float = 0.0,
    L_crown: float | None = None,
) -> dict:
    """
    Required thickness for a standard torispherical (flanged-and-dished) head.

    Standard proportions: L_crown = D, r_knuckle = 0.06·D.
    Formula per UG-32(e):
        t = 0.885·P·L / (S·E - 0.1·P) + c

    Parameters
    ----------
    P : float
        Internal design pressure (Pa, gauge). Must be >= 0.
    D : float
        Inside diameter of the shell (m). Must be > 0.
    S : float
        Maximum allowable stress (Pa). Must be > 0.
    E : float
        Joint efficiency (default 1.0). Must be in (0, 1].
    c : float
        Corrosion allowance (m). Must be >= 0.
    L_crown : float | None
        Inside crown radius (m). Default: L_crown = D (standard proportions).
        Must be > 0 if provided.

    Returns
    -------
    dict
        ok              : True
        t_required_m    : required thickness (m)
        t_required_mm   : same in mm
        t_no_ca_m       : required thickness without CA (m)
        MAWP_Pa         : MAWP at the required thickness
        L_crown_m       : inside crown radius used (m)
        r_knuckle_m     : standard knuckle radius 0.06·D (m)
        P_Pa, D_m, S_Pa, E_factor, c_m: inputs echoed
        warnings        : list of strings
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
    err = _guard_nonneg("c", c)
    if err:
        return _err(err)

    E_f = float(E)
    if not (0 < E_f <= 1.0):
        return _err(f"E (joint efficiency) must be in (0, 1], got {E_f}")

    P_v, D_v, S_v, c_v = float(P), float(D), float(S), float(c)

    if L_crown is not None:
        err = _guard_positive("L_crown", L_crown)
        if err:
            return _err(err)
        L_v = float(L_crown)
    else:
        L_v = D_v  # standard proportions

    r_k = 0.06 * D_v  # standard knuckle radius

    denom = S_v * E_f - 0.1 * P_v
    if denom <= 0:
        return _err(
            f"S·E - 0.1·P = {denom:.2f} Pa ≤ 0; "
            "pressure exceeds material/efficiency limit for UG-32(e)."
        )

    t_req = 0.885 * P_v * L_v / denom + c_v
    t_net = t_req - c_v

    # Check knuckle radius code requirement: r_k >= 0.06·L and r_k >= 3·t_net
    if r_k < 0.06 * L_v:
        msg = (
            f"Knuckle radius r_k = {r_k*1e3:.2f} mm < 0.06·L = {0.06*L_v*1e3:.2f} mm; "
            "does not meet UG-32(e) minimum knuckle requirement."
        )
        warn_list.append(msg)
        _warnings_mod.warn(msg, stacklevel=2)

    if t_net > 0 and r_k < 3.0 * t_net:
        msg = (
            f"Knuckle radius r_k = {r_k*1e3:.2f} mm < 3·t = {3.0*t_net*1e3:.2f} mm; "
            "does not meet UG-32(e) 3t minimum knuckle requirement."
        )
        warn_list.append(msg)
        _warnings_mod.warn(msg, stacklevel=2)

    mawp = S_v * E_f * t_net / (0.885 * L_v + 0.1 * t_net)

    return {
        "ok": True,
        "t_required_m": t_req,
        "t_required_mm": t_req * 1e3,
        "t_no_ca_m": t_net,
        "MAWP_Pa": mawp,
        "L_crown_m": L_v,
        "r_knuckle_m": r_k,
        "P_Pa": P_v,
        "D_m": D_v,
        "S_Pa": S_v,
        "E_factor": E_f,
        "c_m": c_v,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 5. external_pressure_check — UG-28 simplified factor-A/factor-B
#
# For a cylindrical shell under external pressure:
#   Step 1: compute geometric factors L/D_o, D_o/t
#   Step 2: factor A from the geometric chart (approximated by polynomial fit
#           valid for the elastic buckling range):
#               A ≈ 0.125 / (L/D_o · D_o/t)   [Wineburg formula, simplified]
#           This approximation covers the common "elastic" regime.
#   Step 3: factor B — for carbon/low-alloy steel (E ≈ 200 GPa, ambient):
#               B = min(A·E/2, S_allow)
#           where S_allow is the material allowable at temperature.
#   Step 4: Allowable external pressure:
#               P_allow = 4B / (3·D_o/t)
#   Step 5: Check P_ext <= P_allow.
#
# The factor-A approximation is conservative for L/D_o > 4; for shorter vessels
# a note is added to the warnings advising use of the actual ASME charts.
# ---------------------------------------------------------------------------

def external_pressure_check(
    P_ext: float,
    D_o: float,
    L: float,
    t: float,
    E_mod: float = 200e9,
    nu: float = 0.3,
    S_allow: float | None = None,
) -> dict:
    """
    Simplified UG-28 external pressure / buckling check for a cylindrical shell.

    Uses a factor-A/factor-B approximation suitable for the elastic buckling
    regime (common for long vessels, L/D_o > 4).  For shorter vessels the
    actual ASME Section II Part D charts should be used.

    Parameters
    ----------
    P_ext : float
        External design pressure (Pa, gauge). Must be > 0.
    D_o : float
        Outside diameter of the shell (m). Must be > 0.
    L : float
        Unsupported length between stiffening rings or heads (m). Must be > 0.
    t : float
        Shell wall thickness (m). Must be > 0.
    E_mod : float
        Young's modulus of the material at design temperature (Pa).
        Default 200e9 (carbon steel, ambient). Must be > 0.
    nu : float
        Poisson's ratio (default 0.3). Must be in (0, 0.5).
    S_allow : float | None
        Allowable stress (Pa).  If None, not used to cap factor B.
        If provided, B is capped at S_allow.

    Returns
    -------
    dict
        ok               : True
        L_over_Do        : slenderness ratio L/D_o
        Do_over_t        : diameter-to-thickness ratio D_o/t
        factor_A         : factor A (geometric/elastic parameter)
        factor_B_Pa      : factor B (allowable stress, Pa)
        P_allow_Pa       : allowable external pressure (Pa)
        P_ext_Pa         : applied external pressure (Pa)
        pass_fail        : True if P_ext <= P_allow
        safety_factor    : P_allow / P_ext
        warnings         : list of strings

    Notes
    -----
    Factor-A approximation: A ≈ 0.125 / (L/D_o × D_o/t)  [UG-28 / Wineburg]
    This is valid for elastic buckling (A on the left of the chart knee).
    Factor-B: B = A·E/2  (elastic regime), capped at S_allow if provided.
    Allowable pressure: P_allow = 4B / (3·D_o/t)
    """
    warn_list: list[str] = []

    err = _guard_positive("P_ext", P_ext)
    if err:
        return _err(err)
    err = _guard_positive("D_o", D_o)
    if err:
        return _err(err)
    err = _guard_positive("L", L)
    if err:
        return _err(err)
    err = _guard_positive("t", t)
    if err:
        return _err(err)
    err = _guard_positive("E_mod", E_mod)
    if err:
        return _err(err)

    nu_v = float(nu)
    if not (0 < nu_v < 0.5):
        return _err(f"nu (Poisson's ratio) must be in (0, 0.5), got {nu_v}")

    if t >= D_o / 2.0:
        return _err(f"Wall thickness t={t} m must be < D_o/2 = {D_o/2} m")

    P_v = float(P_ext)
    D_v = float(D_o)
    L_v = float(L)
    t_v = float(t)
    E_v = float(E_mod)

    L_over_Do = L_v / D_v
    Do_over_t = D_v / t_v

    # Factor A: elastic buckling approximation (Windenburg-Trilling / UG-28 charts)
    # A ≈ 0.125 / (L/D_o × D_o/t)
    A = 0.125 / (L_over_Do * Do_over_t)

    if L_over_Do < 4.0:
        msg = (
            f"L/D_o = {L_over_Do:.2f} < 4; vessel is classified as 'short'. "
            "The simplified factor-A approximation may be non-conservative; "
            "verify with ASME Section II Part D charts or ASME VIII-1 Fig. G."
        )
        warn_list.append(msg)
        _warnings_mod.warn(msg, stacklevel=2)

    # Factor B: elastic regime — B = A·E/2
    B = A * E_v / 2.0

    # Cap at S_allow if material allowable is provided
    if S_allow is not None:
        err = _guard_positive("S_allow", S_allow)
        if err:
            return _err(err)
        S_v = float(S_allow)
        if B > S_v:
            B = S_v
            msg = (
                f"Factor B capped at S_allow = {S_v/1e6:.2f} MPa "
                "(inelastic / yield-limited regime)."
            )
            warn_list.append(msg)
            _warnings_mod.warn(msg, stacklevel=2)

    # Allowable external pressure (UG-28 step 6)
    P_allow = 4.0 * B / (3.0 * Do_over_t)

    pass_fail = P_v <= P_allow
    sf = P_allow / P_v if P_v > 0 else float("inf")

    if not pass_fail:
        msg = (
            f"External pressure P_ext = {P_v/1e3:.2f} kPa exceeds "
            f"P_allow = {P_allow/1e3:.2f} kPa. Increase wall thickness or add stiffening rings."
        )
        warn_list.append(msg)
        _warnings_mod.warn(msg, stacklevel=2)

    return {
        "ok": True,
        "L_over_Do": L_over_Do,
        "Do_over_t": Do_over_t,
        "factor_A": A,
        "factor_B_Pa": B,
        "P_allow_Pa": P_allow,
        "P_ext_Pa": P_v,
        "pass_fail": pass_fail,
        "safety_factor": sf,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 6. mawp_cylindrical — inverse of UG-27(c)(1)
#
#     MAWP = S·E·t_net / (R + 0.6·t_net)
#
# where t_net = t_nominal - c  (nominal wall minus corrosion allowance).
# ---------------------------------------------------------------------------

def mawp_cylindrical(
    t: float,
    R: float,
    S: float,
    E: float = 1.0,
    c: float = 0.0,
) -> dict:
    """
    Maximum Allowable Working Pressure for an existing cylindrical shell.

    Inverse of UG-27(c)(1):
        MAWP = S·E·t_net / (R + 0.6·t_net)
    where t_net = t - c (nominal wall minus corrosion allowance).

    Parameters
    ----------
    t : float
        Nominal wall thickness (m). Must be > 0.
    R : float
        Inside radius (m). Must be > 0.
    S : float
        Maximum allowable stress (Pa). Must be > 0.
    E : float
        Joint efficiency (default 1.0). Must be in (0, 1].
    c : float
        Corrosion allowance (m). Must be >= 0, and c < t.

    Returns
    -------
    dict
        ok           : True
        MAWP_Pa      : maximum allowable working pressure (Pa)
        MAWP_kPa     : same in kPa
        MAWP_bar     : same in bar
        MAWP_psi     : same in psi
        t_net_m      : net wall thickness after corrosion allowance (m)
        warnings     : list of strings
    """
    warn_list: list[str] = []

    err = _guard_positive("t", t)
    if err:
        return _err(err)
    err = _guard_positive("R", R)
    if err:
        return _err(err)
    err = _guard_positive("S", S)
    if err:
        return _err(err)
    err = _guard_nonneg("c", c)
    if err:
        return _err(err)

    E_f = float(E)
    if not (0 < E_f <= 1.0):
        return _err(f"E (joint efficiency) must be in (0, 1], got {E_f}")

    t_v = float(t)
    R_v = float(R)
    S_v = float(S)
    c_v = float(c)

    if c_v >= t_v:
        return _err(
            f"Corrosion allowance c={c_v*1e3:.2f} mm >= nominal wall t={t_v*1e3:.2f} mm; "
            "no remaining wall thickness."
        )

    t_net = t_v - c_v

    if t_net >= 0.5 * R_v:
        msg = (
            f"Net wall {t_net*1e3:.2f} mm >= 0.5·R = {0.5*R_v*1e3:.2f} mm; "
            "UG-27 thin-shell formula may underestimate MAWP for thick walls."
        )
        warn_list.append(msg)
        _warnings_mod.warn(msg, stacklevel=2)

    mawp = S_v * E_f * t_net / (R_v + 0.6 * t_net)

    return {
        "ok": True,
        "MAWP_Pa": mawp,
        "MAWP_kPa": mawp * 1e-3,
        "MAWP_bar": mawp * 1e-5,
        "MAWP_psi": mawp / 6894.757,
        "t_net_m": t_net,
        "t_nominal_m": t_v,
        "R_m": R_v,
        "S_Pa": S_v,
        "E_factor": E_f,
        "c_m": c_v,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 7. nozzle_reinforcement — UG-37 area-replacement method
#
# Required area to be replaced:
#     A_req = d · t_req · F
#
# where d   = finished diameter of the opening (m)
#       t_req = required shell thickness (UG-27, without CA)
#       F   = correction factor (1.0 for standard nozzles, 0.5–1.0 for angled)
#
# Available areas (UG-37(c)):
#   A1 = (2·d - d) · (E1·t_shell - F·t_req) - 2·t_n·(E1·t_shell - F·t_req)·(1-fr1)
#      = (t_shell - F·t_req) · (d - 2·t_n) · ... simplified:
#        A1 = d·(E1·t_shell_actual - F·t_req)   [in excess shell area]
#            where t_shell_actual = t_shell - c  (net shell thickness)
#
#   A2 = 5·t_n·t_n   [nozzle wall in tension, within 2.5·t_shell above shell surface]
#        for inward projection or flush nozzle (simplified conservative)
#
#   A3 = 0 (no inward nozzle projection assumed)
#   A4 = 0 (no fillet weld area added — conservative)
#
# Total available = A1 + A2 + A3 + A4 >= A_req
#
# For simplicity this implementation uses:
#   A1 = d · (t_shell_net - F·t_req)   (shell excess)
#   A2 = 5 · t_n_net · min(t_n_net, 2.5·t_shell_net)   (nozzle wall excess)
#   A_total = A1 + A2
# ---------------------------------------------------------------------------

def nozzle_reinforcement(
    P: float,
    D_shell: float,
    t_shell: float,
    d_nozzle: float,
    t_nozzle: float,
    S: float,
    E: float = 1.0,
    c: float = 0.0,
    F: float = 1.0,
) -> dict:
    """
    Nozzle opening reinforcement check per ASME BPVC VIII-1 UG-37.

    Uses the area-replacement method: the area removed by the opening must be
    replaced by excess material in the shell, nozzle wall, and/or welds.

    Parameters
    ----------
    P : float
        Internal design pressure (Pa, gauge). Must be >= 0.
    D_shell : float
        Inside diameter of the shell (m). Must be > 0.
    t_shell : float
        Nominal shell wall thickness (m). Must be > 0.
    d_nozzle : float
        Finished (inside) diameter of the opening / nozzle bore (m). Must be > 0.
    t_nozzle : float
        Nominal nozzle wall thickness (m). Must be > 0.
    S : float
        Allowable stress of the shell material (Pa). Must be > 0.
    E : float
        Joint efficiency of the shell (default 1.0). Must be in (0, 1].
    c : float
        Corrosion allowance (m, applied to both shell and nozzle). Must be >= 0.
    F : float
        Correction factor for nozzle inclination (default 1.0 for perpendicular).
        Must be in (0.5, 1.0].

    Returns
    -------
    dict
        ok                  : True
        A_required_m2       : required replacement area (m²)
        A1_shell_m2         : area available from excess shell material (m²)
        A2_nozzle_m2        : area available from nozzle wall (m²)
        A_total_m2          : total available area A1 + A2 (m²)
        reinforcement_ok    : True if A_total >= A_required
        shortfall_m2        : A_required - A_total (negative = excess) (m²)
        t_req_shell_m       : required shell thickness (UG-27, no CA) (m)
        P_Pa, D_shell_m, t_shell_m, d_nozzle_m, t_nozzle_m: inputs echoed
        warnings            : list of strings
    """
    warn_list: list[str] = []

    err = _guard_nonneg("P", P)
    if err:
        return _err(err)
    for name, val in (("D_shell", D_shell), ("t_shell", t_shell),
                      ("d_nozzle", d_nozzle), ("t_nozzle", t_nozzle), ("S", S)):
        err = _guard_positive(name, val)
        if err:
            return _err(err)
    err = _guard_nonneg("c", c)
    if err:
        return _err(err)

    E_f = float(E)
    if not (0 < E_f <= 1.0):
        return _err(f"E (joint efficiency) must be in (0, 1], got {E_f}")

    F_f = float(F)
    if not (0.5 <= F_f <= 1.0):
        return _err(f"F (correction factor) must be in [0.5, 1.0], got {F_f}")

    P_v = float(P)
    D_v = float(D_shell)
    ts_v = float(t_shell)
    d_v = float(d_nozzle)
    tn_v = float(t_nozzle)
    S_v = float(S)
    c_v = float(c)
    R_v = D_v / 2.0

    # Required shell thickness per UG-27(c)(1), no corrosion allowance
    denom_circ = S_v * E_f - 0.6 * P_v
    if denom_circ <= 0:
        return _err(
            f"S·E - 0.6·P = {denom_circ:.2f} Pa ≤ 0; "
            "pressure exceeds material/efficiency limit."
        )
    t_req = P_v * R_v / denom_circ  # UG-27 required thickness (no CA)

    # Net (corroded) thicknesses
    ts_net = ts_v - c_v
    tn_net = tn_v - c_v

    if ts_net <= 0:
        return _err(
            f"Net shell thickness ts_net = {ts_net*1e3:.2f} mm ≤ 0 after corrosion allowance."
        )
    if tn_net <= 0:
        return _err(
            f"Net nozzle thickness tn_net = {tn_net*1e3:.2f} mm ≤ 0 after corrosion allowance."
        )

    # Under-thickness shell warning
    if ts_net < t_req:
        msg = (
            f"Net shell thickness {ts_net*1e3:.2f} mm < required {t_req*1e3:.2f} mm; "
            "shell is under-thickness; area-replacement result is informational only."
        )
        warn_list.append(msg)
        _warnings_mod.warn(msg, stacklevel=2)

    # Required area (UG-37(c)(1)):
    A_req = d_v * t_req * F_f

    # Area A1 — shell excess above t_req (within the reinforcement zone = d on each side)
    #   A1 = (2d) × (ts_net - F·t_req)  but only if ts_net > F·t_req
    A1 = d_v * (ts_net - F_f * t_req)
    if A1 < 0.0:
        A1 = 0.0

    # Area A2 — nozzle wall within reinforcement zone height 2.5·ts_net above shell O.D.
    #   Height available = min(2.5·ts_net, 2.5·tn_net)
    h2 = min(2.5 * ts_net, 2.5 * tn_net)
    A2 = 2.0 * tn_net * h2  # two sides of nozzle wall

    A_total = A1 + A2
    ok_flag = A_total >= A_req
    shortfall = A_req - A_total

    if not ok_flag:
        msg = (
            f"Nozzle reinforcement INSUFFICIENT: "
            f"A_total = {A_total*1e6:.2f} mm² < A_required = {A_req*1e6:.2f} mm². "
            f"Shortfall = {shortfall*1e6:.2f} mm². Add a reinforcing pad."
        )
        warn_list.append(msg)
        _warnings_mod.warn(msg, stacklevel=2)

    return {
        "ok": True,
        "A_required_m2": A_req,
        "A1_shell_m2": A1,
        "A2_nozzle_m2": A2,
        "A_total_m2": A_total,
        "reinforcement_ok": ok_flag,
        "shortfall_m2": shortfall,
        "t_req_shell_m": t_req,
        "P_Pa": P_v,
        "D_shell_m": D_v,
        "t_shell_m": ts_v,
        "d_nozzle_m": d_v,
        "t_nozzle_m": tn_v,
        "S_Pa": S_v,
        "E_factor": E_f,
        "c_m": c_v,
        "F_factor": F_f,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 8. hydrostatic_test_pressure — UG-99(b)
#
#     P_test = 1.3 × MAWP × (S_test / S_design)
#
# The stress-ratio correction S_test/S_design accounts for the fact that
# allowable stresses change at test temperature (usually ambient).
# If both S_test and S_design are the same (same material, same temp) the
# ratio = 1 and P_test = 1.3 × MAWP.
# ---------------------------------------------------------------------------

def hydrostatic_test_pressure(
    MAWP: float,
    S_test: float | None = None,
    S_design: float | None = None,
) -> dict:
    """
    Hydrostatic test pressure per ASME BPVC VIII-1 UG-99(b).

    P_test = 1.3 × MAWP × (S_test / S_design)

    If S_test and S_design are not provided the ratio defaults to 1.0.

    Parameters
    ----------
    MAWP : float
        Maximum Allowable Working Pressure (Pa). Must be > 0.
    S_test : float | None
        Allowable stress at test temperature (Pa). Must be > 0 if provided.
    S_design : float | None
        Allowable stress at design temperature (Pa). Must be > 0 if provided.

    Returns
    -------
    dict
        ok                 : True
        P_test_Pa          : hydrostatic test pressure (Pa)
        P_test_kPa         : same in kPa
        P_test_bar         : same in bar
        P_test_psi         : same in psi
        MAWP_Pa            : MAWP used (Pa)
        stress_ratio       : S_test / S_design
        warnings           : list of strings
    """
    warn_list: list[str] = []

    err = _guard_positive("MAWP", MAWP)
    if err:
        return _err(err)

    ratio = 1.0

    if S_test is not None and S_design is not None:
        err = _guard_positive("S_test", S_test)
        if err:
            return _err(err)
        err = _guard_positive("S_design", S_design)
        if err:
            return _err(err)
        ratio = float(S_test) / float(S_design)
        if ratio < 1.0:
            msg = (
                f"S_test/S_design = {ratio:.3f} < 1.0; test temperature may be above "
                "design temperature — consult UG-99 Table UG-99 and UG-100."
            )
            warn_list.append(msg)
            _warnings_mod.warn(msg, stacklevel=2)
    elif (S_test is None) != (S_design is None):
        msg = (
            "Only one of S_test / S_design provided; both are needed to apply "
            "the stress-ratio correction. Using ratio = 1.0."
        )
        warn_list.append(msg)
        _warnings_mod.warn(msg, stacklevel=2)

    P_test = 1.3 * float(MAWP) * ratio

    return {
        "ok": True,
        "P_test_Pa": P_test,
        "P_test_kPa": P_test * 1e-3,
        "P_test_bar": P_test * 1e-5,
        "P_test_psi": P_test / 6894.757,
        "MAWP_Pa": float(MAWP),
        "stress_ratio": ratio,
        "warnings": warn_list,
    }
