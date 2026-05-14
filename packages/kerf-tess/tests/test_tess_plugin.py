"""
Tests for kerf_tess plugin.

Designed to pass without Node.js, pythonOCC, or a real database:
- Plugin registration is tested with mocked app and context.
- Route schema is validated via TestClient.
- Worker class instantiation is tested with a mock pool.
- TessInputSpec round-trip is tested.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Also need kerf_cad_core on the path for the _OCC_AVAILABLE import in plugin.py
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "kerf-cad-core", "src"),
)

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── TessInputSpec ─────────────────────────────────────────────────────────────

def test_tess_input_spec_defaults():
    from kerf_tess.specs import TessInputSpec
    spec = TessInputSpec()
    assert spec.resolution == 50000
    assert spec.export_format == "glb"
    assert spec.scale == 1.0


def test_tess_input_spec_round_trip():
    from kerf_tess.specs import TessInputSpec
    original = TessInputSpec(resolution=10000, export_format="glb", scale=2.5)
    restored = TessInputSpec.from_dict(original.to_dict())
    assert restored.resolution == 10000
    assert restored.export_format == "glb"
    assert restored.scale == 2.5


def test_tess_input_spec_from_empty_dict():
    from kerf_tess.specs import TessInputSpec
    spec = TessInputSpec.from_dict({})
    assert spec.resolution == 50000
    assert spec.scale == 1.0


# ── Routes import ─────────────────────────────────────────────────────────────

def test_routes_importable():
    from kerf_tess.routes import router
    assert router is not None


def test_run_tess_route_registered():
    from kerf_tess.routes import router
    paths = [route.path for route in router.routes]
    assert "/run-tess" in paths


# ── HTTP route — bad input ────────────────────────────────────────────────────

def test_run_tess_missing_step_b64():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from kerf_tess.routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/run-tess", json={"step_b64": ""})
    assert resp.status_code == 400


def test_run_tess_invalid_base64():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from kerf_tess.routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.post("/run-tess", json={"step_b64": "not-valid-base64!!!"})
    assert resp.status_code == 400


# ── Plugin registration ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_plugin_register_mounts_route():
    from fastapi import FastAPI
    from kerf_tess.plugin import register

    app = FastAPI()
    ctx = MagicMock()
    ctx.cloud_enabled = False
    ctx.local_mode = True
    ctx.workers = None

    manifest = await register(app, ctx)

    assert manifest.name == "tess"
    assert manifest.version == "0.1.0"
    assert "cad-core" in manifest.depends

    # Route should be present
    paths = [r.path for r in app.routes]
    assert "/run-tess" in paths


@pytest.mark.asyncio
async def test_plugin_register_cloud_mode_registers_worker():
    from fastapi import FastAPI
    from kerf_tess.plugin import register

    app = FastAPI()
    ctx = MagicMock()
    ctx.cloud_enabled = True
    ctx.local_mode = False
    ctx.workers = MagicMock()
    ctx.workers.register = MagicMock()

    manifest = await register(app, ctx)

    # Worker should have been registered
    ctx.workers.register.assert_called_once()
    call_kwargs = ctx.workers.register.call_args
    assert call_kwargs[0][0] == "auto_tess" or call_kwargs[1].get("name") == "auto_tess" or \
           ("auto_tess" in str(call_kwargs))


@pytest.mark.asyncio
async def test_plugin_register_local_mode_skips_worker():
    from fastapi import FastAPI
    from kerf_tess.plugin import register

    app = FastAPI()
    ctx = MagicMock()
    ctx.cloud_enabled = False
    ctx.local_mode = True
    ctx.workers = MagicMock()
    ctx.workers.register = MagicMock()

    await register(app, ctx)

    ctx.workers.register.assert_not_called()


# ── Worker instantiation ──────────────────────────────────────────────────────

def test_auto_tess_worker_instantiation():
    from kerf_tess.worker import AutoTessWorker

    mock_pool = MagicMock()
    mock_storage_getter = MagicMock(return_value=MagicMock())

    worker = AutoTessWorker(
        pool=mock_pool,
        storage_getter=mock_storage_getter,
        pyworker_url="http://localhost:8090",
        poll_interval=10.0,
        timeout=30,
    )

    assert worker.name == "auto_tess"
    assert worker.timeout == 30
