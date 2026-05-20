"""kerf sync — two-way folder mirror between a local directory and a cloud project.

One-shot mode (T-127)
---------------------
``kerf sync <project-id> <local-dir> [--dry-run]``
Fetches the remote file list, walks the local directory, and syncs once.

Daemon mode (T-324)
-------------------
``kerf sync <project-id> <local-dir> --watch [--interval N]``
Runs a foreground tick loop.  Each tick calls ``sync_tick(state)`` which:

1.  Fetches the current remote manifest (file-id → sha / updated_at).
2.  Walks the local directory and computes per-file SHA-256.
3.  Compares to the *previous* tick's snapshot (``SyncState``):
    - remote changed, local unchanged → pull
    - local changed, remote unchanged → push
    - both changed (OCC conflict!)    → STOP + print conflict report
    - neither changed                 → skip
4.  Updates the state snapshot.

The tick function is a plain callable so tests can drive it without real I/O or
sleeping.

OCC semantics (T-302)
---------------------
If the same file changed on *both* sides between two ticks the daemon stops
immediately and prints a human-readable conflict report.  The conflicting file
is NOT modified on either side — the user must resolve manually.

Large-file pointers
-------------------
After pulling any remote file its content is inspected; LFS pointer stubs are
hydrated implicitly by calling the hydrate machinery (best-effort).

Deletions
---------
A file that exists locally but not remotely is pushed (not treated as a
deletion).  A file deleted locally is NOT auto-deleted on the server — the
user receives a warning instead (safe default per T-127 DoD).

Exit codes
----------
0 — sync completed / daemon exited cleanly (Ctrl-C).
1 — one or more files failed to sync / partial failure.
2 — auth failure.
3 — project not found / API error.
4 — OCC conflict detected (daemon mode only).
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

_RETRY_DELAYS = (1, 2, 4)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class FileSnapshot:
    """Per-file snapshot captured at the end of each tick."""
    local_sha: Optional[str]    # SHA-256 hex of local bytes; None if absent
    remote_sha: Optional[str]   # server-provided sha / updated_at string; None if absent
    remote_id: Optional[str]    # server file-id, for download


@dataclasses.dataclass
class SyncState:
    """State carried between daemon ticks."""
    api_url: str
    project_id: str
    local_dir: Path
    token: str
    # Map of relative POSIX path → snapshot from the *previous* tick.
    # Empty dict on the very first tick → everything is treated as "first-seen"
    # (pull remote-only, push local-only, no OCC possible on tick 0).
    snapshots: Dict[str, FileSnapshot] = dataclasses.field(default_factory=dict)
    # Tick counter (0-based); purely for diagnostics.
    tick: int = 0


@dataclasses.dataclass
class ConflictInfo:
    path: str
    local_sha_prev: Optional[str]
    local_sha_now: Optional[str]
    remote_sha_prev: Optional[str]
    remote_sha_now: Optional[str]


@dataclasses.dataclass
class SyncResult:
    """Result of a single tick."""
    pulled: List[str] = dataclasses.field(default_factory=list)
    pushed: List[str] = dataclasses.field(default_factory=list)
    warnings: List[str] = dataclasses.field(default_factory=list)
    errors: List[str] = dataclasses.field(default_factory=list)
    conflicts: List[ConflictInfo] = dataclasses.field(default_factory=list)
    # True if the daemon should stop after this tick (OCC or fatal error).
    stop: bool = False
    stop_reason: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors and not self.conflicts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sync_tick(state: SyncState) -> SyncResult:
    """Execute one synchronisation tick.

    This is the core logic unit.  It has no side-effects on ``state`` itself —
    callers must update ``state.snapshots`` and ``state.tick`` from the
    returned result if they want the OCC detection to work across multiple
    ticks.  The daemon loop (``run_daemon``) and the ``cmd_sync`` one-shot
    helper do this automatically.

    Parameters
    ----------
    state:
        Current daemon state.  ``state.snapshots`` holds the per-file snapshot
        from the *previous* tick; on the first tick pass an empty dict.

    Returns
    -------
    SyncResult
        Describes what happened.  If ``result.stop`` is True the daemon should
        halt (OCC conflict or unrecoverable error).
    """
    result = SyncResult()
    # Always set _new_snapshots so callers can safely update state.snapshots.
    result._new_snapshots = dict(state.snapshots)  # type: ignore[attr-defined]

    # 1. Fetch remote manifest.
    try:
        remote_files = _list_remote_files(state.api_url, state.project_id, state.token)
    except _ApiError as exc:
        result.errors.append(str(exc))
        result.stop = True
        result.stop_reason = f"API error: {exc}"
        return result

    # 2. Walk local directory.
    local_map = _build_local_map(state.local_dir)

    # 3. Build current remote map.
    remote_map: Dict[str, dict] = {}
    for rf in remote_files:
        if rf.get("kind") == "folder":
            continue
        name = rf.get("name", "")
        if not name:
            continue
        remote_map[name] = rf

    # 4. Compute current snapshots.
    all_paths = set(remote_map.keys()) | set(local_map.keys())

    new_snapshots: Dict[str, FileSnapshot] = {}
    for path in sorted(all_paths):
        local_info = local_map.get(path)
        remote_info = remote_map.get(path)

        local_sha_now: Optional[str] = None
        if local_info:
            local_sha_now = _sha256_file(local_info["path"])

        remote_sha_now: Optional[str] = None
        remote_id: Optional[str] = None
        if remote_info:
            remote_sha_now = _remote_sha(remote_info)
            remote_id = str(remote_info.get("id", ""))

        new_snapshots[path] = FileSnapshot(
            local_sha=local_sha_now,
            remote_sha=remote_sha_now,
            remote_id=remote_id,
        )

    # 5. Compare new snapshots to previous to decide actions.
    is_first_tick = not state.snapshots

    for path, new_snap in new_snapshots.items():
        prev_snap = state.snapshots.get(path)

        if is_first_tick:
            # First tick: no prior baseline.  Decide by comparing actual content.
            # - local only  → push
            # - remote only → pull
            # - both present, same content (SHA match) → in sync, nothing to do
            # - both present, different content → pull remote (conservative default)
            # OCC is impossible on tick 0 because we have no baseline to compare.
            local_only = new_snap.local_sha is not None and new_snap.remote_sha is None
            remote_only = new_snap.remote_sha is not None and new_snap.local_sha is None
            both_present = new_snap.local_sha is not None and new_snap.remote_sha is not None

            if remote_only:
                ok = _pull_file(
                    state.api_url,
                    state.project_id,
                    state.token,
                    new_snap.remote_id or "",
                    state.local_dir / path,
                )
                if ok:
                    result.pulled.append(path)
                    new_snapshots[path] = dataclasses.replace(
                        new_snap,
                        local_sha=_sha256_file(state.local_dir / path),
                    )
                else:
                    result.errors.append(f"pull failed: {path}")

            elif local_only:
                ok = _push_file(
                    state.api_url,
                    state.project_id,
                    state.token,
                    state.local_dir / path,
                    path,
                    kind=remote_map.get(path, {}).get("kind", "file"),
                )
                if ok:
                    result.pushed.append(path)
                else:
                    result.errors.append(f"push failed: {path}")

            elif both_present:
                # Both sides exist on first tick — compare actual content to
                # decide direction.  If local SHA == remote-content SHA → in sync.
                # Otherwise pull remote (conservative: server is ground truth on
                # first connect; user can always push afterwards).
                remote_content_sha = _remote_content_sha(
                    state.api_url, state.project_id, state.token, new_snap.remote_id or "",
                )
                if remote_content_sha and remote_content_sha != new_snap.local_sha:
                    # Remote differs from local → pull.
                    ok = _pull_file(
                        state.api_url,
                        state.project_id,
                        state.token,
                        new_snap.remote_id or "",
                        state.local_dir / path,
                    )
                    if ok:
                        result.pulled.append(path)
                        new_snapshots[path] = dataclasses.replace(
                            new_snap,
                            local_sha=_sha256_file(state.local_dir / path),
                        )
                    else:
                        result.errors.append(f"pull failed: {path}")
                # else: in sync or can't determine → skip

            continue  # first tick handled above

        # ---- Subsequent ticks: OCC detection ---------------------------------
        local_changed = prev_snap is None or prev_snap.local_sha != new_snap.local_sha
        remote_changed = prev_snap is None or prev_snap.remote_sha != new_snap.remote_sha

        if local_changed and remote_changed:
            # OCC conflict — both sides changed since last tick.
            conflict = ConflictInfo(
                path=path,
                local_sha_prev=prev_snap.local_sha if prev_snap else None,
                local_sha_now=new_snap.local_sha,
                remote_sha_prev=prev_snap.remote_sha if prev_snap else None,
                remote_sha_now=new_snap.remote_sha,
            )
            result.conflicts.append(conflict)
            result.stop = True
            result.stop_reason = "OCC conflict"
            continue

        if remote_changed and not local_changed:
            if new_snap.remote_sha is None:
                # Remote file disappeared; warn only.
                result.warnings.append(
                    f"{path}: remote file removed - not deleting local copy"
                )
            else:
                # Pull from remote.
                ok = _pull_file(
                    state.api_url,
                    state.project_id,
                    state.token,
                    new_snap.remote_id or "",
                    state.local_dir / path,
                )
                if ok:
                    result.pulled.append(path)
                    # Refresh local SHA after download.
                    new_snapshots[path] = dataclasses.replace(
                        new_snap,
                        local_sha=_sha256_file(state.local_dir / path),
                    )
                else:
                    result.errors.append(f"pull failed: {path}")

        elif local_changed and not remote_changed:
            if new_snap.local_sha is None:
                # Local file disappeared; warn only.
                result.warnings.append(
                    f"{path}: local file removed - not deleting remote copy"
                )
            else:
                # Push to remote.
                ok = _push_file(
                    state.api_url,
                    state.project_id,
                    state.token,
                    state.local_dir / path,
                    path,
                    kind=remote_map.get(path, {}).get("kind", "file"),
                )
                if ok:
                    result.pushed.append(path)
                else:
                    result.errors.append(f"push failed: {path}")
        # else: neither changed — in sync, nothing to do.

    # Attach updated snapshots to result so the caller can update state.
    result._new_snapshots = new_snapshots  # type: ignore[attr-defined]
    return result


def run_daemon(
    state: SyncState,
    interval_secs: float = 5.0,
    max_ticks: Optional[int] = None,
) -> int:
    """Run the tick loop until interrupted, a conflict is detected, or max_ticks.

    Returns an exit code:
      0 — clean exit (Ctrl-C or max_ticks reached with no errors).
      1 — one or more sync errors.
      4 — OCC conflict.
    """
    print(
        f"kerf sync daemon watching project {state.project_id!r} "
        f"in {state.local_dir} (interval={interval_secs}s) — Ctrl-C to stop.",
        file=sys.stderr,
    )

    exit_code = 0
    tick_count = 0
    try:
        while True:
            result = sync_tick(state)

            # Update state snapshots.
            state.snapshots = result._new_snapshots  # type: ignore[attr-defined]
            state.tick += 1
            tick_count += 1

            # Print actions.
            for p in result.pulled:
                print(f"  pull   {p}", file=sys.stderr)
            for p in result.pushed:
                print(f"  push   {p}", file=sys.stderr)
            for w in result.warnings:
                print(f"  warn   {w}", file=sys.stderr)
            for e in result.errors:
                print(f"  error  {e}", file=sys.stderr)

            if result.conflicts:
                print("\nOCC CONFLICT — sync stopped. Manual resolution required.", file=sys.stderr)
                for c in result.conflicts:
                    print(f"  CONFLICT  {c.path}", file=sys.stderr)
                    print(f"    local  prev={c.local_sha_prev!r}  now={c.local_sha_now!r}", file=sys.stderr)
                    print(f"    remote prev={c.remote_sha_prev!r}  now={c.remote_sha_now!r}", file=sys.stderr)
                exit_code = 4
                break

            if result.stop:
                print(f"  daemon stopping: {result.stop_reason}", file=sys.stderr)
                if result.errors:
                    exit_code = 1 if exit_code == 0 else exit_code
                break

            if result.errors:
                exit_code = 1

            if max_ticks is not None and tick_count >= max_ticks:
                break

            time.sleep(interval_secs)

    except KeyboardInterrupt:
        print("\nSync stopped by user.", file=sys.stderr)

    return exit_code


# ---------------------------------------------------------------------------
# One-shot entry point (T-127 / ``kerf sync`` without --watch)
# ---------------------------------------------------------------------------

def cmd_sync(args) -> int:  # noqa: ANN001
    """Execute ``kerf sync``."""
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
    local_dir = Path(args.local_dir).resolve()
    dry_run: bool = getattr(args, "dry_run", False)
    watch: bool = getattr(args, "watch", False)
    interval: float = float(getattr(args, "interval", 5))

    if not local_dir.exists():
        local_dir.mkdir(parents=True, exist_ok=True)

    state = SyncState(
        api_url=api_url,
        project_id=project_id,
        local_dir=local_dir,
        token=token,
    )

    if watch:
        return run_daemon(state, interval_secs=interval)

    # ---- One-shot mode --------------------------------------------------
    if dry_run:
        # Dry-run: just fetch + diff, no mutations.
        print(f"Fetching remote file list for project {project_id!r}...", file=sys.stderr)
        try:
            remote_files = _list_remote_files(api_url, project_id, token)
        except _ApiError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return exc.exit_code

        local_map = _build_local_map(local_dir)
        actions = _compute_diff(remote_files, local_map, local_dir)

        if not actions:
            print("Already in sync — nothing to do.", file=sys.stderr)
            return 0

        for action in actions:
            if action["type"] in ("pull", "push"):
                _print_action(action["type"], action["path"], action.get("reason", ""), dry_run=True)
            elif action["type"] == "warn":
                print(f"  warn   {action['path']}  — {action.get('reason', '')}", file=sys.stderr)

        print(f"\nDry-run complete — {len(actions)} action(s) would be applied.", file=sys.stderr)
        return 0

    # ---- One-shot apply (mtime-based, T-127 compatible) ---------------------
    print(f"Fetching remote file list for project {project_id!r}...", file=sys.stderr)
    try:
        remote_files = _list_remote_files(api_url, project_id, token)
    except _ApiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code

    local_map = _build_local_map(local_dir)
    actions = _compute_diff(remote_files, local_map, local_dir)

    if not actions:
        print("Already in sync — nothing to do.", file=sys.stderr)
        return 0

    failures = 0
    for action in actions:
        if action["type"] == "pull":
            _print_action("pull", action["path"], action.get("reason", ""), dry_run=False)
            ok = _pull_file(
                api_url, project_id, token, action["file_id"],
                local_dir / action["path"],
            )
            if not ok:
                failures += 1
        elif action["type"] == "push":
            _print_action("push", action["path"], action.get("reason", ""), dry_run=False)
            ok = _push_file(
                api_url, project_id, token,
                local_dir / action["path"],
                action["path"],
                action.get("kind", "file"),
            )
            if not ok:
                failures += 1
        elif action["type"] == "warn":
            print(f"  warn   {action['path']}  - {action.get('reason', '')}", file=sys.stderr)

    ok_count = len([a for a in actions if a["type"] in ("pull", "push")]) - failures
    print(f"\nSync complete — {ok_count} action(s) applied.", file=sys.stderr)
    if failures:
        print(f"  {failures} action(s) failed.", file=sys.stderr)

    return 1 if failures else 0


# ---------------------------------------------------------------------------
# Remote file list
# ---------------------------------------------------------------------------

class _ApiError(Exception):
    def __init__(self, msg: str, exit_code: int = 3):
        super().__init__(msg)
        self.exit_code = exit_code


def _list_remote_files(api_url: str, pid: str, token: str) -> List[dict]:
    """Return parsed JSON list from GET /api/projects/{pid}/files."""
    url = f"{api_url}/api/projects/{pid}/files"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise _ApiError(f"auth failure (HTTP {exc.code})", exit_code=2) from exc
        if exc.code == 404:
            raise _ApiError("project not found (HTTP 404)", exit_code=3) from exc
        raise _ApiError(f"server error HTTP {exc.code}", exit_code=3) from exc
    except urllib.error.URLError as exc:
        raise _ApiError(f"network error: {exc.reason}", exit_code=3) from exc


# ---------------------------------------------------------------------------
# Local file map + SHA
# ---------------------------------------------------------------------------

def _build_local_map(local_dir: Path) -> Dict[str, dict]:
    """Return {relative_posix_path: {path, mtime, size}} for files under local_dir."""
    result = {}
    if not local_dir.exists():
        return result
    for fp in sorted(local_dir.rglob("*")):
        if not fp.is_file():
            continue
        rel = fp.relative_to(local_dir).as_posix()
        stat = fp.stat()
        result[rel] = {"path": fp, "mtime": stat.st_mtime, "size": stat.st_size}
    return result


def _sha256_file(path: Path) -> Optional[str]:
    """Return hex SHA-256 of a file's bytes, or None if the file does not exist."""
    try:
        data = path.read_bytes()
        return hashlib.sha256(data).hexdigest()
    except OSError:
        return None


