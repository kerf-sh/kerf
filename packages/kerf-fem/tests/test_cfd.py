"""
Hermetic test suite for kerf_fem.cfd_potential and kerf_fem.cfd_navier_stokes.

All analytic oracles are cited inline per test.  No network, no third-party
fixture files — all reference values are baked in from the published sources.

Primary references
------------------
[Lamb]    Lamb H., Hydrodynamics, 6th ed. (1932), Article 69, p. 75.
[KC]      Kundu P. K., Cohen I. M., Fluid Mechanics, 4th ed. (2008), §6.5.
[GGS82]   Ghia U., Ghia K. N., Shin C. T., J. Comput. Phys. 48 (1982) 387-411,
          Table I — lid-driven cavity Re=100 vertical centreline u-velocity.
[Chorin]  Chorin A. J., Math. Comp. 22 (1968) 745-762.
[Schlicht] Schlichting H., Boundary-Layer Theory, 8th ed., §5.1.
"""

from __future__ import annotations

import math
import sys
import os

# ---------------------------------------------------------------------------
# Path resolution — work both from repo root and directly from tests/
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _PKG_SRC not in sys.path:
    sys.path.insert(0, _PKG_SRC)

import pytest

from kerf_fem.cfd_potential import (
    cylinder_Cp_analytic,
    cylinder_streamfunction_analytic,
    cylinder_velocity_analytic,
    doublet_stagnation_points,
    make_grid,
)
from kerf_fem.cfd_navier_stokes import (
    GHIA_RE100_U,
    GHIA_RE100_Y_OVER_H,
    ghia_re100_centreline,
    make_staggered_grid,
)


# ===========================================================================
# Helper
# ===========================================================================

def _approx(a: float, b: float, tol: float = 1e-10) -> bool:
    """Return True when |a − b| <= tol."""
    return abs(a - b) <= tol


# ===========================================================================
# 1. cylinder_Cp_analytic  —  Cp(θ) = 1 − 4 sin²θ
#    [Lamb §69]; [KC §6.5]
# ===========================================================================

class TestCylinderCpAnalytic:

    def test_cp_at_stagnation_front(self):
        """Cp(0°) = 1 − 4·sin²0 = 1 exactly. [Lamb §69; KC §6.5]"""
        assert _approx(cylinder_Cp_analytic(0.0), 1.0)

    def test_cp_at_stagnation_rear(self):
        """Cp(180°) = 1 − 4·sin²π = 1 exactly (rear stagnation). [Lamb §69]"""
        assert _approx(cylinder_Cp_analytic(math.pi), 1.0)

    def test_cp_at_90(self):
        """Cp(90°) = 1 − 4·1 = −3 (maximum suction). [Lamb §69; KC §6.5]"""
        assert _approx(cylinder_Cp_analytic(math.pi / 2), -3.0)

    def test_cp_at_270(self):
        """Cp(270°) = Cp(3π/2) = −3 by symmetry. [KC §6.5]"""
        assert _approx(cylinder_Cp_analytic(3.0 * math.pi / 2), -3.0)

    def test_cp_at_30deg(self):
        """Cp(30°) = 1 − 4·sin²30 = 1 − 4·0.25 = 0. [Lamb §69]"""
        assert _approx(cylinder_Cp_analytic(math.radians(30)), 0.0, tol=1e-12)

    def test_cp_at_60deg(self):
        """Cp(60°) = 1 − 4·sin²60 = 1 − 4·0.75 = −2. [Lamb §69]"""
        assert _approx(cylinder_Cp_analytic(math.radians(60)), -2.0, tol=1e-12)

    def test_cp_at_120deg(self):
        """Cp(120°) = 1 − 4·sin²120 = −2, same as 60° (top-half symmetry). [Lamb §69]"""
        assert _approx(cylinder_Cp_analytic(math.radians(120)), -2.0, tol=1e-12)

    def test_cp_at_150deg(self):
        """Cp(150°) = 1 − 4·sin²150 = 0, same as 30°. [Lamb §69]"""
        assert _approx(cylinder_Cp_analytic(math.radians(150)), 0.0, tol=1e-12)

    def test_cp_symmetry_about_flow_axis_30(self):
        """Cp(θ) == Cp(−θ): symmetric about the x-axis. [KC §6.5]"""
        theta = math.radians(30)
        assert _approx(cylinder_Cp_analytic(theta), cylinder_Cp_analytic(-theta))

    def test_cp_symmetry_about_flow_axis_70(self):
        """Cp(70°) == Cp(−70°): top/bottom symmetry. [KC §6.5]"""
        theta = math.radians(70)
        assert _approx(cylinder_Cp_analytic(theta), cylinder_Cp_analytic(-theta))

    def test_cp_symmetry_90(self):
        """Cp(π/2) == Cp(−π/2): peak suction is symmetric. [KC §6.5]"""
        assert _approx(
            cylinder_Cp_analytic(math.pi / 2),
            cylinder_Cp_analytic(-math.pi / 2),
        )

    def test_cp_front_rear_equal(self):
        """Cp(0) == Cp(π) == 1: both stagnation points have the same Cp. [Lamb §69]"""
        assert _approx(cylinder_Cp_analytic(0.0), cylinder_Cp_analytic(math.pi))

    def test_cp_formula_arbitrary_angle(self):
        """Cp = 1 − 4 sin²θ verified at θ = 45°: expected −1. [Lamb §69]"""
        theta = math.pi / 4
        expected = 1.0 - 4.0 * (math.sin(theta) ** 2)
        assert _approx(cylinder_Cp_analytic(theta), expected)

    def test_cp_range_min_max(self):
        """Cp ∈ [−3, 1] everywhere on the surface. [KC §6.5]"""
        for deg in range(0, 361, 5):
            cp = cylinder_Cp_analytic(math.radians(deg))
            assert -3.0 - 1e-12 <= cp <= 1.0 + 1e-12

    def test_cp_bernoulli_consistency(self):
        """
        Bernoulli relation: Cp + |V|²/V∞² = 1, i.e. Cp = 1 − (Vθ/V∞)².
        At r = R, Vr = 0 and Vθ = −2 V∞ sinθ, so |V|²/V∞² = 4 sin²θ.
        Cp + 4 sin²θ must equal 1 at each θ. [KC §6.5]
        """
        for deg in range(0, 360, 15):
            theta = math.radians(deg)
            cp = cylinder_Cp_analytic(theta)
            v_ratio_sq = 4.0 * math.sin(theta) ** 2   # |V/V∞|² on body
            assert _approx(cp + v_ratio_sq, 1.0, tol=1e-12)


