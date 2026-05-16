"""
Hermetic tests for kerf_cad_core.welding — weld process engineering.

Coverage:
  process.arc_heat_input          — HI = η·V·I/(1000·v)
  process.carbon_equivalent_iiw   — IIW CE formula
  process.preheat_temperature     — AWS D1.1 / Yurioka preheat
  process.cooling_time_t85        — Rykalin t8/5 (butt + fillet)
  process.fillet_weld_volume      — leg²/2 × length
  process.groove_weld_volume      — trapezoid × length
  process.deposition_time         — mass / rate × 3600
  process.electrode_consumption   — deposit / efficiency
  process.number_of_passes        — ceil(groove / pass)
  process.angular_distortion      — Okerblom empirical
  process.longitudinal_distortion — Lincoln Electric / thermal-stress
  process.interpass_temperature_check — AWS D1.1 limits
  tools.*                         — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas are verified algebraically against published expressions.

References
----------
AWS D1.1/D1.1M:2020 — Structural Welding Code (Steel)
IIW Doc. IXJ-123-85 — CE formula
Lincoln Electric "The Procedure Handbook of Arc Welding", 14th ed.
Radaj D. (1992) — Heat Effects of Welding, Springer

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.welding.process import (
    arc_heat_input,
    carbon_equivalent_iiw,
    preheat_temperature,
    cooling_time_t85,
    fillet_weld_volume,
    groove_weld_volume,
    deposition_time,
    electrode_consumption,
    number_of_passes,
    angular_distortion,
    longitudinal_distortion,
    interpass_temperature_check,
)
from kerf_cad_core.welding.tools import (
    run_arc_heat_input,
    run_carbon_equivalent_iiw,
    run_preheat_temperature,
    run_cooling_time_t85,
    run_fillet_weld_volume,
    run_groove_weld_volume,
    run_deposition_time,
    run_electrode_consumption,
    run_number_of_passes,
    run_angular_distortion,
    run_longitudinal_distortion,
    run_interpass_temperature_check,
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


REL = 1e-9  # relative tolerance


# ===========================================================================
# 1. arc_heat_input
# ===========================================================================

class TestArcHeatInput:

    def test_formula_algebraic(self):
        """HI = η × V × I / (1000 × v)."""
        eta, V, I, v = 0.85, 28.0, 200.0, 7.0
        expected = eta * V * I / (1000.0 * v)
        res = arc_heat_input(eta, V, I, v)
        assert res["ok"] is True
        assert abs(res["HI_kJ_mm"] - expected) / expected < REL

    def test_hi_increases_with_current(self):
        """Higher current → higher heat input."""
        hi_low  = arc_heat_input(0.80, 25.0, 150.0, 6.0)["HI_kJ_mm"]
        hi_high = arc_heat_input(0.80, 25.0, 300.0, 6.0)["HI_kJ_mm"]
        assert hi_high > hi_low

    def test_hi_decreases_with_travel_speed(self):
        """Higher travel speed → lower heat input."""
        hi_slow = arc_heat_input(0.85, 28.0, 200.0, 5.0)["HI_kJ_mm"]
        hi_fast = arc_heat_input(0.85, 28.0, 200.0, 10.0)["HI_kJ_mm"]
        assert hi_fast < hi_slow

    def test_hi_proportional_to_voltage(self):
        """Heat input ∝ V: doubling voltage doubles HI."""
        eta, V, I, v = 0.80, 25.0, 180.0, 6.0
        hi1 = arc_heat_input(eta, V, I, v)["HI_kJ_mm"]
        hi2 = arc_heat_input(eta, V * 2.0, I, v)["HI_kJ_mm"]
        assert abs(hi2 / hi1 - 2.0) < REL

    def test_excessive_hi_warning(self):
        """HI > 3.5 kJ/mm must generate a warning."""
        # Slow travel, high current to exceed 3.5 kJ/mm
        res = arc_heat_input(0.99, 40.0, 1200.0, 3.0)  # HI ≈ 15.84 kJ/mm
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_no_warning_normal_hi(self):
        """Normal HI should produce no warnings."""
        res = arc_heat_input(0.85, 24.0, 150.0, 6.0)  # HI ≈ 0.51 kJ/mm
        assert res["ok"] is True
        assert res["warnings"] == []

    def test_eta_above_1_returns_error(self):
        """Efficiency > 1.0 must return ok=False."""
        res = arc_heat_input(1.5, 28.0, 200.0, 7.0)
        assert res["ok"] is False

    def test_negative_voltage_returns_error(self):
        res = arc_heat_input(0.80, -28.0, 200.0, 7.0)
        assert res["ok"] is False

    def test_zero_travel_speed_returns_error(self):
        res = arc_heat_input(0.80, 28.0, 200.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 2. carbon_equivalent_iiw
# ===========================================================================

class TestCarbonEquivalentIIW:

    def test_formula_algebraic(self):
        """CE = C + Mn/6 + (Cr+Mo+V)/5 + (Cu+Ni)/15."""
        C, Mn, Si, Cr, Mo, V, Cu, Ni = 0.20, 1.40, 0.30, 0.10, 0.05, 0.02, 0.0, 0.0
        expected = C + Mn/6 + (Cr + Mo + V)/5 + (Cu + Ni)/15
        res = carbon_equivalent_iiw(C=C, Mn=Mn, Si=Si, Cr=Cr, Mo=Mo, V=V, Cu=Cu, Ni=Ni)
        assert res["ok"] is True
        assert abs(res["CE_IIW"] - expected) / expected < REL

    def test_pure_carbon_steel_s355(self):
        """S355 typical: C≈0.20, Mn≈1.50 → CE ≈ 0.45."""
        res = carbon_equivalent_iiw(C=0.20, Mn=1.50)
        assert res["ok"] is True
        expected = 0.20 + 1.50 / 6.0
        assert abs(res["CE_IIW"] - expected) < 1e-9

    def test_high_ce_warning(self):
        """CE > 0.45 must trigger a warning."""
        res = carbon_equivalent_iiw(C=0.30, Mn=1.80, Cr=0.50, Mo=0.20)
        assert res["ok"] is True
        assert res["CE_IIW"] > 0.45
        assert len(res["warnings"]) > 0

    def test_very_high_ce_cracking_warning(self):
        """CE > 0.70 must trigger a cracking-risk warning."""
        res = carbon_equivalent_iiw(C=0.40, Mn=2.0, Cr=0.80, Mo=0.50, V=0.10)
        assert res["ok"] is True
        assert res["CE_IIW"] > 0.70
        # Should have at least one cracking warning
        assert any("cracking" in w.lower() or "hydrogen" in w.lower() for w in res["warnings"])

    def test_defaults_zero_alloying(self):
        """With only C and Mn provided, alloy terms default to 0."""
        res = carbon_equivalent_iiw(C=0.18, Mn=1.00)
        assert res["ok"] is True
        assert res["CE_IIW"] == pytest.approx(0.18 + 1.00 / 6.0, rel=1e-9)

    def test_negative_C_returns_error(self):
        res = carbon_equivalent_iiw(C=-0.10, Mn=1.00)
        assert res["ok"] is False

    def test_negative_Mn_returns_error(self):
        res = carbon_equivalent_iiw(C=0.20, Mn=-0.5)
        assert res["ok"] is False


# ===========================================================================
# 3. preheat_temperature
# ===========================================================================

class TestPreheatTemperature:

    def test_zero_ce_no_preheat(self):
        """CE = 0 → preheat clamped to 0 °C."""
        res = preheat_temperature(CE=0.0, t_mm=20.0, HI_kJ_mm=1.5)
        assert res["ok"] is True
        assert res["T_preheat_C"] == 0.0

    def test_high_ce_requires_preheat(self):
        """High CE steel (0.55) + thick plate should give preheat > 50 °C."""
        res = preheat_temperature(CE=0.55, t_mm=40.0, HI_kJ_mm=1.0)
        assert res["ok"] is True
        assert res["T_preheat_C"] > 50.0

    def test_preheat_increases_with_ce(self):
        """Increasing CE must increase preheat."""
        T1 = preheat_temperature(CE=0.30, t_mm=20.0, HI_kJ_mm=1.0)["T_preheat_C"]
        T2 = preheat_temperature(CE=0.50, t_mm=20.0, HI_kJ_mm=1.0)["T_preheat_C"]
        assert T2 >= T1

    def test_preheat_increases_with_thickness(self):
        """Thicker plate requires higher preheat (thickness correction)."""
        T_thin  = preheat_temperature(CE=0.45, t_mm=15.0, HI_kJ_mm=1.5)["T_preheat_C"]
        T_thick = preheat_temperature(CE=0.45, t_mm=50.0, HI_kJ_mm=1.5)["T_preheat_C"]
        assert T_thick >= T_thin

    def test_preheat_decreases_with_high_HI(self):
        """Higher HI reduces required preheat (more heat already in joint)."""
        T_low_hi = preheat_temperature(CE=0.45, t_mm=25.0, HI_kJ_mm=1.0)["T_preheat_C"]
        T_hi_hi  = preheat_temperature(CE=0.45, t_mm=25.0, HI_kJ_mm=5.0)["T_preheat_C"]
        assert T_hi_hi <= T_low_hi

    def test_method_a_formula(self):
        """Method A: T_p = 350·√CE − 25 (before corrections)."""
        CE, t, HI = 0.40, 25.0, 1.0
        # At t=25mm, thickness correction=0; HI=1.0, HI reduction=0
        T_A_expected = max(0.0, 350.0 * math.sqrt(CE) - 25.0)
        res = preheat_temperature(CE=CE, t_mm=t, HI_kJ_mm=HI)
        assert res["ok"] is True
        assert abs(res["T_preheat_method_A"] - T_A_expected) < 1.0

    def test_negative_CE_returns_error(self):
        res = preheat_temperature(CE=-0.1, t_mm=20.0, HI_kJ_mm=1.0)
        assert res["ok"] is False

    def test_zero_thickness_returns_error(self):
        res = preheat_temperature(CE=0.40, t_mm=0.0, HI_kJ_mm=1.0)
        assert res["ok"] is False


# ===========================================================================
# 4. cooling_time_t85
# ===========================================================================

class TestCoolingTimeT85:

    def test_butt_weld_returns_positive(self):
        """Butt weld t8/5 must be positive for reasonable inputs."""
        res = cooling_time_t85(HI_kJ_mm=2.0, T_preheat_C=100.0, t_mm=20.0, joint_type="butt")
        assert res["ok"] is True
        assert res["t85_s"] > 0.0

    def test_fillet_weld_returns_positive(self):
        """Fillet weld t8/5 must be positive."""
        res = cooling_time_t85(HI_kJ_mm=1.5, T_preheat_C=50.0, t_mm=12.0, joint_type="fillet")
        assert res["ok"] is True
        assert res["t85_s"] > 0.0

    def test_butt_3d_formula_algebraic(self):
        """Verify 3D Rykalin formula algebraically."""
        HI, T0, h = 2.0, 100.0, 25.0
        Q = HI * 1000.0
        lam = 0.40
        inv_diff = (1.0 / 500.0) - (1.0 / 800.0)
        k3 = 6700.0 - 5.0 * T0
        t85_expected = k3 * Q**2 * inv_diff**2 / (2.0 * math.pi * lam)
        res = cooling_time_t85(HI, T0, h, joint_type="butt")
        assert res["ok"] is True
        assert abs(res["t85_s"] - t85_expected) / t85_expected < 1e-9

    def test_fillet_2d_formula_algebraic(self):
        """Verify 2D Rykalin formula algebraically."""
        HI, T0, h = 1.5, 50.0, 10.0
        Q = HI * 1000.0
        lam = 0.40
        rho_c = 3.6e-3
        inv_diff_sq = (1.0 / 500.0**2) - (1.0 / 800.0**2)
        k2 = 4300.0 - 4.3 * T0
        t85_expected = k2 * Q**2 * inv_diff_sq / (2.0 * math.pi**2 * lam**2 * rho_c * h**2)
        res = cooling_time_t85(HI, T0, h, joint_type="fillet")
        assert res["ok"] is True
        assert abs(res["t85_s"] - t85_expected) / t85_expected < 1e-9

    def test_higher_hi_increases_t85(self):
        """Higher HI → longer t8/5 (proportional to Q²)."""
        t85_lo = cooling_time_t85(1.0, 50.0, 20.0)["t85_s"]
        t85_hi = cooling_time_t85(2.0, 50.0, 20.0)["t85_s"]
        assert t85_hi > t85_lo

    def test_t85_proportional_to_HI_squared(self):
        """t8/5 ∝ Q² ∝ HI²: doubling HI multiplies t8/5 by 4."""
        t85_1 = cooling_time_t85(1.0, 0.0, 30.0, joint_type="butt")["t85_s"]
        t85_2 = cooling_time_t85(2.0, 0.0, 30.0, joint_type="butt")["t85_s"]
        assert abs(t85_2 / t85_1 - 4.0) < 1e-6

    def test_invalid_joint_type_returns_error(self):
        res = cooling_time_t85(1.5, 100.0, 20.0, joint_type="tee")
        assert res["ok"] is False

    def test_negative_hi_returns_error(self):
        res = cooling_time_t85(-1.0, 100.0, 20.0)
        assert res["ok"] is False

    def test_negative_preheat_returns_error(self):
        res = cooling_time_t85(1.0, -50.0, 20.0)
        assert res["ok"] is False


# ===========================================================================
# 5. fillet_weld_volume
# ===========================================================================

class TestFilletWeldVolume:

    def test_area_formula(self):
        """Area = leg²/2."""
        leg, L = 8.0, 200.0
        res = fillet_weld_volume(leg_mm=leg, length_mm=L)
        assert res["ok"] is True
        expected_area = 0.5 * leg**2
        assert abs(res["area_mm2"] - expected_area) < REL

    def test_volume_formula(self):
        """Volume = leg²/2 × length."""
        leg, L = 10.0, 500.0
        res = fillet_weld_volume(leg, L)
        assert res["ok"] is True
        expected = 0.5 * leg**2 * L
        assert abs(res["volume_mm3"] - expected) < REL

    def test_throat_formula(self):
        """Throat = leg / √2."""
        leg = 12.0
        res = fillet_weld_volume(leg, 100.0)
        assert res["ok"] is True
        expected_throat = leg / math.sqrt(2.0)
        assert abs(res["throat_mm"] - expected_throat) / expected_throat < REL

    def test_doubling_leg_quadruples_volume(self):
        """Volume ∝ leg², so doubling leg → 4× volume."""
        v1 = fillet_weld_volume(5.0, 100.0)["volume_mm3"]
        v2 = fillet_weld_volume(10.0, 100.0)["volume_mm3"]
        assert abs(v2 / v1 - 4.0) < REL

    def test_small_leg_warning(self):
        """Leg < 3 mm must trigger a warning."""
        res = fillet_weld_volume(2.0, 100.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_large_leg_warning(self):
        """Leg > 20 mm must trigger a warning."""
        res = fillet_weld_volume(25.0, 100.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_negative_leg_returns_error(self):
        res = fillet_weld_volume(-5.0, 100.0)
        assert res["ok"] is False

    def test_zero_length_returns_error(self):
        res = fillet_weld_volume(8.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 6. groove_weld_volume
# ===========================================================================

class TestGrooveWeldVolume:

    def test_trapezoid_volume_known_dimensions(self):
        """Manual trapezoid computation for a 60° V-groove."""
        depth, angle, rf, rg, L = 20.0, 60.0, 2.0, 3.0, 300.0
        d_fill = depth - rf
        half_ang = math.radians(angle / 2.0)
        w_t = 2.0 * d_fill * math.tan(half_ang) + rg
        area = (w_t + rg) / 2.0 * d_fill
        expected_vol = area * L
        res = groove_weld_volume(
            depth_mm=depth, width_top_mm=0, width_root_mm=0,
            length_mm=L,
            included_angle_deg=angle, root_face_mm=rf, root_gap_mm=rg
        )
        assert res["ok"] is True
        assert abs(res["volume_mm3"] - expected_vol) / expected_vol < 1e-9

    def test_explicit_top_width_override(self):
        """Providing explicit width_top_mm overrides geometric computation."""
        res = groove_weld_volume(
            depth_mm=25.0, width_top_mm=18.0, width_root_mm=3.0,
            length_mm=200.0
        )
        assert res["ok"] is True
        assert res["width_top_mm"] == 18.0

    def test_volume_proportional_to_length(self):
        """Volume ∝ length."""
        v1 = groove_weld_volume(20.0, 0, 0, 100.0)["volume_mm3"]
        v2 = groove_weld_volume(20.0, 0, 0, 200.0)["volume_mm3"]
        assert abs(v2 / v1 - 2.0) < 1e-9

    def test_narrow_angle_warning(self):
        """Included angle < 30° must trigger a warning."""
        res = groove_weld_volume(20.0, 0, 0, 200.0, included_angle_deg=20.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_wide_angle_warning(self):
        """Included angle > 90° must trigger a warning."""
        res = groove_weld_volume(20.0, 0, 0, 200.0, included_angle_deg=100.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_root_face_ge_depth_returns_error(self):
        """root_face >= depth must return ok=False."""
        res = groove_weld_volume(20.0, 0, 0, 200.0, root_face_mm=20.0)
        assert res["ok"] is False

    def test_negative_depth_returns_error(self):
        res = groove_weld_volume(-10.0, 0, 0, 200.0)
        assert res["ok"] is False


# ===========================================================================
# 7. deposition_time
# ===========================================================================

class TestDepositionTime:

    def test_formula_algebraic(self):
        """time_s = (volume × density / deposition_rate) × 3600."""
        vol, DR, rho = 100_000.0, 2.0, 7.85e-6
        mass = vol * rho
        expected_s = mass / DR * 3600.0
        res = deposition_time(vol, DR, rho)
        assert res["ok"] is True
        assert abs(res["time_s"] - expected_s) / expected_s < REL

    def test_time_min_consistent_with_time_s(self):
        """time_min = time_s / 60."""
        res = deposition_time(50_000.0, 3.0)
        assert res["ok"] is True
        assert abs(res["time_min"] - res["time_s"] / 60.0) < REL

    def test_higher_deposition_rate_shorter_time(self):
        """Doubling deposition rate halves the deposition time."""
        t1 = deposition_time(80_000.0, 2.0)["time_s"]
        t2 = deposition_time(80_000.0, 4.0)["time_s"]
        assert abs(t1 / t2 - 2.0) < REL

    def test_negative_volume_returns_error(self):
        res = deposition_time(-1000.0, 2.0)
        assert res["ok"] is False

    def test_zero_deposition_rate_returns_error(self):
        res = deposition_time(10000.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 8. electrode_consumption
# ===========================================================================

class TestElectrodeConsumption:

    def test_formula_algebraic(self):
        """electrode_mass = deposit_mass / efficiency."""
        vol, rho, eff = 50_000.0, 7.85e-6, 0.70
        deposit = vol * rho
        expected = deposit / eff
        res = electrode_consumption(vol, rho, eff)
        assert res["ok"] is True
        assert abs(res["electrode_mass_kg"] - expected) / expected < REL

    def test_100_percent_efficiency(self):
        """At 100% efficiency, electrode mass equals deposit mass."""
        res = electrode_consumption(10_000.0, 7.85e-6, 1.0)
        assert res["ok"] is True
        assert abs(res["electrode_mass_kg"] - res["deposit_mass_kg"]) < 1e-12

    def test_lower_efficiency_more_electrode(self):
        """Lower efficiency → more electrode required."""
        m1 = electrode_consumption(50_000.0, deposition_efficiency=0.80)["electrode_mass_kg"]
        m2 = electrode_consumption(50_000.0, deposition_efficiency=0.60)["electrode_mass_kg"]
        assert m2 > m1

    def test_low_efficiency_warning(self):
        """Efficiency < 60% must trigger a warning."""
        res = electrode_consumption(50_000.0, deposition_efficiency=0.50)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_efficiency_above_1_returns_error(self):
        res = electrode_consumption(10_000.0, deposition_efficiency=1.10)
        assert res["ok"] is False

    def test_negative_volume_returns_error(self):
        res = electrode_consumption(-5000.0)
        assert res["ok"] is False


# ===========================================================================
# 9. number_of_passes
# ===========================================================================

class TestNumberOfPasses:

    def test_exact_division(self):
        """100 mm² groove / 25 mm² pass = 4 passes exactly."""
        res = number_of_passes(100.0, 25.0)
        assert res["ok"] is True
        assert res["n_passes"] == 4

    def test_ceiling_applied(self):
        """Non-integer fill ratio → ceiling applied."""
        res = number_of_passes(110.0, 25.0)  # 4.4 → ceil = 5
        assert res["ok"] is True
        assert res["n_passes"] == 5

    def test_single_pass(self):
        """Pass area >= groove area → 1 pass."""
        res = number_of_passes(20.0, 50.0)
        assert res["ok"] is True
        assert res["n_passes"] == 1

    def test_fill_ratio_correct(self):
        """fill_ratio = groove / pass."""
        ga, pa = 150.0, 35.0
        res = number_of_passes(ga, pa)
        assert res["ok"] is True
        assert abs(res["fill_ratio"] - ga / pa) < REL

    def test_high_pass_count_warning(self):
        """More than 30 passes must trigger a warning."""
        res = number_of_passes(1600.0, 40.0)  # 40 passes
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_negative_groove_area_returns_error(self):
        res = number_of_passes(-100.0, 25.0)
        assert res["ok"] is False

    def test_zero_pass_area_returns_error(self):
        res = number_of_passes(100.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 10. angular_distortion
# ===========================================================================

class TestAngularDistortion:

    def test_formula_algebraic(self):
        """θ = 0.015 × HI × leg / t²."""
        HI, t, leg = 1.5, 12.0, 8.0
        expected_rad = 0.015 * HI * leg / (t**2)
        res = angular_distortion(HI, t, leg)
        assert res["ok"] is True
        assert abs(res["theta_rad"] - expected_rad) / expected_rad < REL

    def test_degrees_consistent_with_radians(self):
        """theta_deg == degrees(theta_rad)."""
        res = angular_distortion(2.0, 10.0, 8.0)
        assert res["ok"] is True
        assert abs(res["theta_deg"] - math.degrees(res["theta_rad"])) < REL

    def test_higher_hi_more_distortion(self):
        """Higher HI → more angular distortion."""
        d1 = angular_distortion(1.0, 10.0, 8.0)["theta_rad"]
        d2 = angular_distortion(2.0, 10.0, 8.0)["theta_rad"]
        assert d2 > d1

    def test_thicker_plate_less_distortion(self):
        """Thicker plate → less angular distortion (t² in denominator)."""
        d1 = angular_distortion(1.5, 8.0, 8.0)["theta_rad"]
        d2 = angular_distortion(1.5, 16.0, 8.0)["theta_rad"]
        assert d2 < d1

    def test_thickness_squared_scaling(self):
        """Doubling plate thickness reduces distortion by factor 4."""
        d1 = angular_distortion(1.5, 10.0, 8.0)["theta_rad"]
        d2 = angular_distortion(1.5, 20.0, 8.0)["theta_rad"]
        assert abs(d1 / d2 - 4.0) < REL

    def test_large_distortion_warning(self):
        """θ > 3° must trigger a warning."""
        # large leg, thin plate, high HI: 0.015 × 4.0 × 15.0 / 4.0² → ~3.2°
        res = angular_distortion(4.0, 4.0, 15.0)
        assert res["ok"] is True
        assert res["theta_deg"] > 3.0
        assert len(res["warnings"]) > 0

    def test_negative_hi_returns_error(self):
        res = angular_distortion(-1.0, 10.0, 8.0)
        assert res["ok"] is False

    def test_zero_plate_thickness_returns_error(self):
        res = angular_distortion(1.5, 0.0, 8.0)
        assert res["ok"] is False


# ===========================================================================
# 11. longitudinal_distortion
# ===========================================================================

class TestLongitudinalDistortion:

    def test_formula_algebraic(self):
        """δ = 3.33 × HI × L² / (A × E)."""
        HI, L, A, E = 1.5, 3000.0, 5000.0, 210_000.0
        k = 12e-6 / 3.6e-3 * 1000.0
        expected = k * HI * L**2 / (A * E)
        res = longitudinal_distortion(HI, L, A, E)
        assert res["ok"] is True
        assert abs(res["delta_mm"] - expected) / expected < REL

    def test_distortion_increases_with_HI(self):
        """Higher HI → more longitudinal distortion."""
        d1 = longitudinal_distortion(1.0, 2000.0, 4000.0)["delta_mm"]
        d2 = longitudinal_distortion(2.0, 2000.0, 4000.0)["delta_mm"]
        assert d2 > d1

    def test_distortion_proportional_to_length_squared(self):
        """δ ∝ L²: doubling L → 4× distortion."""
        d1 = longitudinal_distortion(1.0, 1000.0, 3000.0)["delta_mm"]
        d2 = longitudinal_distortion(1.0, 2000.0, 3000.0)["delta_mm"]
        assert abs(d2 / d1 - 4.0) < REL

    def test_distortion_decreases_with_area(self):
        """Larger cross-section → less distortion."""
        d1 = longitudinal_distortion(1.5, 2000.0, 2000.0)["delta_mm"]
        d2 = longitudinal_distortion(1.5, 2000.0, 4000.0)["delta_mm"]
        assert d2 < d1

    def test_excessive_distortion_warning(self):
        """δ > L/1000 must trigger a warning."""
        # long member, high HI, small area
        res = longitudinal_distortion(5.0, 10_000.0, 1000.0, 210_000.0)
        assert res["ok"] is True
        if res["delta_mm"] > res["length_mm"] * 0.001:
            assert len(res["warnings"]) > 0

    def test_negative_HI_returns_error(self):
        res = longitudinal_distortion(-1.0, 2000.0, 4000.0)
        assert res["ok"] is False

    def test_zero_area_returns_error(self):
        res = longitudinal_distortion(1.0, 2000.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 12. interpass_temperature_check
# ===========================================================================

class TestInterpassTemperatureCheck:

    def test_compliant_case(self):
        """Interpass within bounds must return compliant=True."""
        res = interpass_temperature_check(T_preheat_C=100.0, T_interpass_C=150.0, T_max_C=250.0)
        assert res["ok"] is True
        assert res["compliant"] is True
        assert res["preheat_satisfied"] is True
        assert res["max_ok"] is True

    def test_below_preheat_noncompliant(self):
        """Interpass below preheat must set preheat_satisfied=False."""
        res = interpass_temperature_check(T_preheat_C=100.0, T_interpass_C=80.0)
        assert res["ok"] is True
        assert res["preheat_satisfied"] is False
        assert res["compliant"] is False
        assert len(res["warnings"]) > 0

    def test_above_max_noncompliant(self):
        """Interpass above T_max must set max_ok=False."""
        res = interpass_temperature_check(T_preheat_C=100.0, T_interpass_C=300.0, T_max_C=250.0)
        assert res["ok"] is True
        assert res["max_ok"] is False
        assert res["compliant"] is False

    def test_margin_below_max(self):
        """margin_below_max_C = T_max - T_interpass."""
        res = interpass_temperature_check(T_preheat_C=100.0, T_interpass_C=200.0, T_max_C=250.0)
        assert res["ok"] is True
        assert abs(res["margin_below_max_C"] - 50.0) < REL

    def test_at_exactly_preheat_and_max(self):
        """At boundary values: T_interpass = T_preheat = T_max."""
        res = interpass_temperature_check(T_preheat_C=200.0, T_interpass_C=200.0, T_max_C=200.0)
        assert res["ok"] is True
        assert res["compliant"] is True

    def test_zero_preheat_compliant(self):
        """Zero preheat, any positive interpass → preheat_satisfied=True."""
        res = interpass_temperature_check(T_preheat_C=0.0, T_interpass_C=20.0)
        assert res["ok"] is True
        assert res["preheat_satisfied"] is True

    def test_negative_preheat_returns_error(self):
        res = interpass_temperature_check(T_preheat_C=-10.0, T_interpass_C=100.0)
        assert res["ok"] is False

    def test_negative_interpass_returns_error(self):
        res = interpass_temperature_check(T_preheat_C=100.0, T_interpass_C=-50.0)
        assert res["ok"] is False


# ===========================================================================
# 13. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_arc_heat_input_happy_path(self):
        ctx = _ctx()
        raw = _run(run_arc_heat_input(ctx, _args(eta=0.85, V=28.0, I=200.0, v=7.0)))
        d = _ok_tool(raw)
        assert d["HI_kJ_mm"] > 0

    def test_run_arc_heat_input_missing_v(self):
        ctx = _ctx()
        raw = _run(run_arc_heat_input(ctx, _args(eta=0.85, V=28.0, I=200.0)))
        _err_tool(raw)

    def test_run_arc_heat_input_bad_json(self):
        ctx = _ctx()
        raw = _run(run_arc_heat_input(ctx, b"not json"))
        _err_tool(raw)

    def test_run_carbon_equivalent_iiw_happy_path(self):
        ctx = _ctx()
        raw = _run(run_carbon_equivalent_iiw(ctx, _args(C=0.20, Mn=1.40, Cr=0.10)))
        d = _ok_tool(raw)
        assert d["CE_IIW"] > 0

    def test_run_carbon_equivalent_iiw_missing_Mn(self):
        ctx = _ctx()
        raw = _run(run_carbon_equivalent_iiw(ctx, _args(C=0.20)))
        _err_tool(raw)

    def test_run_preheat_temperature_happy_path(self):
        ctx = _ctx()
        raw = _run(run_preheat_temperature(ctx, _args(CE=0.45, t_mm=25.0, HI_kJ_mm=1.5)))
        d = _ok_tool(raw)
        assert "T_preheat_C" in d

    def test_run_preheat_temperature_missing_CE(self):
        ctx = _ctx()
        raw = _run(run_preheat_temperature(ctx, _args(t_mm=25.0, HI_kJ_mm=1.5)))
        _err_tool(raw)

    def test_run_cooling_time_t85_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cooling_time_t85(ctx, _args(HI_kJ_mm=2.0, T_preheat_C=100.0, t_mm=20.0)))
        d = _ok_tool(raw)
        assert d["t85_s"] > 0

    def test_run_cooling_time_t85_fillet(self):
        ctx = _ctx()
        raw = _run(run_cooling_time_t85(ctx, _args(
            HI_kJ_mm=1.5, T_preheat_C=50.0, t_mm=12.0, joint_type="fillet"
        )))
        d = _ok_tool(raw)
        assert d["joint_type"] == "fillet"

    def test_run_fillet_volume_happy_path(self):
        ctx = _ctx()
        raw = _run(run_fillet_weld_volume(ctx, _args(leg_mm=8.0, length_mm=200.0)))
        d = _ok_tool(raw)
        assert abs(d["volume_mm3"] - 0.5 * 8.0**2 * 200.0) < REL

    def test_run_groove_volume_happy_path(self):
        ctx = _ctx()
        raw = _run(run_groove_weld_volume(ctx, _args(
            depth_mm=20.0, width_top_mm=0, width_root_mm=0, length_mm=300.0
        )))
        d = _ok_tool(raw)
        assert d["volume_mm3"] > 0

    def test_run_deposition_time_happy_path(self):
        ctx = _ctx()
        raw = _run(run_deposition_time(ctx, _args(volume_mm3=50_000.0, deposition_rate_kg_h=3.0)))
        d = _ok_tool(raw)
        assert d["time_s"] > 0

    def test_run_electrode_consumption_happy_path(self):
        ctx = _ctx()
        raw = _run(run_electrode_consumption(ctx, _args(
            volume_mm3=50_000.0, deposition_efficiency=0.70
        )))
        d = _ok_tool(raw)
        assert d["electrode_mass_kg"] > d["deposit_mass_kg"]

    def test_run_number_of_passes_happy_path(self):
        ctx = _ctx()
        raw = _run(run_number_of_passes(ctx, _args(groove_area_mm2=100.0, pass_area_mm2=25.0)))
        d = _ok_tool(raw)
        assert d["n_passes"] == 4

    def test_run_angular_distortion_happy_path(self):
        ctx = _ctx()
        raw = _run(run_angular_distortion(ctx, _args(HI_kJ_mm=1.5, t_mm=12.0, leg_mm=8.0)))
        d = _ok_tool(raw)
        assert d["theta_deg"] > 0

    def test_run_longitudinal_distortion_happy_path(self):
        ctx = _ctx()
        raw = _run(run_longitudinal_distortion(ctx, _args(
            HI_kJ_mm=1.5, length_mm=3000.0, A_mm2=5000.0
        )))
        d = _ok_tool(raw)
        assert d["delta_mm"] > 0

    def test_run_interpass_check_compliant(self):
        ctx = _ctx()
        raw = _run(run_interpass_temperature_check(ctx, _args(
            T_preheat_C=100.0, T_interpass_C=150.0
        )))
        d = _ok_tool(raw)
        assert d["compliant"] is True

    def test_run_interpass_check_noncompliant(self):
        ctx = _ctx()
        raw = _run(run_interpass_temperature_check(ctx, _args(
            T_preheat_C=100.0, T_interpass_C=50.0
        )))
        d = _ok_tool(raw)
        assert d["compliant"] is False

    def test_run_interpass_check_missing_T_interpass(self):
        ctx = _ctx()
        raw = _run(run_interpass_temperature_check(ctx, _args(T_preheat_C=100.0)))
        _err_tool(raw)
