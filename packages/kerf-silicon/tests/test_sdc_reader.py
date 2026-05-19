"""test_sdc_reader.py — pytest suite for kerf_silicon.sta.sdc_reader.

Run with::

    PYTHONPATH=packages/kerf-core/src:packages/kerf-silicon/src \\
        python3 -m pytest packages/kerf-silicon/tests/test_sdc_reader.py -x
"""
from __future__ import annotations

import pytest

from kerf_silicon.sta.sdc_reader import (
    parse_sdc,
    SDCConstraints,
    ClockDef,
    InputDelay,
    OutputDelay,
    MaxDelay,
    FalsePath,
)


# ---------------------------------------------------------------------------
# create_clock
# ---------------------------------------------------------------------------


class TestCreateClock:
    def test_parses_period(self):
        sdc = parse_sdc("create_clock -period 10 [get_ports clk]")
        assert len(sdc.clocks) == 1
        assert sdc.clocks[0].period_ns == pytest.approx(10.0)

    def test_parses_period_float(self):
        sdc = parse_sdc("create_clock -period 3.14 clk")
        assert sdc.clocks[0].period_ns == pytest.approx(3.14)

    def test_parses_name_flag(self):
        sdc = parse_sdc("create_clock -period 5 -name myclk clk")
        assert sdc.clocks[0].name == "myclk"

    def test_default_name_from_port(self):
        sdc = parse_sdc("create_clock -period 10 clk")
        assert sdc.clocks[0].port == "clk"

    def test_period_100mhz(self):
        """100 MHz = 10 ns period."""
        sdc = parse_sdc("create_clock -period 10 -name clk [get_ports clk]")
        assert sdc.clocks[0].period_ns == pytest.approx(10.0)

    def test_period_200mhz(self):
        """200 MHz = 5 ns period."""
        sdc = parse_sdc("create_clock -period 5 clk")
        assert sdc.clocks[0].period_ns == pytest.approx(5.0)

    def test_multiple_clocks(self):
        sdc = parse_sdc(
            "create_clock -period 10 clk\n"
            "create_clock -period 20 -name slow_clk slow_clk\n"
        )
        assert len(sdc.clocks) == 2
        periods = {c.period_ns for c in sdc.clocks}
        assert 10.0 in periods
        assert 20.0 in periods

    def test_missing_period_not_added(self):
        sdc = parse_sdc("create_clock clk")
        assert len(sdc.clocks) == 0

    def test_waveform_ignored(self):
        """waveform option should not break parsing."""
        sdc = parse_sdc("create_clock -period 10 -waveform {0 5} clk")
        assert len(sdc.clocks) == 1
        assert sdc.clocks[0].period_ns == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# set_input_delay
# ---------------------------------------------------------------------------


