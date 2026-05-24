"""
kerf_cad_core.heatxfer.shell_tube_bell — Bell-Delaware shell-and-tube HX design.

Implements TEMA tube-layout and the full Bell-Delaware method for shell-side
heat transfer and pressure drop, following:

  Bell, K.J. (1963, 1981 update) — "Delaware Method" shell-side analysis.
  Kern, D.Q. (1950) "Process Heat Transfer" — Kern example kerosene cooler.
  TEMA (9th ed.) — tube-layout geometry.
  Shah & Sekulic (2003) "Fundamentals of Heat Exchanger Design" — Ch. 8.

Public API
----------
tube_count(shell_id, tube_od, pitch, layout, n_passes) → int
shell_tube_design(duty_W, t_hot_in, t_hot_out, t_cold_in, t_cold_out,
                  shell_props, tube_props, geometry) → dict

All functions are pure-Python; no OCC dependency.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SIGMA_SB = 5.670374419e-8  # Stefan-Boltzmann, not used here but conventional


# ---------------------------------------------------------------------------
# 1. TUBE-LAYOUT GEOMETRY (TEMA)
# ---------------------------------------------------------------------------

# Tube-count constants per layout (empirical TEMA table coefficients).
# Source: TEMA 9th ed., Table RGP-T-2.4 and Shah & Sekulic Table 8.1.
# For a given layout the effective packing factor η = N_tubes / (A_shell / A_pitch_cell)
# We use the standard TEMA tube-count formula:
#   N_t = CL / CTP * (D_s/P_t)^2
# where CL is the tube-layout constant and CTP is the tube-count correction.

_LAYOUT_CL: dict[str, float] = {
    "triangular_30":  0.866,   # sin(30°) packing fraction
    "rotated_60":     0.866,   # same cell area as 30°
    "square_90":      1.0,
    "rotated_45":     0.707,   # sin(45°)
}

_CTP_PASSES: dict[int, float] = {
    1: 0.93,
    2: 0.90,
    4: 0.85,
    6: 0.80,
}


def tube_count(
    shell_id: float,
    tube_od: float,
    pitch: float,
    layout: Literal["triangular_30", "rotated_60", "square_90", "rotated_45"],
    n_passes: int = 1,
) -> int:
    """
    Estimate tube count using the TEMA tube-layout formula.

    Parameters
    ----------
    shell_id : float
        Shell inner diameter (m).
    tube_od : float
        Tube outer diameter (m).
    pitch : float
        Tube pitch centre-to-centre (m). Must be >= 1.25 * tube_od (TEMA).
    layout : str
        One of "triangular_30", "rotated_60", "square_90", "rotated_45".
    n_passes : int
        Number of tube passes (1, 2, 4, or 6).

    Returns
    -------
    int
        Estimated number of tubes (≥ 1).

    References
    ----------
    TEMA 9th ed. Table RGP-T-2.4.
    Shah & Sekulic (2003) Eq. 8.1-8.3.
    """
    if shell_id <= 0:
        raise ValueError("shell_id must be > 0")
    if tube_od <= 0:
        raise ValueError("tube_od must be > 0")
    if pitch < 1.25 * tube_od - 1e-6:
        raise ValueError("pitch must be >= 1.25 * tube_od (TEMA minimum)")
    if layout not in _LAYOUT_CL:
        raise ValueError(f"layout must be one of {list(_LAYOUT_CL)}")
    if n_passes not in _CTP_PASSES:
        # fall back to nearest
        n_passes = min(_CTP_PASSES, key=lambda k: abs(k - n_passes))

    CL = _LAYOUT_CL[layout]
    CTP = _CTP_PASSES[n_passes]
    # TEMA formula: N_t = CTP/CL * (π/4) * (D_s/P_t)^2
    # (the π/4 comes from converting D_s² shell cross-section to tube-count)
    N_t = (CTP / CL) * (math.pi / 4.0) * (shell_id / pitch) ** 2
    return max(1, int(N_t))


# ---------------------------------------------------------------------------
# 2. SHELL-SIDE GEOMETRY (Bell-Delaware)
# ---------------------------------------------------------------------------

def _shell_geometry(geom: dict) -> dict:
    """
    Derive all Bell-Delaware geometric areas and fractions from geometry dict.

    Required keys in geom
    ---------------------
    D_s         : shell inner diameter (m)
    D_otl       : outer tube-limit diameter (m) — typically D_s - 12 mm
    D_ctl       : central tube-limit diameter = D_otl - tube_od  (m)
    tube_od     : tube outer diameter (m)
    pitch       : tube pitch (m)
    layout      : layout string
    B           : baffle spacing (central) (m)
    B_in        : inlet baffle spacing (m), default = B
    B_out       : outlet baffle spacing (m), default = B
    baffle_cut  : baffle cut fraction of shell diameter (dimensionless, e.g. 0.25)
    N_b         : number of baffles
    N_t         : number of tubes
    D_s_nozzle  : shell nozzle inner diameter (m) — for bypass estimation
    D_tb        : tube-to-baffle clearance (m), default 0.0008 m (TEMA C)
    D_sb        : shell-to-baffle clearance (m), default 0.003 m
    n_ss        : number of sealing strips pairs, default 1

    Returns dict with all derived geometry.
    """
    D_s = geom["D_s"]
    D_otl = geom.get("D_otl", D_s - 0.012)
    tube_od = geom["tube_od"]
    D_ctl = geom.get("D_ctl", D_otl - tube_od)
    pitch = geom["pitch"]
    layout = geom.get("layout", "triangular_30")
    B = geom["B"]
    B_in = geom.get("B_in", B)
    B_out = geom.get("B_out", B)
    baffle_cut = geom.get("baffle_cut", 0.25)   # fraction of D_s
    N_b = geom["N_b"]
    N_t = geom["N_t"]
    D_tb = geom.get("D_tb", 0.0008)
    D_sb = geom.get("D_sb", 0.0030)
    n_ss = geom.get("n_ss", 1)

    # Baffle cut height from shell centre
    l_c = baffle_cut * D_s   # linear cut height

    # --- Cross-flow area at shell centreline (Bell-Delaware eq. 8.11) ---
    # For triangular/rotated layout p_p (effective pitch perpendicular to flow)
    if layout in ("triangular_30", "rotated_60"):
        p_perp = pitch * math.sqrt(3) / 2  # for 30° triangular
        if layout == "rotated_60":
            p_perp = pitch * math.sqrt(3) / 2  # same
    else:
        p_perp = pitch  # square layouts

    # Fraction of tubes in cross-flow window
    theta_ctl = 2 * math.acos(max(-1.0, min(1.0, (D_s / 2 - l_c) / (D_ctl / 2))))
    F_c = 1 - theta_ctl / math.pi   # fraction of tubes in pure cross-flow

    # Ideal cross-flow area (m²) — Bell-Delaware eq. 8.11
    S_m = B * (D_s - D_otl + (D_otl - tube_od) / pitch * (pitch - tube_od))

    # --- Window area (baffle window) ---
    # Shell cross-section in baffle window
    A_s = math.pi * D_s ** 2 / 4
    theta_ds = 2 * math.acos(max(-1.0, min(1.0, 1 - 2 * baffle_cut)))
    A_fc = A_s * (theta_ds - math.sin(theta_ds)) / (2 * math.pi)  # window open area
    # Tubes in window
    N_t_w = int(N_t * (theta_ctl / (2 * math.pi)))
    A_t_w = N_t_w * math.pi * tube_od ** 2 / 4
    S_w = max(1e-6, A_fc - A_t_w)

    # --- Bypass area (S_b) — between bundle and shell ---
    D_s_nozzle = geom.get("D_s_nozzle", D_s * 0.2)
    S_b = B * (D_s - D_otl)

    # --- Leakage areas ---
    # Tube-to-baffle holes (each tube has one clearance circle per baffle)
    S_tb = 0.5 * N_t * math.pi / 4 * ((tube_od + D_tb) ** 2 - tube_od ** 2)
    # Shell-to-baffle annulus (partial arc ~ half circumference)
    theta_sb = 2 * math.acos(max(-1.0, min(1.0, 1 - 2 * D_sb / D_s)))
    S_sb = (math.pi / 4) * ((D_s + D_sb) ** 2 - D_s ** 2) * (1 - theta_sb / (2 * math.pi))
    S_sb = max(1e-8, S_sb)

    return {
        "S_m": S_m,
        "S_w": S_w,
        "S_b": S_b,
        "S_tb": S_tb,
        "S_sb": S_sb,
        "F_c": F_c,
        "N_t_w": N_t_w,
        "theta_ctl": theta_ctl,
        "B": B,
        "B_in": B_in,
        "B_out": B_out,
        "N_b": N_b,
        "N_t": N_t,
        "n_ss": n_ss,
        "D_s": D_s,
        "tube_od": tube_od,
        "pitch": pitch,
        "layout": layout,
        "baffle_cut": baffle_cut,
        "l_c": l_c,
    }


# ---------------------------------------------------------------------------
# 3. BELL-DELAWARE CORRECTION FACTORS
# ---------------------------------------------------------------------------

def _Jc(F_c: float) -> float:
    """
    Jc — baffle cut correction factor for cross-flow (Bell-Delaware).
    Accounts for tubes in baffle windows contributing less to shell-side h.
    Eq: Jc = 0.55 + 0.72 * F_c  (Shah & Sekulic Eq. 8.20)
    Range: 0.65 – 1.15 typical.
    """
    return 0.55 + 0.72 * F_c


def _Jl(S_tb: float, S_sb: float, S_m: float) -> float:
    """
    Jl — tube/baffle and shell/baffle leakage correction (Bell-Delaware).
    Streams A (tube-baffle) and E (shell-baffle) bypass the bundle.
    Eq: Jl = 0.44*(1 - r_s) + (1 - 0.44*(1-r_s)) * exp(-2.2 * r_lm)
    where r_s = S_sb/(S_tb+S_sb), r_lm = (S_tb+S_sb)/S_m
    Shah & Sekulic Eq. 8.24.
    """
    S_L = S_tb + S_sb
    if S_m <= 0 or S_L <= 0:
        return 1.0
    r_s = S_sb / S_L
    r_lm = S_L / S_m
    Jl = 0.44 * (1 - r_s) + (1 - 0.44 * (1 - r_s)) * math.exp(-2.2 * r_lm)
    return max(0.1, min(1.0, Jl))


def _Jb(S_b: float, S_m: float, n_ss: int, N_c: float) -> float:
    """
    Jb — bundle-to-shell bypass correction (Bell-Delaware stream C).
    Eq: Jb = exp(-C_bh * r_b * (1 - (2*n_ss/N_c)^(1/3)))  if n_ss < N_c/2
            = 1.0 otherwise
    C_bh = 1.35 (laminar) or 1.25 (turbulent), use 1.25 (conservative typical).
    r_b = S_b / S_m
    Shah & Sekulic Eq. 8.27.
    """
    if S_m <= 0:
        return 1.0
    r_b = S_b / S_m
    if N_c <= 0 or n_ss >= N_c / 2:
        return 1.0
    C_bh = 1.25
    Jb = math.exp(-C_bh * r_b * (1 - (2 * n_ss / N_c) ** (1 / 3)))
    return max(0.1, min(1.0, Jb))


def _Jr(Re_s: float) -> float:
    """
    Jr — adverse laminar-flow correction (Bell-Delaware).
    Significant only when Re_s < 20.
    Jr = 1 for Re_s >= 20.
    Jr = (10/N_c)^0.18 for Re_s < 20 (simplified; N_c not explicitly needed here).
    Use Bell (1981) simplified: Jr = (20/Re_s)^0.18 when Re_s < 20.
    Shah & Sekulic Eq. 8.30.
    """
    if Re_s >= 20:
        return 1.0
    return (20.0 / Re_s) ** 0.18


def _Js(N_b: int, B: float, B_in: float, B_out: float) -> float:
    """
    Js — unequal baffle-spacing correction (Bell-Delaware).
    Accounts for inlet/outlet baffle spacings differing from central spacing.
    Eq: Js = (N_b - 1 + B_in^(1-n_b) + B_out^(1-n_b)) / (N_b - 1 + B_in + B_out)
    where n_b = 0.6 (turbulent) or 1/3 (laminar); use 0.6.
    Normalised to B (central spacing).
    Shah & Sekulic Eq. 8.32.
    """
    if N_b <= 1 or B <= 0:
        return 1.0
    n_b = 0.6  # turbulent exponent
    Bin_n = (B_in / B) ** (1 - n_b)
    Bout_n = (B_out / B) ** (1 - n_b)
    numerator = (N_b - 1) + Bin_n + Bout_n
    denominator = (N_b - 1) + (B_in / B) + (B_out / B)
    if denominator <= 0:
        return 1.0
    return numerator / denominator


# ---------------------------------------------------------------------------
# 4. IDEAL BANK NUSSELT (Bell-Delaware j-factor)
# ---------------------------------------------------------------------------

def _ideal_bank_j(Re_s: float, layout: str) -> float:
    """
    Ideal cross-flow j-factor for a bank of tubes (Bell-Delaware).

    j = a1 * Re_s^(a2) * (1 + 0.14 * Re_s^a3) — piecewise in Re.
    Coefficients from Bell (1981) / Shah & Sekulic Table 8.2 for triangular pitch.
    For square pitch coefficients differ; use HEDH table values.

    Parameters
    ----------
    Re_s : float  Shell-side Reynolds number (ρ u_s D_o / μ).
    layout : str  Tube layout.

    Returns
    -------
    float  Colburn j-factor (j = Nu / (Re * Pr^(1/3))).
    """
    # Bell-Delaware piecewise coefficients (triangular 30°), HEDH 1983.
    # Ranges: Re < 10, 10-100, 100-1000, 1000-10000, > 10000
    tri_coefs = [
        (1e0,   1e1,   1.400, -0.667, 0.0),
        (1e1,   1e2,   1.360, -0.657, 0.0),
        (1e2,   1e3,   0.593, -0.477, 0.0),
        (1e3,   1e4,   0.321, -0.388, 0.0),
        (1e4,   1e7,   0.321, -0.388, 0.0),
    ]
    sq_coefs = [
        (1e0,   1e1,   1.550, -0.667, 0.0),
        (1e1,   1e2,   0.898, -0.539, 0.0),
        (1e2,   1e3,   0.408, -0.395, 0.0),
        (1e3,   1e4,   0.310, -0.333, 0.0),
        (1e4,   1e7,   0.310, -0.333, 0.0),
    ]
    coefs = sq_coefs if layout in ("square_90", "rotated_45") else tri_coefs
    Re_s = max(0.1, Re_s)
    for Re_lo, Re_hi, a1, a2, _ in coefs:
        if Re_s <= Re_hi:
            return a1 * Re_s ** a2
    # extrapolate last segment
    a1, a2 = coefs[-1][2], coefs[-1][3]
    return a1 * Re_s ** a2


# ---------------------------------------------------------------------------
# 5. SHELL-SIDE HEAT-TRANSFER COEFFICIENT
# ---------------------------------------------------------------------------

def shell_side_htc(
    m_dot_s: float,
    props_s: dict,
    geo: dict,
    N_c: float,
) -> tuple[float, float, dict]:
    """
    Compute shell-side heat-transfer coefficient h_s (W/m²·K) using
    the full Bell-Delaware method.

    Parameters
    ----------
    m_dot_s   : shell-side mass flow rate (kg/s)
    props_s   : {'rho': kg/m³, 'mu': Pa·s, 'cp': J/kg·K, 'k': W/m·K, 'Pr': -}
    geo       : geometry dict (output of _shell_geometry)
    N_c       : number of tube rows crossed in one cross-flow pass

    Returns
    -------
    h_s : float   shell-side heat-transfer coefficient (W/m²·K)
    Re_s : float  shell-side Reynolds number
    factors : dict  Jc, Jl, Jb, Jr, Js and j_ideal
    """
    S_m = geo["S_m"]
    rho = props_s["rho"]
    mu = props_s["mu"]
    k_f = props_s["k"]
    Pr = props_s.get("Pr", props_s["cp"] * mu / k_f)
    D_o = geo["tube_od"]

    G_s = m_dot_s / S_m   # mass velocity (kg/m²·s)
    Re_s = G_s * D_o / mu

    j_id = _ideal_bank_j(Re_s, geo["layout"])

    # Ideal h (before correction factors)
    h_id = j_id * Re_s * Pr ** (1 / 3) * k_f / D_o

    # Correction factors
    Jc = _Jc(geo["F_c"])
    Jl = _Jl(geo["S_tb"], geo["S_sb"], S_m)
    Jb = _Jb(geo["S_b"], S_m, geo["n_ss"], N_c)
    Jr = _Jr(Re_s)
    Js = _Js(geo["N_b"], geo["B"], geo["B_in"], geo["B_out"])

    h_s = h_id * Jc * Jl * Jb * Jr * Js

    return h_s, Re_s, {
        "j_ideal": j_id,
        "h_ideal": h_id,
        "Jc": Jc,
        "Jl": Jl,
        "Jb": Jb,
        "Jr": Jr,
        "Js": Js,
    }


# ---------------------------------------------------------------------------
# 6. TUBE-SIDE HEAT-TRANSFER COEFFICIENT
# ---------------------------------------------------------------------------

def tube_side_htc(
    m_dot_t: float,
    props_t: dict,
    D_i: float,
    N_t: int,
    n_passes: int = 1,
) -> tuple[float, float]:
    """
    Tube-side heat-transfer coefficient h_t using Dittus-Boelter (turbulent)
    or Sieder-Tate correction of Hausen (laminar).

    Parameters
    ----------
    m_dot_t   : total tube-side mass flow rate (kg/s)
    props_t   : {'rho', 'mu', 'cp', 'k', 'Pr'} — bulk fluid properties
    D_i       : tube inner diameter (m)
    N_t       : total tube count
    n_passes  : number of tube passes

    Returns
    -------
    h_t  : float  tube-side h (W/m²·K)
    Re_t : float  tube-side Reynolds number
    """
    mu = props_t["mu"]
    k_f = props_t["k"]
    Pr = props_t.get("Pr", props_t["cp"] * mu / k_f)

    # Flow per pass
    N_tubes_per_pass = N_t / n_passes
    m_per_tube = m_dot_t / N_tubes_per_pass
    A_tube = math.pi * D_i ** 2 / 4
    G_t = m_per_tube / A_tube  # kg/m²·s
    Re_t = G_t * D_i / mu

    if Re_t > 10_000:
        # Dittus-Boelter: Nu = 0.023 Re^0.8 Pr^0.4 (heating; conservative for cooling)
        Nu = 0.023 * Re_t ** 0.8 * Pr ** 0.4
    elif Re_t > 2_300:
        # Transition: linear interpolation
        Nu_lam = 3.66
        Nu_turb = 0.023 * 10_000 ** 0.8 * Pr ** 0.4
        Nu = Nu_lam + (Re_t - 2_300) / (10_000 - 2_300) * (Nu_turb - Nu_lam)
    else:
        # Sieder-Tate/Hausen laminar: Nu = 3.66 + correction
        # Hausen entry-length:
        # Nu = 3.66 + 0.065*(D/L)*Re*Pr / (1 + 0.04*((D/L)*Re*Pr)^(2/3))
        # Use L/D = 100 as default (long tube assumption)
        x = (1 / 100) * Re_t * Pr
        Nu = 3.66 + 0.065 * x / (1 + 0.04 * x ** (2 / 3))

    h_t = Nu * k_f / D_i
    return h_t, Re_t


# ---------------------------------------------------------------------------
# 7. OVERALL HEAT-TRANSFER COEFFICIENT
# ---------------------------------------------------------------------------

def overall_U(
    h_t: float,
    h_s: float,
    D_i: float,
    D_o: float,
    k_wall: float,
    R_foul_t: float = 0.0002,
    R_foul_s: float = 0.0002,
) -> float:
    """
    Overall heat-transfer coefficient U (W/m²·K) based on outer tube area.

    1/U = 1/h_t*(D_i/D_o) + R_foul_t*(D_i/D_o) + D_o*ln(D_o/D_i)/(2*k_wall)
            + R_foul_s + 1/h_s

    Follows HEDH / Shah & Sekulic Eq. 8.4.

    Parameters
    ----------
    h_t       : tube-side film coefficient (W/m²·K) — based on inner area
    h_s       : shell-side film coefficient (W/m²·K) — based on outer area
    D_i       : tube inner diameter (m)
    D_o       : tube outer diameter (m)
    k_wall    : tube-wall thermal conductivity (W/m·K)
    R_foul_t  : tube-side fouling resistance (m²·K/W). TEMA default 0.0002.
    R_foul_s  : shell-side fouling resistance (m²·K/W). TEMA default 0.0002.

    Returns
    -------
    float  U (W/m²·K)
    """
    if D_i <= 0 or D_o <= D_i:
        raise ValueError("D_i must be > 0 and D_o > D_i")
    ratio = D_i / D_o
    R_tube_wall = D_o * math.log(D_o / D_i) / (2 * k_wall)
    inv_U = (1 / h_t) * ratio + R_foul_t * ratio + R_tube_wall + R_foul_s + 1 / h_s
    return 1.0 / inv_U


# ---------------------------------------------------------------------------
# 8. PRESSURE DROP
# ---------------------------------------------------------------------------

def tube_side_dp(
    m_dot_t: float,
    props_t: dict,
    D_i: float,
    L_tube: float,
    N_t: int,
    n_passes: int,
) -> float:
    """
    Tube-side pressure drop (Pa) — Darcy-Weisbach + end-turn losses.
    ΔP = n_passes * (f*L/D + 4*n_passes) * ρu²/2
    Friction factor f from Petukhov (turbulent) or Hagen-Poiseuille (laminar).
    """
    mu = props_t["mu"]
    rho = props_t["rho"]
    N_tubes_per_pass = N_t / n_passes
    m_per_tube = m_dot_t / N_tubes_per_pass
    A_tube = math.pi * D_i ** 2 / 4
    u_t = m_per_tube / (rho * A_tube)
    Re_t = rho * u_t * D_i / mu

    if Re_t > 3_000:
        # Petukhov friction factor
        f = (0.790 * math.log(Re_t) - 1.64) ** (-2)
    else:
        f = 64 / max(Re_t, 1.0)

    # Darcy-Weisbach per pass + 4 velocity heads per return bend
    dp_friction = f * (L_tube / D_i) * (rho * u_t ** 2 / 2)
    dp_nozzle = 2 * (rho * u_t ** 2 / 2)  # nozzle inlet+outlet (simplified)
    return n_passes * dp_friction + dp_nozzle


def shell_side_dp(
    m_dot_s: float,
    props_s: dict,
    geo: dict,
    N_c: float,
) -> float:
    """
    Bell-Delaware shell-side pressure drop (Pa).
    ΔP_shell = ΔP_crossflow * (N_b - 1) * R_b * R_l
             + ΔP_window * N_b
             + ΔP_nozzle

    Following Shah & Sekulic §8.4 / Bell (1981).
    """
    S_m = geo["S_m"]
    S_w = geo["S_w"]
    D_o = geo["tube_od"]
    rho = props_s["rho"]
    mu = props_s["mu"]
    k_f = props_s["k"]
    N_b = geo["N_b"]
    B = geo["B"]
    B_in = geo["B_in"]
    B_out = geo["B_out"]

    G_s = m_dot_s / S_m
    Re_s = G_s * D_o / mu

    # Ideal cross-flow ΔP per baffle compartment (Eu friction factor)
    # Eu (Euler number) from Bell correlation — approximated as:
    # Eu_id = b1 * Re^b2 for tube bank (Zukauskas/Bell coefficients)
    Eu_id = _ideal_eu(Re_s, geo["layout"])
    dp_id_xf = Eu_id * N_c * rho * (G_s / rho) ** 2 / 2  # Pa per cross-flow pass

    # Bypass correction Rb (Bell Eq. 8.44)
    n_ss = geo["n_ss"]
    if S_m > 0:
        r_b = geo["S_b"] / S_m
    else:
        r_b = 0
    C_bp = 3.7 if Re_s < 100 else 4.5  # Bell (1981) Table 9
    if n_ss < N_c / 2:
        Rb = math.exp(-C_bp * r_b * (1 - (2 * n_ss / max(N_c, 1)) ** (1 / 3)))
    else:
        Rb = 1.0
    Rb = max(0.1, min(1.0, Rb))

    # Leakage correction Rl
    S_L = geo["S_tb"] + geo["S_sb"]
    r_lm = S_L / max(S_m, 1e-9)
    Rl = math.exp(-1.33 * (1 + geo["S_sb"] / max(S_L, 1e-9)) * r_lm ** 0.15)
    Rl = max(0.1, min(1.0, Rl))

    dp_crossflow = dp_id_xf * (N_b - 1) * Rb * Rl

    # Window pressure drop (Bell Eq. 8.48)
    G_w = m_dot_s / math.sqrt(S_m * S_w) if S_w > 0 else G_s
    N_t_w = geo["N_t_w"]
    dp_window = N_b * Rl * (2 + 0.6 * N_t_w) * rho * (G_w / rho) ** 2 / 2

    # End-zone pressure drop (inlet+outlet, larger spacing)
    dp_endzone = dp_id_xf * (B_in / B + B_out / B) * Rb
    dp_endzone = max(0.0, dp_endzone)

    return dp_crossflow + dp_window + dp_endzone


def _ideal_eu(Re_s: float, layout: str) -> float:
    """
    Ideal Euler friction number for a tube bank (Bell-Delaware).
    Eu = b1 * Re^b2 — coefficients from HEDH (1983) / Bell Table 9.
    """
    tri_coefs = [
        (1e0,  1e1,  32.0, -1.0),
        (1e1,  1e2,   6.0, -0.5),
        (1e2,  1e3,   0.9, -0.2),
        (1e3,  1e4,   0.40, -0.15),
        (1e4,  1e7,   0.40, -0.15),
    ]
    sq_coefs = [
        (1e0,  1e1,  35.0, -1.0),
        (1e1,  1e2,   7.0, -0.5),
        (1e2,  1e3,   1.1, -0.2),
        (1e3,  1e4,   0.50, -0.15),
        (1e4,  1e7,   0.50, -0.15),
    ]
    coefs = sq_coefs if layout in ("square_90", "rotated_45") else tri_coefs
    Re_s = max(0.1, Re_s)
    for Re_lo, Re_hi, b1, b2 in coefs:
        if Re_s <= Re_hi:
            return b1 * Re_s ** b2
    b1, b2 = coefs[-1][2], coefs[-1][3]
    return b1 * Re_s ** b2


# ---------------------------------------------------------------------------
# 9. TOP-LEVEL DESIGN FUNCTION
# ---------------------------------------------------------------------------

def shell_tube_design(
    duty_W: float,
    t_hot_in: float,
    t_hot_out: float,
    t_cold_in: float,
    t_cold_out: float,
    shell_props: dict,
    tube_props: dict,
    geometry: dict,
) -> dict:
    """
    Shell-and-tube heat exchanger design using the Bell-Delaware method.

    Parameters
    ----------
    duty_W       : heat duty (W)
    t_hot_in     : hot-fluid inlet temperature (°C or K, consistent)
    t_hot_out    : hot-fluid outlet temperature
    t_cold_in    : cold-fluid inlet temperature
    t_cold_out   : cold-fluid outlet temperature
    shell_props  : shell-side fluid properties dict:
                   {'rho': kg/m³, 'mu': Pa·s, 'cp': J/kg·K, 'k': W/m·K}
                   Optional: 'Pr' (computed if missing), 'm_dot': kg/s
    tube_props   : tube-side fluid properties dict (same keys + 'm_dot')
    geometry     : HX geometry dict:
                   {
                     'D_s': m, 'tube_od': m, 'tube_id': m, 'pitch': m,
                     'layout': str, 'L_tube': m, 'N_t': int, 'n_passes': int,
                     'N_b': int, 'B': m, 'B_in': m (opt), 'B_out': m (opt),
                     'baffle_cut': fraction (default 0.25),
                     'k_wall': W/m·K, 'R_foul_t': m²K/W, 'R_foul_s': m²K/W,
                     'D_tb': m (opt), 'D_sb': m (opt), 'n_ss': int (opt)
                   }

    Returns
    -------
    dict with keys:
        U_W_m2K       : overall HTC (W/m²·K)
        A_actual_m2   : actual heat-transfer area (m²)
        A_req_m2      : required area for duty at LMTD (m²)
        overdesign    : A_actual/A_req - 1 (fraction)
        N_tubes       : tube count
        N_baffles     : baffle count
        h_t_W_m2K     : tube-side film HTC
        h_s_W_m2K     : shell-side film HTC
        Re_t          : tube-side Reynolds
        Re_s          : shell-side Reynolds
        LMTD_K        : log-mean temperature difference (K) [F=1 counter-flow]
        dP_tube_Pa    : tube-side pressure drop (Pa)
        dP_shell_Pa   : shell-side pressure drop (Pa)
        factors       : Bell-Delaware Jc/Jl/Jb/Jr/Js
        ok            : True
    """
    # --- Derived fluid properties ---
    for p in (shell_props, tube_props):
        if "Pr" not in p:
            p["Pr"] = p["cp"] * p["mu"] / p["k"]

    # --- LMTD (counter-flow; F-factor = 1.0 as first pass) ---
    dT1 = t_hot_in - t_cold_out
    dT2 = t_hot_out - t_cold_in
    if abs(dT1 - dT2) < 1e-6:
        LMTD = dT1
    else:
        LMTD = (dT1 - dT2) / math.log(dT1 / dT2)

    # --- Geometry setup ---
    geom = dict(geometry)
    D_o = geom["tube_od"]
    D_i = geom["tube_id"]
    L_tube = geom["L_tube"]
    N_t = geom["N_t"]
    n_passes = geom.get("n_passes", 1)
    N_b = geom["N_b"]
    k_wall = geom.get("k_wall", 50.0)  # carbon steel default
    R_foul_t = geom.get("R_foul_t", 0.0002)
    R_foul_s = geom.get("R_foul_s", 0.0002)

    geo = _shell_geometry(geom)

    # Number of tube rows in one cross-flow window (Bell eq.)
    D_s = geom["D_s"]
    pitch = geom["pitch"]
    l_c = geo["l_c"]
    # N_c = number of tube rows crossed = (D_s - 2*l_c) / pitch (approx)
    N_c = max(1.0, (D_s - 2 * l_c) / pitch)

    # --- Mass flow rates ---
    # If not provided, infer from duty and cp
    m_dot_s = shell_props.get("m_dot")
    if m_dot_s is None:
        dT_shell = abs(t_hot_in - t_hot_out)
        m_dot_s = duty_W / (shell_props["cp"] * dT_shell) if dT_shell > 0 else 1.0

    m_dot_t = tube_props.get("m_dot")
    if m_dot_t is None:
        dT_tube = abs(t_cold_out - t_cold_in)
        m_dot_t = duty_W / (tube_props["cp"] * dT_tube) if dT_tube > 0 else 1.0

    # --- Heat-transfer coefficients ---
    h_s, Re_s, factors = shell_side_htc(m_dot_s, shell_props, geo, N_c)
    h_t, Re_t = tube_side_htc(m_dot_t, tube_props, D_i, N_t, n_passes)

    # --- Overall U ---
    U = overall_U(h_t, h_s, D_i, D_o, k_wall, R_foul_t, R_foul_s)

    # --- Areas ---
    A_actual = N_t * math.pi * D_o * L_tube
    A_req = duty_W / (U * LMTD) if (U * LMTD) > 0 else float("inf")
    overdesign = A_actual / A_req - 1.0 if A_req > 0 else 0.0

    # --- Pressure drops ---
    dP_tube = tube_side_dp(m_dot_t, tube_props, D_i, L_tube, N_t, n_passes)
    dP_shell = shell_side_dp(m_dot_s, shell_props, geo, N_c)

    return {
        "ok": True,
        "U_W_m2K": round(U, 2),
        "A_actual_m2": round(A_actual, 3),
        "A_req_m2": round(A_req, 3),
        "overdesign": round(overdesign, 4),
        "N_tubes": N_t,
        "N_baffles": N_b,
        "h_t_W_m2K": round(h_t, 2),
        "h_s_W_m2K": round(h_s, 2),
        "Re_t": round(Re_t, 1),
        "Re_s": round(Re_s, 1),
        "LMTD_K": round(LMTD, 3),
        "dP_tube_Pa": round(dP_tube, 1),
        "dP_shell_Pa": round(dP_shell, 1),
        "factors": factors,
    }
