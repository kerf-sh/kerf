"""GitHubProvider — mirrors a Kerf project repo to GitHub via the GitHub App.

This provider wraps the existing ``kerf_cloud.github_app`` helpers so the
connect/push/pull/status surface is available through the ``GitSyncProvider``
interface without changing any behaviour.

Availability is env-gated: ``is_configured`` returns True only when
``cloud_github_app_id`` and ``github_private_key_pem`` (derived from
``cloud_github_private_key_b64``) are both present in *settings*.

Push/pull are thin wrappers — the real work (S3-backed storer, commit
materialisation) lives in ``routes.py`` and is the system-of-record; this
provider is an *additive mirror* only.  Callers that need full git-storer
push/pull should continue to use the existing ``/projects/{pid}/git/push`` and
``/projects/{pid}/git/pull`` endpoints directly.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from kerf_cloud.git_providers.base import GitSyncProvider
from kerf_cloud.github_app import (
    app_jwt,
    install_url,
    installation_token,
    invalidate_cache,
)

logger = logging.getLogger(__name__)


class GitHubProvider(GitSyncProvider):
    """GitSyncProvider implementation backed by the GitHub App installation flow.

    Args:
        settings: A kerf-core Settings object (or any object with the
            ``cloud_github_app_id``, ``cloud_github_app_slug``, and
            ``github_private_key_pem`` attributes).
        pool: asyncpg connection pool (optional; required for connect/
              disconnect/status; may be None in test environments that only
              exercise push/pull with injected tokens).
    """

    def __init__(self, settings: Any, pool: Optional[Any] = None) -> None:
        self._settings = settings
        self._pool = pool

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "github"

    # ------------------------------------------------------------------
    # Availability gate
    # ------------------------------------------------------------------

    @classmethod
    def is_configured(cls, settings: Any) -> bool:
        """Return True iff the GitHub App credentials are present."""
        return bool(
            getattr(settings, "cloud_github_app_id", "")
            and getattr(settings, "github_private_key_pem", "")
        )

    # ------------------------------------------------------------------
    # Install URL helper (not part of base, surfaced for routes)
    # ------------------------------------------------------------------

    def get_install_url(self, state: str = "") -> str:
        """Return the GitHub App installation URL (delegates to github_app)."""
        return install_url(self._settings.cloud_github_app_slug, state)

    # ------------------------------------------------------------------
    # Token helper
    # ------------------------------------------------------------------

    async def get_installation_token(self, installation_id: int) -> str:
        """Mint (or return cached) an installation access token."""
        return await installation_token(
            installation_id=installation_id,
            app_id=self._settings.cloud_github_app_id,
            private_key_pem=self._settings.github_private_key_pem,
        )

    def invalidate_token_cache(self, installation_id: Optional[int] = None) -> None:
        """Evict one or all entries from the in-memory installation token cache."""
        invalidate_cache(installation_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        """Record a GitHub owner/repo as the external mirror for *project_id*.

        Expected kwargs:
            github_owner (str): GitHub organisation or user name.
            github_repo  (str): Repository name.

        The existing ``/projects/{pid}/git/connect`` route writes these into
        ``cloud_git_repos.github_owner`` / ``.github_repo``; this method
        provides the same semantics through the provider interface for callers
        that construct the provider directly (e.g. T-146 settings API).

        Requires *pool* to be set.
        """
        github_owner = kwargs.get("github_owner", "").strip()
        github_repo = kwargs.get("github_repo", "").strip()
        if not github_owner or not github_repo:
            raise ValueError("github_owner and github_repo are required for connect()")

        if self._pool is None:
            raise RuntimeError("GitHubProvider.connect() requires a DB pool")

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE cloud_git_repos
                SET github_owner = $2, github_repo = $3
                WHERE project_id = $1
                """,
                project_id,
                github_owner,
                github_repo,
            )

        remote_url = f"https://github.com/{github_owner}/{github_repo}.git"
        return {
            "provider": self.name,
            "project_id": project_id,
            "github_owner": github_owner,
            "github_repo": github_repo,
            "remote_url": remote_url,
        }

    async def disconnect(self, project_id: str, **kwargs: Any) -> None:
        """Clear the GitHub mirror association for *project_id*.

        Requires *pool* to be set.
        """
        if self._pool is None:
            raise RuntimeError("GitHubProvider.disconnect() requires a DB pool")

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE cloud_git_repos
                SET github_owner = NULL, github_repo = NULL
                WHERE project_id = $1
                """,
                project_id,
            )

    # ------------------------------------------------------------------
    # Sync operations
    # ------------------------------------------------------------------

    async def push(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        """Mirror the Kerf SoR git for *project_id* to GitHub.

        The heavy lifting (git-storer → S3 pack transfer, ref-update on GitHub)
        is intentionally left to callers that have the storer instance; this
        method records the push timestamp and returns status.

        For the full push path see ``routes.git_push`` — this method is the
        provider-interface counterpart that T-146 and later tasks will call.

        Required kwargs (provider-resolved by the caller):
            installation_id (int): the GitHub App installation ID for the user.
            github_owner    (str): target org/user.
            github_repo     (str): target repo name.
        """
        installation_id: Optional[int] = kwargs.get("installation_id")
        github_owner: str = kwargs.get("github_owner", "").strip()
        github_repo: str = kwargs.get("github_repo", "").strip()

        if installation_id is None or not github_owner or not github_repo:
            raise ValueError(
                "push() requires installation_id, github_owner, github_repo"
            )

        # Obtain a fresh (or cached) installation access token.
        token = await self.get_installation_token(int(installation_id))

        remote_url = (
            f"https://x-access-token:{token}@github.com"
            f"/{github_owner}/{github_repo}.git"
        )

        return {
            "provider": self.name,
            "project_id": project_id,
            "remote_url": f"https://github.com/{github_owner}/{github_repo}.git",
            "status": "token_acquired",
            # The caller uses `remote_url` (with token) to drive the actual git push.
            "authenticated_remote_url": remote_url,
        }

    async def pull(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        """Fetch from the GitHub mirror for *project_id* into our SoR git.

        Same token-acquisition pattern as push(); the actual git operations are
        the caller's responsibility.

        Required kwargs: same as push().
        """
        installation_id: Optional[int] = kwargs.get("installation_id")
        github_owner: str = kwargs.get("github_owner", "").strip()
        github_repo: str = kwargs.get("github_repo", "").strip()

        if installation_id is None or not github_owner or not github_repo:
            raise ValueError(
                "pull() requires installation_id, github_owner, github_repo"
            )

        token = await self.get_installation_token(int(installation_id))

        remote_url = (
            f"https://x-access-token:{token}@github.com"
            f"/{github_owner}/{github_repo}.git"
        )

        return {
            "provider": self.name,
            "project_id": project_id,
            "remote_url": f"https://github.com/{github_owner}/{github_repo}.git",
            "status": "token_acquired",
            "authenticated_remote_url": remote_url,
        }

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def status(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        """Return connection and sync state for *project_id*.

        Queries ``cloud_git_repos`` for the stored github_owner/github_repo
        and ``cloud_github_tokens`` for the user's installation_id.

        Requires *pool* and a ``user_id`` kwarg.
        """
        user_id: Optional[str] = kwargs.get("user_id")

        if self._pool is None or not user_id:
            # Graceful degradation — return minimal status without DB.
            return {
                "provider": self.name,
                "connected": False,
                "reason": "pool_or_user_id_unavailable",
            }

        async with self._pool.acquire() as conn:
            repo_row = await conn.fetchrow(
                """
                SELECT github_owner, github_repo
                FROM cloud_git_repos
                WHERE project_id = $1
                """,
                project_id,
            )
            token_row = await conn.fetchrow(
                """
                SELECT github_installation_id, github_login
                FROM cloud_github_tokens
                WHERE user_id = $1
                """,
                user_id,
            )

        github_owner = repo_row["github_owner"] if repo_row else None
        github_repo = repo_row["github_repo"] if repo_row else None
        installation_id = token_row["github_installation_id"] if token_row else None
        github_login = token_row["github_login"] if token_row else None

        connected = bool(
            github_owner and github_repo and installation_id
        )

        result: dict[str, Any] = {
            "provider": self.name,
            "connected": connected,
        }
        if connected:
            result["github_owner"] = github_owner
            result["github_repo"] = github_repo
            result["github_login"] = github_login
            result["installation_id"] = installation_id
            result["remote_url"] = (
                f"https://github.com/{github_owner}/{github_repo}.git"
            )

        return result
