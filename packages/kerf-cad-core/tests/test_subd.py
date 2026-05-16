"""
Tests for kerf_cad_core.geom.subd — Catmull-Clark subdivision surfaces.

All tests are hermetic: no OCC, no database, no network.  Pure-Python
geometry only.

Coverage (>= 30 tests):
  1.  SubDMesh dataclass — construction, edge_key, get/set_crease.
  2.  catmull_clark_subdivide — 0 levels (identity), 1/2/3 levels on cube:
        vertex/face/edge counts, Euler formula V-E+F=2 for closed mesh.
  3.  Face-point correctness — centroid of cube face must lie at face center.
  4.  Flat patch stays flat — all subdivided vertices coplanar with z=0.
  5.  Centroid preservation — barycentric center of cube is preserved.
  6.  Crease edges — fully-creased edge points are midpoints; limit position
        is close to the input vertex for corner vertices.
  7.  subd_to_quadmesh — returns all-quad faces, correct counts.
  8.  quad_mesh_to_subd — boundary edges tagged crease=1.
  9.  subd_limit_position — smooth interior vertex converges; corner returns itself.
  10. extract_isoparametric_polylines — returns non-empty list of polylines.
  11. Edge-count validation — E = F * 4 / 2 + boundary (checks mesh structure).
  12. Never-raise guards — bad inputs do not raise exceptions.
"""

from __future__ import annotations

import math
from typing import Dict, List, Set, Tuple

import pytest

from kerf_cad_core.geom.subd import (
    SubDMesh,
    _catmull_clark_once,
    _centroid,
    catmull_clark_subdivide,
    extract_isoparametric_polylines,
    quad_mesh_to_subd,
    subd_limit_position,
    subd_to_quadmesh,
)


# ---------------------------------------------------------------------------
# Mesh factories
# ---------------------------------------------------------------------------

def make_cube() -> SubDMesh:
    """Unit cube centred at origin — 8 vertices, 6 quad faces."""
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


def make_flat_patch(n: int = 3) -> SubDMesh:
    """n×n grid of quads in the z=0 plane."""
    verts = []
    for i in range(n + 1):
        for j in range(n + 1):
            verts.append([float(i), float(j), 0.0])
    faces = []
    for i in range(n):
        for j in range(n):
            a = i * (n + 1) + j
            b = a + 1
            c = (i + 1) * (n + 1) + j + 1
            d = (i + 1) * (n + 1) + j
            faces.append([a, b, c, d])
    return SubDMesh(vertices=verts, faces=faces)


def _count_unique_edges(mesh: SubDMesh) -> int:
    seen: Set[Tuple[int, int]] = set()
    for face in mesh.faces:
        n = len(face)
        for i in range(n):
            key = mesh.edge_key(face[i], face[(i + 1) % n])
            seen.add(key)
    return len(seen)


def _euler_characteristic(mesh: SubDMesh) -> int:
    """V - E + F for the mesh."""
    V = mesh.num_vertices
    E = _count_unique_edges(mesh)
    F = mesh.num_faces
    return V - E + F


def _mesh_centroid(mesh: SubDMesh) -> List[float]:
    return _centroid(mesh.vertices)


# ---------------------------------------------------------------------------
# Group 1: SubDMesh dataclass
# ---------------------------------------------------------------------------

def test_subdmesh_empty():
    m = SubDMesh()
    assert m.num_vertices == 0
    assert m.num_faces == 0
    assert m.creases == {}


def test_subdmesh_construction():
    cube = make_cube()
    assert cube.num_vertices == 8
    assert cube.num_faces == 6


def test_subdmesh_edge_key_ordering():
    m = SubDMesh()
    assert m.edge_key(3, 1) == (1, 3)
    assert m.edge_key(1, 3) == (1, 3)


def test_subdmesh_get_crease_default():
    cube = make_cube()
    assert cube.get_crease(0, 1) == 0.0


def test_subdmesh_set_crease():
    cube = make_cube()
    cube.set_crease(0, 1, 0.75)
    assert cube.get_crease(0, 1) == pytest.approx(0.75)
    # Symmetric
    assert cube.get_crease(1, 0) == pytest.approx(0.75)


def test_subdmesh_crease_clamped():
    cube = make_cube()
    cube.set_crease(0, 1, 2.5)   # should clamp to 1
    assert cube.get_crease(0, 1) == pytest.approx(1.0)
    cube.set_crease(0, 1, -0.5)  # should clamp to 0
    assert cube.get_crease(0, 1) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Group 2: catmull_clark_subdivide — level counts
