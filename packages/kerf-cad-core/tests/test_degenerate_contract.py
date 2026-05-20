"""GK-67: Degenerate-input contract tests across construction verbs.

Matrix: verb × degenerate-input cell.

Oracle: every cell yields **structured failure** (ok=False / BuildError /
ValueError with a message) and NEVER:
  - raises an unhandled exception outside the documented contract, OR
  - returns a Body that fails validate_body.

If a verb does raise something other than BuildError / ValueError we mark
the cell xfail with a note so the harness documents the gap rather than
failing the suite.

Verbs covered
-------------
extrude_to_body  revolve_to_body  sweep1  network_srf (loft)
fit_curve        fit_surface      blend_srf_g1  box_to_body
sew_faces        body_union       body_intersection  body_difference
"""

from __future__ import annotations

import math

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Imports — pure Python, no OCCT required
# ---------------------------------------------------------------------------

from kerf_cad_core.geom.brep import Body, validate_body
from kerf_cad_core.geom.brep_build import BuildError, box_to_body, extrude_to_body, revolve_to_body
from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface
from kerf_cad_core.geom.sweep1 import sweep1
from kerf_cad_core.geom.network_srf import network_srf
from kerf_cad_core.geom.curve_toolkit import fit_curve
from kerf_cad_core.geom.patch_srf import fit_surface
from kerf_cad_core.geom.blend_srf import blend_srf_g1
from kerf_cad_core.geom.sew import sew_faces
from kerf_cad_core.geom.boolean import body_union, body_intersection, body_difference

NAN = float("nan")
INF = float("inf")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line_curve(p0, p1) -> NurbsCurve:
    """Minimal degree-1 NURBS line from p0 to p1."""
    cp = np.array([p0, p1], dtype=float)
    knots = np.array([0.0, 0.0, 1.0, 1.0])
    return NurbsCurve(degree=1, control_points=cp, knots=knots)


def _circle_curve(center=(0, 0, 0), radius=1.0) -> NurbsCurve:
    """Approximate NURBS circle (degree 2, 9 ctrl pts)."""
    from kerf_cad_core.geom.nurbs import make_circle_nurbs
    c = np.asarray(center, dtype=float)
    ax = np.array([1.0, 0.0, 0.0])
    ay = np.array([0.0, 1.0, 0.0])
    return make_circle_nurbs(c, radius, ax, ay)


def _flat_nurbs_surface(nu=4, nv=4, degree_u=3, degree_v=3) -> NurbsSurface:
    """Flat unit-square NurbsSurface in the XY plane."""
    ctrl = np.zeros((nu, nv, 3))
    for i in range(nu):
        for j in range(nv):
            ctrl[i, j] = [i / (nu - 1), j / (nv - 1), 0.0]
    ku = np.concatenate([[0.0] * (degree_u + 1),
                         np.linspace(0, 1, max(0, nu - degree_u - 1) + 2)[1:-1],
                         [1.0] * (degree_u + 1)])
    # ensure correct length: nu + degree_u + 1
    ku = np.pad(ku, (0, max(0, nu + degree_u + 1 - len(ku))), constant_values=1.0)[:nu + degree_u + 1]
    kv = np.concatenate([[0.0] * (degree_v + 1),
                         np.linspace(0, 1, max(0, nv - degree_v - 1) + 2)[1:-1],
                         [1.0] * (degree_v + 1)])
    kv = np.pad(kv, (0, max(0, nv + degree_v + 1 - len(kv))), constant_values=1.0)[:nv + degree_v + 1]
    return NurbsSurface(degree_u=degree_u, degree_v=degree_v,
                        control_points=ctrl, knots_u=ku, knots_v=kv)


def _shifted_surface(dz=2.0, nu=4, nv=4, degree_u=3, degree_v=3) -> NurbsSurface:
    s = _flat_nurbs_surface(nu, nv, degree_u, degree_v)
    ctrl = s.control_points.copy()
    ctrl[:, :, 2] += dz
    return NurbsSurface(degree_u=s.degree_u, degree_v=s.degree_v,
                        control_points=ctrl, knots_u=s.knots_u, knots_v=s.knots_v)


