"""
Tests for kerf_aero.sizing.mission_profile.

All expected values are derived analytically from the Breguet equations and
Raymer's weight-fraction defaults (Table 6.1).

References
----------
[R6.1]  Raymer D. P., "Aircraft Design: A Conceptual Approach," 6th ed. (2018),
        Table 6.1 — Typical mission-segment weight fractions.
[R6.2]  Raymer, §6.2 — Mission fuel-fraction derivation.
"""

from __future__ import annotations

import math
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _PKG_SRC not in sys.path:
    sys.path.insert(0, _PKG_SRC)

import pytest

from kerf_aero.sizing.mission_profile import (
    MissionProfile,
    MissionSegment,
    SegmentKind,
)


# ---------------------------------------------------------------------------
# Segment fraction tests
# ---------------------------------------------------------------------------


class TestSegmentFraction:
    """Per-segment weight-fraction computation."""

    def test_warmup_takeoff_default(self):
        seg = MissionSegment(kind=SegmentKind.WARMUP_TAKEOFF)
        assert seg.compute_fraction() == pytest.approx(0.970, abs=1e-9)

    def test_climb_default(self):
        seg = MissionSegment(kind=SegmentKind.CLIMB)
        assert seg.compute_fraction() == pytest.approx(0.985, abs=1e-9)

    def test_descent_default(self):
        seg = MissionSegment(kind=SegmentKind.DESCENT)
        assert seg.compute_fraction() == pytest.approx(0.990, abs=1e-9)

    def test_landing_default(self):
        seg = MissionSegment(kind=SegmentKind.LANDING)
        assert seg.compute_fraction() == pytest.approx(0.995, abs=1e-9)

    def test_fixed_fraction_override(self):
        seg = MissionSegment(kind=SegmentKind.WARMUP_TAKEOFF, weight_fraction=0.950)
        assert seg.compute_fraction() == pytest.approx(0.950, abs=1e-9)

    def test_fixed_fraction_segment_kind(self):
        seg = MissionSegment(kind=SegmentKind.FIXED_FRACTION, weight_fraction=0.888)
        assert seg.compute_fraction() == pytest.approx(0.888, abs=1e-9)

    def test_fixed_fraction_required_for_unknown_kind(self):
        seg = MissionSegment(kind=SegmentKind.FIXED_FRACTION)
        with pytest.raises(ValueError, match="weight_fraction"):
            seg.compute_fraction()

    def test_cruise_breguet(self):
        """Breguet cruise: W_end/W_start = exp(-R·c_j / (V·L/D))."""
        R, V, ld, cj = 500.0, 120.0, 10.0, 0.45
        expected = math.exp(-R * cj / (V * ld))
        seg = MissionSegment(
            kind=SegmentKind.CRUISE,
            range_nm=R,
            velocity_ktas=V,
            ld_ratio=ld,
            tsfc=cj,
        )
        assert seg.compute_fraction() == pytest.approx(expected, rel=1e-9)

    def test_cruise_fraction_less_than_one(self):
        """A cruise segment always consumes fuel → fraction < 1."""
        seg = MissionSegment(
            kind=SegmentKind.CRUISE,
            range_nm=1000.0,
            velocity_ktas=200.0,
            ld_ratio=15.0,
            tsfc=0.5,
        )
        assert seg.compute_fraction() < 1.0
        assert seg.compute_fraction() > 0.0

    def test_cruise_missing_velocity_raises(self):
        seg = MissionSegment(
            kind=SegmentKind.CRUISE,
            range_nm=500.0,
            velocity_ktas=0.0,
            ld_ratio=10.0,
            tsfc=0.45,
        )
        with pytest.raises(ValueError, match="CRUISE"):
            seg.compute_fraction()

    def test_loiter_breguet(self):
        """Breguet endurance: W_end/W_start = exp(-E·c_j / (L/D))."""
        E, ld, cj = 1.0, 12.0, 0.5
        expected = math.exp(-E * cj / ld)
        seg = MissionSegment(
            kind=SegmentKind.LOITER,
            endurance_hr=E,
            ld_ratio=ld,
            tsfc=cj,
        )
        assert seg.compute_fraction() == pytest.approx(expected, rel=1e-9)

    def test_loiter_missing_endurance_raises(self):
        seg = MissionSegment(
            kind=SegmentKind.LOITER,
            endurance_hr=0.0,
            ld_ratio=12.0,
            tsfc=0.5,
        )
        with pytest.raises(ValueError, match="LOITER"):
            seg.compute_fraction()


# ---------------------------------------------------------------------------
# Mission fuel fraction tests
# ---------------------------------------------------------------------------


