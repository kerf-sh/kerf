"""
Tests for kerf_civil.superelevation — AASHTO runoff transitions and
multi-template corridor cross-sections.

Key validation oracles
----------------------
1. AASHTO Table 3-21 / Exhibit 3-20: design speed 50 mph, e=6%, 12-ft lane
   → relative gradient Δ = 0.50 % → L_r = (12 * 1 * 0.06) / 0.005 = 144 ft
   AASHTO published range for this case: ~140-180 ft. ✓

2. Tangent runout (normal crown = 2 %):
   T_R = L_r * (e_NC / e_full) = 144 * (2/6) = 48 ft.

3. Divided highway template — 22 ft median (6.7 m), 2×12 ft lanes each dir
   (2 × 3.66 m = 7.31 m each side), shoulder 3 m outer:
   Expected half-width ≈ 6.7/2 + 7.31 + shoulder = 3.35 + 7.31 + 3.0 = 13.66 m
   Total width ≈ 27.3 m.

4. Profile: at station inside curve e(s) = e_full; at station far on tangent e(s) = 0.

5. Reverse crown template: right edge elevation < CL elevation (slopes down).

6. corridor_cross_section_at: with positive e, right side lowers relative to template.
"""

from __future__ import annotations

import math
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ft_to_m(ft: float) -> float:
    return ft / 3.28084


def m_to_ft(m: float) -> float:
    return m * 3.28084


# ---------------------------------------------------------------------------
# AASHTO runoff length
# ---------------------------------------------------------------------------

class TestRunoffLength:
    """Oracle 1: L_r = (w * n * e_d) / Δ for design speed 50 mph."""

    def test_50mph_6pct_12ft(self):
        from kerf_civil.superelevation import runoff_length_ft
        # Δ at 50 mph = 0.50%, e=6%, w=12ft, n=1
        L_r = runoff_length_ft(50.0, 6.0, 12.0, 1)
        # Expected: 12 * 0.06 / 0.005 = 144 ft
        assert L_r == pytest.approx(144.0, abs=1.0)

    def test_aashto_range_50mph(self):
        """L_r for 50 mph, 6%, 12 ft should be in AASHTO 140-180 ft range."""
        from kerf_civil.superelevation import runoff_length_ft
        L_r = runoff_length_ft(50.0, 6.0, 12.0, 1)
        assert 140.0 <= L_r <= 180.0

    def test_higher_speed_longer_runoff(self):
        """Higher speed → smaller Δ → longer runoff."""
        from kerf_civil.superelevation import runoff_length_ft
        L_r_50 = runoff_length_ft(50.0, 6.0, 12.0, 1)
        L_r_70 = runoff_length_ft(70.0, 6.0, 12.0, 1)
        assert L_r_70 > L_r_50

    def test_higher_e_longer_runoff(self):
        """Higher superelevation → proportionally longer runoff."""
        from kerf_civil.superelevation import runoff_length_ft
        L_r_4 = runoff_length_ft(50.0, 4.0, 12.0, 1)
        L_r_8 = runoff_length_ft(50.0, 8.0, 12.0, 1)
        assert L_r_8 == pytest.approx(2.0 * L_r_4, rel=1e-6)

    def test_two_lanes_double_length(self):
        """n_lanes=2 doubles the runoff length."""
        from kerf_civil.superelevation import runoff_length_ft
        L_1 = runoff_length_ft(50.0, 6.0, 12.0, 1)
        L_2 = runoff_length_ft(50.0, 6.0, 12.0, 2)
        assert L_2 == pytest.approx(2.0 * L_1, rel=1e-6)


# ---------------------------------------------------------------------------
# Tangent runout
# ---------------------------------------------------------------------------

class TestTangentRunout:
    """Oracle 2: T_R = L_r * (e_NC / e_full)."""

    def test_50mph_6pct(self):
        from kerf_civil.superelevation import runoff_length_ft, tangent_runout_length_ft
        L_r = runoff_length_ft(50.0, 6.0, 12.0, 1)
        T_R = tangent_runout_length_ft(6.0, 2.0, L_r)
        # = 144 * (2/6) = 48 ft
        assert T_R == pytest.approx(48.0, abs=1.0)

    def test_proportional_to_crown(self):
        from kerf_civil.superelevation import runoff_length_ft, tangent_runout_length_ft
        L_r = runoff_length_ft(60.0, 8.0, 12.0, 1)
        T_R2 = tangent_runout_length_ft(8.0, 2.0, L_r)
        T_R4 = tangent_runout_length_ft(8.0, 4.0, L_r)
        assert T_R4 == pytest.approx(2.0 * T_R2, rel=1e-6)

    def test_aashto_relative_gradient_50mph(self):
        from kerf_civil.superelevation import aashto_relative_gradient
        delta = aashto_relative_gradient(50.0)
        assert delta == pytest.approx(0.50, abs=0.01)

    def test_aashto_relative_gradient_60mph(self):
        from kerf_civil.superelevation import aashto_relative_gradient
        delta = aashto_relative_gradient(60.0)
        assert delta == pytest.approx(0.45, abs=0.01)


