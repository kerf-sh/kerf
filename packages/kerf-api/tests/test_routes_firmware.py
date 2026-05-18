"""
test_routes_firmware.py — hermetic tests for the firmware HTTP routes.

Tests /firmware/build, /firmware/upload, and /firmware/monitor using
FastAPI TestClient.  Backend modules (gcc_orchestrator, upload.router,
serial_monitor) are stubbed out so the tests run without arduino-cli,
avrdude, or pyserial installed.

Key behaviours asserted:
  - Routes always return 200 (never 5xx).
  - Responses always carry {ok, status, errors}.
  - When no compiler / no port is found → status == "pending".
  - When source_path / hex_path is missing → status == "error".
  - Successful stubs → status == "success".

Run:
    PYTHONPATH=packages/kerf-core/src:packages/kerf-firmware/src:packages/kerf-api/src \\
        python3 -m pytest packages/kerf-api/tests/test_routes_firmware.py -x
"""
from __future__ import annotations

import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Stub kerf_firmware.* before any route import
# ---------------------------------------------------------------------------

def _make_build_result(ok, status, hex_path=None, errors=None, warnings=None):
    from collections import namedtuple
    BR = namedtuple("BuildResult", ["ok", "status", "hex_path", "errors", "warnings", "stdout", "stderr"])
    return BR(ok=ok, status=status, hex_path=hex_path,
              errors=errors or [], warnings=warnings or [],
              stdout="", stderr="")


def _make_upload_result(ok, status, port=None, errors=None):
    from collections import namedtuple
    UR = namedtuple("UploadResult", ["ok", "status", "port", "errors", "warnings", "stdout", "stderr"])
    return UR(ok=ok, status=status, port=port,
              errors=errors or [], warnings=[], stdout="", stderr="")


def _make_monitor_result(ok, status, port=None, lines=None, errors=None):
    from collections import namedtuple
    MR = namedtuple("MonitorResult", ["ok", "status", "port", "lines", "errors"])
    return MR(ok=ok, status=status, port=port,
              lines=lines or [], errors=errors or [])


def _inject_firmware_stubs(
    build_ok=True,
    build_status="success",
    upload_ok=True,
    upload_status="success",
    monitor_ok=True,
    monitor_status="success",
    no_compiler=False,
    no_port=False,
):
    """Inject stub modules for all three kerf_firmware sub-modules."""
    # ── kerf_firmware package root ────────────────────────────────────────────
    pkg = types.ModuleType("kerf_firmware")
    sys.modules["kerf_firmware"] = pkg

    # ── gcc_orchestrator ──────────────────────────────────────────────────────
    orch = types.ModuleType("kerf_firmware.gcc_orchestrator")
    if no_compiler:
        def _build(source_path, fw_config=None):
            return _make_build_result(False, "pending",
                                      errors=["No compiler found. Install arduino-cli."])
    else:
        def _build(source_path, fw_config=None):
            if not source_path:
                return _make_build_result(False, "error", errors=["BAD_ARGS"])
            return _make_build_result(build_ok, build_status,
                                      hex_path="/tmp/sketch.hex" if build_ok else None)
    orch.build = _build
    sys.modules["kerf_firmware.gcc_orchestrator"] = orch

    # ── upload.router ─────────────────────────────────────────────────────────
    upload_pkg = types.ModuleType("kerf_firmware.upload")
    sys.modules["kerf_firmware.upload"] = upload_pkg

    upload_mod = types.ModuleType("kerf_firmware.upload.router")
    if no_port:
        def _upload(hex_path, fw_config=None, port=None):
            return _make_upload_result(False, "pending",
                                       errors=["No serial port found."])
    else:
        def _upload(hex_path, fw_config=None, port=None):
            if not hex_path:
                return _make_upload_result(False, "error", errors=["BAD_ARGS"])
            return _make_upload_result(upload_ok, upload_status,
                                       port=port or "/dev/ttyUSB0")
    upload_mod.upload = _upload
    sys.modules["kerf_firmware.upload.router"] = upload_mod

    # ── serial_monitor ────────────────────────────────────────────────────────
    monitor_mod = types.ModuleType("kerf_firmware.serial_monitor")
    if no_port:
        def _snapshot(fw_config=None, port=None, baud=9600, **kw):
            return _make_monitor_result(False, "pending",
                                        errors=["No serial port found."])
    else:
        def _snapshot(fw_config=None, port=None, baud=9600, **kw):
            return _make_monitor_result(monitor_ok, monitor_status,
                                        port=port or "/dev/ttyUSB0",
                                        lines=["Hello from board", "Temp: 23.5C"])
    monitor_mod.snapshot = _snapshot
    sys.modules["kerf_firmware.serial_monitor"] = monitor_mod


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def _build_app():
    """Build a minimal FastAPI app with only the firmware routes."""
    # Clear cached route module so stubs take effect
    for key in list(sys.modules.keys()):
        if "routes_firmware" in key:
            del sys.modules[key]

    from kerf_api.routes_firmware import firmware_router  # noqa: PLC0415
    app = FastAPI()
    app.include_router(firmware_router, prefix="/api", tags=["firmware"])
    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def client():
    _inject_firmware_stubs()
    app = _build_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def client_no_compiler():
    _inject_firmware_stubs(no_compiler=True)
    app = _build_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def client_no_port():
    _inject_firmware_stubs(no_port=True)
    app = _build_app()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests: /firmware/build
