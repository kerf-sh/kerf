"""Hermetic tests for the GitHub login (Sign in with GitHub) routes.

Tests cover:
  - /auth/github/login/start: 302 to GitHub with correct params + state cookie
  - /auth/github/login/callback: creates/finds user, issues session, redirects
  - /auth/github/login/callback: bad/missing state -> error redirect (not 500)
  - /auth/github/login/callback: GitHub access_denied -> error redirect

GitHub API calls are mocked via httpx.MockTransport; no real network calls.
Database calls are mocked via monkeypatching kerf_core.db.connection.
"""
import asyncio
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

def _make_app(settings_overrides=None):
    """Build a minimal FastAPI app with only the kerf-auth router."""
    from kerf_auth.routes import router as auth_router

    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    return app


# ---------------------------------------------------------------------------
# Settings mock — avoids touching .env / real secrets
# ---------------------------------------------------------------------------

FAKE_SETTINGS = MagicMock()
FAKE_SETTINGS.cloud_github_client_id = "Iv1.test_client_id"
FAKE_SETTINGS.cloud_github_client_secret = "test_secret"
FAKE_SETTINGS.cloud_github_redirect_url = "http://localhost:8080/auth/github/callback"
FAKE_SETTINGS.google_client_id = ""
FAKE_SETTINGS.google_client_secret = ""
FAKE_SETTINGS.google_redirect_url = "http://localhost:8080/auth/google/callback"
FAKE_SETTINGS.cors_origin = "http://localhost:5173"
FAKE_SETTINGS.jwt_secret = "test-jwt-secret"
FAKE_SETTINGS.jwt_access_ttl_minutes = 15
FAKE_SETTINGS.jwt_refresh_ttl_days = 30
FAKE_SETTINGS.password_pepper = "test-pepper"
FAKE_SETTINGS.local_mode = False

# ---------------------------------------------------------------------------
# DB pool mock helpers
# ---------------------------------------------------------------------------

def _mock_conn(user_row=None):
    """Return a mock asyncpg connection."""
    conn = AsyncMock()
    # fetchrow returns a dict-like row; the real code calls dict(row)
    conn.fetchrow = AsyncMock(return_value=user_row)
    conn.execute = AsyncMock()
    return conn


def _make_pool(conn):
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


import datetime as _dt

FAKE_USER_ROW = {
    "id": "00000000-0000-0000-0000-000000000001",
    "email": "hub@example.com",
    "name": "Hub User",
    "avatar_url": "https://avatars.githubusercontent.com/u/1",
    "account_role": "user",
    "is_system": False,
    "created_at": _dt.datetime(2024, 1, 1),
}

FAKE_WORKSPACE_ROW = {
    "id": "00000000-0000-0000-0000-000000000002",
    "slug": "personal-00000000-abcd1234",
    "name": "Hub User",
    "avatar_url": None,
    "created_at": _dt.datetime(2024, 1, 1),
    "created_by": "00000000-0000-0000-0000-000000000001",
    "avatar_storage_key": None,
}

FAKE_RT_ROW = {
    "id": "00000000-0000-0000-0000-000000000003",
    "user_id": "00000000-0000-0000-0000-000000000001",
    "token_hash": "fakehash",
    "expires_at": _dt.datetime(2024, 2, 1),
    "revoked_at": None,
    "created_at": _dt.datetime(2024, 1, 1),
}

# ---------------------------------------------------------------------------
# httpx mock helpers for GitHub API
# ---------------------------------------------------------------------------

