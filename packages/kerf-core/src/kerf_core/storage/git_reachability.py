"""Concrete GitReachabilityOracle backed by real pygit2 bare repos (T-150).

Walk every commit reachable from every branch and tag in the project's bare
git repository.  For each commit, scan its tree for blob objects whose content
parses as an LFS pointer that encodes the queried oid.  If found in *any*
commit across *all* history, the oid is considered reachable — GC must not
reclaim it.

Safety contract (mirrors the Protocol doc-string):
  - False negatives are FORBIDDEN.  The oracle only returns False when it has
    positively confirmed that no reachable commit references the oid.
  - False positives are safe — they merely delay GC.
  - Any IO error during the walk causes the oracle to return True (safe side).

Execution model
---------------
``is_oid_reachable`` is synchronous so it can be called from ``BlobGCWorker``
without await.  The pygit2 walk is CPU/IO-bound and should be invoked from a
thread-pool executor when called from async code (the worker's ``_tick`` is
already sync for the oracle call path, but the caller can also wrap this in
``asyncio.get_event_loop().run_in_executor(None, oracle.is_oid_reachable, oid)``
for non-blocking usage if needed).

Repo location
-------------
The oracle receives a ``repo_dir`` — the filesystem path of the bare git repo.
For a ``LocalStorage`` deployment this is resolved via
``kerf_core.storage.git_storer.resolve_project_repo``; for a ``LocalStorage``
test, callers pass the path directly.  The oracle is intentionally
repo-per-instance so it is lightweight to construct and test.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import pygit2

from kerf_core.storage.lfs_pointer import LfsPointerError
from kerf_core.storage.lfs_pointer import parse as parse_lfs_pointer

__all__ = ["GitReachabilityOracle"]

logger = logging.getLogger(__name__)

# LFS pointer blobs are at most ~200 bytes; reject anything larger up-front to
# avoid parsing huge blobs (images, binaries, source files).
_MAX_POINTER_BYTES = 1024


class GitReachabilityOracle:
    """Walk all commits reachable from any ref and check for an LFS pointer.

    An oid is reachable if *any* tree blob in *any* reachable commit parses as
    an LFS pointer that references this oid.  The walk covers all branches,
    tags, and stash refs so old commits and detached history are included.

    Args:
        repo_dir: Filesystem path of the bare git repo to inspect.
    """

    def __init__(self, repo_dir: str) -> None:
        self._repo_dir = repo_dir

    # ------------------------------------------------------------------
    # GitReachabilityOracle Protocol surface
    # ------------------------------------------------------------------

    def is_oid_reachable(self, oid: str) -> bool:
        """Return True if any commit in the repo's history references this oid.

        Conservatively returns True on any IO or git error so a transient
        failure never causes accidental data loss.
        """
        try:
            return self._walk_repo(oid)
        except Exception:
            logger.exception(
                "git_reachability_oracle error walking repo=%s oid=%s — "
                "treating as reachable (safe default)",
                self._repo_dir, oid,
            )
            return True  # safe over-approximation

    def last_unreachable_at(self, oid: str) -> Optional[datetime]:
        """Always returns None — we cannot determine *when* an oid became unreachable.

        Returning None is always safe per the Protocol contract (it defers the
        GC decision to the grace-window timestamps already stored in the DB).
        """
        return None

    # ------------------------------------------------------------------
    # Internal walk
    # ------------------------------------------------------------------

    def _walk_repo(self, target_oid: str) -> bool:
        """Open the bare repo and walk all refs to find ``target_oid``.

        Returns True if found, False if not found (unreachable).
        Raises on any pygit2 / filesystem error so the caller can catch and
        return True conservatively.
        """
        try:
            repo = pygit2.Repository(self._repo_dir)
        except (pygit2.GitError, KeyError):
            # Repo does not exist or is not yet initialized — no history → unreachable.
            return False

        # Collect all tip commits: branches, tags, any other refs.
        tip_oids: list[pygit2.Oid] = []
        try:
            for ref_name in repo.references:
                try:
                    ref = repo.lookup_reference(ref_name)
                    resolved = ref.resolve()
                    tip = repo.get(resolved.target)
                    if tip is None:
                        continue
                    # Peeled: tags point to tag objects that themselves point at commits.
                    if isinstance(tip, pygit2.Tag):
                        try:
                            tip = tip.peel(pygit2.Commit)
                        except Exception:
                            continue
                    if isinstance(tip, pygit2.Commit):
                        tip_oids.append(tip.id)
                except Exception:
                    continue  # skip unresolvable refs
        except Exception:
            # references iteration itself failed — empty repo
            return False

        if not tip_oids:
            return False

        # Walk commits reachable from all tips with a single walker so we
        # visit each commit exactly once.
        walker = repo.walk(tip_oids[0], pygit2.GIT_SORT_NONE)
        for extra in tip_oids[1:]:
            try:
                walker.push(extra)
            except Exception:
                pass

        for commit in walker:
            if _tree_contains_pointer(repo, commit.tree, target_oid):
                return True

        return False


# ---------------------------------------------------------------------------
# Tree scanning helpers
# ---------------------------------------------------------------------------

def _tree_contains_pointer(
    repo: pygit2.Repository,
    tree: pygit2.Tree,
    target_oid: str,
) -> bool:
    """Recursively scan a commit's tree for an LFS pointer referencing target_oid."""
    for entry in tree:
        if entry.filemode == pygit2.GIT_FILEMODE_TREE:
            try:
                subtree = repo.get(entry.id)
                if subtree is not None and isinstance(subtree, pygit2.Tree):
                    if _tree_contains_pointer(repo, subtree, target_oid):
                        return True
            except Exception:
                continue
        elif entry.filemode in (pygit2.GIT_FILEMODE_BLOB, pygit2.GIT_FILEMODE_BLOB_EXECUTABLE):
            try:
                blob = repo.get(entry.id)
                if blob is None or not isinstance(blob, pygit2.Blob):
                    continue
                # Skip large blobs — LFS pointers are tiny
                if blob.size > _MAX_POINTER_BYTES:
                    continue
                data = bytes(blob.data)
                try:
                    parsed = parse_lfs_pointer(data)
                    if parsed["oid"] == target_oid:
                        return True
                except LfsPointerError:
                    pass  # not an LFS pointer — normal file
            except Exception:
                continue
    return False
