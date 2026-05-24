"""Slice 8: email verification + password reset.

Bug history: the welcome email was sent inside a bare `except: pass`
(zero emails, zero signal), and verify/reset flows did not exist at all
despite the templates being present. This pins the new contract:
- _send_email never raises and logs on failure (no silent swallow)
- /verify-email consumes a token then redirects
- /forgot-password never enumerates accounts
- /reset-password rejects weak/invalid input
- register wires welcome + verify (no `except: pass`)
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import kerf_auth.routes as auth


@pytest.fixture(autouse=True)
def _stub_rate_limit(monkeypatch):
    """Prevent rate_limit from hitting the DB pool in all tests here.

    The /forgot-password route now has a rate_limit dependency (R17).
    Stub enforce so tests remain hermetic.
    """
    import kerf_core.rate_limit as _rl_module
    monkeypatch.setattr(_rl_module, "enforce", AsyncMock(return_value=None))
    import kerf_core.db.connection as _conn_module
    monkeypatch.setattr(_conn_module, "get_pool_required", AsyncMock(return_value=MagicMock()))


def _app():
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    return app


def _fake_pool(conn):
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _conn():
    conn = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    return conn


# ---- _send_email must never raise, and must log on failure -------------

def test_send_email_swallows_then_logs(caplog):
    # Force the provider import/render path to blow up.
    with patch("kerf_cloud.email.templates.renderer") as r:
        r.render.side_effect = RuntimeError("provider boom")
        with caplog.at_level("WARNING"):
            auth._send_email("welcome", "a@b.com", {"Name": "A"})  # must not raise
    assert any("email send failed" in m for m in caplog.messages)


# ---- /verify-email -----------------------------------------------------

def test_verify_email_empty_token_redirects_invalid():
    with patch.object(auth, "_app_url", return_value="https://app.test"):
        c = TestClient(_app())
        r = c.get("/auth/verify-email", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://app.test/?verify=invalid"


def test_verify_email_valid_token_marks_verified_and_redirects():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value={"id": "tok-1", "user_id": "u-1"})
    with patch.object(auth, "_app_url", return_value="https://app.test"), \
         patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))):
        c = TestClient(_app())
        r = c.get("/auth/verify-email?token=raw", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://app.test/projects?verified=1"
    # users.email_verified set + token consumed.
    sqls = " ".join(str(call.args[0]) for call in conn.execute.await_args_list)
    assert "UPDATE users SET email_verified = true" in sqls
    assert "UPDATE email_tokens SET used_at = now()" in sqls


# ---- /forgot-password : no account enumeration -------------------------

def test_forgot_password_unknown_email_is_ok_and_silent():
    conn = _conn()
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(auth.users_queries, "get_user_by_email", AsyncMock(return_value=None)), \
         patch.object(auth, "_send_email") as send:
        c = TestClient(_app())
        r = c.post("/auth/forgot-password", json={"email": "nobody@x.com"})
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    send.assert_not_called()


def test_forgot_password_known_user_sends_reset():
    conn = _conn()
    conn.execute = AsyncMock()
    user = {"id": "u-1", "name": "Pat", "password_hash": "bcrypt$x"}
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(auth.users_queries, "get_user_by_email", AsyncMock(return_value=user)), \
         patch.object(auth, "_app_url", return_value="https://app.test"), \
         patch.object(auth, "_send_email") as send:
        c = TestClient(_app())
        r = c.post("/auth/forgot-password", json={"email": "pat@x.com"})
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    send.assert_called_once()
    assert send.call_args.args[0] == "password_reset"
    assert "/reset-password?token=" in send.call_args.args[2]["ResetURL"]


# ---- /reset-password : input validation --------------------------------

def test_reset_password_short_password_400():
    c = TestClient(_app())
    r = c.post("/auth/reset-password", json={"token": "t", "password": "short"})
    assert r.status_code == 400


def test_reset_password_invalid_token_400():
    conn = _conn()
    conn.fetchrow = AsyncMock(return_value=None)
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))):
        c = TestClient(_app())
        r = c.post("/auth/reset-password",
                   json={"token": "bad", "password": "longenough1"})
    assert r.status_code == 400


# ---- register wiring (source contract) ---------------------------------

def test_register_wires_welcome_and_verify_no_silent_swallow():
    import pathlib
    src = pathlib.Path(auth.__file__).read_text()
    i = src.index("async def register(")
    body = src[i:i + 3000]
    assert '_send_email("welcome"' in body
    assert '_send_email("verify_email"' in body
    assert "pass  # email failure must never fail registration" not in body
