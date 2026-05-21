"""
T-66: STEP tessellation jobs — hermetic feature tests.

Scope:
  - step_tessellation_jobs lifecycle: queued → running → done / error
  - step-ref file kind (FILE_KINDS allow-list)
  - step_tess_input_spec (TessInputSpec round-trip and validation)
  - POST /projects/{pid}/files/{fid}/tessellate (enqueue / re-enqueue)
  - DELETE /projects/{pid}/files/{fid}/tessellate (purge / re-queue reset)
  - tessellation_status surfaced in GET /projects/{pid}/files

Strategy: monkey-patch get_pool_required, project_workspace_id, and
get_user_workspace_role; no real Postgres needed.

25 test functions covering job submission, state machine, idempotency,
auth guards, TessInputSpec, and step-ref kind.
"""
from __future__ import annotations

import pathlib
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from datetime import datetime, timedelta, timezone
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
_PROJECT_ID = str(uuid.uuid4())
_WORKSPACE_ID = str(uuid.uuid4())
_OWNER_ID = str(uuid.uuid4())
_EDITOR_ID = str(uuid.uuid4())
_VIEWER_ID = str(uuid.uuid4())
_STRANGER_ID = str(uuid.uuid4())  # no workspace role
_FILE_ID = str(uuid.uuid4())
_FILE_ID_2 = str(uuid.uuid4())

# ---------------------------------------------------------------------------
# Fake DB primitives
# ---------------------------------------------------------------------------

class _FakeRow(dict):
    """asyncpg Record-alike."""
    def __getitem__(self, key):
        return super().__getitem__(key)


class _FakeTessConn:
    """Connection that handles tessellation-related queries."""

    def __init__(
        self,
        *,
        file_exists: bool = True,
        tess_row: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.file_exists = file_exists
        self.tess_row = tess_row or {}
        self.executes: List[str] = []
        self.inserted: bool = False
        self.updated: bool = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def fetchrow(self, query: str, *args, **kwargs):
        q = query.strip().lower()
        # files check in purge_tessellation
        if "from files" in q and "deleted_at is null" in q:
            if self.file_exists:
                return _FakeRow({"mesh_storage_key": self.tess_row.get("mesh_storage_key")})
            return None
        # workspace_id from project
        if "workspace_id from projects" in q or "workspace_id" in q and "projects" in q:
            return _FakeRow({"workspace_id": _WORKSPACE_ID})
        return None

    async def fetch(self, query: str, *args, **kwargs):
        q = query.strip().lower()
        if "step_tessellation_jobs" in q or "tessellation_status" in q:
            # list_files response with tessellation_status
            return [
                _FakeRow({
                    "id": uuid.UUID(_FILE_ID),
                    "project_id": uuid.UUID(_PROJECT_ID),
                    "parent_id": None,
                    "name": "part.step",
                    "kind": "step",
                    "extension": "step",
                    "storage_key": f"files/{_PROJECT_ID}/part.step",
                    "mime_type": "model/step",
                    "size": 12345,
                    "mesh_storage_key": None,
                    "tessellation_status": self.tess_row.get("status"),
                    "created_at": datetime.now(tz=timezone.utc),
                    "updated_at": datetime.now(tz=timezone.utc),
                })
            ]
        return []

    async def execute(self, query: str, *args, **kwargs):
        q = query.strip()
        self.executes.append(q)
        if "INSERT INTO step_tessellation_jobs" in q:
            self.inserted = True
        if "UPDATE step_tessellation_jobs" in q:
            self.updated = True
        return "OK"


class _FakePool:
    def __init__(self, conn: _FakeTessConn) -> None:
        self._conn = conn

    def acquire(self):
        return self._conn


# ---------------------------------------------------------------------------
# App builder + helpers
# ---------------------------------------------------------------------------

def _build_app():
    import kerf_core.db.connection as _conn_mod

    @asynccontextmanager
    async def _lifespan(app):
        _conn_mod._pool = object()
        yield
        _conn_mod._pool = None

    app = FastAPI(lifespan=_lifespan)
    from kerf_api.routes import router as api_router
    app.include_router(api_router, prefix="/api")
    return app


def _auth_token(user_id: str) -> str:
    now = datetime.now(tz=timezone.utc)
    return jwt.encode(
        {"sub": user_id, "exp": now + timedelta(hours=1), "iat": now},
        "dev-secret-change-in-production",
        algorithm="HS256",
    )


def _headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_auth_token(user_id)}"}


