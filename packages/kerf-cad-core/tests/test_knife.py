"""GK-89 — hermetic oracle tests for knife_face.

Oracles (from spec):
  1. Knife a planar face by a diagonal → 2 triangle-faces of equal area ± tol.
  2. Knife a 4-vertex quad face along its midline → 2 quad faces, total area
     preserved.
"""

from __future__ import annotations

import math
import pytest
import numpy as np

from kerf_cad_core.geom.knife import knife_face
from kerf_cad_core.geom.brep import Body, Shell, Face, Loop, Coedge, Edge, Vertex, Line3, Plane, _unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _poly_area_3d(pts) -> float:
    """Area of a planar polygon via fan triangulation from centroid."""
    pts = [np.asarray(p, dtype=float) for p in pts]
    n = len(pts)
    if n < 3:
        return 0.0
    c = np.mean(pts, axis=0)
    area = 0.0
    for i in range(n):
        a = pts[i] - c
        b = pts[(i + 1) % n] - c
        area += np.linalg.norm(np.cross(a, b))
    return float(area) * 0.5


def _face_poly_area(face: Face) -> float:
    """Area of a B-rep Face from its outer loop vertex positions."""
    outer = face.outer_loop()
    if outer is None:
        return 0.0
    pts = [ce.start_point() for ce in outer.coedges]
    return _poly_area_3d(pts)


def _make_brep_face(pts) -> Face:
    """Build a minimal B-rep Face from an ordered list of 3-D points."""
    pts = [np.asarray(p, dtype=float) for p in pts]
    n = len(pts)
    # Plane from first three non-collinear vertices
    e1 = _unit(pts[1] - pts[0])
    normal = np.zeros(3)
    for i in range(2, n):
        crs = np.cross(e1, pts[i] - pts[0])
        if np.linalg.norm(crs) > 1e-10:
            normal = _unit(crs)
            break
    if np.linalg.norm(normal) < 1e-10:
        normal = np.array([0.0, 0.0, 1.0])
    y_axis = _unit(np.cross(normal, e1))
    srf = Plane(origin=pts[0].copy(), x_axis=e1, y_axis=y_axis)

    vertices = [Vertex(point=p.copy()) for p in pts]
    coedges = []
    for i in range(n):
        v0, v1 = vertices[i], vertices[(i + 1) % n]
        seg = Line3(p0=v0.point.copy(), p1=v1.point.copy())
        e = Edge(curve=seg, t0=0.0, t1=1.0, v_start=v0, v_end=v1)
        coedges.append(Coedge(edge=e, orientation=True))
    loop = Loop(coedges=coedges, is_outer=True)
    return Face(surface=srf, loops=[loop])


def _face_in_body(face: Face) -> Body:
    """Wrap a single Face in a Body so we can pass a face_id."""
    shell = Shell(faces=[face], is_closed=False)
    body = Body(shells=[shell])
    return body


# ---------------------------------------------------------------------------
# Oracle 1: diagonal knife on a unit square → two triangles of equal area
# ---------------------------------------------------------------------------


