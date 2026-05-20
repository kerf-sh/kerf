"""
Farassat 1A formulation of the Ffowcs Williams-Hawkings (FW-H) equation.

Reference
---------
Farassat, F. & Succi, G.P. (1980). "A Review of Propeller Discrete Frequency
Noise Prediction Technology with Special Reference to Two Current Methods for
Time Domain Calculations." Journal of Sound and Vibration 71(3), 399-419.

Farassat, F. (2007). "Derivation of Formulations 1 and 1A of Farassat."
NASA/TM-2007-214853.

Sign conventions
----------------
- Observer position x, source position y
- r = |x - y|,  r̂ = (x - y) / r  (pointing toward observer)
- Mach number of source panel: M_r = (ẏ · r̂) / a₀
- Retarded distance: r* = r (1 - M_r)   (factor in the denominator)

Thickness-noise kernel (Farassat 1A, Eq. T1):
    p'_T = (ρ₀ / 4π) ∫∫_f=0 [
        (U̇_n) / (r (1 - M_r)²)
        + (U_n (r Ṁ_r + a₀(M_r - M²))) / (r² (1 - M_r)³)
    ]_ret dS

Loading-noise kernel (Farassat 1A, Eq. L1):
    p'_L = (1 / 4π a₀) ∫∫_f=0 [
        (L̇_r) / (r (1 - M_r)²)
    ]_ret dS
    + (1 / 4π) ∫∫_f=0 [
        (L_r - L_M) / (r² (1 - M_r)²)
        + (L_r (r Ṁ_r + a₀(M_r - M²))) / (a₀ r² (1 - M_r)³)
    ]_ret dS

where:
    U_n  = ρ₀ vₙ  (volume velocity, ρ₀ × normal velocity of panel)
    L_r  = F · r̂  (loading in observer direction)
    L_M  = F · M̂  (loading in Mach direction — same as M · L for subsonic)
    M    = |ẏ| / a₀  (panel Mach number magnitude)

For low-Mach subsonic propellers (M ≪ 1) the 1/(1-M_r)³ terms are
numerically small but retained for generality.

Implementation
--------------
We use a **time-domain summation** approach:
  1. For each observer time t, for each panel, solve the retarded-time equation.
  2. Interpolate panel state (position, velocity, force, area, normal) at τ.
  3. Accumulate thickness + loading kernels.

For N_t observer times and N_panel panels the cost is O(N_t × N_panel).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .observer import retarded_time, retarded_time_moving_source

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RotorSurface:
    """
    Discretised rotor / propeller surface for FW-H.

    Each panel is a triangle or quadrilateral reduced to a centroid.

    Attributes
    ----------
    panel_positions : ndarray (N_panel, 3)
        Panel centroid positions at reference time (m).
    panel_areas : ndarray (N_panel,)
        Panel areas (m²).
    panel_normals : ndarray (N_panel, 3)
        Outward unit normals (dimensionless).
    """
    panel_positions: np.ndarray   # (N_panel, 3)
    panel_areas: np.ndarray       # (N_panel,)
    panel_normals: np.ndarray     # (N_panel, 3)

    def __post_init__(self) -> None:
        self.panel_positions = np.asarray(self.panel_positions, dtype=float)
        self.panel_areas = np.asarray(self.panel_areas, dtype=float)
        self.panel_normals = np.asarray(self.panel_normals, dtype=float)


@dataclass
class RotorMotion:
    """
    Time-history of the rotor surface motion and loading.

    Attributes
    ----------
    time : ndarray (N_t,)
        Time samples (s). Must be uniformly spaced for FFT.
    panel_positions : ndarray (N_t, N_panel, 3)
        Panel centroid positions at each time step (m).
    panel_velocities : ndarray (N_t, N_panel, 3)
        Panel centroid velocities (m/s).
    panel_forces : ndarray (N_t, N_panel, 3)
        Aerodynamic force vector on each panel (N).
        Positive = force on the fluid (reaction), per FW-H convention.
    rho0 : float
        Ambient density (kg/m³).
    speed_of_sound : float
        Ambient speed of sound (m/s).
    """
    time: np.ndarray              # (N_t,)
    panel_positions: np.ndarray   # (N_t, N_panel, 3)
    panel_velocities: np.ndarray  # (N_t, N_panel, 3)
    panel_forces: np.ndarray      # (N_t, N_panel, 3)
    rho0: float
    speed_of_sound: float

    def __post_init__(self) -> None:
        self.time = np.asarray(self.time, dtype=float)
        self.panel_positions = np.asarray(self.panel_positions, dtype=float)
        self.panel_velocities = np.asarray(self.panel_velocities, dtype=float)
        self.panel_forces = np.asarray(self.panel_forces, dtype=float)


@dataclass
class NoiseResult:
    """
    Far-field acoustic pressure result from FW-H solver.

    Attributes
    ----------
    time : ndarray (N_t,)
        Observer time array (s).
    p_thickness : ndarray (N_obs, N_t)
        Thickness-noise pressure time-history (Pa).
    p_loading : ndarray (N_obs, N_t)
        Loading-noise pressure time-history (Pa).
    p_total : ndarray (N_obs, N_t)
        Total pressure = thickness + loading (Pa).
    oaspl_thickness_db : ndarray (N_obs,)
        Thickness-noise OASPL (dB SPL).
    oaspl_loading_db : ndarray (N_obs,)
        Loading-noise OASPL (dB SPL).
    oaspl_total_db : ndarray (N_obs,)
        Total OASPL (dB SPL).
    observer_positions : ndarray (N_obs, 3)
        Observer positions (m).
    """
    time: np.ndarray
    p_thickness: np.ndarray
    p_loading: np.ndarray
    p_total: np.ndarray
    oaspl_thickness_db: np.ndarray
    oaspl_loading_db: np.ndarray
    oaspl_total_db: np.ndarray
    observer_positions: np.ndarray


# ---------------------------------------------------------------------------
# Farassat 1A kernel — vectorised over panels, scalar in time
# ---------------------------------------------------------------------------

def _time_derivative(f_vals: np.ndarray, time: np.ndarray) -> np.ndarray:
    """
    Second-order central finite difference of f along the time axis.

    Parameters
    ----------
    f_vals : ndarray (N_t, ...)
        Function values.
    time : ndarray (N_t,)
        Time array (uniform or non-uniform).

    Returns
    -------
    ndarray (N_t, ...)
        Time derivative approximation.
    """
    dt = np.gradient(time)  # (N_t,) — handles non-uniform spacing
    # Broadcast dt for multi-dimensional arrays
    for _ in range(f_vals.ndim - 1):
        dt = dt[..., np.newaxis]
    return np.gradient(f_vals, axis=0) / dt


def _farassat_1a_single_observer(
    observer: np.ndarray,          # (3,)
    surface: RotorSurface,
    motion: RotorMotion,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute thickness and loading noise time-histories at a single observer.

    Returns
    -------
    p_T : ndarray (N_t,)
        Thickness noise (Pa).
    p_L : ndarray (N_t,)
        Loading noise (Pa).
    """
    time = motion.time
    N_t = len(time)
    N_panel = motion.panel_positions.shape[1]
    a0 = motion.speed_of_sound
    rho0 = motion.rho0

    # Pre-compute panel areas and initial normals from surface
    areas = surface.panel_areas         # (N_panel,)

    # Pre-compute time derivatives (do once on full arrays)
    # panel_velocities: (N_t, N_panel, 3)
    # panel_forces: (N_t, N_panel, 3)
    vel = motion.panel_velocities       # (N_t, N_panel, 3)
    forces = motion.panel_forces        # (N_t, N_panel, 3)
    positions = motion.panel_positions  # (N_t, N_panel, 3)

    # U_n = rho0 * v_n  for each panel; v_n = v · n (use surface normals)
    # Panel normal: use surface.panel_normals (fixed reference) — for
    # rotating panels, normals also rotate with position.
    # We derive rotating normals from the cross product of the blade span
    # direction with the panel velocity direction — but to keep this general,
    # we accept that the caller supplies panel_normals in the RotorSurface as
    # the *initial* normals and compute rotated normals from the rotation of
    # the position vector (azimuth angle).
    #
    # For a rotor spinning about the z-axis, the normal at time t is obtained
    # by rotating the reference normal by the same azimuth angle as the panel
    # centroid. We detect this from positions.
    #
    # Simplified: use the *outward* normal from the panel centroid projected
    # in the rotor plane (radially outward from spin axis) + the thrust-axis
    # component from surface.panel_normals.
    #
    # For general use, we use surface.panel_normals directly (assumes the
    # caller has pre-rotated them, OR that for thickness noise the key quantity
    # is the normal velocity component).
    #
    # A robust approach: for each panel, at each time, compute the outward
    # normal from the panel's position relative to the rotor axis.

    normals_ref = surface.panel_normals   # (N_panel, 3)

    # Accumulate contributions
    p_T = np.zeros(N_t)
    p_L = np.zeros(N_t)

    # For efficiency we vectorise over panels, iterate over observer times.
    # Precompute time-derivatives of force and derive panel-wise U_n.

    # Gradient along time axis (axis=0)
    dt_arr = np.gradient(time)  # (N_t,)

    # vel_n: (N_t, N_panel) — normal velocity of each panel
    # For rotating rotor: normal direction rotates. Compute instantaneous
    # radial unit vector (in x-y plane) for each panel at each time.
    # panel centroid in x-y plane → angle → rotate initial normal
    pos_xy = positions[:, :, :2]  # (N_t, N_panel, 2)
    r_radial = np.sqrt(pos_xy[:, :, 0]**2 + pos_xy[:, :, 1]**2)  # (N_t, N_panel)
    r_radial = np.maximum(r_radial, 1e-10)

    # Unit radial vector: (N_t, N_panel, 2)
    e_r_xy = pos_xy / r_radial[:, :, np.newaxis]

    # Instantaneous outward normal = (e_r_x, e_r_y, n_ref_z)
    # where n_ref_z is the z-component of the reference normal (thrust axis)
    normals_dynamic = np.zeros((N_t, N_panel, 3))
    normals_dynamic[:, :, 0] = e_r_xy[:, :, 0] * normals_ref[:, 0]
    normals_dynamic[:, :, 1] = e_r_xy[:, :, 1] * normals_ref[:, 1]
    normals_dynamic[:, :, 2] = normals_ref[:, 2]

    # Renormalise
    nn = np.linalg.norm(normals_dynamic, axis=2, keepdims=True)
    nn = np.maximum(nn, 1e-10)
    normals_dynamic = normals_dynamic / nn

    # Normal velocity: v · n  → (N_t, N_panel)
    vel_n = np.einsum('tpi,tpi->tp', vel, normals_dynamic)  # (N_t, N_panel)

    # U_n = rho0 * vel_n   (thickness source strength)
    U_n = rho0 * vel_n  # (N_t, N_panel)

    # dU_n/dt  (N_t, N_panel)
    dU_n_dt = np.gradient(U_n, axis=0) / dt_arr[:, np.newaxis]

    # Force in observer direction (loading source)
    # L_r = F · r̂  — but r̂ depends on source position (changes with time!)
    # We pre-compute r̂ for each (t, panel) based on *current* source position.
    # (Retarded-time correction is applied via the time shift below.)

    # For the simplified (but physically correct for subsonic) formulation
    # we evaluate the FW-H integral in the time domain: for each *observer*
    # time t_obs and each panel, interpolate panel state at τ = t_obs - r/a0.

    # Build interpolators (linear interp via numpy)
    # positions: (N_t, N_panel, 3)
    # vel: (N_t, N_panel, 3)
    # forces: (N_t, N_panel, 3)
    # U_n: (N_t, N_panel)
    # dU_n_dt: (N_t, N_panel)

    t0 = time[0]
    t1 = time[-1]

    def interp_scalar(arr_tp: np.ndarray, tau_arr: np.ndarray) -> np.ndarray:
        """
        Interpolate arr_tp[time, panel] at tau_arr[panel] for each panel.

        arr_tp: (N_t, N_panel)
        tau_arr: (N_panel,) — retarded time per panel
        Returns: (N_panel,)
        """
        out = np.zeros(N_panel)
        for p in range(N_panel):
            out[p] = np.interp(tau_arr[p], time, arr_tp[:, p])
        return out

    def interp_vec(arr_tpi: np.ndarray, tau_arr: np.ndarray) -> np.ndarray:
        """
        arr_tpi: (N_t, N_panel, 3)
        tau_arr: (N_panel,)
        Returns: (N_panel, 3)
        """
        out = np.zeros((N_panel, 3))
        for p in range(N_panel):
            for i in range(3):
                out[p, i] = np.interp(tau_arr[p], time, arr_tpi[:, p, i])
        return out

    # Pre-compute dF/dt  (N_t, N_panel, 3)
    dF_dt = np.gradient(forces, axis=0) / dt_arr[:, np.newaxis, np.newaxis]

    for it, t_obs in enumerate(time):
        # --- Retarded time for each panel ---
        # τ_p = t_obs - |x - y_p(τ_p)| / a0
        # For subsonic low-Mach: first estimate τ_p ≈ t_obs - |x - y_p(t_obs)| / a0
        # then one Newton correction using current velocity.

        # Step 1: source positions at t_obs
        pos_t = interp_vec(positions, np.full(N_panel, t_obs))  # (N_panel, 3)
        r_vec = observer[np.newaxis, :] - pos_t   # (N_panel, 3)
        r_mag = np.linalg.norm(r_vec, axis=1)     # (N_panel,)
        r_mag = np.maximum(r_mag, 1e-10)

        # Initial retarded time estimate
        tau_p = t_obs - r_mag / a0                # (N_panel,)
        tau_p = np.clip(tau_p, t0, t1)

        # Step 2: One Newton refinement
        pos_tau = interp_vec(positions, tau_p)     # (N_panel, 3)
        vel_tau = interp_vec(vel, tau_p)           # (N_panel, 3)
        r_vec_tau = observer[np.newaxis, :] - pos_tau  # (N_panel, 3)
        r_mag_tau = np.linalg.norm(r_vec_tau, axis=1)  # (N_panel,)
        r_mag_tau = np.maximum(r_mag_tau, 1e-10)
        r_hat_tau = r_vec_tau / r_mag_tau[:, np.newaxis]  # (N_panel, 3)

        f_eq = tau_p + r_mag_tau / a0 - t_obs     # (N_panel,)
        M_r_tau = np.einsum('pi,pi->p', vel_tau, r_hat_tau) / a0  # (N_panel,)
        df = 1.0 - M_r_tau                        # (N_panel,)
        df = np.where(np.abs(df) < 1e-6, 1e-6, df)
        tau_p = tau_p - f_eq / df
        tau_p = np.clip(tau_p, t0, t1)

        # Step 3: Final panel state at retarded time
        pos_tau = interp_vec(positions, tau_p)     # (N_panel, 3)
        vel_tau = interp_vec(vel, tau_p)           # (N_panel, 3)
        r_vec_tau = observer[np.newaxis, :] - pos_tau
        r_mag_tau = np.linalg.norm(r_vec_tau, axis=1)
        r_mag_tau = np.maximum(r_mag_tau, 1e-10)
        r_hat_tau = r_vec_tau / r_mag_tau[:, np.newaxis]  # (N_panel, 3)

        M_vec_tau = vel_tau / a0                   # (N_panel, 3)
        M_r_tau = np.einsum('pi,pi->p', M_vec_tau, r_hat_tau)  # (N_panel,)
        M_mag_tau = np.linalg.norm(M_vec_tau, axis=1)          # (N_panel,)

        # (1 - M_r)  — denominator factor
        one_minus_Mr = 1.0 - M_r_tau              # (N_panel,)
        one_minus_Mr = np.where(np.abs(one_minus_Mr) < 1e-4, 1e-4 * np.sign(one_minus_Mr + 1e-15), one_minus_Mr)

        # --- Thickness noise ---
        # Kernel: [U̇_n / (r (1-M_r)²) + U_n (r Ṁ_r + a₀(M_r - M²)) / (r² (1-M_r)³)] * dS
        U_n_tau = interp_scalar(U_n, tau_p)          # (N_panel,)
        dU_n_tau = interp_scalar(dU_n_dt, tau_p)     # (N_panel,)

        # Ṁ_r: time derivative of M_r at τ
        # M_r = (v · r̂) / a0 — we use a finite-difference on the interpolated M_r
        dtau_fd = np.maximum((t1 - t0) / N_t * 0.5, 1e-9)
        tau_pp = np.clip(tau_p + dtau_fd, t0, t1)
        tau_pm = np.clip(tau_p - dtau_fd, t0, t1)
        pos_pp = interp_vec(positions, tau_pp)
        vel_pp = interp_vec(vel, tau_pp)
        pos_pm = interp_vec(positions, tau_pm)
        vel_pm = interp_vec(vel, tau_pm)

        r_pp = observer[np.newaxis, :] - pos_pp
        r_pp_mag = np.maximum(np.linalg.norm(r_pp, axis=1), 1e-10)
        r_pp_hat = r_pp / r_pp_mag[:, np.newaxis]
        Mr_pp = np.einsum('pi,pi->p', vel_pp / a0, r_pp_hat)

        r_pm = observer[np.newaxis, :] - pos_pm
        r_pm_mag = np.maximum(np.linalg.norm(r_pm, axis=1), 1e-10)
        r_pm_hat = r_pm / r_pm_mag[:, np.newaxis]
        Mr_pm = np.einsum('pi,pi->p', vel_pm / a0, r_pm_hat)

        dMr_dt_tau = (Mr_pp - Mr_pm) / (tau_pp - tau_pm + 1e-30)  # (N_panel,)

        term_T1 = dU_n_tau / (r_mag_tau * one_minus_Mr**2)
        term_T2 = U_n_tau * (r_mag_tau * dMr_dt_tau + a0 * (M_r_tau - M_mag_tau**2)) \
                  / (r_mag_tau**2 * one_minus_Mr**3)

        integrand_T = (term_T1 + term_T2) * areas  # (N_panel,)
        p_T[it] = np.sum(integrand_T) / (4.0 * math.pi)

        # --- Loading noise ---
        F_tau = interp_vec(forces, tau_p)            # (N_panel, 3)
        dF_tau = interp_vec(dF_dt, tau_p)            # (N_panel, 3)

        # L_r = F · r̂  (N_panel,)
        L_r = np.einsum('pi,pi->p', F_tau, r_hat_tau)
        # L_M = F · M̂ = F · (v/|v|)  — loading along source velocity direction
        v_mag = np.linalg.norm(vel_tau, axis=1)
        v_mag = np.maximum(v_mag, 1e-10)
        M_hat = vel_tau / v_mag[:, np.newaxis]
        L_M = np.einsum('pi,pi->p', F_tau, M_hat)

        # dL_r / dt ≈ (dF/dt) · r̂  (partial, ignoring r̂ rate — r̂ is slowly changing)
        dLr_dt = np.einsum('pi,pi->p', dF_tau, r_hat_tau)

        term_L1 = dLr_dt / (a0 * r_mag_tau * one_minus_Mr**2)
        term_L2 = (L_r - L_M) / (r_mag_tau**2 * one_minus_Mr**2)
        term_L3 = L_r * (r_mag_tau * dMr_dt_tau + a0 * (M_r_tau - M_mag_tau**2)) \
                  / (a0 * r_mag_tau**2 * one_minus_Mr**3)

        # NOTE: forces are total forces (N), not per-area intensities.
        # The Farassat 1A loading kernel integral ∫ L_r dS = F_r (total force).
        # Therefore NO area multiplication — the area is already embedded in F_tau.
        integrand_L = term_L1 + term_L2 + term_L3  # (N_panel,)
        p_L[it] = np.sum(integrand_L) / (4.0 * math.pi)

    return p_T, p_L


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_far_field_noise(
    surface: RotorSurface,
    motion: RotorMotion,
    observers: list[np.ndarray] | np.ndarray,
) -> NoiseResult:
    """
    Compute far-field acoustic pressure at each observer using Farassat 1A.

    Parameters
    ----------
    surface : RotorSurface
        Panel geometry (centroid positions, areas, normals).
    motion : RotorMotion
        Time-history of panel motion and loading.
    observers : list of ndarray (3,) or ndarray (N_obs, 3)
        Observer positions in Cartesian coordinates (m).

    Returns
    -------
    NoiseResult
        Thickness + loading pressure time-histories and OASPL per observer.
    """
    from .oaspl import oaspl_db

    if isinstance(observers, np.ndarray) and observers.ndim == 1:
        observers = [observers]
    obs_arr = [np.asarray(o, dtype=float) for o in observers]
    N_obs = len(obs_arr)
    N_t = len(motion.time)

    p_T_all = np.zeros((N_obs, N_t))
    p_L_all = np.zeros((N_obs, N_t))

    for i, obs in enumerate(obs_arr):
        p_T, p_L = _farassat_1a_single_observer(obs, surface, motion)
        p_T_all[i] = p_T
        p_L_all[i] = p_L

    p_total = p_T_all + p_L_all

    oaspl_T = np.array([oaspl_db(p_T_all[i]) for i in range(N_obs)])
    oaspl_L = np.array([oaspl_db(p_L_all[i]) for i in range(N_obs)])
    oaspl_tot = np.array([oaspl_db(p_total[i]) for i in range(N_obs)])

    return NoiseResult(
        time=motion.time,
        p_thickness=p_T_all,
        p_loading=p_L_all,
        p_total=p_total,
        oaspl_thickness_db=oaspl_T,
        oaspl_loading_db=oaspl_L,
        oaspl_total_db=oaspl_tot,
        observer_positions=np.array([o for o in obs_arr]),
    )
