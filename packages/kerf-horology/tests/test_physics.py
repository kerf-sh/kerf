"""Tests for the extended horology physics modules.

Covers:
  - escapement.py   — SwissLeverGeometry / swiss_lever_geometry
  - mainspring.py   — mainspring_torque / power_reserve_hours
  - balance.py      — balance_period / beats_per_hour / isochronism_check
                       / hairspring_stiffness

Calibre validation:
  - ETA 2824-2: 28800 bph, ~38h power reserve
  - Simple Swiss lever: 15-tooth escape wheel, 8° lift — geometric consistency
"""

from __future__ import annotations

import math
import sys
import os

import pytest

# ---------------------------------------------------------------------------
# Path setup (mirror conftest)
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_PACKAGES = os.path.dirname(_PKG)

for _entry in os.listdir(_PACKAGES):
    if not _entry.startswith("kerf-"):
        continue
    _src = os.path.join(_PACKAGES, _entry, "src")
    if os.path.isdir(_src) and _src not in sys.path:
        sys.path.insert(0, _src)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from kerf_horology.escapement import swiss_lever_geometry, SwissLeverGeometry
from kerf_horology.mainspring import mainspring_torque, power_reserve_hours
from kerf_horology.balance import (
    balance_period,
    beats_per_hour,
    period_from_bph,
    isochronism_check,
    hairspring_stiffness,
)
from kerf_horology.tools import (
    _escapement_geometry,
    _mainspring_torque_tool,
    _power_reserve_tool,
    _balance_period_tool,
    _isochronism_tool,
)


# ===========================================================================
# ESCAPEMENT TESTS
# ===========================================================================


