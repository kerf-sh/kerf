"""T-125 — live cloud-git commit handler wired to the materialize spine.

Proves, against a live Postgres + a local (temp-dir) object store + real
pygit2 bare repos, that:

  * POST /projects/{pid}/git/commit no longer records a synthetic random
    sha — it runs ``materialize_and_commit``, producing a REAL git tree
    (large/binary files offloaded as canonical LFS pointers, small UTF-8
    files inlined verbatim) and records the REAL commit sha in
    ``cloud_git_commits``;
  * the ledger/commit ordering is git-then-cloud_git_commits: the recorded
    sha always exists as a real object in the repo;
  * the cheap-fork endpoint shares object-store keys — forking adds
    ``blob_refs`` rows for the fork pointing at the SAME oids with NO second
    byte copy in the object store, and the fork gets its own repo whose
    LFS pointers resolve to the shared keys.

These ``cloud_git_*`` tables have no migration in-tree and are absent from
the shared dev DB; the fixture creates them with CREATE TABLE IF NOT EXISTS
(purely additive — never dropped/truncated) and scopes every row with a
unique suffix so the shared DB is left intact.

Run with:

    DATABASE_URL="postgres://pc@localhost:5432/kerf?sslmode=disable" \
        python3 -m pytest packages/kerf-cloud/tests/test_git_commit_materialize.py -q
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pygit2
import pytest

from kerf_core.storage import set_storage
from kerf_core.storage.factory import create_storage, resolve_project_repo
from kerf_core.storage.lfs_pointer import serialize as serialize_pointer
from kerf_core.storage.materialize import blob_storage_key

import kerf_cloud.routes as routes

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_TAG = "test-t125-"

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
# Schema bootstrap (additive only — IF NOT EXISTS, never dropped/truncated)
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
CREATE TABLE IF NOT EXISTS cloud_git_commits (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    sha          text NOT NULL,
    message      text NOT NULL,
    author_name  text NOT NULL DEFAULT '',
    author_email text NOT NULL DEFAULT '',
    branch       text NOT NULL DEFAULT 'main',
    parent_shas  text[] NOT NULL DEFAULT '{}',
    created_at   timestamptz NOT NULL DEFAULT now()
);
"""


async def _bootstrap_schema(conn: asyncpg.Connection) -> None:
    for stmt in _CLOUD_GIT_DDL.split(";"):
        s = stmt.strip()
        if s:
            await conn.execute(s)


# ---------------------------------------------------------------------------
# Tenant fixtures (unique-suffixed; self-cleaning)
# ---------------------------------------------------------------------------

async def _make_user(conn: asyncpg.Connection) -> uuid.UUID:
    uid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO users (id, email, name) VALUES ($1, $2, $3)",
        uid, f"{_TAG}{uid.hex}@test.invalid", f"T125 User {uid}",
    )
    return uid


async def _make_workspace(conn: asyncpg.Connection, owner: uuid.UUID) -> uuid.UUID:
    ws = uuid.uuid4()
    await conn.execute(
        "INSERT INTO workspaces (id, slug, name, created_by) VALUES ($1, $2, $3, $4)",
        ws, f"{_TAG}{ws.hex}", f"T125 WS {ws}", owner,
    )
    return ws


