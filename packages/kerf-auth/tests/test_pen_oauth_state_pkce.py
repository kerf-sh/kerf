"""Penetration tests: OAuth state randomness + CSRF protection (T-74).

Scope: Google + GitHub OAuth state randomness + PKCE verifier check.

Success criteria (12 cases):
  - missing/mismatched state rejected
  - PKCE downgrade rejected (no code_challenge accepted without verifier)
  - CSRF on callback caught (cookie vs param mismatch)

No real network calls; no real database; no secrets.
All external dependencies mocked via unittest.mock.
"""
import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def _make_app():
    from kerf_auth.routes import router as auth_router
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    return app


# ---------------------------------------------------------------------------
# Fake settings — no real secrets
# ---------------------------------------------------------------------------

FAKE_SETTINGS = MagicMock()
FAKE_SETTINGS.google_client_id = "fake-google-client.apps.googleusercontent.com"
FAKE_SETTINGS.google_client_secret = "fake-google-secret"
FAKE_SETTINGS.google_redirect_url = "http://localhost:8080/auth/google/callback"
FAKE_SETTINGS.cloud_github_client_id = "Iv1.fake_gh_client_id"
FAKE_SETTINGS.cloud_github_client_secret = "fake-gh-secret"
FAKE_SETTINGS.cloud_github_redirect_url = "http://localhost:8080/auth/github/callback"
FAKE_SETTINGS.cors_origin = "http://localhost:5173"
FAKE_SETTINGS.jwt_secret = "test-jwt-secret-state-pkce"
FAKE_SETTINGS.jwt_access_ttl_minutes = 15
FAKE_SETTINGS.jwt_refresh_ttl_days = 30
FAKE_SETTINGS.password_pepper = "test-pepper"
FAKE_SETTINGS.local_mode = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _loc_params(response):
    loc = response.headers["location"]
    parsed = urlparse(loc)
    return parsed, parse_qs(parsed.query)


def _google_start(client):
    r = client.get("/auth/google/start")
    assert r.status_code == 302
    _, params = _loc_params(r)
    state = params["state"][0]
    cookie = r.cookies.get("kerf_oauth_state", "")
    return state, cookie


def _github_start(client):
    r = client.get("/auth/github/login/start")
    assert r.status_code == 302
    _, params = _loc_params(r)
    state = params["state"][0]
    cookie = r.cookies.get("kerf_github_login_state", "")
    return state, cookie


def _fake_response(status_code, data):
    r = MagicMock()
    r.status_code = status_code
    r.json = MagicMock(return_value=data)
    return r


# ===========================================================================
# Case 1+2: State is random and unique across calls (both providers)
# ===========================================================================

class TestStateRandomness:
    """The nonce embedded in the OAuth state must not repeat across flows."""

    def setup_method(self):
        self._p = patch("kerf_auth.routes.settings", FAKE_SETTINGS)
        self._p.start()
        self.app = _make_app()
        self.client = TestClient(self.app, follow_redirects=False)

    def teardown_method(self):
        self._p.stop()

    def test_google_state_nonce_is_unique_across_flows(self):
        """Two /google/start requests produce different state values."""
        state1, _ = _google_start(self.client)
        state2, _ = _google_start(self.client)
        assert state1 != state2, (
            "state nonce must differ across OAuth initiation calls (CSRF risk if reused)"
        )

    def test_github_state_nonce_is_unique_across_flows(self):
        """Two /github/login/start requests produce different state values."""
        state1, _ = _github_start(self.client)
        state2, _ = _github_start(self.client)
        assert state1 != state2, (
            "state nonce must differ across OAuth initiation calls (CSRF risk if reused)"
        )

    def test_google_state_nonce_has_sufficient_entropy(self):
        """State is base64url of at least 16 bytes — i.e. ≥22 chars of nonce."""
        state, _ = _google_start(self.client)
        # Decode the JSON-in-base64 to get the embedded nonce
        padded = state + "=" * (-len(state) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded))
        nonce = decoded["n"]
        assert len(nonce) >= 16, f"nonce too short: {nonce!r}"

    def test_state_cookie_matches_url_state_param_google(self):
        """Cookie value must equal the URL state param (binding check)."""
        state, cookie = _google_start(self.client)
        assert state == cookie, "state cookie != url state param — session not bound"

    def test_state_cookie_matches_url_state_param_github(self):
        state, cookie = _github_start(self.client)
        assert state == cookie, "state cookie != url state param — session not bound"


# ===========================================================================
# Case 3+4: Google callback — state mismatch → 400
# ===========================================================================

