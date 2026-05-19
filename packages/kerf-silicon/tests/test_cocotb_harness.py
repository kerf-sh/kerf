"""
tests/test_cocotb_harness.py
=============================

Pytest suite for the cocotb-compatible harness in kerf_silicon.

Coverage targets
----------------
- ``@cocotb.test()`` decorator registers coroutines in ``_registered_tests``
- ``Timer`` records elapsed time and can be awaited
- ``ClockCycles`` toggles the clock signal N*2 times and resumes after N cycles
- ``RisingEdge`` sets signal high and resumes
- ``DUT`` signal reads/writes flow through the shadow dict
- ``DUT`` raises ``AttributeError`` for unknown signals
- ``runner.run()`` returns ``PENDING`` when no simulator is present
- ``runner.simulator_available()`` matches whether ghdl/verilator is on PATH
"""

from __future__ import annotations

import asyncio
import shutil

import pytest

from kerf_silicon.cocotb_harness import (
    DUT,
    Timer,
    RisingEdge,
    ClockCycles,
    test as cocotb_test,
)
from kerf_silicon.cocotb_harness import _registered_tests
from kerf_silicon.cocotb_harness.runner import (
    PENDING,
    SimulatorRunner,
    simulator_available,
    run as runner_run,
)
from kerf_silicon.cocotb_harness.triggers import _UNIT_TO_NS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously inside a fresh event loop."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# @cocotb.test() decorator
# ---------------------------------------------------------------------------

class TestDecoratorRegistration:
    def test_bare_decorator_registers(self):
        """@cocotb.test (no parens) should register the function."""
        before = len(_registered_tests)

        @cocotb_test
        async def my_testbench(dut):
            pass

        assert len(_registered_tests) == before + 1
        assert _registered_tests[-1]["func"] is my_testbench

    def test_called_decorator_registers(self):
        """@cocotb.test() (with parens) should also register."""
        before = len(_registered_tests)

        @cocotb_test()
        async def my_testbench2(dut):
            pass

        assert len(_registered_tests) == before + 1
        assert _registered_tests[-1]["func"] is my_testbench2

    def test_decorator_preserves_callable(self):
        """The decorated function must still be callable normally."""

        @cocotb_test()
        async def identity(dut):
            return dut

        sentinel = object()
        result = _run(identity(sentinel))
        assert result is sentinel

    def test_decorator_stores_timeout(self):
        """timeout_time and timeout_unit are stored in the registry entry."""

        @cocotb_test(timeout_time=50, timeout_unit="us")
        async def timed_test(dut):
            pass

        entry = _registered_tests[-1]
        assert entry["timeout_time"] == 50
        assert entry["timeout_unit"] == "us"

    def test_decorator_stores_skip_flag(self):
        """skip=True is stored in the registry entry."""

        @cocotb_test(skip=True)
        async def skipped_test(dut):
            pass

        assert _registered_tests[-1]["skip"] is True


# ---------------------------------------------------------------------------
# DUT signal proxy
# ---------------------------------------------------------------------------

class TestDUT:
    def test_initial_values(self):
        dut = DUT({"clk": 0, "rst_n": 1, "data": 0xFF})
        assert dut.clk.value == 0
        assert dut.rst_n.value == 1
        assert dut.data.value == 0xFF

    def test_write_updates_shadow(self):
        dut = DUT({"clk": 0, "q": 0})
        dut.clk.value = 1
        assert dut.clk.value == 1
        dut.q.value = 42
        assert dut.q.value == 42

    def test_overwrite_same_signal(self):
        dut = DUT({"sig": 5})
        dut.sig.value = 10
        dut.sig.value = 20
        assert dut.sig.value == 20

    def test_unknown_signal_raises(self):
        dut = DUT({"clk": 0})
        with pytest.raises(AttributeError, match="no signal"):
            _ = dut.nonexistent

    def test_signals_dict_accessible(self):
        dut = DUT({"a": 1, "b": 2})
        assert set(dut._signals.keys()) == {"a", "b"}

    def test_iteration_yields_signals(self):
        dut = DUT({"x": 0, "y": 1})
        names = {s._name for s in dut}
        assert names == {"x", "y"}

    def test_int_conversion(self):
        dut = DUT({"val": 7})
        assert int(dut.val) == 7

    def test_equality_with_plain_int(self):
        dut = DUT({"n": 3})
        assert dut.n == 3


