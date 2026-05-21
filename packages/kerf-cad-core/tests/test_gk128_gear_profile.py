"""GK-128 hermetic oracle tests: gear tooth profile generator.

Pure-Python; no OCCT, no database, no ProjectCtx.

Oracles:
  * involute: base_radius == pitch_radius * cos(pressure_angle_rad)
  * involute: pitch_radius == module * teeth / 2
  * involute: wheel_curve contains exactly `teeth` tooth periods
              (determined by counting tooth tips / angular pitches)
  * cycloid:  pitch_radius == module * teeth / 2
  * cycloid:  wheel_curve contains exactly `teeth` tooth periods
  * both:     tooth_curve and wheel_curve are closed (first == last point)
"""

from __future__ import annotations

import math

import pytest

from kerf_cad_core.geom.gears import involute_gear, cycloid_gear
from kerf_cad_core.geom import involute_gear as inv_gear_exported
from kerf_cad_core.geom import cycloid_gear as cyc_gear_exported


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tooth_period_count(wheel_curve: list, teeth: int) -> int:
    """Count tooth periods by dividing the wheel into `teeth` equal angular
    sectors and verifying that at least one point in each sector reaches
    within 20% of the tip-root amplitude.

    This is robust against multiple consecutive points at the tip radius and
    against flat-topped tip arcs.
    """
    pts = wheel_curve[:-1]  # drop closing duplicate
    if not pts:
        return 0
    radii = [math.hypot(p[0], p[1]) for p in pts]
    angles = [math.atan2(p[1], p[0]) % (2.0 * math.pi) for p in pts]
    r_max = max(radii)
    r_min = min(radii)
    # Threshold at 80% of the amplitude above the root
    threshold = r_min + (r_max - r_min) * 0.8
    ang_pitch = 2.0 * math.pi / teeth
    count = 0
    for k in range(teeth):
        lo = k * ang_pitch
        hi = lo + ang_pitch
        for a, rad in zip(angles, radii):
            if lo <= a < hi and rad >= threshold:
                count += 1
                break
    return count


def _is_closed(curve: list, tol: float = 1e-9) -> bool:
    return (
        abs(curve[0][0] - curve[-1][0]) < tol
        and abs(curve[0][1] - curve[-1][1]) < tol
    )


# ===========================================================================
# 1. involute_gear — formula oracles
# ===========================================================================

class TestInvoluteGearOracles:
    """Core oracle invariants that must hold for any valid parameters."""

    @pytest.mark.parametrize("module,teeth,alpha_deg", [
        (1.0,  10, 20.0),
        (2.0,  20, 20.0),
        (3.0,  25, 14.5),
        (0.5,  40, 25.0),
        (4.0,  16, 20.0),
    ])
    def test_pitch_radius_formula(self, module, teeth, alpha_deg):
        """Oracle: pitch_radius == module * teeth / 2."""
        r = involute_gear(module, teeth, alpha_deg)
        assert r["pitch_radius"] == pytest.approx(module * teeth / 2, rel=1e-12)

    @pytest.mark.parametrize("module,teeth,alpha_deg", [
        (1.0,  10, 20.0),
        (2.0,  20, 20.0),
        (3.0,  25, 14.5),
        (0.5,  40, 25.0),
        (4.0,  16, 20.0),
    ])
    def test_base_radius_formula(self, module, teeth, alpha_deg):
        """Oracle: base_radius == pitch_radius * cos(pressure_angle_rad)."""
        r = involute_gear(module, teeth, alpha_deg)
        expected = r["pitch_radius"] * math.cos(math.radians(alpha_deg))
        assert r["base_radius"] == pytest.approx(expected, rel=1e-12)

    def test_base_radius_less_than_pitch(self):
        """base_radius < pitch_radius for all pressure angles in (10, 30)."""
        r = involute_gear(2.0, 20, 20.0)
        assert r["base_radius"] < r["pitch_radius"]

    def test_tooth_curve_closed(self):
        """tooth_curve first point == last point."""
        r = involute_gear(2.0, 20, 20.0)
        assert _is_closed(r["tooth_curve"])

    def test_wheel_curve_closed(self):
        """wheel_curve first point == last point."""
        r = involute_gear(2.0, 20, 20.0)
        assert _is_closed(r["wheel_curve"])

    @pytest.mark.parametrize("teeth", [8, 12, 16, 20, 24, 32, 40])
    def test_wheel_has_exactly_teeth_periods(self, teeth):
        """Oracle: generated wheel_curve has exactly `teeth` tooth-tip peaks."""
        r = involute_gear(module=2.0, teeth=teeth, pressure_angle_deg=20.0)
        peaks = _tooth_period_count(r["wheel_curve"], teeth)
        assert peaks == teeth, (
            f"Expected {teeth} peaks for {teeth}-tooth gear, got {peaks}"
        )

    def test_tooth_curve_points_are_2d(self):
        r = involute_gear(2.0, 20, 20.0)
        for pt in r["tooth_curve"]:
            assert len(pt) == 2

    def test_wheel_curve_points_are_2d(self):
        r = involute_gear(2.0, 20, 20.0)
        for pt in r["wheel_curve"]:
            assert len(pt) == 2

    def test_return_keys(self):
        r = involute_gear(2.0, 20, 20.0)
        for key in ("tooth_curve", "wheel_curve", "pitch_radius", "base_radius"):
            assert key in r, f"Missing key {key!r}"

    def test_tip_radius_approx_pitch_plus_module(self):
        """Max radius in wheel_curve ≈ r_pitch + module (ISO addendum = 1·m)."""
        m, z = 2.0, 20
        r = involute_gear(m, z, 20.0)
        r_tip_expected = r["pitch_radius"] + m
        pts = r["wheel_curve"][:-1]
        r_max = max(math.hypot(p[0], p[1]) for p in pts)
        assert r_max == pytest.approx(r_tip_expected, rel=0.01)


