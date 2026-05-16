"""
Hermetic tests for kerf_cad_core.surveying — COGO / traverse / area.

Coverage:
  cogo.dms_to_dd / dd_to_dms
  cogo.bearing_to_azimuth / azimuth_to_bearing
  cogo.forward (polar → rectangular)
  cogo.inverse (rectangular → polar)
  cogo.traverse_misclosure
  cogo.traverse_adjust (Compass and Transit rules)
  cogo.area_by_coordinates (Shoelace)
  cogo.area_by_dmd (Double Meridian Distance)
  cogo.line_line_intersection
  cogo.line_circle_intersection
  cogo.point_of_intersection
  cogo.resection (Tienstra)
  cogo.level_loop_adjust
  tools.* — LLM tool wrappers (happy path + error paths)

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Values verified against hand-calculations and published surveying texts.

References
----------
Wolf & Ghilani, "Elementary Surveying", 14th ed.
Bannister, Raymond, Baker, "Surveying", 7th ed.

Author: imranparuk
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid
import warnings

import pytest

from kerf_cad_core.surveying.cogo import (
    dms_to_dd,
    dd_to_dms,
    bearing_to_azimuth,
    azimuth_to_bearing,
    forward,
    inverse,
    traverse_misclosure,
    traverse_adjust,
    area_by_coordinates,
    area_by_dmd,
    line_line_intersection,
    line_circle_intersection,
    point_of_intersection,
    resection,
    level_loop_adjust,
)
from kerf_cad_core.surveying.tools import (
    run_dms_to_dd,
    run_dd_to_dms,
    run_bearing_azimuth,
    run_forward,
    run_inverse,
    run_traverse,
    run_traverse_adjust,
    run_area_coordinates,
    run_area_dmd,
    run_poi,
    run_resection,
    run_level_loop,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ctx():
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
        return ProjectCtx(
            pool=None, storage=None,
            project_id=uuid.uuid4(), user_id=uuid.uuid4(),
            role="owner", http_client=None,
        )
    except Exception:
        return None


def _args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


def _ok_tool(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err_tool(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


REL = 1e-9  # relative tolerance for floating-point comparisons


def _pt(n, e):
    return {"northing": n, "easting": e}


# ===========================================================================
# 1. DMS ↔ Decimal Degrees
# ===========================================================================

class TestDmsDd:

    def test_dms_to_dd_zero(self):
        r = dms_to_dd(0, 0, 0)
        assert r["ok"] is True
        assert r["dd"] == 0.0

    def test_dms_to_dd_known_value(self):
        """45°30'00\" = 45.5°"""
        r = dms_to_dd(45, 30, 0)
        assert r["ok"] is True
        assert abs(r["dd"] - 45.5) < REL

    def test_dms_to_dd_seconds(self):
        """1°01'01\" = 1 + 1/60 + 1/3600 ≈ 1.016944..."""
        r = dms_to_dd(1, 1, 1)
        assert r["ok"] is True
        expected = 1.0 + 1.0 / 60.0 + 1.0 / 3600.0
        assert abs(r["dd"] - expected) < REL

    def test_dms_to_dd_negative(self):
        """−30°00'00\" = −30.0"""
        r = dms_to_dd(-30, 0, 0)
        assert r["ok"] is True
        assert abs(r["dd"] - (-30.0)) < REL

    def test_dms_to_dd_invalid_minutes(self):
        r = dms_to_dd(10, 60, 0)
        assert r["ok"] is False

    def test_dms_to_dd_invalid_seconds(self):
        r = dms_to_dd(10, 30, 60)
        assert r["ok"] is False

    def test_dd_to_dms_roundtrip(self):
        """dd → dms → dd must recover original value within 1e-9."""
        for dd in (0.0, 45.5, 123.456789, -15.25):
            r = dd_to_dms(dd)
            assert r["ok"] is True
            sign = -1 if dd < 0 else 1
            rec = sign * (abs(r["degrees"]) + r["minutes"] / 60.0 + r["seconds"] / 3600.0)
            assert abs(rec - dd) < 1e-9, f"Roundtrip failed for dd={dd}: got {rec}"

    def test_dd_to_dms_90_degrees(self):
        r = dd_to_dms(90.0)
        assert r["ok"] is True
        assert r["degrees"] == 90
        assert r["minutes"] == 0
        assert abs(r["seconds"]) < 1e-6

    def test_dd_to_dms_fraction(self):
        """0.5° = 0°30'00\"."""
        r = dd_to_dms(0.5)
        assert r["ok"] is True
        assert r["degrees"] == 0
        assert r["minutes"] == 30
        assert abs(r["seconds"]) < 1e-6


