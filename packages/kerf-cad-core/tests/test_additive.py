"""
Hermetic tests for kerf_cad_core.additive — additive-manufacturing
process planning / DFAM calculators.

Coverage:
  dfam.process_params             — property lookup and error paths
  dfam.build_time_estimate        — layer count × layer time + travel
  dfam.support_volume             — overhang support volume heuristic
  dfam.overhang_removability      — overhang angle → support need + removability
  dfam.orientation_cost           — scalar cost function
  dfam.best_orientation           — pick best of N candidates
  dfam.shrinkage_compensation     — compensated model dimension
  dfam.lattice_infill             — Gibson-Ashby E_eff, mass
  dfam.feature_checks             — min wall / hole / bridge checks
  dfam.cost_rollup                — machine + material + post cost
  dfam.nesting_packing            — powder-bed packing + batch count
  tools.*                         — LLM wrapper happy + error paths

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Calculations verified algebraically against published formulas.

References
----------
Gibson, I., Rosen, D. & Stucker, B. "Additive Manufacturing Technologies", 2nd ed.
Gibson, L.J. & Ashby, M.F. "Cellular Solids", 2nd ed.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.additive.dfam import (
    process_params,
    build_time_estimate,
    support_volume,
    overhang_removability,
    orientation_cost,
    best_orientation,
    shrinkage_compensation,
    lattice_infill,
    feature_checks,
    cost_rollup,
    nesting_packing,
)
from kerf_cad_core.additive.tools import (
    run_am_process_params,
    run_am_build_time_estimate,
    run_am_support_volume,
    run_am_overhang_removability,
    run_am_orientation_cost,
    run_am_best_orientation,
    run_am_shrinkage_compensation,
    run_am_lattice_infill,
    run_am_feature_checks,
    run_am_cost_rollup,
    run_am_nesting_packing,
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
# 1. process_params
# ===========================================================================

class TestProcessParams:

    def test_fdm_lookup(self):
        res = process_params("FDM")
        assert res["ok"] is True
        assert res["process"] == "FDM"
        assert res["min_wall_m"] > 0
        assert res["overhang_threshold_deg"] == 45.0
        assert res["needs_support"] is True
        assert res["powder_bed"] is False

    def test_all_processes_return_ok(self):
        for p in ("FDM", "SLA", "SLS", "MJF", "DMLS"):
            r = process_params(p)
            assert r["ok"] is True, f"expected ok for {p}"

    def test_sls_powder_bed(self):
        r = process_params("SLS")
        assert r["powder_bed"] is True
        assert r["needs_support"] is False

    def test_mjf_powder_bed(self):
        r = process_params("MJF")
        assert r["powder_bed"] is True

    def test_case_insensitive(self):
        assert process_params("fdm")["ok"] is True
        assert process_params("Sla")["ok"] is True

    def test_unknown_process_error(self):
        r = process_params("INKJET")
        assert r["ok"] is False
        assert "reason" in r

    def test_dmls_min_wall_smallest(self):
        """DMLS can print finer features than FDM."""
        assert process_params("DMLS")["min_wall_m"] < process_params("FDM")["min_wall_m"]

    def test_tool_happy_path(self):
        raw = _run(run_am_process_params(_ctx(), _args(process="SLS")))
        d = _ok_tool(raw)
        assert d["powder_bed"] is True

    def test_tool_missing_process(self):
        raw = _run(run_am_process_params(_ctx(), _args()))
        _err_tool(raw)


# ===========================================================================
# 2. build_time_estimate
# ===========================================================================

class TestBuildTimeEstimate:

    def test_layer_count_hand_calc(self):
        # 100 mm tall part, 0.2 mm layers → 500 layers
        res = build_time_estimate("FDM", [0.1, 0.1, 0.1], layer_thickness_m=0.0002)
        assert res["ok"] is True
        assert res["layer_count"] == 500

    def test_total_time_components(self):
        # deposit_time + travel_time should equal build_time_s
        res = build_time_estimate("FDM", [0.05, 0.05, 0.05], layer_thickness_m=0.0002)
        assert res["ok"] is True
        assert abs(res["deposit_time_s"] + res["travel_time_s"] - res["build_time_s"]) < 1e-4

    def test_travel_overhead(self):
        # With 20% travel overhead, travel_time = 0.20 × deposit_time
        res = build_time_estimate(
            "FDM", [0.05, 0.05, 0.05],
            layer_thickness_m=0.0002,
            travel_overhead_frac=0.20,
        )
        assert res["ok"] is True
        assert abs(res["travel_time_s"] - res["deposit_time_s"] * 0.20) < 1e-3

    def test_build_time_h_consistent(self):
        res = build_time_estimate("SLA", [0.03, 0.03, 0.03])
        assert res["ok"] is True
        # build_time_h is rounded to 4dp so allow small rounding tolerance
        assert abs(res["build_time_h"] - res["build_time_s"] / 3600.0) < 1e-4

    def test_invalid_bbox_rejected(self):
        r = build_time_estimate("FDM", [0.05, 0.05, -0.1])
        assert r["ok"] is False

    def test_invalid_fill_fraction_rejected(self):
        r = build_time_estimate("FDM", [0.05, 0.05, 0.05], fill_fraction=0.0)
        assert r["ok"] is False

    def test_tool_happy_path(self):
        raw = _run(run_am_build_time_estimate(
            _ctx(),
            _args(process="FDM", bounding_box_m=[0.1, 0.1, 0.1]),
        ))
        d = _ok_tool(raw)
        assert d["layer_count"] > 0

    def test_tool_missing_bbox(self):
        raw = _run(run_am_build_time_estimate(_ctx(), _args(process="FDM")))
        _err_tool(raw)


# ===========================================================================
# 3. support_volume
# ===========================================================================

class TestSupportVolume:

    def test_zero_overhang_gives_zero_support(self):
        res = support_volume(1e-5, 1e-3, overhang_fraction=0.0, support_height_m=0.05)
        assert res["ok"] is True
        assert res["support_volume_m3"] == 0.0

    def test_hand_calc(self):
        # projected_area=0.01 m², overhang_fraction=0.5, height=0.05, density=0.15
        # sv = 0.01 × 0.5 × 0.05 × 0.15 = 3.75e-6 m³
        res = support_volume(
            1e-4, 0.01,
            overhang_fraction=0.5,
            support_density=0.15,
            support_height_m=0.05,
        )
        assert res["ok"] is True
        expected = 0.01 * 0.5 * 0.05 * 0.15
        assert abs(res["support_volume_m3"] - expected) < 1e-12

    def test_ratio_computed(self):
        res = support_volume(1e-4, 0.01, overhang_fraction=0.3, support_height_m=0.02)
        assert res["ok"] is True
        assert "support_to_part_ratio" in res

    def test_invalid_part_volume(self):
        r = support_volume(-1e-5, 1e-3)
        assert r["ok"] is False

    def test_tool_happy_path(self):
        raw = _run(run_am_support_volume(
            _ctx(),
            _args(part_volume_m3=1e-5, projected_area_m2=1e-3, support_height_m=0.05),
        ))
        _ok_tool(raw)


# ===========================================================================
# 4. overhang_removability
# ===========================================================================

class TestOverhangRemovability:

    def test_fdm_below_threshold_no_support(self):
        r = overhang_removability("FDM", 30.0)
        assert r["ok"] is True
        assert r["needs_support"] is False
        assert r["removability"] == "N/A"

    def test_fdm_above_threshold_needs_support(self):
        r = overhang_removability("FDM", 60.0)
        assert r["ok"] is True
        assert r["needs_support"] is True

    def test_sls_never_needs_support(self):
        r = overhang_removability("SLS", 89.0)
        assert r["ok"] is True
        assert r["needs_support"] is False
        assert r["removability"] == "easy"

    def test_mjf_never_needs_support(self):
        r = overhang_removability("MJF", 85.0)
        assert r["ok"] is True
        assert r["needs_support"] is False

    def test_dmls_steep_overhang_difficult(self):
        r = overhang_removability("DMLS", 80.0)
        assert r["ok"] is True
        assert r["removability"] == "difficult"
        assert len(r["warnings"]) > 0

    def test_sla_moderate_overhang(self):
        r = overhang_removability("SLA", 55.0)
        assert r["ok"] is True
        assert r["removability"] == "moderate"

    def test_invalid_angle(self):
        r = overhang_removability("FDM", 95.0)
        assert r["ok"] is False

    def test_tool_happy_path(self):
        raw = _run(run_am_overhang_removability(
            _ctx(), _args(process="FDM", overhang_angle_deg=50.0),
        ))
        d = _ok_tool(raw)
        assert d["needs_support"] is True


# ===========================================================================
# 5 & 6. orientation_cost / best_orientation
# ===========================================================================

class TestOrientationCost:

    def test_zero_overhang_lower_cost(self):
        r_no_oh = orientation_cost([0.1, 0.05, 0.03], 0.05, 0.0, "FDM")
        r_with_oh = orientation_cost([0.1, 0.05, 0.03], 0.05, 0.04, "FDM")
        assert r_no_oh["ok"] is True
        assert r_with_oh["ok"] is True
        assert r_no_oh["cost"] < r_with_oh["cost"]

    def test_sls_support_term_is_zero(self):
        r = orientation_cost([0.1, 0.1, 0.05], 0.05, 0.03, "SLS")
        assert r["ok"] is True
        assert r["support_term"] == 0.0

    def test_cost_is_positive(self):
        r = orientation_cost([0.05, 0.05, 0.05], 0.015, 0.005, "DMLS")
        assert r["ok"] is True
        assert r["cost"] > 0

    def test_overhang_exceeds_surface_area_rejected(self):
        r = orientation_cost([0.05, 0.05, 0.05], 0.01, 0.02, "FDM")
        assert r["ok"] is False

    def test_best_orientation_picks_lowest_cost(self):
        bboxes = [
            [0.10, 0.05, 0.20],  # tall (more support area)
            [0.10, 0.20, 0.05],  # flat (less build height)
        ]
        overhangs = [0.03, 0.005]
        r = best_orientation(bboxes, 0.06, overhangs, "FDM")
        assert r["ok"] is True
        # flat orientation should be cheaper (lower index 1)
        assert r["best_index"] == 1

    def test_best_orientation_mismatched_lengths(self):
        r = best_orientation([[0.1, 0.1, 0.1]], 0.05, [0.01, 0.02], "FDM")
        assert r["ok"] is False

    def test_tool_orientation_cost_happy(self):
        raw = _run(run_am_orientation_cost(
            _ctx(),
            _args(
                process="FDM",
                part_bbox_m=[0.05, 0.05, 0.08],
                surface_area_m2=0.02,
                overhang_area_m2=0.005,
            ),
        ))
        _ok_tool(raw)

    def test_tool_best_orientation_happy(self):
        raw = _run(run_am_best_orientation(
            _ctx(),
            _args(
                process="FDM",
                part_bbox_m_list=[[0.1, 0.1, 0.2], [0.2, 0.1, 0.1]],
                surface_area_m2=0.06,
                overhang_areas_m2=[0.02, 0.005],
            ),
        ))
        d = _ok_tool(raw)
        assert d["best_index"] in (0, 1)


# ===========================================================================
# 7. shrinkage_compensation
# ===========================================================================

class TestShrinkageCompensation:

    def test_pa12_sls_hand_calc(self):
        # SLS PA12 shrinkage = 3.0%
        # compensated = 0.100 / (1 - 0.030) = 0.100 / 0.970 ≈ 0.103093 m
        res = shrinkage_compensation(0.100, "SLS", "PA12")
        assert res["ok"] is True
        expected = 0.100 / (1 - 0.030)
        assert abs(res["compensated_dim_m"] - expected) < 1e-9

    def test_scale_factor_consistency(self):
        res = shrinkage_compensation(0.050, "FDM", "ABS")
        assert res["ok"] is True
        # both values are stored with rounding; allow for accumulated rounding error
        assert abs(res["compensated_dim_m"] - res["nominal_dim_m"] * res["scale_factor"]) < 1e-6

    def test_zero_shrinkage_material_gives_scale_1(self):
        # DMLS 316L shrinkage = 0.1%; scale factor ≈ 1.001
        res = shrinkage_compensation(0.100, "DMLS", "316L")
        assert res["ok"] is True
        assert res["scale_factor"] > 1.0
        assert res["scale_factor"] < 1.005

    def test_unknown_material_uses_default(self):
        res = shrinkage_compensation(0.050, "FDM", "UNOBTANIUM")
        assert res["ok"] is True
        assert len(res["warnings"]) > 0

    def test_invalid_dim(self):
        r = shrinkage_compensation(-0.1, "FDM")
        assert r["ok"] is False

    def test_tool_happy_path(self):
        raw = _run(run_am_shrinkage_compensation(
            _ctx(),
            _args(nominal_dim_m=0.100, process="SLS", material="PA12"),
        ))
        d = _ok_tool(raw)
        assert d["compensated_dim_m"] > 0.100


# ===========================================================================
# 8. lattice_infill (Gibson-Ashby)
# ===========================================================================

class TestLatticeInfill:

    def test_gyroid_hand_calc(self):
        # gyroid: E_eff = 0.3 × ρ_rel² × E_solid
        # ρ_rel=0.2, E_solid=3.5e9 Pa
        # E_eff = 0.3 × 0.04 × 3.5e9 = 42e6 Pa
        res = lattice_infill("FDM", "gyroid", 0.2, 3.5e9, 1240.0, 1e-5)
        assert res["ok"] is True
        expected_E = 0.3 * (0.2 ** 2) * 3.5e9
        assert abs(res["effective_modulus_Pa"] - expected_E) / expected_E < 1e-6

    def test_cubic_hand_calc(self):
        # cubic: E_eff = 1.0 × ρ_rel¹ × E_solid
        # ρ_rel=0.3, E_solid=193e9 Pa (316L)
        # E_eff = 0.3 × 193e9 = 57.9e9 Pa
        res = lattice_infill("DMLS", "cubic", 0.3, 193e9, 7980.0, 1e-5)
        assert res["ok"] is True
        expected_E = 1.0 * 0.3 * 193e9
        assert abs(res["effective_modulus_Pa"] - expected_E) / expected_E < 1e-6

    def test_mass_hand_calc(self):
        # ρ_eff = ρ_rel × ρ_solid = 0.25 × 1010 = 252.5 kg/m³
        # mass = 252.5 × 1e-4 = 0.02525 kg
        res = lattice_infill("SLS", "gyroid", 0.25, 1.7e9, 1010.0, 1e-4)
        assert res["ok"] is True
        expected_mass = 0.25 * 1010.0 * 1e-4
        assert abs(res["mass_kg"] - expected_mass) / expected_mass < 1e-6

    def test_relative_stiffness_gyroid_lt_cubic(self):
        """Gyroid (bending-dominated) is less stiff than cubic at same density."""
        rg = lattice_infill("FDM", "gyroid", 0.3, 3.5e9, 1240.0, 1e-5)
        rc = lattice_infill("FDM", "cubic", 0.3, 3.5e9, 1240.0, 1e-5)
        assert rg["relative_stiffness"] < rc["relative_stiffness"]

    def test_invalid_relative_density(self):
        r = lattice_infill("FDM", "gyroid", 1.0, 3.5e9, 1240.0, 1e-5)
        assert r["ok"] is False

    def test_invalid_infill_type(self):
        r = lattice_infill("FDM", "honeycomb", 0.2, 3.5e9, 1240.0, 1e-5)
        assert r["ok"] is False

    def test_tool_happy_path(self):
        raw = _run(run_am_lattice_infill(
            _ctx(),
            _args(
                process="FDM",
                infill_type="gyroid",
                relative_density=0.2,
                solid_modulus_Pa=3.5e9,
                solid_density_kg_m3=1240.0,
                volume_m3=1e-5,
            ),
        ))
        d = _ok_tool(raw)
        assert d["effective_modulus_Pa"] > 0

    def test_tool_missing_field(self):
        raw = _run(run_am_lattice_infill(
            _ctx(),
            _args(process="FDM", infill_type="gyroid"),
        ))
        _err_tool(raw)


# ===========================================================================
# 9. feature_checks
# ===========================================================================

class TestFeatureChecks:

    def test_fdm_wall_passes(self):
        r = feature_checks("FDM", wall_thickness_m=0.0010)  # 1.0 mm > 0.8 mm
        assert r["ok"] is True
        assert r["wall_pass"] is True
        assert len(r["warnings"]) == 0

    def test_fdm_wall_fails(self):
        r = feature_checks("FDM", wall_thickness_m=0.0005)  # 0.5 mm < 0.8 mm
        assert r["ok"] is True  # ok=True but warning
        assert r["wall_pass"] is False
        assert len(r["warnings"]) > 0

    def test_sla_hole_passes(self):
        r = feature_checks("SLA", hole_diameter_m=0.001)  # 1 mm > 0.5 mm
        assert r["ok"] is True
        assert r["hole_pass"] is True

    def test_dmls_bridge_passes(self):
        r = feature_checks("DMLS", bridge_span_m=0.008)  # 8 mm < 10 mm
        assert r["ok"] is True
        assert r["bridge_pass"] is True

    def test_fdm_bridge_fails(self):
        r = feature_checks("FDM", bridge_span_m=0.025)  # 25 mm > 20 mm
        assert r["ok"] is True
        assert r["bridge_pass"] is False
        assert any("bridge" in w.lower() for w in r["warnings"])

    def test_no_feature_supplied_error(self):
        r = feature_checks("FDM")
        assert r["ok"] is False

    def test_multiple_checks_at_once(self):
        r = feature_checks(
            "SLS",
            wall_thickness_m=0.0008,
            hole_diameter_m=0.002,
            bridge_span_m=0.040,
        )
        assert r["ok"] is True
        assert "wall_pass" in r
        assert "hole_pass" in r
        assert "bridge_pass" in r

    def test_tool_happy_path(self):
        raw = _run(run_am_feature_checks(
            _ctx(),
            _args(process="FDM", wall_thickness_m=0.001, hole_diameter_m=0.002),
        ))
        d = _ok_tool(raw)
        assert d["wall_pass"] is True


# ===========================================================================
# 10. cost_rollup
# ===========================================================================

class TestCostRollup:

    def test_machine_cost_hand_calc(self):
        # build_time_s=3600, machine_rate=3.0 → machine_cost=$3
        res = cost_rollup(
            "FDM", "PLA",
            build_time_s=3600.0,
            support_volume_m3=0.0,
            part_volume_m3=1e-5,
            machine_rate_per_h=3.0,
            material_cost_per_kg=20.0,
        )
        assert res["ok"] is True
        assert abs(res["machine_cost_usd"] - 3.0) < 1e-6

    def test_material_cost_hand_calc(self):
        # part_volume = 1e-5 m³, density PLA = 1240 kg/m³, cost $20/kg
        # mass = 1e-5 × 1240 = 0.0124 kg
        # material_cost = 0.0124 × 20 = $0.248
        res = cost_rollup(
            "FDM", "PLA",
            build_time_s=3600.0,
            support_volume_m3=0.0,
            part_volume_m3=1e-5,
            machine_rate_per_h=3.0,
            material_cost_per_kg=20.0,
        )
        assert res["ok"] is True
        expected_mass = 1e-5 * 1240.0
        expected_mat = expected_mass * 20.0
        assert abs(res["material_cost_usd"] - expected_mat) < 1e-4

    def test_total_includes_post(self):
        res = cost_rollup(
            "SLA", "standard_resin",
            build_time_s=7200.0,
            support_volume_m3=5e-7,
            part_volume_m3=2e-6,
            post_cost=5.0,
        )
        assert res["ok"] is True
        assert abs(res["total_cost_usd"] - (
            res["machine_cost_usd"] + res["material_cost_usd"] + res["post_cost_usd"]
        )) < 1e-4

    def test_invalid_build_time(self):
        r = cost_rollup("FDM", "PLA", build_time_s=-1.0,
                        support_volume_m3=0.0, part_volume_m3=1e-5)
        assert r["ok"] is False

    def test_tool_happy_path(self):
        raw = _run(run_am_cost_rollup(
            _ctx(),
            _args(
                process="DMLS",
                material="316L",
                build_time_s=18000.0,
                support_volume_m3=1e-7,
                part_volume_m3=5e-6,
            ),
        ))
        d = _ok_tool(raw)
        assert d["total_cost_usd"] > 0

    def test_tool_missing_field(self):
        raw = _run(run_am_cost_rollup(
            _ctx(),
            _args(process="FDM", material="PLA", build_time_s=3600.0),
        ))
        _err_tool(raw)


# ===========================================================================
# 11. nesting_packing
# ===========================================================================

class TestNestingPacking:

    def test_n_max_hand_calc(self):
        # build = 0.3×0.3×0.3 = 0.027 m³, φ=0.6, effective = 0.0162 m³
        # part = 1e-4 m³ → n_max = floor(0.0162 / 1e-4) = 162
        bv = 0.3 ** 3
        pv = 1e-4
        res = nesting_packing(bv, pv, n_parts=50, packing_factor=0.60)
        assert res["ok"] is True
        expected_n_max = int(bv * 0.60 / pv)
        assert res["n_max_per_build"] == expected_n_max

    def test_batches_needed(self):
        # n_max = 10, n_parts = 25 → ceil(25/10) = 3 batches
        bv = 1e-2
        pv = 1e-2 * 0.60 / 10  # exactly 10 parts per build
        res = nesting_packing(bv, pv, n_parts=25, packing_factor=0.60)
        assert res["ok"] is True
        assert res["batches_needed"] == 3

    def test_utilisation_below_one(self):
        res = nesting_packing(0.027, 1e-5, n_parts=10, packing_factor=0.65)
        assert res["ok"] is True
        assert res["utilisation"] <= 1.0

    def test_low_utilisation_warning(self):
        res = nesting_packing(0.027, 1e-5, n_parts=1, packing_factor=0.65)
        assert res["ok"] is True
        assert any("utilisation" in w.lower() for w in res["warnings"])

    def test_invalid_packing_factor(self):
        r = nesting_packing(0.027, 1e-5, n_parts=10, packing_factor=0.0)
        assert r["ok"] is False

    def test_tool_happy_path(self):
        raw = _run(run_am_nesting_packing(
            _ctx(),
            _args(
                build_volume_m3=0.027,
                part_volume_m3=1e-4,
                n_parts=100,
                packing_factor=0.65,
            ),
        ))
        d = _ok_tool(raw)
        assert d["batches_needed"] >= 1

    def test_tool_missing_field(self):
        raw = _run(run_am_nesting_packing(
            _ctx(),
            _args(build_volume_m3=0.027, part_volume_m3=1e-4),
        ))
        _err_tool(raw)


# ---------------------------------------------------------------------------
# Externally-citable reference cases
#   Gibson, L.J. & Ashby, M.F. "Cellular Solids: Structure and Properties",
#     2nd ed., Cambridge University Press (1997), Ch. 5.
#   Gibson, Rosen & Stucker "Additive Manufacturing Technologies", 2nd ed.
# ---------------------------------------------------------------------------

class TestAdditiveExternalReferenceCases:
    """Cross-checked against Gibson & Ashby 'Cellular Solids' 2nd ed. and
    standard DfAM cost/build-time relations (Gibson/Rosen/Stucker)."""

    def test_gibson_ashby_bending_dominated_exponent(self):
        # Gibson & Ashby Eq. 5.6 (open-cell, bending-dominated foam):
        # E*/Es = C (rho*/rhos)^2, C ≈ 0.3.  gyroid uses C1=0.3, n=2.
        r = lattice_infill("FDM", "gyroid", 0.30, 200e9, 7900.0, 1e-4)
        assert math.isclose(r["C1"], 0.3, rel_tol=1e-12)
        assert math.isclose(r["n_exponent"], 2.0, rel_tol=1e-12)
        assert math.isclose(r["effective_modulus_Pa"],
                            0.3 * 0.30 ** 2 * 200e9, rel_tol=1e-9)

    def test_gibson_ashby_stretch_dominated_linear(self):
        # Gibson & Ashby: stretch-dominated lattices scale linearly,
        # E*/Es ~ (rho*/rhos)^1.  cubic uses C1=1.0, n=1.
        r = lattice_infill("FDM", "cubic", 0.30, 200e9, 7900.0, 1e-4)
        assert math.isclose(r["n_exponent"], 1.0, rel_tol=1e-12)
        assert math.isclose(r["effective_modulus_Pa"],
                            1.0 * 0.30 ** 1 * 200e9, rel_tol=1e-9)

    def test_gibson_ashby_density_rule_of_mixtures(self):
        # Gibson & Ashby: relative density maps linearly to effective density
        # rho* = rho_rel * rho_s.
        r = lattice_infill("FDM", "gyroid", 0.30, 200e9, 7900.0, 1e-4)
        assert math.isclose(r["effective_density_kg_m3"], 0.30 * 7900.0,
                            rel_tol=1e-9)

    def test_gibson_ashby_relative_stiffness(self):
        # Relative stiffness E*/Es of a 30 %-dense gyroid = 0.3*0.3^2 = 0.027.
        r = lattice_infill("FDM", "gyroid", 0.30, 200e9, 7900.0, 1e-4)
        assert math.isclose(r["relative_stiffness"], 0.3 * 0.30 ** 2,
                            rel_tol=1e-4)

    def test_lattice_mass_density_volume(self):
        # m = rho_eff * V (mass-volume identity).
        r = lattice_infill("FDM", "gyroid", 0.30, 200e9, 7900.0, 1e-4)
        assert math.isclose(r["mass_kg"], 0.30 * 7900.0 * 1e-4, rel_tol=1e-4)

    def test_shrinkage_compensation_scale_factor(self):
        # Standard AM shrinkage compensation (Gibson/Rosen/Stucker §):
        # compensated dim = nominal / (1 - shrinkage).
        r = shrinkage_compensation(0.1, "SLS")
        s = r["shrinkage_fraction"]
        assert math.isclose(r["compensated_dim_m"], 0.1 / (1.0 - s),
                            rel_tol=1e-6)
        assert math.isclose(r["scale_factor"], 1.0 / (1.0 - s), rel_tol=1e-5)

    def test_cost_rollup_machine_time_linear(self):
        # DfAM cost model: machine cost = build_time_h * machine_rate.
        r = cost_rollup("SLS", "nylon", 3600.0, 1e-6, 1e-5,
                        machine_rate_per_h=30.0, material_cost_per_kg=80.0)
        assert math.isclose(r["build_time_h"], 1.0, rel_tol=1e-9)
        assert math.isclose(r["machine_cost_usd"], 1.0 * 30.0, rel_tol=1e-9)

    def test_cost_rollup_total_is_sum(self):
        # Total cost = machine + material + post (additive cost rollup).
        r = cost_rollup("SLS", "nylon", 3600.0, 1e-6, 1e-5,
                        machine_rate_per_h=30.0, material_cost_per_kg=80.0,
                        post_cost=5.0)
        assert math.isclose(
            r["total_cost_usd"],
            r["machine_cost_usd"] + r["material_cost_usd"] + r["post_cost_usd"],
            rel_tol=1e-9)

    def test_build_time_scales_with_height(self):
        # Layer-wise AM: build time grows with part height (layer count).
        a = build_time_estimate("FDM", (0.05, 0.05, 0.05))
        b = build_time_estimate("FDM", (0.05, 0.05, 0.10))
        assert b["build_time_s"] > a["build_time_s"]

    def test_support_volume_proportional_to_overhang(self):
        # More overhang area -> more support material (DfAM heuristic).
        a = support_volume(1e-4, 1e-2, overhang_fraction=0.1)
        b = support_volume(1e-4, 1e-2, overhang_fraction=0.4)
        assert b["support_volume_m3"] > a["support_volume_m3"]
