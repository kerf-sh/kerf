"""
Tests for kerf_cad_core.spc — SPC control charts.

Validation against:
  - ASTM E2587 Table 1 Shewhart constants (A2, A3, B3, B4, D3, D4)
  - Montgomery (2020) §6 textbook X̄-R example (piston ring outer diameter)
  - Textbook CUSUM example (known shift detection)
  - EWMA steady-state limit formula
  - Nelson / WECO run-rule definitions

All tests are pure-Python and hermetic.

References
----------
Montgomery, D.C. (2020). Introduction to Statistical Quality Control, 8th ed.
  §6.2 (X-bar R), §9.1 (CUSUM), §9.2 (EWMA).
ASTM E2587-16, Table 1.
Nelson, L.S. (1984). JQT 16(4): 237-239.

Author: imranparuk
"""
from __future__ import annotations

import math
import pytest

from kerf_cad_core.spc import (
    xbar_r_chart,
    xbar_s_chart,
    cusum_chart,
    ewma_chart,
    run_rules,
)
from kerf_cad_core.spc.charts import _SHEWHART_CONSTANTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _near(a: float, b: float, rel: float = 1e-4, abs_tol: float = 1e-9) -> bool:
    return abs(a - b) <= max(rel * max(abs(a), abs(b), 1.0), abs_tol)


# ---------------------------------------------------------------------------
# ASTM E2587 Table 1 — Shewhart constants spot-checks
# ---------------------------------------------------------------------------

def test_shewhart_constants_n2():
    """ASTM E2587 Table 1 for n=2."""
    c = _SHEWHART_CONSTANTS[2]
    assert _near(c["A2"], 1.880)
    assert _near(c["D4"], 3.267)
    assert _near(c["D3"], 0.000)
    assert _near(c["d2"], 1.128)
    assert _near(c["c4"], 0.7979)


def test_shewhart_constants_n5():
    """ASTM E2587 Table 1 for n=5."""
    c = _SHEWHART_CONSTANTS[5]
    assert _near(c["A2"], 0.577)
    assert _near(c["D3"], 0.000)
    assert _near(c["D4"], 2.114)
    assert _near(c["A3"], 1.427)
    assert _near(c["B3"], 0.000)
    assert _near(c["B4"], 2.089)


def test_shewhart_constants_n10():
    """ASTM E2587 Table 1 for n=10."""
    c = _SHEWHART_CONSTANTS[10]
    assert _near(c["A2"], 0.308)
    assert _near(c["D3"], 0.223)
    assert _near(c["D4"], 1.777)
    assert _near(c["A3"], 0.975)
    assert _near(c["B3"], 0.284)
    assert _near(c["B4"], 1.716)
    assert _near(c["c4"], 0.9727)


def test_shewhart_constants_n25():
    """ASTM E2587 Table 1 for n=25."""
    c = _SHEWHART_CONSTANTS[25]
    assert _near(c["A2"], 0.153)
    assert _near(c["D4"], 1.541)
    assert _near(c["c4"], 0.9896)


# ---------------------------------------------------------------------------
# X̄-R chart — textbook example
# Montgomery §6.2: Piston ring outer diameters (74.xxx inches), n=5
# We use a simplified version with known grand-mean and R-bar.
# ---------------------------------------------------------------------------

