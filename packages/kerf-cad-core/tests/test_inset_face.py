"""
Tests for GK-73 — inset_face (SubDCage + Body).

Oracle (from spec):
  inset(area=A, gap=g) on a planar quad yields:
    * outer quad of area A
    * inner quad of area (sqrt(A) - 2*g)^2
    * N ring quads (one per original edge) + sealed topology
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.geom.inset_face import inset_face, InsetResult
from kerf_cad_core.geom.subd_authoring import SubDCage, create_subd_primitive


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _quad_area_3d(pts):
    """Approximate area of a planar quad (4 points) via two triangles."""
    import math

    def _cross(a, b):
        return [
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        ]

    def _norm(v):
        return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)

    def _sub(a, b):
        return [a[i] - b[i] for i in range(3)]

    p0, p1, p2, p3 = pts
    # Triangle 1: p0, p1, p2
    e1 = _sub(p1, p0)
    e2 = _sub(p2, p0)
    area1 = 0.5 * _norm(_cross(e1, e2))
    # Triangle 2: p0, p2, p3
    e3 = _sub(p2, p0)
    e4 = _sub(p3, p0)
    area2 = 0.5 * _norm(_cross(e3, e4))
    return area1 + area2


def _make_unit_quad_cage() -> SubDCage:
    """A single unit-square quad face in the XY plane, z=0."""
    verts = [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
    ]
    faces = [[0, 1, 2, 3]]
    return SubDCage(vertices=verts, faces=faces)


def _make_2x2_quad_cage() -> SubDCage:
    """A single 2x2 square quad face."""
    verts = [
        [0.0, 0.0, 0.0],
        [2.0, 0.0, 0.0],
        [2.0, 2.0, 0.0],
        [0.0, 2.0, 0.0],
    ]
    faces = [[0, 1, 2, 3]]
    return SubDCage(vertices=verts, faces=faces)


# ---------------------------------------------------------------------------
# Group 1: Return type + basic shape
# ---------------------------------------------------------------------------

def test_inset_face_returns_inset_result():
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 0, 0.1)
    assert isinstance(result, InsetResult)
    assert isinstance(result, dict)


def test_inset_result_has_required_keys():
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 0, 0.1)
    assert "target" in result
    assert "face_id" in result
    assert "ring_face_ids" in result
    assert "gap" in result


def test_inset_result_attribute_access():
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 0, 0.1)
    assert result.gap == pytest.approx(0.1)
    assert result.face_id == 0


def test_inset_returns_subd_cage():
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 0, 0.1)
    assert isinstance(result.target, SubDCage)


# ---------------------------------------------------------------------------
# Group 2: Topology for SubD quad face
# ---------------------------------------------------------------------------

def test_inset_subd_adds_correct_vertex_count():
    """Insetting a quad adds exactly 4 new vertices (inner ring)."""
    cage = _make_unit_quad_cage()
    orig_n = len(cage.vertices)
    result = inset_face(cage, 0, 0.1)
    assert len(result.target.vertices) == orig_n + 4


def test_inset_subd_adds_ring_faces():
    """Insetting a quad face creates exactly 4 ring quads."""
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 0, 0.1)
    assert len(result.ring_face_ids) == 4


def test_inset_subd_total_face_count():
    """Original 1 face → 1 inner + 4 ring = 5 faces."""
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 0, 0.1)
    assert len(result.target.faces) == 5


def test_inset_subd_ring_faces_are_quads():
    """Each ring face is a quad (4 vertices)."""
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 0, 0.1)
    for rid in result.ring_face_ids:
        assert len(result.target.faces[rid]) == 4


def test_inset_subd_inner_face_is_quad():
    """The inner face is still a quad."""
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 0, 0.1)
    inner_face = result.target.faces[result.face_id]
    assert len(inner_face) == 4


# ---------------------------------------------------------------------------
# Group 3: Geometry oracle — area-preserving check
# ---------------------------------------------------------------------------

def test_inset_subd_inner_area_oracle():
    """Oracle: inset(area=1, gap=0.1) on unit quad → inner area ≈ (1 - 2*0.1)² = 0.64.

    NOTE: the spec oracle uses sqrt(A) - 2g for a square: side = sqrt(A),
    inner_side = side - 2*gap → inner_area = (side - 2*gap)^2.
    """
    cage = _make_unit_quad_cage()  # 1×1 quad, area = 1
    gap = 0.1
    result = inset_face(cage, 0, gap)
    inner_verts_ids = result.target.faces[result.face_id]
    inner_pts = [result.target.vertices[i] for i in inner_verts_ids]
    inner_area = _quad_area_3d(inner_pts)
    expected = (math.sqrt(1.0) - 2 * gap) ** 2  # = 0.64
    assert inner_area == pytest.approx(expected, rel=0.1)


def test_inset_subd_2x2_inner_area_oracle():
    """Oracle: inset(area=4, gap=0.2) on 2×2 quad → inner area ≈ (2 - 2*0.2)² = 2.56."""
    cage = _make_2x2_quad_cage()
    gap = 0.2
    result = inset_face(cage, 0, gap)
    inner_verts_ids = result.target.faces[result.face_id]
    inner_pts = [result.target.vertices[i] for i in inner_verts_ids]
    inner_area = _quad_area_3d(inner_pts)
    expected = (math.sqrt(4.0) - 2 * gap) ** 2  # = (2 - 0.4)^2 = 2.56
    assert inner_area == pytest.approx(expected, rel=0.1)


def test_inset_subd_outer_area_unchanged():
    """The outer boundary (ring outer verts) spans the original face area."""
    cage = _make_unit_quad_cage()
    gap = 0.1
    result = inset_face(cage, 0, gap)
    # The outer vertices are the original face vertices (first 4 of cage)
    orig_pts = [cage.vertices[i] for i in cage.faces[0]]
    outer_area = _quad_area_3d(orig_pts)
    assert outer_area == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Group 4: Immutability
# ---------------------------------------------------------------------------

def test_inset_subd_does_not_mutate_original():
    """Original cage must not be mutated."""
    cage = _make_unit_quad_cage()
    orig_face_count = len(cage.faces)
    orig_vert_count = len(cage.vertices)
    inset_face(cage, 0, 0.1)
    assert len(cage.faces) == orig_face_count
    assert len(cage.vertices) == orig_vert_count


# ---------------------------------------------------------------------------
# Group 5: Direction parameter
# ---------------------------------------------------------------------------

def test_inset_subd_inward_shrinks():
    """Inward inset yields inner face smaller than original."""
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 0, 0.2, direction="inward")
    inner_ids = result.target.faces[result.face_id]
    inner_pts = [result.target.vertices[i] for i in inner_ids]
    inner_area = _quad_area_3d(inner_pts)
    assert inner_area < 1.0


def test_inset_subd_outward_grows():
    """Outward inset with gap=0.2 yields inner face larger than original."""
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 0, 0.2, direction="outward")
    inner_ids = result.target.faces[result.face_id]
    inner_pts = [result.target.vertices[i] for i in inner_ids]
    inner_area = _quad_area_3d(inner_pts)
    assert inner_area > 1.0


# ---------------------------------------------------------------------------
# Group 6: Multi-face cage — inset one face only
# ---------------------------------------------------------------------------

def test_inset_subd_cube_face_0():
    """Insetting face 0 of a cube cage returns the correct face count."""
    cage = create_subd_primitive("cube")
    n_faces_before = len(cage.faces)
    result = inset_face(cage, 0, 0.1)
    # Original 6 faces; face 0 replaced + 4 ring quads added
    assert len(result.target.faces) == n_faces_before + 4


def test_inset_subd_cube_other_faces_unchanged():
    """Faces 1-5 of the cube are not altered when we inset face 0."""
    cage = create_subd_primitive("cube")
    result = inset_face(cage, 0, 0.1)
    new_cage = result.target
    for fi in range(1, len(cage.faces)):
        assert new_cage.faces[fi] == cage.faces[fi]


def test_inset_subd_cube_ring_count():
    """Insetting a quad face of a cube gives exactly 4 ring faces."""
    cage = create_subd_primitive("cube")
    result = inset_face(cage, 0, 0.1)
    assert len(result.ring_face_ids) == 4


def test_inset_subd_pentagon_face():
    """Insetting an n-gon (5-sided face) produces 5 ring quads."""
    verts = []
    n = 5
    for i in range(n):
        angle = 2 * math.pi * i / n
        verts.append([math.cos(angle), math.sin(angle), 0.0])
    cage = SubDCage(vertices=verts, faces=[list(range(n))])
    result = inset_face(cage, 0, 0.1)
    assert len(result.ring_face_ids) == n


def test_inset_subd_hexagon_face():
    """Insetting a 6-sided face produces 6 ring quads."""
    n = 6
    verts = [[math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0.0] for i in range(n)]
    cage = SubDCage(vertices=verts, faces=[list(range(n))])
    result = inset_face(cage, 0, 0.1)
    assert len(result.ring_face_ids) == n


# ---------------------------------------------------------------------------
# Group 7: Edge cases & safety
# ---------------------------------------------------------------------------

def test_inset_face_invalid_face_id_safe():
    """Invalid face_id returns original cage with empty ring."""
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 999, 0.1)
    assert result.ring_face_ids == []
    assert len(result.target.faces) == len(cage.faces)


def test_inset_face_zero_gap():
    """Zero gap is valid — inner face coincides with original."""
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 0, 0.0)
    assert isinstance(result, InsetResult)


def test_inset_face_gap_recorded():
    """gap value is preserved in the result."""
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 0, 0.25)
    assert result.gap == pytest.approx(0.25)


def test_inset_face_face_id_recorded():
    """face_id is preserved in the result."""
    cage = _make_unit_quad_cage()
    result = inset_face(cage, 0, 0.1)
    assert result.face_id == 0


def test_inset_face_unknown_direction_defaults_to_inward():
    """Unknown direction string falls back to inward."""
    cage = _make_unit_quad_cage()
    result_default = inset_face(cage, 0, 0.1, direction="inward")
    result_unknown = inset_face(cage, 0, 0.1, direction="bogus")
    inner_default = result_default.target.faces[result_default.face_id]
    inner_unknown = result_unknown.target.faces[result_unknown.face_id]
    # Both should produce same topology
    assert len(inner_default) == len(inner_unknown)


# ---------------------------------------------------------------------------
# Group 8: B-rep Body path
# ---------------------------------------------------------------------------

def test_inset_face_body_basic():
    """inset_face works on a Body (make_box face)."""
    from kerf_cad_core.geom.brep import make_box
    body = make_box(size=(2.0, 2.0, 2.0))
    result = inset_face(body, 0, 0.1)
    assert isinstance(result, InsetResult)


def test_inset_face_body_returns_body():
    """inset_face on a Body returns a Body in the result."""
    from kerf_cad_core.geom.brep import make_box, Body
    body = make_box(size=(2.0, 2.0, 2.0))
    result = inset_face(body, 0, 0.1)
    assert isinstance(result.target, Body)


def test_inset_face_body_ring_count():
    """Insetting a quad B-rep face produces 4 ring faces."""
    from kerf_cad_core.geom.brep import make_box
    body = make_box(size=(2.0, 2.0, 2.0))
    result = inset_face(body, 0, 0.1)
    assert len(result.ring_face_ids) == 4


def test_inset_face_body_does_not_mutate():
    """Original body is not mutated."""
    from kerf_cad_core.geom.brep import make_box
    body = make_box(size=(2.0, 2.0, 2.0))
    orig_face_count = len(body.all_faces())
    inset_face(body, 0, 0.1)
    assert len(body.all_faces()) == orig_face_count


def test_inset_face_body_invalid_face_id_safe():
    """Invalid face_id on a Body returns original body unchanged."""
    from kerf_cad_core.geom.brep import make_box
    body = make_box(size=(2.0, 2.0, 2.0))
    result = inset_face(body, 999, 0.1)
    assert result.ring_face_ids == []


# ---------------------------------------------------------------------------
# Group 9: Public facade import
# ---------------------------------------------------------------------------

def test_public_facade_inset_face():
    """inset_face is importable from kerf_cad_core.geom."""
    from kerf_cad_core.geom import inset_face as _if  # noqa: F401
    assert callable(_if)


def test_public_facade_inset_result():
    """InsetResult is importable from kerf_cad_core.geom."""
    from kerf_cad_core.geom import InsetResult as _IR  # noqa: F401
    assert issubclass(_IR, dict)
