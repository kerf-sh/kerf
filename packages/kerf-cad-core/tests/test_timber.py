"""
Hermetic tests for kerf_cad_core.timber — NDS allowable-stress timber design.

Coverage:
  design.CD_load_duration         — tabulated CD values
  design.CM_wet                   — wet-service factors for sawn/glulam
  design.Ct_temp                  — temperature factors
  design.CL_beam_stability        — Ylinen beam stability factor
  design.CF_size                  — size factor for sawn lumber
  design.Cfu_flat_use             — flat-use factor
  design.Ci_incising              — incising factor
  design.Cr_repetitive            — repetitive-member factor
  design.CP_column_stability      — Ylinen column stability factor
  design.FcE_critical             — Euler critical buckling stress
  design.Cb_bearing_area          — bearing area factor
  design.sawn_section             — dressed section properties
  design.glulam_section           — glulam section properties
  design.adjusted_Fb/Fv/Fc/...   — adjusted design values
  design.bending_stress           — fb = M/S
  design.shear_stress             — fv = 1.5V/A
  design.check_bending            — fb <= Fb'
  design.check_shear              — fv <= Fv'
  design.check_deflection         — L/360 / L/240 limits
  design.check_compression_column — fc <= Fc'
  design.check_combined_bending_axial — NDS §3.9.2 interaction
  design.check_bearing            — fc_perp <= Fc_perp'
  design.lateral_yield_bolt       — NDS yield modes Im/Is/II/IIIm/IIIs/IV
  design.withdrawal_nail          — W = 1380 G^2.5 D^1.5
  design.reference_design_values  — tabulated species/grade values
  tools.*                         — LLM wrapper happy paths + error paths

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas verified algebraically against NDS 2018 / Breyer hand-calcs.

References
----------
NDS 2018 — National Design Specification for Wood Construction (AWC)
Breyer, D.E. et al. "Design of Wood Structures", 7th ed.
NDS Supplement 2018 — Design Values for Wood Construction

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.timber.design import (
    CD_load_duration,
    CM_wet,
    Ct_temp,
    CL_beam_stability,
    CF_size,
    Cfu_flat_use,
    Ci_incising,
    Cr_repetitive,
    CP_column_stability,
    FcE_critical,
    Cb_bearing_area,
    sawn_section,
    glulam_section,
    adjusted_Fb,
    adjusted_Fv,
    adjusted_Fc,
    adjusted_Fc_perp,
    adjusted_E_prime,
    bending_stress,
    shear_stress,
    check_bending,
    check_shear,
    check_deflection,
    check_compression_column,
    check_combined_bending_axial,
    check_bearing,
    lateral_yield_bolt,
    withdrawal_nail,
    reference_design_values,
)
from kerf_cad_core.timber.tools import (
    run_timber_reference_values,
    run_timber_adjusted_Fb,
    run_timber_adjusted_Fc,
    run_timber_sawn_section,
    run_timber_glulam_section,
    run_timber_check_bending,
    run_timber_check_shear,
    run_timber_check_deflection,
    run_timber_column_stability,
    run_timber_check_column,
    run_timber_check_combined,
    run_timber_check_bearing,
    run_timber_lateral_yield_bolt,
    run_timber_withdrawal_nail,
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


REL = 1e-6


# ===========================================================================
# 1. CD — load duration factor
# ===========================================================================

class TestCDLoadDuration:

    def test_permanent_load_CD_0_9(self):
        res = CD_load_duration("permanent")
        assert res["ok"] is True
        assert res["CD"] == pytest.approx(0.9)

    def test_ten_year_CD_1_0(self):
        res = CD_load_duration("ten_year")
        assert res["ok"] is True
        assert res["CD"] == pytest.approx(1.0)

    def test_snow_alias_CD_1_15(self):
        """'snow' is an alias for two_month → CD=1.15."""
        res = CD_load_duration("snow")
        assert res["ok"] is True
        assert res["CD"] == pytest.approx(1.15)

    def test_wind_CD_1_6(self):
        res = CD_load_duration("wind")
        assert res["ok"] is True
        assert res["CD"] == pytest.approx(1.6)

    def test_impact_CD_2_0(self):
        res = CD_load_duration("impact")
        assert res["ok"] is True
        assert res["CD"] == pytest.approx(2.0)

    def test_unknown_load_type_returns_error(self):
        res = CD_load_duration("blizzard")
        assert res["ok"] is False
        assert "reason" in res


# ===========================================================================
# 2. CM — wet-service factor
# ===========================================================================

class TestCMWet:

    def test_sawn_Fb_CM_0_85(self):
        """Sawn lumber Fb wet-service factor = 0.85 (NDS Supplement Table 4A)."""
        res = CM_wet("Fb", "sawn")
        assert res["ok"] is True
        assert res["CM"] == pytest.approx(0.85)

    def test_sawn_E_CM_0_90(self):
        res = CM_wet("E", "sawn")
        assert res["ok"] is True
        assert res["CM"] == pytest.approx(0.90)

    def test_glulam_Fb_CM_0_80(self):
        res = CM_wet("Fb", "glulam")
        assert res["ok"] is True
        assert res["CM"] == pytest.approx(0.80)

    def test_glulam_Fc_perp_CM_0_53(self):
        res = CM_wet("Fc_perp", "glulam")
        assert res["ok"] is True
        assert res["CM"] == pytest.approx(0.53)

    def test_unknown_prop_returns_error(self):
        res = CM_wet("Fweird", "sawn")
        assert res["ok"] is False

    def test_unknown_species_type_returns_error(self):
        res = CM_wet("Fb", "bamboo")
        assert res["ok"] is False


# ===========================================================================
# 3. Ct — temperature factor
# ===========================================================================

class TestCtTemp:

    def test_below_100F_returns_1_0(self):
        """Temperature <= 100°F → Ct = 1.0 for all properties."""
        for prop in ("Fb", "Fv", "Fc", "E"):
            res = Ct_temp(prop, 85.0)
            assert res["ok"] is True
            assert res["Ct"] == pytest.approx(1.0)

    def test_110F_Fb_returns_0_8(self):
        """100 < T <= 125°F, Fb → Ct = 0.8."""
        res = Ct_temp("Fb", 110.0)
        assert res["ok"] is True
        assert res["Ct"] == pytest.approx(0.8)

    def test_140F_Fb_returns_0_7(self):
        """125 < T <= 150°F, Fb → Ct = 0.7."""
        res = Ct_temp("Fb", 140.0)
        assert res["ok"] is True
        assert res["Ct"] == pytest.approx(0.7)

    def test_110F_E_returns_0_9(self):
        """100 < T <= 125°F, E → Ct = 0.9."""
        res = Ct_temp("E", 110.0)
        assert res["ok"] is True
        assert res["Ct"] == pytest.approx(0.9)

    def test_above_150F_returns_error(self):
        res = Ct_temp("Fb", 160.0)
        assert res["ok"] is False


# ===========================================================================
# 4. CL — beam stability factor
# ===========================================================================

class TestCLBeamStability:

    def test_short_unbraced_fully_supported_CL_near_1(self):
        """Short beam with high E'/Fb* ratio → CL close to 1.0."""
        # le=2ft, b=4in, d=8in, E'=1.3M psi, Fb*=1500 psi
        res = CL_beam_stability(2.0, 4.0, 8.0, 1_300_000.0, 1500.0)
        assert res["ok"] is True
        # With large E' relative to Fb*, CL should be close to 1.0
        assert res["CL"] > 0.95

    def test_CL_between_0_and_1(self):
        """CL must always be in [0, 1]."""
        res = CL_beam_stability(10.0, 1.5, 9.25, 580_000.0, 900.0)
        assert res["ok"] is True
        assert 0.0 <= res["CL"] <= 1.0

    def test_larger_unbraced_length_reduces_CL(self):
        """Longer unbraced length increases RB, reduces CL."""
        E = 1_600_000.0
        Fb_star = 1000.0
        b, d = 1.5, 9.25
        res_short = CL_beam_stability(2.0, b, d, E, Fb_star)
        res_long = CL_beam_stability(12.0, b, d, E, Fb_star)
        assert res_long["CL"] < res_short["CL"]

    def test_slenderness_warning_for_high_RB(self):
        """RB > 50 should appear in warnings."""
        # Extreme case: le=50ft, b=1.5in, d=20in
        res = CL_beam_stability(50.0, 1.5, 20.0, 580_000.0, 900.0)
        assert res["ok"] is True
        assert any("50" in w for w in res["warnings"])

    def test_negative_le_returns_error(self):
        res = CL_beam_stability(-1.0, 3.5, 9.25, 1_600_000.0, 1000.0)
        assert res["ok"] is False