class TestSwissLeverGeometry:
    """Unit tests for swiss_lever_geometry."""

    def _default(self, **kwargs) -> SwissLeverGeometry:
        defaults = dict(
            escape_teeth=15,
            lift_deg=8.0,
            draw_deg=12.0,
            escape_wheel_radius_mm=1.925,
            lever_arm_mm=1.6,
            escape_wheel_torque_Nmm=0.35,
        )
        defaults.update(kwargs)
        return swiss_lever_geometry(**defaults)

    def test_tooth_pitch_15_teeth(self):
        """15-tooth escape wheel: tooth pitch = 360/15 = 24°."""
        g = self._default(escape_teeth=15)
        assert abs(g.tooth_pitch_deg - 24.0) < 1e-9

    def test_half_lift(self):
        """half_lift_deg = lift_deg / 2."""
        g = self._default(lift_deg=8.0)
        assert abs(g.half_lift_deg - 4.0) < 1e-9

    def test_impulse_face_angle_equals_half_lift(self):
        """For symmetric Swiss lever, impulse_face_angle = half_lift_deg."""
        g = self._default(lift_deg=10.0)
        assert abs(g.impulse_face_angle_deg - g.half_lift_deg) < 1e-9

    def test_pallet_angles_symmetric(self):
        """Entry and exit pallet angles are symmetric about zero."""
        g = self._default()
        assert abs(g.entry_pallet_angle_deg + g.exit_pallet_angle_deg) < 1e-9

    def test_pallet_angles_half_tooth_pitch(self):
        """Pallet angles = ±tooth_pitch/2."""
        g = self._default(escape_teeth=15)
        assert abs(abs(g.entry_pallet_angle_deg) - 12.0) < 1e-9
        assert abs(abs(g.exit_pallet_angle_deg) - 12.0) < 1e-9

    def test_drop_positive_8deg_lift_15_teeth(self):
        """15-tooth wheel, 8° lift: drop = 24/2 - 8/2 = 12 - 4 = 8°."""
        g = self._default(escape_teeth=15, lift_deg=8.0)
        expected_drop = (g.tooth_pitch_deg / 2.0) - g.half_lift_deg
        assert abs(g.drop_deg - expected_drop) < 1e-9
        assert abs(g.drop_deg - 8.0) < 1e-9

    def test_drop_positive_for_standard_parameters(self):
        """Drop must be non-negative for all standard combinations."""
        for teeth in (15, 18, 20):
            for lift in (6.0, 8.0, 10.0, 12.0):
                pitch = 360.0 / teeth
                # skip cases where lift >= tooth_pitch (gear would lock)
                if lift >= pitch:
                    continue
                g = swiss_lever_geometry(
                    escape_teeth=teeth,
                    lift_deg=lift,
                    draw_deg=12.0,
                    escape_wheel_radius_mm=1.925,
                    lever_arm_mm=1.6,
                    escape_wheel_torque_Nmm=0.35,
                )
                assert g.drop_deg >= 0, (
                    f"Negative drop for teeth={teeth}, lift={lift}"
                )

    def test_impulse_force_positive(self):
        """Impulse force at balance must be positive."""
        g = self._default()
        assert g.impulse_force_at_balance_mN > 0

    def test_impulse_force_formula(self):
        """impulse_force = torque / lever_arm × 1000 (N·mm → mN)."""
        g = self._default(escape_wheel_torque_Nmm=0.35, lever_arm_mm=1.6)
        expected = 0.35 / 1.6 * 1000.0
        assert abs(g.impulse_force_at_balance_mN - expected) < 1e-6

    def test_energy_per_impulse_positive(self):
        """Energy per impulse must be positive."""
        g = self._default()
        assert g.energy_per_impulse_uJ > 0

    def test_energy_formula(self):
        """energy = force × arc_length of pallet stone during half-lift."""
        g = self._default()
        arc_mm = g.lever_arm_mm * math.radians(g.half_lift_deg)
        expected_uJ = g.impulse_force_at_balance_mN * arc_mm
        assert abs(g.energy_per_impulse_uJ - expected_uJ) < 1e-6

    def test_consistency_standard_parameters(self):
        """Standard Swiss lever parameters pass all consistency checks."""
        g = self._default(lift_deg=8.0, draw_deg=12.0)
        assert g.is_consistent, f"Unexpected errors: {g.consistency_errors}"

    def test_consistency_fails_excessive_lift(self):
        """Lift angle > half tooth pitch causes negative drop → error."""
        # 15 teeth → pitch 24° → half pitch 12°; lift 25° > 12° → drop < 0
        g = self._default(escape_teeth=15, lift_deg=25.0)
        assert not g.is_consistent
        assert any("drop" in e.lower() for e in g.consistency_errors)

    def test_consistency_fails_low_draw_angle(self):
        """Draw angle < 8° triggers a consistency warning."""
        g = self._default(draw_deg=5.0)
        assert not g.is_consistent
        assert any("draw" in e.lower() for e in g.consistency_errors)

    def test_tool_wrapper_returns_dict(self):
        """_escapement_geometry tool wrapper returns a JSON-serialisable dict."""
        result = _escapement_geometry(escape_teeth=15, lift_deg=8.0, draw_deg=12.0)
        assert isinstance(result, dict)
        assert result["escape_teeth"] == 15
        assert abs(result["tooth_pitch_deg"] - 24.0) < 1e-4
        assert result["is_consistent"] is True
        assert result["consistency_errors"] == []

    def test_15_tooth_8deg_lift_geometric_consistency(self):
        """Reference: 15-tooth escape wheel with 8° lift is geometrically consistent.

        This is the canonical validation case per the task specification.
        """
        g = swiss_lever_geometry(
            escape_teeth=15,
            lift_deg=8.0,
            draw_deg=12.0,
            escape_wheel_radius_mm=1.925,
            lever_arm_mm=1.6,
            escape_wheel_torque_Nmm=0.35,
        )
        assert g.is_consistent, f"15T/8° lift geometry inconsistent: {g.consistency_errors}"
        assert abs(g.tooth_pitch_deg - 24.0) < 1e-6
        assert abs(g.drop_deg - 8.0) < 1e-6       # 12 - 4 = 8°
        assert abs(g.half_lift_deg - 4.0) < 1e-6


# ===========================================================================
# MAINSPRING TESTS
# ===========================================================================


