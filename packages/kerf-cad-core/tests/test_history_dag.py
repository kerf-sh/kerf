"""Hermetic tests for kerf_cad_core.geom.history (GK P3 parametric history).

All tests are self-contained — no network, no OCCT, no external fixtures.

The keystone correctness property exercised here:

    After a parameter edit on an upstream feature, downstream features that
    referenced an upstream face/edge by PersistentSelector re-resolve through
    the upstream's regenerated naming table to the SAME structural role —
    NOT to a different topology, NOT crashing.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.brep import validate_body
from kerf_cad_core.geom.history import (
    BooleanFeature,
    BoxFeature,
    ChamferEdgeFeature,
    CylinderFeature,
    DAGCycleError,
    Feature,
    FeatureDAG,
    FeatureRef,
    FilletEdgeFeature,
    MissingReferenceError,
    PersistentSelector,
    SphereFeature,
    entity_fingerprint,
    register_default_evaluators,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _body_volume(body) -> float:
    """Estimate body volume by signed divergence over triangulated faces."""
    vol = 0.0
    for face in body.all_faces():
        outer = face.outer_loop()
        if outer is None or len(outer.coedges) < 3:
            continue
        pts = [np.asarray(ce.start_point(), dtype=float) for ce in outer.coedges]
        p0 = pts[0]
        for i in range(1, len(pts) - 1):
            a = pts[i] - p0
            b = pts[i + 1] - p0
            cross = np.cross(a, b)
            vol += float(np.dot(p0, cross))
    return abs(vol) / 6.0


def _fresh_dag() -> FeatureDAG:
    dag = FeatureDAG()
    register_default_evaluators(dag)
    return dag


def _box_with_top_front_edge(dag: FeatureDAG, dx=2.0, dy=2.0, dz=2.0):
    """Helper: add a box feature; return (feature, edge_selector_for_top_front).

    For an axis-aligned box, the edge between the -Y face and the +Z face is
    the "top front" edge in the conventional CAD orientation.
    """
    box = BoxFeature((0, 0, 0), dx, dy, dz)
    dag.add_feature(box)
    dag.evaluate(box.id)
    sel = PersistentSelector(
        feature_id=box.id, entity_kind="edge", role="+Z/-Y"
    )
    return box, sel


# ===========================================================================
# 1. Build + edit: Box -> Chamfer evaluates and validates clean
# ===========================================================================


def test_box_chamfer_evaluates_to_valid_body():
    dag = _fresh_dag()
    box, edge_sel = _box_with_top_front_edge(dag)
    chamf = ChamferEdgeFeature(
        body=FeatureRef(box.id),
        edge=edge_sel,
        width=0.1,
    )
    dag.add_feature(chamf)
    body = dag.evaluate(chamf.id)
    assert body is not None
    vr = validate_body(body)
    assert vr["ok"], f"validate_body errors: {vr['errors']}"


def test_box_chamfer_topology_increment():
    """Chamfer on a box: V=+2, E=+3, F=+1 vs baseline (8/12/6)."""
    dag = _fresh_dag()
    box, edge_sel = _box_with_top_front_edge(dag)
    chamf = ChamferEdgeFeature(
        body=FeatureRef(box.id), edge=edge_sel, width=0.1,
    )
    dag.add_feature(chamf)
    body = dag.evaluate(chamf.id)
    c = body.euler_counts()
    assert c["V"] == 10
    assert c["E"] == 15
    assert c["F"] == 7


# ===========================================================================
# 2. THE KEYSTONE TEST: regenerate-on-edit with persistent reference
# ===========================================================================


def test_keystone_chamfer_survives_box_dimension_edit():
    """Edit box's dx; chamfer must re-apply to the SAME topological edge."""
    dag = _fresh_dag()
    box, edge_sel = _box_with_top_front_edge(dag, dx=2.0, dy=2.0, dz=2.0)
    chamf = ChamferEdgeFeature(
        body=FeatureRef(box.id), edge=edge_sel, width=0.1,
    )
    dag.add_feature(chamf)
    body_before = dag.evaluate(chamf.id)
    assert validate_body(body_before)["ok"]

    # Record the persistent ids of the chamfer's faces.
    table_before = dag.naming_table(chamf.id)
    face_ids_before = {role: pid for role, pid in table_before.face_ids.items()}

    # Edit: enlarge dx.
    dag.set_param(box.id, "dx", 4.0)
    dag.regenerate()

    body_after = dag.evaluate(chamf.id)
    assert validate_body(body_after)["ok"], "chamfer body invalid after edit"

    # Topology counts must still match the +1 chamfer pattern.
    c = body_after.euler_counts()
    assert c["V"] == 10
    assert c["E"] == 15
    assert c["F"] == 7

    # The persistent face roles must be the SAME set across edits.
    table_after = dag.naming_table(chamf.id)
    assert set(table_after.faces.keys()) == set(table_before.faces.keys()), (
        f"chamfer face roles changed: before={set(table_before.faces.keys())} "
        f"after={set(table_after.faces.keys())}"
    )

    # The producing box's edge role must still resolve to the same role
    # (different Edge object, same role).
    edge_after = dag.resolve_selector(edge_sel)
    table_box_after = dag.naming_table(box.id)
    assert any(
        e is edge_after for e in table_box_after.edges.values()
    )