# ===========================================================================
# 5. CF — size factor
# ===========================================================================

class TestCFSize:

    def test_d_le_12_CF_equals_1(self):
        """d <= 12 in → CF = 1.0 for Fb."""
        res = CF_size("Fb", 1.5, 11.25)
        assert res["ok"] is True
        assert res["CF"] == pytest.approx(1.0)

    def test_d_gt_12_CF_less_than_1_for_Fb(self):
        """d > 12 in → CF < 1.0 for Fb (NDS §4.3.6)."""
        res = CF_size("Fb", 1.5, 13.25)
        assert res["ok"] is True
        expected = (12.0 / 13.25) ** (1.0 / 9.0)
        assert res["CF"] == pytest.approx(expected, rel=REL)

    def test_Fv_returns_1_regardless_of_d(self):
        """Fv is not subject to size factor → CF = 1.0."""
        res = CF_size("Fv", 1.5, 20.0)
        assert res["ok"] is True
        assert res["CF"] == pytest.approx(1.0)


# ===========================================================================
# 6. Cfu — flat-use factor
# ===========================================================================

class TestCfuFlatUse:

    def test_strong_axis_Cfu_1_0(self):
        """b < d (strong-axis bending) → Cfu = 1.0."""
        res = Cfu_flat_use(1.5, 9.25)
        assert res["ok"] is True
        assert res["Cfu"] == pytest.approx(1.0)
        assert res["flat_use"] is False

    def test_flat_use_Cfu_gt_1(self):
        """b > d (flat use, weak-axis) → Cfu > 1.0."""
        res = Cfu_flat_use(9.25, 1.5)
        assert res["ok"] is True
        assert res["Cfu"] > 1.0
        assert res["flat_use"] is True
        expected = (9.25 / 1.5) ** (1.0 / 9.0)
        assert res["Cfu"] == pytest.approx(expected, rel=REL)


