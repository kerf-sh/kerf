"""
Tests for feature_draft tool — pure logic, no DB required.

Exercises validate_draft_args and build_draft_node directly so the suite
runs without a live Postgres connection.
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kerf_imports.tools.feature_draft import validate_draft_args, build_draft_node, ANGLE_MIN, ANGLE_MAX


# ── validate_draft_args ───────────────────────────────────────────────────────

def test_valid_outward_draft():
    err, code = validate_draft_args([1, 2, 3], 6, 5.0, "outward")
    assert err is None and code is None


def test_valid_inward_draft():
    err, code = validate_draft_args([7], 4, -3.0, "inward")
    assert err is None and code is None


def test_angle_at_boundary_positive():
    err, code = validate_draft_args([1], 2, 30.0, "outward")
    assert err is None


def test_angle_at_boundary_negative():
    err, code = validate_draft_args([1], 2, -30.0, "outward")
    assert err is None


def test_angle_too_large_rejected():
    err, code = validate_draft_args([1], 2, 30.1, "outward")
    assert code == "BAD_ARGS"
    assert "30.1" in err


def test_angle_too_small_rejected():
    err, code = validate_draft_args([1], 2, -31.0, "inward")
    assert code == "BAD_ARGS"


def test_empty_face_ids_rejected():
    err, code = validate_draft_args([], 2, 5.0, "outward")
    assert code == "BAD_ARGS"
    assert "face_ids" in err


def test_none_face_ids_rejected():
    err, code = validate_draft_args(None, 2, 5.0, "outward")
    assert code == "BAD_ARGS"


def test_missing_neutral_plane_rejected():
    err, code = validate_draft_args([1, 2], None, 5.0, "outward")
    assert code == "BAD_ARGS"
    assert "neutral_plane" in err


def test_invalid_pull_direction_rejected():
    err, code = validate_draft_args([1], 2, 5.0, "sideways")
    assert code == "BAD_ARGS"
    assert "sideways" in err


# ── build_draft_node ──────────────────────────────────────────────────────────

def test_build_node_shape():
    node = build_draft_node("draft-1", [2, 3], 1, 7.5, "outward")
    assert node["id"] == "draft-1"
    assert node["op"] == "draft"
    params = node["params"]
    assert params["face_ids"] == [2, 3]
    assert params["neutral_plane_face_id"] == 1
    assert params["angle_deg"] == 7.5
    assert params["pull_direction"] == "outward"


def test_build_node_inward():
    node = build_draft_node("draft-2", [5], 0, -2.0, "inward")
    assert node["params"]["pull_direction"] == "inward"
    assert node["params"]["angle_deg"] == -2.0


def test_build_node_optional_name():
    node = build_draft_node("draft-3", [1], 0, 1.0, "outward", name="housing_taper")
    assert node.get("name") == "housing_taper"


def test_build_node_no_name_field_when_empty():
    node = build_draft_node("draft-4", [1], 0, 1.0, "outward")
    assert "name" not in node


def test_node_is_json_serialisable():
    node = build_draft_node("draft-5", [1, 2], 3, 5.0, "outward")
    dumped = json.dumps(node)
    loaded = json.loads(dumped)
    assert loaded["op"] == "draft"
