"""
Observer geometry and retarded-time solver for Farassat 1A FW-H.

The retarded (emission) time τ satisfies:

    t - τ - |x - y(τ)| / a₀ = 0

where x is the observer position, y(τ) is the source position at τ,
a₀ is the ambient speed of sound, and t is the observer (reception) time.

We use a fixed-point / Newton iteration per source panel.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np


class Observer(NamedTuple):
    """Cartesian observer position (m)."""
    x: float
    y: float
    z: float

    def as_array(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z], dtype=float)


def retarded_time(
    t_obs: float,
    source_pos: np.ndarray,  # (3,) — source position at emission time (assumed fixed for panel)
    observer: np.ndarray,    # (3,)
    speed_of_sound: float,
) -> tuple[float, float, np.ndarray]:
    """
    Compute retarded time τ, retarded distance r, and unit direction r̂.

    For a *stationary* source panel (the dominant case when surface motion is
    embedded in the Farassat kernel), the retarded time is:

        τ = t - |x - y| / a₀

    Returns
    -------
    tau : float
        Retarded time (s).
    r : float
        Distance |x - y| (m) at emission.
    r_hat : ndarray (3,)
        Unit vector from source to observer.
    """
    r_vec = observer - source_pos
    r = float(np.linalg.norm(r_vec))
    if r < 1e-12:
        r = 1e-12
    r_hat = r_vec / r
    tau = t_obs - r / speed_of_sound
    return tau, r, r_hat


def retarded_time_moving_source(
    t_obs: float,
    source_trajectory: np.ndarray,  # (N_t, 3) — source position vs time
    time_array: np.ndarray,          # (N_t,) — time values
    observer: np.ndarray,
    speed_of_sound: float,
    max_iter: int = 50,
    tol: float = 1e-10,
) -> tuple[float, float, np.ndarray, float]:
    """
    Solve the retarded-time equation for a *moving* source via Newton iteration.

    Returns
    -------
    tau : float
        Retarded emission time (s).
    r : float
        Distance |x - y(τ)| at emission (m).
    r_hat : ndarray (3,)
        Unit observer–source direction at emission.
    M_r : float
        Mach number of source along r̂ at emission.
    """
    # Initial guess: τ = t - r(t) / a₀  (use current position)
    y_t = np.interp(t_obs, time_array, source_trajectory[:, 0]), \
          np.interp(t_obs, time_array, source_trajectory[:, 1]), \
          np.interp(t_obs, time_array, source_trajectory[:, 2])
    y_t = np.array(y_t)

    r_vec = observer - y_t
    r = float(np.linalg.norm(r_vec))
    tau = t_obs - r / speed_of_sound

    for _ in range(max_iter):
        y_tau = np.array([
            np.interp(tau, time_array, source_trajectory[:, i])
            for i in range(3)
        ])
        r_vec = observer - y_tau
        r = float(np.linalg.norm(r_vec))
        if r < 1e-12:
            r = 1e-12
        f = tau + r / speed_of_sound - t_obs

        # Derivative: df/dτ = 1 - (r_hat · ẏ) / a₀
        # Estimate ẏ via finite difference on interpolated trajectory
        dt_fd = max((time_array[-1] - time_array[0]) / len(time_array) * 0.1, 1e-8)
        tau_p = min(tau + dt_fd, time_array[-1])
        tau_m = max(tau - dt_fd, time_array[0])
        y_p = np.array([np.interp(tau_p, time_array, source_trajectory[:, i]) for i in range(3)])
        y_m = np.array([np.interp(tau_m, time_array, source_trajectory[:, i]) for i in range(3)])
        ydot = (y_p - y_m) / (tau_p - tau_m + 1e-30)

        r_hat = r_vec / r
        M_r = float(np.dot(ydot, r_hat)) / speed_of_sound
        df_dtau = 1.0 - float(np.dot(ydot, r_hat)) / speed_of_sound

        if abs(df_dtau) < 1e-15:
            break
        tau_new = tau - f / df_dtau
        # Clamp to time array bounds
        tau = float(np.clip(tau_new, time_array[0], time_array[-1]))
        if abs(f) < tol:
            break

    # Final values
    y_tau = np.array([np.interp(tau, time_array, source_trajectory[:, i]) for i in range(3)])
    r_vec = observer - y_tau
    r = float(np.linalg.norm(r_vec))
    if r < 1e-12:
        r = 1e-12
    r_hat = r_vec / r

    # Source velocity at τ
    dt_fd = max((time_array[-1] - time_array[0]) / len(time_array) * 0.1, 1e-8)
    tau_p = min(tau + dt_fd, time_array[-1])
    tau_m = max(tau - dt_fd, time_array[0])
    y_p = np.array([np.interp(tau_p, time_array, source_trajectory[:, i]) for i in range(3)])
    y_m = np.array([np.interp(tau_m, time_array, source_trajectory[:, i]) for i in range(3)])
    ydot = (y_p - y_m) / (tau_p - tau_m + 1e-30)
    M_r = float(np.dot(ydot, r_hat)) / speed_of_sound

    return tau, r, r_hat, M_r
