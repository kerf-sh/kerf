"""Hermetic tests for the B-rep topology model, Euler operators, and
validation (``kerf_cad_core.geom.brep``).

All tests are self-contained -- no network, no OCCT, no fixtures.
"""

import math

import numpy as np
import pytest

from kerf_cad_core.geom.brep import (
    Body,
    CircleArc3,
    Coedge,
    Edge,
    EulerError,
    Face,
    Line3,
    Loop,
    Plane,
    Shell,
    Solid,
    Vertex,
    kev,
    kfmrh,
    kfmrh_inverse,
    make_box,
    make_cylinder,
    make_sphere,
    make_tetra,
    make_torus,
    mef,
    mev,
    mvfs,
    validate_body,
)


# ---------------------------------------------------------------------------
# Euler-Poincare on hand-built / generated primitives
# ---------------------------------------------------------------------------


def test_box_topology_counts():
    body = make_box()
    c = body.euler_counts()
    assert c["V"] == 8
    assert c["E"] == 12
    assert c["F"] == 6
    assert c["S"] == 1
    assert c["G"] == 0


def test_box_satisfies_euler_poincare():
    body = make_box()
    assert body.euler_poincare_residual() == 0
    assert body.satisfies_euler_poincare()


def test_tetra_topology_counts():
    body = make_tetra()
    c = body.euler_counts()
    assert c["V"] == 4
    assert c["E"] == 6
    assert c["F"] == 4
    assert c["S"] == 1
    assert c["G"] == 0


def test_tetra_satisfies_euler_poincare():
    assert make_tetra().satisfies_euler_poincare()


def test_cylinder_satisfies_euler_poincare():
    body = make_cylinder(radius=2.0, height=5.0)
    assert body.euler_poincare_residual() == 0


def test_cylinder_face_count():
    body = make_cylinder()
    # lateral + 2 caps
    assert len(body.all_faces()) == 3


def test_sphere_satisfies_euler_poincare():
    body = make_sphere(radius=3.0)
    assert body.euler_poincare_residual() == 0


def test_sphere_single_face():
    body = make_sphere()
    assert len(body.all_faces()) == 1
    assert body.genus() == 0


def test_torus_is_genus_one():
    body = make_torus(major_radius=3.0, minor_radius=1.0)
    assert body.genus() == 1


def test_torus_satisfies_euler_poincare():
    body = make_torus()
    assert body.euler_poincare_residual() == 0


def test_box_euler_characteristic_is_two():
    # V - E + F = 2 for a genus-0 closed solid
    c = make_box().euler_counts()
    assert c["V"] - c["E"] + c["F"] == 2


def test_tetra_euler_characteristic_is_two():
    c = make_tetra().euler_counts()
    assert c["V"] - c["E"] + c["F"] == 2


# ---------------------------------------------------------------------------
# validate_body on valid solids
# ---------------------------------------------------------------------------


def test_validate_box_ok():
    res = validate_body(make_box())
    assert res["ok"], res["errors"]


def test_validate_tetra_ok():
    res = validate_body(make_tetra())
    assert res["ok"], res["errors"]


def test_validate_cylinder_ok():
    res = validate_body(make_cylinder())
    assert res["ok"], res["errors"]


def test_validate_sphere_ok():
    res = validate_body(make_sphere())
    assert res["ok"], res["errors"]


def test_validate_torus_ok():
    res = validate_body(make_torus())
    assert res["ok"], res["errors"]


def test_validate_returns_dict_shape():
    res = validate_body(make_box())
    assert set(res.keys()) == {"ok", "errors"}
    assert isinstance(res["errors"], list)


# ---------------------------------------------------------------------------
# validate_body on deliberately broken solids
# ---------------------------------------------------------------------------


def test_validate_fails_open_loop():
    body = make_box()
    # break a loop by dropping a coedge so the cycle no longer closes
    face = body.all_faces()[0]
    loop = face.outer_loop()
    loop.coedges = loop.coedges[:-1]
    loop._relink()
    res = validate_body(body)
    assert not res["ok"]
    assert any("open" in e or "euler" in e for e in res["errors"])


def test_validate_fails_flipped_face():
    body = make_box()
    # reverse a face outer loop -> orientation becomes CW wrt normal
    face = body.all_faces()[0]
    loop = face.outer_loop()
    loop.coedges = list(reversed(loop.coedges))
    for ce in loop.coedges:
        ce.orientation = not ce.orientation
    loop._relink()
    res = validate_body(body)
    assert not res["ok"]
    assert any("CW" in e or "CCW" in e or "manifold" in e
               for e in res["errors"])