# ===========================================================================
# 7. Ci — incising factor
# ===========================================================================

class TestCiIncising:

    def test_Fb_Ci_0_80(self):
        res = Ci_incising("Fb")
        assert res["ok"] is True
        assert res["Ci"] == pytest.approx(0.80)

    def test_E_Ci_0_95(self):
        res = Ci_incising("E")
        assert res["ok"] is True
        assert res["Ci"] == pytest.approx(0.95)

    def test_Fc_perp_Ci_1_0(self):
        res = Ci_incising("Fc_perp")
        assert res["ok"] is True
        assert res["Ci"] == pytest.approx(1.0)

    def test_unknown_prop_returns_error(self):
        res = Ci_incising("Fweird")
        assert res["ok"] is False


# ===========================================================================
# 8. Cr — repetitive member factor
# ===========================================================================

class TestCrRepetitive:

    def test_2x4_at_16in_oc_Cr_1_15(self):
        """2x4 (1.5\" dressed) at 16\" → repetitive, Cr=1.15."""
        res = Cr_repetitive(1.5, 16.0)
        assert res["ok"] is True
        assert res["Cr"] == pytest.approx(1.15)
        assert res["repetitive"] is True

    def test_6x8_at_12in_oc_not_repetitive(self):
        """6x8 (b=5.5\" > 3.5\") → not repetitive, Cr=1.0."""
        res = Cr_repetitive(5.5, 12.0)
        assert res["ok"] is True
        assert res["Cr"] == pytest.approx(1.0)
        assert res["repetitive"] is False

    def test_2x4_at_48in_oc_not_repetitive(self):
        """2x4 at 48\" spacing (> 24\") → not repetitive."""
        res = Cr_repetitive(1.5, 48.0)
        assert res["ok"] is True
        assert res["Cr"] == pytest.approx(1.0)


# ===========================================================================
# 9. FcE and CP — column stability
# ===========================================================================

class TestColumnStability:

    def test_FcE_formula(self):
        """FcE = 0.822 × E' / (le/d)²."""
        E_min = 580_000.0
        le_d = 20.0
        res = FcE_critical(E_min, le_d)
        assert res["ok"] is True
        expected = 0.822 * E_min / le_d ** 2
        assert res["FcE_psi"] == pytest.approx(expected, rel=REL)

    def test_le_d_greater_than_50_warns(self):
        """le/d > 50 should trigger a warning."""
        res = FcE_critical(580_000.0, 55.0)
        assert res["ok"] is True
        assert any("50" in w for w in res["warnings"])

    def test_CP_between_0_and_1(self):
        """CP must be in [0, 1]."""
        FcE = 0.822 * 580_000.0 / (20.0 ** 2)
        res = CP_column_stability(20.0, 1400.0, FcE)
        assert res["ok"] is True
        assert 0.0 <= res["CP"] <= 1.0

    def test_CP_high_FcE_approaches_1(self):
        """When FcE >> Fc*, CP approaches 1.0."""
        res = CP_column_stability(5.0, 1000.0, 1_000_000.0)
        assert res["ok"] is True
        assert res["CP"] > 0.97

    def test_CP_low_FcE_near_0(self):
        """When FcE << Fc*, CP is small."""
        res = CP_column_stability(50.0, 2000.0, 10.0)
        assert res["ok"] is True
        assert res["CP"] < 0.1


# ===========================================================================
# 10. Cb — bearing area factor
# ===========================================================================

class TestCbBearingArea:

    def test_lb_lt_6_formula(self):
        """Cb = (lb + 0.375) / lb for lb < 6 in."""
        lb = 3.0
        res = Cb_bearing_area(lb)
        assert res["ok"] is True
        expected = (lb + 0.375) / lb
        assert res["Cb"] == pytest.approx(expected, rel=REL)

    def test_lb_ge_6_returns_1(self):
        """Cb = 1.0 for lb >= 6 in."""
        res = Cb_bearing_area(6.0)
        assert res["ok"] is True
        assert res["Cb"] == pytest.approx(1.0)

    def test_lb_zero_returns_error(self):
        res = Cb_bearing_area(0.0)
        assert res["ok"] is False


# ===========================================================================
# 11. Section properties
# ===========================================================================

class TestSawnSection:

    def test_2x4_dressed_dims(self):
        """2x4 nominal → 1.5 × 3.5 dressed (NDS Supplement Table 1B)."""
        res = sawn_section(2, 4)
        assert res["ok"] is True
        assert res["b_actual_in"] == pytest.approx(1.5)
        assert res["d_actual_in"] == pytest.approx(3.5)

    def test_2x10_section_properties(self):
        """2x10 dressed = 1.5 × 9.25; verify A, S, I."""
        res = sawn_section(2, 10)
        assert res["ok"] is True
        b, d = 1.5, 9.25
        assert res["A_in2"] == pytest.approx(b * d, rel=REL)
        assert res["S_in3"] == pytest.approx(b * d ** 2 / 6.0, rel=REL)
        assert res["I_in4"] == pytest.approx(b * d ** 3 / 12.0, rel=REL)

    def test_unknown_nominal_size_returns_error(self):
        res = sawn_section(2, 3)  # 2x3 not in standard table
        assert res["ok"] is False


