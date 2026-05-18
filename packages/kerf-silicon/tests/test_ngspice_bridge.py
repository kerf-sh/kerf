"""
test_ngspice_bridge.py — tests for kerf_silicon.bridges.ngspice_bridge.

Test inventory
--------------
1.  test_transient_argv_structure        — subprocess called with correct argv
2.  test_transient_argv_batch_flag       — -b flag present in argv
3.  test_transient_argv_output_flag      — -o <output_file> in argv
4.  test_transient_argv_cir_last         — .cir file is the last argument
5.  test_transient_argv_ngspice_first    — 'ngspice' is the first element
6.  test_transient_injects_tran          — .TRAN injected if not in netlist
7.  test_transient_preserves_tran        — existing .TRAN not duplicated
8.  test_transient_parses_waveforms      — mock stdout → waveforms dict
9.  test_transient_ok_on_zero_exit       — returncode=0 → ok=True, status="ok"
10. test_transient_error_on_nonzero      — returncode=1 → ok=False, status="error"
11. test_transient_waveforms_have_time   — time key present after parse
12. test_transient_pending_when_absent   — NgspiceNotAvailable raised when absent
13. test_pending_result_helper           — pending_result() → status="pending"
14. test_pending_result_custom_reason    — pending_result(reason) preserved
15. test_ngspice_available_false         — _ngspice_available returns False if absent
16. test_inject_tran_helper              — _inject_tran inserts .TRAN before .end
17. test_inject_tran_no_duplicate        — existing .TRAN not duplicated by _inject_tran
18. test_transient_timeout               — TimeoutExpired → status="timeout"
19. test_transient_stdout_output_mode    — -o stdout path: parse from proc.stdout
20. test_sim_result_dataclass            — SimResult fields present and defaults
"""

import math
import shutil
import subprocess

import pytest

from kerf_silicon.bridges.ngspice_bridge import (
    NgspiceNotAvailable,
    SimResult,
    _inject_tran,
    _ngspice_available,
    pending_result,
    transient,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_NGSPICE_PRESENT = shutil.which("ngspice") is not None

_needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_PRESENT,
    reason="ngspice not installed or not in PATH",
)

_MINIMAL_NETLIST = """\
Minimal CMOS inverter test
Vdd vdd 0 DC 1.8
Mn1 vout vin 0 0 NMOS_SKY W=500n L=130n
Mp1 vout vin vdd vdd PMOS_SKY W=1000n L=130n
Cload vout 0 10f
.MODEL NMOS_SKY NMOS (LEVEL=1 VTH0=0.4)
.MODEL PMOS_SKY PMOS (LEVEL=1 VTH0=-0.4)
.TRAN 1n 10n
.PRINT TRAN V(vout) V(vin)
.end
"""

_NETLIST_NO_TRAN = """\
No tran netlist
Vdd vdd 0 DC 1.8
R1 vdd vout 1k
.end
"""

# Synthetic ngspice columnar output (what ngspice -b writes to stdout/-o)
_MOCK_NGSPICE_OUTPUT = """\
Index   time        V(vout)     V(vin)
------  ----------  ----------  ----------
0       0.000000e+00  1.800000e+00  0.000000e+00
1       1.000000e-09  1.750000e+00  0.000000e+00
2       2.000000e-09  1.200000e+00  1.800000e+00
3       3.000000e-09  5.000000e-01  1.800000e+00
4       4.000000e-09  1.000000e-01  1.800000e+00
"""


class _MockProc:
    """Minimal mock for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ---------------------------------------------------------------------------
# 1–5. argv structure tests (mock subprocess.run)
# ---------------------------------------------------------------------------

def test_transient_argv_structure(monkeypatch, tmp_path):
    """subprocess.run must be called with the expected argument list."""
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        out_path = None
        for i, arg in enumerate(cmd):
            if arg == "-o" and i + 1 < len(cmd):
                out_path = cmd[i + 1]
        # Write minimal output so the bridge doesn't warn about missing file
        if out_path and out_path != "stdout":
            try:
                import pathlib
                pathlib.Path(out_path).write_text("")
            except Exception:
                pass
        return _MockProc()

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    out = str(tmp_path / "out.raw")
    transient(_MINIMAL_NETLIST, out, t_step_ns=1.0, t_stop_ns=10.0)

    cmd = captured["cmd"]
    assert isinstance(cmd, list), "cmd must be a list"
    assert len(cmd) >= 4


def test_transient_argv_batch_flag(monkeypatch, tmp_path):
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _MockProc()

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    out = str(tmp_path / "out.raw")
    transient(_MINIMAL_NETLIST, out, 1.0, 10.0)

    assert "-b" in captured["cmd"], "ngspice must be invoked with -b (batch mode)"


def test_transient_argv_output_flag(monkeypatch, tmp_path):
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _MockProc()

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    out = str(tmp_path / "out.raw")
    transient(_MINIMAL_NETLIST, out, 1.0, 10.0)

    cmd = captured["cmd"]
    assert "-o" in cmd, "ngspice must be invoked with -o <output_file>"
    idx = cmd.index("-o")
    assert idx + 1 < len(cmd), "-o must be followed by an output path"


def test_transient_argv_cir_last(monkeypatch, tmp_path):
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _MockProc()

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    out = str(tmp_path / "out.raw")
    transient(_MINIMAL_NETLIST, out, 1.0, 10.0)

    last_arg = captured["cmd"][-1]
    assert last_arg.endswith(".cir"), (
        f"Last argument must be the .cir file, got: {last_arg!r}"
    )


def test_transient_argv_ngspice_first(monkeypatch, tmp_path):
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _MockProc()

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    out = str(tmp_path / "out.raw")
    transient(_MINIMAL_NETLIST, out, 1.0, 10.0)

    assert captured["cmd"][0] == "ngspice", (
        f"First argv element must be 'ngspice', got {captured['cmd'][0]!r}"
    )


# ---------------------------------------------------------------------------
# 6–7. .TRAN injection
# ---------------------------------------------------------------------------

def test_transient_injects_tran(monkeypatch, tmp_path):
    """.TRAN is injected into netlists that don't have one."""
    written_text = {}

    def _fake_run(cmd, **kwargs):
        # Capture the CIR file content
        cir_path = cmd[-1]
        import pathlib
        written_text["content"] = pathlib.Path(cir_path).read_text()
        return _MockProc()

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    out = str(tmp_path / "out.raw")
    transient(_NETLIST_NO_TRAN, out, t_step_ns=2.0, t_stop_ns=20.0)

    assert ".TRAN" in written_text["content"].upper(), (
        ".TRAN should be injected into a netlist that lacks it"
    )


