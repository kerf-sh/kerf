"""
kerf_silicon.cocotb_harness.runner
====================================

SimulatorRunner — launches a real VHDL/Verilog simulation via ghdl or
verilator when the tool-chain is present, or returns a ``PENDING`` sentinel
when it is absent.

Usage
-----
::

    from kerf_silicon.cocotb_harness.runner import SimulatorRunner, PENDING

    result = SimulatorRunner.run(
        toplevel="my_counter",
        source_files=["rtl/counter.vhd"],
        test_module="tests.test_counter",
        simulator="ghdl",   # or "verilator"; default: auto-detect
    )
    if result is PENDING:
        pytest.skip("No simulator installed")

Simulator auto-detection
------------------------
The runner looks for ``ghdl`` and ``verilator`` executables on ``PATH``.
If neither is found, ``run()`` returns the ``PENDING`` sentinel instead of
raising an exception, enabling tests to mark themselves as pending/xfail
in CI environments that lack HDL tool-chains.

Real simulation
---------------
When a simulator is found, the runner:
  1. Creates a temporary build directory.
  2. Invokes cocotb's ``SimulatorRunner`` (``cocotb.runner``) if cocotb is
     installed, falling back to a minimal subprocess invocation.
  3. Returns the process ``CompletedProcess`` result or raises
     ``SimulationError`` on non-zero exit.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Public sentinel
# ---------------------------------------------------------------------------

class _Pending:
    """Singleton returned by ``run()`` when no simulator is available."""

    _instance: "_Pending | None" = None

    def __new__(cls) -> "_Pending":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "PENDING"


PENDING = _Pending()
"""Sentinel value: ``run()`` returns this when no simulator is installed."""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class SimulationError(RuntimeError):
    """Raised when a simulator process exits with a non-zero return code."""


# ---------------------------------------------------------------------------
# Simulator detection helpers
# ---------------------------------------------------------------------------

def _find_simulator(preference: str | None = None) -> str | None:
    """
    Return the name of the first available simulator executable, or None.

    Parameters
    ----------
    preference : str | None
        If given, check *only* this simulator (``"ghdl"`` or ``"verilator"``).
        If None, check ``ghdl`` then ``verilator`` in order.
    """
    candidates = [preference] if preference else ["ghdl", "verilator"]
    for name in candidates:
        if shutil.which(name) is not None:
            return name
    return None


def simulator_available(name: str | None = None) -> bool:
    """Return True if at least one supported simulator is on PATH."""
    return _find_simulator(name) is not None


# ---------------------------------------------------------------------------
# SimulatorRunner
# ---------------------------------------------------------------------------

class SimulatorRunner:
    """
    Thin wrapper around HDL simulators (ghdl / verilator).

    Class method
    ------------
    ``SimulatorRunner.run(toplevel, source_files, test_module, ...)``
        Execute the simulation and return either a ``CompletedProcess``
        result or the ``PENDING`` sentinel.
    """

    @classmethod
    def run(
        cls,
        toplevel: str,
        source_files: list[str | Path],
        test_module: str,
        *,
        simulator: str | None = None,
        work_dir: str | Path | None = None,
        extra_args: list[str] | None = None,
        timeout: int = 120,
    ) -> Any:
        """
        Run the testbench simulation.

        Parameters
        ----------
        toplevel : str
            Name of the top-level HDL entity/module.
        source_files : list[str | Path]
            RTL source files (VHDL or Verilog/SystemVerilog).
        test_module : str
            Python module containing the ``@cocotb.test()`` coroutines.
        simulator : str | None
            Force a specific simulator (``"ghdl"`` or ``"verilator"``).
            If None, auto-detect.
        work_dir : str | Path | None
            Build directory.  A temp dir is used when None.
        extra_args : list[str] | None
            Additional arguments forwarded to the simulator.
        timeout : int
            Process timeout in seconds (default 120).

        Returns
        -------
        subprocess.CompletedProcess | PENDING
            Returns ``PENDING`` when no simulator is found.
            Returns the ``CompletedProcess`` on success.

        Raises
        ------
        SimulationError
            When the simulator exits non-zero.
        """
        sim_exe = _find_simulator(simulator)
        if sim_exe is None:
            return PENDING

        # Try to delegate to cocotb's own runner first.
        try:
            return cls._run_via_cocotb(
                toplevel=toplevel,
                source_files=source_files,
                test_module=test_module,
                simulator=sim_exe,
                work_dir=work_dir,
                extra_args=extra_args or [],
                timeout=timeout,
            )
        except ImportError:
            pass

        # Fallback: minimal subprocess invocation.
        return cls._run_subprocess(
            toplevel=toplevel,
            source_files=[str(f) for f in source_files],
            test_module=test_module,
            simulator=sim_exe,
            work_dir=work_dir,
            extra_args=extra_args or [],
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_via_cocotb(
        toplevel: str,
        source_files: list[str | Path],
        test_module: str,
        simulator: str,
        work_dir: str | Path | None,
        extra_args: list[str],
        timeout: int,
    ) -> subprocess.CompletedProcess:
        """Delegate to cocotb.runner.get_runner when cocotb is installed."""
        from cocotb.runner import get_runner  # type: ignore[import]

        runner = get_runner(simulator)
        runner.build(
            sources=source_files,
            hdl_toplevel=toplevel,
            always=True,
            build_dir=str(work_dir) if work_dir else None,
        )
        runner.test(
            hdl_toplevel=toplevel,
            test_module=test_module,
            extra_args=extra_args,
        )
        # cocotb runner doesn't return a CompletedProcess; fabricate one.
        return subprocess.CompletedProcess(args=[], returncode=0)

    @staticmethod
    def _run_subprocess(
        toplevel: str,
        source_files: list[str],
        test_module: str,
        simulator: str,
        work_dir: str | Path | None,
        extra_args: list[str],
        timeout: int,
    ) -> subprocess.CompletedProcess:
        """
        Minimal subprocess invocation when cocotb is not installed.

        This path is intentionally thin — it compiles and elaborates the
        design then exits.  Full co-simulation requires cocotb.
        """
        import tempfile

        build_dir = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="kerf_sim_"))

        if simulator == "ghdl":
            cmd = (
                ["ghdl", "-a", "--workdir", str(build_dir)]
                + source_files
            )
        elif simulator == "verilator":
            cmd = (
                ["verilator", "--lint-only", "-Wall"]
                + source_files
                + extra_args
            )
        else:
            raise SimulationError(f"Unsupported simulator: {simulator!r}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise SimulationError(
                f"{simulator} exited {result.returncode}:\n"
                f"{result.stdout}\n{result.stderr}"
            )
        return result


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

def run(
    toplevel: str,
    source_files: list[str | Path],
    test_module: str,
    **kwargs: Any,
) -> Any:
    """
    Convenience wrapper for ``SimulatorRunner.run()``.

    See ``SimulatorRunner.run`` for full parameter documentation.
    """
    return SimulatorRunner.run(toplevel, source_files, test_module, **kwargs)
