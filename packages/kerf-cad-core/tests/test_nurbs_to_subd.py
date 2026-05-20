"""Tests for GK-53: NURBS Body → SubD cage (reverse, quad-dominant).

All tests are hermetic: no OCC, no database, no network. Pure-Python
geometry + NumPy only.

Coverage:
  1.  Round-trip cube: SubD cage → NURBS body → SubD cage reproduces
      original cage vertices to ≤ 1e-7 (ORACLE).
  2.  Return type is SubDMesh.
  3.  Quad-only cage: every face in the returned cage has exactly 4 vertices.
  4.  Vertex count matches expected for a cube cage (8 unique vertices).
  5.  Face count matches original face count (6 for cube).
  6.  Round-trip with one level of CC: SubD cage → CC → NURBS → SubD cage
      reproduces the CC cage vertices to ≤ 1e-7.
  7.  Round-trip with two levels of CC.
  8.  NurbsToSubdError raised for a body with no NURBS faces.
  9.  Boundary edge creases: open-boundary patches get crease=1.0.
  10. Vertex positions in round-trip cage match originals in any order
      (permutation-invariant oracle).
  11. Re-converting the extracted cage back to NURBS produces a valid body.
  12. Face topology: each recovered face's 4 vertices are distinct.
  13. subd_roundtrip: cube cage → NURBS → cage → NURBS → cage round-trip
      (two full inversions) stays ≤ 1e-7.
"""

from __future__ import annotations

import math
from typing import List

import numpy as np
import pytest

