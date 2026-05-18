"""
kerf_1dsim.components
=====================

Standard 1-D lumped-element components.  Each class follows the convention:

    equations(t, x, dx) -> list[float]

where:
  t   — current time  [s]
  x   — state / algebraic variable vector   (list or tuple)
  dx  — derivative vector (same shape; may be zeros for algebraic vars)

The returned list contains residual values F_i such that the system is
satisfied when every F_i == 0.

Variable ordering per component is documented in each class docstring.

Modelica domain correspondence
-------------------------------
  Resistor          — Modelica.Electrical.Analog.Basic.Resistor
  Capacitor         — Modelica.Electrical.Analog.Basic.Capacitor
  Inductor          — Modelica.Electrical.Analog.Basic.Inductor
  MassSpring        — Modelica.Mechanics.Translational.Components.Mass +
                      Modelica.Mechanics.Translational.Components.Spring
  Damper            — Modelica.Mechanics.Translational.Components.Damper
  ThermalConductor  — Modelica.Thermal.HeatTransfer.Components.ThermalConductor
  FluidResistor     — Modelica.Fluid pipe resistance (linearised)
"""

from __future__ import annotations

import math
from typing import Sequence


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class Component:
    """Abstract base for a lumped 1-D component."""

    #: Number of state / algebraic variables owned by this component.
    n_vars: int = 0

    def equations(
        self,
        t: float,
        x: Sequence[float],
        dx: Sequence[float],
    ) -> list[float]:
        """Return residual vector.  Override in subclasses."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Electrical
# ---------------------------------------------------------------------------

class Resistor(Component):
    """
    Ideal resistor — Ohm's law.

    Variables (x):
      0  v   — voltage across resistor [V]
      1  i   — current through resistor [A]

    Equations:
      v - R*i == 0
      (current continuity — provided by network assembly)

    Parameters
    ----------
    R : float
        Resistance [Ohm]
    """

    n_vars = 2

    def __init__(self, R: float) -> None:
        if R <= 0:
            raise ValueError(f"Resistor: R must be > 0, got {R}")
        self.R = float(R)

    def equations(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        v, i = x[0], x[1]
        # Ohm's law residual
        return [v - self.R * i]


class Capacitor(Component):
    """
    Ideal capacitor — C dv/dt = i.

    Variables (x):
      0  v   — voltage [V]
      1  i   — current [A]

    Equations:
      C * dv/dt - i == 0

    Parameters
    ----------
    C : float
        Capacitance [F]
    """

    n_vars = 2

    def __init__(self, C: float) -> None:
        if C <= 0:
            raise ValueError(f"Capacitor: C must be > 0, got {C}")
        self.C = float(C)

    def equations(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        v, i = x[0], x[1]
        dv = dx[0]
        # Differential residual: C*dv/dt - i = 0
        return [self.C * dv - i]


class Inductor(Component):
    """
    Ideal inductor — L di/dt = v.

    Variables (x):
      0  v   — voltage [V]
      1  i   — current [A]

    Equations:
      L * di/dt - v == 0

    Parameters
    ----------
    L : float
        Inductance [H]
    """

    n_vars = 2

    def __init__(self, L: float) -> None:
        if L <= 0:
            raise ValueError(f"Inductor: L must be > 0, got {L}")
        self.L = float(L)

    def equations(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        v, i = x[0], x[1]
        di = dx[1]
        # L*di/dt - v = 0
        return [self.L * di - v]


# ---------------------------------------------------------------------------
# Mechanical (translational)
# ---------------------------------------------------------------------------

class MassSpring(Component):
    """
    Lumped mass on a spring — second-order ODE.

    State variables (x):
      0  q   — displacement from natural length [m]
      1  v   — velocity [m/s]

    Derivative variables (dx):
      0  dq  — dq/dt == v  (kinematic constraint)
      1  dv  — dv/dt == acceleration

    Equations:
      dq - v == 0                     (kinematics)
      m * dv + k * q - F_ext == 0     (Newton 2nd law)

    Parameters
    ----------
    m : float
        Mass [kg]
    k : float
        Spring stiffness [N/m]
    F_ext : float or callable(t) -> float
        External force [N].  Default 0.
    """

    n_vars = 2

    def __init__(self, m: float, k: float, F_ext=0.0) -> None:
        if m <= 0:
            raise ValueError(f"MassSpring: m must be > 0, got {m}")
        if k <= 0:
            raise ValueError(f"MassSpring: k must be > 0, got {k}")
        self.m = float(m)
        self.k = float(k)
        self._F_ext = F_ext

    def _force(self, t: float) -> float:
        if callable(self._F_ext):
            return float(self._F_ext(t))
        return float(self._F_ext)

    def equations(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        q, v = x[0], x[1]
        dq, dv = dx[0], dx[1]
        F = self._force(t)
        return [
            dq - v,                        # kinematic consistency
            self.m * dv + self.k * q - F,  # Newton
        ]


class Damper(Component):
    """
    Viscous damper (dashpot).

    State variables (x):
      0  v_rel — relative velocity across damper [m/s]
      1  F_d   — damper force [N]

    Equations:
      F_d - b * v_rel == 0

    Parameters
    ----------
    b : float
        Damping coefficient [N·s/m]
    """

    n_vars = 2

    def __init__(self, b: float) -> None:
        if b <= 0:
            raise ValueError(f"Damper: b must be > 0, got {b}")
        self.b = float(b)

    def equations(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        v_rel, F_d = x[0], x[1]
        return [F_d - self.b * v_rel]


# ---------------------------------------------------------------------------
# Thermal
# ---------------------------------------------------------------------------

class ThermalConductor(Component):
    """
    Lumped thermal conductor (Fourier law).

    Variables (x):
      0  T_a  — temperature at port A [K or °C]
      1  T_b  — temperature at port B [K or °C]
      2  Q    — heat flow from A to B [W]

    Equations:
      Q - G * (T_a - T_b) == 0

    Parameters
    ----------
    G : float
        Thermal conductance [W/K]  (= k * A / L  for a slab)
    """

    n_vars = 3

    def __init__(self, G: float) -> None:
        if G <= 0:
            raise ValueError(f"ThermalConductor: G must be > 0, got {G}")
        self.G = float(G)

    def equations(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        T_a, T_b, Q = x[0], x[1], x[2]
        return [Q - self.G * (T_a - T_b)]


# ---------------------------------------------------------------------------
# Fluid
# ---------------------------------------------------------------------------

class FluidResistor(Component):
    """
    Linearised fluid resistance (Hagen-Poiseuille approximation).

    Variables (x):
      0  p_in  — inlet pressure [Pa]
      1  p_out — outlet pressure [Pa]
      2  q     — volumetric flow rate [m³/s]

    Equations:
      q - (p_in - p_out) / Rf == 0

    Parameters
    ----------
    Rf : float
        Fluid resistance [Pa·s/m³]
    """

    n_vars = 3

    def __init__(self, Rf: float) -> None:
        if Rf <= 0:
            raise ValueError(f"FluidResistor: Rf must be > 0, got {Rf}")
        self.Rf = float(Rf)

    def equations(self, t: float, x: Sequence[float], dx: Sequence[float]) -> list[float]:
        p_in, p_out, q = x[0], x[1], x[2]
        return [q - (p_in - p_out) / self.Rf]