def _remote_sha(rf: dict) -> str:
    """Derive a stable change token from a remote file record.

    Uses ``sha256`` if the server provides it; falls back to ``updated_at``
    (a timestamp string).  Both work correctly as "did it change?" tokens.
    """
    return rf.get("sha256") or rf.get("sha") or rf.get("updated_at") or ""


def _remote_content_sha(api_url: str, pid: str, token: str, file_id: str) -> Optional[str]:
    """Download a remote file and return its SHA-256.  Returns None on error.

    Used on the first tick when both sides have the file — lets us compare
    actual content rather than relying on the server-side sha256 field (which
    may not be present on older server versions).
    """
    if not file_id:
        return None
    url = f"{api_url}/api/projects/{pid}/files/{file_id}/download"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            return hashlib.sha256(data).hexdigest()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# One-shot diff (used by dry-run path)
# ---------------------------------------------------------------------------

def _compute_diff(
    remote_files: List[dict],
    local_map: Dict[str, dict],
    local_dir: Path,
) -> List[dict]:
    """Return a list of action dicts: {type, path, ...}."""
    actions = []

    remote_map: Dict[str, dict] = {}
    for rf in remote_files:
        if rf.get("kind") == "folder":
            continue
        name = rf.get("name", "")
        if not name:
            continue
        remote_map[name] = rf

    seen_remote_paths = set()

    for rel_path, rf in remote_map.items():
        seen_remote_paths.add(rel_path)
        if rel_path not in local_map:
            actions.append({
                "type": "pull",
                "path": rel_path,
                "file_id": str(rf.get("id", "")),
                "reason": "remote-only",
            })
        else:
            local_mtime = local_map[rel_path]["mtime"]
            remote_updated_at = rf.get("updated_at")
            if remote_updated_at:
                try:
                    remote_ts = _parse_iso(remote_updated_at)
                    if local_mtime > remote_ts + 1:
                        actions.append({
                            "type": "push",
                            "path": rel_path,
                            "kind": rf.get("kind", "file"),
                            "reason": "local newer",
                        })
                    elif remote_ts > local_mtime + 1:
                        actions.append({
                            "type": "pull",
                            "path": rel_path,
                            "file_id": str(rf.get("id", "")),
                            "reason": "remote newer",
                        })
                except (ValueError, OSError):
                    pass

    for rel_path in local_map:
        if rel_path not in seen_remote_paths:
            actions.append({
                "type": "push",
                "path": rel_path,
                "kind": "file",
                "reason": "local-only",
            })

    return actions