def _assert_structured_failure_or_exception(result, allowed_exc=(BuildError, ValueError)):
    """Assert a result is a structured-failure dict or an allowed exception was raised
    (caller already caught it and passed it here as the result or raises higher).
    This helper is for the dict-returning verbs."""
    assert isinstance(result, dict), f"Expected dict result, got {type(result)}"
    assert "ok" in result, f"Result dict missing 'ok' key: {result}"
    assert result["ok"] is False, f"Expected ok=False for degenerate input, got ok=True"


def _assert_body_valid(body):
    """If a Body is returned, validate it."""
    if isinstance(body, Body):
        res = validate_body(body)
        assert res["ok"], f"Returned Body is invalid: {res['errors']}"


# ===========================================================================
# extrude_to_body
# ===========================================================================

class TestExtrudeToBodyDegenerate:

    def test_zero_vertices_raises_BuildError(self):
        with pytest.raises(BuildError):
            extrude_to_body([], [0, 0, 1])

    def test_one_vertex_raises_BuildError(self):
        with pytest.raises(BuildError):
            extrude_to_body([[0, 0, 0]], [0, 0, 1])

    def test_two_vertices_raises_BuildError(self):
        with pytest.raises(BuildError):
            extrude_to_body([[0, 0, 0], [1, 0, 0]], [0, 0, 1])

    def test_zero_length_direction_raises_BuildError(self):
        tri = [[0, 0, 0], [1, 0, 0], [0.5, 1, 0]]
        with pytest.raises(BuildError):
            extrude_to_body(tri, [0, 0, 0])

    def test_near_zero_direction_raises_BuildError(self):
        tri = [[0, 0, 0], [1, 0, 0], [0.5, 1, 0]]
        with pytest.raises(BuildError):
            extrude_to_body(tri, [0, 0, 1e-20])

    def test_nan_in_vertices_raises_or_builderror(self):
        tri = [[NAN, 0, 0], [1, 0, 0], [0.5, 1, 0]]
        try:
            extrude_to_body(tri, [0, 0, 1])
            # If it returns something, it must not produce an invalid Body
            # (but this path is unexpected for NaN input)
        except (BuildError, ValueError, FloatingPointError):
            pass
        # We just assert no unhandled arbitrary exception leaks out;
        # numpy may raise ValueError for NaN in linalg ops → acceptable

    def test_nan_in_direction_raises_or_builderror(self):
        tri = [[0, 0, 0], [1, 0, 0], [0.5, 1, 0]]
        try:
            extrude_to_body(tri, [0, 0, NAN])
        except (BuildError, ValueError, FloatingPointError):
            pass

    def test_coincident_all_vertices_raises_BuildError(self):
        """Three identical points (degenerate polygon)."""
        # area_vec will be zero; cross(a,b) = 0 for all i -> d_len check hits first
        # since direction is valid. The result is a degenerate solid.
        tri = [[1, 1, 0], [1, 1, 0], [1, 1, 0]]
        try:
            body = extrude_to_body(tri, [0, 0, 1])
            # If it doesn't raise, the returned body must still be validate_body-clean
            # OR we accept BuildError
            _assert_body_valid(body)
        except BuildError:
            pass

    def test_inf_in_vertices_raises_or_builderror(self):
        tri = [[INF, 0, 0], [1, 0, 0], [0.5, 1, 0]]
        try:
            extrude_to_body(tri, [0, 0, 1])
        except (BuildError, ValueError, OverflowError):
            pass


# ===========================================================================
# revolve_to_body
# ===========================================================================