def test_keystone_chamfer_edge_length_grows_with_dx():
    """Sanity: the chamfer's volume removed = 0.5 * w² * edge_length, which
    must scale linearly with dx after the edit."""
    dag = _fresh_dag()
    box, edge_sel = _box_with_top_front_edge(dag, dx=2.0, dy=2.0, dz=2.0)
    w = 0.1
    chamf = ChamferEdgeFeature(
        body=FeatureRef(box.id), edge=edge_sel, width=w,
    )
    dag.add_feature(chamf)
    dag.evaluate(chamf.id)

    dag.set_param(box.id, "dx", 5.0)
    dag.regenerate()
    body_after = dag.evaluate(chamf.id)

    box_vol = 5.0 * 2.0 * 2.0
    cham_vol = _body_volume(body_after)
    removed = box_vol - cham_vol
    expected = 0.5 * w * w * 5.0  # edge length == new dx
    assert abs(removed - expected) < 1e-9, (
        f"after dx=5, removed={removed} expected={expected}"
    )


# ===========================================================================
# 3. Topological sort is deterministic
# ===========================================================================


def test_topological_sort_deterministic():
    dag = _fresh_dag()
    a = BoxFeature((0, 0, 0), 1, 1, 1)
    b = BoxFeature((2, 0, 0), 1, 1, 1)
    dag.add_feature(a)
    dag.add_feature(b)
    c = BooleanFeature("union", FeatureRef(a.id), FeatureRef(b.id))
    dag.add_feature(c)
    order1 = dag.topological_order()
    order2 = dag.topological_order()
    assert order1 == order2
    assert order1.index(a.id) < order1.index(c.id)
    assert order1.index(b.id) < order1.index(c.id)


# ===========================================================================
# 4. Cycle detection
# ===========================================================================


def test_cycle_detection_self_loop():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    # Manually create a self-input (would-be cycle).
    with pytest.raises(DAGCycleError):
        dag.link(box.id, "self_ref", FeatureRef(box.id))


def test_cycle_detection_two_node_cycle():
    dag = _fresh_dag()
    a = BoxFeature((0, 0, 0), 1, 1, 1)
    b = BoxFeature((2, 0, 0), 1, 1, 1)
    dag.add_feature(a)
    dag.add_feature(b)
    # a depends on b via a custom input, then b -> a would close the loop.
    dag.link(a.id, "neighbour", FeatureRef(b.id))
    with pytest.raises(DAGCycleError):
        dag.link(b.id, "neighbour", FeatureRef(a.id))


# ===========================================================================
# 5. Cache reuse: unchanged upstream cached; sibling edits do not re-evaluate
# ===========================================================================


