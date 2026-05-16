"""
kerf_cad_core.concrete.design — ACI 318-19 reinforced-concrete design.

Units: US-customary throughout.
  Lengths / dimensions : inches (in)
  Areas               : square inches (in²)
  Forces              : pounds (lb) or kips (kip = 1000 lb)
  Moments             : kip·in  (or ft·kip where noted in docstrings)
  Stresses            : psi (pounds per square inch)
  f'c, fy             : psi

All functions return plain dicts.  Warnings are collected in result["warnings"]
(list of strings); the functions never raise.

References
----------
ACI 318-19 Chapters 9, 10, 11, 12, 17, 22, 24, 25.
McCormac & Brown "Design of Reinforced Concrete" 9th ed. (MC9).
Wight "Reinforced Concrete: Mechanics and Design" 8th ed.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _beta1(fc_psi: float) -> float:
    """ACI 318-19 §22.2.2.4.3 — Whitney stress-block depth factor β₁."""
    if fc_psi <= 4000:
        return 0.85
    b = 0.85 - 0.05 * (fc_psi - 4000) / 1000.0
    return max(b, 0.65)


def _phi_flexure(net_tensile_strain: float) -> tuple[float, str]:
    """ACI 318-19 §21.2.2 strength-reduction factor for flexure.

    Returns (phi, zone) where zone is one of:
      'tension-controlled'    εt >= 0.005   → φ = 0.90
      'transition'            0.002 < εt < 0.005
      'compression-controlled' εt <= 0.002   → φ = 0.65 (tied) / 0.75 (spiral)
    We use tied column φ = 0.65 for compression-controlled.
    """
    eps_t = net_tensile_strain
    if eps_t >= 0.005:
        return 0.90, "tension-controlled"
    elif eps_t > 0.002:
        # linear interpolation per ACI 318-19 Table 21.2.2
        phi = 0.65 + (eps_t - 0.002) * (0.90 - 0.65) / (0.005 - 0.002)
        return phi, "transition"
    else:
        return 0.65, "compression-controlled"


def _rho_balanced(fc_psi: float, fy_psi: float) -> float:
    """Balanced reinforcement ratio (ACI 318-19 §9.3.3.1 derivation)."""
    beta1 = _beta1(fc_psi)
    eps_u = 0.003
    return (0.85 * beta1 * fc_psi / fy_psi) * (eps_u / (eps_u + fy_psi / 29_000_000))


def _rho_max(fc_psi: float, fy_psi: float) -> float:
    """Maximum ρ for tension-controlled section (εt = 0.004, ACI 318-19 §9.3.3.1)."""
    beta1 = _beta1(fc_psi)
    eps_u = 0.003
    return (0.85 * beta1 * fc_psi / fy_psi) * (eps_u / (eps_u + 0.004))


def _rho_min_beam(fc_psi: float, fy_psi: float) -> float:
    """ACI 318-19 §9.6.1.2 minimum steel ratio for beams."""
    return max(3 * math.sqrt(fc_psi) / fy_psi, 200 / fy_psi)


# ---------------------------------------------------------------------------
# 1. Singly & doubly reinforced rectangular beam flexure
# ---------------------------------------------------------------------------

def beam_flexure(
    b: float,
    d: float,
    As: float,
    fc_psi: float,
    fy_psi: float,
    *,
    As_prime: float = 0.0,
    d_prime: float = 0.0,
    Es_psi: float = 29_000_000.0,
) -> dict[str, Any]:
    """Rectangular beam flexural strength — singly or doubly reinforced.

    Parameters (US-customary, all in inches / psi)
    ----------
    b       : beam width (in)
    d       : effective depth to tension steel centroid (in)
    As      : tension steel area (in²)
    fc_psi  : concrete compressive strength f'c (psi)
    fy_psi  : steel yield strength fy (psi)
    As_prime: compression steel area (in²); 0 → singly reinforced
    d_prime : depth to compression steel centroid (in); required if As_prime > 0
    Es_psi  : steel modulus (psi); default 29,000,000 psi

    Returns
    -------
    dict with keys:
      a_in          — Whitney stress-block depth (in)
      c_in          — neutral axis depth (in)
      beta1         — β₁ factor
      eps_t         — net tensile strain at extreme tension steel
      phi           — strength-reduction factor
      zone          — 'tension-controlled' / 'transition' / 'compression-controlled'
      Mn_kipin      — nominal moment capacity (kip·in)
      phi_Mn_kipin  — design moment capacity φMn (kip·in)
      rho           — provided tension steel ratio As/(b·d)
      rho_min       — ACI minimum steel ratio
      rho_max       — ACI maximum (tension-controlled limit, εt=0.004)
      rho_balanced  — balanced steel ratio
      warnings      — list[str]

    Notes
    -----
    For doubly reinforced beams the compression steel stress is computed from
    strain compatibility and may be less than fy if the steel has not yielded.
    """
    warnings: list[str] = []

    beta1 = _beta1(fc_psi)
    rho_min = _rho_min_beam(fc_psi, fy_psi)
    rho_max = _rho_max(fc_psi, fy_psi)
    rho_bal = _rho_balanced(fc_psi, fy_psi)
    rho = As / (b * d)

    if rho < rho_min:
        warnings.append(
            f"under-reinforced-fails: ρ={rho:.5f} < ρ_min={rho_min:.5f} (ACI 318-19 §9.6.1.2)"
        )
    if rho > rho_max:
        warnings.append(
            f"over-reinforced (εt<0.004): ρ={rho:.5f} > ρ_max={rho_max:.5f}"
        )

    # Compression steel contribution
    if As_prime > 0.0 and d_prime > 0.0:
        # Iterative neutral-axis solve for doubly reinforced
        # Force equilibrium: 0.85*f'c*b*a + As'*f's = As*fy
        # where f's = Es * (c - d') / c * 0.003 <= fy
        c = (As * fy_psi) / (0.85 * fc_psi * b * beta1)  # initial guess (singly)
        for _ in range(50):
            eps_prime = 0.003 * (c - d_prime) / c
            fs_prime = min(eps_prime * Es_psi, fy_psi)
            if fs_prime < 0:
                fs_prime = 0.0
            c_new = (As * fy_psi - As_prime * fs_prime) / (0.85 * fc_psi * b * beta1)
            if abs(c_new - c) < 1e-6:
                break
            c = c_new
        a = beta1 * c
        eps_prime = 0.003 * (c - d_prime) / c
        fs_prime = min(eps_prime * Es_psi, fy_psi)
        if fs_prime < 0:
            fs_prime = 0.0
        # Moment arms
        Mn = (0.85 * fc_psi * b * a * (d - a / 2) + As_prime * fs_prime * (d - d_prime))
    else:
        # Singly reinforced
        a = (As * fy_psi) / (0.85 * fc_psi * b)
        c = a / beta1
        fs_prime = 0.0
        Mn = 0.85 * fc_psi * b * a * (d - a / 2)

    eps_t = 0.003 * (d - c) / c
    phi, zone = _phi_flexure(eps_t)

    if zone == "compression-controlled":
        warnings.append(
            "compression-controlled section: φ reduced to 0.65; verify design intent"
        )

    Mn_kipin = Mn / 1000.0
    phi_Mn_kipin = phi * Mn_kipin

    return {
        "a_in": a,
        "c_in": c,
        "beta1": beta1,
        "eps_t": eps_t,
        "phi": phi,
        "zone": zone,
        "Mn_kipin": Mn_kipin,
        "phi_Mn_kipin": phi_Mn_kipin,
        "rho": rho,
        "rho_min": rho_min,
        "rho_max": rho_max,
        "rho_balanced": rho_bal,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. Required As for a given Mu
# ---------------------------------------------------------------------------

def beam_required_As(
    b: float,
    d: float,
    Mu_kipin: float,
    fc_psi: float,
    fy_psi: float,
) -> dict[str, Any]:
    """Required tension steel area for a rectangular beam given factored moment Mu.

    Parameters (US-customary)
    ----------
    b          : beam width (in)
    d          : effective depth (in)
    Mu_kipin   : factored moment demand (kip·in)
    fc_psi     : f'c (psi)
    fy_psi     : fy  (psi)

    Returns
    -------
    dict with keys:
      As_req_in2    — required steel area (in²)
      a_in          — stress-block depth (in)
      rho_req       — required steel ratio
      rho_min       — ACI minimum steel ratio
      phi_Mn_kipin  — design moment capacity at As_req (kip·in); ≈ Mu
      warnings      — list[str]

    Notes
    -----
    Uses the quadratic solution of φMn = Mu (assuming φ = 0.90 and iterating
    once to verify tension-controlled zone).  Warns if As_req < As_min.
    """
    warnings: list[str] = []
    rho_min = _rho_min_beam(fc_psi, fy_psi)
    beta1 = _beta1(fc_psi)
    phi = 0.90  # assume tension-controlled initially

    # Quadratic: Mu = phi * As * fy * (d - As*fy/(1.7*f'c*b))
    # Let x = As*fy / (0.85*f'c*b)  → a = x
    # phi * fy * As * (d - x/2) = Mu  →  solve As
    # phi * As * fy * d - phi * (As*fy)^2 / (1.7*f'c*b) = Mu
    alpha = fy_psi / (1.7 * fc_psi * b)
    # Mu_psin = Mu_kipin * 1000 (lb·in)
    Mu_lbin = Mu_kipin * 1000.0
    # phi * fy * As * d - phi * fy^2 * As^2 / (1.7*f'c*b) = Mu
    # → phi*fy^2/(1.7*f'c*b) * As^2 - phi*fy*d * As + Mu = 0
    A_coef = phi * fy_psi**2 / (1.7 * fc_psi * b)
    B_coef = -phi * fy_psi * d
    C_coef = Mu_lbin
    disc = B_coef**2 - 4 * A_coef * C_coef
    if disc < 0:
        warnings.append("discriminant<0: section may be too small for this Mu")
        As_req = 0.0
        a = 0.0
    else:
        # Take the smaller root (the one that works for a singly reinforced beam)
        As_req = (-B_coef - math.sqrt(disc)) / (2 * A_coef)
        a = As_req * fy_psi / (0.85 * fc_psi * b)

    rho_req = As_req / (b * d) if b * d > 0 else 0.0
    As_min = rho_min * b * d

    if As_req < As_min:
        warnings.append(
            f"As_req={As_req:.3f} in² < As_min={As_min:.3f} in² (ACI §9.6.1.2); "
            "use As_min"
        )
        As_req = As_min

    # Verify phi_Mn ≥ Mu
    c = (As_req * fy_psi / (0.85 * fc_psi * b)) / beta1
    eps_t = 0.003 * (d - c) / c if c > 0 else 1.0
    phi_actual, zone = _phi_flexure(eps_t)
    Mn_lbin = 0.85 * fc_psi * b * (As_req * fy_psi / (0.85 * fc_psi * b)) * (
        d - (As_req * fy_psi / (0.85 * fc_psi * b)) / 2
    )
    phi_Mn_kipin = phi_actual * Mn_lbin / 1000.0

    return {
        "As_req_in2": As_req,
        "a_in": a,
        "rho_req": rho_req,
        "rho_min": rho_min,
        "phi_Mn_kipin": phi_Mn_kipin,
        "zone": zone,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. Beam shear
# ---------------------------------------------------------------------------

def beam_shear(
    b_w: float,
    d: float,
    fc_psi: float,
    fy_psi: float,
    Vu_kip: float,
    Av_in2: float,
    s_in: float,
    *,
    rho_w: float = 0.0,
    Nu_kip: float = 0.0,
) -> dict[str, Any]:
    """ACI 318-19 §22.5 one-way shear for rectangular beams.

    Parameters (US-customary)
    ----------
    b_w     : web width (in)
    d       : effective depth (in)
    fc_psi  : f'c (psi)
    fy_psi  : fy of stirrup steel (psi)
    Vu_kip  : factored shear demand (kip)
    Av_in2  : stirrup area (both legs) per spacing (in²/stirrup)
    s_in    : stirrup spacing (in)
    rho_w   : longitudinal tension steel ratio As/(b_w*d); optional (0 → use
              simplified Vc = 2*lambda*sqrt(f'c)*b_w*d)
    Nu_kip  : factored axial load (kip, + compression); default 0

    Returns
    -------
    dict with keys:
      Vc_kip          — concrete shear strength (kip)
      Vs_kip          — steel shear strength at given Av, s (kip)
      Vn_kip          — nominal shear strength Vc + Vs (kip)
      phi_Vn_kip      — design shear strength φVn (kip); φ = 0.75
      demand_ratio    — Vu / (φVn)
      s_req_in        — required stirrup spacing for Vs = (Vu/φ - Vc) (in)
      s_max_in        — ACI maximum stirrup spacing (in)
      Vs_max_kip      — ACI upper limit on Vs = 8*sqrt(f'c)*b_w*d/1000 (kip)
      adequate        — bool: φVn >= Vu
      warnings        — list[str]

    Notes
    -----
    Uses Table 22.5.5.1 simplified Vc when rho_w == 0, else detailed form.
    Stirrups required when Vu > φVc/2 (ACI §9.6.3.1).
    """
    warnings: list[str] = []
    phi_v = 0.75  # ACI §21.2.1 shear

    lam = 1.0  # normal-weight concrete
    sqrt_fc = math.sqrt(fc_psi)

    # Concrete shear strength
    if rho_w > 0:
        # ACI 318-19 Eq. (22.5.5.1) detailed
        Nu_lb = Nu_kip * 1000.0
        Vc_lb = (
            8 * lam * (rho_w ** (1 / 3)) * sqrt_fc + Nu_lb / (6 * b_w * d)
        ) * b_w * d
    else:
        # Simplified: Vc = 2λ√f'c · bw · d
        Vc_lb = 2 * lam * sqrt_fc * b_w * d

    Vc_kip = Vc_lb / 1000.0

    # Steel shear strength at provided Av / s
    Vs_kip = (Av_in2 * fy_psi * d) / (s_in * 1000.0)
    Vn_kip = Vc_kip + Vs_kip
    phi_Vn_kip = phi_v * Vn_kip

    # Required stirrup spacing for the given Vu
    Vs_req_kip = max(Vu_kip / phi_v - Vc_kip, 0.0)
    if Vs_req_kip > 0 and Av_in2 > 0:
        s_req_in = (Av_in2 * fy_psi * d) / (Vs_req_kip * 1000.0)
    elif Vs_req_kip == 0:
        s_req_in = float("inf")  # no stirrups needed beyond minimum
    else:
        s_req_in = 0.0
        warnings.append("Av_in2=0 but stirrups are needed; provide stirrup area")

    # ACI maximum stirrup spacing (§9.7.6.2.2)
    s_max_in = min(d / 2.0, 24.0)
    # If Vs > 4√f'c·bw·d → halve max spacing
    Vs_limit_kip = 4 * sqrt_fc * b_w * d / 1000.0
    if Vs_kip > Vs_limit_kip:
        s_max_in = min(d / 4.0, 12.0)
        warnings.append(
            f"Vs={Vs_kip:.2f} kip > 4√f'c·bw·d={Vs_limit_kip:.2f} kip: "
            "max stirrup spacing halved (ACI §9.7.6.2.2)"
        )

    Vs_max_kip = 8 * sqrt_fc * b_w * d / 1000.0
    if Vs_req_kip > Vs_max_kip:
        warnings.append(
            f"spacing-violation: Vs_req={Vs_req_kip:.2f} kip > "
            f"Vs_max=8√f'c·bw·d={Vs_max_kip:.2f} kip; increase section size"
        )

    if s_in > s_max_in:
        warnings.append(
            f"spacing-violation: provided s={s_in:.2f} in > s_max={s_max_in:.2f} in "
            "(ACI §9.7.6.2.2)"
        )

    adequate = phi_Vn_kip >= Vu_kip
    demand_ratio = Vu_kip / phi_Vn_kip if phi_Vn_kip > 0 else float("inf")

    return {
        "Vc_kip": Vc_kip,
        "Vs_kip": Vs_kip,
        "Vn_kip": Vn_kip,
        "phi_Vn_kip": phi_Vn_kip,
        "demand_ratio": demand_ratio,
        "s_req_in": s_req_in,
        "s_max_in": s_max_in,
        "Vs_max_kip": Vs_max_kip,
        "adequate": adequate,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. T-beam effective flange width
# ---------------------------------------------------------------------------

def tbeam_effective_flange(
    bw: float,
    hf: float,
    span_in: float,
    spacing_in: float,
    *,
    side: str = "both",
) -> dict[str, Any]:
    """ACI 318-19 §6.3.2 effective overhanging flange width for T-beams.

    Parameters (US-customary, inches)
    ----------
    bw         : web width (in)
    hf         : flange (slab) thickness (in)
    span_in    : clear span of beam (in)
    spacing_in : center-to-center spacing to adjacent beam (in)
    side       : 'both' (T-beam, default) or 'one' (L-beam / edge beam)

    Returns
    -------
    dict with keys:
      be_in     — effective flange width (in)
      overhang  — total overhang (in); = be_in - bw
      warnings  — list[str]
    """
    warnings: list[str] = []

    if side not in ("both", "one"):
        warnings.append("side must be 'both' or 'one'; defaulting to 'both'")
        side = "both"

    # ACI 318-19 Table 6.3.2.1.
    #   Symmetric T-beam (both sides), overhang each side ≤ least of:
    #     8*hf,  sw/2,  ln/8
    #   Flange on one side only (L-beam / edge), overhang ≤ least of:
    #     6*hf,  sw/2,  ln/12
    sw = spacing_in - bw  # clear distance to adjacent web
    if side == "both":
        overhang_each = min(8 * hf, sw / 2, span_in / 8)
        be = bw + 2 * overhang_each
    else:  # L-beam / one side only
        overhang_each = min(6 * hf, sw / 2, span_in / 12)
        be = bw + overhang_each

    return {
        "be_in": be,
        "overhang_in": be - bw,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. Short tied/spiral column axial capacity + uniaxial P-M interaction
# ---------------------------------------------------------------------------

def column_axial(
    b: float,
    h: float,
    Ast: float,
    fc_psi: float,
    fy_psi: float,
    *,
    column_type: str = "tied",
) -> dict[str, Any]:
    """ACI 318-19 §22.4.2 — short column maximum axial load capacity.

    Parameters (US-customary, inches / psi)
    ----------
    b           : column width (in)
    h           : column depth (in)
    Ast         : total longitudinal steel area (in²)
    fc_psi      : f'c (psi)
    fy_psi      : fy (psi)
    column_type : 'tied' (default) or 'spiral'

    Returns
    -------
    dict with keys:
      Ag_in2        — gross cross-sectional area (in²)
      Pn_kip        — nominal axial capacity (kip)
      phi_Pn_kip    — design axial capacity (kip); φ = 0.80 (tied) / 0.85 (spiral)
      phi           — strength-reduction factor
      rho_g         — gross steel ratio Ast/Ag
      rho_min       — ACI minimum (0.01)
      rho_max       — ACI maximum (0.08)
      warnings      — list[str]
    """
    warnings: list[str] = []
    Ag = b * h
    rho_g = Ast / Ag

    if rho_g < 0.01:
        warnings.append(
            f"rho_g={rho_g:.4f} < 0.01: ACI 318-19 §10.6.1.1 minimum not met"
        )
    if rho_g > 0.08:
        warnings.append(
            f"rho_g={rho_g:.4f} > 0.08: ACI 318-19 §10.6.1.1 maximum exceeded"
        )

    # ACI 318-19 Eq. (22.4.2.2) / (22.4.2.3)
    Pn = 0.85 * fc_psi * (Ag - Ast) + fy_psi * Ast  # lb
    Pn_kip = Pn / 1000.0

    if column_type == "spiral":
        phi = 0.75
        # Factor 0.85 per ACI Table 22.4.2.1 for spiral
        phi_Pn_kip = phi * 0.85 * Pn_kip
    else:
        phi = 0.65
        # Factor 0.80 per ACI Table 22.4.2.1 for tied
        phi_Pn_kip = phi * 0.80 * Pn_kip

    return {
        "Ag_in2": Ag,
        "Pn_kip": Pn_kip,
        "phi_Pn_kip": phi_Pn_kip,
        "phi": phi,
        "rho_g": rho_g,
        "rho_min": 0.01,
        "rho_max": 0.08,
        "warnings": warnings,
    }


def column_pm_interaction(
    b: float,
    h: float,
    d: float,
    d_prime: float,
    As_top: float,
    As_bot: float,
    fc_psi: float,
    fy_psi: float,
    *,
    column_type: str = "tied",
    n_points: int = 20,
) -> dict[str, Any]:
    """ACI 318-19 uniaxial P-M interaction diagram for rectangular column.

    Parameters (US-customary, inches / psi)
    ----------
    b           : column width (in)
    h           : column height/depth (in)
    d           : depth to tension steel (bottom layer) (in)
    d_prime     : depth to compression steel (top layer) (in)
    As_top      : compression-side steel area (in²)
    As_bot      : tension-side steel area (in²)
    fc_psi      : f'c (psi)
    fy_psi      : fy (psi)
    column_type : 'tied' (default) or 'spiral'
    n_points    : number of points on the interaction diagram (default 20)

    Returns
    -------
    dict with keys:
      points         — list of {"phi_Pn_kip": ..., "phi_Mn_kipin": ...,
                                "zone": ..., "eps_t": ...}
                        (n_points + 2 entries from pure axial to pure bending)
      phi_Po_kip     — design pure axial capacity (kip)
      phi_Mn0_kipin  — design pure bending capacity (kip·in) at Pu=0
      warnings       — list[str]

    Notes
    -----
    The diagram is generated by sweeping neutral-axis depth c from ∞ (pure
    axial) down to the balanced point and beyond to pure flexure.  Each point
    gives Pn and Mn from statics; φ is applied per ACI §21.2.2.  The
    slender-column warning is raised if h > 22 in (indicative only — proper
    slenderness check requires effective length and bracing info).
    """
    warnings: list[str] = []
    if h > 22:
        warnings.append(
            "slender-column: h > 22 in; verify slenderness (ACI 318-19 §6.2.5) "
            "and apply moment magnification if needed"
        )

    Ag = b * h
    beta1 = _beta1(fc_psi)
    Es = 29_000_000.0  # psi

    phi_col = 0.65 if column_type == "tied" else 0.75

    # Pure axial (c = ∞)
    Pn_max = 0.85 * fc_psi * (Ag - As_top - As_bot) + fy_psi * (As_top + As_bot)
    Pn_max_kip = Pn_max / 1000.0
    k_axial = 0.85 if column_type == "spiral" else 0.80
    phi_Po_kip = phi_col * k_axial * Pn_max_kip

    points = []

    # Sweep c from h (large compression) down to near 0 (tension-controlled)
    c_max = h  # full depth — all concrete in compression
    c_min = 0.01 * d  # essentially pure bending

    for i in range(n_points + 1):
        t = i / n_points  # 0 → large c (axial), 1 → small c (flexure)
        c = c_max * (1 - t) + c_min * t

        a = min(beta1 * c, h)

        # Stress in top steel (compression side, depth d')
        eps_top = 0.003 * (c - d_prime) / c
        fs_top = max(min(eps_top * Es, fy_psi), -fy_psi)

        # Stress in bottom steel (tension side, depth d)
        eps_bot = 0.003 * (c - d) / c
        fs_bot = max(min(eps_bot * Es, fy_psi), -fy_psi)

        # Concrete force (compression positive)
        Cc = 0.85 * fc_psi * b * a  # lb
        # Steel forces (+ = compression)
        Fs_top = As_top * fs_top - 0.85 * fc_psi * As_top  # subtract displaced concrete
        Fs_bot = As_bot * fs_bot

        Pn = (Cc + Fs_top + Fs_bot) / 1000.0  # kip

        # Moments about centroid (h/2)
        yc = h / 2 - a / 2  # concrete force arm from centroid
        y_top = h / 2 - d_prime  # top steel arm
        y_bot = d - h / 2  # bottom steel arm

        Mn = (Cc * yc + As_top * fs_top * y_top - 0.85 * fc_psi * As_top * y_top
              + As_bot * fs_bot * y_bot) / 1000.0  # kip·in
        Mn = abs(Mn)

        # Net tensile strain for φ
        eps_t = 0.003 * (d - c) / c
        phi, zone = _phi_flexure(eps_t)
        # For compression (Pn > 0) columns, φ is bounded by column φ
        phi_eff = max(phi_col, phi) if Pn > 0 else phi
        # Actually ACI 318-19 §21.2.2 transitions from φ_col at ε_t=0.002
        # to φ_flexure at ε_t=0.005. Already handled by _phi_flexure + clamp:
        phi_eff = phi_col + (phi - phi_col) * min(max(
            (eps_t - 0.002) / (0.005 - 0.002), 0.0), 1.0)

        phi_Pn = phi_eff * Pn
        phi_Mn = phi_eff * Mn

        points.append({
            "phi_Pn_kip": phi_Pn,
            "phi_Mn_kipin": phi_Mn,
            "zone": zone,
            "eps_t": eps_t,
        })

    # Pure bending point (P = 0) using beam_flexure
    bf = beam_flexure(b, d, As_bot, fc_psi, fy_psi,
                      As_prime=As_top, d_prime=d_prime)
    phi_Mn0_kipin = bf["phi_Mn_kipin"]
    points.append({
        "phi_Pn_kip": 0.0,
        "phi_Mn_kipin": phi_Mn0_kipin,
        "zone": bf["zone"],
        "eps_t": bf["eps_t"],
    })

    return {
        "points": points,
        "phi_Po_kip": phi_Po_kip,
        "phi_Mn0_kipin": phi_Mn0_kipin,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 6. Development length
# ---------------------------------------------------------------------------

def development_length(
    db_in: float,
    fc_psi: float,
    fy_psi: float,
    *,
    coating: str = "uncoated",
    position: str = "other",
    confinement: str = "other",
    cover_in: float = 0.0,
    spacing_in: float = 0.0,
    cb_in: float = 0.0,
    Ktr: float = 0.0,
) -> dict[str, Any]:
    """ACI 318-19 §25.4.2 tension development length for deformed bars.

    Parameters (US-customary)
    ----------
    db_in       : bar diameter (in); use 0.375 for #3, 0.5 for #4, etc.
    fc_psi      : f'c (psi)
    fy_psi      : fy (psi)
    coating     : 'uncoated' (default) or 'epoxy'
    position    : 'top' (horizontal bar with >12 in fresh concrete below)
                  or 'other' (default)
    confinement : 'confined' (cb+Ktr)/db >= 2.5 or 'other' (default)
    cover_in    : side cover or half spacing to next bar (in); used for (cb+Ktr)/db
    spacing_in  : clear spacing between bars (in); used for (cb+Ktr)/db
    cb_in       : smaller of cover or half c/c spacing (in); if 0, uses cover_in
    Ktr         : transverse reinforcement index Atr*fyt/(1500*s*n); default 0

    Returns
    -------
    dict with keys:
      ld_in         — required development length (in)
      ld_db_ratio   — ld / db
      psi_t         — top bar factor
      psi_e         — epoxy coating factor
      cb_Ktr_db     — (cb+Ktr)/db confinement term (capped at 2.5)
      warnings      — list[str]

    Notes
    -----
    ACI 318-19 Eq. (25.4.2.4a):
      ld/db = (3/40) * (fy/(λ*√f'c)) * (ψt*ψe*ψs*ψg) / ((cb+Ktr)/db)
    λ = 1.0 (normal-weight concrete).  ψs=1.0, ψg=1.0 assumed (conservative).
    Minimum ld = max(300 mm, 12 in) per ACI §25.4.2.1 (using 12 in).
    """
    warnings: list[str] = []
    lam = 1.0  # normal weight

    psi_t = 1.3 if position == "top" else 1.0
    if coating == "epoxy":
        psi_e = 1.5 if cover_in < 3 * db_in or spacing_in < 6 * db_in else 1.2
    else:
        psi_e = 1.0

    psi_te = psi_t * psi_e
    if psi_te > 1.7:
        psi_te = 1.7
        warnings.append("ψt·ψe capped at 1.7 per ACI §25.4.2.4")

    psi_s = 1.0  # conservative
    psi_g = 1.0  # assume Grade 60 (fy ≤ 60,000 psi handles via fy term)

    cb = cb_in if cb_in > 0 else min(cover_in, spacing_in / 2) if spacing_in > 0 else cover_in
    cb_Ktr_db = (cb + Ktr) / db_in if db_in > 0 else 2.5
    cb_Ktr_db = min(cb_Ktr_db, 2.5)
    if cb_Ktr_db < 1.0:
        cb_Ktr_db = 1.0  # ACI minimum denominator

    sqrt_fc = min(math.sqrt(fc_psi), math.sqrt(10000))  # ACI cap at √10,000

    ld_db = (3.0 / 40.0) * (fy_psi / (lam * sqrt_fc)) * (psi_te * psi_s * psi_g) / cb_Ktr_db
    ld_in = max(ld_db * db_in, 12.0)

    return {
        "ld_in": ld_in,
        "ld_db_ratio": ld_in / db_in,
        "psi_t": psi_t,
        "psi_e": psi_e,
        "cb_Ktr_db": cb_Ktr_db,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. One-way slab thickness & steel
# ---------------------------------------------------------------------------

def slab_one_way(
    span_in: float,
    fc_psi: float,
    fy_psi: float,
    wu_psf: float,
    *,
    condition: str = "simply-supported",
    b_in: float = 12.0,
) -> dict[str, Any]:
    """ACI 318-19 §7.3.1 one-way slab minimum thickness & required steel.

    Parameters (US-customary)
    ----------
    span_in     : clear span (in)
    fc_psi      : f'c (psi)
    fy_psi      : fy (psi)
    wu_psf      : factored uniform load (psf = lb/ft²)
    condition   : 'simply-supported' (default), 'one-end-continuous',
                  'both-ends-continuous', 'cantilever'
    b_in        : design strip width (in); default 12 in (per-foot strip)

    Returns
    -------
    dict with keys:
      h_min_in      — ACI minimum slab thickness (in)
      d_in          — assumed effective depth (h - 1.0 in cover) (in)
      Mu_kipin      — factored moment (kip·in) for the design strip
      As_req_in2    — required steel per b_in strip (in²)
      As_min_in2    — ACI minimum (0.0018*b*h for fy=60 ksi) (in²)
      warnings      — list[str]

    Notes
    -----
    ACI Table 7.3.1.1 minimum thickness factors (for fy=60,000 psi):
      simply-supported: L/20,  one-end: L/24,  both-ends: L/28, cantilever: L/10
    Modified for fy ≠ 60 ksi per ACI §7.3.1.1.1: multiply by (0.4 + fy/100000).
    """
    warnings: list[str] = []

    _factors = {
        "simply-supported": 20,
        "one-end-continuous": 24,
        "both-ends-continuous": 28,
        "cantilever": 10,
    }
    factor = _factors.get(condition, 20)
    if condition not in _factors:
        warnings.append(f"unknown condition '{condition}'; using simply-supported")

    # ACI §7.3.1.1.1 fy modifier
    fy_mod = 0.4 + fy_psi / 100_000.0
    h_min_in = (span_in / factor) * fy_mod
    h_min_in = max(h_min_in, 3.5)  # ACI §7.3.1.1 absolute min ≈ 3.5 in

    d_in = h_min_in - 1.0  # 0.75 in cover + ~0.25 in bar radius

    # Factored moment (simple span approximation wu*L²/8 for simply supported,
    # wu*L²/16 for continuous ends)
    L_ft = span_in / 12.0
    wu_klf = wu_psf * b_in / 12.0 / 1000.0  # kip/ft for b_in strip
    if condition == "both-ends-continuous":
        Mu_kipft = wu_klf * L_ft**2 / 16.0
    elif condition == "one-end-continuous":
        Mu_kipft = wu_klf * L_ft**2 / 10.0
    elif condition == "cantilever":
        Mu_kipft = wu_klf * L_ft**2 / 2.0
    else:
        Mu_kipft = wu_klf * L_ft**2 / 8.0
    Mu_kipin = Mu_kipft * 12.0

    req = beam_required_As(b_in, d_in, Mu_kipin, fc_psi, fy_psi)
    As_req = req["As_req_in2"]

    # ACI §7.6.1.1 minimum shrinkage/temperature steel (fy=60 ksi → 0.0018*Ag)
    rho_temp = 0.0018 * 60_000 / fy_psi
    As_min = rho_temp * b_in * h_min_in

    As_req = max(As_req, As_min)

    return {
        "h_min_in": h_min_in,
        "d_in": d_in,
        "Mu_kipin": Mu_kipin,
        "As_req_in2": As_req,
        "As_min_in2": As_min,
        "warnings": warnings + req.get("warnings", []),
    }


# ---------------------------------------------------------------------------
# 8. Immediate deflection (Branson effective moment of inertia + crack control)
# ---------------------------------------------------------------------------

def immediate_deflection(
    b: float,
    h: float,
    d: float,
    As: float,
    fc_psi: float,
    fy_psi: float,
    Ma_kipin: float,
    span_in: float,
    *,
    load_condition: str = "midspan",
    n_bars: int = 1,
    Es_psi: float = 29_000_000.0,
) -> dict[str, Any]:
    """Immediate (short-term) deflection using Branson's Ie (ACI 318-19 §24.2.3).

    Parameters (US-customary, inches / psi)
    ----------
    b           : beam width (in)
    h           : total section depth (in)
    d           : effective depth (in)
    As          : tension steel area (in²)
    fc_psi      : f'c (psi)
    fy_psi      : fy (psi)
    Ma_kipin    : maximum service moment (kip·in)
    span_in     : span length (in)
    load_condition : 'midspan' (default, uses coefficient 5/384)
                    or 'cantilever' (1/8)
    n_bars      : number of tension bars (for crack spacing calculation)
    Es_psi      : steel modulus (psi)

    Returns
    -------
    dict with keys:
      Ig_in4        — gross moment of inertia (in⁴)
      Icr_in4       — cracked transformed moment of inertia (in⁴)
      Mcr_kipin     — cracking moment (kip·in)
      Ie_in4        — Branson effective Ie (in⁴)
      Ec_psi        — concrete modulus (psi)
      delta_in      — immediate deflection (in)
      delta_L_ratio — span/deflection ratio
      warnings      — list[str]

    Notes
    -----
    Branson: Ie = (Mcr/Ma)³*Ig + [1-(Mcr/Ma)³]*Icr  ≤ Ig
    Ec = 57,000*√f'c (ACI §19.2.2.1, normal-weight concrete).
    Cracked Icr uses transformed section (modular ratio n = Es/Ec).
    """
    warnings: list[str] = []

    Ec = 57_000 * math.sqrt(fc_psi)  # ACI Eq. (19.2.2.1b) psi
    n_ratio = Es_psi / Ec  # modular ratio

    Ig = b * h**3 / 12.0
    fr = 7.5 * math.sqrt(fc_psi)  # ACI §19.2.3.1 psi
    yt = h / 2.0
    Mcr_lbin = fr * Ig / yt
    Mcr_kipin = Mcr_lbin / 1000.0

    # Cracked transformed section — locate neutral axis
    # b*kd²/2 = n*As*(d - kd)
    # → b/2 * kd² + n*As*kd - n*As*d = 0
    A_q = b / 2.0
    B_q = n_ratio * As
    C_q = -n_ratio * As * d
    disc = B_q**2 - 4 * A_q * C_q
    kd = (-B_q + math.sqrt(disc)) / (2 * A_q)
    Icr = b * kd**3 / 3.0 + n_ratio * As * (d - kd)**2

    Ma_lbin = Ma_kipin * 1000.0
    if Ma_lbin <= 0:
        Ma_lbin = 1.0  # avoid division by zero
        warnings.append("Ma_kipin <= 0: deflection forced to zero")

    ratio = min(Mcr_lbin / Ma_lbin, 1.0)
    Ie = ratio**3 * Ig + (1 - ratio**3) * Icr
    Ie = min(Ie, Ig)

    if load_condition == "cantilever":
        coef = 1.0 / 8.0
    else:
        coef = 5.0 / 384.0
        if load_condition != "midspan":
            warnings.append(f"unknown load_condition '{load_condition}'; using midspan (5/384)")

    # Uniform load deflection: Δ = coef * w * L^4 / (Ec * Ie)
    # But we have Ma_kipin as input, not w directly.
    # For midspan uniform: Ma ≈ w*L²/8 → w = 8*Ma/L²
    # For cantilever uniform: Ma = w*L²/2 → w = 2*Ma/L²
    if load_condition == "cantilever":
        w_lb_in = Ma_lbin * 2.0 / span_in**2
    else:
        w_lb_in = Ma_lbin * 8.0 / span_in**2
    delta_in = coef * w_lb_in * span_in**4 / (Ec * Ie)
    delta_L_ratio = span_in / delta_in if delta_in > 0 else float("inf")

    # ACI limit check L/240 (immediate) or L/360 (live only)
    if delta_L_ratio < 240:
        warnings.append(
            f"deflection L/{delta_L_ratio:.0f} < L/240 (ACI §24.2.2 limit for "
            "immediate total load)"
        )

    return {
        "Ig_in4": Ig,
        "Icr_in4": Icr,
        "Mcr_kipin": Mcr_kipin,
        "Ie_in4": Ie,
        "Ec_psi": Ec,
        "delta_in": delta_in,
        "delta_L_ratio": delta_L_ratio,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 9. Crack control (z-factor / bar spacing) — ACI 318-99 / Gergely-Lutz
# ---------------------------------------------------------------------------

def crack_control(
    b: float,
    h: float,
    d: float,
    As: float,
    fc_psi: float,
    fy_psi: float,
    n_bars: int,
    Ms_kipin: float,
    *,
    cover_in: float = 1.5,
    Es_psi: float = 29_000_000.0,
) -> dict[str, Any]:
    """ACI 318-19 §24.3 crack-control bar spacing (replaces z-factor).

    Parameters (US-customary)
    ----------
    b           : beam width (in)
    h           : total depth (in)
    d           : effective depth (in)
    As          : tension steel area (in²)
    fc_psi      : f'c (psi)
    fy_psi      : fy (psi)
    n_bars      : number of tension bars
    Ms_kipin    : service (unfactored) moment (kip·in)
    cover_in    : clear cover to tension steel (in); default 1.5 in
    Es_psi      : steel modulus (psi)

    Returns
    -------
    dict with keys:
      fs_psi        — service steel stress (psi) from cracked-section analysis
      s_provided_in — actual bar spacing (in) = (b - 2*cover - db) / (n_bars-1)
      s_max_in      — ACI §24.3.2 maximum bar spacing (in)
      z_factor      — Gergely-Lutz z = fs*(dc*A)^(1/3) [kip/in]
      adequate      — bool: fs < (2/3)*fy and s_provided <= s_max
      warnings      — list[str]

    Notes
    -----
    ACI 318-19 §24.3.2 Eq. (24.3.2):
      s ≤ 15*(40,000/fs) − 2.5*cc  ≤  12*(40,000/fs)
    where fs = service steel stress (psi), cc = clear cover (in).
    Gergely-Lutz z ≤ 175 kip/in (interior), 145 kip/in (exterior) per ACI 318-99.
    """
    warnings: list[str] = []

    Ec = 57_000 * math.sqrt(fc_psi)
    n_ratio = Es_psi / Ec

    # Neutral axis (cracked)
    A_q = b / 2.0
    B_q = n_ratio * As
    C_q = -n_ratio * As * d
    disc = B_q**2 - 4 * A_q * C_q
    kd = (-B_q + math.sqrt(disc)) / (2 * A_q)
    Icr = b * kd**3 / 3.0 + n_ratio * As * (d - kd)**2

    Ms_lbin = Ms_kipin * 1000.0
    fs_psi = n_ratio * Ms_lbin * (d - kd) / Icr

    # ACI §24.3.2 maximum bar spacing
    cc = cover_in
    if fs_psi > 0:
        s_max_1 = 15.0 * (40_000 / fs_psi) - 2.5 * cc
        s_max_2 = 12.0 * (40_000 / fs_psi)
        s_max_in = min(s_max_1, s_max_2)
    else:
        s_max_in = float("inf")

    # Approximate bar diameter from As / n_bars
    db_approx = math.sqrt(4 * As / (n_bars * math.pi)) if n_bars > 0 else 0.5
    if n_bars > 1:
        s_provided_in = (b - 2 * cc - db_approx) / (n_bars - 1)
    else:
        s_provided_in = b - 2 * cc

    # Gergely-Lutz z-factor
    dc = cover_in + db_approx / 2.0
    A_bar = 2 * dc * b / n_bars if n_bars > 0 else b
    z_factor = fs_psi / 1000.0 * (dc * A_bar) ** (1 / 3)

    if fs_psi > (2 / 3) * fy_psi:
        warnings.append(
            f"spacing-violation: service stress fs={fs_psi:.0f} psi > (2/3)fy="
            f"{(2/3)*fy_psi:.0f} psi; check service load levels"
        )

    if s_provided_in > s_max_in:
        warnings.append(
            f"spacing-violation: bar spacing={s_provided_in:.2f} in > "
            f"s_max={s_max_in:.2f} in (ACI §24.3.2)"
        )

    if z_factor > 175:
        warnings.append(
            f"z={z_factor:.1f} kip/in > 175 kip/in (ACI 318-99 interior limit)"
        )

    adequate = fs_psi <= (2 / 3) * fy_psi and s_provided_in <= s_max_in

    return {
        "fs_psi": fs_psi,
        "s_provided_in": s_provided_in,
        "s_max_in": s_max_in,
        "z_factor": z_factor,
        "adequate": adequate,
        "warnings": warnings,
    }
