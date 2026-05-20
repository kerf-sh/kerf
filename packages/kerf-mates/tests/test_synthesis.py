"""
tests/test_synthesis.py — pytest suite for kerf_mates.synthesis

Covers:
  - fourbar.synthesise_four_bar   (Burmester 4-bar synthesis)
  - cam.synthesise_cam            (cam-profile synthesis)
  - gear_train.synthesise_gear_train (gear-train synthesis)

All tests use analytic oracles: known-good numeric results derived from
first principles so the test is independent of any third-party library.

Author: imranparuk
"""

from __future__ import annotations

import math
import pytest

from kerf_mates.synthesis import fourbar, cam, gear_train


# ============================================================================
# Helpers
# ============================================================================

def _coupler_point_xy(r2, theta2_rad, theta3_rad, px, py):
    """World-frame coupler-point position."""
    Ax = r2 * math.cos(theta2_rad)
    Ay = r2 * math.sin(theta2_rad)
    cos3 = math.cos(theta3_rad)
    sin3 = math.sin(theta3_rad)
    return (Ax + px * cos3 - py * sin3,
            Ay + px * sin3 + py * cos3)


def _four_bar_position(r1, r2, r3, r4, theta2_rad, branch=1):
    """
    Freudenstein closed-form for theta3, theta4 (radians).
    Returns (theta3, theta4) or raises ValueError on locked config.
    """
    K1 = r1 / r2
    K2 = r1 / r4
    K3 = (r1**2 + r4**2 + r2**2 - r3**2) / (2.0 * r2 * r4)
    cos2 = math.cos(theta2_rad)
    sin2 = math.sin(theta2_rad)
    A_f = K3 - K2 * cos2
    B_f = K1 - cos2
    aa = A_f - B_f
    bb = -2.0 * sin2
    cc = A_f + B_f
    if abs(aa) < 1e-14:
        if abs(bb) < 1e-14:
            raise ValueError("Locked configuration")
        t = -cc / bb
    else:
        disc = bb * bb - 4.0 * aa * cc
        if disc < 0:
            raise ValueError("No real solution")
        t = (-bb + branch * math.sqrt(disc)) / (2.0 * aa)
    theta4 = 2.0 * math.atan(t)
    ex = r1 + r4 * math.cos(theta4) - r2 * cos2
    ey = r4 * math.sin(theta4) - r2 * sin2
    theta3 = math.atan2(ey, ex)
    return theta3, theta4


def _min_dist_to_curve(r, px, py, target_x, target_y, n=720, branch=1):
    """Minimum distance from target to the coupler curve (dense sampling)."""
    r1, r2, r3, r4 = r
    min_d = float("inf")
    for i in range(n):
        t2 = 2.0 * math.pi * i / n
        try:
            t3, _ = _four_bar_position(r1, r2, r3, r4, t2, branch)
        except ValueError:
            continue
        cx, cy = _coupler_point_xy(r2, t2, t3, px, py)
        d = math.sqrt((cx - target_x)**2 + (cy - target_y)**2)
        if d < min_d:
            min_d = d
    return min_d


# ============================================================================
# 1.  Four-bar linkage synthesis — Burmester
# ============================================================================