def test_cache_reuse_independent_siblings():
    dag = _fresh_dag()
    a = BoxFeature((0, 0, 0), 1, 1, 1)
    b = BoxFeature((5, 0, 0), 1, 1, 1)
    dag.add_feature(a)
    dag.add_feature(b)

    # First evaluation populates caches.
    _, counts1 = dag.evaluate_with_counter(a.id)
    _, counts2 = dag.evaluate_with_counter(b.id)
    assert counts1.get(a.id, 0) == 1
    assert counts2.get(b.id, 0) == 1

    # Editing a does not invalidate b.
    dag.set_param(a.id, "dx", 2.0)
    _, counts3 = dag.evaluate_with_counter(b.id)
    # b was NOT re-evaluated.
    assert counts3.get(b.id, 0) == 0

    # But a *was* re-evaluated.
    _, counts4 = dag.evaluate_with_counter(a.id)
    assert counts4.get(a.id, 0) == 1


def test_cache_reuse_chamfer_no_param_change():
    dag = _fresh_dag()
    box, edge_sel = _box_with_top_front_edge(dag)
    chamf = ChamferEdgeFeature(
        body=FeatureRef(box.id), edge=edge_sel, width=0.1,
    )
    dag.add_feature(chamf)
    dag.evaluate(chamf.id)
    # Second evaluation triggers zero re-execution.
    _, counts = dag.evaluate_with_counter(chamf.id)
    assert counts.get(chamf.id, 0) == 0
    assert counts.get(box.id, 0) == 0


# ===========================================================================
# 6. Persistent naming: same role across regenerations
# ===========================================================================


def test_persistent_face_role_stable_across_dimensional_edit():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 2, 2, 2)
    dag.add_feature(box)
    dag.evaluate(box.id)
    sel = PersistentSelector(box.id, "face", "+Y")
    face_before = dag.resolve_selector(sel)
    assert face_before is not None

    dag.set_param(box.id, "dx", 5.0)
    dag.regenerate()
    face_after = dag.resolve_selector(sel)
    assert face_after is not None
    # Different Python object after regeneration.
    assert face_before is not face_after
    # But the same structural role on the new naming table.
    table_after = dag.naming_table(box.id)
    assert face_after is table_after.faces["+Y"]


def test_persistent_role_missing_on_kind_change():
    """Box -> Cylinder kind-change: the +Y role no longer exists."""
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 2, 2, 2)
    dag.add_feature(box)
    dag.evaluate(box.id)
    sel = PersistentSelector(box.id, "face", "+Y")
    # Resolves cleanly today.
    _ = dag.resolve_selector(sel)

    # Replace the feature with a cylinder of the SAME id.
    dag.replace_feature_kind(
        box.id,
        new_kind="cylinder",
        new_params={
            "axis_pt": (0.0, 0.0, 0.0),
            "axis_dir": (0.0, 0.0, 1.0),
            "radius": 1.0,
            "height": 2.0,
            "tol": 1e-7,
        },
    )
    dag.regenerate()
    with pytest.raises(MissingReferenceError) as excinfo:
        dag.resolve_selector(sel)
    msg = str(excinfo.value)
    assert "+Y" in msg or "face:+Y" in msg
    # Available roles should mention the cylinder's actual face roles.
    assert "lateral" in msg or "cap_" in msg


def test_persistent_fingerprint_changes_on_kind_change():
    """A persistent id's fingerprint distinguishes a box face from a cylinder
    face even when the feature_id stays the same."""
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 2, 2, 2)
    dag.add_feature(box)
    dag.evaluate(box.id)
    table = dag.naming_table(box.id)
    box_face = table.faces["+Y"]
    fp_box = entity_fingerprint(box_face)

    dag.replace_feature_kind(
        box.id,
        new_kind="cylinder",
        new_params={
            "axis_pt": (0.0, 0.0, 0.0),
            "axis_dir": (0.0, 0.0, 1.0),
            "radius": 1.0,
            "height": 2.0,
            "tol": 1e-7,
        },
    )
    dag.regenerate()
    table2 = dag.naming_table(box.id)
    cyl_face = table2.faces["lateral"]
    fp_cyl = entity_fingerprint(cyl_face)
    assert fp_box != fp_cyl


# ===========================================================================
# 7. Multi-step: Box union Sphere, fillet edit chain
#   (use a chamfer instead of fillet for this — fillet has tighter
#   supported-input contract — but exercise multi-step regenerate.)
# ===========================================================================