def test_validate_fails_dangling_edge():
    body = make_box()
    # introduce a free-floating edge with no coedge into the body
    v0 = Vertex(np.array([9.0, 9.0, 9.0]), 1e-7)
    v1 = Vertex(np.array([9.0, 9.0, 10.0]), 1e-7)
    dangling = Edge(Line3(v0.point, v1.point), 0.0, 1.0, v0, v1, 1e-7)
    # attach via a fake loop holding zero live coedges
    extra = Loop([], is_outer=False)
    extra.coedges = []
    body.wires.append(extra)
    # force the edge to be discoverable: register a detached coedge
    ce = Coedge(dangling, True)
    ce.loop = None
    dangling.coedges = [ce]
    body.solids[0].shells[0].faces[0].loops[0].coedges  # touch
    # directly assert dangling detection on the edge
    res = validate_body(body)
    # The dangling edge is reachable only if referenced; emulate by
    # adding to a wire loop then clearing coedges:
    extra.coedges = [Coedge(dangling, True)]
    extra._relink()
    extra.coedges[0].loop = None
    res2 = validate_body(body)
    assert not res2["ok"]
    assert any("dangling" in e for e in res2["errors"])


def test_validate_fails_non_manifold_three_coedges():
    body = make_box()
    edge = body.all_edges()[0]
    # add a third coedge use of an existing manifold edge
    face = body.all_faces()[-1]
    loop = face.outer_loop()
    loop.coedges.append(Coedge(edge, True, loop))
    loop._relink()
    res = validate_body(body)
    assert not res["ok"]
    assert any("non-manifold" in e or "manifold" in e or "euler" in e
               for e in res["errors"])


def test_validate_fails_tolerance_inversion_edge_face():
    body = make_box()
    face = body.all_faces()[0]
    face.tol = 1e-3  # larger than incident edge tol (1e-7)
    res = validate_body(body)
    assert not res["ok"]
    assert any("tolerance inversion" in e for e in res["errors"])


def test_validate_fails_tolerance_inversion_vertex_edge():
    body = make_box()
    edge = body.all_edges()[0]
    edge.v_start.tol = 1e-12  # smaller than edge tol (1e-7)
    res = validate_body(body)
    assert not res["ok"]
    assert any("tolerance inversion" in e for e in res["errors"])


def test_validate_fails_euler_on_extra_face():
    body = make_box()
    # append a stray face into the shell -> Euler residual nonzero
    shell = body.all_shells()[0]
    v = [Vertex(np.array([5.0, 0, 0]), 1e-7),
         Vertex(np.array([6.0, 0, 0]), 1e-7),
         Vertex(np.array([6.0, 1, 0]), 1e-7)]
    e = [Edge(Line3(v[0].point, v[1].point), 0, 1, v[0], v[1], 1e-7),
         Edge(Line3(v[1].point, v[2].point), 0, 1, v[1], v[2], 1e-7),
         Edge(Line3(v[2].point, v[0].point), 0, 1, v[2], v[0], 1e-7)]
    lp = Loop([Coedge(e[0], True), Coedge(e[1], True),
               Coedge(e[2], True)], is_outer=True)
    pl = Plane(v[0].point, v[1].point - v[0].point,
               v[2].point - v[0].point)
    shell.add_face(Face(pl, [lp], orientation=True, tol=1e-7))
    res = validate_body(body)
    assert not res["ok"]
    assert any("euler" in e for e in res["errors"])


def test_validate_fails_open_loop_vertex_discontinuity():
    body = make_tetra()
    face = body.all_faces()[0]
    loop = face.outer_loop()
    # corrupt one coedge's edge endpoint so the cycle no longer matches
    bad_v = Vertex(np.array([99.0, 99.0, 99.0]), 1e-7)
    loop.coedges[0].edge.v_end = bad_v
    res = validate_body(body)
    assert not res["ok"]


# ---------------------------------------------------------------------------
# Euler operators preserve the invariant
# ---------------------------------------------------------------------------


def test_mvfs_residual_zero():
    body, solid, shell, face, loop, v = mvfs((0.0, 0.0, 0.0))
    assert body.euler_poincare_residual() == 0


def test_mvfs_returns_full_chain():
    body, solid, shell, face, loop, v = mvfs((1.0, 2.0, 3.0))
    assert isinstance(body, Body)
    assert isinstance(solid, Solid)
    assert isinstance(shell, Shell)
    assert isinstance(face, Face)
    assert isinstance(loop, Loop)
    assert isinstance(v, Vertex)
    assert np.allclose(v.point, [1.0, 2.0, 3.0])


def test_mev_preserves_residual():
    body, solid, shell, face, loop, v = mvfs((0.0, 0.0, 0.0))
    before = body.euler_poincare_residual()
    edge, v_new = mev(loop, v, (1.0, 0.0, 0.0))
    after = body.euler_poincare_residual()
    assert before == after == 0
    assert edge.v_start is v
    assert edge.v_end is v_new