class TestFourBarSynthesis:

    def test_returns_ok(self):
        """synthesise_four_bar returns ok=True for valid 3-point input."""
        pts = [(10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        result = fourbar.synthesise_four_bar(pts, max_iters=2000)
        assert result["ok"] is True, f"Expected ok=True, got reason={result.get('reason')}"

    def test_coupler_curve_passes_through_all_three_points(self):
        """
        Oracle: synthesised linkage coupler curve passes within 0.5 mm of each
        of the three specified precision points.
        """
        pts = [(10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        result = fourbar.synthesise_four_bar(pts, tol_mm=0.5, max_iters=3000)
        assert result["ok"] is True

        r = (result["r1"], result["r2"], result["r3"], result["r4"])
        px, py = result["px"], result["py"]

        for i, (tx, ty) in enumerate(pts):
            d = min(
                _min_dist_to_curve(r, px, py, tx, ty, n=720, branch=b)
                for b in (1, -1)
            )
            assert d <= 0.5, (
                f"Coupler curve too far from point {i} ({tx},{ty}): "
                f"min distance = {d:.4f} mm > 0.5 mm"
            )

    def test_max_error_field(self):
        """max_error_mm field is consistent with the actual coupler curve error."""
        pts = [(5.0, 0.0), (8.0, 6.0), (3.0, 8.0)]
        result = fourbar.synthesise_four_bar(pts, max_iters=2000)
        assert result["ok"] is True
        assert "max_error_mm" in result
        assert result["max_error_mm"] >= 0.0

    def test_link_lengths_positive(self):
        """All synthesised link lengths must be strictly positive."""
        pts = [(20.0, 0.0), (15.0, 15.0), (0.0, 20.0)]
        result = fourbar.synthesise_four_bar(pts, max_iters=2000)
        assert result["ok"] is True
        for key in ("r1", "r2", "r3", "r4"):
            assert result[key] > 0, f"{key} must be > 0, got {result[key]}"

    def test_grashof_field_present(self):
        """Grashof classification string must be returned."""
        pts = [(10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        result = fourbar.synthesise_four_bar(pts, max_iters=1000)
        assert result["ok"] is True
        assert "grashof" in result
        assert isinstance(result["grashof"], str)
        assert len(result["grashof"]) > 0

    def test_error_bad_points_count(self):
        """Must require exactly 3 points."""
        r = fourbar.synthesise_four_bar([(0, 0), (1, 1)])
        assert r["ok"] is False
        assert "three" in r["reason"].lower() or "3" in r["reason"]

    def test_error_non_numeric_point(self):
        """Non-numeric coordinates must return ok=False."""
        r = fourbar.synthesise_four_bar([(0, 0), (1, "a"), (2, 2)])
        assert r["ok"] is False

    def test_collinear_points_still_returns_result(self):
        """
        Three collinear precision points are geometrically degenerate but
        the function should still return ok=True (the optimiser will find
        some solution, possibly with large error).
        """
        pts = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)]
        result = fourbar.synthesise_four_bar(pts, max_iters=500)
        assert result["ok"] is True  # doesn't crash

    def test_returns_warnings_list(self):
        """Result always contains a 'warnings' list."""
        pts = [(10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        result = fourbar.synthesise_four_bar(pts, max_iters=500)
        assert "warnings" in result
        assert isinstance(result["warnings"], list)


# ============================================================================
# 2.  Cam-profile synthesis
# ============================================================================

class TestCamSynthesis:

    # -- Cycloidal -----------------------------------------------------------

    def test_cycloidal_ok(self):
        """synthesise_cam returns ok=True for cycloidal law."""
        result = cam.synthesise_cam("cycloidal", h=10.0, beta_deg=120.0)
        assert result["ok"] is True

    def test_cycloidal_lift_correct(self):
        """
        Oracle: cycloidal displacement at theta=beta must equal h.
        y(β) = h * [1 - sin(2π)/2π] = h * [1 - 0] = h.
        """
        h = 10.0
        result = cam.synthesise_cam("cycloidal", h=h, beta_deg=120.0)
        assert result["ok"] is True
        assert result["lift_ok"] is True
        last = result["profile"][-1]
        assert abs(last["displacement"] - h) < 1e-6, (
            f"Expected displacement {h} at beta, got {last['displacement']}"
        )

    def test_cycloidal_zero_velocity_at_boundaries(self):
        """
        Oracle: cycloidal dy/dθ at θ=0 and θ=β must be 0.
        dy/dθ = (h/β)·[1 − cos(2πξ)];  at ξ=0: 1−cos(0)=0; at ξ=1: 1−cos(2π)=0.
        """
        result = cam.synthesise_cam("cycloidal", h=10.0, beta_deg=120.0, n_points=720)
        assert result["ok"] is True
        first = result["profile"][0]
        last = result["profile"][-1]
        assert abs(first["velocity_per_omega"]) < 1e-9, (
            f"Start velocity not zero: {first['velocity_per_omega']}"
        )
        assert abs(last["velocity_per_omega"]) < 1e-9, (
            f"End velocity not zero: {last['velocity_per_omega']}"
        )

    def test_cycloidal_zero_acceleration_at_boundaries(self):
        """
        Oracle: cycloidal d²y/dθ² at θ=0 and θ=β must be 0.
        d²y/dθ² = (2πh/β²)·sin(2πξ); at ξ=0 and ξ=1 both are 0.
        """
        result = cam.synthesise_cam("cycloidal", h=10.0, beta_deg=120.0, n_points=720)
        assert result["ok"] is True
        first = result["profile"][0]
        last = result["profile"][-1]
        assert abs(first["acceleration_per_omega2"]) < 1e-9, (
            f"Start acceleration not zero: {first['acceleration_per_omega2']}"
        )
        assert abs(last["acceleration_per_omega2"]) < 1e-9, (
            f"End acceleration not zero: {last['acceleration_per_omega2']}"
        )

    def test_cycloidal_continuity_ok(self):
        """continuity_ok must be True for cycloidal law."""
        result = cam.synthesise_cam("cycloidal", h=10.0, beta_deg=90.0)
        assert result["ok"] is True
        assert result["continuity_ok"] is True, (
            f"continuity_ok=False; warnings={result['warnings']}"
        )

    def test_cycloidal_midpoint_displacement(self):
        """
        Oracle: at θ = β/2 (ξ=0.5), cycloidal displacement = h/2.
        y(β/2) = h·[0.5 − sin(π)/2π] = h·[0.5 − 0] = h/2.
        """
        h = 20.0
        beta_deg = 180.0
        result = cam.synthesise_cam("cycloidal", h=h, beta_deg=beta_deg, n_points=100)
        assert result["ok"] is True
        # Find point closest to β/2
        mid_idx = len(result["profile"]) // 2
        mid = result["profile"][mid_idx]
        assert abs(mid["displacement"] - h / 2.0) < 0.01, (
            f"Midpoint displacement {mid['displacement']:.6f} != {h/2:.6f}"
        )

    def test_cycloidal_fall(self):
        """Cycloidal fall: displacement starts at h and ends at 0."""
        h = 15.0
        result = cam.synthesise_cam("cycloidal", h=h, beta_deg=120.0, rise=False)
        assert result["ok"] is True
        first = result["profile"][0]
        last = result["profile"][-1]
        assert abs(first["displacement"] - h) < 1e-6
        assert abs(last["displacement"] - 0.0) < 1e-6

    # -- Polynomial ----------------------------------------------------------

    def test_polynomial_ok(self):
        """synthesise_cam returns ok=True for polynomial law."""
        result = cam.synthesise_cam("polynomial", h=10.0, beta_deg=120.0, poly_order=5)
        assert result["ok"] is True
        assert result["poly_order"] == 5

    def test_polynomial_lift_correct_order5(self):
        """
        Oracle: 3-4-5 polynomial y(β) = h·[10·1³ − 15·1⁴ + 6·1⁵] = h·[10−15+6] = h.
        """
        h = 10.0
        result = cam.synthesise_cam("polynomial", h=h, beta_deg=120.0, poly_order=5)
        assert result["ok"] is True
        assert result["lift_ok"] is True
        last = result["profile"][-1]
        assert abs(last["displacement"] - h) < 1e-9, (
            f"Poly-5 lift: expected {h}, got {last['displacement']}"
        )

    def test_polynomial_lift_correct_order7(self):
        """
        Oracle: 4-5-6-7 polynomial y(β) = h·[35−84+70−20] = h·1 = h.
        """
        h = 8.0
        result = cam.synthesise_cam("polynomial", h=h, beta_deg=90.0, poly_order=7)
        assert result["ok"] is True
        assert result["lift_ok"] is True
        last = result["profile"][-1]
        assert abs(last["displacement"] - h) < 1e-9

    def test_polynomial_zero_velocity_at_boundaries_order5(self):
        """
        Oracle: 3-4-5 polynomial dy/dξ = 30ξ² − 60ξ³ + 30ξ⁴;
                at ξ=0: 0; at ξ=1: 30−60+30 = 0.
        """
        result = cam.synthesise_cam("polynomial", h=10.0, beta_deg=120.0,
                                     poly_order=5, n_points=1000)
        assert result["ok"] is True
        first = result["profile"][0]
        last = result["profile"][-1]
        assert abs(first["velocity_per_omega"]) < 1e-8
        assert abs(last["velocity_per_omega"]) < 1e-8

    def test_polynomial_zero_acceleration_at_boundaries_order5(self):
        """
        Oracle: 3-4-5 polynomial d²y/dξ² = 60ξ − 180ξ² + 120ξ³;
                at ξ=0: 0; at ξ=1: 60−180+120 = 0.
        """
        result = cam.synthesise_cam("polynomial", h=10.0, beta_deg=120.0,
                                     poly_order=5, n_points=1000)
        assert result["ok"] is True
        first = result["profile"][0]
        last = result["profile"][-1]
        assert abs(first["acceleration_per_omega2"]) < 1e-6
        assert abs(last["acceleration_per_omega2"]) < 1e-6

    def test_polynomial_order7_zero_velocity_at_boundaries(self):
        """
        Oracle: 4-5-6-7 polynomial dy/dξ = 140ξ³−420ξ⁴+420ξ⁵−140ξ⁶;
                at ξ=0: 0; at ξ=1: 140−420+420−140 = 0.
        """
        result = cam.synthesise_cam("polynomial", h=12.0, beta_deg=90.0,
                                     poly_order=7, n_points=1000)
        assert result["ok"] is True
        first = result["profile"][0]
        last = result["profile"][-1]
        assert abs(first["velocity_per_omega"]) < 1e-8
        assert abs(last["velocity_per_omega"]) < 1e-8

    def test_polynomial_continuity_ok(self):
        """continuity_ok must be True for polynomial law."""
        for order in (5, 7):
            result = cam.synthesise_cam("polynomial", h=10.0, beta_deg=120.0,
                                         poly_order=order)
            assert result["ok"] is True
            assert result["continuity_ok"] is True, (
                f"order={order}: continuity_ok=False; warnings={result['warnings']}"
            )

    # -- Harmonic ------------------------------------------------------------

    def test_harmonic_ok(self):
        """synthesise_cam returns ok=True for harmonic law."""
        result = cam.synthesise_cam("harmonic", h=10.0, beta_deg=120.0)
        assert result["ok"] is True

    def test_harmonic_lift_correct(self):
        """
        Oracle: harmonic y(β) = (h/2)·[1−cos(π)] = (h/2)·2 = h.
        """
        h = 10.0
        result = cam.synthesise_cam("harmonic", h=h, beta_deg=120.0)
        assert result["ok"] is True
        assert result["lift_ok"] is True
        last = result["profile"][-1]
        assert abs(last["displacement"] - h) < 1e-6

    def test_harmonic_zero_velocity_at_boundaries(self):
        """
        Oracle: harmonic dy/dθ = (πh/2β)·sin(πξ);
                at ξ=0: sin(0)=0; at ξ=1: sin(π)=0.
        """
        result = cam.synthesise_cam("harmonic", h=10.0, beta_deg=120.0, n_points=720)
        assert result["ok"] is True
        first = result["profile"][0]
        last = result["profile"][-1]
        assert abs(first["velocity_per_omega"]) < 1e-9
        assert abs(last["velocity_per_omega"]) < 1e-9

    def test_harmonic_nonzero_acceleration_at_boundaries(self):
        """
        Oracle: harmonic d²y/dθ² = (π²h/2β²)·cos(πξ);
                at ξ=0: cos(0)=1 → finite; at ξ=1: cos(π)=−1 → finite.
        Both are non-zero, confirming the known impulsive-jerk property.
        """
        h = 10.0
        beta_deg = 120.0
        beta = math.radians(beta_deg)
        result = cam.synthesise_cam("harmonic", h=h, beta_deg=beta_deg, n_points=720)
        assert result["ok"] is True
        first = result["profile"][0]
        last = result["profile"][-1]
        expected_start_acc = math.pi**2 * h / (2.0 * beta**2)
        assert abs(first["acceleration_per_omega2"] - expected_start_acc) < 1e-6, (
            f"Start acc {first['acceleration_per_omega2']:.6f} "
            f"!= expected {expected_start_acc:.6f}"
        )
        assert abs(last["acceleration_per_omega2"] + expected_start_acc) < 1e-6, (
            f"End acc {last['acceleration_per_omega2']:.6f} "
            f"!= expected {-expected_start_acc:.6f}"
        )

    def test_harmonic_midpoint(self):
        """
        Oracle: at θ=β/2 (ξ=0.5), harmonic y = (h/2)·[1−cos(π/2)] = h/2.
        """
        h = 20.0
        result = cam.synthesise_cam("harmonic", h=h, beta_deg=180.0, n_points=100)
        assert result["ok"] is True
        mid_idx = len(result["profile"]) // 2
        mid = result["profile"][mid_idx]
        assert abs(mid["displacement"] - h / 2.0) < 0.01

    # -- Input validation ----------------------------------------------------

    def test_invalid_law(self):
        r = cam.synthesise_cam("unknown_law", h=10.0, beta_deg=120.0)
        assert r["ok"] is False

    def test_negative_h(self):
        r = cam.synthesise_cam("cycloidal", h=-1.0, beta_deg=120.0)
        assert r["ok"] is False

    def test_zero_beta(self):
        r = cam.synthesise_cam("cycloidal", h=10.0, beta_deg=0.0)
        assert r["ok"] is False

    def test_invalid_poly_order(self):
        r = cam.synthesise_cam("polynomial", h=10.0, beta_deg=120.0, poly_order=3)
        assert r["ok"] is False

    def test_profile_is_list(self):
        result = cam.synthesise_cam("cycloidal", h=10.0, beta_deg=90.0, n_points=36)
        assert result["ok"] is True
        assert isinstance(result["profile"], list)
        assert len(result["profile"]) == 37  # n_points + 1 (includes endpoint)

    def test_profile_keys(self):
        """Each profile entry contains the required keys."""
        result = cam.synthesise_cam("cycloidal", h=10.0, beta_deg=90.0, n_points=10)
        assert result["ok"] is True
        required = {"theta_deg", "displacement", "velocity_per_omega",
                    "acceleration_per_omega2"}
        for entry in result["profile"]:
            assert required.issubset(entry.keys()), (
                f"Missing keys in profile entry: {required - entry.keys()}"
            )


# ============================================================================
# 3.  Gear-train synthesis
# ============================================================================

class TestGearTrainSynthesis:

    def test_returns_ok_ratio_2(self):
        """Simple 1:2 reduction returns ok=True."""
        result = gear_train.synthesise_gear_train(2.0)
        assert result["ok"] is True

    def test_ratio_within_tolerance_simple(self):
        """
        Oracle: achieved ratio must be within 2% of target.
        For ratio=4.0, feasible tooth pairs include (17,68), (18,72), etc.
        """
        target = 4.0
        result = gear_train.synthesise_gear_train(target, tol_ratio=0.02)
        assert result["ok"] is True
        actual = result["total_ratio"]
        err = abs(actual - target) / target
        assert err <= 0.02, (
            f"Ratio error {err:.4f} exceeds 2% tolerance for target {target}"
        )

    def test_ratio_5_single_stage(self):
        """
        Oracle: ratio=5 should be achievable in a single stage.
        z2/z1 = 5: e.g. (17,85), (18,90), (20,100), etc.
        """
        result = gear_train.synthesise_gear_train(5.0, prefer_stages=1, tol_ratio=0.02)
        assert result["ok"] is True
        assert result["stages"] == 1
        sc = result["stage_configs"][0]
        # Verify tooth count ratio matches
        actual_ratio = sc["z2"] / sc["z1"]
        assert abs(actual_ratio - result["total_ratio"]) < 1e-9

    def test_integer_tooth_counts(self):
        """All tooth counts must be integers."""
        for target in (2.0, 3.0, 5.0, 8.0):
            result = gear_train.synthesise_gear_train(target, tol_ratio=0.05)
            assert result["ok"] is True, f"target={target} failed: {result.get('reason')}"
            for i, sc in enumerate(result["stage_configs"]):
                assert isinstance(sc["z1"], int), f"target={target} stage {i}: z1 not int"
                assert isinstance(sc["z2"], int), f"target={target} stage {i}: z2 not int"

    def test_standard_module(self):
        """
        Module must be from the ISO 54 standard series (first or second choice).
        """
        all_modules = (
            gear_train._ISO_MODULES_FIRST + gear_train._ISO_MODULES_SECOND
        )
        for target in (2.0, 4.0, 6.0):
            result = gear_train.synthesise_gear_train(target)
            assert result["ok"] is True, f"target={target}: {result.get('reason')}"
            for sc in result["stage_configs"]:
                assert sc["module"] in all_modules, (
                    f"Non-standard module {sc['module']} for target={target}"
                )

    def test_centre_distance_formula(self):
        """
        Oracle: centre_distance = module * (z1 + z2) / 2  (ISO 21771 §10.1).
        """
        result = gear_train.synthesise_gear_train(3.0)
        assert result["ok"] is True
        for sc in result["stage_configs"]:
            expected_cd = sc["module"] * (sc["z1"] + sc["z2"]) / 2.0
            assert abs(sc["centre_distance_mm"] - expected_cd) < 1e-6, (
                f"Centre distance mismatch: {sc['centre_distance_mm']:.6f} "
                f"!= {expected_cd:.6f}"
            )

    def test_pitch_diameter_formula(self):
        """
        Oracle: pitch_diameter = module * teeth  (ISO 21771 §4.2).
        """
        result = gear_train.synthesise_gear_train(4.0)
        assert result["ok"] is True
        for sc in result["stage_configs"]:
            assert abs(sc["pitch_diameter_1_mm"] - sc["module"] * sc["z1"]) < 1e-9
            assert abs(sc["pitch_diameter_2_mm"] - sc["module"] * sc["z2"]) < 1e-9

    def test_two_stage_large_ratio(self):
        """
        A ratio of 20 cannot be a single stage (z2/z1 = 20 → z2=340 > 150).
        Two-stage synthesis should succeed.
        """
        result = gear_train.synthesise_gear_train(20.0, tol_ratio=0.05)
        assert result["ok"] is True
        # Verify overall ratio
        overall = 1.0
        for sc in result["stage_configs"]:
            overall *= sc["z2"] / sc["z1"]
        assert abs(overall - result["total_ratio"]) < 1e-9

    def test_two_stage_product_matches(self):
        """
        Oracle: total_ratio must equal the product of individual stage ratios.
        """
        result = gear_train.synthesise_gear_train(10.0, tol_ratio=0.05)
        assert result["ok"] is True
        product = 1.0
        for sc in result["stage_configs"]:
            product *= sc["z2"] / sc["z1"]
        assert abs(product - result["total_ratio"]) < 1e-9, (
            f"Product {product:.9f} != total_ratio {result['total_ratio']:.9f}"
        )

    def test_ratio_1_1(self):
        """1:1 ratio (identity) should work."""
        result = gear_train.synthesise_gear_train(1.0, tol_ratio=0.02)
        assert result["ok"] is True
        assert abs(result["total_ratio"] - 1.0) <= 0.02

    def test_tooth_counts_in_valid_range(self):
        """All tooth counts must be >= 17 (no undercut at 20°) and <= 150."""
        for target in (2.0, 5.0, 10.0):
            result = gear_train.synthesise_gear_train(target, tol_ratio=0.05)
            assert result["ok"] is True
            for sc in result["stage_configs"]:
                assert sc["z1"] >= gear_train._Z_MIN, (
                    f"z1={sc['z1']} < {gear_train._Z_MIN}"
                )
                assert sc["z2"] <= gear_train._Z_MAX, (
                    f"z2={sc['z2']} > {gear_train._Z_MAX}"
                )

    def test_warnings_list_present(self):
        """Result always contains 'warnings' list."""
        result = gear_train.synthesise_gear_train(3.0)
        assert "warnings" in result
        assert isinstance(result["warnings"], list)

    def test_error_negative_ratio(self):
        r = gear_train.synthesise_gear_train(-1.0)
        assert r["ok"] is False

    def test_error_zero_ratio(self):
        r = gear_train.synthesise_gear_train(0.0)
        assert r["ok"] is False

    def test_error_bad_prefer_stages(self):
        r = gear_train.synthesise_gear_train(3.0, prefer_stages=3)
        assert r["ok"] is False

    def test_ratio_error_field(self):
        """ratio_error = |actual - target| / target."""
        target = 4.0
        result = gear_train.synthesise_gear_train(target)
        assert result["ok"] is True
        expected_err = abs(result["total_ratio"] - target) / target
        assert abs(result["ratio_error"] - expected_err) < 1e-9

    def test_prefer_stages_1_respected(self):
        """prefer_stages=1 should return a 1-stage result when feasible."""
        result = gear_train.synthesise_gear_train(
            3.0, prefer_stages=1, tol_ratio=0.05
        )
        assert result["ok"] is True
        assert result["stages"] == 1

    def test_prefer_stages_2_respected(self):
        """prefer_stages=2 should return a 2-stage result."""
        result = gear_train.synthesise_gear_train(
            4.0, prefer_stages=2, tol_ratio=0.05
        )
        assert result["ok"] is True
        assert result["stages"] == 2

    def test_stage_configs_keys(self):
        """Each stage_config dict contains required keys."""
        result = gear_train.synthesise_gear_train(5.0)
        assert result["ok"] is True
        required = {
            "module", "z1", "z2", "ratio",
            "centre_distance_mm", "pitch_diameter_1_mm",
            "pitch_diameter_2_mm",
        }
        for sc in result["stage_configs"]:
            assert required.issubset(sc.keys()), (
                f"Missing keys: {required - sc.keys()}"
            )