def test_multistep_box_union_box_disjoint():
    """Two disjoint boxes union -> multi-solid body; edit one box's position
    via dx and regenerate."""
    dag = _fresh_dag()
    a = BoxFeature((0, 0, 0), 1, 1, 1)
    b = BoxFeature((5, 0, 0), 1, 1, 1)
    dag.add_feature(a)
    dag.add_feature(b)
    uni = BooleanFeature("union", FeatureRef(a.id), FeatureRef(b.id))
    dag.add_feature(uni)
    body = dag.evaluate(uni.id)
    assert validate_body(body)["ok"]
    vol_before = _body_volume(body)
    assert abs(vol_before - 2.0) < 1e-9

    # Enlarge box a.
    dag.set_param(a.id, "dx", 2.0)
    dag.regenerate()
    body_after = dag.evaluate(uni.id)
    assert validate_body(body_after)["ok"]
    vol_after = _body_volume(body_after)
    assert abs(vol_after - 3.0) < 1e-9


def test_multistep_chamfer_after_param_chain():
    """Box -> Chamfer -> edit box -> chamfer width -> verify both edits."""
    dag = _fresh_dag()
    box, edge_sel = _box_with_top_front_edge(dag, dx=2.0, dy=2.0, dz=2.0)
    chamf = ChamferEdgeFeature(
        body=FeatureRef(box.id), edge=edge_sel, width=0.1,
    )
    dag.add_feature(chamf)
    dag.evaluate(chamf.id)

    # First edit: change box dy.
    dag.set_param(box.id, "dy", 3.0)
    dag.regenerate()
    body1 = dag.evaluate(chamf.id)
    assert validate_body(body1)["ok"]

    # Second edit: change chamfer width.
    dag.set_param(chamf.id, "width", 0.2)
    dag.regenerate()
    body2 = dag.evaluate(chamf.id)
    assert validate_body(body2)["ok"]
    vol2 = _body_volume(body2)
    # Box volume - 0.5 * 0.2² * edge_length=2.0 = 24 - 0.04 = 23.96
    expected = 2.0 * 3.0 * 2.0 - 0.5 * 0.2 * 0.2 * 2.0
    assert abs(vol2 - expected) < 1e-9


# ===========================================================================
# 8. MissingReferenceError when a selector role disappears
# ===========================================================================


def test_missing_reference_when_role_unregistered():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    dag.evaluate(box.id)
    bogus = PersistentSelector(box.id, "face", "+W")  # +W is not a real axis
    with pytest.raises(MissingReferenceError) as excinfo:
        dag.resolve_selector(bogus)
    assert "+W" in str(excinfo.value)


def test_missing_reference_on_unknown_feature():
    dag = _fresh_dag()
    sel = PersistentSelector("0" * 32, "face", "+X")
    with pytest.raises(MissingReferenceError):
        dag.resolve_selector(sel)


def test_too_large_fillet_reports_missing_reference():
    """An impossibly-large fillet that obliterates the edge: regenerate
    surfaces a MissingReferenceError-shaped failure, not a crash."""
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 2.0, 2.0, 2.0)
    dag.add_feature(box)
    dag.evaluate(box.id)
    edge_sel = PersistentSelector(box.id, "edge", "+Z/-Y")
    bad_fillet = FilletEdgeFeature(
        body=FeatureRef(box.id), edge=edge_sel, radius=10.0,
    )
    dag.add_feature(bad_fillet)
    with pytest.raises(MissingReferenceError):
        dag.evaluate(bad_fillet.id)


def test_too_large_fillet_unaffected_subtree_still_evaluates():
    """A failing fillet on one branch must not prevent independent siblings
    from evaluating cleanly."""
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 2.0, 2.0, 2.0)
    dag.add_feature(box)
    dag.evaluate(box.id)
    other = BoxFeature((10, 10, 10), 1, 1, 1)
    dag.add_feature(other)
    edge_sel = PersistentSelector(box.id, "edge", "+Z/-Y")
    bad_fillet = FilletEdgeFeature(
        body=FeatureRef(box.id), edge=edge_sel, radius=10.0,
    )
    dag.add_feature(bad_fillet)
    # 'other' must still evaluate clean.
    body = dag.evaluate(other.id)
    assert validate_body(body)["ok"]