# ===========================================================================
# 2. involute_gear — validation / edge cases
# ===========================================================================

class TestInvoluteGearValidation:

    def test_invalid_module_zero(self):
        with pytest.raises(ValueError, match="module"):
            involute_gear(0, 20, 20.0)

    def test_invalid_module_negative(self):
        with pytest.raises(ValueError, match="module"):
            involute_gear(-1.0, 20, 20.0)

    def test_invalid_teeth_too_few(self):
        with pytest.raises(ValueError, match="teeth"):
            involute_gear(2.0, 2, 20.0)

    def test_invalid_teeth_string(self):
        with pytest.raises((ValueError, TypeError)):
            involute_gear(2.0, "twenty", 20.0)  # type: ignore[arg-type]

    def test_invalid_alpha_too_low(self):
        with pytest.raises(ValueError, match="pressure_angle_deg"):
            involute_gear(2.0, 20, 9.0)

    def test_invalid_alpha_too_high(self):
        with pytest.raises(ValueError, match="pressure_angle_deg"):
            involute_gear(2.0, 20, 31.0)

    def test_invalid_alpha_boundary_10(self):
        """10.0 is excluded (must be strictly > 10)."""
        with pytest.raises(ValueError, match="pressure_angle_deg"):
            involute_gear(2.0, 20, 10.0)

    def test_invalid_alpha_boundary_30(self):
        """30.0 is excluded (must be strictly < 30)."""
        with pytest.raises(ValueError, match="pressure_angle_deg"):
            involute_gear(2.0, 20, 30.0)

    def test_valid_alpha_boundary_just_above_10(self):
        r = involute_gear(2.0, 20, 10.001)
        assert r["pitch_radius"] == pytest.approx(2.0 * 20 / 2, rel=1e-12)

    def test_valid_minimum_teeth(self):
        """teeth=3 is the minimum acceptable."""
        r = involute_gear(1.0, 3, 20.0)
        assert r["pitch_radius"] == pytest.approx(1.5, rel=1e-12)

    def test_large_gear(self):
        """100-tooth gear: verify formula and closure."""
        r = involute_gear(1.0, 100, 20.0)
        assert r["pitch_radius"] == pytest.approx(50.0, rel=1e-12)
        assert _is_closed(r["wheel_curve"])


# ===========================================================================
# 3. cycloid_gear — formula oracles
# ===========================================================================

