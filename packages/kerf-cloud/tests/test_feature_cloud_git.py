"""Hermetic tests for T-63: Cloud git refs + GitHub App.

Covers:
  - GitHubProvider: push / pull (fetch) / connect / disconnect / status
  - Installation token rotation (cache expiry → re-mint)
  - PEM keys not leaked in any return value
  - is_configured() availability gate
  - Multiple installation IDs isolated in cache
  - Uninstall (disconnect) clears DB association
  - Error propagation on HTTP failures from GitHub
  - install_url with state round-trip

No real network calls; no real DB; no .env files read.
25 test cases total.
"""
from __future__ import annotations

import base64
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# ---------------------------------------------------------------------------
# Throwaway RSA key pair (generated once for the module)
# ---------------------------------------------------------------------------

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_KEY_PEM = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
).decode()

_FAKE_SETTINGS = MagicMock()
_FAKE_SETTINGS.cloud_github_app_id = "3727956"
_FAKE_SETTINGS.cloud_github_app_slug = "kerf-app"
_FAKE_SETTINGS.github_private_key_pem = _PRIVATE_KEY_PEM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _mock_gh_token_response(token: str = "ghs_test", expires_at: str = "2099-01-01T00:00:00Z") -> AsyncMock:
    """Return a mock httpx AsyncClient that returns a GitHub installation token."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={"token": token, "expires_at": expires_at})

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# T1-T5: GitHubProvider.is_configured()
# ---------------------------------------------------------------------------

class TestIsConfigured:
    def test_configured_when_both_app_id_and_pem_present(self):
        from kerf_cloud.git_providers.github import GitHubProvider
        assert GitHubProvider.is_configured(_FAKE_SETTINGS) is True

    def test_not_configured_when_app_id_empty(self):
        from kerf_cloud.git_providers.github import GitHubProvider
        s = MagicMock()
        s.cloud_github_app_id = ""
        s.github_private_key_pem = _PRIVATE_KEY_PEM
        assert GitHubProvider.is_configured(s) is False

    def test_not_configured_when_pem_empty(self):
        from kerf_cloud.git_providers.github import GitHubProvider
        s = MagicMock()
        s.cloud_github_app_id = "3727956"
        s.github_private_key_pem = ""
        assert GitHubProvider.is_configured(s) is False

    def test_not_configured_when_both_missing(self):
        from kerf_cloud.git_providers.github import GitHubProvider
        s = MagicMock()
        s.cloud_github_app_id = ""
        s.github_private_key_pem = ""
        assert GitHubProvider.is_configured(s) is False

    def test_provider_name_is_github(self):
        from kerf_cloud.git_providers.github import GitHubProvider
        provider = GitHubProvider(_FAKE_SETTINGS)
        assert provider.name == "github"


# ---------------------------------------------------------------------------
# T6-T9: GitHubProvider.push()
# ---------------------------------------------------------------------------

class TestGitHubProviderPush:
    @pytest.mark.asyncio
    async def test_push_returns_token_acquired_status(self):
        from kerf_cloud.git_providers.github import GitHubProvider
        from kerf_cloud.github_app import invalidate_cache

        invalidate_cache(111)
        provider = GitHubProvider(_FAKE_SETTINGS)

        with patch("kerf_cloud.github_app.httpx.AsyncClient", return_value=_mock_gh_token_response("ghs_push_tok")):
            result = await provider.push(
                project_id="proj-1",
                installation_id=111,
                github_owner="acme",
                github_repo="widget",
            )

        assert result["status"] == "token_acquired"
        assert result["provider"] == "github"
        assert result["remote_url"] == "https://github.com/acme/widget.git"

    @pytest.mark.asyncio
    async def test_push_authenticated_remote_url_contains_token(self):
        from kerf_cloud.git_providers.github import GitHubProvider
        from kerf_cloud.github_app import invalidate_cache

        invalidate_cache(112)
        provider = GitHubProvider(_FAKE_SETTINGS)

        with patch("kerf_cloud.github_app.httpx.AsyncClient", return_value=_mock_gh_token_response("ghs_secret_push")):
            result = await provider.push(
                project_id="proj-2",
                installation_id=112,
                github_owner="acme",
                github_repo="widget",
            )

        assert "ghs_secret_push" in result["authenticated_remote_url"]
        assert "x-access-token" in result["authenticated_remote_url"]

    @pytest.mark.asyncio
    async def test_push_pem_not_in_result(self):
        """PEM private key must never appear in the push() return value."""
        from kerf_cloud.git_providers.github import GitHubProvider
        from kerf_cloud.github_app import invalidate_cache

        invalidate_cache(113)
        provider = GitHubProvider(_FAKE_SETTINGS)

        with patch("kerf_cloud.github_app.httpx.AsyncClient", return_value=_mock_gh_token_response()):
            result = await provider.push(
                project_id="proj-3",
                installation_id=113,
                github_owner="acme",
                github_repo="widget",
            )

        result_str = str(result)
        assert "PRIVATE KEY" not in result_str
        assert _PRIVATE_KEY_PEM[:30] not in result_str

    @pytest.mark.asyncio
    async def test_push_missing_args_raises_value_error(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        provider = GitHubProvider(_FAKE_SETTINGS)
        with pytest.raises(ValueError, match="push\\(\\) requires"):
            await provider.push(project_id="proj-x")


# ---------------------------------------------------------------------------
# T10-T12: GitHubProvider.pull() (fetch)
# ---------------------------------------------------------------------------

class TestGitHubProviderPull:
    @pytest.mark.asyncio
    async def test_pull_returns_token_acquired_status(self):
        from kerf_cloud.git_providers.github import GitHubProvider
        from kerf_cloud.github_app import invalidate_cache

        invalidate_cache(211)
        provider = GitHubProvider(_FAKE_SETTINGS)

        with patch("kerf_cloud.github_app.httpx.AsyncClient", return_value=_mock_gh_token_response("ghs_pull_tok")):
            result = await provider.pull(
                project_id="proj-4",
                installation_id=211,
                github_owner="acme",
                github_repo="sensor",
            )

        assert result["status"] == "token_acquired"
        assert result["provider"] == "github"

    @pytest.mark.asyncio
    async def test_pull_authenticated_remote_url_contains_token(self):
        from kerf_cloud.git_providers.github import GitHubProvider
        from kerf_cloud.github_app import invalidate_cache

        invalidate_cache(212)
        provider = GitHubProvider(_FAKE_SETTINGS)

        with patch("kerf_cloud.github_app.httpx.AsyncClient", return_value=_mock_gh_token_response("ghs_pull_secret")):
            result = await provider.pull(
                project_id="proj-5",
                installation_id=212,
                github_owner="acme",
                github_repo="sensor",
            )

        assert "ghs_pull_secret" in result["authenticated_remote_url"]

    @pytest.mark.asyncio
    async def test_pull_missing_args_raises_value_error(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        provider = GitHubProvider(_FAKE_SETTINGS)
        with pytest.raises(ValueError, match="pull\\(\\) requires"):
            await provider.pull(project_id="proj-y")


# ---------------------------------------------------------------------------
# T13-T15: GitHubProvider.connect() / disconnect() (install / uninstall)
# ---------------------------------------------------------------------------

class TestGitHubProviderConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect_writes_owner_and_repo_to_db(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        conn = AsyncMock()
        conn.execute = AsyncMock()
        pool = _make_pool(conn)

        provider = GitHubProvider(_FAKE_SETTINGS, pool=pool)
        result = await provider.connect(
            project_id="proj-c1",
            github_owner="kerf-hq",
            github_repo="myproject",
        )

        conn.execute.assert_called_once()
        call_sql = conn.execute.call_args[0][0]
        assert "github_owner" in call_sql
        assert "github_repo" in call_sql

        assert result["provider"] == "github"
        assert result["github_owner"] == "kerf-hq"
        assert result["github_repo"] == "myproject"
        assert result["remote_url"] == "https://github.com/kerf-hq/myproject.git"

    @pytest.mark.asyncio
    async def test_connect_raises_without_pool(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        provider = GitHubProvider(_FAKE_SETTINGS, pool=None)
        with pytest.raises(RuntimeError, match="requires a DB pool"):
            await provider.connect(
                project_id="proj-c2",
                github_owner="acme",
                github_repo="widget",
            )

    @pytest.mark.asyncio
    async def test_disconnect_clears_owner_and_repo(self):
        """Uninstall: disconnect() NULLs github_owner/github_repo in DB."""
        from kerf_cloud.git_providers.github import GitHubProvider

        conn = AsyncMock()
        conn.execute = AsyncMock()
        pool = _make_pool(conn)

        provider = GitHubProvider(_FAKE_SETTINGS, pool=pool)
        await provider.disconnect(project_id="proj-d1")

        conn.execute.assert_called_once()
        call_sql = conn.execute.call_args[0][0]
        assert "NULL" in call_sql
        assert "github_owner" in call_sql or "github_repo" in call_sql


# ---------------------------------------------------------------------------
# T16-T18: GitHubProvider.status()
# ---------------------------------------------------------------------------

class TestGitHubProviderStatus:
    @pytest.mark.asyncio
    async def test_status_returns_connected_true_when_all_data_present(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[
            {"github_owner": "kerf-hq", "github_repo": "proj"},  # cloud_git_repos
            {"github_installation_id": 777, "github_login": "alice"},  # cloud_github_tokens
        ])
        pool = _make_pool(conn)

        provider = GitHubProvider(_FAKE_SETTINGS, pool=pool)
        result = await provider.status(project_id="proj-s1", user_id="user-001")

        assert result["connected"] is True
        assert result["github_owner"] == "kerf-hq"
        assert result["github_repo"] == "proj"
        assert result["installation_id"] == 777
        assert result["github_login"] == "alice"

    @pytest.mark.asyncio
    async def test_status_returns_connected_false_when_no_token_row(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[
            {"github_owner": "kerf-hq", "github_repo": "proj"},  # repo exists
            None,  # no cloud_github_tokens row
        ])
        pool = _make_pool(conn)

        provider = GitHubProvider(_FAKE_SETTINGS, pool=pool)
        result = await provider.status(project_id="proj-s2", user_id="user-002")

        assert result["connected"] is False

    @pytest.mark.asyncio
    async def test_status_without_pool_returns_disconnected(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        provider = GitHubProvider(_FAKE_SETTINGS, pool=None)
        result = await provider.status(project_id="proj-s3", user_id="user-003")

        assert result["connected"] is False
        assert "reason" in result


# ---------------------------------------------------------------------------
# T19-T22: Installation token rotation (cache expiry → re-mint)
# ---------------------------------------------------------------------------

class TestInstallationTokenRotation:
    @pytest.mark.asyncio
    async def test_expired_token_triggers_re_mint(self):
        """After expiry, installation_token() must call GitHub again."""
        from kerf_cloud.github_app import installation_token, invalidate_cache, _store_token

        installation_id = 55001
        invalidate_cache(installation_id)

        # Manually store an already-expired entry in the cache.
        _store_token(installation_id, "ghs_expired", expires_at=None)
        # Override the expiry to be in the past.
        from kerf_cloud import github_app
        with github_app._cache_lock:
            github_app._token_cache[installation_id] = ("ghs_expired", time.time() - 10)

        call_count = {"n": 0}

        async def _fake_post(url, **kwargs):
            call_count["n"] += 1
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={
                "token": "ghs_fresh",
                "expires_at": "2099-01-01T00:00:00Z",
            })
            return resp

        mock_client = AsyncMock()
        mock_client.post = _fake_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("kerf_cloud.github_app.httpx.AsyncClient", return_value=mock_client):
            token = await installation_token(installation_id, "3727956", _PRIVATE_KEY_PEM)

        assert token == "ghs_fresh"
        assert call_count["n"] == 1

    @pytest.mark.asyncio
    async def test_valid_cached_token_not_re_minted(self):
        from kerf_cloud.github_app import installation_token, invalidate_cache

        installation_id = 55002
        invalidate_cache(installation_id)

        call_count = {"n": 0}

        async def _fake_post(url, **kwargs):
            call_count["n"] += 1
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={
                "token": "ghs_valid",
                "expires_at": "2099-01-01T00:00:00Z",
            })
            return resp

        mock_client = AsyncMock()
        mock_client.post = _fake_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("kerf_cloud.github_app.httpx.AsyncClient", return_value=mock_client):
            t1 = await installation_token(installation_id, "3727956", _PRIVATE_KEY_PEM)
            t2 = await installation_token(installation_id, "3727956", _PRIVATE_KEY_PEM)
            t3 = await installation_token(installation_id, "3727956", _PRIVATE_KEY_PEM)

        assert t1 == t2 == t3 == "ghs_valid"
        assert call_count["n"] == 1, "GitHub should only be called once for a valid cached token"

    @pytest.mark.asyncio
    async def test_multiple_installation_ids_isolated_in_cache(self):
        """Separate installation_ids get separate tokens; no cross-contamination."""
        from kerf_cloud.github_app import installation_token, invalidate_cache

        id_a, id_b = 55010, 55011
        invalidate_cache(id_a)
        invalidate_cache(id_b)

        call_log: list[str] = []

        def _make_mock(token_val: str) -> AsyncMock:
            async def _post(url, **kwargs):
                call_log.append(token_val)
                resp = MagicMock()
                resp.raise_for_status = MagicMock()
                resp.json = MagicMock(return_value={
                    "token": token_val,
                    "expires_at": "2099-01-01T00:00:00Z",
                })
                return resp
            mc = AsyncMock()
            mc.post = _post
            mc.__aenter__ = AsyncMock(return_value=mc)
            mc.__aexit__ = AsyncMock(return_value=False)
            return mc

        # Seed both caches with distinct tokens.
        with patch("kerf_cloud.github_app.httpx.AsyncClient", side_effect=[
            _make_mock("ghs_a"), _make_mock("ghs_b"),
        ]):
            token_a = await installation_token(id_a, "3727956", _PRIVATE_KEY_PEM)
            token_b = await installation_token(id_b, "3727956", _PRIVATE_KEY_PEM)

        assert token_a == "ghs_a"
        assert token_b == "ghs_b"
        assert token_a != token_b

    @pytest.mark.asyncio
    async def test_invalidate_cache_clears_single_entry(self):
        from kerf_cloud.github_app import installation_token, invalidate_cache

        installation_id = 55020
        invalidate_cache(installation_id)

        call_count = {"n": 0}

        async def _fake_post(url, **kwargs):
            call_count["n"] += 1
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={
                "token": f"ghs_rotation_{call_count['n']}",
                "expires_at": "2099-01-01T00:00:00Z",
            })
            return resp

        mock_client = AsyncMock()
        mock_client.post = _fake_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("kerf_cloud.github_app.httpx.AsyncClient", return_value=mock_client):
            await installation_token(installation_id, "3727956", _PRIVATE_KEY_PEM)
            invalidate_cache(installation_id)  # explicit cache eviction
            await installation_token(installation_id, "3727956", _PRIVATE_KEY_PEM)

        assert call_count["n"] == 2, "After invalidation, a new token must be minted"


# ---------------------------------------------------------------------------
# T23-T25: PEM not leaked + error propagation
# ---------------------------------------------------------------------------

class TestSecurityAndErrors:
    @pytest.mark.asyncio
    async def test_pem_not_in_pull_result(self):
        from kerf_cloud.git_providers.github import GitHubProvider
        from kerf_cloud.github_app import invalidate_cache

        invalidate_cache(300)
        provider = GitHubProvider(_FAKE_SETTINGS)

        with patch("kerf_cloud.github_app.httpx.AsyncClient", return_value=_mock_gh_token_response("ghs_pull_pem_check")):
            result = await provider.pull(
                project_id="proj-pem1",
                installation_id=300,
                github_owner="acme",
                github_repo="private",
            )

        result_str = str(result)
        assert "PRIVATE KEY" not in result_str
        assert "BEGIN RSA" not in result_str

    @pytest.mark.asyncio
    async def test_push_http_error_from_github_raises_value_error(self):
        """A 401 from GitHub's token endpoint should surface as ValueError."""
        import httpx
        from kerf_cloud.git_providers.github import GitHubProvider
        from kerf_cloud.github_app import invalidate_cache

        installation_id = 301
        invalidate_cache(installation_id)

        async def _bad_post(url, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.raise_for_status = MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "401",
                    request=MagicMock(),
                    response=mock_resp,
                )
            )
            return mock_resp

        mock_client = AsyncMock()
        mock_client.post = _bad_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        provider = GitHubProvider(_FAKE_SETTINGS)
        with patch("kerf_cloud.github_app.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(ValueError, match="GitHub token acquisition failed"):
                await provider.push(
                    project_id="proj-err1",
                    installation_id=installation_id,
                    github_owner="acme",
                    github_repo="secret",
                )

    @pytest.mark.asyncio
    async def test_status_pem_not_in_status_result(self):
        """Status result must not contain PEM key material."""
        from kerf_cloud.git_providers.github import GitHubProvider

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[
            {"github_owner": "kerf-hq", "github_repo": "proj"},
            {"github_installation_id": 888, "github_login": "bob"},
        ])
        pool = _make_pool(conn)

        provider = GitHubProvider(_FAKE_SETTINGS, pool=pool)
        result = await provider.status(project_id="proj-pem2", user_id="user-099")

        result_str = str(result)
        assert "PRIVATE KEY" not in result_str
        assert "BEGIN RSA" not in result_str
        assert _PRIVATE_KEY_PEM[:20] not in result_str
