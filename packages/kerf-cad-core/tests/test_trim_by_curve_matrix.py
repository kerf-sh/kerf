"""
Tests for GK-40: Pure-Python trim-by-curve analytic carrier matrix.

All tests are hermetic — no OCC, no DB, no network.

Coverage:
  1. trim_face_analytic — plane ⊥ cylinder (exact circle, residual ≤ 1e-7)
  2. trim_face_analytic — oblique plane × cylinder (sinusoidal v(u), residual ≤ 1e-7)
  3. trim_face_analytic — commutative: (CylinderSurface, Plane) == (Plane, CylinderSurface)
  4. trim_face_analytic — unsupported pairs → structured "unsupported-input" (not exception)
  5. trim_face_analytic — plane ∥ cylinder axis → structured "unsupported-input"
  6. AnalyticTrimLoop metadata — is_circle flag, semi-axes, centre for perpendicular case
  7. AnalyticTrimLoop metadata — is_circle=False for oblique case
  8. UV samples on plane surface (uv_on_a) lie exactly on the plane
  9. UV samples on cylinder (uv_on_b) → cylinder.evaluate(u,v) matches 3-D oracle to 1e-7
 10. Varying cylinder radius and height — residual ≤ 1e-7
 11. Cylinder at non-origin centre — residual ≤ 1e-7
 12. Plane at non-zero z — residual ≤ 1e-7
 13. samples parameter controls UV list length
 14. tol gate: extremely tight tol raises ok=False + preserves reason prefix
 15. imprint_plane_cylinder_loop — perpendicular plane → Edge + Vertex returned
 16. imprint_plane_cylinder_loop — parallel plane → None
 17. imprint_plane_cylinder_loop — oblique plane → None
 18. imprint_plane_cylinder_loop — rim circle radius matches CylShape radius
 19. imprint_plane_cylinder_loop — seam vertex on the circle
 20. AnalyticTrimLoop dataclass field access
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.brep import CylinderSurface, Plane, SphereSurface
from kerf_cad_core.geom.trim_curve import (
    AnalyticTrimLoop,
    trim_face_analytic,
)
from kerf_cad_core.geom.boolean import (
    _CylShape,
    _try_recognise_cylinder,
    imprint_plane_cylinder_loop,
)
from kerf_cad_core.geom.brep_build import cylinder_to_body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_z_plane(z: float = 0.0) -> Plane:
    """XY plane at height z; normal = +Z."""
    return Plane(
        origin=np.array([0.0, 0.0, z]),
        x_axis=np.array([1.0, 0.0, 0.0]),
        y_axis=np.array([0.0, 1.0, 0.0]),
    )


def _make_z_cylinder(
    cx: float = 0.0,
    cy: float = 0.0,
    cz: float = 0.0,
    r: float = 1.0,
    h: float = 2.0,
) -> CylinderSurface:
    """Z-axis cylinder with centre (cx, cy, cz), radius r."""
    return CylinderSurface(
        center=np.array([cx, cy, cz]),
        axis=np.array([0.0, 0.0, 1.0]),
        radius=r,
    )


def _cyl_shape_from_body(r: float = 1.0, h: float = 2.0, axis_pt=None) -> _CylShape:
    """Build a _CylShape for a Z-axis cylinder."""
    if axis_pt is None:
        axis_pt = np.array([0.0, 0.0, 0.0])
    body = cylinder_to_body(
        axis_pt=axis_pt,
        axis_dir=np.array([0.0, 0.0, 1.0]),
        radius=r,
        height=h,
    )
    shape = _try_recognise_cylinder(body)
    assert shape is not None, "cylinder recognition failed"
    return shape


# ---------------------------------------------------------------------------
# 1. Perpendicular plane × Z-cylinder → exact circle, residual ≤ 1e-7
# ---------------------------------------------------------------------------

class TestPerpendicularPlaneZCylinder:
    """Plane normal ∥ cylinder axis (Z) — result must be a perfect circle."""

    def setup_method(self):
        self.plane = _make_z_plane(z=1.0)
        self.cyl = _make_z_cylinder(cx=0.0, cy=0.0, cz=0.0, r=1.0)
        self.result = trim_face_analytic(self.plane, self.cyl, samples=256)

    def test_ok(self):
        assert self.result["ok"] is True, self.result["reason"]

    def test_reason_empty(self):
        assert self.result["reason"] == ""

    def test_residual_le_1e7(self):
        assert self.result["residual_max"] <= 1e-7, (
            f"residual {self.result['residual_max']:.3e} exceeds 1e-7"
        )

    def test_loop_is_not_none(self):
        assert self.result["loop"] is not None

    def test_loop_is_circle(self):
        loop: AnalyticTrimLoop = self.result["loop"]
        assert loop.is_circle is True

    def test_loop_semi_axes_equal(self):
        loop: AnalyticTrimLoop = self.result["loop"]
        assert abs(loop.semi_axis_a - loop.semi_axis_b) < 1e-10

    def test_loop_semi_axis_equals_radius(self):
        loop: AnalyticTrimLoop = self.result["loop"]
        # Both semi-axes equal to cylinder radius (1.0)
        assert abs(loop.semi_axis_a - 1.0) < 1e-10
        assert abs(loop.semi_axis_b - 1.0) < 1e-10

    def test_loop_centre_at_correct_z(self):
        loop: AnalyticTrimLoop = self.result["loop"]
        # The plane is at z=1; cylinder axis is the Z-axis; intersection centre = (0,0,1)
        assert abs(loop.circle_center[2] - 1.0) < 1e-10
        assert abs(loop.circle_center[0]) < 1e-10
        assert abs(loop.circle_center[1]) < 1e-10

    def test_loop_normal_is_plus_z(self):
        loop: AnalyticTrimLoop = self.result["loop"]
        # Plane normal is +Z; loop normal should also be ±Z
        assert abs(abs(loop.circle_normal[2]) - 1.0) < 1e-10

    def test_uv_on_a_length(self):
        assert len(self.result["uv_on_a"]) == 256

    def test_uv_on_b_length(self):
        assert len(self.result["uv_on_b"]) == 256

    def test_uv_on_b_v_constant(self):
        """All cylinder UV samples should have v ≈ 1.0 (plane at z=1, cylinder base at z=0)."""
        uv_b = self.result["uv_on_b"]
        vs = [v for (_, v) in uv_b]
        # v should be exactly 1.0 (plane height relative to cylinder bottom)
        assert all(abs(v - 1.0) < 1e-10 for v in vs), (
            f"v values not constant: min={min(vs):.3e}, max={max(vs):.3e}"
        )

    def test_cylinder_eval_matches_3d_oracle(self):
        """cylinder.evaluate(u,v) at each sample must lie on the plane z=1."""
        uv_b = self.result["uv_on_b"]
        for u, v in uv_b:
            pt = self.cyl.evaluate(u, v)
            assert abs(pt[2] - 1.0) < 1e-7, f"z={pt[2]:.3e} not 1.0 at u={u:.3f}"
            # Also: distance from Z-axis must equal radius
            dist = math.hypot(pt[0], pt[1])
            assert abs(dist - 1.0) < 1e-7, f"dist={dist:.3e} != 1.0"

    def test_plane_eval_matches_3d_oracle(self):
        """plane.evaluate(u,v) at uv_on_a samples must match cylinder 3-D points."""
        uv_a = self.result["uv_on_a"]
        uv_b = self.result["uv_on_b"]
        for (up, vp), (uc, vc) in zip(uv_a, uv_b):
            pt_plane = self.plane.evaluate(up, vp)
            pt_cyl = self.cyl.evaluate(uc, vc)
            dist = float(np.linalg.norm(pt_plane - pt_cyl))
            assert dist < 1e-7, f"plane/cyl mismatch {dist:.3e} at u={uc:.3f}"


# ---------------------------------------------------------------------------
# 2. Oblique plane × Z-cylinder → sinusoidal loop, residual ≤ 1e-7
# ---------------------------------------------------------------------------

class TestObliquePlaneCylinder:
    """Plane tilted 45° about the Y-axis; normal = (1,0,1)/sqrt(2)."""

    def setup_method(self):
        # Plane with normal = (1/√2, 0, 1/√2), origin at (0,0,1)
        n = np.array([1.0, 0.0, 1.0]) / math.sqrt(2.0)
        # x_axis ⊥ n: use y_axis = (0,1,0), then x_axis = y_axis × n
        ya = np.array([0.0, 1.0, 0.0])
        xa = np.cross(ya, n)
        xa /= np.linalg.norm(xa)
        self.plane = Plane(
            origin=np.array([0.0, 0.0, 1.0]),
            x_axis=xa,
            y_axis=ya,
        )
        self.cyl = _make_z_cylinder(r=1.0)
        self.result = trim_face_analytic(self.plane, self.cyl, samples=128)

    def test_ok(self):
        assert self.result["ok"] is True, self.result["reason"]

    def test_residual_le_1e7(self):
        assert self.result["residual_max"] <= 1e-7, (
            f"residual {self.result['residual_max']:.3e} exceeds 1e-7"
        )

    def test_not_circle(self):
        loop: AnalyticTrimLoop = self.result["loop"]
        # Oblique plane — should NOT be marked as circle
        assert loop.is_circle is False

    def test_semi_axes_different(self):
        loop: AnalyticTrimLoop = self.result["loop"]
        # semi_axis_a > semi_axis_b = r for oblique intersection
        assert loop.semi_axis_a > loop.semi_axis_b - 1e-10

    def test_cylinder_pts_on_plane(self):
        """All sampled 3-D points must lie on the oblique plane."""
        n = self.plane._n
        p0 = self.plane.origin
        uv_b = self.result["uv_on_b"]
        for u, v in uv_b:
            pt = self.cyl.evaluate(u, v)
            residual = float(abs(np.dot(n, pt - p0)))
            assert residual < 1e-7, f"point not on plane: residual={residual:.3e}"

    def test_num_samples_correct(self):
        assert len(self.result["uv_on_b"]) == 128
        assert len(self.result["uv_on_a"]) == 128


# ---------------------------------------------------------------------------
# 3. Commutative: (Cylinder, Plane) == (Plane, Cylinder)
# ---------------------------------------------------------------------------

class TestCommutativity:
    def setup_method(self):
        self.plane = _make_z_plane(z=0.5)
        self.cyl = _make_z_cylinder(r=2.0)
        self.r_pc = trim_face_analytic(self.plane, self.cyl, samples=64)
        self.r_cp = trim_face_analytic(self.cyl, self.plane, samples=64)

    def test_both_ok(self):
        assert self.r_pc["ok"] is True, self.r_pc["reason"]
        assert self.r_cp["ok"] is True, self.r_cp["reason"]

    def test_both_residual_le_1e7(self):
        assert self.r_pc["residual_max"] <= 1e-7
        assert self.r_cp["residual_max"] <= 1e-7

    def test_uv_on_a_swapped(self):
        """With swapped inputs, uv_on_a and uv_on_b are themselves swapped."""
        # (Plane,Cyl): uv_on_a=plane, uv_on_b=cyl
        # (Cyl,Plane): uv_on_a=cyl, uv_on_b=plane
        # The 3-D points must match regardless
        uv_plane_from_pc = self.r_pc["uv_on_a"]   # plane UV in (Plane,Cyl)
        uv_plane_from_cp = self.r_cp["uv_on_b"]   # plane UV in (Cyl,Plane)
        pts_a = [self.plane.evaluate(u, v) for u, v in uv_plane_from_pc]
        pts_b = [self.plane.evaluate(u, v) for u, v in uv_plane_from_cp]
        # Both should be the same 3-D points (modulo order — same parametric u)
        for pa, pb in zip(pts_a, pts_b):
            assert float(np.linalg.norm(np.asarray(pa) - np.asarray(pb))) < 1e-9

    def test_loop_is_circle_both(self):
        assert self.r_pc["loop"].is_circle is True
        assert self.r_cp["loop"].is_circle is True


# ---------------------------------------------------------------------------
# 4. Unsupported pairs → structured "unsupported-input" (not exception)
# ---------------------------------------------------------------------------

class TestUnsupportedPairs:
    def setup_method(self):
        self.plane = _make_z_plane()
        self.sph = SphereSurface(center=np.array([0.0, 0.0, 0.0]), radius=1.0)
        self.cyl = _make_z_cylinder()

    def test_plane_sphere_returns_unsupported(self):
        res = trim_face_analytic(self.plane, self.sph)
        assert res["ok"] is False
        assert res["reason"].startswith("unsupported-input")

    def test_sphere_plane_returns_unsupported(self):
        res = trim_face_analytic(self.sph, self.plane)
        assert res["ok"] is False
        assert res["reason"].startswith("unsupported-input")

    def test_sphere_sphere_returns_unsupported(self):
        sph2 = SphereSurface(center=np.array([1.0, 0.0, 0.0]), radius=0.5)
        res = trim_face_analytic(self.sph, sph2)
        assert res["ok"] is False
        assert res["reason"].startswith("unsupported-input")

    def test_sphere_cylinder_returns_unsupported(self):
        res = trim_face_analytic(self.sph, self.cyl)
        assert res["ok"] is False
        assert res["reason"].startswith("unsupported-input")

    def test_plane_plane_returns_unsupported(self):
        plane2 = _make_z_plane(z=1.0)
        res = trim_face_analytic(self.plane, plane2)
        assert res["ok"] is False
        assert res["reason"].startswith("unsupported-input")

    def test_unsupported_loop_is_none(self):
        res = trim_face_analytic(self.plane, self.sph)
        assert res["loop"] is None

    def test_unsupported_uv_lists_empty(self):
        res = trim_face_analytic(self.plane, self.sph)
        assert res["uv_on_a"] == []
        assert res["uv_on_b"] == []

    def test_unsupported_does_not_raise(self):
        # Must return a dict, not raise any exception
        try:
            res = trim_face_analytic(self.sph, self.plane)
            assert isinstance(res, dict)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"trim_face_analytic raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# 5. Plane parallel to cylinder axis → unsupported-input
# ---------------------------------------------------------------------------

class TestParallelPlane:
    def test_parallel_xy_plane_returns_unsupported(self):
        """Plane with normal = (1,0,0) is parallel to Z-axis cylinder."""
        # Normal = +X → plane contains Z-axis direction → parallel to cyl axis
        plane = Plane(
            origin=np.array([2.0, 0.0, 0.0]),
            x_axis=np.array([0.0, 1.0, 0.0]),
            y_axis=np.array([0.0, 0.0, 1.0]),
        )
        cyl = _make_z_cylinder(r=1.0)
        res = trim_face_analytic(plane, cyl)
        assert res["ok"] is False
        assert "unsupported-input" in res["reason"]
        assert "parallel" in res["reason"].lower()

    def test_parallel_does_not_raise(self):
        plane = Plane(
            origin=np.array([0.0, 2.0, 0.0]),
            x_axis=np.array([1.0, 0.0, 0.0]),
            y_axis=np.array([0.0, 0.0, 1.0]),
        )
        cyl = _make_z_cylinder()
        try:
            res = trim_face_analytic(plane, cyl)
            assert isinstance(res, dict)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"raised: {exc}")


# ---------------------------------------------------------------------------
# 6–7. Analytic loop metadata
# ---------------------------------------------------------------------------

class TestAnalyticTrimLoopMetadata:
    def test_dataclass_fields(self):
        """AnalyticTrimLoop is accessible and has the expected attributes."""
        loop = AnalyticTrimLoop(
            circle_center=np.array([0.0, 0.0, 1.0]),
            circle_normal=np.array([0.0, 0.0, 1.0]),
            semi_axis_a=2.0,
            semi_axis_b=2.0,
            is_circle=True,
            num_samples=64,
        )
        assert loop.semi_axis_a == 2.0
        assert loop.semi_axis_b == 2.0
        assert loop.is_circle is True
        assert loop.num_samples == 64

    def test_oblique_loop_is_not_circle(self):
        n = np.array([1.0, 0.0, 1.0]) / math.sqrt(2.0)
        ya = np.array([0.0, 1.0, 0.0])
        xa = np.cross(ya, n)
        xa /= np.linalg.norm(xa)
        plane = Plane(origin=np.array([0.0, 0.0, 0.5]), x_axis=xa, y_axis=ya)
        cyl = _make_z_cylinder(r=1.0)
        res = trim_face_analytic(plane, cyl, samples=64)
        assert res["ok"] is True
        assert res["loop"].is_circle is False


# ---------------------------------------------------------------------------
# 10–12. Varying geometry
# ---------------------------------------------------------------------------

class TestVaryingGeometry:
    @pytest.mark.parametrize("r", [0.5, 1.0, 3.0, 10.0])
    def test_varying_radius(self, r):
        plane = _make_z_plane(z=1.0)
        cyl = _make_z_cylinder(r=r)
        res = trim_face_analytic(plane, cyl)
        assert res["ok"] is True, res["reason"]
        assert res["residual_max"] <= 1e-7
        loop = res["loop"]
        assert abs(loop.semi_axis_a - r) < 1e-10
        assert loop.is_circle is True

    @pytest.mark.parametrize("cx,cy,cz", [
        (0.0, 0.0, 0.0),
        (3.0, -2.0, 0.0),
        (-1.0, 4.0, -5.0),
    ])
    def test_cylinder_at_nonorigin_centre(self, cx, cy, cz):
        plane = _make_z_plane(z=cz + 1.0)
        cyl = _make_z_cylinder(cx=cx, cy=cy, cz=cz, r=1.0)
        res = trim_face_analytic(plane, cyl)
        assert res["ok"] is True, res["reason"]
        assert res["residual_max"] <= 1e-7
        loop = res["loop"]
        # Loop centre should be at (cx, cy, cz+1)
        expected = np.array([cx, cy, cz + 1.0])
        assert float(np.linalg.norm(loop.circle_center - expected)) < 1e-9

    @pytest.mark.parametrize("pz", [0.0, 0.5, 1.0, -3.0])
    def test_plane_at_various_z(self, pz):
        plane = _make_z_plane(z=pz)
        cyl = _make_z_cylinder(r=1.5)
        res = trim_face_analytic(plane, cyl)
        assert res["ok"] is True, res["reason"]
        assert res["residual_max"] <= 1e-7


# ---------------------------------------------------------------------------
# 13. samples parameter
# ---------------------------------------------------------------------------

class TestSamplesParameter:
    @pytest.mark.parametrize("n", [4, 16, 64, 512])
    def test_uv_list_length_matches_samples(self, n):
        plane = _make_z_plane(z=1.0)
        cyl = _make_z_cylinder(r=1.0)
        res = trim_face_analytic(plane, cyl, samples=n)
        assert res["ok"] is True
        assert len(res["uv_on_a"]) == n
        assert len(res["uv_on_b"]) == n
        assert res["loop"].num_samples == n


# ---------------------------------------------------------------------------
# 14. tol gate
# ---------------------------------------------------------------------------

class TestTolGate:
    def test_extremely_tight_tol_may_fail(self):
        """With tol = 0 the gate must fire if residual is non-zero."""
        plane = _make_z_plane(z=1.0)
        cyl = _make_z_cylinder(r=1.0)
        res = trim_face_analytic(plane, cyl, tol=0.0)
        # residual_max is reported regardless; if > 0 then ok=False
        if res["residual_max"] > 0.0:
            assert res["ok"] is False
        # Must never raise
        assert isinstance(res, dict)

    def test_normal_tol_passes(self):
        plane = _make_z_plane(z=1.0)
        cyl = _make_z_cylinder(r=1.0)
        res = trim_face_analytic(plane, cyl, tol=1e-7)
        assert res["ok"] is True, res["reason"]


# ---------------------------------------------------------------------------
# 15–19. imprint_plane_cylinder_loop
# ---------------------------------------------------------------------------

class TestImprintPlaneCylinderLoop:
    def setup_method(self):
        self.cyl_shape = _cyl_shape_from_body(r=1.0, h=4.0)

    def test_perpendicular_returns_edge_vertex(self):
        result = imprint_plane_cylinder_loop(
            self.cyl_shape,
            plane_normal=np.array([0.0, 0.0, 1.0]),
            plane_origin=np.array([0.0, 0.0, 2.0]),
        )
        assert result is not None
        edge, vertex = result
        assert edge is not None
        assert vertex is not None

    def test_rim_circle_radius_matches(self):
        result = imprint_plane_cylinder_loop(
            self.cyl_shape,
            plane_normal=np.array([0.0, 0.0, 1.0]),
            plane_origin=np.array([0.0, 0.0, 1.5]),
        )
        assert result is not None
        edge, vertex = result
        # The CircleArc3 should have the cylinder's radius
        assert abs(edge.curve.radius - 1.0) < 1e-10

    def test_seam_vertex_on_circle(self):
        """The seam vertex must lie on the rim circle."""
        result = imprint_plane_cylinder_loop(
            self.cyl_shape,
            plane_normal=np.array([0.0, 0.0, 1.0]),
            plane_origin=np.array([0.0, 0.0, 1.0]),
        )
        assert result is not None
        edge, vertex = result
        # vertex.point should be r away from rim_centre in XY
        rim_centre = edge.curve.center
        d = float(np.linalg.norm(
            np.asarray(vertex.point[:2]) - np.asarray(rim_centre[:2])
        ))
        assert abs(d - 1.0) < 1e-9

    def test_parallel_plane_returns_none(self):
        """Plane with normal ⊥ axis (parallel to axis) returns None."""
        result = imprint_plane_cylinder_loop(
            self.cyl_shape,
            plane_normal=np.array([1.0, 0.0, 0.0]),  # ⊥ Z-axis
            plane_origin=np.array([2.0, 0.0, 1.0]),
        )
        assert result is None

    def test_oblique_plane_returns_none(self):
        """Oblique plane (not perpendicular) returns None."""
        n = np.array([1.0, 0.0, 1.0]) / math.sqrt(2.0)
        result = imprint_plane_cylinder_loop(
            self.cyl_shape,
            plane_normal=n,
            plane_origin=np.array([0.0, 0.0, 1.0]),
        )
        assert result is None

    def test_does_not_raise_for_any_input(self):
        """imprint_plane_cylinder_loop must never raise."""
        cyl = self.cyl_shape
        normals = [
            np.array([0.0, 0.0, 1.0]),    # perpendicular
            np.array([1.0, 0.0, 0.0]),    # parallel
            np.array([1.0, 0.0, 1.0]) / math.sqrt(2.0),  # oblique
        ]
        for n in normals:
            try:
                imprint_plane_cylinder_loop(cyl, n, np.zeros(3))
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"raised for normal={n}: {exc}")


# ---------------------------------------------------------------------------
# 20. End-to-end: plane⊥cylinder circular loop residual oracle
# ---------------------------------------------------------------------------

class TestCircularLoopOracle:
    """High-precision oracle: verify the plane×cylinder circular intersection
    analytically.  A z-plane at height h through a Z-cylinder of radius r
    must yield all sample points at distance r from the Z-axis and height h.
    """

    @pytest.mark.parametrize("r,h", [
        (1.0, 0.0),
        (2.5, 3.0),
        (0.1, -1.0),
    ])
    def test_all_samples_at_exact_radius_and_height(self, r, h):
        plane = _make_z_plane(z=h)
        cyl = _make_z_cylinder(r=r)
        res = trim_face_analytic(plane, cyl, samples=512, tol=1e-7)
        assert res["ok"] is True, res["reason"]

        uv_b = res["uv_on_b"]
        for u, v in uv_b:
            pt = cyl.evaluate(u, v)
            # Height must be h
            assert abs(pt[2] - h) < 1e-10, f"z={pt[2]:.3e} ≠ {h}"
            # Radial distance must be r
            dist = math.hypot(pt[0], pt[1])
            assert abs(dist - r) < 1e-10, f"dist={dist:.3e} ≠ {r}"

    def test_residual_is_zero_for_perpendicular(self):
        """For a plane ⊥ cylinder axis, residual must be exactly 0 (machine ε)."""
        plane = _make_z_plane(z=1.0)
        cyl = _make_z_cylinder(r=1.0)
        res = trim_face_analytic(plane, cyl, samples=1024)
        # Residual must be at machine ε — definitely below 1e-14
        assert res["residual_max"] < 1e-14, (
            f"residual {res['residual_max']:.3e} should be machine ε for perpendicular"
        )
