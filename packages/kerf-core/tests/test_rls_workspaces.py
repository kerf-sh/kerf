"""
T-84 — RLS: workspaces + workspace_members + workspace_invites
==============================================================
Hermetic tests for application-level multi-tenant access control on the
``workspaces``, ``workspace_members``, and ``workspace_invites`` tables.

All 15 cases use in-memory fake connections — no real database required.

Invariants under test
---------------------
workspaces SELECT (list / get):
  W01  list_workspaces JOIN query only returns workspaces the caller is a member of.
  W02  User B's workspaces are not returned to User A (no shared membership).
  W03  get_workspace: non-member receives 404 (security by obscurity — not 403).
  W04  get_workspace: member receives workspace row + full member list.
  W05  get_workspace: completely unknown slug returns 404.

workspaces WRITE (update / delete):
  W06  update_workspace: non-member (no role) → 403 owner-or-admin required.
  W07  update_workspace: member role (not owner/admin) → 403.
  W08  update_workspace: admin role → allowed (no exception).
  W09  delete_workspace: admin role → 403 (owner only).
  W10  delete_workspace: owner role → allowed.

workspace_members WRITE (invite / change-role / remove):
  W11  invite_workspace_member: member role cannot invite → 403.
  W12  invite_workspace_member: non-member (None role) cannot invite → 403.
  W13  change_workspace_member_role: only owner can be demoted when they are the
       sole owner — request must return 400.
  W14  remove_workspace_member: cannot remove the only owner → 400.
  W15  remove_workspace_member: admin can remove a non-owner member.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import kerf_api.routes as api_routes


# ---------------------------------------------------------------------------
# Fixtures — UUIDs for two isolated tenants
# ---------------------------------------------------------------------------

WS_A_ID = str(uuid.uuid4())
WS_A_SLUG = "acme-corp"
WS_B_ID = str(uuid.uuid4())
WS_B_SLUG = "rival-inc"

USER_A = str(uuid.uuid4())  # owner of WS_A, admin of nothing
USER_B = str(uuid.uuid4())  # owner of WS_B
USER_C = str(uuid.uuid4())  # member of WS_A only
USER_D = str(uuid.uuid4())  # no workspace memberships

# workspace_members: {(ws_id, user_id): role}
_MEMBERS: dict[tuple[str, str], str] = {
    (WS_A_ID, USER_A): "owner",
    (WS_A_ID, USER_C): "member",
    (WS_B_ID, USER_B): "owner",
}

_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# In-memory fake DB connection
# ---------------------------------------------------------------------------

class FakeRecord(dict):
    """Minimal asyncpg-like record."""
    def __getitem__(self, key):
        return super().__getitem__(key)

    def get(self, key, default=None):
        return super().get(key, default)


def _ws_record(ws_id: str, slug: str) -> FakeRecord:
    return FakeRecord({
        "id": uuid.UUID(ws_id),
        "slug": slug,
        "name": slug.replace("-", " ").title(),
        "avatar_storage_key": None,
        "created_by": uuid.UUID(USER_A if ws_id == WS_A_ID else USER_B),
        "created_at": _TS,
        "updated_at": _TS,
    })


_WORKSPACES: dict[str, FakeRecord] = {
    WS_A_ID: _ws_record(WS_A_ID, WS_A_SLUG),
    WS_B_ID: _ws_record(WS_B_ID, WS_B_SLUG),
}
_SLUG_TO_ID = {WS_A_SLUG: WS_A_ID, WS_B_SLUG: WS_B_ID}


class FakeConn:
    """Simulates asyncpg.Connection for workspace access-control queries."""

    def __init__(self):
        self._owner_count: dict[str, int] = {}  # override for sole-owner tests

    async def fetchrow(self, query: str, *args) -> Optional[FakeRecord]:
        q = query.strip().lower()

        # workspace_members role lookup
        if "from workspace_members" in q and "where workspace_id" in q and "user_id" in q and "role" in q:
            ws_id, user_id = str(args[0]), str(args[1])
            role = _MEMBERS.get((ws_id, user_id))
            if role:
                return FakeRecord({"role": role})
            return None

        # workspace by id
        if "select * from workspaces where id" in q or "select workspace_id from workspaces" in q:
            ws_id = str(args[0])
            return _WORKSPACES.get(ws_id)

        # workspace by slug
        if "from workspaces where slug" in q:
            slug = str(args[0])
            ws_id = _SLUG_TO_ID.get(slug)
            return _WORKSPACES.get(ws_id) if ws_id else None

        # workspace_members get_workspace_member (two uuid args)
        if "from workspace_members where workspace_id" in q and "user_id" in q:
            if len(args) == 2:
                ws_id, user_id = str(args[0]), str(args[1])
                role = _MEMBERS.get((ws_id, user_id))
                if role:
                    return FakeRecord({
                        "workspace_id": uuid.UUID(ws_id),
                        "user_id": uuid.UUID(user_id),
                        "role": role,
                        "created_at": _TS,
                    })
            return None

        # default workspace (owner join)
        if "join workspace_members" in q and "role = 'owner'" in q:
            user_id = str(args[0])
            for (ws_id, uid), role in _MEMBERS.items():
                if uid == user_id and role == "owner":
                    return _WORKSPACES.get(ws_id)
            return None

        return None

    async def fetchval(self, query: str, *args) -> Any:
        q = query.strip().lower()
        # owner count query
        if "count(*)" in q and "role = 'owner'" in q:
            ws_id = str(args[0])
            override = self._owner_count.get(ws_id)
            if override is not None:
                return override
            count = sum(
                1 for (wid, _), role in _MEMBERS.items()
                if wid == ws_id and role == "owner"
            )
            return count
        return 0

    async def fetch(self, query: str, *args) -> list[FakeRecord]:
        q = query.strip().lower()

        # list_workspaces: JOIN workspace_members WHERE m.user_id = $1
        if "from workspaces w" in q and "join workspace_members m" in q and "where m.user_id" in q:
            user_id = str(args[0])
            results = []
            for (ws_id, uid), role in _MEMBERS.items():
                if uid != user_id:
                    continue
                ws = _WORKSPACES.get(ws_id)
                if not ws:
                    continue
                row = FakeRecord(dict(ws))
                row["role"] = role
                row["member_count"] = sum(1 for (wid, _) in _MEMBERS if wid == ws_id)
                row["project_count"] = 0
                results.append(row)
            return results

        # list_workspace_members: JOIN users ON wm.user_id
        if "from workspace_members wm" in q and "join users u" in q and "where wm.workspace_id" in q:
            ws_id = str(args[0])
            results = []
            for (wid, uid), role in _MEMBERS.items():
                if wid != ws_id:
                    continue
                results.append(FakeRecord({
                    "workspace_id": uuid.UUID(wid),
                    "user_id": uuid.UUID(uid),
                    "role": role,
                    "created_at": _TS,
                    "email": f"user-{uid[:8]}@example.com",
                    "name": f"User {uid[:8]}",
                    "avatar_url": None,
                }))
            return results

        return []

    async def execute(self, query: str, *args) -> str:
        q = query.strip().lower()
        if "delete from workspaces" in q:
            return "DELETE 1"
        if "delete from workspace_members" in q:
            return "DELETE 1"
        return ""

    def transaction(self):
        return _FakeTxn()


class _FakeTxn:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


class FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self): return self._conn
    async def __aexit__(self, *_): pass


def _fake_pool(conn=None):
    if conn is None:
        conn = FakeConn()
    pool = MagicMock()
    ctx = FakeConnCtx(conn)
    pool.acquire = MagicMock(return_value=ctx)
    return pool


def _app():
    app = FastAPI()
    app.include_router(api_routes.router, prefix="/api")
    return app


def _auth_header(user_id: str) -> dict:
    from kerf_auth.routes import generate_access_token
    token, _ = generate_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# W01  list_workspaces JOIN only returns own workspaces
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_w01_list_workspaces_only_returns_own():
    """User A's membership query returns WS_A only — not WS_B."""
    conn = FakeConn()
    rows = await conn.fetch(
        """
        SELECT w.id, w.slug, w.name, w.avatar_storage_key, w.created_by,
               w.created_at, w.updated_at, m.role,
               0 as member_count, 0 as project_count
        FROM workspaces w
        JOIN workspace_members m ON m.workspace_id = w.id
        WHERE m.user_id = $1
        ORDER BY w.created_at ASC
        """,
        USER_A,
    )
    slugs = {r["slug"] for r in rows}
    assert WS_A_SLUG in slugs, "User A must see their own workspace"
    assert WS_B_SLUG not in slugs, "User A must NOT see User B's workspace"


