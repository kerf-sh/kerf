"""
Hermetic tests for kerf_cad_core.rigging — lifting & rigging engineering.

Coverage (≥30 tests):
  lift.sling_tension            — angle-factor formula, edge-cases, warnings
  lift.multi_leg_share          — 2/3/4-leg equal and unequal, flexible/rigid
  lift.cg_pick_loads            — 2/3/4-point CG distributions, stability flag
  lift.sling_wll_derate         — sling/eyebolt/shackle derate tables
  lift.wire_rope_capacity       — table lookup, WLL computation
  lift.chain_capacity           — grade_80 / grade_100 lookup
  lift.synthetic_sling_capacity — hitch factors, ply, material
  lift.spreader_beam_check      — SHS / CHS / WF section parsing, utilisation
  lift.padeye_check             — tension, bearing, shear-out failure modes
  lift.tip_over_two_crane       — load share, UNSTABLE, WLL_EXCEEDED
  lift.crane_radius_interpolate — interpolation, extrapolation warnings

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas are verified algebraically against rigging-handbook hand-calculations.

References
----------
ASME B30.9-2018  — Slings
Rigging Engineering Basics, J.D. Isbester, 2013

Author: imranparuk
"""
from __future__ import annotations

import math

import pytest

from kerf_cad_core.rigging.lift import (
    sling_tension,
    multi_leg_share,
    cg_pick_loads,
    sling_wll_derate,
    wire_rope_capacity,
    chain_capacity,
    synthetic_sling_capacity,
    spreader_beam_check,
    padeye_check,
    tip_over_two_crane,
    crane_radius_interpolate,
)

_G = 9.80665
REL = 1e-6


# ===========================================================================
# 1. sling_tension
# ===========================================================================

class TestSlingTension:

    def test_vertical_sling_no_amplification(self):
        """At 90° (vertical) the LAF = 1/sin 90° = 1.0 exactly."""
        res = sling_tension(1000.0, 90.0)
        assert res["ok"] is True
        assert abs(res["load_angle_factor"] - 1.0) < REL
        # tension per 1-leg = weight
        expected_kN = 1000.0 * _G / 1000.0
        assert abs(res["tension_per_leg_kN"] - expected_kN) < REL

    def test_45_deg_laf_is_sqrt2(self):
        """At 45° the LAF = 1/sin 45° = √2."""
        res = sling_tension(1000.0, 45.0)
        assert res["ok"] is True
        assert abs(res["load_angle_factor"] - math.sqrt(2)) < 1e-9

    def test_30_deg_laf_is_2(self):
        """At 30° the LAF = 1/sin 30° = 2.0."""
        res = sling_tension(1000.0, 30.0)
        assert res["ok"] is True
        assert abs(res["load_angle_factor"] - 2.0) < 1e-9

    def test_2_legs_halves_tension(self):
        """With n_legs=2 the tension per leg is halved vs n_legs=1."""
        r1 = sling_tension(1000.0, 60.0, n_legs=1)
        r2 = sling_tension(1000.0, 60.0, n_legs=2)
        assert abs(r2["tension_per_leg_kN"] - r1["tension_per_leg_kN"] / 2.0) < 1e-9

    def test_warning_issued_below_30_deg(self):
        """Angle < 30° must include SLING_ANGLE_TOO_SHALLOW in warnings."""
        res = sling_tension(5000.0, 20.0)
        assert res["ok"] is True
        assert any("SLING_ANGLE_TOO_SHALLOW" in w for w in res["warnings"])

    def test_required_wll_equals_tension_over_df(self):
        """required_wll_kg = tension_per_leg_kg / design_factor."""
        df = 5.0
        res = sling_tension(2000.0, 45.0, design_factor=df)
        expected = res["tension_per_leg_kg"] / df
        assert abs(res["required_wll_kg"] - expected) < REL

    def test_zero_angle_returns_error(self):
        """angle_deg = 0 is degenerate (infinite tension) → error."""
        res = sling_tension(1000.0, 0.0)
        assert res["ok"] is False

    def test_negative_load_returns_error(self):
        res = sling_tension(-100.0, 45.0)
        assert res["ok"] is False

    def test_n_legs_out_of_range_returns_error(self):
        res = sling_tension(1000.0, 45.0, n_legs=0)
        assert res["ok"] is False

    def test_hand_calc_60_deg_2_legs(self):
        """
        Hand-calc: load=10000 kg, angle=60°, n_legs=2
          W = 10000 × 9.80665 / 1000 = 98.0665 kN
          LAF = 1/sin(60°) = 1/0.8660 = 1.1547
          T_per_leg = (98.0665 / 2) × 1.1547 = 56.588... kN
        """
        W = 10000.0
        theta = 60.0
        n = 2
        res = sling_tension(W, theta, n_legs=n)
        W_kN = W * _G / 1000.0
        laf = 1.0 / math.sin(math.radians(theta))
        expected = W_kN / n * laf
        assert abs(res["tension_per_leg_kN"] - expected) / expected < 1e-9


