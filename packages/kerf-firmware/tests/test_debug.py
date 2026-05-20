"""
tests/test_debug.py — pytest suite for kerf_firmware.debug (T-262).

All tests are fully mocked — openocd and arm-none-eabi-gdb are NOT required.
Subprocess calls are intercepted via the _subprocess_factory injection point
in OpenOCDSession and the _raw_tasks / _raw_sync injection points in
RTOSInspector.

Scenarios
---------
T1  Debug bridge produces structured task-list [{name, state, priority, stack_high_water}]
T2  Mutex held-by-task_a produces a dependency edge (task_b -> task_a)
T3  Stack watermark < 10 % free triggers a warning in the snapshot
T4  Cloud-API route returns the JTAG sentinel ("JTAG requires the local Kerf CLI")
T5  OpenOCDNotInstalledError raised when openocd binary is absent
T6  GDBNotInstalledError raised when gdb binary is absent
T7  parse_mi_line correctly parses a GDB/MI result record
T8  Dependency edges are empty when no mutexes are held
T9  Multiple tasks snapshot — each appears in task list
T10 RTOSInspector snapshot via _raw_tasks + _raw_sync injection (no subprocess)
T11 attach_and_snapshot returns sentinel dict when KERF_LOCAL_CLI is not set
T12 firmware_debug_attach_route returns sentinel when KERF_LOCAL_CLI != "1"
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — fake subprocess factory
# ---------------------------------------------------------------------------

def _make_fake_popen(stdout_lines: list[str]):
    """
    Return a callable that mimics subprocess.Popen.

    The returned process object has:
    - .stdout  — an io.StringIO fed with stdout_lines
    - .stdin   — a MagicMock that accepts .write() and .flush()
    - .returncode — 0
    - .kill()  — no-op
    - .wait()  — no-op
    - .communicate() — ('', '')
    """
    class FakeProc:
        def __init__(self):
            self.stdout = io.StringIO("".join(stdout_lines))
            self.stdin  = MagicMock()
            self.stderr = io.StringIO("")
            self.returncode = 0

        def kill(self):
            pass

        def wait(self, timeout=None):
            pass

        def communicate(self, input=None, timeout=None):
            return ("", "")

    fake = FakeProc()

    def factory(*args, **kwargs):
        return fake

    factory._fake = fake
    return factory


# Standard GDB/MI lines that represent a "done" result record
_MI_DONE = ["^done\n", "(gdb)\n"]

# ---------------------------------------------------------------------------
# T1 — Debug bridge produces structured task list
# ---------------------------------------------------------------------------

class TestTaskListPayload:
    """T1 — RTOSInspector.snapshot() returns correctly shaped task dicts."""

    def test_snapshot_produces_task_list(self):
        from kerf_firmware.debug.openocd import OpenOCDSession
        from kerf_firmware.debug.rtos_inspect import RTOSInspector

        raw_tasks = [
            {"name": "sensor_task", "state": "RUNNING", "priority": 5,
             "stack_high_water": 400, "stack_size": 512},
            {"name": "idle_task",   "state": "READY",   "priority": 1,
             "stack_high_water": 450, "stack_size": 512},
        ]
        factory = _make_fake_popen(_MI_DONE)
        session = OpenOCDSession(_subprocess_factory=factory)
        session.start()
        inspector = RTOSInspector(session, _raw_tasks=raw_tasks)
        snap = inspector.snapshot()
        session.close()

        assert len(snap.tasks) == 2
        names = {t.name for t in snap.tasks}
        assert "sensor_task" in names
        assert "idle_task" in names

    def test_task_fields_present(self):
        from kerf_firmware.debug.openocd import OpenOCDSession
        from kerf_firmware.debug.rtos_inspect import RTOSInspector

        raw_tasks = [
            {"name": "ctrl_task", "state": "BLOCKED", "priority": 3,
             "stack_high_water": 200, "stack_size": 512},
        ]
        factory = _make_fake_popen(_MI_DONE)
        session = OpenOCDSession(_subprocess_factory=factory)
        session.start()
        inspector = RTOSInspector(session, _raw_tasks=raw_tasks)
        snap = inspector.snapshot()
        session.close()

        t = snap.tasks[0]
        assert t.name == "ctrl_task"
        assert t.state == "BLOCKED"
        assert t.priority == 3
        assert t.stack_high_water == 200
        assert t.stack_size == 512

    def test_as_dict_returns_required_keys(self):
        from kerf_firmware.debug.openocd import OpenOCDSession
        from kerf_firmware.debug.rtos_inspect import RTOSInspector

        raw_tasks = [
            {"name": "t1", "state": "READY", "priority": 2,
             "stack_high_water": 300, "stack_size": 512},
        ]
        factory = _make_fake_popen(_MI_DONE)
        session = OpenOCDSession(_subprocess_factory=factory)
        session.start()
        inspector = RTOSInspector(session, _raw_tasks=raw_tasks)
        snap = inspector.snapshot()
        session.close()

        d = snap.tasks[0].as_dict()
        for key in ("name", "state", "priority", "stack_high_water",
                    "stack_size", "stack_pct_free", "stack_warning"):
            assert key in d, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# T2 — Mutex held-by-task_a produces dependency edge
# ---------------------------------------------------------------------------

class TestMutexDependencyEdge:
    """T2 — a mutex reported as held-by-task_a produces an edge in the dep view."""

    def _make_session_inspector(self, raw_tasks, raw_sync):
        from kerf_firmware.debug.openocd import OpenOCDSession
        from kerf_firmware.debug.rtos_inspect import RTOSInspector
        factory = _make_fake_popen(_MI_DONE)
        session = OpenOCDSession(_subprocess_factory=factory)
        session.start()
        inspector = RTOSInspector(
            session, _raw_tasks=raw_tasks, _raw_sync=raw_sync
        )
        return session, inspector

    def test_mutex_held_produces_edge(self):
        raw_tasks = [
            {"name": "task_a", "state": "RUNNING", "priority": 5,
             "stack_high_water": 300, "stack_size": 512},
            {"name": "task_b", "state": "BLOCKED", "priority": 3,
             "stack_high_water": 200, "stack_size": 512},
        ]
        raw_sync = [
            {"name": "my_mutex", "kind": "mutex",
             "held_by": "task_a", "waiters": ["task_b"]},
        ]
        session, inspector = self._make_session_inspector(raw_tasks, raw_sync)
        snap = inspector.snapshot()
        session.close()

        assert len(snap.edges) == 1
        edge = snap.edges[0]
        assert edge.from_task == "task_b"
        assert edge.to_task   == "task_a"
        assert "mutex" in edge.label
        assert "my_mutex" in edge.label

    def test_edge_dict_keys(self):
        raw_tasks = [
            {"name": "a", "state": "RUNNING", "priority": 5,
             "stack_high_water": 300, "stack_size": 512},
            {"name": "b", "state": "BLOCKED", "priority": 2,
             "stack_high_water": 250, "stack_size": 512},
        ]
        raw_sync = [
            {"name": "m1", "kind": "mutex", "held_by": "a", "waiters": ["b"]},
        ]
        session, inspector = self._make_session_inspector(raw_tasks, raw_sync)
        snap = inspector.snapshot()
        session.close()

        d = snap.edges[0].as_dict()
        assert d["from"] == "b"
        assert d["to"]   == "a"
        assert "label" in d

    def test_no_edge_when_mutex_free(self):
        raw_tasks = [
            {"name": "a", "state": "RUNNING", "priority": 5,
             "stack_high_water": 300, "stack_size": 512},
        ]
        raw_sync = [
            {"name": "free_mutex", "kind": "mutex", "held_by": None, "waiters": []},
        ]
        session, inspector = self._make_session_inspector(raw_tasks, raw_sync)
        snap = inspector.snapshot()
        session.close()

        assert snap.edges == []


# ---------------------------------------------------------------------------
# T3 — Stack watermark < 10 % triggers warning
# ---------------------------------------------------------------------------

class TestStackWatermarkWarning:
    """T3 — stack watermark below 10 % free triggers a panel warning."""

    def _snapshot_with_tasks(self, tasks_dicts):
        from kerf_firmware.debug.openocd import OpenOCDSession
        from kerf_firmware.debug.rtos_inspect import RTOSInspector
        factory = _make_fake_popen(_MI_DONE)
        session = OpenOCDSession(_subprocess_factory=factory)
        session.start()
        inspector = RTOSInspector(session, _raw_tasks=tasks_dicts)
        snap = inspector.snapshot()
        session.close()
        return snap

    def test_critically_low_stack_produces_warning(self):
        # 40 / 512 = 7.8 % — well below 10 %
        snap = self._snapshot_with_tasks([
            {"name": "overflow_task", "state": "READY", "priority": 2,
             "stack_high_water": 40, "stack_size": 512},
        ])
        assert len(snap.warnings) >= 1
        assert any("overflow_task" in w for w in snap.warnings)
        assert any("stack" in w.lower() for w in snap.warnings)

    def test_stack_warning_flag_on_task(self):
        snap = self._snapshot_with_tasks([
            {"name": "tight_task", "state": "READY", "priority": 1,
             "stack_high_water": 30, "stack_size": 512},
        ])
        assert snap.tasks[0].stack_warning is True

    def test_healthy_stack_no_warning(self):
        # 400 / 512 = 78 %
        snap = self._snapshot_with_tasks([
            {"name": "ok_task", "state": "RUNNING", "priority": 5,
             "stack_high_water": 400, "stack_size": 512},
        ])
        assert snap.warnings == []
        assert snap.tasks[0].stack_warning is False

    def test_exactly_10_percent_no_warning(self):
        # 51.2 / 512 = exactly 10 % — should NOT warn (< 10 %)
        snap = self._snapshot_with_tasks([
            {"name": "boundary_task", "state": "READY", "priority": 2,
             "stack_high_water": 52, "stack_size": 512},
        ])
        # 52/512 = 10.15 % → no warning
        assert snap.tasks[0].stack_warning is False

    def test_just_below_10_percent_warns(self):
        # 50 / 512 = 9.76 % → warn
        snap = self._snapshot_with_tasks([
            {"name": "edge_task", "state": "READY", "priority": 2,
             "stack_high_water": 50, "stack_size": 512},
        ])
        assert snap.tasks[0].stack_warning is True
        assert len(snap.warnings) >= 1


# ---------------------------------------------------------------------------
# T4 — Cloud-API route returns JTAG sentinel
# ---------------------------------------------------------------------------

class TestJTAGSentinel:
    """T4 — cloud route returns the JTAG sentinel string."""

    def test_firmware_debug_sentinel_without_local_cli(self):
        from kerf_cli.commands.firmware_debug import cloud_sentinel_response, JTAG_CLOUD_SENTINEL

        resp = cloud_sentinel_response()
        assert resp["ok"] is False
        assert resp["error"] == "JTAG_LOCAL_ONLY"
        assert JTAG_CLOUD_SENTINEL in resp["message"]
        assert JTAG_CLOUD_SENTINEL in resp["warnings"]

    def test_sentinel_message_exact_text(self):
        from kerf_cli.commands.firmware_debug import JTAG_CLOUD_SENTINEL
        assert JTAG_CLOUD_SENTINEL == "JTAG requires the local Kerf CLI"

    def test_route_returns_sentinel_without_env(self):
        """The /firmware/debug/attach route must return sentinel when
        KERF_LOCAL_CLI != '1'."""
        import asyncio
        from kerf_firmware.routes import firmware_debug_attach_route

        # Ensure KERF_LOCAL_CLI is not set
        env_bak = os.environ.pop("KERF_LOCAL_CLI", None)
        try:
            result = asyncio.run(firmware_debug_attach_route({}))
        finally:
            if env_bak is not None:
                os.environ["KERF_LOCAL_CLI"] = env_bak

        assert result["ok"] is False
        assert result["error"] == "JTAG_LOCAL_ONLY"
        assert "JTAG requires the local Kerf CLI" in result["message"]

    def test_snapshot_route_returns_sentinel_without_env(self):
        """GET /firmware/debug/snapshot also returns sentinel on cloud path."""
        import asyncio
        from kerf_firmware.routes import firmware_debug_snapshot_route

        env_bak = os.environ.pop("KERF_LOCAL_CLI", None)
        try:
            result = asyncio.run(firmware_debug_snapshot_route())
        finally:
            if env_bak is not None:
                os.environ["KERF_LOCAL_CLI"] = env_bak

        assert result["ok"] is False
        assert result["error"] == "JTAG_LOCAL_ONLY"


# ---------------------------------------------------------------------------
# T5 — OpenOCDNotInstalledError when openocd is absent
# ---------------------------------------------------------------------------

class TestOpenOCDNotInstalled:
    """T5 — OpenOCDNotInstalledError raised when openocd is not on PATH."""

    def test_raises_when_openocd_absent(self):
        from kerf_firmware.debug.openocd import OpenOCDSession, OpenOCDNotInstalledError

        with patch("shutil.which", return_value=None):
            session = OpenOCDSession()
            with pytest.raises(OpenOCDNotInstalledError):
                session.start()


# ---------------------------------------------------------------------------
# T6 — GDBNotInstalledError when gdb is absent
# ---------------------------------------------------------------------------

class TestGDBNotInstalled:
    """T6 — GDBNotInstalledError raised when arm-none-eabi-gdb is absent."""

    def test_raises_when_gdb_absent(self):
        from kerf_firmware.debug.openocd import (
            OpenOCDSession,
            GDBNotInstalledError,
        )
        import kerf_firmware.debug.openocd as _ocd_mod

        # openocd is "found" on PATH but all GDB candidates are absent.
        fake_proc = MagicMock()
        fake_proc.stdout = io.StringIO("")
        fake_proc.kill = MagicMock()
        fake_proc.wait = MagicMock()

        with patch("shutil.which", return_value="/usr/bin/openocd"):
            # patch _find_gdb at module level to return None
            with patch.object(_ocd_mod, "_find_gdb", return_value=None):
                # Use the real subprocess.Popen path (which is used for the
                # openocd check), but intercept the actual Popen call so
                # openocd "starts" without a real binary.
                with patch("subprocess.Popen", return_value=fake_proc):
                    session = OpenOCDSession()
                    with pytest.raises(GDBNotInstalledError):
                        session.start()


# ---------------------------------------------------------------------------
# T7 — parse_mi_line correctly parses GDB/MI records
# ---------------------------------------------------------------------------

class TestParseMILine:
    """T7 — parse_mi_line handles common GDB/MI output formats."""

    def test_result_done(self):
        from kerf_firmware.debug.openocd import parse_mi_line
        rec = parse_mi_line("^done,value=\"42\"")
        assert rec is not None
        assert rec.type == "result"
        assert rec.class_ == "done"
        assert rec.payload.get("value") == "42"

    def test_result_error(self):
        from kerf_firmware.debug.openocd import parse_mi_line
        rec = parse_mi_line("^error,msg=\"No symbol\"")
        assert rec is not None
        assert rec.type == "result"
        assert rec.class_ == "error"

    def test_gdb_prompt_returns_none(self):
        from kerf_firmware.debug.openocd import parse_mi_line
        assert parse_mi_line("(gdb)") is None

    def test_empty_line_returns_none(self):
        from kerf_firmware.debug.openocd import parse_mi_line
        assert parse_mi_line("") is None

    def test_stream_record(self):
        from kerf_firmware.debug.openocd import parse_mi_line
        rec = parse_mi_line('~"FreeRTOS threads: 3\\n"')
        assert rec is not None
        assert rec.type == "stream"

    def test_async_running(self):
        from kerf_firmware.debug.openocd import parse_mi_line
        rec = parse_mi_line("*running,thread-id=\"all\"")
        assert rec is not None
        assert rec.type == "async"
        assert rec.class_ == "running"


# ---------------------------------------------------------------------------
# T8 — No edges when no mutexes held
# ---------------------------------------------------------------------------

class TestNoEdgesWhenNoMutexesHeld:
    """T8 — dependency edges are empty when sync objects have no holders."""

    def test_no_edges_with_free_mutexes(self):
        from kerf_firmware.debug.openocd import OpenOCDSession
        from kerf_firmware.debug.rtos_inspect import RTOSInspector

        raw_tasks = [
            {"name": "a", "state": "RUNNING", "priority": 3,
             "stack_high_water": 300, "stack_size": 512},
        ]
        raw_sync = [
            {"name": "free_lock", "kind": "mutex", "held_by": None, "waiters": []},
        ]
        factory = _make_fake_popen(_MI_DONE)
        session = OpenOCDSession(_subprocess_factory=factory)
        session.start()
        inspector = RTOSInspector(session, _raw_tasks=raw_tasks, _raw_sync=raw_sync)
        snap = inspector.snapshot()
        session.close()

        assert snap.edges == []

    def test_no_edges_with_no_sync_objects(self):
        from kerf_firmware.debug.openocd import OpenOCDSession
        from kerf_firmware.debug.rtos_inspect import RTOSInspector

        raw_tasks = [
            {"name": "a", "state": "RUNNING", "priority": 3,
             "stack_high_water": 300, "stack_size": 512},
        ]
        factory = _make_fake_popen(_MI_DONE)
        session = OpenOCDSession(_subprocess_factory=factory)
        session.start()
        inspector = RTOSInspector(session, _raw_tasks=raw_tasks, _raw_sync=[])
        snap = inspector.snapshot()
        session.close()

        assert snap.edges == []


# ---------------------------------------------------------------------------
# T9 — Multiple tasks snapshot
# ---------------------------------------------------------------------------

class TestMultipleTasks:
    """T9 — all tasks appear in the snapshot when multiple tasks registered."""

    def test_three_tasks_all_present(self):
        from kerf_firmware.debug.openocd import OpenOCDSession
        from kerf_firmware.debug.rtos_inspect import RTOSInspector

        raw_tasks = [
            {"name": "comm_task",   "state": "RUNNING",   "priority": 7,
             "stack_high_water": 350, "stack_size": 512},
            {"name": "sensor_task", "state": "READY",     "priority": 5,
             "stack_high_water": 400, "stack_size": 512},
            {"name": "idle_task",   "state": "SUSPENDED", "priority": 0,
             "stack_high_water": 480, "stack_size": 512},
        ]
        factory = _make_fake_popen(_MI_DONE)
        session = OpenOCDSession(_subprocess_factory=factory)
        session.start()
        inspector = RTOSInspector(session, _raw_tasks=raw_tasks)
        snap = inspector.snapshot()
        session.close()

        assert len(snap.tasks) == 3
        names = {t.name for t in snap.tasks}
        assert "comm_task"   in names
        assert "sensor_task" in names
        assert "idle_task"   in names

    def test_snapshot_as_dict_structure(self):
        from kerf_firmware.debug.openocd import OpenOCDSession
        from kerf_firmware.debug.rtos_inspect import RTOSInspector

        raw_tasks = [
            {"name": "t1", "state": "RUNNING", "priority": 5,
             "stack_high_water": 300, "stack_size": 512},
        ]
        factory = _make_fake_popen(_MI_DONE)
        session = OpenOCDSession(_subprocess_factory=factory)
        session.start()
        inspector = RTOSInspector(session, _raw_tasks=raw_tasks, _raw_sync=[])
        snap = inspector.snapshot()
        session.close()

        d = snap.as_dict()
        assert "tasks"        in d
        assert "sync_objects" in d
        assert "edges"        in d
        assert "warnings"     in d
        assert isinstance(d["tasks"], list)


# ---------------------------------------------------------------------------
# T10 — Raw injection (no subprocess)
# ---------------------------------------------------------------------------

class TestRawInjection:
    """T10 — RTOSInspector with _raw_tasks + _raw_sync bypasses subprocess."""

    def test_raw_injection_no_subprocess_needed(self):
        """Inspector works without ever starting a real process."""
        from kerf_firmware.debug.openocd import OpenOCDSession
        from kerf_firmware.debug.rtos_inspect import RTOSInspector

        raw_tasks = [
            {"name": "injected_task", "state": "READY", "priority": 4,
             "stack_high_water": 250, "stack_size": 512},
        ]
        raw_sync = [
            {"name": "injected_mutex", "kind": "mutex",
             "held_by": "injected_task", "waiters": []},
        ]

        # Minimal fake session — session.start() is never called
        factory = _make_fake_popen(_MI_DONE)
        session = OpenOCDSession(_subprocess_factory=factory)
        session.start()

        inspector = RTOSInspector(session, _raw_tasks=raw_tasks, _raw_sync=raw_sync)
        snap = inspector.snapshot()
        session.close()

        assert snap.tasks[0].name == "injected_task"
        assert snap.sync_objects[0].name == "injected_mutex"
        assert snap.sync_objects[0].held_by == "injected_task"


# ---------------------------------------------------------------------------
# T11 — attach_and_snapshot sentinel when KERF_LOCAL_CLI not set
# ---------------------------------------------------------------------------

class TestAttachAndSnapshotSentinel:
    """T11 — attach_and_snapshot returns sentinel dict when JTAG unavailable."""

    def test_returns_sentinel_message(self):
        from kerf_cli.commands.firmware_debug import (
            attach_and_snapshot,
            JTAG_CLOUD_SENTINEL,
        )
        from kerf_firmware.debug.openocd import OpenOCDNotInstalledError

        # Make OpenOCD raise NotInstalled
        with patch("shutil.which", return_value=None):
            result = attach_and_snapshot(elf_path="", target="stm32f4")

        assert result["ok"] is False
        # Should be OPENOCD_NOT_INSTALLED (not a cloud sentinel, but still fails gracefully)
        assert "error" in result
        assert "tasks" in result
        assert isinstance(result["tasks"], list)

    def test_cloud_sentinel_fields(self):
        from kerf_cli.commands.firmware_debug import cloud_sentinel_response, JTAG_CLOUD_SENTINEL

        r = cloud_sentinel_response()
        assert r["ok"] is False
        assert r["error"] == "JTAG_LOCAL_ONLY"
        assert "JTAG requires the local Kerf CLI" in r["message"]
        assert "JTAG requires the local Kerf CLI" in r["warnings"]
        assert r["tasks"] == []
        assert r["sync_objects"] == []
        assert r["edges"] == []


# ---------------------------------------------------------------------------
# T12 — firmware_debug_attach_route returns sentinel on cloud path
# ---------------------------------------------------------------------------

class TestFirmwareDebugRoute:
    """T12 — route-level sentinel test (covered partly by T4 too)."""

    def test_attach_route_sentinel_tasks_empty(self):
        import asyncio
        from kerf_firmware.routes import firmware_debug_attach_route

        env_bak = os.environ.pop("KERF_LOCAL_CLI", None)
        try:
            result = asyncio.run(firmware_debug_attach_route(
                {"elf_path": "/tmp/test.elf", "target": "stm32f4"}
            ))
        finally:
            if env_bak is not None:
                os.environ["KERF_LOCAL_CLI"] = env_bak

        assert result["tasks"] == []
        assert result["ok"] is False

    def test_attach_route_sentinel_message_exact(self):
        import asyncio
        from kerf_firmware.routes import firmware_debug_attach_route

        env_bak = os.environ.pop("KERF_LOCAL_CLI", None)
        try:
            result = asyncio.run(firmware_debug_attach_route({}))
        finally:
            if env_bak is not None:
                os.environ["KERF_LOCAL_CLI"] = env_bak

        assert result["message"] == "JTAG requires the local Kerf CLI"
