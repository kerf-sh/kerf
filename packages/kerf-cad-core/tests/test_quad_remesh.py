"""
Tests for the quad_remesh tool and instant_meshes_runner helpers.

All tests are pure-Python — no database, no OCC, no binary required.
OBJ parser, schema validation, and graceful-degradation paths are covered.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(initial_content: str = ""):
    """Return (ctx, store, file_id) with an in-memory fake pool."""
    store = {
        "content": initial_content or json.dumps({"version": 1, "features": []}),
        "kind": "feature",
    }
    project_id = uuid.uuid4()
    file_id    = uuid.uuid4()

    class FakePool:
        async def fetchrow(self, query, *args):
            return {"content": store["content"], "kind": store["kind"]}

        def execute(self, query, *args):
            # Called synchronously from append_feature_node / read_feature_content.
            # args[0] is new content when writing.
            if args:
                store["content"] = args[0]

        def fetchone(self, query, *args):
            return (store["content"], store["kind"])

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
    from kerf_cad_core.quad_remesh import run_quad_remesh

    args = {"file_id": str(file_id), **kwargs}
    loop = asyncio.new_event_loop()
    try:
        raw = loop.run_until_complete(
            run_quad_remesh(ctx, json.dumps(args).encode())
        )
    finally:
        loop.close()
    return json.loads(raw)


# ---------------------------------------------------------------------------
# instant_meshes_runner — OBJ parser
# ---------------------------------------------------------------------------

class TestObjParser:
    def test_empty_string(self):
        from kerf_cad_core.instant_meshes_runner import _parse_obj
        v, q, t = _parse_obj("")
        assert v == [] and q == [] and t == []

    def test_comment_only(self):
        from kerf_cad_core.instant_meshes_runner import _parse_obj
        v, q, t = _parse_obj("# just a comment\n")
        assert v == [] and q == [] and t == []

    def test_vertices_parsed(self):
        from kerf_cad_core.instant_meshes_runner import _parse_obj
        obj = "v 1.0 2.0 3.0\nv -1 0 0\n"
        v, q, t = _parse_obj(obj)
        assert len(v) == 2
        assert v[0] == pytest.approx([1.0, 2.0, 3.0])
        assert v[1] == pytest.approx([-1.0, 0.0, 0.0])

    def test_triangle_faces_parsed(self):
        from kerf_cad_core.instant_meshes_runner import _parse_obj
        obj = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
        v, q, t = _parse_obj(obj)
        assert len(t) == 1
        assert t[0] == [0, 1, 2]  # 0-based conversion

    def test_quad_faces_parsed(self):
        from kerf_cad_core.instant_meshes_runner import _parse_obj
        obj = "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n"
        v, q, t = _parse_obj(obj)
        assert len(q) == 1
        assert q[0] == [0, 1, 2, 3]
        assert t == []

    def test_slash_notation_stripped(self):
        from kerf_cad_core.instant_meshes_runner import _parse_obj
        # f v/vt/vn notation — only vertex index used
        obj = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1/1/1 2/2/1 3/3/1\n"
        v, q, t = _parse_obj(obj)
        assert t == [[0, 1, 2]]

    def test_mixed_faces(self):
        from kerf_cad_core.instant_meshes_runner import _parse_obj
        obj = (
            "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nv 0.5 0.5 1\n"
            "f 1 2 3 4\n"   # quad
            "f 1 2 5\n"     # tri
        )
        v, q, t = _parse_obj(obj)
        assert len(q) == 1
        assert len(t) == 1

    def test_bad_vertex_line_ignored(self):
        from kerf_cad_core.instant_meshes_runner import _parse_obj
        obj = "v 0 0\n"  # only 2 coords — ignored
        v, q, t = _parse_obj(obj)
        assert v == []

    def test_bad_face_index_ignored(self):
        from kerf_cad_core.instant_meshes_runner import _parse_obj
        obj = "v 0 0 0\nf bad_idx 2 3\n"
        # Should not raise; bad token skipped
        try:
            v, q, t = _parse_obj(obj)
        except Exception:
            pytest.fail("_parse_obj raised on bad face index")


# ---------------------------------------------------------------------------
# instant_meshes_runner — InstantMeshesNotInstalledError
# ---------------------------------------------------------------------------

class TestBinaryMissing:
    def test_raises_when_binary_absent(self, tmp_path):
        from kerf_cad_core.instant_meshes_runner import (
            InstantMeshesNotInstalledError,
            run_instant_meshes,
            BINARY_NAME,
        )
        import shutil
        if shutil.which(BINARY_NAME) is not None:
            pytest.skip("instant-meshes is installed — skipping missing-binary test")

        obj_path = tmp_path / "test.obj"
        obj_path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")

        with pytest.raises(InstantMeshesNotInstalledError):
            run_instant_meshes(str(obj_path))

    def test_error_message_contains_install_hint(self, tmp_path):
        from kerf_cad_core.instant_meshes_runner import (
            InstantMeshesNotInstalledError,
            run_instant_meshes,
            BINARY_NAME,
        )
        import shutil
        if shutil.which(BINARY_NAME) is not None:
            pytest.skip("instant-meshes is installed — skipping missing-binary test")

        obj_path = tmp_path / "test.obj"
        obj_path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")

        try:
            run_instant_meshes(str(obj_path))
        except InstantMeshesNotInstalledError as exc:
            assert "instant-meshes" in str(exc).lower()
            assert "github.com" in str(exc)


# ---------------------------------------------------------------------------
# quad_remesh tool — schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_missing_file_id(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, target_feature_ref="pad-1")
        # file_id is passed — but test with empty string
        args = {"file_id": "", "target_feature_ref": "pad-1"}
        import asyncio
        from kerf_cad_core.quad_remesh import run_quad_remesh
        loop = asyncio.new_event_loop()
        raw = loop.run_until_complete(run_quad_remesh(ctx, json.dumps(args).encode()))
        loop.close()
        r = json.loads(raw)
        assert r.get("error") or r.get("status") == "error"

    def test_missing_target_feature_ref(self):
        from kerf_cad_core.quad_remesh import run_quad_remesh
        ctx, store, fid = make_ctx()
        args = {"file_id": str(fid), "target_feature_ref": ""}
        loop = asyncio.new_event_loop()
        raw = loop.run_until_complete(run_quad_remesh(ctx, json.dumps(args).encode()))
        loop.close()
        r = json.loads(raw)
        assert r.get("error") or r.get("status") == "error"

    def test_invalid_file_id(self):
        from kerf_cad_core.quad_remesh import run_quad_remesh
        ctx, store, fid = make_ctx()
        args = {"file_id": "not-a-uuid", "target_feature_ref": "pad-1"}
        loop = asyncio.new_event_loop()
        raw = loop.run_until_complete(run_quad_remesh(ctx, json.dumps(args).encode()))
        loop.close()
        r = json.loads(raw)
        assert r.get("error") or r.get("status") == "error"

    def test_invalid_json_args(self):
        from kerf_cad_core.quad_remesh import run_quad_remesh
        ctx, store, fid = make_ctx()
        loop = asyncio.new_event_loop()
        raw = loop.run_until_complete(run_quad_remesh(ctx, b"not json"))
        loop.close()
        r = json.loads(raw)
        assert r.get("error") or r.get("status") == "error"

    def test_smoothness_out_of_range(self):
        from kerf_cad_core.quad_remesh import run_quad_remesh
        ctx, store, fid = make_ctx()
        args = {"file_id": str(fid), "target_feature_ref": "pad-1", "smoothness_iters": 99}
        loop = asyncio.new_event_loop()
        raw = loop.run_until_complete(run_quad_remesh(ctx, json.dumps(args).encode()))
        loop.close()
        r = json.loads(raw)
        assert r.get("error") or r.get("status") == "error"

    def test_target_vertex_count_zero(self):
        from kerf_cad_core.quad_remesh import run_quad_remesh
        ctx, store, fid = make_ctx()
        args = {"file_id": str(fid), "target_feature_ref": "pad-1", "target_vertex_count": 0}
        loop = asyncio.new_event_loop()
        raw = loop.run_until_complete(run_quad_remesh(ctx, json.dumps(args).encode()))
        loop.close()
        r = json.loads(raw)
        assert r.get("error") or r.get("status") == "error"


# ---------------------------------------------------------------------------
# quad_remesh tool — graceful degradation (binary missing)
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    def test_binary_missing_returns_ok_payload_with_warning(self):
        """
        When instant-meshes is absent the tool must return ok_payload (not raise)
        with status='binary_missing' so the chat agent can surface a friendly message.
        """
        from kerf_cad_core.instant_meshes_runner import BINARY_NAME
        import shutil

        if shutil.which(BINARY_NAME) is not None:
            pytest.skip("instant-meshes is installed — skipping degradation test")

        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, target_feature_ref="pad-1")

        # Should be an ok_payload (not an error_payload) — the chat agent
        # receives a structured response with hint, not a crash.
        assert "result" in result or "status" in result
        # Unwrap nested result if ok_payload wraps it.
        inner = result.get("result", result)
        assert inner.get("status") == "binary_missing"
        assert "hint" in inner
        assert "warning" in inner

    def test_binary_missing_hint_contains_url(self):
        from kerf_cad_core.instant_meshes_runner import BINARY_NAME
        import shutil

        if shutil.which(BINARY_NAME) is not None:
            pytest.skip("instant-meshes is installed")

        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, target_feature_ref="pad-1")
        inner = result.get("result", result)
        hint = inner.get("hint", "")
        assert "instant-meshes" in hint.lower() or "github.com" in hint

    def test_node_is_appended_even_when_binary_missing(self):
        """
        The feature node must be appended to the file content even when the
        binary isn't available — the structural record is committed regardless.
        """
        from kerf_cad_core.instant_meshes_runner import BINARY_NAME
        import shutil

        if shutil.which(BINARY_NAME) is not None:
            pytest.skip("instant-meshes is installed")

        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_feature_ref="pad-1")

        doc = json.loads(store["content"])
        ops = [f["op"] for f in doc.get("features", [])]
        assert "quad_remesh" in ops


# ---------------------------------------------------------------------------
# quad_remesh tool — spec registration
# ---------------------------------------------------------------------------

class TestSpecRegistration:
    def test_spec_has_correct_name(self):
        from kerf_cad_core.quad_remesh import quad_remesh_spec
        assert quad_remesh_spec.name == "feature_quad_remesh"

    def test_spec_requires_file_id(self):
        from kerf_cad_core.quad_remesh import quad_remesh_spec
        assert "file_id" in quad_remesh_spec.input_schema["required"]

    def test_spec_requires_target_feature_ref(self):
        from kerf_cad_core.quad_remesh import quad_remesh_spec
        assert "target_feature_ref" in quad_remesh_spec.input_schema["required"]

    def test_spec_has_target_vertex_count_property(self):
        from kerf_cad_core.quad_remesh import quad_remesh_spec
        props = quad_remesh_spec.input_schema["properties"]
        assert "target_vertex_count" in props
        assert props["target_vertex_count"]["default"] == 5000

    def test_spec_has_smoothness_iters_property(self):
        from kerf_cad_core.quad_remesh import quad_remesh_spec
        props = quad_remesh_spec.input_schema["properties"]
        assert "smoothness_iters" in props
        assert props["smoothness_iters"]["default"] == 2

    def test_spec_has_align_to_boundary_property(self):
        from kerf_cad_core.quad_remesh import quad_remesh_spec
        props = quad_remesh_spec.input_schema["properties"]
        assert "align_to_boundary" in props
        assert props["align_to_boundary"]["default"] is True

    def test_spec_has_crease_angle_deg_property(self):
        from kerf_cad_core.quad_remesh import quad_remesh_spec
        props = quad_remesh_spec.input_schema["properties"]
        assert "crease_angle_deg" in props
        assert props["crease_angle_deg"]["default"] == 20.0


# ---------------------------------------------------------------------------
# instant_meshes_runner — build_cli helper
# ---------------------------------------------------------------------------

class TestCLIBuilder:
    def test_cli_with_boundaries(self):
        from kerf_cad_core.instant_meshes_runner import _build_cli
        cmd = _build_cli("/in.obj", "/out.obj", 5000, 2, True)
        assert "--boundaries" in cmd

    def test_cli_without_boundaries(self):
        from kerf_cad_core.instant_meshes_runner import _build_cli
        cmd = _build_cli("/in.obj", "/out.obj", 5000, 2, False)
        assert "--boundaries" not in cmd

    def test_cli_target_verts(self):
        from kerf_cad_core.instant_meshes_runner import _build_cli
        cmd = _build_cli("/in.obj", "/out.obj", 3000, 1, False)
        v_idx = cmd.index("-v")
        assert cmd[v_idx + 1] == "3000"

    def test_cli_smoothness(self):
        from kerf_cad_core.instant_meshes_runner import _build_cli
        cmd = _build_cli("/in.obj", "/out.obj", 5000, 4, False)
        s_idx = cmd.index("-s")
        assert cmd[s_idx + 1] == "4"

    def test_cli_input_output_present(self):
        from kerf_cad_core.instant_meshes_runner import _build_cli, BINARY_NAME
        cmd = _build_cli("/in.obj", "/out.obj", 5000, 2, False)
        assert cmd[0] == BINARY_NAME
        assert "/in.obj" in cmd
        assert "/out.obj" in cmd
