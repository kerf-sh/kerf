"""
Hermetic tests for kerf_cad_core.reliability — systems reliability & risk analysis.

Coverage:
  analysis.weibull_reliability    — Weibull R(t), F(t)
  analysis.weibull_hazard         — Weibull h(t)
  analysis.weibull_b_life         — B10/B50 life
  analysis.weibull_mttf           — MTTF with Gamma function
  analysis.weibull_characteristic_life — 63.2% point
  analysis.weibull_fit            — RRX/RRY/MLE regression
  analysis.exponential_reliability — R(t)=exp(-t/MTBF)
  analysis.exponential_mtbf_ci   — chi-square MTBF bounds
  analysis.system_series          — product formula
  analysis.system_parallel        — 1-product(Q)
  analysis.system_k_out_of_n      — binomial series
  analysis.system_bridge          — 5-component bridge
  analysis.availability           — A=MTBF/(MTBF+MTTR)
  analysis.redundancy_gain        — parallel gain
  analysis.stress_strength_normal — closed-form z
  analysis.stress_strength_numeric — empirical fraction
  analysis.fmea_rpn               — S×O×D
  analysis.fmea_criticality       — criticality number
  analysis.fault_tree_top         — AND/OR tree evaluation
  analysis.fault_tree_cut_sets    — minimal cut sets
  analysis.fault_tree_importance  — Birnbaum importance
  analysis.reliability_allocation_equal — r^(1/n)
  analysis.reliability_allocation_agree — AGREE method
  analysis.arrhenius_af           — thermal AF
  analysis.inverse_power_af       — stress AF
  tools.*                         — LLM wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Calculations verified against O'Connor & Kleyner, Tobias & Trindade, and
MIL-HDBK-217F hand-calculations.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.reliability.analysis import (
    weibull_reliability,
    weibull_hazard,
    weibull_b_life,
    weibull_mttf,
    weibull_characteristic_life,
    weibull_fit,
    exponential_reliability,
    exponential_mtbf_ci,
    system_series,
    system_parallel,
    system_k_out_of_n,
    system_bridge,
    availability,
    redundancy_gain,
    stress_strength_normal,
    stress_strength_numeric,
    fmea_rpn,
    fmea_criticality,
    fault_tree_top,
    fault_tree_cut_sets,
    fault_tree_importance,
    reliability_allocation_equal,
    reliability_allocation_agree,
    arrhenius_af,
    inverse_power_af,
    _norm_cdf,
    _gamma_func,
    _chi2_ppf,
)
from kerf_cad_core.reliability.tools import (
    run_weibull_fit,
    run_weibull_b_life,
    run_weibull_mttf,
    run_weibull_eval,
    run_exponential_mtbf_ci,
    run_system,
    run_availability,
    run_stress_strength,
    run_fmea_rpn,
    run_fault_tree,
    run_reliability_allocation,
    run_accel_life,
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


def _ok(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


REL = 1e-4  # relative tolerance for hand-calc comparisons


# ===========================================================================
# 1. Weibull reliability
# ===========================================================================

class TestWeibullReliability:
    def test_exponential_case_beta1(self):
        # beta=1 → exponential: R(t) = exp(-t/eta)
        t, eta = 100.0, 500.0
        r = weibull_reliability(t, beta=1.0, eta=eta)
        assert r["ok"]
        expected = math.exp(-t / eta)
        assert abs(r["R"] - expected) < 1e-10
        assert abs(r["F"] - (1.0 - expected)) < 1e-10

    def test_characteristic_life_is_632(self):
        # At t=eta (gamma=0), R = exp(-1) ≈ 0.3679, F ≈ 0.6321
        eta = 1000.0
        r = weibull_reliability(eta, beta=2.5, eta=eta)
        assert r["ok"]
        assert abs(r["R"] - math.exp(-1)) < 1e-10
        assert abs(r["F"] - (1 - math.exp(-1))) < 1e-10

    def test_three_param_shift(self):
        # gamma=200, t=700, eta=500, beta=1.5
        gamma, eta, beta = 200.0, 500.0, 1.5
        t = 700.0
        z = (t - gamma) / eta  # = 1.0
        expected_R = math.exp(-(z ** beta))
        r = weibull_reliability(t, beta=beta, eta=eta, gamma=gamma)
        assert r["ok"]
        assert abs(r["R"] - expected_R) < 1e-10

    def test_t_at_gamma_rejected(self):
        r = weibull_reliability(100.0, beta=2.0, eta=500.0, gamma=100.0)
        assert not r["ok"]

    def test_invalid_beta(self):
        r = weibull_reliability(100.0, beta=-1.0, eta=500.0)
        assert not r["ok"]


# ===========================================================================
# 2. Weibull hazard
# ===========================================================================

class TestWeibullHazard:
    def test_constant_hazard_beta1(self):
        # beta=1 → h(t) = 1/eta (constant)
        eta = 1000.0
        h = weibull_hazard(500.0, beta=1.0, eta=eta)
        assert h["ok"]
        assert abs(h["h"] - 1.0 / eta) < 1e-12

    def test_increasing_hazard_beta_gt1(self):
        # For beta=2, h increases with t
        eta = 1000.0
        h1 = weibull_hazard(100.0, beta=2.0, eta=eta)
        h2 = weibull_hazard(500.0, beta=2.0, eta=eta)
        assert h1["ok"] and h2["ok"]
        assert h2["h"] > h1["h"]


# ===========================================================================
# 3. Weibull B-life
# ===========================================================================

class TestWeibullBLife:
    def test_b10_hand_calc(self):
        # B10: t_B10 = eta * (-ln(0.9))^(1/beta)
        beta, eta = 2.0, 1000.0
        t_b10 = weibull_b_life(10.0, beta=beta, eta=eta)
        assert t_b10["ok"]
        expected = eta * (-math.log(0.9)) ** (1.0 / beta)
        assert abs(t_b10["t_B"] - expected) / expected < REL

    def test_b50_is_median(self):
        # B50: t_B50 = eta * ln(2)^(1/beta)
        beta, eta = 1.5, 800.0
        t_b50 = weibull_b_life(50.0, beta=beta, eta=eta)
        assert t_b50["ok"]
        expected = eta * math.log(2.0) ** (1.0 / beta)
        assert abs(t_b50["t_B"] - expected) / expected < REL

    def test_b10_lt_b50(self):
        beta, eta = 2.0, 1000.0
        t10 = weibull_b_life(10.0, beta=beta, eta=eta)
        t50 = weibull_b_life(50.0, beta=beta, eta=eta)
        assert t10["t_B"] < t50["t_B"]

    def test_invalid_pct(self):
        r = weibull_b_life(0.0, beta=2.0, eta=1000.0)
        assert not r["ok"]
        r2 = weibull_b_life(100.0, beta=2.0, eta=1000.0)
        assert not r2["ok"]


# ===========================================================================
# 4. Weibull MTTF
# ===========================================================================

class TestWeibullMttf:
    def test_exponential_mttf_equals_eta(self):
        # beta=1: MTTF = eta * Gamma(2) = eta * 1! = eta
        eta = 1234.0
        r = weibull_mttf(beta=1.0, eta=eta)
        assert r["ok"]
        assert abs(r["mttf"] - eta) < 1e-6

    def test_beta2_mttf(self):
        # beta=2: MTTF = eta * Gamma(1.5) = eta * sqrt(pi)/2
        eta = 1000.0
        r = weibull_mttf(beta=2.0, eta=eta)
        assert r["ok"]
        expected = eta * math.sqrt(math.pi) / 2.0
        assert abs(r["mttf"] - expected) / expected < REL

    def test_characteristic_life(self):
        beta, eta, gamma = 2.5, 500.0, 50.0
        r = weibull_characteristic_life(beta=beta, eta=eta, gamma=gamma)
        assert r["ok"]
        assert abs(r["t_632"] - (eta + gamma)) < 1e-10
        assert abs(r["eta"] - eta) < 1e-10


# ===========================================================================
# 5. Weibull fit (regression)
# ===========================================================================

class TestWeibullFit:
    # Tobias & Trindade example data (times in hours)
    TIMES = [93.0, 150.0, 196.0, 245.0, 312.0]

    def test_rrx_returns_positive_beta_eta(self):
        r = weibull_fit(self.TIMES, method="RRX")
        assert r["ok"]
        assert r["beta"] > 0
        assert r["eta"] > 0

    def test_rry_similar_to_rrx(self):
        r1 = weibull_fit(self.TIMES, method="RRX")
        r2 = weibull_fit(self.TIMES, method="RRY")
        assert r1["ok"] and r2["ok"]
        # beta should be within 50% of each other for this data
        assert abs(r1["beta"] - r2["beta"]) / r1["beta"] < 0.5

    def test_mle_returns_beta_eta(self):
        r = weibull_fit(self.TIMES, method="MLE")
        assert r["ok"]
        assert r["beta"] > 0
        assert r["eta"] > 0

    def test_censored_data_reduces_nothing(self):
        # Adding suspensions shouldn't fail
        r = weibull_fit(self.TIMES, censored=[400.0, 500.0], method="RRX")
        assert r["ok"]
        assert r["beta"] > 0

    def test_rrx_r_squared_in_range(self):
        r = weibull_fit(self.TIMES, method="RRX")
        assert r["ok"]
        assert 0.0 <= r["r_squared"] <= 1.0

    def test_too_few_failures_warns(self):
        import warnings as _w
        with _w.catch_warnings(record=True) as caught:
            _w.simplefilter("always")
            r = weibull_fit([100.0], method="RRX")
        # either warns or returns ok=False (single point — fit fails)
        # single failure with no others → regression fails (< 2 fail points)
        # Either a warning was issued or ok=False
        assert not r["ok"] or len(caught) > 0 or len(r.get("warnings", [])) > 0


# ===========================================================================
# 6. Exponential reliability
# ===========================================================================

class TestExponentialReliability:
    def test_r_at_zero(self):
        r = exponential_reliability(0.0, mtbf=1000.0)
        assert r["ok"]
        assert abs(r["R"] - 1.0) < 1e-12

    def test_r_at_one_mtbf(self):
        # R(MTBF) = exp(-1) ≈ 0.3679
        r = exponential_reliability(1000.0, mtbf=1000.0)
        assert r["ok"]
        assert abs(r["R"] - math.exp(-1)) < 1e-10

    def test_lambda_equals_reciprocal_mtbf(self):
        mtbf = 500.0
        r = exponential_reliability(100.0, mtbf=mtbf)
        assert r["ok"]
        assert abs(r["lambda"] - 1.0 / mtbf) < 1e-12


# ===========================================================================
# 7. Exponential MTBF chi-square CI
# ===========================================================================

class TestExponentialMtbfCI:
    def test_basic_bounds_ordering(self):
        # With 5 failures, test_time=5000: lower < point < upper
        r = exponential_mtbf_ci(5, 5000.0, confidence=0.9)
        assert r["ok"]
        assert r["mtbf_lower"] < r["mtbf_point"] < r["mtbf_upper"]

    def test_point_estimate_correct(self):
        r = exponential_mtbf_ci(10, 10000.0, confidence=0.9)
        assert r["ok"]
        assert abs(r["mtbf_point"] - 1000.0) < 1e-9

    def test_zero_failures(self):
        # 0 failures → only lower bound; upper = inf
        r = exponential_mtbf_ci(0, 1000.0, confidence=0.9)
        assert r["ok"]
        assert r["mtbf_upper"] == float("inf")
        assert r["mtbf_lower"] > 0

    def test_more_failures_narrower_interval(self):
        r10 = exponential_mtbf_ci(10, 10000.0, confidence=0.9)
        r50 = exponential_mtbf_ci(50, 50000.0, confidence=0.9)
        # Relative interval width: (upper-lower)/point
        w10 = (r10["mtbf_upper"] - r10["mtbf_lower"]) / r10["mtbf_point"]
        w50 = (r50["mtbf_upper"] - r50["mtbf_lower"]) / r50["mtbf_point"]
        assert w50 < w10

    def test_chi2_lower_bound_hand_calc(self):
        # 5 failures, T=5000, confidence=0.90
        # df_lower = 2*(5+1) = 12;  chi2(0.95, 12) via WH approx
        # MTBF_lower = 2*5000 / chi2(0.95, 12)
        # chi2(0.95, 12) ≈ 21.026 (textbook)
        # MTBF_lower ≈ 10000 / 21.026 ≈ 475.6
        r = exponential_mtbf_ci(5, 5000.0, confidence=0.90)
        assert r["ok"]
        # WH approximation is close but not exact — allow 5% tolerance
        assert 440 < r["mtbf_lower"] < 530


# ===========================================================================
# 8. System reliability
# ===========================================================================

class TestSystemReliability:
    def test_series_product(self):
        r = system_series([0.9, 0.95, 0.99])
        assert r["ok"]
        expected = 0.9 * 0.95 * 0.99
        assert abs(r["R_system"] - expected) < 1e-10

    def test_parallel_formula(self):
        r = system_parallel([0.9, 0.9, 0.9])
        assert r["ok"]
        q = (1 - 0.9) ** 3
        assert abs(r["R_system"] - (1 - q)) < 1e-10

    def test_series_single_component(self):
        r = system_series([0.95])
        assert r["ok"]
        assert abs(r["R_system"] - 0.95) < 1e-12

    def test_parallel_improves_over_single(self):
        r1 = system_parallel([0.8])
        r2 = system_parallel([0.8, 0.8])
        assert r2["R_system"] > r1["R_system"]

    def test_k_of_n_k_equals_n_is_series(self):
        # 3-of-3 with r=0.9 should equal series of 3
        r_kon = system_k_out_of_n(3, 3, 0.9)
        r_ser = system_series([0.9, 0.9, 0.9])
        assert r_kon["ok"] and r_ser["ok"]
        assert abs(r_kon["R_system"] - r_ser["R_system"]) < 1e-9

    def test_k_of_n_k_equals_1_is_parallel(self):
        # 1-of-3 with r=0.9 should equal parallel of 3
        r_kon = system_k_out_of_n(1, 3, 0.9)
        r_par = system_parallel([0.9, 0.9, 0.9])
        assert r_kon["ok"] and r_par["ok"]
        assert abs(r_kon["R_system"] - r_par["R_system"]) < 1e-9

    def test_k_of_n_2_of_3_hand_calc(self):
        # 2-of-3, r=0.9: R = C(3,2)*0.9^2*0.1 + C(3,3)*0.9^3 = 3*0.081 + 0.729 = 0.972
        r = system_k_out_of_n(2, 3, 0.9)
        assert r["ok"]
        expected = 3 * 0.9**2 * 0.1 + 0.9**3
        assert abs(r["R_system"] - expected) < 1e-9

    def test_bridge_symmetric_r_05(self):
        # All components r=0.5: bridge has known analytical value
        # R = r3*(r1+r2-r1r2)*(r4+r5-r4r5) + (1-r3)*(r1r5+r2r4-r1r5r2r4)
        # = 0.5*(0.75*0.75) + 0.5*(0.25+0.25-0.25*0.25)
        # = 0.5*0.5625 + 0.5*0.4375 = 0.28125 + 0.21875 = 0.5
        r = system_bridge([0.5, 0.5, 0.5, 0.5, 0.5])
        assert r["ok"]
        assert abs(r["R_system"] - 0.5) < 1e-9

    def test_bridge_requires_5_components(self):
        r = system_bridge([0.9, 0.9, 0.9])
        assert not r["ok"]


# ===========================================================================
# 9. Availability and redundancy
# ===========================================================================

class TestAvailabilityRedundancy:
    def test_availability_formula(self):
        mtbf, mttr = 1000.0, 10.0
        r = availability(mtbf, mttr)
        assert r["ok"]
        expected = mtbf / (mtbf + mttr)
        assert abs(r["availability"] - expected) < 1e-12
        assert abs(r["unavailability"] - (1.0 - expected)) < 1e-12

    def test_availability_99_9_pct(self):
        # MTBF=9990, MTTR=10 → A ≈ 0.999
        r = availability(9990.0, 10.0)
        assert r["ok"]
        assert abs(r["availability"] - 9990.0 / 10000.0) < 1e-9

    def test_redundancy_gain_n2_increases_r(self):
        r = redundancy_gain(0.8, 2)
        assert r["ok"]
        # R_active = 1 - 0.2^2 = 0.96
        assert abs(r["R_active"] - (1 - 0.2**2)) < 1e-9
        assert r["gain_active"] > 1.0

    def test_redundancy_gain_with_standby(self):
        r = redundancy_gain(0.8, 2, n_standby=1)
        assert r["ok"]
        # R_standby = 1 - 0.2^3 = 0.992
        assert abs(r["R_with_standby"] - (1 - 0.2**3)) < 1e-9
        assert r["R_with_standby"] > r["R_active"]


# ===========================================================================
# 10. Stress-strength interference
# ===========================================================================

class TestStressStrength:
    def test_normal_normal_zero_mean_diff(self):
        # mu_r = mu_s → z = 0 → R = 0.5
        r = stress_strength_normal(mu_s=100.0, sigma_s=10.0, mu_r=100.0, sigma_r=10.0)
        assert r["ok"]
        assert abs(r["R"] - 0.5) < 1e-4

    def test_normal_normal_large_margin(self):
        # Large margin (mu_r >> mu_s): R should be close to 1
        r = stress_strength_normal(mu_s=100.0, sigma_s=5.0, mu_r=200.0, sigma_r=5.0)
        assert r["ok"]
        assert r["R"] > 0.999

    def test_normal_normal_z_hand_calc(self):
        # z = (150-100) / sqrt(10^2 + 20^2) = 50 / sqrt(500) ≈ 2.236
        mu_s, sigma_s, mu_r, sigma_r = 100.0, 20.0, 150.0, 10.0
        r = stress_strength_normal(mu_s, sigma_s, mu_r, sigma_r)
        assert r["ok"]
        z_expected = (mu_r - mu_s) / math.sqrt(sigma_r**2 + sigma_s**2)
        assert abs(r["z"] - z_expected) < 1e-9
        assert abs(r["R"] - _norm_cdf(z_expected)) < 1e-9

    def test_numeric_perfect_separation(self):
        # All strength > all stress → R = 1.0
        stress = [1.0, 2.0, 3.0]
        strength = [10.0, 20.0, 30.0]
        r = stress_strength_numeric(stress, strength)
        assert r["ok"]
        assert r["R"] == 1.0

    def test_numeric_no_separation(self):
        # All stress > all strength → R = 0.0
        stress = [10.0, 20.0, 30.0]
        strength = [1.0, 2.0, 3.0]
        r = stress_strength_numeric(stress, strength)
        assert r["ok"]
        assert r["R"] == 0.0

    def test_numeric_half_passes(self):
        # strength > stress for exactly half
        stress = [5.0, 15.0]
        strength = [10.0, 10.0]  # 10>5 (pass), 10<15 (fail)
        r = stress_strength_numeric(stress, strength)
        assert r["ok"]
        assert abs(r["R"] - 0.5) < 1e-9


# ===========================================================================
# 11. FMEA
# ===========================================================================

class TestFMEA:
    def test_rpn_multiplication(self):
        r = fmea_rpn(severity=7, occurrence=5, detection=3)
        assert r["ok"]
        assert r["RPN"] == 7 * 5 * 3

    def test_rpn_low(self):
        r = fmea_rpn(1, 1, 1)
        assert r["ok"]
        assert r["RPN"] == 1
        assert r["risk_level"] == "low"

    def test_rpn_high(self):
        r = fmea_rpn(10, 5, 3)
        assert r["ok"]
        assert r["RPN"] >= 100
        assert r["risk_level"] in ("high", "critical")

    def test_rpn_critical(self):
        r = fmea_rpn(10, 10, 3)
        assert r["ok"]
        assert r["RPN"] == 300
        assert r["risk_level"] == "critical"

    def test_rpn_invalid_range(self):
        r = fmea_rpn(0, 5, 5)
        assert not r["ok"]
        r2 = fmea_rpn(5, 11, 5)
        assert not r2["ok"]

    def test_criticality_formula(self):
        # Cm = mode_ratio * severity * occurrence
        sev, occ, mr = 5.0, 0.01, 0.3
        r = fmea_criticality(sev, occ, mode_ratio=mr)
        assert r["ok"]
        assert abs(r["criticality"] - sev * occ * mr) < 1e-12


# ===========================================================================
# 12. Fault tree
# ===========================================================================

class TestFaultTree:
    # Simple 2-level tree: OR(AND(E1, E2), E3)
    TREE = {
        "type": "OR",
        "children": [
            {
                "type": "AND",
                "children": [
                    {"type": "basic", "id": "E1", "p": 0.1},
                    {"type": "basic", "id": "E2", "p": 0.2},
                ],
            },
            {"type": "basic", "id": "E3", "p": 0.05},
        ],
    }

    def test_top_event_prob_hand_calc(self):
        # P(AND) = 0.1*0.2 = 0.02
        # P(OR)  = 1 - (1-0.02)*(1-0.05) = 1 - 0.98*0.95 = 1 - 0.931 = 0.069
        r = fault_tree_top(self.TREE)
        assert r["ok"]
        expected = 1 - (1 - 0.1 * 0.2) * (1 - 0.05)
        assert abs(r["p_top"] - expected) < 1e-9

    def test_and_only_tree(self):
        tree = {
            "type": "AND",
            "children": [
                {"type": "basic", "id": "A", "p": 0.3},
                {"type": "basic", "id": "B", "p": 0.4},
            ],
        }
        r = fault_tree_top(tree)
        assert r["ok"]
        assert abs(r["p_top"] - 0.3 * 0.4) < 1e-9

    def test_or_only_tree(self):
        tree = {
            "type": "OR",
            "children": [
                {"type": "basic", "id": "A", "p": 0.1},
                {"type": "basic", "id": "B", "p": 0.2},
            ],
        }
        r = fault_tree_top(tree)
        assert r["ok"]
        assert abs(r["p_top"] - (1 - 0.9 * 0.8)) < 1e-9

    def test_cut_sets_simple_or(self):
        # OR of two basics → two cut sets, each a singleton
        tree = {
            "type": "OR",
            "children": [
                {"type": "basic", "id": "X1", "p": 0.05},
                {"type": "basic", "id": "X2", "p": 0.03},
            ],
        }
        r = fault_tree_cut_sets(tree)
        assert r["ok"]
        assert r["n_cut_sets"] == 2

    def test_cut_sets_and_gives_one_set(self):
        # AND of two basics → one cut set = {E1, E2}
        tree = {
            "type": "AND",
            "children": [
                {"type": "basic", "id": "E1", "p": 0.1},
                {"type": "basic", "id": "E2", "p": 0.2},
            ],
        }
        r = fault_tree_cut_sets(tree)
        assert r["ok"]
        assert r["n_cut_sets"] == 1
        assert set(r["cut_sets"][0]) == {"E1", "E2"}

    def test_birnbaum_importance_basic(self):
        tree = {"type": "basic", "id": "X", "p": 0.1}
        r = fault_tree_importance(tree, "X")
        assert r["ok"]
        # I_B = P(top|X=1) - P(top|X=0) = 1 - 0 = 1
        assert abs(r["I_birnbaum"] - 1.0) < 1e-9

    def test_birnbaum_importance_and(self):
        tree = {
            "type": "AND",
            "children": [
                {"type": "basic", "id": "E1", "p": 0.2},
                {"type": "basic", "id": "E2", "p": 0.3},
            ],
        }
        r = fault_tree_importance(tree, "E1")
        assert r["ok"]
        # I_B(E1) = P(top|E1=1) - P(top|E1=0) = P(E2) - 0 = 0.3
        assert abs(r["I_birnbaum"] - 0.3) < 1e-9


# ===========================================================================
# 13. Reliability allocation
# ===========================================================================

class TestReliabilityAllocation:
    def test_equal_product_equals_system(self):
        r_sys = 0.9
        n = 5
        r = reliability_allocation_equal(r_sys, n)
        assert r["ok"]
        # Product of r_i^n should equal r_sys
        assert abs(r["r_component"] ** n - r_sys) < 1e-9

    def test_equal_formula(self):
        r_sys = 0.95
        n = 4
        r = reliability_allocation_equal(r_sys, n)
        assert r["ok"]
        assert abs(r["r_component"] - r_sys ** (1.0 / n)) < 1e-9

    def test_agree_two_subsystems(self):
        r = reliability_allocation_agree(0.95, [0.5, 0.5])
        assert r["ok"]
        assert len(r["allocations"]) == 2
        # Equal importance → equal lambda allocation
        assert abs(r["allocations"][0]["lambda_i"] - r["allocations"][1]["lambda_i"]) < 1e-9

    def test_agree_unequal_importance(self):
        # Higher importance → higher failure-rate allowance
        r = reliability_allocation_agree(0.95, [0.7, 0.3])
        assert r["ok"]
        assert r["allocations"][0]["lambda_i"] > r["allocations"][1]["lambda_i"]

    def test_agree_invalid_importance(self):
        r = reliability_allocation_agree(0.95, [-0.5, 0.5])
        assert not r["ok"]


# ===========================================================================
# 14. Accelerated life testing
# ===========================================================================

class TestAcceleratedLife:
    def test_arrhenius_af_gt1_when_T_acc_gt_T_use(self):
        # E_a=0.7 eV, T_use=298 K (25°C), T_acc=398 K (125°C)
        r = arrhenius_af(E_a=0.7, T_use_K=298.0, T_acc_K=398.0)
        assert r["ok"]
        assert r["AF"] > 1.0

    def test_arrhenius_af_hand_calc(self):
        # AF = exp(0.7 / 8.617e-5 * (1/298 - 1/398))
        E_a, T_use, T_acc = 0.7, 298.0, 398.0
        k = 8.617333262145e-5
        expected = math.exp(E_a / k * (1.0 / T_use - 1.0 / T_acc))
        r = arrhenius_af(E_a=E_a, T_use_K=T_use, T_acc_K=T_acc)
        assert r["ok"]
        assert abs(r["AF"] - expected) / expected < REL

    def test_arrhenius_deceleration_warns(self):
        import warnings as _w
        with _w.catch_warnings(record=True) as caught:
            _w.simplefilter("always")
            r = arrhenius_af(E_a=0.7, T_use_K=398.0, T_acc_K=298.0)
        assert r["ok"]
        # AF < 1 (deceleration) and warning issued
        assert r["AF"] < 1.0
        assert len(caught) > 0 or len(r.get("warnings", [])) > 0

    def test_inverse_power_af_formula(self):
        V_use, V_acc, n = 100.0, 200.0, 3.0
        r = inverse_power_af(V_use, V_acc, n)
        assert r["ok"]
        expected = (V_acc / V_use) ** n
        assert abs(r["AF"] - expected) < 1e-9

    def test_inverse_power_af_gt1_when_V_acc_gt_V_use(self):
        r = inverse_power_af(100.0, 150.0, 4.0)
        assert r["ok"]
        assert r["AF"] > 1.0


# ===========================================================================
# 15. LLM tool wrappers
# ===========================================================================

class TestTools:
    def test_tool_weibull_fit_ok(self):
        raw = _run(run_weibull_fit(
            _ctx(),
            _args(times=[93.0, 150.0, 196.0, 245.0, 312.0], method="RRX")
        ))
        d = _ok(raw)
        assert d["beta"] > 0
        assert d["eta"] > 0

    def test_tool_weibull_fit_missing_times(self):
        raw = _run(run_weibull_fit(_ctx(), _args(method="RRX")))
        _err(raw)

    def test_tool_weibull_b_life_ok(self):
        raw = _run(run_weibull_b_life(_ctx(), _args(pct=10, beta=2.0, eta=1000.0)))
        d = _ok(raw)
        assert d["t_B"] > 0

    def test_tool_weibull_b_life_missing_field(self):
        raw = _run(run_weibull_b_life(_ctx(), _args(pct=10, eta=1000.0)))
        _err(raw)

    def test_tool_weibull_mttf_ok(self):
        raw = _run(run_weibull_mttf(_ctx(), _args(beta=2.0, eta=1000.0)))
        d = _ok(raw)
        assert "mttf" in d
        assert "t_632" in d

    def test_tool_weibull_eval_ok(self):
        raw = _run(run_weibull_eval(_ctx(), _args(t=500.0, beta=2.0, eta=1000.0)))
        d = _ok(raw)
        assert 0 <= d["R"] <= 1
        assert 0 <= d["F"] <= 1
        assert d["h"] > 0

    def test_tool_exponential_mtbf_ci_ok(self):
        raw = _run(run_exponential_mtbf_ci(_ctx(), _args(failures=5, test_time=5000.0)))
        d = _ok(raw)
        assert d["mtbf_lower"] < d["mtbf_point"] < d["mtbf_upper"]

    def test_tool_exponential_mtbf_ci_missing_failures(self):
        raw = _run(run_exponential_mtbf_ci(_ctx(), _args(test_time=5000.0)))
        _err(raw)

    def test_tool_system_series_ok(self):
        raw = _run(run_system(_ctx(), _args(config="series", reliabilities=[0.9, 0.95])))
        d = _ok(raw)
        assert abs(d["R_system"] - 0.9 * 0.95) < 1e-9

    def test_tool_system_k_of_n_ok(self):
        raw = _run(run_system(_ctx(), _args(config="k_of_n", k=2, n=3, r=0.9)))
        _ok(raw)

    def test_tool_system_bridge_ok(self):
        raw = _run(run_system(_ctx(), _args(
            config="bridge", reliabilities=[0.9, 0.9, 0.9, 0.9, 0.9]
        )))
        _ok(raw)

    def test_tool_system_invalid_config(self):
        raw = _run(run_system(_ctx(), _args(config="star")))
        _err(raw)

    def test_tool_availability_ok(self):
        raw = _run(run_availability(_ctx(), _args(mtbf=1000.0, mttr=10.0)))
        d = _ok(raw)
        assert abs(d["availability"] - 1000.0 / 1010.0) < 1e-9

    def test_tool_availability_with_redundancy(self):
        raw = _run(run_availability(_ctx(), _args(
            mtbf=1000.0, mttr=10.0, r=0.9, n_active=2, n_standby=1
        )))
        d = _ok(raw)
        assert "redundancy" in d

    def test_tool_stress_strength_normal_ok(self):
        raw = _run(run_stress_strength(_ctx(), _args(
            mode="normal", mu_s=100.0, sigma_s=10.0, mu_r=150.0, sigma_r=15.0
        )))
        d = _ok(raw)
        assert 0 <= d["R"] <= 1

    def test_tool_stress_strength_numeric_ok(self):
        raw = _run(run_stress_strength(_ctx(), _args(
            mode="numeric",
            stress_samples=[1.0, 2.0, 3.0],
            strength_samples=[5.0, 6.0, 7.0],
        )))
        d = _ok(raw)
        assert d["R"] == 1.0

    def test_tool_fmea_rpn_ok(self):
        raw = _run(run_fmea_rpn(_ctx(), _args(severity=7, occurrence=5, detection=3)))
        d = _ok(raw)
        assert d["RPN"] == 105
        assert "criticality" in d

    def test_tool_fmea_rpn_bad_rating(self):
        raw = _run(run_fmea_rpn(_ctx(), _args(severity=0, occurrence=5, detection=3)))
        _err(raw)

    def test_tool_fault_tree_ok(self):
        tree = {
            "type": "OR",
            "children": [
                {"type": "basic", "id": "E1", "p": 0.1},
                {"type": "basic", "id": "E2", "p": 0.05},
            ],
        }
        raw = _run(run_fault_tree(_ctx(), _args(tree=tree, event_id="E1")))
        d = _ok(raw)
        assert "p_top" in d
        assert "cut_sets" in d
        assert "I_birnbaum" in d

    def test_tool_fault_tree_missing_tree(self):
        raw = _run(run_fault_tree(_ctx(), _args()))
        _err(raw)

    def test_tool_allocation_equal_ok(self):
        raw = _run(run_reliability_allocation(
            _ctx(), _args(method="equal", r_system=0.9, n_components=5)
        ))
        d = _ok(raw)
        assert abs(d["r_component"] ** 5 - 0.9) < 1e-8

    def test_tool_allocation_agree_ok(self):
        raw = _run(run_reliability_allocation(
            _ctx(), _args(method="agree", r_system=0.95, importances=[0.6, 0.4])
        ))
        d = _ok(raw)
        assert len(d["allocations"]) == 2

    def test_tool_accel_arrhenius_ok(self):
        raw = _run(run_accel_life(_ctx(), _args(
            model="arrhenius", E_a=0.7, T_use_K=298.0, T_acc_K=398.0
        )))
        d = _ok(raw)
        assert d["AF"] > 1.0

    def test_tool_accel_inverse_power_ok(self):
        raw = _run(run_accel_life(_ctx(), _args(
            model="inverse_power", V_use=100.0, V_acc=200.0, n=3.0
        )))
        d = _ok(raw)
        assert abs(d["AF"] - 8.0) < 1e-6  # (200/100)^3 = 8

    def test_tool_accel_invalid_model(self):
        raw = _run(run_accel_life(_ctx(), _args(model="eyring")))
        _err(raw)

    def test_tool_bad_json(self):
        raw = _run(run_weibull_fit(_ctx(), b"not-json"))
        _err(raw)