def _parse_iso(ts: str) -> float:
    """Parse an ISO-8601 UTC string to a POSIX timestamp."""
    ts = ts.rstrip("Z")
    try:
        dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    except ValueError:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    return dt.timestamp()


# ---------------------------------------------------------------------------
# Pull (download)
# ---------------------------------------------------------------------------

def _pull_file(
    api_url: str,
    pid: str,
    token: str,
    file_id: str,
    dest: Path,
) -> bool:
    """Download a remote file to dest. Returns True on success."""
    url = f"{api_url}/api/projects/{pid}/files/{file_id}/download"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    delays = list(_RETRY_DELAYS)
    last_err = ""
    for delay in [0] + delays:
        if delay:
            time.sleep(delay)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                print(f"  error pulling {dest.name}: HTTP {exc.code}", file=sys.stderr)
                return False
            last_err = f"HTTP {exc.code}"
            continue
        except urllib.error.URLError as exc:
            last_err = f"network: {exc.reason}"
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".kerf_sync_")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
        except OSError as exc:
            print(f"  error writing {dest}: {exc}", file=sys.stderr)
            return False

        _maybe_hydrate(dest, api_url, pid, token)
        return True

    print(f"  error pulling {dest.name}: {last_err}", file=sys.stderr)
    return False


def _maybe_hydrate(path: Path, api_url: str, pid: str, token: str) -> None:
    """If path is an LFS pointer stub, hydrate it in place."""
    try:
        from kerf_cli.hydrate import _detect_stub, _hydrate_file  # noqa: PLC0415
        result = _detect_stub(path)
        if result is not None:
            oid, size = result
            _hydrate_file(path, oid, size, pid, api_url, token)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Push (upload)
