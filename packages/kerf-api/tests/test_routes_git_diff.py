"""Integration tests for the git diff + resolve endpoints (T-186).

Covers:
  - GET /api/workspaces/{wsid}/git/commits/{sha}/diff
      * returns correct JSON shape for a textual change
      * marks STEP / binary files correctly (binary=true, text_diff absent)
      * returns 404 for an unknown sha
      * returns 404 for a project the user is not a member of
  - POST /api/workspaces/{wsid}/git/resolve
      * writes a new commit; the file content matches the picked side

DB safety:
  - All rows are written with a unique run-prefix and cleaned up in a
    finally block.  No DROP / CREATE / TRUNCATE.
  - storage_backend=local (temp dir), never real S3.

Run:
    DATABASE_URL="postgres://pc@localhost:5432/kerf?sslmode=disable" \\
        python3 -m pytest packages/kerf-api/tests/test_routes_git_diff.py -q
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import secrets
import sys
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator

import asyncpg
import jwt
import pygit2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# sys.path bootstrap
# ---------------------------------------------------------------------------
_HERE = pathlib.Path(__file__).parent
_PACKAGES_ROOT = _HERE.parent.parent

for _entry in _PACKAGES_ROOT.iterdir():
    if not _entry.name.startswith("kerf-"):
        continue
    _src = _entry / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DB_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgres://pc@localhost:5432/kerf?sslmode=disable",
)
_JWT_SECRET: str = "dev-secret-change-in-production"
_RUN_PREFIX: str = f"gitdiff-{secrets.token_hex(4)}"

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def _mint_jwt(user_id: str) -> str:
    now = datetime.now(tz=timezone.utc)
    return jwt.encode(
        {"sub": user_id, "exp": now + timedelta(hours=1), "iat": now},
        _JWT_SECRET,
        algorithm="HS256",
    )


def _auth_headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_mint_jwt(user_id)}"}


# ---------------------------------------------------------------------------
# Storage temp dir (module-level)
# ---------------------------------------------------------------------------

_STORAGE_TMPDIR: str | None = None
_FIXTURE_DATA: dict | None = None


def _storage_root() -> str:
    global _STORAGE_TMPDIR
    if _STORAGE_TMPDIR is None:
        _STORAGE_TMPDIR = tempfile.mkdtemp(prefix="kerf-gitdiff-test-")
    return _STORAGE_TMPDIR


# ---------------------------------------------------------------------------
# DB fixture helpers
# ---------------------------------------------------------------------------

async def _create_fixtures(db_url: str, storage_root: str) -> dict:
    """Insert minimal rows and build a bare git repo with two commits."""
    from kerf_core.storage.factory import create_storage
    from kerf_core.storage.materialize import materialize_and_commit, FileEntry

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=3)
    data: dict = {}

    try:
        async with pool.acquire() as conn:
            # User
            user_email = f"{_RUN_PREFIX}@gitdiff.test"
            user_row = await conn.fetchrow(
                "INSERT INTO users (email, name, account_role, is_system) "
                "VALUES ($1, $2, 'user', false) RETURNING id",
                user_email, f"GitDiff {_RUN_PREFIX}",
            )
            user_id = str(user_row["id"])
            data["user_id"] = user_id
            data["user_email"] = user_email

            # Workspace
            ws_row = await conn.fetchrow(
                "INSERT INTO workspaces (slug, name, created_by) VALUES ($1, $2, $3) RETURNING id",
                f"ws-{_RUN_PREFIX}", f"WS {_RUN_PREFIX}", user_row["id"],
            )
            ws_id = str(ws_row["id"])
            data["ws_id"] = ws_id

            await conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES ($1, $2, 'owner')",
                ws_row["id"], user_row["id"],
            )

            # Project (id is the wsid used in the URL)
            proj_row = await conn.fetchrow(
                "INSERT INTO projects (workspace_id, name, description, visibility, tags) "
                "VALUES ($1, $2, 'desc', 'private', '{}') RETURNING id",
                ws_row["id"], f"GitDiffProj {_RUN_PREFIX}",
            )
            project_id = str(proj_row["id"])
            data["project_id"] = project_id

            # Second user (not a member) — for auth tests
            other_user_row = await conn.fetchrow(
                "INSERT INTO users (email, name, account_role, is_system) "
                "VALUES ($1, $2, 'user', false) RETURNING id",
                f"{_RUN_PREFIX}-other@gitdiff.test", f"Other {_RUN_PREFIX}",
            )
            data["other_user_id"] = str(other_user_row["id"])

        # Build a real bare git repo with two commits via materialize_and_commit
        storage = create_storage(backend="local", local_storage_path=os.path.join(storage_root, "objs"))
        pool2 = await asyncpg.create_pool(db_url, min_size=1, max_size=2)

        try:
            async with pool2.acquire() as conn2:
                # Commit 1: add a text file + a binary blob
                text_v1 = b"version = 1\nkey = 'hello'\n"
                binary_blob = bytes(range(256)) * 4  # 1 KiB non-UTF-8

                r1 = await materialize_and_commit(
                    repo_dir=_repo_dir(storage_root, project_id),
                    files=[
                        FileEntry(path="config.py", content=text_v1),
                        FileEntry(path="model.step", content=binary_blob),
                    ],
                    project_id=uuid.UUID(project_id),
                    workspace_id=uuid.UUID(ws_id),
                    storage=storage,
                    db_conn=conn2,
                    message="initial commit",
                )
                data["sha1"] = r1.commit_sha

                # Commit 2: modify the text file (binary stays the same)
                text_v2 = b"version = 2\nkey = 'world'\n"
                r2 = await materialize_and_commit(
                    repo_dir=_repo_dir(storage_root, project_id),
                    files=[
                        FileEntry(path="config.py", content=text_v2),
                        FileEntry(path="model.step", content=binary_blob),
                    ],
                    project_id=uuid.UUID(project_id),
                    workspace_id=uuid.UUID(ws_id),
                    storage=storage,
                    db_conn=conn2,
                    message="bump version",
                )
                data["sha2"] = r2.commit_sha

                data["text_v1"] = text_v1
                data["text_v2"] = text_v2
                data["binary_blob"] = binary_blob
        finally:
            await pool2.close()
    finally:
        await pool.close()

    return data


def _repo_dir(storage_root: str, project_id: str) -> str:
    """Mirror the LocalStorage path that resolve_project_repo produces."""
    return os.path.join(storage_root, "objs", "workspaces", project_id, "git")


async def _delete_fixtures(db_url: str, data: dict) -> None:
    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            for uid in [data.get("user_id"), data.get("other_user_id")]:
                if not uid:
                    continue
                uid_u = uuid.UUID(uid)
                await conn.execute("DELETE FROM blob_refs WHERE project_id = $1", uuid.UUID(data["project_id"]))
                await conn.execute(
                    "DELETE FROM blob_objects WHERE first_workspace_id = $1",
                    uuid.UUID(data["ws_id"]),
                )
                await conn.execute("DELETE FROM projects WHERE id = $1", uuid.UUID(data["project_id"]))
                await conn.execute("DELETE FROM workspace_members WHERE workspace_id = $1", uuid.UUID(data["ws_id"]))
                await conn.execute("DELETE FROM workspaces WHERE id = $1", uuid.UUID(data["ws_id"]))
                await conn.execute("DELETE FROM refresh_tokens WHERE user_id = $1", uid_u)
                await conn.execute("DELETE FROM email_tokens WHERE user_id = $1", uid_u)
                await conn.execute("DELETE FROM users WHERE id = $1", uid_u)
    finally:
        await pool.close()


def _get_fixture_data() -> dict:
    global _FIXTURE_DATA
    if _FIXTURE_DATA is None:
        _FIXTURE_DATA = asyncio.run(_create_fixtures(_DB_URL, _storage_root()))
    return _FIXTURE_DATA


@pytest.fixture(scope="session", autouse=True)
def session_fixtures() -> Generator[dict, None, None]:
    data = _get_fixture_data()
    yield data
    asyncio.run(_delete_fixtures(_DB_URL, data))


# ---------------------------------------------------------------------------
# Test app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):
    import kerf_core.db.connection as _conn
    from kerf_core.storage.local import LocalStorage
    from kerf_core.storage import set_storage as _ss

    pool = await asyncpg.create_pool(_DB_URL, min_size=2, max_size=5)
    _conn._pool = pool
    _ss(LocalStorage(root=os.path.join(_storage_root(), "objs")))
    yield
    _conn._pool = None
    await pool.close()


def _build_app() -> FastAPI:
    from kerf_api.routes_git_diff import router as diff_router

    app = FastAPI(lifespan=_lifespan)
    app.include_router(diff_router, prefix="/api")
    return app


@pytest.fixture(scope="session")
def client(session_fixtures) -> Generator[TestClient, None, None]:
    app = _build_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests — GET .../diff
# ---------------------------------------------------------------------------


class TestCommitDiffEndpoint:
    """HTTP-level tests for GET /api/workspaces/{wsid}/git/commits/{sha}/diff."""

    def test_diff_returns_200_and_correct_shape(self, client: TestClient, session_fixtures):
        data = _get_fixture_data()
        pid = data["project_id"]
        uid = data["user_id"]
        sha2 = data["sha2"]

        r = client.get(
            f"/api/workspaces/{pid}/git/commits/{sha2}/diff",
            headers=_auth_headers(uid),
        )
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"

        body = r.json()
        assert body["sha"] == sha2
        assert "parent_sha" in body
        assert "files" in body
        assert isinstance(body["files"], list)

    def test_diff_text_file_has_diff_and_not_binary(self, client: TestClient, session_fixtures):
        data = _get_fixture_data()
        pid = data["project_id"]
        uid = data["user_id"]
        sha2 = data["sha2"]

        r = client.get(
            f"/api/workspaces/{pid}/git/commits/{sha2}/diff",
            headers=_auth_headers(uid),
        )
        assert r.status_code == 200

        body = r.json()
        text_file = next((f for f in body["files"] if f["path"] == "config.py"), None)
        assert text_file is not None, f"config.py not in files: {[f['path'] for f in body['files']]}"
        assert text_file["binary"] is False
        assert "text_diff" in text_file
        assert text_file["text_diff"] is not None
        assert "-version = 1" in text_file["text_diff"]
        assert "+version = 2" in text_file["text_diff"]

    def test_diff_binary_file_is_marked_binary(self, client: TestClient, session_fixtures):
        data = _get_fixture_data()
        pid = data["project_id"]
        uid = data["user_id"]
        sha2 = data["sha2"]

        r = client.get(
            f"/api/workspaces/{pid}/git/commits/{sha2}/diff",
            headers=_auth_headers(uid),
        )
        assert r.status_code == 200

        body = r.json()
        # model.step is stored as LFS pointer (non-UTF-8 binary) → binary=true
        step_file = next((f for f in body["files"] if f["path"] == "model.step"), None)
        # NOTE: if the file was unchanged between commits it won't appear in diff;
        # the initial commit (sha1) adds it so we check sha1 below for the binary test
        # For sha2 with unchanged binary, it may not appear — check sha1 instead

    def test_initial_commit_diff_has_binary_step(self, client: TestClient, session_fixtures):
        data = _get_fixture_data()
        pid = data["project_id"]
        uid = data["user_id"]
        sha1 = data["sha1"]

        r = client.get(
            f"/api/workspaces/{pid}/git/commits/{sha1}/diff",
            headers=_auth_headers(uid),
        )
        assert r.status_code == 200

        body = r.json()
        # Root commit: parent_sha should be ""
        assert body["parent_sha"] == ""
        step_file = next((f for f in body["files"] if f["path"] == "model.step"), None)
        assert step_file is not None, f"model.step missing from root commit diff: {[f['path'] for f in body['files']]}"
        # Binary blob → binary=true, no text_diff
        assert step_file["binary"] is True
        assert "text_diff" not in step_file or step_file.get("text_diff") is None

    def test_diff_unknown_sha_returns_404(self, client: TestClient, session_fixtures):
        data = _get_fixture_data()
        pid = data["project_id"]
        uid = data["user_id"]

        r = client.get(
            f"/api/workspaces/{pid}/git/commits/deadbeef1234deadbeef1234deadbeef1234dead/diff",
            headers=_auth_headers(uid),
        )
        assert r.status_code == 404

    def test_diff_non_member_returns_404(self, client: TestClient, session_fixtures):
        data = _get_fixture_data()
        pid = data["project_id"]
        other_uid = data["other_user_id"]
        sha2 = data["sha2"]

        r = client.get(
            f"/api/workspaces/{pid}/git/commits/{sha2}/diff",
            headers=_auth_headers(other_uid),
        )
        assert r.status_code == 404

    def test_diff_unauthenticated_returns_403(self, client: TestClient, session_fixtures):
        data = _get_fixture_data()
        pid = data["project_id"]
        sha2 = data["sha2"]

        r = client.get(
            f"/api/workspaces/{pid}/git/commits/{sha2}/diff",
        )
        assert r.status_code in (401, 403)

    def test_diff_unknown_project_returns_404(self, client: TestClient, session_fixtures):
        data = _get_fixture_data()
        uid = data["user_id"]
        fake_pid = str(uuid.uuid4())

        r = client.get(
            f"/api/workspaces/{fake_pid}/git/commits/abc123/diff",
            headers=_auth_headers(uid),
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Tests — POST .../resolve
# ---------------------------------------------------------------------------


class TestResolveEndpoint:
    """HTTP-level tests for POST /api/workspaces/{wsid}/git/resolve."""

    def test_resolve_theirs_writes_commit(self, client: TestClient, session_fixtures):
        data = _get_fixture_data()
        pid = data["project_id"]
        uid = data["user_id"]
        sha1 = data["sha1"]

        r = client.post(
            f"/api/workspaces/{pid}/git/resolve",
            json={"path": "config.py", "pick": "theirs", "against_sha": sha1},
            headers=_auth_headers(uid),
        )
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text[:300]}"
        body = r.json()
        assert body.get("ok") is True
        assert "sha" in body
        assert len(body["sha"]) == 40

    def test_resolve_yours_writes_commit(self, client: TestClient, session_fixtures):
        data = _get_fixture_data()
        pid = data["project_id"]
        uid = data["user_id"]
        sha1 = data["sha1"]

        r = client.post(
            f"/api/workspaces/{pid}/git/resolve",
            json={"path": "config.py", "pick": "yours", "against_sha": sha1},
            headers=_auth_headers(uid),
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True

    def test_resolve_invalid_pick_returns_422(self, client: TestClient, session_fixtures):
        data = _get_fixture_data()
        pid = data["project_id"]
        uid = data["user_id"]

        r = client.post(
            f"/api/workspaces/{pid}/git/resolve",
            json={"path": "config.py", "pick": "neither", "against_sha": data["sha1"]},
            headers=_auth_headers(uid),
        )
        assert r.status_code == 422

    def test_resolve_content_matches_theirs(self, client: TestClient, session_fixtures):
        """After resolving with pick=theirs, HEAD should contain the sha1 content."""
        data = _get_fixture_data()
        pid = data["project_id"]
        uid = data["user_id"]
        sha1 = data["sha1"]
        text_v1 = data["text_v1"]
        storage_root = _storage_root()

        r = client.post(
            f"/api/workspaces/{pid}/git/resolve",
            json={"path": "config.py", "pick": "theirs", "against_sha": sha1},
            headers=_auth_headers(uid),
        )
        assert r.status_code == 200
        new_sha = r.json()["sha"]

        # Verify the new commit has the right content at config.py
        repo = pygit2.Repository(_repo_dir(storage_root, pid))
        commit = repo.revparse_single(new_sha).peel(pygit2.Commit)
        entry = commit.tree["config.py"]
        blob_data = bytes(repo[entry.id].data)
        # The content should be text_v1 (from sha1) since we picked "theirs"
        assert blob_data == text_v1
