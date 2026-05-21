"""test_rhino3dm_io.py — GK-127 hermetic oracle for the 3DM reader.

Strategy
--------
* If the ``rhino3dm`` PyPI package is available, we test the authoritative
  backend (skip the minimal-reader path).
* Otherwise we use the fixture writer ``make_minimal_sphere_3dm`` which writes
  a tiny .3dm containing a single NURBS sphere, then round-trips it through
  ``read_3dm`` (minimal reader).

The oracle: the read-back surface is a rational degree-2 surface whose control
points are within ε = 1e-9 of the written surface.
"""

import math
import os
import tempfile

import numpy as np
import pytest

from kerf_cad_core.geom.io.rhino3dm import (
    Rhino3dmReadError,
    make_minimal_sphere_3dm,
    read_3dm,
    _try_rhino3dm,
    _make_sphere_nurbs_surface,
)
from kerf_cad_core.geom.nurbs import NurbsSurface


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HAS_RHINO3DM = _try_rhino3dm() is not None


def _surfaces_close(a: NurbsSurface, b: NurbsSurface, atol: float = 1e-9) -> bool:
    """Return True if two NurbsSurfaces share the same geometry within atol."""
    if a.degree_u != b.degree_u or a.degree_v != b.degree_v:
        return False
    if a.control_points.shape != b.control_points.shape:
        return False
    return np.allclose(a.control_points, b.control_points, atol=atol)


# ---------------------------------------------------------------------------
# Tests: public API contract
# ---------------------------------------------------------------------------

class TestRhino3dmReadError:
    def test_importable(self):
        """Rhino3dmReadError should be importable from the geom package."""
        from kerf_cad_core.geom import Rhino3dmReadError as E  # noqa: F401
        assert issubclass(E, Exception)

    def test_read_3dm_importable(self):
        """read_3dm should be importable from the geom package."""
        from kerf_cad_core.geom import read_3dm as fn  # noqa: F401
        assert callable(fn)

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            read_3dm("/tmp/_kerf_nonexistent_fixture_xyz.3dm")

    def test_garbage_file_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".3dm", delete=False) as f:
            f.write(b"\x00\x01\x02\x03garbage")
            fname = f.name
        try:
            with pytest.raises(Rhino3dmReadError):
                read_3dm(fname)
        finally:
            os.unlink(fname)


# ---------------------------------------------------------------------------
# Tests: sphere NURBS construction
# ---------------------------------------------------------------------------

class TestSphereNurbs:
    def test_sphere_surface_structure(self):
        srf = _make_sphere_nurbs_surface(radius=1.0)
        assert srf.degree_u == 2
        assert srf.degree_v == 2
        assert srf.control_points.shape == (9, 5, 3)
        assert srf.weights is not None
        assert srf.weights.shape == (9, 5)

    def test_sphere_surface_points_on_sphere(self):
        """The on-knot control points that map to the sphere surface.

        For a rational NURBS sphere, the control points at the "even" positions
        (i.e. where the weight is 1.0) lie *exactly* on the sphere of the given
        radius.  The intermediate arc-midpoint control points lie off the sphere
        (they are the rational Bezier intermediate points).
        """
        r = 2.5
        srf = _make_sphere_nurbs_surface(radius=r)
        # weight-1 positions: i=0,2,4,6,8 (u) × j=0,2,4 (v)
        for i in [0, 2, 4, 6, 8]:
            for j in [0, 2, 4]:
                pt = srf.control_points[i, j]
                dist = float(np.linalg.norm(pt))
                assert abs(dist - r) < 1e-12, (
                    f"CP[{i},{j}] distance {dist:.6f} ≠ radius {r}"
                )

    def test_sphere_rational_weights_nonzero(self):
        srf = _make_sphere_nurbs_surface(radius=1.0)
        assert srf.weights is not None
        assert np.all(srf.weights > 0)

    def test_sphere_knot_vectors_clamped(self):
        srf = _make_sphere_nurbs_surface()
        # Clamped: first and last (degree+1) entries must be equal
        d = srf.degree_u
        assert np.all(srf.knots_u[:d + 1] == srf.knots_u[0])
        assert np.all(srf.knots_u[-(d + 1):] == srf.knots_u[-1])
        dv = srf.degree_v
        assert np.all(srf.knots_v[:dv + 1] == srf.knots_v[0])
        assert np.all(srf.knots_v[-(dv + 1):] == srf.knots_v[-1])


