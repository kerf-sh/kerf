"""Git commit diff + resolve endpoints (T-186).

Routes
------
GET  /workspaces/{wsid}/git/commits/{sha}/diff
    Returns a JSON manifest describing every file changed in the given commit
    relative to its parent.  Text files include a unified diff; binary / large
    files carry ``binary: true`` and a null ``text_diff``.

POST /workspaces/{wsid}/git/resolve
    Body: ``{path: str, pick: "yours"|"theirs", against_sha: str}``
    Reads both sides of the path at HEAD vs ``against_sha``, writes the
    chosen side back, and records a new commit via ``materialize_and_commit``.
    Returns ``{ok: true, sha: "<new-commit-sha>"}``.

``wsid`` is treated as the project UUID (``projects.id``).  The git repo for
a project lives under the storage root at ``workspaces/<project_id>/git`` —
resolved via ``resolve_project_repo`` from the storage/git_storer module.

Auth
----
Both endpoints require a valid JWT (``require_auth``).  The caller must be a
member of the workspace that owns the project; non-members receive 404 (same
as other project routes so membership is not revealed).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import UUID

import pygit2
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from kerf_core.db.connection import get_pool_required
from kerf_core.dependencies import require_auth
from kerf_core.storage import get_storage_required
from kerf_core.storage.diff import (
    file_kind_from_path,
    is_binary_content,
    unified_text_diff,
)
from kerf_core.storage.git_storer import resolve_project_repo
from kerf_core.storage.lfs_pointer import LfsPointerError
from kerf_core.storage.lfs_pointer import parse as parse_pointer
from kerf_core.storage.materialize import (
    FileEntry,
    materialize_and_commit,
    read_path,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Auth / project helpers
# ---------------------------------------------------------------------------


async def _get_project_and_check_membership(
    pid: str, user_id: str
) -> dict:
    """Return the project row or raise 404 (masks auth failures)."""
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, workspace_id, name FROM projects WHERE id = $1",
            pid,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        ws_id = str(row["workspace_id"])
        member = await conn.fetchrow(
            "SELECT role FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
            ws_id, user_id,
        )
        if not member:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        return dict(row)


# ---------------------------------------------------------------------------
# pygit2 helpers (sync, run in thread executor)
# ---------------------------------------------------------------------------

def _list_commit_changes(repo_dir: str, sha: str) -> list[dict]:
    """Return raw change records by comparing ``sha`` to its parent.

    Each record contains:
    ``path``, ``change`` (added|modified|deleted), ``oid_old``, ``oid_new``,
    ``raw_old`` (bytes|None), ``raw_new`` (bytes|None).

    LFS-pointer blobs are returned verbatim (the caller decides hydration).
    """
    try:
        repo = pygit2.Repository(repo_dir)
    except (pygit2.GitError, KeyError) as exc:
        raise FileNotFoundError(f"no git repo at {repo_dir!r}: {exc}") from exc

    try:
        commit = repo.revparse_single(sha)
    except KeyError:
        raise KeyError(f"commit {sha!r} not found")

    if not isinstance(commit, pygit2.Commit):
        commit = commit.peel(pygit2.Commit)

    # New tree (the commit itself)
    new_tree = commit.tree

    # Parent tree — empty tree if this is the root commit
    if commit.parents:
        parent = commit.parents[0]
        old_tree = parent.tree
        parent_sha = str(parent.id)
    else:
        old_tree = None
        parent_sha = ""

    changes: list[dict] = []

    if old_tree is None:
        # Root commit: every file is "added"
        for full_path, entry in _walk_tree(repo, new_tree, ""):
            blob = repo[entry.id]
            raw = bytes(blob.data)
            changes.append(
                {
                    "path": full_path,
                    "change": "added",
                    "oid_old": None,
                    "oid_new": str(entry.id),
                    "raw_old": None,
                    "raw_new": raw,
                }
            )
    else:
        # Diff old tree vs new tree using pygit2 diff
        diff = old_tree.diff_to_tree(new_tree)
        for patch in diff:
            delta = patch.delta
            path = delta.new_file.path or delta.old_file.path

            # Map pygit2 status flag to a change label
            status_flag = delta.status
            if status_flag == pygit2.GIT_DELTA_ADDED:
                change = "added"
            elif status_flag == pygit2.GIT_DELTA_DELETED:
                change = "deleted"
            else:
                change = "modified"

            raw_old: Optional[bytes] = None
            raw_new: Optional[bytes] = None
            oid_old: Optional[str] = None
            oid_new: Optional[str] = None

            if delta.old_file.id and str(delta.old_file.id) != "0" * 40:
                try:
                    blob_old = repo[delta.old_file.id]
                    raw_old = bytes(blob_old.data)
                    oid_old = str(delta.old_file.id)
                except Exception:
                    pass

            if delta.new_file.id and str(delta.new_file.id) != "0" * 40:
                try:
                    blob_new = repo[delta.new_file.id]
                    raw_new = bytes(blob_new.data)
                    oid_new = str(delta.new_file.id)
                except Exception:
                    pass

            changes.append(
                {
                    "path": path,
                    "change": change,
                    "oid_old": oid_old,
                    "oid_new": oid_new,
                    "raw_old": raw_old,
                    "raw_new": raw_new,
                }
            )

    return changes, parent_sha


def _walk_tree(repo: pygit2.Repository, tree, prefix: str):
    """Recursively yield (full_path, entry) tuples for every blob in *tree*."""
    for entry in tree:
        name = f"{prefix}/{entry.name}" if prefix else entry.name
        obj = repo[entry.id]
        if isinstance(obj, pygit2.Tree):
            yield from _walk_tree(repo, obj, name)
        else:
            yield name, entry


def _get_commit_parent_sha(repo_dir: str, sha: str) -> str:
    """Return the parent sha of *sha*, or empty string for the root commit."""
    try:
        repo = pygit2.Repository(repo_dir)
        commit = repo.revparse_single(sha).peel(pygit2.Commit)
        return str(commit.parents[0].id) if commit.parents else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# LFS pointer OID extraction
# ---------------------------------------------------------------------------

def _extract_lfs_oid(raw: bytes) -> Optional[str]:
    """Return ``sha256:<hex>`` if *raw* is an LFS pointer; else None."""
    try:
        parsed = parse_pointer(raw)
        return f"sha256:{parsed['oid']}"
    except LfsPointerError:
        return None


# ---------------------------------------------------------------------------
# GET /workspaces/{wsid}/git/commits/{sha}/diff
# ---------------------------------------------------------------------------

@router.get("/workspaces/{wsid}/git/commits/{sha}/diff")
async def get_commit_diff(
    wsid: str,
    sha: str,
    payload: dict = Depends(require_auth),
):
    """Return the diff manifest for commit *sha* within project *wsid*.

    Response shape::

        {
          "sha": "...",
          "parent_sha": "...",
          "files": [
            {
              "path": "src/foo.py",
              "kind": "script",
              "change": "modified",
              "binary": false,
              "text_diff": "--- a/...\\n+++ b/...\\n@@ ...",
              "oid_old": "sha256:...",
              "oid_new": "sha256:..."
            },
            {
              "path": "assets/bigpart.step",
              "kind": "step",
              "change": "modified",
              "binary": true,
              "preview_thumb_url": null,
              "oid_old": "sha256:...",
              "oid_new": "sha256:..."
            }
          ]
        }
    """
    user_id = payload.get("sub")
    await _get_project_and_check_membership(wsid, user_id)

    storage = get_storage_required()
    loc = resolve_project_repo(wsid, storage)

    try:
        changes, parent_sha = await asyncio.get_event_loop().run_in_executor(
            None, _list_commit_changes, loc.repo_dir, sha
        )
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="git repo not found")
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"commit {sha!r} not found")

    files = []
    for rec in changes:
        path: str = rec["path"]
        raw_old: Optional[bytes] = rec["raw_old"]
        raw_new: Optional[bytes] = rec["raw_new"]

        # Determine OIDs — prefer the LFS pointer oid if available, else git blob oid
        oid_old = None
        oid_new = None

        representative = raw_new if raw_new is not None else raw_old

        if raw_old is not None:
            lfs_old = _extract_lfs_oid(raw_old)
            oid_old = lfs_old if lfs_old else (f"sha256:{rec['oid_old']}" if rec["oid_old"] else None)

        if raw_new is not None:
            lfs_new = _extract_lfs_oid(raw_new)
            oid_new = lfs_new if lfs_new else (f"sha256:{rec['oid_new']}" if rec["oid_new"] else None)

        # Binary classification: use the representative side
        # An LFS pointer blob means the real content is binary/large
        is_lfs = (
            (raw_old is not None and _extract_lfs_oid(raw_old) is not None)
            or (raw_new is not None and _extract_lfs_oid(raw_new) is not None)
        )
        binary = is_lfs or (
            representative is not None and is_binary_content(representative)
        )

        kind = file_kind_from_path(path)
        entry: dict = {
            "path": path,
            "kind": kind,
            "change": rec["change"],
            "binary": binary,
            "oid_old": oid_old,
            "oid_new": oid_new,
        }

        if binary:
            entry["preview_thumb_url"] = None
        else:
            # Produce unified diff from the raw git blob bytes
            old_bytes = raw_old if raw_old is not None else b""
            new_bytes = raw_new if raw_new is not None else b""
            entry["text_diff"] = unified_text_diff(
                old_bytes,
                new_bytes,
                fromfile=path,
                tofile=path,
            )

        files.append(entry)

    return {
        "sha": sha,
        "parent_sha": parent_sha,
        "files": files,
    }


# ---------------------------------------------------------------------------
# POST /workspaces/{wsid}/git/resolve
# ---------------------------------------------------------------------------

class ResolveRequest(BaseModel):
    path: str
    pick: str  # "yours" | "theirs"
    against_sha: str


@router.post("/workspaces/{wsid}/git/resolve")
async def resolve_conflict(
    wsid: str,
    req: ResolveRequest,
    payload: dict = Depends(require_auth),
):
    """Write a resolve commit picking one side of a file conflict.

    ``pick="yours"``   → keep the HEAD version of ``path``
    ``pick="theirs"``  → adopt ``against_sha``'s version of ``path``

    After writing, returns ``{ok: true, sha: "<new-commit-sha>"}``.
    """
    if req.pick not in ("yours", "theirs"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pick must be 'yours' or 'theirs'",
        )

    user_id = payload.get("sub")
    project = await _get_project_and_check_membership(wsid, user_id)
    workspace_id_str: str = str(project["workspace_id"])

    storage = get_storage_required()
    loc = resolve_project_repo(wsid, storage)

    # Read both sides via the round-trip read_path helper
    try:
        yours_bytes = await read_path(
            repo_dir=loc.repo_dir,
            path=req.path,
            storage=storage,
            ref="HEAD",
        )
    except (KeyError, pygit2.GitError, pygit2.InvalidSpecError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"path {req.path!r} not found at HEAD: {exc}",
        )

    try:
        theirs_bytes = await read_path(
            repo_dir=loc.repo_dir,
            path=req.path,
            storage=storage,
            ref=req.against_sha,
        )
    except (KeyError, pygit2.GitError, pygit2.InvalidSpecError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"path {req.path!r} not found at {req.against_sha!r}: {exc}",
        )

    chosen_bytes = yours_bytes if req.pick == "yours" else theirs_bytes

    # We need to rebuild the full HEAD tree with the resolved file replaced.
    # Read the entire HEAD tree to get all current files, then substitute.
    head_files = await _read_all_head_files(loc.repo_dir, storage)
    head_files[req.path] = chosen_bytes

    file_entries = [FileEntry(path=p, content=c) for p, c in head_files.items()]

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        result = await materialize_and_commit(
            repo_dir=loc.repo_dir,
            files=file_entries,
            project_id=UUID(wsid),
            workspace_id=UUID(workspace_id_str),
            storage=storage,
            db_conn=conn,
            message=f"Resolved {req.path} ({req.pick})",
            author_name="Kerf",
            author_email="noreply@kerf.dev",
        )

    return {"ok": True, "sha": result.commit_sha}


# ---------------------------------------------------------------------------
# Helper: read all files at HEAD into a dict path -> bytes
# ---------------------------------------------------------------------------

def _collect_tree_paths(
    repo: pygit2.Repository,
    tree: pygit2.Tree,
    prefix: str,
) -> list[tuple[str, bytes]]:
    """Recursively collect (path, raw_bytes) for every blob in *tree*."""
    results = []
    for entry in tree:
        full_path = f"{prefix}/{entry.name}" if prefix else entry.name
        obj = repo[entry.id]
        if isinstance(obj, pygit2.Tree):
            results.extend(_collect_tree_paths(repo, obj, full_path))
        elif isinstance(obj, pygit2.Blob):
            results.append((full_path, bytes(obj.data)))
    return results


def _read_head_tree_sync(repo_dir: str) -> list[tuple[str, bytes]]:
    """Synchronous helper — returns list of (path, raw_bytes) at HEAD."""
    try:
        repo = pygit2.Repository(repo_dir)
        head = repo.revparse_single("HEAD").peel(pygit2.Commit)
        return _collect_tree_paths(repo, head.tree, "")
    except (pygit2.GitError, KeyError):
        return []


async def _read_all_head_files(repo_dir: str, storage) -> dict[str, bytes]:
    """Return a mapping of path → hydrated bytes for every file at HEAD.

    LFS pointer blobs are resolved through the object store so the resolve
    commit can re-materialize the full payload, not just the pointer.
    """
    raw_pairs: list[tuple[str, bytes]] = await asyncio.get_event_loop().run_in_executor(
        None, _read_head_tree_sync, repo_dir
    )

    result: dict[str, bytes] = {}
    for path, raw in raw_pairs:
        lfs_oid = _extract_lfs_oid(raw)
        if lfs_oid:
            # Hydrate from the object store
            hydrated = await read_path(
                repo_dir=repo_dir,
                path=path,
                storage=storage,
                ref="HEAD",
            )
            result[path] = hydrated
        else:
            result[path] = raw

    return result