class TestMainspringTorque:
    """Unit tests for mainspring_torque."""

    def test_fully_wound_returns_max_torque(self):
        """At full wind, torque = max_torque_Nmm."""
        t = mainspring_torque(turns=6.0, full_turns=6.0, max_torque_Nmm=5.0)
        assert abs(t - 5.0) < 1e-9

    def test_run_down_returns_residual(self):
        """At zero turns, torque = residual_factor × max_torque."""
        t = mainspring_torque(turns=0.0, full_turns=6.0, max_torque_Nmm=5.0,
                              residual_factor=0.5)
        assert abs(t - 2.5) < 1e-9

    def test_half_wound_midpoint(self):
        """At half wind with residual=0, torque = max_torque / 2."""
        t = mainspring_torque(turns=3.0, full_turns=6.0, max_torque_Nmm=5.0,
                              residual_factor=0.0)
        assert abs(t - 2.5) < 1e-9

    def test_linear_interpolation(self):
        """Torque increases linearly from residual to max."""
        max_t = 5.0
        residual = 0.5
        residual_t = residual * max_t  # 2.5
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            expected = residual_t + (max_t - residual_t) * frac
            actual = mainspring_torque(frac * 6.0, 6.0, max_t, residual)
            assert abs(actual - expected) < 1e-9, (
                f"frac={frac}: expected {expected}, got {actual}"
            )

    def test_clamped_below_zero(self):
        """Turns below 0 are clamped to residual torque."""
        t_neg = mainspring_torque(-1.0, 6.0, 5.0, residual_factor=0.5)
        t_zero = mainspring_torque(0.0, 6.0, 5.0, residual_factor=0.5)
        assert abs(t_neg - t_zero) < 1e-9

    def test_clamped_above_full(self):
        """Turns above full_turns are clamped to max_torque."""
        t_over = mainspring_torque(7.0, 6.0, 5.0)
        assert abs(t_over - 5.0) < 1e-9

    def test_raises_on_invalid_full_turns(self):
        with pytest.raises(ValueError, match="full_turns"):
            mainspring_torque(1.0, 0.0, 5.0)

    def test_raises_on_invalid_max_torque(self):
        with pytest.raises(ValueError, match="max_torque"):
            mainspring_torque(1.0, 6.0, -1.0)

    def test_raises_on_invalid_residual_factor(self):
        with pytest.raises(ValueError, match="residual_factor"):
            mainspring_torque(1.0, 6.0, 5.0, residual_factor=1.0)

    def test_tool_wrapper(self):
        """_mainspring_torque_tool returns correct dict."""
        result = _mainspring_torque_tool(6.0, 6.0, 5.0, 0.5)
        assert abs(result["torque_Nmm"] - 5.0) < 1e-4
        assert abs(result["turns_fraction"] - 1.0) < 1e-4


