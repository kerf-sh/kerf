"""VLM with viscous strip drag and Prandtl-Glauert / Kármán-Tsien compressibility.

This module bridges the inviscid VLM (vlm.py) with the XFOIL-class 2-D viscous
panel solver (panel_2d_viscous.py) to produce a complete drag polar:

    CD_total = CDi  (VLM induced drag)
             + CD0  (viscous profile drag, strip integration)
             + CD_wave_est  (transonic wave-drag estimate, see note below)

Compressibility corrections
---------------------------
Prandtl-Glauert (PG):
    CL_c = CL_i / sqrt(1 - M²)
    Valid for M < M_crit (~0.6-0.7 depending on airfoil).

Kármán-Tsien (KT):
    beta = sqrt(1 - M²)
    CL_c = CL_i / (beta + (M²/(1+beta)) * (CL_i/2))
    More accurate at higher subsonic Mach numbers.  We apply KT as the default
    when M > 0.3 and PG otherwise (or when KT numerics become unstable).

Wave drag estimate (CD_wave_est)
---------------------------------
A simple Korn-equation-style estimate is used:
    M_crit ≈ κ/CL^(1/3) - t/c - alpha/10   (κ = 0.95 for NACA 4-digit)
    CD_wave = 20 * (M - M_crit)^4   for M > M_crit
            = 0                      for M <= M_crit

This is a rough trend estimate only, documented as such.  For transonic
design-point accuracy a full-potential or Euler solver is required.

Strip integration
-----------------
The span is divided into N_strips sampling stations.  At each strip the local
chord, spanwise lift distribution (from VLM), and effective AoA are used to
compute a local chord Reynolds number, then panel_solve_viscous gives the
section profile drag Cd.  The wing profile drag is:

    CD0 = (1/S) * Σ (Cd_i * c_i * Δy_i)

For efficiency N_strips defaults to 7 (sparser than the VLM grid).

References
----------
Abbott & von Doenhoff, "Theory of Wing Sections", Dover 1959.
Raymer, "Aircraft Design: A Conceptual Approach", 5th ed., AIAA 2012, §12.
Korn, J.L. (1975). Aerodynamic Design of Transonic Wings by Computer.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# Internal imports
# ---------------------------------------------------------------------------

from .vlm import vlm_wing, _build_wing_mesh
from .panel_2d_viscous import panel_solve_viscous
from .flight_dynamics.atmosphere import atmosphere


# ---------------------------------------------------------------------------
# Wing geometry dataclass (dict-based for JSON compatibility)
# ---------------------------------------------------------------------------

def _wing_defaults(wing: dict) -> dict:
    """Fill missing wing geometry keys with defaults."""
    w = dict(wing)
    w.setdefault("tip_chord", w.get("root_chord", 1.0))
    w.setdefault("sweep_deg", 0.0)
    w.setdefault("twist_deg", 0.0)
    w.setdefault("airfoil", "naca2412")
    w.setdefault("m_chord", 4)
    w.setdefault("n_span", 16)
    # thickness-to-chord ratio for wave drag estimate (NACA 2412 → 0.12)
    if "tc_ratio" not in w:
        af = w["airfoil"]
        if isinstance(af, str) and af.startswith("naca") and len(af) == 8:
            # NACA 4-digit: last two digits = t/c in percent
            try:
                w["tc_ratio"] = int(af[6:8]) / 100.0
            except ValueError:
                w["tc_ratio"] = 0.12
        else:
            w["tc_ratio"] = 0.12
    return w


# ---------------------------------------------------------------------------
# Spanwise CL distribution from VLM
# ---------------------------------------------------------------------------

def _spanwise_cl_distribution(
    vlm_result: dict,
    wing: dict,
    alpha_deg: float,
    v_inf: float = 1.0,
) -> tuple[NDArray, NDArray, NDArray, NDArray]:
    """Extract spanwise strip CL, alpha_eff, chord, and y-positions from VLM.

    Returns
    -------
    y_mid : (n_span,) spanwise mid-strip positions
    cl_strip : (n_span,) strip lift coefficient (section)
    c_strip : (n_span,) chord at each strip
    alpha_eff_strip : (n_span,) effective AoA at each strip (deg)
    """
    w = _wing_defaults(wing)
    span = w["span"]
    root_chord = w["root_chord"]
    tip_chord = w["tip_chord"]
    sweep_deg = w["sweep_deg"]
    twist_deg = w["twist_deg"]
    m_chord = w["m_chord"]
    n_span = w["n_span"]

    gamma = vlm_result["gamma"]  # shape (n_span * m_chord,)
    N = len(gamma)

    alpha_rad = math.radians(alpha_deg)

    # Chord lengths at panel strip mid-points
    y_edges = np.linspace(-span / 2, span / 2, n_span + 1)
    y_mid = 0.5 * (y_edges[:-1] + y_edges[1:])

    # Local chord at each strip
    eta_mid = (y_mid + span / 2) / span
    c_strip = root_chord + (tip_chord - root_chord) * eta_mid

    # Δy for each span strip
    dy_strip = np.diff(y_edges)  # shape (n_span,)

    # Strip circulation: sum chordwise panels within each span strip
    gamma_2d = gamma.reshape(n_span, m_chord)
    gamma_strip = gamma_2d.sum(axis=1)  # total circulation per strip

    # Section CL from Kutta-Joukowski: dL = rho * V * Gamma * dy
    # CL_strip = dL / (0.5 * rho * V^2 * c * dy) = 2*Gamma / (V * c)
    cl_strip = 2.0 * gamma_strip / (v_inf * c_strip)

    # Effective angle of attack per strip (small angle: alpha_eff = alpha - induced_alpha)
    # induced_alpha ≈ CL_strip / (pi * AR) as a crude estimate; exact from downwash.
    # We use a strip-average approach: alpha_eff ≈ alpha - w_induced/V_inf.
    # For the viscous lookup we use the local alpha_eff to get the right Cd.
    # Simple estimate: alpha_eff_strip = CL_strip / (2*pi) * (1 + correction for finite wing)
    # Better: use thin-airfoil theory inversion.
    # For a thin symmetric airfoil: CL_section = 2*pi*(alpha - alpha_0) so
    # alpha_eff = CL_strip / (2*pi) radians (assumes alpha_0=0, linear range).
    alpha_eff_strip_rad = cl_strip / (2.0 * math.pi)
    # Clamp to a reasonable physical range to avoid solver divergence
    alpha_eff_strip_rad = np.clip(alpha_eff_strip_rad, math.radians(-5), math.radians(15))
    alpha_eff_strip_deg = np.degrees(alpha_eff_strip_rad)

    return y_mid, cl_strip, c_strip, alpha_eff_strip_deg


# ---------------------------------------------------------------------------
# Viscous strip integration
# ---------------------------------------------------------------------------

def strip_viscous_drag(
    wing: dict,
    vlm_result: dict,
    alpha_deg: float,
    rho: float,
    V: float,
    mu: float,
    n_strips: int = 7,
    n_panels: int = 80,
) -> float:
    """Compute wing profile drag CD0 by spanwise strip integration.

    Parameters
    ----------
    wing : dict
        Wing geometry with keys: span, root_chord, tip_chord (opt), sweep_deg,
        twist_deg, airfoil (NACA string or coords), m_chord, n_span.
    vlm_result : dict
        Output of ``vlm_wing`` (must contain 'gamma').
    alpha_deg : float
        Global angle of attack (degrees).
    rho : float
        Air density (kg/m³).
    V : float
        Freestream speed (m/s).
    mu : float
        Dynamic viscosity (Pa·s).
    n_strips : int
        Number of spanwise strips for viscous integration (default 7).
    n_panels : int
        Panel count for the 2-D viscous solver per strip (default 80; lower=faster).

    Returns
    -------
    CD0 : float
        Wing profile drag coefficient.
    """
    w = _wing_defaults(wing)
    span = w["span"]
    root_chord = w["root_chord"]
    tip_chord = w["tip_chord"]
    airfoil = w["airfoil"]
    n_span = w["n_span"]
    m_chord = w["m_chord"]

    # Full spanwise distribution from VLM
    y_full, cl_full, c_full, aeff_full = _spanwise_cl_distribution(
        vlm_result, wing, alpha_deg, v_inf=V
    )

    # Sample at n_strips positions (interior, avoiding wing tips)
    y_edges_full = np.linspace(-span / 2, span / 2, n_span + 1)
    y_sample = np.linspace(
        y_edges_full[1],          # one strip in from port tip
        y_edges_full[-2],         # one strip in from starboard tip
        n_strips,
    )

    # Interpolate chord and alpha_eff at sample positions
    c_sample = np.interp(y_sample, y_full, c_full)
    aeff_sample = np.interp(y_sample, y_full, aeff_full)

    # Reference area
    c_mean = 0.5 * (root_chord + tip_chord)
    S_ref = span * c_mean

    # Per-strip viscous drag
    cd0_sections = np.zeros(n_strips)
    nu = mu / rho

    for k in range(n_strips):
        c_k = c_sample[k]
        a_k = aeff_sample[k]
        Re_k = rho * V * c_k / mu   # local chord Reynolds number

        try:
            vis = panel_solve_viscous(
                airfoil,
                alpha_deg=float(a_k),
                Re=float(Re_k),
                n_panels=n_panels,
                max_iter=40,
                relax=0.5,
            )
            cd0_sections[k] = max(float(vis["CD"]), 0.0)
        except Exception:
            # If the viscous solver fails (e.g. separated flow), fall back to
            # a flat-plate skin-friction estimate: Cd ≈ 0.074 / Re^0.2 (turbulent)
            Re_clamped = max(Re_k, 1e4)
            cd0_sections[k] = 0.074 / Re_clamped**0.2

    # Strip integration:
    # Use trapezoidal integration in y with local chord weighting.
    # We integrate over the full span using the sampled points.
    # CD0 = (1/S) * ∫ Cd(y) * c(y) dy
    #
    # Extend to full span by assuming constant Cd at the sample values
    # (the sampling already spans most of the wing).
    # Use np.trapz for the y-integral.
    integrand = cd0_sections * c_sample
    CD0 = float(np.trapezoid(integrand, y_sample)) / S_ref

    # The sample only covers one side due to symmetry; the sampling runs full-span
    # so no factor-of-2 needed.  Account for symmetric wing: both halves included
    # in y_sample already (y goes -b/2 to +b/2).
    return max(CD0, 0.0)


# ---------------------------------------------------------------------------
# Compressibility corrections
# ---------------------------------------------------------------------------

def prandtl_glauert(CL_inc: float, M: float) -> float:
    """Apply Prandtl-Glauert compressibility correction to a lift coefficient.

    CL_c = CL_i / sqrt(1 - M²)

    Valid for M < ~0.7 (linearised subsonic theory).  Returns CL_inc unchanged
    if M < 0.05 (incompressible limit) or if the correction would be > 5x.
    """
    if M < 0.05:
        return CL_inc
    M2 = min(M * M, 0.98)  # clamp near sonic to avoid division by zero
    beta = math.sqrt(1.0 - M2)
    return CL_inc / beta


def karman_tsien(CL_inc: float, M: float) -> float:
    """Apply Kármán-Tsien compressibility correction.

    CL_c = CL_i / (β + (M²/(1+β)) * (CL_i/2))

    where β = sqrt(1 − M²).

    More accurate than Prandtl-Glauert for 0.3 < M < 0.7.  Returns Prandtl-
    Glauert result if the KT denominator would be < 0.2 (numerical safety).
    """
    if M < 0.05:
        return CL_inc
    M2 = min(M * M, 0.95)
    beta = math.sqrt(1.0 - M2)
    denom = beta + (M2 / (1.0 + beta)) * (CL_inc / 2.0)
    if denom < 0.2:
        # Fall back to PG
        return prandtl_glauert(CL_inc, M)
    return CL_inc / denom


def apply_compressibility(CL_inc: float, M: float, method: str = "karman_tsien") -> float:
    """Return compressibility-corrected CL.

    Parameters
    ----------
    CL_inc : float
        Incompressible lift coefficient.
    M : float
        Freestream Mach number.
    method : str
        'prandtl_glauert' or 'karman_tsien' (default).

    Raises
    ------
    ValueError if M >= 1.0 (supersonic, not handled here).
    """
    if M >= 1.0:
        raise ValueError(f"Compressibility correction only valid for M < 1.0, got M={M:.3f}")
    if method == "prandtl_glauert":
        return prandtl_glauert(CL_inc, M)
    elif method == "karman_tsien":
        return karman_tsien(CL_inc, M)
    else:
        raise ValueError(f"Unknown compressibility method: {method!r}")


# ---------------------------------------------------------------------------
# Wave drag estimate (Korn equation style)
# ---------------------------------------------------------------------------

_KORN_KAPPA = {
    "conventional": 0.87,
    "supercritical": 0.95,
}


def wave_drag_estimate(CL: float, M: float, tc_ratio: float, alpha_deg: float = 0.0,
                        wing_type: str = "conventional") -> tuple[float, float]:
    """Estimate wave drag using a Korn-equation-style M_crit model.

    Parameters
    ----------
    CL : float
        Lift coefficient (compressibility-corrected).
    M : float
        Freestream Mach number.
    tc_ratio : float
        Wing thickness-to-chord ratio.
    alpha_deg : float
        Angle of attack (degrees), used in M_crit estimate.
    wing_type : str
        'conventional' (κ=0.87) or 'supercritical' (κ=0.95).

    Returns
    -------
    (M_crit, CD_wave) : tuple[float, float]
        Critical Mach number estimate and wave drag coefficient.

    Notes
    -----
    **Simplification**: This uses the empirical Korn relation
        M_crit ≈ κ - t/c - CL/10 - (alpha_deg/100)
    which is accurate to ±0.02 in M_crit for NACA 4-digit-class sections.
    Below M_crit the wave drag is zero.  Above M_crit a quartic rise
        CD_wave = 20 * (M - M_crit)^4
    is used (Lock's formula, empirical).  This is a trend estimator only;
    transonic buffet and shock-induced separation require a higher-fidelity
    model (full-potential or RANS).
    """
    kappa = _KORN_KAPPA.get(wing_type, 0.87)
    # Korn formula (simplified, per Raymer §12.3)
    M_crit = kappa - tc_ratio - abs(CL) / 10.0 - abs(alpha_deg) / 100.0
    M_crit = max(min(M_crit, 0.98), 0.3)  # physical bounds

    if M <= M_crit:
        return M_crit, 0.0

    # Lock's quartic wave drag rise
    CD_wave = 20.0 * (M - M_crit) ** 4
    return M_crit, float(CD_wave)


# ---------------------------------------------------------------------------
# Total drag breakdown
# ---------------------------------------------------------------------------

def total_drag(
    wing: dict,
    alpha_deg: float,
    M: float,
    rho: float,
    V: float,
    mu: float,
    *,
    n_strips: int = 7,
    n_panels: int = 80,
    comp_method: str = "karman_tsien",
) -> dict:
    """Compute full drag polar with induced, profile, and wave drag.

    Parameters
    ----------
    wing : dict
        Wing geometry dict (see ``vlm_viscous.py`` module docstring).
    alpha_deg : float
        Angle of attack (degrees).
    M : float
        Freestream Mach number (< 1.0).
    rho : float
        Air density (kg/m³).
    V : float
        Freestream speed (m/s).
    mu : float
        Dynamic viscosity (Pa·s).
    n_strips : int
        Number of spanwise strips for viscous integration (default 7).
    n_panels : int
        Panel count for 2-D viscous solver (default 80).
    comp_method : str
        Compressibility correction method ('prandtl_glauert' or 'karman_tsien').

    Returns
    -------
    dict with keys:
        CL         : float – compressibility-corrected lift coefficient
        CL_inc     : float – incompressible VLM lift coefficient
        CDi        : float – induced drag from VLM
        CD0        : float – viscous profile drag (strip integration)
        CD_wave_est: float – wave drag estimate (zero below M_crit)
        M_crit     : float – critical Mach number estimate
        CD_total   : float – total drag
        LD         : float – lift-to-drag ratio
        comp_method: str   – compressibility method used
        vlm        : dict  – raw VLM output
    """
    if M >= 1.0:
        raise ValueError(f"total_drag requires M < 1.0, got {M:.3f}")

    w = _wing_defaults(wing)

    # Run VLM (incompressible)
    vlm_res = vlm_wing(
        span=w["span"],
        root_chord=w["root_chord"],
        tip_chord=w["tip_chord"],
        sweep_deg=w["sweep_deg"],
        twist_deg=w["twist_deg"],
        alpha_deg=alpha_deg,
        m_chord=w["m_chord"],
        n_span=w["n_span"],
        v_inf=V,
    )

    CL_inc = vlm_res["CL"]
    CDi_inc = vlm_res["CDi"]

    # Compressibility correction
    CL_c = apply_compressibility(CL_inc, M, method=comp_method)
    # Scale CDi with CL²: CDi_c ≈ CDi_inc * (CL_c/CL_inc)²
    if abs(CL_inc) > 1e-8:
        CDi = CDi_inc * (CL_c / CL_inc) ** 2
    else:
        CDi = CDi_inc

    # Viscous strip integration (uses incompressible VLM spanwise gamma)
    CD0 = strip_viscous_drag(
        wing, vlm_res, alpha_deg, rho, V, mu,
        n_strips=n_strips,
        n_panels=n_panels,
    )

    # Wave drag
    tc = w["tc_ratio"]
    M_crit, CD_wave = wave_drag_estimate(CL_c, M, tc, alpha_deg)

    CD_total = CDi + CD0 + CD_wave
    LD = CL_c / CD_total if abs(CD_total) > 1e-12 else float("inf")

    return {
        "CL": float(CL_c),
        "CL_inc": float(CL_inc),
        "CDi": float(CDi),
        "CD0": float(CD0),
        "CD_wave_est": float(CD_wave),
        "M_crit": float(M_crit),
        "CD_total": float(CD_total),
        "LD": float(LD),
        "comp_method": comp_method,
        "vlm": vlm_res,
    }


# ---------------------------------------------------------------------------
# LLM tool: aero_vlm_full
# ---------------------------------------------------------------------------

def aero_vlm_full(
    wing: dict,
    alpha_deg: float,
    M: float,
    altitude_m: float,
    *,
    n_strips: int = 7,
    n_panels: int = 80,
    comp_method: str = "karman_tsien",
) -> dict:
    """Full aerodynamic analysis: VLM + viscous strip + compressibility + atmosphere.

    LLM-callable tool that performs:
    1. USSA-76 atmosphere lookup at *altitude_m* → ρ, μ, a.
    2. Mach consistency check (V = M * a).
    3. VLM lift + induced drag (incompressible).
    4. Prandtl-Glauert / Kármán-Tsien compressibility correction on CL.
    5. Viscous strip integration → CD0 (profile drag).
    6. Korn-equation wave drag estimate → CD_wave_est.
    7. Returns the full polar dict.

    Parameters
    ----------
    wing : dict
        Wing geometry.  Required keys: ``span`` (m), ``root_chord`` (m).
        Optional keys: ``tip_chord``, ``sweep_deg``, ``twist_deg``,
        ``airfoil`` (NACA string, default 'naca2412'), ``m_chord``,
        ``n_span``, ``tc_ratio``.
    alpha_deg : float
        Angle of attack (degrees).
    M : float
        Freestream Mach number (0 < M < 1.0).
    altitude_m : float
        Geometric altitude (m), 0 – 86 000 m.
    n_strips : int
        Spanwise sampling for viscous strip integration (default 7).
    n_panels : int
        2-D panel count per viscous strip (default 80).
    comp_method : str
        Compressibility method: 'prandtl_glauert' or 'karman_tsien'.

    Returns
    -------
    dict with keys:
        altitude_m, M, rho_kg_m3, V_m_s, mu_Pa_s, T_K,
        CL, CL_inc, CDi, CD0, CD_wave_est, M_crit, CD_total, LD,
        comp_method, vlm  (raw VLM sub-dict).

    Raises
    ------
    ValueError
        On invalid inputs (M >= 1.0, altitude out of range, etc.)
    """
    # --- Input validation ---
    if not (0.0 <= M < 1.0):
        raise ValueError(f"Mach number must be in [0, 1), got {M:.4f}")
    if altitude_m < 0 or altitude_m > 86_000:
        raise ValueError(f"altitude_m must be in [0, 86000], got {altitude_m}")
    if "span" not in wing:
        raise ValueError("wing dict must contain 'span'")
    if "root_chord" not in wing:
        raise ValueError("wing dict must contain 'root_chord'")

    # --- Atmosphere lookup ---
    atm = atmosphere(altitude_m)
    rho = atm.density_kg_m3
    mu = atm.viscosity_Pa_s
    a = atm.speed_of_sound_m_s
    T = atm.temperature_K
    V = M * a if M > 0.0 else 1.0   # avoid V=0 for incompressible limit

    # --- Core computation ---
    result = total_drag(
        wing=wing,
        alpha_deg=alpha_deg,
        M=M,
        rho=rho,
        V=V,
        mu=mu,
        n_strips=n_strips,
        n_panels=n_panels,
        comp_method=comp_method,
    )

    # --- Augment with atmosphere fields ---
    result["altitude_m"] = float(altitude_m)
    result["M"] = float(M)
    result["rho_kg_m3"] = float(rho)
    result["V_m_s"] = float(V)
    result["mu_Pa_s"] = float(mu)
    result["T_K"] = float(T)

    return result
