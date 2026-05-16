"""
Hermetic tests for kerf_cad_core.channel — open-channel hydraulics.

All tests are pure-Python, deterministic, and independent of OCC / DB / network.
Numeric results are verified against Chow (1959) hand-calculations or direct
algebraic derivations.

Sections covered
----------------
  flow.section_properties       — geometry for each shape
  flow.normal_depth             — Manning bisection (multiple shapes)
  flow.critical_depth           — Z-factor bisection
  flow.froude_number            — regime classification
  flow.specific_energy          — E = y + V²/2g
  flow.momentum_function        — M = Q²/gA + ȳA
  flow.hydraulic_jump           — Bélanger (rect) + general momentum
  flow.gvf_profile_type         — M/S/C/H/A classification
  flow.gvf_direct_step          — profile length sign / direction
  flow.best_hydraulic_section   — dimensional correctness
  flow.weir_broad_crested       — formula check
  flow.weir_sharp_crested       — formula check
  flow.weir_vnotch              — formula check
  flow.culvert_control          — inlet vs outlet control logic
  flow.channel_transition       — energy balance
  plugin._TOOL_MODULES          — registration check

References
----------
Chow, V.T. (1959) Open-Channel Hydraulics.  McGraw-Hill.
Henderson, F.M. (1966) Open Channel Flow.  Macmillan.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math

import pytest

from kerf_cad_core.channel.flow import (
    _G,
    _section_props,
    section_properties,
    normal_depth,
    critical_depth,
    froude_number,
    specific_energy,
    momentum_function,
    hydraulic_jump,
    gvf_profile_type,
    gvf_direct_step,
    best_hydraulic_section,
    weir_broad_crested,
    weir_sharp_crested,
    weir_vnotch,
    culvert_control,
    channel_transition,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    """Minimal stub for ProjectCtx — tools only need it to not be None."""
    class _Ctx:
        project_id = "test"
    return _Ctx()


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


REL = 1e-4   # 0.01 % relative tolerance for bisection results
STRICT = 1e-9  # strict algebraic checks


# ===========================================================================
# 1. Section properties — rectangular
# ===========================================================================

class TestSectionPropertiesRectangular:

    def test_area_correct(self):
        """A = b * y."""
        props = _section_props("rectangular", y=1.0, b=2.0)
        assert abs(props["A"] - 2.0) < STRICT

    def test_wetted_perimeter_correct(self):
        """P = b + 2y."""
        props = _section_props("rectangular", y=1.0, b=3.0)
        assert abs(props["P"] - 5.0) < STRICT

    def test_hydraulic_radius(self):
        """R = A/P = 3 / 5 = 0.6."""
        props = _section_props("rectangular", y=1.0, b=3.0)
        assert abs(props["R"] - 0.6) < STRICT

    def test_hydraulic_depth(self):
        """D_h = A/T = b*y / b = y for rectangular."""
        y, b = 1.5, 2.0
        props = _section_props("rectangular", y=y, b=b)
        assert abs(props["D_h"] - y) < STRICT

    def test_section_factor_Z(self):
        """Z = A * sqrt(D_h) = b*y * sqrt(y)."""
        y, b = 2.0, 1.5
        props = _section_props("rectangular", y=y, b=b)
        expected_Z = b * y * math.sqrt(y)
        assert abs(props["Z"] - expected_Z) < STRICT


# ===========================================================================
# 2. Section properties — trapezoidal
# ===========================================================================

class TestSectionPropertiesTrapezoidal:

    def test_area_formula(self):
        """A = (b + z*y) * y."""
        b, z, y = 2.0, 1.5, 1.0
        props = _section_props("trapezoidal", y=y, b=b, z=z)
        expected = (b + z * y) * y
        assert abs(props["A"] - expected) < STRICT

    def test_top_width(self):
        """T = b + 2*z*y."""
        b, z, y = 2.0, 1.0, 1.5
        props = _section_props("trapezoidal", y=y, b=b, z=z)
        assert abs(props["T"] - (b + 2 * z * y)) < STRICT


# ===========================================================================
# 3. Section properties — circular (partial flow)
# ===========================================================================

class TestSectionPropertiesCircular:

    def test_full_pipe_area(self):
        """At y=D: A = pi*D²/4."""
        D = 1.0
        props = _section_props("circular", y=D, D=D)
        assert abs(props["A"] - math.pi * D * D / 4.0) < 1e-6

    def test_half_full_area(self):
        """At y=D/2: A = pi*D²/8 (semicircle)."""
        D = 1.0
        props = _section_props("circular", y=D / 2.0, D=D)
        expected = math.pi * D * D / 8.0
        assert abs(props["A"] - expected) < 1e-6

    def test_zero_depth_returns_zeros(self):
        """y=0 returns all-zero properties without error."""
        props = _section_props("circular", y=0.0, D=1.0)
        assert props["A"] == 0.0
        assert props["P"] == 0.0


# ===========================================================================
# 4. Normal depth — rectangular channel (Manning)
# ===========================================================================

class TestNormalDepthRectangular:

    # Reference: B=2m, n=0.013, S=0.001, Q=1.0 m³/s
    # Solve y_n from (1/n)*B*y*(B*y/(B+2y))^(2/3)*S^0.5 = Q

    B = 2.0
    n = 0.013
    S = 0.001
    Q = 1.0

    def test_bisection_converges(self):
        result = normal_depth("rectangular", self.Q, self.S, manning_n=self.n, b=self.B)
        assert result["ok"], result.get("reason")
        assert not result["channel_full"]

    def test_manning_equation_satisfied(self):
        """Q_check(y_n) must equal Q within 0.01 %."""
        result = normal_depth("rectangular", self.Q, self.S, manning_n=self.n, b=self.B)
        y_n = result["normal_depth_m"]
        A = self.B * y_n
        P = self.B + 2.0 * y_n
        R = A / P
        Q_check = (1.0 / self.n) * A * (R ** (2.0 / 3.0)) * math.sqrt(self.S)
        assert abs(Q_check - self.Q) / self.Q < REL

    def test_subcritical_regime_gentle_slope(self):
        """Gentle slope → subcritical normal flow."""
        result = normal_depth("rectangular", 0.5, 0.0005, manning_n=0.013, b=1.0)
        assert result["ok"]
        assert result["flow_regime"] == "subcritical"

    def test_supercritical_regime_steep_slope(self):
        """Steep slope → supercritical; warning issued."""
        result = normal_depth("rectangular", 0.5, 0.05, manning_n=0.013, b=1.0)
        assert result["ok"]
        assert result["flow_regime"] == "supercritical"
        assert any("supercritical" in w for w in result["warnings"])

    def test_channel_full_when_capacity_exceeded(self):
        """Very large Q with small max_depth → channel_full flag."""
        result = normal_depth("rectangular", 100.0, 0.001, manning_n=0.013, b=0.5, max_depth_m=0.5)
        assert result["ok"]
        assert result["channel_full"]

    def test_invalid_slope_returns_error(self):
        result = normal_depth("rectangular", 1.0, -0.001, manning_n=0.013, b=2.0)
        assert result["ok"] is False

    def test_invalid_flow_returns_error(self):
        result = normal_depth("rectangular", 0.0, 0.001, manning_n=0.013, b=2.0)
        assert result["ok"] is False

    def test_chezy_normal_depth(self):
        """Chezy alternative: Q_check(y_n) must equal Q."""
        C = 50.0  # m^0.5/s
        S = 0.002
        Q = 0.8
        result = normal_depth("rectangular", Q, S, chezy_C=C, b=1.5)
        assert result["ok"], result.get("reason")
        y_n = result["normal_depth_m"]
        A = 1.5 * y_n
        P = 1.5 + 2.0 * y_n
        R = A / P
        Q_check = C * A * math.sqrt(R * S)
        assert abs(Q_check - Q) / Q < REL


# ===========================================================================
# 5. Normal depth — trapezoidal channel
# ===========================================================================

class TestNormalDepthTrapezoidal:

    B, Z, N, S, Q = 3.0, 1.5, 0.025, 0.001, 5.0

    def test_manning_equation_satisfied(self):
        result = normal_depth("trapezoidal", self.Q, self.S, manning_n=self.N, b=self.B, z=self.Z)
        assert result["ok"], result.get("reason")
        y_n = result["normal_depth_m"]
        A = (self.B + self.Z * y_n) * y_n
        P = self.B + 2.0 * y_n * math.sqrt(1.0 + self.Z * self.Z)
        R = A / P
        Q_check = (1.0 / self.N) * A * (R ** (2.0 / 3.0)) * math.sqrt(self.S)
        assert abs(Q_check - self.Q) / self.Q < REL


# ===========================================================================
# 6. Critical depth
# ===========================================================================

class TestCriticalDepth:

    def test_rectangular_hand_calc(self):
        """Rectangular: yc = (Q²/g/b²)^(1/3).  B=2m, Q=1 m³/s."""
        B = 2.0
        Q = 1.0
        yc_expected = (Q * Q / (_G * B * B)) ** (1.0 / 3.0)
        result = critical_depth("rectangular", Q, b=B)
        assert result["ok"]
        assert abs(result["critical_depth_m"] - yc_expected) / yc_expected < REL

    def test_froude_at_critical_is_one(self):
        """Fr at critical depth should be ≈ 1."""
        result = critical_depth("rectangular", 2.0, b=3.0)
        assert result["ok"]
        assert result["froude_number"] is not None
        assert abs(result["froude_number"] - 1.0) < 0.01

    def test_trapezoidal_critical_bisects_correctly(self):
        """Verify Z(yc) = Q/sqrt(g)."""
        B, Z, Q = 2.0, 1.0, 3.0
        result = critical_depth("trapezoidal", Q, b=B, z=Z)
        assert result["ok"]
        yc = result["critical_depth_m"]
        A = (B + Z * yc) * yc
        T = B + 2 * Z * yc
        D_h = A / T
        Z_sec = A * math.sqrt(D_h)
        Z_target = Q / math.sqrt(_G)
        assert abs(Z_sec - Z_target) / Z_target < REL

    def test_min_specific_energy_positive(self):
        result = critical_depth("rectangular", 1.0, b=2.0)
        assert result["ok"]
        E_min = result["min_specific_energy_m"]
        assert E_min is not None and E_min > 0.0

    def test_invalid_flow_returns_error(self):
        result = critical_depth("rectangular", -1.0, b=2.0)
        assert result["ok"] is False


# ===========================================================================
# 7. Froude number
# ===========================================================================

class TestFroudeNumber:

    def test_subcritical(self):
        """Deep, slow flow → subcritical."""
        result = froude_number("rectangular", flow_m3s=0.5, depth_m=2.0, b=2.0)
        assert result["ok"]
        assert result["froude_number"] < 1.0
        assert result["flow_regime"] == "subcritical"

    def test_supercritical(self):
        """Shallow, fast flow → supercritical."""
        result = froude_number("rectangular", flow_m3s=5.0, depth_m=0.1, b=2.0)
        assert result["ok"]
        assert result["froude_number"] > 1.0
        assert result["flow_regime"] == "supercritical"

    def test_fr_formula(self):
        """Fr = V / sqrt(g * D_h) must match manual calc."""
        Q, y, b = 2.0, 1.0, 2.0
        result = froude_number("rectangular", flow_m3s=Q, depth_m=y, b=b)
        A = b * y
        T = b
        D_h = A / T
        V = Q / A
        Fr_expected = V / math.sqrt(_G * D_h)
        assert abs(result["froude_number"] - Fr_expected) < STRICT

    def test_invalid_depth_returns_error(self):
        result = froude_number("rectangular", flow_m3s=1.0, depth_m=0.0, b=2.0)
        assert result["ok"] is False


# ===========================================================================
# 8. Specific energy
# ===========================================================================

class TestSpecificEnergy:

    def test_formula(self):
        """E = y + V²/(2g)."""
        Q, y, b = 2.0, 1.0, 2.0
        result = specific_energy("rectangular", Q, y, b=b)
        assert result["ok"]
        A = b * y
        V = Q / A
        E_expected = y + V * V / (2.0 * _G)
        assert abs(result["specific_energy_m"] - E_expected) < STRICT

    def test_velocity_head_component(self):
        Q, y, b = 3.0, 0.5, 2.0
        result = specific_energy("rectangular", Q, y, b=b)
        assert result["ok"]
        V = result["velocity_m_per_s"]
        Vh_expected = V * V / (2.0 * _G)
        assert abs(result["velocity_head_m"] - Vh_expected) < STRICT

    def test_deeper_flow_lower_velocity(self):
        """Increasing depth at same Q reduces velocity."""
        r1 = specific_energy("rectangular", 2.0, 0.5, b=2.0)
        r2 = specific_energy("rectangular", 2.0, 1.5, b=2.0)
        assert r1["ok"] and r2["ok"]
        assert r1["velocity_m_per_s"] > r2["velocity_m_per_s"]

    def test_invalid_depth_returns_error(self):
        result = specific_energy("rectangular", 1.0, -0.5, b=2.0)
        assert result["ok"] is False


# ===========================================================================
# 9. Hydraulic jump — rectangular (Bélanger equation)
# ===========================================================================

class TestHydraulicJumpRectangular:

    # Standard example: B=2m, Q=5 m³/s, y1=0.3m
    B = 2.0
    Q = 5.0
    y1 = 0.3

    def test_belanger_equation(self):
        """Rectangular jump: y2 = (y1/2)*(sqrt(1 + 8*Fr1²) - 1)."""
        result = hydraulic_jump("rectangular", self.Q, self.y1, b=self.B)
        assert result["ok"]
        V1 = self.Q / (self.B * self.y1)
        Fr1 = V1 / math.sqrt(_G * self.y1)  # D_h = y for rect
        y2_expected = 0.5 * self.y1 * (math.sqrt(1.0 + 8.0 * Fr1 * Fr1) - 1.0)
        assert abs(result["depth2_m"] - y2_expected) / y2_expected < REL

    def test_y2_greater_than_y1(self):
        """Sequent depth must be greater than upstream depth."""
        result = hydraulic_jump("rectangular", self.Q, self.y1, b=self.B)
        assert result["ok"]
        assert result["depth2_m"] > self.y1

    def test_energy_loss_positive(self):
        """Energy must be lost across the jump."""
        result = hydraulic_jump("rectangular", self.Q, self.y1, b=self.B)
        assert result["ok"]
        assert result["energy_loss_m"] > 0.0

    def test_froude2_subcritical(self):
        """Downstream Froude number should be < 1 (subcritical)."""
        result = hydraulic_jump("rectangular", self.Q, self.y1, b=self.B)
        assert result["ok"]
        assert result["froude2"] < 1.0

    def test_relative_energy_loss_in_range(self):
        """Relative energy loss must be in (0, 1)."""
        result = hydraulic_jump("rectangular", self.Q, self.y1, b=self.B)
        assert result["ok"]
        rel = result["relative_energy_loss"]
        assert 0.0 < rel < 1.0

    def test_length_estimate_positive(self):
        result = hydraulic_jump("rectangular", self.Q, self.y1, b=self.B)
        assert result["ok"]
        assert result["length_estimate_m"] > 0.0

    def test_subcritical_upstream_warning(self):
        """Deep subcritical depth: Fr1 < 1 → warning issued."""
        result = hydraulic_jump("rectangular", 0.5, 2.0, b=2.0)
        assert result["ok"]
        assert len(result["warnings"]) > 0

    def test_invalid_flow_returns_error(self):
        result = hydraulic_jump("rectangular", 0.0, 0.3, b=2.0)
        assert result["ok"] is False


# ===========================================================================
# 10. Hydraulic jump — trapezoidal (momentum bisection)
# ===========================================================================

class TestHydraulicJumpTrapezoidal:

    def test_y2_greater_than_y1(self):
        result = hydraulic_jump("trapezoidal", 4.0, 0.25, b=2.0, z=1.0)
        assert result["ok"]
        assert result["depth2_m"] > 0.25

    def test_energy_loss_positive(self):
        result = hydraulic_jump("trapezoidal", 4.0, 0.25, b=2.0, z=1.0)
        assert result["ok"]
        assert result["energy_loss_m"] > 0.0


# ===========================================================================
# 11. GVF profile type classification
# ===========================================================================

class TestGvfProfileType:

    def test_mild_M1(self):
        """Mild slope, y > yn > yc → M1."""
        result = gvf_profile_type(
            "rectangular", flow_m3s=1.0, slope=0.001, manning_n=0.013,
            depth_m=3.0, b=2.0,
        )
        assert result["ok"]
        assert result["channel_class"] == "mild"
        assert result["profile_type"] == "M1"

    def test_mild_M2(self):
        """Mild slope, yc < y < yn → M2.
        For Q=1, B=2, n=0.013, S=0.001: yn≈0.449m, yc≈0.294m.
        Choose y=0.38 (between yc and yn) → M2.
        """
        result = gvf_profile_type(
            "rectangular", flow_m3s=1.0, slope=0.001, manning_n=0.013,
            depth_m=0.38, b=2.0,
        )
        assert result["ok"]
        assert result["channel_class"] == "mild"
        assert result["profile_type"] == "M2"

    def test_steep_S1(self):
        """Steep slope, y > yc > yn → S1."""
        result = gvf_profile_type(
            "rectangular", flow_m3s=1.0, slope=0.05, manning_n=0.013,
            depth_m=2.0, b=2.0,
        )
        assert result["ok"]
        assert result["channel_class"] == "steep"
        assert result["profile_type"] == "S1"

    def test_adverse_slope_A2(self):
        """Adverse (negative) slope → A-profile."""
        result = gvf_profile_type(
            "rectangular", flow_m3s=1.0, slope=-0.001, manning_n=0.013,
            depth_m=2.0, b=2.0,
        )
        assert result["ok"]
        assert result["channel_class"] == "adverse"
        assert result["profile_type"] in ("A2", "A3")

    def test_horizontal_slope_H(self):
        """Zero slope → H-profile."""
        result = gvf_profile_type(
            "rectangular", flow_m3s=1.0, slope=0.0, manning_n=0.013,
            depth_m=2.0, b=2.0,
        )
        assert result["ok"]
        assert result["channel_class"] == "horizontal"
        assert result["profile_type"] in ("H2", "H3")

    def test_invalid_flow_returns_error(self):
        result = gvf_profile_type(
            "rectangular", flow_m3s=0.0, slope=0.001, manning_n=0.013,
            depth_m=1.0, b=2.0,
        )
        assert result["ok"] is False


# ===========================================================================
# 12. GVF direct-step profile
# ===========================================================================

class TestGvfDirectStep:

    def test_returns_correct_number_of_steps(self):
        result = gvf_direct_step(
            "rectangular", 1.0, 0.001, 0.013,
            depth_start_m=0.8, depth_end_m=1.2, n_steps=10, b=2.0,
        )
        assert result["ok"]
        assert len(result["profile"]) == 10

    def test_total_length_finite(self):
        result = gvf_direct_step(
            "rectangular", 1.0, 0.001, 0.013,
            depth_start_m=0.8, depth_end_m=1.4, n_steps=50, b=2.0,
        )
        assert result["ok"]
        assert math.isfinite(result["total_length_m"])

    def test_first_station_at_zero(self):
        result = gvf_direct_step(
            "rectangular", 1.0, 0.001, 0.013,
            depth_start_m=1.0, depth_end_m=1.5, n_steps=5, b=2.0,
        )
        assert result["ok"]
        assert result["profile"][0]["x_m"] == pytest.approx(0.0)

    def test_profile_has_required_fields(self):
        result = gvf_direct_step(
            "rectangular", 1.0, 0.001, 0.013,
            depth_start_m=1.0, depth_end_m=1.3, n_steps=5, b=2.0,
        )
        assert result["ok"]
        for row in result["profile"]:
            for key in ("x_m", "depth_m", "specific_energy_m", "velocity_m_per_s",
                        "froude_number", "friction_slope"):
                assert key in row

    def test_invalid_n_steps_returns_error(self):
        result = gvf_direct_step(
            "rectangular", 1.0, 0.001, 0.013,
            depth_start_m=1.0, depth_end_m=1.3, n_steps=1, b=2.0,
        )
        assert result["ok"] is False


# ===========================================================================
# 13. Best hydraulic section
# ===========================================================================

class TestBestHydraulicSection:

    def test_rectangular_b_equals_2y(self):
        """Best rectangular section: b = 2*y."""
        result = best_hydraulic_section("rectangular", 1.0, 0.001, 0.013)
        assert result["ok"]
        b = result["optimal_bottom_width_m"]
        y = result["optimal_depth_m"]
        assert abs(b - 2.0 * y) / (2.0 * y) < REL

    def test_rectangular_flow_satisfied(self):
        """Manning Q at optimal dimensions must equal design Q."""
        Q = 2.0
        S = 0.001
        n = 0.013
        result = best_hydraulic_section("rectangular", Q, S, n)
        assert result["ok"]
        y = result["optimal_depth_m"]
        b = result["optimal_bottom_width_m"]
        A = b * y
        P = b + 2 * y
        R = A / P
        Q_check = (1.0 / n) * A * (R ** (2.0 / 3.0)) * math.sqrt(S)
        assert abs(Q_check - Q) / Q < REL

    def test_trapezoidal_side_slope(self):
        """Best trapezoidal z = 1/sqrt(3) ≈ 0.5774."""
        result = best_hydraulic_section("trapezoidal", 3.0, 0.001, 0.025)
        assert result["ok"]
        z = result["optimal_side_slope"]
        assert abs(z - 1.0 / math.sqrt(3.0)) < 1e-6

    def test_triangular_side_slope_45(self):
        """Best triangular z = 1 (45°)."""
        result = best_hydraulic_section("triangular", 1.0, 0.001, 0.013)
        assert result["ok"]
        assert abs(result["optimal_side_slope"] - 1.0) < STRICT

    def test_circular_y_over_D_ratio(self):
        """Best circular: y/D ≈ 0.938."""
        result = best_hydraulic_section("circular", 1.0, 0.001, 0.013)
        assert result["ok"]
        ratio = result["optimal_depth_m"] / result["optimal_diameter_m"]
        assert abs(ratio - 0.938) < 1e-6

    def test_invalid_slope_returns_error(self):
        result = best_hydraulic_section("rectangular", 1.0, 0.0, 0.013)
        assert result["ok"] is False


# ===========================================================================
# 14. Weirs
# ===========================================================================

class TestWeirBroadCrested:

    def test_formula_chow_critical_flow(self):
        """Chow (1959): Q = Cd·(2/3)·√(2g/3)·L·H^(3/2).

        The ideal critical-flow coefficient (2/3)·√(2g/3) = 1.7046 (SI).
        """
        H, L, Cd = 0.5, 3.0, 0.93
        result = weir_broad_crested(H, L, Cd)
        assert result["ok"]
        C_ideal = (2.0 / 3.0) * math.sqrt(2.0 * _G / 3.0)
        Q_expected = Cd * C_ideal * L * H ** 1.5
        assert abs(result["discharge_m3s"] - Q_expected) < STRICT
        assert abs(C_ideal - 1.7046) < 1e-3

    def test_ideal_weir_chow_reference(self):
        """Chow Ex.: ideal broad-crested weir (Cd=1.0), L=1 m, H=1 m →
        Q = 1.705 m³/s (the textbook ideal critical-flow result)."""
        result = weir_broad_crested(1.0, 1.0, 1.0)
        assert result["ok"]
        assert abs(result["discharge_m3s"] - 1.7046) < 1e-2

    def test_henderson_typical_coefficient(self):
        """Henderson (1966) §6-2: a real broad-crested weir with
        Cd≈0.85, L=4 m, H=0.6 m → Q = 0.85·1.705·4·0.6^1.5 ≈ 2.694 m³/s."""
        result = weir_broad_crested(0.6, 4.0, 0.85)
        assert result["ok"]
        Q_expected = 0.85 * 1.7046 * 4.0 * 0.6 ** 1.5
        assert abs(result["discharge_m3s"] - Q_expected) < 1e-2
        # Lumped coefficient C = Cd·1.705 reported for classic form
        assert abs(result["discharge_coefficient_Cd_full"] - 0.85 * 1.7046) < 1e-3

    def test_head_sensitivity(self):
        """Q ∝ H^1.5: doubling H multiplies Q by 2^1.5."""
        Q1 = weir_broad_crested(1.0, 2.0, 0.93)["discharge_m3s"]
        Q2 = weir_broad_crested(2.0, 2.0, 0.93)["discharge_m3s"]
        assert abs(Q2 / Q1 - 2.0 ** 1.5) < 1e-9

    def test_dimensionless_Cd_above_one_rejected(self):
        """Cd is now strictly the dimensionless coefficient (0, 1]."""
        result = weir_broad_crested(0.5, 3.0, 1.7)
        assert result["ok"] is False

    def test_invalid_head_returns_error(self):
        result = weir_broad_crested(-0.1, 1.0)
        assert result["ok"] is False


class TestWeirSharpCrested:

    def test_formula(self):
        """Q = (2/3) * Cd * L * sqrt(2g) * H^1.5."""
        H, L, Cd = 0.4, 2.0, 0.611
        result = weir_sharp_crested(H, L, Cd)
        assert result["ok"]
        Q_expected = (2.0 / 3.0) * Cd * L * math.sqrt(2.0 * _G) * H ** 1.5
        assert abs(result["discharge_m3s"] - Q_expected) < STRICT

    def test_length_proportionality(self):
        """Q ∝ L for same head."""
        Q1 = weir_sharp_crested(0.5, 1.0)["discharge_m3s"]
        Q2 = weir_sharp_crested(0.5, 2.0)["discharge_m3s"]
        assert abs(Q2 / Q1 - 2.0) < 1e-9

    def test_invalid_Cd_returns_error(self):
        result = weir_sharp_crested(0.5, 2.0, Cd=1.5)
        assert result["ok"] is False


class TestWeirVnotch:

    def test_formula_90deg(self):
        """Q = (8/15) * Cd * tan(45°) * sqrt(2g) * H^2.5."""
        H, Cd, theta = 0.3, 0.611, 90.0
        result = weir_vnotch(H, theta, Cd)
        assert result["ok"]
        Q_expected = (8.0 / 15.0) * Cd * math.tan(math.radians(theta / 2.0)) * math.sqrt(2.0 * _G) * H ** 2.5
        assert abs(result["discharge_m3s"] - Q_expected) < STRICT

    def test_H_exponent_2p5(self):
        """Q ∝ H^2.5: doubling H multiplies Q by 2^2.5."""
        Q1 = weir_vnotch(0.5, 90.0)["discharge_m3s"]
        Q2 = weir_vnotch(1.0, 90.0)["discharge_m3s"]
        assert abs(Q2 / Q1 - 2.0 ** 2.5) < 1e-9

    def test_60deg_notch_lower_than_90deg(self):
        """60° notch discharges less than 90° at same head."""
        Q60 = weir_vnotch(0.5, 60.0)["discharge_m3s"]
        Q90 = weir_vnotch(0.5, 90.0)["discharge_m3s"]
        assert Q60 < Q90

    def test_invalid_angle_returns_error(self):
        result = weir_vnotch(0.3, notch_angle_deg=0.0)
        assert result["ok"] is False


# ===========================================================================
# 15. Culvert control
# ===========================================================================

class TestCulvertControl:

    def test_returns_ok(self):
        result = culvert_control(
            diameter_m=0.9, length_m=20.0, slope=0.02,
            manning_n=0.013, headwater_m=1.5,
        )
        assert result["ok"]

    def test_capacity_is_minimum_of_inlet_outlet(self):
        result = culvert_control(
            diameter_m=0.9, length_m=20.0, slope=0.02,
            manning_n=0.013, headwater_m=1.5,
        )
        assert result["ok"]
        Q_cap = result["capacity_m3s"]
        assert Q_cap == min(result["inlet_control_Q_m3s"], result["outlet_control_Q_m3s"])

    def test_controlling_condition_label(self):
        result = culvert_control(
            diameter_m=0.9, length_m=20.0, slope=0.02,
            manning_n=0.013, headwater_m=1.5,
        )
        assert result["ok"]
        assert result["controlling_condition"] in ("inlet", "outlet")

    def test_larger_head_gives_higher_capacity(self):
        r1 = culvert_control(0.6, 15.0, 0.01, 0.013, 0.8)
        r2 = culvert_control(0.6, 15.0, 0.01, 0.013, 1.6)
        assert r1["ok"] and r2["ok"]
        assert r2["capacity_m3s"] > r1["capacity_m3s"]

    def test_invalid_diameter_returns_error(self):
        result = culvert_control(0.0, 10.0, 0.01, 0.013, 1.0)
        assert result["ok"] is False

    def test_tailwater_warning_if_submerged(self):
        result = culvert_control(
            diameter_m=0.6, length_m=10.0, slope=0.01,
            manning_n=0.013, headwater_m=1.5, tailwater_m=1.0,
        )
        assert result["ok"]
        assert any("tailwater" in w.lower() for w in result["warnings"])


# ===========================================================================
# 16. Channel transition
# ===========================================================================

class TestChannelTransition:

    def test_expansion_returns_ok(self):
        """Flow expands: wide → wider channel."""
        result = channel_transition(
            "rectangular", 2.0, 1.0, "rectangular",
            b=2.0, b_2=3.0,
        )
        assert result["ok"]

    def test_transition_type_expansion(self):
        """Wider downstream → velocity decreases → expansion."""
        result = channel_transition(
            "rectangular", 2.0, 1.0, "rectangular",
            b=1.0, b_2=3.0,
        )
        assert result["ok"]
        assert result["transition_type"] == "expansion"

    def test_energy_decreases_with_loss(self):
        """Energy at section 2 must be ≤ energy at section 1."""
        result = channel_transition(
            "rectangular", 2.0, 1.0, "rectangular",
            b=2.0, b_2=4.0,
        )
        assert result["ok"]
        assert result["energy2_m"] <= result["energy1_m"] + 1e-10

    def test_invalid_flow_returns_error(self):
        result = channel_transition("rectangular", 0.0, 1.0, "rectangular", b=2.0)
        assert result["ok"] is False

    def test_invalid_depth_returns_error(self):
        result = channel_transition("rectangular", 1.0, -0.5, "rectangular", b=2.0)
        assert result["ok"] is False


# ===========================================================================
# 16b. CITABLE Chow (1959) "Open-Channel Hydraulics" reference cases
#
# Each value below is taken from, or derived from, a worked example or
# closed-form result in Chow, V.T. (1959) Open-Channel Hydraulics
# (McGraw-Hill), cross-checked with Henderson (1966) Open Channel Flow.
# These are externally citable, not self-consistency round-trips.
# ===========================================================================

class TestChowReferenceCases:

    def test_chow_example_5_1_trapezoidal_normal_depth(self):
        """Chow (1959) Example 5-1: trapezoidal channel, b = 20 ft,
        side slope z = 2, n = 0.025, S₀ = 0.0016, Q = 400 cfs.
        Chow's tabulated answer is the normal depth yₙ ≈ 3.36 ft.

        Worked in SI here: b = 6.096 m, Q = 11.327 m³/s.
        """
        b = 20.0 * 0.3048
        Q = 400.0 * 0.0283168
        res = normal_depth("trapezoidal", Q, 0.0016, manning_n=0.025, b=b, z=2.0)
        assert res["ok"], res.get("reason")
        yn_ft = res["normal_depth_m"] / 0.3048
        assert abs(yn_ft - 3.36) < 0.02

    def test_rectangular_critical_depth_closed_form(self):
        """Chow §3-7: for a rectangular channel the critical depth has the
        closed form yc = (q²/g)^(1/3) with q = Q/b.  b = 3 m, Q = 10 m³/s
        → yc = ((10/3)²/9.80665)^(1/3) ≈ 1.0425 m."""
        b, Q = 3.0, 10.0
        q = Q / b
        yc_expected = (q * q / _G) ** (1.0 / 3.0)
        res = critical_depth("rectangular", Q, b=b)
        assert res["ok"]
        assert abs(res["critical_depth_m"] - yc_expected) < 1e-3
        assert abs(yc_expected - 1.0425) < 1e-3

    def test_belanger_sequent_depth_henderson(self):
        """Henderson (1966) §3 / Chow §15-2 Bélanger equation.
        Rectangular, q = 4 m²/s, y₁ = 0.5 m (supercritical).
        V₁ = 8 m/s, Fr₁ = 8/√(g·0.5) ≈ 3.613,
        y₂ = (y₁/2)(√(1+8Fr₁²) − 1) ≈ 2.317 m."""
        b, Q, y1 = 1.0, 4.0, 0.5
        res = hydraulic_jump("rectangular", Q, y1, b=b)
        assert res["ok"]
        V1 = Q / (b * y1)
        Fr1 = V1 / math.sqrt(_G * y1)
        y2_expected = 0.5 * y1 * (math.sqrt(1.0 + 8.0 * Fr1 * Fr1) - 1.0)
        assert abs(res["depth2_m"] - y2_expected) < 1e-4
        assert abs(res["depth2_m"] - 2.3168) < 2e-3

    def test_belanger_energy_loss_closed_form(self):
        """Chow Eq. 15-4: hydraulic-jump energy loss
        ΔE = (y₂ − y₁)³ / (4·y₁·y₂).  For q = 4 m²/s, y₁ = 0.5 m the
        closed-form loss is ≈ 1.294 m."""
        b, Q, y1 = 1.0, 4.0, 0.5
        res = hydraulic_jump("rectangular", Q, y1, b=b)
        assert res["ok"]
        y2 = res["depth2_m"]
        dE_expected = (y2 - y1) ** 3 / (4.0 * y1 * y2)
        assert abs(res["energy_loss_m"] - dE_expected) < 1e-4
        assert abs(res["energy_loss_m"] - 1.2943) < 2e-3

    def test_broad_crested_weir_chow_ideal(self):
        """Chow §14 / Henderson §6-2: the ideal broad-crested weir
        (Cd = 1) discharge is Q = (2/3)·√(2g/3)·L·H^(3/2) ≈ 1.705·L·H^(3/2).
        For L = 1 m, H = 1 m the textbook ideal result is Q ≈ 1.705 m³/s."""
        res = weir_broad_crested(1.0, 1.0, 1.0)
        assert res["ok"]
        assert abs(res["discharge_m3s"] - 1.7046) < 5e-3

    def test_best_hydraulic_rectangular_chow(self):
        """Chow §7-6: the most efficient rectangular section satisfies
        b = 2y and R = y/2 (half of a square / half-hexagon family)."""
        res = best_hydraulic_section("rectangular", 2.0, 0.001, 0.013)
        assert res["ok"]
        b = res["optimal_bottom_width_m"]
        y = res["optimal_depth_m"]
        assert abs(b - 2.0 * y) < 1e-6 * (2.0 * y)
        assert abs(res["hydraulic_radius_m"] - y / 2.0) < 1e-6 * y

    def test_best_hydraulic_trapezoidal_chow_half_hexagon(self):
        """Chow §7-6: the most efficient trapezoidal section is half of a
        regular hexagon — side slope z = 1/√3 ≈ 0.5774 and R = y/2."""
        res = best_hydraulic_section("trapezoidal", 3.0, 0.001, 0.025)
        assert res["ok"]
        assert abs(res["optimal_side_slope"] - 1.0 / math.sqrt(3.0)) < 1e-6
        y = res["optimal_depth_m"]
        assert abs(res["hydraulic_radius_m"] - y / 2.0) < 1e-6 * y


# ===========================================================================
# 17. Tool wrappers (async)
# ===========================================================================

class TestToolWrappers:

    def test_tool_normal_depth_ok(self):
        from kerf_cad_core.channel.tools import run_channel_normal_depth
        ctx = _ctx()
        raw = _run(run_channel_normal_depth(ctx, _args(
            shape="rectangular", flow_m3s=1.0, slope=0.001, manning_n=0.013, b=2.0
        )))
        d = json.loads(raw)
        assert d.get("ok"), f"Expected ok, got: {d}"
        assert d["normal_depth_m"] > 0

    def test_tool_normal_depth_bad_json(self):
        from kerf_cad_core.channel.tools import run_channel_normal_depth
        ctx = _ctx()
        raw = _run(run_channel_normal_depth(ctx, b"not json {{{"))
        d = json.loads(raw)
        assert d.get("code") == "BAD_ARGS" or d.get("ok") is False

    def test_tool_critical_depth_ok(self):
        from kerf_cad_core.channel.tools import run_channel_critical_depth
        ctx = _ctx()
        raw = _run(run_channel_critical_depth(ctx, _args(shape="rectangular", flow_m3s=2.0, b=2.0)))
        d = json.loads(raw)
        assert d.get("ok"), f"Expected ok, got: {d}"
        assert d["critical_depth_m"] > 0

    def test_tool_hydraulic_jump_ok(self):
        from kerf_cad_core.channel.tools import run_channel_hydraulic_jump
        ctx = _ctx()
        raw = _run(run_channel_hydraulic_jump(ctx, _args(
            shape="rectangular", flow_m3s=5.0, depth1_m=0.3, b=2.0
        )))
        d = json.loads(raw)
        assert d.get("ok"), f"Expected ok, got: {d}"
        assert d["depth2_m"] > d["depth1_m"]

    def test_tool_weir_vnotch_ok(self):
        from kerf_cad_core.channel.tools import run_channel_weir_vnotch
        ctx = _ctx()
        raw = _run(run_channel_weir_vnotch(ctx, _args(head_m=0.5)))
        d = json.loads(raw)
        assert d.get("ok"), f"Expected ok, got: {d}"
        assert d["discharge_m3s"] > 0

    def test_tool_culvert_control_ok(self):
        from kerf_cad_core.channel.tools import run_channel_culvert_control
        ctx = _ctx()
        raw = _run(run_channel_culvert_control(ctx, _args(
            diameter_m=0.9, length_m=20.0, slope=0.02,
            manning_n=0.013, headwater_m=1.5,
        )))
        d = json.loads(raw)
        assert d.get("ok"), f"Expected ok, got: {d}"
        assert d["capacity_m3s"] > 0

    def test_tool_best_section_rectangular(self):
        from kerf_cad_core.channel.tools import run_channel_best_hydraulic_section
        ctx = _ctx()
        raw = _run(run_channel_best_hydraulic_section(ctx, _args(
            shape="rectangular", flow_m3s=2.0, slope=0.001, manning_n=0.013,
        )))
        d = json.loads(raw)
        assert d.get("ok"), f"Expected ok, got: {d}"
        assert "optimal_depth_m" in d
        assert "optimal_bottom_width_m" in d

    def test_tool_missing_required_field(self):
        from kerf_cad_core.channel.tools import run_channel_normal_depth
        ctx = _ctx()
        raw = _run(run_channel_normal_depth(ctx, _args(shape="rectangular", slope=0.001)))
        d = json.loads(raw)
        assert d.get("ok") is False
        assert "reason" in d


# ===========================================================================
# 18. Plugin registration
# ===========================================================================

def test_plugin_includes_channel_tools():
    """plugin._TOOL_MODULES must include channel.tools."""
    from kerf_cad_core.plugin import _TOOL_MODULES
    assert "kerf_cad_core.channel.tools" in _TOOL_MODULES