# ===========================================================================
# 2. multi_leg_share
# ===========================================================================

class TestMultiLegShare:

    def test_2_equal_legs_share_50_50(self):
        """Two equal-length slings: 50/50 share."""
        res = multi_leg_share(2000.0, [4.0, 4.0])
        assert res["ok"] is True
        loads = res["leg_loads_kg"]
        assert len(loads) == 2
        assert abs(loads[0] - loads[1]) < 1e-9
        assert abs(loads[0] - 1000.0) < 1e-9

    def test_2_unequal_legs_shorter_heavier(self):
        """Shorter sling carries more load (inverse-proportion)."""
        res = multi_leg_share(1000.0, [2.0, 4.0])
        assert res["ok"] is True
        # inv: 1/2=0.5, 1/4=0.25 → shares 2/3, 1/3
        loads = res["leg_loads_kg"]
        assert abs(loads[0] / loads[1] - 2.0) < 1e-9

    def test_3_equal_legs_share_equally(self):
        """Three equal slings → 1/3 each."""
        total = 3000.0
        res = multi_leg_share(total, [5.0, 5.0, 5.0])
        assert res["ok"] is True
        for load in res["leg_loads_kg"]:
            assert abs(load - total / 3.0) < 1e-9

    def test_4_leg_flexible_slack_warning(self):
        """4-leg flexible: longest leg flagged as slack, FLEXIBLE_4LEG warning."""
        res = multi_leg_share(4000.0, [3.0, 3.0, 3.0, 6.0])
        assert res["ok"] is True
        assert any("FLEXIBLE_4LEG" in w for w in res["warnings"])
        # The slack leg (index 3, longest = 6.0 m) should carry zero load
        assert abs(res["leg_loads_kg"][3]) < 1e-9

    def test_4_leg_rigid_equal_share(self):
        """Rigid mode: all 4 legs carry equal load regardless of lengths."""
        res = multi_leg_share(4000.0, [1.0, 2.0, 3.0, 4.0], mode="rigid")
        assert res["ok"] is True
        for load in res["leg_loads_kg"]:
            assert abs(load - 1000.0) < 1e-9

    def test_total_load_sums_correctly(self):
        """Sum of leg loads must equal total load."""
        total = 5000.0
        res = multi_leg_share(total, [2.5, 3.0, 4.5])
        assert res["ok"] is True
        assert abs(sum(res["leg_loads_kg"]) - total) < 1e-6

    def test_invalid_n_legs_returns_error(self):
        res = multi_leg_share(1000.0, [1.0, 2.0, 3.0, 4.0, 5.0])
        assert res["ok"] is False

    def test_required_wll_is_max_leg_over_df(self):
        """required_wll_kg = max(leg_loads_kg) / design_factor."""
        df = 4.0
        res = multi_leg_share(3000.0, [2.0, 4.0], design_factor=df)
        assert res["ok"] is True
        expected = max(res["leg_loads_kg"]) / df
        assert abs(res["required_wll_kg"] - expected) < 1e-9


# ===========================================================================
# 3. cg_pick_loads
# ===========================================================================

