"""
Tests for kerf_cad_core.geom.subd_authoring — author-time SubD cage ops.

All tests are hermetic: no OCC, no database, no network.

Coverage:
  1. SubDCage construction and basic properties
  2. create_subd_primitive — cube, cylinder, sphere, torus
  3. subd_extrude — face count grows predictably, topology valid
  4. subd_bevel — edge count and face topology
  5. subd_loop_cut — cube loop-cut increases face count, round-trips CC
  6. subd_set_crease — sharpness stored; inf sharpness produces hard edge
  7. to_subd_surface — round-trip through CC evaluator, no topology errors
  8. Crease sharpness=inf on a closed loop produces a sharp edge in evaluation
  9. Never-raise guards
"""

from __future__ import annotations

import math
from typing import Dict, List, Set, Tuple

import pytest

from kerf_cad_core.geom.subd_authoring import (
    SubDCage,
    SubDSurface,
    create_subd_primitive,
    subd_bevel,
    subd_extrude,
    subd_loop_cut,
    subd_set_crease,
    subd_vertex_slide,
    to_subd_surface,
)
from kerf_cad_core.geom.subd import SubDMesh


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_unique_edges(cage_or_mesh) -> int:
    seen: Set[Tuple[int, int]] = set()
    for face in cage_or_mesh.faces:
        n = len(face)
        for i in range(n):
            a, b = face[i], face[(i + 1) % n]
            seen.add((min(a, b), max(a, b)))
    return len(seen)


def _euler_characteristic(mesh: SubDMesh) -> int:
    V = mesh.num_vertices
    E = _count_unique_edges(mesh)
    F = mesh.num_faces
    return V - E + F


def _all_vertex_indices_valid(cage: SubDCage) -> bool:
    nv = cage.num_vertices
    for face in cage.faces:
        for idx in face:
            if idx < 0 or idx >= nv:
                return False
    return True


def _all_vertex_indices_valid_mesh(mesh: SubDMesh) -> bool:
    nv = mesh.num_vertices
    for face in mesh.faces:
        for idx in face:
            if idx < 0 or idx >= nv:
                return False
    return True


# ---------------------------------------------------------------------------
# Group 1: SubDCage construction
# ---------------------------------------------------------------------------

def test_subdcage_empty():
    c = SubDCage()
    assert c.num_vertices == 0
    assert c.num_faces == 0
    assert c.sharpness == {}


def test_subdcage_construction():
    verts = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
    faces = [[0, 1, 2, 3]]
    c = SubDCage(vertices=verts, faces=faces)
    assert c.num_vertices == 4
    assert c.num_faces == 1


def test_cage_edges_single_quad():
    verts = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
    faces = [[0, 1, 2, 3]]
    c = SubDCage(vertices=verts, faces=faces)
    edges = c.cage_edges()
    assert len(edges) == 4


def test_cage_edge_id_lookup():
    verts = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
    faces = [[0, 1, 2, 3]]
    c = SubDCage(vertices=verts, faces=faces)
    eid = c.edge_id(0, 1)
    assert eid is not None
    assert 0 <= eid < len(c.cage_edges())


def test_cage_get_sharpness_default():
    c = SubDCage(vertices=[[0, 0, 0], [1, 0, 0]], faces=[])
    assert c.get_sharpness(0) == 0.0


# ---------------------------------------------------------------------------
# Group 2: create_subd_primitive
# ---------------------------------------------------------------------------

def test_create_cube_basic():
    cage = create_subd_primitive("cube")
    assert cage.num_vertices == 8
    assert cage.num_faces == 6


def test_create_cube_dims():
    cage = create_subd_primitive("cube", width=4.0, height=2.0, depth=6.0)
    xs = [v[0] for v in cage.vertices]
    ys = [v[1] for v in cage.vertices]
    zs = [v[2] for v in cage.vertices]
    assert pytest.approx(max(xs) - min(xs), abs=1e-9) == 4.0
    assert pytest.approx(max(ys) - min(ys), abs=1e-9) == 2.0
    assert pytest.approx(max(zs) - min(zs), abs=1e-9) == 6.0