class TestGlulamSection:

    def test_section_properties_formula(self):
        """Verify A=b*d, S=b*d²/6, I=b*d³/12."""
        b, d = 5.125, 18.0
        res = glulam_section(b, d)
        assert res["ok"] is True
        assert res["A_in2"] == pytest.approx(b * d, rel=REL)
        assert res["S_in3"] == pytest.approx(b * d ** 2 / 6.0, rel=REL)
        assert res["I_in4"] == pytest.approx(b * d ** 3 / 12.0, rel=REL)

    def test_negative_depth_returns_error(self):
        res = glulam_section(5.125, -18.0)
        assert res["ok"] is False


# ===========================================================================
# 12. Adjusted design values
# ===========================================================================

class TestAdjustedDesignValues:

    def test_Fb_prime_all_factors_1(self):
        """All factors = 1.0 → Fb' = Fb_ref."""
        res = adjusted_Fb(1500.0)
        assert res["ok"] is True
        assert res["Fb_prime_psi"] == pytest.approx(1500.0)

    def test_Fb_prime_with_CD_CM_CF(self):
        """Fb' = Fb × CD × CM × CF (others = 1.0)."""
        Fb, CD, CM, CF = 1000.0, 1.15, 0.85, 0.92
        res = adjusted_Fb(Fb, CD=CD, CM=CM, CF=CF)
        assert res["ok"] is True
        expected = Fb * CD * CM * CF
        assert res["Fb_prime_psi"] == pytest.approx(expected, rel=REL)

    def test_Fv_prime_formula(self):
        Fv, CD, CM, Ct, Ci = 180.0, 1.0, 0.97, 1.0, 0.875
        res = adjusted_Fv(Fv, CD=CD, CM=CM, Ct=Ct, Ci=Ci)
        assert res["ok"] is True
        assert res["Fv_prime_psi"] == pytest.approx(Fv * CD * CM * Ct * Ci, rel=REL)

    def test_E_prime_formula(self):
        E, CM, Ct, Ci = 1_600_000.0, 0.90, 1.0, 0.95
        res = adjusted_E_prime(E, CM=CM, Ct=Ct, Ci=Ci)
        assert res["ok"] is True
        assert res["E_prime_psi"] == pytest.approx(E * CM * Ct * Ci, rel=REL)


# ===========================================================================
# 13. Stress computations
# ===========================================================================

class TestStressCalc:

    def test_bending_stress_M_over_S(self):
        """fb = M / S."""
        M, S = 48_000.0, 32.0  # lb·in, in³
        res = bending_stress(M, S)
        assert res["ok"] is True
        assert res["fb_psi"] == pytest.approx(M / S, rel=REL)

    def test_shear_stress_1_5V_over_A(self):
        """fv = 1.5 × V / A."""
        V, A = 2400.0, 10.875  # lb, in²
        res = shear_stress(V, A)
        assert res["ok"] is True
        assert res["fv_psi"] == pytest.approx(1.5 * V / A, rel=REL)

    def test_zero_shear_force(self):
        res = shear_stress(0.0, 10.0)
        assert res["ok"] is True
        assert res["fv_psi"] == pytest.approx(0.0)


# ===========================================================================
# 14. Design checks
# ===========================================================================

class TestCheckBending:

    def test_pass_when_fb_le_Fb_prime(self):
        res = check_bending(800.0, 1200.0)
        assert res["ok"] is True
        assert res["pass_"] is True
        assert res["utilization"] == pytest.approx(800.0 / 1200.0, rel=REL)

    def test_fail_when_fb_gt_Fb_prime(self):
        res = check_bending(1500.0, 1200.0)
        assert res["ok"] is True
        assert res["pass_"] is False
        assert len(res["warnings"]) > 0

    def test_utilization_at_unity(self):
        """fb == Fb' → utilization = 1.0 (marginal pass)."""
        res = check_bending(1000.0, 1000.0)
        assert res["ok"] is True
        assert res["pass_"] is True
        assert res["utilization"] == pytest.approx(1.0)


class TestCheckShear:

    def test_pass_below_limit(self):
        res = check_shear(100.0, 180.0)
        assert res["ok"] is True
        assert res["pass_"] is True

    def test_fail_above_limit(self):
        res = check_shear(200.0, 175.0)
        assert res["ok"] is True
        assert res["pass_"] is False
        assert len(res["warnings"]) > 0


class TestCheckDeflection:

    def test_pass_within_limits(self):
        """delta_L = span/400 < L/360 and delta_TL = span/300 < L/240 → pass."""
        span = 12.0 * 12.0  # 12 ft in inches
        dL = span / 400.0
        dTL = span / 300.0
        res = check_deflection(dL, dTL, span)
        assert res["ok"] is True
        assert res["pass_"] is True
        assert res["live_ok"] is True
        assert res["total_ok"] is True

    def test_fail_live_load_limit(self):
        """delta_L = span/300 > L/360 → live fails."""
        span = 10.0 * 12.0
        dL = span / 300.0  # exceeds L/360
        dTL = span / 500.0
        res = check_deflection(dL, dTL, span)
        assert res["ok"] is True
        assert res["live_ok"] is False
        assert res["pass_"] is False
        assert len(res["warnings"]) > 0

    def test_deflection_limit_formula(self):
        """Allowable live = span / limit_L."""
        span = 120.0
        res = check_deflection(0.1, 0.1, span, limit_L=360.0, limit_TL=240.0)
        assert res["ok"] is True
        assert res["limit_L_in"] == pytest.approx(span / 360.0, rel=REL)
        assert res["limit_TL_in"] == pytest.approx(span / 240.0, rel=REL)

    def test_custom_limits(self):
        """Custom limit_L=480, limit_TL=360 should be used."""
        span = 180.0
        dL = span / 500.0  # passes L/480
        dTL = span / 400.0  # passes L/360
        res = check_deflection(dL, dTL, span, limit_L=480.0, limit_TL=360.0)
        assert res["ok"] is True
        assert res["pass_"] is True


