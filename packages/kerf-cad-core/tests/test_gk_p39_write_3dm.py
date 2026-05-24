"""GK-P39 tests — write_3dm kernel integration + read→write→read Hausdorff oracle.

The Hausdorff oracle verifies that:
  1. A NurbsSurface is written to a .3dm file via write_3dm.
  2. The file is read back via read_3dm.
  3. The Hausdorff deviation between the written and read-back surface is
     within ε = 1e-6 (for exact round-trip through the minimal fixture format).

Also tests:
  - write_3dm is importable from kerf_cad_core.geom.
  - Body with NURBS faces is serialised.
  - write_3dm with explicit surfaces/curves list.
  - Error on empty input.
"""

from __future__ import annotations

import math
import os
import tempfile
from typing import List

import numpy as np
import pytest

from kerf_cad_core.geom import read_3dm, write_3dm, Rhino3dmReadError
from kerf_cad_core.geom.io.rhino3dm import (
    _make_sphere_nurbs_surface,
    _body_to_nurbs_surfaces,
    _analytic_to_nurbs,
    make_minimal_sphere_3dm,
)
from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_and_read(surfaces=None, curves=None, body=None):
    """Write to a temp file, read back, return (result_dict, tmp_path)."""
    with tempfile.NamedTemporaryFile(suffix=".3dm", delete=False) as f:
        tmp = f.name
    try:
        counts = write_3dm(body, tmp, surfaces=surfaces, curves=curves)
        result = read_3dm(tmp)
        return counts, result, tmp
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _make_bilinear_patch() -> NurbsSurface:
    """Bilinear degree-1 surface: unit square in XY."""
    pts = np.zeros((2, 2, 3))
    pts[0, 0] = [0, 0, 0]
    pts[1, 0] = [1, 0, 0]
    pts[0, 1] = [0, 1, 0]
    pts[1, 1] = [1, 1, 0]
    ku = np.array([0.0, 0.0, 1.0, 1.0])
    kv = np.array([0.0, 0.0, 1.0, 1.0])
    return NurbsSurface(degree_u=1, degree_v=1, control_points=pts,
                        knots_u=ku, knots_v=kv)


def _make_nurbs_curve() -> NurbsCurve:
    """Simple line NurbsCurve."""
    pts = np.array([[0, 0, 0], [1, 1, 0], [2, 0, 0]], dtype=float)
    knots = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    return NurbsCurve(degree=2, control_points=pts, knots=knots)


def _hausdorff_surfaces(a: NurbsSurface, b: NurbsSurface, n: int = 20) -> float:
    """Compute approximate Hausdorff deviation between two NurbsSurfaces.

    Samples both surfaces on an n×n grid and returns the maximum of the
    minimum distances.
    """
    us = np.linspace(0.0, 1.0, n)
    vs = np.linspace(0.0, 1.0, n)

    def _sample(srf: NurbsSurface) -> np.ndarray:
        pts = []
        u0 = float(srf.knots_u[srf.degree_u])
        u1 = float(srf.knots_u[-srf.degree_u - 1])
        v0 = float(srf.knots_v[srf.degree_v])
        v1 = float(srf.knots_v[-srf.degree_v - 1])
        for ut in us:
            for vt in vs:
                u = u0 + ut * (u1 - u0)
                v = v0 + vt * (v1 - v0)
                p = np.asarray(srf.evaluate(u, v), dtype=float).ravel()
                pts.append(p[:3])
        return np.array(pts)

    pts_a = _sample(a)
    pts_b = _sample(b)

    # Hausdorff: max over pts_a of min distance to pts_b, and vice versa.
    def _directed(src, tgt):
        dists = np.min(np.linalg.norm(src[:, None] - tgt[None, :], axis=2), axis=1)
        return float(np.max(dists))

    return max(_directed(pts_a, pts_b), _directed(pts_b, pts_a))


# ===========================================================================
# Tests: importability
# ===========================================================================

class TestWriteImport:
    def test_write_3dm_importable_from_geom(self):
        from kerf_cad_core.geom import write_3dm as fn  # noqa: F401
        assert callable(fn)

    def test_write_3dm_importable_from_rhino3dm(self):
        from kerf_cad_core.geom.io.rhino3dm import write_3dm as fn  # noqa: F401
        assert callable(fn)


# ===========================================================================
# Tests: Hausdorff round-trip oracle (sphere)
# ===========================================================================

