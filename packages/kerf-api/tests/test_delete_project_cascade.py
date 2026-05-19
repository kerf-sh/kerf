"""
Hermetic tests for DELETE /api/projects/{pid} — T-313 cleanup.

Strategy: monkey-patch get_pool_required, project_workspace_id,
get_user_workspace_role, and get_storage_required so no real DB, JWT,
or S3 connection is needed.

Covers:
  - 404 when project doesn't exist
  - 403 for editor / viewer roles
  - 200 with correct shape for owner
  - storage.delete() called for every blob key collected from files rows
  - storage.delete_prefix() called for the git prefix and photos prefix
  - project row is deleted from DB
"""
from __future__ import annotations

import json
import sys
import os
import uuid
import pathlib
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# sys.path bootstrap — mirrors conftest.py
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
# Fixtures / constants
# ---------------------------------------------------------------------------

_PROJECT_ID = str(uuid.uuid4())
_WORKSPACE_ID = str(uuid.uuid4())
_OWNER_ID = str(uuid.uuid4())
_EDITOR_ID = str(uuid.uuid4())
_VIEWER_ID = str(uuid.uuid4())

_STORAGE_KEY_1 = f"files/{_PROJECT_ID}/main.step"
_STORAGE_KEY_2 = f"files/{_PROJECT_ID}/part.jscad"
_MESH_KEY_1 = f"meshes/{_PROJECT_ID}/main.mesh"
_TESS_MESH_KEY = f"tess/{_PROJECT_ID}/step.mesh"
_THUMBNAIL_KEY = f"thumbnails/{_PROJECT_ID}/thumb.jpg"
_COVER_KEY = f"covers/{_PROJECT_ID}/cover.jpg"
_PHOTO_KEY = f"photos/{_PROJECT_ID}/fileid/shot.jpg"


# ---------------------------------------------------------------------------
# Fake DB objects
# ---------------------------------------------------------------------------

class _FakeRow(dict):
    """Behaves like asyncpg Record for [] access."""
    def __getitem__(self, key):
        return super().__getitem__(key)


_FILE_ROWS = [
    _FakeRow({
        "storage_key": _STORAGE_KEY_1,
        "mesh_storage_key": _MESH_KEY_1,
        "content": "{}",
        "kind": "step",
    }),
    _FakeRow({
        "storage_key": _STORAGE_KEY_2,
        "mesh_storage_key": None,
        "content": json.dumps({"photos": [_PHOTO_KEY]}),
        "kind": "part",
    }),
]

_PROJ_ROW = _FakeRow({
    "thumbnail_storage_key": _THUMBNAIL_KEY,
    "cover_storage_key": _COVER_KEY,
})

_TESS_ROWS = [_FakeRow({"mesh_storage_key": _TESS_MESH_KEY})]

_ROLES: dict[str, str] = {
    _OWNER_ID: "owner",
    _EDITOR_ID: "editor",
    _VIEWER_ID: "viewer",
}


class _FakeConn:
    def __init__(self, *, has_project: bool = True):
        self._has_project = has_project
        self.executes: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def fetchrow(self, query: str, *args, **kwargs):
        q = query.strip().lower()
        if "workspace_id from projects" in q:
            if not self._has_project:
                return None
            return _FakeRow({"workspace_id": _WORKSPACE_ID})
        if "thumbnail_storage_key" in q:
            return _PROJ_ROW
        return None

    async def fetch(self, query: str, *args, **kwargs):
        q = query.strip().lower()
        if "storage_key" in q and "mesh_storage_key" in q and "content" in q:
            return _FILE_ROWS
        if "step_tessellation_jobs" in q:
            return _TESS_ROWS
        return []

    async def execute(self, query: str, *args, **kwargs):
        self.executes.append(query.strip())
        return "DELETE 1"


class _FakePool:
    def __init__(self, *, has_project: bool = True):
        self._has_project = has_project
        self._conn = _FakeConn(has_project=has_project)

    def acquire(self):
        return self._conn


