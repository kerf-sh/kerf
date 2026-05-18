"""
Tests for kerf_civil — horizontal/vertical alignment, corridor, and earthwork.

DoD oracles:
  1. Circular curve length  L = R · Δ (radians)  — exact to 1e-12
  2. Clothoid spiral end angle θₛ = L / (2R)     — analytic, exact to 1e-12
  3. Parabolic crest high-point at expected x      — analytic formula
  4. Average-end-area volume matches trapezoid rule on uniform prism
"""

from __future__ import annotations

import math
import pytest

# ---------------------------------------------------------------------------
# Horizontal alignment — tangent
# ---------------------------------------------------------------------------

class TestTangentSegment:
    def test_arc_length(self):
        from kerf_civil.horizontal_alignment import TangentSegment
        t = TangentSegment(length=100.0)
        assert t.arc_length() == pytest.approx(100.0, abs=1e-12)

    def test_end_bearing_unchanged(self):
        from kerf_civil.horizontal_alignment import TangentSegment
        t = TangentSegment(length=50.0, bearing_rad=math.pi / 4)
        assert t.end_bearing() == pytest.approx(math.pi / 4, abs=1e-12)

    def test_coords_at_zero(self):
        from kerf_civil.horizontal_alignment import TangentSegment
        t = TangentSegment(length=100.0, bearing_rad=0.0)
        x, y = t.coords_at(0.0)
        assert x == pytest.approx(0.0, abs=1e-12)
        assert y == pytest.approx(0.0, abs=1e-12)

    def test_coords_at_end_due_north(self):
        from kerf_civil.horizontal_alignment import TangentSegment
        # bearing_rad=0 => due north => (sin 0, cos 0) = (0, 1) direction
        t = TangentSegment(length=100.0, bearing_rad=0.0)
        x, y = t.coords_at(100.0)
        assert x == pytest.approx(0.0, abs=1e-12)
        assert y == pytest.approx(100.0, abs=1e-12)

    def test_negative_length_raises(self):
        from kerf_civil.horizontal_alignment import TangentSegment
        with pytest.raises(ValueError):
            TangentSegment(length=-1.0)


# ---------------------------------------------------------------------------
# Horizontal alignment — circular arc (DoD oracle 1)
# ---------------------------------------------------------------------------

class TestCircularArc:
    """DoD: arc length = R · Δ to 1e-12"""

    @pytest.mark.parametrize("R, delta_deg", [
        (100.0, 30.0),
        (500.0, 90.0),
        (250.0, 45.0),
        (1000.0, 5.0),
        (50.0, 180.0),
    ])
    def test_arc_length_exact(self, R, delta_deg):
        from kerf_civil.horizontal_alignment import CircularArc
        delta_rad = math.radians(delta_deg)
        arc = CircularArc(radius=R, delta_rad=delta_rad)
        expected = R * delta_rad
        assert arc.arc_length() == pytest.approx(expected, abs=1e-12)

    def test_arc_length_left_turn(self):
        from kerf_civil.horizontal_alignment import CircularArc
        R, delta_deg = 200.0, 60.0
        delta_rad = math.radians(delta_deg)
        arc = CircularArc(radius=R, delta_rad=-delta_rad)  # left turn
        expected = R * delta_rad
        assert arc.arc_length() == pytest.approx(expected, abs=1e-12)

    def test_end_bearing_right_turn(self):
        from kerf_civil.horizontal_alignment import CircularArc
        bearing = math.pi / 6
        delta = math.pi / 3
        arc = CircularArc(radius=100.0, delta_rad=delta, bearing_rad=bearing)
        assert arc.end_bearing() == pytest.approx(bearing + delta, abs=1e-12)

    def test_chord_length(self):
        from kerf_civil.horizontal_alignment import CircularArc
        R = 300.0
        delta_rad = math.radians(60.0)
        arc = CircularArc(radius=R, delta_rad=delta_rad)
        expected = 2 * R * math.sin(delta_rad / 2)
        assert arc.chord_length() == pytest.approx(expected, abs=1e-10)

    def test_tangent_length(self):
        from kerf_civil.horizontal_alignment import CircularArc
        R = 300.0
        delta_rad = math.radians(60.0)
        arc = CircularArc(radius=R, delta_rad=delta_rad)
        expected = R * math.tan(delta_rad / 2)
        assert arc.tangent_length() == pytest.approx(expected, abs=1e-10)

    def test_coords_at_zero_is_origin(self):
        from kerf_civil.horizontal_alignment import CircularArc
        arc = CircularArc(radius=100.0, delta_rad=math.pi / 2)
        x, y = arc.coords_at(0.0, (0.0, 0.0))
        assert x == pytest.approx(0.0, abs=1e-10)
        assert y == pytest.approx(0.0, abs=1e-10)

    def test_coords_at_quarter_circle_due_north(self):
        """90° right turn from due-north bearing should end up due-east."""
        from kerf_civil.horizontal_alignment import CircularArc
        R = 100.0
        delta = math.pi / 2  # 90°, right turn
        # bearing_rad=0 = due north
        arc = CircularArc(radius=R, delta_rad=delta, bearing_rad=0.0)
        L = arc.arc_length()
        x, y = arc.coords_at(L, (0.0, 0.0))
        # After a 90° right turn from north, end tangent is due east.
        # The arc subtends a quarter circle; end point should be R right and R forward of centre.
        # Centre is to the right of start: (+R, 0) in (easting, northing)
        # End point (angle = π/2 swept): x_end = R, y_end = R (in easting/northing)
        assert x == pytest.approx(R, abs=1e-9)
        assert y == pytest.approx(R, abs=1e-9)

    def test_zero_radius_raises(self):
        from kerf_civil.horizontal_alignment import CircularArc
        with pytest.raises(ValueError):
            CircularArc(radius=0.0, delta_rad=0.1)


