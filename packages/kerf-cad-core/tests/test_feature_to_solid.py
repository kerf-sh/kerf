"""
Tests for the `feature_to_solid` backend LLM tool.

Pure-Python: no database required. All tests use a lightweight in-memory
FakePool/ctx, matching the pattern in test_feature_sweep1_mode.py.

Covers (~12 cases):
  - ToolSpec schema: name, required fields, optional tolerance.
  - Default values: tolerance defaults to 1e-6 when omitted.
  - Accepted tolerance overrides.
  - Node shape: stored JSON matches the tree node spec.
  - Error paths: invalid JSON, missing file_id, non-uuid file_id,
    missing target_id, non-existent file.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from kerf_cad_core.surfacing import (
    feature_to_solid_spec,
    run_feature_to_solid,
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
        run_feature_to_solid(ctx, json.dumps(args).encode())
    )
    return json.loads(raw)


# ---------------------------------------------------------------------------
# ToolSpec schema
# ---------------------------------------------------------------------------

class TestFeatureToSolidSpec:
    def test_spec_name(self):
        assert feature_to_solid_spec.name == "feature_to_solid"

    def test_required_fields(self):
        required = feature_to_solid_spec.input_schema.get("required", [])
        assert "file_id" in required
        assert "target_id" in required

    def test_tolerance_not_required(self):
        required = feature_to_solid_spec.input_schema.get("required", [])
        assert "options" not in required

    def test_tolerance_in_options_schema(self):
        props = feature_to_solid_spec.input_schema["properties"]
        assert "options" in props
        opts = props["options"]["properties"]
        assert "tolerance" in opts
        assert opts["tolerance"]["type"] == "number"

    def test_target_id_in_schema(self):
        props = feature_to_solid_spec.input_schema["properties"]
        assert "target_id" in props


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

class TestToSolidDefaults:
    def test_tolerance_defaults_to_1e_6(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, target_id="sweep1-1")
        assert result.get("error") is None
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["tolerance"] == pytest.approx(1e-6)

    def test_node_id_auto_generated(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_id="sweep1-1")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["id"].startswith("to_solid-")

    def test_explicit_id_in_options(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_id="sweep1-1", options={"id": "to_solid-custom"})
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["id"] == "to_solid-custom"


# ---------------------------------------------------------------------------
# Tolerance overrides
# ---------------------------------------------------------------------------

class TestToSolidToleranceOverride:
    def test_custom_tolerance_stored(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_id="sweep1-1", options={"tolerance": 1e-4})
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["tolerance"] == pytest.approx(1e-4)

    def test_zero_tolerance_ignored_uses_default(self):
        # tolerance=0 is not positive so fallback to 1e-6
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_id="sweep1-1", options={"tolerance": 0})
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["tolerance"] == pytest.approx(1e-6)


# ---------------------------------------------------------------------------
# Node shape
# ---------------------------------------------------------------------------

class TestToSolidNodeShape:
    def test_node_op_is_to_solid(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_id="blend_srf-1")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["op"] == "to_solid"

    def test_target_id_stored(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_id="network_srf-2")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["target_id"] == "network_srf-2"

    def test_result_payload_contains_op(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, target_id="loft-1")
        assert result.get("op") == "to_solid"
        assert result.get("id", "").startswith("to_solid-")


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

class TestToSolidErrors:
    def test_invalid_json_args(self):
        ctx, _, _ = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_to_solid(ctx, b"not json")
        )
        result = json.loads(raw)
        assert result.get("error") is not None
        assert result.get("code") == "BAD_ARGS"

    def test_missing_file_id(self):
        ctx, _, _ = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_to_solid(ctx, json.dumps({"target_id": "x"}).encode())
        )
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_non_uuid_file_id(self):
        ctx, _, _ = make_ctx()
        result = run_tool(ctx, "not-a-uuid", target_id="x")
        assert result.get("code") == "BAD_ARGS"

    def test_missing_target_id(self):
        ctx, _, fid = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_to_solid(ctx, json.dumps({"file_id": str(fid)}).encode())
        )
        result = json.loads(raw)
        assert result.get("code") == "BAD_ARGS"

    def test_non_existent_file_returns_not_found(self):
        ctx, _, fid = make_ctx(kind="NOT_FOUND")
        result = run_tool(ctx, fid, target_id="sweep1-1")
        assert result.get("code") == "NOT_FOUND"