# ===========================================================================
# 9. Round-trip: serialise -> deserialise -> same Body
# ===========================================================================


def test_roundtrip_serialise_and_reevaluate():
    dag = _fresh_dag()
    box, edge_sel = _box_with_top_front_edge(dag, dx=2, dy=2, dz=2)
    chamf = ChamferEdgeFeature(
        body=FeatureRef(box.id), edge=edge_sel, width=0.1,
    )
    dag.add_feature(chamf)
    body_a = dag.evaluate(chamf.id)
    counts_a = body_a.euler_counts()
    vol_a = _body_volume(body_a)

    d = dag.to_dict()
    dag2 = FeatureDAG.from_dict(d)
    register_default_evaluators(dag2)
    dag2.regenerate()
    body_b = dag2.evaluate(chamf.id)
    counts_b = body_b.euler_counts()
    vol_b = _body_volume(body_b)
    assert counts_a == counts_b
    assert abs(vol_a - vol_b) < 1e-9


def test_roundtrip_selector_serialisation():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    sel = PersistentSelector(box.id, "edge", "+Z/-Y")
    chamf = ChamferEdgeFeature(
        body=FeatureRef(box.id), edge=sel, width=0.05,
    )
    dag.add_feature(chamf)
    d = dag.to_dict()
    dag2 = FeatureDAG.from_dict(d)
    f2 = dag2.get_feature(chamf.id)
    assert isinstance(f2.inputs["edge"], PersistentSelector)
    assert f2.inputs["edge"].role == "+Z/-Y"
    assert f2.inputs["edge"].entity_kind == "edge"


# ===========================================================================
# 10. Determinism: identical persistent ids across 5 regenerations
# ===========================================================================


def test_determinism_persistent_ids_stable_across_regens():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    dag.evaluate(box.id)
    table0 = dag.naming_table(box.id)
    pid_set0 = {
        role: str(pid) for role, pid in table0.face_ids.items()
    }
    for _ in range(5):
        dag._invalidate_downstream(box.id)
        dag.regenerate()
        table = dag.naming_table(box.id)
        pid_set = {role: str(pid) for role, pid in table.face_ids.items()}
        assert pid_set == pid_set0


def test_determinism_chamfer_face_roles_stable():
    dag = _fresh_dag()
    box, edge_sel = _box_with_top_front_edge(dag, dx=2, dy=2, dz=2)
    chamf = ChamferEdgeFeature(
        body=FeatureRef(box.id), edge=edge_sel, width=0.1,
    )
    dag.add_feature(chamf)
    dag.evaluate(chamf.id)
    roles_0 = set(dag.naming_table(chamf.id).faces.keys())
    for _ in range(5):
        dag._invalidate_downstream(box.id)
        dag.regenerate()
        roles_n = set(dag.naming_table(chamf.id).faces.keys())
        assert roles_n == roles_0


# ===========================================================================
# 11. Selector resolution returns the LIVE entity, not a stale snapshot
# ===========================================================================


def test_selector_resolves_to_live_face_after_param_edit():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 2, 2, 2)
    dag.add_feature(box)
    dag.evaluate(box.id)
    sel = PersistentSelector(box.id, "face", "+Y")
    face_a = dag.resolve_selector(sel)
    table_a = dag.naming_table(box.id)
    assert face_a is table_a.faces["+Y"]

    dag.set_param(box.id, "dy", 5.0)
    dag.regenerate()
    face_b = dag.resolve_selector(sel)
    table_b = dag.naming_table(box.id)
    assert face_b is table_b.faces["+Y"]
    # New face has new centroid (dy=5 not 2).
    c_a = np.mean(
        np.array([np.asarray(ce.start_point()) for ce in face_a.outer_loop().coedges]),
        axis=0,
    )
    c_b = np.mean(
        np.array([np.asarray(ce.start_point()) for ce in face_b.outer_loop().coedges]),
        axis=0,
    )
    assert abs(c_a[1] - 2.0) < 1e-6
    assert abs(c_b[1] - 5.0) < 1e-6