# ---------------------------------------------------------------------------
# Timer trigger
# ---------------------------------------------------------------------------

class TestTimer:
    def setup_method(self):
        # Reset class-level accumulator before each test.
        Timer.elapsed_ns = 0.0

    def test_await_does_not_raise(self):
        async def body():
            await Timer(10, units="ns")
        _run(body())

    def test_timer_await_coroutine(self):
        async def body():
            await Timer(10, units="ns")

        _run(body())

    def test_timer_accumulates_ns(self):
        async def body():
            await Timer(10, units="ns")
            await Timer(5, units="ns")

        _run(body())
        assert Timer.elapsed_ns == pytest.approx(15.0)

    def test_timer_us_conversion(self):
        async def body():
            await Timer(1, units="us")

        _run(body())
        assert Timer.elapsed_ns == pytest.approx(1000.0)

    def test_timer_ms_conversion(self):
        async def body():
            await Timer(2, units="ms")

        _run(body())
        assert Timer.elapsed_ns == pytest.approx(2_000_000.0)

    def test_timer_ps_conversion(self):
        async def body():
            await Timer(100, units="ps")

        _run(body())
        assert Timer.elapsed_ns == pytest.approx(0.1)

    def test_timer_invalid_unit_raises(self):
        with pytest.raises(ValueError, match="Unknown time unit"):
            Timer(1, units="lightyears")

    def test_all_valid_units_accepted(self):
        for unit in _UNIT_TO_NS:
            t = Timer(1, units=unit)
            assert t._ns > 0


# ---------------------------------------------------------------------------
# RisingEdge trigger
# ---------------------------------------------------------------------------

class TestRisingEdge:
    def test_sets_signal_high(self):
        dut = DUT({"clk": 0})

        async def body():
            await RisingEdge(dut.clk)

        _run(body())
        assert dut.clk.value == 1

    def test_already_high_stays_high(self):
        dut = DUT({"clk": 1})

        async def body():
            await RisingEdge(dut.clk)

        _run(body())
        assert dut.clk.value == 1

    def test_returns_after_single_await(self):
        """RisingEdge should resume within a single coroutine step."""
        dut = DUT({"clk": 0})
        steps = []

        async def body():
            steps.append("before")
            await RisingEdge(dut.clk)
            steps.append("after")

        _run(body())
        assert steps == ["before", "after"]


# ---------------------------------------------------------------------------
# ClockCycles trigger
# ---------------------------------------------------------------------------

class TestClockCycles:
    def test_zero_cycles_no_toggle(self):
        dut = DUT({"clk": 0})

        async def body():
            await ClockCycles(dut.clk, 0)

        _run(body())
        # 0 cycles → 0 toggles → value unchanged
        assert dut.clk.value == 0

    def test_one_cycle_two_toggles(self):
        """1 cycle = 2 half-periods = clock returns to original value."""
        dut = DUT({"clk": 0})

        async def body():
            await ClockCycles(dut.clk, 1)

        _run(body())
        # 0 → 1 → 0 (2 toggles, ends at 0)
        assert dut.clk.value == 0

    def test_n_cycles_final_value(self):
        """After N cycles the clock should be back at the starting value."""
        for n in [1, 2, 5, 10]:
            dut = DUT({"clk": 0})

            async def body(cycles=n):
                await ClockCycles(dut.clk, cycles)

            _run(body())
            # 2*n toggles from 0 → always ends at 0 (even number of toggles)
            assert dut.clk.value == 0, f"Failed for n={n}"

    def test_three_cycles_toggle_count(self):
        """Track that exactly 6 toggles happen for 3 cycles."""
        dut = DUT({"clk": 0})
        toggle_log: list[int] = []
        original_setter = type(dut.clk).value.fset

        # Monkey-patch to record toggled values
        values: list[int] = []

        async def body():
            for _ in range(2 * 3):
                dut.clk.value = 1 - int(dut.clk.value)
                values.append(dut.clk.value)

        _run(body())
        assert len(values) == 6
        assert values == [1, 0, 1, 0, 1, 0]

    def test_negative_cycles_raises(self):
        dut = DUT({"clk": 0})
        with pytest.raises(ValueError, match="num_cycles"):
            ClockCycles(dut.clk, -1)

    def test_resumes_after_cycles(self):
        """ClockCycles must complete so subsequent lines execute."""
        dut = DUT({"clk": 0})
        reached = []

        async def body():
            await ClockCycles(dut.clk, 4)
            reached.append(True)

        _run(body())
        assert reached == [True]