def _make_xbar_r_data():
    """
    Simplified piston-ring-style data.
    20 subgroups of n=5, structured so x̄̄ ≈ 74.001, R̄ ≈ 0.023.
    These data come from Montgomery Table 6.2 (first 20 subgroups).
    """
    # Each inner list is one subgroup of 5
    subgroups = [
        [74.030, 74.002, 74.019, 73.992, 74.008],
        [73.995, 73.992, 74.001, 74.011, 74.004],
        [73.988, 74.024, 74.021, 74.005, 74.002],
        [74.002, 73.996, 73.993, 74.015, 74.009],
        [73.992, 74.007, 74.015, 73.989, 74.014],
        [74.009, 73.994, 73.997, 73.985, 73.993],
        [73.995, 74.006, 73.994, 74.000, 74.005],
        [73.985, 74.003, 73.993, 74.015, 73.988],
        [74.008, 73.995, 74.009, 74.005, 74.004],
        [73.998, 74.000, 73.990, 74.007, 73.995],
        [73.994, 73.998, 73.994, 73.995, 73.990],
        [74.004, 74.000, 74.007, 74.000, 73.996],
        [73.983, 74.002, 73.998, 73.997, 74.012],
        [74.006, 73.967, 73.994, 74.000, 73.984],
        [74.012, 74.014, 73.998, 73.999, 74.007],
        [74.000, 73.984, 74.005, 73.998, 73.996],
        [73.994, 74.012, 73.986, 74.005, 74.007],
        [74.006, 74.010, 74.018, 74.003, 74.000],
        [73.984, 74.002, 74.003, 74.005, 73.997],
        [74.000, 74.010, 74.013, 74.020, 74.003],
    ]
    return [x for sg in subgroups for x in sg]


def test_xbar_r_subgroup_count():
    data = _make_xbar_r_data()
    r = xbar_r_chart(data, n=5)
    assert r["ok"]
    assert r["k"] == 20
    assert r["n"] == 5


def test_xbar_r_limits_structure():
    data = _make_xbar_r_data()
    r = xbar_r_chart(data, n=5)
    assert r["ok"]
    assert r["xbar_ucl"] > r["xbar_cl"] > r["xbar_lcl"]
    assert r["r_ucl"] > r["r_cl"] >= 0.0  # D3=0 for n=5


def test_xbar_r_formula_manual():
    """
    Manually verify UCL/LCL formula:
      UCL_xbar = x̄̄ + A2 * R̄
      LCL_xbar = x̄̄ - A2 * R̄
    """
    data = _make_xbar_r_data()
    r = xbar_r_chart(data, n=5)
    A2 = r["constants"]["A2"]
    xbar_bar = r["xbar_bar"]
    r_bar = r["r_bar"]
    expected_ucl = xbar_bar + A2 * r_bar
    expected_lcl = xbar_bar - A2 * r_bar
    assert _near(r["xbar_ucl"], expected_ucl)
    assert _near(r["xbar_lcl"], expected_lcl)


def test_xbar_r_sigma_estimate():
    """Estimated sigma = R̄/d2."""
    data = _make_xbar_r_data()
    r = xbar_r_chart(data, n=5)
    d2 = r["constants"]["d2"]
    expected_sigma = r["r_bar"] / d2
    assert _near(r["sigma_xbar_estimated"], expected_sigma)


def test_xbar_r_in_control_known_data():
    """The Montgomery piston-ring data (in-control) should have 0 OOC on X̄."""
    data = _make_xbar_r_data()
    r = xbar_r_chart(data, n=5)
    # This dataset is designed to be in-control; expect no OOC
    assert len(r["ooc_xbar"]) == 0, f"Unexpected OOC: {r['ooc_xbar']}"


def test_xbar_r_detects_ooc():
    """Insert an obvious outlier subgroup; should be flagged OOC."""
    data = _make_xbar_r_data()
    # Replace first subgroup with far-out values
    data[:5] = [80.0, 80.1, 80.0, 80.0, 80.0]
    r = xbar_r_chart(data, n=5)
    assert r["ok"]
    assert any(p["subgroup"] == 0 for p in r["ooc_xbar"]), "Outlier subgroup not flagged"


# ---------------------------------------------------------------------------
# X̄-S chart
# ---------------------------------------------------------------------------

def test_xbar_s_structure():
    data = _make_xbar_r_data()
    r = xbar_s_chart(data, n=5)
    assert r["ok"]
    assert r["k"] == 20
    assert r["xbar_ucl"] > r["xbar_cl"] > r["xbar_lcl"]
    assert r["s_ucl"] > r["s_cl"] >= r["s_lcl"]


