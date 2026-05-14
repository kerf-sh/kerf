"""
Tests for the `feature_surface_boolean` backend LLM tool (NURBS Phase 4 C1-T3).

Pure-Python: no database required. All tests use a lightweight in-memory
FakePool/ctx, matching the pattern in test_feature_boolean.py.

Covers (~15 cases):
  - ToolSpec schema: name, required fields, kind enum, fuzziness field.
  - Schema: kind accepts cut/fuse/common, rejects other strings.
  - Schema: target_a_id, target_b_id, kind are all required.
  - Schema: fuzziness is optional; stored when provided.
  - Node shape: stored JSON matches the tree node spec (op == "surface_boolean").
  - Fuzziness: default absent; explicit value stored; zero/negative rejected.
  - Error paths: invalid JSON, missing fields, non-uuid file_id,
    unknown kind, non-existent file.
  - options.id: explicit id stored; auto-generated id prefixed "surface_boolean-".
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from kerf_cad_core.surfacing import (
    feature_surface_boolean_spec,
    run_feature_surface_boolean,
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
        run_feature_surface_boolean(ctx, json.dumps(args).encode())
    )
    return json.loads(raw)


# ---------------------------------------------------------------------------
# ToolSpec schema
# ---------------------------------------------------------------------------

class TestFeatureSurfaceBooleanSpec:
    def test_spec_name(self):
        assert feature_surface_boolean_spec.name == "feature_surface_boolean"

    def test_required_fields(self):
        required = feature_surface_boolean_spec.input_schema.get("required", [])
        assert "file_id" in required
        assert "target_a_id" in required
        assert "target_b_id" in required
        assert "kind" in required

    def test_kind_enum_values(self):
        props = feature_surface_boolean_spec.input_schema["properties"]
        enum = props["kind"].get("enum", [])
        assert set(enum) == {"cut", "fuse", "common"}

    def test_fuzziness_is_number_property(self):
        props = feature_surface_boolean_spec.input_schema["properties"]
        assert "fuzziness" in props
        assert props["fuzziness"]["type"] == "number"

    def test_fuzziness_not_required(self):
        required = feature_surface_boolean_spec.input_schema.get("required", [])
        assert "fuzziness" not in required

    def test_options_not_required(self):
        required = feature_surface_boolean_spec.input_schema.get("required", [])
        assert "options" not in required


# ---------------------------------------------------------------------------
# kind accepted for all valid values
# ---------------------------------------------------------------------------

class TestSurfaceBooleanKindValidValues:
    @pytest.mark.parametrize("kind", ["cut", "fuse", "common"])
    def test_valid_kind_accepted(self, kind):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, target_a_id="sweep1-1", target_b_id="blend-1", kind=kind)
        assert result.get("error") is None, (
            f"Expected success for kind='{kind}', got: {result.get('error')}"
        )
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["kind"] == kind


# ---------------------------------------------------------------------------
# Node shape
# ---------------------------------------------------------------------------

class TestSurfaceBooleanNodeShape:
    def test_node_op_is_surface_boolean(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_a_id="sweep1-1", target_b_id="blend-2", kind="cut")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["op"] == "surface_boolean"

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
        assert node["id"].startswith("surface_boolean-")

    def test_explicit_id_via_options(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_a_id="p-1", target_b_id="p-2", kind="cut",
                 options={"id": "surface_boolean-custom"})
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["id"] == "surface_boolean-custom"

    def test_result_payload_contains_kind(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, target_a_id="p-1", target_b_id="p-2", kind="fuse")
        assert result.get("kind") == "fuse"
        assert result.get("op") == "surface_boolean"

    def test_result_payload_contains_id(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, target_a_id="a", target_b_id="b", kind="cut")
        assert result.get("id", "").startswith("surface_boolean-")


# ---------------------------------------------------------------------------
# Fuzziness handling
# ---------------------------------------------------------------------------

class TestSurfaceBooleanFuzziness:
    def test_fuzziness_absent_by_default(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_a_id="a", target_b_id="b", kind="cut")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert "fuzziness" not in node

    def test_fuzziness_stored_when_provided(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_a_id="a", target_b_id="b", kind="cut", fuzziness=1e-3)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert abs(node["fuzziness"] - 1e-3) < 1e-10

    def test_fuzziness_zero_rejected(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, target_a_id="a", target_b_id="b", kind="cut", fuzziness=0)
        assert result.get("code") == "BAD_ARGS"

    def test_fuzziness_negative_rejected(self):
        ctx, _, fid = make_ctx()
        result = run_tool(ctx, fid, target_a_id="a", target_b_id="b", kind="cut", fuzziness=-1e-4)
        assert result.get("code") == "BAD_ARGS"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

class TestSurfaceBooleanErrors:
    def test_invalid_json_args(self):
        ctx, _, _ = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_surface_boolean(ctx, b"not json")
        )
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_missing_file_id(self):
        ctx, _, _ = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_surface_boolean(ctx, json.dumps({
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
            run_feature_surface_boolean(ctx, json.dumps({
                "file_id": str(fid), "target_b_id": "b", "kind": "cut"
            }).encode())
        )
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_missing_target_b_id(self):
        ctx, _, fid = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_surface_boolean(ctx, json.dumps({
                "file_id": str(fid), "target_a_id": "a", "kind": "fuse"
            }).encode())
        )
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_non_existent_file_returns_not_found(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        result = run_tool(ctx, fid,
                          target_a_id="a", target_b_id="b", kind="cut")
        assert result.get("code") == "NOT_FOUND"