class _FakeStorage:
    def __init__(self):
        self.deleted: list[str] = []
        self.prefixes: list[str] = []

    async def delete(self, key: str) -> None:
        self.deleted.append(key)

    async def delete_prefix(self, prefix: str) -> int:
        self.prefixes.append(prefix)
        return 0


# ---------------------------------------------------------------------------
# App builder
# ---------------------------------------------------------------------------

def _build_app():
    import kerf_core.db.connection as _conn_mod
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    @asynccontextmanager
    async def lifespan(app):
        fake_pool = object()
        _conn_mod._pool = fake_pool
        yield
        _conn_mod._pool = None

    app = FastAPI(lifespan=lifespan)
    from kerf_api.routes import router as api_router
    app.include_router(api_router, prefix="/api")
    return app


def _auth_token(user_id: str) -> str:
    import jwt
    from datetime import datetime, timedelta, timezone
    now = datetime.now(tz=timezone.utc)
    return jwt.encode(
        {"sub": user_id, "exp": now + timedelta(hours=1), "iat": now},
        "dev-secret-change-in-production",
        algorithm="HS256",
    )


def _headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_auth_token(user_id)}"}


# ---------------------------------------------------------------------------
# Shared call helper
# ---------------------------------------------------------------------------

def _call(user_id: str, *, has_project: bool = True, storage: _FakeStorage | None = None):
    from fastapi.testclient import TestClient
    if storage is None:
        storage = _FakeStorage()

    fake_pool = _FakePool(has_project=has_project)
    role = _ROLES.get(user_id, "editor")

    app = _build_app()
    with (
        patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=fake_pool)),
        patch(
            "kerf_api.routes.get_user_workspace_role",
            new=AsyncMock(return_value=role),
        ),
        patch("kerf_api.routes.get_storage_required", return_value=storage),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            return (
                client.delete(f"/api/projects/{_PROJECT_ID}", headers=_headers(user_id)),
                fake_pool._conn,
                storage,
            )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDeleteProjectAuth:
    def test_404_when_project_missing(self):
        resp, _, _ = _call(_OWNER_ID, has_project=False)
        assert resp.status_code == 404, resp.text

    def test_403_for_editor(self):
        resp, _, _ = _call(_EDITOR_ID)
        assert resp.status_code == 403, resp.text

    def test_403_for_viewer(self):
        resp, _, _ = _call(_VIEWER_ID)
        assert resp.status_code == 403, resp.text


class TestDeleteProjectOwner:
    def setup_method(self):
        self.resp, self.conn, self.storage = _call(_OWNER_ID)

    def test_200(self):
        assert self.resp.status_code == 200, self.resp.text

    def test_response_shape(self):
        body = self.resp.json()
        assert body["deleted"] is True
        assert body["project_id"] == _PROJECT_ID
        assert isinstance(body["removed_blobs"], int)

    def test_project_row_deleted(self):
        deleted_queries = [q for q in self.conn.executes if "delete from projects" in q.lower()]
        assert len(deleted_queries) >= 1, f"Expected DELETE FROM projects, got: {self.conn.executes}"

    def test_file_storage_keys_deleted(self):
        assert _STORAGE_KEY_1 in self.storage.deleted, f"storage.deleted={self.storage.deleted}"
        assert _STORAGE_KEY_2 in self.storage.deleted

    def test_mesh_storage_key_deleted(self):
        assert _MESH_KEY_1 in self.storage.deleted

    def test_thumbnail_key_deleted(self):
        assert _THUMBNAIL_KEY in self.storage.deleted

    def test_cover_key_deleted(self):
        assert _COVER_KEY in self.storage.deleted

    def test_photo_key_deleted(self):
        assert _PHOTO_KEY in self.storage.deleted

    def test_tess_mesh_key_deleted(self):
        assert _TESS_MESH_KEY in self.storage.deleted

    def test_git_prefix_deleted(self):
        expected = f"workspaces/{_WORKSPACE_ID}/git/{_PROJECT_ID}/"
        assert expected in self.storage.prefixes, f"prefixes={self.storage.prefixes}"

    def test_photos_prefix_deleted(self):
        expected = f"photos/{_PROJECT_ID}/"
        assert expected in self.storage.prefixes, f"prefixes={self.storage.prefixes}"
