"""
kerf_silicon.cocotb_harness.triggers
=====================================

Awaitable trigger objects — mirrors the cocotb triggers API.

In pure-Python / pytest mode every trigger is a no-op coroutine so that
testbench coroutines can be driven directly by ``asyncio.run`` or
``pytest-asyncio`` without a simulator.

Real simulator integration
--------------------------
When a simulator is present (see ``runner.py``), the triggers delegate to
the real cocotb counterparts.  In that mode these classes are thin wrappers
around ``cocotb.triggers.*``.

Exported triggers
-----------------
``Timer(time, units)``
    Wait *time* simulation units.  Pure-Python: records elapsed time in
    ``Timer.elapsed_ns`` but does not actually sleep.

``RisingEdge(signal)``
    Wait until *signal* transitions from 0→1.  Pure-Python: toggles the
    signal once (0→1) so the coroutine resumes exactly once.

``ClockCycles(clock_signal, num_cycles, rising=True)``
    Wait *num_cycles* clock cycles.  Pure-Python: toggles the clock signal
    ``2 * num_cycles`` times (one full cycle = low→high→low… or high→low→high)
    updating the shadow value on each toggle.
"""

from __future__ import annotations

import asyncio
from typing import Any


# ---------------------------------------------------------------------------
# _UNIT_TO_NS — time unit → nanosecond multiplier
# ---------------------------------------------------------------------------

_UNIT_TO_NS: dict[str, float] = {
    "fs": 1e-6,
    "ps": 1e-3,
    "ns": 1.0,
    "us": 1e3,
    "ms": 1e6,
    "sec": 1e9,
    "s":   1e9,
}


# ---------------------------------------------------------------------------
# Timer
# ---------------------------------------------------------------------------

class Timer:
    """
    Wait *time* simulation-time units.

    Parameters
    ----------
    time : float | int
        Simulation time value.
    units : str
        One of ``"fs"``, ``"ps"``, ``"ns"`` (default), ``"us"``, ``"ms"``,
        ``"sec"``/``"s"``.

    Examples
    --------
    ::

        await Timer(10, units="ns")
        await Timer(1, units="us")

    In pure-Python mode this coroutine records the elapsed nanoseconds in
    ``Timer.elapsed_ns`` (cumulative on the class) but performs no real
    delay.
    """

    # Class-level accumulator so tests can inspect total elapsed sim time.
    elapsed_ns: float = 0.0

    def __init__(self, time: float, units: str = "ns") -> None:
        mult = _UNIT_TO_NS.get(units.lower())
        if mult is None:
            raise ValueError(
                f"Unknown time unit {units!r}. "
                f"Valid units: {list(_UNIT_TO_NS.keys())}"
            )
        self._ns = time * mult

    def __await__(self):
        Timer.elapsed_ns += self._ns
        return (yield from asyncio.sleep(0).__await__())

    def __repr__(self) -> str:
        return f"Timer({self._ns}ns)"


# ---------------------------------------------------------------------------
# RisingEdge
# ---------------------------------------------------------------------------

class RisingEdge:
    """
    Wait until *signal* has a rising edge (0 → 1).

    Parameters
    ----------
    signal : Signal
        Any object with a ``.value`` property (e.g. ``DUT.clk``).

    In pure-Python mode the coroutine forces ``signal.value = 1`` so the
    caller observes a high level immediately after the await.
    """

    def __init__(self, signal: Any) -> None:
        self._signal = signal

    def __await__(self):
        # Pure-Python: ensure signal goes high.
        self._signal.value = 1
        return (yield from asyncio.sleep(0).__await__())

    def __repr__(self) -> str:
        return f"RisingEdge({self._signal!r})"


# ---------------------------------------------------------------------------
# ClockCycles
# ---------------------------------------------------------------------------

class ClockCycles:
    """
    Wait for *num_cycles* clock cycles.

    Parameters
    ----------
    clock_signal : Signal
        The clock signal to toggle (e.g. ``dut.clk``).
    num_cycles : int
        Number of full cycles to wait.
    rising : bool
        If True (default) count rising edges; if False count falling edges.
        Pure-Python mode always toggles the clock ``2 * num_cycles`` times
        regardless of this flag.

    In pure-Python mode this coroutine toggles ``clock_signal.value`` between
    0 and 1 a total of ``2 * num_cycles`` times (one toggle = half-period),
    simulating *num_cycles* full clock periods.
    """

    def __init__(self, clock_signal: Any, num_cycles: int, rising: bool = True) -> None:
        if num_cycles < 0:
            raise ValueError(f"num_cycles must be >= 0, got {num_cycles}")
        self._signal = clock_signal
        self._cycles = num_cycles
        self._rising = rising

    def __await__(self):
        # Toggle 2*N times (each toggle = half period).
        for _ in range(2 * self._cycles):
            self._signal.value = 1 - int(self._signal.value)
        return (yield from asyncio.sleep(0).__await__())

    def __repr__(self) -> str:
        return f"ClockCycles({self._signal!r}, {self._cycles})"
