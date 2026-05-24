"""
kerf_cad_core.flowmeter.measure — flow metering & flow-control sizing.

Pure-Python (no OCC, no external dependencies).  All functions return a plain
dict:  success → {"ok": True, ...}   failure → {"ok": False, "reason": "..."}
Functions NEVER raise.

Scope
-----
1.  Differential-pressure meters — ISO 5167 orifice plate, venturi tube,
    nozzle: Reader-Harris/Gallagher discharge coefficient, expansibility
    factor, mass & volume flow from ΔP, permanent pressure loss.

2.  Control-valve sizing — ISA/IEC Cv & Kv for:
      • liquid — choked flow (FL factor), cavitation index, FF factor
      • gas    — xT factor, expansion factor Y
      • steam  — inlet-condition with specific volume

3.  Pressure-relief-valve required orifice area — API 520 Part I:
      • gas / vapour (critical / sub-critical)
      • liquid
      • steam (Napier equation)
    API 526 designation letter lookup.

4.  Pitot tube and annubar velocity-based flow.

5.  Open-channel flow — V-notch (triangular), rectangular, Parshall flume.

6.  Rotameter (variable-area meter) scaling.

7.  Turndown ratio utility.

Units (SI unless noted)
-----------------------
  pressure      Pa (absolute where required, differential where noted)
  flow rates    m³/s (volume), kg/s (mass)
  Cv/Kv         US gpm / bar units  (Cv), m³/h / bar^0.5 units (Kv)
  area          m²
  length/head   m
  temperature   K
  density       kg/m³
  viscosity     Pa·s (dynamic)
  velocity      m/s

References
----------
ISO 5167-1:2003  — Measurement of fluid flow — Orifice plates
ISO 5167-2:2003  — Measurement of fluid flow — Venturi tubes
ISO 5167-3:2003  — Measurement of fluid flow — Nozzles
ANSI/ISA-75.01.01-2007 / IEC 60534-2-1:2011 — Control valve sizing
API Standard 520 Part I (9th ed., 2014) — PRV sizing
API Standard 526 (7th ed., 2017) — PRV designation letters
Miller — Flow Measurement Engineering Handbook (3rd ed.)

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ok(**kwargs: Any) -> dict:
    return {"ok": True, **kwargs}


def _pos(name: str, val: Any) -> str | None:
    """Return error reason string if val is not a positive number, else None."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return f"{name} must be a number"
    if not (v > 0):
        return f"{name} must be > 0"
    return None


def _nonneg(name: str, val: Any) -> str | None:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return f"{name} must be a number"
    if v < 0:
        return f"{name} must be >= 0"
    return None


# ---------------------------------------------------------------------------
# 1. ISO 5167  Differential-pressure meters
# ---------------------------------------------------------------------------

# Reader-Harris / Gallagher (RHG) discharge coefficient — ISO 5167-1:2003 §5.3
# Valid for orifice plates (D&D corners, flange, D & D/2 taps).
# Approximate form; full iterative solve for Re-dependent C is included.

_DP_METER_TYPES = {"orifice", "venturi", "nozzle"}

# Venturi / nozzle approximate C (weakly Re-dependent — use constant here)
_C_VENTURI = 0.985   # ISO 5167-4 Annex A
_C_NOZZLE = 0.9975   # ISA 1932 nozzle high-Re approx

# Permanent pressure-loss ratios  ΔP_perm / ΔP_measured  (approximate)
_PPL_RATIO = {
    "orifice": 0.73,    # classical orifice at β=0.6 (approx 0.73(1-β^4))
    "venturi": 0.07,    # diffuser recovery ≈93 %
    "nozzle":  0.35,    # partial recovery
}


def _rhg_orifice_C(beta: float, Re_D: float) -> float:
    """Reader-Harris/Gallagher Cd for D&D tapping, ISO 5167-1:2003 Eq.(1).

    Cd = 0.5961 + 0.0261β² − 0.216β⁸
         + 0.000521(10⁶β/Re_D)^0.7
         + (0.0188+0.0063A)β^3.5 (10⁶/Re_D)^0.3
         + (0.043+0.080exp(−10L1)−0.123exp(−7L1)) (1−0.11A) β⁴/(1−β⁴)
         − 0.031 (M2−0.8M2^1.1) β^1.3
    where A = (19000β/Re_D)^0.8, L1=L2=1 (D&D taps), M2=2L2/(1-β).
    """
    L1 = 1.0   # D&D taps
    L2 = 1.0
    A = (19000.0 * beta / Re_D) ** 0.8 if Re_D > 0 else 0.0
    M2 = 2.0 * L2 / (1.0 - beta)
    b2 = beta ** 2
    b4 = beta ** 4
    b35 = beta ** 3.5
    b13 = beta ** 1.3
    b8 = beta ** 8
    term1 = 0.5961 + 0.0261 * b2 - 0.216 * b8
    term2 = 0.000521 * (1e6 * beta / Re_D) ** 0.7 if Re_D > 0 else 0.0
    term3 = (0.0188 + 0.0063 * A) * b35 * (1e6 / Re_D) ** 0.3 if Re_D > 0 else 0.0
    term4 = (
        (0.043 + 0.080 * math.exp(-10.0 * L1) - 0.123 * math.exp(-7.0 * L1))
        * (1.0 - 0.11 * A) * b4 / (1.0 - b4)
    )
    term5 = -0.031 * (M2 - 0.8 * M2 ** 1.1) * b13
    return term1 + term2 + term3 + term4 + term5