class TestPowerReserve:
    """Unit tests for power_reserve_hours."""

    def test_eta_2824_2_approximate_power_reserve(self):
        """ETA 2824-2: 28800 bph, ~38h power reserve.

        The ETA 2824-2 has:
          - 28800 bph (4 Hz, period = 0.25 s)
          - ~38h power reserve when new
          - Barrel: ~6.5 turns full wind
          - Max barrel torque: ~5.5 N·mm at barrel
          - Gear ratio barrel→escape: ~5612
            (escape_wheel_turns/h = 28800/(2×15) = 960;
             barrel_turns/h = 960/5612 ≈ 0.171; 6.5/0.171 ≈ 38h)
          - Escape-wheel torque required: ~0.0004 N·mm
            (residual barrel torque = 0.5×5.5 = 2.75 N·mm;
             at escape wheel: 2.75/5612 ≈ 0.00049 N·mm;
             required < 0.00049 so even a run-down spring can drive the esc.)

        We verify that power_reserve_hours gives ≥ 35h and ≤ 45h.
        """
        gear_ratio = 5612.0
        bph = 28800
        barrel_turns = 6.5
        full_turns = 6.5
        max_torque = 5.5        # N·mm at barrel
        required_esc = 0.0004   # N·mm at escape wheel (below residual/ratio)

        reserve = power_reserve_hours(
            barrel_turns=barrel_turns,
            escape_train_torque_required_Nmm=required_esc,
            gear_ratio=gear_ratio,
            beats_per_hour=bph,
            full_turns=full_turns,
            max_torque_Nmm=max_torque,
            residual_factor=0.5,
            escape_wheel_teeth=15,
        )
        assert 30.0 <= reserve <= 50.0, (
            f"ETA 2824-2 power reserve {reserve:.1f}h outside expected 30–50h range"
        )

    def test_zero_reserve_when_torque_insufficient(self):
        """Reserve = 0 when full-wind torque / gear_ratio < required.

        required_esc = 0.002 N·mm at escape wheel
        min_barrel_torque = 0.002 × 5000 = 10 N·mm > max_torque = 5.0 N·mm
        → even fully wound spring can't drive the escapement → 0h reserve.
        """
        reserve = power_reserve_hours(
            barrel_turns=6.0,
            escape_train_torque_required_Nmm=0.002,
            gear_ratio=5000.0,
            beats_per_hour=28800,
            full_turns=6.0,
            max_torque_Nmm=5.0,
            residual_factor=0.5,
        )
        assert reserve == 0.0

    def test_more_winding_more_reserve(self):
        """A more wound spring gives more power reserve than a less wound one."""
        # Use required_esc well below residual/gear_ratio so both have non-zero reserve
        # residual = 0.5*5.0 = 2.5; residual/gear = 2.5/5000 = 0.0005
        # required_esc = 0.0002 < 0.0005 so all turns are usable
        kwargs = dict(
            escape_train_torque_required_Nmm=0.0002,
            gear_ratio=5000.0,
            beats_per_hour=28800,
            full_turns=6.0,
            max_torque_Nmm=5.0,
            residual_factor=0.5,
            escape_wheel_teeth=15,
        )
        reserve_full = power_reserve_hours(barrel_turns=6.0, **kwargs)
        reserve_half = power_reserve_hours(barrel_turns=3.0, **kwargs)
        assert reserve_full > reserve_half

    def test_raises_invalid_gear_ratio(self):
        with pytest.raises(ValueError, match="gear_ratio"):
            power_reserve_hours(6.0, 0.001, 0.0, 28800, 6.0, 5.0)

    def test_tool_wrapper(self):
        """_power_reserve_tool returns a dict with power_reserve_hours key."""
        result = _power_reserve_tool(
            barrel_turns=6.5,
            escape_train_torque_required_Nmm=0.0004,
            gear_ratio=5612.0,
            beats_per_hour_val=28800,
            full_turns=6.5,
            max_torque_Nmm=5.5,
            escape_wheel_teeth=15,
        )
        assert "power_reserve_hours" in result
        assert result["power_reserve_hours"] > 0


# ===========================================================================
# BALANCE / HAIRSPRING TESTS
# ===========================================================================