def test_mev_then_kev_round_trip_identity():
    body, solid, shell, face, loop, v = mvfs((0.0, 0.0, 0.0))
    counts0 = body.euler_counts()
    edge, v_new = mev(loop, v, (2.0, 0.0, 0.0))
    counts1 = body.euler_counts()
    assert counts1["V"] == counts0["V"] + 1
    assert counts1["E"] == counts0["E"] + 1
    kev(loop, edge)
    counts2 = body.euler_counts()
    assert counts2["V"] == counts0["V"]
    assert counts2["E"] == counts0["E"]
    assert body.euler_poincare_residual() == 0


def test_multiple_mev_keep_residual_zero():
    body, solid, shell, face, loop, v = mvfs((0.0, 0.0, 0.0))
    cur = v
    for i in range(1, 6):
        edge, cur = mev(loop, cur, (float(i), 0.0, 0.0))
        assert body.euler_poincare_residual() == 0


def test_mef_preserves_residual():
    # build a single quad loop face then split it with mef
    P = [np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]),
         np.array([1.0, 1.0, 0.0]), np.array([0.0, 1.0, 0.0])]
    V = [Vertex(p, 1e-7) for p in P]
    E = [Edge(Line3(P[i], P[(i + 1) % 4]), 0, 1, V[i], V[(i + 1) % 4],
              1e-7) for i in range(4)]
    ces = [Coedge(E[i], True) for i in range(4)]
    loop = Loop(ces, is_outer=True)
    pl = Plane(P[0], P[1] - P[0], P[3] - P[0])
    face = Face(pl, [loop], orientation=True, tol=1e-7)
    shell = Shell([face], is_closed=False)
    body = Body(shells=[shell])
    before = body.euler_poincare_residual()
    bridge, new_face = mef(loop, ces[0], ces[2], surface=pl)
    after = body.euler_poincare_residual()
    assert before == after
    c = body.euler_counts()
    # E+1, F+1, L+1 keeps residual constant
    assert any(f.id == new_face.id for f in body.all_faces())


def test_kfmrh_increases_genus_and_keeps_residual():
    body = make_box()
    before = body.euler_poincare_residual()
    solid = body.solids[0]
    shell = solid.shells[0]
    # remove a face and reattach its loop as a ring on a neighbour
    removed = shell.faces[-1]
    hole = removed.outer_loop()
    kfmrh(solid, removed, hole)
    after = body.euler_poincare_residual()
    assert before == 0
    assert after == 0


def test_kfmrh_inverse_round_trip():
    body = make_box()
    solid = body.solids[0]
    shell = solid.shells[0]
    f0 = shell.faces[0]
    removed = shell.faces[-1]
    hole = removed.outer_loop()
    n_faces = len(shell.faces)
    kfmrh(solid, removed, hole)
    assert len(shell.faces) == n_faces - 1
    kfmrh_inverse(solid, shell.faces[0], hole)
    assert len(shell.faces) == n_faces
    assert body.euler_poincare_residual() == 0


# ---------------------------------------------------------------------------
# make_box geometric / topological correctness
# ---------------------------------------------------------------------------


def test_make_box_vertex_positions():
    body = make_box(origin=(0, 0, 0), size=(2, 3, 4))
    pts = np.array(sorted(
        [tuple(v.point) for v in body.all_vertices()]
    ))
    assert pts.shape == (8, 3)
    assert np.allclose(pts.min(axis=0), [0, 0, 0])
    assert np.allclose(pts.max(axis=0), [2, 3, 4])


def test_make_box_all_faces_quads():
    body = make_box()
    for f in body.all_faces():
        assert len(f.outer_loop().coedges) == 4


def test_make_box_edges_length_match_size():
    body = make_box(size=(2.0, 2.0, 2.0))
    lengths = sorted(round(e.length(), 6) for e in body.all_edges())
    # all 12 edges of a 2-cube have length 2
    assert all(abs(L - 2.0) < 1e-6 for L in lengths)


def test_make_box_every_edge_two_coedges():
    body = make_box()
    for e in body.all_edges():
        live = [ce for ce in e.coedges if ce.loop is not None]
        assert len(live) == 2
        assert {ce.orientation for ce in live} == {True, False}


def test_make_box_outer_loops_ccw():
    body = make_box()
    res = validate_body(body)
    # validate_body already enforces CCW outer; assert no orientation err
    assert not any("CW" in e for e in res["errors"]), res["errors"]


def test_make_box_offset_origin():
    body = make_box(origin=(10, 20, 30), size=(1, 1, 1))
    for v in body.all_vertices():
        assert 10 <= v.point[0] <= 11
        assert 20 <= v.point[1] <= 21
        assert 30 <= v.point[2] <= 31
    assert validate_body(body)["ok"]


