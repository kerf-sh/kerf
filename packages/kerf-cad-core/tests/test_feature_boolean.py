"""
Tests for the `feature_boolean` backend LLM tool.

Pure-Python: no database required. All tests use a lightweight in-memory
FakePool/ctx, matching the pattern in test_feature_sweep1_mode.py.

Covers (~12 cases):
  - ToolSpec schema: name, required fields, kind enum.
  - Schema: kind accepts cut/fuse/common, rejects other strings.
  - Schema: target_a_id, target_b_id, kind are all required.
  - Node shape: stored JSON matches the tree node spec.
  - Error paths: invalid JSON, missing fields, non-uuid file_id,
    unknown kind, non-existent file.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from kerf_cad_core.surfacing import (
    feature_boolean_spec,
    run_feature_boolean,
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
            if kind == "NOT_FOUND":
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
        run_feature_boolean(ctx, json.dumps(args).encode())
    )
    return json.loads(raw)


# ---------------------------------------------------------------------------
# ToolSpec schema
# ---------------------------------------------------------------------------

class TestFeatureBooleanSpec:
    def test_spec_name(self):
        assert feature_boolean_spec.name == "feature_boolean"

    def test_required_fields(self):
        required = feature_boolean_spec.input_schema.get("required", [])
        assert "file_id" in required
        assert "target_a_id" in required
        assert "target_b_id" in required
        assert "kind" in required

    def test_kind_enum_values(self):
        props = feature_boolean_spec.input_schema["properties"]
        enum = props["kind"].get("enum", [])
        assert set(enum) == {"cut", "fuse", "common"}

    def test_options_not_required(self):
        required = feature_boolean_spec.input_schema.get("required", [])
        assert "options" not in required


# ---------------------------------------------------------------------------
# kind accepted for all valid values
# ---------------------------------------------------------------------------

class TestBooleanKindValidValues:
    @pytest.mark.parametrize("kind", ["cut", "fuse", "common"])
    def test_valid_kind_accepted(self, kind):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, target_a_id="pad-1", target_b_id="pad-2", kind=kind)
        assert result.get("error") is None, (
            f"Expected success for kind='{kind}', got: {result.get('error')}"
        )
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["kind"] == kind


# ---------------------------------------------------------------------------
# Node shape
# ---------------------------------------------------------------------------

class TestBooleanNodeShape:
    def test_node_op_is_boolean(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_a_id="pad-1", target_b_id="sweep1-1", kind="cut")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["op"] == "boolean"

    def test_target_ids_stored(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_a_id="body-a", target_b_id="body-b", kind="fuse")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["target_a_id"] == "body-a"
        assert node["target_b_id"] == "body-b"

    def test_node_id_auto_generated(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_a_id="p-1", target_b_id="p-2", kind="common")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["id"].startswith("boolean-")

    def test_explicit_id_via_options(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_a_id="p-1", target_b_id="p-2", kind="cut",
                 options={"id": "boolean-custom"})
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["id"] == "boolean-custom"

    def test_result_payload_contains_kind(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, target_a_id="p-1", target_b_id="p-2", kind="fuse")
        assert result.get("kind") == "fuse"
        assert result.get("op") == "boolean"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

class TestBooleanErrors:
    def test_invalid_json_args(self):
        ctx, _, _ = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_boolean(ctx, b"not json")
        )
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_missing_file_id(self):
        ctx, _, _ = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_boolean(ctx, json.dumps({
                "target_a_id": "a", "target_b_id": "b", "kind": "cut"
            }).encode())
        )
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_non_uuid_file_id(self):
        ctx, _, _ = make_ctx()
        result = run_tool(ctx, "not-a-uuid",
                          target_a_id="a", target_b_id="b", kind="cut")
        assert result.get("code") == "BAD_ARGS"

    def test_unknown_kind_rejected(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, target_a_id="a", target_b_id="b", kind="union")
        assert result.get("code") == "BAD_ARGS"
        assert "union" in result.get("error", "")

    def test_empty_kind_rejected(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, target_a_id="a", target_b_id="b", kind="")
        assert result.get("code") == "BAD_ARGS"

    def test_missing_target_a_id(self):
        ctx, _, fid = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_boolean(ctx, json.dumps({
                "file_id": str(fid), "target_b_id": "b", "kind": "cut"
            }).encode())
        )
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_non_existent_file_returns_not_found(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        result = run_tool(ctx, fid,
                          target_a_id="a", target_b_id="b", kind="cut")
        assert result.get("code") == "NOT_FOUND"
