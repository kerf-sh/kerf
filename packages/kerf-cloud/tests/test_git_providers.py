"""Unit tests for the GitSyncProvider abstraction and GitHubProvider.

Covers:
  - GitSyncProvider interface enforcement (abstract method compliance)
  - GitHubProvider.is_configured: True/False based on settings presence
  - GitHubProvider.name == "github"
  - GitHubProvider.get_install_url delegates to github_app.install_url
  - GitHubProvider.get_installation_token delegates to github_app.installation_token
  - GitHubProvider.push / pull return correct shape and acquire token
  - GitHubProvider.connect / disconnect / status with fake DB pool
  - ProviderRegistry: available_names, get, configured_providers
  - ProviderRegistry: unconfigured provider absent from registry
  - _build_default_registry smoke-test

No real network calls; no real DB; no .env files touched.
"""

from __future__ import annotations

import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# ---------------------------------------------------------------------------
# Generate a throwaway RSA key pair for tests
# ---------------------------------------------------------------------------

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_KEY_PEM = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
).decode()

# ---------------------------------------------------------------------------
# Fake settings helpers
# ---------------------------------------------------------------------------


def _configured_settings():
    s = MagicMock()
    s.cloud_github_app_id = "3727956"
    s.cloud_github_app_slug = "kerf-app"
    s.github_private_key_pem = _PRIVATE_KEY_PEM
    return s


def _unconfigured_settings_no_id():
    s = MagicMock()
    s.cloud_github_app_id = ""
    s.github_private_key_pem = _PRIVATE_KEY_PEM
    s.cloud_github_app_slug = "kerf-app"
    # GitLab also unconfigured so the default registry returns empty.
    s.cloud_gitlab_app_id = ""
    s.cloud_gitlab_app_secret = ""
    return s


def _unconfigured_settings_no_key():
    s = MagicMock()
    s.cloud_github_app_id = "3727956"
    s.github_private_key_pem = ""
    s.cloud_github_app_slug = "kerf-app"
    # GitLab also unconfigured.
    s.cloud_gitlab_app_id = ""
    s.cloud_gitlab_app_secret = ""
    return s


def _make_pool(conn):
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


# ---------------------------------------------------------------------------
# GitSyncProvider abstract interface
# ---------------------------------------------------------------------------


class TestGitSyncProviderInterface:
    """Verify the ABC enforces the full interface."""

    def test_cannot_instantiate_base_directly(self):
        from kerf_cloud.git_providers.base import GitSyncProvider

        with pytest.raises(TypeError):
            GitSyncProvider()  # type: ignore[abstract]

    def test_partial_implementation_raises(self):
        from kerf_cloud.git_providers.base import GitSyncProvider

        class PartialProvider(GitSyncProvider):
            @property
            def name(self):
                return "partial"

            @classmethod
            def is_configured(cls, settings):
                return True

            # Missing: connect, disconnect, push, pull, status

        with pytest.raises(TypeError):
            PartialProvider()  # type: ignore[abstract]

    def test_full_implementation_instantiates(self):
        from kerf_cloud.git_providers.base import GitSyncProvider

        class MinimalProvider(GitSyncProvider):
            @property
            def name(self):
                return "minimal"

            @classmethod
            def is_configured(cls, settings):
                return True

            async def connect(self, project_id, **kwargs):
                return {"provider": "minimal"}

            async def disconnect(self, project_id, **kwargs):
                pass

            async def push(self, project_id, **kwargs):
                return {"provider": "minimal"}

            async def pull(self, project_id, **kwargs):
                return {"provider": "minimal"}

            async def status(self, project_id, **kwargs):
                return {"provider": "minimal", "connected": False}

        p = MinimalProvider()
        assert p.name == "minimal"


# ---------------------------------------------------------------------------
# GitHubProvider.is_configured
# ---------------------------------------------------------------------------