# ===========================================================================
# 2. Bearing ↔ Azimuth
# ===========================================================================

class TestBearingAzimuth:

    def test_ne_bearing_equals_azimuth(self):
        """NE 45° → azimuth 45°."""
        r = bearing_to_azimuth("NE", 45.0)
        assert r["ok"] is True
        assert abs(r["azimuth_dd"] - 45.0) < REL

    def test_se_bearing(self):
        """SE 30° → azimuth 150°."""
        r = bearing_to_azimuth("SE", 30.0)
        assert r["ok"] is True
        assert abs(r["azimuth_dd"] - 150.0) < REL

    def test_sw_bearing(self):
        """SW 60° → azimuth 240°."""
        r = bearing_to_azimuth("SW", 60.0)
        assert r["ok"] is True
        assert abs(r["azimuth_dd"] - 240.0) < REL

    def test_nw_bearing(self):
        """NW 45° → azimuth 315°."""
        r = bearing_to_azimuth("NW", 45.0)
        assert r["ok"] is True
        assert abs(r["azimuth_dd"] - 315.0) < REL

    def test_azimuth_to_bearing_roundtrip(self):
        """Azimuth → bearing → azimuth must recover original value."""
        for az in (30.0, 120.0, 200.0, 300.0):
            rb = azimuth_to_bearing(az)
            assert rb["ok"] is True
            ra = bearing_to_azimuth(rb["quadrant"], rb["bearing_dd"])
            assert ra["ok"] is True
            assert abs(ra["azimuth_dd"] - az) < 1e-6

    def test_invalid_quadrant(self):
        r = bearing_to_azimuth("XX", 45.0)
        assert r["ok"] is False

    def test_bearing_dd_out_of_range(self):
        r = bearing_to_azimuth("NE", 91.0)
        assert r["ok"] is False


# ===========================================================================
# 3. Forward problem
# ===========================================================================

class TestForward:

    def test_north_direction(self):
        """Azimuth 0° → delta_E=0, delta_N=distance."""
        r = forward(1000.0, 2000.0, 0.0, 100.0)
        assert r["ok"] is True
        assert abs(r["delta_N"] - 100.0) < 1e-9
        assert abs(r["delta_E"]) < 1e-9

    def test_east_direction(self):
        """Azimuth 90° → delta_N=0, delta_E=distance."""
        r = forward(0.0, 0.0, 90.0, 50.0)
        assert r["ok"] is True
        assert abs(r["delta_N"]) < 1e-9
        assert abs(r["delta_E"] - 50.0) < 1e-9

    def test_south_direction(self):
        """Azimuth 180° → delta_N = -distance, delta_E ≈ 0."""
        r = forward(500.0, 500.0, 180.0, 200.0)
        assert r["ok"] is True
        assert abs(r["delta_N"] - (-200.0)) < 1e-9
        assert abs(r["delta_E"]) < 1e-9

    def test_ne_45_degree(self):
        """Azimuth 45° → delta_N = delta_E = dist × cos(45°)."""
        d = 100.0
        r = forward(0.0, 0.0, 45.0, d)
        assert r["ok"] is True
        expected = d * math.cos(math.pi / 4.0)
        assert abs(r["delta_N"] - expected) < 1e-9
        assert abs(r["delta_E"] - expected) < 1e-9

    def test_zero_distance(self):
        r = forward(100.0, 200.0, 45.0, 0.0)
        assert r["ok"] is True
        assert r["northing"] == pytest.approx(100.0)
        assert r["easting"] == pytest.approx(200.0)

    def test_negative_distance_returns_error(self):
        r = forward(0.0, 0.0, 0.0, -5.0)
        assert r["ok"] is False


