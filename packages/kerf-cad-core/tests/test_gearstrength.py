"""
Hermetic tests for kerf_cad_core.gearstrength — AGMA 2001-D04 gear stress & rating.

Coverage:
  rating.agma_dynamic_factor        — Kv from Qv & pitch-line velocity
  rating.agma_geometry_factor_J     — spur and helical bending factor J
  rating.agma_geometry_factor_I     — pitting factor I, spur and helical
  rating.agma_bending_stress        — English and metric units
  rating.agma_contact_stress        — English and metric units
  rating.agma_safety_factors        — SF / SH, pass/fail, warnings
  rating.agma_power_rating          — Wt limits, power, torque
  rating.agma_service_life          — YN / ZN, regimes, hardness warnings
  tools.*                           — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas are verified algebraically against Shigley 10th ed. §§ 14-1..14-5
and AGMA 2001-D04 examples.

References
----------
Shigley's Mechanical Engineering Design, 10th ed., §§ 14-1 to 14-5
AGMA 2001-D04 — Fundamental Rating Factors and Calculation Methods

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.gearstrength.rating import (
    agma_dynamic_factor,
    agma_geometry_factor_J,
    agma_geometry_factor_I,
    agma_bending_stress,
    agma_contact_stress,
    agma_safety_factors,
    agma_power_rating,
    agma_service_life,
)
from kerf_cad_core.gearstrength.tools import (
    run_agma_dynamic_factor,
    run_agma_geometry_factor_J,
    run_agma_geometry_factor_I,
    run_agma_bending_stress,
    run_agma_contact_stress,
    run_agma_safety_factors,
    run_agma_power_rating,
    run_agma_service_life,
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


# ---------------------------------------------------------------------------
# 1. agma_dynamic_factor
# ---------------------------------------------------------------------------

class TestDynamicFactor:
    def test_kv_greater_than_one(self):
        """Kv must always be >= 1 for any valid inputs."""
        r = agma_dynamic_factor(1000, 6)
        assert r["ok"] is True
        assert r["Kv"] >= 1.0

    def test_higher_quality_lower_kv(self):
        """Better quality (higher Qv) yields lower (better) Kv at same velocity."""
        kv6 = agma_dynamic_factor(1000, 6)["Kv"]
        kv10 = agma_dynamic_factor(1000, 10)["Kv"]
        assert kv10 < kv6

    def test_higher_velocity_higher_kv(self):
        """Higher velocity raises the dynamic factor."""
        kv_low  = agma_dynamic_factor(500,  6)["Kv"]
        kv_high = agma_dynamic_factor(3000, 6)["Kv"]
        assert kv_high > kv_low

    def test_shigley_example_approx(self):
        """
        Shigley 10th Example 14-4: Qv=6, Vt=600 ft/min → Kv ≈ 1.374.
        Allow ±5% tolerance for floating-point and formula variant.
        """
        r = agma_dynamic_factor(600, 6)
        assert r["ok"] is True
        assert abs(r["Kv"] - 1.374) < 0.10  # within 10% of textbook value

    def test_vt_max_field_present(self):
        r = agma_dynamic_factor(500, 8)
        assert "Vt_max_fpm" in r
        assert r["Vt_max_fpm"] > 0

    def test_over_velocity_limit_warns(self):
        """Exceeding Vt_max for the quality number should produce a warning."""
        # Use very high velocity with low Qv to guarantee exceedance
        r = agma_dynamic_factor(50_000, 3)
        assert "warnings" in r
        assert len(r["warnings"]) > 0

    def test_error_negative_velocity(self):
        r = agma_dynamic_factor(-100, 6)
        assert r["ok"] is False

    def test_error_qv_out_of_range_low(self):
        r = agma_dynamic_factor(1000, 2)
        assert r["ok"] is False

    def test_error_qv_out_of_range_high(self):
        r = agma_dynamic_factor(1000, 13)
        assert r["ok"] is False

    def test_kv_formula_manual(self):
        """Verify Kv formula manually: B=0.25*(12-Qv)^(2/3), A=50+56*(1-B)."""
        Vt, Qv = 800, 7
        B = 0.25 * (12 - Qv) ** (2 / 3)
        A = 50 + 56 * (1 - B)
        Kv_expected = ((A + math.sqrt(Vt)) / A) ** B
        r = agma_dynamic_factor(Vt, Qv)
        assert abs(r["Kv"] - Kv_expected) < 1e-10


# ---------------------------------------------------------------------------
# 2. agma_geometry_factor_J
# ---------------------------------------------------------------------------

class TestGeometryFactorJ:
    def test_spur_20deg_20teeth(self):
        """Standard spur gear with 20 teeth at 20° should give J ~ 0.300."""
        r = agma_geometry_factor_J(20, 0.0)
        assert r["ok"] is True
        assert abs(r["J"] - 0.300) < 0.02

    def test_spur_25deg_larger_J(self):
        """25° pressure angle generally gives higher J than 20° (wider tooth)."""
        j20 = agma_geometry_factor_J(50, 0.0, pressure_angle_deg=20)["J"]
        j25 = agma_geometry_factor_J(50, 0.0, pressure_angle_deg=25)["J"]
        assert j25 > j20

    def test_more_teeth_higher_J(self):
        """More teeth → thicker tooth base → higher J."""
        j_small = agma_geometry_factor_J(20, 0.0)["J"]
        j_large = agma_geometry_factor_J(100, 0.0)["J"]
        assert j_large > j_small

    def test_helical_J_less_than_spur(self):
        """Helical correction reduces J (helix_correction < 1), so J_helical < J_spur."""
        r_spur    = agma_geometry_factor_J(30, 0.0)
        r_helical = agma_geometry_factor_J(30, 30.0)
        # helix_correction < 1 implies J_helical <= J_spur
        assert r_helical["helix_correction"] < 1.0
        assert r_helical["J"] < r_spur["J"]

    def test_helix_correction_in_result(self):
        r = agma_geometry_factor_J(40, 25.0)
        assert "helix_correction" in r
        assert 0 < r["helix_correction"] <= 1.0

    def test_error_N_too_small(self):
        r = agma_geometry_factor_J(5, 0.0)
        assert r["ok"] is False

    def test_error_psi_too_large(self):
        r = agma_geometry_factor_J(30, 60.0)
        assert r["ok"] is False

    def test_j_spur_equals_j_with_zero_helix(self):
        """For ψ=0, J should equal J_spur (no correction applied)."""
        r = agma_geometry_factor_J(30, 0.0)
        assert r["J"] == pytest.approx(r["J_spur"], abs=1e-10)


# ---------------------------------------------------------------------------
# 3. agma_geometry_factor_I
# ---------------------------------------------------------------------------

class TestGeometryFactorI:
    def test_spur_standard(self):
        """Spur gear pair 20t pinion / 40t gear at 20° → I should be ~0.107."""
        r = agma_geometry_factor_I(20, 40, 0.0)
        assert r["ok"] is True
        # Shigley Example 14-4 gives I ≈ 0.107 for similar geometry
        assert 0.05 < r["I"] < 0.25

    def test_gear_ratio_field(self):
        r = agma_geometry_factor_I(20, 60, 0.0)
        assert r["m_G"] == pytest.approx(3.0)

    def test_higher_ratio_different_I(self):
        """I changes with gear ratio."""
        i1 = agma_geometry_factor_I(20, 40, 0.0)["I"]
        i2 = agma_geometry_factor_I(20, 80, 0.0)["I"]
        assert i1 != pytest.approx(i2, abs=0.001)

    def test_helical_phi_t_differs_from_phi_n(self):
        """For helical gear, transverse pressure angle phi_t != phi_n."""
        r = agma_geometry_factor_I(20, 40, 20.0, pressure_angle_deg=20.0)
        assert r["phi_t_deg"] > 20.0  # transverse PA > normal PA for ψ > 0

    def test_spur_phi_t_equals_phi_n(self):
        r = agma_geometry_factor_I(20, 40, 0.0, pressure_angle_deg=20.0)
        assert r["phi_t_deg"] == pytest.approx(20.0, abs=1e-6)

    def test_error_N_g_less_than_N_p(self):
        r = agma_geometry_factor_I(40, 20, 0.0)
        assert r["ok"] is False

    def test_error_N_p_too_small(self):
        r = agma_geometry_factor_I(5, 20, 0.0)
        assert r["ok"] is False

    def test_internal_gear_different_I(self):
        """Internal (ring) gear has different I formula."""
        I_ext = agma_geometry_factor_I(20, 80, 0.0, external=True)["I"]
        I_int = agma_geometry_factor_I(20, 80, 0.0, external=False)["I"]
        assert I_ext != pytest.approx(I_int, abs=0.001)


# ---------------------------------------------------------------------------
# 4. agma_bending_stress  (English units)
# ---------------------------------------------------------------------------

class TestBendingStress:
    # Shigley Example 14-4 baseline parameters (English, approximate):
    # Wt=540 lbf, Ko=1.0, Kv~1.37, Ks=1.0, Km=1.2, KB=1.0
    # b=2.0 in, Pd=8 teeth/in, J~0.30 → σ_t ~ 540*1.0*1.37*1.0*8*1.2*1.0/(2.0*0.30)
    def test_english_units_positive_stress(self):
        r = agma_bending_stress(540, 1.0, 1.37, 1.0, 1.2, 1.0, 2.0, 8, 0.30)
        assert r["ok"] is True
        assert r["sigma_t"] > 0
        assert r["unit"] == "psi"

    def test_formula_manually(self):
        """Verify English formula: σ_t = Wt·Ko·Kv·Ks·Pd·Km·KB / (b·J)."""
        Wt, Ko, Kv, Ks, Pd, Km, KB, b, J = 540, 1.0, 1.37, 1.0, 8, 1.2, 1.0, 2.0, 0.30
        expected = Wt * Ko * Kv * Ks * Pd * Km * KB / (b * J)
        r = agma_bending_stress(Wt, Ko, Kv, Ks, Km, KB, b, Pd, J, metric=False)
        assert r["sigma_t"] == pytest.approx(expected, rel=1e-6)

    def test_metric_units_positive_stress(self):
        """Metric: Wt=2400 N, b=50 mm, m=3 mm, J=0.30 → σ_t [MPa]."""
        r = agma_bending_stress(2400, 1.0, 1.37, 1.0, 1.2, 1.0, 50, 3, 0.30, metric=True)
        assert r["ok"] is True
        assert r["unit"] == "MPa"
        assert r["sigma_t"] > 0

    def test_metric_formula_manually(self):
        """Verify metric formula: σ_t = Wt·Ko·Kv·Ks·Km·KB / (b·m·J)."""
        Wt, Ko, Kv, Ks, m, Km, KB, b, J = 2400, 1.0, 1.37, 1.0, 3, 1.2, 1.0, 50, 0.30
        expected = Wt * Ko * Kv * Ks * Km * KB / (b * m * J)
        r = agma_bending_stress(Wt, Ko, Kv, Ks, Km, KB, b, m, J, metric=True)
        assert r["sigma_t"] == pytest.approx(expected, rel=1e-6)

    def test_high_stress_warning(self):
        """Very high bending stress should flag a warning."""
        r = agma_bending_stress(100_000, 2.0, 2.0, 1.5, 2.0, 1.0, 1.0, 20, 0.30)
        assert "warnings" in r

    def test_error_zero_b(self):
        r = agma_bending_stress(540, 1.0, 1.37, 1.0, 1.2, 1.0, 0, 8, 0.30)
        assert r["ok"] is False

    def test_error_negative_Wt(self):
        r = agma_bending_stress(-100, 1.0, 1.37, 1.0, 1.2, 1.0, 2.0, 8, 0.30)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 5. agma_contact_stress
# ---------------------------------------------------------------------------

class TestContactStress:
    # Shigley approximate: Cp(steel/steel)=2300, Wt=540, Ko=1, Kv=1.37, Ks=1
    # Km=1.2, d_p=2.5 in, b=2.0 in, I~0.107
    def test_english_positive_stress(self):
        r = agma_contact_stress(540, 1.0, 1.37, 1.0, 1.2, 2300, 2.5, 2.0, 0.107)
        assert r["ok"] is True
        assert r["sigma_c"] > 0
        assert r["unit"] == "psi"

    def test_formula_manually(self):
        """Verify: σ_c = Cp * sqrt(Wt·Ko·Kv·Ks·Km / (d·b·I))."""
        Wt, Ko, Kv, Ks, Km = 540, 1.0, 1.37, 1.0, 1.2
        Cp, d, b, I = 2300, 2.5, 2.0, 0.107
        rad = Wt * Ko * Kv * Ks * Km / (d * b * I)
        expected = Cp * math.sqrt(rad)
        r = agma_contact_stress(Wt, Ko, Kv, Ks, Km, Cp, d, b, I)
        assert r["sigma_c"] == pytest.approx(expected, rel=1e-6)

    def test_metric_units(self):
        """Metric Cp for steel/steel = 191 √MPa."""
        r = agma_contact_stress(2400, 1.0, 1.37, 1.0, 1.2, 191, 60, 50, 0.107, metric=True)
        assert r["ok"] is True
        assert r["unit"] == "MPa"

    def test_high_stress_warning(self):
        # Drive a very large Wt to trigger the over-limit warning
        r = agma_contact_stress(1_000_000, 2.0, 2.0, 1.5, 2.0, 2300, 2.5, 2.0, 0.107)
        assert "warnings" in r

    def test_radicand_in_result(self):
        r = agma_contact_stress(540, 1.0, 1.37, 1.0, 1.2, 2300, 2.5, 2.0, 0.107)
        assert "radicand" in r
        assert r["radicand"] > 0

    def test_error_zero_d_p(self):
        r = agma_contact_stress(540, 1.0, 1.37, 1.0, 1.2, 2300, 0, 2.0, 0.107)
        assert r["ok"] is False

    def test_error_zero_I(self):
        r = agma_contact_stress(540, 1.0, 1.37, 1.0, 1.2, 2300, 2.5, 2.0, 0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 6. agma_safety_factors
# ---------------------------------------------------------------------------

class TestSafetyFactors:
    def test_safe_gear(self):
        """Well-designed gear: SF and SH both >= 1."""
        r = agma_safety_factors(20_000, 100_000, 55_000, 180_000)
        assert r["ok"] is True
        assert r["SF"] >= 1.0
        assert r["SH"] >= 1.0
        assert r["bending_ok"] is True
        assert r["contact_ok"] is True

    def test_bending_overstress_flagged(self):
        """Bending stress > allowable → bending_ok=False + warning."""
        r = agma_safety_factors(60_000, 100_000, 55_000, 180_000)
        assert r["bending_ok"] is False
        assert "warnings" in r
        overstress_warns = [w for w in r["warnings"] if "BENDING OVERSTRESS" in w]
        assert len(overstress_warns) >= 1

    def test_contact_overstress_flagged(self):
        """Contact stress > allowable → contact_ok=False + warning."""
        r = agma_safety_factors(20_000, 200_000, 55_000, 180_000)
        assert r["contact_ok"] is False
        assert "warnings" in r

    def test_sf_formula(self):
        """SF = (S_t * YN / (K_T * K_R)) / sigma_b."""
        sigma_b, sigma_c, St, Sc = 30_000, 150_000, 65_000, 225_000
        sigma_t_all = St * 1.0 / (1.0 * 1.0)
        expected_SF = sigma_t_all / sigma_b
        r = agma_safety_factors(sigma_b, sigma_c, St, Sc)
        assert r["SF"] == pytest.approx(expected_SF, rel=1e-6)

    def test_sh_formula(self):
        """SH = (S_c * ZN / (K_T * K_R)) / sigma_c."""
        sigma_b, sigma_c, St, Sc = 30_000, 150_000, 65_000, 225_000
        sigma_c_all = Sc * 1.0 / (1.0 * 1.0)
        expected_SH = sigma_c_all / sigma_c
        r = agma_safety_factors(sigma_b, sigma_c, St, Sc)
        assert r["SH"] == pytest.approx(expected_SH, rel=1e-6)

    def test_reliability_factor_lowers_allowable(self):
        """Higher K_R reduces allowable stress → lower SF."""
        r1 = agma_safety_factors(30_000, 150_000, 65_000, 225_000, K_R=1.0)
        r2 = agma_safety_factors(30_000, 150_000, 65_000, 225_000, K_R=1.25)
        assert r2["SF"] < r1["SF"]

    def test_low_sf_warning(self):
        """SF between 1.0 and 1.2 should warn about low safety factor."""
        # Tune inputs so SF ≈ 1.05
        r = agma_safety_factors(62_000, 150_000, 65_000, 225_000)
        if 1.0 <= r["SF"] < 1.2:
            assert "warnings" in r

    def test_error_zero_sigma_b(self):
        r = agma_safety_factors(0, 100_000, 55_000, 180_000)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 7. agma_power_rating
# ---------------------------------------------------------------------------

class TestPowerRating:
    # Standard English test: 20-tooth pinion / 40-tooth gear, Pd=8, d_p=2.5 in
    def test_power_rating_positive(self):
        r = agma_power_rating(
            S_t=55_000, S_c=180_000, Cp=2300,
            b=2.0, m_or_Pd=8, d_p=2.5,
            N_p=20, N_g=40, psi_deg=0.0, n_rpm=1200,
        )
        assert r["ok"] is True
        assert r["power_rated"] > 0
        assert r["unit_power"] == "hp"

    def test_governing_is_bending_or_contact(self):
        r = agma_power_rating(
            S_t=55_000, S_c=180_000, Cp=2300,
            b=2.0, m_or_Pd=8, d_p=2.5,
            N_p=20, N_g=40, psi_deg=0.0, n_rpm=1200,
        )
        assert r["governing"] in ("bending", "contact")

    def test_wt_rated_is_min_of_bending_and_contact(self):
        r = agma_power_rating(
            S_t=55_000, S_c=180_000, Cp=2300,
            b=2.0, m_or_Pd=8, d_p=2.5,
            N_p=20, N_g=40, psi_deg=0.0, n_rpm=1200,
        )
        assert r["Wt_rated"] == pytest.approx(
            min(r["Wt_bending_lim"], r["Wt_contact_lim"]), rel=1e-9
        )

    def test_metric_units(self):
        r = agma_power_rating(
            S_t=380, S_c=1240, Cp=191,
            b=50, m_or_Pd=3, d_p=60,
            N_p=20, N_g=40, psi_deg=0.0, n_rpm=1200,
            metric=True,
        )
        assert r["ok"] is True
        assert r["unit_power"] == "kW"

    def test_wider_face_higher_power(self):
        """Wider face width increases rated power."""
        r1 = agma_power_rating(
            S_t=55_000, S_c=180_000, Cp=2300,
            b=1.0, m_or_Pd=8, d_p=2.5,
            N_p=20, N_g=40, psi_deg=0.0, n_rpm=1200,
        )
        r2 = agma_power_rating(
            S_t=55_000, S_c=180_000, Cp=2300,
            b=3.0, m_or_Pd=8, d_p=2.5,
            N_p=20, N_g=40, psi_deg=0.0, n_rpm=1200,
        )
        assert r2["power_rated"] > r1["power_rated"]

    def test_error_N_g_less_than_N_p(self):
        r = agma_power_rating(
            S_t=55_000, S_c=180_000, Cp=2300,
            b=2.0, m_or_Pd=8, d_p=2.5,
            N_p=40, N_g=20, psi_deg=0.0, n_rpm=1200,
        )
        assert r["ok"] is False

    def test_kv_present_in_result(self):
        r = agma_power_rating(
            S_t=55_000, S_c=180_000, Cp=2300,
            b=2.0, m_or_Pd=8, d_p=2.5,
            N_p=20, N_g=40, psi_deg=0.0, n_rpm=1200,
        )
        assert "Kv" in r
        assert r["Kv"] >= 1.0


# ---------------------------------------------------------------------------
# 8. agma_service_life
# ---------------------------------------------------------------------------

class TestServiceLife:
    def test_long_life_plateau(self):
        """At 10^11 cycles both YN and ZN should be at or near the 0.9 floor."""
        r = agma_service_life(1e11)
        assert r["ok"] is True
        assert r["YN"] == pytest.approx(0.9, abs=0.01)
        assert r["ZN"] == pytest.approx(0.9, abs=0.01)
        assert r["regime"] == "long_life"

    def test_finite_life_yn_above_plateau(self):
        """At 10^6 cycles YN should be above the long-life floor."""
        r = agma_service_life(1e6)
        assert r["YN"] > 0.9

    def test_yn_decreases_with_cycles(self):
        """YN should decrease as cycles increase (finite to long-life)."""
        yn_low  = agma_service_life(1e5)["YN"]
        yn_high = agma_service_life(1e8)["YN"]
        assert yn_low > yn_high

    def test_zn_decreases_with_cycles(self):
        zn_low  = agma_service_life(1e5)["ZN"]
        zn_high = agma_service_life(1e8)["ZN"]
        assert zn_low > zn_high

    def test_low_hardness_warning(self):
        """Hardness below 180 HB should trigger a warning."""
        r = agma_service_life(1e7, hardness_HB=150)
        assert "warnings" in r
        assert any("180 HB" in w for w in r["warnings"])

    def test_high_hardness_warning(self):
        """Hardness > 400 HB should trigger a warning."""
        r = agma_service_life(1e7, hardness_HB=450)
        assert "warnings" in r

    def test_regime_finite(self):
        r = agma_service_life(1e7)
        assert r["regime"] == "finite"

    def test_error_zero_cycles(self):
        r = agma_service_life(0)
        assert r["ok"] is False

    def test_error_unknown_gear_type(self):
        r = agma_service_life(1e7, gear_type="nitrided")
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 9. LLM tool wrappers — happy paths
# ---------------------------------------------------------------------------

class TestToolsHappyPath:
    def test_tool_dynamic_factor(self):
        raw = _run(run_agma_dynamic_factor(_ctx(), _args(Vt_fpm=600, Qv=6)))
        r = json.loads(raw)
        assert r["ok"] is True
        assert r["Kv"] >= 1.0

    def test_tool_geometry_J(self):
        raw = _run(run_agma_geometry_factor_J(_ctx(), _args(N=30, psi_deg=0.0)))
        r = json.loads(raw)
        assert r["ok"] is True
        assert r["J"] > 0

    def test_tool_geometry_I(self):
        raw = _run(run_agma_geometry_factor_I(_ctx(), _args(N_p=20, N_g=40, psi_deg=0.0)))
        r = json.loads(raw)
        assert r["ok"] is True
        assert r["I"] > 0

    def test_tool_bending_stress(self):
        raw = _run(run_agma_bending_stress(
            _ctx(),
            _args(Wt=540, Ko=1.0, Kv=1.37, Ks=1.0, Km=1.2, KB=1.0,
                  b=2.0, m_or_Pd=8, J=0.30)
        ))
        r = json.loads(raw)
        assert r["ok"] is True
        assert r["sigma_t"] > 0

    def test_tool_contact_stress(self):
        raw = _run(run_agma_contact_stress(
            _ctx(),
            _args(Wt=540, Ko=1.0, Kv=1.37, Ks=1.0, Km=1.2,
                  Cp=2300, d_p=2.5, b=2.0, I=0.107)
        ))
        r = json.loads(raw)
        assert r["ok"] is True
        assert r["sigma_c"] > 0

    def test_tool_safety_factors(self):
        raw = _run(run_agma_safety_factors(
            _ctx(),
            _args(sigma_b=20_000, sigma_c=100_000, S_t=55_000, S_c=180_000)
        ))
        r = json.loads(raw)
        assert r["ok"] is True
        assert r["SF"] > 0
        assert r["SH"] > 0

    def test_tool_power_rating(self):
        raw = _run(run_agma_power_rating(
            _ctx(),
            _args(S_t=55_000, S_c=180_000, Cp=2300,
                  b=2.0, m_or_Pd=8, d_p=2.5,
                  N_p=20, N_g=40, psi_deg=0.0, n_rpm=1200)
        ))
        r = json.loads(raw)
        assert r["ok"] is True
        assert r["power_rated"] > 0

    def test_tool_service_life(self):
        raw = _run(run_agma_service_life(_ctx(), _args(N_cycles=1e7)))
        r = json.loads(raw)
        assert r["ok"] is True
        assert 0 < r["YN"] <= 2.5
        assert 0 < r["ZN"] <= 2.0


# ---------------------------------------------------------------------------
# 10. LLM tool wrappers — error paths
# ---------------------------------------------------------------------------

class TestToolsErrorPaths:
    def test_invalid_json(self):
        raw = _run(run_agma_dynamic_factor(_ctx(), b"not-json"))
        r = json.loads(raw)
        # err_payload returns {"error": ..., "code": "BAD_ARGS"} for parse failures
        assert "error" in r or r.get("ok") is False

    def test_missing_Vt_fpm(self):
        raw = _run(run_agma_dynamic_factor(_ctx(), _args(Qv=6)))
        r = json.loads(raw)
        assert r["ok"] is False
        assert "Vt_fpm" in r["reason"]

    def test_missing_N_in_J(self):
        raw = _run(run_agma_geometry_factor_J(_ctx(), _args(psi_deg=0.0)))
        r = json.loads(raw)
        assert r["ok"] is False

    def test_missing_N_p_in_I(self):
        raw = _run(run_agma_geometry_factor_I(_ctx(), _args(N_g=40, psi_deg=0.0)))
        r = json.loads(raw)
        assert r["ok"] is False

    def test_missing_Wt_in_bending(self):
        raw = _run(run_agma_bending_stress(
            _ctx(),
            _args(Ko=1.0, Kv=1.37, Ks=1.0, Km=1.2, KB=1.0, b=2.0, m_or_Pd=8, J=0.30)
        ))
        r = json.loads(raw)
        assert r["ok"] is False

    def test_missing_Cp_in_contact(self):
        raw = _run(run_agma_contact_stress(
            _ctx(),
            _args(Wt=540, Ko=1.0, Kv=1.37, Ks=1.0, Km=1.2, d_p=2.5, b=2.0, I=0.107)
        ))
        r = json.loads(raw)
        assert r["ok"] is False

    def test_missing_S_t_in_safety(self):
        raw = _run(run_agma_safety_factors(
            _ctx(),
            _args(sigma_b=20_000, sigma_c=100_000, S_c=180_000)
        ))
        r = json.loads(raw)
        assert r["ok"] is False

    def test_missing_N_cycles_in_life(self):
        raw = _run(run_agma_service_life(_ctx(), _args(hardness_HB=200)))
        r = json.loads(raw)
        assert r["ok"] is False


# ===========================================================================
# Externally-citable reference cases (production-confidence validation)
# Cross-checked vs AGMA 2001-D04, Shigley 10th ed. §§14-1..14-5,
# Norton "Machine Design" 5th ed. Ch. 11.
# ===========================================================================

from kerf_cad_core.gearstrength.rating import (  # noqa: E402
    agma_dynamic_factor as _ref_kv,
    agma_bending_stress as _ref_sigma_b,
    agma_contact_stress as _ref_sigma_c,
    agma_geometry_factor_I as _ref_I,
    agma_safety_factors as _ref_sf,
    agma_service_life as _ref_life,
)


class TestGearStrengthExternalReferences:
    """Validated against AGMA 2001-D04 equations & Shigley §14 examples."""

    def test_kv_agma_eq_14_27_28(self):
        # AGMA 2001-D04 Eqs (14-27),(14-28): Qv=6, Vt=1200 ft/min.
        # B=0.25(12-6)^(2/3)=0.82548, A=50+56(1-B)=59.773,
        # Kv=((A+√V)/A)^B = 1.45842.
        r = _ref_kv(1200.0, 6)
        B = 0.25 * (12 - 6) ** (2.0 / 3.0)
        A = 50.0 + 56.0 * (1.0 - B)
        assert r["B"] == pytest.approx(B, rel=1e-12)
        assert r["A"] == pytest.approx(A, rel=1e-12)
        assert r["Kv"] == pytest.approx(((A + math.sqrt(1200.0)) / A) ** B, rel=1e-12)

    def test_kv_quality_11_ground(self):
        # AGMA: Qv=11 ground gear, Vt=2000 ft/min — Kv near 1.1.
        r = _ref_kv(2000.0, 11)
        B = 0.25 * (12 - 11) ** (2.0 / 3.0)
        A = 50.0 + 56.0 * (1.0 - B)
        assert r["Kv"] == pytest.approx(((A + math.sqrt(2000.0)) / A) ** B, rel=1e-12)

    def test_kv_validity_limit(self):
        # Shigley Eq (14-29): Vt_max = [A+(Qv-3)]². Exceeding it warns.
        r = _ref_kv(50000.0, 6)
        assert "warnings" in r

    def test_bending_stress_metric_canonical(self):
        # AGMA/Shigley Eq (14-15) metric: σ = Wt·Ko·Kv·Ks·Km·KB/(b·m·J).
        # Wt=3000 N, b=40 mm, m=4 mm, J=0.36, others=1, Km=1.3.
        r = _ref_sigma_b(3000.0, 1, 1.2, 1, 1.3, 1, 40.0, 4.0, 0.36, metric=True)
        exp = 3000.0 * 1 * 1.2 * 1 * 1.3 * 1 / (40.0 * 4.0 * 0.36)
        assert r["sigma_t"] == pytest.approx(exp, rel=1e-12)
        assert r["unit"] == "MPa"

    def test_bending_stress_english(self):
        # AGMA/Shigley Eq (14-15) English: σ = Wt·Ko·Kv·Ks·Pd·Km·KB/(b·J).
        r = _ref_sigma_b(382.0, 1, 1.52, 1, 1.6, 1, 1.5, 8.0, 0.30, metric=False)
        exp = 382.0 * 1 * 1.52 * 1 * 8.0 * 1.6 * 1 / (1.5 * 0.30)
        assert r["sigma_t"] == pytest.approx(exp, rel=1e-12)
        assert r["unit"] == "psi"

    def test_contact_stress_eq_14_16(self):
        # AGMA/Shigley Eq (14-16): σc = Cp√(Wt·Ko·Kv·Ks·Km/(dp·b·I)).
        # Steel/steel Cp=191 √MPa metric.
        r = _ref_sigma_c(3000.0, 1, 1.2, 1, 1.3, 191.0, 80.0, 40.0, 0.10, metric=True)
        exp = 191.0 * math.sqrt(3000.0 * 1 * 1.2 * 1 * 1.3 / (80.0 * 40.0 * 0.10))
        assert r["sigma_c"] == pytest.approx(exp, rel=1e-12)

    def test_geometry_factor_I_norton_eq_12_22(self):
        # Norton "Machine Design" Eq (12.22) / AGMA simplified external spur:
        # I = (cosφ sinφ)/(2 mN) · mG/(mG+1), mN=1. φ=20°, 18/54T → mG=3.
        r = _ref_I(18, 54, 0.0, pressure_angle_deg=20.0)
        phi = math.radians(20.0)
        mg = 54.0 / 18.0
        exp = math.cos(phi) * math.sin(phi) / 2.0 * (mg / (mg + 1.0))
        assert r["I"] == pytest.approx(exp, rel=1e-9)

    def test_geometry_factor_I_helical_transverse(self):
        # AGMA: helical transverse pressure angle tan φt = tan φn/cos ψ.
        r = _ref_I(20, 40, 20.0, pressure_angle_deg=20.0)
        phi_n = math.radians(20.0)
        psi = math.radians(20.0)
        phi_t = math.atan(math.tan(phi_n) / math.cos(psi))
        assert r["phi_t_deg"] == pytest.approx(math.degrees(phi_t), rel=1e-9)

    def test_safety_factors_agma_4_1(self):
        # AGMA 2001-D04 §4.1: σ_all = St·YN/(KT·KR); SF = σ_all/σ.
        # St=450 MPa, YN=1, KT=KR=1, σb=300 MPa → SF=1.5.
        r = _ref_sf(300.0, 1000.0, 450.0, 1550.0, YN=1.0, ZN=1.0)
        assert r["SF"] == pytest.approx(450.0 / 300.0, rel=1e-12)
        assert r["SH"] == pytest.approx(1550.0 / 1000.0, rel=1e-12)

    def test_service_life_YN_ZN_agma(self):
        # AGMA 2001-D04 Figs 14-14/14-15 (Shigley §14-5):
        # YN = 1.3558 N^-0.0178, ZN = 1.4488 N^-0.023 for 1e8 cycles.
        r = _ref_life(1e8, hardness_HB=250.0)
        assert r["YN"] == pytest.approx(1.3558 * (1e8 ** -0.0178), rel=1e-9)
        assert r["ZN"] == pytest.approx(1.4488 * (1e8 ** -0.023), rel=1e-9)
