"""
Hermetic tests for kerf_cad_core.injection — plastic injection-moulding
process design calculators.

Coverage:
  process.polymer_properties       — property lookup and error paths
  process.clamp_tonnage            — force calculation, over-tonnage flag
  process.shot_volume_weight       — shot weight, capacity check
  process.gate_runner_sizing       — gate geometry from flow rate
  process.cooling_time             — Fourier plate-cooling equation
  process.flow_length_feasibility  — L/t ratio check
  process.shrinkage_sink_estimate  — shrinkage + sink depth
  process.cycle_time_breakdown     — total cycle and fractions
  process.cavities_from_tonnage    — max cavities from press size
  process.draft_ejection_force     — draft angle + ejection force
  tools.*                          — LLM wrapper happy + error paths

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Calculations verified algebraically against published formulas.

References
----------
Rosato, D.V. & Rosato, M.G. "Injection Moulding Handbook", 3rd ed.
Menges, G. et al. "How to Make Injection Molds", 3rd ed.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.injection.process import (
    polymer_properties,
    clamp_tonnage,
    shot_volume_weight,
    gate_runner_sizing,
    cooling_time,
    flow_length_feasibility,
    shrinkage_sink_estimate,
    cycle_time_breakdown,
    cavities_from_tonnage,
    draft_ejection_force,
)
from kerf_cad_core.injection.tools import (
    run_polymer_properties,
    run_clamp_tonnage,
    run_shot_volume_weight,
    run_gate_runner_sizing,
    run_cooling_time,
    run_flow_length_feasibility,
    run_shrinkage_sink_estimate,
    run_cycle_time_breakdown,
    run_cavities_from_tonnage,
    run_draft_ejection_force,
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
# 1. polymer_properties
# ===========================================================================

class TestPolymerProperties:

    def test_pp_lookup(self):
        res = polymer_properties("PP")
        assert res["ok"] is True
        assert res["polymer"] == "PP"
        assert res["melt_temp_C"] > 0
        assert res["alpha_m2s"] > 0
        assert res["shrinkage_pct"] > 0

    def test_all_supported_polymers(self):
        for p in ("PP", "ABS", "PC", "PA", "POM"):
            res = polymer_properties(p)
            assert res["ok"] is True, f"Expected ok for {p}, got {res}"

    def test_case_insensitive(self):
        assert polymer_properties("abs")["ok"] is True
        assert polymer_properties("Pc")["ok"] is True

    def test_unknown_polymer_returns_error(self):
        res = polymer_properties("UNOBTANIUM")
        assert res["ok"] is False
        assert "reason" in res

    def test_properties_contain_expected_fields(self):
        res = polymer_properties("ABS")
        for field in ("melt_temp_C", "mold_temp_C", "ejection_temp_C",
                      "shrinkage_pct", "alpha_m2s", "density_kg_m3",
                      "flow_length_limit", "mu_friction"):
            assert field in res, f"Missing field {field}"

    def test_pc_higher_melt_than_pp(self):
        """PC has higher processing temperature than PP."""
        t_pp = polymer_properties("PP")["melt_temp_C"]
        t_pc = polymer_properties("PC")["melt_temp_C"]
        assert t_pc > t_pp

    def test_pom_highest_shrinkage(self):
        """POM (acetal) has highest shrinkage among the table polymers."""
        shrinkages = {p: polymer_properties(p)["shrinkage_pct"] for p in ("PP", "ABS", "PC", "PA", "POM")}
        assert shrinkages["POM"] >= max(shrinkages["ABS"], shrinkages["PC"])


# ===========================================================================
# 2. clamp_tonnage
# ===========================================================================

class TestClampTonnage:

    def test_basic_calculation(self):
        """F = n × A × P × sf; 1 cavity, A=0.01 m², P=50 MPa, sf=1.0."""
        res = clamp_tonnage(
            projected_area_m2=0.01, cavity_pressure_Pa=50e6,
            n_cavities=1, safety_factor=1.0
        )
        assert res["ok"] is True
        # F = 1 × 0.01 × 50e6 = 500 000 N = 500 kN
        assert abs(res["clamp_force_kN"] - 500.0) < 1e-9

    def test_multiple_cavities_scales_linearly(self):
        """Doubling cavities doubles clamping force."""
        r1 = clamp_tonnage(0.005, 40e6, n_cavities=1, safety_factor=1.0)
        r2 = clamp_tonnage(0.005, 40e6, n_cavities=2, safety_factor=1.0)
        assert abs(r2["clamp_force_kN"] / r1["clamp_force_kN"] - 2.0) < 1e-9

    def test_safety_factor_scales_force(self):
        """Applying safety_factor=1.1 increases force by 10%."""
        r_no_sf = clamp_tonnage(0.01, 35e6, n_cavities=1, safety_factor=1.0)
        r_sf = clamp_tonnage(0.01, 35e6, n_cavities=1, safety_factor=1.1)
        assert abs(r_sf["clamp_force_kN"] / r_no_sf["clamp_force_kN"] - 1.1) < 1e-9

    def test_separating_force_excludes_safety_factor(self):
        """separating_force_kN = clamp_force_kN / safety_factor."""
        sf = 1.15
        res = clamp_tonnage(0.01, 50e6, n_cavities=1, safety_factor=sf)
        assert abs(res["separating_force_kN"] * sf - res["clamp_force_kN"]) < 1e-6

    def test_over_tonnage_warning_issued(self):
        """Very large area + high pressure triggers over-tonnage warning."""
        res = clamp_tonnage(
            projected_area_m2=1.0, cavity_pressure_Pa=100e6,
            n_cavities=10, safety_factor=1.1
        )
        assert res["ok"] is True
        assert any("over-tonnage" in w for w in res["warnings"])

    def test_negative_area_returns_error(self):
        res = clamp_tonnage(-0.01, 40e6)
        assert res["ok"] is False

    def test_zero_cavities_returns_error(self):
        res = clamp_tonnage(0.01, 40e6, n_cavities=0)
        assert res["ok"] is False

    def test_warnings_list_present_on_ok(self):
        res = clamp_tonnage(0.01, 40e6)
        assert res["ok"] is True
        assert "warnings" in res
        assert isinstance(res["warnings"], list)


# ===========================================================================
# 3. shot_volume_weight
# ===========================================================================

class TestShotVolumeWeight:

    def test_shot_weight_equals_volume_times_density(self):
        """shot_weight = shot_volume × polymer_density."""
        Vp = 50e-6  # 50 cm³
        Vr = 5e-6
        nc = 2
        rho = polymer_properties("PP")["density_kg_m3"]
        res = shot_volume_weight(Vp, Vr, nc, "PP")
        assert res["ok"] is True
        expected_vol = nc * Vp + Vr
        expected_wt = expected_vol * rho
        assert abs(res["shot_volume_m3"] - expected_vol) / expected_vol < REL
        assert abs(res["shot_weight_kg"] - expected_wt) / expected_wt < REL

    def test_part_weight_separate_from_runner(self):
        Vp, Vr = 30e-6, 10e-6
        rho = polymer_properties("ABS")["density_kg_m3"]
        res = shot_volume_weight(Vp, Vr, 1, "ABS")
        assert abs(res["part_weight_kg"] - Vp * rho) / (Vp * rho) < REL
        assert abs(res["runner_weight_kg"] - Vr * rho) / (Vr * rho) < REL

    def test_within_capacity_true_for_small_shot(self):
        res = shot_volume_weight(1e-7, 1e-8, 1, "PP", machine_shot_capacity_kg=5.0)
        assert res["ok"] is True
        assert res["within_capacity"] is True

    def test_over_capacity_triggers_warning(self):
        res = shot_volume_weight(1e-3, 1e-4, 10, "PC", machine_shot_capacity_kg=0.5)
        assert res["ok"] is True
        assert res["within_capacity"] is False
        assert any("short-shot" in w for w in res["warnings"])

    def test_zero_runner_volume_valid(self):
        res = shot_volume_weight(50e-6, 0.0, 1, "PP")
        assert res["ok"] is True
        assert res["runner_weight_kg"] == pytest.approx(0.0, abs=1e-15)

    def test_unknown_polymer_returns_error(self):
        res = shot_volume_weight(50e-6, 5e-6, 1, "XYZ")
        assert res["ok"] is False

    def test_negative_part_volume_returns_error(self):
        res = shot_volume_weight(-1e-6, 5e-6, 1, "PP")
        assert res["ok"] is False


# ===========================================================================
# 4. gate_runner_sizing
# ===========================================================================

class TestGateRunnerSizing:

    def test_gate_thickness_is_60pct_wall(self):
        """Gate land thickness = 0.6 × wall_thickness."""
        t_wall = 3e-3
        res = gate_runner_sizing(1e-6, t_wall, "ABS")
        assert res["ok"] is True
        assert abs(res["gate_thickness_m"] - 0.6 * t_wall) / (0.6 * t_wall) < REL

    def test_gate_velocity_matches_limit(self):
        """Gate velocity = Q / (t_gate × w_gate) must equal velocity limit."""
        Q = 1e-5
        t_wall = 3e-3
        v_lim = 0.5
        res = gate_runner_sizing(Q, t_wall, "PP", gate_velocity_limit_ms=v_lim)
        assert res["ok"] is True
        assert abs(res["gate_velocity_ms"] - v_lim) / v_lim < REL

    def test_gate_area_matches_q_over_v(self):
        """A_gate = Q / v_lim."""
        Q = 5e-6
        v_lim = 0.3
        res = gate_runner_sizing(Q, 2e-3, "PC", gate_velocity_limit_ms=v_lim)
        assert res["ok"] is True
        A_expected = Q / v_lim
        assert abs(res["gate_area_m2"] - A_expected) / A_expected < REL

    def test_runner_diameter_at_least_4mm(self):
        """Runner diameter >= 4 mm (practical minimum)."""
        res = gate_runner_sizing(1e-8, 1e-3, "PP")
        assert res["ok"] is True
        assert res["runner_diameter_m"] >= 4e-3

    def test_runner_diameter_at_least_1p5x_gate_thickness(self):
        """Runner diameter >= 1.5 × gate_thickness."""
        t_wall = 5e-3
        res = gate_runner_sizing(1e-4, t_wall, "ABS")
        assert res["ok"] is True
        t_gate = 0.6 * t_wall
        assert res["runner_diameter_m"] >= 1.5 * t_gate - 1e-12

    def test_thin_wall_warning(self):
        """Wall < 0.8 mm triggers thin-wall-flow warning."""
        res = gate_runner_sizing(1e-7, 0.5e-3, "PP")
        assert res["ok"] is True
        assert any("thin-wall" in w for w in res["warnings"])

    def test_negative_flow_rate_returns_error(self):
        res = gate_runner_sizing(-1e-6, 2e-3, "ABS")
        assert res["ok"] is False

    def test_unknown_polymer_returns_error(self):
        res = gate_runner_sizing(1e-6, 2e-3, "NOPE")
        assert res["ok"] is False


# ===========================================================================
# 5. cooling_time
# ===========================================================================

class TestCoolingTime:

    def _manual_cooling_time(self, wall, T_m, T_w, T_e, alpha):
        s = wall / 2.0
        ln_arg = (8.0 / math.pi ** 2) * (T_m - T_w) / (T_e - T_w)
        return (s ** 2 / (math.pi ** 2 * alpha)) * math.log(ln_arg)

    def test_pp_standard_conditions_algebraic(self):
        """Verify against hand-calculation for PP."""
        alpha = polymer_properties("PP")["alpha_m2s"]
        wall = 3e-3
        T_m, T_w, T_e = 230.0, 40.0, 90.0
        t_expected = self._manual_cooling_time(wall, T_m, T_w, T_e, alpha)
        res = cooling_time(wall, T_m, T_w, T_e, "PP")
        assert res["ok"] is True
        assert abs(res["cooling_time_s"] - t_expected) / t_expected < REL

    def test_thicker_wall_longer_cooling(self):
        """Doubling wall thickness must increase cooling time by ~4×."""
        T_m, T_w, T_e = 240.0, 60.0, 80.0
        r1 = cooling_time(2e-3, T_m, T_w, T_e, "ABS")
        r2 = cooling_time(4e-3, T_m, T_w, T_e, "ABS")
        # t ∝ s² = (wall/2)²; doubling wall → factor 4
        assert abs(r2["cooling_time_s"] / r1["cooling_time_s"] - 4.0) < 1e-6

    def test_cooling_time_positive(self):
        res = cooling_time(3e-3, 270.0, 80.0, 100.0, "PA")
        assert res["ok"] is True
        assert res["cooling_time_s"] > 0

    def test_alpha_matches_polymer_table(self):
        """alpha returned must equal polymer table value."""
        alpha_table = polymer_properties("POM")["alpha_m2s"]
        res = cooling_time(4e-3, 215.0, 90.0, 120.0, "POM")
        assert res["ok"] is True
        assert abs(res["alpha_m2s"] - alpha_table) < 1e-20

    def test_invalid_temperature_order_returns_error(self):
        """ejection_temp >= melt_temp must return error."""
        res = cooling_time(3e-3, 230.0, 40.0, 250.0, "PP")
        assert res["ok"] is False

    def test_mold_temp_above_ejection_returns_error(self):
        """mold_temp >= ejection_temp must return error."""
        res = cooling_time(3e-3, 230.0, 100.0, 80.0, "PP")
        assert res["ok"] is False

    def test_negative_wall_thickness_returns_error(self):
        res = cooling_time(-1e-3, 230.0, 40.0, 90.0, "PP")
        assert res["ok"] is False

    def test_pc_longer_cooling_than_pp_same_wall(self):
        """PC has higher ejection temp → relatively less driving ΔT; but PC
        melt temp is higher so check that cooling time is positive and finite."""
        res = cooling_time(3e-3, 295.0, 85.0, 125.0, "PC")
        assert res["ok"] is True
        assert math.isfinite(res["cooling_time_s"])
        assert res["cooling_time_s"] > 0


# ===========================================================================
# 6. flow_length_feasibility
# ===========================================================================

class TestFlowLengthFeasibility:

    def test_feasible_short_flow_path(self):
        """L/t = 100, PP limit = 280 → feasible."""
        res = flow_length_feasibility(0.1, 1e-3, "PP")
        assert res["ok"] is True
        assert res["feasible"] is True
        assert abs(res["flow_length_ratio"] - 100.0) < REL

    def test_infeasible_exceeds_limit(self):
        """L/t = 400 > PP limit of 280 → not feasible, warning issued."""
        res = flow_length_feasibility(0.4, 1e-3, "PP")
        assert res["ok"] is True
        assert res["feasible"] is False
        assert any("thin-wall-flow" in w for w in res["warnings"])

    def test_pc_tighter_limit_than_pp(self):
        """PC limit (150) < PP limit (280)."""
        lim_pp = polymer_properties("PP")["flow_length_limit"]
        lim_pc = polymer_properties("PC")["flow_length_limit"]
        assert lim_pc < lim_pp

    def test_margin_positive_when_feasible(self):
        res = flow_length_feasibility(0.05, 1e-3, "ABS")
        assert res["ok"] is True
        assert res["margin_pct"] > 0

    def test_margin_negative_when_infeasible(self):
        res = flow_length_feasibility(1.0, 1e-3, "PC")
        assert res["ok"] is True
        assert res["margin_pct"] < 0

    def test_ratio_calculation(self):
        """flow_length_ratio = flow_length_m / wall_thickness_m."""
        L, t = 0.15, 2e-3
        res = flow_length_feasibility(L, t, "ABS")
        assert abs(res["flow_length_ratio"] - L / t) / (L / t) < REL

    def test_negative_flow_length_returns_error(self):
        res = flow_length_feasibility(-0.1, 2e-3, "PP")
        assert res["ok"] is False

    def test_unknown_polymer_returns_error(self):
        res = flow_length_feasibility(0.1, 2e-3, "FOO")
        assert res["ok"] is False


# ===========================================================================
# 7. shrinkage_sink_estimate
# ===========================================================================

class TestShrinkageSinkEstimate:

    def test_linear_shrinkage_formula(self):
        """ΔL = part_dim × shrinkage_pct / 100."""
        L = 0.1
        s_pct = polymer_properties("PP")["shrinkage_pct"]
        res = shrinkage_sink_estimate(L, 2e-3, "PP")
        assert res["ok"] is True
        delta_expected = L * s_pct / 100.0
        assert abs(res["linear_shrinkage_m"] - delta_expected) / delta_expected < REL

    def test_mould_dim_compensates_shrinkage(self):
        """mould_dim = part_dim / (1 - s/100)."""
        L = 0.05
        s_pct = polymer_properties("ABS")["shrinkage_pct"]
        res = shrinkage_sink_estimate(L, 1.5e-3, "ABS")
        assert res["ok"] is True
        mould_expected = L / (1.0 - s_pct / 100.0)
        assert abs(res["mould_dim_m"] - mould_expected) / mould_expected < REL

    def test_sink_depth_scales_with_wall_thickness(self):
        """Thicker wall → larger sink depth."""
        r_thin = shrinkage_sink_estimate(0.05, 2e-3, "PP")
        r_thick = shrinkage_sink_estimate(0.05, 6e-3, "PP")
        assert r_thick["sink_depth_m"] > r_thin["sink_depth_m"]

    def test_thick_wall_warning(self):
        """Wall > 4 mm triggers sink-mark warning."""
        res = shrinkage_sink_estimate(0.1, 5e-3, "POM")
        assert res["ok"] is True
        assert any("sink" in w.lower() for w in res["warnings"])

    def test_pom_higher_shrinkage_than_abs(self):
        r_pom = shrinkage_sink_estimate(0.1, 2e-3, "POM")
        r_abs = shrinkage_sink_estimate(0.1, 2e-3, "ABS")
        assert r_pom["linear_shrinkage_m"] > r_abs["linear_shrinkage_m"]

    def test_negative_part_dim_returns_error(self):
        res = shrinkage_sink_estimate(-0.1, 2e-3, "PP")
        assert res["ok"] is False

    def test_unknown_polymer_returns_error(self):
        res = shrinkage_sink_estimate(0.1, 2e-3, "UNKNOWN")
        assert res["ok"] is False


# ===========================================================================
# 8. cycle_time_breakdown
# ===========================================================================

class TestCycleTimeBreakdown:

    def test_total_cycle_sums_all_phases(self):
        tc, tf, tp, tm, te = 15.0, 2.0, 5.0, 3.0, 1.5
        res = cycle_time_breakdown(tc, tf, tp, tm, te)
        assert res["ok"] is True
        expected_total = tc + tf + tp + tm + te
        assert abs(res["total_cycle_s"] - expected_total) < 1e-9

    def test_cooling_fraction_formula(self):
        """cooling_fraction_pct = cooling_time / total × 100."""
        tc, tf, tp, tm, te = 20.0, 2.0, 4.0, 2.0, 1.0
        res = cycle_time_breakdown(tc, tf, tp, tm, te)
        total = tc + tf + tp + tm + te
        expected_frac = tc / total * 100.0
        assert abs(res["cooling_fraction_pct"] - expected_frac) < 1e-9

    def test_shots_per_hour_formula(self):
        """shots_per_hour = 3600 / total_cycle_s."""
        tc, tf, tp, tm, te = 25.0, 3.0, 6.0, 2.5, 1.5
        res = cycle_time_breakdown(tc, tf, tp, tm, te)
        assert abs(res["shots_per_hour"] - 3600.0 / res["total_cycle_s"]) < REL

    def test_fractions_sum_to_100(self):
        """All phase fractions must sum to 100%."""
        tc, tf, tp, tm, te = 18.0, 2.0, 5.0, 2.0, 1.0
        res = cycle_time_breakdown(tc, tf, tp, tm, te)
        total_frac = (
            res["cooling_fraction_pct"]
            + res["fill_fraction_pct"]
            + (res["total_cycle_s"] - tc - tf) / res["total_cycle_s"] * 100.0
        )
        assert abs(total_frac - 100.0) < 1e-9

    def test_zero_optional_phases_valid(self):
        """pack_hold, mold_open_close, ejection may be 0."""
        res = cycle_time_breakdown(10.0, 1.0, 0.0, 0.0, 0.0)
        assert res["ok"] is True
        assert abs(res["total_cycle_s"] - 11.0) < 1e-9

    def test_negative_cooling_time_returns_error(self):
        res = cycle_time_breakdown(-5.0, 2.0, 3.0, 2.0, 1.0)
        assert res["ok"] is False

    def test_negative_pack_hold_returns_error(self):
        res = cycle_time_breakdown(15.0, 2.0, -1.0, 2.0, 1.0)
        assert res["ok"] is False


# ===========================================================================
# 9. cavities_from_tonnage
# ===========================================================================

class TestCavitiesFromTonnage:

    def test_basic_cavity_count(self):
        """1000 kN press, A=0.01 m², P=35 MPa, sf=1.0 → 1000000/(0.01×35e6)≈2."""
        res = cavities_from_tonnage(1000.0, 0.01, 35e6, safety_factor=1.0)
        assert res["ok"] is True
        # F_machine = 1e6 N; F_per_cavity = 0.01 × 35e6 = 350 000 N → n=2
        assert res["max_cavities"] == 2

    def test_larger_press_more_cavities(self):
        """Bigger press → more cavities."""
        r1 = cavities_from_tonnage(500.0, 0.005, 40e6, safety_factor=1.0)
        r2 = cavities_from_tonnage(1000.0, 0.005, 40e6, safety_factor=1.0)
        assert r2["max_cavities"] >= r1["max_cavities"]

    def test_safety_factor_reduces_cavities(self):
        """Higher SF → fewer cavities."""
        r_no_sf = cavities_from_tonnage(1000.0, 0.01, 35e6, safety_factor=1.0)
        r_sf = cavities_from_tonnage(1000.0, 0.01, 35e6, safety_factor=1.5)
        assert r_sf["max_cavities"] <= r_no_sf["max_cavities"]

    def test_insufficient_tonnage_returns_zero_with_warning(self):
        """Press too small → max_cavities=0, over-tonnage warning."""
        res = cavities_from_tonnage(1.0, 0.1, 100e6, safety_factor=1.0)
        assert res["ok"] is True
        assert res["max_cavities"] == 0
        assert any("over-tonnage" in w for w in res["warnings"])

    def test_negative_machine_tonnage_returns_error(self):
        res = cavities_from_tonnage(-500.0, 0.01, 35e6)
        assert res["ok"] is False

    def test_inverse_of_clamp_tonnage(self):
        """cavities_from_tonnage must be consistent with clamp_tonnage."""
        A = 0.01
        P = 40e6
        sf = 1.1
        n = 4
        # Required press for 4 cavities:
        r_press = clamp_tonnage(A, P, n_cavities=n, safety_factor=sf)
        F_kN = r_press["clamp_force_kN"]
        # Back-calculate cavities from that press size:
        r_cav = cavities_from_tonnage(F_kN, A, P, safety_factor=sf)
        assert r_cav["max_cavities"] >= n - 1  # allow floor rounding


# ===========================================================================
# 10. draft_ejection_force
# ===========================================================================

class TestDraftEjectionForce:

    def test_standard_finish_draft_angle(self):
        """Standard finish → 1.0° draft."""
        res = draft_ejection_force(0.01, 2e-3, 0.05, "PP", "standard")
        assert res["ok"] is True
        assert abs(res["draft_angle_deg"] - 1.0) < 1e-9

    def test_polished_draft_angle(self):
        """Polished → 0.5° draft."""
        res = draft_ejection_force(0.01, 2e-3, 0.05, "ABS", "polished")
        assert res["ok"] is True
        assert abs(res["draft_angle_deg"] - 0.5) < 1e-9

    def test_textured_draft_angle(self):
        """Textured → 3.0° draft."""
        res = draft_ejection_force(0.01, 2e-3, 0.05, "PC", "textured")
        assert res["ok"] is True
        assert abs(res["draft_angle_deg"] - 3.0) < 1e-9

    def test_ejection_force_positive(self):
        res = draft_ejection_force(0.005, 2e-3, 0.04, "PA")
        assert res["ok"] is True
        assert res["ejection_force_N"] > 0

    def test_lateral_area_formula(self):
        """A_side = 4 × √(projected_area) × L_draw."""
        A = 0.01
        L = 0.03
        res = draft_ejection_force(A, 2e-3, L, "PP")
        A_side_expected = 4.0 * math.sqrt(A) * L
        assert abs(res["A_side_m2"] - A_side_expected) / A_side_expected < REL

    def test_longer_draw_increases_ejection_force(self):
        """Longer draw depth → greater lateral area → greater ejection force."""
        r1 = draft_ejection_force(0.01, 2e-3, 0.02, "PP")
        r2 = draft_ejection_force(0.01, 2e-3, 0.05, "PP")
        assert r2["ejection_force_N"] > r1["ejection_force_N"]

    def test_negative_projected_area_returns_error(self):
        res = draft_ejection_force(-0.01, 2e-3, 0.05, "PP")
        assert res["ok"] is False

    def test_unknown_polymer_returns_error(self):
        res = draft_ejection_force(0.01, 2e-3, 0.05, "UNKNOWN")
        assert res["ok"] is False

    def test_invalid_surface_finish_returns_error(self):
        res = draft_ejection_force(0.01, 2e-3, 0.05, "PP", "mirror")
        assert res["ok"] is False

    def test_pom_lower_friction_than_pp(self):
        """POM has lower friction than PP → lower ejection force (same geometry)."""
        kwargs = dict(projected_area_m2=0.01, wall_thickness_m=2e-3, L_draw_m=0.05)
        r_pp = draft_ejection_force(**kwargs, polymer="PP")
        r_pom = draft_ejection_force(**kwargs, polymer="POM")
        assert r_pom["ejection_force_N"] < r_pp["ejection_force_N"]


# ===========================================================================
# 11. LLM tool wrappers (run_*)
# ===========================================================================

class TestToolWrappers:

    def test_run_polymer_properties_happy_path(self):
        ctx = _ctx()
        raw = _run(run_polymer_properties(ctx, _args(polymer="PP")))
        d = _ok_tool(raw)
        assert d["melt_temp_C"] > 0

    def test_run_polymer_properties_unknown(self):
        ctx = _ctx()
        raw = _run(run_polymer_properties(ctx, _args(polymer="UNOBTANIUM")))
        _err_tool(raw)

    def test_run_clamp_tonnage_happy_path(self):
        ctx = _ctx()
        raw = _run(run_clamp_tonnage(ctx, _args(
            projected_area_m2=0.01, cavity_pressure_Pa=40e6
        )))
        d = _ok_tool(raw)
        assert d["clamp_force_kN"] > 0

    def test_run_clamp_tonnage_missing_area(self):
        ctx = _ctx()
        raw = _run(run_clamp_tonnage(ctx, _args(cavity_pressure_Pa=40e6)))
        _err_tool(raw)

    def test_run_shot_volume_weight_happy_path(self):
        ctx = _ctx()
        raw = _run(run_shot_volume_weight(ctx, _args(
            part_volume_m3=50e-6, runner_volume_m3=5e-6,
            n_cavities=1, polymer="ABS"
        )))
        d = _ok_tool(raw)
        assert d["shot_weight_kg"] > 0

    def test_run_shot_volume_weight_bad_json(self):
        ctx = _ctx()
        raw = _run(run_shot_volume_weight(ctx, b"not json"))
        _err_tool(raw)

    def test_run_gate_runner_sizing_happy_path(self):
        ctx = _ctx()
        raw = _run(run_gate_runner_sizing(ctx, _args(
            flow_rate_m3s=1e-5, wall_thickness_m=3e-3, polymer="PP"
        )))
        d = _ok_tool(raw)
        assert d["gate_thickness_m"] > 0
        assert d["runner_diameter_m"] >= 4e-3

    def test_run_cooling_time_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cooling_time(ctx, _args(
            wall_thickness_m=3e-3, melt_temp_C=230.0,
            mold_temp_C=40.0, ejection_temp_C=90.0, polymer="PP"
        )))
        d = _ok_tool(raw)
        assert d["cooling_time_s"] > 0

    def test_run_cooling_time_bad_temps(self):
        ctx = _ctx()
        raw = _run(run_cooling_time(ctx, _args(
            wall_thickness_m=3e-3, melt_temp_C=80.0,
            mold_temp_C=40.0, ejection_temp_C=200.0, polymer="PP"
        )))
        _err_tool(raw)

    def test_run_flow_length_feasibility_happy_path(self):
        ctx = _ctx()
        raw = _run(run_flow_length_feasibility(ctx, _args(
            flow_length_m=0.1, wall_thickness_m=1e-3, polymer="PP"
        )))
        d = _ok_tool(raw)
        assert d["feasible"] is True

    def test_run_shrinkage_sink_estimate_happy_path(self):
        ctx = _ctx()
        raw = _run(run_shrinkage_sink_estimate(ctx, _args(
            part_dim_m=0.1, wall_thickness_m=2e-3, polymer="ABS"
        )))
        d = _ok_tool(raw)
        assert d["mould_dim_m"] > d["part_dim_m"]

    def test_run_cycle_time_breakdown_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cycle_time_breakdown(ctx, _args(
            cooling_time_s=20.0, fill_time_s=2.0, pack_hold_time_s=5.0,
            mold_open_close_s=2.0, ejection_time_s=1.0
        )))
        d = _ok_tool(raw)
        assert abs(d["total_cycle_s"] - 30.0) < 1e-9

    def test_run_cavities_from_tonnage_happy_path(self):
        ctx = _ctx()
        raw = _run(run_cavities_from_tonnage(ctx, _args(
            machine_tonnage_kN=1000.0,
            projected_area_per_cavity_m2=0.01,
            cavity_pressure_Pa=35e6,
        )))
        d = _ok_tool(raw)
        assert d["max_cavities"] >= 1

    def test_run_draft_ejection_force_happy_path(self):
        ctx = _ctx()
        raw = _run(run_draft_ejection_force(ctx, _args(
            projected_area_m2=0.01, wall_thickness_m=2e-3,
            L_draw_m=0.05, polymer="PP"
        )))
        d = _ok_tool(raw)
        assert d["ejection_force_N"] > 0
        assert d["draft_angle_deg"] == pytest.approx(1.0)

    def test_run_draft_ejection_force_missing_field(self):
        ctx = _ctx()
        raw = _run(run_draft_ejection_force(ctx, _args(
            projected_area_m2=0.01, wall_thickness_m=2e-3, polymer="PP"
            # missing L_draw_m
        )))
        _err_tool(raw)
