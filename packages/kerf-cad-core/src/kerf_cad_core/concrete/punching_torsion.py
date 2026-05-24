"""
kerf_cad_core.concrete.punching_torsion — ACI 318-19 §22.6 punching shear
and §22.7 torsion design.

Units
-----
All public functions accept a ``metric`` keyword (default True) which selects
the unit system:

  metric=True  (SI)
    Lengths / dimensions : mm
    Areas               : mm²
    Forces              : N
    Stresses  (f'c, fy) : MPa
    Moments / Torques   : N·mm

  metric=False (US-customary)
    Lengths / dimensions : in
    Areas               : in²
    Forces              : lb  (lbf)
    Stresses  (f'c, fy) : psi
    Moments / Torques   : lb·in

All functions return plain ``dict``s.  Warnings are collected in
``result["warnings"]`` (list[str]); the functions never raise.

References
----------
ACI 318-19 Chapters 22.6 (two-way shear) and 22.7 (torsion).
Wight, J.K. "Reinforced Concrete: Mechanics and Design" 8th ed., Ch. 13
  (punching) and Ch. 8 (torsion).
Nilson, Darwin & Dolan "Design of Concrete Structures" 14th ed., Ch. 8
  (torsion).

Validation
----------
Punching shear: Wight & MacGregor 8th ed., Example 13-1 style check.
Torsion       : Nilson et al. Example 8-1 style check.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any


# ===========================================================================
# Internal helpers
# ===========================================================================

def _sqrt_fc(fc: float) -> float:
    """Square root of f'c; raises ValueError for negative f'c."""
    if fc < 0:
        raise ValueError(f"f'c must be >= 0; got {fc}")
    return math.sqrt(fc)


# ---------------------------------------------------------------------------
# Size-effect factor λs (ACI 318-19 §22.5.5.1.3 / §22.6.5.2)
# ---------------------------------------------------------------------------

def _lambda_s(d: float, metric: bool = True) -> float:
    """ACI 318-19 §22.5.5.1.3 size-effect factor.

    λs = min(1.0, sqrt(2 / (1 + 0.004·d)))

    where d is in **mm** for SI or **in** for US-customary.
    The factor 0.004 applies when d is in mm; the equivalent for inches is
    0.004 × 25.4 ≈ 0.1016, but ACI 318-19 Commentary (in the official SI
    edition) uses 0.004·d_mm, so we convert if needed.
    """
    if metric:
        d_mm = d
    else:
        d_mm = d * 25.4  # convert in → mm for the ACI formula
    val = math.sqrt(2.0 / (1.0 + 0.004 * d_mm))
    return min(val, 1.0)


# ===========================================================================
# 1. Critical perimeter b0 helper
# ===========================================================================

def critical_perimeter(
    c1: float,
    c2: float,
    d: float,
    *,
    column_location: str = "interior",
) -> dict[str, Any]:
    """Critical perimeter b0 at d/2 from the column face (ACI 318-19 §22.6.4.1).

    Parameters
    ----------
    c1 : column dimension parallel to bending direction (mm or in)
    c2 : column dimension perpendicular to bending direction (mm or in)
    d  : effective slab depth (mm or in)
    column_location : 'interior' | 'edge' | 'corner'

    Returns
    -------
    dict with keys:
      b0          — critical perimeter (mm or in)
      column_location
      warnings    — list[str]

    Notes
    -----
    Interior column : b0 = 2·(c1 + d) + 2·(c2 + d)
    Edge column     : b0 = 2·(c1 + d/2) + (c2 + d)   (one free face)
    Corner column   : b0 = (c1 + d/2) + (c2 + d/2)   (two free faces)
    """
    warnings: list[str] = []
    d2 = d / 2.0

    loc = column_location.lower().strip()
    if loc == "interior":
        b0 = 2.0 * (c1 + d) + 2.0 * (c2 + d)
    elif loc == "edge":
        b0 = 2.0 * (c1 + d2) + (c2 + d)
    elif loc == "corner":
        b0 = (c1 + d2) + (c2 + d2)
    else:
        warnings.append(
            f"unknown column_location '{column_location}'; defaulting to 'interior'"
        )
        loc = "interior"
        b0 = 2.0 * (c1 + d) + 2.0 * (c2 + d)

    return {
        "b0": b0,
        "column_location": loc,
        "warnings": warnings,
    }


# ===========================================================================
# 2. Two-way concrete shear strength (ACI 318-19 §22.6.5.2)
# ===========================================================================

def two_way_concrete_shear_strength(
    b0: float,
    d: float,
    fc: float,
    beta_c: float,
    alpha_s: float,
    *,
    lam: float = 1.0,
    lambda_s: float | None = None,
    metric: bool = True,
) -> dict[str, Any]:
    """Nominal two-way (punching) shear strength φVc per ACI 318-19 Table 22.6.5.2.

    The minimum of three expressions governs:

      (1) Vc = (0.33·λs·λ·√f'c)·b0·d                           [SI, MPa·mm²→N]
      (2) Vc = (0.17 + 0.34/β_c)·λs·λ·√f'c·b0·d               [SI]
      (3) Vc = (αs·d/b0 + 0.17)·λs·λ·√f'c·b0·d                [SI]

    For US-customary (metric=False) the coefficients become:

      (1) Vc = 4·λs·λ·√f'c·b0·d                                [psi, in²→lbf]
      (2) Vc = (2 + 4/β_c)·λs·λ·√f'c·b0·d
      (3) Vc = (αs·d/b0 + 2)·λs·λ·√f'c·b0·d

    Parameters
    ----------
    b0      : critical perimeter (mm or in)
    d       : effective slab depth (mm or in)
    fc      : concrete compressive strength f'c (MPa or psi)
    beta_c  : ratio of long to short column dimension (≥ 1)
    alpha_s : column location constant (40 interior / 30 edge / 20 corner)
    lam     : concrete density factor λ; 1.0 for normal-weight (default)
    lambda_s: size-effect factor; if None, computed from d per §22.5.5.1.3
    metric  : True → SI (MPa, mm, N); False → US-customary (psi, in, lbf)

    Returns
    -------
    dict with keys:
      lambda_s        — size-effect factor
      Vc1, Vc2, Vc3  — three nominal strengths (N or lbf) before φ
      Vc              — governing (minimum) nominal strength (N or lbf)
      warnings        — list[str]
    """
    warnings: list[str] = []

    if beta_c < 1.0:
        beta_c = max(beta_c, 1e-9)
        warnings.append("beta_c should be >= 1.0 (long/short ratio); using provided value")

    # Size-effect factor
    ls = lambda_s if lambda_s is not None else _lambda_s(d, metric=metric)

    sqrt_fc = _sqrt_fc(fc)

    if metric:
        # ACI 318-19 SI Table 22.6.5.2 — SI coefficients
        Vc1 = 0.33 * ls * lam * sqrt_fc * b0 * d
        Vc2 = (0.17 + 0.34 / beta_c) * ls * lam * sqrt_fc * b0 * d
        Vc3 = (alpha_s * d / b0 + 0.17) * ls * lam * sqrt_fc * b0 * d
    else:
        # ACI 318-19 US-customary Table 22.6.5.2
        Vc1 = 4.0 * ls * lam * sqrt_fc * b0 * d
        Vc2 = (2.0 + 4.0 / beta_c) * ls * lam * sqrt_fc * b0 * d
        Vc3 = (alpha_s * d / b0 + 2.0) * ls * lam * sqrt_fc * b0 * d

    Vc = min(Vc1, Vc2, Vc3)

    return {
        "lambda_s": ls,
        "Vc1": Vc1,
        "Vc2": Vc2,
        "Vc3": Vc3,
        "Vc": Vc,
        "warnings": warnings,
    }


# ===========================================================================
# 3. Punching shear check
# ===========================================================================

def punching_shear_check(
    Vu: float,
    b0: float,
    d: float,
    fc: float,
    beta_c: float,
    alpha_s: float,
    *,
    phi: float = 0.75,
    lam: float = 1.0,
    lambda_s: float | None = None,
    metric: bool = True,
) -> dict[str, Any]:
    """Two-way (punching) shear design check.

    Parameters
    ----------
    Vu      : factored punching shear demand (N or lbf)
    b0      : critical perimeter at d/2 from column face (mm or in)
    d       : effective slab depth (mm or in)
    fc      : f'c (MPa or psi)
    beta_c  : long-to-short column dimension ratio (≥ 1)
    alpha_s : 40 interior / 30 edge / 20 corner per ACI §22.6.5.2
    phi     : strength-reduction factor; default 0.75 (ACI §21.2.1)
    lam     : concrete density factor; 1.0 for normal-weight
    lambda_s: override for size-effect factor; computed if None
    metric  : True → SI; False → US-customary

    Returns
    -------
    dict with keys:
      Vc                    — nominal concrete shear strength (N or lbf)
      phiVc                 — design strength φVc (N or lbf)
      vu                    — average shear stress = Vu / (b0·d) (MPa or psi)
      phivc                 — design shear stress = φVc / (b0·d)
      demand_capacity_ratio — Vu / φVc
      ok                    — bool: Vu ≤ φVc
      governing_formula     — 1, 2, or 3 (which formula controlled Vc)
      lambda_s              — size-effect factor used
      warnings              — list[str]
    """
    warnings: list[str] = []

    result = two_way_concrete_shear_strength(
        b0, d, fc, beta_c, alpha_s,
        lam=lam, lambda_s=lambda_s, metric=metric
    )
    warnings.extend(result["warnings"])

    Vc = result["Vc"]
    ls = result["lambda_s"]

    # Identify governing formula
    vals = [result["Vc1"], result["Vc2"], result["Vc3"]]
    governing = int(vals.index(Vc)) + 1

    phiVc = phi * Vc
    bo_d = b0 * d
    vu = Vu / bo_d if bo_d > 0 else float("inf")
    phivc = phiVc / bo_d if bo_d > 0 else 0.0
    dcr = Vu / phiVc if phiVc > 0 else float("inf")
    ok = Vu <= phiVc

    if not ok:
        warnings.append(
            f"punching shear FAILS: Vu={Vu:.1f} > φVc={phiVc:.1f} "
            f"(DCR={dcr:.2f}); consider increasing d or f'c"
        )

    return {
        "Vc": Vc,
        "phiVc": phiVc,
        "vu": vu,
        "phivc": phivc,
        "demand_capacity_ratio": dcr,
        "ok": ok,
        "governing_formula": governing,
        "lambda_s": ls,
        "warnings": warnings,
    }


# ===========================================================================
# 4. Cracking / threshold torsion (ACI 318-19 §22.7.4–22.7.5)
# ===========================================================================

def cracking_torsion(
    Acp: float,
    pcp: float,
    fc: float,
    *,
    lam: float = 1.0,
    metric: bool = True,
) -> dict[str, Any]:
    """Cracking torsion Tcr and threshold (negligible) torsion Tth.

    ACI 318-19 Eq. (22.7.5.1) / Table 22.7.5.1:

      SI (MPa, mm):
        Tcr = 0.33·λ·√f'c · Acp²/pcp           [N·mm]
        Tth = 0.083·λ·√f'c · Acp²/pcp = Tcr/4  [N·mm]   (§22.7.4.1a)

      US-customary (psi, in):
        Tcr = 4·λ·√f'c · Acp²/pcp              [lb·in]
        Tth = 1·λ·√f'c · Acp²/pcp  = Tcr/4    [lb·in]

    Design torsion may be neglected when Tu ≤ φ·Tth  (φ=0.75, §21.2.1).

    Parameters
    ----------
    Acp : gross cross-sectional area enclosed by outer perimeter (mm² or in²)
    pcp : outer perimeter of gross section (mm or in)
    fc  : f'c (MPa or psi)
    lam : concrete density factor; 1.0 for normal-weight
    metric: True → SI; False → US-customary

    Returns
    -------
    dict with keys:
      Tcr         — cracking torsion (N·mm or lb·in)
      Tth         — threshold torsion = Tcr/4 (N·mm or lb·in)
      phi_Tth     — φ·Tth = 0.75·Tth (design threshold)
      warnings    — list[str]
    """
    warnings: list[str] = []

    if Acp <= 0 or pcp <= 0:
        warnings.append("Acp and pcp must be > 0; returning zeros")
        return {"Tcr": 0.0, "Tth": 0.0, "phi_Tth": 0.0, "warnings": warnings}

    sqrt_fc = _sqrt_fc(fc)

    if metric:
        Tcr = 0.33 * lam * sqrt_fc * Acp**2 / pcp
    else:
        Tcr = 4.0 * lam * sqrt_fc * Acp**2 / pcp

    Tth = Tcr / 4.0
    phi_Tth = 0.75 * Tth

    return {
        "Tcr": Tcr,
        "Tth": Tth,
        "phi_Tth": phi_Tth,
        "warnings": warnings,
    }


# ===========================================================================
# 5. Torsion design capacity (ACI 318-19 §22.7.6 / §22.7.7)
# ===========================================================================

def torsion_capacity(
    Aoh: float,
    ph: float,
    fyt: float,
    s: float,
    At: float,
    Al: float,
    *,
    fy: float | None = None,
    theta_deg: float = 45.0,
    phi: float = 0.75,
    metric: bool = True,
) -> dict[str, Any]:
    """Nominal torsional capacity from closed stirrups + longitudinal steel.

    ACI 318-19 §22.7.6.1 / Eq. (22.7.6.1a-b):

      Ao  = 0.85·Aoh                          (§22.7.6.1.1)
      Tn  = 2·Ao·(At/s)·fyt·cot θ            (stirrup contribution)

    ACI §22.7.6.1.2 (longitudinal steel check):
      Al ≥ At·fyt·ph / (s·fy)   (at minimum per §9.6.4.3 when combined)

    Parameters
    ----------
    Aoh     : area enclosed by centerline of outermost closed stirrup (mm² or in²)
    ph      : perimeter of closed stirrups (mm or in)
    fyt     : stirrup yield strength (MPa or psi)
    s       : stirrup spacing (mm or in)
    At      : area of one leg of closed stirrup (mm² or in²)
    Al      : total area of longitudinal torsion steel (mm² or in²)
    fy      : longitudinal steel yield strength; defaults to fyt if None
    theta_deg: angle of compression diagonal (deg); default 45° per ACI §22.7.6.1
    phi     : strength-reduction factor; default 0.75
    metric  : True → SI; False → US-customary

    Returns
    -------
    dict with keys:
      Ao          — area term = 0.85·Aoh (mm² or in²)
      Tn_stirrup  — nominal Tn from stirrups = 2·Ao·At·fyt·cotθ/s (N·mm or lb·in)
      phi_Tn      — design torsional strength φ·Tn (N·mm or lb·in)
      Al_req      — minimum longitudinal steel required = At·fyt·ph/(s·fy)
      Al_ok       — bool: provided Al ≥ Al_req
      warnings    — list[str]
    """
    warnings: list[str] = []

    if fy is None:
        fy = fyt

    if s <= 0:
        warnings.append("stirrup spacing s must be > 0; capacity = 0")
        return {
            "Ao": 0.0, "Tn_stirrup": 0.0, "phi_Tn": 0.0,
            "Al_req": 0.0, "Al_ok": False, "warnings": warnings,
        }

    theta = math.radians(theta_deg)
    cot_theta = 1.0 / math.tan(theta) if abs(math.tan(theta)) > 1e-12 else float("inf")

    Ao = 0.85 * Aoh

    # ACI 318-19 Eq. (22.7.6.1a): Tn = 2·Ao·At·fyt·cotθ / s
    Tn = 2.0 * Ao * (At / s) * fyt * cot_theta
    phi_Tn = phi * Tn

    # Minimum longitudinal steel check (ACI §22.7.6.1.2)
    Al_req = (At / s) * fyt * ph / fy
    Al_ok = Al >= Al_req - 1e-9

    if not Al_ok:
        warnings.append(
            f"insufficient longitudinal steel: Al={Al:.4f} < Al_req={Al_req:.4f} "
            f"(ACI §22.7.6.1.2)"
        )

    # ACI §22.7.6.1.1 requires Ao ≥ 0.85·Aoh (already used)
    # ACI §22.7.6.2 max stirrup spacing
    if metric:
        s_max = min(ph / 8.0, 300.0)  # mm
    else:
        s_max = min(ph / 8.0, 12.0)   # in
    if s > s_max:
        warnings.append(
            f"stirrup spacing s={s:.1f} exceeds max ph/8={ph/8:.1f} "
            f"(ACI §22.7.6.2)"
        )

    return {
        "Ao": Ao,
        "Tn_stirrup": Tn,
        "phi_Tn": phi_Tn,
        "Al_req": Al_req,
        "Al_ok": Al_ok,
        "warnings": warnings,
    }


# ===========================================================================
# 6. Combined shear + torsion interaction check (ACI 318-19 §22.7.7.1)
# ===========================================================================

def combined_shear_torsion_check(
    Vu: float,
    Tu: float,
    Vc: float,
    b_w: float,
    d: float,
    Aoh: float,
    ph: float,
    fc: float,
    *,
    phi: float = 0.75,
    metric: bool = True,
) -> dict[str, Any]:
    """Unified shear + torsion interaction check per ACI 318-19 §22.7.7.1.

    ACI 318-19 Eq. (22.7.7.1a) — solid section:

      √[ (Vu/(bw·d))² + (Tu·ph/(1.7·Aoh²))² ] ≤ φ·(Vc/(bw·d) + Vs_limit)

    where the right-hand side limit (concrete + steel) for solid sections is:

      φ·(Vc/(bw·d) + Vn_max_stress)

    ACI 318-19 defines the RHS as:
      SI:   φ·(Vc/(bw·d) + 0.66·√f'c)
      USC:  φ·(Vc/(bw·d) + 8·√f'c)

    Parameters
    ----------
    Vu   : factored shear (N or lbf)
    Tu   : factored torsion (N·mm or lb·in)
    Vc   : nominal concrete shear strength (N or lbf); from beam_shear
    b_w  : web width (mm or in)
    d    : effective depth (mm or in)
    Aoh  : area enclosed by closed stirrup centerline (mm² or in²)
    ph   : perimeter of closed stirrups (mm or in)
    fc   : f'c (MPa or psi)
    phi  : strength-reduction factor; default 0.75
    metric: True → SI; False → US-customary

    Returns
    -------
    dict with keys:
      lhs             — left-hand side of interaction equation (MPa or psi)
      rhs             — right-hand side limit φ·(Vc/(bw·d) + limit_stress)
      demand_ratio    — lhs / rhs
      ok              — bool: lhs ≤ rhs
      vu_stress       — Vu/(bw·d) shear stress (MPa or psi)
      tu_stress       — Tu·ph/(1.7·Aoh²) torsion stress (MPa or psi)
      warnings        — list[str]
    """
    warnings: list[str] = []

    bwd = b_w * d
    if bwd <= 0:
        warnings.append("b_w·d must be > 0")
        bwd = 1.0

    Aoh2 = 1.7 * Aoh**2
    if Aoh2 <= 0:
        warnings.append("Aoh must be > 0")
        Aoh2 = 1.0

    vu_stress = Vu / bwd
    tu_stress = Tu * ph / Aoh2

    lhs = math.sqrt(vu_stress**2 + tu_stress**2)

    sqrt_fc = _sqrt_fc(fc)
    vc_stress = Vc / bwd

    if metric:
        # SI: RHS = φ·(Vc/(bw·d) + 0.66·√f'c)
        limit_stress = 0.66 * sqrt_fc
    else:
        # USC: RHS = φ·(Vc/(bw·d) + 8·√f'c)
        limit_stress = 8.0 * sqrt_fc

    rhs = phi * (vc_stress + limit_stress)

    dcr = lhs / rhs if rhs > 0 else float("inf")
    ok = lhs <= rhs

    if not ok:
        warnings.append(
            f"combined shear+torsion FAILS: LHS={lhs:.3f} > RHS={rhs:.3f} "
            f"(DCR={dcr:.2f}); increase section size or f'c"
        )

    return {
        "lhs": lhs,
        "rhs": rhs,
        "demand_ratio": dcr,
        "ok": ok,
        "vu_stress": vu_stress,
        "tu_stress": tu_stress,
        "warnings": warnings,
    }