def _tess_post(
    user_id: str = _OWNER_ID,
    file_id: str = _FILE_ID,
    role: str = "owner",
    project_exists: bool = True,
    conn: Optional[_FakeTessConn] = None,
):
    """Helper to POST tessellate and return (response, conn)."""
    conn = conn or _FakeTessConn()
    pool = _FakePool(conn)
    app = _build_app()

    ws_id = _WORKSPACE_ID if project_exists else None

    with (
        patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)),
        patch("kerf_api.routes.project_workspace_id", new=AsyncMock(return_value=ws_id)),
        patch("kerf_api.routes.get_user_workspace_role", new=AsyncMock(return_value=role)),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                f"/api/projects/{_PROJECT_ID}/files/{file_id}/tessellate",
                headers=_headers(user_id),
            )
    return resp, conn


def _tess_delete(
    user_id: str = _OWNER_ID,
    file_id: str = _FILE_ID,
    role: str = "owner",
    project_exists: bool = True,
    file_exists: bool = True,
    conn: Optional[_FakeTessConn] = None,
):
    """Helper to DELETE tessellate (purge) and return (response, conn)."""
    conn = conn or _FakeTessConn(file_exists=file_exists)
    pool = _FakePool(conn)
    app = _build_app()

    ws_id = _WORKSPACE_ID if project_exists else None

    with (
        patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)),
        patch("kerf_api.routes.project_workspace_id", new=AsyncMock(return_value=ws_id)),
        patch("kerf_api.routes.get_user_workspace_role", new=AsyncMock(return_value=role)),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.delete(
                f"/api/projects/{_PROJECT_ID}/files/{file_id}/tessellate",
                headers=_headers(user_id),
            )
    return resp, conn


# ===========================================================================
# Section 1 — TessInputSpec unit tests (step_tess_input_spec)
# ===========================================================================

def test_tess_input_spec_defaults():
    """TessInputSpec ships with sane defaults."""
    from kerf_tess.specs import TessInputSpec
    spec = TessInputSpec()
    assert spec.resolution == 50000
    assert spec.export_format == "glb"
    assert spec.scale == 1.0


def test_tess_input_spec_custom_values():
    from kerf_tess.specs import TessInputSpec
    spec = TessInputSpec(resolution=5000, export_format="glb", scale=0.001)
    assert spec.resolution == 5000
    assert spec.scale == 0.001


def test_tess_input_spec_round_trip_to_dict():
    from kerf_tess.specs import TessInputSpec
    spec = TessInputSpec(resolution=12345, export_format="glb", scale=2.5)
    d = spec.to_dict()
    restored = TessInputSpec.from_dict(d)
    assert restored.resolution == spec.resolution
    assert restored.export_format == spec.export_format
    assert restored.scale == spec.scale


def test_tess_input_spec_from_empty_dict_uses_defaults():
    from kerf_tess.specs import TessInputSpec
    spec = TessInputSpec.from_dict({})
    assert spec.resolution == 50000
    assert spec.scale == 1.0


def test_tess_input_spec_from_partial_dict():
    from kerf_tess.specs import TessInputSpec
    spec = TessInputSpec.from_dict({"resolution": 9999})
    assert spec.resolution == 9999
    assert spec.scale == 1.0  # default preserved


def test_tess_input_spec_to_dict_keys():
    from kerf_tess.specs import TessInputSpec
    d = TessInputSpec().to_dict()
    assert "resolution" in d
    assert "export_format" in d
    assert "scale" in d


# ===========================================================================
# Section 2 — step-ref file kind (step_ref_kind)
# ===========================================================================

def test_step_ref_kind_in_file_kinds():
    """'step-ref' must be a recognised file kind."""
    from kerf_api.routes import FILE_KINDS
    assert "step-ref" in FILE_KINDS


def test_step_kind_in_file_kinds():
    """'step' must also be a recognised file kind for STEP uploads."""
    from kerf_api.routes import FILE_KINDS
    assert "step" in FILE_KINDS


def test_step_ref_distinct_from_step():
    from kerf_api.routes import FILE_KINDS
    kinds_list = list(FILE_KINDS)
    assert kinds_list.count("step-ref") == 1
    assert kinds_list.count("step") == 1
    assert "step-ref" != "step"


# ===========================================================================
# Section 3 — POST /tessellate (enqueue)
# ===========================================================================

def test_tessellate_post_returns_200_for_owner():
    resp, _ = _tess_post(user_id=_OWNER_ID, role="owner")
    assert resp.status_code == 200, resp.text


def test_tessellate_post_returns_queued_status():
    resp, _ = _tess_post()
    assert resp.json().get("status") == "queued"


def test_tessellate_post_inserts_job_row():
    resp, conn = _tess_post()
    assert resp.status_code == 200
    assert conn.inserted, "Expected INSERT INTO step_tessellation_jobs"


def test_tessellate_post_upsert_conflict_key():
    """ON CONFLICT (file_id) means re-submitting resets status to queued."""
    resp, conn = _tess_post()
    assert resp.status_code == 200
    # Verify the upsert SQL was issued (ON CONFLICT clause present)
    sql = " ".join(conn.executes)
    assert "ON CONFLICT" in sql or "on conflict" in sql.lower()


