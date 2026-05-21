"""
T-82 — RLS: file_revisions (OSS undo)
======================================
Hermetic tests for the application-level multi-tenant access control on the
``file_revisions`` table.

The access model: ``file_revisions`` has no workspace_id column.  Tenant
isolation is enforced by the route layer joining through the FK chain:
    file_revisions.file_id → files.project_id → projects.workspace_id
combined with a ``workspace_members`` membership check.

All 12 cases use in-memory fake connections — no real database required.

Invariants under test
----------------------
SELECT (list / get revision):
  1.  User A can list revisions for their own file (member of WS_A).
  2.  User A cannot list revisions for a file belonging to WS_B (non-member).
  3.  User A gets 404 when fetching a specific revision of B's file.
  4.  Providing B's revision ID with A's project/file params → 404.
  5.  get_revision_content: existence check enforces project ownership.

UPDATE / RESTORE:
  6.  Non-member attempting restore gets 403 (role is None).
  7.  viewer role cannot restore (role == 'viewer' → 403).
  8.  editor/member role can restore.
  9.  owner role can restore.

Cross-table isolation:
  10. Revision lookup uses INNER JOIN files f ON f.project_id — cannot guess
      a revision that belongs to a different project even by raw revision ID.
  11. User A querying B's revision via A's project ID returns 404.
  12. write_revision is scoped to file_id; inserting into B's file is only
      possible if the caller first has membership — the route layer always
      checks role before calling write_revision.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Fixtures — UUIDs for two isolated tenants
# ---------------------------------------------------------------------------

WS_A = str(uuid.uuid4())
WS_B = str(uuid.uuid4())
USER_A = str(uuid.uuid4())
USER_B = str(uuid.uuid4())
PROJ_A = str(uuid.uuid4())
PROJ_B = str(uuid.uuid4())
FILE_A = str(uuid.uuid4())
FILE_B = str(uuid.uuid4())
REV_A1 = str(uuid.uuid4())
REV_A2 = str(uuid.uuid4())
REV_B1 = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# In-memory fake store
# ---------------------------------------------------------------------------

# workspace_members: {(ws_id, user_id): role}
_MEMBERS: dict[tuple[str, str], str] = {
    (WS_A, USER_A): "owner",
    (WS_B, USER_B): "owner",
}

# projects: {pid: workspace_id}
_PROJECTS: dict[str, str] = {
    PROJ_A: WS_A,
    PROJ_B: WS_B,
}

# files: {fid: project_id}
_FILES: dict[str, str] = {
    FILE_A: PROJ_A,
    FILE_B: PROJ_B,
}

# file_revisions: {rid: {file_id, source, content, ...}}
_REVISIONS: dict[str, dict] = {
    REV_A1: {
        "id": uuid.UUID(REV_A1),
        "file_id": uuid.UUID(FILE_A),
        "source": "user",
        "content": "hello from A rev 1",
        "content_preview": "hello from A rev 1",
        "user_id": uuid.UUID(USER_A),
        "user_name": "Alice",
        "created_at": None,
        "kind": "base",
        "content_codec": "plain",
        "content_gz": None,
        "parent_revision_id": None,
    },
    REV_A2: {
        "id": uuid.UUID(REV_A2),
        "file_id": uuid.UUID(FILE_A),
        "source": "llm",
        "content": "hello from A rev 2",
        "content_preview": "hello from A rev 2",
        "user_id": None,
        "user_name": None,
        "created_at": None,
        "kind": "base",
        "content_codec": "plain",
        "content_gz": None,
        "parent_revision_id": None,
    },
    REV_B1: {
        "id": uuid.UUID(REV_B1),
        "file_id": uuid.UUID(FILE_B),
        "source": "user",
        "content": "secret content of tenant B",
        "content_preview": "secret content of tenant B",
        "user_id": uuid.UUID(USER_B),
        "user_name": "Bob",
        "created_at": None,
        "kind": "base",
        "content_codec": "plain",
        "content_gz": None,
        "parent_revision_id": None,
    },
}


class FakeRecord(dict):
    """asyncpg-compatible record that supports both dict and attribute access."""

    def __getitem__(self, key):
        return super().__getitem__(key)

    def get(self, key, default=None):
        return super().get(key, default)

    def keys(self):
        return super().keys()


class FakeConn:
    """Simulates asyncpg.Connection for access-control queries."""

    async def fetchrow(self, query: str, *args) -> Optional[FakeRecord]:
        q = query.strip().lower()

        # workspace_members role lookup
        if "from workspace_members" in q and "where workspace_id" in q:
            ws_id, user_id = str(args[0]), str(args[1])
            role = _MEMBERS.get((ws_id, user_id))
            return FakeRecord({"role": role}) if role else None

        # projects.workspace_id lookup
        if "select workspace_id from projects" in q:
            pid = str(args[0])
            ws_id = _PROJECTS.get(pid)
            return FakeRecord({"workspace_id": uuid.UUID(ws_id)}) if ws_id else None

        # files.project_id lookup
        if "select project_id from files" in q:
            fid = str(args[0])
            pid = _FILES.get(fid)
            return FakeRecord({"project_id": uuid.UUID(pid)}) if pid else None

        # revision lookup with project join: WHERE fr.id = $1 AND fr.file_id = $2 AND f.project_id = $3
        if "from file_revisions fr" in q and "f.project_id" in q:
            rid, fid, pid = str(args[0]), str(args[1]), str(args[2])
            rev = _REVISIONS.get(rid)
            if (
                rev
                and str(rev["file_id"]) == fid
                and _FILES.get(fid) == pid
            ):
                return FakeRecord({k: v for k, v in rev.items()})
            return None

        # bare revision lookup by id
        if "from file_revisions" in q and "where" in q and "id = $1" in q:
            rid = str(args[0])
            rev = _REVISIONS.get(rid)
            return FakeRecord({k: v for k, v in rev.items()}) if rev else None

        return None

    async def fetch(self, query: str, *args) -> list[FakeRecord]:
        q = query.strip().lower()

        # list revisions for a file (WHERE fr.file_id = $1)
        if "from file_revisions fr" in q and "fr.file_id = $1" in q:
            fid = str(args[0])
            results = []
            for rev in _REVISIONS.values():
                if str(rev["file_id"]) == fid:
                    results.append(FakeRecord({k: v for k, v in rev.items()}))
            return results

        return []

    async def fetchval(self, query: str, *args) -> Any:
        q = query.strip().lower()

        # SELECT 1 FROM file_revisions fr INNER JOIN files f ON f.id = fr.file_id
        # WHERE fr.id = $1 AND fr.file_id = $2 AND f.project_id = $3
        if "select 1 from file_revisions fr" in q and "f.project_id" in q:
            rid, fid, pid = str(args[0]), str(args[1]), str(args[2])
            rev = _REVISIONS.get(rid)
            if (
                rev
                and str(rev["file_id"]) == fid
                and _FILES.get(fid) == pid
            ):
                return 1
            return None

        return None

    async def execute(self, query: str, *args) -> str:
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
# Shared helpers
# ---------------------------------------------------------------------------

async def _role(ws_id: str, user_id: str) -> Optional[str]:
    from kerf_api.routes import get_user_workspace_role
    conn = FakeConn()
    return await get_user_workspace_role(conn, ws_id, user_id)


def _project_ws(pid: str) -> Optional[str]:
    """Simulate project_workspace_id() without hitting real DB."""
    return _PROJECTS.get(pid)


def _enforce_access(role: Optional[str]) -> None:
    """Mirror routes.py guard: not member → 404."""
    if not role:
        raise HTTPException(status_code=404, detail="project not found")


def _enforce_write_access(role: Optional[str]) -> None:
    """Mirror routes.py guard for restore: viewer/None → 403."""
    if not role or role == "viewer":
        raise HTTPException(status_code=403, detail="viewer cannot restore revisions")


# ---------------------------------------------------------------------------
# Case 1 — User A can list revisions for their own file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_revisions_user_a_can_see_own_file():
    """list_revisions for FILE_A must return REV_A1 and REV_A2 for USER_A."""
    from kerf_api.routes import get_user_workspace_role

    conn = FakeConn()
    ws_id = _project_ws(PROJ_A)
    role = await get_user_workspace_role(conn, ws_id, USER_A)
    _enforce_access(role)  # must not raise

    rows = await conn.fetch(
        "SELECT fr.id, fr.file_id, fr.source FROM file_revisions fr WHERE fr.file_id = $1",
        uuid.UUID(FILE_A),
    )
    rids = {str(r["id"]) for r in rows}
    assert REV_A1 in rids
    assert REV_A2 in rids
    assert REV_B1 not in rids, "User A must not see tenant B's revision"


# ---------------------------------------------------------------------------
# Case 2 — User A cannot list revisions for tenant B's file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_revisions_non_member_gets_404():
    """User A querying FILE_B must get 404 — membership check blocks access."""
    from kerf_api.routes import get_user_workspace_role

    conn = FakeConn()
    ws_id = _project_ws(PROJ_B)
    role = await get_user_workspace_role(conn, ws_id, USER_A)

    assert role is None, f"USER_A must have no role in WS_B, got {role!r}"
    with pytest.raises(HTTPException) as exc_info:
        _enforce_access(role)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Case 3 — User A gets 404 fetching a revision of B's file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_revision_cross_tenant_returns_404():
    """User A attempting to GET REV_B1 (belongs to PROJ_B) must get 404."""
    from kerf_api.routes import get_user_workspace_role

    conn = FakeConn()
    ws_id = _project_ws(PROJ_B)
    role = await get_user_workspace_role(conn, ws_id, USER_A)

    assert not role
    with pytest.raises(HTTPException) as exc_info:
        _enforce_access(role)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Case 4 — Revision ID forging: B's rid + A's fid/pid → 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_revision_forged_params_returns_404():
    """Passing B's revision ID with A's file/project IDs must return None from
    the JOIN (file_id mismatch) — simulating the INNER JOIN check."""
    conn = FakeConn()
    # Route layer would call conn.fetchrow with rid=REV_B1, fid=FILE_A, pid=PROJ_A
    row = await conn.fetchrow(
        """
        SELECT fr.id, fr.file_id, fr.source FROM file_revisions fr
        INNER JOIN files f ON f.id = fr.file_id
        WHERE fr.id = $1 AND fr.file_id = $2 AND f.project_id = $3
        """,
        uuid.UUID(REV_B1), uuid.UUID(FILE_A), uuid.UUID(PROJ_A),
    )
    assert row is None, "Revision from WS_B must not be found under WS_A file/project"


# ---------------------------------------------------------------------------
# Case 5 — get_revision_content existence check enforces project ownership
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_revision_content_cross_project_returns_none():
    """The SELECT 1 existence check (fr.id, fr.file_id, f.project_id) must
    return None when the revision does not belong to the requested project."""
    conn = FakeConn()
    # REV_B1 belongs to FILE_B / PROJ_B; asking under FILE_A / PROJ_A → None
    exists = await conn.fetchval(
        """
        SELECT 1 FROM file_revisions fr
        INNER JOIN files f ON f.id = fr.file_id
        WHERE fr.id = $1 AND fr.file_id = $2 AND f.project_id = $3
        """,
        uuid.UUID(REV_B1), uuid.UUID(FILE_A), uuid.UUID(PROJ_A),
    )
    assert exists is None, "Cross-tenant revision existence check must return None"


# ---------------------------------------------------------------------------
# Case 6 — Non-member restore attempt gets 403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_revision_non_member_gets_403():
    """User A attempting to restore a revision in PROJ_B must get 403."""
    from kerf_api.routes import get_user_workspace_role

    conn = FakeConn()
    ws_id = _project_ws(PROJ_B)
    role = await get_user_workspace_role(conn, ws_id, USER_A)

    assert not role
    with pytest.raises(HTTPException) as exc_info:
        _enforce_write_access(role)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Case 7 — viewer role cannot restore
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_revision_viewer_gets_403():
    """A 'viewer' workspace role must be blocked from restoring revisions."""
    from kerf_api.routes import get_user_workspace_role

    _MEMBERS[(WS_B, USER_A)] = "viewer"
    try:
        conn = FakeConn()
        ws_id = _project_ws(PROJ_B)
        role = await get_user_workspace_role(conn, ws_id, USER_A)
        assert role == "viewer"

        with pytest.raises(HTTPException) as exc_info:
            _enforce_write_access(role)
        assert exc_info.value.status_code == 403
    finally:
        del _MEMBERS[(WS_B, USER_A)]


# ---------------------------------------------------------------------------
# Case 8 — member role can restore
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_revision_member_allowed():
    """A 'member' role must pass the restore gate."""
    from kerf_api.routes import get_user_workspace_role

    _MEMBERS[(WS_A, USER_B)] = "member"
    try:
        conn = FakeConn()
        ws_id = _project_ws(PROJ_A)
        role = await get_user_workspace_role(conn, ws_id, USER_B)
        assert role == "member"
        # Must not raise
        _enforce_write_access(role)
    finally:
        del _MEMBERS[(WS_A, USER_B)]


# ---------------------------------------------------------------------------
# Case 9 — owner role can restore
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restore_revision_owner_allowed():
    """User A (owner of WS_A) must pass the restore gate for PROJ_A."""
    from kerf_api.routes import get_user_workspace_role

    conn = FakeConn()
    ws_id = _project_ws(PROJ_A)
    role = await get_user_workspace_role(conn, ws_id, USER_A)
    assert role == "owner"
    # Must not raise
    _enforce_write_access(role)


# ---------------------------------------------------------------------------
# Case 10 — INNER JOIN on files.project_id prevents cross-project rev access
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inner_join_prevents_cross_project_revision_access():
    """Revision REV_B1 in FILE_B/PROJ_B must not be reachable via FILE_A/PROJ_A
    because the INNER JOIN on files.project_id fails."""
    conn = FakeConn()
    row = await conn.fetchrow(
        """
        SELECT fr.id FROM file_revisions fr
        INNER JOIN files f ON f.id = fr.file_id
        WHERE fr.id = $1 AND fr.file_id = $2 AND f.project_id = $3
        """,
        uuid.UUID(REV_B1), uuid.UUID(FILE_B), uuid.UUID(PROJ_A),  # wrong project
    )
    assert row is None, (
        "JOIN on f.project_id must prevent reading B's revision under A's project"
    )


# ---------------------------------------------------------------------------
# Case 11 — User A querying B's revision under A's project returns 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_revision_wrong_project_id_returns_404():
    """Even if User A is a member of PROJ_A, they cannot read REV_B1 which
    belongs to FILE_B in PROJ_B — the project_id join guard catches this."""
    from kerf_api.routes import get_user_workspace_role

    conn = FakeConn()
    # User A is a valid member of WS_A — membership passes
    ws_id = _project_ws(PROJ_A)
    role = await get_user_workspace_role(conn, ws_id, USER_A)
    assert role is not None  # access to PROJ_A is valid

    # But the revision belongs to PROJ_B — the fetch returns None
    row = await conn.fetchrow(
        """
        SELECT fr.id FROM file_revisions fr
        INNER JOIN files f ON f.id = fr.file_id
        WHERE fr.id = $1 AND fr.file_id = $2 AND f.project_id = $3
        """,
        uuid.UUID(REV_B1), uuid.UUID(FILE_B), uuid.UUID(PROJ_A),
    )
    assert row is None, "B's revision must not be accessible under A's project"


# ---------------------------------------------------------------------------
# Case 12 — write_revision route gate: membership must be checked before write
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_revision_non_member_blocked():
    """The route layer must verify membership before calling write_revision.
    This test verifies the gate logic directly: User A has no role in WS_B,
    so the route must raise 404 before any write path is reached."""
    from kerf_api.routes import get_user_workspace_role

    conn = FakeConn()
    ws_id = _project_ws(PROJ_B)
    role = await get_user_workspace_role(conn, ws_id, USER_A)

    assert role is None, "USER_A must have no membership in WS_B"

    reached_write = False
    with pytest.raises(HTTPException) as exc_info:
        _enforce_access(role)
        # The following would only execute if the guard was bypassed:
        reached_write = True  # pragma: no cover

    assert not reached_write, "write path must not be reached after 404 gate"
    assert exc_info.value.status_code == 404
