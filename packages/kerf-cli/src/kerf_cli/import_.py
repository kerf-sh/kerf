"""kerf import — re-create a project from a materialised export directory.

Usage::

    kerf import <dir>

Reads a directory produced by ``kerf export``, then:

1. Parses ``.kerf/metadata.json`` to determine the project name
   (``--name`` overrides).
2. Reads ``.kerf/manifest.lock`` for per-file SHA-256 OIDs; verifies each
   local file matches before uploading.
3. Creates a new project via ``POST /api/projects``.
4. Re-creates any sub-folder structure, then uploads each file via
   ``POST /api/projects/{pid}/files``.

The round-trip ``kerf export → kerf import`` produces a new project whose
file content is byte-for-byte identical to the original.

Exit codes
----------
0 — success (all files uploaded).
1 — partial failure (some files failed) or I/O error.
2 — authentication failure.
3 — server / network error.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

_RETRY_DELAYS = (1, 2, 4)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def cmd_import(args) -> int:  # noqa: ANN001
    """Execute ``kerf import``."""
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

    import_dir = Path(args.import_dir)
    project_name: Optional[str] = getattr(args, "name", None) or None

    if not import_dir.exists():
        print(f"error: directory not found: {import_dir}", file=sys.stderr)
        return 1

    if not import_dir.is_dir():
        print(f"error: not a directory: {import_dir}", file=sys.stderr)
        return 1

    # ---- read .kerf/metadata.json -------------------------------------------
    kerf_dir = import_dir / ".kerf"
    metadata: dict = {}
    metadata_path = kerf_dir / "metadata.json"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"warning: could not read .kerf/metadata.json: {exc}", file=sys.stderr)

    if not project_name:
        project_name = metadata.get("name") or import_dir.name

    # ---- read .kerf/manifest.lock -------------------------------------------
    lock: dict = {}
    lock_path = kerf_dir / "manifest.lock"
    if lock_path.exists():
        try:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            print(f"warning: could not read .kerf/manifest.lock: {exc}", file=sys.stderr)

    # Build {rel_path: lock_entry} lookup for kind + OID verification.
    lock_index: dict[str, dict] = {
        e["path"]: e for e in lock.get("files", []) if e.get("path")
    }

    # ---- collect files to upload --------------------------------------------
    # Walk the directory, skipping .kerf/ and any hidden files at root level.
    entries: list[tuple[str, bytes]] = []
    for local_file in sorted(import_dir.rglob("*")):
        if not local_file.is_file():
            continue
        rel = local_file.relative_to(import_dir)
        # Skip the .kerf/ metadata directory.
        if rel.parts[0] == ".kerf":
            continue
        rel_posix = rel.as_posix()

        content = local_file.read_bytes()

        # Integrity check against manifest.lock if available.
        if rel_posix in lock_index:
            expected_oid = lock_index[rel_posix].get("oid", "")
            if expected_oid:
                actual_oid = hashlib.sha256(content).hexdigest()
                if actual_oid != expected_oid:
                    print(
                        f"warning: SHA-256 mismatch for {rel_posix} "
                        f"(expected {expected_oid[:12]}…, got {actual_oid[:12]}…) — "
                        "file may have been modified after export",
                        file=sys.stderr,
                    )

        entries.append((rel_posix, content))

    # ---- create project -----------------------------------------------------
    print(f"Creating project {project_name!r}...", file=sys.stderr)
    try:
        pid = _create_project(api_url, token, project_name)
    except _ApiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code

    print(f"  Created project ID: {pid}", file=sys.stderr)

    # ---- upload files -------------------------------------------------------
    failures = 0
    for rel_posix, content_bytes in entries:
        kind = lock_index.get(rel_posix, {}).get("kind", "file")
        name = Path(rel_posix).name

        print(f"  Uploading {rel_posix}...", file=sys.stderr)
        ok = _upload_file(api_url, pid, token, name, kind, content_bytes)
        if not ok:
            failures += 1

    total = len(entries)
    ok_count = total - failures
    print(
        f"\nImport complete — {ok_count}/{total} file(s) uploaded to project {pid}.",
        file=sys.stderr,
    )
    if failures:
        print(f"  {failures} file(s) failed.", file=sys.stderr)

    return 1 if failures else 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _ApiError(Exception):
    def __init__(self, msg: str, exit_code: int = 3):
        super().__init__(msg)
        self.exit_code = exit_code


def _create_project(api_url: str, token: str, name: str) -> str:
    """POST /api/projects and return the new project ID."""
    import json as _json  # noqa: PLC0415
    payload = _json.dumps({"name": name}).encode("utf-8")
    url = f"{api_url}/api/projects"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = _json.loads(resp.read().decode())
            pid = data.get("id") or data.get("project_id")
            if not pid:
                raise _ApiError("server did not return a project ID", exit_code=3)
            return str(pid)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise _ApiError(f"auth failure (HTTP {exc.code})", exit_code=2) from exc
        raise _ApiError(
            f"failed to create project: HTTP {exc.code}", exit_code=3
        ) from exc
    except urllib.error.URLError as exc:
        raise _ApiError(f"network error: {exc.reason}", exit_code=3) from exc


def _upload_file(
    api_url: str,
    pid: str,
    token: str,
    name: str,
    kind: str,
    content_bytes: bytes,
) -> bool:
    """POST a single file to /api/projects/{pid}/files.  Returns True on success."""
    import json as _json  # noqa: PLC0415

    # Determine text vs binary content.
    try:
        content_text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content_text = ""

    payload = _json.dumps({
        "name": name,
        "kind": kind,
        "content": content_text,
    }).encode("utf-8")

    url = f"{api_url}/api/projects/{pid}/files"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    delays = list(_RETRY_DELAYS)
    last_err = ""
    for delay in [0] + delays:
        if delay:
            time.sleep(delay)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp.read()
                return True
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401, 403):
                print(f"  error uploading {name}: HTTP {exc.code}", file=sys.stderr)
                return False
            last_err = f"HTTP {exc.code}"
            continue
        except urllib.error.URLError as exc:
            last_err = f"network: {exc.reason}"
            continue

    print(f"  error uploading {name}: {last_err}", file=sys.stderr)
    return False
