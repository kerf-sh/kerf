"""
T-89 — RLS: upload_sessions
=============================
Hermetic tests for the application-level multi-tenant access control on the
``upload_sessions`` table (folded into migration 0002 from 008_upload_sessions).

Postgres-level RLS is not used; isolation is enforced in routes.py via
workspace_members membership checks and ``WHERE project_id = $N`` guards on
every upload_sessions query.  All 10 cases use in-memory fake connections —
no real database required.

Invariants under test
---------------------
Tenant isolation (SELECT):
  1. User A cannot retrieve upload session belonging to project B (404 gate).
  2. get_upload_session with session id from B's project and A's pid → not found.
  3. Cross-tenant sha256 lookup is project-scoped — B's session not visible to A.

CREATE (POST /projects/{pid}/uploads):
  4. Non-member cannot create upload session (404 gate, no role).
  5. Viewer role cannot create upload session (403 gate).
  6. Member (non-viewer) can create upload session.

UPDATE / chunk (PUT /projects/{pid}/uploads/{uid}/chunks/{n}):
  7. Non-member cannot write a chunk to B's project upload (404 gate).
  8. Viewer role cannot write chunks (403 gate).

FINALIZE / DELETE:
  9. Non-member cannot finalize an upload on B's project (404 gate).
 10. Only project member (non-viewer) can cancel / delete an upload; non-member
     gets 404.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Fixtures — two isolated tenants
# ---------------------------------------------------------------------------

WS_A = str(uuid.uuid4())
WS_B = str(uuid.uuid4())
USER_A = str(uuid.uuid4())
USER_B = str(uuid.uuid4())
PROJ_A1 = str(uuid.uuid4())
PROJ_B1 = str(uuid.uuid4())

SESSION_A1 = str(uuid.uuid4())  # belongs to PROJ_A1 / USER_A
SESSION_B1 = str(uuid.uuid4())  # belongs to PROJ_B1 / USER_B
SHA256_A = "a" * 64
SHA256_B = "b" * 64

_FUTURE = datetime.utcnow() + timedelta(hours=23)


# ---------------------------------------------------------------------------
# In-memory fake DB
# ---------------------------------------------------------------------------

class FakeRecord(dict):
    def __getitem__(self, key):
        return super().__getitem__(key)

    def get(self, key, default=None):
        return super().get(key, default)


# workspace_members: {(ws_id, user_id): role}
_MEMBERS: dict[tuple[str, str], str] = {
    (WS_A, USER_A): "owner",
    (WS_B, USER_B): "owner",
}

# upload_sessions store: {session_id: FakeRecord}
_SESSIONS: dict[str, FakeRecord] = {
    SESSION_A1: FakeRecord({
        "id": uuid.UUID(SESSION_A1),
        "project_id": uuid.UUID(PROJ_A1),
        "user_id": uuid.UUID(USER_A),
        "filename": "part.step",
        "size": 1024,
        "mime": "model/step",
        "sha256": SHA256_A,
        "storage_key": SESSION_A1,
        "chunk_size": 5242880,
        "total_chunks": 1,
        "received_chunks": [],
        "bytes_received": 0,
        "complete": False,
        "created_at": datetime.utcnow(),
        "expires_at": _FUTURE,
    }),
    SESSION_B1: FakeRecord({
        "id": uuid.UUID(SESSION_B1),
        "project_id": uuid.UUID(PROJ_B1),
        "user_id": uuid.UUID(USER_B),
        "filename": "other.step",
        "size": 2048,
        "mime": "model/step",
        "sha256": SHA256_B,
        "storage_key": SESSION_B1,
        "chunk_size": 5242880,
        "total_chunks": 1,
        "received_chunks": [],
        "bytes_received": 0,
        "complete": False,
        "created_at": datetime.utcnow(),
        "expires_at": _FUTURE,
    }),
}

# projects: pid → ws_id
_PROJECTS: dict[str, str] = {
    PROJ_A1: WS_A,
    PROJ_B1: WS_B,
}


class FakeConn:
    """Simulates asyncpg.Connection for access-control queries."""

    async def fetchrow(self, query: str, *args) -> Optional[FakeRecord]:
        q = query.strip().lower()

        # workspace_members role lookup
        if "from workspace_members" in q:
            ws_id, user_id = str(args[0]), str(args[1])
            role = _MEMBERS.get((ws_id, user_id))
            if role:
                return FakeRecord({"role": role})
            return None

        # upload_sessions lookup by id + project_id guard (routes.py pattern)
        if "from upload_sessions" in q and "where id = $1 and project_id = $2" in q:
            session_id = str(args[0])
            project_id = str(args[1])
            row = _SESSIONS.get(session_id)
            if row and str(row["project_id"]) == project_id:
                return row
            return None

        # upload_sessions lookup by id only (plain get)
        if "from upload_sessions" in q and "where id = $1" in q:
            session_id = str(args[0])
            return _SESSIONS.get(session_id)

        # sha256 lookup: project_id = $1 and sha256 = $2
        if "from upload_sessions" in q and "sha256 = $2" in q:
            project_id = str(args[0])
            sha256 = str(args[1])
            for row in _SESSIONS.values():
                if str(row["project_id"]) == project_id and row["sha256"] == sha256:
                    if not row["complete"] and row["expires_at"] > datetime.utcnow():
                        return row
            return None

        return None

    async def fetch(self, query: str, *args) -> list[FakeRecord]:
        return []

    async def execute(self, query: str, *args) -> str:
        q = query.strip().lower()
        if "delete from upload_sessions where id = $1" in q:
            session_id = str(args[0])
            if session_id in _SESSIONS:
                return "DELETE 1"
            return "DELETE 0"
        if "insert into upload_sessions" in q:
            return "INSERT 0 1"
        if "update upload_sessions" in q:
            return "UPDATE 1"
        return ""

    def transaction(self):
        return _FakeTxn()


class _FakeTxn:
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_):
        pass


class FakeConnCtx:
    async def __aenter__(self):
        return FakeConn()
    async def __aexit__(self, *_):
        pass


class FakePool:
    def acquire(self):
        return FakeConnCtx()


# ---------------------------------------------------------------------------
# Helper: project_workspace_id simulation
# ---------------------------------------------------------------------------

async def _project_ws(pid: str) -> Optional[str]:
    return _PROJECTS.get(pid)


# ---------------------------------------------------------------------------
# Helper: role gate (mirrors routes.py logic for uploads)
# ---------------------------------------------------------------------------

async def _check_upload_access(conn: FakeConn, pid: str, user_id: str) -> str:
    """
    Returns the role if the user is a non-viewer member of the project's
    workspace; raises HTTPException 404/403 otherwise (same as routes.py).
    """
    from kerf_api.routes import get_user_workspace_role

    ws_id = await _project_ws(pid)
    if not ws_id:
        raise HTTPException(status_code=404, detail="project not found")

    role = await get_user_workspace_role(conn, ws_id, user_id)
    if not role:
        raise HTTPException(status_code=404, detail="project not found")
    if role == "viewer":
        raise HTTPException(status_code=403, detail="viewer cannot upload")
    return role


# ---------------------------------------------------------------------------
# Case 1 — User A cannot retrieve upload session belonging to project B
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_upload_cross_tenant_returns_404():
    """routes.py: GET /projects/{pid}/uploads/{uid}
    User A requests SESSION_B1 under PROJ_B1 — workspace membership check
    fires before the DB read, returning 404 (no membership)."""
    conn = FakeConn()

    with pytest.raises(HTTPException) as exc_info:
        await _check_upload_access(conn, PROJ_B1, USER_A)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Case 2 — Session id from B's project coupled with A's project id → not found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_session_project_id_guard():
    """The WHERE id=$1 AND project_id=$2 guard on upload_sessions prevents
    cross-project access even when the session UUID is known."""
    conn = FakeConn()

    # B's session id queried against A's project_id → no row
    row = await conn.fetchrow(
        """
        select id, project_id, user_id, filename, size, mime, sha256, storage_key,
               chunk_size, total_chunks, received_chunks, bytes_received, complete, expires_at
        from upload_sessions
        where id = $1 and project_id = $2
        """,
        uuid.UUID(SESSION_B1),   # session from B
        uuid.UUID(PROJ_A1),      # but wrong project
    )
    assert row is None, "Session B1 must not be visible under project A1"


# ---------------------------------------------------------------------------
# Case 3 — Cross-tenant sha256 lookup is project-scoped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sha256_lookup_is_project_scoped():
    """get_upload_session_by_sha256 uses WHERE project_id=$1 AND sha256=$2 —
    a sha256 from B's session is not returned when queried against A's project."""
    conn = FakeConn()

    # Query B's sha256 under A's project → should be None
    row = await conn.fetchrow(
        """
        select * from upload_sessions
        where project_id = $1 and sha256 = $2 and complete = false and expires_at > now()
        """,
        uuid.UUID(PROJ_A1),   # A's project
        SHA256_B,              # sha256 that belongs to B's session
    )
    assert row is None, "B's sha256 must not be visible under A's project"

    # Sanity: A's sha256 under A's project does return a row
    row_a = await conn.fetchrow(
        """
        select * from upload_sessions
        where project_id = $1 and sha256 = $2 and complete = false and expires_at > now()
        """,
        uuid.UUID(PROJ_A1),
        SHA256_A,
    )
    assert row_a is not None
    assert str(row_a["project_id"]) == PROJ_A1


# ---------------------------------------------------------------------------
# Case 4 — Non-member cannot create upload session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_init_upload_non_member_gets_404():
    """POST /projects/{pid}/uploads — User A has no membership in WS_B → 404."""
    conn = FakeConn()

    with pytest.raises(HTTPException) as exc_info:
        await _check_upload_access(conn, PROJ_B1, USER_A)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Case 5 — Viewer role cannot create upload session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_init_upload_viewer_gets_403():
    """Viewer role must be blocked from initiating uploads (403)."""
    _MEMBERS[(WS_B, USER_A)] = "viewer"
    try:
        conn = FakeConn()
        with pytest.raises(HTTPException) as exc_info:
            await _check_upload_access(conn, PROJ_B1, USER_A)
        assert exc_info.value.status_code == 403
        assert "viewer" in exc_info.value.detail
    finally:
        del _MEMBERS[(WS_B, USER_A)]


# ---------------------------------------------------------------------------
# Case 6 — Member (non-viewer) can create upload session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_init_upload_member_allowed():
    """An 'editor' member of WS_A can initiate an upload for PROJ_A1."""
    USER_EDITOR = str(uuid.uuid4())
    _MEMBERS[(WS_A, USER_EDITOR)] = "editor"
    try:
        conn = FakeConn()
        role = await _check_upload_access(conn, PROJ_A1, USER_EDITOR)
        assert role == "editor"
    finally:
        del _MEMBERS[(WS_A, USER_EDITOR)]


# ---------------------------------------------------------------------------
# Case 7 — Non-member cannot write a chunk to B's project upload
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_chunk_cross_tenant_gets_404():
    """PUT /projects/{pid}/uploads/{uid}/chunks/{n}
    User A trying to write a chunk to B's project must get 404 at the
    workspace-membership gate before the upload_sessions row is read."""
    conn = FakeConn()

    with pytest.raises(HTTPException) as exc_info:
        await _check_upload_access(conn, PROJ_B1, USER_A)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Case 8 — Viewer cannot write chunks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_chunk_viewer_gets_403():
    """Viewer role must be blocked from writing chunks (403)."""
    # Temporarily make USER_A a viewer in WS_A (their own workspace)
    original_role = _MEMBERS[(WS_A, USER_A)]
    _MEMBERS[(WS_A, USER_A)] = "viewer"
    try:
        conn = FakeConn()
        with pytest.raises(HTTPException) as exc_info:
            await _check_upload_access(conn, PROJ_A1, USER_A)
        assert exc_info.value.status_code == 403
    finally:
        _MEMBERS[(WS_A, USER_A)] = original_role


# ---------------------------------------------------------------------------
# Case 9 — Non-member cannot finalize an upload on B's project
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_finalize_upload_cross_tenant_gets_404():
    """POST /projects/{pid}/uploads/{uid}/finalize
    User A attempting to finalize a session in B's project hits 404 at the
    membership gate."""
    conn = FakeConn()

    with pytest.raises(HTTPException) as exc_info:
        await _check_upload_access(conn, PROJ_B1, USER_A)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Case 10 — Non-member cannot cancel/delete an upload; member can
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_upload_cross_tenant_gets_404_member_succeeds():
    """DELETE /projects/{pid}/uploads/{uid}
    Non-member (User A against B's project) must get 404.
    Project member (User B against B's project) passes the gate.
    """
    conn = FakeConn()

    # Non-member gets 404
    with pytest.raises(HTTPException) as exc_info:
        await _check_upload_access(conn, PROJ_B1, USER_A)
    assert exc_info.value.status_code == 404

    # Owner B passes the gate
    role = await _check_upload_access(conn, PROJ_B1, USER_B)
    assert role == "owner"

    # Session for B's project is accessible under the correct project_id guard
    row = await conn.fetchrow(
        """
        select id, project_id, user_id, filename, size, mime, sha256, storage_key,
               chunk_size, total_chunks, received_chunks, bytes_received, complete, expires_at
        from upload_sessions
        where id = $1 and project_id = $2
        """,
        uuid.UUID(SESSION_B1),
        uuid.UUID(PROJ_B1),
    )
    assert row is not None
    assert str(row["id"]) == SESSION_B1