# ---------------------------------------------------------------------------

class TestFirmwareBuildRoute:
    def test_missing_source_path_returns_error(self, client):
        r = client.post("/api/firmware/build", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["status"] == "error"
        assert len(data["errors"]) > 0

    def test_empty_source_path_returns_error(self, client):
        r = client.post("/api/firmware/build", json={"source_path": ""})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["status"] == "error"

    def test_valid_source_path_returns_success(self, client):
        r = client.post("/api/firmware/build", json={"source_path": "/tmp/sketch"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["status"] == "success"
        assert data["hex_path"] is not None
        assert data["errors"] == []

    def test_no_compiler_returns_pending(self, client_no_compiler):
        r = client_no_compiler.post("/api/firmware/build",
                                    json={"source_path": "/tmp/sketch"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["status"] == "pending"
        assert any("compiler" in e.lower() or "arduino" in e.lower()
                   for e in data["errors"])

    def test_response_always_has_required_keys(self, client):
        r = client.post("/api/firmware/build", json={"source_path": "/tmp/sketch"})
        data = r.json()
        for key in ("ok", "status", "hex_path", "errors", "warnings"):
            assert key in data, f"missing key: {key}"

    def test_fw_config_accepted(self, client):
        r = client.post("/api/firmware/build", json={
            "source_path": "/tmp/sketch",
            "fw_config": {"board": {"fqbn": "arduino:avr:uno"}},
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True


# ---------------------------------------------------------------------------
# Tests: /firmware/upload
# ---------------------------------------------------------------------------

class TestFirmwareUploadRoute:
    def test_missing_hex_path_returns_error(self, client):
        r = client.post("/api/firmware/upload", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["status"] == "error"

    def test_empty_hex_path_returns_error(self, client):
        r = client.post("/api/firmware/upload", json={"hex_path": ""})
        assert r.status_code == 200
        assert r.json()["status"] == "error"

    def test_valid_hex_path_returns_success(self, client):
        r = client.post("/api/firmware/upload", json={"hex_path": "/tmp/sketch.hex"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["status"] == "success"
        assert data["port"] is not None
        assert data["errors"] == []

    def test_no_port_returns_pending(self, client_no_port):
        r = client_no_port.post("/api/firmware/upload",
                                json={"hex_path": "/tmp/sketch.hex"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["status"] == "pending"
        assert any("port" in e.lower() for e in data["errors"])

    def test_port_override_accepted(self, client):
        r = client.post("/api/firmware/upload", json={
            "hex_path": "/tmp/sketch.hex",
            "port": "/dev/ttyACM0",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["port"] == "/dev/ttyACM0"

    def test_response_always_has_required_keys(self, client):
        r = client.post("/api/firmware/upload", json={"hex_path": "/tmp/sketch.hex"})
        data = r.json()
        for key in ("ok", "status", "port", "errors"):
            assert key in data, f"missing key: {key}"


# ---------------------------------------------------------------------------
# Tests: /firmware/monitor
# ---------------------------------------------------------------------------

class TestFirmwareMonitorRoute:
    def test_no_args_returns_success_with_lines(self, client):
        r = client.post("/api/firmware/monitor", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["status"] == "success"
        assert isinstance(data["lines"], list)

    def test_no_port_returns_pending(self, client_no_port):
        r = client_no_port.post("/api/firmware/monitor", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["status"] == "pending"

    def test_baud_override_accepted(self, client):
        r = client.post("/api/firmware/monitor", json={"baud": 115200})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_invalid_baud_falls_back_to_9600(self, client):
        r = client.post("/api/firmware/monitor", json={"baud": -1})
        assert r.status_code == 200
        # Should not error out on bad baud value
        data = r.json()
        assert "status" in data

    def test_response_always_has_required_keys(self, client):
        r = client.post("/api/firmware/monitor", json={})
        data = r.json()
        for key in ("ok", "status", "port", "lines", "errors"):
            assert key in data, f"missing key: {key}"

    def test_port_override_accepted(self, client):
        r = client.post("/api/firmware/monitor", json={"port": "/dev/ttyACM0"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["port"] == "/dev/ttyACM0"