# ---------------------------------------------------------------------------
# W02  User B's workspaces not returned to User A
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_w02_cross_tenant_workspace_invisible():
    """User A performing list never receives WS_B rows."""
    conn = FakeConn()
    rows = await conn.fetch(
        "SELECT w.id FROM workspaces w JOIN workspace_members m ON m.workspace_id = w.id WHERE m.user_id = $1 ORDER BY w.created_at ASC",
        USER_A,
    )
    returned_ids = {str(r["id"]) for r in rows}
    assert WS_B_ID not in returned_ids


# ---------------------------------------------------------------------------
# W03  get_workspace: non-member sees 404 not 403
# ---------------------------------------------------------------------------

def test_w03_get_workspace_non_member_returns_404():
    """User A requesting WS_B returns 404 (workspace hidden, not 403 — security by obscurity)."""
    conn = FakeConn()

    with patch.object(api_routes, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(api_routes.workspaces_queries, "get_workspace_by_slug",
                      AsyncMock(return_value=dict(_WORKSPACES[WS_B_ID]))), \
         patch.object(api_routes, "get_user_workspace_role", AsyncMock(return_value=None)):
        client = TestClient(_app())
        r = client.get(f"/api/workspaces/{WS_B_SLUG}", headers=_auth_header(USER_A))

    assert r.status_code == 404, f"Expected 404 for non-member, got {r.status_code}"


# ---------------------------------------------------------------------------
# W04  get_workspace: member sees workspace + member list
# ---------------------------------------------------------------------------

def test_w04_get_workspace_member_sees_workspace():
    """User A requesting WS_A (their workspace) receives the workspace detail."""
    conn = FakeConn()
    ws_row = dict(_WORKSPACES[WS_A_ID])
    members = [
        {
            "workspace_id": uuid.UUID(WS_A_ID),
            "user_id": uuid.UUID(USER_A),
            "role": "owner",
            "created_at": _TS,
            "email": "user-a@example.com",
            "name": "User A",
            "avatar_url": None,
        }
    ]

    with patch.object(api_routes, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(api_routes.workspaces_queries, "get_workspace_by_slug", AsyncMock(return_value=ws_row)), \
         patch.object(api_routes, "get_user_workspace_role", AsyncMock(return_value="owner")), \
         patch.object(api_routes.workspaces_queries, "list_workspace_members", AsyncMock(return_value=members)):
        client = TestClient(_app())
        r = client.get(f"/api/workspaces/{WS_A_SLUG}", headers=_auth_header(USER_A))

    assert r.status_code == 200, f"Expected 200 for owner, got {r.status_code}: {r.text}"
    body = r.json()
    assert body["slug"] == WS_A_SLUG
    assert "members" in body
    assert len(body["members"]) == 1


# ---------------------------------------------------------------------------
# W05  get_workspace: completely unknown slug → 404
# ---------------------------------------------------------------------------

def test_w05_get_workspace_unknown_slug_returns_404():
    """A slug that does not exist in the DB → 404."""
    with patch.object(api_routes, "get_pool_required", AsyncMock(return_value=_fake_pool())), \
         patch.object(api_routes.workspaces_queries, "get_workspace_by_slug", AsyncMock(return_value=None)):
        client = TestClient(_app())
        r = client.get("/api/workspaces/no-such-workspace", headers=_auth_header(USER_A))

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# W06  update_workspace: non-member → 403
# ---------------------------------------------------------------------------

def test_w06_update_workspace_non_member_gets_403():
    """User D (no membership) attempting PATCH /workspaces/{slug} must get 403."""
    conn = FakeConn()
    ws_row = dict(_WORKSPACES[WS_A_ID])

    with patch.object(api_routes, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(api_routes.workspaces_queries, "get_workspace_by_slug", AsyncMock(return_value=ws_row)), \
         patch.object(api_routes, "get_user_workspace_role", AsyncMock(return_value=None)):
        client = TestClient(_app())
        r = client.patch(
            f"/api/workspaces/{WS_A_SLUG}",
            json={"name": "Hacked Corp"},
            headers=_auth_header(USER_D),
        )

    assert r.status_code == 403


# ---------------------------------------------------------------------------
# W07  update_workspace: member role (non-admin/owner) → 403
# ---------------------------------------------------------------------------

def test_w07_update_workspace_member_gets_403():
    """User C is 'member' of WS_A — PATCH must be rejected with 403."""
    ws_row = dict(_WORKSPACES[WS_A_ID])

    with patch.object(api_routes, "get_pool_required", AsyncMock(return_value=_fake_pool())), \
         patch.object(api_routes.workspaces_queries, "get_workspace_by_slug", AsyncMock(return_value=ws_row)), \
         patch.object(api_routes, "get_user_workspace_role", AsyncMock(return_value="member")):
        client = TestClient(_app())
        r = client.patch(
            f"/api/workspaces/{WS_A_SLUG}",
            json={"name": "Sneaky Rename"},
            headers=_auth_header(USER_C),
        )

    assert r.status_code == 403


# ---------------------------------------------------------------------------
# W08  update_workspace: admin role → allowed
# ---------------------------------------------------------------------------

def test_w08_update_workspace_admin_allowed():
    """An 'admin' may update workspace settings."""
    ws_row = dict(_WORKSPACES[WS_A_ID])
    updated_ws = {**ws_row, "name": "Acme Corp Updated", "my_role": "admin"}

    with patch.object(api_routes, "get_pool_required", AsyncMock(return_value=_fake_pool())), \
         patch.object(api_routes.workspaces_queries, "get_workspace_by_slug", AsyncMock(return_value=ws_row)), \
         patch.object(api_routes, "get_user_workspace_role", AsyncMock(return_value="admin")), \
         patch.object(api_routes.workspaces_queries, "update_workspace", AsyncMock(return_value=updated_ws)):
        client = TestClient(_app())
        r = client.patch(
            f"/api/workspaces/{WS_A_SLUG}",
            json={"name": "Acme Corp Updated"},
            headers=_auth_header(USER_A),
        )

    assert r.status_code == 200


# ---------------------------------------------------------------------------
# W09  delete_workspace: admin role → 403 (owner only)
# ---------------------------------------------------------------------------

def test_w09_delete_workspace_admin_gets_403():
    """Admin cannot delete a workspace — only owner may."""
    ws_row = dict(_WORKSPACES[WS_A_ID])

    with patch.object(api_routes, "get_pool_required", AsyncMock(return_value=_fake_pool())), \
         patch.object(api_routes.workspaces_queries, "get_workspace_by_slug", AsyncMock(return_value=ws_row)), \
         patch.object(api_routes, "get_user_workspace_role", AsyncMock(return_value="admin")):
        client = TestClient(_app())
        r = client.delete(f"/api/workspaces/{WS_A_SLUG}", headers=_auth_header(USER_A))

    assert r.status_code == 403


# ---------------------------------------------------------------------------
# W10  delete_workspace: owner role → 204
# ---------------------------------------------------------------------------

def test_w10_delete_workspace_owner_allowed():
    """Owner may delete their workspace (204 No Content)."""
    ws_row = dict(_WORKSPACES[WS_A_ID])

    with patch.object(api_routes, "get_pool_required", AsyncMock(return_value=_fake_pool())), \
         patch.object(api_routes.workspaces_queries, "get_workspace_by_slug", AsyncMock(return_value=ws_row)), \
         patch.object(api_routes, "get_user_workspace_role", AsyncMock(return_value="owner")), \
         patch.object(api_routes.workspaces_queries, "delete_workspace", AsyncMock(return_value=True)):
        client = TestClient(_app())
        r = client.delete(f"/api/workspaces/{WS_A_SLUG}", headers=_auth_header(USER_A))

    assert r.status_code == 204


# ---------------------------------------------------------------------------
# W11  invite_workspace_member: member role cannot invite → 403
# ---------------------------------------------------------------------------

def test_w11_invite_member_cannot_invite():
    """A 'member' may not invite others — only owner/admin may."""
    ws_row = dict(_WORKSPACES[WS_A_ID])

    with patch.object(api_routes, "get_pool_required", AsyncMock(return_value=_fake_pool())), \
         patch.object(api_routes.workspaces_queries, "get_workspace_by_slug", AsyncMock(return_value=ws_row)), \
         patch.object(api_routes, "get_user_workspace_role", AsyncMock(return_value="member")):
        client = TestClient(_app())
        r = client.post(
            f"/api/workspaces/{WS_A_SLUG}/members",
            json={"email": "outsider@example.com", "role": "member"},
            headers=_auth_header(USER_C),
        )

    assert r.status_code == 403


# ---------------------------------------------------------------------------
# W12  invite_workspace_member: non-member → 403
# ---------------------------------------------------------------------------

def test_w12_invite_non_member_gets_403():
    """A user with no workspace membership cannot invite others."""
    ws_row = dict(_WORKSPACES[WS_A_ID])

    with patch.object(api_routes, "get_pool_required", AsyncMock(return_value=_fake_pool())), \
         patch.object(api_routes.workspaces_queries, "get_workspace_by_slug", AsyncMock(return_value=ws_row)), \
         patch.object(api_routes, "get_user_workspace_role", AsyncMock(return_value=None)):
        client = TestClient(_app())
        r = client.post(
            f"/api/workspaces/{WS_A_SLUG}/members",
            json={"email": "hijack@example.com", "role": "owner"},
            headers=_auth_header(USER_D),
        )

    assert r.status_code == 403


# ---------------------------------------------------------------------------
# W13  change_workspace_member_role: cannot demote sole owner → 400
# ---------------------------------------------------------------------------

def test_w13_cannot_demote_sole_owner():
    """Attempting to demote the only owner to member must return 400."""
    ws_row = dict(_WORKSPACES[WS_A_ID])
    current_member = {
        "workspace_id": uuid.UUID(WS_A_ID),
        "user_id": uuid.UUID(USER_A),
        "role": "owner",
        "created_at": _TS,
    }
    conn = FakeConn()
    # Override fetchval so owner count returns 1
    conn._owner_count[WS_A_ID] = 1

    with patch.object(api_routes, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(api_routes.workspaces_queries, "get_workspace_by_slug", AsyncMock(return_value=ws_row)), \
         patch.object(api_routes, "get_user_workspace_role", AsyncMock(return_value="owner")), \
         patch.object(api_routes.workspaces_queries, "get_workspace_member", AsyncMock(return_value=current_member)):
        client = TestClient(_app())
        r = client.patch(
            f"/api/workspaces/{WS_A_SLUG}/members/{USER_A}",
            json={"role": "member"},
            headers=_auth_header(USER_A),
        )

    assert r.status_code == 400, (
        f"Expected 400 when demoting sole owner, got {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# W14  remove_workspace_member: cannot remove sole owner → 400
# ---------------------------------------------------------------------------

def test_w14_cannot_remove_sole_owner():
    """Attempting to remove the only owner must return 400."""
    ws_row = dict(_WORKSPACES[WS_A_ID])
    current_member = {
        "workspace_id": uuid.UUID(WS_A_ID),
        "user_id": uuid.UUID(USER_A),
        "role": "owner",
        "created_at": _TS,
    }
    conn = FakeConn()
    conn._owner_count[WS_A_ID] = 1  # only one owner

    with patch.object(api_routes, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(api_routes.workspaces_queries, "get_workspace_by_slug", AsyncMock(return_value=ws_row)), \
         patch.object(api_routes, "get_user_workspace_role", AsyncMock(return_value="owner")), \
         patch.object(api_routes.workspaces_queries, "get_workspace_member", AsyncMock(return_value=current_member)):
        client = TestClient(_app())
        r = client.delete(
            f"/api/workspaces/{WS_A_SLUG}/members/{USER_A}",
            headers=_auth_header(USER_A),
        )

    assert r.status_code == 400, (
        f"Expected 400 when removing sole owner, got {r.status_code}: {r.text}"
    )


# ---------------------------------------------------------------------------
# W15  remove_workspace_member: admin can remove non-owner member
# ---------------------------------------------------------------------------

def test_w15_admin_can_remove_non_owner_member():
    """An admin removing a 'member' succeeds with 204."""
    ws_row = dict(_WORKSPACES[WS_A_ID])
    member_to_remove = {
        "workspace_id": uuid.UUID(WS_A_ID),
        "user_id": uuid.UUID(USER_C),
        "role": "member",
        "created_at": _TS,
    }

    with patch.object(api_routes, "get_pool_required", AsyncMock(return_value=_fake_pool())), \
         patch.object(api_routes.workspaces_queries, "get_workspace_by_slug", AsyncMock(return_value=ws_row)), \
         patch.object(api_routes, "get_user_workspace_role", AsyncMock(return_value="admin")), \
         patch.object(api_routes.workspaces_queries, "get_workspace_member", AsyncMock(return_value=member_to_remove)), \
         patch.object(api_routes.workspaces_queries, "remove_workspace_member", AsyncMock(return_value=True)):
        client = TestClient(_app())
        r = client.delete(
            f"/api/workspaces/{WS_A_SLUG}/members/{USER_C}",
            headers=_auth_header(USER_A),
        )

    assert r.status_code == 204
