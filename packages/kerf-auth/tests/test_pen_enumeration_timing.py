"""T-76 — Account enumeration timing leaks.

Scope: login + reset (forgot-password) endpoints are constant-time on
user-exists vs not — an attacker cannot enumerate valid accounts by
measuring response-time deltas.

10 hermetic cases (asyncpg mocked):

  C01  login: unknown email → 401 with "invalid credentials"
  C02  login: known email + wrong password → 401 with "invalid credentials"
  C03  login: unknown email error text == known-wrong-password error text
  C04  login: unknown email performs a dummy bcrypt check (timing guard present)
  C05  login: unknown email status code == known-wrong-password status code
  C06  forgot-password: unknown email → 200 {"status": "ok"}
  C07  forgot-password: known email + no password_hash (OAuth) → 200 {"status": "ok"}
  C08  forgot-password: known email + password_hash → 200 {"status": "ok"}
  C09  forgot-password: identical response body for unknown vs known email
  C10  _DUMMY_HASH constant is a valid bcrypt hash (guard integrity check)
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import kerf_auth.routes as auth


# ---------------------------------------------------------------------------
# Helpers shared across cases
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_rate_limit_enforce(monkeypatch):
    """Prevent rate_limit from hitting the DB pool in all tests here.

    The rate_limit() dependency in kerf_core.dependencies calls
    kerf_core.rate_limit.enforce(pool, ...) which needs a live DB.
    We stub enforce to be a no-op so the login/register endpoint tests
    stay hermetic.
    """
    # Stub enforce so rate_limit deps never need a live pool
    import kerf_core.rate_limit as _rl_module
    monkeypatch.setattr(_rl_module, "enforce", AsyncMock(return_value=None))

    # rate_limit._dep imports get_pool_required locally; patch it in
    # kerf_core.db.connection so the local import resolves to our no-op.
    import kerf_core.db.connection as _conn_module
    _fake_pool_obj = MagicMock()
    monkeypatch.setattr(_conn_module, "get_pool_required", AsyncMock(return_value=_fake_pool_obj))


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    return app


def _fake_pool(conn):
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _conn_no_user():
    """Connection that returns None for get_user_by_email → unknown account."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    return conn


def _conn_known_user(password: str = "correctpassword"):
    """Connection that returns a user row with a real bcrypt hash."""
    from datetime import datetime, timezone
    hashed = auth.hash_password(password)
    user_row = MagicMock()
    user_row.__getitem__ = lambda self, k: {
        "id": "u-known-1",
        "email": "known@example.com",
        "name": "Known User",
        "avatar_url": None,
        "account_role": "user",
        "is_system": False,
        "email_verified": True,
        "created_at": datetime.now(timezone.utc),
        "password_hash": hashed,
    }[k]
    user_row.get = lambda k, default=None: {
        "email_verified": True,
        "password_hash": hashed,
    }.get(k, default)
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=user_row)
    conn.execute = AsyncMock()
    return conn, user_row


def _conn_known_user_no_hash():
    """OAuth user — password_hash is None."""
    from datetime import datetime, timezone
    user_row = MagicMock()
    user_row.__getitem__ = lambda self, k: {
        "id": "u-oauth-1",
        "email": "oauth@example.com",
        "name": "OAuth User",
        "avatar_url": None,
        "account_role": "user",
        "is_system": False,
        "email_verified": True,
        "created_at": datetime.now(timezone.utc),
        "password_hash": None,
    }[k]
    user_row.get = lambda k, default=None: {
        "email_verified": True,
        "password_hash": None,
    }.get(k, default)
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=user_row)
    conn.execute = AsyncMock()
    return conn, user_row


# ---------------------------------------------------------------------------
# C01  login: unknown email → 401 "invalid credentials"
# ---------------------------------------------------------------------------

def test_c01_login_unknown_email_returns_401():
    conn = _conn_no_user()
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))):
        c = TestClient(_app())
        r = c.post("/auth/login", json={"email": "nobody@example.com", "password": "anypass"})
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid credentials"


# ---------------------------------------------------------------------------
# C02  login: known email + wrong password → 401 "invalid credentials"
# ---------------------------------------------------------------------------

def test_c02_login_known_wrong_password_returns_401():
    conn, _ = _conn_known_user(password="correctpassword")
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))):
        c = TestClient(_app())
        r = c.post("/auth/login", json={"email": "known@example.com", "password": "wrongpassword"})
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid credentials"


# ---------------------------------------------------------------------------
# C03  login: error text is identical for unknown vs wrong-password
# ---------------------------------------------------------------------------

def test_c03_login_error_text_identical_for_unknown_vs_wrong_password():
    conn_unknown = _conn_no_user()
    conn_known, _ = _conn_known_user(password="correctpassword")

    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn_unknown))):
        c = TestClient(_app())
        r_unknown = c.post("/auth/login", json={"email": "nobody@example.com", "password": "anypass"})

    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn_known))):
        c = TestClient(_app())
        r_wrong = c.post("/auth/login", json={"email": "known@example.com", "password": "wrongpassword"})

    assert r_unknown.status_code == r_wrong.status_code
    assert r_unknown.json()["detail"] == r_wrong.json()["detail"]


# ---------------------------------------------------------------------------
# C04  login: unknown email invokes dummy bcrypt check (timing guard present)
#
#  The route must call check_password(_DUMMY_HASH, ...) when the account is
#  absent so the response time matches the wrong-password path.  We verify
#  this by confirming check_password is called even when fetchrow returns None.
# ---------------------------------------------------------------------------