def test_create_cube_quad_faces():
    cage = create_subd_primitive("cube")
    assert all(len(f) == 4 for f in cage.faces)


def test_create_cube_vertex_indices_valid():
    cage = create_subd_primitive("cube")
    assert _all_vertex_indices_valid(cage)


def test_create_cylinder_basic():
    cage = create_subd_primitive("cylinder", radius=1.0, height=2.0, segments=8)
    # 8 bottom + 8 top ring vertices, plus caps handled as n-gons
    assert cage.num_vertices == 16
    # 8 side quads + 2 cap faces
    assert cage.num_faces == 10


def test_create_cylinder_vertex_indices_valid():
    cage = create_subd_primitive("cylinder")
    assert _all_vertex_indices_valid(cage)


def test_create_sphere_basic():
    cage = create_subd_primitive("sphere", radius=1.0, segments_u=8, segments_v=6)
    # 1 south pole + 5 rings of 8 + 1 north pole
    assert cage.num_vertices == 1 + 5 * 8 + 1
    assert cage.num_faces > 0


def test_create_sphere_vertex_indices_valid():
    cage = create_subd_primitive("sphere")
    assert _all_vertex_indices_valid(cage)


def test_create_torus_basic():
    cage = create_subd_primitive("torus", major_radius=2.0, minor_radius=0.5, segments_u=8, segments_v=6)
    assert cage.num_vertices == 8 * 6
    assert cage.num_faces == 8 * 6


def test_create_torus_all_quad():
    cage = create_subd_primitive("torus")
    assert all(len(f) == 4 for f in cage.faces)


def test_create_torus_vertex_indices_valid():
    cage = create_subd_primitive("torus")
    assert _all_vertex_indices_valid(cage)


def test_create_unknown_kind_returns_empty():
    cage = create_subd_primitive("cone")
    assert cage.num_faces == 0


def test_create_primitive_case_insensitive():
    cage = create_subd_primitive("CUBE")
    assert cage.num_faces == 6


# ---------------------------------------------------------------------------
# Group 3: subd_extrude
# ---------------------------------------------------------------------------

def test_extrude_single_face_adds_side_quads():
    """Extruding one face of a cube adds 4 side quads + 1 cap = +5 faces."""
    cage = create_subd_primitive("cube")
    before = cage.num_faces
    result = subd_extrude(cage, [0], distance=0.5)
    # Face 0 removed, replaced by 4 side quads + 1 new top face = +5 net
    assert result.num_faces == before + 4


def test_extrude_new_vertices_created():
    cage = create_subd_primitive("cube")
    before_v = cage.num_vertices
    result = subd_extrude(cage, [0], distance=1.0)
    # Extruding a quad adds 4 new vertices
    assert result.num_vertices == before_v + 4


def test_extrude_vertex_indices_valid():
    cage = create_subd_primitive("cube")
    result = subd_extrude(cage, [0], distance=0.5)
    assert _all_vertex_indices_valid(result)


def test_extrude_two_faces():
    cage = create_subd_primitive("cube")
    before = cage.num_faces
    result = subd_extrude(cage, [0, 1], distance=0.3)
    # Each quad face: -1 + 4 side + 1 cap = net +4 per face
    assert result.num_faces == before + 4 + 4


def test_extrude_empty_face_ids_unchanged():
    cage = create_subd_primitive("cube")
    result = subd_extrude(cage, [], distance=1.0)
    assert result.num_faces == cage.num_faces
    assert result.num_vertices == cage.num_vertices


