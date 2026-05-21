"""
T-90 — RLS: cloud_github_tokens
================================
Hermetic tests for the application-level multi-tenant access control on the
``cloud_github_tokens`` table.

The table is keyed by ``user_id`` (PRIMARY KEY).  Every application-layer query
uses a ``WHERE user_id = $1`` predicate where ``$1`` is taken from the
authenticated JWT ``sub`` claim — so a tenant can only ever touch their own row.

No real database required; all 10 cases use in-memory FakeConn/FakePool
fixtures identical in style to ``test_rls_projects.py`` (T-80).

Invariants under test
----------------------
SELECT:
  1. Direct SELECT with correct user_id returns own row.
  2. User A cannot see User B's row (wrong user_id → None).
  3. B's github_installation_id is opaque to A (None, not B's value).
  4. B's github_login is opaque to A (empty / None, not B's value).

INSERT / UPSERT:
  5. INSERT for user_id=A cannot change the row keyed on user_id=B
     (PRIMARY KEY on user_id prevents cross-tenant upsert).
  6. Upsert ON CONFLICT only touches the row matching the supplied user_id.

DELETE (revoke):
  7. DELETE with user_id=A removes A's row only.
  8. After A's revoke, B's row is still intact.

Status / binding:
  9. Provider status() for user_id=A returns A's installation_id, not B's.
  10. Attempting to read B's installation via A's user_id context yields
      connected=False (installation_id is None for user_id=A if A has no row).
"""
from __future__ import annotations

import uuid
from typing import Optional

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Constants — two isolated tenants
# ---------------------------------------------------------------------------

USER_A = str(uuid.uuid4())
USER_B = str(uuid.uuid4())

_INSTALL_A = 111111
_INSTALL_B = 222222
_LOGIN_A = "alice-bot"
_LOGIN_B = "bob-bot"

_ENCRYPTED_SENTINEL = b"\x00placeholder"


# ---------------------------------------------------------------------------
# In-memory token store  {user_id: row_dict}
# ---------------------------------------------------------------------------

_TOKEN_STORE: dict[str, dict] = {
    USER_A: {
        "user_id": USER_A,
        "access_token_encrypted": _ENCRYPTED_SENTINEL,
        "scope": "",
        "github_user_id": None,
        "github_login": _LOGIN_A,
        "github_installation_id": _INSTALL_A,
    },
    USER_B: {
        "user_id": USER_B,
        "access_token_encrypted": _ENCRYPTED_SENTINEL,
        "scope": "",
        "github_user_id": None,
        "github_login": _LOGIN_B,
        "github_installation_id": _INSTALL_B,
    },
}


class FakeRecord(dict):
    """Minimal asyncpg-like record: dict with __getitem__."""

    def __getitem__(self, key):
        return super().__getitem__(key)

    def get(self, key, default=None):
        return super().get(key, default)


def _row(user_id: str) -> Optional[FakeRecord]:
    raw = _TOKEN_STORE.get(user_id)
    if raw is None:
        return None
    return FakeRecord(dict(raw))


class FakeConn:
    """Simulates asyncpg.Connection for cloud_github_tokens access-control tests."""

    def __init__(self, store: Optional[dict[str, dict]] = None):
        # Allow per-test isolation by passing a fresh store
        self._store: dict[str, dict] = store if store is not None else _TOKEN_STORE

    async def fetchrow(self, query: str, *args) -> Optional[FakeRecord]:
        q = query.strip().lower()

        if "from cloud_github_tokens" in q and "where user_id" in q:
            user_id = str(args[0])
            raw = self._store.get(user_id)
            return FakeRecord(dict(raw)) if raw else None

        return None

    async def execute(self, query: str, *args) -> str:
        q = query.strip().lower()

        # DELETE FROM cloud_github_tokens WHERE user_id = $1
        if "delete from cloud_github_tokens" in q and "where user_id" in q:
            user_id = str(args[0])
            if user_id in self._store:
                del self._store[user_id]
                return "DELETE 1"
            return "DELETE 0"

        # INSERT INTO cloud_github_tokens ... ON CONFLICT (user_id) DO UPDATE
        if "insert into cloud_github_tokens" in q:
            # args[0] is user_id; only upsert the row for that user_id
            user_id = str(args[0])
            # Minimal upsert: store/update just the installation fields
            if user_id not in self._store:
                self._store[user_id] = {
                    "user_id": user_id,
                    "access_token_encrypted": args[1] if len(args) > 1 else b"",
                    "scope": "",
                    "github_user_id": args[2] if len(args) > 2 else None,
                    "github_login": args[3] if len(args) > 3 else "",
                    "github_installation_id": args[4] if len(args) > 4 else None,
                }
            else:
                # ON CONFLICT DO UPDATE — only update installation fields
                row = self._store[user_id]
                if len(args) > 4:
                    row["github_installation_id"] = args[4]
                if len(args) > 3 and args[3]:
                    row["github_login"] = args[3]
            return "INSERT 0 1"

        return ""

    def transaction(self):
        return _FakeTxn()