class TestSetInputDelay:
    def test_basic(self):
        sdc = parse_sdc("set_input_delay -clock clk 2.0 in_a")
        assert len(sdc.input_delays) == 1
        assert sdc.input_delays[0].delay_ns == pytest.approx(2.0)
        assert sdc.input_delays[0].clock == "clk"

    def test_port_captured(self):
        sdc = parse_sdc("set_input_delay -clock clk 1.5 my_port")
        assert sdc.input_delays[0].ports == ["my_port"]

    def test_negative_delay(self):
        sdc = parse_sdc("set_input_delay -clock clk -1.0 in_a")
        assert sdc.input_delays[0].delay_ns == pytest.approx(-1.0)

    def test_multiple_ports(self):
        # Two separate statements
        sdc = parse_sdc(
            "set_input_delay -clock clk 2.0 in_a\n"
            "set_input_delay -clock clk 3.0 in_b\n"
        )
        assert len(sdc.input_delays) == 2
        delays = {d.ports[0]: d.delay_ns for d in sdc.input_delays}
        assert delays["in_a"] == pytest.approx(2.0)
        assert delays["in_b"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# set_output_delay
# ---------------------------------------------------------------------------


class TestSetOutputDelay:
    def test_basic(self):
        sdc = parse_sdc("set_output_delay -clock clk 1.0 out_z")
        assert len(sdc.output_delays) == 1
        assert sdc.output_delays[0].delay_ns == pytest.approx(1.0)
        assert sdc.output_delays[0].clock == "clk"

    def test_port_captured(self):
        sdc = parse_sdc("set_output_delay -clock clk 2.5 out_q")
        assert sdc.output_delays[0].ports == ["out_q"]

    def test_zero_delay(self):
        sdc = parse_sdc("set_output_delay -clock clk 0.0 out_z")
        assert sdc.output_delays[0].delay_ns == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# set_max_delay
# ---------------------------------------------------------------------------


class TestSetMaxDelay:
    def test_basic(self):
        sdc = parse_sdc("set_max_delay 5.0 -from in_a -to out_z")
        assert len(sdc.max_delays) == 1
        assert sdc.max_delays[0].delay_ns == pytest.approx(5.0)

    def test_from_to(self):
        sdc = parse_sdc("set_max_delay 3.0 -from src_reg -to dst_reg")
        assert sdc.max_delays[0].from_ == "src_reg"
        assert sdc.max_delays[0].to == "dst_reg"

    def test_datapath_only_flag_ignored(self):
        sdc = parse_sdc("set_max_delay -datapath_only 4.0 -from a -to b")
        assert sdc.max_delays[0].delay_ns == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# set_false_path
# ---------------------------------------------------------------------------


class TestSetFalsePath:
    def test_basic(self):
        sdc = parse_sdc("set_false_path -from scan_in -to scan_out")
        assert len(sdc.false_paths) == 1
        assert sdc.false_paths[0].from_ == "scan_in"
        assert sdc.false_paths[0].to == "scan_out"

    def test_only_from(self):
        sdc = parse_sdc("set_false_path -from reset_n")
        assert sdc.false_paths[0].from_ == "reset_n"
        assert sdc.false_paths[0].to == ""

    def test_only_to(self):
        sdc = parse_sdc("set_false_path -to scan_out")
        assert sdc.false_paths[0].to == "scan_out"
        assert sdc.false_paths[0].from_ == ""

    def test_setup_flag_ignored(self):
        sdc = parse_sdc("set_false_path -setup -from a -to b")
        assert sdc.false_paths[0].from_ == "a"
        assert sdc.false_paths[0].to == "b"


# ---------------------------------------------------------------------------
# Comments and line continuation
# ---------------------------------------------------------------------------


class TestCommentsAndContinuation:
    def test_hash_comment_stripped(self):
        sdc = parse_sdc("# This is a comment\ncreate_clock -period 10 clk")
        assert len(sdc.clocks) == 1

    def test_inline_comment_stripped(self):
        sdc = parse_sdc("create_clock -period 10 clk  # 100 MHz clock")
        assert len(sdc.clocks) == 1
        assert sdc.clocks[0].period_ns == pytest.approx(10.0)

    def test_backslash_continuation(self):
        sdc = parse_sdc(
            "create_clock -period 10 \\\n"
            "    clk\n"
        )
        assert len(sdc.clocks) == 1
        assert sdc.clocks[0].period_ns == pytest.approx(10.0)

    def test_empty_lines_ignored(self):
        sdc = parse_sdc("\n\n\ncreate_clock -period 5 clk\n\n")
        assert len(sdc.clocks) == 1

    def test_unknown_command_skipped(self):
        sdc = parse_sdc(
            "set_driving_cell -cell inv_1 in_a\n"
            "create_clock -period 10 clk\n"
        )
        # set_driving_cell is unknown; only create_clock should be parsed
        assert len(sdc.clocks) == 1
        assert sdc.input_delays == []


# ---------------------------------------------------------------------------
# Mixed constraints
# ---------------------------------------------------------------------------


class TestMixedConstraints:
    SDC = """
# 100 MHz design constraints
create_clock -period 10 -name clk [get_ports clk]
set_input_delay  -clock clk 2.0 in_a
set_input_delay  -clock clk 1.5 in_b
set_output_delay -clock clk 1.0 out_z
set_max_delay 8.0 -from in_a -to out_z
set_false_path -from scan_in -to scan_out
"""

    def test_all_commands_parsed(self):
        sdc = parse_sdc(self.SDC)
        assert len(sdc.clocks) == 1
        assert len(sdc.input_delays) == 2
        assert len(sdc.output_delays) == 1
        assert len(sdc.max_delays) == 1
        assert len(sdc.false_paths) == 1

    def test_clock_name(self):
        sdc = parse_sdc(self.SDC)
        assert sdc.clocks[0].name == "clk"

    def test_clock_period(self):
        sdc = parse_sdc(self.SDC)
        assert sdc.clocks[0].period_ns == pytest.approx(10.0)

    def test_input_delays_sum(self):
        sdc = parse_sdc(self.SDC)
        total = sum(d.delay_ns for d in sdc.input_delays)
        assert total == pytest.approx(2.0 + 1.5)

    def test_false_path_from_to(self):
        sdc = parse_sdc(self.SDC)
        fp = sdc.false_paths[0]
        assert fp.from_ == "scan_in"
        assert fp.to == "scan_out"


# ---------------------------------------------------------------------------
# Return-type checks
# ---------------------------------------------------------------------------


class TestReturnTypes:
    def test_returns_sdc_constraints(self):
        sdc = parse_sdc("")
        assert isinstance(sdc, SDCConstraints)

    def test_clock_is_clock_def(self):
        sdc = parse_sdc("create_clock -period 10 clk")
        assert isinstance(sdc.clocks[0], ClockDef)

    def test_input_delay_is_input_delay(self):
        sdc = parse_sdc("set_input_delay -clock clk 1.0 p")
        assert isinstance(sdc.input_delays[0], InputDelay)

    def test_output_delay_is_output_delay(self):
        sdc = parse_sdc("set_output_delay -clock clk 1.0 p")
        assert isinstance(sdc.output_delays[0], OutputDelay)

    def test_max_delay_is_max_delay(self):
        sdc = parse_sdc("set_max_delay 5 -from a -to b")
        assert isinstance(sdc.max_delays[0], MaxDelay)

    def test_false_path_is_false_path(self):
        sdc = parse_sdc("set_false_path -from a -to b")
        assert isinstance(sdc.false_paths[0], FalsePath)
