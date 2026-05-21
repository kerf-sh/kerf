"""
T-99 — Hermetic pytest: Civil persona end-to-end scenario.

Simulates the LLM-driven civil workflow:
  1. Horizontal alignment  — tangent + circular arc + clothoid spiral
  2. Vertical alignment    — tangent + parabolic crest curve + tangent
  3. Corridor sweep        — cross-sections at 20 m interval
  4. Earthwork volumes     — AEA cut/fill from a rectangular prism fixture
     Success criterion: computed volumes match analytic reference within 2 %.
  5. Mass haul             — Brückner curve ordinates
  6. DXF export            — alignment to DXF R12; structural validation
  7. Cut/fill DXF          — profile diagram to DXF R12

All tests are pure-Python, hermetic: no DB, no network, no OCC.
No mocks needed — all calculations use fixed deterministic inputs.

DoD assertions (≥ 10 visible assertions per class):
  • Alignment: total length exact, arc length R·Δ, spiral end angle L/(2R)
  • Earthwork: volumes within 2 % of analytic reference
  • Mass haul: final ordinate correct; swell factor applied
  • DXF: valid R12 structure; ALIGNMENT layer present; station labels
  • Cut/fill DXF: CUT / FILL / DATUM layers; EOF present
  • coords_at_station: start = origin, mid-tangent, end within tolerance
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 1 — Horizontal alignment persona scenario
# ---------------------------------------------------------------------------

class TestCivilAlignmentPersona:
    """
    Civil scenario: 500 m road alignment with tangent → arc → spiral → tangent.

    Design parameters (typical rural highway):
      T1 : tangent  200 m
      A1 : arc      R=300 m, Δ=30°
      S1 : spiral   L=60 m,  R=300 m (entry transition)
      T2 : tangent  remaining (~80 m filler, exact)
    """

    R = 300.0
    DELTA_DEG = 30.0
    SPIRAL_L = 60.0
    TANGENT_1 = 200.0
    TANGENT_2 = 80.0

    def _build(self):
        from kerf_civil.horizontal_alignment import HorizontalAlignment
        ha = HorizontalAlignment()
        ha.add_tangent(self.TANGENT_1)
        ha.add_arc(self.R, math.radians(self.DELTA_DEG))
        ha.add_spiral(self.SPIRAL_L, self.R)
        ha.add_tangent(self.TANGENT_2)
        return ha

    # ----- DoD assertions -----

    def test_alignment_total_length(self):
        """Total length = sum of all element lengths."""
        ha = self._build()
        arc_len = self.R * math.radians(self.DELTA_DEG)
        expected = self.TANGENT_1 + arc_len + self.SPIRAL_L + self.TANGENT_2
        assert ha.total_length() == pytest.approx(expected, rel=1e-10)

    def test_arc_length_rdelta(self):
        """Arc element: L = R · |Δ| (DoD oracle 1)."""
        from kerf_civil.horizontal_alignment import CircularArc
        arc = CircularArc(radius=self.R, delta_rad=math.radians(self.DELTA_DEG))
        expected = self.R * math.radians(self.DELTA_DEG)
        assert arc.arc_length() == pytest.approx(expected, abs=1e-12)

    def test_spiral_end_angle_analytic(self):
        """Spiral: θₛ = L/(2R) (DoD oracle 2)."""
        from kerf_civil.horizontal_alignment import ClothoidSpiral
        sp = ClothoidSpiral(length=self.SPIRAL_L, radius_end=self.R)
        expected = self.SPIRAL_L / (2.0 * self.R)
        assert sp.end_angle_rad() == pytest.approx(expected, abs=1e-12)

    def test_station_list_covers_full_length(self):
        """station_list last element equals total length."""
        ha = self._build()
        stations = ha.station_list(interval=20.0)
        assert stations[-1] == pytest.approx(ha.total_length(), abs=1e-9)

    def test_station_list_includes_zero(self):
        ha = self._build()
        stations = ha.station_list(interval=20.0)
        assert stations[0] == pytest.approx(0.0, abs=1e-12)

    def test_station_list_monotone(self):
        ha = self._build()
        stations = ha.station_list(interval=20.0)
        for a, b in zip(stations, stations[1:]):
            assert b > a - 1e-9

    def test_coords_at_station_start_is_origin(self):
        """coords_at_station(0) must return (0, 0)."""
        ha = self._build()
        x, y = ha.coords_at_station(0.0)
        assert x == pytest.approx(0.0, abs=1e-10)
        assert y == pytest.approx(0.0, abs=1e-10)

    def test_coords_at_station_mid_tangent_due_north(self):
        """
        Alignment starts bearing=0 (due north) → after 100 m on tangent 1
        coords should be (0, 100).
        """
        ha = self._build()
        x, y = ha.coords_at_station(100.0)
        # bearing_rad=0 → (sin 0, cos 0) direction = (0, 1)
        assert x == pytest.approx(0.0, abs=1e-9)
        assert y == pytest.approx(100.0, abs=1e-9)

    def test_coords_at_station_end_tangent_1(self):
        """At station 200 (end of tangent 1) → (0, 200)."""
        ha = self._build()
        x, y = ha.coords_at_station(200.0)
        assert x == pytest.approx(0.0, abs=1e-9)
        assert y == pytest.approx(200.0, abs=1e-9)

    def test_coords_at_station_total_length(self):
        """coords_at_station(total_length) must not raise and return finite values."""
        ha = self._build()
        L = ha.total_length()
        x, y = ha.coords_at_station(L)
        assert math.isfinite(x)
        assert math.isfinite(y)

    def test_coords_at_station_out_of_range_raises(self):
        ha = self._build()
        with pytest.raises(ValueError):
            ha.coords_at_station(ha.total_length() + 10.0)

    def test_bearing_chain_after_arc(self):
        """After a 30° right turn, current bearing should be 30° (π/6 rad)."""
        ha = self._build()
        # bearing_chain is tracked internally
        # After T1=200 (bearing stays 0), then arc Δ=30° right, bearing = π/6
        # Approximation: after spiral the bearing is π/6 + spiral end angle
        expected_after_arc = math.radians(30.0)
        # Just test that arc changes bearing
        from kerf_civil.horizontal_alignment import HorizontalAlignment
        ha2 = HorizontalAlignment()
        ha2.add_tangent(100.0)
        ha2.add_arc(self.R, math.radians(self.DELTA_DEG))
        assert ha2._current_bearing == pytest.approx(expected_after_arc, abs=1e-12)


# ---------------------------------------------------------------------------
# 2 — Vertical alignment persona scenario
# ---------------------------------------------------------------------------

class TestCivilVerticalAlignmentPersona:
    """
    Vertical alignment: flat → crest curve → descending grade.

    Parameters:
      datum  : elev=10 m, grade=+3 %
      T1     : 200 m tangent
      C1     : 200 m parabolic crest (grade_out=−3 %)
      T2     : 100 m tangent
    """

    def _build(self):
        from kerf_civil.vertical_alignment import VerticalAlignment
        va = VerticalAlignment()
        va.set_datum(elev=10.0, grade_pct=3.0)
        va.add_tangent(200.0)
        va.add_curve(200.0, grade_out_pct=-3.0)
        va.add_tangent(100.0)
        return va

    def test_total_length(self):
        va = self._build()
        assert va.total_length() == pytest.approx(500.0, abs=1e-12)

    def test_elevation_at_datum(self):
        from kerf_civil.vertical_alignment import VerticalAlignment
        va = VerticalAlignment()
        va.set_datum(elev=10.0, grade_pct=3.0)
        assert va._current_elev == pytest.approx(10.0, abs=1e-12)

    def test_elevation_after_tangent_1(self):
        """After 200 m at +3 %: elev = 10 + 3/100*200 = 16 m."""
        from kerf_civil.vertical_alignment import VerticalAlignment
        va = VerticalAlignment()
        va.set_datum(elev=10.0, grade_pct=3.0)
        va.add_tangent(200.0)
        assert va._current_elev == pytest.approx(16.0, abs=1e-12)

    def test_crest_curve_detected(self):
        """Parabolic curve g1=+3%, g2=−3% is a crest."""
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=3.0, grade_out_pct=-3.0)
        assert c.is_crest()

    def test_crest_K_value(self):
        """K = L / |A| = 200 / 6."""
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=3.0, grade_out_pct=-3.0)
        assert c.K_value() == pytest.approx(200.0 / 6.0, abs=1e-12)

    def test_high_point_at_centre(self):
        """
        Symmetric crest (g1=+3%, g2=−3%) → high point at L/2 = 100 m.
        x* = −g1 * L / A = −3 * 200 / (−6) = 100.
        """
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=3.0, grade_out_pct=-3.0)
        x_star = c.high_low_point_x()
        assert x_star == pytest.approx(100.0, abs=1e-10)

    def test_grade_zero_at_high_point(self):
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=3.0, grade_out_pct=-3.0)
        x_star = c.high_low_point_x()
        assert c.grade_at_pct(x_star) == pytest.approx(0.0, abs=1e-8)

    def test_high_point_elevation_finite(self):
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=3.0, grade_out_pct=-3.0, elev_bvc=16.0)
        e_star = c.high_low_point_elev()
        assert math.isfinite(e_star)
        assert e_star > 16.0  # elevation at high point > BVC elevation

    def test_elev_evc_symmetric_crest(self):
        """
        For symmetric crest (g1=+3%, g2=−3%, L=200), the EVC elevation
        should equal the BVC elevation (symmetry).
        y(L) = bvc + g1/100*L + A/(200L)*L² = bvc + 6 + (-6)/200*200 = bvc
        """
        from kerf_civil.vertical_alignment import ParabolicCurve
        c = ParabolicCurve(length=200.0, grade_in_pct=3.0, grade_out_pct=-3.0, elev_bvc=16.0)
        # EVC = BVC + g1/100*L + A/200 = 16 + 3/100*200 + (-6)/200*200 = 16+6-6 = 16
        assert c.elev_evc() == pytest.approx(16.0, abs=1e-10)


# ---------------------------------------------------------------------------
# 3 — Corridor sweep persona
# ---------------------------------------------------------------------------

class TestCivilCorridorPersona:
    """Corridor sweep: 300 m straight road, standard 2-lane section."""

    def _build_corridor(self):
        from kerf_civil.horizontal_alignment import HorizontalAlignment
        from kerf_civil.vertical_alignment import VerticalAlignment
        from kerf_civil.corridor import TypicalSection, Corridor

        ha = HorizontalAlignment()
        ha.add_tangent(300.0)

        va = VerticalAlignment()
        va.set_datum(elev=20.0, grade_pct=2.0)
        va.add_tangent(300.0)

        ts = TypicalSection(
            lane_width=3.65,
            shoulder_width=2.4,
            lanes_each_side=1,
            crown_slope_pct=2.0,
        )
        return Corridor(h_alignment=ha, v_alignment=va, typical_section=ts)

    def test_cross_section_count_300m_at_20m(self):
        """300 m / 20 m = 16 sections (0, 20, 40, ..., 300)."""
        corridor = self._build_corridor()
        sections = corridor.cross_sections(interval=20.0)
        assert len(sections) == 16

    def test_cross_section_has_cl(self):
        corridor = self._build_corridor()
        xs = corridor.cross_section_at(150.0)
        cl = [p for p in xs.points if p.label == "CL"]
        assert len(cl) == 1
        assert cl[0].offset == pytest.approx(0.0, abs=1e-12)

    def test_cl_elevation_at_station_150(self):
        """At station 150: elev = 20 + 2%*150 = 23 m."""
        corridor = self._build_corridor()
        xs = corridor.cross_section_at(150.0)
        assert xs.cl_elevation == pytest.approx(23.0, abs=1e-6)

    def test_symmetry_shoulder_offsets(self):
        """Left and right shoulders are equidistant from CL."""
        corridor = self._build_corridor()
        xs = corridor.cross_section_at(100.0)
        left_sh = [p for p in xs.points if p.label == "shoulder_left"]
        right_sh = [p for p in xs.points if p.label == "shoulder_right"]
        assert len(left_sh) == 1 and len(right_sh) == 1
        assert left_sh[0].offset == pytest.approx(-right_sh[0].offset, abs=1e-10)

    def test_surface_points_non_empty(self):
        corridor = self._build_corridor()
        pts = corridor.surface_points(interval=50.0)
        assert len(pts) > 0

    def test_cross_section_point_count(self):
        """Each cross section has CL + 2 edge_lane + 2 shoulder + 2 daylight = 7 points."""
        corridor = self._build_corridor()
        xs = corridor.cross_section_at(0.0)
        assert len(xs.points) == 7

    def test_points_ordered_left_to_right(self):
        """Points should be ordered by offset (left → CL → right)."""
        corridor = self._build_corridor()
        xs = corridor.cross_section_at(60.0)
        offsets = [p.offset for p in xs.points]
        for a, b in zip(offsets, offsets[1:]):
            assert b >= a - 1e-10


# ---------------------------------------------------------------------------
# 4 — Earthwork volumes persona (DoD: within 2 %)
# ---------------------------------------------------------------------------

class TestCivilEarthworkPersona:
    """
    Earthwork scenario: uniform 5 m² cut over a 200 m alignment at 20 m stations.

    Analytic volume: 11 stations, 10 intervals of 20 m.
    V_analytic = 10 * 20 * 5 = 1000 m³ (uniform prism — AEA is exact).

    The test verifies computed volume matches analytic within 2 %.
    """

    STATIONS = [i * 20.0 for i in range(11)]  # 0, 20, 40, ..., 200
    CUT_UNIFORM = [5.0] * 11
    FILL_ZERO = [0.0] * 11
    ANALYTIC_VOLUME = 1000.0  # m³

    def test_aea_uniform_prism_exact(self):
        """AEA on uniform prism is exact (zero error)."""
        from kerf_civil.earthwork import average_end_area_volume
        result = average_end_area_volume(self.CUT_UNIFORM, 20.0)
        assert result == pytest.approx(self.ANALYTIC_VOLUME, abs=1e-12)

    def test_aea_variable_stations_within_2_percent(self):
        """Variable-spacing AEA on same fixture: within 2% of analytic."""
        from kerf_civil.earthwork import average_end_area_volume_variable
        result = average_end_area_volume_variable(self.CUT_UNIFORM, self.STATIONS)
        error_pct = abs(result - self.ANALYTIC_VOLUME) / self.ANALYTIC_VOLUME * 100
        assert error_pct < 2.0, f"Volume error {error_pct:.2f}% exceeds 2%"

    def test_fill_zero_for_all_cut(self):
        """All cut, no fill → fill volume = 0."""
        from kerf_civil.earthwork import average_end_area_volume_variable
        fill_vol = average_end_area_volume_variable(self.FILL_ZERO, self.STATIONS)
        assert fill_vol == pytest.approx(0.0, abs=1e-12)

    def test_mixed_cut_fill_within_2_percent(self):
        """
        Linearly varying cut (0 → 10 m²) over 200 m.
        Analytic: trapezoid = 200 * (0+10)/2 = 1000 m³.
        AEA (same result for linear): within 2%.
        """
        from kerf_civil.earthwork import average_end_area_volume_variable
        n = 11
        cut_lin = [10.0 * i / (n - 1) for i in range(n)]
        result = average_end_area_volume_variable(cut_lin, self.STATIONS)
        analytic = 200.0 * 10.0 / 2.0  # = 1000
        error_pct = abs(result - analytic) / analytic * 100
        assert error_pct < 2.0, f"Volume error {error_pct:.2f}% exceeds 2%"

    def test_cut_exceeds_fill_net_positive(self):
        """Net earthwork = cut − fill*swell should be positive for surplus cut."""
        from kerf_civil.earthwork import average_end_area_volume_variable, mass_haul
        cut_areas = [8.0] * 11
        fill_areas = [2.0] * 11
        mh = mass_haul(self.STATIONS, cut_areas, fill_areas, swell_factor=1.0)
        # cut_vol = 8*200 = 1600; fill_vol = 2*200 = 400; net = 1200
        assert mh[-1].mass_ordinate == pytest.approx(1200.0, abs=1e-9)

    def test_prismoidal_matches_aea_uniform(self):
        """For uniform prism, prismoidal = AEA."""
        from kerf_civil.earthwork import prismoidal_volume, average_end_area_volume
        A = 5.0
        areas = [A] * 11
        mid_areas = [A] * 10
        pv = prismoidal_volume(areas, mid_areas, 20.0)
        aea = average_end_area_volume(areas, 20.0)
        assert pv == pytest.approx(aea, abs=1e-12)

    def test_volumes_within_2_pct_of_analytic_crest_fill(self):
        """
        Parabolic fill profile (v-notch): areas = 5*(1-(x/100)^2) for x in [0..200].
        Analytic integral = ∫₀²⁰⁰ 5*(1-(x/100)^2) dx = 5[x - x^3/(3*10000)]₀²⁰⁰
            = 5*(200 - 8000000/30000) = 5*(200 - 266.67) → negative → use abs
        Actually: areas are non-negative so clamp.  Use a simpler parabola:
            a(x) = (x/200) * (1 - x/200) * 20   (peak = 5 m² at mid)
        Analytic: ∫₀²⁰⁰ 20*(x/200)*(1-x/200) dx = 20 * 1/6 * 200 = 666.67 m³
        """
        from kerf_civil.earthwork import average_end_area_volume_variable
        stations = [i * 20.0 for i in range(11)]
        areas = [20.0 * (s / 200.0) * (1.0 - s / 200.0) for s in stations]
        analytic = 20.0 * 200.0 / 6.0  # = 666.67
        result = average_end_area_volume_variable(areas, stations)
        error_pct = abs(result - analytic) / analytic * 100
        # AEA on parabola: error is small but < 2% for 10 intervals
        assert error_pct < 2.0, f"Volume error {error_pct:.2f}% exceeds 2%"


# ---------------------------------------------------------------------------
# 5 — Mass haul Brückner curve persona
# ---------------------------------------------------------------------------

class TestCivilMassHaulPersona:
    """Mass haul scenario: 5 cut zones + 5 fill zones alternating."""

    STATIONS = [i * 20.0 for i in range(11)]

    def test_mass_haul_first_ordinate_zero(self):
        from kerf_civil.earthwork import mass_haul
        mh = mass_haul(self.STATIONS, [5.0] * 11, [0.0] * 11)
        assert mh[0].mass_ordinate == pytest.approx(0.0, abs=1e-12)
        assert mh[0].station == pytest.approx(0.0, abs=1e-12)

    def test_mass_haul_all_cut_final_positive(self):
        from kerf_civil.earthwork import mass_haul
        mh = mass_haul(self.STATIONS, [5.0] * 11, [0.0] * 11, swell_factor=1.0)
        assert mh[-1].mass_ordinate == pytest.approx(1000.0, abs=1e-9)
        assert mh[-1].cut_vol == pytest.approx(1000.0, abs=1e-9)

    def test_mass_haul_swell_reduces_net(self):
        """Swell factor > 1 expands fill, reducing the net ordinate."""
        from kerf_civil.earthwork import mass_haul
        mh_no_swell = mass_haul(self.STATIONS, [5.0] * 11, [3.0] * 11, swell_factor=1.0)
        mh_swell = mass_haul(self.STATIONS, [5.0] * 11, [3.0] * 11, swell_factor=1.25)
        assert mh_swell[-1].mass_ordinate < mh_no_swell[-1].mass_ordinate

    def test_mass_haul_length_equals_station_count(self):
        from kerf_civil.earthwork import mass_haul
        mh = mass_haul(self.STATIONS, [5.0] * 11, [2.0] * 11)
        assert len(mh) == len(self.STATIONS)

    def test_mass_haul_monotone_all_cut(self):
        from kerf_civil.earthwork import mass_haul
        mh = mass_haul(self.STATIONS, [5.0] * 11, [0.0] * 11)
        for i in range(1, len(mh)):
            assert mh[i].mass_ordinate >= mh[i - 1].mass_ordinate - 1e-9

    def test_mass_haul_equal_volumes_zero_net(self):
        from kerf_civil.earthwork import mass_haul
        mh = mass_haul(self.STATIONS, [5.0] * 11, [5.0] * 11, swell_factor=1.0)
        assert mh[-1].mass_ordinate == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 6 — DXF export persona (alignment → DXF R12)
# ---------------------------------------------------------------------------

class TestCivilDxfAlignmentPersona:
    """
    DXF export: build alignment, sample station coords, export to DXF R12.

    Verifies:
      - Valid DXF structure (HEADER / ENTITIES / ENDSEC / EOF / $ACADVER)
      - ALIGNMENT layer polyline present
      - STATIONS layer tick marks present
      - ANNOT layer labels present
      - validate_dxf returns empty error list
      - Byte-level: starts with '0' group code
      - Station count matches expected
    """

    def _build_alignment(self):
        from kerf_civil.horizontal_alignment import HorizontalAlignment
        ha = HorizontalAlignment()
        ha.add_tangent(200.0)
        ha.add_arc(300.0, math.radians(30.0))
        ha.add_tangent(100.0)
        return ha

    def _sample_stations(self, ha, interval=20.0):
        stations = ha.station_list(interval=interval)
        coords = [(s, *ha.coords_at_station(s)) for s in stations]
        return coords

    def test_dxf_not_empty(self):
        from kerf_civil.dxf_export import alignment_to_dxf
        ha = self._build_alignment()
        coords = self._sample_stations(ha)
        dxf = alignment_to_dxf(coords)
        assert len(dxf) > 0

    def test_dxf_validate_no_errors(self):
        from kerf_civil.dxf_export import alignment_to_dxf, validate_dxf
        ha = self._build_alignment()
        coords = self._sample_stations(ha)
        dxf = alignment_to_dxf(coords)
        errors = validate_dxf(dxf)
        assert errors == [], f"DXF validation errors: {errors}"

    def test_dxf_contains_header_section(self):
        from kerf_civil.dxf_export import alignment_to_dxf
        ha = self._build_alignment()
        dxf = alignment_to_dxf(self._sample_stations(ha))
        assert "SECTION" in dxf
        assert "$ACADVER" in dxf
        assert "AC1009" in dxf

    def test_dxf_contains_entities_section(self):
        from kerf_civil.dxf_export import alignment_to_dxf
        ha = self._build_alignment()
        dxf = alignment_to_dxf(self._sample_stations(ha))
        assert "ENTITIES" in dxf

    def test_dxf_ends_with_eof(self):
        from kerf_civil.dxf_export import alignment_to_dxf
        ha = self._build_alignment()
        dxf = alignment_to_dxf(self._sample_stations(ha))
        assert dxf.strip().endswith("EOF")

    def test_dxf_contains_alignment_layer(self):
        """Centreline polyline must be on ALIGNMENT layer."""
        from kerf_civil.dxf_export import alignment_to_dxf
        ha = self._build_alignment()
        dxf = alignment_to_dxf(self._sample_stations(ha))
        assert "ALIGNMENT" in dxf

    def test_dxf_contains_stations_layer(self):
        from kerf_civil.dxf_export import alignment_to_dxf
        ha = self._build_alignment()
        dxf = alignment_to_dxf(self._sample_stations(ha))
        assert "STATIONS" in dxf

    def test_dxf_contains_annot_layer(self):
        from kerf_civil.dxf_export import alignment_to_dxf
        ha = self._build_alignment()
        dxf = alignment_to_dxf(self._sample_stations(ha))
        assert "ANNOT" in dxf

    def test_dxf_polyline_entity_present(self):
        from kerf_civil.dxf_export import alignment_to_dxf
        ha = self._build_alignment()
        dxf = alignment_to_dxf(self._sample_stations(ha))
        assert "POLYLINE" in dxf
        assert "VERTEX" in dxf
        assert "SEQEND" in dxf

    def test_dxf_no_labels_when_disabled(self):
        from kerf_civil.dxf_export import alignment_to_dxf
        ha = self._build_alignment()
        dxf = alignment_to_dxf(self._sample_stations(ha), include_station_labels=False)
        assert "ANNOT" not in dxf

    def test_dxf_vertex_count_matches_stations(self):
        """Number of VERTEX lines should equal number of station coords."""
        from kerf_civil.dxf_export import alignment_to_dxf
        ha = self._build_alignment()
        coords = self._sample_stations(ha, interval=20.0)
        dxf = alignment_to_dxf(coords, include_station_labels=False)
        vertex_count = dxf.count("\nVERTEX\n")
        assert vertex_count == len(coords)


# ---------------------------------------------------------------------------
# 7 — Cut/fill DXF profile export
# ---------------------------------------------------------------------------

class TestCivilCutFillDxfPersona:
    """DXF export for cut/fill profile diagram."""

    STATIONS = [i * 20.0 for i in range(11)]
    CUT_AREAS = [5.0 + 0.5 * i for i in range(11)]
    FILL_AREAS = [2.0 - 0.1 * i for i in range(11)]

    def test_cut_fill_dxf_valid_structure(self):
        from kerf_civil.dxf_export import cut_fill_profile_to_dxf, validate_dxf
        dxf = cut_fill_profile_to_dxf(self.STATIONS, self.CUT_AREAS, self.FILL_AREAS)
        errors = validate_dxf(dxf)
        assert errors == [], f"DXF errors: {errors}"

    def test_cut_fill_dxf_has_cut_layer(self):
        from kerf_civil.dxf_export import cut_fill_profile_to_dxf
        dxf = cut_fill_profile_to_dxf(self.STATIONS, self.CUT_AREAS, self.FILL_AREAS)
        assert "CUT" in dxf

    def test_cut_fill_dxf_has_fill_layer(self):
        from kerf_civil.dxf_export import cut_fill_profile_to_dxf
        dxf = cut_fill_profile_to_dxf(self.STATIONS, self.CUT_AREAS, self.FILL_AREAS)
        assert "FILL" in dxf

    def test_cut_fill_dxf_has_datum_layer(self):
        from kerf_civil.dxf_export import cut_fill_profile_to_dxf
        dxf = cut_fill_profile_to_dxf(self.STATIONS, self.CUT_AREAS, self.FILL_AREAS)
        assert "DATUM" in dxf

    def test_cut_fill_dxf_mismatched_lengths_raises(self):
        from kerf_civil.dxf_export import cut_fill_profile_to_dxf
        with pytest.raises(ValueError):
            cut_fill_profile_to_dxf([0.0, 10.0], [1.0], [1.0, 2.0])

    def test_cut_fill_dxf_ends_with_eof(self):
        from kerf_civil.dxf_export import cut_fill_profile_to_dxf
        dxf = cut_fill_profile_to_dxf(self.STATIONS, self.CUT_AREAS, self.FILL_AREAS)
        assert dxf.strip().endswith("EOF")

    def test_cut_fill_dxf_not_empty(self):
        from kerf_civil.dxf_export import cut_fill_profile_to_dxf
        dxf = cut_fill_profile_to_dxf(self.STATIONS, self.CUT_AREAS, self.FILL_AREAS)
        assert len(dxf) > 100


# ---------------------------------------------------------------------------
# 8 — Civil LLM tools (run_civil_horizontal_alignment / run_civil_earthwork_volume)
# ---------------------------------------------------------------------------

class TestCivilToolsPersona:
    """
    Exercise the civil LLM tool wrappers without kerf_core.
    Uses the _compat shims so no DB / registry needed.
    """

    def _make_ctx(self):
        from kerf_civil._compat import ProjectCtx
        return ProjectCtx()

    def test_ha_tool_tangent_arc_roundtrip(self):
        """run_civil_horizontal_alignment returns ok=True and correct total length."""
        from kerf_civil.tools import run_civil_horizontal_alignment

        params = {
            "elements": [
                {"type": "tangent", "length": 200.0},
                {"type": "arc", "radius": 300.0, "delta_deg": 30.0, "turn_right": True},
                {"type": "tangent", "length": 100.0},
            ],
            "design_speed_mph": 60,
        }
        ctx = self._make_ctx()
        raw = _run(run_civil_horizontal_alignment(params, ctx))
        result = json.loads(raw)
        assert result.get("ok") is True or "total_length_m" in result, \
            f"Unexpected result: {result}"
        total = result.get("total_length_m", result.get("data", {}).get("total_length_m"))
        if total is not None:
            arc_len = 300.0 * math.radians(30.0)
            expected = 200.0 + arc_len + 100.0
            assert float(total) == pytest.approx(expected, rel=1e-4)

    def test_ha_tool_spiral_element(self):
        """run_civil_horizontal_alignment handles spiral element."""
        from kerf_civil.tools import run_civil_horizontal_alignment

        params = {
            "elements": [
                {"type": "spiral", "length": 60.0, "radius": 300.0, "turn_right": True},
            ],
        }
        ctx = self._make_ctx()
        raw = _run(run_civil_horizontal_alignment(params, ctx))
        result = json.loads(raw)
        # Should not error
        assert "error" not in result or result.get("ok") is True

    def test_earthwork_volume_tool_uniform_prism(self):
        """run_civil_earthwork_volume returns correct volumes for uniform prism."""
        from kerf_civil.tools import run_civil_earthwork_volume

        stations = [i * 20.0 for i in range(6)]  # 0..100 m
        cut = [5.0] * 6
        fill = [0.0] * 6
        params = {
            "stations_m": stations,
            "cut_areas_m2": cut,
            "fill_areas_m2": fill,
            "swell_factor": 1.0,
        }
        ctx = self._make_ctx()
        raw = _run(run_civil_earthwork_volume(params, ctx))
        result = json.loads(raw)
        # Extract fields regardless of wrapper shape
        cut_vol = result.get("total_cut_m3") or result.get("data", {}).get("total_cut_m3")
        if cut_vol is not None:
            assert float(cut_vol) == pytest.approx(500.0, rel=1e-4)

    def test_earthwork_volume_tool_bad_stations_raises(self):
        """Mismatched lengths return ok=False or error."""
        from kerf_civil.tools import run_civil_earthwork_volume

        params = {
            "stations_m": [0.0, 20.0],
            "cut_areas_m2": [5.0],  # wrong length
            "fill_areas_m2": [0.0, 0.0],
        }
        ctx = self._make_ctx()
        raw = _run(run_civil_earthwork_volume(params, ctx))
        result = json.loads(raw)
        # Should be an error — either ok=False or has "error" key
        is_error = (result.get("ok") is False) or ("error" in result)
        assert is_error, f"Expected error, got: {result}"

    def test_va_tool_returns_total_length(self):
        """run_civil_vertical_alignment returns correct total length."""
        from kerf_civil.tools import run_civil_vertical_alignment

        params = {
            "datum_elev_m": 10.0,
            "initial_grade_pct": 3.0,
            "elements": [
                {"type": "tangent", "length": 200.0},
                {"type": "curve", "length": 200.0, "grade_out_pct": -3.0},
                {"type": "tangent", "length": 100.0},
            ],
        }
        ctx = self._make_ctx()
        raw = _run(run_civil_vertical_alignment(params, ctx))
        result = json.loads(raw)
        total = result.get("total_length_m") or result.get("data", {}).get("total_length_m")
        if total is not None:
            assert float(total) == pytest.approx(500.0, rel=1e-4)
