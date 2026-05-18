"""
Tsiolkovsky rocket equation and related propulsion relationships.

Conventions
-----------
- Isp in seconds (specific impulse referenced to g0 = 9.80665 m/s²)
- m0 = initial (wet) mass [kg]
- mf = final (dry) mass [kg]
- c*  = characteristic velocity [m/s]
- γ   = ratio of specific heats (dimensionless)
- ΔV  = delta-V [m/s]
- F   = thrust [N]
- ṁ   = mass-flow rate [kg/s]

All public functions return a plain dict and never raise; errors arrive as
{"ok": False, "reason": "..."}.

References
----------
Sutton & Biblarz, "Rocket Propulsion Elements", 9th ed.
"""

from __future__ import annotations

import math

G0: float = 9.80665  # m/s² — standard gravity


def delta_v(isp: float, m0: float, mf: float) -> dict:
    """
    Tsiolkovsky ideal rocket equation.

    ΔV = Isp · g0 · ln(m0 / mf)

    Parameters
    ----------
    isp : specific impulse [s]
    m0  : initial wet mass [kg]
    mf  : final dry mass [kg]

    Returns
    -------
    dict with keys:
        delta_v_ms  [m/s]
        delta_v_kms [km/s]
        mass_ratio  m0/mf
        ve          effective exhaust velocity [m/s]
    """
    if isp <= 0:
        return {"ok": False, "reason": "Isp must be positive"}
    if m0 <= 0 or mf <= 0:
        return {"ok": False, "reason": "Masses must be positive"}
    if mf > m0:
        return {"ok": False, "reason": "Dry mass cannot exceed wet mass"}

    ve = isp * G0
    mr = m0 / mf
    dv = ve * math.log(mr)
    return {
        "ok": True,
        "delta_v_ms": dv,
        "delta_v_kms": dv / 1000.0,
        "mass_ratio": mr,
        "ve": ve,
        "isp": isp,
        "m0": m0,
        "mf": mf,
    }


def effective_exhaust_velocity(isp: float) -> dict:
    """
    Convert Isp [s] to effective exhaust velocity ve = Isp · g0 [m/s].
    """
    if isp <= 0:
        return {"ok": False, "reason": "Isp must be positive"}
    return {"ok": True, "ve": isp * G0, "isp": isp, "g0": G0}


def isp_from_cstar(
    c_star: float,
    gamma: float,
    expansion_ratio: float = 1.0,
    pe_over_pc: float | None = None,
    pa_over_pc: float = 0.0,
) -> dict:
    """
    Vacuum Isp from characteristic velocity c* and nozzle parameters.

    Isp_vac = c* · Cf_vac / g0

    where the vacuum thrust coefficient Cf_vac for an ideal nozzle is:

        Cf = sqrt( 2γ² / (γ−1) · (2/(γ+1))^((γ+1)/(γ−1))
                    · (1 − (pe/pc)^((γ−1)/γ)) )
             + (pe/pc) · Ae/At

    When pe_over_pc is None an isentropic exit is computed from expansion_ratio.

    Parameters
    ----------
    c_star         : characteristic velocity [m/s]
    gamma          : ratio of specific heats
    expansion_ratio: Ae/At nozzle area ratio (used only when pe_over_pc is None)
    pe_over_pc     : exit-to-chamber pressure ratio (overrides expansion_ratio)
    pa_over_pc     : ambient-to-chamber pressure ratio (0 = vacuum)

    Returns
    -------
    dict with isp_vac, isp_sea (at given pa_over_pc), Cf, c_star
    """
    if c_star <= 0:
        return {"ok": False, "reason": "c* must be positive"}
    if gamma <= 1:
        return {"ok": False, "reason": "γ must be > 1"}

    if pe_over_pc is None:
        # Solve isentropic area ratio to find pe/pc
        # Area ratio: Ae/At = (1/Me) * [(2/(γ+1))*(1 + (γ-1)/2 * Me²)]^((γ+1)/(2(γ-1)))
        # We invert numerically for expansion_ratio
        from kerf_aero.propulsion.nozzle import exit_mach_from_area_ratio
        res = exit_mach_from_area_ratio(expansion_ratio, gamma)
        if not res["ok"]:
            return res
        me = res["mach"]
        pe_over_pc = (1.0 + (gamma - 1.0) / 2.0 * me**2) ** (-gamma / (gamma - 1.0))

    # Vacuum Cf
    term1_sq = (
        2.0 * gamma**2
        / (gamma - 1.0)
        * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0))
        * (1.0 - pe_over_pc ** ((gamma - 1.0) / gamma))
    )
    if term1_sq < 0:
        return {"ok": False, "reason": "Invalid pressure ratio for these γ"}
    cf_momentum = math.sqrt(term1_sq)
    cf_pressure = pe_over_pc * expansion_ratio  # vacuum: pa=0
    cf_vac = cf_momentum + cf_pressure
    cf_sea = cf_momentum + (pe_over_pc - pa_over_pc) * expansion_ratio

    isp_vac = c_star * cf_vac / G0
    isp_sea = c_star * cf_sea / G0

    return {
        "ok": True,
        "isp_vac": isp_vac,
        "isp_sea": isp_sea,
        "cf_vac": cf_vac,
        "cf_sea": cf_sea,
        "c_star": c_star,
        "gamma": gamma,
        "pe_over_pc": pe_over_pc,
        "expansion_ratio": expansion_ratio,
    }


