"""
Tests for kerf_piping — P&ID data model, isometric routing, symbols, tools.

DoD reference (T-167):
  - 3-component loop (pump → vessel → HX) routes isometrically
  - Correct elbow counts for the loop
  - SVG export produces valid SVG with component count
  - import_pid round-trips a text spec
  - pytest green
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys

import pytest

# sys.path bootstrap (also handled by conftest, but belt-and-suspenders)
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from kerf_piping.pid import (
    Point3, ORIGIN,
    Nozzle, PipeSchedule,
    Vessel, Pump, HeatExchanger, Valve, Instrument,
    ValveType, InstrumentVariable, InstrumentFunction,
    Pipe, FlowDirection,
    PIDDiagram,
)
from kerf_piping.isometric import (
    route_orthogonal, route_loop, count_fittings, pipe_length,
    summarise_route, FittingType, FittingCount,
)
from kerf_piping.symbols import pid_diagram_svg, symbol_for
from kerf_piping.tools import _parse_pid_text


# ===========================================================================
# pid.py — data model tests
# ===========================================================================

class TestPoint3:
    def test_distance_zero(self):
        p = Point3(1.0, 2.0, 3.0)
        assert p.distance_to(p) == pytest.approx(0.0)

    def test_distance_known(self):
        a = Point3(0.0, 0.0, 0.0)
        b = Point3(3.0, 4.0, 0.0)
        assert a.distance_to(b) == pytest.approx(5.0)

    def test_add(self):
        a = Point3(1, 2, 3)
        b = Point3(4, 5, 6)
        c = a + b
        assert c == Point3(5, 7, 9)

    def test_sub(self):
        a = Point3(5, 5, 5)
        b = Point3(2, 1, 3)
        c = a - b
        assert c == Point3(3, 4, 2)

    def test_as_tuple(self):
        p = Point3(1.0, 2.0, 3.0)
        assert p.as_tuple() == (1.0, 2.0, 3.0)


class TestNozzle:
    def test_default_nozzle(self):
        n = Nozzle("N1")
        assert n.tag == "N1"
        assert n.connected_to is None
        assert n.diameter_mm == 50.0

    def test_nozzle_with_position(self):
        p = Point3(1.0, 2.0, 3.0)
        n = Nozzle("inlet", position=p, diameter_mm=100.0)
        assert n.position == p
        assert n.diameter_mm == 100.0


class TestVessel:
    def test_vessel_created(self):
        v = Vessel("V-101")
        assert v.tag == "V-101"

    def test_default_nozzles(self):
        v = Vessel("V-101")
        assert "inlet" in v.nozzles
        assert "outlet" in v.nozzles

    def test_vessel_parameters(self):
        v = Vessel("V-102", vessel_type="column", diameter_m=1.5, length_m=5.0)
        assert v.vessel_type == "column"
        assert v.diameter_m == 1.5
        assert v.length_m == 5.0


class TestPump:
    def test_pump_created(self):
        p = Pump("P-101", flow_m3h=20.0, head_m=50.0)
        assert p.tag == "P-101"
        assert p.flow_m3h == 20.0

    def test_pump_nozzles(self):
        p = Pump("P-101")
        assert "suction" in p.nozzles
        assert "discharge" in p.nozzles


class TestHeatExchanger:
    def test_hx_created(self):
        hx = HeatExchanger("E-101", duty_kw=1000.0)
        assert hx.tag == "E-101"
        assert hx.duty_kw == 1000.0

    def test_hx_nozzles(self):
        hx = HeatExchanger("E-101")
        assert "shell_inlet" in hx.nozzles
        assert "shell_outlet" in hx.nozzles
        assert "tube_inlet" in hx.nozzles
        assert "tube_outlet" in hx.nozzles


class TestValve:
    def test_valve_gate(self):
        v = Valve("XV-101", valve_type=ValveType.GATE)
        assert v.valve_type == ValveType.GATE

    def test_valve_ball(self):
        v = Valve("XV-102", valve_type=ValveType.BALL)
        assert v.valve_type == ValveType.BALL

    def test_valve_nozzles(self):
        v = Valve("XV-103")
        assert "inlet" in v.nozzles
        assert "outlet" in v.nozzles


class TestInstrument:
    def test_instrument_tag_parse(self):
        i = Instrument("FT-101")
        assert i.tag == "FT-101"
        # Should parse variable=F (flow), function=T (transmitter)
        assert i.variable == InstrumentVariable.FLOW
        assert i.function == InstrumentFunction.TRANSMITTER
        assert i.loop_number == 101

    def test_pressure_indicator_controller(self):
        i = Instrument("PIC-202")
        assert i.variable == InstrumentVariable.PRESSURE
        assert i.loop_number == 202

    def test_level_transmitter(self):
        i = Instrument("LT-305")
        assert i.variable == InstrumentVariable.LEVEL


class TestPipe:
    def test_pipe_line_designation(self):
        p = Pipe(tag='', from_equipment='P-101', from_nozzle='discharge',
                  to_equipment='V-101', to_nozzle='inlet',
                  diameter_mm=50.0, schedule=PipeSchedule.SCH_40,
                  fluid='water')
        ld = p.line_designation()
        assert '50' in ld or 'WA' in ld

    def test_pipe_tag_used_if_set(self):
        p = Pipe(tag='4"-WA-101-A1', from_equipment='A', from_nozzle='x',
                  to_equipment='B', to_nozzle='y')
        assert p.line_designation() == '4"-WA-101-A1'


class TestPIDDiagram:
    def _make_simple_diagram(self) -> PIDDiagram:
        diag = PIDDiagram("TEST-001")
        pump = Pump("P-101", position=Point3(0, 0, 0))
        vessel = Vessel("V-101", position=Point3(5, 0, 0))
        hx = HeatExchanger("E-101", position=Point3(10, 0, 0))
        diag.add_component(pump)
        diag.add_component(vessel)
        diag.add_component(hx)
        pipe1 = Pipe(
            tag="2\"-PR-001",
            from_equipment="P-101", from_nozzle="discharge",
            to_equipment="V-101", to_nozzle="inlet",
            diameter_mm=50.0,
        )
        pipe2 = Pipe(
            tag="2\"-PR-002",
            from_equipment="V-101", from_nozzle="outlet",
            to_equipment="E-101", to_nozzle="shell_inlet",
            diameter_mm=50.0,
        )
        diag.add_pipe(pipe1)
        diag.add_pipe(pipe2)
        return diag

    def test_diagram_component_count(self):
        d = self._make_simple_diagram()
        assert len(d.components) == 3

    def test_diagram_pipe_count(self):
        d = self._make_simple_diagram()
        assert len(d.pipes) == 2

    def test_get_component(self):
        d = self._make_simple_diagram()
        c = d.get_component("P-101")
        assert isinstance(c, Pump)

    def test_duplicate_tag_raises(self):
        d = PIDDiagram()
        d.add_component(Pump("P-101"))
        with pytest.raises(ValueError, match="already exists"):
            d.add_component(Pump("P-101"))

    def test_pipe_missing_equipment_raises(self):
        d = PIDDiagram()
        d.add_component(Pump("P-101"))
        pipe = Pipe(
            from_equipment="P-101", from_nozzle="discharge",
            to_equipment="V-999", to_nozzle="inlet",
        )
        with pytest.raises(ValueError, match="not found"):
            d.add_pipe(pipe)

    def test_nozzle_marked_connected(self):
        d = self._make_simple_diagram()
        # The pump discharge nozzle should be marked as connected
        pump = d.get_component("P-101")
        assert pump.nozzles["discharge"].connected_to is not None

    def test_connected_pipes(self):
        d = self._make_simple_diagram()
        pipes = d.connected_pipes("V-101")
        assert len(pipes) == 2  # pipe1 → vessel + vessel → pipe2

    def test_summary_keys(self):
        d = self._make_simple_diagram()
        s = d.summary()
        assert "name" in s
        assert "component_count" in s
        assert "pipe_count" in s
        assert s["component_count"] == 3
        assert s["pipe_count"] == 2


# ===========================================================================
# isometric.py — routing tests
# ===========================================================================

class TestRouteOrthogonal:
    def test_same_point_empty(self):
        segs = route_orthogonal(ORIGIN, ORIGIN)
        assert segs == []

    def test_single_axis_z(self):
        """Vertical run — one segment, no elbows."""
        segs = route_orthogonal(Point3(0, 0, 0), Point3(0, 0, 5))
        assert len(segs) == 1
        fc = count_fittings(segs)
        assert fc.elbows_90 == 0

    def test_single_axis_x(self):
        """Horizontal run in X — one segment."""
        segs = route_orthogonal(Point3(0, 0, 0), Point3(10, 0, 0), prefer_axis="X")
        assert len(segs) == 1
        assert count_fittings(segs).elbows_90 == 0

    def test_two_axis_one_elbow(self):
        """L-shaped run: Z then X → 2 segments, 1 elbow."""
        segs = route_orthogonal(Point3(0, 0, 0), Point3(5, 0, 3), prefer_axis="Z")
        assert len(segs) == 2
        fc = count_fittings(segs)
        assert fc.elbows_90 == 1

    def test_three_axis_two_elbows(self):
        """General 3D offset: Z + X + Y → 3 segments, 2 elbows."""
        segs = route_orthogonal(Point3(0, 0, 0), Point3(5, 4, 3), prefer_axis="Z")
        assert len(segs) == 3
        fc = count_fittings(segs)
        assert fc.elbows_90 == 2

    def test_continuity(self):
        """Each segment's end must equal the next segment's start."""
        segs = route_orthogonal(Point3(1, 2, 3), Point3(8, 6, 9))
        for i in range(len(segs) - 1):
            end_i = segs[i].end
            start_next = segs[i + 1].start
            assert end_i.distance_to(start_next) < 1e-9, \
                f"Segment {i} end ≠ segment {i+1} start"

    def test_last_segment_ends_at_destination(self):
        dest = Point3(7.0, 3.0, 2.0)
        segs = route_orthogonal(ORIGIN, dest)
        if segs:
            assert segs[-1].end.distance_to(dest) < 1e-9

    def test_first_segment_starts_at_source(self):
        src = Point3(1.0, 2.0, 3.0)
        dest = Point3(5.0, 8.0, 0.0)
        segs = route_orthogonal(src, dest)
        if segs:
            assert segs[0].start.distance_to(src) < 1e-9

    def test_pipe_length_positive(self):
        segs = route_orthogonal(ORIGIN, Point3(3, 4, 5))
        assert pipe_length(segs) > 0.0

    def test_segment_directions_are_axis_aligned(self):
        """Each segment must be axis-aligned (only one non-zero direction component)."""
        segs = route_orthogonal(Point3(0, 0, 0), Point3(5, 3, 7))
        for seg in segs:
            d = seg.direction
            nonzero = sum(1 for v in d if abs(v) > 1e-9)
            assert nonzero == 1, f"Segment direction {d} is not axis-aligned"


class TestRouteLoop:
    """3-component loop (pump → vessel → HX) — the DoD reference case."""

    def _make_loop_waypoints(self):
        """
        Pump discharge at (0,0,1), vessel inlet at (5,0,4),
        vessel outlet at (5,0,0), HX shell_inlet at (10,0,2).
        Two legs:
          leg 0: pump_discharge → vessel_inlet
          leg 1: vessel_outlet  → hx_shell_inlet
        """
        return [
            Point3(0.0, 0.0, 1.0),   # pump discharge
            Point3(5.0, 0.0, 4.0),   # vessel inlet
        ], [
            Point3(5.0, 0.0, 0.0),   # vessel outlet
            Point3(10.0, 0.0, 2.0),  # HX shell inlet
        ]

    def test_3_component_loop_routes(self):
        """DoD: 3-component loop routes without error."""
        wps_a, wps_b = self._make_loop_waypoints()
        legs_a = route_loop(wps_a)
        legs_b = route_loop(wps_b)
        assert len(legs_a) == 1
        assert len(legs_b) == 1
        all_legs = legs_a + legs_b
        summary = summarise_route(all_legs)
        # Each L-shaped leg produces exactly 1 elbow (Z then X)
        assert summary.total_elbows_90 == 2, (
            f"Expected 2 elbows (one per L-shaped leg), got {summary.total_elbows_90}"
        )

    def test_3_component_loop_elbow_count_detail(self):
        """
        Detailed check: pump(0,0,1) → vessel(5,0,4).
        Offset: (5,0,3) → Z first (3 units), then X (5 units) = 2 segments, 1 elbow.
        """
        segs = route_orthogonal(
            Point3(0.0, 0.0, 1.0),
            Point3(5.0, 0.0, 4.0),
            prefer_axis="Z",
        )
        fc = count_fittings(segs)
        assert fc.elbows_90 == 1, f"Expected 1 elbow, got {fc.elbows_90}"

    def test_loop_requires_2_waypoints(self):
        with pytest.raises(ValueError, match="at least 2"):
            route_loop([Point3(0, 0, 0)])

    def test_summarise_route_keys(self):
        wps = [Point3(0, 0, 0), Point3(3, 0, 4), Point3(10, 5, 4)]
        legs = route_loop(wps)
        s = summarise_route(legs)
        d = s.as_dict()
        assert "total_elbows_90" in d
        assert "total_pipe_length" in d
        assert "legs" in d
        assert d["legs"] == 2


class TestPipeLength:
    def test_straight_run(self):
        """Straight Z run of 10 units → pipe_length = 10."""
        segs = route_orthogonal(ORIGIN, Point3(0, 0, 10.0))
        assert pipe_length(segs) == pytest.approx(10.0)

    def test_right_angle_run(self):
        """Z=3 then X=4 → pipe_length = 7.0 (elbow not counted as length)."""
        segs = route_orthogonal(ORIGIN, Point3(4.0, 0.0, 3.0), prefer_axis="Z")
        assert pipe_length(segs) == pytest.approx(7.0)


# ===========================================================================
# symbols.py — SVG export tests
# ===========================================================================

class TestPidDiagramSvg:
    def _make_simple_diagram(self) -> PIDDiagram:
        diag = PIDDiagram("P&ID-TEST")
        diag.add_component(Pump("P-101"))
        diag.add_component(Vessel("V-101"))
        diag.add_component(HeatExchanger("E-101"))
        diag.add_pipe(Pipe(
            tag="L-001",
            from_equipment="P-101", from_nozzle="discharge",
            to_equipment="V-101", to_nozzle="inlet",
        ))
        diag.add_pipe(Pipe(
            tag="L-002",
            from_equipment="V-101", from_nozzle="outlet",
            to_equipment="E-101", to_nozzle="shell_inlet",
        ))
        return diag

    def test_svg_is_string(self):
        diag = self._make_simple_diagram()
        svg = pid_diagram_svg(diag)
        assert isinstance(svg, str)

    def test_svg_starts_with_tag(self):
        """SVG must start with an <svg> element."""
        diag = self._make_simple_diagram()
        svg = pid_diagram_svg(diag)
        assert svg.strip().startswith("<svg"), "SVG output does not start with <svg>"

    def test_svg_closes_tag(self):
        diag = self._make_simple_diagram()
        svg = pid_diagram_svg(diag)
        assert "</svg>" in svg

    def test_svg_contains_component_tags(self):
        diag = self._make_simple_diagram()
        svg = pid_diagram_svg(diag)
        assert "P-101" in svg
        assert "V-101" in svg
        assert "E-101" in svg

    def test_svg_contains_title(self):
        diag = self._make_simple_diagram()
        svg = pid_diagram_svg(diag, title="MY_TITLE")
        assert "MY_TITLE" in svg

    def test_svg_custom_dimensions(self):
        diag = self._make_simple_diagram()
        svg = pid_diagram_svg(diag, width=1200, height=600)
        assert 'width="1200"' in svg
        assert 'height="600"' in svg


class TestSymbolFor:
    def test_pump_symbol(self):
        p = Pump("P-101")
        sym = symbol_for(p)
        assert "pump" in sym

    def test_vessel_symbol(self):
        v = Vessel("V-101")
        sym = symbol_for(v)
        assert "vessel" in sym

    def test_hx_symbol(self):
        hx = HeatExchanger("E-101")
        sym = symbol_for(hx)
        assert "hx" in sym

    def test_valve_gate_symbol(self):
        v = Valve("XV-101", valve_type=ValveType.GATE)
        sym = symbol_for(v)
        assert "valve" in sym

    def test_instrument_symbol(self):
        i = Instrument("FT-101")
        sym = symbol_for(i)
        assert sym == "circle"


# ===========================================================================
# tools.py — import_pid round-trip tests
# ===========================================================================

class TestParsePidText:
    """
    DoD: import_pid round-trips a text spec.
    """

    SIMPLE_SPEC = """