class TestCycloidGearOracles:

    @pytest.mark.parametrize("module,teeth", [
        (1.0, 12),
        (2.0, 20),
        (3.0, 30),
        (0.5, 40),
    ])
    def test_pitch_radius_formula(self, module, teeth):
        """Oracle: pitch_radius == module * teeth / 2."""
        r = cycloid_gear(module, teeth)
        assert r["pitch_radius"] == pytest.approx(module * teeth / 2, rel=1e-12)

    def test_base_radius_equals_pitch_radius(self):
        """Cycloidal gears have no base circle; base_radius == pitch_radius."""
        r = cycloid_gear(2.0, 20)
        assert r["base_radius"] == pytest.approx(r["pitch_radius"], rel=1e-12)

    def test_tooth_curve_closed(self):
        r = cycloid_gear(2.0, 20)
        assert _is_closed(r["tooth_curve"])

    def test_wheel_curve_closed(self):
        r = cycloid_gear(2.0, 20)
        assert _is_closed(r["wheel_curve"])

    @pytest.mark.parametrize("teeth", [8, 12, 16, 20, 24, 32])
    def test_wheel_has_exactly_teeth_periods(self, teeth):
        """Oracle: generated wheel_curve has exactly `teeth` tooth-tip peaks."""
        r = cycloid_gear(module=2.0, teeth=teeth)
        peaks = _tooth_period_count(r["wheel_curve"], teeth)
        assert peaks == teeth, (
            f"Expected {teeth} peaks for {teeth}-tooth cycloid gear, got {peaks}"
        )

    def test_return_keys(self):
        r = cycloid_gear(2.0, 20)
        for key in ("tooth_curve", "wheel_curve", "pitch_radius", "base_radius"):
            assert key in r, f"Missing key {key!r}"

    def test_tooth_curve_points_are_2d(self):
        r = cycloid_gear(2.0, 20)
        for pt in r["tooth_curve"]:
            assert len(pt) == 2

    def test_wheel_curve_points_are_2d(self):
        r = cycloid_gear(2.0, 20)
        for pt in r["wheel_curve"]:
            assert len(pt) == 2


# ===========================================================================
# 4. cycloid_gear — validation
# ===========================================================================

class TestCycloidGearValidation:

    def test_invalid_module_zero(self):
        with pytest.raises(ValueError, match="module"):
            cycloid_gear(0, 20)

    def test_invalid_module_negative(self):
        with pytest.raises(ValueError, match="module"):
            cycloid_gear(-2.0, 20)

    def test_invalid_teeth_too_few(self):
        with pytest.raises(ValueError, match="teeth"):
            cycloid_gear(2.0, 2)

    def test_valid_minimum_teeth(self):
        """teeth=3 is the minimum acceptable."""
        r = cycloid_gear(1.0, 3)
        assert r["pitch_radius"] == pytest.approx(1.5, rel=1e-12)


# ===========================================================================
# 5. geom __init__ re-export
# ===========================================================================

class TestGeomExports:
    """The two functions must be importable from kerf_cad_core.geom."""

    def test_involute_gear_exported(self):
        assert callable(inv_gear_exported)

    def test_cycloid_gear_exported(self):
        assert callable(cyc_gear_exported)

    def test_exported_involute_pitch_radius(self):
        r = inv_gear_exported(2.0, 20, 20.0)
        assert r["pitch_radius"] == pytest.approx(20.0, rel=1e-12)

    def test_exported_cycloid_pitch_radius(self):
        r = cyc_gear_exported(2.0, 20)
        assert r["pitch_radius"] == pytest.approx(20.0, rel=1e-12)


# ===========================================================================
# 6. Cross-function consistency
# ===========================================================================

class TestCrossConsistency:

    def test_involute_and_cycloid_same_pitch_radius(self):
        """Both gear types yield the same pitch_radius for the same m and z."""
        m, z = 2.0, 20
        ri = involute_gear(m, z, 20.0)
        rc = cycloid_gear(m, z)
        assert ri["pitch_radius"] == pytest.approx(rc["pitch_radius"], rel=1e-12)

    def test_wheel_curve_length_scales_with_teeth(self):
        """More teeth → larger wheel_curve polygon (more points)."""
        r_low  = involute_gear(2.0, 16, 20.0)
        r_high = involute_gear(2.0, 32, 20.0)
        assert len(r_high["wheel_curve"]) > len(r_low["wheel_curve"])