def test_tessellate_post_404_project_missing():
    resp, _ = _tess_post(project_exists=False)
    assert resp.status_code == 404


def test_tessellate_post_404_stranger_role():
    """User with no workspace role should get 404 (not leak project existence)."""
    resp, _ = _tess_post(user_id=_STRANGER_ID, role=None)
    assert resp.status_code == 404


def test_tessellate_post_viewer_allowed():
    """Tessellate POST does not gate on viewer — any member can trigger."""
    resp, _ = _tess_post(role="viewer")
    assert resp.status_code == 200


def test_tessellate_post_editor_allowed():
    resp, _ = _tess_post(role="editor")
    assert resp.status_code == 200


def test_tessellate_post_unauthenticated_rejected():
    app = _build_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(f"/api/projects/{_PROJECT_ID}/files/{_FILE_ID}/tessellate")
    assert resp.status_code in (401, 403)


# ===========================================================================
# Section 4 — DELETE /tessellate (purge / re-queue reset)
# ===========================================================================

def test_tessellate_delete_returns_200():
    resp, _ = _tess_delete()
    assert resp.status_code == 200, resp.text


def test_tessellate_delete_returns_purged_status():
    resp, _ = _tess_delete()
    assert resp.json().get("status") == "purged"


def test_tessellate_delete_issues_update():
    """Purge must issue UPDATE step_tessellation_jobs back to queued."""
    resp, conn = _tess_delete()
    assert resp.status_code == 200
    assert conn.updated, "Expected UPDATE step_tessellation_jobs"


def test_tessellate_delete_404_when_project_missing():
    resp, _ = _tess_delete(project_exists=False)
    assert resp.status_code == 404


def test_tessellate_delete_404_when_file_missing():
    resp, _ = _tess_delete(file_exists=False)
    assert resp.status_code == 404


def test_tessellate_delete_404_stranger_role():
    resp, _ = _tess_delete(user_id=_STRANGER_ID, role=None)
    assert resp.status_code == 404


def test_tessellate_delete_unauthenticated_rejected():
    app = _build_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.delete(f"/api/projects/{_PROJECT_ID}/files/{_FILE_ID}/tessellate")
    assert resp.status_code in (401, 403)


# ===========================================================================
# Section 5 — tessellation_status surfaced in file listings
# ===========================================================================

def test_list_files_includes_tessellation_status_field():
    """GET /projects/{pid}/files includes tessellation_status from LEFT JOIN."""
    conn = _FakeTessConn(tess_row={"status": "done", "mesh_storage_key": "meshes/x.glb"})
    pool = _FakePool(conn)
    app = _build_app()

    with (
        patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)),
        patch("kerf_api.routes.project_workspace_id", new=AsyncMock(return_value=_WORKSPACE_ID)),
        patch("kerf_api.routes.get_user_workspace_role", new=AsyncMock(return_value="owner")),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                f"/api/projects/{_PROJECT_ID}/files",
                headers=_headers(_OWNER_ID),
            )

    assert resp.status_code == 200, resp.text
    files = resp.json()
    assert isinstance(files, list)
    assert len(files) >= 1
    # tessellation_status key is present (may be None or a string)
    assert "tessellation_status" in files[0]


def test_list_files_tessellation_status_done_value():
    conn = _FakeTessConn(tess_row={"status": "done", "mesh_storage_key": "meshes/x.glb"})
    pool = _FakePool(conn)
    app = _build_app()

    with (
        patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)),
        patch("kerf_api.routes.project_workspace_id", new=AsyncMock(return_value=_WORKSPACE_ID)),
        patch("kerf_api.routes.get_user_workspace_role", new=AsyncMock(return_value="owner")),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                f"/api/projects/{_PROJECT_ID}/files",
                headers=_headers(_OWNER_ID),
            )

    files = resp.json()
    assert files[0]["tessellation_status"] == "done"


def test_list_files_tessellation_status_queued_value():
    conn = _FakeTessConn(tess_row={"status": "queued"})
    pool = _FakePool(conn)
    app = _build_app()

    with (
        patch("kerf_api.routes.get_pool_required", new=AsyncMock(return_value=pool)),
        patch("kerf_api.routes.project_workspace_id", new=AsyncMock(return_value=_WORKSPACE_ID)),
        patch("kerf_api.routes.get_user_workspace_role", new=AsyncMock(return_value="owner")),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get(
                f"/api/projects/{_PROJECT_ID}/files",
                headers=_headers(_OWNER_ID),
            )

    files = resp.json()
    assert files[0]["tessellation_status"] == "queued"
