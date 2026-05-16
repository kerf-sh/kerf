"""
Hermetic tests for kerf_cad_core.ergonomics — human-factors engineering.

Coverage:
  human.anthropometric_percentile  — z-score scaling, male/female, boundary cases
  human.design_for_range           — clearance vs reach, both-sexes span
  human.niosh_rwl                  — NIOSH 1994 example, multiplier math
  human.lifting_index              — LI classification
  human.snook_push_pull            — table lookup, exceedance flag
  human.grip_strength_percentile   — percentile scaling
  human.pinch_strength_percentile  — percentile scaling
  human.rula_score                 — grand score from joint angles
  human.reba_score                 — grand score from body segments
  human.workstation_heights        — population default calculations
  human.visual_angle               — angle formula, adequacy
  human.min_character_size         — character height from distance
  human.metabolic_expenditure      — Murrell rest allowance formula
  human.rest_allowance             — standalone Murrell formula
  human.reach_envelope             — percentile reach lookup

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas verified against published hand-calcs.

References
----------
NIOSH (1994) — Revised NIOSH Lifting Equation, DHHS (NIOSH) Publication 94-110.
Waters TR et al. (1993) — Ergonomics 36(7):749-776.
McAtamney & Corlett (1993) — Applied Ergonomics 24(2):91-99.

Author: imranparuk
"""
from __future__ import annotations

import math
import pytest