# ===========================================================================
# 2. cylinder_velocity_analytic  —  polar components at r, θ
#    [KC §6.5]: Vr = V∞ cosθ (1 − R²/r²),  Vθ = −V∞ sinθ (1 + R²/r²)
# ===========================================================================

class TestCylinderVelocityAnalytic:

    R = 1.0
    V_INF = 1.0

    def test_radial_velocity_zero_on_surface(self):
        """Vr(R, θ) = 0 for all θ: no normal flow through the body. [KC §6.5]"""
        for deg in range(0, 360, 20):
            theta = math.radians(deg)
            vr, _ = cylinder_velocity_analytic(self.R, theta, self.R, self.V_INF)
            assert _approx(vr, 0.0, tol=1e-15)

    def test_tangential_velocity_on_surface(self):
        """Vθ(R, θ) = −2 V∞ sinθ exactly on the cylinder surface. [KC §6.5]"""
        for deg in [0, 30, 45, 60, 90, 120, 150, 180, 270]:
            theta = math.radians(deg)
            _, vt = cylinder_velocity_analytic(self.R, theta, self.R, self.V_INF)
            expected = -2.0 * self.V_INF * math.sin(theta)
            assert _approx(vt, expected, tol=1e-14), \
                f"deg={deg}: got {vt}, expected {expected}"

    def test_stagnation_velocity_zero_at_front(self):
        """At θ=0 (front stagnation), |V| = 0. [KC §6.5]"""
        vr, vt = cylinder_velocity_analytic(self.R, 0.0, self.R, self.V_INF)
        assert _approx(abs(vr) + abs(vt), 0.0, tol=1e-15)

    def test_stagnation_velocity_zero_at_rear(self):
        """At θ=π (rear stagnation), |V| = 0. [KC §6.5]"""
        vr, vt = cylinder_velocity_analytic(self.R, math.pi, self.R, self.V_INF)
        assert _approx(abs(vr) + abs(vt), 0.0, tol=1e-14)

    def test_speed_at_top_of_cylinder(self):
        """|V| at θ=π/2 on surface = 2 V∞. [Lamb §69]"""
        _, vt = cylinder_velocity_analytic(self.R, math.pi / 2, self.R, self.V_INF)
        assert _approx(abs(vt), 2.0 * self.V_INF, tol=1e-14)

    def test_far_field_approaches_uniform_flow(self):
        """At r >> R, Vr → V∞ cosθ and Vθ → −V∞ sinθ (uniform flow). [KC §6.5]"""
        r_far = 1000.0 * self.R
        theta = math.radians(45)
        vr, vt = cylinder_velocity_analytic(r_far, theta, self.R, self.V_INF)
        assert _approx(vr, self.V_INF * math.cos(theta), tol=1e-5)
        assert _approx(vt, -self.V_INF * math.sin(theta), tol=1e-5)

    def test_velocity_proportional_to_vinf(self):
        """Velocity components scale linearly with V∞. [KC §6.5]"""
        r = 1.5 * self.R
        theta = math.radians(45)
        vr1, vt1 = cylinder_velocity_analytic(r, theta, self.R, 1.0)
        vr2, vt2 = cylinder_velocity_analytic(r, theta, self.R, 3.0)
        assert _approx(vr2, 3.0 * vr1, tol=1e-12)
        assert _approx(vt2, 3.0 * vt1, tol=1e-12)


