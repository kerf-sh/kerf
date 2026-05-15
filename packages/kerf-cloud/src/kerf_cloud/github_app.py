"""GitHub App authentication helpers.

Provides:
  app_jwt()              — short-lived RS256 JWT signed with the App private key.
  installation_token()   — POST .../access_tokens with the app JWT, cached until
                           ~expiry (in-memory only; never persisted to DB).
  install_url()          — GitHub App installation URL for the repo-connect flow.

Security notes:
  - The private key is never logged or returned.
  - Installation tokens are short-lived (~1 h from GitHub). We cache them in
    memory with a 5-minute safety margin and re-mint on expiry.
  - Only the installation_id (a plain integer) is persisted to the database.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory token cache: installation_id -> (token_str, expiry_epoch_sec)
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_token_cache: dict[int, tuple[str, float]] = {}

# Refresh 5 minutes before actual expiry to avoid races.
_EXPIRY_MARGIN_SEC = 300


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def app_jwt(app_id: str, private_key_pem: str) -> str:
    """Return a short-lived RS256 JWT for authenticating as the GitHub App.

    Args:
        app_id: Numeric GitHub App ID (as string, from config).
        private_key_pem: RSA private key PEM text.

    Returns:
        Encoded JWT string.

    Raises:
        ValueError: if app_id or private_key_pem are empty.
        Exception: propagates jwt/cryptography errors.
    """
    if not app_id or not private_key_pem:
        raise ValueError("github_app: app_id and private_key_pem are required")

    import jwt  # pyjwt

    now = int(time.time())
    payload = {
        "iat": now - 60,   # issued 60 s ago to allow clock skew
        "exp": now + 540,  # 9 minutes (GitHub max is 10)
        "iss": app_id,
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


# ---------------------------------------------------------------------------
# Installation token
# ---------------------------------------------------------------------------

def _cached_token(installation_id: int) -> Optional[str]:
    """Return a cached token if still valid, else None."""
    with _cache_lock:
        entry = _token_cache.get(installation_id)
        if entry is None:
            return None
        token, expiry = entry
        if time.time() < expiry:
            return token
        del _token_cache[installation_id]
        return None


def _store_token(installation_id: int, token: str, expires_at: Optional[str]) -> None:
    """Cache a token until its GitHub-reported expiry minus the safety margin."""
    expiry = time.time() + 3600 - _EXPIRY_MARGIN_SEC  # fallback: ~55 min
    if expires_at:
        try:
            dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            expiry = dt.timestamp() - _EXPIRY_MARGIN_SEC
        except Exception:
            pass
    with _cache_lock:
        _token_cache[installation_id] = (token, expiry)


async def installation_token(
    installation_id: int,
    app_id: str,
    private_key_pem: str,
) -> str:
    """Mint (or return cached) an installation access token.

    Calls POST https://api.github.com/app/installations/{id}/access_tokens
    with a fresh App JWT as Bearer. Returns the short-lived token string.

    Raises:
        ValueError: if configuration is missing.
        httpx.HTTPStatusError: if the GitHub API returns an error.
    """
    cached = _cached_token(installation_id)
    if cached:
        return cached

    jwt_token = app_jwt(app_id, private_key_pem)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    token = data["token"]
    expires_at = data.get("expires_at")
    _store_token(installation_id, token, expires_at)
    return token


# ---------------------------------------------------------------------------
# Installation URL helper
# ---------------------------------------------------------------------------

def install_url(app_slug: str, state: str = "") -> str:
    """Return the GitHub App installation URL.

    If app_slug is set, uses the canonical /apps/<slug>/installations/new form.
    Otherwise falls back to a generic GitHub Apps URL (the user must have the
    slug configured).

    Args:
        app_slug: GitHub App slug (the URL-safe name, e.g. "kerf-app").
        state:    Optional opaque state string passed through the redirect.

    Returns:
        Full URL to redirect the user to for repo selection.
    """
    if not app_slug:
        raise ValueError("github_app: cloud_github_app_slug is required for install_url")
    base = f"https://github.com/apps/{app_slug}/installations/new"
    if state:
        return f"{base}?state={state}"
    return base


# ---------------------------------------------------------------------------
# Cache invalidation (for tests / revocation)
# ---------------------------------------------------------------------------

def invalidate_cache(installation_id: Optional[int] = None) -> None:
    """Remove one or all entries from the in-memory token cache."""
    with _cache_lock:
        if installation_id is None:
            _token_cache.clear()
        else:
            _token_cache.pop(installation_id, None)
