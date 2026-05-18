"""T-185 — auto_commit_if_idle pytest suite.

Tests run against a live Postgres instance (DATABASE_URL env-var required).
Each test gets a fresh workspace + project; rows are scoped with a unique
tag and cleaned up in the autouse fixture.

Run:

    DATABASE_URL="postgres://pc@localhost:5432/kerf?sslmode=disable" \\
        python3 -m pytest packages/kerf-cloud/tests/test_auto_commit.py -x -q
"""

from __future__ import annotations

import asyncio
import datetime
import os
import tempfile
import uuid

import asyncpg
import pytest

from kerf_core.storage.factory import create_storage, resolve_project_repo
from kerf_core.storage.materialize import auto_commit_if_idle

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgres://pc@localhost:5432/kerf?sslmode=disable"
)
_TAG = "test-t185-"

# ---------------------------------------------------------------------------
# Event loop helpers
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
# Schema bootstrap — additive only; never drops existing tables.
# ---------------------------------------------------------------------------

_CLOUD_GIT_DDL = """
CREATE TABLE IF NOT EXISTS cloud_git_repos (
    project_id        uuid PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    default_branch    text NOT NULL DEFAULT 'main',
    head_sha          text NOT NULL DEFAULT '',
    github_remote_url text,
    github_owner      text,
    github_repo       text,
    last_pushed_at    timestamptz,
    last_fetched_at   timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cloud_git_branches (
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name       text NOT NULL,
    head_sha   text NOT NULL DEFAULT '',
    is_default boolean NOT NULL DEFAULT false,
    PRIMARY KEY (project_id, name)
);
CREATE TABLE IF NOT EXISTS cloud_git_commits (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    sha          text NOT NULL,
    message      text NOT NULL,
    author_name  text NOT NULL DEFAULT '',
    author_email text NOT NULL DEFAULT '',
    branch       text NOT NULL DEFAULT 'main',
    kind         text NOT NULL DEFAULT 'manual' CHECK (kind IN ('manual', 'autosave')),
    created_at   timestamptz NOT NULL DEFAULT now()
);
"""


async def _bootstrap_schema(conn: asyncpg.Connection) -> None:
    for stmt in _CLOUD_GIT_DDL.split(";"):
        s = stmt.strip()
        if s:
            await conn.execute(s)


# ---------------------------------------------------------------------------
# Tenant helpers
# ---------------------------------------------------------------------------

async def _make_user(conn: asyncpg.Connection) -> uuid.UUID:
    uid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO users (id, email, name) VALUES ($1, $2, $3)",
        uid,
        f"{_TAG}{uid.hex}@test.invalid",
        f"T185 User {uid}",
    )
    return uid


async def _make_workspace(conn: asyncpg.Connection, owner: uuid.UUID) -> uuid.UUID:
    ws = uuid.uuid4()
    await conn.execute(
        "INSERT INTO workspaces (id, slug, name, created_by) VALUES ($1, $2, $3, $4)",
        ws,
        f"{_TAG}{ws.hex}",
        f"T185 WS {ws}",
        owner,
    )
    return ws


async def _make_project(conn: asyncpg.Connection, ws: uuid.UUID) -> uuid.UUID:
    pid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO projects (id, workspace_id, name) VALUES ($1, $2, $3)",
        pid,
        ws,
        f"test-t185-proj-{pid}",
    )
    await conn.execute(
        "INSERT INTO cloud_git_repos (project_id, default_branch) VALUES ($1, 'main')",
        pid,
    )
    await conn.execute(
        "INSERT INTO cloud_git_branches (project_id, name, is_default) "
        "VALUES ($1, 'main', true)",
        pid,
    )
    return pid


async def _add_file(conn: asyncpg.Connection, pid: uuid.UUID, name: str, content: str) -> uuid.UUID:
    fid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO files (id, project_id, name, kind, content) VALUES ($1, $2, $3, 'file', $4)",
        fid,
        pid,
        name,
        content,
    )
    return fid