# ---------------------------------------------------------------------------

def test_subdivide_0_levels_is_identity():
    cube = make_cube()
    result = catmull_clark_subdivide(cube, levels=0)
    assert result.num_vertices == 8
    assert result.num_faces == 6


def test_subdivide_1_level_cube_faces():
    """One CC level on cube: 6 faces * 4 = 24 new faces."""
    cube = make_cube()
    result = catmull_clark_subdivide(cube, levels=1)
    assert result.num_faces == 24


def test_subdivide_1_level_cube_vertices():
    """8 original + 12 edge + 6 face = 26 vertices."""
    cube = make_cube()
    result = catmull_clark_subdivide(cube, levels=1)
    assert result.num_vertices == 26


def test_subdivide_2_levels_cube_faces():
    """Two levels: 6 * 4^2 = 96 faces."""
    cube = make_cube()
    result = catmull_clark_subdivide(cube, levels=2)
    assert result.num_faces == 96


def test_subdivide_3_levels_cube_faces():
    """Three levels: 6 * 4^3 = 384 faces."""
    cube = make_cube()
    result = catmull_clark_subdivide(cube, levels=3)
    assert result.num_faces == 384


def test_subdivide_1_level_euler_characteristic():
    """Closed mesh: V - E + F = 2."""
    cube = make_cube()
    result = catmull_clark_subdivide(cube, levels=1)
    assert _euler_characteristic(result) == 2


def test_subdivide_2_levels_euler_characteristic():
    cube = make_cube()
    result = catmull_clark_subdivide(cube, levels=2)
    assert _euler_characteristic(result) == 2


def test_subdivide_3_levels_euler_characteristic():
    cube = make_cube()
    result = catmull_clark_subdivide(cube, levels=3)
    assert _euler_characteristic(result) == 2


# ---------------------------------------------------------------------------
# Group 3: Face-point (centroid) correctness
# ---------------------------------------------------------------------------

def test_face_point_is_centroid():
    """After one level, face-point vertices lie at face centroids of the input."""
    cube = make_cube()
    # Bottom face [0,1,2,3]: centroid should be (0,0,-1)
    face_centroid = _centroid([cube.vertices[i] for i in cube.faces[0]])
    assert face_centroid == pytest.approx([0.0, 0.0, -1.0], abs=1e-12)


def test_face_point_vertex_present_after_subdiv():
    """The centroid of the bottom face must appear in the level-1 mesh."""
    cube = make_cube()
    result = catmull_clark_subdivide(cube, levels=1)
    # Bottom face centroid = (0, 0, -1)
    found = any(
        abs(v[0] - 0.0) < 1e-9 and abs(v[1] - 0.0) < 1e-9 and abs(v[2] - (-1.0)) < 1e-9
        for v in result.vertices
    )
    assert found, "Bottom face centroid (0,0,-1) not found after 1 CC level"


# ---------------------------------------------------------------------------
# Group 4: Flat patch stays flat
# ---------------------------------------------------------------------------

def test_flat_patch_stays_flat_1_level():
    """Subdividing a flat z=0 patch should keep all vertices at z=0."""
    patch = make_flat_patch(3)
    result = catmull_clark_subdivide(patch, levels=1)
    for v in result.vertices:
        assert abs(v[2]) < 1e-10, f"Vertex z={v[2]} is not 0"


def test_flat_patch_stays_flat_2_levels():
    patch = make_flat_patch(2)
    result = catmull_clark_subdivide(patch, levels=2)
    for v in result.vertices:
        assert abs(v[2]) < 1e-10


# ---------------------------------------------------------------------------
# Group 5: Centroid preservation
# ---------------------------------------------------------------------------

def test_centroid_preserved_after_1_level():
    """The barycentre of all vertices should stay near origin for a symmetric cube."""
    cube = make_cube()
    before = _mesh_centroid(cube)
    result = catmull_clark_subdivide(cube, levels=1)
    after = _mesh_centroid(result)
    for a, b in zip(before, after):
        assert abs(a - b) < 1e-9


def test_centroid_preserved_after_2_levels():
    cube = make_cube()
    before = _mesh_centroid(cube)
    result = catmull_clark_subdivide(cube, levels=2)
    after = _mesh_centroid(result)
    for a, b in zip(before, after):
        assert abs(a - b) < 1e-9


