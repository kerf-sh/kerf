"""
kerf_cad_core.gearstrength.rating — AGMA 2001-D04 gear stress & rating.

Implements eight public functions for the strength/rating layer of spur and
helical gears, per AGMA 2001-D04 and Shigley's §§ 14-1 to 14-5.

Public API
----------
agma_dynamic_factor(Vt_fps, Qv)
    Dynamic factor Kv from AGMA quality number Qv and pitch-line velocity.

agma_geometry_factor_J(N, psi_deg, *, pressure_angle_deg)
    Bending geometry factor J (Lewis form factor Y with helical correction).

agma_geometry_factor_I(N_p, N_g, psi_deg, *, pressure_angle_deg, external)
    Pitting (contact) geometry factor I.

agma_bending_stress(Wt, Ko, Kv, Ks, Km, KB, b, m_or_Pd, J, *, metric)
    AGMA bending stress σ_t.
    Metric:   σ_t = Wt·Ko·Kv·Ks·Km·KB / (b·m·J)   [MPa]
    English:  σ_t = Wt·Ko·Kv·Ks·Pd·Km·KB / (b·J)   [psi]

agma_contact_stress(Wt, Ko, Kv, Ks, Km, Cp, d_p, b, I, *, metric)
    AGMA contact (pitting) stress σ_c.
    σ_c = Cp · √(Wt·Ko·Kv·Ks·Km / (d·b·I))

agma_safety_factors(sigma_b, sigma_c, S_t, S_c, *, YN, ZN, K_T, K_R)
    Safety factors SF (bending) and SH (contact) vs allowable.

agma_power_rating(S_t, S_c, Cp, b, m_or_Pd, d_p, N_p, N_g, psi_deg,
                  n_rpm, *, metric, Ko, Ks, Km, KB, Qv, K_T, K_R,
                  pressure_angle_deg)
    Maximum safe transmitted power and torque from allowable stresses.

agma_service_life(N_cycles, *, hardness_HB, gear_type)
    Stress-cycle factors YN (bending) and ZN (contact) for a given
    number of stress cycles, per AGMA 2001-D04 Figs. 14-14 & 14-15.

All functions:
  - Return {"ok": True, ...} on success, {"ok": False, "reason": ...} on error.
  - Append human-readable warnings (list[str]) to the result dict when
    conditions flag under-rated or over-stressed situations.
  - NEVER raise.

Units
-----
Unless explicitly noted via the ``metric`` flag:
  English (default):
    Wt       — lbf (tangential load)
    b        — inches (face width)
    Pd       — teeth/inch (diametral pitch)
    d_p      — inches (pitch diameter of pinion)
    sigma    — psi
    power    — hp
    torque   — lbf·in

  Metric (metric=True):
    Wt       — N
    b        — mm
    m        — mm (module)
    d_p      — mm
    sigma    — MPa
    power    — kW
    torque   — N·mm

References
----------
AGMA 2001-D04, §§ 3, 5, 6, 14
Shigley's Mechanical Engineering Design, 10th ed., §§ 14-1..14-5
Norton, R.L. "Machine Design", 5th ed., Ch. 11

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings as _warnings_mod
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


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


def _guard_range(name: str, value: Any, lo: float, hi: float) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite"
    if v < lo or v > hi:
        return f"{name} must be in [{lo}, {hi}], got {v}"
    return None


# ---------------------------------------------------------------------------
# 1. Dynamic factor Kv  (AGMA 2001-D04 §6.2, Shigley §14-2)
# ---------------------------------------------------------------------------

# AGMA quality-number range: 3 (lowest) to 12 (highest precision)
_QV_MIN = 3
_QV_MAX = 12

# Transmission accuracy number A (AGMA 2001-D04, Eq. 14-27)
# A = 50 + 56(1 − B);  B = 0.25(12 − Qv)^(2/3)
# Kv = ((A + √(200 Vt)) / A)^B   where Vt is in ft/min


def agma_dynamic_factor(Vt_fps: float, Qv: int | float) -> dict:
    """
    AGMA dynamic factor Kv from quality number and pitch-line velocity.

    Parameters
    ----------
    Vt_fps : float
        Pitch-line velocity in ft/min (English).  Must be > 0.
        (To convert: Vt_fps = π · d_in · n_rpm / 12, where d_in is in inches.)
    Qv : int or float
        AGMA transmission accuracy / quality number.  Range: 3–12.
        Higher Qv → tighter tolerances → lower (better) Kv.
        Typical: hobbed/shaped = 5-6; shaved = 7-8; ground = 11-12.

    Returns
    -------
    dict
        ok   : True
        Kv   : dynamic factor (dimensionless; Kv >= 1)
        A    : transmission accuracy constant
        B    : exponent
        Vt_fpm : pitch-line velocity (ft/min)
        Qv   : quality number used

    Warnings
    --------
    If Vt_fps > Vt_max (the maximum velocity valid for the quality number),
    a warning is issued in the "warnings" key.

    References
    ----------
    AGMA 2001-D04, §6.2 (Eqs. 14-27, 14-28)
    Shigley 10th ed., §14-2, Eqs. (14-27), (14-28)
    """
    err = _guard_positive("Vt_fps", Vt_fps)
    if err:
        return _err(err)
    err = _guard_range("Qv", Qv, _QV_MIN, _QV_MAX)
    if err:
        return _err(err)

    Vt = float(Vt_fps)   # ft/min
    qv = float(Qv)

    # AGMA 2001-D04 Eqs. (14-27) and (14-28)
    B = 0.25 * (12.0 - qv) ** (2.0 / 3.0)
    A = 50.0 + 56.0 * (1.0 - B)

    # Maximum valid velocity for this quality number (Shigley Eq. 14-29):
    # Vt_max = [A + (Qv - 3)]^2  (ft/min)
    Vt_max = (A + (qv - 3.0)) ** 2.0

    warns: list[str] = []
    if Vt > Vt_max:
        warns.append(
            f"Vt_fps={Vt:.1f} ft/min exceeds the AGMA validity limit "
            f"Vt_max={Vt_max:.1f} ft/min for Qv={Qv}. "
            "Kv formula is not reliable at this speed; upgrade gear quality."
        )

    # Kv = ((A + sqrt(Vt)) / A)^B   (AGMA/Shigley Eq. 14-28, Vt in ft/min)
    # (The factor 200 appears in the metric form where Vt is in m/s;
    #  here the input is always in ft/min.)
    Kv = ((A + math.sqrt(Vt)) / A) ** B

    result: dict = {
        "ok": True,
        "Kv": Kv,
        "A": A,
        "B": B,
        "Vt_fpm": Vt,
        "Vt_max_fpm": Vt_max,
        "Qv": Qv,
    }
    if warns:
        result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 2. Geometry factor J  (bending)  Shigley §14-3, Table 14-2 / Fig. 14-6
# ---------------------------------------------------------------------------

# Approximate J factors for 20° full-depth spur gears vs tooth count.
# Source: Shigley Table 14-2 (20° pressure angle, standard full-depth).
# We use linear interpolation between tabulated points.
# (N_teeth, J_spur)
_J_TABLE_20 = [
    (13, 0.245), (14, 0.261), (15, 0.270), (16, 0.277), (17, 0.283),
    (18, 0.289), (19, 0.295), (20, 0.300), (22, 0.311), (24, 0.324),
    (26, 0.331), (28, 0.337), (30, 0.346), (34, 0.358), (38, 0.370),
    (43, 0.380), (50, 0.390), (60, 0.408), (75, 0.422), (100, 0.440),
    (150, 0.463), (300, 0.490), (400, 0.500),
]

_J_TABLE_25 = [
    (13, 0.290), (14, 0.310), (15, 0.325), (16, 0.335), (17, 0.340),
    (18, 0.348), (19, 0.354), (20, 0.360), (22, 0.371), (24, 0.381),
    (26, 0.390), (28, 0.399), (30, 0.408), (34, 0.421), (38, 0.434),
    (43, 0.446), (50, 0.462), (60, 0.480), (75, 0.500), (100, 0.520),
    (150, 0.550), (300, 0.590), (400, 0.600),
]


def _interp_J(N: float, table: list[tuple[float, float]]) -> float:
    """Linear interpolation into the J table for tooth count N."""
    if N <= table[0][0]:
        return table[0][1]
    if N >= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        n0, j0 = table[i]
        n1, j1 = table[i + 1]
        if n0 <= N <= n1:
            t = (N - n0) / (n1 - n0)
            return j0 + t * (j1 - j0)
    return table[-1][1]  # fallback


def agma_geometry_factor_J(
    N: int | float,
    psi_deg: float,
    *,
    pressure_angle_deg: float = 20.0,
) -> dict:
    """
    Bending geometry factor J for spur (ψ=0) and helical gears.

    The spur value J_spur is read from the approximate AGMA/Shigley table
    (Shigley Table 14-2) for 20° or 25° normal pressure angles.  For
    helical gears the correction is (Shigley Eq. 14-7):

        J_helical = J_spur / (1 − (sin²ψ / (2 cos ψ)) × (ln(1 + 1/N)))

    This is a simplified form; for precise work consult AGMA 908-B89.

    Parameters
    ----------
    N : int or float
        Number of teeth on the gear.  Must be >= 12.
    psi_deg : float
        Helix angle (degrees).  0 = spur; typical helical: 15–30°.
    pressure_angle_deg : float
        Normal pressure angle (degrees). Supported: 20 (default) or 25.

    Returns
    -------
    dict
        ok              : True
        J               : geometry factor (dimensionless)
        J_spur          : spur baseline value (before helix correction)
        helix_correction: correction factor applied (1.0 for spur)
        N               : tooth count
        psi_deg         : helix angle
        pressure_angle_deg : pressure angle
    """
    err = _guard_range("N", N, 12, 10000)
    if err:
        return _err(err)
    err = _guard_range("psi_deg", psi_deg, 0, 45)
    if err:
        return _err(err)
    err = _guard_range("pressure_angle_deg", pressure_angle_deg, 14, 30)
    if err:
        return _err(err)

    N_val = float(N)
    psi = math.radians(float(psi_deg))
    pa = float(pressure_angle_deg)

    # Select table nearest to requested pressure angle
    if abs(pa - 25.0) < abs(pa - 20.0):
        table = _J_TABLE_25
        pa_used = 25.0
    else:
        table = _J_TABLE_20
        pa_used = 20.0

    J_spur = _interp_J(N_val, table)

    # Helical correction (simplified AGMA/Shigley)
    if psi_deg < 0.5:
        corr = 1.0
        J_val = J_spur
    else:
        sp = math.sin(psi)
        cp = math.cos(psi)
        if N_val > 0 and cp > 0:
            corr = 1.0 - (sp ** 2 / (2.0 * cp)) * math.log(1.0 + 1.0 / N_val)
            # corr should be < 1 (helix reduces effective J due to load sharing)
            corr = max(corr, 0.5)  # clamp to physical range
        else:
            corr = 1.0
        J_val = J_spur * corr

    warns: list[str] = []
    if pa_used != pa:
        warns.append(
            f"pressure_angle_deg={pa}° is not tabulated; using nearest: {pa_used}°."
        )

    result: dict = {
        "ok": True,
        "J": J_val,
        "J_spur": J_spur,
        "helix_correction": corr,
        "N": N_val,
        "psi_deg": psi_deg,
        "pressure_angle_deg": pa_used,
    }
    if warns:
        result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 3. Geometry factor I  (contact / pitting)  Shigley §14-3
# ---------------------------------------------------------------------------

def agma_geometry_factor_I(
    N_p: int | float,
    N_g: int | float,
    psi_deg: float,
    *,
    pressure_angle_deg: float = 20.0,
    external: bool = True,
) -> dict:
    """
    Pitting (contact) geometry factor I.

    For a spur or helical gear pair (Shigley Eq. 14-23):

        I = (cos φ_t · sin φ_t) / (2 m_N) × m_G / (m_G + 1)  [external]
        I = (cos φ_t · sin φ_t) / (2 m_N) × m_G / (m_G − 1)  [internal]

    where:
        φ_t  = transverse pressure angle = arctan(tan φ_n / cos ψ)
        m_N  = load-sharing ratio = p_N / (0.95 Z)
               for spur: m_N = 1.0 (conservative)
               for helical: m_N = F·cos ψ / Z  (approximate; here m_N=1.0 used)
        m_G  = gear ratio = N_g / N_p  (must be >= 1)

    For a first-pass estimate m_N = 1.0 is used (conservative; underestimates I).

    Parameters
    ----------
    N_p : int or float
        Number of teeth on pinion.  Must be >= 12.
    N_g : int or float
        Number of teeth on gear.  Must be >= N_p.
    psi_deg : float
        Helix angle (degrees).  0 = spur.
    pressure_angle_deg : float
        Normal pressure angle φ_n (degrees).  Default 20°.
    external : bool
        True (default) = external mesh; False = internal (ring) gear.

    Returns
    -------
    dict
        ok                 : True
        I                  : geometry factor I (dimensionless)
        phi_t_deg          : transverse pressure angle (degrees)
        m_G                : gear ratio N_g / N_p
        m_N                : load-sharing ratio used (1.0 for spur)
        N_p, N_g, psi_deg, pressure_angle_deg, external
    """
    err = _guard_range("N_p", N_p, 12, 10000)
    if err:
        return _err(err)
    err = _guard_range("N_g", N_g, 12, 100000)
    if err:
        return _err(err)
    err = _guard_range("psi_deg", psi_deg, 0, 45)
    if err:
        return _err(err)
    err = _guard_range("pressure_angle_deg", pressure_angle_deg, 14, 30)
    if err:
        return _err(err)

    Np = float(N_p)
    Ng = float(N_g)
    psi = math.radians(float(psi_deg))
    phi_n = math.radians(float(pressure_angle_deg))

    if Ng < Np:
        return _err(f"N_g ({Ng}) must be >= N_p ({Np}) (put the pinion as N_p).")

    m_G = Ng / Np  # gear ratio

    # Transverse pressure angle (for helical gears)
    # tan φ_t = tan φ_n / cos ψ
    phi_t = math.atan(math.tan(phi_n) / math.cos(psi)) if psi > 0 else phi_n

    # Load-sharing ratio: m_N = 1.0 (conservative / spur assumption)
    m_N = 1.0

    # Geometry factor I
    sin_t = math.sin(phi_t)
    cos_t = math.cos(phi_t)

    if external:
        I_val = (cos_t * sin_t) / (2.0 * m_N) * (m_G / (m_G + 1.0))
    else:
        if m_G <= 1.0:
            return _err(
                "For internal (ring) gear m_G must be > 1 "
                "(internal gear formula has m_G − 1 in denominator)."
            )
        I_val = (cos_t * sin_t) / (2.0 * m_N) * (m_G / (m_G - 1.0))

    return {
        "ok": True,
        "I": I_val,
        "phi_t_deg": math.degrees(phi_t),
        "m_G": m_G,
        "m_N": m_N,
        "N_p": Np,
        "N_g": Ng,
        "psi_deg": psi_deg,
        "pressure_angle_deg": pressure_angle_deg,
        "external": external,
    }


# ---------------------------------------------------------------------------
# 4. AGMA bending stress  (Shigley §14-4, Eq. 14-15 / 14-16)
# ---------------------------------------------------------------------------

def agma_bending_stress(
    Wt: float,
    Ko: float,
    Kv: float,
    Ks: float,
    Km: float,
    KB: float,
    b: float,
    m_or_Pd: float,
    J: float,
    *,
    metric: bool = False,
) -> dict:
    """
    AGMA bending stress σ_t.

    Metric  (metric=True):
        σ_t = Wt · Ko · Kv · Ks · (1/b) · (1/m) · (Km · KB / J)   [MPa]

    English (metric=False):
        σ_t = Wt · Ko · Kv · Ks · Pd / b · Km · KB / J              [psi]

    Both reduce to the canonical form:
        σ_t = Wt · Ko · Kv · Ks · Km · KB / (b · m_eff · J)
    where m_eff = module m [mm] for metric, or 1/Pd [in] for English.

    Parameters
    ----------
    Wt : float
        Transmitted (tangential) load.  lbf (English) or N (metric).
    Ko : float
        Overload factor (>= 1).  Accounts for external dynamic loads.
    Kv : float
        Dynamic factor (>= 1).  From agma_dynamic_factor().
    Ks : float
        Size factor (>= 1).  Typically 1.0 for Pd >= 5, up to 1.5+.
        AGMA 2001-D04 §6.3: Ks = 1.192 (F √Y / P)^0.0535 approx.
    Km : float
        Load-distribution factor (>= 1).  Accounts for non-uniform
        load distribution across the face width.
    KB : float
        Rim thickness factor (>= 1).  1.0 for solid gear blanks.
    b : float
        Face width.  inches (English) or mm (metric).  Must be > 0.
    m_or_Pd : float
        Module m [mm] (metric) or diametral pitch Pd [teeth/in] (English).
        Must be > 0.
    J : float
        Bending geometry factor J from agma_geometry_factor_J().  > 0.
    metric : bool
        If True, treat inputs as metric (N, mm, MPa).  Default False (English).

    Returns
    -------
    dict
        ok           : True
        sigma_t      : AGMA bending stress (psi or MPa)
        unit         : "psi" or "MPa"
        Wt, Ko, Kv, Ks, Km, KB, b, m_or_Pd, J, metric : echoed inputs
        warnings     : list of human-readable stress warnings (may be absent)
    """
    for name, val in (
        ("Wt", Wt), ("Ko", Ko), ("Kv", Kv), ("Ks", Ks),
        ("Km", Km), ("KB", KB), ("b", b), ("m_or_Pd", m_or_Pd), ("J", J),
    ):
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    Wt_f = float(Wt)
    Ko_f = float(Ko)
    Kv_f = float(Kv)
    Ks_f = float(Ks)
    Km_f = float(Km)
    KB_f = float(KB)
    b_f  = float(b)
    mPd  = float(m_or_Pd)
    J_f  = float(J)

    # Effective module for the formula: module m in mm (metric) or 1/Pd in inches
    if metric:
        # σ_t [MPa] = Wt[N] · Ko · Kv · Ks · Km · KB / (b[mm] · m[mm] · J)
        # (Units: N/(mm·mm) = N/mm² = MPa  ✓)
        denom = b_f * mPd * J_f
        sigma_t = (Wt_f * Ko_f * Kv_f * Ks_f * Km_f * KB_f) / denom
        unit = "MPa"
    else:
        # σ_t [psi] = Wt[lbf] · Ko · Kv · Ks · Pd[1/in] · Km · KB / (b[in] · J)
        denom = b_f * J_f
        sigma_t = (Wt_f * Ko_f * Kv_f * Ks_f * mPd * Km_f * KB_f) / denom
        unit = "psi"

    warns: list[str] = []
    # Sanity: typical bending stress for steel gears rarely exceeds 100 ksi / 700 MPa
    high_thresh = 700.0 if metric else 100_000.0
    if sigma_t > high_thresh:
        warns.append(
            f"Bending stress {sigma_t:.1f} {unit} exceeds typical structural "
            f"steel limit ({high_thresh} {unit}). Verify inputs or upgrade gear."
        )

    result: dict = {
        "ok": True,
        "sigma_t": sigma_t,
        "unit": unit,
        "Wt": Wt_f,
        "Ko": Ko_f,
        "Kv": Kv_f,
        "Ks": Ks_f,
        "Km": Km_f,
        "KB": KB_f,
        "b": b_f,
        "m_or_Pd": mPd,
        "J": J_f,
        "metric": metric,
    }
    if warns:
        result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 5. AGMA contact (pitting) stress  (Shigley §14-4, Eq. 14-16)
# ---------------------------------------------------------------------------

def agma_contact_stress(
    Wt: float,
    Ko: float,
    Kv: float,
    Ks: float,
    Km: float,
    Cp: float,
    d_p: float,
    b: float,
    I: float,
    *,
    metric: bool = False,
) -> dict:
    """
    AGMA contact (pitting) stress σ_c.

    σ_c = Cp · √(Wt · Ko · Kv · Ks · Km / (d_p · b · I))

    Parameters
    ----------
    Wt : float
        Tangential transmitted load.  lbf (English) or N (metric).
    Ko : float
        Overload factor (>= 1).
    Kv : float
        Dynamic factor (>= 1).
    Ks : float
        Size factor (>= 1).
    Km : float
        Load-distribution factor (>= 1).
    Cp : float
        Elastic coefficient √(psi) (English) or √(MPa) (metric).
        Steel/steel: 2300 √psi (English) or 191 √MPa (metric).
        See AGMA 2001-D04 Table 9 / Shigley Table 14-8.
    d_p : float
        Pitch diameter of the pinion.  inches (English) or mm (metric).
    b : float
        Face width.  inches (English) or mm (metric).
    I : float
        Pitting geometry factor from agma_geometry_factor_I().  > 0.
    metric : bool
        True = metric units (N, mm, MPa).  Default False (English, lbf, in, psi).

    Returns
    -------
    dict
        ok       : True
        sigma_c  : AGMA contact stress (√psi or √MPa — i.e. actual psi or MPa)
        unit     : "psi" or "MPa"
        radicand : value under the square-root sign (for diagnostics)
        warnings : list of stress warnings (may be absent)
    """
    for name, val in (
        ("Wt", Wt), ("Ko", Ko), ("Kv", Kv), ("Ks", Ks),
        ("Km", Km), ("Cp", Cp), ("d_p", d_p), ("b", b), ("I", I),
    ):
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    Wt_f = float(Wt)
    Ko_f = float(Ko)
    Kv_f = float(Kv)
    Ks_f = float(Ks)
    Km_f = float(Km)
    Cp_f = float(Cp)
    d_f  = float(d_p)
    b_f  = float(b)
    I_f  = float(I)

    radicand = (Wt_f * Ko_f * Kv_f * Ks_f * Km_f) / (d_f * b_f * I_f)
    if radicand < 0:
        return _err("Radicand is negative — check inputs.")
    sigma_c = Cp_f * math.sqrt(radicand)

    unit = "MPa" if metric else "psi"

    warns: list[str] = []
    # Typical upper limits: ~200 ksi English or ~1400 MPa metric for hardened steel
    high_thresh = 1400.0 if metric else 200_000.0
    if sigma_c > high_thresh:
        warns.append(
            f"Contact stress {sigma_c:.1f} {unit} exceeds typical hardened-steel "
            f"limit ({high_thresh} {unit}). Verify inputs or increase face width."
        )

    result: dict = {
        "ok": True,
        "sigma_c": sigma_c,
        "unit": unit,
        "radicand": radicand,
        "Wt": Wt_f,
        "Ko": Ko_f,
        "Kv": Kv_f,
        "Ks": Ks_f,
        "Km": Km_f,
        "Cp": Cp_f,
        "d_p": d_f,
        "b": b_f,
        "I": I_f,
        "metric": metric,
    }
    if warns:
        result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 6. Safety factors  (AGMA 2001-D04 §4.1, Shigley §14-5)
# ---------------------------------------------------------------------------

def agma_safety_factors(
    sigma_b: float,
    sigma_c: float,
    S_t: float,
    S_c: float,
    *,
    YN: float = 1.0,
    ZN: float = 1.0,
    K_T: float = 1.0,
    K_R: float = 1.0,
) -> dict:
    """
    AGMA safety factors for bending (SF) and contact (SH).

    Allowable bending stress:
        sigma_t_all = S_t · YN / (K_T · K_R)

    Allowable contact stress:
        sigma_c_all = S_c · ZN / (K_T · K_R)

    Safety factors:
        SF = sigma_t_all / sigma_b   (bending; SF >= 1 → safe)
        SH = sigma_c_all / sigma_c   (contact; SH >= 1.2 recommended per AGMA)

    Parameters
    ----------
    sigma_b : float
        Actual AGMA bending stress σ_t (psi or MPa).
    sigma_c : float
        Actual AGMA contact stress σ_c (psi or MPa).
    S_t : float
        Allowable bending stress number (material property, psi or MPa).
        Typical carburised-hardened steel: 65 kpsi / 450 MPa.
    S_c : float
        Allowable contact stress number (material property, psi or MPa).
        Typical carburised-hardened steel: 225 kpsi / 1550 MPa.
    YN : float
        Bending stress-cycle factor (default 1.0 — life >= 3×10^6 cycles).
    ZN : float
        Contact stress-cycle factor (default 1.0 — life >= 10^7 cycles).
    K_T : float
        Temperature factor (default 1.0 — < 120°C / 250°F).
    K_R : float
        Reliability factor (default 1.0 — 90% reliability).
        1.0 → 90%, 1.25 → 99%, 1.5 → 99.99%.

    Returns
    -------
    dict
        ok            : True
        SF            : bending safety factor
        SH            : contact safety factor
        sigma_t_all   : allowable bending stress
        sigma_c_all   : allowable contact stress
        bending_ok    : True if SF >= 1.0
        contact_ok    : True if SH >= 1.0
        warnings      : list of human-readable warnings (may be absent)
    """
    for name, val in (
        ("sigma_b", sigma_b), ("sigma_c", sigma_c),
        ("S_t", S_t), ("S_c", S_c),
        ("YN", YN), ("ZN", ZN), ("K_T", K_T), ("K_R", K_R),
    ):
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    sb = float(sigma_b)
    sc = float(sigma_c)
    St = float(S_t)
    Sc = float(S_c)
    yn = float(YN)
    zn = float(ZN)
    kT = float(K_T)
    kR = float(K_R)

    sigma_t_all = St * yn / (kT * kR)
    sigma_c_all = Sc * zn / (kT * kR)

    SF = sigma_t_all / sb
    SH = sigma_c_all / sc

    bending_ok = SF >= 1.0
    contact_ok = SH >= 1.0

    warns: list[str] = []
    if not bending_ok:
        warns.append(
            f"BENDING OVERSTRESS: SF={SF:.3f} < 1.0 "
            f"(sigma_b={sb:.1f} > sigma_t_all={sigma_t_all:.1f})."
        )
    elif SF < 1.2:
        warns.append(
            f"Low bending safety factor SF={SF:.3f}; AGMA recommends >= 1.2."
        )
    if not contact_ok:
        warns.append(
            f"CONTACT OVERSTRESS: SH={SH:.3f} < 1.0 "
            f"(sigma_c={sc:.1f} > sigma_c_all={sigma_c_all:.1f})."
        )
    elif SH < 1.2:
        warns.append(
            f"Low contact safety factor SH={SH:.3f}; AGMA recommends >= 1.2."
        )

    result: dict = {
        "ok": True,
        "SF": SF,
        "SH": SH,
        "sigma_t_all": sigma_t_all,
        "sigma_c_all": sigma_c_all,
        "bending_ok": bending_ok,
        "contact_ok": contact_ok,
        "YN": yn,
        "ZN": zn,
        "K_T": kT,
        "K_R": kR,
    }
    if warns:
        result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 7. Power / torque rating  (Shigley §14-5)
# ---------------------------------------------------------------------------

def agma_power_rating(
    S_t: float,
    S_c: float,
    Cp: float,
    b: float,
    m_or_Pd: float,
    d_p: float,
    N_p: int | float,
    N_g: int | float,
    psi_deg: float,
    n_rpm: float,
    *,
    metric: bool = False,
    Ko: float = 1.0,
    Ks: float = 1.0,
    Km: float = 1.3,
    KB: float = 1.0,
    Qv: float = 6.0,
    K_T: float = 1.0,
    K_R: float = 1.0,
    pressure_angle_deg: float = 20.0,
    YN: float = 1.0,
    ZN: float = 1.0,
) -> dict:
    """
    Maximum safe transmitted power and torque rating for a gear pair.

    Computes the maximum Wt satisfying both the bending and contact AGMA
    allowable stresses simultaneously, then converts to power and torque.

    Parameters
    ----------
    S_t : float
        Allowable bending stress number (psi English / MPa metric).
    S_c : float
        Allowable contact stress number (psi English / MPa metric).
    Cp : float
        Elastic coefficient (√psi English / √MPa metric).
    b : float
        Face width (in English / mm metric).
    m_or_Pd : float
        Module m [mm] (metric) or diametral pitch Pd [1/in] (English).
    d_p : float
        Pinion pitch diameter (in English / mm metric).
    N_p, N_g : int or float
        Pinion and gear tooth counts.  N_g >= N_p.
    psi_deg : float
        Helix angle (degrees; 0 = spur).
    n_rpm : float
        Pinion rotational speed (rpm).
    metric : bool
        Unit system flag.
    Ko, Ks, Km, KB, Qv, K_T, K_R, pressure_angle_deg, YN, ZN : float
        Service/design factors (see agma_bending_stress and agma_safety_factors
        for descriptions).

    Returns
    -------
    dict
        ok             : True
        Wt_bending_lim : max Wt from bending allowable (lbf or N)
        Wt_contact_lim : max Wt from contact allowable (lbf or N)
        Wt_rated       : governing (minimum) Wt limit (lbf or N)
        governing      : "bending" or "contact"
        power_rated    : rated power (hp or kW)
        torque_rated   : rated torque (lbf·in or N·mm)
        unit_power     : "hp" or "kW"
        unit_torque    : "lbf·in" or "N·mm"
        warnings       : list of warnings (may be absent)
    """
    for name, val in (
        ("S_t", S_t), ("S_c", S_c), ("Cp", Cp), ("b", b),
        ("m_or_Pd", m_or_Pd), ("d_p", d_p), ("n_rpm", n_rpm),
        ("Ko", Ko), ("Ks", Ks), ("Km", Km), ("KB", KB),
        ("K_T", K_T), ("K_R", K_R), ("YN", YN), ("ZN", ZN),
    ):
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    # --- Dynamic factor Kv from pitch-line velocity ---
    if metric:
        # Vt [m/s] = π * d_p[mm] * n_rpm / (60000)
        # Convert to ft/min: 1 m/s = 196.85 ft/min
        Vt_ms = math.pi * float(d_p) * float(n_rpm) / 60_000.0
        Vt_fpm = Vt_ms * 196.85
    else:
        # Vt [ft/min] = π * d_p[in] * n_rpm / 12
        Vt_fpm = math.pi * float(d_p) * float(n_rpm) / 12.0

    kv_res = agma_dynamic_factor(Vt_fpm, Qv)
    if not kv_res["ok"]:
        return _err(f"Dynamic factor error: {kv_res['reason']}")
    Kv = kv_res["Kv"]

    # --- Geometry factors J and I ---
    j_res = agma_geometry_factor_J(N_p, psi_deg, pressure_angle_deg=pressure_angle_deg)
    if not j_res["ok"]:
        return _err(f"Geometry factor J error: {j_res['reason']}")
    J = j_res["J"]

    i_res = agma_geometry_factor_I(N_p, N_g, psi_deg, pressure_angle_deg=pressure_angle_deg)
    if not i_res["ok"]:
        return _err(f"Geometry factor I error: {i_res['reason']}")
    I_val = i_res["I"]

    Ko_f = float(Ko)
    Ks_f = float(Ks)
    Km_f = float(Km)
    KB_f = float(KB)
    b_f  = float(b)
    mPd  = float(m_or_Pd)
    dp_f = float(d_p)
    kT   = float(K_T)
    kR   = float(K_R)
    St   = float(S_t)
    Sc   = float(S_c)
    Cp_f = float(Cp)

    # Allowable stresses
    sigma_t_all = St * float(YN) / (kT * kR)
    sigma_c_all = Sc * float(ZN) / (kT * kR)

    # --- Solve for Wt from bending allowable ---
    # sigma_t = Wt · Ko · Kv · Ks · mPd_eff · Km · KB / (b · J)  (English)
    # sigma_t = Wt · Ko · Kv · Ks · Km · KB / (b · m · J)        (metric)
    if metric:
        bending_denom = Ko_f * Kv * Ks_f * Km_f * KB_f / (b_f * mPd * J)
    else:
        bending_denom = Ko_f * Kv * Ks_f * mPd * Km_f * KB_f / (b_f * J)
    Wt_bending = sigma_t_all / bending_denom if bending_denom > 0 else 0.0

    # --- Solve for Wt from contact allowable ---
    # sigma_c = Cp * sqrt(Wt · Ko · Kv · Ks · Km / (d · b · I))
    # → Wt = (sigma_c_all / Cp)² * d * b * I / (Ko · Kv · Ks · Km)
    contact_num = (sigma_c_all / Cp_f) ** 2 * dp_f * b_f * I_val
    contact_denom = Ko_f * Kv * Ks_f * Km_f
    Wt_contact = contact_num / contact_denom if contact_denom > 0 else 0.0

    Wt_rated = min(Wt_bending, Wt_contact)
    governing = "bending" if Wt_bending <= Wt_contact else "contact"

    # --- Convert to power and torque ---
    if metric:
        # Torque [N·mm] = Wt[N] * d_p[mm] / 2
        torque = Wt_rated * dp_f / 2.0
        # Power [kW] = Torque[N·mm] * n_rpm / (9.55e6)
        # Derivation: P[W] = T[N·m] * ω[rad/s] = T[N·mm]*1e-3 * 2π*n/60
        #             P[kW] = T[N·mm] * n / (60000/(2π*1000)) = T * n / 9549296
        power = torque * float(n_rpm) / 9_549_296.0
        unit_power = "kW"
        unit_torque = "N·mm"
    else:
        # Torque [lbf·in] = Wt[lbf] * d_p[in] / 2
        torque = Wt_rated * dp_f / 2.0
        # Power [hp] = Wt[lbf] * Vt[ft/min] / 33000
        power = Wt_rated * Vt_fpm / 33_000.0
        unit_power = "hp"
        unit_torque = "lbf·in"

    warns: list[str] = []
    if Wt_rated <= 0:
        warns.append("Rated tangential load Wt <= 0; check inputs.")
    # Aggregate Kv warnings
    if kv_res.get("warnings"):
        warns.extend(kv_res["warnings"])

    result: dict = {
        "ok": True,
        "Wt_bending_lim": Wt_bending,
        "Wt_contact_lim": Wt_contact,
        "Wt_rated": Wt_rated,
        "governing": governing,
        "power_rated": power,
        "torque_rated": torque,
        "unit_power": unit_power,
        "unit_torque": unit_torque,
        "Kv": Kv,
        "J": J,
        "I": I_val,
        "Vt_fpm": Vt_fpm,
        "metric": metric,
    }
    if warns:
        result["warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# 8. Service-life factors YN and ZN  (AGMA 2001-D04, Figs. 14-14 & 14-15)
# ---------------------------------------------------------------------------

# AGMA 2001-D04 stress-cycle factor equations (Shigley §14-5):
# For hardness >= 180 HB (through-hardened):
#   YN = 1.3558 N^-0.0178    (bending, N in cycles; range 3e6 – 10^10)
#   ZN = 1.4488 N^-0.023     (contact, N in cycles; range 10^7 – 10^10)
# For N < lower limit, AGMA uses:
#   YN = 2.3194 N^-0.0538    (< 3e6 cycles, hardened)
#   ZN = 1.4488 N^-0.023     (same formula; lower limit is 10^6)

_YN_LOW_THRESH  = 3e6    # below this, use low-cycle YN formula
_YN_HIGH_THRESH = 1e10   # above this, YN → floor (AGMA plateau)
_ZN_LOW_THRESH  = 1e6
_ZN_HIGH_THRESH = 1e10
_YN_PLATEAU     = 0.9    # conservative floor at very high cycles
_ZN_PLATEAU     = 0.9


def agma_service_life(
    N_cycles: float,
    *,
    hardness_HB: float = 200.0,
    gear_type: str = "through_hardened",
) -> dict:
    """
    AGMA 2001-D04 stress-cycle factors YN (bending) and ZN (contact).

    YN modifies the allowable bending stress for finite life:
        sigma_t_all = S_t · YN / (K_T · K_R)

    ZN modifies the allowable contact stress:
        sigma_c_all = S_c · ZN / (K_T · K_R)

    At long life (N → ∞) both approach a lower plateau (~0.9 per AGMA).

    Parameters
    ----------
    N_cycles : float
        Number of stress cycles (full load application cycles).  Must be > 0.
        For a rotating gear: N_cycles = n_rpm × 60 × hours.
        Use the pinion cycle count (higher speed → more cycles, lower YN/ZN).
    hardness_HB : float
        Brinell hardness of the gear material (HB).
        Used to select the AGMA equation variant:
          through-hardened: applies for HB 180–400.
    gear_type : str
        Currently supported: "through_hardened" (default).
        (Case-carburised / nitrided require tabulated S_t / S_c adjustments
        not needed for the YN/ZN factors themselves.)

    Returns
    -------
    dict
        ok        : True
        YN        : bending stress-cycle factor
        ZN        : contact stress-cycle factor
        N_cycles  : cycle count used
        hardness_HB
        regime    : "low_cycle" | "finite" | "long_life"
        warnings  : list (may be absent)

    References
    ----------
    AGMA 2001-D04, §§ 4.2.1, 4.2.2 (Figs. 14-14, 14-15)
    Shigley 10th ed., §14-5, Eqs. (14-31)–(14-35)
    """
    err = _guard_positive("N_cycles", N_cycles)
    if err:
        return _err(err)
    err = _guard_range("hardness_HB", hardness_HB, 100, 700)
    if err:
        return _err(err)

    supported = ("through_hardened",)
    if gear_type not in supported:
        return _err(f"gear_type {gear_type!r} not supported. Use one of {supported}.")

    N = float(N_cycles)

    warns: list[str] = []

    # ---- Bending cycle factor YN ----
    if N < 1000:
        # Very low cycle — treat as static; YN can be > 1 (some codes allow)
        YN = 2.3194 * (max(N, 1.0) ** -0.0538)
        regime = "low_cycle"
    elif N < _YN_LOW_THRESH:
        # Low-cycle finite life (< 3e6)
        YN = 2.3194 * (N ** -0.0538)
        regime = "finite"
    elif N <= _YN_HIGH_THRESH:
        # Standard finite-life range
        YN = 1.3558 * (N ** -0.0178)
        regime = "finite"
    else:
        # Long-life plateau
        YN = _YN_PLATEAU
        regime = "long_life"

    # Clamp to physical bounds
    YN = max(min(YN, 2.5), _YN_PLATEAU)

    # ---- Contact cycle factor ZN ----
    if N < _ZN_LOW_THRESH:
        ZN = 1.4488 * (max(N, 1.0) ** -0.023)
    elif N <= _ZN_HIGH_THRESH:
        ZN = 1.4488 * (N ** -0.023)
    else:
        ZN = _ZN_PLATEAU
    ZN = max(min(ZN, 2.0), _ZN_PLATEAU)

    # Hardness warning
    if hardness_HB < 180:
        warns.append(
            f"Hardness {hardness_HB} HB is below the AGMA through-hardened "
            "minimum (180 HB). Allowable stresses should be reduced."
        )
    if hardness_HB > 400:
        warns.append(
            f"Hardness {hardness_HB} HB exceeds through-hardened range (≤400 HB). "
            "Consider case-carburised or nitrided gear models."
        )

    result: dict = {
        "ok": True,
        "YN": YN,
        "ZN": ZN,
        "N_cycles": N,
        "hardness_HB": hardness_HB,
        "regime": regime,
    }
    if warns:
        result["warnings"] = warns
    return result