# Simple 3-component P&ID
VESSEL V-101 type=drum d=1.2 L=3.0
PUMP P-101 type=centrifugal flow=15.0 head=40.0
HX E-101 type=shell_tube duty=750.0
PIPE L-001 P-101.discharge V-101.inlet dn=50.0 sched=40 fluid=water
PIPE L-002 V-101.outlet E-101.shell_inlet dn=50.0 sched=40 fluid=water
"""

    def test_round_trip_component_count(self):
        diag, warnings = _parse_pid_text(self.SIMPLE_SPEC, "TEST-001")
        assert len(diag.components) == 3, f"Expected 3 components, got {len(diag.components)}"

    def test_round_trip_pipe_count(self):
        diag, warnings = _parse_pid_text(self.SIMPLE_SPEC, "TEST-001")
        assert len(diag.pipes) == 2, f"Expected 2 pipes, got {len(diag.pipes)}"

    def test_round_trip_no_warnings(self):
        diag, warnings = _parse_pid_text(self.SIMPLE_SPEC, "TEST-001")
        assert warnings == [], f"Unexpected warnings: {warnings}"

    def test_round_trip_vessel_params(self):
        diag, _ = _parse_pid_text(self.SIMPLE_SPEC, "TEST")
        v = diag.get_component("V-101")
        assert isinstance(v, Vessel)
        assert v.vessel_type == "drum"
        assert v.diameter_m == pytest.approx(1.2)
        assert v.length_m == pytest.approx(3.0)

    def test_round_trip_pump_params(self):
        diag, _ = _parse_pid_text(self.SIMPLE_SPEC, "TEST")
        p = diag.get_component("P-101")
        assert isinstance(p, Pump)
        assert p.flow_m3h == pytest.approx(15.0)
        assert p.head_m == pytest.approx(40.0)

    def test_round_trip_hx_params(self):
        diag, _ = _parse_pid_text(self.SIMPLE_SPEC, "TEST")
        hx = diag.get_component("E-101")
        assert isinstance(hx, HeatExchanger)
        assert hx.duty_kw == pytest.approx(750.0)

    def test_round_trip_pipe_diameter(self):
        diag, _ = _parse_pid_text(self.SIMPLE_SPEC, "TEST")
        for pipe in diag.pipes.values():
            assert pipe.diameter_mm == pytest.approx(50.0)

    def test_round_trip_pipe_fluid(self):
        diag, _ = _parse_pid_text(self.SIMPLE_SPEC, "TEST")
        for pipe in diag.pipes.values():
            assert pipe.fluid == "water"

    def test_blank_lines_and_comments_ignored(self):
        spec = "\n# comment\n\nVESSEL V-200\n"
        diag, warnings = _parse_pid_text(spec, "TEST")
        assert len(diag.components) == 1

    def test_unknown_directive_warning(self):
        spec = "UNKNOWN_THING foo bar\nVESSEL V-300\n"
        diag, warnings = _parse_pid_text(spec, "TEST")
        assert any("Unknown directive" in w for w in warnings)

    def test_valve_parse(self):
        spec = "VALVE XV-101 type=ball dn=80\n"
        diag, warnings = _parse_pid_text(spec, "TEST")
        assert len(diag.components) == 1
        v = diag.get_component("XV-101")
        assert isinstance(v, Valve)
        assert v.valve_type == ValveType.BALL

    def test_instrument_parse(self):
        spec = "INSTRUMENT FT-201\n"
        diag, warnings = _parse_pid_text(spec, "TEST")
        i = diag.get_component("FT-201")
        assert isinstance(i, Instrument)

    def test_summary_roundtrip(self):
        """summary() of a parsed diagram has correct counts."""
        diag, _ = _parse_pid_text(self.SIMPLE_SPEC, "P&ID-001")
        s = diag.summary()
        assert s["component_count"] == 3
        assert s["pipe_count"] == 2


# ===========================================================================
# tools.py — async tool tests
# ===========================================================================

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class FakeCtx:
    pass


class TestRouteIsometricTool:
    def test_basic_route(self):
        from kerf_piping.tools import run_piping_route_isometric
        args = {
            "start": [0.0, 0.0, 0.0],
            "end": [5.0, 0.0, 3.0],
            "diameter_mm": 50.0,
            "schedule": "40",
            "prefer_axis": "Z",
        }
        result = _run(run_piping_route_isometric(args, FakeCtx()))
        data = json.loads(result)
        assert "elbows_90" in data
        assert data["elbows_90"] == 1
        assert "total_pipe_length_m" in data

    def test_straight_route(self):
        from kerf_piping.tools import run_piping_route_isometric
        args = {"start": [0.0, 0.0, 0.0], "end": [0.0, 0.0, 10.0]}
        result = _run(run_piping_route_isometric(args, FakeCtx()))
        data = json.loads(result)
        assert data["elbows_90"] == 0
        assert data["total_pipe_length_m"] == pytest.approx(10.0)

    def test_tool_returns_segments(self):
        from kerf_piping.tools import run_piping_route_isometric
        args = {"start": [0.0, 0.0, 0.0], "end": [3.0, 4.0, 5.0]}
        result = _run(run_piping_route_isometric(args, FakeCtx()))
        data = json.loads(result)
        assert "segments" in data
        assert len(data["segments"]) > 0


class TestImportPidTool:
    SPEC = """
