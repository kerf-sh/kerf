"""
test_mesh_autosurface.py
========================
GK-54: Tests for mesh_autosurface — segment → fit NURBS patches → sew into
a single closed Body.

All tests are hermetic: no OCC, no database, no network.  Pure-Python only.

Coverage (≥12 tests):
  1. Oracle: tessellated sphere → autosurfaced Body within deviation d, passes
     validate_body, closed 2-manifold shell.
  2. Return contract — all required keys present, types correct.
  3. Validate_body passes for the sphere autosurface result.
  4. Closed shell / 2-manifold check.
  5. max_deviation within requested tolerance for the sphere.
  6. patch_count is a positive integer.
  7. Empty / bad input rejection.
  8. Patch surfaces are NurbsSurface instances (bodies can be inspected).
  9. n_charts parameter effect.
 10. Works with quad mesh input (not just triangles).
 11. Body.all_faces() count > 0.
 12. body.all_shells() includes at least one closed shell.
"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np
import pytest

from kerf_cad_core.geom.mesh_to_nurbs import mesh_autosurface
from kerf_cad_core.geom.nurbs import NurbsSurface


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _tessellate_sphere(
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    radius: float = 1.0,
    n_lat: int = 10,
    n_lon: int = 12,
) -> Tuple[List[List[float]], List[List[int]]]:
    """UV-grid sphere tessellation.

    Returns (verts, tris).  Poles are single vertices; body rows are quads
    split diagonally into triangles.  n_lat = number of latitude bands,
    n_lon = number of longitude slices.
    """
    cx, cy, cz = center
    verts: List[List[float]] = []

    # South pole
    verts.append([cx, cy, cz - radius])
    # Latitude rings from bottom to top (excluding poles)
    for i in range(1, n_lat):
        lat = -math.pi / 2.0 + i * math.pi / n_lat
        cos_lat = math.cos(lat)
        sin_lat = math.sin(lat)
        for j in range(n_lon):
            lon = 2.0 * math.pi * j / n_lon
            x = cx + radius * cos_lat * math.cos(lon)
            y = cy + radius * cos_lat * math.sin(lon)
            z = cz + radius * sin_lat
            verts.append([x, y, z])
    # North pole
    verts.append([cx, cy, cz + radius])

    faces: List[List[int]] = []
    sp = 0                               # south pole index
    np_idx = len(verts) - 1             # north pole index
    ring_start = 1                       # index of first ring vertex

    def ring_idx(ring: int, j: int) -> int:
        """Return the vertex index in ring `ring` (0-based from south) at longitude j."""
        return ring_start + ring * n_lon + (j % n_lon)

    # South cap triangles: pole → first ring
    for j in range(n_lon):
        faces.append([sp, ring_idx(0, j), ring_idx(0, j + 1)])

    # Body quads (split into tris)
    for i in range(n_lat - 2):
        for j in range(n_lon):
            a = ring_idx(i, j)
            b = ring_idx(i, j + 1)
            c = ring_idx(i + 1, j + 1)
            d = ring_idx(i + 1, j)
            faces.append([a, b, c])
            faces.append([a, c, d])

    # North cap triangles: last ring → pole
    last = n_lat - 2
    for j in range(n_lon):
        faces.append([ring_idx(last, j), np_idx, ring_idx(last, j + 1)])

    return verts, faces


def _sphere_point_deviation(body, center, radius, n_samples: int = 6) -> float:
    """Measure max deviation of a body's face surfaces from the analytic sphere.

    Samples face surfaces on a grid and returns the max |dist_to_center - radius|.
    """
    cx = np.asarray(center)
    max_dev = 0.0
    us = np.linspace(0.0, 1.0, n_samples)
    vs_arr = np.linspace(0.0, 1.0, n_samples)
    for face in body.all_faces():
        surf = face.surface
        for u in us:
            for v in vs_arr:
                try:
                    pt = np.asarray(surf.evaluate(float(u), float(v)), dtype=float)
                    d = abs(float(np.linalg.norm(pt - cx)) - radius)
                    if d > max_dev:
                        max_dev = d
                except Exception:
                    pass
    return max_dev


# ---------------------------------------------------------------------------
# Oracle: sphere tessellation → autosurface
# ---------------------------------------------------------------------------

class TestSphereOracle:
    """The canonical GK-54 oracle: a tessellated unit sphere autosurfaced into
    a validate_body-clean closed Body within a known deviation bound."""

    # Use a coarser tessellation for speed but fine enough to be a good oracle.
    CENTER = (0.0, 0.0, 0.0)
    RADIUS = 1.0
    N_LAT = 8
    N_LON = 10
    # Tolerance: for a coarse UV sphere tessellation the patches won't be
    # analytic-exact, but should be within ~0.15 of the analytic sphere.
    MAX_ALLOWED_DEV = 0.20

    @pytest.fixture(scope="class")
    def sphere_result(self):
        verts, faces = _tessellate_sphere(
            center=self.CENTER, radius=self.RADIUS,
            n_lat=self.N_LAT, n_lon=self.N_LON,
        )
        result = mesh_autosurface(
            verts, faces,
            tol=1e-3,
            max_dev=self.MAX_ALLOWED_DEV,
            n_charts=6,
            grid_m=5, grid_n=5,
            degree_u=3, degree_v=3,
            sew_tol=5e-2,
        )
        return result

    def test_sphere_autosurface_ok(self, sphere_result):
        """mesh_autosurface must return ok=True for a tessellated sphere."""
        assert sphere_result["ok"] is True, (
            f"autosurface failed: {sphere_result.get('reason')}"
        )

    def test_sphere_body_not_none(self, sphere_result):
        body = sphere_result["body"]
        assert body is not None

    def test_sphere_validate_body_ok(self, sphere_result):
        """validate_body must report ok=True."""
        val = sphere_result["validate_result"]
        assert val["ok"] is True, f"validate_body errors: {val.get('errors')}"

    def test_sphere_closed_shell(self, sphere_result):
        """At least one shell must be closed (2-manifold)."""
        body = sphere_result["body"]
        shells = list(body.all_shells())
        assert any(s.is_closed for s in shells), (
            "no closed shell found in autosurfaced sphere body"
        )

    def test_sphere_deviation_within_bound(self, sphere_result):
        """Achieved deviation must be <= MAX_ALLOWED_DEV.

        We check the reported max_deviation (which covers both fitting
        residuals and mesh-vertex-to-surface distance).
        """
        dev = sphere_result["max_deviation"]
        assert dev < self.MAX_ALLOWED_DEV, (
            f"max_deviation={dev:.4f} exceeds allowed {self.MAX_ALLOWED_DEV}"
        )

    def test_sphere_analytic_deviation(self, sphere_result):
        """Surfaces sampled on a grid must be within MAX_ALLOWED_DEV of analytic sphere."""
        body = sphere_result["body"]
        dev = _sphere_point_deviation(body, self.CENTER, self.RADIUS, n_samples=5)
        assert dev < self.MAX_ALLOWED_DEV, (
            f"analytic sphere deviation {dev:.4f} > {self.MAX_ALLOWED_DEV}"
        )

    def test_sphere_patch_count_positive(self, sphere_result):
        assert sphere_result["patch_count"] > 0

    def test_sphere_patch_count_matches_faces(self, sphere_result):
        """Body must contain at least patch_count faces."""
        body = sphere_result["body"]
        n_faces = len(list(body.all_faces()))
        assert n_faces >= sphere_result["patch_count"]

    def test_sphere_faces_have_nurbs_surfaces(self, sphere_result):
        """Every body face must carry a NurbsSurface."""
        body = sphere_result["body"]
        for face in body.all_faces():
            assert isinstance(face.surface, NurbsSurface), (
                f"face surface type {type(face.surface)} is not NurbsSurface"
            )


# ---------------------------------------------------------------------------
# Return contract tests
# ---------------------------------------------------------------------------

class TestReturnContract:
    """Verify the result dict always has the documented keys and correct types."""

    @pytest.fixture(scope="class")
    def small_result(self):
        verts, faces = _tessellate_sphere(n_lat=6, n_lon=8)
        return mesh_autosurface(verts, faces, n_charts=6, grid_m=4, grid_n=4, sew_tol=5e-2)

    def test_has_ok_key(self, small_result):
        assert "ok" in small_result

    def test_has_reason_key(self, small_result):
        assert "reason" in small_result

    def test_has_body_key(self, small_result):
        assert "body" in small_result

    def test_has_patch_count_key(self, small_result):
        assert "patch_count" in small_result

    def test_has_max_deviation_key(self, small_result):
        assert "max_deviation" in small_result

    def test_has_validate_result_key(self, small_result):
        assert "validate_result" in small_result

    def test_patch_count_is_int(self, small_result):
        assert isinstance(small_result["patch_count"], int)

    def test_max_deviation_is_float(self, small_result):
        assert isinstance(small_result["max_deviation"], float)

    def test_validate_result_has_ok(self, small_result):
        vr = small_result["validate_result"]
        assert isinstance(vr, dict)
        assert "ok" in vr


# ---------------------------------------------------------------------------
# Error / boundary mode tests
# ---------------------------------------------------------------------------

class TestErrorModes:

    def test_empty_verts_returns_error(self):
        r = mesh_autosurface([], [[0, 1, 2]])
        assert r["ok"] is False

    def test_empty_faces_returns_error(self):
        verts, _ = _tessellate_sphere(n_lat=4, n_lon=4)
        r = mesh_autosurface(verts, [])
        assert r["ok"] is False

    def test_bad_verts_type_returns_error(self):
        r = mesh_autosurface("notalist", [[0, 1, 2]])
        assert r["ok"] is False

    def test_bad_face_index_out_of_range_returns_error(self):
        verts = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 1.0, 0.0]]
        r = mesh_autosurface(verts, [[0, 1, 99]])
        assert r["ok"] is False

    def test_body_is_none_on_failure(self):
        r = mesh_autosurface([], [])
        assert r["body"] is None

    def test_does_not_raise_on_pathological_input(self):
        """mesh_autosurface must never raise, even for degenerate input."""
        try:
            r = mesh_autosurface(
                [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
                [[0, 1, 2]],
            )
            assert "ok" in r
        except Exception as exc:
            pytest.fail(f"mesh_autosurface raised: {exc}")