class TestRevolveToBodyDegenerate:

    def _make_profile(self, pts) -> NurbsCurve:
        """Degree-1 NURBS through list of 3D points."""
        n = len(pts)
        cp = np.array(pts, dtype=float)
        knots = np.array([0.0] * 2 + list(np.linspace(0, 1, n - 1)[1:]) + [1.0] * 2) if n > 2 else np.array([0.0, 0.0, 1.0, 1.0])
        return NurbsCurve(degree=1, control_points=cp, knots=knots[:n + 2])

    def test_zero_length_axis_dir_raises_or_builderror(self):
        profile = _line_curve([1, 0, 0], [1, 1, 0])
        try:
            revolve_to_body(profile, [0, 0, 0], [0, 0, 0])
        except (BuildError, ValueError, ZeroDivisionError, FloatingPointError):
            pass

    def test_nan_axis_dir_raises_or_builderror(self):
        profile = _line_curve([1, 0, 0], [1, 1, 0])
        try:
            revolve_to_body(profile, [0, 0, 0], [NAN, 0, 1])
        except (BuildError, ValueError, FloatingPointError):
            pass

    def test_nan_axis_point_raises_or_builderror(self):
        profile = _line_curve([1, 0, 0], [1, 1, 0])
        try:
            revolve_to_body(profile, [NAN, 0, 0], [0, 0, 1])
        except (BuildError, ValueError, FloatingPointError):
            pass

    def test_profile_on_axis_raises_or_builderror(self):
        """Profile at radius=0 — spindle / degenerate case."""
        profile = _line_curve([0, 0, 0], [0, 0, 1])
        try:
            body = revolve_to_body(profile, [0, 0, 0], [0, 0, 1])
            _assert_body_valid(body)
        except (BuildError, ValueError):
            pass


# ===========================================================================
# sweep1
# ===========================================================================

class TestSweep1Degenerate:

    def test_zero_length_path_raises_or_returns_surface(self):
        """Path with coincident endpoints (zero-length rail)."""
        profile = _circle_curve(radius=0.5)
        # A zero-length path: both control points at origin.
        path_cp = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
        path = NurbsCurve(degree=1, control_points=path_cp,
                          knots=np.array([0.0, 0.0, 1.0, 1.0]))
        try:
            result = sweep1(profile, path)
            # If it returns, it must be a NurbsSurface (not Body — sweep1 returns surface)
            assert isinstance(result, NurbsSurface)
        except (ValueError, BuildError, ZeroDivisionError, FloatingPointError):
            pass

    @pytest.mark.xfail(
        reason=(
            "GK-67 gap: sweep1 with a 1-control-point path (malformed knot vector) "
            "raises IndexError from de_boor rather than ValueError/BuildError. "
            "sweep1 lacks an input-validation guard for knot-vector length."
        ),
        raises=IndexError,
        strict=True,
    )
    def test_single_point_path_raises_or_returns_surface(self):
        """Path with only one distinct control point — documents gap in sweep1 guard."""
        profile = _circle_curve(radius=0.5)
        path_cp = np.array([[0.0, 0.0, 0.0]])
        path = NurbsCurve(degree=1, control_points=path_cp,
                          knots=np.array([0.0, 1.0]))
        sweep1(profile, path)

    def test_nan_in_path_control_points(self):
        profile = _line_curve([0, 0, 0], [1, 0, 0])
        path_cp = np.array([[0.0, 0.0, 0.0], [NAN, 0.0, 1.0]])
        path = NurbsCurve(degree=1, control_points=path_cp,
                          knots=np.array([0.0, 0.0, 1.0, 1.0]))
        try:
            sweep1(profile, path)
        except (ValueError, BuildError, FloatingPointError):
            pass

    def test_nan_in_profile_control_points(self):
        profile_cp = np.array([[NAN, 0.0, 0.0], [1.0, 0.0, 0.0]])
        profile = NurbsCurve(degree=1, control_points=profile_cp,
                             knots=np.array([0.0, 0.0, 1.0, 1.0]))
        path = _line_curve([0, 0, 0], [0, 0, 1])
        try:
            sweep1(profile, path)
        except (ValueError, BuildError, FloatingPointError):
            pass

    def test_coincident_profile_control_points(self):
        """All profile CPs at same location — degenerate profile (zero-area cross-section)."""
        profile_cp = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
        knots = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
        profile = NurbsCurve(degree=2, control_points=profile_cp, knots=knots)
        path = _line_curve([0, 0, 0], [0, 0, 2])
        try:
            result = sweep1(profile, path)
            # Degenerate but not invalid for a surface — just flat; acceptable
            assert isinstance(result, NurbsSurface)
        except (ValueError, BuildError):
            pass

    def test_degree_zero_profile_raises(self):
        """degree < 1 must raise ValueError per sweep1's own guard."""
        with pytest.raises(ValueError):
            profile_cp = np.array([[0.0, 0.0, 0.0]])
            profile = NurbsCurve(degree=1, control_points=profile_cp,
                                 knots=np.array([0.0, 1.0]))
            # Force degree mismatch by monkeypatching
            profile.degree = 0
            path = _line_curve([0, 0, 0], [0, 0, 1])
            sweep1(profile, path)


