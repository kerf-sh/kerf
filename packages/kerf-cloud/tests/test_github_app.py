"""Hermetic tests for the GitHub App auth module and repo-connect flow.

Covers:
  - app_jwt(): produces a decodable RS256 JWT with correct iss/exp fields
  - installation_token(): calls the right endpoint with Bearer app-jwt,
    returns the token (mocked httpx)
  - /auth/github/start: redirects to GitHub App install URL
  - /auth/github/callback: persists installation_id; handles missing/bad params
  - Login flow (/auth/github/login/start) still 302s unchanged

No real network calls; no real DB; no .env files touched.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

# ---------------------------------------------------------------------------
# Generate a throwaway RSA key pair for tests
# ---------------------------------------------------------------------------

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_KEY_PEM = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
).decode()
_PRIVATE_KEY_B64 = base64.b64encode(_PRIVATE_KEY_PEM.encode()).decode()


# ---------------------------------------------------------------------------
# github_app module tests
# ---------------------------------------------------------------------------

class TestAppJwt:
    def test_produces_rs256_jwt_with_correct_iss(self):
        import jwt as pyjwt
        from kerf_cloud.github_app import app_jwt

        token = app_jwt(app_id="3727956", private_key_pem=_PRIVATE_KEY_PEM)
        assert isinstance(token, str)

        public_key = _PRIVATE_KEY.public_key()
        payload = pyjwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_exp": False},
        )
        assert payload["iss"] == "3727956"

    def test_exp_is_in_future(self):
        import jwt as pyjwt
        from kerf_cloud.github_app import app_jwt

        token = app_jwt(app_id="3727956", private_key_pem=_PRIVATE_KEY_PEM)
        public_key = _PRIVATE_KEY.public_key()
        payload = pyjwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_exp": False},
        )
        assert payload["exp"] > time.time()

    def test_exp_within_10_minutes(self):
        import jwt as pyjwt
        from kerf_cloud.github_app import app_jwt

        token = app_jwt(app_id="3727956", private_key_pem=_PRIVATE_KEY_PEM)
        public_key = _PRIVATE_KEY.public_key()
        payload = pyjwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_exp": False},
        )
        # Must expire within 10 minutes from now
        assert payload["exp"] <= time.time() + 610

    def test_raises_on_empty_app_id(self):
        from kerf_cloud.github_app import app_jwt
        with pytest.raises(ValueError):
            app_jwt(app_id="", private_key_pem=_PRIVATE_KEY_PEM)

    def test_raises_on_empty_private_key(self):
        from kerf_cloud.github_app import app_jwt
        with pytest.raises(ValueError):
            app_jwt(app_id="3727956", private_key_pem="")


class TestInstallationToken:
    """Tests for installation_token() — mocks httpx."""

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint_with_bearer_jwt(self):
        from kerf_cloud.github_app import installation_token, invalidate_cache

        invalidate_cache(12345)  # ensure no cached token

        captured = {}

        async def _fake_post(url, **kwargs):
            captured["url"] = url
            captured["auth_header"] = kwargs.get("headers", {}).get("Authorization", "")
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={
                "token": "ghs_test_installation_token",
                "expires_at": "2099-01-01T00:00:00Z",
            })
            return resp

        mock_client = AsyncMock()
        mock_client.post = _fake_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("kerf_cloud.github_app.httpx.AsyncClient", return_value=mock_client):
            token = await installation_token(
                installation_id=12345,
                app_id="3727956",
                private_key_pem=_PRIVATE_KEY_PEM,
            )

        assert token == "ghs_test_installation_token"
        assert "installations/12345/access_tokens" in captured["url"]
        assert captured["auth_header"].startswith("Bearer ")

    @pytest.mark.asyncio
    async def test_returns_cached_token_on_second_call(self):
        from kerf_cloud.github_app import installation_token, invalidate_cache

        invalidate_cache(99999)
        call_count = {"n": 0}

        async def _fake_post(url, **kwargs):
            call_count["n"] += 1
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={
                "token": "ghs_cached",
                "expires_at": "2099-01-01T00:00:00Z",
            })
            return resp

        mock_client = AsyncMock()
        mock_client.post = _fake_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("kerf_cloud.github_app.httpx.AsyncClient", return_value=mock_client):
            t1 = await installation_token(99999, "3727956", _PRIVATE_KEY_PEM)
            t2 = await installation_token(99999, "3727956", _PRIVATE_KEY_PEM)

        assert t1 == t2 == "ghs_cached"
        assert call_count["n"] == 1, "should only call GitHub once (second call should be cached)"


class TestInstallUrl:
    def test_includes_slug(self):
        from kerf_cloud.github_app import install_url

        url = install_url("kerf-app")
        assert "https://github.com/apps/kerf-app/installations/new" == url

    def test_includes_state(self):
        from kerf_cloud.github_app import install_url

        url = install_url("kerf-app", state="abc123")
        assert "state=abc123" in url

    def test_raises_on_empty_slug(self):
        from kerf_cloud.github_app import install_url
        with pytest.raises(ValueError):
            install_url("")


# ---------------------------------------------------------------------------
# Route-level tests
# ---------------------------------------------------------------------------

def _make_cloud_app():
    from fastapi import FastAPI
    from kerf_cloud.routes import github_oauth_router
    app = FastAPI()
    app.include_router(github_oauth_router, prefix="/auth")
    return app


FAKE_CLOUD_SETTINGS = MagicMock()
FAKE_CLOUD_SETTINGS.cloud_github_app_id = "3727956"
FAKE_CLOUD_SETTINGS.cloud_github_app_slug = "kerf-app"
FAKE_CLOUD_SETTINGS.github_private_key_pem = _PRIVATE_KEY_PEM
FAKE_CLOUD_SETTINGS.cloud_github_client_id = "Iv23_test"
FAKE_CLOUD_SETTINGS.cloud_github_client_secret = "secret"
FAKE_CLOUD_SETTINGS.cloud_github_redirect_url = "http://localhost:8080/auth/github/callback"
FAKE_CLOUD_SETTINGS.cors_origin = "http://localhost:5173"
FAKE_CLOUD_SETTINGS.jwt_secret = "test-jwt"


def _fake_require_auth():
    async def _dep():
        return {"sub": "00000000-0000-0000-0000-000000000001"}
    return _dep


def _loc_params(response):
    loc = response.headers["location"]
    parsed = urlparse(loc)
    return parsed, parse_qs(parsed.query)


def _make_pool(conn):
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


class TestGithubStartRoute:
    def setup_method(self):
        from fastapi import FastAPI
        from kerf_cloud import routes as cloud_routes
        from kerf_auth.routes import require_auth as _real_require_auth

        self._settings_patcher = patch("kerf_cloud.routes.settings", FAKE_CLOUD_SETTINGS)
        self._settings_patcher.start()

        app = FastAPI()
        # Override require_auth so we don't need a real JWT
        app.include_router(cloud_routes.github_oauth_router, prefix="/auth")

        # Patch require_auth dependency
        from kerf_cloud.routes import github_oauth_router
        from kerf_core.dependencies import require_auth
        app.dependency_overrides[require_auth] = _fake_require_auth()

        from fastapi.testclient import TestClient
        self.client = TestClient(app, follow_redirects=False)

    def teardown_method(self):
        self._settings_patcher.stop()

    def test_redirects_302_to_github_app_install(self):
        response = self.client.get("/auth/github/start")
        assert response.status_code == 302
        loc = response.headers["location"]
        assert "github.com/apps/kerf-app/installations/new" in loc

    def test_redirect_contains_state_param(self):
        response = self.client.get("/auth/github/start")
        _, params = _loc_params(response)
        assert "state" in params

    def test_sets_state_cookie(self):
        response = self.client.get("/auth/github/start")
        assert "kerf_github_oauth_state" in response.cookies

    def test_not_configured_returns_503_when_app_id_missing(self):
        unconfigured = MagicMock()
        unconfigured.cloud_github_app_id = ""
        unconfigured.github_private_key_pem = ""
        unconfigured.cloud_github_app_slug = "kerf-app"
        with patch("kerf_cloud.routes.settings", unconfigured):
            response = self.client.get("/auth/github/start")
        assert response.status_code == 503

    def test_not_configured_returns_503_when_slug_missing(self):
        unconfigured = MagicMock()
        unconfigured.cloud_github_app_id = "3727956"
        unconfigured.github_private_key_pem = _PRIVATE_KEY_PEM
        unconfigured.cloud_github_app_slug = ""
        with patch("kerf_cloud.routes.settings", unconfigured):
            response = self.client.get("/auth/github/start")
        assert response.status_code == 503


class TestGithubCallbackRoute:
    def setup_method(self):
        from fastapi import FastAPI
        from kerf_cloud import routes as cloud_routes
        from kerf_core.dependencies import require_auth

        self._settings_patcher = patch("kerf_cloud.routes.settings", FAKE_CLOUD_SETTINGS)
        self._settings_patcher.start()

        app = FastAPI()
        app.include_router(cloud_routes.github_oauth_router, prefix="/auth")
        app.dependency_overrides[require_auth] = _fake_require_auth()

        from fastapi.testclient import TestClient
        self.client = TestClient(app, follow_redirects=False)

    def teardown_method(self):
        self._settings_patcher.stop()

    def _get_state(self):
        r = self.client.get("/auth/github/start")
        assert r.status_code == 302
        _, params = _loc_params(r)
        return params["state"][0]

    def test_callback_persists_installation_id_and_redirects(self):
        state = self._get_state()

        conn = AsyncMock()
        conn.execute = AsyncMock()
        pool = _make_pool(conn)

        async def _fake_installation_token(installation_id, app_id, private_key_pem):
            return "ghs_fake_token"

        mock_gh_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = MagicMock(return_value={"login": "testuser"})
        mock_gh_client.get = AsyncMock(return_value=mock_resp)
        mock_gh_client.__aenter__ = AsyncMock(return_value=mock_gh_client)
        mock_gh_client.__aexit__ = AsyncMock(return_value=False)

        with patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=pool)), \
             patch("kerf_cloud.routes._gh_installation_token", _fake_installation_token), \
             patch("kerf_cloud.routes.httpx.AsyncClient", return_value=mock_gh_client), \
             patch("kerf_cloud.routes.encrypt_secret", return_value=b"fake_encrypted"):
            response = self.client.get(
                "/auth/github/callback",
                params={
                    "installation_id": "98765",
                    "setup_action": "install",
                    "state": state,
                },
                cookies={"kerf_github_oauth_state": state},
            )

        assert response.status_code == 302
        loc = response.headers["location"]
        assert "provider=github" in loc
        assert "error" not in loc

        # Verify installation_id was passed to the DB execute call
        conn.execute.assert_called_once()
        call_args = conn.execute.call_args[0]
        # The 6th positional arg ($5) is the installation_id
        assert 98765 in call_args

    def test_callback_missing_installation_id_redirects_with_error(self):
        state = self._get_state()

        response = self.client.get(
            "/auth/github/callback",
            params={"state": state},  # no installation_id
            cookies={"kerf_github_oauth_state": state},
        )

        assert response.status_code == 302
        assert "error=no_installation" in response.headers["location"]

    def test_callback_bad_state_raises_400(self):
        response = self.client.get(
            "/auth/github/callback",
            params={"installation_id": "1234", "state": "wrong_state"},
            cookies={"kerf_github_oauth_state": "different_state"},
        )
        assert response.status_code == 400

    def test_not_configured_returns_503(self):
        unconfigured = MagicMock()
        unconfigured.cloud_github_app_id = ""
        unconfigured.github_private_key_pem = ""
        with patch("kerf_cloud.routes.settings", unconfigured):
            response = self.client.get(
                "/auth/github/callback",
                params={"installation_id": "1234", "state": "s"},
                cookies={"kerf_github_oauth_state": "s"},
            )
        assert response.status_code == 503


# ---------------------------------------------------------------------------
# Login flow regression: /auth/github/login/start still 302s unchanged
# ---------------------------------------------------------------------------

class TestLoginFlowUnchanged:
    """Verify the login flow (kerf-auth) still 302s to GitHub OAuth."""

    def setup_method(self):
        from fastapi import FastAPI
        from kerf_auth.routes import router as auth_router

        FAKE_AUTH_SETTINGS = MagicMock()
        FAKE_AUTH_SETTINGS.cloud_github_client_id = "Iv23_login_test"
        FAKE_AUTH_SETTINGS.cloud_github_client_secret = "login_secret"
        FAKE_AUTH_SETTINGS.cloud_github_redirect_url = "http://localhost:8080/auth/github/callback"
        FAKE_AUTH_SETTINGS.cors_origin = "http://localhost:5173"

        self._patcher = patch("kerf_auth.routes.settings", FAKE_AUTH_SETTINGS)
        self._patcher.start()

        app = FastAPI()
        app.include_router(auth_router, prefix="/auth")

        from fastapi.testclient import TestClient
        self.client = TestClient(app, follow_redirects=False)

    def teardown_method(self):
        self._patcher.stop()

    def test_login_start_still_302s_to_github_oauth(self):
        response = self.client.get("/auth/github/login/start")
        assert response.status_code == 302
        loc = response.headers["location"]
        # Login uses the OAuth web flow, not the App installation URL
        assert loc.startswith("https://github.com/login/oauth/authorize")

    def test_login_start_scope_is_read_user_email(self):
        response = self.client.get("/auth/github/login/start")
        _, params = _loc_params(response)
        scope = params.get("scope", [""])[0]
        assert "read:user" in scope
        assert "user:email" in scope

    def test_login_start_not_scope_repo(self):
        response = self.client.get("/auth/github/login/start")
        _, params = _loc_params(response)
        scope = params.get("scope", [""])[0]
        # Must NOT request repo scope (that's the old connect flow)
        assert "repo" not in scope.split(",")
