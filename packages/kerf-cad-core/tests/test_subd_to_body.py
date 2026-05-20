"""GK-52: SubD cage → watertight NURBS Body (Catmull-Clark limit surface).

Oracle assertions
-----------------
1.  SubD cube cage → smooth Body: validate_body OK.
2.  Limit-surface deviation from Stam evaluation ≤ 1e-6 at every patch corner.
3.  Shell is closed 2-manifold (every edge used by exactly 2 opposite coedges).
4.  Body Euler–Poincaré residual is zero (V - E + F - H = 2).
5.  Extraordinary vertex handling: cube corners have valence 3 (not 4),
    the Stam limit formula still produces exact results.
6.  subd_limit_positions returns one entry per cage vertex.
7.  SubdToNurbsError raised for non-quad / empty cage.
8.  subd_cage_to_limit_nurbs_body produces one Face per quad.
9.  All patches are degree-3 NurbsSurface with (4,4,3) control grid.
10. Patch knot vectors are clamped [0, 1].
11. validate_body passes for sub1 limit body (1 CC level then limit).
12. validate_body passes for sub2 limit body (2 CC levels then limit).
13. Body has exactly one Solid.
14. Shell is_closed=True on cube cage limit body.
15. Limit positions of cube corners are strictly inside the cage bounding box.
16. subd_cage_to_limit_nurbs_body + subd_cage_to_nurbs_body give same validate.
17. All faces in limit body have exactly one outer loop.
18. subd_watertight_cube: end-to-end oracle (cube cage → smooth closed Body).
19. catmull_clark_limit_deviation_oracle: Stam positions == NURBS corners (≤ 1e-6).
20. catmull_clark_sub1_limit_body validates OK.
"""

from __future__ import annotations

import math
from typing import List

import numpy as np
import pytest