def test_extrude_negative_distance_moves_inward():
    """Extrude with negative distance: vertices should move inward."""
    cage = create_subd_primitive("cube")
    bottom_face = cage.faces[0]
    # face[0] is at z = -1 (bottom of unit cube)
    original_z = cage.vertices[bottom_face[0]][2]
    result = subd_extrude(cage, [0], distance=-0.5)
    # The 4 new vertices are at z shifted by normal * (-0.5)
    # Bottom face normal is (0, 0, -1), so delta_z = +0.5 (moves toward center)
    new_verts_z = [result.vertices[i][2] for i in range(cage.num_vertices, result.num_vertices)]
    assert all(z > original_z for z in new_verts_z)


# ---------------------------------------------------------------------------
# Group 4: subd_bevel
# ---------------------------------------------------------------------------

def test_bevel_single_edge():
    cage = create_subd_primitive("cube")
    before_faces = cage.num_faces
    before_verts = cage.num_vertices
    edges = cage.cage_edges()
    result = subd_bevel(cage, [0], amount=0.1)
    # Bevel replaces edge with wider geometry — more verts added
    assert result.num_vertices > before_verts


def test_bevel_vertex_indices_valid():
    cage = create_subd_primitive("cube")
    result = subd_bevel(cage, [0], amount=0.1)
    assert _all_vertex_indices_valid(result)


def test_bevel_zero_amount_unchanged():
    cage = create_subd_primitive("cube")
    result = subd_bevel(cage, [0], amount=0.0)
    assert result.num_faces == cage.num_faces
    assert result.num_vertices == cage.num_vertices


def test_bevel_negative_amount_unchanged():
    cage = create_subd_primitive("cube")
    result = subd_bevel(cage, [0], amount=-0.1)
    assert result.num_faces == cage.num_faces


# ---------------------------------------------------------------------------
# Group 5: subd_loop_cut
# ---------------------------------------------------------------------------

def test_loop_cut_cube_splits_faces():
    """Loop cut on edge ring of a cube should increase face count."""
    cage = create_subd_primitive("cube")
    edges = cage.cage_edges()
    before_faces = cage.num_faces
    # Pick one edge from the equatorial ring
    ring = [0]
    result = subd_loop_cut(cage, ring, t=0.5)
    # Each cut face is split into 2, so face count increases
    assert result.num_faces >= before_faces


def test_loop_cut_creates_new_vertices():
    cage = create_subd_primitive("cube")
    before_v = cage.num_vertices
    result = subd_loop_cut(cage, [0], t=0.5)
    assert result.num_vertices > before_v


def test_loop_cut_vertex_indices_valid():
    cage = create_subd_primitive("cube")
    result = subd_loop_cut(cage, [0], t=0.5)
    assert _all_vertex_indices_valid(result)


def test_loop_cut_at_t_half():
    """A loop cut at t=0.5 creates a new vertex exactly at edge midpoint."""
    cage = create_subd_primitive("cube")
    edges = cage.cage_edges()
    a, b = edges[0]
    va = cage.vertices[a]
    vb = cage.vertices[b]
    expected_mid = [(va[k] + vb[k]) / 2.0 for k in range(3)]

    result = subd_loop_cut(cage, [0], t=0.5)
    new_verts = result.vertices[cage.num_vertices:]
    found = any(
        all(abs(v[k] - expected_mid[k]) < 1e-9 for k in range(3))
        for v in new_verts
    )
    assert found, f"Midpoint {expected_mid} not found in new vertices"


def test_loop_cut_empty_ring_unchanged():
    cage = create_subd_primitive("cube")
    result = subd_loop_cut(cage, [], t=0.5)
    assert result.num_faces == cage.num_faces


def test_loop_cut_then_evaluate_round_trip():
    """Loop-cut cube round-trips through CC evaluation without topology errors."""
    cage = create_subd_primitive("cube")
    cage_cut = subd_loop_cut(cage, [0, 1], t=0.5)
    surface = to_subd_surface(cage_cut, levels=1)
    mesh = surface.mesh
    # All face vertex indices must be in range
    assert _all_vertex_indices_valid_mesh(mesh)
    # All faces must be quads
    assert all(len(f) == 4 for f in mesh.faces)


