"""Regression: GET .../messages must return part_refs/tool_calls as
arrays, not raw jsonb strings.

Bug: list_messages returned dict(row) verbatim. chat_messages.part_refs
and tool_calls are jsonb; asyncpg yields jsonb as a raw string (no
global JSON codec — handlers json.loads it per-call), so the client
received part_refs:"[]" and did "[]".map(...) →
"Uncaught TypeError: e.part_refs.map is not a function" (chat crash).

Fix decodes both columns. These pin: str jsonb → list, None → [],
already-list passes through, malformed → [].
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from kerf_api.routes import list_messages


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _pool(rows):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows)
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


ROWS = [
    {"id": "m1", "role": "user", "content": "hi",
     "part_refs": "[]", "tool_calls": "[]"},
    {"id": "m2", "role": "user", "content": "x",
     "part_refs": '[{"part_id":"p1","label":"Base"}]',
     "tool_calls": '[{"id":"t1"}]'},
    {"id": "m3", "role": "assistant", "content": "y",
     "part_refs": None, "tool_calls": None},
    {"id": "m4", "role": "user", "content": "z",
     "part_refs": [{"part_id": "p2"}], "tool_calls": []},
    {"id": "m5", "role": "user", "content": "bad",
     "part_refs": "{not json", "tool_calls": "also bad"},
]


def _call():
    cms = [
        patch("kerf_api.routes.get_pool_required",
              AsyncMock(return_value=_pool(ROWS))),
        patch("kerf_api.routes.project_workspace_id",
              AsyncMock(return_value="ws-1")),
        patch("kerf_api.routes.get_user_workspace_role",
              AsyncMock(return_value="owner")),
    ]
    for cm in cms:
        cm.start()
    try:
        return _run(list_messages("p1", "t1", None, payload={"sub": "u1"}))
    finally:
        for cm in reversed(cms):
            cm.stop()


def test_part_refs_and_tool_calls_always_arrays():
    out = _call()
    for m in out:
        assert isinstance(m["part_refs"], list), f"{m['id']} part_refs not list"
        assert isinstance(m["tool_calls"], list), f"{m['id']} tool_calls not list"


def test_values_decoded_correctly():
    out = {m["id"]: m for m in _call()}
    assert out["m1"]["part_refs"] == []
    assert out["m2"]["part_refs"] == [{"part_id": "p1", "label": "Base"}]
    assert out["m2"]["tool_calls"] == [{"id": "t1"}]
    assert out["m3"]["part_refs"] == [] and out["m3"]["tool_calls"] == []
    assert out["m4"]["part_refs"] == [{"part_id": "p2"}]  # already a list
    # malformed jsonb degrades to [] instead of crashing the client
    assert out["m5"]["part_refs"] == [] and out["m5"]["tool_calls"] == []
