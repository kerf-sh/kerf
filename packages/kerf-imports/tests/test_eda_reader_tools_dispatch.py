"""
test_eda_reader_tools_dispatch.py — hermetic dispatch tests for the EDA reader LLM tools.

Covers the TOOLS list wiring for qif_reader, ibis_reader, eagle_reader, pads_reader,
geda_reader, allegro_reader, jt_reader, and parasolid_reader.  Verifies that each
module exposes a non-empty TOOLS list and that the handler returns a well-formed
ok/error payload (no crash on minimal args).

No real file I/O or network calls; ctx is a minimal stub.
"""
from __future__ import annotations

import asyncio
import json
import types
import uuid

import pytest


# ---------------------------------------------------------------------------
# Minimal ctx stub
# ---------------------------------------------------------------------------

class _FakePool:
    async def fetchrow(self, *a, **kw):
        return None
    async def execute(self, *a, **kw):
        pass
    async def fetchval(self, *a, **kw):
        return None


def _make_ctx():
    ctx = types.SimpleNamespace()
    ctx.project_id = uuid.uuid4()
    ctx.pool = _FakePool()
    ctx.storage = None
    ctx.http_client = None
    ctx.logger = types.SimpleNamespace(info=lambda *a, **kw: None, warning=lambda *a, **kw: None)
    return ctx


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# TOOLS list wiring tests
# ---------------------------------------------------------------------------

class TestToolsListWiring:
    """Each EDA / CAD reader module must expose a non-empty TOOLS list."""

    def _check_module(self, module_path):
        import importlib
        mod = importlib.import_module(module_path)
        tools = getattr(mod, "TOOLS", None)
        assert tools is not None, f"{module_path} has no TOOLS attribute"
        assert len(tools) >= 1, f"{module_path}.TOOLS is empty"
        for entry in tools:
            assert len(entry) == 3, f"{module_path}.TOOLS entry must be (name, spec, handler)"
            name, spec, handler = entry
            assert isinstance(name, str) and name, f"tool name must be non-empty string"
            assert hasattr(spec, "name"), f"spec must have .name attribute"
            assert callable(handler), f"handler must be callable"
        return tools

    def test_qif_reader_tools_wired(self):
        tools = self._check_module("kerf_imports.qif_reader")
        names = [t[0] for t in tools]
        assert "import_qif" in names

    def test_ibis_reader_tools_wired(self):
        tools = self._check_module("kerf_imports.ibis_reader")
        names = [t[0] for t in tools]
        assert "import_ibis" in names

    def test_eagle_reader_tools_wired(self):
        tools = self._check_module("kerf_imports.eagle_reader")
        names = [t[0] for t in tools]
        assert "import_eagle" in names

    def test_pads_reader_tools_wired(self):
        tools = self._check_module("kerf_imports.pads_reader")
        names = [t[0] for t in tools]
        assert "import_pads" in names

    def test_geda_reader_tools_wired(self):
        tools = self._check_module("kerf_imports.geda_reader")
        names = [t[0] for t in tools]
        assert "import_geda" in names

    def test_allegro_reader_tools_wired(self):
        tools = self._check_module("kerf_imports.allegro_reader")
        names = [t[0] for t in tools]
        assert "import_allegro" in names

    def test_jt_reader_tools_wired(self):
        tools = self._check_module("kerf_imports.jt_reader")
        names = [t[0] for t in tools]
        assert "import_jt" in names

    def test_parasolid_reader_tools_wired(self):
        tools = self._check_module("kerf_imports.parasolid_reader")
        names = [t[0] for t in tools]
        assert "import_xt" in names


# ---------------------------------------------------------------------------
# Dispatch smoke tests — handlers return error payloads on missing args, not crashes
# ---------------------------------------------------------------------------

class TestDispatchHandlers:
    """Handlers must return a JSON error payload on invalid / missing args."""

    def _get_handler(self, module_path, tool_name):
        import importlib
        mod = importlib.import_module(module_path)
        tools = getattr(mod, "TOOLS", [])
        for name, spec, handler in tools:
            if name == tool_name:
                return handler
        pytest.fail(f"tool {tool_name!r} not found in {module_path}.TOOLS")

    def _call_bad_args(self, module_path, tool_name):
        handler = self._get_handler(module_path, tool_name)
        ctx = _make_ctx()
        result = run(handler(ctx, b"{}"))
        data = json.loads(result)
        # Must return a structured payload — either ok or error
        assert "ok" in data or "error" in data, f"unexpected payload shape: {data}"
        return data

    def test_import_qif_bad_args(self):
        data = self._call_bad_args("kerf_imports.qif_reader", "import_qif")
        # no file_id → should return error
        assert data.get("ok") is not True or data.get("code") is not None

    def test_import_ibis_bad_args(self):
        data = self._call_bad_args("kerf_imports.ibis_reader", "import_ibis")
        assert data.get("ok") is not True or data.get("code") is not None

    def test_import_eagle_bad_args(self):
        data = self._call_bad_args("kerf_imports.eagle_reader", "import_eagle")
        assert data.get("ok") is not True or data.get("code") is not None

    def test_import_pads_bad_args(self):
        data = self._call_bad_args("kerf_imports.pads_reader", "import_pads")
        assert data.get("ok") is not True or data.get("code") is not None

    def test_import_geda_bad_args(self):
        data = self._call_bad_args("kerf_imports.geda_reader", "import_geda")
        assert data.get("ok") is not True or data.get("code") is not None

    def test_import_allegro_bad_args(self):
        data = self._call_bad_args("kerf_imports.allegro_reader", "import_allegro")
        assert data.get("ok") is not True or data.get("code") is not None

    def test_import_jt_bad_args(self):
        data = self._call_bad_args("kerf_imports.jt_reader", "import_jt")
        # no storage → error
        assert data.get("ok") is not True or "code" in data

    def test_import_xt_bad_args(self):
        data = self._call_bad_args("kerf_imports.parasolid_reader", "import_xt")
        assert data.get("ok") is not True or "code" in data
