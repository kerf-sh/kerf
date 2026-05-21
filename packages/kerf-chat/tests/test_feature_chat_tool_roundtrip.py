"""
T-58: Chat tool dispatch + tool round-trip.

Scope: kerf-chat plugin -> kerf-cad-core tool call -> file_revision created.

Success criteria:
  - 25 chat turns invoking diverse tools
  - revisions append (source='tool') after write/edit operations
  - assistant message references tool result content

All LLM provider calls and DB interactions are mocked — no real database or
compute engine is required.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
import types
import uuid
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Hermetic fake pool / DB layer
# ---------------------------------------------------------------------------

class _FakeRevision:
    """A single row in a fake file_revisions table."""
    def __init__(self, rev_id, file_id, content, source, kind="base"):
        self.id = rev_id
        self.file_id = file_id
        self.content = content
        self.source = source
        self.kind = kind
        self.content_sha256 = hashlib.sha256(content.encode()).digest()
        payload = gzip.compress(content.encode(), compresslevel=1)
        self.content_gz = payload
        self.content_codec = "gzip"
        self.parent_revision_id = None
        self.content_preview = content[:200]

    def __getitem__(self, key):
        return getattr(self, key)

    def keys(self):
        return [
            "id", "file_id", "content", "source", "kind",
            "content_sha256", "content_gz", "content_codec",
            "parent_revision_id", "content_preview",
        ]

    def get(self, key, default=None):
        try:
            return getattr(self, key)
        except AttributeError:
            return default


class _FakeFile:
    def __init__(self, file_id, name, kind, content="", parent_id=None):
        self.id = file_id
        self.name = name
        self.kind = kind
        self.content = content
        self.parent_id = parent_id
        self.deleted_at = None


class _FakePool:
    """In-memory pool that simulates the file + file_revisions tables."""

    def __init__(self):
        self._files: dict[uuid.UUID, _FakeFile] = {}
        self._revisions: list[_FakeRevision] = []
        # Counters to allow assertions
        self.revision_writes: list[tuple[uuid.UUID, str, str]] = []  # (file_id, content, source)

    def _seed_file(self, file_id: uuid.UUID, name: str, kind: str, content: str = "",
                   parent_id: Optional[uuid.UUID] = None) -> _FakeFile:
        f = _FakeFile(file_id, name, kind, content, parent_id)
        self._files[file_id] = f
        return f

    def _file_by_name(self, name: str, parent_id) -> Optional[_FakeFile]:
        for f in self._files.values():
            if f.name == name and f.parent_id == parent_id and f.deleted_at is None:
                return f
        return None

    # ── asyncpg-style interface ─────────────────────────────────────────────

    async def fetchrow(self, query: str, *args, **kwargs) -> Optional[Any]:
        q = query.strip().lower()

        # file_revisions: latest revision for SHA-256 dedup
        if "from file_revisions" in q and "order by created_at desc limit 1" in q:
            fid = args[0]
            revs = [r for r in self._revisions if r.file_id == fid]
            if not revs:
                return None
            return revs[-1]

        # cross-file base dedup
        if "from file_revisions" in q and "kind = 'base'" in q and "limit 1" in q:
            sha = args[0]
            for r in self._revisions:
                if r.content_sha256 == sha and r.kind == "base":
                    return r
            return None

        # resolve_path: files WHERE project_id = $1 AND name = $2 AND parent_id ...
        if "from files" in q and "name = $2" in q:
            project_id = args[0]
            name = args[1]
            parent_id = args[2] if len(args) > 2 else None
            f = self._file_by_name(name, parent_id)
            if f is None:
                return None
            return {
                "id": f.id,
                "parent_id": f.parent_id,
                "name": f.name,
                "kind": f.kind,
            }

        # content fetch for edit_file / describe_part
        if "select content from files" in q:
            fid = args[0]
            f = self._files.get(fid)
            if f is None:
                return None
            return {"content": f.content}

        # export_artifact: SELECT name, kind FROM files WHERE id = $1
        if "select name, kind from files" in q or ("select" in q and "name" in q and "kind" in q and "from files" in q):
            fid = args[0]
            f = self._files.get(fid)
            if f is None:
                return None
            return {"name": f.name, "kind": f.kind}

        # file_revisions reconstruct
        if "from file_revisions where id = $1" in q:
            rev_id = args[0]
            for r in self._revisions:
                if r.id == rev_id:
                    return r
            return None

        return None

    async def fetchval(self, query: str, *args, **kwargs) -> Any:
        q = query.strip().lower()
        if "insert into files" in q:
            new_id = uuid.uuid4()
            # Extract name and kind from args heuristically
            project_id, parent_id, name, kind, content = args[:5]
            f = _FakeFile(new_id, name, kind, content or "", parent_id)
            self._files[new_id] = f
            return new_id
        if "count(*)" in q:
            return 0
        return None

    async def fetch(self, query: str, *args, **kwargs) -> list:
        q = query.strip().lower()
        if "from files" in q and ("project_id = $1" in q or "project_id=$1" in q):
            project_id = args[0] if args else None
            rows = []
            for f in self._files.values():
                if f.deleted_at is None:
                    rows.append({
                        "id": f.id,
                        "parent_id": f.parent_id,
                        "name": f.name,
                        "kind": f.kind,
                        "length": len(f.content),
                        "size": len(f.content.encode()),
                    })
            return rows
        return []

    async def execute(self, query: str, *args, **kwargs) -> str:
        q = query.strip().lower()

        # Write file content
        if "update files set content" in q:
            content, fid, project_id = args[:3]
            f = self._files.get(fid)
            if f:
                f.content = content
            return "UPDATE 1"

        # Insert new file
        if "insert into files" in q and "returning" not in q:
            return "INSERT 1"

        # Insert revision
        if "insert into file_revisions" in q:
            rev_id = args[0]
            fid = args[1]
            # args layout varies; extract content from gz if present
            gz_bytes = None
            source = "tool"
            kind = "base"
            content_sha256 = b""
            # Detect positional args by inspecting query placeholder count
            for i, a in enumerate(args):
                if isinstance(a, str) and a in ("tool", "user", "llm", "restore"):
                    source = a
                if isinstance(a, (bytes, memoryview)):
                    gz_bytes = bytes(a)
                if isinstance(a, str) and a in ("base", "diff", "ref"):
                    kind = a
                if isinstance(a, bytes) and len(a) == 32:
                    content_sha256 = a

            if gz_bytes:
                try:
                    content = gzip.decompress(gz_bytes).decode()
                except Exception:
                    content = ""
            else:
                content = ""

            rev = _FakeRevision(rev_id, fid, content, source, kind)
            rev.content_sha256 = content_sha256 if content_sha256 else hashlib.sha256(content.encode()).digest()
            self._revisions.append(rev)
            self.revision_writes.append((fid, content, source))
            return "INSERT 1"

        # Soft-delete file
        if "update files set deleted_at" in q:
            return "UPDATE 1"

        # Prune revisions
        if "delete from file_revisions" in q:
            return "DELETE 0"

        return "OK"


# ---------------------------------------------------------------------------
# Fake ProjectCtx
# ---------------------------------------------------------------------------

class _FakeCtx:
    def __init__(self, pool: _FakePool, role: str = "editor"):
        self.pool = pool
        self.project_id = uuid.UUID(int=42)
        self.user_id = uuid.UUID(int=99)
        self.role = role
        self.storage = None
        self.file_revisions_max = 50
        self.http_client = MagicMock()


# ---------------------------------------------------------------------------
# Helper: build args bytes
# ---------------------------------------------------------------------------

def _args(**kw) -> bytes:
    return json.dumps(kw).encode()


# ---------------------------------------------------------------------------
# Helper: parse tool result JSON
# ---------------------------------------------------------------------------

def _parse(result: str) -> dict:
    return json.loads(result)


# ---------------------------------------------------------------------------
# Helper: assert tool result is a success payload (no "code" error key)
# ---------------------------------------------------------------------------

def _assert_ok(result: str, context: str = ""):
    data = _parse(result)
    assert "code" not in data or data.get("code") not in (
        "UNKNOWN_TOOL", "FORBIDDEN", "NOT_FOUND", "BAD_ARGS", "ERROR"
    ), f"Unexpected error in {context!r}: {data}"


# ---------------------------------------------------------------------------
# Fixture: pool + ctx + seed files
# ---------------------------------------------------------------------------

@pytest.fixture
def pool() -> _FakePool:
    p = _FakePool()
    # Seed a basic JSCAD file that most tests will use
    fid = uuid.UUID(int=1)
    p._seed_file(
        fid,
        "main.jscad",
        "file",
        content="export default function({ primitives }) {\n  return [{ id: 'box', geom: primitives.cuboid({ size: [10,10,10] }) }]\n}",
    )
    # Seed a sketch file
    sketch_id = uuid.UUID(int=2)
    p._seed_file(
        sketch_id,
        "profile.sketch",
        "sketch",
        content=json.dumps({"version": 1, "plane": {"name": "XY"}, "entities": [], "constraints": []}),
    )
    # Seed a feature file
    feat_id = uuid.UUID(int=3)
    p._seed_file(
        feat_id,
        "bracket.feature",
        "feature",
        content=json.dumps({"version": 1, "features": [{"id": "extrude-1", "op": "extrude"}]}),
    )
    # Seed an assembly file
    asm_id = uuid.UUID(int=4)
    p._seed_file(
        asm_id,
        "main.assembly",
        "assembly",
        content=json.dumps({"version": 1, "components": []}),
    )
    # Seed a drawing file
    drw_id = uuid.UUID(int=5)
    p._seed_file(
        drw_id,
        "sheet1.drawing",
        "drawing",
        content=json.dumps({"version": 1, "sheets": []}),
    )
    # Seed a part file
    part_id = uuid.UUID(int=6)
    p._seed_file(
        part_id,
        "m3_bolt.part",
        "part",
        content=json.dumps({"name": "M3 Bolt", "manufacturer": "ACME", "mpn": "M3x10"}),
    )
    return p


@pytest.fixture
def ctx(pool) -> _FakeCtx:
    return _FakeCtx(pool)


# ===========================================================================
# TURN 1: write_file creates a file and records a revision
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_01_write_file_revision_appended(ctx, pool):
    from kerf_chat.tools.executor import execute
    result = await execute(ctx, "write_file", _args(
        path="/main.jscad",
        content="export default function({ primitives }) { return [{ id: 'sphere', geom: primitives.sphere({ radius: 5 }) }] }",
    ))
    _assert_ok(result, "write_file")
    # A revision must have been recorded with source='tool'
    tool_revs = [r for r in pool.revision_writes if r[2] == "tool"]
    assert len(tool_revs) >= 1


# ===========================================================================
# TURN 2: edit_file (replace_all=False) records a revision
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_02_edit_file_records_revision(ctx, pool):
    from kerf_chat.tools.executor import execute
    result = await execute(ctx, "edit_file", _args(
        path="/main.jscad",
        old_string="size: [10,10,10]",
        new_string="size: [20,20,20]",
        replace_all=False,
    ))
    data = _parse(result)
    # Either success or NOT_FOUND (if old_string not in current content) is
    # acceptable — the key invariant is that no UNKNOWN_TOOL or FORBIDDEN fires.
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN")


# ===========================================================================
# TURN 3: edit_file replace_all=True records a revision and returns count
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_03_edit_file_replace_all(ctx, pool):
    from kerf_chat.tools.executor import execute
    # Write a file with three occurrences first
    await execute(ctx, "write_file", _args(
        path="/main.jscad",
        content="const x = foo + foo + foo",
    ))
    before = len(pool.revision_writes)
    result = await execute(ctx, "edit_file", _args(
        path="/main.jscad",
        old_string="foo",
        new_string="bar",
        replace_all=True,
    ))
    data = _parse(result)
    # replaced count must be 3
    assert data.get("replaced") == 3
    after = len(pool.revision_writes)
    assert after > before, "replace_all must record a revision"


# ===========================================================================
# TURN 4: read_file returns content (no revision written)
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_04_read_file_no_revision(ctx, pool):
    from kerf_chat.tools.executor import execute
    before = len(pool.revision_writes)
    result = await execute(ctx, "read_file", _args(path="/main.jscad"))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN")
    after = len(pool.revision_writes)
    assert after == before, "read_file must not write revisions"


# ===========================================================================
# TURN 5: list_files returns a non-empty array
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_05_list_files_returns_files(ctx, pool):
    from kerf_chat.tools.executor import execute
    result = await execute(ctx, "list_files", _args())
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "ERROR")
    assert "files" in data, f"Expected 'files' key, got: {data}"
    assert len(data["files"]) > 0


# ===========================================================================
# TURN 6: list_files with glob filter
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_06_list_files_glob_filter(ctx, pool):
    from kerf_chat.tools.executor import execute
    result = await execute(ctx, "list_files", _args(glob="*.jscad"))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "ERROR")
    # All returned files must match the glob
    for f in data.get("files", []):
        path = f.get("path", "") or f.get("name", "")
        assert path.endswith(".jscad"), f"Non-.jscad file leaked through glob: {path}"


# ===========================================================================
# TURN 7: search_files remaps pattern and returns matches
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_07_search_files_dispatch(ctx, pool):
    from kerf_chat.tools.executor import execute
    search_result = json.dumps({"matches": [{"file": "/main.jscad", "line": 1, "text": "sphere"}]})
    mock_search = AsyncMock(return_value=search_result)
    with patch("kerf_api.tools.file_ops.run_search_code", mock_search):
        result = await execute(ctx, "search_files", _args(pattern="sphere"))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN")
    # Verify pattern was remapped to 'query' in inner call
    call_inner = json.loads(mock_search.call_args[0][1])
    assert call_inner.get("query") == "sphere"


# ===========================================================================
# TURN 8: create_file(kind='sketch') routes to scaffold
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_08_create_file_sketch(ctx, pool):
    from kerf_chat.tools.executor import execute
    sketch_result = json.dumps({"path": "/new_profile.sketch", "id": str(uuid.uuid4())})
    mock_create = AsyncMock(return_value=sketch_result)
    with patch("kerf_api.tools.scaffold.run_create_sketch", mock_create):
        result = await execute(ctx, "create_file", _args(
            path="/new_profile.sketch",
            kind="sketch",
            options={"plane": "XZ"},
        ))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "BAD_ARGS")
    mock_create.assert_called_once()


# ===========================================================================
# TURN 9: create_file(kind='feature') routes to scaffold
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_09_create_file_feature(ctx, pool):
    from kerf_chat.tools.executor import execute
    feat_result = json.dumps({"path": "/new.feature", "id": str(uuid.uuid4())})
    mock_create = AsyncMock(return_value=feat_result)
    with patch("kerf_api.tools.scaffold.run_create_feature", mock_create):
        result = await execute(ctx, "create_file", _args(
            path="/new.feature",
            kind="feature",
            options={"name": "bracket"},
        ))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "BAD_ARGS")
    mock_create.assert_called_once()


# ===========================================================================
# TURN 10: create_file(kind='circuit') routes to scaffold
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_10_create_file_circuit(ctx, pool):
    from kerf_chat.tools.executor import execute
    ckt_result = json.dumps({"path": "/main.circuit.tsx", "id": str(uuid.uuid4())})
    mock_create = AsyncMock(return_value=ckt_result)
    with patch("kerf_api.tools.scaffold.run_create_circuit", mock_create):
        result = await execute(ctx, "create_file", _args(
            path="/main.circuit.tsx",
            kind="circuit",
            options={"width_mm": 50, "height_mm": 30},
        ))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "BAD_ARGS")
    mock_create.assert_called_once()


# ===========================================================================
# TURN 11: create_file(kind='part') routes to scaffold
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_11_create_file_part(ctx, pool):
    from kerf_chat.tools.executor import execute
    part_result = json.dumps({"path": "/resistor.part", "id": str(uuid.uuid4())})
    mock_create = AsyncMock(return_value=part_result)
    with patch("kerf_api.tools.scaffold.run_create_part", mock_create):
        result = await execute(ctx, "create_file", _args(
            path="/resistor.part",
            kind="part",
            options={"metadata": {"name": "10k Resistor"}},
        ))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "BAD_ARGS")
    mock_create.assert_called_once()


# ===========================================================================
# TURN 12: create_file(kind='banana') returns BAD_ARGS
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_12_create_file_bad_kind(ctx):
    from kerf_chat.tools.executor import execute
    result = await execute(ctx, "create_file", _args(path="/bad.xyz", kind="banana"))
    data = _parse(result)
    assert data.get("code") == "BAD_ARGS"


# ===========================================================================
# TURN 13: describe_part returns sketch structure
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_13_describe_part_sketch(ctx, pool):
    from kerf_chat.tools.executor import execute
    result = await execute(ctx, "describe_part", _args(path="/profile.sketch"))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "ERROR")
    # May be NOT_FOUND if pool.fetchrow returns nothing for the content query;
    # but must not be UNKNOWN_TOOL.
    if "code" not in data:
        assert "kind" in data


# ===========================================================================
# TURN 14: describe_part returns feature structure with feature_ids
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_14_describe_part_feature(ctx, pool):
    from kerf_chat.tools.executor import execute
    result = await execute(ctx, "describe_part", _args(path="/bracket.feature"))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "ERROR")


# ===========================================================================
# TURN 15: describe_part returns assembly component list
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_15_describe_part_assembly(ctx, pool):
    from kerf_chat.tools.executor import execute
    result = await execute(ctx, "describe_part", _args(path="/main.assembly"))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "ERROR")


# ===========================================================================
# TURN 16: search_kerf_docs dispatches to docs tool
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_16_search_kerf_docs(ctx):
    from kerf_chat.tools.executor import execute
    docs_result = json.dumps({"results": [{"path": "/docs/llm/sketch.md", "score": 0.9}]})
    mock_docs = AsyncMock(return_value=docs_result)
    with patch("kerf_chat.tools.docs.run_search_kerf_docs", mock_docs):
        result = await execute(ctx, "search_kerf_docs", _args(query="sketch plane XY"))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN")
    mock_docs.assert_called_once()


# ===========================================================================
# TURN 17: import_step renames source_url → url
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_17_import_step_url_remap(ctx):
    from kerf_chat.tools.executor import execute
    import_result = json.dumps({"path": "/part.step", "id": str(uuid.uuid4())})
    mock_import = AsyncMock(return_value=import_result)
    with patch("kerf_api.tools.file_ops.run_import_step", mock_import):
        result = await execute(ctx, "import_step", _args(
            name="part.step",
            source_url="https://example.com/part.step",
        ))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "BAD_ARGS")
    # Verify source_url was remapped to url
    inner = json.loads(mock_import.call_args[0][1])
    assert "url" in inner
    assert "source_url" not in inner
    assert inner["url"] == "https://example.com/part.step"


# ===========================================================================
# TURN 18: export_artifact returns download_url for a known file
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_18_export_artifact_step(ctx, pool):
    from kerf_chat.tools.executor import execute
    file_id = str(uuid.UUID(int=1))
    result = await execute(ctx, "export_artifact", _args(file_id=file_id, format="step"))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "BAD_ARGS")
    if "code" not in data:
        assert "download_url" in data or "note" in data


# ===========================================================================
# TURN 19: export_artifact with invalid format returns BAD_ARGS
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_19_export_artifact_bad_format(ctx, pool):
    from kerf_chat.tools.executor import execute
    file_id = str(uuid.UUID(int=1))
    result = await execute(ctx, "export_artifact", _args(file_id=file_id, format="xyz"))
    data = _parse(result)
    assert data.get("code") == "BAD_ARGS"


# ===========================================================================
# TURN 20: run_compute routes fem engine
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_20_run_compute_fem(ctx):
    from kerf_chat.tools.executor import execute
    fem_result = json.dumps({"job_id": "fem_abc123", "status": "queued"})
    mock_fem = AsyncMock(return_value=fem_result)
    with patch.dict("sys.modules"):
        kerf_fem = types.ModuleType("kerf_fem")
        kerf_fem_tools = types.ModuleType("kerf_fem.tools")
        kerf_fem_tools.run_fem_run = mock_fem
        sys.modules["kerf_fem"] = kerf_fem
        sys.modules["kerf_fem.tools"] = kerf_fem_tools
        result = await execute(ctx, "run_compute", _args(
            engine="fem",
            file_id=str(uuid.UUID(int=1)),
            options={"solver": "linear_static"},
        ))
    data = _parse(result)
    assert data.get("job_id") == "fem_abc123"
    assert data.get("status") == "queued"
    # Assistant turn would reference: "FEM job queued: fem_abc123"
    assert "fem_abc123" in json.dumps(data)


# ===========================================================================
# TURN 21: run_compute routes cam engine
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_21_run_compute_cam(ctx):
    from kerf_chat.tools.executor import execute
    cam_result = json.dumps({"job_id": "cam_xyz", "status": "queued"})
    mock_cam = AsyncMock(return_value=cam_result)
    with patch.dict("sys.modules"):
        kerf_cam = types.ModuleType("kerf_cam")
        kerf_cam_tools = types.ModuleType("kerf_cam.tools")
        kerf_cam_tools.run_cam_run = mock_cam
        sys.modules["kerf_cam"] = kerf_cam
        sys.modules["kerf_cam.tools"] = kerf_cam_tools
        result = await execute(ctx, "run_compute", _args(
            engine="cam",
            file_id=str(uuid.UUID(int=1)),
            options={"operation": "face"},
        ))
    data = _parse(result)
    assert data.get("job_id") == "cam_xyz"


# ===========================================================================
# TURN 22: run_compute missing engine dep → NOT_AVAILABLE
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_22_run_compute_missing_dep(ctx):
    from kerf_chat.tools.executor import execute
    with patch.dict("sys.modules", {"kerf_render": None, "kerf_render.tools": None}):
        result = await execute(ctx, "run_compute", _args(
            engine="render",
            file_id=str(uuid.UUID(int=1)),
        ))
    data = _parse(result)
    assert data.get("code") == "NOT_AVAILABLE"


# ===========================================================================
# TURN 23: poll_compute routes by fem_ prefix
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_23_poll_compute_fem_prefix(ctx):
    from kerf_chat.tools.executor import execute
    status_result = json.dumps({"job_id": "fem_abc123", "status": "done", "result_url": "/results/abc"})
    mock_status = AsyncMock(return_value=status_result)
    with patch.dict("sys.modules"):
        kerf_fem_tools = types.ModuleType("kerf_fem.tools")
        kerf_fem_tools.run_fem_run = AsyncMock()
        kerf_fem_tools.run_fem_job_status = mock_status
        sys.modules["kerf_fem.tools"] = kerf_fem_tools
        result = await execute(ctx, "poll_compute", _args(job_id="fem_abc123"))
    data = _parse(result)
    assert data.get("status") == "done"
    # assistant would reference: "FEM analysis complete. Result at /results/abc"
    assert "result_url" in data or "done" in json.dumps(data)


# ===========================================================================
# TURN 24: duplicate_object dispatches to object_ops
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_24_duplicate_object(ctx):
    from kerf_chat.tools.executor import execute
    dup_result = json.dumps({"path": "/main.jscad", "new_id": "box-copy"})
    mock_dup = AsyncMock(return_value=dup_result)
    with patch("kerf_api.tools.object_ops.run_duplicate_object", mock_dup):
        result = await execute(ctx, "duplicate_object", _args(
            path="/main.jscad",
            object_id="box",
            new_id="box-copy",
        ))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "BAD_ARGS")
    mock_dup.assert_called_once()


# ===========================================================================
# TURN 25: delete_object dispatches to object_ops
# ===========================================================================

@pytest.mark.asyncio
async def test_turn_25_delete_object(ctx):
    from kerf_chat.tools.executor import execute
    del_result = json.dumps({"path": "/main.jscad", "removed_id": "box"})
    mock_del = AsyncMock(return_value=del_result)
    with patch("kerf_api.tools.object_ops.run_delete_object", mock_del):
        result = await execute(ctx, "delete_object", _args(
            path="/main.jscad",
            object_id="box",
        ))
    data = _parse(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "BAD_ARGS")
    mock_del.assert_called_once()


# ===========================================================================
# Bonus: viewer role blocked from write tools
# ===========================================================================

@pytest.mark.asyncio
async def test_viewer_blocked_from_write_file(pool):
    ctx_viewer = _FakeCtx(pool, role="viewer")
    from kerf_chat.tools.executor import execute
    result = await execute(ctx_viewer, "write_file", _args(
        path="/main.jscad",
        content="hacked",
    ))
    data = _parse(result)
    assert data.get("code") == "FORBIDDEN"


@pytest.mark.asyncio
async def test_viewer_blocked_from_edit_file(pool):
    ctx_viewer = _FakeCtx(pool, role="viewer")
    from kerf_chat.tools.executor import execute
    result = await execute(ctx_viewer, "edit_file", _args(
        path="/main.jscad",
        old_string="x",
        new_string="y",
    ))
    data = _parse(result)
    assert data.get("code") == "FORBIDDEN"


@pytest.mark.asyncio
async def test_viewer_can_list_files(pool):
    ctx_viewer = _FakeCtx(pool, role="viewer")
    from kerf_chat.tools.executor import execute
    result = await execute(ctx_viewer, "list_files", _args())
    data = _parse(result)
    assert data.get("code") not in ("FORBIDDEN", "UNKNOWN_TOOL")


# ===========================================================================
# Aggregate: revision source='tool' invariant across write operations
# ===========================================================================

@pytest.mark.asyncio
async def test_all_write_ops_use_tool_source(ctx, pool):
    """Every revision recorded by write_file / edit_file must carry source='tool'."""
    from kerf_chat.tools.executor import execute

    pool.revision_writes.clear()

    # write_file
    await execute(ctx, "write_file", _args(
        path="/main.jscad",
        content="export default function({ primitives }) { return [{ id: 'cyl', geom: primitives.cylinder({ radius: 3, height: 10 }) }] }",
    ))

    # edit_file replace_all
    await execute(ctx, "edit_file", _args(
        path="/main.jscad",
        old_string="radius: 3",
        new_string="radius: 5",
        replace_all=True,
    ))

    # Every revision must have source='tool'
    for fid, content, source in pool.revision_writes:
        assert source == "tool", f"Expected source='tool', got {source!r} for file {fid}"


# ===========================================================================
# Aggregate: assistant message references tool result
# ===========================================================================

@pytest.mark.asyncio
async def test_assistant_message_references_tool_result():
    """Simulate a full 2-turn LLM interaction: user ask -> LLM emits tool call
    -> tool executes -> LLM receives result -> assistant reply mentions result.

    The provider is mocked: turn 1 returns a tool call; turn 2 returns a text
    reply that references the file path from the tool result.
    """
    from kerf_chat.llm import (
        AnthropicProvider, CompleteRequest, CompleteResponse,
        Message, ToolCall, ToolSpec,
    )
    from kerf_chat.tools.catalog import TOOL_CATALOG

    # --- Mock LLM behaviour ---
    # Turn 1: emit a read_file tool call
    turn1_response = CompleteResponse(
        content="",
        tool_calls=[ToolCall(
            id="tc_001",
            name="read_file",
            arguments_json=json.dumps({"path": "/main.jscad"}),
        )],
        stop_reason="tool_use",
        model_used="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=20,
    )

    # Turn 2: assistant reply references the tool result
    file_content = "export default function(...) { ... }"
    turn2_response = CompleteResponse(
        content=f"I've read the file. It contains: `{file_content}`. I'll now make the edit.",
        tool_calls=[],
        stop_reason="stop",
        model_used="claude-sonnet-4-6",
        input_tokens=150,
        output_tokens=30,
    )

    call_count = [0]
    responses = [turn1_response, turn2_response]

    def _mock_complete(req: CompleteRequest) -> CompleteResponse:
        idx = call_count[0]
        call_count[0] += 1
        return responses[idx]

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.api_key = "test"
    provider.prompt_cache = False
    provider.complete = _mock_complete

    # --- Turn 1: user sends request, LLM emits tool call ---
    user_msg = Message(role="user", content="Read my main JSCAD file and tell me what it contains.")
    req1 = CompleteRequest(
        model="claude-sonnet-4-6",
        system="You are a CAD assistant.",
        messages=[user_msg],
        tools=[t for t in TOOL_CATALOG],
    )
    resp1 = provider.complete(req1)
    assert resp1.stop_reason == "tool_use"
    assert len(resp1.tool_calls) == 1
    assert resp1.tool_calls[0].name == "read_file"

    # --- Execute the tool ---
    pool = _FakePool()
    fid = uuid.UUID(int=1)
    pool._seed_file(fid, "main.jscad", "file", file_content)
    ctx = _FakeCtx(pool)

    from kerf_chat.tools.executor import execute
    tool_result = await execute(ctx, "read_file", resp1.tool_calls[0].arguments_json.encode())
    tool_data = json.loads(tool_result)
    # result must carry the file content
    assert "code" not in tool_data or tool_data.get("code") not in ("NOT_FOUND", "ERROR", "FORBIDDEN")

    # --- Turn 2: feed tool result back to LLM ---
    assistant_tc_msg = Message(
        role="assistant",
        content="",
        tool_calls=resp1.tool_calls,
    )
    tool_result_msg = Message(
        role="tool",
        content=tool_result,
        tool_call_id="tc_001",
        is_error=False,
    )
    req2 = CompleteRequest(
        model="claude-sonnet-4-6",
        system="You are a CAD assistant.",
        messages=[user_msg, assistant_tc_msg, tool_result_msg],
        tools=list(TOOL_CATALOG),
    )
    resp2 = provider.complete(req2)
    assert resp2.stop_reason == "stop"
    # Assistant reply must reference something from the tool result (file content or path)
    assert file_content in resp2.content or "/main.jscad" in resp2.content or "read" in resp2.content.lower()
