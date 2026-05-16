"""
Hermetic tests for kerf_cad_core.tank — API 650 atmospheric storage-tank design.

Coverage:
  api650.shell_course_thickness       — 1-foot & variable-design-point methods
  api650.minimum_shell_thickness      — Table 5-6a bands
  api650.bottom_plate_thickness       — §5.4 minimums
  api650.annular_plate_thickness      — §5.5 Table 5-1a pressure bands
  api650.cone_roof_thickness          — supported & self-supporting cone
  api650.dome_roof_thickness          — self-supporting dome
  api650.wind_girder_section_modulus  — §5.9.7.1 Z formula
  api650.intermediate_stiffener_spacing — §5.9.7.3 W_max formula
  api650.overturning_stability        — §5.11 overturning SF
  api650.anchorage_requirement        — §5.11.2 bolt area
  api650.seismic_annex_e              — Annex E Housner model
  api650.venting_normal               — API 2000 §4
  api650.venting_emergency            — API 2000 §5.3.2
  api650.settlement_check             — App. B limits
  api650.nozzle_reinforcement_note    — §5.7.3 area-replacement
  tools.*                             — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas verified algebraically against published API 650 hand-calcs.

References
----------
API Standard 650, 13th Edition, 2020
API Standard 2000, 7th Edition, 2014

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.tank.api650 import (
    shell_course_thickness,
    minimum_shell_thickness,
    bottom_plate_thickness,
    annular_plate_thickness,
    cone_roof_thickness,
    dome_roof_thickness,
    wind_girder_section_modulus,
    intermediate_stiffener_spacing,
    overturning_stability,
    anchorage_requirement,
    seismic_annex_e,
    venting_normal,
    venting_emergency,
    settlement_check,
    nozzle_reinforcement_note,
)
from kerf_cad_core.tank.tools import (
    run_tank_shell_course_thickness,
    run_tank_minimum_shell_thickness,
    run_tank_bottom_plate_thickness,
    run_tank_annular_plate_thickness,
    run_tank_cone_roof_thickness,
    run_tank_dome_roof_thickness,
    run_tank_wind_girder_section_modulus,
    run_tank_intermediate_stiffener,
    run_tank_overturning_stability,
    run_tank_anchorage_requirement,
    run_tank_seismic_annex_e,
    run_tank_venting_normal,
    run_tank_venting_emergency,
    run_tank_settlement_check,
    run_tank_nozzle_reinforcement,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

REL = 1e-6  # relative tolerance for floating-point checks


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


# ===========================================================================
# 1. shell_course_thickness — §5.6.3
# ===========================================================================

class TestShellCourseThickness:

    def test_1foot_algebraic_product_formula(self):
        """Verify t_d = 4900 D (H - 0.3) G / Sd algebraically.

        API 650 §5.6.3.1: t [mm] = 4.9 × D [m] × (H-x) [m] × G / Sd [MPa]
        In SI: t [m] = 4900 × D [m] × (H-x) [m] × G / Sd [Pa]
        Example: D=15, H-x=9.7, G=1, Sd=160 MPa → t = 4900×15×9.7/160e6 ≈ 4.45 mm ✓
        """
        D, H, G, Sd = 15.0, 10.0, 1.0, 160e6
        expected = 4900.0 * D * (H - 0.3) * G / Sd
        res = shell_course_thickness(D=D, H=H, G=G, Sd=Sd, c=0.0)
        assert res["ok"] is True
        assert abs(res["t_design_m"] - expected) / expected < REL

    def test_1foot_corrosion_allowance_added(self):
        """Corrosion allowance must be added on top of governing net thickness."""
        D, H, c = 15.0, 10.0, 0.003
        res0 = shell_course_thickness(D=D, H=H, c=0.0)
        res_c = shell_course_thickness(D=D, H=H, c=c)
        assert res_c["ok"] is True
        assert abs(res_c["t_required_m"] - res0["t_required_m"] - c) < 1e-12

    def test_hydrotest_governs_when_G_low(self):
        """With G < Sd/St the hydrotest formula governs (t_t = 4900DhG/Sd > t_d when G < Sd/St).

        t_t = 4900 D h / St
        t_d = 4900 D h G / Sd
        t_t > t_d  ⟺  1/St > G/Sd  ⟺  G < Sd/St ≈ 0.936
        """
        D, H, Sd, St = 15.0, 10.0, 160e6, 171e6
        G_threshold = Sd / St  # ≈ 0.936
        G_low = G_threshold * 0.99  # slightly below threshold → hydrotest governs
        res = shell_course_thickness(D=D, H=H, G=G_low, Sd=Sd, St=St, c=0.0)
        assert res["ok"] is True
        assert res["governing"] == "hydrotest"

    def test_product_governs_when_G_high(self):
        """G = 1.1 > Sd/St → product formula governs."""
        res = shell_course_thickness(D=15.0, H=10.0, G=1.1, Sd=160e6, St=171e6, c=0.0)
        assert res["ok"] is True
        assert res["governing"] == "product"

    def test_variable_method_x0_equals_1foot_at_0_3(self):
        """variable method with x=0.3 should give the same result as 1-foot."""
        D, H, G, Sd = 20.0, 12.0, 1.0, 160e6
        r1 = shell_course_thickness(D=D, H=H, G=G, Sd=Sd, c=0.0, method="1-foot")
        rv = shell_course_thickness(D=D, H=H, G=G, Sd=Sd, c=0.0, method="variable", x=0.3)
        assert rv["ok"] is True
        assert abs(rv["t_design_m"] - r1["t_design_m"]) / r1["t_design_m"] < REL

    def test_variable_x_zero_gives_maximum_thickness(self):
        """x=0 (bottom of course) gives maximum shell thickness for variable method."""
        D, H = 15.0, 10.0
        r_0 = shell_course_thickness(D=D, H=H, method="variable", x=0.0)
        r_1 = shell_course_thickness(D=D, H=H, method="variable", x=1.0)
        assert r_0["t_design_m"] > r_1["t_design_m"]

    def test_t_required_mm_consistent(self):
        """t_required_mm == t_required_m × 1000."""
        res = shell_course_thickness(D=20.0, H=15.0)
        assert abs(res["t_required_mm"] - res["t_required_m"] * 1e3) < 1e-10

    def test_negative_D_returns_error(self):
        res = shell_course_thickness(D=-5.0, H=10.0)
        assert res["ok"] is False

    def test_variable_x_ge_H_returns_error(self):
        res = shell_course_thickness(D=10.0, H=5.0, method="variable", x=5.0)
        assert res["ok"] is False

    def test_unknown_method_returns_error(self):
        res = shell_course_thickness(D=10.0, H=5.0, method="bogus")
        assert res["ok"] is False


# ===========================================================================
# 2. minimum_shell_thickness — Table 5-6a
# ===========================================================================

class TestMinimumShellThickness:

    def test_small_tank_5mm(self):
        """D ≤ 15 m → 5 mm."""
        res = minimum_shell_thickness(D=10.0)
        assert res["ok"] is True
        assert res["t_min_mm"] == pytest.approx(5.0)

    def test_medium_tank_6mm(self):
        """15 < D ≤ 30 m → 6 mm."""
        res = minimum_shell_thickness(D=20.0)
        assert res["ok"] is True
        assert res["t_min_mm"] == pytest.approx(6.0)

    def test_large_tank_8mm(self):
        """30 < D ≤ 60 m → 8 mm."""
        res = minimum_shell_thickness(D=45.0)
        assert res["ok"] is True
        assert res["t_min_mm"] == pytest.approx(8.0)

    def test_very_large_tank_10mm(self):
        """D > 60 m → 10 mm."""
        res = minimum_shell_thickness(D=80.0)
        assert res["ok"] is True
        assert res["t_min_mm"] == pytest.approx(10.0)

    def test_zero_D_returns_error(self):
        res = minimum_shell_thickness(D=0.0)
        assert res["ok"] is False


# ===========================================================================
# 3. bottom_plate_thickness — §5.4
# ===========================================================================

class TestBottomPlateThickness:

    def test_minimum_6mm_net(self):
        """API 650 §5.4.1 minimum is 6 mm net."""
        res = bottom_plate_thickness()
        assert res["ok"] is True
        assert res["t_min_net_mm"] == pytest.approx(6.0)

    def test_corrosion_allowance_added(self):
        """t_required_m = 6 mm + CA."""
        c = 0.003
        res = bottom_plate_thickness(c=c)
        assert res["ok"] is True
        assert abs(res["t_required_m"] - (0.006 + c)) < 1e-12

    def test_negative_c_returns_error(self):
        res = bottom_plate_thickness(c=-0.001)
        assert res["ok"] is False

    def test_large_ca_warning_without_liner(self):
        """CA > 3 mm without liner should produce a warning."""
        res = bottom_plate_thickness(c=0.005)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_large_ca_no_warning_with_liner(self):
        """CA > 3 mm with liner — warning suppressed."""
        res = bottom_plate_thickness(c=0.005, has_liner=True)
        assert res["ok"] is True
        assert len(res["warnings"]) == 0


# ===========================================================================
# 4. annular_plate_thickness — §5.5
# ===========================================================================

class TestAnnularPlateThickness:

    def test_min_6mm_low_pressure(self):
        """Low liquid head → minimum 6 mm annular plate."""
        res = annular_plate_thickness(D=10.0, H=2.0, G=0.85)
        assert res["ok"] is True
        assert res["t_annular_net_mm"] >= 6.0

    def test_higher_pressure_gives_thicker_plate(self):
        """Taller tank / heavier product → thicker annular plate."""
        r_low = annular_plate_thickness(D=10.0, H=2.0, G=1.0)
        r_high = annular_plate_thickness(D=20.0, H=20.0, G=1.0)
        assert r_high["t_annular_net_mm"] >= r_low["t_annular_net_mm"]

    def test_min_projection_600mm(self):
        """Annular plate minimum projection must be 600 mm."""
        res = annular_plate_thickness(D=15.0, H=10.0)
        assert res["ok"] is True
        assert res["min_projection_mm"] == pytest.approx(600.0)

    def test_zero_D_returns_error(self):
        res = annular_plate_thickness(D=0.0, H=10.0)
        assert res["ok"] is False


# ===========================================================================
# 5. cone_roof_thickness — §5.10.5.1
# ===========================================================================

class TestConeRoofThickness:

    def test_supported_cone_minimum_5mm(self):
        """Supported cone: minimum net thickness is 5 mm."""
        res = cone_roof_thickness(D=20.0, self_supporting=False)
        assert res["ok"] is True
        assert res["t_required_m"] >= 5e-3

    def test_self_supporting_formula(self):
        """Self-supporting cone: t = N_m / (Sd × E) ≥ 5 mm."""
        D, theta_deg, w, Sd = 20.0, 15.0, 1200.0, 160e6
        theta_r = math.radians(theta_deg)
        N_m = w * D / (4.0 * math.sin(theta_r))
        t_calc = N_m / Sd
        res = cone_roof_thickness(D=D, theta_deg=theta_deg, design_load_Pa=w, Sd=Sd,
                                   self_supporting=True, c=0.0)
        assert res["ok"] is True
        assert abs(res["t_calc_m"] - t_calc) / max(t_calc, 1e-12) < REL

    def test_corrosion_allowance_added_cone(self):
        """CA is added to the governing net thickness."""
        c = 0.003
        r0 = cone_roof_thickness(D=20.0, c=0.0)
        rc = cone_roof_thickness(D=20.0, c=c)
        assert abs(rc["t_required_m"] - r0["t_required_m"] - c) < 1e-12

    def test_angle_out_of_range_returns_error(self):
        """theta_deg < 9.46° → error."""
        res = cone_roof_thickness(D=20.0, theta_deg=5.0)
        assert res["ok"] is False

    def test_frangible_joint_supported_cone(self):
        """Supported cone < 37° → frangible_joint is True."""
        res = cone_roof_thickness(D=20.0, theta_deg=15.0, self_supporting=False)
        assert res["ok"] is True
        assert res["frangible_joint"] is True

    def test_frangible_joint_self_supporting_false(self):
        """Self-supporting cone → frangible_joint is False."""
        res = cone_roof_thickness(D=20.0, self_supporting=True)
        assert res["ok"] is True
        assert res["frangible_joint"] is False


# ===========================================================================
# 6. dome_roof_thickness — §5.10.5.2
# ===========================================================================

class TestDomeRoofThickness:

    def test_membrane_formula_algebraic(self):
        """t_calc = w * Rc / (2 * Sd * E)."""
        D, w, Sd, E = 20.0, 1200.0, 160e6, 1.0
        Rc = 0.8 * D
        expected = w * Rc / (2.0 * Sd * E)
        res = dome_roof_thickness(D=D, design_load_Pa=w, Sd=Sd, E_joint=E, c=0.0)
        assert res["ok"] is True
        assert abs(res["t_calc_m"] - expected) / max(expected, 1e-12) < REL

    def test_default_Rc_is_0_8_D(self):
        """Default crown radius must be 0.8 × D."""
        D = 25.0
        res = dome_roof_thickness(D=D)
        assert res["ok"] is True
        assert abs(res["Rc_m"] - 0.8 * D) < 1e-12

    def test_minimum_5mm_dome(self):
        """Result must never go below 5 mm (API 650 §5.10.5.2 minimum)."""
        res = dome_roof_thickness(D=5.0, design_load_Pa=100.0)
        assert res["ok"] is True
        assert res["t_required_m"] >= 5e-3

    def test_Rc_out_of_range_warning(self):
        """Rc > 1.5 D should trigger a warning."""
        res = dome_roof_thickness(D=10.0, Rc=20.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_t_mm_consistent(self):
        """t_required_mm == t_required_m × 1000."""
        res = dome_roof_thickness(D=15.0)
        assert abs(res["t_required_mm"] - res["t_required_m"] * 1e3) < 1e-10


# ===========================================================================
# 7. wind_girder_section_modulus — §5.9.7
# ===========================================================================

class TestWindGirderSectionModulus:

    def test_algebraic_formula(self):
        """Z = 0.0001 D² H (V/190)² with V in km/h."""
        D, H, V_ms = 15.0, 12.0, 45.0
        V_kmh = V_ms * 3.6
        expected_Z = 0.0001 * D**2 * H * (V_kmh / 190.0)**2
        res = wind_girder_section_modulus(D=D, t_shell=0.006, V_wind_m_s=V_ms, H_shell=H)
        assert res["ok"] is True
        assert abs(res["Z_required_m3"] - expected_Z) / expected_Z < REL

    def test_Z_cm3_consistent(self):
        """Z_required_cm3 == Z_required_m3 × 1e6."""
        res = wind_girder_section_modulus(D=20.0, t_shell=0.008)
        assert abs(res["Z_required_cm3"] - res["Z_required_m3"] * 1e6) < 1e-9

    def test_higher_wind_requires_larger_Z(self):
        """Z ∝ V²; doubling V quadruples Z."""
        D, H, t = 15.0, 12.0, 0.006
        r1 = wind_girder_section_modulus(D=D, t_shell=t, V_wind_m_s=30.0, H_shell=H)
        r2 = wind_girder_section_modulus(D=D, t_shell=t, V_wind_m_s=60.0, H_shell=H)
        ratio = r2["Z_required_m3"] / r1["Z_required_m3"]
        assert abs(ratio - 4.0) / 4.0 < REL

    def test_zero_D_returns_error(self):
        res = wind_girder_section_modulus(D=0.0, t_shell=0.006)
        assert res["ok"] is False


# ===========================================================================
# 8. intermediate_stiffener_spacing — §5.9.7.3
# ===========================================================================

class TestIntermediateStiffenerSpacing:

    def test_W_max_formula(self):
        """W_max = (9.47 t (190/V))^(1/3) with V in km/h."""
        D, t, H, V_ms = 15.0, 0.006, 12.0, 45.0
        V_kmh = V_ms * 3.6
        expected_W = (9.47 * t * (190.0 / V_kmh)) ** (1.0 / 3.0)
        res = intermediate_stiffener_spacing(D=D, t_shell=t, H_shell=H, V_wind_m_s=V_ms)
        assert res["ok"] is True
        assert abs(res["W_max_m"] - expected_W) / expected_W < REL

    def test_short_tank_needs_no_stiffeners(self):
        """A tank shorter than W_max needs 0 intermediate stiffeners.

        At V=45 m/s, t=6 mm: W_max ≈ 0.405 m.  Use H_shell=0.3 m < W_max.
        """
        res = intermediate_stiffener_spacing(D=15.0, t_shell=0.006, H_shell=0.3)
        assert res["ok"] is True
        assert res["n_stiffeners_min"] == 0

    def test_tall_thin_tank_needs_stiffeners(self):
        """A tall, thin-walled tank at high wind must require ≥ 1 stiffener."""
        res = intermediate_stiffener_spacing(D=30.0, t_shell=0.005, H_shell=20.0,
                                              V_wind_m_s=55.0)
        assert res["ok"] is True
        assert res["n_stiffeners_min"] >= 1

    def test_spacing_le_W_max(self):
        """Actual spacing must always be ≤ W_max."""
        res = intermediate_stiffener_spacing(D=20.0, t_shell=0.006, H_shell=15.0)
        assert res["ok"] is True
        assert res["spacing_actual_m"] <= res["W_max_m"] + 1e-9


# ===========================================================================
# 9. overturning_stability — §5.11
# ===========================================================================

class TestOverturningStability:

    def test_heavy_tank_stable_sf_ge_1_5(self):
        """A very heavy tank should have SF ≥ 1.5 (no anchorage needed)."""
        res = overturning_stability(D=15.0, H_shell=12.0, W_total_N=5e6)
        assert res["ok"] is True
        assert res["SF_overturning"] >= 1.5
        assert res["overturning_ok"] is True

    def test_light_tank_in_high_wind_overturns(self):
        """A light tank in extreme wind must fail stability check (SF < 1.5)."""
        res = overturning_stability(D=10.0, H_shell=10.0, W_total_N=50_000.0,
                                     V_wind_m_s=55.0)
        assert res["ok"] is True
        assert res["overturning_ok"] is False
        assert len(res["warnings"]) > 0

    def test_liquid_increases_stability(self):
        """Adding liquid (H_liquid_m > 0) must increase SF."""
        kwargs = dict(D=15.0, H_shell=12.0, W_total_N=500_000.0, V_wind_m_s=45.0)
        r_empty = overturning_stability(**kwargs, H_liquid_m=0.0)
        r_full = overturning_stability(**kwargs, H_liquid_m=11.0)
        assert r_full["SF_overturning"] > r_empty["SF_overturning"]

    def test_M_wind_formula(self):
        """M_wind = 0.5 ρ V² Cf D H × H/2."""
        D, H, V, Cf = 15.0, 12.0, 45.0, 0.7
        rho = 1.225
        q = 0.5 * rho * V**2
        expected_M = q * Cf * D * H * H / 2.0
        res = overturning_stability(D=D, H_shell=H, W_total_N=1e6, V_wind_m_s=V, Cf=Cf)
        assert res["ok"] is True
        assert abs(res["M_wind_Nm"] - expected_M) / expected_M < REL

    def test_invalid_Cf_returns_error(self):
        res = overturning_stability(D=15.0, H_shell=12.0, W_total_N=1e6, Cf=3.0)
        assert res["ok"] is False


# ===========================================================================
# 10. anchorage_requirement — §5.11.2
# ===========================================================================

class TestAnchorageRequirement:

    def test_no_uplift_zero_area(self):
        """When resisting moment > overturning moment, no anchor bolts needed."""
        D, M, W = 15.0, 100_000.0, 5_000_000.0
        res = anchorage_requirement(D=D, M_overturning_Nm=M, W_shell_N=W)
        assert res["ok"] is True
        assert res["anchors_required"] is False
        assert res["A_bolt_required_m2"] == 0.0

    def test_uplift_bolt_area_formula(self):
        """A_bolt = F_per_bolt / sigma_allow with F = (2M/D - W) / n_bolts."""
        D, M, W = 15.0, 10_000_000.0, 500_000.0
        n = 16
        SF = 2.0
        sigma_allow_A307 = 124e6 / SF
        F_uplift = 2.0 * M / D - W
        F_per_bolt = F_uplift / n
        A_req = F_per_bolt / sigma_allow_A307
        res = anchorage_requirement(D=D, M_overturning_Nm=M, W_shell_N=W,
                                     n_bolts=n, bolt_grade="A307", safety_factor=SF)
        assert res["ok"] is True
        assert res["anchors_required"] is True
        assert abs(res["A_bolt_required_m2"] - A_req) / A_req < REL

    def test_invalid_bolt_grade_returns_error(self):
        res = anchorage_requirement(D=15.0, M_overturning_Nm=1e6, W_shell_N=1e6,
                                     bolt_grade="Z999")
        assert res["ok"] is False

    def test_n_bolts_lt_4_returns_error(self):
        res = anchorage_requirement(D=15.0, M_overturning_Nm=1e6, W_shell_N=1e6,
                                     n_bolts=2)
        assert res["ok"] is False


# ===========================================================================
# 11. seismic_annex_e — Annex E
# ===========================================================================

class TestSeismicAnnexE:

    def test_mass_fractions_sum_to_total(self):
        """m_imp + m_conv must equal m_total."""
        res = seismic_annex_e(D=15.0, H_liquid=10.0)
        assert res["ok"] is True
        assert abs(res["m_imp_kg"] + res["m_conv_kg"] - res["m_total_kg"]) / res["m_total_kg"] < 1e-10

    def test_total_liquid_mass_formula(self):
        """m_total = ρ × π/4 × D² × H."""
        D, H, rho = 15.0, 10.0, 850.0
        expected = rho * math.pi / 4.0 * D**2 * H
        res = seismic_annex_e(D=D, H_liquid=H, rho_liquid=rho)
        assert res["ok"] is True
        assert abs(res["m_total_kg"] - expected) / expected < REL

    def test_V_total_srss(self):
        """V_total = sqrt(V_imp² + V_conv²)."""
        res = seismic_annex_e(D=15.0, H_liquid=10.0)
        assert res["ok"] is True
        expected = math.sqrt(res["V_imp_N"]**2 + res["V_conv_N"]**2)
        assert abs(res["V_total_N"] - expected) / max(expected, 1.0) < REL

    def test_M_total_srss(self):
        """M_total = sqrt(M_imp² + M_conv²)."""
        res = seismic_annex_e(D=15.0, H_liquid=10.0)
        assert res["ok"] is True
        expected = math.sqrt(res["M_imp_Nm"]**2 + res["M_conv_Nm"]**2)
        assert abs(res["M_total_Nm"] - expected) / max(expected, 1.0) < REL

    def test_freeboard_equals_delta_s(self):
        """freeboard_required_m must equal delta_s_m."""
        res = seismic_annex_e(D=20.0, H_liquid=15.0, Sds=1.0)
        assert res["ok"] is True
        assert abs(res["freeboard_required_m"] - res["delta_s_m"]) < 1e-12

    def test_zero_seismic_gives_zero_shear(self):
        """With Sds=0 and Sd1=0 base shear must be zero."""
        res = seismic_annex_e(D=15.0, H_liquid=10.0, Sds=0.0, Sd1=0.0)
        assert res["ok"] is True
        assert res["V_total_N"] == pytest.approx(0.0, abs=1.0)

    def test_high_sloshing_warning(self):
        """High Sds (1.5g) → large sloshing → inadequate freeboard warning."""
        res = seismic_annex_e(D=30.0, H_liquid=5.0, Sds=1.5, Sd1=0.6)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0


# ===========================================================================
# 12. venting_normal — API 2000 §4
# ===========================================================================

class TestVentingNormal:

    def test_breathing_rate_formula(self):
        """Vb = 0.1 × V_tank."""
        V = 500.0
        res = venting_normal(V_tank_m3=V)
        assert res["ok"] is True
        assert abs(res["V_breathing_m3_h"] - 0.1 * V) / (0.1 * V) < REL

    def test_fill_rate_contributes_to_in_breathing(self):
        """V_total_in = Vb + fill_rate × 3600."""
        V, fill = 200.0, 0.05
        res = venting_normal(V_tank_m3=V, fill_rate_m3_s=fill)
        assert res["ok"] is True
        expected = 0.1 * V + fill * 3600.0
        assert abs(res["V_total_in_m3_h"] - expected) / expected < REL

    def test_class_I_flag(self):
        """Flash point < 37.8°C → class_I_service = True."""
        res = venting_normal(V_tank_m3=100.0, flash_point_C=30.0)
        assert res["ok"] is True
        assert res["class_I_service"] is True
        assert len(res["warnings"]) > 0

    def test_class_II_no_flag(self):
        """Flash point ≥ 37.8°C → class_I_service = False."""
        res = venting_normal(V_tank_m3=100.0, flash_point_C=60.0)
        assert res["ok"] is True
        assert res["class_I_service"] is False

    def test_large_tank_warning(self):
        """V > 56,800 m³ → warning about simplified formula."""
        res = venting_normal(V_tank_m3=60_000.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0


# ===========================================================================
# 13. venting_emergency — API 2000 §5.3.2
# ===========================================================================

class TestVentingEmergency:

    def test_Q_fire_formula_direct(self):
        """Q_fire = 3.091 × A_w^0.82 with explicit wetted_area_m2."""
        A_w = 100.0
        res = venting_emergency(V_tank_m3=500.0, wetted_area_m2=A_w)
        assert res["ok"] is True
        expected = 3.091 * A_w ** 0.82
        assert abs(res["Q_emergency_m3_h"] - expected) / expected < REL

    def test_Q_fire_computed_from_D_and_H(self):
        """Compute wetted area from D and H_liquid; max height 9.14 m."""
        D, H = 15.0, 12.0
        H_wet = min(H, 9.14)
        A_w = math.pi * D * H_wet + math.pi / 4.0 * D**2
        expected = 3.091 * A_w ** 0.82
        res = venting_emergency(V_tank_m3=500.0, D=D, H_liquid=H)
        assert res["ok"] is True
        assert abs(res["Q_emergency_m3_h"] - expected) / expected < REL

    def test_missing_wetted_area_and_D_H_returns_error(self):
        """Neither wetted_area_m2 nor D+H_liquid → error."""
        res = venting_emergency(V_tank_m3=500.0)
        assert res["ok"] is False

    def test_large_wetted_area_warning(self):
        """A_w > 260 m² → environment factor warning."""
        res = venting_emergency(V_tank_m3=1000.0, wetted_area_m2=300.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0


# ===========================================================================
# 14. settlement_check — Appendix B
# ===========================================================================

class TestSettlementCheck:

    def test_all_zero_settlement_passes(self):
        """No settlement → all checks pass."""
        res = settlement_check(D=20.0)
        assert res["ok"] is True
        assert res["overall_ok"] is True

    def test_edge_limit_formula(self):
        """Edge limit = D [m] × 10 mm/m."""
        D = 20.0
        res = settlement_check(D=D, S_edge_mm=D * 10.0 - 0.01)
        assert res["ok"] is True
        assert res["edge_ok"] is True

    def test_edge_settlement_exceeds_limit(self):
        """S_edge above limit → edge_ok = False, warning issued."""
        D = 20.0
        res = settlement_check(D=D, S_edge_mm=D * 10.0 + 1.0)
        assert res["ok"] is True
        assert res["edge_ok"] is False
        assert res["overall_ok"] is False
        assert any("edge" in w.lower() or "SETTLEMENT" in w for w in res["warnings"])

    def test_differential_limit_scales_with_arc(self):
        """Differential limit = 13 mm × arc_deg / 10."""
        arc = 20.0
        expected = 13.0 * arc / 10.0
        res = settlement_check(D=15.0, measurement_arc_deg=arc)
        assert abs(res["diff_limit_mm"] - expected) < 1e-10

    def test_differential_over_limit(self):
        """S_diff > limit → diff_ok = False."""
        res = settlement_check(D=15.0, S_diff_max_mm=50.0, measurement_arc_deg=10.0)
        assert res["ok"] is True
        assert res["diff_ok"] is False

    def test_zero_D_returns_error(self):
        res = settlement_check(D=0.0)
        assert res["ok"] is False


# ===========================================================================
# 15. nozzle_reinforcement_note — §5.7
# ===========================================================================

class TestNozzleReinforcementNote:

    def test_well_reinforced_nozzle_passes(self):
        """Thick nozzle in a thick shell must pass the area check."""
        res = nozzle_reinforcement_note(
            D_shell=15.0, t_shell=0.020, d_nozzle=0.2, t_nozzle=0.012, H=8.0
        )
        assert res["ok"] is True
        assert res["reinforcement_ok"] is True
        assert res["A_total_m2"] >= res["A_required_m2"]

    def test_undersized_nozzle_fails(self):
        """Large thin nozzle in a thin shell must fail the area check."""
        res = nozzle_reinforcement_note(
            D_shell=15.0, t_shell=0.006, d_nozzle=0.8, t_nozzle=0.004, H=10.0
        )
        assert res["ok"] is True
        assert res["reinforcement_ok"] is False
        assert res["shortfall_m2"] > 0
        assert len(res["warnings"]) > 0

    def test_A_required_formula(self):
        """A_required = d_nozzle × t_req_shell.

        t_req [m] = 4900 × D [m] × H [m] × G / Sd [Pa]  (API 650 §5.6.3 SI)
        """
        D_s, t_s, d_n, t_n, H = 15.0, 0.015, 0.3, 0.010, 8.0
        Sd = 160e6
        t_req = 4900.0 * D_s * H / Sd  # G defaults to 1.0
        A_req = d_n * t_req
        res = nozzle_reinforcement_note(D_shell=D_s, t_shell=t_s, d_nozzle=d_n,
                                         t_nozzle=t_n, H=H, Sd=Sd)
        assert res["ok"] is True
        assert abs(res["A_required_m2"] - A_req) / max(A_req, 1e-12) < REL

    def test_zero_shell_thickness_returns_error(self):
        res = nozzle_reinforcement_note(D_shell=15.0, t_shell=0.0, d_nozzle=0.2,
                                         t_nozzle=0.010, H=5.0)
        assert res["ok"] is False


# ===========================================================================
# 16. LLM tool wrappers (run_tank_*)
# ===========================================================================

class TestToolWrappers:

    def test_shell_course_happy_path(self):
        ctx = _ctx()
        raw = _run(run_tank_shell_course_thickness(ctx, _args(D=15.0, H=10.0, G=1.0)))
        d = _ok_tool(raw)
        assert d["t_required_m"] > 0
        assert d["t_required_mm"] > 0

    def test_shell_course_missing_H(self):
        ctx = _ctx()
        raw = _run(run_tank_shell_course_thickness(ctx, _args(D=15.0)))
        _err_tool(raw)

    def test_shell_course_bad_json(self):
        ctx = _ctx()
        raw = _run(run_tank_shell_course_thickness(ctx, b"NOT JSON"))
        _err_tool(raw)

    def test_min_thickness_happy_path(self):
        ctx = _ctx()
        raw = _run(run_tank_minimum_shell_thickness(ctx, _args(D=20.0)))
        d = _ok_tool(raw)
        assert d["t_min_mm"] == pytest.approx(6.0)

    def test_min_thickness_missing_D(self):
        ctx = _ctx()
        raw = _run(run_tank_minimum_shell_thickness(ctx, _args()))
        _err_tool(raw)

    def test_bottom_plate_happy_path(self):
        ctx = _ctx()
        raw = _run(run_tank_bottom_plate_thickness(ctx, _args(c=0.003)))
        d = _ok_tool(raw)
        assert d["t_required_mm"] == pytest.approx(9.0)

    def test_annular_happy_path(self):
        ctx = _ctx()
        raw = _run(run_tank_annular_plate_thickness(ctx, _args(D=20.0, H=10.0)))
        d = _ok_tool(raw)
        assert d["t_annular_net_mm"] >= 6.0

    def test_annular_missing_D(self):
        ctx = _ctx()
        raw = _run(run_tank_annular_plate_thickness(ctx, _args(H=10.0)))
        _err_tool(raw)

    def test_cone_roof_happy_path(self):
        ctx = _ctx()
        raw = _run(run_tank_cone_roof_thickness(ctx, _args(D=20.0)))
        d = _ok_tool(raw)
        assert d["t_required_mm"] >= 5.0

    def test_dome_roof_happy_path(self):
        ctx = _ctx()
        raw = _run(run_tank_dome_roof_thickness(ctx, _args(D=20.0)))
        d = _ok_tool(raw)
        assert d["t_required_mm"] >= 5.0
        assert d["Rc_m"] == pytest.approx(16.0)

    def test_wind_girder_happy_path(self):
        ctx = _ctx()
        raw = _run(run_tank_wind_girder_section_modulus(
            ctx, _args(D=15.0, t_shell=0.006, H_shell=12.0)))
        d = _ok_tool(raw)
        assert d["Z_required_m3"] > 0

    def test_wind_girder_missing_t_shell(self):
        ctx = _ctx()
        raw = _run(run_tank_wind_girder_section_modulus(ctx, _args(D=15.0)))
        _err_tool(raw)

    def test_intermediate_stiffener_happy_path(self):
        ctx = _ctx()
        raw = _run(run_tank_intermediate_stiffener(
            ctx, _args(D=20.0, t_shell=0.006, H_shell=15.0)))
        d = _ok_tool(raw)
        assert d["W_max_m"] > 0

    def test_overturning_happy_path(self):
        ctx = _ctx()
        raw = _run(run_tank_overturning_stability(
            ctx, _args(D=15.0, H_shell=12.0, W_total_N=5e6)))
        d = _ok_tool(raw)
        assert d["SF_overturning"] > 0
        assert isinstance(d["overturning_ok"], bool)

    def test_anchorage_happy_path_no_uplift(self):
        ctx = _ctx()
        raw = _run(run_tank_anchorage_requirement(
            ctx, _args(D=15.0, M_overturning_Nm=100_000.0, W_shell_N=5_000_000.0)))
        d = _ok_tool(raw)
        assert d["anchors_required"] is False

    def test_seismic_happy_path(self):
        ctx = _ctx()
        raw = _run(run_tank_seismic_annex_e(ctx, _args(D=15.0, H_liquid=10.0)))
        d = _ok_tool(raw)
        assert d["m_total_kg"] > 0
        assert d["V_total_N"] >= 0

    def test_seismic_missing_H_liquid(self):
        ctx = _ctx()
        raw = _run(run_tank_seismic_annex_e(ctx, _args(D=15.0)))
        _err_tool(raw)

    def test_venting_normal_happy_path(self):
        ctx = _ctx()
        raw = _run(run_tank_venting_normal(ctx, _args(V_tank_m3=500.0)))
        d = _ok_tool(raw)
        assert d["V_total_out_m3_h"] > 0

    def test_venting_emergency_happy_path_wetted_area(self):
        ctx = _ctx()
        raw = _run(run_tank_venting_emergency(
            ctx, _args(V_tank_m3=500.0, wetted_area_m2=100.0)))
        d = _ok_tool(raw)
        assert d["Q_emergency_m3_h"] > 0

    def test_venting_emergency_from_D_H(self):
        ctx = _ctx()
        raw = _run(run_tank_venting_emergency(
            ctx, _args(V_tank_m3=500.0, D=10.0, H_liquid=8.0)))
        d = _ok_tool(raw)
        assert d["Q_emergency_m3_h"] > 0

    def test_settlement_happy_path(self):
        ctx = _ctx()
        raw = _run(run_tank_settlement_check(ctx, _args(D=20.0)))
        d = _ok_tool(raw)
        assert d["overall_ok"] is True

    def test_settlement_failing(self):
        ctx = _ctx()
        raw = _run(run_tank_settlement_check(
            ctx, _args(D=20.0, S_edge_mm=10000.0)))
        d = _ok_tool(raw)
        assert d["edge_ok"] is False

    def test_nozzle_happy_path(self):
        ctx = _ctx()
        raw = _run(run_tank_nozzle_reinforcement(ctx, _args(
            D_shell=15.0, t_shell=0.020, d_nozzle=0.2, t_nozzle=0.012, H=8.0
        )))
        d = _ok_tool(raw)
        assert isinstance(d["reinforcement_ok"], bool)

    def test_nozzle_missing_H(self):
        ctx = _ctx()
        raw = _run(run_tank_nozzle_reinforcement(ctx, _args(
            D_shell=15.0, t_shell=0.020, d_nozzle=0.2, t_nozzle=0.012
        )))
        _err_tool(raw)
