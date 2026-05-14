"""test_import_3dm.py — pytest suite for import_3dm and export_3dm LLM tools.

Uses the importlib.util.spec_from_file_location + stub pattern from test_erc.py
so the full tools package init (which needs a live DB) is never triggered.
"""
import importlib.util
import json
import sys
import types
import unittest
import uuid


# ---------------------------------------------------------------------------
# Load tools.import_3dm with stubs
# ---------------------------------------------------------------------------

def _load_module():
    """Load import_3dm with minimal stubs for its dependencies."""
    # Stub tools.registry
    reg_stub = types.ModuleType("tools.registry")
    reg_stub.ToolSpec = type(
        "ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)}
    )
    reg_stub.err_payload = lambda msg, code: json.dumps({"error": msg, "code": code})
    reg_stub.ok_payload = lambda v: json.dumps(v)
    reg_stub.register = lambda spec, write=False: (lambda fn: fn)

    # Stub tools.context
    ctx_stub = types.ModuleType("tools.context")

    class _ProjectCtx:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    ctx_stub.ProjectCtx = _ProjectCtx

    prev_reg = sys.modules.get("tools.registry")
    prev_ctx = sys.modules.get("tools.context")
    prev_tools = sys.modules.get("tools")

    sys.modules["tools.registry"] = reg_stub
    sys.modules["tools.context"] = ctx_stub
    # Only set tools to a bare module if it isn't already the real package;
    # replacing the real package breaks every subsequent direct-import test.
    if prev_tools is None or not hasattr(prev_tools, "__path__"):
        sys.modules["tools"] = types.ModuleType("tools")

    spec = importlib.util.spec_from_file_location(
        "tools.import_3dm",
        "/Users/pc/code/exo/kerf/.claude/worktrees/agent-a32c4befabb8b2b49/kerf-imports/src/kerf_imports/tools/import_3dm.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Restore or clean up stubs
    for key, prev in (
        ("tools.registry", prev_reg),
        ("tools.context", prev_ctx),
        ("tools", prev_tools),
    ):
        if prev is not None:
            sys.modules[key] = prev
        else:
            sys.modules.pop(key, None)

    return mod


_mod = _load_module()
_import_3dm = _mod.import_3dm
_export_3dm = _mod.export_3dm
_ensure_folder = _mod._ensure_folder


# ---------------------------------------------------------------------------
# Async test runner helper
# ---------------------------------------------------------------------------

import asyncio


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Fake context helpers
# ---------------------------------------------------------------------------

class _FakeStorage:
    def __init__(self, data: bytes = b""):
        self._data = data
        self.put_calls = []

    async def get(self, key):
        return self._data

    async def put(self, key, data, content_type=None):
        self.put_calls.append((key, data))

    async def presign(self, key, expires=3600):
        return f"https://cdn.example.com/{key}?token=x"


class _FakePool:
    """Minimal asyncpg-pool stub that records queries and returns preset rows."""

    def __init__(self):
        self._fetchrow_results = []
        self._fetchval_results = []
        self.execute_calls = []

    def queue_fetchrow(self, row):
        self._fetchrow_results.append(row)

    def queue_fetchval(self, val):
        self._fetchval_results.append(val)

    async def fetchrow(self, query, *args):
        if self._fetchrow_results:
            return self._fetchrow_results.pop(0)
        return None

    async def fetchval(self, query, *args):
        if self._fetchval_results:
            return self._fetchval_results.pop(0)
        return uuid.uuid4()

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


def _ctx(**kw):
    import types as _t
    defaults = dict(
        pool=_FakePool(),
        storage=_FakeStorage(),
        project_id=uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"),
        user_id=uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002"),
        role="owner",
        http_client=None,
        file_revisions_max=0,
    )
    defaults.update(kw)
    return _t.SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Arg-validation tests
# ---------------------------------------------------------------------------

class TestImport3dmArgValidation(unittest.TestCase):

    def test_missing_project_id(self):
        ctx = _ctx()
        result = json.loads(_run(
            _import_3dm(ctx, json.dumps({"file_blob_id_or_storage_key": "k1"}).encode())
        ))
        self.assertIn("error", result)
        self.assertEqual(result["code"], "BAD_ARGS")

    def test_missing_blob_ref(self):
        ctx = _ctx()
        result = json.loads(_run(
            _import_3dm(ctx, json.dumps({"project_id": "proj-1"}).encode())
        ))
        self.assertIn("error", result)
        self.assertEqual(result["code"], "BAD_ARGS")

    def test_invalid_json(self):
        ctx = _ctx()
        result = json.loads(_run(_import_3dm(ctx, b"not-json")))
        self.assertIn("error", result)
        self.assertEqual(result["code"], "BAD_ARGS")

    def test_no_storage(self):
        ctx = _ctx(storage=None)
        result = json.loads(_run(
            _import_3dm(
                ctx,
                json.dumps({
                    "project_id": "proj-1",
                    "file_blob_id_or_storage_key": "key1",
                }).encode(),
            )
        ))
        self.assertIn("error", result)
        self.assertEqual(result["code"], "NO_STORAGE")


class TestExport3dmArgValidation(unittest.TestCase):

    def test_missing_project_id(self):
        ctx = _ctx()
        result = json.loads(_run(
            _export_3dm(ctx, json.dumps({"file_ids": ["id1"]}).encode())
        ))
        self.assertIn("error", result)
        self.assertEqual(result["code"], "BAD_ARGS")

    def test_missing_file_ids(self):
        ctx = _ctx()
        result = json.loads(_run(
            _export_3dm(ctx, json.dumps({"project_id": "proj-1"}).encode())
        ))
        self.assertIn("error", result)
        self.assertEqual(result["code"], "BAD_ARGS")

    def test_empty_file_ids(self):
        ctx = _ctx()
        result = json.loads(_run(
            _export_3dm(
                ctx,
                json.dumps({"project_id": "proj-1", "file_ids": []}).encode(),
            )
        ))
        self.assertIn("error", result)
        self.assertEqual(result["code"], "BAD_ARGS")

    def test_no_storage(self):
        ctx = _ctx(storage=None)
        result = json.loads(_run(
            _export_3dm(
                ctx,
                json.dumps({
                    "project_id": "proj-1",
                    "file_ids": [str(uuid.uuid4())],
                }).encode(),
            )
        ))
        self.assertIn("error", result)
        self.assertEqual(result["code"], "NO_STORAGE")

    def test_invalid_json(self):
        ctx = _ctx()
        result = json.loads(_run(_export_3dm(ctx, b"{bad")))
        self.assertIn("error", result)
        self.assertEqual(result["code"], "BAD_ARGS")


# ---------------------------------------------------------------------------
# Happy path — mocked pyworker
# ---------------------------------------------------------------------------

class TestImport3dmHappyPath(unittest.TestCase):

    def _make_pyworker_response(self):
        """Return a fake /import-3dm response with mixed object kinds."""
        return {
            "layers": [{"id": "l1", "name": "Walls", "full_path": "Walls"}],
            "files": [
                {
                    "name": "wall0.feature",
                    "kind": "feature",
                    "content": {
                        "source": "rhino3dm",
                        "kind": "feature",
                        "rhino_layer": "Walls",
                    },
                },
                {
                    "name": "profile0.sketch",
                    "kind": "sketch",
                    "content": {
                        "source": "rhino3dm",
                        "kind": "sketch",
                        "rhino_layer": "Walls",
                    },
                },
                {
                    "name": "mesh0.mesh",
                    "kind": "mesh",
                    "content": {"source": "rhino3dm", "kind": "mesh"},
                },
            ],
            "stats": {"count_by_kind": {"feature": 1, "sketch": 1, "mesh": 1}},
            "errors": [],
        }

    def test_happy_path_creates_files(self):
        """Mocks pyworker response; verifies created_files and stats are returned."""
        import unittest.mock as mock

        fake_response = mock.MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = self._make_pyworker_response()

        fake_client = mock.AsyncMock()
        fake_client.__aenter__ = mock.AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = mock.AsyncMock(return_value=False)
        fake_client.post = mock.AsyncMock(return_value=fake_response)

        blob_bytes = b"fake-3dm-content"
        ctx = _ctx(storage=_FakeStorage(data=blob_bytes))
        # Pre-queue fetchval responses for folder + 3 files
        for _ in range(4):
            ctx.pool.queue_fetchval(uuid.uuid4())

        with mock.patch("httpx.AsyncClient", return_value=fake_client):
            result = json.loads(_run(
                _import_3dm(
                    ctx,
                    json.dumps({
                        "project_id": str(ctx.project_id),
                        "file_blob_id_or_storage_key": "blobs/model.3dm",
                    }).encode(),
                )
            ))

        self.assertNotIn("error", result)
        self.assertIn("created_files", result)
        self.assertEqual(len(result["created_files"]), 3)
        kinds = {f["rhino_kind"] for f in result["created_files"]}
        self.assertIn("feature", kinds)
        self.assertIn("sketch", kinds)
        self.assertIn("mesh", kinds)
        self.assertEqual(result["stats"]["count_by_kind"]["feature"], 1)

    def test_pyworker_error_propagated(self):
        import unittest.mock as mock

        fake_response = mock.MagicMock()
        fake_response.status_code = 500
        fake_response.text = "internal error"

        fake_client = mock.AsyncMock()
        fake_client.__aenter__ = mock.AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = mock.AsyncMock(return_value=False)
        fake_client.post = mock.AsyncMock(return_value=fake_response)

        ctx = _ctx(storage=_FakeStorage(data=b"data"))

        with mock.patch("httpx.AsyncClient", return_value=fake_client):
            result = json.loads(_run(
                _import_3dm(
                    ctx,
                    json.dumps({
                        "project_id": str(ctx.project_id),
                        "file_blob_id_or_storage_key": "blobs/bad.3dm",
                    }).encode(),
                )
            ))

        self.assertIn("error", result)
        self.assertEqual(result["code"], "PYWORKER_ERROR")


if __name__ == "__main__":
    unittest.main()