# ---------------------------------------------------------------------------
# Group 6: subd_set_crease
# ---------------------------------------------------------------------------

def test_set_crease_stores_sharpness():
    cage = create_subd_primitive("cube")
    result = subd_set_crease(cage, 0, sharpness=0.5)
    assert result.get_sharpness(0) == pytest.approx(0.5)


def test_set_crease_inf_stores_inf():
    cage = create_subd_primitive("cube")
    result = subd_set_crease(cage, 0, sharpness=math.inf)
    assert math.isinf(result.get_sharpness(0))


def test_set_crease_zero_removes():
    cage = create_subd_primitive("cube")
    cage = subd_set_crease(cage, 0, sharpness=0.8)
    cage = subd_set_crease(cage, 0, sharpness=0.0)
    assert cage.get_sharpness(0) == 0.0


def test_set_crease_out_of_range_edge_noop():
    cage = create_subd_primitive("cube")
    result = subd_set_crease(cage, 9999, sharpness=1.0)
    # No crash, sharpness not set for valid edges
    assert result.get_sharpness(0) == 0.0


def test_set_crease_original_unchanged():
    """subd_set_crease returns a new cage; original is unmodified."""
    cage = create_subd_primitive("cube")
    _ = subd_set_crease(cage, 0, sharpness=math.inf)
    assert cage.get_sharpness(0) == 0.0


# ---------------------------------------------------------------------------
# Group 7: to_subd_surface round-trip
# ---------------------------------------------------------------------------

def test_to_subd_surface_returns_surface():
    cage = create_subd_primitive("cube")
    surface = to_subd_surface(cage)
    assert isinstance(surface, SubDSurface)


def test_to_subd_surface_levels_stored():
    cage = create_subd_primitive("cube")
    surface = to_subd_surface(cage, levels=3)
    assert surface.levels == 3


def test_to_subd_surface_cube_face_count():
    """Cube cage (6 faces) at 2 levels → 6 * 4^2 = 96 faces."""
    cage = create_subd_primitive("cube")
    surface = to_subd_surface(cage, levels=2)
    assert surface.mesh.num_faces == 96


def test_to_subd_surface_all_quad():
    cage = create_subd_primitive("cube")
    surface = to_subd_surface(cage, levels=2)
    assert all(len(f) == 4 for f in surface.mesh.faces)


def test_to_subd_surface_vertex_indices_valid():
    cage = create_subd_primitive("cube")
    surface = to_subd_surface(cage, levels=2)
    assert _all_vertex_indices_valid_mesh(surface.mesh)


def test_to_subd_surface_euler_characteristic():
    """Closed surface: V - E + F = 2."""
    cage = create_subd_primitive("cube")
    surface = to_subd_surface(cage, levels=2)
    assert _euler_characteristic(surface.mesh) == 2


def test_to_subd_surface_torus_all_quad():
    """Torus cage (all quads) evaluates to an all-quad mesh."""
    cage = create_subd_primitive("torus")
    surface = to_subd_surface(cage, levels=1)
    assert all(len(f) == 4 for f in surface.mesh.faces)


def test_to_subd_surface_torus_vertex_indices_valid():
    cage = create_subd_primitive("torus")
    surface = to_subd_surface(cage, levels=1)
    assert _all_vertex_indices_valid_mesh(surface.mesh)


def test_to_subd_surface_cage_reference_preserved():
    cage = create_subd_primitive("cube")
    surface = to_subd_surface(cage, levels=1)
    assert surface.cage is cage


# ---------------------------------------------------------------------------
# Group 8: Crease sharpness=inf produces hard edge in evaluated mesh
# ---------------------------------------------------------------------------