# ===========================================================================
# 3. Incompressibility and irrotationality — analytic velocity field
#    div V = ∂Vx/∂x + ∂Vy/∂y = 0  (continuity)
#    curl V = ∂Vy/∂x − ∂Vx/∂y = 0  (irrotational)
#    checked numerically via central finite differences in Cartesian coords.
#    [KC §6.3 & §6.5; Lamb §69]
# ===========================================================================

class TestConservationProperties:

    R = 1.0
    V_INF = 1.0
    H = 1e-5  # step for central differences

    def _vel_cart(self, x: float, y: float):
        """Cartesian (ux, uy) converted from polar components."""
        r = math.hypot(x, y)
        if r < 1e-12:
            return 0.0, 0.0
        theta = math.atan2(y, x)
        vr, vt = cylinder_velocity_analytic(r, theta, self.R, self.V_INF)
        cos_t = x / r; sin_t = y / r
        ux = vr * cos_t - vt * sin_t
        uy = vr * sin_t + vt * cos_t
        return ux, uy

    def test_incompressibility_at_sample_points(self):
        """
        ∇·V = 0 at six off-body points (central-difference check, h=1e-5).
        For potential flow ∇·V = 0 everywhere outside the cylinder. [KC §6.3]
        """
        test_points = [
            (2.0, 0.5), (3.0, 1.0), (0.0, 2.5),
            (-1.5, 1.5), (4.0, -1.0), (1.5, 3.0),
        ]
        h = self.H
        for (x, y) in test_points:
            ux_xp, _ = self._vel_cart(x + h, y)
            ux_xm, _ = self._vel_cart(x - h, y)
            _, uy_yp = self._vel_cart(x, y + h)
            _, uy_ym = self._vel_cart(x, y - h)
            div_v = (ux_xp - ux_xm) / (2 * h) + (uy_yp - uy_ym) / (2 * h)
            assert abs(div_v) < 1e-6, \
                f"non-zero divergence {div_v} at ({x},{y})"

    def test_irrotationality_at_sample_points(self):
        """
        ∇×V = 0 at six off-body points (central-difference check, h=1e-5).
        Irrotational flow: ω_z = ∂Vy/∂x − ∂Vx/∂y = 0. [KC §6.3; Lamb §69]
        """
        test_points = [
            (2.0, 0.5), (3.0, 1.0), (0.0, 2.5),
            (-1.5, 1.5), (4.0, -1.0), (1.5, 3.0),
        ]
        h = self.H
        for (x, y) in test_points:
            _, uy_xp = self._vel_cart(x + h, y)
            _, uy_xm = self._vel_cart(x - h, y)
            ux_yp, _ = self._vel_cart(x, y + h)
            ux_ym, _ = self._vel_cart(x, y - h)
            curl_z = (uy_xp - uy_xm) / (2 * h) - (ux_yp - ux_ym) / (2 * h)
            assert abs(curl_z) < 1e-6, \
                f"non-zero vorticity {curl_z} at ({x},{y})"


# ===========================================================================
# 4. cylinder_streamfunction_analytic
#    ψ(x,y) = V∞ y (1 − R²/(x²+y²))
#    [Lamb §69; KC §6.5]
# ===========================================================================

