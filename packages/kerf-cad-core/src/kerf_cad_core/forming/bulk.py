"""
kerf_cad_core.forming.bulk — pure-Python bulk metal forming calculators.

Implements ten public functions covering the main bulk-forming processes:

  flow_stress(K, eps, n)
      Hollomon power-law flow stress: σ = K · ε^n.

  mean_flow_stress(K, n, eps_f)
      Mean (average) flow stress over strain range 0 → eps_f:
      σ̄_f = K · ε_f^n / (n + 1).

  upset_forging_force(sigma_f, A0, h0, hf, mu)
      Open-die upset forging force including friction and barrel-factor
      (Siebel slab-method approximation).

  closed_die_forging_load(sigma_f, A_proj, Kf)
      Closed-die forging load = projected area × constraint factor × mean
      flow stress.

  forward_extrusion(sigma_f, A0, Af, mu, die_half_angle_deg, L)
      Forward (direct) extrusion pressure and force — ideal work + friction
      + redundant work.

  backward_extrusion(sigma_f, A0, Af, mu, die_half_angle_deg)
      Backward (indirect) extrusion pressure and force.

  flat_rolling(sigma_f, mu, R, h0, hf, w, omega_rad_s)
      Flat rolling: contact length, roll force from friction-hill integration,
      torque, power, max draft from bite angle, neutral point, roll flattening
      note.

  wire_drawing(sigma_f, A0, Af, mu, die_half_angle_deg)
      Wire/bar drawing: drawing stress, force, max reduction per pass,
      and limiting reduction.

  forming_work(F_N, displacement_m, eta)
      Mechanical work / energy and adiabatic temperature rise.

  passes_required(r_total, r_per_pass)
      Minimum number of passes to achieve total reduction.

All functions return plain dicts:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Limit-exceeded flags are issued via the `warnings`
module and collected into the result dict's "warnings" list.

Units
-----
  lengths       — metres (m) unless noted
  areas         — square metres (m²)
  force         — Newtons (N)
  pressure/stress — Pascals (Pa)
  angles        — degrees (°) for inputs; radians used internally
  temperature   — degrees Celsius (°C) for rise outputs
  power         — Watts (W)
  torque        — Newton-metres (N·m)
  energy/work   — Joules (J)

References
----------
Kalpakjian, S. & Schmid, S.R. "Manufacturing Engineering & Technology", 7th ed.
  Forging: §14.3–14.5; Extrusion: §15.2–15.4; Rolling: §13.2–13.6;
  Drawing: §15.5–15.6
Hosford, W.F. & Caddell, R.M. "Metal Forming: Mechanics and Metallurgy", 4th ed.
  Hollomon: §2.1; Slab analysis: §4.2–4.5
Groover, M.P. "Fundamentals of Modern Manufacturing", 5th ed.
  Forging: §19.3; Rolling: §19.1; Extrusion/Drawing: §19.4–19.5

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _warn(msg: str, collected: list) -> None:
    """Issue a UserWarning and append to collected list."""
    warnings.warn(msg, UserWarning, stacklevel=4)
    collected.append(msg)


# ---------------------------------------------------------------------------
# 1. flow_stress
# ---------------------------------------------------------------------------

def flow_stress(
    K: float,
    eps: float,
    n: float,
) -> dict:
    """
    Hollomon power-law flow stress: σ = K · ε^n.

    The Hollomon (1945) equation is the most widely used description of
    strain-hardening behaviour in bulk metal forming:

        σ_f = K · ε^n

    where:
      σ_f — true (flow) stress at true strain ε (Pa)
      K   — strength coefficient (Pa)
      ε   — true (logarithmic) strain  (dimensionless, > 0)
      n   — strain-hardening exponent (dimensionless, 0 ≤ n ≤ 1)

    Typical values (approximate):
      Low-carbon steel:    K ≈ 530 MPa, n ≈ 0.26
      304 Stainless steel: K ≈ 1275 MPa, n ≈ 0.45
      Aluminium 1100-O:    K ≈ 180 MPa, n ≈ 0.20
      Copper (annealed):   K ≈ 315 MPa, n ≈ 0.54

    Parameters
    ----------
    K : float
        Strength coefficient (Pa).  Must be > 0.
    eps : float
        True strain at which to evaluate flow stress.  Must be > 0.
    n : float
        Strain-hardening exponent.  Typical range [0, 1].  Must be >= 0.

    Returns
    -------
    dict
        ok           : True
        K_Pa         : strength coefficient (Pa)
        eps          : true strain
        n            : strain-hardening exponent
        sigma_f_Pa   : flow stress σ = K · ε^n (Pa)
        warnings     : list of warning strings

    Notes
    -----
    ε must be > 0 for the power law to be well defined (ε=0 gives σ=0 for
    n>0, which is physically unreasonable at the start of deformation; in
    practice a small offset strain of ~0.002 is sometimes used).
    """
    warninglist: list[str] = []

    err = _guard_positive("K", K)
    if err:
        return _err(err)
    err = _guard_positive("eps", eps)
    if err:
        return _err(err)
    err = _guard_nonneg("n", n)
    if err:
        return _err(err)

    K_val = float(K)
    e = float(eps)
    n_val = float(n)

    if n_val > 1.0:
        _warn(
            f"Strain-hardening exponent n={n_val} > 1.0 is physically unusual "
            "for metallic materials; verify input.",
            warninglist,
        )

    sigma_f = K_val * (e ** n_val)

    return {
        "ok": True,
        "K_Pa": K_val,
        "eps": e,
        "n": n_val,
        "sigma_f_Pa": sigma_f,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 2. mean_flow_stress
# ---------------------------------------------------------------------------

def mean_flow_stress(
    K: float,
    n: float,
    eps_f: float,
) -> dict:
    """
    Mean (average) flow stress over a strain range 0 → ε_f.

    When the full strain history from 0 to ε_f is relevant (e.g. for work
    calculations or force estimates using the mean flow stress), the average
    of the Hollomon flow stress over the strain range is:

        σ̄_f = K · ε_f^n / (n + 1)

    This arises from integrating σ_f = K ε^n from 0 to ε_f:
        σ̄_f = (1/ε_f) · ∫₀^{ε_f} K ε^n dε
             = K · ε_f^n / (n + 1)

    Parameters
    ----------
    K : float
        Strength coefficient (Pa).  Must be > 0.
    n : float
        Strain-hardening exponent.  Must be >= 0.
    eps_f : float
        Final true strain (total deformation strain).  Must be > 0.

    Returns
    -------
    dict
        ok              : True
        K_Pa            : strength coefficient (Pa)
        n               : strain-hardening exponent
        eps_f           : final true strain
        sigma_f_at_eps_f: flow stress at ε_f (Pa)
        mean_flow_stress_Pa: σ̄_f = K · ε_f^n / (n + 1) (Pa)
        warnings        : list of warning strings

    Notes
    -----
    For perfectly plastic material (n = 0), σ̄_f = K regardless of ε_f.
    For work-hardening materials, σ̄_f < σ_f(ε_f).
    """
    warninglist: list[str] = []

    err = _guard_positive("K", K)
    if err:
        return _err(err)
    err = _guard_nonneg("n", n)
    if err:
        return _err(err)
    err = _guard_positive("eps_f", eps_f)
    if err:
        return _err(err)

    K_val = float(K)
    n_val = float(n)
    ef = float(eps_f)

    if n_val > 1.0:
        _warn(
            f"Strain-hardening exponent n={n_val} > 1.0 is physically unusual; verify input.",
            warninglist,
        )

    sigma_at_ef = K_val * (ef ** n_val)
    sigma_mean = K_val * (ef ** n_val) / (n_val + 1.0)

    return {
        "ok": True,
        "K_Pa": K_val,
        "n": n_val,
        "eps_f": ef,
        "sigma_f_at_eps_f_Pa": sigma_at_ef,
        "mean_flow_stress_Pa": sigma_mean,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 3. upset_forging_force
# ---------------------------------------------------------------------------

def upset_forging_force(
    sigma_f: float,
    A0: float,
    h0: float,
    hf: float,
    mu: float = 0.1,
) -> dict:
    """
    Open-die upset forging force with friction (Siebel/slab method).

    For a solid cylindrical workpiece compressed between flat dies, the
    Siebel slab-method approximation (accounting for Coulomb friction at
    die faces) gives an average forging pressure:

        p_avg = σ_f · (1 + 2·μ·R_f / (3·h_f))      [von Mises]

    where R_f is the final workpiece radius after upsetting.

    Volume conservation: A0·h0 = Af·hf  →  Af = A0·h0/hf
    → R_f = sqrt(Af / π)

    The total forging force is:
        F = p_avg · A_f

    Barrelling increases the actual contact area; this formula uses the
    final cross-sectional area as a conservative estimate.

    Parameters
    ----------
    sigma_f : float
        Flow stress at the forging strain (Pa).  Use mean flow stress for
        incremental forging or instantaneous flow stress.  Must be > 0.
    A0 : float
        Initial cross-sectional area of workpiece (m²).  Must be > 0.
    h0 : float
        Initial height of workpiece (m).  Must be > 0.
    hf : float
        Final height after forging (m).  Must be > 0 and < h0.
    mu : float
        Coulomb friction coefficient at die–workpiece interface
        (default 0.1).  Typical range: 0.05 (lubricated) – 0.4 (dry).
        Must be >= 0.

    Returns
    -------
    dict
        ok              : True
        sigma_f_Pa      : flow stress used (Pa)
        A0_m2           : initial area (m²)
        h0_m            : initial height (m)
        hf_m            : final height (m)
        Af_m2           : final area (m²) — volume conservation
        Rf_m            : final radius (m)
        true_strain     : true compressive strain = ln(h0/hf)
        reduction_pct   : height reduction (%)
        mu              : friction coefficient used
        friction_factor : 2μR_f/(3h_f)  — Siebel friction term
        p_avg_Pa        : average forging pressure (Pa)
        F_N             : forging force (N)
        F_MN            : forging force (MN) for tonnage reference
        warnings        : list of warning strings

    Notes
    -----
    Warnings are issued if:
      - friction_factor > 0.5 (ring test / tribology concern)
      - reduction > 80 % (risk of workpiece fracture / excessive force)
    """
    warninglist: list[str] = []

    err = _guard_positive("sigma_f", sigma_f)
    if err:
        return _err(err)
    err = _guard_positive("A0", A0)
    if err:
        return _err(err)
    err = _guard_positive("h0", h0)
    if err:
        return _err(err)
    err = _guard_positive("hf", hf)
    if err:
        return _err(err)
    err = _guard_nonneg("mu", mu)
    if err:
        return _err(err)

    sf = float(sigma_f)
    A = float(A0)
    h0v = float(h0)
    hfv = float(hf)
    mu_v = float(mu)

    if hfv >= h0v:
        return _err(
            f"hf={hfv} m must be < h0={h0v} m (workpiece must be compressed)."
        )

    # Volume conservation
    Af = A * h0v / hfv
    Rf = math.sqrt(Af / math.pi)

    # True strain (compressive, positive value)
    eps_true = math.log(h0v / hfv)
    reduction_pct = (1.0 - hfv / h0v) * 100.0

    # Siebel friction correction factor
    ff = 2.0 * mu_v * Rf / (3.0 * hfv)

    # Average forging pressure
    p_avg = sf * (1.0 + ff)

    # Total forging force
    F = p_avg * Af
    F_MN = F / 1e6

    if ff > 0.5:
        _warn(
            f"Friction factor 2μR/(3h) = {ff:.3f} > 0.5 — consider better lubrication "
            "or smaller workpiece diameter to reduce forging force.",
            warninglist,
        )
    if reduction_pct > 80.0:
        _warn(
            f"Height reduction {reduction_pct:.1f}% > 80% — risk of workpiece fracture "
            "or excessive press tonnage; consider multiple passes.",
            warninglist,
        )

    return {
        "ok": True,
        "sigma_f_Pa": sf,
        "A0_m2": A,
        "h0_m": h0v,
        "hf_m": hfv,
        "Af_m2": Af,
        "Rf_m": Rf,
        "true_strain": eps_true,
        "reduction_pct": reduction_pct,
        "mu": mu_v,
        "friction_factor": ff,
        "p_avg_Pa": p_avg,
        "F_N": F,
        "F_MN": F_MN,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 4. closed_die_forging_load
# ---------------------------------------------------------------------------

def closed_die_forging_load(
    sigma_f: float,
    A_proj: float,
    Kf: float = 6.0,
) -> dict:
    """
    Closed-die (impression-die) forging load.

    The forging load for impression-die (closed-die) forging is estimated as:

        F = Kf · σ̄_f · A_proj

    where:
      Kf    — constraint / die-fill factor (dimensionless), typically 3–9
      σ̄_f  — mean flow stress of the workpiece material at forging temperature
      A_proj — projected area of the forging (the plan-form area including flash)

    The constraint factor Kf accounts for:
      - Flash resistance (back-pressure from thin flash land)
      - Friction at die surfaces
      - Complexity of the forging geometry

    Typical Kf values:
      3 – simple shapes, generous flash
      6 – moderate complexity (default)
      8 – complex, thin-flash, high-precision forgings

    Parameters
    ----------
    sigma_f : float
        Mean flow stress at forging temperature and strain (Pa).  Must be > 0.
    A_proj : float
        Projected plan-form area of the forging including flash (m²).
        Must be > 0.
    Kf : float
        Die constraint / flash factor (default 6.0).  Typical range [3, 9].
        Must be > 0.

    Returns
    -------
    dict
        ok          : True
        sigma_f_Pa  : mean flow stress used (Pa)
        A_proj_m2   : projected area used (m²)
        Kf          : constraint factor used
        F_N         : forging load (N)
        F_MN        : forging load (MN) for press tonnage reference
        F_tonnesf   : forging load (metric tonnes-force)
        warnings    : list of warning strings

    Notes
    -----
    A warning is issued if Kf > 8 or if the computed load exceeds 100 MN
    (press-tonnage-exceeded flag), indicating that the workpiece may need
    to be subdivided or forged in multiple heats.
    """
    warninglist: list[str] = []

    err = _guard_positive("sigma_f", sigma_f)
    if err:
        return _err(err)
    err = _guard_positive("A_proj", A_proj)
    if err:
        return _err(err)
    err = _guard_positive("Kf", Kf)
    if err:
        return _err(err)

    sf = float(sigma_f)
    Ap = float(A_proj)
    kf = float(Kf)

    if kf > 8.0:
        _warn(
            f"Kf={kf} > 8.0 is outside the typical range [3, 9]; verify design.",
            warninglist,
        )

    F = kf * sf * Ap
    F_MN = F / 1e6
    F_tonf = F / (9806.65)  # metric tonnes-force (1 tf = 9806.65 N)

    if F_MN > 100.0:
        _warn(
            f"PRESS-TONNAGE-EXCEEDED: computed forging load {F_MN:.1f} MN exceeds "
            "100 MN — consider splitting the forging or using multiple heats.",
            warninglist,
        )

    return {
        "ok": True,
        "sigma_f_Pa": sf,
        "A_proj_m2": Ap,
        "Kf": kf,
        "F_N": F,
        "F_MN": F_MN,
        "F_tonnesf": F_tonf,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 5. forward_extrusion
# ---------------------------------------------------------------------------

def forward_extrusion(
    sigma_f: float,
    A0: float,
    Af: float,
    mu: float = 0.05,
    die_half_angle_deg: float = 45.0,
    L: float = 0.0,
) -> dict:
    """
    Forward (direct) extrusion pressure and force.

    The extrusion pressure for forward extrusion is estimated using the
    modified upper-bound formula (Johnson/Altan):

        p_e = σ̄_f · (B · ln(R) + p_friction)

    where the total specific extrusion pressure (per unit billet area) is:

        p_e / σ̄_f = (1 + μ/tan(α)) · ln(A0/Af) + friction_billet_container

    Simplified form used here (Kalpakjian §15.2 combined ideal + redundant
    + friction approach):

        p_e = σ̄_f · [ln(R) · (1 + B) + μ · π · D0 · L / A0]

    where:
      R   — extrusion ratio = A0 / Af
      B   — redundant-work factor ≈ 0.8 + 1.2·tan(α)  (α = die half-angle)
      L   — billet length remaining in container (m); friction over container wall
      D0  — billet diameter = 2·sqrt(A0/π)
      μ   — friction coefficient (container / die interface)

    Parameters
    ----------
    sigma_f : float
        Mean flow stress of billet material (Pa).  Must be > 0.
    A0 : float
        Billet (container bore) cross-sectional area (m²).  Must be > 0.
    Af : float
        Extrudate (product) cross-sectional area (m²).  Must be > 0 and < A0.
    mu : float
        Friction coefficient at billet–container and billet–die interfaces
        (default 0.05 — lubricated extrusion).  Must be >= 0.
    die_half_angle_deg : float
        Die half-angle α (degrees, measured from the extrusion axis).
        Default 45° (flat die).  Valid range: 0 < α < 90°.
    L : float
        Length of billet remaining in the container (m).  Used for
        container-wall friction component.  Default 0.0 (no container friction).
        Must be >= 0.

    Returns
    -------
    dict
        ok                   : True
        sigma_f_Pa           : mean flow stress (Pa)
        A0_m2                : billet area (m²)
        Af_m2                : extrudate area (m²)
        extrusion_ratio      : R = A0 / Af
        true_strain          : ε = ln(R)
        die_half_angle_deg   : die half-angle (°)
        redundant_factor_B   : B = 0.8 + 1.2·tan(α)
        mu                   : friction coefficient used
        p_ideal_Pa           : ideal extrusion pressure (σ̄_f · ln R) (Pa)
        p_e_Pa               : total extrusion pressure including friction
                               and redundant work (Pa)
        F_N                  : extrusion force = p_e × A0 (N)
        F_MN                 : extrusion force (MN)
        warnings             : list of warning strings

    Notes
    -----
    A warning is issued if:
      - extrusion_ratio > 20 (very high — fracture / dead-metal-zone risk)
      - die_half_angle < 5° (excessive friction on die face / scoring risk)
      - die_half_angle > 60° (severe redundant work / adiabatic heating)
    """
    warninglist: list[str] = []

    err = _guard_positive("sigma_f", sigma_f)
    if err:
        return _err(err)
    err = _guard_positive("A0", A0)
    if err:
        return _err(err)
    err = _guard_positive("Af", Af)
    if err:
        return _err(err)
    err = _guard_nonneg("mu", mu)
    if err:
        return _err(err)
    err = _guard_positive("die_half_angle_deg", die_half_angle_deg)
    if err:
        return _err(err)
    err = _guard_nonneg("L", L)
    if err:
        return _err(err)

    sf = float(sigma_f)
    a0 = float(A0)
    af = float(Af)
    mu_v = float(mu)
    alpha_deg = float(die_half_angle_deg)
    Lv = float(L)

    if af >= a0:
        return _err(
            f"Af={af} m² must be < A0={a0} m² (area must be reduced in extrusion)."
        )
    if alpha_deg >= 90.0:
        return _err(
            f"die_half_angle_deg={alpha_deg}° must be < 90°."
        )

    alpha_rad = math.radians(alpha_deg)
    R = a0 / af  # extrusion ratio
    eps_true = math.log(R)

    # Redundant-work factor B (Kalpakjian Eq 15.3)
    B = 0.8 + 1.2 * math.tan(alpha_rad)

    # Ideal pressure
    p_ideal = sf * eps_true

    # Redundant work contribution
    p_redundant = sf * (B - 1.0) * eps_true  # = sf·eps·(B-1)

    # Container-wall friction (billet–container friction over remaining length L)
    D0 = 2.0 * math.sqrt(a0 / math.pi)
    p_friction_container = (
        mu_v * math.pi * D0 * Lv / a0 * sf
    ) if Lv > 0.0 else 0.0

    p_e = p_ideal + p_redundant + p_friction_container
    F = p_e * a0
    F_MN = F / 1e6

    if R > 20.0:
        _warn(
            f"Extrusion ratio R={R:.1f} > 20 — risk of fracture / dead-metal zone; "
            "consider warm/hot extrusion or multiple-pass process.",
            warninglist,
        )
    if alpha_deg < 5.0:
        _warn(
            f"Die half-angle {alpha_deg}° < 5° — excessive friction on die land; "
            "scoring and galling risk.",
            warninglist,
        )
    if alpha_deg > 60.0:
        _warn(
            f"Die half-angle {alpha_deg}° > 60° — severe redundant work and "
            "adiabatic heating expected; verify thermal limits.",
            warninglist,
        )
    if F_MN > 50.0:
        _warn(
            f"PRESS-TONNAGE-EXCEEDED: extrusion force {F_MN:.1f} MN exceeds 50 MN — "
            "consider reducing billet size or extrusion ratio.",
            warninglist,
        )

    return {
        "ok": True,
        "sigma_f_Pa": sf,
        "A0_m2": a0,
        "Af_m2": af,
        "extrusion_ratio": R,
        "true_strain": eps_true,
        "die_half_angle_deg": alpha_deg,
        "redundant_factor_B": B,
        "mu": mu_v,
        "p_ideal_Pa": p_ideal,
        "p_redundant_Pa": p_redundant,
        "p_friction_container_Pa": p_friction_container,
        "p_e_Pa": p_e,
        "F_N": F,
        "F_MN": F_MN,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 6. backward_extrusion
# ---------------------------------------------------------------------------

def backward_extrusion(
    sigma_f: float,
    A0: float,
    Af: float,
    mu: float = 0.05,
    die_half_angle_deg: float = 45.0,
) -> dict:
    """
    Backward (indirect) extrusion pressure and force.

    In backward (indirect) extrusion the billet does not slide against the
    container wall — the die moves into the billet.  This eliminates
    container-wall friction, so the extrusion pressure is lower than for
    forward extrusion.  The billet–container friction term (μπDL/A0) vanishes.

    The extrusion pressure formula (same ideal + redundant, no container friction):

        p_e = σ̄_f · B · ln(R)

    where B = 0.8 + 1.2·tan(α) is the redundant-work factor.

    Parameters
    ----------
    sigma_f : float
        Mean flow stress of billet material (Pa).  Must be > 0.
    A0 : float
        Billet (container bore) cross-sectional area (m²).  Must be > 0.
    Af : float
        Extrudate (product) cross-sectional area (m²).  Must be > 0 and < A0.
    mu : float
        Friction coefficient at die–workpiece interface (default 0.05).
        Must be >= 0.  (Container friction is zero in backward extrusion.)
    die_half_angle_deg : float
        Die half-angle α (degrees).  Default 45°.  Valid range: 0 < α < 90°.

    Returns
    -------
    dict
        ok                   : True
        sigma_f_Pa           : mean flow stress (Pa)
        A0_m2                : billet area (m²)
        Af_m2                : extrudate area (m²)
        extrusion_ratio      : R = A0 / Af
        true_strain          : ε = ln(R)
        die_half_angle_deg   : die half-angle (°)
        redundant_factor_B   : B = 0.8 + 1.2·tan(α)
        mu                   : friction coefficient used
        p_ideal_Pa           : ideal extrusion pressure (σ̄_f · ln R) (Pa)
        p_e_Pa               : backward extrusion pressure (Pa)
        F_N                  : extrusion force = p_e × A0 (N)
        F_MN                 : extrusion force (MN)
        forward_vs_backward_ratio: p_e_backward / (p_e_forward at same L=0)
        warnings             : list of warning strings
    """
    warninglist: list[str] = []

    err = _guard_positive("sigma_f", sigma_f)
    if err:
        return _err(err)
    err = _guard_positive("A0", A0)
    if err:
        return _err(err)
    err = _guard_positive("Af", Af)
    if err:
        return _err(err)
    err = _guard_nonneg("mu", mu)
    if err:
        return _err(err)
    err = _guard_positive("die_half_angle_deg", die_half_angle_deg)
    if err:
        return _err(err)

    sf = float(sigma_f)
    a0 = float(A0)
    af = float(Af)
    alpha_deg = float(die_half_angle_deg)

    if af >= a0:
        return _err(
            f"Af={af} m² must be < A0={a0} m² (area must be reduced in extrusion)."
        )
    if alpha_deg >= 90.0:
        return _err(
            f"die_half_angle_deg={alpha_deg}° must be < 90°."
        )

    alpha_rad = math.radians(alpha_deg)
    R = a0 / af
    eps_true = math.log(R)

    B = 0.8 + 1.2 * math.tan(alpha_rad)
    p_ideal = sf * eps_true
    p_e = sf * B * eps_true   # no container friction
    F = p_e * a0
    F_MN = F / 1e6

    # Forward at same parameters (L=0)
    p_forward = sf * B * eps_true  # same without container term
    ratio = p_e / p_forward if p_forward > 0 else 1.0

    if R > 20.0:
        _warn(
            f"Extrusion ratio R={R:.1f} > 20 — risk of fracture; consider multiple passes.",
            warninglist,
        )
    if F_MN > 50.0:
        _warn(
            f"PRESS-TONNAGE-EXCEEDED: backward extrusion force {F_MN:.1f} MN exceeds 50 MN.",
            warninglist,
        )

    return {
        "ok": True,
        "sigma_f_Pa": sf,
        "A0_m2": a0,
        "Af_m2": af,
        "extrusion_ratio": R,
        "true_strain": eps_true,
        "die_half_angle_deg": alpha_deg,
        "redundant_factor_B": B,
        "mu": float(mu),
        "p_ideal_Pa": p_ideal,
        "p_e_Pa": p_e,
        "F_N": F,
        "F_MN": F_MN,
        "forward_vs_backward_ratio": ratio,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 7. flat_rolling
# ---------------------------------------------------------------------------

def flat_rolling(
    sigma_f: float,
    mu: float,
    R: float,
    h0: float,
    hf: float,
    w: float,
    omega_rad_s: float = 0.0,
) -> dict:
    """
    Flat rolling: contact length, roll force, torque, power, and neutral point.

    Flat (strip/sheet) rolling analysis using the mean flow stress and the
    friction-hill approximation.

    Contact length (geometric):
        L_c = sqrt(R · Δh)   where Δh = h0 - hf

    Roll force (mean flow stress × contact area):
        F = σ̄_f · w · L_c · p_friction

    Friction-hill correction factor (Siebel/Shohet approximation):
        p_friction = 1 + μ·L_c / (2·h_avg)
        where h_avg = (h0 + hf) / 2

    Torque (per roll, both rolls equal):
        T = F · L_c / 2

    Power (two rolls):
        P = 2 · T · ω   (if angular velocity ω given)

    Neutral point (angle φ_n where strip and roll speeds equal):
        φ_n ≈ φ_entry / 2 · (1 - μ/tan(φ_entry))    (approximation)
        where φ_entry = sqrt(Δh / R) (entry angle in radians)

    Max draft from bite condition:
        Δh_max = μ² · R

    Roll flattening note: when roll force is high relative to roll stiffness,
    rolls flatten (Hitchcock radius R' > R); this function flags the condition
    but does not compute R' (requires material constants of the rolls).

    Parameters
    ----------
    sigma_f : float
        Mean flow stress of the strip (Pa).  Must be > 0.
    mu : float
        Friction coefficient between strip and rolls.  Must be > 0.
    R : float
        Roll radius (m).  Must be > 0.
    h0 : float
        Incoming strip thickness (m).  Must be > 0.
    hf : float
        Outgoing strip thickness (m).  Must be > 0 and < h0.
    w : float
        Strip width (m).  Must be > 0.
    omega_rad_s : float
        Angular velocity of each roll (rad/s).  Default 0 (power not computed).
        Must be >= 0.

    Returns
    -------
    dict
        ok                  : True
        sigma_f_Pa          : mean flow stress (Pa)
        mu                  : friction coefficient
        R_m                 : roll radius (m)
        h0_m                : incoming thickness (m)
        hf_m                : outgoing thickness (m)
        delta_h_m           : draft = h0 - hf (m)
        w_m                 : strip width (m)
        reduction_pct       : thickness reduction (%)
        true_strain         : ε = ln(h0/hf)
        contact_length_m    : L_c = sqrt(R·Δh) (m)
        bite_angle_deg      : φ_entry = arctan(L_c/R) (°)
        max_draft_m         : Δh_max = μ²·R (m); draft feasible if Δh <= Δh_max
        draft_feasible      : True if Δh <= max_draft_m
        h_avg_m             : average thickness = (h0 + hf) / 2 (m)
        friction_hill_factor: 1 + μ·L_c/(2·h_avg)
        F_N                 : roll separating force (N)
        F_MN                : roll force (MN)
        torque_per_roll_Nm  : torque on each roll = F·L_c/2 (N·m)
        power_W             : rolling power = 2·T·ω (W); 0.0 if ω=0
        neutral_point_deg   : approx. neutral-point angle from exit (°)
        roll_flattening_note: advisory string
        warnings            : list of warning strings

    Notes
    -----
    Warnings are issued if:
      - draft > max_draft (bite condition violated — rolls cannot grip strip)
      - reduction > 50 % per pass (large single-pass reduction risk)
      - power > 10 MW (large mill power)
    """
    warninglist: list[str] = []

    err = _guard_positive("sigma_f", sigma_f)
    if err:
        return _err(err)
    err = _guard_positive("mu", mu)
    if err:
        return _err(err)
    err = _guard_positive("R", R)
    if err:
        return _err(err)
    err = _guard_positive("h0", h0)
    if err:
        return _err(err)
    err = _guard_positive("hf", hf)
    if err:
        return _err(err)
    err = _guard_positive("w", w)
    if err:
        return _err(err)
    err = _guard_nonneg("omega_rad_s", omega_rad_s)
    if err:
        return _err(err)

    sf = float(sigma_f)
    mu_v = float(mu)
    Rv = float(R)
    h0v = float(h0)
    hfv = float(hf)
    wv = float(w)
    omega = float(omega_rad_s)

    if hfv >= h0v:
        return _err(
            f"hf={hfv} m must be < h0={h0v} m (strip must be reduced in rolling)."
        )

    dh = h0v - hfv
    reduction_pct = dh / h0v * 100.0
    eps_true = math.log(h0v / hfv)

    # Contact length
    Lc = math.sqrt(Rv * dh)

    # Bite angle
    bite_angle_rad = math.atan(Lc / Rv)
    bite_angle_deg = math.degrees(bite_angle_rad)

    # Max draft from bite condition
    dh_max = mu_v ** 2 * Rv
    draft_feasible = dh <= dh_max

    # Average thickness
    h_avg = (h0v + hfv) / 2.0

    # Friction-hill correction
    ff = 1.0 + mu_v * Lc / (2.0 * h_avg)

    # Roll separating force
    F = sf * wv * Lc * ff
    F_MN = F / 1e6

    # Torque per roll
    T = F * Lc / 2.0

    # Power (two rolls)
    P = 2.0 * T * omega if omega > 0.0 else 0.0

    # Neutral point angle (approximation from Hosford & Caddell)
    # φ_n ≈ φ_entry * (1 - μ/tan(φ_entry)) / 2   (only if tan > mu)
    if bite_angle_deg > 0.0 and math.tan(bite_angle_rad) > mu_v:
        phi_n_rad = bite_angle_rad * (1.0 - mu_v / math.tan(bite_angle_rad)) / 2.0
        neutral_pt_deg = math.degrees(phi_n_rad)
    else:
        neutral_pt_deg = 0.0

    flattening_note = (
        "Roll flattening (Hitchcock effect) may increase effective roll radius "
        "when roll force is large relative to roll bending stiffness. "
        "Compute R' = R·(1 + 16F/(π·E·w·Δh)) where E is roll Young's modulus."
    )

    if not draft_feasible:
        _warn(
            f"EXCEEDS-BITE-LIMIT: draft Δh={dh*1000:.2f} mm exceeds max draft "
            f"Δh_max=μ²R={dh_max*1000:.2f} mm — rolls cannot grip the strip.",
            warninglist,
        )
    if reduction_pct > 50.0:
        _warn(
            f"Reduction {reduction_pct:.1f}% per pass > 50% — large single-pass "
            "reduction; verify material ductility and mill load capacity.",
            warninglist,
        )
    if P > 10.0e6:
        _warn(
            f"Rolling power {P/1e6:.1f} MW > 10 MW — verify mill motor capacity.",
            warninglist,
        )

    return {
        "ok": True,
        "sigma_f_Pa": sf,
        "mu": mu_v,
        "R_m": Rv,
        "h0_m": h0v,
        "hf_m": hfv,
        "delta_h_m": dh,
        "w_m": wv,
        "reduction_pct": reduction_pct,
        "true_strain": eps_true,
        "contact_length_m": Lc,
        "bite_angle_deg": bite_angle_deg,
        "max_draft_m": dh_max,
        "draft_feasible": draft_feasible,
        "h_avg_m": h_avg,
        "friction_hill_factor": ff,
        "F_N": F,
        "F_MN": F_MN,
        "torque_per_roll_Nm": T,
        "power_W": P,
        "neutral_point_deg": neutral_pt_deg,
        "roll_flattening_note": flattening_note,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 8. wire_drawing
# ---------------------------------------------------------------------------

def wire_drawing(
    sigma_f: float,
    A0: float,
    Af: float,
    mu: float = 0.05,
    die_half_angle_deg: float = 8.0,
) -> dict:
    """
    Wire/bar drawing: drawing stress, force, max reduction, limiting reduction.

    The drawing stress for wire or rod drawing through a conical die is
    estimated using the Hosford–Caddell (slab analysis) formula:

        σ_d = σ̄_f · B · (1 - (Af/A0)^B)

    where:
        B = μ · cot(α)      (friction-geometry parameter)
        α = die_half_angle  (radians)
        μ = Coulomb friction coefficient

    This form (from Hosford & Caddell §6.5 / Kalpakjian §15.5) includes:
      - Ideal work: σ̄_f · ln(A0/Af)
      - Friction correction: multiplied by B/(B–1) factor
      - Redundant work: approximated through die-angle term

    Maximum reduction per pass (Hosford–Caddell):
        r_max = 1 - exp(–1/B)
        (when σ_d → σ̄_f, i.e. wire breaks as it exits)

    Limiting (theoretical maximum) reduction for frictionless ideal drawing:
        r_limit → 1 - 1/e ≈ 63.2%  (when B → ∞, i.e. μ → 0, α → 0)

    In practice, single-pass reductions are limited to ~25–45% for cold drawing.

    Parameters
    ----------
    sigma_f : float
        Mean flow stress of the wire/bar material (Pa).  Must be > 0.
    A0 : float
        Initial wire/bar cross-sectional area (m²).  Must be > 0.
    Af : float
        Final wire/bar cross-sectional area (m²).  Must be > 0 and < A0.
    mu : float
        Coulomb friction coefficient at wire–die interface (default 0.05).
        Must be >= 0.
    die_half_angle_deg : float
        Die semi-angle α (degrees, measured from wire axis).  Default 8°.
        Valid range: 0 < α < 90°.

    Returns
    -------
    dict
        ok                  : True
        sigma_f_Pa          : mean flow stress (Pa)
        A0_m2               : initial area (m²)
        Af_m2               : final area (m²)
        true_strain         : ε = ln(A0/Af)
        reduction_pct       : area reduction r = (1 - Af/A0)×100 (%)
        die_half_angle_deg  : die half-angle (°)
        mu                  : friction coefficient
        B_factor            : B = μ·cot(α)
        sigma_d_Pa          : drawing stress (Pa)
        sigma_d_over_sigmaf : σ_d / σ̄_f (< 1 required for feasibility)
        F_N                 : drawing force = σ_d × Af (N)
        max_reduction_pct   : maximum single-pass reduction r_max = (1 - e^{-1/B})×100 (%)
        limiting_reduction_pct: theoretical limit ≈ 63.2 % (frictionless ideal)
        feasible            : True if σ_d < σ̄_f
        warnings            : list of warning strings

    Notes
    -----
    Warnings are issued if:
      - σ_d / σ̄_f > 1 (EXCEEDS-LIMIT-REDUCTION: wire will break at die exit)
      - reduction > max_reduction (same physical condition)
      - die_half_angle < 3° (excessive friction / galling)
      - die_half_angle > 30° (large redundant work / temperature rise)
    """
    warninglist: list[str] = []

    err = _guard_positive("sigma_f", sigma_f)
    if err:
        return _err(err)
    err = _guard_positive("A0", A0)
    if err:
        return _err(err)
    err = _guard_positive("Af", Af)
    if err:
        return _err(err)
    err = _guard_nonneg("mu", mu)
    if err:
        return _err(err)
    err = _guard_positive("die_half_angle_deg", die_half_angle_deg)
    if err:
        return _err(err)

    sf = float(sigma_f)
    a0 = float(A0)
    af = float(Af)
    mu_v = float(mu)
    alpha_deg = float(die_half_angle_deg)

    if af >= a0:
        return _err(
            f"Af={af} m² must be < A0={a0} m² (wire must be reduced in drawing)."
        )
    if alpha_deg >= 90.0:
        return _err(
            f"die_half_angle_deg={alpha_deg}° must be < 90°."
        )

    alpha_rad = math.radians(alpha_deg)
    eps_true = math.log(a0 / af)
    reduction = (1.0 - af / a0)
    reduction_pct = reduction * 100.0

    # B factor
    if alpha_rad > 0.0:
        B = mu_v / math.tan(alpha_rad)
    else:
        B = 1e9  # limiting case: frictionless/small angle

    # Drawing stress (Hosford-Caddell slab analysis)
    # σ_d = σ̄_f · (B/(B-1)) · [1 - (Af/A0)^((B-1)/B)]    (B ≠ 1)
    # For B = 0 (no friction, not useful) or B very small, approximate
    if abs(B) < 1e-9:
        # frictionless: σ_d = σ̄_f · ln(A0/Af)
        sigma_d = sf * eps_true
    elif abs(B - 1.0) < 1e-9:
        # B → 1 limiting form: σ_d = σ̄_f · ln(A0/Af)
        sigma_d = sf * eps_true
    else:
        # Hosford-Caddell general form
        sigma_d = sf * (B / (B - 1.0)) * (1.0 - (af / a0) ** ((B - 1.0) / B))

    sigma_d_ratio = sigma_d / sf
    F = sigma_d * af

    # Max reduction per pass
    if B > 0.0:
        r_max = 1.0 - math.exp(-1.0 / B) if B > 1e-6 else 1.0 - 1.0 / math.e
    else:
        r_max = 1.0 - 1.0 / math.e

    r_max_pct = r_max * 100.0
    limiting_pct = (1.0 - 1.0 / math.e) * 100.0  # ≈ 63.2%

    feasible = sigma_d_ratio < 1.0

    if not feasible:
        _warn(
            f"EXCEEDS-LIMIT-REDUCTION: drawing stress / flow stress = {sigma_d_ratio:.3f} >= 1.0 "
            "— wire will fracture at die exit; reduce draft per pass.",
            warninglist,
        )
    elif reduction_pct > r_max_pct:
        _warn(
            f"Reduction {reduction_pct:.1f}% > theoretical max {r_max_pct:.1f}% per pass — "
            "wire fracture risk; reduce draft.",
            warninglist,
        )
    if alpha_deg < 3.0:
        _warn(
            f"Die half-angle {alpha_deg}° < 3° — excessive friction on die land; galling risk.",
            warninglist,
        )
    if alpha_deg > 30.0:
        _warn(
            f"Die half-angle {alpha_deg}° > 30° — large redundant work and temperature rise.",
            warninglist,
        )

    return {
        "ok": True,
        "sigma_f_Pa": sf,
        "A0_m2": a0,
        "Af_m2": af,
        "true_strain": eps_true,
        "reduction_pct": reduction_pct,
        "die_half_angle_deg": alpha_deg,
        "mu": mu_v,
        "B_factor": B,
        "sigma_d_Pa": sigma_d,
        "sigma_d_over_sigmaf": sigma_d_ratio,
        "F_N": F,
        "max_reduction_pct": r_max_pct,
        "limiting_reduction_pct": limiting_pct,
        "feasible": feasible,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 9. forming_work
# ---------------------------------------------------------------------------

def forming_work(
    F_N: float,
    displacement_m: float,
    eta: float = 1.0,
    rho: float = 7850.0,
    Cp: float = 502.0,
    volume_m3: float = 0.0,
) -> dict:
    """
    Mechanical work / energy and adiabatic temperature rise.

    In bulk forming, the work done by the press equals the deformation energy:

        W = F · d / η

    where η is the press/machine efficiency.

    For the adiabatic temperature rise (an upper bound, ignoring heat loss
    to tools and environment):

        ΔT = W / (ρ · V · C_p)

    where ρ is density (kg/m³), V is workpiece volume (m³), C_p is specific
    heat capacity (J/kg·K).

    Parameters
    ----------
    F_N : float
        Average forming force (N).  Must be > 0.
    displacement_m : float
        Total press stroke / displacement (m).  Must be > 0.
    eta : float
        Machine efficiency (default 1.0 — no losses).  Range (0, 1].
    rho : float
        Workpiece density (kg/m³).  Default 7850 (steel).  Must be > 0.
        Used only if volume_m3 > 0.
    Cp : float
        Specific heat capacity (J/kg·K).  Default 502 (steel).  Must be > 0.
        Used only if volume_m3 > 0.
    volume_m3 : float
        Workpiece volume (m³).  Default 0.0 (temperature rise not computed).
        Must be >= 0.

    Returns
    -------
    dict
        ok                  : True
        F_N                 : forming force (N)
        displacement_m      : press stroke (m)
        eta                 : machine efficiency
        W_J                 : forming work W = F·d / η (J)
        W_kJ                : forming work (kJ)
        delta_T_C           : adiabatic temperature rise (°C); 0.0 if volume_m3=0
        warnings            : list of warning strings

    Notes
    -----
    The adiabatic temperature rise is an upper bound — actual temperature rise
    will be lower due to heat loss to dies, tools, and environment.
    Significant temperature rises (ΔT > 200°C) can affect material properties
    and die life.
    """
    warninglist: list[str] = []

    err = _guard_positive("F_N", F_N)
    if err:
        return _err(err)
    err = _guard_positive("displacement_m", displacement_m)
    if err:
        return _err(err)
    err = _guard_positive("eta", eta)
    if err:
        return _err(err)
    if float(eta) > 1.0:
        return _err(f"eta must be <= 1.0, got {eta}")
    err = _guard_positive("rho", rho)
    if err:
        return _err(err)
    err = _guard_positive("Cp", Cp)
    if err:
        return _err(err)
    err = _guard_nonneg("volume_m3", volume_m3)
    if err:
        return _err(err)

    F = float(F_N)
    d = float(displacement_m)
    eta_v = float(eta)
    rho_v = float(rho)
    Cp_v = float(Cp)
    V = float(volume_m3)

    W = F * d / eta_v
    W_kJ = W / 1000.0

    delta_T = 0.0
    if V > 0.0:
        mass = rho_v * V
        delta_T = W / (mass * Cp_v)
        if delta_T > 200.0:
            _warn(
                f"Adiabatic temperature rise ΔT = {delta_T:.1f}°C > 200°C — "
                "significant thermal softening and die wear expected.",
                warninglist,
            )

    return {
        "ok": True,
        "F_N": F,
        "displacement_m": d,
        "eta": eta_v,
        "W_J": W,
        "W_kJ": W_kJ,
        "delta_T_C": delta_T,
        "warnings": warninglist,
    }


# ---------------------------------------------------------------------------
# 10. passes_required
# ---------------------------------------------------------------------------

def passes_required(
    r_total: float,
    r_per_pass: float,
) -> dict:
    """
    Minimum number of passes to achieve a total area/thickness reduction.

    For a sequence of rolling or drawing passes each with fractional reduction r,
    the cumulative reduction after N passes is:

        r_cumulative = 1 - (1 - r_per_pass)^N

    Solving for N (minimum integer passes to reach r_total):

        N = ceil(ln(1 - r_total) / ln(1 - r_per_pass))

    True strain per pass: ε = -ln(1 - r_per_pass)
    Total true strain: ε_total = N · ε_per_pass

    Parameters
    ----------
    r_total : float
        Total fractional reduction required, e.g. 0.75 for 75% area reduction.
        Range: (0, 1).
    r_per_pass : float
        Fractional reduction per individual pass, e.g. 0.20 for 20%.
        Range: (0, 1).  Must be < r_total (except if single-pass sufficient).

    Returns
    -------
    dict
        ok                  : True
        r_total             : total reduction fraction
        r_per_pass          : per-pass reduction fraction
        n_passes            : minimum number of passes (integer)
        eps_per_pass        : true strain per pass = ln(1/(1-r_per_pass))
        eps_total           : total accumulated true strain = n_passes × ε_pass
        cumulative_reduction_pct: actual cumulative reduction after n_passes (%)
        total_reduction_pct : target total reduction (%)
        per_pass_reduction_pct : per-pass reduction (%)
        warnings            : list of warning strings

    Notes
    -----
    If r_per_pass >= r_total, a single pass is sufficient.
    A warning is issued if n_passes > 20 (many passes → consider annealing
    between passes to restore ductility).
    """
    warninglist: list[str] = []

    err = _guard_positive("r_total", r_total)
    if err:
        return _err(err)
    err = _guard_positive("r_per_pass", r_per_pass)
    if err:
        return _err(err)

    rt = float(r_total)
    rp = float(r_per_pass)

    if rt >= 1.0:
        return _err(f"r_total={rt} must be < 1.0 (100% reduction is not physical).")
    if rp >= 1.0:
        return _err(f"r_per_pass={rp} must be < 1.0.")

    # If a single pass achieves the total reduction
    if rp >= rt:
        n = 1
    else:
        # ceil(ln(1-r_total) / ln(1-r_per_pass))
        # ln(1-r) < 0 for 0 < r < 1; both numerator and denominator are negative → positive ratio
        n = math.ceil(math.log(1.0 - rt) / math.log(1.0 - rp))

    eps_pass = math.log(1.0 / (1.0 - rp))
    eps_total = n * eps_pass
    r_actual = 1.0 - (1.0 - rp) ** n
    r_actual_pct = r_actual * 100.0

    if n > 20:
        _warn(
            f"n_passes={n} > 20 — many passes required; consider intermediate annealing "
            "to restore ductility and avoid fracture.",
            warninglist,
        )

    return {
        "ok": True,
        "r_total": rt,
        "r_per_pass": rp,
        "n_passes": n,
        "eps_per_pass": eps_pass,
        "eps_total": eps_total,
        "cumulative_reduction_pct": r_actual_pct,
        "total_reduction_pct": rt * 100.0,
        "per_pass_reduction_pct": rp * 100.0,
        "warnings": warninglist,
    }
