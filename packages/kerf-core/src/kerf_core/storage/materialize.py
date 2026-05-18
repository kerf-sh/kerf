"""Git-as-substrate core write-loop (T-124).

This module is the keystone that turns a project's in-memory file set into a
real git commit, transparently offloading large/binary files to the shared
content-addressed object store while keeping diff-able source inline.

The pipeline, per file, is:

  1. classify  — ``kerf_core.storage.classify.should_store_as_blob`` decides
     blob-vs-inline (size dominates; non-UTF-8 is always a blob). The
     threshold defaults to ``settings.git_inline_max_bytes``.
  2. blob path — compute ``sha256`` of the raw bytes (the *oid*), write the
     bytes to the object-storage backend under a content-addressed key
     (``blobs/<oid[:2]>/<oid>`` — idempotent: same content → same key, so
     forks share objects for free), record the oid in the dedup ledger
     (``blob_objects`` + ``blob_refs``), and place the **canonical Git-LFS v1
     pointer** (``lfs_pointer.serialize``) into the git tree at the file path.
  3. inline path — the file's exact bytes go into the git tree verbatim.
  4. commit — assemble the tree (nested dirs preserved) and commit it into a
     per-project **bare** git repository via ``pygit2``.

It deliberately reuses the existing seams (``classify``, ``lfs_pointer``,
``db.queries.blob_objects``, the ``Storage`` backend, ``pygit2``) rather than
inventing a parallel mechanism.

INTEGRATION NOTE (left intentionally out of this slice)
-------------------------------------------------------
The live cloud-git commit handler ``POST /projects/{pid}/git/commit`` in
``packages/kerf-cloud/src/kerf_cloud/routes.py`` currently records a *synthetic*
random sha into ``cloud_git_commits`` and never builds a real tree. Wiring
``materialize_and_commit`` into that handler also requires resolving where each
project's bare repo lives on disk / in S3 (``S3GitStorer`` prefix
``workspaces/{pid}/git``) and threading the storage backend + db connection
through the request — that touches the S3 sync + concurrency-marker path owned
by adjacent waves (T-125). To keep this slice landable and well-tested, the
write-loop is delivered here as a standalone, fully-tested service function;
the handler integration is a one-call substitution
(``sha = await materialize_and_commit(...)``) once the repo-location seam from
T-125 lands. Read-back is provided by ``read_path`` for round-trip tests and
for the future ``kerf export --hydrate`` path.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import posixpath
from dataclasses import dataclass, field
from typing import Mapping, Optional
from uuid import UUID

import pygit2

from kerf_core.db.queries.blob_objects import add_ref, record_blob
from kerf_core.storage.base import Storage
from kerf_core.storage.classify import should_store_as_blob
from kerf_core.storage.lfs_pointer import parse as parse_pointer
from kerf_core.storage.lfs_pointer import serialize as serialize_pointer

__all__ = [
    "FileEntry",
    "MaterializeResult",
    "blob_storage_key",
    "materialize_and_commit",
    "read_path",
]

# Bytes sampled from the head of a file to probe UTF-8 validity when size
# alone does not decide the blob/inline question. 8 KiB matches the classify
# docstring's stated convention.
_SAMPLE_BYTES = 8192


def blob_storage_key(oid: str) -> str:
    """Content-addressed object-store key for a blob oid.

    ``blobs/<first-2-hex>/<full-oid>`` — the 2-char fan-out keeps any single
    prefix listing small, and the key is a pure function of content so two
    projects (or a project and its fork) that contain identical bytes write
    to (and read from) the exact same key: zero marginal storage for forks.
    """
    if len(oid) < 2:
        raise ValueError(f"oid too short to key: {oid!r}")
    return f"blobs/{oid[:2]}/{oid}"


@dataclass
class FileEntry:
    """One file to materialize.

    ``path`` is a POSIX-style repo-relative path (``models/part.step``).
    ``content`` is the exact raw bytes of the file.
    """

    path: str
    content: bytes


@dataclass
class MaterializeResult:
    commit_sha: str
    tree_sha: str
    # path -> oid for every file that was offloaded as a blob
    blobs: dict[str, str] = field(default_factory=dict)
    # paths that were stored inline in the git tree verbatim
    inlined: list[str] = field(default_factory=list)
    # shas of the commit's parents (empty list for a root commit)
    parent_shas: list[str] = field(default_factory=list)


def _normalize_path(path: str) -> str:
    """Validate and normalize a repo-relative POSIX path.

    Rejects absolute paths and any ``..`` traversal so a malicious path can
    neither escape the repo tree nor the object-store prefix.
    """
    if not path or path != path.strip():
        raise ValueError(f"invalid path: {path!r}")
    p = path.replace("\\", "/")
    if p.startswith("/"):
        raise ValueError(f"path must be repo-relative, not absolute: {path!r}")
    norm = posixpath.normpath(p)
    if norm == "." or norm.startswith("../") or norm == "..":
        raise ValueError(f"path escapes repository root: {path!r}")
    parts = norm.split("/")
    if any(seg in ("", ".", "..") for seg in parts):
        raise ValueError(f"path has invalid segment: {path!r}")
    return norm


def _ensure_bare_repo(repo_dir: str) -> pygit2.Repository:
    """Open the per-project bare repo at ``repo_dir``, initializing if absent.

    A bare repo is the right substrate here: there is no working tree to
    check out on the server; the tree is assembled object-by-object from the
    materialized file set.
    """
    os.makedirs(repo_dir, exist_ok=True)
    try:
        return pygit2.Repository(repo_dir)
    except (pygit2.GitError, KeyError):
        return pygit2.init_repository(repo_dir, bare=True)


def _build_tree(repo: pygit2.Repository, blobs_by_path: Mapping[str, bytes]) -> pygit2.Oid:
    """Build a (possibly nested) git tree from path -> tree-content bytes.

    ``blobs_by_path`` values are the bytes that go into git: the verbatim file
    content for inline files, or the serialized LFS pointer for offloaded
    files. Nested directories are reconstructed faithfully.
    """
    # nested dict: dir-name -> subtree dict, file-name -> git blob Oid
    root: dict = {}
    for path, content in blobs_by_path.items():
        blob_oid = repo.create_blob(content)
        parts = path.split("/")
        node = root
        for seg in parts[:-1]:
            node = node.setdefault(seg, {})
            if not isinstance(node, dict):
                raise ValueError(f"path collides with a file: {path!r}")
        leaf = parts[-1]
        if isinstance(node.get(leaf), dict):
            raise ValueError(f"path collides with a directory: {path!r}")
        node[leaf] = blob_oid

    def _write(node: dict) -> pygit2.Oid:
        builder = repo.TreeBuilder()
        for name, value in sorted(node.items()):
            if isinstance(value, dict):
                builder.insert(name, _write(value), pygit2.GIT_FILEMODE_TREE)
            else:
                builder.insert(name, value, pygit2.GIT_FILEMODE_BLOB)
        return builder.write()

    return _write(root)


async def materialize_and_commit(
    *,
    repo_dir: str,
    files: list[FileEntry],
    project_id: UUID,
    workspace_id: Optional[UUID],
    storage: Storage,
    db_conn,
    message: str,
    author_name: str = "Kerf",
    author_email: str = "noreply@kerf.dev",
    branch: str = "main",
    threshold: Optional[int] = None,
) -> MaterializeResult:
    """Classify → (blob → store+ledger+pointer | inline) → commit a git tree.

    Args:
        repo_dir:     Filesystem path of the per-project **bare** git repo.
                      Created (initialized bare) if it does not exist.
        files:        The complete set of files for this commit. The commit's
                      tree is exactly this set (a snapshot, not a delta).
        project_id:   Project UUID — recorded in ``blob_refs``.
        workspace_id: Workspace UUID — recorded as ``first_workspace_id`` on
                      first upload of an oid (dedup billing). May be ``None``.
        storage:      Object-storage backend (``LocalStorage``/``S3Storage``).
        db_conn:      An ``asyncpg`` connection for the dedup ledger writes.
        message:      Commit message.
        branch:       Branch ref to advance (``refs/heads/<branch>``).
        threshold:    Override for the blob size threshold (bytes). Defaults
                      to ``settings.git_inline_max_bytes`` via ``classify``.

    Returns:
        ``MaterializeResult`` with the new commit/tree shas and a breakdown of
        which paths were offloaded as blobs vs. stored inline.
    """
    tree_content: dict[str, bytes] = {}
    result = MaterializeResult(commit_sha="", tree_sha="")

    for entry in files:
        path = _normalize_path(entry.path)
        content = entry.content
        size = len(content)
        sample = content[:_SAMPLE_BYTES]

        if should_store_as_blob(path, size, sample, threshold=threshold):
            oid = hashlib.sha256(content).hexdigest()
            key = blob_storage_key(oid)

            # Write bytes to the object store keyed by oid. Idempotent by
            # construction: identical content → identical key, so re-writing
            # is a harmless overwrite and forks never duplicate bytes.
            await storage.put(
                key,
                io.BytesIO(content),
                "application/octet-stream",
                size,
            )

            # Record in the dedup ledger: blob_objects (one row per oid) and
            # blob_refs (one row per oid/project/path). Both are idempotent.
            await record_blob(db_conn, oid, size, workspace_id)
            await add_ref(db_conn, oid, project_id, path)

            # What goes into git for this path is the canonical LFS pointer,
            # never the bytes themselves.
            tree_content[path] = serialize_pointer(oid, size)
            result.blobs[path] = oid
        else:
            # Small, diff-able UTF-8 file: exact bytes go straight into git.
            tree_content[path] = content
            result.inlined.append(path)

    # pygit2 is synchronous and CPU/IO bound; run the tree+commit build off
    # the event loop so we never block other coroutines.
    def _commit() -> tuple[str, str, list[str]]:
        repo = _ensure_bare_repo(repo_dir)
        tree_oid = _build_tree(repo, tree_content)

        ref_name = f"refs/heads/{branch}"
        parents: list[pygit2.Oid] = []
        try:
            parent_ref = repo.lookup_reference(ref_name)
            parents = [parent_ref.target]
        except KeyError:
            parents = []

        parent_sha_strs = [str(p) for p in parents]

        signature = pygit2.Signature(author_name, author_email)
        commit_oid = repo.create_commit(
            ref_name,
            signature,
            signature,
            message,
            tree_oid,
            parents,
        )
        # Point HEAD at this branch so a plain `git clone` checks it out.
        try:
            repo.set_head(ref_name)
        except (pygit2.GitError, ValueError):
            pass
        return str(commit_oid), str(tree_oid), parent_sha_strs

    commit_sha, tree_sha, parent_shas = await asyncio.get_event_loop().run_in_executor(
        None, _commit
    )
    result.commit_sha = commit_sha
    result.tree_sha = tree_sha
    result.parent_shas = parent_shas
    return result


async def read_path(
    *,
    repo_dir: str,
    path: str,
    storage: Storage,
    ref: str = "HEAD",
) -> bytes:
    """Reconstruct the original file content for ``path`` at ``ref``.

    Inline files are returned straight from the git tree. For offloaded files
    the git tree holds an LFS pointer; this resolves the oid back to the
    bytes in the object store. This is the round-trip / hydrate primitive.
    """
    norm = _normalize_path(path)

    def _read_tree_blob() -> bytes:
        repo = pygit2.Repository(repo_dir)
        commit = repo.revparse_single(ref)
        if isinstance(commit, pygit2.Commit):
            tree = commit.tree
        else:
            tree = commit.peel(pygit2.Commit).tree
        entry = tree[norm]  # raises KeyError if absent
        blob = repo[entry.id]
        return bytes(blob.data)

    raw = await asyncio.get_event_loop().run_in_executor(None, _read_tree_blob)

    # If the tree object is a valid LFS pointer, hydrate from object store;
    # otherwise it is the verbatim inline content.
    try:
        parsed = parse_pointer(raw)
    except Exception:
        return raw

    oid = str(parsed["oid"])
    key = blob_storage_key(oid)
    stream, _content_type = await storage.get(key)
    try:
        data = stream.read()
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()
    return data