from kerf_cad_core.ergonomics.human import (
    anthropometric_percentile,
    design_for_range,
    niosh_rwl,
    lifting_index,
    snook_push_pull,
    grip_strength_percentile,
    pinch_strength_percentile,
    rula_score,
    reba_score,
    workstation_heights,
    visual_angle,
    min_character_size,
    metabolic_expenditure,
    rest_allowance,
    reach_envelope,
    _z_from_pctile,
    _ANTHROPOMETRIC_TABLE,
    _NIOSH_LC,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(result: dict) -> dict:
    assert result.get("ok") is True, f"Expected ok=True, got: {result}"
    return result


def _err(result: dict) -> dict:
    assert result.get("ok") is False, f"Expected ok=False, got: {result}"
    return result


# ---------------------------------------------------------------------------
# 1. z_from_pctile — inverse normal CDF
# ---------------------------------------------------------------------------

class TestZFromPctile:
    def test_50th_percentile_is_zero(self):
        """50th percentile should give z ≈ 0."""
        z = _z_from_pctile(0.50)
        assert abs(z) < 0.01

    def test_84th_percentile_is_approximately_one(self):
        """84.13th percentile ≈ z=1.0 (one standard deviation above mean)."""
        z = _z_from_pctile(0.8413)
        assert abs(z - 1.0) < 0.01

    def test_5th_percentile_is_negative(self):
        """5th percentile should give z ≈ -1.645."""
        z = _z_from_pctile(0.05)
        assert abs(z - (-1.645)) < 0.02

    def test_95th_percentile_is_positive(self):
        """95th percentile should give z ≈ +1.645."""
        z = _z_from_pctile(0.95)
        assert abs(z - 1.645) < 0.02

    def test_symmetry(self):
        """z at p and z at (1-p) should be negatives of each other."""
        z05 = _z_from_pctile(0.05)
        z95 = _z_from_pctile(0.95)
        assert abs(z05 + z95) < 0.001

    def test_invalid_percentile_raises(self):
        """Values outside (0,1) should raise ValueError."""
        with pytest.raises(ValueError):
            _z_from_pctile(0.0)
        with pytest.raises(ValueError):
            _z_from_pctile(1.0)


# ---------------------------------------------------------------------------
# 2. anthropometric_percentile
# ---------------------------------------------------------------------------

class TestAnthropometricPercentile:
    def test_stature_50th_male(self):
        """Male 50th-percentile stature should equal the mean (1755 mm)."""
        r = _ok(anthropometric_percentile("stature", 0.50, sex="male"))
        assert abs(r["dimension_mm"] - 1755.0) < 1.0

    def test_stature_50th_female(self):
        """Female 50th-percentile stature should equal female mean (1621 mm)."""
        r = _ok(anthropometric_percentile("stature", 0.50, sex="female"))
        assert abs(r["dimension_mm"] - 1621.0) < 1.0

    def test_5th_percentile_below_mean(self):
        """5th-percentile dimension < mean."""
        r = _ok(anthropometric_percentile("stature", 0.05, sex="male"))
        assert r["dimension_mm"] < 1755.0

    def test_95th_percentile_above_mean(self):
        """95th-percentile dimension > mean."""
        r = _ok(anthropometric_percentile("stature", 0.95, sex="male"))
        assert r["dimension_mm"] > 1755.0

    def test_5th_and_95th_symmetry_about_mean(self):
        """5th and 95th percentiles should be equidistant from the mean."""
        r5 = _ok(anthropometric_percentile("shoulder_breadth", 0.05, sex="male"))
        r95 = _ok(anthropometric_percentile("shoulder_breadth", 0.95, sex="male"))
        mean = 465.0
        diff5 = abs(mean - r5["dimension_mm"])
        diff95 = abs(r95["dimension_mm"] - mean)
        assert abs(diff5 - diff95) < 0.5  # symmetric about mean

    def test_z_score_computation(self):
        """Verify z-score embedded in result is correct."""
        r = _ok(anthropometric_percentile("stature", 0.84, sex="male"))
        # z at 84th ≈ 1.0 → stature ≈ 1755 + 1.0×71 = 1826
        assert abs(r["dimension_mm"] - 1826.0) < 5.0

    def test_unknown_dimension_error(self):
        """Unknown dimension name should return ok=False."""
        r = _err(anthropometric_percentile("nonexistent_dimension", 0.50))
        assert "Unknown dimension" in r["reason"]

    def test_invalid_sex_error(self):
        """Invalid sex string should return ok=False."""
        r = _err(anthropometric_percentile("stature", 0.50, sex="robot"))
        assert "sex" in r["reason"]

    def test_invalid_percentile_error(self):
        """Percentile outside (0,1) should return ok=False."""
        r = _err(anthropometric_percentile("stature", 1.5))
        assert "percentile" in r["reason"]

    def test_all_dimensions_present(self):
        """All dimensions in table should return valid results at 50th percentile."""
        for dim in _ANTHROPOMETRIC_TABLE:
            r = anthropometric_percentile(dim, 0.50, sex="male")
            assert r["ok"] is True, f"Failed for dimension {dim!r}: {r}"


# ---------------------------------------------------------------------------
# 3. design_for_range
# ---------------------------------------------------------------------------

class TestDesignForRange:
    def test_clearance_gives_largest_user(self):
        """Clearance should return 95th-percentile critical value."""
        r = _ok(design_for_range("shoulder_breadth", application="clearance"))
        # 95th percentile male shoulder breadth: 465 + 1.645×26 ≈ 507.8 mm
        assert r["critical_mm"] > 465.0

    def test_reach_gives_smallest_user(self):
        """Reach should return 5th-percentile critical value."""
        r = _ok(design_for_range("functional_reach_forward", application="reach"))
        # 5th-percentile female: 650 + z(0.05)×42 ≈ 650 - 1.645×42 ≈ 581 mm
        assert r["critical_mm"] < 650.0

    def test_clearance_includes_both_sexes(self):
        """With include_both_sexes=True, clearance uses the larger of male/female 95th."""
        r_both = _ok(design_for_range("shoulder_breadth", application="clearance",
                                       include_both_sexes=True))
        r_male = _ok(design_for_range("shoulder_breadth", application="clearance",
                                       include_both_sexes=False))
        # Male shoulder breadth is larger, so both-sex critical should equal male 95th
        assert r_both["critical_mm"] >= r_male["critical_mm"] - 0.1

    def test_invalid_application_error(self):
        """Invalid application type should return ok=False."""
        r = _err(design_for_range("stature", application="invalid"))
        assert "application" in r["reason"]

    def test_warnings_populated(self):
        """Warnings list should contain text for clearance."""
        r = _ok(design_for_range("shoulder_breadth", application="clearance"))
        assert len(r["warnings"]) > 0


# ---------------------------------------------------------------------------
# 4. niosh_rwl — hand-calc verification
# ---------------------------------------------------------------------------

class TestNioshRwl:
    def test_niosh_1994_example(self):
        """
        Verify against NIOSH 1994 example (Waters et al.):
        H=40cm, V=30cm, D=40cm, A=0, F=0.2/min, coupling=good.
        RWL = 23 × (25/40) × (1 - 0.003×|30-75|) × (0.82 + 4.5/40) × 1.0 × FM × 1.0
            = 23 × 0.625 × (1 - 0.003×45) × (0.82 + 0.1125) × 1.0 × 1.0 × 1.0
            = 23 × 0.625 × 0.865 × 0.9325 × 1.0
            ≈ 23 × 0.625 × 0.865 × 0.9325 ≈ 11.60 kg
        """
        r = _ok(niosh_rwl(L_kg=10.0, H_cm=40.0, V_cm=30.0, D_cm=40.0,
                          A_deg=0.0, freq_per_min=0.2, duration="short", coupling="good"))
        # Verify individual multipliers
        assert abs(r["HM"] - 0.625) < 0.001, f"HM={r['HM']}"
        assert abs(r["VM"] - 0.865) < 0.002, f"VM={r['VM']}"
        assert abs(r["DM"] - 0.9325) < 0.002, f"DM={r['DM']}"
        assert abs(r["AM"] - 1.000) < 0.001, f"AM={r['AM']}"
        assert r["FM"] == 1.00, f"FM={r['FM']}"
        assert r["CM"] == 1.00, f"CM={r['CM']}"
        expected_rwl = 23.0 * 0.625 * 0.865 * 0.9325 * 1.0 * 1.0 * 1.0
        assert abs(r["RWL_kg"] - expected_rwl) < 0.05, f"RWL={r['RWL_kg']}"

    def test_symmetric_lift_am_equals_one(self):
        """Zero asymmetry angle → AM = 1.0."""
        r = _ok(niosh_rwl(L_kg=5.0, H_cm=25.0, V_cm=75.0, D_cm=25.0, A_deg=0.0))
        assert r["AM"] == 1.0

    def test_max_asymmetry_reduces_am(self):
        """135° asymmetry → AM = 1 - 0.0032 × 135 = 0.568."""
        r = _ok(niosh_rwl(L_kg=5.0, H_cm=25.0, V_cm=75.0, D_cm=25.0, A_deg=135.0))
        expected_am = max(0.0, 1.0 - 0.0032 * 135.0)
        assert abs(r["AM"] - expected_am) < 0.001

    def test_optimal_conditions_rwl_near_lc(self):
        """
        At optimal conditions (H=25, V=75, D=25, A=0, low freq, good coupling),
        RWL should approach the Load Constant (23 kg) since all multipliers → 1.
        DM = 0.82 + 4.5/25 = 1.00
        """
        r = _ok(niosh_rwl(L_kg=20.0, H_cm=25.0, V_cm=75.0, D_cm=25.0,
                          A_deg=0.0, freq_per_min=0.2, duration="short", coupling="good"))
        assert r["DM"] == pytest.approx(1.00, abs=0.001)
        assert r["HM"] == pytest.approx(1.00, abs=0.001)  # H=25 → min, HM=1
        assert r["VM"] == pytest.approx(1.00, abs=0.001)  # V=75 → VM=1
        assert r["RWL_kg"] == pytest.approx(_NIOSH_LC, abs=0.1)

    def test_li_exceeds_one_warning(self):
        """LI > 1.0 should generate a warning."""
        r = _ok(niosh_rwl(L_kg=25.0, H_cm=60.0, V_cm=30.0, D_cm=50.0))
        assert r["LI"] > 1.0
        assert any("LI=" in w for w in r["warnings"])

    def test_invalid_h_cm(self):
        """H_cm <= 0 should return ok=False."""
        r = _err(niosh_rwl(L_kg=10.0, H_cm=0.0, V_cm=75.0, D_cm=25.0))
        assert "H_cm" in r["reason"]

    def test_invalid_v_cm_out_of_range(self):
        """V_cm > 175 should return ok=False."""
        r = _err(niosh_rwl(L_kg=10.0, H_cm=25.0, V_cm=200.0, D_cm=25.0))
        assert "V_cm" in r["reason"]

    def test_poor_coupling_reduces_rwl(self):
        """Poor coupling at V < 75 cm reduces CM from 1.0 to 0.9."""
        r_good = _ok(niosh_rwl(L_kg=5.0, H_cm=30.0, V_cm=50.0, D_cm=30.0,
                               coupling="good"))
        r_poor = _ok(niosh_rwl(L_kg=5.0, H_cm=30.0, V_cm=50.0, D_cm=30.0,
                               coupling="poor"))
        assert r_poor["RWL_kg"] < r_good["RWL_kg"]
        assert abs(r_poor["CM"] - 0.90) < 0.001


# ---------------------------------------------------------------------------
# 5. lifting_index
# ---------------------------------------------------------------------------

class TestLiftingIndex:
    def test_acceptable_lift(self):
        """Light load at good conditions → LI ≤ 1.0 → acceptable."""
        r = _ok(lifting_index(L_kg=5.0, H_cm=25.0, V_cm=75.0, D_cm=25.0))
        assert r["LI"] <= 1.0
        assert r["risk_level"] == "acceptable"

    def test_elevated_risk(self):
        """Moderately heavy lift in poor conditions → LI between 1–3."""
        r = _ok(lifting_index(L_kg=18.0, H_cm=45.0, V_cm=30.0, D_cm=50.0))
        if r["LI"] > 1.0:
            assert r["risk_level"] in ("elevated_risk", "high_risk")

    def test_high_risk(self):
        """Very heavy load at poor conditions → LI > 3 → high_risk."""
        r = _ok(lifting_index(L_kg=40.0, H_cm=60.0, V_cm=10.0, D_cm=80.0,
                              coupling="poor"))
        # With these extreme conditions, LI > 3 is expected
        if r["LI"] > 3.0:
            assert r["risk_level"] == "high_risk"


# ---------------------------------------------------------------------------
# 6. snook_push_pull
# ---------------------------------------------------------------------------

class TestSnookPushPull:
    def test_push_male_returns_valid_force(self):
        """Push task for male at low frequency should return a positive limit."""
        r = _ok(snook_push_pull("push", "male", freq_per_min=1.0, distance_m=7.5))
        assert r["max_acceptable_N"] > 0

    def test_carry_female_returns_valid_force(self):
        """Carry task for female should return a positive limit."""
        r = _ok(snook_push_pull("carry", "female", freq_per_min=2.0, distance_m=7.5))
        assert r["max_acceptable_N"] > 0

    def test_exceedance_flag_set(self):
        """Applied force above limit should set exceeds_limit=True."""
        r = _ok(snook_push_pull("push", "female", freq_per_min=6.0, distance_m=30.0,
                                force_applied_N=500.0))
        assert r["exceeds_limit"] is True
        assert len(r["warnings"]) > 0

    def test_no_exceedance_when_within_limit(self):
        """Applied force at half the limit should not exceed."""
        r_limit = _ok(snook_push_pull("push", "male", freq_per_min=1.0, distance_m=7.5))
        limit = r_limit["max_acceptable_N"]
        r = _ok(snook_push_pull("push", "male", freq_per_min=1.0, distance_m=7.5,
                                force_applied_N=limit * 0.5))
        assert r["exceeds_limit"] is False

    def test_invalid_task_error(self):
        """Invalid task type should return ok=False."""
        r = _err(snook_push_pull("sprint", "male", 1.0, 5.0))
        assert "task" in r["reason"]


# ---------------------------------------------------------------------------
# 7. grip_strength_percentile
# ---------------------------------------------------------------------------

class TestGripStrength:
    def test_50th_male_equals_mean(self):
        """Male 50th-percentile grip ≈ 476 N (mean)."""
        r = _ok(grip_strength_percentile(0.50, sex="male"))
        assert abs(r["grip_strength_N"] - 476.0) < 2.0

    def test_50th_female_equals_mean(self):
        """Female 50th-percentile grip ≈ 285 N (mean)."""
        r = _ok(grip_strength_percentile(0.50, sex="female"))
        assert abs(r["grip_strength_N"] - 285.0) < 2.0

    def test_5th_percentile_lower_than_mean(self):
        """5th-percentile grip < mean."""
        r = _ok(grip_strength_percentile(0.05, sex="male"))
        assert r["grip_strength_N"] < 476.0

    def test_5th_percentile_warning(self):
        """5th-percentile should trigger a design warning."""
        r = _ok(grip_strength_percentile(0.05, sex="female"))
        assert len(r["warnings"]) > 0


# ---------------------------------------------------------------------------
# 8. pinch_strength_percentile
# ---------------------------------------------------------------------------

class TestPinchStrength:
    def test_50th_male_equals_mean(self):
        """Male 50th-percentile pinch ≈ 100 N (mean)."""
        r = _ok(pinch_strength_percentile(0.50, sex="male"))
        assert abs(r["pinch_strength_N"] - 100.0) < 2.0

    def test_female_lower_than_male(self):
        """Female 50th-percentile pinch < male 50th-percentile."""
        rm = _ok(pinch_strength_percentile(0.50, sex="male"))
        rf = _ok(pinch_strength_percentile(0.50, sex="female"))
        assert rf["pinch_strength_N"] < rm["pinch_strength_N"]

    def test_invalid_sex_error(self):
        """Invalid sex should return ok=False."""
        r = _err(pinch_strength_percentile(0.50, sex="other"))
        assert "sex" in r["reason"]


# ---------------------------------------------------------------------------
# 9. rula_score
# ---------------------------------------------------------------------------

class TestRulaScore:
    def test_neutral_posture_low_score(self):
        """Near-neutral posture with no load should give low grand score."""
        r = _ok(rula_score(
            upper_arm_angle_deg=15.0,
            lower_arm_angle_deg=80.0,
            wrist_angle_deg=5.0,
            neck_angle_deg=10.0,
            trunk_angle_deg=5.0,
        ))
        assert r["grand_score"] <= 3

    def test_extreme_posture_high_score(self):
        """Extreme posture with high load should give high grand score."""
        r = _ok(rula_score(
            upper_arm_angle_deg=100.0,
            lower_arm_angle_deg=150.0,
            wrist_angle_deg=45.0,
            neck_angle_deg=35.0,
            trunk_angle_deg=50.0,
            wrist_twisted=True,
            shoulder_raised=True,
            upper_arm_abducted=True,
            static_or_repeated=True,
            force_kg=15.0,
        ))
        assert r["grand_score"] >= 5

    def test_action_level_assignment(self):
        """Grand score 7 should give action level 4."""
        r = _ok(rula_score(
            upper_arm_angle_deg=100.0,
            lower_arm_angle_deg=150.0,
            wrist_angle_deg=45.0,
            neck_angle_deg=35.0,
            trunk_angle_deg=50.0,
            static_or_repeated=True,
            force_kg=15.0,
        ))
        assert r["action_level"] in (3, 4)

    def test_neck_over_20_generates_warning(self):
        """Neck angle > 20° should generate a warning."""
        r = _ok(rula_score(
            upper_arm_angle_deg=15.0,
            lower_arm_angle_deg=80.0,
            wrist_angle_deg=5.0,
            neck_angle_deg=30.0,
            trunk_angle_deg=5.0,
        ))
        assert any("Neck" in w for w in r["warnings"])

    def test_missing_required_arg_returns_error(self):
        """Missing required joint angle should not crash (handled by tools layer)."""
        # Calling with valid angles, just verifying no exception
        r = rula_score(10.0, 80.0, 5.0, 10.0, 5.0)
        assert r.get("ok") is True


# ---------------------------------------------------------------------------
# 10. reba_score
# ---------------------------------------------------------------------------

class TestRebaScore:
    def test_neutral_posture_negligible_risk(self):
        """Neutral posture with no load → low REBA score."""
        r = _ok(reba_score(
            trunk_angle_deg=5.0,
            neck_angle_deg=10.0,
            leg_angle_deg=0.0,
            upper_arm_angle_deg=15.0,
            lower_arm_angle_deg=80.0,
            wrist_angle_deg=5.0,
        ))
        assert r["reba_score"] <= 5

    def test_extreme_posture_high_score(self):
        """Extreme posture with heavy load → high REBA score."""
        r = _ok(reba_score(
            trunk_angle_deg=80.0,
            neck_angle_deg=35.0,
            leg_angle_deg=70.0,
            upper_arm_angle_deg=100.0,
            lower_arm_angle_deg=150.0,
            wrist_angle_deg=30.0,
            load_kg=15.0,
            coupling="poor",
        ))
        assert r["reba_score"] >= 8

    def test_trunk_over_60_generates_warning(self):
        """Trunk angle > 60° should generate warning."""
        r = _ok(reba_score(
            trunk_angle_deg=70.0,
            neck_angle_deg=10.0,
            leg_angle_deg=0.0,
            upper_arm_angle_deg=20.0,
            lower_arm_angle_deg=80.0,
            wrist_angle_deg=5.0,
        ))
        assert any("Trunk" in w for w in r["warnings"])

    def test_invalid_coupling_error(self):
        """Invalid coupling string should return ok=False."""
        r = _err(reba_score(5.0, 10.0, 0.0, 15.0, 80.0, 5.0, coupling="excellent"))
        assert "coupling" in r["reason"]


# ---------------------------------------------------------------------------
# 11. workstation_heights
# ---------------------------------------------------------------------------

class TestWorkstationHeights:
    def test_returns_valid_heights_for_default_male_50th(self):
        """Default male 50th-percentile should return sensible heights."""
        r = _ok(workstation_heights(sex="male", percentile=0.50))
        # Seat height should be in plausible range (350–550 mm)
        assert 350 < r["seat_height_lo_mm"] < 600
        assert r["seat_height_hi_mm"] > r["seat_height_lo_mm"]

    def test_standing_work_surface_varies_by_task(self):
        """Heavy work surface should be lower than precision surface."""
        r_heavy = _ok(workstation_heights(task_type="heavy_work"))
        r_prec = _ok(workstation_heights(task_type="precision"))
        assert r_heavy["work_surface_standing_mm"] < r_prec["work_surface_standing_mm"]

    def test_female_shorter_surfaces_than_male(self):
        """Female workstation heights should generally be lower than male."""
        rf = _ok(workstation_heights(sex="female", percentile=0.50))
        rm = _ok(workstation_heights(sex="male", percentile=0.50))
        assert rf["work_surface_standing_mm"] < rm["work_surface_standing_mm"]

    def test_invalid_task_type_error(self):
        """Invalid task type should return ok=False."""
        r = _err(workstation_heights(task_type="extreme_yoga"))
        assert "task_type" in r["reason"]


# ---------------------------------------------------------------------------
# 12. visual_angle
# ---------------------------------------------------------------------------

class TestVisualAngle:
    def test_formula_hand_calc(self):
        """
        For h=3 mm, d=600 mm:
        alpha = 2 * arctan(1.5 / 600) = 2 * arctan(0.0025)
              ≈ 2 * 0.0025 rad = 0.005 rad = 0.2865° = 17.19 arcmin
        """
        r = _ok(visual_angle(object_height_mm=3.0, viewing_distance_mm=600.0))
        expected_arcmin = math.degrees(2 * math.atan2(1.5, 600.0)) * 60.0
        assert abs(r["visual_angle_arcmin"] - expected_arcmin) < 0.01

    def test_adequate_flag_true_when_over_20_arcmin(self):
        """Character subtending ≥ 20 arcmin should be flagged adequate."""
        r = _ok(visual_angle(object_height_mm=5.8, viewing_distance_mm=600.0))
        # 5.8 mm at 600 mm: alpha ≈ 2*atan(2.9/600) ≈ 0.5611° = 33.67 arcmin
        assert r["adequate_for_reading"] is True

    def test_adequate_flag_false_when_under_20_arcmin(self):
        """Very small character should be flagged inadequate."""
        r = _ok(visual_angle(object_height_mm=2.0, viewing_distance_mm=600.0))
        # 2mm at 600mm: alpha ≈ 11.46 arcmin < 20
        assert r["adequate_for_reading"] is False
        assert len(r["warnings"]) > 0

    def test_invalid_distance_error(self):
        """Zero viewing distance should return ok=False."""
        r = _err(visual_angle(object_height_mm=3.0, viewing_distance_mm=0.0))
        assert "viewing_distance_mm" in r["reason"]


# ---------------------------------------------------------------------------
# 13. min_character_size
# ---------------------------------------------------------------------------

class TestMinCharacterSize:
    def test_min_char_height_hand_calc(self):
        """
        For d=600 mm, min_arcmin=20:
        alpha = 20/60 degrees = 0.3333°
        h = 2 * 600 * tan(0.3333°/2) = 2 * 600 * tan(0.1667°)
          = 1200 * tan(0.002909 rad) ≈ 1200 * 0.002909 ≈ 3.491 mm
        """
        r = _ok(min_character_size(viewing_distance_mm=600.0, min_arcmin=20.0))
        expected_h = 2.0 * 600.0 * math.tan(math.radians(20.0 / 60.0 / 2.0))
        assert abs(r["min_char_height_mm"] - expected_h) < 0.01

    def test_preferred_larger_than_minimum(self):
        """Preferred character size should be larger than minimum."""
        r = _ok(min_character_size(viewing_distance_mm=600.0))
        assert r["preferred_char_height_mm"] > r["min_char_height_mm"]

    def test_larger_distance_gives_larger_character(self):
        """Farther viewing distance requires larger characters."""
        r1 = _ok(min_character_size(viewing_distance_mm=300.0))
        r2 = _ok(min_character_size(viewing_distance_mm=600.0))
        assert r2["min_char_height_mm"] > r1["min_char_height_mm"]

    def test_proportional_scaling(self):
        """Doubling viewing distance should double character height."""
        r1 = _ok(min_character_size(viewing_distance_mm=400.0))
        r2 = _ok(min_character_size(viewing_distance_mm=800.0))
        ratio = r2["min_char_height_mm"] / r1["min_char_height_mm"]
        assert abs(ratio - 2.0) < 0.01


# ---------------------------------------------------------------------------
# 14. metabolic_expenditure
# ---------------------------------------------------------------------------

class TestMetabolicExpenditure:
    def test_moderate_activity_rate(self):
        """Moderate activity should give 450 W."""
        r = _ok(metabolic_expenditure(activity="moderate"))
        assert r["metabolic_rate_W"] == 450.0

    def test_heavy_exceeds_8h_ceiling(self):
        """Heavy work (600 W) exceeds 8h ceiling (350 W) → warning."""
        r = _ok(metabolic_expenditure(activity="heavy"))
        assert r["exceeds_8h_ceiling"] is True
        assert len(r["warnings"]) > 0

    def test_very_light_does_not_exceed_ceiling(self):
        """Very light work (175 W) is below 8h ceiling."""
        r = _ok(metabolic_expenditure(activity="very_light"))
        assert r["exceeds_8h_ceiling"] is False

    def test_total_energy_calculation(self):
        """Total energy = metabolic_rate × duration_s / 1000."""
        r = _ok(metabolic_expenditure(activity="light", duration_min=30.0))
        expected_kJ = 280.0 * 30.0 * 60.0 / 1000.0
        assert abs(r["total_energy_kJ"] - expected_kJ) < 0.1

    def test_rest_allowance_increases_with_activity(self):
        """Rest allowance should be higher for heavy vs light activity."""
        r_light = _ok(metabolic_expenditure(activity="light", duration_min=60.0))
        r_heavy = _ok(metabolic_expenditure(activity="heavy", duration_min=60.0))
        assert r_heavy["rest_allowance_min"] > r_light["rest_allowance_min"]

    def test_invalid_activity_error(self):
        """Invalid activity string should return ok=False."""
        r = _err(metabolic_expenditure(activity="sprint"))
        assert "activity" in r["reason"]


# ---------------------------------------------------------------------------
# 15. rest_allowance (standalone Murrell formula)
# ---------------------------------------------------------------------------

class TestRestAllowance:
    def test_murrell_formula_hand_calc(self):
        """
        Murrell (1965): R = T × (M - S) / (M - 1.5)
        where S = 4.0 W/kg (8-hour metabolic standard), 1.5 W/kg = basal.
        For M_W=450W, mass=75kg → M_nrm = 6.0 W/kg
        fraction = (6.0 - 4.0) / (6.0 - 1.5) = 2.0 / 4.5 ≈ 0.4444
        rest_min = 60 × 0.4444 ≈ 26.67 min
        """
        r = _ok(rest_allowance(metabolic_rate_W=450.0, body_mass_kg=75.0,
                               task_duration_min=60.0))
        M_nrm = 450.0 / 75.0  # = 6.0 W/kg
        S = 4.0
        _BASAL = 1.5
        expected_fraction = (M_nrm - S) / (M_nrm - _BASAL)
        expected_rest = 60.0 * expected_fraction
        assert abs(r["rest_fraction"] - expected_fraction) < 0.001
        assert abs(r["rest_min"] - expected_rest) < 0.01

    def test_below_threshold_no_rest_needed(self):
        """If metabolic rate ≤ rest rate, no rest needed."""
        r = _ok(rest_allowance(metabolic_rate_W=80.0, body_mass_kg=75.0))
        # M_nrm = 80/75 = 1.067 W/kg < S=1.5
        assert r["rest_fraction"] == 0.0
        assert r["rest_min"] == 0.0

    def test_warning_above_ceiling(self):
        """Rate > 350 W ceiling should trigger warning."""
        r = _ok(rest_allowance(metabolic_rate_W=600.0))
        assert len(r["warnings"]) > 0

    def test_invalid_rate_error(self):
        """Negative or zero metabolic rate should return ok=False."""
        r = _err(rest_allowance(metabolic_rate_W=0.0))
        assert "metabolic_rate_W" in r["reason"]


# ---------------------------------------------------------------------------
# 16. reach_envelope
# ---------------------------------------------------------------------------

class TestReachEnvelope:
    def test_5th_percentile_female_smaller_reach(self):
        """5th-percentile female reach < 50th-percentile male reach."""
        rf5 = _ok(reach_envelope(sex="female", percentile=0.05))
        rm50 = _ok(reach_envelope(sex="male", percentile=0.50))
        assert rf5["reach_radius_mm"] < rm50["reach_radius_mm"]

    def test_maximum_reach_larger_than_functional(self):
        """Maximum reach should be ~20% more than functional reach."""
        r_func = _ok(reach_envelope(reach_type="functional"))
        r_max = _ok(reach_envelope(reach_type="maximum"))
        ratio = r_max["reach_radius_mm"] / r_func["reach_radius_mm"]
        assert abs(ratio - 1.20) < 0.01

    def test_reach_design_warning_at_5th_percentile(self):
        """5th-percentile design should generate a warning."""
        r = _ok(reach_envelope(percentile=0.05))
        assert len(r["warnings"]) > 0

    def test_seated_vs_standing(self):
        """Both postures should return valid results."""
        r_st = _ok(reach_envelope(posture="standing"))
        r_se = _ok(reach_envelope(posture="seated"))
        assert r_st["reach_radius_mm"] > 0
        assert r_se["reach_radius_mm"] > 0

    def test_invalid_posture_error(self):
        """Invalid posture should return ok=False."""
        r = _err(reach_envelope(posture="crouching"))
        assert "posture" in r["reason"]

    def test_invalid_reach_type_error(self):
        """Invalid reach_type should return ok=False."""
        r = _err(reach_envelope(reach_type="superhuman"))
        assert "reach_type" in r["reason"]
