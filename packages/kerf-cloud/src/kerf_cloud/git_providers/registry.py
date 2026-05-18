"""GitSyncProvider registry.

Holds all known provider *classes* and exposes only those whose
``is_configured(settings)`` gate returns True.

Usage
-----
    from kerf_cloud.git_providers.registry import ProviderRegistry
    from kerf_cloud.git_providers.github import GitHubProvider
    from kerf_core.config import get_settings

    registry = ProviderRegistry(get_settings())
    registry.register(GitHubProvider)

    # Iterate only configured (available) providers:
    for provider in registry.configured_providers(pool=pool):
        print(provider.name)

    # Look up a specific one:
    gh = registry.get("github", pool=pool)
    if gh:
        await gh.connect(project_id, github_owner=..., github_repo=...)
"""

from __future__ import annotations

import logging
from typing import Any, Iterator, Optional, Type

from kerf_cloud.git_providers.base import GitSyncProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry of GitSyncProvider classes, filtered by env-gate.

    Args:
        settings: A Settings object passed to each provider's
            ``is_configured`` classmethod and instance constructor.
    """

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._classes: list[Type[GitSyncProvider]] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, provider_cls: Type[GitSyncProvider]) -> None:
        """Add *provider_cls* to the registry.

        Idempotent — registering the same class twice is a no-op.
        """
        if provider_cls not in self._classes:
            self._classes.append(provider_cls)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_available(self, name: str) -> bool:
        """Return True iff a provider with *name* is registered and configured."""
        for cls in self._classes:
            try:
                instance = cls.__new__(cls)
                instance._settings = self._settings  # type: ignore[attr-defined]
                if instance.name == name and cls.is_configured(self._settings):
                    return True
            except Exception:
                pass
        return False

    def configured_providers(self, pool: Optional[Any] = None) -> Iterator[GitSyncProvider]:
        """Yield provider instances for every configured provider.

        Only providers whose ``is_configured(settings)`` returns True are
        yielded.  Unconfigured providers are silently skipped.
        """
        for cls in self._classes:
            try:
                if cls.is_configured(self._settings):
                    yield cls(self._settings, pool)
            except Exception as exc:
                logger.warning(
                    "git_providers: skipping provider due to instantiation error",
                    provider=cls.__name__,
                    error=str(exc),
                )

    def get(self, name: str, pool: Optional[Any] = None) -> Optional[GitSyncProvider]:
        """Return a configured provider instance by *name*, or None.

        Returns None (rather than raising) when the provider is not registered
        or its ``is_configured`` gate is False — callers should treat None as
        "this provider is not available" and surface a 404/503 accordingly.
        """
        for cls in self._classes:
            try:
                instance = cls.__new__(cls)
                instance._settings = self._settings  # type: ignore[attr-defined]
                if instance.name == name and cls.is_configured(self._settings):
                    return cls(self._settings, pool)
            except Exception:
                pass
        return None

    def available_names(self) -> list[str]:
        """Return the names of all configured providers."""
        names: list[str] = []
        for cls in self._classes:
            try:
                if cls.is_configured(self._settings):
                    instance = cls.__new__(cls)
                    instance._settings = self._settings  # type: ignore[attr-defined]
                    names.append(instance.name)
            except Exception:
                pass
        return names


# ---------------------------------------------------------------------------
# Module-level default registry — populated at import time with all
# built-in providers.  Callers that need a pool-aware instance should call
# get(name, pool=pool) at request time rather than at module import.
# ---------------------------------------------------------------------------

def _build_default_registry(settings: Any) -> ProviderRegistry:
    """Return a registry pre-populated with all built-in providers."""
    from kerf_cloud.git_providers.github import GitHubProvider

    reg = ProviderRegistry(settings)
    reg.register(GitHubProvider)
    return reg