class TestGitHubProviderIsConfigured:
    def test_returns_true_when_both_present(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        assert GitHubProvider.is_configured(_configured_settings()) is True

    def test_returns_false_when_app_id_missing(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        assert GitHubProvider.is_configured(_unconfigured_settings_no_id()) is False

    def test_returns_false_when_pem_missing(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        assert GitHubProvider.is_configured(_unconfigured_settings_no_key()) is False

    def test_returns_false_when_both_missing(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        s = MagicMock()
        s.cloud_github_app_id = ""
        s.github_private_key_pem = ""
        assert GitHubProvider.is_configured(s) is False


# ---------------------------------------------------------------------------
# GitHubProvider.name
# ---------------------------------------------------------------------------


class TestGitHubProviderName:
    def test_name_is_github(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        p = GitHubProvider(_configured_settings())
        assert p.name == "github"


# ---------------------------------------------------------------------------
# GitHubProvider.get_install_url
# ---------------------------------------------------------------------------


class TestGitHubProviderInstallUrl:
    def test_delegates_to_github_app_install_url(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        p = GitHubProvider(_configured_settings())
        url = p.get_install_url(state="abc123")
        assert "github.com/apps/kerf-app/installations/new" in url
        assert "state=abc123" in url

    def test_no_state(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        p = GitHubProvider(_configured_settings())
        url = p.get_install_url()
        assert url == "https://github.com/apps/kerf-app/installations/new"


# ---------------------------------------------------------------------------
# GitHubProvider.get_installation_token
# ---------------------------------------------------------------------------


class TestGitHubProviderInstallationToken:
    @pytest.mark.asyncio
    async def test_delegates_to_github_app_installation_token(self):
        from kerf_cloud.git_providers.github import GitHubProvider
        from kerf_cloud.github_app import invalidate_cache

        invalidate_cache(55555)

        async def _fake_token(installation_id, app_id, private_key_pem):
            assert installation_id == 55555
            assert app_id == "3727956"
            return "ghs_provider_test_token"

        with patch("kerf_cloud.git_providers.github.installation_token", _fake_token):
            p = GitHubProvider(_configured_settings())
            token = await p.get_installation_token(55555)

        assert token == "ghs_provider_test_token"


# ---------------------------------------------------------------------------
# GitHubProvider.push
# ---------------------------------------------------------------------------


class TestGitHubProviderPush:
    @pytest.mark.asyncio
    async def test_push_returns_correct_shape(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        async def _fake_token(installation_id, app_id, private_key_pem):
            return "ghs_push_token"

        with patch("kerf_cloud.git_providers.github.installation_token", _fake_token):
            p = GitHubProvider(_configured_settings())
            result = await p.push(
                "proj-1",
                installation_id=100,
                github_owner="acme",
                github_repo="my-design",
            )

        assert result["provider"] == "github"
        assert result["project_id"] == "proj-1"
        assert result["status"] == "token_acquired"
        assert "acme/my-design.git" in result["remote_url"]
        # authenticated URL must contain the token but NOT be the public URL
        assert "ghs_push_token" in result["authenticated_remote_url"]
        assert "x-access-token" in result["authenticated_remote_url"]

    @pytest.mark.asyncio
    async def test_push_raises_on_missing_kwargs(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        p = GitHubProvider(_configured_settings())
        with pytest.raises(ValueError):
            await p.push("proj-1")  # no installation_id / owner / repo


# ---------------------------------------------------------------------------
# GitHubProvider.pull
# ---------------------------------------------------------------------------


class TestGitHubProviderPull:
    @pytest.mark.asyncio
    async def test_pull_returns_correct_shape(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        async def _fake_token(installation_id, app_id, private_key_pem):
            return "ghs_pull_token"

        with patch("kerf_cloud.git_providers.github.installation_token", _fake_token):
            p = GitHubProvider(_configured_settings())
            result = await p.pull(
                "proj-2",
                installation_id=200,
                github_owner="acme",
                github_repo="my-design",
            )

        assert result["provider"] == "github"
        assert result["project_id"] == "proj-2"
        assert result["status"] == "token_acquired"
        assert "ghs_pull_token" in result["authenticated_remote_url"]

    @pytest.mark.asyncio
    async def test_pull_raises_on_missing_kwargs(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        p = GitHubProvider(_configured_settings())
        with pytest.raises(ValueError):
            await p.pull("proj-2")


# ---------------------------------------------------------------------------
# GitHubProvider.connect / disconnect
# ---------------------------------------------------------------------------


class TestGitHubProviderConnect:
    @pytest.mark.asyncio
    async def test_connect_updates_db_and_returns_remote_url(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        conn = AsyncMock()
        conn.execute = AsyncMock()
        pool = _make_pool(conn)

        p = GitHubProvider(_configured_settings(), pool=pool)
        result = await p.connect(
            "proj-abc",
            github_owner="acme",
            github_repo="widget",
        )

        assert result["provider"] == "github"
        assert result["github_owner"] == "acme"
        assert result["github_repo"] == "widget"
        assert "acme/widget.git" in result["remote_url"]
        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_raises_on_missing_owner(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        pool = _make_pool(AsyncMock())
        p = GitHubProvider(_configured_settings(), pool=pool)
        with pytest.raises(ValueError):
            await p.connect("proj-abc", github_repo="widget")

    @pytest.mark.asyncio
    async def test_connect_raises_without_pool(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        p = GitHubProvider(_configured_settings(), pool=None)
        with pytest.raises(RuntimeError, match="pool"):
            await p.connect("proj-abc", github_owner="acme", github_repo="widget")


class TestGitHubProviderDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_clears_db_row(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        conn = AsyncMock()
        conn.execute = AsyncMock()
        pool = _make_pool(conn)

        p = GitHubProvider(_configured_settings(), pool=pool)
        await p.disconnect("proj-abc")

        conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_raises_without_pool(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        p = GitHubProvider(_configured_settings(), pool=None)
        with pytest.raises(RuntimeError, match="pool"):
            await p.disconnect("proj-abc")


# ---------------------------------------------------------------------------
# GitHubProvider.status
# ---------------------------------------------------------------------------


class TestGitHubProviderStatus:
    @pytest.mark.asyncio
    async def test_status_connected_when_all_data_present(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[
            {"github_owner": "acme", "github_repo": "widget"},
            {"github_installation_id": 77777, "github_login": "acmebot"},
        ])
        pool = _make_pool(conn)

        p = GitHubProvider(_configured_settings(), pool=pool)
        result = await p.status("proj-abc", user_id="user-1")

        assert result["provider"] == "github"
        assert result["connected"] is True
        assert result["github_owner"] == "acme"
        assert result["github_repo"] == "widget"
        assert result["installation_id"] == 77777

    @pytest.mark.asyncio
    async def test_status_disconnected_when_no_repo_row(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(side_effect=[
            None,  # no repo row
            {"github_installation_id": 77777, "github_login": "acmebot"},
        ])
        pool = _make_pool(conn)

        p = GitHubProvider(_configured_settings(), pool=pool)
        result = await p.status("proj-abc", user_id="user-1")

        assert result["provider"] == "github"
        assert result["connected"] is False

    @pytest.mark.asyncio
    async def test_status_graceful_without_pool(self):
        from kerf_cloud.git_providers.github import GitHubProvider

        p = GitHubProvider(_configured_settings(), pool=None)
        result = await p.status("proj-abc", user_id="user-1")

        assert result["provider"] == "github"
        assert result["connected"] is False


# ---------------------------------------------------------------------------
# ProviderRegistry
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    def test_available_names_includes_configured_provider(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.github import GitHubProvider

        reg = ProviderRegistry(_configured_settings())
        reg.register(GitHubProvider)

        assert "github" in reg.available_names()

    def test_available_names_excludes_unconfigured_provider(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.github import GitHubProvider

        reg = ProviderRegistry(_unconfigured_settings_no_id())
        reg.register(GitHubProvider)

        assert "github" not in reg.available_names()

    def test_get_returns_instance_when_configured(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.github import GitHubProvider

        reg = ProviderRegistry(_configured_settings())
        reg.register(GitHubProvider)

        provider = reg.get("github")
        assert provider is not None
        assert provider.name == "github"
        assert isinstance(provider, GitHubProvider)

    def test_get_returns_none_when_unconfigured(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.github import GitHubProvider

        reg = ProviderRegistry(_unconfigured_settings_no_key())
        reg.register(GitHubProvider)

        assert reg.get("github") is None

    def test_get_returns_none_for_unknown_name(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.github import GitHubProvider

        reg = ProviderRegistry(_configured_settings())
        reg.register(GitHubProvider)

        assert reg.get("gitlab") is None

    def test_configured_providers_yields_instances(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.github import GitHubProvider

        reg = ProviderRegistry(_configured_settings())
        reg.register(GitHubProvider)

        providers = list(reg.configured_providers())
        assert len(providers) == 1
        assert providers[0].name == "github"

    def test_configured_providers_empty_when_none_configured(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.github import GitHubProvider

        reg = ProviderRegistry(_unconfigured_settings_no_id())
        reg.register(GitHubProvider)

        providers = list(reg.configured_providers())
        assert providers == []

    def test_register_is_idempotent(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.github import GitHubProvider

        reg = ProviderRegistry(_configured_settings())
        reg.register(GitHubProvider)
        reg.register(GitHubProvider)  # second time — should not duplicate

        providers = list(reg.configured_providers())
        assert len(providers) == 1

    def test_is_available_true_when_configured(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.github import GitHubProvider

        reg = ProviderRegistry(_configured_settings())
        reg.register(GitHubProvider)

        assert reg.is_available("github") is True

    def test_is_available_false_when_unconfigured(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.github import GitHubProvider

        reg = ProviderRegistry(_unconfigured_settings_no_id())
        reg.register(GitHubProvider)

        assert reg.is_available("github") is False


# ---------------------------------------------------------------------------
# _build_default_registry smoke test
# ---------------------------------------------------------------------------


class TestBuildDefaultRegistry:
    def test_contains_github_when_configured(self):
        from kerf_cloud.git_providers.registry import _build_default_registry

        reg = _build_default_registry(_configured_settings())
        assert "github" in reg.available_names()

    def test_empty_when_unconfigured(self):
        from kerf_cloud.git_providers.registry import _build_default_registry

        reg = _build_default_registry(_unconfigured_settings_no_id())
        assert reg.available_names() == []


# ---------------------------------------------------------------------------
# GitLabProvider helpers
# ---------------------------------------------------------------------------


def _gitlab_configured_settings():
    s = MagicMock()
    s.cloud_gitlab_app_id = "gitlab-app-id-12345"
    s.cloud_gitlab_app_secret = "gitlab-app-secret-xyz"
    s.cloud_gitlab_host = ""  # default: https://gitlab.com
    return s


def _gitlab_unconfigured_settings_no_id():
    s = MagicMock()
    s.cloud_gitlab_app_id = ""
    s.cloud_gitlab_app_secret = "gitlab-app-secret-xyz"
    s.cloud_gitlab_host = ""
    return s


def _gitlab_unconfigured_settings_no_secret():
    s = MagicMock()
    s.cloud_gitlab_app_id = "gitlab-app-id-12345"
    s.cloud_gitlab_app_secret = ""
    s.cloud_gitlab_host = ""
    return s


# ---------------------------------------------------------------------------
# GitLabProvider.is_configured
# ---------------------------------------------------------------------------


class TestGitLabProviderIsConfigured:
    def test_returns_true_when_both_present(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        assert GitLabProvider.is_configured(_gitlab_configured_settings()) is True

    def test_returns_false_when_app_id_missing(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        assert GitLabProvider.is_configured(_gitlab_unconfigured_settings_no_id()) is False

    def test_returns_false_when_secret_missing(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        assert GitLabProvider.is_configured(_gitlab_unconfigured_settings_no_secret()) is False

    def test_returns_false_when_both_missing(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        s = MagicMock()
        s.cloud_gitlab_app_id = ""
        s.cloud_gitlab_app_secret = ""
        assert GitLabProvider.is_configured(s) is False


# ---------------------------------------------------------------------------
# GitLabProvider.name
# ---------------------------------------------------------------------------


class TestGitLabProviderName:
    def test_name_is_gitlab(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings())
        assert p.name == "gitlab"


# ---------------------------------------------------------------------------
# GitLabProvider.connect
# ---------------------------------------------------------------------------


class TestGitLabProviderConnect:
    @pytest.mark.asyncio
    async def test_connect_returns_correct_shape(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings())
        result = await p.connect(
            "proj-gl-1",
            gitlab_namespace="acme",
            gitlab_project="my-design",
        )

        assert result["provider"] == "gitlab"
        assert result["project_id"] == "proj-gl-1"
        assert result["gitlab_namespace"] == "acme"
        assert result["gitlab_project"] == "my-design"
        assert "acme/my-design.git" in result["remote_url"]
        assert "gitlab.com" in result["remote_url"]
        # persistence note must be present (deferred migration)
        assert "persistence_note" in result

    @pytest.mark.asyncio
    async def test_connect_uses_custom_host(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings())
        result = await p.connect(
            "proj-gl-2",
            gitlab_namespace="corp",
            gitlab_project="widget",
            gitlab_host="https://gitlab.internal.corp",
        )

        assert "gitlab.internal.corp" in result["remote_url"]
        assert result["gitlab_host"] == "https://gitlab.internal.corp"

    @pytest.mark.asyncio
    async def test_connect_raises_on_missing_namespace(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings())
        with pytest.raises(ValueError, match="gitlab_namespace"):
            await p.connect("proj-gl-1", gitlab_project="my-design")

    @pytest.mark.asyncio
    async def test_connect_raises_on_missing_project(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings())
        with pytest.raises(ValueError, match="gitlab_project"):
            await p.connect("proj-gl-1", gitlab_namespace="acme")


# ---------------------------------------------------------------------------
# GitLabProvider.disconnect
# ---------------------------------------------------------------------------


class TestGitLabProviderDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_completes_without_error(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        # disconnect is a no-op until persistence columns land; must not raise
        p = GitLabProvider(_gitlab_configured_settings())
        await p.disconnect("proj-gl-1")

    @pytest.mark.asyncio
    async def test_disconnect_without_pool_does_not_raise(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings(), pool=None)
        await p.disconnect("proj-gl-1")  # should complete gracefully


# ---------------------------------------------------------------------------
# GitLabProvider.push
# ---------------------------------------------------------------------------


class TestGitLabProviderPush:
    @pytest.mark.asyncio
    async def test_push_returns_correct_shape(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings())
        result = await p.push(
            "proj-gl-3",
            gitlab_access_token="glpat-test-push-token",
            gitlab_namespace="acme",
            gitlab_project="my-design",
        )

        assert result["provider"] == "gitlab"
        assert result["project_id"] == "proj-gl-3"
        assert result["status"] == "token_acquired"
        assert "acme/my-design.git" in result["remote_url"]
        # authenticated URL must embed the token but not equal the public URL
        assert "glpat-test-push-token" in result["authenticated_remote_url"]
        assert "oauth2" in result["authenticated_remote_url"]
        assert result["remote_url"] != result["authenticated_remote_url"]

    @pytest.mark.asyncio
    async def test_push_embeds_token_in_https_url(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings())
        result = await p.push(
            "proj-gl-3",
            gitlab_access_token="mytoken",
            gitlab_namespace="ns",
            gitlab_project="proj",
        )

        auth_url = result["authenticated_remote_url"]
        assert auth_url.startswith("https://oauth2:mytoken@")

    @pytest.mark.asyncio
    async def test_push_raises_on_missing_token(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings())
        with pytest.raises(ValueError, match="gitlab_access_token"):
            await p.push(
                "proj-gl-3",
                gitlab_namespace="acme",
                gitlab_project="my-design",
            )

    @pytest.mark.asyncio
    async def test_push_raises_on_missing_namespace(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings())
        with pytest.raises(ValueError):
            await p.push(
                "proj-gl-3",
                gitlab_access_token="tok",
                gitlab_project="my-design",
            )

    @pytest.mark.asyncio
    async def test_push_uses_custom_host(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings())
        result = await p.push(
            "proj-gl-4",
            gitlab_access_token="tok",
            gitlab_namespace="corp",
            gitlab_project="widget",
            gitlab_host="https://gitlab.internal.corp",
        )

        assert "gitlab.internal.corp" in result["remote_url"]
        assert "gitlab.internal.corp" in result["authenticated_remote_url"]


# ---------------------------------------------------------------------------
# GitLabProvider.pull
# ---------------------------------------------------------------------------


class TestGitLabProviderPull:
    @pytest.mark.asyncio
    async def test_pull_returns_correct_shape(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings())
        result = await p.pull(
            "proj-gl-5",
            gitlab_access_token="glpat-test-pull-token",
            gitlab_namespace="acme",
            gitlab_project="my-design",
        )

        assert result["provider"] == "gitlab"
        assert result["project_id"] == "proj-gl-5"
        assert result["status"] == "token_acquired"
        assert "glpat-test-pull-token" in result["authenticated_remote_url"]

    @pytest.mark.asyncio
    async def test_pull_raises_on_missing_kwargs(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings())
        with pytest.raises(ValueError):
            await p.pull("proj-gl-5")  # no token / namespace / project


# ---------------------------------------------------------------------------
# GitLabProvider.status
# ---------------------------------------------------------------------------


class TestGitLabProviderStatus:
    @pytest.mark.asyncio
    async def test_status_returns_disconnected_no_token(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        p = GitLabProvider(_gitlab_configured_settings())
        result = await p.status("proj-gl-6")

        assert result["provider"] == "gitlab"
        assert result["connected"] is False
        assert "persistence_pending" in result.get("reason", "")

    @pytest.mark.asyncio
    async def test_status_with_valid_token_includes_user(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider
        from unittest.mock import patch, AsyncMock

        fake_user = {"username": "acmebot", "id": 42}

        p = GitLabProvider(_gitlab_configured_settings())

        async def _fake_verify(token):
            assert token == "glpat-valid"
            return fake_user

        with patch.object(p, "_verify_token", _fake_verify):
            result = await p.status("proj-gl-6", gitlab_access_token="glpat-valid")

        assert result["provider"] == "gitlab"
        assert result["token_valid"] is True
        assert result["gitlab_user"] == "acmebot"

    @pytest.mark.asyncio
    async def test_status_with_invalid_token_marks_token_invalid(self):
        from kerf_cloud.git_providers.gitlab import GitLabProvider
        from unittest.mock import patch

        p = GitLabProvider(_gitlab_configured_settings())

        async def _bad_verify(token):
            raise ValueError("GitLab token validation failed: HTTP 401")

        with patch.object(p, "_verify_token", _bad_verify):
            result = await p.status("proj-gl-6", gitlab_access_token="bad-token")

        assert result["provider"] == "gitlab"
        assert result["token_valid"] is False
        assert "token_error" in result


# ---------------------------------------------------------------------------
# GitLabProvider in ProviderRegistry
# ---------------------------------------------------------------------------


class TestGitLabProviderInRegistry:
    def test_gitlab_appears_in_available_names_when_configured(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        reg = ProviderRegistry(_gitlab_configured_settings())
        reg.register(GitLabProvider)

        assert "gitlab" in reg.available_names()

    def test_gitlab_absent_from_available_names_when_unconfigured(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        reg = ProviderRegistry(_gitlab_unconfigured_settings_no_id())
        reg.register(GitLabProvider)

        assert "gitlab" not in reg.available_names()

    def test_get_gitlab_returns_instance_when_configured(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        reg = ProviderRegistry(_gitlab_configured_settings())
        reg.register(GitLabProvider)

        provider = reg.get("gitlab")
        assert provider is not None
        assert provider.name == "gitlab"
        assert isinstance(provider, GitLabProvider)

    def test_get_gitlab_returns_none_when_unconfigured(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        reg = ProviderRegistry(_gitlab_unconfigured_settings_no_secret())
        reg.register(GitLabProvider)

        assert reg.get("gitlab") is None

    def test_github_and_gitlab_coexist_when_both_configured(self):
        from kerf_cloud.git_providers.registry import ProviderRegistry
        from kerf_cloud.git_providers.github import GitHubProvider
        from kerf_cloud.git_providers.gitlab import GitLabProvider

        # Build a settings mock that has both sets of credentials.
        s = MagicMock()
        s.cloud_github_app_id = "3727956"
        s.cloud_github_app_slug = "kerf-app"
        s.github_private_key_pem = _PRIVATE_KEY_PEM
        s.cloud_gitlab_app_id = "gitlab-app-id"
        s.cloud_gitlab_app_secret = "gitlab-app-secret"
        s.cloud_gitlab_host = ""

        reg = ProviderRegistry(s)
        reg.register(GitHubProvider)
        reg.register(GitLabProvider)

        names = reg.available_names()
        assert "github" in names
        assert "gitlab" in names

    def test_default_registry_contains_gitlab_when_configured(self):
        from kerf_cloud.git_providers.registry import _build_default_registry

        reg = _build_default_registry(_gitlab_configured_settings())
        assert "gitlab" in reg.available_names()

    def test_default_registry_gitlab_absent_when_unconfigured(self):
        from kerf_cloud.git_providers.registry import _build_default_registry

        reg = _build_default_registry(_gitlab_unconfigured_settings_no_id())
        # github is also unconfigured in this settings mock, so should be empty
        assert "gitlab" not in reg.available_names()
