"""test_element_types.py — pytest suite for element_types.py LLM tools."""
import importlib.util
import sys
import types
import json
import asyncio


_spec = importlib.util.spec_from_file_location(
    "tools.element_types", "/Users/pc/code/exo/kerf/.claude/worktrees/agent-a32c4befabb8b2b49/kerf-bim/src/kerf_bim/tools/element_types.py"
)
_reg_stub = types.ModuleType("tools.registry")
_reg_stub.ToolSpec = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_reg_stub.err_payload = lambda msg, code: json.dumps({"error": msg, "code": code})
_reg_stub.ok_payload = lambda v: json.dumps(v)
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)

_ctxt_stub = types.ModuleType("tools.context")
_ctxt_stub.ProjectCtx = type("ProjectCtx", (), {})

_bim_stub = types.ModuleType("tools.bim")
_bim_stub.resolve_path = lambda ctx, path: {"exists": False}
async def _record_revision_for_file(ctx, fid, body, src): return None
_bim_stub.record_revision_for_file = _record_revision_for_file

_prev_reg = sys.modules.get("tools.registry")
_prev_ctxt = sys.modules.get("tools.context")
_prev_bim = sys.modules.get("tools.bim")
sys.modules["tools.registry"] = _reg_stub
sys.modules["tools.context"] = _ctxt_stub
sys.modules["tools.bim"] = _bim_stub

_mod = importlib.util.module_from_spec(_spec)
sys.modules["tools.element_types"] = _mod
_spec.loader.exec_module(_mod)

_run_bulk = _mod.run_bulk_set_type_param
_run_apply = _mod.run_apply_type_to_instance
_run_report = _mod.run_report_type_usage
_run_clone = _mod.run_clone_type
_run_delete = _mod.run_delete_type

if _prev_reg:
    sys.modules["tools.registry"] = _prev_reg
else:
    del sys.modules["tools.registry"]
if _prev_ctxt:
    sys.modules["tools.context"] = _prev_ctxt
else:
    del sys.modules["tools.context"]
if _prev_bim:
    sys.modules["tools.bim"] = _prev_bim
else:
    del sys.modules["tools.bim"]

_run_bulk = _mod.run_bulk_set_type_param
_run_apply = _mod.run_apply_type_to_instance
_run_report = _mod.run_report_type_usage
_run_clone = _mod.run_clone_type
_run_delete = _mod.run_delete_type


def _run(coro):
    return asyncio.run(coro)


class MockPool:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.executed = []

    @staticmethod
    def _normalize(q, a):
        if "$1" in q and a:
            idx = 0
            while f"${idx+1}" in q:
                q = q.replace(f"${idx+1}", str(a[idx]))
                idx += 1
        return q

    async def fetchrow(self, q, *a):
        q_str = self._normalize(q, a)
        for r in self._rows:
            if r[0] == q_str:
                return r[1]
        return None

    async def fetch(self, q, *a):
        return [r[1] for r in self._rows if len(r) > 1]

    async def execute(self, q, *a):
        self.executed.append((q, a))


class MockCtx:
    def __init__(self, pool, project_id="proj-1"):
        self.pool = pool
        self.project_id = project_id


WINDOW_FAMILY = {
    "version": 1,
    "name": "GenericWindow",
    "category": "Window",
    "params": [
        {"name": "Width", "type": "number", "default": 600, "min": 100, "max": 5000},
        {"name": "Glazing", "type": "enum", "options": ["single", "double", "triple"], "default": "double"},
    ],
    "types": [
        {"id": "type-600x900", "name": "600x900 Standard", "params": {"Width": 600, "Glazing": "double"}},
        {"id": "type-900x1200", "name": "900x1200 Large", "params": {"Width": 900, "Glazing": "double"}},
    ],
}

BIM_DOC = {
    "instances": [
        {"id": "inst-1", "type": "instance", "family_id": "00000000-0000-0000-0000-000000000001", "type_id": "type-600x900", "params": {}},
        {"id": "inst-2", "type": "instance", "family_id": "00000000-0000-0000-0000-000000000001", "type_id": "type-600x900", "params": {"Width": 650}},
    ]
}