# ---------------------------------------------------------------------------
# Superelevation profile
# ---------------------------------------------------------------------------

class TestSuperelevationProfile:
    """Oracle 4: profile correctness at key stations."""

    def _get_e(self, station, curve_start=500.0, curve_end=1000.0,
                e_full=0.06, speed_kph=80.0):
        from kerf_civil.superelevation import superelevation_profile_at_station
        return superelevation_profile_at_station(
            station, curve_start, curve_end, e_full, speed_kph,
            lane_width_m=3.65, n_lanes=1,
        )

    def test_full_super_at_mid_curve(self):
        """Middle of a long curve should reach e_full."""
        e = self._get_e(750.0)
        assert e == pytest.approx(0.06, abs=1e-3)

    def test_zero_on_far_tangent(self):
        """Far upstream tangent: e = 0."""
        e = self._get_e(0.0)
        assert e == pytest.approx(0.0, abs=1e-9)

    def test_zero_on_far_departure(self):
        """Far downstream tangent: e = 0."""
        e = self._get_e(2000.0)
        assert e == pytest.approx(0.0, abs=1e-9)

    def test_monotone_approach(self):
        """e increases monotonically through approach transition."""
        from kerf_civil.superelevation import (
            superelevation_profile_at_station,
            runoff_length_ft,
            tangent_runout_length_ft,
            aashto_relative_gradient,
        )
        cs, ce = 500.0, 1000.0
        speed_kph = 80.0
        e_full = 0.06
        speed_mph = speed_kph / 1.60934
        L_r_ft = runoff_length_ft(speed_mph, e_full * 100, 3.65 * 3.28084, 1)
        T_R_ft = tangent_runout_length_ft(e_full * 100, 2.0, L_r_ft)
        L_r = L_r_ft / 3.28084
        T_R = T_R_ft / 3.28084

        approach_start = cs - (2.0 / 3.0) * L_r - T_R
        samples = [approach_start + i * (cs - approach_start) / 20 for i in range(21)]
        e_vals = [superelevation_profile_at_station(s, cs, ce, e_full, speed_kph) for s in samples]
        # Should be non-decreasing
        for i in range(len(e_vals) - 1):
            assert e_vals[i] <= e_vals[i + 1] + 1e-9

    def test_e_full_clamped(self):
        """e_full is clamped to e_max=8%."""
        e = self._get_e(750.0, e_full=0.15)  # 15% -> clamped to 8%
        assert e <= 0.08 + 1e-6

    def test_runoff_ft_validation_oracle(self):
        """
        AASHTO Table 3-21 oracle: 50 mph, e=6%, 12-ft lane → ~144 ft runoff.
        This validates the published AASHTO design table range (140-180 ft).
        """
        from kerf_civil.superelevation import runoff_length_ft
        L_r = runoff_length_ft(50.0, 6.0, 12.0, 1)
        # AASHTO range for this combination: 140-180 ft
        assert 140.0 <= L_r <= 180.0, f"L_r={L_r} ft outside AASHTO range [140, 180]"


# ---------------------------------------------------------------------------
# Divided highway template
# ---------------------------------------------------------------------------