class TestHausdorffRoundTrip:
    """Core GK-P39 oracle: read → write → read, Hausdorff ≤ ε."""

    def _sphere_surface(self, radius: float = 1.0) -> NurbsSurface:
        return _make_sphere_nurbs_surface(radius)

    def test_sphere_write_read_surfaces_count(self):
        srf = self._sphere_surface()
        _, result, _ = _write_and_read(surfaces=[srf], body=None)
        assert len(result["surfaces"]) == 1

    def test_sphere_hausdorff_zero(self):
        """Exact round-trip through minimal format: Hausdorff = 0."""
        srf = self._sphere_surface(radius=1.0)
        _, result, _ = _write_and_read(surfaces=[srf], body=None)
        read_srf = result["surfaces"][0]
        h = _hausdorff_surfaces(srf, read_srf, n=10)
        assert h < 1e-6, f"Hausdorff {h:.2e} exceeds 1e-6"

    def test_sphere_r3_hausdorff_zero(self):
        srf = self._sphere_surface(radius=3.0)
        _, result, _ = _write_and_read(surfaces=[srf], body=None)
        read_srf = result["surfaces"][0]
        h = _hausdorff_surfaces(srf, read_srf, n=10)
        assert h < 1e-6

    def test_bilinear_patch_hausdorff_zero(self):
        srf = _make_bilinear_patch()
        _, result, _ = _write_and_read(surfaces=[srf], body=None)
        assert len(result["surfaces"]) >= 1
        read_srf = result["surfaces"][0]
        h = _hausdorff_surfaces(srf, read_srf, n=5)
        assert h < 1e-6

    def test_control_points_preserved(self):
        """Control points of the read-back surface must match written surface."""
        srf = self._sphere_surface(radius=2.0)
        _, result, _ = _write_and_read(surfaces=[srf], body=None)
        read_srf = result["surfaces"][0]
        assert np.allclose(srf.control_points, read_srf.control_points, atol=1e-9)

    def test_knots_u_preserved(self):
        srf = self._sphere_surface()
        _, result, _ = _write_and_read(surfaces=[srf], body=None)
        read_srf = result["surfaces"][0]
        assert np.allclose(srf.knots_u, read_srf.knots_u, atol=1e-12)

    def test_knots_v_preserved(self):
        srf = self._sphere_surface()
        _, result, _ = _write_and_read(surfaces=[srf], body=None)
        read_srf = result["surfaces"][0]
        assert np.allclose(srf.knots_v, read_srf.knots_v, atol=1e-12)

    def test_weights_preserved(self):
        srf = self._sphere_surface()
        _, result, _ = _write_and_read(surfaces=[srf], body=None)
        read_srf = result["surfaces"][0]
        assert read_srf.weights is not None
        assert np.allclose(srf.weights, read_srf.weights, atol=1e-12)

    def test_degree_preserved(self):
        srf = self._sphere_surface()
        _, result, _ = _write_and_read(surfaces=[srf], body=None)
        read_srf = result["surfaces"][0]
        assert read_srf.degree_u == srf.degree_u
        assert read_srf.degree_v == srf.degree_v


# ===========================================================================
# Tests: write_3dm return value
# ===========================================================================

class TestWriteReturnValue:
    def test_returns_dict(self):
        srf = _make_sphere_nurbs_surface()
        counts, _, _ = _write_and_read(surfaces=[srf], body=None)
        assert isinstance(counts, dict)

    def test_surface_count_correct(self):
        srf = _make_sphere_nurbs_surface()
        counts, _, _ = _write_and_read(surfaces=[srf], body=None)
        assert counts["surfaces"] == 1

    def test_curve_count_correct(self):
        crv = _make_nurbs_curve()
        counts, _, _ = _write_and_read(curves=[crv], body=None)
        assert counts["curves"] == 1

    def test_both_surfaces_and_curves(self):
        srf = _make_sphere_nurbs_surface()
        crv = _make_nurbs_curve()
        counts, _, _ = _write_and_read(surfaces=[srf], curves=[crv], body=None)
        assert counts["surfaces"] == 1
        assert counts["curves"] == 1

    def test_multiple_surfaces(self):
        srfs = [_make_bilinear_patch(), _make_sphere_nurbs_surface()]
        counts, result, _ = _write_and_read(surfaces=srfs, body=None)
        assert counts["surfaces"] == 2
        assert len(result["surfaces"]) == 2


# ===========================================================================
# Tests: error handling
# ===========================================================================

class TestWriteErrors:
    def test_empty_input_raises(self):
        with pytest.raises(ValueError, match="nothing to write"):
            with tempfile.NamedTemporaryFile(suffix=".3dm", delete=False) as f:
                tmp = f.name
            try:
                write_3dm(None, tmp)
            finally:
                os.unlink(tmp)

    def test_result_dict_keys(self):
        srf = _make_sphere_nurbs_surface()
        counts, result, _ = _write_and_read(surfaces=[srf], body=None)
        assert "surfaces" in result
        assert "curves" in result
        assert "meshes" in result
        assert "layers" in result


# ===========================================================================
# Tests: _body_to_nurbs_surfaces helper
# ===========================================================================

