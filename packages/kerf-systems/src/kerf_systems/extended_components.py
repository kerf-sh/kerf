"""
kerf_systems.extended_components
=================================

Extended Modelica-class component library.

All components follow the kerf_systems component convention exactly:

    Component.n_vars        : int       — number of local state variables
    Component.var_names     : list[str] — variable names (property)
    Component.default_x0    : list[float] — initial state (property)
    Component.residuals(t, x, dx) -> list[float]
        Returns one residual per equation contributed.
        len(residuals) == n_vars - (algebraic variables without an ODE).

Domains covered
---------------
  Mechanical 1-D translational / rotational
    Mass, Spring, Damper, Lever, Gear, Bearing
  Hydraulic (extended)
    Orifice, Valve, Accumulator, Pump_constant_flow
  Pneumatic
    Pneumatic_cylinder
  Thermal-fluid
    Heat_exchanger_eNTU
  Control (extended)
    Lead_lag, Deadband, Saturation, Rate_limiter
"""

from __future__ import annotations

import math
from typing import Callable, Sequence


# ===========================================================================
# 1. MECHANICAL 1-D TRANSLATIONAL / ROTATIONAL
# ===========================================================================


class Mass:
    """
    Ideal translational mass (Newton's 2nd law).

    Governing equations:
      m * dv/dt = F_net   (Newton II)
      dx/dt = v           (kinematic relation)

    Modelica analogue: Modelica.Mechanics.Translational.Components.Mass

    Variables (x_local):
      0  pos    — position [m]
      1  vel    — velocity [m/s]

    Residuals:
      d(pos)/dt - vel
      m * d(vel)/dt - F_in

    Parameters
    ----------
    m : float
        Mass [kg].
    F_in : float or callable(t)
        Applied force [N].  Default 0.
    x0 : float
        Initial position [m].  Default 0.
    v0 : float
        Initial velocity [m/s].  Default 0.
    """

    n_vars = 2

    def __init__(
        self,
        m: float,
        F_in=0.0,
        x0: float = 0.0,
        v0: float = 0.0,
    ) -> None:
        if m <= 0:
            raise ValueError(f"Mass: m must be > 0, got {m}")
        self.m = float(m)
        self._F_in = F_in
        self._x0 = float(x0)
        self._v0 = float(v0)

    def _get_F(self, t: float) -> float:
        if callable(self._F_in):
            return float(self._F_in(t))
        return float(self._F_in)

    @property
    def default_x0(self) -> list[float]:
        return [self._x0, self._v0]

    @property
    def var_names(self) -> list[str]:
        return ["pos", "vel"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        pos, vel = x[0], x[1]
        dpos, dvel = dx[0], dx[1]
        F = self._get_F(t)
        return [
            dpos - vel,          # kinematic constraint
            self.m * dvel - F,   # Newton II
        ]


class Spring:
    """
    Ideal translational spring (Hooke's law).

    Governing equation:
      F = k * (x_a - x_b)

    Modelica analogue: Modelica.Mechanics.Translational.Components.Spring

    Variables (x_local):
      0  x_a — position of port a [m]
      1  x_b — position of port b [m]
      2  F   — spring force [N]  (+ means compression of port a)

    Residual:
      F - k * (x_a - x_b)

    Parameters
    ----------
    k : float
        Spring stiffness [N/m].
    x_a0, x_b0 : float
        Initial positions.  Default 0, 0.
    """

    n_vars = 3

    def __init__(self, k: float, x_a0: float = 0.0, x_b0: float = 0.0) -> None:
        if k <= 0:
            raise ValueError(f"Spring: k must be > 0, got {k}")
        self.k = float(k)
        self._x_a0 = float(x_a0)
        self._x_b0 = float(x_b0)

    @property
    def default_x0(self) -> list[float]:
        return [self._x_a0, self._x_b0, self.k * (self._x_a0 - self._x_b0)]

    @property
    def var_names(self) -> list[str]:
        return ["x_a", "x_b", "F"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        x_a, x_b, F = x[0], x[1], x[2]
        return [F - self.k * (x_a - x_b)]


class Damper:
    """
    Ideal translational viscous damper.

    Governing equation:
      F = b * (v_a - v_b)

    Modelica analogue: Modelica.Mechanics.Translational.Components.Damper

    Variables (x_local):
      0  v_a — velocity at port a [m/s]
      1  v_b — velocity at port b [m/s]
      2  F   — damping force [N]

    Residual:
      F - b * (v_a - v_b)

    Parameters
    ----------
    b : float
        Viscous damping coefficient [N·s/m].
    """

    n_vars = 3

    def __init__(self, b: float) -> None:
        if b <= 0:
            raise ValueError(f"Damper: b must be > 0, got {b}")
        self.b = float(b)

    @property
    def default_x0(self) -> list[float]:
        return [0.0, 0.0, 0.0]

    @property
    def var_names(self) -> list[str]:
        return ["v_a", "v_b", "F"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        v_a, v_b, F = x[0], x[1], x[2]
        return [F - self.b * (v_a - v_b)]


class Lever:
    """
    Rigid lever (two-arm).

    Governing equations (static equilibrium):
      F_out = F_in * (l1 / l2)
      x_out = x_in * (l2 / l1)   [displacement relation]

    Modelica analogue: Modelica.Mechanics.Translational.Components.IdealRollingWheel
    (conceptually; a true lever class is less common in MSL).

    Variables (x_local):
      0  F_in  — input force [N]
      1  F_out — output force [N]
      2  x_in  — input displacement [m]
      3  x_out — output displacement [m]

    Residuals:
      F_out - F_in * (l1 / l2)
      x_out - x_in * (l2 / l1)

    Parameters
    ----------
    l1 : float
        Input arm length [m].
    l2 : float
        Output arm length [m].
    """

    n_vars = 4

    def __init__(self, l1: float, l2: float) -> None:
        if l1 <= 0:
            raise ValueError(f"Lever: l1 must be > 0, got {l1}")
        if l2 <= 0:
            raise ValueError(f"Lever: l2 must be > 0, got {l2}")
        self.l1 = float(l1)
        self.l2 = float(l2)

    @property
    def default_x0(self) -> list[float]:
        return [0.0, 0.0, 0.0, 0.0]

    @property
    def var_names(self) -> list[str]:
        return ["F_in", "F_out", "x_in", "x_out"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        F_in, F_out, x_in, x_out = x[0], x[1], x[2], x[3]
        ratio = self.l1 / self.l2
        return [
            F_out - F_in * ratio,
            x_out - x_in / ratio,
        ]


class Gear:
    """
    Ideal gear (rotational).

    Governing equations:
      omega_out = omega_in / ratio
      T_out     = T_in * ratio

    Modelica analogue: Modelica.Mechanics.Rotational.Components.IdealGear

    Variables (x_local):
      0  omega_in  — input angular velocity [rad/s]
      1  omega_out — output angular velocity [rad/s]
      2  T_in      — input torque [N·m]
      3  T_out     — output torque [N·m]

    Residuals:
      omega_out - omega_in / ratio
      T_out     - T_in * ratio

    Parameters
    ----------
    ratio : float
        Gear ratio (input/output).  ratio > 1 → speed reduction.
    """

    n_vars = 4

    def __init__(self, ratio: float) -> None:
        if ratio <= 0:
            raise ValueError(f"Gear: ratio must be > 0, got {ratio}")
        self.ratio = float(ratio)

    @property
    def default_x0(self) -> list[float]:
        return [0.0, 0.0, 0.0, 0.0]

    @property
    def var_names(self) -> list[str]:
        return ["omega_in", "omega_out", "T_in", "T_out"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        omega_in, omega_out, T_in, T_out = x[0], x[1], x[2], x[3]
        return [
            omega_out - omega_in / self.ratio,
            T_out - T_in * self.ratio,
        ]


class Bearing:
    """
    Bearing with Coulomb + viscous friction torque.

    Governing equation:
      T_friction = mu_c * T_normal * sign(omega) + b_v * omega

    For continuous simulation, sign(omega) is regularised with a
    smooth hyperbolic tangent:
      sign_reg(omega) = tanh(omega / omega_eps)

    Modelica analogue: Modelica.Mechanics.Rotational.Components.BearingFriction

    Variables (x_local):
      0  omega     — shaft angular velocity [rad/s]
      1  T_friction — friction torque opposing motion [N·m]

    Residual:
      T_friction - (mu_c * T_normal * tanh(omega / omega_eps) + b_v * omega)

    Parameters
    ----------
    mu_c : float
        Coulomb friction coefficient (dimensionless).  Default 0.01.
    T_normal : float
        Normal force * effective radius [N·m].  Default 1.0.
    b_v : float
        Viscous friction coefficient [N·m·s/rad].  Default 0.0.
    omega_eps : float
        Regularisation bandwidth [rad/s].  Default 0.01.
    """

    n_vars = 2

    def __init__(
        self,
        mu_c: float = 0.01,
        T_normal: float = 1.0,
        b_v: float = 0.0,
        omega_eps: float = 0.01,
    ) -> None:
        if T_normal < 0:
            raise ValueError(f"Bearing: T_normal must be >= 0, got {T_normal}")
        if omega_eps <= 0:
            raise ValueError(f"Bearing: omega_eps must be > 0, got {omega_eps}")
        self.mu_c = float(mu_c)
        self.T_normal = float(T_normal)
        self.b_v = float(b_v)
        self.omega_eps = float(omega_eps)

    @property
    def default_x0(self) -> list[float]:
        return [0.0, 0.0]

    @property
    def var_names(self) -> list[str]:
        return ["omega", "T_friction"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        omega, T_friction = x[0], x[1]
        sign_reg = math.tanh(omega / self.omega_eps)
        T_expected = self.mu_c * self.T_normal * sign_reg + self.b_v * omega
        return [T_friction - T_expected]


# ===========================================================================
# 2. HYDRAULIC (EXTENDED)
# ===========================================================================


class Orifice:
    """
    Turbulent orifice — Torricelli / square-root pressure-flow law.

    Q = Cd * A * sqrt(2 * |ΔP| / rho) * sign(ΔP)

    Regularised at ΔP≈0 to avoid sqrt singularity:
      Q = Cd * A * sqrt(2 * sqrt(ΔP² + ε²) / rho) * sign(ΔP)

    Modelica analogue: Modelica.Fluid.Fittings.SimpleGenericOrifice

    Variables (x_local):
      0  P_a — upstream pressure [Pa]
      1  P_b — downstream pressure [Pa]
      2  Q   — volumetric flow [m³/s]  (positive: a→b)

    Residual:
      Q - Cd * A * sqrt(2 * sqrt((P_a-P_b)²+ε²) / rho) * sign(P_a-P_b)

    Parameters
    ----------
    Cd : float
        Discharge coefficient (0 < Cd ≤ 1).  Default 0.611.
    A : float
        Orifice area [m²].
    rho : float
        Fluid density [kg/m³].  Default 870 (hydraulic oil).
    """

    n_vars = 3

    def __init__(self, Cd: float, A: float, rho: float = 870.0) -> None:
        if Cd <= 0 or Cd > 1:
            raise ValueError(f"Orifice: Cd must be in (0,1], got {Cd}")
        if A <= 0:
            raise ValueError(f"Orifice: A must be > 0, got {A}")
        if rho <= 0:
            raise ValueError(f"Orifice: rho must be > 0, got {rho}")
        self.Cd = float(Cd)
        self.A = float(A)
        self.rho = float(rho)

    @property
    def default_x0(self) -> list[float]:
        return [1e5, 0.0, 0.0]

    @property
    def var_names(self) -> list[str]:
        return ["P_a", "P_b", "Q"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        P_a, P_b, Q = x[0], x[1], x[2]
        dP = P_a - P_b
        eps = 1.0  # Pa regularisation
        q_mag = self.Cd * self.A * math.sqrt(2.0 * math.sqrt(dP * dP + eps * eps) / self.rho)
        q_signed = q_mag if dP >= 0 else -q_mag
        return [Q - q_signed]


class Valve:
    """
    Variable-opening control valve.

    Q = Cd * (opening * A_max) * sqrt(2 * |ΔP| / rho) * sign(ΔP)

    opening is clamped to [0, 1].

    Modelica analogue: Modelica.Fluid.Valves.ValveLinear

    Variables (x_local):
      0  P_a    — inlet pressure [Pa]
      1  P_b    — outlet pressure [Pa]
      2  opening — fractional valve opening [0..1]
      3  Q      — volumetric flow [m³/s]

    Residual:
      Q - Cd * clamp(opening,0,1) * A_max * sqrt(2*|ΔP|/rho) * sign(ΔP)

    Parameters
    ----------
    Cd : float
        Discharge coefficient.  Default 0.7.
    A_max : float
        Full-open orifice area [m²].
    rho : float
        Fluid density [kg/m³].  Default 870.
    """

    n_vars = 4

    def __init__(self, Cd: float = 0.7, A_max: float = 1e-4, rho: float = 870.0) -> None:
        if Cd <= 0 or Cd > 1:
            raise ValueError(f"Valve: Cd must be in (0,1], got {Cd}")
        if A_max <= 0:
            raise ValueError(f"Valve: A_max must be > 0, got {A_max}")
        if rho <= 0:
            raise ValueError(f"Valve: rho must be > 0, got {rho}")
        self.Cd = float(Cd)
        self.A_max = float(A_max)
        self.rho = float(rho)

    @property
    def default_x0(self) -> list[float]:
        return [1e5, 0.0, 1.0, 0.0]

    @property
    def var_names(self) -> list[str]:
        return ["P_a", "P_b", "opening", "Q"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        P_a, P_b, opening, Q = x[0], x[1], x[2], x[3]
        alpha = max(0.0, min(1.0, opening))
        dP = P_a - P_b
        eps = 1.0  # Pa
        q_mag = self.Cd * alpha * self.A_max * math.sqrt(
            2.0 * math.sqrt(dP * dP + eps * eps) / self.rho
        )
        q_signed = q_mag if dP >= 0 else -q_mag
        return [Q - q_signed]


class Accumulator:
    """
    Gas-charged hydraulic accumulator (polytropic process).

    Gas law (polytropic):
      P * V^n = P0 * V0^n  →  V_gas = V0 * (P0 / P)^(1/n)
    Liquid volume:
      V_liq = V0 - V_gas

    Dynamic equation (compliance):
      dV_liq/dt = Q_in   (continuity)
      P = P0 * (V0 / V_gas)^n = P0 * (V0 / (V0 - V_liq))^n

    For small deviations about operating point P_op, linearised compliance:
      C_acc = V_liq_op / (n * P_op)
      C_acc * dP/dt = Q_in

    This implementation uses the nonlinear formulation:
      State:  [P, V_liq]
      ODEs:   dV_liq/dt - Q_in = 0
      Algebraic: P - P0 * (V0 / (V0 - V_liq))^n = 0

    Modelica analogue: Modelica.Fluid.Vessels.ClosedVolume + IdealGas

    Variables (x_local):
      0  P     — gas/liquid interface pressure [Pa]
      1  V_liq — liquid volume in accumulator [m³]
      2  Q_in  — volumetric inflow [m³/s]

    Residuals:
      dV_liq/dt - Q_in
      P - P0 * (V0 / (V0 - V_liq))^n  [algebraic pressure equation]

    Parameters
    ----------
    V0 : float
        Pre-charge gas volume [m³].
    P0 : float
        Pre-charge pressure [Pa].  Default 1e6.
    n : float
        Polytropic index (1.0 = isothermal, 1.4 = adiabatic).  Default 1.4.
    """

    n_vars = 3

    def __init__(self, V0: float, P0: float = 1e6, n: float = 1.4) -> None:
        if V0 <= 0:
            raise ValueError(f"Accumulator: V0 must be > 0, got {V0}")
        if P0 <= 0:
            raise ValueError(f"Accumulator: P0 must be > 0, got {P0}")
        if n <= 0:
            raise ValueError(f"Accumulator: n must be > 0, got {n}")
        self.V0 = float(V0)
        self.P0 = float(P0)
        self.n = float(n)

    @property
    def default_x0(self) -> list[float]:
        # Initially no liquid, gas at pre-charge pressure
        return [self.P0, 0.0, 0.0]

    @property
    def var_names(self) -> list[str]:
        return ["P", "V_liq", "Q_in"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        P, V_liq, Q_in = x[0], x[1], x[2]
        dV_liq = dx[1]
        # Clamp V_liq to avoid V_gas ≤ 0
        V_liq_clamped = max(0.0, min(V_liq, self.V0 * 0.9999))
        V_gas = self.V0 - V_liq_clamped
        P_gas = self.P0 * (self.V0 / V_gas) ** self.n
        return [
            dV_liq - Q_in,       # continuity
            P - P_gas,           # polytropic pressure
        ]


class Pump_constant_flow:
    """
    Ideal constant-flow pump.

    Delivers a prescribed volumetric flow Q_set regardless of pressure.
    The pressure rise is determined by the downstream circuit.

    Modelica analogue: Modelica.Fluid.Sources.MassFlowSource_T (analogous)

    Variables (x_local):
      0  P_in  — inlet pressure [Pa]
      1  P_out — outlet pressure [Pa]
      2  Q     — volumetric flow [m³/s]

    Residual:
      Q - Q_set(t)

    Parameters
    ----------
    Q_set : float or callable(t)
        Prescribed flow [m³/s].
    """

    n_vars = 3

    def __init__(self, Q_set=1e-3) -> None:
        self._Q_set = Q_set

    def _get_Q(self, t: float) -> float:
        if callable(self._Q_set):
            return float(self._Q_set(t))
        return float(self._Q_set)

    @property
    def default_x0(self) -> list[float]:
        return [0.0, 1e5, self._get_Q(0.0)]

    @property
    def var_names(self) -> list[str]:
        return ["P_in", "P_out", "Q"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        Q = x[2]
        return [Q - self._get_Q(t)]


# ===========================================================================
# 3. PNEUMATIC
# ===========================================================================


class Pneumatic_cylinder:
    """
    Double-acting pneumatic cylinder.

    Governing equations (quasi-static force balance):
      F_extend  = P_extend  * A_bore - P_retract * A_annulus
      F_retract = P_retract * A_annulus - P_extend * A_bore

    where:
      A_bore    = π/4 * bore²
      A_annulus = π/4 * (bore² - rod²)

    Modelica analogue: Modelica.Mechanics.Translational.Components.Force

    Variables (x_local):
      0  P_extend  — extend-side pressure [Pa]
      1  P_retract — retract-side pressure [Pa]
      2  F_extend  — extension force [N]
      3  F_retract — retraction force [N]

    Residuals:
      F_extend  - (P_extend * A_bore - P_retract * A_annulus)
      F_retract - (P_retract * A_annulus - P_extend * A_bore)

    Parameters
    ----------
    bore : float
        Cylinder bore diameter [m].
    stroke : float
        Maximum stroke [m].  (Informational; does not enter residuals.)
    rod : float
        Piston rod diameter [m].
    P_supply : float
        Nominal supply pressure [Pa].  Used for default_x0.
    """

    n_vars = 4

    def __init__(
        self,
        bore: float,
        stroke: float,
        rod: float,
        P_supply: float = 6e5,
    ) -> None:
        if bore <= 0:
            raise ValueError(f"Pneumatic_cylinder: bore must be > 0, got {bore}")
        if rod >= bore:
            raise ValueError(f"Pneumatic_cylinder: rod must be < bore, got rod={rod} bore={bore}")
        if stroke <= 0:
            raise ValueError(f"Pneumatic_cylinder: stroke must be > 0, got {stroke}")
        self.bore = float(bore)
        self.rod = float(rod)
        self.stroke = float(stroke)
        self.P_supply = float(P_supply)
        self.A_bore = math.pi / 4.0 * bore ** 2
        self.A_annulus = math.pi / 4.0 * (bore ** 2 - rod ** 2)

    @property
    def default_x0(self) -> list[float]:
        F_ext = self.P_supply * self.A_bore - 1e5 * self.A_annulus
        F_ret = self.P_supply * self.A_annulus - 1e5 * self.A_bore
        return [self.P_supply, 1e5, F_ext, F_ret]

    @property
    def var_names(self) -> list[str]:
        return ["P_extend", "P_retract", "F_extend", "F_retract"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        P_e, P_r, F_e, F_r = x[0], x[1], x[2], x[3]
        return [
            F_e - (P_e * self.A_bore - P_r * self.A_annulus),
            F_r - (P_r * self.A_annulus - P_e * self.A_bore),
        ]


# ===========================================================================
# 4. THERMAL-FLUID
# ===========================================================================


class Heat_exchanger_eNTU:
    """
    Counterflow heat exchanger using the ε-NTU method.

    Effectiveness:
      C_min = min(m_dot_h * Cp_h, m_dot_c * Cp_c)
      C_max = max(m_dot_h * Cp_h, m_dot_c * Cp_c)
      C_r   = C_min / C_max
      NTU   = UA / C_min
      ε     = (1 - exp(-NTU*(1-C_r))) / (1 - C_r*exp(-NTU*(1-C_r)))  [counterflow]
      Q_max = C_min * (T_h_in - T_c_in)
      Q     = ε * Q_max

    Outlet temperatures:
      T_h_out = T_h_in - Q / (m_dot_h * Cp_h)
      T_c_out = T_c_in + Q / (m_dot_c * Cp_c)

    Modelica analogue: Modelica.Thermal.HeatTransfer.Components.Convection (aggregated)

    Variables (x_local):
      0  T_h_in  — hot-side inlet temperature [K]
      1  T_c_in  — cold-side inlet temperature [K]
      2  T_h_out — hot-side outlet temperature [K]
      3  T_c_out — cold-side outlet temperature [K]
      4  Q       — heat transfer rate [W]

    Residuals:
      T_h_out - (T_h_in - Q / (m_dot_h * Cp_h))
      T_c_out - (T_c_in + Q / (m_dot_c * Cp_c))
      Q - ε * C_min * (T_h_in - T_c_in)

    Parameters
    ----------
    UA : float
        Overall heat transfer coefficient × area [W/K].
    m_dot_h : float
        Hot-side mass flow rate [kg/s].
    m_dot_c : float
        Cold-side mass flow rate [kg/s].
    Cp_h : float
        Hot-side specific heat [J/(kg·K)].  Default 4186 (water).
    Cp_c : float
        Cold-side specific heat [J/(kg·K)].  Default 4186 (water).
    """

    n_vars = 5

    def __init__(
        self,
        UA: float,
        m_dot_h: float,
        m_dot_c: float,
        Cp_h: float = 4186.0,
        Cp_c: float = 4186.0,
    ) -> None:
        if UA <= 0:
            raise ValueError(f"Heat_exchanger_eNTU: UA must be > 0, got {UA}")
        if m_dot_h <= 0:
            raise ValueError(f"Heat_exchanger_eNTU: m_dot_h must be > 0, got {m_dot_h}")
        if m_dot_c <= 0:
            raise ValueError(f"Heat_exchanger_eNTU: m_dot_c must be > 0, got {m_dot_c}")
        if Cp_h <= 0 or Cp_c <= 0:
            raise ValueError("Heat_exchanger_eNTU: Cp must be > 0")
        self.UA = float(UA)
        self.m_dot_h = float(m_dot_h)
        self.m_dot_c = float(m_dot_c)
        self.Cp_h = float(Cp_h)
        self.Cp_c = float(Cp_c)

        C_h = self.m_dot_h * self.Cp_h
        C_c = self.m_dot_c * self.Cp_c
        self._C_min = min(C_h, C_c)
        self._C_max = max(C_h, C_c)
        self._C_r = self._C_min / self._C_max
        self._NTU = self.UA / self._C_min
        # Counterflow effectiveness
        Cr = self._C_r
        NTU = self._NTU
        if abs(1.0 - Cr) < 1e-8:
            self._eps = NTU / (1.0 + NTU)
        else:
            exp_term = math.exp(-NTU * (1.0 - Cr))
            self._eps = (1.0 - exp_term) / (1.0 - Cr * exp_term)

    @property
    def default_x0(self) -> list[float]:
        return [400.0, 300.0, 380.0, 320.0, 0.0]

    @property
    def var_names(self) -> list[str]:
        return ["T_h_in", "T_c_in", "T_h_out", "T_c_out", "Q"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        T_h_in, T_c_in, T_h_out, T_c_out, Q = (
            x[0], x[1], x[2], x[3], x[4]
        )
        C_h = self.m_dot_h * self.Cp_h
        C_c = self.m_dot_c * self.Cp_c
        Q_expected = self._eps * self._C_min * (T_h_in - T_c_in)
        return [
            T_h_out - (T_h_in - Q / C_h),
            T_c_out - (T_c_in + Q / C_c),
            Q - Q_expected,
        ]


# ===========================================================================
# 5. CONTROL (EXTENDED)
# ===========================================================================


class Lead_lag:
    """
    Lead-lag compensator transfer function.

    G(s) = (T_lead * s + 1) / (T_lag * s + 1)

    State-space realisation:
      T_lag * dx_f/dt + x_f = u
      y = x_f + T_lead * dx_f/dt
        = x_f + (T_lead / T_lag) * (u - x_f)

    Residuals:
      T_lag * d(x_f)/dt + x_f - u
      y - x_f - (T_lead / T_lag) * (u - x_f)

    Modelica analogue: Modelica.Blocks.Continuous.LeadLag

    Variables (x_local):
      0  u   — input signal
      1  x_f — lag filter state
      2  y   — output signal

    Parameters
    ----------
    T_lead : float
        Lead time constant [s].
    T_lag : float
        Lag time constant [s].
    """

    n_vars = 3

    def __init__(self, T_lead: float, T_lag: float) -> None:
        if T_lag <= 0:
            raise ValueError(f"Lead_lag: T_lag must be > 0, got {T_lag}")
        if T_lead < 0:
            raise ValueError(f"Lead_lag: T_lead must be >= 0, got {T_lead}")
        self.T_lead = float(T_lead)
        self.T_lag = float(T_lag)

    @property
    def default_x0(self) -> list[float]:
        return [0.0, 0.0, 0.0]

    @property
    def var_names(self) -> list[str]:
        return ["u", "x_f", "y"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        u, x_f, y = x[0], x[1], x[2]
        dx_f = dx[1]
        ratio = self.T_lead / self.T_lag
        return [
            self.T_lag * dx_f + x_f - u,
            y - x_f - ratio * (u - x_f),
        ]


class Deadband:
    """
    Deadband element (algebraic).

    y = 0                    if |u| <= band/2
    y = u - band/2 * sign(u) otherwise

    Modelica analogue: Modelica.Blocks.Nonlinear.DeadZone

    Implemented with smooth approximation to avoid discontinuity:
      d = band/2
      y = u - d * tanh(u/d)   [smooth version; exact in limits]

    Variables (x_local):
      0  u — input
      1  y — output

    Residual:
      y - (u - (band/2) * tanh(u / (band/2 + eps)))

    Parameters
    ----------
    band : float
        Total deadband width [same units as signal].
    """

    n_vars = 2

    def __init__(self, band: float) -> None:
        if band < 0:
            raise ValueError(f"Deadband: band must be >= 0, got {band}")
        self.band = float(band)

    @property
    def default_x0(self) -> list[float]:
        return [0.0, 0.0]

    @property
    def var_names(self) -> list[str]:
        return ["u", "y"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        u, y = x[0], x[1]
        d = self.band / 2.0
        eps = 1e-9
        y_expected = u - d * math.tanh(u / (d + eps))
        return [y - y_expected]


class Saturation:
    """
    Static saturation (clamp) element.

    y = max(lower, min(upper, u))

    Smooth version using softclip:
      y ≈ lower + (upper-lower) * sigmoid((u - lower) / smoothing)
            — but this shifts the slope.

    We use a two-sided smooth clamp:
      y = lower + 0.5*(upper-lower)*(1 + tanh((2*u - upper - lower)
                                              / (upper - lower + eps)))

    Modelica analogue: Modelica.Blocks.Nonlinear.Limiter

    Variables (x_local):
      0  u — input
      1  y — output

    Parameters
    ----------
    lower : float
        Lower saturation limit.
    upper : float
        Upper saturation limit.
    """

    n_vars = 2

    def __init__(self, lower: float, upper: float) -> None:
        if lower >= upper:
            raise ValueError(
                f"Saturation: lower must be < upper, got lower={lower} upper={upper}"
            )
        self.lower = float(lower)
        self.upper = float(upper)

    @property
    def default_x0(self) -> list[float]:
        return [0.0, 0.0]

    @property
    def var_names(self) -> list[str]:
        return ["u", "y"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        u, y = x[0], x[1]
        span = self.upper - self.lower
        mid = 0.5 * (self.upper + self.lower)
        # Smooth symmetric clamp via tanh
        y_expected = mid + 0.5 * span * math.tanh((u - mid) / (0.5 * span))
        return [y - y_expected]


class Rate_limiter:
    """
    Rate limiter (slew-rate limiter).

    Limits dy/dt to [-slew_max, +slew_max].

    In continuous DAE form, the unconstrained derivative is projected:
      dy/dt = clamp(du/dt, -slew_max, +slew_max)

    Implemented as an ODE:
      dy/dt = slew_max * tanh((du/dt) / slew_max)

    which gives the smooth saturation of the derivative.

    Modelica analogue: Modelica.Blocks.Nonlinear.SlewRateLimiter

    Variables (x_local):
      0  u — input signal
      1  y — rate-limited output

    Residual:
      dy/dt - slew_max * tanh((du/dt) / slew_max)

    Parameters
    ----------
    slew_max : float
        Maximum rate of change per second (must be > 0).
    y0 : float
        Initial output value.  Default 0.
    """

    n_vars = 2

    def __init__(self, slew_max: float, y0: float = 0.0) -> None:
        if slew_max <= 0:
            raise ValueError(f"Rate_limiter: slew_max must be > 0, got {slew_max}")
        self.slew_max = float(slew_max)
        self.y0 = float(y0)

    @property
    def default_x0(self) -> list[float]:
        return [0.0, self.y0]

    @property
    def var_names(self) -> list[str]:
        return ["u", "y"]

    def residuals(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        du, dy = dx[0], dx[1]
        clamped_rate = self.slew_max * math.tanh(du / self.slew_max)
        return [dy - clamped_rate]


# ===========================================================================
# Registry helpers for LLM tool instantiation
# ===========================================================================

_COMPONENT_REGISTRY: dict[str, type] = {
    # Mechanical
    "Mass": Mass,
    "Spring": Spring,
    "Damper": Damper,
    "Lever": Lever,
    "Gear": Gear,
    "Bearing": Bearing,
    # Hydraulic
    "Orifice": Orifice,
    "Valve": Valve,
    "Accumulator": Accumulator,
    "Pump_constant_flow": Pump_constant_flow,
    # Pneumatic
    "Pneumatic_cylinder": Pneumatic_cylinder,
    # Thermal-fluid
    "Heat_exchanger_eNTU": Heat_exchanger_eNTU,
    # Control
    "Lead_lag": Lead_lag,
    "Deadband": Deadband,
    "Saturation": Saturation,
    "Rate_limiter": Rate_limiter,
}


def list_extended_components() -> list[str]:
    """Return names of all extended components."""
    return sorted(_COMPONENT_REGISTRY)


def instantiate_component(name: str, **kwargs):
    """
    Instantiate an extended component by name.

    Parameters
    ----------
    name : str
        Component class name (see list_extended_components()).
    **kwargs
        Constructor keyword arguments.

    Returns
    -------
    component instance

    Raises
    ------
    KeyError
        If ``name`` is not a known extended component.
    """
    if name not in _COMPONENT_REGISTRY:
        raise KeyError(
            f"Unknown extended component {name!r}.  "
            f"Available: {sorted(_COMPONENT_REGISTRY)}"
        )
    return _COMPONENT_REGISTRY[name](**kwargs)


__all__ = [
    "Mass",
    "Spring",
    "Damper",
    "Lever",
    "Gear",
    "Bearing",
    "Orifice",
    "Valve",
    "Accumulator",
    "Pump_constant_flow",
    "Pneumatic_cylinder",
    "Heat_exchanger_eNTU",
    "Lead_lag",
    "Deadband",
    "Saturation",
    "Rate_limiter",
    "list_extended_components",
    "instantiate_component",
]
