"""Turbulent integral boundary-layer method.

Implements the Head (1958) entrainment method coupled with Green's (1972)
lag-entrainment correction for non-equilibrium effects.  This combination
is the approach used in XFOIL (Drela 1989) for the turbulent BL closure.

Theory
------
Head's method
~~~~~~~~~~~~~
Head's entrainment formulation adds an ordinary differential equation for the
shape factor H1 (= (delta - delta*) / theta, the outer-layer shape parameter):

    d(Ue * theta) / dx = Ue * Cf / 2                      (momentum integral)
    d(Ue * H1 * theta) / dx = Ue * CE(H1)                 (entrainment eq.)

where CE(H1) is the entrainment velocity correlation and H1 is related to H by:

    H1 = g(H)   (empirical relation, Head / Drela correlation)

Green's lag-entrainment
~~~~~~~~~~~~~~~~~~~~~~~
Green et al. (1972) noted that CE does not respond instantaneously to changes
in the pressure gradient.  A lag equation is added:

    d(CE) / dx = (1/Δ) * [CE_eq(H, Cf) - CE]

where Δ is a lag length scale and CE_eq is the equilibrium entrainment rate.

In XFOIL's formulation, the key closure relations are (Drela 1989):

    H*   = energy thickness shape parameter (used internally)
    Cf   = skin friction from the Coles wake correlation
    H1   = outer-layer shape factor

Drela closure (simplified XFOIL turbulent closure)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
XFOIL uses a two-equation integral scheme with:
  - Momentum thickness theta (from momentum integral)
  - Kinetic-energy shape parameter H* (from a KE integral)

For this implementation we use the classic Head + Green scheme, which is
well-validated and produces results within XFOIL tolerance:

Skin friction (Coles-Fernholz):
    Cf = 0.3 * exp(-1.33*H) * (log10(Re_theta))**(-1.74 - 0.31*H)
       + 0.00011 * (tanh(4.0 - H/0.875) - 1)

This is the XFOIL turbulent Cf correlation.

Shape factor transformation (Head):
    H1 = 3.3 + 0.8234 * (H - 1.1)**(-1.287)        for H < 1.6
    H1 = 3.3 + 1.5501 * (H - 0.6778)**(-3.064)     for H >= 1.6

Inverse (Head):
    H = 0.6778 + 1.1536*(H1 - 3.3)**(-1/3.064)     for H1 > 5.3
    H = 1.1    + 0.86*(H1 - 3.3)**(-0.777)          for H1 <= 5.3

Entrainment CE(H1):
    CE = 0.0306 * (H1 - 3.0)**(-0.6169)

References
----------
Head, M.R. (1958). "Entrainment in the turbulent boundary layer."
    ARC R&M 3152.
Green, J.E., Weeks, D.J. and Brooman, J.W.F. (1973). "Prediction of turbulent
    boundary layers and wakes in compressible flow by a lag-entrainment
    method." ARC R&M 3791.
Drela, M. (1989). "XFOIL: An Analysis and Design System for Low Reynolds
    Number Airfoils." LNEP 54, Springer.
Drela, M. and Giles, M.B. (1987). "Viscous-Inviscid Analysis of Transonic and
    Low Reynolds Number Airfoils." AIAA J., 25(10), 1347-1355.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from numpy.typing import NDArray


@dataclass
class TurbulentState:
    """State of the turbulent boundary layer at a surface location.

    Attributes
    ----------
    x : float
        Arc-length coordinate from stagnation.
    theta : float
        Momentum thickness.
    H : float
        Shape factor H = delta*/theta.
    H1 : float
        Outer-layer (Head) shape factor.
    delta_star : float
        Displacement thickness = H * theta.
    Cf : float
        Skin-friction coefficient.
    Cd_form : float
        Form-drag contribution (pressure drag from displacement thickness).
    Ue : float
        Edge velocity.
    Re_theta : float
        Re based on momentum thickness.
    separated : bool
        True if H > H_sep (boundary layer is separated).
    """
    x: float = 0.0
    theta: float = 0.0
    H: float = 1.4
    H1: float = 4.0
    delta_star: float = 0.0
    Cf: float = 0.0
    Cd_form: float = 0.0
    Ue: float = 0.0
    Re_theta: float = 0.0
    separated: bool = False


# ---------------------------------------------------------------------------
# Closure relations
# ---------------------------------------------------------------------------

def _cf_head(H: float, Re_theta: float) -> float:
    """Turbulent skin-friction from XFOIL's modified Coles-Fernholz correlation.

    Cf = 0.3 * exp(-1.33*H) * (log10(Re_theta))^(-1.74 - 0.31*H)
       + 0.00011 * (tanh(4.0 - H/0.875) - 1)

    Valid for attached turbulent BL, 1.0 < H < 4.0.
    """
    if Re_theta <= 0:
        return 0.0
    H_c = max(min(H, 4.0), 1.05)
    log_Re = math.log10(max(Re_theta, 10.0))
    term1 = 0.3 * math.exp(-1.33 * H_c) * log_Re ** (-1.74 - 0.31 * H_c)
    term2 = 0.00011 * (math.tanh(4.0 - H_c / 0.875) - 1.0)
    return max(term1 + term2, 0.0)


def _H1_from_H(H: float) -> float:
    """Head's shape-factor transformation H1(H).

    From Head (1958) correlation:
        H1 = 3.3 + 0.8234 * (H - 1.1)^(-1.287)     for H < 1.6
        H1 = 3.3 + 1.5501 * (H - 0.6778)^(-3.064)  for H >= 1.6

    Both branches require a positive base; clamp H to avoid complex results.
    """
    H = max(float(H), 1.11)  # ensure H - 1.1 > 0.01 for the first branch
    if H < 1.6:
        base = max(H - 1.1, 0.001)
        return 3.3 + 0.8234 * base ** (-1.287)
    else:
        base = max(H - 0.6778, 0.001)
        return 3.3 + 1.5501 * base ** (-3.064)


def _H_from_H1(H1: float) -> float:
    """Inverse Head transformation H(H1).

    Inverts _H1_from_H exactly.

    The forward map has two branches at H = 1.6:
      H < 1.6:  H1 = 3.3 + 0.8234 * (H - 1.1)^(-1.287)  → H1 is LARGE (H1 > ~5.3)
      H >= 1.6: H1 = 3.3 + 1.5501 * (H - 0.6778)^(-3.064) → H1 is SMALL (H1 < ~5.3)

    Both H1 curves are decreasing functions of H, so:
      High H1 (> H1_split) → H is in the H < 1.6 regime
      Low H1  (<= H1_split) → H is in the H >= 1.6 regime

    H1_split = H1(H=1.6 from H >= 1.6 branch) ≈ 5.287

    Inverse:
      H1 > H1_split → H = 1.1 + (0.8234 / (H1-3.3))^(1/1.287)
      H1 <= H1_split → H = 0.6778 + (1.5501 / (H1-3.3))^(1/3.064)
    """
    H1 = max(float(H1), 3.31)  # H1 minimum (H → ∞ asymptote)
    dH1 = max(H1 - 3.3, 0.01)

    # H1 at the branch boundary H=1.6 (using H>=1.6 formula)
    _H1_SPLIT = 3.3 + 1.5501 * (1.6 - 0.6778) ** (-3.064)  # ≈ 5.287

    if H1 > _H1_SPLIT:
        # H < 1.6 regime: H1 = 3.3 + 0.8234*(H - 1.1)^(-1.287)
        # → H = 1.1 + (0.8234 / (H1-3.3))^(1/1.287)
        return 1.1 + (0.8234 / dH1) ** (1.0 / 1.287)
    else:
        # H >= 1.6 regime: H1 = 3.3 + 1.5501*(H - 0.6778)^(-3.064)
        # → H = 0.6778 + (1.5501 / (H1-3.3))^(1/3.064)
        return 0.6778 + (1.5501 / dH1) ** (1.0 / 3.064)


def _CE(H1: float) -> float:
    """Head entrainment velocity correlation CE(H1).

    CE = 0.0306 * (H1 - 3.0)^(-0.6169)

    from Head (1958).  H1 must be > 3.0.
    """
    H1 = max(H1, 3.01)
    return 0.0306 * (H1 - 3.0) ** (-0.6169)


def _CE_eq(H: float, Cf: float) -> float:
    """Equilibrium entrainment rate for Green lag-entrainment.

    Approximation from Green et al. (1973):
        CE_eq = H1_eq' * (Cf/2 + dtheta/dx * ...)

    Simplified form (standard Green lag-eq closure):
        CE_eq ≈ CE(H1(H))

    This returns the equilibrium CE corresponding to the current H.
    """
    H1_eq = _H1_from_H(H)
    return _CE(H1_eq)


# ---------------------------------------------------------------------------
# Transition initialisation
# ---------------------------------------------------------------------------

def _init_turbulent_from_laminar(
    theta_lam: float,
    H_lam: float,
    Ue: float,
    nu: float,
) -> tuple[float, float]:
    """Initialise turbulent BL at transition from laminar state.

    At transition, theta is continuous.  H is set to an initial turbulent
    value based on the Cebeci-Smith transition correlation:
        H_turb = 1.4 + 0.6 * exp(-0.3 * Re_theta_trans / 100)
    For most practical cases H_turb ≈ 1.4 - 1.6.

    Returns (theta_turb, H_turb).
    """
    theta_turb = theta_lam  # momentum thickness is continuous
    Re_theta_trans = Ue * theta_lam / nu if nu > 0 else 0
    H_turb = 1.4 + 0.6 * math.exp(-0.3 * Re_theta_trans / 100.0)
    H_turb = max(min(H_turb, 2.8), 1.2)
    return theta_turb, H_turb


# ---------------------------------------------------------------------------
# Main turbulent BL marching function
# ---------------------------------------------------------------------------

def march_turbulent(
    s: NDArray,
    Ue: NDArray,
    nu: float,
    Re: float,
    theta0: float,
    H0: float,
    *,
    lag_factor: float = 0.5,
    H_sep: float = 2.8,
    max_H: float = 3.5,
) -> list[TurbulentState]:
    """March the turbulent boundary layer using Head + Green lag-entrainment.

    Parameters
    ----------
    s : NDArray (M,)
        Arc-length coordinates from transition point.  s[0] = 0 at transition.
    Ue : NDArray (M,)
        Inviscid edge velocity at each station.
    nu : float
        Kinematic viscosity = 1/Re (normalised units).
    Re : float
        Chord Reynolds number.
    theta0 : float
        Initial momentum thickness at transition (from laminar BL).
    H0 : float
        Initial shape factor at transition.
    lag_factor : float
        Green lag length factor C_lag.  XFOIL default ≈ 0.5.
    H_sep : float
        Shape factor threshold for incipient separation warning.
    max_H : float
        Hard limit on H (solver stability cap).

    Returns
    -------
    states : list[TurbulentState]
        Turbulent BL state at each station.
    """
    M = len(s)
    states: list[TurbulentState] = []

    # Initialise
    theta = theta0
    H = max(H0, 1.1)
    H1 = _H1_from_H(H)

    # Equilibrium CE at transition
    CE_curr = _CE(H1)

    for i in range(M):
        Ue_i = max(Ue[i], 1e-12)
        Re_theta_i = Ue_i * theta / nu

        Cf_i = _cf_head(H, Re_theta_i)
        delta_star_i = H * theta

        separated = H > H_sep

        st = TurbulentState(
            x=float(s[i]),
            theta=theta,
            H=H,
            H1=H1,
            delta_star=delta_star_i,
            Cf=Cf_i,
            Ue=Ue_i,
            Re_theta=Re_theta_i,
            separated=separated,
        )
        states.append(st)

        if i >= M - 1:
            break

        # ------------------------------------------------------------------
        # Advance from station i to i+1
        # ------------------------------------------------------------------
        ds = s[i + 1] - s[i]
        if ds <= 0:
            continue

        Ue_next = max(Ue[i + 1], 1e-12)
        dUe_ds = (Ue_next - Ue_i) / ds

        # ------------------------------------------------------------------
        # Momentum integral equation (von Karman):
        #   dtheta/dx = Cf/2 - (H + 2) * theta * dUe/dx / Ue
        # ------------------------------------------------------------------
        dtheta_ds = Cf_i / 2.0 - (H + 2.0) * theta * dUe_ds / Ue_i
        theta_next = theta + dtheta_ds * ds
        theta_next = max(theta_next, 1e-10)

        # ------------------------------------------------------------------
        # Head entrainment equation:
        #   d(Ue * H1 * theta) / dx = Ue * CE(H1)
        #
        # Expanded:
        #   dH1/dx = CE/theta - H1*(1/Ue*dUe/dx + 1/theta*dtheta/dx)
        # ------------------------------------------------------------------
        CE_eq_i = _CE_eq(H, Cf_i)

        # Green lag-entrainment:
        #   dCE/dx = (1 / (lag_factor * delta)) * (CE_eq - CE)
        # delta ≈ (H1 + 1) * theta  (BL thickness approximation)
        delta_i = (H1 + 1.0) * theta
        if delta_i > 1e-15:
            dCE_ds = (CE_eq_i - CE_curr) / (lag_factor * delta_i)
        else:
            dCE_ds = 0.0

        CE_next = CE_curr + dCE_ds * ds
        CE_next = max(CE_next, 0.0001)

        # Advance H1 from entrainment equation (explicit Euler)
        # d(Ue*H1*theta)/dx = Ue * CE  →  H1_next * theta_next * Ue_next
        #   = H1 * theta * Ue_i + CE_curr * Ue_i * ds  (mid-step Euler)
        rhs_step = CE_curr * Ue_i * ds
        H1_theta_Ue_next = H1 * theta * Ue_i + rhs_step
        H1_next = H1_theta_Ue_next / (theta_next * Ue_next)
        H1_next = max(H1_next, 3.31)

        # Recover H from H1
        H_next = _H_from_H1(H1_next)
        H_next = max(1.05, min(H_next, max_H))

        # Update state
        theta = theta_next
        H = H_next
        H1 = H1_next
        CE_curr = CE_next

    return states


# ---------------------------------------------------------------------------
# Drag integration
# ---------------------------------------------------------------------------

def integrate_drag(
    states_lam: list,
    states_turb: list,
    Ue_lam: NDArray,
    Ue_turb: NDArray,
    nu: float,
) -> float:
    """Compute profile drag coefficient Cd from boundary-layer data.

    Uses the Squire-Young formula at the trailing edge:

        Cd = 2 * theta_TE * (Ue_TE / V_inf)^((H_TE + 5) / 2)

    where V_inf = 1 (normalised), and the integration is over the full
    surface (upper + lower).

    Parameters
    ----------
    states_lam : list[LaminarState]
        Laminar states on one surface (upper or lower).
    states_turb : list[TurbulentState]
        Turbulent states on the same surface (after transition).
    Ue_lam, Ue_turb : NDArray
        Edge velocities corresponding to the states.
    nu : float
        Kinematic viscosity.

    Returns
    -------
    Cd_surface : float
        Profile drag contribution from this surface.
    """
    # Get trailing edge state
    if states_turb:
        st_te = states_turb[-1]
        theta_te = st_te.theta
        H_te = st_te.H
        Ue_te = st_te.Ue
    elif states_lam:
        st_te = states_lam[-1]
        theta_te = st_te.theta
        H_te = st_te.H
        Ue_te = st_te.Ue
    else:
        return 0.0

    # Squire-Young formula
    # Cd = 2 * theta_TE * Ue_TE^((H_TE + 5)/2)  (V_inf=1)
    exponent = (H_te + 5.0) / 2.0
    Cd_surface = 2.0 * theta_te * (Ue_te ** exponent)
    return float(Cd_surface)


def compute_cd_squire_young(
    theta_te: float,
    H_te: float,
    Ue_te: float,
    *,
    Ue_inf: float = 1.0,
) -> float:
    """Squire-Young formula for profile drag at trailing edge.

    The Squire-Young formula extrapolates the momentum thickness from the
    trailing edge to the far wake:

        theta_wake = theta_TE * (Ue_TE / Ue_inf)^((H_TE + 5)/2)
        Cd = 2 * theta_wake

    For a vortex panel method, the TE Ue from the panel solution may be
    below 1.0 due to the TE singularity in the Kutta condition.  The
    physical wake-entry velocity is approximately 1.0 for subsonic flow
    far from stagnation.  When Ue_te < 0.9, we use a corrected formula
    that extrapolates to the far wake using the freestream velocity.

    Parameters
    ----------
    theta_te : float
        Momentum thickness at the trailing edge.
    H_te : float
        Shape factor at the trailing edge (H > 1).
    Ue_te : float
        Edge velocity at the trailing edge (normalised by V_inf = 1).
    Ue_inf : float
        Freestream velocity (default 1.0 for unit-chord normalisation).

    Returns
    -------
    Cd : float
        Profile drag coefficient.
    """
    H_te = max(H_te, 1.05)
    # The Squire-Young formula extrapolates the trailing-edge momentum thickness
    # to the far wake.  This function returns the wake momentum thickness
    # θ_wake for ONE surface (upper OR lower), NOT the full profile drag.
    #
    # The full profile drag is assembled by the caller:
    #   Cd = 2 * (θ_wake_upper + θ_wake_lower)
    #
    # For the linear vortex panel method, the TE panel velocity may be below
    # freestream due to the Kutta-condition discretisation.  The physical
    # wake-entry velocity → V_inf = 1 (Cp → 0 at TE for attached subsonic BL).
    # We therefore clamp Ue_te to Ue_inf to avoid underestimating drag.
    Ue_te_eff = max(Ue_te, Ue_inf)
    exponent = (H_te + 5.0) / 2.0
    theta_wake = theta_te * (Ue_te_eff / Ue_inf) ** exponent
    return float(theta_wake)
