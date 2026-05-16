"""
kerf_cad_core.seismic.elf — ASCE 7 Equivalent Lateral Force (ELF) procedure.

Pure-Python module; no OCC dependency.  Distinct from vibration/ (mechanical
rotating machinery) and geotech/ (soil behaviour) and struct/ (member sizing).

Public functions
----------------
site_coefficients(Ss, S1, site_class)
    Fa, Fv from ASCE 7 Table 11.4-1 / 11.4-2 (interpolated).
    Returns Fa, Fv, SMS, SM1, SDS, SD1.

design_spectrum(T, SDS, SD1, *, TL=6.0)
    Design response spectral acceleration Sa(T) per ASCE 7 §11.4.5.
    Covers T0, Ts, constant-acceleration, constant-velocity, long-period
    transition regions.

approximate_period(hn, structure_type)
    Approximate fundamental period Ta = Ct · hn^x (ASCE 7 Table 12.8-2).
    Supports: 'steel_moment', 'concrete_moment', 'eccentrically_braced',
              'other' (all other structural systems).

seismic_response_coefficient(SDS, SD1, T, R, Ie, *, TL=6.0)
    Cs per ASCE 7 §12.8.1.1 with cap (SD1/(T·R/Ie) or SD1·TL/(T²·R/Ie))
    and floor (0.044·SDS·Ie, ≥0.01; 0.5·S1/(R/Ie) when S1≥0.6g).
    Flags Cs-cap-governs in warnings.

base_shear(Cs, W)
    V = Cs · W.

vertical_distribution(V, W_stories, h_stories, T)
    Cvx and Fx per ASCE 7 §12.8.3 with k exponent (1.0 for T≤0.5s,
    2.0 for T≥2.5s, linear interpolation between).

story_shear_and_overturning(Fx, h_stories)
    Vx (storey shear) and Mx (overturning moment at each level) from Fx.

drift_and_stability(delta_xe, Cd, Ie, Px, Vx, hsx)
    Inelastic drift Δx = Cd·delta_xe/Ie, drift ratio, story drift limit check,
    and P-delta stability coefficient θ = Px·Δx/(Vx·hsx·Cd).
    Flags drift exceedance and θ > 0.10 (θ_max limit per §12.8.7).

sdof_spectral_displacement(Sa_g, T)
    Elastic spectral displacement Sd = Sa·g·T²/(4π²) in metres.

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Units
-----
Unless otherwise stated:
  lengths     — metres (m)
  mass/weight — kN (seismic weight W in kN)
  stress      — kPa (not used directly here)
  Sa, SDS, SD1, Ss, S1 — dimensionless (g)
  R, Cd, Ω0  — dimensionless seismic design coefficients
  Ie          — importance factor (dimensionless)
  T           — seconds

References
----------
ASCE/SEI 7-22 "Minimum Design Loads and Associated Criteria for
Buildings and Other Structures", Chapters 11–12.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any

__all__ = [
    "site_coefficients",
    "design_spectrum",
    "approximate_period",
    "seismic_response_coefficient",
    "base_shear",
    "vertical_distribution",
    "story_shear_and_overturning",
    "drift_and_stability",
    "sdof_spectral_displacement",
]

# ---------------------------------------------------------------------------
# Site coefficient tables (ASCE 7-22 Tables 11.4-1 and 11.4-2)
# Rows: site classes A, B, C, D, E
# Columns for Fa: Ss breakpoints 0.25, 0.50, 0.75, 1.00, 1.25, 1.50
# Columns for Fv: S1 breakpoints 0.10, 0.20, 0.30, 0.40, 0.50, 0.60
# ---------------------------------------------------------------------------

_SITE_CLASSES = ("A", "B", "C", "D", "E")

_FA_SS_BREAKPOINTS = (0.25, 0.50, 0.75, 1.00, 1.25, 1.50)
_FA_TABLE: dict[str, tuple[float, ...]] = {
    #         Ss:  0.25  0.50  0.75  1.00  1.25  1.50
    "A": (0.8,  0.8,  0.8,  0.8,  0.8,  0.8),
    "B": (0.9,  0.9,  0.9,  0.9,  0.9,  0.9),
    "C": (1.3,  1.3,  1.2,  1.2,  1.2,  1.2),
    "D": (1.6,  1.4,  1.2,  1.1,  1.0,  1.0),
    "E": (2.4,  1.7,  1.3,  (None),  (None),  (None)),  # type: ignore[misc]
}

_FV_S1_BREAKPOINTS = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60)
_FV_TABLE: dict[str, tuple[float, ...]] = {
    #         S1:  0.10  0.20  0.30  0.40  0.50  0.60
    "A": (0.8,  0.8,  0.8,  0.8,  0.8,  0.8),
    "B": (0.8,  0.8,  0.8,  0.8,  0.8,  0.8),
    "C": (1.5,  1.5,  1.5,  1.5,  1.5,  1.4),
    "D": (2.4,  2.2,  2.0,  1.9,  1.8,  1.7),
    "E": (4.2,  3.3,  2.8,  (None),  (None),  (None)),  # type: ignore[misc]
}


def _interp_table(
    val: float,
    breakpoints: tuple[float, ...],
    row: tuple[Any, ...],
) -> float | None:
    """Linear interpolation within a site-coefficient table row.
    Returns None if the val falls in a region where site class E
    requires a site-specific hazard analysis (table entry is None).
    """
    n = len(breakpoints)
    if val <= breakpoints[0]:
        v = row[0]
        return float(v) if v is not None else None
    if val >= breakpoints[-1]:
        v = row[-1]
        return float(v) if v is not None else None
    for i in range(n - 1):
        if breakpoints[i] <= val <= breakpoints[i + 1]:
            v0, v1 = row[i], row[i + 1]
            if v0 is None or v1 is None:
                return None
            t = (val - breakpoints[i]) / (breakpoints[i + 1] - breakpoints[i])
            return float(v0) + t * (float(v1) - float(v0))
    return None


# ---------------------------------------------------------------------------
# Approximate fundamental period coefficients (ASCE 7 Table 12.8-2)
# ---------------------------------------------------------------------------

_PERIOD_COEFF: dict[str, tuple[float, float]] = {
    # structure_type: (Ct, x)
    "steel_moment":           (0.0724, 0.80),
    "concrete_moment":        (0.0466, 0.90),
    "eccentrically_braced":   (0.0731, 0.75),
    "other":                  (0.0488, 0.75),
}


# ---------------------------------------------------------------------------
# site_coefficients
# ---------------------------------------------------------------------------

def site_coefficients(
    Ss: float,
    S1: float,
    site_class: str,
) -> dict[str, Any]:
    """Compute site-modified MCE spectral accelerations and design values.

    Parameters
    ----------
    Ss : float
        Mapped MCE short-period spectral acceleration (g). Must be >= 0.
    S1 : float
        Mapped MCE 1-second spectral acceleration (g). Must be >= 0.
    site_class : str
        ASCE 7 site class: 'A', 'B', 'C', 'D', or 'E'.

    Returns
    -------
    dict with keys: Fa, Fv, SMS, SM1, SDS, SD1, warnings.
    """
    warnings: list[str] = []
    sc = site_class.upper().strip()
    if sc not in _SITE_CLASSES:
        return {"ok": False, "reason": f"site_class must be one of {_SITE_CLASSES}"}
    if Ss < 0:
        return {"ok": False, "reason": "Ss must be >= 0"}
    if S1 < 0:
        return {"ok": False, "reason": "S1 must be >= 0"}

    Fa = _interp_table(Ss, _FA_SS_BREAKPOINTS, _FA_TABLE[sc])
    Fv = _interp_table(S1, _FV_S1_BREAKPOINTS, _FV_TABLE[sc])

    if Fa is None:
        return {
            "ok": False,
            "reason": (
                f"Site class E with Ss={Ss:.2f}g requires site-specific "
                "hazard analysis per ASCE 7 §11.4.8 — Fa not tabulated."
            ),
        }
    if Fv is None:
        return {
            "ok": False,
            "reason": (
                f"Site class E with S1={S1:.2f}g requires site-specific "
                "hazard analysis per ASCE 7 §11.4.8 — Fv not tabulated."
            ),
        }

    SMS = Fa * Ss
    SM1 = Fv * S1
    SDS = (2.0 / 3.0) * SMS
    SD1 = (2.0 / 3.0) * SM1

    if sc == "E" and S1 >= 0.20:
        warnings.append(
            "Site class E: S1 >= 0.2g — verify site-specific analysis not "
            "required per ASCE 7 §11.4.8."
        )
    if SDS >= 0.50:
        warnings.append(
            f"SDS={SDS:.3f}g >= 0.5g: likely Seismic Design Category D or higher "
            "— verify SDC per ASCE 7 Table 11.6-1."
        )

    return {
        "ok": True,
        "Fa": round(Fa, 4),
        "Fv": round(Fv, 4),
        "SMS": round(SMS, 4),
        "SM1": round(SM1, 4),
        "SDS": round(SDS, 4),
        "SD1": round(SD1, 4),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# design_spectrum
# ---------------------------------------------------------------------------

def design_spectrum(
    T: float,
    SDS: float,
    SD1: float,
    *,
    TL: float = 6.0,
) -> dict[str, Any]:
    """ASCE 7 design response spectral acceleration Sa(T).

    Parameters
    ----------
    T : float
        Structural period (s). Must be >= 0.
    SDS : float
        Design spectral acceleration, short period (g). > 0.
    SD1 : float
        Design spectral acceleration, 1-second period (g). > 0.
    TL : float
        Long-period transition period (s). Default 6.0 s.

    Returns
    -------
    dict with keys: T, Sa_g, region, T0, Ts, TL, warnings.
    """
    warnings: list[str] = []
    if T < 0:
        return {"ok": False, "reason": "T must be >= 0"}
    if SDS <= 0:
        return {"ok": False, "reason": "SDS must be > 0"}
    if SD1 <= 0:
        return {"ok": False, "reason": "SD1 must be > 0"}
    if TL <= 0:
        return {"ok": False, "reason": "TL must be > 0"}

    T0 = 0.2 * SD1 / SDS
    Ts = SD1 / SDS

    if T < T0:
        Sa = SDS * (0.4 + 0.6 * T / T0)
        region = "rising"
    elif T <= Ts:
        Sa = SDS
        region = "constant_acceleration"
    elif T <= TL:
        Sa = SD1 / T
        region = "constant_velocity"
    else:
        Sa = SD1 * TL / (T ** 2)
        region = "long_period"

    if T > TL:
        warnings.append(
            f"T={T:.3f}s > TL={TL:.1f}s: long-period transition region; "
            "verify TL from ASCE 7 Figure 22-14 for your region."
        )

    return {
        "ok": True,
        "T": round(T, 4),
        "Sa_g": round(Sa, 6),
        "region": region,
        "T0": round(T0, 4),
        "Ts": round(Ts, 4),
        "TL": round(TL, 2),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# approximate_period
# ---------------------------------------------------------------------------

def approximate_period(
    hn: float,
    structure_type: str = "other",
) -> dict[str, Any]:
    """Approximate fundamental period Ta = Ct · hn^x (ASCE 7 Table 12.8-2).

    Parameters
    ----------
    hn : float
        Height above base to highest level (m). Must be > 0.
    structure_type : str
        One of 'steel_moment', 'concrete_moment',
        'eccentrically_braced', 'other' (default).

    Returns
    -------
    dict with keys: Ta_s, Ct, x, hn_m, structure_type, warnings.
    """
    warnings: list[str] = []
    st = structure_type.lower().strip()
    if st not in _PERIOD_COEFF:
        return {
            "ok": False,
            "reason": (
                f"structure_type must be one of "
                f"{list(_PERIOD_COEFF.keys())}"
            ),
        }
    if hn <= 0:
        return {"ok": False, "reason": "hn must be > 0"}

    Ct, x = _PERIOD_COEFF[st]
    Ta = Ct * (hn ** x)

    if hn > 72.0:
        warnings.append(
            f"hn={hn:.1f}m > 72 m: upper bound on Ta may apply; verify "
            "ASCE 7 §12.8.2 Cu·Ta limit."
        )
    if Ta > 4.0:
        warnings.append(
            f"Ta={Ta:.3f}s > 4.0s: long-period structure — consider modal "
            "response spectrum analysis (ASCE 7 §12.9)."
        )

    return {
        "ok": True,
        "Ta_s": round(Ta, 4),
        "Ct": Ct,
        "x": x,
        "hn_m": round(hn, 3),
        "structure_type": st,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# seismic_response_coefficient
# ---------------------------------------------------------------------------

def seismic_response_coefficient(
    SDS: float,
    SD1: float,
    T: float,
    R: float,
    Ie: float,
    *,
    TL: float = 6.0,
    S1: float = 0.0,
) -> dict[str, Any]:
    """Seismic response coefficient Cs per ASCE 7 §12.8.1.1.

    Parameters
    ----------
    SDS : float
        Design spectral acceleration, short period (g). > 0.
    SD1 : float
        Design spectral acceleration, 1-second period (g). > 0.
    T : float
        Fundamental period (s). > 0.
    R : float
        Response modification coefficient (dimensionless). > 0.
    Ie : float
        Importance factor (dimensionless). > 0.
    TL : float
        Long-period transition period (s). Default 6.0 s.
    S1 : float
        Mapped MCE 1-second acceleration (g) for floor check. Default 0.

    Returns
    -------
    dict with keys: Cs, Cs_basic, Cs_cap, Cs_floor, cap_governs,
                    floor_governs, R_over_Ie, warnings.
    """
    warnings: list[str] = []
    if SDS <= 0:
        return {"ok": False, "reason": "SDS must be > 0"}
    if SD1 <= 0:
        return {"ok": False, "reason": "SD1 must be > 0"}
    if T <= 0:
        return {"ok": False, "reason": "T must be > 0"}
    if R <= 0:
        return {"ok": False, "reason": "R must be > 0"}
    if Ie <= 0:
        return {"ok": False, "reason": "Ie must be > 0"}
    if TL <= 0:
        return {"ok": False, "reason": "TL must be > 0"}

    R_over_Ie = R / Ie

    # Basic Cs (§12.8.1.1 Eq. 12.8-2)
    Cs_basic = SDS / R_over_Ie

    # Upper bound / cap
    if T <= TL:
        Cs_cap = SD1 / (T * R_over_Ie)
    else:
        Cs_cap = SD1 * TL / (T ** 2 * R_over_Ie)

    # Floor (§12.8.1.1 Eq. 12.8-5 and 12.8-6)
    Cs_floor_1 = 0.044 * SDS * Ie
    Cs_floor_1 = max(Cs_floor_1, 0.01)

    Cs_floor_2 = 0.0
    if S1 >= 0.6:
        Cs_floor_2 = 0.5 * S1 / R_over_Ie

    Cs_floor = max(Cs_floor_1, Cs_floor_2)

    # Governing Cs
    Cs = min(Cs_basic, Cs_cap)
    cap_governs = Cs < Cs_basic
    Cs = max(Cs, Cs_floor)
    floor_governs = Cs == Cs_floor and Cs_floor > min(Cs_basic, Cs_cap)

    if cap_governs:
        warnings.append(
            f"Cs cap governs: Cs={Cs:.4f}g (cap={Cs_cap:.4f}g < "
            f"basic={Cs_basic:.4f}g). Period-dependent cap controls."
        )
    if floor_governs:
        warnings.append(
            f"Cs floor governs: Cs_floor={Cs_floor:.4f}g applied."
        )

    return {
        "ok": True,
        "Cs": round(Cs, 6),
        "Cs_basic": round(Cs_basic, 6),
        "Cs_cap": round(Cs_cap, 6),
        "Cs_floor": round(Cs_floor, 6),
        "cap_governs": cap_governs,
        "floor_governs": floor_governs,
        "R_over_Ie": round(R_over_Ie, 4),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# base_shear
# ---------------------------------------------------------------------------

def base_shear(Cs: float, W: float) -> dict[str, Any]:
    """Base shear V = Cs · W (ASCE 7 §12.8.1).

    Parameters
    ----------
    Cs : float
        Seismic response coefficient (dimensionless). Must be > 0.
    W : float
        Effective seismic weight (kN). Must be > 0.

    Returns
    -------
    dict with keys: V_kN, Cs, W_kN, warnings.
    """
    if Cs <= 0:
        return {"ok": False, "reason": "Cs must be > 0"}
    if W <= 0:
        return {"ok": False, "reason": "W must be > 0"}

    V = Cs * W
    warnings: list[str] = []
    if Cs > 0.5:
        warnings.append(
            f"Cs={Cs:.4f} > 0.5: unusually high seismic response coefficient; "
            "verify inputs."
        )

    return {
        "ok": True,
        "V_kN": round(V, 3),
        "Cs": round(Cs, 6),
        "W_kN": round(W, 3),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# vertical_distribution
# ---------------------------------------------------------------------------

def vertical_distribution(
    V: float,
    W_stories: list[float],
    h_stories: list[float],
    T: float,
) -> dict[str, Any]:
    """Vertical force distribution Fx per ASCE 7 §12.8.3.

    Parameters
    ----------
    V : float
        Total base shear (kN). > 0.
    W_stories : list[float]
        Seismic weight at each storey level (kN). Bottom→top order. All > 0.
    h_stories : list[float]
        Height of each storey level above base (m). Bottom→top order.
        Must be strictly increasing and all > 0.
    T : float
        Fundamental period (s). > 0.

    Returns
    -------
    dict with keys: Fx_kN (list), Cvx (list), k, V_kN, warnings.
    """
    warnings: list[str] = []
    if V <= 0:
        return {"ok": False, "reason": "V must be > 0"}
    if T <= 0:
        return {"ok": False, "reason": "T must be > 0"}
    if len(W_stories) == 0:
        return {"ok": False, "reason": "W_stories must not be empty"}
    if len(W_stories) != len(h_stories):
        return {"ok": False, "reason": "W_stories and h_stories must be the same length"}
    if any(w <= 0 for w in W_stories):
        return {"ok": False, "reason": "All W_stories values must be > 0"}
    if any(h <= 0 for h in h_stories):
        return {"ok": False, "reason": "All h_stories values must be > 0"}
    for i in range(1, len(h_stories)):
        if h_stories[i] <= h_stories[i - 1]:
            return {
                "ok": False,
                "reason": "h_stories must be strictly increasing (bottom to top)",
            }

    # k exponent (§12.8.3)
    if T <= 0.5:
        k = 1.0
    elif T >= 2.5:
        k = 2.0
    else:
        k = 1.0 + (T - 0.5) / 2.0  # linear interpolation

    # Cvx = (wx · hx^k) / Σ(wi · hi^k)
    whk = [W_stories[i] * (h_stories[i] ** k) for i in range(len(W_stories))]
    sum_whk = sum(whk)
    if sum_whk == 0:
        return {"ok": False, "reason": "Sum of W·h^k is zero; check inputs"}

    Cvx = [v / sum_whk for v in whk]
    Fx = [round(V * c, 3) for c in Cvx]
    Cvx_rounded = [round(c, 6) for c in Cvx]

    if abs(sum(Cvx) - 1.0) > 1e-9:
        warnings.append("Cvx values do not sum to 1.0 — numerical precision issue.")

    return {
        "ok": True,
        "Fx_kN": Fx,
        "Cvx": Cvx_rounded,
        "k": round(k, 4),
        "V_kN": round(V, 3),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# story_shear_and_overturning
# ---------------------------------------------------------------------------

def story_shear_and_overturning(
    Fx: list[float],
    h_stories: list[float],
) -> dict[str, Any]:
    """Story shear Vx and overturning moment Mx at each level.

    Parameters
    ----------
    Fx : list[float]
        Lateral force at each storey (kN). Bottom→top order.
    h_stories : list[float]
        Height of each storey above base (m). Bottom→top order.

    Returns
    -------
    dict with keys: Vx_kN (list), Mx_kNm (list), warnings.
    Vx[i] = sum of Fx[i..n-1] (shear at level i).
    Mx[i] = sum of Fx[j]·(h[j]-h[i]) for j >= i.
    """
    warnings: list[str] = []
    if len(Fx) == 0:
        return {"ok": False, "reason": "Fx must not be empty"}
    if len(Fx) != len(h_stories):
        return {"ok": False, "reason": "Fx and h_stories must be the same length"}
    if any(h <= 0 for h in h_stories):
        return {"ok": False, "reason": "All h_stories values must be > 0"}

    n = len(Fx)
    Vx = []
    Mx = []

    for i in range(n):
        vx = sum(Fx[j] for j in range(i, n))
        # overturning moment about level i
        mx = sum(Fx[j] * (h_stories[j] - h_stories[i]) for j in range(i, n))
        Vx.append(round(vx, 3))
        Mx.append(round(mx, 3))

    if Vx and Vx[0] <= 0:
        warnings.append("Base shear (Vx[0]) is <= 0; check Fx inputs.")

    return {
        "ok": True,
        "Vx_kN": Vx,
        "Mx_kNm": Mx,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# drift_and_stability
# ---------------------------------------------------------------------------

def drift_and_stability(
    delta_xe: list[float],
    Cd: float,
    Ie: float,
    Px: list[float],
    Vx: list[float],
    hsx: list[float],
    *,
    drift_limit_ratio: float = 0.02,
) -> dict[str, Any]:
    """Inelastic drift and P-delta stability coefficients (ASCE 7 §12.8.6/7).

    Parameters
    ----------
    delta_xe : list[float]
        Elastic storey displacements from analysis (m). Bottom→top.
    Cd : float
        Deflection amplification factor (dimensionless). > 0.
    Ie : float
        Importance factor (dimensionless). > 0.
    Px : list[float]
        Total gravity load above each storey (kN). Bottom→top. All >= 0.
    Vx : list[float]
        Storey shear at each level (kN). Bottom→top. All > 0.
    hsx : list[float]
        Storey height at each level (m). Bottom→top. All > 0.
    drift_limit_ratio : float
        Allowable drift ratio Δ_allow/hsx (default 0.02 = 2% per ASCE 7
        Table 12.12-1 for Risk Category II, most occupancies).

    Returns
    -------
    dict with keys: Delta_x_m (list), drift_ratio (list),
                    drift_ok (list), theta (list), theta_ok (list),
                    Cd, Ie, drift_limit_ratio, warnings.
    """
    warnings: list[str] = []
    n = len(delta_xe)
    if n == 0:
        return {"ok": False, "reason": "delta_xe must not be empty"}
    if Cd <= 0:
        return {"ok": False, "reason": "Cd must be > 0"}
    if Ie <= 0:
        return {"ok": False, "reason": "Ie must be > 0"}
    if len(Px) != n or len(Vx) != n or len(hsx) != n:
        return {"ok": False, "reason": "delta_xe, Px, Vx, hsx must all be the same length"}
    if any(v <= 0 for v in Vx):
        return {"ok": False, "reason": "All Vx values must be > 0"}
    if any(h <= 0 for h in hsx):
        return {"ok": False, "reason": "All hsx values must be > 0"}
    if any(p < 0 for p in Px):
        return {"ok": False, "reason": "All Px values must be >= 0"}

    Delta_x = [round((Cd * delta_xe[i]) / Ie, 6) for i in range(n)]
    drift_ratio = [round(Delta_x[i] / hsx[i], 6) for i in range(n)]
    drift_ok = [dr <= drift_limit_ratio for dr in drift_ratio]

    theta = []
    theta_ok_list = []
    for i in range(n):
        th = (Px[i] * Delta_x[i]) / (Vx[i] * hsx[i] * Cd)
        theta.append(round(th, 6))
        theta_ok_list.append(th <= 0.10)

    for i, dr in enumerate(drift_ratio):
        if dr > drift_limit_ratio:
            warnings.append(
                f"Storey {i + 1}: drift ratio {dr:.4f} exceeds limit "
                f"{drift_limit_ratio:.4f} — drift exceedance."
            )

    for i, th in enumerate(theta):
        if th > 0.10:
            warnings.append(
                f"Storey {i + 1}: θ={th:.4f} > 0.10 — P-delta effects "
                "significant; verify θ ≤ θ_max per ASCE 7 §12.8.7."
            )

    if not all(drift_ok):
        warnings.append("irregularity-note: drift exceedance detected; "
                        "review structural irregularity per ASCE 7 §12.3.")

    return {
        "ok": True,
        "Delta_x_m": Delta_x,
        "drift_ratio": drift_ratio,
        "drift_ok": drift_ok,
        "theta": theta,
        "theta_ok": theta_ok_list,
        "Cd": Cd,
        "Ie": Ie,
        "drift_limit_ratio": drift_limit_ratio,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# sdof_spectral_displacement
# ---------------------------------------------------------------------------

def sdof_spectral_displacement(Sa_g: float, T: float) -> dict[str, Any]:
    """Elastic SDOF spectral displacement Sd = Sa·g·T²/(4π²).

    Parameters
    ----------
    Sa_g : float
        Spectral acceleration (g). Must be >= 0.
    T : float
        Period (s). Must be > 0.

    Returns
    -------
    dict with keys: Sd_m, Sd_mm, Sa_g, T_s, warnings.
    """
    warnings: list[str] = []
    if Sa_g < 0:
        return {"ok": False, "reason": "Sa_g must be >= 0"}
    if T <= 0:
        return {"ok": False, "reason": "T must be > 0"}

    g = 9.80665  # m/s²
    Sd = Sa_g * g * (T ** 2) / (4.0 * math.pi ** 2)

    if Sd > 2.0:
        warnings.append(
            f"Sd={Sd:.3f}m > 2.0m: very large spectral displacement; "
            "verify Sa_g and T inputs."
        )

    return {
        "ok": True,
        "Sd_m": round(Sd, 6),
        "Sd_mm": round(Sd * 1000.0, 3),
        "Sa_g": round(Sa_g, 6),
        "T_s": round(T, 4),
        "warnings": warnings,
    }
