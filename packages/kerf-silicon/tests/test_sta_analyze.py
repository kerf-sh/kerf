"""test_sta_analyze.py — pytest suite for kerf_silicon.sta.analyze.

Run with::

    PYTHONPATH=packages/kerf-core/src:packages/kerf-silicon/src \\
        python3 -m pytest packages/kerf-silicon/tests/test_sta_analyze.py -x
"""
from __future__ import annotations

import pathlib
import pytest

from kerf_silicon.liberty import parse as parse_liberty
from kerf_silicon.sta.analyze import analyze, STAReport, PathReport
from kerf_silicon.sta.sdc_reader import parse_sdc

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
INV1_LIB = FIXTURES / "inv_1.lib"

INV_CELL = "sky130_fd_sc_hd__inv_1"


@pytest.fixture(scope="module")
def inv_lib():
    return parse_liberty(INV1_LIB.read_text())


def _two_inv_netlist():
    """Two-inverter chain: in_a -> u1(INV) -> u2(INV) -> out_z."""
    return {
        "module": "two_inv",
        "ports": {
            "in_a": {"direction": "input"},
            "out_z": {"direction": "output"},
        },
        "instances": {
            "u1": {
                "cell": INV_CELL,
                "connections": {"A": "in_a", "Y": "net1"},
            },
            "u2": {
                "cell": INV_CELL,
                "connections": {"A": "net1", "Y": "out_z"},
            },
        },
    }


def _reconvergent_netlist():
    """
    Fan-out then reconvergent:
      in_a -> u1(INV) -> net1 -> u2(INV) -> out_y  (path length 2)
                               -> u3(INV) -> out_z  (path length 2)
    Both paths go through u1 — arrival at out_y/out_z must equal
    max(arrival_at_u1_Y + arc_delay) = 2 * inv_delay.
    """
    return {
        "module": "reconvergent",
        "ports": {
            "in_a": {"direction": "input"},
            "out_y": {"direction": "output"},
            "out_z": {"direction": "output"},
        },
        "instances": {
            "u1": {
                "cell": INV_CELL,
                "connections": {"A": "in_a", "Y": "net1"},
            },
            "u2": {
                "cell": INV_CELL,
                "connections": {"A": "net1", "Y": "out_y"},
            },
            "u3": {
                "cell": INV_CELL,
                "connections": {"A": "net1", "Y": "out_z"},
            },
        },
    }


def _get_inv_delay(lib) -> float:
    """Extract the cell_rise delay for inv_1 at (0.05 ns, 0.005 pF)."""
    from kerf_silicon.sta.graph import TimingGraph
    g = TimingGraph(
        {"module": "x",
         "ports": {"in_a": {"direction": "input"}, "out_z": {"direction": "output"}},
         "instances": {"u1": {"cell": INV_CELL, "connections": {"A": "in_a", "Y": "out_z"}}}},
        lib, transition_ns=0.05, load_cap_pf=0.005,
    )
    # The internal arc from u1/A to u1/Y carries the delay
    arcs = [e for e in g.successors("u1/A") if e.dst == "u1/Y"]
    assert arcs
    return arcs[0].delay


# ---------------------------------------------------------------------------
# Tests: Two-inverter chain
# ---------------------------------------------------------------------------


