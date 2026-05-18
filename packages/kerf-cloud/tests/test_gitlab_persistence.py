"""T-152 — GitLab connection persistence integration tests.

Proves, against a live Postgres, that:

  * GitLabProvider.connect() writes gitlab_host / gitlab_namespace /
    gitlab_project to cloud_git_repos.
  * The row survives a reload (re-query returns the stored values).
  * GitLabProvider.disconnect() NULLs out those columns.
  * GitLabProvider.status() returns connected=True when a mirror row exists
    and connected=False after disconnect.
  * A second connect() overwrites the previous mirror coordinates.

DB rule: shared Postgres postgres://pc@localhost:5432/kerf?sslmode=disable.
NO DROP/CREATE/TRUNCATE. All rows use unique test-t152- prefix. Cleanup runs
in a module-scoped fixture.

Run with:

    DATABASE_URL="postgres://pc@localhost:5432/kerf?sslmode=disable" \\
        python3 -m pytest packages/kerf-cloud/tests/test_gitlab_persistence.py -q
"""

from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_TAG = "test-t152-"

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
# Fixtures
# ---------------------------------------------------------------------------

async def _make_user(conn: asyncpg.Connection) -> uuid.UUID:
    uid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO users (id, email, name) VALUES ($1, $2, $3)",
        uid, f"{_TAG}{uid.hex}@test.invalid", f"T152 User {uid}",
    )
    return uid


async def _make_workspace(conn: asyncpg.Connection, owner: uuid.UUID) -> uuid.UUID:
    ws = uuid.uuid4()
    await conn.execute(
        "INSERT INTO workspaces (id, slug, name, created_by) VALUES ($1, $2, $3, $4)",
        ws, f"{_TAG}{ws.hex}", f"T152 WS {ws}", owner,
    )
    return ws


async def _make_project(conn: asyncpg.Connection, ws: uuid.UUID) -> uuid.UUID:
    pid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO projects (id, workspace_id, name) VALUES ($1, $2, $3)",
        pid, ws, f"test-t152-proj-{pid}",
    )
    await conn.execute(
        "INSERT INTO cloud_git_repos (project_id, default_branch) VALUES ($1, 'main')",
        pid,
    )
    return pid


async def _cleanup(conn: asyncpg.Connection) -> None:
    await conn.execute("DELETE FROM projects  WHERE name LIKE $1", "test-t152-proj-%")
    await conn.execute("DELETE FROM workspaces WHERE slug LIKE $1", f"{_TAG}%")
    await conn.execute("DELETE FROM users      WHERE email LIKE $1", f"{_TAG}%@test.invalid")


def _make_pool(conn):
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _gitlab_settings():
    s = MagicMock()
    s.cloud_gitlab_app_id = "gitlab-app-id-test"
    s.cloud_gitlab_app_secret = "gitlab-app-secret-test"
    s.cloud_gitlab_host = ""
    return s


@pytest.fixture(scope="module")
def conn():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")
    c = run(asyncpg.connect(DATABASE_URL))
    yield c
    run(_cleanup(c))
    run(c.close())


@pytest.fixture()
def fixtures(conn):
    uid = run(_make_user(conn))
    ws = run(_make_workspace(conn, uid))
    pid = run(_make_project(conn, ws))
    return conn, str(uid), str(pid)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_connect_persists_mirror_coordinates(fixtures):
    """connect() writes gitlab_host / gitlab_namespace / gitlab_project to DB."""
    conn, uid, pid = fixtures
    pool = _make_pool(conn)

    from kerf_cloud.git_providers.gitlab import GitLabProvider

    p = GitLabProvider(_gitlab_settings(), pool=pool)
    result = run(p.connect(
        pid,
        gitlab_namespace="acme",
        gitlab_project="widget",
        gitlab_host="https://gitlab.com",
    ))

    assert result["provider"] == "gitlab"
    assert result["gitlab_namespace"] == "acme"
    assert result["gitlab_project"] == "widget"

    # Verify directly in the DB.
    row = run(conn.fetchrow(
        "SELECT gitlab_host, gitlab_namespace, gitlab_project "
        "FROM cloud_git_repos WHERE project_id = $1",
        uuid.UUID(pid),
    ))
    assert row is not None
    assert row["gitlab_namespace"] == "acme"
    assert row["gitlab_project"] == "widget"
    assert row["gitlab_host"] == "https://gitlab.com"