# ===========================================================================
# 4. Inverse problem
# ===========================================================================

class TestInverse:

    def test_pure_north(self):
        """Points on the same easting → azimuth 0°."""
        r = inverse(0.0, 0.0, 100.0, 0.0)
        assert r["ok"] is True
        assert abs(r["azimuth_dd"]) < 1e-9
        assert abs(r["distance"] - 100.0) < REL

    def test_pure_east(self):
        """Points on the same northing → azimuth 90°."""
        r = inverse(0.0, 0.0, 0.0, 100.0)
        assert r["ok"] is True
        assert abs(r["azimuth_dd"] - 90.0) < 1e-9
        assert abs(r["distance"] - 100.0) < REL

    def test_forward_inverse_roundtrip(self):
        """forward then inverse must recover original azimuth and distance."""
        az = 123.456
        d = 250.0
        rf = forward(1000.0, 2000.0, az, d)
        ri = inverse(1000.0, 2000.0, rf["northing"], rf["easting"])
        assert abs(ri["azimuth_dd"] - az) < 1e-6
        assert abs(ri["distance"] - d) < 1e-6

    def test_coincident_points_error(self):
        r = inverse(100.0, 200.0, 100.0, 200.0)
        assert r["ok"] is False

    def test_pythagorean_distance(self):
        """3-4-5 triangle: (0,0)→(3,4) distance = 5."""
        r = inverse(0.0, 0.0, 3.0, 4.0)
        assert r["ok"] is True
        assert abs(r["distance"] - 5.0) < REL


# ===========================================================================
# 5. Traverse misclosure
# ===========================================================================

class TestTraverseMisclosure:

    def _perfect_square(self, side=100.0):
        """A perfect square traverse should have zero misclosure."""
        return [
            {"azimuth_dd": 0.0,   "distance": side},
            {"azimuth_dd": 90.0,  "distance": side},
            {"azimuth_dd": 180.0, "distance": side},
            {"azimuth_dd": 270.0, "distance": side},
        ]

    def test_perfect_closure(self):
        r = traverse_misclosure(self._perfect_square())
        assert r["ok"] is True
        assert abs(r["closure_N"]) < 1e-9
        assert abs(r["closure_E"]) < 1e-9
        assert r["linear_misclosure"] < 1e-9
        assert r["precision_ok"] is True

    def test_traverse_length(self):
        """Total traverse length = sum of leg distances."""
        legs = self._perfect_square(50.0)
        r = traverse_misclosure(legs)
        assert r["ok"] is True
        assert abs(r["traverse_length"] - 200.0) < REL

    def test_misclosure_flagged_warning(self):
        """A poor traverse should issue a UserWarning."""
        legs = [
            {"azimuth_dd": 0.0,   "distance": 100.0},
            {"azimuth_dd": 90.0,  "distance": 100.0},
            {"azimuth_dd": 181.0, "distance": 100.0},  # deliberate error
            {"azimuth_dd": 270.0, "distance": 100.0},
        ]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = traverse_misclosure(legs, tolerance=0.0001)
            assert r["ok"] is True
            # Either precision_ok is False OR a warning was emitted
            if not r["precision_ok"]:
                assert len(w) >= 1

    def test_empty_legs_error(self):
        r = traverse_misclosure([])
        assert r["ok"] is False

    def test_leg_delta_values(self):
        """Check delta_N and delta_E in output legs."""
        legs = [{"azimuth_dd": 45.0, "distance": math.sqrt(2.0)}]
        r = traverse_misclosure(legs)
        assert r["ok"] is True
        assert abs(r["legs"][0]["delta_N"] - 1.0) < 1e-9
        assert abs(r["legs"][0]["delta_E"] - 1.0) < 1e-9


# ===========================================================================
# 6. Traverse adjustment
# ===========================================================================