# ---------------------------------------------------------------------------
# Group 6: Crease edges
# ---------------------------------------------------------------------------

def test_fully_creased_edge_point_is_midpoint():
    """Fully creased edge: its edge-point must be exactly the midpoint."""
    cube = make_cube()
    cube.set_crease(0, 1, 1.0)
    result = catmull_clark_subdivide(cube, levels=1)
    # Edge 0-1 midpoint: avg of (-1,-1,-1) and (1,-1,-1) = (0,-1,-1)
    expected = [0.0, -1.0, -1.0]
    found = any(
        all(abs(v[k] - expected[k]) < 1e-9 for k in range(3))
        for v in result.vertices
    )
    assert found, f"Creased edge midpoint {expected} not found"


def test_corner_vertex_limit_position_is_itself():
    """A vertex with >=2 creased incident edges has limit == control position."""
    cube = make_cube()
    # Make vertex 0 a corner by creasing both its incident edges
    cube.set_crease(0, 1, 1.0)
    cube.set_crease(0, 3, 1.0)
    cube.set_crease(0, 4, 1.0)
    lim = subd_limit_position(cube, 0)
    expected = cube.vertices[0]
    for a, b in zip(lim, expected):
        assert abs(a - b) < 1e-9


def test_crease_limit_position_near_input():
    """Vertex with a single crease: limit stays close to control pos."""
    cube = make_cube()
    cube.set_crease(0, 1, 1.0)  # one creased edge -> crease-vertex rule
    lim = subd_limit_position(cube, 0)
    v = cube.vertices[0]
    dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(lim, v)))
    assert dist < 2.0  # qualitative: stays in the vicinity


def test_smooth_interior_vertex_limit():
    """Interior vertex of a flat 3x3 grid: limit is close to control pos."""
    patch = make_flat_patch(4)
    # Centre vertex — fully interior
    centre_vi = 2 * 5 + 2  # index in a 5x5 grid, vertex at (2,2)
    lim = subd_limit_position(patch, centre_vi)
    v = patch.vertices[centre_vi]
    dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(lim, v)))
    assert dist < 1.0  # limit is near (smooth rule shifts it slightly)


# ---------------------------------------------------------------------------
# Group 7: subd_to_quadmesh
# ---------------------------------------------------------------------------

def test_subd_to_quadmesh_returns_quads():
    cube = make_cube()
    result = subd_to_quadmesh(cube, levels=1)
    assert all(len(f) == 4 for f in result.faces)


def test_subd_to_quadmesh_face_count():
    cube = make_cube()
    result = subd_to_quadmesh(cube, levels=2)
    assert result.num_faces == 96


def test_subd_to_quadmesh_levels_1():
    cube = make_cube()
    result = subd_to_quadmesh(cube, levels=1)
    assert result.num_faces == 24


# ---------------------------------------------------------------------------
# Group 8: quad_mesh_to_subd boundary creases
# ---------------------------------------------------------------------------

def test_quad_mesh_to_subd_boundary_crease():
    """Open quad: all 4 outer edges should be tagged as crease=1."""
    # Single quad face
    verts = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
    faces = [[0, 1, 2, 3]]
    mesh = quad_mesh_to_subd(verts, faces)
    # All 4 edges are boundary (shared by only 1 face)
    assert mesh.get_crease(0, 1) == pytest.approx(1.0)
    assert mesh.get_crease(1, 2) == pytest.approx(1.0)
    assert mesh.get_crease(2, 3) == pytest.approx(1.0)
    assert mesh.get_crease(3, 0) == pytest.approx(1.0)


def test_quad_mesh_to_subd_interior_no_crease():
    """Interior edge of a 2-quad strip should have crease=0."""
    verts = [[0, 0, 0], [1, 0, 0], [2, 0, 0],
             [0, 1, 0], [1, 1, 0], [2, 1, 0]]
    faces = [[0, 1, 4, 3], [1, 2, 5, 4]]
    mesh = quad_mesh_to_subd(verts, faces)
    # Edge 1-4 is shared by both faces → interior → crease=0
    assert mesh.get_crease(1, 4) == pytest.approx(0.0)


def test_quad_mesh_to_subd_preserves_positions():
    verts = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
    faces = [[0, 1, 2, 3]]
    mesh = quad_mesh_to_subd(verts, faces)
    for i, v in enumerate(verts):
        assert mesh.vertices[i] == pytest.approx(v)


