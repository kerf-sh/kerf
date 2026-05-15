"""
Tests for the sheet_metal_flange tool (T-1).

Pure-Python: no database, no OCCT, no ProjectCtx required for validation /
schema tests.  The integration tests that actually write a feature node use a
lightweight in-memory fake pool, identical to the pattern in test_feature_loft.py.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from kerf_cad_core.sheet_metal import (
    validate_flange_args,
    run_sheet_metal_flange,
    sheet_metal_flange_spec,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(initial_content: str = ""):
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


def _run_tool(ctx, file_id, **kwargs):
    a = {"file_id": str(file_id), **kwargs}
    raw = asyncio.new_event_loop().run_until_complete(
        run_sheet_metal_flange(ctx, json.dumps(a).encode())
    )
    return json.loads(raw)


# ---------------------------------------------------------------------------
# validate_flange_args — pure validation, no DB, no OCCT
# ---------------------------------------------------------------------------

class TestValidateFlangeArgs:
    """Unit-test the validation helper in isolation."""

    VALID = dict(
        edge_ref="top-front",
        flange_length=25.0,
        bend_angle_deg=90.0,
        bend_radius=2.0,
        thickness=1.5,
        k_factor=0.44,
        base_width=100.0,
        base_depth=80.0,
    )

    def _call(self, **overrides):
        kw = {**self.VALID, **overrides}
        return validate_flange_args(**kw)

    # --- Happy path ---

    def test_valid_90deg(self):
        err, code = self._call()
        assert err is None and code is None

    def test_valid_135deg(self):
        err, code = self._call(bend_angle_deg=135.0)
        assert err is None and code is None

    def test_valid_180deg_boundary(self):
        err, code = self._call(bend_angle_deg=180.0)
        assert err is None and code is None

    def test_k_factor_boundary_lo(self):
        # 0.01 is the practical minimum
        err, code = self._call(k_factor=0.01)
        assert err is None and code is None

    def test_k_factor_boundary_hi(self):
        err, code = self._call(k_factor=0.99)
        assert err is None and code is None

    # --- k_factor out of range ---

    def test_k_factor_zero_rejected(self):
        err, code = self._call(k_factor=0.0)
        assert err is not None
        assert code == "BAD_ARGS"
        assert "k_factor" in err

    def test_k_factor_one_rejected(self):
        err, code = self._call(k_factor=1.0)
        assert err is not None
        assert code == "BAD_ARGS"
        assert "k_factor" in err

    def test_k_factor_negative_rejected(self):
        err, code = self._call(k_factor=-0.1)
        assert err is not None
        assert code == "BAD_ARGS"

    def test_k_factor_gt_1_rejected(self):
        err, code = self._call(k_factor=1.5)
        assert err is not None
        assert code == "BAD_ARGS"

    # --- bend_angle_deg out of range ---

    def test_angle_zero_rejected(self):
        err, code = self._call(bend_angle_deg=0.0)
        assert err is not None
        assert code == "BAD_ARGS"
        assert "bend_angle_deg" in err

    def test_angle_negative_rejected(self):
        err, code = self._call(bend_angle_deg=-45.0)
        assert err is not None
        assert code == "BAD_ARGS"

    def test_angle_181_rejected(self):
        err, code = self._call(bend_angle_deg=181.0)
        assert err is not None
        assert code == "BAD_ARGS"

    # --- edge_ref required ---

    def test_empty_edge_ref_rejected(self):
        err, code = self._call(edge_ref="")
        assert err is not None
        assert code == "BAD_ARGS"
        assert "edge_ref" in err

    def test_whitespace_edge_ref_rejected(self):
        err, code = self._call(edge_ref="   ")
        assert err is not None
        assert code == "BAD_ARGS"

    # --- positive length / thickness / radius ---

    def test_flange_length_zero_rejected(self):
        err, code = self._call(flange_length=0.0)
        assert err is not None and code == "BAD_ARGS"
        assert "flange_length" in err

    def test_flange_length_negative_rejected(self):
        err, code = self._call(flange_length=-5.0)
        assert err is not None and code == "BAD_ARGS"

    def test_thickness_zero_rejected(self):
        err, code = self._call(thickness=0.0)
        assert err is not None and code == "BAD_ARGS"
        assert "thickness" in err

    def test_bend_radius_zero_rejected(self):
        err, code = self._call(bend_radius=0.0)
        assert err is not None and code == "BAD_ARGS"
        assert "bend_radius" in err

    def test_base_width_zero_rejected(self):
        err, code = self._call(base_width=0.0)
        assert err is not None and code == "BAD_ARGS"
        assert "base_width" in err

    def test_base_depth_negative_rejected(self):
        err, code = self._call(base_depth=-10.0)
        assert err is not None and code == "BAD_ARGS"
        assert "base_depth" in err


# ---------------------------------------------------------------------------
# ToolSpec schema check
# ---------------------------------------------------------------------------

class TestToolSpec:
    def test_name(self):
        assert sheet_metal_flange_spec.name == "sheet_metal_flange"

    def test_required_fields(self):
        req = sheet_metal_flange_spec.input_schema.get("required", [])
        for field in ["file_id", "edge_ref", "flange_length", "bend_angle_deg",
                      "bend_radius", "thickness", "base_width", "base_depth"]:
            assert field in req, f"'{field}' missing from required"

    def test_k_factor_in_properties(self):
        props = sheet_metal_flange_spec.input_schema.get("properties", {})
        assert "k_factor" in props

    def test_description_mentions_unfold_deferred(self):
        assert "T-2" in sheet_metal_flange_spec.description or \
               "unfold" in sheet_metal_flange_spec.description.lower()


# ---------------------------------------------------------------------------
# run_sheet_metal_flange — integration tests with fake DB
# ---------------------------------------------------------------------------

class TestRunSheetMetalFlange:

    def _make(self, **kw):
        ctx, store, fid = _make_ctx()
        result = _run_tool(
            ctx, fid,
            edge_ref=kw.get("edge_ref", "top-front"),
            flange_length=kw.get("flange_length", 25.0),
            bend_angle_deg=kw.get("bend_angle_deg", 90.0),
            bend_radius=kw.get("bend_radius", 2.0),
            thickness=kw.get("thickness", 1.5),
            k_factor=kw.get("k_factor", 0.44),
            base_width=kw.get("base_width", 100.0),
            base_depth=kw.get("base_depth", 80.0),
        )
        return result, store

    def test_success_minimal(self):
        result, store = self._make()
        # ok_payload returns the dict directly (no "ok" key);
        # absence of "error" key signals success.
        assert "error" not in result
        assert "op" in result

    def test_node_appended_to_file(self):
        result, store = self._make()
        assert "error" not in result
        doc = json.loads(store["content"])
        features = doc.get("features", [])
        assert len(features) == 1
        assert features[0]["op"] == "sheet_metal_flange"

    def test_node_id_auto_generated(self):
        _, store = self._make()
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["id"].startswith("sheet_metal_flange-")

    def test_all_params_stored(self):
        result, store = self._make(
            edge_ref="top-back",
            flange_length=30.0,
            bend_angle_deg=120.0,
            bend_radius=3.0,
            thickness=2.0,
            k_factor=0.38,
            base_width=150.0,
            base_depth=100.0,
        )
        assert "error" not in result
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["edge_ref"] == "top-back"
        assert node["flange_length"] == 30.0
        assert node["bend_angle_deg"] == 120.0
        assert node["bend_radius"] == 3.0
        assert node["thickness"] == 2.0
        assert abs(node["k_factor"] - 0.38) < 1e-9
        assert node["base_width"] == 150.0
        assert node["base_depth"] == 100.0

    def test_explicit_id(self):
        ctx, store, fid = _make_ctx()
        result = _run_tool(
            ctx, fid,
            id="my-flange-42",
            edge_ref="top-left",
            flange_length=10.0,
            bend_angle_deg=90.0,
            bend_radius=1.0,
            thickness=1.0,
            k_factor=0.44,
            base_width=60.0,
            base_depth=40.0,
        )
        assert "error" not in result
        doc = json.loads(store["content"])
        assert doc["features"][0]["id"] == "my-flange-42"

    def test_bad_file_id(self):
        ctx, _, _ = _make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_sheet_metal_flange(ctx, json.dumps({
                "file_id": "not-a-uuid",
                "edge_ref": "top-front",
                "flange_length": 10.0,
                "bend_angle_deg": 90.0,
                "bend_radius": 1.0,
                "thickness": 1.0,
                "k_factor": 0.44,
                "base_width": 50.0,
                "base_depth": 50.0,
            }).encode())
        )
        result = json.loads(raw)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_k_factor_one_rejected_via_runner(self):
        ctx, _, fid = _make_ctx()
        result = _run_tool(
            ctx, fid,
            edge_ref="top-front",
            flange_length=10.0,
            bend_angle_deg=90.0,
            bend_radius=1.0,
            thickness=1.0,
            k_factor=1.0,  # invalid
            base_width=50.0,
            base_depth=50.0,
        )
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_angle_0_rejected_via_runner(self):
        ctx, _, fid = _make_ctx()
        result = _run_tool(
            ctx, fid,
            edge_ref="top-front",
            flange_length=10.0,
            bend_angle_deg=0.0,  # invalid
            bend_radius=1.0,
            thickness=1.0,
            k_factor=0.44,
            base_width=50.0,
            base_depth=50.0,
        )
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_empty_edge_ref_rejected_via_runner(self):
        ctx, _, fid = _make_ctx()
        result = _run_tool(
            ctx, fid,
            edge_ref="",  # invalid
            flange_length=10.0,
            bend_angle_deg=90.0,
            bend_radius=1.0,
            thickness=1.0,
            k_factor=0.44,
            base_width=50.0,
            base_depth=50.0,
        )
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_second_node_gets_incremented_id(self):
        ctx, store, fid = _make_ctx()
        _run_tool(ctx, fid, edge_ref="top-front", flange_length=10.0,
                  bend_angle_deg=90.0, bend_radius=1.0, thickness=1.0,
                  k_factor=0.44, base_width=50.0, base_depth=50.0)
        _run_tool(ctx, fid, edge_ref="top-back", flange_length=10.0,
                  bend_angle_deg=90.0, bend_radius=1.0, thickness=1.0,
                  k_factor=0.44, base_width=50.0, base_depth=50.0)
        doc = json.loads(store["content"])
        ids = [f["id"] for f in doc["features"]]
        assert ids[0] == "sheet_metal_flange-1"
        assert ids[1] == "sheet_metal_flange-2"

    def test_response_contains_k_factor(self):
        result, _ = self._make(k_factor=0.33)
        assert "error" not in result
        assert abs(result["k_factor"] - 0.33) < 1e-9

    def test_response_note_mentions_unfold(self):
        result, _ = self._make()
        note = result.get("note", "")
        assert "unfold" in note.lower() or "T-2" in note