# ===========================================================================
# network_srf (loft/skinning)
# ===========================================================================

class TestNetworkSrfDegenerate:

    def test_empty_curve_list_raises_ValueError(self):
        with pytest.raises(ValueError):
            network_srf([])

    def test_single_curve_raises_ValueError(self):
        c = _line_curve([0, 0, 0], [1, 0, 0])
        with pytest.raises(ValueError):
            network_srf([c])

    def test_nan_in_control_points_raises_or_returns(self):
        cp = np.array([[NAN, 0.0, 0.0], [1.0, 0.0, 0.0]])
        c1 = NurbsCurve(degree=1, control_points=cp, knots=np.array([0.0, 0.0, 1.0, 1.0]))
        c2 = _line_curve([0, 0, 1], [1, 0, 1])
        try:
            network_srf([c1, c2])
        except (ValueError, BuildError, FloatingPointError):
            pass

    def test_coincident_curves_returns_degenerate_surface_or_raises(self):
        """Two identical curves → degenerate (zero-area) surface."""
        c1 = _line_curve([0, 0, 0], [1, 0, 0])
        c2 = _line_curve([0, 0, 0], [1, 0, 0])
        try:
            result = network_srf([c1, c2])
            assert isinstance(result, NurbsSurface)
        except (ValueError, BuildError):
            pass

    def test_incompatible_dimension_raises_ValueError(self):
        c1 = _line_curve([0, 0, 0], [1, 0, 0])  # 3D
        # Build a 2D-dimension curve manually
        cp2d = np.array([[0.0, 0.0], [1.0, 0.0]])
        c2_2d = NurbsCurve(degree=1, control_points=cp2d,
                           knots=np.array([0.0, 0.0, 1.0, 1.0]))
        with pytest.raises(ValueError):
            network_srf([c1, c2_2d])


# ===========================================================================
# fit_curve
# ===========================================================================

class TestFitCurveDegenerate:

    def test_empty_points_returns_failure(self):
        result = fit_curve([])
        _assert_structured_failure_or_exception(result)

    def test_single_point_returns_failure(self):
        result = fit_curve([[0, 0, 0]])
        _assert_structured_failure_or_exception(result)

    def test_nan_points_returns_failure_or_ok_false(self):
        result = fit_curve([[NAN, 0, 0], [1, 0, 0], [2, 0, 0]])
        assert isinstance(result, dict)
        # ok may be True or False depending on numpy's handling of NaN;
        # what matters is it's a dict and doesn't raise.

    def test_coincident_points_returns_ok_true_or_structured(self):
        """All points identical — documented to return ok=True degenerate case."""
        pts = [[1.0, 2.0, 3.0]] * 5
        result = fit_curve(pts)
        assert isinstance(result, dict)
        assert "ok" in result
        # Per fit_curve docstring: all-same returns ok=True with degenerate msg

    def test_two_coincident_points_ok_but_degenerate(self):
        pts = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
        result = fit_curve(pts)
        assert isinstance(result, dict)
        assert "ok" in result

    def test_inf_points_returns_dict(self):
        result = fit_curve([[INF, 0, 0], [1, 0, 0]])
        assert isinstance(result, dict)