def test_c04_login_unknown_email_calls_dummy_bcrypt():
    conn = _conn_no_user()
    calls: list = []

    original_check = auth.check_password

    def spy_check(stored: str, pw: str) -> bool:
        calls.append(stored)
        return original_check(stored, pw)

    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(auth, "check_password", side_effect=spy_check):
        c = TestClient(_app())
        c.post("/auth/login", json={"email": "nobody@example.com", "password": "anypass"})

    assert len(calls) >= 1, "check_password must be called for unknown email (timing guard)"
    # The hash passed to the dummy check must be the module-level _DUMMY_HASH
    assert calls[0] == auth._DUMMY_HASH, (
        "First check_password call for unknown email must use _DUMMY_HASH, "
        f"got: {calls[0][:20]!r}..."
    )


# ---------------------------------------------------------------------------
# C05  login: HTTP status identical for unknown vs wrong-password
# ---------------------------------------------------------------------------

def test_c05_login_status_code_identical_for_unknown_vs_wrong_password():
    conn_unknown = _conn_no_user()
    conn_known, _ = _conn_known_user(password="correctpassword")

    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn_unknown))):
        c = TestClient(_app())
        r_unknown = c.post("/auth/login", json={"email": "nobody@example.com", "password": "anypass"})

    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn_known))):
        c = TestClient(_app())
        r_wrong = c.post("/auth/login", json={"email": "known@example.com", "password": "wrongpassword"})

    assert r_unknown.status_code == r_wrong.status_code == 401


# ---------------------------------------------------------------------------
# C06  forgot-password: unknown email → 200 {"status": "ok"} (no enumeration)
# ---------------------------------------------------------------------------

def test_c06_forgot_password_unknown_email_returns_200_ok():
    conn = _conn_no_user()
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))):
        c = TestClient(_app())
        r = c.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# C07  forgot-password: OAuth user (no password_hash) → 200 {"status": "ok"}
# ---------------------------------------------------------------------------

def test_c07_forgot_password_oauth_user_returns_200_ok():
    conn, user_row = _conn_known_user_no_hash()
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(auth, "_send_email"):
        c = TestClient(_app())
        r = c.post("/auth/forgot-password", json={"email": "oauth@example.com"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# C08  forgot-password: known email with password_hash → 200 {"status": "ok"}
# ---------------------------------------------------------------------------

def test_c08_forgot_password_known_email_returns_200_ok():
    from datetime import datetime, timezone

    token_row = None  # _create_email_token is mocked
    user_row = MagicMock()
    user_row.__getitem__ = lambda self, k: {
        "id": "u-known-2",
        "email": "known2@example.com",
        "name": "Known User2",
        "avatar_url": None,
        "account_role": "user",
        "is_system": False,
        "email_verified": True,
        "created_at": datetime.now(timezone.utc),
        "password_hash": "$2b$12$fakehash",
    }[k]
    user_row.get = lambda k, default=None: {
        "email_verified": True,
        "password_hash": "$2b$12$fakehash",
    }.get(k, default)

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=user_row)
    conn.execute = AsyncMock()

    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(auth, "_create_email_token", AsyncMock(return_value="reset-tok-123")), \
         patch.object(auth, "_send_email"):
        c = TestClient(_app())
        r = c.post("/auth/forgot-password", json={"email": "known2@example.com"})

    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# C09  forgot-password: response body identical for unknown vs known email
# ---------------------------------------------------------------------------

def test_c09_forgot_password_identical_response_for_unknown_vs_known():
    from datetime import datetime, timezone

    conn_unknown = _conn_no_user()

    user_row = MagicMock()
    user_row.__getitem__ = lambda self, k: {
        "id": "u-known-3",
        "email": "known3@example.com",
        "name": "Known User3",
        "avatar_url": None,
        "account_role": "user",
        "is_system": False,
        "email_verified": True,
        "created_at": datetime.now(timezone.utc),
        "password_hash": "$2b$12$fakehash",
    }[k]
    user_row.get = lambda k, default=None: {
        "email_verified": True,
        "password_hash": "$2b$12$fakehash",
    }.get(k, default)

    conn_known = AsyncMock()
    conn_known.fetchrow = AsyncMock(return_value=user_row)
    conn_known.execute = AsyncMock()

    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn_unknown))):
        c = TestClient(_app())
        r_unknown = c.post("/auth/forgot-password", json={"email": "nobody@example.com"})

    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn_known))), \
         patch.object(auth, "_create_email_token", AsyncMock(return_value="reset-tok-456")), \
         patch.object(auth, "_send_email"):
        c = TestClient(_app())
        r_known = c.post("/auth/forgot-password", json={"email": "known3@example.com"})

    assert r_unknown.status_code == r_known.status_code == 200
    assert r_unknown.json() == r_known.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# C10  _DUMMY_HASH is a valid bcrypt hash (guard integrity check)
#
#  If the constant becomes corrupted or is replaced with a non-bcrypt value
#  the timing guard silently stops working.  Verify bcrypt can parse it.
# ---------------------------------------------------------------------------

def test_c10_dummy_hash_is_valid_bcrypt():
    dummy = auth._DUMMY_HASH
    assert isinstance(dummy, str), "_DUMMY_HASH must be a str"
    # bcrypt.checkpw must not raise — the hash is syntactically valid
    try:
        result = bcrypt.checkpw(b"some-password", dummy.encode("utf-8"))
    except Exception as exc:
        pytest.fail(f"_DUMMY_HASH is not a valid bcrypt hash: {exc}")
    # It should return False (wrong password), not raise
    assert result is False
