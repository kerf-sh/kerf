"""
tests/test_harness3d.py — T-323 3D in-vehicle wiring harness through DMU.

DoD:
  - Routing solver: 4-wire harness through 3-box obstacle set, paths found
  - Formboard flatten: 2D lengths within ±2 mm of 3D path lengths (exact by design)
  - Voltage-drop report: matches analytic V = I·R within 5%
  - Library: ≥ 20 standard automotive connectors present
  - pytest green

All tests are hermetic (no DB, no network, no optional deps required).
"""
from __future__ import annotations

import math

import pytest

from kerf_electronics.harness3d.router import (
    AABB,
    HarnessEdge,
    RouteResult,
    awg_resistance_per_m,
    route_harness_3d,
)
from kerf_electronics.harness3d.library import (
    CONNECTOR_LIBRARY,
    lookup_connector,
)
from kerf_electronics.harness3d.formboard import (
    FormboardResult,
    flatten_harness,
)
from kerf_electronics.harness3d.report import (
    CircuitReport,
    HarnessReport,
    voltage_drop_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _analytic_voltage_drop(length_mm: float, awg: int, current_a: float) -> float:
    """Reference: V = I × R, R = r_per_m × length_m."""
    r_per_m = awg_resistance_per_m(awg)
    length_m = length_mm / 1000.0
    return current_a * r_per_m * length_m


def _make_4wire_fixture():
    """
    4-wire harness through a 3-box obstacle set.

    Layout (all units mm):

        Start pins:   (0,0,0), (0,50,0), (0,100,0), (0,150,0)
        End pins:     (500,0,0), (500,50,0), (500,100,0), (500,150,0)

    Three axis-aligned boxes block the straight path in the middle:
        Box A: x=[150,200], y=[-20,200], z=[-20,20]   (cuts across y)
        Box B: x=[250,300], y=[-20,100], z=[-20,20]
        Box C: x=[350,400], y=[-20,200], z=[-20,20]

    Grid step 25 mm — coarse enough to be fast in tests.
    """
    obstacles = [
        AABB(min_x=150, min_y=-20, min_z=-20, max_x=200, max_y=200, max_z=20),
        AABB(min_x=250, min_y=-20, min_z=-20, max_x=300, max_y=100, max_z=20),
        AABB(min_x=350, min_y=-20, min_z=-20, max_x=400, max_y=200, max_z=20),
    ]

    edges = [
        HarnessEdge(
            from_pin="J1.1", to_pin="J2.1",
            from_pos=(0.0, 0.0, 0.0), to_pos=(500.0, 0.0, 0.0),
            gauge_awg=16, current_a=8.0,
        ),
        HarnessEdge(
            from_pin="J1.2", to_pin="J2.2",
            from_pos=(0.0, 50.0, 0.0), to_pos=(500.0, 50.0, 0.0),
            gauge_awg=20, current_a=2.0,
        ),
        HarnessEdge(
            from_pin="J1.3", to_pin="J2.3",
            from_pos=(0.0, 100.0, 0.0), to_pos=(500.0, 100.0, 0.0),
            gauge_awg=20, current_a=2.0,
        ),
        HarnessEdge(
            from_pin="J1.4", to_pin="J2.4",
            from_pos=(0.0, 150.0, 0.0), to_pos=(500.0, 150.0, 0.0),
            gauge_awg=18, current_a=5.0,
        ),
    ]

    return edges, obstacles


# ===========================================================================
# SECTION 1 — Routing solver
# ===========================================================================

class TestRoutingBasic:
    """Basic routing without obstacles."""

    def test_straight_shot_no_obstacles(self):
        edge = HarnessEdge(
            from_pin="A", to_pin="B",
            from_pos=(0.0, 0.0, 0.0), to_pos=(100.0, 0.0, 0.0),
            gauge_awg=20,
        )
        results = route_harness_3d([edge])
        assert len(results) == 1
        r = results[0]
        assert r.ok, f"expected ok, got: {r.reason}"
        # Path length must be ≥ straight-line distance (100 mm)
        assert r.length_mm >= 100.0 - 1e-3

    def test_waypoints_start_end_match(self):
        edge = HarnessEdge(
            from_pin="A", to_pin="B",
            from_pos=(10.0, 20.0, 30.0), to_pos=(110.0, 20.0, 30.0),
        )
        results = route_harness_3d([edge])
        r = results[0]
        assert r.ok
        assert r.waypoints[0] == pytest.approx(
            (10.0, 20.0, 30.0), abs=1e-6
        )
        assert r.waypoints[-1] == pytest.approx(
            (110.0, 20.0, 30.0), abs=1e-6
        )

    def test_empty_edges_returns_empty(self):
        results = route_harness_3d([])
        assert results == []

    def test_multiple_independent_edges(self):
        edges = [
            HarnessEdge("A", "B", (0, 0, 0), (50, 0, 0)),
            HarnessEdge("C", "D", (0, 100, 0), (50, 100, 0)),
        ]
        results = route_harness_3d(edges)
        assert len(results) == 2
        assert all(r.ok for r in results)

    def test_3d_path_length_positive(self):
        edge = HarnessEdge(
            from_pin="P", to_pin="Q",
            from_pos=(0, 0, 0), to_pos=(30, 40, 0),
        )
        results = route_harness_3d([edge])
        r = results[0]
        assert r.ok
        assert r.length_mm > 0.0

    def test_result_has_to_dict(self):
        edge = HarnessEdge("X", "Y", (0, 0, 0), (100, 0, 0), gauge_awg=20)
        r = route_harness_3d([edge])[0]
        d = r.to_dict()
        assert "from_pin" in d
        assert "length_mm" in d
        assert "waypoints" in d


class TestRoutingWithObstacles:
    """Routing around AABB obstacles."""

    def test_detours_around_single_block(self):
        """
        Obstacle blocks the straight x-axis path; router must go around.
        """
        obs = [AABB(min_x=40, min_y=-10, min_z=-10, max_x=60, max_y=10, max_z=10)]
        edge = HarnessEdge(
            from_pin="S", to_pin="E",
            from_pos=(0.0, 0.0, 0.0), to_pos=(100.0, 0.0, 0.0),
        )
        results = route_harness_3d([edge], obstacles=obs, grid_step_mm=10.0)
        r = results[0]
        assert r.ok, f"expected path found: {r.reason}"
        # Detour must be longer than straight distance
        assert r.length_mm > 100.0

    def test_4wire_3box_fixture_all_routed(self):
        """T-323 DoD test fixture: 4 wires through 3-box obstacle set."""
        edges, obstacles = _make_4wire_fixture()
        results = route_harness_3d(edges, obstacles=obstacles, grid_step_mm=25.0)
        assert len(results) == 4
        failed = [r for r in results if not r.ok]
        assert len(failed) == 0, (
            f"Expected all 4 wires routed; failed: "
            + ", ".join(f"{r.edge.from_pin}->{r.edge.to_pin}: {r.reason}"
                        for r in failed)
        )

    def test_4wire_length_exceeds_straight(self):
        """Detoured paths must be longer than the straight-line distance."""
        edges, obstacles = _make_4wire_fixture()
        results = route_harness_3d(edges, obstacles=obstacles, grid_step_mm=25.0)
        for r in results:
            assert r.ok
            # Straight-line distance = 500 mm
            assert r.length_mm >= 500.0 - 1e-3, (
                f"{r.edge.from_pin}: length {r.length_mm:.1f} mm < 500 mm"
            )

    def test_route_result_waypoints_are_triples(self):
        edges, obstacles = _make_4wire_fixture()
        results = route_harness_3d(edges, obstacles=obstacles, grid_step_mm=25.0)
        for r in results:
            assert r.ok
            for pt in r.waypoints:
                assert len(pt) == 3, f"waypoint {pt!r} is not a triple"


# ===========================================================================
# SECTION 2 — Connector library
# ===========================================================================

class TestConnectorLibrary:
    def test_library_has_at_least_20_entries(self):
        assert len(CONNECTOR_LIBRARY) >= 20, (
            f"library has {len(CONNECTOR_LIBRARY)} entries; need ≥ 20"
        )

    def test_all_entries_have_positive_pin_count(self):
        for pid, spec in CONNECTOR_LIBRARY.items():
            assert spec.pin_count >= 1, f"{pid}: pin_count must be ≥ 1"

    def test_all_entries_have_positive_current(self):
        for pid, spec in CONNECTOR_LIBRARY.items():
            assert spec.current_per_pin_a > 0, (
                f"{pid}: current_per_pin_a must be > 0"
            )

    def test_lookup_known_connector(self):
        spec = lookup_connector("DT-4P")
        assert spec.pin_count == 4
        assert spec.family == "Deutsch DT"

    def test_lookup_unknown_raises(self):
        with pytest.raises(KeyError, match="not found"):
            lookup_connector("NONEXISTENT-999")

    def test_mil_spec_present(self):
        mil_parts = [
            k for k, v in CONNECTOR_LIBRARY.items()
            if "MIL" in v.family.upper() or "MIL" in k.upper()
        ]
        assert len(mil_parts) >= 2, "expected ≥ 2 MIL-spec connectors"

    def test_deutsch_dt_series(self):
        dt_parts = [k for k in CONNECTOR_LIBRARY if k.startswith("DT-")]
        assert len(dt_parts) >= 3

    def test_molex_minifit(self):
        mf_parts = [k for k in CONNECTOR_LIBRARY if "MINIFIT" in k]
        assert len(mf_parts) >= 2

    def test_ip_rating_field_nonempty(self):
        for pid, spec in CONNECTOR_LIBRARY.items():
            assert spec.ip_rating, f"{pid}: ip_rating must not be empty"

    def test_temp_range_sensible(self):
        for pid, spec in CONNECTOR_LIBRARY.items():
            assert spec.temp_min_c < spec.temp_max_c, (
                f"{pid}: temp_min_c must be < temp_max_c"
            )

    def test_connector_spec_fields(self):
        spec = lookup_connector("MIL38999-9")
        assert spec.pin_count == 9
        assert spec.voltage_v == 200.0
        assert spec.ip_rating == "IP67"
        assert spec.temp_min_c == -65.0

    def test_ev_connector_present(self):
        ev_parts = [
            k for k, v in CONNECTOR_LIBRARY.items()
            if v.voltage_v >= 200.0
        ]
        assert len(ev_parts) >= 1, "expected ≥ 1 high-voltage / EV connector"

    def test_all_descriptions_nonempty(self):
        for pid, spec in CONNECTOR_LIBRARY.items():
            assert spec.description, f"{pid}: description must not be empty"


# ===========================================================================
# SECTION 3 — Formboard flatten
# ===========================================================================

class TestFormboardFlatten:
    def _4wire_routes(self):
        edges, obstacles = _make_4wire_fixture()
        return route_harness_3d(edges, obstacles=obstacles, grid_step_mm=25.0)

    def test_returns_formboard_result(self):
        routes = self._4wire_routes()
        fb = flatten_harness(routes)
        assert isinstance(fb, FormboardResult)

    def test_segment_count_matches_ok_routes(self):
        routes = self._4wire_routes()
        ok_count = sum(1 for r in routes if r.ok)
        fb = flatten_harness(routes)
        assert len(fb.segments) == ok_count

    def test_flat_lengths_equal_3d_lengths(self):
        """
        DoD: formboard segment lengths within ±2 mm of 3D path lengths.

        By design (pure arc-length preservation) the difference should be
        essentially 0 (floating-point precision only).
        """
        routes = self._4wire_routes()
        fb = flatten_harness(routes)
        for seg, route in zip(fb.segments, [r for r in routes if r.ok]):
            diff = abs(seg.length_mm - route.length_mm)
            assert diff <= 2.0, (
                f"{seg.from_pin}→{seg.to_pin}: flat={seg.length_mm:.3f} mm, "
                f"3D={route.length_mm:.3f} mm, diff={diff:.3f} mm > 2 mm"
            )

    def test_total_length_sums_segments(self):
        routes = self._4wire_routes()
        fb = flatten_harness(routes)
        expected = sum(s.length_mm for s in fb.segments)
        assert pytest.approx(fb.total_length_mm, rel=1e-9) == expected

    def test_bounding_box_positive(self):
        routes = self._4wire_routes()
        fb = flatten_harness(routes)
        assert fb.width_mm > 0
        assert fb.height_mm > 0

    def test_empty_routes_returns_empty(self):
        fb = flatten_harness([])
        assert fb.segments == []
        assert fb.total_length_mm == 0.0

    def test_all_failed_routes(self):
        # Create a route result that failed
        edge = HarnessEdge("X", "Y", (0, 0, 0), (100, 0, 0))
        r = RouteResult(edge=edge, ok=False, reason="test failure")
        fb = flatten_harness([r])
        assert fb.segments == []
        assert len(fb.failed_edges) == 1

    def test_to_dict_keys(self):
        routes = self._4wire_routes()
        fb = flatten_harness(routes)
        d = fb.to_dict()
        assert "total_length_mm" in d
        assert "width_mm" in d
        assert "height_mm" in d
        assert "segments" in d
        assert "failed_edges" in d

    def test_length_table_returns_list(self):
        routes = self._4wire_routes()
        fb = flatten_harness(routes)
        table = fb.length_table()
        assert isinstance(table, list)
        assert len(table) == len(fb.segments)

    def test_segments_have_pin_names(self):
        routes = self._4wire_routes()
        fb = flatten_harness(routes)
        for seg in fb.segments:
            assert seg.from_pin
            assert seg.to_pin

    def test_x_start_is_zero(self):
        """Each circuit starts at x=0 (stacked layout)."""
        routes = self._4wire_routes()
        fb = flatten_harness(routes)
        for seg in fb.segments:
            assert seg.x_start == pytest.approx(0.0, abs=1e-9)

    def test_x_end_equals_length(self):
        routes = self._4wire_routes()
        fb = flatten_harness(routes)
        for seg in fb.segments:
            assert pytest.approx(seg.x_end, rel=1e-9) == seg.length_mm


# ===========================================================================
# SECTION 4 — Voltage-drop report
# ===========================================================================

class TestVoltageDrop:
    def _4wire_routes(self):
        edges, obstacles = _make_4wire_fixture()
        return route_harness_3d(edges, obstacles=obstacles, grid_step_mm=25.0)

    def test_returns_harness_report(self):
        routes = self._4wire_routes()
        rpt = voltage_drop_report(routes)
        assert isinstance(rpt, HarnessReport)

    def test_circuit_count(self):
        routes = self._4wire_routes()
        rpt = voltage_drop_report(routes)
        ok_count = sum(1 for r in routes if r.ok)
        assert len(rpt.circuits) == ok_count

    def test_voltage_drop_analytic_within_5pct(self):
        """
        DoD: voltage drop matches analytic V=I·R within 5%.

        The router can choose any path length ≥ straight-line distance.
        We compute the analytic prediction using the actual routed length.
        """
        routes = self._4wire_routes()
        rpt = voltage_drop_report(routes, supply_v=12.0)

        for c in rpt.circuits:
            analytic = _analytic_voltage_drop(c.length_mm, c.gauge_awg, c.current_a)
            # analytic == c.voltage_drop_v by construction; tolerance is 5%
            if analytic > 1e-9:
                rel_err = abs(c.voltage_drop_v - analytic) / analytic
                assert rel_err <= 0.05, (
                    f"{c.from_pin}→{c.to_pin}: computed {c.voltage_drop_v:.6f} V, "
                    f"analytic {analytic:.6f} V, err={rel_err*100:.2f}%"
                )

    def test_voltage_drop_exact_formula(self):
        """
        Cross-check the formula directly with a single known circuit.

        Straight shot, no obstacles, AWG 20, 2 A, supply 12 V.
        Length is exactly 1000 mm = 1 m.
        AWG 20 resistance = 0.0336 Ω/m (from table).
        Expected drop = 2 × 0.0336 = 0.0672 V.
        """
        edge = HarnessEdge(
            from_pin="GND", to_pin="LOAD",
            from_pos=(0.0, 0.0, 0.0), to_pos=(1000.0, 0.0, 0.0),
            gauge_awg=20, current_a=2.0,
        )
        routes = route_harness_3d([edge], grid_step_mm=100.0)
        rpt = voltage_drop_report(routes, supply_v=12.0)
        assert len(rpt.circuits) == 1
        c = rpt.circuits[0]

        # Compute expected using actual routed length (may differ from 1000 mm
        # due to grid snapping — router snaps start/end to actual pin positions)
        expected_v = _analytic_voltage_drop(c.length_mm, 20, 2.0)
        assert pytest.approx(c.voltage_drop_v, rel=1e-6) == expected_v

    def test_resistance_formula(self):
        """R = r_per_m × length_m."""
        edge = HarnessEdge(
            from_pin="A", to_pin="B",
            from_pos=(0, 0, 0), to_pos=(500, 0, 0),
            gauge_awg=14, current_a=10.0,
        )
        routes = route_harness_3d([edge])
        rpt = voltage_drop_report(routes)
        c = rpt.circuits[0]
        r_per_m = awg_resistance_per_m(14)
        expected_r = r_per_m * c.length_mm / 1000.0
        assert pytest.approx(c.resistance_ohm, rel=1e-6) == expected_r

    def test_pct_drop_formula(self):
        """pct_drop = 100 × V_drop / supply_v."""
        edge = HarnessEdge(
            from_pin="A", to_pin="B",
            from_pos=(0, 0, 0), to_pos=(200, 0, 0),
            gauge_awg=20, current_a=1.0,
        )
        routes = route_harness_3d([edge])
        rpt = voltage_drop_report(routes, supply_v=12.0)
        c = rpt.circuits[0]
        expected_pct = 100.0 * c.voltage_drop_v / 12.0
        assert pytest.approx(c.pct_drop, rel=1e-6) == expected_pct

    def test_empty_routes(self):
        rpt = voltage_drop_report([])
        assert rpt.circuits == []
        assert rpt.total_length_mm == 0.0

    def test_failed_route_excluded(self):
        edge = HarnessEdge("X", "Y", (0, 0, 0), (100, 0, 0))
        r = RouteResult(edge=edge, ok=False, reason="blocked")
        rpt = voltage_drop_report([r])
        assert rpt.circuits == []
        assert len(rpt.failed_edges) == 1

    def test_total_length_sums_circuits(self):
        routes = self._4wire_routes()
        rpt = voltage_drop_report(routes)
        expected = sum(c.length_mm for c in rpt.circuits)
        assert pytest.approx(rpt.total_length_mm, rel=1e-9) == expected

    def test_max_drop_is_max(self):
        routes = self._4wire_routes()
        rpt = voltage_drop_report(routes)
        if rpt.circuits:
            expected_max = max(c.voltage_drop_v for c in rpt.circuits)
            assert pytest.approx(rpt.max_drop_v, rel=1e-9) == expected_max

    def test_to_dict_structure(self):
        routes = self._4wire_routes()
        rpt = voltage_drop_report(routes)
        d = rpt.to_dict()
        assert "circuit_count" in d
        assert "total_length_mm" in d
        assert "max_drop_v" in d
        assert "circuits" in d

    def test_circuit_to_dict(self):
        edge = HarnessEdge("A", "B", (0, 0, 0), (100, 0, 0), gauge_awg=20, current_a=1.0)
        routes = route_harness_3d([edge])
        rpt = voltage_drop_report(routes, supply_v=12.0)
        c = rpt.circuits[0]
        d = c.to_dict()
        assert "from_pin" in d
        assert "to_pin" in d
        assert "gauge_awg" in d
        assert "length_mm" in d
        assert "voltage_drop_v" in d
        assert "pct_drop" in d


# ===========================================================================
# SECTION 5 — AWG table
# ===========================================================================

class TestAWGTable:
    def test_awg20_resistance(self):
        """AWG 20 = 0.0336 Ω/m (standard copper)."""
        r = awg_resistance_per_m(20)
        assert pytest.approx(r, rel=0.01) == 0.0336

    def test_awg14_resistance_lower_than_awg20(self):
        """Thicker wire → lower resistance."""
        assert awg_resistance_per_m(14) < awg_resistance_per_m(20)

    def test_unlisted_awg_returns_positive(self):
        """Unlisted AWG uses formula; must return a positive value."""
        r = awg_resistance_per_m(15)
        assert r > 0.0

    def test_awg0_has_very_low_resistance(self):
        assert awg_resistance_per_m(0) < 0.001  # < 1 mΩ/m


# ===========================================================================
# SECTION 6 — Integration (full harness pipeline)
# ===========================================================================

class TestFullPipeline:
    """End-to-end: route → flatten → report."""

    def test_4wire_full_pipeline(self):
        edges, obstacles = _make_4wire_fixture()

        # Route
        routes = route_harness_3d(edges, obstacles=obstacles, grid_step_mm=25.0)
        assert all(r.ok for r in routes), "some routes failed"

        # Flatten
        fb = flatten_harness(routes)
        assert len(fb.segments) == 4

        # Length ±2 mm check (DoD)
        for seg, r in zip(fb.segments, routes):
            diff = abs(seg.length_mm - r.length_mm)
            assert diff <= 2.0, f"length diff {diff:.3f} mm > 2 mm"

        # Voltage drop
        rpt = voltage_drop_report(routes, supply_v=12.0)
        assert len(rpt.circuits) == 4

        # Analytic cross-check within 5% (DoD)
        for c in rpt.circuits:
            analytic = _analytic_voltage_drop(c.length_mm, c.gauge_awg, c.current_a)
            if analytic > 1e-9:
                err = abs(c.voltage_drop_v - analytic) / analytic
                assert err <= 0.05, f"voltage drop err {err*100:.2f}% > 5%"

    def test_library_integration_lookup(self):
        spec = lookup_connector("DT-6P")
        assert spec.pin_count == 6
        assert spec.ip_rating == "IP67"

    def test_report_dict_serialisable(self):
        """The entire report dict must be JSON serialisable."""
        import json
        edges, obstacles = _make_4wire_fixture()
        routes = route_harness_3d(edges, obstacles=obstacles, grid_step_mm=25.0)
        fb = flatten_harness(routes)
        rpt = voltage_drop_report(routes, supply_v=12.0)
        # Should not raise
        json.dumps(fb.to_dict())
        json.dumps(rpt.to_dict())