FAM_ID = "00000000-0000-0000-0000-000000000001"
BIM_ID = "00000000-0000-0000-0000-000000000002"


class TestBulkSetTypeParam:
    @staticmethod
    def _make_ctx(fam_doc=None):
        rows = []
        if fam_doc:
            q = "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'family' AND deleted_at IS NULL"
            q_norm = q.replace("$1", FAM_ID).replace("$2", "proj-1")
            rows.append((q_norm, {"content": json.dumps(fam_doc)}))
        pool = MockPool(rows)
        return MockCtx(pool)

    def test_sets_type_param_value(self):
        ctx = self._make_ctx(WINDOW_FAMILY)
        r = _run(_run_bulk(ctx, json.dumps({"family_file_id": FAM_ID, "type_id": "type-600x900", "param_name": "Glazing", "value": "triple"}).encode()))
        out = json.loads(r)
        assert out.get("param_name") == "Glazing"
        assert out.get("value") == "triple"

    def test_bad_family_id(self):
        ctx = self._make_ctx()
        r = _run(_run_bulk(ctx, json.dumps({"family_file_id": "not-a-uuid", "type_id": "t1", "param_name": "p", "value": 1}).encode()))
        out = json.loads(r)
        assert "error" in out

    def test_family_not_found(self):
        ctx = self._make_ctx()
        r = _run(_run_bulk(ctx, json.dumps({"family_file_id": FAM_ID, "type_id": "type-600x900", "param_name": "Width", "value": 800}).encode()))
        out = json.loads(r)
        assert "error" in out

    def test_type_not_found(self):
        ctx = self._make_ctx(WINDOW_FAMILY)
        r = _run(_run_bulk(ctx, json.dumps({"family_file_id": FAM_ID, "type_id": "type-missing", "param_name": "Width", "value": 800}).encode()))
        out = json.loads(r)
        assert "error" in out

    def test_enum_value_validation(self):
        ctx = self._make_ctx(WINDOW_FAMILY)
        r = _run(_run_bulk(ctx, json.dumps({"family_file_id": FAM_ID, "type_id": "type-600x900", "param_name": "Glazing", "value": "quadruple"}).encode()))
        out = json.loads(r)
        assert "error" in out


class TestApplyTypeToInstance:
    @staticmethod
    def _make_ctx(fam_doc=None, bim_doc=None):
        rows = []
        if fam_doc:
            q = "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'family' AND deleted_at IS NULL"
            q_norm = q.replace("$1", FAM_ID).replace("$2", "proj-1")
            rows.append((q_norm, {"content": json.dumps(fam_doc)}))
        if bim_doc:
            q = "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'bim' AND deleted_at IS NULL"
            q_norm = q.replace("$1", BIM_ID).replace("$2", "proj-1")
            rows.append((q_norm, {"content": json.dumps(bim_doc)}))
        pool = MockPool(rows)
        return MockCtx(pool)

    def test_swaps_instance_type(self):
        ctx = self._make_ctx(WINDOW_FAMILY, BIM_DOC)
        r = _run(_run_apply(ctx, json.dumps({"host_file_id": BIM_ID, "instance_id": "inst-1", "type_id": "type-900x1200"}).encode()))
        out = json.loads(r)
        assert out.get("type_id") == "type-900x1200"
        assert out.get("instance_id") == "inst-1"

    def test_instance_not_found(self):
        ctx = self._make_ctx(WINDOW_FAMILY, BIM_DOC)
        r = _run(_run_apply(ctx, json.dumps({"host_file_id": BIM_ID, "instance_id": "inst-missing", "type_id": "type-900x1200"}).encode()))
        out = json.loads(r)
        assert "error" in out