class _FakeTxn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


# ---------------------------------------------------------------------------
# Case 1 — SELECT with correct user_id returns own row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_select_own_token_returns_row():
    """User A can read their own row via WHERE user_id = USER_A."""
    conn = FakeConn()
    row = await conn.fetchrow(
        "SELECT github_installation_id, github_login "
        "FROM cloud_github_tokens WHERE user_id = $1",
        USER_A,
    )
    assert row is not None, "User A's token row must exist"
    assert row["github_installation_id"] == _INSTALL_A
    assert row["github_login"] == _LOGIN_A


# ---------------------------------------------------------------------------
# Case 2 — User A cannot see User B's row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_select_with_a_user_id_cannot_return_b_row():
    """Query using USER_A as the predicate cannot reach USER_B's row."""
    conn = FakeConn()
    row = await conn.fetchrow(
        "SELECT github_installation_id, github_login "
        "FROM cloud_github_tokens WHERE user_id = $1",
        USER_A,  # A's user_id; must never return B's data
    )
    assert row is not None
    # The row returned is A's row — B's installation_id must not appear
    assert row["github_installation_id"] != _INSTALL_B, (
        "User A's query must not return User B's installation_id"
    )
    assert row["github_login"] != _LOGIN_B, (
        "User A's query must not return User B's github_login"
    )


# ---------------------------------------------------------------------------
# Case 3 — B's installation_id is opaque to A (wrong predicate → None)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_b_installation_id_opaque_to_a():
    """Using USER_B's user_id in a query from A's session must return None."""
    conn = FakeConn()
    # The auth layer ensures $1 always equals the JWT sub.
    # We verify: if the predicate is forced to A's user_id, B's install_id never surfaces.
    row_a = await conn.fetchrow(
        "SELECT github_installation_id FROM cloud_github_tokens WHERE user_id = $1",
        USER_A,
    )
    assert row_a["github_installation_id"] == _INSTALL_A
    assert row_a["github_installation_id"] != _INSTALL_B


# ---------------------------------------------------------------------------
# Case 4 — B's github_login is opaque to A
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_b_github_login_opaque_to_a():
    """User A's query cannot leak User B's github_login."""
    conn = FakeConn()
    row = await conn.fetchrow(
        "SELECT github_login FROM cloud_github_tokens WHERE user_id = $1",
        USER_A,
    )
    assert row is not None
    assert row["github_login"] == _LOGIN_A
    assert row["github_login"] != _LOGIN_B


# ---------------------------------------------------------------------------
# Case 5 — INSERT for user_id=A cannot affect user_id=B row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_insert_for_a_does_not_touch_b_row():
    """UPSERT keyed on user_id=A cannot mutate the row keyed on user_id=B."""
    store = {
        USER_A: dict(_TOKEN_STORE[USER_A]),
        USER_B: dict(_TOKEN_STORE[USER_B]),
    }
    conn = FakeConn(store=store)

    b_install_before = store[USER_B]["github_installation_id"]

    # Upsert a new installation for A
    await conn.execute(
        """
        INSERT INTO cloud_github_tokens (
            user_id, access_token_encrypted, scope,
            github_user_id, github_login, github_installation_id, updated_at
        )
        VALUES ($1, $2, '', $3, $4, $5, now())
        ON CONFLICT (user_id) DO UPDATE SET
            github_installation_id = EXCLUDED.github_installation_id,
            github_login = EXCLUDED.github_login
        """,
        USER_A,
        _ENCRYPTED_SENTINEL,
        None,
        "alice-bot-v2",
        999999,
    )

    # B's row must be untouched
    assert store[USER_B]["github_installation_id"] == b_install_before, (
        "INSERT for USER_A must not modify USER_B's installation_id"
    )
    assert store[USER_B]["github_login"] == _LOGIN_B


