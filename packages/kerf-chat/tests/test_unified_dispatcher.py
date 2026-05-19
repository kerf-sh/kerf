"""
T-308: Unified tool dispatcher tests.

These tests verify that the dispatcher correctly routes catalog tool names
to their underlying implementations.  All DB / engine calls are mocked —
no real database or compute engines are required.
"""
from __future__ import annotations

import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Minimal ProjectCtx stub
# ---------------------------------------------------------------------------

class _FakePool:
    async def fetchrow(self, *a, **kw):
        return None

    async def fetchval(self, *a, **kw):
        return None

    async def fetch(self, *a, **kw):
        return []

    async def execute(self, *a, **kw):
        return None


class _FakeCtx:
    def __init__(self, role="editor"):
        import uuid
        self.pool = _FakePool()
        self.project_id = uuid.UUID(int=1)
        self.user_id = uuid.UUID(int=2)
        self.role = role
        self.storage = None
        self.file_revisions_max = 10
        self.http_client = MagicMock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _args(**kw) -> bytes:
    return json.dumps(kw).encode()


# ---------------------------------------------------------------------------
# Import the dispatcher module under test
# ---------------------------------------------------------------------------

from kerf_chat.tools.dispatcher import dispatch, _DISPATCH
from kerf_chat.tools.executor import execute


# ---------------------------------------------------------------------------
# 1. Unknown tool returns UNKNOWN_TOOL error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_unknown_tool_returns_error():
    ctx = _FakeCtx()
    result = await dispatch(ctx, "nonexistent_tool_xyz", b"{}")
    data = json.loads(result)
    assert data.get("code") == "UNKNOWN_TOOL"


# ---------------------------------------------------------------------------
# 2. run_compute(engine='fem') routes to run_fem_run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_compute_fem_routes_to_fem_run():
    ctx = _FakeCtx()
    fem_result = json.dumps({"job_id": "fem_test_123", "status": "queued"})

    mock_run_fem_run = AsyncMock(return_value=fem_result)

    with patch.dict("sys.modules", {"kerf_fem": types.ModuleType("kerf_fem")}):
        kerf_fem_tools = types.ModuleType("kerf_fem.tools")
        kerf_fem_tools.run_fem_run = mock_run_fem_run
        sys.modules["kerf_fem.tools"] = kerf_fem_tools

        result = await dispatch(ctx, "run_compute", _args(
            engine="fem",
            file_id="00000000-0000-0000-0000-000000000001",
            options={"solver": "linear_static"},
        ))

    data = json.loads(result)
    assert data.get("job_id") == "fem_test_123"
    mock_run_fem_run.assert_called_once()


# ---------------------------------------------------------------------------
# 3. run_compute(engine='cam') routes to run_cam_run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_compute_cam_routes_to_cam_run():
    ctx = _FakeCtx()
    cam_result = json.dumps({"job_id": "cam_abc", "status": "queued"})

    mock_run_cam_run = AsyncMock(return_value=cam_result)

    with patch.dict("sys.modules"):
        kerf_cam = types.ModuleType("kerf_cam")
        kerf_cam_tools = types.ModuleType("kerf_cam.tools")
        kerf_cam_tools.run_cam_run = mock_run_cam_run
        sys.modules["kerf_cam"] = kerf_cam
        sys.modules["kerf_cam.tools"] = kerf_cam_tools

        result = await dispatch(ctx, "run_compute", _args(
            engine="cam",
            file_id="00000000-0000-0000-0000-000000000002",
            options={"operation": "face"},
        ))

    data = json.loads(result)
    assert data.get("job_id") == "cam_abc"


# ---------------------------------------------------------------------------
# 4. run_compute with missing engine dep returns NOT_AVAILABLE
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_compute_missing_dep_returns_not_available():
    ctx = _FakeCtx()

    # Ensure kerf_tess is not importable.
    with patch.dict("sys.modules", {"kerf_tess": None, "kerf_tess.tools": None}):
        result = await dispatch(ctx, "run_compute", _args(
            engine="tess",
            file_id="00000000-0000-0000-0000-000000000003",
        ))

    data = json.loads(result)
    assert data.get("code") == "NOT_AVAILABLE"


# ---------------------------------------------------------------------------
# 5. run_compute with unknown engine returns BAD_ARGS
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_compute_unknown_engine():
    ctx = _FakeCtx()
    result = await dispatch(ctx, "run_compute", _args(
        engine="quantum",
        file_id="00000000-0000-0000-0000-000000000004",
    ))
    data = json.loads(result)
    assert data.get("code") == "BAD_ARGS"


# ---------------------------------------------------------------------------
# 6. poll_compute routes by job_id prefix
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_poll_compute_fem_prefix():
    ctx = _FakeCtx()
    fem_status_result = json.dumps({"job_id": "fem_abc", "status": "running"})
    mock_fem_status = AsyncMock(return_value=fem_status_result)

    with patch.dict("sys.modules"):
        kerf_fem_tools = types.ModuleType("kerf_fem.tools")
        kerf_fem_tools.run_fem_run = AsyncMock()
        kerf_fem_tools.run_fem_job_status = mock_fem_status
        sys.modules["kerf_fem.tools"] = kerf_fem_tools

        result = await dispatch(ctx, "poll_compute", _args(job_id="fem_abc"))

    data = json.loads(result)
    assert data.get("status") == "running"
    mock_fem_status.assert_called_once()


@pytest.mark.asyncio
async def test_poll_compute_unknown_prefix_returns_ok():
    """Unknown job_id prefix returns 'unknown' status (not an error)."""
    ctx = _FakeCtx()
    result = await dispatch(ctx, "poll_compute", _args(job_id="xyz_123"))
    data = json.loads(result)
    # Should not be an error — just an 'unknown' status.
    assert "error" not in data or data.get("status") == "unknown"
    assert data.get("job_id") == "xyz_123"


