"""
Tests for feature_rib tool — pure logic, no DB required.
Exercises validate_rib_args and build_rib_node directly.
"""
import json
import sys
import os
import importlib.util

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

spec = importlib.util.spec_from_file_location("feature_rib", os.path.join(os.path.dirname(__file__), "../src/kerf_imports/tools/feature_rib.py"))
feature_rib_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feature_rib_mod)

validate_rib_args = feature_rib_mod.validate_rib_args
build_rib_node = feature_rib_mod.build_rib_node


def test_valid_sketch_and_positive_thickness():
    err, code = validate_rib_args("sketch-1", 5.0)
    assert err is None and code is None


def test_valid_integer_thickness():
    err, code = validate_rib_args("sketch-1", 3)
    assert err is None and code is None


def test_zero_thickness_rejected():
    err, code = validate_rib_args("sketch-1", 0)
    assert code == "BAD_ARGS"
    assert "thickness" in err.lower()


def test_negative_thickness_rejected():
    err, code = validate_rib_args("sketch-1", -2.5)
    assert code == "BAD_ARGS"
    assert "positive" in err.lower()


def test_missing_sketch_id_rejected():
    err, code = validate_rib_args("", 5.0)
    assert code == "BAD_ARGS"
    assert "sketch_id" in err.lower()


def test_none_sketch_id_rejected():
    err, code = validate_rib_args(None, 5.0)
    assert code == "BAD_ARGS"


def test_missing_thickness_rejected():
    err, code = validate_rib_args("sketch-1", None)
    assert code == "BAD_ARGS"


def test_build_node_basic():
    node = build_rib_node("rib-1", "sketch-1", 3.0, False, False, 0)
    assert node["id"] == "rib-1"
    assert node["op"] == "rib"
    assert node["params"]["sketch_id"] == "sketch-1"
    assert node["params"]["thickness_mm"] == 3.0
    assert node["params"]["both_sides"] is False
    assert node["params"]["midplane"] is False
    assert node["params"]["draft_angle_deg"] == 0


def test_build_node_both_sides_true():
    node = build_rib_node("rib-2", "sketch-1", 4.0, True, False, 0)
    assert node["params"]["both_sides"] is True


def test_build_node_midplane_true():
    node = build_rib_node("rib-3", "sketch-1", 2.0, False, True, 0)
    assert node["params"]["midplane"] is True


def test_build_node_with_draft_angle():
    node = build_rib_node("rib-4", "sketch-1", 3.0, False, False, 2.5)
    assert node["params"]["draft_angle_deg"] == 2.5


def test_build_node_optional_name_included():
    node = build_rib_node("rib-5", "sketch-1", 3.0, False, False, 0, name="stiffener")
    assert node.get("name") == "stiffener"


def test_build_node_no_name_field_when_empty():
    node = build_rib_node("rib-6", "sketch-1", 3.0, False, False, 0)
    assert "name" not in node


def test_node_is_json_serialisable():
    node = build_rib_node("rib-7", "sketch-1", 3.0, True, True, 1.5, name="gusset")
    dumped = json.dumps(node)
    loaded = json.loads(dumped)
    assert loaded["op"] == "rib"
    assert loaded["params"]["both_sides"] is True
    assert loaded["params"]["midplane"] is True