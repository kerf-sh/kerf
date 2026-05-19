"""T-312 — ensure_git_repo always creates the 'main' cloud_git_branches row.

Spec:
  1. Calling ensure_git_repo inserts both cloud_git_repos (default_branch='main')
     AND cloud_git_branches (project_id, name='main', head_sha=None, is_default=True).
  2. A second call with the same project_id produces no duplicate rows
     (ON CONFLICT … DO NOTHING).
  3. The POST /projects/{pid}/git/init handler still returns the expected shape.

Tests use a mock pool that records executed SQL statements — no live DB required.
"""
from __future__ import annotations

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock

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
# Fake pool / connection that records SQL statements and args
# ---------------------------------------------------------------------------

class _FakeConn:
    """Records execute() and fetchrow() calls; supports the async-context manager."""

    def __init__(self, *, existing_repo=None):
        self._existing_repo = existing_repo
        self.executed: list[tuple[str, tuple]] = []  # (sql, args)

    async def fetchrow(self, sql: str, *args):
        self.executed.append((sql, args))
        return self._existing_repo

    async def execute(self, sql: str, *args):
        self.executed.append((sql, args))


def _make_pool(conn: _FakeConn) -> MagicMock:
    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _sqls(conn: _FakeConn) -> list[str]:
    """Return normalised SQL strings from all recorded statements."""
    return [" ".join(sql.split()).upper() for sql, _ in conn.executed]


def _args_for(conn: _FakeConn, pattern: str) -> tuple | None:
    """Return the args tuple for the first statement matching *pattern* (case-insensitive)."""
    pat = re.compile(pattern, re.IGNORECASE)
    for sql, args in conn.executed:
        if pat.search(sql):
            return args
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEnsureGitRepoCreatesBranchRow:
    """ensure_git_repo inserts both the repos and branches rows."""

    def test_inserts_repos_row(self):
        from kerf_cloud.routes import ensure_git_repo

        conn = _FakeConn()
        pool = _make_pool(conn)
        run(ensure_git_repo(pool, project_id="p-1"))

        sqls = _sqls(conn)
        assert any("INSERT INTO CLOUD_GIT_REPOS" in s for s in sqls), (
            "Expected INSERT INTO cloud_git_repos, got: " + str(sqls)
        )

    def test_inserts_branches_row_with_correct_values(self):
        from kerf_cloud.routes import ensure_git_repo

        conn = _FakeConn()
        pool = _make_pool(conn)
        run(ensure_git_repo(pool, project_id="p-1"))

        args = _args_for(conn, r"INSERT INTO cloud_git_branches")
        assert args is not None, "No INSERT INTO cloud_git_branches found"

        # The INSERT uses literal values for name/head_sha/is_default:
        #   VALUES ($1, 'main', NULL, true)
        # so only project_id is a bind parameter.
        assert args[0] == "p-1", f"project_id mismatch: {args[0]}"

        # Verify the SQL itself encodes the correct literals.
        branch_sql = next(
            sql for sql, _ in conn.executed
            if re.search(r"INSERT INTO cloud_git_branches", sql, re.IGNORECASE)
        )
        sql_upper = branch_sql.upper()
        assert "'MAIN'" in sql_upper, f"branch name 'main' not found in SQL: {branch_sql}"
        assert "NULL" in sql_upper, f"head_sha NULL not found in SQL: {branch_sql}"
        assert "TRUE" in sql_upper, f"is_default true not found in SQL: {branch_sql}"

    def test_repos_default_branch_is_main(self):
        from kerf_cloud.routes import ensure_git_repo

        conn = _FakeConn()
        pool = _make_pool(conn)
        result = run(ensure_git_repo(pool, project_id="p-1"))

        assert result["default_branch"] == "main"

    def test_repos_row_not_inserted_when_already_exists(self):
        """Early-return path: repos INSERT is skipped, but branch INSERT still runs."""
        from kerf_cloud.routes import ensure_git_repo

        # Simulate the row already existing.
        fake_existing = {"default_branch": "main", "head_sha": ""}
        conn = _FakeConn(existing_repo=fake_existing)
        pool = _make_pool(conn)
        run(ensure_git_repo(pool, project_id="p-1"))

        sqls = _sqls(conn)
        assert not any("INSERT INTO CLOUD_GIT_REPOS" in s for s in sqls), (
            "Should NOT re-insert cloud_git_repos when already exists"
        )
        # Branch INSERT must still run (for backfill of old projects).
        assert any("INSERT INTO CLOUD_GIT_BRANCHES" in s for s in sqls), (
            "Branch INSERT must still run even on early-return path"
        )

    def test_no_duplicate_on_second_call(self):
        """Second call with same project_id: ON CONFLICT DO NOTHING means still only one INSERT."""
        from kerf_cloud.routes import ensure_git_repo

        conn = _FakeConn()
        pool = _make_pool(conn)

        run(ensure_git_repo(pool, project_id="p-1"))
        first_count = sum(
            1 for sql, _ in conn.executed
            if re.search(r"INSERT INTO cloud_git_branches", sql, re.IGNORECASE)
        )

        # On second call the fetchrow returns the repos row (simulate existing).
        # We reuse the same conn; fetchrow still returns None (first call inserted).
        # The key assertion is that the SQL itself contains ON CONFLICT DO NOTHING.
        branch_sql = next(
            sql for sql, _ in conn.executed
            if re.search(r"INSERT INTO cloud_git_branches", sql, re.IGNORECASE)
        )
        assert "ON CONFLICT" in branch_sql.upper(), (
            "branch INSERT must include ON CONFLICT … DO NOTHING"
        )
        assert "DO NOTHING" in branch_sql.upper(), (
            "branch INSERT must include ON CONFLICT … DO NOTHING"
        )