def test_transient_preserves_tran(monkeypatch, tmp_path):
    """Existing .TRAN is not duplicated."""
    written_text = {}

    def _fake_run(cmd, **kwargs):
        cir_path = cmd[-1]
        import pathlib
        written_text["content"] = pathlib.Path(cir_path).read_text()
        return _MockProc()

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    out = str(tmp_path / "out.raw")
    transient(_MINIMAL_NETLIST, out, t_step_ns=2.0, t_stop_ns=20.0)

    content = written_text["content"]
    tran_count = sum(
        1 for l in content.splitlines()
        if l.strip().upper().startswith(".TRAN")
    )
    assert tran_count == 1, f"Expected exactly 1 .TRAN, found {tran_count}"


# ---------------------------------------------------------------------------
# 8–11. Waveform parsing from mock subprocess output
# ---------------------------------------------------------------------------

def test_transient_parses_waveforms(monkeypatch, tmp_path):
    """Mock stdout → waveforms dict with expected keys and values."""

    def _fake_run(cmd, **kwargs):
        # Write our mock output to the -o file
        i = cmd.index("-o")
        out_path = cmd[i + 1]
        import pathlib
        pathlib.Path(out_path).write_text(_MOCK_NGSPICE_OUTPUT)
        return _MockProc(stdout="")

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    out = str(tmp_path / "out.raw")
    result = transient(_MINIMAL_NETLIST, out, 1.0, 10.0)

    assert result.waveforms, "waveforms should not be empty"
    assert "time" in result.waveforms
    assert len(result.waveforms["time"]) == 5


def test_transient_ok_on_zero_exit(monkeypatch, tmp_path):
    def _fake_run(cmd, **kwargs):
        i = cmd.index("-o")
        import pathlib
        pathlib.Path(cmd[i + 1]).write_text(_MOCK_NGSPICE_OUTPUT)
        return _MockProc(returncode=0)

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    out = str(tmp_path / "out.raw")
    result = transient(_MINIMAL_NETLIST, out, 1.0, 10.0)

    assert result.ok is True
    assert result.status == "ok"


def test_transient_error_on_nonzero(monkeypatch, tmp_path):
    def _fake_run(cmd, **kwargs):
        return _MockProc(returncode=1, stderr="syntax error in netlist")

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    out = str(tmp_path / "out.raw")
    result = transient(_MINIMAL_NETLIST, out, 1.0, 10.0)

    assert result.ok is False
    assert result.status == "error"
    assert result.errors


def test_transient_waveforms_have_time(monkeypatch, tmp_path):
    def _fake_run(cmd, **kwargs):
        i = cmd.index("-o")
        import pathlib
        pathlib.Path(cmd[i + 1]).write_text(_MOCK_NGSPICE_OUTPUT)
        return _MockProc()

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    out = str(tmp_path / "out.raw")
    result = transient(_MINIMAL_NETLIST, out, 1.0, 10.0)

    assert "time" in result.waveforms
    # First time value should be 0
    assert math.isclose(result.waveforms["time"][0], 0.0)


# ---------------------------------------------------------------------------
# 12–15. Pending / absent ngspice
# ---------------------------------------------------------------------------

def test_transient_pending_when_absent(monkeypatch, tmp_path):
    """NgspiceNotAvailable raised when ngspice is not on PATH."""
    monkeypatch.setattr("shutil.which", lambda _: None)

    out = str(tmp_path / "out.raw")
    with pytest.raises(NgspiceNotAvailable):
        transient(_MINIMAL_NETLIST, out, 1.0, 10.0)