# ---------------------------------------------------------------------------
# Horizontal alignment — clothoid spiral (DoD oracle 2)
# ---------------------------------------------------------------------------

class TestClothoidSpiral:
    """DoD: end angle θₛ = L / (2R) to 1e-12 (analytic Euler clothoid)."""

    @pytest.mark.parametrize("L, R", [
        (60.0, 300.0),
        (100.0, 500.0),
        (30.0, 150.0),
        (200.0, 800.0),
        (50.0, 100.0),
    ])
    def test_end_angle_analytic(self, L, R):
        from kerf_civil.horizontal_alignment import ClothoidSpiral
        sp = ClothoidSpiral(length=L, radius_end=R)
        expected = L / (2.0 * R)
        assert sp.end_angle_rad() == pytest.approx(expected, abs=1e-12)

    def test_clothoid_parameter(self):
        from kerf_civil.horizontal_alignment import ClothoidSpiral
        L, R = 80.0, 400.0
        sp = ClothoidSpiral(length=L, radius_end=R)
        expected_A = math.sqrt(R * L)
        assert sp.parameter_A == pytest.approx(expected_A, abs=1e-12)

    def test_end_bearing_right(self):
        from kerf_civil.horizontal_alignment import ClothoidSpiral
        L, R = 60.0, 300.0
        bearing0 = math.pi / 6
        sp = ClothoidSpiral(length=L, radius_end=R, bearing_rad=bearing0, turn_right=True)
        theta_s = L / (2.0 * R)
        assert sp.end_bearing() == pytest.approx(bearing0 + theta_s, abs=1e-12)

    def test_end_bearing_left(self):
        from kerf_civil.horizontal_alignment import ClothoidSpiral
        L, R = 60.0, 300.0
        bearing0 = math.pi / 4
        sp = ClothoidSpiral(length=L, radius_end=R, bearing_rad=bearing0, turn_right=False)
        theta_s = L / (2.0 * R)
        assert sp.end_bearing() == pytest.approx(bearing0 - theta_s, abs=1e-12)

    def test_coords_at_zero_is_start(self):
        from kerf_civil.horizontal_alignment import ClothoidSpiral
        sp = ClothoidSpiral(length=80.0, radius_end=400.0)
        x, y = sp.coords_at(0.0, (10.0, 20.0))
        assert x == pytest.approx(10.0, abs=1e-10)
        assert y == pytest.approx(20.0, abs=1e-10)

    def test_tangent_offset_small_angle(self):
        """For small θₛ the tangent offset x ≈ L (cos of small angle ≈ 1)."""
        from kerf_civil.horizontal_alignment import ClothoidSpiral
        L, R = 10.0, 1000.0  # very small end angle = 0.005 rad
        sp = ClothoidSpiral(length=L, radius_end=R, bearing_rad=0.0)
        x, y = sp.coords_at(L)
        # x should be ≈ L  (along the forward direction = y in northing)
        # bearing=0 → forward = (sin0, cos0) = (0, 1) => northing
        assert y == pytest.approx(L, rel=1e-4)

    def test_zero_length_raises(self):
        from kerf_civil.horizontal_alignment import ClothoidSpiral
        with pytest.raises(ValueError):
            ClothoidSpiral(length=0.0, radius_end=300.0)

    def test_zero_radius_raises(self):
        from kerf_civil.horizontal_alignment import ClothoidSpiral
        with pytest.raises(ValueError):
            ClothoidSpiral(length=60.0, radius_end=0.0)