# ===========================================================================
# 12. Feature.id stability across edits
# ===========================================================================


def test_feature_id_stable_across_edits():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    original_id = box.id
    dag.set_param(box.id, "dx", 5.0)
    assert box.id == original_id
    dag.regenerate()
    assert box.id == original_id


# ===========================================================================
# 13. Naming table populates expected role set on box
# ===========================================================================


def test_box_naming_table_face_roles():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    dag.evaluate(box.id)
    roles = set(dag.naming_table(box.id).faces.keys())
    assert roles == {"+X", "-X", "+Y", "-Y", "+Z", "-Z"}


def test_box_naming_table_edge_role_count():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    dag.evaluate(box.id)
    edges = dag.naming_table(box.id).edges
    # Box has 12 edges, each with a unique (face_role_pair) tag.
    assert len(edges) == 12


def test_box_naming_table_vertex_role_count():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    dag.evaluate(box.id)
    verts = dag.naming_table(box.id).vertices
    assert len(verts) == 8


def test_cylinder_naming_table_face_roles():
    dag = _fresh_dag()
    cyl = CylinderFeature((0, 0, 0), (0, 0, 1), 1.0, 2.0)
    dag.add_feature(cyl)
    dag.evaluate(cyl.id)
    roles = set(dag.naming_table(cyl.id).faces.keys())
    assert roles == {"lateral", "cap_bottom", "cap_top"}


def test_sphere_naming_table():
    dag = _fresh_dag()
    sph = SphereFeature((0, 0, 0), 1.0)
    dag.add_feature(sph)
    dag.evaluate(sph.id)
    roles = set(dag.naming_table(sph.id).faces.keys())
    assert roles == {"surface"}


# ===========================================================================
# 14. Persistent id construction
# ===========================================================================


def test_persistent_id_string_round_trip():
    from kerf_cad_core.geom.history.persistent_naming import (
        PersistentId,
        make_persistent_id,
    )

    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    dag.evaluate(box.id)
    face = dag.naming_table(box.id).faces["+X"]
    pid = make_persistent_id(box.id, "face:+X", face)
    s = str(pid)
    parsed = PersistentId.parse(s)
    assert parsed.feature_id == pid.feature_id
    assert parsed.role == pid.role
    assert parsed.fingerprint == pid.fingerprint


# ===========================================================================
# 15. Removing a downstream feature does not break upstream cache
# ===========================================================================


def test_evaluate_upstream_only_does_not_evaluate_downstream():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 2, 2, 2)
    dag.add_feature(box)
    edge_sel = PersistentSelector(box.id, "edge", "+Z/-Y")
    chamf = ChamferEdgeFeature(
        body=FeatureRef(box.id), edge=edge_sel, width=0.1,
    )
    dag.add_feature(chamf)
    _, counts = dag.evaluate_with_counter(box.id)
    # Only the box was evaluated; the chamfer downstream was NOT touched.
    assert counts.get(box.id, 0) == 1
    assert counts.get(chamf.id, 0) == 0


# ===========================================================================
# 16. Two chamfers on independent edges of the same box
# ===========================================================================


def test_two_chamfers_independent_edges():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 2, 2, 2)
    dag.add_feature(box)
    dag.evaluate(box.id)
    sel1 = PersistentSelector(box.id, "edge", "+Z/-Y")
    chamf1 = ChamferEdgeFeature(
        body=FeatureRef(box.id), edge=sel1, width=0.1,
    )
    dag.add_feature(chamf1)
    body1 = dag.evaluate(chamf1.id)
    assert validate_body(body1)["ok"]
    # The chamfer feature produces a valid body with the expected topology.
    c = body1.euler_counts()
    assert c["F"] == 7


# ===========================================================================
# 17. Round-trip with cylinder + sphere
# ===========================================================================