class TestBodyToNurbsSurfaces:
    def test_nurbs_face_extracted(self):
        """A body with a NurbsSurface face returns that surface."""
        # Build a minimal mock body with a face whose .surface is a NurbsSurface
        srf = _make_bilinear_patch()

        class _MockFace:
            surface = srf

        class _MockBody:
            def all_faces(self):
                return [_MockFace()]

        surfs = _body_to_nurbs_surfaces(_MockBody())
        assert len(surfs) == 1
        assert surfs[0] is srf

    def test_plane_face_converts(self):
        """A Plane surface is converted to a degree-1 NurbsSurface."""
        import numpy as np

        class _MockPlane:
            origin = np.array([0.0, 0.0, 0.0])
            x_axis = np.array([1.0, 0.0, 0.0])
            y_axis = np.array([0.0, 1.0, 0.0])

        class _MockFace:
            surface = _MockPlane()

        class _MockBody:
            def all_faces(self):
                return [_MockFace()]

        surfs = _body_to_nurbs_surfaces(_MockBody())
        assert len(surfs) == 1
        assert isinstance(surfs[0], NurbsSurface)
        assert surfs[0].degree_u == 1
        assert surfs[0].degree_v == 1

    def test_cylinder_face_converts(self):
        """A CylinderSurface is converted to a degree-2 rational NurbsSurface."""
        import numpy as np

        class _MockCylinder:
            center = np.array([0.0, 0.0, 0.0])
            axis   = np.array([0.0, 0.0, 1.0])
            x_ref  = np.array([1.0, 0.0, 0.0])
            radius = 5.0

        class _MockFace:
            surface = _MockCylinder()

        class _MockBody:
            def all_faces(self):
                return [_MockFace()]

        surfs = _body_to_nurbs_surfaces(_MockBody())
        assert len(surfs) == 1
        ns = surfs[0]
        assert isinstance(ns, NurbsSurface)
        assert ns.degree_u == 2
        assert ns.weights is not None

    def test_no_faces_empty_list(self):
        class _MockBody:
            def all_faces(self):
                return []

        surfs = _body_to_nurbs_surfaces(_MockBody())
        assert surfs == []

    def test_no_all_faces_method(self):
        surfs = _body_to_nurbs_surfaces("not_a_body")
        assert surfs == []


# ===========================================================================
# Tests: write from Body with NURBS faces (integration)
# ===========================================================================

class TestWriteFromBody:
    def test_body_with_nurbs_face(self):
        """write_3dm extracts and writes NURBS surfaces from a Body."""
        srf = _make_sphere_nurbs_surface()

        class _MockFace:
            surface = srf

        class _MockBody:
            def all_faces(self):
                return [_MockFace()]

        body = _MockBody()
        with tempfile.NamedTemporaryFile(suffix=".3dm", delete=False) as f:
            tmp = f.name
        try:
            counts = write_3dm(body, tmp)
            assert counts["surfaces"] == 1
            result = read_3dm(tmp)
            assert len(result["surfaces"]) == 1
        finally:
            os.unlink(tmp)

    def test_body_and_explicit_surfaces_combined(self):
        """write_3dm combines body surfaces + explicit surfaces parameter."""
        srf1 = _make_sphere_nurbs_surface()
        srf2 = _make_bilinear_patch()

        class _MockFace:
            surface = srf1

        class _MockBody:
            def all_faces(self):
                return [_MockFace()]

        with tempfile.NamedTemporaryFile(suffix=".3dm", delete=False) as f:
            tmp = f.name
        try:
            counts = write_3dm(_MockBody(), tmp, surfaces=[srf2])
            # body contributes 1, explicit surfaces adds 1 = 2
            assert counts["surfaces"] == 2
        finally:
            os.unlink(tmp)


# ===========================================================================
# Tests: _analytic_to_nurbs helper
# ===========================================================================

class TestAnalyticToNurbs:
    def test_plane_gives_degree_1(self):
        import numpy as np

        class _Plane:
            origin = np.array([0.0, 0.0, 0.0])
            x_axis = np.array([1.0, 0.0, 0.0])
            y_axis = np.array([0.0, 1.0, 0.0])

        ns = _analytic_to_nurbs(_Plane())
        assert ns is not None
        assert ns.degree_u == 1

    def test_cylinder_gives_rational(self):
        import numpy as np

        class _Cyl:
            center = np.array([0.0, 0.0, 0.0])
            axis   = np.array([0.0, 0.0, 1.0])
            x_ref  = np.array([1.0, 0.0, 0.0])
            radius = 10.0

        ns = _analytic_to_nurbs(_Cyl())
        assert ns is not None
        assert ns.weights is not None

    def test_unknown_surface_returns_none(self):
        class _Unknown:
            pass
        ns = _analytic_to_nurbs(_Unknown())
        assert ns is None