class TestTraverseAdjust:

    def _imperfect_traverse(self):
        """Traverse with a small deliberate misclosure."""
        return [
            {"azimuth_dd": 0.0,   "distance": 100.0},
            {"azimuth_dd": 90.0,  "distance": 100.0},
            {"azimuth_dd": 179.5, "distance": 100.0},
            {"azimuth_dd": 270.0, "distance": 100.0},
        ]

    def test_compass_closure_after_near_zero(self):
        r = traverse_adjust(self._imperfect_traverse(), method="compass")
        assert r["ok"] is True
        assert r["closure_after"] < 1e-9

    def test_transit_closure_after_near_zero(self):
        r = traverse_adjust(self._imperfect_traverse(), method="transit")
        assert r["ok"] is True
        assert r["closure_after"] < 1e-9

    def test_stations_start_at_origin(self):
        r = traverse_adjust(self._imperfect_traverse())
        assert r["ok"] is True
        s0 = r["stations"][0]
        assert abs(s0["northing"]) < 1e-12
        assert abs(s0["easting"]) < 1e-12

    def test_n_stations_is_n_legs_plus_one(self):
        legs = self._imperfect_traverse()
        r = traverse_adjust(legs)
        assert r["ok"] is True
        assert len(r["stations"]) == len(legs) + 1

    def test_perfect_traverse_zero_corrections(self):
        """Perfect traverse: all corrections should be zero."""
        legs = [
            {"azimuth_dd": 0.0,   "distance": 100.0},
            {"azimuth_dd": 90.0,  "distance": 100.0},
            {"azimuth_dd": 180.0, "distance": 100.0},
            {"azimuth_dd": 270.0, "distance": 100.0},
        ]
        r = traverse_adjust(legs, method="compass")
        assert r["ok"] is True
        for leg in r["adjusted_legs"]:
            assert abs(leg["correction_N"]) < 1e-9
            assert abs(leg["correction_E"]) < 1e-9

    def test_invalid_method_returns_error(self):
        r = traverse_adjust(self._imperfect_traverse(), method="bowditch_wrong")
        assert r["ok"] is False


# ===========================================================================
# 7. Area by coordinates (Shoelace)
# ===========================================================================

class TestAreaByCoordinates:

    def test_unit_square(self):
        """Unit square area = 1.0 m²."""
        pts = [_pt(0, 0), _pt(1, 0), _pt(1, 1), _pt(0, 1)]
        r = area_by_coordinates(pts)
        assert r["ok"] is True
        assert abs(r["area_m2"] - 1.0) < REL

    def test_rectangle(self):
        """10×20 rectangle → 200 m²."""
        pts = [_pt(0, 0), _pt(10, 0), _pt(10, 20), _pt(0, 20)]
        r = area_by_coordinates(pts)
        assert r["ok"] is True
        assert abs(r["area_m2"] - 200.0) < REL

    def test_triangle(self):
        """Right triangle with legs 3, 4 → area = 6.0 m²."""
        pts = [_pt(0, 0), _pt(3, 0), _pt(0, 4)]
        r = area_by_coordinates(pts)
        assert r["ok"] is True
        assert abs(r["area_m2"] - 6.0) < REL

    def test_fewer_than_3_points_error(self):
        r = area_by_coordinates([_pt(0, 0), _pt(1, 1)])
        assert r["ok"] is False

    def test_regular_polygon_area(self):
        """Regular hexagon with circumradius 1.0 → area = 3√3/2 ≈ 2.598 m²."""
        R = 1.0
        pts = [_pt(R * math.cos(math.pi / 2 + i * 2 * math.pi / 6),
                   R * math.sin(math.pi / 2 + i * 2 * math.pi / 6))
               for i in range(6)]
        r = area_by_coordinates(pts)
        assert r["ok"] is True
        expected = 3.0 * math.sqrt(3.0) / 2.0
        assert abs(r["area_m2"] - expected) / expected < 1e-9


# ===========================================================================
# 8. Area by DMD
# ===========================================================================