class TestMissionFuelFraction:
    """Aggregate fuel-fraction calculation for a complete mission."""

    def test_product_of_fractions(self):
        """mission_fuel_fraction() is the product of all per-segment fractions."""
        profile = MissionProfile(
            segments=[
                MissionSegment(kind=SegmentKind.WARMUP_TAKEOFF),   # 0.970
                MissionSegment(kind=SegmentKind.CLIMB),             # 0.985
                MissionSegment(kind=SegmentKind.DESCENT),           # 0.990
                MissionSegment(kind=SegmentKind.LANDING),           # 0.995
            ]
        )
        expected_mff = 0.970 * 0.985 * 0.990 * 0.995
        assert profile.mission_fuel_fraction() == pytest.approx(expected_mff, rel=1e-9)

    def test_fuel_fraction_includes_trapped_fuel(self):
        """fuel_fraction() = (1 - mff) * (1 + trapped_fuel_factor)."""
        profile = MissionProfile(
            segments=[
                MissionSegment(kind=SegmentKind.WARMUP_TAKEOFF),
                MissionSegment(kind=SegmentKind.CLIMB),
                MissionSegment(kind=SegmentKind.DESCENT),
                MissionSegment(kind=SegmentKind.LANDING),
            ],
            trapped_fuel_factor=0.06,
        )
        mff = profile.mission_fuel_fraction()
        expected = (1.0 - mff) * 1.06
        assert profile.fuel_fraction() == pytest.approx(expected, rel=1e-9)

    def test_fuel_fraction_zero_trapped(self):
        profile = MissionProfile(
            segments=[
                MissionSegment(kind=SegmentKind.WARMUP_TAKEOFF),
                MissionSegment(kind=SegmentKind.LANDING),
            ],
            trapped_fuel_factor=0.0,
        )
        mff = 0.970 * 0.995
        assert profile.fuel_fraction() == pytest.approx(1.0 - mff, rel=1e-9)

    def test_single_cruise_fuel_fraction(self):
        """A cruise-only mission: fuel fraction matches Breguet directly."""
        R, V, ld, cj = 1000.0, 200.0, 15.0, 0.5
        profile = MissionProfile(
            segments=[
                MissionSegment(
                    kind=SegmentKind.CRUISE,
                    range_nm=R,
                    velocity_ktas=V,
                    ld_ratio=ld,
                    tsfc=cj,
                )
            ],
            trapped_fuel_factor=0.0,
        )
        expected_frac = 1.0 - math.exp(-R * cj / (V * ld))
        assert profile.fuel_fraction() == pytest.approx(expected_frac, rel=1e-9)

    def test_breguet_range_fuel_fraction_round_trip(self):
        """
        W_f/W_0 = 0.4 → W_end/W_start = 0.6 → R = (V·L/D/c_j)·ln(1/0.6).

        This verifies the closed-form Breguet equation is correctly encoded.
        Closed-form R = (200 · 15 / 0.5) · ln(10/6) ≈ 3065 nm.
        """
        V, ld, cj = 200.0, 15.0, 0.5
        W_end_over_W_start = 0.6  # W_f/W_0 = 0.4

        # Analytically compute range that gives this fraction
        R_analytical = (V * ld / cj) * math.log(1.0 / W_end_over_W_start)
        assert R_analytical == pytest.approx(3065.1, abs=1.0)

        # Verify that our Breguet segment produces the expected fraction
        seg = MissionSegment(
            kind=SegmentKind.CRUISE,
            range_nm=R_analytical,
            velocity_ktas=V,
            ld_ratio=ld,
            tsfc=cj,
        )
        assert seg.compute_fraction() == pytest.approx(W_end_over_W_start, rel=1e-6)

    def test_empty_mission_mff_is_one(self):
        profile = MissionProfile(segments=[])
        assert profile.mission_fuel_fraction() == pytest.approx(1.0, abs=1e-9)

    def test_empty_mission_fuel_fraction_zero_trapped(self):
        """No segments, no fuel burned."""
        profile = MissionProfile(segments=[], trapped_fuel_factor=0.0)
        assert profile.fuel_fraction() == pytest.approx(0.0, abs=1e-9)

    def test_simple_cruise_factory_ga(self):
        """Factory produces the correct number of segments for a GA cruise."""
        p = MissionProfile.simple_cruise(500, 120, 10, 0.45, include_reserves=False)
        assert len(p.segments) == 5  # warmup, climb, cruise, descent, landing

    def test_simple_cruise_factory_with_reserves(self):
        p = MissionProfile.simple_cruise(500, 120, 10, 0.45, include_reserves=True)
        # warmup, climb, cruise, descent, landing, loiter
        assert len(p.segments) == 6
        assert p.segments[-1].kind == SegmentKind.LOITER

    def test_fuel_fraction_positive_and_less_than_one(self):
        """Sanity: total fuel fraction is physically plausible."""
        p = MissionProfile.simple_cruise(1000, 450, 17, 0.6)
        ff = p.fuel_fraction()
        assert 0.0 < ff < 1.0
