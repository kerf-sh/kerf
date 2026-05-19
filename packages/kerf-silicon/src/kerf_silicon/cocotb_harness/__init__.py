"""
kerf_silicon.cocotb_harness
===========================

A cocotb-compatible Python testbench harness for VHDL/Verilog simulators.

Provides a drop-in subset of the cocotb API that:
  - Works without any installed simulator (pure-Python, tests run as
    regular pytest cases).
  - When ghdl or verilator is present, delegates to a real simulator via
    ``runner.run()``.
  - Marks individual tests as PENDING (xfail) when no simulator is detected
    rather than erroring hard.

Exported API (mirrors cocotb public surface):
  ``test``          — decorator to register a coroutine as a testbench test
  ``DUT``           — signal-container proxy (see dut.py)
  ``Timer``         — wait N time units (see triggers.py)
  ``RisingEdge``    — wait for a rising edge on a signal (see triggers.py)
  ``ClockCycles``   — wait for N clock cycles (see triggers.py)
  ``runner``        — SimulatorRunner factory / run helper (see runner.py)
"""

from .dut import DUT
from .triggers import Timer, RisingEdge, ClockCycles
from . import runner as runner_module

__all__ = [
    "test",
    "DUT",
    "Timer",
    "RisingEdge",
    "ClockCycles",
    "runner_module",
]

# ---------------------------------------------------------------------------
# Registry of test coroutines (populated by @cocotb.test())
# ---------------------------------------------------------------------------

_registered_tests: list = []


def test(_func=None, *, timeout_time=None, timeout_unit="ns", skip=False):
    """
    Decorator: ``@cocotb.test()`` or ``@cocotb.test``.

    Registers *func* (an async coroutine) as a simulator testbench entry
    point.  The decorator does NOT alter the callable — pytest can still
    discover and invoke it directly.

    Parameters
    ----------
    timeout_time : float | None
        Optional simulation-time timeout (informational; respected by
        ``runner.run`` when a real simulator is used).
    timeout_unit : str
        Time unit for ``timeout_time`` (default ``"ns"``).
    skip : bool
        If True the test is registered but skipped.
    """

    def decorator(func):
        _registered_tests.append({
            "func": func,
            "timeout_time": timeout_time,
            "timeout_unit": timeout_unit,
            "skip": skip,
        })
        return func

    if _func is not None:
        # Called as @cocotb.test (no parentheses)
        return decorator(_func)
    # Called as @cocotb.test(...)
    return decorator