def test_xbar_s_formula_manual():
    """
    UCL_xbar = x̄̄ + A3 * S̄
    UCL_s    = B4 * S̄
    """
    data = _make_xbar_r_data()
    r = xbar_s_chart(data, n=5)
    A3 = r["constants"]["A3"]
    B4 = r["constants"]["B4"]
    B3 = r["constants"]["B3"]
    assert _near(r["xbar_ucl"], r["xbar_bar"] + A3 * r["s_bar"])
    assert _near(r["s_ucl"], B4 * r["s_bar"])
    assert _near(r["s_lcl"], B3 * r["s_bar"])


def test_xbar_s_in_control():
    data = _make_xbar_r_data()
    r = xbar_s_chart(data, n=5)
    assert len(r["ooc_xbar"]) == 0


# ---------------------------------------------------------------------------
# CUSUM chart — textbook validation
# ---------------------------------------------------------------------------

def _cusum_textbook_data():
    """
    Montgomery §9.1 example:  μ₀=10, σ=1, k=0.5, h=5.
    Data: first 20 points from Montgomery Table 9.1 (in-control phase).
    Then a step shift of +2σ (12.0 region) starting at point 21.
    """
    in_ctrl = [
        9.45, 7.99, 9.29, 11.66, 12.16, 10.18, 8.04, 11.46, 9.20, 10.34,
        9.03, 11.47, 10.51, 9.40, 10.08, 9.37, 10.62, 10.31, 8.52, 10.84,
    ]
    shifted = [12.0 + 0.3 * (i % 3 - 1) for i in range(15)]
    return in_ctrl + shifted


def test_cusum_detects_shift():
    """CUSUM should detect an upward shift after the in-control phase."""
    data = _cusum_textbook_data()
    r = cusum_chart(data, target=10.0, k=0.5, h=5.0, sigma=1.0)
    assert r["ok"]
    # There should be OOC points in the shifted region (indices >= 20)
    ooc_indices = [p["index"] for p in r["ooc_high"]]
    assert any(idx >= 20 for idx in ooc_indices), f"No shift detected. OOC: {ooc_indices}"


def test_cusum_in_control_phase():
    """First 20 points (in-control) should not trigger CUSUM (or very few)."""
    data = _cusum_textbook_data()[:20]
    r = cusum_chart(data, target=10.0, k=0.5, h=5.0, sigma=1.0)
    assert r["ok"]
    # In-control phase should be clean
    assert len(r["ooc_high"]) == 0, f"False alarms: {r['ooc_high']}"


def test_cusum_no_sigma_estimates():
    """Without sigma, CUSUM estimates from moving range."""
    data = [10.0 + 0.5 * (i % 2 == 0) - 0.25 * (i % 3 == 0) for i in range(30)]
    r = cusum_chart(data, target=10.0)
    assert r["ok"]
    assert r["sigma"] > 0


def test_cusum_fast_initial_response():
    """FIR headstart initialises C+ at H/2."""
    data = [10.0] * 10
    r = cusum_chart(data, target=10.0, k=0.5, h=5.0, sigma=1.0, fast_initial_response=True)
    assert r["ok"]
    assert r["fast_initial_response"] is True
    # With constant on-target data, C+ should decrease from H/2
    assert r["c_pos"][0] <= r["H"] / 2.0


def test_cusum_known_c_pos():
    """
    Verify CUSUM accumulation for simple step.
    x = [11, 11, 11, ...], μ₀=10, σ=1, k=0.5 → K=0.5
    C_i+ = max(0, C_{i-1}+ + (x_i - 10) - 0.5) = max(0, C_{i-1}+ + 0.5)
    So C_0+ = 0.5, C_1+ = 1.0, C_2+ = 1.5, ...
    """
    data = [11.0] * 10
    r = cusum_chart(data, target=10.0, sigma=1.0, k=0.5, h=5.0)
    assert r["ok"]
    for i in range(10):
        expected = 0.5 * (i + 1)
        assert _near(r["c_pos"][i], expected, rel=1e-6), (
            f"c_pos[{i}] = {r['c_pos'][i]}, expected {expected}"
        )