class TestKnifeTriangle:
    """Knife a unit square by its diagonal; expect two triangles ≈ 0.5 area each."""

    TOL = 1e-6

    def _setup(self):
        # Unit square in XY: (0,0,0), (1,0,0), (1,1,0), (0,1,0)
        pts = [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
        face = _make_brep_face(pts)
        body = _face_in_body(face)
        # Diagonal from (0,0,0) to (1,1,0)
        diag = Line3(p0=np.array([0.0, 0.0, 0.0]), p1=np.array([1.0, 1.0, 0.0]))
        return body, diag

    def test_returns_two_faces(self):
        body, diag = self._setup()
        result = knife_face(body, 0, diag)
        assert len(result) == 2, f"Expected 2 faces, got {len(result)}"

    def test_both_areas_equal(self):
        body, diag = self._setup()
        face_a, face_b = knife_face(body, 0, diag)
        area_a = _face_poly_area(face_a)
        area_b = _face_poly_area(face_b)
        assert abs(area_a - area_b) < self.TOL, (
            f"Triangle areas not equal: {area_a:.8f} vs {area_b:.8f}"
        )

    def test_each_area_is_half(self):
        body, diag = self._setup()
        face_a, face_b = knife_face(body, 0, diag)
        area_a = _face_poly_area(face_a)
        area_b = _face_poly_area(face_b)
        assert abs(area_a - 0.5) < self.TOL, f"face_a area {area_a:.8f} not ≈ 0.5"
        assert abs(area_b - 0.5) < self.TOL, f"face_b area {area_b:.8f} not ≈ 0.5"

    def test_area_sum_preserved(self):
        body, diag = self._setup()
        face_a, face_b = knife_face(body, 0, diag)
        total = _face_poly_area(face_a) + _face_poly_area(face_b)
        assert abs(total - 1.0) < self.TOL, f"Total area {total:.8f} not ≈ 1.0"


# ---------------------------------------------------------------------------
# Oracle 2: midline knife on unit square → two quads, area preserved
# ---------------------------------------------------------------------------


class TestKnifeQuadMidline:
    """Knife a unit square along its horizontal midline; expect two rectangles."""

    TOL = 1e-6

    def _setup(self):
        # Unit square in XY
        pts = [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
        face = _make_brep_face(pts)
        body = _face_in_body(face)
        # Horizontal midline from (0, 0.5, 0) to (1, 0.5, 0)
        midline = Line3(
            p0=np.array([0.0, 0.5, 0.0]),
            p1=np.array([1.0, 0.5, 0.0]),
        )
        return body, midline

    def test_returns_two_faces(self):
        body, midline = self._setup()
        result = knife_face(body, 0, midline)
        assert len(result) == 2

    def test_total_area_preserved(self):
        body, midline = self._setup()
        face_a, face_b = knife_face(body, 0, midline)
        total = _face_poly_area(face_a) + _face_poly_area(face_b)
        # Original unit square has area 1.0
        assert abs(total - 1.0) < self.TOL, (
            f"Total area {total:.8f} not ≈ 1.0 (original)"
        )

    def test_each_face_has_area_half(self):
        body, midline = self._setup()
        face_a, face_b = knife_face(body, 0, midline)
        area_a = _face_poly_area(face_a)
        area_b = _face_poly_area(face_b)
        assert abs(area_a - 0.5) < self.TOL, f"face_a area {area_a:.8f} not ≈ 0.5"
        assert abs(area_b - 0.5) < self.TOL, f"face_b area {area_b:.8f} not ≈ 0.5"

    def test_both_faces_have_four_vertices(self):
        """Midline cut of a quad must yield two quads (4 vertices each)."""
        body, midline = self._setup()
        face_a, face_b = knife_face(body, 0, midline)
        verts_a = len(face_a.outer_loop().coedges)
        verts_b = len(face_b.outer_loop().coedges)
        assert verts_a == 4, f"face_a has {verts_a} vertices, expected 4"
        assert verts_b == 4, f"face_b has {verts_b} vertices, expected 4"


# ---------------------------------------------------------------------------
# Regression: public import works
# ---------------------------------------------------------------------------


def test_import_from_geom_init():
    from kerf_cad_core.geom import knife_face as kf  # noqa: F401
    assert callable(kf)


# ---------------------------------------------------------------------------
# SubDCage knife: diagonal splits a quad cage into two triangular cages
# ---------------------------------------------------------------------------


def test_knife_subd_cage_diagonal():
    from kerf_cad_core.geom.subd_authoring import SubDCage

    cage = SubDCage(
        vertices=[
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        faces=[[0, 1, 2, 3]],
    )
    diag = Line3(p0=np.array([0.0, 0.0, 0.0]), p1=np.array([1.0, 1.0, 0.0]))
    cage_a, cage_b = knife_face(cage, 0, diag)
    area_a = _poly_area_3d(cage_a.vertices)
    area_b = _poly_area_3d(cage_b.vertices)
    assert abs(area_a + area_b - 1.0) < 1e-6, f"SubD total area {area_a + area_b:.8f}"
    assert abs(area_a - area_b) < 1e-6, f"SubD areas not equal: {area_a} vs {area_b}"
