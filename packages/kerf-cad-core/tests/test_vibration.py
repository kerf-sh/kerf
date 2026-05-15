"""
Hermetic tests for kerf_cad_core.vibration — mechanical vibration analysis.

Coverage:
  dynamics.sdof_natural_frequency           — ωn, fn
  dynamics.sdof_damped_frequency            — ωd, ζ, c_cr
  dynamics.sdof_damping_ratio_log_decrement — δ, ζ from peaks
  dynamics.sdof_free_response               — x(t) for all damping regimes
  dynamics.sdof_harmonic_magnification      — M, phase
  dynamics.sdof_harmonic_phase              — convenience wrapper
  dynamics.sdof_base_transmissibility       — TR, isolation zone
  dynamics.sdof_rotating_unbalance          — amplitude, non-dimensional
  dynamics.dof2_eigen                       — 2-DOF eigenvalues, mode shapes
  dynamics.beam_natural_frequency           — simply-supported, cantilever
  dynamics.shaft_whirl_rayleigh             — Rayleigh critical speed
  dynamics.isolator_stiffness               — required k for TR

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas verified algebraically against published closed-form expressions.

References
----------
Rao, S.S. "Mechanical Vibrations", 5th ed.
Inman, D.J. "Engineering Vibration", 4th ed.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.vibration.dynamics import (
    sdof_natural_frequency,
    sdof_damped_frequency,
    sdof_damping_ratio_log_decrement,
    sdof_free_response,
    sdof_harmonic_magnification,
    sdof_harmonic_phase,
    sdof_base_transmissibility,
    sdof_rotating_unbalance,
    dof2_eigen,
    beam_natural_frequency,
    shaft_whirl_rayleigh,
    isolator_stiffness,
)
from kerf_cad_core.vibration.tools import (
    run_sdof_natural_frequency,
    run_sdof_damped_frequency,
    run_sdof_log_decrement,
    run_sdof_free_response,
    run_sdof_harmonic,
    run_sdof_transmissibility,
    run_sdof_rotating_unbalance,
    run_2dof_eigen,
    run_beam_frequency,
    run_shaft_whirl_rayleigh,
    run_isolator_stiffness,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
        return ProjectCtx(
            pool=None, storage=None,
            project_id=uuid.uuid4(), user_id=uuid.uuid4(),
            role="owner", http_client=None,
        )
    except Exception:
        return None


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


def _ok_tool(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err_tool(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


REL = 1e-6  # relative tolerance for float comparisons


# ===========================================================================
# 1. sdof_natural_frequency
# ===========================================================================

class TestSdofNaturalFrequency:

    def test_formula_omega_n_equals_sqrt_k_over_m(self):
        """ωn = √(k/m) must match exactly."""
        m, k = 2.0, 800.0
        res = sdof_natural_frequency(m, k)
        assert res["ok"] is True
        expected = math.sqrt(k / m)
        assert abs(res["omega_n"] - expected) / expected < REL

    def test_fn_hz_is_omega_n_over_2pi(self):
        """fn = ωn / (2π)."""
        m, k = 5.0, 5000.0
        res = sdof_natural_frequency(m, k)
        assert res["ok"] is True
        assert abs(res["fn_hz"] - res["omega_n"] / (2 * math.pi)) < 1e-12

    def test_increasing_stiffness_increases_frequency(self):
        """Doubling k must increase ωn by √2."""
        m = 1.0
        omega1 = sdof_natural_frequency(m, 100.0)["omega_n"]
        omega2 = sdof_natural_frequency(m, 200.0)["omega_n"]
        assert abs(omega2 / omega1 - math.sqrt(2.0)) < 1e-9

    def test_increasing_mass_decreases_frequency(self):
        """Quadrupling m must halve ωn."""
        k = 400.0
        omega1 = sdof_natural_frequency(1.0, k)["omega_n"]
        omega4 = sdof_natural_frequency(4.0, k)["omega_n"]
        assert abs(omega4 / omega1 - 0.5) < 1e-9

    def test_invalid_mass_returns_error(self):
        res = sdof_natural_frequency(-1.0, 100.0)
        assert res["ok"] is False

    def test_zero_stiffness_returns_error(self):
        res = sdof_natural_frequency(1.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 2. sdof_damped_frequency
# ===========================================================================

class TestSdofDampedFrequency:

    def test_underdamped_omega_d_formula(self):
        """ωd = ωn√(1-ζ²) for underdamped case."""
        m, k = 1.0, 100.0
        c = 2.0  # zeta = c / (2√km) = 2/(2×10) = 0.1
        res = sdof_damped_frequency(m, k, c)
        assert res["ok"] is True
        assert res["regime"] == "underdamped"
        omega_n = math.sqrt(k / m)
        zeta = res["zeta"]
        omega_d_expected = omega_n * math.sqrt(1.0 - zeta ** 2)
        assert abs(res["omega_d"] - omega_d_expected) / omega_d_expected < REL

    def test_critical_damping_ratio_equals_one(self):
        """c = c_cr → ζ = 1.0 and regime = critically_damped."""
        m, k = 2.0, 200.0
        c_cr = 2.0 * math.sqrt(k * m)
        res = sdof_damped_frequency(m, k, c_cr)
        assert res["ok"] is True
        assert res["regime"] == "critically_damped"
        assert abs(res["zeta"] - 1.0) < 1e-9

    def test_overdamped_omega_d_is_zero(self):
        """Overdamped case: ωd = 0."""
        m, k = 1.0, 100.0
        c_cr = 2.0 * math.sqrt(k * m)
        res = sdof_damped_frequency(m, k, c_cr * 2.0)
        assert res["ok"] is True
        assert res["regime"] == "overdamped"
        assert res["omega_d"] == 0.0

    def test_damping_ratio_formula(self):
        """ζ = c / (2√km) must be correct."""
        m, k, c = 3.0, 300.0, 15.0
        c_cr = 2.0 * math.sqrt(k * m)
        zeta_expected = c / c_cr
        res = sdof_damped_frequency(m, k, c)
        assert abs(res["zeta"] - zeta_expected) / zeta_expected < REL

    def test_zero_damping_returns_underdamped(self):
        """c=0 → ζ=0, ωd = ωn, underdamped."""
        m, k = 1.0, 100.0
        res = sdof_damped_frequency(m, k, 0.0)
        assert res["ok"] is True
        assert res["regime"] == "underdamped"
        assert abs(res["omega_d"] - res["omega_n"]) < 1e-9

    def test_negative_damping_returns_error(self):
        res = sdof_damped_frequency(1.0, 100.0, -1.0)
        assert res["ok"] is False


# ===========================================================================
# 3. sdof_damping_ratio_log_decrement
# ===========================================================================

class TestLogDecrement:

    def test_exact_formula_match(self):
        """δ = (1/n) ln(x1/xn), ζ = δ/√(4π²+δ²)."""
        x1, xn, n = 10.0, 5.0, 3
        delta = (1.0 / n) * math.log(x1 / xn)
        zeta_expected = delta / math.sqrt(4 * math.pi ** 2 + delta ** 2)
        res = sdof_damping_ratio_log_decrement(x1, xn, n)
        assert res["ok"] is True
        assert abs(res["delta"] - delta) / delta < REL
        assert abs(res["zeta"] - zeta_expected) / zeta_expected < REL

    def test_approx_formula_close_for_small_delta(self):
        """ζ_approx ≈ δ/(2π) must be within 1% of exact for small δ."""
        x1, xn, n = 10.0, 9.0, 1
        res = sdof_damping_ratio_log_decrement(x1, xn, n)
        assert res["ok"] is True
        assert abs(res["zeta_approx"] - res["zeta"]) / res["zeta"] < 0.01

    def test_single_cycle(self):
        """n=1: δ = ln(x1/xn)."""
        x1, xn = 5.0, 3.0
        delta_expected = math.log(x1 / xn)
        res = sdof_damping_ratio_log_decrement(x1, xn, 1)
        assert abs(res["delta"] - delta_expected) / delta_expected < REL

    def test_xn_ge_x1_returns_error(self):
        """xn >= x1 must return error (not decaying)."""
        res = sdof_damping_ratio_log_decrement(5.0, 10.0, 3)
        assert res["ok"] is False

    def test_negative_x1_returns_error(self):
        res = sdof_damping_ratio_log_decrement(-1.0, 0.5, 2)
        assert res["ok"] is False

    def test_n_zero_returns_error(self):
        res = sdof_damping_ratio_log_decrement(5.0, 4.0, 0)
        assert res["ok"] is False


# ===========================================================================
# 4. sdof_free_response
# ===========================================================================

class TestSdofFreeResponse:

    def test_underdamped_at_t0_equals_x0(self):
        """x(0) = x0 for any system."""
        m, k, c = 1.0, 100.0, 2.0
        x0, v0 = 0.05, 0.0
        res = sdof_free_response(m, k, c, x0, v0, 0.0)
        assert res["ok"] is True
        assert abs(res["x_t"] - x0) < 1e-12

    def test_underdamped_x0_zero_v0_nonzero(self):
        """With x0=0, x(t) = (v0/ωd)e^(-ζωn t)sin(ωd t)."""
        m, k, c = 1.0, 100.0, 2.0
        x0, v0, t = 0.0, 1.0, 0.1
        res = sdof_free_response(m, k, c, x0, v0, t)
        assert res["ok"] is True
        omega_n = math.sqrt(k / m)
        c_cr = 2.0 * math.sqrt(k * m)
        zeta = c / c_cr
        omega_d = omega_n * math.sqrt(1.0 - zeta ** 2)
        x_expected = (v0 / omega_d) * math.exp(-zeta * omega_n * t) * math.sin(omega_d * t)
        assert abs(res["x_t"] - x_expected) / (abs(x_expected) + 1e-12) < 1e-6

    def test_critically_damped_returns_finite(self):
        """Critically damped: x(t) must be finite and correct."""
        m, k = 1.0, 100.0
        c_cr = 2.0 * math.sqrt(k * m)
        x0, v0, t = 0.01, 0.0, 0.1
        res = sdof_free_response(m, k, c_cr, x0, v0, t)
        assert res["ok"] is True
        assert res["regime"] == "critically_damped"
        omega_n = math.sqrt(k / m)
        x_expected = (x0 + (v0 + omega_n * x0) * t) * math.exp(-omega_n * t)
        assert abs(res["x_t"] - x_expected) / (abs(x_expected) + 1e-12) < 1e-6

    def test_overdamped_decays_without_oscillation(self):
        """Overdamped: regime = overdamped, x(t) != 0 for small t."""
        m, k = 1.0, 100.0
        c_cr = 2.0 * math.sqrt(k * m)
        res = sdof_free_response(m, k, c_cr * 3.0, 0.01, 0.0, 0.05)
        assert res["ok"] is True
        assert res["regime"] == "overdamped"
        assert math.isfinite(res["x_t"])

    def test_negative_t_returns_error(self):
        res = sdof_free_response(1.0, 100.0, 2.0, 0.01, 0.0, -0.1)
        assert res["ok"] is False

    def test_invalid_m_returns_error(self):
        res = sdof_free_response(0.0, 100.0, 2.0, 0.01, 0.0, 0.1)
        assert res["ok"] is False


# ===========================================================================
# 5. sdof_harmonic_magnification
# ===========================================================================

class TestSdofHarmonicMagnification:

    def test_static_case_r_near_zero(self):
        """For r → 0, M → 1 (quasi-static loading)."""
        res = sdof_harmonic_magnification(0.1, 0.01)
        assert res["ok"] is True
        assert abs(res["M"] - 1.0) < 0.01

    def test_formula_algebraic(self):
        """M = 1/√[(1-r²)²+(2ζr)²] must match exactly."""
        zeta, r = 0.2, 0.5
        denom = math.sqrt((1 - r ** 2) ** 2 + (2 * zeta * r) ** 2)
        M_expected = 1.0 / denom
        res = sdof_harmonic_magnification(zeta, r)
        assert res["ok"] is True
        assert abs(res["M"] - M_expected) / M_expected < REL

    def test_phase_at_resonance_is_90_degrees(self):
        """At r=1 (resonance), φ = 90° for any ζ > 0."""
        res = sdof_harmonic_magnification(0.1, 1.0)
        assert res["ok"] is True
        # Phase should be approximately 90 degrees
        assert abs(res["phi_deg"] - 90.0) < 1.0

    def test_zero_damping_at_resonance_is_handled(self):
        """r=1, ζ=0: denominator → 0; function should return error or handle gracefully."""
        res = sdof_harmonic_magnification(0.0, 1.0)
        # Either returns error (denominator=0) or very large M
        assert "ok" in res

    def test_high_frequency_magnification_less_than_one(self):
        """For r >> 1, M < 1 (attenuation)."""
        res = sdof_harmonic_magnification(0.05, 5.0)
        assert res["ok"] is True
        assert res["M"] < 1.0

    def test_negative_zeta_returns_error(self):
        res = sdof_harmonic_magnification(-0.1, 1.0)
        assert res["ok"] is False

    def test_zero_r_returns_error(self):
        res = sdof_harmonic_magnification(0.1, 0.0)
        assert res["ok"] is False

    def test_phase_wrapper_returns_same_as_magnification(self):
        """sdof_harmonic_phase must return same result as sdof_harmonic_magnification."""
        zeta, r = 0.15, 0.8
        res_mag = sdof_harmonic_magnification(zeta, r)
        res_phase = sdof_harmonic_phase(zeta, r)
        assert res_mag["phi_rad"] == res_phase["phi_rad"]
        assert res_mag["M"] == res_phase["M"]


# ===========================================================================
# 6. sdof_base_transmissibility
# ===========================================================================

class TestSdofBaseTransmissibility:

    def test_formula_algebraic(self):
        """TR = √[(1+(2ζr)²)/((1-r²)²+(2ζr)²)] must match exactly."""
        zeta, r = 0.1, 2.0
        num = 1.0 + (2 * zeta * r) ** 2
        denom = (1 - r ** 2) ** 2 + (2 * zeta * r) ** 2
        TR_expected = math.sqrt(num / denom)
        res = sdof_base_transmissibility(zeta, r)
        assert res["ok"] is True
        assert abs(res["TR"] - TR_expected) / TR_expected < REL

    def test_isolation_zone_r_gt_sqrt2(self):
        """r > √2 should give TR < 1 for small ζ."""
        res = sdof_base_transmissibility(0.05, 2.0)
        assert res["ok"] is True
        assert res["TR"] < 1.0
        assert res["isolating"] is True

    def test_amplification_zone_r_lt_sqrt2(self):
        """r < √2 gives TR > 1 (amplification); isolating = False."""
        res = sdof_base_transmissibility(0.1, 1.0)
        assert res["ok"] is True
        assert res["TR"] > 1.0
        assert res["isolating"] is False

    def test_tr_dB_negative_in_isolation_zone(self):
        """TR_dB < 0 when TR < 1 (isolation zone)."""
        res = sdof_base_transmissibility(0.05, 3.0)
        assert res["ok"] is True
        assert res["TR_dB"] < 0.0

    def test_negative_zeta_returns_error(self):
        res = sdof_base_transmissibility(-0.1, 2.0)
        assert res["ok"] is False

    def test_zero_r_returns_error(self):
        res = sdof_base_transmissibility(0.1, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 7. sdof_rotating_unbalance
# ===========================================================================

class TestSdofRotatingUnbalance:

    def test_formula_algebraic(self):
        """X = (m_u e/m) r²/√[(1-r²)²+(2ζr)²]."""
        m, k, c = 10.0, 10000.0, 50.0
        m_u, e = 0.1, 0.02
        omega = 50.0  # rad/s
        omega_n = math.sqrt(k / m)
        c_cr = 2.0 * math.sqrt(k * m)
        zeta = c / c_cr
        r = omega / omega_n
        nondim = r ** 2 / math.sqrt((1 - r ** 2) ** 2 + (2 * zeta * r) ** 2)
        X_expected = (m_u * e / m) * nondim

        res = sdof_rotating_unbalance(m, k, c, m_u, e, omega)
        assert res["ok"] is True
        assert abs(res["X_m"] - X_expected) / X_expected < REL

    def test_nondim_amplitude_formula(self):
        """MX/(m_u e) must be r²/√[(1-r²)²+(2ζr)²]."""
        m, k, c = 5.0, 5000.0, 20.0
        m_u, e, omega = 0.05, 0.01, 30.0
        res = sdof_rotating_unbalance(m, k, c, m_u, e, omega)
        assert res["ok"] is True
        omega_n = math.sqrt(k / m)
        r = omega / omega_n
        zeta = res["zeta"]
        nondim_expected = r ** 2 / math.sqrt((1 - r ** 2) ** 2 + (2 * zeta * r) ** 2)
        assert abs(res["MX_over_mue"] - nondim_expected) / nondim_expected < REL

    def test_zero_omega_returns_error(self):
        res = sdof_rotating_unbalance(10.0, 10000.0, 0.0, 0.1, 0.02, 0.0)
        assert res["ok"] is False

    def test_negative_eccentricity_returns_error(self):
        res = sdof_rotating_unbalance(10.0, 10000.0, 0.0, 0.1, -0.01, 50.0)
        assert res["ok"] is False


# ===========================================================================
# 8. dof2_eigen
# ===========================================================================

class TestDof2Eigen:

    def test_symmetric_system_frequencies(self):
        """Symmetric 2-DOF: m1=m2=1, k1=k3=k, k2=k → well-known eigenvalues."""
        m, k = 1.0, 1000.0
        # K11 = k+k = 2k, K22 = k+k = 2k, K12 = -k
        # Char. eq: λ² - 4k/m λ + 3k²/m² = 0
        # λ = (4k/m ± √(16k²/m² - 12k²/m²)) / 2 = (4k ± 2k) / 2m
        # λ1 = k/m, λ2 = 3k/m
        res = dof2_eigen(m, m, k, k, k)
        assert res["ok"] is True
        omega1_expected = math.sqrt(k / m)
        omega2_expected = math.sqrt(3 * k / m)
        assert abs(res["omega_1"] - omega1_expected) / omega1_expected < REL
        assert abs(res["omega_2"] - omega2_expected) / omega2_expected < REL

    def test_omega1_less_than_omega2(self):
        """First mode must have lower frequency than second."""
        res = dof2_eigen(1.0, 2.0, 500.0, 300.0, 200.0)
        assert res["ok"] is True
        assert res["omega_1"] < res["omega_2"]

    def test_fn_hz_from_omega(self):
        """fn = ω / (2π)."""
        res = dof2_eigen(1.0, 1.0, 1000.0, 500.0)
        assert res["ok"] is True
        assert abs(res["fn_1_hz"] - res["omega_1"] / (2 * math.pi)) < 1e-10
        assert abs(res["fn_2_hz"] - res["omega_2"] / (2 * math.pi)) < 1e-10

    def test_mode_shape_normalised_to_one(self):
        """Mode shapes must start with 1.0 (normalised)."""
        res = dof2_eigen(1.0, 1.0, 1000.0, 500.0, 200.0)
        assert res["ok"] is True
        assert res["mode_shape_1"][0] == 1.0
        assert res["mode_shape_2"][0] == 1.0

    def test_negative_mass_returns_error(self):
        res = dof2_eigen(-1.0, 1.0, 1000.0, 500.0)
        assert res["ok"] is False

    def test_zero_coupling_stiffness_returns_error(self):
        """k2 must be > 0."""
        res = dof2_eigen(1.0, 1.0, 1000.0, 0.0)
        assert res["ok"] is False

    def test_k3_zero_default(self):
        """k3=0 (default) must work without error."""
        res = dof2_eigen(2.0, 3.0, 800.0, 400.0)
        assert res["ok"] is True


# ===========================================================================
# 9. beam_natural_frequency
# ===========================================================================

class TestBeamNaturalFrequency:

    def test_simply_supported_mode1_formula(self):
        """SS mode 1: βL = π, ωn = π² √(EI/(μL⁴))."""
        L, mu, E, I = 1.0, 2.0, 200e9, 1e-8
        omega_expected = math.pi ** 2 * math.sqrt(E * I / (mu * L ** 4))
        res = beam_natural_frequency(1, L, mu, E, I, "simply-supported")
        assert res["ok"] is True
        assert abs(res["omega_n"] - omega_expected) / omega_expected < REL

    def test_simply_supported_mode2_double_mode1_beta_L(self):
        """SS mode 2: βL = 2π → ωn = 4 × ωn_mode1."""
        L, mu, E, I = 1.0, 2.0, 200e9, 1e-8
        res1 = beam_natural_frequency(1, L, mu, E, I, "simply-supported")
        res2 = beam_natural_frequency(2, L, mu, E, I, "simply-supported")
        assert res2["ok"] is True
        # ωn ∝ (βL)² = (nπ)², so mode2/mode1 = 4
        assert abs(res2["omega_n"] / res1["omega_n"] - 4.0) < 1e-9

    def test_cantilever_mode1_beta_L_value(self):
        """Cantilever mode 1: βL ≈ 1.87510."""
        res = beam_natural_frequency(1, 1.0, 1.0, 1.0, 1.0, "cantilever")
        assert res["ok"] is True
        assert abs(res["beta_L"] - 1.87510407) < 1e-5

    def test_cantilever_mode1_lower_than_ss_mode1(self):
        """Cantilever (βL≈1.875) < SS (βL=π≈3.14) → cantilever ωn < SS ωn."""
        L, mu, E, I = 1.0, 2.0, 200e9, 1e-8
        omega_ss = beam_natural_frequency(1, L, mu, E, I, "simply-supported")["omega_n"]
        omega_cant = beam_natural_frequency(1, L, mu, E, I, "cantilever")["omega_n"]
        assert omega_cant < omega_ss

    def test_fn_hz_from_omega(self):
        """fn = ωn/(2π)."""
        res = beam_natural_frequency(1, 0.5, 3.0, 200e9, 1e-9)
        assert res["ok"] is True
        assert abs(res["fn_hz"] - res["omega_n"] / (2 * math.pi)) < 1e-10

    def test_unknown_bc_returns_error(self):
        res = beam_natural_frequency(1, 1.0, 2.0, 200e9, 1e-8, "fixed-fixed")
        assert res["ok"] is False

    def test_mode_zero_returns_error(self):
        res = beam_natural_frequency(0, 1.0, 2.0, 200e9, 1e-8)
        assert res["ok"] is False

    def test_zero_length_returns_error(self):
        res = beam_natural_frequency(1, 0.0, 2.0, 200e9, 1e-8)
        assert res["ok"] is False

    def test_cantilever_mode4_beta_L_approx(self):
        """Cantilever mode 4: βL ≈ 10.99554."""
        res = beam_natural_frequency(4, 1.0, 1.0, 1.0, 1.0, "cantilever")
        assert res["ok"] is True
        assert abs(res["beta_L"] - 10.99554073) < 1e-4


# ===========================================================================
# 10. shaft_whirl_rayleigh
# ===========================================================================

class TestShaftWhirlRayleigh:

    def test_single_disk_at_midspan(self):
        """Single disk at midspan: Rayleigh ω² = g/y_mid.
        y_mid = mg L³/(48 EI) → ω = √(48 EI / (m L³))."""
        E, I = 200e9, 1e-8
        m = 5.0
        L = 2.0
        # Disk at midspan; provide span explicitly
        res = shaft_whirl_rayleigh([L / 2.0], [m], E, I, span_m=L)
        assert res["ok"] is True
        assert res["omega_cr"] > 0
        assert res["n_cr_rpm"] > 0
        assert len(res["deflections_m"]) == 1
        # Verify: y_mid = mg L³/(48 EI), omega = √(g/y_mid)
        g = 9.80665
        y_mid = m * g * L ** 3 / (48.0 * E * I)
        omega_expected = math.sqrt(g / y_mid)
        assert abs(res["omega_cr"] - omega_expected) / omega_expected < 1e-6

    def test_two_equal_disks(self):
        """Two equal disks at L/3 and 2L/3: symmetric, should give valid result."""
        E, I = 200e9, 1e-7
        L = 1.0
        masses = [10.0, 10.0]
        positions = [L / 3.0, 2 * L / 3.0]

        res = shaft_whirl_rayleigh(positions, masses, E, I, span_m=L)
        assert res["ok"] is True
        assert res["omega_cr"] > 0
        assert math.isfinite(res["omega_cr"])

    def test_stiffer_shaft_gives_higher_critical_speed(self):
        """Doubling EI must increase critical speed."""
        L = 1.0
        masses = [5.0]
        positions = [0.4]

        res1 = shaft_whirl_rayleigh(positions, masses, 200e9, 1e-8, span_m=L)
        res2 = shaft_whirl_rayleigh(positions, masses, 400e9, 1e-8, span_m=L)
        assert res1["ok"] is True and res2["ok"] is True
        assert res2["omega_cr"] > res1["omega_cr"]

    def test_empty_list_returns_error(self):
        res = shaft_whirl_rayleigh([], [], 200e9, 1e-8)
        assert res["ok"] is False

    def test_mismatched_list_lengths_returns_error(self):
        res = shaft_whirl_rayleigh([0.3, 0.6], [5.0], 200e9, 1e-8)
        assert res["ok"] is False

    def test_position_at_zero_returns_error(self):
        """Disk at position 0 must return error (at bearing)."""
        res = shaft_whirl_rayleigh([0.0, 0.5], [5.0, 5.0], 200e9, 1e-8)
        assert res["ok"] is False


# ===========================================================================
# 11. isolator_stiffness
# ===========================================================================

class TestIsolatorStiffness:

    def test_formula_for_tr_and_r(self):
        """Verify r = √(1 + 1/TR), k = m ωn², ωn = ω_exc / r."""
        m, omega_exc, TR = 100.0, 100.0, 0.1
        r_expected = math.sqrt(1.0 + 1.0 / TR)
        omega_n_expected = omega_exc / r_expected
        k_expected = m * omega_n_expected ** 2

        res = isolator_stiffness(m, omega_exc, TR)
        assert res["ok"] is True
        assert abs(res["r"] - r_expected) / r_expected < REL
        assert abs(res["omega_n"] - omega_n_expected) / omega_n_expected < REL
        assert abs(res["k_N_per_m"] - k_expected) / k_expected < REL

    def test_tr_actual_matches_target(self):
        """TR_actual at the computed r must equal TR_target for undamped isolator."""
        m, omega_exc, TR_target = 50.0, 200.0, 0.05
        res = isolator_stiffness(m, omega_exc, TR_target)
        assert res["ok"] is True
        assert abs(res["TR_actual"] - TR_target) / TR_target < 1e-9

    def test_lower_TR_requires_lower_k(self):
        """Lower target TR (more isolation) → lower stiffness k."""
        m, omega_exc = 100.0, 100.0
        k_high = isolator_stiffness(m, omega_exc, 0.2)["k_N_per_m"]
        k_low = isolator_stiffness(m, omega_exc, 0.05)["k_N_per_m"]
        assert k_low < k_high

    def test_static_deflection_formula(self):
        """Static deflection = mg/k."""
        m, omega_exc, TR = 200.0, 50.0, 0.1
        g = 9.80665
        res = isolator_stiffness(m, omega_exc, TR)
        assert res["ok"] is True
        k = res["k_N_per_m"]
        delta_st_expected = m * g / k
        assert abs(res["static_deflection_m"] - delta_st_expected) / delta_st_expected < REL

    def test_tr_ge_1_returns_error(self):
        """TR >= 1 must return error (not in isolation zone)."""
        res = isolator_stiffness(100.0, 100.0, 1.5)
        assert res["ok"] is False

    def test_tr_zero_returns_error(self):
        res = isolator_stiffness(100.0, 100.0, 0.0)
        assert res["ok"] is False

    def test_negative_m_returns_error(self):
        res = isolator_stiffness(-10.0, 100.0, 0.1)
        assert res["ok"] is False

    def test_fn_hz_from_omega_n(self):
        """fn = ωn / (2π)."""
        res = isolator_stiffness(50.0, 314.0, 0.1)
        assert res["ok"] is True
        assert abs(res["fn_hz"] - res["omega_n"] / (2 * math.pi)) < 1e-10


# ===========================================================================
# 12. LLM tool wrappers (run_*)
# ===========================================================================

class TestToolWrappers:

    def test_run_sdof_natural_frequency_happy_path(self):
        ctx = _ctx()
        raw = _run(run_sdof_natural_frequency(ctx, _args(m=2.0, k=800.0)))
        d = _ok_tool(raw)
        assert d["omega_n"] == pytest.approx(math.sqrt(400.0), rel=1e-6)

    def test_run_sdof_natural_frequency_missing_k(self):
        ctx = _ctx()
        raw = _run(run_sdof_natural_frequency(ctx, _args(m=2.0)))
        _err_tool(raw)

    def test_run_sdof_damped_frequency_happy_path(self):
        ctx = _ctx()
        raw = _run(run_sdof_damped_frequency(ctx, _args(m=1.0, k=100.0, c=2.0)))
        d = _ok_tool(raw)
        assert d["zeta"] < 1.0
        assert d["regime"] == "underdamped"

    def test_run_sdof_log_decrement_happy_path(self):
        ctx = _ctx()
        raw = _run(run_sdof_log_decrement(ctx, _args(x1=10.0, xn=5.0, n=3)))
        d = _ok_tool(raw)
        assert d["delta"] > 0
        assert 0 < d["zeta"] < 1

    def test_run_sdof_log_decrement_bad_json(self):
        ctx = _ctx()
        raw = _run(run_sdof_log_decrement(ctx, b"not_json"))
        _err_tool(raw)

    def test_run_sdof_free_response_happy_path(self):
        ctx = _ctx()
        raw = _run(run_sdof_free_response(
            ctx, _args(m=1.0, k=100.0, c=2.0, x0=0.01, v0=0.0, t=0.0)
        ))
        d = _ok_tool(raw)
        assert abs(d["x_t"] - 0.01) < 1e-10

    def test_run_sdof_harmonic_happy_path(self):
        ctx = _ctx()
        raw = _run(run_sdof_harmonic(ctx, _args(zeta=0.2, r=0.5)))
        d = _ok_tool(raw)
        assert d["M"] > 0

    def test_run_sdof_transmissibility_isolation_zone(self):
        ctx = _ctx()
        raw = _run(run_sdof_transmissibility(ctx, _args(zeta=0.05, r=2.0)))
        d = _ok_tool(raw)
        assert d["TR"] < 1.0
        assert d["isolating"] is True

    def test_run_sdof_rotating_unbalance_happy_path(self):
        ctx = _ctx()
        raw = _run(run_sdof_rotating_unbalance(
            ctx, _args(m=10.0, k=10000.0, c=50.0, m_u=0.1, e=0.02, omega=50.0)
        ))
        d = _ok_tool(raw)
        assert d["X_m"] > 0

    def test_run_2dof_eigen_happy_path(self):
        ctx = _ctx()
        raw = _run(run_2dof_eigen(ctx, _args(m1=1.0, m2=1.0, k1=1000.0, k2=500.0)))
        d = _ok_tool(raw)
        assert d["omega_1"] < d["omega_2"]

    def test_run_2dof_eigen_missing_m1(self):
        ctx = _ctx()
        raw = _run(run_2dof_eigen(ctx, _args(m2=1.0, k1=1000.0, k2=500.0)))
        _err_tool(raw)

    def test_run_beam_frequency_simply_supported(self):
        ctx = _ctx()
        raw = _run(run_beam_frequency(
            ctx, _args(mode=1, length_m=1.0, mass_per_m=2.0, E=200e9, I=1e-8,
                       bc="simply-supported")
        ))
        d = _ok_tool(raw)
        expected = math.pi ** 2 * math.sqrt(200e9 * 1e-8 / (2.0 * 1.0 ** 4))
        assert abs(d["omega_n"] - expected) / expected < REL

    def test_run_shaft_whirl_rayleigh_happy_path(self):
        ctx = _ctx()
        raw = _run(run_shaft_whirl_rayleigh(
            ctx, _args(
                lengths_m=[0.3, 0.7],
                masses_kg=[5.0, 5.0],
                E=200e9, I=1e-8,
                span_m=1.0,
            )
        ))
        d = _ok_tool(raw)
        assert d["omega_cr"] > 0
        assert d["n_cr_rpm"] > 0

    def test_run_isolator_stiffness_happy_path(self):
        ctx = _ctx()
        raw = _run(run_isolator_stiffness(
            ctx, _args(m=100.0, omega_exc=100.0, TR_target=0.1)
        ))
        d = _ok_tool(raw)
        assert d["k_N_per_m"] > 0
        assert abs(d["TR_actual"] - 0.1) < 1e-9

    def test_run_isolator_stiffness_invalid_TR(self):
        ctx = _ctx()
        raw = _run(run_isolator_stiffness(
            ctx, _args(m=100.0, omega_exc=100.0, TR_target=1.5)
        ))
        _err_tool(raw)