# ---------------------------------------------------------------------------
# EWMA chart
# ---------------------------------------------------------------------------

def test_ewma_steady_state_limits():
    """
    Steady-state EWMA UCL = μ₀ + L * σ * sqrt(λ/(2-λ)).
    For λ=0.2, L=3, σ=1: UCL = 3 * sqrt(0.2/1.8) = 3 * sqrt(1/9) = 1.0
    """
    data = [10.0] * 20
    r = ewma_chart(data, lam=0.2, target=10.0, sigma=1.0, L=3.0, steady_state=True)
    assert r["ok"]
    expected_ss_sigma = math.sqrt(1.0 * 0.2 / 1.8)
    assert _near(r["sigma_ewma_ss"], expected_ss_sigma)
    expected_ucl = 10.0 + 3.0 * expected_ss_sigma
    assert _near(r["ucl"][0], expected_ucl)


def test_ewma_transient_limits():
    """Transient limits should converge to steady-state."""
    data = [10.0] * 50
    r = ewma_chart(data, lam=0.2, target=10.0, sigma=1.0, L=3.0, steady_state=False)
    assert r["ok"]
    # By point 50, transient ~ steady-state
    ss_sigma = math.sqrt(1.0 * 0.2 / 1.8)
    ss_ucl = 10.0 + 3.0 * ss_sigma
    assert _near(r["ucl"][-1], ss_ucl, rel=0.001)


def test_ewma_detects_shift():
    """Mean shift of 2σ should be detected by EWMA."""
    # In-control
    data = [10.0] * 20
    # Step shift of +2
    data += [12.0] * 20
    r = ewma_chart(data, lam=0.2, target=10.0, sigma=1.0, L=3.0, steady_state=True)
    assert r["ok"]
    ooc_idx = [p["index"] for p in r["ooc"]]
    assert any(idx >= 20 for idx in ooc_idx), f"Shift not detected. OOC: {ooc_idx}"


def test_ewma_lambda_one_is_shewhart():
    """
    λ=1.0 makes EWMA = the original observations (no smoothing),
    and limits = μ₀ ± L·σ (same as 3σ Shewhart).
    """
    data = [10.0] * 10
    r = ewma_chart(data, lam=1.0, target=10.0, sigma=1.0, L=3.0, steady_state=True)
    assert r["ok"]
    # σ_ewma = σ * sqrt(1/(2-1)) = σ
    assert _near(r["sigma_ewma_ss"], 1.0)
    assert _near(r["ucl"][0], 13.0)
    assert _near(r["lcl"][0], 7.0)


def test_ewma_first_value():
    """First EWMA value = λ*x_0 + (1-λ)*μ₀."""
    data = [12.0] + [10.0] * 9
    lam = 0.3
    r = ewma_chart(data, lam=lam, target=10.0, sigma=1.0)
    assert r["ok"]
    expected = lam * 12.0 + (1 - lam) * 10.0
    assert _near(r["ewma"][0], expected)


def test_ewma_bad_lambda():
    r = ewma_chart([10.0] * 5, lam=0.0)
    assert not r["ok"]
    r2 = ewma_chart([10.0] * 5, lam=1.1)
    assert not r2["ok"]


# ---------------------------------------------------------------------------
# Run rules
# ---------------------------------------------------------------------------

def test_run_rules_nelson1_flagged():
    """A point at +4σ should trigger nelson1."""
    center = 0.0
    sigma = 1.0
    data = [0.0] * 10 + [4.0]  # last point at +4σ
    r = run_rules(data, center=center, sigma=sigma)
    assert r["ok"]
    assert 10 in r["violations"]["nelson1"], f"nelson1 violations: {r['violations']['nelson1']}"
    assert r["any_violation"]


