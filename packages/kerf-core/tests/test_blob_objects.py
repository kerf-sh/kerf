"""Integration tests for kerf_core.db.queries.blob_objects.

Requires a live Postgres database.  Set DATABASE_URL before running, e.g.:

    DATABASE_URL="postgres://pc@localhost:5432/kerf?sslmode=disable" \
        python -m pytest packages/kerf-core/tests/test_blob_objects.py -q

Each test creates its own user/workspace/project rows and tears them down via
the autouse fixture so it does not interfere with real data.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import pytest

from kerf_core.db.queries.blob_objects import (
    add_ref,
    drop_ref,
    first_workspace,
    record_blob,
    refcount,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_TAG = "test-blob-"

# ---------------------------------------------------------------------------
# Single shared event loop for the whole module — asyncpg connections are
# bound to the loop they were created on; creating a new loop per call
# causes "Future attached to different loop" errors.
# ---------------------------------------------------------------------------
_LOOP: asyncio.AbstractEventLoop | None = None


def _loop() -> asyncio.AbstractEventLoop:
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP


def run(coro):
    return _loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _make_user(conn: asyncpg.Connection) -> uuid.UUID:
    uid = uuid.uuid4()
    email = f"{_TAG}{uid.hex}@test.invalid"
    await conn.execute(
        "INSERT INTO users (id, email, name) VALUES ($1, $2, $3)",
        uid, email, f"Test Blob User {uid}",
    )
    return uid


async def _make_workspace(conn: asyncpg.Connection, owner_id: uuid.UUID) -> uuid.UUID:
    ws_id = uuid.uuid4()
    slug = f"{_TAG}{ws_id.hex}"
    await conn.execute(
        "INSERT INTO workspaces (id, slug, name, created_by) VALUES ($1, $2, $3, $4)",
        ws_id, slug, f"Test WS {ws_id}", owner_id,
    )
    return ws_id


async def _make_project(conn: asyncpg.Connection, ws_id: uuid.UUID) -> uuid.UUID:
    proj_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO projects (id, workspace_id, name) VALUES ($1, $2, $3)",
        proj_id, ws_id, f"test-blob-proj-{proj_id}",
    )
    return proj_id


async def _make_fixtures(conn: asyncpg.Connection):
    """Return (oid, ws_id, proj_id) for a fresh test scenario."""
    oid = f"{_TAG}{uuid.uuid4().hex}"
    owner_id = await _make_user(conn)
    ws_id = await _make_workspace(conn, owner_id)
    proj_id = await _make_project(conn, ws_id)
    return oid, ws_id, proj_id


async def _cleanup(conn: asyncpg.Connection) -> None:
    await conn.execute("DELETE FROM blob_refs   WHERE oid LIKE $1", f"{_TAG}%")
    await conn.execute("DELETE FROM blob_objects WHERE oid LIKE $1", f"{_TAG}%")
    await conn.execute("DELETE FROM projects  WHERE name LIKE $1", "test-blob-proj-%")
    await conn.execute("DELETE FROM workspaces WHERE slug LIKE $1", f"{_TAG}%")
    await conn.execute("DELETE FROM users      WHERE email LIKE $1", f"{_TAG}%@test.invalid")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def conn():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")
    connection = run(asyncpg.connect(DATABASE_URL))
    yield connection
    run(connection.close())


@pytest.fixture(autouse=True)
def cleanup(conn):
    yield
    run(_cleanup(conn))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_record_blob_inserts_row(conn):
    oid, ws_id, _ = run(_make_fixtures(conn))

    run(record_blob(conn, oid, 1024, ws_id))

    row = run(conn.fetchrow(
        "SELECT size_bytes, first_workspace_id FROM blob_objects WHERE oid = $1", oid
    ))
    assert row is not None
    assert row["size_bytes"] == 1024
    assert row["first_workspace_id"] == ws_id


def test_record_blob_idempotent(conn):
    """Calling record_blob twice for the same oid must not raise or double-insert."""
    oid, ws_id, _ = run(_make_fixtures(conn))

    run(record_blob(conn, oid, 512, ws_id))
    run(record_blob(conn, oid, 512, ws_id))  # no-op

    count = run(conn.fetchval(
        "SELECT COUNT(*) FROM blob_objects WHERE oid = $1", oid
    ))
    assert int(count) == 1


def test_add_ref_and_refcount(conn):
    oid, ws_id, proj_id = run(_make_fixtures(conn))

    run(record_blob(conn, oid, 256, ws_id))
    run(add_ref(conn, oid, proj_id, "models/part.step"))

    assert run(refcount(conn, oid)) == 1


def test_add_ref_multiple_paths(conn):
    oid, ws_id, proj_id = run(_make_fixtures(conn))

    run(record_blob(conn, oid, 256, ws_id))
    run(add_ref(conn, oid, proj_id, "models/a.step"))
    run(add_ref(conn, oid, proj_id, "models/b.step"))

    assert run(refcount(conn, oid)) == 2


def test_add_ref_idempotent(conn):
    """Adding the same (oid, project_id, path) twice must not raise or double-count."""
    oid, ws_id, proj_id = run(_make_fixtures(conn))

    run(record_blob(conn, oid, 128, ws_id))
    run(add_ref(conn, oid, proj_id, "models/part.step"))
    run(add_ref(conn, oid, proj_id, "models/part.step"))

    assert run(refcount(conn, oid)) == 1


def test_drop_ref_decrements_count(conn):
    oid, ws_id, proj_id = run(_make_fixtures(conn))

    run(record_blob(conn, oid, 256, ws_id))
    run(add_ref(conn, oid, proj_id, "models/part.step"))
    run(add_ref(conn, oid, proj_id, "models/other.step"))

    run(drop_ref(conn, oid, proj_id, "models/part.step"))
    assert run(refcount(conn, oid)) == 1

    run(drop_ref(conn, oid, proj_id, "models/other.step"))
    assert run(refcount(conn, oid)) == 0


def test_refcount_no_refs(conn):
    oid, ws_id, _ = run(_make_fixtures(conn))

    run(record_blob(conn, oid, 64, ws_id))
    assert run(refcount(conn, oid)) == 0


def test_first_workspace_returns_correct_id(conn):
    oid, ws_id, _ = run(_make_fixtures(conn))

    run(record_blob(conn, oid, 64, ws_id))
    assert run(first_workspace(conn, oid)) == ws_id


def test_first_workspace_none_for_unknown_oid(conn):
    assert run(first_workspace(conn, f"{_TAG}nonexistent-oid-xyz")) is None


def test_workspace_delete_sets_null_on_blob_objects(conn):
    """Deleting a workspace NULLs first_workspace_id (ON DELETE SET NULL)."""
    oid, ws_id, _ = run(_make_fixtures(conn))

    run(record_blob(conn, oid, 32, ws_id))

    # Delete workspace; ON DELETE SET NULL must fire on blob_objects.
    run(conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id))

    row = run(conn.fetchrow(
        "SELECT first_workspace_id FROM blob_objects WHERE oid = $1", oid
    ))
    assert row is not None
    assert row["first_workspace_id"] is None


def test_project_delete_cascades_blob_refs(conn):
    """Deleting a project must cascade-delete all its blob_refs rows."""
    oid, ws_id, proj_id = run(_make_fixtures(conn))

    run(record_blob(conn, oid, 128, ws_id))
    run(add_ref(conn, oid, proj_id, "models/part.step"))
    run(add_ref(conn, oid, proj_id, "models/other.step"))

    assert run(refcount(conn, oid)) == 2

    # Delete project; all refs must cascade.
    run(conn.execute("DELETE FROM projects WHERE id = $1", proj_id))

    assert run(refcount(conn, oid)) == 0