class TestTwoInverterChain:
    def test_report_type(self, inv_lib):
        report = analyze(_two_inv_netlist(), inv_lib)
        assert isinstance(report, STAReport)

    def test_arrival_at_out_equals_two_inv_delays(self, inv_lib):
        """Arrival at out_z = 2 × inv_delay (forward propagation)."""
        inv_delay = _get_inv_delay(inv_lib)
        # Use a very loose clock so slack is positive
        sdc = parse_sdc("create_clock -period 100 clk")
        rep = analyze(_two_inv_netlist(), inv_lib, sdc)

        # Extract the endpoint arrival from worst_paths
        path = next(
            (p for p in rep.worst_paths if p.endpoint == "out_z"), None
        )
        assert path is not None
        # arrival should be approximately 2 * inv_delay
        assert path.arrival == pytest.approx(2 * inv_delay, rel=1e-6)

    def test_worst_path_endpoint_is_out_z(self, inv_lib):
        sdc = parse_sdc("create_clock -period 100 clk")
        report = analyze(_two_inv_netlist(), inv_lib, sdc)
        endpoints = {p.endpoint for p in report.worst_paths}
        assert "out_z" in endpoints

    def test_worst_path_startpoint_is_in_a(self, inv_lib):
        sdc = parse_sdc("create_clock -period 100 clk")
        report = analyze(_two_inv_netlist(), inv_lib, sdc)
        path = next(p for p in report.worst_paths if p.endpoint == "out_z")
        assert path.startpoint == "in_a"

    def test_slack_positive_with_loose_clock(self, inv_lib):
        sdc = parse_sdc("create_clock -period 100 clk")
        report = analyze(_two_inv_netlist(), inv_lib, sdc)
        path = next(p for p in report.worst_paths if p.endpoint == "out_z")
        assert path.slack > 0.0

    def test_path_report_has_segments(self, inv_lib):
        sdc = parse_sdc("create_clock -period 100 clk")
        report = analyze(_two_inv_netlist(), inv_lib, sdc)
        path = next(p for p in report.worst_paths if p.endpoint == "out_z")
        assert len(path.segments) >= 2  # at least startpoint + endpoint

    def test_segments_monotonically_increasing_arrival(self, inv_lib):
        sdc = parse_sdc("create_clock -period 100 clk")
        report = analyze(_two_inv_netlist(), inv_lib, sdc)
        path = next(p for p in report.worst_paths if p.endpoint == "out_z")
        arrivals = [s.arrival for s in path.segments]
        for i in range(len(arrivals) - 1):
            assert arrivals[i] <= arrivals[i + 1] + 1e-12


# ---------------------------------------------------------------------------
# Tests: Reconvergent path — max arrival wins
# ---------------------------------------------------------------------------


class TestReconvergentPath:
    def test_reconvergent_arrival_equals_max(self, inv_lib):
        """out_y and out_z both receive arrival from u1/Y; must equal 2 * inv_delay."""
        inv_delay = _get_inv_delay(inv_lib)
        sdc = parse_sdc("create_clock -period 100 clk")
        rep = analyze(_reconvergent_netlist(), inv_lib, sdc)

        for ep in ("out_y", "out_z"):
            path = next(
                (p for p in rep.worst_paths if p.endpoint == ep), None
            )
            assert path is not None, f"No path to {ep}"
            # Both go through u1 so arrival = 2 * inv_delay
            assert path.arrival == pytest.approx(2 * inv_delay, rel=1e-6), (
                f"arrival at {ep}: {path.arrival} ≠ 2 * {inv_delay}"
            )

    def test_reconvergent_both_endpoints_reported(self, inv_lib):
        sdc = parse_sdc("create_clock -period 100 clk")
        rep = analyze(_reconvergent_netlist(), inv_lib, sdc)
        endpoints = {p.endpoint for p in rep.worst_paths}
        assert "out_y" in endpoints
        assert "out_z" in endpoints


# ---------------------------------------------------------------------------
# Tests: Setup violation
# ---------------------------------------------------------------------------


class TestSetupViolation:
    def test_violation_fires_with_tight_clock(self, inv_lib):
        """A clock period tighter than the path delay must produce a violation."""
        inv_delay = _get_inv_delay(inv_lib)
        # Set period to less than 2 * inv_delay to guarantee negative slack
        tight_period = inv_delay  # half the path delay
        sdc = parse_sdc(f"create_clock -period {tight_period:.6f} clk")
        report = analyze(_two_inv_netlist(), inv_lib, sdc)
        assert report.has_violations, (
            f"Expected setup violation with period={tight_period:.6f} "
            f"< path_delay={2 * inv_delay:.6f}"
        )

    def test_violation_slack_is_negative(self, inv_lib):
        inv_delay = _get_inv_delay(inv_lib)
        tight_period = inv_delay
        sdc = parse_sdc(f"create_clock -period {tight_period:.6f} clk")
        report = analyze(_two_inv_netlist(), inv_lib, sdc)
        violations = [p for p in report.worst_paths if p.is_violated]
        assert violations
        assert violations[0].slack < 0.0

    def test_no_violation_with_loose_clock(self, inv_lib):
        sdc = parse_sdc("create_clock -period 100 clk")
        report = analyze(_two_inv_netlist(), inv_lib, sdc)
        assert not report.has_violations