async def _make_project(conn: asyncpg.Connection, ws: uuid.UUID) -> uuid.UUID:
    pid = uuid.uuid4()
    await conn.execute(
        "INSERT INTO projects (id, workspace_id, name) VALUES ($1, $2, $3)",
        pid, ws, f"test-t125-proj-{pid}",
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


async def _add_file(conn, pid, name, content: bytes, parent=None, storage=None):
    """Insert a file the way the real app does.

    Small UTF-8 text → inline ``content`` column. Large/binary content →
    object store under ``storage_key`` (matches production; the commit
    handler fetches it back once and re-keys it content-addressed).
    """
    fid = uuid.uuid4()
    is_text = False
    try:
        content.decode("utf-8")
        is_text = len(content) < 1_048_576
    except UnicodeDecodeError:
        is_text = False

    if is_text:
        await conn.execute(
            "INSERT INTO files (id, project_id, parent_id, name, kind, content) "
            "VALUES ($1, $2, $3, $4, 'file', $5)",
            fid, pid, parent, name, content.decode("utf-8"),
        )
    else:
        import io
        key = f"projects/{pid}/files/{fid}/{name}"
        await storage.put(key, io.BytesIO(content), "application/octet-stream", len(content))
        await conn.execute(
            "INSERT INTO files (id, project_id, parent_id, name, kind, content, "
            "storage_key, size) VALUES ($1, $2, $3, $4, 'file', '', $5, $6)",
            fid, pid, parent, name, key, len(content),
        )
    return fid


async def _cleanup(conn: asyncpg.Connection) -> None:
    await conn.execute(
        "DELETE FROM blob_refs WHERE project_id IN "
        "(SELECT id FROM projects WHERE name LIKE $1)",
        "test-t125-proj-%",
    )
    await conn.execute(
        "DELETE FROM blob_objects WHERE first_workspace_id IN "
        "(SELECT id FROM workspaces WHERE slug LIKE $1)",
        f"{_TAG}%",
    )
    await conn.execute("DELETE FROM projects  WHERE name LIKE $1", "test-t125-proj-%")
    await conn.execute("DELETE FROM workspaces WHERE slug LIKE $1", f"{_TAG}%")
    await conn.execute("DELETE FROM users      WHERE email LIKE $1", f"{_TAG}%@test.invalid")


@pytest.fixture(scope="module")
def conn():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set")
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
    with tempfile.TemporaryDirectory(prefix="kerf-t125-") as d:
        yield d


@pytest.fixture()
def storage(workdir):
    st = create_storage(
        backend="local", local_storage_path=os.path.join(workdir, "objs")
    )
    set_storage(st)
    return st


# ---------------------------------------------------------------------------
# Pool shim: route handlers do `async with pool.acquire() as conn`
# ---------------------------------------------------------------------------

def _pool_for(conn):
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _req():
    r = MagicMock()
    return r


def _patches(conn, *, uid):
    pool = _pool_for(conn)
    return [
        patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=pool)),
        patch("kerf_cloud.routes.require_editor", AsyncMock(return_value=str(uid))),
        patch("kerf_cloud.routes.require_role",
              AsyncMock(return_value=(str(uid), "owner"))),
    ]


def _body_request(body: dict):
    r = MagicMock()
    r.json = AsyncMock(return_value=body)
    r.body = AsyncMock(return_value=b"x")
    return r


def _tree_bytes(repo_dir: str, path: str, ref: str = "HEAD") -> bytes:
    repo = pygit2.Repository(repo_dir)
    commit = repo.revparse_single(ref)
    tree = commit.tree if isinstance(commit, pygit2.Commit) else commit.peel(pygit2.Commit).tree
    return bytes(repo[tree[path].id].data)


# ---------------------------------------------------------------------------
# 1. Real commit: large file → LFS pointer, small file → inline verbatim,
#    cloud_git_commits records the REAL sha.
# ---------------------------------------------------------------------------

def test_commit_produces_real_tree_and_records_real_sha(conn, storage, workdir):
    uid = run(_make_user(conn))
    ws = run(_make_workspace(conn, uid))
    pid = run(_make_project(conn, ws))

    big = b"S" * (1_048_576 + 64)  # > git_inline_max_bytes → blob
    oid = hashlib.sha256(big).hexdigest()
    small = b"print('hi from kerf')\n"  # tiny UTF-8 → inline

    run(_add_file(conn, pid, "model.step", big, storage=storage))
    run(_add_file(conn, pid, "main.py", small, storage=storage))

    cms = _patches(conn, uid=uid)
    for c in cms:
        c.start()
    try:
        resp = run(routes.git_commit(
            _body_request({"message": "first real commit", "branch": "main"}),
            payload={"sub": str(uid)},
            pid=str(pid),
        ))
    finally:
        for c in reversed(cms):
            c.stop()

    sha = resp["sha"]
    assert resp["branch"] == "main"
    # Not a synthetic 40-hex token: it must be a resolvable git commit.
    loc = resolve_project_repo(str(pid), storage)
    repo = pygit2.Repository(loc.repo_dir)
    obj = repo.revparse_single(sha)
    assert isinstance(obj.peel(pygit2.Commit), pygit2.Commit)
    assert str(obj.peel(pygit2.Commit).id) == sha

    # Large file offloaded as the canonical LFS pointer (not raw bytes).
    assert resp["blobs"] == {"model.step": oid}
    assert resp["inlined"] == ["main.py"]
    assert _tree_bytes(loc.repo_dir, "model.step") == serialize_pointer(oid, len(big))
    # Small file inlined verbatim.
    assert _tree_bytes(loc.repo_dir, "main.py") == small

    # Object bytes physically present once, keyed content-addressed.
    obj_path = os.path.join(workdir, "objs", blob_storage_key(oid))
    assert os.path.isfile(obj_path)
    with open(obj_path, "rb") as f:
        assert f.read() == big

    # cloud_git_commits recorded the REAL sha (ordering: git first).
    row = run(conn.fetchrow(
        "SELECT sha, message, branch, parent_shas FROM cloud_git_commits WHERE project_id = $1",
        pid,
    ))
    assert row["sha"] == sha
    assert row["message"] == "first real commit"
    assert row["branch"] == "main"
    # First commit — no parents.
    assert list(row["parent_shas"]) == []

    # Branch + repo head advanced to the real sha.
    b = run(conn.fetchval(
        "SELECT head_sha FROM cloud_git_branches WHERE project_id = $1 AND name = 'main'",
        pid,
    ))
    assert b == sha
    rh = run(conn.fetchval(
        "SELECT head_sha FROM cloud_git_repos WHERE project_id = $1", pid
    ))
    assert rh == sha

    # Ledger rows for the offloaded blob.
    bo = run(conn.fetchrow(
        "SELECT size_bytes, first_workspace_id FROM blob_objects WHERE oid = $1", oid
    ))
    assert bo["size_bytes"] == len(big)
    assert bo["first_workspace_id"] == ws


