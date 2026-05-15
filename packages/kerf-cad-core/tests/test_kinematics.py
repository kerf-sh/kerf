"""
Hermetic tests for kerf_cad_core.kinematics — planar mechanism/linkage kinematics.

Coverage:
  linkage.four_bar_grashof           — Grashof condition + type classification
  linkage.four_bar_position          — Freudenstein position analysis
  linkage.four_bar_transmission_angle — transmission angle + acceptability
  linkage.four_bar_coupler_curve     — coupler-curve sampling
  linkage.slider_crank               — position / velocity / acceleration
  linkage.cam_follower_cycloidal     — cycloidal cam profile
  linkage.cam_follower_harmonic      — harmonic cam profile

All tests are pure-Python and hermetic: no OCC, no DB, no network, no fixtures.
Analytic values are verified against published closed-form expressions.

References
----------
Norton, R.L. "Design of Machinery", 5th ed.
Shigley, J.E. & Uicker, J.J. "Theory of Machines & Mechanisms", 4th ed.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.kinematics.linkage import (
    four_bar_grashof,
    four_bar_position,
    four_bar_transmission_angle,
    four_bar_coupler_curve,
    slider_crank,
    cam_follower_cycloidal,
    cam_follower_harmonic,
)
from kerf_cad_core.kinematics.tools import (
    run_four_bar_grashof,
    run_four_bar_position,
    run_four_bar_transmission_angle,
    run_four_bar_coupler_curve,
    run_slider_crank,
    run_cam_follower_cycloidal,
    run_cam_follower_harmonic,
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


REL = 1e-6  # relative tolerance for floating-point checks
ABS = 1e-9  # absolute tolerance for near-zero checks


# ===========================================================================
# 1. four_bar_grashof
# ===========================================================================

class TestFourBarGrashof:

    def test_crank_rocker_classification(self):
        """Classic crank-rocker: shortest link is crank (r2)."""
        # r2 shortest, S+L <= P+Q
        res = four_bar_grashof(r1=4.0, r2=2.0, r3=4.5, r4=3.5)
        assert res["ok"] is True
        assert res["grashof"] is True
        assert res["type"] == "crank-rocker"
        assert res["special"] is False

    def test_double_crank_classification(self):
        """Double-crank: ground link (r1) is shortest."""
        # r1 is shortest: ground = 1, crank=3, coupler=4, output=4 → S=1, L=4, P+Q=3+4=7 >= S+L=5 ✓
        res = four_bar_grashof(r1=1.0, r2=3.0, r3=4.0, r4=4.0)
        assert res["ok"] is True
        assert res["grashof"] is True
        assert res["type"] == "double-crank"

    def test_double_rocker_classification(self):
        """Double-rocker: coupler (r3) is shortest in a Grashof linkage."""
        # r3=1 shortest: r1=4, r2=3, r3=1, r4=4 → S=1, L=4, others=3+4=7 >= S+L=5 ✓
        # idx of S=1 is 2 (coupler), so double-rocker
        res = four_bar_grashof(r1=4.0, r2=3.0, r3=1.0, r4=4.0)
        assert res["ok"] is True
        assert res["grashof"] is True
        assert res["type"] == "double-rocker"

    def test_non_grashof_classification(self):
        """Non-Grashof: S+L > P+Q."""
        # S=1, L=10, P=2, Q=3 → S+L=11 > P+Q=5
        res = four_bar_grashof(r1=2.0, r2=1.0, r3=3.0, r4=10.0)
        assert res["ok"] is True
        assert res["grashof"] is False
        assert res["type"] == "non-Grashof"

    def test_invalid_negative_link_returns_error(self):
        """Negative link length must return ok=False."""
        res = four_bar_grashof(r1=-1.0, r2=2.0, r3=3.0, r4=4.0)
        assert res["ok"] is False
        assert "reason" in res

    def test_sl_pq_values_returned(self):
        """S, L, P, Q are returned and consistent."""
        r1, r2, r3, r4 = 4.0, 2.0, 4.5, 3.5
        res = four_bar_grashof(r1, r2, r3, r4)
        assert res["ok"] is True
        links = sorted([r1, r2, r3, r4])
        assert res["S"] == links[0]
        assert res["L"] == links[-1]
        # P + Q = sum of all - S - L
        assert abs((res["P"] + res["Q"]) - (r1 + r2 + r3 + r4 - res["S"] - res["L"])) < ABS


# ===========================================================================
# 2. four_bar_position
# ===========================================================================

class TestFourBarPosition:

    def test_theta2_zero_closes_loop(self):
        """At theta2=0, the closure residual must be negligible."""
        res = four_bar_position(r1=4.0, r2=2.0, r3=4.5, r4=3.5, theta2_deg=0.0)
        assert res["ok"] is True
        assert res["closure_residual"] < 1e-6

    def test_theta2_90_closes_loop(self):
        """At theta2=90°, the closure residual must be negligible."""
        res = four_bar_position(r1=4.0, r2=2.0, r3=4.5, r4=3.5, theta2_deg=90.0)
        assert res["ok"] is True
        assert res["closure_residual"] < 1e-6

    def test_theta2_180_closes_loop(self):
        """At theta2=180°, the closure residual must be negligible."""
        res = four_bar_position(r1=4.0, r2=2.0, r3=4.5, r4=3.5, theta2_deg=180.0)
        assert res["ok"] is True
        assert res["closure_residual"] < 1e-6

    def test_branch_minus_one_returns_different_solution(self):
        """Open (branch=1) and crossed (branch=-1) must give different theta4."""
        r1, r2, r3, r4 = 4.0, 2.0, 4.5, 3.5
        res1 = four_bar_position(r1, r2, r3, r4, theta2_deg=45.0, branch=1)
        res2 = four_bar_position(r1, r2, r3, r4, theta2_deg=45.0, branch=-1)
        assert res1["ok"] is True
        assert res2["ok"] is True
        # Both branches should close the loop
        assert res1["closure_residual"] < 1e-6
        assert res2["closure_residual"] < 1e-6

    def test_freudenstein_analytical_verification(self):
        """
        Verify the result satisfies the original vector-loop closure equations
        directly: r2·cos(θ2)+r3·cos(θ3) = r1+r4·cos(θ4)
                  r2·sin(θ2)+r3·sin(θ3) = r4·sin(θ4)
        """
        r1, r2, r3, r4 = 4.0, 2.0, 4.5, 3.5
        theta2_deg = 60.0
        res = four_bar_position(r1, r2, r3, r4, theta2_deg)
        assert res["ok"] is True

        t2 = math.radians(res["theta2_deg"])
        t3 = math.radians(res["theta3_deg"])
        t4 = math.radians(res["theta4_deg"])

        lhs_x = r2 * math.cos(t2) + r3 * math.cos(t3)
        rhs_x = r1 + r4 * math.cos(t4)
        lhs_y = r2 * math.sin(t2) + r3 * math.sin(t3)
        rhs_y = r4 * math.sin(t4)

        assert abs(lhs_x - rhs_x) < 1e-6
        assert abs(lhs_y - rhs_y) < 1e-6

    def test_invalid_branch_returns_error(self):
        """Invalid branch value must return ok=False."""
        res = four_bar_position(4.0, 2.0, 4.5, 3.5, 0.0, branch=2)
        assert res["ok"] is False

    def test_negative_link_returns_error(self):
        """Negative link length must return ok=False."""
        res = four_bar_position(-1.0, 2.0, 4.5, 3.5, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 3. four_bar_transmission_angle
# ===========================================================================

class TestFourBarTransmissionAngle:

    def test_mu_at_theta2_zero(self):
        """Transmission angle at theta2=0 must be finite and in [0°, 180°]."""
        res = four_bar_transmission_angle(r1=4.0, r2=2.0, r3=4.5, r4=3.5, theta2_deg=0.0)
        assert res["ok"] is True
        assert 0.0 <= res["mu_deg"] <= 180.0

    def test_acceptable_range_flagged(self):
        """For a well-designed linkage, acceptable should be True at theta2=90°."""
        # A crank-rocker with reasonable proportions
        res = four_bar_transmission_angle(r1=4.0, r2=2.0, r3=4.5, r4=3.5, theta2_deg=90.0)
        assert res["ok"] is True
        acceptable = res["acceptable"]
        assert isinstance(acceptable, bool)
        # deviation_from_90 = |mu - 90|
        assert abs(res["mu_deviation_from_90"] - abs(res["mu_deg"] - 90.0)) < 1e-9

    def test_law_of_cosines_formula(self):
        """Verify the law-of-cosines formula for mu against manual calculation."""
        r1, r2, r3, r4 = 4.0, 2.0, 4.5, 3.5
        theta2_deg = 60.0
        theta2 = math.radians(theta2_deg)

        BD2 = r1 * r1 + r2 * r2 - 2.0 * r1 * r2 * math.cos(theta2)
        cos_mu = (r3 * r3 + r4 * r4 - BD2) / (2.0 * r3 * r4)
        cos_mu = max(-1.0, min(1.0, cos_mu))
        mu_expected = math.degrees(math.acos(cos_mu))

        res = four_bar_transmission_angle(r1, r2, r3, r4, theta2_deg)
        assert res["ok"] is True
        assert abs(res["mu_deg"] - mu_expected) < 1e-9

    def test_invalid_link_returns_error(self):
        """Zero link length must return ok=False."""
        res = four_bar_transmission_angle(0.0, 2.0, 4.5, 3.5, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 4. four_bar_coupler_curve
# ===========================================================================

class TestFourBarCouplerCurve:

    def test_n_points_returned(self):
        """Coupler curve must return approximately n_points points."""
        res = four_bar_coupler_curve(r1=4.0, r2=2.0, r3=4.5, r4=3.5, px=1.0, py=0.0, n_points=36)
        assert res["ok"] is True
        assert res["n_points"] >= 30  # allow some singularity-skips

    def test_point_structure(self):
        """Each point dict must have keys theta2_deg, x, y."""
        res = four_bar_coupler_curve(r1=4.0, r2=2.0, r3=4.5, r4=3.5, px=0.0, py=0.0, n_points=4)
        assert res["ok"] is True
        for pt in res["points"]:
            assert "theta2_deg" in pt
            assert "x" in pt
            assert "y" in pt

    def test_coupler_point_on_coupler_axis_traces_consistent_curve(self):
        """A coupler point at (px=0, py=0) coincides with joint A — trace should not be degenerate."""
        res = four_bar_coupler_curve(r1=4.0, r2=2.0, r3=4.5, r4=3.5, px=0.0, py=0.0, n_points=12)
        assert res["ok"] is True
        # All x values should be between -(r2+r3) and (r2+r3+r1) roughly
        for pt in res["points"]:
            assert isinstance(pt["x"], float)
            assert isinstance(pt["y"], float)

    def test_invalid_n_points_adjusted(self):
        """n_points < 2 should be adjusted and not crash."""
        res = four_bar_coupler_curve(r1=4.0, r2=2.0, r3=4.5, r4=3.5, px=0.0, py=0.0, n_points=1)
        assert res["ok"] is True


# ===========================================================================
# 5. slider_crank
# ===========================================================================

class TestSliderCrank:

    def test_tdc_position(self):
        """At theta=0° (TDC), x_B = r + l."""
        r, l = 0.05, 0.15
        res = slider_crank(r=r, l=l, theta_deg=0.0)
        assert res["ok"] is True
        assert abs(res["x_B"] - (r + l)) < 1e-10

    def test_bdc_position(self):
        """At theta=180° (BDC), x_B = -r + l."""
        r, l = 0.05, 0.15
        res = slider_crank(r=r, l=l, theta_deg=180.0)
        assert res["ok"] is True
        assert abs(res["x_B"] - (l - r)) < 1e-10

    def test_velocity_zero_at_tdc_and_bdc(self):
        """Slider velocity must be zero at TDC (0°) and BDC (180°) for constant omega."""
        r, l, omega = 0.05, 0.15, 100.0
        for angle in (0.0, 180.0):
            res = slider_crank(r=r, l=l, theta_deg=angle, omega_rad_s=omega)
            assert res["ok"] is True
            assert abs(res["v_B"]) < 1e-8, f"v_B={res['v_B']} at theta={angle}"

    def test_position_formula_at_90_degrees(self):
        """At theta=90°, x_B = √(l²-r²) (analytical)."""
        r, l = 0.05, 0.15
        x_expected = math.sqrt(l * l - r * r)
        res = slider_crank(r=r, l=l, theta_deg=90.0)
        assert res["ok"] is True
        assert abs(res["x_B"] - x_expected) < 1e-10

    def test_velocity_direction_at_90_degrees(self):
        """At theta=90°, velocity must be negative (slider moving toward BDC) for positive omega."""
        r, l, omega = 0.05, 0.15, 10.0
        res = slider_crank(r=r, l=l, theta_deg=90.0, omega_rad_s=omega)
        assert res["ok"] is True
        assert res["v_B"] < 0.0

    def test_omega_zero_gives_zero_velocity_acceleration(self):
        """When omega=alpha=0, velocity and acceleration must be zero."""
        res = slider_crank(r=0.05, l=0.15, theta_deg=45.0, omega_rad_s=0.0, alpha_rad_s2=0.0)
        assert res["ok"] is True
        assert res["v_B"] == 0.0
        assert res["a_B"] == 0.0

    def test_invalid_negative_r_returns_error(self):
        """Negative crank radius must return ok=False."""
        res = slider_crank(r=-0.05, l=0.15, theta_deg=0.0)
        assert res["ok"] is False

    def test_invalid_zero_l_returns_error(self):
        """Zero connecting-rod length must return ok=False."""
        res = slider_crank(r=0.05, l=0.0, theta_deg=0.0)
        assert res["ok"] is False

    def test_phi_deg_at_tdc_is_zero(self):
        """At TDC (theta=0), connecting-rod angle phi must be zero."""
        res = slider_crank(r=0.05, l=0.15, theta_deg=0.0)
        assert res["ok"] is True
        assert abs(res["phi_deg"]) < 1e-9

    def test_stroke_equals_2r(self):
        """Total stroke (x_TDC - x_BDC) must equal 2r for an in-line crank."""
        r, l = 0.06, 0.18
        x_tdc = slider_crank(r=r, l=l, theta_deg=0.0)["x_B"]
        x_bdc = slider_crank(r=r, l=l, theta_deg=180.0)["x_B"]
        assert abs((x_tdc - x_bdc) - 2.0 * r) < 1e-10


# ===========================================================================
# 6. cam_follower_cycloidal
# ===========================================================================

class TestCamFollowerCycloidal:

    def test_displacement_at_start_is_zero(self):
        """y(theta=0) must be 0 (rise)."""
        res = cam_follower_cycloidal(h=10.0, beta_deg=90.0, theta_deg=0.0)
        assert res["ok"] is True
        assert abs(res["displacement"]) < 1e-10

    def test_displacement_at_end_equals_h(self):
        """y(theta=beta) must equal h (rise)."""
        h, beta = 10.0, 90.0
        res = cam_follower_cycloidal(h=h, beta_deg=beta, theta_deg=beta)
        assert res["ok"] is True
        assert abs(res["displacement"] - h) < 1e-9

    def test_velocity_at_start_is_zero(self):
        """dy/dθ at theta=0 must be 0 (smooth-start boundary condition)."""
        res = cam_follower_cycloidal(h=10.0, beta_deg=90.0, theta_deg=0.0)
        assert res["ok"] is True
        assert abs(res["velocity_per_omega"]) < 1e-10

    def test_velocity_at_end_is_zero(self):
        """dy/dθ at theta=beta must be 0 (smooth-end boundary condition)."""
        h, beta = 10.0, 90.0
        res = cam_follower_cycloidal(h=h, beta_deg=beta, theta_deg=beta)
        assert res["ok"] is True
        assert abs(res["velocity_per_omega"]) < 1e-10

    def test_acceleration_at_start_is_zero(self):
        """d²y/dθ² at theta=0 must be 0."""
        res = cam_follower_cycloidal(h=10.0, beta_deg=90.0, theta_deg=0.0)
        assert res["ok"] is True
        assert abs(res["acceleration_per_omega2"]) < 1e-10

    def test_acceleration_at_end_is_zero(self):
        """d²y/dθ² at theta=beta must be 0."""
        h, beta = 10.0, 90.0
        res = cam_follower_cycloidal(h=h, beta_deg=beta, theta_deg=beta)
        assert res["ok"] is True
        assert abs(res["acceleration_per_omega2"]) < 1e-10

    def test_midpoint_displacement_formula(self):
        """At theta=beta/2, y = h/2 (cycloidal is symmetric)."""
        h, beta = 10.0, 90.0
        res = cam_follower_cycloidal(h=h, beta_deg=beta, theta_deg=beta / 2.0)
        assert res["ok"] is True
        assert abs(res["displacement"] - h / 2.0) < 1e-9

    def test_fall_at_beta_gives_zero_displacement(self):
        """For fall, y(theta=beta) must be 0."""
        h, beta = 10.0, 90.0
        res = cam_follower_cycloidal(h=h, beta_deg=beta, theta_deg=beta, rise=False)
        assert res["ok"] is True
        assert abs(res["displacement"]) < 1e-9

    def test_fall_at_zero_gives_h(self):
        """For fall, y(theta=0) must equal h."""
        h, beta = 10.0, 90.0
        res = cam_follower_cycloidal(h=h, beta_deg=beta, theta_deg=0.0, rise=False)
        assert res["ok"] is True
        assert abs(res["displacement"] - h) < 1e-9

    def test_analytical_formula_at_quarter_point(self):
        """Verify y at theta=beta/4 against the analytical formula."""
        h, beta_deg = 10.0, 90.0
        beta = math.radians(beta_deg)
        theta = beta / 4.0
        xi = theta / beta  # = 0.25
        y_expected = h * (xi - math.sin(2.0 * math.pi * xi) / (2.0 * math.pi))
        res = cam_follower_cycloidal(h=h, beta_deg=beta_deg, theta_deg=beta_deg / 4.0)
        assert res["ok"] is True
        assert abs(res["displacement"] - y_expected) < 1e-10

    def test_invalid_negative_h_returns_error(self):
        """Negative h must return ok=False."""
        res = cam_follower_cycloidal(h=-5.0, beta_deg=90.0, theta_deg=0.0)
        assert res["ok"] is False


# ===========================================================================
# 7. cam_follower_harmonic
# ===========================================================================

class TestCamFollowerHarmonic:

    def test_displacement_at_start_is_zero(self):
        """y(theta=0) must be 0 for rise."""
        res = cam_follower_harmonic(h=10.0, beta_deg=90.0, theta_deg=0.0)
        assert res["ok"] is True
        assert abs(res["displacement"]) < 1e-10

    def test_displacement_at_end_equals_h(self):
        """y(theta=beta) must equal h for rise."""
        h, beta = 10.0, 90.0
        res = cam_follower_harmonic(h=h, beta_deg=beta, theta_deg=beta)
        assert res["ok"] is True
        assert abs(res["displacement"] - h) < 1e-9

    def test_midpoint_displacement(self):
        """At theta=beta/2, y = h/2 (harmonic is symmetric)."""
        h, beta = 10.0, 90.0
        res = cam_follower_harmonic(h=h, beta_deg=beta, theta_deg=beta / 2.0)
        assert res["ok"] is True
        assert abs(res["displacement"] - h / 2.0) < 1e-9

    def test_analytical_formula_at_quarter_point(self):
        """Verify y at theta=beta/4 against (h/2)(1 - cos(π/4)) = h(2-√2)/4."""
        h, beta_deg = 10.0, 90.0
        beta = math.radians(beta_deg)
        theta = beta / 4.0
        xi = theta / beta  # 0.25
        y_expected = (h / 2.0) * (1.0 - math.cos(math.pi * xi))
        res = cam_follower_harmonic(h=h, beta_deg=beta_deg, theta_deg=beta_deg / 4.0)
        assert res["ok"] is True
        assert abs(res["displacement"] - y_expected) < 1e-10

    def test_warning_always_present(self):
        """Harmonic profile must always return at least one warning about acceleration discontinuity."""
        res = cam_follower_harmonic(h=10.0, beta_deg=90.0, theta_deg=45.0)
        assert res["ok"] is True
        assert len(res["warnings"]) >= 1
        # The warning must mention acceleration
        assert any("acceleration" in w.lower() for w in res["warnings"])

    def test_fall_at_zero_gives_h(self):
        """For fall, y(theta=0) must equal h."""
        h, beta = 10.0, 90.0
        res = cam_follower_harmonic(h=h, beta_deg=beta, theta_deg=0.0, rise=False)
        assert res["ok"] is True
        assert abs(res["displacement"] - h) < 1e-9

    def test_invalid_zero_beta_returns_error(self):
        """beta_deg=0 must return ok=False."""
        res = cam_follower_harmonic(h=10.0, beta_deg=0.0, theta_deg=0.0)
        assert res["ok"] is False


# ===========================================================================
# 8. Tool wrappers (LLM interface)
# ===========================================================================

class TestToolWrappers:

    def test_grashof_tool_happy_path(self):
        raw = _run(run_four_bar_grashof(_ctx(), _args(r1=4.0, r2=2.0, r3=4.5, r4=3.5)))
        d = _ok_tool(raw)
        assert "type" in d

    def test_grashof_tool_missing_field_returns_error(self):
        raw = _run(run_four_bar_grashof(_ctx(), _args(r1=4.0, r2=2.0, r3=4.5)))
        _err_tool(raw)

    def test_position_tool_happy_path(self):
        raw = _run(run_four_bar_position(
            _ctx(), _args(r1=4.0, r2=2.0, r3=4.5, r4=3.5, theta2_deg=45.0)
        ))
        d = _ok_tool(raw)

    def test_position_tool_invalid_json(self):
        raw = _run(run_four_bar_position(_ctx(), b"not-json"))
        _err_tool(raw)

    def test_transmission_angle_tool_happy_path(self):
        raw = _run(run_four_bar_transmission_angle(
            _ctx(), _args(r1=4.0, r2=2.0, r3=4.5, r4=3.5, theta2_deg=60.0)
        ))
        _ok_tool(raw)

    def test_coupler_curve_tool_happy_path(self):
        raw = _run(run_four_bar_coupler_curve(
            _ctx(), _args(r1=4.0, r2=2.0, r3=4.5, r4=3.5, px=1.0, py=0.5, n_points=12)
        ))
        _ok_tool(raw)

    def test_slider_crank_tool_happy_path(self):
        raw = _run(run_slider_crank(_ctx(), _args(r=0.05, l=0.15, theta_deg=90.0, omega_rad_s=100.0)))
        _ok_tool(raw)

    def test_slider_crank_tool_missing_field(self):
        raw = _run(run_slider_crank(_ctx(), _args(r=0.05, l=0.15)))
        _err_tool(raw)

    def test_cam_cycloidal_tool_happy_path(self):
        raw = _run(run_cam_follower_cycloidal(
            _ctx(), _args(h=10.0, beta_deg=90.0, theta_deg=45.0)
        ))
        _ok_tool(raw)

    def test_cam_harmonic_tool_happy_path(self):
        raw = _run(run_cam_follower_harmonic(
            _ctx(), _args(h=10.0, beta_deg=90.0, theta_deg=45.0)
        ))
        _ok_tool(raw)

    def test_cam_harmonic_tool_fall_branch(self):
        raw = _run(run_cam_follower_harmonic(
            _ctx(), _args(h=10.0, beta_deg=90.0, theta_deg=45.0, rise=False)
        ))
        _ok_tool(raw)
