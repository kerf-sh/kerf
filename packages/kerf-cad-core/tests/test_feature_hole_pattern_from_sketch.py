"""
Tests for feature_hole_pattern_from_sketch tool and helpers.

Pure-Python: no database, no OCCT needed for the validation and
point-extraction tests.  The tool-registration tests use a lightweight
fake pool/ctx following the same pattern as test_feature_boss_with_draft.py.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from kerf_cad_core.feature_hole_pattern_from_sketch import (
    validate_hole_pattern_args,
    extract_sketch_points,
    build_hole_pattern_node,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sketch_json(entities):
    """Return a JSON string for a minimal sketch with the given entities."""
    return json.dumps({"version": 1, "entities": entities})


def make_ctx(initial_content: str = ""):
    """Return (ctx, store, file_id) with an in-memory fake pool."""
    store = {
        "content": initial_content or json.dumps({"version": 1, "features": []}),
        "kind": "feature",
    }
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()

    class FakePool:
        def fetchone(self, query, *args):
            return (store["content"], store["kind"])

        def execute(self, query, *args):
            store["content"] = args[0]

    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]

    ctx = ProjectCtx(
        pool=FakePool(),
        storage=None,
        project_id=project_id,
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )
    return ctx, store, file_id


def run_tool(ctx, file_id, **kwargs):
    from kerf_cad_core.feature_hole_pattern_from_sketch import (
        run_feature_hole_pattern_from_sketch,
    )

    args = {"file_id": str(file_id), **kwargs}
    raw = asyncio.new_event_loop().run_until_complete(
        run_feature_hole_pattern_from_sketch(ctx, json.dumps(args).encode())
    )
    return json.loads(raw)


# ---------------------------------------------------------------------------
# validate_hole_pattern_args
# ---------------------------------------------------------------------------

class TestValidateHolePatternArgs:
    def test_valid_minimal(self):
        err, code = validate_hole_pattern_args("/holes.sketch", 3.0, 8.0)
        assert err is None and code is None

    def test_missing_sketch_path(self):
        err, code = validate_hole_pattern_args("", 3.0, 8.0)
        assert code == "BAD_ARGS"
        assert "sketch_path" in err

    def test_none_sketch_path(self):
        err, code = validate_hole_pattern_args(None, 3.0, 8.0)
        assert code == "BAD_ARGS"

    def test_sketch_path_wrong_extension(self):
        err, code = validate_hole_pattern_args("/holes.json", 3.0, 8.0)
        assert code == "BAD_ARGS"
        assert ".sketch" in err

    def test_diameter_zero_rejected(self):
        err, code = validate_hole_pattern_args("/h.sketch", 0, 8.0)
        assert code == "BAD_ARGS"
        assert "diameter" in err

    def test_diameter_negative_rejected(self):
        err, code = validate_hole_pattern_args("/h.sketch", -1.0, 8.0)
        assert code == "BAD_ARGS"

    def test_diameter_not_number_rejected(self):
        err, code = validate_hole_pattern_args("/h.sketch", "big", 8.0)
        assert code == "BAD_ARGS"

    def test_depth_zero_rejected(self):
        err, code = validate_hole_pattern_args("/h.sketch", 3.0, 0)
        assert code == "BAD_ARGS"
        assert "depth" in err

    def test_depth_negative_rejected(self):
        err, code = validate_hole_pattern_args("/h.sketch", 3.0, -5.0)
        assert code == "BAD_ARGS"

    def test_depth_not_number_rejected(self):
        err, code = validate_hole_pattern_args("/h.sketch", 3.0, "deep")
        assert code == "BAD_ARGS"

    def test_very_small_positive_diameter_ok(self):
        err, code = validate_hole_pattern_args("/h.sketch", 0.001, 8.0)
        assert err is None

    def test_very_small_positive_depth_ok(self):
        err, code = validate_hole_pattern_args("/h.sketch", 3.0, 0.001)
        assert err is None


# ---------------------------------------------------------------------------
# extract_sketch_points
# ---------------------------------------------------------------------------

class TestExtractSketchPoints:
    def test_empty_sketch_returns_empty(self):
        pts = extract_sketch_points(_sketch_json([]))
        assert pts == []

    def test_none_returns_empty(self):
        pts = extract_sketch_points(None)
        assert pts == []

    def test_origin_excluded(self):
        entities = [{"type": "point", "id": "origin", "x": 0, "y": 0}]
        pts = extract_sketch_points(_sketch_json(entities))
        assert pts == []

    def test_single_point_extracted(self):
        entities = [{"type": "point", "id": "p1", "x": 10.0, "y": 20.0}]
        pts = extract_sketch_points(_sketch_json(entities))
        assert len(pts) == 1
        assert pts[0] == {"x": 10.0, "y": 20.0}

    def test_multiple_points_extracted(self):
        entities = [
            {"type": "point", "id": "p1", "x": 10.0, "y": 10.0},
            {"type": "point", "id": "p2", "x": 40.0, "y": 10.0},
            {"type": "point", "id": "p3", "x": 40.0, "y": 40.0},
            {"type": "point", "id": "p4", "x": 10.0, "y": 40.0},
        ]
        pts = extract_sketch_points(_sketch_json(entities))
        assert len(pts) == 4
        xs = {p["x"] for p in pts}
        assert xs == {10.0, 40.0}

    def test_non_point_entities_ignored(self):
        entities = [
            {"type": "line", "id": "l1", "p1": "p0", "p2": "p1"},
            {"type": "circle", "id": "c1", "center": "p2", "radius": 5},
            {"type": "point", "id": "p1", "x": 15.0, "y": 25.0},
        ]
        pts = extract_sketch_points(_sketch_json(entities))
        assert len(pts) == 1
        assert pts[0] == {"x": 15.0, "y": 25.0}

    def test_origin_and_regular_points_mixed(self):
        entities = [
            {"type": "point", "id": "origin", "x": 0, "y": 0},
            {"type": "point", "id": "p1", "x": 5.0, "y": 7.0},
            {"type": "point", "id": "p2", "x": 12.0, "y": 3.0},
        ]
        pts = extract_sketch_points(_sketch_json(entities))
        assert len(pts) == 2

    def test_json_string_input(self):
        entities = [{"type": "point", "id": "p1", "x": 1.0, "y": 2.0}]
        pts = extract_sketch_points(_sketch_json(entities))
        assert len(pts) == 1

    def test_dict_input(self):
        obj = {"entities": [{"type": "point", "id": "p1", "x": 3.0, "y": 4.0}]}
        pts = extract_sketch_points(obj)
        assert pts == [{"x": 3.0, "y": 4.0}]

    def test_invalid_json_returns_empty(self):
        pts = extract_sketch_points("{not valid json")
        assert pts == []

    def test_missing_coordinates_default_to_zero(self):
        entities = [{"type": "point", "id": "p1"}]
        pts = extract_sketch_points(_sketch_json(entities))
        assert pts == [{"x": 0.0, "y": 0.0}]

    def test_no_entities_key_returns_empty(self):
        pts = extract_sketch_points(json.dumps({"version": 1}))
        assert pts == []

    def test_integer_coordinates_coerced_to_float(self):
        entities = [{"type": "point", "id": "p1", "x": 5, "y": 3}]
        pts = extract_sketch_points(_sketch_json(entities))
        assert pts[0]["x"] == 5.0
        assert isinstance(pts[0]["x"], float)


# ---------------------------------------------------------------------------
# build_hole_pattern_node
# ---------------------------------------------------------------------------

class TestBuildHolePatternNode:
    def test_required_fields_present(self):
        node = build_hole_pattern_node(
            "hole_pattern-1", "/holes.sketch", 3.0, 8.0
        )
        assert node["id"] == "hole_pattern-1"
        assert node["op"] == "hole_pattern"
        assert node["sketch_path"] == "/holes.sketch"
        assert node["diameter"] == 3.0
        assert node["depth"] == 8.0
        assert "target_id" not in node
        assert "name" not in node

    def test_target_id_included_when_provided(self):
        node = build_hole_pattern_node(
            "hole_pattern-1", "/h.sketch", 3.0, 8.0, target_id="pad-1"
        )
        assert node["target_id"] == "pad-1"

    def test_target_id_omitted_when_empty(self):
        node = build_hole_pattern_node("n", "/h.sketch", 3.0, 8.0, target_id="")
        assert "target_id" not in node

    def test_name_included_when_provided(self):
        node = build_hole_pattern_node(
            "hole_pattern-1", "/h.sketch", 3.0, 8.0, name="bolt holes"
        )
        assert node["name"] == "bolt holes"

    def test_diameter_coerced_to_float(self):
        node = build_hole_pattern_node("n", "/h.sketch", 3, 8)
        assert isinstance(node["diameter"], float)
        assert isinstance(node["depth"], float)

    def test_schema_round_trip(self):
        node = build_hole_pattern_node(
            "hole_pattern-7", "/grid.sketch", 2.5, 12.0, target_id="revolve-1"
        )
        restored = json.loads(json.dumps(node))
        assert restored == node


# ---------------------------------------------------------------------------
# Tool handler (fake DB) — requires kerf_core to be importable
# ---------------------------------------------------------------------------

class TestRunFeatureHolePatternFromSketch:
    @pytest.fixture(autouse=True)
    def _skip_if_no_kerf_core(self):
        try:
            from kerf_core.utils.context import ProjectCtx  # noqa: F401
        except ImportError:
            pytest.skip("kerf_core not installed")

    def test_missing_file_id(self):
        ctx, store, fid = make_ctx()
        from kerf_cad_core.feature_hole_pattern_from_sketch import (
            run_feature_hole_pattern_from_sketch,
        )
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_hole_pattern_from_sketch(
                ctx,
                json.dumps({
                    "sketch_path": "/h.sketch",
                    "diameter": 3.0,
                    "depth": 8.0,
                }).encode(),
            )
        )
        result = json.loads(raw)
        assert "error" in result

    def test_missing_sketch_path(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, diameter=3.0, depth=8.0)
        assert "error" in result

    def test_missing_diameter(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, sketch_path="/h.sketch", depth=8.0)
        assert "error" in result

    def test_missing_depth(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, sketch_path="/h.sketch", diameter=3.0)
        assert "error" in result

    def test_invalid_uuid(self):
        from kerf_cad_core.feature_hole_pattern_from_sketch import (
            run_feature_hole_pattern_from_sketch,
        )
        ctx, store, fid = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_hole_pattern_from_sketch(
                ctx,
                json.dumps({
                    "file_id": "not-a-uuid",
                    "sketch_path": "/h.sketch",
                    "diameter": 3.0,
                    "depth": 8.0,
                }).encode(),
            )
        )
        result = json.loads(raw)
        assert "error" in result

    def test_diameter_zero_rejected(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, sketch_path="/h.sketch", diameter=0, depth=8.0)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_depth_zero_rejected(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, sketch_path="/h.sketch", diameter=3.0, depth=0)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_sketch_path_wrong_extension_rejected(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, sketch_path="/holes.json", diameter=3.0, depth=8.0)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_appends_node(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, sketch_path="/holes.sketch", diameter=3.0, depth=8.0)
        assert "error" not in result
        assert result["op"] == "hole_pattern"
        doc = json.loads(store["content"])
        assert len(doc["features"]) == 1
        node = doc["features"][0]
        assert node["op"] == "hole_pattern"
        assert node["sketch_path"] == "/holes.sketch"
        assert node["diameter"] == 3.0
        assert node["depth"] == 8.0

    def test_node_id_auto_increments(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, sketch_path="/h.sketch", diameter=3.0, depth=8.0)
        run_tool(ctx, fid, sketch_path="/h.sketch", diameter=3.0, depth=8.0)
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"] == "hole_pattern-1"
        assert doc["features"][1]["id"] == "hole_pattern-2"

    def test_explicit_node_id(self):
        ctx, store, fid = make_ctx()
        result = run_tool(
            ctx, fid, sketch_path="/h.sketch", diameter=3.0, depth=8.0, id="hpat-custom"
        )
        assert result["id"] == "hpat-custom"
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"] == "hpat-custom"

    def test_target_id_stored(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, sketch_path="/h.sketch", diameter=3.0, depth=8.0, target_id="pad-1")
        doc = json.loads(store["content"])
        assert doc["features"][0]["target_id"] == "pad-1"

    def test_target_id_absent_when_omitted(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, sketch_path="/h.sketch", diameter=3.0, depth=8.0)
        doc = json.loads(store["content"])
        assert "target_id" not in doc["features"][0]

    def test_name_stored(self):
        ctx, store, fid = make_ctx()
        run_tool(
            ctx, fid, sketch_path="/h.sketch", diameter=3.0, depth=8.0,
            name="bolt pattern"
        )
        doc = json.loads(store["content"])
        assert doc["features"][0]["name"] == "bolt pattern"

    def test_op_field_in_payload(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, sketch_path="/h.sketch", diameter=3.0, depth=8.0)
        assert result.get("op") == "hole_pattern"

    def test_file_id_in_payload(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, sketch_path="/h.sketch", diameter=3.0, depth=8.0)
        assert result.get("file_id") == str(fid)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
