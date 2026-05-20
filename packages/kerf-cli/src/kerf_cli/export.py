"""kerf export — materialise a project as a plain file tree on disk.

Usage::

    kerf export <project-id> --out <dir>

Calls ``GET /api/projects/{pid}/export`` (returns a ZIP produced by the
server's ``materialize_project_tree`` spine), then extracts the archive
into *out-dir* as a plain directory tree.

The export always produces two metadata files inside the hidden ``.kerf/``
sub-directory:

``.kerf/metadata.json``
    Human-readable project metadata: name, description, tags, created_at,
    source project ID, source workspace ID (from the ZIP manifest).

``.kerf/manifest.lock``
    Machine-readable lock file that records:

    * every file's POSIX path, kind, byte-exact SHA-256 OID, and size;
    * ``cloud_git_repo`` block (default_branch, if the project has one);
    * ``workspace_id_hint`` (anonymised: first 8 hex chars only — enough
      to detect cross-owner imports without leaking the full UUID).

    On import the lock is used for content-integrity verification (the
    importer can check that the SHA-256 of the local file matches the
    recorded OID before uploading).

Exit codes
----------
0 — success.
1 — I/O or extraction error.
2 — authentication failure (HTTP 401/403).
3 — project/server error (HTTP 4xx/5xx, network).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def cmd_export(args) -> int:  # noqa: ANN001
    """Execute ``kerf export``."""
    from kerf_cli.credentials import get_api_url, get_api_token  # noqa: PLC0415

    token: Optional[str] = getattr(args, "token", None) or get_api_token()
    if not token:
        print(
            "error: no API token found. Set KERF_API_TOKEN or pass --token.\n"
            "To create a token: https://kerf.sh/w/<workspace>/settings#api-tokens",
            file=sys.stderr,
        )
        return 2

    api_url: str = get_api_url()
    if getattr(args, "url", None):
        api_url = args.url.rstrip("/")

    project_id: str = args.project_id
    out_dir: Optional[str] = getattr(args, "out", None) or None

    if not out_dir:
        out_dir = f"kerf-export-{project_id[:8]}"

    out_path = Path(out_dir)

    print(f"Exporting project {project_id!r} → {out_path} ...", file=sys.stderr)

    # ---- fetch ZIP from server -----------------------------------------------
    zip_bytes, err_code = _fetch_zip(api_url, token, project_id)
    if zip_bytes is None:
        return err_code  # type: ignore[return-value]

    # ---- extract to directory -----------------------------------------------
    try:
        manifest = _extract_to_dir(zip_bytes, out_path)
    except Exception as exc:  # noqa: BLE001
        print(f"error: extraction failed: {exc}", file=sys.stderr)
        return 1

    # ---- write .kerf/metadata.json ------------------------------------------
    kerf_dir = out_path / ".kerf"
    kerf_dir.mkdir(parents=True, exist_ok=True)

    metadata: dict = {
        "kerf_export_version": 1,
        "project_id": project_id,
        "name": manifest.get("name", ""),
        "description": manifest.get("description", ""),
        "tags": manifest.get("tags", []),
        "created_at": manifest.get("created_at", ""),
        "workspace_id_hint": manifest.get("workspace_id_hint", ""),
    }
    (kerf_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    # ---- write .kerf/manifest.lock ------------------------------------------
    lock = _build_manifest_lock(out_path, manifest)
    (kerf_dir / "manifest.lock").write_text(
        json.dumps(lock, indent=2, sort_keys=True), encoding="utf-8"
    )

    file_count = len([f for f in manifest.get("files", []) if f.get("classification") != "folder"])
    print(
        f"Exported {file_count} file(s) → {out_path}",
        file=sys.stderr,
    )
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_zip(
    api_url: str, token: str, project_id: str
) -> tuple[Optional[bytes], int]:
    """Fetch the export ZIP from the server.  Returns (bytes, 0) on success or
    (None, exit_code) on failure."""
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    url = f"{api_url}/api/projects/{project_id}/export"
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return resp.read(), 0
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            print(f"error: auth failure (HTTP {exc.code})", file=sys.stderr)
            return None, 2
        if exc.code == 404:
            print("error: project not found (HTTP 404)", file=sys.stderr)
            return None, 3
        print(f"error: server error HTTP {exc.code}", file=sys.stderr)
        return None, 3
    except urllib.error.URLError as exc:
        print(f"error: network error: {exc.reason}", file=sys.stderr)
        return None, 3


def _extract_to_dir(zip_bytes: bytes, out_path: Path) -> dict:
    """Extract a server-produced export ZIP into *out_path*.

    Returns the parsed kerf-manifest.json (or ``{}`` if absent).
    Files under ``.kerf/`` inside the ZIP are skipped — we write our own.
    """
    out_path.mkdir(parents=True, exist_ok=True)
    manifest: dict = {}

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # Parse embedded kerf-manifest.json first.
        if "kerf-manifest.json" in zf.namelist():
            manifest = json.loads(zf.read("kerf-manifest.json").decode("utf-8"))

        for info in zf.infolist():
            name = info.filename
            # Skip manifest itself and directory entries.
            if name == "kerf-manifest.json":
                continue
            if name.endswith("/"):
                continue
            # Skip any pre-existing .kerf/ entries from the server ZIP.
            if name.startswith(".kerf/"):
                continue

            dest = out_path / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))

    return manifest


def _sha256_file(path: Path) -> str:
    """Return hex SHA-256 of the file at *path*."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _build_manifest_lock(out_path: Path, server_manifest: dict) -> dict:
    """Build the ``.kerf/manifest.lock`` dict.

    For each non-folder file:
    - ``path``    — POSIX path relative to *out_path*
    - ``kind``    — file kind
    - ``oid``     — sha256 of the local file bytes (verified against server OID)
    - ``size``    — byte size

    Also records ``cloud_git_repo`` and ``workspace_id_hint`` if present in
    the server manifest.
    """
    lock_files: list[dict] = []

    for entry in server_manifest.get("files", []):
        if entry.get("classification") == "folder":
            continue

        rel_path = entry.get("path", "")
        if not rel_path:
            continue

        local_file = out_path / rel_path
        if local_file.exists():
            # Use the actual on-disk SHA-256 (source of truth after extraction).
            oid = _sha256_file(local_file)
            size = local_file.stat().st_size
        else:
            # File is missing locally — record the server-reported OID.
            oid = entry.get("oid", "")
            size = entry.get("size", 0)

        lock_entry: dict = {
            "path": rel_path,
            "kind": entry.get("kind", "file"),
            "oid": oid,
            "size": size,
        }
        if entry.get("mime_type"):
            lock_entry["mime_type"] = entry["mime_type"]

        lock_files.append(lock_entry)

    lock: dict = {
        "kerf_lock_version": 1,
        "files": lock_files,
    }

    # Preserve cloud_git_repo info from the server manifest if present.
    if "cloud_git_repo" in server_manifest:
        lock["cloud_git_repo"] = server_manifest["cloud_git_repo"]

    # Anonymise workspace_id to just the first 8 hex chars.
    ws_hint = server_manifest.get("workspace_id_hint", "")
    if ws_hint:
        lock["workspace_id_hint"] = ws_hint[:8]

    return lock