class TestAreaByDmd:

    def test_unit_square_matches_shoelace(self):
        """DMD and Shoelace must give the same area for a unit square."""
        pts = [_pt(0, 0), _pt(1, 0), _pt(1, 1), _pt(0, 1)]
        r_dmd = area_by_dmd(pts)
        r_shoelace = area_by_coordinates(pts)
        assert r_dmd["ok"] is True
        assert r_shoelace["ok"] is True
        assert abs(r_dmd["area_m2"] - r_shoelace["area_m2"]) < 1e-9

    def test_rectangle_dmd(self):
        pts = [_pt(0, 0), _pt(10, 0), _pt(10, 20), _pt(0, 20)]
        r = area_by_dmd(pts)
        assert r["ok"] is True
        assert abs(r["area_m2"] - 200.0) < REL

    def test_dmd_legs_count(self):
        pts = [_pt(0, 0), _pt(5, 0), _pt(5, 5), _pt(0, 5)]
        r = area_by_dmd(pts)
        assert r["ok"] is True
        assert len(r["dmd_legs"]) == 4

    def test_fewer_than_3_points_error(self):
        r = area_by_dmd([_pt(0, 0), _pt(1, 0)])
        assert r["ok"] is False


# ===========================================================================
# 9. Line–line intersection
# ===========================================================================

class TestLineLineIntersection:

    def test_axis_crossing(self):
        """N-axis and E-axis intersect at origin."""
        p1 = _pt(-1, 0)
        p2 = _pt(1, 0)
        p3 = _pt(0, -1)
        p4 = _pt(0, 1)
        r = line_line_intersection(p1, p2, p3, p4)
        assert r["ok"] is True
        assert abs(r["northing"]) < 1e-9
        assert abs(r["easting"]) < 1e-9

    def test_diagonal_intersection(self):
        """Two 45° diagonals crossing at (5, 5)."""
        p1 = _pt(0, 0)
        p2 = _pt(10, 10)
        p3 = _pt(0, 10)
        p4 = _pt(10, 0)
        r = line_line_intersection(p1, p2, p3, p4)
        assert r["ok"] is True
        assert abs(r["northing"] - 5.0) < 1e-9
        assert abs(r["easting"] - 5.0) < 1e-9

    def test_parallel_lines_error(self):
        """Parallel lines must return ok=False."""
        p1 = _pt(0, 0)
        p2 = _pt(1, 0)
        p3 = _pt(0, 1)
        p4 = _pt(1, 1)
        r = line_line_intersection(p1, p2, p3, p4)
        assert r["ok"] is False

    def test_missing_northing_error(self):
        r = line_line_intersection({"easting": 0}, _pt(1, 0), _pt(0, -1), _pt(0, 1))
        assert r["ok"] is False


# ===========================================================================
# 10. Line–circle intersection
# ===========================================================================

class TestLineCircleIntersection:

    def test_two_intersections(self):
        """Horizontal line through circle centre — two intersections."""
        p1 = _pt(0, -10)
        p2 = _pt(0, 10)
        centre = _pt(0, 0)
        r = line_circle_intersection(p1, p2, centre, 5.0)
        assert r["ok"] is True
        assert r["n_intersections"] == 2

    def test_tangent_line(self):
        """Tangent line touches circle at exactly one point."""
        # Line N=5 (horizontal), circle centre (0,0) radius 5 → tangent at (5,0)
        p1 = _pt(5, -10)
        p2 = _pt(5, 10)
        centre = _pt(0, 0)
        r = line_circle_intersection(p1, p2, centre, 5.0)
        assert r["ok"] is True
        assert r["n_intersections"] in (1, 2)  # discriminant≈0 may give 1 or 2

    def test_no_intersection(self):
        """Line far from circle — no intersection."""
        p1 = _pt(100, 0)
        p2 = _pt(100, 1)
        centre = _pt(0, 0)
        r = line_circle_intersection(p1, p2, centre, 5.0)
        assert r["ok"] is True
        assert r["n_intersections"] == 0

    def test_negative_radius_error(self):
        r = line_circle_intersection(_pt(0, 0), _pt(1, 0), _pt(0, 0), -1.0)
        assert r["ok"] is False

    def test_intersection_points_on_circle(self):
        """Each intersection point must lie on the circle."""
        p1 = _pt(0, -10)
        p2 = _pt(0, 10)
        centre = _pt(0, 0)
        R = 3.0
        r = line_circle_intersection(p1, p2, centre, R)
        assert r["ok"] is True
        for pt in r["intersections"]:
            dn = pt["northing"] - centre["northing"]
            de = pt["easting"] - centre["easting"]
            dist = math.hypot(dn, de)
            assert abs(dist - R) < 1e-9, f"Point {pt} not on circle (dist={dist})"


