"""Robust create-project workspace resolution.

Root cause of the recurring {"detail":"workspace_id or workspace_slug
required"}: create_project hard-required the client to send a workspace,
so a transient client-side workspace-load failure made project creation
impossible. Fix: when no workspace is supplied, the server resolves the
caller's default workspace (self-healing if absent). The server owns
membership, so this is correct — not a workaround.

These tests pin: (1) no workspace + existing default → uses it, no 400;
(2) no workspace + no default → creates a personal one; (3) explicit
workspace still wins and the default lookup is skipped.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from kerf_api.routes import CreateProjectRequest, create_project


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _Tx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *a):
        return False


def _conn():
    c = AsyncMock()
    c.fetchrow = AsyncMock(return_value={"name": "Imran", "email": "imran@x.com"})
    c.transaction = MagicMock(return_value=_Tx())
    return c


def _pool(conn):
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _patches(*, default_ws, role="owner"):
    """Common patch set; returns (ctx_managers, captured)."""
    conn = _conn()
    projects_q = MagicMock()
    projects_q.create_project = AsyncMock(return_value={"id": "p1", "name": "X"})
    files_q = MagicMock()
    files_q.create_file = AsyncMock()
    cpw = AsyncMock(return_value={"id": "ws-created"})
    gdw = AsyncMock(return_value=default_ws)
    gwbs = AsyncMock(return_value=None)
    fake_settings = MagicMock()
    fake_settings.cloud_enabled = False

    cms = [
        patch("kerf_api.routes.get_pool_required", AsyncMock(return_value=_pool(conn))),
        patch("kerf_api.routes.get_default_workspace", gdw),
        patch("kerf_api.routes.create_personal_workspace", cpw),
        patch("kerf_api.routes.get_user_workspace_role", AsyncMock(return_value=role)),
        patch("kerf_api.routes.get_workspace_by_slug", gwbs),
        patch("kerf_api.routes.projects_queries", projects_q),
        patch("kerf_api.routes.files_queries", files_q),
        patch("kerf_api.routes.settings", fake_settings),
    ]
    return cms, {"projects_q": projects_q, "cpw": cpw, "gdw": gdw}


def _call(req):
    return _run(create_project(req, payload={"sub": "user-1"}))


def test_no_workspace_uses_existing_default_no_400():
    cms, cap = _patches(default_ws=({"id": "ws-default"}, True))
    for cm in cms:
        cm.start()
    try:
        result = _call(CreateProjectRequest(name="My Project"))
    finally:
        for cm in reversed(cms):
            cm.stop()
    assert result["id"] == "p1"
    assert result["my_role"] == "owner"
    cap["cpw"].assert_not_awaited()  # default existed; no creation
    # project created in the resolved default workspace
    args = cap["projects_q"].create_project.await_args.args
    assert "ws-default" in args


def test_no_workspace_no_default_creates_personal():
    cms, cap = _patches(default_ws=(None, False))
    for cm in cms:
        cm.start()
    try:
        result = _call(CreateProjectRequest(name="My Project"))
    finally:
        for cm in reversed(cms):
            cm.stop()
    assert result["id"] == "p1"
    cap["cpw"].assert_awaited()  # self-healed a workspace
    args = cap["projects_q"].create_project.await_args.args
    assert "ws-created" in args


def test_explicit_workspace_wins_and_skips_default_lookup():
    cms, cap = _patches(default_ws=({"id": "ws-default"}, True))
    for cm in cms:
        cm.start()
    try:
        result = _call(
            CreateProjectRequest(name="My Project", workspace_id="ws-explicit")
        )
    finally:
        for cm in reversed(cms):
            cm.stop()
    assert result["id"] == "p1"
    cap["gdw"].assert_not_awaited()  # explicit id → no default resolution
    args = cap["projects_q"].create_project.await_args.args
    assert "ws-explicit" in args