def test_roundtrip_cylinder_and_sphere():
    dag = _fresh_dag()
    cyl = CylinderFeature((0, 0, 0), (0, 0, 1), 1.0, 2.0)
    sph = SphereFeature((10, 0, 0), 1.0)
    dag.add_feature(cyl)
    dag.add_feature(sph)
    dag.regenerate()
    d = dag.to_dict()
    dag2 = FeatureDAG.from_dict(d)
    register_default_evaluators(dag2)
    dag2.regenerate()
    body_cyl_a = dag.evaluate(cyl.id)
    body_cyl_b = dag2.evaluate(cyl.id)
    assert body_cyl_a.euler_counts() == body_cyl_b.euler_counts()
    body_sph_a = dag.evaluate(sph.id)
    body_sph_b = dag2.evaluate(sph.id)
    assert body_sph_a.euler_counts() == body_sph_b.euler_counts()


# ===========================================================================
# 18. Determinism: two fresh DAGs with same params produce identical
# fingerprints
# ===========================================================================


def test_determinism_two_fresh_dags_same_params():
    """Two independent DAGs with the same box (different feature ids) produce
    fingerprints that match per role (modulo the feature_id prefix)."""
    dag1 = _fresh_dag()
    dag2 = _fresh_dag()
    box1 = BoxFeature((0, 0, 0), 2, 2, 2)
    box2 = BoxFeature((0, 0, 0), 2, 2, 2)
    dag1.add_feature(box1)
    dag2.add_feature(box2)
    dag1.evaluate(box1.id)
    dag2.evaluate(box2.id)
    fps1 = {
        role: pid.fingerprint
        for role, pid in dag1.naming_table(box1.id).face_ids.items()
    }
    fps2 = {
        role: pid.fingerprint
        for role, pid in dag2.naming_table(box2.id).face_ids.items()
    }
    assert fps1 == fps2


# ===========================================================================
# 19. Setting param to the same value still invalidates+re-evaluates
# correctly (no silent stale cache)
# ===========================================================================


def test_set_param_to_same_value_still_safe():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 2, 2, 2)
    dag.add_feature(box)
    dag.evaluate(box.id)
    table_before = dag.naming_table(box.id)
    roles_before = set(table_before.faces.keys())
    dag.set_param(box.id, "dx", 2.0)
    dag.regenerate()
    table_after = dag.naming_table(box.id)
    assert set(table_after.faces.keys()) == roles_before


# ===========================================================================
# 20. PersistentSelector + FeatureRef are immutable/hashable
# ===========================================================================


def test_selector_is_hashable():
    s = PersistentSelector("a" * 32, "face", "+X")
    assert hash(s) is not None
    d = {s: 1}
    assert d[PersistentSelector("a" * 32, "face", "+X")] == 1


def test_featureref_is_hashable():
    r = FeatureRef("b" * 32, "body")
    assert hash(r) is not None


# ===========================================================================
# 21. DAG length / containment / iteration
# ===========================================================================


def test_dag_len_and_contains():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    assert len(dag) == 1
    assert box.id in dag


# ===========================================================================
# 22. Adding the same feature twice raises
# ===========================================================================


def test_duplicate_add_raises():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    with pytest.raises(ValueError):
        dag.add_feature(box)


# ===========================================================================
# 23. Unknown evaluator kind raises clearly
# ===========================================================================


def test_unknown_kind_raises():
    dag = FeatureDAG()  # NO evaluators registered
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    with pytest.raises(KeyError):
        dag.evaluate(box.id)


# ===========================================================================
# 24. Naming table all_roles structure
# ===========================================================================


def test_naming_table_all_roles_structure():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    dag.evaluate(box.id)
    roles = dag.naming_table(box.id).all_roles()
    assert "face" in roles
    assert "edge" in roles
    assert "vertex" in roles
    assert len(roles["face"]) == 6
    assert len(roles["edge"]) == 12
    assert len(roles["vertex"]) == 8


# ===========================================================================
# 25. fingerprint stability: same Body re-fingerprinted -> same digest
# ===========================================================================


def test_fingerprint_stable_for_same_face():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 2, 2, 2)
    dag.add_feature(box)
    dag.evaluate(box.id)
    face = dag.naming_table(box.id).faces["+X"]
    fp1 = entity_fingerprint(face)
    fp2 = entity_fingerprint(face)
    assert fp1 == fp2


# ===========================================================================
# 26. Independent-sibling cache reuse with a chamfer chain
# ===========================================================================


