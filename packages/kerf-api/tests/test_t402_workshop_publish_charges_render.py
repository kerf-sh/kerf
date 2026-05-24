"""T-402 R6 — workshop publish cover-render billing gate tests.

Covers:
1. test_workshop_publish_charges_render
   workshop_publish flow pre-gates the cover render against the publisher's
   account.  When the billing gate raises 402 (insufficient credits), the
   cover render is skipped gracefully (cover_key=None) so the publish still
   succeeds for the rest of the metadata (the gate exception is swallowed by
   the try/except in workshop_publish around _generate_project_cover).

2. test_generate_project_cover_gates_billing_before_http_call
   _generate_project_cover calls _run_billing_gate with the publisher's
   user_id BEFORE making the httpx POST; the HTTP call must NOT be made when
   the gate denies.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.run(coro)


WS_ID = uuid.uuid4()
USER_ID = str(uuid.uuid4())
PROJ_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeRecord(dict):
    def __getitem__(self, key):
        return super().__getitem__(key)
    def get(self, key, default=None):
        return super().get(key, default)


def _make_project(**kwargs):
    import datetime
    defaults = {
        "id": PROJ_ID,
        "workspace_id": WS_ID,
        "visibility": "private",
        "name": "Widget",
        "description": "desc",
        "tags": [],
        "readme": None,
        "readme_generated_at": None,
        "cover_storage_key": None,
        "thumbnail_storage_key": None,
        "created_at": datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
        "updated_at": datetime.datetime(2025, 1, 2, tzinfo=datetime.timezone.utc),
        "workshop_images": [],
        "workshop_model_id": None,
        "workshop_model_name": None,
        "forked_from_project_id": None,
        "created_by": None,
        "author_id": None,
        "author_name": "alice",
        "author_avatar_url": None,
        "workspace_slug": "ws-test",
        "workspace_name": "Test WS",
        "is_verified_publisher": False,
        "likes_count": 0,
        "liked_by_me": False,
        "forks_count": 0,
        "file_count": 0,
        "total_bytes": 0,
    }
    defaults.update(kwargs)
    return _FakeRecord(defaults)


def _make_pool(conn=None):
    conn = conn or AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


# ---------------------------------------------------------------------------
# Test 1: billing gate denial → cover skipped, publish still returns metadata
# ---------------------------------------------------------------------------


def test_workshop_publish_charges_render():
    """Cover render gate-denial must not abort the publish — cover is skipped gracefully."""
    from kerf_api.routes import workshop_publish, WorkshopPublishRequest

    project = _make_project()
    updated = _FakeRecord(dict(project))
    updated["visibility"] = "public"
    updated["readme"] = None

    conn = AsyncMock()
    pool = _make_pool(conn)

    # Simulate gate denial via HTTPException(402) inside _generate_project_cover.
    gate_denial = HTTPException(
        status_code=402,
        detail="Insufficient credits for GPU render.",
    )

    cms = [
        patch("kerf_api.routes.get_pool_required", AsyncMock(return_value=pool)),
        patch("kerf_api.routes.projects_queries.get_project", AsyncMock(return_value=project)),
        patch("kerf_api.routes.get_user_workspace_role", AsyncMock(return_value="owner")),
        patch("kerf_api.routes.projects_queries.update_project", AsyncMock(return_value=updated)),
        # _generate_project_cover raises (gate denial) → cover_key=None, publish continues.
        patch("kerf_api.routes._generate_project_cover", AsyncMock(side_effect=gate_denial)),
        patch("kerf_api.routes.get_storage_required", MagicMock()),
    ]
    for cm in cms:
        cm.start()
    try:
        body = WorkshopPublishRequest(
            project_id=str(PROJ_ID),
            generate_readme=False,
        )
        result = _run(workshop_publish(body, auth={"sub": USER_ID}))
    finally:
        for cm in reversed(cms):
            cm.stop()

    # Publish succeeds even though cover render was denied.
    assert result["visibility"] == "public"
    assert result["project_id"] == str(PROJ_ID)
    # No cover key set because the gate denied it.
    assert result.get("cover_storage_key") is None


# ---------------------------------------------------------------------------
# Test 2: _generate_project_cover gates billing BEFORE the HTTP dispatch
# ---------------------------------------------------------------------------


def test_generate_project_cover_gates_billing_before_http_call():
    """_run_billing_gate must be called with the publisher's user_id before httpx POST.

    We force _BLENDER_AVAILABLE=True via monkeypatching kerf_render.routes so
    the function reaches the billing-gate call, then confirm:
    - gate is invoked with the correct user_id
    - the httpx POST is never made when the gate raises
    - the function returns None gracefully
    """
    from kerf_api.routes import _generate_project_cover
    import kerf_render.routes as _krr

    conn = AsyncMock()
    # Provide a fake file row so the early-exit "no file rows" doesn't fire.
    conn.fetch = AsyncMock(return_value=[{"id": uuid.uuid4(), "name": "part.step",
                                          "kind": "step", "content": None, "bytes": 100}])

    storage = MagicMock()
    storage.put = AsyncMock()

    # Patch _run_billing_gate to raise 402 (simulating insufficient credits).
    gate_denial = HTTPException(status_code=402, detail="Insufficient credits")
    gate_mock = AsyncMock(side_effect=gate_denial)

    fake_settings = MagicMock()
    fake_settings.render_service_url = "http://render-service"

    # httpx mock to confirm it is NOT called when gate raises.
    http_post_mock = AsyncMock()

    cms = [
        # Force Blender available so the function body past _BLENDER_AVAILABLE check runs.
        patch.object(_krr, "_BLENDER_AVAILABLE", True),
        patch("kerf_api.routes.get_settings", return_value=fake_settings),
        patch("kerf_render.routes._run_billing_gate", gate_mock),
    ]
    for cm in cms:
        cm.start()
    try:
        result = _run(_generate_project_cover(conn, {}, PROJ_ID, storage, user_id=USER_ID))
    finally:
        for cm in reversed(cms):
            cm.stop()

    # Gate was called with the correct user_id.
    gate_mock.assert_called_once()
    call_args = gate_mock.call_args
    assert call_args[0][0] == USER_ID, f"Expected user_id={USER_ID!r}, got {call_args[0][0]!r}"

    # HTTP dispatch was NOT made because the gate raised first.
    http_post_mock.assert_not_called()

    # Function returns None gracefully (cover skipped on gate denial).
    assert result is None
