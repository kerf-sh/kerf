"""Turbulent integral boundary-layer — Head (1958) + skin-friction closure.

Theory
------
Head's (1958) entrainment method marches two coupled ODEs:

  d(theta)/ds = Cf/2 - (H + 2)*theta/Ue * dUe/ds           (von Kármán)
  d(Ue*H1*theta)/ds = Ue * CE(H1)                           (entrainment)

where H1 is the shape parameter linked to H via the Ludwieg-Tillmann
relation, and CE is the entrainment function:

    CE(H1) = 0.0306 * (H1 - 3.0)^(-0.6169)

Shape-factor relation  (Head):
    H1 = 3.3 + 0.8234*(H - 1.1)^(-1.287)   for H <= 1.6
    H1 = 3.3 + 1.5501*(H - 0.6778)^(-3.064) for H >  1.6

Skin-friction closure  (Ludwieg-Tillmann 1950):
    Cf = 0.246 * exp(-1.561*H) * Re_theta^(-0.268)

This is the standard textbook Head method sufficient for attached turbulent
boundary layers.  It under-predicts separation; a full Green lag-entrainment
extension is left as a TODO for a future turbulent-closure upgrade.

TODO
----
- Add Green (1972) lag-entrainment equation for more accurate adverse-PG
  and near-separation prediction (needed for Cd accuracy within 15%).
- Implement wake-region turbulent BL for Cd integration.
- Validate against Preston-tube measurements on NACA 0012 at Re=3e6.

References
----------
Head, M.R. (1958). "Entrainment in the turbulent boundary layer."
    ARC R&M No. 3152.
Ludwieg, H. & Tillmann, W. (1950). Investigations of the Wall-Shearing
    Stress in Turbulent Boundary Layers.  NACA TM 1285.
Drela, M. (1989). XFOIL documentation.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from numpy.typing import NDArray

from .laminar import BLState


# ---------------------------------------------------------------------------
# Head's auxiliary relations
# ---------------------------------------------------------------------------

def _H_to_H1(H: float) -> float:
    """Convert shape factor H = delta*/theta to H1 (entrainment shape factor)."""
    H = max(H, 1.11)   # guard against H == 1.1 exactly (zero base)
    if H <= 1.6:
        base = max(H - 1.1, 1e-6)
        return 3.3 + 0.8234 * base ** (-1.287)
    else:
        base = max(H - 0.6778, 1e-6)
        return 3.3 + 1.5501 * base ** (-3.064)


def _H1_to_H(H1: float) -> float:
    """Inverse of _H_to_H1: convert H1 → H.  Numerical inversion."""
    H1 = max(H1, 3.01)
    H = 2.0  # initial guess
    for _ in range(50):
        H1_try = _H_to_H1(H)
        # Numerical derivative
        dH = 1e-5
        H1_hi = _H_to_H1(H + dH)
        dH1_dH = (H1_hi - H1_try) / dH
        if abs(dH1_dH) < 1e-20:
            break
        delta = (H1_try - H1) / dH1_dH
        H_new = H - delta
        H_new = max(H_new, 1.12)
        if abs(H_new - H) < 1e-8:
            H = H_new
            break
        H = H_new
    return H


def _CE(H1: float) -> float:
    """Head's entrainment function."""
    return 0.0306 * max(H1 - 3.0, 0.001) ** (-0.6169)


def _Cf_ludwieg_tillmann(H: float, Re_theta: float) -> float:
    """Ludwieg-Tillmann skin-friction formula."""
    return 0.246 * math.exp(-1.561 * H) * max(Re_theta, 10.0) ** (-0.268)


# ---------------------------------------------------------------------------
# Turbulent march (simple forward Euler + predictor-corrector)
# ---------------------------------------------------------------------------

def march_turbulent(
    s: NDArray,
    Ue: NDArray,
    Re: float,
    theta_init: float,
    H_init: float = 1.4,
) -> list[BLState]:
    """March turbulent boundary layer via Head's entrainment method.

    Parameters
    ----------
    s         : (N,) arc-length stations (monotonically increasing from transition).
    Ue        : (N,) edge velocity at each station.
    Re        : chord Reynolds number.
    theta_init: momentum thickness at start of turbulent region.
    H_init    : initial shape factor (typically 1.4 for fresh turbulent BL).

    Returns
    -------
    list[BLState]  length N
    """
    s = np.asarray(s, dtype=float)
    Ue = np.asarray(Ue, dtype=float)
    N = len(s)
    nu = 1.0 / Re

    # dUe/ds via central differences
    dUe_ds = np.gradient(Ue, s)

    states: list[BLState] = []

    # State vector: [theta, H1*theta*Ue]  → we track theta and H1
    theta = float(theta_init)
    H = float(H_init)
    H1 = _H_to_H1(H)

    for i in range(N):
        Ue_i = float(Ue[i])
        s_i = float(s[i])
        dUe_ds_i = float(dUe_ds[i])
        Re_theta_i = Ue_i * theta / nu
        Cf_i = _Cf_ludwieg_tillmann(H, Re_theta_i)
        delta_star_i = H * theta

        states.append(BLState(
            s=s_i,
            theta=theta,
            delta_star=delta_star_i,
            H=H,
            Cf=Cf_i,
            Ue=Ue_i,
            Re_theta=Re_theta_i,
        ))

        if i < N - 1:
            ds = float(s[i + 1]) - s_i

            # von Kármán ODE: d(theta)/ds
            dtheta_ds = Cf_i / 2.0 - (H + 2.0) * theta * dUe_ds_i / max(Ue_i, 1e-10)

            # Entrainment ODE: d(Ue*H1*theta)/ds = Ue * CE(H1)
            # = Ue*H1*dtheta/ds + Ue*theta*dH1/ds + H1*theta*dUe/ds = Ue*CE(H1)
            # Rearranged: d(H1*theta)/ds = CE(H1) - H1*theta/Ue * dUe/ds
            E_i = _CE(H1)
            d_H1theta_ds = E_i - H1 * theta * dUe_ds_i / max(Ue_i, 1e-10)

            # Forward Euler step
            theta_new = theta + dtheta_ds * ds
            H1theta_new = H1 * theta + d_H1theta_ds * ds

            theta_new = max(theta_new, 1e-10)
            H1_new = H1theta_new / max(theta_new, 1e-10)
            H1_new = max(H1_new, 3.01)

            # Convert H1 → H
            H_new = _H1_to_H(H1_new)
            H_new = max(H_new, 1.05)

            theta = theta_new
            H = H_new
            H1 = H1_new

    return states