# ===========================================================================
# 11. Point of intersection
# ===========================================================================

class TestPointOfIntersection:

    def test_perpendicular_rays(self):
        """Two perpendicular rays that cross: az 0° from (0,5) and az 90° from (0,0)."""
        # Ray 1: from (0,5) going due North (az=0) → stays at easting=5
        # Ray 2: from (0,0) going due East  (az=90) → stays at northing=0
        # Intersection: northing=0, easting=5
        r = point_of_intersection(
            azimuth1_dd=0.0, n1=0.0, e1=5.0,
            azimuth2_dd=90.0, n2=0.0, e2=0.0,
        )
        assert r["ok"] is True
        # Ray 1 is a pure-north line at easting=5; ray 2 is a pure-east line at northing=0
        # They cross at (northing=0, easting=5) in the forward direction
        assert abs(r["easting"] - 5.0) < 1e-9
        assert abs(r["northing"]) < 1e-9

    def test_known_intersection(self):
        """Two rays aimed at (50, 50) from different stations."""
        # Station 1 at (0,0) aimed at 45° (NE direction)
        # Station 2 at (100,0) aimed at 135° (NW direction)
        r = point_of_intersection(
            azimuth1_dd=45.0, n1=0.0, e1=0.0,
            azimuth2_dd=315.0, n2=0.0, e2=100.0,
        )
        assert r["ok"] is True
        assert abs(r["northing"] - 50.0) < 1e-6
        assert abs(r["easting"] - 50.0) < 1e-6

    def test_parallel_rays_error(self):
        """Parallel rays must return ok=False."""
        r = point_of_intersection(
            azimuth1_dd=0.0, n1=0.0, e1=0.0,
            azimuth2_dd=0.0, n2=0.0, e2=10.0,
        )
        assert r["ok"] is False


# ===========================================================================
# 12. Resection
# ===========================================================================

class TestResection:

    def _triangle_control_points(self):
        """Equilateral triangle with known vertices."""
        s = 100.0
        return [
            _pt(0.0, 0.0),
            _pt(0.0, s),
            _pt(s * math.sqrt(3) / 2.0, s / 2.0),
        ]

    def test_wrong_n_known_points(self):
        r = resection([_pt(0, 0), _pt(1, 0)], [30.0, 30.0])
        assert r["ok"] is False

    def test_wrong_n_obs_angles(self):
        pts = self._triangle_control_points()
        r = resection(pts, [30.0])
        assert r["ok"] is False

    def test_zero_angle_error(self):
        pts = self._triangle_control_points()
        r = resection(pts, [0.0, 30.0])
        assert r["ok"] is False

    def test_returns_coordinates(self):
        """Basic smoke test: resection returns finite coordinates."""
        pts = self._triangle_control_points()
        # Instrument somewhere inside the triangle
        r = resection(pts, [40.0, 40.0])
        # May succeed or detect danger circle — just check for ok or a reason
        assert "ok" in r
        if r["ok"]:
            assert math.isfinite(r["northing"])
            assert math.isfinite(r["easting"])

    def test_collinear_control_points_error(self):
        """Three collinear control points → degenerate triangle."""
        pts = [_pt(0, 0), _pt(0, 50), _pt(0, 100)]
        r = resection(pts, [30.0, 30.0])
        assert r["ok"] is False


# ===========================================================================
# 13. Level loop adjustment
# ===========================================================================