class TestCgPickLoads:

    def test_2_point_centred_cg_equal_share(self):
        """CG at midpoint of 2 pick points → 50/50 share."""
        res = cg_pick_loads(2000.0, cg_x=5.0, cg_y=0.0, pick_points=[(0.0, 0.0), (10.0, 0.0)])
        assert res["ok"] is True
        assert abs(res["pick_loads_kg"][0] - 1000.0) < 1e-9
        assert abs(res["pick_loads_kg"][1] - 1000.0) < 1e-9

    def test_2_point_cg_at_one_end(self):
        """CG directly above pick point A → all load on A."""
        res = cg_pick_loads(2000.0, cg_x=0.0, cg_y=0.0, pick_points=[(0.0, 0.0), (10.0, 0.0)])
        assert res["ok"] is True
        assert abs(res["pick_loads_kg"][0] - 2000.0) < 1e-9
        assert abs(res["pick_loads_kg"][1]) < 1e-9

    def test_3_point_centroid_equal_share(self):
        """CG at centroid of equilateral triangle → equal 1/3 each."""
        # Equilateral triangle with centroid at (1, 1/√3)
        pts = [(0.0, 0.0), (2.0, 0.0), (1.0, math.sqrt(3))]
        cx = sum(p[0] for p in pts) / 3.0
        cy = sum(p[1] for p in pts) / 3.0
        res = cg_pick_loads(3000.0, cg_x=cx, cg_y=cy, pick_points=pts)
        assert res["ok"] is True
        total = 3000.0
        for load in res["pick_loads_kg"]:
            assert abs(load - total / 3.0) < 1e-6

    def test_cg_outside_polygon_unstable_warning(self):
        """CG outside the pick polygon → UNSTABLE warning, cg_inside=False."""
        pts = [(0.0, 0.0), (2.0, 0.0), (1.0, 2.0)]
        res = cg_pick_loads(1000.0, cg_x=5.0, cg_y=5.0, pick_points=pts)
        assert res["ok"] is True
        assert res["cg_inside"] is False
        assert any("UNSTABLE" in w for w in res["warnings"])

    def test_4_point_symmetric_centred(self):
        """CG at centre of unit square → 25% each corner."""
        pts = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        res = cg_pick_loads(4000.0, cg_x=0.5, cg_y=0.5, pick_points=pts)
        assert res["ok"] is True
        for load in res["pick_loads_kg"]:
            assert abs(load - 1000.0) < 1e-6

    def test_total_load_conserved(self):
        """Sum of pick_loads_kg always equals total load."""
        pts = [(0.0, 0.0), (3.0, 0.0), (3.0, 4.0), (0.0, 4.0)]
        res = cg_pick_loads(7500.0, cg_x=1.5, cg_y=2.0, pick_points=pts)
        assert res["ok"] is True
        assert abs(sum(res["pick_loads_kg"]) - 7500.0) < 1e-6

    def test_too_few_points_returns_error(self):
        res = cg_pick_loads(1000.0, cg_x=0.0, cg_y=0.0, pick_points=[(0.0, 0.0)])
        assert res["ok"] is False

    def test_too_many_points_returns_error(self):
        pts = [(float(i), 0.0) for i in range(5)]
        res = cg_pick_loads(1000.0, cg_x=2.0, cg_y=0.0, pick_points=pts)
        assert res["ok"] is False


# ===========================================================================
# 4. sling_wll_derate
# ===========================================================================

class TestSlingWllDerate:

    def test_zero_angle_no_derate(self):
        """0° (vertical) → derate factor = 1.0."""
        res = sling_wll_derate(5000.0, 0.0)
        assert res["ok"] is True
        assert abs(res["derate_factor"] - 1.0) < REL
        assert abs(res["derated_wll_kg"] - 5000.0) < REL

    def test_30_deg_from_vertical_sling(self):
        """30° from vertical → factor ≈ 0.866 (sin 60°)."""
        res = sling_wll_derate(1000.0, 30.0, hardware_type="sling")
        assert res["ok"] is True
        assert abs(res["derate_factor"] - 0.866) < 1e-3

    def test_45_deg_sling_factor(self):
        """45° from vertical → factor ≈ 0.707 (sin 45°)."""
        res = sling_wll_derate(2000.0, 45.0)
        assert res["ok"] is True
        assert abs(res["derate_factor"] - 0.707) < 1e-3

    def test_eyebolt_on_axis_no_derate(self):
        """Eyebolt at 0° → no derate."""
        res = sling_wll_derate(500.0, 0.0, hardware_type="eyebolt")
        assert res["ok"] is True
        assert abs(res["derate_factor"] - 1.0) < REL

    def test_eyebolt_15_deg_50_percent(self):
        """Eyebolt at 15° from axis → 50% derate per ASME B30.26."""
        res = sling_wll_derate(1000.0, 15.0, hardware_type="eyebolt")
        assert res["ok"] is True
        assert abs(res["derate_factor"] - 0.5) < REL
        assert abs(res["derated_wll_kg"] - 500.0) < REL

    def test_multi_leg_multiplies_wll(self):
        """n_legs=4 multiplies derated WLL by 4."""
        res_1 = sling_wll_derate(2000.0, 30.0, n_legs=1)
        res_4 = sling_wll_derate(2000.0, 30.0, n_legs=4)
        assert abs(res_4["total_wll_kg"] - 4.0 * res_1["derated_wll_kg"]) < 1e-6

    def test_invalid_hardware_type_error(self):
        res = sling_wll_derate(1000.0, 30.0, hardware_type="block")
        assert res["ok"] is False

    def test_sling_angle_too_shallow_warning(self):
        """Sling from-vertical > 60° triggers SLING_ANGLE_TOO_SHALLOW warning."""
        res = sling_wll_derate(1000.0, 70.0, hardware_type="sling")
        assert res["ok"] is True
        assert any("SLING_ANGLE_TOO_SHALLOW" in w for w in res["warnings"])


