"""T-306 — GET /projects/{pid}/git/branches ahead/behind extension tests.

Spec:
  1. Without remote: ahead/behind are null for every branch.
  2. With remote (mocked pygit2 repo): ahead/behind reflect divergence.

Tests call route handler functions directly (same pattern as existing tests).
DB rule: shared Postgres, unique-suffixed rows via _TAG, no DROP/TRUNCATE.

Run with:

    DATABASE_URL="postgres://pc@localhost:5432/kerf?sslmode=disable" \\
        python -m pytest packages/kerf-cloud/tests/test_git_branches_ahead_behind.py -q
"""
from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_TAG = "test-t306-"

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
# Schema bootstrap
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS cloud_git_repos (
    project_id        uuid PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    default_branch    text NOT NULL DEFAULT 'main',
    head_sha          text NOT NULL DEFAULT '',
    github_remote_url text,
    github_owner      text,
    github_repo       text,
    last_pushed_at    timestamptz,
    last_fetched_at   timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    gitlab_host       text,
    gitlab_namespace  text,
    gitlab_project    text
);
CREATE TABLE IF NOT EXISTS cloud_git_branches (
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name       text NOT NULL,
    head_sha   text NOT NULL DEFAULT '',
    is_default boolean NOT NULL DEFAULT false,
    PRIMARY KEY (project_id, name)
);
"""


async def _bootstrap(conn) -> None:
    for stmt in _DDL.split(";"):
        s = stmt.strip()
        if s:
            await conn.execute(s)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

async def _make_user(conn):
    uid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO users (id, email, name) VALUES ($1, $2, $3)",
        uid, f"{_TAG}{uid.hex}@test.invalid", f"T306 User {uid}",
    )
    return uid


async def _make_workspace(conn, owner):
    ws = uuid.uuid4()
    await conn.execute(
        "INSERT INTO workspaces (id, slug, name, created_by) VALUES ($1, $2, $3, $4)",
        ws, f"{_TAG}{ws.hex}", f"T306 WS {ws}", owner,
    )
    return ws


async def _make_project(conn, ws):
    pid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO projects (id, workspace_id, name) VALUES ($1, $2, $3)",
        pid, ws, f"test-t306-proj-{pid}",
    )
    await conn.execute(
        "INSERT INTO cloud_git_repos (project_id, default_branch) VALUES ($1, 'main')",
        pid,
    )
    await conn.execute(
        "INSERT INTO cloud_git_branches (project_id, name, is_default) VALUES ($1, 'main', true)",
        pid,
    )
    return pid


async def _cleanup(conn):
    await conn.execute("DELETE FROM projects WHERE name LIKE $1", "test-t306-proj-%")
    await conn.execute("DELETE FROM workspaces WHERE slug LIKE $1", f"{_TAG}%")
    await conn.execute("DELETE FROM users WHERE email LIKE $1", f"{_TAG}%@test.invalid")


@pytest.fixture(scope="module")
def conn():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")
    import asyncpg
    c = run(asyncpg.connect(DATABASE_URL))
    run(_bootstrap(c))
    yield c
    run(c.close())


@pytest.fixture(autouse=True)
def cleanup(conn):
    yield
    run(_cleanup(conn))


# ---------------------------------------------------------------------------
# Pool / request shims
# ---------------------------------------------------------------------------

def _pool_for(conn):
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _req():
    return MagicMock()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_branches_without_remote_returns_null_ahead_behind(conn):
    """Without a git repo on disk, ahead/behind must be null for all branches."""
    uid, ws, pid = run(_make_user(conn)), None, None

    async def _setup():
        nonlocal ws, pid
        ws = await _make_workspace(conn, uid)
        pid = await _make_project(conn, ws)
    run(_setup())

    import kerf_cloud.routes as routes

    with patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=_pool_for(conn))), \
         patch("kerf_cloud.routes.require_role", AsyncMock(return_value=(str(uid), "owner"))), \
         patch("kerf_cloud.routes.get_storage_required", return_value=MagicMock()), \
         patch("kerf_cloud.routes.resolve_project_repo",
               return_value=MagicMock(repo_dir="/tmp/__nonexistent_kerf_t306__")):
        result = run(routes.git_branches(
            request=_req(),
            payload={"sub": str(uid)},
            pid=str(pid),
        ))

    assert isinstance(result, list)
    assert len(result) >= 1
    for branch in result:
        assert branch["ahead"] is None, f"Expected ahead=None, got {branch['ahead']}"
        assert branch["behind"] is None, f"Expected behind=None, got {branch['behind']}"
        assert "name" in branch
        assert "head_sha" in branch
        assert "is_default" in branch


def test_branches_with_remote_returns_ahead_behind_counts(conn):
    """With a mocked pygit2 repo that has a tracking branch, ahead/behind are integers."""
    uid, ws, pid = run(_make_user(conn)), None, None

    async def _setup():
        nonlocal ws, pid
        ws = await _make_workspace(conn, uid)
        pid = await _make_project(conn, ws)
    run(_setup())

    import kerf_cloud.routes as routes
    import os as _os

    # Build a fake pygit2 repo object that reports ahead=3, behind=1 for 'main'.
    fake_local_branch = MagicMock()
    fake_local_branch.target = "abc123local"
    fake_upstream = MagicMock()
    fake_upstream.target = "abc123remote"
    fake_local_branch.upstream = fake_upstream

    fake_repo = MagicMock()
    fake_repo.lookup_branch = MagicMock(return_value=fake_local_branch)
    fake_repo.ahead_behind = MagicMock(return_value=(3, 1))

    # Patch os.path.isdir to return True for the fake repo_dir.
    fake_repo_dir = "/tmp/__fake_kerf_t306_repo__"

    with patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=_pool_for(conn))), \
         patch("kerf_cloud.routes.require_role", AsyncMock(return_value=(str(uid), "owner"))), \
         patch("kerf_cloud.routes.get_storage_required", return_value=MagicMock()), \
         patch("kerf_cloud.routes.resolve_project_repo",
               return_value=MagicMock(repo_dir=fake_repo_dir)), \
         patch("os.path.isdir", return_value=True), \
         patch("pygit2.Repository", return_value=fake_repo):
        result = run(routes.git_branches(
            request=_req(),
            payload={"sub": str(uid)},
            pid=str(pid),
        ))

    assert isinstance(result, list)
    main_branch = next((b for b in result if b["name"] == "main"), None)
    assert main_branch is not None
    assert main_branch["ahead"] == 3, f"Expected ahead=3, got {main_branch['ahead']}"
    assert main_branch["behind"] == 1, f"Expected behind=1, got {main_branch['behind']}"
