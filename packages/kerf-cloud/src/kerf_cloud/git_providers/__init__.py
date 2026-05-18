"""kerf_cloud.git_providers — external git-sync provider abstraction.

Public surface
--------------
    GitSyncProvider   abstract base class (base.py)
    GitHubProvider    GitHub App implementation (github.py)
    ProviderRegistry  env-gated registry (registry.py)

The Kerf cloud-git storer (S3-backed go-git) is the system-of-record and is
never replaced by a provider — providers are additive mirrors only.
"""

from kerf_cloud.git_providers.base import GitSyncProvider
from kerf_cloud.git_providers.github import GitHubProvider
from kerf_cloud.git_providers.registry import ProviderRegistry, _build_default_registry

__all__ = [
    "GitSyncProvider",
    "GitHubProvider",
    "ProviderRegistry",
    "_build_default_registry",
]
