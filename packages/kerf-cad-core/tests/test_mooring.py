"""
Hermetic tests for kerf_cad_core.mooring — offshore mooring & station-keeping.

Coverage:
  lines.catenary_line       — inextensible catenary geometry and tensions
  lines.multiseg_catenary   — multi-segment catenary
  lines.mooring_system      — restoring force and stiffness
  lines.anchor_holding      — drag-embedment, pile, suction-caisson
  lines.morison_wave_current — Morison drag + inertia
  lines.mean_env_load       — wind + current hull force
  lines.watch_circle        — API RP 2SK offset limit
  lines.line_safety_factor  — SF check
  lines.riser_top_tension   — riser top tension
  tools.*                   — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas are verified algebraically against published catenary/offshore expressions.

References
----------
API RP 2SK (3rd ed., 2005) — Design and Analysis of Station-Keeping Systems.
Faltinsen, O.M. "Sea Loads on Ships and Offshore Structures", CUP 1990.
Morison, J.R. et al. (1950) — "The Force Exerted by Surface Waves on Piles".

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid
import warnings as _warnings_module

import pytest

from kerf_cad_core.mooring.lines import (
    catenary_line,
    multiseg_catenary,
    mooring_system,
    anchor_holding,
    morison_wave_current,
    mean_env_load,
    watch_circle,
    line_safety_factor,
    riser_top_tension,
)
from kerf_cad_core.mooring.tools import (
    run_catenary_line,
    run_multiseg_catenary,
    run_mooring_system,
    run_anchor_holding,
    run_morison_force,
    run_mean_env_load,
    run_watch_circle,
    run_line_sf,
    run_riser_top_tension,
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
# 1. catenary_line — inextensible catenary
# ===========================================================================

class TestCatenaryLine:

    def test_catenary_param_equals_H_over_w(self):
        """Catenary parameter a = H/w is returned correctly."""
        w, L, H = 400.0, 500.0, 200_000.0
        r = catenary_line(w, L, H)
        assert r["ok"] is True
        assert abs(r["catenary_param_m"] - H / w) < 1e-9

    def test_vertical_fairlead_tension_equals_sqrt_H2_V2(self):
        """T_fairlead = sqrt(H² + V_f²) must hold exactly."""
        w, L, H = 300.0, 600.0, 150_000.0
        r = catenary_line(w, L, H)
        assert r["ok"] is True
        V_f = r["V_fairlead_N"]
        T_f_expected = math.sqrt(H**2 + V_f**2)
        assert abs(r["T_fairlead_N"] - T_f_expected) / T_f_expected < REL

    def test_fully_suspended_V_fairlead_equals_wL(self):
        """For fully suspended catenary V_fairlead = w × L."""
        w, L, H = 200.0, 400.0, 800_000.0  # high H, large catenary param → fully suspended
        r = catenary_line(w, L, H)
        assert r["ok"] is True
        assert abs(r["V_fairlead_N"] - w * L) / (w * L) < REL

    def test_anchor_tension_equals_H_when_fully_suspended(self):
        """At the touch-down / bottom tangent point, T_anchor = H."""
        w, L, H = 200.0, 300.0, 600_000.0
        r = catenary_line(w, L, H)
        assert r["ok"] is True
        # T_anchor = sqrt(H² + V_anchor²); V_anchor = 0 for fully suspended
        assert abs(r["T_anchor_N"] - H) / H < REL

    def test_horizontal_span_formula_matches_catenary_identity(self):
        """
        For fully suspended catenary:
            x_span = a × asinh(wL/H) = (H/w) × arcsinh(wL/H)

        Derivation: arc length from lowest point to fairlead = L,
        catenary x = a × arcsinh(s/a) where s is arc length.
        At the fairlead s = L: x = a × arcsinh(L/a) = (H/w) × arcsinh(wL/H).
        """
        w, L, H = 500.0, 400.0, 1_000_000.0
        r = catenary_line(w, L, H)
        assert r["ok"] is True
        a = H / w
        x_expected = a * math.asinh(w * L / H)
        assert abs(r["horizontal_span_m"] - x_expected) / x_expected < REL

    def test_angle_fairlead_arctan_V_over_H(self):
        """angle_fairlead_deg = atan(V_f / H) in degrees."""
        w, L, H = 600.0, 500.0, 250_000.0
        r = catenary_line(w, L, H)
        assert r["ok"] is True
        expected_deg = math.degrees(math.atan2(r["V_fairlead_N"], H))
        assert abs(r["angle_fairlead_deg"] - expected_deg) < 1e-6

    def test_scope_ratio(self):
        """scope = L / water_depth when water_depth is supplied."""
        w, L, H = 300.0, 500.0, 100_000.0
        depth = 100.0
        r = catenary_line(w, L, H, water_depth=depth)
        assert r["ok"] is True
        assert abs(r["scope"] - L / depth) < 1e-9

    def test_profile_length_matches_n_profile_pts(self):
        """profile_x and profile_z have exactly n_profile_pts points."""
        r = catenary_line(300.0, 500.0, 200_000.0, n_profile_pts=20)
        assert r["ok"] is True
        assert len(r["profile_x"]) == 20
        assert len(r["profile_z"]) == 20

    def test_profile_x_monotone_increasing(self):
        """profile_x should be monotonically non-decreasing (anchor to fairlead)."""
        r = catenary_line(400.0, 600.0, 300_000.0, n_profile_pts=30)
        assert r["ok"] is True
        xs = r["profile_x"]
        for i in range(1, len(xs)):
            assert xs[i] >= xs[i - 1] - 1e-9, f"Non-monotone at i={i}: {xs[i-1]} > {xs[i]}"

    def test_profile_z_nonneg(self):
        """All profile_z values should be >= 0 (height above seabed)."""
        r = catenary_line(300.0, 400.0, 150_000.0, n_profile_pts=25)
        assert r["ok"] is True
        for z in r["profile_z"]:
            assert z >= -1e-9, f"Negative z in profile: {z}"

    def test_invalid_w_returns_error(self):
        r = catenary_line(-10.0, 500.0, 100_000.0)
        assert r["ok"] is False

    def test_invalid_L_returns_error(self):
        r = catenary_line(300.0, 0.0, 100_000.0)
        assert r["ok"] is False

    def test_invalid_H_returns_error(self):
        r = catenary_line(300.0, 500.0, -1.0)
        assert r["ok"] is False

    def test_elastic_catenary_span_longer_than_inextensible(self):
        """With finite EA, elastic stretch increases horizontal span."""
        w, L, H = 200.0, 500.0, 80_000.0
        r_inext = catenary_line(w, L, H)
        r_elas = catenary_line(w, L, H, EA=50_000_000.0)
        assert r_inext["ok"] is True
        assert r_elas["ok"] is True
        # Elastic catenary has slightly longer span due to stretch
        assert r_elas["horizontal_span_m"] >= r_inext["horizontal_span_m"] - 1e-3


# ===========================================================================
# 2. multiseg_catenary
# ===========================================================================

class TestMultisegCatenary:

    def test_single_segment_matches_catenary_line(self):
        """Single-segment multiseg must match catenary_line result."""
        w, L, H = 350.0, 500.0, 180_000.0
        r_single = catenary_line(w, L, H)
        r_multi = multiseg_catenary([{"w": w, "L": L}], H)
        assert r_single["ok"] is True
        assert r_multi["ok"] is True
        assert abs(r_multi["T_fairlead_N"] - r_single["T_fairlead_N"]) / r_single["T_fairlead_N"] < REL

    def test_two_segment_vertical_sum(self):
        """V_fairlead = sum of all segment V_fairlead values."""
        segs = [
            {"w": 400.0, "L": 300.0, "label": "chain"},
            {"w": 150.0, "L": 400.0, "label": "wire"},
        ]
        H = 200_000.0
        r = multiseg_catenary(segs, H)
        assert r["ok"] is True
        V_sum = sum(s["V_fairlead_N"] for s in r["segments_out"])
        assert abs(r["V_fairlead_N"] - V_sum) / max(V_sum, 1.0) < REL

    def test_total_arc_length_is_sum_of_segments(self):
        segs = [
            {"w": 400.0, "L": 200.0},
            {"w": 200.0, "L": 300.0},
            {"w": 100.0, "L": 150.0},
        ]
        H = 150_000.0
        r = multiseg_catenary(segs, H)
        assert r["ok"] is True
        expected_L = 200.0 + 300.0 + 150.0
        assert abs(r["total_arc_length_m"] - expected_L) < 1e-9

    def test_missing_w_returns_error(self):
        r = multiseg_catenary([{"L": 300.0}], H=100_000.0)
        assert r["ok"] is False

    def test_empty_segments_returns_error(self):
        r = multiseg_catenary([], H=100_000.0)
        assert r["ok"] is False


# ===========================================================================
# 3. mooring_system
# ===========================================================================

class TestMooringSystem:

    def _symmetric_4line_system(self):
        """4 lines at 0/90/180/270° — symmetric spread mooring."""
        lines = [
            {"w": 300.0, "L": 800.0, "H0": 200_000.0, "azimuth_deg": 0.0},
            {"w": 300.0, "L": 800.0, "H0": 200_000.0, "azimuth_deg": 90.0},
            {"w": 300.0, "L": 800.0, "H0": 200_000.0, "azimuth_deg": 180.0},
            {"w": 300.0, "L": 800.0, "H0": 200_000.0, "azimuth_deg": 270.0},
        ]
        return lines

    def test_zero_offset_restoring_force_near_zero(self):
        """At zero offset, symmetric system restoring force ≈ 0."""
        lines = self._symmetric_4line_system()
        r = mooring_system(lines, water_depth=200.0, fairlead_radius=50.0, offsets=[0.0])
        assert r["ok"] is True
        # Should be exactly zero by symmetry
        assert abs(r["restoring_force_N"][0]) < 1.0  # within 1 N

    def test_positive_offset_gives_negative_restoring_force(self):
        """Positive surge offset → negative (opposing) restoring force."""
        lines = self._symmetric_4line_system()
        r = mooring_system(lines, water_depth=200.0, fairlead_radius=50.0,
                           offsets=[0.0, 10.0, 20.0])
        assert r["ok"] is True
        # At positive offset, restoring force should oppose (be negative or zero)
        assert r["restoring_force_N"][1] <= 0.0

    def test_stiffness_list_length_matches_offsets(self):
        lines = self._symmetric_4line_system()
        offsets = [0.0, 5.0, 10.0, 15.0]
        r = mooring_system(lines, water_depth=200.0, fairlead_radius=50.0, offsets=offsets)
        assert r["ok"] is True
        assert len(r["stiffness_N_per_m"]) == len(offsets)

    def test_max_tension_increases_with_offset(self):
        """Larger offset → larger maximum line tension."""
        lines = self._symmetric_4line_system()
        r = mooring_system(lines, water_depth=200.0, fairlead_radius=50.0,
                           offsets=[0.0, 15.0])
        assert r["ok"] is True
        assert r["max_line_tension_N"][1] >= r["max_line_tension_N"][0]

    def test_empty_lines_returns_error(self):
        r = mooring_system([], water_depth=200.0, fairlead_radius=50.0, offsets=[0.0])
        assert r["ok"] is False

    def test_empty_offsets_returns_error(self):
        lines = self._symmetric_4line_system()
        r = mooring_system(lines, water_depth=200.0, fairlead_radius=50.0, offsets=[])
        assert r["ok"] is False


# ===========================================================================
# 4. anchor_holding
# ===========================================================================

class TestAnchorHolding:

    def test_drag_embedment_soft_clay_factor_30(self):
        """Drag-embedment holding = 30 × weight for soft_clay."""
        w_kN = 200.0
        r = anchor_holding("drag_embedment", anchor_weight_kN=w_kN, soil_type="soft_clay")
        assert r["ok"] is True
        assert abs(r["holding_kN"] - 30.0 * w_kN) < 1e-9

    def test_drag_embedment_sand_factor_10(self):
        """Drag-embedment holding = 10 × weight for sand."""
        w_kN = 150.0
        r = anchor_holding("drag_embedment", anchor_weight_kN=w_kN, soil_type="sand")
        assert r["ok"] is True
        assert abs(r["holding_kN"] - 10.0 * w_kN) < 1e-9

    def test_pile_capacity_formula(self):
        """Pile lateral capacity: H = 9 × Su × D × L."""
        D, Lp, Su_kPa = 1.5, 20.0, 100.0
        r = anchor_holding("pile", pile_diameter_m=D, pile_length_m=Lp, Su_kPa=Su_kPa)
        assert r["ok"] is True
        expected = 9.0 * Su_kPa * 1e3 * D * Lp / 1e3  # kN
        assert abs(r["holding_kN"] - expected) / expected < REL

    def test_suction_caisson_capacity_formula(self):
        """Suction caisson: H = Su × D × L × 10."""
        dc, Lc, su = 8.0, 12.0, 50.0
        r = anchor_holding("suction_caisson",
                            caisson_diameter_m=dc, caisson_length_m=Lc, Su_avg_kPa=su)
        assert r["ok"] is True
        expected = su * 1e3 * dc * Lc * 10.0 / 1e3  # kN
        assert abs(r["holding_kN"] - expected) / expected < REL

    def test_unknown_anchor_type_returns_error(self):
        r = anchor_holding("gravity_anchor")
        assert r["ok"] is False

    def test_drag_missing_weight_returns_error(self):
        r = anchor_holding("drag_embedment")
        assert r["ok"] is False

    def test_pile_missing_Su_returns_error(self):
        r = anchor_holding("pile", pile_diameter_m=1.0, pile_length_m=10.0)
        assert r["ok"] is False

    def test_suction_missing_diameter_returns_error(self):
        r = anchor_holding("suction_caisson", caisson_length_m=10.0, Su_avg_kPa=80.0)
        assert r["ok"] is False


# ===========================================================================
# 5. morison_wave_current
# ===========================================================================

class TestMorisonForce:

    def test_drag_force_per_m_formula(self):
        """f_drag/L = ½ × ρ × Cd × D × u_r² must match."""
        D = 1.0
        L = 10.0
        rho = 1025.0
        Cd = 1.0
        Cm = 2.0
        Uc = 0.5
        Uw = 2.0
        omega = 0.5
        k = 0.1
        r = morison_wave_current(D, L, rho, Cd, Cm, Uc, Uw, omega, k)
        assert r["ok"] is True
        u_r = Uc + Uw
        expected_drag_per_m = 0.5 * rho * Cd * D * u_r**2
        assert abs(r["F_drag_per_m_N_m"] - expected_drag_per_m) / expected_drag_per_m < REL

    def test_inertia_force_per_m_formula(self):
        """f_inertia/L = ρ × Cm × (π D²/4) × (ω × U_w) must match."""
        D = 0.8
        L = 20.0
        rho = 1025.0
        Cd = 0.7
        Cm = 2.0
        Uc = 0.0
        Uw = 1.5
        omega = 0.6
        k = 0.1
        r = morison_wave_current(D, L, rho, Cd, Cm, Uc, Uw, omega, k)
        assert r["ok"] is True
        A_ref = math.pi * D**2 / 4.0
        expected_inertia_per_m = rho * Cm * A_ref * (omega * Uw)
        assert abs(r["F_inertia_per_m_N_m"] - expected_inertia_per_m) / expected_inertia_per_m < REL

    def test_total_force_equals_drag_plus_inertia(self):
        """F_total_max = F_drag_max + F_inertia_max (conservative)."""
        r = morison_wave_current(1.2, 15.0, 1025.0, 1.0, 2.0, 0.3, 1.8, 0.5, 0.1)
        assert r["ok"] is True
        assert abs(r["F_total_max_N"] - (r["F_drag_max_N"] + r["F_inertia_max_N"])) < 1e-6

    def test_KC_formula(self):
        """KC = U_w × T_wave / D must match."""
        D, L, rho, Cd, Cm = 1.5, 10.0, 1025.0, 1.0, 2.0
        Uc, Uw, omega, k = 0.0, 2.0, 0.628, 0.1
        r = morison_wave_current(D, L, rho, Cd, Cm, Uc, Uw, omega, k)
        assert r["ok"] is True
        T_wave = 2.0 * math.pi / omega
        KC_expected = Uw * T_wave / D
        assert abs(r["KC"] - KC_expected) / KC_expected < REL

    def test_zero_current_still_works(self):
        r = morison_wave_current(1.0, 10.0, 1025.0, 1.0, 2.0, 0.0, 2.0, 0.5, 0.1)
        assert r["ok"] is True
        assert r["F_drag_max_N"] > 0

    def test_zero_wave_only_drag_from_current(self):
        """Zero wave (Uw=0) → inertia = 0, drag from current only."""
        D = 1.0
        L = 5.0
        Uc = 1.0
        r = morison_wave_current(D, L, 1025.0, 1.0, 2.0, Uc, 0.0, 0.5, 0.1)
        assert r["ok"] is True
        assert r["F_inertia_max_N"] == 0.0
        expected_drag = 0.5 * 1025.0 * 1.0 * D * Uc**2 * L
        assert abs(r["F_drag_max_N"] - expected_drag) / expected_drag < REL

    def test_negative_D_returns_error(self):
        r = morison_wave_current(-1.0, 10.0, 1025.0, 1.0, 2.0, 0.5, 1.0, 0.5, 0.1)
        assert r["ok"] is False

    def test_negative_Cd_returns_error(self):
        r = morison_wave_current(1.0, 10.0, 1025.0, -1.0, 2.0, 0.5, 1.0, 0.5, 0.1)
        assert r["ok"] is False


# ===========================================================================
# 6. mean_env_load
# ===========================================================================

class TestMeanEnvLoad:

    def test_wind_force_formula(self):
        """F_wind = ½ × rho_air × Cd_wind × A × V²"""
        A = 500.0
        Cd = 1.1
        rho_a = 1.225
        V = 25.0
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore")
            r = mean_env_load(A, Cd, rho_a, V,
                              hull_area_current=200.0, Cd_current=1.0,
                              rho_water=1025.0, V_current=0.0)
        assert r["ok"] is True
        expected = 0.5 * rho_a * Cd * A * V**2
        assert abs(r["F_wind_N"] - expected) / expected < REL

    def test_zero_wind_speed(self):
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore")
            r = mean_env_load(500.0, 1.0, 1.225, 0.0,
                              200.0, 1.0, 1025.0, 1.0)
        assert r["ok"] is True
        assert r["F_wind_N"] == 0.0

    def test_current_force_formula(self):
        """F_current = ½ × rho_water × Cd_current × A × V²"""
        A = 300.0
        Cd = 0.8
        rho_w = 1025.0
        Vc = 1.5
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore")
            r = mean_env_load(500.0, 1.0, 1.225, 0.0,
                              A, Cd, rho_w, Vc)
        assert r["ok"] is True
        expected = 0.5 * rho_w * Cd * A * Vc**2
        assert abs(r["F_current_N"] - expected) / expected < REL

    def test_total_force_is_sum(self):
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore")
            r = mean_env_load(400.0, 1.2, 1.225, 20.0,
                              250.0, 0.9, 1025.0, 1.2)
        assert r["ok"] is True
        assert abs(r["F_total_N"] - (r["F_wind_N"] + r["F_current_N"])) < 1e-6

    def test_negative_hull_area_wind_returns_error(self):
        r = mean_env_load(-1.0, 1.0, 1.225, 10.0, 200.0, 1.0, 1025.0, 1.0)
        assert r["ok"] is False


# ===========================================================================
# 7. watch_circle
# ===========================================================================

class TestWatchCircle:

    def _mock_system_result(self, offsets):
        return {
            "offsets_m": offsets,
            "restoring_force_N": [-x * 1e5 for x in offsets],
        }

    def test_no_exceedance_within_limit(self):
        sr = self._mock_system_result([0.0, 3.0, 5.0])
        r = watch_circle(sr, max_offset_fraction=0.05, water_depth=200.0)
        assert r["ok"] is True
        # max allowed = 10 m; all offsets <= 5 m
        assert r["offset_exceeded"] is False

    def test_exceedance_detected(self):
        sr = self._mock_system_result([0.0, 5.0, 15.0])
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore")
            r = watch_circle(sr, max_offset_fraction=0.05, water_depth=200.0)
        assert r["ok"] is True
        # max allowed = 10 m; 15 m exceeds
        assert r["offset_exceeded"] is True
        assert r["critical_offset_m"] == 15.0

    def test_max_offset_m_computed_correctly(self):
        sr = self._mock_system_result([0.0])
        r = watch_circle(sr, max_offset_fraction=0.05, water_depth=300.0)
        assert r["ok"] is True
        assert abs(r["max_offset_m"] - 15.0) < 1e-9

    def test_watch_circle_radius_equals_max_offset(self):
        sr = self._mock_system_result([0.0])
        r = watch_circle(sr, max_offset_fraction=0.05, water_depth=200.0)
        assert r["ok"] is True
        assert r["watch_circle_radius_m"] == r["max_offset_m"]

    def test_invalid_system_result_returns_error(self):
        r = watch_circle({"bad_key": []})
        assert r["ok"] is False

    def test_no_water_depth_gives_none_max_offset(self):
        sr = self._mock_system_result([0.0, 5.0])
        r = watch_circle(sr)
        assert r["ok"] is True
        assert r["max_offset_m"] is None
        assert r["offset_exceeded"] is False


# ===========================================================================
# 8. line_safety_factor
# ===========================================================================

class TestLineSafetyFactor:

    def test_sf_formula(self):
        """SF_actual = T_break / T_applied."""
        T_a, T_b = 500.0, 1000.0
        r = line_safety_factor(T_a, T_b)
        assert r["ok"] is True
        assert abs(r["SF_actual"] - T_b / T_a) < 1e-9

    def test_pass_sf_above_threshold(self):
        """SF_actual = 2.0 ≥ 1.67 → pass."""
        r = line_safety_factor(500.0, 1000.0, sf_required=1.67)
        assert r["ok"] is True
        assert r["pass_sf"] is True

    def test_fail_sf_below_threshold(self):
        """SF_actual = 1.5 < 1.67 → fail with warning."""
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore")
            r = line_safety_factor(667.0, 1000.0, sf_required=1.67)
        assert r["ok"] is True
        assert r["pass_sf"] is False
        assert len(r["warnings"]) > 0

    def test_utilisation_pct_formula(self):
        """utilisation_pct = T_applied / T_break × 100."""
        T_a, T_b = 600.0, 1000.0
        with _warnings_module.catch_warnings():
            _warnings_module.simplefilter("ignore")
            r = line_safety_factor(T_a, T_b)
        assert r["ok"] is True
        assert abs(r["utilisation_pct"] - 60.0) < 1e-9

    def test_damaged_condition_sf(self):
        """SF 1.25 for damaged condition (80% MBL utilisation)."""
        r = line_safety_factor(800.0, 1000.0, sf_required=1.25)
        assert r["ok"] is True
        assert r["pass_sf"] is True

    def test_zero_T_applied_returns_error(self):
        r = line_safety_factor(0.0, 1000.0)
        assert r["ok"] is False

    def test_negative_T_break_returns_error(self):
        r = line_safety_factor(100.0, -100.0)
        assert r["ok"] is False


# ===========================================================================
# 9. riser_top_tension
# ===========================================================================

class TestRiserTopTension:

    def test_vertical_riser_formula(self):
        """T_top = T_bottom + w × L for θ=0."""
        w_r, L_r, T_bot = 500.0, 1000.0, 200_000.0
        r = riser_top_tension(w_r, L_r, T_bot, theta_deg=0.0)
        assert r["ok"] is True
        expected = T_bot + w_r * L_r
        assert abs(r["T_top_N"] - expected) < 1e-6

    def test_inclined_riser_cos_theta(self):
        """T_top = T_bottom + w × L × cos(θ)."""
        w_r, L_r, T_bot, theta = 400.0, 800.0, 150_000.0, 10.0
        r = riser_top_tension(w_r, L_r, T_bot, theta_deg=theta)
        assert r["ok"] is True
        expected = T_bot + w_r * L_r * math.cos(math.radians(theta))
        assert abs(r["T_top_N"] - expected) / expected < REL

    def test_zero_inclination_H_top_zero(self):
        """Vertical riser: H_top = 0."""
        r = riser_top_tension(300.0, 500.0, 100_000.0, theta_deg=0.0)
        assert r["ok"] is True
        assert r["H_top_N"] < 1e-9

    def test_weight_component_returned(self):
        w_r, L_r = 600.0, 600.0
        r = riser_top_tension(w_r, L_r, 0.0)
        assert r["ok"] is True
        assert abs(r["weight_component_N"] - w_r * L_r) < 1e-9

    def test_theta_90_returns_error(self):
        r = riser_top_tension(300.0, 500.0, 0.0, theta_deg=90.0)
        assert r["ok"] is False

    def test_negative_w_r_returns_error(self):
        r = riser_top_tension(-100.0, 500.0, 0.0)
        assert r["ok"] is False

    def test_large_inclination_warns(self):
        """θ > 15° should emit a warning."""
        with _warnings_module.catch_warnings(record=True) as caught:
            _warnings_module.simplefilter("always")
            r = riser_top_tension(400.0, 600.0, 0.0, theta_deg=30.0)
        assert r["ok"] is True
        assert len(r["warnings"]) > 0


# ===========================================================================
# 10. LLM tool wrappers
# ===========================================================================

class TestTools:
    """Verify all LLM tool wrappers return ok=True on valid inputs and
    ok=False / error payload on invalid inputs."""

    # -- catenary line tool --

    def test_tool_catenary_line_ok(self):
        raw = _run(run_catenary_line(_ctx(), _args(w=300.0, L=500.0, H=150_000.0)))
        d = _ok_tool(raw)
        assert "T_fairlead_N" in d

    def test_tool_catenary_line_missing_H(self):
        raw = _run(run_catenary_line(_ctx(), _args(w=300.0, L=500.0)))
        _err_tool(raw)

    def test_tool_catenary_line_invalid_json(self):
        raw = _run(run_catenary_line(_ctx(), b"not-json"))
        _err_tool(raw)

    # -- multiseg tool --

    def test_tool_multiseg_ok(self):
        segs = [{"w": 400.0, "L": 300.0}, {"w": 150.0, "L": 400.0}]
        raw = _run(run_multiseg_catenary(_ctx(), _args(segments=segs, H=180_000.0)))
        _ok_tool(raw)

    def test_tool_multiseg_missing_H(self):
        raw = _run(run_multiseg_catenary(_ctx(), _args(segments=[{"w": 300.0, "L": 200.0}])))
        _err_tool(raw)

    # -- mooring system tool --

    def test_tool_mooring_system_ok(self):
        lines = [
            {"w": 300.0, "L": 800.0, "H0": 200_000.0, "azimuth_deg": 0.0},
            {"w": 300.0, "L": 800.0, "H0": 200_000.0, "azimuth_deg": 180.0},
        ]
        raw = _run(run_mooring_system(_ctx(), _args(
            lines=lines, water_depth=200.0,
            fairlead_radius=30.0, offsets=[0.0, 5.0],
        )))
        _ok_tool(raw)

    def test_tool_mooring_system_missing_offsets(self):
        lines = [{"w": 300.0, "L": 800.0, "H0": 200_000.0, "azimuth_deg": 0.0}]
        raw = _run(run_mooring_system(_ctx(), _args(
            lines=lines, water_depth=200.0, fairlead_radius=30.0
        )))
        _err_tool(raw)

    # -- anchor holding tool --

    def test_tool_anchor_drag_ok(self):
        raw = _run(run_anchor_holding(_ctx(), _args(
            anchor_type="drag_embedment", anchor_weight_kN=200.0, soil_type="soft_clay"
        )))
        _ok_tool(raw)

    def test_tool_anchor_pile_ok(self):
        raw = _run(run_anchor_holding(_ctx(), _args(
            anchor_type="pile", pile_diameter_m=1.5, pile_length_m=20.0, Su_kPa=100.0
        )))
        _ok_tool(raw)

    def test_tool_anchor_missing_type(self):
        raw = _run(run_anchor_holding(_ctx(), _args(anchor_weight_kN=100.0)))
        _err_tool(raw)

    # -- Morison force tool --

    def test_tool_morison_ok(self):
        raw = _run(run_morison_force(_ctx(), _args(
            D=1.0, L=10.0, rho=1025.0, Cd=1.0, Cm=2.0,
            U_c=0.5, U_w=2.0, omega=0.5, k=0.1,
        )))
        _ok_tool(raw)

    def test_tool_morison_missing_D(self):
        raw = _run(run_morison_force(_ctx(), _args(
            L=10.0, rho=1025.0, Cd=1.0, Cm=2.0,
            U_c=0.5, U_w=2.0, omega=0.5, k=0.1,
        )))
        _err_tool(raw)

    # -- mean env load tool --

    def test_tool_mean_env_ok(self):
        raw = _run(run_mean_env_load(_ctx(), _args(
            hull_area_wind=400.0, Cd_wind=1.1, rho_air=1.225, V_wind=20.0,
            hull_area_current=250.0, Cd_current=0.9, rho_water=1025.0, V_current=1.5,
        )))
        _ok_tool(raw)

    def test_tool_mean_env_missing_V_wind(self):
        raw = _run(run_mean_env_load(_ctx(), _args(
            hull_area_wind=400.0, Cd_wind=1.1, rho_air=1.225,
            hull_area_current=250.0, Cd_current=0.9, rho_water=1025.0, V_current=1.5,
        )))
        _err_tool(raw)

    # -- watch circle tool --

    def test_tool_watch_circle_ok(self):
        sr = {"offsets_m": [0.0, 5.0], "restoring_force_N": [0.0, -5e5]}
        raw = _run(run_watch_circle(_ctx(), _args(
            system_result=sr, water_depth=200.0, max_offset_fraction=0.05,
        )))
        _ok_tool(raw)

    def test_tool_watch_circle_missing_system_result(self):
        raw = _run(run_watch_circle(_ctx(), _args(water_depth=200.0)))
        _err_tool(raw)

    # -- line SF tool --

    def test_tool_line_sf_ok(self):
        raw = _run(run_line_sf(_ctx(), _args(T_applied_kN=500.0, T_break_kN=1000.0)))
        _ok_tool(raw)

    def test_tool_line_sf_missing_T_applied(self):
        raw = _run(run_line_sf(_ctx(), _args(T_break_kN=1000.0)))
        _err_tool(raw)

    # -- riser tool --

    def test_tool_riser_ok(self):
        raw = _run(run_riser_top_tension(_ctx(), _args(
            w_r=500.0, L_r=1000.0, T_bottom=200_000.0
        )))
        _ok_tool(raw)

    def test_tool_riser_missing_w_r(self):
        raw = _run(run_riser_top_tension(_ctx(), _args(L_r=1000.0, T_bottom=0.0)))
        _err_tool(raw)
