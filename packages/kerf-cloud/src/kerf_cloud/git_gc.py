"""
git_gc — per-project packfile garbage collection (T-188).

repack_project(workspace_id) compacts loose git objects in a project's bare
repo, returning a summary dict with loose_objects_before, loose_objects_after,
and packfile_size_bytes.

Architecture note — S3-backed repos
-------------------------------------
For the S3 storage backend, the canonical repo lives in object storage.
repack_project works against the *local working-copy* directory that
S3GitStorer.clone_to_local populates (the same path used by
resolve_project_repo / materialize_and_commit). Because a full sync-down /
sync-back is expensive and the primary goal is loose-object reduction, this
function shells out to `git repack` against the local working copy and then
**does not push back to S3** — the push path (push_from_local) already runs
`git gc --aggressive` on every commit. GC here is therefore a supplemental
maintenance pass; if the local working copy is absent (e.g. a cold start where
no commit has happened yet) the function returns {"skipped": True, "reason":
"local repo not yet materialised"} rather than fail.

For the local (filesystem) backend the repo lives on disk at a stable path and
repack runs in-place with no extra setup.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pygit2

logger = logging.getLogger(__name__)


def _count_loose_objects(repo_dir: str) -> int:
    """Count loose git objects in objects/XX/YYYYYY... files."""
    objects_dir = os.path.join(repo_dir, "objects")
    if not os.path.isdir(objects_dir):
        return 0
    count = 0
    for entry in os.scandir(objects_dir):
        if not entry.is_dir():
            continue
        name = entry.name
        # Loose object dirs are two-hex-char names.
        if len(name) == 2 and all(c in "0123456789abcdef" for c in name):
            count += sum(1 for _ in os.scandir(entry.path))
    return count


def _packfile_size(repo_dir: str) -> int:
    """Total bytes of all .pack files in objects/pack/."""
    pack_dir = os.path.join(repo_dir, "objects", "pack")
    if not os.path.isdir(pack_dir):
        return 0
    return sum(
        os.path.getsize(os.path.join(pack_dir, f))
        for f in os.listdir(pack_dir)
        if f.endswith(".pack")
    )


def repack_project(workspace_id: str | Any, *, storage=None) -> dict:
    """Compact loose objects for the project identified by *workspace_id*.

    Parameters
    ----------
    workspace_id:
        The project UUID (also used as the project_id in resolve_project_repo).
    storage:
        Optional storage instance.  When None the function attempts to resolve
        the storage from the module-level get_storage() — this works when
        called from within the running server.  Pass an explicit storage object
        from tests.

    Returns
    -------
    dict with keys:
        loose_objects_before  int
        loose_objects_after   int
        packfile_size_bytes   int
        skipped               bool  (only present when True)
        reason                str   (only present when skipped)
    """
    # Resolve storage if not supplied.
    if storage is None:
        try:
            from kerf_core.storage import get_storage  # noqa: PLC0415
            storage = get_storage()
        except Exception:
            return {
                "skipped": True,
                "reason": "storage not configured — pass storage= explicitly or run inside the server",
                "loose_objects_before": 0,
                "loose_objects_after": 0,
                "packfile_size_bytes": 0,
            }

    from kerf_core.storage.git_storer import resolve_project_repo  # noqa: PLC0415

    location = resolve_project_repo(str(workspace_id), storage)
    repo_dir = location.repo_dir

    if not os.path.isdir(repo_dir):
        return {
            "skipped": True,
            "reason": "local repo not yet materialised",
            "loose_objects_before": 0,
            "loose_objects_after": 0,
            "packfile_size_bytes": 0,
        }

    # Verify it is a real git repo before operating.
    try:
        pygit2.Repository(repo_dir)
    except Exception:
        return {
            "skipped": True,
            "reason": f"{repo_dir} is not a valid git repository",
            "loose_objects_before": 0,
            "loose_objects_after": 0,
            "packfile_size_bytes": 0,
        }

    loose_before = _count_loose_objects(repo_dir)

    # compress_references is available in pygit2 >= 1.14 on some builds.
    try:
        repo = pygit2.Repository(repo_dir)
        if hasattr(repo, "compress_references"):
            repo.compress_references()
    except Exception as exc:
        logger.debug("compress_references failed (non-fatal): %s", exc)

    # Shell out to git repack for pack consolidation + loose-object pruning.
    try:
        subprocess.run(
            [
                "git",
                "-C",
                repo_dir,
                "repack",
                "-adk",
                "--depth=50",
                "--window=10",
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning(
            "git repack failed for workspace_id=%s repo_dir=%s: %s",
            workspace_id, repo_dir, exc,
        )
        return {
            "skipped": True,
            "reason": f"git repack failed: {exc}",
            "loose_objects_before": loose_before,
            "loose_objects_after": loose_before,
            "packfile_size_bytes": _packfile_size(repo_dir),
        }

    loose_after = _count_loose_objects(repo_dir)
    pack_bytes = _packfile_size(repo_dir)

    logger.info(
        "repack_project workspace_id=%s loose_before=%d loose_after=%d pack_bytes=%d",
        workspace_id, loose_before, loose_after, pack_bytes,
    )
    return {
        "loose_objects_before": loose_before,
        "loose_objects_after": loose_after,
        "packfile_size_bytes": pack_bytes,
    }
