"""
kerf_cad_core.windload.asce7 — ASCE 7-22 wind loading calculations.

Implements the following public functions (all pure Python, no OCC):

  velocity_pressure_exposure_Kz(z, exposure)
      Velocity pressure exposure coefficient per ASCE 7-22 Table 26.10-1.
      Exposure categories B, C, D using power-law profile.

  topographic_factor_Kzt(K1, K2, K3)
      Topographic factor per ASCE 7-22 Eq. 26.8-1.

  ground_elevation_factor_Ke(z_e_m)
      Ground elevation factor per ASCE 7-22 Eq. 26.9-1 (SI).

  velocity_pressure_qz(Kz, Kzt, Kd, Ke, V, *, unit_system)
      Design velocity pressure.
      SI:  qz = 0.613 · Kz · Kzt · Kd · Ke · V²  (Pa, V in m/s)
      US:  qz = 0.00256 · Kz · Kzt · Kd · Ke · V²  (psf, V in mph)

  gust_effect_factor_G(exposure, *, Iz, Lz, Q_ratio, flexible)
      Gust-effect factor G for rigid structures (ASCE 7-22 §26.11.4).

  gust_effect_factor_Gf(n1, zbar, Iz, Lz, V, *, B, H, D, damping_ratio)
      Gust-effect factor Gf for flexible / dynamically sensitive structures
      (ASCE 7-22 §26.11.5, natural frequency n1 < 1 Hz or H > 60 m).

  mwfrs_wall_pressure(qz, qi, G, Cp_windward, Cp_leeward, Cp_side,
                       GCpi, *, surface)
      MWFRS external wall pressures p = q·G·Cp − qi·GCpi
      (ASCE 7-22 §27.3.1).

  mwfrs_roof_pressure(qh, qi, G, Cp_roof, GCpi)
      MWFRS roof pressures (ASCE 7-22 §27.3.1).

  components_cladding_GCp(zone, component_type, effective_area_m2,
                            *, unit_system)
      Components & cladding GCp coefficients by zone and effective area
      (ASCE 7-22 Fig. 30.3-1 / 30.3-2 simplified look-up).

  base_shear_overturning(pressures_by_height, tributary_widths, heights)
      Simplified base shear and overturning moment from MWFRS pressures.

  along_wind_drift(H, V, exposure, *, drift_limit_ratio)
      Simplified along-wind drift check (H/drift_limit_ratio).

All functions return plain dicts:
    success → {"ok": True, ...computed fields...}
    failure → {"ok": False, "reason": "<human-readable>"}
Functions NEVER raise.

Flexible-structure conditions and high-drift results are flagged via the
"warnings" list in the returned dict; they do not raise exceptions.

Units
-----
SI (default where applicable):
  lengths      — metres (m)
  velocity     — m/s  (SI) or mph (US)
  pressure     — Pa   (SI) or psf (US)

References
----------
ASCE/SEI 7-22, Chapters 26–27, 30.
ASCE 7-22 Commentary C26, C27.

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings as _warnings_module
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_EXPOSURE_PARAMS: dict[str, dict] = {
    "B": {
        "alpha": 7.0,
        "zg_m": 365.76,  # 1200 ft
        "z_min_m": 9.14,  # 30 ft
        "alpha_bar": 1.0 / 4.0,
        "b_bar": 0.45,
        "c": 0.30,
        "l_bar_m": 97.54,  # 320 ft
        "epsilon_bar": 1.0 / 3.0,
    },
    "C": {
        "alpha": 9.5,
        "zg_m": 274.32,  # 900 ft
        "z_min_m": 4.57,  # 15 ft
        "alpha_bar": 1.0 / 6.5,
        "b_bar": 0.65,
        "c": 0.20,
        "l_bar_m": 152.4,  # 500 ft
        "epsilon_bar": 1.0 / 5.0,
    },
    "D": {
        "alpha": 11.5,
        "zg_m": 213.36,  # 700 ft
        "z_min_m": 2.1336,  # 7 ft (ASCE 7-16/22 Table 26.11-1 — NOT 15 ft)
        "alpha_bar": 1.0 / 9.0,
        "b_bar": 0.80,
        "c": 0.15,
        "l_bar_m": 198.12,  # 650 ft
        "epsilon_bar": 1.0 / 8.0,
    },
}


# ---------------------------------------------------------------------------
# 1. velocity_pressure_exposure_Kz
# ---------------------------------------------------------------------------

def velocity_pressure_exposure_Kz(
    z: float,
    exposure: str,
) -> dict:
    """
    Velocity pressure exposure coefficient Kz per ASCE 7-22 Table 26.10-1.

    Uses the power-law profile:
        Kz = 2.01 × (z / zg)^(2/alpha)   for z >= z_min
        Kz = 2.01 × (z_min / zg)^(2/alpha)  for z < z_min

    Parameters
    ----------
    z : float
        Height above ground (m). Must be > 0.
    exposure : str
        Exposure category: 'B', 'C', or 'D'.

    Returns
    -------
    dict
        ok            : True
        Kz            : velocity pressure exposure coefficient (dimensionless)
        z_used_m      : effective height used (>= z_min)
        z_min_m       : minimum height for this exposure
        exposure      : exposure category
        alpha         : power-law exponent used
        zg_m          : gradient height (m)

    Unit system: SI (heights in metres).

    References
    ----------
    ASCE 7-22 §26.10.1, Table 26.10-1.
    """
    err = _guard_positive("z", z)
    if err:
        return _err(err)

    exp = str(exposure).strip().upper()
    if exp not in _EXPOSURE_PARAMS:
        return _err(
            f"exposure must be 'B', 'C', or 'D'; got {exposure!r}."
        )

    p = _EXPOSURE_PARAMS[exp]
    alpha = p["alpha"]
    zg = p["zg_m"]
    z_min = p["z_min_m"]

    z_eff = max(float(z), z_min)
    Kz = 2.01 * (z_eff / zg) ** (2.0 / alpha)

    return {
        "ok": True,
        "Kz": Kz,
        "z_used_m": z_eff,
        "z_min_m": z_min,
        "exposure": exp,
        "alpha": alpha,
        "zg_m": zg,
    }


# ---------------------------------------------------------------------------
# 2. topographic_factor_Kzt
# ---------------------------------------------------------------------------

def topographic_factor_Kzt(
    K1: float,
    K2: float,
    K3: float,
) -> dict:
    """
    Topographic factor Kzt per ASCE 7-22 Eq. 26.8-1.

    Kzt = (1 + K1 · K2 · K3)²

    K1, K2, K3 are site-specific multipliers from ASCE 7-22 Figs. 26.8-1A/B/C.
    For flat terrain (no topographic feature), K1 = K2 = K3 = 0 → Kzt = 1.0.

    Parameters
    ----------
    K1 : float
        Speed-up factor (from ASCE 7-22 Fig. 26.8-1A). Must be >= 0.
    K2 : float
        Distance from crest factor (from Fig. 26.8-1B). Must be >= 0.
    K3 : float
        Height factor (from Fig. 26.8-1C). Must be >= 0.

    Returns
    -------
    dict
        ok  : True
        Kzt : topographic factor (>= 1.0)
        K1  : K1 used
        K2  : K2 used
        K3  : K3 used

    Unit system: dimensionless.

    References
    ----------
    ASCE 7-22 §26.8.2, Eq. 26.8-1.
    """
    for name, val in (("K1", K1), ("K2", K2), ("K3", K3)):
        err = _guard_nonneg(name, val)
        if err:
            return _err(err)

    Kzt = (1.0 + float(K1) * float(K2) * float(K3)) ** 2

    return {
        "ok": True,
        "Kzt": Kzt,
        "K1": float(K1),
        "K2": float(K2),
        "K3": float(K3),
    }


# ---------------------------------------------------------------------------
# 3. ground_elevation_factor_Ke
# ---------------------------------------------------------------------------

def ground_elevation_factor_Ke(
    z_e_m: float,
) -> dict:
    """
    Ground elevation factor Ke per ASCE 7-22 Eq. 26.9-1.

    Ke = e^(-0.000119 × z_e)

    where z_e is the ground elevation above sea level in metres.
    At sea level (z_e = 0), Ke = 1.0.

    Parameters
    ----------
    z_e_m : float
        Site ground elevation above sea level (m). Must be >= 0.

    Returns
    -------
    dict
        ok     : True
        Ke     : ground elevation factor (dimensionless, <= 1.0)
        z_e_m  : ground elevation used (m)

    Unit system: SI (elevation in metres).

    Notes
    -----
    ASCE 7-22 Eq. 26.9-1 is presented in US customary units originally:
        Ke = e^(-0.0000362 × z_e_ft)
    The SI equivalent with z_e in metres is:
        Ke = e^(-0.000119 × z_e_m)
    (1 ft = 0.3048 m → 0.0000362 / 0.3048 ≈ 0.000119)

    References
    ----------
    ASCE 7-22 §26.9, Eq. 26.9-1; Table 26.9-1.
    """
    err = _guard_nonneg("z_e_m", z_e_m)
    if err:
        return _err(err)

    Ke = math.exp(-0.000119 * float(z_e_m))

    return {
        "ok": True,
        "Ke": Ke,
        "z_e_m": float(z_e_m),
    }


# ---------------------------------------------------------------------------
# 4. velocity_pressure_qz
# ---------------------------------------------------------------------------

_UNIT_SYSTEMS = ("SI", "US")


def velocity_pressure_qz(
    Kz: float,
    Kzt: float,
    Kd: float,
    Ke: float,
    V: float,
    *,
    unit_system: str = "SI",
) -> dict:
    """
    Design velocity pressure qz per ASCE 7-22 Eq. 26.10-1.

    SI:  qz = 0.613 · Kz · Kzt · Kd · Ke · V²   (Pa, V in m/s)
    US:  qz = 0.00256 · Kz · Kzt · Kd · Ke · V²  (psf, V in mph)

    Parameters
    ----------
    Kz : float
        Velocity pressure exposure coefficient (dimensionless). Must be > 0.
    Kzt : float
        Topographic factor (dimensionless, >= 1.0). Must be >= 1.0.
    Kd : float
        Wind directionality factor (dimensionless, 0.85–0.95 typical).
        Must be in range (0, 1].
    Ke : float
        Ground elevation factor (dimensionless, <= 1.0). Must be in (0, 1].
    V : float
        Basic wind speed (m/s for SI; mph for US). Must be > 0.
    unit_system : str
        'SI' (default) or 'US'.

    Returns
    -------
    dict
        ok          : True
        qz          : design velocity pressure (Pa for SI; psf for US)
        unit_system : 'SI' or 'US'
        Kz          : Kz used
        Kzt         : Kzt used
        Kd          : Kd used
        Ke          : Ke used
        V           : basic wind speed used

    References
    ----------
    ASCE 7-22 §26.10.2, Eq. 26.10-1.
    """
    for name, val in (("Kz", Kz), ("V", V)):
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    if float(Kzt) < 1.0:
        return _err(f"Kzt must be >= 1.0 (flat terrain gives Kzt=1.0); got {Kzt}.")
    if not (0 < float(Kd) <= 1.0):
        return _err(f"Kd must be in (0, 1]; got {Kd}.")
    if not (0 < float(Ke) <= 1.0):
        return _err(f"Ke must be in (0, 1]; got {Ke}.")

    us = str(unit_system).strip().upper()
    if us not in _UNIT_SYSTEMS:
        return _err(f"unit_system must be 'SI' or 'US'; got {unit_system!r}.")

    Kz_f = float(Kz)
    Kzt_f = float(Kzt)
    Kd_f = float(Kd)
    Ke_f = float(Ke)
    V_f = float(V)

    if us == "SI":
        # ASCE 7-22 Eq. 26.10-1 (SI): qz = 0.613 Kz Kzt Kd Ke V²
        qz = 0.613 * Kz_f * Kzt_f * Kd_f * Ke_f * V_f ** 2
    else:
        # ASCE 7-22 Eq. 26.10-1 (US): qz = 0.00256 Kz Kzt Kd Ke V²
        qz = 0.00256 * Kz_f * Kzt_f * Kd_f * Ke_f * V_f ** 2

    return {
        "ok": True,
        "qz": qz,
        "unit_system": us,
        "Kz": Kz_f,
        "Kzt": Kzt_f,
        "Kd": Kd_f,
        "Ke": Ke_f,
        "V": V_f,
    }


# ---------------------------------------------------------------------------
# 5. gust_effect_factor_G (rigid structures)
# ---------------------------------------------------------------------------

def gust_effect_factor_G(
    exposure: str,
    *,
    Iz: float | None = None,
    Lz: float | None = None,
    Q_ratio: float | None = None,
    flexible: bool = False,
) -> dict:
    """
    Gust-effect factor G for rigid structures per ASCE 7-22 §26.11.4.

    For rigid structures (n1 >= 1 Hz), G may be taken as 0.85 (simplified)
    or computed per the detailed formula.

    Simplified: G = 0.85 (ASCE 7-22 §26.11.4 simplified approach).

    Detailed formula (if Iz, Lz, Q_ratio provided):
        Q = 1 / sqrt(1 + 0.63 × ((B + H) / Lz)^0.63)
        gQ = gv = 3.4
        G = 0.925 × (1 + 1.7 × Iz × gQ × Q) / (1 + 1.7 × gv × Iz)

    Parameters
    ----------
    exposure : str
        Exposure category 'B', 'C', or 'D' (for validation only in simplified).
    Iz : float, optional
        Intensity of turbulence at mean roof height z_bar
        (ASCE 7-22 Eq. 26.11-5). If omitted, simplified G=0.85 is returned.
    Lz : float, optional
        Integral length scale of turbulence (m) at z_bar
        (ASCE 7-22 Eq. 26.11-7). Required if Iz is provided.
    Q_ratio : float, optional
        (B + H) / Lz ratio used in Q formula. Required if Iz is provided.
        B = building width (m), H = mean roof height (m).
    flexible : bool
        If True, a warning is issued that Gf (not G) should be used.
        G = 0.85 is still returned as a conservative fallback.

    Returns
    -------
    dict
        ok        : True
        G         : gust-effect factor
        method    : 'simplified' or 'detailed'
        exposure  : exposure category
        warnings  : list of warning strings

    References
    ----------
    ASCE 7-22 §26.11.4, Eqs. 26.11-4 through 26.11-8.
    """
    exp = str(exposure).strip().upper()
    if exp not in _EXPOSURE_PARAMS:
        return _err(f"exposure must be 'B', 'C', or 'D'; got {exposure!r}.")

    warns: list[str] = []

    if flexible:
        warns.append(
            "Structure may be flexible (n1 < 1 Hz or H > 60 m). "
            "Use gust_effect_factor_Gf for flexible structures per ASCE 7-22 §26.11.5."
        )

    if Iz is None:
        # Simplified approach: G = 0.85
        return {
            "ok": True,
            "G": 0.85,
            "method": "simplified",
            "exposure": exp,
            "warnings": warns,
        }

    # Detailed approach
    if Lz is None:
        return _err("Lz is required when Iz is provided (detailed G computation).")
    if Q_ratio is None:
        return _err(
            "Q_ratio = (B + H) / Lz is required when Iz is provided (detailed G computation)."
        )

    err = _guard_positive("Iz", Iz)
    if err:
        return _err(err)
    err = _guard_positive("Lz", Lz)
    if err:
        return _err(err)
    err = _guard_positive("Q_ratio", Q_ratio)
    if err:
        return _err(err)

    Iz_f = float(Iz)
    Q_r = float(Q_ratio)

    # Background response factor Q (ASCE 7-22 Eq. 26.11-6)
    Q = 1.0 / math.sqrt(1.0 + 0.63 * Q_r ** 0.63)

    # Peak factors
    gQ = 3.4
    gv = 3.4

    # Detailed G (ASCE 7-22 Eq. 26.11-4)
    G = 0.925 * (1.0 + 1.7 * Iz_f * gQ * Q) / (1.0 + 1.7 * gv * Iz_f)

    return {
        "ok": True,
        "G": G,
        "Q": Q,
        "Iz": Iz_f,
        "Lz": float(Lz),
        "Q_ratio": Q_r,
        "gQ": gQ,
        "gv": gv,
        "method": "detailed",
        "exposure": exp,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 6. gust_effect_factor_Gf (flexible structures)
# ---------------------------------------------------------------------------

def gust_effect_factor_Gf(
    n1: float,
    zbar: float,
    Iz: float,
    Lz: float,
    V: float,
    *,
    B: float,
    H: float,
    D: float,
    damping_ratio: float = 0.02,
) -> dict:
    """
    Gust-effect factor Gf for flexible or dynamically sensitive structures
    per ASCE 7-22 §26.11.5.

    Applicable when n1 < 1 Hz (natural frequency) or H > 60 m.

    Formula (ASCE 7-22 Eq. 26.11-10):
        Gf = 0.925 × (1 + 1.7 × Iz × sqrt(gQ²Q² + gR²R²))
                   / (1 + 1.7 × gv × Iz)

    where:
        gR = sqrt(2 × ln(3600 × n1)) + 0.5772 / sqrt(2 × ln(3600 × n1))
        R² = (1/β) × Rn × RH × RB × (0.53 + 0.47 × RD)   resonance factor
        Rn = 7.47 × N1 / (1 + 10.3 × N1)^(5/3),  N1 = n1 × Lz / V_zbar
        RH, RB, RD per ASCE 7-22 Eq. 26.11-15a/b

    Parameters
    ----------
    n1 : float
        Fundamental natural frequency of the structure (Hz). Must be > 0.
    zbar : float
        Equivalent height (m), typically 0.6H but >= z_min. Must be > 0.
    Iz : float
        Intensity of turbulence at zbar (dimensionless). Must be > 0.
    Lz : float
        Integral length scale of turbulence at zbar (m). Must be > 0.
    V : float
        Mean wind speed at zbar (m/s). Must be > 0.
    B : float
        Building width (m) perpendicular to wind. Must be > 0.
    H : float
        Mean roof height (m). Must be > 0.
    D : float
        Building depth (m) along wind direction. Must be > 0.
    damping_ratio : float
        Structural damping ratio β (fraction, not percent). Default 0.02 (2%).
        Must be in (0, 1).

    Returns
    -------
    dict
        ok            : True
        Gf            : gust-effect factor for flexible structure
        gQ            : peak factor for background response
        gR            : peak factor for resonant response
        gv            : peak factor for wind speed (3.4)
        Q             : background response factor
        R_squared     : resonance response factor R²
        Rn            : spectral density factor
        RH            : reduction factor for height
        RB            : reduction factor for width
        RD            : reduction factor for depth
        n1_Hz         : natural frequency used (Hz)
        zbar_m        : equivalent height used (m)
        warnings      : list of warning strings

    References
    ----------
    ASCE 7-22 §26.11.5, Eqs. 26.11-10 through 26.11-15.
    """
    warns: list[str] = []

    for name, val in (
        ("n1", n1), ("zbar", zbar), ("Iz", Iz), ("Lz", Lz), ("V", V),
        ("B", B), ("H", H), ("D", D),
    ):
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    if not (0 < float(damping_ratio) < 1.0):
        return _err(f"damping_ratio must be in (0, 1); got {damping_ratio}.")

    if float(n1) >= 1.0:
        warns.append(
            f"n1 = {n1} Hz >= 1 Hz: structure may be rigid; consider G (not Gf)."
        )
    if float(H) <= 60.0:
        warns.append(
            f"H = {H} m <= 60 m: flexible Gf formula still valid but G=0.85 "
            "may be used for rigid structures below 60 m."
        )

    n1_f = float(n1)
    Iz_f = float(Iz)
    Lz_f = float(Lz)
    V_f = float(V)
    B_f = float(B)
    H_f = float(H)
    D_f = float(D)
    beta = float(damping_ratio)

    # Background response Q
    BpH_over_Lz = (B_f + H_f) / Lz_f
    Q = 1.0 / math.sqrt(1.0 + 0.63 * BpH_over_Lz ** 0.63)

    # Reduced frequency N1 = n1 × Lz / V
    N1 = n1_f * Lz_f / V_f

    # Spectral density Rn (ASCE 7-22 Eq. 26.11-12)
    Rn = 7.47 * N1 / (1.0 + 10.3 * N1) ** (5.0 / 3.0)

    # Reduction functions (ASCE 7-22 Eq. 26.11-15a/b)
    def _R_eta(eta: float) -> float:
        if eta < 1e-9:
            return 1.0
        return (1.0 / eta) - (1.0 / (2.0 * eta ** 2)) * (1.0 - math.exp(-2.0 * eta))

    eta_H = 4.6 * n1_f * H_f / V_f
    eta_B = 4.6 * n1_f * B_f / V_f
    eta_D = 15.4 * n1_f * D_f / V_f

    RH = _R_eta(eta_H)
    RB = _R_eta(eta_B)
    RD = _R_eta(eta_D)

    # Resonance factor R² (ASCE 7-22 Eq. 26.11-11)
    R_sq = (1.0 / beta) * Rn * RH * RB * (0.53 + 0.47 * RD)

    # Peak factors
    gQ = 3.4
    gv = 3.4
    T = 3600.0  # integration period (s)
    nu = n1_f  # expected frequency of peak
    ln_nu_T = math.log(nu * T)
    if ln_nu_T <= 0:
        gR = 3.4
    else:
        sqrt_2_ln = math.sqrt(2.0 * ln_nu_T)
        gR = sqrt_2_ln + 0.5772 / sqrt_2_ln

    # Gf (ASCE 7-22 Eq. 26.11-10)
    numerator = 1.0 + 1.7 * Iz_f * math.sqrt(gQ ** 2 * Q ** 2 + gR ** 2 * R_sq)
    denominator = 1.0 + 1.7 * gv * Iz_f
    Gf = 0.925 * numerator / denominator

    return {
        "ok": True,
        "Gf": Gf,
        "gQ": gQ,
        "gR": gR,
        "gv": gv,
        "Q": Q,
        "R_squared": R_sq,
        "Rn": Rn,
        "RH": RH,
        "RB": RB,
        "RD": RD,
        "N1": N1,
        "n1_Hz": n1_f,
        "zbar_m": float(zbar),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 7. mwfrs_wall_pressure
# ---------------------------------------------------------------------------

_WALL_SURFACES = ("windward", "leeward", "side")

# ASCE 7-22 Table 27.3-1: External pressure coefficients Cp for walls
# For windward: Cp = 0.8 (constant regardless of h/L)
# For leeward: depends on L/B ratio; side walls: -0.7
_CP_WINDWARD = 0.8
_CP_SIDE = -0.7

# Default internal pressure coefficients GCpi (ASCE 7-22 Table 26.13-1)
# Enclosed: ±0.18; Partially enclosed: ±0.55; Open: 0.0
_GCPI_TABLE = {
    "enclosed": 0.18,
    "partially_enclosed": 0.55,
    "open": 0.0,
}


def mwfrs_wall_pressure(
    qz: float,
    qi: float,
    G: float,
    Cp_windward: float,
    Cp_leeward: float,
    Cp_side: float,
    GCpi: float,
    *,
    surface: str = "windward",
) -> dict:
    """
    MWFRS external wall pressures per ASCE 7-22 §27.3.1.

    p = q · G · Cp − qi · (±GCpi)

    The governing (maximum magnitude) pressure is returned for each surface.
    Both +GCpi and -GCpi cases are evaluated; the critical case is selected.

    Parameters
    ----------
    qz : float
        Velocity pressure at height z (Pa or psf). Use qz for windward;
        use qh (at mean roof height) for leeward and side. Must be > 0.
    qi : float
        Internal pressure velocity pressure reference (Pa or psf).
        Typically qh for enclosed/partially enclosed. Must be > 0.
    G : float
        Gust-effect factor (dimensionless). Must be > 0.
    Cp_windward : float
        External pressure coefficient windward wall (+0.8 typical).
    Cp_leeward : float
        External pressure coefficient leeward wall (negative, -0.2 to -0.5).
    Cp_side : float
        External pressure coefficient side walls (-0.7 typical).
    GCpi : float
        Internal pressure coefficient (from ASCE 7-22 Table 26.13-1).
        Pass the magnitude; ± cases are applied internally. Must be >= 0.
    surface : str
        'windward', 'leeward', or 'side'. Selects which Cp is used.

    Returns
    -------
    dict
        ok         : True
        p_pos      : pressure with +GCpi internal (Pa or psf)
        p_neg      : pressure with -GCpi internal (Pa or psf)
        p_critical : governing pressure (maximum absolute value) (Pa or psf)
        surface    : surface selected
        qz         : velocity pressure used
        qi         : internal pressure reference used
        G          : gust-effect factor used
        Cp         : Cp for selected surface
        GCpi       : GCpi used

    References
    ----------
    ASCE 7-22 §27.3.1, Eq. 27.3-1; Table 27.3-1.
    """
    for name, val in (("qz", qz), ("qi", qi), ("G", G)):
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    e = _guard_nonneg("GCpi", GCpi)
    if e:
        return _err(e)

    surf = str(surface).strip().lower()
    if surf not in _WALL_SURFACES:
        return _err(
            f"surface must be one of {_WALL_SURFACES}; got {surface!r}."
        )

    cp_map = {
        "windward": float(Cp_windward),
        "leeward": float(Cp_leeward),
        "side": float(Cp_side),
    }
    Cp = cp_map[surf]
    qz_f = float(qz)
    qi_f = float(qi)
    G_f = float(G)
    gcpi = float(GCpi)

    # p = q·G·Cp − qi·(±GCpi)
    p_pos = qz_f * G_f * Cp - qi_f * gcpi   # positive internal (suction on wall)
    p_neg = qz_f * G_f * Cp + qi_f * gcpi   # negative internal (pressure on wall)

    p_critical = p_pos if abs(p_pos) >= abs(p_neg) else p_neg

    return {
        "ok": True,
        "p_pos": p_pos,
        "p_neg": p_neg,
        "p_critical": p_critical,
        "surface": surf,
        "qz": qz_f,
        "qi": qi_f,
        "G": G_f,
        "Cp": Cp,
        "Cp_windward": float(Cp_windward),
        "Cp_leeward": float(Cp_leeward),
        "Cp_side": float(Cp_side),
        "GCpi": gcpi,
    }


# ---------------------------------------------------------------------------
# 8. mwfrs_roof_pressure
# ---------------------------------------------------------------------------

def mwfrs_roof_pressure(
    qh: float,
    qi: float,
    G: float,
    Cp_roof: float,
    GCpi: float,
) -> dict:
    """
    MWFRS roof pressures per ASCE 7-22 §27.3.1.

    p = qh · G · Cp − qi · (±GCpi)

    Both ±GCpi cases are evaluated; the critical (maximum absolute) case
    is returned.

    Parameters
    ----------
    qh : float
        Velocity pressure at mean roof height h (Pa or psf). Must be > 0.
    qi : float
        Internal pressure velocity pressure reference (Pa or psf).
        Must be > 0.
    G : float
        Gust-effect factor (dimensionless). Must be > 0.
    Cp_roof : float
        External pressure coefficient for roof (negative for flat roofs,
        varies by roof slope and h/L per ASCE 7-22 Table 27.3-1).
    GCpi : float
        Internal pressure coefficient magnitude (Table 26.13-1). Must be >= 0.

    Returns
    -------
    dict
        ok         : True
        p_pos      : pressure with +GCpi internal
        p_neg      : pressure with -GCpi internal
        p_critical : governing pressure (maximum absolute value)
        qh         : mean-roof-height velocity pressure used
        qi         : internal pressure reference used
        G          : gust factor used
        Cp_roof    : roof Cp used
        GCpi       : GCpi used

    References
    ----------
    ASCE 7-22 §27.3.1, Eq. 27.3-1; Table 27.3-1 (roof Cp).
    """
    for name, val in (("qh", qh), ("qi", qi), ("G", G)):
        e = _guard_positive(name, val)
        if e:
            return _err(e)

    e = _guard_nonneg("GCpi", GCpi)
    if e:
        return _err(e)

    qh_f = float(qh)
    qi_f = float(qi)
    G_f = float(G)
    Cp_r = float(Cp_roof)
    gcpi = float(GCpi)

    p_pos = qh_f * G_f * Cp_r - qi_f * gcpi
    p_neg = qh_f * G_f * Cp_r + qi_f * gcpi

    p_critical = p_pos if abs(p_pos) >= abs(p_neg) else p_neg

    return {
        "ok": True,
        "p_pos": p_pos,
        "p_neg": p_neg,
        "p_critical": p_critical,
        "qh": qh_f,
        "qi": qi_f,
        "G": G_f,
        "Cp_roof": Cp_r,
        "GCpi": gcpi,
    }


# ---------------------------------------------------------------------------
# 9. components_cladding_GCp
# ---------------------------------------------------------------------------

# Simplified GCp tables — ASCE 7-22 Fig. 30.3-1/2 (low-rise buildings, h <= 18 m)
# zone: 1=field, 2=edge, 3=corner
# component_type: 'wall' or 'roof'
# Returns (GCp_pos, GCp_neg) bounds for the given zone and effective area
# This is a simplified lookup; full implementation requires interpolation
# on semi-log plots. Here we use the tabulated extremes from the figures.

# Format: (zone, component_type) -> [(area_upper_m2, GCp_pos, GCp_neg), ...]
# Last entry applies for areas > last threshold.
_CC_GCP_TABLE: dict[tuple[int, str], list[tuple[float, float, float]]] = {
    # Wall zones (Fig. 30.3-1, low-rise)
    (1, "wall"): [(0.93, 1.0, -1.1), (9.3, 0.8, -0.8), (46.5, 0.7, -0.7)],
    (2, "wall"): [(0.93, 1.1, -1.4), (9.3, 0.9, -1.1), (46.5, 0.7, -0.7)],
    (3, "wall"): [(0.93, 1.1, -1.4), (9.3, 0.9, -1.1), (46.5, 0.7, -0.7)],
    # Roof zones (Fig. 30.3-2, flat to low-slope roof h/L <= 0.5)
    (1, "roof"): [(0.93, 0.3, -1.0), (9.3, 0.2, -0.9), (46.5, 0.2, -0.8)],
    (2, "roof"): [(0.93, 0.3, -1.8), (9.3, 0.2, -1.4), (46.5, 0.2, -1.0)],
    (3, "roof"): [(0.93, 0.3, -2.8), (9.3, 0.2, -2.2), (46.5, 0.2, -1.0)],
}


def components_cladding_GCp(
    zone: int,
    component_type: str,
    effective_area_m2: float,
    *,
    unit_system: str = "SI",
) -> dict:
    """
    Components & cladding GCp coefficients by zone and effective area
    per ASCE 7-22 Fig. 30.3-1 / 30.3-2.

    Applies to low-rise buildings (h <= 18 m / 60 ft).
    Zone 1 = field, Zone 2 = edge, Zone 3 = corner.

    Parameters
    ----------
    zone : int
        Zone number: 1 (field), 2 (edge), or 3 (corner).
    component_type : str
        'wall' or 'roof'.
    effective_area_m2 : float
        Effective wind area of the component (m²). Must be > 0.
    unit_system : str
        'SI' (default) or 'US'. Affects only the note in the output; GCp
        is dimensionless.

    Returns
    -------
    dict
        ok               : True
        GCp_pos          : positive (inward) GCp coefficient
        GCp_neg          : negative (outward/suction) GCp coefficient
        zone             : zone number
        component_type   : 'wall' or 'roof'
        effective_area_m2: effective area used
        note             : applicable standard note

    References
    ----------
    ASCE 7-22 §30.3, Figs. 30.3-1, 30.3-2.
    """
    e = _guard_positive("effective_area_m2", effective_area_m2)
    if e:
        return _err(e)

    zone_i = int(zone)
    ctype = str(component_type).strip().lower()
    us = str(unit_system).strip().upper()
    if us not in _UNIT_SYSTEMS:
        return _err(f"unit_system must be 'SI' or 'US'; got {unit_system!r}.")

    key = (zone_i, ctype)
    if key not in _CC_GCP_TABLE:
        return _err(
            f"zone must be 1, 2, or 3; component_type must be 'wall' or 'roof'. "
            f"Got zone={zone}, component_type={component_type!r}."
        )

    table = _CC_GCP_TABLE[key]
    A = float(effective_area_m2)

    GCp_pos = table[-1][1]
    GCp_neg = table[-1][2]
    for area_thresh, gcp_p, gcp_n in table:
        if A <= area_thresh:
            GCp_pos = gcp_p
            GCp_neg = gcp_n
            break

    return {
        "ok": True,
        "GCp_pos": GCp_pos,
        "GCp_neg": GCp_neg,
        "zone": zone_i,
        "component_type": ctype,
        "effective_area_m2": A,
        "note": (
            "Simplified lookup from ASCE 7-22 Fig. 30.3-1/2 (low-rise, h <= 18 m). "
            "GCp is dimensionless. Use design pressure p = qh × (GCp - GCpi)."
        ),
    }


# ---------------------------------------------------------------------------
# 10. base_shear_overturning
# ---------------------------------------------------------------------------

def base_shear_overturning(
    pressures_by_height: list[float],
    tributary_widths: list[float],
    heights: list[float],
) -> dict:
    """
    Base shear V and overturning moment M_OT from MWFRS pressures.

    Simplified along-wind base shear and overturning moment by summing
    pressure resultants over building height increments.

    Parameters
    ----------
    pressures_by_height : list[float]
        List of design pressures at each level (Pa or psf). Length >= 1.
    tributary_widths : list[float]
        List of tributary widths (m or ft) at each level. Same length.
        Must all be > 0.
    heights : list[float]
        List of height increments dz (m or ft) at each level. Same length.
        Must all be > 0.

    Returns
    -------
    dict
        ok                 : True
        base_shear         : total base shear V (N or lb, depending on input units)
        overturning_moment : total overturning moment M_OT (N·m or ft·lb)
        n_levels           : number of levels summed
        forces             : list of force at each level (N or lb)
        moment_arms        : list of cumulative height to mid of each strip (m or ft)

    Notes
    -----
    The height used for each strip moment arm is the distance from the base
    to the centroid of each pressure strip (lower bound + dz/2).
    The first level's lower bound is assumed to be 0.

    References
    ----------
    ASCE 7-22 §27.4 (simplified method), general structural mechanics.
    """
    n = len(pressures_by_height)
    if n == 0:
        return _err("pressures_by_height must have at least one entry.")
    if len(tributary_widths) != n:
        return _err(
            f"tributary_widths length ({len(tributary_widths)}) must match "
            f"pressures_by_height length ({n})."
        )
    if len(heights) != n:
        return _err(
            f"heights length ({len(heights)}) must match "
            f"pressures_by_height length ({n})."
        )

    for i, (w, h) in enumerate(zip(tributary_widths, heights)):
        e = _guard_positive(f"tributary_widths[{i}]", w)
        if e:
            return _err(e)
        e = _guard_positive(f"heights[{i}]", h)
        if e:
            return _err(e)

    forces: list[float] = []
    moment_arms: list[float] = []
    z_base = 0.0

    for p, w, dz in zip(pressures_by_height, tributary_widths, heights):
        F = float(p) * float(w) * float(dz)
        z_centroid = z_base + float(dz) / 2.0
        forces.append(F)
        moment_arms.append(z_centroid)
        z_base += float(dz)

    base_shear = sum(forces)
    overturning_moment = sum(F * arm for F, arm in zip(forces, moment_arms))

    return {
        "ok": True,
        "base_shear": base_shear,
        "overturning_moment": overturning_moment,
        "n_levels": n,
        "forces": forces,
        "moment_arms": moment_arms,
    }


# ---------------------------------------------------------------------------
# 11. along_wind_drift
# ---------------------------------------------------------------------------

def along_wind_drift(
    H: float,
    V: float,
    exposure: str,
    *,
    drift_limit_ratio: float = 500.0,
) -> dict:
    """
    Simplified along-wind drift check.

    Estimates the along-wind drift index as H / drift_limit_ratio and flags
    structures requiring detailed dynamic analysis.

    This is a simplified serviceability check. For detailed drift calculations,
    use the full along-wind displacement formula with Gf and modal analysis.

    Parameters
    ----------
    H : float
        Building total height (m). Must be > 0.
    V : float
        Basic wind speed (m/s). Must be > 0.
    exposure : str
        Exposure category 'B', 'C', or 'D'.
    drift_limit_ratio : float
        Allowable drift ratio H/drift (default 500, i.e. H/500 limit).
        Must be > 0.

    Returns
    -------
    dict
        ok                  : True
        allowable_drift_m   : H / drift_limit_ratio (m)
        drift_limit_ratio   : drift limit used
        H_m                 : building height (m)
        V_mps               : basic wind speed (m/s)
        exposure            : exposure category
        flexible_flag       : True if H > 60 m or estimated n1 < 1 Hz
        warnings            : list of warning strings

    Notes
    -----
    Flexible-structure flag is set when H > 60 m, per ASCE 7-22 §26.2
    definition of "flexible structure" (fn < 1 Hz).
    Approximate n1 from empirical formula: n1 ≈ 75 / H (for steel frame,
    ASCE 7-22 Commentary C26.11.2).

    References
    ----------
    ASCE 7-22 §26.2 (flexible structure definition), §26.11.5, Commentary C26.11.
    """
    e = _guard_positive("H", H)
    if e:
        return _err(e)
    e = _guard_positive("V", V)
    if e:
        return _err(e)
    e = _guard_positive("drift_limit_ratio", drift_limit_ratio)
    if e:
        return _err(e)

    exp = str(exposure).strip().upper()
    if exp not in _EXPOSURE_PARAMS:
        return _err(f"exposure must be 'B', 'C', or 'D'; got {exposure!r}.")

    H_f = float(H)
    V_f = float(V)
    dr = float(drift_limit_ratio)

    allowable_drift = H_f / dr

    warns: list[str] = []
    n1_approx = 75.0 / H_f  # empirical approximation for steel frame
    flexible = H_f > 60.0 or n1_approx < 1.0

    if flexible:
        warns.append(
            f"H = {H_f} m (approx. n1 ≈ {n1_approx:.2f} Hz): structure classified "
            "as flexible per ASCE 7-22 §26.2. Use gust_effect_factor_Gf and "
            "detailed along-wind displacement formula for accurate drift."
        )
    if allowable_drift > 0.025 * H_f:
        warns.append(
            f"Allowable drift H/{int(dr)} = {allowable_drift:.3f} m. "
            "Verify serviceability requirements with detailed analysis."
        )

    return {
        "ok": True,
        "allowable_drift_m": allowable_drift,
        "drift_limit_ratio": dr,
        "H_m": H_f,
        "V_mps": V_f,
        "exposure": exp,
        "n1_approx_Hz": n1_approx,
        "flexible_flag": flexible,
        "warnings": warns,
    }