def _make_response(status_code, data):
    """Build a minimal response mock that behaves like httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=data)
    return resp


def _gh_token_response(access_token="ghu_test_token"):
    return _make_response(200, {"access_token": access_token, "scope": "read:user,user:email"})


def _gh_user_response():
    return _make_response(200, {
        "id": 12345,
        "login": "hubuser",
        "name": "Hub User",
        "avatar_url": "https://avatars.githubusercontent.com/u/1",
    })


def _gh_emails_response(email="hub@example.com", primary=True, verified=True):
    return _make_response(200, [
        {"email": email, "primary": primary, "verified": verified},
    ])


# ---------------------------------------------------------------------------
# Helper: extract query params from a Location URL
# ---------------------------------------------------------------------------

def _loc_params(response):
    loc = response.headers["location"]
    parsed = urlparse(loc)
    return parsed, parse_qs(parsed.query)


# ===========================================================================
# Tests: /auth/github/login/start
# ===========================================================================

class TestGithubLoginStart:
    def setup_method(self):
        patcher = patch("kerf_auth.routes.settings", FAKE_SETTINGS)
        patcher.start()
        self._patcher = patcher
        self.app = _make_app()
        self.client = TestClient(self.app, follow_redirects=False)

    def teardown_method(self):
        self._patcher.stop()

    def test_redirects_302_to_github(self):
        response = self.client.get("/auth/github/login/start")
        assert response.status_code == 302
        loc = response.headers["location"]
        assert loc.startswith("https://github.com/login/oauth/authorize")

    def test_redirect_contains_client_id(self):
        response = self.client.get("/auth/github/login/start")
        _, params = _loc_params(response)
        assert params["client_id"][0] == "Iv1.test_client_id"

    def test_redirect_scope_is_read_user_email(self):
        response = self.client.get("/auth/github/login/start")
        _, params = _loc_params(response)
        scope = params["scope"][0]
        assert "read:user" in scope
        assert "user:email" in scope

    def test_redirect_contains_state(self):
        response = self.client.get("/auth/github/login/start")
        _, params = _loc_params(response)
        assert "state" in params
        assert len(params["state"][0]) > 8

    def test_sets_state_cookie_with_max_age(self):
        response = self.client.get("/auth/github/login/start")
        assert "kerf_github_login_state" in response.cookies
        # Verify the Set-Cookie header has max-age (not maxage)
        raw_headers = response.headers.get_list("set-cookie") if hasattr(response.headers, "get_list") else [
            v for k, v in response.headers.items() if k.lower() == "set-cookie"
        ]
        cookie_header = " ".join(raw_headers).lower()
        assert "max-age" in cookie_header
        assert "httponly" in cookie_header

    def test_state_cookie_value_matches_url_state(self):
        response = self.client.get("/auth/github/login/start")
        _, params = _loc_params(response)
        url_state = params["state"][0]
        cookie_state = response.cookies["kerf_github_login_state"]
        assert url_state == cookie_state

    def test_redirect_uri_points_to_login_callback(self):
        response = self.client.get("/auth/github/login/start")
        _, params = _loc_params(response)
        redirect_uri = params["redirect_uri"][0]
        assert "/auth/github/login/callback" in redirect_uri

    def test_not_configured_returns_503(self):
        unconfigured = MagicMock()
        unconfigured.cloud_github_client_id = ""
        unconfigured.cloud_github_client_secret = ""
        with patch("kerf_auth.routes.settings", unconfigured):
            response = self.client.get("/auth/github/login/start")
        assert response.status_code == 503


# ===========================================================================
# Tests: /auth/github/login/callback — happy path
# ===========================================================================

class TestGithubLoginCallback:
    def setup_method(self):
        self._settings_patcher = patch("kerf_auth.routes.settings", FAKE_SETTINGS)
        self._settings_patcher.start()
        self.app = _make_app()
        self.client = TestClient(self.app, follow_redirects=False)

    def teardown_method(self):
        self._settings_patcher.stop()

    def _start_and_extract_state(self):
        r = self.client.get("/auth/github/login/start")
        assert r.status_code == 302
        _, params = _loc_params(r)
        return params["state"][0]

    def _make_async_client_mock(self, token_resp=None, user_resp=None, emails_resp=None):
        """
        Return a context-manager compatible mock for httpx.AsyncClient.

        The callback uses two separate ``async with httpx.AsyncClient() as
        client:`` blocks:
          1. POST access_token
          2. GET /user  +  GET /user/emails  (via asyncio.gather)

        We keep a call counter so the first __aenter__ returns a post mock
        and the second returns a get mock.
        """
        token = token_resp or _gh_token_response()
        user = user_resp or _gh_user_response()
        emails = emails_resp or _gh_emails_response()

        # --- client for the token POST ---
        post_client = AsyncMock()
        post_client.post = AsyncMock(return_value=token)

        # --- client for the user/emails GETs ---
        get_client = AsyncMock()
        get_client.get = AsyncMock(side_effect=[user, emails])

        call_count = {"n": 0}

        class _CM:
            async def __aenter__(self_):
                n = call_count["n"]
                call_count["n"] += 1
                return post_client if n == 0 else get_client

            async def __aexit__(self_, *args):
                return False

        def _factory(**kw):
            return _CM()

        return _factory

    def test_happy_path_creates_session_and_redirects(self):
        state = self._start_and_extract_state()

        conn = _mock_conn()
        # fetchrow sequence for "new user, new workspace" path:
        #   1. UPDATE by github_id → None (not found)
        #   2. UPDATE by email → None (not found)
        #   3. INSERT user → FAKE_USER_ROW
        #   4. INSERT workspace (create_workspace) → FAKE_WORKSPACE_ROW
        #   5. INSERT workspace_member (add_workspace_member) → some row
        #   6. INSERT refresh_token (create_refresh_token) → FAKE_RT_ROW
        fake_member_row = {"workspace_id": "ws-id", "user_id": "user-id", "role": "owner"}
        conn.fetchrow = AsyncMock(
            side_effect=[None, None, FAKE_USER_ROW, FAKE_WORKSPACE_ROW, fake_member_row, FAKE_RT_ROW]
        )
        pool = _make_pool(conn)

        with patch("kerf_auth.routes.get_pool_required", AsyncMock(return_value=pool)), \
             patch("kerf_auth.routes.httpx.AsyncClient", self._make_async_client_mock()):
            response = self.client.get(
                "/auth/github/login/callback",
                params={"code": "test_code", "state": state},
                cookies={"kerf_github_login_state": state},
            )

        assert response.status_code == 302
        loc = response.headers["location"]
        assert loc.startswith("http://localhost:5173/auth/callback")
        parsed, params = _loc_params(response)
        assert "access_token" in params
        assert "refresh_token" in params

    def test_existing_user_by_github_id_gets_session(self):
        state = self._start_and_extract_state()

        conn = _mock_conn()
        # fetchrow sequence for "existing user by github_id":
        #   1. UPDATE by github_id → FAKE_USER_ROW (found)
        #   2. INSERT refresh_token → FAKE_RT_ROW
        conn.fetchrow = AsyncMock(side_effect=[FAKE_USER_ROW, FAKE_RT_ROW])
        pool = _make_pool(conn)

        with patch("kerf_auth.routes.get_pool_required", AsyncMock(return_value=pool)), \
             patch("kerf_auth.routes.httpx.AsyncClient", self._make_async_client_mock()):
            response = self.client.get(
                "/auth/github/login/callback",
                params={"code": "test_code", "state": state},
                cookies={"kerf_github_login_state": state},
            )

        assert response.status_code == 302
        assert "access_token" in response.headers["location"]

    def test_existing_user_by_email_gets_session(self):
        state = self._start_and_extract_state()

        conn = _mock_conn()
        # fetchrow sequence for "existing user by email" path:
        #   1. UPDATE by github_id → None
        #   2. UPDATE by email → FAKE_USER_ROW (found)
        #   3. INSERT refresh_token → FAKE_RT_ROW
        conn.fetchrow = AsyncMock(side_effect=[None, FAKE_USER_ROW, FAKE_RT_ROW])
        pool = _make_pool(conn)

        with patch("kerf_auth.routes.get_pool_required", AsyncMock(return_value=pool)), \
             patch("kerf_auth.routes.httpx.AsyncClient", self._make_async_client_mock()):
            response = self.client.get(
                "/auth/github/login/callback",
                params={"code": "test_code", "state": state},
                cookies={"kerf_github_login_state": state},
            )

        assert response.status_code == 302
        assert "access_token" in response.headers["location"]


# ===========================================================================
# Tests: /auth/github/login/callback — error / bad state paths
# ===========================================================================

class TestGithubLoginCallbackErrors:
    def setup_method(self):
        self._patcher = patch("kerf_auth.routes.settings", FAKE_SETTINGS)
        self._patcher.start()
        self.app = _make_app()
        self.client = TestClient(self.app, follow_redirects=False)

    def teardown_method(self):
        self._patcher.stop()

    def test_missing_state_cookie_redirects_with_error(self):
        # state in URL but no cookie -> state mismatch
        response = self.client.get(
            "/auth/github/login/callback",
            params={"code": "test_code", "state": "some_state"},
            # no cookie set
        )
        assert response.status_code == 302
        assert "error=" in response.headers["location"]
        assert "500" not in response.headers["location"]

    def test_state_mismatch_redirects_with_error_not_500(self):
        r = self.client.get("/auth/github/login/start")
        _, params = _loc_params(r)
        real_state = params["state"][0]

        response = self.client.get(
            "/auth/github/login/callback",
            params={"code": "test_code", "state": "WRONG_STATE"},
            cookies={"kerf_github_login_state": real_state},
        )
        assert response.status_code == 302
        loc = response.headers["location"]
        assert "error=" in loc
        assert "500" not in loc

    def test_access_denied_redirects_with_github_denied(self):
        r = self.client.get("/auth/github/login/start")
        _, params = _loc_params(r)
        state = params["state"][0]

        response = self.client.get(
            "/auth/github/login/callback",
            params={"error": "access_denied", "state": state},
            cookies={"kerf_github_login_state": state},
        )
        assert response.status_code == 302
        loc = response.headers["location"]
        assert "github_denied" in loc

    def test_missing_code_redirects_with_error(self):
        r = self.client.get("/auth/github/login/start")
        _, params = _loc_params(r)
        state = params["state"][0]

        response = self.client.get(
            "/auth/github/login/callback",
            params={"state": state},  # no code
            cookies={"kerf_github_login_state": state},
        )
        assert response.status_code == 302
        assert "error=" in response.headers["location"]

    def test_not_configured_returns_503(self):
        unconfigured = MagicMock()
        unconfigured.cloud_github_client_id = ""
        unconfigured.cloud_github_client_secret = ""
        unconfigured.cors_origin = "http://localhost:5173"
        with patch("kerf_auth.routes.settings", unconfigured):
            response = self.client.get(
                "/auth/github/login/callback",
                params={"code": "x", "state": "y"},
            )
        assert response.status_code == 503