# ===========================================================================
# 5. wire_rope_capacity
# ===========================================================================

class TestWireRopeCapacity:

    def test_16mm_1570_wll(self):
        """16 mm 6×19 IWRC 1570 MPa: MBF=153 kN → WLL = 153/5 = 30.6 kN."""
        res = wire_rope_capacity(16.0, "6x19_iwrc_1570")
        assert res["ok"] is True
        assert abs(res["mbf_kN"] - 153.0) < 1e-6
        assert abs(res["wll_kN"] - 153.0 / 5.0) < 1e-6

    def test_design_factor_applied(self):
        """Custom design factor must scale WLL correctly."""
        df = 8.0
        res = wire_rope_capacity(20.0, "6x19_iwrc_1570", design_factor=df)
        assert res["ok"] is True
        assert abs(res["wll_kN"] - res["mbf_kN"] / df) < 1e-9

    def test_wll_kg_consistent(self):
        """wll_kg = wll_kN × 1000 / g."""
        res = wire_rope_capacity(24.0, "6x19_iwrc_1770")
        assert res["ok"] is True
        expected_kg = res["wll_kN"] * 1000.0 / _G
        assert abs(res["wll_kg"] - expected_kg) < 1e-6

    def test_unknown_diameter_returns_error(self):
        res = wire_rope_capacity(99.0)
        assert res["ok"] is False
        assert "reason" in res

    def test_unknown_grade_returns_error(self):
        res = wire_rope_capacity(16.0, "6x7_fc_old")
        assert res["ok"] is False


# ===========================================================================
# 6. chain_capacity
# ===========================================================================

class TestChainCapacity:

    def test_13mm_grade80_wll(self):
        """13 mm Grade 80 chain: catalogue WLL = 5.30 t."""
        res = chain_capacity(13.0, "grade_80")
        assert res["ok"] is True
        assert abs(res["wll_t"] - 5.30) < 1e-6

    def test_grade100_higher_than_grade80(self):
        """Grade 100 must have higher WLL than Grade 80 for same size."""
        r80 = chain_capacity(10.0, "grade_80")
        r100 = chain_capacity(10.0, "grade_100")
        assert r80["ok"] and r100["ok"]
        assert r100["wll_t"] > r80["wll_t"]

    def test_wll_kg_consistent(self):
        """wll_kg = wll_t × 1000."""
        res = chain_capacity(16.0, "grade_100")
        assert res["ok"] is True
        assert abs(res["wll_kg"] - res["wll_t"] * 1000.0) < 1e-6

    def test_unknown_size_returns_error(self):
        res = chain_capacity(15.0)
        assert res["ok"] is False

    def test_effective_wll_applies_design_factor(self):
        df = 2.0
        res = chain_capacity(8.0, "grade_80", design_factor=df)
        assert res["ok"] is True
        assert abs(res["effective_wll_kg"] - res["wll_kg"] / df) < 1e-9


# ===========================================================================
# 7. synthetic_sling_capacity
# ===========================================================================