# ---------------------------------------------------------------------------
# AASHTO superelevation
# ---------------------------------------------------------------------------

class TestAASHTOSuperelevation:
    def test_minimum_radius_returns_emax(self):
        from kerf_civil.horizontal_alignment import aashto_superelevation
        e = aashto_superelevation(60, radius_ft=400)
        assert e == pytest.approx(8.0, abs=0.1)

    def test_large_radius_returns_small_e(self):
        from kerf_civil.horizontal_alignment import aashto_superelevation
        e = aashto_superelevation(60, radius_ft=5000)
        assert e <= 2.0

    def test_e_bounded_by_emax(self):
        from kerf_civil.horizontal_alignment import aashto_superelevation
        for speed in (20, 30, 40, 50, 60, 70, 80):
            e = aashto_superelevation(speed, radius_ft=10)
            assert e <= 8.0


# ---------------------------------------------------------------------------
# Compound horizontal alignment
# ---------------------------------------------------------------------------

class TestHorizontalAlignment:
    def test_total_length_single_tangent(self):
        from kerf_civil.horizontal_alignment import HorizontalAlignment
        ha = HorizontalAlignment()
        ha.add_tangent(200.0)
        assert ha.total_length() == pytest.approx(200.0, abs=1e-12)

    def test_total_length_tangent_arc_tangent(self):
        from kerf_civil.horizontal_alignment import HorizontalAlignment
        ha = HorizontalAlignment()
        ha.add_tangent(100.0)
        ha.add_arc(300.0, math.radians(45.0))
        ha.add_tangent(100.0)
        expected = 100.0 + 300.0 * math.radians(45.0) + 100.0
        assert ha.total_length() == pytest.approx(expected, abs=1e-10)

    def test_bearing_chain_two_arcs(self):
        """Bearing after two 45° arcs should be 90°."""
        from kerf_civil.horizontal_alignment import HorizontalAlignment
        ha = HorizontalAlignment()
        ha.add_arc(200.0, math.radians(45.0))
        ha.add_arc(200.0, math.radians(45.0))
        assert ha._current_bearing == pytest.approx(math.radians(90.0), abs=1e-12)

    def test_spiral_arc_chain(self):
        """Station after spiral+arc should equal sum of their lengths."""
        from kerf_civil.horizontal_alignment import HorizontalAlignment
        ha = HorizontalAlignment()
        ha.add_spiral(60.0, 300.0)
        ha.add_arc(300.0, math.radians(30.0))
        expected_L = 60.0 + 300.0 * math.radians(30.0)
        assert ha.total_length() == pytest.approx(expected_L, abs=1e-10)

    def test_station_list_covers_full_length(self):
        from kerf_civil.horizontal_alignment import HorizontalAlignment
        ha = HorizontalAlignment()
        ha.add_tangent(105.0)
        stations = ha.station_list(interval=20.0)
        assert stations[-1] == pytest.approx(105.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Vertical alignment — tangent
# ---------------------------------------------------------------------------

class TestVerticalTangent:
    def test_elev_at_start(self):
        from kerf_civil.vertical_alignment import VerticalTangent
        t = VerticalTangent(length=100.0, grade_pct=5.0, elev_start=10.0)
        assert t.elev_at(0.0) == pytest.approx(10.0, abs=1e-12)

    def test_elev_at_end(self):
        from kerf_civil.vertical_alignment import VerticalTangent
        t = VerticalTangent(length=100.0, grade_pct=5.0, elev_start=10.0)
        assert t.elev_at(100.0) == pytest.approx(15.0, abs=1e-12)

    def test_negative_grade(self):
        from kerf_civil.vertical_alignment import VerticalTangent
        t = VerticalTangent(length=200.0, grade_pct=-3.0, elev_start=50.0)
        assert t.elev_at(200.0) == pytest.approx(44.0, abs=1e-12)


# ---------------------------------------------------------------------------
# Vertical alignment — parabolic curve (DoD oracles 3)
# ---------------------------------------------------------------------------

class TestParabolicCurve:
    """DoD: high point of a crest curve lies at x* = −g1 * L / A."""

    def test_elev_at_bvc(self):
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=4.0, grade_out_pct=-2.0, elev_bvc=100.0)
        assert c.elev_at(0.0) == pytest.approx(100.0, abs=1e-12)

    def test_A_value(self):
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=4.0, grade_out_pct=-2.0)
        assert c.A == pytest.approx(-6.0, abs=1e-12)

    def test_K_value(self):
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=4.0, grade_out_pct=-2.0)
        # K = L / |A| = 200 / 6
        assert c.K_value() == pytest.approx(200.0 / 6.0, abs=1e-12)

    def test_crest_identification(self):
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=4.0, grade_out_pct=-2.0)
        assert c.is_crest()
        assert not c.is_sag()

    def test_sag_identification(self):
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=-3.0, grade_out_pct=3.0)
        assert c.is_sag()
        assert not c.is_crest()

    @pytest.mark.parametrize("g1, g2, L, elev_bvc", [
        (4.0, -2.0, 200.0, 100.0),
        (5.0, -1.0, 150.0, 50.0),
        (3.0, -3.0, 300.0, 200.0),
    ])
    def test_high_point_location_analytic(self, g1, g2, L, elev_bvc):
        """DoD oracle 3: x* = −g1 * L / A."""
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=L, grade_in_pct=g1, grade_out_pct=g2, elev_bvc=elev_bvc)
        A = g2 - g1
        x_expected = -g1 * L / A
        x_actual = c.high_low_point_x()
        assert x_actual is not None, "Expected a high point within the curve"
        assert x_actual == pytest.approx(x_expected, abs=1e-10)

    def test_high_point_elevation(self):
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=4.0, grade_out_pct=-2.0, elev_bvc=100.0)
        x_star = c.high_low_point_x()
        e_star = c.high_low_point_elev()
        # Verify it matches elev_at(x_star)
        assert e_star == pytest.approx(c.elev_at(x_star), abs=1e-12)
        # Verify it is a maximum for a crest curve
        eps = 1.0
        if x_star - eps >= 0:
            assert c.elev_at(x_star) >= c.elev_at(x_star - eps)
        if x_star + eps <= c.length:
            assert c.elev_at(x_star) >= c.elev_at(x_star + eps)

    def test_no_high_point_monotone_grade(self):
        """No sign change in grade → no extremum within the curve."""
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=2.0, grade_out_pct=5.0)
        # Low point at x < 0 → outside the curve
        assert c.high_low_point_x() is None

    def test_elev_at_evc(self):
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=4.0, grade_out_pct=-2.0, elev_bvc=100.0)
        # y(L) = bvc + g1/100 * L + A/(200L) * L^2  = 100 + 4/100*200 + (-6)/(200*200)*200^2
        #      = 100 + 8 + (-6)/200 * 200  = 100 + 8 - 6 = 102
        assert c.elev_evc() == pytest.approx(102.0, abs=1e-10)

    def test_from_K_and_A(self):
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve.from_K_and_A(K=50.0, A_pct=-6.0, grade_in_pct=3.0)
        assert c.length == pytest.approx(300.0, abs=1e-12)
        assert c.grade_out_pct == pytest.approx(-3.0, abs=1e-12)

    def test_grade_at_pct_at_high_point(self):
        """Grade at the high-point should be 0 %."""
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=4.0, grade_out_pct=-2.0)
        x_star = c.high_low_point_x()
        g = c.grade_at_pct(x_star)
        assert g == pytest.approx(0.0, abs=1e-8)