class TestCheckCompression:

    def test_pass_fc_lt_Fc_prime(self):
        res = check_compression_column(900.0, 1200.0)
        assert res["ok"] is True
        assert res["pass_"] is True

    def test_fail_fc_gt_Fc_prime(self):
        res = check_compression_column(1500.0, 1200.0)
        assert res["ok"] is True
        assert res["pass_"] is False


class TestCheckCombined:

    def test_pass_low_loads(self):
        """With fc and fb both well below limits → interaction < 1."""
        res = check_combined_bending_axial(
            fb_psi=200.0,
            Fb_prime_psi=1200.0,
            fc_psi=300.0,
            Fc_star_psi=1400.0,
            FcE_psi=1000.0,
        )
        assert res["ok"] is True
        assert res["pass_"] is True
        assert res["interaction"] < 1.0

    def test_fail_when_fc_exceeds_FcE(self):
        """fc >= FcE → Euler denominator non-positive → fails."""
        res = check_combined_bending_axial(
            fb_psi=100.0,
            Fb_prime_psi=1200.0,
            fc_psi=1100.0,
            Fc_star_psi=1400.0,
            FcE_psi=1000.0,
        )
        assert res["ok"] is True
        assert res["pass_"] is False

    def test_interaction_equation_algebraic(self):
        """Verify NDS §3.9.2: (fc/Fc*)² + fb/(Fb' × (1-fc/FcE))."""
        fc, Fc_star, FcE, fb, Fb_p = 500.0, 1400.0, 1000.0, 300.0, 1200.0
        expected_term1 = (fc / Fc_star) ** 2
        expected_term2 = fb / (Fb_p * (1.0 - fc / FcE))
        expected = expected_term1 + expected_term2
        res = check_combined_bending_axial(fb, Fb_p, fc, Fc_star, FcE)
        assert res["ok"] is True
        assert res["interaction"] == pytest.approx(expected, rel=REL)


class TestCheckBearing:

    def test_pass_bearing(self):
        res = check_bearing(300.0, 625.0)
        assert res["ok"] is True
        assert res["pass_"] is True

    def test_fail_bearing(self):
        res = check_bearing(700.0, 625.0)
        assert res["ok"] is True
        assert res["pass_"] is False


# ===========================================================================
# 15. Lateral yield — bolt/lag screw
# ===========================================================================

class TestLateralYieldBolt:

    def test_governing_mode_positive(self):
        """All inputs valid → Z > 0 and governing mode is known."""
        res = lateral_yield_bolt(
            D_in=0.75,
            tm_in=3.5,
            ts_in=1.5,
            Fyb_psi=45_000.0,
            Fe_m_psi=4650.0,
            Fe_s_psi=4650.0,
        )
        assert res["ok"] is True
        assert res["Z_lb"] > 0
        assert res["governing_mode"] in ("Im", "Is", "II", "IIIm", "IIIs", "IV")

    def test_all_six_modes_computed(self):
        """Result must contain all six yield modes."""
        res = lateral_yield_bolt(0.5, 3.0, 1.5, 45_000.0, 4650.0, 4650.0)
        assert res["ok"] is True
        assert set(res["modes"].keys()) == {"Im", "Is", "II", "IIIm", "IIIs", "IV"}

    def test_governing_is_minimum(self):
        """Governing mode Z must equal the minimum across all modes."""
        res = lateral_yield_bolt(0.625, 3.5, 1.5, 45_000.0, 4650.0, 4650.0)
        assert res["ok"] is True
        positive = {k: v for k, v in res["modes"].items() if v > 0}
        min_mode = min(positive, key=lambda k: positive[k])
        assert res["governing_mode"] == min_mode
        assert res["Z_lb"] == pytest.approx(positive[min_mode], rel=REL)

    def test_theta_90_reduces_Z_vs_0(self):
        """Load perpendicular to grain (θ=90°) increases Kθ → increases Rd → reduces Z."""
        Z_0 = lateral_yield_bolt(0.75, 3.5, 1.5, 45_000.0, 4650.0, 4650.0, 0.0)
        Z_90 = lateral_yield_bolt(0.75, 3.5, 1.5, 45_000.0, 4650.0, 4650.0, 90.0)
        assert Z_0["ok"] is True and Z_90["ok"] is True
        assert Z_90["Z_lb"] < Z_0["Z_lb"]

    def test_negative_D_returns_error(self):
        res = lateral_yield_bolt(-0.5, 3.0, 1.5, 45_000.0, 4650.0, 4650.0)
        assert res["ok"] is False