class TestDividedHighwayTemplate:
    """Oracle 3: width spans correctly for 22 ft median + 2×12 ft lanes."""

    def test_total_width_ft_equiv(self):
        """
        22 ft (6.706 m) median, 2×12 ft (2×3.658 m) lanes each dir,
        3m inner shoulder, 3m outer shoulder.
        Half-width = 6.706/2 + 3.0 + 2×3.658 + 3.0 = 3.353 + 3.0 + 7.315 + 3.0 = 16.668 m
        Total = 33.34 m (approx).
        """
        from kerf_civil.superelevation import divided_highway_template
        median_m = 22 * 0.3048  # 22 ft → m
        lane_m = 12 * 0.3048   # 12 ft → m
        pts = divided_highway_template(
            median_width=median_m,
            n_lanes_each_dir=2,
            lane_width=lane_m,
            shoulder_inner=3.0,
            shoulder_outer=3.0,
        )
        xs = [p.x_offset for p in pts]
        total_width = max(xs) - min(xs)
        # median/2 + inner_shl + 2 lanes + outer_shl on each side × 2
        expected = median_m + 2 * (3.0 + 2 * lane_m + 3.0)
        assert total_width == pytest.approx(expected, abs=0.05)

    def test_has_cl_point(self):
        from kerf_civil.superelevation import divided_highway_template
        pts = divided_highway_template()
        codes = [p.code for p in pts]
        assert "CL" in codes

    def test_symmetric_offsets(self):
        """Left and right sides should be symmetric in x."""
        from kerf_civil.superelevation import divided_highway_template
        pts = divided_highway_template()
        xs = [p.x_offset for p in pts]
        assert abs(min(xs)) == pytest.approx(max(xs), abs=1e-9)

    def test_right_side_lower_than_cl(self):
        """Lanes fall away from centreline; right side of road is below CL elevation."""
        from kerf_civil.superelevation import divided_highway_template
        pts = divided_highway_template(crown_slope_pct=2.0)
        outer_right = next(p for p in reversed(pts) if "SHOULDER_OUT" in p.code or "DAYLIGHT" in p.code)
        assert outer_right.y_offset < 0.0

    def test_ordered_left_to_right(self):
        """Points must be ordered by increasing x_offset."""
        from kerf_civil.superelevation import divided_highway_template
        pts = divided_highway_template()
        xs = [p.x_offset for p in pts]
        assert xs == sorted(xs)


# ---------------------------------------------------------------------------
# Reverse crown template
# ---------------------------------------------------------------------------

class TestReverseCrownTemplate:
    """Oracle 5: right edge elevation < CL for positive super."""

    def test_right_edge_below_cl(self):
        from kerf_civil.superelevation import reverse_crown_template
        pts = reverse_crown_template(n_lanes=4, lane_width=3.65, e_pct=6.0)
        right_edge = next(p for p in pts if "EDGE_LANE_R" in p.code)
        assert right_edge.y_offset < 0.0

    def test_left_edge_above_cl(self):
        """For full super (right-hand curve), left side is high side."""
        from kerf_civil.superelevation import reverse_crown_template
        pts = reverse_crown_template(n_lanes=4, lane_width=3.65, e_pct=6.0)
        left_edge = next(p for p in pts if "EDGE_LANE_L" in p.code)
        assert left_edge.y_offset > 0.0

    def test_uniform_slope(self):
        """All lane points should lie on a straight slope line."""
        from kerf_civil.superelevation import reverse_crown_template
        e = 0.06
        pts = reverse_crown_template(n_lanes=4, lane_width=3.65, e_pct=e * 100)
        # CL at (0, 0); each point should satisfy y = -e * x
        for p in pts:
            if p.code in ("CL", "SHOULDER_L", "SHOULDER_R"):
                continue
            assert p.y_offset == pytest.approx(-e * p.x_offset, abs=1e-6)


# ---------------------------------------------------------------------------
# Urban curb-and-gutter template
# ---------------------------------------------------------------------------

class TestUrbanCurbGutterTemplate:
    def test_has_gutter_and_sidewalk(self):
        from kerf_civil.superelevation import urban_curb_gutter_template
        pts = urban_curb_gutter_template()
        codes = [p.code for p in pts]
        assert any("GUTTER" in c for c in codes)
        assert any("SIDEWALK" in c for c in codes)

    def test_sidewalk_outer_further_than_gutter(self):
        """Sidewalk outer edge must be further from CL than gutter."""
        from kerf_civil.superelevation import urban_curb_gutter_template
        pts = urban_curb_gutter_template()
        right_pts = {p.code: p for p in pts if "_R" in p.code}
        gutter_x = right_pts["GUTTER_R"].x_offset
        sw_outer_x = right_pts["SIDEWALK_OUTER_R"].x_offset
        assert sw_outer_x > gutter_x

    def test_cl_at_zero(self):
        from kerf_civil.superelevation import urban_curb_gutter_template
        pts = urban_curb_gutter_template()
        cl = next(p for p in pts if p.code == "CL")
        assert cl.x_offset == pytest.approx(0.0, abs=1e-9)
        assert cl.y_offset == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# corridor_cross_section_at
# ---------------------------------------------------------------------------