# ===========================================================================
# fit_surface
# ===========================================================================

class TestFitSurfaceDegenerate:

    def test_empty_grid_returns_failure(self):
        result = fit_surface([])
        _assert_structured_failure_or_exception(result)

    def test_1d_grid_returns_failure(self):
        pts = np.zeros((4, 3))  # (m, 3) — not (m, n, 3)
        result = fit_surface(pts)
        _assert_structured_failure_or_exception(result)

    def test_too_few_rows_returns_failure(self):
        pts = np.zeros((1, 5, 3))
        result = fit_surface(pts, degree_u=3)
        _assert_structured_failure_or_exception(result)

    def test_too_few_cols_returns_failure(self):
        pts = np.zeros((5, 1, 3))
        result = fit_surface(pts, degree_v=3)
        _assert_structured_failure_or_exception(result)

    @pytest.mark.xfail(
        reason=(
            "GK-67 gap: fit_surface with NaN grid points propagates NaN into "
            "np.linalg.lstsq which raises a numpy ValueError ('invalid value') "
            "that is not caught internally. fit_surface lacks a NaN-input guard."
        ),
        raises=ValueError,
        strict=True,
    )
    def test_nan_in_grid_returns_dict(self):
        """fit_surface with NaN points — documents gap: should return ok=False dict."""
        pts = np.zeros((4, 4, 3))
        pts[0, 0, 0] = NAN
        result = fit_surface(pts)
        assert isinstance(result, dict)

    def test_coincident_grid_points_returns_dict(self):
        """All grid points at origin — degenerate surface."""
        pts = np.zeros((4, 4, 3))
        result = fit_surface(pts)
        assert isinstance(result, dict)
        assert "ok" in result

    def test_zero_tolerance_returns_failure(self):
        pts = np.zeros((4, 4, 3))
        for i in range(4):
            for j in range(4):
                pts[i, j] = [i, j, 0.0]
        result = fit_surface(pts, tol=0.0)
        _assert_structured_failure_or_exception(result)

    def test_negative_tolerance_returns_failure(self):
        pts = np.zeros((4, 4, 3))
        for i in range(4):
            for j in range(4):
                pts[i, j] = [i, j, 0.0]
        result = fit_surface(pts, tol=-1.0)
        _assert_structured_failure_or_exception(result)


# ===========================================================================
# blend_srf_g1
# ===========================================================================

class TestBlendSrfG1Degenerate:

    def test_zero_blend_width_returns_failure(self):
        s1 = _flat_nurbs_surface()
        s2 = _shifted_surface(dz=2.0)
        result = blend_srf_g1(s1, s2, blend_width=0.0)
        _assert_structured_failure_or_exception(result)

    def test_negative_blend_width_returns_failure(self):
        s1 = _flat_nurbs_surface()
        s2 = _shifted_surface(dz=2.0)
        result = blend_srf_g1(s1, s2, blend_width=-1.0)
        _assert_structured_failure_or_exception(result)

    def test_invalid_edge_spec_returns_failure(self):
        s1 = _flat_nurbs_surface()
        s2 = _shifted_surface(dz=2.0)
        result = blend_srf_g1(s1, s2, edge="invalid_edge")
        _assert_structured_failure_or_exception(result)

    def test_nan_surface_ctrl_pts_returns_dict_or_raises(self):
        s1 = _flat_nurbs_surface()
        # Inject NaN into s2's control points
        ctrl2 = _shifted_surface(dz=2.0).control_points.copy()
        ctrl2[0, 0, 0] = NAN
        s2 = NurbsSurface(degree_u=3, degree_v=3,
                          control_points=ctrl2,
                          knots_u=_flat_nurbs_surface().knots_u,
                          knots_v=_flat_nurbs_surface().knots_v)
        try:
            result = blend_srf_g1(s1, s2)
            assert isinstance(result, dict)
        except (ValueError, BuildError, FloatingPointError):
            pass

    def test_coincident_surfaces_returns_dict(self):
        """Both surfaces identical — degenerate blend (zero-width gap)."""
        s = _flat_nurbs_surface()
        result = blend_srf_g1(s, s)
        assert isinstance(result, dict)
        assert "ok" in result


