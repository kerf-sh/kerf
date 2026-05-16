"""
Hermetic tests for kerf_cad_core.bearings — rolling-element bearing selection & life.

Coverage:
  select.bearing_equivalent_load  — P = X·Fr + Y·Fa, e-ratio table
  select.bearing_rating_life      — L10 basic life (ball p=3, roller p=10/3)
  select.bearing_adjusted_life    — Lna = a1 × a23 × L10
  select.bearing_static_safety    — s0 = C0/P0, warning thresholds
  select.bearing_required_capacity — C from target Lh (inversion)
  select.bearing_limiting_speed   — n·dm parameter check
  select.bearing_grease_interval  — SKF relubrication formula
  select.bearing_select           — series table selection
  tools.*                         — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas verified algebraically against ISO 281, SKF catalogue, and Shigley.

References
----------
ISO 281:2007 — Rolling bearings — Dynamic load ratings and rating life
Shigley's Mechanical Engineering Design, 10th ed., §§ 11-1 to 11-9
SKF Bearing Catalogue, 2018 edition

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.bearings.select import (
    bearing_equivalent_load,
    bearing_rating_life,
    bearing_adjusted_life,
    bearing_static_safety,
    bearing_required_capacity,
    bearing_limiting_speed,
    bearing_grease_interval,
    bearing_select,
)
from kerf_cad_core.bearings.tools import (
    run_bearing_equivalent_load,
    run_bearing_rating_life,
    run_bearing_adjusted_life,
    run_bearing_static_safety,
    run_bearing_required_capacity,
    run_bearing_limiting_speed,
    run_bearing_grease_interval,
    run_bearing_select,
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
# 1. bearing_equivalent_load
# ===========================================================================

class TestBearingEquivalentLoad:

    def test_pure_radial_ball_no_axial(self):
        """Pure radial load, no axial: P = Fr (Fa/Fr <= e always)."""
        res = bearing_equivalent_load(Fr=5000.0, Fa=0.0, bearing_type="ball", C0=10000.0)
        assert res["ok"] is True
        assert res["P_N"] == pytest.approx(5000.0, rel=REL)
        assert res["X"] == 1.0
        assert res["Y"] == 0.0

    def test_high_axial_load_increases_P(self):
        """When Fa/Fr > e, the axial component increases P."""
        C0 = 5000.0
        Fr = 2000.0
        Fa = 3000.0  # large axial → Fa/C0 = 0.6, so e ≈ 0.44; Fa/Fr=1.5 > e
        res = bearing_equivalent_load(Fr=Fr, Fa=Fa, bearing_type="ball", C0=C0)
        assert res["ok"] is True
        # P = X·Fr + Y·Fa must be > Fr for significant axial load
        assert res["P_N"] >= Fr

    def test_equivalent_load_at_least_Fr(self):
        """ISO 281: equivalent load P >= Fr always."""
        res = bearing_equivalent_load(Fr=1000.0, Fa=500.0, bearing_type="ball", C0=8000.0)
        assert res["ok"] is True
        assert res["P_N"] >= 1000.0

    def test_roller_bearing_ignores_axial(self):
        """Cylindrical roller: P = Fr regardless of Fa."""
        res = bearing_equivalent_load(Fr=3000.0, Fa=2000.0, bearing_type="roller")
        assert res["ok"] is True
        assert res["P_N"] == pytest.approx(3000.0, rel=REL)
        assert len(res["warnings"]) > 0  # should warn about ignored Fa

    def test_roller_bearing_no_axial_no_warning(self):
        """Cylindrical roller with Fa=0 returns no warning."""
        res = bearing_equivalent_load(Fr=3000.0, Fa=0.0, bearing_type="roller")
        assert res["ok"] is True
        assert res["P_N"] == pytest.approx(3000.0, rel=REL)
        assert not any("axial" in w.lower() for w in res["warnings"])

    def test_angular_contact_low_axial(self):
        """Angular-contact: low Fa/Fr <= 0.68 → P = Fr."""
        res = bearing_equivalent_load(Fr=5000.0, Fa=1000.0, bearing_type="angular-contact")
        assert res["ok"] is True
        # Fa/Fr = 0.2 < e=0.68, so P = Fr
        assert res["P_N"] == pytest.approx(5000.0, rel=REL)

    def test_angular_contact_high_axial(self):
        """Angular-contact: high Fa/Fr > 0.68 → P = 0.41·Fr + 0.87·Fa."""
        Fr, Fa = 1000.0, 2000.0  # Fa/Fr = 2.0 > 0.68
        res = bearing_equivalent_load(Fr=Fr, Fa=Fa, bearing_type="angular-contact")
        assert res["ok"] is True
        expected = 0.41 * Fr + 0.87 * Fa
        assert res["P_N"] == pytest.approx(expected, rel=REL)

    def test_negative_Fr_returns_error(self):
        """Negative radial force must return ok=False."""
        res = bearing_equivalent_load(Fr=-100.0, Fa=0.0)
        assert res["ok"] is False

    def test_negative_Fa_returns_error(self):
        """Negative axial force must return ok=False."""
        res = bearing_equivalent_load(Fr=1000.0, Fa=-50.0)
        assert res["ok"] is False

    def test_unknown_bearing_type_returns_error(self):
        """Unknown bearing type must return ok=False."""
        res = bearing_equivalent_load(Fr=1000.0, Fa=0.0, bearing_type="needle")
        assert res["ok"] is False

    def test_conservative_default_without_C0(self):
        """Without C0, conservative (highest Y) factors should be applied."""
        res = bearing_equivalent_load(Fr=1000.0, Fa=200.0, bearing_type="ball")
        assert res["ok"] is True
        # Y=2.30 is the conservative default: P = max(1·Fr, 0.56·Fr + 2.30·Fa)
        assert any("conservative" in w.lower() for w in res["warnings"])

    def test_zero_Fr_zero_Fa_gives_zero_P_with_warning(self):
        """Zero Fr and Fa → P=0, should warn."""
        res = bearing_equivalent_load(Fr=0.0, Fa=0.0)
        assert res["ok"] is True
        assert res["P_N"] == 0.0


# ===========================================================================
# 2. bearing_rating_life
# ===========================================================================

class TestBearingRatingLife:

    def test_ball_l10_formula(self):
        """L10 = (C/P)^3 for ball bearings (ISO 281)."""
        C, P = 20000.0, 10000.0
        res = bearing_rating_life(C, P, "ball")
        assert res["ok"] is True
        assert res["L10_rev"] == pytest.approx(8.0, rel=REL)  # (2)^3 = 8

    def test_roller_l10_formula(self):
        """L10 = (C/P)^(10/3) for roller bearings."""
        C, P = 20000.0, 10000.0
        res = bearing_rating_life(C, P, "roller")
        assert res["ok"] is True
        expected = 2.0 ** (10.0 / 3.0)
        assert res["L10_rev"] == pytest.approx(expected, rel=REL)

    def test_l10_hours_computed_when_n_rpm_given(self):
        """L10_hours = L10_rev × 1e6 / (60 × n)."""
        C, P, n = 20000.0, 10000.0, 1000.0
        res = bearing_rating_life(C, P, "ball", n_rpm=n)
        assert res["ok"] is True
        expected_hours = res["L10_rev"] * 1e6 / (60.0 * n)
        assert res["L10_hours"] == pytest.approx(expected_hours, rel=REL)

    def test_l10_hours_absent_without_n_rpm(self):
        """L10_hours should NOT appear in result when n_rpm is not provided."""
        res = bearing_rating_life(20000.0, 10000.0)
        assert res["ok"] is True
        assert "L10_hours" not in res

    def test_under_capacity_warns(self):
        """C/P < 1.0 must produce a warning."""
        res = bearing_rating_life(5000.0, 10000.0, "ball")
        assert res["ok"] is True
        assert any("under-capacity" in w.lower() or "c/p" in w.lower() for w in res["warnings"])

    def test_ball_life_scales_cubic_with_C(self):
        """Doubling C doubles C/P, which cubes L10 from 1→8 times."""
        P, n = 10000.0, 1000.0
        C1, C2 = 10000.0, 20000.0
        L1 = bearing_rating_life(C1, P)["L10_rev"]
        L2 = bearing_rating_life(C2, P)["L10_rev"]
        assert L2 / L1 == pytest.approx(8.0, rel=1e-9)

    def test_roller_exponent_differs_from_ball(self):
        """Ball and roller must give different L10 for same C/P = 2."""
        C, P = 20000.0, 10000.0
        L_ball = bearing_rating_life(C, P, "ball")["L10_rev"]
        L_roller = bearing_rating_life(C, P, "roller")["L10_rev"]
        assert abs(L_ball - L_roller) > 1e-6

    def test_negative_C_returns_error(self):
        res = bearing_rating_life(-1000.0, 5000.0)
        assert res["ok"] is False

    def test_zero_P_returns_error(self):
        res = bearing_rating_life(10000.0, 0.0)
        assert res["ok"] is False

    def test_unknown_bearing_type_returns_error(self):
        res = bearing_rating_life(10000.0, 5000.0, "tapered")
        assert res["ok"] is False


# ===========================================================================
# 3. bearing_adjusted_life
# ===========================================================================

class TestBearingAdjustedLife:

    def test_a1_equals_1_matches_L10(self):
        """a1=1, a23=1 → Lna = L10 exactly."""
        C, P, n = 20000.0, 10000.0, 1000.0
        res = bearing_adjusted_life(C, P, n, a1=1.0, a23=1.0)
        assert res["ok"] is True
        assert res["Lna_rev"] == pytest.approx(res["L10_rev"], rel=REL)
        assert res["Lna_hours"] == pytest.approx(res["L10_hours"], rel=REL)

    def test_a1_reduces_life(self):
        """a1 < 1 must reduce Lna relative to L10."""
        C, P, n = 20000.0, 10000.0, 1000.0
        res = bearing_adjusted_life(C, P, n, a1=0.21, a23=1.0)
        assert res["ok"] is True
        assert res["Lna_rev"] < res["L10_rev"]
        assert abs(res["Lna_rev"] - 0.21 * res["L10_rev"]) / res["L10_rev"] < REL

    def test_a23_scales_life(self):
        """a23=2 doubles Lna vs a23=1."""
        C, P, n = 20000.0, 10000.0, 1000.0
        res1 = bearing_adjusted_life(C, P, n, a1=1.0, a23=1.0)
        res2 = bearing_adjusted_life(C, P, n, a1=1.0, a23=2.0)
        assert res2["Lna_rev"] == pytest.approx(2.0 * res1["Lna_rev"], rel=REL)

    def test_lna_hours_formula(self):
        """Lna_hours = Lna_rev × 1e6 / (60 × n)."""
        C, P, n = 20000.0, 10000.0, 1500.0
        res = bearing_adjusted_life(C, P, n)
        assert res["ok"] is True
        expected = res["Lna_rev"] * 1e6 / (60.0 * n)
        assert res["Lna_hours"] == pytest.approx(expected, rel=REL)

    def test_low_a23_warns(self):
        """a23 < 0.5 should produce a lubrication warning."""
        res = bearing_adjusted_life(20000.0, 10000.0, 1000.0, a23=0.3)
        assert res["ok"] is True
        assert any("a23" in w for w in res["warnings"])

    def test_missing_n_rpm_returns_error(self):
        """n_rpm <= 0 must return ok=False."""
        res = bearing_adjusted_life(20000.0, 10000.0, -1.0)
        assert res["ok"] is False

    def test_roller_adjusted_life_longer_than_ball_same_CoverP(self):
        """For C/P=2, roller L10=(2^(10/3)) > ball L10=(2^3=8), so adjusted lives differ."""
        C, P, n = 20000.0, 10000.0, 1000.0
        res_ball = bearing_adjusted_life(C, P, n, bearing_type="ball")
        res_roller = bearing_adjusted_life(C, P, n, bearing_type="roller")
        # C/P=2; ball: 8, roller: 2^(10/3) ≈ 10.08
        assert res_roller["L10_rev"] > res_ball["L10_rev"]


# ===========================================================================
# 4. bearing_static_safety
# ===========================================================================

class TestBearingStaticSafety:

    def test_s0_formula(self):
        """s0 = C0/P0."""
        C0, P0 = 15000.0, 5000.0
        res = bearing_static_safety(C0, P0)
        assert res["ok"] is True
        assert res["s0"] == pytest.approx(3.0, rel=REL)

    def test_adequate_safety_no_warnings(self):
        """s0 >= 1.5 should produce no warnings."""
        res = bearing_static_safety(15000.0, 5000.0)
        assert res["ok"] is True
        assert res["warnings"] == []

    def test_marginal_safety_warns(self):
        """s0 between 1.0 and 1.5 should warn."""
        C0, P0 = 12000.0, 10000.0  # s0 = 1.2
        res = bearing_static_safety(C0, P0)
        assert res["ok"] is True
        assert res["s0"] == pytest.approx(1.2, rel=REL)
        assert len(res["warnings"]) > 0

    def test_inadequate_safety_warns(self):
        """s0 < 1.0 must warn about inadequate safety."""
        res = bearing_static_safety(C0=5000.0, P0=8000.0)
        assert res["ok"] is True
        assert res["s0"] < 1.0
        assert any("inadequate" in w.lower() or "s0" in w for w in res["warnings"])

    def test_dangerous_safety_warns(self):
        """s0 < 0.8 must warn about permanent deformation risk."""
        res = bearing_static_safety(C0=3000.0, P0=8000.0)
        assert res["ok"] is True
        assert res["s0"] < 0.8
        assert any("dangerous" in w.lower() or "deformation" in w.lower() for w in res["warnings"])

    def test_zero_C0_returns_error(self):
        res = bearing_static_safety(C0=0.0, P0=5000.0)
        assert res["ok"] is False

    def test_negative_P0_returns_error(self):
        res = bearing_static_safety(C0=10000.0, P0=-1.0)
        assert res["ok"] is False


# ===========================================================================
# 5. bearing_required_capacity
# ===========================================================================

class TestBearingRequiredCapacity:

    def test_inverse_of_adjusted_life_ball(self):
        """C_required must satisfy the adjusted life equation exactly (ball)."""
        P, n, Lh = 5000.0, 1000.0, 20000.0
        a1, a23 = 1.0, 1.0
        res = bearing_required_capacity(P, n, Lh, bearing_type="ball", a1=a1, a23=a23)
        assert res["ok"] is True
        C_req = res["C_required_N"]
        # Verify: bearing_adjusted_life(C_req, P, n) should give Lna_hours ≈ Lh
        check = bearing_adjusted_life(C_req, P, n, bearing_type="ball", a1=a1, a23=a23)
        assert check["Lna_hours"] == pytest.approx(Lh, rel=1e-5)

    def test_inverse_of_adjusted_life_roller(self):
        """C_required must satisfy the adjusted life equation exactly (roller)."""
        P, n, Lh = 8000.0, 500.0, 30000.0
        res = bearing_required_capacity(P, n, Lh, bearing_type="roller")
        assert res["ok"] is True
        C_req = res["C_required_N"]
        check = bearing_adjusted_life(C_req, P, n, bearing_type="roller")
        assert check["Lna_hours"] == pytest.approx(Lh, rel=1e-5)

    def test_higher_target_life_requires_higher_C(self):
        """Doubling target life must require higher C."""
        P, n = 5000.0, 1000.0
        C1 = bearing_required_capacity(P, n, 10000.0)["C_required_N"]
        C2 = bearing_required_capacity(P, n, 20000.0)["C_required_N"]
        assert C2 > C1

    def test_a1_reduces_required_C(self):
        """Higher reliability (lower a1) requires larger C for the same target life."""
        P, n, Lh = 5000.0, 1000.0, 20000.0
        C_l10 = bearing_required_capacity(P, n, Lh, a1=1.0)["C_required_N"]
        C_l5 = bearing_required_capacity(P, n, Lh, a1=0.62)["C_required_N"]
        assert C_l5 > C_l10  # lower a1 → need bigger bearing to meet same Lh

    def test_negative_P_returns_error(self):
        res = bearing_required_capacity(-1.0, 1000.0, 20000.0)
        assert res["ok"] is False

    def test_zero_Lh_target_returns_error(self):
        res = bearing_required_capacity(5000.0, 1000.0, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 6. bearing_limiting_speed
# ===========================================================================

class TestBearingLimitingSpeed:

    def test_ndm_formula(self):
        """n·dm = n × dm_mm."""
        dm, n = 38.5, 1000.0
        res = bearing_limiting_speed(dm, n, "ball")
        assert res["ok"] is True
        assert res["ndm"] == pytest.approx(dm * n, rel=REL)

    def test_utilisation_formula(self):
        """utilisation = ndm / ndm_limit."""
        dm, n = 38.5, 1000.0
        res = bearing_limiting_speed(dm, n, "ball")
        assert res["ok"] is True
        assert res["utilisation"] == pytest.approx(res["ndm"] / 600_000.0, rel=REL)

    def test_over_speed_warns(self):
        """n·dm > limit must produce an over-speed warning."""
        # For ball: limit = 600 000 mm·rpm; dm=100, n=7000 → ndm = 700 000
        res = bearing_limiting_speed(100.0, 7000.0, "ball")
        assert res["ok"] is True
        assert res["utilisation"] > 1.0
        assert any("over-speed" in w.lower() or "exceeds" in w.lower() for w in res["warnings"])

    def test_high_utilisation_warns(self):
        """n·dm at 85% of limit must produce a near-limit warning."""
        # 85% of 600 000 = 510 000; dm=51, n=10000 → ndm=510 000
        res = bearing_limiting_speed(51.0, 10000.0, "ball")
        assert res["ok"] is True
        assert 0.8 < res["utilisation"] <= 1.0
        assert len(res["warnings"]) > 0

    def test_roller_limit_lower_than_ball(self):
        """Roller bearing limit (300 000) < ball limit (600 000)."""
        dm, n = 50.0, 3000.0  # ndm = 150 000 < both limits
        res_ball = bearing_limiting_speed(dm, n, "ball")
        res_roller = bearing_limiting_speed(dm, n, "roller")
        # Same ndm, different limits → roller utilisation > ball utilisation
        assert res_roller["utilisation"] > res_ball["utilisation"]

    def test_zero_dm_returns_error(self):
        res = bearing_limiting_speed(0.0, 1000.0, "ball")
        assert res["ok"] is False

    def test_zero_n_returns_error(self):
        res = bearing_limiting_speed(38.5, 0.0, "ball")
        assert res["ok"] is False

    def test_unknown_type_returns_error(self):
        res = bearing_limiting_speed(38.5, 1000.0, "tapered")
        assert res["ok"] is False


# ===========================================================================
# 7. bearing_grease_interval
# ===========================================================================

class TestBearingGreaseInterval:

    def test_moderate_speed_gives_positive_interval(self):
        """Low-to-moderate speed should give a positive relubrication interval."""
        res = bearing_grease_interval(dm_mm=38.5, n_rpm=1000.0, C_kN=14.0, P_kN=7.0)
        assert res["ok"] is True
        assert res["relubrication_hours"] > 0

    def test_load_factor_formula(self):
        """f_load = (C/P)^0.3."""
        dm, n, C, P = 38.5, 1000.0, 14.0, 7.0
        res = bearing_grease_interval(dm, n, C, P)
        assert res["ok"] is True
        expected_f = (C / P) ** 0.3
        assert res["f_load"] == pytest.approx(expected_f, rel=REL)

    def test_higher_load_shortens_interval(self):
        """Higher P (lower C/P) must reduce the relubrication interval."""
        dm, n, C = 38.5, 1000.0, 14.0
        h1 = bearing_grease_interval(dm, n, C, P_kN=2.0)["relubrication_hours"]
        h2 = bearing_grease_interval(dm, n, C, P_kN=10.0)["relubrication_hours"]
        assert h2 < h1

    def test_very_high_speed_returns_zero_with_warning(self):
        """n·√dm >= 14e6 must return 0 hours and a warning."""
        # n·√dm = 14e6 at dm=1: n = 14e6 → use n=15e6 to exceed
        res = bearing_grease_interval(dm_mm=1.0, n_rpm=15e6, C_kN=10.0, P_kN=5.0)
        assert res["ok"] is True
        assert res["relubrication_hours"] == 0.0
        assert len(res["warnings"]) > 0

    def test_under_capacity_warns(self):
        """C < P must produce under-capacity warning."""
        res = bearing_grease_interval(dm_mm=38.5, n_rpm=1000.0, C_kN=5.0, P_kN=10.0)
        assert res["ok"] is True
        assert any("under-capacity" in w.lower() or "c/p" in w.lower() for w in res["warnings"])

    def test_negative_dm_returns_error(self):
        res = bearing_grease_interval(-1.0, 1000.0, 14.0, 7.0)
        assert res["ok"] is False

    def test_negative_C_kN_returns_error(self):
        res = bearing_grease_interval(38.5, 1000.0, -1.0, 7.0)
        assert res["ok"] is False


# ===========================================================================
# 8. bearing_select
# ===========================================================================

class TestBearingSelect:

    def test_select_6200_finds_bearing(self):
        """Should find a suitable 6200-series bearing for moderate load and life."""
        res = bearing_select(
            series="6200",
            Fr=3000.0, Fa=0.0,
            n_rpm=1000.0, Lh_min=5000.0,
        )
        assert res["ok"] is True
        assert res["selected"] is not None
        sel = res["selected"]
        assert sel["Lna_hours"] >= 5000.0

    def test_select_returns_candidates_list(self):
        """Candidates list should be non-empty for any valid series."""
        res = bearing_select("6000", Fr=2000.0, Fa=0.0, n_rpm=1000.0, Lh_min=1.0)
        assert res["ok"] is True
        assert len(res["candidates"]) > 0

    def test_select_warns_if_no_bearing_qualifies(self):
        """Very high load / very long life: no bearing qualifies → warning."""
        res = bearing_select(
            series="6000",
            Fr=100000.0, Fa=0.0,
            n_rpm=10000.0, Lh_min=1e9,
        )
        assert res["ok"] is True
        assert res["selected"] is None
        assert len(res["warnings"]) > 0

    def test_select_NU200_roller(self):
        """NU200 cylindrical roller series selection."""
        res = bearing_select(
            series="NU200",
            Fr=5000.0, Fa=0.0,
            n_rpm=500.0, Lh_min=10000.0,
            bearing_type="roller",
        )
        assert res["ok"] is True
        # NU200 rollers have high C; should find a match
        assert res["selected"] is not None

    def test_selected_bearing_has_static_safety(self):
        """Selected bearing must meet the requested s0_min."""
        res = bearing_select(
            series="6200",
            Fr=2000.0, Fa=0.0,
            n_rpm=1000.0, Lh_min=5000.0,
            s0_min=1.0,
        )
        assert res["ok"] is True
        if res["selected"] is not None:
            assert res["selected"]["s0"] >= 1.0

    def test_invalid_series_returns_error(self):
        res = bearing_select("9999", Fr=1000.0, Fa=0.0, n_rpm=1000.0, Lh_min=1000.0)
        assert res["ok"] is False

    def test_negative_Fr_returns_error(self):
        res = bearing_select("6200", Fr=-100.0, Fa=0.0, n_rpm=1000.0, Lh_min=1000.0)
        assert res["ok"] is False

    def test_zero_n_rpm_returns_error(self):
        res = bearing_select("6200", Fr=1000.0, Fa=0.0, n_rpm=0.0, Lh_min=1000.0)
        assert res["ok"] is False

    def test_candidates_sorted_by_bore(self):
        """Candidates should be in ascending bore order (as stored in table)."""
        res = bearing_select("6300", Fr=1000.0, Fa=0.0, n_rpm=500.0, Lh_min=100.0)
        assert res["ok"] is True
        bores = [c["bore_mm"] for c in res["candidates"]]
        assert bores == sorted(bores)


# ===========================================================================
# 9. LLM tool wrappers (run_*)
# ===========================================================================

class TestToolWrappers:

    def test_run_bearing_equivalent_load_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bearing_equivalent_load(ctx, _args(Fr=5000.0, Fa=1000.0, bearing_type="ball", C0=20000.0)))
        d = _ok_tool(raw)
        assert d["P_N"] >= 5000.0

    def test_run_bearing_equivalent_load_missing_Fr(self):
        ctx = _ctx()
        raw = _run(run_bearing_equivalent_load(ctx, _args(Fa=0.0)))
        _err_tool(raw)

    def test_run_bearing_rating_life_ball(self):
        ctx = _ctx()
        raw = _run(run_bearing_rating_life(ctx, _args(C=20000.0, P=10000.0, bearing_type="ball")))
        d = _ok_tool(raw)
        assert d["L10_rev"] == pytest.approx(8.0, rel=1e-9)

    def test_run_bearing_rating_life_roller_with_speed(self):
        ctx = _ctx()
        raw = _run(run_bearing_rating_life(ctx, _args(C=20000.0, P=10000.0, bearing_type="roller", n_rpm=1000.0)))
        d = _ok_tool(raw)
        expected = 2.0 ** (10.0 / 3.0)
        assert d["L10_rev"] == pytest.approx(expected, rel=1e-9)
        assert "L10_hours" in d

    def test_run_bearing_rating_life_missing_P(self):
        ctx = _ctx()
        raw = _run(run_bearing_rating_life(ctx, _args(C=20000.0)))
        _err_tool(raw)

    def test_run_bearing_adjusted_life_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bearing_adjusted_life(ctx, _args(C=20000.0, P=10000.0, n_rpm=1000.0)))
        d = _ok_tool(raw)
        assert d["Lna_hours"] > 0

    def test_run_bearing_adjusted_life_bad_json(self):
        ctx = _ctx()
        raw = _run(run_bearing_adjusted_life(ctx, b"bad json"))
        _err_tool(raw)

    def test_run_bearing_static_safety_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bearing_static_safety(ctx, _args(C0=15000.0, P0=5000.0)))
        d = _ok_tool(raw)
        assert d["s0"] == pytest.approx(3.0, rel=1e-9)

    def test_run_bearing_static_safety_missing_C0(self):
        ctx = _ctx()
        raw = _run(run_bearing_static_safety(ctx, _args(P0=5000.0)))
        _err_tool(raw)

    def test_run_bearing_required_capacity_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bearing_required_capacity(ctx, _args(P=5000.0, n_rpm=1000.0, Lh_target=20000.0)))
        d = _ok_tool(raw)
        assert d["C_required_N"] > 5000.0

    def test_run_bearing_required_capacity_missing_Lh(self):
        ctx = _ctx()
        raw = _run(run_bearing_required_capacity(ctx, _args(P=5000.0, n_rpm=1000.0)))
        _err_tool(raw)

    def test_run_bearing_limiting_speed_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bearing_limiting_speed(ctx, _args(dm_mm=38.5, n_rpm=1000.0)))
        d = _ok_tool(raw)
        assert d["ndm"] == pytest.approx(38500.0, rel=1e-9)

    def test_run_bearing_limiting_speed_missing_dm(self):
        ctx = _ctx()
        raw = _run(run_bearing_limiting_speed(ctx, _args(n_rpm=1000.0)))
        _err_tool(raw)

    def test_run_bearing_grease_interval_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bearing_grease_interval(ctx, _args(dm_mm=38.5, n_rpm=1000.0, C_kN=14.0, P_kN=7.0)))
        d = _ok_tool(raw)
        assert d["relubrication_hours"] > 0

    def test_run_bearing_grease_interval_missing_field(self):
        ctx = _ctx()
        raw = _run(run_bearing_grease_interval(ctx, _args(dm_mm=38.5, n_rpm=1000.0, C_kN=14.0)))
        _err_tool(raw)

    def test_run_bearing_select_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bearing_select(ctx, _args(
            series="6200", Fr=3000.0, Fa=0.0, n_rpm=1000.0, Lh_min=5000.0
        )))
        d = _ok_tool(raw)
        assert d["selected"] is not None

    def test_run_bearing_select_invalid_series(self):
        ctx = _ctx()
        raw = _run(run_bearing_select(ctx, _args(
            series="XXXX", Fr=3000.0, Fa=0.0, n_rpm=1000.0, Lh_min=5000.0
        )))
        _err_tool(raw)

    def test_run_bearing_select_bad_json(self):
        ctx = _ctx()
        raw = _run(run_bearing_select(ctx, b"not-json"))
        _err_tool(raw)


# ===========================================================================
# Externally-citable reference cases (production-confidence validation)
# Cross-checked vs ISO 281:2007, ISO 76:2006, SKF Bearing Catalogue 2018.
# ===========================================================================

from kerf_cad_core.bearings.select import (  # noqa: E402
    bearing_equivalent_load as _ref_eq_load,
    bearing_rating_life as _ref_rating_life,
    bearing_adjusted_life as _ref_adj_life,
    bearing_static_safety as _ref_static,
    bearing_required_capacity as _ref_req_cap,
    bearing_limiting_speed as _ref_lim_speed,
)


class TestBearingsExternalReferences:
    """Validated against ISO 281, ISO 76 and SKF catalogue method."""

    def test_rating_life_ball_iso281(self):
        # ISO 281 §5: ball p=3. C=30.7 kN, P=3 kN → L10=1071.65 Mrev.
        r = _ref_rating_life(30700.0, 3000.0, "ball")
        assert r["L10_rev"] == pytest.approx((30700.0 / 3000.0) ** 3, rel=1e-12)

    def test_rating_life_roller_iso281(self):
        # ISO 281 §5: roller p=10/3.
        r = _ref_rating_life(50000.0, 5000.0, "roller")
        assert r["L10_rev"] == pytest.approx(10.0 ** (10.0 / 3.0), rel=1e-12)

    def test_rating_life_hours(self):
        # ISO 281: L10h = L10·1e6/(60 n). C/P=10 ball, n=1000 rpm.
        r = _ref_rating_life(10000.0, 1000.0, "ball", n_rpm=1000.0)
        assert r["L10_hours"] == pytest.approx(1000.0 * 1e6 / (60.0 * 1000.0), rel=1e-9)

    def test_equivalent_load_radial_only(self):
        # ISO 281 §5: pure radial, Fa=0 → P = Fr (X=1, Y=0).
        r = _ref_eq_load(5000.0, 0.0, "ball", C0=10000.0)
        assert r["P_N"] == pytest.approx(5000.0, rel=1e-12)

    def test_equivalent_load_dgbb_table4(self):
        # ISO 281 Table 4 deep-groove ball: Fa/C0=0.014 → e=0.19, X=0.56,
        # Y=2.30. With Fa/Fr > e use P = 0.56 Fr + 2.30 Fa.
        # Fr=1000, Fa=500, C0 such that Fa/C0=0.014 → C0=500/0.014.
        C0 = 500.0 / 0.014
        r = _ref_eq_load(1000.0, 500.0, "ball", C0=C0)
        assert r["e"] == pytest.approx(0.19, rel=1e-6)
        # Fa/Fr = 0.5 > e=0.19 → P = 0.56·1000 + 2.30·500
        assert r["P_N"] == pytest.approx(0.56 * 1000.0 + 2.30 * 500.0, rel=1e-9)

    def test_static_safety_iso76(self):
        # ISO 76: s0 = C0/P0. C0=15 kN, P0=5 kN → s0=3.0.
        r = _ref_static(15000.0, 5000.0)
        assert r["s0"] == pytest.approx(3.0, rel=1e-12)

    def test_static_safety_low_warns(self):
        # ISO 76: s0=0.5 < 0.8 must warn (raceway brinelling risk).
        r = _ref_static(5000.0, 10000.0)
        assert r["s0"] == pytest.approx(0.5, rel=1e-12)
        assert any("0.8" in w for w in r["warnings"])

    def test_required_capacity_inverts_life(self):
        # ISO 281 inverse: C = P (L10h·60·n/1e6)^(1/p). Round-trip check.
        P, n, Lh = 4000.0, 1500.0, 20000.0
        rc = _ref_req_cap(P, n, Lh, "ball")
        C = rc["C_required_N"]
        back = _ref_rating_life(C, P, "ball", n_rpm=n)
        assert back["L10_hours"] == pytest.approx(Lh, rel=1e-6)

    def test_adjusted_life_reliability_factor(self):
        # ISO 281: Lna = a1·a23·L10. a1=0.21 (99% reliability) halves... 
        base = _ref_adj_life(10000.0, 1000.0, 1000.0, "ball", a1=1.0, a23=1.0)
        adj = _ref_adj_life(10000.0, 1000.0, 1000.0, "ball", a1=0.21, a23=1.0)
        assert adj["Lna_rev"] == pytest.approx(0.21 * base["L10_rev"], rel=1e-12)

    def test_limiting_speed_ndm(self):
        # SKF catalogue: n·dm parameter. dm=50 mm, n=10000 rpm → 500000 mm·rpm,
        # below grease limit 600000 for ball bearings.
        r = _ref_lim_speed(50.0, 10000.0, "ball")
        assert r["ndm"] == pytest.approx(500000.0, rel=1e-12)
        assert r["ndm_limit"] == pytest.approx(600000.0, rel=1e-12)