# ---------------------------------------------------------------------------
# 7. create_file dispatches by kind
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_file_sketch_kind():
    ctx = _FakeCtx()
    sketch_result = json.dumps({"path": "/test.sketch", "id": "abc"})
    mock_create_sketch = AsyncMock(return_value=sketch_result)

    with patch("kerf_api.tools.scaffold.run_create_sketch", mock_create_sketch):
        result = await dispatch(ctx, "create_file", _args(
            path="/test.sketch",
            kind="sketch",
            options={"plane": "XY"},
        ))

    data = json.loads(result)
    assert data.get("path") == "/test.sketch"
    mock_create_sketch.assert_called_once()


@pytest.mark.asyncio
async def test_create_file_circuit_kind():
    ctx = _FakeCtx()
    circuit_result = json.dumps({"path": "/main.circuit.tsx", "id": "ccc"})
    mock_create_circuit = AsyncMock(return_value=circuit_result)

    with patch("kerf_api.tools.scaffold.run_create_circuit", mock_create_circuit):
        result = await dispatch(ctx, "create_file", _args(
            path="/main.circuit.tsx",
            kind="circuit",
            options={"width_mm": 50, "height_mm": 30},
        ))

    data = json.loads(result)
    assert data.get("path") == "/main.circuit.tsx"


@pytest.mark.asyncio
async def test_create_file_invalid_kind():
    ctx = _FakeCtx()
    result = await dispatch(ctx, "create_file", _args(
        path="/test.xyz",
        kind="banana",
    ))
    data = json.loads(result)
    assert data.get("code") == "BAD_ARGS"


# ---------------------------------------------------------------------------
# 8. import_step renames source_url → url
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_import_step_renames_source_url():
    ctx = _FakeCtx()
    import_result = json.dumps({"path": "/part.step", "id": "sss"})
    mock_import_step = AsyncMock(return_value=import_result)

    with patch("kerf_api.tools.file_ops.run_import_step", mock_import_step):
        result = await dispatch(ctx, "import_step", _args(
            name="part.step",
            source_url="https://example.com/part.step",
        ))

    # Verify the underlying impl was called with url= instead of source_url=
    call_args = mock_import_step.call_args
    inner_bytes = call_args[0][1]
    inner = json.loads(inner_bytes)
    assert "url" in inner
    assert "source_url" not in inner


# ---------------------------------------------------------------------------
# 9. Viewer role is blocked from write tools via execute()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_viewer_blocked_from_write_tools():
    ctx = _FakeCtx(role="viewer")
    result = await execute(ctx, "write_file", _args(path="/x.jscad", content="..."))
    data = json.loads(result)
    assert data.get("code") == "FORBIDDEN"


# ---------------------------------------------------------------------------
# 10. Viewer role can use read tools via execute()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_viewer_can_use_read_file():
    ctx = _FakeCtx(role="viewer")
    # read_file will hit the DB and fail gracefully since pool is a stub.
    result = await execute(ctx, "read_file", _args(path="/main.jscad"))
    data = json.loads(result)
    # Should be NOT_FOUND (DB stub) not FORBIDDEN
    assert data.get("code") != "FORBIDDEN"


# ---------------------------------------------------------------------------
# 11. search_files remaps pattern → query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_files_remaps_pattern():
    ctx = _FakeCtx()
    search_result = json.dumps({"matches": []})
    mock_search = AsyncMock(return_value=search_result)

    with patch("kerf_api.tools.file_ops.run_search_code", mock_search):
        result = await dispatch(ctx, "search_files", _args(pattern="cube"))

    call_args = mock_search.call_args
    inner_bytes = call_args[0][1]
    inner = json.loads(inner_bytes)
    assert inner.get("query") == "cube"


# ---------------------------------------------------------------------------
# 12. edit_file with replace_all=true replaces all occurrences
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edit_file_replace_all_delegates_correctly():
    ctx = _FakeCtx()

    # Override resolve_path and pool to simulate a real file with 3 occurrences.
    file_content = "foo bar foo bar foo"
    ctx.pool.fetchrow = AsyncMock(return_value={"content": file_content})
    ctx.pool.execute = AsyncMock()

    from kerf_api.tools.file_ops import resolve_path as _resolve_path

    mock_resolve = AsyncMock(return_value={"exists": True, "id": "1", "kind": "file"})
    mock_revision = AsyncMock()

    # dispatch_edit_file imports resolve_path and record_revision_for_file
    # from kerf_api.tools.file_ops at call time; patch at that location.
    with patch("kerf_api.tools.file_ops.resolve_path", mock_resolve), \
         patch("kerf_api.tools.file_ops.record_revision_for_file", mock_revision):
        result = await dispatch(ctx, "edit_file", _args(
            path="/main.jscad",
            old_string="foo",
            new_string="baz",
            replace_all=True,
        ))

    data = json.loads(result)
    assert data.get("replaced") == 3


# ---------------------------------------------------------------------------
# 13. The _DISPATCH table contains exactly the catalog tool names
# ---------------------------------------------------------------------------

def test_dispatch_table_matches_catalog():
    from kerf_chat.tools.catalog import TOOL_CATALOG
    catalog_names = {t.name for t in TOOL_CATALOG}
    dispatch_names = set(_DISPATCH.keys())
    assert catalog_names == dispatch_names, (
        f"Catalog / dispatch mismatch.\n"
        f"  In catalog but not dispatch: {catalog_names - dispatch_names}\n"
        f"  In dispatch but not catalog: {dispatch_names - catalog_names}"
    )