def test_run_rules_nelson1_not_flagged():
    """Points within ±3σ should not trigger nelson1."""
    data = [2.5] * 20
    r = run_rules(data, center=0.0, sigma=1.0)
    assert r["ok"]
    assert len(r["violations"]["nelson1"]) == 0


def test_run_rules_nelson2_run_above():
    """9 consecutive points above center → nelson2."""
    data = [1.0] * 9  # all above center=0
    r = run_rules(data, center=0.0, sigma=1.0)
    assert r["ok"]
    assert len(r["violations"]["nelson2"]) > 0, "nelson2 not triggered"


def test_run_rules_nelson2_not_triggered():
    """Fewer than 9 consecutive same side → no nelson2."""
    data = [1.0] * 8
    r = run_rules(data, center=0.0, sigma=1.0)
    assert r["ok"]
    assert len(r["violations"]["nelson2"]) == 0


def test_run_rules_nelson3_trend():
    """6 strictly increasing points → nelson3."""
    data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    r = run_rules(data, center=3.5, sigma=2.0)
    assert r["ok"]
    assert len(r["violations"]["nelson3"]) > 0, "nelson3 trend not detected"


def test_run_rules_nelson5_two_of_three():
    """2 of 3 consecutive beyond +2σ → nelson5."""
    sigma = 1.0
    center = 0.0
    # points at +2.5σ, 0, +2.5σ → 2 of 3 beyond ±2σ
    data = [2.5, 0.0, 2.5]
    r = run_rules(data, center=center, sigma=sigma)
    assert r["ok"]
    assert len(r["violations"]["nelson5"]) > 0, "nelson5 not detected"


def test_run_rules_nelson7_hugging():
    """15 consecutive within ±1σ → nelson7."""
    data = [0.5] * 15  # within ±1σ of center=0
    r = run_rules(data, center=0.0, sigma=1.0)
    assert r["ok"]
    assert len(r["violations"]["nelson7"]) > 0, "nelson7 not triggered"


def test_run_rules_weco4_eight_same_side():
    """8 consecutive same side of CL → weco4."""
    # Values above center=0 (even within ±1σ) count as same side
    data = [0.5] * 8  # all above center=0
    r = run_rules(data, center=0.0, sigma=2.0, rules=["weco4"])
    assert r["ok"]
    assert len(r["violations"]["weco4"]) > 0


def test_run_rules_subset():
    """Only requested rules are evaluated."""
    data = [0.0] * 20
    r = run_rules(data, center=0.0, sigma=1.0, rules=["nelson1"])
    assert r["ok"]
    assert "nelson1" in r["violations"]
    assert "nelson2" not in r["violations"]


def test_run_rules_no_sigma_estimates():
    """Without sigma, should estimate from moving range."""
    data = [10.0 + (i % 2) * 0.1 for i in range(20)]
    r = run_rules(data, center=10.05)
    assert r["ok"]
    assert r["sigma"] > 0


def test_run_rules_clean_process():
    """Perfectly in-control data should have no violations."""
    data = [0.0] * 30  # constant at center, within ±1σ always
    # Only check rules that won't trigger for zero-variance data
    r = run_rules(data, center=0.0, sigma=1.0, rules=["nelson1", "nelson3"])
    assert r["ok"]
    # nelson1: no OOC (all at exactly 0, within 3σ)
    assert len(r["violations"]["nelson1"]) == 0
    # nelson3: all equal values, not strictly monotone — no trend
    assert len(r["violations"]["nelson3"]) == 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_xbar_r_not_enough_data():
    r = xbar_r_chart([1.0, 2.0], n=5)  # less than one subgroup
    assert not r["ok"]


def test_xbar_r_bad_n():
    with pytest.raises(ValueError, match="out of range"):
        xbar_r_chart([1.0] * 10, n=1)


def test_cusum_too_few():
    r = cusum_chart([10.0])
    assert not r["ok"]


def test_ewma_empty():
    r = ewma_chart([])
    assert not r["ok"]


def test_run_rules_empty():
    r = run_rules([])
    assert not r["ok"]
