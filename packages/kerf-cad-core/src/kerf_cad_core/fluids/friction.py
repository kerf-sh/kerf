"""
kerf_cad_core.fluids.friction — Canonical Darcy-Weisbach friction factor.

Single authoritative implementation used by all piping / duct / fluid-power
pressure-drop calculations in kerf-cad-core.

Public API
----------
darcy_friction_factor(reynolds, rel_roughness) -> float
    Returns the Darcy (Moody) friction factor f.

Algorithm
---------
  Re < 2300         — Laminar:   f = 64 / Re
  2300 ≤ Re < 4000  — Transition: linearly blended between the laminar value
                      at Re = 2300 and the turbulent value at Re = 4000.
  Re ≥ 4000         — Turbulent: Colebrook-White equation iterated to
                      convergence (tol 1e-10); seeded by Swamee-Jain (1976)
                      explicit approximation.

Colebrook-White (Moody 1944, J. Fluids Eng. 66(8)):
    1/√f = -2 log₁₀( ε/(3.7 D) + 2.51/(Re √f) )

Swamee-Jain (1976) seed (ASCE J. Hydraul. Div. 102(5)):
    f₀ = 0.25 / [log₁₀(ε/(3.7D) + 5.74/Re⁰·⁹)]²
    Accuracy: ±3% vs Colebrook-White in turbulent range.

For smooth pipes (rel_roughness = 0) the Filonenko (1954) formula is used
as the turbulent seed:
    f₀ = (0.790 ln Re − 1.64)⁻²

References
----------
Moody, L.F. (1944) "Friction factors for pipe flow". Trans. ASME 66(8):671–684.
Colebrook, C.F. (1939) "Turbulent flow in pipes". J. Inst. Civil Eng. 11:133–156.
Swamee, P.K. & Jain, A.K. (1976) "Explicit equations for pipe-flow problems".
    ASCE J. Hydraul. Div. 102(5):657–664.
Filonenko, G.K. (1954) "Hydraulic resistance in pipes". Teploenergetika 1(4):40–44.
White, F.M. (2016) Fluid Mechanics, 8th ed. McGraw-Hill.

Author: imranparuk
"""

from __future__ import annotations

import math

# Convergence parameters
_TOL = 1e-10
_MAX_ITER = 200

# Transition-zone boundaries
_RE_LAMINAR_MAX = 2300.0
_RE_TURBULENT_MIN = 4000.0


def darcy_friction_factor(reynolds: float, rel_roughness: float) -> float:
    """Return the Darcy-Weisbach (Moody) friction factor f.

    Parameters
    ----------
    reynolds : float
        Reynolds number Re = ρ v D / μ.  Must be > 0.
    rel_roughness : float
        Relative pipe roughness ε/D (dimensionless).  Must be ≥ 0.
        For a smooth pipe pass 0.0.

    Returns
    -------
    float
        Darcy friction factor f (dimensionless).  Always > 0.

    Raises
    ------
    ValueError
        If reynolds ≤ 0 or rel_roughness < 0 or either is not finite.

    Examples
    --------
    Laminar:
        >>> darcy_friction_factor(1000, 0.0)
        0.064

    Fully turbulent (rough pipe, Re → ∞ limit from Moody chart):
        >>> import math
        >>> f_rough = 1 / (-2 * math.log10(0.05 / 3.7)) ** 2  # ≈ 0.0723
    """
    # --- Input guards ---
    reynolds = float(reynolds)
    rel_roughness = float(rel_roughness)

    if not math.isfinite(reynolds):
        raise ValueError(f"reynolds must be finite, got {reynolds}")
    if reynolds <= 0:
        raise ValueError(f"reynolds must be > 0, got {reynolds}")
    if not math.isfinite(rel_roughness):
        raise ValueError(f"rel_roughness must be finite, got {rel_roughness}")
    if rel_roughness < 0:
        raise ValueError(f"rel_roughness must be >= 0, got {rel_roughness}")

    # --- Laminar regime ---
    if reynolds < _RE_LAMINAR_MAX:
        return 64.0 / reynolds

    # --- Turbulent regime ---
    if reynolds >= _RE_TURBULENT_MIN:
        return _turbulent(reynolds, rel_roughness)

    # --- Transition zone (2300 ≤ Re < 4000): linear blend ---
    f_lam = 64.0 / _RE_LAMINAR_MAX
    f_turb = _turbulent(_RE_TURBULENT_MIN, rel_roughness)
    blend = (reynolds - _RE_LAMINAR_MAX) / (_RE_TURBULENT_MIN - _RE_LAMINAR_MAX)
    return f_lam + blend * (f_turb - f_lam)


def _turbulent(re: float, eps_d: float) -> float:
    """Colebrook-White friction factor for Re ≥ 4000, converged iteratively."""
    # Seed: Filonenko for smooth pipes, Swamee-Jain for rough
    if eps_d == 0.0:
        # Smooth pipe: Filonenko seed
        ln_re = math.log(re)
        denom = 0.790 * ln_re - 1.640
        if denom <= 0:
            f = 0.02
        else:
            f = denom ** -2
    else:
        # Swamee-Jain explicit approximation
        term = eps_d / 3.7 + 5.74 / (re ** 0.9)
        if term <= 0:
            f = 0.02
        else:
            log_term = math.log10(term)
            if log_term == 0:
                f = 0.02
            else:
                f = 0.25 / log_term ** 2

    # Colebrook-White fixed-point iteration: f_{n+1} = 1/(-2 log10(ε/(3.7D) + 2.51/(Re√f)))²
    for _ in range(_MAX_ITER):
        sqrt_f = math.sqrt(max(f, 1e-16))
        inner = eps_d / 3.7 + 2.51 / (re * sqrt_f)
        if inner <= 0:
            break
        rhs = -2.0 * math.log10(inner)
        if rhs == 0:
            break
        f_new = 1.0 / rhs ** 2
        if abs(f_new - f) < _TOL:
            return f_new
        f = f_new

    return f
