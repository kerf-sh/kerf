"""
Tests for kerf_silicon.bridges.ghdl_bridge.

All subprocess calls are mocked so the suite runs without GHDL installed.
The "pending" path is exercised by temporarily hiding ghdl from shutil.which.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from kerf_silicon.bridges.ghdl_bridge import SimResult, simulate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_completed_process(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    """Return a fake CompletedProcess-like object."""
    mock = MagicMock(spec=subprocess.CompletedProcess)
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


# ---------------------------------------------------------------------------
# Pending path — ghdl not installed
# ---------------------------------------------------------------------------


class TestPendingWhenNoBinary:
    def test_returns_pending_status_when_ghdl_absent(self):
        with patch("shutil.which", return_value=None):
            result = simulate(["design.vhd"], "tb_top")
        assert result.status == "pending"

    def test_pending_log_contains_install_hint(self):
        with patch("shutil.which", return_value=None):
            result = simulate(["design.vhd"], "tb_top")
        assert "ghdl" in result.log.lower()
        # Should mention at least one install method
        assert "brew" in result.log or "apt" in result.log

    def test_pending_has_no_vcd_path(self):
        with patch("shutil.which", return_value=None):
            result = simulate(["design.vhd"], "tb_top")
        assert result.vcd_path is None


# ---------------------------------------------------------------------------
# argv shape verification across all three steps
# ---------------------------------------------------------------------------


class TestSubprocessArgvShape:
    """Verify that simulate() calls ghdl with the correct argv for each step."""

    def _run_simulate(
        self,
        vhdl_files: list[str],
        top_entity: str = "tb_counter",
        time_ns: int = 500,
        vcd_out: Path | None = None,
    ):
        """Helper: patch which + subprocess.run and return (result, calls)."""
        ok_proc = _make_completed_process(returncode=0)

        with patch("shutil.which", return_value="/usr/bin/ghdl"), \
             patch("subprocess.run", return_value=ok_proc) as mock_run:
            if vcd_out is None:
                # Use a fixed path so we can assert on it
                vcd_out = Path("/tmp/test_out.vcd")
            result = simulate(vhdl_files, top_entity, time_ns=time_ns, vcd_out=vcd_out)

        return result, mock_run

    # -- analyse step --------------------------------------------------------

    def test_analyse_called_first(self):
        _, mock_run = self._run_simulate(["a.vhd", "b.vhd"])
        first_call_argv = mock_run.call_args_list[0][0][0]
        assert first_call_argv[0] == "ghdl"
        assert first_call_argv[1] == "-a"

    def test_analyse_includes_all_vhdl_files(self):
        files = ["design.vhd", "testbench.vhd"]
        _, mock_run = self._run_simulate(files)
        analyse_argv = mock_run.call_args_list[0][0][0]
        assert "design.vhd" in analyse_argv
        assert "testbench.vhd" in analyse_argv

    def test_analyse_argv_is_ghdl_a_files(self):
        files = ["counter4.vhd", "counter4_tb.vhd"]
        _, mock_run = self._run_simulate(files)
        analyse_argv = mock_run.call_args_list[0][0][0]
        # Must be: ["ghdl", "-a", "counter4.vhd", "counter4_tb.vhd"]
        assert analyse_argv == ["ghdl", "-a"] + files

    # -- elaborate step ------------------------------------------------------

    def test_elaborate_called_second(self):
        _, mock_run = self._run_simulate(["tb.vhd"], top_entity="tb_top")
        second_call_argv = mock_run.call_args_list[1][0][0]
        assert second_call_argv[0] == "ghdl"
        assert second_call_argv[1] == "-e"

    def test_elaborate_argv_contains_top_entity(self):
        _, mock_run = self._run_simulate(["tb.vhd"], top_entity="tb_counter4")
        elaborate_argv = mock_run.call_args_list[1][0][0]
        assert elaborate_argv == ["ghdl", "-e", "tb_counter4"]

    # -- run step ------------------------------------------------------------

    def test_run_called_third(self):
        _, mock_run = self._run_simulate(["tb.vhd"], top_entity="tb_top")
        third_call_argv = mock_run.call_args_list[2][0][0]
        assert third_call_argv[0] == "ghdl"
        assert third_call_argv[1] == "-r"

    def test_run_argv_contains_top_entity(self):
        _, mock_run = self._run_simulate(["tb.vhd"], top_entity="tb_adder")
        run_argv = mock_run.call_args_list[2][0][0]
        assert "tb_adder" in run_argv

    def test_run_argv_contains_vcd_flag(self):
        vcd = Path("/tmp/waves.vcd")
        _, mock_run = self._run_simulate(["tb.vhd"], vcd_out=vcd)
        run_argv = mock_run.call_args_list[2][0][0]
        assert any(a.startswith("--vcd=") for a in run_argv)

    def test_run_argv_vcd_flag_contains_path(self):
        vcd = Path("/tmp/specific_waves.vcd")
        _, mock_run = self._run_simulate(["tb.vhd"], vcd_out=vcd)
        run_argv = mock_run.call_args_list[2][0][0]
        vcd_arg = next(a for a in run_argv if a.startswith("--vcd="))
        assert str(vcd) in vcd_arg

    def test_run_argv_contains_stop_time_flag(self):
        _, mock_run = self._run_simulate(["tb.vhd"], time_ns=750)
        run_argv = mock_run.call_args_list[2][0][0]
        assert any(a.startswith("--stop-time=") for a in run_argv)

    def test_run_argv_stop_time_encodes_ns(self):
        _, mock_run = self._run_simulate(["tb.vhd"], time_ns=750)
        run_argv = mock_run.call_args_list[2][0][0]
        stop_arg = next(a for a in run_argv if a.startswith("--stop-time="))
        assert "750ns" in stop_arg

    def test_exactly_three_subprocess_calls(self):
        _, mock_run = self._run_simulate(["tb.vhd"])
        assert mock_run.call_count == 3

    # -- step ordering -------------------------------------------------------

    def test_steps_are_analyse_elaborate_run_in_order(self):
        _, mock_run = self._run_simulate(["tb.vhd"], top_entity="tb_top")
        flags = [c[0][0][1] for c in mock_run.call_args_list]
        assert flags == ["-a", "-e", "-r"]


# ---------------------------------------------------------------------------
# VCD path set on success
# ---------------------------------------------------------------------------


class TestSuccessPath:
    def test_status_ok_on_success(self):
        ok_proc = _make_completed_process(returncode=0)
        with patch("shutil.which", return_value="/usr/bin/ghdl"), \
             patch("subprocess.run", return_value=ok_proc):
            result = simulate(["tb.vhd"], "tb_top", vcd_out=Path("/tmp/out.vcd"))
        assert result.status == "ok"

    def test_vcd_path_set_on_success(self):
        vcd = Path("/tmp/counter4.vcd")
        ok_proc = _make_completed_process(returncode=0)
        with patch("shutil.which", return_value="/usr/bin/ghdl"), \
             patch("subprocess.run", return_value=ok_proc):
            result = simulate(["tb.vhd"], "tb_top", vcd_out=vcd)
        assert result.vcd_path == vcd

    def test_vcd_path_is_path_object(self):
        vcd = Path("/tmp/waves.vcd")
        ok_proc = _make_completed_process(returncode=0)
        with patch("shutil.which", return_value="/usr/bin/ghdl"), \
             patch("subprocess.run", return_value=ok_proc):
            result = simulate(["tb.vhd"], "tb_top", vcd_out=vcd)
        assert isinstance(result.vcd_path, Path)

    def test_default_time_ns_is_1000(self):
        ok_proc = _make_completed_process(returncode=0)
        with patch("shutil.which", return_value="/usr/bin/ghdl"), \
             patch("subprocess.run", return_value=ok_proc) as mock_run:
            simulate(["tb.vhd"], "tb_top", vcd_out=Path("/tmp/out.vcd"))
        run_argv = mock_run.call_args_list[2][0][0]
        stop_arg = next(a for a in run_argv if a.startswith("--stop-time="))
        assert "1000ns" in stop_arg


# ---------------------------------------------------------------------------
# Error path — non-zero exit code from any step
# ---------------------------------------------------------------------------


class TestErrorPath:
    def test_status_error_when_analyse_fails(self):
        fail_proc = _make_completed_process(returncode=1, stderr="error in analysis")
        with patch("shutil.which", return_value="/usr/bin/ghdl"), \
             patch("subprocess.run", return_value=fail_proc):
            result = simulate(["bad.vhd"], "tb_top", vcd_out=Path("/tmp/out.vcd"))
        assert result.status == "error"

    def test_no_vcd_path_when_analyse_fails(self):
        fail_proc = _make_completed_process(returncode=1, stderr="error")
        with patch("shutil.which", return_value="/usr/bin/ghdl"), \
             patch("subprocess.run", return_value=fail_proc):
            result = simulate(["bad.vhd"], "tb_top", vcd_out=Path("/tmp/out.vcd"))
        assert result.vcd_path is None

    def test_stops_after_analyse_fails_only_one_call(self):
        fail_proc = _make_completed_process(returncode=1)
        with patch("shutil.which", return_value="/usr/bin/ghdl"), \
             patch("subprocess.run", return_value=fail_proc) as mock_run:
            simulate(["bad.vhd"], "tb_top", vcd_out=Path("/tmp/out.vcd"))
        # Should stop after first failure (analyse step only)
        assert mock_run.call_count == 1

    def test_status_error_when_elaborate_fails(self):
        def side_effect(argv, **kwargs):
            if argv[1] == "-a":
                return _make_completed_process(returncode=0)
            return _make_completed_process(returncode=1, stderr="elab error")

        with patch("shutil.which", return_value="/usr/bin/ghdl"), \
             patch("subprocess.run", side_effect=side_effect):
            result = simulate(["tb.vhd"], "tb_top", vcd_out=Path("/tmp/out.vcd"))
        assert result.status == "error"

    def test_stops_after_elaborate_fails_two_calls(self):
        call_count = 0

        def side_effect(argv, **kwargs):
            nonlocal call_count
            call_count += 1
            if argv[1] == "-a":
                return _make_completed_process(returncode=0)
            return _make_completed_process(returncode=1)

        with patch("shutil.which", return_value="/usr/bin/ghdl"), \
             patch("subprocess.run", side_effect=side_effect):
            simulate(["tb.vhd"], "tb_top", vcd_out=Path("/tmp/out.vcd"))
        assert call_count == 2

    def test_status_error_when_run_fails(self):
        def side_effect(argv, **kwargs):
            if argv[1] in ("-a", "-e"):
                return _make_completed_process(returncode=0)
            return _make_completed_process(returncode=1, stderr="runtime assertion failed")

        with patch("shutil.which", return_value="/usr/bin/ghdl"), \
             patch("subprocess.run", side_effect=side_effect):
            result = simulate(["tb.vhd"], "tb_top", vcd_out=Path("/tmp/out.vcd"))
        assert result.status == "error"


# ---------------------------------------------------------------------------
# Log accumulation
# ---------------------------------------------------------------------------


class TestLogAccumulation:
    def test_log_captures_all_step_output(self):
        def side_effect(argv, **kwargs):
            step = argv[1]
            if step == "-a":
                return _make_completed_process(0, stdout="analysis ok\n")
            if step == "-e":
                return _make_completed_process(0, stderr="elaboration done\n")
            return _make_completed_process(0, stdout="simulation finished\n")

        with patch("shutil.which", return_value="/usr/bin/ghdl"), \
             patch("subprocess.run", side_effect=side_effect):
            result = simulate(["tb.vhd"], "tb_top", vcd_out=Path("/tmp/out.vcd"))

        assert "analysis ok" in result.log
        assert "elaboration done" in result.log
        assert "simulation finished" in result.log
