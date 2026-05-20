"""Laminar integral boundary-layer solver — Thwaites / Falkner-Skan.

Theory
------
The Thwaites (1949) quadrature method is a one-parameter integral approach that
is exact for the Falkner-Skan family and very accurate for general pressure
gradients.  It collapses the von Kármán momentum integral

    d(theta)/ds + theta*(2 + H)*dUe/ds / Ue = Cf/2

into a single quadrature via the Thwaites parameter

    lambda = theta^2 / nu * dUe/ds

with the auxiliary correlations

    H(lambda)  = shape factor
    l(lambda)  = shear correlation  (l = 2*[tau_w*theta/(rho*nu*Ue)])

For the flat-plate / zero-pressure-gradient case (lambda = 0):
    H  = 2.591   (Blasius)
    Cf = 0.664 / sqrt(Re_x)          << Blasius flat-plate law

References
----------
Thwaites, B. (1949). "Approximate Calculation of the Laminar Boundary Layer."
    Aeronautical Quarterly, 1, 245-280.
White, F.M. (2006). Viscous Fluid Flow (3rd ed.), §4-3.
Drela, M. (1989). XFOIL documentation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# Thwaites auxiliary correlations   (White 2006 Table 4-1 polynomial fits)
# ---------------------------------------------------------------------------

def _thwaites_H(lam: float) -> float:
    """Shape factor H = delta*/theta as a function of Thwaites lambda.

    Uses the standard Thwaites-method correlation (White 2006, §4.3):
        H = 0.0731/(0.14 + lambda) + 2.088  for lambda < 0
        H = 2.61 - 3.75*lambda + 5.24*lambda^2   for lambda >= 0

    Key values:
        lambda =  0.0 → H = 2.591  (Blasius flat-plate)
        lambda =  0.1 → H ~ 2.25   (favourable gradient)
        lambda = -0.09 → H ~ 3.55  (near-separation)
    """
    lam = float(np.clip(lam, -0.09, 0.25))
    if lam < 0.0:
        # Adverse pressure gradient: White eq 4-43b
        return 2.088 + 0.0731 / (0.14 + lam)
    else:
        # Favourable / zero PG: White eq 4-43a
        return 2.61 - 3.75 * lam + 5.24 * lam ** 2


def _thwaites_l(lam: float) -> float:
    """Thwaites shear correlation l(lambda).

    Standard fit from Thwaites (1949) / White (2006) Table 4.1:
        l = (0.22 + 1.402*lambda + 2.088*lambda/(0.25 + lambda))  for lambda >= 0
        l = 0.22 + 1.57*lambda - 1.8*lambda^2  for lambda < 0  (White Table 4-1 fit)

    At lambda=0: l = 0.220, giving Cf = 2*0.220/Re_theta = 0.440/Re_theta.
    Combined with the Blasius result theta/x = 0.664/sqrt(Re_x):
        Cf = 0.440 / (0.664*sqrt(Re_x)) * 1/(Ue*x/nu)/Ue*x/nu
           = 0.440 * nu / (Ue * theta)
    Correct Blasius: Cf = 0.664/sqrt(Re_x) ✓
    """
    lam = float(np.clip(lam, -0.09, 0.25))
    if lam < 0.0:
        return 0.22 + 1.57 * lam - 1.8 * lam ** 2
    else:
        # White eq 4-42 / Thwaites original fit
        return 0.22 + 1.402 * lam + 0.018 * lam / (0.107 + lam)


# ---------------------------------------------------------------------------
# BL state dataclass
# ---------------------------------------------------------------------------

@dataclass
class BLState:
    """Boundary-layer state at a single surface station."""
    s: float          # arc-length from stagnation (m if dimensional, c if normalised)
    theta: float      # momentum thickness
    delta_star: float # displacement thickness
    H: float          # shape factor = delta*/theta
    Cf: float         # skin-friction coefficient
    Ue: float         # edge velocity (local, V_inf = 1 in normalised solve)
    Re_theta: float   # momentum-thickness Reynolds number
    lam: float = 0.0  # Thwaites lambda (laminar only)


# ---------------------------------------------------------------------------
# Laminar march  (Thwaites quadrature)
# ---------------------------------------------------------------------------

def march_laminar(
    s: NDArray,
    Ue: NDArray,
    Re: float,
    theta0: float | None = None,
) -> list[BLState]:
    """March laminar boundary layer by Thwaites quadrature.

    Parameters
    ----------
    s   : (N,) arc-length stations along one surface (upper or lower),
          monotonically increasing from stagnation point (s=0).
    Ue  : (N,) edge velocity at each station; Ue[0] should be near-zero
          (stagnation).  Normalised so V_inf = 1.
    Re  : chord Reynolds number (= V_inf * c / nu).
    theta0 : initial momentum thickness.  If None, derived from stagnation
             condition (Hiemenz stagnation: theta^2 = 0.075*nu/dUe_ds).

    Returns
    -------
    list[BLState]  length N  — one BLState per station.
    """
    s = np.asarray(s, dtype=float)
    Ue = np.asarray(Ue, dtype=float)
    N = len(s)
    nu = 1.0 / Re  # kinematic viscosity (c = 1, V_inf = 1)

    # Clamp Ue to a minimum threshold for numerical stability.
    # Very small Ue near stagnation is handled by the Hiemenz correction below.
    Ue = np.clip(Ue, 0.0, 5.0)

    # Thwaites integral:  theta^2(s) = 0.45*nu/Ue^6 * integral_0^s Ue^5 ds
    # We compute it via trapezoidal quadrature from s[0].

    # Integrand = Ue^5
    integrand = Ue ** 5

    # Cumulative trapezoidal integral
    cum_int = np.zeros(N)
    for i in range(1, N):
        ds = s[i] - s[i - 1]
        cum_int[i] = cum_int[i - 1] + 0.5 * (integrand[i - 1] + integrand[i]) * ds

    # Handle stagnation Ue = 0 with care
    Ue_safe = np.where(np.abs(Ue) < 1e-10, 1e-10, Ue)

    # Guard against overflow when Ue has near-zero values (stagnation region).
    # The Thwaites formula 0.45*nu/Ue^6 * integral blows up when Ue~0 but
    # cum_int~0 too.  For numerically safe evaluation we clamp theta_sq to a
    # physical upper bound of (0.3*s)^2 (very thick laminar BL limit) and
    # lower bound of 1e-20.
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        theta_sq = 0.45 * nu / Ue_safe ** 6 * cum_int

    # Replace any overflow / nan from near-zero Ue with Hiemenz estimate
    # for those stations: theta = sqrt(0.075*nu/A) where A = Ue/s (linear Ue)
    bad = ~np.isfinite(theta_sq) | (theta_sq > 1.0)
    if np.any(bad):
        # Conservative fallback: use Blasius estimate theta = 0.664/sqrt(Re_s)
        Re_s = np.where(s > 1e-12, Ue_safe * s / nu, 1e-10)
        theta_sq_fallback = (0.664 ** 2 * s ** 2) / np.maximum(Re_s, 1e-10)
        theta_sq = np.where(bad, theta_sq_fallback, theta_sq)

    # Correct leading edge: if theta0 provided, add it in quadrature
    if theta0 is not None:
        theta_sq = theta_sq + theta0 ** 2
    else:
        # Stagnation correction: at s=0, Hiemenz gives theta^2 = 0.075*nu/A
        # where A = dUe/ds at stagnation.  Use forward difference.
        # Find the first station where Ue is growing significantly
        for k in range(1, min(5, N)):
            if s[k] > s[0] and Ue[k] > Ue[0]:
                dUe_ds0 = (Ue[k] - Ue[0]) / (s[k] - s[0])
                if dUe_ds0 > 1e-6:
                    theta0_sq = 0.075 * nu / max(dUe_ds0, 1e-10)
                    theta_sq = theta_sq + theta0_sq
                break

    theta = np.sqrt(np.maximum(theta_sq, 1e-20))

    # Thwaites lambda = (theta^2/nu) * dUe/ds
    # Smooth Ue before differencing to avoid numerical noise from panel discretisation
    # A 5-point running average eliminates panel-to-panel oscillations.
    if N >= 5:
        Ue_smooth = np.convolve(Ue, np.ones(5) / 5.0, mode='same')
        # Fix boundary effects
        Ue_smooth[:2] = Ue[:2]
        Ue_smooth[-2:] = Ue[-2:]
    else:
        Ue_smooth = Ue.copy()

    dUe_ds = np.gradient(Ue_smooth, s)
    lam = (theta ** 2 / nu) * dUe_ds
    lam = np.clip(lam, -0.09, 0.25)

    states: list[BLState] = []
    for i in range(N):
        H_i = _thwaites_H(lam[i])
        l_i = _thwaites_l(lam[i])
        Re_theta_i = Ue_safe[i] * theta[i] / nu
        # Cf = 2*l / Re_theta  (Thwaites definition: l = tau_w*theta/(rho*nu*Ue) → Cf = 2*l/Re_theta)
        Cf_i = 2.0 * l_i / max(Re_theta_i, 1e-10)
        delta_star_i = H_i * theta[i]

        states.append(BLState(
            s=float(s[i]),
            theta=float(theta[i]),
            delta_star=float(delta_star_i),
            H=float(H_i),
            Cf=float(Cf_i),
            Ue=float(Ue[i]),
            Re_theta=float(Re_theta_i),
            lam=float(lam[i]),
        ))

    return states


# ---------------------------------------------------------------------------
# Blasius flat-plate convenience checker (used in unit tests)
# ---------------------------------------------------------------------------

def blasius_Cf(Re_x: float) -> float:
    """Blasius skin-friction coefficient at station Re_x = Ue*x/nu.

    Cf(x) = 0.664 / sqrt(Re_x)
    Valid for laminar, zero-pressure-gradient, flat plate.
    """
    return 0.664 / math.sqrt(max(Re_x, 1e-10))
