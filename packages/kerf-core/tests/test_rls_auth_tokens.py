"""
T-85 — RLS: api_tokens + refresh_tokens
=========================================
Hermetic tests for application-level multi-tenant access control on the
``api_tokens`` and ``refresh_tokens`` tables.

The application enforces tenant isolation by always filtering queries with
``workspace_id`` (api_tokens) and ``user_id`` (refresh_tokens).  No Postgres
row-level security policies exist — the invariants live in the query layer.

All 12 cases are fully in-memory: no real database required.

Invariants under test
----------------------
api_tokens — SELECT:
  1. list_api_tokens(workspace_id=WS_A) returns only WS_A tokens.
  2. list_api_tokens(workspace_id=WS_B) returns nothing for the fake store
     (cross-tenant workspace filter yields empty).
  3. list_api_tokens(workspace_id=WS_A, user_id=USER_A) further scopes to owner.
  4. get_api_token(token_A_id) returns the correct row.
  5. get_api_token_by_hash returns None when token is revoked (revoked_at set).

api_tokens — WRITE:
  6. create_api_token stores workspace_id + user_id exactly as supplied —
     no cross-tenant drift is possible via the query.
  7. revoke_api_token updates only the matching id — it does NOT touch other
     tenants' tokens even if passed an id from another workspace.
  8. list_api_tokens(include_revoked=False) hides revoked tokens; True shows them.

refresh_tokens:
  9.  create_refresh_token stores user_id exactly as supplied.
  10. get_refresh_token returns None when revoked_at is set.
  11. get_refresh_token returns None when expires_at is in the past.
  12. revoke_all_user_refresh_tokens affects only the specified user's tokens.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Fixtures — two isolated tenants
# ---------------------------------------------------------------------------

WS_A = str(uuid.uuid4())
WS_B = str(uuid.uuid4())
USER_A = str(uuid.uuid4())
USER_B = str(uuid.uuid4())

TOKEN_A1_ID = str(uuid.uuid4())
TOKEN_A2_ID = str(uuid.uuid4())
TOKEN_B1_ID = str(uuid.uuid4())
TOKEN_A1_HASH = "hash_a1_active"
TOKEN_A2_HASH = "hash_a2_revoked"
TOKEN_B1_HASH = "hash_b1_active"

REFRESH_A1_HASH = "refresh_hash_a1"
REFRESH_A2_HASH = "refresh_hash_a2_revoked"
REFRESH_B1_HASH = "refresh_hash_b1"

_NOW = datetime.now(timezone.utc)
_FUTURE = _NOW + timedelta(hours=1)
_PAST = _NOW - timedelta(hours=1)


# ---------------------------------------------------------------------------
# In-memory fake DB stores
# ---------------------------------------------------------------------------

def _make_api_token(
    tid: str,
    ws_id: str,
    uid: str,
    token_hash: str,
    name: str,
    revoked_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    return {
        "id": uuid.UUID(tid),
        "workspace_id": uuid.UUID(ws_id),
        "user_id": uuid.UUID(uid),
        "token_hash": token_hash,
        "name": name,
        "scopes": ["workspace:member-role"],
        "last_used_at": None,
        "revoked_at": revoked_at,
        "created_at": _NOW,
    }


def _make_refresh_token(
    uid: str,
    token_hash: str,
    expires_at: datetime,
    revoked_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "user_id": uuid.UUID(uid),
        "token_hash": token_hash,
        "expires_at": expires_at,
        "revoked_at": revoked_at,
        "created_at": _NOW,
    }


# Mutable stores (reset per-case via deep copy when needed)
_API_TOKENS: Dict[str, Dict[str, Any]] = {
    TOKEN_A1_ID: _make_api_token(TOKEN_A1_ID, WS_A, USER_A, TOKEN_A1_HASH, "sdk-token-a1"),
    TOKEN_A2_ID: _make_api_token(TOKEN_A2_ID, WS_A, USER_A, TOKEN_A2_HASH, "sdk-token-a2-revoked", revoked_at=_NOW),
    TOKEN_B1_ID: _make_api_token(TOKEN_B1_ID, WS_B, USER_B, TOKEN_B1_HASH, "sdk-token-b1"),
}

_REFRESH_TOKENS: Dict[str, Dict[str, Any]] = {
    REFRESH_A1_HASH: _make_refresh_token(USER_A, REFRESH_A1_HASH, _FUTURE),
    REFRESH_A2_HASH: _make_refresh_token(USER_A, REFRESH_A2_HASH, _FUTURE, revoked_at=_NOW),
    REFRESH_B1_HASH: _make_refresh_token(USER_B, REFRESH_B1_HASH, _FUTURE),
}


# ---------------------------------------------------------------------------
# Fake connection — mirrors the query layer behaviour
# ---------------------------------------------------------------------------

class FakeConn:
    """In-memory asyncpg.Connection stand-in for token query tests."""

    # ---- api_tokens --------------------------------------------------------

    async def fetchrow(self, query: str, *args) -> Optional[Dict[str, Any]]:
        q = query.strip().lower()

        # get_api_token: SELECT * FROM api_tokens WHERE id = $1
        if "from api_tokens" in q and "where id = $1" in q:
            tid = str(args[0])
            return dict(_API_TOKENS[tid]) if tid in _API_TOKENS else None

        # get_api_token_by_hash: UPDATE api_tokens SET last_used_at … WHERE token_hash = $1
        if "from api_tokens" in q and "token_hash = $1" in q:
            token_hash = args[0]
            for row in _API_TOKENS.values():
                if row["token_hash"] == token_hash and row["revoked_at"] is None:
                    row["last_used_at"] = _NOW
                    return dict(row)
            return None

        # create_api_token: INSERT INTO api_tokens … RETURNING *
        if "insert into api_tokens" in q:
            ws_id, uid, token_hash, name, scopes = args
            new_id = str(uuid.uuid4())
            row = _make_api_token(new_id, str(ws_id), str(uid), token_hash, name)
            row["scopes"] = scopes
            _API_TOKENS[new_id] = row
            return dict(row)

        # create_refresh_token: INSERT INTO refresh_tokens … RETURNING *
        if "insert into refresh_tokens" in q:
            uid, token_hash, expires_at = args
            row = _make_refresh_token(str(uid), token_hash, expires_at)
            _REFRESH_TOKENS[token_hash] = row
            return dict(row)

        # get_refresh_token: SELECT * FROM refresh_tokens WHERE token_hash = $1 …
        if "from refresh_tokens" in q and "token_hash = $1" in q:
            token_hash = args[0]
            row = _REFRESH_TOKENS.get(token_hash)
            if row is None:
                return None
            if row["revoked_at"] is not None:
                return None
            # expires_at > now()
            exp = row["expires_at"]
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp <= _NOW:
                return None
            return dict(row)

        return None

    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        q = query.strip().lower()

        # list_api_tokens — dynamic WHERE clause; we parse the filter args
        if "from api_tokens" in q:
            results = list(_API_TOKENS.values())

            # Apply workspace_id / user_id / revoked_at filters as the real
            # query does (order of $N params follows list_api_tokens logic).
            param_idx = 0

            if "workspace_id = $" in q:
                ws_filter = str(args[param_idx])
                results = [r for r in results if str(r["workspace_id"]) == ws_filter]
                param_idx += 1

            if "user_id = $" in q:
                uid_filter = str(args[param_idx])
                results = [r for r in results if str(r["user_id"]) == uid_filter]
                param_idx += 1

            if "revoked_at is null" in q:
                results = [r for r in results if r["revoked_at"] is None]

            return [dict(r) for r in results]

        return []

    async def execute(self, query: str, *args) -> str:
        q = query.strip().lower()

        # revoke_api_token: UPDATE api_tokens SET revoked_at = now() WHERE id = $1
        if "update api_tokens set revoked_at" in q and "where id = $1" in q:
            tid = str(args[0])
            if tid in _API_TOKENS:
                _API_TOKENS[tid]["revoked_at"] = _NOW
                return "UPDATE 1"
            return "UPDATE 0"

        # revoke_refresh_token: UPDATE refresh_tokens SET revoked_at WHERE token_hash = $1
        if "update refresh_tokens set revoked_at" in q and "token_hash = $1" in q:
            token_hash = args[0]
            if token_hash in _REFRESH_TOKENS:
                _REFRESH_TOKENS[token_hash]["revoked_at"] = _NOW
                return "UPDATE 1"
            return "UPDATE 0"

        # revoke_all_user_refresh_tokens: … WHERE user_id = $1 AND revoked_at IS NULL
        if "update refresh_tokens set revoked_at" in q and "user_id = $1" in q:
            uid = str(args[0])
            count = 0
            for row in _REFRESH_TOKENS.values():
                if str(row["user_id"]) == uid and row["revoked_at"] is None:
                    row["revoked_at"] = _NOW
                    count += 1
            return f"UPDATE {count}"

        return ""


# ---------------------------------------------------------------------------
# Case 1 — list_api_tokens scoped to WS_A only returns WS_A tokens
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_api_tokens_ws_a_only():
    """Filtering by workspace_id=WS_A must exclude WS_B tokens."""
    from kerf_core.db.queries.api_tokens import list_api_tokens

    conn = FakeConn()
    tokens = await list_api_tokens(conn, workspace_id=uuid.UUID(WS_A))
    ids = {str(t["id"]) for t in tokens}
    # WS_A has TOKEN_A1 (active); TOKEN_A2 is revoked → hidden by default
    assert TOKEN_A1_ID in ids, "Active WS_A token must be returned"
    assert TOKEN_B1_ID not in ids, "WS_B token must not leak into WS_A listing"


# ---------------------------------------------------------------------------
# Case 2 — list_api_tokens(WS_B) returns nothing when store has no WS_B active tokens
# for a USER_A context (cross-tenant workspace filter)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_api_tokens_cross_tenant_ws_b_invisible():
    """Requesting WS_B tokens as USER_A context must not return WS_B rows
    because the workspace_id filter is enforced by the query layer.
    The test asserts that USER_A's tokens are not returned when workspace_id=WS_B."""
    from kerf_core.db.queries.api_tokens import list_api_tokens

    conn = FakeConn()
    # USER_A requests their tokens scoped to WS_B — workspace_id filter blocks it
    tokens = await list_api_tokens(conn, workspace_id=uuid.UUID(WS_B), user_id=uuid.UUID(USER_A))
    assert tokens == [], (
        "USER_A has no tokens in WS_B — cross-tenant filter must return empty list"
    )