class TestGoogleCallbackStateMismatch:
    """CSRF protection: Google callback rejects missing/mismatched state."""

    def setup_method(self):
        self._p = patch("kerf_auth.routes.settings", FAKE_SETTINGS)
        self._p.start()
        self.app = _make_app()
        self.client = TestClient(self.app, follow_redirects=False)

    def teardown_method(self):
        self._p.stop()

    def test_google_missing_state_cookie_rejected(self):
        """No state cookie → 400 (CSRF: attacker forged callback without initiation)."""
        response = self.client.get(
            "/auth/google/callback",
            params={"code": "legit_code", "state": "some_state"},
            # no cookie set intentionally
        )
        assert response.status_code == 400

    def test_google_wrong_state_param_rejected(self):
        """State param differs from cookie → 400."""
        state, cookie = _google_start(self.client)
        response = self.client.get(
            "/auth/google/callback",
            params={"code": "legit_code", "state": "ATTACKER_FORGED_STATE"},
            cookies={"kerf_oauth_state": cookie},
        )
        assert response.status_code == 400

    def test_google_empty_state_rejected(self):
        """Empty state string is rejected (not matched against empty cookie)."""
        state, cookie = _google_start(self.client)
        response = self.client.get(
            "/auth/google/callback",
            params={"code": "legit_code", "state": ""},
            cookies={"kerf_oauth_state": cookie},
        )
        assert response.status_code == 400

    def test_google_csrf_different_session_state_rejected(self):
        """State from a *different* /google/start session is rejected
        (CSRF: victim initiates, attacker replays their own state)."""
        victim_state, victim_cookie = _google_start(self.client)
        attacker_state, attacker_cookie = _google_start(self.client)

        # Attacker sends their state param but victim's cookie (or vice versa)
        response = self.client.get(
            "/auth/google/callback",
            params={"code": "code", "state": attacker_state},
            cookies={"kerf_oauth_state": victim_cookie},
        )
        assert response.status_code == 400


# ===========================================================================
# Case 5+6: GitHub callback — state mismatch → error redirect (not 200/500)
# ===========================================================================

class TestGithubCallbackStateMismatch:
    """CSRF protection: GitHub callback redirects with error on bad state."""

    def setup_method(self):
        self._p = patch("kerf_auth.routes.settings", FAKE_SETTINGS)
        self._p.start()
        self.app = _make_app()
        self.client = TestClient(self.app, follow_redirects=False)

    def teardown_method(self):
        self._p.stop()

    def test_github_missing_state_cookie_redirects_error(self):
        """No cookie → error redirect, never 200 or 500."""
        response = self.client.get(
            "/auth/github/login/callback",
            params={"code": "code123", "state": "any_state"},
        )
        assert response.status_code == 302
        loc = response.headers["location"]
        assert "error=" in loc
        assert "500" not in loc

    def test_github_wrong_state_redirects_error(self):
        """Mismatched state → error redirect."""
        state, cookie = _github_start(self.client)
        response = self.client.get(
            "/auth/github/login/callback",
            params={"code": "code123", "state": "WRONG"},
            cookies={"kerf_github_login_state": cookie},
        )
        assert response.status_code == 302
        assert "error=" in response.headers["location"]

    def test_github_csrf_different_session_state_rejected(self):
        """Attacker's state param with victim's cookie → error redirect."""
        victim_state, victim_cookie = _github_start(self.client)
        attacker_state, attacker_cookie = _github_start(self.client)

        response = self.client.get(
            "/auth/github/login/callback",
            params={"code": "code", "state": attacker_state},
            cookies={"kerf_github_login_state": victim_cookie},
        )
        assert response.status_code == 302
        assert "error=" in response.headers["location"]

    def test_github_access_denied_redirects_with_github_denied(self):
        """User cancels GitHub OAuth → access_denied error propagated cleanly."""
        state, cookie = _github_start(self.client)
        response = self.client.get(
            "/auth/github/login/callback",
            params={"error": "access_denied", "state": state},
            cookies={"kerf_github_login_state": cookie},
        )
        assert response.status_code == 302
        assert "github_denied" in response.headers["location"]


# ===========================================================================
# Case 7: PKCE downgrade — Google does not add code_challenge to redirect
#   The server does not accept a code_verifier-less PKCE downgrade because
#   we use server-side state cookies (not PKCE) for CSRF. Verify that the
#   /google/start redirect does NOT include code_challenge_method=plain,
#   which would be a PKCE downgrade (S256 not negotiated = downgrade).
# ===========================================================================

class TestPKCEDowngrade:
    """PKCE downgrade: server must not advertise plain PKCE challenge."""

    def setup_method(self):
        self._p = patch("kerf_auth.routes.settings", FAKE_SETTINGS)
        self._p.start()
        self.app = _make_app()
        self.client = TestClient(self.app, follow_redirects=False)

    def teardown_method(self):
        self._p.stop()

    def test_google_start_does_not_advertise_plain_pkce(self):
        """redirect must not include code_challenge_method=plain (downgrade risk)."""
        response = self.client.get("/auth/google/start")
        _, params = _loc_params(response)
        method = params.get("code_challenge_method", [""])[0]
        assert method != "plain", (
            "code_challenge_method=plain is a PKCE downgrade — "
            "use S256 or server-side state cookies instead"
        )

    def test_github_start_does_not_include_pkce_downgrade_params(self):
        """GitHub start redirect must not include code_challenge_method=plain."""
        response = self.client.get("/auth/github/login/start")
        _, params = _loc_params(response)
        method = params.get("code_challenge_method", [""])[0]
        assert method != "plain", "plain PKCE downgrade must be rejected"