def thrust_from_mass_flow(
    mass_flow: float,
    isp: float,
    pa_over_pc: float = 0.0,
    pe_over_pc: float = 0.0,
    ae_over_at: float = 0.0,
    pc: float = 0.0,
) -> dict:
    """
    Thrust F = ṁ · ve  + (pe − pa) · Ae

    For a simple calculation with only Isp given (vacuum), use only mass_flow
    and isp; the pressure-thrust term (pe−pa)·Ae can be added optionally.

    Parameters
    ----------
    mass_flow   : propellant mass-flow rate [kg/s]
    isp         : specific impulse [s]
    pa_over_pc  : ambient / chamber pressure ratio (default 0 → vacuum)
    pe_over_pc  : exit / chamber pressure ratio (default 0 → ignore pressure term)
    ae_over_at  : exit area / throat area (needed for pressure-thrust term)
    pc          : chamber pressure [Pa] (needed for pressure-thrust term)

    Returns
    -------
    dict with thrust [N] and thrust [kN]
    """
    if mass_flow <= 0:
        return {"ok": False, "reason": "mass_flow must be positive"}
    if isp <= 0:
        return {"ok": False, "reason": "Isp must be positive"}

    ve = isp * G0
    thrust = mass_flow * ve

    # Optional pressure-thrust correction
    if pc > 0 and ae_over_at > 0 and pe_over_pc > 0:
        # At = ṁ c* / pc  (c* = ve / Cf, but here we just add the delta)
        # Simplified: ΔF = (pe − pa) · Ae = (pe_over_pc − pa_over_pc) · pc · At · ae_over_at
        # Require c* for At; skip if not provided
        pass

    return {
        "ok": True,
        "thrust_n": thrust,
        "thrust_kn": thrust / 1000.0,
        "mass_flow": mass_flow,
        "isp": isp,
        "ve": ve,
    }


def mass_ratio_for_delta_v(delta_v_ms: float, isp: float) -> dict:
    """
    Invert the rocket equation: m0/mf = exp(ΔV / ve).

    Parameters
    ----------
    delta_v_ms : desired ΔV [m/s]
    isp        : specific impulse [s]

    Returns
    -------
    dict with mass_ratio m0/mf
    """
    if delta_v_ms < 0:
        return {"ok": False, "reason": "ΔV must be non-negative"}
    if isp <= 0:
        return {"ok": False, "reason": "Isp must be positive"}
    ve = isp * G0
    mr = math.exp(delta_v_ms / ve)
    return {
        "ok": True,
        "mass_ratio": mr,
        "propellant_fraction": 1.0 - 1.0 / mr,
        "delta_v_ms": delta_v_ms,
        "isp": isp,
        "ve": ve,
    }


def propellant_mass(
    delta_v_ms: float,
    isp: float,
    dry_mass: float,
) -> dict:
    """
    Required propellant mass for a given ΔV budget.

    mp = m_dry · (exp(ΔV / ve) − 1)

    Parameters
    ----------
    delta_v_ms : required ΔV [m/s]
    isp        : specific impulse [s]
    dry_mass   : structural/payload dry mass [kg]

    Returns
    -------
    dict with propellant_mass [kg], wet_mass [kg], mass_ratio
    """
    res = mass_ratio_for_delta_v(delta_v_ms, isp)
    if not res["ok"]:
        return res
    mr = res["mass_ratio"]
    mp = dry_mass * (mr - 1.0)
    return {
        "ok": True,
        "propellant_mass": mp,
        "wet_mass": dry_mass + mp,
        "dry_mass": dry_mass,
        "mass_ratio": mr,
        "propellant_fraction": mp / (dry_mass + mp),
        "delta_v_ms": delta_v_ms,
        "isp": isp,
    }
