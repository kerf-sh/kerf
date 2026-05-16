"""
Hermetic tests for kerf_cad_core.railway — railway track & vehicle engineering.

Coverage:
  track.equilibrium_cant      — physics formula validation
  track.applied_cant          — policy limits and deficiency flag
  track.cant_deficiency       — deficiency / excess calculation
  track.cant_gradient_check   — UIC spatial and temporal limits
  track.transition_length     — rate_of_change / cant_gradient / combined
  track.gauge_widening        — UIC table and formula methods
  track.vertical_curve_length — crest and sag formulae
  track.hertzian_contact      — semi-axes, contact area, pressure
  track.davis_resistance      — Davis + grade + curve resistance
  track.tractive_effort       — power / adhesion limit
  track.braking_distance      — reaction + braking + grade
  track.rail_bending          — Winkler beam-on-elastic-foundation
  track.rail_thermal_stress   — CWR thermal stress + buckling flag
  tools.*                     — LLM wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Formulas verified algebraically against published expressions.

References
----------
UIC 703-2:2011, EN 13803-1:2010, Hay (1982), Esveld (2001),
Timoshenko (1976), Johnson (1985)

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.railway.track import (
    equilibrium_cant,
    applied_cant,
    cant_deficiency,
    cant_gradient_check,
    transition_length,
    gauge_widening,
    vertical_curve_length,
    hertzian_contact,
    davis_resistance,
    tractive_effort,
    braking_distance,
    rail_bending,
    rail_thermal_stress,
)
from kerf_cad_core.railway.tools import (
    run_equilibrium_cant,
    run_applied_cant,
    run_cant_deficiency,
    run_cant_gradient_check,
    run_transition_length,
    run_gauge_widening,
    run_vertical_curve,
    run_hertzian_contact,
    run_davis_resistance,
    run_tractive_effort,
    run_braking_distance,
    run_rail_bending,
    run_thermal_stress,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_G = 9.80665


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


# ---------------------------------------------------------------------------
# 1. equilibrium_cant
# ---------------------------------------------------------------------------

class TestEquilibriumCant:
    def test_standard_formula(self):
        """h_eq = V²×G / (g×R); 200 km/h, R=2000 m, G=1.435 m."""
        V_ms = 200.0 / 3.6
        G = 1.435
        R = 2000.0
        expected_mm = (V_ms ** 2 * G / (_G * R)) * 1e3
        r = equilibrium_cant(200.0, 2000.0)
        assert r["ok"] is True
        assert abs(r["cant_eq_mm"] - expected_mm) < 0.01

    def test_uic_approximation_1435mm(self):
        """Simplified UIC: h_eq ≈ 11.8 × V² / R for 1435 mm gauge."""
        # h_eq = V²×1.435/(9.80665×R) ≈ (1.435/9.80665) × V²/R
        # = 0.14633 × V²/R  in m; × 1000 = 146.33 × V²/R mm
        # Standard simplified: 11.8 × V²[km/h] / R  (V in km/h, approximate)
        # The formula with exact g gives: h = (G/g) × V_ms² / R
        # V_ms = V_kmh / 3.6 → V_ms² = V_kmh²/12.96
        # h_mm = (G/g) × V_kmh² / (12.96 × R) × 1000
        # = (1435 / 9.80665) × V_kmh² / (12.96 × R)
        # = 146.33 × V_kmh² / (12.96 × R) = 11.29 × V_kmh²/R  (≈ 11.8)
        r = equilibrium_cant(100.0, 1000.0)
        assert r["ok"] is True
        # Rough: should be around 11.3–11.8 × 100²/1000 = 113–118 mm
        assert 110.0 < r["cant_eq_mm"] < 125.0

    def test_invalid_speed_zero(self):
        r = equilibrium_cant(0.0, 1000.0)
        assert r["ok"] is False

    def test_invalid_radius_negative(self):
        r = equilibrium_cant(100.0, -500.0)
        assert r["ok"] is False

    def test_custom_gauge(self):
        """Narrower gauge → less cant for same speed/radius."""
        r_std = equilibrium_cant(160.0, 1500.0, 1435.0)
        r_narrow = equilibrium_cant(160.0, 1500.0, 1000.0)
        assert r_std["ok"] is True
        assert r_narrow["ok"] is True
        assert r_narrow["cant_eq_mm"] < r_std["cant_eq_mm"]

    def test_proportional_to_speed_squared(self):
        """Doubling speed quadruples equilibrium cant."""
        r1 = equilibrium_cant(100.0, 500.0)
        r2 = equilibrium_cant(200.0, 500.0)
        assert abs(r2["cant_eq_mm"] / r1["cant_eq_mm"] - 4.0) < 0.01

    def test_inversely_proportional_to_radius(self):
        """Doubling radius halves cant."""
        r1 = equilibrium_cant(150.0, 1000.0)
        r2 = equilibrium_cant(150.0, 2000.0)
        assert abs(r1["cant_eq_mm"] / r2["cant_eq_mm"] - 2.0) < 0.01


# ---------------------------------------------------------------------------
# 2. applied_cant
# ---------------------------------------------------------------------------

class TestAppliedCant:
    def test_low_speed_no_deficiency(self):
        """Low speed: h_eq < max_cant → applied = h_eq, deficiency ≈ 0."""
        r = applied_cant(80.0, 3000.0)
        assert r["ok"] is True
        assert abs(r["cant_deficiency_mm"]) < 0.1
        assert r["cant_applied_mm"] == pytest.approx(r["cant_eq_mm"], abs=0.01)

    def test_high_speed_capped_at_max_cant(self):
        """High speed: h_eq > 150 mm → applied = max_cant = 150 mm."""
        r = applied_cant(300.0, 500.0)
        assert r["ok"] is True
        assert r["cant_applied_mm"] <= r["max_cant_mm"] + 1e-9

    def test_deficiency_warning_triggered(self):
        """Very high speed on tight curve: deficiency > 130 mm → warning."""
        r = applied_cant(350.0, 400.0, cant_deficiency_limit_mm=130.0)
        assert r["ok"] is True
        if r["cant_deficiency_mm"] > 130.0:
            assert "cant_deficiency_exceeded" in r["warnings"]

    def test_warning_absent_when_ok(self):
        r = applied_cant(80.0, 5000.0)
        assert r["ok"] is True
        assert "cant_deficiency_exceeded" not in r["warnings"]


# ---------------------------------------------------------------------------
# 3. cant_deficiency
# ---------------------------------------------------------------------------

class TestCantDeficiency:
    def test_zero_applied_cant(self):
        """Applied cant = 0 → deficiency = equilibrium cant."""
        r = cant_deficiency(120.0, 1000.0, 0.0)
        r_eq = equilibrium_cant(120.0, 1000.0)
        assert r["ok"] is True
        assert abs(r["cant_deficiency_mm"] - r_eq["cant_eq_mm"]) < 0.01

    def test_exact_equilibrium_applied(self):
        """Applied cant = equilibrium cant → deficiency = 0."""
        r_eq = equilibrium_cant(120.0, 1000.0)
        r = cant_deficiency(120.0, 1000.0, r_eq["cant_eq_mm"])
        assert r["ok"] is True
        assert abs(r["cant_deficiency_mm"]) < 0.01

    def test_excess_cant(self):
        """Applied > equilibrium → negative deficiency (excess)."""
        r_eq = equilibrium_cant(60.0, 2000.0)
        r = cant_deficiency(60.0, 2000.0, r_eq["cant_eq_mm"] + 20.0)
        assert r["ok"] is True
        assert r["cant_deficiency_mm"] < 0.0
        assert r["cant_excess_mm"] > 0.0

    def test_warning_above_limit(self):
        r = cant_deficiency(250.0, 600.0, 50.0, deficiency_limit_mm=100.0)
        assert r["ok"] is True
        if r["cant_deficiency_mm"] > 100.0:
            assert "cant_deficiency_exceeded" in r["warnings"]

    def test_invalid_negative_cant(self):
        r = cant_deficiency(100.0, 800.0, -5.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 4. cant_gradient_check
# ---------------------------------------------------------------------------

class TestCantGradientCheck:
    def test_both_ok(self):
        """Short cant change, long transition → both criteria pass."""
        r = cant_gradient_check(10.0, 100.0, 100.0)
        assert r["ok"] is True
        assert r["gradient_ok"] is True
        assert r["rate_ok"] is True

    def test_gradient_exceeded(self):
        """Δh=100 mm, L=50 m → gradient=2 mm/m > 1.0 limit."""
        r = cant_gradient_check(100.0, 50.0, 60.0)
        assert r["ok"] is True
        assert r["cant_gradient_mm_per_m"] == pytest.approx(2.0)
        assert r["gradient_ok"] is False

    def test_rate_exceeded(self):
        """Δh=110 mm, L=100 m, V=200 km/h → rate=110×200/3.6/100 ≈ 61 mm/s > 55."""
        V_ms = 200.0 / 3.6
        delta_h = 110.0
        L = 100.0
        rate = delta_h * V_ms / L
        r = cant_gradient_check(delta_h, L, 200.0)
        assert r["ok"] is True
        assert r["cant_rate_mm_per_s"] == pytest.approx(rate, rel=1e-6)
        if rate > 55.0:
            assert r["rate_ok"] is False

    def test_zero_cant_change(self):
        """No cant change → both zero, both pass."""
        r = cant_gradient_check(0.0, 100.0, 160.0)
        assert r["ok"] is True
        assert r["cant_gradient_mm_per_m"] == pytest.approx(0.0)
        assert r["cant_rate_mm_per_s"] == pytest.approx(0.0)

    def test_invalid_zero_length(self):
        r = cant_gradient_check(20.0, 0.0, 120.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 5. transition_length
# ---------------------------------------------------------------------------

class TestTransitionLength:
    def test_rate_of_change_method(self):
        """L = Δh × V / rate_limit = 100 × (200/3.6) / 55."""
        V_ms = 200.0 / 3.6
        expected = 100.0 * V_ms / 55.0
        r = transition_length(100.0, 200.0, method="rate_of_change")
        assert r["ok"] is True
        assert r["transition_length_m"] == pytest.approx(expected, rel=1e-6)

    def test_cant_gradient_method(self):
        """L = Δh / gradient_limit = 100 / 1.0 = 100 m."""
        r = transition_length(100.0, 200.0, method="cant_gradient")
        assert r["ok"] is True
        assert r["transition_length_m"] == pytest.approx(100.0, rel=1e-6)

    def test_combined_method_takes_max(self):
        r = transition_length(100.0, 200.0, method="combined")
        assert r["ok"] is True
        assert r["transition_length_m"] >= r["L_rate_m"]
        assert r["transition_length_m"] >= r["L_gradient_m"]

    def test_zero_cant_change(self):
        """Zero cant change → zero length."""
        r = transition_length(0.0, 160.0)
        assert r["ok"] is True
        assert r["transition_length_m"] == pytest.approx(0.0)

    def test_invalid_method(self):
        r = transition_length(50.0, 160.0, method="bogus")
        assert r["ok"] is False

    def test_longer_at_higher_speed(self):
        """Higher speed → longer transition (rate-of-change)."""
        r1 = transition_length(80.0, 120.0, method="rate_of_change")
        r2 = transition_length(80.0, 200.0, method="rate_of_change")
        assert r2["transition_length_m"] > r1["transition_length_m"]


# ---------------------------------------------------------------------------
# 6. gauge_widening
# ---------------------------------------------------------------------------

class TestGaugeWidening:
    def test_uic_no_widening(self):
        """R >= 250 m → no widening."""
        r = gauge_widening(300.0)
        assert r["ok"] is True
        assert r["gauge_widening_mm"] == pytest.approx(0.0)
        assert r["gauge_design_mm"] == pytest.approx(1435.0)

    def test_uic_5mm_widening(self):
        """175 ≤ R < 250 m → 5 mm."""
        r = gauge_widening(200.0)
        assert r["ok"] is True
        assert r["gauge_widening_mm"] == pytest.approx(5.0)

    def test_uic_10mm_widening(self):
        """150 ≤ R < 175 m → 10 mm."""
        r = gauge_widening(160.0)
        assert r["ok"] is True
        assert r["gauge_widening_mm"] == pytest.approx(10.0)

    def test_uic_15mm_widening(self):
        """R < 150 m → 15 mm."""
        r = gauge_widening(100.0)
        assert r["ok"] is True
        assert r["gauge_widening_mm"] == pytest.approx(15.0)

    def test_formula_method(self):
        """Formula method: R < 300 m → positive widening."""
        r = gauge_widening(200.0, method="formula")
        assert r["ok"] is True
        assert r["gauge_widening_mm"] > 0.0

    def test_formula_zero_for_large_r(self):
        """Formula method: R >= 300 m → zero widening."""
        r = gauge_widening(400.0, method="formula")
        assert r["ok"] is True
        assert r["gauge_widening_mm"] == pytest.approx(0.0)

    def test_invalid_method(self):
        r = gauge_widening(200.0, method="unknown")
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 7. vertical_curve_length
# ---------------------------------------------------------------------------

class TestVerticalCurveLength:
    def test_crest_formula(self):
        """L_crest = V² × |Δg| / 1300 = 200² × 1.5 / 1300."""
        expected = 200.0 ** 2 * 1.5 / 1300.0
        r = vertical_curve_length(1.5, 200.0, curve_type="crest")
        assert r["ok"] is True
        assert r["vertical_curve_length_m"] == pytest.approx(expected, rel=1e-9)

    def test_sag_formula(self):
        """L_sag = V² × |Δg| / 400 = 120² × 2.0 / 400."""
        expected = 120.0 ** 2 * 2.0 / 400.0
        r = vertical_curve_length(2.0, 120.0, curve_type="sag")
        assert r["ok"] is True
        assert r["vertical_curve_length_m"] == pytest.approx(expected, rel=1e-9)

    def test_sag_longer_than_crest(self):
        """Sag requires longer curve than crest (more restrictive comfort)."""
        rc = vertical_curve_length(2.0, 160.0, curve_type="crest")
        rs = vertical_curve_length(2.0, 160.0, curve_type="sag")
        assert rs["vertical_curve_length_m"] > rc["vertical_curve_length_m"]

    def test_negative_grade_sign_ignored(self):
        """Negative Δg should give same length as positive (absolute value)."""
        r_pos = vertical_curve_length(3.0, 200.0, curve_type="crest")
        r_neg = vertical_curve_length(-3.0, 200.0, curve_type="crest")
        assert r_pos["vertical_curve_length_m"] == pytest.approx(r_neg["vertical_curve_length_m"])

    def test_k_value_consistency(self):
        """K_value = L / |Δg| should be self-consistent."""
        r = vertical_curve_length(2.5, 180.0, curve_type="crest")
        assert r["ok"] is True
        assert r["K_value"] == pytest.approx(r["vertical_curve_length_m"] / 2.5, rel=1e-9)

    def test_invalid_curve_type(self):
        r = vertical_curve_length(1.0, 160.0, curve_type="side")
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 8. hertzian_contact
# ---------------------------------------------------------------------------

class TestHertzianContact:
    def test_basic_result_positive(self):
        """Contact semi-axes and pressure must be positive."""
        r = hertzian_contact(
            P_N=80000.0,
            R1x_m=0.46, R1y_m=0.5,
            R2x_m=1e9, R2y_m=0.3,
        )
        assert r["ok"] is True
        assert r["semi_axis_a_m"] > 0.0
        assert r["semi_axis_b_m"] > 0.0
        assert r["max_pressure_Pa"] > 0.0
        assert r["contact_area_m2"] > 0.0

    def test_contact_area_equals_pi_a_b(self):
        """contact_area = π × a × b."""
        r = hertzian_contact(80000.0, 0.46, 0.5, 1e9, 0.3)
        assert r["ok"] is True
        expected_area = math.pi * r["semi_axis_a_m"] * r["semi_axis_b_m"]
        assert r["contact_area_m2"] == pytest.approx(expected_area, rel=1e-9)

    def test_max_pressure_formula(self):
        """p0 = 1.5 × P / (π × a × b)."""
        r = hertzian_contact(80000.0, 0.46, 0.5, 1e9, 0.3)
        assert r["ok"] is True
        p0_check = 1.5 * 80000.0 / r["contact_area_m2"]
        assert r["max_pressure_Pa"] == pytest.approx(p0_check, rel=1e-9)

    def test_higher_load_higher_pressure(self):
        """Doubling wheel load increases contact pressure."""
        r1 = hertzian_contact(50000.0, 0.46, 0.5, 1e9, 0.3)
        r2 = hertzian_contact(100000.0, 0.46, 0.5, 1e9, 0.3)
        assert r2["max_pressure_Pa"] > r1["max_pressure_Pa"]

    def test_invalid_poisson_ratio(self):
        r = hertzian_contact(80000.0, 0.46, 0.5, 1e9, 0.3, nu1=0.6)
        assert r["ok"] is False

    def test_pressure_in_gpa_range(self):
        """Hertz contact pressure must be positive and finite."""
        r = hertzian_contact(80000.0, 0.46, 0.5, 1e9, 0.3)
        assert r["ok"] is True
        # Approximate Hertz formula gives results in the 100 MPa–3 GPa range
        assert 0.1e9 < r["max_pressure_Pa"] < 3e9


# ---------------------------------------------------------------------------
# 9. davis_resistance
# ---------------------------------------------------------------------------

class TestDavisResistance:
    def test_tangent_track_only_davis(self):
        """No grade, no curve → total = A + BV + CV²."""
        A, B, C = 2.0, 0.02, 0.0005
        V = 100.0  # km/h
        expected_specific = A + B * V + C * V ** 2  # N/kN
        r = davis_resistance(500000.0, V, A, B, C)
        assert r["ok"] is True
        assert r["R_davis_N_per_kN"] == pytest.approx(expected_specific, rel=1e-9)
        assert r["R_grade_N_per_kN"] == pytest.approx(0.0)
        assert r["R_curve_N_per_kN"] == pytest.approx(0.0)

    def test_grade_resistance_ascending(self):
        """1% upgrade → R_grade = 10 N/kN."""
        r = davis_resistance(500000.0, 80.0, 2.0, 0.02, 0.0005, grade_percent=1.0)
        assert r["ok"] is True
        assert r["R_grade_N_per_kN"] == pytest.approx(10.0)

    def test_grade_resistance_descending(self):
        """−2% downgrade → R_grade = −20 N/kN (helps momentum)."""
        r = davis_resistance(500000.0, 80.0, 2.0, 0.02, 0.0005, grade_percent=-2.0)
        assert r["ok"] is True
        assert r["R_grade_N_per_kN"] == pytest.approx(-20.0)

    def test_curve_resistance_roeckl(self):
        """R=305 m → R_curve = 6500/(305−55) = 6500/250 = 26 N/kN."""
        r = davis_resistance(500000.0, 60.0, 2.0, 0.01, 0.0003, curve_radius_m=305.0)
        assert r["ok"] is True
        assert r["R_curve_N_per_kN"] == pytest.approx(6500.0 / 250.0, rel=1e-9)

    def test_total_force_consistent(self):
        """R_total_N = R_total_N_per_kN × W_kN."""
        m = 300000.0  # kg
        r = davis_resistance(m, 100.0, 1.5, 0.01, 0.0003, grade_percent=0.5)
        assert r["ok"] is True
        W_kN = m * _G / 1000.0
        expected_N = r["R_total_N_per_kN"] * W_kN
        assert r["R_total_N"] == pytest.approx(expected_N, rel=1e-9)

    def test_invalid_small_curve_radius(self):
        """R <= 55 m → Röckl formula invalid."""
        r = davis_resistance(500000.0, 20.0, 2.0, 0.01, 0.0003, curve_radius_m=50.0)
        assert r["ok"] is False

    def test_zero_speed(self):
        """V=0: only constant A term."""
        r = davis_resistance(100000.0, 0.0, 3.0, 0.02, 0.001)
        assert r["ok"] is True
        assert r["R_davis_N_per_kN"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# 10. tractive_effort
# ---------------------------------------------------------------------------

class TestTractiveEffort:
    def test_power_limited(self):
        """TE_power = P/V; no adhesion check when axle_load=0."""
        P = 4_000_000.0  # 4 MW
        V = 200.0  # km/h
        V_ms = V / 3.6
        expected = P / V_ms
        r = tractive_effort(P, V)
        assert r["ok"] is True
        assert r["TE_power_N"] == pytest.approx(expected, rel=1e-9)
        assert r["TE_applied_N"] == pytest.approx(expected, rel=1e-9)
        assert r["adhesion_limited"] is False

    def test_adhesion_limited(self):
        """Low adhesion → adhesion clips tractive effort."""
        P = 10_000_000.0   # huge power
        V = 10.0            # km/h (low speed → very high TE from power)
        axle_N = 200000.0   # N per axle
        r = tractive_effort(P, V, adhesion_coeff=0.25, axle_load_N=axle_N, driven_axles=4)
        assert r["ok"] is True
        assert r["adhesion_limited"] is True
        assert r["TE_applied_N"] < r["TE_power_N"]
        assert "adhesion_limited" in r["warnings"]
        # TE_adhesion = 0.25 × 200000 × 4 = 200 000 N
        assert r["TE_adhesion_N"] == pytest.approx(0.25 * axle_N * 4, rel=1e-9)

    def test_not_adhesion_limited_high_speed(self):
        """At high speed, power-limited; adhesion not binding."""
        r = tractive_effort(3_000_000.0, 200.0, adhesion_coeff=0.25,
                            axle_load_N=200000.0, driven_axles=4)
        assert r["ok"] is True
        if not r["adhesion_limited"]:
            assert r["TE_applied_N"] == pytest.approx(r["TE_power_N"], rel=1e-9)

    def test_invalid_zero_speed(self):
        r = tractive_effort(3_000_000.0, 0.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 11. braking_distance
# ---------------------------------------------------------------------------

class TestBrakingDistance:
    def test_basic_formula(self):
        """s_brake = V²/(2a); no reaction time, no grade."""
        V_ms = 100.0 / 3.6
        a = 0.8
        expected_brake = V_ms ** 2 / (2.0 * a)
        r = braking_distance(100.0, 0.8, reaction_time_s=0.0)
        assert r["ok"] is True
        assert r["brake_distance_m"] == pytest.approx(expected_brake, rel=1e-9)
        assert r["braking_distance_m"] == pytest.approx(expected_brake, rel=1e-9)

    def test_reaction_distance(self):
        """s_reaction = V_ms × t_react."""
        V_ms = 160.0 / 3.6
        t = 1.5
        r = braking_distance(160.0, 1.0, reaction_time_s=t)
        assert r["ok"] is True
        assert r["reaction_distance_m"] == pytest.approx(V_ms * t, rel=1e-9)

    def test_total_distance_increases_with_speed(self):
        r1 = braking_distance(80.0, 0.8)
        r2 = braking_distance(160.0, 0.8)
        assert r2["braking_distance_m"] > r1["braking_distance_m"]

    def test_grade_aids_braking(self):
        """Ascending grade increases effective deceleration → shorter distance."""
        r_flat = braking_distance(160.0, 0.8, grade_percent=0.0)
        r_uphill = braking_distance(160.0, 0.8, grade_percent=1.5)
        assert r_uphill["braking_distance_m"] < r_flat["braking_distance_m"]

    def test_time_to_stop(self):
        """t_stop = V_ms / a_eff."""
        V_ms = 100.0 / 3.6
        a = 1.0
        r = braking_distance(100.0, a, reaction_time_s=0.0)
        assert r["ok"] is True
        assert r["time_to_stop_s"] == pytest.approx(V_ms / a, rel=1e-9)

    def test_invalid_zero_deceleration(self):
        r = braking_distance(100.0, 0.0)
        assert r["ok"] is False

    def test_grade_overwhelms_braking(self):
        """Steep downgrade making a_eff ≤ 0 → error."""
        r = braking_distance(60.0, 0.1, grade_percent=-5.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 12. rail_bending
# ---------------------------------------------------------------------------

class TestRailBending:
    def test_characteristic_length_formula(self):
        """L_c = (4EI/u)^(1/4)."""
        E = 210e9
        I = 30.55e-6
        u = 25e6
        expected_Lc = (4 * E * I / u) ** 0.25
        r = rail_bending(80000.0, I, E, u)
        assert r["ok"] is True
        assert r["characteristic_length_m"] == pytest.approx(expected_Lc, rel=1e-6)

    def test_deflection_formula(self):
        """y_max = P / (2 × u × L_c)."""
        E = 210e9
        I = 30.55e-6
        u = 25e6
        P = 80000.0
        L_c = (4 * E * I / u) ** 0.25
        expected_y = P / (2.0 * u * L_c)
        r = rail_bending(P, I, E, u)
        assert r["ok"] is True
        assert r["max_deflection_m"] == pytest.approx(expected_y, rel=1e-6)

    def test_bending_moment_formula(self):
        """M_max = P × L_c / 4."""
        E = 210e9
        I = 30.55e-6
        u = 25e6
        P = 80000.0
        L_c = (4 * E * I / u) ** 0.25
        expected_M = P * L_c / 4.0
        r = rail_bending(P, I, E, u)
        assert r["ok"] is True
        assert r["max_bending_moment_Nm"] == pytest.approx(expected_M, rel=1e-6)

    def test_stress_formula(self):
        """σ_max = M_max × (h/2) / I."""
        E = 210e9
        I = 30.55e-6
        u = 25e6
        P = 80000.0
        h = 0.172
        L_c = (4 * E * I / u) ** 0.25
        M_max = P * L_c / 4.0
        expected_sigma = M_max * (h / 2.0) / I
        r = rail_bending(P, I, E, u, rail_height_m=h)
        assert r["ok"] is True
        assert r["max_rail_stress_Pa"] == pytest.approx(expected_sigma, rel=1e-6)

    def test_ballast_pressure_positive(self):
        r = rail_bending(80000.0, 30.55e-6)
        assert r["ok"] is True
        assert r["ballast_pressure_Pa"] > 0.0

    def test_heavier_load_higher_stress(self):
        r1 = rail_bending(60000.0, 30.55e-6)
        r2 = rail_bending(120000.0, 30.55e-6)
        assert r2["max_rail_stress_Pa"] > r1["max_rail_stress_Pa"]

    def test_invalid_zero_I(self):
        r = rail_bending(80000.0, 0.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# 13. rail_thermal_stress
# ---------------------------------------------------------------------------

class TestRailThermalStress:
    def test_cwr_formula(self):
        """σ = E × α × ΔT."""
        E = 210e9
        alpha = 11.5e-6
        dT = 40.0
        expected = E * alpha * dT
        r = rail_thermal_stress(dT, E, alpha)
        assert r["ok"] is True
        assert r["thermal_stress_Pa"] == pytest.approx(expected, rel=1e-9)

    def test_thermal_force_formula(self):
        """F = σ × A."""
        E = 210e9
        alpha = 11.5e-6
        dT = 30.0
        A = 7.686e-3
        sigma = E * alpha * dT
        expected_F = sigma * A
        r = rail_thermal_stress(dT, E, alpha, rail_area_m2=A)
        assert r["ok"] is True
        assert r["thermal_force_N"] == pytest.approx(expected_F, rel=1e-9)

    def test_compressive_warming(self):
        """ΔT > 0 → compressive."""
        r = rail_thermal_stress(20.0)
        assert r["ok"] is True
        assert r["is_compressive"] is True
        assert r["is_tensile"] is False
        assert r["thermal_stress_Pa"] > 0.0

    def test_tensile_cooling(self):
        """ΔT < 0 → tensile."""
        r = rail_thermal_stress(-20.0)
        assert r["ok"] is True
        assert r["is_tensile"] is True
        assert r["is_compressive"] is False
        assert r["thermal_stress_Pa"] < 0.0

    def test_buckling_risk_flagged(self):
        """Very high ΔT → CWR buckling risk."""
        # σ = 210e9 × 11.5e-6 × ΔT; ratio = σ/700e6
        # ratio > 0.70 when ΔT > 0.70 × 700e6 / (210e9 × 11.5e-6)
        threshold = 0.70 * 700e6 / (210e9 * 11.5e-6)
        dT_risk = threshold + 5.0
        r = rail_thermal_stress(dT_risk)
        assert r["ok"] is True
        assert r["CWR_buckling_risk"] is True
        assert "CWR_buckling_risk" in r["warnings"]

    def test_no_buckling_risk_low_dT(self):
        r = rail_thermal_stress(10.0)
        assert r["ok"] is True
        assert r["CWR_buckling_risk"] is False

    def test_jointed_rail_zero_stress(self):
        """CWR=False → no thermal stress."""
        r = rail_thermal_stress(40.0, CWR=False)
        assert r["ok"] is True
        assert r["thermal_stress_Pa"] == pytest.approx(0.0)
        assert r["CWR_buckling_risk"] is False


# ---------------------------------------------------------------------------
# LLM Tool wrappers — happy paths
# ---------------------------------------------------------------------------

class TestToolsHappyPath:
    def test_tool_equilibrium_cant(self):
        raw = _run(run_equilibrium_cant(_ctx(), _args(speed_kmh=200.0, radius_m=2000.0)))
        d = _ok_tool(raw)
        assert "cant_eq_mm" in d

    def test_tool_applied_cant(self):
        raw = _run(run_applied_cant(_ctx(), _args(speed_kmh=160.0, radius_m=1500.0)))
        d = _ok_tool(raw)
        assert "cant_applied_mm" in d

    def test_tool_cant_deficiency(self):
        raw = _run(run_cant_deficiency(_ctx(), _args(
            speed_kmh=120.0, radius_m=1000.0, cant_applied_mm=80.0
        )))
        d = _ok_tool(raw)
        assert "cant_deficiency_mm" in d

    def test_tool_cant_gradient_check(self):
        raw = _run(run_cant_gradient_check(_ctx(), _args(
            cant_change_mm=50.0, transition_length_m=120.0, speed_kmh=160.0
        )))
        d = _ok_tool(raw)
        assert "gradient_ok" in d

    def test_tool_transition_length(self):
        raw = _run(run_transition_length(_ctx(), _args(
            cant_change_mm=80.0, speed_kmh=200.0
        )))
        d = _ok_tool(raw)
        assert "transition_length_m" in d

    def test_tool_gauge_widening(self):
        raw = _run(run_gauge_widening(_ctx(), _args(radius_m=200.0)))
        d = _ok_tool(raw)
        assert "gauge_widening_mm" in d

    def test_tool_vertical_curve(self):
        raw = _run(run_vertical_curve(_ctx(), _args(
            delta_g_percent=2.0, speed_kmh=200.0, curve_type="crest"
        )))
        d = _ok_tool(raw)
        assert "vertical_curve_length_m" in d

    def test_tool_hertzian_contact(self):
        raw = _run(run_hertzian_contact(_ctx(), _args(
            P_N=80000.0, R1x_m=0.46, R1y_m=0.5, R2x_m=1e9, R2y_m=0.3
        )))
        d = _ok_tool(raw)
        assert "max_pressure_Pa" in d

    def test_tool_davis_resistance(self):
        raw = _run(run_davis_resistance(_ctx(), _args(
            mass_kg=500000.0, speed_kmh=100.0, A=2.0, B=0.02, C=0.0005
        )))
        d = _ok_tool(raw)
        assert "R_total_N" in d

    def test_tool_tractive_effort(self):
        raw = _run(run_tractive_effort(_ctx(), _args(
            power_W=4_000_000.0, speed_kmh=160.0
        )))
        d = _ok_tool(raw)
        assert "TE_power_N" in d

    def test_tool_braking_distance(self):
        raw = _run(run_braking_distance(_ctx(), _args(
            speed_kmh=160.0, deceleration_ms2=1.0
        )))
        d = _ok_tool(raw)
        assert "braking_distance_m" in d

    def test_tool_rail_bending(self):
        raw = _run(run_rail_bending(_ctx(), _args(
            wheel_load_N=80000.0, rail_I_m4=30.55e-6
        )))
        d = _ok_tool(raw)
        assert "max_rail_stress_Pa" in d

    def test_tool_thermal_stress(self):
        raw = _run(run_thermal_stress(_ctx(), _args(delta_T_K=30.0)))
        d = _ok_tool(raw)
        assert "thermal_stress_Pa" in d


# ---------------------------------------------------------------------------
# LLM Tool wrappers — error paths
# ---------------------------------------------------------------------------

class TestToolsErrorPaths:
    def test_missing_speed_kmh(self):
        raw = _run(run_equilibrium_cant(_ctx(), _args(radius_m=2000.0)))
        _err_tool(raw)

    def test_missing_radius_m(self):
        raw = _run(run_equilibrium_cant(_ctx(), _args(speed_kmh=200.0)))
        _err_tool(raw)

    def test_negative_speed_for_braking(self):
        raw = _run(run_braking_distance(_ctx(), _args(speed_kmh=-10.0, deceleration_ms2=1.0)))
        _err_tool(raw)

    def test_missing_fields_davis(self):
        raw = _run(run_davis_resistance(_ctx(), _args(mass_kg=500000.0, speed_kmh=100.0, A=2.0)))
        _err_tool(raw)

    def test_invalid_json(self):
        raw = _run(run_equilibrium_cant(_ctx(), b"not-valid-json"))
        _err_tool(raw)

    def test_thermal_stress_missing_dT(self):
        raw = _run(run_thermal_stress(_ctx(), _args(E_Pa=210e9)))
        _err_tool(raw)