def _expansibility_orifice(beta: float, dp: float, p1: float,
                            kappa: float) -> float:
    """ISO 5167-1:2003 Eq.(11) expansibility factor ε for orifice plate.

    ε = 1 − (0.351 + 0.256β⁴ + 0.93β⁸) [1 − (p2/p1)^(1/κ)]
    where p2/p1 = (p1 − dp) / p1
    """
    x = dp / p1
    b4 = beta ** 4
    b8 = beta ** 8
    return 1.0 - (0.351 + 0.256 * b4 + 0.93 * b8) * (1.0 - (1.0 - x) ** (1.0 / kappa))


def _expansibility_venturi(beta: float, dp: float, p1: float,
                            kappa: float) -> float:
    """ISO 5167-4:2003 Annex A expansibility for venturi / nozzle.

    Simpler form:
    ε = sqrt( (kappa * tau^(2/k) / (k-1))
              * ((1-beta^4)/(1 - tau^((k-1)/k) * beta^4 * ...)) ... )
    Use Eq. from ISO 5167-3/4:
    ε ≈ 1 − x*(0.41 + 0.35*β⁴)/κ   (linearised, conservative)
    """
    x = dp / p1
    b4 = beta ** 4
    return 1.0 - x * (0.41 + 0.35 * b4) / kappa


