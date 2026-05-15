"""
Tests for the `feature_trim_by_curve` backend LLM tool (NURBS Phase 4 C2-T3).

Pure-Python: no database required. All tests use a lightweight in-memory
FakePool/ctx, matching the pattern in test_feature_surface_boolean.py.

Covers (~15 cases):
  - ToolSpec schema: name, required fields, keep_side enum, tolerance field.
  - Required field validation: file_id, target_feature_ref, target_face_name,
    trim_curve_ref all required.
  - keep_side: default 'positive', accepts 'positive'/'negative', rejects other.
  - tolerance: optional, default absent, stored when provided, zero/negative rejected.
  - Node shape: op == 'trim_by_curve', all fields stored correctly.
  - Auto-id prefix 'trim_by_curve-', explicit id via options.id.
  - Error paths: invalid JSON, non-uuid file_id, missing fields, non-existent file.
  - Result payload: id, op, keep_side fields present.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from kerf_cad_core.surfacing import (
    feature_trim_by_curve_spec,
    run_feature_trim_by_curve,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(initial_content: str = "", kind: str = "feature"):
    """Return (ctx, store, file_id) with an in-memory fake pool."""
    store = {
        "content": initial_content or json.dumps({"version": 1, "features": []}),
        "kind": kind,
    }
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()

    class FakePool:
        def fetchone(self, query, *args):
            if store["kind"] == "NOT_FOUND":
                return None
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
    args = {"file_id": str(file_id), **kwargs}
    raw = asyncio.new_event_loop().run_until_complete(
        run_feature_trim_by_curve(ctx, json.dumps(args).encode())
    )
    return json.loads(raw)


# ---------------------------------------------------------------------------
# ToolSpec schema
# ---------------------------------------------------------------------------

class TestFeatureTrimByCurveSpec:
    def test_spec_name(self):
        assert feature_trim_by_curve_spec.name == "feature_trim_by_curve"

    def test_required_fields(self):
        required = feature_trim_by_curve_spec.input_schema.get("required", [])
        assert "file_id" in required
        assert "target_feature_ref" in required
        assert "target_face_name" in required
        assert "trim_curve_ref" in required

    def test_keep_side_enum_values(self):
        props = feature_trim_by_curve_spec.input_schema["properties"]
        enum = props["keep_side"].get("enum", [])
        assert set(enum) == {"positive", "negative"}

    def test_tolerance_is_number_property(self):
        props = feature_trim_by_curve_spec.input_schema["properties"]
        assert "tolerance" in props
        assert props["tolerance"]["type"] == "number"

    def test_tolerance_not_required(self):
        required = feature_trim_by_curve_spec.input_schema.get("required", [])
        assert "tolerance" not in required

    def test_keep_side_not_required(self):
        required = feature_trim_by_curve_spec.input_schema.get("required", [])
        assert "keep_side" not in required

    def test_options_not_required(self):
        required = feature_trim_by_curve_spec.input_schema.get("required", [])
        assert "options" not in required


# ---------------------------------------------------------------------------
# keep_side handling
# ---------------------------------------------------------------------------

class TestTrimByCurveKeepSide:
    def test_default_keep_side_is_positive(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid,
                 target_feature_ref="sweep1-1",
                 target_face_name="face-1",
                 trim_curve_ref="/sketch/cut.sketch")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["keep_side"] == "positive"

    def test_explicit_positive_kept(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid,
                 target_feature_ref="sweep1-1",
                 target_face_name="face-1",
                 trim_curve_ref="/sketch/cut.sketch",
                 keep_side="positive")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["keep_side"] == "positive"

    def test_negative_accepted(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid,
                 target_feature_ref="sweep1-1",
                 target_face_name="face-1",
                 trim_curve_ref="/sketch/cut.sketch",
                 keep_side="negative")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["keep_side"] == "negative"

    def test_invalid_keep_side_rejected(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid,
                          target_feature_ref="sweep1-1",
                          target_face_name="face-1",
                          trim_curve_ref="/sketch/cut.sketch",
                          keep_side="left")
        assert result.get("code") == "BAD_ARGS"
        assert "left" in result.get("error", "")


# ---------------------------------------------------------------------------
# Node shape
# ---------------------------------------------------------------------------

class TestTrimByCurveNodeShape:
    def test_node_op_is_trim_by_curve(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid,
                 target_feature_ref="sweep1-1",
                 target_face_name="face-2",
                 trim_curve_ref="/sketch/window.sketch")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["op"] == "trim_by_curve"

    def test_all_required_fields_stored(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid,
                 target_feature_ref="blend-1",
                 target_face_name="face-3",
                 trim_curve_ref="/sketch/edge.sketch")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["target_feature_ref"] == "blend-1"
        assert node["target_face_name"] == "face-3"
        assert node["trim_curve_ref"] == "/sketch/edge.sketch"

    def test_node_id_auto_generated(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid,
                 target_feature_ref="b-1",
                 target_face_name="face-1",
                 trim_curve_ref="/sketch/c.sketch")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["id"].startswith("trim_by_curve-")

    def test_explicit_id_via_options(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid,
                 target_feature_ref="b-1",
                 target_face_name="face-1",
                 trim_curve_ref="/sketch/c.sketch",
                 options={"id": "trim_by_curve-custom"})
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["id"] == "trim_by_curve-custom"

    def test_result_payload_contains_op(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid,
                          target_feature_ref="b-1",
                          target_face_name="face-1",
                          trim_curve_ref="/sketch/c.sketch")
        assert result.get("op") == "trim_by_curve"

    def test_result_payload_contains_keep_side(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid,
                          target_feature_ref="b-1",
                          target_face_name="face-1",
                          trim_curve_ref="/sketch/c.sketch",
                          keep_side="negative")
        assert result.get("keep_side") == "negative"

    def test_result_payload_contains_id(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid,
                          target_feature_ref="b-1",
                          target_face_name="face-1",
                          trim_curve_ref="/sketch/c.sketch")
        assert result.get("id", "").startswith("trim_by_curve-")


# ---------------------------------------------------------------------------
# Tolerance handling
# ---------------------------------------------------------------------------

class TestTrimByCurveTolerance:
    def test_tolerance_absent_by_default(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid,
                 target_feature_ref="b-1",
                 target_face_name="face-1",
                 trim_curve_ref="/sketch/c.sketch")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert "tolerance" not in node

    def test_tolerance_stored_when_provided(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid,
                 target_feature_ref="b-1",
                 target_face_name="face-1",
                 trim_curve_ref="/sketch/c.sketch",
                 tolerance=1e-2)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert abs(node["tolerance"] - 1e-2) < 1e-10

    def test_tolerance_zero_rejected(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid,
                          target_feature_ref="b-1",
                          target_face_name="face-1",
                          trim_curve_ref="/sketch/c.sketch",
                          tolerance=0)
        assert result.get("code") == "BAD_ARGS"

    def test_tolerance_negative_rejected(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid,
                          target_feature_ref="b-1",
                          target_face_name="face-1",
                          trim_curve_ref="/sketch/c.sketch",
                          tolerance=-0.001)
        assert result.get("code") == "BAD_ARGS"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

class TestTrimByCurveErrors:
    def test_invalid_json_args(self):
        ctx, _, _ = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_trim_by_curve(ctx, b"not json")
        )
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_missing_file_id(self):
        ctx, _, _ = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_trim_by_curve(ctx, json.dumps({
                "target_feature_ref": "b-1",
                "target_face_name": "face-1",
                "trim_curve_ref": "/sketch/c.sketch",
            }).encode())
        )
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_non_uuid_file_id(self):
        ctx, _, _ = make_ctx()
        result = run_tool(ctx, "not-a-uuid",
                          target_feature_ref="b-1",
                          target_face_name="face-1",
                          trim_curve_ref="/sketch/c.sketch")
        assert result.get("code") == "BAD_ARGS"

    def test_missing_target_feature_ref(self):
        ctx, _, fid = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_trim_by_curve(ctx, json.dumps({
                "file_id": str(fid),
                "target_face_name": "face-1",
                "trim_curve_ref": "/sketch/c.sketch",
            }).encode())
        )
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_missing_target_face_name(self):
        ctx, _, fid = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_trim_by_curve(ctx, json.dumps({
                "file_id": str(fid),
                "target_feature_ref": "b-1",
                "trim_curve_ref": "/sketch/c.sketch",
            }).encode())
        )
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_missing_trim_curve_ref(self):
        ctx, _, fid = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_trim_by_curve(ctx, json.dumps({
                "file_id": str(fid),
                "target_feature_ref": "b-1",
                "target_face_name": "face-1",
            }).encode())
        )
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_non_existent_file_returns_not_found(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        result = run_tool(ctx, fid,
                          target_feature_ref="b-1",
                          target_face_name="face-1",
                          trim_curve_ref="/sketch/c.sketch")
        assert result.get("code") == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Multiple nodes accumulate
# ---------------------------------------------------------------------------

class TestTrimByCurveMultipleNodes:
    def test_multiple_nodes_get_distinct_ids(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid,
                 target_feature_ref="b-1",
                 target_face_name="face-1",
                 trim_curve_ref="/sketch/a.sketch")
        run_tool(ctx, fid,
                 target_feature_ref="b-2",
                 target_face_name="face-2",
                 trim_curve_ref="/sketch/b.sketch")
        doc = json.loads(store["content"])
        assert len(doc["features"]) == 2
        ids = [n["id"] for n in doc["features"]]
        assert ids[0] != ids[1]
        assert ids[0].startswith("trim_by_curve-")
        assert ids[1].startswith("trim_by_curve-")
