"""
kerf_cad_core.waterhammer.transient — Hydraulic transient analysis.

All functions are pure Python (math only; no OCC / numpy / scipy).
Warnings are appended to result["warnings"]; exceptions are never raised.

References
----------
Wylie, E.B. & Streeter, V.L. (1993) Fluid Transients in Systems. Prentice Hall.
Chaudhry, M.H. (2014) Applied Hydraulic Transients, 3rd ed. Springer.
Streeter, V.L. & Wylie, E.B. (1967) Hydraulic Transients. McGraw-Hill.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_G = 9.80665          # gravitational acceleration (m/s²)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _warn(result: dict, msg: str) -> None:
    result.setdefault("warnings", []).append(msg)


# ---------------------------------------------------------------------------
# 1. Pressure-wave celerity (wave speed)
# ---------------------------------------------------------------------------

def wave_speed(
    K_fluid: float,
    rho: float,
    D: float,
    e: float,
    E_pipe: float,
    restraint: str = "anchored-both",
    alpha_gas: float = 0.0,
    P_abs: float = 101325.0,
) -> dict[str, Any]:
    """Pressure-wave celerity a (m/s) in a pressurised pipe.

    The Joukowsky / Allievi formula accounts for:
      - fluid compressibility (bulk modulus K_fluid)
      - pipe wall elasticity (Young's modulus E_pipe, diameter D, thickness e)
      - axial restraint factor c1 (Wylie & Streeter Table 2.1)
      - entrained gas by modifying the effective bulk modulus

    Restraint options
    -----------------
    'anchored-both'   : c1 = 1 − ν²      (both ends anchored, Poisson ν=0.3)
    'anchored-up'     : c1 = 1 − ν/2
    'expansion-joint' : c1 = 1.0

    Entrained-gas correction (Chaudhry §2.4)
    -----------------------------------------
    K_eff = 1 / (1/K_fluid + α_gas / P_abs)
    where α_gas is the void fraction (0–1).

    Parameters
    ----------
    K_fluid  : bulk modulus of the liquid (Pa).  Water ≈ 2.07e9 Pa.
    rho      : fluid density (kg/m³).  Water ≈ 998.
    D        : internal pipe diameter (m). Must be > 0.
    e        : pipe wall thickness (m). Must be > 0.
    E_pipe   : Young's modulus of pipe material (Pa).  Steel ≈ 200e9 Pa.
    restraint: axial restraint condition (see above).  Default 'anchored-both'.
    alpha_gas: free-gas void fraction 0–1 (default 0 = no gas).
    P_abs    : absolute pressure at the section (Pa), used only for gas
               correction (default 101325 Pa).

    Returns dict with:
      a_m_s        — wave celerity (m/s)
      pipe_period  — 2L/a (s) — requires L to be passed; returned as None here
                     (use moc_single_pipe or joukowsky_head_rise for full pipe)
      K_eff        — effective bulk modulus after gas correction (Pa)
      c1           — restraint factor (dimensionless)
      warnings     — list of warning strings (may be empty)
    """
    result: dict[str, Any] = {"warnings": []}

    if K_fluid <= 0:
        _warn(result, "K_fluid must be > 0; returning a=0")
        result["a_m_s"] = 0.0
        result["K_eff"] = 0.0
        result["c1"] = None
        result["pipe_period"] = None
        return result
    if rho <= 0:
        _warn(result, "rho must be > 0; returning a=0")
        result["a_m_s"] = 0.0
        result["K_eff"] = K_fluid
        result["c1"] = None
        result["pipe_period"] = None
        return result
    if D <= 0 or e <= 0:
        _warn(result, "D and e must be > 0; returning a=0")
        result["a_m_s"] = 0.0
        result["K_eff"] = K_fluid
        result["c1"] = None
        result["pipe_period"] = None
        return result
    if E_pipe <= 0:
        _warn(result, "E_pipe must be > 0; returning a=0")
        result["a_m_s"] = 0.0
        result["K_eff"] = K_fluid
        result["c1"] = None
        result["pipe_period"] = None
        return result

    # Restraint factor c1 (Poisson ν = 0.3 for steel/HDPE typical)
    nu = 0.30
    _restraint_map = {
        "anchored-both": 1.0 - nu**2,
        "anchored-up": 1.0 - nu / 2.0,
        "expansion-joint": 1.0,
    }
    if restraint not in _restraint_map:
        _warn(result, f"Unknown restraint '{restraint}'; using 'expansion-joint' (c1=1)")
        c1 = 1.0
    else:
        c1 = _restraint_map[restraint]

    # Entrained-gas correction (void fraction α_gas)
    if alpha_gas < 0.0 or alpha_gas >= 1.0:
        _warn(result, "alpha_gas must be in [0, 1); clamped to 0")
        alpha_gas = 0.0

    if alpha_gas > 0.0:
        if P_abs <= 0:
            _warn(result, "P_abs must be > 0 for gas correction; using 101325 Pa")
            P_abs = 101325.0
        K_eff = 1.0 / (1.0 / K_fluid + alpha_gas / P_abs)
    else:
        K_eff = K_fluid

    # Pipe flexibility term  (D / (e * E_pipe)) * c1
    pipe_flex = (D / (e * E_pipe)) * c1

    # Wave celerity:  a = sqrt(K_eff/rho / (1 + K_eff/rho_norm * D/(eE) * c1))
    # Correct form:  a² = (K_eff/rho) / (1 + (K_eff * D * c1) / (e * E_pipe))
    denom = 1.0 + K_eff * pipe_flex
    a = math.sqrt(K_eff / rho / denom)

    result["a_m_s"] = a
    result["K_eff"] = K_eff
    result["c1"] = c1
    result["pipe_period"] = None  # L not provided; use joukowsky or moc for full calc

    if a > 1600.0:
        _warn(result, f"Wave speed {a:.0f} m/s is unusually high (>1600 m/s); check inputs")
    if a < 100.0:
        _warn(result, f"Wave speed {a:.0f} m/s is very low (<100 m/s); likely high gas content")

    return result


# ---------------------------------------------------------------------------
# 2. Joukowsky head rise
# ---------------------------------------------------------------------------

def joukowsky_head_rise(
    V0: float,
    a: float,
    L: float,
    t_close: float,
    rho: float = 998.0,
    P_vapor_Pa: float = 2338.0,
    H0: float = 0.0,
    pipe_rating_m: float | None = None,
) -> dict[str, Any]:
    """Joukowsky (Allievi) head rise for valve closure.

    Pipe period  T_p = 2L/a

    Rapid closure (t_close ≤ T_p):
        ΔH = a · V0 / g    (instantaneous; Joukowsky)

    Slow closure (t_close > T_p):
        ΔH = a · V0 / g · (T_p / t_close)  [approximate linear interpolation]
        In practice: ΔH_slow = a · V0 / g · 2L / (a · t_close)
                              = 2 · L · V0 / (g · t_close)   [rigid-column approx]

    Parameters
    ----------
    V0         : initial flow velocity (m/s). Must be >= 0.
    a          : wave celerity (m/s). Must be > 0.
    L          : pipe length (m). Must be > 0.
    t_close    : valve closure time (s). Must be > 0.
    rho        : fluid density (kg/m³, default 998).
    P_vapor_Pa : vapour pressure (Pa, default 2338 ≈ water 20°C).
    H0         : steady-state head at valve (m, default 0 — absolute check).
    pipe_rating_m : pressure rating expressed as head (m). If given, flags
                    overpressure when H0 + ΔH > pipe_rating_m.

    Returns dict with:
      dH_m          — head rise (m, positive = pressure rise)
      H_max_m       — H0 + dH_m
      T_pipe_s      — pipe period 2L/a (s)
      rapid_closure — True if t_close <= T_pipe_s
      column_sep    — True if H_max_m - dH_m*2 < H_vapor_m  (return wave)
      overpressure  — True if H_max_m > pipe_rating_m (only if rating given)
      warnings      — list of strings
    """
    result: dict[str, Any] = {"warnings": []}

    if V0 < 0:
        _warn(result, "V0 must be >= 0; using 0")
        V0 = 0.0
    if a <= 0:
        _warn(result, "a must be > 0")
        result.update({"dH_m": 0.0, "H_max_m": H0, "T_pipe_s": None,
                       "rapid_closure": None, "column_sep": False, "overpressure": False})
        return result
    if L <= 0:
        _warn(result, "L must be > 0")
        result.update({"dH_m": 0.0, "H_max_m": H0, "T_pipe_s": None,
                       "rapid_closure": None, "column_sep": False, "overpressure": False})
        return result
    if t_close <= 0:
        _warn(result, "t_close must be > 0; using instantaneous closure")
        t_close = 1e-9

    T_pipe = 2.0 * L / a

    if t_close <= T_pipe:
        # Rapid closure — Joukowsky
        dH = a * V0 / _G
        rapid = True
    else:
        # Slow closure — rigid-column approximation
        dH = 2.0 * L * V0 / (_G * t_close)
        rapid = False

    H_max = H0 + dH
    H_vapor_m = P_vapor_Pa / (rho * _G)

    # Column separation check: on the return wave the head drops by 2*dH
    # below the initial; flag if that drops below vapor pressure head.
    H_min_estimate = H0 - dH
    col_sep = H_min_estimate < H_vapor_m
    if col_sep:
        _warn(result, (
            f"Column separation risk: estimated minimum head {H_min_estimate:.1f} m "
            f"< vapor pressure head {H_vapor_m:.2f} m"
        ))

    overpressure = False
    if pipe_rating_m is not None:
        if H_max > pipe_rating_m:
            overpressure = True
            _warn(result, (
                f"Overpressure: H_max {H_max:.1f} m exceeds pipe rating {pipe_rating_m:.1f} m"
            ))

    result.update({
        "dH_m": dH,
        "H_max_m": H_max,
        "T_pipe_s": T_pipe,
        "rapid_closure": rapid,
        "column_sep": col_sep,
        "overpressure": overpressure,
    })
    return result


# ---------------------------------------------------------------------------
# 3. MOC single-pipe solver
# ---------------------------------------------------------------------------

def moc_single_pipe(
    L: float,
    D: float,
    a: float,
    V0: float,
    H_res: float,
    f: float,
    n_reaches: int,
    t_total: float,
    closure_law: str = "linear",
    t_close: float | None = None,
    downstream_bc: str = "valve",
    P_vapor_Pa: float = 2338.0,
    rho: float = 998.0,
    pipe_rating_m: float | None = None,
) -> dict[str, Any]:
    """Method-of-Characteristics (MOC) single-pipe transient solver.

    Solves the 1-D water-hammer equations on a uniform reach grid using the
    explicit MOC scheme (Wylie & Streeter §3.2).

    Boundary conditions
    -------------------
    Upstream  : constant-head reservoir (H = H_res)
    Downstream: 'valve'    — valve with closure law τ(t), where τ=1 fully open
                'dead-end' — zero-velocity (dV/dt = 0 → V=0 always)

    Closure laws (τ: 0 = fully closed, 1 = fully open)
    ---------------------------------------------------
    'linear'    : τ(t) = max(0, 1 − t/t_close)
    'parabolic' : τ(t) = max(0, (1 − t/t_close)²)

    The valve boundary uses the characteristic equation + orifice:
        H_n = H_res - (a/g) * V_n   [for C+ characteristic from upstream]
        Q = τ · Q0 · sqrt(H_n / H0_valve)   (linearised orifice, Chaudhry §4.3)

    Parameters
    ----------
    L          : pipe length (m). Must be > 0.
    D          : internal diameter (m). Must be > 0.
    a          : wave celerity (m/s). Must be > 0.
    V0         : initial (steady-state) flow velocity (m/s). Must be >= 0.
    H_res      : upstream reservoir head (m, constant BC).
    f          : Darcy-Weisbach friction factor (dimensionless). Must be >= 0.
    n_reaches  : number of uniform reaches (integer >= 2). Reach length dx=L/n.
    t_total    : total simulation time (s). Must be > 0.
    closure_law: 'linear' or 'parabolic'. Default 'linear'.
    t_close    : valve closure time (s). Default = T_pipe (pipe period = 2L/a).
    downstream_bc: 'valve' (default) or 'dead-end'.
    P_vapor_Pa : vapour pressure (Pa). Default 2338 (water 20 °C).
    rho        : fluid density (kg/m³). Default 998.
    pipe_rating_m: pressure rating as head (m). Optional; triggers overpressure flag.

    Returns dict with:
      H_envelope_max  — list of n+1 max head values vs node position [m]
      H_envelope_min  — list of n+1 min head values vs node position [m]
      V_envelope_max  — list of n+1 max velocity values [m/s]
      V_envelope_min  — list of n+1 min velocity values [m/s]
      x_nodes_m       — node positions (m) from upstream end
      dt_s            — time step used (s)
      dx_m            — reach length (m)
      T_pipe_s        — pipe period 2L/a (s)
      n_steps         — number of time steps executed
      column_sep      — True if any node head < H_vapor
      overpressure    — True if any node max head > pipe_rating_m (if given)
      courant_ok      — True (Courant = a*dt/dx = 1 by construction)
      warnings        — list of strings
    """
    result: dict[str, Any] = {"warnings": []}

    # --- Input validation ---
    if L <= 0:
        _warn(result, "L must be > 0")
        return _moc_empty(result)
    if D <= 0:
        _warn(result, "D must be > 0")
        return _moc_empty(result)
    if a <= 0:
        _warn(result, "a must be > 0")
        return _moc_empty(result)
    if V0 < 0:
        _warn(result, "V0 must be >= 0; using 0")
        V0 = 0.0
    if f < 0:
        _warn(result, "f must be >= 0; using 0")
        f = 0.0
    if n_reaches < 2:
        _warn(result, "n_reaches must be >= 2; using 2")
        n_reaches = 2
    if t_total <= 0:
        _warn(result, "t_total must be > 0")
        return _moc_empty(result)
    if closure_law not in ("linear", "parabolic"):
        _warn(result, f"Unknown closure_law '{closure_law}'; using 'linear'")
        closure_law = "linear"
    if downstream_bc not in ("valve", "dead-end"):
        _warn(result, f"Unknown downstream_bc '{downstream_bc}'; using 'valve'")
        downstream_bc = "valve"

    dx = L / n_reaches
    # Courant-Friedrich-Lewy: dt = dx / a  → Courant = 1 exactly
    dt = dx / a
    n_nodes = n_reaches + 1
    T_pipe = 2.0 * L / a

    if t_close is None:
        t_close = T_pipe
    if t_close <= 0:
        _warn(result, "t_close must be > 0; using T_pipe")
        t_close = T_pipe

    # Steady-state initial conditions
    A_pipe = math.pi * D**2 / 4.0
    Q0 = V0 * A_pipe  # initial volumetric flow (m³/s)
    # This solver works in *velocity* (V), not discharge (Q).  The MOC
    # compatibility equations are H ± B·V with the velocity-form impedance
    # B = a/g (Wylie & Streeter §3-2; the discharge form a/(g·A) must be
    # used only with Q = V·A).  Likewise the velocity-form per-reach
    # resistance is R = f·dx/(2·g·D) (the discharge form f·dx/(2·g·D·A²)
    # would over-state losses by a factor A² when applied to V).
    R_pipe = f * dx / (2.0 * _G * D)  # friction head-loss coeff per reach (V-form)

    # Initial head gradient: H decreases from upstream to downstream due to friction
    # dH/dx = -f * V² / (2 * g * D)
    dH_dx = -f * V0**2 / (2.0 * _G * D)

    # Initial head at each node
    H = [H_res + dH_dx * i * dx for i in range(n_nodes)]
    V = [V0] * n_nodes

    # Steady-state head at downstream valve
    H0_valve = H[n_nodes - 1]

    # Pipeline hydraulic impedance, velocity form: B = a / g
    # (so that H ± B·V are the correct C+ / C- compatibility equations;
    # the C+ characteristic at an instantaneously closed valve then yields
    # the Joukowsky head rise ΔH = a·V0/g exactly.)
    B = a / _G

    H_max = list(H)
    H_min = list(H)
    V_max = list(V)
    V_min = [v for v in V]

    H_vapor_m = P_vapor_Pa / (rho * _G)
    column_sep_flag = False
    overpressure_flag = False

    def _tau(t: float) -> float:
        if t >= t_close:
            return 0.0
        frac = 1.0 - t / t_close
        if closure_law == "parabolic":
            return frac * frac
        return frac  # linear

    n_steps = max(1, int(math.ceil(t_total / dt)))
    t = 0.0

    for step in range(n_steps):
        t += dt
        H_new = [0.0] * n_nodes
        V_new = [0.0] * n_nodes

        # --- Interior nodes (i=1..n-1) using C+ and C- characteristics ---
        for i in range(1, n_nodes - 1):
            # C+: from (i-1) at previous step
            Cp = H[i - 1] + B * V[i - 1] - R_pipe * V[i - 1] * abs(V[i - 1])
            Cm = H[i + 1] - B * V[i + 1] + R_pipe * V[i + 1] * abs(V[i + 1])
            H_new[i] = 0.5 * (Cp + Cm)
            V_new[i] = (Cp - Cm) / (2.0 * B)

        # --- Upstream BC: reservoir (H = H_res) ---
        # Use C- characteristic from node 1
        Cm0 = H[1] - B * V[1] + R_pipe * V[1] * abs(V[1])
        H_new[0] = H_res
        V_new[0] = (H_res - Cm0) / B

        # --- Downstream BC ---
        if downstream_bc == "dead-end":
            # V = 0 always; use C+ from node n-2
            Cp_n = H[n_nodes - 2] + B * V[n_nodes - 2] - R_pipe * V[n_nodes - 2] * abs(V[n_nodes - 2])
            H_new[n_nodes - 1] = Cp_n  # V=0 so H_new = Cp
            V_new[n_nodes - 1] = 0.0
        else:
            # Valve BC: C+ from node n-2 + orifice equation
            Cp_n = H[n_nodes - 2] + B * V[n_nodes - 2] - R_pipe * V[n_nodes - 2] * abs(V[n_nodes - 2])
            tau = _tau(t)
            if tau <= 0.0:
                # Fully closed
                V_new[n_nodes - 1] = 0.0
                H_new[n_nodes - 1] = Cp_n
            elif H0_valve <= 0.0:
                # Degenerate: no initial head at valve — use C+ only
                V_new[n_nodes - 1] = 0.0
                H_new[n_nodes - 1] = Cp_n
            else:
                # Orifice: Q = tau * Q0 * sqrt(H_v / H0_valve)
                # Combined with C+: H_v = Cp_n - B * V_v
                # Q_v = V_v * A
                # V_v = tau * V0 * sqrt(H_v / H0_valve)
                # Substitute: H_v = Cp_n - B * tau * V0 * sqrt(H_v / H0_valve)
                # Let u = sqrt(H_v / H0_valve); H_v = H0_valve * u²
                # H0_valve * u² + B * tau * V0 * u - Cp_n = 0
                a_coef = H0_valve
                b_coef = B * tau * V0
                c_coef = -Cp_n
                disc = b_coef**2 - 4.0 * a_coef * c_coef
                if disc < 0.0:
                    disc = 0.0
                u = (-b_coef + math.sqrt(disc)) / (2.0 * a_coef)
                if u < 0.0:
                    u = 0.0
                H_new[n_nodes - 1] = H0_valve * u * u
                V_new[n_nodes - 1] = tau * V0 * u

        # --- Update state and envelopes ---
        for i in range(n_nodes):
            H[i] = H_new[i]
            V[i] = V_new[i]
            if H[i] > H_max[i]:
                H_max[i] = H[i]
            if H[i] < H_min[i]:
                H_min[i] = H[i]
            if V[i] > V_max[i]:
                V_max[i] = V[i]
            if V[i] < V_min[i]:
                V_min[i] = V[i]

            # Column separation
            if H[i] < H_vapor_m:
                column_sep_flag = True

            # Overpressure
            if pipe_rating_m is not None and H[i] > pipe_rating_m:
                overpressure_flag = True

    if column_sep_flag:
        _warn(result, (
            "Column separation detected: head dropped below vapor pressure head "
            f"({H_vapor_m:.2f} m). MOC results may be unreliable beyond this point."
        ))
    if overpressure_flag and pipe_rating_m is not None:
        _warn(result, (
            f"Overpressure: head exceeded pipe rating {pipe_rating_m:.1f} m at one or more nodes."
        ))

    x_nodes = [i * dx for i in range(n_nodes)]

    result.update({
        "H_envelope_max": H_max,
        "H_envelope_min": H_min,
        "V_envelope_max": V_max,
        "V_envelope_min": V_min,
        "x_nodes_m": x_nodes,
        "dt_s": dt,
        "dx_m": dx,
        "T_pipe_s": T_pipe,
        "n_steps": n_steps,
        "column_sep": column_sep_flag,
        "overpressure": overpressure_flag,
        "courant_ok": True,
    })
    return result


def _moc_empty(result: dict) -> dict:
    result.update({
        "H_envelope_max": [],
        "H_envelope_min": [],
        "V_envelope_max": [],
        "V_envelope_min": [],
        "x_nodes_m": [],
        "dt_s": None,
        "dx_m": None,
        "T_pipe_s": None,
        "n_steps": 0,
        "column_sep": False,
        "overpressure": False,
        "courant_ok": False,
    })
    return result


# ---------------------------------------------------------------------------
# 4. Safe valve-closure time
# ---------------------------------------------------------------------------

def safe_closure_time(
    V0: float,
    a: float,
    L: float,
    H0: float,
    dH_allowable: float,
) -> dict[str, Any]:
    """Minimum safe valve-closure time to limit surge below dH_allowable.

    Based on the slow-closure (rigid-column) formula:
        ΔH_slow = 2 · L · V0 / (g · t_close)

    Solving for t_close:
        t_close_min = 2 · L · V0 / (g · dH_allowable)

    Also computes the critical (pipe period) time T_pipe = 2L/a, and
    flags whether the safe time is rapid or slow closure.

    Parameters
    ----------
    V0           : initial velocity (m/s). Must be >= 0.
    a            : wave celerity (m/s). Must be > 0.
    L            : pipe length (m). Must be > 0.
    H0           : steady-state head at valve (m). Must be > 0.
    dH_allowable : maximum allowable head rise (m). Must be > 0.

    Returns dict with:
      t_close_min_s  — minimum safe closure time (s)
      T_pipe_s       — pipe period 2L/a (s)
      rapid_at_min   — True if t_close_min <= T_pipe (closure is in rapid regime)
      dH_rapid_m     — Joukowsky head rise for instantaneous closure (m)
      warnings       — list of strings
    """
    result: dict[str, Any] = {"warnings": []}

    if V0 < 0:
        _warn(result, "V0 must be >= 0; using 0")
        V0 = 0.0
    if a <= 0:
        _warn(result, "a must be > 0")
        result.update({"t_close_min_s": None, "T_pipe_s": None,
                       "rapid_at_min": None, "dH_rapid_m": None})
        return result
    if L <= 0:
        _warn(result, "L must be > 0")
        result.update({"t_close_min_s": None, "T_pipe_s": None,
                       "rapid_at_min": None, "dH_rapid_m": None})
        return result
    if H0 <= 0:
        _warn(result, "H0 must be > 0")
        result.update({"t_close_min_s": None, "T_pipe_s": None,
                       "rapid_at_min": None, "dH_rapid_m": None})
        return result
    if dH_allowable <= 0:
        _warn(result, "dH_allowable must be > 0")
        result.update({"t_close_min_s": None, "T_pipe_s": None,
                       "rapid_at_min": None, "dH_rapid_m": None})
        return result

    T_pipe = 2.0 * L / a
    dH_rapid = a * V0 / _G

    if V0 == 0.0:
        t_close_min = 0.0
    else:
        t_close_min = 2.0 * L * V0 / (_G * dH_allowable)

    rapid_at_min = t_close_min <= T_pipe

    if dH_rapid > dH_allowable and t_close_min <= T_pipe:
        _warn(result, (
            f"Even at t_close_min={t_close_min:.2f} s the closure is in the rapid "
            f"regime (T_pipe={T_pipe:.2f} s); actual surge may exceed dH_allowable. "
            "Consider a longer closure time or surge protection."
        ))

    result.update({
        "t_close_min_s": t_close_min,
        "T_pipe_s": T_pipe,
        "rapid_at_min": rapid_at_min,
        "dH_rapid_m": dH_rapid,
    })
    return result


# ---------------------------------------------------------------------------
# 5. Pump-trip transient (simplified)
# ---------------------------------------------------------------------------

def pump_trip_simplified(
    H_ss: float,
    V0: float,
    a: float,
    L: float,
    WR2: float,
    n_rated: float,
    P_rated_W: float,
    rho: float = 998.0,
    D: float = 0.0,
    P_vapor_Pa: float = 2338.0,
) -> dict[str, Any]:
    """Simplified pump-trip (power failure) transient analysis.

    Uses the rigid-column / Joukowsky approach to estimate:
    1. Pump rundown time (deceleration from rated speed to zero):
           t_rundown = WR² · n_rated / (375 · P_rated_W / n_rated)
           Simplified: τ_run = WR² · (2π·n_rated/60)² / (2 · T_rated)
           where T_rated = P_rated_W / (2π·n_rated/60)

    2. Head drop at pump (check-valve upstream):
           After trip, flow decelerates.  For rigid-column over time t_run:
           ΔH_drop = V0 · a / g  (max instantaneous Joukowsky depression)

    3. Check-valve slam (when flow reverses):
           ΔH_slam = a · |V_reverse| / g
           V_reverse estimated as V0 (conservative) after full reversal.

    4. Column-separation flag at pump suction (H_pump_min < H_vapor).

    Parameters
    ----------
    H_ss     : steady-state total head at pump discharge (m). Must be > 0.
    V0       : steady-state pipe velocity (m/s). Must be > 0.
    a        : wave celerity (m/s). Must be > 0.
    L        : pipe length (m). Must be > 0.
    WR2      : pump + motor rotational inertia W·R² (kg·m²). Must be > 0.
    n_rated  : rated speed (rpm). Must be > 0.
    P_rated_W: rated shaft power (W). Must be > 0.
    rho      : fluid density (kg/m³, default 998).
    D        : pipe diameter (m). Used only if > 0 to compute A; else V0 used directly.
    P_vapor_Pa: vapour pressure (Pa, default 2338).

    Returns dict with:
      t_rundown_s    — estimated pump rundown time (s)
      dH_drop_m      — Joukowsky head drop at pump trip (m, positive = drop)
      dH_slam_m      — check-valve slam head rise (m)
      H_min_m        — estimated minimum head (H_ss - dH_drop)
      column_sep     — True if H_min_m < H_vapor_m
      warnings       — list of strings
    """
    result: dict[str, Any] = {"warnings": []}

    for name, val in [("H_ss", H_ss), ("V0", V0), ("a", a), ("L", L),
                      ("WR2", WR2), ("n_rated", n_rated), ("P_rated_W", P_rated_W)]:
        if val <= 0:
            _warn(result, f"{name} must be > 0")
            result.update({"t_rundown_s": None, "dH_drop_m": None,
                           "dH_slam_m": None, "H_min_m": None, "column_sep": False})
            return result

    omega = 2.0 * math.pi * n_rated / 60.0  # rad/s
    T_rated = P_rated_W / omega               # rated torque (N·m)
    # Deceleration: I·dω/dt = -T_rated  → t_run = I·ω / T_rated
    # I = WR² (kg·m²), assuming WR² is moment of inertia
    t_rundown = WR2 * omega / T_rated

    dH_drop = a * V0 / _G         # Joukowsky depression at trip
    dH_slam = a * V0 / _G         # conservative: check-valve slam = same magnitude
    H_min = H_ss - dH_drop

    H_vapor_m = P_vapor_Pa / (rho * _G)
    col_sep = H_min < H_vapor_m
    if col_sep:
        _warn(result, (
            f"Column separation risk after pump trip: estimated H_min={H_min:.1f} m "
            f"< vapor head {H_vapor_m:.2f} m. Consider surge protection."
        ))

    result.update({
        "t_rundown_s": t_rundown,
        "dH_drop_m": dH_drop,
        "dH_slam_m": dH_slam,
        "H_min_m": H_min,
        "column_sep": col_sep,
    })
    return result


# ---------------------------------------------------------------------------
# 6. Air vessel sizing (rigid-column approximation)
# ---------------------------------------------------------------------------

def air_vessel_sizing(
    V0: float,
    A_pipe: float,
    a: float,
    L: float,
    H_res: float,
    dH_allowable: float,
    P_atm_Pa: float = 101325.0,
    rho: float = 998.0,
    polytropic_n: float = 1.2,
) -> dict[str, Any]:
    """Estimate air vessel (air chamber) volume for surge protection.

    Uses the rigid-column analysis (Wylie & Streeter §8.2):

      The vessel must absorb the kinetic energy of the decelerating water
      column.  The minimum air volume is derived from the polytropic gas law:

        P1 · V1^n = P2 · V2^n

      and the rigid-column momentum equation:

        L/A · dV/dt = -g · (H - H_res)   (simplified single pipe)

    Simplified estimate (Chaudhry §13.3):

      Minimum air volume:
        Vol_air = (a · L · V0 · A_pipe) / (2 · g · dH_allowable)

    Parameters
    ----------
    V0           : initial velocity (m/s). Must be > 0.
    A_pipe       : pipe cross-sectional area (m²). Must be > 0.
    a            : wave celerity (m/s). Must be > 0.
    L            : pipe length (m). Must be > 0.
    H_res        : reservoir head (m). Must be > 0.
    dH_allowable : max allowable head change (m). Must be > 0.
    P_atm_Pa     : atmospheric pressure (Pa, default 101325).
    rho          : fluid density (kg/m³, default 998).
    polytropic_n : polytropic index for air compression (default 1.2).

    Returns dict with:
      vol_min_m3        — minimum air volume (m³)
      vol_recommended_m3— 1.5× safety-factored volume (m³)
      initial_pressure_Pa — initial air pressure = rho*g*H_res + P_atm_Pa (Pa)
      warnings          — list of strings
    """
    result: dict[str, Any] = {"warnings": []}

    for name, val in [("V0", V0), ("A_pipe", A_pipe), ("a", a), ("L", L),
                      ("H_res", H_res), ("dH_allowable", dH_allowable)]:
        if val <= 0:
            _warn(result, f"{name} must be > 0")
            result.update({"vol_min_m3": None, "vol_recommended_m3": None,
                           "initial_pressure_Pa": None})
            return result

    # Minimum air volume (simplified rigid-column formula)
    vol_min = (a * L * V0 * A_pipe) / (2.0 * _G * dH_allowable)

    vol_recommended = 1.5 * vol_min  # 50% safety factor

    P_initial = rho * _G * H_res + P_atm_Pa

    if polytropic_n != 1.0 and polytropic_n != 1.4:
        _warn(result, (
            f"polytropic_n={polytropic_n} used; typical values: 1.0 (isothermal) "
            "or 1.4 (adiabatic). 1.2 is commonly used in practice."
        ))

    result.update({
        "vol_min_m3": vol_min,
        "vol_recommended_m3": vol_recommended,
        "initial_pressure_Pa": P_initial,
    })
    return result


# ---------------------------------------------------------------------------
# 7. Surge tank — oscillation period and amplitude
# ---------------------------------------------------------------------------

def surge_tank_oscillation(
    L: float,
    A_pipe: float,
    A_tank: float,
    H0: float,
    V0: float,
    rho: float = 998.0,
) -> dict[str, Any]:
    """Surge tank (simple open tank) oscillation period and amplitude.

    Mass-oscillation equations (Wylie & Streeter §8.1 / Chaudhry §13.2):

      Period:    T_osc = 2π · sqrt(L · A_tank / (g · A_pipe))
      Amplitude: z_max = V0 · sqrt(L · A_pipe / (g · A_tank))

    (Jaeger; Chaudhry, Applied Hydraulic Transients §13-2.  The
    frictionless surge amplitude follows from energy conservation
    ½·(ρ L A_pipe) V0² = ½·(ρ g A_tank) z_max², giving
    z_max = V0·sqrt(L·A_pipe / (g·A_tank)).  Note z_max = V0·(A_pipe/A_tank)/ω,
    NOT V0/ω.)

    This is for an undamped, frictionless simple surge tank (conservative
    upper bound on oscillation amplitude).

    Parameters
    ----------
    L      : tunnel / pipe length from reservoir to surge tank (m). Must be > 0.
    A_pipe : tunnel / pipe cross-sectional area (m²). Must be > 0.
    A_tank : surge tank cross-sectional area (m²). Must be > 0.
    H0     : initial steady-state head in tunnel (m). Must be > 0.
    V0     : initial flow velocity (m/s). Must be >= 0.
    rho    : fluid density (kg/m³, default 998).

    Returns dict with:
      T_osc_s    — oscillation period (s)
      z_max_m    — maximum water-level amplitude in surge tank (m)
      omega_rad_s— natural frequency (rad/s)
      warnings   — list of strings
    """
    result: dict[str, Any] = {"warnings": []}

    for name, val in [("L", L), ("A_pipe", A_pipe), ("A_tank", A_tank), ("H0", H0)]:
        if val <= 0:
            _warn(result, f"{name} must be > 0")
            result.update({"T_osc_s": None, "z_max_m": None, "omega_rad_s": None})
            return result
    if V0 < 0:
        _warn(result, "V0 must be >= 0; using 0")
        V0 = 0.0

    omega = math.sqrt(_G * A_pipe / (L * A_tank))
    T_osc = 2.0 * math.pi / omega
    # Frictionless mass-oscillation amplitude (Chaudhry §13-2):
    #   z_max = V0 · sqrt(L · A_pipe / (g · A_tank))
    # Equivalently z_max = V0 · (A_pipe / A_tank) / omega.  The previous
    # form V0/omega = V0·sqrt(L·A_tank/(g·A_pipe)) inverted the area ratio
    # and over-predicted the surge by a factor A_tank/A_pipe.
    z_max = V0 * math.sqrt(L * A_pipe / (_G * A_tank))

    if z_max > H0:
        _warn(result, (
            f"Surge tank amplitude z_max={z_max:.1f} m exceeds initial head H0={H0:.1f} m; "
            "tank may drain or overflow. Increase tank area or reduce velocity."
        ))

    result.update({
        "T_osc_s": T_osc,
        "z_max_m": z_max,
        "omega_rad_s": omega,
    })
    return result


# ---------------------------------------------------------------------------
# 8. Relief valve flow
# ---------------------------------------------------------------------------

def relief_valve_flow(
    H_set: float,
    H_operating: float,
    Cv: float,
    rho: float = 998.0,
    P_atm_Pa: float = 101325.0,
) -> dict[str, Any]:
    """Estimate relief valve discharge flow rate.

    Uses the orifice / Cv formula:
        Q = Cv · sqrt(dP)   [US flow coefficient, dP in psi — converted internally]

    Alternatively, using the SI head form:
        Q = A_eff · sqrt(2·g·dH)

    This function uses the SI form.  Cv_SI = A_eff · sqrt(2g):
        Cv_SI = Cv · 2.403e-5  (converts US GPM/sqrt(psi) to m³/s/sqrt(Pa))

    Parameters
    ----------
    H_set       : relief valve set pressure expressed as head (m). Must be > 0.
    H_operating : actual upstream head at the valve (m). Must be > 0.
    Cv          : valve flow coefficient (US units: GPM/sqrt(psi)). Must be > 0.
    rho         : fluid density (kg/m³, default 998).
    P_atm_Pa    : atmospheric pressure (Pa, default 101325).

    Returns dict with:
      Q_m3s      — discharge flow rate (m³/s)
      dH_m       — differential head across valve (m)
      valve_open — True if H_operating > H_set
      warnings   — list of strings
    """
    result: dict[str, Any] = {"warnings": []}

    for name, val in [("H_set", H_set), ("H_operating", H_operating), ("Cv", Cv)]:
        if val <= 0:
            _warn(result, f"{name} must be > 0")
            result.update({"Q_m3s": 0.0, "dH_m": 0.0, "valve_open": False})
            return result

    valve_open = H_operating > H_set

    if not valve_open:
        result.update({"Q_m3s": 0.0, "dH_m": 0.0, "valve_open": False})
        return result

    dH = H_operating - H_set
    dP_Pa = rho * _G * dH
    dP_psi = dP_Pa / 6894.757  # 1 psi = 6894.757 Pa

    # Cv in GPM/sqrt(psi); Q_GPM = Cv * sqrt(dP_psi)
    Q_gpm = Cv * math.sqrt(dP_psi)
    Q_m3s = Q_gpm * 6.30902e-5  # 1 GPM = 6.30902e-5 m³/s

    result.update({
        "Q_m3s": Q_m3s,
        "dH_m": dH,
        "valve_open": True,
    })
    return result