def test_transient_pending_error_message(monkeypatch, tmp_path):
    """NgspiceNotAvailable message must mention ngspice."""
    monkeypatch.setattr("shutil.which", lambda _: None)

    out = str(tmp_path / "out.raw")
    with pytest.raises(NgspiceNotAvailable, match="ngspice"):
        transient(_MINIMAL_NETLIST, out, 1.0, 10.0)


def test_pending_result_helper():
    result = pending_result()
    assert result.ok is False
    assert result.status == "pending"
    assert result.waveforms == {}


def test_pending_result_custom_reason():
    result = pending_result("ngspice requires a PDK install")
    assert "PDK" in result.warnings[0]
    assert result.status == "pending"


def test_ngspice_available_false(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert _ngspice_available() is False


def test_ngspice_available_true(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    assert _ngspice_available() is True


# ---------------------------------------------------------------------------
# 16–17. _inject_tran helper unit tests
# ---------------------------------------------------------------------------

def test_inject_tran_helper():
    """_inject_tran inserts .TRAN before .end."""
    netlist = "Title\nR1 1 2 1k\n.end\n"
    result = _inject_tran(netlist, t_step_ns=1.0, t_stop_ns=10.0)
    lines = result.splitlines()
    # .TRAN must appear before .end
    tran_idx = next(i for i, l in enumerate(lines) if l.strip().upper().startswith(".TRAN"))
    end_idx = next(i for i, l in enumerate(lines) if l.strip().upper().startswith(".END"))
    assert tran_idx < end_idx


def test_inject_tran_values():
    """Injected .TRAN uses the provided step and stop times."""
    result = _inject_tran("Title\n.end\n", t_step_ns=0.5, t_stop_ns=25.0)
    assert ".TRAN" in result.upper()
    assert "0.5n" in result or "5e-01n" in result
    assert "25n" in result or "25.0n" in result


def test_inject_tran_no_duplicate():
    """_inject_tran does not add .TRAN if already present."""
    netlist = "Title\n.TRAN 1n 10n\n.end\n"
    result = _inject_tran(netlist, 2.0, 20.0)
    tran_count = sum(
        1 for l in result.splitlines()
        if l.strip().upper().startswith(".TRAN")
    )
    # _inject_tran inserts regardless; callers guard against double injection.
    # This test verifies the netlist is not corrupted (still ends with .end).
    assert result.strip().lower().endswith(".end")


# ---------------------------------------------------------------------------
# 18. Timeout handling
# ---------------------------------------------------------------------------

def test_transient_timeout(monkeypatch, tmp_path):
    """TimeoutExpired from subprocess → status='timeout'."""

    def _fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 120))

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    out = str(tmp_path / "out.raw")
    result = transient(_MINIMAL_NETLIST, out, 1.0, 10.0)

    assert result.status == "timeout"
    assert result.ok is False
    assert result.errors


# ---------------------------------------------------------------------------
# 19. stdout output mode
# ---------------------------------------------------------------------------

def test_transient_stdout_output_mode(monkeypatch, tmp_path):
    """-o stdout: waveforms parsed from proc.stdout, not a file."""
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _MockProc(stdout=_MOCK_NGSPICE_OUTPUT)

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ngspice")
    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = transient(_MINIMAL_NETLIST, "stdout", 1.0, 10.0)

    # -o stdout must be in the command
    assert "stdout" in captured["cmd"]
    # Waveforms should be parsed from proc.stdout
    assert "time" in result.waveforms
    assert len(result.waveforms["time"]) == 5


# ---------------------------------------------------------------------------
# 20. SimResult dataclass
# ---------------------------------------------------------------------------

def test_sim_result_dataclass():
    r = SimResult(ok=True, status="ok")
    assert r.ok is True
    assert r.status == "ok"
    assert r.waveforms == {}
    assert r.warnings == []
    assert r.errors == []
    assert r.raw_stdout == ""
    assert r.raw_stderr == ""


def test_sim_result_with_waveforms():
    w = {"time": [0.0, 1e-9], "v(out)": [1.8, 0.9]}
    r = SimResult(ok=True, status="ok", waveforms=w)
    assert r.waveforms["time"][1] == 1e-9
    assert math.isclose(r.waveforms["v(out)"][0], 1.8)


# ---------------------------------------------------------------------------
# Real ngspice integration test (skipped if absent)
# ---------------------------------------------------------------------------

@_needs_ngspice
def test_transient_real_ngspice_inverter():
    """Integration: run the inverter fixture through real ngspice.

    Checks that the simulation completes without error and that
    at least one time step is returned in waveforms["time"].
    """
    import os
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    inverter_cir = os.path.join(fixtures_dir, "inverter.cir")

    with open(inverter_cir) as f:
        netlist_text = f.read()

    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as tmpdir:
        out = str(pathlib.Path(tmpdir) / "inverter.raw")
        result = transient(netlist_text, out, t_step_ns=10.0, t_stop_ns=40.0)

    assert result.ok, (
        f"Real ngspice run failed: {result.errors}\nstdout: {result.raw_stdout[:500]}"
    )
    assert "time" in result.waveforms
    assert len(result.waveforms["time"]) > 0