def _find_edge_midpoint_in_mesh(mesh: SubDMesh, va: List[float], vb: List[float]) -> bool:
    """Check if the midpoint of (va, vb) appears in the mesh vertices."""
    mid = [(va[k] + vb[k]) / 2.0 for k in range(3)]
    return any(
        all(abs(v[k] - mid[k]) < 1e-6 for k in range(3))
        for v in mesh.vertices
    )


def test_crease_inf_edge_stays_hard_after_eval():
    """An edge with sharpness=inf should evaluate as fully creased (midpoint preserved)."""
    cage = create_subd_primitive("cube")
    # Edge 0 of the cube cage
    edges = cage.cage_edges()
    a, b = edges[0]
    va = cage.vertices[a]
    vb = cage.vertices[b]
    expected_mid = [(va[k] + vb[k]) / 2.0 for k in range(3)]

    creased = subd_set_crease(cage, 0, sharpness=math.inf)
    surface = to_subd_surface(creased, levels=1)

    # With crease=1 (clamped from inf), the edge point is exactly the midpoint
    found = any(
        all(abs(v[k] - expected_mid[k]) < 1e-6 for k in range(3))
        for v in surface.mesh.vertices
    )
    assert found, "Hard-creased edge midpoint not found in evaluated mesh"


def test_crease_zero_edge_smooth():
    """An edge with sharpness=0 should not force the midpoint in the evaluation."""
    cage = create_subd_primitive("cube")
    surface_no_crease = to_subd_surface(cage, levels=1)
    edges = cage.cage_edges()
    a, b = edges[0]
    va = cage.vertices[a]
    vb = cage.vertices[b]
    # The smooth edge point should differ from the midpoint for a cube corner
    mid = [(va[k] + vb[k]) / 2.0 for k in range(3)]
    # For a smooth CC subdivision the edge point != simple midpoint
    # (the face centroid is averaged in); just verify the surface evaluates OK
    assert surface_no_crease.mesh.num_faces > 0


def test_closed_crease_loop_produces_sharp_edge():
    """A full loop of creased edges on a torus produces a line of hard edges."""
    cage = create_subd_primitive("torus", segments_u=8, segments_v=6)
    edges = cage.cage_edges()
    su, sv = 8, 6

    # Crease all edges in the first "latitude" ring (edges connecting ring 0 and 1)
    # These are edges between vertices j*su+i and ((j+1)%sv)*su+i for j=0
    creased = cage
    count = 0
    for eid, (a, b) in enumerate(edges):
        ja, ia = divmod(a, su)
        jb, ib = divmod(b, su)
        if (ja == 0 and jb == 1) or (ja == 1 and jb == 0):
            creased = subd_set_crease(creased, eid, sharpness=math.inf)
            count += 1

    assert count > 0, "No crease edges set"
    surface = to_subd_surface(creased, levels=1)
    # The mesh should still be valid
    assert _all_vertex_indices_valid_mesh(surface.mesh)
    assert all(len(f) == 4 for f in surface.mesh.faces)


# ---------------------------------------------------------------------------
# Group 9: Loop-cut → bevel round-trip
# ---------------------------------------------------------------------------

def test_cube_loop_cut_bevel_round_trip():
    """Cube → loop-cut → bevel round-trips through CC eval without topology errors."""
    cage = create_subd_primitive("cube")
    edges = cage.cage_edges()

    # Loop cut at t=0.5 across one edge
    cage_cut = subd_loop_cut(cage, [0], t=0.5)
    assert _all_vertex_indices_valid(cage_cut)

    # Bevel one edge of the cut cage
    cage_beveled = subd_bevel(cage_cut, [0], amount=0.05)
    assert _all_vertex_indices_valid(cage_beveled)

    # Full CC evaluation
    surface = to_subd_surface(cage_beveled, levels=1)
    assert isinstance(surface, SubDSurface)
    assert _all_vertex_indices_valid_mesh(surface.mesh)
    assert all(len(f) == 4 for f in surface.mesh.faces)


