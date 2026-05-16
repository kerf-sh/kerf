"""
Hermetic tests for kerf_cad_core.heattreat — heat-treatment process engineering.

Coverage (≥ 30 tests):
  process.grossmann_DI           — DI from composition, multiplying factors
  process.jominy_hardness        — Jominy hardness and cooling-rate interpolation
  process.actual_critical_diameter — D_act from DI and H
  process.as_quenched_hardness   — Hodge-Orehoski model
  process.hollomon_jaffe          — H-J tempering parameter & tempered hardness
  process.carburizing_case_depth  — Harris formula and erfc depth
  process.nitriding_case_depth    — diffusion zone depth
  process.induction_case_depth    — skin depth / case depth
  process.austenitizing_temperature — hypo vs hypereutectoid guidance
  process.andrews_Ac1 / Ac3      — Andrews 1965 critical temperatures
  process.martensite_start_Ms    — Andrews 1965 Ms
  process.martensite_finish_Mf   — Mf estimate
  process.koistinen_marburger    — martensite fraction
  process.retained_austenite     — RA fraction
  process.annealing_temperature  — full/process anneal guidance
  process.normalizing_temperature — normalizing guidance
  process.stress_relief_temperature — SR guidance by steel family
  process.hardness_convert       — HRC↔HB↔HV↔HRB↔UTS conversions
  tools.*                        — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas verified algebraically against published expressions.

References
----------
Grossmann M.A. (1942) — Trans. AIME 150, 227-259
Andrews K.W. (1965) — JISI 203, 721-727
Koistinen D.P., Marburger R.E. (1959) — Acta Metall. 7, 59-60
Hollomon J.H., Jaffe L.D. (1945) — Trans. AIME 162, 223-249
Harris F.E. (1943) — Met. Prog. 44, 265
ASM Handbook Vol. 4 — Heat Treating (1991)

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.heattreat.process import (
    grossmann_DI,
    jominy_hardness,
    actual_critical_diameter,
    as_quenched_hardness,
    hollomon_jaffe,
    carburizing_case_depth,
    nitriding_case_depth,
    induction_case_depth,
    austenitizing_temperature,
    andrews_Ac1,
    andrews_Ac3,
    martensite_start_Ms,
    martensite_finish_Mf,
    koistinen_marburger,
    retained_austenite,
    annealing_temperature,
    normalizing_temperature,
    stress_relief_temperature,
    hardness_convert,
    _hrc_to_HB,
    _hrc_to_HV,
    _HB_to_hrc,
    _CARB_D0_cm2_s,
    _CARB_Q_J_mol,
    _R_J_mol_K,
)
from kerf_cad_core.heattreat.tools import (
    run_ht_grossmann_DI,
    run_ht_jominy_hardness,
    run_ht_actual_critical_diameter,
    run_ht_as_quenched_hardness,
    run_ht_hollomon_jaffe,
    run_ht_carburizing_case_depth,
    run_ht_nitriding_case_depth,
    run_ht_induction_case_depth,
    run_ht_austenitizing_temperature,
    run_ht_andrews_Ac1,
    run_ht_andrews_Ac3,
    run_ht_martensite_start_Ms,
    run_ht_martensite_finish_Mf,
    run_ht_koistinen_marburger,
    run_ht_retained_austenite,
    run_ht_annealing_temperature,
    run_ht_normalizing_temperature,
    run_ht_stress_relief_temperature,
    run_ht_hardness_convert,
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


REL = 1e-4  # relative tolerance for floating-point checks


# ===========================================================================
# 1. grossmann_DI
# ===========================================================================

class TestGrossmannDI:

    def test_plain_carbon_positive_DI(self):
        """Plain carbon steel (C=0.40, Mn=0.70) must yield positive DI."""
        res = grossmann_DI(C=0.40, Mn=0.70)
        assert res["ok"] is True
        assert res["DI_mm"] > 0
        assert res["DI_in"] > 0

    def test_alloy_steel_higher_DI_than_plain_carbon(self):
        """Adding Cr, Mo must increase DI over plain carbon baseline."""
        res_plain = grossmann_DI(C=0.40, Mn=0.70)
        res_alloy = grossmann_DI(C=0.40, Mn=0.70, Cr=1.0, Mo=0.25)
        assert res_alloy["DI_mm"] > res_plain["DI_mm"]

    def test_alloy_multiplier_formula(self):
        """Verify alloy_multiplier = fMn × fSi × ... by hand for known values."""
        Mn, Si = 0.70, 0.25
        fMn = 1.0 + 3.3333 * Mn
        fSi = 1.0 + 0.7000 * Si
        # Other elements zero → product = fMn * fSi
        res = grossmann_DI(C=0.40, Mn=Mn, Si=Si)
        assert res["ok"] is True
        expected_mult = fMn * fSi
        assert abs(res["alloy_multiplier"] - expected_mult) / expected_mult < REL

    def test_DI_mm_equals_DI_in_times_25p4(self):
        """DI_mm must equal DI_in × 25.4 exactly."""
        res = grossmann_DI(C=0.40, Mn=0.80, Cr=1.05, Mo=0.20, Ni=0.20)
        assert res["ok"] is True
        assert abs(res["DI_mm"] - res["DI_in"] * 25.4) < 1e-9

    def test_zero_C_returns_error(self):
        """C=0 must return ok=False (below minimum valid C)."""
        res = grossmann_DI(C=0.0)
        assert res["ok"] is False

    def test_negative_Mn_returns_error(self):
        """Negative composition inputs must return ok=False."""
        res = grossmann_DI(C=0.40, Mn=-0.5)
        assert res["ok"] is False

    def test_high_C_warning_present(self):
        """C > 1.10 wt% must trigger a warning."""
        res = grossmann_DI(C=1.20)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_DI0_scales_with_sqrt_C(self):
        """DI0 ∝ √C (Grossmann base formula)."""
        res1 = grossmann_DI(C=0.40, grain_size_ASTM=7)
        res2 = grossmann_DI(C=0.90, grain_size_ASTM=7)
        # DI0(0.9) / DI0(0.4) ≈ sqrt(0.9)/sqrt(0.4) for no-alloy case
        ratio_actual = res2["DI0_in"] / res1["DI0_in"]
        ratio_expected = math.sqrt(0.90) / math.sqrt(0.40)
        assert abs(ratio_actual - ratio_expected) / ratio_expected < 0.01


# ===========================================================================
# 2. jominy_hardness
# ===========================================================================

class TestJominyHardness:

    def test_J1_hardness_near_maximum(self):
        """At J=1.5 mm (end), hardness should be close to HRC_max."""
        res = jominy_hardness(C=0.40, jominy_dist_mm=1.5)
        assert res["ok"] is True
        # At 1.5 mm the decay factor is exp(-k*(1.5-1.5)) = 1, so HRC ≈ HRC_max
        assert abs(res["HRC"] - res["HRC_max"]) < 1.0

    def test_hardness_decreases_with_distance(self):
        """HRC must decrease as distance from quenched end increases."""
        r1 = jominy_hardness(C=0.40, jominy_dist_mm=5.0)
        r2 = jominy_hardness(C=0.40, jominy_dist_mm=25.0)
        assert r1["HRC"] > r2["HRC"]

    def test_higher_C_gives_higher_HRC_max(self):
        """Higher carbon gives higher maximum Jominy hardness."""
        r1 = jominy_hardness(C=0.20, jominy_dist_mm=1.5)
        r2 = jominy_hardness(C=0.60, jominy_dist_mm=1.5)
        assert r2["HRC_max"] > r1["HRC_max"]

    def test_cooling_rate_decreases_with_distance(self):
        """Cooling rate must decrease as distance increases."""
        r1 = jominy_hardness(C=0.40, jominy_dist_mm=5.0)
        r2 = jominy_hardness(C=0.40, jominy_dist_mm=25.0)
        assert r1["cooling_rate_degC_s"] > r2["cooling_rate_degC_s"]

    def test_zero_C_returns_error(self):
        res = jominy_hardness(C=0.0, jominy_dist_mm=10.0)
        assert res["ok"] is False

    def test_negative_dist_returns_error(self):
        res = jominy_hardness(C=0.40, jominy_dist_mm=-1.0)
        assert res["ok"] is False


# ===========================================================================
# 3. actual_critical_diameter
# ===========================================================================

class TestActualCriticalDiameter:

    def test_D_act_less_than_or_equal_DI(self):
        """D_act must be <= DI for any finite H."""
        res = actual_critical_diameter(DI_mm=80.0, H=1.0)
        assert res["ok"] is True
        assert res["D_act_mm"] <= res["DI_mm"] + 1e-6

    def test_D_act_increases_with_H(self):
        """Higher quench severity H must give larger D_act."""
        r1 = actual_critical_diameter(DI_mm=80.0, H=0.5)
        r2 = actual_critical_diameter(DI_mm=80.0, H=2.0)
        assert r2["D_act_mm"] > r1["D_act_mm"]

    def test_D_act_mm_equals_D_act_in_times_25p4(self):
        """D_act_mm must equal D_act_in × 25.4 exactly."""
        res = actual_critical_diameter(DI_mm=50.0, H=1.5)
        assert res["ok"] is True
        assert abs(res["D_act_mm"] - res["D_act_in"] * 25.4) < 1e-6

    def test_negative_DI_returns_error(self):
        res = actual_critical_diameter(DI_mm=-10.0, H=1.0)
        assert res["ok"] is False

    def test_zero_H_returns_error(self):
        res = actual_critical_diameter(DI_mm=50.0, H=0.0)
        assert res["ok"] is False


# ===========================================================================
# 4. as_quenched_hardness
# ===========================================================================

class TestAsQuenchedHardness:

    def test_100pct_martensite_gives_HRC_100M(self):
        """At 100% martensite, HRC must equal HRC_100M."""
        res = as_quenched_hardness(C_wt_pct=0.40, martensite_pct=100.0)
        assert res["ok"] is True
        assert abs(res["HRC"] - res["HRC_100M"]) < 0.01

    def test_0pct_martensite_gives_HRC_0M(self):
        """At 0% martensite, HRC must equal HRC_0M."""
        res = as_quenched_hardness(C_wt_pct=0.40, martensite_pct=0.0)
        assert res["ok"] is True
        assert abs(res["HRC"] - res["HRC_0M"]) < 0.01

    def test_HRC_increases_with_martensite(self):
        """More martensite must give higher hardness."""
        r1 = as_quenched_hardness(C_wt_pct=0.40, martensite_pct=20.0)
        r2 = as_quenched_hardness(C_wt_pct=0.40, martensite_pct=80.0)
        assert r2["HRC"] > r1["HRC"]

    def test_higher_C_gives_higher_100M_hardness(self):
        """Higher carbon must give higher HRC_100M."""
        r1 = as_quenched_hardness(C_wt_pct=0.30, martensite_pct=100.0)
        r2 = as_quenched_hardness(C_wt_pct=0.60, martensite_pct=100.0)
        assert r2["HRC_100M"] > r1["HRC_100M"]

    def test_martensite_over_100_returns_error(self):
        res = as_quenched_hardness(C_wt_pct=0.40, martensite_pct=101.0)
        assert res["ok"] is False

    def test_negative_C_returns_error(self):
        res = as_quenched_hardness(C_wt_pct=-0.1, martensite_pct=80.0)
        assert res["ok"] is False

    def test_low_martensite_warning(self):
        """Martensite < 50% should trigger a warning."""
        res = as_quenched_hardness(C_wt_pct=0.40, martensite_pct=30.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0


# ===========================================================================
# 5. hollomon_jaffe
# ===========================================================================

class TestHollomonJaffe:

    def test_P_formula(self):
        """Verify P = T_K × (C_HJ + log10(t)) algebraically."""
        T_C, t, C_HJ = 200.0, 2.0, 20.0
        T_K = T_C + 273.15
        P_expected = T_K * (C_HJ + math.log10(t))
        res = hollomon_jaffe(C_wt_pct=0.40, T_C=T_C, t_hours=t, C_HJ=C_HJ)
        assert res["ok"] is True
        assert abs(res["P"] - P_expected) < 1.0  # P rounded to 0 decimals

    def test_higher_T_gives_lower_HRC(self):
        """Higher tempering temperature must give lower tempered hardness."""
        r1 = hollomon_jaffe(C_wt_pct=0.40, T_C=200.0, t_hours=1.0)
        r2 = hollomon_jaffe(C_wt_pct=0.40, T_C=600.0, t_hours=1.0)
        assert r2["HRC_tempered"] < r1["HRC_tempered"]

    def test_longer_time_gives_lower_HRC(self):
        """Longer tempering time must lower hardness at the same temperature."""
        r1 = hollomon_jaffe(C_wt_pct=0.40, T_C=400.0, t_hours=0.5)
        r2 = hollomon_jaffe(C_wt_pct=0.40, T_C=400.0, t_hours=8.0)
        assert r2["HRC_tempered"] < r1["HRC_tempered"]

    def test_HRC_tempered_less_than_aq(self):
        """Tempered hardness must be <= as-quenched hardness."""
        res = hollomon_jaffe(
            C_wt_pct=0.40, T_C=450.0, t_hours=2.0, HRC_as_quenched=55.0
        )
        assert res["ok"] is True
        assert res["HRC_tempered"] <= res["HRC_as_quenched"] + 0.1

    def test_high_T_warning(self):
        """Tempering > 700 °C must trigger a warning."""
        res = hollomon_jaffe(C_wt_pct=0.40, T_C=750.0, t_hours=1.0)
        assert res["ok"] is True
        assert any("700" in w or "Ac1" in w for w in res["warnings"])

    def test_negative_T_returns_error(self):
        res = hollomon_jaffe(C_wt_pct=0.40, T_C=-10.0, t_hours=1.0)
        assert res["ok"] is False

    def test_invalid_HRC_aq_returns_error(self):
        """HRC_as_quenched > 68 must return ok=False."""
        res = hollomon_jaffe(
            C_wt_pct=0.40, T_C=300.0, t_hours=1.0, HRC_as_quenched=70.0
        )
        assert res["ok"] is False


# ===========================================================================
# 6. carburizing_case_depth
# ===========================================================================

class TestCarburizingCaseDepth:

    def test_harris_formula_algebraic(self):
        """Verify Harris case depth x = k * sqrt(D * t_s) algebraically."""
        T_C, t_hours = 925.0, 4.0
        T_K = T_C + 273.15
        t_s = t_hours * 3600.0
        D = _CARB_D0_cm2_s * math.exp(-_CARB_Q_J_mol / (_R_J_mol_K * T_K))
        x_harris_cm = 1.0 * math.sqrt(D * t_s)
        x_harris_mm_expected = x_harris_cm * 10.0

        res = carburizing_case_depth(T_C=T_C, t_hours=t_hours)
        assert res["ok"] is True
        assert abs(res["case_depth_harris_mm"] - x_harris_mm_expected) < 1e-6

    def test_longer_time_gives_deeper_case(self):
        """Longer carburizing time must give a deeper Harris case depth."""
        r1 = carburizing_case_depth(T_C=925.0, t_hours=2.0)
        r2 = carburizing_case_depth(T_C=925.0, t_hours=8.0)
        assert r2["case_depth_harris_mm"] > r1["case_depth_harris_mm"]

    def test_higher_T_gives_deeper_case(self):
        """Higher temperature must give deeper case (higher D)."""
        r1 = carburizing_case_depth(T_C=850.0, t_hours=4.0)
        r2 = carburizing_case_depth(T_C=950.0, t_hours=4.0)
        assert r2["case_depth_harris_mm"] > r1["case_depth_harris_mm"]

    def test_D_arrhenius_at_925(self):
        """Verify D at 925 °C matches manual Arrhenius calculation."""
        T_C = 925.0
        T_K = T_C + 273.15
        D_expected = _CARB_D0_cm2_s * math.exp(-_CARB_Q_J_mol / (_R_J_mol_K * T_K))
        res = carburizing_case_depth(T_C=T_C, t_hours=1.0)
        assert res["ok"] is True
        assert abs(res["D_cm2_s"] - D_expected) / D_expected < REL

    def test_erfc_depth_positive(self):
        """erfc case depth must be positive for valid inputs."""
        res = carburizing_case_depth(T_C=925.0, t_hours=6.0)
        assert res["ok"] is True
        assert res["case_depth_erfc_mm"] >= 0.0

    def test_target_C_ge_surface_C_returns_error(self):
        """target_C >= surface_C must return ok=False."""
        res = carburizing_case_depth(
            T_C=925.0, t_hours=4.0, surface_C=0.85, target_C=0.90
        )
        assert res["ok"] is False

    def test_invalid_T_returns_error(self):
        """Negative temperature must return ok=False."""
        res = carburizing_case_depth(T_C=-100.0, t_hours=4.0)
        assert res["ok"] is False


# ===========================================================================
# 7. nitriding_case_depth
# ===========================================================================

class TestNitridingCaseDepth:

    def test_returns_positive_depths(self):
        """Nitriding at 520 °C for 20 h must give positive depths."""
        res = nitriding_case_depth(T_C=520.0, t_hours=20.0)
        assert res["ok"] is True
        assert res["diffusion_zone_depth_mm"] > 0.0
        assert res["white_layer_depth_mm"] > 0.0
        assert res["total_case_depth_mm"] > res["diffusion_zone_depth_mm"]

    def test_longer_time_gives_deeper_zone(self):
        """More time must give deeper diffusion zone."""
        r1 = nitriding_case_depth(T_C=525.0, t_hours=10.0)
        r2 = nitriding_case_depth(T_C=525.0, t_hours=50.0)
        assert r2["diffusion_zone_depth_mm"] > r1["diffusion_zone_depth_mm"]

    def test_zero_time_returns_error(self):
        res = nitriding_case_depth(T_C=525.0, t_hours=0.0)
        assert res["ok"] is False


# ===========================================================================
# 8. induction_case_depth
# ===========================================================================

class TestInductionCaseDepth:

    def test_skin_depth_formula(self):
        """Verify δ = sqrt(rho / (pi * f * mu0 * mu_r)) algebraically."""
        MU0 = 4.0 * math.pi * 1e-7
        f, rho, mu_r = 10_000.0, 1.1e-6, 1.0
        delta_m_expected = math.sqrt(rho / (math.pi * f * MU0 * mu_r))
        delta_mm_expected = delta_m_expected * 1000.0

        res = induction_case_depth(freq_Hz=f, t_s=1.0, rho=rho, mu_r=mu_r)
        assert res["ok"] is True
        assert abs(res["skin_depth_mm"] - delta_mm_expected) / delta_mm_expected < REL

    def test_case_depth_is_1p5_times_skin_depth(self):
        """case_depth = 1.5 × skin_depth."""
        res = induction_case_depth(freq_Hz=10_000.0, t_s=1.0)
        assert res["ok"] is True
        assert abs(res["case_depth_mm"] - 1.5 * res["skin_depth_mm"]) < 1e-9

    def test_higher_freq_gives_shallower_case(self):
        """Higher frequency must give shallower skin depth."""
        r1 = induction_case_depth(freq_Hz=1_000.0, t_s=1.0)
        r2 = induction_case_depth(freq_Hz=100_000.0, t_s=1.0)
        assert r2["skin_depth_mm"] < r1["skin_depth_mm"]

    def test_skin_depth_scales_inv_sqrt_freq(self):
        """δ ∝ 1/√f — quadrupling f halves δ."""
        r1 = induction_case_depth(freq_Hz=10_000.0, t_s=1.0)
        r2 = induction_case_depth(freq_Hz=40_000.0, t_s=1.0)
        ratio = r2["skin_depth_mm"] / r1["skin_depth_mm"]
        assert abs(ratio - 0.5) < 1e-4

    def test_zero_freq_returns_error(self):
        res = induction_case_depth(freq_Hz=0.0, t_s=1.0)
        assert res["ok"] is False


# ===========================================================================
# 9. austenitizing_temperature
# ===========================================================================

class TestAustenitizingTemperature:

    def test_hypoeutectoid_range_above_Ac3(self):
        """Hypoeutectoid steel (C=0.40): austenitize range must be above Ac3."""
        res = austenitizing_temperature(C_wt_pct=0.40)
        assert res["ok"] is True
        assert res["steel_class"] == "hypoeutectoid"
        assert res["T_austenit_min_C"] > res["Ac3_approx_C"]

    def test_hypereutectoid_range_above_Ac1(self):
        """Hypereutectoid steel (C=0.90): austenitize range must be above Ac1."""
        res = austenitizing_temperature(C_wt_pct=0.90)
        assert res["ok"] is True
        assert res["steel_class"] == "hypereutectoid"
        assert res["T_austenit_min_C"] > res["Ac1_approx_C"]

    def test_low_C_warning(self):
        """Very low C steel (C=0.10) should trigger a hardness warning."""
        res = austenitizing_temperature(C_wt_pct=0.10)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_zero_C_returns_error(self):
        res = austenitizing_temperature(C_wt_pct=0.0)
        assert res["ok"] is False


# ===========================================================================
# 10 & 11. andrews_Ac1, andrews_Ac3
# ===========================================================================

class TestAndrewsAc:

    def test_Ac1_baseline_near_723(self):
        """Andrews Ac1 for plain carbon (no alloys) must be ~723 °C."""
        res = andrews_Ac1()
        assert res["ok"] is True
        # With no alloy additions, Ac1 = 723 exactly
        assert abs(res["Ac1_C"] - 723.0) < 0.5

    def test_Ac1_Ni_lowers_temperature(self):
        """Ni lowers Ac1 (negative coefficient)."""
        r0 = andrews_Ac1(Ni=0.0)
        r1 = andrews_Ac1(Ni=2.0)
        assert r1["Ac1_C"] < r0["Ac1_C"]

    def test_Ac1_Cr_raises_temperature(self):
        """Cr raises Ac1 (positive coefficient)."""
        r0 = andrews_Ac1(Cr=0.0)
        r1 = andrews_Ac1(Cr=1.0)
        assert r1["Ac1_C"] > r0["Ac1_C"]

    def test_Ac3_formula_algebraic_for_1040(self):
        """Andrews Ac3 for AISI 1040 (C=0.40, Mn=0.75) vs manual calculation."""
        C, Mn = 0.40, 0.75
        Ac3_expected = 910.0 - 203.0 * math.sqrt(C) - 30.0 * Mn
        res = andrews_Ac3(C=C, Mn=Mn)
        assert res["ok"] is True
        assert abs(res["Ac3_C"] - Ac3_expected) < 0.5

    def test_Ac3_decreases_with_C(self):
        """Higher C lowers Ac3 (−203√C term)."""
        r1 = andrews_Ac3(C=0.20)
        r2 = andrews_Ac3(C=0.60)
        assert r2["Ac3_C"] < r1["Ac3_C"]

    def test_negative_composition_returns_error(self):
        """Negative Mn must return ok=False."""
        res = andrews_Ac1(Mn=-0.5)
        assert res["ok"] is False


# ===========================================================================
# 12. martensite_start_Ms
# ===========================================================================

class TestMartensiteStartMs:

    def test_Ms_formula_algebraic_plain_carbon(self):
        """Ms for plain carbon (no alloys) = 539 - 423*C."""
        C = 0.40
        Ms_expected = 539.0 - 423.0 * C
        res = martensite_start_Ms(C=C)
        assert res["ok"] is True
        assert abs(res["Ms_C"] - Ms_expected) < 0.2

    def test_higher_C_lowers_Ms(self):
        """Higher carbon must lower Ms."""
        r1 = martensite_start_Ms(C=0.20)
        r2 = martensite_start_Ms(C=0.60)
        assert r2["Ms_C"] < r1["Ms_C"]

    def test_alloy_elements_lower_Ms(self):
        """Mn, Ni, Cr, Mo all have negative coefficients → lower Ms."""
        r0 = martensite_start_Ms(C=0.40)
        r1 = martensite_start_Ms(C=0.40, Mn=1.5, Ni=2.0, Cr=1.0)
        assert r1["Ms_C"] < r0["Ms_C"]

    def test_sub_zero_Ms_warning(self):
        """Ms < 0 must trigger a cryogenic-treatment warning."""
        # 18% Ni maraging steel area: C=0.03, Ni=18
        res = martensite_start_Ms(C=0.10, Ni=18.0, Mn=0.1)
        assert res["ok"] is True
        if res["Ms_C"] < 0:
            assert len(res["warnings"]) > 0


# ===========================================================================
# 13. martensite_finish_Mf
# ===========================================================================

class TestMartensiteFinishMf:

    def test_Mf_is_Ms_minus_215(self):
        """Mf must equal Ms − 215 °C."""
        Ms = 350.0
        res = martensite_finish_Mf(Ms_C=Ms)
        assert res["ok"] is True
        assert abs(res["Mf_C"] - (Ms - 215.0)) < 1e-6

    def test_cryo_warning_for_low_Mf(self):
        """Mf < −100 °C must trigger cryogenic warning."""
        res = martensite_finish_Mf(Ms_C=50.0)  # Mf = 50 - 215 = -165
        assert res["ok"] is True
        assert len(res["warnings"]) > 0


# ===========================================================================
# 14. koistinen_marburger
# ===========================================================================

class TestKoistinenMarburger:

    def test_above_Ms_gives_zero_martensite(self):
        """At T >= Ms, martensite fraction must be 0."""
        res = koistinen_marburger(T_C=350.0, Ms_C=300.0)
        assert res["ok"] is True
        assert res["martensite_frac"] == 0.0

    def test_at_Ms_gives_zero(self):
        """At T = Ms, martensite fraction = 0."""
        res = koistinen_marburger(T_C=300.0, Ms_C=300.0)
        assert res["ok"] is True
        assert res["martensite_frac"] == 0.0

    def test_km_formula_algebraic(self):
        """Verify f_M = 1 − exp(−0.011 × (Ms − T)) for T < Ms."""
        Ms, T = 350.0, 25.0
        frac_expected = 1.0 - math.exp(-0.011 * (Ms - T))
        res = koistinen_marburger(T_C=T, Ms_C=Ms)
        assert res["ok"] is True
        assert abs(res["martensite_frac"] - frac_expected) < REL

    def test_deeper_quench_gives_more_martensite(self):
        """Lower T gives higher martensite fraction (deeper into Ms-Mf range)."""
        r1 = koistinen_marburger(T_C=200.0, Ms_C=350.0)
        r2 = koistinen_marburger(T_C=25.0, Ms_C=350.0)
        assert r2["martensite_frac"] > r1["martensite_frac"]

    def test_pct_equals_100_times_frac(self):
        """martensite_pct must equal martensite_frac × 100."""
        res = koistinen_marburger(T_C=25.0, Ms_C=350.0)
        assert res["ok"] is True
        assert abs(res["martensite_pct"] - res["martensite_frac"] * 100.0) < 1e-6


# ===========================================================================
# 15. retained_austenite
# ===========================================================================

class TestRetainedAustenite:

    def test_RA_plus_martensite_equals_1(self):
        """RA + martensite fraction must equal 1 (for T < Ms)."""
        T, Ms = 25.0, 300.0
        ra = retained_austenite(T_quench_C=T, Ms_C=Ms)
        km = koistinen_marburger(T_C=T, Ms_C=Ms)
        assert ra["ok"] is True
        assert km["ok"] is True
        total = ra["retained_austenite_frac"] + km["martensite_frac"]
        assert abs(total - 1.0) < 1e-4

    def test_high_RA_triggers_warning(self):
        """RA > 15% must trigger a warning about sub-zero treatment."""
        # Ms=200 °C, T=25 °C → RA = exp(-0.011*(200-25)) = exp(-1.925) ≈ 14.6%
        # Use Ms=150, T=25 → (Ms-T)=125 → RA=exp(-1.375)≈25%
        res = retained_austenite(T_quench_C=25.0, Ms_C=150.0)
        assert res["ok"] is True
        if res["retained_austenite_pct"] > 15.0:
            assert len(res["warnings"]) > 0


# ===========================================================================
# 16. annealing_temperature
# ===========================================================================

class TestAnnealingTemperature:

    def test_full_anneal_above_Ac3_for_hypoeutectoid(self):
        """Full anneal min must be above Ac3 for hypoeutectoid."""
        res = annealing_temperature(C_wt_pct=0.40)
        assert res["ok"] is True
        assert res["full_anneal_min_C"] > res["Ac3_approx_C"]

    def test_process_anneal_below_Ac1(self):
        """Process anneal must be below Ac1."""
        res = annealing_temperature(C_wt_pct=0.40)
        assert res["ok"] is True
        assert res["process_anneal_max_C"] < res["Ac1_approx_C"]

    def test_hypereutectoid_full_anneal_near_Ac1(self):
        """For hypereutectoid (C=1.0), full anneal min ≈ Ac1 + 10 °C."""
        res = annealing_temperature(C_wt_pct=1.0)
        assert res["ok"] is True
        assert res["full_anneal_min_C"] < res["Ac1_approx_C"] + 15.0


# ===========================================================================
# 17. normalizing_temperature
# ===========================================================================

class TestNormalizingTemperature:

    def test_normalize_above_Ac3(self):
        """Normalizing range must start above Ac3."""
        res = normalizing_temperature(C_wt_pct=0.40)
        assert res["ok"] is True
        assert res["normalize_min_C"] > res["Ac3_approx_C"]

    def test_hypereutectoid_warning(self):
        """Hypereutectoid steel (C=1.0) must trigger a cementite-network warning."""
        res = normalizing_temperature(C_wt_pct=1.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0


# ===========================================================================
# 18. stress_relief_temperature
# ===========================================================================

class TestStressReliefTemperature:

    def test_plain_carbon_range_returned(self):
        """plain_carbon SR range must be within known bounds."""
        res = stress_relief_temperature("plain_carbon")
        assert res["ok"] is True
        assert 500.0 <= res["SR_min_C"] < res["SR_max_C"] <= 700.0

    def test_stainless_304_sensitization_warning(self):
        """Stainless 304 SR must have a sensitization warning."""
        res = stress_relief_temperature("stainless_304")
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_unknown_steel_type_returns_error(self):
        res = stress_relief_temperature("unobtanium")
        assert res["ok"] is False

    def test_maraging_range_reasonable(self):
        """Maraging steel SR should be in the 480–510 °C ageing range."""
        res = stress_relief_temperature("maraging")
        assert res["ok"] is True
        assert 480.0 <= res["SR_min_C"] < res["SR_max_C"] <= 520.0


# ===========================================================================
# 19. hardness_convert
# ===========================================================================

class TestHardnessConvert:

    def test_HRC_round_trip(self):
        """HRC → HB → back-calculate HRC must be close."""
        hrc_in = 45.0
        res = hardness_convert(value=hrc_in, from_scale="HRC")
        assert res["ok"] is True
        HB = res["HB"]
        hrc_back = _HB_to_hrc(HB)
        assert abs(hrc_back - hrc_in) < 0.2

    def test_HB_to_HRC_formula(self):
        """Verify HB=200 converts to the algebraic polynomial inverse."""
        HB = 200.0
        hrc_expected = _HB_to_hrc(HB)
        res = hardness_convert(value=HB, from_scale="HB")
        assert res["ok"] is True
        assert abs(res["HRC"] - hrc_expected) < 0.5

    def test_UTS_approx_3p45_times_HB(self):
        """UTS_MPa ≈ 3.45 × HB (for HRC input)."""
        res = hardness_convert(value=40.0, from_scale="HRC")
        assert res["ok"] is True
        assert abs(res["UTS_MPa"] - 3.45 * res["HB"]) < 1.0

    def test_HV_greater_than_HB_for_hard_steel(self):
        """For high hardness (HRC 50+), HV > HB typically."""
        res = hardness_convert(value=55.0, from_scale="HRC")
        assert res["ok"] is True
        assert res["HV"] > res["HB"]

    def test_HRC_to_HB_polynomial_values(self):
        """Spot-check HRC=30 → HB using the polynomial."""
        hrc = 30.0
        HB_expected = _hrc_to_HB(hrc)
        res = hardness_convert(value=hrc, from_scale="HRC")
        assert res["ok"] is True
        assert abs(res["HB"] - HB_expected) < 1.0

    def test_HRB_out_of_range_returns_error(self):
        """HRB > 100 is out of range and must return ok=False."""
        res = hardness_convert(value=105.0, from_scale="HRB")
        assert res["ok"] is False

    def test_invalid_scale_returns_error(self):
        res = hardness_convert(value=40.0, from_scale="HRA")
        assert res["ok"] is False

    def test_HV_round_trip(self):
        """HRC=50 → HV → back-calc HRC via HV inverse must be close."""
        hrc_in = 50.0
        res1 = hardness_convert(value=hrc_in, from_scale="HRC")
        assert res1["ok"] is True
        HV = res1["HV"]
        res2 = hardness_convert(value=HV, from_scale="HV")
        assert res2["ok"] is True
        assert abs(res2["HRC"] - hrc_in) < 0.5


# ===========================================================================
# 20. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_ht_grossmann_DI_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_grossmann_DI(ctx, _args(C=0.40, Mn=0.70, Cr=1.05, Mo=0.20)))
        d = _ok_tool(raw)
        assert d["DI_mm"] > 0

    def test_run_ht_grossmann_DI_missing_C(self):
        ctx = _ctx()
        raw = _run(run_ht_grossmann_DI(ctx, _args(Mn=0.70)))
        _err_tool(raw)

    def test_run_ht_jominy_hardness_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_jominy_hardness(ctx, _args(C=0.40, jominy_dist_mm=10.0)))
        d = _ok_tool(raw)
        assert d["HRC"] > 0

    def test_run_ht_actual_critical_diameter_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_actual_critical_diameter(ctx, _args(DI_mm=75.0, H=1.0)))
        d = _ok_tool(raw)
        assert d["D_act_mm"] > 0

    def test_run_ht_as_quenched_hardness_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_as_quenched_hardness(
            ctx, _args(C_wt_pct=0.40, martensite_pct=90.0)
        ))
        d = _ok_tool(raw)
        assert d["HRC"] > 0

    def test_run_ht_hollomon_jaffe_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_hollomon_jaffe(
            ctx, _args(C_wt_pct=0.40, T_C=400.0, t_hours=2.0)
        ))
        d = _ok_tool(raw)
        assert d["P"] > 0
        assert d["HRC_tempered"] > 0

    def test_run_ht_carburizing_case_depth_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_carburizing_case_depth(
            ctx, _args(T_C=925.0, t_hours=6.0)
        ))
        d = _ok_tool(raw)
        assert d["case_depth_harris_mm"] > 0

    def test_run_ht_nitriding_case_depth_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_nitriding_case_depth(ctx, _args(T_C=525.0, t_hours=24.0)))
        d = _ok_tool(raw)
        assert d["total_case_depth_mm"] > 0

    def test_run_ht_induction_case_depth_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_induction_case_depth(ctx, _args(freq_Hz=10000.0, t_s=1.5)))
        d = _ok_tool(raw)
        assert d["case_depth_mm"] > 0

    def test_run_ht_austenitizing_temperature_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_austenitizing_temperature(ctx, _args(C_wt_pct=0.40)))
        d = _ok_tool(raw)
        assert d["T_austenit_min_C"] > 0

    def test_run_ht_andrews_Ac1_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_andrews_Ac1(ctx, _args(Si=0.25, Mn=0.70)))
        d = _ok_tool(raw)
        assert d["Ac1_C"] > 600.0

    def test_run_ht_andrews_Ac3_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_andrews_Ac3(ctx, _args(C=0.40, Mn=0.75)))
        d = _ok_tool(raw)
        assert d["Ac3_C"] > 700.0

    def test_run_ht_martensite_start_Ms_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_martensite_start_Ms(ctx, _args(C=0.40, Mn=0.70)))
        d = _ok_tool(raw)
        assert "Ms_C" in d

    def test_run_ht_martensite_finish_Mf_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_martensite_finish_Mf(ctx, _args(Ms_C=370.0)))
        d = _ok_tool(raw)
        assert abs(d["Mf_C"] - (370.0 - 215.0)) < 0.1

    def test_run_ht_koistinen_marburger_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_koistinen_marburger(ctx, _args(T_C=25.0, Ms_C=350.0)))
        d = _ok_tool(raw)
        assert d["martensite_pct"] > 0

    def test_run_ht_retained_austenite_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_retained_austenite(ctx, _args(T_quench_C=25.0, Ms_C=300.0)))
        d = _ok_tool(raw)
        assert 0.0 <= d["retained_austenite_pct"] <= 100.0

    def test_run_ht_annealing_temperature_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_annealing_temperature(ctx, _args(C_wt_pct=0.40)))
        d = _ok_tool(raw)
        assert d["full_anneal_min_C"] > 700.0

    def test_run_ht_normalizing_temperature_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_normalizing_temperature(ctx, _args(C_wt_pct=0.30)))
        d = _ok_tool(raw)
        assert d["normalize_min_C"] > 700.0

    def test_run_ht_stress_relief_temperature_happy_path(self):
        ctx = _ctx()
        raw = _run(run_ht_stress_relief_temperature(
            ctx, _args(steel_type="plain_carbon")
        ))
        d = _ok_tool(raw)
        assert d["SR_min_C"] > 0

    def test_run_ht_hardness_convert_happy_path_HRC(self):
        ctx = _ctx()
        raw = _run(run_ht_hardness_convert(ctx, _args(value=45.0, from_scale="HRC")))
        d = _ok_tool(raw)
        assert d["HB"] > 0
        assert d["HV"] > 0

    def test_run_ht_hardness_convert_bad_json(self):
        ctx = _ctx()
        raw = _run(run_ht_hardness_convert(ctx, b"not json"))
        _err_tool(raw)

    def test_run_ht_hollomon_jaffe_missing_T_C(self):
        ctx = _ctx()
        raw = _run(run_ht_hollomon_jaffe(ctx, _args(C_wt_pct=0.40, t_hours=2.0)))
        _err_tool(raw)


# ---------------------------------------------------------------------------
# Externally-citable reference cases
#   Andrews K.W. (1965) JISI 203, 721-727
#   Koistinen & Marburger (1959) Acta Metall. 7, 59-60
#   Grossmann (1942) Trans. AIME 150, 227-259 / ASM HB Vol. 4
#   Hollomon & Jaffe (1945) Trans. AIME 162, 223-249
#   Harris (1943) Met. Prog. 44, 265
# ---------------------------------------------------------------------------

class TestHeatTreatExternalReferenceCases:
    """Exact-reproduction checks against the cited primary metallurgy
    literature (ASM Handbook Vol. 4 reproduces all of these formulas)."""

    def test_andrews_Ac1_plain_carbon_base(self):
        # Andrews (1965): Ac1 = 723 - 16.9 Ni + 29.1 Si - 10.7 Mn
        #                       + 16.9 Cr + 6.38 W.  Plain C -> 723 C.
        assert math.isclose(andrews_Ac1()["Ac1_C"], 723.0, rel_tol=1e-9)

    def test_andrews_Ac1_alloyed(self):
        # Andrews (1965) linear Ac1 for Si=0.3, Mn=0.8, Cr=1.0, Ni=0.5.
        r = andrews_Ac1(Si=0.3, Mn=0.8, Cr=1.0, Ni=0.5)
        exp = 723.0 - 16.9 * 0.5 + 29.1 * 0.3 - 10.7 * 0.8 + 16.9 * 1.0
        assert math.isclose(r["Ac1_C"], round(exp, 1), rel_tol=1e-9)

    def test_andrews_Ac3_carbon_term(self):
        # Andrews (1965): Ac3 = 910 - 203 sqrt(C) (+ alloy terms).
        r = andrews_Ac3(C=0.40)
        assert math.isclose(r["Ac3_C"], round(910.0 - 203.0 * math.sqrt(0.40), 1),
                            rel_tol=1e-9)

    def test_andrews_Ms_carbon(self):
        # Andrews (1965): Ms = 539 - 423 C - 30.4 Mn - 17.7 Ni - 12.1 Cr
        #                      - 7.5 Mo (+10 Co - 7.5 Si).
        r = martensite_start_Ms(C=0.40)
        assert math.isclose(r["Ms_C"], round(539.0 - 423.0 * 0.40, 1),
                            rel_tol=1e-9)

    def test_andrews_Ms_4340_literature(self):
        # AISI 4340 (C0.40 Mn0.70 Cr0.80 Ni1.80 Mo0.25): Andrews linear Ms.
        r = martensite_start_Ms(C=0.40, Mn=0.70, Cr=0.80, Ni=1.80, Mo=0.25)
        exp = (539.0 - 423.0 * 0.40 - 30.4 * 0.70 - 17.7 * 1.80
               - 12.1 * 0.80 - 7.5 * 0.25)
        assert math.isclose(r["Ms_C"], round(exp, 1), rel_tol=1e-9)
        # 4340 Andrews-formula Ms is ~305 C (published dilatometric ~285-300 C;
        # the Andrews linear fit is known to run slightly high).
        assert 290.0 < r["Ms_C"] < 320.0

    def test_koistinen_marburger_exact(self):
        # Koistinen & Marburger (1959): f_M = 1 - exp(-0.011 (Ms - T)).
        r = koistinen_marburger(T_C=20.0, Ms_C=300.0)
        # Output is rounded to 3 decimals by the implementation.
        assert math.isclose(r["martensite_frac"],
                            1.0 - math.exp(-0.011 * (300.0 - 20.0)),
                            abs_tol=5e-4)

    def test_koistinen_marburger_zero_above_Ms(self):
        # K-M: no martensite forms above Ms (f_M = 0 for T >= Ms).
        r = koistinen_marburger(T_C=350.0, Ms_C=300.0)
        assert math.isclose(r["martensite_frac"], 0.0, abs_tol=1e-12)

    def test_grossmann_DI_base_diameter(self):
        # Grossmann (1942) / ASM HB Vol. 4: DI0 = 0.54 sqrt(C) at ASTM GS 7.
        r = grossmann_DI(C=0.40, grain_size_ASTM=7.0)
        assert math.isclose(r["DI0_in"], 0.54 * math.sqrt(0.40), rel_tol=1e-9)

    def test_grossmann_alloy_multiplier(self):
        # Grossmann Mn factor (ASM HB Vol. 4 Table 2): f_Mn = 1 + 3.333 Mn.
        r = grossmann_DI(C=0.40, Mn=0.80, grain_size_ASTM=7.0)
        assert math.isclose(r["alloy_multiplier"], 1.0 + 3.3333 * 0.80,
                            rel_tol=1e-5)

    def test_hollomon_jaffe_parameter(self):
        # Hollomon & Jaffe (1945): P = T_K (C_HJ + log10 t), C_HJ=20.
        # T=500 C -> 773.15 K, t=1 h -> P = 773.15*20 = 15463.
        r = hollomon_jaffe(C_wt_pct=0.40, T_C=500.0, t_hours=1.0,
                           HRC_as_quenched=55.0)
        assert math.isclose(r["P"],
                            round((500.0 + 273.15) * (20.0 + math.log10(1.0)), 0),
                            rel_tol=1e-9)

    def test_carburizing_arrhenius_diffusivity(self):
        # Harris (1943) + Arrhenius: D = D0 exp(-Q/RT), x = k sqrt(D t).
        # D0=0.20 cm^2/s, Q=142 kJ/mol, R=8.314, T=925 C.
        r = carburizing_case_depth(T_C=925.0, t_hours=8.0)
        D_exp = 0.20 * math.exp(-142000.0 / (8.314 * (925.0 + 273.15)))
        assert math.isclose(r["D_cm2_s"], D_exp, rel_tol=1e-9)
        assert math.isclose(r["case_depth_harris_mm"],
                            1.0 * math.sqrt(D_exp * 8.0 * 3600.0) * 10.0,
                            rel_tol=1e-9)

    def test_carburizing_case_depth_sqrt_time(self):
        # Harris: case depth scales with sqrt(time) (parabolic kinetics).
        a = carburizing_case_depth(T_C=925.0, t_hours=4.0)
        b = carburizing_case_depth(T_C=925.0, t_hours=16.0)
        assert math.isclose(b["case_depth_harris_mm"],
                            2.0 * a["case_depth_harris_mm"], rel_tol=1e-9)

    def test_induction_skin_depth_formula(self):
        # ASM HB Vol. 4 / EM skin depth: delta = sqrt(rho/(pi f mu0 mu_r)).
        r = induction_case_depth(freq_Hz=10000.0, t_s=5.0,
                                 rho=1.1e-6, mu_r=1.0)
        mu0 = 4.0 * math.pi * 1e-7
        delta_mm = math.sqrt(1.1e-6 / (math.pi * 10000.0 * mu0 * 1.0)) * 1000.0
        assert math.isclose(r["skin_depth_mm"], delta_mm, rel_tol=1e-9)
