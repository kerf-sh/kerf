"""
Tests for the `feature_surface_curvature_combs` backend LLM tool
(NURBS Phase 4 Capability 4).

Pure-Python: no database required.  All tests use a lightweight in-memory
FakePool/ctx, matching the pattern in test_feature_surface_boolean.py.

Covers (~10 cases):
  - ToolSpec schema: name, required fields (file_id, target_feature_ref).
  - Schema: target_feature_ref required; target_face_name optional.
  - Schema: uv_density and scale_factor are optional numeric fields.
  - Node shape: stored JSON has op == "surface_curvature_combs".
  - Defaults: show_combs stored when provided; absent when not provided.
  - uv_density: zero/negative rejected; > 0.5 rejected; valid value stored.
  - scale_factor: zero/negative rejected; valid value stored.
  - Error paths: invalid JSON, missing required fields, non-uuid file_id,
    non-existent file.
  - options.id: explicit id stored; auto-generated id prefixed "surface_curvature_combs-".
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from kerf_cad_core.surfacing import (
    feature_surface_curvature_combs_spec,
    run_feature_surface_curvature_combs,
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
        run_feature_surface_curvature_combs(ctx, json.dumps(args).encode())
    )
    return json.loads(raw)


# ---------------------------------------------------------------------------
# ToolSpec schema
# ---------------------------------------------------------------------------

class TestFeatureSurfaceCurvatureCombsSpec:
    def test_spec_name(self):
        assert feature_surface_curvature_combs_spec.name == "feature_surface_curvature_combs"

    def test_required_fields(self):
        required = feature_surface_curvature_combs_spec.input_schema.get("required", [])
        assert "file_id" in required
        assert "target_feature_ref" in required

    def test_target_face_name_not_required(self):
        required = feature_surface_curvature_combs_spec.input_schema.get("required", [])
        assert "target_face_name" not in required

    def test_uv_density_is_optional_number(self):
        props = feature_surface_curvature_combs_spec.input_schema["properties"]
        assert "uv_density" in props
        assert props["uv_density"]["type"] == "number"
        required = feature_surface_curvature_combs_spec.input_schema.get("required", [])
        assert "uv_density" not in required

    def test_scale_factor_is_optional_number(self):
        props = feature_surface_curvature_combs_spec.input_schema["properties"]
        assert "scale_factor" in props
        assert props["scale_factor"]["type"] == "number"
        required = feature_surface_curvature_combs_spec.input_schema.get("required", [])
        assert "scale_factor" not in required

    def test_show_combs_is_optional_boolean(self):
        props = feature_surface_curvature_combs_spec.input_schema["properties"]
        assert "show_combs" in props
        assert props["show_combs"]["type"] == "boolean"


# ---------------------------------------------------------------------------
# Node shape
# ---------------------------------------------------------------------------

class TestCurvatureCombsNodeShape:
    def test_op_is_surface_curvature_combs(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_feature_ref="blend_srf-1")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["op"] == "surface_curvature_combs"

    def test_target_feature_ref_stored(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_feature_ref="sweep1-2")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["target_feature_ref"] == "sweep1-2"

    def test_auto_id_prefix(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_feature_ref="blend_srf-1")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["id"].startswith("surface_curvature_combs-")

    def test_explicit_options_id_stored(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_feature_ref="blend_srf-1",
                 options={"id": "my-combs-node"})
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["id"] == "my-combs-node"


# ---------------------------------------------------------------------------
# Optional fields
# ---------------------------------------------------------------------------

class TestCurvatureCombsOptionalFields:
    def test_uv_density_stored_when_provided(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_feature_ref="blend_srf-1", uv_density=0.05)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["uv_density"] == pytest.approx(0.05)

    def test_uv_density_absent_when_not_provided(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_feature_ref="blend_srf-1")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert "uv_density" not in node

    def test_scale_factor_stored_when_provided(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_feature_ref="sweep1-1", scale_factor=20.0)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["scale_factor"] == pytest.approx(20.0)

    def test_show_combs_false_stored(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_feature_ref="blend_srf-1", show_combs=False)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["show_combs"] is False

    def test_target_face_name_stored_when_provided(self):
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_feature_ref="network_srf-1",
                 target_face_name="face-0")
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["target_face_name"] == "face-0"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class TestCurvatureCombsValidation:
    def test_uv_density_zero_rejected(self):
        ctx, _store, fid = make_ctx()
        result = run_tool(ctx, fid, target_feature_ref="blend_srf-1",
                          uv_density=0)
        assert result.get("error") is not None
        assert result.get("code") == "BAD_ARGS"

    def test_uv_density_negative_rejected(self):
        ctx, _store, fid = make_ctx()
        result = run_tool(ctx, fid, target_feature_ref="blend_srf-1",
                          uv_density=-0.1)
        assert result.get("error") is not None
        assert result.get("code") == "BAD_ARGS"

    def test_uv_density_too_large_rejected(self):
        ctx, _store, fid = make_ctx()
        result = run_tool(ctx, fid, target_feature_ref="blend_srf-1",
                          uv_density=0.6)
        assert result.get("error") is not None
        assert result.get("code") == "BAD_ARGS"

    def test_scale_factor_zero_rejected(self):
        ctx, _store, fid = make_ctx()
        result = run_tool(ctx, fid, target_feature_ref="blend_srf-1",
                          scale_factor=0)
        assert result.get("error") is not None
        assert result.get("code") == "BAD_ARGS"

    def test_scale_factor_negative_rejected(self):
        ctx, _store, fid = make_ctx()
        result = run_tool(ctx, fid, target_feature_ref="blend_srf-1",
                          scale_factor=-5)
        assert result.get("error") is not None
        assert result.get("code") == "BAD_ARGS"

    def test_missing_target_feature_ref_rejected(self):
        ctx, _store, fid = make_ctx()
        result = run_tool(ctx, fid)  # no target_feature_ref
        assert result.get("error") is not None
        assert result.get("code") == "BAD_ARGS"

    def test_non_uuid_file_id_rejected(self):
        ctx, _store, _fid = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_surface_curvature_combs(
                ctx,
                json.dumps({
                    "file_id": "not-a-uuid",
                    "target_feature_ref": "blend_srf-1",
                }).encode()
            )
        )
        result = json.loads(raw)
        assert result.get("error") is not None
        assert result.get("code") == "BAD_ARGS"

    def test_not_found_file_returns_not_found(self):
        ctx, store, fid = make_ctx()
        store["kind"] = "NOT_FOUND"
        result = run_tool(ctx, fid, target_feature_ref="blend_srf-1")
        assert result.get("error") is not None
        assert result.get("code") == "NOT_FOUND"

    def test_invalid_json_args_rejected(self):
        ctx, _store, _fid = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_feature_surface_curvature_combs(ctx, b"{not valid json}")
        )
        result = json.loads(raw)
        assert result.get("error") is not None