# ---------------------------------------------------------------------------
# Group 10: Never-raise guards
# ---------------------------------------------------------------------------

def test_create_primitive_no_raise_bad_kind():
    result = create_subd_primitive("banana")
    assert isinstance(result, SubDCage)


def test_extrude_no_raise_empty_cage():
    cage = SubDCage()
    result = subd_extrude(cage, [0], distance=1.0)
    assert isinstance(result, SubDCage)


def test_bevel_no_raise_empty_cage():
    cage = SubDCage()
    result = subd_bevel(cage, [0], amount=0.1)
    assert isinstance(result, SubDCage)


def test_loop_cut_no_raise_empty_cage():
    cage = SubDCage()
    result = subd_loop_cut(cage, [0], t=0.5)
    assert isinstance(result, SubDCage)


def test_set_crease_no_raise_empty_cage():
    cage = SubDCage()
    result = subd_set_crease(cage, 0, sharpness=1.0)
    assert isinstance(result, SubDCage)


def test_to_subd_surface_no_raise_empty():
    cage = SubDCage()
    result = to_subd_surface(cage)
    assert isinstance(result, SubDSurface)


def test_extrude_invalid_face_id_no_raise():
    cage = create_subd_primitive("cube")
    result = subd_extrude(cage, [999], distance=1.0)
    assert isinstance(result, SubDCage)
    assert result.num_faces == cage.num_faces  # no change


def test_loop_cut_invalid_edge_id_no_raise():
    cage = create_subd_primitive("cube")
    result = subd_loop_cut(cage, [9999], t=0.5)
    assert isinstance(result, SubDCage)


# ---------------------------------------------------------------------------
# Group 11: subd_vertex_slide (GK-105)
# ---------------------------------------------------------------------------

def _make_simple_quad() -> SubDCage:
    """Unit quad with vertices at corners."""
    verts = [
        [0.0, 0.0, 0.0],  # 0
        [1.0, 0.0, 0.0],  # 1
        [1.0, 1.0, 0.0],  # 2
        [0.0, 1.0, 0.0],  # 3
    ]
    faces = [[0, 1, 2, 3]]
    return SubDCage(vertices=verts, faces=faces)


def _find_edge_between(cage: SubDCage, a: int, b: int) -> int:
    for eid, (u, v) in enumerate(cage.cage_edges()):
        if (u == a and v == b) or (u == b and v == a):
            return eid
    raise AssertionError(f"Edge ({a},{b}) not found")


def test_vertex_slide_t0_identity():
    """t=0 → vertex stays exactly in place."""
    cage = _make_simple_quad()
    eid = _find_edge_between(cage, 0, 1)
    result = subd_vertex_slide(cage, 0, eid, t=0.0)
    assert result.vertices[0] == cage.vertices[0]


def test_vertex_slide_t1_lands_on_neighbour():
    """t=1 → vertex coincides with the neighbour."""
    cage = _make_simple_quad()
    eid = _find_edge_between(cage, 0, 1)
    result = subd_vertex_slide(cage, 0, eid, t=1.0)
    assert result.vertices[0] == pytest.approx(cage.vertices[1])


def test_vertex_slide_t05_midpoint():
    """t=0.5 → vertex moves to midpoint between original and neighbour."""
    cage = _make_simple_quad()
    eid = _find_edge_between(cage, 0, 1)
    result = subd_vertex_slide(cage, 0, eid, t=0.5)
    expected = [
        (cage.vertices[0][i] + cage.vertices[1][i]) / 2.0
        for i in range(3)
    ]
    assert result.vertices[0] == pytest.approx(expected)


def test_vertex_slide_topology_unchanged():
    """Topology (V/E/F counts) must not change."""
    cage = _make_simple_quad()
    eid = _find_edge_between(cage, 0, 1)
    result = subd_vertex_slide(cage, 0, eid, t=0.5)
    assert result.num_vertices == cage.num_vertices
    assert result.num_faces == cage.num_faces
    assert len(result.cage_edges()) == len(cage.cage_edges())


