"""
Hermetic tests for kerf_cad_core.casting — metal casting design calculators.

Coverage:
  design.shrinkage_allowance     — pattern shrinkage + machining allowance
  design.draft_angle_volume      — draft taper volume addition
  design.chvorinov_solidification — Chvorinov's Rule: t = B·(V/A)^n
  design.riser_size              — modulus method riser sizing
  design.gating_system           — Bernoulli-based gating design
  design.casting_yield           — yield percentage + warnings
  design.pouring_guidance        — pouring temperature + thin-section warnings
  tools.*                        — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas are verified algebraically against AFS / Groover hand-calc values.

References
----------
Groover, M.P. "Fundamentals of Modern Manufacturing", 5th ed., Ch. 11
Kalpakjian, S. & Schmid, S.R. "Manufacturing Engineering & Technology", 7th ed.
Campbell, J. "Castings", 2nd ed.
AFS Gating and Risering Manual

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.casting.design import (
    shrinkage_allowance,
    draft_angle_volume,
    chvorinov_solidification,
    riser_size,
    gating_system,
    casting_yield,
    pouring_guidance,
)
from kerf_cad_core.casting.tools import (
    run_casting_shrinkage_allowance,
    run_casting_draft_angle_volume,
    run_casting_chvorinov,
    run_casting_riser_size,
    run_casting_gating_system,
    run_casting_yield,
    run_casting_pouring_guidance,
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


REL = 1e-9  # relative tolerance for floating-point checks


# ===========================================================================
# 1. shrinkage_allowance
# ===========================================================================

class TestShrinkageAllowance:

    def test_carbon_steel_pattern_larger_than_nominal(self):
        """Pattern must be larger than nominal for carbon_steel (2.0% shrinkage)."""
        res = shrinkage_allowance("carbon_steel", 100.0)
        assert res["ok"] is True
        assert res["pattern_dim_mm"] > 100.0

    def test_shrinkage_dim_algebraic_carbon_steel(self):
        """shrinkage_dim = nominal / (1 - 0.020) for carbon_steel."""
        nom = 100.0
        ls = 0.020
        expected = nom / (1.0 - ls)
        res = shrinkage_allowance("carbon_steel", nom)
        assert res["ok"] is True
        assert abs(res["shrinkage_dim_mm"] - expected) / expected < REL

    def test_aluminium_alloy_shrinkage_dim(self):
        """shrinkage_dim = nominal / (1 - 0.013) for aluminium_alloy."""
        nom = 200.0
        ls = 0.013
        expected = nom / (1.0 - ls)
        res = shrinkage_allowance("aluminium_alloy", nom)
        assert res["ok"] is True
        assert abs(res["shrinkage_dim_mm"] - expected) / expected < REL

    def test_machining_stock_added_to_pattern(self):
        """pattern_dim = shrinkage_dim + machining_stock."""
        res = shrinkage_allowance("grey_cast_iron", 50.0)
        assert res["ok"] is True
        stock = res["machining_stock_mm"]
        assert abs(res["pattern_dim_mm"] - (res["shrinkage_dim_mm"] + stock)) < 1e-10

    def test_extra_machining_added(self):
        """Extra machining adds to total stock."""
        res_no_extra = shrinkage_allowance("carbon_steel", 100.0)
        res_with_extra = shrinkage_allowance("carbon_steel", 100.0, extra_machining_mm=2.0)
        assert res_with_extra["pattern_dim_mm"] - res_no_extra["pattern_dim_mm"] == pytest.approx(2.0, rel=REL)

    def test_grey_iron_lower_shrinkage_than_steel(self):
        """Grey iron has lower linear shrinkage than carbon steel."""
        res_gi = shrinkage_allowance("grey_cast_iron", 100.0)
        res_cs = shrinkage_allowance("carbon_steel", 100.0)
        assert res_gi["linear_shrinkage"] < res_cs["linear_shrinkage"]

    def test_unknown_alloy_returns_error(self):
        """Unknown alloy must return ok=False."""
        res = shrinkage_allowance("unobtanium", 100.0)
        assert res["ok"] is False
        assert "reason" in res

    def test_zero_nominal_returns_error(self):
        """nominal_dim_mm=0 must return ok=False."""
        res = shrinkage_allowance("carbon_steel", 0.0)
        assert res["ok"] is False

    def test_negative_nominal_returns_error(self):
        """Negative nominal must return ok=False."""
        res = shrinkage_allowance("carbon_steel", -10.0)
        assert res["ok"] is False

    def test_negative_extra_machining_returns_error(self):
        """Negative extra_machining_mm must return ok=False."""
        res = shrinkage_allowance("carbon_steel", 100.0, extra_machining_mm=-1.0)
        assert res["ok"] is False

    def test_warnings_list_present(self):
        """Result always has a warnings list."""
        res = shrinkage_allowance("bronze", 80.0)
        assert res["ok"] is True
        assert isinstance(res["warnings"], list)


# ===========================================================================
# 2. draft_angle_volume
# ===========================================================================

class TestDraftAngleVolume:

    def test_algebraic_added_volume(self):
        """added_volume = base_area * height * tan(draft_deg)."""
        A, H, deg = 0.01, 0.05, 2.0
        tan_d = math.tan(math.radians(deg))
        expected = A * H * tan_d
        res = draft_angle_volume(A, H, deg)
        assert res["ok"] is True
        assert abs(res["added_volume_m3"] - expected) / expected < REL

    def test_total_volume_equals_base_plus_added(self):
        """total_volume = base_area × height + added_volume."""
        A, H, deg = 0.005, 0.10, 3.0
        res = draft_angle_volume(A, H, deg)
        assert res["ok"] is True
        base_vol = A * H
        assert abs(res["total_volume_m3"] - (base_vol + res["added_volume_m3"])) < 1e-15

    def test_larger_draft_gives_more_volume(self):
        """Larger draft angle → more added volume."""
        A, H = 0.01, 0.05
        v1 = draft_angle_volume(A, H, 1.0)["added_volume_m3"]
        v2 = draft_angle_volume(A, H, 3.0)["added_volume_m3"]
        assert v2 > v1

    def test_zero_draft_raises_error(self):
        """draft_deg=0 must return ok=False."""
        res = draft_angle_volume(0.01, 0.05, 0.0)
        assert res["ok"] is False

    def test_negative_height_returns_error(self):
        res = draft_angle_volume(0.01, -0.05, 2.0)
        assert res["ok"] is False

    def test_negative_area_returns_error(self):
        res = draft_angle_volume(-0.01, 0.05, 2.0)
        assert res["ok"] is False

    def test_large_draft_produces_warning(self):
        """draft_deg > 10° should produce a warning."""
        res = draft_angle_volume(0.01, 0.05, 15.0)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_tan_draft_correct(self):
        """tan_draft field equals tan of draft_deg."""
        deg = 2.5
        res = draft_angle_volume(0.02, 0.08, deg)
        assert res["ok"] is True
        assert abs(res["tan_draft"] - math.tan(math.radians(deg))) < 1e-12


# ===========================================================================
# 3. chvorinov_solidification
# ===========================================================================

class TestChvorinovSolidification:

    def test_algebraic_formula_default_B_n(self):
        """t = B · (V/A)^n for default B=600, n=2.0."""
        V, A = 0.001, 0.06  # 1 L sphere-ish
        B, n = 600.0, 2.0
        modulus = V / A
        expected = B * (modulus ** n)
        res = chvorinov_solidification(V, A)
        assert res["ok"] is True
        assert abs(res["solidification_s"] - expected) / expected < REL

    def test_algebraic_custom_B_n(self):
        """t = B · (V/A)^n for custom B=1000, n=1.8."""
        V, A = 5e-4, 0.04
        B, n = 1000.0, 1.8
        modulus = V / A
        expected = B * (modulus ** n)
        res = chvorinov_solidification(V, A, B=B, n=n)
        assert res["ok"] is True
        assert abs(res["solidification_s"] - expected) / expected < REL

    def test_modulus_field_equals_V_over_A(self):
        """modulus_m must equal volume/area."""
        V, A = 2e-3, 0.12
        res = chvorinov_solidification(V, A)
        assert res["ok"] is True
        assert abs(res["modulus_m"] - V / A) < 1e-15

    def test_doubling_B_doubles_time(self):
        """Doubling B doubles solidification time (linear in B)."""
        V, A = 1e-3, 0.06
        t1 = chvorinov_solidification(V, A, B=600.0)["solidification_s"]
        t2 = chvorinov_solidification(V, A, B=1200.0)["solidification_s"]
        assert abs(t2 / t1 - 2.0) < 1e-10

    def test_larger_modulus_longer_solidification(self):
        """A larger V/A modulus gives a longer solidification time."""
        # sphere: V = (4/3)πr³, A = 4πr²  → modulus = r/3
        # large r → large modulus → longer time
        V1, A1 = 1e-3, 0.06
        V2, A2 = 2e-3, 0.06
        t1 = chvorinov_solidification(V1, A1)["solidification_s"]
        t2 = chvorinov_solidification(V2, A2)["solidification_s"]
        assert t2 > t1

    def test_zero_volume_returns_error(self):
        res = chvorinov_solidification(0.0, 0.06)
        assert res["ok"] is False

    def test_negative_area_returns_error(self):
        res = chvorinov_solidification(1e-3, -0.06)
        assert res["ok"] is False

    def test_atypical_n_produces_warning(self):
        """n outside [1.5, 2.0] must produce a warning."""
        res = chvorinov_solidification(1e-3, 0.06, n=2.5)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_n_at_lower_boundary_no_warning(self):
        """n=1.5 is at boundary — no warning expected."""
        res = chvorinov_solidification(1e-3, 0.06, n=1.5)
        assert res["ok"] is True
        # No warning for n=1.5 (at boundary)
        assert all("exponent" not in w for w in res["warnings"])


# ===========================================================================
# 4. riser_size
# ===========================================================================

class TestRiserSize:

    # Reference hand-calc fixture:
    # V_c = 1e-3 m³, A_c = 0.06 m²
    # M_c = 1e-3 / 0.06 = 1/60 m
    # M_r_req = 1.2/60 = 0.02 m
    # D_min = 5 * 0.02 = 0.1 m
    _V = 1e-3
    _A = 0.06

    def test_casting_modulus_algebraic(self):
        """M_casting = V/A."""
        res = riser_size(self._V, self._A)
        assert res["ok"] is True
        assert abs(res["casting_modulus_m"] - self._V / self._A) < 1e-15

    def test_riser_modulus_required(self):
        """M_riser_required = 1.2 * M_casting."""
        res = riser_size(self._V, self._A)
        assert res["ok"] is True
        assert abs(res["riser_modulus_required_m"] - 1.2 * (self._V / self._A)) < REL

    def test_riser_diameter_algebraic(self):
        """D_min = 6 * M_casting (from D/5 >= 1.2*M_c → D >= 6*M_c)."""
        M_c = self._V / self._A
        D_expected = 6.0 * M_c
        res = riser_size(self._V, self._A)
        assert res["ok"] is True
        assert abs(res["riser_diameter_m"] - D_expected) / D_expected < REL

    def test_riser_height_equals_diameter(self):
        """For H=D cylinder, riser_height == riser_diameter."""
        res = riser_size(self._V, self._A)
        assert res["ok"] is True
        assert abs(res["riser_height_m"] - res["riser_diameter_m"]) < 1e-15

    def test_riser_volume_formula(self):
        """V_riser = π/4 * D^3."""
        res = riser_size(self._V, self._A)
        assert res["ok"] is True
        D = res["riser_diameter_m"]
        V_expected = (math.pi / 4.0) * D ** 3
        assert abs(res["riser_volume_m3"] - V_expected) / V_expected < REL

    def test_riser_neck_diameter(self):
        """Riser neck = 0.65 × D_min."""
        res = riser_size(self._V, self._A)
        assert res["ok"] is True
        assert abs(res["riser_neck_diameter_m"] - 0.65 * res["riser_diameter_m"]) < 1e-12

    def test_feeds_ok_true_for_correct_riser(self):
        """feeds_ok must be True for a correctly sized riser."""
        res = riser_size(self._V, self._A)
        assert res["ok"] is True
        assert res["feeds_ok"] is True

    def test_riser_solidification_exceeds_casting(self):
        """Riser solidification time must exceed casting solidification time."""
        res = riser_size(self._V, self._A)
        assert res["ok"] is True
        assert res["riser_solidification_s"] > res["casting_solidification_s"]

    def test_invalid_riser_shape_returns_error(self):
        """Unknown riser_shape must return ok=False."""
        res = riser_size(self._V, self._A, riser_shape="spherical")
        assert res["ok"] is False

    def test_zero_casting_volume_returns_error(self):
        res = riser_size(0.0, self._A)
        assert res["ok"] is False

    def test_warnings_list_present(self):
        res = riser_size(self._V, self._A)
        assert isinstance(res["warnings"], list)


# ===========================================================================
# 5. gating_system
# ===========================================================================

class TestGatingSystem:

    # Reference fixture: 20 kg carbon steel, 30 s pour, 0.5 m sprue
    _mass = 20.0
    _alloy = "carbon_steel"
    _t_pour = 30.0
    _H = 0.5

    def _ref(self, **kwargs):
        return gating_system(self._mass, self._alloy, self._t_pour, self._H, **kwargs)

    def test_happy_path_returns_ok(self):
        res = self._ref()
        assert res["ok"] is True

    def test_volume_to_fill_formula(self):
        """V_fill = mass / density."""
        res = self._ref()
        rho = res["density_kg_m3"]
        expected = self._mass / rho
        assert abs(res["volume_to_fill_m3"] - expected) / expected < REL

    def test_flow_rate_formula(self):
        """Q = V_fill / t_pour."""
        res = self._ref()
        Q_expected = res["volume_to_fill_m3"] / self._t_pour
        assert abs(res["flow_rate_m3_s"] - Q_expected) / Q_expected < REL

    def test_velocity_bernoulli(self):
        """v = Cd * sqrt(2*g*H) (default Cd=0.85)."""
        res = self._ref()
        v_expected = 0.85 * math.sqrt(2.0 * 9.81 * self._H)
        assert abs(res["velocity_m_s"] - v_expected) / v_expected < REL

    def test_choke_area_formula(self):
        """A_choke = Q / v."""
        res = self._ref()
        A_expected = res["flow_rate_m3_s"] / res["velocity_m_s"]
        assert abs(res["choke_area_m2"] - A_expected) / A_expected < REL

    def test_unpressurised_gate_larger_than_sprue(self):
        """Unpressurised (1:2:4): gate area > runner area > sprue area."""
        res = self._ref(system_type="unpressurised")
        assert res["gate_area_m2"] > res["runner_area_m2"]
        assert res["runner_area_m2"] > res["sprue_area_m2"]

    def test_pressurised_gate_smaller_than_sprue(self):
        """Pressurised (1:0.75:0.5): gate < runner < sprue."""
        res = self._ref(system_type="pressurised")
        assert res["gate_area_m2"] < res["runner_area_m2"]
        assert res["runner_area_m2"] < res["sprue_area_m2"]

    def test_unpressurised_ratios_correct(self):
        """Unpressurised ratios: gate/sprue = 4, runner/sprue = 2."""
        res = self._ref(system_type="unpressurised")
        assert abs(res["gate_area_m2"] / res["sprue_area_m2"] - 4.0) < 1e-10
        assert abs(res["runner_area_m2"] / res["sprue_area_m2"] - 2.0) < 1e-10

    def test_pressurised_ratios_correct(self):
        """Pressurised ratios: sprue/gate = 1/0.5 = 2, runner/gate = 0.75/0.5 = 1.5."""
        res = self._ref(system_type="pressurised")
        assert abs(res["sprue_area_m2"] / res["gate_area_m2"] - 2.0) < 1e-10
        assert abs(res["runner_area_m2"] / res["gate_area_m2"] - 1.5) < 1e-10

    def test_unknown_alloy_returns_error(self):
        res = gating_system(20.0, "unobtanium", 30.0, 0.5)
        assert res["ok"] is False

    def test_unknown_system_type_returns_error(self):
        res = gating_system(20.0, "carbon_steel", 30.0, 0.5, system_type="turbulent")
        assert res["ok"] is False

    def test_discharge_coeff_gt_1_returns_error(self):
        res = gating_system(20.0, "carbon_steel", 30.0, 0.5, discharge_coeff=1.5)
        assert res["ok"] is False

    def test_aluminium_alloy_density_used(self):
        """Aluminium alloy (~2700 kg/m³) gives different volume than steel."""
        res_al = gating_system(5.0, "aluminium_alloy", 20.0, 0.3)
        res_cs = gating_system(5.0, "carbon_steel", 20.0, 0.3)
        assert res_al["ok"] is True
        assert res_cs["ok"] is True
        # Al has much lower density → larger volume to fill
        assert res_al["volume_to_fill_m3"] > res_cs["volume_to_fill_m3"]

    def test_short_pour_time_warning(self):
        """Pour time < 5 s should produce a turbulence warning."""
        res = gating_system(20.0, "carbon_steel", 2.0, 0.5)
        assert res["ok"] is True
        assert len(res["warnings"]) > 0


# ===========================================================================
# 6. casting_yield
# ===========================================================================

class TestCastingYield:

    def test_perfect_yield_100_pct(self):
        """When poured = casting, yield = 100%."""
        res = casting_yield(10.0, 10.0)
        assert res["ok"] is True
        assert abs(res["yield_pct"] - 100.0) < REL

    def test_yield_formula_algebraic(self):
        """yield = casting / total × 100."""
        m_cast, m_total = 15.0, 25.0
        expected = (m_cast / m_total) * 100.0
        res = casting_yield(m_cast, m_total)
        assert res["ok"] is True
        assert abs(res["yield_pct"] - expected) / expected < REL

    def test_gating_mass_field(self):
        """gating_riser_mass = total - casting."""
        m_cast, m_total = 15.0, 25.0
        res = casting_yield(m_cast, m_total)
        assert res["ok"] is True
        assert abs(res["gating_riser_mass_kg"] - (m_total - m_cast)) < 1e-12

    def test_yield_below_60_pct_generates_warning(self):
        """yield < 60% must generate a warning."""
        res = casting_yield(5.0, 10.0)  # 50% yield
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_yield_below_50_pct_generates_two_warnings(self):
        """yield < 50% must generate at least two warnings."""
        res = casting_yield(4.0, 10.0)  # 40% yield
        assert res["ok"] is True
        assert len(res["warnings"]) >= 2

    def test_yield_above_60_pct_no_warning(self):
        """yield >= 60% should have no warnings."""
        res = casting_yield(7.0, 10.0)  # 70% yield
        assert res["ok"] is True
        assert len(res["warnings"]) == 0

    def test_casting_greater_than_poured_returns_error(self):
        """casting_mass > total_poured must return ok=False."""
        res = casting_yield(20.0, 10.0)
        assert res["ok"] is False

    def test_zero_casting_mass_returns_error(self):
        res = casting_yield(0.0, 10.0)
        assert res["ok"] is False

    def test_zero_total_poured_returns_error(self):
        res = casting_yield(5.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 7. pouring_guidance
# ===========================================================================

class TestPouringGuidance:

    def test_carbon_steel_temp_range(self):
        """carbon_steel pouring temperature is in expected range."""
        res = pouring_guidance("carbon_steel", 10.0)
        assert res["ok"] is True
        assert res["pouring_temp_low_C"] >= 1500
        assert res["pouring_temp_high_C"] <= 1700

    def test_aluminium_alloy_temp_range(self):
        """aluminium_alloy pouring temperature is below 900°C."""
        res = pouring_guidance("aluminium_alloy", 5.0)
        assert res["ok"] is True
        assert res["pouring_temp_high_C"] < 900

    def test_thin_section_ferrous_triggers_warning(self):
        """Section < 5 mm for ferrous alloy must set thin_section_warning=True."""
        res = pouring_guidance("carbon_steel", 3.0)
        assert res["ok"] is True
        assert res["thin_section_warning"] is True
        assert len(res["warnings"]) > 0

    def test_thick_section_ferrous_no_warning(self):
        """Section >= 5 mm for ferrous alloy: thin_section_warning=False."""
        res = pouring_guidance("carbon_steel", 10.0)
        assert res["ok"] is True
        assert res["thin_section_warning"] is False
        assert len(res["warnings"]) == 0

    def test_thin_section_aluminium_threshold_3mm(self):
        """Al/Mg alloy threshold is 3 mm."""
        res_thin = pouring_guidance("aluminium_alloy", 2.0)
        res_thick = pouring_guidance("aluminium_alloy", 5.0)
        assert res_thin["thin_section_warning"] is True
        assert res_thick["thin_section_warning"] is False

    def test_thin_section_bronze_threshold_2mm(self):
        """Non-ferrous (bronze) threshold is 2 mm."""
        res_thin = pouring_guidance("bronze", 1.5)
        res_thick = pouring_guidance("bronze", 3.0)
        assert res_thin["thin_section_warning"] is True
        assert res_thick["thin_section_warning"] is False

    def test_fluidity_note_non_empty(self):
        """Fluidity note must be a non-empty string."""
        res = pouring_guidance("grey_cast_iron", 8.0)
        assert res["ok"] is True
        assert isinstance(res["fluidity_note"], str)
        assert len(res["fluidity_note"]) > 0

    def test_unknown_alloy_returns_error(self):
        res = pouring_guidance("unobtanium", 5.0)
        assert res["ok"] is False

    def test_zero_section_returns_error(self):
        res = pouring_guidance("carbon_steel", 0.0)
        assert res["ok"] is False


# ===========================================================================
# 8. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_shrinkage_happy_path(self):
        ctx = _ctx()
        raw = _run(run_casting_shrinkage_allowance(ctx, _args(alloy="carbon_steel", nominal_dim_mm=100.0)))
        d = _ok_tool(raw)
        assert d["pattern_dim_mm"] > 100.0

    def test_run_shrinkage_missing_alloy(self):
        ctx = _ctx()
        raw = _run(run_casting_shrinkage_allowance(ctx, _args(nominal_dim_mm=100.0)))
        _err_tool(raw)

    def test_run_shrinkage_bad_json(self):
        ctx = _ctx()
        raw = _run(run_casting_shrinkage_allowance(ctx, b"not-json"))
        _err_tool(raw)

    def test_run_draft_happy_path(self):
        ctx = _ctx()
        raw = _run(run_casting_draft_angle_volume(ctx, _args(base_area_m2=0.01, height_m=0.05, draft_deg=2.0)))
        d = _ok_tool(raw)
        assert d["added_volume_m3"] > 0

    def test_run_draft_missing_height(self):
        ctx = _ctx()
        raw = _run(run_casting_draft_angle_volume(ctx, _args(base_area_m2=0.01, draft_deg=2.0)))
        _err_tool(raw)

    def test_run_chvorinov_happy_path(self):
        ctx = _ctx()
        raw = _run(run_casting_chvorinov(ctx, _args(volume_m3=1e-3, area_m2=0.06)))
        d = _ok_tool(raw)
        assert d["solidification_s"] > 0

    def test_run_chvorinov_custom_B_n(self):
        ctx = _ctx()
        V, A, B, n = 1e-3, 0.06, 800.0, 1.8
        raw = _run(run_casting_chvorinov(ctx, _args(volume_m3=V, area_m2=A, B=B, n=n)))
        d = _ok_tool(raw)
        expected = B * ((V / A) ** n)
        assert abs(d["solidification_s"] - expected) / expected < REL

    def test_run_chvorinov_missing_area(self):
        ctx = _ctx()
        raw = _run(run_casting_chvorinov(ctx, _args(volume_m3=1e-3)))
        _err_tool(raw)

    def test_run_riser_happy_path(self):
        ctx = _ctx()
        raw = _run(run_casting_riser_size(ctx, _args(casting_volume_m3=1e-3, casting_surface_area_m2=0.06)))
        d = _ok_tool(raw)
        assert d["riser_diameter_m"] > 0
        assert d["feeds_ok"] is True

    def test_run_riser_invalid_shape(self):
        ctx = _ctx()
        raw = _run(run_casting_riser_size(ctx, _args(
            casting_volume_m3=1e-3, casting_surface_area_m2=0.06, riser_shape="spherical"
        )))
        _err_tool(raw)

    def test_run_gating_happy_path_unpressurised(self):
        ctx = _ctx()
        raw = _run(run_casting_gating_system(ctx, _args(
            casting_mass_kg=20.0, alloy="carbon_steel",
            pouring_time_s=30.0, sprue_height_m=0.5
        )))
        d = _ok_tool(raw)
        assert d["choke_area_m2"] > 0

    def test_run_gating_pressurised(self):
        ctx = _ctx()
        raw = _run(run_casting_gating_system(ctx, _args(
            casting_mass_kg=10.0, alloy="aluminium_alloy",
            pouring_time_s=20.0, sprue_height_m=0.4,
            system_type="pressurised"
        )))
        d = _ok_tool(raw)
        assert d["gate_area_m2"] < d["sprue_area_m2"]

    def test_run_gating_missing_alloy(self):
        ctx = _ctx()
        raw = _run(run_casting_gating_system(ctx, _args(
            casting_mass_kg=20.0, pouring_time_s=30.0, sprue_height_m=0.5
        )))
        _err_tool(raw)

    def test_run_yield_happy_path(self):
        ctx = _ctx()
        raw = _run(run_casting_yield(ctx, _args(casting_mass_kg=15.0, total_poured_mass_kg=25.0)))
        d = _ok_tool(raw)
        assert abs(d["yield_pct"] - 60.0) < 1e-9

    def test_run_yield_low_triggers_warning(self):
        ctx = _ctx()
        raw = _run(run_casting_yield(ctx, _args(casting_mass_kg=5.0, total_poured_mass_kg=10.0)))
        d = _ok_tool(raw)
        assert len(d["warnings"]) > 0

    def test_run_yield_missing_total(self):
        ctx = _ctx()
        raw = _run(run_casting_yield(ctx, _args(casting_mass_kg=10.0)))
        _err_tool(raw)

    def test_run_pouring_guidance_happy_path(self):
        ctx = _ctx()
        raw = _run(run_casting_pouring_guidance(ctx, _args(alloy="grey_cast_iron", section_thickness_mm=8.0)))
        d = _ok_tool(raw)
        assert d["pouring_temp_low_C"] > 0
        assert d["thin_section_warning"] is False

    def test_run_pouring_guidance_thin_section(self):
        ctx = _ctx()
        raw = _run(run_casting_pouring_guidance(ctx, _args(alloy="carbon_steel", section_thickness_mm=2.0)))
        d = _ok_tool(raw)
        assert d["thin_section_warning"] is True

    def test_run_pouring_guidance_missing_alloy(self):
        ctx = _ctx()
        raw = _run(run_casting_pouring_guidance(ctx, _args(section_thickness_mm=5.0)))
        _err_tool(raw)


# ---------------------------------------------------------------------------
# Externally-citable reference cases (Groover / Kalpakjian / Campbell)
# ---------------------------------------------------------------------------

class TestCastingExternalReferenceCases:
    """Cross-checked against Groover 5th ed. & Kalpakjian 7th ed."""

    def test_chvorinov_modulus_cube_groover(self):
        # Groover, Fundamentals of Modern Manufacturing 5th ed. §10.6.3:
        # Chvorinov t = B*(V/A)^n.  50 mm cube: V=1.25e-4 m^3, A=1.5e-2 m^2.
        v = 0.05 ** 3
        a = 6 * 0.05 ** 2
        r = chvorinov_solidification(v, a, B=600.0, n=2.0)
        assert math.isclose(r["modulus_m"], v / a, rel_tol=1e-12)
        assert math.isclose(r["solidification_s"], 600.0 * (v / a) ** 2,
                            rel_tol=1e-12)

    def test_chvorinov_sphere_vs_cube_ratio(self):
        # Groover §10.6.3 worked principle: a sphere solidifies slower than a
        # cube of equal volume because V/A is larger.  Equal V = 1e-4 m^3.
        v = 1e-4
        r_sphere = (3.0 * v / (4.0 * math.pi)) ** (1.0 / 3.0)
        a_sphere = 4.0 * math.pi * r_sphere ** 2
        side = v ** (1.0 / 3.0)
        a_cube = 6.0 * side ** 2
        ts = chvorinov_solidification(v, a_sphere)["solidification_s"]
        tc = chvorinov_solidification(v, a_cube)["solidification_s"]
        assert ts > tc

    def test_casting_yield_groover(self):
        # Groover §11.1: casting yield = casting mass / total poured * 100.
        r = casting_yield(10.0, 16.0)
        assert math.isclose(r["yield_pct"], 10.0 / 16.0 * 100.0, rel_tol=1e-12)

    def test_shrinkage_allowance_steel_groover_table(self):
        # Groover 5th ed. Table 10.1 / Kalpakjian Table 12.1: cast steel
        # solidification + solid contraction ~2.0 % linear.
        # pattern = nominal / (1 - s).
        r = shrinkage_allowance("carbon_steel", 1000.0)
        assert math.isclose(r["shrinkage_dim_mm"], 1000.0 / (1.0 - 0.02),
                            rel_tol=1e-12)

    def test_shrinkage_allowance_grey_iron_low(self):
        # Kalpakjian 7th ed. Table 12.1: grey cast iron has very low shrinkage
        # (graphite expansion); ~1.0 % linear.
        r = shrinkage_allowance("grey_cast_iron", 500.0)
        assert math.isclose(r["shrinkage_dim_mm"], 500.0 / (1.0 - 0.010),
                            rel_tol=1e-12)

    def test_gating_bernoulli_velocity_kalpakjian_11(self):
        # Kalpakjian & Schmid 7th ed. §11.3: sprue exit velocity from
        # Bernoulli: v = Cd*sqrt(2 g h).  h=0.2 m, Cd=0.85, g=9.81.
        r = gating_system(10.0, "aluminium_alloy", 10.0, 0.2,
                          discharge_coeff=0.85, mold_efficiency=1.0)
        assert math.isclose(r["velocity_m_s"],
                            0.85 * math.sqrt(2 * 9.81 * 0.2), rel_tol=1e-9)

    def test_gating_continuity_flow_rate(self):
        # Kalpakjian §11.3 continuity: Q = volume / pour_time.
        # Al alloy rho ~ 2700 kg/m^3 from catalog; 10 kg -> V=10/2700 m^3.
        r = gating_system(10.0, "aluminium_alloy", 10.0, 0.2)
        assert math.isclose(r["flow_rate_m3_s"],
                            (10.0 / 2700.0) / 10.0, rel_tol=1e-9)

    def test_unpressurised_gating_ratio_kalpakjian(self):
        # Kalpakjian §11.3: unpressurised system uses gating ratio 1:2:4
        # (sprue : runner : gate).
        r = gating_system(5.0, "grey_cast_iron", 8.0, 0.25,
                          system_type="unpressurised")
        assert r["gating_ratio"] == (1.0, 2.0, 4.0)

    def test_riser_modulus_criterion_afs(self):
        # AFS / Chvorinov modulus rule (Kalpakjian §11.4): riser must have a
        # larger modulus than the casting; M_riser_required = 1.2*M_casting.
        r = riser_size(1e-4, 1.5e-2)
        assert math.isclose(r["riser_modulus_required_m"],
                            1.2 * r["casting_modulus_m"], rel_tol=1e-12)

    def test_riser_feeds_when_modulus_sufficient(self):
        # AFS feeding criterion: a correctly sized riser solidifies after the
        # casting (feeds_ok True).
        r = riser_size(1e-4, 1.5e-2)
        assert r["feeds_ok"] is True