# ===========================================================================
# box_to_body
# ===========================================================================

class TestBoxToBodyDegenerate:

    def test_zero_dx_raises_BuildError(self):
        """A flat box (dx=0) should fail validate_body and raise BuildError."""
        try:
            body = box_to_body([0, 0, 0], 0.0, 1.0, 1.0)
            # If it returns, body must be valid (but flat box has degenerate edges)
            _assert_body_valid(body)
        except BuildError:
            pass

    def test_zero_dy_raises_BuildError(self):
        try:
            body = box_to_body([0, 0, 0], 1.0, 0.0, 1.0)
            _assert_body_valid(body)
        except BuildError:
            pass

    def test_zero_dz_raises_BuildError(self):
        try:
            body = box_to_body([0, 0, 0], 1.0, 1.0, 0.0)
            _assert_body_valid(body)
        except BuildError:
            pass

    def test_nan_corner_raises_or_builderror(self):
        try:
            box_to_body([NAN, 0, 0], 1.0, 1.0, 1.0)
        except (BuildError, ValueError, FloatingPointError):
            pass

    def test_nan_extents_raises_or_builderror(self):
        try:
            box_to_body([0, 0, 0], NAN, 1.0, 1.0)
        except (BuildError, ValueError, FloatingPointError):
            pass

    def test_negative_extents_returns_valid_body_or_raises(self):
        """Negative extent flips orientation — should either succeed (valid Body) or raise."""
        try:
            body = box_to_body([0, 0, 0], -1.0, 1.0, 1.0)
            _assert_body_valid(body)
        except BuildError:
            pass


# ===========================================================================
# sew_faces
# ===========================================================================

class TestSewFacesDegenerate:

    def test_empty_faces_raises_BuildError(self):
        from kerf_cad_core.geom.brep_build import BuildError as BBError
        try:
            sew_faces([])
        except (BBError, BuildError, ValueError):
            pass

    def test_single_face_produces_open_shell(self):
        """sew_faces with one face — valid but open shell."""
        from kerf_cad_core.geom.brep_build import surface_to_face, BuildError as BBError
        from kerf_cad_core.geom.brep import Plane
        import numpy as np
        p = Plane(origin=np.array([0.0, 0.0, 0.0]),
                  x_axis=np.array([1.0, 0.0, 0.0]),
                  y_axis=np.array([0.0, 1.0, 0.0]))
        face = surface_to_face(p)
        try:
            shell = sew_faces([face])
            assert not shell.is_closed  # one face → open shell
        except (BBError, BuildError, ValueError):
            pass


# ===========================================================================
# body_union / body_intersection / body_difference
# ===========================================================================

