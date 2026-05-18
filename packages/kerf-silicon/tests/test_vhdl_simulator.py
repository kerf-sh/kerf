"""Tests for the behavioural VHDL event-driven simulator with delta cycles."""
import pytest

try:
    from kerf_silicon.vhdl.parser import parse as _parse
    _HAS_PARSER = True
except ImportError:
    _HAS_PARSER = False

from kerf_silicon.vhdl.simulator import Simulator, SimulationError
from kerf_silicon.vhdl.std_logic import and2, not1, or2


class TestSignalBasics:
    def test_signal_initial_value(self):
        sim = Simulator()
        a = sim.add_signal("a", "0")
        assert a.value == "0"

    def test_signal_default_initial_is_u(self):
        sim = Simulator()
        a = sim.add_signal("a")
        assert a.value == "U"

    def test_duplicate_signal_raises(self):
        sim = Simulator()
        sim.add_signal("a", "0")
        with pytest.raises(ValueError):
            sim.add_signal("a", "1")

    def test_drive_without_simulator_raises(self):
        from kerf_silicon.vhdl.simulator import Signal
        sig = Signal("orphan", "0")
        with pytest.raises(RuntimeError):
            sig.drive("1")

    def test_get_signal(self):
        sim = Simulator()
        a = sim.add_signal("a", "Z")
        assert sim.get_signal("a") is a


class TestDeltaCycles:
    """Verify that delta-cycle settling works correctly."""

    def _make_and_gate_sim(self, init_a="0", init_b="1"):
        """Helper: create a simulator with a single 2-input AND gate."""
        sim = Simulator()
        a = sim.add_signal("a", init_a)
        b = sim.add_signal("b", init_b)
        out = sim.add_signal("out", "U")

        def and_gate():
            out.drive(and2(a.value, b.value))

        sim.add_process(and_gate, sensitivity=[a, b])
        return sim, a, b, out

    def test_and_gate_settles_at_t0_delta(self):
        """(1,1) -> out=1 within delta cycles at T=0."""
        sim, a, b, out = self._make_and_gate_sim("1", "1")
        sim.run_until(0)
        assert out.value == "1"

    def test_and_gate_zero_input(self):
        """(1,0) -> out=0."""
        sim, a, b, out = self._make_and_gate_sim("1", "0")
        sim.run_until(0)
        assert out.value == "0"

    def test_and_gate_both_zero(self):
        sim, a, b, out = self._make_and_gate_sim("0", "0")
        sim.run_until(0)
        assert out.value == "0"

    def test_and_gate_input_change_propagates(self):
        """Changing an input triggers re-evaluation via sensitivity."""
        sim, a, b, out = self._make_and_gate_sim("0", "1")
        sim.run_until(0)
        assert out.value == "0"  # 0 AND 1 = 0
        # Drive 'a' to 1 at T=100
        a.drive("1", delay_ps=100)
        sim.run_until(200)
        assert out.value == "1"  # 1 AND 1 = 1

    def test_not_gate_delta_cycle(self):
        sim = Simulator()
        a = sim.add_signal("a", "0")
        out = sim.add_signal("out", "U")

        def not_gate():
            out.drive(not1(a.value))

        sim.add_process(not_gate, sensitivity=[a])
        sim.run_until(0)
        assert out.value == "1"

    def test_inverter_chain_two_stages(self):
        """Two cascaded inverters: input drives first, first drives second."""
        sim = Simulator()
        a = sim.add_signal("a", "1")
        mid = sim.add_signal("mid", "U")
        out = sim.add_signal("out", "U")

        def inv1():
            mid.drive(not1(a.value))

        def inv2():
            out.drive(not1(mid.value))

        sim.add_process(inv1, sensitivity=[a])
        sim.add_process(inv2, sensitivity=[mid])
        sim.run_until(0)
        # inv1: not(1) = 0 -> mid=0; inv2: not(0) = 1 -> out=1
        assert mid.value == "0"
        assert out.value == "1"

    def test_or_gate_settles(self):
        sim = Simulator()
        a = sim.add_signal("a", "0")
        b = sim.add_signal("b", "1")
        out = sim.add_signal("out", "U")

        def or_gate():
            out.drive(or2(a.value, b.value))

        sim.add_process(or_gate, sensitivity=[a, b])
        sim.run_until(0)
        assert out.value == "1"  # 0 OR 1 = 1