class TestStreamfunctionAnalytic:

    R = 1.0
    V_INF = 1.0

    def test_psi_zero_on_cylinder_surface(self):
        """ψ = 0 on the cylinder surface r = R. [Lamb §69]"""
        for deg in range(0, 360, 20):
            theta = math.radians(deg)
            x = self.R * math.cos(theta)
            y = self.R * math.sin(theta)
            psi = cylinder_streamfunction_analytic(x, y, self.R, self.V_INF)
            assert _approx(psi, 0.0, tol=1e-14), \
                f"deg={deg}: psi={psi}"

    def test_psi_far_field_equals_uniform_flow(self):
        """Far field: ψ → V∞ y as r → ∞. [KC §6.5]"""
        r_far = 1000.0 * self.R
        for deg in [30, 60, 90, 120]:
            theta = math.radians(deg)
            x = r_far * math.cos(theta)
            y = r_far * math.sin(theta)
            psi = cylinder_streamfunction_analytic(x, y, self.R, self.V_INF)
            psi_uniform = self.V_INF * y
            assert _approx(psi, psi_uniform, tol=1.0e-3 * abs(psi_uniform) + 1e-10)

    def test_psi_stagnation_line_xaxis(self):
        """ψ = 0 along the x-axis (θ=0, π) away from the body. [Lamb §69]"""
        for x in [2.0, 5.0, 10.0, -3.0, -7.0]:
            psi = cylinder_streamfunction_analytic(x, 0.0, self.R, self.V_INF)
            assert _approx(psi, 0.0, tol=1e-14)

    def test_psi_origin_returns_zero(self):
        """ψ at r=0 (degenerate) returns 0 without error. [implementation guard]"""
        psi = cylinder_streamfunction_analytic(0.0, 0.0, self.R, self.V_INF)
        assert psi == 0.0

    def test_psi_formula_spot_check(self):
        """ψ at (3, 4) with R=1, V∞=1: expected V∞·y·(1 − R²/r²) = 4·(1−1/25). [Lamb §69]"""
        x, y, R = 3.0, 4.0, 1.0
        r2 = x * x + y * y
        expected = 1.0 * y * (1.0 - R * R / r2)
        psi = cylinder_streamfunction_analytic(x, y, R, 1.0)
        assert _approx(psi, expected, tol=1e-14)


# ===========================================================================
# 5. doublet_stagnation_points
#    θ=0 (front) and θ=π (rear) stagnation. [Lamb §69; KC §6.5]
# ===========================================================================

class TestDoubletStagnationPoints:

    def test_returns_ok(self):
        """doublet_stagnation_points returns ok=True. [implementation contract]"""
        result = doublet_stagnation_points()
        assert result.get("ok") is True

    def test_front_stagnation_at_zero(self):
        """Front stagnation at θ=0. [Lamb §69; KC §6.5]"""
        result = doublet_stagnation_points()
        assert _approx(result["front"], 0.0, tol=1e-15)

    def test_rear_stagnation_at_pi(self):
        """Rear stagnation at θ=π. [Lamb §69]"""
        result = doublet_stagnation_points()
        assert _approx(result["rear"], math.pi, tol=1e-15)

    def test_stagnation_tangential_velocity_zero(self):
        """Vθ = −2 V∞ sinθ = 0 at both stagnation angles. [KC §6.5]"""
        result = doublet_stagnation_points()
        R = 1.0; V_INF = 1.0
        for key in ("front", "rear"):
            theta = result[key]
            _, vt = cylinder_velocity_analytic(R, theta, R, V_INF)
            assert _approx(vt, 0.0, tol=1e-14), \
                f"Non-zero Vθ={vt} at {key} stagnation"

    def test_stagnation_cp_equals_one(self):
        """Cp = 1 at both stagnation points (Bernoulli, V=0). [KC §6.5]"""
        result = doublet_stagnation_points()
        for key in ("front", "rear"):
            cp = cylinder_Cp_analytic(result[key])
            assert _approx(cp, 1.0, tol=1e-14), \
                f"Cp={cp} at {key} stagnation, expected 1"


# ===========================================================================
# 6. make_grid
#    Grid construction and uniform-spacing checks. [module docstring]
# ===========================================================================

