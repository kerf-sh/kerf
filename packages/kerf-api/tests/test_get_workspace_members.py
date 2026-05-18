"""Regression: GET /workspaces/{slug} 500'd on the settings page.

get_workspace did `[user_to_response(m) for m in members]`, but member
rows are workspace_members⋈users: they have `user_id` (not `id`) and no
account_role/is_system, so user_to_response raised KeyError → 500. Fix
serializes members with workspace_member_to_response in the shape
WorkspaceMembers.jsx consumes: m.user_id, m.role, m.user.{...}.
"""
from __future__ import annotations

import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

from kerf_api.routes import get_workspace, workspace_member_to_response


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_member_serializer_shape():
    row = {
        "workspace_id": "ws", "user_id": "u-1", "role": "owner",
        "created_at": dt.datetime(2024, 1, 1),
        "email": "a@b.com", "name": "Ann", "avatar_url": None,
    }
    out = workspace_member_to_response(row)
    assert out == {
        "user_id": "u-1",
        "role": "owner",
        "user": {"id": "u-1", "name": "Ann", "email": "a@b.com", "avatar_url": ""},
    }


def test_get_workspace_does_not_500_and_returns_member_shape():
    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    ws_row = {
        "id": "ws-1", "slug": "personal-x", "name": "Personal",
        "avatar_storage_key": None, "created_at": dt.datetime(2024, 1, 1),
    }
    members = [
        {"workspace_id": "ws-1", "user_id": "u-1", "role": "owner",
         "created_at": dt.datetime(2024, 1, 1), "email": "a@b.com",
         "name": "Ann", "avatar_url": None},
        {"workspace_id": "ws-1", "user_id": "u-2", "role": "member",
         "created_at": dt.datetime(2024, 1, 2), "email": "b@c.com",
         "name": "Bob", "avatar_url": "http://x/y.png"},
    ]
    wq = MagicMock()
    wq.get_workspace_by_slug = AsyncMock(return_value=ws_row)
    wq.list_workspace_members = AsyncMock(return_value=members)

    cms = [
        patch("kerf_api.routes.get_pool_required", AsyncMock(return_value=pool)),
        patch("kerf_api.routes.workspaces_queries", wq),
        patch("kerf_api.routes.get_user_workspace_role", AsyncMock(return_value="owner")),
    ]
    for cm in cms:
        cm.start()
    try:
        result = _run(get_workspace("personal-x", None, payload={"sub": "u-1"}))
    finally:
        for cm in reversed(cms):
            cm.stop()

    assert result["slug"] == "personal-x"
    assert result["my_role"] == "owner"
    assert result["member_count"] == 2
    assert len(result["members"]) == 2
    m0 = result["members"][0]
    assert m0["user_id"] == "u-1"
    assert m0["role"] == "owner"
    assert m0["user"]["name"] == "Ann"
    assert m0["user"]["email"] == "a@b.com"
    assert result["members"][1]["user"]["avatar_url"] == "http://x/y.png"