# ---------------------------------------------------------------------------
# Case 3 — list_api_tokens(WS_A, USER_A) returns only USER_A's active WS_A tokens
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_api_tokens_ws_a_user_a_scoped():
    """Dual workspace+user filter returns only that user's active tokens."""
    from kerf_core.db.queries.api_tokens import list_api_tokens

    conn = FakeConn()
    tokens = await list_api_tokens(conn, workspace_id=uuid.UUID(WS_A), user_id=uuid.UUID(USER_A))
    ids = {str(t["id"]) for t in tokens}
    # Only TOKEN_A1 is active for USER_A in WS_A (TOKEN_A2 is revoked)
    assert TOKEN_A1_ID in ids
    assert TOKEN_A2_ID not in ids, "Revoked token must be hidden by default"
    assert TOKEN_B1_ID not in ids, "WS_B token must not appear"


# ---------------------------------------------------------------------------
# Case 4 — get_api_token returns row by id for own token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_api_token_by_id_own_token():
    """get_api_token returns the correct record for the token owner."""
    from kerf_core.db.queries.api_tokens import get_api_token

    conn = FakeConn()
    row = await get_api_token(conn, uuid.UUID(TOKEN_A1_ID))
    assert row is not None
    assert str(row["workspace_id"]) == WS_A
    assert str(row["user_id"]) == USER_A
    assert row["name"] == "sdk-token-a1"


