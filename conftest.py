"""Repo-root conftest.

Ensures the legacy ``backend/`` tree (which still hosts ``tools/``,
``workers/``, ``utils/``, ``geom/``, ``distributors/``) is importable by all
plugin tests until those modules are migrated into plugins.

This file is collected by pytest before any test modules.
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_REPO_ROOT, "backend")

if _BACKEND not in sys.path and os.path.isdir(_BACKEND):
    sys.path.insert(0, _BACKEND)


# Until each plugin is `pip install -e`'d, add their ``src/`` dirs to sys.path
# so ``from kerf_<name> import ...`` works in tests without an install step.
def _add_plugin_src_paths(base: str) -> None:
    """Discover every ``<base>/kerf-<x>/src`` (or packages/kerf-<x>/src) and
    insert it on sys.path."""
    candidates = []
    # Either flat layout (kerf-X/) or monorepo layout (packages/kerf-X/).
    candidates.append(_REPO_ROOT)
    pkg_dir = os.path.join(_REPO_ROOT, "packages")
    if os.path.isdir(pkg_dir):
        candidates.append(pkg_dir)
    for parent in candidates:
        try:
            entries = os.listdir(parent)
        except FileNotFoundError:
            continue
        for entry in entries:
            if not entry.startswith("kerf-"):
                continue
            src = os.path.join(parent, entry, "src")
            if os.path.isdir(src) and src not in sys.path:
                sys.path.insert(0, src)


_add_plugin_src_paths(_REPO_ROOT)