class TestMakeGrid:

    def test_grid_nx_ny_stored(self):
        """make_grid returns correct nx, ny. [module API]"""
        g = make_grid(11, 21)
        assert g["ok"] is True
        assert g["nx"] == 11
        assert g["ny"] == 21

    def test_grid_x_length(self):
        """g['x'] has exactly nx elements. [module API]"""
        g = make_grid(11, 21)
        assert len(g["x"]) == 11
        assert len(g["y"]) == 21

    def test_grid_first_last_x(self):
        """g['x'][0] == x_range[0], g['x'][-1] == x_range[1]. [module API]"""
        g = make_grid(11, 21, x_range=(-1.0, 3.0), y_range=(0.0, 2.0))
        assert _approx(g["x"][0], -1.0)
        assert _approx(g["x"][-1], 3.0)
        assert _approx(g["y"][0], 0.0)
        assert _approx(g["y"][-1], 2.0)

    def test_grid_dx_uniform(self):
        """Node spacing is exactly dx = (x1−x0)/(nx−1). [module API]"""
        g = make_grid(6, 6, x_range=(0.0, 5.0), y_range=(0.0, 5.0))
        dx_expected = 1.0
        for i in range(1, 6):
            assert _approx(g["x"][i] - g["x"][i - 1], dx_expected, tol=1e-13)

    def test_grid_bad_nx_returns_error(self):
        """make_grid with nx<3 returns ok=False. [module API]"""
        g = make_grid(2, 5)
        assert g.get("ok") is False

    def test_grid_bad_range_returns_error(self):
        """make_grid with x_range descending returns ok=False. [module API]"""
        g = make_grid(10, 10, x_range=(2.0, 1.0))
        assert g.get("ok") is False

    def test_grid_dx_dy_values(self):
        """dx and dy match the analytically expected spacing. [module API]"""
        g = make_grid(5, 9, x_range=(0.0, 4.0), y_range=(0.0, 8.0))
        assert _approx(g["dx"], 1.0, tol=1e-14)
        assert _approx(g["dy"], 1.0, tol=1e-14)


# ===========================================================================
# 7. make_staggered_grid
#    Cell counts, cell-centre positions. [module docstring; Chorin 1968]
# ===========================================================================

class TestMakeStaggeredGrid:

    def test_staggered_returns_ok(self):
        """make_staggered_grid returns ok=True for valid inputs. [module API]"""
        g = make_staggered_grid(8, 6, 2.0, 3.0)
        assert g["ok"] is True

    def test_staggered_nx_ny(self):
        """nx, ny are stored correctly. [module API]"""
        g = make_staggered_grid(8, 6, 2.0, 3.0)
        assert g["nx"] == 8
        assert g["ny"] == 6

    def test_staggered_cell_spacings(self):
        """dx = Lx/nx, dy = Ly/ny. [MAC staggered grid; Chorin 1968]"""
        g = make_staggered_grid(10, 5, 2.0, 1.0)
        assert _approx(g["dx"], 0.2, tol=1e-14)
        assert _approx(g["dy"], 0.2, tol=1e-14)

    def test_staggered_cell_centres_count(self):
        """Cell-centre arrays xc, yc have length nx and ny respectively. [module API]"""
        g = make_staggered_grid(7, 9, 1.0, 1.0)
        assert len(g["xc"]) == 7
        assert len(g["yc"]) == 9

    def test_staggered_first_cell_centre(self):
        """First cell centre is at 0.5*dx, 0.5*dy. [MAC layout; Chorin 1968]"""
        g = make_staggered_grid(4, 4, 1.0, 1.0)
        dx = 0.25; dy = 0.25
        assert _approx(g["xc"][0], 0.5 * dx, tol=1e-14)
        assert _approx(g["yc"][0], 0.5 * dy, tol=1e-14)

    def test_staggered_last_cell_centre(self):
        """Last cell centre is at Lx − 0.5*dx, Ly − 0.5*dy. [MAC layout]"""
        g = make_staggered_grid(4, 4, 1.0, 1.0)
        dx = 0.25; dy = 0.25
        assert _approx(g["xc"][-1], 1.0 - 0.5 * dx, tol=1e-14)
        assert _approx(g["yc"][-1], 1.0 - 0.5 * dy, tol=1e-14)

    def test_staggered_bad_nx_returns_error(self):
        """make_staggered_grid with nx<3 returns ok=False. [module API]"""
        g = make_staggered_grid(2, 4, 1.0, 1.0)
        assert g.get("ok") is False

    def test_staggered_bad_Lx_returns_error(self):
        """make_staggered_grid with Lx<=0 returns ok=False. [module API]"""
        g = make_staggered_grid(4, 4, -1.0, 1.0)
        assert g.get("ok") is False

    def test_staggered_Lx_Ly_stored(self):
        """Lx and Ly are stored in the returned dict. [module API]"""
        g = make_staggered_grid(5, 5, 3.0, 7.0)
        assert _approx(g["Lx"], 3.0)
        assert _approx(g["Ly"], 7.0)


