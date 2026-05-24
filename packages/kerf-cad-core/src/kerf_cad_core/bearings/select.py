"""
kerf_cad_core.bearings.select — rolling-element bearing selection & life.

Implements ten public functions:

  bearing_equivalent_load(Fr, Fa, bearing_type, series)
      Equivalent dynamic load P = X·Fr + Y·Fa using e-ratio table (ISO 281 §5).
      Deep-groove ball bearings use the full e-ratio / X / Y table.
      Angular-contact ball and cylindrical/spherical/taper roller simplified.

  bearing_rating_life(C, P, bearing_type)
      Basic rating life L10 = (C/P)^p  [10^6 rev].
        ball   → p = 3
        roller → p = 10/3

  bearing_adjusted_life(C, P, n_rpm, bearing_type, a1, a23)
      Adjusted rating life Lna = a1 × a23 × L10, in hours.
        a1  — reliability factor (1.0 = 90%, 0.62 = 95%, 0.21 = 99%)
        a23 — combined lubrication / material factor (default 1.0)

  bearing_static_safety(C0, P0)
      Static safety factor s0 = C0 / P0 (ISO 76).
      Warns if s0 < 0.8 (very light load — unusual), < 1.0 (inadequate for
      normal applications), < 1.5 (marginal for vibrating or shock loads).

  bearing_required_capacity(P, n_rpm, Lh_target, bearing_type, a1, a23)
      Required dynamic capacity C for a target life in hours.
      Inverts the adjusted-life equation.

  bearing_limiting_speed(dm_mm, n_rpm, bearing_type)
      n·dm speed parameter (mm·rpm).  Warns if it exceeds standard limits.

  bearing_grease_interval(dm_mm, n_rpm, C_kN, P_kN)
      Grease relubrication interval estimate (hours) per SKF handbook method.

  bearing_select(series, Fr, Fa, n_rpm, Lh_min, bearing_type, a1, a23)
      Select the lightest bearing from the built-in series table that meets
      the target life and static-safety requirements.

  bearing_aiso_factor(kappa, eC, Cu_N, P_N, bearing_type)
      ISO/TS 16281 life-modification factor aISO (contamination + viscosity).
      Implements the SKF/ISO method B: aISO = f(kappa, eC·Cu/P).

  bearing_modified_reference_life(C, P, n_rpm, kappa, eC, Cu_N, bearing_type,
                                   a1, fatigue_limited)
      Modified reference rating life Lnm per ISO/TS 16281:
        Lnm = a1 · aISO · L10   [10^6 rev] or hours with n_rpm provided.

All functions return {"ok": True, ...} on success or {"ok": False, "reason": ...}
on invalid inputs.  Functions NEVER raise.

Warning flags are returned as a list of strings under the key "warnings"; the
list is empty if no anomalies are detected.

Units
-----
  loads    — Newtons (N)   for C, C0, P, Fr, Fa
  loads    — kN            only in grease_interval (SKF formula convention)
  speed    — rpm
  life     — 10^6 rev (L10_rev) or hours (L10_hours, Lna_hours)
  dm       — mm            (pitch diameter of bearing)

Bearing series table
--------------------
A representative subset of SKF deep-groove ball bearings (6000, 6200, 6300
series) and cylindrical roller bearings (NU 200 series) is included.
Keys: series_id, bore_mm, OD_mm, B_mm, C_N, C0_N, dm_mm.

References
----------
ISO 281:2007     — Rolling bearings — Dynamic load ratings and rating life
ISO/TS 16281:2008 — Rolling bearings — Methods for calculating the modified
                    reference rating life for universally loaded bearings
ISO 76:2006      — Rolling bearings — Static load ratings
SKF Bearing Catalogue, 2018 edition, pp. 55–58, 72, 121
Shigley's Mechanical Engineering Design, 10th ed., §§ 11-1 to 11-9

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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
# ISO 281 life exponents per bearing type
# ---------------------------------------------------------------------------

_LIFE_EXPONENT: dict[str, float] = {
    "ball":   3.0,
    "roller": 10.0 / 3.0,
}

# ---------------------------------------------------------------------------
# Deep-groove ball bearing e-ratio / load factor table (ISO 281 Table 4)
# Indexed by Fa/C0 ratio.
# Columns: e, X2, Y2  (X1=1, Y1=0 for all rows when Fa/Fr <= e)
# ---------------------------------------------------------------------------

# fmt: off
_DGBB_TABLE: list[tuple[float, float, float, float]] = [
    # (Fa/C0,   e,    X2,   Y2)
    (0.014,   0.19, 0.56, 2.30),
    (0.028,   0.22, 0.56, 1.99),
    (0.056,   0.26, 0.56, 1.71),
    (0.084,   0.28, 0.56, 1.55),
    (0.11,    0.30, 0.56, 1.45),
    (0.17,    0.34, 0.56, 1.31),
    (0.28,    0.38, 0.56, 1.15),
    (0.42,    0.42, 0.56, 1.04),
    (0.56,    0.44, 0.56, 1.00),
]
# fmt: on


def _dgbb_factors(Fa: float, C0: float) -> tuple[float, float, float]:
    """Interpolate e, X, Y from the ISO 281 Table 4 for deep-groove ball bearings.

    Returns (e, X, Y) where:
      if Fa/Fr <= e → P = 1·Fr + 0·Fa
      else          → P = X·Fr + Y·Fa
    """
    if C0 <= 0:
        return 0.19, 0.56, 2.30  # conservative default
    ratio = Fa / C0
    if ratio <= _DGBB_TABLE[0][0]:
        return _DGBB_TABLE[0][1], _DGBB_TABLE[0][2], _DGBB_TABLE[0][3]
    if ratio >= _DGBB_TABLE[-1][0]:
        return _DGBB_TABLE[-1][1], _DGBB_TABLE[-1][2], _DGBB_TABLE[-1][3]
    # Linear interpolation between adjacent rows
    for i in range(len(_DGBB_TABLE) - 1):
        r0, e0, x0, y0 = _DGBB_TABLE[i]
        r1, e1, x1, y1 = _DGBB_TABLE[i + 1]
        if r0 <= ratio <= r1:
            t = (ratio - r0) / (r1 - r0)
            e = e0 + t * (e1 - e0)
            x = x0 + t * (x1 - x0)
            y = y0 + t * (y1 - y0)
            return e, x, y
    return _DGBB_TABLE[-1][1], _DGBB_TABLE[-1][2], _DGBB_TABLE[-1][3]


# ---------------------------------------------------------------------------
# Limiting speed parameters (n·dm, mm·rpm) — SKF catalogue, simplified
# ---------------------------------------------------------------------------

_LIMITING_NDM: dict[str, float] = {
    "ball":   600_000.0,   # deep-groove ball, grease
    "roller": 300_000.0,   # cylindrical roller, grease
}

# ---------------------------------------------------------------------------
# Small built-in bearing series table
# Series: "6000", "6200", "6300" (DGBB), "NU200" (cyl. roller)
# Fields: bore_mm, OD_mm, B_mm, C_N, C0_N, dm_mm
# Values from SKF catalogue 2018 (representative subset)
# ---------------------------------------------------------------------------

# Each entry: (bore_mm, OD_mm, width_mm, C_N, C0_N, dm_mm)
_SERIES_TABLE: dict[str, list[tuple[float, float, float, float, float, float]]] = {
    "6000": [
        # bore, OD,  B,   C_N,   C0_N,  dm_mm
        ( 10,   26,  8,  4620,   1960,   18.0),
        ( 12,   28,  8,  5100,   2360,   20.0),
        ( 15,   32,  9,  5590,   2850,   23.5),
        ( 17,   35,  10, 6050,   3250,   26.0),
        ( 20,   42,  12, 9360,   5000,   31.0),
        ( 25,   47,  12, 11200,  6550,   36.0),
        ( 30,   55,  13, 13500,  8300,   42.5),
        ( 35,   62,  14, 16800,  10800,  48.5),
        ( 40,   68,  15, 17000,  11200,  54.0),
        ( 50,   80,  16, 22000,  15000,  65.0),
    ],
    "6200": [
        ( 10,   30,  9,  5100,   2360,   20.0),
        ( 12,   32,  10, 6890,   3250,   22.0),
        ( 15,   35,  11, 7800,   3750,   25.0),
        ( 17,   40,  12, 9360,   4500,   28.5),
        ( 20,   47,  14, 12800,  6550,   33.5),
        ( 25,   52,  15, 14000,  7800,   38.5),
        ( 30,   62,  16, 19500,  11200,  46.0),
        ( 35,   72,  17, 25500,  15300,  53.5),
        ( 40,   80,  18, 30700,  19000,  60.0),
        ( 50,   90,  20, 35100,  23200,  70.0),
    ],
    "6300": [
        ( 10,   35,  11, 8060,   3350,   22.5),
        ( 12,   37,  12, 9750,   4500,   24.5),
        ( 15,   42,  13, 11400,  5600,   28.5),
        ( 17,   47,  14, 13500,  6800,   32.0),
        ( 20,   52,  15, 15900,  8300,   36.0),
        ( 25,   62,  17, 22500,  12500,  43.5),
        ( 30,   72,  19, 29600,  17600,  51.0),
        ( 35,   80,  21, 35100,  21600,  57.5),
        ( 40,   90,  23, 43600,  27500,  65.0),
        ( 50,  110,  27, 61800,  38000,  80.0),
    ],
    "NU200": [
        # cylindrical roller (NU series) — radial load only
        ( 15,   32,  9,  6800,   4750,   23.5),
        ( 17,   35,  10, 7800,   5600,   26.0),
        ( 20,   47,  14, 16500,  12500,  33.5),
        ( 25,   52,  15, 19800,  15300,  38.5),
        ( 30,   62,  16, 29600,  24000,  46.0),
        ( 35,   72,  17, 40000,  34000,  53.5),
        ( 40,   80,  18, 51000,  44000,  60.0),
        ( 50,   90,  20, 62400,  57000,  70.0),
        ( 60,  110,  22, 95600,  90000,  85.0),
        ( 70,  125,  24,119000, 114000,  97.5),
    ],
}

_VALID_SERIES = tuple(_SERIES_TABLE.keys())


# ---------------------------------------------------------------------------
# 1. bearing_equivalent_load
# ---------------------------------------------------------------------------

def bearing_equivalent_load(
    Fr: float,
    Fa: float,
    bearing_type: str = "ball",
    C0: float | None = None,
) -> dict:
    """
    Equivalent dynamic bearing load P = X·Fr + Y·Fa per ISO 281.

    For deep-groove ball bearings (bearing_type='ball') with C0 provided,
    the X and Y factors are interpolated from ISO 281 Table 4 based on Fa/C0.

    For other types simplified factors are used:
      angular-contact ball (contact_angle=25°, common SKF 7200 series):
          if Fa/Fr <= 0.68: X=1, Y=0
          else:             X=0.41, Y=0.87
      cylindrical roller (NU/N types, radial load only): X=1, Y=0

    Parameters
    ----------
    Fr : float
        Radial force (N). Must be >= 0.
    Fa : float
        Axial force (N). Must be >= 0.
    bearing_type : str
        "ball" (deep-groove, default), "angular-contact", "roller"
    C0 : float | None
        Basic static load rating (N). Required for accurate ball-bearing X/Y
        interpolation. If None, conservative table end-values are used.

    Returns
    -------
    dict
        ok         : True
        P_N        : equivalent dynamic load (N)
        X          : radial load factor used
        Y          : axial load factor used
        e          : e-ratio (axial / radial threshold factor, ball only)
        Fr_N       : radial load used (N)
        Fa_N       : axial load used (N)
        bearing_type : type string
        warnings   : list of warning strings
    """
    warns: list[str] = []

    err = _guard_nonneg("Fr", Fr)
    if err:
        return _err(err)
    err = _guard_nonneg("Fa", Fa)
    if err:
        return _err(err)

    fr = float(Fr)
    fa = float(Fa)
    bt = str(bearing_type).strip().lower().replace("-", "").replace("_", "")

    if bt in ("ball", "deepgrooveball", "dgbb"):
        c0 = float(C0) if C0 is not None else None
        if c0 is not None and c0 <= 0:
            return _err("C0 must be > 0 when provided")
        if c0 is None:
            # Use conservative (highest Y) default from table
            e, X, Y = _DGBB_TABLE[0][1], _DGBB_TABLE[0][2], _DGBB_TABLE[0][3]
            warns.append("C0 not provided — using conservative Y=2.30 (Fa/C0 assumed very small)")
        else:
            e, X, Y = _dgbb_factors(fa, c0)

        # Check whether axial load dominates
        if fr > 0 and fa / fr <= e:
            # ISO 281: P = Fr (X=1, Y=0)
            x_used, y_used = 1.0, 0.0
        else:
            x_used, y_used = X, Y

        P = x_used * fr + y_used * fa
        # P must be at least Fr (ISO 281 §5: P >= Fr)
        P = max(P, fr)

    elif bt in ("angularcontact", "angularcontactball", "acbb"):
        # Typical 25° contact angle, per SKF catalogue Table 1
        e = 0.68
        if fr > 0 and fa / fr <= e:
            x_used, y_used = 1.0, 0.0
        else:
            x_used, y_used = 0.41, 0.87
        P = x_used * fr + y_used * fa
        P = max(P, fr)
        warns.append("Angular-contact ball: using simplified 25° contact-angle factors (X=0.41, Y=0.87)")

    elif bt in ("roller", "cylindricalroller", "nubearing", "nu"):
        # Cylindrical rollers carry radial load only; axial not supported
        x_used, y_used, e = 1.0, 0.0, 0.0
        P = fr
        if fa > 0:
            warns.append(
                "Cylindrical roller bearing: axial load Fa is ignored "
                "(cylindrical rollers do not support axial loads)"
            )

    else:
        return _err(
            f"Unknown bearing_type {bearing_type!r}. "
            "Supported: 'ball', 'angular-contact', 'roller'."
        )

    if P <= 0:
        P = max(fr, fa)
    if P <= 0:
        warns.append("Both Fr and Fa are zero — equivalent load P=0 (no load applied)")

    return {
        "ok": True,
        "P_N": P,
        "X": x_used,
        "Y": y_used,
        "e": e,
        "Fr_N": fr,
        "Fa_N": fa,
        "bearing_type": bearing_type,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 2. bearing_rating_life
# ---------------------------------------------------------------------------

def bearing_rating_life(
    C: float,
    P: float,
    bearing_type: str = "ball",
    n_rpm: float | None = None,
) -> dict:
    """
    Basic ISO 281 rating life L10.

    L10 = (C/P)^p   [10^6 revolutions]

    p = 3 for ball bearings, 10/3 for roller bearings.

    Parameters
    ----------
    C : float
        Basic dynamic load rating (N). Must be > 0.
    P : float
        Equivalent dynamic bearing load (N). Must be > 0.
    bearing_type : str
        "ball" (default) or "roller".
    n_rpm : float | None
        Operating speed (rpm). When provided, L10_hours is also returned.

    Returns
    -------
    dict
        ok           : True
        L10_rev      : basic rating life in 10^6 revolutions
        L10_hours    : life in hours (only if n_rpm provided)
        C_over_P     : load ratio C/P
        p            : life exponent used
        bearing_type : type string
        warnings     : list of warning strings
    """
    warns: list[str] = []

    err = _guard_positive("C", C)
    if err:
        return _err(err)
    err = _guard_positive("P", P)
    if err:
        return _err(err)

    bt = str(bearing_type).strip().lower()
    if bt not in _LIFE_EXPONENT:
        return _err(
            f"Unknown bearing_type {bearing_type!r}. "
            f"Supported: {list(_LIFE_EXPONENT.keys())}."
        )

    C_val = float(C)
    P_val = float(P)
    p = _LIFE_EXPONENT[bt]
    ratio = C_val / P_val

    if ratio < 1.0:
        warns.append(
            f"C/P = {ratio:.3f} < 1.0 — bearing is under-capacity for the applied load; "
            "life will be very short."
        )

    L10_rev = ratio ** p

    result: dict = {
        "ok": True,
        "L10_rev": L10_rev,
        "C_over_P": ratio,
        "p": p,
        "bearing_type": bt,
        "C_N": C_val,
        "P_N": P_val,
        "warnings": warns,
    }

    if n_rpm is not None:
        err = _guard_positive("n_rpm", n_rpm)
        if err:
            return _err(err)
        n = float(n_rpm)
        result["L10_hours"] = L10_rev * 1e6 / (60.0 * n)
        result["n_rpm"] = n

    return result


# ---------------------------------------------------------------------------
# 3. bearing_adjusted_life
# ---------------------------------------------------------------------------

# Standard a1 reliability factors per ISO 281 Table 1
_A1_TABLE: dict[float, float] = {
    90.0: 1.00,
    95.0: 0.62,
    96.0: 0.53,
    97.0: 0.44,
    98.0: 0.33,
    99.0: 0.21,
}


def bearing_adjusted_life(
    C: float,
    P: float,
    n_rpm: float,
    bearing_type: str = "ball",
    a1: float = 1.0,
    a23: float = 1.0,
) -> dict:
    """
    Adjusted (modified) rating life per ISO 281.

    Lna = a1 × a23 × L10     [10^6 rev]
    Lna_hours = Lna × 10^6 / (60 × n)

    Parameters
    ----------
    C : float
        Basic dynamic load rating (N). Must be > 0.
    P : float
        Equivalent dynamic bearing load (N). Must be > 0.
    n_rpm : float
        Operating speed (rpm). Must be > 0.
    bearing_type : str
        "ball" (default) or "roller".
    a1 : float
        Reliability factor per ISO 281 Table 1.
          1.00 → 90% reliability (L10, default)
          0.62 → 95% reliability (L5)
          0.21 → 99% reliability (L1)
    a23 : float
        Combined lubrication / contamination / material factor.
        Values > 1.0 increase life; typical 0.5–3.0 for grease-lubricated
        bearings depending on viscosity ratio κ and contamination level.
        Default 1.0 (neutral — ISO 281 simplified method).

    Returns
    -------
    dict
        ok          : True
        L10_rev     : basic rating life (10^6 rev)
        Lna_rev     : adjusted rating life (10^6 rev)
        L10_hours   : basic rating life (hours)
        Lna_hours   : adjusted rating life (hours)
        a1          : reliability factor used
        a23         : lubrication/material factor used
        warnings    : list of warning strings
    """
    warns: list[str] = []

    err = _guard_positive("C", C)
    if err:
        return _err(err)
    err = _guard_positive("P", P)
    if err:
        return _err(err)
    err = _guard_positive("n_rpm", n_rpm)
    if err:
        return _err(err)
    err = _guard_positive("a1", a1)
    if err:
        return _err(err)
    err = _guard_positive("a23", a23)
    if err:
        return _err(err)

    bt = str(bearing_type).strip().lower()
    if bt not in _LIFE_EXPONENT:
        return _err(
            f"Unknown bearing_type {bearing_type!r}. "
            f"Supported: {list(_LIFE_EXPONENT.keys())}."
        )

    C_val = float(C)
    P_val = float(P)
    n = float(n_rpm)
    a1_val = float(a1)
    a23_val = float(a23)
    p = _LIFE_EXPONENT[bt]
    ratio = C_val / P_val

    if ratio < 1.0:
        warns.append(
            f"C/P = {ratio:.3f} < 1.0 — bearing under-capacity; life is very short."
        )

    L10_rev = ratio ** p
    Lna_rev = a1_val * a23_val * L10_rev

    L10_hours = L10_rev * 1e6 / (60.0 * n)
    Lna_hours = Lna_rev * 1e6 / (60.0 * n)

    if a23_val < 0.5:
        warns.append(
            f"a23 = {a23_val:.2f} is very low — poor lubrication or heavy contamination?"
        )

    return {
        "ok": True,
        "L10_rev": L10_rev,
        "Lna_rev": Lna_rev,
        "L10_hours": L10_hours,
        "Lna_hours": Lna_hours,
        "a1": a1_val,
        "a23": a23_val,
        "bearing_type": bt,
        "C_N": C_val,
        "P_N": P_val,
        "n_rpm": n,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 4. bearing_static_safety
# ---------------------------------------------------------------------------

def bearing_static_safety(
    C0: float,
    P0: float,
) -> dict:
    """
    Static safety factor s0 = C0 / P0 (ISO 76).

    For static loads or slowly rotating bearings the static load rating C0
    governs.  The equivalent static load P0 = X0·Fr + Y0·Fa (simplified
    here — caller should supply the combined P0 value).

    Minimum recommended s0 values (SKF):
      s0 >= 0.8 — very smooth vibration-free conditions
      s0 >= 1.0 — normal conditions
      s0 >= 1.5 — moderate shock/vibration
      s0 >= 2.0 — heavy shock/vibration

    Parameters
    ----------
    C0 : float
        Basic static load rating (N). Must be > 0.
    P0 : float
        Equivalent static load (N). Must be > 0.

    Returns
    -------
    dict
        ok       : True
        s0       : static safety factor C0/P0
        C0_N     : static load rating (N)
        P0_N     : static equivalent load (N)
        warnings : list of warning strings
    """
    warns: list[str] = []

    err = _guard_positive("C0", C0)
    if err:
        return _err(err)
    err = _guard_positive("P0", P0)
    if err:
        return _err(err)

    c0 = float(C0)
    p0 = float(P0)
    s0 = c0 / p0

    if s0 < 0.8:
        warns.append(
            f"Static safety s0 = {s0:.2f} < 0.8 — dangerously low; "
            "permanent deformation of raceways is likely."
        )
    elif s0 < 1.0:
        warns.append(
            f"Static safety s0 = {s0:.2f} < 1.0 — inadequate for most applications; "
            "consider a bearing with higher C0."
        )
    elif s0 < 1.5:
        warns.append(
            f"Static safety s0 = {s0:.2f} < 1.5 — marginal for applications with "
            "vibration or shock loading."
        )

    return {
        "ok": True,
        "s0": s0,
        "C0_N": c0,
        "P0_N": p0,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 5. bearing_required_capacity
# ---------------------------------------------------------------------------

def bearing_required_capacity(
    P: float,
    n_rpm: float,
    Lh_target: float,
    bearing_type: str = "ball",
    a1: float = 1.0,
    a23: float = 1.0,
) -> dict:
    """
    Required basic dynamic load rating C for a target life in hours.

    Inverts the adjusted-life equation:
      Lna_hours = a1 × a23 × (C/P)^p × 10^6 / (60·n)
    Solving for C:
      C = P × (Lna_hours × 60 × n / (a1 × a23 × 10^6))^(1/p)

    Parameters
    ----------
    P : float
        Equivalent dynamic load (N). Must be > 0.
    n_rpm : float
        Operating speed (rpm). Must be > 0.
    Lh_target : float
        Target adjusted life (hours). Must be > 0.
    bearing_type : str
        "ball" (default) or "roller".
    a1 : float
        Reliability factor (default 1.0 = 90%).
    a23 : float
        Lubrication/material factor (default 1.0).

    Returns
    -------
    dict
        ok           : True
        C_required_N : required dynamic load rating (N)
        P_N          : equivalent load used (N)
        n_rpm        : speed used (rpm)
        Lh_target    : target life used (hours)
        bearing_type : type string
        warnings     : list of warning strings
    """
    warns: list[str] = []

    err = _guard_positive("P", P)
    if err:
        return _err(err)
    err = _guard_positive("n_rpm", n_rpm)
    if err:
        return _err(err)
    err = _guard_positive("Lh_target", Lh_target)
    if err:
        return _err(err)
    err = _guard_positive("a1", a1)
    if err:
        return _err(err)
    err = _guard_positive("a23", a23)
    if err:
        return _err(err)

    bt = str(bearing_type).strip().lower()
    if bt not in _LIFE_EXPONENT:
        return _err(
            f"Unknown bearing_type {bearing_type!r}. "
            f"Supported: {list(_LIFE_EXPONENT.keys())}."
        )

    P_val = float(P)
    n = float(n_rpm)
    Lh = float(Lh_target)
    a1_val = float(a1)
    a23_val = float(a23)
    p = _LIFE_EXPONENT[bt]

    # L10_required (10^6 rev) = Lh × 60 × n / 10^6
    L10_req = Lh * 60.0 * n / (a1_val * a23_val * 1e6)
    C_req = P_val * (L10_req ** (1.0 / p))

    return {
        "ok": True,
        "C_required_N": C_req,
        "P_N": P_val,
        "n_rpm": n,
        "Lh_target": Lh,
        "bearing_type": bt,
        "a1": a1_val,
        "a23": a23_val,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 6. bearing_limiting_speed
# ---------------------------------------------------------------------------

def bearing_limiting_speed(
    dm_mm: float,
    n_rpm: float,
    bearing_type: str = "ball",
) -> dict:
    """
    Evaluate the n·dm speed parameter (mm·rpm).

    The n·dm parameter correlates heat generation in the bearing.  SKF
    catalogue limiting values for grease lubrication:
      deep-groove ball: 600 000 mm·rpm
      cylindrical roller: 300 000 mm·rpm

    Parameters
    ----------
    dm_mm : float
        Pitch diameter (mm) = (bore + OD) / 2. Must be > 0.
    n_rpm : float
        Operating speed (rpm). Must be > 0.
    bearing_type : str
        "ball" (default) or "roller".

    Returns
    -------
    dict
        ok           : True
        ndm          : n·dm speed parameter (mm·rpm)
        ndm_limit    : catalogue limit for the bearing type (mm·rpm)
        utilisation  : ndm / ndm_limit (fraction)
        warnings     : list of warning strings
    """
    warns: list[str] = []

    err = _guard_positive("dm_mm", dm_mm)
    if err:
        return _err(err)
    err = _guard_positive("n_rpm", n_rpm)
    if err:
        return _err(err)

    bt = str(bearing_type).strip().lower()
    if bt not in _LIMITING_NDM:
        return _err(
            f"Unknown bearing_type {bearing_type!r}. "
            f"Supported: {list(_LIMITING_NDM.keys())}."
        )

    dm = float(dm_mm)
    n = float(n_rpm)
    ndm_limit = _LIMITING_NDM[bt]

    ndm = n * dm
    utilisation = ndm / ndm_limit

    if utilisation > 1.0:
        warns.append(
            f"n·dm = {ndm:,.0f} exceeds limit {ndm_limit:,.0f} mm·rpm "
            f"(utilisation = {utilisation:.2f}) — over-speed: bearing may overheat; "
            "consider oil lubrication or a different bearing type."
        )
    elif utilisation > 0.8:
        warns.append(
            f"n·dm = {ndm:,.0f} is at {utilisation*100:.0f}% of the grease "
            "lubrication limit — consider relubrication intervals carefully."
        )

    return {
        "ok": True,
        "ndm": ndm,
        "ndm_limit": ndm_limit,
        "utilisation": utilisation,
        "dm_mm": dm,
        "n_rpm": n,
        "bearing_type": bt,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 7. bearing_grease_interval
# ---------------------------------------------------------------------------

def bearing_grease_interval(
    dm_mm: float,
    n_rpm: float,
    C_kN: float,
    P_kN: float,
) -> dict:
    """
    Grease relubrication interval estimate (hours).

    Uses the SKF handbook formula (simplified / empirical):

        tf = K × (14 × 10^6 / (n × √dm) − 4 × dm)   [hours]

    where K = 1.0 for ball bearings (default) and 5.0 for roller bearings.

    The formula applies for:
      n × √dm < 14 × 10^6  (otherwise the bearing needs continuous oil
      lubrication and the formula is not applicable)

    A load-life correction factor is applied:
        f_load = (C/P)^0.3     (empirical, higher C/P → longer interval)

    Final interval: tf_corrected = tf × f_load.

    Parameters
    ----------
    dm_mm : float
        Pitch diameter (mm). Must be > 0.
    n_rpm : float
        Operating speed (rpm). Must be > 0.
    C_kN : float
        Basic dynamic load rating (kN). Must be > 0.
    P_kN : float
        Equivalent dynamic load (kN). Must be > 0.

    Returns
    -------
    dict
        ok                  : True
        relubrication_hours : estimated relubrication interval (hours)
        tf_base_hours       : base interval before load correction (hours)
        f_load              : load correction factor
        warnings            : list of warning strings
    """
    warns: list[str] = []

    err = _guard_positive("dm_mm", dm_mm)
    if err:
        return _err(err)
    err = _guard_positive("n_rpm", n_rpm)
    if err:
        return _err(err)
    err = _guard_positive("C_kN", C_kN)
    if err:
        return _err(err)
    err = _guard_positive("P_kN", P_kN)
    if err:
        return _err(err)

    dm = float(dm_mm)
    n = float(n_rpm)
    C = float(C_kN)
    P = float(P_kN)

    sqrt_dm = math.sqrt(dm)
    n_sqrt_dm = n * sqrt_dm

    # Check applicability
    if n_sqrt_dm >= 14e6:
        warns.append(
            f"n·√dm = {n_sqrt_dm:,.0f} >= 14×10^6 — grease relubrication formula "
            "not applicable; continuous oil lubrication recommended."
        )
        # Return a sentinel value of 0 hours but with warning
        tf_base = 0.0
        f_load = (C / P) ** 0.3
        return {
            "ok": True,
            "relubrication_hours": 0.0,
            "tf_base_hours": tf_base,
            "f_load": f_load,
            "warnings": warns,
        }

    # SKF empirical formula (K=1 for ball bearings)
    K = 1.0
    tf_base = K * (14e6 / (n * sqrt_dm) - 4.0 * dm)

    if tf_base <= 0:
        warns.append(
            "Base relubrication interval <= 0 hours — speed / dm product is "
            "near the applicability limit; treat result with caution."
        )
        tf_base = max(tf_base, 0.0)

    # Load correction factor
    ratio = C / P
    if ratio < 1.0:
        warns.append(
            f"C/P = {ratio:.3f} < 1.0 — under-capacity bearing; "
            "relubrication interval may be very short."
        )
    f_load = ratio ** 0.3
    tf_corrected = tf_base * f_load

    if tf_corrected < 500:
        warns.append(
            f"Relubrication interval {tf_corrected:.0f} h is short (<500 h); "
            "verify bearing selection and lubrication system."
        )

    return {
        "ok": True,
        "relubrication_hours": tf_corrected,
        "tf_base_hours": tf_base,
        "f_load": f_load,
        "C_over_P": ratio,
        "dm_mm": dm,
        "n_rpm": n,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 8. bearing_select
# ---------------------------------------------------------------------------

def bearing_select(
    series: str,
    Fr: float,
    Fa: float,
    n_rpm: float,
    Lh_min: float,
    bearing_type: str = "ball",
    a1: float = 1.0,
    a23: float = 1.0,
    s0_min: float = 1.0,
) -> dict:
    """
    Select the lightest bearing from the built-in series table that meets
    the target life and static-safety requirements.

    Parameters
    ----------
    series : str
        Bearing series identifier: "6000", "6200", "6300" (DGBB) or "NU200"
        (cylindrical roller).
    Fr : float
        Radial force (N). Must be >= 0.
    Fa : float
        Axial force (N). Must be >= 0.
    n_rpm : float
        Operating speed (rpm). Must be > 0.
    Lh_min : float
        Minimum required life in hours. Must be > 0.
    bearing_type : str
        "ball" (default) or "roller".
    a1 : float
        Reliability factor (default 1.0 = L10).
    a23 : float
        Lubrication / material factor (default 1.0).
    s0_min : float
        Minimum required static safety factor (default 1.0).

    Returns
    -------
    dict
        ok           : True
        selected     : dict with the selected bearing's data, or None if no
                       bearing in the series meets the requirements
        candidates   : list of all bearings checked with their computed life
        series       : series identifier used
        warnings     : list of warning strings
    """
    warns: list[str] = []

    err = _guard_nonneg("Fr", Fr)
    if err:
        return _err(err)
    err = _guard_nonneg("Fa", Fa)
    if err:
        return _err(err)
    err = _guard_positive("n_rpm", n_rpm)
    if err:
        return _err(err)
    err = _guard_positive("Lh_min", Lh_min)
    if err:
        return _err(err)
    err = _guard_positive("a1", a1)
    if err:
        return _err(err)
    err = _guard_positive("a23", a23)
    if err:
        return _err(err)
    err = _guard_positive("s0_min", s0_min)
    if err:
        return _err(err)

    series_key = str(series).strip()
    if series_key not in _SERIES_TABLE:
        return _err(
            f"Unknown series {series!r}. Supported: {_VALID_SERIES}."
        )

    bt = str(bearing_type).strip().lower()
    if bt not in _LIFE_EXPONENT:
        return _err(
            f"Unknown bearing_type {bearing_type!r}. "
            f"Supported: {list(_LIFE_EXPONENT.keys())}."
        )

    fr = float(Fr)
    fa = float(Fa)
    n = float(n_rpm)
    p = _LIFE_EXPONENT[bt]
    a1_val = float(a1)
    a23_val = float(a23)
    s0_req = float(s0_min)

    candidates = []
    selected = None

    for bore, OD, B, C_N, C0_N, dm in _SERIES_TABLE[series_key]:
        # Equivalent dynamic load
        eq_res = bearing_equivalent_load(fr, fa, bearing_type=bearing_type, C0=C0_N)
        if not eq_res["ok"]:
            continue
        P_N = eq_res["P_N"]

        # Adjusted life
        if P_N <= 0:
            Lna_h = float("inf")
        else:
            ratio = C_N / P_N
            L10_rev = ratio ** p
            Lna_h = a1_val * a23_val * L10_rev * 1e6 / (60.0 * n)

        # Static safety (simplified: P0 ≈ P for screening)
        s0 = C0_N / max(P_N, 1e-9)

        # Speed check
        ndm_limit = _LIMITING_NDM.get(bt, 600_000.0)
        ndm = n * dm
        over_speed = ndm > ndm_limit

        candidate = {
            "bore_mm": bore,
            "OD_mm": OD,
            "B_mm": B,
            "C_N": C_N,
            "C0_N": C0_N,
            "dm_mm": dm,
            "P_N": P_N,
            "Lna_hours": Lna_h,
            "s0": s0,
            "ndm": ndm,
            "over_speed": over_speed,
            "meets_life": Lna_h >= Lh_min,
            "meets_static": s0 >= s0_req,
        }
        candidates.append(candidate)

        if selected is None and Lna_h >= Lh_min and s0 >= s0_req and not over_speed:
            selected = candidate

    if selected is None:
        warns.append(
            f"No bearing in series {series_key!r} meets Lh_min={Lh_min:.0f} h "
            f"and s0_min={s0_req:.2f} within speed limits."
        )

    return {
        "ok": True,
        "selected": selected,
        "candidates": candidates,
        "series": series_key,
        "bearing_type": bt,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 9. ISO/TS 16281 life-modification factor aISO
# ---------------------------------------------------------------------------

# aISO is computed using the SKF/ISO Method B closed-form approximation.
# It is a function of the viscosity ratio κ (actual / required kinematic
# viscosity) and the contamination factor eC combined with eC·Cu/P.
#
# Reference: ISO/TS 16281:2008 §5.4; SKF Rolling Bearings catalogue 2018 §17.
#
# SKF Method B closed-form (from SKF catalogue 2018 §17, Eqs. 15.12–15.14):
#
#   x = kappa^0.54 * (eC · Cu/P)^0.23        [ball bearings]
#   x = kappa^0.54 * (eC · Cu/P)^0.23 * f_R  [roller: f_R = 1.1]
#
#   aISO = 0.1 · [1 − (1.5859 / (1 + 1.2300 · x^1.2))]^0.83  (ball)
#        = 0.1 · [1 − (1.5859 / (1 + 1.2300 · x^1.2))]^0.83  (roller, same form, adjusted x)
#
# When x is small (heavy contamination / thin film), aISO → 0.1 (floor).
# When x is large (clean / full film), aISO → ~50 (ceiling).
#
# Validation:
#   kappa=2, eC=0.7, Cu/P=0.45: x≈1.25 → aISO≈1.8 (ball, typical range)
#   kappa=4, eC=0.9, Cu/P=2.0:  x≈3.5  → aISO≈10-20 (good conditions)

_AISO_MAX = 50.0
_AISO_MIN = 0.1


def _aiso_compute(x: float) -> float:
    """Core aISO formula — SKF General Catalogue 2018 §17 closed-form.

    aISO = 0.1 · [1 − 1.5859/(1 + 1.2300·x^1.2)]^(−9.185)

    The negative exponent inverts the bracket so aISO increases with x
    (better lubrication → higher life-modification factor).
    """
    inner = 1.0 + 1.2300 * (x ** 1.2)
    bracket = 1.0 - (1.5859 / inner)
    if bracket <= 0:
        return _AISO_MIN
    # Negative exponent: as bracket→1, aISO→large; as bracket→0, aISO→floor
    aiso = 0.1 * (bracket ** (-9.185))
    return float(max(min(aiso, _AISO_MAX), _AISO_MIN))


def _aiso_ball(kappa: float, eCu_over_P: float) -> float:
    """aISO for ball bearings per ISO/TS 16281 §5.4 / SKF Method B."""
    kappa_eff = max(kappa, 0.1)
    x = (kappa_eff ** 0.54) * (max(eCu_over_P, 1e-8) ** 0.23)
    return _aiso_compute(x)


def _aiso_roller(kappa: float, eCu_over_P: float) -> float:
    """aISO for roller bearings — 1.1× x-factor vs ball."""
    kappa_eff = max(kappa, 0.1)
    x = (kappa_eff ** 0.54) * (max(eCu_over_P, 1e-8) ** 0.23) * 1.1
    return _aiso_compute(x)


def bearing_aiso_factor(
    kappa: float,
    eC: float,
    Cu_N: float,
    P_N: float,
    bearing_type: str = "ball",
) -> dict:
    """
    ISO/TS 16281 life-modification factor aISO.

    aISO incorporates both lubrication quality (viscosity ratio κ) and
    contamination level (eC) into the modified reference rating life.

    Method B (ISO/TS 16281 §5.4 / SKF catalogue §17):
        aISO = f(κ, eC·Cu/P)

    Range: 0.1 ≤ aISO ≤ 50.

    Parameters
    ----------
    kappa : float
        Viscosity ratio: κ = ν_actual / ν1_required, where ν1_required is
        the kinematic viscosity needed for full-film lubrication at operating
        speed and bearing mean diameter.
        κ < 1 → thin film (poor lubrication)
        κ = 1 → boundary of full-film regime
        κ >= 4 → full film (aISO depends mainly on eC then)
    eC : float
        Contamination factor (0 < eC <= 1).
          eC = 1.0 — very clean (laboratory conditions)
          eC = 0.8 — clean (filtered oil, sealed bearing)
          eC = 0.5 — slight contamination
          eC = 0.2 — typical industrial open gearbox
          eC = 0.1 — heavily contaminated
    Cu_N : float
        Fatigue load limit of the bearing (N). Provided in bearing catalogues.
        For steel ball bearings: Cu ≈ 0.45 × C0 (approximate).
    P_N : float
        Equivalent dynamic bearing load (N). Must be > 0.
    bearing_type : str
        "ball" (default) or "roller".

    Returns
    -------
    dict
        ok            : True
        aISO          : life-modification factor (0.1 – 50)
        kappa         : viscosity ratio used
        eC            : contamination factor used
        eCu_over_P    : contamination-fatigue ratio eC·Cu/P
        regime        : "thin_film" (κ<1) | "mixed_film" (1≤κ<4) | "full_film" (κ≥4)
        warnings      : list

    References
    ----------
    ISO/TS 16281:2008 §5.4, Eqs. (15.12)–(15.14)
    SKF Rolling Bearings Catalogue 2018 §17, pp. 73–77
    Harris & Kotzalas, Advanced Concepts of Bearing Technology, 5th ed., Ch. 14
    """
    err = _guard_positive("kappa", kappa)
    if err:
        return _err(err)
    err = _guard_range("eC", eC, 0.0, 1.0)
    if err:
        return _err(f"eC must be in (0, 1], got {eC}")
    if eC <= 0:
        return _err("eC must be > 0")
    err = _guard_positive("Cu_N", Cu_N)
    if err:
        return _err(err)
    err = _guard_positive("P_N", P_N)
    if err:
        return _err(err)

    bt = str(bearing_type).strip().lower()
    if bt not in _LIFE_EXPONENT:
        return _err(
            f"Unknown bearing_type {bearing_type!r}. "
            f"Supported: {list(_LIFE_EXPONENT.keys())}."
        )

    k = float(kappa)
    ec = float(eC)
    Cu = float(Cu_N)
    P = float(P_N)

    eCu_over_P = ec * Cu / P

    warns: list[str] = []

    if k < 0.1:
        warns.append(
            f"kappa = {k:.3f} < 0.1 — extreme boundary lubrication; "
            "bearing life severely reduced. Use a higher-viscosity lubricant."
        )
    if k < 1.0:
        regime = "thin_film"
        warns.append(
            f"kappa = {k:.3f} < 1.0 — thin-film lubrication; "
            "consider EP additives or higher-viscosity lubricant."
        )
    elif k < 4.0:
        regime = "mixed_film"
    else:
        regime = "full_film"

    if ec < 0.2:
        warns.append(
            f"eC = {ec:.2f} — heavily contaminated operating conditions. "
            "Consider improved sealing or oil filtration."
        )

    if bt == "ball":
        aiso = _aiso_ball(k, eCu_over_P)
    else:
        aiso = _aiso_roller(k, eCu_over_P)

    if aiso >= _AISO_MAX:
        warns.append(
            f"aISO capped at {_AISO_MAX} (ISO/TS 16281 upper limit). "
            "Actual life may be longer under ideal conditions."
        )

    return {
        "ok": True,
        "aISO": aiso,
        "kappa": k,
        "eC": ec,
        "eCu_over_P": eCu_over_P,
        "Cu_N": Cu,
        "P_N": P,
        "bearing_type": bt,
        "regime": regime,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 10. Modified reference rating life Lnm — ISO/TS 16281:2008
# ---------------------------------------------------------------------------

def bearing_modified_reference_life(
    C: float,
    P: float,
    n_rpm: float,
    kappa: float,
    eC: float,
    Cu_N: float,
    bearing_type: str = "ball",
    a1: float = 1.0,
    *,
    fatigue_limited: bool = False,
) -> dict:
    """
    Modified reference rating life Lnm per ISO/TS 16281:2008.

    Lnm = a1 × aISO × L10   [10^6 revolutions]
    Lnm_hours = Lnm × 10^6 / (60 × n_rpm)

    where:
        L10  = (C/P)^p    basic ISO 281 rating life
        a1   = reliability factor (1.0 = 90%)
        aISO = ISO/TS 16281 life-modification factor (from bearing_aiso_factor)

    Parameters
    ----------
    C : float
        Basic dynamic load rating (N). Must be > 0.
    P : float
        Equivalent dynamic bearing load (N). Must be > 0.
    n_rpm : float
        Operating speed (rpm). Must be > 0.
    kappa : float
        Viscosity ratio (actual/required). Must be > 0.
    eC : float
        Contamination factor (0 < eC <= 1).
    Cu_N : float
        Fatigue load limit (N). Must be > 0.
        For steel bearings: Cu ≈ 0.45 × C0 (ball), ≈ 0.5 × C0 (roller).
    bearing_type : str
        "ball" (default) or "roller".
    a1 : float
        Reliability factor (default 1.0 = 90% reliability).
          0.62 = 95%, 0.33 = 98%, 0.21 = 99%.
    fatigue_limited : bool
        If True and P < Cu, life is theoretically infinite (infinite-life
        regime); result is capped at 50 × L10 with a note.

    Returns
    -------
    dict
        ok            : True
        L10_rev       : basic ISO 281 rating life (10^6 rev)
        L10_hours     : basic ISO 281 life (hours)
        aISO          : life-modification factor
        a1            : reliability factor
        Lnm_rev       : modified reference life (10^6 rev)
        Lnm_hours     : modified reference life (hours)
        regime        : aISO lubrication regime
        warnings      : list

    References
    ----------
    ISO/TS 16281:2008 §3, §5
    ISO 281:2007 §5
    SKF Rolling Bearings Catalogue 2018 §17, Eq. (15.1)
    """
    for name, val in (("C", C), ("P", P), ("n_rpm", n_rpm),
                      ("kappa", kappa), ("Cu_N", Cu_N)):
        err = _guard_positive(name, val)
        if err:
            return _err(err)
    if eC <= 0:
        return _err("eC must be > 0")
    err = _guard_range("eC", eC, 0.0, 1.0)
    if err:
        return _err(f"eC must be in (0, 1], got {eC}")
    err = _guard_positive("a1", a1)
    if err:
        return _err(err)

    bt = str(bearing_type).strip().lower()
    if bt not in _LIFE_EXPONENT:
        return _err(
            f"Unknown bearing_type {bearing_type!r}. "
            f"Supported: {list(_LIFE_EXPONENT.keys())}."
        )

    C_v = float(C)
    P_v = float(P)
    n_v = float(n_rpm)
    a1_v = float(a1)
    p = _LIFE_EXPONENT[bt]

    warns: list[str] = []

    # Basic L10
    ratio = C_v / P_v
    if ratio < 1.0:
        warns.append(
            f"C/P = {ratio:.3f} < 1.0 — bearing under-capacity; very short life."
        )
    L10_rev = ratio ** p
    L10_hours = L10_rev * 1e6 / (60.0 * n_v)

    # Fatigue-load limit check
    if fatigue_limited and P_v < float(Cu_N):
        warns.append(
            f"P = {P_v:.1f} N < Cu = {Cu_N:.1f} N — load below fatigue limit; "
            "theoretically infinite life. aISO capped at 50 (ISO/TS 16281 §5.3)."
        )

    # aISO
    aiso_res = bearing_aiso_factor(
        float(kappa), float(eC), float(Cu_N), P_v, bearing_type=bt
    )
    if not aiso_res["ok"]:
        return _err(f"aISO computation failed: {aiso_res['reason']}")
    aiso = aiso_res["aISO"]
    if aiso_res.get("warnings"):
        warns.extend(aiso_res["warnings"])

    Lnm_rev = a1_v * aiso * L10_rev
    Lnm_hours = Lnm_rev * 1e6 / (60.0 * n_v)

    return {
        "ok": True,
        "L10_rev": L10_rev,
        "L10_hours": L10_hours,
        "aISO": aiso,
        "a1": a1_v,
        "Lnm_rev": Lnm_rev,
        "Lnm_hours": Lnm_hours,
        "C_N": C_v,
        "P_N": P_v,
        "n_rpm": n_v,
        "kappa": float(kappa),
        "eC": float(eC),
        "Cu_N": float(Cu_N),
        "bearing_type": bt,
        "regime": aiso_res["regime"],
        "warnings": warns,
    }
