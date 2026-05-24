"""GK-P46 wiring test: mesh/implicit ToolSpec dispatch + FeatureView entries."""
from __future__ import annotations

import json
import pathlib
import uuid

import pytest

try:
    import kerf_cad_core.mesh_implicit_tools  # noqa: F401
    _HAS_MESH_TOOLS = True
except ImportError:
    _HAS_MESH_TOOLS = False

_WORKTREE = pathlib.Path(__file__).parents[3]
_FEATURE_VIEW = _WORKTREE / "src" / "components" / "FeatureView.jsx"


def _fv() -> str:
    return _FEATURE_VIEW.read_text(encoding="utf-8")


def _registered(name: str) -> bool:
    from kerf_chat.tools.registry import Registry  # type: ignore
    return any(t.spec.name == name for t in Registry)


# FeatureView presence
def test_sdf_csg_in_feature_view():
    assert "sdf_csg" in _fv()

def test_uv_unwrap_in_feature_view():
    assert "uv_unwrap" in _fv()

def test_isotropic_remesh_in_feature_view():
    assert "isotropic_remesh" in _fv()

def test_retopo_snap_in_feature_view():
    assert "retopo_snap" in _fv()


# ToolSpec registration
@pytest.mark.skipif(not _HAS_MESH_TOOLS, reason="mesh_implicit_tools not importable")
def test_sdf_csg_registered():
    import kerf_cad_core.mesh_implicit_tools
    assert _registered("feature_sdf_csg")

@pytest.mark.skipif(not _HAS_MESH_TOOLS, reason="mesh_implicit_tools not importable")
def test_uv_unwrap_registered():
    import kerf_cad_core.mesh_implicit_tools
    assert _registered("feature_uv_unwrap")

@pytest.mark.skipif(not _HAS_MESH_TOOLS, reason="mesh_implicit_tools not importable")
def test_isotropic_remesh_registered():
    import kerf_cad_core.mesh_implicit_tools
    assert _registered("feature_isotropic_remesh")

@pytest.mark.skipif(not _HAS_MESH_TOOLS, reason="mesh_implicit_tools not importable")
def test_retopo_snap_registered():
    import kerf_cad_core.mesh_implicit_tools
    assert _registered("feature_retopo_snap")


# Schema sanity
@pytest.mark.skipif(not _HAS_MESH_TOOLS, reason="mesh_implicit_tools not importable")
def test_sdf_csg_schema_primitives_required():
    import kerf_cad_core.mesh_implicit_tools as m
    schema = m.feature_sdf_csg_spec.input_schema
    assert "primitives" in schema.get("required", [])

@pytest.mark.skipif(not _HAS_MESH_TOOLS, reason="mesh_implicit_tools not importable")
def test_isotropic_remesh_schema():
    import kerf_cad_core.mesh_implicit_tools as m
    schema = m.feature_isotropic_remesh_spec.input_schema
    required = schema.get("required", [])
    assert "file_id" in required
    assert "target_id" in required
    assert "target_edge_length" in required


# Dispatch error cases
@pytest.mark.skipif(not _HAS_MESH_TOOLS, reason="mesh_implicit_tools not importable")
def test_sdf_csg_bad_resolution():
    import asyncio
    import kerf_cad_core.mesh_implicit_tools as m

    class _FakePool:
        def fetchone(self, *a, **kw): return None

    class _FakeCtx:
        pool = _FakePool()
        project_id = uuid.uuid4()

    result = asyncio.get_event_loop().run_until_complete(
        m.run_feature_sdf_csg(
            _FakeCtx(),
            json.dumps({
                "file_id": str(uuid.uuid4()),
                "primitives": [{"type": "sphere", "id": "s1", "cx": 0, "cy": 0, "cz": 0, "r": 5}],
                "resolution": 999,  # out of range
            }).encode(),
        )
    )
    payload = json.loads(result)
    assert payload.get("code") == "BAD_ARGS"

@pytest.mark.skipif(not _HAS_MESH_TOOLS, reason="mesh_implicit_tools not importable")
def test_retopo_snap_missing_source():
    import asyncio
    import kerf_cad_core.mesh_implicit_tools as m

    class _FakePool:
        def fetchone(self, *a, **kw): return None

    class _FakeCtx:
        pool = _FakePool()
        project_id = uuid.uuid4()

    result = asyncio.get_event_loop().run_until_complete(
        m.run_feature_retopo_snap(
            _FakeCtx(),
            json.dumps({
                "file_id": str(uuid.uuid4()),
                "retopo_cage_id": "cage-1",
                # missing source_mesh_id
            }).encode(),
        )
    )
    payload = json.loads(result)
    assert payload.get("code") == "BAD_ARGS"
