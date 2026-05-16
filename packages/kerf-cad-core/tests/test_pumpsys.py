"""
Hermetic tests for kerf_cad_core.pumpsys — centrifugal-pump & system-curve
engineering.

Coverage:
  curve.system_curve              — H = H_static + K·Q²
  curve.system_K_from_pipe        — K from Darcy-Weisbach + fittings
  curve.pump_curve_from_points    — quadratic fit from catalogue points
  curve.operating_point           — pump / system intersection
  curve.hydraulic_power           — fluid power, brake power, efficiency
  curve.npsh_available            — NPSHa calculation
  curve.npsh_check                — cavitation margin
  curve.affinity_speed            — speed-change affinity laws
  curve.affinity_trim             — impeller-trim affinity laws
  curve.pumps_in_series           — combined head
  curve.pumps_in_parallel         — combined flow
  curve.specific_speed            — Ns + impeller guidance
  curve.minimum_flow_note         — below-MCSF warning
  tools.*                         — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas are verified algebraically against pump-handbook hand-calcs.

References
----------
Kaplan, I. et al., "Pump Handbook", 4th ed., McGraw-Hill (2010).
White, F.M., "Fluid Mechanics", 8th ed., McGraw-Hill (2016).
HI (Hydraulic Institute) Standards 9.6.4.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.pumpsys.curve import (
    system_curve,
    system_K_from_pipe,
    pump_curve_from_points,
    operating_point,
    hydraulic_power,
    npsh_available,
    npsh_check,
    affinity_speed,
    affinity_trim,
    pumps_in_series,
    pumps_in_parallel,
    specific_speed,
    minimum_flow_note,
)
from kerf_cad_core.pumpsys.tools import (
    run_system_curve,
    run_system_K_from_pipe,
    run_pump_curve_fit,
    run_operating_point,
    run_hydraulic_power,
    run_npsh_available,
    run_npsh_check,
    run_affinity_speed,
    run_affinity_trim,
    run_pumps_in_series,
    run_pumps_in_parallel,
    run_specific_speed,
    run_minimum_flow_check,
)

_G = 9.81
REL = 1e-6


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


# ===========================================================================
# 1. system_curve
# ===========================================================================

class TestSystemCurve:

    def test_pure_static_head_no_friction(self):
        """K=0: H_sys = H_static regardless of Q."""
        res = system_curve(H_static=10.0, K=0.0, Q=0.05)
        assert res["ok"] is True
        assert abs(res["H_system_m"] - 10.0) < REL

    def test_pure_friction_no_static(self):
        """H_static=0: H_sys = K·Q²."""
        K, Q = 200.0, 0.05
        res = system_curve(H_static=0.0, K=K, Q=Q)
        assert res["ok"] is True
        expected = K * Q ** 2
        assert abs(res["H_system_m"] - expected) / expected < REL

    def test_combined_static_and_friction(self):
        """H_sys = H_static + K·Q²."""
        H_s, K, Q = 8.0, 150.0, 0.03
        res = system_curve(H_static=H_s, K=K, Q=Q)
        assert res["ok"] is True
        expected = H_s + K * Q ** 2
        assert abs(res["H_system_m"] - expected) / expected < REL

    def test_zero_flow_returns_static_head(self):
        """At Q=0 the system head equals the static head."""
        res = system_curve(H_static=15.0, K=500.0, Q=0.0)
        assert res["ok"] is True
        assert abs(res["H_system_m"] - 15.0) < REL

    def test_negative_K_returns_error(self):
        res = system_curve(H_static=10.0, K=-1.0, Q=0.01)
        assert res["ok"] is False

    def test_negative_Q_returns_error(self):
        res = system_curve(H_static=5.0, K=100.0, Q=-0.01)
        assert res["ok"] is False


# ===========================================================================
# 2. system_K_from_pipe
# ===========================================================================

class TestSystemKFromPipe:

    def test_K_formula_algebraic(self):
        """K = (f·L/D + K_fittings) / (2·g·A²)."""
        f, L, D = 0.02, 50.0, 0.1
        A = math.pi * D ** 2 / 4.0
        K_fit = 3.0
        res = system_K_from_pipe(f, L, D, A, K_fittings=K_fit)
        assert res["ok"] is True
        expected = (f * L / D + K_fit) / (2.0 * _G * A ** 2)
        assert abs(res["K"] - expected) / expected < REL

    def test_no_fittings_default(self):
        """Without K_fittings the formula reduces to (f·L/D) / (2·g·A²)."""
        f, L, D = 0.025, 100.0, 0.15
        A = math.pi * D ** 2 / 4.0
        res = system_K_from_pipe(f, L, D, A)
        assert res["ok"] is True
        expected = (f * L / D) / (2.0 * _G * A ** 2)
        assert abs(res["K"] - expected) / expected < REL

    def test_negative_f_returns_error(self):
        A = math.pi * 0.1 ** 2 / 4.0
        res = system_K_from_pipe(-0.02, 50.0, 0.1, A)
        assert res["ok"] is False

    def test_zero_D_returns_error(self):
        A = math.pi * 0.1 ** 2 / 4.0
        res = system_K_from_pipe(0.02, 50.0, 0.0, A)
        assert res["ok"] is False

    def test_f_L_D_field_in_result(self):
        f, L, D = 0.02, 50.0, 0.1
        A = math.pi * D ** 2 / 4.0
        res = system_K_from_pipe(f, L, D, A)
        assert res["ok"] is True
        assert abs(res["f_L_D"] - f * L / D) < REL


# ===========================================================================
# 3. pump_curve_from_points
# ===========================================================================

class TestPumpCurveFromPoints:

    # Catalogue points for a typical centrifugal pump:
    # (Q m³/s, H m) — shut-off, mid-curve, max-flow
    _pts3 = [(0.0, 30.0), (0.05, 25.0), (0.10, 10.0)]

    def test_three_point_fit_passes_through_all(self):
        """For exactly 3 points, the quadratic passes through each."""
        pts = self._pts3
        res = pump_curve_from_points(pts)
        assert res["ok"] is True
        a, b, c = res["a"], res["b"], res["c"]
        for q, h in pts:
            h_fit = a * q ** 2 + b * q + c
            assert abs(h_fit - h) < 0.01, f"Fit residual too large at Q={q}: {h_fit} vs {h}"

    def test_shutoff_head_equals_c(self):
        """H(Q=0) = c (intercept)."""
        res = pump_curve_from_points(self._pts3)
        assert res["ok"] is True
        assert abs(res["H_shutoff"] - res["c"]) < REL
        assert abs(res["H_shutoff"] - 30.0) < 0.01

    def test_Q_max_correct(self):
        """Q_max should equal the largest Q in points."""
        res = pump_curve_from_points(self._pts3)
        assert res["ok"] is True
        assert abs(res["Q_max"] - 0.10) < REL

    def test_four_point_lsq_fit(self):
        """Least-squares over 4 points: fit through all for a pure quadratic."""
        # Generate 4 exact points from a known quadratic: H = -3000*Q^2 - 10*Q + 35
        a0, b0, c0 = -3000.0, -10.0, 35.0
        Qs = [0.0, 0.02, 0.06, 0.10]
        pts = [(q, a0 * q ** 2 + b0 * q + c0) for q in Qs]
        res = pump_curve_from_points(pts)
        assert res["ok"] is True
        # For pure quadratic data the least-squares solution is exact
        assert abs(res["a"] - a0) < 0.1
        assert abs(res["b"] - b0) < 0.1
        assert abs(res["c"] - c0) < 0.1

    def test_fewer_than_3_points_returns_error(self):
        res = pump_curve_from_points([(0.0, 30.0), (0.05, 25.0)])
        assert res["ok"] is False

    def test_duplicate_Q_values_returns_error(self):
        res = pump_curve_from_points([(0.0, 30.0), (0.0, 25.0), (0.05, 20.0)])
        assert res["ok"] is False

    def test_negative_Q_returns_error(self):
        res = pump_curve_from_points([(-0.01, 30.0), (0.05, 25.0), (0.10, 10.0)])
        assert res["ok"] is False


# ===========================================================================
# 4. operating_point
# ===========================================================================

class TestOperatingPoint:

    def _get_pump_coeffs(self):
        """Fit the sample 3-point catalogue."""
        pts = [(0.0, 30.0), (0.05, 25.0), (0.10, 10.0)]
        r = pump_curve_from_points(pts)
        return r["a"], r["b"], r["c"]

    def test_operating_point_on_pump_curve(self):
        """Operating Q and H must satisfy the pump curve equation."""
        a, b, c = self._get_pump_coeffs()
        res = operating_point(a, b, c, H_static=5.0, K=500.0)
        assert res["ok"] is True
        Q = res["Q_op_m3s"]
        H = res["H_op_m"]
        H_pump = a * Q ** 2 + b * Q + c
        assert abs(H - H_pump) / max(abs(H), 1e-6) < 1e-5

    def test_operating_point_on_system_curve(self):
        """Operating Q and H must also satisfy the system curve."""
        a, b, c = self._get_pump_coeffs()
        H_static, K = 5.0, 500.0
        res = operating_point(a, b, c, H_static, K)
        assert res["ok"] is True
        Q = res["Q_op_m3s"]
        H = res["H_op_m"]
        H_sys = H_static + K * Q ** 2
        assert abs(H - H_sys) / max(abs(H), 1e-6) < 1e-5

    def test_zero_system_K_gives_Q_at_static_head(self):
        """K=0 system: pump head = H_static at operating point.
        a·Q² + b·Q + (c − H_static) = 0."""
        a, b, c = self._get_pump_coeffs()
        H_static = 20.0
        res = operating_point(a, b, c, H_static=H_static, K=0.0)
        assert res["ok"] is True
        assert abs(res["H_op_m"] - H_static) / H_static < 1e-5

    def test_high_static_head_exceeds_shutoff_returns_warning(self):
        """If H_static > shut-off head, no physical intersection."""
        a, b, c = self._get_pump_coeffs()
        res = operating_point(a, b, c, H_static=100.0, K=0.0)
        # Either error or ok=True with warnings about negative/zero flow
        if res["ok"]:
            # Q_op should be 0 or negative (clamped to 0)
            assert res["Q_op_m3s"] <= 1e-9

    def test_negative_H_static_returns_error(self):
        a, b, c = self._get_pump_coeffs()
        res = operating_point(a, b, c, H_static=-1.0, K=100.0)
        assert res["ok"] is False

    def test_negative_K_returns_error(self):
        a, b, c = self._get_pump_coeffs()
        res = operating_point(a, b, c, H_static=5.0, K=-10.0)
        assert res["ok"] is False


# ===========================================================================
# 5. hydraulic_power
# ===========================================================================

class TestHydraulicPower:

    def test_hydraulic_power_formula(self):
        """P_hydraulic = ρ·g·Q·H."""
        rho, Q, H = 1000.0, 0.05, 20.0
        res = hydraulic_power(Q, H, rho)
        assert res["ok"] is True
        expected = rho * _G * Q * H
        assert abs(res["P_hydraulic_W"] - expected) / expected < REL

    def test_brake_power_from_eta(self):
        """P_brake = P_hydraulic / η."""
        rho, Q, H, eta = 1000.0, 0.05, 20.0, 0.75
        res = hydraulic_power(Q, H, rho, eta=eta)
        assert res["ok"] is True
        P_hyd = rho * _G * Q * H
        P_brake_expected = P_hyd / eta
        assert abs(res["P_brake_W"] - P_brake_expected) / P_brake_expected < REL
        assert abs(res["eta"] - eta) < REL

    def test_eta_from_shaft_power(self):
        """η = P_hydraulic / P_brake when P_shaft_W provided."""
        rho, Q, H = 1000.0, 0.05, 20.0
        P_hyd = rho * _G * Q * H
        P_shaft = P_hyd / 0.80
        res = hydraulic_power(Q, H, rho, P_shaft_W=P_shaft)
        assert res["ok"] is True
        assert abs(res["eta"] - 0.80) < 1e-5

    def test_eta_and_P_shaft_mutually_exclusive(self):
        """Providing both eta and P_shaft_W must return ok=False."""
        res = hydraulic_power(0.05, 20.0, 1000.0, eta=0.8, P_shaft_W=15000.0)
        assert res["ok"] is False

    def test_low_eta_triggers_warning(self):
        """η < 0.3 must add a warning."""
        res = hydraulic_power(0.05, 20.0, 1000.0, eta=0.20)
        assert res["ok"] is True
        assert any("low" in w.lower() for w in res["warnings"])

    def test_negative_Q_returns_error(self):
        res = hydraulic_power(-0.01, 20.0, 1000.0)
        assert res["ok"] is False

    def test_zero_H_returns_error(self):
        res = hydraulic_power(0.05, 0.0, 1000.0)
        assert res["ok"] is False

    def test_shaft_power_less_than_hydraulic_returns_error(self):
        """P_shaft_W < P_hydraulic violates energy conservation."""
        rho, Q, H = 1000.0, 0.1, 30.0
        P_hyd = rho * _G * Q * H
        res = hydraulic_power(Q, H, rho, P_shaft_W=P_hyd * 0.5)
        assert res["ok"] is False


# ===========================================================================
# 6. npsh_available
# ===========================================================================

class TestNPSHAvailable:

    def test_standard_npsha_formula(self):
        """NPSHa = (P_atm - P_vapor) / (ρ·g) − z − h_f."""
        P_atm = 101325.0
        P_vap = 2338.0     # water at 20°C
        rho = 998.0
        z = 3.0            # suction lift
        h_f = 0.5
        res = npsh_available(P_atm, P_vap, rho, z, h_f)
        assert res["ok"] is True
        expected = (P_atm - P_vap) / (rho * _G) - z - h_f
        assert abs(res["NPSHa_m"] - expected) / expected < REL

    def test_flooded_suction_increases_npsha(self):
        """Negative z (flooded suction) increases NPSHa relative to z=0."""
        P_atm, P_vap, rho = 101325.0, 2338.0, 998.0
        res_lift = npsh_available(P_atm, P_vap, rho, z_suction_m=3.0, h_friction_m=0.5)
        res_flood = npsh_available(P_atm, P_vap, rho, z_suction_m=-2.0, h_friction_m=0.5)
        assert res_flood["NPSHa_m"] > res_lift["NPSHa_m"]

    def test_zero_friction_and_no_lift(self):
        """z=0, h_f=0: NPSHa = P_margin."""
        P_atm, P_vap, rho = 101325.0, 2338.0, 998.0
        res = npsh_available(P_atm, P_vap, rho, z_suction_m=0.0, h_friction_m=0.0)
        assert res["ok"] is True
        expected = (P_atm - P_vap) / (rho * _G)
        assert abs(res["NPSHa_m"] - expected) / expected < REL
        assert abs(res["P_margin_m"] - expected) / expected < REL

    def test_negative_npsha_adds_warning(self):
        """Very high suction lift produces NPSHa <= 0 → warning."""
        res = npsh_available(101325.0, 2338.0, 998.0, z_suction_m=15.0, h_friction_m=0.5)
        assert res["ok"] is True
        assert any("cavitation" in w.lower() for w in res["warnings"])

    def test_vapor_pressure_ge_atm_returns_error(self):
        res = npsh_available(101325.0, 101325.0, 998.0, z_suction_m=0.0, h_friction_m=0.0)
        assert res["ok"] is False

    def test_negative_friction_returns_error(self):
        res = npsh_available(101325.0, 2338.0, 998.0, z_suction_m=0.0, h_friction_m=-0.5)
        assert res["ok"] is False


# ===========================================================================
# 7. npsh_check
# ===========================================================================

class TestNPSHCheck:

    def test_adequate_npsh_no_cavitation(self):
        """NPSHa well above NPSHr + margin → no cavitation risk."""
        res = npsh_check(NPSHa_m=10.0, NPSHr_m=3.0, margin_m=0.5)
        assert res["ok"] is True
        assert res["cavitation_risk"] is False
        assert res["warnings"] == []

    def test_cavitation_risk_flagged(self):
        """NPSHa < NPSHr + margin → cavitation_risk=True, warning added."""
        res = npsh_check(NPSHa_m=3.0, NPSHr_m=3.0, margin_m=0.5)
        assert res["ok"] is True
        assert res["cavitation_risk"] is True
        assert len(res["warnings"]) > 0
        assert "CAVITATION" in res["warnings"][0].upper()

    def test_npsha_minus_npshr_field(self):
        """NPSHa_minus_NPSHr must equal NPSHa − NPSHr."""
        NPSHa, NPSHr = 8.5, 4.0
        res = npsh_check(NPSHa_m=NPSHa, NPSHr_m=NPSHr)
        assert res["ok"] is True
        assert abs(res["NPSHa_minus_NPSHr"] - (NPSHa - NPSHr)) < REL

    def test_default_margin_is_0p5(self):
        """Default margin is 0.5 m."""
        res = npsh_check(NPSHa_m=3.4, NPSHr_m=3.0)
        assert res["ok"] is True
        assert res["margin_m"] == pytest.approx(0.5)
        assert res["cavitation_risk"] is True  # 3.4 < 3.0 + 0.5

    def test_zero_margin_only_flags_when_npsha_lt_npshr(self):
        """With margin=0, only flag when NPSHa < NPSHr."""
        res = npsh_check(NPSHa_m=3.1, NPSHr_m=3.0, margin_m=0.0)
        assert res["ok"] is True
        assert res["cavitation_risk"] is False

    def test_negative_npshr_returns_error(self):
        res = npsh_check(NPSHa_m=5.0, NPSHr_m=-1.0)
        assert res["ok"] is False


# ===========================================================================
# 8. affinity_speed
# ===========================================================================

class TestAffinitySpeed:

    def test_speed_increase_scales_flow(self):
        """Q₂ = Q₁·(n₂/n₁)."""
        Q1, H1, P1, n1, n2 = 0.05, 20.0, 12000.0, 1450.0, 1750.0
        res = affinity_speed(Q1, H1, P1, n1, n2)
        assert res["ok"] is True
        expected_Q2 = Q1 * (n2 / n1)
        assert abs(res["Q2"] - expected_Q2) / expected_Q2 < REL

    def test_speed_increase_scales_head_squared(self):
        """H₂ = H₁·(n₂/n₁)²."""
        Q1, H1, P1, n1, n2 = 0.05, 20.0, 12000.0, 1450.0, 1750.0
        res = affinity_speed(Q1, H1, P1, n1, n2)
        assert res["ok"] is True
        expected_H2 = H1 * (n2 / n1) ** 2
        assert abs(res["H2"] - expected_H2) / expected_H2 < REL

    def test_speed_increase_scales_power_cubed(self):
        """P₂ = P₁·(n₂/n₁)³."""
        Q1, H1, P1, n1, n2 = 0.05, 20.0, 12000.0, 1450.0, 1750.0
        res = affinity_speed(Q1, H1, P1, n1, n2)
        assert res["ok"] is True
        expected_P2 = P1 * (n2 / n1) ** 3
        assert abs(res["P2"] - expected_P2) / expected_P2 < REL

    def test_same_speed_returns_original_values(self):
        """n₁ = n₂ → Q₂=Q₁, H₂=H₁, P₂=P₁."""
        Q1, H1, P1, n = 0.05, 20.0, 12000.0, 1450.0
        res = affinity_speed(Q1, H1, P1, n, n)
        assert res["ok"] is True
        assert abs(res["Q2"] - Q1) < REL
        assert abs(res["H2"] - H1) < REL
        assert abs(res["P2"] - P1) < REL

    def test_halving_speed_reduces_power_by_8(self):
        """P₂/P₁ = (0.5)³ = 0.125 when n₂ = n₁/2."""
        Q1, H1, P1, n1 = 0.05, 20.0, 10000.0, 1450.0
        res = affinity_speed(Q1, H1, P1, n1, n1 / 2)
        assert res["ok"] is True
        assert abs(res["P2"] / P1 - 0.125) < 1e-9

    def test_negative_speed_returns_error(self):
        res = affinity_speed(0.05, 20.0, 10000.0, 1450.0, -1000.0)
        assert res["ok"] is False

    def test_ratio_field_correct(self):
        Q1, H1, P1, n1, n2 = 0.05, 20.0, 12000.0, 1450.0, 1750.0
        res = affinity_speed(Q1, H1, P1, n1, n2)
        assert res["ok"] is True
        assert abs(res["ratio"] - n2 / n1) < REL


# ===========================================================================
# 9. affinity_trim
# ===========================================================================

class TestAffinityTrim:

    def test_trim_reduces_flow_linearly(self):
        """Q₂ = Q₁·(D₂/D₁)."""
        Q1, H1, P1, D1, D2 = 0.05, 20.0, 12000.0, 0.25, 0.22
        res = affinity_trim(Q1, H1, P1, D1, D2)
        assert res["ok"] is True
        assert abs(res["Q2"] - Q1 * D2 / D1) / (Q1 * D2 / D1) < REL

    def test_trim_reduces_head_by_ratio_squared(self):
        """H₂ = H₁·(D₂/D₁)²."""
        Q1, H1, P1, D1, D2 = 0.05, 20.0, 12000.0, 0.25, 0.22
        res = affinity_trim(Q1, H1, P1, D1, D2)
        assert res["ok"] is True
        expected = H1 * (D2 / D1) ** 2
        assert abs(res["H2"] - expected) / expected < REL

    def test_trim_reduces_power_by_ratio_cubed(self):
        """P₂ = P₁·(D₂/D₁)³."""
        Q1, H1, P1, D1, D2 = 0.05, 20.0, 12000.0, 0.25, 0.22
        res = affinity_trim(Q1, H1, P1, D1, D2)
        assert res["ok"] is True
        expected = P1 * (D2 / D1) ** 3
        assert abs(res["P2"] - expected) / expected < REL

    def test_no_trim_returns_original(self):
        """D₂ = D₁ → no change."""
        Q1, H1, P1, D1 = 0.05, 20.0, 12000.0, 0.25
        res = affinity_trim(Q1, H1, P1, D1, D1)
        assert res["ok"] is True
        assert abs(res["Q2"] - Q1) < REL
        assert abs(res["H2"] - H1) < REL
        assert abs(res["P2"] - P1) < REL

    def test_excessive_trim_adds_warning(self):
        """Trim ratio < 0.7 adds a warning."""
        res = affinity_trim(0.05, 20.0, 12000.0, 0.30, 0.20)
        assert res["ok"] is True
        assert any("trim" in w.lower() or "accuracy" in w.lower() for w in res["warnings"])

    def test_negative_D2_returns_error(self):
        res = affinity_trim(0.05, 20.0, 12000.0, 0.25, -0.10)
        assert res["ok"] is False


# ===========================================================================
# 10. pumps_in_series
# ===========================================================================

class TestPumpsInSeries:

    def test_two_identical_pumps_doubles_head(self):
        """Two identical pumps in series → 2× the head at any Q."""
        a, b, c = -2000.0, -5.0, 30.0
        Q = 0.04
        H_single = a * Q ** 2 + b * Q + c
        res = pumps_in_series([(a, b, c), (a, b, c)], Q_eval=Q)
        assert res["ok"] is True
        assert abs(res["H_combined_m"] - 2 * H_single) / (2 * H_single) < REL

    def test_individual_heads_sum_to_combined(self):
        """H_combined = sum of H_individual."""
        curves = [(-1000.0, -10.0, 25.0), (-1500.0, -8.0, 35.0)]
        Q = 0.03
        res = pumps_in_series(curves, Q_eval=Q)
        assert res["ok"] is True
        total = sum(res["H_individual_m"])
        assert abs(res["H_combined_m"] - total) < REL

    def test_single_pump_in_series_is_identity(self):
        """One pump in series: H_combined = H_single."""
        a, b, c = -2000.0, -5.0, 30.0
        Q = 0.03
        res = pumps_in_series([(a, b, c)], Q_eval=Q)
        assert res["ok"] is True
        H_direct = a * Q ** 2 + b * Q + c
        assert abs(res["H_combined_m"] - H_direct) < REL

    def test_zero_curves_returns_error(self):
        res = pumps_in_series([], Q_eval=0.05)
        assert res["ok"] is False

    def test_negative_Q_eval_returns_error(self):
        res = pumps_in_series([(-1000.0, -5.0, 30.0)], Q_eval=-0.01)
        assert res["ok"] is False


# ===========================================================================
# 11. pumps_in_parallel
# ===========================================================================

class TestPumpsInParallel:

    def test_two_identical_pumps_doubles_flow(self):
        """Two identical pumps in parallel → 2× the flow at any H."""
        a, b, c = -2000.0, -5.0, 30.0
        H = 20.0
        # Single pump: solve a·Q² + b·Q + (c - H) = 0
        disc = b ** 2 - 4 * a * (c - H)
        Q_single = (-b - math.sqrt(disc)) / (2 * a)

        res = pumps_in_parallel([(a, b, c), (a, b, c)], H_eval=H)
        assert res["ok"] is True
        # Some floating point tolerance
        assert abs(res["Q_combined_m3s"] - 2 * Q_single) / (2 * Q_single) < 1e-5

    def test_individual_flows_sum_to_combined(self):
        """Q_combined = sum of Q_individual."""
        curves = [(-1000.0, -10.0, 25.0), (-1500.0, -8.0, 35.0)]
        H = 15.0
        res = pumps_in_parallel(curves, H_eval=H)
        assert res["ok"] is True
        total = sum(res["Q_individual_m3s"])
        assert abs(res["Q_combined_m3s"] - total) < REL

    def test_head_exceeding_shutoff_warns_and_gives_zero_flow(self):
        """H_eval > shut-off head: pump cannot contribute; Q=0 with warning."""
        a, b, c = -2000.0, -5.0, 20.0  # shut-off = 20 m
        H_eval = 25.0  # above shut-off
        res = pumps_in_parallel([(a, b, c)], H_eval=H_eval)
        assert res["ok"] is True
        assert res["Q_combined_m3s"] == pytest.approx(0.0, abs=1e-9)
        assert len(res["warnings"]) > 0

    def test_zero_curves_returns_error(self):
        res = pumps_in_parallel([], H_eval=15.0)
        assert res["ok"] is False

    def test_negative_H_eval_returns_error(self):
        res = pumps_in_parallel([(-1000.0, -5.0, 30.0)], H_eval=-1.0)
        assert res["ok"] is False


# ===========================================================================
# 12. specific_speed
# ===========================================================================

class TestSpecificSpeed:

    def test_ns_true_dimensionless_form_with_g(self):
        """Ns* = ω·√Q / (g·H)^(3/4) — White Fluid Mech. 8th ed. Eq. 11.30b.

        Authoritative: the dimensionless specific speed MUST include g so the
        result is unit-free. (Earlier code omitted g — a real defect now fixed.)
        """
        Q, H, n = 0.05, 25.0, 1450.0
        omega = n * 2.0 * math.pi / 60.0
        g = 9.81
        Ns_expected = omega * math.sqrt(Q) / (g * H) ** 0.75
        res = specific_speed(Q, H, n)
        assert res["ok"] is True
        assert abs(res["Ns"] - Ns_expected) / Ns_expected < 1e-6

    def test_white_radial_pump_example(self):
        """White, Fluid Mechanics 8th ed.: a 1750-rpm centrifugal pump,
        Q = 0.0283 m³/s (≈ 449 gpm), H = 91 m → Ns* ≈ 0.19, well inside
        White's radial band (Ns* ≲ 0.75)."""
        res = specific_speed(Q=0.0283, H=91.0, n=1750.0)
        assert res["ok"] is True
        assert abs(res["Ns"] - 0.1888) < 0.01
        assert "radial" in res["impeller_type"].lower()

    def test_white_example_11_8_borderline(self):
        """White Ex. 11.8-type point: n = 1170 rpm, Q = 0.0631 m³/s,
        H = 14.5 m → Ns* ≈ 0.747 (upper edge of the radial band,
        White Fig. 11.20)."""
        res = specific_speed(Q=0.0631, H=14.5, n=1170.0)
        assert res["ok"] is True
        assert abs(res["Ns"] - 0.747) < 0.01
        assert "radial" in res["impeller_type"].lower()

    def test_low_Ns_classified_as_radial(self):
        """Low Ns* (high head, low flow) → radial impeller (White §11.4)."""
        res = specific_speed(Q=0.001, H=100.0, n=2900.0)
        assert res["ok"] is True
        assert "radial" in res["impeller_type"].lower()

    def test_high_Ns_classified_as_axial(self):
        """High Ns* (low head, high flow) → axial impeller.
        White: efficient axial-flow pumps have Ns* ≈ 2.2–5 (dimensionless)."""
        res = specific_speed(Q=1.0, H=2.0, n=900.0)
        assert res["ok"] is True
        assert res["Ns"] > 1.5
        assert "axial" in res["impeller_type"].lower()

    def test_medium_Ns_classified_as_mixed_flow(self):
        """Ns* in White's 0.75–1.5 band → mixed-flow (Francis) impeller."""
        omega = 1450.0 * 2.0 * math.pi / 60.0
        g = 9.81
        Q = 0.1
        Ns_target = 1.1  # mid mixed-flow band
        H = (omega * math.sqrt(Q) / Ns_target) ** (4.0 / 3.0) / g
        res = specific_speed(Q=Q, H=H, n=1450.0)
        assert res["ok"] is True
        assert 0.75 < res["Ns"] < 1.5
        assert "mixed" in res["impeller_type"].lower()

    def test_dimensional_and_us_customary_fields(self):
        """Legacy dimensional Ns and US customary Nss are also returned."""
        Q, H, n = 0.05, 25.0, 1450.0
        omega = n * 2.0 * math.pi / 60.0
        res = specific_speed(Q, H, n)
        assert res["ok"] is True
        assert abs(res["Ns_dimensional"]
                   - omega * math.sqrt(Q) / H ** 0.75) / res["Ns_dimensional"] < 1e-6
        # US customary: n[rpm]·√Q[gpm] / H[ft]^¾
        Q_gpm = Q * 15850.323
        H_ft = H / 0.3048
        assert abs(res["Nss_us_customary"]
                   - n * math.sqrt(Q_gpm) / H_ft ** 0.75) / res["Nss_us_customary"] < 1e-6

    def test_n_rad_s_field(self):
        """n_rad_s == n_rpm × 2π/60."""
        res = specific_speed(Q=0.05, H=25.0, n=1450.0)
        assert res["ok"] is True
        expected_omega = 1450.0 * 2.0 * math.pi / 60.0
        assert abs(res["n_rad_s"] - expected_omega) / expected_omega < REL

    def test_negative_Q_returns_error(self):
        res = specific_speed(Q=-0.01, H=25.0, n=1450.0)
        assert res["ok"] is False

    def test_zero_H_returns_error(self):
        res = specific_speed(Q=0.05, H=0.0, n=1450.0)
        assert res["ok"] is False


