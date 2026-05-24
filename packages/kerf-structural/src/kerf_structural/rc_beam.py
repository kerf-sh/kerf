"""
ACI 318 rectangular RC beam design — tension steel for flexure.

Design method: strength-design (USD) using the ACI R-method (R_n approach).
All inputs in US customary units (kips, inches, kip-ft, psi).

References
----------
ACI 318-19 §22.2, §9.3, §9.6, §25.2
Wight, J.K. — "Reinforced Concrete: Mechanics and Design", 8th ed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Canonical ACI 318-19 helpers live in kerf-cad-core — import from there to
# avoid duplication.  kerf-cad-core is the low-level base layer that all CAD
# compute plugins share.
from kerf_cad_core.concrete.design import (
    _beta1,
    beam_flexure as _beam_flexure,
)


@dataclass
class RCBeamResult:
    """Output from :func:`design_rc_beam`."""
    ok: bool
    reason: str = ""

    # Geometry
    b: float = 0.0          # beam width  (in)
    h: float = 0.0          # total depth (in)
    d: float = 0.0          # effective depth (in)

    # Materials
    fc: float = 0.0         # f'c (psi)
    fy: float = 0.0         # fy  (psi)

    # Design
    Mu: float = 0.0         # factored moment (kip-in)
    Rn: float = 0.0         # nominal moment coefficient  Mu/(phi b d^2)  (psi)
    rho: float = 0.0        # required steel ratio
    rho_min: float = 0.0    # ACI 318 minimum steel ratio
    rho_max: float = 0.0    # ACI 318 maximum steel ratio (eps_t >= 0.004)
    As_required: float = 0.0  # required steel area (in^2)
    phi: float = 0.9        # strength-reduction factor (tension-controlled)
    beta1: float = 0.85     # ACI stress-block factor


# ─────────────────────────────────────────────────────────────────────────────
# _beta1 is re-exported from kerf_cad_core.concrete.design (imported above).
# The local definition has been removed to eliminate the true code duplicate.


def design_rc_beam(
    b: float,
    h: float,
    Mu_kip_ft: float,
    *,
    fc: float = 4_000.0,
    fy: float = 60_000.0,
    cover: float = 1.5,
    stirrup_dia: float = 0.375,
    bar_dia: float = 0.625,
    phi: float = 0.9,
) -> RCBeamResult:
    """
    Required tension steel area for a singly-reinforced rectangular beam.

    Parameters
    ----------
    b : float
        Beam width (in).
    h : float
        Total beam depth (in).
    Mu_kip_ft : float
        Factored moment demand (kip-ft).
    fc : float
        Concrete compressive strength f'c (psi). Default 4 000 psi.
    fy : float
        Steel yield strength (psi). Default 60 000 psi.
    cover : float
        Clear cover to stirrups (in). Default 1.5 in.
    stirrup_dia : float
        Stirrup bar diameter (in). Default 0.375 in (#3).
    bar_dia : float
        Longitudinal bar diameter for d estimation (in). Default 0.625 in (#5).
    phi : float
        Strength-reduction factor. Default 0.90 (tension-controlled).

    Returns
    -------
    RCBeamResult
        Design summary including As_required, rho, rho_min, rho_max.
    """
    res = RCBeamResult(ok=False, b=b, h=h, fc=fc, fy=fy, phi=phi)

    # Validate
    if b <= 0 or h <= 0:
        res.reason = "b and h must be positive"
        return res
    if fc <= 0 or fy <= 0:
        res.reason = "fc and fy must be positive"
        return res
    if Mu_kip_ft <= 0:
        res.reason = "Mu must be positive"
        return res

    # Effective depth
    d = h - cover - stirrup_dia - bar_dia / 2.0
    if d <= 0:
        res.reason = "Effective depth d <= 0 — check cover / bar sizes vs h"
        return res
    res.d = d

    # Convert moment to kip-in
    Mu = Mu_kip_ft * 12.0
    res.Mu = Mu

    # ACI R-method  Rn = Mu / (φ b d²)
    Rn = Mu * 1_000.0 / (phi * b * d * d)   # psi  (Mu in kip-in → * 1000 → lb-in)
    res.Rn = Rn

    # β₁
    b1 = _beta1(fc)
    res.beta1 = b1

    # Discriminant check: cannot be over-reinforced in the pure-R sense
    discriminant = 1.0 - 2.0 * Rn / (0.85 * fc)
    if discriminant < 0:
        res.reason = (
            f"Beam is over-reinforced for given dimensions "
            f"(discriminant={discriminant:.4f}). Increase b, d, or reduce Mu."
        )
        return res

    # Required steel ratio
    rho = (0.85 * fc / fy) * (1.0 - math.sqrt(discriminant))
    res.rho = rho

    # ρ_min — ACI 318-19 §9.6.1.2
    rho_min = max(3.0 * math.sqrt(fc) / fy, 200.0 / fy)
    res.rho_min = rho_min

    # ρ_max — ACI 318-19: net tensile strain εt ≥ 0.004 (§9.3.3.1)
    eps_cu = 0.003
    eps_t_min = 0.004
    rho_max = 0.85 * b1 * fc / fy * (eps_cu / (eps_cu + eps_t_min))
    res.rho_max = rho_max

    # Govern by minimum
    rho_design = max(rho, rho_min)

    # Check maximum
    if rho_design > rho_max:
        res.reason = (
            f"Required ρ={rho_design:.6f} exceeds ρ_max={rho_max:.6f} "
            f"(net tensile strain < 0.004). Increase section size."
        )
        res.As_required = rho_design * b * d
        return res

    As = rho_design * b * d
    res.As_required = As
    res.rho = rho_design
    res.ok = True
    return res


def check_rc_beam(
    b: float,
    h: float,
    As: float,
    *,
    fc: float = 4_000.0,
    fy: float = 60_000.0,
    cover: float = 1.5,
    stirrup_dia: float = 0.375,
    bar_dia: float = 0.625,
    phi: float = 0.9,
) -> dict:
    """
    Compute the design moment capacity φMn for a given steel area.

    Delegates to :func:`kerf_cad_core.concrete.design.beam_flexure` — the
    canonical ACI 318-19 singly-reinforced beam flexural analysis routine.

    Returns
    -------
    dict with keys: ok, phi_Mn_kip_ft, Mn_kip_ft, a, c, epsilon_t, phi
    """
    d = h - cover - stirrup_dia - bar_dia / 2.0
    if d <= 0 or b <= 0 or As <= 0:
        return {"ok": False, "reason": "Invalid geometry or As"}

    # Delegate to canonical implementation (kerf_cad_core.concrete.design)
    core = _beam_flexure(b, d, As, fc, fy)

    # Translate core result keys → kerf-structural's public dict shape.
    # kerf-structural returns Mn/phiMn in kip-ft; core uses kip-in.
    return {
        "ok": True,
        "phi_Mn_kip_ft": core["phi_Mn_kipin"] / 12.0,
        "Mn_kip_ft": core["Mn_kipin"] / 12.0,
        "a": core["a_in"],
        "c": core["c_in"],
        "epsilon_t": core["eps_t"],
        "phi": core["phi"],
    }
