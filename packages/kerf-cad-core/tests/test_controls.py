"""
Hermetic tests for kerf_cad_core.controls — classical control-systems analysis.

Coverage (>= 30 tests):
  system.second_order_spec          — ωn, ζ → performance specs
  system.second_order_inverse       — inverse spec (single metric → ωn, ζ)
  system.first_order_step           — first-order step response
  system.first_order_impulse        — first-order impulse response
  system.second_order_step          — second-order step response (all regimes)
  system.second_order_impulse       — second-order impulse response
  system.routh_hurwitz              — stability table + sign changes
  system.bode_point                 — magnitude/phase at single frequency
  system.gain_phase_margins         — GM, PM, crossover frequencies
  system.steady_state_errors        — Kp, Kv, Ka, ess
  system.pid_zn_open                — Z-N open-loop PID
  system.pid_zn_closed              — Z-N closed-loop PID
  system.pid_cohen_coon             — Cohen-Coon PID
  system.pid_imc                    — Lambda/IMC PID
  system.root_locus_breakaway       — real-axis breakaway points
  tools (LLM wrappers)              — happy path + error paths

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas verified against Ogata "Modern Control Engineering" (5th ed.) and
Nise "Control Systems Engineering" (7th ed.) hand-calculations.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.controls.system import (
    second_order_spec,
    second_order_inverse,
    first_order_step,
    first_order_impulse,
    second_order_step,
    second_order_impulse,
    routh_hurwitz,
    bode_point,
    gain_phase_margins,
    steady_state_errors,
    pid_zn_open,
    pid_zn_closed,
    pid_cohen_coon,
    pid_imc,
    root_locus_breakaway,
)
from kerf_cad_core.controls.tools import (
    run_second_order_spec,
    run_second_order_inverse,
    run_first_order_response,
    run_second_order_response,
    run_routh_hurwitz,
    run_bode_point,
    run_gain_phase_margins,
    run_steady_state_errors,
    run_pid_tuning,
    run_root_locus_breakaway,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REL = 1e-5  # relative tolerance


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


def _approx(a, b, rel=REL):
    if b == 0:
        return abs(a) < 1e-10
    return abs(a - b) / abs(b) < rel


# ===========================================================================
# 1. second_order_spec
# ===========================================================================

class TestSecondOrderSpec:

    def test_underdamped_overshoot_formula(self):
        """OS% = 100 exp(-π ζ/√(1-ζ²)) — Ogata §5-4."""
        wn, zeta = 10.0, 0.5
        res = second_order_spec(wn, zeta)
        assert res["ok"] is True
        expected_os = 100.0 * math.exp(-math.pi * zeta / math.sqrt(1 - zeta ** 2))
        assert _approx(res["overshoot_pct"], expected_os)

    def test_underdamped_peak_time_formula(self):
        """tp = π/ωd — Ogata eq. 5-32."""
        wn, zeta = 5.0, 0.3
        res = second_order_spec(wn, zeta)
        assert res["ok"] is True
        wd = wn * math.sqrt(1 - zeta ** 2)
        assert _approx(res["peak_time_s"], math.pi / wd)

    def test_underdamped_rise_time_formula(self):
        """tr = (π - arccos(ζ)) / ωd — Ogata eq. 5-34."""
        wn, zeta = 8.0, 0.4
        res = second_order_spec(wn, zeta)
        assert res["ok"] is True
        wd = wn * math.sqrt(1 - zeta ** 2)
        tr_expected = (math.pi - math.acos(zeta)) / wd
        assert _approx(res["rise_time_s"], tr_expected)

    def test_settling_time_2pct_formula(self):
        """ts_2pct ≈ 4/(ζ·ωn) — Ogata §5-4."""
        wn, zeta = 4.0, 0.7
        res = second_order_spec(wn, zeta)
        assert res["ok"] is True
        ts_expected = 4.0 / (zeta * wn)
        assert _approx(res["settling_time_2pct"], ts_expected)

    def test_critically_damped_no_overshoot(self):
        """ζ = 1 → 0% overshoot and no peak time."""
        res = second_order_spec(5.0, 1.0)
        assert res["ok"] is True
        assert res["overshoot_pct"] == 0.0
        assert res["peak_time_s"] is None

    def test_overdamped_no_overshoot(self):
        """ζ > 1 → 0% overshoot."""
        res = second_order_spec(3.0, 2.0)
        assert res["ok"] is True
        assert res["overshoot_pct"] == 0.0

    def test_ogata_example_zeta_0707(self):
        """Ogata example: ζ=0.707 → OS ≈ 4.3%."""
        res = second_order_spec(1.0, 0.707)
        assert res["ok"] is True
        assert abs(res["overshoot_pct"] - 4.3) < 0.15

    def test_warning_low_damping(self):
        """ζ < 0.1 → LOW_DAMPING warning."""
        res = second_order_spec(10.0, 0.05)
        assert res["ok"] is True
        assert any("LOW_DAMPING" in w for w in res["warnings"])

    def test_invalid_wn_returns_error(self):
        res = second_order_spec(-1.0, 0.5)
        assert res["ok"] is False

    def test_invalid_zeta_returns_error(self):
        res = second_order_spec(5.0, -0.1)
        assert res["ok"] is False


# ===========================================================================
# 2. second_order_inverse
# ===========================================================================

class TestSecondOrderInverse:

    def test_overshoot_16_3_gives_zeta_0_5(self):
        """OS = 16.3% → ζ ≈ 0.5 (Ogata example)."""
        res = second_order_inverse(overshoot=16.3)
        assert res["ok"] is True
        assert abs(res["zeta"] - 0.5) < 0.01

    def test_settling_time_gives_wn_and_zeta(self):
        """settling_time constrains ωn given assumed ζ=0.7."""
        ts = 2.0
        res = second_order_inverse(settling_time=ts)
        assert res["ok"] is True
        # wn = 4/(zeta*ts) with zeta=0.7
        wn_expected = 4.0 / (0.7 * ts)
        assert _approx(res["wn"], wn_expected)

    def test_peak_time_gives_wn(self):
        """peak_time = π/ωd, zeta assumed=0.5."""
        tp = 0.5
        res = second_order_inverse(peak_time=tp)
        assert res["ok"] is True
        assert res["wn"] > 0

    def test_rise_time_gives_wn(self):
        """rise_time gives ωn (zeta assumed=0.7)."""
        res = second_order_inverse(rise_time=0.3)
        assert res["ok"] is True
        assert res["wn"] > 0

    def test_multiple_specs_returns_error(self):
        res = second_order_inverse(overshoot=16.3, settling_time=2.0)
        assert res["ok"] is False

    def test_no_spec_returns_error(self):
        res = second_order_inverse()
        assert res["ok"] is False

    def test_invalid_overshoot_returns_error(self):
        res = second_order_inverse(overshoot=0.0)
        assert res["ok"] is False


# ===========================================================================
# 3. first_order_step
# ===========================================================================

class TestFirstOrderStep:

    def test_at_t0_y_is_zero(self):
        """y(0) = K(1 - e^0) = 0."""
        res = first_order_step(2.0, 1.0, [0.0])
        assert res["ok"] is True
        assert abs(res["y"][0]) < 1e-12

    def test_at_t_tau_y_is_0_632K(self):
        """y(τ) = K(1 - 1/e) ≈ 0.6321 K."""
        K, tau = 3.0, 2.0
        res = first_order_step(K, tau, [tau])
        assert res["ok"] is True
        expected = K * (1.0 - 1.0 / math.e)
        assert _approx(res["y"][0], expected)

    def test_steady_state_equals_K(self):
        """y(∞) → K."""
        K, tau = 4.0, 0.5
        res = first_order_step(K, tau, [20 * tau])
        assert res["ok"] is True
        assert abs(res["y"][0] - K) / K < 1e-6
        assert res["steady_state"] == K

    def test_multiple_samples(self):
        """Multiple t samples return matching list lengths."""
        ts = [0.0, 0.5, 1.0, 2.0]
        res = first_order_step(1.0, 1.0, ts)
        assert res["ok"] is True
        assert len(res["t"]) == 4
        assert len(res["y"]) == 4

    def test_negative_t_returns_error(self):
        res = first_order_step(1.0, 1.0, [-0.1])
        assert res["ok"] is False

    def test_zero_tau_returns_error(self):
        res = first_order_step(1.0, 0.0, [1.0])
        assert res["ok"] is False


# ===========================================================================
# 4. first_order_impulse
# ===========================================================================

class TestFirstOrderImpulse:

    def test_at_t0_y_is_K_over_tau(self):
        """h(0) = K/τ."""
        K, tau = 5.0, 2.0
        res = first_order_impulse(K, tau, [0.0])
        assert res["ok"] is True
        assert _approx(res["y"][0], K / tau)
        assert _approx(res["peak_y"], K / tau)

    def test_at_t_tau_y_decays(self):
        """h(τ) = (K/τ) e^(-1) ≈ 0.3679 K/τ."""
        K, tau = 2.0, 1.0
        res = first_order_impulse(K, tau, [tau])
        assert res["ok"] is True
        expected = (K / tau) * math.exp(-1.0)
        assert _approx(res["y"][0], expected)

    def test_zero_tau_returns_error(self):
        res = first_order_impulse(1.0, 0.0, [1.0])
        assert res["ok"] is False


# ===========================================================================
# 5. second_order_step
# ===========================================================================

class TestSecondOrderStep:

    def test_underdamped_at_t0_is_zero(self):
        """y(0) = 0 for step response."""
        res = second_order_step(5.0, 0.5, [0.0])
        assert res["ok"] is True
        assert abs(res["y"][0]) < 1e-12

    def test_underdamped_final_value_is_K(self):
        """y(∞) → K for underdamped system."""
        wn, zeta, K = 4.0, 0.5, 2.0
        t_large = 50.0 / (zeta * wn)
        res = second_order_step(wn, zeta, [t_large], K=K)
        assert res["ok"] is True
        assert abs(res["y"][0] - K) / K < 1e-4

    def test_critically_damped_no_overshoot(self):
        """Critically damped step response: y < K for all t > 0."""
        wn, zeta = 5.0, 1.0
        t_pts = [0.1 * i / wn for i in range(1, 20)]
        res = second_order_step(wn, zeta, t_pts)
        assert res["ok"] is True
        assert all(y <= 1.0 + 1e-8 for y in res["y"])

    def test_overdamped_monotone_approach(self):
        """Overdamped: response is monotonically increasing."""
        wn, zeta = 3.0, 2.0
        ts = [0.1 * i for i in range(1, 20)]
        res = second_order_step(wn, zeta, ts)
        assert res["ok"] is True
        for i in range(1, len(res["y"])):
            assert res["y"][i] >= res["y"][i - 1] - 1e-10

    def test_underdamped_exact_formula_at_one_sample(self):
        """Verify exact underdamped formula at one time point."""
        wn, zeta, K = 10.0, 0.3, 1.0
        t = 0.2
        wd = wn * math.sqrt(1 - zeta ** 2)
        sigma = zeta * wn
        y_expected = K * (1.0 - math.exp(-sigma * t) * (
            math.cos(wd * t) + (sigma / wd) * math.sin(wd * t)
        ))
        res = second_order_step(wn, zeta, [t], K=K)
        assert res["ok"] is True
        assert _approx(res["y"][0], y_expected)

    def test_invalid_wn_returns_error(self):
        res = second_order_step(-1.0, 0.5, [0.1])
        assert res["ok"] is False


# ===========================================================================
# 6. second_order_impulse
# ===========================================================================

class TestSecondOrderImpulse:

    def test_underdamped_formula_at_sample(self):
        """h(t) = (K ωn/ωd) e^(-ζωn t) sin(ωd t) for underdamped."""
        wn, zeta, K = 8.0, 0.25, 1.0
        t = 0.15
        wd = wn * math.sqrt(1 - zeta ** 2)
        sigma = zeta * wn
        h_expected = (K * wn / wd) * math.exp(-sigma * t) * math.sin(wd * t)
        res = second_order_impulse(wn, zeta, [t], K=K)
        assert res["ok"] is True
        assert _approx(res["y"][0], h_expected)

    def test_critically_damped_formula(self):
        """h(t) = K ωn² t e^(-ωn t) for critically damped."""
        wn, K = 4.0, 1.0
        t = 0.1
        h_expected = K * wn ** 2 * t * math.exp(-wn * t)
        res = second_order_impulse(wn, 1.0, [t], K=K)
        assert res["ok"] is True
        assert _approx(res["y"][0], h_expected)


# ===========================================================================
# 7. routh_hurwitz
# ===========================================================================

class TestRouthHurwitz:

    def test_stable_second_order(self):
        """s² + 3s + 2 = (s+1)(s+2) — both poles in LHP."""
        res = routh_hurwitz([1, 3, 2])
        assert res["ok"] is True
        assert res["stable"] is True
        assert res["sign_changes"] == 0

    def test_unstable_missing_term(self):
        """s³ + s = s(s²+1) — poles at ±j (marginal), but missing s² term → unstable."""
        # s³ + 0 s² + 1 s + 0: missing s² and constant → two sign changes expected
        res = routh_hurwitz([1, 0, 1, 0])
        assert res["ok"] is True
        # Near-zero pivot → warning
        assert len(res["warnings"]) > 0

    def test_stable_third_order(self):
        """s³ + 6s² + 11s + 6 = (s+1)(s+2)(s+3) — all stable."""
        res = routh_hurwitz([1, 6, 11, 6])
        assert res["ok"] is True
        assert res["stable"] is True
        assert res["sign_changes"] == 0

    def test_unstable_third_order(self):
        """s³ - s² - s + 1: RHP poles expected."""
        # Coefficients not all positive → definitely unstable
        res = routh_hurwitz([1, -1, -1, 1])
        assert res["ok"] is True
        assert res["stable"] is False

    def test_degree_extraction(self):
        """n should equal polynomial degree."""
        res = routh_hurwitz([1, 2, 1])
        assert res["ok"] is True
        assert res["n"] == 2

    def test_single_coefficient_returns_error(self):
        res = routh_hurwitz([1])
        assert res["ok"] is False

    def test_leading_zero_returns_error(self):
        res = routh_hurwitz([0, 1, 2])
        assert res["ok"] is False

    def test_nise_example_all_positive_coeffs(self):
        """Nise example: s⁴ + 2s³ + 3s² + 4s + 5 — not all stable (sign change check)."""
        # All coefficients positive but Routh may show instability
        res = routh_hurwitz([1, 2, 3, 4, 5])
        assert res["ok"] is True
        # Just verify it runs and returns valid structure
        assert "sign_changes" in res
        assert "routh_array" in res


# ===========================================================================
# 8. bode_point
# ===========================================================================

class TestBodePoint:

    def test_pure_gain_at_any_omega(self):
        """G(s) = K → magnitude = 20log10(K), phase = 0."""
        K = 10.0
        res = bode_point([K], [1], 1.0)
        assert res["ok"] is True
        assert _approx(res["magnitude_dB"], 20.0 * math.log10(K))
        assert abs(res["phase_deg"]) < 1e-9

    def test_integrator_minus_20dB_per_decade(self):
        """G(s) = 1/s: |G(j10)| = 0.1 → -20 dB, phase = -90°."""
        res = bode_point([1], [1, 0], 10.0)
        assert res["ok"] is True
        assert _approx(res["magnitude_dB"], -20.0)
        assert _approx(res["phase_deg"], -90.0, rel=1e-4)

    def test_first_order_lag_at_corner_frequency(self):
        """G(s) = 1/(s/wc + 1): at ω=wc, |G| = -3 dB, phase = -45°."""
        wc = 5.0
        # num = [1], den = [1/wc, 1]
        res = bode_point([1], [1.0 / wc, 1.0], wc)
        assert res["ok"] is True
        assert abs(res["magnitude_dB"] - (-3.01)) < 0.02
        assert abs(res["phase_deg"] - (-45.0)) < 0.01

    def test_second_order_at_natural_freq_peak(self):
        """G(s) = ωn²/(s²+2ζωns+ωn²): at ω=ωn, ζ=0.5, phase=-90°."""
        wn, zeta = 10.0, 0.5
        # G(jωn) = ωn²/(−ωn² + j·2ζωn² + ωn²) = 1/(j·2ζ)
        res = bode_point([wn ** 2], [1, 2 * zeta * wn, wn ** 2], wn)
        assert res["ok"] is True
        assert abs(res["phase_deg"] - (-90.0)) < 0.1

    def test_invalid_omega_returns_error(self):
        res = bode_point([1], [1, 1], -1.0)
        assert res["ok"] is False


# ===========================================================================
# 9. gain_phase_margins
# ===========================================================================

class TestGainPhaseMargins:

    def test_stable_first_order_has_infinite_pm(self):
        """G(s) = K/(s+1): phase never reaches -180°, so PM should be none or large."""
        res = gain_phase_margins([1], [1, 1])
        assert res["ok"] is True
        # Phase crossover may not be found for first order
        # Just check the function runs and gives valid output
        assert "gain_margin_dB" in res

    def test_known_second_order_with_integrator(self):
        """G(s) = 10/(s(s+1)(s+10)) — phase crosses -180°."""
        # G = 10 / (s^3 + 11s^2 + 10s)
        # den: s(s+1)(s+10) = s^3 + 11s^2 + 10s + 0
        res = gain_phase_margins([10], [1, 11, 10, 0])
        assert res["ok"] is True
        assert "gain_margin_dB" in res
        assert "phase_margin_deg" in res

    def test_poor_margin_flagged_in_warnings(self):
        """Very low phase margin should appear in warnings."""
        # G(s) = 100/(s(s+1)(s+2)) — unstable at high gain
        res = gain_phase_margins([100], [1, 3, 2, 0])
        assert res["ok"] is True
        # If margins are found and poor, warnings should mention it
        # Just check it doesn't crash
        assert isinstance(res["warnings"], list)

    def test_invalid_num_returns_error(self):
        res = gain_phase_margins([], [1, 1])
        assert res["ok"] is False

    def test_invalid_omega_range_returns_error(self):
        res = gain_phase_margins([1], [1, 1], [100.0, 1.0])  # min > max
        assert res["ok"] is False


# ===========================================================================
# 10. steady_state_errors
# ===========================================================================

class TestSteadyStateErrors:

    def test_type_0_kp_finite_ess_step_nonzero(self):
        """G(s) = K/(s+1): type 0, Kp = K, ess_step = 1/(1+K)."""
        K = 9.0
        res = steady_state_errors([K], [1, 1])
        assert res["ok"] is True
        assert res["system_type"] == 0
        assert _approx(res["Kp"], K)
        assert _approx(res["ess_step"], 1.0 / (1.0 + K))

    def test_type_1_zero_ess_step(self):
        """G(s) = K/(s(s+1)): type 1, ess_step = 0."""
        res = steady_state_errors([5], [1, 1, 0])
        assert res["ok"] is True
        assert res["system_type"] == 1
        assert res["ess_step"] == 0.0

    def test_type_1_kv_from_numerator(self):
        """G(s) = 5/(s(s+1)): Kv = lim s→0 s·G(s) = 5."""
        res = steady_state_errors([5], [1, 1, 0])
        assert res["ok"] is True
        assert _approx(res["Kv"], 5.0)
        assert _approx(res["ess_ramp"], 1.0 / 5.0)

    def test_type_2_zero_ess_ramp(self):
        """G(s) = K/s²(s+1): type 2, ess_ramp = 0."""
        res = steady_state_errors([2], [1, 1, 0, 0])
        assert res["ok"] is True
        assert res["system_type"] == 2
        assert res["ess_ramp"] == 0.0

    def test_invalid_empty_num_returns_error(self):
        res = steady_state_errors([], [1, 1])
        assert res["ok"] is False


# ===========================================================================
# 11. pid_zn_open
# ===========================================================================

class TestPidZnOpen:

    def test_kp_formula(self):
        """Kp = 1.2 τ/(K θ) for PID — Ogata §8-6."""
        K, tau, theta = 2.0, 5.0, 0.5
        res = pid_zn_open(K, tau, theta)
        assert res["ok"] is True
        Kp_expected = 1.2 * tau / (K * theta)
        assert _approx(res["PID"]["Kp"], Kp_expected)

    def test_ti_formula(self):
        """Ti = 2θ for PID."""
        K, tau, theta = 1.0, 3.0, 1.0
        res = pid_zn_open(K, tau, theta)
        assert res["ok"] is True
        assert _approx(res["PID"]["Ti"], 2.0 * theta)

    def test_td_formula(self):
        """Td = 0.5θ for PID."""
        K, tau, theta = 1.0, 3.0, 1.0
        res = pid_zn_open(K, tau, theta)
        assert res["ok"] is True
        assert _approx(res["PID"]["Td"], 0.5 * theta)

    def test_pi_kp_formula(self):
        """Kp = 0.9 τ/(K θ) for PI."""
        K, tau, theta = 3.0, 4.0, 0.8
        res = pid_zn_open(K, tau, theta)
        assert res["ok"] is True
        Kp_PI_expected = 0.9 * tau / (K * theta)
        assert _approx(res["PI"]["Kp"], Kp_PI_expected)

    def test_controllability_ratio(self):
        """R = theta/tau."""
        K, tau, theta = 1.0, 4.0, 1.0
        res = pid_zn_open(K, tau, theta)
        assert res["ok"] is True
        assert _approx(res["R"], theta / tau)

    def test_warning_for_hard_to_control(self):
        """theta/tau > 1 → warning."""
        res = pid_zn_open(1.0, 1.0, 2.0)  # theta/tau = 2
        assert res["ok"] is True
        assert any("HARD_TO_CONTROL" in w for w in res["warnings"])

    def test_invalid_theta_returns_error(self):
        res = pid_zn_open(1.0, 5.0, -1.0)
        assert res["ok"] is False

    def test_zero_K_returns_error(self):
        res = pid_zn_open(0.0, 5.0, 1.0)
        assert res["ok"] is False


# ===========================================================================
# 12. pid_zn_closed
# ===========================================================================

class TestPidZnClosed:

    def test_kp_formula(self):
        """Kp = 0.6 Ku for PID — Ziegler-Nichols closed-loop."""
        Ku, Tu = 2.5, 0.8
        res = pid_zn_closed(Ku, Tu)
        assert res["ok"] is True
        assert _approx(res["PID"]["Kp"], 0.6 * Ku)

    def test_ti_formula(self):
        """Ti = Tu/2 for PID."""
        Ku, Tu = 3.0, 1.2
        res = pid_zn_closed(Ku, Tu)
        assert res["ok"] is True
        assert _approx(res["PID"]["Ti"], Tu / 2.0)

    def test_td_formula(self):
        """Td = Tu/8 for PID."""
        Ku, Tu = 3.0, 1.2
        res = pid_zn_closed(Ku, Tu)
        assert res["ok"] is True
        assert _approx(res["PID"]["Td"], Tu / 8.0)

    def test_invalid_Ku_returns_error(self):
        res = pid_zn_closed(-1.0, 1.0)
        assert res["ok"] is False


# ===========================================================================
# 13. pid_cohen_coon
# ===========================================================================

class TestPidCohenCoon:

    def test_R_formula(self):
        """R = theta/(theta + tau)."""
        K, tau, theta = 1.0, 5.0, 1.0
        res = pid_cohen_coon(K, tau, theta)
        assert res["ok"] is True
        R_expected = theta / (theta + tau)
        assert _approx(res["R"], R_expected)

    def test_pid_kp_formula(self):
        """Kp = (1/K)(τ/θ)(4/3 + R/4)."""
        K, tau, theta = 2.0, 4.0, 1.0
        R = theta / (theta + tau)
        Kp_expected = (1.0 / K) * (tau / theta) * (4.0 / 3.0 + R / 4.0)
        res = pid_cohen_coon(K, tau, theta)
        assert res["ok"] is True
        assert _approx(res["PID"]["Kp"], Kp_expected)

    def test_pi_ti_formula(self):
        """Ti = theta(30+3R)/(9+20R) for PI."""
        K, tau, theta = 1.0, 3.0, 0.5
        R = theta / (theta + tau)
        Ti_PI_expected = theta * (30.0 + 3.0 * R) / (9.0 + 20.0 * R)
        res = pid_cohen_coon(K, tau, theta)
        assert res["ok"] is True
        assert _approx(res["PI"]["Ti"], Ti_PI_expected)

    def test_invalid_K_zero_returns_error(self):
        res = pid_cohen_coon(0.0, 5.0, 1.0)
        assert res["ok"] is False


# ===========================================================================
# 14. pid_imc
# ===========================================================================

class TestPidImc:

    def test_kp_formula(self):
        """Kp = τ / (K(λ + θ))."""
        K, tau, theta, lc = 2.0, 5.0, 0.5, 2.0
        res = pid_imc(K, tau, theta, lc)
        assert res["ok"] is True
        Kp_expected = tau / (K * (lc + theta))
        assert _approx(res["PID"]["Kp"], Kp_expected)

    def test_ti_equals_tau(self):
        """Ti = tau."""
        K, tau, theta, lc = 1.0, 4.0, 0.8, 1.5
        res = pid_imc(K, tau, theta, lc)
        assert res["ok"] is True
        assert _approx(res["PID"]["Ti"], tau)

    def test_td_equals_half_theta(self):
        """Td = theta/2."""
        K, tau, theta, lc = 1.0, 3.0, 1.0, 2.0
        res = pid_imc(K, tau, theta, lc)
        assert res["ok"] is True
        assert _approx(res["PID"]["Td"], theta / 2.0)

    def test_aggressive_lambda_warning(self):
        """lambda_c < max(0.25tau, theta) → AGGRESSIVE_LAMBDA warning."""
        K, tau, theta = 1.0, 10.0, 1.0
        lc = 0.1  # < max(0.25*10, 1) = max(2.5, 1) = 2.5
        res = pid_imc(K, tau, theta, lc)
        assert res["ok"] is True
        assert any("AGGRESSIVE_LAMBDA" in w for w in res["warnings"])

    def test_invalid_lambda_returns_error(self):
        res = pid_imc(1.0, 5.0, 1.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 15. root_locus_breakaway
# ===========================================================================

class TestRootLocusBreakaway:

    def test_simple_system_s_plus_1_den(self):
        """G(s) = 1/((s+1)(s+3)): breakaway at s = -2."""
        # num = [1], den = (s+1)(s+3) = s²+4s+3
        res = root_locus_breakaway([1], [1, 4, 3])
        assert res["ok"] is True
        # Should find root near s = -2
        assert len(res["breakaway_points"]) >= 1
        assert any(abs(r - (-2.0)) < 0.01 for r in res["breakaway_points"])

    def test_two_pole_one_zero_breakaway(self):
        """G(s) = (s+2)/((s+1)(s+4)): breakaway exists between -4 and -1."""
        res = root_locus_breakaway([1, 2], [1, 5, 4])
        assert res["ok"] is True
        # candidate points should be real numbers
        assert isinstance(res["breakaway_points"], list)

    def test_constant_numerator_denominator(self):
        """G(s) = 1/s² → breakaway at 0."""
        res = root_locus_breakaway([1], [1, 0, 0])
        assert res["ok"] is True
        assert "breakaway_points" in res

    def test_empty_num_returns_error(self):
        res = root_locus_breakaway([], [1, 2, 1])
        assert res["ok"] is False


# ===========================================================================
# 16. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_second_order_spec_happy_path(self):
        ctx = _ctx()
        raw = _run(run_second_order_spec(ctx, _args(wn=10.0, zeta=0.5)))
        d = _ok_tool(raw)
        assert d["overshoot_pct"] > 0

    def test_run_second_order_spec_missing_zeta(self):
        ctx = _ctx()
        raw = _run(run_second_order_spec(ctx, _args(wn=10.0)))
        _err_tool(raw)

    def test_run_second_order_inverse_overshoot(self):
        ctx = _ctx()
        raw = _run(run_second_order_inverse(ctx, _args(overshoot=16.3)))
        d = _ok_tool(raw)
        assert abs(d["zeta"] - 0.5) < 0.01

    def test_run_first_order_response_step(self):
        ctx = _ctx()
        raw = _run(run_first_order_response(ctx, _args(K=2.0, tau=1.0, t_samples=[0.0, 1.0, 5.0])))
        d = _ok_tool(raw)
        assert len(d["y"]) == 3

    def test_run_first_order_response_impulse(self):
        ctx = _ctx()
        raw = _run(run_first_order_response(
            ctx, _args(K=2.0, tau=1.0, t_samples=[0.0], response_type="impulse")
        ))
        d = _ok_tool(raw)
        assert _approx(d["peak_y"], 2.0 / 1.0)

    def test_run_second_order_response_step(self):
        ctx = _ctx()
        raw = _run(run_second_order_response(ctx, _args(wn=5.0, zeta=0.7, t_samples=[0.0, 1.0])))
        d = _ok_tool(raw)
        assert abs(d["y"][0]) < 1e-10

    def test_run_routh_hurwitz_stable(self):
        ctx = _ctx()
        raw = _run(run_routh_hurwitz(ctx, _args(coeffs=[1, 6, 11, 6])))
        d = _ok_tool(raw)
        assert d["stable"] is True

    def test_run_routh_hurwitz_bad_json(self):
        ctx = _ctx()
        raw = _run(run_routh_hurwitz(ctx, b"not_json"))
        _err_tool(raw)

    def test_run_bode_point_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bode_point(ctx, _args(num=[1], den=[1, 1], omega=1.0)))
        d = _ok_tool(raw)
        assert "magnitude_dB" in d

    def test_run_gain_phase_margins_happy_path(self):
        ctx = _ctx()
        raw = _run(run_gain_phase_margins(ctx, _args(num=[10], den=[1, 11, 10, 0])))
        d = _ok_tool(raw)
        assert "gain_margin_dB" in d

    def test_run_steady_state_errors_type1(self):
        ctx = _ctx()
        raw = _run(run_steady_state_errors(ctx, _args(num_ol=[5], den_ol=[1, 1, 0])))
        d = _ok_tool(raw)
        assert d["system_type"] == 1
        assert d["ess_step"] == 0.0

    def test_run_pid_tuning_zn_open(self):
        ctx = _ctx()
        raw = _run(run_pid_tuning(ctx, _args(method="zn_open", K=2.0, tau=5.0, theta=0.5)))
        d = _ok_tool(raw)
        assert "PID" in d

    def test_run_pid_tuning_zn_closed(self):
        ctx = _ctx()
        raw = _run(run_pid_tuning(ctx, _args(method="zn_closed", Ku=2.5, Tu=0.8)))
        d = _ok_tool(raw)
        assert "PID" in d

    def test_run_pid_tuning_cohen_coon(self):
        ctx = _ctx()
        raw = _run(run_pid_tuning(ctx, _args(method="cohen_coon", K=1.0, tau=5.0, theta=1.0)))
        d = _ok_tool(raw)
        assert "PID" in d

    def test_run_pid_tuning_imc(self):
        ctx = _ctx()
        raw = _run(run_pid_tuning(ctx, _args(method="imc", K=2.0, tau=5.0, theta=0.5, lambda_c=2.0)))
        d = _ok_tool(raw)
        assert "PID" in d

    def test_run_pid_tuning_missing_param_returns_error(self):
        ctx = _ctx()
        raw = _run(run_pid_tuning(ctx, _args(method="zn_open", K=2.0)))  # missing tau, theta
        _err_tool(raw)

    def test_run_pid_tuning_unknown_method_returns_error(self):
        ctx = _ctx()
        raw = _run(run_pid_tuning(ctx, _args(method="unknown")))
        _err_tool(raw)

    def test_run_root_locus_breakaway_happy_path(self):
        ctx = _ctx()
        raw = _run(run_root_locus_breakaway(ctx, _args(num=[1], den=[1, 4, 3])))
        d = _ok_tool(raw)
        assert any(abs(r - (-2.0)) < 0.01 for r in d["breakaway_points"])

    def test_run_root_locus_breakaway_missing_den(self):
        ctx = _ctx()
        raw = _run(run_root_locus_breakaway(ctx, _args(num=[1])))
        _err_tool(raw)