# ---------------------------------------------------------------------------
# Compound vertical alignment
# ---------------------------------------------------------------------------

class TestVerticalAlignment:
    def test_total_length(self):
        from kerf_civil.vertical_alignment import VerticalAlignment
        va = VerticalAlignment()
        va.set_datum(elev=100.0, grade_pct=3.0)
        va.add_tangent(200.0)
        va.add_curve(200.0, grade_out_pct=-3.0)
        va.add_tangent(100.0)
        assert va.total_length() == pytest.approx(500.0, abs=1e-12)

    def test_elevation_after_tangent(self):
        from kerf_civil.vertical_alignment import VerticalAlignment
        va = VerticalAlignment()
        va.set_datum(elev=0.0, grade_pct=5.0)
        va.add_tangent(100.0)
        assert va._current_elev == pytest.approx(5.0, abs=1e-12)


# ---------------------------------------------------------------------------
# Corridor
# ---------------------------------------------------------------------------

class TestCorridor:
    def _simple_corridor(self, length=200.0, grade=0.0):
        from kerf_civil.horizontal_alignment import HorizontalAlignment
        from kerf_civil.vertical_alignment import VerticalAlignment
        from kerf_civil.corridor import TypicalSection, Corridor
        ha = HorizontalAlignment()
        ha.add_tangent(length)
        va = VerticalAlignment()
        va.set_datum(elev=10.0, grade_pct=grade)
        va.add_tangent(length)
        ts = TypicalSection(lane_width=3.65, shoulder_width=2.4, lanes_each_side=1)
        return Corridor(h_alignment=ha, v_alignment=va, typical_section=ts)

    def test_cross_section_count(self):
        c = self._simple_corridor(200.0)
        sections = c.cross_sections(interval=20.0)
        # 0, 20, 40, ..., 200 = 11 sections
        assert len(sections) == 11

    def test_cross_section_has_cl_point(self):
        c = self._simple_corridor(100.0)
        xs = c.cross_section_at(50.0)
        cl_points = [p for p in xs.points if p.label == "CL"]
        assert len(cl_points) == 1
        assert cl_points[0].offset == pytest.approx(0.0, abs=1e-12)

    def test_cross_section_cl_elevation(self):
        c = self._simple_corridor(100.0, grade=5.0)
        xs = c.cross_section_at(40.0)
        # CL elevation = 10 + 5%*40 = 12.0
        assert xs.cl_elevation == pytest.approx(12.0, abs=1e-6)

    def test_surface_points_non_empty(self):
        c = self._simple_corridor(100.0)
        pts = c.surface_points(interval=50.0)
        assert len(pts) > 0

    def test_symmetry_of_section(self):
        """Left and right shoulder offsets should mirror each other."""
        c = self._simple_corridor(100.0)
        xs = c.cross_section_at(50.0)
        left_sh = [p for p in xs.points if p.label == "shoulder_left"]
        right_sh = [p for p in xs.points if p.label == "shoulder_right"]
        assert len(left_sh) == 1 and len(right_sh) == 1
        assert left_sh[0].offset == pytest.approx(-right_sh[0].offset, abs=1e-10)


