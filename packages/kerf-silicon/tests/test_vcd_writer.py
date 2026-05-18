"""Tests for the VCD waveform writer."""
import io

import pytest

from kerf_silicon.vhdl.vcd_writer import VCDWriter, write_vcd


class TestVCDStructure:
    """Verify that VCD output is structurally valid."""

    def _simple_vcd(self) -> str:
        buf = io.StringIO()
        with VCDWriter(buf, timescale="1ps") as writer:
            a_id = writer.register_var("top", "a")
            writer.change(a_id, 0, "0")
            writer.change(a_id, 100, "1")
        buf.seek(0)
        return buf.read()

    def test_starts_with_timescale(self):
        text = self._simple_vcd()
        assert text.startswith("$timescale"), (
            f"VCD must start with $timescale, got: {text[:60]!r}"
        )

    def test_contains_enddefinitions(self):
        text = self._simple_vcd()
        assert "$enddefinitions $end" in text

    def test_contains_scope(self):
        text = self._simple_vcd()
        assert "$scope module top $end" in text

    def test_contains_var_declaration(self):
        text = self._simple_vcd()
        assert "$var wire 1" in text

    def test_contains_dumpvars(self):
        text = self._simple_vcd()
        assert "$dumpvars" in text

    def test_contains_time_markers(self):
        text = self._simple_vcd()
        assert "#0" in text or "#100" in text

    def test_value_change_format(self):
        text = self._simple_vcd()
        lines = text.splitlines()
        # Expect "0!" or "1!" style lines (value + id_code)
        vc_lines = [l for l in lines if l and l[0] in "01xzXZ" and not l.startswith("$")]
        assert len(vc_lines) > 0

    def test_timescale_preserved(self):
        buf = io.StringIO()
        with VCDWriter(buf, timescale="10ns") as writer:
            writer.register_var("top", "clk")
        buf.seek(0)
        text = buf.read()
        assert "10ns" in text


class TestVCDMultiSignal:
    def test_multiple_signals(self):
        buf = io.StringIO()
        with VCDWriter(buf) as writer:
            a_id = writer.register_var("top", "a")
            b_id = writer.register_var("top", "b")
            writer.change(a_id, 0, "0")
            writer.change(b_id, 0, "1")
            writer.change(a_id, 50, "1")
            writer.change(b_id, 50, "0")
        buf.seek(0)
        text = buf.read()
        assert "$var wire 1" in text
        # Should have two var declarations
        assert text.count("$var wire 1") == 2

    def test_time_ordering(self):
        """Events at different times must appear in ascending time order."""
        buf = io.StringIO()
        with VCDWriter(buf) as writer:
            a_id = writer.register_var("top", "a")
            writer.change(a_id, 200, "0")
            writer.change(a_id, 100, "1")
            writer.change(a_id, 300, "0")
        buf.seek(0)
        text = buf.read()
        lines = text.splitlines()
        times = [int(l[1:]) for l in lines if l.startswith("#")]
        assert times == sorted(times), f"Times not sorted: {times}"


class TestVCDStdLogicMapping:
    """Verify IEEE 1164 -> VCD character mapping."""

    def _get_value_lines(self, text: str) -> list[str]:
        return [
            l for l in text.splitlines()
            if l and l[0] in "01xzXZ" and not l.startswith("$")
        ]

    def test_zero_maps_to_0(self):
        buf = io.StringIO()
        with VCDWriter(buf) as writer:
            a_id = writer.register_var("top", "a")
            writer.change(a_id, 10, "0")
        buf.seek(0)
        text = buf.read()
        vc_lines = self._get_value_lines(text)
        # Find the change at T=10 (after #10 marker)
        lines = text.splitlines()
        after_10 = False
        for line in lines:
            if line == "#10":
                after_10 = True
            elif after_10 and line and line[0] in "01xz":
                assert line[0] == "0", f"Expected '0', got {line[0]!r}"
                break

    def test_unknown_maps_to_x(self):
        buf = io.StringIO()
        with VCDWriter(buf) as writer:
            a_id = writer.register_var("top", "a")
            writer.change(a_id, 10, "X")
        buf.seek(0)
        text = buf.read()
        lines = text.splitlines()
        after_10 = False
        for line in lines:
            if line == "#10":
                after_10 = True
            elif after_10 and line and line[0] in "01xz":
                assert line[0] == "x", f"Expected 'x', got {line[0]!r}"
                break

    def test_highz_maps_to_z(self):
        buf = io.StringIO()
        with VCDWriter(buf) as writer:
            a_id = writer.register_var("top", "a")
            writer.change(a_id, 10, "Z")
        buf.seek(0)
        text = buf.read()
        lines = text.splitlines()
        after_10 = False
        for line in lines:
            if line == "#10":
                after_10 = True
            elif after_10 and line and line[0] in "01xz":
                assert line[0] == "z", f"Expected 'z', got {line[0]!r}"
                break


class TestWriteVCDConvenience:
    def test_write_vcd_returns_string(self):
        text = write_vcd(
            signals={"clk": [(0, "0"), (50, "1"), (100, "0"), (150, "1")]},
        )
        assert isinstance(text, str)
        assert text.startswith("$timescale")

    def test_write_vcd_parseable(self):
        """Produced VCD text must be parseable as structured text."""
        text = write_vcd(
            signals={
                "a": [(0, "0"), (100, "1")],
                "b": [(0, "1"), (200, "0")],
            }
        )
        lines = text.splitlines()
        # Must have header keywords
        keywords = {"$timescale", "$scope", "$var", "$enddefinitions", "$dumpvars"}
        found = {l.split()[0] for l in lines if l.startswith("$")}
        assert keywords.issubset(found), f"Missing keywords: {keywords - found}"

    def test_write_vcd_empty_signals(self):
        text = write_vcd(signals={})
        assert text.startswith("$timescale")
        assert "$enddefinitions $end" in text


class TestVCDWriterClosed:
    def test_write_after_close_raises(self):
        buf = io.StringIO()
        writer = VCDWriter(buf)
        a_id = writer.register_var("top", "a")
        writer.close()
        with pytest.raises(RuntimeError):
            writer.change(a_id, 10, "1")

    def test_double_close_is_safe(self):
        buf = io.StringIO()
        writer = VCDWriter(buf)
        writer.close()
        writer.close()  # Should not raise


class TestSimulatorVCDIntegration:
    """Run the simulator and dump its state to VCD."""

    def test_and_gate_vcd_output(self):
        from kerf_silicon.vhdl.simulator import Simulator
        from kerf_silicon.vhdl.std_logic import and2

        sim = Simulator()
        a = sim.add_signal("a", "1")
        b = sim.add_signal("b", "1")
        out = sim.add_signal("out", "U")

        def and_gate():
            out.drive(and2(a.value, b.value))

        sim.add_process(and_gate, sensitivity=[a, b])
        sim.run_until(0)
        assert out.value == "1"

        # Dump to VCD
        buf = io.StringIO()
        with VCDWriter(buf) as writer:
            for name, sig in [("a", a), ("b", b), ("out", out)]:
                id_code = writer.register_var("top", name)
                writer.change(id_code, sim.now, sig.value)

        buf.seek(0)
        text = buf.read()
        assert text.startswith("$timescale")
        assert "$enddefinitions $end" in text