async def _add_revision(
    conn: asyncpg.Connection,
    file_id: uuid.UUID,
    content: str,
    *,
    ts: datetime.datetime | None = None,
) -> uuid.UUID:
    rid = uuid.uuid4()
    if ts is not None:
        await conn.execute(
            "INSERT INTO file_revisions (id, file_id, content, source, created_at) "
            "VALUES ($1, $2, $3, 'user', $4)",
            rid,
            file_id,
            content,
            ts,
        )
    else:
        await conn.execute(
            "INSERT INTO file_revisions (id, file_id, content, source) "
            "VALUES ($1, $2, $3, 'user')",
            rid,
            file_id,
            content,
        )
    return rid


async def _add_commit(
    conn: asyncpg.Connection,
    pid: uuid.UUID,
    *,
    ts: datetime.datetime | None = None,
    kind: str = "manual",
) -> None:
    """Insert a synthetic cloud_git_commits row at a given timestamp."""
    sha = uuid.uuid4().hex * 1  # not a real git sha, but sufficient for tests
    if ts is not None:
        await conn.execute(
            "INSERT INTO cloud_git_commits "
            "(project_id, sha, message, author_name, author_email, branch, kind, created_at) "
            "VALUES ($1, $2, 'test commit', '', '', 'main', $3, $4)",
            pid,
            sha,
            kind,
            ts,
        )
    else:
        await conn.execute(
            "INSERT INTO cloud_git_commits "
            "(project_id, sha, message, author_name, author_email, branch, kind) "
            "VALUES ($1, $2, 'test commit', '', '', 'main', $3)",
            pid,
            sha,
            kind,
        )


async def _cleanup(conn: asyncpg.Connection) -> None:
    await conn.execute(
        "DELETE FROM cloud_git_commits WHERE project_id IN "
        "(SELECT id FROM projects WHERE name LIKE $1)",
        "test-t185-proj-%",
    )
    await conn.execute(
        "DELETE FROM blob_refs WHERE project_id IN "
        "(SELECT id FROM projects WHERE name LIKE $1)",
        "test-t185-proj-%",
    )
    await conn.execute(
        "DELETE FROM blob_objects WHERE first_workspace_id IN "
        "(SELECT id FROM workspaces WHERE slug LIKE $1)",
        f"{_TAG}%",
    )
    await conn.execute("DELETE FROM projects  WHERE name  LIKE $1", "test-t185-proj-%")
    await conn.execute("DELETE FROM workspaces WHERE slug  LIKE $1", f"{_TAG}%")
    await conn.execute("DELETE FROM users      WHERE email LIKE $1", f"{_TAG}%@test.invalid")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def conn():
    c = run(asyncpg.connect(DATABASE_URL))
    run(_bootstrap_schema(c))
    yield c
    run(c.close())


@pytest.fixture(autouse=True)
def cleanup(conn):
    yield
    run(_cleanup(conn))


@pytest.fixture()
def workdir():
    with tempfile.TemporaryDirectory(prefix="kerf-t185-") as d:
        yield d


@pytest.fixture()
def storage(workdir):
    return create_storage(
        backend="local",
        local_storage_path=os.path.join(workdir, "objs"),
    )


# ---------------------------------------------------------------------------
# Helper that calls auto_commit_if_idle synchronously via run()
# ---------------------------------------------------------------------------

def _auto_commit(ws_id, conn, storage, *, idle_minutes=15):
    return run(
        auto_commit_if_idle(
            ws_id,
            db_conn=conn,
            storage=storage,
            idle_minutes=idle_minutes,
        )
    )


# ---------------------------------------------------------------------------
# Test 1: no autosave when zero file_revisions exist
# ---------------------------------------------------------------------------

def test_no_autosave_when_zero_revisions(conn, storage):
    uid = run(_make_user(conn))
    ws = run(_make_workspace(conn, uid))
    pid = run(_make_project(conn, ws))
    # Add a file but no revisions
    run(_add_file(conn, pid, "empty.py", ""))

    result = _auto_commit(ws, conn, storage)
    assert result is None

    rows = run(conn.fetch(
        "SELECT kind FROM cloud_git_commits WHERE project_id = $1", pid
    ))
    assert len(rows) == 0