# ===========================================================================
# 13. minimum_flow_note
# ===========================================================================

class TestMinimumFlowNote:

    def test_above_mcsf_no_warning(self):
        """Q_op > Q_bep × 0.25 → no warning."""
        res = minimum_flow_note(Q_op=0.04, Q_bep=0.10)
        assert res["ok"] is True
        assert res["below_min_flow"] is False
        assert res["warnings"] == []

    def test_below_mcsf_flags_warning(self):
        """Q_op < Q_bep × 0.25 → below_min_flow=True, warning."""
        res = minimum_flow_note(Q_op=0.02, Q_bep=0.10)
        assert res["ok"] is True
        assert res["below_min_flow"] is True
        assert len(res["warnings"]) > 0
        assert "minimum" in res["warnings"][0].lower() or "recirculation" in res["warnings"][0].lower()

    def test_at_exactly_25pct_no_warning(self):
        """Q_op = Q_bep × 0.25 exactly → not below MCSF."""
        res = minimum_flow_note(Q_op=0.025, Q_bep=0.10)
        assert res["ok"] is True
        assert res["below_min_flow"] is False

    def test_q_fraction_field(self):
        """Q_fraction = Q_op / Q_bep."""
        res = minimum_flow_note(Q_op=0.06, Q_bep=0.10)
        assert res["ok"] is True
        assert abs(res["Q_fraction"] - 0.6) < REL

    def test_q_min_field(self):
        """Q_min = Q_bep × min_fraction."""
        res = minimum_flow_note(Q_op=0.04, Q_bep=0.10, min_fraction=0.3)
        assert res["ok"] is True
        assert abs(res["Q_min_m3s"] - 0.03) < REL

    def test_custom_min_fraction(self):
        """Custom min_fraction overrides the 25% default."""
        res = minimum_flow_note(Q_op=0.04, Q_bep=0.10, min_fraction=0.5)
        assert res["ok"] is True
        assert res["below_min_flow"] is True

    def test_above_120pct_bep_warns(self):
        """Q_op > 1.2 × Q_bep → overload warning."""
        res = minimum_flow_note(Q_op=0.13, Q_bep=0.10)
        assert res["ok"] is True
        assert any("120" in w or "bep" in w.lower() or "overload" in w.lower() for w in res["warnings"])

    def test_negative_Q_op_returns_error(self):
        res = minimum_flow_note(Q_op=-0.01, Q_bep=0.10)
        assert res["ok"] is False

    def test_zero_Q_bep_returns_error(self):
        res = minimum_flow_note(Q_op=0.01, Q_bep=0.0)
        assert res["ok"] is False

    def test_invalid_min_fraction_returns_error(self):
        res = minimum_flow_note(Q_op=0.04, Q_bep=0.10, min_fraction=1.5)
        assert res["ok"] is False


