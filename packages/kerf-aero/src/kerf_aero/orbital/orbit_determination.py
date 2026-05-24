"""Batch Least-Squares Orbit Determination (OD).

Estimates a spacecraft orbit state (position + velocity at epoch t_0) from
simulated or real tracking observations by iterating weighted normal equations
until convergence.

Algorithm (Vallado 2013, Ch. 10; Tapley, Schutz & Born 2004, §4):

    1. Reference trajectory: propagate reference state X̄_0 forward using
       the Keplerian + optional J2 dynamics (RK4, simultaneous STM).

    2. Predicted observations: compute ŷ_i = h(X̄(t_i)) — range ρ and/or
       range-rate ρ̇ at each observation epoch t_i.

    3. Residuals: y_i - ŷ_i.

    4. Measurement partials (H-matrix at t_i):
           H_i = ∂h/∂x  evaluated at X̄(t_i)   [p × 6]
       These are mapped back to epoch via the STM Φ(t_i, t₀):
           H̃_i = H_i · Φ(t_i, t₀)             [p × 6]

    5. Normal equations (information form):
           Λ = Σ H̃_iᵀ W_i H̃_i                 (6 × 6 information matrix)
           b = Σ H̃_iᵀ W_i (y_i - ŷ_i)         (6-vector)
       where W_i = diag(1/σ²) is the per-observation weight matrix.

    6. State correction:   δX̄_0 = Λ⁻¹ b
       Update reference:   X̄_0  ← X̄_0 + δX̄_0

    7. Iterate steps 1–6 until ||δX̄_0|| < tolerance (default 1e-3 m position).

    8. Estimated covariance:  P = Λ⁻¹  (formal, observation-only).

Observation types supported:
  - 'range'      : scalar range ρ = |r_sc - r_gs|  [km]
  - 'range_rate' : scalar range-rate ρ̇ = (r-r_gs)·(v-v_gs)/ρ  [km/s]
  - 'both'       : [ρ, ρ̇] (2-vector) — the most common radar observable

Ground station positions are specified in Earth-Centred Inertial (ECI) frame.
For low-fidelity analysis (no Earth rotation) this is equivalent to ECEF with a
fixed station.  A helper is provided to convert geodetic lat/lon/alt to ECI
assuming a fixed Earth (suitable for short observation arcs).

References
----------
Vallado, D. A. (2013). *Fundamentals of Astrodynamics and Applications*, 4th
    ed., Microcosm/Springer. Chapter 10, "Initial Orbit Determination."
Tapley, B. D., Schutz, B. E., & Born, G. H. (2004). *Statistical Orbit
    Determination*. Elsevier. §4.3 (batch LS), §4.5 (covariance).
Montenbruck, O., & Gill, E. (2000). *Satellite Orbits*. Springer. §5.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Sequence

import numpy as np
from numpy.typing import NDArray

from .perturbations import MU_EARTH, J2, R_EARTH
from .stm import propagate_stm


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: WGS-84 Earth equatorial radius [km]
R_EARTH_WGS84_KM: float = 6_378.137

#: WGS-84 flattening
_F_WGS84: float = 1.0 / 298.257223563


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Observation:
    """A single tracking observation.

    Attributes
    ----------
    t : float
        Observation epoch relative to the OD reference epoch t₀ [s].
        Must be ≥ 0 for forward propagation.
    obs_type : {'range', 'range_rate', 'both'}
        Observation type(s) measured.
    y : NDArray
        Observed values:
          - 'range'      → shape (1,) [km]
          - 'range_rate' → shape (1,) [km/s]
          - 'both'       → shape (2,) = [ρ [km], ρ̇ [km/s]]
    sigma : NDArray
        1-sigma noise level — same shape as y; used to form W = diag(1/σ²).
    station_eci : NDArray, shape (3,)
        Ground station position in ECI [km] at epoch t.
    station_vel_eci : NDArray, shape (3,), optional
        Ground station velocity in ECI [km/s] at epoch t.  Defaults to [0,0,0].
    """

    t: float
    obs_type: Literal["range", "range_rate", "both"]
    y: NDArray
    sigma: NDArray
    station_eci: NDArray
    station_vel_eci: NDArray = field(default_factory=lambda: np.zeros(3))

    def __post_init__(self) -> None:
        self.y = np.asarray(self.y, dtype=float)
        self.sigma = np.asarray(self.sigma, dtype=float)
        self.station_eci = np.asarray(self.station_eci, dtype=float)
        self.station_vel_eci = np.asarray(self.station_vel_eci, dtype=float)

        if self.obs_type == "both" and self.y.shape != (2,):
            raise ValueError(
                f"obs_type='both' requires y of shape (2,), got {self.y.shape}"
            )
        if self.obs_type in ("range", "range_rate") and self.y.shape != (1,):
            raise ValueError(
                f"obs_type='{self.obs_type}' requires y of shape (1,), got {self.y.shape}"
            )
        if self.sigma.shape != self.y.shape:
            raise ValueError(
                f"sigma shape {self.sigma.shape} must match y shape {self.y.shape}"
            )


@dataclass
class ODResult:
    """Result of a batch least-squares orbit determination.

    Attributes
    ----------
    state_epoch : NDArray, shape (6,)
        Estimated state [r(3) km; v(3) km/s] at the reference epoch t₀.
    covariance : NDArray, shape (6, 6)
        Formal state covariance P = Λ⁻¹ [km², km·km/s, km²/s²].
    residuals : list[NDArray]
        Post-fit residuals y_i - ŷ_i for each observation, in units of the
        observation (km or km/s).
    iterations : int
        Number of iterations taken.
    converged : bool
        Whether the solution converged within the iteration limit.
    rms_residual : float
        RMS of weighted (normalised) post-fit residuals.  A value near 1
        indicates noise-consistent residuals.
    sigma_0 : float
        A posteriori standard deviation (= sqrt(chi² / dof)).
    """

    state_epoch: NDArray
    covariance: NDArray
    residuals: list[NDArray]
    iterations: int
    converged: bool
    rms_residual: float
    sigma_0: float


# ---------------------------------------------------------------------------
# Ground station helper
# ---------------------------------------------------------------------------

def geodetic_to_eci(
    lat_deg: float,
    lon_deg: float,
    alt_km: float,
    gst_rad: float = 0.0,
) -> NDArray:
    """Convert geodetic (WGS-84) ground station location to ECI position.

    For short observation arcs the station velocity due to Earth rotation may
    be computed from  v = ω_E × r_eci  with ω_E = 7.2921150e-5 rad/s.

    Parameters
    ----------
    lat_deg : float
        Geodetic latitude [degrees].
    lon_deg : float
        East longitude [degrees].
    alt_km : float
        Altitude above WGS-84 ellipsoid [km].
    gst_rad : float
        Greenwich Sidereal Time [rad] at the observation epoch.
        Default 0 effectively treats ECEF X-axis aligned with ECI X-axis
        (suitable for instantaneous snapshots or zero-time analyses).

    Returns
    -------
    NDArray, shape (3,)
        ECI position [km].
    """
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)

    # WGS-84 radii
    a = R_EARTH_WGS84_KM
    f = _F_WGS84
    e2 = 2.0 * f - f ** 2  # first eccentricity squared

    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    N = a / math.sqrt(1.0 - e2 * sin_lat ** 2)  # prime vertical radius

    # ECEF
    x_ecef = (N + alt_km) * cos_lat * math.cos(lon)
    y_ecef = (N + alt_km) * cos_lat * math.sin(lon)
    z_ecef = (N * (1.0 - e2) + alt_km) * sin_lat

    # Rotate ECEF → ECI by GST angle around Z
    cos_gst = math.cos(gst_rad)
    sin_gst = math.sin(gst_rad)

    x_eci = cos_gst * x_ecef - sin_gst * y_ecef
    y_eci = sin_gst * x_ecef + cos_gst * y_ecef
    z_eci = z_ecef

    return np.array([x_eci, y_eci, z_eci])


# ---------------------------------------------------------------------------
# Observation model and partials
# ---------------------------------------------------------------------------

def _predict_observation(
    x: NDArray,
    obs: Observation,
) -> NDArray:
    """Compute predicted observation ŷ = h(x) at one station.

    Parameters
    ----------
    x : NDArray, shape (6,)
        Spacecraft state [r(3); v(3)] [km, km/s] at the observation epoch.
    obs : Observation
        Observation descriptor (type, station position/velocity).

    Returns
    -------
    NDArray
        Predicted observation value(s), same shape as obs.y.
    """
    r_sc = x[:3]
    v_sc = x[3:6]
    r_gs = obs.station_eci
    v_gs = obs.station_vel_eci

    rho_vec = r_sc - r_gs
    rho = float(np.linalg.norm(rho_vec))
    if rho < 1e-6:
        rho = 1e-6  # guard against zero range

    rho_dot = float(np.dot(rho_vec, v_sc - v_gs)) / rho

    if obs.obs_type == "range":
        return np.array([rho])
    elif obs.obs_type == "range_rate":
        return np.array([rho_dot])
    else:  # "both"
        return np.array([rho, rho_dot])


def _observation_partials(
    x: NDArray,
    obs: Observation,
) -> NDArray:
    """Compute H = ∂h/∂x (measurement Jacobian) at observation epoch.

    For range:
        ∂ρ/∂r  = ρ̂ = (r - r_gs) / ρ
        ∂ρ/∂v  = 0

    For range-rate:
        ∂ρ̇/∂r  = (v - v_gs) / ρ - ρ̇ * ρ̂ / ρ
        ∂ρ̇/∂v  = ρ̂

    where ρ̂ = (r - r_gs) / ρ.

    Parameters
    ----------
    x : NDArray, shape (6,)
        Spacecraft state at observation epoch.
    obs : Observation

    Returns
    -------
    NDArray, shape (p, 6)
        H matrix where p is the number of observation components.
    """
    r_sc = x[:3]
    v_sc = x[3:6]
    r_gs = obs.station_eci
    v_gs = obs.station_vel_eci

    rho_vec = r_sc - r_gs
    rho = float(np.linalg.norm(rho_vec))
    if rho < 1e-6:
        rho = 1e-6

    rho_hat = rho_vec / rho
    dv = v_sc - v_gs
    rho_dot = float(np.dot(rho_vec, dv)) / rho

    # ∂ρ/∂x (1×6)
    H_range = np.zeros((1, 6))
    H_range[0, 0:3] = rho_hat
    # ∂ρ/∂v = 0 (stays zero)

    # ∂ρ̇/∂x (1×6)
    H_rrate = np.zeros((1, 6))
    H_rrate[0, 0:3] = (dv / rho) - (rho_dot / rho) * rho_hat
    H_rrate[0, 3:6] = rho_hat

    if obs.obs_type == "range":
        return H_range
    elif obs.obs_type == "range_rate":
        return H_rrate
    else:  # "both"
        return np.vstack([H_range, H_rrate])


# ---------------------------------------------------------------------------
# Propagation cache: compute all states + STMs from epoch
# ---------------------------------------------------------------------------

def _propagate_arc(
    x0: NDArray,
    obs_list: Sequence[Observation],
    *,
    mu: float,
    include_j2: bool,
    j2: float,
    r_earth: float,
) -> list[tuple[NDArray, NDArray]]:
    """Propagate reference state to all observation epochs.

    Returns a list of (state_at_ti, Phi_i) for each obs, where Phi_i is the
    cumulative STM from epoch t=0 to t=t_i:  Phi_i = Phi(t_i, t_0).

    Strategy: propagate incrementally (epoch → obs[0] → obs[1] → ...) using
    augmented RK4 (simultaneous state + STM), chaining the incremental STMs:
        Phi(t_i, t_0) = Phi(t_i, t_{i-1}) * Phi(t_{i-1}, t_0)
    This is numerically equivalent to propagating from t0 each time but
    is more efficient (O(n) rather than O(n²) propagation steps).
    """
    results: list[tuple[NDArray, NDArray]] = []
    x_prev = x0.copy()
    t_prev = 0.0
    phi_cumul = np.eye(6)  # cumulative STM, starts as identity at epoch

    for obs in obs_list:
        dt = obs.t - t_prev
        if dt < 0.0:
            raise ValueError(
                f"Observations must be in non-decreasing time order; "
                f"got dt={dt:.3f} s at t={obs.t:.3f}"
            )

        if dt == 0.0:
            # Same epoch as previous or t=0 observation
            results.append((x_prev.copy(), phi_cumul.copy()))
            continue

        stm_res = propagate_stm(
            x_prev[:3], x_prev[3:6], dt,
            mu=mu, include_j2=include_j2, j2=j2, r_earth=r_earth,
        )
        x_curr = stm_res.state_final

        # Cumulative STM: Phi(t_i, t_0) = Phi(t_i, t_{i-1}) * Phi(t_{i-1}, t_0)
        phi_cumul = stm_res.stm @ phi_cumul

        results.append((x_curr, phi_cumul.copy()))
        x_prev = x_curr
        t_prev = obs.t

    return results


# ---------------------------------------------------------------------------
# Core batch least-squares OD
# ---------------------------------------------------------------------------

def batch_least_squares_od(
    observations: Sequence[Observation],
    x0_apriori: NDArray,
    *,
    mu: float = MU_EARTH,
    include_j2: bool = False,
    j2: float = J2,
    r_earth: float = R_EARTH,
    max_iter: int = 20,
    tol_pos_km: float = 1e-6,
    a_priori_covariance: NDArray | None = None,
) -> ODResult:
    """Estimate orbit state from tracking observations via batch least-squares.

    Implements the *Differential Correction* / *Weighted Least Squares* (WLS)
    orbit determination algorithm (Vallado 2013 §10.6; Tapley et al. 2004 §4.3).

    Parameters
    ----------
    observations : sequence of Observation
        Tracking data, sorted by time (ascending).  Must have t ≥ 0.
    x0_apriori : array-like, shape (6,)
        A priori (initial guess) state at epoch t=0: [r(3) km; v(3) km/s].
        This is the linearisation point for the first iteration.
    mu : float
        Gravitational parameter [km^3/s^2].
    include_j2 : bool
        Include J2 oblateness in the reference orbit dynamics.
    j2, r_earth : float
        J2 coefficient and Earth radius for the perturbation model.
    max_iter : int
        Maximum number of differential-correction iterations.
    tol_pos_km : float
        Convergence tolerance on the position component of δX̄_0 [km].
        Default 1e-6 km = 1 mm.
    a_priori_covariance : NDArray, shape (6, 6) or None
        Optional a priori state covariance P₀ (information form adds
        P₀⁻¹ to the normal matrix).  If None, no a priori constraint.

    Returns
    -------
    ODResult
        Estimated state, covariance, residuals, iteration count, convergence
        flag, and residual statistics.

    Raises
    ------
    ValueError
        If observations are not time-ordered or other input inconsistencies.

    Notes
    -----
    - Units are consistent with kerf-aero conventions: km, km/s, seconds.
    - The formal covariance P = Λ⁻¹ is the inverse of the information matrix
      and represents the minimum-variance estimate under Gaussian measurement
      noise and an accurate force model.
    - No process noise is added (batch, not filter); covariance underestimates
      uncertainty if the force model is imperfect.
    - For arc lengths > 1 orbit pass, J2 should be enabled for accuracy.

    References
    ----------
    Vallado (2013), §10.6 *Batch Least Squares*.
    Tapley, Schutz & Born (2004), §4.3 *Linearised LS*, §4.5 *Covariance*.
    """
    observations = list(observations)
    if not observations:
        raise ValueError("At least one observation is required")

    # Validate time ordering
    for k in range(1, len(observations)):
        if observations[k].t < observations[k - 1].t:
            raise ValueError(
                f"Observations must be time-ordered: obs[{k}].t="
                f"{observations[k].t:.3f} < obs[{k-1}].t={observations[k-1].t:.3f}"
            )

    x0 = np.asarray(x0_apriori, dtype=float).copy()
    x0_ref = x0.copy()  # store a priori reference for P0 constraint

    if x0.shape != (6,):
        raise ValueError(f"x0_apriori must be shape (6,), got {x0.shape}")

    # A priori information matrix (P₀⁻¹)
    # In the batch LS with a priori, the normal equations become:
    #   (Λ_obs + P₀⁻¹) δX = b_obs + P₀⁻¹(x0_ref - X_ref)
    # Here X_ref is the current reference state, so the second term updates
    # as the reference state changes.
    P0_inv: NDArray | None = None
    if a_priori_covariance is not None:
        P0_inv = np.linalg.inv(np.asarray(a_priori_covariance, dtype=float))

    converged = False
    n_iter = 0

    for n_iter in range(1, max_iter + 1):
        # ------------------------------------------------------------------
        # 1. Propagate reference trajectory + STMs
        # ------------------------------------------------------------------
        arc = _propagate_arc(
            x0, observations,
            mu=mu, include_j2=include_j2, j2=j2, r_earth=r_earth,
        )

        # ------------------------------------------------------------------
        # 2–4. Accumulate normal equations
        # ------------------------------------------------------------------
        Lambda = np.zeros((6, 6))   # observation-only information matrix
        b_vec = np.zeros(6)         # right-hand side

        for obs, (x_ti, phi_ti) in zip(observations, arc):
            # Predicted observation
            y_pred = _predict_observation(x_ti, obs)

            # Residual
            dy = obs.y - y_pred

            # Measurement Jacobian H_i (p×6) at t_i
            H_i = _observation_partials(x_ti, obs)

            # Map to epoch: H̃_i = H_i · Φ(t_i, t_0)  (p×6)
            H_tilde = H_i @ phi_ti

            # Weight matrix W = diag(1/σ²)
            W_diag = 1.0 / (obs.sigma ** 2)  # shape (p,)
            # H̃ᵀ W H̃  and  H̃ᵀ W dy
            for k in range(len(obs.y)):
                w_k = W_diag[k]
                h_k = H_tilde[k, :]  # shape (6,)
                Lambda += w_k * np.outer(h_k, h_k)
                b_vec += w_k * h_k * dy[k]

        # ------------------------------------------------------------------
        # 4b. Add a priori constraint (Tapley §4.3.2)
        #     Normal equation with prior:
        #       (Λ + P₀⁻¹) δX = b + P₀⁻¹ (x0_ref - x0_current)
        # ------------------------------------------------------------------
        Lambda_full = Lambda.copy()
        b_full = b_vec.copy()
        if P0_inv is not None:
            Lambda_full = Lambda + P0_inv
            # A priori residual: how far current reference is from a priori
            b_full = b_vec + P0_inv @ (x0_ref - x0)

        # ------------------------------------------------------------------
        # 5. Solve normal equations.
        #
        # The information matrix Λ = Σ H̃ᵀ W H̃ is theoretically positive
        # semi-definite (PSD) by construction.  Numerically, accumulated
        # floating-point errors in the STM chain can introduce tiny negative
        # eigenvalues (|λ_min| ≪ λ_max) for long or poorly-observed arcs.
        #
        # Strategy: symmetrize Λ, then use an eigenvalue-clipped solve.
        # Eigenvalues below a relative threshold (λ_max × 1e-14) are set to
        # that threshold, restoring positive-definiteness while preserving
        # well-conditioned directions.  This is equivalent to regularisation
        # only in truly unobservable subspaces (Tapley et al. 2004 §4.3.3).
        # ------------------------------------------------------------------

        # Symmetrize (remove anti-symmetric numerical noise from STM products)
        Lambda_full = 0.5 * (Lambda_full + Lambda_full.T)

        # Eigendecomposition and clip.
        # Λ = Σ H̃ᵀ W H̃ is theoretically PSD; negative eigenvalues are
        # numerical noise from STM chain products.  We zero-clip them (set to 0)
        # to obtain the Moore-Penrose pseudo-inverse, which gives zero correction
        # in unobservable directions (Tapley et al. 2004, §4.3.3).
        eigvals_arr, eigvecs = np.linalg.eigh(Lambda_full)
        # Keep only positive eigenvalues (invert them); zero-clip negatives.
        inv_eigvals = np.where(eigvals_arr > 0, 1.0 / eigvals_arr, 0.0)
        Lambda_inv = eigvecs @ np.diag(inv_eigvals) @ eigvecs.T
        dx = Lambda_inv @ b_full

        # Step-size limiter: cap position correction at 50 km and velocity
        # at 0.1 km/s per iteration to prevent divergence from poor
        # linearisation (large initial error).
        pos_step = float(np.linalg.norm(dx[:3]))
        vel_step = float(np.linalg.norm(dx[3:6]))
        max_pos_step = 50.0   # km
        max_vel_step = 0.1    # km/s
        if pos_step > max_pos_step:
            dx[:3] *= max_pos_step / pos_step
        if vel_step > max_vel_step:
            dx[3:6] *= max_vel_step / vel_step

        # ------------------------------------------------------------------
        # 6. Update reference state
        # ------------------------------------------------------------------
        x0 = x0 + dx

        # ------------------------------------------------------------------
        # 7. Convergence check (on position component of δX̄_0)
        # ------------------------------------------------------------------
        pos_change = float(np.linalg.norm(dx[:3]))
        if pos_change < tol_pos_km:
            converged = True
            break

    # Store the final Lambda (observation-only, for covariance estimate)
    Lambda_final = Lambda

    # ------------------------------------------------------------------
    # Final pass: compute post-fit residuals and statistics
    # ------------------------------------------------------------------
    arc_final = _propagate_arc(
        x0, observations,
        mu=mu, include_j2=include_j2, j2=j2, r_earth=r_earth,
    )

    residuals: list[NDArray] = []
    chi2_sum = 0.0
    n_obs_total = 0

    for obs, (x_ti, _phi_ti) in zip(observations, arc_final):
        y_pred = _predict_observation(x_ti, obs)
        resid = obs.y - y_pred
        residuals.append(resid)
        chi2_sum += float(np.sum((resid / obs.sigma) ** 2))
        n_obs_total += len(obs.y)

    dof = max(n_obs_total - 6, 1)
    sigma_0 = math.sqrt(chi2_sum / dof)
    rms_residual = math.sqrt(chi2_sum / n_obs_total) if n_obs_total > 0 else 0.0

    # Formal covariance: P = Λ_full⁻¹ using same eigenvalue-clip as solve.
    # Poorly-observed directions have large (but finite) formal variance.
    Lambda_cov = 0.5 * (Lambda_full + Lambda_full.T)
    try:
        # Lambda_inv is already computed in the last iteration's solve step.
        # Use it directly as the covariance (same eigenvalue decomposition).
        cov = Lambda_inv.copy()
        cov = 0.5 * (cov + cov.T)  # symmetrize numerical noise
    except (NameError, np.linalg.LinAlgError):
        cov = np.full((6, 6), np.nan)

    return ODResult(
        state_epoch=x0,
        covariance=cov,
        residuals=residuals,
        iterations=n_iter,
        converged=converged,
        rms_residual=rms_residual,
        sigma_0=sigma_0,
    )


# ---------------------------------------------------------------------------
# Convenience: generate synthetic observations from truth orbit + noise
# ---------------------------------------------------------------------------

def generate_synthetic_observations(
    r0_truth: NDArray,
    v0_truth: NDArray,
    obs_times: Sequence[float],
    station_eci: NDArray,
    obs_type: Literal["range", "range_rate", "both"] = "both",
    sigma_range_km: float = 0.001,         # 1 m range noise
    sigma_rrate_km_per_s: float = 1e-6,    # 1 mm/s range-rate noise
    seed: int | None = None,
    *,
    mu: float = MU_EARTH,
    include_j2: bool = False,
    j2: float = J2,
    r_earth: float = R_EARTH,
    station_vel_eci: NDArray | None = None,
) -> list[Observation]:
    """Generate synthetic tracking observations from a truth orbit.

    Propagates the truth orbit and adds Gaussian noise.  Used for OD
    validation (noise→0 → estimate→truth).

    Parameters
    ----------
    r0_truth, v0_truth : NDArray, shape (3,)
        True initial state at epoch t=0.
    obs_times : sequence of float
        Observation epoch times [s] relative to epoch.
    station_eci : NDArray, shape (3,)
        Ground station ECI position [km].
    obs_type : {'range', 'range_rate', 'both'}
        Observable type.
    sigma_range_km : float
        1-sigma range measurement noise [km].  Default 1 m.
    sigma_rrate_km_per_s : float
        1-sigma range-rate noise [km/s].  Default 1 mm/s.
    seed : int or None
        NumPy RNG seed for reproducibility.

    Returns
    -------
    list[Observation]
        Synthetic observations sorted by time.
    """
    rng = np.random.default_rng(seed)
    r0 = np.asarray(r0_truth, dtype=float)
    v0 = np.asarray(v0_truth, dtype=float)
    r_gs = np.asarray(station_eci, dtype=float)
    v_gs = np.zeros(3) if station_vel_eci is None else np.asarray(station_vel_eci, dtype=float)

    obs_list: list[Observation] = []
    x_prev = np.concatenate([r0, v0])
    t_prev = 0.0

    for t_i in sorted(obs_times):
        dt = t_i - t_prev
        if dt > 0.0:
            stm_res = propagate_stm(
                x_prev[:3], x_prev[3:6], dt,
                mu=mu, include_j2=include_j2, j2=j2, r_earth=r_earth,
            )
            x_i = stm_res.state_final
        else:
            x_i = x_prev.copy()

        # True range / range-rate
        rho_vec = x_i[:3] - r_gs
        rho_true = float(np.linalg.norm(rho_vec))
        if rho_true < 1e-6:
            rho_true = 1e-6
        rho_dot_true = float(np.dot(rho_vec, x_i[3:6] - v_gs)) / rho_true

        # Add noise
        if obs_type == "range":
            y = np.array([rho_true + rng.normal(0.0, sigma_range_km)])
            sigma = np.array([sigma_range_km])
        elif obs_type == "range_rate":
            y = np.array([rho_dot_true + rng.normal(0.0, sigma_rrate_km_per_s)])
            sigma = np.array([sigma_rrate_km_per_s])
        else:  # both
            noise_rho = rng.normal(0.0, sigma_range_km)
            noise_rrate = rng.normal(0.0, sigma_rrate_km_per_s)
            y = np.array([rho_true + noise_rho, rho_dot_true + noise_rrate])
            sigma = np.array([sigma_range_km, sigma_rrate_km_per_s])

        obs_list.append(
            Observation(
                t=t_i,
                obs_type=obs_type,
                y=y,
                sigma=sigma,
                station_eci=r_gs.copy(),
                station_vel_eci=v_gs.copy(),
            )
        )
        x_prev = x_i
        t_prev = t_i

    return obs_list
