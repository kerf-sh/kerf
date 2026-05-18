"""GitLabProvider — mirrors a Kerf project repo to GitLab via a PAT or OAuth token.

This provider uses the GitLab API to validate connectivity and construct an
authenticated remote URL for push/pull operations.

Availability is env-gated: ``is_configured`` returns True only when both
``cloud_gitlab_app_id`` and ``cloud_gitlab_app_secret`` are present in
*settings*.  When absent the provider is hidden — no errors, no feature flags
needed.

Token model
-----------
GitLab supports two flows:
  1. **OAuth App** — the user completes an OAuth dance; callers pass
     ``gitlab_access_token`` (a user OAuth access token) to push/pull.
  2. **Personal Access Token (PAT)** — the user supplies a long-lived PAT;
     callers pass ``gitlab_access_token`` directly.

In both cases push/pull receive the token via kwargs and embed it into an
authenticated remote URL of the form::

    https://oauth2:<token>@gitlab.com/<namespace>/<project>.git

This is the same ``authenticated_remote_url`` pattern that GitHubProvider uses.

Persistence
-----------
``cloud_git_repos`` carries ``gitlab_host``, ``gitlab_namespace``, and
``gitlab_project`` columns (landed in T-152).  ``cloud_gitlab_tokens`` holds
the encrypted OAuth / PAT token per user, analogous to ``cloud_github_tokens``.

``connect`` writes mirror coordinates to ``cloud_git_repos`` and (when a token
is provided) upserts the token row in ``cloud_gitlab_tokens``.
``disconnect`` NULLs out the mirror coordinates and deletes the token row.
``status`` queries ``cloud_git_repos`` to determine whether a mirror is attached.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from kerf_cloud.git_providers.base import GitSyncProvider

logger = logging.getLogger(__name__)

_GITLAB_API_VERSION = "v4"


class GitLabProvider(GitSyncProvider):
    """GitSyncProvider implementation backed by the GitLab API.

    Args:
        settings: A kerf-core Settings object (or any object with the
            ``cloud_gitlab_app_id`` and ``cloud_gitlab_app_secret`` attributes
            and, optionally, ``cloud_gitlab_host``).
        pool: asyncpg connection pool (optional; required once the persistence
              columns land; safe to pass None in the interim or in tests).
    """

    def __init__(self, settings: Any, pool: Optional[Any] = None) -> None:
        self._settings = settings
        self._pool = pool

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "gitlab"

    # ------------------------------------------------------------------
    # Availability gate
    # ------------------------------------------------------------------

    @classmethod
    def is_configured(cls, settings: Any) -> bool:
        """Return True iff the GitLab OAuth App credentials are present."""
        return bool(
            getattr(settings, "cloud_gitlab_app_id", "")
            and getattr(settings, "cloud_gitlab_app_secret", "")
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _host(self) -> str:
        """Return the configured GitLab host URL (default: https://gitlab.com)."""
        return (
            getattr(self._settings, "cloud_gitlab_host", "").rstrip("/")
            or "https://gitlab.com"
        )

    def _api_base(self) -> str:
        return f"{self._host()}/api/{_GITLAB_API_VERSION}"

    def _remote_url(
        self,
        namespace: str,
        project: str,
        token: Optional[str] = None,
        host: Optional[str] = None,
    ) -> str:
        """Build a GitLab remote URL, with optional embedded token for auth."""
        base = (host or self._host()).rstrip("/")
        if token:
            # Strip scheme and re-inject credentials.
            if base.startswith("https://"):
                return f"https://oauth2:{token}@{base[8:]}/{namespace}/{project}.git"
            if base.startswith("http://"):
                return f"http://oauth2:{token}@{base[7:]}/{namespace}/{project}.git"
        return f"{base}/{namespace}/{project}.git"

    async def _verify_token(self, token: str) -> dict[str, Any]:
        """Call GET /user to validate *token* and return the GitLab user payload.

        Raises ``ValueError`` if the token is invalid or the request fails.
        """
        url = f"{self._api_base()}/user"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 200:
            return resp.json()
        raise ValueError(
            f"GitLab token validation failed: HTTP {resp.status_code}"
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        """Associate *project_id* with a GitLab project as its external mirror.

        Expected kwargs:
            gitlab_namespace (str): GitLab group/user namespace.
            gitlab_project   (str): Repository slug.
            gitlab_host      (str, optional): Defaults to https://gitlab.com.
            user_id          (str, optional): When provided, upserts a token
                row in ``cloud_gitlab_tokens``.
            gitlab_access_token (str, optional): The OAuth / PAT token to
                persist (encrypted at rest).  Only written when user_id is
                also provided.

        Returns the connection info dict.
        """
        namespace: str = kwargs.get("gitlab_namespace", "").strip()
        project: str = kwargs.get("gitlab_project", "").strip()
        host: str = kwargs.get("gitlab_host", "").strip() or self._host()
        user_id: str = kwargs.get("user_id", "").strip()
        token: str = kwargs.get("gitlab_access_token", "").strip()

        if not namespace or not project:
            raise ValueError(
                "gitlab_namespace and gitlab_project are required for connect()"
            )

        if self._pool is None:
            raise RuntimeError(
                "GitLabProvider.connect() requires a database pool"
            )

        remote_url = self._remote_url(namespace, project, host=host)

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE cloud_git_repos
                SET gitlab_host = $2, gitlab_namespace = $3, gitlab_project = $4
                WHERE project_id = $1
                """,
                project_id, host, namespace, project,
            )
            if user_id and token:
                await conn.execute(
                    """
                    INSERT INTO cloud_gitlab_tokens
                        (user_id, access_token_encrypted, gitlab_host, updated_at)
                    VALUES ($1, $2, $3, now())
                    ON CONFLICT (user_id) DO UPDATE
                        SET access_token_encrypted = EXCLUDED.access_token_encrypted,
                            gitlab_host = EXCLUDED.gitlab_host,
                            updated_at = now()
                    """,
                    user_id, token.encode(), host,
                )

        logger.info(
            "gitlab_provider.connect: persisted mirror for project %s → %s/%s @ %s",
            project_id, namespace, project, host,
        )

        return {
            "provider": self.name,
            "project_id": project_id,
            "gitlab_host": host,
            "gitlab_namespace": namespace,
            "gitlab_project": project,
            "remote_url": remote_url,
        }

    async def disconnect(self, project_id: str, **kwargs: Any) -> None:
        """Clear the GitLab mirror association for *project_id*.

        Optional kwargs:
            user_id (str): When provided, also deletes the token row from
                ``cloud_gitlab_tokens``.
        """
        user_id: str = kwargs.get("user_id", "").strip()

        if self._pool is None:
            raise RuntimeError(
                "GitLabProvider.disconnect() requires a database pool"
            )

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE cloud_git_repos
                SET gitlab_host = NULL, gitlab_namespace = NULL, gitlab_project = NULL
                WHERE project_id = $1
                """,
                project_id,
            )
            if user_id:
                await conn.execute(
                    "DELETE FROM cloud_gitlab_tokens WHERE user_id = $1",
                    user_id,
                )

        logger.info(
            "gitlab_provider.disconnect: cleared mirror for project %s",
            project_id,
        )

    # ------------------------------------------------------------------
    # Sync operations
    # ------------------------------------------------------------------

    async def push(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        """Mirror the Kerf SoR git for *project_id* to GitLab.

        Returns an ``authenticated_remote_url`` containing the access token
        so the caller can drive the actual git push.

        Required kwargs:
            gitlab_access_token (str): A valid GitLab OAuth or PAT token.
            gitlab_namespace    (str): GitLab group/user namespace.
            gitlab_project      (str): Repository slug.
            gitlab_host         (str, optional): Defaults to https://gitlab.com.
        """
        token: str = kwargs.get("gitlab_access_token", "").strip()
        namespace: str = kwargs.get("gitlab_namespace", "").strip()
        project: str = kwargs.get("gitlab_project", "").strip()
        host: str = kwargs.get("gitlab_host", "").strip() or self._host()

        if not token or not namespace or not project:
            raise ValueError(
                "push() requires gitlab_access_token, gitlab_namespace, gitlab_project"
            )

        public_url = self._remote_url(namespace, project, host=host)
        auth_url = self._remote_url(namespace, project, token=token, host=host)

        return {
            "provider": self.name,
            "project_id": project_id,
            "remote_url": public_url,
            "status": "token_acquired",
            "authenticated_remote_url": auth_url,
        }

    async def pull(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        """Fetch from the GitLab mirror for *project_id* into our SoR git.

        Same token-embedding pattern as push(); the actual git operations are
        the caller's responsibility.

        Required kwargs: same as push().
        """
        token: str = kwargs.get("gitlab_access_token", "").strip()
        namespace: str = kwargs.get("gitlab_namespace", "").strip()
        project: str = kwargs.get("gitlab_project", "").strip()
        host: str = kwargs.get("gitlab_host", "").strip() or self._host()

        if not token or not namespace or not project:
            raise ValueError(
                "pull() requires gitlab_access_token, gitlab_namespace, gitlab_project"
            )

        public_url = self._remote_url(namespace, project, host=host)
        auth_url = self._remote_url(namespace, project, token=token, host=host)

        return {
            "provider": self.name,
            "project_id": project_id,
            "remote_url": public_url,
            "status": "token_acquired",
            "authenticated_remote_url": auth_url,
        }

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def status(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        """Return the current connection/sync state for *project_id*.

        Queries ``cloud_git_repos`` to determine whether a GitLab mirror is
        attached (i.e. ``gitlab_namespace`` is not NULL).  Returns
        ``connected: True`` when a mirror row exists.

        Optional kwargs:
            gitlab_access_token (str): When provided, also calls GET /user to
                verify the token and include the authenticated GitLab username.
        """
        token: str = kwargs.get("gitlab_access_token", "").strip()

        result: dict[str, Any] = {
            "provider": self.name,
            "connected": False,
        }

        if self._pool is not None:
            try:
                async with self._pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        SELECT gitlab_host, gitlab_namespace, gitlab_project
                        FROM cloud_git_repos
                        WHERE project_id = $1
                          AND gitlab_namespace IS NOT NULL
                          AND gitlab_namespace <> ''
                        """,
                        project_id,
                    )
                if row is not None:
                    result["connected"] = True
                    result["gitlab_host"] = row["gitlab_host"] or self._host()
                    result["gitlab_namespace"] = row["gitlab_namespace"]
                    result["gitlab_project"] = row["gitlab_project"]
            except Exception as exc:
                logger.warning(
                    "gitlab_provider.status: DB query failed: %s", exc
                )

        if token:
            try:
                user_data = await self._verify_token(token)
                result["gitlab_user"] = user_data.get("username", "")
                result["token_valid"] = True
            except ValueError as exc:
                result["token_valid"] = False
                result["token_error"] = str(exc)
            except httpx.TransportError as exc:
                # Network-level failure (DNS error, connection refused, timeout).
                # Surface cleanly rather than propagating a raw httpx exception.
                logger.warning(
                    "gitlab_provider.status: network error verifying token: %s", exc
                )
                result["token_valid"] = False
                result["token_error"] = f"network error: {exc}"

        return result
