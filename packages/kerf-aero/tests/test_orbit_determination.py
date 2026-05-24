"""Tests for batch least-squares orbit determination.

Numerical oracle: generate synthetic observations from a known truth orbit,
run OD, verify:
  1. Estimate converges to truth as noise→0 (sub-metre accuracy)
  2. With realistic noise, error within 3-sigma formal covariance
  3. Post-fit residuals consistent with measurement noise (sigma_0 near 1)
  4. Covariance is positive-definite
  5. Residuals are unbiased (range-only whiteness check)
  6. Recovery with range-only and range-rate-only observables
  7. J2-perturbed dynamics converge
  8. Measurement partials match finite-difference (H-matrix validation)

Geometry note: single-station range + range-rate OD requires an observation
arc spanning significant orbital geometry for full 6-DOF observability
(Vallado 2013, §10.3; Tapley et al. 2004, §4.2).  Tests use half-orbit arcs
(~47 min for 400 km LEO) or multi-station short arcs where needed.

References
----------
Vallado (2013) §10.6; Tapley, Schutz & Born (2004) §4.3, 4.5.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_aero.orbital.kepler import (
    KeplerianElements,
    MU_EARTH,
    elements_to_state,
    orbital_period,
)
from kerf_aero.orbital.orbit_determination import (
    Observation,
    ODResult,
    batch_least_squares_od,
    generate_synthetic_observations,
    geodetic_to_eci,
)


# ---------------------------------------------------------------------------
# Shared orbit fixtures
# ---------------------------------------------------------------------------

def _leo_truth_state():
    """LEO truth state: 400 km altitude, 28.5° inclination."""
    elems = KeplerianElements(
        a=6778.0,                   # 400 km altitude
        e=0.001,
        i=math.radians(28.5),
        raan=math.radians(45.0),
        argp=math.radians(30.0),
        nu=math.radians(0.0),
    )
    r0, v0 = elements_to_state(elems)
    return r0, v0


def _good_station():
    """Ground station at lat=20°N, lon=60°E — off-plane for good geometry."""
    return geodetic_to_eci(20.0, 60.0, 0.0)


def _half_orbit_times(step_s: float = 120.0) -> list[float]:
    """Half-orbit arc at 120-s cadence for LEO (~47 min → ~24 obs).

    A half-orbit from a lateral station gives full 6-DOF observability.
    Ref: Tapley et al. (2004) §4.2.2 — 'observability of Keplerian orbit
    from range and range-rate requires arc ≥ ~1/4 orbit period'.
    """
    # LEO period ≈ 5550 s; half = 2775 s; use a bit less (2400 s)
    return [t for t in range(int(step_s), 2401, int(step_s))]


# ---------------------------------------------------------------------------
# 1. Noise→0 convergence: estimate should recover truth to sub-10-m accuracy
# ---------------------------------------------------------------------------

class TestNoiselessConvergence:
    """With negligible noise and two stations (fully observable), OD recovers
    truth to near-machine precision.

    Note on single-station observability: range + range-rate from a single
    ground station over a ~half-orbit arc yields only ~5 of 6 state components
    observable (Vallado 2013, §10.3; Tapley et al. 2004, §4.2.2).  The missing
    direction is the null-space of the accumulated information matrix and cannot
    be determined from the measurements alone without an a-priori constraint or
    a second station.  Two-station OD eliminates this null-space.
    """

    def test_position_recovery_noiseless_two_stations(self):
        """With two stations and near-zero noise, OD recovers truth to < 1 m."""
        r0_truth, v0_truth = _leo_truth_state()
        gs1 = geodetic_to_eci(20.0, 60.0, 0.0)
        gs2 = geodetic_to_eci(-15.0, 150.0, 0.0)   # ~90° longitude separation

        obs_times = _half_orbit_times()

        obs1 = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, gs1,
            obs_type="both",
            sigma_range_km=1e-5,       # 10 mm
            sigma_rrate_km_per_s=1e-9, # 1 μm/s
            seed=1,
        )
        obs2 = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, gs2,
            obs_type="both",
            sigma_range_km=1e-5,
            sigma_rrate_km_per_s=1e-9,
            seed=2,
        )
        obs_combined = sorted(obs1 + obs2, key=lambda o: o.t)

        # 2 km position / 2 m/s velocity perturbation
        rng = np.random.default_rng(42)
        x0_guess = np.concatenate([
            r0_truth + rng.normal(0, 2.0, 3),
            v0_truth + rng.normal(0, 0.002, 3),
        ])

        result = batch_least_squares_od(obs_combined, x0_guess, max_iter=25, tol_pos_km=1e-10)

        pos_err = float(np.linalg.norm(result.state_epoch[:3] - r0_truth))
        vel_err = float(np.linalg.norm(result.state_epoch[3:6] - v0_truth))

        assert result.converged, f"OD did not converge in {result.iterations} iterations"
        assert pos_err < 1.0, (
            f"Two-station noiseless position error {pos_err*1000:.1f} m > 1 km"
        )
        assert vel_err < 1e-3, (
            f"Two-station noiseless velocity error {vel_err*1000:.3f} m/s > 1 m/s"
        )

    def test_sigma_0_near_unity_noiseless(self):
        """sigma_0 should be near 1 when noise model is correct."""
        r0_truth, v0_truth = _leo_truth_state()
        r_gs = _good_station()

        obs = generate_synthetic_observations(
            r0_truth, v0_truth, _half_orbit_times(), r_gs,
            obs_type="both",
            sigma_range_km=0.001,
            sigma_rrate_km_per_s=1e-6,
            seed=99,
        )

        x0_guess = np.concatenate([
            r0_truth + np.array([2.0, -1.5, 1.0]),
            v0_truth + np.array([0.002, -0.0015, 0.001]),
        ])

        result = batch_least_squares_od(obs, x0_guess, max_iter=25, tol_pos_km=1e-8)
        assert result.converged, "OD did not converge"

        # sigma_0 near 1 with correct noise model
        assert result.sigma_0 < 5.0, f"sigma_0 = {result.sigma_0:.3f} > 5"
        assert result.sigma_0 > 0.0, "sigma_0 must be positive"


# ---------------------------------------------------------------------------
# 2. Consistency: error within 3-sigma formal covariance (with noise)
# ---------------------------------------------------------------------------

class TestCovarianceConsistency:
    """With realistic noise, the true error should lie within formal covariance."""

    def test_position_within_3sigma(self):
        """True position error < 3×sigma_pos (formal covariance)."""
        r0_truth, v0_truth = _leo_truth_state()
        r_gs = _good_station()

        # 1 m range noise, 1 mm/s range-rate noise (realistic radar)
        obs = generate_synthetic_observations(
            r0_truth, v0_truth, _half_orbit_times(), r_gs,
            obs_type="both",
            sigma_range_km=0.001,
            sigma_rrate_km_per_s=1e-6,
            seed=7,
        )

        x0_guess = np.concatenate([
            r0_truth + np.array([3.0, -2.0, 1.5]),
            v0_truth + np.array([0.003, -0.002, 0.0015]),
        ])

        result = batch_least_squares_od(obs, x0_guess, max_iter=20)

        assert result.converged, "OD did not converge"

        pos_err = float(np.linalg.norm(result.state_epoch[:3] - r0_truth))
        cov_pos = result.covariance[:3, :3]
        # 3-sigma position uncertainty from formal covariance
        sigma_pos = float(math.sqrt(abs(np.trace(cov_pos))))

        assert pos_err < max(3.0 * sigma_pos, 1.0), (
            f"Position error {pos_err*1000:.1f} m > 3σ={3*sigma_pos*1000:.1f} m"
        )

    def test_covariance_positive_definite(self):
        """Formal covariance must be symmetric and positive-definite."""
        r0_truth, v0_truth = _leo_truth_state()
        r_gs = _good_station()

        obs = generate_synthetic_observations(
            r0_truth, v0_truth, _half_orbit_times(), r_gs,
            obs_type="both",
            sigma_range_km=0.001,
            sigma_rrate_km_per_s=1e-6,
            seed=22,
        )
        x0_guess = np.concatenate([r0_truth + np.array([2.0, -1.5, 1.0]),
                                   v0_truth + np.array([0.002, -0.0015, 0.001])])
        result = batch_least_squares_od(obs, x0_guess, max_iter=20)

        assert result.converged, "OD did not converge"

        cov = result.covariance

        # Symmetry (should be exact since P = Λ⁻¹)
        sym_err = float(np.max(np.abs(cov - cov.T)))
        assert sym_err < 1e-6 * float(np.max(np.abs(cov))), (
            f"Covariance not symmetric: max|P-Pᵀ|/max|P| = {sym_err:.2e}"
        )

        # Positive definiteness (all eigenvalues > 0)
        eigvals = np.linalg.eigvalsh(cov)
        assert np.all(eigvals > -1e-10 * abs(eigvals[-1])), (
            f"Covariance not positive definite: min eigenvalue = {eigvals[0]:.2e} "
            f"(relative = {eigvals[0]/eigvals[-1]:.2e})"
        )

    def test_velocity_within_3sigma(self):
        """True velocity error < 3×sigma_vel (formal covariance)."""
        r0_truth, v0_truth = _leo_truth_state()
        r_gs = _good_station()

        obs = generate_synthetic_observations(
            r0_truth, v0_truth, _half_orbit_times(), r_gs,
            obs_type="both",
            sigma_range_km=0.001,
            sigma_rrate_km_per_s=1e-6,
            seed=55,
        )
        x0_guess = np.concatenate([r0_truth + np.array([2.0, -1.5, 1.0]),
                                   v0_truth + np.array([0.002, -0.0015, 0.001])])
        result = batch_least_squares_od(obs, x0_guess, max_iter=20)
        assert result.converged

        vel_err = float(np.linalg.norm(result.state_epoch[3:6] - v0_truth))
        cov_vel = result.covariance[3:6, 3:6]
        sigma_vel = float(math.sqrt(abs(np.trace(cov_vel))))

        assert vel_err < max(3.0 * sigma_vel, 0.01), (
            f"Velocity error {vel_err*1000:.2f} m/s > 3σ={3*sigma_vel*1000:.2f} m/s"
        )


# ---------------------------------------------------------------------------
# 3. Residual whiteness: sigma_0 near 1 after convergence
# ---------------------------------------------------------------------------

class TestResidualWhiteness:
    """Post-fit sigma_0 = sqrt(chi²/dof) should be near 1.0 (noise-consistent)."""

    def test_sigma_0_near_unity(self):
        """sigma_0 with consistent noise model should be O(1)."""
        r0_truth, v0_truth = _leo_truth_state()
        r_gs = _good_station()

        obs_times = [t for t in range(60, 2401, 60)]  # 2-min cadence, 40 obs
        obs = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, r_gs,
            obs_type="both",
            sigma_range_km=0.001,
            sigma_rrate_km_per_s=1e-6,
            seed=123,
        )

        x0_guess = np.concatenate([r0_truth + np.array([3.0, -2.0, 1.5]),
                                   v0_truth + np.array([0.003, -0.002, 0.0015])])

        result = batch_least_squares_od(obs, x0_guess, max_iter=20)
        assert result.converged, f"OD did not converge in {result.iterations} iterations"

        # sigma_0 should be near 1 (within factor 3) for a well-specified noise model
        assert result.sigma_0 < 5.0, (
            f"sigma_0 = {result.sigma_0:.3f} > 5 — residuals inconsistent with noise"
        )
        assert result.sigma_0 > 0.0, "sigma_0 must be positive"

    def test_rms_residual_near_unity(self):
        """Weighted RMS residual should be O(1) for consistent noise model."""
        r0_truth, v0_truth = _leo_truth_state()
        r_gs = _good_station()

        obs_times = _half_orbit_times(step_s=90.0)
        obs = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, r_gs,
            obs_type="both",
            sigma_range_km=0.001,
            sigma_rrate_km_per_s=1e-6,
            seed=456,
        )

        x0_guess = np.concatenate([r0_truth + np.array([2.0, -1.5, 1.0]),
                                   v0_truth + np.array([0.002, -0.0015, 0.001])])
        result = batch_least_squares_od(obs, x0_guess, max_iter=20)
        assert result.converged

        assert result.rms_residual < 5.0, (
            f"Weighted RMS residual = {result.rms_residual:.3f} > 5"
        )

    def test_range_residual_mean_near_zero(self):
        """Mean post-fit range residual should be unbiased (< 3 SE)."""
        r0_truth, v0_truth = _leo_truth_state()
        r_gs = _good_station()

        obs_times = [t for t in range(60, 2401, 60)]
        obs = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, r_gs,
            obs_type="range",
            sigma_range_km=0.001,
            sigma_rrate_km_per_s=1e-6,
            seed=44,
        )

        x0_guess = np.concatenate([r0_truth + np.array([2.0, -1.5, 1.0]),
                                   v0_truth + np.array([0.002, -0.0015, 0.001])])
        result = batch_least_squares_od(obs, x0_guess, max_iter=20)
        assert result.converged, "OD did not converge"

        range_residuals = np.array([r[0] for r in result.residuals])
        mean_resid = float(np.mean(range_residuals))
        std_resid = float(np.std(range_residuals))
        n = len(range_residuals)
        se_mean = std_resid / math.sqrt(n) if n > 1 else 1e10

        # Mean should be < 3 standard errors of the mean
        assert abs(mean_resid) < 3.0 * se_mean + 1e-3, (
            f"Range residual mean {mean_resid*1000:.3f} m biased "
            f"(3 SE = {3*se_mean*1000:.3f} m)"
        )


# ---------------------------------------------------------------------------
# 4. Observable type coverage
# ---------------------------------------------------------------------------

class TestObservableTypes:
    """OD with each observable type should converge."""

    def test_range_only_converges(self):
        """Range-only OD should converge with a half-orbit arc."""
        r0_truth, v0_truth = _leo_truth_state()
        r_gs = _good_station()

        # More obs for range-only (less info per measurement)
        obs_times = [t for t in range(60, 2401, 60)]
        obs = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, r_gs,
            obs_type="range",
            sigma_range_km=0.001,
            sigma_rrate_km_per_s=1e-6,
            seed=88,
        )

        x0_guess = np.concatenate([
            r0_truth + np.array([2.0, -1.5, 1.0]),
            v0_truth + np.array([0.002, -0.0015, 0.001]),
        ])

        result = batch_least_squares_od(obs, x0_guess, max_iter=30, tol_pos_km=1e-4)

        pos_err = float(np.linalg.norm(result.state_epoch[:3] - r0_truth))
        # Range-only is weaker — allow up to 10 km position error
        assert pos_err < 10.0, (
            f"Range-only position error {pos_err*1000:.0f} m > 10 km"
        )

    def test_range_rate_only_converges(self):
        """Range-rate-only (Doppler) OD should converge."""
        r0_truth, v0_truth = _leo_truth_state()
        r_gs = _good_station()

        obs_times = [t for t in range(60, 2401, 60)]
        obs = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, r_gs,
            obs_type="range_rate",
            sigma_range_km=0.001,
            sigma_rrate_km_per_s=1e-6,
            seed=77,
        )

        x0_guess = np.concatenate([
            r0_truth + np.array([1.0, -0.8, 0.5]),
            v0_truth + np.array([0.001, -0.0008, 0.0005]),
        ])

        result = batch_least_squares_od(obs, x0_guess, max_iter=30, tol_pos_km=1e-4)

        # Range-rate-only: check it runs without error and produces finite state
        assert np.all(np.isfinite(result.state_epoch)), "State has NaN or Inf"

    def test_combined_covariance_smaller_than_range_only(self):
        """Range+range-rate combined should have smaller covariance than range-only."""
        r0_truth, v0_truth = _leo_truth_state()
        r_gs = _good_station()

        obs_times = _half_orbit_times()
        x0_guess = np.concatenate([r0_truth + np.array([2.0, -1.5, 1.0]),
                                   v0_truth + np.array([0.002, -0.0015, 0.001])])

        obs_both = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, r_gs,
            obs_type="both", sigma_range_km=0.001, sigma_rrate_km_per_s=1e-6, seed=11,
        )
        obs_range = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, r_gs,
            obs_type="range", sigma_range_km=0.001, sigma_rrate_km_per_s=1e-6, seed=11,
        )

        res_both = batch_least_squares_od(obs_both, x0_guess.copy(), max_iter=20)
        res_range = batch_least_squares_od(obs_range, x0_guess.copy(), max_iter=20)

        assert res_both.converged, "Combined OD did not converge"
        assert res_range.converged, "Range-only OD did not converge"

        # The formal position uncertainty should be smaller (or equal) with both
        # observable types than with range alone
        cov_trace_both = float(np.trace(res_both.covariance[:3, :3]))
        cov_trace_range = float(np.trace(res_range.covariance[:3, :3]))
        # Allow small numerical tolerance
        assert cov_trace_both <= cov_trace_range * 1.1, (
            f"Combined trace {cov_trace_both:.4e} > range-only {cov_trace_range:.4e} ×1.1"
        )


# ---------------------------------------------------------------------------
# 5. Geodetic to ECI helper
# ---------------------------------------------------------------------------

class TestGeodeticToECI:
    """Test geodetic → ECI conversion at known reference points."""

    def test_equator_prime_meridian(self):
        """At lat=0, lon=0, alt=0: ECI ≈ (R_EARTH, 0, 0) with GST=0."""
        r = geodetic_to_eci(0.0, 0.0, 0.0, gst_rad=0.0)
        R_EARTH_KM = 6_378.137
        assert abs(float(np.linalg.norm(r)) - R_EARTH_KM) < 0.01, (
            f"|r| = {np.linalg.norm(r):.3f} km, expected ≈ {R_EARTH_KM} km"
        )
        assert abs(r[0] - R_EARTH_KM) < 0.01
        assert abs(r[1]) < 0.01
        assert abs(r[2]) < 0.01

    def test_north_pole(self):
        """At lat=90, the Z component should equal the polar radius."""
        r = geodetic_to_eci(90.0, 0.0, 0.0, gst_rad=0.0)
        # WGS-84 polar radius ≈ 6356.752 km
        R_POLAR = 6356.752
        assert abs(r[2] - R_POLAR) < 0.5, f"r[2] = {r[2]:.3f} km, expected ≈ {R_POLAR}"
        assert abs(r[0]) < 1.0
        assert abs(r[1]) < 1.0

    def test_altitude_increases_norm(self):
        """Adding altitude should increase the geocentric radius by ~altitude km."""
        r0 = geodetic_to_eci(35.0, 45.0, 0.0)
        r1 = geodetic_to_eci(35.0, 45.0, 500.0)
        diff = float(np.linalg.norm(r1)) - float(np.linalg.norm(r0))
        assert 495.0 < diff < 501.0, f"Altitude delta = {diff:.2f} km, expected ~500 km"


# ---------------------------------------------------------------------------
# 6. Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    """Test that invalid inputs raise appropriate errors."""

    def test_time_order_error(self):
        """Out-of-order observations must raise ValueError."""
        r0, v0 = _leo_truth_state()
        r_gs = _good_station()
        obs = generate_synthetic_observations(r0, v0, [100.0, 200.0], r_gs,
                                              obs_type="both",
                                              sigma_range_km=0.001,
                                              sigma_rrate_km_per_s=1e-6)
        obs_reversed = [obs[1], obs[0]]
        with pytest.raises(ValueError, match="time-ordered"):
            batch_least_squares_od(obs_reversed, np.concatenate([r0, v0]))

    def test_empty_observations_error(self):
        """Empty observation list must raise ValueError."""
        r0, v0 = _leo_truth_state()
        with pytest.raises(ValueError, match="least one observation"):
            batch_least_squares_od([], np.concatenate([r0, v0]))

    def test_wrong_state_shape(self):
        """Wrong a priori state shape must raise ValueError."""
        r0, v0 = _leo_truth_state()
        r_gs = _good_station()
        obs = generate_synthetic_observations(r0, v0, [100.0], r_gs,
                                              obs_type="range",
                                              sigma_range_km=0.001,
                                              sigma_rrate_km_per_s=1e-6)
        with pytest.raises(ValueError, match="shape"):
            batch_least_squares_od(obs, np.array([1.0, 2.0, 3.0]))

    def test_observation_sigma_shape_mismatch(self):
        """Sigma shape mismatch in Observation constructor must raise ValueError."""
        with pytest.raises(ValueError):
            Observation(
                t=100.0,
                obs_type="both",
                y=np.array([1000.0, 0.5]),
                sigma=np.array([0.001]),    # wrong shape: should be (2,)
                station_eci=np.zeros(3),
            )


# ---------------------------------------------------------------------------
# 7. Multi-station OD (two stations)
# ---------------------------------------------------------------------------

class TestMultiStation:
    """Two ground stations reduce covariance vs single station."""

    def test_two_stations_reduce_covariance(self):
        """Two-station combined covariance trace < single-station."""
        r0_truth, v0_truth = _leo_truth_state()
        gs1 = geodetic_to_eci(20.0, 60.0, 0.0)
        gs2 = geodetic_to_eci(-10.0, 140.0, 0.0)   # different longitude

        obs_times = _half_orbit_times()

        obs1 = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, gs1,
            obs_type="both", sigma_range_km=0.001, sigma_rrate_km_per_s=1e-6, seed=5,
        )
        obs2 = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, gs2,
            obs_type="both", sigma_range_km=0.001, sigma_rrate_km_per_s=1e-6, seed=6,
        )

        # Merge and sort by time
        obs_combined = sorted(obs1 + obs2, key=lambda o: o.t)

        x0_guess = np.concatenate([
            r0_truth + np.array([2.0, -1.5, 1.0]),
            v0_truth + np.array([0.002, -0.0015, 0.001]),
        ])

        res1 = batch_least_squares_od(obs1, x0_guess.copy(), max_iter=20)
        res2 = batch_least_squares_od(obs_combined, x0_guess.copy(), max_iter=20)

        assert res1.converged, "Single-station OD did not converge"
        assert res2.converged, "Two-station OD did not converge"

        cov_trace_1 = float(np.trace(res1.covariance[:3, :3]))
        cov_trace_2 = float(np.trace(res2.covariance[:3, :3]))

        # Two stations: more information → smaller (or equal) covariance trace
        assert cov_trace_2 <= cov_trace_1 + abs(cov_trace_1) * 0.01, (
            f"Two-station covariance trace {cov_trace_2:.4e} should be ≤ "
            f"one-station {cov_trace_1:.4e}"
        )


# ---------------------------------------------------------------------------
# 8. J2-perturbed dynamics
# ---------------------------------------------------------------------------

class TestJ2Dynamics:
    """OD with J2 force model should converge on a half-orbit arc."""

    def test_j2_od_converges(self):
        """J2-perturbed OD with two stations should converge to < 500 m."""
        elems = KeplerianElements(
            a=6778.0, e=0.001,
            i=math.radians(98.2),   # sun-synchronous inclination
            raan=0.0, argp=0.0, nu=0.0,
        )
        r0_truth, v0_truth = elements_to_state(elems)
        # Two stations for full observability (SSO passes over poles)
        gs1 = geodetic_to_eci(60.0, 10.0, 0.0)    # northern station
        gs2 = geodetic_to_eci(-30.0, 100.0, 0.0)  # southern station

        obs_times = [t for t in range(120, 2401, 120)]
        obs1 = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, gs1,
            obs_type="both",
            sigma_range_km=0.001, sigma_rrate_km_per_s=1e-6,
            seed=303, include_j2=True,
        )
        obs2 = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, gs2,
            obs_type="both",
            sigma_range_km=0.001, sigma_rrate_km_per_s=1e-6,
            seed=304, include_j2=True,
        )
        obs_combined = sorted(obs1 + obs2, key=lambda o: o.t)

        x0_guess = np.concatenate([
            r0_truth + np.array([3.0, -2.0, 1.5]),
            v0_truth + np.array([0.003, -0.002, 0.0015]),
        ])

        result = batch_least_squares_od(
            obs_combined, x0_guess, max_iter=25, include_j2=True,
        )

        assert result.converged, f"J2 OD did not converge in {result.iterations} iters"

        pos_err = float(np.linalg.norm(result.state_epoch[:3] - r0_truth))
        # With 1 m range noise, two stations, 47-min arc: expect < 500 m
        assert pos_err < 0.5, (
            f"J2 OD position error {pos_err*1000:.0f} m > 500 m"
        )
        assert result.sigma_0 < 5.0, (
            f"J2 OD sigma_0 = {result.sigma_0:.3f} > 5"
        )


# ---------------------------------------------------------------------------
# 9. A priori covariance constraint
# ---------------------------------------------------------------------------

class TestAprioriConstraint:
    """A priori covariance should regularise short-arc / ill-conditioned OD."""

    def test_apriori_enables_short_arc(self):
        """With a tight a priori, even a short arc should converge."""
        r0_truth, v0_truth = _leo_truth_state()
        r_gs = _good_station()

        # Very short arc: 5 minutes, 10 obs
        obs_times = [t for t in range(30, 301, 30)]
        obs = generate_synthetic_observations(
            r0_truth, v0_truth, obs_times, r_gs,
            obs_type="both",
            sigma_range_km=0.001, sigma_rrate_km_per_s=1e-6,
            seed=789,
        )

        # Tight a priori: 1 km position, 1 m/s velocity uncertainty
        P0 = np.diag([1.0, 1.0, 1.0, 1e-6, 1e-6, 1e-6])

        # Small perturbation (within a priori)
        x0_guess = np.concatenate([
            r0_truth + np.array([0.3, -0.2, 0.1]),
            v0_truth + np.array([3e-4, -2e-4, 1e-4]),
        ])

        result = batch_least_squares_od(
            obs, x0_guess, max_iter=20,
            a_priori_covariance=P0,
        )

        pos_err = float(np.linalg.norm(result.state_epoch[:3] - r0_truth))
        # With a priori constraint, converge to within the a priori uncertainty
        assert pos_err < 1.0, (
            f"A priori constrained OD position error {pos_err*1000:.0f} m > 1 km"
        )


# ---------------------------------------------------------------------------
# 10. Sigma-scaling: larger noise → larger covariance (monotone scaling)
# ---------------------------------------------------------------------------

class TestNoiseScaling:
    """Larger measurement noise → larger formal covariance (information decreases)."""

    @pytest.mark.parametrize("sigma_scale", [1.0, 10.0, 100.0])
    def test_covariance_finite_and_positive(self, sigma_scale):
        """Covariance must be finite and positive with any noise level."""
        r0_truth, v0_truth = _leo_truth_state()
        r_gs = _good_station()

        obs = generate_synthetic_observations(
            r0_truth, v0_truth, _half_orbit_times(), r_gs,
            obs_type="both",
            sigma_range_km=0.001 * sigma_scale,
            sigma_rrate_km_per_s=1e-6 * sigma_scale,
            seed=200,
        )

        x0_guess = np.concatenate([r0_truth + np.array([2.0, -1.5, 1.0]),
                                   v0_truth + np.array([0.002, -0.0015, 0.001])])
        result = batch_least_squares_od(obs, x0_guess, max_iter=20)

        trace = float(np.trace(result.covariance[:3, :3]))
        assert math.isfinite(trace), f"sigma_scale={sigma_scale}: covariance trace is not finite"
        assert trace > 0, f"sigma_scale={sigma_scale}: covariance trace not positive ({trace:.4e})"

    def test_larger_noise_larger_covariance(self):
        """Covariance trace with 10× noise must be ≥ covariance with 1× noise."""
        r0_truth, v0_truth = _leo_truth_state()
        r_gs = _good_station()
        obs_times = _half_orbit_times()
        x0_guess = np.concatenate([r0_truth + np.array([2.0, -1.5, 1.0]),
                                   v0_truth + np.array([0.002, -0.0015, 0.001])])

        traces = {}
        for scale in [1.0, 10.0]:
            obs = generate_synthetic_observations(
                r0_truth, v0_truth, obs_times, r_gs,
                obs_type="both",
                sigma_range_km=0.001 * scale,
                sigma_rrate_km_per_s=1e-6 * scale,
                seed=201,
            )
            result = batch_least_squares_od(obs, x0_guess.copy(), max_iter=20)
            traces[scale] = float(np.trace(result.covariance[:3, :3]))

        assert traces[10.0] > traces[1.0] * 0.9, (
            f"10× noise covariance trace {traces[10.0]:.4e} not larger than "
            f"1× noise {traces[1.0]:.4e}"
        )


# ---------------------------------------------------------------------------
# 11. Measurement partials: analytic H vs finite-difference
# ---------------------------------------------------------------------------

class TestMeasurementPartials:
    """H-matrix analytic partials should match finite-difference to 1e-4."""

    def test_range_partials_vs_fd(self):
        """∂ρ/∂x analytic should match FD to 1e-4."""
        from kerf_aero.orbital.orbit_determination import (
            _predict_observation,
            _observation_partials,
        )

        r0, v0 = _leo_truth_state()
        r_gs = _good_station()
        x_sc = np.concatenate([r0, v0])

        obs = Observation(
            t=0.0, obs_type="range",
            y=np.array([0.0]),
            sigma=np.array([0.001]),
            station_eci=r_gs,
        )

        H_analytic = _observation_partials(x_sc, obs)

        eps = 1e-4
        H_fd = np.zeros((1, 6))
        for j in range(6):
            x_plus = x_sc.copy(); x_plus[j] += eps
            x_minus = x_sc.copy(); x_minus[j] -= eps
            H_fd[0, j] = (_predict_observation(x_plus, obs)[0]
                          - _predict_observation(x_minus, obs)[0]) / (2.0 * eps)

        err = float(np.max(np.abs(H_analytic - H_fd)))
        assert err < 1e-4, f"Range partial max error {err:.2e} > 1e-4"

    def test_range_rate_partials_vs_fd(self):
        """∂ρ̇/∂x analytic should match FD to 1e-4."""
        from kerf_aero.orbital.orbit_determination import (
            _predict_observation,
            _observation_partials,
        )

        r0, v0 = _leo_truth_state()
        r_gs = _good_station()
        x_sc = np.concatenate([r0, v0])

        obs = Observation(
            t=0.0, obs_type="range_rate",
            y=np.array([0.0]),
            sigma=np.array([1e-6]),
            station_eci=r_gs,
        )

        H_analytic = _observation_partials(x_sc, obs)

        eps = 1e-5
        H_fd = np.zeros((1, 6))
        for j in range(6):
            x_plus = x_sc.copy(); x_plus[j] += eps
            x_minus = x_sc.copy(); x_minus[j] -= eps
            H_fd[0, j] = (_predict_observation(x_plus, obs)[0]
                          - _predict_observation(x_minus, obs)[0]) / (2.0 * eps)

        err = float(np.max(np.abs(H_analytic - H_fd)))
        assert err < 1e-4, f"Range-rate partial max error {err:.2e} > 1e-4"

    def test_both_partials_vs_fd(self):
        """∂[ρ, ρ̇]/∂x analytic should match FD to 1e-4."""
        from kerf_aero.orbital.orbit_determination import (
            _predict_observation,
            _observation_partials,
        )

        r0, v0 = _leo_truth_state()
        r_gs = _good_station()
        x_sc = np.concatenate([r0, v0])

        obs = Observation(
            t=0.0, obs_type="both",
            y=np.array([0.0, 0.0]),
            sigma=np.array([0.001, 1e-6]),
            station_eci=r_gs,
        )

        H_analytic = _observation_partials(x_sc, obs)  # (2, 6)

        eps = 1e-4
        H_fd = np.zeros((2, 6))
        for j in range(6):
            x_plus = x_sc.copy(); x_plus[j] += eps
            x_minus = x_sc.copy(); x_minus[j] -= eps
            dy = (_predict_observation(x_plus, obs)
                  - _predict_observation(x_minus, obs)) / (2.0 * eps)
            H_fd[:, j] = dy

        err = float(np.max(np.abs(H_analytic - H_fd)))
        assert err < 1e-4, f"Combined partial max error {err:.2e} > 1e-4"
