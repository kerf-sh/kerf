"""
GHDL VHDL simulator subprocess bridge.

Wraps the three-step GHDL workflow:
  1. ghdl -a <files>       — analyse (compile) VHDL sources
  2. ghdl -e <top_entity>  — elaborate the design
  3. ghdl -r <top_entity> --vcd=<out> --stop-time=<ns>ns  — run / simulate

Returns a :class:`SimResult` dataclass.  When ``ghdl`` is not on ``$PATH``
the call returns immediately with ``status="pending"`` and an install hint in
``log``.

Install hints:
  macOS:  brew install ghdl
  Debian/Ubuntu: apt install ghdl
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass
class GHDLError:
    """A single structured diagnostic emitted by ghdl."""

    file: str
    line: int
    column: int
    severity: str  # "error" | "warning" | "note"
    message: str


@dataclass
class SimResult:
    """Result returned by :func:`simulate`."""

    status: str          # "ok" | "error" | "pending"
    vcd_path: Optional[Path] = None
    log: str = ""
    errors: list[GHDLError] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Error-line parser
# ---------------------------------------------------------------------------

# GHDL diagnostic format:
#   <file>:<line>:<col>: <severity>: <message>
# e.g.  counter4_tb.vhd:12:5: error: unknown identifier "clck"
_DIAG_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<sev>\w+):\s*(?P<msg>.+)$"
)


def _parse_errors(text: str) -> list[GHDLError]:
    """Extract structured diagnostics from ghdl stderr/stdout."""
    result: list[GHDLError] = []
    for raw_line in text.splitlines():
        m = _DIAG_RE.match(raw_line.strip())
        if m:
            result.append(
                GHDLError(
                    file=m.group("file"),
                    line=int(m.group("line")),
                    column=int(m.group("col")),
                    severity=m.group("sev"),
                    message=m.group("msg"),
                )
            )
    return result


# ---------------------------------------------------------------------------
# Core public function
# ---------------------------------------------------------------------------


def simulate(
    vhdl_files: list[str | Path],
    top_entity: str,
    time_ns: int = 1000,
    vcd_out: Optional[Path] = None,
    *,
    workdir: Optional[Path] = None,
    timeout: int = 120,
) -> SimResult:
    """Run a VHDL simulation through GHDL.

    Parameters
    ----------
    vhdl_files:
        Ordered list of ``.vhd`` / ``.vhdl`` source paths.  All files are
        analysed (``ghdl -a``) in the order supplied.
    top_entity:
        Name of the top-level entity / testbench to elaborate and run.
    time_ns:
        Simulation stop time in nanoseconds (default 1000 ns).
    vcd_out:
        Destination for the VCD waveform file.  When *None* a temporary file
        is created inside *workdir* (or a fresh temp directory).
    workdir:
        Working directory for GHDL's work library.  A temporary directory is
        used when *None*.
    timeout:
        Per-subprocess timeout in seconds (default 120).

    Returns
    -------
    SimResult
        ``status="pending"`` if ghdl is not installed.
        ``status="ok"`` on success.
        ``status="error"`` on non-zero exit from any step.
    """
    # --- binary check --------------------------------------------------
    if shutil.which("ghdl") is None:
        return SimResult(
            status="pending",
            log=(
                "ghdl not found on $PATH.  "
                "Install with: brew install ghdl  (macOS) or  apt install ghdl  (Debian/Ubuntu)"
            ),
        )

    # --- normalise file list -------------------------------------------
    vhdl_paths = [Path(f) for f in vhdl_files]

    # --- set up working directory / VCD path ---------------------------
    _tmp_ctx: tempfile.TemporaryDirectory | None = None
    if workdir is None:
        _tmp_ctx = tempfile.TemporaryDirectory(prefix="kerf_ghdl_")
        _workdir = Path(_tmp_ctx.name)
    else:
        _workdir = Path(workdir)
        _workdir.mkdir(parents=True, exist_ok=True)

    if vcd_out is None:
        vcd_out = _workdir / f"{top_entity}.vcd"

    accumulated_log: list[str] = []
    accumulated_errors: list[GHDLError] = []

    def _run(argv: list[str], step: str) -> tuple[int, str]:
        """Execute *argv* and return (returncode, combined output)."""
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_workdir),
        )
        combined = ""
        if proc.stdout:
            combined += proc.stdout
        if proc.stderr:
            combined += proc.stderr
        accumulated_log.append(f"--- {step} ---\n{combined}")
        accumulated_errors.extend(_parse_errors(combined))
        return proc.returncode, combined

    try:
        # Step 1: analyse all VHDL source files
        analyse_argv = ["ghdl", "-a"] + [str(p) for p in vhdl_paths]
        rc, _ = _run(analyse_argv, "analyse")
        if rc != 0:
            return SimResult(
                status="error",
                log="\n".join(accumulated_log),
                errors=accumulated_errors,
            )

        # Step 2: elaborate the top-level entity
        elaborate_argv = ["ghdl", "-e", top_entity]
        rc, _ = _run(elaborate_argv, "elaborate")
        if rc != 0:
            return SimResult(
                status="error",
                log="\n".join(accumulated_log),
                errors=accumulated_errors,
            )

        # Step 3: run the simulation
        run_argv = [
            "ghdl", "-r", top_entity,
            f"--vcd={vcd_out}",
            f"--stop-time={time_ns}ns",
        ]
        rc, _ = _run(run_argv, "run")
        if rc != 0:
            return SimResult(
                status="error",
                log="\n".join(accumulated_log),
                errors=accumulated_errors,
            )

        return SimResult(
            status="ok",
            vcd_path=vcd_out,
            log="\n".join(accumulated_log),
            errors=accumulated_errors,
        )

    finally:
        if _tmp_ctx is not None:
            # Keep temp dir alive only for the duration of this call when
            # vcd_out was auto-generated inside it; caller already has the
            # path string captured in SimResult.vcd_path before cleanup.
            # Note: we intentionally do NOT clean up here so the caller can
            # read the VCD.  The OS will reclaim the temp dir eventually.
            pass