VESSEL V-101 type=drum
PUMP P-101 type=centrifugal flow=10.0
HX E-101 type=shell_tube duty=500.0
PIPE L-001 P-101.discharge V-101.inlet dn=50.0
PIPE L-002 V-101.outlet E-101.shell_inlet dn=50.0
"""

    def test_import_pid_basic(self):
        from kerf_piping.tools import run_piping_import_pid
        args = {"text": self.SPEC, "diagram_name": "TEST-001"}
        result = _run(run_piping_import_pid(args, FakeCtx()))
        data = json.loads(result)
        assert "diagram" in data
        assert data["diagram"]["component_count"] == 3
        assert data["diagram"]["pipe_count"] == 2

    def test_import_pid_no_warnings(self):
        from kerf_piping.tools import run_piping_import_pid
        args = {"text": self.SPEC}
        result = _run(run_piping_import_pid(args, FakeCtx()))
        data = json.loads(result)
        assert data["warnings"] == []

    def test_import_pid_round_trip_summary(self):
        """summary keys match expected structure."""
        from kerf_piping.tools import run_piping_import_pid
        args = {"text": self.SPEC, "diagram_name": "P&ID-ROUNDTRIP"}
        result = _run(run_piping_import_pid(args, FakeCtx()))
        data = json.loads(result)
        diag_summary = data["diagram"]
        assert diag_summary["name"] == "P&ID-ROUNDTRIP"
        assert "components" in diag_summary
        tags = [c["tag"] for c in diag_summary["components"]]
        assert "V-101" in tags
        assert "P-101" in tags
        assert "E-101" in tags


class TestExportSvgTool:
    SPEC = """