def test_connect_survives_reload(fixtures):
    """After connect(), a fresh status() query reads the persisted values."""
    conn, uid, pid = fixtures
    pool = _make_pool(conn)

    from kerf_cloud.git_providers.gitlab import GitLabProvider

    p = GitLabProvider(_gitlab_settings(), pool=pool)
    run(p.connect(pid, gitlab_namespace="corp", gitlab_project="design"))

    # status() queries the DB — simulate "reload" by calling it on a fresh provider.
    p2 = GitLabProvider(_gitlab_settings(), pool=pool)
    status = run(p2.status(pid))

    assert status["connected"] is True
    assert status["gitlab_namespace"] == "corp"
    assert status["gitlab_project"] == "design"


def test_disconnect_clears_mirror_coordinates(fixtures):
    """disconnect() NULLs gitlab_namespace / gitlab_project / gitlab_host."""
    conn, uid, pid = fixtures
    pool = _make_pool(conn)

    from kerf_cloud.git_providers.gitlab import GitLabProvider

    p = GitLabProvider(_gitlab_settings(), pool=pool)
    run(p.connect(pid, gitlab_namespace="acme", gitlab_project="widget"))

    # Confirm connected.
    status_before = run(p.status(pid))
    assert status_before["connected"] is True

    # Disconnect.
    run(p.disconnect(pid))

    # Verify columns NULLed.
    row = run(conn.fetchrow(
        "SELECT gitlab_namespace, gitlab_project FROM cloud_git_repos WHERE project_id = $1",
        uuid.UUID(pid),
    ))
    assert row["gitlab_namespace"] is None
    assert row["gitlab_project"] is None

    # status() now returns disconnected.
    status_after = run(p.status(pid))
    assert status_after["connected"] is False


def test_status_reflects_connection_state(fixtures):
    """status() returns False before connect, True after, False after disconnect."""
    conn, uid, pid = fixtures
    pool = _make_pool(conn)

    from kerf_cloud.git_providers.gitlab import GitLabProvider

    p = GitLabProvider(_gitlab_settings(), pool=pool)

    # Initially disconnected (fresh project).
    s0 = run(p.status(pid))
    assert s0["connected"] is False

    run(p.connect(pid, gitlab_namespace="ns", gitlab_project="repo"))
    s1 = run(p.status(pid))
    assert s1["connected"] is True

    run(p.disconnect(pid))
    s2 = run(p.status(pid))
    assert s2["connected"] is False


def test_second_connect_overwrites_mirror(fixtures):
    """A second connect() replaces the previously stored mirror coordinates."""
    conn, uid, pid = fixtures
    pool = _make_pool(conn)

    from kerf_cloud.git_providers.gitlab import GitLabProvider

    p = GitLabProvider(_gitlab_settings(), pool=pool)
    run(p.connect(pid, gitlab_namespace="old-ns", gitlab_project="old-proj"))
    run(p.connect(
        pid,
        gitlab_namespace="new-ns",
        gitlab_project="new-proj",
        gitlab_host="https://gitlab.internal",
    ))

    row = run(conn.fetchrow(
        "SELECT gitlab_host, gitlab_namespace, gitlab_project "
        "FROM cloud_git_repos WHERE project_id = $1",
        uuid.UUID(pid),
    ))
    assert row["gitlab_namespace"] == "new-ns"
    assert row["gitlab_project"] == "new-proj"
    assert row["gitlab_host"] == "https://gitlab.internal"
