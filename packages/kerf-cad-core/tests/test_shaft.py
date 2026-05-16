"""
Hermetic tests for kerf_cad_core.shaft — shaft & bearing sizing calculators.

Coverage:
  calc.shaft_diameter  — DE-Goodman and max-shear methods
  calc.shaft_critical_speed — simply-supported and fixed-fixed
  calc.bearing_l10     — ball (p=3) and roller (p=10/3)
  calc.key_size        — table lookup, shear / bearing stress checks
  tools.*              — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas are verified algebraically against published expressions.

References
----------
ASME B106.1M-1985 — Design of Transmission Shafting
ISO 281:2007 — Rolling bearings — Dynamic load ratings and rating life
Shigley's Mechanical Engineering Design, 10th ed.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.shaft.calc import (
    shaft_diameter,
    shaft_critical_speed,
    bearing_l10,
    key_size,
)
from kerf_cad_core.shaft.tools import (
    run_shaft_diameter,
    run_shaft_critical_speed,
    run_bearing_l10,
    run_key_size,
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
    except Exception:  # pragma: no cover — kerf_core not installed
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


REL = 1e-6  # relative tolerance for floating-point checks


# ===========================================================================
# 1. shaft_diameter — DE-Goodman
# ===========================================================================

class TestShaftDiameterDEGoodman:

    def test_pure_torsion_matches_tau_formula(self):
        """Pure torsion (M=0): d must satisfy τ = 16T / (π d³).

        From DE-Goodman with M=0:
            d³ = (32/πSe) × √(¾) × T   (Kf=Kfs=1, sf=1)
            d³ = (32/πSe) × (√3/2) × T

        The max-shear formula with M=0:
            d³ = (32/πSe) × T

        Use max-shear to verify τ = 16T/(πd³) matches τ_allow = Se/2.
        """
        T = 200.0       # N·m
        Se = 300e6      # Pa allowable
        res = shaft_diameter(M=0.0, T=T, sigma_allow=Se, method="max-shear")
        assert res["ok"] is True
        d = res["diameter_m"]
        # Back-calculate τ from d
        tau_actual = 16.0 * T / (math.pi * d ** 3)
        tau_allow = Se / 2.0
        assert abs(tau_actual - tau_allow) / tau_allow < REL

    def test_combined_load_larger_than_torsion_only(self):
        """Adding bending moment must increase required diameter."""
        T = 150.0
        Se = 200e6
        d_torsion = shaft_diameter(M=0.0, T=T, sigma_allow=Se)["diameter_m"]
        d_combined = shaft_diameter(M=100.0, T=T, sigma_allow=Se)["diameter_m"]
        assert d_combined > d_torsion

    def test_combined_load_larger_than_bending_only(self):
        """Adding torque must increase required diameter over bending-only."""
        M = 200.0
        Se = 250e6
        d_bending = shaft_diameter(M=M, T=0.0, sigma_allow=Se)["diameter_m"]
        d_combined = shaft_diameter(M=M, T=300.0, sigma_allow=Se)["diameter_m"]
        assert d_combined > d_bending

    def test_zero_loads_returns_zero_diameter(self):
        """M=T=0 → diameter=0 (degenerate but valid)."""
        res = shaft_diameter(M=0.0, T=0.0, sigma_allow=100e6)
        assert res["ok"] is True
        assert res["diameter_m"] == 0.0

    def test_safety_factor_scales_diameter(self):
        """Doubling safety_factor must increase diameter by 2^(1/3)."""
        M, T, Se = 100.0, 200.0, 300e6
        d1 = shaft_diameter(M=M, T=T, sigma_allow=Se, safety_factor=1.0)["diameter_m"]
        d2 = shaft_diameter(M=M, T=T, sigma_allow=Se, safety_factor=2.0)["diameter_m"]
        ratio = d2 / d1
        assert abs(ratio - 2.0 ** (1.0 / 3.0)) < 1e-9

    def test_stress_concentration_increases_diameter(self):
        """Kf > 1 must increase required diameter."""
        M, T, Se = 100.0, 150.0, 200e6
        d_no_notch = shaft_diameter(M=M, T=T, sigma_allow=Se, Kf=1.0, Kfs=1.0)["diameter_m"]
        d_notch = shaft_diameter(M=M, T=T, sigma_allow=Se, Kf=2.0, Kfs=1.5)["diameter_m"]
        assert d_notch > d_no_notch

    def test_degoodman_algebraic_check(self):
        """Verify DE-Goodman formula algebraically for known inputs."""
        M, T, Se = 100.0, 200.0, 400e6
        # d³ = (32/πSe) × √(M² + 0.75T²)
        rhs = (32.0 / (math.pi * Se)) * math.sqrt(M ** 2 + 0.75 * T ** 2)
        d_expected = rhs ** (1.0 / 3.0)
        res = shaft_diameter(M=M, T=T, sigma_allow=Se, method="DE-Goodman")
        assert res["ok"] is True
        assert abs(res["diameter_m"] - d_expected) / d_expected < REL

    def test_negative_M_returns_error(self):
        """Negative bending moment must return ok=False."""
        res = shaft_diameter(M=-10.0, T=100.0, sigma_allow=200e6)
        assert res["ok"] is False
        assert "reason" in res

    def test_negative_T_returns_error(self):
        """Negative torque must return ok=False."""
        res = shaft_diameter(M=100.0, T=-5.0, sigma_allow=200e6)
        assert res["ok"] is False

    def test_negative_sigma_allow_returns_error(self):
        """Non-positive allowable stress must return ok=False."""
        res = shaft_diameter(M=100.0, T=50.0, sigma_allow=-1.0)
        assert res["ok"] is False

    def test_invalid_method_returns_error(self):
        """Unknown method string must return ok=False."""
        res = shaft_diameter(M=100.0, T=50.0, sigma_allow=200e6, method="von-mises-wrong")
        assert res["ok"] is False


class TestShaftDiameterMaxShear:

    def test_max_shear_formula_matches_algebraic(self):
        """Verify max-shear formula: d³ = (32/πSe) × √(M² + T²)."""
        M, T, Se = 80.0, 120.0, 250e6
        rhs = (32.0 / (math.pi * Se)) * math.sqrt(M ** 2 + T ** 2)
        d_expected = rhs ** (1.0 / 3.0)
        res = shaft_diameter(M=M, T=T, sigma_allow=Se, method="max-shear")
        assert res["ok"] is True
        assert abs(res["diameter_m"] - d_expected) / d_expected < REL

    def test_max_shear_greater_than_de_goodman(self):
        """max-shear criterion must yield >= diameter compared to DE-Goodman
        for the same M, T (since √(M²+T²) >= √(M²+0.75T²))."""
        M, T, Se = 100.0, 200.0, 300e6
        d_dg = shaft_diameter(M=M, T=T, sigma_allow=Se, method="DE-Goodman")["diameter_m"]
        d_ms = shaft_diameter(M=M, T=T, sigma_allow=Se, method="max-shear")["diameter_m"]
        assert d_ms >= d_dg


# ===========================================================================
# 2. shaft_critical_speed
# ===========================================================================

class TestShaftCriticalSpeed:

    def _omega_simply_supported(self, L, m, E, I):
        """Reference formula: ω = (π/L)² × √(EI/m)."""
        return (math.pi / L) ** 2 * math.sqrt(E * I / m)

    def test_simply_supported_matches_reference(self):
        """simply-supported: ω = (π/L)² √(EI/m)."""
        L, m, E, I = 1.0, 5.0, 200e9, 1e-6
        omega_ref = self._omega_simply_supported(L, m, E, I)
        res = shaft_critical_speed(L, m, E, I, supports="simply-supported")
        assert res["ok"] is True
        assert abs(res["omega_rad_s"] - omega_ref) / omega_ref < REL

    def test_fixed_fixed_higher_than_simply_supported(self):
        """fixed-fixed boundary gives higher critical speed than simply-supported."""
        L, m, E, I = 0.8, 4.0, 200e9, 5e-7
        res_ss = shaft_critical_speed(L, m, E, I, supports="simply-supported")
        res_ff = shaft_critical_speed(L, m, E, I, supports="fixed-fixed")
        assert res_ff["n_rpm"] > res_ss["n_rpm"]

    def test_critical_speed_scales_sqrt_EI(self):
        """Doubling EI must increase ω by √2 (critical speed ∝ √(EI))."""
        L, m, E, I = 1.0, 3.0, 200e9, 1e-7
        omega1 = shaft_critical_speed(L, m, E, I)["omega_rad_s"]
        omega2 = shaft_critical_speed(L, m, E * 2, I)["omega_rad_s"]
        assert abs(omega2 / omega1 - math.sqrt(2.0)) < 1e-9

    def test_critical_speed_scales_inv_sqrt_m(self):
        """Doubling mass_per_m must decrease ω by √2 (ω ∝ 1/√m)."""
        L, m, E, I = 1.0, 3.0, 200e9, 1e-7
        omega1 = shaft_critical_speed(L, m, E, I)["omega_rad_s"]
        omega2 = shaft_critical_speed(L, m * 2, E, I)["omega_rad_s"]
        assert abs(omega2 / omega1 - 1.0 / math.sqrt(2.0)) < 1e-9

    def test_rpm_from_omega(self):
        """n_rpm == omega × 60 / (2π)."""
        L, m, E, I = 0.5, 2.0, 200e9, 1e-8
        res = shaft_critical_speed(L, m, E, I)
        assert res["ok"] is True
        n_expected = res["omega_rad_s"] * 60.0 / (2.0 * math.pi)
        assert abs(res["n_rpm"] - n_expected) / n_expected < REL

    def test_negative_length_returns_error(self):
        res = shaft_critical_speed(-1.0, 5.0, 200e9, 1e-6)
        assert res["ok"] is False

    def test_zero_mass_per_m_returns_error(self):
        res = shaft_critical_speed(1.0, 0.0, 200e9, 1e-6)
        assert res["ok"] is False

    def test_unknown_supports_returns_error(self):
        res = shaft_critical_speed(1.0, 5.0, 200e9, 1e-6, supports="cantilever")
        assert res["ok"] is False


# ===========================================================================
# 3. bearing_l10
# ===========================================================================

class TestBearingL10:

    def test_ball_bearing_basic_life(self):
        """L10 = (C/P)³ for ball bearings (ISO 281)."""
        C, P, n = 10000.0, 5000.0, 1000.0
        res = bearing_l10(C, P, n, "ball")
        assert res["ok"] is True
        expected = (C / P) ** 3
        assert abs(res["L10_rev"] - expected) / expected < REL

    def test_roller_bearing_basic_life(self):
        """L10 = (C/P)^(10/3) for roller bearings (ISO 281)."""
        C, P, n = 20000.0, 8000.0, 500.0
        res = bearing_l10(C, P, n, "roller")
        assert res["ok"] is True
        expected = (C / P) ** (10.0 / 3.0)
        assert abs(res["L10_rev"] - expected) / expected < REL

    def test_doubling_C_over_P_doubles_L10_ball(self):
        """For ball bearing: L10 ∝ (C/P)³, so doubling C/P multiplies L10 by 2³=8."""
        C1, C2, P, n = 10000.0, 20000.0, 10000.0, 1000.0
        L1 = bearing_l10(C1, P, n, "ball")["L10_rev"]
        L2 = bearing_l10(C2, P, n, "ball")["L10_rev"]
        # C/P goes from 1 to 2, so L10 goes from 1 to 8
        assert abs(L2 / L1 - 8.0) < 1e-9

    def test_L10_doubles_when_C_over_P_increases_by_2_to_1_over_p_ball(self):
        """L10 doubles when C/P increases by factor 2^(1/p) for ball p=3."""
        C_base, P, n = 10000.0, 5000.0, 1000.0
        p = 3.0
        factor = 2.0 ** (1.0 / p)
        C_new = C_base * factor  # C/P increases by 2^(1/3), L10 doubles
        L1 = bearing_l10(C_base, P, n, "ball")["L10_rev"]
        L2 = bearing_l10(C_new, P, n, "ball")["L10_rev"]
        assert abs(L2 / L1 - 2.0) < 1e-9

    def test_L10_doubles_when_C_over_P_increases_by_2_to_1_over_p_roller(self):
        """L10 doubles when C/P increases by factor 2^(1/p) for roller p=10/3."""
        C_base, P, n = 15000.0, 5000.0, 800.0
        p = 10.0 / 3.0
        factor = 2.0 ** (1.0 / p)
        C_new = C_base * factor
        L1 = bearing_l10(C_base, P, n, "roller")["L10_rev"]
        L2 = bearing_l10(C_new, P, n, "roller")["L10_rev"]
        assert abs(L2 / L1 - 2.0) < 1e-9

    def test_roller_has_different_life_than_ball_same_loads(self):
        """Ball and roller give different L10 for same C, P."""
        C, P, n = 12000.0, 6000.0, 1200.0
        L_ball = bearing_l10(C, P, n, "ball")["L10_rev"]
        L_roller = bearing_l10(C, P, n, "roller")["L10_rev"]
        # p=3 vs p=10/3: with C/P=2, ball=8, roller=2^(10/3)≈10.08
        assert abs(L_ball - L_roller) > 1e-6

    def test_l10_hours_formula(self):
        """L10_hours = L10_rev × 1e6 / (60 × n)."""
        C, P, n = 20000.0, 10000.0, 1500.0
        res = bearing_l10(C, P, n, "ball")
        assert res["ok"] is True
        hours_expected = res["L10_rev"] * 1e6 / (60.0 * n)
        assert abs(res["L10_hours"] - hours_expected) / hours_expected < REL

    def test_negative_C_returns_error(self):
        res = bearing_l10(C=-1.0, P=5000.0, n_rpm=1000.0)
        assert res["ok"] is False

    def test_negative_P_returns_error(self):
        res = bearing_l10(C=10000.0, P=-100.0, n_rpm=1000.0)
        assert res["ok"] is False

    def test_zero_n_rpm_returns_error(self):
        res = bearing_l10(C=10000.0, P=5000.0, n_rpm=0.0)
        assert res["ok"] is False

    def test_unknown_bearing_type_returns_error(self):
        res = bearing_l10(C=10000.0, P=5000.0, n_rpm=1000.0, bearing_type="needle")
        assert res["ok"] is False


# ===========================================================================
# 4. key_size
# ===========================================================================

class TestKeySize:

    def test_standard_key_lookup_25mm_shaft(self):
        """25 mm shaft → 8×7 key (ANSI B17.1, range 22–30 mm)."""
        res = key_size(shaft_d_mm=25.0, torque_Nm=100.0)
        assert res["ok"] is True
        assert res["key_width_mm"] == 8.0
        assert res["key_height_mm"] == 7.0

    def test_shear_stress_formula(self):
        """Verify τ = F / (w × L) where F = 2T/d."""
        d_mm = 50.0
        T_Nm = 500.0
        res = key_size(shaft_d_mm=d_mm, torque_Nm=T_Nm)
        assert res["ok"] is True
        d_m = d_mm * 1e-3
        w_m = res["key_width_mm"] * 1e-3
        L_m = res["key_length_mm"] * 1e-3
        F = 2.0 * T_Nm / d_m
        tau_expected = F / (w_m * L_m)
        assert abs(res["shear_stress_Pa"] - tau_expected) / tau_expected < REL

    def test_bearing_stress_formula(self):
        """Verify σ_c = F / (h/2 × L)."""
        d_mm = 40.0
        T_Nm = 300.0
        res = key_size(shaft_d_mm=d_mm, torque_Nm=T_Nm)
        assert res["ok"] is True
        d_m = d_mm * 1e-3
        h_m = res["key_height_mm"] * 1e-3
        L_m = res["key_length_mm"] * 1e-3
        F = 2.0 * T_Nm / d_m
        sigma_c_expected = F / ((h_m / 2.0) * L_m)
        assert abs(res["bearing_stress_Pa"] - sigma_c_expected) / sigma_c_expected < REL

    def test_zero_torque_gives_zero_stresses(self):
        """Zero torque → zero shear and bearing stress, all checks pass."""
        res = key_size(shaft_d_mm=30.0, torque_Nm=0.0)
        assert res["ok"] is True
        assert res["shear_stress_Pa"] == 0.0
        assert res["bearing_stress_Pa"] == 0.0
        assert res["shear_ok"] is True
        assert res["bearing_ok"] is True

    def test_large_torque_fails_stress_check(self):
        """A very large torque must fail shear or bearing check."""
        res = key_size(shaft_d_mm=10.0, torque_Nm=50000.0, material="cast_iron")
        assert res["ok"] is True  # function succeeded
        # At least one of the stress checks should fail
        assert not res["shear_ok"] or not res["bearing_ok"]

    def test_custom_key_length(self):
        """Custom key_length_mm must be used in stress calculation."""
        d_mm, T = 50.0, 400.0
        res_default = key_size(shaft_d_mm=d_mm, torque_Nm=T)
        res_custom = key_size(shaft_d_mm=d_mm, torque_Nm=T, key_length_mm=200.0)
        assert res_default["key_length_mm"] != 200.0
        assert res_custom["key_length_mm"] == 200.0
        # Longer key → lower stress
        assert res_custom["shear_stress_Pa"] < res_default["shear_stress_Pa"]

    def test_out_of_range_shaft_returns_error(self):
        """Shaft diameter outside table range returns ok=False."""
        res = key_size(shaft_d_mm=500.0, torque_Nm=100.0)
        assert res["ok"] is False
        assert "reason" in res

    def test_negative_shaft_d_returns_error(self):
        res = key_size(shaft_d_mm=-20.0, torque_Nm=100.0)
        assert res["ok"] is False

    def test_negative_torque_returns_error(self):
        res = key_size(shaft_d_mm=30.0, torque_Nm=-50.0)
        assert res["ok"] is False

    def test_unknown_material_returns_error(self):
        res = key_size(shaft_d_mm=30.0, torque_Nm=100.0, material="unobtanium")
        assert res["ok"] is False

    def test_safety_factors_positive_for_valid_inputs(self):
        """Safety factors must be finite positive for valid inputs."""
        res = key_size(shaft_d_mm=30.0, torque_Nm=100.0)
        assert res["ok"] is True
        assert res["shear_safety_factor"] > 0
        assert res["bearing_safety_factor"] > 0
        assert math.isfinite(res["shear_safety_factor"])
        assert math.isfinite(res["bearing_safety_factor"])


# ===========================================================================
# 5. LLM tool wrappers (run_*)
# ===========================================================================

class TestToolWrappers:

    def test_run_shaft_diameter_happy_path(self):
        ctx = _ctx()
        raw = _run(run_shaft_diameter(ctx, _args(M=100.0, T=200.0, sigma_allow=300e6)))
        d = _ok_tool(raw)
        assert d["diameter_m"] > 0

    def test_run_shaft_diameter_missing_M(self):
        ctx = _ctx()
        raw = _run(run_shaft_diameter(ctx, _args(T=200.0, sigma_allow=300e6)))
        _err_tool(raw)

    def test_run_shaft_critical_speed_happy_path(self):
        ctx = _ctx()
        raw = _run(run_shaft_critical_speed(ctx, _args(
            length_m=1.0, mass_per_m=5.0, E=200e9, I=1e-6
        )))
        d = _ok_tool(raw)
        assert d["n_rpm"] > 0

    def test_run_shaft_critical_speed_bad_json(self):
        ctx = _ctx()
        raw = _run(run_shaft_critical_speed(ctx, b"not json"))
        _err_tool(raw)

    def test_run_bearing_l10_ball_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bearing_l10(ctx, _args(C=20000.0, P=10000.0, n_rpm=1000.0, bearing_type="ball")))
        d = _ok_tool(raw)
        assert abs(d["L10_rev"] - 8.0) < 1e-9  # (20000/10000)^3 = 8

    def test_run_bearing_l10_roller_happy_path(self):
        ctx = _ctx()
        raw = _run(run_bearing_l10(ctx, _args(C=20000.0, P=10000.0, n_rpm=500.0, bearing_type="roller")))
        d = _ok_tool(raw)
        expected = 2.0 ** (10.0 / 3.0)
        assert abs(d["L10_rev"] - expected) / expected < 1e-9

    def test_run_bearing_l10_missing_C(self):
        ctx = _ctx()
        raw = _run(run_bearing_l10(ctx, _args(P=5000.0, n_rpm=1000.0)))
        _err_tool(raw)

    def test_run_key_size_happy_path(self):
        ctx = _ctx()
        raw = _run(run_key_size(ctx, _args(shaft_d_mm=50.0, torque_Nm=400.0)))
        d = _ok_tool(raw)
        assert d["key_width_mm"] > 0
        assert d["key_height_mm"] > 0

    def test_run_key_size_negative_torque(self):
        ctx = _ctx()
        raw = _run(run_key_size(ctx, _args(shaft_d_mm=50.0, torque_Nm=-100.0)))
        _err_tool(raw)

    def test_run_shaft_diameter_max_shear_via_tool(self):
        ctx = _ctx()
        raw = _run(run_shaft_diameter(ctx, _args(
            M=80.0, T=120.0, sigma_allow=250e6, method="max-shear"
        )))
        d = _ok_tool(raw)
        # Verify algebraically
        rhs = (32.0 / (math.pi * 250e6)) * math.sqrt(80.0 ** 2 + 120.0 ** 2)
        d_expected = rhs ** (1.0 / 3.0)
        assert abs(d["diameter_m"] - d_expected) / d_expected < REL

    def test_run_shaft_critical_speed_fixed_fixed(self):
        ctx = _ctx()
        raw = _run(run_shaft_critical_speed(ctx, _args(
            length_m=0.8, mass_per_m=4.0, E=200e9, I=5e-7, supports="fixed-fixed"
        )))
        d = _ok_tool(raw)
        assert d["beta_L"] == pytest.approx(4.73004074, rel=1e-5)


# ===========================================================================
# Externally-citable reference cases (production-confidence validation)
# Cross-checked against authoritative published worked examples.
# ===========================================================================

from kerf_cad_core.shaft.calc import (  # noqa: E402
    shaft_diameter as _ref_shaft_diameter,
    bearing_l10 as _ref_bearing_l10,
    shaft_critical_speed as _ref_shaft_crit,
    key_size as _ref_key_size,
)


class TestShaftExternalReferences:
    """Validated against Shigley 10th ed., SKF catalogue, Rao Mechanical Vibrations."""

    def test_de_pure_bending_closed_form(self):
        # Shigley 10th ed. Eq. (7-7) reduces, for pure bending (T=0), to
        # d^3 = 32 Kf M / (pi Se). M=1000 N·m, Se=100 MPa → d = 0.046702 m.
        r = _ref_shaft_diameter(1000.0, 0.0, 100e6, method="DE-Goodman")
        assert r["ok"]
        assert r["diameter_m"] == pytest.approx((32 * 1000.0 / (math.pi * 100e6)) ** (1 / 3), rel=1e-12)

    def test_de_pure_torsion_von_mises(self):
        # Shigley §7-4: DE pure-torsion equivalent → d^3 = 16√3 T /(π Se).
        # T=1000 N·m, Se=100 MPa. Coefficient 32√0.75 = 16√3 = 27.7128.
        r = _ref_shaft_diameter(0.0, 1000.0, 100e6, method="DE-Goodman")
        d_exp = (16 * math.sqrt(3) * 1000.0 / (math.pi * 100e6)) ** (1 / 3)
        assert r["diameter_m"] == pytest.approx(d_exp, rel=1e-12)

    def test_max_shear_pure_torsion(self):
        # Tresca (ASME B106): d^3 = 16 T /(π τ_allow), τ_allow = σ/2.
        # T=1000 N·m, σ=100 MPa → τ=50 MPa.
        r = _ref_shaft_diameter(0.0, 1000.0, 100e6, method="max-shear")
        d_exp = (16 * 1000.0 / (math.pi * 50e6)) ** (1 / 3)
        assert r["diameter_m"] == pytest.approx(d_exp, rel=1e-12)

    def test_max_shear_combined(self):
        # Tresca combined: d^3 = 16/(π τ) √(M²+T²). M=600, T=800 → √=1000.
        r = _ref_shaft_diameter(600.0, 800.0, 100e6, method="max-shear")
        d_exp = (16 * 1000.0 / (math.pi * 50e6)) ** (1 / 3)
        assert r["diameter_m"] == pytest.approx(d_exp, rel=1e-12)

    def test_bearing_l10_ball_skf(self):
        # SKF catalogue / ISO 281: ball p=3. C=30.7 kN, P=3 kN
        # L10 = (30700/3000)^3 = 1071.65 Mrev.
        r = _ref_bearing_l10(30700.0, 3000.0, 1.0, "ball")
        assert r["L10_rev"] == pytest.approx((30700.0 / 3000.0) ** 3, rel=1e-12)

    def test_bearing_l10_roller_iso281(self):
        # ISO 281: roller p=10/3. C=30.7 kN, P=3 kN.
        r = _ref_bearing_l10(30700.0, 3000.0, 1.0, "roller")
        assert r["L10_rev"] == pytest.approx((30700.0 / 3000.0) ** (10.0 / 3.0), rel=1e-12)

    def test_bearing_l10_hours_conversion(self):
        # ISO 281: L10h = L10·1e6/(60 n). C/P=10 ball, n=1500 rpm
        # L10=1000 Mrev → L10h = 1000e6/(60·1500) = 11111.11 h.
        r = _ref_bearing_l10(10000.0, 1000.0, 1500.0, "ball")
        assert r["L10_hours"] == pytest.approx(1000.0 * 1e6 / (60.0 * 1500.0), rel=1e-9)

    def test_critical_speed_ss_euler_bernoulli(self):
        # Rao "Mechanical Vibrations" 5th ed. §8-6: simply-supported uniform
        # shaft ω₁ = π² √(EI/(mL⁴)). Steel d=50mm, L=1m, E=207 GPa, ρ=7800.
        d, L, E, rho = 0.05, 1.0, 207e9, 7800.0
        I = math.pi * d ** 4 / 64.0
        m = rho * math.pi * d ** 2 / 4.0
        r = _ref_shaft_crit(L, m, E, I, supports="simply-supported")
        assert r["omega_rad_s"] == pytest.approx(math.pi ** 2 * math.sqrt(E * I / (m * L ** 4)), rel=1e-12)

    def test_critical_speed_fixed_fixed_eigenvalue(self):
        # Rao §8-6: fixed-fixed first eigenvalue βL = 4.730041.
        d, L, E, rho = 0.05, 1.0, 207e9, 7800.0
        I = math.pi * d ** 4 / 64.0
        m = rho * math.pi * d ** 2 / 4.0
        r = _ref_shaft_crit(L, m, E, I, supports="fixed-fixed")
        bl = 4.73004074
        assert r["omega_rad_s"] == pytest.approx(bl ** 2 * math.sqrt(E * I / (m * L ** 4)), rel=1e-6)

    def test_key_shear_stress_shigley(self):
        # Shigley §8-9: tangential force F = 2T/d; key shear τ = F/(wL).
        # d=30 mm → DIN 6885 key 8×7; T=200 N·m, L=45 mm (1.5·d).
        r = _ref_key_size(30.0, 200.0, "steel_1045")
        assert r["ok"]
        F = 2.0 * 200.0 / 0.030
        tau = F / (0.008 * 0.045)
        assert r["shear_stress_Pa"] == pytest.approx(tau, rel=1e-9)
        assert r["key_width_mm"] == 8 and r["key_height_mm"] == 7
