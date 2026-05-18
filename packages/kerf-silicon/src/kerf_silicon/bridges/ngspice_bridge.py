"""
ngspice_bridge.py — device-level SPICE subprocess bridge for silicon.

This bridge handles MOSFET-level / BSIM4 / sub-circuit netlists for IC
design simulation.  It is distinct from kerf_electronics.routes_spice which
handles PCB-level analysis; here we target transistor-level CMOS netlists
(130nm / sky130 process corner).

Public API
----------
    transient(netlist_text, output_file, t_step_ns, t_stop_ns,
              *, timeout=120) -> SimResult
        Run ngspice in batch mode on ``netlist_text``, return
        a ``SimResult`` with ``waveforms`` and ``status``.

    NgspiceNotAvailable
        Sentinel exception raised when ngspice is not on PATH.

    SimResult
        Dataclass: ok, status, waveforms, warnings, errors,
        raw_stdout, raw_stderr.

Subprocess invocation
---------------------
    ngspice -b -o <output_file> <input.cir>

    -b  batch mode (non-interactive)
    -o  redirect ngspice print/plot output to a file

When ngspice is absent from PATH, ``transient`` raises
``NgspiceNotAvailable`` so callers and tests can detect the condition
cleanly (``pytest.skip`` or return a pending result).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kerf_silicon.bridges.spice_netlist import parse_ngspice_output


# ---------------------------------------------------------------------------
# Availability sentinel
# ---------------------------------------------------------------------------

class NgspiceNotAvailable(RuntimeError):
    """Raised when the ``ngspice`` binary cannot be found on PATH."""


def _ngspice_available() -> bool:
    return shutil.which("ngspice") is not None


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SimResult:
    """Result of a SPICE simulation run.

    Attributes
    ----------
    ok:
        True when ngspice exited with code 0 and produced output.
    status:
        Human-readable status string: ``"ok"``, ``"pending"``
        (ngspice absent), ``"error"``, or ``"timeout"``.
    waveforms:
        Dict mapping node/column names to lists of float values.
        ``waveforms["time"]`` is the time axis (seconds) when present.
    warnings:
        List of non-fatal warning strings.
    errors:
        List of error strings.
    raw_stdout:
        Captured stdout from ngspice (truncated to 8 kB).
    raw_stderr:
        Captured stderr from ngspice (truncated to 4 kB).
    """

    ok: bool
    status: str
    waveforms: dict[str, list[float]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw_stdout: str = ""
    raw_stderr: str = ""


# ---------------------------------------------------------------------------
# Core bridge function
# ---------------------------------------------------------------------------

_STDOUT_LIMIT = 8192
_STDERR_LIMIT = 4096


def transient(
    netlist_text: str,
    output_file: str,
    t_step_ns: float,
    t_stop_ns: float,
    *,
    timeout: int = 120,
) -> SimResult:
    """Run a SPICE transient simulation via ngspice batch mode.

    The function writes ``netlist_text`` to a temporary ``.cir`` file,
    invokes ``ngspice -b -o <output_file> <input.cir>``, then parses the
    ngspice output into named waveform arrays.

    Parameters
    ----------
    netlist_text:
        Complete SPICE netlist including ``.TRAN`` directive.  If the
        netlist does not already contain a ``.TRAN`` directive one is
        injected using ``t_step_ns`` and ``t_stop_ns``.
    output_file:
        Path where ngspice should write its raw / print output.
        Pass an absolute path; a temporary file is used if this is
        ``"stdout"`` (ngspice's ``-o stdout`` writes to its stdout).
    t_step_ns:
        Suggested time step in nanoseconds (used when injecting .TRAN).
    t_stop_ns:
        Stop time in nanoseconds (used when injecting .TRAN).
    timeout:
        Subprocess timeout in seconds (default 120).

    Returns
    -------
    SimResult

    Raises
    ------
    NgspiceNotAvailable
        When ``ngspice`` is not on PATH.
    """
    if not _ngspice_available():
        raise NgspiceNotAvailable(
            "ngspice binary not found on PATH. "
            "Install with: brew install ngspice  or  apt install ngspice"
        )

    # Inject .TRAN if not already present
    tran_present = any(
        line.strip().upper().startswith(".TRAN")
        for line in netlist_text.splitlines()
    )
    deck = netlist_text
    if not tran_present:
        # Insert before .end
        deck = _inject_tran(netlist_text, t_step_ns, t_stop_ns)

    with tempfile.TemporaryDirectory(prefix="kerf_spice_") as tmpdir:
        tmppath = Path(tmpdir)
        cir_path = tmppath / "input.cir"
        cir_path.write_text(deck)

        # Resolve output path
        if output_file == "stdout":
            out_arg = "stdout"
            raw_path: Optional[Path] = None
        else:
            raw_path = Path(output_file)
            out_arg = str(raw_path)

        cmd = ["ngspice", "-b", "-o", out_arg, str(cir_path)]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )
        except subprocess.TimeoutExpired:
            return SimResult(
                ok=False,
                status="timeout",
                errors=[f"ngspice timed out after {timeout}s"],
            )
        except FileNotFoundError:
            # Shouldn't happen (checked above), but guard anyway
            raise NgspiceNotAvailable("ngspice not found")

        stdout = (proc.stdout or "")[-_STDOUT_LIMIT:]
        stderr = (proc.stderr or "")[-_STDERR_LIMIT:]
        errors: list[str] = []
        warnings: list[str] = []

        if proc.returncode != 0:
            errors.append(
                f"ngspice exited with code {proc.returncode}: "
                f"{stderr[:500]}"
            )

        # Parse waveform data
        # ngspice -o stdout writes print output to stdout;
        # ngspice -o <file> writes to the file.
        output_text = ""
        if output_file == "stdout":
            output_text = proc.stdout or ""
        elif raw_path and raw_path.exists():
            try:
                output_text = raw_path.read_text(errors="replace")
            except OSError as exc:
                warnings.append(f"could not read output file: {exc}")
        elif not errors:
            warnings.append("ngspice produced no output file")

        waveforms = parse_ngspice_output(output_text) if output_text else {}

        ok = proc.returncode == 0 and not errors
        status = "ok" if ok else "error"

        return SimResult(
            ok=ok,
            status=status,
            waveforms=waveforms,
            warnings=warnings,
            errors=errors,
            raw_stdout=stdout,
            raw_stderr=stderr,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _inject_tran(netlist_text: str, t_step_ns: float, t_stop_ns: float) -> str:
    """Insert a .TRAN directive before the .end line."""
    tran_line = f".TRAN {t_step_ns:.4g}n {t_stop_ns:.4g}n"
    lines = netlist_text.splitlines()
    result: list[str] = []
    inserted = False
    for line in lines:
        if not inserted and line.strip().upper().startswith(".END"):
            result.append(tran_line)
            inserted = True
        result.append(line)
    if not inserted:
        result.append(tran_line)
        result.append(".end")
    return "\n".join(result) + "\n"


def pending_result(reason: str = "ngspice not available") -> SimResult:
    """Return a SimResult with status 'pending' for use when ngspice is absent.

    This helper lets callers build a deferred / pending result without
    raising an exception — useful when the simulation is optional or can
    be retried later.
    """
    return SimResult(
        ok=False,
        status="pending",
        warnings=[reason],
    )