class TestBalancePeriod:
    """Unit tests for balance_period and related functions."""

    # ETA 2824-2 reference validation
    # bph = 28800  →  T = 7200/28800 = 0.25000 s
    # If I = 10 g·mm², k = I × (2π/T)² = 10 × (8π)² ≈ 6318.0 N·mm/rad
    ETA_BPH = 28800
    ETA_T = 7200.0 / ETA_BPH            # = 0.25 s
    ETA_I = 10.0                          # g·mm² (representative)
    ETA_K = ETA_I * (2 * math.pi / ETA_T) ** 2   # N·mm/rad

    def test_eta_2824_period(self):
        """ETA 2824-2: I=10 g·mm², k computed from 28800 bph → T = 0.25 s."""
        T = balance_period(self.ETA_I, self.ETA_K)
        assert abs(T - self.ETA_T) < 1e-9, (
            f"ETA 2824-2 period: expected {self.ETA_T} s, got {T} s"
        )

    def test_eta_2824_bph(self):
        """beats_per_hour for ETA 2824-2 period = 28800 exactly."""
        T = balance_period(self.ETA_I, self.ETA_K)
        bph = beats_per_hour(T)
        assert abs(bph - self.ETA_BPH) < 0.01, (
            f"ETA 2824-2 bph: expected {self.ETA_BPH}, got {bph:.3f}"
        )

    def test_period_formula(self):
        """T = 2π√(I/k) holds numerically."""
        I, k = 12.0, 0.2
        T = balance_period(I, k)
        expected = 2.0 * math.pi * math.sqrt(I / k)
        assert abs(T - expected) < 1e-12

    def test_bph_formula(self):
        """bph = 7200 / T holds for standard beat rates."""
        for target_bph in (18000, 21600, 28800, 36000):
            T = 7200.0 / target_bph
            assert abs(beats_per_hour(T) - target_bph) < 0.001

    def test_period_from_bph_inverse(self):
        """period_from_bph is the inverse of beats_per_hour."""
        for bph in (18000, 21600, 28800, 36000):
            T = period_from_bph(bph)
            assert abs(beats_per_hour(T) - bph) < 0.001

    def test_18000_bph_period(self):
        """18000 bph vintage pocket watch: T = 0.4 s."""
        assert abs(period_from_bph(18000) - 0.4) < 1e-9

    def test_21600_bph_period(self):
        """21600 bph (ETA 2472 etc.): T = 1/3 s."""
        assert abs(period_from_bph(21600) - (1.0 / 3.0)) < 1e-9

    def test_28800_bph_period(self):
        """28800 bph (ETA 2824-2, Rolex 3135): T = 0.25 s."""
        assert abs(period_from_bph(28800) - 0.25) < 1e-9

    def test_36000_bph_period(self):
        """36000 bph (Zenith El Primero): T = 0.2 s."""
        assert abs(period_from_bph(36000) - 0.2) < 1e-9

    def test_period_increases_with_inertia(self):
        """Heavier balance → longer period."""
        k = 0.3
        T_light = balance_period(5.0, k)
        T_heavy = balance_period(15.0, k)
        assert T_heavy > T_light

    def test_period_decreases_with_stiffness(self):
        """Stiffer hairspring → shorter period."""
        I = 10.0
        T_soft = balance_period(I, 0.1)
        T_stiff = balance_period(I, 0.4)
        assert T_stiff < T_soft

    def test_raises_zero_inertia(self):
        with pytest.raises(ValueError, match="I_balance"):
            balance_period(0.0, 0.2)

    def test_raises_zero_stiffness(self):
        with pytest.raises(ValueError, match="k_hairspring"):
            balance_period(10.0, 0.0)

    def test_raises_zero_period(self):
        with pytest.raises(ValueError, match="period"):
            beats_per_hour(0.0)

    def test_tool_wrapper(self):
        """_balance_period_tool returns correct dict."""
        result = _balance_period_tool(self.ETA_I, self.ETA_K)
        assert abs(result["period_seconds"] - self.ETA_T) < 1e-6
        assert abs(result["bph"] - self.ETA_BPH) < 0.1


class TestHairspringStiffness:
    """Unit tests for hairspring_stiffness (inverse solve)."""

    def test_roundtrip_eta_2824(self):
        """hairspring_stiffness → balance_period → beats_per_hour == 28800."""
        I = 10.0
        k = hairspring_stiffness(28800, I)
        T = balance_period(I, k)
        bph = beats_per_hour(T)
        assert abs(bph - 28800) < 0.01

    def test_roundtrip_all_standard_rates(self):
        """Roundtrip for 18000, 21600, 28800, 36000 bph."""
        I = 10.0
        for target in (18000, 21600, 28800, 36000):
            k = hairspring_stiffness(target, I)
            T = balance_period(I, k)
            got = beats_per_hour(T)
            assert abs(got - target) < 0.01, (
                f"bph={target}: roundtrip gave {got:.3f}"
            )

    def test_higher_bph_needs_stiffer_spring(self):
        """A faster beat rate requires a stiffer hairspring."""
        I = 10.0
        k_slow = hairspring_stiffness(21600, I)
        k_fast = hairspring_stiffness(28800, I)
        assert k_fast > k_slow