class TestReportTypeUsage:
    @staticmethod
    def _make_ctx(fam_doc=None, bim_docs=None):
        rows = []
        if fam_doc:
            q = "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'family' AND deleted_at IS NULL"
            q_norm = q.replace("$1", FAM_ID).replace("$2", "proj-1")
            rows.append((q_norm, {"content": json.dumps(fam_doc)}))
        if bim_docs:
            q = "SELECT id, content FROM files WHERE project_id = $1 AND kind = 'bim' AND deleted_at IS NULL"
            q_norm = q.replace("$1", "proj-1")
            for bd in bim_docs:
                rows.append((q_norm, {"id": BIM_ID, "content": json.dumps(bd)}))
        pool = MockPool(rows)
        return MockCtx(pool)

    def test_counts_instances(self):
        ctx = self._make_ctx(WINDOW_FAMILY, [BIM_DOC])
        r = _run(_run_report(ctx, json.dumps({"family_file_id": FAM_ID, "type_id": "type-600x900"}).encode()))
        out = json.loads(r)
        assert out.get("total") == 2

    def test_returns_by_host(self):
        ctx = self._make_ctx(WINDOW_FAMILY, [BIM_DOC])
        r = _run(_run_report(ctx, json.dumps({"family_file_id": FAM_ID, "type_id": "type-600x900"}).encode()))
        out = json.loads(r)
        assert len(out.get("by_host", [])) == 1


class TestCloneType:
    @staticmethod
    def _make_ctx(fam_doc=None):
        rows = []
        if fam_doc:
            q = "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'family' AND deleted_at IS NULL"
            q_norm = q.replace("$1", FAM_ID).replace("$2", "proj-1")
            rows.append((q_norm, {"content": json.dumps(fam_doc)}))
        pool = MockPool(rows)
        return MockCtx(pool)

    def test_duplicates_type(self):
        ctx = self._make_ctx(WINDOW_FAMILY)
        r = _run(_run_clone(ctx, json.dumps({"family_file_id": FAM_ID, "source_type_id": "type-600x900", "new_name": "600x900 Copy"}).encode()))
        out = json.loads(r)
        assert out["new_type"]["name"] == "600x900 Copy"
        assert out["new_type"]["params"]["Width"] == 600

    def test_source_type_not_found(self):
        ctx = self._make_ctx(WINDOW_FAMILY)
        r = _run(_run_clone(ctx, json.dumps({"family_file_id": FAM_ID, "source_type_id": "type-missing", "new_name": "Copy"}).encode()))
        out = json.loads(r)
        assert "error" in out


class TestDeleteType:
    @staticmethod
    def _make_ctx(fam_doc=None, bim_docs=None):
        rows = []
        if fam_doc:
            q = "SELECT content FROM files WHERE id = $1 AND project_id = $2 AND kind = 'family' AND deleted_at IS NULL"
            q_norm = q.replace("$1", FAM_ID).replace("$2", "proj-1")
            rows.append((q_norm, {"content": json.dumps(fam_doc)}))
        if bim_docs:
            q = "SELECT id, content FROM files WHERE project_id = $1 AND kind = 'bim' AND deleted_at IS NULL"
            q_norm = q.replace("$1", "proj-1")
            for bd in bim_docs:
                rows.append((q_norm, {"id": BIM_ID, "content": json.dumps(bd)}))
        pool = MockPool(rows)
        return MockCtx(pool)

    def test_deletes_type(self):
        ctx = self._make_ctx(WINDOW_FAMILY)
        r = _run(_run_delete(ctx, json.dumps({"family_file_id": FAM_ID, "type_id": "type-600x900"}).encode()))
        out = json.loads(r)
        assert out.get("deleted_type_id") == "type-600x900"
        assert out.get("reassigned_to") is None

    def test_deletes_with_reassign(self):
        ctx = self._make_ctx(WINDOW_FAMILY, [BIM_DOC])
        r = _run(_run_delete(ctx, json.dumps({"family_file_id": FAM_ID, "type_id": "type-600x900", "reassign_to": "type-900x1200"}).encode()))
        out = json.loads(r)
        assert out.get("deleted_type_id") == "type-600x900"
        assert out.get("reassigned_to") == "type-900x1200"
        assert out.get("reassigned_instance_count") == 2


if __name__ == "__main__":
    import unittest
    unittest.main()