# ---------------------------------------------------------------------------

def _push_file(
    api_url: str,
    pid: str,
    token: str,
    local_path: Path,
    rel_path: str,
    kind: str = "file",
) -> bool:
    """Upload a local file to the project. Returns True on success."""
    try:
        content_bytes = local_path.read_bytes()
    except OSError as exc:
        print(f"  error reading {local_path}: {exc}", file=sys.stderr)
        return False

    try:
        content_text = content_bytes.decode("utf-8")
        is_text = True
    except UnicodeDecodeError:
        content_text = ""
        is_text = False

    name = Path(rel_path).name

    payload = json.dumps({
        "name": name,
        "kind": kind,
        "content": content_text if is_text else "",
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
            if exc.code in (400, 401, 403, 404):
                print(f"  error pushing {name}: HTTP {exc.code}", file=sys.stderr)
                return False
            last_err = f"HTTP {exc.code}"
            continue
        except urllib.error.URLError as exc:
            last_err = f"network: {exc.reason}"
            continue

    print(f"  error pushing {name}: {last_err}", file=sys.stderr)
    return False


# ---------------------------------------------------------------------------
# Display helper
# ---------------------------------------------------------------------------

def _print_action(action_type: str, path: str, reason: str, dry_run: bool) -> None:
    tag = "[dry-run] " if dry_run else ""
    print(f"  {tag}{action_type:<6}  {path}  ({reason})", file=sys.stderr)
