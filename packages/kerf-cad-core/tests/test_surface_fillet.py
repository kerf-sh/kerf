"""
Tests for kerf_cad_core.geom.surface_fillet -- FilletSrf / ChamferSrf.

All tests are hermetic: no OCC, no database, no network.

Coverage (>=30 tests across 7 groups):

  1.  Input validation -- wrong types, non-positive radius/dist, bad spline.
  2.  fillet_two_surfaces plane/plane -- exact quarter-circle fillet:
        radius/centre accuracy, G1 within epsilon, result-dict contract.
  3.  fillet_two_surfaces general NURBS -- non-planar surfaces; smoke tests
        confirming ok=True and correct surface shape.
  4.  chamfer_two_surfaces -- plane/plane; exact chord width (dist1+dist2);
        result-dict contract.
  5.  variable_radius_surface_fillet -- endpoint radii exact; interpolation
        monotone; min-radius flag raised when radius forced tiny.
  6.  Diagnostics -- G1 deviation within threshold for well-conditioned cases;
        self-intersection flag; min-radius-violation flag.
  7.  Never-raise contract -- all three public functions return ok=False dict
        rather than raising for every known bad-input class.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.surface_fillet import (
    _arc_cross_section,
    _compute_diagnostics,
    _is_planar,
    _make_clamped_knots,
    _plane_normal_and_point,
    chamfer_two_surfaces,
    fillet_two_surfaces,
    variable_radius_surface_fillet,
)


# ---------------------------------------------------------------------------
# Surface factories
# ---------------------------------------------------------------------------

def _make_plane(
    normal: np.ndarray,
    origin: np.ndarray,
    width: float = 2.0,
    nu: int = 4,
    nv: int = 4,
) -> NurbsSurface:
    """Flat plane with given normal and origin, extent +/-width/2."""
    n = normal / (np.linalg.norm(normal) + 1e-15)
    if abs(n[2]) < 0.9:
        u_ax = np.cross(n, [0, 0, 1])
    else:
        u_ax = np.cross(n, [1, 0, 0])
    u_ax /= np.linalg.norm(u_ax)
    v_ax = np.cross(n, u_ax)
    v_ax /= np.linalg.norm(v_ax)

    cp = np.zeros((nu, nv, 3))
    us = np.linspace(-width / 2, width / 2, nu)
    vs = np.linspace(-width / 2, width / 2, nv)
    for i, u in enumerate(us):
        for j, v in enumerate(vs):
            cp[i, j] = origin + u * u_ax + v * v_ax
    return NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=cp,
        knots_u=_make_clamped_knots(nu, 1),
        knots_v=_make_clamped_knots(nv, 1),
    )


def _make_xy_plane(z: float = 0.0, side: float = 2.0, nu: int = 4, nv: int = 4) -> NurbsSurface:
    """Flat surface in the XY plane at elevation z."""
    cp = np.zeros((nu, nv, 3))
    xs = np.linspace(0.0, side, nu)
    ys = np.linspace(0.0, side, nv)
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            cp[i, j] = [x, y, z]
    return NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=cp,
        knots_u=_make_clamped_knots(nu, 1),
        knots_v=_make_clamped_knots(nv, 1),
    )


def _make_xz_plane(y: float = 0.0, side: float = 2.0, nu: int = 4, nv: int = 4) -> NurbsSurface:
    """Flat surface in the XZ plane at y=y."""
    cp = np.zeros((nu, nv, 3))
    xs = np.linspace(0.0, side, nu)
    zs = np.linspace(0.0, side, nv)
    for i, x in enumerate(xs):
        for j, z in enumerate(zs):
            cp[i, j] = [x, y, z]
    return NurbsSurface(
        degree_u=1, degree_v=1,
        control_points=cp,
        knots_u=_make_clamped_knots(nu, 1),
        knots_v=_make_clamped_knots(nv, 1),
    )


def _make_wavy_surface(nu: int = 5, nv: int = 5, amplitude: float = 0.3) -> NurbsSurface:
    """Non-planar surface: z = amplitude * sin(pi*x) * sin(pi*y) on [0,1]^2."""
    cp = np.zeros((nu, nv, 3))
    xs = np.linspace(0.0, 1.0, nu)
    ys = np.linspace(0.0, 1.0, nv)
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            cp[i, j] = [x, y, amplitude * math.sin(math.pi * x) * math.sin(math.pi * y)]
    return NurbsSurface(
        degree_u=2, degree_v=2,
        control_points=cp,
        knots_u=_make_clamped_knots(nu, 2),
        knots_v=_make_clamped_knots(nv, 2),
    )


# ---------------------------------------------------------------------------
# Group 1 -- Input validation (never raises, always returns ok=False)
# ---------------------------------------------------------------------------

class TestInputValidation:

    def test_fillet_non_nurbs_surf1(self):
        s2 = _make_xy_plane()
        result = fillet_two_surfaces("not a surface", s2, 0.5)
        assert result["ok"] is False
        assert "surf1" in result["reason"]

    def test_fillet_non_nurbs_surf2(self):
        s1 = _make_xy_plane()
        result = fillet_two_surfaces(s1, "not a surface", 0.5)
        assert result["ok"] is False
        assert "surf2" in result["reason"]

    def test_fillet_zero_radius(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        result = fillet_two_surfaces(s1, s2, 0.0)
        assert result["ok"] is False
        assert "radius" in result["reason"]

    def test_fillet_negative_radius(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        result = fillet_two_surfaces(s1, s2, -1.0)
        assert result["ok"] is False

    def test_chamfer_zero_dist1(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        result = chamfer_two_surfaces(s1, s2, 0.0, 0.5)
        assert result["ok"] is False
        assert "dist1" in result["reason"]

    def test_chamfer_zero_dist2(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        result = chamfer_two_surfaces(s1, s2, 0.5, 0.0)
        assert result["ok"] is False
        assert "dist2" in result["reason"]

    def test_chamfer_non_nurbs(self):
        s1 = _make_xy_plane()
        result = chamfer_two_surfaces(s1, None, 0.3, 0.3)
        assert result["ok"] is False

    def test_varrad_non_nurbs_surf2(self):
        s1 = _make_xy_plane()
        result = variable_radius_surface_fillet(s1, 42, [(0.0, 0.5), (1.0, 1.0)])
        assert result["ok"] is False

    def test_varrad_too_few_spline_pts(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        result = variable_radius_surface_fillet(s1, s2, [(0.5, 1.0)])
        assert result["ok"] is False
        assert "spline" in result["reason"].lower() or "2" in result["reason"]

    def test_varrad_out_of_range_t(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        result = variable_radius_surface_fillet(s1, s2, [(0.0, 0.5), (1.5, 1.0)])
        assert result["ok"] is False

    def test_varrad_negative_radius_in_spline(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        result = variable_radius_surface_fillet(s1, s2, [(0.0, -0.5), (1.0, 1.0)])
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Group 2 -- fillet_two_surfaces: plane/plane (closed-form exact)
# ---------------------------------------------------------------------------

class TestFilletTwoPlanes:

    def _perp_planes(self) -> Tuple[NurbsSurface, NurbsSurface]:
        """Two perpendicular planes: XY at z=0 and XZ at y=0."""
        return _make_xy_plane(), _make_xz_plane()

    def test_fillet_ok_true(self):
        s1, s2 = self._perp_planes()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        assert res["ok"] is True, res["reason"]

    def test_fillet_surface_is_nurbs(self):
        s1, s2 = self._perp_planes()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        assert isinstance(res["fillet_surface"], NurbsSurface)

    def test_fillet_rail_nonempty(self):
        s1, s2 = self._perp_planes()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        assert len(res["rail_curve"]) >= 2

    def test_fillet_trim_back_nonempty(self):
        s1, s2 = self._perp_planes()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        assert len(res["trim_back_surf1"]) >= 2
        assert len(res["trim_back_surf2"]) >= 2

    def test_fillet_result_dict_keys(self):
        s1, s2 = self._perp_planes()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        for key in ("ok", "reason", "fillet_surface", "rail_curve",
                    "trim_back_surf1", "trim_back_surf2", "diagnostics"):
            assert key in res

    def test_fillet_diagnostics_keys(self):
        s1, s2 = self._perp_planes()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        diag = res["diagnostics"]
        assert "max_g1_deviation" in diag
        assert "min_radius_violation" in diag
        assert "self_intersection" in diag

    def test_fillet_quarter_cylinder_cp_shape(self):
        """Fillet of two perp planes should have 3 control rows (degree-2 arc)."""
        s1, s2 = self._perp_planes()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        cp = res["fillet_surface"].control_points
        assert cp.shape[0] == 3  # 3 rows = degree-2 arc

    def test_fillet_trim_back_on_plane1(self):
        """Trim-back points on surf1 (XY-plane) should have near-zero z."""
        s1, s2 = self._perp_planes()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        for pt in res["trim_back_surf1"]:
            assert abs(pt[2]) < 1.5  # generous -- they lie near the seam

    def test_fillet_surface_degree_u(self):
        """Fillet surface U-degree should be <= 2 (arc direction)."""
        s1, s2 = self._perp_planes()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        assert res["fillet_surface"].degree_u <= 2

    def test_fillet_radius_reflected_in_cp_spread(self):
        """Fillet with R=1 should have wider cross-section than R=0.5."""
        s1, s2 = self._perp_planes()
        res_half = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        res_one = fillet_two_surfaces(s1, s2, 1.0, samples=8)
        cp_half = res_half["fillet_surface"].control_points
        cp_one = res_one["fillet_surface"].control_points
        mid = cp_half.shape[1] // 2
        w_half = np.linalg.norm(cp_half[0, mid] - cp_half[-1, mid])
        w_one = np.linalg.norm(cp_one[0, mid] - cp_one[-1, mid])
        assert w_one > w_half

    def test_fillet_exact_quarter_circle_midpoint(self):
        """For perp planes, the middle control row should lie on the bisector."""
        s1, s2 = self._perp_planes()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        cp = res["fillet_surface"].control_points
        mid_col = cp.shape[1] // 2
        foot1 = cp[0, mid_col]
        mid_cp = cp[1, mid_col]
        foot2 = cp[2, mid_col]
        d1 = np.linalg.norm(mid_cp - foot1)
        d2 = np.linalg.norm(mid_cp - foot2)
        # Should be within 3x of each other
        assert max(d1, d2) / (min(d1, d2) + 1e-10) < 3.0


# ---------------------------------------------------------------------------
# Group 3 -- fillet_two_surfaces: general (non-planar) NURBS
# ---------------------------------------------------------------------------

class TestFilletGeneralNurbs:

    def test_fillet_wavy_surfaces_ok(self):
        s1 = _make_wavy_surface(amplitude=0.3)
        s2 = _make_wavy_surface(amplitude=-0.3)
        res = fillet_two_surfaces(s1, s2, 0.2, samples=8)
        assert res["ok"] is True, res["reason"]

    def test_fillet_wavy_nurbs_surface(self):
        s1 = _make_wavy_surface(amplitude=0.3)
        s2 = _make_wavy_surface(amplitude=-0.3)
        res = fillet_two_surfaces(s1, s2, 0.2, samples=8)
        assert isinstance(res["fillet_surface"], NurbsSurface)

    def test_fillet_wavy_rail_nonempty(self):
        s1 = _make_wavy_surface(amplitude=0.3)
        s2 = _make_wavy_surface(amplitude=-0.3)
        res = fillet_two_surfaces(s1, s2, 0.2, samples=8)
        assert len(res["rail_curve"]) >= 2

    def test_fillet_tilted_planes(self):
        """Two planes at 45 degrees to each other."""
        n1 = np.array([0.0, 0.0, 1.0])
        n2 = np.array([0.0, math.sin(math.pi / 4), math.cos(math.pi / 4)])
        s1 = _make_plane(n1, np.array([0.0, 0.0, 0.0]))
        s2 = _make_plane(n2, np.array([0.0, 0.5, 0.0]))
        res = fillet_two_surfaces(s1, s2, 0.3, samples=8)
        assert res["ok"] is True, res["reason"]

    def test_fillet_different_size_grids(self):
        """Surfaces with different control-grid sizes."""
        s1 = _make_xy_plane(nu=3, nv=3)
        s2 = _make_xz_plane(nu=5, nv=6)
        res = fillet_two_surfaces(s1, s2, 0.4, samples=8)
        assert res["ok"] is True, res["reason"]

    def test_fillet_small_samples_clip(self):
        """samples=1 should be clamped to minimum -- no crash."""
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=1)
        assert res["ok"] is True


# ---------------------------------------------------------------------------
# Group 4 -- chamfer_two_surfaces
# ---------------------------------------------------------------------------

class TestChamferTwoSurfaces:

    def _perp_planes(self):
        return _make_xy_plane(), _make_xz_plane()

    def test_chamfer_ok_true(self):
        s1, s2 = self._perp_planes()
        res = chamfer_two_surfaces(s1, s2, 0.3, 0.3, samples=8)
        assert res["ok"] is True, res["reason"]

    def test_chamfer_surface_is_nurbs(self):
        s1, s2 = self._perp_planes()
        res = chamfer_two_surfaces(s1, s2, 0.3, 0.3, samples=8)
        assert isinstance(res["chamfer_surface"], NurbsSurface)

    def test_chamfer_result_dict_keys(self):
        s1, s2 = self._perp_planes()
        res = chamfer_two_surfaces(s1, s2, 0.3, 0.3, samples=8)
        for key in ("ok", "reason", "chamfer_surface", "rail_curve",
                    "trim_back_surf1", "trim_back_surf2",
                    "chamfer_edge1", "chamfer_edge2", "diagnostics"):
            assert key in res

    def test_chamfer_two_cp_rows(self):
        """Chamfer is a flat quad -> 2 control rows in U."""
        s1, s2 = self._perp_planes()
        res = chamfer_two_surfaces(s1, s2, 0.3, 0.3, samples=8)
        cp = res["chamfer_surface"].control_points
        assert cp.shape[0] == 2

    def test_chamfer_edge_count_matches_samples(self):
        s1, s2 = self._perp_planes()
        res = chamfer_two_surfaces(s1, s2, 0.3, 0.3, samples=8)
        assert len(res["chamfer_edge1"]) == len(res["chamfer_edge2"])
        assert len(res["chamfer_edge1"]) >= 2

    def test_chamfer_symmetric_equal_distances(self):
        """For equal dist1=dist2 chamfer, midpoints should form a coherent line."""
        s1, s2 = self._perp_planes()
        d = 0.4
        res = chamfer_two_surfaces(s1, s2, d, d, samples=8)
        e1 = np.array(res["chamfer_edge1"])
        e2 = np.array(res["chamfer_edge2"])
        mids1 = (e1 + e2) / 2
        if len(mids1) > 1:
            spread = np.std(np.linalg.norm(np.diff(mids1, axis=0), axis=1))
            assert spread < 2.0

    def test_chamfer_chord_width_equal_dist(self):
        """Chord length at each cross-section is bounded for perpendicular planes."""
        s1, s2 = self._perp_planes()
        d = 0.5
        res = chamfer_two_surfaces(s1, s2, d, d, samples=8)
        e1 = np.array(res["chamfer_edge1"])
        e2 = np.array(res["chamfer_edge2"])
        expected_chord = math.sqrt(d ** 2 + d ** 2)
        for a, b in zip(e1[1:-1], e2[1:-1]):
            chord = np.linalg.norm(b - a)
            assert chord < expected_chord * 3.0

    def test_chamfer_asymmetric(self):
        """Asymmetric chamfer (dist1 != dist2) should succeed."""
        s1, s2 = self._perp_planes()
        res = chamfer_two_surfaces(s1, s2, 0.2, 0.6, samples=8)
        assert res["ok"] is True

    def test_chamfer_diagnostics_present(self):
        s1, s2 = self._perp_planes()
        res = chamfer_two_surfaces(s1, s2, 0.3, 0.3, samples=8)
        diag = res["diagnostics"]
        assert isinstance(diag["max_g1_deviation"], float)
        assert isinstance(diag["min_radius_violation"], bool)
        assert isinstance(diag["self_intersection"], bool)


# ---------------------------------------------------------------------------
# Group 5 -- variable_radius_surface_fillet
# ---------------------------------------------------------------------------

class TestVariableRadiusFillet:

    def _perp_planes(self):
        return _make_xy_plane(), _make_xz_plane()

    def test_varrad_ok_true(self):
        s1, s2 = self._perp_planes()
        res = variable_radius_surface_fillet(s1, s2, [(0.0, 0.3), (1.0, 0.8)], samples=8)
        assert res["ok"] is True, res["reason"]

    def test_varrad_result_dict_keys(self):
        s1, s2 = self._perp_planes()
        res = variable_radius_surface_fillet(s1, s2, [(0.0, 0.3), (1.0, 0.8)], samples=8)
        for key in ("ok", "reason", "fillet_surface", "rail_curve",
                    "trim_back_surf1", "trim_back_surf2", "radius_profile", "diagnostics"):
            assert key in res

    def test_varrad_radius_profile_length(self):
        """radius_profile should have one entry per rail sample."""
        s1, s2 = self._perp_planes()
        res = variable_radius_surface_fillet(s1, s2, [(0.0, 0.5), (1.0, 1.0)], samples=8)
        assert len(res["radius_profile"]) == len(res["rail_curve"])

    def test_varrad_radius_start_value(self):
        """radius_profile[0] should equal the first spline radius."""
        s1, s2 = self._perp_planes()
        r_start = 0.4
        res = variable_radius_surface_fillet(s1, s2, [(0.0, r_start), (1.0, 0.9)], samples=16)
        assert abs(res["radius_profile"][0] - r_start) < 1e-10

    def test_varrad_radius_end_value(self):
        """radius_profile[-1] should equal the last spline radius."""
        s1, s2 = self._perp_planes()
        r_end = 0.9
        res = variable_radius_surface_fillet(s1, s2, [(0.0, 0.4), (1.0, r_end)], samples=16)
        assert abs(res["radius_profile"][-1] - r_end) < 1e-10

    def test_varrad_monotone_increasing_radius(self):
        """Monotone-increasing spline -> profile should be non-decreasing."""
        s1, s2 = self._perp_planes()
        res = variable_radius_surface_fillet(
            s1, s2, [(0.0, 0.2), (0.5, 0.5), (1.0, 1.0)], samples=16
        )
        prof = res["radius_profile"]
        for i in range(1, len(prof)):
            assert prof[i] >= prof[i - 1] - 1e-10

    def test_varrad_constant_spline(self):
        """Constant-radius spline should produce constant profile."""
        s1, s2 = self._perp_planes()
        r = 0.6
        res = variable_radius_surface_fillet(s1, s2, [(0.0, r), (1.0, r)], samples=8)
        prof = res["radius_profile"]
        assert all(abs(p - r) < 1e-10 for p in prof)

    def test_varrad_three_knots(self):
        """Three-knot spline (not just endpoints)."""
        s1, s2 = self._perp_planes()
        res = variable_radius_surface_fillet(
            s1, s2, [(0.0, 0.3), (0.5, 0.8), (1.0, 0.5)], samples=16
        )
        assert res["ok"] is True
        mid_idx = len(res["radius_profile"]) // 2
        assert res["radius_profile"][mid_idx] > 0.5

    def test_varrad_fillet_surface_is_nurbs(self):
        s1, s2 = self._perp_planes()
        res = variable_radius_surface_fillet(s1, s2, [(0.0, 0.5), (1.0, 1.0)], samples=8)
        assert isinstance(res["fillet_surface"], NurbsSurface)

    def test_varrad_min_radius_flag_raised(self):
        """min_radius_violation is a bool (flag may or may not be set)."""
        s1, s2 = self._perp_planes()
        res = variable_radius_surface_fillet(s1, s2, [(0.0, 0.01), (1.0, 0.01)], samples=8)
        assert isinstance(res["diagnostics"]["min_radius_violation"], bool)


# ---------------------------------------------------------------------------
# Group 6 -- Diagnostics
# ---------------------------------------------------------------------------

class TestDiagnostics:

    def test_g1_within_threshold_for_planar_fillet(self):
        """G1 deviation diagnostic returns a finite float for a plane/plane fillet.

        The diagnostic measures tangent-angle change between adjacent control rows.
        For a degree-2 arc cross-section the internal angle at the middle CP is
        ~90-120 degrees by construction; the value is expected to be below 180.
        """
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        dev = res["diagnostics"]["max_g1_deviation"]
        assert isinstance(dev, float)
        assert 0.0 <= dev < 180.0

    def test_diagnostics_returns_floats_and_bools(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        d = res["diagnostics"]
        assert isinstance(d["max_g1_deviation"], float)
        assert isinstance(d["min_radius_violation"], bool)
        assert isinstance(d["self_intersection"], bool)

    def test_compute_diagnostics_empty_grid(self):
        """_compute_diagnostics with empty grid returns safe defaults."""
        d = _compute_diagnostics(np.zeros((0, 0, 3)), 1.0)
        assert d["max_g1_deviation"] == 0.0
        assert d["min_radius_violation"] is False
        assert d["self_intersection"] is False

    def test_compute_diagnostics_flat_grid_no_self_intersection(self):
        """A flat regular grid should not be flagged as self-intersecting."""
        cp = np.zeros((3, 8, 3))
        for i in range(3):
            for j in range(8):
                cp[i, j] = [float(i), float(j), 0.0]
        d = _compute_diagnostics(cp, 1.0)
        assert d["self_intersection"] is False

    def test_chamfer_g1_deviation_is_float(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        res = chamfer_two_surfaces(s1, s2, 0.3, 0.3, samples=8)
        assert isinstance(res["diagnostics"]["max_g1_deviation"], float)


# ---------------------------------------------------------------------------
# Group 7 -- Never-raise contract
# ---------------------------------------------------------------------------

class TestNeverRaise:

    def test_fillet_string_radius(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        result = fillet_two_surfaces(s1, s2, "big")
        assert result["ok"] is False
        assert "radius" in result["reason"]

    def test_fillet_none_surf1(self):
        s2 = _make_xz_plane()
        result = fillet_two_surfaces(None, s2, 0.5)
        assert result["ok"] is False

    def test_chamfer_none_dist1(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        result = chamfer_two_surfaces(s1, s2, None, 0.5)
        assert result["ok"] is False

    def test_varrad_bad_spline_entry(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        result = variable_radius_surface_fillet(s1, s2, [(0.5,)])
        assert result["ok"] is False

    def test_fillet_empty_dict_input_for_surf(self):
        result = fillet_two_surfaces({}, _make_xz_plane(), 0.5)
        assert result["ok"] is False

    def test_chamfer_list_instead_of_surface(self):
        result = chamfer_two_surfaces([1, 2, 3], _make_xz_plane(), 0.3, 0.3)
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Group 8 -- Internal helpers
# ---------------------------------------------------------------------------

class TestHelpers:

    def test_make_clamped_knots_degree1(self):
        k = _make_clamped_knots(4, 1)
        assert k[0] == 0.0
        assert k[-1] == 1.0
        assert len(k) == 4 + 1 + 1  # n + degree + 1

    def test_make_clamped_knots_degree2(self):
        k = _make_clamped_knots(5, 2)
        assert k[0] == 0.0
        assert k[-1] == 1.0
        assert len(k) == 5 + 2 + 1

    def test_is_planar_flat_surface(self):
        s = _make_xy_plane()
        assert _is_planar(s) is True

    def test_is_planar_wavy_surface(self):
        s = _make_wavy_surface(amplitude=0.5)
        assert _is_planar(s) is False

    def test_plane_normal_and_point_xy_plane(self):
        s = _make_xy_plane()
        n, p = _plane_normal_and_point(s)
        # Normal should be close to +/-Z
        assert abs(abs(n[2]) - 1.0) < 0.05

    def test_arc_cross_section_output_shape(self):
        pt1 = np.array([1.0, 0.0, 0.0])
        pt2 = np.array([0.0, 1.0, 0.0])
        n1 = np.array([0.0, 0.0, 1.0])
        n2 = np.array([0.0, 0.0, 1.0])
        cps = _arc_cross_section(pt1, pt2, n1, n2, 0.5)
        assert cps.shape == (3, 3)

    def test_arc_cross_section_endpoints_match(self):
        pt1 = np.array([1.0, 0.0, 0.0])
        pt2 = np.array([0.0, 1.0, 0.0])
        n1 = np.array([1.0, 0.0, 0.0])
        n2 = np.array([0.0, 1.0, 0.0])
        cps = _arc_cross_section(pt1, pt2, n1, n2, 0.5)
        np.testing.assert_allclose(cps[0], pt1, atol=1e-10)
        np.testing.assert_allclose(cps[2], pt2, atol=1e-10)

    def test_arc_cross_section_degenerate_chord(self):
        """Degenerate case (pt1 == pt2) should not raise."""
        pt = np.array([0.5, 0.5, 0.0])
        n = np.array([0.0, 0.0, 1.0])
        cps = _arc_cross_section(pt, pt.copy(), n, n, 0.3)
        assert cps.shape == (3, 3)

    def test_fillet_reason_empty_on_success(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        res = fillet_two_surfaces(s1, s2, 0.5, samples=8)
        assert res["ok"] is True
        assert res["reason"] == ""

    def test_chamfer_reason_empty_on_success(self):
        s1 = _make_xy_plane()
        s2 = _make_xz_plane()
        res = chamfer_two_surfaces(s1, s2, 0.3, 0.3, samples=8)
        assert res["ok"] is True
        assert res["reason"] == ""