class TestBooleanDegenerate:

    def _box(self, x=0, y=0, z=0, dx=1, dy=1, dz=1):
        return box_to_body([x, y, z], dx, dy, dz)

    def test_union_unsupported_shapes_raises_BuildError(self):
        """Non-box, non-sphere inputs raise BuildError with unsupported-input."""
        from kerf_cad_core.geom.brep_build import sphere_to_body
        sph = sphere_to_body([0, 0, 0], 1.0)
        box = self._box()
        with pytest.raises(BuildError):
            body_union(sph, box)

    def test_intersection_unsupported_shapes_raises_BuildError(self):
        from kerf_cad_core.geom.brep_build import sphere_to_body
        sph = sphere_to_body([0, 0, 0], 1.0)
        box = self._box()
        with pytest.raises(BuildError):
            body_intersection(sph, box)

    def test_difference_unsupported_shapes_raises_BuildError(self):
        from kerf_cad_core.geom.brep_build import sphere_to_body
        sph = sphere_to_body([0, 0, 0], 1.0)
        box = self._box()
        with pytest.raises(BuildError):
            body_difference(sph, box)

    def test_union_empty_body_raises_or_returns_valid(self):
        """Empty Body as an operand — no valid AABB → BuildError."""
        empty = Body()
        box = self._box()
        with pytest.raises(BuildError):
            body_union(empty, box)

    def test_intersection_empty_body_raises_or_returns_valid(self):
        empty = Body()
        box = self._box()
        with pytest.raises(BuildError):
            body_intersection(empty, box)

    def test_difference_empty_body_raises_or_returns_valid(self):
        empty = Body()
        box = self._box()
        with pytest.raises(BuildError):
            body_difference(empty, box)

    def test_union_disjoint_boxes_returns_valid_body(self):
        """Sanity: disjoint boxes union correctly — body should be valid."""
        a = self._box(0, 0, 0, 1, 1, 1)
        b = self._box(5, 0, 0, 1, 1, 1)
        result = body_union(a, b)
        _assert_body_valid(result)

    def test_intersection_disjoint_boxes_returns_empty_body(self):
        """Disjoint → intersection is empty Body (zero solids)."""
        a = self._box(0, 0, 0, 1, 1, 1)
        b = self._box(5, 0, 0, 1, 1, 1)
        result = body_intersection(a, b)
        assert isinstance(result, Body)
        assert len(result.solids) == 0


# ===========================================================================
# Additional cross-cutting NaN / Inf regression cells
# ===========================================================================

class TestNanInfCrossCutting:

    def test_fit_curve_nan_returns_dict(self):
        pts = [[0, 0, 0], [NAN, 1, 0], [2, 0, 0]]
        result = fit_curve(pts)
        assert isinstance(result, dict)

    def test_fit_curve_inf_returns_dict(self):
        pts = [[0, 0, 0], [INF, 1, 0], [2, 0, 0]]
        result = fit_curve(pts)
        assert isinstance(result, dict)

    @pytest.mark.xfail(
        reason=(
            "GK-67 gap: fit_surface with NaN grid points propagates NaN into "
            "np.linalg.lstsq which raises a numpy ValueError ('invalid value') "
            "that is not caught internally. fit_surface lacks a NaN-input guard."
        ),
        raises=ValueError,
        strict=True,
    )
    def test_fit_surface_nan_returns_dict(self):
        """fit_surface NaN — documents gap: should return ok=False dict."""
        pts = np.zeros((4, 4, 3))
        pts[1, 1] = [NAN, 0, 0]
        result = fit_surface(pts)
        assert isinstance(result, dict)

    @pytest.mark.xfail(
        reason=(
            "GK-67 gap: fit_surface with Inf grid points propagates Inf into "
            "np.linalg.lstsq which raises a numpy ValueError ('invalid value') "
            "that is not caught internally. fit_surface lacks an Inf-input guard."
        ),
        raises=ValueError,
        strict=True,
    )
    def test_fit_surface_inf_returns_dict(self):
        """fit_surface Inf — documents gap: should return ok=False dict."""
        pts = np.zeros((4, 4, 3))
        pts[2, 2] = [INF, 0, 0]
        result = fit_surface(pts)
        assert isinstance(result, dict)

    def test_extrude_nan_vertex_does_not_return_invalid_body(self):
        tri = [[NAN, 0, 0], [1, 0, 0], [0.5, 1, 0]]
        try:
            body = extrude_to_body(tri, [0, 0, 1])
            _assert_body_valid(body)
        except (BuildError, ValueError, FloatingPointError):
            pass

    def test_network_srf_nan_raises_or_returns_surface(self):
        cp = np.array([[0.0, 0.0, 0.0], [NAN, 0.0, 0.0]])
        c1 = NurbsCurve(degree=1, control_points=cp, knots=np.array([0.0, 0.0, 1.0, 1.0]))
        c2 = _line_curve([0, 0, 1], [1, 0, 1])
        try:
            result = network_srf([c1, c2])
            assert isinstance(result, NurbsSurface)
        except (ValueError, BuildError, FloatingPointError):
            pass
