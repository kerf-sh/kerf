"""
kerf_cad_core.railway.track — pure-Python railway track & vehicle engineering.

Implements thirteen public functions covering:

  1.  equilibrium_cant(V, R, G)
        Equilibrium (theoretical) cant for speed V on curve radius R.

  2.  applied_cant(V, R, G, cant_deficiency, cant_excess)
        Applied (actual) superelevation considering cant policy limits.

  3.  cant_deficiency(V, R, G, cant_applied)
        Cant deficiency (unbalanced cant) — positive means too little cant.

  4.  cant_gradient_check(cant_change_mm, transition_length_m, speed_kmh)
        Cant ramp rate check: mm/m and mm/s against UIC limits.

  5.  transition_length(cant_change_mm, speed_kmh, *, method, rate_limit_mm_s)
        Minimum transition (Euler spiral/cubic spiral) length from cant-ramp
        rate-of-change limit.

  6.  gauge_widening(radius_m, gauge_nom_mm, *, method)
        Additional rail gauge widening on tight curves.

  7.  vertical_curve_length(delta_g_percent, speed_kmh, *, curve_type)
        Minimum vertical curve length (crest or sag).

  8.  hertzian_contact(P, R1x, R1y, R2x, R2y, E1, nu1, E2, nu2)
        Hertzian wheel–rail contact: semi-axes a, b, max pressure p0.

  9.  davis_resistance(mass_kg, speed_kmh, A, B, C, *, grade_percent, curve_radius_m)
        Davis train resistance formula: A + BV + CV², plus grade & curve
        resistance.

  10. tractive_effort(power_W, speed_kmh, *, adhesion_coeff, axle_load_N, driven_axles)
        Maximum continuous tractive effort from power; adhesion limit check.

  11. braking_distance(speed_kmh, deceleration_ms2, *, reaction_time_s)
        Braking distance and mean deceleration from initial speed to rest.

  12. rail_bending(wheel_load_N, rail_I_m4, rail_E_Pa, foundation_modulus_Pa_per_m)
        Beam-on-elastic-foundation (Winkler) rail stress, deflection, and
        sleeper/ballast reaction.

  13. rail_thermal_stress(delta_T_K, E_Pa, alpha, *, CWR, rail_area_m2, yield_Pa)
        Rail thermal stress in continuously-welded rail; CWR buckling risk flag.

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Warning flags (never fatal):
  "cant_deficiency_exceeded"  — cant deficiency > limit_mm (default 130 mm)
  "adhesion_limited"          — tractive effort clipped by adhesion
  "CWR_buckling_risk"         — compressive thermal stress > buckling threshold

Units
-----
  lengths     — metres (m) unless _mm suffix
  forces      — Newtons (N)
  stress      — Pascals (Pa)
  speed       — km/h for track engineering inputs; m/s internally where noted
  cant        — millimetres (mm)  (UIC/EN convention)
  temperature — Kelvin difference (ΔK = ΔK)
  angles      — radians (rad) internally; degrees where noted
  gauge       — millimetres (mm)

References
----------
UIC 703-2:2011 — Track alignment design parameters
EN 13803-1:2010 — Railway applications — Track alignment design parameters
Hay, W.W. (1982) "Railroad Engineering", 2nd ed., Wiley
Esveld, C. (2001) "Modern Railway Track", 2nd ed., MRT-Productions
Johnson, K.L. (1985) "Contact Mechanics", Cambridge
Timoshenko, S.P. (1976) "Strength of Materials, Part II", Van Nostrand Reinhold

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_finite, _guard_nonneg, _guard_positive

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ok(**fields) -> dict:
    d: dict = {"ok": True}
    d.update(fields)
    if "warnings" not in d:
        d["warnings"] = []
    return d


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Standard track gauges (mm) — for reference
_GAUGE_STANDARD_MM = 1435.0  # standard gauge (UIC)

# Standard gravity (m/s²)
_G_MS2 = 9.80665

# UIC/EN maximum cant deficiency limits (mm) by line category
# Conservative: high-speed lines use 130 mm for tilting trains; 100 mm standard
_CANT_DEFICIENCY_LIMIT_MM = 130.0

# UIC 703 cant ramp rate limit: 1.0 mm/m (cant gradient) for normal operation
_CANT_GRADIENT_LIMIT_MM_PER_M = 1.0

# UIC 703 cant rate-of-change limit at speed: 55 mm/s for normal, 75 for higher
_CANT_RATE_LIMIT_MM_PER_S = 55.0

# CWR buckling threshold: compressive stress ratio to yield; flag above 0.7
_CWR_BUCKLING_RATIO = 0.70

# Steel rail modulus / coefficient
_RAIL_E_PA = 210e9   # Young's modulus for steel rail (Pa)
_RAIL_ALPHA = 11.5e-6  # thermal expansion coefficient for rail steel (1/K)

# Hertzian contact: ellipticity integral approximation coefficients (Greenwood)
_HZ_N_ITER = 50  # iterations for elliptic integral approximation


# ---------------------------------------------------------------------------
# 1. equilibrium_cant
# ---------------------------------------------------------------------------

def equilibrium_cant(
    speed_kmh: float,
    radius_m: float,
    gauge_mm: float = _GAUGE_STANDARD_MM,
) -> dict:
    """
    Equilibrium (theoretical) cant for a given speed and curve radius.

    The equilibrium cant is the superelevation at which the resultant of
    gravity and centrifugal force acts normal to the track plane; no lateral
    force on the wheel flanges.

    Formula (UIC 703-2, §4.1):
        h_eq = (g / v²) × (v² / R) × G_eff × (1/g)
             = V² × G_eff / (g × R)

    where V is speed in m/s, G_eff is the effective gauge (centre-to-centre
    of rail heads ≈ gauge_mm + 1500 mm for standard gauge head width; UIC
    uses effective gauge = gauge_nom for cant calculation), g is gravity.

    Simplified UIC formula (equivalent):
        h_eq [mm] = 11.8 × V² [km/h] / R [m]     (gauge = 1435 mm)

    This function uses the exact physics formula adapted for any gauge.

    Parameters
    ----------
    speed_kmh : float
        Design speed (km/h). Must be > 0.
    radius_m : float
        Horizontal curve radius (m). Must be > 0.
    gauge_mm : float
        Nominal track gauge centre-to-centre (mm). Default 1435 mm.

    Returns
    -------
    dict
        ok              : True
        cant_eq_mm      : equilibrium cant (mm)
        speed_kmh       : speed used (km/h)
        radius_m        : radius used (m)
        gauge_mm        : gauge used (mm)
        warnings        : []
    """
    err = _guard_positive("speed_kmh", speed_kmh)
    if err:
        return _err(err)
    err = _guard_positive("radius_m", radius_m)
    if err:
        return _err(err)
    err = _guard_positive("gauge_mm", gauge_mm)
    if err:
        return _err(err)

    V_ms = float(speed_kmh) / 3.6  # km/h → m/s
    R = float(radius_m)
    G_m = float(gauge_mm) * 1e-3  # mm → m

    # h_eq = V² × G / (g × R)  [metres]
    h_eq_m = (V_ms ** 2 * G_m) / (_G_MS2 * R)
    h_eq_mm = h_eq_m * 1e3

    return _ok(
        cant_eq_mm=h_eq_mm,
        speed_kmh=float(speed_kmh),
        radius_m=R,
        gauge_mm=float(gauge_mm),
    )


# ---------------------------------------------------------------------------
# 2. applied_cant
# ---------------------------------------------------------------------------

def applied_cant(
    speed_kmh: float,
    radius_m: float,
    gauge_mm: float = _GAUGE_STANDARD_MM,
    *,
    max_cant_mm: float = 150.0,
    cant_deficiency_limit_mm: float = _CANT_DEFICIENCY_LIMIT_MM,
) -> dict:
    """
    Applied (actual) cant considering policy limits.

    The applied cant is selected to keep cant deficiency within the allowed
    limit while not exceeding the maximum permissible cant.

    Applied cant policy:
        h_app = min(h_eq, max_cant_mm)
        such that h_eq - h_app <= cant_deficiency_limit_mm

    Parameters
    ----------
    speed_kmh : float
        Design speed (km/h). Must be > 0.
    radius_m : float
        Horizontal curve radius (m). Must be > 0.
    gauge_mm : float
        Nominal track gauge (mm). Default 1435 mm.
    max_cant_mm : float
        Maximum permissible cant (mm). Default 150 mm (EN 13803 mainline).
    cant_deficiency_limit_mm : float
        Maximum allowable cant deficiency (mm). Default 130 mm.

    Returns
    -------
    dict
        ok                    : True
        cant_eq_mm            : equilibrium cant (mm)
        cant_applied_mm       : applied (actual) cant (mm)
        cant_deficiency_mm    : residual cant deficiency (mm)
        warnings              : ["cant_deficiency_exceeded"] if exceeded
    """
    err = _guard_positive("speed_kmh", speed_kmh)
    if err:
        return _err(err)
    err = _guard_positive("radius_m", radius_m)
    if err:
        return _err(err)
    err = _guard_positive("gauge_mm", gauge_mm)
    if err:
        return _err(err)
    err = _guard_positive("max_cant_mm", max_cant_mm)
    if err:
        return _err(err)
    err = _guard_positive("cant_deficiency_limit_mm", cant_deficiency_limit_mm)
    if err:
        return _err(err)

    r = equilibrium_cant(speed_kmh, radius_m, gauge_mm)
    if not r["ok"]:
        return r

    h_eq = r["cant_eq_mm"]
    # Applied cant: at most max_cant_mm, at most h_eq (no excess cant here)
    h_app = min(h_eq, float(max_cant_mm))
    # Ensure non-negative
    h_app = max(h_app, 0.0)

    h_def = h_eq - h_app

    warnings: list[str] = []
    if h_def > float(cant_deficiency_limit_mm):
        warnings.append("cant_deficiency_exceeded")

    return _ok(
        cant_eq_mm=h_eq,
        cant_applied_mm=h_app,
        cant_deficiency_mm=h_def,
        cant_deficiency_limit_mm=float(cant_deficiency_limit_mm),
        max_cant_mm=float(max_cant_mm),
        speed_kmh=float(speed_kmh),
        radius_m=float(radius_m),
        gauge_mm=float(gauge_mm),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 3. cant_deficiency
# ---------------------------------------------------------------------------

def cant_deficiency(
    speed_kmh: float,
    radius_m: float,
    cant_applied_mm: float,
    gauge_mm: float = _GAUGE_STANDARD_MM,
    *,
    deficiency_limit_mm: float = _CANT_DEFICIENCY_LIMIT_MM,
) -> dict:
    """
    Cant deficiency (unbalanced cant) for a given applied cant.

    Positive deficiency: train tends to overturn outward (lateral force on
    outer rail flange).  Negative: excess cant (inner rail flange loading).

    h_def = h_eq - h_applied

    Parameters
    ----------
    speed_kmh : float
        Speed (km/h). Must be > 0.
    radius_m : float
        Curve radius (m). Must be > 0.
    cant_applied_mm : float
        Actual applied cant (mm). Must be >= 0.
    gauge_mm : float
        Track gauge (mm). Default 1435 mm.
    deficiency_limit_mm : float
        Alert threshold (mm). Default 130 mm.

    Returns
    -------
    dict
        ok                  : True
        cant_eq_mm          : equilibrium cant (mm)
        cant_applied_mm     : applied cant (mm)
        cant_deficiency_mm  : h_eq − h_applied (mm); negative = excess cant
        cant_excess_mm      : max(0, h_applied − h_eq) (mm)
        warnings            : ["cant_deficiency_exceeded"] if > limit
    """
    err = _guard_positive("speed_kmh", speed_kmh)
    if err:
        return _err(err)
    err = _guard_positive("radius_m", radius_m)
    if err:
        return _err(err)
    err = _guard_nonneg("cant_applied_mm", cant_applied_mm)
    if err:
        return _err(err)
    err = _guard_positive("gauge_mm", gauge_mm)
    if err:
        return _err(err)

    r = equilibrium_cant(speed_kmh, radius_m, gauge_mm)
    if not r["ok"]:
        return r

    h_eq = r["cant_eq_mm"]
    h_app = float(cant_applied_mm)
    h_def = h_eq - h_app
    h_excess = max(0.0, h_app - h_eq)

    warnings: list[str] = []
    if h_def > float(deficiency_limit_mm):
        warnings.append("cant_deficiency_exceeded")

    return _ok(
        cant_eq_mm=h_eq,
        cant_applied_mm=h_app,
        cant_deficiency_mm=h_def,
        cant_excess_mm=h_excess,
        deficiency_limit_mm=float(deficiency_limit_mm),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 4. cant_gradient_check
# ---------------------------------------------------------------------------

def cant_gradient_check(
    cant_change_mm: float,
    transition_length_m: float,
    speed_kmh: float,
    *,
    gradient_limit_mm_per_m: float = _CANT_GRADIENT_LIMIT_MM_PER_M,
    rate_limit_mm_per_s: float = _CANT_RATE_LIMIT_MM_PER_S,
) -> dict:
    """
    Check the cant ramp rate against UIC/EN limits.

    Two criteria:
      Spatial: cant gradient = Δh / L [mm/m]   ≤ gradient_limit (1.0 mm/m)
      Temporal: cant rate   = Δh × V / L [mm/s] ≤ rate_limit (55 mm/s)

    Parameters
    ----------
    cant_change_mm : float
        Total change in cant over the transition (mm). Must be >= 0.
    transition_length_m : float
        Length of the transition (m). Must be > 0.
    speed_kmh : float
        Train speed (km/h). Must be > 0.
    gradient_limit_mm_per_m : float
        Spatial cant gradient limit (mm/m). Default 1.0 mm/m (UIC 703).
    rate_limit_mm_per_s : float
        Temporal cant rate limit (mm/s). Default 55 mm/s (UIC 703).

    Returns
    -------
    dict
        ok                      : True
        cant_gradient_mm_per_m  : Δh / L (mm/m)
        cant_rate_mm_per_s      : Δh × V / L (mm/s)
        gradient_ok             : True if spatial gradient ≤ limit
        rate_ok                 : True if temporal rate ≤ limit
        gradient_limit_mm_per_m : limit used
        rate_limit_mm_per_s     : limit used
        warnings                : list (empty if both ok)
    """
    err = _guard_nonneg("cant_change_mm", cant_change_mm)
    if err:
        return _err(err)
    err = _guard_positive("transition_length_m", transition_length_m)
    if err:
        return _err(err)
    err = _guard_positive("speed_kmh", speed_kmh)
    if err:
        return _err(err)

    delta_h = float(cant_change_mm)
    L = float(transition_length_m)
    V_ms = float(speed_kmh) / 3.6

    gradient = delta_h / L                  # mm/m
    rate = delta_h * V_ms / L               # mm/s

    gradient_ok = gradient <= float(gradient_limit_mm_per_m)
    rate_ok = rate <= float(rate_limit_mm_per_s)

    warnings: list[str] = []
    if not gradient_ok:
        warnings.append("cant_gradient_exceeded")
    if not rate_ok:
        warnings.append("cant_rate_exceeded")

    return _ok(
        cant_gradient_mm_per_m=gradient,
        cant_rate_mm_per_s=rate,
        gradient_ok=gradient_ok,
        rate_ok=rate_ok,
        gradient_limit_mm_per_m=float(gradient_limit_mm_per_m),
        rate_limit_mm_per_s=float(rate_limit_mm_per_s),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 5. transition_length
# ---------------------------------------------------------------------------

def transition_length(
    cant_change_mm: float,
    speed_kmh: float,
    *,
    method: str = "rate_of_change",
    rate_limit_mm_s: float = _CANT_RATE_LIMIT_MM_PER_S,
    gradient_limit_mm_m: float = _CANT_GRADIENT_LIMIT_MM_PER_M,
) -> dict:
    """
    Minimum transition length from cant-ramp rate-of-change constraints.

    Two methods:
      "rate_of_change"  — L_min = Δh × V / rate_limit  (temporal constraint)
      "cant_gradient"   — L_min = Δh / gradient_limit   (spatial constraint)
      "combined"        — max(L_rate, L_gradient)

    The clothoid / Euler spiral naturally distributes curvature linearly;
    the cubic parabola gives essentially the same length for railway use.

    Parameters
    ----------
    cant_change_mm : float
        Total cant change over the transition (mm). Must be >= 0.
    speed_kmh : float
        Design speed (km/h). Must be > 0.
    method : str
        "rate_of_change" | "cant_gradient" | "combined". Default "rate_of_change".
    rate_limit_mm_s : float
        Temporal cant rate limit (mm/s). Default 55 mm/s.
    gradient_limit_mm_m : float
        Spatial cant gradient limit (mm/m). Default 1.0 mm/m.

    Returns
    -------
    dict
        ok                      : True
        transition_length_m     : minimum transition length (m)
        L_rate_m                : length from rate-of-change criterion (m)
        L_gradient_m            : length from cant-gradient criterion (m)
        method                  : method used
        cant_change_mm          : Δh used (mm)
        speed_kmh               : speed used (km/h)
        warnings                : []
    """
    err = _guard_nonneg("cant_change_mm", cant_change_mm)
    if err:
        return _err(err)
    err = _guard_positive("speed_kmh", speed_kmh)
    if err:
        return _err(err)
    err = _guard_positive("rate_limit_mm_s", rate_limit_mm_s)
    if err:
        return _err(err)
    err = _guard_positive("gradient_limit_mm_m", gradient_limit_mm_m)
    if err:
        return _err(err)

    delta_h = float(cant_change_mm)
    V_ms = float(speed_kmh) / 3.6

    # Rate-of-change criterion: L = Δh × V / rate_limit
    L_rate = delta_h * V_ms / float(rate_limit_mm_s) if delta_h > 0 else 0.0

    # Cant gradient criterion: L = Δh / gradient_limit
    L_gradient = delta_h / float(gradient_limit_mm_m) if delta_h > 0 else 0.0

    m = str(method).strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if m in ("rateofchange", "rate"):
        L_min = L_rate
    elif m in ("cantgradient", "gradient", "spatial"):
        L_min = L_gradient
    elif m == "combined":
        L_min = max(L_rate, L_gradient)
    else:
        return _err(
            f"Unknown method {method!r}. Supported: 'rate_of_change', 'cant_gradient', 'combined'."
        )

    return _ok(
        transition_length_m=L_min,
        L_rate_m=L_rate,
        L_gradient_m=L_gradient,
        method=method,
        cant_change_mm=delta_h,
        speed_kmh=float(speed_kmh),
    )


# ---------------------------------------------------------------------------
# 6. gauge_widening
# ---------------------------------------------------------------------------

def gauge_widening(
    radius_m: float,
    gauge_nom_mm: float = _GAUGE_STANDARD_MM,
    *,
    method: str = "UIC",
) -> dict:
    """
    Additional rail gauge widening on tight curves.

    On tight curves, gauge widening prevents wheel flange binding.
    UIC 505 / EN 13715 prescribe gauge widening as a function of curve radius.

    UIC 505 table (standard gauge 1435 mm):
        R >= 250 m  → no widening (0 mm)
        175 ≤ R < 250 m → 5 mm
        150 ≤ R < 175 m → 10 mm
        R < 150 m → 15 mm (max)

    For non-standard gauges, a formula approximation is used:
        w ≈ k × (l² / (8 × R))   where l = rigid wheelbase, k = empirical factor

    Parameters
    ----------
    radius_m : float
        Curve radius (m). Must be > 0.
    gauge_nom_mm : float
        Nominal track gauge (mm). Default 1435 mm.
    method : str
        "UIC" (default, table lookup for standard gauge) or "formula"
        (continuous approximation, any gauge).

    Returns
    -------
    dict
        ok              : True
        gauge_widening_mm : additional widening (mm)
        gauge_design_mm : gauge_nom_mm + gauge_widening_mm
        radius_m        : radius used
        gauge_nom_mm    : nominal gauge used
        method          : method used
        warnings        : []
    """
    err = _guard_positive("radius_m", radius_m)
    if err:
        return _err(err)
    err = _guard_positive("gauge_nom_mm", gauge_nom_mm)
    if err:
        return _err(err)

    R = float(radius_m)
    G = float(gauge_nom_mm)

    m = str(method).strip().upper()

    if m == "UIC":
        # UIC 505 / EN 13715 table for standard gauge 1435 mm
        if R >= 250.0:
            w_mm = 0.0
        elif R >= 175.0:
            w_mm = 5.0
        elif R >= 150.0:
            w_mm = 10.0
        else:
            w_mm = 15.0
    elif m in ("FORMULA", "APPROX"):
        # Approximate continuous formula
        # Rigid wheelbase l = 2.5 m (typical bogied stock)
        # w ≈ (l² × G) / (8 × R × 1000) — empirical
        # Using standard: w = 3000 / R  (mm) for R < 300 m, 0 otherwise
        # Reference: Hay (1982) Ch. 3
        l_wb = 2.5  # m — representative bogie wheelbase
        if R < 300.0:
            w_mm = (l_wb ** 2 / (8.0 * R)) * 1e3  # m → mm
            w_mm = min(w_mm, 15.0)  # cap at 15 mm
        else:
            w_mm = 0.0
    else:
        return _err(f"Unknown method {method!r}. Supported: 'UIC', 'formula'.")

    return _ok(
        gauge_widening_mm=w_mm,
        gauge_design_mm=G + w_mm,
        radius_m=R,
        gauge_nom_mm=G,
        method=m,
    )


# ---------------------------------------------------------------------------
# 7. vertical_curve_length
# ---------------------------------------------------------------------------

def vertical_curve_length(
    delta_g_percent: float,
    speed_kmh: float,
    *,
    curve_type: str = "crest",
) -> dict:
    """
    Minimum vertical curve length for passenger comfort and safety.

    Formulae per EN 13803-1 / UIC 703-2:
        Crest (summit):  L_min = V² × |Δg| / (13 × 100)     [m; V in km/h, Δg in %]
                         (limiting criterion: sight distance / derailment risk)
        Sag (valley):    L_min = V² × |Δg| / (4 × 100)      [m; V in km/h, Δg in %]
                         (limiting criterion: passenger comfort; vertical acceleration)

    The denominators correspond to:
        Crest: limiting vertical acceleration ≈ 0.6 m/s²  (derailment threshold)
        Sag:   limiting vertical acceleration ≈ 0.2 m/s²  (comfort threshold)

    Parameters
    ----------
    delta_g_percent : float
        Algebraic change of grade (%). May be negative; absolute value is used.
    speed_kmh : float
        Design speed (km/h). Must be > 0.
    curve_type : str
        "crest" (summit/hump, default) or "sag" (valley/dip).

    Returns
    -------
    dict
        ok                      : True
        vertical_curve_length_m : minimum vertical curve length (m)
        delta_g_percent         : |Δg| used (%)
        speed_kmh               : speed used (km/h)
        curve_type              : type used
        K_value                 : rate-of-grade-change (m per 1% grade change)
        warnings                : []
    """
    err = _guard_finite("delta_g_percent", delta_g_percent)
    if err:
        return _err(err)
    err = _guard_positive("speed_kmh", speed_kmh)
    if err:
        return _err(err)

    ct = str(curve_type).strip().lower()
    if ct not in ("crest", "sag"):
        return _err(f"Unknown curve_type {curve_type!r}. Supported: 'crest', 'sag'.")

    V = float(speed_kmh)
    abs_dg = abs(float(delta_g_percent))

    if ct == "crest":
        # L = V² × |Δg| / 1300  (from a = V²/R where R = L/|Δg| and a_lim ≈ 0.6 m/s² → factor 1300)
        L = (V ** 2 * abs_dg) / 1300.0
    else:  # sag
        # L = V² × |Δg| / 400   (a_lim ≈ 0.2 m/s² → factor 400)
        L = (V ** 2 * abs_dg) / 400.0

    # K value = L / |Δg| (m per %)
    K = L / abs_dg if abs_dg > 0 else 0.0

    return _ok(
        vertical_curve_length_m=L,
        delta_g_percent=abs_dg,
        speed_kmh=V,
        curve_type=ct,
        K_value=K,
    )


# ---------------------------------------------------------------------------
# 8. hertzian_contact
# ---------------------------------------------------------------------------

def _elliptic_integrals(k: float) -> tuple[float, float]:
    """
    Approximate complete elliptic integrals K(k) and E(k) via AGM (Gauss).
    k is the modulus (0 < k < 1); returns (K, E).
    """
    # Arithmetic-geometric mean method for K(k)
    # and the complementary for E(k)
    k2 = k * k
    k_prime2 = 1.0 - k2

    # AGM for K
    a = 1.0
    b = math.sqrt(k_prime2)
    for _ in range(_HZ_N_ITER):
        a_new = (a + b) / 2.0
        b_new = math.sqrt(a * b)
        if abs(a_new - b_new) < 1e-15:
            break
        a, b = a_new, b_new
    K = math.pi / (2.0 * a)

    # For E(k): use series approximation (Abramowitz & Stegun 17.3.36)
    # E(k) ≈ (π/2)(1 - Σ [(2n-1)!!/(2n)!!]² × k^(2n)/(2n-1))
    # We'll use the Gauss transformation result more directly.
    # Landen transformation cascade for E:
    a0 = 1.0
    b0 = math.sqrt(k_prime2)
    c0 = k
    E_sum = c0 ** 2
    c_sq_sum = c0 ** 2
    for n in range(1, _HZ_N_ITER):
        a1 = (a0 + b0) / 2.0
        b1 = math.sqrt(a0 * b0)
        c1 = (a0 - b0) / 2.0
        E_sum += (2 ** n) * c1 ** 2
        if abs(c1) < 1e-15:
            break
        a0, b0 = a1, b1

    E = K * (1.0 - E_sum / 2.0)

    return K, E


def hertzian_contact(
    P_N: float,
    R1x_m: float,
    R1y_m: float,
    R2x_m: float,
    R2y_m: float,
    E1_Pa: float = _RAIL_E_PA,
    nu1: float = 0.28,
    E2_Pa: float = _RAIL_E_PA,
    nu2: float = 0.28,
) -> dict:
    """
    Hertzian wheel–rail contact: semi-axes, max contact pressure.

    Models the contact between wheel and rail as two general quadric surfaces.
    The wheel has principal radii R1x (rolling direction) and R1y (transverse),
    the rail has R2x (longitudinal) and R2y (transverse head profile radius).

    Hertz (1881) theory gives the contact ellipse semi-axes a (major) and b
    (minor) and the maximum pressure p0.

    Parameters
    ----------
    P_N : float
        Normal wheel load (N). Must be > 0.
    R1x_m : float
        Wheel rolling radius (m). Must be > 0. Typical: 0.46 m.
    R1y_m : float
        Wheel transverse radius (m). Must be > 0. Typical: 0.3–0.5 m.
    R2x_m : float
        Rail longitudinal radius (m). Must be > 0.
        For a straight rail: very large (e.g. 1e9 m → flat).
    R2y_m : float
        Rail head transverse profile radius (m). Must be > 0. Typical: 0.3 m.
    E1_Pa : float
        Wheel Young's modulus (Pa). Default 210 GPa (steel).
    nu1 : float
        Wheel Poisson's ratio. Default 0.28.
    E2_Pa : float
        Rail Young's modulus (Pa). Default 210 GPa (steel).
    nu2 : float
        Rail Poisson's ratio. Default 0.28.

    Returns
    -------
    dict
        ok              : True
        semi_axis_a_m   : major contact semi-axis a (m)
        semi_axis_b_m   : minor contact semi-axis b (m)
        contact_area_m2 : π × a × b (m²)
        max_pressure_Pa : p0 = 3P / (2πab) (Pa)
        E_star_Pa       : combined modulus E* (Pa)
        warnings        : []

    Notes
    -----
    For pure rail-head geometry (no rolling-direction curvature on rail),
    set R2x_m to a large value (e.g. 1e9).
    The Boussinesq-Hertz solution is:
        1/R_eq = 1/R1x + 1/R1y + 1/R2x + 1/R2y  (sum of principal curvatures)
    """
    for name, val in [
        ("P_N", P_N), ("R1x_m", R1x_m), ("R1y_m", R1y_m),
        ("R2x_m", R2x_m), ("R2y_m", R2y_m), ("E1_Pa", E1_Pa), ("E2_Pa", E2_Pa),
    ]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)
    for name, val in [("nu1", nu1), ("nu2", nu2)]:
        err = _guard_finite(name, val)
        if err:
            return _err(err)
        if not (0.0 < float(val) < 0.5):
            return _err(f"{name} must be in (0, 0.5), got {val}")

    P = float(P_N)
    r1x = float(R1x_m)
    r1y = float(R1y_m)
    r2x = float(R2x_m)
    r2y = float(R2y_m)

    # Combined modulus E*
    E_star = 1.0 / ((1.0 - float(nu1) ** 2) / float(E1_Pa) +
                     (1.0 - float(nu2) ** 2) / float(E2_Pa))

    # Sum of principal curvatures (Hertz notation)
    # For bodies 1 and 2 with two principal radii each:
    # A + B = (1/2) × (1/R1x + 1/R1y + 1/R2x + 1/R2y)
    A_plus_B = 0.5 * (1.0/r1x + 1.0/r1y + 1.0/r2x + 1.0/r2y)
    A_minus_B = 0.5 * abs((1.0/r1x - 1.0/r1y) - (1.0/r2x - 1.0/r2y))
    # Wait — Hertz convention: A = (1/2)(kappa_1a + kappa_2a), B = ... for min axis
    # Using Johnson (1985) p.84: A+B = (1/2) Σ(1/Ri); |A-B| = half-difference of curvature sums
    # Let k1 = 1/R1x + 1/R1y, k2 = 1/R2x + 1/R2y
    # Then A = (k1 + k2)/4, and the eccentricity from the theta angle.
    # Simplified for axis-aligned surfaces (the theta term vanishes):
    # Ry_eff = 1/(1/R1y + 1/R2y);  Rx_eff = 1/(1/R1x + 1/R2x)
    Rx_eff = 1.0 / (1.0/r1x + 1.0/r2x)
    Ry_eff = 1.0 / (1.0/r1y + 1.0/r2y)

    # For two cylinders with perpendicular axes crossed at 90°,
    # use the simplified Hertz formulae for contact ellipse directly.
    # For an arbitrary geometry, compute ellipticity k = b/a from:
    #   b/a = (Ry_eff/Rx_eff)^(1/3)   [approximate for small eccentricity]
    # More precisely solve numerically; use approximate closed form:
    R_sum = Rx_eff + Ry_eff
    R_prod = Rx_eff * Ry_eff

    # Approximate semi-axes (Hertz, Johnson §4.2):
    #   a = (3P / (4 E*)) ^(1/3) × (Rx_eff + Ry_eff)^(1/3) × f_a
    # where f_a, f_b are ellipticity correction factors.
    # Using the Greenwood (1985) approximation for elliptic contact:
    # Ellipticity parameter e from: Rx_eff <= Ry_eff (a >= b)
    if Rx_eff >= Ry_eff:
        R_a = Rx_eff
        R_b = Ry_eff
    else:
        R_a = Ry_eff
        R_b = Rx_eff

    # Ellipticity ratio k = b/a ≈ (R_b/R_a)^(2/3)  [Greenwood approximation]
    k_ratio = (R_b / R_a) ** (2.0 / 3.0)

    # Complete elliptic integrals K(e), E(e) where e² = 1 - k²
    e_sq = 1.0 - k_ratio ** 2
    if e_sq < 0.0:
        e_sq = 0.0
    if e_sq > 1.0 - 1e-12:
        e_sq = 1.0 - 1e-12
    e_mod = math.sqrt(e_sq)
    K_e, E_e = _elliptic_integrals(e_mod)

    # Equivalent radius: R_eq = sqrt(R_a * R_b) approximately for combined geometry
    R_eq = math.sqrt(R_a * R_b)

    # Contact half-width scale: delta = (3P / (4 E* R_eq))^(1/3)
    delta = (3.0 * P / (4.0 * E_star * R_eq)) ** (1.0 / 3.0)

    # Semi-axes:  a = delta × (R_a/R_eq)^(1/2)   (approximate)
    #             b = delta × (R_b/R_eq)^(1/2)
    a_semi = delta * math.sqrt(R_a / R_eq)
    b_semi = delta * math.sqrt(R_b / R_eq)

    # Ensure a >= b
    if b_semi > a_semi:
        a_semi, b_semi = b_semi, a_semi

    contact_area = math.pi * a_semi * b_semi
    p0 = 1.5 * P / contact_area if contact_area > 0 else 0.0

    return _ok(
        semi_axis_a_m=a_semi,
        semi_axis_b_m=b_semi,
        contact_area_m2=contact_area,
        max_pressure_Pa=p0,
        E_star_Pa=E_star,
        Rx_eff_m=Rx_eff,
        Ry_eff_m=Ry_eff,
    )


# ---------------------------------------------------------------------------
# 9. davis_resistance
# ---------------------------------------------------------------------------

def davis_resistance(
    mass_kg: float,
    speed_kmh: float,
    A: float,
    B: float,
    C: float,
    *,
    grade_percent: float = 0.0,
    curve_radius_m: float = 0.0,
    gauge_mm: float = _GAUGE_STANDARD_MM,
) -> dict:
    """
    Davis train resistance formula: A + BV + CV².

    Total resistance = rolling + grade + curve resistance.

    Davis formula (modified):
        R_davis = A + B×V + C×V²    [N/kN or N per kN of train mass]

    Coefficients A, B, C are train-specific (from test data / manufacturer):
      A  — constant resistance (rolling friction) [N/kN]
      B  — speed-dependent term (flange, track irregularity) [N·h/(kN·km)]
      C  — aerodynamic drag coefficient [N·h²/(kN·km²)]

    Grade resistance:
        R_grade = W × g% / 100     [N per kN = N/kN, where g% is grade in %]
        (positive = ascending)

    Curve resistance (Röckl formula, UIC):
        R_curve = 6500 / (R - 55)  [N/kN, R in metres, R > 55 m]

    Parameters
    ----------
    mass_kg : float
        Total train mass (kg). Must be > 0.
    speed_kmh : float
        Speed (km/h). Must be >= 0.
    A : float
        Davis A coefficient [N/kN]. Must be >= 0.
    B : float
        Davis B coefficient [N·h/(kN·km)]. Must be >= 0.
    C : float
        Davis C coefficient [N·h²/(kN·km²)]. Must be >= 0.
    grade_percent : float
        Track grade (%). Positive = ascending. Default 0.
    curve_radius_m : float
        Curve radius (m). 0 = tangent track (no curve resistance). Default 0.
    gauge_mm : float
        Track gauge (mm). Default 1435 mm.

    Returns
    -------
    dict
        ok                  : True
        R_davis_N_per_kN    : Davis resistance component (N/kN)
        R_grade_N_per_kN    : Grade resistance component (N/kN)
        R_curve_N_per_kN    : Curve resistance component (N/kN)
        R_total_N_per_kN    : Total specific resistance (N/kN)
        R_total_N           : Total resistance force (N)
        mass_kg             : train mass used (kg)
        speed_kmh           : speed used (km/h)
        warnings            : []
    """
    err = _guard_positive("mass_kg", mass_kg)
    if err:
        return _err(err)
    err = _guard_nonneg("speed_kmh", speed_kmh)
    if err:
        return _err(err)
    err = _guard_nonneg("A", A)
    if err:
        return _err(err)
    err = _guard_nonneg("B", B)
    if err:
        return _err(err)
    err = _guard_nonneg("C", C)
    if err:
        return _err(err)
    err = _guard_finite("grade_percent", grade_percent)
    if err:
        return _err(err)
    err = _guard_nonneg("curve_radius_m", curve_radius_m)
    if err:
        return _err(err)

    V = float(speed_kmh)
    m = float(mass_kg)
    W_kN = m * _G_MS2 / 1000.0  # weight in kN

    # Davis formula: A + BV + CV²  (N/kN)
    R_davis = float(A) + float(B) * V + float(C) * V ** 2

    # Grade resistance: N/kN = g%  (i.e. 10 N/kN per 1% grade for normalised form)
    R_grade = float(grade_percent) * 10.0  # N/kN (= kg·g / 1000 per tonne, g ≈ 10)
    # More precisely: R_grade [N/kN] = g% × g / 100 × 1000 / g = 10 × g%
    # But let's use exact: 9.80665/100 × 1000/9.80665 = 10 exactly for N/kN

    # Curve resistance (Röckl formula)
    R_curve = 0.0
    R = float(curve_radius_m)
    if R > 0.0:
        if R <= 55.0:
            return _err(
                f"curve_radius_m={R} <= 55 m: Röckl formula not valid for R <= 55 m."
            )
        R_curve = 6500.0 / (R - 55.0)  # N/kN

    R_total_specific = R_davis + R_grade + R_curve  # N/kN
    R_total_N = R_total_specific * W_kN  # N

    return _ok(
        R_davis_N_per_kN=R_davis,
        R_grade_N_per_kN=R_grade,
        R_curve_N_per_kN=R_curve,
        R_total_N_per_kN=R_total_specific,
        R_total_N=R_total_N,
        mass_kg=m,
        speed_kmh=V,
        weight_kN=W_kN,
    )


# ---------------------------------------------------------------------------
# 10. tractive_effort
# ---------------------------------------------------------------------------

def tractive_effort(
    power_W: float,
    speed_kmh: float,
    *,
    adhesion_coeff: float = 0.25,
    axle_load_N: float = 0.0,
    driven_axles: int = 4,
) -> dict:
    """
    Maximum tractive effort from power; adhesion limit check.

    Tractive effort from power:
        TE_power = P / V      (W / (m/s) = N)

    Adhesion limit:
        TE_adhesion = μ × W_driven
    where W_driven = axle_load_N × driven_axles is the total weight on driven wheels.

    Applied tractive effort is the minimum of TE_power and TE_adhesion.

    Parameters
    ----------
    power_W : float
        Continuous traction power (W). Must be > 0.
    speed_kmh : float
        Speed (km/h). Must be > 0.
    adhesion_coeff : float
        Wheel–rail adhesion coefficient μ. Default 0.25 (dry, typical).
    axle_load_N : float
        Axle load per driven axle (N). 0 = skip adhesion limit check.
    driven_axles : int
        Number of driven axles. Default 4.

    Returns
    -------
    dict
        ok                  : True
        TE_power_N          : tractive effort limited by power (N)
        TE_adhesion_N       : adhesion limit (N); 0 if axle_load_N=0
        TE_applied_N        : min(TE_power, TE_adhesion) if adhesion limit active
        adhesion_limited    : True if TE_adhesion < TE_power
        adhesion_coeff      : μ used
        speed_kmh           : speed used (km/h)
        warnings            : ["adhesion_limited"] if clipped
    """
    err = _guard_positive("power_W", power_W)
    if err:
        return _err(err)
    err = _guard_positive("speed_kmh", speed_kmh)
    if err:
        return _err(err)
    err = _guard_positive("adhesion_coeff", adhesion_coeff)
    if err:
        return _err(err)
    err = _guard_nonneg("axle_load_N", axle_load_N)
    if err:
        return _err(err)
    if int(driven_axles) <= 0:
        return _err(f"driven_axles must be > 0, got {driven_axles}")

    V_ms = float(speed_kmh) / 3.6
    P = float(power_W)

    TE_power = P / V_ms
    mu = float(adhesion_coeff)
    n_axles = int(driven_axles)
    W_driven = float(axle_load_N) * n_axles

    adhesion_limited = False
    if W_driven > 0.0:
        TE_adhesion = mu * W_driven
        if TE_adhesion < TE_power:
            adhesion_limited = True
            TE_applied = TE_adhesion
        else:
            TE_applied = TE_power
    else:
        TE_adhesion = 0.0
        TE_applied = TE_power

    warnings: list[str] = []
    if adhesion_limited:
        warnings.append("adhesion_limited")

    return _ok(
        TE_power_N=TE_power,
        TE_adhesion_N=TE_adhesion,
        TE_applied_N=TE_applied,
        adhesion_limited=adhesion_limited,
        adhesion_coeff=mu,
        speed_kmh=float(speed_kmh),
        power_W=P,
        driven_axles=n_axles,
        axle_load_N=float(axle_load_N),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 11. braking_distance
# ---------------------------------------------------------------------------

def braking_distance(
    speed_kmh: float,
    deceleration_ms2: float,
    *,
    reaction_time_s: float = 1.5,
    grade_percent: float = 0.0,
) -> dict:
    """
    Braking distance and mean deceleration from initial speed to rest.

    Braking distance (uniform deceleration from V to 0):
        s = V²/(2a)   (V in m/s)

    With driver reaction time:
        s_reaction = V × t_reaction
        s_total = s_reaction + s_brake

    Grade effect on deceleration (positive grade = ascending = helps braking):
        a_effective = a_brake + g × sin(θ) ≈ a_brake + g × grade%/100

    Parameters
    ----------
    speed_kmh : float
        Initial speed (km/h). Must be > 0.
    deceleration_ms2 : float
        Applied braking deceleration (m/s²). Must be > 0.
        Typical: 0.7–1.2 m/s² for conventional trains; up to 2.73 m/s² for metro.
    reaction_time_s : float
        Driver/system reaction time (s). Default 1.5 s (TSI). Must be >= 0.
    grade_percent : float
        Track grade (%). Positive = ascending. Default 0.

    Returns
    -------
    dict
        ok                      : True
        braking_distance_m      : total stopping distance (m)
        reaction_distance_m     : distance during reaction phase (m)
        brake_distance_m        : distance during braking phase (m)
        mean_deceleration_ms2   : effective deceleration including grade (m/s²)
        time_to_stop_s          : time from brakes applied to stop (s)
        speed_kmh               : initial speed (km/h)
        warnings                : []
    """
    err = _guard_positive("speed_kmh", speed_kmh)
    if err:
        return _err(err)
    err = _guard_positive("deceleration_ms2", deceleration_ms2)
    if err:
        return _err(err)
    err = _guard_nonneg("reaction_time_s", reaction_time_s)
    if err:
        return _err(err)
    err = _guard_finite("grade_percent", grade_percent)
    if err:
        return _err(err)

    V_ms = float(speed_kmh) / 3.6
    a_brake = float(deceleration_ms2)
    t_react = float(reaction_time_s)
    g_pct = float(grade_percent)

    # Grade contribution to effective deceleration
    a_grade = _G_MS2 * g_pct / 100.0  # positive = ascending = aids braking
    a_eff = a_brake + a_grade

    if a_eff <= 0.0:
        return _err(
            f"Effective deceleration {a_eff:.3f} m/s² <= 0: grade resistance "
            f"overwhelms braking effort (grade={g_pct}%)."
        )

    s_reaction = V_ms * t_react
    s_brake = (V_ms ** 2) / (2.0 * a_eff)
    s_total = s_reaction + s_brake
    t_stop = V_ms / a_eff

    return _ok(
        braking_distance_m=s_total,
        reaction_distance_m=s_reaction,
        brake_distance_m=s_brake,
        mean_deceleration_ms2=a_eff,
        time_to_stop_s=t_stop,
        speed_kmh=float(speed_kmh),
        initial_speed_ms=V_ms,
    )


# ---------------------------------------------------------------------------
# 12. rail_bending
# ---------------------------------------------------------------------------

def rail_bending(
    wheel_load_N: float,
    rail_I_m4: float,
    rail_E_Pa: float = _RAIL_E_PA,
    foundation_modulus_Pa_per_m: float = 25e6,
    *,
    rail_height_m: float = 0.172,
    sleeper_spacing_m: float = 0.6,
    sleeper_area_m2: float = 0.08,
) -> dict:
    """
    Rail bending on elastic foundation (Winkler model).

    Treats the rail as an infinite beam on a Winkler elastic foundation
    (Timoshenko, 1976).  The rail foundation modulus u (Pa/m) represents
    the combined stiffness of rail pad, sleeper, ballast, and subgrade.

    Characteristic length:
        L_c = (4EI / u)^(1/4)   [m]

    Maximum rail deflection (under load):
        y_max = P × L_c / (2 × E × I × kappa × 2)
              = P / (2 × u × L_c)           [Timoshenko notation]

    Maximum rail bending moment:
        M_max = P × L_c / 4

    Maximum bending stress:
        sigma_max = M_max × y_centroid / I
                  = M_max × (h/2) / I

    Sleeper/ballast reaction pressure (distributed over sleeper bearing area):
        q_sleeper = y_max × u × sleeper_spacing
                  (reaction per sleeper = y_max × u × spacing)
        p_ballast = reaction_per_sleeper / sleeper_area_m2

    Parameters
    ----------
    wheel_load_N : float
        Wheel load (N). Must be > 0.
    rail_I_m4 : float
        Rail second moment of area (m⁴). Must be > 0.
        Typical UIC60: I ≈ 30.55e-6 m⁴.
    rail_E_Pa : float
        Rail steel Young's modulus (Pa). Default 210 GPa.
    foundation_modulus_Pa_per_m : float
        Winkler foundation modulus u (Pa/m = N/m per m = N/m²/m).
        Typical: 15–50 MPa/m (soft–stiff ballast + pad). Default 25 MPa/m.
    rail_height_m : float
        Rail section height (m). Default 0.172 m (UIC60).
    sleeper_spacing_m : float
        Sleeper spacing (m). Default 0.6 m.
    sleeper_area_m2 : float
        Sleeper bearing area on ballast (m²). Default 0.08 m².

    Returns
    -------
    dict
        ok                      : True
        max_deflection_m        : y_max (m)
        max_bending_moment_Nm   : M_max (N·m)
        max_rail_stress_Pa      : σ_max (Pa) at rail foot/head
        sleeper_reaction_N      : force per sleeper (N)
        ballast_pressure_Pa     : pressure on sleeper bearing area (Pa)
        characteristic_length_m : L_c (m)
        warnings                : []
    """
    err = _guard_positive("wheel_load_N", wheel_load_N)
    if err:
        return _err(err)
    err = _guard_positive("rail_I_m4", rail_I_m4)
    if err:
        return _err(err)
    err = _guard_positive("rail_E_Pa", rail_E_Pa)
    if err:
        return _err(err)
    err = _guard_positive("foundation_modulus_Pa_per_m", foundation_modulus_Pa_per_m)
    if err:
        return _err(err)
    err = _guard_positive("rail_height_m", rail_height_m)
    if err:
        return _err(err)
    err = _guard_positive("sleeper_spacing_m", sleeper_spacing_m)
    if err:
        return _err(err)
    err = _guard_positive("sleeper_area_m2", sleeper_area_m2)
    if err:
        return _err(err)

    P = float(wheel_load_N)
    EI = float(rail_E_Pa) * float(rail_I_m4)
    u = float(foundation_modulus_Pa_per_m)
    h = float(rail_height_m)
    s_sp = float(sleeper_spacing_m)
    s_area = float(sleeper_area_m2)

    # Characteristic length (Winkler)
    L_c = (4.0 * EI / u) ** 0.25

    # Maximum deflection under point load (Timoshenko §57)
    y_max = P * L_c / (2.0 * EI * (2.0 / L_c ** 2) * 2.0)
    # Cleaner form: y_max = P / (2 × u × L_c)  [from substitution]
    y_max = P / (2.0 * u * L_c)

    # Maximum bending moment: M_max = P × L_c / 4
    M_max = P * L_c / 4.0

    # Maximum bending stress at extreme fibre (y = h/2 from neutral axis)
    sigma_max = M_max * (h / 2.0) / float(rail_I_m4)

    # Sleeper reaction (force per sleeper = foundation reaction × spacing)
    sleeper_reaction = y_max * u * s_sp

    # Ballast pressure
    p_ballast = sleeper_reaction / s_area

    return _ok(
        max_deflection_m=y_max,
        max_bending_moment_Nm=M_max,
        max_rail_stress_Pa=sigma_max,
        sleeper_reaction_N=sleeper_reaction,
        ballast_pressure_Pa=p_ballast,
        characteristic_length_m=L_c,
        EI_Nm2=EI,
        foundation_modulus_Pa_per_m=u,
    )


# ---------------------------------------------------------------------------
# 13. rail_thermal_stress
# ---------------------------------------------------------------------------

def rail_thermal_stress(
    delta_T_K: float,
    E_Pa: float = _RAIL_E_PA,
    alpha: float = _RAIL_ALPHA,
    *,
    CWR: bool = True,
    rail_area_m2: float = 7.686e-3,
    yield_Pa: float = 700e6,
) -> dict:
    """
    Rail thermal stress and CWR buckling risk.

    In a continuously-welded rail (CWR), longitudinal thermal movement is
    fully restrained; all thermal strain becomes stress:

        σ = E × α × ΔT

    Compressive when temperature rises (ΔT > 0) → buckling risk.
    Tensile when temperature drops (ΔT < 0) → rail break risk.

    Buckling risk flag: σ_comp / yield_Pa > CWR_BUCKLING_RATIO (0.70).

    For jointed rail the stress is zero (rails are free to expand at joints);
    set CWR=False to get the stress in a fishplated/jointed track section
    (returns 0 Pa — no restraint).

    Parameters
    ----------
    delta_T_K : float
        Temperature change from stress-free (neutral) temperature (K = °C).
        Positive = warming (compressive); negative = cooling (tensile).
    E_Pa : float
        Rail Young's modulus (Pa). Default 210 GPa.
    alpha : float
        Thermal expansion coefficient (1/K). Default 11.5×10⁻⁶ /K (rail steel).
    CWR : bool
        True (default) = continuously-welded rail (fully restrained).
        False = jointed rail (no thermal stress).
    rail_area_m2 : float
        Rail cross-sectional area (m²). Default 7.686×10⁻³ m² (UIC60).
    yield_Pa : float
        Rail steel yield stress (Pa). Default 700 MPa (grade 900A).

    Returns
    -------
    dict
        ok                      : True
        thermal_stress_Pa       : σ = E × α × ΔT (Pa); positive = compression
        thermal_force_N         : σ × A (N); compressive = positive
        is_compressive          : True if ΔT > 0
        is_tensile              : True if ΔT < 0
        buckling_stress_ratio   : σ / yield_Pa (0 if tensile)
        CWR_buckling_risk       : True if compressive stress ratio > 0.70
        CWR                     : whether CWR assumption used
        warnings                : ["CWR_buckling_risk"] if flagged
    """
    err = _guard_finite("delta_T_K", delta_T_K)
    if err:
        return _err(err)
    err = _guard_positive("E_Pa", E_Pa)
    if err:
        return _err(err)
    err = _guard_positive("alpha", alpha)
    if err:
        return _err(err)
    err = _guard_positive("rail_area_m2", rail_area_m2)
    if err:
        return _err(err)
    err = _guard_positive("yield_Pa", yield_Pa)
    if err:
        return _err(err)

    dT = float(delta_T_K)
    E = float(E_Pa)
    a = float(alpha)
    A = float(rail_area_m2)
    f_y = float(yield_Pa)

    if not CWR:
        # Jointed rail: no restraint, no thermal stress
        return _ok(
            thermal_stress_Pa=0.0,
            thermal_force_N=0.0,
            is_compressive=False,
            is_tensile=False,
            buckling_stress_ratio=0.0,
            CWR_buckling_risk=False,
            CWR=False,
        )

    # σ = E × α × ΔT  (positive = compressive when ΔT > 0)
    sigma = E * a * dT
    F = sigma * A

    is_compressive = dT > 0
    is_tensile = dT < 0

    buckling_ratio = abs(sigma) / f_y if is_compressive else 0.0
    cwr_risk = is_compressive and (buckling_ratio > _CWR_BUCKLING_RATIO)

    warnings: list[str] = []
    if cwr_risk:
        warnings.append("CWR_buckling_risk")

    return _ok(
        thermal_stress_Pa=sigma,
        thermal_force_N=F,
        is_compressive=is_compressive,
        is_tensile=is_tensile,
        buckling_stress_ratio=buckling_ratio,
        CWR_buckling_risk=cwr_risk,
        CWR=True,
        delta_T_K=dT,
        warnings=warnings,
    )
