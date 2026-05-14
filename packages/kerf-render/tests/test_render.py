"""
test_render.py — pytest suite for tools/render.py.

Uses importlib.util.spec_from_file_location to load the module without
triggering the tools/__init__.py database chain (same pattern as test_mesh.py).
"""

import asyncio
import importlib.util
import json
import os
import sys
import types
import uuid

_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "backend")
_PLUGIN_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "kerf_render")


def _load(rel):
    path = os.path.join(_BACKEND, rel)
    spec = importlib.util.spec_from_file_location(
        rel.replace("/", ".").replace(".py", ""), path
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_plugin(filename):
    path = os.path.join(_PLUGIN_TOOLS, filename)
    name = "tools." + filename.replace(".py", "")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_registry_mod = sys.modules.get("tools.registry") or _load("tools/registry.py")
_context_mod  = sys.modules.get("tools.context")  or _load("tools/context.py")
sys.modules.setdefault("tools.registry", _registry_mod)
sys.modules.setdefault("tools.context",  _context_mod)

_render_mod = _load_plugin("tools.py")

# Expose symbols under test
_default_render_doc       = _render_mod._default_render_doc
_parse                    = _render_mod._parse
_serialize                = _render_mod._serialize
create_render             = _render_mod.create_render
set_render_camera         = _render_mod.set_render_camera
add_render_light          = _render_mod.add_render_light
set_render_material_override = _render_mod.set_render_material_override
run_render                = _render_mod.run_render

ProjectCtx = _context_mod.ProjectCtx


# ─── helpers ──────────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakePool:
    """Minimal async pool stub that stores in-memory records."""

    def __init__(self, rows=None):
        self._rows = rows or {}   # uuid → dict

    async def fetchrow(self, query, *args):
        q = query.lower()
        if "files" in q and args:
            fid = args[0]
            return self._rows.get(str(fid))
        return None

    async def fetchval(self, query, *args):
        return "/"

    async def execute(self, query, *args):
        q = query.lower()
        if "insert into files" in q:
            row_id = args[0]
            content = args[5]
            self._rows[str(row_id)] = {
                "id": row_id,
                "kind": "render",
                "content": content,
            }
        elif "update files" in q:
            content = args[0]
            fid = args[1]
            if str(fid) in self._rows:
                self._rows[str(fid)]["content"] = content


class FakeHttpClient:
    """Simulates pyworker unavailable."""

    def post(self, url, **kwargs):
        raise ConnectionRefusedError("pyworker not running")


class FakeHttpClientOk:
    """Simulates a successful pyworker response."""

    def __init__(self, output_b64="aGVsbG8=", fmt="png", seconds=2.5):
        self._b64 = output_b64
        self._fmt = fmt
        self._seconds = seconds

    class _Resp:
        status_code = 200

        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    def post(self, url, **kwargs):
        return self._Resp({
            "status": "ok",
            "output_b64": self._b64,
            "format": self._fmt,
            "render_seconds": self._seconds,
        })


def make_ctx(rows=None, http_client=None):
    return ProjectCtx(
        pool=FakePool(rows or {}),
        storage=None,
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="editor",
        http_client=http_client or FakeHttpClient(),
    )


def make_render_row(content=None):
    fid = uuid.uuid4()
    if content is None:
        content = json.dumps(_default_render_doc("scene-uuid-001"))
    return fid, {str(fid): {"id": fid, "kind": "render", "content": content}}


# ─── _default_render_doc ──────────────────────────────────────────────────────

def test_default_render_doc_version():
    doc = _default_render_doc("some-uuid")
    assert doc["version"] == 1


def test_default_render_doc_scene_file_id():
    doc = _default_render_doc("abc-123", "My Render")
    assert doc["scene_file_id"] == "abc-123"
    assert doc["name"] == "My Render"


def test_default_render_doc_has_three_lights():
    doc = _default_render_doc("x")
    assert len(doc["lights"]) == 3


def test_default_render_doc_camera_perspective():
    doc = _default_render_doc("x")
    assert doc["camera"]["type"] == "perspective"
    assert doc["camera"]["fov_deg"] == 45


def test_default_render_doc_render_settings():
    doc = _default_render_doc("x")
    assert doc["render_settings"]["resolution"] == [1920, 1080]
    assert doc["render_settings"]["samples"] == 128
    assert doc["render_settings"]["denoise"] is True
    assert doc["render_settings"]["output_format"] == "png"


# ─── _parse / _serialize ──────────────────────────────────────────────────────

def test_parse_empty_returns_default():
    doc = _parse("")
    assert doc["version"] == 1


def test_parse_valid_json():
    original = _default_render_doc("uuid-abc")
    serialized = _serialize(original)
    parsed = _parse(serialized)
    assert parsed["scene_file_id"] == "uuid-abc"


def test_serialize_roundtrip():
    doc = _default_render_doc("uuid-xyz")
    s = _serialize(doc)
    assert isinstance(s, str)
    back = json.loads(s)
    assert back["version"] == 1


# ─── create_render ────────────────────────────────────────────────────────────

def test_create_render_ok():
    ctx = make_ctx()
    resp = run(create_render(ctx, json.dumps({
        "scene_file_id": "feature-uuid-001",
        "name": "Hero",
    }).encode()))
    data = json.loads(resp)
    assert "error" not in data
    assert data["name"] == "Hero"
    assert "file_id" in data


def test_create_render_missing_scene_file_id():
    ctx = make_ctx()
    resp = run(create_render(ctx, json.dumps({}).encode()))
    data = json.loads(resp)
    assert "error" in data
    assert data["code"] == "BAD_ARGS"


def test_create_render_custom_resolution():
    ctx = make_ctx()
    resp = run(create_render(ctx, json.dumps({
        "scene_file_id": "x",
        "resolution": [3840, 2160],
        "samples": 256,
    }).encode()))
    data = json.loads(resp)
    assert "error" not in data


# ─── set_render_camera ────────────────────────────────────────────────────────

def test_set_render_camera_updates_position():
    fid, rows = make_render_row()
    ctx = make_ctx(rows)
    resp = run(set_render_camera(ctx, json.dumps({
        "file_id": str(fid),
        "position": [5000, -5000, 3000],
        "target": [0, 0, 0],
        "fov_deg": 35.0,
    }).encode()))
    data = json.loads(resp)
    assert "error" not in data
    assert data["camera"]["position"] == [5000, -5000, 3000]
    assert data["camera"]["fov_deg"] == 35.0


def test_set_render_camera_not_found():
    ctx = make_ctx()
    resp = run(set_render_camera(ctx, json.dumps({
        "file_id": str(uuid.uuid4()),
        "position": [0, 0, 1000],
        "target": [0, 0, 0],
    }).encode()))
    data = json.loads(resp)
    assert "error" in data
    assert data["code"] == "NOT_FOUND"


def test_set_render_camera_wrong_kind():
    fid = uuid.uuid4()
    rows = {str(fid): {"id": fid, "kind": "feature", "content": "{}"}}
    ctx = make_ctx(rows)
    resp = run(set_render_camera(ctx, json.dumps({
        "file_id": str(fid),
        "position": [0, 0, 1000],
        "target": [0, 0, 0],
    }).encode()))
    data = json.loads(resp)
    assert "error" in data
    assert data["code"] == "BAD_KIND"


# ─── add_render_light ─────────────────────────────────────────────────────────

def test_add_render_light_sun():
    fid, rows = make_render_row()
    ctx = make_ctx(rows)
    resp = run(add_render_light(ctx, json.dumps({
        "file_id": str(fid),
        "id": "rim",
        "kind": "sun",
        "direction": [0, 1, -1],
        "intensity": 3.0,
        "color": "#ffccaa",
    }).encode()))
    data = json.loads(resp)
    assert "error" not in data
    assert data["light"]["kind"] == "sun"
    assert data["light_count"] == 4  # 3 defaults + 1


def test_add_render_light_area():
    fid, rows = make_render_row()
    ctx = make_ctx(rows)
    resp = run(add_render_light(ctx, json.dumps({
        "file_id": str(fid),
        "kind": "area",
        "position": [2000, -1000, 3000],
        "size_mm": 500,
        "intensity": 4.0,
    }).encode()))
    data = json.loads(resp)
    assert "error" not in data
    assert data["light"]["size_mm"] == 500.0


# ─── set_render_material_override ─────────────────────────────────────────────

def test_set_material_override_wildcard():
    fid, rows = make_render_row()
    ctx = make_ctx(rows)
    resp = run(set_render_material_override(ctx, json.dumps({
        "file_id": str(fid),
        "target_pattern": "*",
        "material": {
            "kind": "principled",
            "base_color": "#ff0000",
            "roughness": 0.2,
            "metallic": 0.8,
        },
    }).encode()))
    data = json.loads(resp)
    assert "error" not in data
    assert data["material"]["base_color"] == "#ff0000"


# ─── run_render — blender missing path (via pyworker unavailable) ──────────────

def test_run_render_worker_unavailable():
    """When pyworker is down the tool returns a clear error."""
    scene_fid = uuid.uuid4()
    render_doc = _default_render_doc(str(scene_fid))
    render_fid = uuid.uuid4()
    rows = {
        str(render_fid): {"id": render_fid, "kind": "render", "content": json.dumps(render_doc)},
        str(scene_fid): {"id": scene_fid, "kind": "mesh", "content": "v 0 0 0"},
    }
    ctx = make_ctx(rows, http_client=FakeHttpClient())
    resp = run(run_render(ctx, json.dumps({"file_id": str(render_fid)}).encode()))
    data = json.loads(resp)
    assert "error" in data
    assert data["code"] == "WORKER_UNAVAILABLE"


def test_run_render_missing_file_id():
    ctx = make_ctx()
    resp = run(run_render(ctx, json.dumps({}).encode()))
    data = json.loads(resp)
    assert "error" in data
    assert data["code"] == "BAD_ARGS"


def test_run_render_not_found():
    ctx = make_ctx()
    resp = run(run_render(ctx, json.dumps({"file_id": str(uuid.uuid4())}).encode()))
    data = json.loads(resp)
    assert "error" in data
    assert data["code"] == "NOT_FOUND"


def test_run_render_ok_with_fake_worker():
    """Successful render path: worker returns b64 image."""
    scene_fid = uuid.uuid4()
    render_fid = uuid.uuid4()
    render_doc = _default_render_doc(str(scene_fid))
    rows = {
        str(render_fid): {"id": render_fid, "kind": "render", "content": json.dumps(render_doc)},
        str(scene_fid): {"id": scene_fid, "kind": "mesh", "content": "v 0 0 0"},
    }
    ctx = make_ctx(rows, http_client=FakeHttpClientOk())
    resp = run(run_render(ctx, json.dumps({"file_id": str(render_fid)}).encode()))
    data = json.loads(resp)
    assert "error" not in data
    assert data["format"] == "png"
    assert data["output_b64"] == "aGVsbG8="
    assert data["render_seconds"] == 2.5
