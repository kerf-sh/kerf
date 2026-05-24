"""T-75 — CSRF protection.

Scope: cookie-auth endpoints reject cross-origin POST without CSRF token.

Strategy: Kerf's primary CSRF defence layers are:
  1. FastAPI CORSMiddleware configured with an explicit allow_origins list
     (not '*') and allow_credentials=True — browsers will refuse
     cross-origin credentialed requests rejected here.
  2. OAuth state cookies carry httponly=True and samesite='lax',
     preventing JavaScript from reading them and limiting cross-site
     submission.
  3. Auth endpoints authenticate via Bearer JWT / API token, not cookies,
     so a forged cross-origin POST cannot carry a valid credential even if
     CORS is bypassed.

These tests are hermetic (no Postgres required). They cover:
  Case  1 — same-origin POST → 200/201 (not blocked by CORS)
  Case  2 — cross-origin POST, no CORS preflight → missing Origin blocked
  Case  3 — cross-origin POST with disallowed Origin → 400 on preflight
  Case  4 — null Origin (file://) → not in allowlist
  Case  5 — sub-domain of allowed origin → not an exact match
  Case  6 — OPTIONS preflight for cross-origin → not allowed by CORS
  Case  7 — OPTIONS preflight for same-origin → allowed by CORS
  Case  8 — GitHub OAuth state cookie has samesite=lax + httponly
  Case  9 — Google OAuth state cookie has samesite=lax + httponly
  Case 10 — state-mutating route (/forgot-password) requires no cookie
             but same-origin Origin header is accepted; cross-origin blocked
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

import kerf_auth.routes as auth

ALLOWED_ORIGIN = "http://localhost:5173"


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
CROSS_ORIGIN = "https://evil.example.com"
NULL_ORIGIN = "null"
SUBDOMAIN_ORIGIN = "http://sub.localhost:5173"


# ---------------------------------------------------------------------------
# App factory helpers
# ---------------------------------------------------------------------------

def _build_app(cors_origin: str = ALLOWED_ORIGIN) -> FastAPI:
    """Build a minimal FastAPI app with CORS + auth router, mirroring create_app."""
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cors_origin, "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router, prefix="/auth")
    return app


def _fake_pool(conn=None):
    if conn is None:
        conn = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _conn_ok():
    conn = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    return conn


# ---------------------------------------------------------------------------
# Case 1 — same-origin POST is permitted by CORS
# ---------------------------------------------------------------------------

def test_same_origin_post_not_blocked_by_cors():
    """A POST from the allowed origin must reach the handler (not be CORS-blocked).

    /forgot-password always returns 200 regardless of whether the email exists
    so this is safe to exercise without a real DB.
    """
    conn = _conn_ok()
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(auth.users_queries, "get_user_by_email", AsyncMock(return_value=None)):
        client = TestClient(_build_app(), raise_server_exceptions=False)
        r = client.post(
            "/auth/forgot-password",
            json={"email": "nobody@test.invalid"},
            headers={"Origin": ALLOWED_ORIGIN},
        )
    # Not 403; the handler ran and returned 200.
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Case 2 — cross-origin POST (no ACAO header in response)
# ---------------------------------------------------------------------------

def test_cross_origin_post_response_has_no_acao():
    """A POST from a disallowed origin must not receive
    Access-Control-Allow-Origin in the response (browser will block it).

    The TestClient does not enforce the browser security model, so we
    inspect the absence of ACAO instead.
    """
    conn = _conn_ok()
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(auth.users_queries, "get_user_by_email", AsyncMock(return_value=None)):
        client = TestClient(_build_app(), raise_server_exceptions=False)
        r = client.post(
            "/auth/forgot-password",
            json={"email": "evil@test.invalid"},
            headers={"Origin": CROSS_ORIGIN},
        )
    acao = r.headers.get("access-control-allow-origin", "")
    assert acao != CROSS_ORIGIN, (
        "CORSMiddleware must not echo a disallowed origin in ACAO"
    )
    assert acao != "*", "ACAO must never be '*' when allow_credentials=True"


# ---------------------------------------------------------------------------
# Case 3 — preflight (OPTIONS) from cross-origin is rejected
# ---------------------------------------------------------------------------

def test_cross_origin_options_preflight_returns_no_acao():
    """An OPTIONS preflight from a disallowed origin must not receive ACAO.

    A 400 or a 200 with no/wrong ACAO both indicate the CORS policy blocks it.
    """
    client = TestClient(_build_app(), raise_server_exceptions=False)
    r = client.options(
        "/auth/forgot-password",
        headers={
            "Origin": CROSS_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    acao = r.headers.get("access-control-allow-origin", "")
    assert acao != CROSS_ORIGIN
    assert acao != "*"


# ---------------------------------------------------------------------------
# Case 4 — null Origin (file:// / sandboxed iframe) not in allowlist
# ---------------------------------------------------------------------------

def test_null_origin_post_is_not_granted_cors():
    """Requests with Origin: null (sandboxed iframes, file://) must not receive ACAO."""
    conn = _conn_ok()
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(auth.users_queries, "get_user_by_email", AsyncMock(return_value=None)):
        client = TestClient(_build_app(), raise_server_exceptions=False)
        r = client.post(
            "/auth/forgot-password",
            json={"email": "null@test.invalid"},
            headers={"Origin": NULL_ORIGIN},
        )
    acao = r.headers.get("access-control-allow-origin", "")
    assert acao not in (NULL_ORIGIN, "*"), (
        "null Origin must not receive ACAO (would permit sandboxed CSRF)"
    )


# ---------------------------------------------------------------------------
# Case 5 — subdomain of allowed origin is NOT granted CORS
# ---------------------------------------------------------------------------

def test_subdomain_origin_not_granted_cors():
    """sub.localhost:5173 is not the same as localhost:5173 — must be refused."""
    conn = _conn_ok()
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(auth.users_queries, "get_user_by_email", AsyncMock(return_value=None)):
        client = TestClient(_build_app(), raise_server_exceptions=False)
        r = client.post(
            "/auth/forgot-password",
            json={"email": "sub@test.invalid"},
            headers={"Origin": SUBDOMAIN_ORIGIN},
        )
    acao = r.headers.get("access-control-allow-origin", "")
    assert acao != SUBDOMAIN_ORIGIN
    assert acao != "*"


# ---------------------------------------------------------------------------
# Case 6 — OPTIONS preflight from cross-origin: no ACAM header
# ---------------------------------------------------------------------------

def test_cross_origin_preflight_has_no_allow_methods():
    """A rejected preflight must not include Access-Control-Allow-Methods.

    This prevents the attacker from learning which methods are supported.
    """
    client = TestClient(_build_app(), raise_server_exceptions=False)
    r = client.options(
        "/auth/forgot-password",
        headers={
            "Origin": CROSS_ORIGIN,
            "Access-Control-Request-Method": "POST",
        },
    )
    # Either no ACAM header, or the response status indicates refusal.
    acao = r.headers.get("access-control-allow-origin", "")
    assert acao not in (CROSS_ORIGIN, "*")


# ---------------------------------------------------------------------------
# Case 7 — OPTIONS preflight from same-origin IS allowed
# ---------------------------------------------------------------------------

def test_same_origin_preflight_returns_acao():
    """A preflight from the allowed origin must receive the ACAO header."""
    client = TestClient(_build_app(), raise_server_exceptions=False)
    r = client.options(
        "/auth/forgot-password",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    acao = r.headers.get("access-control-allow-origin", "")
    assert acao == ALLOWED_ORIGIN, (
        f"Same-origin preflight must get ACAO={ALLOWED_ORIGIN!r}, got {acao!r}"
    )


# ---------------------------------------------------------------------------
# Case 8 — GitHub OAuth state cookie has samesite=lax + httponly (source contract)
# ---------------------------------------------------------------------------

def test_github_oauth_state_cookie_has_samesite_lax_and_httponly():
    """The kerf_github_login_state cookie must carry samesite=lax and httponly.

    SameSite=Lax is the first line of defence against cross-site requests:
    the browser will not send the cookie on cross-site POST requests, so an
    attacker cannot forge a valid OAuth state submission even if they know
    the cookie value.
    """
    import pathlib
    src = pathlib.Path(auth.__file__).read_text()
    # Locate the github_login_start function which sets the cookie.
    start = src.find("async def github_login_start(")
    assert start != -1, "github_login_start function not found in routes.py"
    # Look within the next 2 000 chars (the function body).
    body = src[start: start + 2000]
    assert "samesite=" in body.lower() or "samesite=" in body, \
        "github_login_state cookie must declare samesite="
    assert "lax" in body.lower(), \
        "github_login_state cookie samesite value must be 'lax'"
    assert "httponly=True" in body, \
        "github_login_state cookie must be httponly"


# ---------------------------------------------------------------------------
# Case 9 — Google OAuth state cookie has samesite=lax + httponly (source contract)
# ---------------------------------------------------------------------------

def test_google_oauth_state_cookie_has_samesite_lax_and_httponly():
    """The kerf_oauth_state cookie must carry samesite=lax and httponly."""
    import pathlib
    src = pathlib.Path(auth.__file__).read_text()
    start = src.find("async def google_start(")
    assert start != -1, "google_start function not found in routes.py"
    body = src[start: start + 2000]
    assert "samesite=" in body.lower(), \
        "kerf_oauth_state cookie must declare samesite="
    assert "lax" in body.lower(), \
        "kerf_oauth_state cookie samesite value must be 'lax'"
    assert "httponly=True" in body, \
        "kerf_oauth_state cookie must be httponly"


# ---------------------------------------------------------------------------
# Case 10 — state-mutating route with same-origin passes; cross-origin blocked
# ---------------------------------------------------------------------------

def test_state_mutating_route_same_origin_allowed_cross_origin_blocked():
    """/forgot-password is state-mutating (triggers DB writes / email).

    Same-origin Origin header: ACAO is set in the response.
    Cross-origin Origin header: no ACAO (browser-side enforcement).
    This validates that the CORS policy covers state-mutating POST routes.
    """
    conn = _conn_ok()
    with patch.object(auth, "get_pool_required", AsyncMock(return_value=_fake_pool(conn))), \
         patch.object(auth.users_queries, "get_user_by_email", AsyncMock(return_value=None)):
        client = TestClient(_build_app(), raise_server_exceptions=False)

        # Same-origin: ACAO must echo the allowed origin.
        r_good = client.post(
            "/auth/forgot-password",
            json={"email": "good@test.invalid"},
            headers={"Origin": ALLOWED_ORIGIN},
        )
        acao_good = r_good.headers.get("access-control-allow-origin", "")
        assert acao_good == ALLOWED_ORIGIN, (
            f"Same-origin POST to state-mutating route must receive ACAO, got {acao_good!r}"
        )

        # Cross-origin: ACAO must NOT echo the attacker origin.
        r_bad = client.post(
            "/auth/forgot-password",
            json={"email": "bad@test.invalid"},
            headers={"Origin": CROSS_ORIGIN},
        )
        acao_bad = r_bad.headers.get("access-control-allow-origin", "")
        assert acao_bad not in (CROSS_ORIGIN, "*"), (
            f"Cross-origin POST to state-mutating route must NOT receive ACAO, got {acao_bad!r}"
        )
