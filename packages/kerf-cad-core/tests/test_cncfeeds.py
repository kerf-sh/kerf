"""
Hermetic tests for kerf_cad_core.cncfeeds — feeds & speeds / cutting-parameter
calculator.

Coverage:
  calc.spindle_rpm          — RPM from cutting speed & diameter
  calc.feed_rate            — table feed rate from chip load × teeth × RPM
  calc.mrr_milling          — MRR for milling
  calc.mrr_drilling         — MRR for drilling
  calc.mrr_turning          — MRR for turning
  calc.cutting_power        — cutting power & torque from Kc
  calc.tangential_force     — tangential cutting force
  calc.chip_thinning_factor — CTF for radial engagement
  calc.corrected_chip_load  — adjusted chip load
  calc.tool_deflection      — cantilever deflection & max stickout
  calc.surface_finish_ra    — theoretical Ra
  calc.drill_thrust_torque  — drilling thrust & torque
  calc.tapping_speed        — rigid tapping axial feed

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas verified by hand against Machinery's Handbook / Sandvik handbooks.

References
----------
Machinery's Handbook, 30th ed.
Sandvik Coromant Milling/Drilling/Turning Handbooks

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.cncfeeds.calc import (
    MATERIAL_KC,
    chip_thinning_factor,
    corrected_chip_load,
    cutting_power,
    drill_thrust_torque,
    feed_rate,
    mrr_drilling,
    mrr_milling,
    mrr_turning,
    spindle_rpm,
    surface_finish_ra,
    tangential_force,
    tapping_speed,
    tool_deflection,
)
from kerf_cad_core.cncfeeds.tools import (
    run_chip_thinning,
    run_corrected_chip_load,
    run_cutting_power,
    run_drill_thrust_torque,
    run_feed_rate,
    run_mrr_drilling,
    run_mrr_milling,
    run_mrr_turning,
    run_spindle_rpm,
    run_surface_finish_ra,
    run_tapping_speed,
    run_tangential_force,
    run_tool_deflection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _Ctx:
    """Minimal ProjectCtx stub — tools only inspect it for type."""
    project_id = uuid.uuid4()


_CTX = _Ctx()


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


def _ok(payload: str) -> dict:
    d = json.loads(payload)
    assert d.get("ok") is True, f"Expected ok=True but got: {d}"
    return d


def _fail(payload: str) -> dict:
    d = json.loads(payload)
    assert d.get("ok") is False, f"Expected ok=False but got: {d}"
    return d


# ===========================================================================
# 1. spindle_rpm
# ===========================================================================

class TestSpindleRpm:
    def test_basic(self):
        # n = 1000 × vc / (π × D) = 1000 × 100 / (π × 50) ≈ 636.62 rpm
        r = spindle_rpm(100.0, 50.0)
        assert r["ok"]
        expected = 1000.0 * 100.0 / (math.pi * 50.0)
        assert abs(r["rpm"] - expected) < 0.01

    def test_small_diameter(self):
        # D=6 mm, vc=60 m/min → n = 1000×60/(π×6) ≈ 3183.1
        r = spindle_rpm(60.0, 6.0)
        assert r["ok"]
        expected = 1000.0 * 60.0 / (math.pi * 6.0)
        assert abs(r["rpm"] - expected) < 0.1

    def test_vc_zero_fails(self):
        r = spindle_rpm(0.0, 10.0)
        assert not r["ok"]

    def test_diameter_zero_fails(self):
        r = spindle_rpm(100.0, 0.0)
        assert not r["ok"]

    def test_negative_fails(self):
        r = spindle_rpm(-50.0, 10.0)
        assert not r["ok"]

    def test_warnings_empty(self):
        r = spindle_rpm(100.0, 20.0)
        assert r["warnings"] == []

    def test_tool_happy(self):
        d = _ok(_run(run_spindle_rpm(_CTX, _args(vc=200.0, diameter=100.0))))
        expected = 1000.0 * 200.0 / (math.pi * 100.0)
        assert abs(d["rpm"] - expected) < 0.01

    def test_tool_missing_vc(self):
        _fail(_run(run_spindle_rpm(_CTX, _args(diameter=10.0))))

    def test_tool_missing_diameter(self):
        _fail(_run(run_spindle_rpm(_CTX, _args(vc=100.0))))


# ===========================================================================
# 2. feed_rate
# ===========================================================================

class TestFeedRate:
    def test_basic(self):
        # Vf = 0.1 × 4 × 1000 = 400 mm/min
        r = feed_rate(0.1, 4, 1000.0)
        assert r["ok"]
        assert abs(r["feed_mm_min"] - 400.0) < 0.001

    def test_two_flute(self):
        r = feed_rate(0.05, 2, 3000.0)
        assert r["ok"]
        assert abs(r["feed_mm_min"] - 300.0) < 0.001

    def test_chip_load_low_warning(self):
        r = feed_rate(0.0005, 4, 1000.0)
        assert r["ok"]
        assert "chip_load_low" in r["warnings"]

    def test_chip_load_high_warning(self):
        r = feed_rate(0.6, 4, 500.0)
        assert r["ok"]
        assert "chip_load_high" in r["warnings"]

    def test_no_warnings_normal(self):
        r = feed_rate(0.1, 4, 1000.0)
        assert r["warnings"] == []

    def test_zero_teeth_fails(self):
        r = feed_rate(0.1, 0, 1000.0)
        assert not r["ok"]

    def test_tool_happy(self):
        d = _ok(_run(run_feed_rate(_CTX, _args(chip_load=0.1, teeth=4, rpm=1000.0))))
        assert abs(d["feed_mm_min"] - 400.0) < 0.001

    def test_tool_missing_teeth(self):
        _fail(_run(run_feed_rate(_CTX, _args(chip_load=0.1, rpm=1000.0))))


# ===========================================================================
# 3. mrr_milling
# ===========================================================================

class TestMrrMilling:
    def test_basic(self):
        # Q = 10 × 5 × 500 = 25000 mm³/min
        r = mrr_milling(10.0, 5.0, 500.0)
        assert r["ok"]
        assert abs(r["mrr_mm3_min"] - 25000.0) < 0.1

    def test_slot_full_width(self):
        # ae=D=12, ap=3, Vf=600
        r = mrr_milling(12.0, 3.0, 600.0)
        assert r["ok"]
        assert abs(r["mrr_mm3_min"] - 21600.0) < 0.1

    def test_zero_depth_fails(self):
        r = mrr_milling(10.0, 0.0, 500.0)
        assert not r["ok"]

    def test_tool_happy(self):
        d = _ok(_run(run_mrr_milling(_CTX, _args(width=10.0, depth=5.0, feed_mm_min=500.0))))
        assert abs(d["mrr_mm3_min"] - 25000.0) < 0.1


# ===========================================================================
# 4. mrr_drilling
# ===========================================================================

class TestMrrDrilling:
    def test_basic(self):
        # Q = π/4 × 10² × 0.2 × 1000 = π/4 × 100 × 200 ≈ 15707.96
        r = mrr_drilling(10.0, 0.2, 1000.0)
        assert r["ok"]
        expected = (math.pi / 4.0) * 100.0 * 0.2 * 1000.0
        assert abs(r["mrr_mm3_min"] - expected) < 0.1

    def test_feed_mm_min(self):
        r = mrr_drilling(10.0, 0.2, 1000.0)
        assert abs(r["feed_mm_min"] - 200.0) < 0.001

    def test_zero_rpm_fails(self):
        r = mrr_drilling(10.0, 0.2, 0.0)
        assert not r["ok"]

    def test_tool_happy(self):
        d = _ok(_run(run_mrr_drilling(_CTX, _args(diameter=10.0, feed_per_rev=0.2, rpm=1000.0))))
        expected = (math.pi / 4.0) * 100.0 * 0.2 * 1000.0
        assert abs(d["mrr_mm3_min"] - expected) < 0.1


# ===========================================================================
# 5. mrr_turning
# ===========================================================================

class TestMrrTurning:
    def test_basic(self):
        # Q = 2 × 0.3 × 200 × 1000 = 120000 mm³/min
        r = mrr_turning(2.0, 0.3, 200.0)
        assert r["ok"]
        assert abs(r["mrr_mm3_min"] - 120000.0) < 0.1

    def test_fine_turning(self):
        # Q = 0.5 × 0.1 × 300 × 1000 = 15000
        r = mrr_turning(0.5, 0.1, 300.0)
        assert r["ok"]
        assert abs(r["mrr_mm3_min"] - 15000.0) < 0.1

    def test_zero_vc_fails(self):
        r = mrr_turning(2.0, 0.3, 0.0)
        assert not r["ok"]

    def test_tool_happy(self):
        d = _ok(_run(run_mrr_turning(_CTX, _args(depth_of_cut=2.0, feed_per_rev=0.3, vc=200.0))))
        assert abs(d["mrr_mm3_min"] - 120000.0) < 0.1


# ===========================================================================
# 6. cutting_power
# ===========================================================================

class TestCuttingPower:
    def test_basic(self):
        # Pc = 2000 × 15000 / 60000 = 500 W; Ps = 500 / 0.85 ≈ 588.24 W
        r = cutting_power(15000.0, 2000.0)
        assert r["ok"]
        pc_expected = 2000.0 * 15000.0 / 60000.0
        assert abs(r["cutting_power_W"] - pc_expected) < 0.1
        ps_expected = pc_expected / 0.85
        assert abs(r["spindle_power_W"] - ps_expected) < 0.1

    def test_efficiency_one(self):
        r = cutting_power(60000.0, 1000.0, efficiency=1.0)
        assert r["ok"]
        assert abs(r["cutting_power_W"] - r["spindle_power_W"]) < 0.001

    def test_over_power_warning(self):
        # kc=3000, mrr=200000 → Pc=3000×200000/60000=10000 W, Ps=10000/0.85≈11765 > 7500
        r = cutting_power(200000.0, 3000.0)
        assert r["ok"]
        assert "over_power" in r["warnings"]

    def test_no_over_power(self):
        r = cutting_power(1000.0, 1000.0)
        assert r["ok"]
        assert "over_power" not in r["warnings"]

    def test_torque_computed(self):
        r = cutting_power(15000.0, 2000.0, rpm=1000.0, diameter_mm=50.0)
        assert r["ok"]
        assert "torque_Nm" in r
        # T = Ps × 60 / (2π × 1000)
        ps = r["spindle_power_W"]
        expected_t = ps * 60.0 / (2.0 * math.pi * 1000.0)
        assert abs(r["torque_Nm"] - expected_t) < 0.001

    def test_efficiency_gt_one_fails(self):
        r = cutting_power(1000.0, 1000.0, efficiency=1.1)
        assert not r["ok"]

    def test_tool_happy(self):
        d = _ok(_run(run_cutting_power(_CTX, _args(mrr=15000.0, kc=2000.0))))
        assert d["cutting_power_W"] > 0

    def test_material_kc_table_populated(self):
        assert "mild_steel" in MATERIAL_KC
        assert "aluminum_6061" in MATERIAL_KC
        assert MATERIAL_KC["aluminum_6061"] < MATERIAL_KC["inconel_718"]


# ===========================================================================
# 7. tangential_force
# ===========================================================================

class TestTangentialForce:
    def test_basic(self):
        # Ft = 2000 × 0.1 × 5.0 × 1.0 = 1000 N
        r = tangential_force(2000.0, 0.1, 5.0)
        assert r["ok"]
        assert abs(r["tangential_N"] - 1000.0) < 0.001

    def test_with_width(self):
        # Ft = 1800 × 0.15 × 3.0 × 10.0 = 8100 N
        r = tangential_force(1800.0, 0.15, 3.0, width_of_cut=10.0)
        assert r["ok"]
        assert abs(r["tangential_N"] - 8100.0) < 0.001

    def test_zero_kc_fails(self):
        r = tangential_force(0.0, 0.1, 5.0)
        assert not r["ok"]

    def test_tool_happy(self):
        d = _ok(_run(run_tangential_force(_CTX, _args(kc=2000.0, chip_load=0.1, depth_of_cut=5.0))))
        assert abs(d["tangential_N"] - 1000.0) < 0.001


# ===========================================================================
# 8. chip_thinning_factor
# ===========================================================================

class TestChipThinningFactor:
    def test_full_slot_ctf_one(self):
        # ae = D/2 → CTF = 1.0
        r = chip_thinning_factor(10.0, 20.0)
        assert r["ok"]
        assert abs(r["ctf"] - 1.0) < 1e-9

    def test_full_diameter_ctf_one(self):
        # ae = D → CTF = 1.0
        r = chip_thinning_factor(20.0, 20.0)
        assert r["ok"]
        assert abs(r["ctf"] - 1.0) < 1e-9

    def test_quarter_engagement(self):
        # ae = D/4: CTF = D / (2√(ae×(D−ae))) = 20 / (2√(5×15)) = 20 / (2×√75)
        d = 20.0
        ae = 5.0
        r = chip_thinning_factor(ae, d)
        assert r["ok"]
        expected = d / (2.0 * math.sqrt(ae * (d - ae)))
        assert abs(r["ctf"] - expected) < 1e-9

    def test_ctf_geq_one(self):
        for ae_frac in [0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0]:
            r = chip_thinning_factor(ae_frac * 20.0, 20.0)
            assert r["ok"]
            assert r["ctf"] >= 1.0 - 1e-9

    def test_severe_warning(self):
        # ae/D = 0.02 < 0.05 → chip_thinning_severe
        r = chip_thinning_factor(0.4, 20.0)
        assert r["ok"]
        assert "chip_thinning_severe" in r["warnings"]

    def test_no_severe_warning_normal(self):
        r = chip_thinning_factor(5.0, 20.0)
        assert r["ok"]
        assert "chip_thinning_severe" not in r["warnings"]

    def test_ae_gt_d_fails(self):
        r = chip_thinning_factor(25.0, 20.0)
        assert not r["ok"]

    def test_tool_happy(self):
        d = _ok(_run(run_chip_thinning(_CTX, _args(radial_engagement=5.0, diameter=20.0))))
        assert d["ctf"] >= 1.0


# ===========================================================================
# 9. corrected_chip_load
# ===========================================================================

class TestCorrectedChipLoad:
    def test_full_slot_no_correction(self):
        # ae = D/2, CTF = 1.0 → programmed = nominal
        r = corrected_chip_load(0.1, 10.0, 20.0)
        assert r["ok"]
        assert abs(r["programmed_chip_load_mm"] - 0.1) < 1e-9

    def test_quarter_engagement_correction(self):
        d = 20.0
        ae = 5.0
        ctf = d / (2.0 * math.sqrt(ae * (d - ae)))
        r = corrected_chip_load(0.1, ae, d)
        assert r["ok"]
        assert abs(r["programmed_chip_load_mm"] - 0.1 * ctf) < 1e-9

    def test_ae_gt_d_fails(self):
        r = corrected_chip_load(0.1, 25.0, 20.0)
        assert not r["ok"]

    def test_tool_happy(self):
        d = _ok(_run(run_corrected_chip_load(_CTX, _args(nominal_chip_load=0.1, ae=5.0, diameter=20.0))))
        assert d["programmed_chip_load_mm"] >= 0.1


# ===========================================================================
# 10. tool_deflection
# ===========================================================================

class TestToolDeflection:
    def test_basic_carbide(self):
        # D=10mm, L=40mm, F=100N, E=600 GPa
        # I = π×10⁴/64 = 490.87 mm⁴
        # EI = 600000 × 490.87 = 2.945e8 N·mm²
        # δ = 100 × 40³ / (3 × 2.945e8) ≈ 100×64000 / 8.835e8 ≈ 0.0000725 mm
        r = tool_deflection(100.0, 40.0, 10.0, E_GPa=600.0)
        assert r["ok"]
        I = math.pi * 10.0 ** 4 / 64.0
        EI = 600.0e3 * I
        expected = 100.0 * 40.0 ** 3 / (3.0 * EI)
        assert abs(r["deflection_mm"] - expected) < 1e-9

    def test_excessive_deflection_warning(self):
        # Large force + long overhang should trigger warning
        r = tool_deflection(5000.0, 100.0, 10.0, E_GPa=210.0)
        assert r["ok"]
        assert "excessive_deflection" in r["warnings"]

    def test_small_deflection_no_warning(self):
        # Small force, short overhang
        r = tool_deflection(10.0, 5.0, 20.0, E_GPa=600.0)
        assert r["ok"]
        assert "excessive_deflection" not in r["warnings"]

    def test_high_aspect_ratio_warning(self):
        # stickout = 5×diameter → excessive_deflection
        r = tool_deflection(1.0, 50.0, 10.0, E_GPa=600.0)
        assert r["ok"]
        assert "excessive_deflection" in r["warnings"]

    def test_max_stickout_positive(self):
        r = tool_deflection(100.0, 40.0, 10.0)
        assert r["ok"]
        assert r["max_stickout_mm"] > 0

    def test_tool_happy(self):
        d = _ok(_run(run_tool_deflection(_CTX, _args(force=100.0, overhang=40.0, diameter=10.0))))
        assert d["deflection_mm"] > 0


# ===========================================================================
# 11. surface_finish_ra
# ===========================================================================

class TestSurfaceFinishRa:
    def test_basic(self):
        # Ra = fn² × 1000 / (32 × r_ε) = 0.2² × 1000 / (32 × 0.8) = 0.04×1000/25.6 ≈ 1.5625 µm
        r = surface_finish_ra(0.2, 0.8)
        assert r["ok"]
        expected = 0.2 ** 2 * 1000.0 / (32.0 * 0.8)
        assert abs(r["Ra_um"] - expected) < 1e-9

    def test_rz_four_times_ra(self):
        r = surface_finish_ra(0.2, 0.8)
        assert r["ok"]
        assert abs(r["Rz_um"] - 4.0 * r["Ra_um"]) < 1e-9

    def test_smaller_feed_better_finish(self):
        r1 = surface_finish_ra(0.1, 0.8)
        r2 = surface_finish_ra(0.2, 0.8)
        assert r1["Ra_um"] < r2["Ra_um"]

    def test_larger_nose_radius_better_finish(self):
        r1 = surface_finish_ra(0.2, 1.6)
        r2 = surface_finish_ra(0.2, 0.4)
        assert r1["Ra_um"] < r2["Ra_um"]

    def test_zero_nose_radius_fails(self):
        r = surface_finish_ra(0.2, 0.0)
        assert not r["ok"]

    def test_tool_happy(self):
        d = _ok(_run(run_surface_finish_ra(_CTX, _args(feed_per_rev=0.2, nose_radius=0.8))))
        assert d["Ra_um"] > 0


# ===========================================================================
# 12. drill_thrust_torque
# ===========================================================================

class TestDrillThrustTorque:
    def test_thrust_formula(self):
        # D=10, fn=0.2, kc=1800, angle=118°
        # κ = 59° = 59π/180 rad
        # thrust = 1800 × 0.2 × 5.0 × sin(59°)
        d = 10.0
        fn = 0.2
        kc = 1800.0
        angle = 118.0
        kappa = math.radians(angle / 2.0)
        expected_thrust = kc * fn * (d / 2.0) * math.sin(kappa)
        r = drill_thrust_torque(d, fn, kc, drill_point_angle=angle)
        assert r["ok"]
        assert abs(r["thrust_N"] - expected_thrust) < 0.001

    def test_torque_formula(self):
        # Mc = kc × fn × D² / 8 / 1000 [N·m]
        d = 10.0
        fn = 0.2
        kc = 1800.0
        expected_torque = kc * fn * d ** 2 / 8.0 / 1000.0
        r = drill_thrust_torque(d, fn, kc)
        assert r["ok"]
        assert abs(r["torque_Nm"] - expected_torque) < 1e-6

    def test_default_point_angle_118(self):
        r = drill_thrust_torque(10.0, 0.2, 1800.0)
        assert r["ok"]
        assert abs(r["drill_point_angle_deg"] - 118.0) < 0.001

    def test_135_point_angle(self):
        r = drill_thrust_torque(10.0, 0.2, 1800.0, drill_point_angle=135.0)
        assert r["ok"]

    def test_invalid_angle_fails(self):
        r = drill_thrust_torque(10.0, 0.2, 1800.0, drill_point_angle=0.0)
        assert not r["ok"]

    def test_invalid_angle_180_fails(self):
        r = drill_thrust_torque(10.0, 0.2, 1800.0, drill_point_angle=180.0)
        assert not r["ok"]

    def test_tool_happy(self):
        d = _ok(_run(run_drill_thrust_torque(_CTX, _args(diameter=10.0, feed_per_rev=0.2, kc=1800.0))))
        assert d["thrust_N"] > 0
        assert d["torque_Nm"] > 0


# ===========================================================================
# 13. tapping_speed
# ===========================================================================

class TestTappingSpeed:
    def test_m8_1_25_pitch(self):
        # M8×1.25 at 500 rpm → Vf = 1.25 × 500 = 625 mm/min
        r = tapping_speed(1.25, 500.0)
        assert r["ok"]
        assert abs(r["feed_mm_min"] - 625.0) < 0.001

    def test_m5_0_8_pitch(self):
        # M5×0.8 at 1000 rpm → Vf = 0.8 × 1000 = 800 mm/min
        r = tapping_speed(0.8, 1000.0)
        assert r["ok"]
        assert abs(r["feed_mm_min"] - 800.0) < 0.001

    def test_zero_pitch_fails(self):
        r = tapping_speed(0.0, 500.0)
        assert not r["ok"]

    def test_zero_rpm_fails(self):
        r = tapping_speed(1.25, 0.0)
        assert not r["ok"]

    def test_warnings_empty(self):
        r = tapping_speed(1.25, 500.0)
        assert r["warnings"] == []

    def test_tool_happy(self):
        d = _ok(_run(run_tapping_speed(_CTX, _args(pitch=1.25, rpm=500.0))))
        assert abs(d["feed_mm_min"] - 625.0) < 0.001

    def test_tool_missing_pitch(self):
        _fail(_run(run_tapping_speed(_CTX, _args(rpm=500.0))))


# ===========================================================================
# Cross-function integration checks
# ===========================================================================

class TestIntegration:
    def test_rpm_feeds_mrr_pipeline(self):
        """Full milling parameter chain: vc → rpm → Vf → MRR."""
        # Aluminum 6061, D=20mm endmill, 4 flutes
        vc = 300.0        # m/min
        D = 20.0          # mm
        fz = 0.05         # mm/tooth
        z = 4
        ae = 10.0         # mm (50% radial)
        ap = 5.0          # mm

        rpm_r = spindle_rpm(vc, D)
        assert rpm_r["ok"]
        n = rpm_r["rpm"]

        fr_r = feed_rate(fz, z, n)
        assert fr_r["ok"]
        vf = fr_r["feed_mm_min"]

        mrr_r = mrr_milling(ae, ap, vf)
        assert mrr_r["ok"]

        pc_r = cutting_power(mrr_r["mrr_mm3_min"], MATERIAL_KC["aluminum_6061"])
        assert pc_r["ok"]
        assert pc_r["cutting_power_W"] > 0

    def test_chip_thinning_pipeline(self):
        """Low ae triggers CTF; corrected chip load > nominal."""
        ae = 2.0    # mm — 10% of D=20mm
        D = 20.0
        nominal_fz = 0.05  # mm

        ct_r = chip_thinning_factor(ae, D)
        assert ct_r["ok"]
        assert ct_r["ctf"] > 1.0

        cc_r = corrected_chip_load(nominal_fz, ae, D)
        assert cc_r["ok"]
        assert cc_r["programmed_chip_load_mm"] > nominal_fz

    def test_drilling_full_chain(self):
        """Drill D=12, vc=40m/min, fn=0.15mm → thrust, torque, MRR."""
        D = 12.0
        vc = 40.0
        fn = 0.15
        kc = MATERIAL_KC["mild_steel"]

        rpm_r = spindle_rpm(vc, D)
        assert rpm_r["ok"]

        mrr_r = mrr_drilling(D, fn, rpm_r["rpm"])
        assert mrr_r["ok"]

        tt_r = drill_thrust_torque(D, fn, kc)
        assert tt_r["ok"]
        assert tt_r["thrust_N"] > 0

    def test_surface_finish_vs_feed(self):
        """Halving feed should quarter Ra (quadratic relationship)."""
        r1 = surface_finish_ra(0.2, 0.8)
        r2 = surface_finish_ra(0.1, 0.8)
        assert r1["ok"] and r2["ok"]
        # Ra ∝ fn² → r2.Ra ≈ r1.Ra / 4
        assert abs(r2["Ra_um"] - r1["Ra_um"] / 4.0) < 1e-9


# ---------------------------------------------------------------------------
# Externally-citable reference cases (Machinery's Handbook / Sandvik)
# ---------------------------------------------------------------------------

class TestCncFeedsExternalReferenceCases:
    """Cross-checked against Machinery's Handbook 30th ed. and Sandvik
    Coromant turning/milling/drilling handbooks."""

    def test_spindle_rpm_machinerys_handbook(self):
        # Machinery's Handbook 30th ed., Speeds & Feeds:
        # n = 1000*vc/(pi*D).  vc=120 m/min, D=50 mm -> 763.94 rpm.
        r = spindle_rpm(120.0, 50.0)
        assert math.isclose(r["rpm"], 1000.0 * 120.0 / (math.pi * 50.0),
                            rel_tol=1e-9)

    def test_feed_rate_vf_definition(self):
        # Machinery's Handbook: table feed Vf = fz * z * n.
        r = feed_rate(0.10, 4, 764.0)
        assert math.isclose(r["feed_mm_min"], 0.10 * 4 * 764.0, rel_tol=1e-12)

    def test_mrr_turning_sandvik(self):
        # Sandvik turning handbook: Q = ap * fn * vc * 1000 (mm^3/min).
        r = mrr_turning(2.0, 0.30, 200.0)
        assert math.isclose(r["mrr_mm3_min"], 2.0 * 0.30 * 200.0 * 1000.0,
                            rel_tol=1e-9)

    def test_mrr_milling_sandvik(self):
        # Sandvik milling handbook: Q = ae * ap * Vf (mm^3/min).
        r = mrr_milling(10.0, 3.0, 500.0)
        assert math.isclose(r["mrr_mm3_min"], 10.0 * 3.0 * 500.0, rel_tol=1e-12)

    def test_mrr_drilling_machinerys_handbook(self):
        # Machinery's Handbook: Q = (pi/4) D^2 * f * n.
        r = mrr_drilling(10.0, 0.2, 800.0)
        assert math.isclose(r["mrr_mm3_min"],
                            (math.pi / 4.0) * 100.0 * 0.2 * 800.0,
                            rel_tol=1e-9)

    def test_cutting_power_sandvik_formula(self):
        # Sandvik: Pc [W] = kc [N/mm^2] * Q [mm^3/min] / 60000.
        r = cutting_power(60000.0, 2000.0)
        assert math.isclose(r["cutting_power_W"], 2000.0 * 60000.0 / 60000.0,
                            rel_tol=1e-12)

    def test_surface_finish_ra_machinerys_handbook(self):
        # Machinery's Handbook: Rmax = f^2/(8*r_eps); Ra ≈ Rmax/4.
        # fn=0.2 mm/rev, r_eps=0.8 mm -> Rmax=6.25 um, Ra=1.5625 um.
        r = surface_finish_ra(0.2, 0.8)
        rmax_um = 0.2 ** 2 / (8.0 * 0.8) * 1000.0
        assert math.isclose(r["Rz_um"], rmax_um, rel_tol=1e-9)
        assert math.isclose(r["Ra_um"], rmax_um / 4.0, rel_tol=1e-9)

    def test_chip_thinning_factor_sandvik(self):
        # Sandvik/Kennametal: CTF = D/(2*sqrt(ae*(D-ae))) for ae<D/2.
        # ae=2 mm, D=10 mm -> CTF = 10/(2*sqrt(2*8)) = 1.25.
        r = chip_thinning_factor(2.0, 10.0)
        assert math.isclose(r["ctf"], 10.0 / (2.0 * math.sqrt(2.0 * 8.0)),
                            rel_tol=1e-9)

    def test_chip_thinning_unity_above_half_diameter(self):
        # Sandvik: no chip thinning correction when ae >= D/2 (CTF = 1.0).
        r = chip_thinning_factor(6.0, 10.0)
        assert math.isclose(r["ctf"], 1.0, rel_tol=1e-12)

    def test_tapping_feed_pitch_times_rpm(self):
        # Machinery's Handbook rigid tapping: Vf = pitch * rpm.
        r = tapping_speed(1.25, 500.0)
        assert math.isclose(r["feed_mm_min"], 1.25 * 500.0, rel_tol=1e-12)

    def test_tool_deflection_cantilever_beam(self):
        # Roark / Machinery's Handbook cantilever: delta = F*L^3/(3*E*I),
        # I = pi*D^4/64.  F=500 N, L=40 mm, D=12 mm, carbide E=600 GPa.
        r = tool_deflection(500.0, 40.0, 12.0, E_GPa=600.0)
        I = math.pi * 12.0 ** 4 / 64.0
        EI = 600.0e3 * I
        assert math.isclose(r["deflection_mm"], 500.0 * 40.0 ** 3 / (3.0 * EI),
                            rel_tol=1e-9)
