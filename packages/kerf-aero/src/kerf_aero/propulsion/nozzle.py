"""
Rocket-nozzle aerodynamics: isentropic-flow relations, area ratios,
exit Mach number, thrust coefficient, and Rao bell-nozzle contour.

All functions accept SI units and return plain dicts.

References
----------
Anderson, "Modern Compressible Flow", 3rd ed., Chapter 5.
Sutton & Biblarz, "Rocket Propulsion Elements", 9th ed., Chapter 3.
Rao, G.V.R., "Exhaust Nozzle Contour for Optimum Thrust", Jet Propulsion,
  28(6), 1958.
"""

from __future__ import annotations

import math
from typing import NamedTuple

_MAX_ITER = 200
_TOL = 1e-10


def _area_ratio_from_mach(mach: float, gamma: float) -> float:
    """
    Isentropic area ratio Ae/At as a function of exit Mach number.

    (Ae/At)² = (1/M²) · [(2/(γ+1)) · (1 + (γ−1)/2 · M²)]^((γ+1)/(γ−1))
    """
    t = (2.0 / (gamma + 1.0)) * (1.0 + (gamma - 1.0) / 2.0 * mach**2)
    exp = (gamma + 1.0) / (gamma - 1.0)
    return (1.0 / mach) * t ** (exp / 2.0)


def exit_mach_from_area_ratio(
    area_ratio: float,
    gamma: float = 1.4,
    supersonic: bool = True,
) -> dict:
    """
    Solve for exit Mach number given isentropic area ratio Ae/At.

    Uses Brent's method to invert the area-Mach relation.

    Parameters
    ----------
    area_ratio  : Ae/At (must be ≥ 1)
    gamma       : ratio of specific heats
    supersonic  : if True solve supersonic root (Me > 1), else subsonic

    Returns
    -------
    dict with mach, area_ratio, gamma, pressure_ratio (pe/pt), temperature_ratio
    """
    if area_ratio < 1.0:
        return {"ok": False, "reason": "Area ratio must be ≥ 1 (throat = 1)"}
    if gamma <= 1.0:
        return {"ok": False, "reason": "γ must be > 1"}

    if area_ratio == 1.0:
        mach = 1.0
    elif supersonic:
        # Bracket: M ∈ [1, ~100]
        mach = _brent(
            lambda m: _area_ratio_from_mach(m, gamma) - area_ratio,
            1.0 + 1e-9,
            50.0,
        )
    else:
        # Subsonic root: M ∈ (0, 1]
        mach = _brent(
            lambda m: _area_ratio_from_mach(m, gamma) - area_ratio,
            1e-6,
            1.0 - 1e-9,
        )

    if mach is None:
        return {"ok": False, "reason": "Root-find failed for given area ratio"}

    # Isentropic relations
    pt_ratio = (1.0 + (gamma - 1.0) / 2.0 * mach**2) ** (gamma / (gamma - 1.0))
    p_ratio = 1.0 / pt_ratio  # pe/p0 (total pressure)
    tt_ratio = 1.0 + (gamma - 1.0) / 2.0 * mach**2
    t_ratio = 1.0 / tt_ratio  # Te/T0

    return {
        "ok": True,
        "mach": mach,
        "area_ratio": area_ratio,
        "gamma": gamma,
        "pressure_ratio": p_ratio,  # pe / p0
        "temperature_ratio": t_ratio,
        "density_ratio": (p_ratio) ** (1.0 / gamma),
    }


def area_ratio_from_pressure_ratio(
    pe_over_pc: float,
    gamma: float = 1.4,
) -> dict:
    """
    Compute the isentropic area ratio Ae/At for a given pressure ratio pe/pc.

    The exit Mach is first recovered from pe/pc via isentropic relations:

        pe/pc = (1 + (γ-1)/2 · Me²)^(−γ/(γ−1))

    then Ae/At is computed from Me.

    Parameters
    ----------
    pe_over_pc : exit-to-chamber (stagnation) pressure ratio
    gamma      : ratio of specific heats

    Returns
    -------
    dict with area_ratio, mach, pressure_ratio
    """
    if not (0 < pe_over_pc < 1):
        return {"ok": False, "reason": "pe/pc must be in (0, 1)"}
    if gamma <= 1.0:
        return {"ok": False, "reason": "γ must be > 1"}

    # Me from isentropic pe/pc — supersonic solution
    t = pe_over_pc ** (-(gamma - 1.0) / gamma)
    me_sq = 2.0 / (gamma - 1.0) * (t - 1.0)
    if me_sq < 0:
        return {"ok": False, "reason": "Pressure ratio implies subsonic flow"}
    me = math.sqrt(me_sq)
    ar = _area_ratio_from_mach(me, gamma)

    return {
        "ok": True,
        "area_ratio": ar,
        "mach": me,
        "pe_over_pc": pe_over_pc,
        "gamma": gamma,
    }