class TestSyntheticSlingCapacity:

    def test_polyester_100mm_1ply_vertical(self):
        """100 mm 1-ply polyester vertical: base WLL = 4000 kg."""
        res = synthetic_sling_capacity(100.0, 1)
        assert res["ok"] is True
        assert abs(res["base_wll_kg"] - 4000.0) < 1e-6

    def test_basket_hitch_doubles_wll(self):
        """Basket hitch multiplies WLL by 2.0."""
        rv = synthetic_sling_capacity(50.0, 1, hitch="vertical")
        rb = synthetic_sling_capacity(50.0, 1, hitch="basket")
        assert abs(rb["adjusted_wll_kg"] / rv["adjusted_wll_kg"] - 2.0) < 1e-9

    def test_choker_hitch_reduces_wll(self):
        """Choker hitch reduces WLL to 80% of vertical."""
        rv = synthetic_sling_capacity(75.0, 2)
        rc = synthetic_sling_capacity(75.0, 2, hitch="choker")
        assert abs(rc["adjusted_wll_kg"] / rv["adjusted_wll_kg"] - 0.80) < 1e-9

    def test_2_ply_doubles_base_wll(self):
        """2-ply has twice the WLL of 1-ply for same width and hitch."""
        r1 = synthetic_sling_capacity(100.0, 1)
        r2 = synthetic_sling_capacity(100.0, 2)
        assert abs(r2["base_wll_kg"] / r1["base_wll_kg"] - 2.0) < 1e-9

    def test_invalid_ply_returns_error(self):
        res = synthetic_sling_capacity(100.0, 3)
        assert res["ok"] is False

    def test_effective_wll_applies_design_factor(self):
        df = 7.0
        res = synthetic_sling_capacity(150.0, 1, design_factor=df)
        assert abs(res["effective_wll_kg"] - res["adjusted_wll_kg"] / df) < 1e-9


# ===========================================================================
# 8. spreader_beam_check
# ===========================================================================

class TestSpreaderBeamCheck:

    def test_shs_200x200x10_parses_and_returns_ok(self):
        """tube_square_200x200x10 should parse without error."""
        res = spreader_beam_check(5000.0, 4.0, section="tube_square_200x200x10")
        assert res["ok"] is True
        assert "utilisation" in res

    def test_chs_219x10_parses(self):
        """tube_round_219x10 should parse correctly."""
        res = spreader_beam_check(3000.0, 3.0, section="tube_round_219x10")
        assert res["ok"] is True
        assert res["area_mm2"] > 0
        assert res["I_mm4"] > 0

    def test_wide_flange_parses(self):
        """wide_flange_300x150x8x12 should parse."""
        res = spreader_beam_check(8000.0, 5.0, section="wide_flange_300x150x8x12")
        assert res["ok"] is True
        assert res["S_mm3"] > 0

    def test_bending_moment_formula(self):
        """M = WL/4 for central point load on simple beam."""
        W_kg = 10000.0
        L = 6.0
        res = spreader_beam_check(W_kg, L, section="tube_square_300x300x12")
        assert res["ok"] is True
        W_N = W_kg * _G
        expected_M = W_N * L / 4.0
        assert abs(res["bending_moment_Nm"] - expected_M) / expected_M < 1e-9

    def test_overloaded_beam_triggers_warning(self):
        """A very thin beam under a large load should flag WLL_EXCEEDED."""
        # tube_square_20x20x2 under 100 t is extremely overstressed
        res = spreader_beam_check(100000.0, 5.0, section="tube_square_20x20x2")
        assert res["ok"] is True  # ok=True, but warnings
        assert any("WLL_EXCEEDED" in w for w in res["warnings"]) or res["utilisation"] > 1.0

    def test_invalid_section_returns_error(self):
        res = spreader_beam_check(5000.0, 4.0, section="bogus_section_xyz")
        assert res["ok"] is False

    def test_utilisation_scales_with_load(self):
        """Doubling the load roughly doubles the utilisation."""
        r1 = spreader_beam_check(5000.0, 4.0, section="tube_square_200x200x10")
        r2 = spreader_beam_check(10000.0, 4.0, section="tube_square_200x200x10")
        assert r1["ok"] and r2["ok"]
        # Not exactly 2× due to axial component, but very close
        ratio = r2["utilisation"] / r1["utilisation"]
        assert 1.8 < ratio < 2.2


