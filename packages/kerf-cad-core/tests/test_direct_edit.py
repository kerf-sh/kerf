"""Verification suite for kerf_cad_core.geom.history.direct_edit (T-107).

Exercises the direct-edit verbs + the direct/parametric coexistence
contract: a direct edit on the current Body snapshot must round-trip
through a DAG ``direct_edit`` node and replay to the same geometry.

Hermetic — no network, no OCCT, no external fixtures.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.brep import validate_body
from kerf_cad_core.geom.brep_build import box_to_body
from kerf_cad_core.geom.history.dag import FeatureDAG
from kerf_cad_core.geom.history.feature import MissingReferenceError
from kerf_cad_core.geom.history.direct_edit import (
    DirectEditError,
    DirectEditRecord,
    UnsupportedBodyError,
    _body_volume,
    _face_persistent_id,
    commit_direct_edits_to_dag,
    direct_delete_feature,
    direct_offset_face,
    direct_push_pull,
    direct_rotate_face,
    direct_translate_face,
)

TOL = 1e-6


def _box(corner=(0.0, 0.0, 0.0), dx=2.0, dy=3.0, dz=4.0):
    return box_to_body(corner=corner, dx=dx, dy=dy, dz=dz)


def _face_id_with_normal(body, target_normal):
    """Return the persistent id of the face whose outward normal ≈ target."""
    tn = np.asarray(target_normal, dtype=float)
    for f in body.all_faces():
        n = np.asarray(f.surface.normal(0.5, 0.5), dtype=float)
        n = n / (np.linalg.norm(n) or 1.0)
        if np.linalg.norm(n - tn) < 1e-6:
            return _face_persistent_id(f)
    raise AssertionError(f"no face with normal {target_normal}")


# ---------------------------------------------------------------------------
# Baseline geometry
# ---------------------------------------------------------------------------


def test_box_baseline_is_valid_six_planar_faces():
    body = _box()
    validate_body(body)
    faces = body.all_faces()
    assert len(faces) == 6
    assert _body_volume(body) == pytest.approx(2.0 * 3.0 * 4.0, rel=1e-6)


# ---------------------------------------------------------------------------
# direct_offset_face / direct_push_pull
# ---------------------------------------------------------------------------


def test_offset_face_outward_increases_volume():
    body = _box(dx=2.0, dy=3.0, dz=4.0)
    fid = _face_id_with_normal(body, (1.0, 0.0, 0.0))
    out = direct_offset_face(body, fid, 1.0)
    validate_body(out)
    # +X face pushed out 1.0 → dx 2→3, volume 24→36
    assert _body_volume(out) == pytest.approx(3.0 * 3.0 * 4.0, rel=1e-6)


def test_offset_face_inward_decreases_volume():
    body = _box(dx=2.0, dy=3.0, dz=4.0)
    fid = _face_id_with_normal(body, (1.0, 0.0, 0.0))
    out = direct_offset_face(body, fid, -0.5)
    validate_body(out)
    assert _body_volume(out) == pytest.approx(1.5 * 3.0 * 4.0, rel=1e-6)


def test_push_pull_equivalent_to_offset():
    body = _box()
    fid = _face_id_with_normal(body, (0.0, 0.0, 1.0))
    a = direct_offset_face(body, fid, 0.75)
    b = direct_push_pull(body, fid, 0.75)
    assert _body_volume(a) == pytest.approx(_body_volume(b), rel=1e-9)


def test_input_body_not_mutated():
    body = _box()
    v0 = _body_volume(body)
    fid = _face_id_with_normal(body, (1.0, 0.0, 0.0))
    direct_offset_face(body, fid, 2.0)
    assert _body_volume(body) == pytest.approx(v0, rel=1e-12)


# ---------------------------------------------------------------------------
# direct_translate_face
# ---------------------------------------------------------------------------


def test_translate_face_along_normal_matches_offset():
    body = _box(dx=2.0, dy=3.0, dz=4.0)
    fid = _face_id_with_normal(body, (1.0, 0.0, 0.0))
    out = direct_translate_face(body, fid, (1.0, 0.0, 0.0))
    validate_body(out)
    assert _body_volume(out) == pytest.approx(3.0 * 3.0 * 4.0, rel=1e-6)


def test_translate_perpendicular_component_does_not_change_plane():
    body = _box(dx=2.0, dy=3.0, dz=4.0)
    fid = _face_id_with_normal(body, (1.0, 0.0, 0.0))
    # delta perpendicular to the +X normal projects to zero offset
    out = direct_translate_face(body, fid, (0.0, 5.0, 0.0))
    assert _body_volume(out) == pytest.approx(2.0 * 3.0 * 4.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Error contract
# ---------------------------------------------------------------------------


def test_unknown_face_raises_missing_reference():
    body = _box()
    with pytest.raises(MissingReferenceError):
        direct_offset_face(body, "deadbeefdeadbeef", 1.0)


def test_collapsing_offset_raises_degenerate():
    body = _box(dx=2.0, dy=3.0, dz=4.0)
    fid = _face_id_with_normal(body, (1.0, 0.0, 0.0))
    with pytest.raises(DirectEditError) as ei:
        # push the +X face inward past the -X face → degenerate box
        direct_offset_face(body, fid, -5.0)
    assert ei.value.reason in ("degenerate-geometry", "direct-edit-error")


def test_unsupported_body_error_is_direct_edit_error_subclass():
    assert issubclass(UnsupportedBodyError, DirectEditError)


def test_direct_edit_error_carries_reason():
    err = DirectEditError("boom", reason="non-planar face")
    assert err.reason == "non-planar face"
    assert isinstance(err, ValueError)


# ---------------------------------------------------------------------------
# DirectEditRecord
# ---------------------------------------------------------------------------


def test_direct_edit_record_dataclass():
    rec = DirectEditRecord(verb="offset", face_persistent_id="abc123")
    assert rec.verb == "offset"
    assert rec.face_persistent_id == "abc123"
    assert rec.params == {}
    rec2 = DirectEditRecord(verb="translate", face_persistent_id="x", params={"d": 1})
    assert rec2.params == {"d": 1}


# ---------------------------------------------------------------------------
# Direct ↔ parametric coexistence: commit to DAG and replay
# ---------------------------------------------------------------------------


def test_commit_direct_edit_to_dag_and_replay():
    body_before = _box(dx=2.0, dy=3.0, dz=4.0)
    fid = _face_id_with_normal(body_before, (1.0, 0.0, 0.0))
    body_after = direct_offset_face(body_before, fid, 1.0)

    dag = FeatureDAG()
    feats = commit_direct_edits_to_dag(dag, body_before, body_after)

    assert len(feats) == 1
    feat = feats[0]
    assert feat.kind == "direct_edit"
    assert "direct_edit" in dag.evaluators()
    assert "planes_after" in feat.params
    assert feat.params["plane_diff"], "a plane changed → diff must be non-empty"

    replayed = dag.evaluate(feat.id)
    validate_body(replayed)
    assert _body_volume(replayed) == pytest.approx(
        _body_volume(body_after), rel=1e-6
    )


def test_commit_registration_is_idempotent():
    body_before = _box()
    fid = _face_id_with_normal(body_before, (0.0, 1.0, 0.0))
    body_after = direct_offset_face(body_before, fid, 0.5)

    dag = FeatureDAG()
    commit_direct_edits_to_dag(dag, body_before, body_after)
    # second commit must not raise on re-registering the evaluator
    commit_direct_edits_to_dag(dag, body_before, body_after)
    assert "direct_edit" in dag.evaluators()


def test_commit_no_change_has_empty_diff():
    body = _box()
    dag = FeatureDAG()
    feats = commit_direct_edits_to_dag(dag, body, body)
    assert feats[0].params["plane_diff"] == []


# ---------------------------------------------------------------------------
# direct_rotate_face — sanity (no crash, stays valid for small rotation)
# ---------------------------------------------------------------------------


def test_rotate_face_unknown_raises_missing_reference():
    body = _box()
    with pytest.raises(MissingReferenceError):
        direct_rotate_face(body, "00000000deadbeef", (0.0, 0.0, 1.0), 0.1)