# ---------------------------------------------------------------------------
# Tests: round-trip oracle (minimal reader)
# ---------------------------------------------------------------------------

class TestMinimalReaderRoundTrip:
    """These tests do NOT require rhino3dm; they use the fixture writer."""

    def _write_and_read(self, radius: float = 1.0):
        with tempfile.NamedTemporaryFile(suffix=".3dm", delete=False) as f:
            fname = f.name
        try:
            written_srf = make_minimal_sphere_3dm(fname, radius=radius)
            result = read_3dm(fname)
        finally:
            os.unlink(fname)
        return written_srf, result

    def test_round_trip_surface_count(self):
        _, result = self._write_and_read()
        assert len(result["surfaces"]) == 1

    def test_round_trip_surface_degree(self):
        _, result = self._write_and_read()
        srf = result["surfaces"][0]
        assert isinstance(srf, NurbsSurface)
        assert srf.degree_u == 2
        assert srf.degree_v == 2

    def test_round_trip_surface_control_points_close(self):
        """Core oracle: control points survive within ε = 1e-9."""
        written, result = self._write_and_read(radius=1.0)
        read_srf = result["surfaces"][0]
        assert _surfaces_close(written, read_srf, atol=1e-9), (
            "Control points diverge beyond tolerance after 3DM round-trip"
        )

    def test_round_trip_surface_radius_3(self):
        """Oracle with a non-unit radius to confirm the scale is preserved."""
        written, result = self._write_and_read(radius=3.0)
        read_srf = result["surfaces"][0]
        assert _surfaces_close(written, read_srf, atol=1e-9)
        # Points at weight-1 positions should be on the r=3 sphere
        for i in [0, 2, 4, 6, 8]:
            for j in [0, 2, 4]:
                dist = float(np.linalg.norm(read_srf.control_points[i, j]))
                assert abs(dist - 3.0) < 1e-9

    def test_round_trip_knots_preserved(self):
        written, result = self._write_and_read()
        read_srf = result["surfaces"][0]
        assert np.allclose(written.knots_u, read_srf.knots_u, atol=1e-12)
        assert np.allclose(written.knots_v, read_srf.knots_v, atol=1e-12)

    def test_round_trip_weights_preserved(self):
        written, result = self._write_and_read()
        read_srf = result["surfaces"][0]
        assert read_srf.weights is not None
        assert written.weights is not None
        assert np.allclose(written.weights, read_srf.weights, atol=1e-12)

    def test_result_dict_keys(self):
        _, result = self._write_and_read()
        assert set(result.keys()) == {"curves", "surfaces", "meshes", "layers"}

    def test_result_curves_list(self):
        _, result = self._write_and_read()
        assert isinstance(result["curves"], list)

    def test_result_meshes_list(self):
        _, result = self._write_and_read()
        assert isinstance(result["meshes"], list)

    def test_result_layers_list(self):
        _, result = self._write_and_read()
        assert isinstance(result["layers"], list)


# ---------------------------------------------------------------------------
# Tests: rhino3dm backend (skip if not installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_RHINO3DM, reason="rhino3dm not installed")
class TestRhino3dmBackend:
    """Sanity-check the rhino3dm-backed reader on a fixture file."""

    def test_rhino3dm_backend_runs(self):
        """round-trip via fixture writer → read_3dm with rhino3dm backend."""
        with tempfile.NamedTemporaryFile(suffix=".3dm", delete=False) as f:
            fname = f.name
        try:
            make_minimal_sphere_3dm(fname, radius=1.0)
            result = read_3dm(fname)
            # The fixture only has a surface; rhino3dm may or may not parse
            # the minimal fixture format, so just check the structure.
            assert isinstance(result, dict)
            assert "surfaces" in result
        finally:
            os.unlink(fname)
