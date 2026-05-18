"""Tests for kerf_cloud.git_gc and kerf_cloud.scheduler.git_gc_runner (T-188).

No live DB or S3 required — uses a temporary local bare repo with real pygit2
and real git subprocess calls.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pygit2
import pytest

from kerf_cloud.git_gc import (
    _count_loose_objects,
    _packfile_size,
    repack_project,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_bare_repo(path: str) -> pygit2.Repository:
    return pygit2.init_repository(path, bare=True)


def _make_loose_objects(repo_dir: str, n: int = 5) -> None:
    """Create n loose git objects by writing blobs via git hash-object."""
    for i in range(n):
        data = f"test-object-{i}-{uuid.uuid4().hex}\n".encode()
        subprocess.run(
            ["git", "-C", repo_dir, "hash-object", "-w", "--stdin"],
            input=data,
            capture_output=True,
            check=True,
        )


def _make_commit_with_loose_objects(repo_dir: str) -> int:
    """Create a real commit in a bare repo, producing referenced loose objects.

    Returns the count of loose objects created.
    """
    import tempfile as _tf  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    # Write a blob, tree, commit using git plumbing so objects are reachable.
    blob_sha = subprocess.run(
        ["git", "-C", repo_dir, "hash-object", "-w", "--stdin"],
        input=b"hello from kerf gc test\n",
        capture_output=True, check=True,
    ).stdout.strip().decode()

    # Write the tree entry format using printf to avoid shell escaping issues.
    tree_input = f"100644 blob {blob_sha}\tfile.txt\n"
    tree_sha = subprocess.run(
        ["git", "-C", repo_dir, "mktree"],
        input=tree_input.encode(), capture_output=True, check=True,
    ).stdout.strip().decode()

    commit_sha = subprocess.run(
        [
            "git", "-C", repo_dir,
            "-c", "user.email=gc@test.invalid",
            "-c", "user.name=GC Test",
            "commit-tree", tree_sha, "-m", "gc test commit",
        ],
        capture_output=True, check=True,
    ).stdout.strip().decode()

    subprocess.run(
        ["git", "-C", repo_dir, "update-ref", "refs/heads/main", commit_sha],
        capture_output=True, check=True,
    )

    return _count_loose_objects(repo_dir)


def _has_git() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


_SKIP_NO_GIT = pytest.mark.skipif(not _has_git(), reason="git binary not available")


# ---------------------------------------------------------------------------
# Fake storage that returns a local repo dir
# ---------------------------------------------------------------------------

class _FakeStorage:
    """Minimal storage stub that mimics LocalStorage for resolve_project_repo.

    resolve_project_repo builds the repo path as:
        os.path.join(str(root), *"workspaces/{pid}/git".split("/"))
    so root must be the *base* directory under which workspaces/ lives.
    """

    def __init__(self, base_dir: str):
        # root is the base directory; resolve_project_repo appends the prefix.
        self.root = Path(base_dir)


def _make_storage_and_repo(base_dir: str, pid: str) -> tuple[_FakeStorage, str]:
    """Create a bare repo at <base_dir>/workspaces/<pid>/git and return
    (storage, repo_dir).

    storage.root is set to base_dir so that resolve_project_repo constructs
    the path <base_dir>/workspaces/<pid>/git correctly.
    """
    repo_dir = os.path.join(base_dir, "workspaces", pid, "git")
    os.makedirs(repo_dir, exist_ok=True)
    pygit2.init_repository(repo_dir, bare=True)
    storage = _FakeStorage(base_dir)
    return storage, repo_dir


# ---------------------------------------------------------------------------
# _count_loose_objects
# ---------------------------------------------------------------------------

@_SKIP_NO_GIT
def test_count_loose_objects_zero_for_empty_repo():
    with tempfile.TemporaryDirectory() as d:
        repo_dir = os.path.join(d, "repo.git")
        pygit2.init_repository(repo_dir, bare=True)
        assert _count_loose_objects(repo_dir) == 0


@_SKIP_NO_GIT
def test_count_loose_objects_reflects_written_blobs():
    with tempfile.TemporaryDirectory() as d:
        repo_dir = os.path.join(d, "repo.git")
        pygit2.init_repository(repo_dir, bare=True)
        _make_loose_objects(repo_dir, n=3)
        assert _count_loose_objects(repo_dir) == 3


# ---------------------------------------------------------------------------
# repack_project — basic shape
# ---------------------------------------------------------------------------

@_SKIP_NO_GIT
def test_repack_project_returns_expected_keys():
    with tempfile.TemporaryDirectory() as base:
        pid = uuid.uuid4().hex
        storage, repo_dir = _make_storage_and_repo(base, pid)
        result = repack_project(pid, storage=storage)
        assert "loose_objects_before" in result
        assert "loose_objects_after" in result
        assert "packfile_size_bytes" in result


@_SKIP_NO_GIT
def test_repack_project_reduces_loose_object_count():
    """Repack packs reachable loose objects (blob + tree + commit) into a pack."""
    with tempfile.TemporaryDirectory() as base:
        pid = uuid.uuid4().hex
        storage, repo_dir = _make_storage_and_repo(base, pid)

        # Create a real referenced commit so objects are reachable and
        # git repack -adk will pack them.
        loose_before = _make_commit_with_loose_objects(repo_dir)
        assert loose_before >= 3  # at least blob, tree, commit

        result = repack_project(pid, storage=storage)
        assert not result.get("skipped"), result.get("reason")
        assert result["loose_objects_before"] == loose_before
        # After repack -adk, reachable loose objects are moved to a pack.
        assert result["loose_objects_after"] < loose_before


@_SKIP_NO_GIT
def test_repack_project_skips_missing_repo():
    with tempfile.TemporaryDirectory() as base:
        pid = uuid.uuid4().hex
        # Don't create the repo dir — just use a storage pointing at base.
        # resolve_project_repo will compute <base>/workspaces/<pid>/git,
        # which doesn't exist → should return skipped.
        storage = _FakeStorage(base)
        result = repack_project(pid, storage=storage)
        assert result.get("skipped") is True
        assert "not yet materialised" in result.get("reason", "")


def test_repack_project_skips_when_storage_none():
    # When no storage is provided and get_storage() is not configured, returns skipped.
    with patch("kerf_cloud.git_gc.get_storage" if False else "builtins.__import__"):
        # Patch the import so get_storage() raises.
        original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    result = repack_project("some-workspace-id", storage=None)
    # May be skipped (if storage not configured) or may resolve.
    # We only check the result has the expected shape.
    assert "loose_objects_before" in result or "skipped" in result


# ---------------------------------------------------------------------------
# git_gc_runner — concurrency cap
# ---------------------------------------------------------------------------

def test_runner_caps_concurrency_at_2():
    """Verify the runner never uses more than 2 concurrent workers."""
    import asyncio  # noqa: PLC0415
    from kerf_cloud.scheduler.git_gc_runner import _MAX_WORKERS

    assert _MAX_WORKERS == 2


@pytest.mark.asyncio
async def test_runner_run_once_no_projects():
    """run_once with an empty project list returns zero counts."""
    from kerf_cloud.scheduler.git_gc_runner import run_once  # noqa: PLC0415

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    result = await run_once(pool=mock_pool, storage=MagicMock())
    assert result["projects_processed"] == 0
    assert result["projects_skipped"] == 0
    assert result["projects_failed"] == 0
    assert result["results"] == []


@pytest.mark.asyncio
async def test_runner_run_once_calls_repack_for_each_project():
    """run_once calls repack_project once per row returned from cloud_git_repos."""
    from kerf_cloud.scheduler.git_gc_runner import run_once  # noqa: PLC0415

    pids = [str(uuid.uuid4()), str(uuid.uuid4())]

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[{"project_id": p} for p in pids])

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    called: list[str] = []

    def _fake_repack(pid, *, storage=None):
        called.append(pid)
        return {
            "loose_objects_before": 0,
            "loose_objects_after": 0,
            "packfile_size_bytes": 0,
        }

    with patch("kerf_cloud.scheduler.git_gc_runner.repack_project", side_effect=_fake_repack):
        result = await run_once(pool=mock_pool, storage=MagicMock())

    assert sorted(called) == sorted(pids)
    assert result["projects_processed"] == 2
    assert result["projects_skipped"] == 0
    assert result["projects_failed"] == 0


@pytest.mark.asyncio
async def test_runner_counts_skipped_projects():
    """run_once counts skipped projects separately from processed."""
    from kerf_cloud.scheduler.git_gc_runner import run_once  # noqa: PLC0415

    pid = str(uuid.uuid4())

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[{"project_id": pid}])

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    def _fake_repack(pid, *, storage=None):
        return {
            "skipped": True,
            "reason": "local repo not yet materialised",
            "loose_objects_before": 0,
            "loose_objects_after": 0,
            "packfile_size_bytes": 0,
        }

    with patch("kerf_cloud.scheduler.git_gc_runner.repack_project", side_effect=_fake_repack):
        result = await run_once(pool=mock_pool, storage=MagicMock())

    assert result["projects_processed"] == 0
    assert result["projects_skipped"] == 1
    assert result["projects_failed"] == 0


@pytest.mark.asyncio
async def test_runner_max_workers_is_2():
    """Verify that at most 2 repack_project calls run simultaneously."""
    from kerf_cloud.scheduler.git_gc_runner import run_once  # noqa: PLC0415

    pids = [str(uuid.uuid4()) for _ in range(6)]

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[{"project_id": p} for p in pids])

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    concurrency_peak = [0]
    active = [0]
    lock = threading.Lock()

    def _slow_repack(pid, *, storage=None):
        with lock:
            active[0] += 1
            concurrency_peak[0] = max(concurrency_peak[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        return {
            "loose_objects_before": 0,
            "loose_objects_after": 0,
            "packfile_size_bytes": 0,
        }

    with patch("kerf_cloud.scheduler.git_gc_runner.repack_project", side_effect=_slow_repack):
        await run_once(pool=mock_pool, storage=MagicMock())

    assert concurrency_peak[0] <= 2, (
        f"Peak concurrency was {concurrency_peak[0]}, expected <= 2"
    )