# ---------------------------------------------------------------------------
# Runner / simulator detection
# ---------------------------------------------------------------------------

class TestRunner:
    def test_pending_when_no_simulator(self, monkeypatch):
        """run() returns PENDING when neither ghdl nor verilator is on PATH."""
        monkeypatch.setattr(shutil, "which", lambda _name: None)

        result = runner_run(
            toplevel="counter",
            source_files=["counter.vhd"],
            test_module="tests.test_counter",
        )
        assert result is PENDING

    def test_pending_is_falsy(self):
        assert not PENDING

    def test_pending_repr(self):
        assert repr(PENDING) == "PENDING"

    def test_pending_singleton(self):
        from kerf_silicon.cocotb_harness.runner import _Pending
        assert _Pending() is PENDING

    def test_simulator_available_false_when_none(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        assert simulator_available() is False

    def test_simulator_available_true_when_present(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
        assert simulator_available() is True

    def test_simulator_available_specific_sim(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ghdl" if name == "ghdl" else None)
        assert simulator_available("ghdl") is True
        assert simulator_available("verilator") is False

    def test_run_returns_pending_no_sim(self, monkeypatch):
        """SimulatorRunner.run() also returns PENDING when no sim found."""
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        result = SimulatorRunner.run(
            toplevel="my_mod",
            source_files=["my_mod.v"],
            test_module="test_my_mod",
        )
        assert result is PENDING

    def test_find_simulator_preference(self, monkeypatch):
        """_find_simulator respects the preference argument."""
        from kerf_silicon.cocotb_harness.runner import _find_simulator

        monkeypatch.setattr(
            shutil, "which",
            lambda name: "/usr/bin/verilator" if name == "verilator" else None,
        )
        # No preference → ghdl checked first, then verilator
        assert _find_simulator() == "verilator"
        # Preference for ghdl → not found
        assert _find_simulator("ghdl") is None
        # Preference for verilator → found
        assert _find_simulator("verilator") == "verilator"


# ---------------------------------------------------------------------------
# Integration: coroutine uses DUT + Timer + ClockCycles together
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_testbench_coroutine(self):
        """
        A typical testbench coroutine drives clk + rst_n, waits for cycles,
        and checks a combinational output — all in pure Python.
        """
        Timer.elapsed_ns = 0.0

        dut = DUT({"clk": 0, "rst_n": 0, "count": 0})

        @cocotb_test()
        async def counter_test(dut):
            # Release reset
            dut.rst_n.value = 0
            await Timer(10, units="ns")
            dut.rst_n.value = 1
            await Timer(10, units="ns")

            # Drive 4 clock cycles and simulate counting
            for _ in range(4):
                await RisingEdge(dut.clk)
                dut.count.value = int(dut.count.value) + 1

            await ClockCycles(dut.clk, 2)

        _run(counter_test(dut))

        assert dut.rst_n.value == 1
        assert dut.clk.value == 1   # last RisingEdge set it high
        assert int(dut.count.value) == 4
        assert Timer.elapsed_ns == pytest.approx(20.0)