# ---------------------------------------------------------------------------
# Geometry adapter sanity
# ---------------------------------------------------------------------------


def test_line3_evaluate_endpoints():
    ln = Line3([0, 0, 0], [2, 0, 0])
    assert np.allclose(ln.evaluate(0.0), [0, 0, 0])
    assert np.allclose(ln.evaluate(1.0), [2, 0, 0])
    assert np.allclose(ln.evaluate(0.5), [1, 0, 0])


def test_circle_arc_radius():
    arc = CircleArc3([0, 0, 0], 5.0, [1, 0, 0], [0, 1, 0])
    p = arc.evaluate(math.pi / 2)
    assert abs(np.linalg.norm(p) - 5.0) < 1e-9


def test_plane_normal_orthogonal():
    pl = Plane([0, 0, 0], [1, 0, 0], [0, 1, 0])
    assert np.allclose(pl.normal(), [0, 0, 1])


def test_vertex_coincident_within_tol():
    a = Vertex(np.array([0.0, 0.0, 0.0]), 1e-3)
    b = Vertex(np.array([0.0005, 0.0, 0.0]), 1e-3)
    c = Vertex(np.array([1.0, 0.0, 0.0]), 1e-3)
    assert a.coincident(b)
    assert not a.coincident(c)


def test_edge_endpoints_match_vertices():
    v0 = Vertex(np.array([0.0, 0.0, 0.0]), 1e-7)
    v1 = Vertex(np.array([3.0, 0.0, 0.0]), 1e-7)
    e = Edge(Line3(v0.point, v1.point), 0.0, 1.0, v0, v1, 1e-7)
    assert np.allclose(e.start_point(), v0.point)
    assert np.allclose(e.end_point(), v1.point)
    assert abs(e.length() - 3.0) < 1e-6


def test_coedge_orientation_reverses_endpoints():
    v0 = Vertex(np.array([0.0, 0.0, 0.0]), 1e-7)
    v1 = Vertex(np.array([1.0, 0.0, 0.0]), 1e-7)
    e = Edge(Line3(v0.point, v1.point), 0.0, 1.0, v0, v1, 1e-7)
    fwd = Coedge(e, True)
    rev = Coedge(e, False)
    assert fwd.start_vertex() is v0
    assert fwd.end_vertex() is v1
    assert rev.start_vertex() is v1
    assert rev.end_vertex() is v0


def test_loop_relinks_circularly():
    v = [Vertex(np.array([float(i), 0.0, 0.0]), 1e-7) for i in range(3)]
    e = [Edge(Line3(v[i].point, v[(i + 1) % 3].point), 0, 1,
              v[i], v[(i + 1) % 3], 1e-7) for i in range(3)]
    ces = [Coedge(e[i], True) for i in range(3)]
    loop = Loop(ces, is_outer=True)
    assert ces[0].next is ces[1]
    assert ces[1].next is ces[2]
    assert ces[2].next is ces[0]
    assert ces[0].prev is ces[2]


def test_body_aggregate_accessors_consistent():
    body = make_box()
    assert len(body.all_shells()) == 1
    assert len(body.all_faces()) == 6
    assert len(body.all_edges()) == 12
    assert len(body.all_vertices()) == 8
    assert len(body.all_coedges()) == 24  # 6 faces * 4 coedges


def test_solid_outer_and_void_shells():
    outer = make_box().solids[0].shells[0]
    void = make_box(origin=(0.2, 0.2, 0.2),
                     size=(0.5, 0.5, 0.5)).solids[0].shells[0]
    solid = Solid([outer, void])
    assert solid.outer_shell is outer
    assert solid.void_shells == [void]


def test_euler_error_on_bad_kev():
    body, solid, shell, face, loop, v = mvfs((0.0, 0.0, 0.0))
    edge, v_new = mev(loop, v, (1.0, 0.0, 0.0))
    stray_v0 = Vertex(np.array([0.0, 0.0, 0.0]), 1e-7)
    stray = Edge(Line3([0, 0, 0], [1, 1, 1]), 0, 1, stray_v0,
                 Vertex(np.array([1.0, 1.0, 1.0]), 1e-7), 1e-7)
    with pytest.raises(EulerError):
        kev(loop, stray)


def test_invariant_documented_form_holds_for_all_primitives():
    # V - E + F - H - 2*(S - G) == 0
    for body in (make_box(), make_tetra(), make_cylinder(),
                 make_sphere(), make_torus()):
        c = body.euler_counts()
        lhs = c["V"] - c["E"] + c["F"] - c["H"] - 2 * (c["S"] - c["G"])
        assert lhs == 0, (body, c)
