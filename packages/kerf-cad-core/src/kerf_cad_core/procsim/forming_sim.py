"""
kerf_cad_core.procsim.forming_sim
==================================
Sheet metal forming formability simulation — AutoForm direction.

This module is *distinct* from kerf_cad_core.forming.bulk (bulk-forming
calculators).  It models **sheet** formability:

  flc0(n, t)
      Keeler-Goodwin FLC₀ (plane-strain intercept) from strain-hardening
      exponent n and sheet thickness t.

  flc_curve(n, t, n_points)
      Full Forming Limit Curve (FLC) as (ε₁, ε₂) pairs using the
      Keeler-Goodwin model.  Minimum is at plane-strain (ε₂ = 0).

  strain_path(mode, eps1_target, r_aniso)
      Major/minor strain path for deep-draw, stretch, or plane-strain modes.

  safety_margin(eps1, eps2, n, t)
      Distance of a strain point from the FLC; safe / marginal / fail zone
      classification.

  thinning(eps1, eps2)
      Through-thickness thinning strain and thinning percentage (volume
      conservation: ε₃ = −ε₁ − ε₂).

  wrinkling_tendency(eps1, eps2, r_aniso, t, R_die)
      Heuristic wrinkling index for the flange/wall region.

  draw_bead_restraining_force(t, sigma_y, mu, R_bead, w_bead)
      Draw-bead restraining force per unit width (Stoughton model).

  blank_holder_force_window(sigma_y, t, A_blank, A_punch, mu, R_die)
      Blank-holder force window [F_min, F_max] for wrinkle-free & no-fracture.

  limiting_draw_ratio(r_aniso, n)
      Limiting draw ratio (LDR) from the Swift–Hill analytic formula.

  springback(sigma_y, E, t, R_punch, nu)
      Springback: pure-bending ratio Rf/R and sidewall-curl estimate.

  one_step_inverse(profile_coords, t, sigma_y, n, K)
      Section-based one-step inverse strain estimate from a target 2-D part
      profile (list of (x, y) points).

LLM tools (gated on kerf_chat / kerf_core availability):

  run_sheet_flc0                — wrap flc0
  run_sheet_flc_curve           — wrap flc_curve
  run_sheet_strain_path         — wrap strain_path
  run_sheet_safety_margin       — wrap safety_margin
  run_sheet_thinning            — wrap thinning
  run_sheet_wrinkling           — wrap wrinkling_tendency
  run_sheet_draw_bead_force     — wrap draw_bead_restraining_force
  run_sheet_bh_force_window     — wrap blank_holder_force_window
  run_sheet_ldr                 — wrap limiting_draw_ratio
  run_sheet_springback          — wrap springback
  run_sheet_one_step_inverse    — wrap one_step_inverse

Design notes
------------
* Pure Python; no numpy / scipy / external deps.
* All functions return plain dicts:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}
* Functions NEVER raise.

Units (consistent throughout)
------------------------------
  lengths / thickness   — metres (m)
  stress / modulus      — Pascals (Pa)
  force                 — Newtons (N)
  strains               — dimensionless (logarithmic / true)
  dimensionless ratios  — dimensionless

References
----------
Keeler, S.P. (1965). "Determination of Forming Limits in Automotive Stampings."
    SAE Technical Paper 650535.
Goodwin, G.M. (1968). "Application of Strain Analysis to Sheet Metal Forming
    Problems in the Press Shop." SAE Technical Paper 680093.
Swift, H.W. (1952). "Plastic instability under plane stress." J. Mech. Phys.
    Solids 1(1): 1–18.
Hill, R. (1952). "On discontinuous plastic states, with special reference to
    localized necking in thin sheets." J. Mech. Phys. Solids 1(1): 19–30.
Hosford, W.F. & Caddell, R.M. (2011). "Metal Forming: Mechanics and
    Metallurgy", 4th ed. Cambridge University Press.
Stoughton, T.B. (1988). "Model of drawbead forces in sheet metal forming."
    Proc. 15th IDDRG Congress.
Marciniak, Z., Duncan, J.L. & Hu, S.J. (2002). "Mechanics of Sheet Metal
    Forming", 2nd ed. Butterworth-Heinemann.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any, List, Sequence, Tuple
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def flc0(n: float, t: float) -> dict:
    """
    Keeler-Goodwin forming-limit curve intercept FLC₀ (plane-strain major strain).

    The Keeler-Goodwin empirical formula for the plane-strain intercept of the
    FLC (ε₂ = 0) is:

        FLC₀ = (23.3 + 14.13·t_mm) · n / 0.21   [expressed as a fraction]

    where:
      n      — strain-hardening exponent (dimensionless, > 0)
      t_mm   — sheet thickness in millimetres (t_mm = t_m × 1000)
      0.21   — reference n for normalisation (n of mild steel ≈ 0.21)
      23.3   — empirical base intercept (% major strain at t = 0)
      14.13  — thickness sensitivity coefficient (% per mm)

    The result is returned both as a percentage (%) and as a fractional strain.

    Ref: Keeler (1965) + Goodwin (1968); tabulated in Hosford & Caddell §12.2.

    Parameters
    ----------
    n : float
        Strain-hardening exponent.  Must be > 0 (typical 0.10–0.55).
    t : float
        Sheet thickness (m).  Must be > 0.

    Returns
    -------
    dict
        ok              : True
        n               : strain-hardening exponent
        t_m             : sheet thickness (m)
        t_mm            : sheet thickness (mm)
        FLC0_pct        : plane-strain intercept (% major strain)
        FLC0            : plane-strain intercept (fractional true strain)
        warnings        : list
    """
    warnings: list[str] = []

    err = _guard_positive("n", n)
    if err:
        return _err(err)
    err = _guard_positive("t", t)
    if err:
        return _err(err)

    n_v = float(n)
    t_v = float(t)
    t_mm = t_v * 1000.0

    if n_v > 0.60:
        warnings.append(
            f"n={n_v} > 0.60 is outside the typical sheet-steel range; verify input."
        )
    if t_mm > 6.0:
        warnings.append(
            f"t={t_mm:.2f} mm > 6 mm is beyond typical deep-draw sheet; FLC₀ model "
            "may underestimate for thick plate."
        )

    # Keeler-Goodwin: FLC0 (%) = (23.3 + 14.13 * t_mm) * n / 0.21
    flc0_pct = (23.3 + 14.13 * t_mm) * n_v / 0.21
    flc0_frac = flc0_pct / 100.0

    return {
        "ok": True,
        "n": n_v,
        "t_m": t_v,
        "t_mm": t_mm,
        "FLC0_pct": flc0_pct,
        "FLC0": flc0_frac,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 2. flc_curve — full FLC as (ε₁, ε₂) pairs
# ---------------------------------------------------------------------------

def flc_curve(n: float, t: float, n_points: int = 21) -> dict:
    """
    Full Forming Limit Curve (FLC) using the Keeler-Goodwin model.

    The FLC defines the boundary between safe and failed strain states on the
    (ε₂, ε₁) diagram (minor strain on x-axis, major strain on y-axis).

    The curve is constructed in two halves:

    Left half  (ε₂ < 0, drawing side):
        The major strain at the FLC increases linearly with |ε₂|:
            ε₁_FLC = FLC₀ + |ε₂| × (1 + 1/R_eff)
        where R_eff ≈ 1.0 (average normal anisotropy, isotropic approximation).
        Simplification: ε₁_FLC = FLC₀ − ε₂  for ε₂ ∈ [−FLC₀, 0].

    Right half (ε₂ > 0, stretching side):
        The major strain drops as the strain state moves toward equal-biaxial:
            ε₁_FLC = FLC₀ + 0.5 × ε₂   (Goodwin's approximation)
        The curve minimum is at plane-strain (ε₂ = 0, ε₁ = FLC₀).

    Points are sampled uniformly along ε₂ from −FLC₀ to +FLC₀.

    Parameters
    ----------
    n : float
        Strain-hardening exponent.  Must be > 0.
    t : float
        Sheet thickness (m).  Must be > 0.
    n_points : int
        Number of (ε₂, ε₁) points to return (default 21, must be >= 3).

    Returns
    -------
    dict
        ok          : True
        n           : strain-hardening exponent
        t_m         : sheet thickness (m)
        FLC0        : plane-strain intercept (fractional true strain)
        curve       : list of {"eps2": float, "eps1_flc": float} dicts
        minimum_eps1: FLC minimum = FLC₀ at plane-strain
        plane_strain_eps2: 0.0 (always)
        warnings    : list
    """
    warnings: list[str] = []

    if not isinstance(n_points, int) or n_points < 3:
        return _err(f"n_points must be an integer >= 3, got {n_points!r}")

    r0 = flc0(n, t)
    if not r0["ok"]:
        return r0

    f0 = r0["FLC0"]
    warnings.extend(r0["warnings"])

    # Build ε₂ array: from −FLC₀ to +FLC₀
    eps2_min = -f0
    eps2_max = f0
    step = (eps2_max - eps2_min) / (n_points - 1)

    curve: list[dict] = []
    for i in range(n_points):
        e2 = eps2_min + i * step
        if e2 <= 0.0:
            # Left half (drawing side): ε₁ = FLC₀ − ε₂
            e1 = f0 - e2
        else:
            # Right half (stretching): ε₁ = FLC₀ + 0.5·ε₂
            e1 = f0 + 0.5 * e2
        curve.append({"eps2": round(e2, 8), "eps1_flc": round(e1, 8)})

    return {
        "ok": True,
        "n": float(n),
        "t_m": float(t),
        "FLC0": f0,
        "curve": curve,
        "minimum_eps1": f0,
        "plane_strain_eps2": 0.0,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. strain_path — major/minor strain path
# ---------------------------------------------------------------------------

_VALID_MODES = {"deep_draw", "stretch", "plane_strain"}


def strain_path(
    mode: str,
    eps1_target: float,
    r_aniso: float = 1.0,
) -> dict:
    """
    Major/minor strain path for a given forming mode.

    For sheet forming the relationship between major (ε₁) and minor (ε₂)
    strains is set by the stress state:

    deep_draw  (pure draw, ε₂ = −ε₁ / (1 + r)):
        In deep-drawing the hoop stress is compressive and the strain ratio
        is controlled by the normal anisotropy r (Lankford coefficient):
            ε₂ = −r × ε₁ / (1 + r)   (from volume conservation + r definition)
        For isotropic material (r = 1): ε₂ = −ε₁/2.

    stretch    (equal-biaxial, ε₂ = ε₁):
        Equi-biaxial stretch: ε₁ = ε₂ (σ₁ = σ₂).

    plane_strain (ε₂ = 0):
        Plane-strain tension: no minor strain, ε₃ = −ε₁.
        This is the most critical (lowest FLC) forming condition.

    Parameters
    ----------
    mode : str
        One of 'deep_draw', 'stretch', 'plane_strain'.
    eps1_target : float
        Target major (thickness-direction neutral) true strain.  Must be > 0.
    r_aniso : float
        Normal anisotropy (Lankford r-value), default 1.0.  Must be > 0.
        Only relevant for 'deep_draw' mode.

    Returns
    -------
    dict
        ok          : True
        mode        : forming mode string
        eps1        : major strain (= eps1_target)
        eps2        : minor strain
        eps3        : thickness strain = −ε₁ − ε₂ (volume conservation)
        r_aniso     : anisotropy value used
        strain_ratio: ε₂/ε₁
        warnings    : list
    """
    warnings: list[str] = []

    if mode not in _VALID_MODES:
        return _err(
            f"mode must be one of {sorted(_VALID_MODES)}, got {mode!r}"
        )
    err = _guard_positive("eps1_target", eps1_target)
    if err:
        return _err(err)
    err = _guard_positive("r_aniso", r_aniso)
    if err:
        return _err(err)

    e1 = float(eps1_target)
    r = float(r_aniso)

    if mode == "deep_draw":
        e2 = -r * e1 / (1.0 + r)
    elif mode == "stretch":
        e2 = e1
    else:  # plane_strain
        e2 = 0.0

    e3 = -e1 - e2  # volume conservation: ε₁ + ε₂ + ε₃ = 0
    ratio = e2 / e1 if abs(e1) > 1e-15 else 0.0

    if r < 0.5:
        warnings.append(
            f"r_aniso={r} < 0.5 is unusually low for sheet steel; verify material data."
        )

    return {
        "ok": True,
        "mode": mode,
        "eps1": e1,
        "eps2": e2,
        "eps3": e3,
        "r_aniso": r,
        "strain_ratio": ratio,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. safety_margin — distance from FLC, zone classification
# ---------------------------------------------------------------------------

def safety_margin(
    eps1: float,
    eps2: float,
    n: float,
    t: float,
) -> dict:
    """
    Safety margin of a strain point relative to the Forming Limit Curve.

    The FLC major-strain limit at the given minor strain ε₂ is computed using
    the Keeler-Goodwin model:

        ε₁_FLC(ε₂) = FLC₀ − ε₂        if ε₂ ≤ 0 (drawing side)
        ε₁_FLC(ε₂) = FLC₀ + 0.5·ε₂    if ε₂ > 0 (stretching side)

    The safety margin is defined as:
        Δε₁ = ε₁_FLC(ε₂) − ε₁

    Zones:
        safe     : Δε₁ > 0.10 (more than 10 % strain below FLC)
        marginal : 0 < Δε₁ ≤ 0.10 (within 10 % of FLC — engineering caution zone)
        fail     : Δε₁ ≤ 0 (at or above FLC — necking/fracture predicted)

    Parameters
    ----------
    eps1 : float
        Major (principal) true strain at the point.  Must be >= 0.
    eps2 : float
        Minor (secondary) true strain at the point.  May be negative (drawing)
        or positive (stretching).
    n : float
        Strain-hardening exponent of the sheet material.  Must be > 0.
    t : float
        Sheet thickness (m).  Must be > 0.

    Returns
    -------
    dict
        ok              : True
        eps1            : major strain
        eps2            : minor strain
        FLC0            : plane-strain intercept
        eps1_flc        : FLC limit at this eps2
        delta_eps1      : safety margin = ε₁_FLC − ε₁
        zone            : 'safe', 'marginal', or 'fail'
        safety_pct      : Δε₁ / FLC₀ × 100 (%)
        warnings        : list
    """
    warnings: list[str] = []

    err = _guard_nonneg("eps1", eps1)
    if err:
        return _err(err)
    if not isinstance(eps2, (int, float)) or not math.isfinite(float(eps2)):
        return _err(f"eps2 must be a finite number, got {eps2!r}")

    r0 = flc0(n, t)
    if not r0["ok"]:
        return r0

    f0 = r0["FLC0"]
    warnings.extend(r0["warnings"])

    e1 = float(eps1)
    e2 = float(eps2)

    if e2 <= 0.0:
        eps1_flc = f0 - e2
    else:
        eps1_flc = f0 + 0.5 * e2

    delta = eps1_flc - e1
    safety_pct = delta / f0 * 100.0 if f0 > 0 else 0.0

    if delta > 0.10:
        zone = "safe"
    elif delta > 0.0:
        zone = "marginal"
    else:
        zone = "fail"

    if zone == "fail":
        warnings.append(
            f"FORMING-FAILURE: strain point (ε₁={e1:.4f}, ε₂={e2:.4f}) is above "
            f"the FLC (ε₁_FLC={eps1_flc:.4f}); necking or fracture predicted."
        )
    elif zone == "marginal":
        warnings.append(
            f"MARGINAL: strain point is within 10 % of the FLC "
            f"(Δε₁={delta:.4f}); increase process margins."
        )

    return {
        "ok": True,
        "eps1": e1,
        "eps2": e2,
        "FLC0": f0,
        "eps1_flc": eps1_flc,
        "delta_eps1": delta,
        "zone": zone,
        "safety_pct": safety_pct,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 5. thinning — volume conservation
# ---------------------------------------------------------------------------

def thinning(eps1: float, eps2: float) -> dict:
    """
    Through-thickness thinning strain and thinning percentage.

    Volume conservation (incompressibility):
        ε₁ + ε₂ + ε₃ = 0   →   ε₃ = −ε₁ − ε₂

    The thinning percentage is:
        thinning_pct = (1 − exp(ε₃)) × 100

    (Since ε₃ < 0 for any net stretching, exp(ε₃) < 1, so thinning_pct > 0.)

    Parameters
    ----------
    eps1 : float
        Major true strain.  Must be >= 0.
    eps2 : float
        Minor true strain.  May be negative (drawing) or positive (stretching).

    Returns
    -------
    dict
        ok              : True
        eps1            : major strain
        eps2            : minor strain
        eps3            : thickness strain = −ε₁ − ε₂
        thinning_pct    : thinning (positive = thinner) (%)
        thickening_pct  : thickening (positive = thicker) (%); 0 unless ε₃ > 0
        warnings        : list
    """
    warnings: list[str] = []

    err = _guard_nonneg("eps1", eps1)
    if err:
        return _err(err)
    if not isinstance(eps2, (int, float)) or not math.isfinite(float(eps2)):
        return _err(f"eps2 must be a finite number, got {eps2!r}")

    e1 = float(eps1)
    e2 = float(eps2)
    e3 = -e1 - e2

    # Actual thickness ratio = exp(ε₃)
    t_ratio = math.exp(e3)
    if e3 < 0:
        thinning_pct = (1.0 - t_ratio) * 100.0
        thickening_pct = 0.0
    else:
        thinning_pct = 0.0
        thickening_pct = (t_ratio - 1.0) * 100.0

    if thinning_pct > 25.0:
        warnings.append(
            f"Thinning {thinning_pct:.1f}% > 25% — risk of necking/fracture."
        )

    return {
        "ok": True,
        "eps1": e1,
        "eps2": e2,
        "eps3": e3,
        "thinning_pct": thinning_pct,
        "thickening_pct": thickening_pct,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 6. wrinkling_tendency — heuristic wrinkling index
# ---------------------------------------------------------------------------

def wrinkling_tendency(
    eps1: float,
    eps2: float,
    r_aniso: float,
    t: float,
    R_die: float,
) -> dict:
    """
    Heuristic wrinkling index for the flange/sidewall region.

    Wrinkling in sheet forming occurs when the compressive hoop stress exceeds
    a critical buckling stress.  The buckling stress for a thin-walled flange is:

        σ_buckle ≈ 0.605 × E_eff × t / R

    where E_eff is an effective modulus that accounts for plastic strain and
    R is the die-corner radius (or flange radius).

    This function uses a simplified wrinkling index:

        W = |ε₂| / ε₁   if ε₂ < 0 (compressive minor strain)
        W = 0            if ε₂ >= 0 (tensile — no wrinkling tendency)

    Augmented by a thickness/radius ratio (t/R_die):

        W_eff = W / (t / R_die)   (higher t/R → more stable against wrinkling)

    Classification:
        W_eff < 5  → 'stable'
        5 ≤ W_eff < 15 → 'tendency'
        W_eff ≥ 15 → 'wrinkle_risk'

    Parameters
    ----------
    eps1 : float
        Major true strain.  Must be > 0.
    eps2 : float
        Minor true strain.  Negative implies compressive hoop; positive implies
        tension (no wrinkling).
    r_aniso : float
        Normal anisotropy (Lankford r-value).  Must be > 0.  Higher r → less
        wrinkling tendency in drawing.
    t : float
        Sheet thickness (m).  Must be > 0.
    R_die : float
        Die-corner or flange radius (m).  Must be > 0.

    Returns
    -------
    dict
        ok              : True
        eps1            : major strain
        eps2            : minor strain
        r_aniso         : anisotropy value
        t_m             : sheet thickness (m)
        R_die_m         : die radius (m)
        t_over_R        : t / R_die (geometric stability parameter)
        wrinkling_index : W = |ε₂|/ε₁ (0 if ε₂ >= 0)
        W_eff           : W / (t/R_die)
        tendency        : 'stable', 'tendency', or 'wrinkle_risk'
        warnings        : list
    """
    warnings: list[str] = []

    err = _guard_positive("eps1", eps1)
    if err:
        return _err(err)
    if not isinstance(eps2, (int, float)) or not math.isfinite(float(eps2)):
        return _err(f"eps2 must be a finite number, got {eps2!r}")
    err = _guard_positive("r_aniso", r_aniso)
    if err:
        return _err(err)
    err = _guard_positive("t", t)
    if err:
        return _err(err)
    err = _guard_positive("R_die", R_die)
    if err:
        return _err(err)

    e1 = float(eps1)
    e2 = float(eps2)
    r = float(r_aniso)
    t_v = float(t)
    R_v = float(R_die)

    t_over_R = t_v / R_v

    if e2 < 0.0:
        W = abs(e2) / e1
        # Anisotropy correction: higher r reduces effective compressive strain
        W = W / (1.0 + 0.5 * (r - 1.0)) if r > 0.0 else W
    else:
        W = 0.0

    W_eff = W / t_over_R if t_over_R > 1e-15 else 0.0

    if W_eff >= 15.0:
        tendency = "wrinkle_risk"
        warnings.append(
            f"WRINKLE-RISK: W_eff={W_eff:.2f} >= 15 — increase blank-holder force "
            "or draw-bead restraint."
        )
    elif W_eff >= 5.0:
        tendency = "tendency"
        warnings.append(
            f"Wrinkling tendency W_eff={W_eff:.2f} in [5, 15) — monitor blank-holder "
            "force closely."
        )
    else:
        tendency = "stable"

    return {
        "ok": True,
        "eps1": e1,
        "eps2": e2,
        "r_aniso": r,
        "t_m": t_v,
        "R_die_m": R_v,
        "t_over_R": t_over_R,
        "wrinkling_index": W,
        "W_eff": W_eff,
        "tendency": tendency,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 7. draw_bead_restraining_force — Stoughton model
# ---------------------------------------------------------------------------

def draw_bead_restraining_force(
    t: float,
    sigma_y: float,
    mu: float,
    R_bead: float,
    w_bead: float = 1.0,
) -> dict:
    """
    Draw-bead restraining force per unit width (Stoughton 1988 model).

    The draw-bead restraining force per unit width F/b is composed of:

    1. Bending resistance over the bead:
            F_bend / b = 2 × σ_y × t² / (4 × R_bead)
       (from pure-bending plastic moment per unit width, both sides of bead)

    2. Friction contribution:
            F_fric / b = 2 × μ × F_normal / b
       where F_normal/b ≈ F_bend/b × (geometric factor)

    Simplified Stoughton (1988) form used here:

        F_restrain / b = σ_y × t²/(4·R_bead) × (2 + 3·μ·π/2)

    This captures the dominant bending and friction terms for a single round
    draw-bead of radius R_bead.

    The total force for a bead of width w_bead is:
        F_total = (F_restrain / b) × w_bead

    Parameters
    ----------
    t : float
        Sheet thickness (m).  Must be > 0.
    sigma_y : float
        Sheet yield stress (Pa).  Must be > 0.
    mu : float
        Friction coefficient at sheet-bead interface.  Must be >= 0.
    R_bead : float
        Draw-bead radius (m).  Must be > 0.
    w_bead : float
        Width of draw-bead section (m), default 1.0 (unit-width result).
        Must be > 0.

    Returns
    -------
    dict
        ok                      : True
        t_m                     : sheet thickness (m)
        sigma_y_Pa              : yield stress (Pa)
        mu                      : friction coefficient
        R_bead_m                : bead radius (m)
        w_bead_m                : bead width (m)
        F_per_width_N_m         : restraining force per unit width (N/m)
        F_total_N               : total restraining force over w_bead (N)
        bending_component_N_m   : bending contribution (N/m)
        friction_component_N_m  : friction contribution (N/m)
        warnings                : list
    """
    warnings: list[str] = []

    err = _guard_positive("t", t)
    if err:
        return _err(err)
    err = _guard_positive("sigma_y", sigma_y)
    if err:
        return _err(err)
    err = _guard_nonneg("mu", mu)
    if err:
        return _err(err)
    err = _guard_positive("R_bead", R_bead)
    if err:
        return _err(err)
    err = _guard_positive("w_bead", w_bead)
    if err:
        return _err(err)

    t_v = float(t)
    sy = float(sigma_y)
    mu_v = float(mu)
    R_v = float(R_bead)
    w_v = float(w_bead)

    # Bending moment per unit width: M/b = σ_y·t²/4
    M_per_b = sy * t_v ** 2 / 4.0

    # Stoughton simplified formula
    F_per_b = M_per_b / R_v * (2.0 + 3.0 * mu_v * math.pi / 2.0)

    # Decompose into bending and friction parts
    F_bend = M_per_b / R_v * 2.0
    F_fric = M_per_b / R_v * (3.0 * mu_v * math.pi / 2.0)

    F_total = F_per_b * w_v

    t_over_R = t_v / R_v
    if t_over_R > 0.5:
        warnings.append(
            f"t/R_bead={t_over_R:.3f} > 0.5 — small bead radius relative to "
            "thickness; bending model accuracy may be reduced."
        )

    return {
        "ok": True,
        "t_m": t_v,
        "sigma_y_Pa": sy,
        "mu": mu_v,
        "R_bead_m": R_v,
        "w_bead_m": w_v,
        "F_per_width_N_m": F_per_b,
        "F_total_N": F_total,
        "bending_component_N_m": F_bend,
        "friction_component_N_m": F_fric,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 8. blank_holder_force_window
# ---------------------------------------------------------------------------

def blank_holder_force_window(
    sigma_y: float,
    t: float,
    A_blank: float,
    A_punch: float,
    mu: float = 0.10,
    R_die: float = 0.005,
) -> dict:
    """
    Blank-holder force window [F_BH_min, F_BH_max] for wrinkle-free, no-fracture.

    The blank-holder force (BHF) must be:

    Above F_min to suppress wrinkling (Yoshida–Miyauchi):
        σ_buckle_critical ≈ 2·σ_y·t / (√3·R_die)   [thin-shell buckling approx]
        F_BH_min = σ_buckle_critical × A_flange × 0.3   [empirical fraction]
        where A_flange = A_blank − A_punch (flange annular area).

    Below F_max to avoid fracture (punch-load limited):
        F_BH_max = σ_y × A_punch / (1 + μ·π/2)   [limiting draw force]

    The practical BHF window is [F_min, F_max].  If F_min >= F_max, the
    geometry is problematic (excessive flange area, insufficient blank thickness,
    or wrong die radius).

    Parameters
    ----------
    sigma_y : float
        Sheet yield stress (Pa).  Must be > 0.
    t : float
        Sheet thickness (m).  Must be > 0.
    A_blank : float
        Total blank area (m²).  Must be > A_punch.
    A_punch : float
        Punch area / part plan area (m²).  Must be > 0.
    mu : float
        Friction coefficient (blank–die interface), default 0.10.
    R_die : float
        Die-corner radius (m), default 0.005 m (5 mm).  Must be > 0.

    Returns
    -------
    dict
        ok              : True
        sigma_y_Pa      : yield stress (Pa)
        t_m             : sheet thickness (m)
        A_blank_m2      : blank area (m²)
        A_punch_m2      : punch area (m²)
        A_flange_m2     : flange area = A_blank − A_punch (m²)
        mu              : friction coefficient
        R_die_m         : die-corner radius (m)
        F_BH_min_N      : minimum blank-holder force to suppress wrinkling (N)
        F_BH_max_N      : maximum blank-holder force before fracture risk (N)
        window_valid    : True if F_BH_min < F_BH_max
        warnings        : list
    """
    warnings: list[str] = []

    err = _guard_positive("sigma_y", sigma_y)
    if err:
        return _err(err)
    err = _guard_positive("t", t)
    if err:
        return _err(err)
    err = _guard_positive("A_blank", A_blank)
    if err:
        return _err(err)
    err = _guard_positive("A_punch", A_punch)
    if err:
        return _err(err)
    err = _guard_nonneg("mu", mu)
    if err:
        return _err(err)
    err = _guard_positive("R_die", R_die)
    if err:
        return _err(err)

    sy = float(sigma_y)
    t_v = float(t)
    Ab = float(A_blank)
    Ap = float(A_punch)
    mu_v = float(mu)
    R_v = float(R_die)

    if Ab <= Ap:
        return _err(
            f"A_blank={Ab:.6g} m² must be > A_punch={Ap:.6g} m² (blank must "
            "extend beyond the punch)."
        )

    A_flange = Ab - Ap

    # F_min: anti-wrinkle; simplified thin-shell buckling on flange
    sigma_buckle = 2.0 * sy * t_v / (math.sqrt(3.0) * R_v)
    F_min = sigma_buckle * A_flange * 0.3

    # F_max: fracture limit (limiting draw force)
    F_max = sy * Ap / (1.0 + mu_v * math.pi / 2.0)

    window_valid = F_min < F_max

    if not window_valid:
        warnings.append(
            f"INVALID-WINDOW: F_BH_min={F_min:.1f} N >= F_BH_max={F_max:.1f} N — "
            "no feasible blank-holder force; review geometry (flange too wide, "
            "R_die too small, or material too thin)."
        )

    return {
        "ok": True,
        "sigma_y_Pa": sy,
        "t_m": t_v,
        "A_blank_m2": Ab,
        "A_punch_m2": Ap,
        "A_flange_m2": A_flange,
        "mu": mu_v,
        "R_die_m": R_v,
        "F_BH_min_N": F_min,
        "F_BH_max_N": F_max,
        "window_valid": window_valid,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 9. limiting_draw_ratio — Swift–Hill analytic LDR
# ---------------------------------------------------------------------------

def limiting_draw_ratio(
    r_aniso: float,
    n: float,
) -> dict:
    """
    Limiting draw ratio (LDR) from the Swift–Hill analytic formula.

    The LDR (β_max) is the maximum blank-to-punch diameter ratio for which
    drawing is possible without fracture.  The Swift–Hill formula gives:

        LDR = β_max = exp(η · r̄)

    where:
      r̄  — normal anisotropy (average Lankford r-value)
      η  — drawing efficiency factor ≈ 1 for ideal conditions

    A more accurate empirical approximation (Marciniak et al. §6.4):

        LDR ≈ exp(√(r̄ · n))    for practical cold-drawn steels

    For isotropic material (r̄ = 1, n ≈ 0.20):  LDR ≈ exp(√0.20) ≈ 1.56.
    High-r steels (r̄ = 2.0, n = 0.22):          LDR ≈ exp(√0.44) ≈ 1.93.

    The classical Swift formula often cited is:
        LDR = exp(η·r̄/(1 + r̄))  — a variant; here we use the simpler form.

    This function uses:
        LDR = exp(√(r̄ · n))

    and also returns the Swift closed-form:
        LDR_swift = exp(r̄/(1 + r̄))

    Textbook cross-check: r̄=2.0, n=0.22 → LDR ≈ 1.93 (Hosford & Caddell §12).

    Parameters
    ----------
    r_aniso : float
        Average normal anisotropy r̄ (Lankford coefficient).  Must be > 0.
    n : float
        Strain-hardening exponent.  Must be > 0.

    Returns
    -------
    dict
        ok          : True
        r_aniso     : anisotropy value
        n           : strain-hardening exponent
        LDR         : exp(√(r̄·n))  (primary estimate)
        LDR_swift   : exp(r̄/(1+r̄)) (Swift pure-anisotropy form)
        FLC0_ratio  : FLC₀/n  (formability index)
        warnings    : list
    """
    warnings: list[str] = []

    err = _guard_positive("r_aniso", r_aniso)
    if err:
        return _err(err)
    err = _guard_positive("n", n)
    if err:
        return _err(err)

    r = float(r_aniso)
    n_v = float(n)

    if r < 0.5:
        warnings.append(
            f"r_aniso={r} < 0.5 — very low anisotropy; drawability will be poor."
        )
    if r > 3.0:
        warnings.append(
            f"r_aniso={r} > 3.0 — unusually high anisotropy; verify material data."
        )

    ldr = math.exp(math.sqrt(r * n_v))
    ldr_swift = math.exp(r / (1.0 + r))

    # Formability index: higher FLC₀/n → better formability in stretch
    flc0_ratio = (23.3 / 0.21)  # FLC₀ per unit n at t = 0 (thickness-independent)

    return {
        "ok": True,
        "r_aniso": r,
        "n": n_v,
        "LDR": ldr,
        "LDR_swift": ldr_swift,
        "FLC0_ratio": flc0_ratio,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 10. springback
# ---------------------------------------------------------------------------

def springback(
    sigma_y: float,
    E: float,
    t: float,
    R_punch: float,
    nu: float = 0.30,
) -> dict:
    """
    Springback estimate: pure-bending ratio and sidewall-curl.

    Two springback contributions:

    1. Pure-bending springback (Hosford & Caddell §9.3):

       The Bauschinger/elastic-unloading springback ratio for a simple bend is:

           Rf/R = 1 − 3·(σ_y/E)·(R/t) + 4·(σ_y/E)³·(R/t)³

       where R = R_punch (inner bend radius), t = sheet thickness.
       This is the standard "springback ratio" — closer to 1 means less
       springback (stiffer material or thicker sheet).

    2. Sidewall-curl estimate (simplified Carden et al. 2002):

       After drawing over a die corner of radius R_die, the sidewall develops
       a curvature due to the reverse bending moment.  A simplified estimate
       of the sidewall-curl radius is:

           R_curl ≈ E·t / (4·σ_y·(1 − ν²))

       Larger R_curl → less curl (more elastic recovery per unit stress).

    Springback increases with higher σ_y/E (yield-to-modulus ratio) and larger
    R/t (bend-radius-to-thickness ratio).

    Parameters
    ----------
    sigma_y : float
        Sheet yield stress (Pa).  Must be > 0.
    E : float
        Young's modulus (Pa).  Must be > 0.
    t : float
        Sheet thickness (m).  Must be > 0.
    R_punch : float
        Inner punch radius / bend radius (m).  Must be > 0.
    nu : float
        Poisson's ratio, default 0.30.  Must be in (0, 0.5).

    Returns
    -------
    dict
        ok              : True
        sigma_y_Pa      : yield stress (Pa)
        E_Pa            : Young's modulus (Pa)
        t_m             : sheet thickness (m)
        R_punch_m       : inner punch radius (m)
        nu              : Poisson's ratio
        R_over_t        : R_punch / t (dimensionless)
        yield_to_modulus: σ_y / E
        Rf_over_R       : springback ratio (pure bending)
        delta_angle_pct : springback as percentage of bend angle (approx)
        R_curl_m        : sidewall-curl radius estimate (m)
        warnings        : list

    Notes
    -----
    Springback increases with:
      - Higher σ_y/E (high-strength steels, aluminium)
      - Larger R/t (gentler bends spring back more)
    The pure-bending formula is valid for R/t >= 2.  For R/t < 2 the formula
    becomes inaccurate (severe bending / plastic strain through full thickness).
    """
    warnings: list[str] = []

    err = _guard_positive("sigma_y", sigma_y)
    if err:
        return _err(err)
    err = _guard_positive("E", E)
    if err:
        return _err(err)
    err = _guard_positive("t", t)
    if err:
        return _err(err)
    err = _guard_positive("R_punch", R_punch)
    if err:
        return _err(err)
    err = _guard_positive("nu", nu)
    if err:
        return _err(err)
    if float(nu) >= 0.5:
        return _err(f"nu={nu} must be < 0.5 for a compressible material.")

    sy = float(sigma_y)
    E_v = float(E)
    t_v = float(t)
    R_v = float(R_punch)
    nu_v = float(nu)

    R_over_t = R_v / t_v
    sy_over_E = sy / E_v

    if R_over_t < 2.0:
        warnings.append(
            f"R/t = {R_over_t:.2f} < 2.0 — pure-bending springback formula accuracy "
            "is reduced; full-thickness plastic strain expected."
        )

    # Pure-bending springback ratio (Hosford & Caddell Eq 9.11)
    x = sy_over_E * R_over_t
    Rf_over_R = 1.0 - 3.0 * x + 4.0 * (x ** 3)

    # Clamp to physical range [0, 2] (formula can give unphysical results for
    # extreme combinations that violate the beam-bending assumption)
    Rf_over_R = max(0.0, min(2.0, Rf_over_R))

    # Approximate springback angle percentage: δθ/θ ≈ (1 − Rf/R) × 100
    # Rf/R < 1: springback (angle opens up), Rf/R > 1: over-springback
    delta_angle_pct = (1.0 - Rf_over_R) * 100.0

    # Sidewall-curl radius
    R_curl = E_v * t_v / (4.0 * sy * (1.0 - nu_v ** 2))

    if sy_over_E > 0.005:
        warnings.append(
            f"σ_y/E = {sy_over_E:.4f} > 0.005 — high-strength material; "
            "significant springback expected; overbend or post-stretch correction needed."
        )

    return {
        "ok": True,
        "sigma_y_Pa": sy,
        "E_Pa": E_v,
        "t_m": t_v,
        "R_punch_m": R_v,
        "nu": nu_v,
        "R_over_t": R_over_t,
        "yield_to_modulus": sy_over_E,
        "Rf_over_R": Rf_over_R,
        "delta_angle_pct": delta_angle_pct,
        "R_curl_m": R_curl,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 11. one_step_inverse — section-based inverse strain estimate
# ---------------------------------------------------------------------------

def one_step_inverse(
    profile_coords: Sequence[Tuple[float, float]],
    t: float,
    sigma_y: float,
    n: float,
    K: float,
) -> dict:
    """
    Section-based one-step inverse strain estimate from a target 2-D profile.

    The "one-step inverse" method back-calculates the blank strain field from
    the deformed part geometry, assuming a proportional (straight-line) strain
    path.  This is a simplified, section-by-section estimate:

    For each segment of the profile (x_i, y_i) → (x_{i+1}, y_{i+1}):

      1. Arc length of deformed segment:
             L_def = sqrt(Δx² + Δy²)

      2. Blank length (volume-conservation, plane-strain assumption):
             L_blank = L_def × exp(−ε₃)
         In the one-step approximation (no thickness change info), we assume
         ε₃ ≈ 0 for the blank → L_blank ≈ L_def / √(exp(ε₁_avg))

         Simplified: L_blank_i = L_def_i (each segment maps 1:1 in blank,
         cumulative strain is computed from cumulative arc length ratio).

      3. The total deformed arc length = Σ L_def_i.
         The total blank arc length ≈ straight-line distance from first to
         last point (bounding blank diagonal — conservative lower bound):
             L_blank_total = distance(p0, p_n)

      4. Average major true strain (plane-strain assumption):
             ε₁_avg = ln(L_def_total / L_blank_total)

      5. Per-segment strain is proportionally distributed:
             ε₁_i = ε₁_avg × (L_def_i / L_def_total)
             ε₂_i = 0  (plane-strain assumption)
             ε₃_i = −ε₁_i

      6. Flow stress at each segment:
             σ_f_i = K × ε₁_i^n   (Hollomon, ε₁_i > 0)

    Returns per-segment data, global strain, and overall formability assessment
    against the FLC.

    Parameters
    ----------
    profile_coords : list of (x, y) tuples
        2-D profile coordinates (m).  Must have >= 2 points.
    t : float
        Sheet thickness (m).  Must be > 0.
    sigma_y : float
        Yield stress (Pa).  Must be > 0.
    n : float
        Strain-hardening exponent.  Must be > 0.
    K : float
        Strength coefficient (Pa).  Must be > 0.

    Returns
    -------
    dict
        ok                  : True
        n_segments          : number of profile segments
        L_def_total_m       : total deformed arc length (m)
        L_blank_total_m     : estimated blank arc length (m) — straight-line approx
        eps1_avg            : average major true strain
        eps1_max            : maximum segment major strain
        segments            : list of per-segment dicts:
                              {L_def_m, eps1, eps2, eps3, sigma_f_Pa, zone}
        overall_zone        : 'safe'/'marginal'/'fail' (worst-case segment)
        FLC0                : FLC₀ at given n, t
        warnings            : list
    """
    warnings: list[str] = []

    # Validate profile
    try:
        coords = [(float(x), float(y)) for x, y in profile_coords]
    except (TypeError, ValueError) as exc:
        return _err(f"profile_coords must be a sequence of (x,y) pairs: {exc}")

    if len(coords) < 2:
        return _err(
            f"profile_coords must have at least 2 points, got {len(coords)}"
        )

    err = _guard_positive("t", t)
    if err:
        return _err(err)
    err = _guard_positive("sigma_y", sigma_y)
    if err:
        return _err(err)
    err = _guard_positive("n", n)
    if err:
        return _err(err)
    err = _guard_positive("K", K)
    if err:
        return _err(err)

    t_v = float(t)
    sy = float(sigma_y)
    n_v = float(n)
    K_v = float(K)

    # Segment arc lengths
    seg_lengths: list[float] = []
    for i in range(len(coords) - 1):
        dx = coords[i + 1][0] - coords[i][0]
        dy = coords[i + 1][1] - coords[i][1]
        seg_lengths.append(math.sqrt(dx * dx + dy * dy))

    L_def_total = sum(seg_lengths)
    if L_def_total < 1e-12:
        return _err("profile_coords: all points are coincident (zero arc length).")

    # Blank arc length: straight-line distance first→last
    dx_tot = coords[-1][0] - coords[0][0]
    dy_tot = coords[-1][1] - coords[0][1]
    L_blank_total = math.sqrt(dx_tot * dx_tot + dy_tot * dy_tot)

    if L_blank_total < 1e-12:
        # Closed profile: use convex-hull perimeter approximation
        L_blank_total = L_def_total * 0.6
        warnings.append(
            "Profile appears closed (first == last point); using L_blank = 0.6·L_def "
            "as blank estimate."
        )

    # Average major strain
    eps1_avg = math.log(L_def_total / L_blank_total)
    if eps1_avg < 0.0:
        warnings.append(
            "Average strain is negative (L_def < L_blank) — blank may be larger than "
            "needed; check profile orientation."
        )
        eps1_avg = abs(eps1_avg)

    # FLC₀ for zone classification
    r0 = flc0(n_v, t_v)
    if not r0["ok"]:
        return r0
    f0 = r0["FLC0"]
    warnings.extend(r0["warnings"])

    # Per-segment data
    segments: list[dict] = []
    eps1_max = 0.0
    zones = []

    for L_seg in seg_lengths:
        e1_seg = eps1_avg * (L_seg / L_def_total)
        e2_seg = 0.0  # plane-strain
        e3_seg = -e1_seg

        # Flow stress
        if e1_seg > 1e-12:
            sf = K_v * (e1_seg ** n_v)
        else:
            sf = sy  # trivially elastic

        # Zone
        sm = safety_margin(e1_seg, e2_seg, n_v, t_v)
        zone = sm["zone"] if sm["ok"] else "unknown"
        zones.append(zone)

        eps1_max = max(eps1_max, e1_seg)
        segments.append({
            "L_def_m": L_seg,
            "eps1": e1_seg,
            "eps2": e2_seg,
            "eps3": e3_seg,
            "sigma_f_Pa": sf,
            "zone": zone,
        })

    # Overall zone: worst case
    priority = {"fail": 2, "marginal": 1, "safe": 0, "unknown": -1}
    overall_zone = max(zones, key=lambda z: priority.get(z, -1))

    if overall_zone == "fail":
        warnings.append(
            "FORMING-FAILURE: one or more profile segments are above the FLC."
        )

    return {
        "ok": True,
        "n_segments": len(segments),
        "L_def_total_m": L_def_total,
        "L_blank_total_m": L_blank_total,
        "eps1_avg": eps1_avg,
        "eps1_max": eps1_max,
        "segments": segments,
        "overall_zone": overall_zone,
        "FLC0": f0,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# LLM tool registrations (gated)
# ---------------------------------------------------------------------------

try:
    import json as _json

    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx  # noqa: F401

    # ── run_sheet_flc0 ────────────────────────────────────────────────────────

    _flc0_spec = ToolSpec(
        name="sheet_forming_flc0",
        description=(
            "Compute the Keeler-Goodwin FLC₀ (plane-strain forming-limit intercept) "
            "for a sheet material from its strain-hardening exponent n and thickness t.\n"
            "\n"
            "FLC₀ = (23.3 + 14.13·t_mm)·n/0.21  (as fractional true strain)\n"
            "\n"
            "Errors: {ok:false, reason} for invalid inputs.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "n": {
                    "type": "number",
                    "description": "Strain-hardening exponent (dimensionless, > 0).",
                },
                "t": {
                    "type": "number",
                    "description": "Sheet thickness (m, > 0).",
                },
            },
            "required": ["n", "t"],
        },
    )

    @register(_flc0_spec, write=False)
    async def run_sheet_flc0(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("n", "t"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        return ok_payload(flc0(a["n"], a["t"]))

    # ── run_sheet_flc_curve ───────────────────────────────────────────────────

    _flc_curve_spec = ToolSpec(
        name="sheet_forming_flc_curve",
        description=(
            "Return the full Forming Limit Curve (FLC) as (ε₂, ε₁) pairs using "
            "the Keeler-Goodwin model.  The curve minimum is at plane-strain (ε₂=0).\n"
            "\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "n": {"type": "number", "description": "Strain-hardening exponent."},
                "t": {"type": "number", "description": "Sheet thickness (m)."},
                "n_points": {
                    "type": "integer",
                    "description": "Number of curve points (default 21, >= 3).",
                },
            },
            "required": ["n", "t"],
        },
    )

    @register(_flc_curve_spec, write=False)
    async def run_sheet_flc_curve(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("n", "t"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        return ok_payload(flc_curve(a["n"], a["t"], a.get("n_points", 21)))

    # ── run_sheet_strain_path ─────────────────────────────────────────────────

    _strain_path_spec = ToolSpec(
        name="sheet_forming_strain_path",
        description=(
            "Return the major/minor strain path for a given forming mode:\n"
            "  deep_draw   — ε₂ = −r·ε₁/(1+r)\n"
            "  stretch     — ε₂ = ε₁ (equi-biaxial)\n"
            "  plane_strain — ε₂ = 0\n"
            "\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "description": "One of 'deep_draw', 'stretch', 'plane_strain'.",
                },
                "eps1_target": {
                    "type": "number",
                    "description": "Target major true strain (> 0).",
                },
                "r_aniso": {
                    "type": "number",
                    "description": "Normal anisotropy r-value (default 1.0, > 0).",
                },
            },
            "required": ["mode", "eps1_target"],
        },
    )

    @register(_strain_path_spec, write=False)
    async def run_sheet_strain_path(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("mode", "eps1_target"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        return ok_payload(
            strain_path(a["mode"], a["eps1_target"], a.get("r_aniso", 1.0))
        )

    # ── run_sheet_safety_margin ───────────────────────────────────────────────

    _safety_margin_spec = ToolSpec(
        name="sheet_forming_safety_margin",
        description=(
            "Assess how close a (ε₁, ε₂) strain state is to the FLC.  Returns "
            "safe / marginal / fail zone and Δε₁ margin.\n\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "eps1": {"type": "number", "description": "Major true strain (>= 0)."},
                "eps2": {"type": "number", "description": "Minor true strain."},
                "n": {"type": "number", "description": "Strain-hardening exponent."},
                "t": {"type": "number", "description": "Sheet thickness (m)."},
            },
            "required": ["eps1", "eps2", "n", "t"],
        },
    )

    @register(_safety_margin_spec, write=False)
    async def run_sheet_safety_margin(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("eps1", "eps2", "n", "t"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        return ok_payload(safety_margin(a["eps1"], a["eps2"], a["n"], a["t"]))

    # ── run_sheet_thinning ────────────────────────────────────────────────────

    _thinning_spec = ToolSpec(
        name="sheet_forming_thinning",
        description=(
            "Compute through-thickness thinning from ε₁ and ε₂ via volume "
            "conservation (ε₃ = −ε₁ − ε₂).\n\nErrors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "eps1": {"type": "number", "description": "Major true strain (>= 0)."},
                "eps2": {"type": "number", "description": "Minor true strain."},
            },
            "required": ["eps1", "eps2"],
        },
    )

    @register(_thinning_spec, write=False)
    async def run_sheet_thinning(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("eps1", "eps2"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        return ok_payload(thinning(a["eps1"], a["eps2"]))

    # ── run_sheet_wrinkling ───────────────────────────────────────────────────

    _wrinkling_spec = ToolSpec(
        name="sheet_forming_wrinkling",
        description=(
            "Heuristic wrinkling index for flange/sidewall region based on strain "
            "state, anisotropy, and t/R_die geometry.\n\nErrors: {ok:false, reason}.  "
            "Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "eps1": {"type": "number", "description": "Major true strain (> 0)."},
                "eps2": {"type": "number", "description": "Minor true strain."},
                "r_aniso": {"type": "number", "description": "Normal anisotropy (> 0)."},
                "t": {"type": "number", "description": "Sheet thickness (m, > 0)."},
                "R_die": {"type": "number", "description": "Die-corner radius (m, > 0)."},
            },
            "required": ["eps1", "eps2", "r_aniso", "t", "R_die"],
        },
    )

    @register(_wrinkling_spec, write=False)
    async def run_sheet_wrinkling(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("eps1", "eps2", "r_aniso", "t", "R_die"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        return ok_payload(
            wrinkling_tendency(a["eps1"], a["eps2"], a["r_aniso"], a["t"], a["R_die"])
        )

    # ── run_sheet_draw_bead_force ─────────────────────────────────────────────

    _draw_bead_spec = ToolSpec(
        name="sheet_forming_draw_bead_force",
        description=(
            "Draw-bead restraining force per unit width using the Stoughton (1988) "
            "bending + friction model.\n\nErrors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "t": {"type": "number", "description": "Sheet thickness (m, > 0)."},
                "sigma_y": {"type": "number", "description": "Yield stress (Pa, > 0)."},
                "mu": {"type": "number", "description": "Friction coefficient (>= 0)."},
                "R_bead": {"type": "number", "description": "Bead radius (m, > 0)."},
                "w_bead": {
                    "type": "number",
                    "description": "Bead width (m, default 1.0).",
                },
            },
            "required": ["t", "sigma_y", "mu", "R_bead"],
        },
    )

    @register(_draw_bead_spec, write=False)
    async def run_sheet_draw_bead_force(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("t", "sigma_y", "mu", "R_bead"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        return ok_payload(
            draw_bead_restraining_force(
                a["t"], a["sigma_y"], a["mu"], a["R_bead"], a.get("w_bead", 1.0)
            )
        )

    # ── run_sheet_bh_force_window ─────────────────────────────────────────────

    _bh_spec = ToolSpec(
        name="sheet_forming_bh_force_window",
        description=(
            "Blank-holder force window [F_BH_min, F_BH_max] for wrinkle-free and "
            "fracture-free drawing.\n\nErrors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "sigma_y": {"type": "number", "description": "Yield stress (Pa, > 0)."},
                "t": {"type": "number", "description": "Sheet thickness (m, > 0)."},
                "A_blank": {"type": "number", "description": "Blank area (m², > A_punch)."},
                "A_punch": {"type": "number", "description": "Punch area (m², > 0)."},
                "mu": {"type": "number", "description": "Friction coefficient (default 0.10)."},
                "R_die": {"type": "number", "description": "Die-corner radius (m, default 0.005)."},
            },
            "required": ["sigma_y", "t", "A_blank", "A_punch"],
        },
    )

    @register(_bh_spec, write=False)
    async def run_sheet_bh_force_window(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("sigma_y", "t", "A_blank", "A_punch"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        return ok_payload(
            blank_holder_force_window(
                a["sigma_y"], a["t"], a["A_blank"], a["A_punch"],
                a.get("mu", 0.10), a.get("R_die", 0.005),
            )
        )

    # ── run_sheet_ldr ─────────────────────────────────────────────────────────

    _ldr_spec = ToolSpec(
        name="sheet_forming_ldr",
        description=(
            "Limiting Draw Ratio (LDR) from Swift–Hill analytic formula: "
            "LDR = exp(√(r̄·n)).  Also returns Swift pure-anisotropy form.\n\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "r_aniso": {
                    "type": "number",
                    "description": "Normal anisotropy r̄ (Lankford coefficient, > 0).",
                },
                "n": {
                    "type": "number",
                    "description": "Strain-hardening exponent (> 0).",
                },
            },
            "required": ["r_aniso", "n"],
        },
    )

    @register(_ldr_spec, write=False)
    async def run_sheet_ldr(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("r_aniso", "n"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        return ok_payload(limiting_draw_ratio(a["r_aniso"], a["n"]))

    # ── run_sheet_springback ──────────────────────────────────────────────────

    _springback_spec = ToolSpec(
        name="sheet_forming_springback",
        description=(
            "Springback estimate: pure-bending Rf/R ratio (Hosford & Caddell) and "
            "sidewall-curl radius.\n\nErrors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "sigma_y": {"type": "number", "description": "Yield stress (Pa, > 0)."},
                "E": {"type": "number", "description": "Young's modulus (Pa, > 0)."},
                "t": {"type": "number", "description": "Sheet thickness (m, > 0)."},
                "R_punch": {"type": "number", "description": "Inner punch/bend radius (m, > 0)."},
                "nu": {"type": "number", "description": "Poisson's ratio (default 0.30)."},
            },
            "required": ["sigma_y", "E", "t", "R_punch"],
        },
    )

    @register(_springback_spec, write=False)
    async def run_sheet_springback(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("sigma_y", "E", "t", "R_punch"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        return ok_payload(
            springback(a["sigma_y"], a["E"], a["t"], a["R_punch"], a.get("nu", 0.30))
        )

    # ── run_sheet_one_step_inverse ────────────────────────────────────────────

    _one_step_spec = ToolSpec(
        name="sheet_forming_one_step_inverse",
        description=(
            "Section-based one-step inverse strain estimate from a target 2-D profile.  "
            "Back-calculates blank strains from deformed geometry assuming proportional "
            "plane-strain paths.\n\nErrors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "profile_coords": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "description": "List of [x, y] coordinate pairs (m).",
                },
                "t": {"type": "number", "description": "Sheet thickness (m, > 0)."},
                "sigma_y": {"type": "number", "description": "Yield stress (Pa, > 0)."},
                "n": {"type": "number", "description": "Strain-hardening exponent (> 0)."},
                "K": {"type": "number", "description": "Strength coefficient (Pa, > 0)."},
            },
            "required": ["profile_coords", "t", "sigma_y", "n", "K"],
        },
    )

    @register(_one_step_spec, write=False)
    async def run_sheet_one_step_inverse(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("profile_coords", "t", "sigma_y", "n", "K"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        return ok_payload(
            one_step_inverse(
                a["profile_coords"], a["t"], a["sigma_y"], a["n"], a["K"]
            )
        )

except ImportError:
    pass