def exit_mach_from_pressure_ratio(
    pe_over_pc: float,
    gamma: float = 1.4,
) -> dict:
    """
    Exit Mach number from isentropic pressure ratio pe/pc.

    Me = sqrt( 2/(γ-1) · ((pc/pe)^((γ-1)/γ) − 1) )

    Parameters
    ----------
    pe_over_pc : exit-to-chamber pressure ratio
    gamma      : ratio of specific heats

    Returns
    -------
    dict with mach, area_ratio, pe_over_pc
    """
    res = area_ratio_from_pressure_ratio(pe_over_pc, gamma)
    if not res["ok"]:
        return res
    return {
        "ok": True,
        "mach": res["mach"],
        "area_ratio": res["area_ratio"],
        "pe_over_pc": pe_over_pc,
        "gamma": gamma,
    }


def nozzle_exit_conditions(
    pc: float,
    tc: float,
    gamma: float,
    molar_mass: float,
    area_ratio: float,
    pa: float = 0.0,
) -> dict:
    """
    Full exit-plane conditions given chamber state and area ratio.

    Parameters
    ----------
    pc          : chamber pressure [Pa]
    tc          : chamber temperature [K]
    gamma       : ratio of specific heats
    molar_mass  : propellant molar mass [kg/mol]
    area_ratio  : Ae/At
    pa          : ambient pressure [Pa] (0 = vacuum)

    Returns
    -------
    dict with exit Mach, pressure, temperature, velocity, c* [m/s]
    """
    R_universal = 8.314462  # J/(mol·K)
    R_spec = R_universal / molar_mass

    res = exit_mach_from_area_ratio(area_ratio, gamma)
    if not res["ok"]:
        return res
    me = res["mach"]

    pe = pc * (1.0 + (gamma - 1.0) / 2.0 * me**2) ** (-gamma / (gamma - 1.0))
    te = tc / (1.0 + (gamma - 1.0) / 2.0 * me**2)
    ve = me * math.sqrt(gamma * R_spec * te)

    # Characteristic velocity c* = pc · At / ṁ = sqrt(γ R Tc) / γ · ((γ+1)/2)^((γ+1)/(2(γ-1)))
    c_star = (
        math.sqrt(gamma * R_spec * tc)
        / gamma
        * ((gamma + 1.0) / 2.0) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))
    )
    # More standard form: c* = sqrt(R Tc / M) * sqrt(γ) * [(γ+1)/2]^(-(γ+1)/(2(γ-1)))  /  γ
    # Using: c* = (1/γ) · sqrt(γ R Tc) · [(γ+1)/2]^((γ+1)/(2(γ-1)))
    # This matches Sutton eq. 3-22.

    # Thrust coefficient (vacuum)
    cf_res = thrust_coefficient(gamma, pe / pc, area_ratio, pa / pc if pc > 0 else 0.0)

    isp_vac = c_star * cf_res["cf_vac"] / 9.80665

    return {
        "ok": True,
        "exit_mach": me,
        "exit_pressure_pa": pe,
        "exit_temperature_k": te,
        "exit_velocity_ms": ve,
        "c_star": c_star,
        "isp_vac": isp_vac,
        "thrust_coefficient_vac": cf_res["cf_vac"],
        "area_ratio": area_ratio,
        "pe_over_pc": pe / pc,
    }


def thrust_coefficient(
    gamma: float,
    pe_over_pc: float,
    ae_over_at: float,
    pa_over_pc: float = 0.0,
) -> dict:
    """
    Ideal thrust coefficient Cf.

    Cf = sqrt[ 2γ²/(γ−1) · (2/(γ+1))^((γ+1)/(γ−1)) · (1 − (pe/pc)^((γ−1)/γ)) ]
         + (pe/pc − pa/pc) · Ae/At

    Parameters
    ----------
    gamma       : ratio of specific heats
    pe_over_pc  : exit-to-chamber pressure ratio
    ae_over_at  : exit-to-throat area ratio
    pa_over_pc  : ambient-to-chamber pressure ratio (0 = vacuum)

    Returns
    -------
    dict with cf_vac, cf_sea, momentum_cf, pressure_cf
    """
    if gamma <= 1.0:
        return {"ok": False, "reason": "γ must be > 1"}
    if not (0 < pe_over_pc < 1):
        return {"ok": False, "reason": "pe/pc must be in (0, 1)"}

    sq_arg = (
        2.0 * gamma**2
        / (gamma - 1.0)
        * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0))
        * (1.0 - pe_over_pc ** ((gamma - 1.0) / gamma))
    )
    if sq_arg < 0:
        return {"ok": False, "reason": "Argument under sqrt is negative"}

    cf_mom = math.sqrt(sq_arg)
    cf_pres_vac = pe_over_pc * ae_over_at
    cf_pres_sea = (pe_over_pc - pa_over_pc) * ae_over_at

    return {
        "ok": True,
        "cf_vac": cf_mom + cf_pres_vac,
        "cf_sea": cf_mom + cf_pres_sea,
        "momentum_cf": cf_mom,
        "pressure_cf_vac": cf_pres_vac,
        "pressure_cf_sea": cf_pres_sea,
        "gamma": gamma,
        "pe_over_pc": pe_over_pc,
        "ae_over_at": ae_over_at,
    }