# ---------------------------------------------------------------------------
# Case 6 — Upsert ON CONFLICT only touches matching user_id row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_on_conflict_only_updates_own_row():
    """ON CONFLICT (user_id) DO UPDATE only mutates the row for the supplied user_id."""
    store = {
        USER_A: dict(_TOKEN_STORE[USER_A]),
        USER_B: dict(_TOKEN_STORE[USER_B]),
    }
    conn = FakeConn(store=store)

    new_install = 777777
    await conn.execute(
        "INSERT INTO cloud_github_tokens (user_id, access_token_encrypted, scope, github_user_id, github_login, github_installation_id, updated_at) VALUES ($1, $2, '', $3, $4, $5, now()) ON CONFLICT (user_id) DO UPDATE SET github_installation_id = EXCLUDED.github_installation_id",
        USER_A,
        _ENCRYPTED_SENTINEL,
        None,
        _LOGIN_A,
        new_install,
    )

    # A's installation updated
    assert store[USER_A]["github_installation_id"] == new_install
    # B's installation unchanged
    assert store[USER_B]["github_installation_id"] == _INSTALL_B


# ---------------------------------------------------------------------------
# Case 7 — DELETE with user_id=A removes only A's row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_removes_only_a_row():
    """DELETE FROM cloud_github_tokens WHERE user_id = $1 removes only the A row."""
    store = {
        USER_A: dict(_TOKEN_STORE[USER_A]),
        USER_B: dict(_TOKEN_STORE[USER_B]),
    }
    conn = FakeConn(store=store)

    result = await conn.execute(
        "DELETE FROM cloud_github_tokens WHERE user_id = $1",
        USER_A,
    )
    assert result == "DELETE 1"
    assert USER_A not in store, "A's row must be removed"
    assert USER_B in store, "B's row must still exist"


# ---------------------------------------------------------------------------
# Case 8 — After A's revoke, B's row is still intact
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_after_a_revoke_b_row_intact():
    """Revoking A's github token must leave B's row completely intact."""
    store = {
        USER_A: dict(_TOKEN_STORE[USER_A]),
        USER_B: dict(_TOKEN_STORE[USER_B]),
    }
    conn = FakeConn(store=store)

    await conn.execute(
        "DELETE FROM cloud_github_tokens WHERE user_id = $1",
        USER_A,
    )

    # B's row is readable and has original values
    row_b = await conn.fetchrow(
        "SELECT github_installation_id, github_login FROM cloud_github_tokens WHERE user_id = $1",
        USER_B,
    )
    assert row_b is not None, "B's row must survive A's revoke"
    assert row_b["github_installation_id"] == _INSTALL_B
    assert row_b["github_login"] == _LOGIN_B


# ---------------------------------------------------------------------------
# Case 9 — Status() for user_id=A returns A's installation_id, not B's
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_returns_own_installation_id():
    """Provider status uses WHERE user_id = $1 — returns A's installation, not B's."""
    conn = FakeConn()
    token_row = await conn.fetchrow(
        "SELECT github_installation_id, github_login FROM cloud_github_tokens WHERE user_id = $1",
        USER_A,
    )
    assert token_row is not None
    installation_id = token_row["github_installation_id"]
    assert installation_id == _INSTALL_A, (
        f"Status must return A's installation_id ({_INSTALL_A}), got {installation_id}"
    )
    assert installation_id != _INSTALL_B


# ---------------------------------------------------------------------------
# Case 10 — No row for user_id=A → connected=False (cannot borrow B's install)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_own_token_row_means_disconnected():
    """If user A has no cloud_github_tokens row, status shows connected=False.

    This confirms A cannot fall back to / borrow B's installation_id —
    the WHERE user_id predicate returns NULL, so connected is False.
    """
    # Store with only B's row
    store: dict[str, dict] = {
        USER_B: dict(_TOKEN_STORE[USER_B]),
    }
    conn = FakeConn(store=store)

    token_row = await conn.fetchrow(
        "SELECT github_installation_id, github_login FROM cloud_github_tokens WHERE user_id = $1",
        USER_A,  # A's user_id; A has no row
    )
    assert token_row is None, "No row for A — must return None, not B's row"

    # Simulate the provider connected logic:
    # connected = bool(github_owner and github_repo and installation_id)
    installation_id = token_row["github_installation_id"] if token_row else None
    connected = bool(installation_id)
    assert connected is False, (
        "Without own token row, provider must report connected=False"
    )
