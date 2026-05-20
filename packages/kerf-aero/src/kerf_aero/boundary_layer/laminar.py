"""Laminar integral boundary-layer method (Thwaites / Falkner-Skan correlation).

Theory
------
Thwaites (1949) momentum-integral method gives an exact quadrature for the
laminar momentum thickness theta and a correlation for the shape factor H:

    d(theta^2 * Ue^6)/dx = 0.45 * nu * Ue^5          (Thwaites integral)

Integrating from the stagnation point (theta=0):

    theta^2 = (0.45 * nu / Ue^6) * integral_0^x Ue^5 ds

The shape factor correlation (Head / Drela form):

    lambda = (theta^2 / nu) * dUe/dx

Falkner-Skan shape-factor correlation:
    l(lambda) = (0.22 + 1.57*lambda - 1.8*lambda^2)   ... Thwaites l-fn
    H(lambda) from tabulated Falkner-Skan solutions

The displacement thickness is:
    delta_star = H * theta

Separation criterion: lambda < -0.09  (Thwaites criterion)

References
----------
Thwaites, B. (1949). "Approximate calculation of the laminar boundary layer."
    Aeronautical Quarterly, 1, 245-280.
Drela, M. (1989). XFOIL documentation.
White, F.M. (2006). Viscous Fluid Flow, 3rd ed., Chapter 4.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from numpy.typing import NDArray


@dataclass
class LaminarState:
    """State of the laminar boundary layer at a surface location.

    Attributes
    ----------
    x : float
        Arc-length coordinate from stagnation (m or normalised).
    theta : float
        Momentum thickness.
    H : float
        Shape factor H = delta*/theta.
    delta_star : float
        Displacement thickness = H * theta.
    Cf : float
        Skin-friction coefficient.
    Ue : float
        Edge velocity (inviscid).
    Re_theta : float
        Reynolds number based on momentum thickness.
    n_ts : float
        Accumulated Tollmien-Schlichting amplification factor (for e^N).
    """
    x: float = 0.0
    theta: float = 0.0
    H: float = 2.6
    delta_star: float = 0.0
    Cf: float = 0.0
    Ue: float = 0.0
    Re_theta: float = 0.0
    n_ts: float = 0.0


def _thwaites_H(lam: float) -> float:
    """Shape factor H(lambda) from Thwaites correlation.

    Uses the standard polynomial fit from White (2006) / Drela notes.
    lambda is the Thwaites pressure-gradient parameter:
        lambda = (theta^2 / nu) * dUe/dx
    """
    # Clamp to physically valid range
    lam = max(-0.09, min(0.25, lam))

    if lam >= 0.0:
        # Attached flow, mild adverse or favourable gradient
        H = 2.61 - 3.75 * lam + 5.24 * lam**2
    else:
        # Adverse gradient
        H = 2.088 + 0.0731 / (lam + 0.14)

    return max(H, 1.05)


def _thwaites_l(lam: float) -> float:
    """Thwaites shear-correlation function l(lambda).

    l(lambda) = (theta/tau_w) * (mu * dUe/dx + ...) approximation.
    Used for skin friction: Cf = 2*l / Re_theta
    """
    lam = max(-0.09, min(0.25, lam))
    # Standard Thwaites correlation
    return 0.22 + 1.57 * lam - 1.8 * lam**2


def _n_amplification_rate(Re_theta: float, H: float) -> float:
    """e^N amplification rate dn/ds in Drela's simplified form.

    Michel's criterion modified by Drela (XFOIL):
        dn/d(log Re_theta) = f(H)

    Uses the Drela envelope-method correlation:
        dN/d(theta) based on the Ory-Drela approximation:
        dN/d(Re_theta) = max(0, (1/(3.3+1.1*H)) *
                         (1.1*H^2.1 - 1/(H-1)) * ln(1.1*H^2.1*(H-1)))

    Actually using the standard simplified Drela form from XFOIL source:
        dN/d(log Re_theta) = (1.415/(H-1) - 0.489) * tanh(20/(H-1) - 12.9)
                            + (3.295/(H-1) + 0.44)
    """
    if H <= 1.05:
        return 0.0
    Hm1 = H - 1.0

    # Drela's envelope-method correlation (XFOIL notation)
    dn_dlnRe = ((1.415 / Hm1 - 0.489) * math.tanh(20.0 / Hm1 - 12.9)
                + 3.295 / Hm1 + 0.44)

    # Convert to dn/d(Re_theta): dn/d(Re_theta) = dn/d(lnRe_theta) / Re_theta
    if Re_theta <= 0:
        return 0.0
    return max(0.0, dn_dlnRe) / Re_theta


def _initial_theta(Ue_stag: float, dUe_dx_stag: float, nu: float) -> float:
    """Stagnation-point initial momentum thickness from Hiemenz solution.

    At a stagnation point, dUe/dx = k (constant), and the Falkner-Skan
    solution for beta=1 gives:
        theta = 0.2924 * sqrt(nu / k)
    """
    k = abs(dUe_dx_stag)
    if k < 1e-15:
        return 1e-6
    return 0.2924 * math.sqrt(nu / k)


def march_laminar(
    s: NDArray,
    Ue: NDArray,
    nu: float,
    Re: float,
    *,
    n_crit: float = 9.0,
) -> tuple[list[LaminarState], int]:
    """March the laminar boundary layer from stagnation to transition/separation.

    Parameters
    ----------
    s : NDArray (M,)
        Arc-length coordinates along the surface (0 at stagnation, increasing
        downstream). Must be monotonically increasing.
    Ue : NDArray (M,)
        Edge (inviscid) velocity at each station. Ue[0] ~ 0 at stagnation.
    nu : float
        Kinematic viscosity = 1/Re (with chord = 1 normalised).
    Re : float
        Chord Reynolds number (used for Re_theta).
    n_crit : float
        Critical N factor for transition (default 9 for clean wind tunnel).

    Returns
    -------
    states : list[LaminarState]
        BL state at each marching station up to transition/separation.
    i_trans : int
        Index in *s* where transition was detected (-1 if not triggered).
    """
    M = len(s)
    states: list[LaminarState] = []
    i_trans = -1

    # ------------------------------------------------------------------
    # Thwaites integral: theta^2 = (0.45*nu/Ue^6) * integral_0^x Ue^5 ds
    # We integrate numerically using the trapezoidal rule.
    # ------------------------------------------------------------------

    # Handle stagnation point (Ue[0] ≈ 0)
    # Use centered difference for dUe/dx at first point
    if len(Ue) > 1 and (s[1] - s[0]) > 0:
        dUe_ds0 = (Ue[1] - Ue[0]) / (s[1] - s[0])
    else:
        dUe_ds0 = 1.0

    theta_sq_integral = 0.0  # running integral of Ue^5 ds
    n_ts = 0.0

    for i in range(M):
        Ue_i = max(Ue[i], 1e-10)

        if i == 0:
            # Initialise at stagnation
            theta_sq_integral = 0.0
            theta_i = _initial_theta(Ue_i, dUe_ds0, nu)
            # Stagnation: lambda = 0.0750 for Hiemenz (beta=1)
            lam_i = 0.0750
        else:
            # Trapezoidal step
            ds = s[i] - s[i - 1]
            Ue_prev = max(Ue[i - 1], 1e-10)
            theta_sq_integral += 0.5 * ds * (Ue_prev**5 + Ue_i**5)

            if Ue_i < 1e-9:
                theta_i = 1e-8
            else:
                theta_sq = 0.45 * nu * theta_sq_integral / Ue_i**6
                theta_sq = max(theta_sq, 1e-20)
                theta_i = math.sqrt(theta_sq)

            # Pressure gradient parameter lambda
            if i < M - 1 and (s[i + 1] - s[i]) > 1e-15:
                dUe_ds = (Ue[i + 1] - Ue[i]) / (s[i + 1] - s[i])
            elif i > 0 and (s[i] - s[i - 1]) > 1e-15:
                dUe_ds = (Ue[i] - Ue[i - 1]) / (s[i] - s[i - 1])
            else:
                dUe_ds = 0.0

            lam_i = (theta_i**2 / nu) * dUe_ds

        H_i = _thwaites_H(lam_i)
        l_i = _thwaites_l(lam_i)
        delta_star_i = H_i * theta_i

        Re_theta_i = Ue_i * theta_i / nu

        # Skin friction: Cf = 2 * l(lambda) / Re_theta
        if Re_theta_i > 1e-10:
            Cf_i = 2.0 * l_i / Re_theta_i
        else:
            Cf_i = 0.0

        # e^N amplification rate (Drela envelope method)
        if i > 0:
            dn_dRe = _n_amplification_rate(Re_theta_i, H_i)
            dRe = Re_theta_i - states[-1].Re_theta if states else 0.0
            if dRe > 0:
                n_ts = n_ts + dn_dRe * dRe

        st = LaminarState(
            x=float(s[i]),
            theta=theta_i,
            H=H_i,
            delta_star=delta_star_i,
            Cf=Cf_i,
            Ue=Ue_i,
            Re_theta=Re_theta_i,
            n_ts=n_ts,
        )
        states.append(st)

        # Transition criterion: N > N_crit
        if n_ts >= n_crit and i_trans < 0:
            i_trans = i
            break

        # Separation: lambda < -0.09 (Thwaites criterion)
        if lam_i <= -0.09 and i > 2:
            # Force transition at separation
            if i_trans < 0:
                i_trans = i
            break

    return states, i_trans