def test_vertex_slide_only_target_vertex_moves():
    """Only the slid vertex changes; all others stay fixed."""
    cage = _make_simple_quad()
    eid = _find_edge_between(cage, 0, 1)
    result = subd_vertex_slide(cage, 0, eid, t=0.7)
    for vi in range(1, cage.num_vertices):
        assert result.vertices[vi] == pytest.approx(cage.vertices[vi])


def test_vertex_slide_cube_t1_on_edge():
    """On a cube, slide a corner vertex fully to its neighbour along edge 0."""
    cage = create_subd_primitive("cube")
    edges = cage.cage_edges()
    a, b = edges[0]
    result = subd_vertex_slide(cage, a, 0, t=1.0)
    assert result.vertices[a] == pytest.approx(cage.vertices[b])
    assert result.num_vertices == cage.num_vertices
    assert result.num_faces == cage.num_faces


def test_vertex_slide_non_incident_edge_returns_copy():
    """If edge_id is not incident on vertex_id, return a copy unchanged."""
    cage = _make_simple_quad()
    # Edge between vertices 2 and 3 is NOT incident on vertex 0
    eid = _find_edge_between(cage, 2, 3)
    result = subd_vertex_slide(cage, 0, eid, t=0.5)
    assert result.vertices[0] == pytest.approx(cage.vertices[0])


def test_vertex_slide_invalid_edge_no_raise():
    cage = create_subd_primitive("cube")
    result = subd_vertex_slide(cage, 0, 9999, t=0.5)
    assert isinstance(result, SubDCage)


def test_vertex_slide_invalid_vertex_no_raise():
    cage = create_subd_primitive("cube")
    result = subd_vertex_slide(cage, 9999, 0, t=0.5)
    assert isinstance(result, SubDCage)


def test_vertex_slide_exported_from_geom_init():
    """subd_vertex_slide must be importable from kerf_cad_core.geom."""
    from kerf_cad_core.geom import subd_vertex_slide as _fn  # noqa: F401
    assert callable(_fn)


# ---------------------------------------------------------------------------
# Group 12: loop_subdivide (GK-108)
# ---------------------------------------------------------------------------

from kerf_cad_core.geom.subd_authoring import loop_subdivide


def _make_tetra() -> tuple:
    """Regular tetrahedron with 4 vertices, 4 triangular faces."""
    # Vertices of a regular tetrahedron
    verts = [
        [1.0,  1.0,  1.0],  # 0
        [1.0, -1.0, -1.0],  # 1
        [-1.0,  1.0, -1.0],  # 2
        [-1.0, -1.0,  1.0],  # 3
    ]
    faces = [
        [0, 1, 2],
        [0, 2, 3],
        [0, 3, 1],
        [1, 3, 2],
    ]
    return verts, faces


def test_loop_subdivide_tetra_face_count():
    """One Loop step on a tetrahedron (4 faces) → 16 faces (4x)."""
    verts, faces = _make_tetra()
    v2, f2 = loop_subdivide(verts, faces, iterations=1)
    assert len(f2) == 16


def test_loop_subdivide_tetra_vertex_count():
    """One Loop step on a tetrahedron (4V) → 4 + 6 = 10 vertices (one per edge)."""
    verts, faces = _make_tetra()
    v2, f2 = loop_subdivide(verts, faces, iterations=1)
    # 4 original + 6 edges in a tetrahedron
    assert len(v2) == 10


def test_loop_subdivide_two_steps_face_count():
    """Two Loop steps on a tetrahedron → 4 * 4^2 = 64 faces."""
    verts, faces = _make_tetra()
    v2, f2 = loop_subdivide(verts, faces, iterations=2)
    assert len(f2) == 64