# ---------------------------------------------------------------------------
# Case 5 — get_api_token_by_hash returns None when token is revoked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_api_token_by_hash_revoked_invisible():
    """A revoked api_token must not be resolvable by hash (revoked_at IS NULL guard)."""
    from kerf_core.db.queries.api_tokens import get_api_token_by_hash

    conn = FakeConn()
    row = await get_api_token_by_hash(conn, TOKEN_A2_HASH)
    assert row is None, "Revoked token must not be returned by get_api_token_by_hash"


# ---------------------------------------------------------------------------
# Case 6 — create_api_token stores workspace_id + user_id exactly as supplied
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_api_token_binds_correct_tenant():
    """create_api_token must bind the supplied workspace_id and user_id —
    the caller cannot drift the token into another tenant's workspace."""
    from kerf_core.db.queries.api_tokens import create_api_token

    conn = FakeConn()
    result = await create_api_token(
        conn,
        workspace_id=uuid.UUID(WS_A),
        user_id=uuid.UUID(USER_A),
        token_hash="new_test_hash_xyz",
        name="ci-token",
        scopes=["workspace:member-role"],
    )
    assert str(result["workspace_id"]) == WS_A, "workspace_id must match WS_A exactly"
    assert str(result["user_id"]) == USER_A, "user_id must match USER_A exactly"
    assert result["name"] == "ci-token"


# ---------------------------------------------------------------------------
# Case 7 — revoke_api_token revokes only the targeted id; does not touch others
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_revoke_api_token_targets_only_specified_id():
    """Revoking TOKEN_B1 must not affect TOKEN_A1 — no cross-tenant side-effects."""
    from kerf_core.db.queries.api_tokens import revoke_api_token, get_api_token

    conn = FakeConn()
    # Pre-condition: both TOKEN_A1 and TOKEN_B1 are active
    assert _API_TOKENS[TOKEN_A1_ID]["revoked_at"] is None
    assert _API_TOKENS[TOKEN_B1_ID]["revoked_at"] is None

    # Revoke TOKEN_B1
    result = await revoke_api_token(conn, uuid.UUID(TOKEN_B1_ID))
    assert result is True, "revoke_api_token must return True on success"

    # TOKEN_B1 is now revoked
    assert _API_TOKENS[TOKEN_B1_ID]["revoked_at"] is not None

    # TOKEN_A1 must be completely untouched
    row_a1 = await get_api_token(conn, uuid.UUID(TOKEN_A1_ID))
    assert row_a1 is not None
    assert row_a1["revoked_at"] is None, "TOKEN_A1 must remain active after TOKEN_B1 revocation"

    # Restore for other tests
    _API_TOKENS[TOKEN_B1_ID]["revoked_at"] = None


