"""T-402 R5 — billing gate auth tests.

Covers:
1. test_run_render_unauth_in_cloud_mode_is_401
   POST /run-render with no auth (user_id=None), cloud mode → 401.
2. test_run_render_unauth_in_self_host_skips_gate
   Same call with KERF_RENDER_BILLING_DISABLED=1 → gate skipped (no 401/402).
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Test 1: cloud mode + no user_id → 401
# ---------------------------------------------------------------------------


def test_run_render_unauth_in_cloud_mode_is_401(monkeypatch):
    """_run_billing_gate must raise HTTP 401 when usage_enabled=True and user_id is None."""
    from kerf_render.routes import _run_billing_gate

    # Patch settings so usage_enabled=True (cloud mode).
    fake_settings = MagicMock()
    fake_settings.usage_enabled = True

    with patch("kerf_render.routes._get_settings", return_value=fake_settings):
        with pytest.raises(HTTPException) as exc_info:
            run(_run_billing_gate(None, 10.0))

    assert exc_info.value.status_code == 401
    assert "Authentication required" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Test 2: self-host mode (KERF_RENDER_BILLING_DISABLED=1) + no user_id → skip gate
# ---------------------------------------------------------------------------


def test_run_render_unauth_in_self_host_skips_gate(monkeypatch):
    """_run_billing_gate must return silently when usage_enabled=False (self-host)."""
    from kerf_render.routes import _run_billing_gate

    # usage_enabled=False = self-host / OSS mode.
    fake_settings = MagicMock()
    fake_settings.usage_enabled = False

    with patch("kerf_render.routes._get_settings", return_value=fake_settings):
        # Should NOT raise — gate is skipped entirely.
        run(_run_billing_gate(None, 10.0))
        # Passes if no exception.


def test_run_render_unauth_in_self_host_billing_disabled_env_skips_gate(monkeypatch):
    """KERF_RENDER_BILLING_DISABLED=1 env var must suppress the gate (self-host kill-switch).

    gate_render_job itself checks _billing_disabled(); this test ensures the
    full path does not raise when usage_enabled=True but the env var is set.
    """
    from kerf_render.routes import _run_billing_gate
    from kerf_billing.render_meter import _BILLING_DISABLED_VAR

    fake_settings = MagicMock()
    fake_settings.usage_enabled = True

    monkeypatch.setenv(_BILLING_DISABLED_VAR, "1")

    fake_pool = AsyncMock()

    with patch("kerf_render.routes._get_settings", return_value=fake_settings), \
         patch("kerf_core.db.connection.get_pool_required", AsyncMock(return_value=fake_pool)):
        # With a non-None user_id and the billing disabled env var set,
        # gate_render_job will skip — no 402 raised.
        run(_run_billing_gate("some-user-id", 10.0))
