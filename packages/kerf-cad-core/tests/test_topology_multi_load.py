"""
Hermetic analytic-oracle tests for
kerf_cad_core.topology.multi_load.

All tests are pure-Python and require no external solvers, no OCC, no DB and
no network access.  Where an FE solve is required a lightweight hand-rolled
stub is used.

Coverage
--------
weighted_compliance
    Verify the weighted sum formula on concrete numeric examples.

accumulate_sensitivity
    Verify linear aggregation of per-load-case sensitivities.

normalise_weights
    Unit tests for edge cases (empty, negatives, zero sum).

LoadCase
    Construction validation.

element_sensitivity
    Analytic check: matches the exact SIMP formula for a single element.

pareto_two_load
    Structural trade-off test: a structure optimised for a vertical load is
    suboptimal for a horizontal load (and vice versa), proving a genuine
    Pareto front exists.

    The solve_fn is a closed-form stub that mimics a 2-element "truss" where
    load 1 (vertical) needs a horizontal member and load 2 (horizontal) needs
    a vertical member.  The compliance values are analytic.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Tuple

import pytest

from kerf_cad_core.topology.multi_load import (
    LoadCase,
    accumulate_sensitivity,
    element_sensitivity,
    normalise_weights,
    pareto_two_load,
    weighted_compliance,
)


# ---------------------------------------------------------------------------
# 1. weighted_compliance
# ---------------------------------------------------------------------------

class TestWeightedCompliance:

    def test_single_load(self):
        assert weighted_compliance([10.0], [1.0]) == pytest.approx(10.0)

    def test_equal_weights(self):
        result = weighted_compliance([4.0, 6.0], [1.0, 1.0])
        assert result == pytest.approx(10.0)

    def test_unequal_weights(self):
        result = weighted_compliance([4.0, 6.0], [0.3, 0.7])
        assert result == pytest.approx(0.3 * 4.0 + 0.7 * 6.0)

    def test_zero_weight_ignores_compliance(self):
        result = weighted_compliance([999.0, 5.0], [0.0, 1.0])
        assert result == pytest.approx(5.0)

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError, match="same length"):
            weighted_compliance([1.0, 2.0], [0.5])

    def test_negative_weight_raises(self):
        with pytest.raises(ValueError, match="negative"):
            weighted_compliance([1.0, 2.0], [0.5, -0.1])

    def test_zero_compliance(self):
        assert weighted_compliance([0.0, 0.0], [0.5, 0.5]) == pytest.approx(0.0)

    def test_float_result_type(self):
        result = weighted_compliance([3], [2])
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# 2. accumulate_sensitivity
# ---------------------------------------------------------------------------

class TestAccumulateSensitivity:

    def test_single_case_identity(self):
        dc = [-0.2, -0.5, -0.3]
        result = accumulate_sensitivity([dc], [1.0])
        assert len(result) == 3
        for a, b in zip(result, dc):
            assert a == pytest.approx(b)

    def test_two_equal_weights(self):
        dc1 = [-1.0, -2.0, -3.0]
        dc2 = [-3.0, -2.0, -1.0]
        result = accumulate_sensitivity([dc1, dc2], [0.5, 0.5])
        expected = [-2.0, -2.0, -2.0]
        for a, b in zip(result, expected):
            assert a == pytest.approx(b)

    def test_two_asymmetric_weights(self):
        dc1 = [1.0, 0.0]
        dc2 = [0.0, 1.0]
        result = accumulate_sensitivity([dc1, dc2], [0.3, 0.7])
        assert result[0] == pytest.approx(0.3)
        assert result[1] == pytest.approx(0.7)

    def test_length_mismatch_cases_raises(self):
        with pytest.raises(ValueError, match="same length"):
            accumulate_sensitivity([[-1.0], [-1.0]], [0.5])

    def test_inconsistent_nel_raises(self):
        with pytest.raises(ValueError, match="expected"):
            accumulate_sensitivity([[-1.0, -2.0], [-1.0]], [0.5, 0.5])

    def test_empty_returns_empty(self):
        result = accumulate_sensitivity([], [])
        assert result == []

    def test_output_length(self):
        n = 50
        dc1 = [-0.1] * n
        dc2 = [-0.2] * n
        result = accumulate_sensitivity([dc1, dc2], [0.6, 0.4])
        assert len(result) == n


# ---------------------------------------------------------------------------
# 3. normalise_weights
# ---------------------------------------------------------------------------

class TestNormaliseWeights:

    def test_already_normalised(self):
        w = [0.3, 0.7]
        result = normalise_weights(w)
        assert abs(sum(result) - 1.0) < 1e-12
        assert result[0] == pytest.approx(0.3)
        assert result[1] == pytest.approx(0.7)

    def test_uniform(self):
        result = normalise_weights([2.0, 2.0, 2.0])
        for v in result:
            assert v == pytest.approx(1.0 / 3.0)

    def test_single_weight(self):
        result = normalise_weights([5.0])
        assert result[0] == pytest.approx(1.0)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            normalise_weights([])

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="negative"):
            normalise_weights([1.0, -0.1])

    def test_zero_sum_raises(self):
        with pytest.raises(ValueError, match="zero"):
            normalise_weights([0.0, 0.0])

    def test_sum_is_one(self):
        result = normalise_weights([3.0, 1.0, 4.0, 1.0, 5.0])
        assert abs(sum(result) - 1.0) < 1e-12


# ---------------------------------------------------------------------------
# 4. LoadCase
# ---------------------------------------------------------------------------

class TestLoadCase:

    def test_construction(self):
        lc = LoadCase([0.0, -1.0, 0.0], [0, 2], name="vert", weight=0.5)
        assert lc.name == "vert"
        assert lc.weight == pytest.approx(0.5)
        assert len(lc.F) == 3
        assert lc.fixed == [0, 2]

    def test_negative_weight_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            LoadCase([1.0], [], weight=-0.1)

    def test_copies_mutable_inputs(self):
        F = [1.0, 2.0]
        fixed = [0]
        lc = LoadCase(F, fixed)
        F.append(99.0)
        fixed.append(99)
        assert len(lc.F) == 2
        assert len(lc.fixed) == 1

    def test_default_weight(self):
        lc = LoadCase([0.0], [])
        assert lc.weight == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 5. element_sensitivity
# ---------------------------------------------------------------------------

class TestElementSensitivity:

    def test_analytic_formula_single_element(self):
        """For one element with xphys=0.5, ce=2.0, p=3, Emin=0:
            dc = -3 * 0.5^2 * 1.0 * 2.0 = -1.5
        """
        xphys = [0.5]
        ce = [2.0]
        dc = element_sensitivity(xphys, ce, penal=3.0, Emin=0.0)
        expected = -3.0 * (0.5 ** 2.0) * 1.0 * 2.0
        assert dc[0] == pytest.approx(expected, rel=1e-9)

    def test_non_positive_output(self):
        """Sensitivities must be <= 0 for positive densities and strain energy."""
        xphys = [0.1, 0.5, 0.9, 1.0]
        ce = [0.5, 1.0, 2.0, 0.3]
        dc = element_sensitivity(xphys, ce, penal=3.0)
        for i, v in enumerate(dc):
            assert v <= 0.0 + 1e-15, (
                f"Sensitivity[{i}] = {v} should be non-positive."
            )

    def test_void_element_zero_sensitivity(self):
        """An element with near-zero density should produce ~0 sensitivity."""
        xphys = [1e-15]
        ce = [100.0]
        dc = element_sensitivity(xphys, ce, penal=3.0, Emin=0.0)
        assert dc[0] == pytest.approx(0.0, abs=1e-10)

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError, match="same length"):
            element_sensitivity([0.5, 0.5], [1.0], penal=3.0)

    def test_length_preserved(self):
        n = 30
        xphys = [0.4] * n
        ce = [1.0] * n
        dc = element_sensitivity(xphys, ce, penal=3.0)
        assert len(dc) == n

    def test_full_density_solid_sensitivity(self):
        """At xphys=1, E(1)=1: dc = -p * 1^(p-1) * (1-Emin) * ce = -p * ce."""
        xphys = [1.0]
        ce = [3.0]
        dc = element_sensitivity(xphys, ce, penal=3.0, Emin=0.0)
        assert dc[0] == pytest.approx(-3.0 * 3.0, rel=1e-9)


# ---------------------------------------------------------------------------
# 6. Pareto two-load trade-off test
# ---------------------------------------------------------------------------

class TestParetoTwoLoad:
    """Analytic stub: two orthogonal bars.

    Consider a two-element "truss" where element 1 carries load 1 and
    element 2 carries load 2.  The designer controls the volume fraction v
    (how much of the total material goes into element 1 versus element 2):

        element 1 area = v          element 2 area = 1 - v

    Compliance under load 1 is proportional to 1/v (stiffer element 1 →
    lower compliance under load 1); compliance under load 2 is proportional
    to 1/(1-v).

    The weighted objective is w1*(1/v) + w2*(1/(1-v)).  The optimal v is:

        v* = sqrt(w1) / (sqrt(w1) + sqrt(w2))

    giving C1* = (sqrt(w1)+sqrt(w2))^2 / w1^(1/2) ... simplified:
        C1 = 1 / v* = (sqrt(w1)+sqrt(w2)) / sqrt(w1)
        C2 = 1 / (1-v*) = (sqrt(w1)+sqrt(w2)) / sqrt(w2)

    This is an exact closed-form Pareto curve.  The test confirms:
    1. solve_fn returns correct values for w1=1 and w1=0 (endpoints).
    2. pareto_two_load detects a genuine trade-off.
    3. As w1 increases (more emphasis on load 1) C1 decreases and C2
       increases — the classical opposing trend.
    """

    @staticmethod
    def _two_bar_solve(w1: float, w2: float) -> Tuple[float, float]:
        """Closed-form optimal compliance for the two-bar problem."""
        # Handle degenerate endpoint cases.
        if w1 <= 0.0:
            # All material to element 2: v* → 0
            v_star = 1e-9
        elif w2 <= 0.0:
            # All material to element 1: v* → 1
            v_star = 1.0 - 1e-9
        else:
            sw1 = math.sqrt(w1)
            sw2 = math.sqrt(w2)
            v_star = sw1 / (sw1 + sw2)
        c1 = 1.0 / v_star
        c2 = 1.0 / (1.0 - v_star)
        return c1, c2

    def test_trade_off_detected(self):
        """pareto_two_load must flag trade_off_exists=True for the two-bar stub."""
        result = pareto_two_load(self._two_bar_solve, n_points=11)
        assert result["ok"] is True, result.get("reason")
        assert result["trade_off_exists"] is True, (
            "No trade-off detected: structure optimal for load 1 is also "
            "optimal for load 2 — this is wrong for the two-bar problem."
        )

    def test_endpoints_analytic(self):
        """At w1=1 (all load-1 optimised) C1 is minimised; at w1=0 C2 is."""
        result = pareto_two_load(self._two_bar_solve, n_points=11)
        assert result["ok"] is True
        front = result["front"]

        # w1=0 endpoint: all material in element 2 → C1 very large, C2 minimum.
        p0 = front[0]  # w1=0
        assert p0["w1"] == pytest.approx(0.0, abs=1e-9)
        assert p0["C2"] < p0["C1"]  # load 2 is cheap, load 1 is expensive

        # w1=1 endpoint: all material in element 1 → C2 very large, C1 minimum.
        p1 = front[-1]  # w1=1
        assert p1["w1"] == pytest.approx(1.0, abs=1e-9)
        assert p1["C1"] < p1["C2"]  # load 1 is cheap, load 2 is expensive

    def test_c1_decreasing_as_w1_increases(self):
        """As w1 increases (more emphasis on load 1) C1 should decrease."""
        result = pareto_two_load(self._two_bar_solve, n_points=11)
        front = result["front"]
        c1_values = [p["C1"] for p in front]
        # Monotone non-increasing: C1 must not increase as w1 increases.
        for i in range(1, len(c1_values)):
            assert c1_values[i] <= c1_values[i - 1] + 1e-9, (
                f"C1 increased from step {i-1} to {i}: "
                f"{c1_values[i-1]:.4f} → {c1_values[i]:.4f}"
            )

    def test_c2_increasing_as_w1_increases(self):
        """As w1 increases (less emphasis on load 2) C2 should increase."""
        result = pareto_two_load(self._two_bar_solve, n_points=11)
        front = result["front"]
        c2_values = [p["C2"] for p in front]
        for i in range(1, len(c2_values)):
            assert c2_values[i] >= c2_values[i - 1] - 1e-9, (
                f"C2 decreased from step {i-1} to {i}: "
                f"{c2_values[i-1]:.4f} → {c2_values[i]:.4f}"
            )

    def test_n_points_correct(self):
        """front must contain exactly n_points entries."""
        result = pareto_two_load(self._two_bar_solve, n_points=7)
        assert result["n_points"] == 7
        assert len(result["front"]) == 7

    def test_w1_plus_w2_equals_one(self):
        """In every front point w1 + w2 must sum to 1."""
        result = pareto_two_load(self._two_bar_solve, n_points=9)
        for p in result["front"]:
            assert p["w1"] + p["w2"] == pytest.approx(1.0, abs=1e-9)

    def test_n_points_less_than_2_returns_error(self):
        """n_points < 2 must return ok=False."""
        result = pareto_two_load(self._two_bar_solve, n_points=1)
        assert result["ok"] is False
        assert "reason" in result

    def test_solve_fn_exception_propagates_as_ok_false(self):
        """If solve_fn raises, pareto_two_load must return ok=False."""
        def bad_solve(w1, w2):
            raise RuntimeError("engine crashed")

        result = pareto_two_load(bad_solve, n_points=5)
        assert result["ok"] is False
        assert "engine crashed" in result.get("reason", "")

    def test_front_sorted_by_w1(self):
        """Front must be sorted by ascending w1."""
        result = pareto_two_load(self._two_bar_solve, n_points=11)
        front = result["front"]
        w1_vals = [p["w1"] for p in front]
        assert w1_vals == sorted(w1_vals)

    def test_optimal_structure_load1_suboptimal_for_load2(self):
        """The structure with w1=1 (load-1 optimal) must have higher C2 than
        the structure with w1=0 (load-2 optimal) by a significant margin.

        This is the key Pareto trade-off assertion: you cannot simultaneously
        minimise compliance for two orthogonal loads with one design.
        """
        result = pareto_two_load(self._two_bar_solve, n_points=11)
        front = result["front"]

        c2_load1_optimal = front[-1]["C2"]   # w1=1 design's load-2 compliance
        c2_load2_optimal = front[0]["C2"]    # w1=0 design's load-2 compliance

        # The w1=1 design must be significantly worse for load 2.
        assert c2_load1_optimal > c2_load2_optimal * 1.5, (
            f"Expected significant Pareto trade-off: C2 for load-1-optimal design "
            f"({c2_load1_optimal:.2f}) should be >> C2 for load-2-optimal design "
            f"({c2_load2_optimal:.2f})."
        )

        c1_load1_optimal = front[-1]["C1"]   # w1=1 design's load-1 compliance
        c1_load2_optimal = front[0]["C1"]    # w1=0 design's load-1 compliance

        # And the load-2-optimal design must be significantly worse for load 1.
        assert c1_load2_optimal > c1_load1_optimal * 1.5, (
            f"Expected significant Pareto trade-off: C1 for load-2-optimal design "
            f"({c1_load2_optimal:.2f}) should be >> C1 for load-1-optimal design "
            f"({c1_load1_optimal:.2f})."
        )