# ---------------------------------------------------------------------------
# Case 8 — list_api_tokens(include_revoked=True) exposes revoked tokens
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_api_tokens_include_revoked_flag():
    """include_revoked=True must surface revoked tokens; False must hide them."""
    from kerf_core.db.queries.api_tokens import list_api_tokens

    conn = FakeConn()

    # Default (include_revoked=False)
    active_only = await list_api_tokens(conn, workspace_id=uuid.UUID(WS_A))
    active_ids = {str(t["id"]) for t in active_only}
    assert TOKEN_A2_ID not in active_ids, "Revoked token must be hidden by default"

    # include_revoked=True
    all_tokens = await list_api_tokens(conn, workspace_id=uuid.UUID(WS_A), include_revoked=True)
    all_ids = {str(t["id"]) for t in all_tokens}
    assert TOKEN_A2_ID in all_ids, "include_revoked=True must reveal revoked token"


# ---------------------------------------------------------------------------
# Case 9 — create_refresh_token stores user_id exactly as supplied
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_refresh_token_binds_correct_user():
    """create_refresh_token must bind user_id exactly — no cross-tenant drift."""
    from kerf_core.db.queries.refresh_tokens import create_refresh_token

    conn = FakeConn()
    expires = _NOW + timedelta(days=7)
    row = await create_refresh_token(conn, uuid.UUID(USER_A), "new_refresh_hash_001", expires)
    assert str(row["user_id"]) == USER_A, "user_id must be bound to USER_A"
    assert row["token_hash"] == "new_refresh_hash_001"
    assert row["revoked_at"] is None


# ---------------------------------------------------------------------------
# Case 10 — get_refresh_token returns None when token is revoked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_refresh_token_revoked_invisible():
    """A revoked refresh_token must not be resolvable (revoked_at IS NULL guard)."""
    from kerf_core.db.queries.refresh_tokens import get_refresh_token

    conn = FakeConn()
    row = await get_refresh_token(conn, REFRESH_A2_HASH)
    assert row is None, "Revoked refresh token must return None"


# ---------------------------------------------------------------------------
# Case 11 — get_refresh_token returns None when token is expired
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_refresh_token_expired_invisible():
    """An expired refresh_token must not be resolvable (expires_at > now() guard)."""
    from kerf_core.db.queries.refresh_tokens import get_refresh_token

    expired_hash = "expired_refresh_hash_test"
    _REFRESH_TOKENS[expired_hash] = _make_refresh_token(USER_A, expired_hash, _PAST)
    try:
        conn = FakeConn()
        row = await get_refresh_token(conn, expired_hash)
        assert row is None, "Expired refresh token must return None"
    finally:
        del _REFRESH_TOKENS[expired_hash]


# ---------------------------------------------------------------------------
# Case 12 — revoke_all_user_refresh_tokens only affects the specified user
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_revoke_all_user_refresh_tokens_tenant_isolation():
    """revoke_all_user_refresh_tokens(USER_A) must not revoke USER_B's tokens."""
    from kerf_core.db.queries.refresh_tokens import revoke_all_user_refresh_tokens

    # Ensure USER_B's token is not yet revoked
    _REFRESH_TOKENS[REFRESH_B1_HASH]["revoked_at"] = None
    # USER_A's active token should also be unrevoked before test
    _REFRESH_TOKENS[REFRESH_A1_HASH]["revoked_at"] = None

    conn = FakeConn()
    count = await revoke_all_user_refresh_tokens(conn, uuid.UUID(USER_A))

    # At minimum the one active USER_A token is revoked
    assert count >= 1, f"Expected at least 1 revoked token for USER_A, got {count}"

    # USER_A's token is now revoked
    assert _REFRESH_TOKENS[REFRESH_A1_HASH]["revoked_at"] is not None, (
        "USER_A's refresh token must be revoked"
    )

    # USER_B's token must be untouched
    assert _REFRESH_TOKENS[REFRESH_B1_HASH]["revoked_at"] is None, (
        "USER_B's refresh token must NOT be revoked — cross-tenant isolation violated"
    )

    # Restore USER_A token for other test runs
    _REFRESH_TOKENS[REFRESH_A1_HASH]["revoked_at"] = None
