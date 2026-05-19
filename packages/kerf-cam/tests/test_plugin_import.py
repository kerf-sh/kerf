"""
Regression test: cam plugin can be imported without error.

The bug: kerf_cam/tools/ is a package directory AND kerf_cam/tools.py was a
sibling module.  Python resolves `kerf_cam.tools` to the package, so
`from kerf_cam.tools import cam_run_spec` failed with ImportError because the
package's __init__.py only contained a comment.

Fix: move the symbols into kerf_cam/tools/__init__.py and remove the orphaned
tools.py.  This test guards the import contract going forward.
"""
import sys
import os

# Ensure src/ is on the path (mirrors conftest.py logic)
_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_PLUGIN_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import pytest


def test_cam_run_spec_importable():
    """cam_run_spec must be importable from kerf_cam.tools (not tools.py)."""
    from kerf_cam.tools import cam_run_spec
    assert cam_run_spec is not None
    assert cam_run_spec.name == "cam_run"


def test_cam_job_status_spec_importable():
    """cam_job_status_spec must be importable from kerf_cam.tools."""
    from kerf_cam.tools import cam_job_status_spec
    assert cam_job_status_spec is not None
    assert cam_job_status_spec.name == "cam_job_status"


def test_run_cam_run_importable():
    """run_cam_run handler must be importable from kerf_cam.tools."""
    from kerf_cam.tools import run_cam_run
    import asyncio
    assert callable(run_cam_run)


def test_run_cam_job_status_importable():
    """run_cam_job_status handler must be importable from kerf_cam.tools."""
    from kerf_cam.tools import run_cam_job_status
    assert callable(run_cam_job_status)


def test_tool_db_still_importable():
    """tool_db sub-module inside the tools package must still resolve."""
    from kerf_cam.tools.tool_db import (
        create_tool_spec,
        run_create_tool,
        update_tool_spec,
        run_update_tool,
        delete_tool_spec,
        run_delete_tool,
        list_tools_llm_spec,
        run_list_tools,
    )
    assert create_tool_spec.name == "create_tool"
    assert list_tools_llm_spec.name == "list_tools"


def test_plugin_register_does_not_raise(monkeypatch):
    """
    Simulate the plugin loader calling register().

    We stub out ctx so we don't need a live server; the test just verifies
    that the import chain in plugin.py completes without ImportError.
    """
    import types
    import asyncio

    # Stub app
    app = types.SimpleNamespace(include_router=lambda r: None)

    # Stub ctx.tools / ctx.workers / ctx.storage / ctx.pool / ctx.config
    registered = {}

    def fake_register(name, spec, handler):
        registered[name] = (spec, handler)

    ctx = types.SimpleNamespace(
        tools=types.SimpleNamespace(register=fake_register),
        workers=types.SimpleNamespace(register=lambda name, factory: None),
        pool=None,
        storage=None,
        config=types.SimpleNamespace(pyworker_url="http://localhost:8090"),
    )

    from kerf_cam import plugin

    async def _run():
        return await plugin.register(app, ctx)

    result = asyncio.run(_run())

    # All four tool-function pairs must be registered
    assert "cam_run" in registered
    assert "cam_job_status" in registered
    assert "create_tool" in registered
    assert "list_tools" in registered
