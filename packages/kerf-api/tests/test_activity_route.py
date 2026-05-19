"""Regression: GET /projects/{pid}/activity returns {events, next_cursor}.

The route was missing entirely (every call 404'd). This test verifies:
  - 200 response with the expected shape for an empty project
  - events is always a list
  - next_cursor is null when the result set is empty
  - 404 when project does not exist
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from kerf_api.routes import get_project_activity


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _pool(rows=None):
    """Build a minimal asyncpg pool mock that returns `rows` from fetch()."""
    if rows is None:
        rows = []
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _call_activity(pid="proj-1", rows=None, ws_id="ws-1", role="owner",
                   limit=50, before=None):
    """Call get_project_activity with patched DB dependencies."""
    cms = [
        patch("kerf_api.routes.get_pool_required",
              AsyncMock(return_value=_pool(rows))),
        patch("kerf_api.routes.project_workspace_id",
              AsyncMock(return_value=ws_id)),
        patch("kerf_api.routes.get_user_workspace_role",
              AsyncMock(return_value=role)),
    ]
    for cm in cms:
        cm.start()
    try:
        return _run(get_project_activity(
            pid=pid, limit=limit, before=before, payload={"sub": "u-1"}
        ))
    finally:
        for cm in reversed(cms):
            cm.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Shape tests — no database required
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_project_returns_200_shape():
    """Empty DB returns {events: [], next_cursor: null} — NOT 404."""
    result = _call_activity()
    assert isinstance(result, dict), "response must be a dict"
    assert "events" in result, "response must have 'events' key"
    assert "next_cursor" in result, "response must have 'next_cursor' key"


def test_empty_project_events_is_list():
    result = _call_activity()
    assert isinstance(result["events"], list)


def test_empty_project_next_cursor_is_null():
    result = _call_activity()
    assert result["next_cursor"] is None


def test_404_when_project_not_found():
    """project_workspace_id returning None → 404."""
    import pytest
    from fastapi import HTTPException
    cms = [
        patch("kerf_api.routes.get_pool_required",
              AsyncMock(return_value=_pool())),
        patch("kerf_api.routes.project_workspace_id",
              AsyncMock(return_value=None)),
        patch("kerf_api.routes.get_user_workspace_role",
              AsyncMock(return_value=None)),
    ]
    for cm in cms:
        cm.start()
    try:
        with pytest.raises(HTTPException) as exc_info:
            _run(get_project_activity(pid="missing", limit=50, before=None, payload={"sub": "u-1"}))
    finally:
        for cm in reversed(cms):
            cm.stop()
    assert exc_info.value.status_code == 404


def test_404_when_user_not_member():
    """get_user_workspace_role returning None → 404 (project hidden from non-member)."""
    import pytest
    from fastapi import HTTPException
    cms = [
        patch("kerf_api.routes.get_pool_required",
              AsyncMock(return_value=_pool())),
        patch("kerf_api.routes.project_workspace_id",
              AsyncMock(return_value="ws-1")),
        patch("kerf_api.routes.get_user_workspace_role",
              AsyncMock(return_value=None)),
    ]
    for cm in cms:
        cm.start()
    try:
        with pytest.raises(HTTPException) as exc_info:
            _run(get_project_activity(pid="proj-1", limit=50, before=None, payload={"sub": "outsider"}))
    finally:
        for cm in reversed(cms):
            cm.stop()
    assert exc_info.value.status_code == 404


def test_event_shape_with_rows():
    """When the DB returns rows, each event has the required keys."""
    import datetime as dt

    ts = dt.datetime(2024, 3, 15, 10, 0, 0,
                     tzinfo=dt.timezone.utc)

    # Simulate a single 'edit' event row (matching the SELECT column list).
    row = {
        "kind": "edit",
        "source": "llm",
        "created_at": ts,
        "user_id": "u-abc",
        "user_name": "Alice",
        "user_avatar_url": "https://example.com/a.png",
        "file_id": "f-1",
        "file_name": "bracket.step",
        "thread_id": None,
        "thread_title": None,
        "content_preview": None,
    }

    result = _call_activity(rows=[row])
    assert len(result["events"]) == 1
    ev = result["events"][0]
    assert ev["kind"] == "edit"
    assert ev["source"] == "llm"
    assert "created_at" in ev
    assert ev["user"]["name"] == "Alice"
    assert ev["user"]["avatar_url"] == "https://example.com/a.png"
    assert ev["file"]["id"] == "f-1"
    assert ev["file"]["name"] == "bracket.step"
    assert "thread" not in ev


def test_chat_event_has_thread_and_preview():
    """Chat events carry thread + content_preview, no file."""
    import datetime as dt

    ts = dt.datetime(2024, 3, 15, 11, 0, 0, tzinfo=dt.timezone.utc)
    row = {
        "kind": "chat",
        "source": None,
        "created_at": ts,
        "user_id": None,
        "user_name": None,
        "user_avatar_url": None,
        "file_id": None,
        "file_name": None,
        "thread_id": "t-1",
        "thread_title": "Fillet radius",
        "content_preview": "How do I set a 2mm fillet on this part?",
    }

    result = _call_activity(rows=[row])
    ev = result["events"][0]
    assert ev["kind"] == "chat"
    assert ev["thread"]["id"] == "t-1"
    assert ev["thread"]["title"] == "Fillet radius"
    assert ev["content_preview"] == "How do I set a 2mm fillet on this part?"
    assert "file" not in ev
    assert "source" not in ev


def test_next_cursor_set_when_full_page():
    """When exactly limit+1 rows are returned, next_cursor == oldest event ts."""
    import datetime as dt

    limit = 3
    ts_base = dt.datetime(2024, 3, 15, 10, 0, 0, tzinfo=dt.timezone.utc)

    # Build limit+1 rows (DB returns limit+1 to signal "has more").
    rows = []
    for i in range(limit + 1):
        ts = dt.datetime(2024, 3, 15, 10 - i, 0, 0, tzinfo=dt.timezone.utc)
        rows.append({
            "kind": "project_created",
            "source": None,
            "created_at": ts,
            "user_id": None,
            "user_name": None,
            "user_avatar_url": None,
            "file_id": None,
            "file_name": None,
            "thread_id": None,
            "thread_title": None,
            "content_preview": None,
        })

    result = _call_activity(rows=rows, limit=limit)
    # Page should only contain `limit` events (the extra one was the lookahead).
    assert len(result["events"]) == limit
    # next_cursor must be set.
    assert result["next_cursor"] is not None
    # It should equal the ISO of the oldest (last) event on the page.
    oldest_ts = rows[limit - 1]["created_at"]
    assert result["next_cursor"] == oldest_ts.isoformat()


def test_next_cursor_null_when_fewer_rows_than_limit():
    """When fewer rows than limit are returned there is no next page."""
    import datetime as dt

    ts = dt.datetime(2024, 3, 15, 10, 0, 0, tzinfo=dt.timezone.utc)
    rows = [
        {
            "kind": "project_created", "source": None, "created_at": ts,
            "user_id": None, "user_name": None, "user_avatar_url": None,
            "file_id": None, "file_name": None,
            "thread_id": None, "thread_title": None, "content_preview": None,
        }
    ]

    result = _call_activity(rows=rows, limit=50)
    assert len(result["events"]) == 1
    assert result["next_cursor"] is None
