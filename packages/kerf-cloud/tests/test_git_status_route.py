"""T-305 — GET /projects/{pid}/git/status route tests.

Spec:
  1. 200 + correct shape with one modified file
  2. 200 + empty list when working tree is clean
  3. 403 / 404 paths

Tests call route handler functions directly (same pattern as
test_git_commit_materialize.py) to avoid ASGI thread contention.

DB rule: shared Postgres, unique-suffixed rows via _TAG, no DROP/TRUNCATE.
Run with:

    DATABASE_URL="postgres://pc@localhost:5432/kerf?sslmode=disable" \\
        python -m pytest packages/kerf-cloud/tests/test_git_status_route.py -q
"""
from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_TAG = "test-t305-"

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
# Schema bootstrap (additive only)
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
        uid, f"{_TAG}{uid.hex}@test.invalid", f"T305 User {uid}",
    )
    return uid


async def _make_workspace(conn, owner):
    ws = uuid.uuid4()
    await conn.execute(
        "INSERT INTO workspaces (id, slug, name, created_by) VALUES ($1, $2, $3, $4)",
        ws, f"{_TAG}{ws.hex}", f"T305 WS {ws}", owner,
    )
    return ws


async def _make_project(conn, ws):
    pid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO projects (id, workspace_id, name) VALUES ($1, $2, $3)",
        pid, ws, f"test-t305-proj-{pid}",
    )
    await conn.execute(
        "INSERT INTO cloud_git_repos (project_id, default_branch) VALUES ($1, 'main')",
        pid,
    )
    return pid


async def _add_file(conn, pid, name, content: str):
    fid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO files (id, project_id, name, kind, content) VALUES ($1, $2, $3, 'file', $4)",
        fid, pid, name, content,
    )
    return fid


async def _cleanup(conn):
    await conn.execute("DELETE FROM projects WHERE name LIKE $1", "test-t305-proj-%")
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


def _patches(conn, *, uid, role="owner"):
    pool = _pool_for(conn)
    return [
        patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=pool)),
        patch("kerf_cloud.routes.require_role",
              AsyncMock(return_value=(str(uid), role))),
        # git_status calls _collect_file_entries which uses get_pool_required,
        # and also calls resolve_project_repo + get_storage_required. We mock
        # the storage / repo so the route can run without an actual git repo.
        patch("kerf_cloud.routes.get_storage_required", return_value=MagicMock()),
        patch("kerf_cloud.routes.resolve_project_repo",
              return_value=MagicMock(repo_dir="/nonexistent/repo")),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_status_with_modified_file(conn):
    """200 + correct shape when the live tree differs from HEAD."""
    uid, ws, pid = run(_make_user(conn)), None, None

    async def _setup():
        nonlocal ws, pid
        ws = await _make_workspace(conn, uid)
        pid = await _make_project(conn, ws)
        await _add_file(conn, pid, "main.jscad", "// hello world\n// line 2\n")
    run(_setup())

    import kerf_cloud.routes as routes

    # _collect_file_entries needs a real pool; we let it use our fixture conn.
    # resolve_project_repo → non-existent dir → pygit2 falls through to empty
    # head_map, so every live file is "added".
    with patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=_pool_for(conn))), \
         patch("kerf_cloud.routes.require_role", AsyncMock(return_value=(str(uid), "owner"))), \
         patch("kerf_cloud.routes.get_storage_required", return_value=MagicMock(
             get=AsyncMock(return_value=(MagicMock(read=MagicMock(return_value=b"")), "text/plain")),
         )), \
         patch("kerf_cloud.routes.resolve_project_repo",
               return_value=MagicMock(repo_dir="/tmp/__nonexistent_kerf_t305__")):
        result = run(routes.git_status(
            request=_req(),
            payload={"sub": str(uid)},
            pid=str(pid),
        ))

    assert "changed_files" in result
    # main.jscad is in the live tree but not in HEAD (no repo) → status "added"
    paths = {f["path"] for f in result["changed_files"]}
    assert "main.jscad" in paths
    entry = next(f for f in result["changed_files"] if f["path"] == "main.jscad")
    assert entry["status"] == "added"
    assert isinstance(entry["additions"], int)
    assert isinstance(entry["deletions"], int)


def test_status_clean_working_tree(conn):
    """200 + empty changed_files when live tree exactly matches HEAD."""
    uid, ws, pid = run(_make_user(conn)), None, None

    async def _setup():
        nonlocal ws, pid
        ws = await _make_workspace(conn, uid)
        pid = await _make_project(conn, ws)
        # No files inserted — live tree is empty.
    run(_setup())

    import kerf_cloud.routes as routes

    with patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=_pool_for(conn))), \
         patch("kerf_cloud.routes.require_role", AsyncMock(return_value=(str(uid), "owner"))), \
         patch("kerf_cloud.routes.get_storage_required", return_value=MagicMock()), \
         patch("kerf_cloud.routes.resolve_project_repo",
               return_value=MagicMock(repo_dir="/tmp/__nonexistent_kerf_t305__")):
        result = run(routes.git_status(
            request=_req(),
            payload={"sub": str(uid)},
            pid=str(pid),
        ))

    assert result == {"changed_files": []}


def test_status_requires_auth(conn):
    """require_role raising 403 propagates to the caller."""
    import kerf_cloud.routes as routes

    with patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=_pool_for(conn))), \
         patch("kerf_cloud.routes.require_role",
               AsyncMock(side_effect=HTTPException(status_code=403, detail="forbidden"))):
        with pytest.raises(HTTPException) as exc:
            run(routes.git_status(
                request=_req(),
                payload={"sub": "00000000-0000-0000-0000-000000000000"},
                pid="00000000-0000-0000-0000-000000000001",
            ))
        assert exc.value.status_code == 403


def test_status_project_not_found(conn):
    """require_role raising 404 propagates to the caller."""
    import kerf_cloud.routes as routes

    with patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=_pool_for(conn))), \
         patch("kerf_cloud.routes.require_role",
               AsyncMock(side_effect=HTTPException(status_code=404, detail="project not found"))):
        with pytest.raises(HTTPException) as exc:
            run(routes.git_status(
                request=_req(),
                payload={"sub": "00000000-0000-0000-0000-000000000000"},
                pid="00000000-0000-0000-0000-000000000099",
            ))
        assert exc.value.status_code == 404