# ---------------------------------------------------------------------------
# 2. Second commit chains history — recorded sha is always a real commit.
# ---------------------------------------------------------------------------

def test_second_commit_chains_history(conn, storage, workdir):
    uid = run(_make_user(conn))
    ws = run(_make_workspace(conn, uid))
    pid = run(_make_project(conn, ws))

    run(_add_file(conn, pid, "README.md", b"v1\n", storage=storage))
    cms = _patches(conn, uid=uid)
    for c in cms:
        c.start()
    try:
        r1 = run(routes.git_commit(
            _body_request({"message": "c1"}), payload={"sub": str(uid)}, pid=str(pid)
        ))
        run(conn.execute("UPDATE files SET content = 'v2\n' WHERE project_id = $1", pid))
        r2 = run(routes.git_commit(
            _body_request({"message": "c2"}), payload={"sub": str(uid)}, pid=str(pid)
        ))
    finally:
        for c in reversed(cms):
            c.stop()

    assert r1["sha"] != r2["sha"]
    loc = resolve_project_repo(str(pid), storage)
    repo = pygit2.Repository(loc.repo_dir)
    head = repo.revparse_single("HEAD").peel(pygit2.Commit)
    assert str(head.id) == r2["sha"]
    assert [str(p.id) for p in head.parents] == [r1["sha"]]
    assert _tree_bytes(loc.repo_dir, "README.md") == b"v2\n"

    # Every recorded sha resolves to a real commit object (ledger never
    # ahead of git).
    rows = run(conn.fetch(
        "SELECT sha FROM cloud_git_commits WHERE project_id = $1", pid
    ))
    for rec in rows:
        assert isinstance(
            repo.revparse_single(rec["sha"]).peel(pygit2.Commit), pygit2.Commit
        )


# ---------------------------------------------------------------------------
# 3. Cheap fork: shares object-store keys, NO second byte copy, both
#    projects' blob_refs point at the same oid.
# ---------------------------------------------------------------------------

def test_fork_shares_object_store_keys_no_byte_copy(conn, storage, workdir):
    uid = run(_make_user(conn))
    ws = run(_make_workspace(conn, uid))
    src = run(_make_project(conn, ws))
    dst = run(_make_project(conn, ws))

    big = os.urandom(1_400_000)  # > 1 MiB binary → blob
    oid = hashlib.sha256(big).hexdigest()
    run(_add_file(conn, src, "part.step", big, storage=storage))

    cms = _patches(conn, uid=uid)
    for c in cms:
        c.start()
    try:
        run(routes.git_commit(
            _body_request({"message": "seed"}), payload={"sub": str(uid)}, pid=str(src)
        ))

        obj_path = os.path.join(workdir, "objs", blob_storage_key(oid))
        assert os.path.isfile(obj_path)
        mtime_before = os.stat(obj_path).st_mtime_ns
        size_before = os.stat(obj_path).st_size

        fork_resp = run(routes.git_fork(
            _body_request({"target_project_id": str(dst)}),
            payload={"sub": str(uid)},
            pid=str(src),
        ))
    finally:
        for c in reversed(cms):
            c.stop()

    assert fork_resp["shared_objects"] == 1

    # NO second byte copy: the single content-addressed object is byte-for-
    # byte untouched (same mtime, same size, still exactly one file).
    assert os.path.isfile(obj_path)
    assert os.stat(obj_path).st_mtime_ns == mtime_before
    assert os.stat(obj_path).st_size == size_before
    blob_dir = os.path.join(workdir, "objs", "blobs", oid[:2])
    assert os.listdir(blob_dir) == [oid]  # exactly one physical object

    # Both projects' blob_refs point at the SAME oid.
    src_refs = run(conn.fetch(
        "SELECT oid, path FROM blob_refs WHERE project_id = $1", src
    ))
    dst_refs = run(conn.fetch(
        "SELECT oid, path FROM blob_refs WHERE project_id = $1", dst
    ))
    assert [(r["oid"], r["path"]) for r in src_refs] == [(oid, "part.step")]
    assert [(r["oid"], r["path"]) for r in dst_refs] == [(oid, "part.step")]

    # The fork has its OWN repo whose LFS pointer resolves to the shared key.
    src_loc = resolve_project_repo(str(src), storage)
    dst_loc = resolve_project_repo(str(dst), storage)
    assert src_loc.repo_dir != dst_loc.repo_dir
    assert _tree_bytes(dst_loc.repo_dir, "part.step") == serialize_pointer(oid, len(big))