# ===========================================================================
# 9. padeye_check
# ===========================================================================

class TestPadeyeCheck:

    def test_lightly_loaded_all_pass(self):
        """A well-proportioned padeye under moderate load should pass all checks."""
        res = padeye_check(
            load_kN=50.0,
            plate_thickness_mm=20.0,
            hole_diameter_mm=50.0,
            pin_diameter_mm=45.0,
        )
        assert res["ok"] is True
        assert res["tension_pass"]
        assert res["bearing_pass"]
        assert res["shearout_pass"]

    def test_overloaded_padeye_warning(self):
        """Extremely thin plate under heavy load → WLL_EXCEEDED warning."""
        res = padeye_check(
            load_kN=500.0,
            plate_thickness_mm=5.0,
            hole_diameter_mm=30.0,
            pin_diameter_mm=25.0,
        )
        assert res["ok"] is True
        assert any("WLL_EXCEEDED" in w for w in res["warnings"])

    def test_pin_too_large_returns_error(self):
        res = padeye_check(
            load_kN=10.0,
            plate_thickness_mm=20.0,
            hole_diameter_mm=30.0,
            pin_diameter_mm=35.0,
        )
        assert res["ok"] is False

    def test_bearing_stress_formula(self):
        """Bearing stress = P / (d_pin × t)."""
        P_kN = 100.0
        t = 25.0
        d_pin = 45.0
        d_hole = 50.0
        res = padeye_check(P_kN, t, d_hole, d_pin)
        assert res["ok"] is True
        P_N = P_kN * 1000.0
        expected_bearing = P_N / (d_pin * t)
        assert abs(res["bearing_stress_MPa"] - expected_bearing) < 1e-6

    def test_utilisation_increases_with_load(self):
        """Higher load → higher governing utilisation."""
        r1 = padeye_check(50.0, 20.0, 50.0, 45.0)
        r2 = padeye_check(100.0, 20.0, 50.0, 45.0)
        assert r1["ok"] and r2["ok"]
        assert r2["governing_utilisation"] > r1["governing_utilisation"]

    def test_negative_load_returns_error(self):
        res = padeye_check(-10.0, 20.0, 50.0, 45.0)
        assert res["ok"] is False


# ===========================================================================
# 10. tip_over_two_crane
# ===========================================================================

class TestTipOverTwoCrane:

    def test_cg_at_midpoint_equal_share(self):
        """CG at midpoint of two cranes → equal 50/50 share."""
        res = tip_over_two_crane(
            total_load_kg=10000.0,
            crane_a_capacity_t=10.0,
            crane_b_capacity_t=10.0,
            lift_point_a_x=0.0,
            lift_point_b_x=10.0,
            cg_x=5.0,
        )
        assert res["ok"] is True
        assert abs(res["crane_a_load_kg"] - 5000.0) < 1e-6
        assert abs(res["crane_b_load_kg"] - 5000.0) < 1e-6
        assert res["cg_between_hooks"] is True

    def test_cg_at_crane_a_all_load_on_a(self):
        """CG at Crane A position → all load on A."""
        res = tip_over_two_crane(
            total_load_kg=5000.0,
            crane_a_capacity_t=10.0,
            crane_b_capacity_t=10.0,
            lift_point_a_x=0.0,
            lift_point_b_x=10.0,
            cg_x=0.0,
        )
        assert res["ok"] is True
        assert abs(res["crane_a_load_kg"] - 5000.0) < 1e-6
        assert abs(res["crane_b_load_kg"]) < 1e-6

    def test_cg_outside_hooks_unstable(self):
        """CG outside the two hooks → UNSTABLE warning."""
        res = tip_over_two_crane(
            total_load_kg=5000.0,
            crane_a_capacity_t=10.0,
            crane_b_capacity_t=10.0,
            lift_point_a_x=0.0,
            lift_point_b_x=10.0,
            cg_x=15.0,
        )
        assert res["ok"] is True
        assert res["cg_between_hooks"] is False
        assert any("UNSTABLE" in w for w in res["warnings"])

    def test_overloaded_crane_warning(self):
        """Load exceeding crane capacity → WLL_EXCEEDED warning."""
        # CG at x=1 (close to Crane A at x=0):
        #   R_A = 20000 × (10-1)/10 = 18000 kg  > Crane A cap 5000 kg
        res = tip_over_two_crane(
            total_load_kg=20000.0,
            crane_a_capacity_t=5.0,   # only 5 t capacity
            crane_b_capacity_t=50.0,
            lift_point_a_x=0.0,
            lift_point_b_x=10.0,
            cg_x=1.0,  # CG close to A → most load on A → A overloaded
        )
        assert res["ok"] is True
        assert any("WLL_EXCEEDED" in w for w in res["warnings"])

    def test_coincident_lift_points_returns_error(self):
        res = tip_over_two_crane(
            total_load_kg=5000.0,
            crane_a_capacity_t=10.0,
            crane_b_capacity_t=10.0,
            lift_point_a_x=5.0,
            lift_point_b_x=5.0,
            cg_x=5.0,
        )
        assert res["ok"] is False

    def test_load_conservation(self):
        """crane_a_load + crane_b_load = total_load."""
        res = tip_over_two_crane(
            total_load_kg=12345.0,
            crane_a_capacity_t=20.0,
            crane_b_capacity_t=20.0,
            lift_point_a_x=0.0,
            lift_point_b_x=8.0,
            cg_x=3.0,
        )
        assert res["ok"] is True
        total = res["crane_a_load_kg"] + res["crane_b_load_kg"]
        assert abs(total - 12345.0) < 1e-6