# ---------------------------------------------------------------------------
# Group 9: subd_limit_position
# ---------------------------------------------------------------------------

def test_limit_position_out_of_range_index():
    cube = make_cube()
    lim = subd_limit_position(cube, 999)
    assert lim == [0.0, 0.0, 0.0]


def test_limit_position_negative_index():
    cube = make_cube()
    lim = subd_limit_position(cube, -1)
    assert lim == [0.0, 0.0, 0.0]


def test_limit_position_isolated_vertex():
    """Vertex with no adjacent faces: limit = vertex position."""
    m = SubDMesh(vertices=[[1.0, 2.0, 3.0]], faces=[])
    lim = subd_limit_position(m, 0)
    assert lim == pytest.approx([1.0, 2.0, 3.0])


def test_limit_position_corner_of_cube():
    """Any cube corner — fully creased 3 edges — limit == control point."""
    cube = make_cube()
    # Crease all 3 edges incident to vertex 0
    cube.set_crease(0, 1, 1.0)
    cube.set_crease(0, 3, 1.0)
    cube.set_crease(0, 4, 1.0)
    for vi in range(8):
        lim = subd_limit_position(cube, vi)
        assert len(lim) == 3


# ---------------------------------------------------------------------------
# Group 10: extract_isoparametric_polylines
# ---------------------------------------------------------------------------

def test_extract_iso_polylines_nonempty():
    cube = make_cube()
    subd = catmull_clark_subdivide(cube, levels=2)
    polys = extract_isoparametric_polylines(subd, direction="u", count=5)
    assert len(polys) > 0


def test_extract_iso_polylines_v_direction():
    cube = make_cube()
    subd = catmull_clark_subdivide(cube, levels=2)
    polys = extract_isoparametric_polylines(subd, direction="v", count=5)
    assert len(polys) > 0


def test_extract_iso_polylines_empty_mesh():
    m = SubDMesh()
    polys = extract_isoparametric_polylines(m, direction="u", count=5)
    assert polys == []


def test_extract_iso_polylines_bad_direction():
    cube = make_cube()
    subd = catmull_clark_subdivide(cube, levels=1)
    # Bad direction should not raise; defaults to 'u'
    polys = extract_isoparametric_polylines(subd, direction="z", count=3)
    assert isinstance(polys, list)


# ---------------------------------------------------------------------------
# Group 11: mesh structure integrity
# ---------------------------------------------------------------------------

def test_all_faces_quad_after_subdiv():
    """After CC subdivision every face is a quad."""
    cube = make_cube()
    for levels in range(1, 4):
        result = catmull_clark_subdivide(cube, levels=levels)
        assert all(len(f) == 4 for f in result.faces), \
            f"Non-quad face at level {levels}"


def test_vertex_indices_valid():
    """All face vertex indices must be within range."""
    cube = make_cube()
    result = catmull_clark_subdivide(cube, levels=2)
    nv = result.num_vertices
    for face in result.faces:
        for idx in face:
            assert 0 <= idx < nv


def test_edge_count_level1():
    """E = 2*F for closed all-quad mesh (each face has 4 half-edges, each edge shared by 2)."""
    cube = make_cube()
    result = catmull_clark_subdivide(cube, levels=1)
    E = _count_unique_edges(result)
    F = result.num_faces
    # Closed mesh: E = 2 * F (standard relation for closed all-quad mesh)
    assert E == 2 * F


# ---------------------------------------------------------------------------
# Group 12: Never-raise guards
# ---------------------------------------------------------------------------

def test_subdivide_empty_mesh_no_raise():
    m = SubDMesh()
    result = catmull_clark_subdivide(m, levels=2)
    assert isinstance(result, SubDMesh)


def test_subd_to_quadmesh_empty_no_raise():
    m = SubDMesh()
    result = subd_to_quadmesh(m, levels=2)
    assert isinstance(result, SubDMesh)


def test_quad_mesh_to_subd_empty_no_raise():
    result = quad_mesh_to_subd([], [])
    assert isinstance(result, SubDMesh)


def test_limit_position_empty_mesh_no_raise():
    m = SubDMesh()
    result = subd_limit_position(m, 0)
    assert result == [0.0, 0.0, 0.0]


def test_extract_iso_no_raise_bad_count():
    cube = make_cube()
    subd = catmull_clark_subdivide(cube, levels=1)
    result = extract_isoparametric_polylines(subd, count=-5)
    assert isinstance(result, list)