class TestRealTimeDelay:
    """Tests for transport-delay (delay_ps > 0) scheduling."""

    def test_signal_updates_after_delay(self):
        """Signal driven with delay_ps arrives after the delay elapses."""
        sim = Simulator()
        x = sim.add_signal("x", "0")
        # Drive x to 1 with a 100ps delay (no process needed, just raw drive)
        x.drive("1", delay_ps=100)
        # Before 100ps x should still be 0
        sim.run_until(50)
        assert x.value == "0"
        # After 100ps x should be 1
        sim.run_until(150)
        assert x.value == "1"

    def test_process_drives_with_delay_on_sensitivity(self):
        """Process woken at T=10 drives output with 50ps delay -> arrives T=60."""
        sim = Simulator()
        trigger = sim.add_signal("trigger", "0")
        out = sim.add_signal("out", "0")

        calls = []

        def on_trigger():
            # Only drive when trigger goes high to avoid T=0 initial firing
            if trigger.value == "1":
                out.drive("1", delay_ps=50)
                calls.append(sim.now)

        sim.add_process(on_trigger, sensitivity=[trigger])
        # Trigger fires at T=10
        trigger.drive("1", delay_ps=10)
        # At T=55 out should still be 0
        sim.run_until(55)
        assert out.value == "0", f"out should be 0 at T=55, got {out.value}"
        # At T=70 out should be 1 (10 + 50 = 60ps)
        sim.run_until(70)
        assert out.value == "1", f"out should be 1 at T=70, got {out.value}"

    def test_multiple_signals_at_different_times(self):
        sim = Simulator()
        x = sim.add_signal("x", "0")
        y = sim.add_signal("y", "0")
        x.drive("1", delay_ps=100)
        y.drive("1", delay_ps=200)
        sim.run_until(150)
        assert x.value == "1"
        assert y.value == "0"
        sim.run_until(250)
        assert y.value == "1"


class TestBusResolution:
    """Multiple drivers resolved onto the same signal."""

    def test_two_drivers_one_and_z(self):
        sim = Simulator()
        out = sim.add_signal("out", "Z")
        driven = {"a": "1", "b": "Z"}

        def driver_a():
            out.drive(driven["a"])

        def driver_b():
            out.drive(driven["b"])

        sim.add_process(driver_a, sensitivity=[])
        sim.add_process(driver_b, sensitivity=[])
        sim.run_until(0)
        # Both fire at init; (1, Z) -> 1
        assert out.value == "1"


class TestParserIntegration:
    """Tests that require the VHDL parser — skipped if not available."""

    @pytest.mark.skipif(not _HAS_PARSER, reason="kerf_silicon.vhdl.parser not available")
    def test_parse_and_simulate_and_gate(self):
        """Parse a minimal VHDL entity+architecture and simulate it."""
        vhdl = """
        library ieee;
        use ieee.std_logic_1164.all;
        entity and_gate is
            port (a, b : in std_logic; y : out std_logic);
        end entity;
        architecture rtl of and_gate is
        begin
            y <= a and b;
        end architecture;
        """
        arch = _parse(vhdl)
        sim = Simulator(architecture=arch)
        a = sim.add_signal("a", "1")
        b = sim.add_signal("b", "1")
        out = sim.add_signal("y", "U")

        def and_proc():
            out.drive(and2(a.value, b.value))

        sim.add_process(and_proc, sensitivity=[a, b])
        sim.run_until(0)
        assert out.value == "1"