# ---------------------------------------------------------------------------
# Earthwork (DoD oracle 4)
# ---------------------------------------------------------------------------

class TestAverageEndAreaVolume:
    """DoD oracle 4: average-end-area = trapezoid rule = exact volume for uniform prism."""

    def test_uniform_prism(self):
        """V = n * spacing * A for a uniform prism (all areas equal)."""
        from kerf_civil.earthwork import average_end_area_volume
        A = 25.0
        spacing = 20.0
        n = 5  # 6 sections, 5 intervals
        areas = [A] * (n + 1)
        expected = n * spacing * A
        result = average_end_area_volume(areas, spacing)
        assert result == pytest.approx(expected, abs=1e-12)

    def test_uniform_prism_variable_spacing(self):
        from kerf_civil.earthwork import average_end_area_volume_variable
        A = 30.0
        stations = [0.0, 15.0, 35.0, 60.0]
        areas = [A, A, A, A]
        # Total length = 60 m, volume = 60 * 30 = 1800
        result = average_end_area_volume_variable(areas, stations)
        assert result == pytest.approx(1800.0, abs=1e-12)

    def test_linear_area_trapezoid(self):
        """For linearly increasing area, AEA equals trapezoid rule exactly."""
        from kerf_civil.earthwork import average_end_area_volume
        spacing = 10.0
        areas = [0.0, 10.0, 20.0, 30.0]  # linear, 3 intervals
        # Trapezoid: (0+10)/2*10 + (10+20)/2*10 + (20+30)/2*10 = 50 + 150 + 250 = 450... wait
        # = 5*10 + 15*10 + 25*10 = 50 + 150 + 250 = 450
        expected = 5 * 10 + 15 * 10 + 25 * 10
        result = average_end_area_volume(areas, spacing)
        assert result == pytest.approx(expected, abs=1e-12)

    def test_single_interval(self):
        from kerf_civil.earthwork import average_end_area_volume
        result = average_end_area_volume([10.0, 20.0], 5.0)
        assert result == pytest.approx(75.0, abs=1e-12)

    def test_empty_returns_zero(self):
        from kerf_civil.earthwork import average_end_area_volume
        assert average_end_area_volume([], 10.0) == 0.0
        assert average_end_area_volume([5.0], 10.0) == 0.0

    def test_variable_spacing_strict_increasing(self):
        from kerf_civil.earthwork import average_end_area_volume_variable
        with pytest.raises(ValueError):
            average_end_area_volume_variable([1.0, 2.0], [10.0, 5.0])  # decreasing

    def test_mismatched_lengths(self):
        from kerf_civil.earthwork import average_end_area_volume_variable
        with pytest.raises(ValueError):
            average_end_area_volume_variable([1.0, 2.0], [0.0, 10.0, 20.0])


