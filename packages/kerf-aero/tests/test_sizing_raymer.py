"""
Tests for kerf_aero.sizing.raymer — Raymer conceptual-sizing method.

Test cases
----------
1.  Cessna 172-class GA single: W_0 ≈ 2 400 lb  (±10 %)
2.  Boeing 737-class jet transport: W_0 ≈ 150 000 lb  (±10 %)
3.  Breguet closed-form: V=200 ktas, L/D=15, c_j=0.5/hr, W_f/W_0=0.4
    → range ≈ 3 065 nm and the inverse function is self-consistent.
4.  Unit / edge-case checks on breguet_range_fraction / breguet_range_nm.
5.  Output structure and physics plausibility checks on SizingResult.

References
----------
[R6.2]  Raymer D. P., "Aircraft Design: A Conceptual Approach," 6th ed. (2018),
        Chapter 6 — Preliminary Sizing.
[Breguet] Breguet range equation (consistent-unit form, range in nm, V in ktas,
          TSFC in /hr):  R = (V · L/D / c_j) · ln(W_start / W_end).
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

from kerf_aero.sizing.raymer import (
    RAYMER_EMPTY_WEIGHT_COEFFICIENTS,
    AircraftParams,
    breguet_range_fraction,
    breguet_range_nm,
    size_aircraft,
)
from kerf_aero.sizing.mission_profile import MissionProfile, MissionSegment, SegmentKind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cessna_172_mission() -> MissionProfile:
    """Short-range GA mission representative of a Cessna 172.

    Parameters chosen so the resulting W_0 lands near 2 400 lb:
    - 300 nm cruise at 122 ktas, L/D=10, TSFC=0.45 /hr
    - Raymer Table 6.1 fractions for all other segments
    - No loiter reserve (conservative fuel estimate)
    """
    return MissionProfile(
        segments=[
            MissionSegment(kind=SegmentKind.WARMUP_TAKEOFF),
            MissionSegment(kind=SegmentKind.CLIMB),
            MissionSegment(
                kind=SegmentKind.CRUISE,
                range_nm=300.0,
                velocity_ktas=122.0,
                ld_ratio=10.0,
                tsfc=0.45,
            ),
            MissionSegment(kind=SegmentKind.DESCENT),
            MissionSegment(kind=SegmentKind.LANDING),
        ]
    )


def _cessna_172_params() -> AircraftParams:
    """Design requirements for a Cessna 172-class single-engine piston."""
    return AircraftParams(
        payload_lb=500.0,   # 3 pax + baggage
        crew_lb=100.0,      # pilot
        wing_loading_lb_ft2=14.0,
        thrust_to_weight=0.09,
        aircraft_class="general_aviation_single",
        W0_guess_lb=2_400.0,
    )


def _boeing_737_mission() -> MissionProfile:
    """Medium-range jet transport mission representative of a Boeing 737.

    Parameters chosen so the resulting W_0 lands near 150 000 lb:
    - 2 000 nm cruise at 450 ktas, L/D=17, TSFC=0.6 /hr
    """
    return MissionProfile(
        segments=[
            MissionSegment(kind=SegmentKind.WARMUP_TAKEOFF),
            MissionSegment(kind=SegmentKind.CLIMB),
            MissionSegment(
                kind=SegmentKind.CRUISE,
                range_nm=2_000.0,
                velocity_ktas=450.0,
                ld_ratio=17.0,
                tsfc=0.6,
            ),
            MissionSegment(kind=SegmentKind.DESCENT),
            MissionSegment(kind=SegmentKind.LANDING),
        ]
    )


def _boeing_737_params() -> AircraftParams:
    """Design requirements for a Boeing 737-class narrow-body jet transport."""
    return AircraftParams(
        payload_lb=35_000.0,   # ~150 pax + bags at 230 lb/pax
        crew_lb=500.0,
        wing_loading_lb_ft2=120.0,
        thrust_to_weight=0.30,
        aircraft_class="jet_transport",
        W0_guess_lb=150_000.0,
    )


# ---------------------------------------------------------------------------
# Cessna 172-class sizing
# ---------------------------------------------------------------------------


class TestCessna172Sizing:
    """Cessna 172-class GA single: W_0 ≈ 2 400 lb ± 10 %."""

    def test_w0_within_10_percent_of_2400_lb(self):
        result = size_aircraft(_cessna_172_mission(), _cessna_172_params())
        W_0 = result["W_0"]
        assert abs(W_0 - 2_400.0) / 2_400.0 < 0.10, (
            f"W_0 = {W_0:.1f} lb; expected 2 400 ± 240 lb"
        )

    def test_weight_budget_closes(self):
        """W_0 = W_empty + W_fuel + W_payload + W_crew (within 0.1 lb rounding)."""
        params = _cessna_172_params()
        result = size_aircraft(_cessna_172_mission(), params)
        total = (
            result["W_empty"]
            + result["W_fuel"]
            + params.payload_lb
            + params.crew_lb
        )
        assert abs(total - result["W_0"]) < 1.0, (
            f"Weight budget error: {total:.1f} vs W_0={result['W_0']:.1f}"
        )

    def test_wing_area_positive(self):
        result = size_aircraft(_cessna_172_mission(), _cessna_172_params())
        assert result["wing_area"] > 0.0

    def test_wing_area_from_wing_loading(self):
        params = _cessna_172_params()
        result = size_aircraft(_cessna_172_mission(), params)
        expected = result["W_0"] / params.wing_loading_lb_ft2
        assert result["wing_area"] == pytest.approx(expected, rel=1e-6)

    def test_thrust_from_tw_ratio(self):
        params = _cessna_172_params()
        result = size_aircraft(_cessna_172_mission(), params)
        expected = params.thrust_to_weight * result["W_0"]
        assert result["thrust"] == pytest.approx(expected, rel=1e-6)

    def test_empty_weight_positive_and_less_than_w0(self):
        result = size_aircraft(_cessna_172_mission(), _cessna_172_params())
        assert 0.0 < result["W_empty"] < result["W_0"]

    def test_fuel_weight_positive_and_less_than_w0(self):
        result = size_aircraft(_cessna_172_mission(), _cessna_172_params())
        assert 0.0 < result["W_fuel"] < result["W_0"]


# ---------------------------------------------------------------------------
# Boeing 737-class sizing
# ---------------------------------------------------------------------------


class TestBoeing737Sizing:
    """Boeing 737-class jet transport: W_0 ≈ 150 000 lb ± 10 %."""

    def test_w0_within_10_percent_of_150000_lb(self):
        result = size_aircraft(_boeing_737_mission(), _boeing_737_params())
        W_0 = result["W_0"]
        assert abs(W_0 - 150_000.0) / 150_000.0 < 0.10, (
            f"W_0 = {W_0:.0f} lb; expected 150 000 ± 15 000 lb"
        )

    def test_weight_budget_closes(self):
        params = _boeing_737_params()
        result = size_aircraft(_boeing_737_mission(), params)
        total = (
            result["W_empty"]
            + result["W_fuel"]
            + params.payload_lb
            + params.crew_lb
        )
        assert abs(total - result["W_0"]) < 1.0, (
            f"Weight budget error: {total:.0f} vs W_0={result['W_0']:.0f}"
        )

    def test_wing_area_plausible(self):
        """737-class wing area should be in 800–1500 ft²."""
        result = size_aircraft(_boeing_737_mission(), _boeing_737_params())
        assert 800.0 < result["wing_area"] < 1_500.0, (
            f"Wing area {result['wing_area']:.0f} ft² out of plausible range"
        )

    def test_thrust_plausible(self):
        """737-class static thrust: ~40 000–60 000 lbf."""
        result = size_aircraft(_boeing_737_mission(), _boeing_737_params())
        assert 30_000.0 < result["thrust"] < 70_000.0, (
            f"Thrust {result['thrust']:.0f} lbf out of plausible range"
        )

    def test_empty_weight_fraction_reasonable(self):
        """Jet transports have W_e/W_0 in the range 0.45–0.60."""
        result = size_aircraft(_boeing_737_mission(), _boeing_737_params())
        fe = result["W_empty"] / result["W_0"]
        assert 0.45 < fe < 0.60, f"W_e/W_0 = {fe:.3f} out of expected range"


# ---------------------------------------------------------------------------
# Breguet closed-form verification
# ---------------------------------------------------------------------------


class TestBreguetClosedForm:
    """
    Verify the Breguet range equation closed-form identity.

    Given V=200 ktas, L/D=15, c_j=0.5/hr, W_f/W_0=0.4:
        W_end/W_start = 1 - W_f/W_0 = 0.6
        R = (V · L/D / c_j) · ln(1 / 0.6)
          = (200 · 15 / 0.5) · ln(5/3)
          = 6000 · 0.51083
          ≈ 3065 nm
    """

    V = 200.0
    LD = 15.0
    CJ = 0.5
    WF_W0 = 0.4  # fuel fraction

    @property
    def W_end_over_W_start(self) -> float:
        return 1.0 - self.WF_W0

    @property
    def R_analytical(self) -> float:
        return (self.V * self.LD / self.CJ) * math.log(1.0 / self.W_end_over_W_start)

    def test_analytical_range_approximately_3065_nm(self):
        """Closed-form Breguet gives ~3065 nm for the stated parameters."""
        assert self.R_analytical == pytest.approx(3065.1, abs=1.0)

    def test_breguet_fraction_from_range_round_trips(self):
        """breguet_range_fraction(R_analytical) recovers the original fraction."""
        frac = breguet_range_fraction(self.R_analytical, self.V, self.LD, self.CJ)
        assert frac == pytest.approx(self.W_end_over_W_start, rel=1e-6)

    def test_breguet_range_from_weights_matches_analytical(self):
        """breguet_range_nm with W_start/W_end=1/0.6 recovers R_analytical."""
        W_start, W_end = 1.0, self.W_end_over_W_start
        R = breguet_range_nm(W_start, W_end, self.V, self.LD, self.CJ)
        assert R == pytest.approx(self.R_analytical, rel=1e-9)

    def test_breguet_fraction_less_than_one(self):
        frac = breguet_range_fraction(self.R_analytical, self.V, self.LD, self.CJ)
        assert frac < 1.0
        assert frac > 0.0

    def test_breguet_range_increases_with_ld(self):
        """Higher L/D → longer range for same weight fraction."""
        R1 = breguet_range_nm(1.0, 0.6, self.V, 15.0, self.CJ)
        R2 = breguet_range_nm(1.0, 0.6, self.V, 20.0, self.CJ)
        assert R2 > R1

    def test_breguet_range_decreases_with_tsfc(self):
        """Higher TSFC → shorter range for same weight fraction."""
        R1 = breguet_range_nm(1.0, 0.6, self.V, self.LD, 0.5)
        R2 = breguet_range_nm(1.0, 0.6, self.V, self.LD, 0.8)
        assert R2 < R1

    def test_breguet_range_invalid_weights_raises(self):
        with pytest.raises(ValueError):
            breguet_range_nm(1.0, 1.5, self.V, self.LD, self.CJ)  # W_end > W_start

    def test_breguet_range_zero_w_end_raises(self):
        with pytest.raises(ValueError):
            breguet_range_nm(1.0, 0.0, self.V, self.LD, self.CJ)


# ---------------------------------------------------------------------------
# Direct coefficient / API tests
# ---------------------------------------------------------------------------


class TestRaymerCoefficients:
    """Smoke tests for the coefficient table and API."""

    def test_general_aviation_single_in_table(self):
        assert "general_aviation_single" in RAYMER_EMPTY_WEIGHT_COEFFICIENTS

    def test_jet_transport_in_table(self):
        assert "jet_transport" in RAYMER_EMPTY_WEIGHT_COEFFICIENTS

    def test_all_c_values_are_floats(self):
        for cls, (A, C) in RAYMER_EMPTY_WEIGHT_COEFFICIENTS.items():
            assert isinstance(A, float), f"{cls}: A is not float"
            assert isinstance(C, float), f"{cls}: C is not float"
            assert A > 0.0, f"{cls}: A must be positive"

    def test_ga_empty_fraction_at_2400_lb_plausible(self):
        """2.36 * 2400^-0.18 should be in a physically plausible range."""
        A, C = RAYMER_EMPTY_WEIGHT_COEFFICIENTS["general_aviation_single"]
        fe = A * 2_400.0**C
        assert 0.40 < fe < 0.80, f"GA empty fraction = {fe:.4f} at 2400 lb"

    def test_jet_transport_empty_fraction_at_150klb_plausible(self):
        A, C = RAYMER_EMPTY_WEIGHT_COEFFICIENTS["jet_transport"]
        fe = A * 150_000.0**C
        assert 0.40 < fe < 0.65, f"JT empty fraction = {fe:.4f} at 150k lb"

    def test_unknown_class_raises(self):
        mission = MissionProfile(
            segments=[MissionSegment(kind=SegmentKind.WARMUP_TAKEOFF)]
        )
        params = AircraftParams(
            payload_lb=500.0,
            crew_lb=100.0,
            wing_loading_lb_ft2=14.0,
            thrust_to_weight=0.09,
            aircraft_class="this_class_does_not_exist",
        )
        with pytest.raises(ValueError, match="aircraft_class"):
            size_aircraft(mission, params)

    def test_custom_A_C_override(self):
        """Explicit A, C should bypass the aircraft_class lookup."""
        mission = _cessna_172_mission()
        params = AircraftParams(
            payload_lb=500.0,
            crew_lb=100.0,
            wing_loading_lb_ft2=14.0,
            thrust_to_weight=0.09,
            aircraft_class="this_class_does_not_exist",  # ignored
            A=2.36,
            C=-0.18,
        )
        # Should not raise and should return a plausible result
        result = size_aircraft(mission, params)
        assert result["W_0"] > 0.0

    def test_result_keys_present(self):
        result = size_aircraft(_cessna_172_mission(), _cessna_172_params())
        for key in ("W_0", "W_empty", "W_fuel", "wing_area", "thrust"):
            assert key in result, f"Key '{key}' missing from SizingResult"