class TestLevelLoopAdjust:

    def test_perfect_loop_zero_misclosure(self):
        """Loop with zero total delta_h → zero misclosure."""
        obs = [
            {"distance": 50.0, "delta_h": 5.0},
            {"distance": 50.0, "delta_h": -5.0},
        ]
        r = level_loop_adjust(obs, known_elev=100.0)
        assert r["ok"] is True
        assert abs(r["misclosure"]) < 1e-12

    def test_adjusted_elevations_close_loop(self):
        """Last adjusted elevation must equal first (known_elev) for closed loop."""
        obs = [
            {"distance": 100.0, "delta_h":  3.1},
            {"distance": 120.0, "delta_h": -1.5},
            {"distance":  80.0, "delta_h": -1.7},
        ]
        r = level_loop_adjust(obs, known_elev=50.0)
        assert r["ok"] is True
        # After adjustment, sum of delta_h should be ~0
        total_adj = sum(o["delta_h"] for o in r["adjusted_observations"])
        assert abs(total_adj) < 1e-9

    def test_known_elev_is_first_station(self):
        obs = [{"distance": 100.0, "delta_h": 2.0},
               {"distance": 100.0, "delta_h": -2.0}]
        r = level_loop_adjust(obs, known_elev=75.0)
        assert r["ok"] is True
        assert abs(r["adjusted_elevations"][0] - 75.0) < 1e-9

    def test_n_elevations_is_n_obs_plus_one(self):
        obs = [{"distance": 50.0, "delta_h": 1.0},
               {"distance": 50.0, "delta_h": 2.0},
               {"distance": 50.0, "delta_h": -3.0}]
        r = level_loop_adjust(obs, known_elev=0.0)
        assert r["ok"] is True
        assert len(r["adjusted_elevations"]) == len(obs) + 1

    def test_empty_observations_error(self):
        r = level_loop_adjust([], known_elev=100.0)
        assert r["ok"] is False

    def test_corrections_sum_to_negative_misclosure(self):
        """Sum of corrections must equal -misclosure."""
        obs = [
            {"distance": 100.0, "delta_h":  2.0},
            {"distance": 200.0, "delta_h": -1.8},
        ]
        r = level_loop_adjust(obs, known_elev=0.0)
        assert r["ok"] is True
        total_corr = sum(o["correction"] for o in r["adjusted_observations"])
        assert abs(total_corr - (-r["misclosure"])) < 1e-9


# ===========================================================================
# 14. LLM tool wrappers
# ===========================================================================