class TestCorridorCrossSectionAt:
    """Oracle 6: superelevation blending adjusts elevations correctly."""

    def test_zero_e_preserves_template(self):
        """With e=0, cross-section matches template y_offsets shifted by cl_elev."""
        from kerf_civil.superelevation import divided_highway_template, corridor_cross_section_at
        tmpl = divided_highway_template()
        cl_elev = 10.0
        blended = corridor_cross_section_at(tmpl, station=100.0, e_at_station=0.0, cl_elevation=cl_elev)
        for orig, new in zip(tmpl, blended):
            if orig.code == "CL":
                assert new.y_offset == pytest.approx(cl_elev, abs=1e-9)
            else:
                assert new.y_offset == pytest.approx(cl_elev + orig.y_offset, abs=1e-6)

    def test_positive_e_lowers_right(self):
        """Positive superelevation should lower right-side points."""
        from kerf_civil.superelevation import divided_highway_template, corridor_cross_section_at
        tmpl = divided_highway_template()
        blended_0 = corridor_cross_section_at(tmpl, 0, 0.0, 0.0)
        blended_e = corridor_cross_section_at(tmpl, 0, 0.06, 0.0)
        # Find a right-side point with positive x_offset
        for b0, be in zip(blended_0, blended_e):
            if b0.x_offset > 1.0 and "CL" not in b0.code:
                assert be.y_offset < b0.y_offset
                break

    def test_positive_e_raises_left(self):
        """Positive superelevation should raise left-side points."""
        from kerf_civil.superelevation import divided_highway_template, corridor_cross_section_at
        tmpl = divided_highway_template()
        blended_0 = corridor_cross_section_at(tmpl, 0, 0.0, 0.0)
        blended_e = corridor_cross_section_at(tmpl, 0, 0.06, 0.0)
        for b0, be in zip(blended_0, blended_e):
            if b0.x_offset < -1.0 and "CL" not in b0.code:
                assert be.y_offset > b0.y_offset
                break

    def test_same_point_count(self):
        """Blended section must have same number of points as template."""
        from kerf_civil.superelevation import reverse_crown_template, corridor_cross_section_at
        tmpl = reverse_crown_template()
        blended = corridor_cross_section_at(tmpl, 100.0, 0.06, 5.0)
        assert len(blended) == len(tmpl)

    def test_e_rotation_formula(self):
        """y_new = cl_elev + y_orig + (-e * x_offset) for non-CL points."""
        from kerf_civil.superelevation import reverse_crown_template, corridor_cross_section_at
        tmpl = reverse_crown_template(n_lanes=4, lane_width=3.65, e_pct=0.0)
        e = 0.04
        cl = 5.0
        blended = corridor_cross_section_at(tmpl, 0.0, e, cl)
        for orig, new in zip(tmpl, blended):
            if orig.code != "CL":
                expected = cl + orig.y_offset + (-e * orig.x_offset)
                assert new.y_offset == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# Integration: LLM tool handlers
# ---------------------------------------------------------------------------

class TestLLMTools:
    """Smoke-test the async tool handlers."""

    @pytest.mark.asyncio
    async def test_superelevation_profile_tool(self):
        import json
        from kerf_civil.superelevation import (
            run_civil_superelevation_profile,
        )
        from kerf_civil._compat import ProjectCtx

        result = await run_civil_superelevation_profile(
            {
                "curve_start_m": 500.0,
                "curve_end_m": 1000.0,
                "e_full_pct": 6.0,
                "design_speed_kph": 80.0,
            },
            ProjectCtx(),
        )
        data = json.loads(result)
        assert "runoff_length_ft" in data
        assert data["runoff_length_ft"] > 0
        assert "profile" in data
        assert len(data["profile"]) > 0

    @pytest.mark.asyncio
    async def test_corridor_template_tool_divided(self):
        import json
        from kerf_civil.superelevation import run_civil_corridor_template
        from kerf_civil._compat import ProjectCtx

        result = await run_civil_corridor_template(
            {
                "template_type": "divided_highway",
                "median_width_m": 22 * 0.3048,
                "n_lanes_each_dir": 2,
                "lane_width_m": 12 * 0.3048,
            },
            ProjectCtx(),
        )
        data = json.loads(result)
        assert "points" in data
        assert data["total_width_m"] > 20.0

    @pytest.mark.asyncio
    async def test_corridor_cross_section_tool(self):
        import json
        from kerf_civil.superelevation import run_civil_corridor_cross_section
        from kerf_civil._compat import ProjectCtx

        result = await run_civil_corridor_cross_section(
            {
                "template_type": "divided_highway",
                "station_m": 750.0,
                "cl_elevation_m": 100.0,
                "e_at_station_pct": 4.0,
            },
            ProjectCtx(),
        )
        data = json.loads(result)
        assert "points" in data
        assert data["e_pct"] == pytest.approx(4.0, abs=1e-9)