# ===========================================================================
# 14. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_system_curve_happy_path(self):
        ctx = _ctx()
        raw = _run(run_system_curve(ctx, _args(H_static=10.0, K=200.0, Q=0.04)))
        d = _ok_tool(raw)
        expected = 10.0 + 200.0 * 0.04 ** 2
        assert abs(d["H_system_m"] - expected) < 1e-6

    def test_run_system_curve_missing_field(self):
        ctx = _ctx()
        raw = _run(run_system_curve(ctx, _args(H_static=10.0, K=200.0)))
        _err_tool(raw)

    def test_run_system_K_happy_path(self):
        ctx = _ctx()
        f, L, D = 0.02, 50.0, 0.1
        A = math.pi * D ** 2 / 4.0
        raw = _run(run_system_K_from_pipe(ctx, _args(f=f, L=L, D=D, A=A, K_fittings=2.0)))
        d = _ok_tool(raw)
        assert d["K"] > 0

    def test_run_pump_curve_fit_happy_path(self):
        ctx = _ctx()
        pts = [[0.0, 30.0], [0.05, 25.0], [0.10, 10.0]]
        raw = _run(run_pump_curve_fit(ctx, _args(points=pts)))
        d = _ok_tool(raw)
        assert abs(d["H_shutoff"] - 30.0) < 0.05

    def test_run_pump_curve_fit_bad_json(self):
        ctx = _ctx()
        raw = _run(run_pump_curve_fit(ctx, b"not valid json"))
        _err_tool(raw)

    def test_run_operating_point_happy_path(self):
        ctx = _ctx()
        pts = [[0.0, 30.0], [0.05, 25.0], [0.10, 10.0]]
        raw_fit = _run(run_pump_curve_fit(ctx, _args(points=pts)))
        fit = json.loads(raw_fit)
        raw_op = _run(run_operating_point(ctx, _args(
            a=fit["a"], b=fit["b"], c=fit["c"],
            H_static=5.0, K=500.0,
        )))
        d = _ok_tool(raw_op)
        assert d["Q_op_m3s"] > 0
        assert d["H_op_m"] > 0

    def test_run_hydraulic_power_happy_path(self):
        ctx = _ctx()
        raw = _run(run_hydraulic_power(ctx, _args(Q=0.05, H=20.0, rho=1000.0, eta=0.75)))
        d = _ok_tool(raw)
        assert d["P_hydraulic_W"] > 0
        assert d["P_brake_W"] > d["P_hydraulic_W"]

    def test_run_npsh_available_happy_path(self):
        ctx = _ctx()
        raw = _run(run_npsh_available(ctx, _args(
            P_atm_Pa=101325.0, P_vapor_Pa=2338.0, rho=998.0,
            z_suction_m=3.0, h_friction_m=0.5,
        )))
        d = _ok_tool(raw)
        assert d["NPSHa_m"] > 0

    def test_run_npsh_check_cavitation(self):
        ctx = _ctx()
        raw = _run(run_npsh_check(ctx, _args(NPSHa_m=3.0, NPSHr_m=3.0, margin_m=0.5)))
        d = _ok_tool(raw)
        assert d["cavitation_risk"] is True

    def test_run_affinity_speed_happy_path(self):
        ctx = _ctx()
        raw = _run(run_affinity_speed(ctx, _args(
            Q1=0.05, H1=20.0, P1=12000.0, n1=1450.0, n2=1750.0
        )))
        d = _ok_tool(raw)
        expected_Q2 = 0.05 * (1750.0 / 1450.0)
        assert abs(d["Q2"] - expected_Q2) / expected_Q2 < REL

    def test_run_affinity_trim_happy_path(self):
        ctx = _ctx()
        raw = _run(run_affinity_trim(ctx, _args(
            Q1=0.05, H1=20.0, P1=12000.0, D1=0.25, D2=0.22
        )))
        d = _ok_tool(raw)
        assert 0 < d["Q2"] < 0.05

    def test_run_pumps_in_series_happy_path(self):
        ctx = _ctx()
        curves = [[-2000.0, -5.0, 30.0], [-2000.0, -5.0, 30.0]]
        raw = _run(run_pumps_in_series(ctx, _args(curves=curves, Q_eval=0.03)))
        d = _ok_tool(raw)
        assert d["n_pumps"] == 2
        single_H = -2000.0 * 0.03 ** 2 + (-5.0) * 0.03 + 30.0
        assert abs(d["H_combined_m"] - 2 * single_H) < 1e-6

    def test_run_pumps_in_parallel_happy_path(self):
        ctx = _ctx()
        curves = [[-2000.0, -5.0, 30.0], [-2000.0, -5.0, 30.0]]
        raw = _run(run_pumps_in_parallel(ctx, _args(curves=curves, H_eval=20.0)))
        d = _ok_tool(raw)
        assert d["n_pumps"] == 2
        assert d["Q_combined_m3s"] > 0

    def test_run_specific_speed_happy_path(self):
        ctx = _ctx()
        raw = _run(run_specific_speed(ctx, _args(Q=0.05, H=25.0, n=1450.0)))
        d = _ok_tool(raw)
        assert d["Ns"] > 0
        assert "impeller_type" in d

    def test_run_minimum_flow_check_happy_path(self):
        ctx = _ctx()
        raw = _run(run_minimum_flow_check(ctx, _args(Q_op=0.02, Q_bep=0.10)))
        d = _ok_tool(raw)
        assert d["below_min_flow"] is True

    def test_run_minimum_flow_check_missing_Q_bep(self):
        ctx = _ctx()
        raw = _run(run_minimum_flow_check(ctx, _args(Q_op=0.02)))
        _err_tool(raw)
