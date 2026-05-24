"""
kerf_cad_core.clutchbrake.design — pure-Python friction clutch & brake design.

Implements:

  Clutches
  --------
  disc_clutch_torque    — disc/plate clutch (uniform-wear, uniform-pressure,
                          multi-plate); actuation force
  cone_clutch_torque    — cone clutch torque & actuation force
  disc_brake_torque     — caliper disc brake

  Brakes
  ------
  band_brake_torque     — flexible band brake (tight side, slack side,
                          self-energizing factor)
  drum_brake_torque     — short-shoe and long-shoe drum brake (leading/trailing,
                          self-energizing & dragging; net torque)

  Thermal & Wear
  --------------
  engagement_energy     — energy dissipated in single engagement
                          (inertia + load contribution)
  temperature_rise      — lumped thermal rise per engagement
  heat_dissipation_area — minimum area required to reject heat
  wear_pv_check         — pV limit check against material catalog
  engagement_time       — time to synchronise + slip energy

  Catalog
  -------
  friction_material_props — return μ, max_pV, max_temp for material name

All functions return plain dict {"ok": True, ...} or {"ok": False, "reason": ...}.
Warnings (pV exceeded, over-temp, self-locking) are returned as a "warnings" list
inside ok responses — never raised as exceptions.

Units
-----
  lengths   — metres (m)
  forces    — Newtons (N)
  moments   — Newton-metres (N·m)
  pressure  — Pascals (Pa)
  stress    — Pascals (Pa)
  speed     — rad/s (angular)  or  rpm (where noted)
  energy    — Joules (J)
  power     — Watts (W)
  temp      — Kelvin delta (ΔK) for rises; °C for absolute limits
  area      — m²
  pV        — Pa·m/s  (pressure × velocity)

References
----------
Shigley's Mechanical Engineering Design, 10th ed., §§ 16-1 to 16-12
Juvinall & Marshek, Machine Component Design, 5th ed., §§ 18.1-18.9
Norton, Machine Design, 5th ed., Chapter 16

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_FRICTION_MATERIALS: dict[str, dict[str, float]] = {
    # name                 μ_dry   max_pV (Pa·m/s)  max_temp (°C)
    "cast_iron_dry":     {"mu": 0.40, "max_pv": 1.75e6, "max_temp": 250.0},
    "cast_iron_wet":     {"mu": 0.12, "max_pv": 3.50e6, "max_temp": 250.0},
    "steel_dry":         {"mu": 0.15, "max_pv": 0.70e6, "max_temp": 250.0},
    "bronze_dry":        {"mu": 0.20, "max_pv": 0.56e6, "max_temp": 150.0},
    "asbestos_dry":      {"mu": 0.40, "max_pv": 1.05e6, "max_temp": 300.0},
    "asbestos_wet":      {"mu": 0.12, "max_pv": 3.50e6, "max_temp": 300.0},
    "molded_dry":        {"mu": 0.35, "max_pv": 1.75e6, "max_temp": 300.0},
    "molded_wet":        {"mu": 0.06, "max_pv": 3.50e6, "max_temp": 300.0},
    "paper_wet":         {"mu": 0.10, "max_pv": 5.25e6, "max_temp": 120.0},
    "sintered_metal_dry":{"mu": 0.35, "max_pv": 1.75e6, "max_temp": 600.0},
    "cork_dry":          {"mu": 0.35, "max_pv": 0.35e6, "max_temp":  80.0},
    "wood_dry":          {"mu": 0.35, "max_pv": 0.53e6, "max_temp":  80.0},
    "carbon_graphite":   {"mu": 0.25, "max_pv": 7.00e6, "max_temp": 500.0},
}


def friction_material_props(material: str) -> dict:
    """
    Return friction material properties from the built-in catalog.

    Parameters
    ----------
    material : str
        Material name (see catalog keys).

    Returns
    -------
    dict
        ok        : True
        material  : name (normalised)
        mu        : dry coefficient of friction (dimensionless)
        max_pv    : maximum allowable pV product (Pa·m/s)
        max_temp  : maximum allowable surface temperature (°C)
        available : list of all material names (always present)
    """
    mat = str(material).strip().lower().replace(" ", "_").replace("-", "_")
    available = list(_FRICTION_MATERIALS.keys())
    if mat not in _FRICTION_MATERIALS:
        return {
            "ok": False,
            "reason": f"Unknown material {material!r}.",
            "available": available,
        }
    props = _FRICTION_MATERIALS[mat]
    return {
        "ok": True,
        "material": mat,
        "mu": props["mu"],
        "max_pv": props["max_pv"],
        "max_temp": props["max_temp"],
        "available": available,
    }


# ---------------------------------------------------------------------------
# 1. Disc / plate clutch torque
# ---------------------------------------------------------------------------

def disc_clutch_torque(
    F_a: float,
    mu: float,
    r_o: float,
    r_i: float,
    *,
    method: str = "uniform-wear",
    n_plates: int = 1,
) -> dict:
    """
    Torque capacity and actuation force relationship for a disc / plate clutch.

    Supports uniform-wear (preferred for design) and uniform-pressure theories.
    Multi-plate clutches use n_friction_surfaces = 2 × n_plates for a pack
    with n_plates friction discs (each face engages).

    Parameters
    ----------
    F_a : float
        Axial actuation force (N). Must be > 0.
    mu : float
        Coefficient of friction. Must be > 0.
    r_o : float
        Outer friction radius (m). Must be > r_i.
    r_i : float
        Inner friction radius (m). Must be >= 0.
    method : str
        'uniform-wear'     (default) — conservative, Shigley §16-2
        'uniform-pressure' — new/relapped surfaces, Shigley §16-2
    n_plates : int
        Number of friction disc pairs (each pair adds 2 friction surfaces).
        Default 1 (single-plate: 2 friction surfaces total).

    Returns
    -------
    dict
        ok             : True
        torque_Nm      : total clutch torque (N·m)
        T_per_surface  : torque per friction surface (N·m)
        n_surfaces     : total number of friction surfaces
        r_mean_m       : effective friction radius (m)
        F_a_N          : actuation force used (N)
        mu             : friction coefficient used
        method         : theory used
        warnings       : list[str]
    """
    warns: list[str] = []

    err = _guard_positive("F_a", F_a)
    if err:
        return _err(err)
    err = _guard_positive("mu", mu)
    if err:
        return _err(err)
    err = _guard_positive("r_o", r_o)
    if err:
        return _err(err)
    err = _guard_nonneg("r_i", r_i)
    if err:
        return _err(err)

    if r_i >= r_o:
        return _err(f"r_i ({r_i}) must be < r_o ({r_o})")

    try:
        n_p = int(n_plates)
    except (TypeError, ValueError):
        return _err(f"n_plates must be an integer, got {n_plates!r}")
    if n_p < 1:
        return _err(f"n_plates must be >= 1, got {n_p}")

    n_surfaces = 2 * n_p  # each plate pack has 2 friction surfaces per disc pair

    meth = str(method).strip().lower().replace("-", "").replace("_", "").replace(" ", "")

    if meth in ("uniformwear", "wear"):
        # Shigley §16-2: r_mean = (r_o + r_i) / 2
        r_mean = (r_o + r_i) / 2.0
    elif meth in ("uniformpressure", "pressure"):
        # Shigley §16-2: r_mean = (2/3) × (r_o³ - r_i³) / (r_o² - r_i²)
        num = r_o ** 3 - r_i ** 3
        den = r_o ** 2 - r_i ** 2
        r_mean = (2.0 / 3.0) * (num / den)
    else:
        return _err(
            f"Unknown method {method!r}. Supported: 'uniform-wear', 'uniform-pressure'."
        )

    T_per = mu * F_a * r_mean
    T_total = T_per * n_surfaces

    if mu > 0.6:
        warns.append(f"mu={mu:.3f} is unusually high (>0.6); verify material pairing.")

    return {
        "ok": True,
        "torque_Nm": T_total,
        "T_per_surface": T_per,
        "n_surfaces": n_surfaces,
        "r_mean_m": r_mean,
        "F_a_N": float(F_a),
        "mu": float(mu),
        "method": method,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 2. Cone clutch torque
# ---------------------------------------------------------------------------

def cone_clutch_torque(
    F_a: float,
    mu: float,
    r_o: float,
    r_i: float,
    half_angle_deg: float,
    *,
    method: str = "uniform-wear",
) -> dict:
    """
    Torque capacity and actuation force for a cone clutch.

    The cone half-angle α is measured from the axis of rotation to the cone
    surface.  Typical values: 8°–15°.  Below ~6° the clutch may self-lock.

    Parameters
    ----------
    F_a : float
        Axial engagement force (N). Must be > 0.
    mu : float
        Coefficient of friction. Must be > 0.
    r_o : float
        Outer cone radius (m). Must be > r_i.
    r_i : float
        Inner cone radius (m). Must be >= 0.
    half_angle_deg : float
        Cone half-angle α (degrees). Must be > 0.
    method : str
        'uniform-wear' (default) or 'uniform-pressure'.

    Returns
    -------
    dict
        ok             : True
        torque_Nm      : clutch torque (N·m)
        F_a_N          : actuation force used (N)
        r_mean_m       : effective friction radius (m)
        alpha_deg      : half-angle used (degrees)
        sin_alpha      : sin(α)
        self_lock      : True if μ ≥ sin(α) (self-locking condition)
        warnings       : list[str]
    """
    warns: list[str] = []

    err = _guard_positive("F_a", F_a)
    if err:
        return _err(err)
    err = _guard_positive("mu", mu)
    if err:
        return _err(err)
    err = _guard_positive("r_o", r_o)
    if err:
        return _err(err)
    err = _guard_nonneg("r_i", r_i)
    if err:
        return _err(err)
    err = _guard_positive("half_angle_deg", half_angle_deg)
    if err:
        return _err(err)

    if r_i >= r_o:
        return _err(f"r_i ({r_i}) must be < r_o ({r_o})")

    alpha = math.radians(float(half_angle_deg))
    sin_a = math.sin(alpha)

    meth = str(method).strip().lower().replace("-", "").replace("_", "").replace(" ", "")

    if meth in ("uniformwear", "wear"):
        r_mean = (r_o + r_i) / 2.0
    elif meth in ("uniformpressure", "pressure"):
        num = r_o ** 3 - r_i ** 3
        den = r_o ** 2 - r_i ** 2
        r_mean = (2.0 / 3.0) * (num / den)
    else:
        return _err(
            f"Unknown method {method!r}. Supported: 'uniform-wear', 'uniform-pressure'."
        )

    # T = mu * F_a * r_mean / sin(alpha)
    # Juvinall §18.5; Shigley §16-3
    T = mu * float(F_a) * r_mean / sin_a

    self_lock = mu >= sin_a
    if self_lock:
        warns.append(
            f"Self-locking condition: μ ({mu:.3f}) >= sin(α) ({sin_a:.4f}). "
            "Clutch may not release. Increase half-angle or reduce μ."
        )
    if half_angle_deg < 6.0:
        warns.append(
            f"half_angle_deg={half_angle_deg:.1f}° is very small (<6°); "
            "self-locking risk is high."
        )

    return {
        "ok": True,
        "torque_Nm": T,
        "F_a_N": float(F_a),
        "r_mean_m": r_mean,
        "alpha_deg": float(half_angle_deg),
        "sin_alpha": sin_a,
        "self_lock": self_lock,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 3. Band brake
# ---------------------------------------------------------------------------

def band_brake_torque(
    drum_radius: float,
    angle_wrap_deg: float,
    mu: float,
    F_tight: float,
    *,
    self_energizing: bool = False,
) -> dict:
    """
    Flexible band brake: tight-side / slack-side forces, braking torque,
    and self-energizing factor.

    The capstan / belt-friction equation governs:
        F_tight / F_slack = exp(μ·θ)

    The band brake is self-energizing when the drum rotation tends to pull
    the band tighter (tight-side on the actuating end).

    Parameters
    ----------
    drum_radius : float
        Drum radius (m). Must be > 0.
    angle_wrap_deg : float
        Band wrap angle θ (degrees). Must be > 0.
    mu : float
        Band-drum coefficient of friction. Must be > 0.
    F_tight : float
        Tight-side tension in the band (N). Must be > 0.
    self_energizing : bool
        If True, report the self-energizing factor Se = exp(μ·θ)
        (the multiplier of slack-side force to get tight-side).

    Returns
    -------
    dict
        ok                 : True
        torque_Nm          : braking torque (N·m)
        F_tight_N          : tight-side force (N)
        F_slack_N          : slack-side force (N)
        capstan_ratio      : F_tight / F_slack = exp(μ·θ)
        self_energizing_factor: exp(μ·θ)
        mu                 : friction coefficient used
        wrap_angle_deg     : wrap angle (degrees)
        warnings           : list[str]
    """
    warns: list[str] = []

    err = _guard_positive("drum_radius", drum_radius)
    if err:
        return _err(err)
    err = _guard_positive("angle_wrap_deg", angle_wrap_deg)
    if err:
        return _err(err)
    err = _guard_positive("mu", mu)
    if err:
        return _err(err)
    err = _guard_positive("F_tight", F_tight)
    if err:
        return _err(err)

    theta = math.radians(float(angle_wrap_deg))
    capstan = math.exp(mu * theta)
    F_slack = float(F_tight) / capstan
    T = (float(F_tight) - F_slack) * float(drum_radius)

    if angle_wrap_deg > 360.0:
        warns.append(
            f"wrap angle {angle_wrap_deg:.1f}° > 360° is geometrically unusual."
        )

    return {
        "ok": True,
        "torque_Nm": T,
        "F_tight_N": float(F_tight),
        "F_slack_N": F_slack,
        "capstan_ratio": capstan,
        "self_energizing_factor": capstan,
        "mu": float(mu),
        "wrap_angle_deg": float(angle_wrap_deg),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 4. Drum brake — short-shoe and long-shoe
# ---------------------------------------------------------------------------

def drum_brake_torque(
    drum_radius: float,
    shoe_width: float,
    mu: float,
    p_max: float,
    theta1_deg: float,
    theta2_deg: float,
    pivot_a: float,
    *,
    shoe_type: str = "leading",
) -> dict:
    """
    Drum brake braking torque using the long-shoe (distributed pressure)
    Shigley §16-3 formulation (Shigley 10th ed., Eqs 16-2, 16-3, 16-6).

    The contact pressure distribution is assumed:
        p(θ) = p_max × sin(θ) / sin(θ_max)

    where θ_max is the angle of maximum pressure (at θ=90° if within arc, else
    at the end).

    Parameters
    ----------
    drum_radius : float
        Drum radius r (m). Must be > 0.
    shoe_width : float
        Shoe face width b (m). Must be > 0.
    mu : float
        Coefficient of friction. Must be > 0.
    p_max : float
        Maximum allowable normal pressure on shoe face (Pa). Must be > 0.
    theta1_deg : float
        Shoe leading edge angle from pivot (degrees). Typically 0–30°.
    theta2_deg : float
        Shoe trailing edge angle from pivot (degrees). theta2 > theta1.
    pivot_a : float
        Perpendicular distance from drum centre to pivot (m). Must be > 0.
    shoe_type : str
        'leading' (default) — self-energizing (rotation assists engagement)
        'trailing'          — de-energizing (self-dragging)

    Returns
    -------
    dict
        ok             : True
        torque_Nm      : braking torque from this shoe (N·m)
        actuating_F_N  : required actuating force at pivot (N)
        self_energizing: True if shoe_type=='leading' and μ causes amplification
        M_f            : friction moment (N·m) about pivot
        M_n            : normal force moment (N·m) about pivot
        shoe_type      : 'leading' or 'trailing'
        warnings       : list[str]
    """
    warns: list[str] = []

    err = _guard_positive("drum_radius", drum_radius)
    if err:
        return _err(err)
    err = _guard_positive("shoe_width", shoe_width)
    if err:
        return _err(err)
    err = _guard_positive("mu", mu)
    if err:
        return _err(err)
    err = _guard_positive("p_max", p_max)
    if err:
        return _err(err)
    err = _guard_nonneg("theta1_deg", theta1_deg)
    if err:
        return _err(err)
    err = _guard_positive("theta2_deg", theta2_deg)
    if err:
        return _err(err)
    err = _guard_positive("pivot_a", pivot_a)
    if err:
        return _err(err)

    if theta2_deg <= theta1_deg:
        return _err(
            f"theta2_deg ({theta2_deg}) must be > theta1_deg ({theta1_deg})"
        )

    stype = str(shoe_type).strip().lower()
    if stype not in ("leading", "trailing"):
        return _err(f"shoe_type must be 'leading' or 'trailing', got {shoe_type!r}")

    r = float(drum_radius)
    b = float(shoe_width)
    a = float(pivot_a)
    th1 = math.radians(float(theta1_deg))
    th2 = math.radians(float(theta2_deg))

    # θ_max for pressure normalisation: if 90° is within arc, sin is max at 90°
    th_max_p = math.radians(90.0)
    sin_theta_max = math.sin(th_max_p) if th1 <= th_max_p <= th2 else max(math.sin(th1), math.sin(th2))

    # Shigley's Mechanical Engineering Design, 10th ed., §16-3,
    # Eqs (16-2), (16-3), (16-4) — internal/external long-shoe drum brake
    # with pivot at perpendicular distance `a` from the drum centre and a
    # sinusoidal pressure distribution  p(θ) = p_max · sin θ / sin θ_a.
    #
    #   Moment of the normal forces about the pivot (Shigley Eq 16-2):
    #     M_N = (p_max · b · r · a / sin θ_a) · ∫[θ1,θ2] sin²θ dθ
    #         = (p_max · b · r · a / sin θ_a) · [θ/2 − sin 2θ / 4]_{θ1}^{θ2}
    #
    #   Moment of the friction forces about the pivot (Shigley Eq 16-3):
    #     M_f = (μ · p_max · b · r / sin θ_a) · ∫[θ1,θ2] sin θ (r − a cos θ) dθ
    #         = (μ · p_max · b · r / sin θ_a) · [−r cos θ − (a/2) sin²θ]_{θ1}^{θ2}
    #
    #   Brake torque about the drum centre (Shigley Eq 16-6):
    #     T = (μ · p_max · b · r² / sin θ_a) · (cos θ1 − cos θ2)
    #
    # Degenerate check: with a = 0 (pivot at drum centre) M_N → 0 and
    # M_f → T, as expected physically.

    pmax_b_r = p_max * b * r / sin_theta_max

    # ∫ sin²θ dθ = θ/2 − sin(2θ)/4   (Shigley Eq 16-2 normal-force moment)
    int_sin2 = ((th2 / 2.0 - math.sin(2.0 * th2) / 4.0)
                - (th1 / 2.0 - math.sin(2.0 * th1) / 4.0))
    M_n = pmax_b_r * a * int_sin2

    # ∫ sin θ (r − a cos θ) dθ = [−r cos θ − (a/2) sin²θ]
    #   (Shigley Eq 16-3 friction-force moment about the pivot)
    def _Ff(t: float) -> float:
        return -r * math.cos(t) - (a / 2.0) * math.sin(t) ** 2

    M_f = pmax_b_r * mu * (_Ff(th2) - _Ff(th1))

    # Torque (Shigley Eq 16-6):
    T = pmax_b_r * mu * r * (math.cos(th1) - math.cos(th2))

    # Actuating force (Shigley Eqs 16-4 / 16-5):
    # Self-energizing (leading) shoe:  F · c = M_n - M_f
    # Self-de-energizing (trailing):   F · c = M_n + M_f
    # c = moment arm of the actuating force about the pivot; the standard
    # textbook assumption c = a (actuator acts at the pivot offset).
    c = a  # actuating force arm = pivot distance (standard assumption)

    if stype == "leading":
        denom = M_n - M_f
        self_en = True
        if denom <= 0.0:
            warns.append(
                f"Leading shoe self-locking: M_f ({M_f:.3f} N·m) >= M_n ({M_n:.3f} N·m). "
                "Reduce μ or adjust shoe geometry."
            )
            F_act = float("inf")
        else:
            F_act = denom / c
    else:
        denom = M_n + M_f
        self_en = False
        F_act = denom / c if c > 0 else float("inf")

    return {
        "ok": True,
        "torque_Nm": T,
        "actuating_F_N": F_act,
        "self_energizing": self_en,
        "M_f": M_f,
        "M_n": M_n,
        "shoe_type": stype,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 5. Caliper disc brake torque
# ---------------------------------------------------------------------------

def disc_brake_torque(
    F_clamp: float,
    mu: float,
    r_eff: float,
    *,
    n_pads: int = 2,
) -> dict:
    """
    Caliper disc brake braking torque.

    Assumes each pad contributes one friction surface.  A typical floating
    caliper has 2 pads (one each side), fixed calipers may have 4.

    Parameters
    ----------
    F_clamp : float
        Clamping force per pad (N). Must be > 0.
    mu : float
        Pad-rotor coefficient of friction. Must be > 0.
    r_eff : float
        Effective friction radius — typically mid-pad radius (m). Must be > 0.
    n_pads : int
        Number of pads (default 2 for floating caliper).

    Returns
    -------
    dict
        ok          : True
        torque_Nm   : total braking torque (N·m)
        F_clamp_N   : clamping force per pad (N)
        mu          : friction coefficient used
        r_eff_m     : effective radius (m)
        n_pads      : number of pads
        warnings    : list[str]
    """
    warns: list[str] = []

    err = _guard_positive("F_clamp", F_clamp)
    if err:
        return _err(err)
    err = _guard_positive("mu", mu)
    if err:
        return _err(err)
    err = _guard_positive("r_eff", r_eff)
    if err:
        return _err(err)

    try:
        n_p = int(n_pads)
    except (TypeError, ValueError):
        return _err(f"n_pads must be an integer, got {n_pads!r}")
    if n_p < 1:
        return _err(f"n_pads must be >= 1, got {n_p}")

    # T = n_pads × μ × F_clamp × r_eff
    T = n_p * mu * float(F_clamp) * float(r_eff)

    if mu > 0.6:
        warns.append(f"mu={mu:.3f} is unusually high (>0.6); verify pad material.")

    return {
        "ok": True,
        "torque_Nm": T,
        "F_clamp_N": float(F_clamp),
        "mu": float(mu),
        "r_eff_m": float(r_eff),
        "n_pads": n_p,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 6. Engagement energy
# ---------------------------------------------------------------------------

def engagement_energy(
    omega1_rad_s: float,
    omega2_rad_s: float,
    I_driving: float,
    I_driven: float,
    *,
    T_load_Nm: float = 0.0,
    t_engage_s: float | None = None,
) -> dict:
    """
    Energy dissipated during a clutch/brake engagement (slip phase).

    Two contributions:
    1. Kinetic energy redistribution from inertia
    2. Work done against / by the load during slip

    For a clutch bringing the driven side from ω₂ to synchronous speed:
        ΔKE = ½ × I_eff × (ω₁ - ω₂)²
    where I_eff = I_driving × I_driven / (I_driving + I_driven)

    Parameters
    ----------
    omega1_rad_s : float
        Driving shaft angular velocity (rad/s). Must be >= 0.
    omega2_rad_s : float
        Driven shaft initial angular velocity (rad/s). Must be >= 0.
    I_driving : float
        Driving-side mass moment of inertia (kg·m²). Must be > 0.
    I_driven : float
        Driven-side mass moment of inertia (kg·m²). Must be > 0.
    T_load_Nm : float
        Resisting load torque on driven side (N·m, >= 0; default 0).
    t_engage_s : float | None
        Engagement / slip time (s). If provided, work done by load
        W_load = T_load × avg_speed × t is added to slip energy.

    Returns
    -------
    dict
        ok               : True
        E_slip_J         : total slip energy dissipated (J)
        E_kinetic_J      : kinetic energy component (J)
        E_load_J         : load-work component (J; 0 if t_engage_s not given)
        delta_omega      : speed difference (rad/s)
        I_eff            : effective inertia (kg·m²)
        warnings         : list[str]
    """
    warns: list[str] = []

    err = _guard_nonneg("omega1_rad_s", omega1_rad_s)
    if err:
        return _err(err)
    err = _guard_nonneg("omega2_rad_s", omega2_rad_s)
    if err:
        return _err(err)
    err = _guard_positive("I_driving", I_driving)
    if err:
        return _err(err)
    err = _guard_positive("I_driven", I_driven)
    if err:
        return _err(err)
    err = _guard_nonneg("T_load_Nm", T_load_Nm)
    if err:
        return _err(err)

    dw = float(omega1_rad_s) - float(omega2_rad_s)
    I_d = float(I_driving)
    I_n = float(I_driven)
    I_eff = I_d * I_n / (I_d + I_n)

    E_kin = 0.5 * I_eff * dw ** 2

    E_load = 0.0
    if t_engage_s is not None:
        err_t = _guard_positive("t_engage_s", t_engage_s)
        if err_t:
            return _err(err_t)
        # average angular velocity of driven side ≈ linear ramp from ω2 to ω1
        omega_avg = (float(omega2_rad_s) + float(omega1_rad_s)) / 2.0
        E_load = float(T_load_Nm) * omega_avg * float(t_engage_s)

    E_total = E_kin + E_load

    if E_total > 1e6:
        warns.append(
            f"Slip energy E_slip={E_total:.1f} J exceeds 1 MJ; verify inputs and "
            "consider duty-cycle thermal analysis."
        )

    return {
        "ok": True,
        "E_slip_J": E_total,
        "E_kinetic_J": E_kin,
        "E_load_J": E_load,
        "delta_omega": dw,
        "I_eff": I_eff,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 7. Temperature rise (lumped model)
# ---------------------------------------------------------------------------

def temperature_rise(
    E_slip_J: float,
    mass_rotor_kg: float,
    *,
    cp_J_per_kgK: float = 500.0,
    fraction_to_rotor: float = 0.5,
) -> dict:
    """
    Lumped thermal temperature rise of the rotor/drum from one engagement.

    ΔT = (fraction × E_slip) / (m × cp)

    Parameters
    ----------
    E_slip_J : float
        Slip energy dissipated (J). Must be > 0.
    mass_rotor_kg : float
        Effective thermal mass of rotor/drum (kg). Must be > 0.
    cp_J_per_kgK : float
        Specific heat capacity (J/kg·K). Default 500 J/kg·K (steel/cast iron).
    fraction_to_rotor : float
        Fraction of slip energy going to the rotor (0–1). Default 0.5
        (equal split between rotor and pad/lining, conservative).

    Returns
    -------
    dict
        ok              : True
        delta_T_K       : temperature rise (K = °C increment)
        E_to_rotor_J    : energy fraction to rotor (J)
        mass_kg         : rotor mass used (kg)
        cp_J_per_kgK    : specific heat used (J/kg·K)
        warnings        : list[str]
    """
    warns: list[str] = []

    err = _guard_positive("E_slip_J", E_slip_J)
    if err:
        return _err(err)
    err = _guard_positive("mass_rotor_kg", mass_rotor_kg)
    if err:
        return _err(err)
    err = _guard_positive("cp_J_per_kgK", cp_J_per_kgK)
    if err:
        return _err(err)

    try:
        f = float(fraction_to_rotor)
    except (TypeError, ValueError):
        return _err(f"fraction_to_rotor must be a number, got {fraction_to_rotor!r}")
    if not (0.0 < f <= 1.0):
        return _err(f"fraction_to_rotor must be in (0, 1], got {f}")

    E_rotor = f * float(E_slip_J)
    dT = E_rotor / (float(mass_rotor_kg) * float(cp_J_per_kgK))

    if dT > 200.0:
        warns.append(
            f"Temperature rise ΔT={dT:.1f} K is very high (>200 K). "
            "Check rotor mass, duty cycle, and cooling provision."
        )

    return {
        "ok": True,
        "delta_T_K": dT,
        "E_to_rotor_J": E_rotor,
        "mass_kg": float(mass_rotor_kg),
        "cp_J_per_kgK": float(cp_J_per_kgK),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 8. Required heat-dissipation area
# ---------------------------------------------------------------------------

def heat_dissipation_area(
    power_W: float,
    *,
    h_conv: float = 20.0,
    delta_T_K: float = 80.0,
) -> dict:
    """
    Minimum heat-dissipation area for steady-state convective cooling.

    Q = h × A × ΔT  →  A = Q / (h × ΔT)

    Parameters
    ----------
    power_W : float
        Heat dissipation power (W). Must be > 0.
    h_conv : float
        Convective heat-transfer coefficient (W/m²·K). Default 20 W/m²·K
        (natural convection in air). Must be > 0.
    delta_T_K : float
        Allowable surface-to-ambient temperature difference (K). Default 80 K.
        Must be > 0.

    Returns
    -------
    dict
        ok              : True
        area_m2         : minimum required area (m²)
        power_W         : power input (W)
        h_W_m2K         : convective coefficient (W/m²·K)
        delta_T_K       : temperature differential (K)
        warnings        : list[str]
    """
    warns: list[str] = []

    err = _guard_positive("power_W", power_W)
    if err:
        return _err(err)
    err = _guard_positive("h_conv", h_conv)
    if err:
        return _err(err)
    err = _guard_positive("delta_T_K", delta_T_K)
    if err:
        return _err(err)

    A = float(power_W) / (float(h_conv) * float(delta_T_K))

    if A > 1.0:
        warns.append(
            f"Required area {A:.3f} m² is large (>1 m²). "
            "Consider forced convection (higher h) or liquid cooling."
        )

    return {
        "ok": True,
        "area_m2": A,
        "power_W": float(power_W),
        "h_W_m2K": float(h_conv),
        "delta_T_K": float(delta_T_K),
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 9. Wear — pV limit check
# ---------------------------------------------------------------------------

def wear_pv_check(
    p_contact: float,
    v_slip: float,
    material: str,
) -> dict:
    """
    Check whether the contact pressure × slip velocity (pV) product is within
    the material's allowable limit.

    Parameters
    ----------
    p_contact : float
        Average contact pressure on friction surface (Pa). Must be > 0.
    v_slip : float
        Average sliding / slip velocity at friction surface (m/s). Must be > 0.
    material : str
        Friction material name from the built-in catalog.

    Returns
    -------
    dict
        ok          : True
        pv_Pa_m_s   : computed pV product (Pa·m/s)
        pv_max      : allowable pV limit (Pa·m/s)
        pv_ok       : True if pv <= pv_max
        safety_factor: pv_max / pv (inf-proof)
        material    : material name
        warnings    : list[str]
    """
    warns: list[str] = []

    err = _guard_positive("p_contact", p_contact)
    if err:
        return _err(err)
    err = _guard_positive("v_slip", v_slip)
    if err:
        return _err(err)

    mat = str(material).strip().lower().replace(" ", "_").replace("-", "_")
    if mat not in _FRICTION_MATERIALS:
        return _err(
            f"Unknown material {material!r}. "
            f"Available: {list(_FRICTION_MATERIALS.keys())}"
        )

    pv = float(p_contact) * float(v_slip)
    pv_max = _FRICTION_MATERIALS[mat]["max_pv"]
    pv_ok = pv <= pv_max
    sf = pv_max / pv if pv > 0 else float("inf")

    if not pv_ok:
        warns.append(
            f"pV exceeded: {pv:.3e} Pa·m/s > limit {pv_max:.3e} Pa·m/s "
            f"(sf={sf:.3f}). Reduce pressure or sliding speed."
        )

    return {
        "ok": True,
        "pv_Pa_m_s": pv,
        "pv_max": pv_max,
        "pv_ok": pv_ok,
        "safety_factor": sf,
        "material": mat,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 10. Engagement time & slip energy
# ---------------------------------------------------------------------------

def engagement_time(
    omega1_rad_s: float,
    omega2_rad_s: float,
    I_driving: float,
    I_driven: float,
    T_clutch_Nm: float,
    *,
    T_load_Nm: float = 0.0,
) -> dict:
    """
    Time to synchronise and total slip energy during clutch engagement.

    Assumes constant clutch torque during slip phase (simplified model).

    From Newton 2nd law for rotation:
        Driving: I₁ × α₁ = -(T_c - T_drive)  [if T_drive=0, driving decelerates]
        Driven:  I₂ × α₂ = T_c - T_load

    Synchronisation time (both sides reach the same ω):
        t_s = (ω₁ - ω₂) × I₁ × I₂ / [(T_c - T_load) × (I₁ + I₂)]

    Slip energy:
        E_slip = T_c × ω_avg × t_s  (approximately)

    Parameters
    ----------
    omega1_rad_s : float
        Initial driving shaft speed (rad/s). Must be >= omega2_rad_s.
    omega2_rad_s : float
        Initial driven shaft speed (rad/s). Must be >= 0.
    I_driving : float
        Driving-side inertia (kg·m²). Must be > 0.
    I_driven : float
        Driven-side inertia (kg·m²). Must be > 0.
    T_clutch_Nm : float
        Clutch (transmitted) torque during slip (N·m). Must be > 0.
    T_load_Nm : float
        Load torque on driven side (N·m, >= 0; default 0).

    Returns
    -------
    dict
        ok              : True
        t_sync_s        : synchronisation time (s)
        E_slip_J        : total slip energy (J)
        omega_sync      : synchronous (final) angular speed (rad/s)
        t_sync_feasible : True if T_clutch > T_load (can actually sync)
        warnings        : list[str]
    """
    warns: list[str] = []

    err = _guard_nonneg("omega1_rad_s", omega1_rad_s)
    if err:
        return _err(err)
    err = _guard_nonneg("omega2_rad_s", omega2_rad_s)
    if err:
        return _err(err)
    err = _guard_positive("I_driving", I_driving)
    if err:
        return _err(err)
    err = _guard_positive("I_driven", I_driven)
    if err:
        return _err(err)
    err = _guard_positive("T_clutch_Nm", T_clutch_Nm)
    if err:
        return _err(err)
    err = _guard_nonneg("T_load_Nm", T_load_Nm)
    if err:
        return _err(err)

    w1 = float(omega1_rad_s)
    w2 = float(omega2_rad_s)
    I1 = float(I_driving)
    I2 = float(I_driven)
    Tc = float(T_clutch_Nm)
    TL = float(T_load_Nm)

    dw = w1 - w2

    feasible = Tc > TL
    if not feasible:
        warns.append(
            f"T_clutch ({Tc:.3f} N·m) <= T_load ({TL:.3f} N·m); "
            "clutch cannot synchronise the driven side."
        )

    if dw < 0:
        warns.append(
            f"omega1 ({w1:.3f}) < omega2 ({w2:.3f}); driven side faster than driving. "
            "Setting |Δω| for calculation."
        )
        dw = abs(dw)

    # Net accelerating torque on driven side
    T_net = Tc - TL

    if T_net <= 0 or dw == 0:
        t_sync = 0.0
        E_slip = 0.0
        omega_sync = (I1 * w1 + I2 * w2) / (I1 + I2)
    else:
        # t_sync = Δω × I1 × I2 / (T_net × (I1 + I2))
        t_sync = dw * I1 * I2 / (T_net * (I1 + I2))
        # Final sync speed (momentum conservation, simplified for constant Tc)
        omega_sync = (I1 * w1 + I2 * w2) / (I1 + I2)
        # Average slip angular velocity
        omega_avg_slip = (w1 + w2) / 2.0
        E_slip = Tc * omega_avg_slip * t_sync

    if E_slip > 1e6:
        warns.append(
            f"Slip energy {E_slip:.1f} J > 1 MJ. Consider reducing inertia or "
            "staged engagement."
        )

    return {
        "ok": True,
        "t_sync_s": t_sync,
        "E_slip_J": E_slip,
        "omega_sync": omega_sync,
        "t_sync_feasible": feasible,
        "warnings": warns,
    }
