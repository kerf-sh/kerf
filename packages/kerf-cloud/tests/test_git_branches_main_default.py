"""T-312 — GET /projects/{pid}/git/branches returns 'main' after ensure_git_repo.

Spec:
  After ensure_git_repo is called, the GET /projects/{pid}/git/branches response
  includes a row with name='main' and is_default=True.

Tests use a mock pool that simulates the DB state after ensure_git_repo has run.
No live DB required.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_LOOP: asyncio.AbstractEventLoop | None = None


def _loop() -> asyncio.AbstractEventLoop:
    global _LOOP
    if _LOOP is None or _LOOP.is_closed():
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP


def run(coro):
    return _loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Fake DB row
# ---------------------------------------------------------------------------

def _make_branch_row(name: str, head_sha=None, is_default: bool = False) -> dict:
    """Return an object that behaves like an asyncpg Record for branch queries."""
    r = MagicMock()
    r.__getitem__ = lambda self, k: {
        "name": name,
        "head_sha": head_sha,
        "is_default": is_default,
    }[k]
    r.get = lambda k, default=None: {
        "name": name,
        "head_sha": head_sha,
        "is_default": is_default,
    }.get(k, default)
    return r


# ---------------------------------------------------------------------------
# Pool / connection helpers
# ---------------------------------------------------------------------------

def _make_pool_with_branches(rows: list) -> MagicMock:
    """Return a mock pool whose connection.fetch() returns *rows*."""
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)

    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _req() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGitBranchesMainDefault:
    """GET /projects/{pid}/git/branches includes main with is_default=True."""

    def test_main_branch_present_after_ensure_git_repo(self):
        """Simulate the DB state just after ensure_git_repo: one 'main' row."""
        import kerf_cloud.routes as routes

        pid = "00000000-0000-0000-0000-000000000001"
        uid = "00000000-0000-0000-0000-000000000002"

        main_row = _make_branch_row("main", head_sha=None, is_default=True)
        pool = _make_pool_with_branches([main_row])

        with patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=pool)), \
             patch("kerf_cloud.routes.require_role", AsyncMock(return_value=(uid, "owner"))), \
             patch("kerf_cloud.routes.get_storage_required", return_value=MagicMock()), \
             patch("kerf_cloud.routes.resolve_project_repo",
                   return_value=MagicMock(repo_dir="/tmp/__nonexistent_kerf_t312__")):
            result = run(routes.git_branches(
                request=_req(),
                payload={"sub": uid},
                pid=pid,
            ))

        assert isinstance(result, list), f"Expected list, got: {type(result)}"
        assert len(result) >= 1, "Expected at least one branch"

        main_entry = next((b for b in result if b["name"] == "main"), None)
        assert main_entry is not None, f"'main' branch missing from response: {result}"
        assert main_entry["is_default"] is True, (
            f"main branch should have is_default=True, got: {main_entry['is_default']}"
        )
        # head_sha is empty string when head_sha is NULL (no commits yet).
        assert main_entry["head_sha"] == "", (
            f"head_sha should be '' for brand-new repo, got: {main_entry['head_sha']!r}"
        )

    def test_main_branch_is_default_true(self):
        """is_default flag on the main branch row is True."""
        import kerf_cloud.routes as routes

        pid = "00000000-0000-0000-0000-000000000003"
        uid = "00000000-0000-0000-0000-000000000004"

        main_row = _make_branch_row("main", head_sha=None, is_default=True)
        feature_row = _make_branch_row("feature/x", head_sha=None, is_default=False)
        pool = _make_pool_with_branches([feature_row, main_row])

        with patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=pool)), \
             patch("kerf_cloud.routes.require_role", AsyncMock(return_value=(uid, "owner"))), \
             patch("kerf_cloud.routes.get_storage_required", return_value=MagicMock()), \
             patch("kerf_cloud.routes.resolve_project_repo",
                   return_value=MagicMock(repo_dir="/tmp/__nonexistent_kerf_t312__")):
            result = run(routes.git_branches(
                request=_req(),
                payload={"sub": uid},
                pid=pid,
            ))

        defaults = [b for b in result if b["is_default"]]
        assert len(defaults) == 1, f"Expected exactly one default branch, got: {defaults}"
        assert defaults[0]["name"] == "main"

    def test_empty_picker_before_fix_is_gone(self):
        """Regression: an empty branches list (old behaviour) is no longer valid
        for a freshly initialised project."""
        import kerf_cloud.routes as routes

        pid = "00000000-0000-0000-0000-000000000005"
        uid = "00000000-0000-0000-0000-000000000006"

        # After the fix, ensure_git_repo inserts a main row, so the fetch
        # always returns at least that row. Simulate the post-fix DB state.
        main_row = _make_branch_row("main", head_sha=None, is_default=True)
        pool = _make_pool_with_branches([main_row])

        with patch("kerf_cloud.routes.get_pool_required", AsyncMock(return_value=pool)), \
             patch("kerf_cloud.routes.require_role", AsyncMock(return_value=(uid, "owner"))), \
             patch("kerf_cloud.routes.get_storage_required", return_value=MagicMock()), \
             patch("kerf_cloud.routes.resolve_project_repo",
                   return_value=MagicMock(repo_dir="/tmp/__nonexistent_kerf_t312__")):
            result = run(routes.git_branches(
                request=_req(),
                payload={"sub": uid},
                pid=pid,
            ))

        assert result != [], "Branch picker must not be empty after project creation"
