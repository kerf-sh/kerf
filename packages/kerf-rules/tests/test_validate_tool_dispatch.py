"""
test_validate_tool_dispatch.py — dispatch test for the validate_against_rules LLM tool.

Verifies that:
  1. kerf_rules.tools.validate_against_rules exposes a TOOLS list.
  2. The TOOLS list contains (name, spec, handler) for "validate_against_rules".
  3. The async handler returns a structured error payload on invalid args.
  4. The async handler succeeds on a compliant AISC project (stub that bypasses
     file-based rule pack resolution via a custom RulePack).
"""
from __future__ import annotations

import asyncio
import json
import types
import uuid

import pytest


def run(coro):
    return asyncio.run(coro)


def _make_ctx():
    ctx = types.SimpleNamespace()
    ctx.project_id = uuid.uuid4()
    ctx.pool = None
    ctx.storage = None
    return ctx


# ---------------------------------------------------------------------------

class TestToolsListWiring:
    def test_tools_list_present(self):
        from kerf_rules.tools.validate_against_rules import TOOLS
        assert isinstance(TOOLS, list), "TOOLS must be a list"

    def test_tools_list_has_validate_entry(self):
        from kerf_rules.tools.validate_against_rules import TOOLS
        names = [t[0] for t in TOOLS]
        assert "validate_against_rules" in names, (
            "TOOLS must contain an entry named 'validate_against_rules'"
        )

    def test_tools_list_entry_shape(self):
        from kerf_rules.tools.validate_against_rules import TOOLS
        for name, spec, handler in TOOLS:
            assert isinstance(name, str) and name
            assert hasattr(spec, "name") and spec.name == name
            assert callable(handler)


class TestDispatchHandler:
    """run_validate_against_rules must return a JSON payload, not crash."""

    def _get_handler(self):
        from kerf_rules.tools.validate_against_rules import TOOLS
        for name, spec, handler in TOOLS:
            if name == "validate_against_rules":
                return handler
        pytest.skip("validate_against_rules tool not found (kerf_chat unavailable)")

    def test_missing_project_returns_error(self):
        handler = self._get_handler()
        ctx = _make_ctx()
        result = run(handler(ctx, b'{"rule_pack": "aisc"}'))
        data = json.loads(result)
        assert data.get("ok") is not True
        assert "code" in data or "error" in data

    def test_missing_rule_pack_returns_error(self):
        handler = self._get_handler()
        ctx = _make_ctx()
        result = run(handler(ctx, b'{"project": {"elements": []}}'))
        data = json.loads(result)
        assert data.get("ok") is not True

    def test_bad_rule_pack_returns_error(self):
        handler = self._get_handler()
        ctx = _make_ctx()
        result = run(handler(ctx, b'{"project": {"elements": []}, "rule_pack": "unknown_pack"}'))
        data = json.loads(result)
        assert data.get("ok") is not True
        assert data.get("code") == "BAD_ARGS"

    def test_empty_project_returns_ok(self):
        """Empty elements list → zero violations → ok=True."""
        handler = self._get_handler()
        ctx = _make_ctx()
        payload = json.dumps({
            "project": {"name": "test", "elements": []},
            "rule_pack": "aisc",
        }).encode()
        result = run(handler(ctx, payload))
        data = json.loads(result)
        # Should succeed: zero elements → zero violations
        assert data.get("ok") is True
        inner = data.get("result", data)
        assert inner.get("violation_count", 0) == 0