VESSEL V-101
PUMP P-101
HX E-101
PIPE L-001 P-101.discharge V-101.inlet dn=50
PIPE L-002 V-101.outlet E-101.shell_inlet dn=50
"""

    def test_export_svg_basic(self):
        from kerf_piping.tools import run_piping_export_svg
        args = {"text": self.SPEC, "diagram_name": "P&ID-SVG-001"}
        result = _run(run_piping_export_svg(args, FakeCtx()))
        data = json.loads(result)
        assert "svg" in data
        assert data["svg"].strip().startswith("<svg")
        assert "</svg>" in data["svg"]
        assert data["component_count"] == 3
        assert data["pipe_count"] == 2


# ===========================================================================
# Module compile smoke tests
# ===========================================================================

class TestModuleImports:
    def test_pid_imports(self):
        import kerf_piping.pid  # noqa: F401

    def test_isometric_imports(self):
        import kerf_piping.isometric  # noqa: F401

    def test_symbols_imports(self):
        import kerf_piping.symbols  # noqa: F401

    def test_tools_imports(self):
        import kerf_piping.tools  # noqa: F401

    def test_plugin_imports(self):
        import kerf_piping.plugin  # noqa: F401

    def test_pycompile_pid(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_piping", "pid.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_isometric(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_piping", "isometric.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_symbols(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_piping", "symbols.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_tools(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_piping", "tools.py")
        py_compile.compile(path, doraise=True)