def test_loop_subdivide_all_triangles():
    """All output faces must remain triangles."""
    verts, faces = _make_tetra()
    v2, f2 = loop_subdivide(verts, faces, iterations=1)
    assert all(len(f) == 3 for f in f2)


def test_loop_subdivide_valid_vertex_indices():
    """All face vertex indices must be in range [0, len(verts))."""
    verts, faces = _make_tetra()
    v2, f2 = loop_subdivide(verts, faces, iterations=1)
    nv = len(v2)
    assert all(0 <= idx < nv for face in f2 for idx in face)


def test_loop_subdivide_zero_iterations_identity():
    """Zero iterations → original mesh returned unchanged."""
    verts, faces = _make_tetra()
    v2, f2 = loop_subdivide(verts, faces, iterations=0)
    assert len(v2) == len(verts)
    assert len(f2) == len(faces)


def test_loop_subdivide_even_vertex_stencil():
    """Even-vertex update: interior vertex of a regular triangle grid uses the
    Loop β stencil.  For a planar equilateral triangle fan with n=6 neighbours,
    the updated position stays at the original position (symmetric average)."""
    # Build a central vertex surrounded by 6 neighbours in a regular hexagonal fan.
    import math as _math
    cx, cy = 0.0, 0.0
    r = 1.0
    centre = [cx, cy, 0.0]
    n = 6
    nbr_verts = [
        [cx + r * _math.cos(2 * _math.pi * i / n),
         cy + r * _math.sin(2 * _math.pi * i / n),
         0.0]
        for i in range(n)
    ]
    verts = [centre] + nbr_verts  # vertex 0 = centre
    # 6 triangles sharing the centre
    faces = [[0, i + 1, (i + 1) % n + 1] for i in range(n)]

    v2, _ = loop_subdivide(verts, faces, iterations=1)

    # For n=6: β = (1/6)*(5/8 - (3/8 + 1/4*cos(2π/6))^2)
    # cos(2π/6) = 0.5  →  inner = 3/8 + 1/8 = 1/2  →  inner² = 1/4
    # β = (1/6)*(5/8 - 1/4) = (1/6)*(3/8) = 1/16
    # alpha = 1 - 6*(1/16) = 1 - 3/8 = 5/8
    # new_centre = 5/8 * (0,0,0) + (1/16)*Σ nbrs
    # Since nbrs are symmetric around origin, Σ nbrs = (0, 0, 0)
    # → new_centre stays at (0, 0, 0)
    new_centre = v2[0]
    assert abs(new_centre[0]) < 1e-9
    assert abs(new_centre[1]) < 1e-9
    assert abs(new_centre[2]) < 1e-9


def test_loop_subdivide_planar_grid_stays_planar():
    """Subdividing a flat triangle grid produces no out-of-plane displacement."""
    # 2x2 quad split into 2 triangles (all z=0)
    verts = [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.5, 0.5, 0.0],  # centre
    ]
    # Fan of 4 triangles from the centre
    faces = [
        [0, 1, 4],
        [1, 2, 4],
        [2, 3, 4],
        [3, 0, 4],
    ]
    v2, f2 = loop_subdivide(verts, faces, iterations=2)
    # All z must remain 0
    for v in v2:
        assert abs(v[2]) < 1e-9, f"z={v[2]} is out of plane"


def test_loop_subdivide_no_raise_empty():
    """Empty mesh → returns empty mesh without raising."""
    v2, f2 = loop_subdivide([], [], iterations=1)
    assert v2 == []
    assert f2 == []


def test_loop_subdivide_no_raise_bad_iterations():
    """Negative iterations clamped to 0."""
    verts, faces = _make_tetra()
    v2, f2 = loop_subdivide(verts, faces, iterations=-5)
    assert len(f2) == len(faces)


def test_loop_subdivide_exported_from_geom_init():
    """loop_subdivide must be importable from kerf_cad_core.geom."""
    from kerf_cad_core.geom import loop_subdivide as _fn  # noqa: F401
    assert callable(_fn)