def dp_meter(
    meter_type: str,
    pipe_d_m: float,
    beta: float,
    dp_pa: float,
    rho_kg_m3: float,
    *,
    mu_pa_s: float = 1e-3,
    p1_pa: float | None = None,
    kappa: float = 1.4,
    gas: bool = False,
    tol: float = 1e-6,
    max_iter: int = 30,
) -> dict:
    """Differential-pressure meter flow calculation (ISO 5167).

    Parameters
    ----------
    meter_type : "orifice" | "venturi" | "nozzle"
    pipe_d_m   : pipe internal diameter [m]
    beta       : diameter ratio d/D  (0.1 – 0.75 orifice, 0.3–0.75 venturi)
    dp_pa      : differential pressure (p1 − p2) [Pa]
    rho_kg_m3  : fluid density at upstream condition [kg/m³]
    mu_pa_s    : dynamic viscosity [Pa·s]  (default water ≈ 1e-3)
    p1_pa      : upstream absolute pressure [Pa]  (required for gas)
    kappa      : isentropic exponent (gas only, default 1.4 air)
    gas        : True → apply expansibility factor ε

    Returns
    -------
    dict with keys: ok, qm_kg_s, qv_m3_s, Cd, Re_D, epsilon,
                    permanent_pressure_loss_pa, warnings
    """
    warnings: list[str] = []

    for name, val in [("pipe_d_m", pipe_d_m), ("dp_pa", dp_pa),
                      ("rho_kg_m3", rho_kg_m3), ("mu_pa_s", mu_pa_s)]:
        err = _pos(name, val)
        if err:
            return _err(err)
    err = _nonneg("beta", beta)
    if err:
        return _err(err)

    if meter_type not in _DP_METER_TYPES:
        return _err(f"meter_type must be one of {sorted(_DP_METER_TYPES)}")

    # Beta range checks (warn, don't fail)
    if meter_type == "orifice" and not (0.1 <= beta <= 0.75):
        warnings.append(f"beta={beta:.3f} out of ISO 5167-1 range [0.10, 0.75]")
    elif meter_type in ("venturi", "nozzle") and not (0.3 <= beta <= 0.75):
        warnings.append(f"beta={beta:.3f} out of ISO 5167 range [0.30, 0.75]")

    if gas and (p1_pa is None or p1_pa <= 0):
        return _err("p1_pa (absolute upstream pressure) required and must be > 0 for gas")

    D = float(pipe_d_m)
    b = float(beta)
    dp = float(dp_pa)
    rho = float(rho_kg_m3)
    mu = float(mu_pa_s)
    kap = float(kappa)

    d_throat = b * D
    A_throat = math.pi / 4.0 * d_throat ** 2
    b4 = b ** 4

    # Expansibility
    if gas and p1_pa is not None and p1_pa > 0:
        x = dp / float(p1_pa)
        if x >= 1.0:
            return _err("dp_pa must be < p1_pa (subsonic meter assumption)")
        if meter_type == "orifice":
            eps = _expansibility_orifice(b, dp, float(p1_pa), kap)
        else:
            eps = _expansibility_venturi(b, dp, float(p1_pa), kap)
    else:
        eps = 1.0

    # Iterative Cd solve for orifice (Re-dependent RHG)
    if meter_type == "orifice":
        # Initial guess C=0.61
        C = 0.61
        for _ in range(max_iter):
            qm = C * eps * A_throat / math.sqrt(1.0 - b4) * math.sqrt(2.0 * rho * dp)
            Re_D = 4.0 * qm / (math.pi * D * mu)
            C_new = _rhg_orifice_C(b, Re_D)
            if abs(C_new - C) < tol:
                C = C_new
                break
            C = C_new
        else:
            warnings.append("RHG iteration did not converge")
    elif meter_type == "venturi":
        C = _C_VENTURI
        Re_D = None  # approximate; compute from result
    else:  # nozzle
        C = _C_NOZZLE
        Re_D = None

    qm = C * eps * A_throat / math.sqrt(1.0 - b4) * math.sqrt(2.0 * rho * dp)
    qv = qm / rho

    if Re_D is None:
        Re_D = 4.0 * qm / (math.pi * D * mu)

    # Re check
    if meter_type == "orifice" and Re_D < 5000:
        warnings.append(f"Re_D={Re_D:.0f} below ISO 5167-1 lower limit (5000); Cd accuracy reduced")

    # Permanent pressure loss
    ppl_ratio = _PPL_RATIO.get(meter_type, 0.5)
    if meter_type == "orifice":
        # more accurate: (1 - beta^1.9) / (1 + beta^1.9)  — ISO 5167
        ppl_ratio = (1.0 - b ** 1.9) / (1.0 + b ** 1.9)
    ppl = ppl_ratio * dp

    return _ok(
        qm_kg_s=qm,
        qv_m3_s=qv,
        Cd=C,
        Re_D=Re_D,
        epsilon=eps,
        permanent_pressure_loss_pa=ppl,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 2. Control-valve sizing (ISA/IEC Cv & Kv)
# ---------------------------------------------------------------------------

# Conversion: Kv = Cv / 1.1561    (US GPM/psi to m³/h / bar^0.5)
_CV_TO_KV = 1.0 / 1.1561

# FL factor by trim type (approximate defaults)
_FL_DEFAULTS = {
    "single_seat": 0.90,
    "double_seat": 0.85,
    "butterfly_60": 0.55,
    "butterfly_90": 0.70,
    "ball_full": 0.60,
}

# xT factor (pressure-drop ratio at choked-flow for gas) by trim
_XT_DEFAULTS = {
    "single_seat": 0.72,
    "double_seat": 0.65,
    "butterfly_60": 0.42,
    "butterfly_90": 0.55,
    "ball_full": 0.53,
}


def control_valve_liquid(
    q_m3h: float,
    rho_kg_m3: float,
    dp_kpa: float,
    p1_kpa: float,
    pv_kpa: float,
    pc_kpa: float,
    *,
    FL: float = 0.90,
) -> dict:
    """ISA/IEC Cv & Kv sizing for incompressible liquid service.

    Parameters
    ----------
    q_m3h     : required flow rate [m³/h]
    rho_kg_m3 : upstream liquid density [kg/m³]
    dp_kpa    : service pressure drop p1 − p2 [kPa]
    p1_kpa    : upstream absolute pressure [kPa]
    pv_kpa    : liquid vapour pressure at flowing temperature [kPa]
    pc_kpa    : liquid thermodynamic critical pressure [kPa]
    FL        : pressure recovery factor (default 0.90 single-seat globe)

    Returns
    -------
    dict: ok, Cv, Kv, dp_choked_kpa, is_choked, cavitation_index,
          is_cavitating, warnings
    """
    warnings: list[str] = []

    for n, v in [("q_m3h", q_m3h), ("rho_kg_m3", rho_kg_m3),
                 ("dp_kpa", dp_kpa), ("p1_kpa", p1_kpa),
                 ("pc_kpa", pc_kpa)]:
        e = _pos(n, v)
        if e:
            return _err(e)
    e = _nonneg("pv_kpa", pv_kpa)
    if e:
        return _err(e)
    if not (0 < FL <= 1.0):
        return _err("FL must be in (0, 1]")

    # FF — liquid critical pressure ratio factor  (IEC 60534-2-1 Eq 13)
    FF = 0.96 - 0.28 * math.sqrt(pv_kpa / pc_kpa)

    # Choked ΔP
    dp_choked = FL ** 2 * (p1_kpa - FF * pv_kpa)
    dp_eff = min(dp_kpa, dp_choked)
    is_choked = dp_kpa >= dp_choked

    if is_choked:
        warnings.append("choked flow: actual ΔP >= ΔP_choked; size to dp_choked")

    # Cavitation index σ = (p1 - pv) / dp
    cav_idx = (p1_kpa - pv_kpa) / dp_kpa if dp_kpa > 0 else math.inf
    # Incipient cavitation roughly when σ < 2 (empirical)
    is_cav = cav_idx < 2.0
    if is_cav:
        warnings.append(f"cavitation likely: cavitation_index={cav_idx:.2f} < 2.0")

    # Kv = Q [m³/h] / sqrt(ΔP/ΔP_ref) where ΔP_ref=1 bar for water (SG=1)
    # General: Kv = Q * sqrt(SG / dp_bar) where SG = rho / 1000
    SG = rho_kg_m3 / 1000.0
    dp_bar = dp_eff / 100.0   # kPa → bar
    if dp_bar <= 0:
        return _err("effective pressure drop is zero; cannot size valve")
    Kv = q_m3h * math.sqrt(SG / dp_bar)
    Cv = Kv / _CV_TO_KV

    return _ok(
        Cv=Cv,
        Kv=Kv,
        dp_choked_kpa=dp_choked,
        FF=FF,
        is_choked=is_choked,
        cavitation_index=cav_idx,
        is_cavitating=is_cav,
        warnings=warnings,
    )


def control_valve_gas(
    q_kg_s: float,
    p1_pa: float,
    T1_K: float,
    MW_g_mol: float,
    dp_pa: float,
    *,
    xT: float = 0.72,
    Fp: float = 1.0,
    Z: float = 1.0,
    kappa: float = 1.4,
) -> dict:
    """ISA/IEC Cv sizing for compressible gas service.

    Parameters
    ----------
    q_kg_s   : mass flow [kg/s]
    p1_pa    : upstream absolute pressure [Pa]
    T1_K     : upstream temperature [K]
    MW_g_mol : molar mass [g/mol]
    dp_pa    : service differential pressure [Pa]
    xT       : terminal pressure-drop ratio factor (choked-flow xT)
    Fp       : piping geometry factor (default 1.0)
    Z        : compressibility factor (default 1.0)
    kappa    : isentropic exponent (default 1.4)

    Returns
    -------
    dict: ok, Cv, Kv, x, Y, is_choked, warnings
    """
    warnings: list[str] = []

    for n, v in [("q_kg_s", q_kg_s), ("p1_pa", p1_pa), ("T1_K", T1_K),
                 ("MW_g_mol", MW_g_mol), ("dp_pa", dp_pa)]:
        e = _pos(n, v)
        if e:
            return _err(e)
    if not (0 < xT <= 1.0):
        return _err("xT must be in (0, 1]")
    if not (0 < Fp <= 2.0):
        return _err("Fp must be in (0, 2]")
    if not (0.5 <= Z <= 2.0):
        return _err("Z must be in [0.5, 2]")

    # Pressure-drop ratio
    x = dp_pa / p1_pa
    # Choked limit: x_choked = xT * kappa / 1.4  (Fk·xT, Fk=κ/1.4)
    Fk = kappa / 1.4
    x_choked = Fk * xT
    is_choked = x >= x_choked

    # Expansion factor Y  (IEC 60534-2-1 Eq 27)
    # Y = 1 - x / (3 * Fk * xT * Fp²)  clamped to [2/3, 1]
    Y = max(2.0 / 3.0, 1.0 - x / (3.0 * Fk * xT))
    x_eff = min(x, x_choked)

    if is_choked:
        warnings.append("choked flow: x >= Fk·xT; actual flow limited by choked condition")
        Y = 2.0 / 3.0

    # Density at inlet
    rho1 = p1_pa * MW_g_mol * 1e-3 / (8.314 * T1_K * Z)   # kg/m³

    # Volumetric flow at upstream condition  [m³/h]
    q_m3h_upstream = q_kg_s / rho1 * 3600.0

    # IEC 60534-2-1 gas Kv equation (rearranged for Kv):
    # q [m³/h] = N7 * Fp * Cv * p1[bar] * Y * sqrt(x / (T1*Z*MW))
    # N7 = 4.17e-2 (SI hybrid: bar, K, g/mol)
    N7 = 4.17e-2
    p1_bar = p1_pa / 1e5
    denom = N7 * Fp * p1_bar * Y * math.sqrt(x_eff / (T1_K * Z * MW_g_mol))
    if denom == 0:
        return _err("zero denominator in gas Cv equation; check inputs")
    Cv = q_m3h_upstream / denom
    Kv = Cv * _CV_TO_KV

    return _ok(
        Cv=Cv,
        Kv=Kv,
        x=x,
        x_choked=x_choked,
        Y=Y,
        is_choked=is_choked,
        warnings=warnings,
    )


def control_valve_steam(
    q_kg_s: float,
    p1_pa: float,
    dp_pa: float,
    v1_m3_kg: float,
    *,
    xT: float = 0.72,
    Fp: float = 1.0,
) -> dict:
    """Cv sizing for steam service (IEC 60534-2-1).

    Uses the steam mass-flow form with upstream specific volume.

    Parameters
    ----------
    q_kg_s    : mass flow [kg/s]
    p1_pa     : upstream absolute pressure [Pa]
    dp_pa     : differential pressure [Pa]
    v1_m3_kg  : upstream specific volume [m³/kg]
    xT        : terminal pressure-drop ratio (default 0.72)
    Fp        : piping geometry factor (default 1.0)

    Returns
    -------
    dict: ok, Cv, Kv, is_choked, warnings
    """
    warnings: list[str] = []

    for n, v in [("q_kg_s", q_kg_s), ("p1_pa", p1_pa),
                 ("dp_pa", dp_pa), ("v1_m3_kg", v1_m3_kg)]:
        e = _pos(n, v)
        if e:
            return _err(e)

    # Steam expansion: use κ ≈ 1.135 (wet/sat steam) or caller-supplied
    kappa = 1.135
    Fk = kappa / 1.4
    x_choked = Fk * xT
    x = dp_pa / p1_pa
    is_choked = x >= x_choked
    Y = max(2.0 / 3.0, 1.0 - x / (3.0 * Fk * xT))
    x_eff = min(x, x_choked)

    if is_choked:
        Y = 2.0 / 3.0
        warnings.append("choked steam flow")

    # N6 form: q [kg/s] = N6 * Fp * Cv * Y * sqrt(dp[bar] / v1)
    # N6 = 1.10e-1  (SI hybrid: bar, m³/kg, kg/s, Cv in US gpm)
    N6 = 1.10e-1
    dp_bar = dp_pa / 1e5
    v1 = float(v1_m3_kg)
    p1_bar = p1_pa / 1e5
    denom = N6 * Fp * Y * math.sqrt(dp_bar / v1)
    if denom == 0:
        return _err("zero denominator in steam Cv equation")
    Cv = q_kg_s / denom
    Kv = Cv * _CV_TO_KV

    return _ok(
        Cv=Cv,
        Kv=Kv,
        x=x,
        x_choked=x_choked,
        Y=Y,
        is_choked=is_choked,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 3. Pressure-relief-valve orifice area (API 520 Part I)
# ---------------------------------------------------------------------------

# API 526 Table 1 — Effective orifice areas (in²) by letter, converted to m²
_API526_ORIFICE = {
    "D": 0.110 * 6.4516e-4,
    "E": 0.196 * 6.4516e-4,
    "F": 0.307 * 6.4516e-4,
    "G": 0.503 * 6.4516e-4,
    "H": 0.785 * 6.4516e-4,
    "J": 1.287 * 6.4516e-4,
    "K": 1.838 * 6.4516e-4,
    "L": 2.853 * 6.4516e-4,
    "M": 3.600 * 6.4516e-4,
    "N": 4.340 * 6.4516e-4,
    "P": 6.380 * 6.4516e-4,
    "Q": 11.05 * 6.4516e-4,
    "R": 16.00 * 6.4516e-4,
    "T": 26.00 * 6.4516e-4,
}
_API526_SORTED = sorted(_API526_ORIFICE.items(), key=lambda kv: kv[1])


def _api526_designation(area_m2: float) -> str:
    """Return smallest API 526 letter whose area >= area_m2."""
    for letter, a in _API526_SORTED:
        if a >= area_m2:
            return letter
    return "T+"  # oversized — larger than standard range


def prv_gas(
    q_kg_s: float,
    p_set_pa: float,
    T_K: float,
    MW_g_mol: float,
    *,
    overpressure_frac: float = 0.10,
    backpressure_pa: float = 101325.0,
    Z: float = 1.0,
    kd: float = 0.975,
    kb: float = 1.0,
    kc: float = 1.0,
) -> dict:
    """API 520 Part I gas/vapour PRV required orifice area.

    Parameters
    ----------
    q_kg_s           : required relieving mass flow [kg/s]
    p_set_pa         : set pressure (gauge, Pa abs from caller) [Pa abs]
    T_K              : relieving temperature [K]
    MW_g_mol         : molar mass [g/mol]
    overpressure_frac: allowable overpressure fraction (default 0.10 = 10%)
    backpressure_pa  : back pressure [Pa abs] (default atmosphere)
    Z                : compressibility at relieving conditions (default 1.0)
    kd               : discharge coefficient (default 0.975)
    kb               : back-pressure correction (default 1.0)
    kc               : combination correction (default 1.0)

    Returns
    -------
    dict: ok, area_m2, designation, P1_pa, Pcf_pa, is_critical, warnings
    """
    warnings: list[str] = []

    for n, v in [("q_kg_s", q_kg_s), ("p_set_pa", p_set_pa),
                 ("T_K", T_K), ("MW_g_mol", MW_g_mol)]:
        e = _pos(n, v)
        if e:
            return _err(e)
    if not (0.0 <= overpressure_frac <= 0.5):
        return _err("overpressure_frac must be in [0, 0.5]")

    P1 = p_set_pa * (1.0 + overpressure_frac)  # relieving pressure
    Pcf = backpressure_pa / P1                  # back-pressure ratio

    # Critical pressure ratio (API Eq 28): rcrit = (2/(k+1))^(k/(k-1))
    # Use k=1.4 for idealised; API 520 uses k from caller if provided.
    k = 1.4
    r_crit = (2.0 / (k + 1.0)) ** (k / (k - 1.0))
    is_critical = Pcf <= r_crit

    # API 520 Part I Eq (4) — critical (sonic) flow:
    # A = W / (C * kd * P1 * kb * kc) * sqrt(T*Z/M)
    # C = 520 * sqrt(k * (2/(k+1))^((k+1)/(k-1)))  — API constant
    C_api = 520.0 * math.sqrt(k * (2.0 / (k + 1.0)) ** ((k + 1.0) / (k - 1.0)))

    # Convert to SI units for area in m²:
    # API eq uses P1 in psia, W in lb/hr, T in °R, M in lb/lbmol
    # We work natively in SI then convert:
    # A_in2 = W_lbhr / (C * kd * P1_psia * kb * kc) * sqrt(T_R * Z / M_lbmol)
    # Conversion factors: 1 kg/s = 7936.64 lb/hr; 1 Pa = 1.45038e-4 psi; T_R = T_K*1.8; M_lbmol = MW_g_mol
    W_lbhr = q_kg_s * 7936.64
    P1_psia = P1 * 1.45038e-4
    T_R = T_K * 1.8
    M = MW_g_mol  # lb/lbmol numerically equal to g/mol

    if not is_critical:
        # Sub-critical: API Eq (5) — use F2 subcritical correction
        warnings.append(f"sub-critical flow: back-pressure ratio={Pcf:.3f} > critical={r_crit:.3f}")
        # F2 = sqrt((k/(k-1)) * r^(2/k) * (1 - r^((k-1)/k)) / (1 - r)) where r = P2/P1
        r = Pcf
        if r >= 1.0:
            return _err("backpressure_pa >= P1 (relieving pressure); check inputs")
        F2 = math.sqrt(
            (k / (k - 1.0)) * r ** (2.0 / k) * (1.0 - r ** ((k - 1.0) / k)) / (1.0 - r)
        )
        A_in2 = W_lbhr / (735.0 * kd * F2 * P1_psia * kc) * math.sqrt(T_R * Z / M)
    else:
        A_in2 = W_lbhr / (C_api * kd * P1_psia * kb * kc) * math.sqrt(T_R * Z / M)

    # Convert in² → m²
    A_m2 = A_in2 * 6.4516e-4
    designation = _api526_designation(A_m2)

    return _ok(
        area_m2=A_m2,
        area_in2=A_in2,
        designation=designation,
        P1_pa=P1,
        Pcf=Pcf,
        is_critical=is_critical,
        warnings=warnings,
    )


def prv_liquid(
    q_m3s: float,
    p_set_pa: float,
    rho_kg_m3: float,
    *,
    overpressure_frac: float = 0.25,
    backpressure_pa: float = 101325.0,
    kd: float = 0.65,
    kw: float = 1.0,
    kc: float = 1.0,
    kv: float = 1.0,
) -> dict:
    """API 520 Part I liquid PRV required orifice area.

    Parameters
    ----------
    q_m3s            : volumetric flow [m³/s]
    p_set_pa         : set pressure [Pa abs]
    rho_kg_m3        : liquid density [kg/m³]
    overpressure_frac: allowable overpressure (default 0.25 = 25%)
    backpressure_pa  : back pressure [Pa abs]
    kd               : discharge coefficient for liquid (default 0.65)
    kw               : back-pressure correction (default 1.0)
    kc               : combination correction (default 1.0)
    kv               : viscosity correction (default 1.0)

    Returns
    -------
    dict: ok, area_m2, designation, warnings
    """
    warnings: list[str] = []

    for n, v in [("q_m3s", q_m3s), ("p_set_pa", p_set_pa),
                 ("rho_kg_m3", rho_kg_m3)]:
        e = _pos(n, v)
        if e:
            return _err(e)

    P1 = p_set_pa * (1.0 + overpressure_frac)
    P2 = float(backpressure_pa)

    # API 520 liquid Eq (3): A = Q / (38.0 * kd * kw * kc * kv) * sqrt(G / (P1-P2))
    # where Q in US gpm, P in psia, G = SG
    # We convert:
    Q_gpm = q_m3s * 264.172  # m³/s → US gal/min
    SG = rho_kg_m3 / 999.0
    P1_psia = P1 * 1.45038e-4
    P2_psia = P2 * 1.45038e-4
    dP = P1_psia - P2_psia
    if dP <= 0:
        return _err("no differential pressure across PRV; check p_set_pa vs backpressure_pa")

    A_in2 = Q_gpm / (38.0 * kd * kw * kc * kv) * math.sqrt(SG / dP)
    A_m2 = A_in2 * 6.4516e-4
    designation = _api526_designation(A_m2)

    return _ok(
        area_m2=A_m2,
        area_in2=A_in2,
        designation=designation,
        P1_pa=P1,
        warnings=warnings,
    )


def prv_steam(
    q_kg_s: float,
    p_set_pa: float,
    *,
    overpressure_frac: float = 0.10,
    kd: float = 0.975,
    kb: float = 1.0,
    kn: float = 1.0,
    ksh: float = 1.0,
) -> dict:
    """API 520 Part I steam PRV — Napier equation.

    Parameters
    ----------
    q_kg_s           : required mass flow [kg/s]
    p_set_pa         : set pressure [Pa abs]
    overpressure_frac: allowable overpressure (default 10%)
    kd               : discharge coefficient (default 0.975)
    kb               : back-pressure correction (default 1.0)
    kn               : Napier steam correction (default 1.0; derates above 1500 psia)
    ksh              : superheat correction (default 1.0 = saturated)

    Returns
    -------
    dict: ok, area_m2, designation, P1_pa, warnings
    """
    warnings: list[str] = []

    for n, v in [("q_kg_s", q_kg_s), ("p_set_pa", p_set_pa)]:
        e = _pos(n, v)
        if e:
            return _err(e)

    P1 = p_set_pa * (1.0 + overpressure_frac)
    P1_psia = P1 * 1.45038e-4

    # Napier steam correction (API 520 Eq 17): if P1 > 1500 psia,
    # kn = (0.1906*P1 - 1000) / (0.2292*P1 - 1061)
    if P1_psia > 1500.0:
        kn = (0.1906 * P1_psia - 1000.0) / (0.2292 * P1_psia - 1061.0)
        warnings.append(f"P1={P1_psia:.0f} psia > 1500 psia; Napier kn={kn:.4f} applied")

    # API 520 Eq (12): A = W / (51.45 * kd * P1 * ksh * kb * kn)
    # W in lb/hr, P1 in psia, A in in²
    W_lbhr = q_kg_s * 7936.64
    A_in2 = W_lbhr / (51.45 * kd * P1_psia * ksh * kb * kn)
    A_m2 = A_in2 * 6.4516e-4
    designation = _api526_designation(A_m2)

    return _ok(
        area_m2=A_m2,
        area_in2=A_in2,
        designation=designation,
        P1_pa=P1,
        P1_psia=P1_psia,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 4. Pitot tube and annubar velocity-based flow
# ---------------------------------------------------------------------------

def pitot_velocity(
    dp_pa: float,
    rho_kg_m3: float,
    *,
    Cp: float = 1.0,
) -> dict:
    """Pitot-tube point velocity from impact pressure.

    v = Cp * sqrt(2 * dp / rho)

    Parameters
    ----------
    dp_pa      : impact (stagnation − static) pressure [Pa]
    rho_kg_m3  : fluid density [kg/m³]
    Cp         : pitot-tube coefficient (default 1.0 NIST standard)

    Returns
    -------
    dict: ok, velocity_m_s
    """
    for n, v in [("dp_pa", dp_pa), ("rho_kg_m3", rho_kg_m3)]:
        e = _pos(n, v)
        if e:
            return _err(e)
    if not (0.5 <= Cp <= 1.1):
        return _err("Cp must be in [0.5, 1.1]")

    vel = Cp * math.sqrt(2.0 * dp_pa / rho_kg_m3)
    return _ok(velocity_m_s=vel)


def annubar_flow(
    dp_pa: float,
    rho_kg_m3: float,
    pipe_d_m: float,
    *,
    Cp: float = 0.77,
) -> dict:
    """Annubar (multi-port averaging pitot) volume & mass flow.

    Uses average-velocity × pipe area:
      v_avg = Cp * sqrt(2 * dp / rho)
      qv    = v_avg * π/4 * D²

    Parameters
    ----------
    dp_pa      : differential pressure [Pa]
    rho_kg_m3  : fluid density [kg/m³]
    pipe_d_m   : pipe inside diameter [m]
    Cp         : annubar flow coefficient (typical 0.77)

    Returns
    -------
    dict: ok, velocity_m_s, qv_m3_s, qm_kg_s
    """
    for n, v in [("dp_pa", dp_pa), ("rho_kg_m3", rho_kg_m3), ("pipe_d_m", pipe_d_m)]:
        e = _pos(n, v)
        if e:
            return _err(e)
    if not (0.5 <= Cp <= 1.1):
        return _err("Cp must be in [0.5, 1.1]")

    vel = Cp * math.sqrt(2.0 * dp_pa / rho_kg_m3)
    A = math.pi / 4.0 * pipe_d_m ** 2
    qv = vel * A
    qm = qv * rho_kg_m3
    return _ok(velocity_m_s=vel, qv_m3_s=qv, qm_kg_s=qm)


# ---------------------------------------------------------------------------
# 5. Open-channel flow
# ---------------------------------------------------------------------------

def v_notch_weir(
    H_m: float,
    *,
    theta_deg: float = 90.0,
    Cd: float = 0.611,
) -> dict:
    """V-notch (triangular) weir flow — ISO 1438.

    Q = (8/15) * Cd * sqrt(2g) * tan(θ/2) * H^(5/2)

    Parameters
    ----------
    H_m       : head above notch vertex [m]
    theta_deg : notch angle [degrees] (default 90°)
    Cd        : discharge coefficient (default 0.611)

    Returns
    -------
    dict: ok, qv_m3_s, warnings
    """
    warnings: list[str] = []
    e = _pos("H_m", H_m)
    if e:
        return _err(e)
    if not (20.0 <= theta_deg <= 120.0):
        warnings.append(f"theta_deg={theta_deg} outside typical range [20, 120]")
    if not (0.4 <= Cd <= 0.8):
        warnings.append(f"Cd={Cd} outside typical range [0.4, 0.8]")

    g = 9.80665
    half_angle = math.radians(theta_deg / 2.0)
    qv = (8.0 / 15.0) * Cd * math.sqrt(2.0 * g) * math.tan(half_angle) * H_m ** 2.5
    return _ok(qv_m3_s=qv, warnings=warnings)


def rectangular_weir(
    H_m: float,
    L_m: float,
    *,
    Cd: float = 0.611,
    end_contractions: int = 2,
) -> dict:
    """Rectangular sharp-crested weir — Francis / Rehbock formula.

    Q = (2/3) * Cd * sqrt(2g) * Leff * H^(3/2)
    Leff = L − 0.1 * n_contractions * H  (Francis contraction correction)

    Parameters
    ----------
    H_m             : head above weir crest [m]
    L_m             : weir length [m]
    Cd              : discharge coefficient (default 0.611)
    end_contractions: number of end contractions (0 or 2, default 2)

    Returns
    -------
    dict: ok, qv_m3_s, Leff_m, warnings
    """
    warnings: list[str] = []
    for n, v in [("H_m", H_m), ("L_m", L_m)]:
        e = _pos(n, v)
        if e:
            return _err(e)
    if end_contractions not in (0, 2):
        return _err("end_contractions must be 0 or 2")

    g = 9.80665
    Leff = L_m - 0.1 * end_contractions * H_m
    if Leff <= 0:
        warnings.append("effective weir length Leff <= 0; contraction correction too large")
        Leff = L_m  # fallback

    qv = (2.0 / 3.0) * Cd * math.sqrt(2.0 * g) * Leff * H_m ** 1.5
    return _ok(qv_m3_s=qv, Leff_m=Leff, warnings=warnings)


# Parshall flume coefficients: {throat_width_m: (C, n)}  from standard tables
_PARSHALL_COEFF: dict[float, tuple[float, float]] = {
    0.025: (0.02426, 1.600),
    0.051: (0.04636, 1.580),
    0.076: (0.07105, 1.530),
    0.152: (0.14286, 1.522),
    0.229: (0.21785, 1.537),
    0.305: (0.29114, 1.522),
    0.457: (0.45674, 1.537),
    0.610: (0.61158, 1.522),
    0.914: (0.91480, 1.537),
    1.219: (1.21928, 1.522),
    1.524: (1.52520, 1.537),
    1.829: (1.82880, 1.522),
}


def parshall_flume(
    Ha_m: float,
    throat_w_m: float,
) -> dict:
    """Parshall flume flow rate from upstream head.

    Q = C * Ha^n   (free-flow equation, USBR standard)

    Parameters
    ----------
    Ha_m       : upstream gauge head [m]
    throat_w_m : throat width [m]; must be a standard size

    Returns
    -------
    dict: ok, qv_m3_s, C, n, warnings
    """
    warnings: list[str] = []
    for n_name, v in [("Ha_m", Ha_m), ("throat_w_m", throat_w_m)]:
        e = _pos(n_name, v)
        if e:
            return _err(e)

    # Find nearest standard size
    best = min(_PARSHALL_COEFF.keys(), key=lambda w: abs(w - throat_w_m))
    if abs(best - throat_w_m) / best > 0.05:
        warnings.append(
            f"throat_w_m={throat_w_m:.4f} not a standard size; "
            f"using nearest={best:.4f} m"
        )
    C, n = _PARSHALL_COEFF[best]
    qv = C * Ha_m ** n
    return _ok(qv_m3_s=qv, C=C, n=n, warnings=warnings)


# ---------------------------------------------------------------------------
# 6. Rotameter (variable-area meter) scaling
# ---------------------------------------------------------------------------

def rotameter_scale(
    Q_ref_m3s: float,
    rho_ref_kg_m3: float,
    rho_actual_kg_m3: float,
    *,
    float_density_kg_m3: float = 8000.0,
) -> dict:
    """Scale rotameter reading for different fluid density.

    Correction:
      Q_actual = Q_reading * sqrt((rho_float − rho_ref) * rho_actual /
                                  ((rho_float − rho_actual) * rho_ref))

    Parameters
    ----------
    Q_ref_m3s          : flow reading on rotameter scale (calibrated fluid) [m³/s]
    rho_ref_kg_m3      : calibration fluid density [kg/m³]
    rho_actual_kg_m3   : actual process fluid density [kg/m³]
    float_density_kg_m3: float (rotor) material density [kg/m³] (default SS 8000)

    Returns
    -------
    dict: ok, Q_actual_m3s, scale_factor
    """
    for n, v in [("Q_ref_m3s", Q_ref_m3s), ("rho_ref_kg_m3", rho_ref_kg_m3),
                 ("rho_actual_kg_m3", rho_actual_kg_m3),
                 ("float_density_kg_m3", float_density_kg_m3)]:
        e = _pos(n, v)
        if e:
            return _err(e)

    rho_f = float(float_density_kg_m3)
    rho_r = float(rho_ref_kg_m3)
    rho_a = float(rho_actual_kg_m3)

    denom_inner = (rho_f - rho_a) * rho_r
    if denom_inner <= 0:
        return _err(
            "denominator is non-positive; check that float_density > rho_actual and rho_ref > 0"
        )
    numer_inner = (rho_f - rho_r) * rho_a
    if numer_inner <= 0:
        return _err(
            "numerator is non-positive; check that float_density > rho_ref"
        )

    scale = math.sqrt(numer_inner / denom_inner)
    Q_actual = float(Q_ref_m3s) * scale
    return _ok(Q_actual_m3s=Q_actual, scale_factor=scale)


# ---------------------------------------------------------------------------
# 7. Turndown ratio
# ---------------------------------------------------------------------------

def turndown_ratio(Q_max: float, Q_min: float) -> dict:
    """Compute meter turndown ratio and check adequacy.

    Parameters
    ----------
    Q_max : maximum flow rate (any consistent unit)
    Q_min : minimum flow rate (any consistent unit)

    Returns
    -------
    dict: ok, turndown, warnings
    """
    warnings: list[str] = []
    for n, v in [("Q_max", Q_max), ("Q_min", Q_min)]:
        e = _pos(n, v)
        if e:
            return _err(e)
    if Q_min > Q_max:
        return _err("Q_min must be <= Q_max")

    td = float(Q_max) / float(Q_min)
    if td < 3.0:
        warnings.append(f"turndown={td:.1f}:1 is low (< 3:1); consider a wider-range meter")
    return _ok(turndown=td, warnings=warnings)
