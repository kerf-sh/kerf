"""Tests for the OpenLane/OpenROAD RTL-to-GDS-II flow seed.

Coverage:
- config.json shape matches OpenLane spec keys
- subprocess receives expected argv (contains 'openlane' or 'flow.tcl')
- pending-sentinel path when openlane is absent from PATH
- FlowResult fields are populated correctly
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List
from unittest import mock

import pytest

# Ensure the package is importable when run via PYTHONPATH
sys.path.insert(
    0,
    str(Path(__file__).parent.parent / "src"),
)

from kerf_silicon.openlane.config import build_config, write_config
from kerf_silicon.openlane.flow import FlowResult, run_flow, FLOW_STEPS, _find_openlane_cmd


# ---------------------------------------------------------------------------
# config.py tests
# ---------------------------------------------------------------------------


class TestBuildConfig:
    def test_required_keys_present(self):
        cfg = build_config("counter", ["rtl/counter.v"])
        for key in ("DESIGN_NAME", "VERILOG_FILES", "CLOCK_PORT", "CLOCK_PERIOD", "PDK", "DIE_AREA"):
            assert key in cfg, f"Missing OpenLane config key: {key}"

    def test_design_name(self):
        cfg = build_config("my_adder", ["src/adder.v"])
        assert cfg["DESIGN_NAME"] == "my_adder"

    def test_verilog_files_list(self):
        files = ["rtl/a.v", "rtl/b.v"]
        cfg = build_config("top", files)
        assert cfg["VERILOG_FILES"] == files

    def test_default_clock_port(self):
        cfg = build_config("top", ["top.v"])
        assert cfg["CLOCK_PORT"] == "clk"

    def test_default_clock_period(self):
        cfg = build_config("top", ["top.v"])
        assert cfg["CLOCK_PERIOD"] == 10.0

    def test_default_pdk(self):
        cfg = build_config("top", ["top.v"])
        assert cfg["PDK"] == "sky130A"

    def test_default_die_area(self):
        cfg = build_config("top", ["top.v"])
        assert cfg["DIE_AREA"] == [0, 0, 100, 100]

    def test_custom_clock_period(self):
        cfg = build_config("top", ["top.v"], clock_period=5.0)
        assert cfg["CLOCK_PERIOD"] == 5.0

    def test_custom_pdk(self):
        cfg = build_config("top", ["top.v"], pdk="gf180mcuD")
        assert cfg["PDK"] == "gf180mcuD"

    def test_custom_die_area(self):
        cfg = build_config("top", ["top.v"], die_area=(0, 0, 200, 200))
        assert cfg["DIE_AREA"] == [0, 0, 200, 200]

    def test_die_area_is_list(self):
        """DIE_AREA must be a JSON-serialisable list, not a tuple."""
        cfg = build_config("top", ["top.v"])
        assert isinstance(cfg["DIE_AREA"], list)

    def test_clock_period_is_float(self):
        cfg = build_config("top", ["top.v"])
        assert isinstance(cfg["CLOCK_PERIOD"], float)

    def test_verilog_files_is_list_copy(self):
        """Mutating the original list must not affect the config."""
        original = ["a.v"]
        cfg = build_config("top", original)
        original.append("b.v")
        assert cfg["VERILOG_FILES"] == ["a.v"]

    def test_empty_design_name_raises(self):
        with pytest.raises(ValueError, match="design_name"):
            build_config("", ["top.v"])

    def test_empty_verilog_files_raises(self):
        with pytest.raises(ValueError, match="verilog_files"):
            build_config("top", [])

    def test_negative_clock_period_raises(self):
        with pytest.raises(ValueError, match="clock_period"):
            build_config("top", ["top.v"], clock_period=-1.0)

    def test_config_is_json_serialisable(self):
        cfg = build_config("top", ["top.v"])
        dumped = json.dumps(cfg)
        loaded = json.loads(dumped)
        assert loaded["DESIGN_NAME"] == "top"


class TestWriteConfig:
    def test_writes_json_file(self, tmp_path):
        cfg = build_config("top", ["top.v"])
        dest = write_config(cfg, tmp_path / "config.json")
        assert dest.exists()
        with open(dest) as f:
            loaded = json.load(f)
        assert loaded["DESIGN_NAME"] == "top"

    def test_creates_parent_dirs(self, tmp_path):
        cfg = build_config("top", ["top.v"])
        dest = write_config(cfg, tmp_path / "run" / "sub" / "config.json")
        assert dest.exists()

    def test_returns_resolved_path(self, tmp_path):
        cfg = build_config("top", ["top.v"])
        dest = write_config(cfg, tmp_path / "config.json")
        assert dest.is_absolute()


# ---------------------------------------------------------------------------
# flow.py — pending sentinel tests
# ---------------------------------------------------------------------------


class TestPendingSentinel:
    def test_pending_when_openlane_absent(self):
        """When openlane is not on PATH the flow must return status='pending'."""
        with mock.patch("kerf_silicon.openlane.flow.shutil.which", return_value=None), \
             mock.patch.dict(os.environ, {"OPENLANE_ROOT": ""}, clear=False):
            result = run_flow("counter", ["counter.v"])
        assert result.status == "pending"

    def test_pending_has_warning(self):
        with mock.patch("kerf_silicon.openlane.flow.shutil.which", return_value=None), \
             mock.patch.dict(os.environ, {"OPENLANE_ROOT": ""}, clear=False):
            result = run_flow("counter", ["counter.v"])
        assert result.warnings, "Expected at least one warning in pending result"
        assert any("openlane" in w.lower() for w in result.warnings)

    def test_pending_gds_path_empty(self):
        with mock.patch("kerf_silicon.openlane.flow.shutil.which", return_value=None), \
             mock.patch.dict(os.environ, {"OPENLANE_ROOT": ""}, clear=False):
            result = run_flow("counter", ["counter.v"])
        assert result.gds_path == ""

    def test_pending_returncode_none(self):
        with mock.patch("kerf_silicon.openlane.flow.shutil.which", return_value=None), \
             mock.patch.dict(os.environ, {"OPENLANE_ROOT": ""}, clear=False):
            result = run_flow("counter", ["counter.v"])
        assert result.returncode is None


# ---------------------------------------------------------------------------
# flow.py — subprocess argv tests
# ---------------------------------------------------------------------------


class TestSubprocessArgv:
    """Verify that run_flow passes the correct command to subprocess.run."""

    def _mock_run(self, captured_cmds: list, returncode: int = 0):
        """Return a mock for subprocess.run that records the command."""
        def _fake_run(cmd, **kwargs):
            captured_cmds.append(cmd)
            # Write an empty log file if stdout kwarg is a file
            if hasattr(kwargs.get("stdout"), "write"):
                pass
            proc = mock.MagicMock()
            proc.returncode = returncode
            return proc

        return _fake_run

    def test_openlane2_cmd_contains_openlane(self, tmp_path):
        """When 'openlane' is on PATH the subprocess command must include 'openlane'."""
        captured: list = []

        with mock.patch("kerf_silicon.openlane.flow.shutil.which", return_value="/usr/bin/openlane"), \
             mock.patch("kerf_silicon.openlane.flow.subprocess.run", side_effect=self._mock_run(captured)):
            run_flow("adder", ["adder.v"], run_dir=str(tmp_path))

        assert captured, "subprocess.run was not called"
        cmd = captured[0]
        assert any("openlane" in part for part in cmd), (
            f"Expected 'openlane' in command, got: {cmd}"
        )

    def test_openlane2_cmd_contains_config_json(self, tmp_path):
        """The config.json path must appear in the subprocess command."""
        captured: list = []

        with mock.patch("kerf_silicon.openlane.flow.shutil.which", return_value="/usr/bin/openlane"), \
             mock.patch("kerf_silicon.openlane.flow.subprocess.run", side_effect=self._mock_run(captured)):
            run_flow("adder", ["adder.v"], run_dir=str(tmp_path))

        cmd = captured[0]
        assert any("config.json" in part for part in cmd), (
            f"Expected 'config.json' in command, got: {cmd}"
        )

    def test_legacy_flow_tcl_cmd_contains_flow_tcl(self, tmp_path):
        """When only OPENLANE_ROOT/flow.tcl exists the command must reference flow.tcl."""
        captured: list = []

        fake_tcl = tmp_path / "flow.tcl"
        fake_tcl.write_text("# stub")

        def _which(name: str):
            if name == "tclsh":
                return "/usr/bin/tclsh"
            return None  # openlane not found

        with mock.patch("kerf_silicon.openlane.flow.shutil.which", side_effect=_which), \
             mock.patch.dict(os.environ, {"OPENLANE_ROOT": str(tmp_path)}, clear=False), \
             mock.patch("kerf_silicon.openlane.flow.subprocess.run", side_effect=self._mock_run(captured)):
            run_flow("counter", ["counter.v"], run_dir=str(tmp_path / "run"))

        assert captured, "subprocess.run was not called"
        cmd = captured[0]
        assert any("flow.tcl" in part for part in cmd), (
            f"Expected 'flow.tcl' in command, got: {cmd}"
        )

    def test_successful_run_returns_success(self, tmp_path):
        """Zero exit code from subprocess → status='success'."""
        captured: list = []

        with mock.patch("kerf_silicon.openlane.flow.shutil.which", return_value="/usr/bin/openlane"), \
             mock.patch("kerf_silicon.openlane.flow.subprocess.run", side_effect=self._mock_run(captured, returncode=0)):
            result = run_flow("adder", ["adder.v"], run_dir=str(tmp_path))

        assert result.status == "success"
        assert result.returncode == 0

    def test_nonzero_exit_returns_error(self, tmp_path):
        """Non-zero exit code from subprocess → status='error'."""
        captured: list = []

        with mock.patch("kerf_silicon.openlane.flow.shutil.which", return_value="/usr/bin/openlane"), \
             mock.patch("kerf_silicon.openlane.flow.subprocess.run", side_effect=self._mock_run(captured, returncode=1)):
            result = run_flow("adder", ["adder.v"], run_dir=str(tmp_path))

        assert result.status == "error"
        assert result.returncode == 1

    def test_log_path_set(self, tmp_path):
        """log_path must be populated when subprocess is launched."""
        with mock.patch("kerf_silicon.openlane.flow.shutil.which", return_value="/usr/bin/openlane"), \
             mock.patch("kerf_silicon.openlane.flow.subprocess.run", side_effect=self._mock_run([])):
            result = run_flow("adder", ["adder.v"], run_dir=str(tmp_path))

        assert result.log_path != ""
        assert "flow.log" in result.log_path


# ---------------------------------------------------------------------------
# FlowResult dataclass
# ---------------------------------------------------------------------------


class TestFlowResult:
    def test_default_fields(self):
        r = FlowResult(status="pending")
        assert r.gds_path == ""
        assert r.log_path == ""
        assert r.returncode is None
        assert r.warnings == []

    def test_field_assignment(self):
        r = FlowResult(status="success", gds_path="/out/top.gds", log_path="/out/flow.log", returncode=0)
        assert r.status == "success"
        assert r.gds_path == "/out/top.gds"
        assert r.returncode == 0


# ---------------------------------------------------------------------------
# FLOW_STEPS constant
# ---------------------------------------------------------------------------


class TestFlowSteps:
    def test_flow_steps_present(self):
        """FLOW_STEPS must list the expected EDA stages."""
        expected = {"synthesis", "floorplan", "placement", "cts", "routing", "gds_out"}
        assert expected.issubset(set(FLOW_STEPS)), (
            f"Missing steps: {expected - set(FLOW_STEPS)}"
        )

    def test_flow_steps_ordered(self):
        """synthesis must precede routing in the step list."""
        assert FLOW_STEPS.index("synthesis") < FLOW_STEPS.index("routing")