# ===========================================================================
# 16. Nail withdrawal
# ===========================================================================

class TestWithdrawalNail:

    def test_formula_W_per_in(self):
        """W = 1380 × G^2.5 × D^1.5."""
        D, L_pen, G = 0.148, 2.0, 0.50
        res = withdrawal_nail(D, L_pen, G)
        assert res["ok"] is True
        expected_per_in = 1380.0 * G ** 2.5 * D ** 1.5
        assert res["W_per_in_lb"] == pytest.approx(expected_per_in, rel=REL)

    def test_W_total_formula(self):
        """W_total = W_per_in × L_pen."""
        D, L_pen, G = 0.131, 1.5, 0.55
        res = withdrawal_nail(D, L_pen, G)
        assert res["ok"] is True
        assert res["W_total_lb"] == pytest.approx(res["W_per_in_lb"] * L_pen, rel=REL)

    def test_higher_G_increases_W(self):
        """Higher specific gravity → higher withdrawal capacity."""
        W_DFL = withdrawal_nail(0.131, 1.5, 0.50)["W_per_in_lb"]
        W_SP = withdrawal_nail(0.131, 1.5, 0.55)["W_per_in_lb"]
        assert W_SP > W_DFL

    def test_zero_D_returns_error(self):
        res = withdrawal_nail(0.0, 2.0, 0.50)
        assert res["ok"] is False


# ===========================================================================
# 17. Reference design values table
# ===========================================================================

class TestReferenceDesignValues:

    def test_DFL_select_structural_Fb(self):
        """Douglas Fir-Larch Select Structural Fb = 1500 psi."""
        res = reference_design_values("douglas_fir_larch", "select_structural")
        assert res["ok"] is True
        assert res["Fb_psi"] == pytest.approx(1500.0)

    def test_southern_pine_no_2_Fv(self):
        """Southern Pine No.2 Fv = 175 psi."""
        res = reference_design_values("southern_pine", "no_2")
        assert res["ok"] is True
        assert res["Fv_psi"] == pytest.approx(175.0)

    def test_all_properties_returned(self):
        """Result must include Fb, Fv, Fc, Fc_perp, Ft, E, Emin."""
        res = reference_design_values("hem_fir", "no_1")
        assert res["ok"] is True
        for key in ("Fb_psi", "Fv_psi", "Fc_psi", "Fc_perp_psi", "Ft_psi", "E_psi", "Emin_psi"):
            assert key in res, f"Missing key: {key}"
            assert res[key] > 0

    def test_unknown_species_returns_error(self):
        res = reference_design_values("teak", "select_structural")
        assert res["ok"] is False

    def test_unknown_grade_returns_error(self):
        res = reference_design_values("douglas_fir_larch", "utility")
        assert res["ok"] is False


# ===========================================================================
# 17b. NDS 2018 worked-example reference cases (citable known answers)
# ===========================================================================