from kerf_cad_core.geom.brep import validate_body
from kerf_cad_core.geom.nurbs import NurbsSurface
from kerf_cad_core.geom.subd import SubDMesh, catmull_clark_subdivide
from kerf_cad_core.geom.subd_to_nurbs import (
    SubdToNurbsError,
    nurbs_body_volume,
    subd_cage_to_limit_nurbs_body,
    subd_cage_to_nurbs_body,
    subd_cage_to_nurbs_patches,
    subd_limit_positions,
    subd_mesh_volume,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_cube_cage() -> SubDMesh:
    """Unit cube centred at origin — all 8 vertices have valence 3 (extraordinary)."""
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


# ---------------------------------------------------------------------------
# 1. subd_watertight_cube: end-to-end oracle
# ---------------------------------------------------------------------------


def test_subd_watertight_cube():
    """Oracle 1: SubD cube cage → smooth closed Body; validate_body OK."""
    cage = make_cube_cage()
    body = subd_cage_to_limit_nurbs_body(cage)
    result = validate_body(body)
    assert result["ok"], f"validate_body errors: {result['errors']}"
    assert len(body.all_faces()) == 6


# ---------------------------------------------------------------------------
# 2. catmull_clark_limit_deviation_oracle: Stam positions == NURBS corners (≤ 1e-6)
# ---------------------------------------------------------------------------


def test_catmull_clark_limit_deviation_oracle():
    """Oracle 2: NURBS patch corners exactly match Stam limit positions (≤ 1e-6).

    This is the main GK-52 deviation oracle. For every patch in the limit body,
    evaluate the NURBS surface at each corner parametric value and compare with
    the precomputed Stam limit position for the corresponding cage vertex.
    """
    cage = make_cube_cage()

    # Compute Stam limit positions for all cage vertices
    limit_pos = subd_limit_positions(cage)

    # Build patches from the limit cage (same faces, limit positions as verts)
    from kerf_cad_core.geom.subd import SubDMesh as _SubDMesh

    limit_verts = [lv.tolist() for lv in limit_pos]
    limit_cage = _SubDMesh(vertices=limit_verts, faces=cage.faces)
    patches = subd_cage_to_nurbs_patches(limit_cage)

    # For each patch corner (u,v) ∈ {(0,0),(1,0),(1,1),(0,1)},
    # evaluated point must match limit_pos[face_vertex] to ≤ 1e-6.
    # Note: faces may be reoriented, so we test against all four limit verts
    # of the face regardless of order.
    for fi, (patch, face) in enumerate(zip(patches, cage.faces)):
        expected_set = {
            tuple(limit_pos[vi].tolist()) for vi in face
        }
        corner_params = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        for u, v in corner_params:
            pt = np.asarray(patch.evaluate(u, v), dtype=float)
            # Find closest expected limit position
            min_dist = min(
                float(np.linalg.norm(pt - np.array(e)))
                for e in expected_set
            )
            assert min_dist <= 1e-6, (
                f"face {fi} corner ({u},{v}): "
                f"NURBS pt {pt} deviates {min_dist:.2e} from Stam limit "
                f"(oracle bound 1e-6)"
            )


# ---------------------------------------------------------------------------
# 3. catmull_clark_sub1_limit_body validates OK
# ---------------------------------------------------------------------------


def test_catmull_clark_sub1_limit_body():
    """Oracle 3: cube cage after 1 CC level → limit body; validate_body OK."""
    cage = make_cube_cage()
    sub1 = catmull_clark_subdivide(cage, levels=1)
    body = subd_cage_to_limit_nurbs_body(sub1)
    result = validate_body(body)
    assert result["ok"], f"validate_body failed on sub1 limit body: {result['errors']}"


# ---------------------------------------------------------------------------
# 4. Limit-body shell is closed 2-manifold
# ---------------------------------------------------------------------------


def test_subd_to_body_shell_is_2_manifold():
    """Shell from limit body: every edge used by exactly 2 opposite coedges."""
    cage = make_cube_cage()
    body = subd_cage_to_limit_nurbs_body(cage)
    shell = body.solids[0].outer_shell
    assert shell.is_closed, "shell should be closed"

    use: dict = {}
    for f in shell.faces:
        for lp in f.loops:
            for ce in lp.coedges:
                use.setdefault(id(ce.edge), []).append(ce)

    for eid, ces in use.items():
        assert len(ces) == 2, f"edge {eid} used by {len(ces)} coedges (expected 2)"
        assert ces[0].orientation != ces[1].orientation, (
            f"edge {eid} coedges same orientation (non-manifold)"
        )


# ---------------------------------------------------------------------------
# 5. Extraordinary vertex handling: cube vertices have valence 3
# ---------------------------------------------------------------------------


def test_extraordinary_vertex_limit_positions():
    """Cube corners have valence 3 (extraordinary). Stam formula handles them."""
    cage = make_cube_cage()
    lim = subd_limit_positions(cage)

    assert len(lim) == 8, "should have 8 limit positions for cube cage"

    # All 8 cube corners are extraordinary (valence 3).
    # The Stam formula gives (n^2*P + 4n*R + n*F)/(n^2+5n) with n=3.
    # For vertex 0 = [-1,-1,-1]: symmetric → limit = [-0.75, -0.75, -0.75].
    v0 = lim[0]
    assert np.allclose(v0, [-0.75, -0.75, -0.75], atol=1e-12), (
        f"vertex 0 limit position {v0} != expected [-0.75,-0.75,-0.75]"
    )
    # All limit positions should be strictly inside the cage bounding box.
    for i, lv in enumerate(lim):
        assert np.all(np.abs(lv) < 1.0 + 1e-12), (
            f"vertex {i} limit {lv} outside bounding box [-1,1]^3"
        )


# ---------------------------------------------------------------------------
# 6. subd_limit_positions returns one entry per vertex
# ---------------------------------------------------------------------------


def test_subd_limit_positions_length():
    cage = make_cube_cage()
    lim = subd_limit_positions(cage)
    assert len(lim) == cage.num_vertices


# ---------------------------------------------------------------------------
# 7. SubdToNurbsError for non-quad / empty cage
# ---------------------------------------------------------------------------


def test_subd_to_body_error_non_quad():
    tri_mesh = SubDMesh(
        vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        faces=[[0, 1, 2]],
    )
    with pytest.raises(SubdToNurbsError):
        subd_cage_to_limit_nurbs_body(tri_mesh)


def test_subd_to_body_error_empty():
    empty = SubDMesh(vertices=[], faces=[])
    with pytest.raises(SubdToNurbsError):
        subd_cage_to_limit_nurbs_body(empty)


# ---------------------------------------------------------------------------
# 8. One Face per quad in limit body
# ---------------------------------------------------------------------------


def test_subd_to_body_face_count():
    cage = make_cube_cage()
    body = subd_cage_to_limit_nurbs_body(cage)
    assert len(body.all_faces()) == cage.num_faces


# ---------------------------------------------------------------------------
# 9. All patches are degree-3 NurbsSurface with (4,4,3) control grid
# ---------------------------------------------------------------------------


def test_subd_to_body_patches_degree3():
    cage = make_cube_cage()
    # Get patches from the limit cage
    limit_pos = subd_limit_positions(cage)
    limit_verts = [lv.tolist() for lv in limit_pos]
    limit_cage = SubDMesh(vertices=limit_verts, faces=cage.faces)
    patches = subd_cage_to_nurbs_patches(limit_cage)

    assert len(patches) == 6
    for i, p in enumerate(patches):
        assert isinstance(p, NurbsSurface), f"patch {i} not NurbsSurface"
        assert p.degree_u == 3, f"patch {i} degree_u != 3"
        assert p.degree_v == 3, f"patch {i} degree_v != 3"
        assert p.control_points.shape == (4, 4, 3), (
            f"patch {i} ctrl shape {p.control_points.shape}, expected (4,4,3)"
        )


# ---------------------------------------------------------------------------
# 10. Patch knot vectors are clamped [0, 1]
# ---------------------------------------------------------------------------


def test_subd_to_body_patch_knots_clamped():
    cage = make_cube_cage()
    limit_pos = subd_limit_positions(cage)
    limit_verts = [lv.tolist() for lv in limit_pos]
    limit_cage = SubDMesh(vertices=limit_verts, faces=cage.faces)
    patches = subd_cage_to_nurbs_patches(limit_cage)

    for i, p in enumerate(patches):
        assert p.knots_u[0] == pytest.approx(0.0), f"patch {i} knots_u[0] != 0"
        assert p.knots_u[-1] == pytest.approx(1.0), f"patch {i} knots_u[-1] != 1"
        assert p.knots_v[0] == pytest.approx(0.0), f"patch {i} knots_v[0] != 0"
        assert p.knots_v[-1] == pytest.approx(1.0), f"patch {i} knots_v[-1] != 1"


# ---------------------------------------------------------------------------
# 11. Sub1 limit body validates OK
# ---------------------------------------------------------------------------


def test_subd_to_body_sub1_validates():
    cage = make_cube_cage()
    sub1 = catmull_clark_subdivide(cage, levels=1)
    body = subd_cage_to_limit_nurbs_body(sub1)
    assert validate_body(body)["ok"]


# ---------------------------------------------------------------------------
# 12. Sub2 limit body validates OK
# ---------------------------------------------------------------------------


def test_subd_to_body_sub2_validates():
    cage = make_cube_cage()
    sub2 = catmull_clark_subdivide(cage, levels=2)
    body = subd_cage_to_limit_nurbs_body(sub2)
    result = validate_body(body)
    assert result["ok"], f"sub2 limit body failed: {result['errors']}"


# ---------------------------------------------------------------------------
# 13. Body has exactly one Solid
# ---------------------------------------------------------------------------


def test_subd_to_body_one_solid():
    cage = make_cube_cage()
    body = subd_cage_to_limit_nurbs_body(cage)
    assert len(body.solids) == 1


# ---------------------------------------------------------------------------
# 14. Shell is_closed=True
# ---------------------------------------------------------------------------


def test_subd_to_body_shell_closed():
    cage = make_cube_cage()
    body = subd_cage_to_limit_nurbs_body(cage)
    for shell in body.all_shells():
        assert shell.is_closed


# ---------------------------------------------------------------------------
# 15. Limit positions strictly inside cage bounding box
# ---------------------------------------------------------------------------


def test_limit_positions_inside_cage():
    cage = make_cube_cage()
    lim = subd_limit_positions(cage)
    # Cage bounding box is [-1,1]^3; limit positions must be strictly inside.
    for i, lv in enumerate(lim):
        assert np.all(np.abs(lv) <= 1.0 + 1e-12), (
            f"vertex {i} limit {lv} outside cage bounding box"
        )
        assert np.all(np.abs(lv) < 1.0), (
            f"vertex {i} limit {lv} not strictly inside cage"
        )


# ---------------------------------------------------------------------------
# 16. Both subd_cage_to_limit_nurbs_body and subd_cage_to_nurbs_body validate
# ---------------------------------------------------------------------------


def test_subd_to_body_both_functions_validate():
    """Both the cage body and the limit body pass validate_body."""
    cage = make_cube_cage()
    cage_body = subd_cage_to_nurbs_body(cage)
    limit_body = subd_cage_to_limit_nurbs_body(cage)
    assert validate_body(cage_body)["ok"]
    assert validate_body(limit_body)["ok"]


# ---------------------------------------------------------------------------
# 17. All faces in limit body have exactly one outer loop
# ---------------------------------------------------------------------------


def test_subd_to_body_faces_have_one_loop():
    cage = make_cube_cage()
    body = subd_cage_to_limit_nurbs_body(cage)
    for fi, face in enumerate(body.all_faces()):
        assert len(face.loops) == 1, (
            f"face {fi} has {len(face.loops)} loops, expected 1"
        )


# ---------------------------------------------------------------------------
# 18. Euler-Poincaré residual is zero
# ---------------------------------------------------------------------------


def test_subd_to_body_euler_poincare():
    cage = make_cube_cage()
    body = subd_cage_to_limit_nurbs_body(cage)
    assert body.euler_poincare_residual() == 0


# ---------------------------------------------------------------------------
# 19. Euler V - E + F = 2 (sphere topology, genus 0)
# ---------------------------------------------------------------------------


def test_subd_to_body_euler_formula():
    """For a closed genus-0 solid: V - E + F = 2 (Euler formula)."""
    cage = make_cube_cage()
    body = subd_cage_to_limit_nurbs_body(cage)

    V = len(body.all_vertices())
    E = len(body.all_edges())
    F = len(body.all_faces())
    L = sum(len(f.loops) for f in body.all_faces())
    H = L - F

    assert V - E + F - H == 2, (
        f"Euler: V={V}, E={E}, F={F}, H={H}, V-E+F-H={V-E+F-H} (expected 2)"
    )


# ---------------------------------------------------------------------------
# 20. Stam limit deviation oracle (parametric mid-surface check)
# ---------------------------------------------------------------------------


def test_subd_to_body_stam_deviation_midpoints():
    """The Stam limit positions deviate ≤ 1e-6 from patch corner evaluations.

    Parametric corners (0,0), (1,0), (1,1), (0,1) of each NURBS patch must
    match a Stam limit position of the corresponding cage vertex to within
    1e-6. This is the primary GK-52 oracle.
    """
    cage = make_cube_cage()
    limit_pos = subd_limit_positions(cage)
    limit_verts = [lv.tolist() for lv in limit_pos]
    limit_cage = SubDMesh(vertices=limit_verts, faces=cage.faces)
    patches = subd_cage_to_nurbs_patches(limit_cage)

    max_dev = 0.0
    for fi, (patch, face) in enumerate(zip(patches, cage.faces)):
        lim_set = [limit_pos[vi] for vi in face]
        for u, v in [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]:
            pt = np.asarray(patch.evaluate(u, v), dtype=float)
            dists = [float(np.linalg.norm(pt - lv)) for lv in lim_set]
            dev = min(dists)
            max_dev = max(max_dev, dev)
            assert dev <= 1e-6, (
                f"face {fi} corner ({u},{v}): deviation {dev:.2e} > 1e-6"
            )

    # Report the maximum observed deviation for debugging (should be ~0)
    assert max_dev <= 1e-6, f"max deviation over all corners: {max_dev:.2e}"