# ===========================================================================
# 11. crane_radius_interpolate
# ===========================================================================

class TestCraneRadiusInterpolate:

    _TABLE = [(5.0, 40.0), (10.0, 25.0), (15.0, 18.0), (20.0, 13.0)]

    def test_exact_table_entry(self):
        """Querying an exact table radius returns that capacity."""
        res = crane_radius_interpolate(10.0, self._TABLE)
        assert res["ok"] is True
        assert abs(res["capacity_t"] - 25.0) < 1e-9

    def test_interpolation_midpoint(self):
        """Midpoint between (10, 25) and (15, 18) → capacity ≈ 21.5 t."""
        res = crane_radius_interpolate(12.5, self._TABLE)
        assert res["ok"] is True
        assert abs(res["capacity_t"] - (25.0 + 18.0) / 2.0) < 1e-9
        assert res["interpolated"] is True

    def test_below_minimum_radius_uses_min(self):
        """Radius < table minimum → minimum-radius capacity, no extrapolation up."""
        res = crane_radius_interpolate(2.0, self._TABLE)
        assert res["ok"] is True
        assert abs(res["capacity_t"] - 40.0) < 1e-9
        assert res["interpolated"] is False

    def test_beyond_maximum_radius_warning(self):
        """Radius > table maximum → max-radius (minimum) capacity + warning."""
        res = crane_radius_interpolate(25.0, self._TABLE)
        assert res["ok"] is True
        assert abs(res["capacity_t"] - 13.0) < 1e-9
        assert any("extrapolat" in w.lower() or "maximum" in w.lower() for w in res["warnings"])

    def test_capacity_kg_consistent(self):
        """capacity_kg = capacity_t × 1000."""
        res = crane_radius_interpolate(7.0, self._TABLE)
        assert res["ok"] is True
        assert abs(res["capacity_kg"] - res["capacity_t"] * 1000.0) < 1e-9

    def test_too_few_table_entries_error(self):
        res = crane_radius_interpolate(5.0, [(10.0, 25.0)])
        assert res["ok"] is False

    def test_decreasing_capacity_with_radius(self):
        """Capacity at larger radius must be less than or equal at smaller radius."""
        r1 = crane_radius_interpolate(8.0, self._TABLE)
        r2 = crane_radius_interpolate(14.0, self._TABLE)
        assert r1["ok"] and r2["ok"]
        assert r2["capacity_t"] <= r1["capacity_t"]

    def test_hand_calc_interpolation(self):
        """
        Hand-calc: between (5, 40) and (10, 25) at radius=7:
          t = (7-5)/(10-5) = 0.4
          capacity = 40 + 0.4 × (25-40) = 40 - 6 = 34 t
        """
        res = crane_radius_interpolate(7.0, self._TABLE)
        assert res["ok"] is True
        assert abs(res["capacity_t"] - 34.0) < 1e-9