def rao_bell_contour(
    r_throat: float,
    r_exit: float,
    length_fraction: float = 0.8,
    n_points: int = 100,
    gamma: float = 1.4,
) -> dict:
    """
    Approximate Rao bell-nozzle contour using the parabolic approximation
    (Rao 1958, widely used for 80 % bell nozzles).

    The contour is parameterised from the throat to the exit plane:

    - Divergence section: circular arc of radius 0.382 Rt from θ_n (initial
      wall angle, ~20-28°) at the inflection point N.
    - Bell section: parabola from N to exit point E at angle θ_e.

    The exit angles θ_n and θ_e are interpolated from the Rao-standard table
    as a function of area ratio and length fraction.

    Parameters
    ----------
    r_throat        : throat radius [m]
    r_exit          : exit radius [m]
    length_fraction : fractional bell length vs. a 15° cone of equal area ratio
                      (typical: 0.8 for 80% bell)
    n_points        : number of (x, r) sample points
    gamma           : ratio of specific heats (used only for metadata)

    Returns
    -------
    dict with:
        contour: list of {"x": ..., "r": ...} dicts [m]
        length  : nozzle length from throat [m]
        area_ratio
        theta_n_deg, theta_e_deg
    """
    if r_throat <= 0 or r_exit <= 0:
        return {"ok": False, "reason": "Radii must be positive"}
    if r_exit < r_throat:
        return {"ok": False, "reason": "Exit radius must be ≥ throat radius"}
    if not (0.5 <= length_fraction <= 1.0):
        return {"ok": False, "reason": "length_fraction must be in [0.5, 1.0]"}

    area_ratio = (r_exit / r_throat) ** 2

    # Reference 15° cone length
    l_cone = (r_exit - r_throat) / math.tan(math.radians(15.0))

    # Bell length
    l_bell = length_fraction * l_cone

    # Rao angle approximation — linear interpolation from tabulated reference
    # For 80% bell nozzle at various area ratios (Sutton Table 3-4 approximation)
    # theta_n: initial divergence wall angle at inflection (N point)
    # theta_e: exit half-angle
    #
    # Reference values (area_ratio → (theta_n_deg, theta_e_deg)) for 0.8 bell:
    _ar_table = [2.0, 3.0, 4.0, 5.0, 8.0, 10.0, 15.0, 20.0, 30.0, 40.0, 50.0, 100.0]
    _tn_table = [25.0, 26.2, 27.0, 27.5, 28.2, 28.5, 28.9, 29.2, 29.5, 29.7, 29.8, 30.0]
    _te_table = [12.7, 11.3, 10.5, 10.0, 9.0, 8.7, 8.2, 7.9, 7.5, 7.3, 7.1, 6.6]

    def _interp(ar: float, xs: list, ys: list) -> float:
        if ar <= xs[0]:
            return ys[0]
        if ar >= xs[-1]:
            return ys[-1]
        for i in range(len(xs) - 1):
            if xs[i] <= ar <= xs[i + 1]:
                t = (ar - xs[i]) / (xs[i + 1] - xs[i])
                return ys[i] + t * (ys[i + 1] - ys[i])
        return ys[-1]

    # Scale angles by length fraction (shorter bell → larger theta_n, smaller theta_e)
    scale = 0.8 / length_fraction  # normalise to 80% reference
    theta_n_deg = _interp(area_ratio, _ar_table, _tn_table) * (0.95 + 0.05 * scale)
    theta_e_deg = _interp(area_ratio, _ar_table, _te_table) * (1.0 / scale) ** 0.3
    theta_n = math.radians(theta_n_deg)
    theta_e = math.radians(theta_e_deg)

    # Inflection point N (on the circular arc of radius 0.382 Rt)
    arc_r = 0.382 * r_throat
    x_n = arc_r * math.sin(theta_n)
    r_n = r_throat + arc_r * (1.0 - math.cos(theta_n))

    # Exit point E
    x_e = l_bell
    r_e = r_exit

    # Fit parabola r(x) = a·x² + b·x + c matching:
    #   r(x_n) = r_n,  r'(x_n) = tan(theta_n)
    #   r(x_e) = r_e,  r'(x_e) = tan(theta_e)
    # Use Hermite cubic parametric form
    # Parametric: P(t) = (1−t)³ P0 + 3(1−t)²t P1 + 3(1−t)t² P2 + t³ P3
    # with tangent vectors derived from angles

    dx = x_e - x_n
    # Control points for cubic Bezier
    k = dx / 3.0
    cx0, cy0 = x_n, r_n
    cx1 = x_n + k
    cy1 = r_n + k * math.tan(theta_n)
    cx2 = x_e - k
    cy2 = r_e - k * math.tan(theta_e)
    cx3, cy3 = x_e, r_e

    # Compute throat region arc + bell parabola
    contour = []

    # Upstream arc (from ~0° to theta_n): circular arc in the convergent/throat section
    # For divergent section only (x ≥ 0 from throat):
    n_arc = max(5, n_points // 10)
    for i in range(n_arc):
        phi = theta_n * i / (n_arc - 1) if n_arc > 1 else 0.0
        xp = arc_r * math.sin(phi)
        rp = r_throat + arc_r * (1.0 - math.cos(phi))
        contour.append({"x": xp, "r": rp})

    # Bell section (Bezier cubic from N to E)
    n_bell = n_points - n_arc
    for i in range(1, n_bell + 1):
        t = i / n_bell
        mt = 1.0 - t
        xp = mt**3 * cx0 + 3 * mt**2 * t * cx1 + 3 * mt * t**2 * cx2 + t**3 * cx3
        rp = mt**3 * cy0 + 3 * mt**2 * t * cy1 + 3 * mt * t**2 * cy2 + t**3 * cy3
        contour.append({"x": xp, "r": rp})

    return {
        "ok": True,
        "contour": contour,
        "length": l_bell,
        "area_ratio": area_ratio,
        "theta_n_deg": theta_n_deg,
        "theta_e_deg": theta_e_deg,
        "length_fraction": length_fraction,
        "r_throat": r_throat,
        "r_exit": r_exit,
        "n_points": len(contour),
    }


# ---------------------------------------------------------------------------
# Internal: Brent's root-finding algorithm
# ---------------------------------------------------------------------------

def _brent(f, xa: float, xb: float, tol: float = _TOL) -> float | None:
    """Brent's method for f(x) = 0 on [xa, xb]. Returns root or None."""
    fa, fb = f(xa), f(xb)
    if fa * fb > 0:
        return None
    if abs(fa) < abs(fb):
        xa, xb = xb, xa
        fa, fb = fb, fa
    xc, fc = xa, fa
    mflag = True
    xs = xb
    xd = 0.0

    for _ in range(_MAX_ITER):
        if abs(xb - xa) < tol:
            return xb
        if fa != fc and fb != fc:
            # Inverse quadratic interpolation
            xs = (
                xa * fb * fc / ((fa - fb) * (fa - fc))
                + xb * fa * fc / ((fb - fa) * (fb - fc))
                + xc * fa * fb / ((fc - fa) * (fc - fb))
            )
        else:
            xs = xb - fb * (xb - xa) / (fb - fa)

        cond1 = not (3 * xa + xb) / 4 < xs < xb and not xb < xs < (3 * xa + xb) / 4
        # Simplified boundary check
        lo, hi = min(xa, xb), max(xa, xb)
        cond1 = not (lo < xs < hi)
        cond2 = mflag and abs(xs - xb) >= abs(xb - xc) / 2
        cond3 = (not mflag) and abs(xs - xb) >= abs(xc - xd) / 2
        cond4 = mflag and abs(xb - xc) < tol
        cond5 = (not mflag) and abs(xc - xd) < tol

        if cond1 or cond2 or cond3 or cond4 or cond5:
            xs = (xa + xb) / 2
            mflag = True
        else:
            mflag = False

        fs = f(xs)
        xd, xc = xc, xb

        if fa * fs < 0:
            xb, fb = xs, fs
        else:
            xa, fa = xs, fs

        if abs(fa) < abs(fb):
            xa, fa, xb, fb = xb, fb, xa, fa

    return xb  # best estimate after max iterations