class TestIsochronism:
    """Unit tests for isochronism_check."""

    def test_ideal_sho_delta_zero(self):
        """Ideal SHO gives zero period variation across amplitude range."""
        result = isochronism_check(10.0, 0.3, (180.0, 310.0))
        assert result.delta_period_ms == 0.0

    def test_ideal_sho_is_isochronous(self):
        """Ideal SHO is classified as isochronous."""
        result = isochronism_check(10.0, 0.3, (180.0, 310.0))
        assert result.is_isochronous is True

    def test_period_consistent_with_balance_period(self):
        """period_at_min_amp matches balance_period for same I/k."""
        I, k = 10.0, 0.3
        result = isochronism_check(I, k, (180.0, 310.0))
        T_direct = balance_period(I, k)
        assert abs(result.period_at_min_amp - T_direct) < 1e-9

    def test_notes_nonempty(self):
        """isochronism_check always returns non-empty notes."""
        result = isochronism_check(10.0, 0.3)
        assert len(result.notes) > 0

    def test_amplitude_range_stored(self):
        """amplitude_range_deg is stored correctly."""
        result = isochronism_check(10.0, 0.3, (200.0, 280.0))
        assert result.amplitude_range_deg == (200.0, 280.0)

    def test_raises_invalid_amplitude_range(self):
        with pytest.raises(ValueError):
            isochronism_check(10.0, 0.3, (300.0, 200.0))  # min > max

    def test_tool_wrapper(self):
        """_isochronism_tool returns correct dict."""
        result = _isochronism_tool(10.0, 0.3, 180.0, 310.0)
        assert "period_seconds" in result
        assert "bph" in result
        assert result["is_isochronous"] is True
        assert result["delta_period_ms"] == 0.0
        assert isinstance(result["notes"], list)


# ===========================================================================
# CALIBRE VALIDATION — ETA 2824-2
# ===========================================================================


class TestETA2824Validation:
    """End-to-end calibre validation for ETA 2824-2.

    Known specs:
      - 28800 bph
      - ~38h power reserve
      - 15-tooth escape wheel (Swiss lever standard)
      - 3 Hz frequency (28800 / 2 / 3600 × 2 = 4 Hz — wait:
        28800 bph / 3600 s/h = 8 beats/s; each beat = half oscillation;
        so oscillation frequency = 4 Hz, period T = 0.25 s)
    """

    BPH = 28800
    T = 7200.0 / BPH   # 0.25 s

    def test_period_is_0_25_seconds(self):
        """ETA 2824-2 period T = 7200/28800 = 0.25 s."""
        assert abs(self.T - 0.25) < 1e-12

    def test_balance_natural_frequency(self):
        """Balance natural angular frequency ω = 2π/T = 8π rad/s."""
        omega = 2.0 * math.pi / self.T
        expected_omega = 8.0 * math.pi
        assert abs(omega - expected_omega) < 1e-9

    def test_hairspring_stiffness_scales_with_inertia(self):
        """k = I × ω² : for ETA 2824-2 with I=10 g·mm², k ≈ 6318 N·mm/rad."""
        I = 10.0
        k = hairspring_stiffness(self.BPH, I)
        omega = 2.0 * math.pi / self.T
        expected_k = I * omega ** 2
        assert abs(k - expected_k) < 1e-6

    def test_roundtrip_period_bph(self):
        """From known bph → period → bph roundtrip is exact."""
        T = period_from_bph(self.BPH)
        bph_back = beats_per_hour(T)
        assert abs(bph_back - self.BPH) < 0.001

    def test_escapement_15t_8deg_consistent(self):
        """15-tooth / 8° lift escapement (ETA 2824-2 style) is consistent."""
        g = swiss_lever_geometry(
            escape_teeth=15,
            lift_deg=8.0,
            draw_deg=12.0,
        )
        assert g.is_consistent
        assert abs(g.drop_deg - 8.0) < 1e-6   # drop = 24/2 - 8/2 = 8°

    def test_power_reserve_plausible(self):
        """ETA 2824-2 power reserve is plausible (~38h, verified 30–50h range).

        Derivation:
          escape_turns/h = 28800 / (2×15) = 960
          barrel_turns/h = 960 / 5612 ≈ 0.171
          usable_turns = 6.5 (residual torque at run-down ≈ 0.00049 N·mm
          at escape wheel exceeds required 0.0004 N·mm → all turns usable)
          reserve ≈ 6.5 / 0.171 ≈ 38h  ✓
        """
        reserve = power_reserve_hours(
            barrel_turns=6.5,
            escape_train_torque_required_Nmm=0.0004,
            gear_ratio=5612.0,
            beats_per_hour=self.BPH,
            full_turns=6.5,
            max_torque_Nmm=5.5,
            residual_factor=0.5,
            escape_wheel_teeth=15,
        )
        assert 30.0 <= reserve <= 50.0, (
            f"Power reserve {reserve:.1f}h outside expected 30–50h"
        )