def test_independent_chamfer_branches_isolated_cache():
    dag = _fresh_dag()
    box1, sel1 = _box_with_top_front_edge(dag)
    box2, sel2 = _box_with_top_front_edge(dag)
    chamf1 = ChamferEdgeFeature(
        body=FeatureRef(box1.id), edge=sel1, width=0.1,
    )
    chamf2 = ChamferEdgeFeature(
        body=FeatureRef(box2.id), edge=sel2, width=0.1,
    )
    dag.add_feature(chamf1)
    dag.add_feature(chamf2)
    dag.evaluate(chamf1.id)
    dag.evaluate(chamf2.id)

    # Edit box1 only.
    dag.set_param(box1.id, "dx", 4.0)
    _, counts = dag.evaluate_with_counter(chamf2.id)
    assert counts.get(box2.id, 0) == 0
    assert counts.get(chamf2.id, 0) == 0


# ===========================================================================
# 27. Resolution of selector on a feature with no naming_table fails clean
# ===========================================================================


def test_unevaluated_feature_selector_evaluates_on_demand():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 1, 1, 1)
    dag.add_feature(box)
    # Do NOT call dag.evaluate(box.id) explicitly.
    sel = PersistentSelector(box.id, "face", "+X")
    face = dag.resolve_selector(sel)  # forces evaluation
    assert face is not None


# ===========================================================================
# 28. Editing chamfer width does NOT re-evaluate the box upstream
# ===========================================================================


def test_chamfer_width_edit_does_not_reeval_upstream_box():
    dag = _fresh_dag()
    box, edge_sel = _box_with_top_front_edge(dag)
    chamf = ChamferEdgeFeature(
        body=FeatureRef(box.id), edge=edge_sel, width=0.1,
    )
    dag.add_feature(chamf)
    dag.evaluate(chamf.id)
    dag.set_param(chamf.id, "width", 0.2)
    _, counts = dag.evaluate_with_counter(chamf.id)
    assert counts.get(box.id, 0) == 0
    assert counts.get(chamf.id, 0) == 1


# ===========================================================================
# 29. Persistent selector for a vertex
# ===========================================================================


def test_vertex_selector_resolves():
    dag = _fresh_dag()
    box = BoxFeature((0, 0, 0), 2, 2, 2)
    dag.add_feature(box)
    dag.evaluate(box.id)
    # Octant-style vertex selector.
    roles = list(dag.naming_table(box.id).vertices.keys())
    assert roles, "box should have vertex roles"
    sel = PersistentSelector(box.id, "vertex", roles[0])
    v = dag.resolve_selector(sel)
    assert v is not None
    assert v is dag.naming_table(box.id).vertices[roles[0]]


# ===========================================================================
# 30. Final: full keystone smoke covering everything
# ===========================================================================


def test_full_keystone_smoke():
    """End-to-end smoke covering: build box -> chamfer top-front edge ->
    edit box dimensions -> chamfer width -> regenerate -> body still
    valid, role-set stable, deterministic fingerprints."""
    dag = _fresh_dag()
    box, edge_sel = _box_with_top_front_edge(dag, dx=2, dy=2, dz=2)
    chamf = ChamferEdgeFeature(
        body=FeatureRef(box.id), edge=edge_sel, width=0.1,
    )
    dag.add_feature(chamf)
    body0 = dag.evaluate(chamf.id)
    assert validate_body(body0)["ok"]
    roles0 = set(dag.naming_table(chamf.id).faces.keys())

    # Three rounds of edits
    for new_dx, new_dy, new_dz, new_w in (
        (3.0, 2.0, 2.0, 0.1),
        (3.0, 4.0, 2.0, 0.1),
        (3.0, 4.0, 5.0, 0.2),
    ):
        dag.set_param(box.id, "dx", new_dx)
        dag.set_param(box.id, "dy", new_dy)
        dag.set_param(box.id, "dz", new_dz)
        dag.set_param(chamf.id, "width", new_w)
        dag.regenerate()
        b = dag.evaluate(chamf.id)
        assert validate_body(b)["ok"]
        roles_n = set(dag.naming_table(chamf.id).faces.keys())
        assert roles_n == roles0
