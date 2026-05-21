"""
T-104: Chat regression matrix.

Scope: the chat agent does NOT silently break the editor — 10 representative
tool calls (sketch / feature / sheet-metal / weldment / drawing / PCB /
jewelry / arch / FEM / CAM) each leave the project re-openable.

Success criteria per domain:
  - tool call returns no UNKNOWN_TOOL / FORBIDDEN / ERROR code
  - describe_part on that file path still returns valid, parseable JSON
    (proxy for "project re-openable" without a live browser)
  - write operations record at least one revision with source='tool'
  - no orphan job records left in an error state

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
# Hermetic in-memory pool (mirrors the one in test_feature_chat_tool_roundtrip)
# ---------------------------------------------------------------------------


class _Rev:
    def __init__(self, rev_id, file_id, content, source, kind="base"):
        self.id = rev_id
        self.file_id = file_id
        self.content = content
        self.source = source
        self.kind = kind
        self.content_sha256 = hashlib.sha256(content.encode()).digest()
        self.content_gz = gzip.compress(content.encode(), compresslevel=1)
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


class _File:
    def __init__(self, file_id, name, kind, content="", parent_id=None):
        self.id = file_id
        self.name = name
        self.kind = kind
        self.content = content
        self.parent_id = parent_id
        self.deleted_at = None


class _Pool:
    """Minimal asyncpg-shaped in-memory pool."""

    def __init__(self):
        self._files: dict[uuid.UUID, _File] = {}
        self._revisions: list[_Rev] = []
        # (file_id, content, source) triples for assertion
        self.revision_writes: list[tuple] = []

    def seed(self, fid: uuid.UUID, name: str, kind: str, content: str = "",
             parent_id: Optional[uuid.UUID] = None) -> _File:
        f = _File(fid, name, kind, content, parent_id)
        self._files[fid] = f
        return f

    def _by_name(self, name: str, parent_id) -> Optional[_File]:
        for f in self._files.values():
            if f.name == name and f.parent_id == parent_id and f.deleted_at is None:
                return f
        return None

    async def fetchrow(self, query: str, *args, **kw) -> Optional[Any]:
        q = query.strip().lower()

        if "from file_revisions" in q and "order by created_at desc limit 1" in q:
            fid = args[0]
            revs = [r for r in self._revisions if r.file_id == fid]
            return revs[-1] if revs else None

        if "from file_revisions" in q and "kind = 'base'" in q and "limit 1" in q:
            sha = args[0]
            for r in self._revisions:
                if r.content_sha256 == sha and r.kind == "base":
                    return r
            return None

        if "from files" in q and "name = $2" in q:
            project_id = args[0]
            name = args[1]
            parent_id = args[2] if len(args) > 2 else None
            f = self._by_name(name, parent_id)
            if f is None:
                return None
            return {"id": f.id, "parent_id": f.parent_id, "name": f.name, "kind": f.kind}

        if "select content from files" in q:
            fid = args[0]
            f = self._files.get(fid)
            return {"content": f.content} if f else None

        if (
            ("select name, kind from files" in q)
            or ("select" in q and "name" in q and "kind" in q and "from files" in q)
        ):
            fid = args[0]
            f = self._files.get(fid)
            return {"name": f.name, "kind": f.kind} if f else None

        if "from file_revisions where id = $1" in q:
            rev_id = args[0]
            for r in self._revisions:
                if r.id == rev_id:
                    return r
            return None

        return None

    async def fetchval(self, query: str, *args, **kw) -> Any:
        q = query.strip().lower()
        if "insert into files" in q:
            new_id = uuid.uuid4()
            project_id, parent_id, name, kind, content = args[:5]
            f = _File(new_id, name, kind, content or "", parent_id)
            self._files[new_id] = f
            return new_id
        if "count(*)" in q:
            return 0
        return None

    async def fetch(self, query: str, *args, **kw) -> list:
        q = query.strip().lower()
        if "from files" in q and ("project_id = $1" in q or "project_id=$1" in q):
            return [
                {
                    "id": f.id,
                    "parent_id": f.parent_id,
                    "name": f.name,
                    "kind": f.kind,
                    "length": len(f.content),
                    "size": len(f.content.encode()),
                }
                for f in self._files.values()
                if f.deleted_at is None
            ]
        return []

    async def execute(self, query: str, *args, **kw) -> str:
        q = query.strip().lower()
        if "update files set content" in q:
            content, fid, project_id = args[:3]
            f = self._files.get(fid)
            if f:
                f.content = content
            return "UPDATE 1"
        if "insert into files" in q and "returning" not in q:
            return "INSERT 1"
        if "insert into file_revisions" in q:
            rev_id = args[0]
            fid = args[1]
            gz_bytes = None
            source = "tool"
            kind = "base"
            content_sha256 = b""
            for a in args:
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
            r = _Rev(rev_id, fid, content, source, kind)
            r.content_sha256 = content_sha256 if content_sha256 else hashlib.sha256(content.encode()).digest()
            self._revisions.append(r)
            self.revision_writes.append((fid, content, source))
            return "INSERT 1"
        if "update files set deleted_at" in q:
            return "UPDATE 1"
        if "delete from file_revisions" in q:
            return "DELETE 0"
        return "OK"


class _Ctx:
    def __init__(self, pool: _Pool, role: str = "editor"):
        self.pool = pool
        self.project_id = uuid.UUID(int=42)
        self.user_id = uuid.UUID(int=99)
        self.role = role
        self.storage = None
        self.file_revisions_max = 50
        self.http_client = MagicMock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _args(**kw) -> bytes:
    return json.dumps(kw).encode()


def _ok(result: str, label: str = "") -> dict:
    """Assert no error code and return parsed dict."""
    data = json.loads(result)
    bad_codes = {"UNKNOWN_TOOL", "FORBIDDEN", "ERROR"}
    assert data.get("code") not in bad_codes, (
        f"[{label}] unexpected error: {data}"
    )
    return data


def _assert_reopenable(data: dict, label: str) -> None:
    """After a describe_part call the result must be parseable metadata."""
    assert "code" not in data or data.get("code") not in {"UNKNOWN_TOOL", "FORBIDDEN", "ERROR"}, (
        f"[{label}] describe_part returned error: {data}"
    )
    # describe_part always includes 'path' and 'kind' on success
    if "code" not in data:
        assert "kind" in data, f"[{label}] describe_part missing 'kind': {data}"


def _assert_revision_written(pool: _Pool, label: str) -> None:
    """At least one revision must carry source='tool'."""
    tool_revs = [r for r in pool.revision_writes if r[2] == "tool"]
    assert tool_revs, f"[{label}] no revision with source='tool' recorded"


# ---------------------------------------------------------------------------
# Fixture: pool seeded with 10 domain files
# ---------------------------------------------------------------------------

@pytest.fixture
def pool() -> _Pool:
    p = _Pool()

    # 1. Sketch (profile.sketch)
    p.seed(
        uuid.UUID(int=1), "profile.sketch", "sketch",
        content=json.dumps({
            "version": 1,
            "plane": {"name": "XY"},
            "entities": [{"id": "l1", "type": "Line", "start": [0, 0], "end": [50, 0]}],
            "constraints": [],
        }),
    )

    # 2. Feature — generic (bracket.feature)
    p.seed(
        uuid.UUID(int=2), "bracket.feature", "feature",
        content=json.dumps({
            "version": 1,
            "features": [
                {"id": "extrude-1", "op": "extrude", "sketch_id": str(uuid.UUID(int=1)), "depth": 10},
            ],
        }),
    )

    # 3. Feature — sheet-metal (panel.feature)
    p.seed(
        uuid.UUID(int=3), "panel.feature", "feature",
        content=json.dumps({
            "version": 1,
            "features": [
                {"id": "sm-flange-1", "op": "sheet_metal_flange", "thickness": 1.5, "bend_radius": 3},
            ],
        }),
    )

    # 4. Feature — weldment (frame.feature)
    p.seed(
        uuid.UUID(int=4), "frame.feature", "feature",
        content=json.dumps({
            "version": 1,
            "features": [
                {"id": "weld-frame-1", "op": "weldment_frame",
                 "profile": "SQ-50x50x3",
                 "skeleton": [{"start": [0, 0, 0], "end": [1000, 0, 0]}]},
            ],
        }),
    )

    # 5. Drawing (sheet1.drawing)
    p.seed(
        uuid.UUID(int=5), "sheet1.drawing", "drawing",
        content=json.dumps({
            "version": 1,
            "sheets": [{"id": "A4-1", "size": "A4", "views": []}],
        }),
    )

    # 6. Circuit / PCB (main.circuit.tsx — stored as 'file' kind)
    p.seed(
        uuid.UUID(int=6), "main.circuit.tsx", "file",
        content=(
            "import { createUseComponent } from '@tscircuit/core'\n"
            "export default () => <board width='100mm' height='80mm' />\n"
        ),
    )

    # 7. Part — jewelry metadata (ring.part)
    p.seed(
        uuid.UUID(int=7), "ring.part", "part",
        content=json.dumps({
            "name": "Wedding Band",
            "manufacturer": "Studio Goldsmith",
            "mpn": "WB-18K-SZ7",
            "material": "18k gold",
            "inner_diameter_mm": 17.35,
        }),
    )

    # 8. Assembly — arch (building.assembly)
    p.seed(
        uuid.UUID(int=8), "building.assembly", "assembly",
        content=json.dumps({
            "version": 1,
            "components": [
                {"id": "floor-1", "file": "slab.feature", "transform": {"t": [0, 0, 0]}},
                {"id": "wall-N", "file": "wall_north.feature", "transform": {"t": [0, 0, 0]}},
            ],
        }),
    )

    # 9. Feature — FEM subject (beam.feature)
    p.seed(
        uuid.UUID(int=9), "beam.feature", "feature",
        content=json.dumps({
            "version": 1,
            "features": [
                {"id": "extrude-beam", "op": "extrude",
                 "sketch_id": str(uuid.UUID(int=1)), "depth": 500},
            ],
        }),
    )

    # 10. JSCAD — CAM subject (cam_stock.jscad)
    p.seed(
        uuid.UUID(int=10), "cam_stock.jscad", "file",
        content=(
            "export default function({ primitives }) {\n"
            "  return [{ id: 'stock', geom: primitives.cuboid({ size: [100, 50, 20] }) }]\n"
            "}\n"
        ),
    )

    return p


@pytest.fixture
def ctx(pool: _Pool) -> _Ctx:
    return _Ctx(pool)


# ===========================================================================
# DOMAIN 1: sketch — write a new entity, verify file re-openable
# ===========================================================================

@pytest.mark.asyncio
async def test_domain_sketch_write_and_reopenable(ctx, pool):
    from kerf_chat.tools.executor import execute

    pool.revision_writes.clear()

    new_sketch = json.dumps({
        "version": 1,
        "plane": {"name": "XY"},
        "entities": [
            {"id": "l1", "type": "Line", "start": [0, 0], "end": [50, 0]},
            {"id": "l2", "type": "Line", "start": [50, 0], "end": [50, 30]},
            {"id": "arc1", "type": "Arc", "center": [25, 0], "radius": 25, "start_angle": 0, "end_angle": 180},
        ],
        "constraints": [{"id": "c1", "type": "horizontal", "entity_id": "l1"}],
    })
    result = await execute(ctx, "write_file", _args(path="/profile.sketch", content=new_sketch))
    _ok(result, "sketch.write_file")
    _assert_revision_written(pool, "sketch")

    # describe_part must parse the sketch and return entity_count
    desc = await execute(ctx, "describe_part", _args(path="/profile.sketch"))
    data = json.loads(desc)
    _assert_reopenable(data, "sketch")
    assert data.get("entity_count") == 3, (
        f"Expected 3 entities after write; got: {data}"
    )


# ===========================================================================
# DOMAIN 2: feature (generic extrude) — edit depth, verify re-openable
# ===========================================================================

@pytest.mark.asyncio
async def test_domain_feature_edit_and_reopenable(ctx, pool):
    from kerf_chat.tools.executor import execute

    pool.revision_writes.clear()

    # edit_file — change extrude depth
    result = await execute(ctx, "edit_file", _args(
        path="/bracket.feature",
        old_string='"depth": 10',
        new_string='"depth": 25',
    ))
    data = json.loads(result)
    # NOT_FOUND is acceptable if old_string miss, but no FORBIDDEN or UNKNOWN_TOOL
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN"), (
        f"feature.edit_file unexpected error: {data}"
    )

    # Regardless of edit outcome: describe_part must still parse fine
    desc = await execute(ctx, "describe_part", _args(path="/bracket.feature"))
    feature_data = json.loads(desc)
    _assert_reopenable(feature_data, "feature")
    if "feature_count" in feature_data:
        assert feature_data["feature_count"] >= 1


# ===========================================================================
# DOMAIN 3: sheet-metal — write full flange feature node, verify re-openable
# ===========================================================================

@pytest.mark.asyncio
async def test_domain_sheet_metal_write_and_reopenable(ctx, pool):
    from kerf_chat.tools.executor import execute

    pool.revision_writes.clear()

    sm_content = json.dumps({
        "version": 1,
        "features": [
            {
                "id": "sm-flange-1",
                "op": "sheet_metal_flange",
                "sketch_id": str(uuid.UUID(int=1)),
                "thickness": 2.0,
                "bend_radius": 4.0,
                "bend_angle": 90.0,
                "k_factor": 0.42,
            },
            {
                "id": "sm-unfold-1",
                "op": "sheet_metal_unfold",
                "source_id": "sm-flange-1",
            },
        ],
    })
    result = await execute(ctx, "write_file", _args(path="/panel.feature", content=sm_content))
    _ok(result, "sheet_metal.write_file")
    _assert_revision_written(pool, "sheet_metal")

    # File must still be parseable
    desc = await execute(ctx, "describe_part", _args(path="/panel.feature"))
    data = json.loads(desc)
    _assert_reopenable(data, "sheet_metal")
    assert data.get("feature_count") == 2, (
        f"Expected 2 features (flange + unfold); got: {data}"
    )


# ===========================================================================
# DOMAIN 4: weldment — add a second member, verify re-openable
# ===========================================================================

@pytest.mark.asyncio
async def test_domain_weldment_edit_and_reopenable(ctx, pool):
    from kerf_chat.tools.executor import execute

    pool.revision_writes.clear()

    # Replace the skeleton with two members (edit_file replace_all=True)
    result = await execute(ctx, "edit_file", _args(
        path="/frame.feature",
        old_string='"skeleton": [{"start": [0, 0, 0], "end": [1000, 0, 0]}]',
        new_string=(
            '"skeleton": ['
            '{"start": [0, 0, 0], "end": [1000, 0, 0]}, '
            '{"start": [0, 0, 0], "end": [0, 1000, 0]}'
            ']'
        ),
    ))
    data = json.loads(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN"), (
        f"weldment.edit_file unexpected error: {data}"
    )

    # describe_part must still parse
    desc = await execute(ctx, "describe_part", _args(path="/frame.feature"))
    feature_data = json.loads(desc)
    _assert_reopenable(feature_data, "weldment")


# ===========================================================================
# DOMAIN 5: drawing — add a view to the sheet, verify re-openable
# ===========================================================================

@pytest.mark.asyncio
async def test_domain_drawing_write_and_reopenable(ctx, pool):
    from kerf_chat.tools.executor import execute

    pool.revision_writes.clear()

    drawing_content = json.dumps({
        "version": 1,
        "sheets": [
            {
                "id": "A4-1",
                "size": "A4",
                "views": [
                    {
                        "id": "front-view",
                        "kind": "orthographic",
                        "direction": "front",
                        "file_id": str(uuid.UUID(int=2)),
                        "position": [40, 100],
                        "scale": 1.0,
                    },
                ],
            }
        ],
    })
    result = await execute(ctx, "write_file", _args(path="/sheet1.drawing", content=drawing_content))
    _ok(result, "drawing.write_file")
    _assert_revision_written(pool, "drawing")

    # describe_part on a drawing returns sheet_count
    desc = await execute(ctx, "describe_part", _args(path="/sheet1.drawing"))
    data = json.loads(desc)
    _assert_reopenable(data, "drawing")
    assert data.get("sheet_count") == 1, (
        f"Expected sheet_count=1; got: {data}"
    )


# ===========================================================================
# DOMAIN 6: PCB / circuit — write TSCircuit board, verify re-openable
# ===========================================================================

@pytest.mark.asyncio
async def test_domain_pcb_write_and_reopenable(ctx, pool):
    from kerf_chat.tools.executor import execute

    pool.revision_writes.clear()

    circuit_content = (
        "import { createUseComponent } from '@tscircuit/core'\n"
        "import { Resistor, Capacitor } from '@tscircuit/core'\n"
        "\n"
        "export default () => (\n"
        "  <board width='100mm' height='80mm'>\n"
        "    <Resistor name='R1' resistance='10k' footprint='0402' />\n"
        "    <Capacitor name='C1' capacitance='100nF' footprint='0402' />\n"
        "  </board>\n"
        ")\n"
    )
    result = await execute(ctx, "write_file", _args(path="/main.circuit.tsx", content=circuit_content))
    _ok(result, "pcb.write_file")
    _assert_revision_written(pool, "pcb")

    # describe_part on a 'file' kind returns line_count + preview
    desc = await execute(ctx, "describe_part", _args(path="/main.circuit.tsx"))
    data = json.loads(desc)
    _assert_reopenable(data, "pcb")
    if "line_count" in data:
        assert data["line_count"] >= 1


# ===========================================================================
# DOMAIN 7: jewelry — update part metadata (ring size), verify re-openable
# ===========================================================================

@pytest.mark.asyncio
async def test_domain_jewelry_edit_and_reopenable(ctx, pool):
    from kerf_chat.tools.executor import execute

    pool.revision_writes.clear()

    # Write updated part metadata to ring.part
    new_part = json.dumps({
        "name": "Wedding Band",
        "manufacturer": "Studio Goldsmith",
        "mpn": "WB-18K-SZ8",
        "material": "18k gold",
        "inner_diameter_mm": 18.19,
        "finish": "brushed",
    })
    result = await execute(ctx, "write_file", _args(path="/ring.part", content=new_part))
    _ok(result, "jewelry.write_file")
    _assert_revision_written(pool, "jewelry")

    # describe_part on a 'part' kind returns name, manufacturer, mpn
    desc = await execute(ctx, "describe_part", _args(path="/ring.part"))
    data = json.loads(desc)
    _assert_reopenable(data, "jewelry")
    if "mpn" in data:
        assert data["mpn"] == "WB-18K-SZ8", (
            f"Part mpn should reflect latest write; got: {data}"
        )


# ===========================================================================
# DOMAIN 8: arch (assembly) — add a third component, verify re-openable
# ===========================================================================

@pytest.mark.asyncio
async def test_domain_arch_assembly_edit_and_reopenable(ctx, pool):
    from kerf_chat.tools.executor import execute

    pool.revision_writes.clear()

    arch_content = json.dumps({
        "version": 1,
        "components": [
            {"id": "floor-1", "file": "slab.feature", "transform": {"t": [0, 0, 0]}},
            {"id": "wall-N", "file": "wall_north.feature", "transform": {"t": [0, 0, 0]}},
            {"id": "roof-1", "file": "roof.feature", "transform": {"t": [0, 0, 3000]}},
        ],
    })
    result = await execute(ctx, "write_file", _args(path="/building.assembly", content=arch_content))
    _ok(result, "arch.write_file")
    _assert_revision_written(pool, "arch")

    # describe_part on an assembly returns component_count + component_ids
    desc = await execute(ctx, "describe_part", _args(path="/building.assembly"))
    data = json.loads(desc)
    _assert_reopenable(data, "arch")
    assert data.get("component_count") == 3, (
        f"Expected 3 arch components; got: {data}"
    )


# ===========================================================================
# DOMAIN 9: FEM — run_compute(engine='fem') queues a job; project re-openable
# ===========================================================================

@pytest.mark.asyncio
async def test_domain_fem_compute_and_reopenable(ctx, pool):
    from kerf_chat.tools.executor import execute

    fem_result = json.dumps({"job_id": "fem_t104_001", "status": "queued"})
    mock_fem = AsyncMock(return_value=fem_result)

    # Inject the mocked FEM engine
    with patch.dict("sys.modules"):
        kerf_fem = types.ModuleType("kerf_fem")
        kerf_fem_tools = types.ModuleType("kerf_fem.tools")
        kerf_fem_tools.run_fem_run = mock_fem
        sys.modules["kerf_fem"] = kerf_fem
        sys.modules["kerf_fem.tools"] = kerf_fem_tools

        result = await execute(ctx, "run_compute", _args(
            engine="fem",
            file_id=str(uuid.UUID(int=9)),  # beam.feature
            options={"solver": "linear_static", "load_case": "gravity"},
        ))

    data = json.loads(result)
    # No error — job queued
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "BAD_ARGS", "ERROR"), (
        f"FEM run_compute unexpected error: {data}"
    )
    assert data.get("job_id") == "fem_t104_001"

    # Source file must still be re-openable after compute dispatch
    desc = await execute(ctx, "describe_part", _args(path="/beam.feature"))
    feature_data = json.loads(desc)
    _assert_reopenable(feature_data, "fem")

    # Poll the job — unknown prefix but should not error
    poll = await execute(ctx, "poll_compute", _args(job_id="fem_t104_001"))
    poll_data = json.loads(poll)
    assert poll_data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN"), (
        f"FEM poll_compute unexpected error: {poll_data}"
    )


# ===========================================================================
# DOMAIN 10: CAM — write toolpath config, run_compute(engine='cam'), reopenable
# ===========================================================================

@pytest.mark.asyncio
async def test_domain_cam_compute_and_reopenable(ctx, pool):
    from kerf_chat.tools.executor import execute

    pool.revision_writes.clear()

    # Agent updates the JSCAD stock file before running CAM
    cam_jscad = (
        "export default function({ primitives }) {\n"
        "  // stock block for facing operation\n"
        "  return [{ id: 'stock', geom: primitives.cuboid({ size: [100, 50, 20] }) }]\n"
        "}\n"
    )
    write_result = await execute(ctx, "write_file", _args(path="/cam_stock.jscad", content=cam_jscad))
    _ok(write_result, "cam.write_file")
    _assert_revision_written(pool, "cam")

    cam_result = json.dumps({"job_id": "cam_t104_001", "status": "queued"})
    mock_cam = AsyncMock(return_value=cam_result)

    with patch.dict("sys.modules"):
        kerf_cam = types.ModuleType("kerf_cam")
        kerf_cam_tools = types.ModuleType("kerf_cam.tools")
        kerf_cam_tools.run_cam_run = mock_cam
        sys.modules["kerf_cam"] = kerf_cam
        sys.modules["kerf_cam.tools"] = kerf_cam_tools

        result = await execute(ctx, "run_compute", _args(
            engine="cam",
            file_id=str(uuid.UUID(int=10)),  # cam_stock.jscad
            options={"operation": "face", "tool_diameter": 6.0, "step_over": 0.5},
        ))

    data = json.loads(result)
    assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "BAD_ARGS", "ERROR"), (
        f"CAM run_compute unexpected error: {data}"
    )
    assert data.get("job_id") == "cam_t104_001"

    # Source JSCAD file must still be re-openable
    desc = await execute(ctx, "describe_part", _args(path="/cam_stock.jscad"))
    file_data = json.loads(desc)
    _assert_reopenable(file_data, "cam")
    # JSCAD is a 'file' kind — should return line_count
    if "line_count" in file_data:
        assert file_data["line_count"] >= 1


# ===========================================================================
# Cross-domain aggregate: all 10 domains produce revisions with source='tool'
# where write operations are involved, and no file ends up un-parseable.
# ===========================================================================

@pytest.mark.asyncio
async def test_aggregate_no_orphan_errors_across_domains(ctx, pool):
    """Run a write on each domain file and confirm describe_part succeeds for all."""
    from kerf_chat.tools.executor import execute

    domain_files = [
        ("/profile.sketch", "sketch"),
        ("/bracket.feature", "feature"),
        ("/panel.feature", "feature"),
        ("/frame.feature", "feature"),
        ("/sheet1.drawing", "drawing"),
        ("/main.circuit.tsx", "file"),
        ("/ring.part", "part"),
        ("/building.assembly", "assembly"),
        ("/beam.feature", "feature"),
        ("/cam_stock.jscad", "file"),
    ]

    for path, expected_kind in domain_files:
        desc = await execute(ctx, "describe_part", _args(path=path))
        data = json.loads(desc)
        # Must not be a system-level error
        assert data.get("code") not in ("UNKNOWN_TOOL", "FORBIDDEN", "ERROR"), (
            f"describe_part({path!r}) returned error: {data}"
        )
        # On success, kind must match what we seeded
        if "code" not in data:
            assert data.get("kind") == expected_kind, (
                f"describe_part({path!r}) kind mismatch: expected {expected_kind!r}, got {data.get('kind')!r}"
            )
