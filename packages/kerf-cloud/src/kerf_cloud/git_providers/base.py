"""Abstract GitSyncProvider interface.

Every external-sync provider (GitHub, GitLab, …) implements this protocol.
Kerf's internal cloud-git (S3-backed go-git storer) is the system-of-record
and is NEVER replaced by a provider — providers are additive mirrors only.

Protocol summary
----------------
  name            unique slug, e.g. "github"
  is_configured   env-gate: True iff the provider's app credentials are present
                  in settings.  Absent credentials → provider hidden, no errors.
  connect         associate a project repo with this provider
  disconnect      remove the association
  push            mirror our SoR git → the external forge
  pull            fetch from the external forge → our SoR git (optional mirror)
  status          machine-readable connection/sync state for a project
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class GitSyncProvider(ABC):
    """Abstract base for an external git-sync (mirror) provider."""

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique, URL-safe slug identifying this provider, e.g. ``"github"``."""

    # ------------------------------------------------------------------
    # Availability gate
    # ------------------------------------------------------------------

    @classmethod
    @abstractmethod
    def is_configured(cls, settings: Any) -> bool:
        """Return True iff the provider's required credentials are present in *settings*.

        When False the registry omits this provider entirely; no 503 is raised,
        no feature flag is needed — the provider simply doesn't exist from the
        caller's perspective.
        """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    async def connect(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        """Associate *project_id* with this provider.

        Provider-specific kwargs (e.g. ``owner``, ``repo`` for GitHub) carry
        the user-supplied target coordinates.  Returns a dict that callers may
        surface (e.g. ``{"provider": "github", "remote_url": "..."}``) — shape
        is provider-defined but must always include ``"provider"``.
        """

    @abstractmethod
    async def disconnect(self, project_id: str, **kwargs: Any) -> None:
        """Remove the external-mirror association for *project_id*."""

    # ------------------------------------------------------------------
    # Sync operations
    # ------------------------------------------------------------------

    @abstractmethod
    async def push(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        """Mirror our SoR git for *project_id* to the external forge.

        Returns a provider-defined status dict (must include ``"provider"``).
        """

    @abstractmethod
    async def pull(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        """Fetch from the external forge into our SoR git for *project_id*.

        Returns a provider-defined status dict (must include ``"provider"``).
        """

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @abstractmethod
    async def status(self, project_id: str, **kwargs: Any) -> dict[str, Any]:
        """Return the current connection/sync state for *project_id*.

        Must include at minimum::

            {
                "provider": "<name>",
                "connected": <bool>,
            }
        """