# ---------------------------------------------------------------------------
# Tests: SDC input delay shifts arrival
# ---------------------------------------------------------------------------


class TestInputDelayShift:
    def test_input_delay_shifts_arrival(self, inv_lib):
        """set_input_delay 2.0 must add 2 ns to arrival at all downstream nodes."""
        sdc_no_delay = parse_sdc("create_clock -period 100 clk")
        sdc_with_delay = parse_sdc(
            "create_clock -period 100 clk\n"
            "set_input_delay -clock clk 2.0 in_a"
        )

        rep_no = analyze(_two_inv_netlist(), inv_lib, sdc_no_delay)
        rep_wd = analyze(_two_inv_netlist(), inv_lib, sdc_with_delay)

        path_no = next(p for p in rep_no.worst_paths if p.endpoint == "out_z")
        path_wd = next(p for p in rep_wd.worst_paths if p.endpoint == "out_z")

        # Arrival with delay should be exactly 2 ns more
        assert path_wd.arrival == pytest.approx(path_no.arrival + 2.0, abs=1e-9)

    def test_input_delay_reduces_slack(self, inv_lib):
        sdc_no_delay = parse_sdc("create_clock -period 100 clk")
        sdc_with_delay = parse_sdc(
            "create_clock -period 100 clk\n"
            "set_input_delay -clock clk 2.0 in_a"
        )
        rep_no = analyze(_two_inv_netlist(), inv_lib, sdc_no_delay)
        rep_wd = analyze(_two_inv_netlist(), inv_lib, sdc_with_delay)
        path_no = next(p for p in rep_no.worst_paths if p.endpoint == "out_z")
        path_wd = next(p for p in rep_wd.worst_paths if p.endpoint == "out_z")
        # slack = required - arrival; more arrival → less slack
        assert path_wd.slack < path_no.slack


# ---------------------------------------------------------------------------
# Tests: Clock period
# ---------------------------------------------------------------------------


class TestClockPeriod:
    def test_clock_period_recorded_in_report(self, inv_lib):
        sdc = parse_sdc("create_clock -period 10 clk")
        report = analyze(_two_inv_netlist(), inv_lib, sdc)
        assert report.clock_period_ns == pytest.approx(10.0)

    def test_default_clock_period_is_10ns(self, inv_lib):
        report = analyze(_two_inv_netlist(), inv_lib)
        assert report.clock_period_ns == pytest.approx(10.0)

    def test_custom_clock_period_25ns(self, inv_lib):
        sdc = parse_sdc("create_clock -period 25 clk")
        report = analyze(_two_inv_netlist(), inv_lib, sdc)
        assert report.clock_period_ns == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# Tests: worst_n paths
# ---------------------------------------------------------------------------


class TestWorstNPaths:
    def test_worst_paths_default_limit(self, inv_lib):
        """Default worst_n=10 limits result list."""
        # single-output design has only 1 endpoint
        report = analyze(_two_inv_netlist(), inv_lib)
        assert len(report.worst_paths) <= 10

    def test_worst_paths_sorted_by_slack(self, inv_lib):
        sdc = parse_sdc("create_clock -period 100 clk")
        report = analyze(_reconvergent_netlist(), inv_lib, sdc)
        slacks = [p.slack for p in report.worst_paths]
        assert slacks == sorted(slacks), "worst_paths should be sorted by ascending slack"

    def test_worst_n_1_returns_single_path(self, inv_lib):
        sdc = parse_sdc("create_clock -period 100 clk")
        report = analyze(_two_inv_netlist(), inv_lib, sdc, worst_n=1)
        assert len(report.worst_paths) == 1

    def test_worst_slack_property(self, inv_lib):
        sdc = parse_sdc("create_clock -period 100 clk")
        report = analyze(_two_inv_netlist(), inv_lib, sdc)
        assert report.worst_slack == min(report.endpoint_slack.values())
