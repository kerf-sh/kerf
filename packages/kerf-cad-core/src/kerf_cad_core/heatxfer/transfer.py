"""
kerf_cad_core.heatxfer.transfer — pure-Python heat-transfer engineering formulas.

Implements the following public functions:

  CONDUCTION
  ----------
  composite_wall(layers, T_hot, T_cold)
      1D steady-state conduction through a plane composite wall (series
      resistances), optionally including contact resistances between layers.

  cylindrical_shell(r_inner, r_outer, k, T_inner, T_outer, L)
      1D radial conduction through a single cylindrical shell.

  spherical_shell(r_inner, r_outer, k, T_inner, T_outer)
      1D radial conduction through a single spherical shell.

  CONVECTION (Nusselt correlations)
  ----------------------------------
  nusselt_flat_plate(Re_L, Pr, *, regime)
      Flat-plate forced convection:
        laminar  — Nu = 0.664 Re^0.5  Pr^(1/3)  (Incropera 7.23)
        turbulent — Nu = 0.037 Re^(4/5) Pr^(1/3)  (Incropera 7.36)
        mixed     — Nu = (0.037 Re^(4/5) - 871) Pr^(1/3)  (Incropera 7.38)

  nusselt_pipe_dittus_boelter(Re_D, Pr, *, heating)
      Dittus-Boelter for turbulent internal pipe flow (Re > 10 000, 0.6<Pr<160).
        heating (fluid heated): Nu = 0.023 Re^0.8 Pr^0.4
        cooling (fluid cooled): Nu = 0.023 Re^0.8 Pr^0.3

  nusselt_pipe_laminar(Re_D, Pr, L_D)
      Laminar internal pipe flow (Re < 2300).
        Thermally developing: Sieder-Tate/Hausen combined entry Nu
        (Incropera 8.58):  Nu = 3.66 + (0.065*(D/L)*Re*Pr) /
                                 (1 + 0.04*((D/L)*Re*Pr)^(2/3))

  nusselt_cylinder_churchill_bernstein(Re_D, Pr)
      External cross-flow over an infinite cylinder:
      Churchill & Bernstein (1977) correlation (Incropera 7.54).

  nusselt_natural_vertical_plate(Ra_L, Pr, *, regime)
      Natural convection on a vertical isothermal plate:
      Churchill & Chu (1975) correlations (Incropera 9.26 / 9.27).
        'laminar'  : entire range low-Ra form
        'all'      : composite form valid for all Ra

  RADIATION
  ---------
  radiation_two_surface(T1, T2, eps1, eps2, A1, A2, F12)
      Net radiation exchange between two gray, diffuse surfaces separated
      by a non-participating medium.  Uses the electrical analogy with
      surface and space resistances (Incropera §13-3).

  EXTENDED SURFACES (fins)
  ------------------------
  fin_efficiency_straight(L, t, k, h, *, tip)
      Straight rectangular fin efficiency η_f and effectiveness ε_f.
        tip = 'adiabatic'  (default) — insulated tip approximation
        tip = 'convective' — convective tip corrected length L_c = L + t/2

  fin_efficiency_pin(L, D, k, h)
      Cylindrical pin fin efficiency η_f and effectiveness ε_f.
      Adiabatic-tip approximation with L_c = L + D/4.

  fin_array_resistance(N, eta_f, A_fin, A_base, h, A_total)
      Overall thermal resistance of a fin array (Incropera 3.108).

  HEAT EXCHANGERS
  ---------------
  lmtd_heat_exchanger(T_h_in, T_h_out, T_c_in, T_c_out, U, A, *, flow)
      LMTD method:  Q = U A ΔT_lm F
        flow = 'counter'  (default), 'parallel', 'crossflow_unmixed'
      Returns Q_W, LMTD_K, F correction factor.

  effectiveness_ntu(C_min, C_max, NTU, *, flow)
      ε-NTU method for given NTU and heat-capacity ratio C_r = C_min/C_max.
        flow = 'counter', 'parallel', 'crossflow_unmixed' (Incropera 11.29–31)
      Returns effectiveness ε, q_max (W), Q (W).

  TRANSIENT
  ---------
  lumped_capacitance(T_i, T_inf, h, A_s, rho, V, c_p, t, *, Lc, k)
      Transient lumped-capacitance model (Incropera §5.3).
      Emits a warnings.warn if Bi = h*Lc/k > 0.1 (model invalid).
      Returns T(t), τ (time constant), Bi.

All functions return a plain dict:
    success → {"ok": True, ...computed fields...}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Invalid-regime warnings use the standard library
``warnings`` module (warn-only, never raise).

Units
-----
Unless otherwise stated:
  lengths     — metres (m)
  temperatures — Kelvin (K)  [Celsius input accepted where noted]
  thermal conductivity — W/(m·K)
  heat transfer coeff — W/(m²·K)
  areas       — m²
  heat flux/rate — W
  emissivity  — dimensionless [0, 1]
  time        — seconds (s)

References
----------
Incropera, F.P. et al., "Fundamentals of Heat and Mass Transfer", 7th ed.,
  Wiley, 2011.
Churchill, S.W. & Bernstein, M. (1977). AIChE J., 23(1), 10-16.
Churchill, S.W. & Chu, H.H.S. (1975). Int. J. Heat Mass Transfer, 18, 1323-1329.

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive

# Stefan-Boltzmann constant (W m⁻² K⁻⁴)
_SIGMA = 5.670374419e-8


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_range(name: str, value: Any, lo: float, hi: float) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if not (lo <= v <= hi):
        return f"{name} must be in [{lo}, {hi}], got {v}"
    return None


def composite_wall(
    layers: list[dict],
    T_hot: float,
    T_cold: float,
) -> dict:
    """
    1D steady-state conduction through a plane composite wall.

    Parameters
    ----------
    layers : list of dict
        Ordered from hot side to cold side.  Each dict must contain:
          "k"   : thermal conductivity (W/m·K)  — material layer
          "t"   : thickness (m)
          OR
          "R_contact" : contact resistance (m²·K/W)  — contact layer (no k/t needed)
        Area A is assumed 1 m² unless specified as "A" key in each layer.
    T_hot : float
        Hot-side surface temperature (K).
    T_cold : float
        Cold-side surface temperature (K).

    Returns
    -------
    dict
        ok             : True
        Q_W            : heat flux / heat transfer rate (W for A=1 m²)
        R_total        : total thermal resistance (K/W)
        layer_resistances: list of per-layer R values (K/W)
        T_interfaces   : temperatures at each inter-layer interface (K)
        T_hot_K        : hot side temperature (K)
        T_cold_K       : cold side temperature (K)
    """
    err = _guard_nonneg("T_hot", T_hot)
    if err:
        return _err(err)
    err = _guard_nonneg("T_cold", T_cold)
    if err:
        return _err(err)

    if not isinstance(layers, list) or len(layers) == 0:
        return _err("layers must be a non-empty list")

    R_list: list[float] = []
    for i, layer in enumerate(layers):
        if not isinstance(layer, dict):
            return _err(f"layers[{i}] must be a dict")
        if "R_contact" in layer:
            rc = layer["R_contact"]
            A = float(layer.get("A", 1.0))
            if A <= 0:
                return _err(f"layers[{i}].A must be > 0")
            R_list.append(float(rc) / A)
        elif "k" in layer and "t" in layer:
            k = float(layer["k"])
            t = float(layer["t"])
            A = float(layer.get("A", 1.0))
            if k <= 0:
                return _err(f"layers[{i}].k must be > 0")
            if t <= 0:
                return _err(f"layers[{i}].t must be > 0")
            if A <= 0:
                return _err(f"layers[{i}].A must be > 0")
            R_list.append(t / (k * A))
        else:
            return _err(
                f"layers[{i}] must contain either 'R_contact' "
                "or both 'k' and 't'"
            )

    R_total = sum(R_list)
    if R_total <= 0:
        return _err("total wall resistance is zero or negative")

    Q = (float(T_hot) - float(T_cold)) / R_total

    # Compute interface temperatures
    T_interfaces: list[float] = []
    T_running = float(T_hot)
    for R_i in R_list[:-1]:
        T_running -= Q * R_i
        T_interfaces.append(T_running)

    return {
        "ok": True,
        "Q_W": Q,
        "R_total": R_total,
        "layer_resistances": R_list,
        "T_interfaces": T_interfaces,
        "T_hot_K": float(T_hot),
        "T_cold_K": float(T_cold),
    }


# ---------------------------------------------------------------------------
# CONDUCTION — Cylindrical shell
# ---------------------------------------------------------------------------

def cylindrical_shell(
    r_inner: float,
    r_outer: float,
    k: float,
    T_inner: float,
    T_outer: float,
    L: float = 1.0,
) -> dict:
    """
    1D radial conduction through a cylindrical shell (per unit length or total).

    Incropera eq. 3.27:  Q = 2π k L (T_i - T_o) / ln(r_o / r_i)

    Parameters
    ----------
    r_inner, r_outer : float  (m, must have r_inner < r_outer)
    k : float  thermal conductivity (W/m·K)
    T_inner, T_outer : float  surface temperatures (K)
    L : float  length of cylinder (m), default 1 m

    Returns
    -------
    dict
        ok      : True
        Q_W     : total heat transfer rate (W)
        q_per_m : heat transfer per unit length (W/m)
        R_cond  : conduction resistance (K/W)
        ln_ratio: ln(r_o/r_i)
    """
    for name, val in [("r_inner", r_inner), ("r_outer", r_outer),
                      ("k", k), ("L", L)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    if float(r_outer) <= float(r_inner):
        return _err(f"r_outer ({r_outer}) must be > r_inner ({r_inner})")

    ri = float(r_inner)
    ro = float(r_outer)
    k_val = float(k)
    length = float(L)
    ln_r = math.log(ro / ri)

    R_cond = ln_r / (2.0 * math.pi * k_val * length)
    Q = (float(T_inner) - float(T_outer)) / R_cond
    q_per_m = Q / length

    return {
        "ok": True,
        "Q_W": Q,
        "q_per_m": q_per_m,
        "R_cond": R_cond,
        "ln_ratio": ln_r,
        "r_inner_m": ri,
        "r_outer_m": ro,
        "k_WmK": k_val,
        "L_m": length,
    }


# ---------------------------------------------------------------------------
# CONDUCTION — Spherical shell
# ---------------------------------------------------------------------------

def spherical_shell(
    r_inner: float,
    r_outer: float,
    k: float,
    T_inner: float,
    T_outer: float,
) -> dict:
    """
    1D radial conduction through a spherical shell.

    Incropera eq. 3.35:
        Q = 4π k r_i r_o (T_i - T_o) / (r_o - r_i)
        R = (r_o - r_i) / (4π k r_i r_o)

    Returns
    -------
    dict
        ok     : True
        Q_W    : heat transfer rate (W)
        R_cond : conduction resistance (K/W)
    """
    for name, val in [("r_inner", r_inner), ("r_outer", r_outer), ("k", k)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    if float(r_outer) <= float(r_inner):
        return _err(f"r_outer ({r_outer}) must be > r_inner ({r_inner})")

    ri = float(r_inner)
    ro = float(r_outer)
    k_val = float(k)

    R_cond = (ro - ri) / (4.0 * math.pi * k_val * ri * ro)
    Q = (float(T_inner) - float(T_outer)) / R_cond

    return {
        "ok": True,
        "Q_W": Q,
        "R_cond": R_cond,
        "r_inner_m": ri,
        "r_outer_m": ro,
        "k_WmK": k_val,
    }


# ---------------------------------------------------------------------------
# CONVECTION — Flat-plate Nusselt correlations
# ---------------------------------------------------------------------------

def nusselt_flat_plate(
    Re_L: float,
    Pr: float,
    *,
    regime: str = "auto",
) -> dict:
    """
    Average Nusselt number for forced convection over a flat plate.

    Regimes
    -------
    'laminar'   Re < 5e5:  Nu = 0.664 Re^0.5 Pr^(1/3)     (Incropera 7.23)
    'turbulent' Re > 5e5:  Nu = 0.037 Re^(4/5) Pr^(1/3)   (Incropera 7.36)
    'mixed'     full plate: Nu = (0.037 Re^(4/5) - 871) Pr^(1/3)  (Incropera 7.38)
    'auto'      selects 'laminar' if Re <= 5e5 else 'mixed'

    Validity: 0.6 <= Pr <= 60; issued as warning only (never raises).

    Parameters
    ----------
    Re_L : float  Reynolds number based on plate length L (dimensionless)
    Pr   : float  Prandtl number (dimensionless)
    regime : str  one of 'laminar', 'turbulent', 'mixed', 'auto'

    Returns
    -------
    dict
        ok      : True
        Nu      : average Nusselt number
        regime  : regime string used
        Re_L    : Reynolds number
        Pr      : Prandtl number
    """
    err = _guard_positive("Re_L", Re_L)
    if err:
        return _err(err)
    err = _guard_positive("Pr", Pr)
    if err:
        return _err(err)

    if not (0.6 <= float(Pr) <= 60):
        warnings.warn(
            f"nusselt_flat_plate: Pr={Pr} outside validity range [0.6, 60]; "
            "result may be inaccurate.",
            stacklevel=2,
        )

    Re = float(Re_L)
    Pr_val = float(Pr)

    reg = str(regime).strip().lower()
    if reg == "auto":
        reg = "laminar" if Re <= 5e5 else "mixed"

    if reg == "laminar":
        Nu = 0.664 * Re ** 0.5 * Pr_val ** (1.0 / 3.0)
    elif reg == "turbulent":
        Nu = 0.037 * Re ** (4.0 / 5.0) * Pr_val ** (1.0 / 3.0)
    elif reg == "mixed":
        Nu = (0.037 * Re ** (4.0 / 5.0) - 871.0) * Pr_val ** (1.0 / 3.0)
    else:
        return _err(
            f"Unknown regime {regime!r}. Supported: 'laminar', 'turbulent', 'mixed', 'auto'."
        )

    return {
        "ok": True,
        "Nu": Nu,
        "regime": reg,
        "Re_L": Re,
        "Pr": Pr_val,
    }


# ---------------------------------------------------------------------------
# CONVECTION — Dittus-Boelter (turbulent pipe flow)
# ---------------------------------------------------------------------------

def nusselt_pipe_dittus_boelter(
    Re_D: float,
    Pr: float,
    *,
    heating: bool = True,
) -> dict:
    """
    Dittus-Boelter correlation for fully developed turbulent pipe flow.

    Nu = 0.023 Re^0.8 Pr^n
      n = 0.4 (fluid heated, T_s > T_m)
      n = 0.3 (fluid cooled, T_s < T_m)

    Validity: Re > 10 000, 0.6 < Pr < 160, L/D > 10.
    A warning is issued if Re <= 10 000.

    References: Incropera 8.60

    Parameters
    ----------
    Re_D    : float  Reynolds number based on pipe diameter
    Pr      : float  Prandtl number
    heating : bool   True = fluid is heated (n=0.4); False = cooled (n=0.3)

    Returns
    -------
    dict
        ok      : True
        Nu      : Nusselt number
        n       : exponent used
        Re_D    : Reynolds number
        Pr      : Prandtl number
    """
    err = _guard_positive("Re_D", Re_D)
    if err:
        return _err(err)
    err = _guard_positive("Pr", Pr)
    if err:
        return _err(err)

    Re = float(Re_D)
    Pr_val = float(Pr)

    if Re <= 10_000:
        warnings.warn(
            f"nusselt_pipe_dittus_boelter: Re_D={Re} <= 10 000; "
            "Dittus-Boelter is for turbulent flow (Re > 10 000). "
            "Use nusselt_pipe_laminar for laminar flow.",
            stacklevel=2,
        )

    if not (0.6 < Pr_val < 160):
        warnings.warn(
            f"nusselt_pipe_dittus_boelter: Pr={Pr_val} outside validity "
            "range (0.6, 160).",
            stacklevel=2,
        )

    n = 0.4 if heating else 0.3
    Nu = 0.023 * Re ** 0.8 * Pr_val ** n

    return {
        "ok": True,
        "Nu": Nu,
        "n": n,
        "heating": heating,
        "Re_D": Re,
        "Pr": Pr_val,
    }


# ---------------------------------------------------------------------------
# CONVECTION — Laminar pipe flow (Hausen / Sieder-Tate entry length)
# ---------------------------------------------------------------------------

def nusselt_pipe_laminar(
    Re_D: float,
    Pr: float,
    L_D: float,
) -> dict:
    """
    Average Nusselt number for laminar internal pipe flow with combined
    hydrodynamic and thermal entry length effects.

    Hausen correlation (Incropera 8.58):
        Nu = 3.66 + 0.065 * Gz / (1 + 0.04 * Gz^(2/3))
    where Gz = (D/L) * Re * Pr  (Graetz number)

    Validity: Re_D < 2300.  Warning issued if Re_D >= 2300.

    Parameters
    ----------
    Re_D : float  Reynolds number (based on diameter)
    Pr   : float  Prandtl number
    L_D  : float  L/D ratio (length / diameter).  Must be > 0.

    Returns
    -------
    dict
        ok   : True
        Nu   : average Nusselt number
        Gz   : Graetz number
        Re_D : Reynolds number
        Pr   : Prandtl number
        L_D  : L/D ratio used
    """
    err = _guard_positive("Re_D", Re_D)
    if err:
        return _err(err)
    err = _guard_positive("Pr", Pr)
    if err:
        return _err(err)
    err = _guard_positive("L_D", L_D)
    if err:
        return _err(err)

    Re = float(Re_D)
    Pr_val = float(Pr)
    LD = float(L_D)

    if Re >= 2300:
        warnings.warn(
            f"nusselt_pipe_laminar: Re_D={Re} >= 2300; "
            "Hausen correlation is for laminar flow (Re < 2300). "
            "Use nusselt_pipe_dittus_boelter for turbulent flow.",
            stacklevel=2,
        )

    Gz = (1.0 / LD) * Re * Pr_val  # D/L * Re * Pr
    Nu = 3.66 + 0.065 * Gz / (1.0 + 0.04 * Gz ** (2.0 / 3.0))

    return {
        "ok": True,
        "Nu": Nu,
        "Gz": Gz,
        "Re_D": Re,
        "Pr": Pr_val,
        "L_D": LD,
    }


# ---------------------------------------------------------------------------
# CONVECTION — External cylinder (Churchill-Bernstein)
# ---------------------------------------------------------------------------

def nusselt_cylinder_churchill_bernstein(
    Re_D: float,
    Pr: float,
) -> dict:
    """
    Average Nusselt number for external cross-flow over a long cylinder.

    Churchill & Bernstein (1977) correlation (Incropera 7.54):

        Nu = 0.3 + [0.62 Re^(1/2) Pr^(1/3)] /
                   [1 + (0.4/Pr)^(2/3)]^(1/4) ×
                   [1 + (Re/282000)^(5/8)]^(4/5)

    Valid for Re·Pr > 0.2.  Warning issued if Re*Pr < 0.2.

    Parameters
    ----------
    Re_D : float  Reynolds number based on cylinder diameter
    Pr   : float  Prandtl number

    Returns
    -------
    dict
        ok   : True
        Nu   : average Nusselt number
        Re_D : Reynolds number
        Pr   : Prandtl number
    """
    err = _guard_positive("Re_D", Re_D)
    if err:
        return _err(err)
    err = _guard_positive("Pr", Pr)
    if err:
        return _err(err)

    Re = float(Re_D)
    Pr_val = float(Pr)

    if Re * Pr_val < 0.2:
        warnings.warn(
            f"nusselt_cylinder_churchill_bernstein: Re*Pr={Re*Pr_val:.4g} < 0.2; "
            "Churchill-Bernstein correlation may be inaccurate.",
            stacklevel=2,
        )

    term1 = 0.62 * Re ** 0.5 * Pr_val ** (1.0 / 3.0)
    denom = (1.0 + (0.4 / Pr_val) ** (2.0 / 3.0)) ** 0.25
    bracket = 1.0 + (Re / 282_000.0) ** (5.0 / 8.0)
    Nu = 0.3 + (term1 / denom) * bracket ** (4.0 / 5.0)

    return {
        "ok": True,
        "Nu": Nu,
        "Re_D": Re,
        "Pr": Pr_val,
    }


# ---------------------------------------------------------------------------
# CONVECTION — Natural convection, vertical plate (Churchill-Chu)
# ---------------------------------------------------------------------------

def nusselt_natural_vertical_plate(
    Ra_L: float,
    Pr: float,
    *,
    regime: str = "all",
) -> dict:
    """
    Average Nusselt number for natural convection on a vertical isothermal plate.

    Churchill & Chu (1975) correlations (Incropera §9.6):

    'laminar' (Ra_L <= 1e9, Incropera 9.26):
        Nu = 0.68 + 0.670 Ra^(1/4) / [1 + (0.492/Pr)^(9/16)]^(4/9)

    'all' — composite valid for all Ra (Incropera 9.27):
        Nu^(1/2) = 0.825 + 0.387 Ra^(1/6) / [1 + (0.492/Pr)^(9/16)]^(8/27)

    Parameters
    ----------
    Ra_L : float  Rayleigh number based on plate height L (= Gr * Pr)
    Pr   : float  Prandtl number
    regime : str  'laminar' or 'all' (default 'all')

    Returns
    -------
    dict
        ok     : True
        Nu     : average Nusselt number
        regime : regime string used
        Ra_L   : Rayleigh number
        Pr     : Prandtl number
    """
    err = _guard_positive("Ra_L", Ra_L)
    if err:
        return _err(err)
    err = _guard_positive("Pr", Pr)
    if err:
        return _err(err)

    Ra = float(Ra_L)
    Pr_val = float(Pr)

    reg = str(regime).strip().lower()
    psi = (1.0 + (0.492 / Pr_val) ** (9.0 / 16.0))

    if reg == "laminar":
        if Ra > 1e9:
            warnings.warn(
                f"nusselt_natural_vertical_plate: Ra_L={Ra:.2e} > 1e9; "
                "laminar correlation is inaccurate at this Ra. Use regime='all'.",
                stacklevel=2,
            )
        Nu = 0.68 + 0.670 * Ra ** 0.25 / psi ** (4.0 / 9.0)
    elif reg == "all":
        Nu_sqrt = 0.825 + 0.387 * Ra ** (1.0 / 6.0) / psi ** (8.0 / 27.0)
        Nu = Nu_sqrt ** 2
    else:
        return _err(
            f"Unknown regime {regime!r}. Supported: 'laminar', 'all'."
        )

    return {
        "ok": True,
        "Nu": Nu,
        "regime": reg,
        "Ra_L": Ra,
        "Pr": Pr_val,
    }


# ---------------------------------------------------------------------------
# RADIATION — Two-surface enclosure
# ---------------------------------------------------------------------------

def radiation_two_surface(
    T1: float,
    T2: float,
    eps1: float,
    eps2: float,
    A1: float,
    A2: float,
    F12: float,
) -> dict:
    """
    Net radiation heat transfer between two gray, diffuse surfaces.

    Electrical analogy (Incropera §13-3):
        Q_12 = (E_b1 - E_b2) / (R_surf1 + R_space + R_surf2)

    where:
        E_b = σ T^4  (blackbody emissive power, W/m²)
        R_surf1 = (1 - ε1) / (ε1 A1)
        R_space = 1 / (A1 F12)
        R_surf2 = (1 - ε2) / (ε2 A2)

    Special case: blackbody surfaces (ε=1) → R_surf = 0.

    Parameters
    ----------
    T1, T2 : float  surface temperatures (K). Must be > 0.
    eps1, eps2 : float  surface emissivities [0, 1]. Must be in (0, 1].
    A1, A2 : float  surface areas (m²). Must be > 0.
    F12 : float  view factor from surface 1 to surface 2 [0, 1].

    Returns
    -------
    dict
        ok        : True
        Q_12_W    : net heat transfer from surface 1 to surface 2 (W)
                    positive → net heat from 1 to 2
        R_total   : total resistance (K/W via electrical analogy in W^-1)
        R_surf1   : surface resistance for surface 1
        R_space   : space (geometric) resistance
        R_surf2   : surface resistance for surface 2
        Eb1_Wm2   : blackbody emissive power of surface 1 (W/m²)
        Eb2_Wm2   : blackbody emissive power of surface 2 (W/m²)
    """
    for name, val in [("T1", T1), ("T2", T2)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)
    for name, val in [("A1", A1), ("A2", A2)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)
    for name, val in [("eps1", eps1), ("eps2", eps2)]:
        err = _guard_range(name, val, 0.0, 1.0)
        if err:
            return _err(err)
        if float(val) == 0.0:
            return _err(f"{name} must be > 0 (perfect reflector not supported)")
    err = _guard_range("F12", F12, 0.0, 1.0)
    if err:
        return _err(err)

    T1_val = float(T1)
    T2_val = float(T2)
    e1 = float(eps1)
    e2 = float(eps2)
    a1 = float(A1)
    a2 = float(A2)
    f12 = float(F12)

    Eb1 = _SIGMA * T1_val ** 4
    Eb2 = _SIGMA * T2_val ** 4

    R_surf1 = (1.0 - e1) / (e1 * a1)
    if f12 == 0.0:
        # No view factor → no exchange
        return {
            "ok": True,
            "Q_12_W": 0.0,
            "R_total": float("inf"),
            "R_surf1": R_surf1,
            "R_space": float("inf"),
            "R_surf2": (1.0 - e2) / (e2 * a2),
            "Eb1_Wm2": Eb1,
            "Eb2_Wm2": Eb2,
        }

    R_space = 1.0 / (a1 * f12)
    R_surf2 = (1.0 - e2) / (e2 * a2)
    R_total = R_surf1 + R_space + R_surf2

    Q_12 = (Eb1 - Eb2) / R_total

    return {
        "ok": True,
        "Q_12_W": Q_12,
        "R_total": R_total,
        "R_surf1": R_surf1,
        "R_space": R_space,
        "R_surf2": R_surf2,
        "Eb1_Wm2": Eb1,
        "Eb2_Wm2": Eb2,
    }


# ---------------------------------------------------------------------------
# EXTENDED SURFACES — Straight rectangular fin
# ---------------------------------------------------------------------------

def fin_efficiency_straight(
    L: float,
    t: float,
    k: float,
    h: float,
    *,
    tip: str = "adiabatic",
) -> dict:
    """
    Efficiency and effectiveness of a straight rectangular fin.

    Corrected-length adiabatic-tip approximation:
        L_c = L + t/2  (convective tip, Incropera 3.80)
        L_c = L        (adiabatic tip)

    mL_c = sqrt(2h / (k t)) × L_c

    η_f = tanh(mL_c) / (mL_c)            (Incropera 3.82)

    ε_f = η_f × (2 L_c / t) × ... simplified as:
          η_f × A_fin / A_base
          where A_fin = 2 L_c  (per unit depth, per side)
                A_base = t     (per unit depth, one side of base)
          Note: ε_f = tanh(mL_c) / (mL_c) × 2Lc / t

    Parameters
    ----------
    L  : float  fin length / height (m)
    t  : float  fin thickness (m)
    k  : float  fin thermal conductivity (W/m·K)
    h  : float  convective heat transfer coefficient (W/m²·K)
    tip: str    'adiabatic' (default) or 'convective'

    Returns
    -------
    dict
        ok       : True
        eta_f    : fin efficiency (dimensionless, in [0,1])
        eps_f    : fin effectiveness (dimensionless)
        mL_c     : fin parameter mL_c
        L_c      : corrected length (m)
        m        : fin parameter m = sqrt(2h/kt) (1/m)
    """
    for name, val in [("L", L), ("t", t), ("k", k), ("h", h)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    tip_s = str(tip).strip().lower()
    if tip_s not in ("adiabatic", "convective"):
        return _err(f"Unknown tip {tip!r}. Supported: 'adiabatic', 'convective'.")

    L_val = float(L)
    t_val = float(t)
    k_val = float(k)
    h_val = float(h)

    L_c = L_val + (t_val / 2.0) if tip_s == "convective" else L_val
    m = math.sqrt(2.0 * h_val / (k_val * t_val))
    mLc = m * L_c

    if mLc == 0.0:
        eta_f = 1.0
    else:
        eta_f = math.tanh(mLc) / mLc

    # Effectiveness: ratio of fin heat transfer to base heat transfer without fin
    # ε_f = q_fin / (h A_base ΔT) = η_f × A_fin / A_base
    # Per unit depth: A_fin_1D = 2*L_c, A_base_1D = t
    eps_f = eta_f * (2.0 * L_c / t_val)

    return {
        "ok": True,
        "eta_f": eta_f,
        "eps_f": eps_f,
        "mL_c": mLc,
        "L_c": L_c,
        "m": m,
        "tip": tip_s,
    }


# ---------------------------------------------------------------------------
# EXTENDED SURFACES — Cylindrical pin fin
# ---------------------------------------------------------------------------

def fin_efficiency_pin(
    L: float,
    D: float,
    k: float,
    h: float,
) -> dict:
    """
    Efficiency and effectiveness of a cylindrical pin fin.

    Adiabatic-tip corrected length: L_c = L + D/4

    m = sqrt(4h / (k D))

    η_f = tanh(mL_c) / (mL_c)

    ε_f = η_f × A_fin / A_base
        A_fin  = π D L_c  (lateral surface of corrected pin)
        A_base = π D² / 4 (cross-section at base)
        → ε_f = η_f × 4 L_c / D

    Parameters
    ----------
    L : float  pin fin length (m)
    D : float  pin fin diameter (m)
    k : float  thermal conductivity (W/m·K)
    h : float  convective heat transfer coefficient (W/m²·K)

    Returns
    -------
    dict
        ok    : True
        eta_f : fin efficiency
        eps_f : fin effectiveness
        mL_c  : fin parameter
        L_c   : corrected length (m)
        m     : m parameter (1/m)
    """
    for name, val in [("L", L), ("D", D), ("k", k), ("h", h)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    L_val = float(L)
    D_val = float(D)
    k_val = float(k)
    h_val = float(h)

    L_c = L_val + D_val / 4.0
    m = math.sqrt(4.0 * h_val / (k_val * D_val))
    mLc = m * L_c

    if mLc == 0.0:
        eta_f = 1.0
    else:
        eta_f = math.tanh(mLc) / mLc

    # Effectiveness
    eps_f = eta_f * (4.0 * L_c / D_val)

    return {
        "ok": True,
        "eta_f": eta_f,
        "eps_f": eps_f,
        "mL_c": mLc,
        "L_c": L_c,
        "m": m,
    }


# ---------------------------------------------------------------------------
# EXTENDED SURFACES — Fin array thermal resistance
# ---------------------------------------------------------------------------

def fin_array_resistance(
    N: int,
    eta_f: float,
    A_fin: float,
    A_base: float,
    h: float,
    A_total: float,
) -> dict:
    """
    Overall thermal resistance of a fin array.

    Incropera eq. 3.108:

        η_overall = 1 - N A_fin / A_total × (1 - η_f)

        R_array = 1 / (η_overall × h × A_total)

    Parameters
    ----------
    N       : int    number of fins
    eta_f   : float  individual fin efficiency (dimensionless)
    A_fin   : float  total surface area of one fin (m²)
    A_base  : float  base area between fins per fin pitch (m²)
    h       : float  convective heat transfer coefficient (W/m²·K)
    A_total : float  total heat transfer area = N*A_fin + A_base_unfinned (m²)

    Returns
    -------
    dict
        ok         : True
        R_array    : thermal resistance of fin array (K/W)
        eta_overall: overall surface efficiency
        N          : number of fins
        h          : h used
        A_total    : total area used
    """
    if not isinstance(N, (int, float)) or float(N) < 1:
        return _err("N must be a positive integer >= 1")
    err = _guard_range("eta_f", eta_f, 0.0, 1.0)
    if err:
        return _err(err)
    for name, val in [("A_fin", A_fin), ("A_base", A_base),
                      ("h", h), ("A_total", A_total)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    N_int = int(N)
    A_f = float(A_fin)
    h_val = float(h)
    A_tot = float(A_total)
    eta = float(eta_f)

    eta_overall = 1.0 - (N_int * A_f / A_tot) * (1.0 - eta)
    if eta_overall <= 0:
        return _err("eta_overall <= 0: check inputs (N, A_fin, A_total inconsistent)")

    R_array = 1.0 / (eta_overall * h_val * A_tot)

    return {
        "ok": True,
        "R_array": R_array,
        "eta_overall": eta_overall,
        "N": N_int,
        "h": h_val,
        "A_total": A_tot,
    }


# ---------------------------------------------------------------------------
# HEAT EXCHANGER — LMTD method
# ---------------------------------------------------------------------------

def lmtd_heat_exchanger(
    T_h_in: float,
    T_h_out: float,
    T_c_in: float,
    T_c_out: float,
    U: float,
    A: float,
    *,
    flow: str = "counter",
) -> dict:
    """
    Heat exchanger analysis via the Log Mean Temperature Difference (LMTD) method.

    Q = U A F ΔT_lm

    ΔT_lm for counter-flow:
        ΔT1 = T_h_in  - T_c_out
        ΔT2 = T_h_out - T_c_in

    ΔT_lm for parallel-flow:
        ΔT1 = T_h_in  - T_c_in
        ΔT2 = T_h_out - T_c_out

    For cross-flow (single pass, both fluids unmixed), F is calculated from
    the standard F-factor chart equations (Incropera 11.15) using P, R parameters.
    Counter and parallel flow use F = 1.

    Parameters
    ----------
    T_h_in, T_h_out : float  hot-side inlet/outlet temperatures (K)
    T_c_in, T_c_out : float  cold-side inlet/outlet temperatures (K)
    U : float  overall heat-transfer coefficient (W/m²·K)
    A : float  heat exchanger area (m²)
    flow : str  'counter' (default), 'parallel', 'crossflow_unmixed'

    Returns
    -------
    dict
        ok       : True
        Q_W      : heat transfer rate (W)
        LMTD_K   : log mean temperature difference (K)
        F        : correction factor (1.0 for counter/parallel)
        flow     : flow arrangement used
        deltaT1  : ΔT at end 1 (K)
        deltaT2  : ΔT at end 2 (K)
    """
    for name, val in [("T_h_in", T_h_in), ("T_h_out", T_h_out),
                      ("T_c_in", T_c_in), ("T_c_out", T_c_out),
                      ("U", U), ("A", A)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    Th_in  = float(T_h_in)
    Th_out = float(T_h_out)
    Tc_in  = float(T_c_in)
    Tc_out = float(T_c_out)

    flow_s = str(flow).strip().lower().replace("-", "").replace("_", "")

    if flow_s in ("counter", "counterflow", "cf"):
        dT1 = Th_in  - Tc_out
        dT2 = Th_out - Tc_in
        F = 1.0
        flow_label = "counter"
    elif flow_s in ("parallel", "parallelflow", "pf"):
        dT1 = Th_in  - Tc_in
        dT2 = Th_out - Tc_out
        F = 1.0
        flow_label = "parallel"
    elif flow_s in ("crossflowunmixed", "crossflow", "cross"):
        dT1 = Th_in  - Tc_out
        dT2 = Th_out - Tc_in
        # F correction factor for cross-flow, both fluids unmixed
        # Using Incropera F-factor for unmixed-unmixed crossflow
        # P = (Tc_out - Tc_in) / (Th_in - Tc_in)
        # R = (Th_in - Th_out) / (Tc_out - Tc_in)
        denom_P = Th_in - Tc_in
        denom_R = Tc_out - Tc_in
        if denom_P == 0:
            return _err("T_h_in == T_c_in; cannot compute F correction factor")
        P = (Tc_out - Tc_in) / denom_P
        R = (Th_in - Th_out) / denom_R if denom_R != 0 else float("inf")
        # For R != 1 and R != inf (limit cases handled separately)
        if R == 1.0:
            # Special case limit
            F = (math.sqrt(2.0) * P) / ((1.0 - P) * math.log((1.0 - P) / (1.0 - P) + 1e-300))
            # Use NTU-derived F: F approaches 1 for most practical cases
            F = 1.0  # conservative approximation for R=1
        elif R == 0:
            F = 1.0
        elif math.isinf(R):
            F = 1.0
        else:
            # Standard unmixed-unmixed crossflow F factor
            # F = sqrt(R² + 1) / ((R - 1) * ln(...)) — standard TEMA formula
            try:
                sq = math.sqrt(R ** 2 + 1.0)
                if abs(R - 1.0) < 1e-10:
                    F = math.sqrt(2.0) / math.log((2.0 - P * (1.0 + 1e-6)) /
                                                   (2.0 - P * (2.0 + 1e-6) + 1e-15))
                    F = min(F, 1.0)
                else:
                    num = math.log((1.0 - R * P) / (1.0 - P))
                    den = (R - 1.0) * math.log(
                        2.0 - P * (R + 1.0 - sq) if 2.0 - P * (R + 1.0 - sq) > 1e-15
                        else 1e-15
                    )
                    if abs(den) < 1e-15:
                        F = 1.0
                    else:
                        F = sq * num / den
            except (ValueError, ZeroDivisionError):
                F = 1.0  # fallback: conservative

        F = max(0.0, min(1.0, F))  # clamp to [0, 1]
        flow_label = "crossflow_unmixed"
    else:
        return _err(
            f"Unknown flow {flow!r}. Supported: 'counter', 'parallel', 'crossflow_unmixed'."
        )

    if abs(dT1 - dT2) < 1e-10:
        LMTD = dT1
    elif dT1 <= 0 or dT2 <= 0:
        return _err(
            f"Temperature difference ΔT1={dT1:.3f} or ΔT2={dT2:.3f} is non-positive; "
            "check flow direction and temperature assignments"
        )
    else:
        LMTD = (dT1 - dT2) / math.log(dT1 / dT2)

    Q = float(U) * float(A) * F * LMTD

    return {
        "ok": True,
        "Q_W": Q,
        "LMTD_K": LMTD,
        "F": F,
        "flow": flow_label,
        "deltaT1": dT1,
        "deltaT2": dT2,
        "U_WmK": float(U),
        "A_m2": float(A),
    }


# ---------------------------------------------------------------------------
# HEAT EXCHANGER — ε-NTU method
# ---------------------------------------------------------------------------

def effectiveness_ntu(
    C_min: float,
    C_max: float,
    NTU: float,
    *,
    flow: str = "counter",
) -> dict:
    """
    Heat exchanger effectiveness via the ε-NTU method.

    C_r = C_min / C_max  (heat capacity ratio)

    Counter-flow (Incropera 11.29):
        ε = [1 - exp(-NTU(1 - Cr))] / [1 - Cr exp(-NTU(1 - Cr))]
        Special case Cr = 1:  ε = NTU / (NTU + 1)

    Parallel-flow (Incropera 11.30):
        ε = [1 - exp(-NTU(1 + Cr))] / (1 + Cr)

    Cross-flow, both fluids unmixed (Incropera 11.31):
        ε = 1 - exp[(NTU^0.22 / Cr)(exp(-Cr NTU^0.78) - 1)]

    Parameters
    ----------
    C_min : float  minimum heat capacity rate (W/K)
    C_max : float  maximum heat capacity rate (W/K)
    NTU   : float  number of transfer units (dimensionless)
    flow  : str    'counter' (default), 'parallel', 'crossflow_unmixed'

    Returns
    -------
    dict
        ok          : True
        epsilon     : heat exchanger effectiveness [0, 1]
        q_max       : maximum possible heat transfer (W·K — needs ΔT_max externally)
                      Note: q_max = C_min × ΔT_max; here C_min is returned.
                      Pass (T_h_in - T_c_in) externally to get Q.
        C_r         : heat capacity ratio C_min/C_max
        NTU         : NTU used
        flow        : flow arrangement
        C_min       : C_min (W/K)
        C_max       : C_max (W/K)
    """
    for name, val in [("C_min", C_min), ("C_max", C_max), ("NTU", NTU)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    if float(C_min) > float(C_max):
        return _err(f"C_min ({C_min}) must be <= C_max ({C_max})")

    Cmin = float(C_min)
    Cmax = float(C_max)
    ntu = float(NTU)

    Cr = Cmin / Cmax

    flow_s = str(flow).strip().lower().replace("-", "").replace("_", "")

    if flow_s in ("counter", "counterflow", "cf"):
        if abs(Cr - 1.0) < 1e-10:
            eps = ntu / (ntu + 1.0)
        else:
            exp_term = math.exp(-ntu * (1.0 - Cr))
            eps = (1.0 - exp_term) / (1.0 - Cr * exp_term)
        flow_label = "counter"
    elif flow_s in ("parallel", "parallelflow", "pf"):
        eps = (1.0 - math.exp(-ntu * (1.0 + Cr))) / (1.0 + Cr)
        flow_label = "parallel"
    elif flow_s in ("crossflowunmixed", "crossflow", "cross"):
        # Incropera 11.31
        if Cr < 1e-10:
            eps = 1.0 - math.exp(-ntu)
        else:
            eps = 1.0 - math.exp(
                (ntu ** 0.22 / Cr) * (math.exp(-Cr * ntu ** 0.78) - 1.0)
            )
        flow_label = "crossflow_unmixed"
    else:
        return _err(
            f"Unknown flow {flow!r}. Supported: 'counter', 'parallel', 'crossflow_unmixed'."
        )

    eps = min(max(eps, 0.0), 1.0)

    return {
        "ok": True,
        "epsilon": eps,
        "C_r": Cr,
        "NTU": ntu,
        "flow": flow_label,
        "C_min": Cmin,
        "C_max": Cmax,
    }


# ---------------------------------------------------------------------------
# TRANSIENT — Lumped capacitance model
# ---------------------------------------------------------------------------

def lumped_capacitance(
    T_i: float,
    T_inf: float,
    h: float,
    A_s: float,
    rho: float,
    V: float,
    c_p: float,
    t: float,
    *,
    Lc: float | None = None,
    k: float | None = None,
) -> dict:
    """
    Transient temperature response using the lumped-capacitance model.

    Incropera §5.3:
        (T(t) - T_inf) / (T_i - T_inf) = exp(-t / τ)
        τ = ρ V c_p / (h A_s)

    Biot number check:
        Bi = h L_c / k   where L_c = V / A_s  (or provided explicitly)

    A warning is issued (but not an error) if Bi > 0.1 (lumped assumption invalid).
    If k is not provided, the Biot number is not computed.

    Parameters
    ----------
    T_i   : float  initial body temperature (K). Must be > 0.
    T_inf : float  ambient/fluid temperature (K). Must be > 0.
    h     : float  convective heat transfer coefficient (W/m²·K). Must be > 0.
    A_s   : float  surface area of the body (m²). Must be > 0.
    rho   : float  body density (kg/m³). Must be > 0.
    V     : float  body volume (m³). Must be > 0.
    c_p   : float  specific heat capacity (J/kg·K). Must be > 0.
    t     : float  time (s). Must be >= 0.
    Lc    : float | None  characteristic length L_c = V/A_s (m).
                          If None, computed as V/A_s.
    k     : float | None  thermal conductivity of body (W/m·K).
                          Required to compute Biot number.

    Returns
    -------
    dict
        ok      : True
        T_t_K   : body temperature at time t (K)
        tau_s   : time constant τ (s)
        Bi      : Biot number (None if k not provided)
        theta   : dimensionless temperature excess (T(t) - T_inf) / (T_i - T_inf)
        T_i_K   : initial temperature (K)
        T_inf_K : ambient temperature (K)
        t_s     : time (s)
        Q_total_J: total heat transferred up to time t (J)
    """
    for name, val in [("T_i", T_i), ("T_inf", T_inf), ("h", h),
                      ("A_s", A_s), ("rho", rho), ("V", V), ("c_p", c_p)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)
    err = _guard_nonneg("t", t)
    if err:
        return _err(err)

    Ti = float(T_i)
    Tinf = float(T_inf)
    h_val = float(h)
    As = float(A_s)
    rho_val = float(rho)
    V_val = float(V)
    cp = float(c_p)
    t_val = float(t)

    # Time constant
    tau = rho_val * V_val * cp / (h_val * As)

    # Dimensionless temperature
    theta = math.exp(-t_val / tau)
    T_t = Tinf + (Ti - Tinf) * theta

    # Total heat transferred
    m_cp = rho_val * V_val * cp
    Q_total = m_cp * (Ti - T_t)

    # Biot number
    Lc_val = float(Lc) if Lc is not None else V_val / As
    Bi = None
    if k is not None:
        err = _guard_positive("k", k)
        if err:
            return _err(err)
        Bi = h_val * Lc_val / float(k)
        if Bi > 0.1:
            warnings.warn(
                f"lumped_capacitance: Bi={Bi:.4f} > 0.1; "
                "the lumped-capacitance assumption (spatially uniform T) is invalid. "
                "Use a distributed-parameter model (e.g. Heisler charts).",
                stacklevel=2,
            )

    return {
        "ok": True,
        "T_t_K": T_t,
        "tau_s": tau,
        "Bi": Bi,
        "theta": theta,
        "T_i_K": Ti,
        "T_inf_K": Tinf,
        "t_s": t_val,
        "Q_total_J": Q_total,
        "Lc_m": Lc_val,
    }
