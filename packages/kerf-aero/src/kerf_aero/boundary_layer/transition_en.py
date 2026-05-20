"""e^N / envelope transition prediction module.

Theory
------
The e^N method (Smith & Gamberoni 1956, van Ingen 1956) tracks the
amplification factor N of the most-amplified Tollmien-Schlichting (TS) wave
along a streamline.  Transition is predicted when N = N_crit.

Drela's simplified envelope method (XFOIL) avoids solving the Orr-Sommerfeld
equation explicitly and instead uses a quasi-parallel, locally-similar
correlation:

    dN/d(ln Re_theta) = f(H)

where

    f(H) = (1.415/(H-1) - 0.489) * tanh(20/(H-1) - 12.9)
           + 3.295/(H-1) + 0.44

This matches the Orr-Sommerfeld database curves to engineering accuracy.

References
----------
Drela, M. and Giles, M.B. (1987). "Viscous-Inviscid Analysis of Transonic and
    Low Reynolds Number Airfoils." AIAA J., 25(10).
Drela, M. (1989). XFOIL code documentation.
Smith, A.M.O. and Gamberoni, N. (1956). "Transition, Pressure Gradient, and
    Stability Theory." Douglas Aircraft Report ES-26388.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class TransitionResult:
    """Result of transition detection.

    Attributes
    ----------
    triggered : bool
        Whether transition was detected.
    x_trans : float
        Arc-length location of transition (surface coordinate).
    n_at_trans : float
        N factor at transition.
    i_trans : int
        Index in the surface array where transition occurred (-1 if not).
    """
    triggered: bool = False
    x_trans: float = 1.0
    n_at_trans: float = 0.0
    i_trans: int = -1


class TransitionDetector:
    """e^N transition detector using Drela's envelope method.

    Parameters
    ----------
    n_crit : float
        Critical N factor (default 9).  Typical values:
            9   -- clean low-turbulence wind tunnel
            11  -- very clean (flight / NTF tunnel)
            7   -- moderate turbulence
            4-5 -- highly turbulent environment
    """

    def __init__(self, n_crit: float = 9.0) -> None:
        self.n_crit = n_crit

    @staticmethod
    def dn_dlnRe(H: float) -> float:
        """Amplification rate dN/d(ln Re_theta) as a function of H.

        This is the Drela envelope-method correlation used in XFOIL.
        Returns 0 for H <= 1.05 (attached, near-flat-plate).
        """
        if H <= 1.05:
            return 0.0
        Hm1 = H - 1.0
        rate = ((1.415 / Hm1 - 0.489) * math.tanh(20.0 / Hm1 - 12.9)
                + 3.295 / Hm1 + 0.44)
        return max(0.0, rate)

    def detect(
        self,
        s_arr: list[float],
        H_arr: list[float],
        Re_theta_arr: list[float],
    ) -> TransitionResult:
        """Integrate N from stagnation and detect when N >= N_crit.

        Parameters
        ----------
        s_arr : list[float]
            Surface arc-length at each laminar BL station.
        H_arr : list[float]
            Shape factor at each station.
        Re_theta_arr : list[float]
            Re_theta at each station.

        Returns
        -------
        TransitionResult
        """
        n = 0.0
        for i in range(1, len(s_arr)):
            H_i = H_arr[i]
            Re_i = Re_theta_arr[i]
            Re_prev = Re_theta_arr[i - 1]

            if Re_i <= 0 or Re_prev <= 0:
                continue

            # dN = (dN/d(ln Re_theta)) * d(ln Re_theta)
            #     = (dN/d(ln Re_theta)) * (Re_i - Re_prev) / Re_avg
            dln_Re = math.log(Re_i / max(Re_prev, 1e-15))
            dn = self.dn_dlnRe(H_i) * dln_Re
            n = n + max(0.0, dn)

            if n >= self.n_crit:
                return TransitionResult(
                    triggered=True,
                    x_trans=s_arr[i],
                    n_at_trans=n,
                    i_trans=i,
                )

        return TransitionResult(triggered=False, x_trans=s_arr[-1] if s_arr else 1.0,
                                n_at_trans=n, i_trans=-1)