# ===========================================================================
# 8. ghia_re100_centreline  —  Ghia-Ghia-Shin 1982 reference data
#    [GGS82] Table I, J. Comput. Phys. 48 (1982) 387-411.
# ===========================================================================

class TestGhiaRe100Centreline:

    def test_returns_ok(self):
        """ghia_re100_centreline returns ok=True. [module API]"""
        result = ghia_re100_centreline()
        assert result.get("ok") is True

    def test_17_stations(self):
        """Table I has exactly 17 y/H stations. [GGS82 Table I]"""
        result = ghia_re100_centreline()
        assert len(result["y_over_H"]) == 17
        assert len(result["u_over_Ulid"]) == 17

    def test_y_over_H_matches_module_constant(self):
        """y/H list returned == GHIA_RE100_Y_OVER_H module constant. [GGS82 Table I]"""
        result = ghia_re100_centreline()
        assert result["y_over_H"] == list(GHIA_RE100_Y_OVER_H)

    def test_u_over_Ulid_matches_module_constant(self):
        """u/Ulid list returned == GHIA_RE100_U module constant. [GGS82 Table I]"""
        result = ghia_re100_centreline()
        assert result["u_over_Ulid"] == list(GHIA_RE100_U)

    def test_top_wall_u_equals_one(self):
        """u/Ulid = 1.0 at y/H = 1.0 (lid velocity). [GGS82 Table I]"""
        result = ghia_re100_centreline()
        idx = result["y_over_H"].index(1.0)
        assert _approx(result["u_over_Ulid"][idx], 1.00000, tol=1e-10)

    def test_bottom_wall_u_zero(self):
        """u/Ulid = 0.0 at y/H = 0.0 (no-slip floor). [GGS82 Table I]"""
        result = ghia_re100_centreline()
        idx = result["y_over_H"].index(0.0)
        assert _approx(result["u_over_Ulid"][idx], 0.0, tol=1e-10)

    def test_midplane_u_negative(self):
        """u/Ulid < 0 near y/H = 0.5 (return flow). [GGS82 Table I, Re=100]"""
        result = ghia_re100_centreline()
        # y/H = 0.5 → u = −0.20581 in GGS82
        idx = result["y_over_H"].index(0.5000)
        assert result["u_over_Ulid"][idx] < 0.0

    def test_top_quarter_u_positive(self):
        """u/Ulid > 0 near the lid (y/H ≈ 0.97), driven by lid. [GGS82 Table I]"""
        result = ghia_re100_centreline()
        # y/H = 0.9766 → u = 0.84123 in GGS82
        idx = result["y_over_H"].index(0.9766)
        assert result["u_over_Ulid"][idx] > 0.0

    def test_re_equals_100(self):
        """Reynolds number is 100. [GGS82]"""
        result = ghia_re100_centreline()
        assert result["Re"] == 100

    def test_specific_ghia_values_exact(self):
        """
        Spot-check 4 published values from GGS82 Table I exactly as baked
        into the module constants — these are reference data, not solver output.
        y/H=0.9766 → u=0.84123; y/H=0.8516 → u=0.23151;
        y/H=0.4531 → u=−0.21090; y/H=0.1016 → u=−0.06434.
        [GGS82 Table I, J. Comput. Phys. 48 (1982) 387-411]
        """
        y_ref = list(GHIA_RE100_Y_OVER_H)
        u_ref = list(GHIA_RE100_U)
        checks = [
            (0.9766, 0.84123),
            (0.8516, 0.23151),
            (0.4531, -0.21090),
            (0.1016, -0.06434),
        ]
        for y_h, u_expected in checks:
            idx = y_ref.index(y_h)
            assert _approx(u_ref[idx], u_expected, tol=1e-10), \
                f"GGS82: y/H={y_h}, got {u_ref[idx]}, expected {u_expected}"

    def test_source_citation_present(self):
        """'source' key contains the GGS82 citation string. [documentation requirement]"""
        result = ghia_re100_centreline()
        assert "Ghia" in result.get("source", "")
        assert "1982" in result.get("source", "")