class TestNDSReferenceCases:
    """Each assertion checks a specific NDS 2018 / Breyer value."""

    def test_CD_table_2_3_2(self):
        # NDS 2018 Table 2.3.2 exact CD values.
        assert CD_load_duration("permanent")["CD"] == pytest.approx(0.9)
        assert CD_load_duration("ten_year")["CD"] == pytest.approx(1.0)
        assert CD_load_duration("snow")["CD"] == pytest.approx(1.15)
        assert CD_load_duration("seven_day")["CD"] == pytest.approx(1.25)
        assert CD_load_duration("wind")["CD"] == pytest.approx(1.6)
        assert CD_load_duration("impact")["CD"] == pytest.approx(2.0)

    def test_Ct_Fc_perp_uses_same_as_Fb_table_2_3_3(self):
        # NDS 2018 Table 2.3.3 (dry): Fc⊥ takes the SAME Ct as Fb/Fv/Fc/Ft
        # (0.8 at 100–125°F, 0.7 at 125–150°F) — NOT 0.67/0.58 (the bug).
        assert Ct_temp("Fc_perp", 110.0)["Ct"] == pytest.approx(0.8)
        assert Ct_temp("Fc_perp", 140.0)["Ct"] == pytest.approx(0.7)
        assert Ct_temp("Fb", 110.0)["Ct"] == pytest.approx(0.8)
        assert Ct_temp("E", 140.0)["Ct"] == pytest.approx(0.9)

    def test_FcE_critical_NDS_3_7_1_5(self):
        # NDS 2018 §3.7.1.5: FcE = 0.822·E'_min/(le/d)².
        # E'_min = 580,000 psi, le/d = 30 → FcE = 0.822·580000/900 = 529.7 psi.
        r = FcE_critical(580_000.0, 30.0)
        assert r["FcE_psi"] == pytest.approx(0.822 * 580_000.0 / 900.0, rel=1e-9)

    def test_CP_Ylinen_NDS_3_7_1_5(self):
        # NDS 2018 §3.7.1.5 Ylinen: CP=(1+a)/(2c)−√[((1+a)/(2c))²−a/c],
        # c=0.8 sawn.  Fc*=1400, FcE=800 → α=0.5714,
        # A=(1.5714)/1.6=0.98214 → CP = 0.98214 − √(0.96460 − 0.71429) = 0.4815.
        r = CP_column_stability(25.0, 1400.0, 800.0)
        a = 800.0 / 1400.0
        A = (1.0 + a) / 1.6
        cp_ref = A - math.sqrt(A * A - a / 0.8)
        assert r["CP"] == pytest.approx(cp_ref, rel=1e-9)

    def test_CL_Ylinen_NDS_3_3_3(self):
        # NDS 2018 §3.3.3.8: RB=√(le·d/b²); FbE=1.20·E'min/RB²;
        # CL=(1+α)/1.9−√[((1+α)/1.9)²−α/0.95], α=FbE/Fb*.
        # le=8 ft=96 in, b=1.5, d=9.25 → RB=√(96·9.25/2.25)=19.87,
        # FbE=1.20·690000/394.7=2097 psi.
        r = CL_beam_stability(8.0, 1.5, 9.25, 690_000.0, 1500.0)
        RB = math.sqrt(96.0 * 9.25 / (1.5 ** 2))
        FbE = 1.20 * 690_000.0 / RB ** 2
        a = FbE / 1500.0
        A = (1.0 + a) / 1.9
        cl_ref = A - math.sqrt(A * A - a / 0.95)
        assert r["RB"] == pytest.approx(RB, rel=1e-9)
        assert r["CL"] == pytest.approx(cl_ref, rel=1e-9)

    def test_withdrawal_nail_NDS_12_2_3(self):
        # NDS 2018 §12.2.3: W = 1380·G^2.5·D^1.5 lb/in.
        # 16d common nail D=0.162 in, DF-L G=0.50 →
        # W = 1380·0.5^2.5·0.162^1.5 = 1380·0.17678·0.06517 = 15.90 lb/in.
        r = withdrawal_nail(0.162, 1.5, 0.50)
        assert r["W_per_in_lb"] == pytest.approx(1380.0 * 0.50 ** 2.5 * 0.162 ** 1.5, rel=1e-9)

    def test_combined_axial_term_uses_Fc_prime_with_CP(self):
        # NDS 2018 Eq. 3.9-3 first term is (fc/Fc')² with Fc' = Fc*·CP.
        # Bug fix: previously used Fc* (no CP) which is unconservative.
        # fc=500, Fc*=1400, CP=0.6 → Fc'=840 → term1=(500/840)²=0.3543
        # (was (500/1400)²=0.1276 before the fix — far too low).
        r = check_combined_bending_axial(
            fb_psi=300.0, Fb_prime_psi=1200.0, fc_psi=500.0,
            Fc_star_psi=1400.0, FcE_psi=1000.0, CP=0.6,
        )
        assert r["term_axial"] == pytest.approx((500.0 / (1400.0 * 0.6)) ** 2, rel=1e-9)
        assert r["Fc_prime_psi"] == pytest.approx(840.0, rel=1e-9)

    def test_combined_default_CP_back_compatible(self):
        # With default CP=1.0, Fc' = Fc* and result matches the legacy formula.
        r = check_combined_bending_axial(300.0, 1200.0, 500.0, 1400.0, 1000.0)
        assert r["term_axial"] == pytest.approx((500.0 / 1400.0) ** 2, rel=1e-9)

    def test_DFL_select_structural_full_row_NDS_table_4A(self):
        # NDS Supplement 2018 Table 4A — Douglas Fir-Larch, Select Structural:
        # Fb=1500, Ft=1000, Fv=180, Fc⊥=625, Fc=1700, E=1.9e6, Emin=0.69e6.
        r = reference_design_values("douglas_fir_larch", "select_structural")
        assert r["Fb_psi"] == 1500.0
        assert r["Ft_psi"] == 1000.0
        assert r["Fv_psi"] == 180.0
        assert r["Fc_perp_psi"] == 625.0
        assert r["Fc_psi"] == 1700.0
        assert r["E_psi"] == 1_900_000.0
        assert r["Emin_psi"] == 690_000.0

    def test_sawn_section_2x10_NDS_supplement_1B(self):
        # NDS Supplement Table 1B: 2x10 dressed = 1.5 × 9.25 in.
        # A=13.875 in², S = b·d²/6 = 1.5·9.25²/6 = 21.39 in³,
        # I = b·d³/12 = 1.5·9.25³/12 = 98.93 in⁴.
        r = sawn_section(2, 10)
        assert r["A_in2"] == pytest.approx(1.5 * 9.25, rel=1e-9)
        assert r["S_in3"] == pytest.approx(1.5 * 9.25 ** 2 / 6.0, rel=1e-9)
        assert r["I_in4"] == pytest.approx(1.5 * 9.25 ** 3 / 12.0, rel=1e-9)