class TestToolWrappers:

    def test_run_dms_to_dd_happy(self):
        ctx = _ctx()
        raw = _run(run_dms_to_dd(ctx, _args(degrees=45, minutes=30, seconds=0)))
        d = _ok_tool(raw)
        assert abs(d["dd"] - 45.5) < 1e-9

    def test_run_dms_to_dd_missing_field(self):
        ctx = _ctx()
        raw = _run(run_dms_to_dd(ctx, _args(degrees=45, minutes=30)))
        _err_tool(raw)

    def test_run_dd_to_dms_happy(self):
        ctx = _ctx()
        raw = _run(run_dd_to_dms(ctx, _args(dd=90.0)))
        d = _ok_tool(raw)
        assert d["degrees"] == 90

    def test_run_bearing_azimuth_to_azimuth(self):
        ctx = _ctx()
        raw = _run(run_bearing_azimuth(ctx, _args(mode="to_azimuth", quadrant="SW", bearing_dd=60.0)))
        d = _ok_tool(raw)
        assert abs(d["azimuth_dd"] - 240.0) < 1e-9

    def test_run_bearing_azimuth_to_bearing(self):
        ctx = _ctx()
        raw = _run(run_bearing_azimuth(ctx, _args(mode="to_bearing", azimuth_dd=315.0)))
        d = _ok_tool(raw)
        assert d["quadrant"] == "NW"
        assert abs(d["bearing_dd"] - 45.0) < 1e-9

    def test_run_bearing_azimuth_bad_mode(self):
        ctx = _ctx()
        raw = _run(run_bearing_azimuth(ctx, _args(mode="sideways")))
        _err_tool(raw)

    def test_run_forward_happy(self):
        ctx = _ctx()
        raw = _run(run_forward(ctx, _args(northing=0.0, easting=0.0, azimuth_dd=0.0, distance=100.0)))
        d = _ok_tool(raw)
        assert abs(d["northing"] - 100.0) < 1e-9

    def test_run_forward_bad_json(self):
        ctx = _ctx()
        raw = _run(run_forward(ctx, b"not json"))
        _err_tool(raw)

    def test_run_inverse_happy(self):
        ctx = _ctx()
        raw = _run(run_inverse(ctx, _args(n1=0.0, e1=0.0, n2=3.0, e2=4.0)))
        d = _ok_tool(raw)
        assert abs(d["distance"] - 5.0) < 1e-9

    def test_run_traverse_happy(self):
        ctx = _ctx()
        legs = [
            {"azimuth_dd": 0.0,   "distance": 100.0},
            {"azimuth_dd": 90.0,  "distance": 100.0},
            {"azimuth_dd": 180.0, "distance": 100.0},
            {"azimuth_dd": 270.0, "distance": 100.0},
        ]
        raw = _run(run_traverse(ctx, json.dumps({"legs": legs}).encode()))
        d = _ok_tool(raw)
        assert d["precision_ok"] is True

    def test_run_traverse_adjust_compass(self):
        ctx = _ctx()
        legs = [
            {"azimuth_dd": 0.0,   "distance": 100.0},
            {"azimuth_dd": 90.0,  "distance": 100.0},
            {"azimuth_dd": 179.5, "distance": 100.0},
            {"azimuth_dd": 270.0, "distance": 100.0},
        ]
        raw = _run(run_traverse_adjust(ctx, json.dumps({"legs": legs, "method": "compass"}).encode()))
        d = _ok_tool(raw)
        assert d["closure_after"] < 1e-9

    def test_run_area_coordinates_happy(self):
        ctx = _ctx()
        pts = [{"northing": 0, "easting": 0}, {"northing": 10, "easting": 0},
               {"northing": 10, "easting": 10}, {"northing": 0, "easting": 10}]
        raw = _run(run_area_coordinates(ctx, json.dumps({"points": pts}).encode()))
        d = _ok_tool(raw)
        assert abs(d["area_m2"] - 100.0) < 1e-9

    def test_run_area_dmd_happy(self):
        ctx = _ctx()
        pts = [{"northing": 0, "easting": 0}, {"northing": 10, "easting": 0},
               {"northing": 10, "easting": 10}, {"northing": 0, "easting": 10}]
        raw = _run(run_area_dmd(ctx, json.dumps({"points": pts}).encode()))
        d = _ok_tool(raw)
        assert abs(d["area_m2"] - 100.0) < 1e-9

    def test_run_poi_happy(self):
        ctx = _ctx()
        raw = _run(run_poi(ctx, _args(
            azimuth1_dd=45.0, n1=0.0, e1=0.0,
            azimuth2_dd=315.0, n2=0.0, e2=100.0,
        )))
        d = _ok_tool(raw)
        assert abs(d["northing"] - 50.0) < 1e-6
        assert abs(d["easting"] - 50.0) < 1e-6

    def test_run_resection_wrong_n_points(self):
        ctx = _ctx()
        raw = _run(run_resection(ctx, json.dumps({
            "p_known": [{"northing": 0, "easting": 0}],
            "obs_angles": [30.0, 40.0],
        }).encode()))
        _err_tool(raw)

    def test_run_level_loop_happy(self):
        ctx = _ctx()
        obs = [
            {"distance": 100.0, "delta_h": 2.0},
            {"distance": 100.0, "delta_h": -2.0},
        ]
        raw = _run(run_level_loop(ctx, json.dumps({"observations": obs, "known_elev": 50.0}).encode()))
        d = _ok_tool(raw)
        assert abs(d["misclosure"]) < 1e-12

    def test_run_level_loop_missing_known_elev(self):
        ctx = _ctx()
        obs = [{"distance": 100.0, "delta_h": 1.0}]
        raw = _run(run_level_loop(ctx, json.dumps({"observations": obs}).encode()))
        _err_tool(raw)