# ---------------------------------------------------------------------------
# Prismoidal formula
# ---------------------------------------------------------------------------

class TestPrismoidalVolume:
    def test_uniform_prism_matches_aea(self):
        """For a uniform prism, prismoidal and AEA give the same result."""
        from kerf_civil.earthwork import prismoidal_volume, average_end_area_volume
        A = 20.0
        spacing = 15.0
        areas = [A, A, A, A]  # 3 intervals
        mid_areas = [A, A, A]
        pv = prismoidal_volume(areas, mid_areas, spacing)
        aea = average_end_area_volume(areas, spacing)
        assert pv == pytest.approx(aea, abs=1e-12)


# ---------------------------------------------------------------------------
# Mass haul
# ---------------------------------------------------------------------------

class TestMassHaul:
    def test_all_cut_no_fill(self):
        from kerf_civil.earthwork import mass_haul
        stations = [0.0, 50.0, 100.0]
        cut = [10.0, 10.0, 10.0]
        fill = [0.0, 0.0, 0.0]
        mh = mass_haul(stations, cut, fill)
        assert mh[-1].cut_vol == pytest.approx(1000.0, abs=1e-10)
        assert mh[-1].fill_vol == pytest.approx(0.0, abs=1e-10)

    def test_equal_cut_fill_net_zero(self):
        from kerf_civil.earthwork import mass_haul
        stations = [0.0, 100.0]
        A = 10.0
        mh = mass_haul(stations, [A, A], [A, A], swell_factor=1.0)
        # net = cut - fill * 1.0 = 0
        assert mh[-1].mass_ordinate == pytest.approx(0.0, abs=1e-12)

    def test_swell_factor_increases_net(self):
        from kerf_civil.earthwork import mass_haul
        stations = [0.0, 100.0]
        mh = mass_haul(stations, [10.0, 10.0], [10.0, 10.0], swell_factor=1.25)
        # net = 1000 - 1000 * 1.25 = -250 (fill > cut in expanded volume)
        assert mh[-1].mass_ordinate == pytest.approx(-250.0, abs=1e-10)

    def test_first_ordinate_is_zero(self):
        from kerf_civil.earthwork import mass_haul
        mh = mass_haul([0.0, 50.0], [5.0, 5.0], [2.0, 2.0])
        assert mh[0].mass_ordinate == pytest.approx(0.0, abs=1e-12)
        assert mh[0].station == pytest.approx(0.0, abs=1e-12)
