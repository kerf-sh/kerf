"""
Tests for feature_mirror tool — pure logic, no DB required.

Exercises validate_mirror_args and build_mirror_node directly so the
suite runs without a live Postgres connection.
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.feature_mirror import validate_mirror_args, build_mirror_node


# ── validate_mirror_args — source mutual exclusion ───────────────────────────

def test_valid_feature_and_plane():
    err, code = validate_mirror_args("pad-1", "", "XZ", None)
    assert err is None and code is None


def test_valid_body_and_plane():
    err, code = validate_mirror_args("", "body-1", "YZ", None)
    assert err is None and code is None


def test_valid_feature_and_face():
    err, code = validate_mirror_args("pad-1", "", "", 7)
    assert err is None and code is None


def test_both_sources_rejected():
    err, code = validate_mirror_args("pad-1", "body-1", "XY", None)
    assert code == "BAD_ARGS"
    assert "source" in err


def test_no_source_rejected():
    err, code = validate_mirror_args("", "", "XY", None)
    assert code == "BAD_ARGS"
    assert "source" in err


# ── validate_mirror_args — plane mutual exclusion ────────────────────────────

def test_both_plane_and_face_rejected():
    err, code = validate_mirror_args("pad-1", "", "XY", 3)
    assert code == "BAD_ARGS"
    assert "mirror" in err


def test_no_plane_rejected():
    err, code = validate_mirror_args("pad-1", "", "", None)
    assert code == "BAD_ARGS"


def test_invalid_plane_rejected():
    err, code = validate_mirror_args("pad-1", "", "AB", None)
    assert code == "BAD_ARGS"
    assert "AB" in err


def test_lowercase_plane_normalised():
    # lowercase should be accepted (normalised inside validate)
    err, code = validate_mirror_args("pad-1", "", "xy", None)
    assert err is None


# ── build_mirror_node ─────────────────────────────────────────────────────────

def test_build_node_feature_plane():
    node = build_mirror_node("mirror_feature-1", "pad-1", "", "XZ", None, True)
    assert node["id"] == "mirror_feature-1"
    assert node["op"] == "mirror_feature"
    params = node["params"]
    assert params["source_feature_id"] == "pad-1"
    assert params["mirror_plane"] == "XZ"
    assert params["merge"] is True
    assert "source_body_id" not in params
    assert "mirror_face_id" not in params


def test_build_node_body_face():
    node = build_mirror_node("mirror_feature-2", "", "body-1", "", 5, False)
    params = node["params"]
    assert params["source_body_id"] == "body-1"
    assert params["mirror_face_id"] == 5
    assert params["merge"] is False
    assert "source_feature_id" not in params
    assert "mirror_plane" not in params


def test_default_merge_is_true():
    node = build_mirror_node("mirror_feature-3", "pad-1", "", "YZ", None, True)
    assert node["params"]["merge"] is True


def test_plane_uppercased_in_node():
    node = build_mirror_node("mirror_feature-4", "pad-1", "", "xy", None, True)
    assert node["params"]["mirror_plane"] == "XY"


def test_optional_name_included():
    node = build_mirror_node("mirror_feature-5", "pad-1", "", "XY", None, True, name="arm_mirror")
    assert node.get("name") == "arm_mirror"


def test_no_name_field_when_empty():
    node = build_mirror_node("mirror_feature-6", "pad-1", "", "XY", None, True)
    assert "name" not in node


def test_node_is_json_serialisable():
    node = build_mirror_node("mirror_feature-7", "pad-1", "", "XZ", None, True)
    dumped = json.dumps(node)
    loaded = json.loads(dumped)
    assert loaded["op"] == "mirror_feature"
