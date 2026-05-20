"""Tests for the T-324 sync daemon - sync_tick() deterministic contract.

Three canonical scenarios
--------------------------
1.  Edit on disk → next tick uploads (push).
2.  Edit in cloud → next tick downloads (pull).
3.  Concurrent edit (both sides changed) → conflict report, no clobber.

The API client is replaced by a lightweight ``FakeServer`` fixture so no
network, no real server, and no sleeping are required.  Each tick is driven
by calling ``sync_tick(state)`` directly.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from kerf_cli.sync import (
    FileSnapshot,
    SyncResult,
    SyncState,
    _build_local_map,
    _remote_sha,
    _sha256_file,
    sync_tick,
)


# ---------------------------------------------------------------------------
# FakeServer - in-memory server that mimics the Kerf API
# ---------------------------------------------------------------------------

class FakeServer:
    """Minimal in-memory Kerf project server for testing.

    Files are stored as ``{name: bytes}``.  Each mutation bumps
    ``_version[name]`` so ``updated_at`` changes - this is the signal that
    ``sync_tick`` detects as a remote change.
    """

    def __init__(self, initial: Optional[Dict[str, bytes]] = None):
        self._files: Dict[str, bytes] = dict(initial or {})
        self._versions: Dict[str, int] = {k: 1 for k in self._files}
        self._id_counter = 100

    # ---- server-side mutations -------------------------------------------

    def server_write(self, name: str, content: bytes) -> None:
        """Simulate a cloud-side edit (e.g. from the browser)."""
        if name not in self._files:
            self._id_counter += 1
        self._files[name] = content
        self._versions[name] = self._versions.get(name, 0) + 1

    def server_delete(self, name: str) -> None:
        self._files.pop(name, None)
        self._versions.pop(name, None)

    # ---- API surface mimicked by sync_tick -------------------------------

    def list_files(self) -> List[dict]:
        """Return a file list in the same shape as GET /api/projects/{pid}/files."""
        result = []
        for name, content in self._files.items():
            sha = hashlib.sha256(content).hexdigest()
            result.append({
                "id": f"id-{name}",
                "name": name,
                "kind": "file",
                # Use sha256 so _remote_sha() returns a stable change token.
                "sha256": sha,
                "updated_at": f"2020-01-01T00:00:0{self._versions.get(name, 1)}Z",
            })
        return result

    def download(self, file_id: str) -> Optional[bytes]:
        """Return file bytes by id (id is ``'id-{name}'``)."""
        name = file_id[len("id-"):]
        return self._files.get(name)

    def upload(self, name: str, content_bytes: bytes) -> bool:
        self._files[name] = content_bytes
        self._versions[name] = self._versions.get(name, 0) + 1
        return True


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------

def _make_patches(server: FakeServer, local_dir: Path):
    """Return a context manager that patches _list_remote_files, _pull_file,
    _push_file so sync_tick uses the FakeServer instead of real HTTP."""

    def fake_list(api_url, pid, token):
        return server.list_files()

    def fake_pull(api_url, pid, token, file_id, dest):
        content = server.download(file_id)
        if content is None:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return True

    def fake_push(api_url, pid, token, local_path, rel_path, kind="file"):
        content = local_path.read_bytes()
        server.upload(Path(rel_path).name, content)
        return True

    return [
        patch("kerf_cli.sync._list_remote_files", side_effect=fake_list),
        patch("kerf_cli.sync._pull_file", side_effect=fake_pull),
        patch("kerf_cli.sync._push_file", side_effect=fake_push),
    ]


def _apply_patches(patches):
    for p in patches:
        p.start()


def _stop_patches(patches):
    for p in patches:
        p.stop()


def _make_state(local_dir: Path) -> SyncState:
    return SyncState(
        api_url="http://fake",
        project_id="proj-1",
        local_dir=local_dir,
        token="token",
    )


def _run_tick(state: SyncState, server: FakeServer, local_dir: Path) -> SyncResult:
    """Run one tick with the FakeServer patches active."""
    patches = _make_patches(server, local_dir)
    _apply_patches(patches)
    try:
        result = sync_tick(state)
        # Update state (daemon loop responsibility).
        state.snapshots = result._new_snapshots  # type: ignore[attr-defined]
        state.tick += 1
        return result
    finally:
        _stop_patches(patches)


# ---------------------------------------------------------------------------
# Scenario 1 - edit on disk → next tick pushes
# ---------------------------------------------------------------------------

class TestLocalEditIsPushed:
    """Edit a file on disk between tick 0 and tick 1; verify push on tick 1."""

    def test_local_edit_triggers_push(self, tmp_path):
        server = FakeServer({"design.step": b"STEP v1"})
        local_dir = tmp_path / "proj"
        local_dir.mkdir()
        state = _make_state(local_dir)

        # Tick 0: initial sync - pulls the remote file to local.
        result0 = _run_tick(state, server, local_dir)
        assert "design.step" in result0.pulled, "tick 0 should pull the remote-only file"
        assert (local_dir / "design.step").read_bytes() == b"STEP v1"

        # Simulate user editing the file on disk.
        (local_dir / "design.step").write_bytes(b"STEP v2 edited locally")

        # Tick 1: local changed, remote unchanged → push.
        result1 = _run_tick(state, server, local_dir)
        assert "design.step" in result1.pushed, "tick 1 should push the local edit"
        assert not result1.conflicts
        # Verify the server received the new content.
        assert server._files["design.step"] == b"STEP v2 edited locally"

    def test_new_local_file_is_pushed(self, tmp_path):
        """A file that only exists locally should be pushed on tick 1."""
        server = FakeServer()
        local_dir = tmp_path / "proj"
        local_dir.mkdir()
        state = _make_state(local_dir)

        # Tick 0: nothing on either side.
        result0 = _run_tick(state, server, local_dir)
        assert not result0.pulled and not result0.pushed

        # Create a new local file.
        (local_dir / "notes.txt").write_bytes(b"hello world")

        # Tick 1: local-only → push.
        result1 = _run_tick(state, server, local_dir)
        assert "notes.txt" in result1.pushed
        assert server._files.get("notes.txt") == b"hello world"


# ---------------------------------------------------------------------------
# Scenario 2 - edit in cloud → next tick pulls
# ---------------------------------------------------------------------------

class TestRemoteEditIsPulled:
    """A cloud-side edit between tick 0 and tick 1 should be downloaded."""

    def test_remote_edit_triggers_pull(self, tmp_path):
        server = FakeServer({"part.step": b"STEP original"})
        local_dir = tmp_path / "proj"
        local_dir.mkdir()
        state = _make_state(local_dir)

        # Tick 0: initial sync - pulls remote file.
        result0 = _run_tick(state, server, local_dir)
        assert "part.step" in result0.pulled

        # Simulate a cloud-side edit (e.g. from the browser).
        server.server_write("part.step", b"STEP cloud-updated")

        # Tick 1: remote changed, local unchanged → pull.
        result1 = _run_tick(state, server, local_dir)
        assert "part.step" in result1.pulled, "tick 1 should pull the remote edit"
        assert not result1.conflicts
        assert (local_dir / "part.step").read_bytes() == b"STEP cloud-updated"

    def test_new_remote_file_is_pulled(self, tmp_path):
        """A file that appears remotely between ticks is pulled."""
        server = FakeServer()
        local_dir = tmp_path / "proj"
        local_dir.mkdir()
        state = _make_state(local_dir)

        # Tick 0: empty.
        _run_tick(state, server, local_dir)

        # New file appears on server.
        server.server_write("assembly.step", b"STEP assembly")

        # Tick 1: remote-only → pull.
        result1 = _run_tick(state, server, local_dir)
        assert "assembly.step" in result1.pulled
        assert (local_dir / "assembly.step").read_bytes() == b"STEP assembly"


# ---------------------------------------------------------------------------
# Scenario 3 - concurrent edit → conflict report, no clobber
# ---------------------------------------------------------------------------

class TestOccConflict:
    """Both sides change the same file between two ticks → conflict, no clobber."""

    def test_concurrent_edit_reports_conflict(self, tmp_path):
        server = FakeServer({"design.step": b"STEP v1"})
        local_dir = tmp_path / "proj"
        local_dir.mkdir()
        state = _make_state(local_dir)

        # Tick 0: pull initial state.
        result0 = _run_tick(state, server, local_dir)
        assert "design.step" in result0.pulled

        # Both sides change the same file concurrently.
        (local_dir / "design.step").write_bytes(b"STEP local-edit")
        server.server_write("design.step", b"STEP cloud-edit")

        # Tick 1: OCC conflict detected.
        result1 = _run_tick(state, server, local_dir)
        assert result1.conflicts, "conflict should be reported"
        assert result1.stop, "daemon should stop on OCC"
        assert any(c.path == "design.step" for c in result1.conflicts)
        # Neither side should have been clobbered.
        assert (local_dir / "design.step").read_bytes() == b"STEP local-edit"
        assert server._files["design.step"] == b"STEP cloud-edit"

    def test_conflict_includes_sha_info(self, tmp_path):
        """ConflictInfo carries prev+now SHAs for both sides."""
        server = FakeServer({"f.txt": b"v1"})
        local_dir = tmp_path / "proj"
        local_dir.mkdir()
        state = _make_state(local_dir)

        _run_tick(state, server, local_dir)  # tick 0

        (local_dir / "f.txt").write_bytes(b"local v2")
        server.server_write("f.txt", b"cloud v2")

        result = _run_tick(state, server, local_dir)  # tick 1
        assert result.conflicts
        c = result.conflicts[0]
        assert c.path == "f.txt"
        # prev SHAs should reflect v1 content.
        expected_prev = hashlib.sha256(b"v1").hexdigest()
        assert c.local_sha_prev == expected_prev
        assert c.remote_sha_prev == expected_prev
        # now SHAs should differ.
        assert c.local_sha_now != c.local_sha_prev
        assert c.remote_sha_now != c.remote_sha_prev

    def test_no_conflict_single_side_change(self, tmp_path):
        """If only one side changes, no conflict is reported."""
        server = FakeServer({"f.txt": b"v1"})
        local_dir = tmp_path / "proj"
        local_dir.mkdir()
        state = _make_state(local_dir)

        _run_tick(state, server, local_dir)  # tick 0

        # Only local changes.
        (local_dir / "f.txt").write_bytes(b"local v2")

        result = _run_tick(state, server, local_dir)  # tick 1
        assert not result.conflicts
        assert not result.stop
        assert "f.txt" in result.pushed


# ---------------------------------------------------------------------------
# Three-file project integration
# ---------------------------------------------------------------------------

class TestThreeFileProject:
    """Simulate a realistic 3-file project across multiple ticks."""

    def test_three_file_scenario(self, tmp_path):
        """
        Setup: remote has design.step, spec.pdf, notes.txt
        Tick 0: initial sync - all three pulled locally
        Tick 1: user edits notes.txt locally → pushed
        Tick 2: cloud updates design.step → pulled locally
        Tick 3: concurrent edit on spec.pdf → conflict
        """
        server = FakeServer({
            "design.step": b"STEP design v1",
            "spec.pdf": b"%PDF spec v1",
            "notes.txt": b"project notes v1",
        })
        local_dir = tmp_path / "proj"
        local_dir.mkdir()
        state = _make_state(local_dir)

        # Tick 0: initial pull.
        r0 = _run_tick(state, server, local_dir)
        assert len(r0.pulled) == 3
        assert not r0.pushed
        assert not r0.conflicts

        # Tick 1: local edit to notes.txt.
        (local_dir / "notes.txt").write_bytes(b"project notes v2 - local edit")
        r1 = _run_tick(state, server, local_dir)
        assert "notes.txt" in r1.pushed
        assert not r1.pulled
        assert not r1.conflicts

        # Tick 2: cloud updates design.step.
        server.server_write("design.step", b"STEP design v2 - cloud update")
        r2 = _run_tick(state, server, local_dir)
        assert "design.step" in r2.pulled
        assert not r2.pushed
        assert not r2.conflicts
        assert (local_dir / "design.step").read_bytes() == b"STEP design v2 - cloud update"

        # Tick 3: concurrent edit on spec.pdf.
        (local_dir / "spec.pdf").write_bytes(b"%PDF spec v2 - local edit")
        server.server_write("spec.pdf", b"%PDF spec v2 - cloud edit")
        r3 = _run_tick(state, server, local_dir)
        assert r3.conflicts
        assert r3.stop
        assert any(c.path == "spec.pdf" for c in r3.conflicts)
        # No clobber.
        assert (local_dir / "spec.pdf").read_bytes() == b"%PDF spec v2 - local edit"
        assert server._files["spec.pdf"] == b"%PDF spec v2 - cloud edit"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_project_no_actions(self, tmp_path):
        server = FakeServer()
        local_dir = tmp_path / "proj"
        local_dir.mkdir()
        state = _make_state(local_dir)

        result = _run_tick(state, server, local_dir)
        assert not result.pulled
        assert not result.pushed
        assert not result.conflicts
        assert not result.stop

    def test_idempotent_after_initial_sync(self, tmp_path):
        """Tick 1 with no changes after tick 0 should produce no actions."""
        server = FakeServer({"file.txt": b"content"})
        local_dir = tmp_path / "proj"
        local_dir.mkdir()
        state = _make_state(local_dir)

        _run_tick(state, server, local_dir)  # tick 0: pulls

        # Tick 1: nothing changed.
        result = _run_tick(state, server, local_dir)
        assert not result.pulled
        assert not result.pushed
        assert not result.conflicts

    def test_local_dir_created_if_missing(self, tmp_path):
        """sync_tick should tolerate a non-existent local_dir gracefully."""
        server = FakeServer({"file.txt": b"hello"})
        local_dir = tmp_path / "nonexistent"
        assert not local_dir.exists()
        state = _make_state(local_dir)

        local_dir.mkdir(parents=True, exist_ok=True)
        result = _run_tick(state, server, local_dir)
        assert "file.txt" in result.pulled


# ---------------------------------------------------------------------------
# Parser integration - --watch / --interval flags
# ---------------------------------------------------------------------------

class TestSyncParserDaemonFlags:
    def test_watch_flag_parsed(self):
        from kerf_cli.main import _build_parser
        args = _build_parser().parse_args(["sync", "p", "/d", "--watch"])
        assert args.watch is True

    def test_interval_flag_parsed(self):
        from kerf_cli.main import _build_parser
        args = _build_parser().parse_args(["sync", "p", "/d", "--watch", "--interval", "10"])
        assert args.interval == 10.0

    def test_interval_default(self):
        from kerf_cli.main import _build_parser
        args = _build_parser().parse_args(["sync", "p", "/d"])
        assert args.interval == 5.0
        assert args.watch is False