# ===========================================================================
# 18. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_timber_reference_values_happy_path(self):
        ctx = _ctx()
        raw = _run(run_timber_reference_values(ctx, _args(
            species="douglas_fir_larch", grade="no_2"
        )))
        d = _ok_tool(raw)
        assert d["Fb_psi"] > 0

    def test_run_timber_reference_values_missing_species(self):
        ctx = _ctx()
        raw = _run(run_timber_reference_values(ctx, _args(grade="no_1")))
        _err_tool(raw)

    def test_run_timber_adjusted_Fb_happy_path(self):
        ctx = _ctx()
        raw = _run(run_timber_adjusted_Fb(ctx, _args(
            Fb_ref=1500.0, CD=1.0, CM=0.85, Ct=1.0
        )))
        d = _ok_tool(raw)
        assert d["Fb_prime_psi"] == pytest.approx(1500.0 * 0.85, rel=REL)

    def test_run_timber_adjusted_Fb_missing_Fb_ref(self):
        ctx = _ctx()
        raw = _run(run_timber_adjusted_Fb(ctx, _args(CD=1.0)))
        _err_tool(raw)

    def test_run_timber_adjusted_Fc_happy_path(self):
        ctx = _ctx()
        raw = _run(run_timber_adjusted_Fc(ctx, _args(Fc_ref=1700.0, CD=1.15, CP=0.8)))
        d = _ok_tool(raw)
        assert d["Fc_prime_psi"] == pytest.approx(1700.0 * 1.15 * 0.8, rel=REL)

    def test_run_timber_sawn_section_happy_path(self):
        ctx = _ctx()
        raw = _run(run_timber_sawn_section(ctx, _args(b_nom_in=2, d_nom_in=10)))
        d = _ok_tool(raw)
        assert d["b_actual_in"] == pytest.approx(1.5)
        assert d["d_actual_in"] == pytest.approx(9.25)

    def test_run_timber_sawn_section_bad_size(self):
        ctx = _ctx()
        raw = _run(run_timber_sawn_section(ctx, _args(b_nom_in=2, d_nom_in=3)))
        _err_tool(raw)

    def test_run_timber_glulam_section_happy_path(self):
        ctx = _ctx()
        raw = _run(run_timber_glulam_section(ctx, _args(b_in=5.125, d_in=18.0)))
        d = _ok_tool(raw)
        assert d["A_in2"] == pytest.approx(5.125 * 18.0, rel=REL)

    def test_run_timber_check_bending_pass(self):
        ctx = _ctx()
        raw = _run(run_timber_check_bending(ctx, _args(fb_psi=900.0, Fb_prime_psi=1200.0)))
        d = _ok_tool(raw)
        assert d["pass_"] is True

    def test_run_timber_check_bending_fail(self):
        ctx = _ctx()
        raw = _run(run_timber_check_bending(ctx, _args(fb_psi=1400.0, Fb_prime_psi=1200.0)))
        d = _ok_tool(raw)
        assert d["pass_"] is False

    def test_run_timber_check_shear_bad_json(self):
        ctx = _ctx()
        raw = _run(run_timber_check_shear(ctx, b"bad json"))
        _err_tool(raw)

    def test_run_timber_check_deflection_pass(self):
        ctx = _ctx()
        span = 144.0  # 12 ft
        raw = _run(run_timber_check_deflection(ctx, _args(
            delta_L_in=span / 400.0, delta_TL_in=span / 300.0, span_in=span
        )))
        d = _ok_tool(raw)
        assert d["pass_"] is True

    def test_run_timber_column_stability_happy_path(self):
        ctx = _ctx()
        raw = _run(run_timber_column_stability(ctx, _args(
            le_d=20.0, Fc_star_psi=1400.0, E_prime_min_psi=580_000.0
        )))
        d = _ok_tool(raw)
        assert "CP" in d
        assert 0.0 <= d["CP"] <= 1.0

    def test_run_timber_check_column_pass(self):
        ctx = _ctx()
        raw = _run(run_timber_check_column(ctx, _args(fc_psi=800.0, Fc_prime_psi=1000.0)))
        d = _ok_tool(raw)
        assert d["pass_"] is True

    def test_run_timber_check_combined_pass(self):
        ctx = _ctx()
        raw = _run(run_timber_check_combined(ctx, _args(
            fb_psi=200.0, Fb_prime_psi=1200.0,
            fc_psi=300.0, Fc_star_psi=1400.0, FcE_psi=1000.0
        )))
        d = _ok_tool(raw)
        assert d["pass_"] is True

    def test_run_timber_check_bearing_fail(self):
        ctx = _ctx()
        raw = _run(run_timber_check_bearing(ctx, _args(
            fc_perp_psi=700.0, Fc_perp_prime_psi=625.0
        )))
        d = _ok_tool(raw)
        assert d["pass_"] is False

    def test_run_timber_lateral_yield_bolt_happy_path(self):
        ctx = _ctx()
        raw = _run(run_timber_lateral_yield_bolt(ctx, _args(
            D_in=0.75, tm_in=3.5, ts_in=1.5,
            Fyb_psi=45_000.0, Fe_m_psi=4650.0, Fe_s_psi=4650.0
        )))
        d = _ok_tool(raw)
        assert d["Z_lb"] > 0
        assert d["governing_mode"] in ("Im", "Is", "II", "IIIm", "IIIs", "IV")

    def test_run_timber_withdrawal_nail_happy_path(self):
        ctx = _ctx()
        raw = _run(run_timber_withdrawal_nail(ctx, _args(
            D_in=0.131, L_pen_in=1.5, G=0.50
        )))
        d = _ok_tool(raw)
        assert d["W_total_lb"] > 0

    def test_run_timber_withdrawal_nail_missing_G(self):
        ctx = _ctx()
        raw = _run(run_timber_withdrawal_nail(ctx, _args(D_in=0.131, L_pen_in=1.5)))
        _err_tool(raw)