# ---------------------------------------------------------------------------
# Test 2: no autosave when idle_minutes hasn't elapsed
# ---------------------------------------------------------------------------

def test_no_autosave_when_idle_not_elapsed(conn, storage):
    uid = run(_make_user(conn))
    ws = run(_make_workspace(conn, uid))
    pid = run(_make_project(conn, ws))

    fid = run(_add_file(conn, pid, "main.py", "v1"))
    # Commit 10 minutes ago
    commit_ts = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(minutes=10)
    run(_add_commit(conn, pid, ts=commit_ts))
    # Revision 5 minutes ago (after the commit)
    rev_ts = commit_ts + datetime.timedelta(minutes=5)
    run(_add_revision(conn, fid, "v2", ts=rev_ts))

    # With idle_minutes=15 the 10-minute gap is not enough
    result = _auto_commit(ws, conn, storage, idle_minutes=15)
    assert result is None

    rows = run(conn.fetch(
        "SELECT kind FROM cloud_git_commits WHERE project_id = $1", pid
    ))
    # Still only the one manual commit
    assert len(rows) == 1
    assert rows[0]["kind"] == "manual"


# ---------------------------------------------------------------------------
# Test 3: autosave fires when conditions are met; row has kind='autosave'
# ---------------------------------------------------------------------------

def test_autosave_fires_when_idle_and_new_revisions(conn, storage):
    uid = run(_make_user(conn))
    ws = run(_make_workspace(conn, uid))
    pid = run(_make_project(conn, ws))

    fid = run(_add_file(conn, pid, "main.py", "v1"))
    # Commit 20 minutes ago
    commit_ts = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(minutes=20)
    run(_add_commit(conn, pid, ts=commit_ts))
    # Revision 18 minutes ago (after the commit, idle_minutes=15 elapsed)
    rev_ts = commit_ts + datetime.timedelta(minutes=2)
    run(_add_revision(conn, fid, "v2", ts=rev_ts))

    result = _auto_commit(ws, conn, storage, idle_minutes=15)
    assert result is not None
    assert result.kind == "autosave"

    rows = run(conn.fetch(
        "SELECT kind, message FROM cloud_git_commits WHERE project_id = $1 ORDER BY created_at",
        pid,
    ))
    assert len(rows) == 2
    assert rows[0]["kind"] == "manual"
    assert rows[1]["kind"] == "autosave"
    assert rows[1]["message"].startswith("autosave ")


# ---------------------------------------------------------------------------
# Test 4: second call with no new edits is a no-op (idempotent)
# ---------------------------------------------------------------------------

def test_second_call_is_noop(conn, storage):
    uid = run(_make_user(conn))
    ws = run(_make_workspace(conn, uid))
    pid = run(_make_project(conn, ws))

    fid = run(_add_file(conn, pid, "main.py", "v1"))
    # Commit 30 minutes ago
    commit_ts = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(minutes=30)
    run(_add_commit(conn, pid, ts=commit_ts))
    # Revision 28 minutes ago
    rev_ts = commit_ts + datetime.timedelta(minutes=2)
    run(_add_revision(conn, fid, "v2", ts=rev_ts))

    # First call — should fire
    r1 = _auto_commit(ws, conn, storage, idle_minutes=15)
    assert r1 is not None

    # Second call immediately — no new revisions since the autosave, so no-op
    r2 = _auto_commit(ws, conn, storage, idle_minutes=15)
    assert r2 is None

    rows = run(conn.fetch(
        "SELECT kind FROM cloud_git_commits WHERE project_id = $1 ORDER BY created_at",
        pid,
    ))
    # Exactly: 1 manual + 1 autosave — no duplicate
    assert len(rows) == 2
    assert rows[0]["kind"] == "manual"
    assert rows[1]["kind"] == "autosave"