# ---------------------------------------------------------------------------
# 4. Empty message rejected (unchanged contract).
# ---------------------------------------------------------------------------

def test_empty_message_rejected(conn, storage):
    uid = run(_make_user(conn))
    ws = run(_make_workspace(conn, uid))
    pid = run(_make_project(conn, ws))

    cms = _patches(conn, uid=uid)
    for c in cms:
        c.start()
    try:
        with pytest.raises(routes.HTTPException) as ei:
            run(routes.git_commit(
                _body_request({"message": "   "}),
                payload={"sub": str(uid)},
                pid=str(pid),
            ))
        assert ei.value.status_code == 400
    finally:
        for c in reversed(cms):
            c.stop()


# ---------------------------------------------------------------------------
# 5. T-151 — parent_shas recorded in cloud_git_commits + returned by /git/log
# ---------------------------------------------------------------------------

def test_parent_shas_empty_on_first_commit_populated_on_second(conn, storage, workdir):
    """First commit has no parents; second commit records the first's sha."""
    uid = run(_make_user(conn))
    ws = run(_make_workspace(conn, uid))
    pid = run(_make_project(conn, ws))

    run(_add_file(conn, pid, "README.md", b"v1\n", storage=storage))

    cms = _patches(conn, uid=uid)
    for c in cms:
        c.start()
    try:
        r1 = run(routes.git_commit(
            _body_request({"message": "root commit"}),
            payload={"sub": str(uid)},
            pid=str(pid),
        ))
        run(conn.execute("UPDATE files SET content = 'v2\n' WHERE project_id = $1", pid))
        r2 = run(routes.git_commit(
            _body_request({"message": "second commit"}),
            payload={"sub": str(uid)},
            pid=str(pid),
        ))
    finally:
        for c in reversed(cms):
            c.stop()

    rows = run(conn.fetch(
        "SELECT sha, parent_shas FROM cloud_git_commits WHERE project_id = $1 ORDER BY created_at ASC",
        pid,
    ))
    assert len(rows) == 2
    first_row = rows[0]
    second_row = rows[1]

    # Root commit has no parents.
    assert list(first_row["parent_shas"]) == []
    assert first_row["sha"] == r1["sha"]

    # Second commit records the first commit's sha as its parent.
    assert list(second_row["parent_shas"]) == [r1["sha"]]
    assert second_row["sha"] == r2["sha"]


def test_git_log_returns_parent_shas(conn, storage, workdir):
    """GET /projects/{pid}/git/log includes parent_shas in each entry."""
    uid = run(_make_user(conn))
    ws = run(_make_workspace(conn, uid))
    pid = run(_make_project(conn, ws))

    run(_add_file(conn, pid, "README.md", b"hello\n", storage=storage))

    cms = _patches(conn, uid=uid)
    for c in cms:
        c.start()
    try:
        r1 = run(routes.git_commit(
            _body_request({"message": "first"}),
            payload={"sub": str(uid)},
            pid=str(pid),
        ))
        run(conn.execute("UPDATE files SET content = 'world\n' WHERE project_id = $1", pid))
        r2 = run(routes.git_commit(
            _body_request({"message": "second"}),
            payload={"sub": str(uid)},
            pid=str(pid),
        ))
    finally:
        for c in reversed(cms):
            c.stop()

    # Build a fake Request for git_log (query_params: branch=None, limit=50).
    req = MagicMock()
    _qp = MagicMock()
    _qp.get = lambda k, d=None: {"limit": "50"}.get(k, d)
    req.query_params = _qp
    pool = _pool_for(conn)

    log_patches = [
        patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=pool)),
        patch("kerf_cloud.routes.require_role",
              AsyncMock(return_value=(str(uid), "owner"))),
    ]
    for p in log_patches:
        p.start()
    try:
        log = run(routes.git_log(req, payload={"sub": str(uid)}, pid=str(pid)))
    finally:
        for p in reversed(log_patches):
            p.stop()

    # log is ordered newest-first
    by_sha = {entry["sha"]: entry for entry in log}
    assert r1["sha"] in by_sha
    assert r2["sha"] in by_sha

    # parent_shas must be present and correct
    assert "parent_shas" in by_sha[r1["sha"]]
    assert "parent_shas" in by_sha[r2["sha"]]
    assert by_sha[r1["sha"]]["parent_shas"] == []
    assert by_sha[r2["sha"]]["parent_shas"] == [r1["sha"]]
