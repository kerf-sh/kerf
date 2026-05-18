"""kerf admin subcommands (T-188).

Entry point: ``kerf admin <subcommand>``.

Subcommands
-----------
repo-size <workspace>
    Print a single-line JSON object with the sizes (in bytes) of the git
    packfiles and LFS blobs attributed to a workspace:

        {"packfile_bytes": 0, "lfs_blob_bytes": 0, "total_bytes": 0}

    packfile_bytes  — sum of all .pack files in the project's local bare
                      repo (the working copy maintained by S3GitStorer / the
                      LocalStorage backend).
    lfs_blob_bytes  — sum of size_bytes from blob_objects rows where
                      first_workspace_id matches the given workspace UUID.
    total_bytes     — packfile_bytes + lfs_blob_bytes.

    Requires DATABASE_URL to be set for the LFS blob query.  The packfile
    stat is resolved from storage (STORAGE_BACKEND env vars or local
    defaults).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid


# ---------------------------------------------------------------------------
# repo-size
# ---------------------------------------------------------------------------

def _cmd_repo_size(args: argparse.Namespace) -> int:
    workspace_id_str = args.workspace.strip()
    try:
        workspace_id = uuid.UUID(workspace_id_str)
    except ValueError:
        print(
            f"Error: '{workspace_id_str}' is not a valid UUID.",
            file=sys.stderr,
        )
        return 1

    # --- LFS blob bytes: query blob_objects filtered by first_workspace_id ---
    lfs_blob_bytes = _query_lfs_blob_bytes(workspace_id)

    # --- packfile bytes: stat the local repo directory ---
    packfile_bytes = _stat_packfile_bytes(workspace_id)

    total_bytes = packfile_bytes + lfs_blob_bytes
    output = {
        "packfile_bytes": packfile_bytes,
        "lfs_blob_bytes": lfs_blob_bytes,
        "total_bytes": total_bytes,
    }
    print(json.dumps(output))
    return 0


def _query_lfs_blob_bytes(workspace_id: uuid.UUID) -> int:
    """Sum size_bytes from blob_objects for the given workspace via asyncpg."""
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print(
            "Warning: DATABASE_URL not set; lfs_blob_bytes will be 0.",
            file=sys.stderr,
        )
        return 0

    try:
        import asyncio  # noqa: PLC0415
        import asyncpg  # noqa: PLC0415

        async def _query():
            conn = await asyncpg.connect(database_url)
            try:
                row = await conn.fetchrow(
                    "SELECT COALESCE(SUM(size_bytes), 0)::bigint AS total "
                    "FROM blob_objects "
                    "WHERE first_workspace_id = $1",
                    workspace_id,
                )
                return int(row["total"]) if row else 0
            finally:
                await conn.close()

        return asyncio.run(_query())
    except Exception as exc:
        print(f"Warning: LFS blob query failed: {exc}", file=sys.stderr)
        return 0


def _stat_packfile_bytes(workspace_id: uuid.UUID) -> int:
    """Stat packfile size from the local bare repo working copy."""
    try:
        from kerf_core.storage import get_storage  # noqa: PLC0415
        from kerf_core.storage.git_storer import resolve_project_repo  # noqa: PLC0415
    except ImportError:
        print(
            "Warning: kerf-core not installed; packfile_bytes will be 0.",
            file=sys.stderr,
        )
        return 0

    try:
        storage = get_storage()
        if storage is None:
            return 0
        location = resolve_project_repo(str(workspace_id), storage)
        repo_dir = location.repo_dir
        pack_dir = os.path.join(repo_dir, "objects", "pack")
        if not os.path.isdir(pack_dir):
            return 0
        return sum(
            os.path.getsize(os.path.join(pack_dir, f))
            for f in os.listdir(pack_dir)
            if f.endswith(".pack")
        )
    except Exception as exc:
        print(f"Warning: packfile stat failed: {exc}", file=sys.stderr)
        return 0


# ---------------------------------------------------------------------------
# Parser helpers (used from main.py)
# ---------------------------------------------------------------------------

def add_admin_parser(sub: "argparse._SubParsersAction") -> None:  # type: ignore[type-arg]
    """Register the ``admin`` subcommand group onto *sub*."""
    admin_p = sub.add_parser(
        "admin",
        help="Operator administration commands",
        description=(
            "Operator-only administration commands for self-hosted Kerf instances.\n"
            "These commands require DATABASE_URL and/or storage environment\n"
            "variables to be configured."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    admin_sub = admin_p.add_subparsers(dest="admin_command", metavar="<admin-command>")
    admin_sub.required = True

    # ---- repo-size ----
    rs_p = admin_sub.add_parser(
        "repo-size",
        help="Print packfile + LFS blob sizes for a workspace as JSON",
        description=(
            "Report the git packfile and LFS blob sizes for a given workspace.\n\n"
            "Output (single-line JSON):\n"
            "  packfile_bytes  — bytes in git .pack files for the workspace project\n"
            "  lfs_blob_bytes  — bytes in blob_objects attributed to this workspace\n"
            "  total_bytes     — sum of the above\n\n"
            "Requires DATABASE_URL for the LFS blob query.  Packfile size is\n"
            "read from the local storage backend repo directory."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    rs_p.add_argument(
        "workspace",
        metavar="workspace-uuid",
        help="Workspace UUID to report sizes for.",
    )
    rs_p.set_defaults(func=_cmd_admin)
    admin_p.set_defaults(func=_cmd_admin)


def _cmd_admin(args: argparse.Namespace) -> int:
    admin_command = getattr(args, "admin_command", None)
    if admin_command == "repo-size":
        return _cmd_repo_size(args)
    print(f"Unknown admin command: {admin_command}", file=sys.stderr)
    return 1