from kerf_cad_core.geom.brep import validate_body
from kerf_cad_core.geom.subd import SubDMesh, catmull_clark_subdivide
from kerf_cad_core.geom.subd_to_nurbs import (
    NurbsToSubdError,
    nurbs_body_to_subd_cage,
    subd_cage_to_nurbs_body,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_cube_cage() -> SubDMesh:
    """Unit cube centred at origin, 8 verts, 6 quad faces."""
    verts = [
        [-1.0, -1.0, -1.0],  # 0
        [ 1.0, -1.0, -1.0],  # 1
        [ 1.0,  1.0, -1.0],  # 2
        [-1.0,  1.0, -1.0],  # 3
        [-1.0, -1.0,  1.0],  # 4
        [ 1.0, -1.0,  1.0],  # 5
        [ 1.0,  1.0,  1.0],  # 6
        [-1.0,  1.0,  1.0],  # 7
    ]
    faces = [
        [0, 1, 2, 3],   # bottom  z=-1
        [4, 5, 6, 7],   # top     z=+1
        [0, 1, 5, 4],   # front   y=-1
        [2, 3, 7, 6],   # back    y=+1
        [0, 3, 7, 4],   # left    x=-1
        [1, 2, 6, 5],   # right   x=+1
    ]
    return SubDMesh(vertices=verts, faces=faces)


def _vert_set(cage: SubDMesh) -> set:
    """Unique rounded vertex positions as a set of tuples."""
    s = set()
    for v in cage.vertices:
        s.add(tuple(round(x, 9) for x in v))
    return s


def _vert_array(cage: SubDMesh) -> np.ndarray:
    return np.array(cage.vertices, dtype=float)


# ---------------------------------------------------------------------------
# 1. Round-trip oracle: cube cage → NURBS body → SubD cage ≤ 1e-7
# ---------------------------------------------------------------------------


def test_roundtrip_cube_oracle():
    """ORACLE: SubD cube cage → NURBS body → SubD cage recovers original verts.

    For every vertex in the ORIGINAL cage there must exist a vertex in the
    RECOVERED cage within 1e-7 (and vice-versa).  This is the GK-53 oracle.
    """
    cage = make_cube_cage()
    body = subd_cage_to_nurbs_body(cage)
    recovered = nurbs_body_to_subd_cage(body, tol=1e-7)

    orig_verts = _vert_array(cage)   # (8, 3)
    rec_verts  = _vert_array(recovered)  # (8, 3)

    tol = 1e-7
    # Every original vertex must be found in recovered (within tol)
    for i, ov in enumerate(orig_verts):
        dists = np.linalg.norm(rec_verts - ov, axis=1)
        assert dists.min() <= tol, (
            f"Original vertex {i} ({ov}) not found in recovered cage "
            f"(min dist {dists.min():.2e})"
        )
    # Every recovered vertex must be found in original (within tol)
    for i, rv in enumerate(rec_verts):
        dists = np.linalg.norm(orig_verts - rv, axis=1)
        assert dists.min() <= tol, (
            f"Recovered vertex {i} ({rv}) not found in original cage "
            f"(min dist {dists.min():.2e})"
        )


# ---------------------------------------------------------------------------
# 2. Return type is SubDMesh
# ---------------------------------------------------------------------------


def test_return_type_is_subd_mesh():
    cage = make_cube_cage()
    body = subd_cage_to_nurbs_body(cage)
    recovered = nurbs_body_to_subd_cage(body)
    assert isinstance(recovered, SubDMesh)


# ---------------------------------------------------------------------------
# 3. All faces are quads
# ---------------------------------------------------------------------------


def test_all_faces_are_quads():
    cage = make_cube_cage()
    body = subd_cage_to_nurbs_body(cage)
    recovered = nurbs_body_to_subd_cage(body)
    for fi, face in enumerate(recovered.faces):
        assert len(face) == 4, f"face {fi} has {len(face)} verts (expected 4)"


# ---------------------------------------------------------------------------
# 4. Vertex count: cube cage has 8 unique vertices
# ---------------------------------------------------------------------------


def test_vertex_count_cube():
    cage = make_cube_cage()
    body = subd_cage_to_nurbs_body(cage)
    recovered = nurbs_body_to_subd_cage(body)
    assert recovered.num_vertices == 8, (
        f"expected 8 unique vertices, got {recovered.num_vertices}"
    )


# ---------------------------------------------------------------------------
# 5. Face count matches original
# ---------------------------------------------------------------------------


def test_face_count_matches_original():
    cage = make_cube_cage()
    body = subd_cage_to_nurbs_body(cage)
    recovered = nurbs_body_to_subd_cage(body)
    assert recovered.num_faces == cage.num_faces, (
        f"expected {cage.num_faces} faces, got {recovered.num_faces}"
    )


# ---------------------------------------------------------------------------
# 6. Round-trip with 1 level of CC
# ---------------------------------------------------------------------------


def test_roundtrip_sub1_oracle():
    """SubD cage → 1 CC level → NURBS body → SubD cage ≤ 1e-7."""
    cage = make_cube_cage()
    sub1 = catmull_clark_subdivide(cage, levels=1)
    body = subd_cage_to_nurbs_body(sub1)
    recovered = nurbs_body_to_subd_cage(body, tol=1e-7)

    orig_verts = _vert_array(sub1)
    rec_verts  = _vert_array(recovered)

    tol = 1e-7
    for i, ov in enumerate(orig_verts):
        dists = np.linalg.norm(rec_verts - ov, axis=1)
        assert dists.min() <= tol, (
            f"sub1 vertex {i} ({ov}) not found (min dist {dists.min():.2e})"
        )


# ---------------------------------------------------------------------------
# 7. Round-trip with 2 levels of CC
# ---------------------------------------------------------------------------


def test_roundtrip_sub2_oracle():
    """SubD cage → 2 CC levels → NURBS body → SubD cage ≤ 1e-7."""
    cage = make_cube_cage()
    sub2 = catmull_clark_subdivide(cage, levels=2)
    body = subd_cage_to_nurbs_body(sub2)
    recovered = nurbs_body_to_subd_cage(body, tol=1e-7)

    orig_verts = _vert_array(sub2)
    rec_verts  = _vert_array(recovered)

    tol = 1e-7
    for i, ov in enumerate(orig_verts):
        dists = np.linalg.norm(rec_verts - ov, axis=1)
        assert dists.min() <= tol, (
            f"sub2 vertex {i} ({ov}) not found (min dist {dists.min():.2e})"
        )


# ---------------------------------------------------------------------------
# 8. NurbsToSubdError for body with no NURBS faces
# ---------------------------------------------------------------------------


def test_error_on_no_nurbs_faces():
    """NurbsToSubdError must be raised when body has no NURBS surfaces."""
    from kerf_cad_core.geom.brep import Body, Solid, Shell, Face, Loop, Coedge, Edge, Vertex
    from kerf_cad_core.geom.brep import Line3, Plane
    import numpy as np

    # Build a minimal Body with a Plane surface (analytic, not NURBS)
    origin = np.zeros(3)
    x_axis = np.array([1.0, 0.0, 0.0])
    y_axis = np.array([0.0, 1.0, 0.0])
    plane = Plane(origin=origin, x_axis=x_axis, y_axis=y_axis)

    v0 = Vertex(point=np.array([0.0, 0.0, 0.0]))
    v1 = Vertex(point=np.array([1.0, 0.0, 0.0]))
    v2 = Vertex(point=np.array([1.0, 1.0, 0.0]))
    v3 = Vertex(point=np.array([0.0, 1.0, 0.0]))

    e01 = Edge(curve=Line3(v0.point, v1.point), t0=0.0, t1=1.0, v_start=v0, v_end=v1)
    e12 = Edge(curve=Line3(v1.point, v2.point), t0=0.0, t1=1.0, v_start=v1, v_end=v2)
    e23 = Edge(curve=Line3(v2.point, v3.point), t0=0.0, t1=1.0, v_start=v2, v_end=v3)
    e30 = Edge(curve=Line3(v3.point, v0.point), t0=0.0, t1=1.0, v_start=v3, v_end=v0)

    ce01 = Coedge(edge=e01, orientation=True)
    ce12 = Coedge(edge=e12, orientation=True)
    ce23 = Coedge(edge=e23, orientation=True)
    ce30 = Coedge(edge=e30, orientation=True)

    lp = Loop(coedges=[ce01, ce12, ce23, ce30], is_outer=True)
    face = Face(surface=plane, loops=[lp])
    shell = Shell(faces=[face], is_closed=False)
    solid = Solid([shell])
    body = Body(solids=[solid])

    with pytest.raises(NurbsToSubdError):
        nurbs_body_to_subd_cage(body)


# ---------------------------------------------------------------------------
# 9. Boundary edges in open-boundary case get crease=1.0
# ---------------------------------------------------------------------------


def test_open_boundary_crease():
    """A single-patch body (open boundary) should crease all 4 boundary edges."""
    cage = make_cube_cage()
    # One face only: extract just the first face's patch
    single_face_cage = SubDMesh(
        vertices=cage.vertices,
        faces=[cage.faces[0]],
    )
    from kerf_cad_core.geom.subd_to_nurbs import subd_cage_to_nurbs_patches
    from kerf_cad_core.geom.brep_build import surface_to_face, surfaces_to_shell
    from kerf_cad_core.geom.brep import Body, Solid, validate_body

    patches = subd_cage_to_nurbs_patches(single_face_cage)
    assert len(patches) == 1

    from kerf_cad_core.geom.nurbs import NurbsSurface
    srf = patches[0]

    from kerf_cad_core.geom.subd_to_nurbs import _extract_patch_corners, NurbsToSubdError, nurbs_body_to_subd_cage

    # Build a minimal Body wrapping just this one patch (open shell)
    face_obj = surface_to_face(srf, tol=1e-7)
    face_obj.shell = None
    shell = surfaces_to_shell([face_obj], sew_tol=1e-5)
    solid = Solid([shell])
    body = Body(solids=[solid])

    recovered = nurbs_body_to_subd_cage(body)
    # All 4 edges of the single quad should be boundary → creased
    assert len(recovered.creases) == 4, (
        f"expected 4 creased edges (all boundary), got {len(recovered.creases)}"
    )
    for ek, val in recovered.creases.items():
        assert val == 1.0, f"edge {ek} crease={val}, expected 1.0"


# ---------------------------------------------------------------------------
# 10. Permutation-invariant oracle
# ---------------------------------------------------------------------------


def test_roundtrip_permutation_invariant():
    """Vertex set of recovered cage equals vertex set of original (unordered)."""
    cage = make_cube_cage()
    body = subd_cage_to_nurbs_body(cage)
    recovered = nurbs_body_to_subd_cage(body, tol=1e-7)

    orig_set = _vert_set(cage)
    rec_set  = _vert_set(recovered)

    assert orig_set == rec_set, (
        f"Vertex sets differ.\nOriginal: {orig_set}\nRecovered: {rec_set}"
    )


# ---------------------------------------------------------------------------
# 11. Re-convert extracted cage → valid NURBS body
# ---------------------------------------------------------------------------


def test_reconvert_to_nurbs_validates():
    """cage → NURBS → cage → NURBS: second body passes validate_body."""
    cage = make_cube_cage()
    body1 = subd_cage_to_nurbs_body(cage)
    cage2 = nurbs_body_to_subd_cage(body1, tol=1e-7)
    body2 = subd_cage_to_nurbs_body(cage2)
    result = validate_body(body2)
    assert result["ok"], f"validate_body failed on double-roundtrip body: {result['errors']}"


# ---------------------------------------------------------------------------
# 12. Each face's 4 vertices are distinct
# ---------------------------------------------------------------------------


def test_face_vertices_distinct():
    cage = make_cube_cage()
    body = subd_cage_to_nurbs_body(cage)
    recovered = nurbs_body_to_subd_cage(body)
    for fi, face in enumerate(recovered.faces):
        assert len(set(face)) == 4, (
            f"face {fi} has duplicate vertex indices: {face}"
        )


# ---------------------------------------------------------------------------
# 13. subd_roundtrip: two full inversions stay ≤ 1e-7
# ---------------------------------------------------------------------------


def test_subd_roundtrip_double_inversion():
    """cage → NURBS → cage2 → NURBS2 → cage3: cage3 ≈ cage2 ≤ 1e-7."""
    cage = make_cube_cage()
    body1 = subd_cage_to_nurbs_body(cage)
    cage2 = nurbs_body_to_subd_cage(body1, tol=1e-7)
    body2 = subd_cage_to_nurbs_body(cage2)
    cage3 = nurbs_body_to_subd_cage(body2, tol=1e-7)

    v2 = _vert_array(cage2)
    v3 = _vert_array(cage3)

    tol = 1e-7
    for i, p2 in enumerate(v2):
        dists = np.linalg.norm(v3 - p2, axis=1)
        assert dists.min() <= tol, (
            f"cage2 vertex {i} ({p2}) not in cage3 (min dist {dists.min():.2e})"
        )
